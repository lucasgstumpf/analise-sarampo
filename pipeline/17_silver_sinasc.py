"""Passo 17 (silver) - Nascidos vivos (SINASC) por município de residência, mês e sexo.

Entrada: data/bronze/sinasc/sinasc_nascidos_vivos_{AAAA}[_prelim_{UF}].dbc  (passo 15)

O SINASC tem uma linha por declaração de nascido vivo (~3 milhões por ano, 60 colunas). Para
a análise de sarampo só interessa a contagem de nascimentos (denominador da cobertura
vacinal), então a silver guarda a contagem por município de residência da mãe, mês de
nascimento e sexo. Cada .dbc é convertido para um .dbf temporário (comum/dbc_rapido) e lido
em blocos, só com as 3 colunas usadas (comum/dbf_rapido).

Regras:
    - ano = ano do arquivo (o SINASC organiza os arquivos pelo ano de nascimento);
    - mês = mês de DTNASC (DDMMAAAA), mesmo com o dia "00" (ignorado, comum em 1994-1996);
      mês vazio ou fora de 01-12 -> mês vazio (a linha fica);
    - município de residência (CODMUNRES) sempre com 6 dígitos (até 2005 vem com 7, com o
      dígito verificador); vazio fica vazio;
    - sexo: 1/M = Masculino, 2/F = Feminino, o resto (0, 9, vazio) = Ignorado;
    - situacao = "definitivo" (arquivo nacional) ou "preliminar" (arquivos por UF, 2025+).

Saída: data/silver/sinasc/sinasc_nascidos_vivos.parquet
           ano, mes, codigo_municipio_residencia, sexo, situacao, nascidos_vivos
       data/silver/sinasc/_auditoria/sinasc_resumo.json  (registros lidos e meses inválidos por arquivo)
Uso:   python pipeline/17_silver_sinasc.py
"""

import json
import os
import re

import pandas as pd

import config
from comum import dbf_rapido
from comum.datasus import dbc2dbf

PADRAO = re.compile(r"sinasc_nascidos_vivos_(\d{4})(?:_prelim_([A-Z]{2}))?\.dbc$")
SEXO = {"1": "Masculino", "M": "Masculino", "2": "Feminino", "F": "Feminino"}
SAIDA = config.SILVER_SINASC / "sinasc_nascidos_vivos.parquet"
SAIDA_RESUMO = config.SILVER_SINASC / "_auditoria" / "sinasc_resumo.json"


def arquivos() -> list[tuple[int, str | None, object]]:
    achados = []
    for arq in config.BRONZE_SINASC.glob("sinasc_nascidos_vivos_*.dbc"):
        m = PADRAO.search(arq.name)
        if m:
            achados.append((int(m.group(1)), m.group(2), arq))
    return sorted(achados, key=lambda x: (x[0], x[1] or ""))


def texto(serie: pd.Series) -> pd.Series:
    """Campo como texto, também quando o .dbf o guarda como número (sem o ".0" do float)."""
    if serie.dtype.kind in "fiu":
        serie = serie.astype("Int64")
    return serie.astype("string").str.strip()


def contar_arquivo(dbf, ano: int) -> tuple[pd.DataFrame, dict]:
    _, _, _, campos = dbf_rapido.cabecalho(dbf)
    nomes = {c[0].upper(): c[0] for c in campos}  # 1996-2005 usam minúsculas em alguns campos
    usar = [nomes["CODMUNRES"], nomes["DTNASC"], nomes["SEXO"]]
    partes, lidos, invalidas = [], 0, 0
    for bloco in dbf_rapido.iterar(dbf, colunas=usar):
        bloco.columns = [c.upper() for c in bloco.columns]
        lidos += len(bloco)
        # DDMMAAAA; em 1994-1996 o dia muitas vezes vem "00" (ignorado): o mês vale assim mesmo.
        mes = pd.to_numeric(texto(bloco["DTNASC"]).str.zfill(8).str[2:4], errors="coerce")
        mes = mes.where(mes.between(1, 12))
        invalidas += int(mes.isna().sum())
        mun = texto(bloco["CODMUNRES"])
        mun = mun.where(mun.str.len() != 7, mun.str[:6]).replace("", pd.NA)
        sexo = texto(bloco["SEXO"]).map(SEXO).fillna("Ignorado")
        df = pd.DataFrame({"mes": mes.astype("Int8"), "codigo_municipio_residencia": mun, "sexo": sexo})
        partes.append(df.groupby(["mes", "codigo_municipio_residencia", "sexo"], dropna=False, as_index=False)
                        .size().rename(columns={"size": "nascidos_vivos"}))
    tabela = (pd.concat(partes).groupby(["mes", "codigo_municipio_residencia", "sexo"], dropna=False, as_index=False)
              ["nascidos_vivos"].sum())
    tabela.insert(0, "ano", ano)
    return tabela, {"registros": lidos, "mes_invalido": invalidas}


def main() -> None:
    config.SILVER_SINASC.mkdir(parents=True, exist_ok=True)
    SAIDA_RESUMO.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = config.DUCKDB_TMP / "17"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    partes, resumo = [], {}
    for ano, uf, arq in arquivos():
        dbf = tmp_dir / (arq.stem + ".dbf")
        dbc2dbf(str(arq), str(dbf))
        tabela, info = contar_arquivo(dbf, ano)
        os.remove(dbf)
        tabela["situacao"] = "preliminar" if uf else "definitivo"
        partes.append(tabela)
        resumo[arq.name] = info
        print(arq.name, info, flush=True)
    silver = (pd.concat(partes, ignore_index=True)
              .groupby(["ano", "mes", "codigo_municipio_residencia", "sexo", "situacao"], dropna=False, as_index=False)
              ["nascidos_vivos"].sum()
              .sort_values(["ano", "mes", "codigo_municipio_residencia", "sexo"], na_position="last")
              .reset_index(drop=True))
    silver["nascidos_vivos"] = silver["nascidos_vivos"].astype("int64")
    tmp = SAIDA.with_suffix(".tmp")
    silver.to_parquet(tmp, index=False, compression="zstd")
    tmp.replace(SAIDA)
    SAIDA_RESUMO.write_text(json.dumps(resumo, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    por_ano = silver.groupby("ano")["nascidos_vivos"].sum()
    print(por_ano.to_string())
    print(f"{SAIDA.name}: {len(silver):,} linhas")


if __name__ == "__main__":
    main()
