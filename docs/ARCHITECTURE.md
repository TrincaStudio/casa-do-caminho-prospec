# Arquitetura

Fluxo de staging:

1. Usuario autentica no frontend com Supabase Auth.
2. Frontend envia JWT para a API FastAPI.
3. API valida o token no Supabase e cria uma pesquisa `PENDING`.
4. Worker Render reivindica jobs pendentes no Supabase.
5. Research Planner cria buscas por grupo, nao por pergunta.
6. Brave Search descobre URLs.
7. URLs sao normalizadas, deduplicadas e classificadas.
8. Firecrawl extrai apenas URLs selecionadas e limitadas.
9. Evidencias sao persistidas e podem ser reutilizadas.
10. OpenAI recebe evidencias e perguntas agrupadas, retornando structured outputs.
11. Resultados apontam para evidencias; evidencias apontam para fontes.

## Modos

- `mock`: nao chama Brave, Firecrawl ou OpenAI. Usado em dev/CI.
- `live`: exige credenciais reais e nao faz fallback para mock.

## Persistencia

O app usa repository. Em staging, `REPOSITORY_BACKEND=supabase`. O backend usa service role somente no servidor. O frontend usa apenas Supabase anon key.

## Processamento Assincrono

A API nao mantem a request aberta durante a pesquisa. O worker processa pesquisas persistentes e atualiza progresso em `research_progress`.
