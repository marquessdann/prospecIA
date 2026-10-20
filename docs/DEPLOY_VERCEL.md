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

## Passo 2 — Importar o projeto (site + API juntos)

O repositório tem um `vercel.json` na raiz que publica **dois serviços num único projeto e num único
endereço**: o site (pasta `frontend`) e a API Python (pasta `backend`, servida em `/api`).

1. No painel da Vercel: **Add New… → Project** → repositório **prospecIA** → **Import**.
2. **Project Name:** `prospecia`.
3. **Root Directory:** deixe **vazio / `./`** (a raiz do repositório). *Não* escolha `backend` nem `frontend`.
4. Em **Environment Variables**, cole o bloco abaixo no primeiro campo *Key* (a Vercel separa sozinha):

   ```
   APP_ENV=production
   SECRET_KEY=uma-sequencia-aleatoria-longa-de-no-minimo-40-caracteres
   CRON_SECRET=outra-sequencia-aleatoria-longa
   PROCESSING_MODE=request
   AUTO_MIGRATE=true
   DB_NULL_POOL=true
   JOB_STALE_MINUTES=2
   COOKIE_SECURE=true
   SINGLE_USER_MODE=true
   FREE_TIER_ONLY=true
   WEB_QUERIES_PER_BUSINESS=1
   OSM_CONTACT_EMAIL=seu-email@exemplo.com
   ```

5. Clique em **Deploy**. (O banco vem no próximo passo; até lá a API responde com erro.)

## Passo 3 — Criar o banco de dados (Neon, grátis)

1. No projeto **prospecia**, abra a aba **Storage**.
2. **Create Database → Neon (Serverless Postgres)** → plano **Free** → região mais próxima.
3. Conecte o banco ao projeto **prospecia** (marque *Production*, *Preview* e *Development*). A Vercel
   cria sozinha `DATABASE_URL` e `DATABASE_URL_UNPOOLED`.
4. **Deployments** → três pontinhos do último deploy → **Redeploy**.
5. Teste: `https://prospecia.vercel.app/api/health` (troque pelo seu endereço) deve mostrar
   `{"status":"ok", ...}`. As tabelas são criadas automaticamente nessa primeira chamada.

## Passo 4 — Criar sua conta

Abra `https://prospecia.vercel.app`. Na primeira vez a tela abre em **Criar conta**. Como
`SINGLE_USER_MODE=true`, depois disso ninguém mais consegue criar conta.

Pronto: já dá para pesquisar no **OpenStreetMap** (grátis, sem chave).

## Passo 5 — (Opcional) Processar com a aba fechada

Use o **cron-job.org** (grátis, sem cartão):

1. Crie conta em https://cron-job.org.
2. **Create cronjob:**
   - **URL:** `https://prospecia.vercel.app/api/worker/cron`
   - **Schedule:** a cada 15 minutos
   - Em **Advanced → Headers**: `Authorization` = `Bearer SEU_CRON_SECRET`
3. Salve. No histórico deve aparecer resposta 200.

## Passo 6 — Ativar Google Places e Brave (quando conseguir cadastrar o pagamento)

Siga `docs/PAGAMENTO.md` para obter as chaves. Depois, no projeto **prospecia**:
**Settings → Environment Variables** → adicione `GOOGLE_PLACES_API_KEY` e/ou `BRAVE_SEARCH_API_KEY`
→ **Deployments → Redeploy**. O modo gratuito (`FREE_TIER_ONLY=true`) continua impedindo cobranças.

## Atualizações

Toda vez que um novo código for enviado ao GitHub, a Vercel publica sozinha o projeto.

## Problemas comuns

| Sintoma | Causa provável | Solução |
|---|---|---|
| `/api/health` dá erro 500 | banco não conectado | refaça o Passo 3 e o Redeploy |
| "This repository needs a vercel.json" | Root Directory apontando para `backend` ou `frontend` | volte o Root Directory para a raiz (`./`) |
| Pesquisa fica "Na fila" | nenhuma aba aberta e sem cron | deixe a aba aberta ou faça o Passo 5 |
| Erro do OpenStreetMap (429/timeout) | servidores públicos ocupados | o sistema tenta de novo sozinho; pesquise áreas menores (bairros) |
