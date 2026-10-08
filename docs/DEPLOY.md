# Deploy

Nao faca deploy automatico a partir desta etapa. Use este arquivo como resumo; o passo a passo completo esta em `docs/STAGING.md`.

## Netlify

- Base directory: `frontend`
- Build: `npm run build`
- Publish: `dist`
- Variaveis: `VITE_API_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`

## Render API

- Root: `backend`
- Build: `pip install -r requirements.txt`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health: `/api/health`

## Render Worker

- Root: `backend`
- Build: `pip install -r requirements.txt`
- Start: `python -m app.worker`

## Supabase

Execute `supabase/migrations/001_initial.sql` e configure Auth antes do primeiro smoke test live.
