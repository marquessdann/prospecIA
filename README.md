# ProspecIA — prospecção B2B de empresas sem site

Plataforma que encontra empresas em fontes públicas e autorizadas (Google Places API, OpenStreetMap), classifica a **presença digital** de cada uma com **evidências, fontes consultadas e nível de confiança**, prioriza leads com uma pontuação configurável e organiza a prospecção num CRM simples.

> **Distinção central:** *"Site não informado no Maps"* significa apenas que o cadastro de origem não traz site. **Não** é a mesma coisa que *"Sem site identificado"*, que só é atribuído depois de uma busca web autorizada não encontrar nenhum domínio compatível. A interface, as exportações e os relatórios mantêm essa diferença.

---

## 1. Arquitetura

```
┌────────────┐  /api (proxy)  ┌──────────────────┐     ┌──────────────┐
│ Next.js 15 │ ─────────────▶ │ FastAPI (API)    │ ──▶ │ PostgreSQL   │  dados, fila durável (SKIP LOCKED),
│ React + TS │  cookie httpOnly│ auth, filtros,   │     │              │  cache de API, histórico
│ Tailwind   │                │ exportação, CRM  │     └──────────────┘
└────────────┘                └──────────────────┘            ▲
                                                               │
                              ┌──────────────────┐     ┌──────┴───────┐
                              │ Worker(s) asyncio│ ──▶ │ Redis        │  rate limit compartilhado
                              │ descoberta+verif.│     └──────────────┘
                              └────────┬─────────┘
          ┌──────────────────┬─────────┴───────┬───────────────────┬─────────────────┐
   Google Places (New)   OSM Nominatim+Overpass   Brave Search API   Sites das empresas   IA (Anthropic, opcional)
```

| Camada | Tecnologia | Por quê |
|---|---|---|
| Frontend | Next.js 15 (App Router), React 19, TypeScript, Tailwind, lucide-react, Leaflet | Dashboard responsivo; o navegador só fala com o próprio domínio (`/api` é encaminhado ao backend), então nenhuma chave sai do servidor |
| Backend | Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic | Ecossistema forte para coleta, normalização e IA; OpenAPI automático em `/docs` |
| Banco | PostgreSQL 16 (JSONB) | Dados relacionais + evidências em JSON; a fila de tarefas usa `FOR UPDATE SKIP LOCKED` (durável e escalável horizontalmente) |
| Fila/cache | Fila persistente no PostgreSQL + Redis para rate limit entre workers | Pesquisas sobrevivem a reinícios e podem ser retomadas do último checkpoint |
| IA | Anthropic Claude via SDK oficial (opcional) | Adjudicação de casos ambíguos e resumos, com saída em JSON de esquema fixo |

### Estrutura

```
backend/
  app/
    providers/        # uma integração por arquivo (base.py define os contratos)
      google_places.py  osm_overpass.py  web_search.py (Brave, Google CSE)  registry.py
    verification/     # núcleo: identificação de empresas sem site
      normalize.py  domains.py  site_checker.py  matcher.py  classifier.py  ai.py
    services/         # fila, execução das pesquisas, dedup, pontuação, custos, cache, exportação
    api/              # rotas REST (auth, searches, businesses, dashboard, exports, settings)
    worker.py  main.py  models.py  schemas.py  security.py  demo.py
  alembic/            # migrações
  tests/              # 50 testes (unidade, integrações simuladas, fluxo ponta a ponta)
frontend/
  app/(app)/          # painel, pesquisas, resultados, detalhes, mapa, configurações
  components/  lib/
docker-compose.yml  .env.example
```

---

## 2. Como a classificação funciona (núcleo do produto)

Para cada empresa, `app/verification/classifier.py` executa e **registra como evidência**:

1. **Site na fonte original** — lê o campo de site de cada fonte (Google `websiteUri`, OSM `website`/`contact:website`). Redes sociais, marketplaces (iFood, Doctoralia…) e diretórios são separados e **não contam como site próprio**.
2. **Busca web autorizada** — consulta `"Nome" Cidade` e `"(41) 99999-9999"` (telefone) na Brave Search API. Resultados de redes sociais/diretórios só são associados se o título bater com o nome ou contiver o telefone.
3. **Domínios prováveis (opcional)** — testa via DNS `nomedaempresa.com.br`/`.com` quando nada foi encontrado. Um domínio adivinhado **só é confirmado se o site tiver telefone ou endereço da empresa**.
4. **Verificação HTTP** — DNS, conexão, TLS, status HTTP, redirecionamentos, página estacionada/"em construção"; respeita `robots.txt`; respostas 401/403/429 são registradas como "bloqueia verificação automatizada" (nunca tenta contornar); proteção contra SSRF (bloqueia IPs privados/metadados).
5. **Correspondência** — similaridade de nome × domínio/título, telefone na página, endereço/CEP, cidade. **Nome parecido sem telefone/endereço fica limitado a 55/100** (evita atribuir o site de um homônimo de outra cidade).
6. **IA (opcional)** — só para candidatos ambíguos. O modelo recebe apenas as evidências, responde em JSON com esquema fixo e só pode escolher domínios da lista de candidatos (qualquer outro é descartado). Telefones/e-mails nunca vêm da IA. Sem IA, tudo funciona por regras.
7. **Decisão**

| Status | Quando |
|---|---|
| **POSSUI SITE** | candidato acessível com correspondência ≥ 70 |
| **SITE INDISPONÍVEL** | a fonte informa um domínio próprio que não resolve, recusa conexão, dá erro HTTP ou está estacionado |
| **SITE SUSPEITO OU NÃO CONFIRMADO** | domínio acessível com correspondência 35–69 |
| **SEM SITE IDENTIFICADO** | fonte sem site **e** ≥ 1 busca web bem-sucedida sem domínio compatível (confiança sobe com busca por telefone e cai para nomes genéricos) |
| **SITE NÃO INFORMADO NO MAPS** | fonte sem site e busca web não executada (sem provedor) — confiança 40, explicitamente inconclusivo |
| **VERIFICAÇÃO PENDENTE** | busca falhou (nova tentativa automática) ou dados insuficientes |

Cada verificação grava: status, confiança, justificativa em português, lista de evidências (+/−), fontes consultadas, candidatos avaliados, uso de IA, custo e data. O histórico completo fica visível na página da empresa.

---

## 3. Fontes de dados, limitações e o que exige credenciais

| Fonte | Uso | Credencial | Limitações |
|---|---|---|---|
| **OpenStreetMap** (Nominatim + Overpass) | descoberta | **não precisa** | cobertura colaborativa, em geral bem menor que o Google Maps no Brasil; servidores públicos limitam uso (respeitamos 1 req/s no Nominatim e cache de 7 dias). Para volume, hospede instâncias próprias. Atribuição ODbL obrigatória (já no mapa). |
| **Google Places API (New)** — Text Search | descoberta | `GOOGLE_PLACES_API_KEY` + faturamento | máx. 20 resultados/página e **60 por consulta**: para cidades grandes, pesquise por bairros/CEPs (a interface aceita várias localizações em lote). Termos restringem cache — padrão sem cache, `place_id` guardado e dados com retenção configurável (30 dias) com expurgo automático do payload bruto. |
| **Brave Search API** | verificação web | `BRAVE_SEARCH_API_KEY` | pago por consulta; respeite os termos de armazenamento do seu plano. |
| Google Programmable Search (CSE) | verificação web (legado) | `GOOGLE_CSE_API_KEY` + `GOOGLE_CSE_CX` | fechado a novos clientes; encerra em **01/01/2027**. Mantido só para quem já tem acesso. |
| ~~Bing Web Search / Bing Maps~~ | — | — | **Bing Search APIs foram aposentadas em 11/08/2025**; Bing Maps for Enterprise está em descontinuação (sucessor: Azure Maps). Não implementados — a arquitetura de `providers/` permite adicionar Azure Maps, Foursquare, SerpAPI etc. implementando `PlaceProvider`/`WebSearchProvider` e registrando em `registry.py`. |
| Diretórios/associações comerciais | — | — | não há API pública padronizada; integre caso a caso, somente com autorização. Nenhum scraping de sites que proíbem coleta. |
| **Anthropic Claude** | IA opcional | `ANTHROPIC_API_KEY` + `AI_PROVIDER=anthropic` | sem chave, a classificação é 100% determinística. |

**Funciona sem nenhuma credencial:** cadastro/login, pesquisas no OpenStreetMap, checagem do site informado na fonte (DNS/HTTP), teste de domínios prováveis, deduplicação, pontuação, CRM, filtros, mapa, exportação CSV/Excel, histórico, controle de consumo. Nesse modo, empresas sem site no cadastro ficam como **"Site não informado no Maps"** (honesto: não há busca web para confirmar).

**Exige credenciais:** Google Places (maior cobertura), busca web (para concluir **"Sem site identificado"**), IA.

Nenhum mecanismo contorna CAPTCHA, autenticação, limites de acesso ou bloqueios.

---

## 4. Custos estimados (out/2026 — confira as páginas oficiais)

Preços configuráveis no `.env` (`COST_*`, `AI_*_PRICE_PER_MTOK`). A tela "Nova pesquisa" mostra a estimativa antes de iniciar.

| Item | Premissa | Preço de referência | Por 1.000 empresas |
|---|---|---|---|
| Google Text Search (SKU Enterprise, por pedir site/telefone/avaliação) | 20 empresas/requisição → 50 req. | ~US$ 35 / 1.000 req.; 1.000 req./mês grátis por SKU | **~US$ 1,75** |
| Brave Search API | 2 consultas/empresa (nome+cidade, telefone) | ~US$ 5 / 1.000 consultas (crédito mensal de US$ 5) | **~US$ 10,00** |
| IA — `claude-opus-5-5` (padrão) | ~35% das empresas ambíguas; ~1.800 tokens entrada / 350 saída | US$ 4 / US$ 20 por milhão de tokens | ~US$ 5,00 |
| IA — `claude-haiku-5-5` (alternativa) | idem | US$ 0,10 / US$ 0,50 por milhão | ~US$ 0,12 |
| OpenStreetMap | — | gratuito | US$ 0 |
| Verificação HTTP/DNS | — | — | US$ 0 |

**Total aproximado:** ~US$ 17 por 1.000 empresas com Google + Brave + IA padrão; ~US$ 12 sem IA ou com Haiku; **~US$ 10 com OSM + Brave**; **US$ 0 com apenas OSM** (sem confirmar "Sem site identificado"). 10.000 empresas ≈ US$ 120–170. Cache, créditos gratuitos e reaproveitamento de verificações recentes (`VERIFICATION_TTL_DAYS`) reduzem o custo real.

Fontes de preço: [Brave Search API](https://brave.com/search/api/), [Google Maps Platform pricing](https://developers.google.com/maps/billing-and-pricing/pricing), [preços Anthropic](https://www.anthropic.com/pricing). Valores de terceiros e mudanças de SKU devem ser verificados antes de orçar.

### Uso individual e gratuito (sem cartão de crédito)
Com `FREE_TIER_ONLY=true` o sistema conta cada requisição cobrável (reserva atômica no banco, válida
mesmo com vários workers) e **bloqueia antes de sair da cota grátis** de cada provedor — Google
Places (~1.000 consultas/mês) e Brave (~US$ 5 de crédito/mês). A IA fica desligada nesse modo,
`WEB_QUERIES_PER_BUSINESS=1` dobra o rendimento da Brave e `SINGLE_USER_MODE=true` permite apenas a
sua conta. Se a cota acabar, nada é classificado como "Sem site" sem a busca: a empresa fica como
"Site não informado no Maps" até ser reverificada. Passo a passo de cadastro com boleto/cartão de
débito em **[docs/PAGAMENTO.md](docs/PAGAMENTO.md)**.

### Controles de consumo implementados
- Limite de empresas por pesquisa (por usuário e teto global `HARD_MAX_RESULTS_PER_SEARCH`).
- Limite mensal em US$ por usuário: aviso a 80%, bloqueio de novas pesquisas e **pausa automática** de pesquisas em andamento ao atingir 100%.
- Estimativa de custo antes de iniciar; custo real por pesquisa e por provedor (`/settings`).
- Cache persistente (`api_cache`) com TTL por provedor conforme licença; deduplicação de lotes e de verificações.
- Erros 401/402/403/429 sinalizados como problemas de credencial/cota/cobrança no log da pesquisa.

---

## 5. Instalação e execução

### Opção A — Docker Compose (recomendado)
```bash
cp .env.example .env          # preencha SECRET_KEY e as chaves que tiver
docker compose up --build
# http://localhost:3000  (crie a conta na tela de login)
# http://localhost:8000/docs  (API documentada)
```
O container da API aplica as migrações (`alembic upgrade head`) ao iniciar. Para escalar a verificação, aumente as réplicas do `worker`.

### Opção B — Local
Pré-requisitos: Python 3.11+, Node 20+, PostgreSQL 14+, Redis (opcional).
```bash
# Banco
createdb prospecia   # e um usuário com acesso; ajuste DATABASE_URL

# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp ../.env.example .env        # ajuste DATABASE_URL, SECRET_KEY, chaves
alembic upgrade head
uvicorn app.main:app --reload --port 8000
python -m app.worker           # em outro terminal (ou RUN_WORKER_IN_API=true)

# Frontend
cd ../frontend
npm install
API_URL=http://localhost:8000 npm run dev    # http://localhost:3000
```

### Dados de demonstração (FICTÍCIOS)
```bash
cd backend && python -m app.demo            # login: demo@prospecia.local / demo12345
python -m app.demo --remove                 # remove todos os registros fictícios
```
Os registros têm o prefixo **[FICTÍCIO]**, o selo "FICTÍCIO" na interface, domínios reservados `*.example`, telefones `0000-xxxx`, coluna própria na exportação e um aviso no painel. Nunca são misturados aos resultados de pesquisas reais (a deduplicação os ignora).

### Testes
```bash
cd backend
pytest                                                  # SQLite
TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost/prospecia_test pytest   # PostgreSQL
cd ../frontend && npm run typecheck && npm run build
```
Cobrem: as 6 classificações (com/sem site, site quebrado, domínio estacionado, homônimo de outra cidade, só redes sociais, falha da busca), a IA não poder inventar domínio, SSRF, robots.txt, bloqueio 403, timeout, parsing das APIs Google/OSM/Brave, retentativa em 429, credencial inválida, deduplicação entre fontes, fluxo completo via API (pesquisa → fila → verificação → filtros → CRM → CSV/Excel → reabrir/reexecutar), pausa/retomada, falha temporária e persistente, limite de consumo, permissões, CSRF e isolamento entre organizações.

---

## 6. Como obter as chaves

**Google Places API (New)**
1. Crie um projeto em https://console.cloud.google.com e **ative o faturamento**.
2. Em *APIs e serviços → Biblioteca*, ative **Places API (New)**.
3. Em *Credenciais*, crie uma chave de API e **restrinja-a** à Places API (New) e ao IP do servidor.
4. Defina `GOOGLE_PLACES_API_KEY`. Configure alertas/cotas de orçamento no Google Cloud.

**Brave Search API**
1. Cadastre-se em https://api-dashboard.search.brave.com, escolha o plano *Search* e gere a chave.
2. Defina `BRAVE_SEARCH_API_KEY`.

**Anthropic (opcional)**
1. Crie uma chave em https://console.anthropic.com.
2. Defina `AI_PROVIDER=anthropic` e `ANTHROPIC_API_KEY`. O modelo padrão é `claude-opus-5-5`; `AI_MODEL=claude-haiku-5-5` reduz custos. O fallback do lado do servidor (`AI_USE_SERVER_FALLBACKS=true`) evita perda de análise em recusas.

**OpenStreetMap:** sem chave; defina `OSM_CONTACT_EMAIL` (política do Nominatim).

---

## 7. Funcionalidades

- **Pesquisa avançada:** país, estado, cidade, bairro, CEP, endereço, coordenadas/raio (com seleção no mapa), vários locais e segmentos em lote, segmento livre, escolha de fontes, limite de empresas.
- **Progresso em tempo real:** lotes, verificações, custo, eventos e erros de integração; resultados aparecem conforme são processados; pausar, retomar (checkpoint por página), cancelar e reexecutar.
- **Resultados:** tabela com todas as colunas pedidas, busca por texto, ordenação, paginação, seleção múltipla, ações em lote, filtros por status, só redes sociais, telefone, e-mail, perfil no Maps, avaliação, nº de avaliações, fonte, data de verificação, confiança, pontuação, status do CRM, possíveis duplicadas, fictício/real.
- **Detalhes:** dados públicos, links para fontes, evidências, histórico de verificações, observação de IA, notas e interações, responsável, status da prospecção, correção manual (gestores), exclusão (gestores).
- **Mapa:** marcadores coloridos por status.
- **Exportação:** CSV (UTF-8, `;`, compatível com Excel) e XLSX com hyperlinks e aba "Sobre"; respeita filtros/seleção e exclui "Não contatar" por padrão; proteção contra injeção de fórmulas.
- **Pontuação 0–100** com pesos editáveis (gestores) e recálculo de toda a base. É uma prioridade estimada, não garantia de interesse.
- **CRM:** 9 estados, notas, interações, responsáveis, trilha de mudanças, sem disparo automático de mensagens.
- **Usuários e papéis:** admin, gestor, membro; limites individuais.

---

## 8. Segurança e LGPD

- Senhas com bcrypt; JWT em cookie `httpOnly` + `SameSite=Lax`; escrita via cookie exige `X-Requested-With` (CSRF); limitação de tentativas de login; cabeçalhos de segurança.
- Isolamento por organização em todas as consultas; papéis para excluir/corrigir.
- Chaves de API apenas em variáveis de ambiente do servidor.
- Minimização: coletamos dados **empresariais públicos** (nome, endereço, telefone/e-mail comercial, site, avaliações). E-mails só são aproveitados quando publicados no **próprio domínio oficial** da empresa. Payloads brutos têm retenção e expurgo automático.
- Direitos do titular: correção (`PATCH /api/businesses/{id}`), exclusão definitiva (`DELETE`), status **"Não contatar"** (zera a pontuação e sai das exportações).
- Sem contorno de proteções; `robots.txt` respeitado; User-Agent identificável; proteção SSRF.
- Recomendação: registre a base legal (legítimo interesse, com teste de balanceamento) e ofereça opt-out em todo contato comercial.

---

## 9. Limitações conhecidas e próximos passos

- Cobertura depende das fontes e planos contratados; nenhuma ferramenta encontra "todas as empresas" nem pesquisa "toda a internet".
- Busca web é a peça que permite concluir "Sem site identificado"; sem ela o sistema não afirma ausência de site.
- Sites que exigem JavaScript para renderizar conteúdo podem ter correspondência menor (o verificador não executa JS); nesses casos o resultado tende a "Site suspeito", nunca a um falso "Sem site".
- Próximos passos sugeridos: provedores Azure Maps/Foursquare, agendamento recorrente (cron) de pesquisas, SSO, auditoria detalhada, testes E2E do frontend em CI.
