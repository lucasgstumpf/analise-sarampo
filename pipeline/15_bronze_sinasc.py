"""Passo 15 (bronze) - Nascidos vivos (SINASC), 1994 até o ano da data de corte.

Fonte: FTP do DATASUS, declarações de nascido vivo por local de residência (DNRES):
    dissemin/publicos/SINASC/1994_1995/Dados/DNRES/DNBR{AAAA}.dbc   1994-1995 (Brasil)
    dissemin/publicos/SINASC/1996_/Dados/DNRES/DNBR{AAAA}.dbc       1996 em diante (Brasil)
    dissemin/publicos/SINASC/PRELIM/DNRES/DN{UF}{AAAA}.dbc          anos preliminares (por UF)
Para cada ano usa o arquivo nacional definitivo, se existir; se não, os preliminares por UF.
O que existe é descoberto listando os diretórios (anos ainda não publicados são só avisados).

É o denominador da cobertura vacinal a partir de 2020 (o SI-PNI agregado trazia a população
alvo até 2019): crianças de 1 ano num ano = nascidos vivos do ano anterior, por município.

Por enquanto só baixa o .dbc original. A conversão para .csv (o DNBR de um ano tem ~3 milhões
de linhas e 60 colunas) fica para quando a leitura dos .dbf for feita em partes, sem carregar
o arquivo inteiro na memória.

Saída: data/bronze/sinasc/sinasc_nascidos_vivos_{AAAA}.dbc            (definitivo, Brasil)
       data/bronze/sinasc/sinasc_nascidos_vivos_{AAAA}_prelim_{UF}.dbc (preliminar, por UF)
       e, ao lado de cada um, <arquivo>.origem.json (URL, data, tamanho e sha256)
Uso:   python pipeline/15_bronze_sinasc.py [--forcar]
"""

import config
from comum.datasus import baixar_arquivo, construir_url, ja_existe, listar_ftp

DIRETORIOS_DEFINITIVOS = [
    "dissemin/publicos/SINASC/1994_1995/Dados/DNRES",
    "dissemin/publicos/SINASC/1996_/Dados/DNRES",
]
DIRETORIO_PRELIMINAR = "dissemin/publicos/SINASC/PRELIM/DNRES"
UFS = ["AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB",
       "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO"]


def main() -> None:
    destino = config.BRONZE_SINASC
    destino.mkdir(parents=True, exist_ok=True)
    # nome em maiúsculas -> (diretório, nome como está no FTP): o FTP mistura .dbc e .DBC
    definitivos = {nome.upper(): (d, nome) for d in DIRETORIOS_DEFINITIVOS for nome in listar_ftp(d)}
    preliminares = {nome.upper(): nome for nome in listar_ftp(DIRETORIO_PRELIMINAR)}

    faltando = []
    for ano in config.ANOS_SINASC:
        if f"DNBR{ano}.DBC" in definitivos:
            d, nome = definitivos[f"DNBR{ano}.DBC"]
            alvos = [(f"{d}/{nome}", destino / f"sinasc_nascidos_vivos_{ano}.dbc")]
        else:
            alvos = [(f"{DIRETORIO_PRELIMINAR}/{preliminares[f'DN{uf}{ano}.DBC']}",
                      destino / f"sinasc_nascidos_vivos_{ano}_prelim_{uf}.dbc")
                     for uf in UFS if f"DN{uf}{ano}.DBC" in preliminares]
            if len(alvos) < len(UFS):
                faltando.append(f"{ano} ({len(alvos)} de {len(UFS)} UFs no preliminar)")
        for caminho, arquivo in alvos:
            if ja_existe(arquivo, config.FORCAR_DOWNLOAD):
                print(f"Já existe, pulando: {arquivo.name}")
                continue
            baixar_arquivo(construir_url(caminho), arquivo)
    if faltando:
        print("Ainda não publicados por completo: " + "; ".join(faltando))


if __name__ == "__main__":
    main()
