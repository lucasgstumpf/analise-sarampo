# Passo a passo: rodar o pipeline completo

Guia para atualizar todos os dados do projeto no computador (Windows, PowerShell), do
ambiente Python até conferir as saídas. Detalhes de cada passo estão no [README](README.md).

## 1. Abrir o terminal na pasta do projeto

```powershell
cd C:\Users\lucas\Documents\00.Gaspar\Code\analise-sarampo
```

Os comandos abaixo partem desta pasta (a raiz do projeto).

## 2. Criar o ambiente (versões fixas)

Os dados só se reproduzem com o mesmo ambiente. A versão do Python está fixada no
`mise.toml` (3.14.10) e a dos pacotes no `requirements-lock.txt`.

Linux/WSL (com [mise](https://mise.jdx.dev)):

```bash
mise install                      # instala o Python do mise.toml
python -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements-lock.txt
```

Windows (PowerShell), com o Python 3.14 instalado:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-lock.txt
```

Se o PowerShell bloquear o script, rode uma vez
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` e tente de novo.

O `pyreaddbc` fica de fora de propósito: ele precisa de compilador C, e o pipeline usa a
conversão em Python puro (`comum/dbc_puro.py`). O conversor usado fica registrado no manifesto.
O `requirements.txt` guarda só as faixas de versão das dependências diretas; use-o para
atualizar o ambiente, não para reproduzir dados.

## 3. Fixar a data de corte

Tudo o que dependeria de "hoje" (o último mês do SI-PNI a baixar, o ano corrente marcado como
parcial) usa a **data de corte**. Para reproduzir uma execução, use a mesma data dela, que
está em `parametros.data_corte` do `_manifesto.json` de cada camada:

```bash
export SARAMPO_DATA_CORTE=2026-11-08          # PowerShell: $env:SARAMPO_DATA_CORTE = "2026-11-08"
```

Sem a variável, vale a data de hoje, e o executor avisa.

## 4. Conferir que o pipeline está visível

```powershell
python pipeline\executar_pipeline.py --listar
```

Devem aparecer os passos 01 a 14.

## 5. Preparar a pasta temporária dos downloads grandes

O passo 03 baixa cada mês do SI-PNI (1-5 GB, um mês por vez) para `data/bronze/_staging/`
e apaga o `.zip` depois de filtrar. Deixe uns 6 GB livres. Para usar outro disco:

```powershell
$env:SARAMPO_STAGING_DIR = "D:\staging-sarampo"   # bash: export SARAMPO_STAGING_DIR=/mnt/d/staging
```

## 6. Rodar

### Opção A: atualização completa (recomendada para a gestão mensal)

```powershell
python pipeline\executar_pipeline.py
```

Roda bronze (01-04, 15, 16), silver (05-08, 17, 18) e gold (09-13, 19, 20 e, por último, a
validação 14). Os passos de bronze **pulam o que já está em disco**, então rodar de novo só
baixa o que falta:
- **01** e **02** pulam cada ano cujo `.csv` já existe (SINAN 2007-2026 e SI-PNI histórico
  1994-2019 já estão baixados neste computador);
- **03** pula os meses já concluídos (desde jan/2020) e tenta os seguintes; mês que ainda
  não foi publicado fica como `nao_publicado` e não é erro;
- **04**, **15** e **16** pulam os arquivos que já existem; **05-08, 17 e 18** limpam;
  **09-13, 19 e 20** geram as tabelas gold; **14** valida a gold contra as referências oficiais.

Para baixar de novo mesmo o que já existe, acrescente `--forcar`. Exemplo, para atualizar a
base preliminar do SINAN, que o DATASUS revisa com o tempo:

```powershell
python pipeline\executar_pipeline.py --passos 01 05 --forcar
```

Se algum passo falhar, o executor para e avisa qual foi. Corrija (normalmente é queda de
internet) e continue **a partir dele**, por exemplo:

```powershell
python pipeline\executar_pipeline.py --passos 03 04 15 16 05 06 07 08 17 18 09 10 11 12 13 19 20 14
```

Todos os passos de bronze retomam de onde pararam; o 03 continua até no meio de um download.

### Opção B: só reprocessar o que já foi baixado (sem internet, minutos)

Refaz a silver e toda a gold a partir da bronze que já está no disco:

```powershell
python pipeline\executar_pipeline.py --camada silver gold
```

Os passos pesados (07, 09, 13 e 19) usam o duckdb, que trabalha em partes e grava no disco o
que não cabe na memória: rodam com ~3 GB de RAM (`SARAMPO_DUCKDB_MEMORIA`, padrão `3GB`) e
precisam de uns 30 GB livres em disco durante o 07. Tempo, num notebook com 6 GB para o WSL:
07 ~40 min, 09 ~10 min, 17 ~10 min. Se o 07 for interrompido depois de gravar as partes,
`python pipeline/07_silver_sipni_doses.py --retomar` continua de onde parou.
O 08 e o 12 só funcionam depois de o 04 ter rodado pelo menos uma vez.

### Retrato da base completa de um mês (notebooks 02 e 03)

O passo 10 precisa do retrato de pelo menos um mês com todas as vacinas, que o 03 grava em
`data\bronze\sipni_doses\_perfil_bruto\` enquanto filtra. Meses baixados antes dessa função
não têm retrato. Para gerar o de jan/2026 (baixa o mês de novo, ~1,9 GB, uns 10 minutos):

```powershell
python pipeline\03_bronze_sipni_doses.py --meses 2026-01
python pipeline\executar_pipeline.py --passos 07 09 10
```

O CSV filtrado de sarampo desse mês é regravado igual; por isso vale refazer o 07 e o 09 depois.

### Série nominal: desde 2020

O 03 baixa de jan/2020 em diante (o DATASUS publica desde então): 81 meses até set/2026,
de 0,1 a 3 GB filtrados cada (~46 GB na bronze). Para baixar só a partir de outro ano (ex.:
para testar), use `SARAMPO_ANO_INICIAL_SIPNI_DOSES=2025`; os anos que faltarem aparecem
como lacuna na `gold_serie_fontes`.

### Rodar um passo isolado

```powershell
python pipeline\03_bronze_sipni_doses.py
python pipeline\executar_pipeline.py --camada silver gold
```

## 7. Conferir as saídas

Ao fim de cada camada, o executor grava `data/<camada>/_manifesto.json`: data de corte e
demais parâmetros, commit do git (e se havia alteração não commitada no `pipeline/`), versões
do Python e dos pacotes, e cada arquivo com tamanho, sha256 e, para parquet, linhas e schema.
Duas execuções com os mesmos `arquivos` no manifesto geraram exatamente os mesmos dados.
Para regerar só o manifesto: `python pipeline/executar_pipeline.py --manifesto gold`.

Status de cada mês do SI-PNI (deve ser `concluido` ou `nao_publicado`, nunca `falhou`):

```powershell
python -c "import json; m=json.load(open('data/bronze/sipni_doses/_auditoria/manifesto.json', encoding='utf-8')); [print(k, v['status'], v.get('linhas_sarampo','')) for k, v in sorted(m.items())]"
```

Funil da silver (linhas lidas, diluentes e duplicadas removidas, linhas finais por mês):

```powershell
Get-Content data\silver\sipni_doses\_auditoria\processamento_resumo.json
```

Tabelas gold geradas (cada uma em .parquet e .csv): 23 em `vacinacao`, 2 em
`sipni_todas_vacinas`, 2 em `sinan`, os 4 arquivos de `ibge` e 6 em `sipni_historico`.
A `gold_serie_fontes` diz, ano a ano, de onde vem o dado e se ele está completo.

A validação (passo 14) imprime um resumo por status e as maiores divergências contra a
tabela oficial do MS; o detalhe fica em `data/gold/validacao/gold_validacao_referencias.csv`.
Antes de publicar, rode com `SARAMPO_VALIDACAO_ESTRITA=1`: o passo falha se houver
divergência sem justificativa em `data/referencia/divergencias_conhecidas.csv`.

```powershell
Get-ChildItem -Recurse data\gold
```

Log completo do download: `data\bronze\sipni_doses\_auditoria\extract_recentes.log`.

## 8. Atualizar os notebooks

```powershell
jupyter lab
```

Abra os notebooks em `notebooks/` e rode **Run All**. Todos (01 a 09) leem só `data/gold/`,
então refletem os dados que acabaram de ser gerados e rodam em qualquer computador que tenha
essa pasta (por exemplo, quem clonou o repositório), sem precisar da bronze nem da silver.

## 9. Guardar no git

A bronze e a silver não vão para o git (são grandes e recriáveis). A gold vai, em `.parquet`
(~10 MB), junto com os arquivos do IBGE; os `.csv` da gold ficam só no computador.

```powershell
git add -A
git commit -m "Atualiza pipeline e dados"
```

## 10. Publicar e recuperar camadas no Azure

Cada camada fica num container do storage `sarampo` (`bronze`, `silver`, `gold`), uma pasta
por versão (a data de corte), cada arquivo comprimido com zstd e o `_manifesto.json` ao lado:

```
gold/versoes.json                         {"ultima": "2026-11-08", "versoes": ["2026-11-08"]}
gold/2026-11-08/_manifesto.json
gold/2026-11-08/sinan/gold_sinan_notificacoes.parquet.zst
```

`ultima` é a versão publicada por último, a recomendada (não necessariamente a de data mais
alta). Hoje há uma versão só, `2026-11-08`, a reconstrução completa das três camadas.

**Recuperar (sem credencial).** Cada arquivo é conferido pelo sha256 do manifesto:

```bash
python pipeline/baixar_azure.py --listar gold bronze           # versões publicadas
python pipeline/baixar_azure.py gold                           # só a gold, versão mais recente
python pipeline/baixar_azure.py bronze --versao 2026-11-08     # a bronze inteira dessa versão
python pipeline/executar_pipeline.py --camada silver gold --origem azure --versao 2026-11-08
                                       # baixa a bronze dessa versão e refaz silver e gold
```

Enquanto os containers não tiverem acesso público de leitura, defina antes
`SARAMPO_AZURE_SAS_LEITURA` com um token SAS de leitura (o trecho depois do `?`).

**Publicar (com credencial de escrita).** Só o `publicar_azure.py` escreve no storage. Ele
regera o manifesto, envia a camada e atualiza o `versoes.json`; uma versão publicada não é
sobrescrita sem `--substituir`. Os `.dbf` (derivados do `.dbc`) e a junção `_completo` não
são publicados.

```bash
export SARAMPO_AZURE_SAS='sv=...&sig=...'     # token de escrita: nunca em arquivo do projeto
export SARAMPO_DATA_CORTE=2026-11-08          # a mesma data da execução que gerou os dados
python pipeline/publicar_azure.py bronze silver gold
# opcional: anotar uma versão antiga no versoes.json (campo "notas")
python pipeline/publicar_azure.py gold --nota 2026-11-01 "substituída por 2026-11-08"
```

Para conferir que uma reprodução bate com a versão publicada, gere numa pasta limpa e
compare os manifestos (`comum.manifesto.comparar`):

```bash
SARAMPO_DADOS_DIR=/tmp/reproducao python pipeline/executar_pipeline.py --camada silver gold --origem azure --versao 2026-11-08
```

## 11. Baixar tudo sem acompanhar (durante a noite)

`pipeline/utilitarios/baixar_tudo.py` baixa todas as fontes da bronze, na série completa:
SINAN, população (DATASUS), SINASC, SI-PNI histórico e IBGE pelo FTP, e o SI-PNI nominal de
2020 em diante pelo S3, em duas filas. Repete o que falhar (todos os passos retomam de onde
pararam), para se o espaço livre ficar abaixo de 40 GB, impede o Windows de dormir enquanto
roda e grava os logs em `data/bronze/_download/`. Os `.dbf` do DPNI e os `.dbc` do SINASC só
são baixados; a conversão fica para depois, porque usa muita memória.

Antes de dormir:

1. Notebook **na tomada**, e a tampa sem suspender (Configurações > Energia > "Ao fechar a
   tampa": Não fazer nada) ou simplesmente aberta. O script já pede ao Windows para não
   dormir, mas fechar a tampa pode suspender mesmo assim.
2. Conferir o plano e o espaço (não baixa nada):
   ```bash
   cd ~/projetos/analise-sarampo && source .venv/bin/activate
   python pipeline/utilitarios/baixar_tudo.py --verificar
   ```
3. Disparar e deixar a janela do terminal **aberta** (no WSL, fechar todas as janelas pode
   desligar o Linux):
   ```bash
   nohup python pipeline/utilitarios/baixar_tudo.py > data/bronze/_download_nohup.log 2>&1 &
   ```

De manhã: `cat data/bronze/_download/RESUMO.txt` (ou `STATUS.txt`, se ainda estiver rodando).
Se algo ficou `FALHOU` ou `interrompido`, rode o mesmo comando de novo: ele continua de onde
parou. Os meses do SI-PNI ficam em `data/bronze/sipni_doses/_auditoria/manifesto_*.json`
(`concluido` ou `nao_publicado`; `falhou` precisa de nova execução).

## Problemas comuns

| Sintoma | O que fazer |
|---|---|
| `ModuleNotFoundError: pandas` (ou outra lib) | o venv não está ativo: volte ao passo 2 |
| `getaddrinfo failed` / `URLError` no 03 | queda de internet: rode o 03 de novo, ele continua de onde parou |
| Passo 03 termina com erro | veja quais meses estão `falhou` no manifesto (passo 7) e rode o 03 de novo |
| `MemoryError` ou `Out of Memory Error` (duckdb) | feche outros programas ou reduza `SARAMPO_DUCKDB_MEMORIA` (ex.: `2GB`); o duckdb passa a usar mais o disco |
| `FileNotFoundError` no 08 ou no 12 | rode antes o 04 (`--passos 04 08 12`) |
| `Nenhum imunobiologicos_*.csv` no 10 | gere o retrato de um mês: `python pipeline\03_bronze_sipni_doses.py --meses 2026-01` |
| `A silver não tem descricao_vacina` no 09 | a silver é anterior às colunas novas: rode o 07 de novo |
