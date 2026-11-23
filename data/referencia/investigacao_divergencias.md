# Investigação das divergências de casos (SINAN x tabela oficial do MS)

Feita em 10/11/2026, com a bronze de 2026-11-08 (SINAN do FTP do DATASUS, `PRELIM`), contra
`ms_sarampo_casos_obitos_1990_2026.csv`. Tolerância do passo 14: `max(10, 5% do oficial)`.

## Resolvida: definição da UF (mudança na pipeline)

**Roraima 2018** (gold 269, oficial 368). Dos 359 casos confirmados *notificados* em RR em
2018, 90 não têm UF de residência (`uf_residencia` vazia; são, pelo contexto do surto, migrantes
venezuelanos). A tabela do MS conta esses casos em RR. Regra adotada no passo 14 e no passo 20:
**UF de residência; quando ela está vazia, a UF de notificação**. Com essa regra, RR 2018 fica
358 (dentro da tolerância) e nenhuma outra UF-ano piora. Testes (UF-ano de 2007 a 2024 fora da
tolerância / soma das diferenças absolutas):

| regra | fora da tolerância | soma \|dif\| |
|---|---:|---:|
| só residência (antes) | 7 | 626 |
| só notificação | 7 | 670 |
| residência, senão notificação (agora) | 6 | 548 |

Contar só pela UF de notificação resolveria PA 2021, BA 2019 e MG 2020, mas criaria outras 4
(AP, RJ e SP em 2020; SC em 2019). O MS não usa uma regra única que reproduza todas as UFs.

## Registradas como conhecidas (17/11/2026, Ígor José Rodrigues)

Todas abaixo estão em `divergencias_conhecidas.csv` (status `EXPLICADA` no passo 14). PA 2021,
MG 2020 e BA 2019 pela UF de notificação; Brasil 2007-2008 como casos não reconhecidos na
série oficial; PR 2020, CE 2015 e PE 2013 como provável reclassificação posterior (hipótese
não confirmada: se a vigilância fornecer a base consolidada, vale conferir).

| UF-ano | gold | oficial | dif | o que os dados mostram |
|---|---:|---:|---:|---|
| PR 2020 | 459 | 377 | +82 | nenhuma definição chega perto (por notificação 454; por início dos sintomas 442). 441 confirmados por laboratório, 350 com autoctonia "indeterminada". Hipótese: reclassificação posterior na base da vigilância que o FTP não recebeu. |
| Brasil 2007 | 30 | 0 | +30 | 26 confirmados por laboratório (BA 9, SP 9, PE 3...), todos encerrados em 2007-2008. O MS registra 0 casos de sarampo em 2007 (ano da epidemia de rubéola: 8.281 rubéolas na mesma base). Hipótese: casos depois descartados ou reclassificados (ex.: rubéola ou reação vacinal) na base oficial. |
| Brasil 2008 | 16 | 0 | +16 | mesmo padrão de 2007 (9 por laboratório, 4 clínicos). |
| PA 2021 | 135 | 111 | +24 | 22 dos 135 foram notificados fora do PA. Por UF de notificação, 115 (dentro da tolerância). |
| MG 2020 | 34 | 22 | +12 | 18 dos 34 foram notificados fora de MG; 21 importados. Por UF de notificação, 18. |
| BA 2019 | 67 | 80 | -13 | por UF de notificação, 74; 21 encerrados só em 2020. |
| CE 2015 | 198 | 211 | -13 | nenhuma definição alternativa sobe para 211. Hipótese: casos incluídos depois na base da vigilância. |
| PE 2013 | 189 | 200 | -11 | idem; 51 encerrados só em 2014. Uma unidade acima da tolerância (10). |

# Cobertura vacinal (gold x TabNet)

Comparação do passo 14 com `tabnet_cobertura_uf_ano.csv` (TabNet, atualizado em maio/2023).

**1994-2016, CPNI recalculado: bate.** A gold soma doses e população-alvo do CPNI do FTP por
UF e código e chega ao mesmo valor do TabNet (diferença 0,00 p.p.) em todas as UF-ano, exceto
4 do sarampo monovalente em 1994-1996. Isso confirma a leitura e o processamento do CPNI.

**2017-2019: o FTP é um retrato mais antigo.** Diferenças medianas de 1 a 5 p.p. em 2017-2018 e
de ~60 p.p. em 2019 (no FTP, 2019 está incompleto: o SI-PNI agregado foi descontinuado). O
TabNet recebeu as atualizações desses anos até 2023; os `CPNIBR17-19.DBF` do FTP não.

**2020-2022, base nominal (RNDS) + SINASC: metodologia própria.** A gold segue a nota técnica
do PNI (doses de SCR em crianças de 1 ano, município de aplicação, nascidos vivos do ano
anterior). Diferença média por UF, D1: 2020 -13,8 p.p.; 2021 +1,3 p.p. (erro médio 3,2 p.p.);
2022 +7,0 p.p. Explicação provável: em 2020 parte dos municípios ainda registrava no sistema
antigo, cujas doses não estão na base aberta do RNDS; em 2022 a base nominal de hoje tem
registros que chegaram depois de maio/2023. Foram testadas outras definições (idade 0-1 ou
1-2, UF de residência, SINASC de 2 anos antes, D2 com e sem tetra viral): nenhuma reduz o erro
de forma consistente, então ficou a da nota técnica.

Decisão (17/11/2026, Ígor José Rodrigues): a `gold_serie_cobertura_uf_ano` usa o TabNet em
2017-2022 (CPNI do FTP até 2016; base nominal a partir de 2023, quando não há dado oficial
exportável). As diferenças acima estão em `divergencias_conhecidas.csv` (2017-2022 com
`codigo = *`, todas as UFs, e o Brasil), assim como as 4 do monovalente em 1994-1996 (até
0,1 p.p.). As tabelas `gold_hist_*` e `gold_cobertura_nominal_*` continuam com os valores
calculados das bases, para comparação. Atenção na análise: há uma troca de fonte entre 2022
(TabNet) e 2023 (nominal).
