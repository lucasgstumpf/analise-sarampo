"""Utilitário - mostra as primeiras linhas de um CSV bruto do SI-PNI (separador ";", latin-1).

Uso: python pipeline/utilitarios/ver_primeiras_linhas.py [caminho_do_csv] [n_linhas]
     Sem argumentos, abre data/bronze/sipni_manual/vacinacao_jan_2026.csv e mostra 15 linhas.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config


def main() -> None:
    arquivo_csv = Path(sys.argv[1]) if len(sys.argv) > 1 else config.BRONZE_SIPNI_MANUAL / "vacinacao_jan_2026.csv"
    n_linhas = int(sys.argv[2]) if len(sys.argv) > 2 else 15
    # nrows evita carregar o arquivo inteiro (as bases mensais têm milhões de linhas).
    df = pd.read_csv(arquivo_csv, sep=";", encoding="latin1", nrows=n_linhas)
    print(df.head(n_linhas))


if __name__ == "__main__":
    main()
