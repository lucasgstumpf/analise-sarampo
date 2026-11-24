# Referências oficiais

Valores publicados pelo Ministério da Saúde, transcritos dos documentos oficiais, para
validar a gold (passo 14, `pipeline/14_validacao.py`). Cada referência guarda o documento
original em `fontes/`, a data de atualização declarada pela fonte e a data em que foi
consultada. Uma referência não é corrigida para "bater" com a pipeline: se a fonte mudar,
entra um arquivo novo, com a nova data.

## `ms_sarampo_casos_obitos_1990_2026.csv`

Casos confirmados e óbitos por sarampo, por UF, grande região e Brasil, 1990 a 2026.

| | |
|---|---|
| Fonte | CGVDI/SVSA/Ministério da Saúde |
| Casos | [casos-confirmados-sarampo-1990-2026.pdf](https://www.gov.br/saude/pt-br/assuntos/saude-de-a-a-z/s/sarampo/situacao-epidemiologica/casos-confirmados-sarampo-1990-2026.pdf), atualizado em 21/09/2026 |
| Óbitos | [obitos-sarampo-1990-2026.pdf](https://www.gov.br/saude/pt-br/assuntos/saude-de-a-a-z/s/sarampo/situacao-epidemiologica/obitos-sarampo-1990-2026.pdf), atualizado em 05/03/2026 |
| Consultado em | 09/11/2026 |
| Observação da fonte | "Dados preliminares sujeitos a revisão" (2026) |

Colunas: `nivel` (uf, regiao, brasil), `codigo` (sigla da UF; N, NE, SE, S, CO; BR),
`nome`, `ano`, `casos_confirmados`, `obitos`. Na região, `SE` é o Sudeste; na UF, Sergipe:
use `nivel` junto com `codigo`.

Como foi transcrito:
- **Óbitos**: extraídos da camada de texto do PDF (sem digitação).
- **Casos**: a tabela do PDF é uma imagem; foi digitada a partir da imagem em resolução
  original.
- **Conferência**: as UFs somam a região e as regiões somam o Brasil em todos os 37 anos,
  para casos e para óbitos (2.442 somas). Na digitação, a única célula lida errado (Sul e RS
  em 2024, 1 caso) apareceu nessa conferência e foi corrigida pela imagem ampliada.

Arquivos (sha256):

```
d5c9afacdf6051ec0e69749ebab56b81083705169328dbfe43629a8e054c535f  fontes/ms_casos_confirmados_sarampo_1990_2026_atualizado_2026-09-21.pdf
1607dfbf2657fc0c0b8df7ac74b22a998f92530cadafe51cc84279d18dac199f  fontes/ms_obitos_sarampo_1990_2026_atualizado_2026-03-05.pdf
```

Como comparar com o SINAN (definição usada pelo passo 14, conferida contra esta tabela):
caso confirmado = `classificacao_final == 1` (sarampo), por ano de notificação e UF de
residência (quando a residência está vazia, a UF de notificação); óbito = caso confirmado com `evolucao_caso == 2` (óbito pelo agravo). O MS
publica a base da vigilância depois das reclassificações; o arquivo do FTP do DATASUS é a
base preliminar. Diferenças pequenas são esperadas; as maiores ficam registradas, com a
justificativa, em `divergencias_conhecidas.csv`.

## `tabnet_cobertura_uf_ano.csv`

Cobertura vacinal oficial por UF e Brasil, 1994 a 2022, do TabNet "Imunizações - Cobertura -
Brasil" (`bd_pni/cpnibr.def`, SI-PNI/CGPNI/SVS/MS, última atualização declarada: maio/2023).

| | |
|---|---|
| Como foi obtida | `python pipeline/utilitarios/consultar_tabnet.py` (preenche o formulário: Linha = UF, Coluna = Ano, todos os anos, sem filtros; e uma consulta nacional com Linha = Ano) |
| Indicadores | Tríplice Viral D1 (021), Tríplice Viral D2 (098), Tetra Viral (097), Sarampo (018) |
| Consultado em | 09/11/2026 (UFs; repetido em 17/11/2026 com resultado idêntico) e 17/11/2026 (Brasil) |
| Arquivos originais | `fontes/tabnet_cpni_*_2026-11-09.csv` (por UF) e `fontes/tabnet_cpni_*_brasil_2026-11-17.csv` |

Colunas: `indicador`, `codigo_imunobiologico`, `codigo_uf` (00 = Brasil), `uf`, `ano`,
`cobertura_percentual`, `consultado_em`. O TabNet avisa para não usar a linha e a coluna de
TOTAL; por isso o Brasil vem da consulta nacional. Metodologia da fonte (nota técnica do
TabNet): local de aplicação; população-alvo de 1 ano = nascidos vivos do ano anterior.

## `divergencias_conhecidas.csv`

Diferenças entre a gold e uma referência que foram analisadas e aceitas, com justificativa.
A validação marca como `EXPLICADA` cada comparação que aparece aqui (`codigo = *` vale para
todas as UFs daquele ano e métrica); as que estão fora da
tolerância e não aparecem aqui ficam como `DIVERGENTE`. Só entra uma linha depois de a
diferença ser investigada; não é lugar para silenciar alertas.

## `ibge_renda_gini_uf_2024_2025.csv`

Rendimento médio mensal real domiciliar per capita (R$) e Índice de Gini por UF e Brasil,
anos de 2024 e 2025, obtidos diretamente da API oficial do **IBGE / SIDRA** (PNAD Contínua Anual).

| | |
|---|---|
| Fonte | IBGE — PNAD Contínua Anual (API v3 de Agregados / SIDRA) |
| Renda per capita | Tabela `7531`, variável `10824`, classificação `1019[49243]` (Total) |
| Índice de Gini | Tabela `7435`, variável `10681` |
| Consultado em | 23/11/2026 |
| Como foi obtida | `python pipeline/utilitarios/baixar_referencias_socioeconomicas.py` |

Colunas: `nivel` (`brasil`, `uf`), `codigo_uf`, `uf`, `nome`, `ano`, `renda_per_capita_reais`,
`indice_gini`, `fonte`, `consultado_em`.

Arquivos originais (`sha256`):

```
bcab35448bafc88d572ad39329fb8bb858a64312ef62308de6df9cc8a796431a  fontes/ibge_sidra_7531_renda_per_capita_2024_2025_2026-11-23.json
5e92e24405017066ba7760869865a8d2ee03a0bb69b791dbe9ebaa3b24044041  fontes/ibge_sidra_7435_gini_2024_2025_2026-11-23.json
```

## `tse_eleicao_2022_2turno_uf.csv`

Resultado oficial do 2º turno das Eleições Presidenciais de 2022 por UF, Exterior (`ZZ`) e Brasil,
agregado a partir do arquivo oficial do **Portal de Dados Abertos do TSE**.

| | |
|---|---|
| Fonte | Tribunal Superior Eleitoral (TSE) — Dados Abertos (`resultados-2022`) |
| Arquivo de origem | `votacao_partido_munzona_2022.zip` -> `votacao_partido_munzona_2022_BR.csv` (`NR_TURNO == 2`, `CD_CARGO == 1`, `QT_VOTOS_NOMINAIS_VALIDOS`) |
| Consultado em | 23/11/2026 |
| Como foi obtida | `python pipeline/utilitarios/baixar_referencias_socioeconomicas.py` |

Colunas: `nivel` (`brasil`, `uf`, `exterior`), `uf`, `votos_lula_pt`, `votos_bolsonaro_pl`,
`votos_validos`, `pct_lula_pt`, `pct_bolsonaro_pl`, `vencedor`, `fonte`, `consultado_em`.
A linha `BR` soma todos os votos válidos (incluindo `ZZ`, batendo exatamente com o total oficial
divulgado pelo TSE: 60.345.999 votos para Lula / 50,90% e 58.206.354 para Bolsonaro / 49,10%).

Arquivo original comprimido (`sha256`):

```
660bdd73a0afe36c9d7d90231a21ae3d8e1015859c1706bba98d598ced355643  fontes/tse_votacao_partido_munzona_2022_BR_2026-11-23.csv.gz
```
