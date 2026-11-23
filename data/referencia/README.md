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
