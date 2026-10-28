# Passo a passo: rodar o pipeline completo

Guia para atualizar todos os dados do projeto no computador (Windows, PowerShell), do
ambiente Python até conferir as saídas. Detalhes de cada passo estão no [README](README.md).

## 1. Abrir o terminal na pasta do projeto

```powershell
cd C:\Users\lucas\Documents\00.Gaspar\Code\analise-sarampo
```

Os comandos abaixo partem desta pasta (a raiz do projeto).

## 2. Ativar o ambiente virtual

O projeto já tem um `.venv` (Python 3.15).

```powershell
.\.venv\Scripts\Activate.ps1
```

O prompt passa a começar com `(.venv)`. Se o PowerShell bloquear o script, rode uma vez
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` e tente de novo.

## 3. Instalar as dependências

O venv hoje tem só pandas, numpy, pyarrow e dbfread, que bastam para o pipeline. Para os
notebooks faltam o Jupyter e as bibliotecas de gráficos:

```powershell
pip install pandas numpy pyarrow dbfread          # pipeline (já instalados; garante as versões)
pip install jupyter matplotlib seaborn nbformat   # notebooks
```

O `pyreaddbc` é opcional: no Python 3.15 ele costuma não instalar (precisa de compilador C),
e o pipeline usa automaticamente a conversão em Python puro (`comum/dbc_puro.py`). Por isso
não use `pip install -r requirements.txt` direto: ele para no `pyreaddbc`.

## 4. Conferir que o pipeline está visível

```powershell
python pipeline\executar_pipeline.py --listar
```

Devem aparecer os passos 01 a 12.

## 5. Preparar a pasta temporária dos downloads grandes

O passo 03 baixa cada mês do SI-PNI (1-2 GB, um mês por vez) para `D:\analise-sarampo\staging`
e apaga o `.zip` depois de filtrar. Deixe uns 3 GB livres no D:. Para usar outra pasta só
nesta sessão do terminal:

```powershell
$env:SARAMPO_STAGING_DIR = "E:\staging-sarampo"
```

## 6. Rodar

### Opção A: atualização completa (recomendada para a gestão mensal)

```powershell
python pipeline\executar_pipeline.py
```

Roda 01 -> 12 em ordem. Os passos de bronze (01-04) **pulam o que já está em disco**, então
rodar de novo só baixa o que falta:
- **01** e **02** pulam cada ano cujo `.csv` já existe (SINAN 2007-2026 e SI-PNI histórico
  1994-2019 já estão baixados neste computador);
- **03** pula os meses já concluídos (jan/2025 a mai/2026) e tenta os seguintes; mês que
  ainda não foi publicado fica como `nao_publicado` e não é erro;
- **04** pula os arquivos do IBGE que já existem; **05-08** limpam; **09-12** geram as tabelas gold.

Para baixar de novo mesmo o que já existe, acrescente `--forcar`. Exemplo, para atualizar a
base preliminar do SINAN, que o DATASUS revisa com o tempo:

```powershell
python pipeline\executar_pipeline.py --passos 01 05 --forcar
```

Se algum passo falhar, o executor para e avisa qual foi. Corrija (normalmente é queda de
internet) e continue **a partir dele**, por exemplo:

```powershell
python pipeline\executar_pipeline.py --passos 03 04 05 06 07 08 09 10 11 12
```

Todos os passos de bronze retomam de onde pararam; o 03 continua até no meio de um download.

### Opção B: só reprocessar o que já foi baixado (sem internet, minutos)

Refaz a silver e toda a gold a partir da bronze que já está no disco:

```powershell
python pipeline\executar_pipeline.py --camada silver gold
```

O 07 usa cerca de 5 GB de RAM e o 09 até ~8 GB. O 08 e o 12 só funcionam depois de o 04 ter
rodado pelo menos uma vez.

### Retrato da base completa de um mês (notebooks 02 e 03)

O passo 10 precisa do retrato de pelo menos um mês com todas as vacinas, que o 03 grava em
`data\bronze\sipni_doses\_perfil_bruto\` enquanto filtra. Meses baixados antes dessa função
não têm retrato. Para gerar o de jan/2026 (baixa o mês de novo, ~1,9 GB, uns 10 minutos):

```powershell
python pipeline\03_bronze_sipni_doses.py --meses 2026-01
python pipeline\executar_pipeline.py --passos 07 09 10
```

O CSV filtrado de sarampo desse mês é regravado igual; por isso vale refazer o 07 e o 09 depois.

### Rodar um passo isolado

```powershell
python pipeline\03_bronze_sipni_doses.py
python pipeline\executar_pipeline.py --camada silver gold
```

## 7. Conferir as saídas

Status de cada mês do SI-PNI (deve ser `concluido` ou `nao_publicado`, nunca `falhou`):

```powershell
python -c "import json; m=json.load(open('data/bronze/sipni_doses/_auditoria/manifesto.json', encoding='utf-8')); [print(k, v['status'], v.get('linhas_sarampo','')) for k, v in sorted(m.items())]"
```

Funil da silver (linhas lidas, diluentes e duplicadas removidas, linhas finais por mês):

```powershell
Get-Content data\silver\sipni_doses\_auditoria\processamento_resumo.json
```

Tabelas gold geradas (cada uma em .parquet e .csv): 23 em `vacinacao`, 2 em
`sipni_todas_vacinas`, 2 em `sinan` e os 4 arquivos de `ibge`.

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

## Problemas comuns

| Sintoma | O que fazer |
|---|---|
| `ModuleNotFoundError: pandas` (ou outra lib) | o venv não está ativo: volte ao passo 2 |
| `getaddrinfo failed` / `URLError` no 03 | queda de internet: rode o 03 de novo, ele continua de onde parou |
| Passo 03 termina com erro | veja quais meses estão `falhou` no manifesto (passo 7) e rode o 03 de novo |
| `MemoryError` no 07 | feche outros programas (precisa de ~5 GB livres de RAM) |
| `FileNotFoundError` no 08 ou no 12 | rode antes o 04 (`--passos 04 08 12`) |
| `Nenhum imunobiologicos_*.csv` no 10 | gere o retrato de um mês: `python pipeline\03_bronze_sipni_doses.py --meses 2026-01` |
| `A silver não tem descricao_vacina` no 09 | a silver é anterior às colunas novas: rode o 07 de novo |
