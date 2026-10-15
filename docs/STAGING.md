# Staging Casa do Caminho

Este documento prepara o repositorio para staging. Nao inclui secrets reais.

## 1. Supabase

1. Crie um projeto Supabase.
2. Em SQL Editor, execute `supabase/migrations/001_initial.sql`.
3. Em Authentication, mantenha cadastro publico desabilitado se a operacao sera interna.
4. Crie usuarios internos da Casa do Caminho manualmente ou por convite.
5. Copie do painel:
   - Project URL.
   - anon public key.
   - service_role key.
6. Configure Site URL e Redirect URLs com a URL final da Netlify.

## 2. Render API

Crie um Web Service apontando para `backend`.

- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health check: `/api/health`

Variaveis:

- `APP_ENV=staging`
- `APP_NAME=Casa do Caminho Research`
- `PUBLIC_API_URL`: URL publica da API no Render.
- `FRONTEND_URL`: URL da Netlify.
- `CORS_ORIGINS`: URL da Netlify.
- `AUTH_REQUIRED=true`
- `REPOSITORY_BACKEND=supabase`
- `RESEARCH_MODE=live`
- `SUPABASE_URL`: Project URL do Supabase.
- `SUPABASE_ANON_KEY`: anon public key.
- `SUPABASE_SERVICE_ROLE_KEY`: service_role key, secret.
- `SUPABASE_JWT_SECRET`: JWT secret do Supabase, somente se o projeto usar assinatura HS256; nunca exponha no frontend.
- `SUPABASE_JWKS_URL`: URL JWKS, somente se usar assinatura assimétrica; por padrao pode ser omitida e sera derivada de `SUPABASE_URL`.
- `SUPABASE_JWT_AUDIENCE=authenticated`.
- `OPENAI_API_KEY`: chave da OpenAI.
- `OPENAI_MODEL`: modelo configurado, padrao `gpt-5-mini`.
- `BRAVE_SEARCH_API_KEY`: chave Brave Search.
- `FIRECRAWL_API_KEY`: chave Firecrawl.

## 3. Render Worker

Crie um Background Worker apontando para `backend`.

- Build command: `pip install -r requirements.txt`
- Start command: `python -m app.worker`

Use as mesmas variaveis da API, exceto que `PUBLIC_API_URL`, `FRONTEND_URL` e `CORS_ORIGINS` sao menos criticas para o worker.

## 4. Netlify

Crie um site apontando para `frontend`.

- Build command: `npm run build`
- Publish directory: `dist`
- SPA fallback: `frontend/netlify.toml` ja possui redirect para `/index.html`.

Variaveis:

- `VITE_API_URL`: URL publica da API Render.
- `VITE_SUPABASE_URL`: Project URL do Supabase.
- `VITE_SUPABASE_ANON_KEY`: anon public key do Supabase.

Essas variaveis sao publicas no bundle frontend. Nunca coloque service role, OpenAI, Brave ou Firecrawl na Netlify.

## 5. APIs Externas

- OpenAI API Key: painel da plataforma OpenAI, em API keys.
- Brave Search API Key: painel Brave Search API.
- Firecrawl API Key: painel Firecrawl.

## 6. Smoke Test Live

Depois de configurar credenciais:

1. Abra a URL da Netlify.
2. Entre com um usuario criado no Supabase Auth.
3. Crie uma pesquisa com nome, CNPJ e site de uma empresa de teste.
4. Confirme que a pesquisa aparece como `PENDING` ou `PROCESSING`.
5. Abra logs do worker no Render e confirme que ele reivindicou o job.
6. Aguarde progresso por etapas.
7. Confirme no dossie:
   - status por pergunta;
   - resposta e resumo;
   - evidencias;
   - fontes clicaveis;
   - data de acesso;
   - consumo Brave/Firecrawl/OpenAI.
8. Atualize o navegador e confirme que o historico e o dossie permanecem.
9. Reinicie a API e confirme que a pesquisa continua visivel.

## 7. Bloqueios Comuns

- `401`: usuario nao autenticado ou callback URL incorreta no Supabase.
- `503 Autenticacao indisponivel`: `SUPABASE_URL` ou `SUPABASE_ANON_KEY` ausente na API.
- Worker nao processa: `REPOSITORY_BACKEND` nao esta como `supabase`, worker sem `SUPABASE_SERVICE_ROLE_KEY`, ou `RESEARCH_MODE` diferente de `live`.
- Pesquisa falha em live: verifique keys OpenAI, Brave e Firecrawl nos logs do worker.
