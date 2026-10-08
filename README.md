# Casa do Caminho Research

Aplicacao para pesquisa publica e organizacao de evidencias sobre empresas potenciais parceiras da Casa do Caminho.

O sistema nao faz score, ranking, aprovacao ou reprovacao automatica. Ele pesquisa, coleta, organiza e apresenta evidencias para decisao humana.

## Implementado

- Frontend React/Vite com Supabase Auth, dashboard, nova pesquisa, progresso, cancelamento e dossie.
- Backend FastAPI com endpoints autenticados para checklist, pesquisas, consulta e cancelamento.
- Worker Render separado (`python -m app.worker`) para processar jobs persistentes.
- Repository com backend Supabase para staging/producao e memory para desenvolvimento/testes.
- Migration Supabase com tabelas normalizadas, RLS e policies de leitura por usuario.
- Research Planner que reduz buscas Brave agrupando as 65 perguntas em grupos estrategicos.
- Normalizacao/deduplicacao de URLs, classificacao de fontes, cache de buscas/documentos e controle basico de uso.
- Modo `mock` sem OpenAI, Brave ou Firecrawl.
- Modo `live` sem fallback silencioso para mock.
- Testes automatizados sem consumo de APIs reais.

## Planejado

- Conectores oficiais dedicados para Receita/CNPJ, CGU, DataJud/CNJ, MTE, Ibama e CVM.
- Exportacao PDF/Docx do dossie.
- Observabilidade avancada de custos e qualidade.
- Convites/admin UI para usuarios internos.

## Arquitetura

Netlify frontend -> Render API -> Supabase Auth/Postgres -> Render worker -> Brave Search + Firecrawl + OpenAI -> Supabase -> dossie.

A API cria pesquisas como `PENDING`. O worker reivindica o proximo job pendente, atualiza progresso persistente, executa o pipeline e salva fontes, documentos, evidencias e respostas.

## Desenvolvimento local

Backend:

```bash
cd backend
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

Worker:

```bash
cd backend
python -m app.worker
```

Para desenvolvimento sem custo, use:

```env
AUTH_REQUIRED=false
REPOSITORY_BACKEND=memory
RESEARCH_MODE=mock
```

## Live/Staging

Staging deve usar:

```env
APP_ENV=staging
AUTH_REQUIRED=true
REPOSITORY_BACKEND=supabase
RESEARCH_MODE=live
```

Configure as credenciais reais apenas nos paineis da Netlify, Render e Supabase. Nunca coloque secrets no frontend.

## Testes e build

```bash
cd backend
python -m pytest
python -m compileall app tests
```

```bash
cd frontend
npm run build
```

## Deploy

- Netlify: base `frontend`, build `npm run build`, publish `dist`, env `VITE_API_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`.
- Render API: root `backend`, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
- Render worker: root `backend`, start `python -m app.worker`.
- Supabase: executar `supabase/migrations/001_initial.sql`, configurar Auth e criar usuarios internos.

Consulte `docs/STAGING.md` para o passo a passo.
