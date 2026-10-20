# Publicar o ProspecIA na nuvem (Vercel + Neon) — sem cartão de crédito

Resultado: o sistema fica em um endereço como `https://prospecia.vercel.app`, acessível de qualquer
computador ou celular, sem instalar nada.

| Peça | Serviço | Custo | Cartão? |
|---|---|---|---|
| Site (frontend) | Vercel — plano Hobby | grátis | não |
| API (backend Python) | Vercel — plano Hobby | grátis | não |
| Banco de dados | Neon Postgres (pelo painel da Vercel) | grátis (0,5 GB) | não |

> ⚠️ **Atenção aos termos:** o plano Hobby da Vercel é destinado a uso **pessoal e não comercial**.
> Se o ProspecIA virar ferramenta de trabalho da sua empresa, a Vercel pede o plano Pro (pago).
> Leia os termos atuais em https://vercel.com/legal e decida conforme o seu caso.

## Como funciona sem servidor

Na Vercel não existe um "worker" rodando o tempo todo. Por isso, com `PROCESSING_MODE=request`:
- **enquanto o ProspecIA estiver aberto no navegador**, ele mesmo vai pedindo ao servidor para
  processar a fila em etapas de ~40 s (aparece "Processando N tarefa(s)" no menu lateral);
- se você fechar a aba, a pesquisa **não se perde**: ela continua do ponto onde parou quando você
  voltar (ou quando o cron rodar — veja o Passo 5).

---

## Passo 1 — Criar a conta na Vercel

1. Acesse https://vercel.com/signup.
2. Escolha **Hobby** e clique em **Continue with GitHub** (use a mesma conta onde está o repositório
   `prospecIA`).
3. Autorize a Vercel a acessar o repositório `prospecIA` quando ela pedir.

## Passo 2 — Publicar a API (backend)

1. No painel da Vercel: **Add New… → Project**.
2. Na lista, escolha o repositório **prospecIA** → **Import**.
3. Preencha:
   - **Project Name:** `prospecia-api`
   - **Root Directory:** clique em *Edit* e escolha a pasta **`backend`**
   - **Framework Preset:** deixe o que a Vercel detectar (FastAPI/Python) — se aparecer "Other", tudo bem.
4. Abra **Environment Variables** e adicione (nome = valor):

   | Nome | Valor |
   |---|---|
   | `APP_ENV` | `production` |
   | `SECRET_KEY` | uma sequência aleatória longa (mín. 40 caracteres) |
   | `CRON_SECRET` | outra sequência aleatória longa (diferente da anterior) |
   | `PROCESSING_MODE` | `request` |
   | `AUTO_MIGRATE` | `true` |
   | `DB_NULL_POOL` | `true` |
   | `JOB_STALE_MINUTES` | `2` |
   | `TICK_BUDGET_SECONDS` | `40` |
   | `COOKIE_SECURE` | `true` |
   | `SINGLE_USER_MODE` | `true` |
   | `FREE_TIER_ONLY` | `true` |
   | `WEB_QUERIES_PER_BUSINESS` | `1` |
   | `OSM_CONTACT_EMAIL` | seu e-mail (exigido pela política do OpenStreetMap) |

5. Clique em **Deploy**. (Ainda vai faltar o banco — é o próximo passo.)

## Passo 3 — Criar o banco de dados (Neon, grátis)

1. Dentro do projeto **prospecia-api**, abra a aba **Storage**.
2. **Create Database → Neon (Serverless Postgres)** → plano **Free** → região mais próxima
   (ex.: São Paulo, se houver; senão Washington/US East).
3. Na tela seguinte, conecte o banco ao projeto **prospecia-api** (marque *Production*, *Preview* e
   *Development*). A Vercel cria sozinha as variáveis `DATABASE_URL` e `DATABASE_URL_UNPOOLED`.
4. Vá em **Deployments**, clique nos três pontinhos do último deploy → **Redeploy**.
5. Teste: abra `https://prospecia-api.vercel.app/api/health` (troque pelo endereço do seu projeto).
   Deve aparecer `{"status":"ok", ...}`. Na primeira chamada as tabelas são criadas automaticamente.

## Passo 4 — Publicar o site (frontend)

1. **Add New… → Project** → o mesmo repositório **prospecIA** → **Import**.
2. Preencha:
   - **Project Name:** `prospecia`
   - **Root Directory:** **`frontend`**
   - **Framework Preset:** Next.js (detectado automaticamente)
3. **Environment Variables:**

   | Nome | Valor |
   |---|---|
   | `API_URL` | o endereço da API do Passo 3, ex.: `https://prospecia-api.vercel.app` (sem barra no final) |

4. **Deploy**. Ao terminar, abra o endereço (ex.: `https://prospecia.vercel.app`).
5. Na primeira vez a tela abre em **Criar conta**: cadastre-se. Como `SINGLE_USER_MODE=true`,
   depois disso ninguém mais consegue criar conta.

Pronto: já dá para pesquisar no **OpenStreetMap** (grátis, sem chave).

## Passo 5 — (Opcional) Processar com a aba fechada

O projeto da API já vem com um cron da Vercel que roda **1 vez por dia** (limite do plano gratuito).
Para processar com mais frequência, use o **cron-job.org** (grátis, sem cartão):

1. Crie conta em https://cron-job.org.
2. **Create cronjob:**
   - **URL:** `https://prospecia-api.vercel.app/api/worker/cron`
   - **Schedule:** a cada 15 minutos
   - Em **Advanced → Headers**, adicione: `Authorization` = `Bearer SEU_CRON_SECRET`
     (o mesmo valor que você colocou em `CRON_SECRET`, com a palavra `Bearer` e um espaço antes).
3. Salve. No histórico do cron-job.org deve aparecer resposta 200.

## Passo 6 — Ativar Google Places e Brave (quando conseguir cadastrar o pagamento)

Siga `docs/PAGAMENTO.md` para obter as chaves. Depois, no projeto **prospecia-api**:
**Settings → Environment Variables** → adicione `GOOGLE_PLACES_API_KEY` e/ou `BRAVE_SEARCH_API_KEY`
→ **Deployments → Redeploy**. O modo gratuito (`FREE_TIER_ONLY=true`) continua impedindo cobranças.

## Atualizações

Toda vez que um novo código for enviado ao GitHub, a Vercel publica sozinha os dois projetos.

## Problemas comuns

| Sintoma | Causa provável | Solução |
|---|---|---|
| `/api/health` dá erro 500 | banco não conectado | refaça o Passo 3 e o Redeploy |
| Login não mantém a sessão | `API_URL` errado no frontend | confira o endereço (com `https://`, sem `/` no final) e faça Redeploy |
| Pesquisa fica "Na fila" | nenhuma aba aberta e sem cron | deixe a aba aberta ou faça o Passo 5 |
| Erro do OpenStreetMap (429/timeout) | servidores públicos ocupados | o sistema tenta de novo sozinho; pesquise áreas menores (bairros) |
