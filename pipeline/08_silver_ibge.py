"""Passo 08 (silver) - População estimada por município (IBGE) em formato tabular.

Entrada: data/bronze/ibge/populacao_sidra.json  (passo 04)

Converte a resposta da API do SIDRA (tabela 6579) num CSV simples. O código do município
vai de 7 para 6 dígitos (sem o dígito verificador), que é o padrão do SI-PNI e do SINAN,
para que as tabelas possam ser cruzadas direto.

As malhas (uf.json, municipios.json) e a lista de UFs (uf_meta.json) não precisam de
tratamento e são lidas pelos notebooks direto da bronze.

Saída: data/silver/ibge/populacao_municipios.csv  (codigo_municipio, populacao, ano)
Uso:   python pipeline/08_silver_ibge.py
"""

import json

import pandas as pd

import config


def main() -> None:
    origem = config.BRONZE_IBGE / "populacao_sidra.json"
    linhas = json.loads(origem.read_text(encoding="utf-8"))[1:]  # 1ª linha é o cabeçalho
    pop = pd.DataFrame({
        "codigo_municipio": [int(l["D1C"]) // 10 for l in linhas],  # 7 -> 6 dígitos (sem o dígito verificador)
        "populacao": [int(l["V"]) for l in linhas],
        "ano": [int(l["D3C"]) for l in linhas],
    })
    config.SILVER_IBGE.mkdir(parents=True, exist_ok=True)
    pop.to_csv(config.SILVER_IBGE / "populacao_municipios.csv", index=False)
    print(f"{len(pop)} municípios, população total {pop['populacao'].sum():,} ({pop['ano'].iloc[0]})")


if __name__ == "__main__":
    main()
