"""Passo 01 (bronze) - Exames de sarampo/rubéola do SINAN, 2007-2026.

Fonte: FTP do DATASUS, base preliminar do SINAN (ficha EXAN), um .dbc por ano:
    dissemin/publicos/SINAN/DADOS/PRELIM/EXANBR{AA}.dbc

Para cada ano baixa o .dbc, converte para .dbf e grava um .csv com as colunas originais.
Nada é renomeado nem filtrado aqui (isso é o passo 05). Anos cujo .csv já existe são
pulados; como a base do SINAN é preliminar e o DATASUS a atualiza, use --forcar de tempos
em tempos para baixar tudo de novo.

Saída: data/bronze/sinan_sarampo/sinan_sarampo_exames_{AAAA}.{dbc,dbf,csv}
Uso:   python pipeline/01_bronze_sinan_sarampo.py [--forcar]
"""

import config
from comum.datasus import extrair_dbc

CAMINHO_TEMPLATE = "dissemin/publicos/SINAN/DADOS/PRELIM/EXANBR{ano}.dbc"


def main() -> None:
    for ano in config.ANOS_SINAN:
        nome_base = f"sinan_sarampo_exames_{config.ano_4_digitos(ano)}"
        extrair_dbc(CAMINHO_TEMPLATE.format(ano=ano), nome_base, config.BRONZE_SINAN, forcar=config.FORCAR_DOWNLOAD)


if __name__ == "__main__":
    main()
