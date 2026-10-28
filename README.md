# analise-sarampo
Repositorio referente ao trabalho da disciplina Analise Visual de Dados do Mestrado UNESP

Análise de dados de vacinação (SI-PNI) e de casos/exames de sarampo (SINAN) no Brasil.

## Organização

```
pipeline/    código de extração e tratamento, em passos numerados (arquitetura medalhão)
data/        dados gerados pelo pipeline, separados em bronze / silver / gold
notebooks/   análises 01-09 (leem só data/gold, que vai para o git)
```

Os dados passam por três camadas:

| Camada | O que tem | Pasta |
|---|---|---|
| **Bronze** | Dado como veio da fonte: baixado e convertido de formato, sem tratamento | `data/bronze/<fonte>/` |
| **Silver** | Dado limpo: colunas legíveis, tipos corrigidos, séries juntadas, sem duplicatas | `data/silver/<fonte>/` |
| **Gold** | Tabelas pequenas, prontas para os notebooks e para BI (versionadas no git) | `data/gold/<tema>/` |

Para só rodar os notebooks, basta clonar o repositório: a pasta `data/gold/` já vem com tudo o
que eles leem.

## Como rodar

Passo a passo completo: [pipeline/COMO_RODAR.md](pipeline/COMO_RODAR.md).

A partir da raiz do projeto, com o venv ativado (`pip install -r requirements.txt`):

```
python pipeline/executar_pipeline.py --listar          # mostra os passos
python pipeline/executar_pipeline.py                   # roda tudo, do 01 ao 12
python pipeline/executar_pipeline.py --camada silver gold
python pipeline/executar_pipeline.py --passos 07 09
```

Cada passo também pode ser rodado sozinho, por exemplo `python pipeline/05_silver_sinan_sarampo.py`.
A documentação completa de cada passo (fonte, entradas, saídas e regras) está em
[pipeline/README.md](pipeline/README.md).

## Fontes oficiais de referência

- Casos confirmados de sarampo, 1990-2026: https://www.gov.br/saude/pt-br/assuntos/saude-de-a-a-z/s/sarampo/situacao-epidemiologica/casos-confirmados-sarampo-1990-2026.pdf
- Óbitos por sarampo, 1990-2026: https://www.gov.br/saude/pt-br/assuntos/saude-de-a-a-z/s/sarampo/situacao-epidemiologica/obitos-sarampo-1990-2026.pdf
