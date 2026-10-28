"""Passo 05 (silver) - Exames de sarampo/rubéola do SINAN com colunas legíveis, 2007-2026.

Entrada: data/bronze/sinan_sarampo/sinan_sarampo_exames_{AAAA}.csv  (passo 01)

Aplica o de-para de colunas (comum.dicionarios.COLUNAS_SINAN) em cada ano e junta a série
histórica num arquivo só. Os valores são mantidos como vieram do .dbf (lidos como texto),
para não perder zeros à esquerda de códigos de município, por exemplo.

Saída: data/silver/sinan_sarampo/sinan_sarampo_exames_{AAAA}.csv       (um por ano)
       data/silver/sinan_sarampo/sinan_sarampo_exames_2007_2026.csv   (série combinada)
Uso:   python pipeline/05_silver_sinan_sarampo.py
"""

import pandas as pd

import config
from comum.datasus import ler_csv_bronze, renomear_colunas
from comum.dicionarios import COLUNAS_SINAN

NOME_BASE_COMBINADO = "sinan_sarampo_exames_2007_2026"


def main() -> None:
    config.SILVER_SINAN.mkdir(parents=True, exist_ok=True)
    dataframes = []
    for ano in config.ANOS_SINAN:
        nome = f"sinan_sarampo_exames_{config.ano_4_digitos(ano)}.csv"
        df = renomear_colunas(ler_csv_bronze(config.BRONZE_SINAN / nome), COLUNAS_SINAN)
        df.to_csv(config.SILVER_SINAN / nome, index=False, encoding="utf-8")
        print(f"{nome}: {len(df)} registros")
        dataframes.append(df)

    combinado = pd.concat(dataframes, ignore_index=True)
    arquivo_combinado = config.SILVER_SINAN / f"{NOME_BASE_COMBINADO}.csv"
    combinado.to_csv(arquivo_combinado, index=False, encoding="utf-8")
    print(f"Série histórica combinada gerada: {arquivo_combinado} ({len(combinado)} registros)")


if __name__ == "__main__":
    main()
