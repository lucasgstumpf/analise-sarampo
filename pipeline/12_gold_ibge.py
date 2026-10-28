"""Passo 12 (gold) - Referências geográficas do IBGE para os mapas (notebook 09).

Entrada: data/bronze/ibge/{uf.json, municipios.json, uf_meta.json}  (passo 04)
         data/silver/ibge/populacao_municipios.csv                  (passo 08)

Copia para a gold o que os mapas precisam, para que a pasta gold seja suficiente para rodar
todos os notebooks. As malhas e a lista de UFs não precisam de tratamento; a população já
vem tratada da silver (código de município com 6 dígitos).

Saída: data/gold/ibge/{uf.json, municipios.json, uf_meta.json, populacao_municipios.csv}
Uso:   python pipeline/12_gold_ibge.py
"""

import shutil

import config

GOLD_DIR = config.GOLD / "ibge"
ARQUIVOS = [
    config.BRONZE_IBGE / "uf.json",
    config.BRONZE_IBGE / "municipios.json",
    config.BRONZE_IBGE / "uf_meta.json",
    config.SILVER_IBGE / "populacao_municipios.csv",
]


def main() -> None:
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    for origem in ARQUIVOS:
        shutil.copyfile(origem, GOLD_DIR / origem.name)
        print(f"{origem.name}: {origem.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
