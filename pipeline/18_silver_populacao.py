"""Passo 18 (silver) - População residente por município, ano, sexo e idade (DATASUS).

Entrada: data/bronze/populacao/POP/POPBR{AA}.zip      (passo 16; IBGE/POP, 1980-2012)
         data/bronze/populacao/POPSVS/POPSBR{AA}.zip  (passo 16; estimativas SVS, 2000-2025)

As duas séries têm layouts diferentes e ficam em tabelas separadas (a gold escolhe qual usar
em cada ano). Dentro de cada zip só o .dbf é lido (o .csv e o .xml do POP repetem o mesmo
conteúdo).
    POP (IBGE/POP):   MUNIC_RES (6 dígitos), ANO, SEXO, SITUACAO (1 urbana, 2 rural, 3 total),
                      FXETARIA (AAAA = de AA a AA anos, ex. 0101 = 1 ano, 2024 = 20-24;
                      I000 = idade ignorada), POPULACAO
    POPSVS (SVS):     COD_MUN (7 dígitos), ANO, SEXO, IDADE (000 a 080, 080 = 80 anos ou mais), POP
Regras: município sempre com 6 dígitos; sexo 1 = Masculino, 2 = Feminino; no POP, idade_min e
idade_max saem da faixa (vazias na idade ignorada); a situação urbana/rural é somada.

Saída: data/silver/populacao/populacao_ibge_pop.parquet
           ano, codigo_municipio, sexo, faixa_etaria, idade_min, idade_max, populacao
       data/silver/populacao/populacao_svs.parquet
           ano, codigo_municipio, sexo, idade (80 = 80 anos ou mais), populacao
Uso:   python pipeline/18_silver_populacao.py
"""

import zipfile

import pandas as pd

import config
from comum import dbf_rapido

SEXO = {"1": "Masculino", "2": "Feminino"}


def ler_dbf_do_zip(arquivo) -> pd.DataFrame:
    with zipfile.ZipFile(arquivo) as zf:
        membro = next(i for i in zf.infolist() if i.filename.lower().endswith(".dbf"))
        dados = zf.read(membro)
    tmp = config.DUCKDB_TMP / "18" / (arquivo.stem + ".dbf")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(dados)
    try:
        df = pd.concat(dbf_rapido.iterar(tmp), ignore_index=True)
    finally:
        tmp.unlink()
    df.columns = [c.upper() for c in df.columns]
    return df


def municipio_6(serie: pd.Series) -> pd.Series:
    s = serie.astype("string").str.strip()
    return s.where(s.str.len() != 7, s.str[:6])


def serie_pop() -> pd.DataFrame:
    partes = []
    for arq in sorted((config.BRONZE_POPULACAO / "POP").glob("POPBR*.zip")):
        df = ler_dbf_do_zip(arq)
        faixa = df["FXETARIA"].astype("string").str.strip()
        valido = faixa.str.fullmatch(r"\d{4}")
        tab = pd.DataFrame({
            "ano": pd.to_numeric(df["ANO"]).astype("int16"),
            "codigo_municipio": municipio_6(df["MUNIC_RES"]),
            "sexo": df["SEXO"].astype("string").str.strip().map(SEXO).fillna("Ignorado"),
            "faixa_etaria": faixa,
            "idade_min": pd.to_numeric(faixa.str[:2].where(valido)).astype("Int16"),
            "idade_max": pd.to_numeric(faixa.str[2:].where(valido)).astype("Int16"),
            "populacao": pd.to_numeric(df["POPULACAO"]).astype("int64"),
        })
        partes.append(tab.groupby(["ano", "codigo_municipio", "sexo", "faixa_etaria", "idade_min", "idade_max"],
                                  dropna=False, as_index=False)["populacao"].sum())
        print(arq.name, len(df), int(tab["populacao"].sum()), flush=True)
    return pd.concat(partes, ignore_index=True)


def serie_svs() -> pd.DataFrame:
    partes = []
    for arq in sorted((config.BRONZE_POPULACAO / "POPSVS").glob("POPSBR*.zip")):
        df = ler_dbf_do_zip(arq)
        tab = pd.DataFrame({
            "ano": pd.to_numeric(df["ANO"]).astype("int16"),
            "codigo_municipio": municipio_6(df["COD_MUN"]),
            "sexo": df["SEXO"].astype("string").str.strip().map(SEXO).fillna("Ignorado"),
            "idade": pd.to_numeric(df["IDADE"].astype("string").str.strip()).astype("int16"),
            "populacao": pd.to_numeric(df["POP"]).astype("int64"),
        })
        partes.append(tab.groupby(["ano", "codigo_municipio", "sexo", "idade"], as_index=False)["populacao"].sum())
        print(arq.name, len(df), int(tab["populacao"].sum()), flush=True)
    return pd.concat(partes, ignore_index=True)


def gravar(df: pd.DataFrame, nome: str) -> None:
    chaves = [c for c in df.columns if c != "populacao"]
    df = df.sort_values(chaves, na_position="last").reset_index(drop=True)
    destino = config.SILVER_POPULACAO / nome
    tmp = destino.with_suffix(".tmp")
    df.to_parquet(tmp, index=False, compression="zstd")
    tmp.replace(destino)
    print(f"{nome}: {len(df):,} linhas, anos {df['ano'].min()}-{df['ano'].max()}")


def main() -> None:
    config.SILVER_POPULACAO.mkdir(parents=True, exist_ok=True)
    gravar(serie_pop(), "populacao_ibge_pop.parquet")
    gravar(serie_svs(), "populacao_svs.parquet")


if __name__ == "__main__":
    main()
