"""Passo 04 (bronze) - Malhas territoriais, lista de UFs e população por município (IBGE).

Fonte: APIs públicas do IBGE.
    - Malhas GeoJSON do Brasil por UF e por município (qualidade mínima, suficiente para
      mapas em escala nacional).
    - Lista de UFs (código, sigla, nome, região).
    - SIDRA, tabela 6579: população residente estimada por município, último ano disponível.

Grava as respostas como vieram (descomprimindo o gzip quando a API manda comprimido).
A conversão da população para CSV fica no passo 08. Arquivos que já existem são pulados
(--forcar baixa tudo de novo, por exemplo quando sair uma nova estimativa de população).

Saída: data/bronze/ibge/{uf.json, municipios.json, uf_meta.json, populacao_sidra.json}
Uso:   python pipeline/04_bronze_ibge.py [--forcar]
"""

import gzip
import os
import urllib.request
from pathlib import Path

import config

MALHAS = "https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR?intrarregiao={nivel}&formato=application/vnd.geo%2Bjson&qualidade=minima"
ESTADOS = "https://servicodados.ibge.gov.br/api/v1/localidades/estados"
# Tabela 6579 (SIDRA): população residente estimada por município, último ano disponível.
POPULACAO = "https://apisidra.ibge.gov.br/values/t/6579/n6/all/v/9324/p/last"


def baixar(url: str, destino: Path) -> None:
    if not config.FORCAR_DOWNLOAD and destino.exists() and destino.stat().st_size > 0:
        print(f"Já existe, pulando: {destino.name}")
        return
    print(f"Baixando {url}")
    with urllib.request.urlopen(url, timeout=120) as resp:
        conteudo = resp.read()
    if conteudo[:2] == bytes([0x1F, 0x8B]):  # algumas respostas do IBGE vêm comprimidas (gzip)
        conteudo = gzip.decompress(conteudo)
    tmp = destino.with_name(destino.name + ".tmp")
    tmp.write_bytes(conteudo)
    os.replace(tmp, destino)  # só ganha o nome final se o download terminou


def main() -> None:
    destino = config.BRONZE_IBGE
    destino.mkdir(parents=True, exist_ok=True)
    baixar(MALHAS.format(nivel="UF"), destino / "uf.json")
    baixar(MALHAS.format(nivel="municipio"), destino / "municipios.json")
    baixar(ESTADOS, destino / "uf_meta.json")
    baixar(POPULACAO, destino / "populacao_sidra.json")


if __name__ == "__main__":
    main()
