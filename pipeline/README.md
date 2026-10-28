# Pipeline de dados (arquitetura medalhão)

Este diretório tem todo o código que baixa e trata os dados do projeto. Os scripts são
numerados na ordem em que devem rodar: primeiro todas as fontes na **bronze** (01-04),
depois a limpeza na **silver** (05-08) e por fim as tabelas de análise na **gold** (09-12).
A gold tem tudo o que os notebooks precisam: quem tiver só a pasta `data/gold/` (ela vai
para o git) roda todos os notebooks, sem baixar nem tratar nada.

```
pipeline/
├── config.py                      caminhos de cada camada e períodos de coleta (fonte única)
├── executar_pipeline.py           roda os passos em ordem (todos, por camada ou por número)
├── 01_bronze_sinan_sarampo.py     SINAN exames de sarampo 2007-2026 (FTP DATASUS, .dbc)
├── 02_bronze_sipni_historico.py   SI-PNI CPNI e DPNI 1994-2019 (FTP DATASUS, .dbf)
├── 03_bronze_sipni_doses.py       SI-PNI doses individuais 2025+ (S3, .zip mensais, filtra sarampo)
├── 04_bronze_ibge.py              malhas, UFs e população por município (API IBGE)
├── 05_silver_sinan_sarampo.py     SINAN com colunas legíveis + série 2007-2026
├── 06_silver_sipni_historico.py   CPNI e DPNI com colunas legíveis + séries 1994-2019
├── 07_silver_sipni_doses.py       doses limpas, tipadas e sem duplicatas (.parquet)
├── 08_silver_ibge.py              população por município em CSV (código de 6 dígitos)
├── 09_gold_vacinacao.py           tabelas agregadas das doses de sarampo (notebooks 04-09 e BI)
├── 10_gold_sipni_todas_vacinas.py retrato da base mensal completa, todas as vacinas (notebooks 02-03)
├── 11_gold_sinan.py               notificações do SINAN prontas para análise (notebook 01)
├── 12_gold_ibge.py                malhas e população copiadas para a gold (notebook 09)
├── comum/
│   ├── datasus.py                 download do FTP, .dbc -> .dbf -> .csv, leitura da bronze
│   ├── dbc_puro.py                conversão .dbc -> .dbf em Python puro (se o pyreaddbc não instalar)
│   └── dicionarios.py             de-para de colunas de cada fonte e filtro de vacinas de sarampo
└── utilitarios/
    ├── migrar_estrutura_antiga.py move os dados da estrutura antiga para a nova (uma vez só)
    ├── filtrar_mes_manual.py      filtra para sarampo um mês do SI-PNI baixado à mão
    └── ver_primeiras_linhas.py    espia as primeiras linhas de um CSV bruto do SI-PNI
```

## Como rodar

Passo a passo completo (ambiente, execução e conferência): [COMO_RODAR.md](COMO_RODAR.md).

Sempre a partir da raiz do projeto, com o venv ativado:

```
python pipeline/executar_pipeline.py --listar          # mostra os passos encontrados
python pipeline/executar_pipeline.py                   # 01 -> 12
python pipeline/executar_pipeline.py --camada bronze   # só os downloads
python pipeline/executar_pipeline.py --passos 07 09    # só refaz silver e gold das doses
python pipeline/03_bronze_sipni_doses.py --meses 2026-01   # reprocessa um mês (ver passo 10)
python pipeline/07_silver_sipni_doses.py               # um passo isolado
```

O executor roda cada passo num processo separado e para no primeiro que falhar.

Cuidados:
- Os passos 01 a 04 baixam dados da internet. O **03** baixa 1-2 GB por mês do SI-PNI para
  uma pasta temporária (`D:\analise-sarampo\staging` por padrão; mude com a variável de
  ambiente `SARAMPO_STAGING_DIR`). Na primeira vez leva horas; depois, só baixa os meses novos.
- **Retomada:** os passos 01 a 04 pulam o que já está em disco. Cada arquivo é gravado como
  `.tmp` e só recebe o nome final quando termina, então um arquivo com nome final está
  completo. No 01 e no 02 a verificação é por etapa (`.dbc`, `.dbf`, `.csv`); no 03 é pelo
  manifesto mais o CSV do mês; no 04, por arquivo. Para baixar tudo de novo, use `--forcar`
  (no executor ou num passo isolado) ou defina `SARAMPO_FORCAR_DOWNLOAD=1`. A base do SINAN
  é preliminar e o DATASUS a atualiza, então vale rodar `--passos 01 --forcar` de tempos em tempos.
- O **07** carrega todas as doses em memória (cerca de 5 GB de RAM). O **09** também: no
  pico, ao ler a silver, chega a ~8 GB; depois fica em ~6 GB.
- **Retrato da base completa (passo 10):** enquanto filtra cada mês, o 03 conta as doses de
  todas as vacinas e resume cada coluna (% vazio, valores distintos), em
  `bronze/sipni_doses/_perfil_bruto/`. Meses baixados antes dessa função não têm retrato;
  para gerar o de um mês, reprocesse-o com `--meses AAAA-MM` (baixa o mês de novo). Os
  notebooks 02 e 03 usam o de jan/2026.
- Para mudar períodos (anos do SINAN, meses do SI-PNI) ou pastas, edite só o `config.py`.

## Camadas e arquivos gerados

### Bronze: dado como veio da fonte

| Passo | Fonte | Saída em `data/bronze/` |
|---|---|---|
| 01 | SINAN, ficha EXAN (sarampo/rubéola), base preliminar, `EXANBR{AA}.dbc` | `sinan_sarampo/sinan_sarampo_exames_{AAAA}.{dbc,dbf,csv}` |
| 02 | SI-PNI CPNI (cobertura anual) e DPNI (doses mensais por faixa etária), `CPNIBR{AA}.DBF` e `DPNIBR{AA}.DBF` | `sipni_historico/sipni_cobertura_vacinal_{AAAA}.*` e `sipni_doses_aplicadas_agregado_{AAAA}.*` |
| 03 | SI-PNI/RNDS nominal anonimizado, `vacinacao_{mmm}_{AAAA}_csv.zip` | `sipni_doses/sipni_doses_sarampo_sipni_{AAAA}_{mmm}.csv`, a junção `..._completo.csv`, `_auditoria/` (manifesto e log) e `_perfil_bruto/` (retrato do mês com todas as vacinas) |
| 04 | IBGE: malhas GeoJSON, lista de UFs, SIDRA tabela 6579 | `ibge/{uf.json, municipios.json, uf_meta.json, populacao_sidra.json}` |

Os `.csv` da bronze mantêm os nomes de coluna originais da fonte. A única exceção é o passo
03: os `.zip` do SI-PNI trazem todas as vacinas e somam dezenas de GB por ano, então o
download já é filtrado para as vacinas com componente de sarampo e salvo com as colunas
renomeadas. O `.zip` original é apagado só depois de o filtrado estar gravado e registrado
no manifesto, que permite retomar a coleta de onde parou.

`data/bronze/sipni_manual/` guarda as bases baixadas à mão na primeira versão dos notebooks
02-04 (janeiro/2026 completo, amostra e o recorte de sarampo). Os notebooks não dependem
mais delas: hoje leem a gold.

### Silver: dado limpo

| Passo | Entrada | Saída em `data/silver/` | O que muda |
|---|---|---|---|
| 05 | bronze/sinan_sarampo | `sinan_sarampo/sinan_sarampo_exames_{AAAA}.csv` e `..._2007_2026.csv` | colunas legíveis (`COLUNAS_SINAN`), série combinada; valores mantidos como texto |
| 06 | bronze/sipni_historico | `sipni_historico/*_{AAAA}.csv` e `*_1994_2019.csv` | colunas legíveis (`COLUNAS_CPNI`, `COLUNAS_DPNI`), séries combinadas |
| 07 | bronze/sipni_doses | `sipni_doses/vacinacao_sarampo_sipni.parquet`, `dim_municipios.csv`, `_auditoria/processamento_resumo.json` | ver abaixo |
| 08 | bronze/ibge | `ibge/populacao_municipios.csv` | população por município, código IBGE de 6 dígitos |

Regras do passo 07 (1 linha = 1 dose):
- mantém só as colunas úteis (56 -> ~30, incluindo descrição da vacina e fabricante);
- remove os diluentes (DILSCR, DILSR), que passam no filtro por terem "sarampo" no nome;
- converte datas e idade; padroniza sexo, tipo de vacina, faixa etária e número da dose;
- calcula o atraso entre a aplicação e a entrada no RNDS (`atraso_registro_dias`);
- marca vacinações com data fora do mês do arquivo (`vacinacao_fora_do_mes`);
- remove documentos duplicados entre meses;
- numera as doses de cada paciente dentro da janela (`ordem_dose_paciente`; é um mínimo,
  porque doses anteriores a 2025 não aparecem);
- tira os nomes de município da tabela de doses e cria a `dim_municipios.csv`.

O `processamento_resumo.json` registra, por mês, quantas linhas cada regra removeu.

### Gold: tabelas prontas para análise

Cada tabela sai em `.parquet` (vai para o git) e `.csv` (cópia local para Excel/BI). As de
doses são contagens: cada linha diz quantas doses há naquela combinação de variáveis, e os
notebooks somam a coluna `doses` em vez de contar linhas da silver.

**Passo 09, `data/gold/vacinacao/`** (doses de vacinas com componente de sarampo):

| Tabela | Granularidade | Notebooks |
|---|---|---|
| `dim_municipios` | código, nome e UF de cada município | 09 |
| `gold_doses_dia` | dia x mês x grupo de dose x tipo de vacina | 04, 06, 08 |
| `gold_doses_uf_mes` | mês x UF x tipo de vacina x dose | 06, 09 |
| `gold_municipio_mes` | município de residência x mês: doses, D1, D2, crianças de 1-4 anos, pacientes únicos | 07, 08, 09 |
| `gold_perfil` | mês x UF x sexo x faixa etária x raça/cor x vacina x dose | 04, 06, 08, 09 |
| `gold_idade_dose` | mês x idade simples x dose x tipo de vacina | 04, 05, 06, 08 |
| `gold_coorte_criancas_municipio` | crianças de 1-4 anos vacinadas e com 2+ doses, por município | 07, 09 |
| `gold_atraso_registro` | mês x UF x faixa de atraso do registro no RNDS | 07, 09 |
| `gold_estabelecimento` | mês x UF x tipo/natureza do estabelecimento x estratégia | 07 |
| `gold_kpis_mensais` | indicadores-resumo por mês | 06 |
| `gold_resumo_geral` | uma linha com os totais da base (doses, pacientes, datas, alertas de qualidade) | 05, 08 |
| `gold_qualidade_colunas` | cada coluna da silver: tipo, % vazio, distintos, valor mais frequente | 05, 08 |
| `gold_funil_processamento` | linhas removidas por regra da silver, por mês | 05 |
| `gold_doses_por_paciente` | nº de pacientes por nº de doses na janela | 05 |
| `gold_dose_descricao_ordem` | mês x descrição da dose x ordem da dose do paciente | 04, 05 |
| `gold_atraso_dias` | dias exatos de atraso do registro x doses | 05 |
| `gold_intervalo_doses` | idade na 1ª dose x dias entre 1ª e 2ª dose x pacientes | 08 |
| `gold_estrategia_faixa` | mês x faixa etária x tipo/natureza do estabelecimento x estratégia | 04, 08 |
| `gold_categoria_atendimento` | mês x categoria de atendimento | 08 |
| `gold_nacionalidade_etnia` | nacionalidade x etnia indígena | 08 |
| `gold_fluxo_uf` | UF de residência x UF de aplicação | 08, 09 |
| `gold_estabelecimento_cnes` | doses por estabelecimento (CNES), com UF, tipo e natureza | 08 |
| `gold_vacina_fabricante` | mês x descrição/sigla/tipo de vacina x fabricante | 04 |

**Passo 10, `data/gold/sipni_todas_vacinas/`** (base mensal completa, todas as vacinas):

| Tabela | Granularidade | Notebooks |
|---|---|---|
| `gold_imunobiologicos_mes` | mês x imunobiológico x sigla x doses (marca `contem_sarampo`) | 02, 03 |
| `gold_perfil_colunas_bruto` | mês x coluna original: linhas, vazios, % vazio, distintos, exemplo | 02 |

**Passo 11, `data/gold/sinan/`**:

| Tabela | Granularidade | Notebooks |
|---|---|---|
| `gold_sinan_notificacoes` | uma linha por notificação 2007-2026, colunas da análise com códigos numéricos, datas, idade em anos e faixa etária | 01 |
| `gold_sinan_qualidade_colunas` | ano x coluna da ficha (todas as 107) x % vazio | 01 |

**Passo 12, `data/gold/ibge/`**: `uf.json`, `municipios.json`, `uf_meta.json` e
`populacao_municipios.csv`, cópias da bronze/silver do IBGE para os mapas (notebook 09).

Todos os notebooks (01-09) leem só `data/gold/`.

## Migração da estrutura antiga

Antes desta reorganização os dados ficavam em `data/sarampo/{raw,processed}`,
`data/vacinacao/{raw,processed}` e `data/geo`. O utilitário abaixo move tudo para as
pastas novas, sem baixar de novo e sem apagar dados, e corrige os caminhos gravados no
manifesto do passo 03:

```
python pipeline/utilitarios/migrar_estrutura_antiga.py              # simulação: só lista
python pipeline/utilitarios/migrar_estrutura_antiga.py --executar   # move de verdade
```

| Antes | Depois |
|---|---|
| `data/sarampo/raw/` | `data/bronze/sinan_sarampo/` |
| `data/sarampo/processed/` | `data/silver/sinan_sarampo/` |
| `data/vacinacao/raw/` (CPNI/DPNI) | `data/bronze/sipni_historico/` |
| `data/vacinacao/processed/` (CPNI/DPNI) | `data/silver/sipni_historico/` |
| `data/vacinacao/processed/sipni_doses_sarampo_sipni_*` | `data/bronze/sipni_doses/` |
| `data/vacinacao/processed/_auditoria/` | `data/bronze/sipni_doses/_auditoria/` (o `processamento_resumo.json` vai para `data/silver/sipni_doses/_auditoria/`) |
| `data/vacinacao/processed/silver/` | `data/silver/sipni_doses/` |
| `data/vacinacao/processed/gold/` | `data/gold/vacinacao/` |
| outros arquivos de `data/vacinacao/{raw,processed}` | `data/bronze/sipni_manual/` |
| `data/geo/{uf,municipios,uf_meta}.json` | `data/bronze/ibge/` |
| `data/geo/populacao_municipios.csv` | `data/silver/ibge/` |

Correspondência com os scripts antigos (as versões antigas ficaram guardadas em
`_codigo_antigo/`, na raiz do projeto, e podem ser apagadas quando o pipeline novo estiver
conferido):

| Antes | Depois |
|---|---|
| `data/datasus_lib.py` | `pipeline/comum/datasus.py` (download/conversão) |
| `data/dbc_puro.py` | `pipeline/comum/dbc_puro.py` |
| `data/sarampo/extract.py` | `01_bronze_sinan_sarampo.py` + `05_silver_sinan_sarampo.py` |
| `data/vacinacao/extract_historico.py` | `02_bronze_sipni_historico.py` + `06_silver_sipni_historico.py` |
| `data/vacinacao/extract_recentes.py` | `03_bronze_sipni_doses.py` |
| `data/geo/baixar_malhas.py` | `04_bronze_ibge.py` + `08_silver_ibge.py` |
| `data/vacinacao/processar_vacinacao.py` | `07_silver_sipni_doses.py` |
| `data/vacinacao/gerar_gold.py` | `09_gold_vacinacao.py` |
| `data/vacinacao/filtrar_sarampo.py` | `utilitarios/filtrar_mes_manual.py` |
| `data/vacinacao/ver_primeiras_linhas.py` | `utilitarios/ver_primeiras_linhas.py` |
| de-para de colunas espalhados nos scripts | `comum/dicionarios.py` |
