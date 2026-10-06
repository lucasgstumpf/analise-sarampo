"""Baixa da API pública do IBGE as malhas (UF e município), a lista de UFs e a população
estimada por município, e grava populacao_municipios.csv (código IBGE de 6 dígitos)."""

import gzip
import json
import urllib.request
from pathlib import Path

import pandas as pd

DESTINO = Path(__file__).parent
MALHAS = "https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR?intrarregiao={nivel}&formato=application/vnd.geo%2Bjson&qualidade=minima"
ESTADOS = "https://servicodados.ibge.gov.br/api/v1/localidades/estados"
# Tabela 6579 (SIDRA): população residente estimada por município, último ano disponível.
POPULACAO = "https://apisidra.ibge.gov.br/values/t/6579/n6/all/v/9324/p/last"


def baixar(url: str, destino: Path) -> None:
    print(f"Baixando {url}")
    with urllib.request.urlopen(url, timeout=120) as resp:
        conteudo = resp.read()
    if conteudo[:2] == bytes([0x1F, 0x8B]):  # algumas respostas do IBGE vêm comprimidas (gzip)
        conteudo = gzip.decompress(conteudo)
    destino.write_bytes(conteudo)


def main() -> None:
    baixar(MALHAS.format(nivel="UF"), DESTINO / "uf.json")
    baixar(MALHAS.format(nivel="municipio"), DESTINO / "municipios.json")
    baixar(ESTADOS, DESTINO / "uf_meta.json")
    baixar(POPULACAO, DESTINO / "pop.json")

    linhas = json.loads((DESTINO / "pop.json").read_text(encoding="utf-8"))[1:]  # 1ª linha é o cabeçalho
    pop = pd.DataFrame({
        "codigo_municipio": [int(l["D1C"]) // 10 for l in linhas],  # 7 -> 6 dígitos (sem o dígito verificador)
        "populacao": [int(l["V"]) for l in linhas],
        "ano": [int(l["D3C"]) for l in linhas],
    })
    pop.to_csv(DESTINO / "populacao_municipios.csv", index=False)
    (DESTINO / "pop.json").unlink()
    print(f"{len(pop)} municípios, população total {pop['populacao'].sum():,} ({pop['ano'].iloc[0]})")


if __name__ == "__main__":
    main()
