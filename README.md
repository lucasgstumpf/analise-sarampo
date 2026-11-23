# analise-sarampo
Repositorio referente ao trabalho da disciplina Analise Visual de Dados do Mestrado UNESP

Análise de dados de vacinação (SI-PNI) e de casos/exames de sarampo (SINAN) no Brasil.

## Organização

```
pipeline/    código de extração e tratamento, em passos numerados (arquitetura medalhão)
data/        dados gerados pelo pipeline, separados em bronze / silver / gold
notebooks/   análises 01-09 (leem só data/gold, que vai para o git)
notebooks/   análises 01-10 (leem data/gold e data/silver, versionados no git)
```

Os dados passam por três camadas:

| Camada | O que tem | Pasta |
|---|---|---|
| **Bronze** | Dado como veio da fonte: baixado e convertido de formato, sem tratamento | `data/bronze/<fonte>/` |
| **Silver** | Dado limpo: colunas legíveis, tipos corrigidos, séries juntadas, sem duplicatas | `data/silver/<fonte>/` |
| **Gold** | Tabelas pequenas, prontas para os notebooks e para BI (versionadas no git) | `data/gold/<tema>/` |

Para só rodar os notebooks, basta clonar o repositório: a pasta `data/gold/` já vem com tudo o
que eles leem. As três camadas também ficam publicadas no Azure, por versão (data de corte), e
podem ser baixadas sem credencial com `python pipeline/baixar_azure.py <camada>` (ver
[COMO_RODAR, seção 10](pipeline/COMO_RODAR.md#10-publicar-e-recuperar-camadas-no-azure)).

## Como rodar

Passo a passo completo: [pipeline/COMO_RODAR.md](pipeline/COMO_RODAR.md).

A partir da raiz do projeto, com o venv ativado (`pip install -r requirements-lock.txt`):

```
python pipeline/executar_pipeline.py --listar          # mostra os passos
python pipeline/executar_pipeline.py                   # roda tudo, do 01 ao 13
python pipeline/executar_pipeline.py --camada silver gold
python pipeline/executar_pipeline.py --passos 07 09
```

Cada passo também pode ser rodado sozinho, por exemplo `python pipeline/05_silver_sinan_sarampo.py`.
A documentação completa de cada passo (fonte, entradas, saídas e regras) está em
[pipeline/README.md](pipeline/README.md).

## Notebooks de Análise

- `01` a `04`: Análises exploratórias preliminares das fontes primárias (SI-PNI e SINAN).
- `05` a `07`: Validação das camadas Silver e Gold, perfil de crianças e atraso no RNDS.
- `08-eda-completa-vacinacao-sarampo.ipynb`: Panorama analítico completo da vacinação contra sarampo.
- `09-mapas-brasil-vacinacao-sarampo.ipynb`: Mapas coropléticos gerais de doses, fluxos e rankings municipais.
- `10-small-multiples-geograficos.ipynb`: **Small Multiples em Mapas Geográficos e Cartogramas Hexagonais** (fundamentação teórica Tufte, Munzner e Ware; matrizes de tempo, completude D1/D2, demografia/bloqueio, latência do RNDS e insumos SCR/SCRV).

## Fontes oficiais de referência

- Casos confirmados de sarampo, 1990-2026: https://www.gov.br/saude/pt-br/assuntos/saude-de-a-a-z/s/sarampo/situacao-epidemiologica/casos-confirmados-sarampo-1990-2026.pdf
- Óbitos por sarampo, 1990-2026: https://www.gov.br/saude/pt-br/assuntos/saude-de-a-a-z/s/sarampo/situacao-epidemiologica/obitos-sarampo-1990-2026.pdf
