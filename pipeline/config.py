"""Configuração central do pipeline: onde fica cada camada e o que coletar.

Todos os scripts numerados importam os caminhos daqui, então mudar uma pasta é mudar uma
linha só. A organização segue a arquitetura medalhão:

    data/bronze/  dado como veio da fonte (só baixado, convertido de formato e, no caso das
                  bases nominais do SI-PNI, filtrado para sarampo)
    data/silver/  dado limpo: colunas com nomes legíveis, tipos corrigidos, séries juntadas
    data/gold/    tabelas agregadas e pequenas, prontas para os notebooks e para BI

Dentro de cada camada há uma pasta por fonte (sinan_sarampo, sipni_historico, sipni_doses,
ibge), para que fique claro de onde veio cada arquivo.
"""

import os
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
# SARAMPO_DADOS_DIR troca a pasta de dados inteira (ex.: para reproduzir numa pasta limpa e
# comparar os manifestos com os de data/).
DADOS = Path(os.environ.get("SARAMPO_DADOS_DIR") or RAIZ / "data")

BRONZE = DADOS / "bronze"
SILVER = DADOS / "silver"
GOLD = DADOS / "gold"

# ---------------------------------------------------------------- bronze
BRONZE_SINAN = BRONZE / "sinan_sarampo"          # .dbc, .dbf e .csv (colunas originais) por ano
BRONZE_SIPNI_HISTORICO = BRONZE / "sipni_historico"  # .dbf e .csv de CPNI/DPNI 1994-2019
BRONZE_SIPNI_DOSES = BRONZE / "sipni_doses"      # CSVs mensais (2025+) já filtrados para sarampo
BRONZE_SIPNI_DOSES_AUDITORIA = BRONZE_SIPNI_DOSES / "_auditoria"  # manifesto.json + log
BRONZE_SIPNI_PERFIL_BRUTO = BRONZE_SIPNI_DOSES / "_perfil_bruto"  # todas as vacinas: contagem e perfil das colunas
BRONZE_SIPNI_MANUAL = BRONZE / "sipni_manual"    # bases baixadas à mão (ex.: jan/2026, notebooks 02-04)
BRONZE_IBGE = BRONZE / "ibge"                    # malhas GeoJSON, lista de UFs e população (SIDRA)
BRONZE_SINASC = BRONZE / "sinasc"                # nascidos vivos (.dbc), denominador da cobertura vacinal
BRONZE_POPULACAO = BRONZE / "populacao"          # estimativas de população do DATASUS (IBGE/POP e POPSVS)

# ---------------------------------------------------------------- silver
SILVER_SINAN = SILVER / "sinan_sarampo"
SILVER_SIPNI_HISTORICO = SILVER / "sipni_historico"
SILVER_SIPNI_DOSES = SILVER / "sipni_doses"
SILVER_SIPNI_DOSES_AUDITORIA = SILVER_SIPNI_DOSES / "_auditoria"
SILVER_IBGE = SILVER / "ibge"
SILVER_SINASC = SILVER / "sinasc"                # nascidos vivos por município de residência x mês x sexo
SILVER_POPULACAO = SILVER / "populacao"          # população por município x ano x sexo x idade (POP e POPSVS)

# ---------------------------------------------------------------- gold
GOLD_VACINACAO = GOLD / "vacinacao"
GOLD_DEMOGRAFIA = GOLD / "demografia"            # nascidos vivos, população e cobertura vacinal 2020+

# ---------------------------------------------------------------- staging
# Os .zip mensais do SI-PNI têm vários GB e ficam aqui só até serem filtrados (o 03 apaga
# cada um em seguida). Para usar outro disco, defina SARAMPO_STAGING_DIR (ex.: D:\staging).
STAGING_DIR = Path(os.environ.get("SARAMPO_STAGING_DIR") or BRONZE / "_staging")

# ---------------------------------------------------------------- períodos
# ---------------------------------------------------------------- data de corte
# Tudo o que dependeria de "hoje" (último mês a baixar, ano corrente parcial) depende desta
# data, que fica registrada no manifesto de cada camada. Para reproduzir uma execução, use a
# mesma data: SARAMPO_DATA_CORTE=AAAA-MM-DD. Sem a variável, vale a data de hoje (o executor
# fixa uma só data para todos os passos da execução).
DATA_CORTE = date.fromisoformat(os.environ.get("SARAMPO_DATA_CORTE") or date.today().isoformat())
DATA_CORTE_EXPLICITA = bool(os.environ.get("SARAMPO_DATA_CORTE"))
_HOJE = DATA_CORTE

# SINAN (exames de sarampo/rubéola, base preliminar): 2007 a 2026, com 2 dígitos.
ANOS_SINAN = [f"{a:02d}" for a in range(7, 27)]

# SINASC (nascidos vivos): de 1994 até o ano da data de corte (os mais recentes são preliminares).
ANOS_SINASC = list(range(1994, DATA_CORTE.year + 1))

# SI-PNI histórico (FTP): 1994 a 2019, com 2 dígitos.
ANOS_SIPNI_HISTORICO = [f"{a:02d}" for a in range(94, 100)] + [f"{a:02d}" for a in range(0, 20)]

# SI-PNI nominal (S3): de jan/ANO_INICIAL até o mês corrente. Meses ainda não publicados ficam
# registrados como "nao_publicado" no manifesto e são tentados de novo na próxima execução.
# O DATASUS publica desde jan/2020; o padrão é 2025 porque 2020-2024 somam ~120-150 GB de
# download. Para trazer a série inteira: SARAMPO_ANO_INICIAL_SIPNI_DOSES=2020.
ANO_INICIAL_SIPNI_DOSES = int(os.environ.get("SARAMPO_ANO_INICIAL_SIPNI_DOSES", "2020"))
PERIODO_SIPNI_DOSES = [
    (ano, mes) for ano in range(ANO_INICIAL_SIPNI_DOSES, _HOJE.year + 1) for mes in range(1, 13)
    if (ano, mes) <= (_HOJE.year, _HOJE.month)
]
ANO_FINAL_SIPNI_DOSES = _HOJE.year

MESES_ABREV = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

# IBGE/SIDRA tabela 6579 (população estimada por município): ano fixo, e não "o último",
# para que baixar de novo traga o mesmo dado.
# Limite de memória do duckdb (passos 07, 09 e 13); acima disso ele usa o disco.
DUCKDB_MEMORIA = os.environ.get("SARAMPO_DUCKDB_MEMORIA") or "3GB"
# Onde o duckdb grava o que não cabe na memória (precisa de alguns GB livres em disco).
DUCKDB_TMP = Path(os.environ.get("SARAMPO_DUCKDB_TMP") or DADOS / "_duckdb_tmp")
ANO_POPULACAO_IBGE = int(os.environ.get("SARAMPO_ANO_POPULACAO_IBGE", "2026"))

# Leitura dos CSVs grandes em pedaços (linhas por chunk).
TAMANHO_CHUNK = 200_000

# ---------------------------------------------------------------- downloads já feitos
# Os passos de bronze pulam o que já existe em disco, para que rodar de novo retome de onde
# parou. Para baixar tudo de novo (ex.: atualizar as bases preliminares do SINAN), passe
# --forcar ao script ou ao executor, ou defina SARAMPO_FORCAR_DOWNLOAD=1.
FORCAR_DOWNLOAD = "--forcar" in sys.argv or os.environ.get("SARAMPO_FORCAR_DOWNLOAD") == "1"


def ano_4_digitos(ano: str) -> str:
    """'07' -> '2007', '94' -> '1994' (anos de 2 dígitos usados nos nomes do DATASUS)."""
    return f"20{ano}" if ano < "50" else f"19{ano}"
