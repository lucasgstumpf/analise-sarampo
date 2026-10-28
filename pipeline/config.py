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
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "data"

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

# ---------------------------------------------------------------- silver
SILVER_SINAN = SILVER / "sinan_sarampo"
SILVER_SIPNI_HISTORICO = SILVER / "sipni_historico"
SILVER_SIPNI_DOSES = SILVER / "sipni_doses"
SILVER_SIPNI_DOSES_AUDITORIA = SILVER_SIPNI_DOSES / "_auditoria"
SILVER_IBGE = SILVER / "ibge"

# ---------------------------------------------------------------- gold
GOLD_VACINACAO = GOLD / "vacinacao"

# ---------------------------------------------------------------- staging
# Os .zip mensais do SI-PNI têm vários GB: o download (temporário) vai para o HD D:, não
# para o disco do projeto. Sobrescreva com a variável de ambiente SARAMPO_STAGING_DIR.
STAGING_DIR = Path(os.environ.get("SARAMPO_STAGING_DIR", r"D:\analise-sarampo\staging"))

# ---------------------------------------------------------------- períodos
_HOJE = datetime.now()

# SINAN (exames de sarampo/rubéola, base preliminar): 2007 a 2026, com 2 dígitos.
ANOS_SINAN = [f"{a:02d}" for a in range(7, 27)]

# SI-PNI histórico (FTP): 1994 a 2019, com 2 dígitos.
ANOS_SIPNI_HISTORICO = [f"{a:02d}" for a in range(94, 100)] + [f"{a:02d}" for a in range(0, 20)]

# SI-PNI nominal (S3): de jan/2025 até o mês corrente. Meses ainda não publicados ficam
# registrados como "nao_publicado" no manifesto e são tentados de novo na próxima execução.
PERIODO_SIPNI_DOSES = [
    (ano, mes) for ano in range(2025, _HOJE.year + 1) for mes in range(1, 13)
    if (ano, mes) <= (_HOJE.year, _HOJE.month)
]
ANO_FINAL_SIPNI_DOSES = _HOJE.year

MESES_ABREV = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

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
