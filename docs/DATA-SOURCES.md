# Fontes de dados

## Implementadas

- Brave Search API: descoberta de URLs por grupo de pesquisa.
- Firecrawl: extracao de paginas selecionadas.
- OpenAI: analise estruturada baseada em evidencias persistidas.

## Preparadas por arquitetura, ainda nao implementadas

- Receita/CNPJ.
- CGU / Portal da Transparencia.
- DataJud/CNJ.
- MTE.
- Ibama.
- CVM.

Essas fontes devem entrar como conectores independentes e alimentar `sources`, `documents` e `evidences`. Nao ha integracao oficial ativa com essas fontes nesta versao.
