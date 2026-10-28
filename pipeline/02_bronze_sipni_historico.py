"""Passo 02 (bronze) - SI-PNI histórico (agregado), 1994-2019.

Fonte: FTP do DATASUS, um .DBF por ano para cada base:
    CPNI - cobertura vacinal anual por município e imunobiológico
           dissemin/publicos/PNI/DADOS/CPNIBR{AA}.DBF
    DPNI - doses aplicadas por mês, município, faixa etária, imunobiológico e dose
           dissemin/publicos/PNI/DADOS/DPNIBR{AA}.DBF

Baixa o .dbf e grava o .csv com as colunas originais. A limpeza e a junção da série
ficam no passo 06. Anos cujo .csv já existe são pulados (--forcar baixa tudo de novo).

Saída: data/bronze/sipni_historico/sipni_cobertura_vacinal_{AAAA}.{dbf,csv}
       data/bronze/sipni_historico/sipni_doses_aplicadas_agregado_{AAAA}.{dbf,csv}
Uso:   python pipeline/02_bronze_sipni_historico.py [--forcar]
"""

import config
from comum.datasus import extrair_dbf

CAMINHO_TEMPLATE_CPNI = "dissemin/publicos/PNI/DADOS/CPNIBR{ano}.DBF"
CAMINHO_TEMPLATE_DPNI = "dissemin/publicos/PNI/DADOS/DPNIBR{ano}.DBF"


def coletar(caminho_template: str, prefixo: str) -> None:
    for ano in config.ANOS_SIPNI_HISTORICO:
        nome_base = f"{prefixo}_{config.ano_4_digitos(ano)}"
        extrair_dbf(caminho_template.format(ano=ano), nome_base, config.BRONZE_SIPNI_HISTORICO, forcar=config.FORCAR_DOWNLOAD)


def main() -> None:
    coletar(CAMINHO_TEMPLATE_CPNI, "sipni_cobertura_vacinal")
    coletar(CAMINHO_TEMPLATE_DPNI, "sipni_doses_aplicadas_agregado")


if __name__ == "__main__":
    main()
