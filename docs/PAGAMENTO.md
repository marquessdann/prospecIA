# Guia de pagamento e cotas gratuitas (uso individual)

Objetivo: usar o ProspecIA **sem pagar nada**, ficando dentro das cotas grátis do Google e da Brave,
mesmo sem cartão de crédito. Com `FREE_TIER_ONLY=true` o sistema conta cada requisição e **para
sozinho antes de sair da cota grátis**.

> As cotas e regras de pagamento mudam com frequência. Os números abaixo foram levantados em out/2026,
> em parte por fontes de terceiros — **sempre confira no painel de cada provedor**.

## Resumo

| Serviço | Para quê | Precisa de pagamento cadastrado? | Cota grátis (aprox.) | Rende por mês |
|---|---|---|---|---|
| OpenStreetMap | encontrar empresas | **Não** | ilimitada (uso moderado) | sem limite prático |
| Google Places API (New) | encontrar empresas (melhor cobertura) | Sim (cartão ou boleto) | ~1.000 consultas/mês (SKU Text Search Enterprise) | até ~18.000 empresas (90% × 1.000 × 20) |
| Brave Search API | confirmar se a empresa tem site | Sim (cartão) | US$ 5 de crédito/mês ≈ 1.000 buscas | ~900 empresas com 1 busca cada |
| IA (Anthropic) | casos ambíguos | Sim | não há | desligada no modo gratuito |

## Passo 0 — Funciona hoje, sem nada cadastrado

Use só o **OpenStreetMap**. Você terá a lista de empresas e a verificação do site informado no cadastro.
Empresas sem site aparecem como **"Site não informado no Maps"** (candidatas — confirme manualmente).

## Passo 1 — Google Cloud (Google Places)

### Formas de pagamento no Brasil
A documentação oficial do Google Cloud lista ([formas de pagamento](https://cloud.google.com/billing/docs/how-to/payment-methods?hl=pt)):
- cartões de **crédito** Visa, Mastercard, Amex, Elo;
- cartões de **débito com bandeira Visa ou Mastercard**;
- no Brasil, **boleto** em conta de **pré-pagamento** ([moedas e formas de pagamento](https://docs.cloud.google.com/billing/docs/resources/currency?hl=pt-br)).

Cartão **pré-pago** não aparece na lista. Muitos cartões de bancos digitais são, na verdade, **débito
Visa/Mastercard** (inclusive virtuais) — vale tentar. Se recusar, use o **boleto**.

**Vantagem do boleto (pré-pagamento):** você deposita um valor antes e a conta usa esse saldo. Dentro
da cota grátis o saldo nem é consumido, e não existe fatura surpresa no cartão. Confira no painel o
valor mínimo do boleto e o que acontece quando o saldo acaba.

### Passo a passo
1. Acesse https://console.cloud.google.com e crie um projeto (ex.: `prospecia`).
2. **Faturamento → Gerenciar contas de faturamento → Criar conta.** País: Brasil. Escolha cartão de
   débito/crédito, ou o modelo de pré-pagamento com boleto, quando oferecido.
3. **APIs e serviços → Biblioteca →** ative **Places API (New)**.
4. **APIs e serviços → Credenciais → Criar credenciais → Chave de API.** Restrinja a chave:
   - *Restrições de API*: somente **Places API (New)**;
   - *Restrições de aplicativo*: endereço IP do servidor onde o ProspecIA roda (se tiver IP fixo).
5. **Limite no próprio Google (segunda proteção, recomendado):** em *APIs e serviços → Places API (New)
   → Cotas e limites do sistema*, reduza o limite de requisições (por minuto e, quando disponível, por
   dia). Ex.: 30 por dia ≈ 900 por mês.
6. **Faturamento → Orçamentos e alertas:** crie um orçamento de R$ 1 com alerta por e-mail. (Alertas
   avisam, mas não bloqueiam — o bloqueio real é o do passo 5 e o do ProspecIA.)
7. No `.env`: `GOOGLE_PLACES_API_KEY=sua-chave`.

> Use a chave **somente no ProspecIA**. O contador do sistema só enxerga as requisições feitas por ele.

## Passo 2 — Brave Search API

A Brave pede um cartão **Visa ou Mastercard (crédito ou débito)** e faz uma autorização de US$ 1 para
validar; a própria ajuda diz que alguns cartões podem ser recusados e sugere tentar outro
([ajuda da Brave Search API](https://api-dashboard.search.brave.com/app/help-feedback)). Pré-pago não é garantido.

1. Cadastre-se em https://api-dashboard.search.brave.com.
2. Escolha o plano **Search** (inclui o crédito mensal) e cadastre o cartão.
3. Em *API Keys*, gere a chave e coloque no `.env`: `BRAVE_SEARCH_API_KEY=sua-chave`.
4. No painel da Brave, se houver opção de limite de gasto/uso mensal, defina-o igual ao crédito grátis.

Se nenhum cartão for aceito: o ProspecIA continua funcionando sem a Brave (empresas ficam como
"Site não informado no Maps"). A Brave também é vendida pelo AWS Marketplace, mas só em planos pagos.

## Passo 3 — Configurar o ProspecIA

```env
FREE_TIER_ONLY=true
SINGLE_USER_MODE=true
WEB_QUERIES_PER_BUSINESS=1
GOOGLE_PLACES_API_KEY=...
BRAVE_SEARCH_API_KEY=...
AI_PROVIDER=none
```

Em **Configurações → Cotas gratuitas das APIs** você acompanha o uso do mês. Quando uma cota acaba:
- **Google:** a pesquisa para nessa fonte (as outras continuam) e mostra "Cota gratuita atingida".
  Use **Retomar** no mês seguinte.
- **Brave:** as empresas ainda não verificadas ficam como "Site não informado no Maps", com o motivo
  "a cota gratuita acabou". Use **Reverificar** (individual ou em lote) quando a cota renovar.

## Dicas para render mais
- Pesquise por **bairro** em cidades grandes: cada consulta do Google traz até 20 empresas, máx. 60.
- Use o filtro "Site não informado no Maps" para escolher **só as melhores** empresas e verifique
  essas em lote — assim a cota da Brave vai para quem importa.
- Empresas verificadas nos últimos 30 dias não são verificadas de novo (`VERIFICATION_TTL_DAYS`).
