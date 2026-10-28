"""Filtra o CSV bruto de vacinação (SI-PNI/RNDS) já baixado manualmente para um mês,
mantendo só as doses de sarampo, e aplica o de-para de colunas do SI-PNI.

Usado quando o .csv do mês já está em data/vacinacao/raw/ (baixado fora do fluxo
automático de extract_recentes.py, ex.: vacinacao_jan_2026.csv).
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from datasus_lib import renomear_colunas

from extract_recentes import COLUMN_MAP_SIPNI, filtro_vacinas_sarampo

RAW_DIR = Path(__file__).parent / "raw"
PROCESSED_DIR = Path(__file__).parent / "processed"

TAMANHO_CHUNK = 200_000


def filtrar_arquivo(nome_arquivo_raw: str, nome_base_saida: str) -> pd.DataFrame:
    arquivo_raw = RAW_DIR / nome_arquivo_raw
    arquivo_saida = PROCESSED_DIR / f"{nome_base_saida}.csv"

    print(f"Filtrando {arquivo_raw}...")
    partes = [
        chunk[filtro_vacinas_sarampo(chunk)]
        for chunk in pd.read_csv(
            arquivo_raw,
            sep=";",
            encoding="latin-1",
            dtype=str,
            chunksize=TAMANHO_CHUNK,
            on_bad_lines="skip",
        )
    ]
    df_raw = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
    df = renomear_colunas(df_raw, COLUMN_MAP_SIPNI)
    df.to_csv(arquivo_saida, index=False, encoding="utf-8")

    print(f"Processo finalizado! Arquivo gerado: {arquivo_saida} ({len(df)} registros)")
    return df


def main() -> None:
    filtrar_arquivo("vacinacao_jan_2026.csv", "vacinacao_sarampo_2026_jan")


if __name__ == "__main__":
    main()
