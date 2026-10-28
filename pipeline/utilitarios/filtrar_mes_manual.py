"""Utilitário - filtra para sarampo um CSV mensal do SI-PNI baixado à mão.

Usado quando o .csv do mês foi baixado fora do fluxo automático do passo 03 (ex.:
vacinacao_jan_2026.csv, base dos notebooks 02-04). Aplica o mesmo filtro e o mesmo de-para
de colunas do passo 03.

Entrada: data/bronze/sipni_manual/vacinacao_jan_2026.csv
Saída:   data/bronze/sipni_manual/vacinacao_sarampo_2026_jan.csv
Uso:     python pipeline/utilitarios/filtrar_mes_manual.py
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from comum.datasus import renomear_colunas
from comum.dicionarios import COLUNAS_SIPNI, filtro_vacinas_sarampo


def filtrar_arquivo(nome_arquivo_bruto: str, nome_base_saida: str) -> pd.DataFrame:
    arquivo_bruto = config.BRONZE_SIPNI_MANUAL / nome_arquivo_bruto
    arquivo_saida = config.BRONZE_SIPNI_MANUAL / f"{nome_base_saida}.csv"

    print(f"Filtrando {arquivo_bruto}...")
    partes = [
        chunk[filtro_vacinas_sarampo(chunk)]
        for chunk in pd.read_csv(
            arquivo_bruto,
            sep=";",
            encoding="latin-1",
            dtype=str,
            chunksize=config.TAMANHO_CHUNK,
            on_bad_lines="skip",
        )
    ]
    df_bruto = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
    df = renomear_colunas(df_bruto, COLUNAS_SIPNI)
    df.to_csv(arquivo_saida, index=False, encoding="utf-8")

    print(f"Processo finalizado! Arquivo gerado: {arquivo_saida} ({len(df)} registros)")
    return df


def main() -> None:
    filtrar_arquivo("vacinacao_jan_2026.csv", "vacinacao_sarampo_2026_jan")


if __name__ == "__main__":
    main()
