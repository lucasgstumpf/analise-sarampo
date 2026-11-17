"""Passo 19 (gold) - Nascidos vivos, população e cobertura vacinal contra sarampo 2020+.

Entrada: data/silver/sinasc/sinasc_nascidos_vivos.parquet              (passo 17)
         data/silver/populacao/populacao_{ibge_pop,svs}.parquet         (passo 18)
         data/silver/sipni_doses/vacinacao_sarampo_sipni.parquet        (passo 07, nominal 2020+)
         data/gold/sipni_historico/gold_hist_cobertura_municipio_ano    (passo 13, CPNI 1994-2019)
         data/referencia/tabnet_cobertura_uf_ano.csv                    (TabNet, cobertura oficial)

Cobertura vacinal, com a metodologia do PNI (nota técnica do TabNet "Imunizações -
Cobertura", bd_pni/Imun_cobertura_desde_1994.pdf):
    cobertura = doses da dose indicada / população-alvo x 100
    local     = município de APLICAÇÃO da dose (não o de residência)
    população-alvo de 1 ano = nascidos vivos (SINASC) do ANO ANTERIOR, por município de
              residência da mãe; se o SINASC daquele ano não existe, o mais recente
    ano corrente: população-alvo proporcional aos meses com dados (meta mensal acumulada)
Numerador na base nominal (crianças de 1 ano, idade em anos completos na data da dose):
    D1 = SCR, 1ª dose
    D2 = SCR 2ª dose + tetra viral (SCRV) (a tetra é a 2ª dose do esquema desde 2013)
Conferido contra o TabNet de 2020-2022 (passo 14): 2021 bate (erro médio de 3 p.p. por UF);
2020 fica ~14 p.p. abaixo e 2022 ~7 p.p. acima, pela diferença de cobertura das bases (ver
data/referencia/investigacao_divergencias.md).

Saída: data/gold/demografia/
    gold_nascidos_vivos_municipio_ano   ano x município de residência (SINASC)
    gold_nascidos_vivos_uf_ano          ano x UF e Brasil
    gold_populacao_municipio_ano        ano x município: total, <1, 1, 1-4 e <5 anos
                                        (1980-1999 IBGE/POP; 2000-2025 estimativas SVS)
    gold_populacao_uf_ano               ano x UF e Brasil
    gold_cobertura_nominal_municipio_ano  2020+: doses D1/D2, população-alvo e cobertura
    gold_cobertura_nominal_uf_ano         2020+: o mesmo por UF e Brasil
    gold_serie_cobertura_uf_ano         1994-hoje, D1 e D2: CPNI do FTP (1994-2016), TabNet
                                        (2017-2022) e nominal (2023+); a coluna fonte diz qual
Uso:   python pipeline/19_gold_demografia_cobertura.py
"""

import importlib
import json

import duckdb
import numpy as np
import pandas as pd

import config

GOLD_DIR = config.GOLD_DEMOGRAFIA
SILVER_DOSES = config.SILVER_SIPNI_DOSES / "vacinacao_sarampo_sipni.parquet"
DOSE_GRUPO = importlib.import_module("09_gold_vacinacao").DOSE_GRUPO
SCR, SCRV = "Tríplice viral (SCR)", "Tetra viral (SCRV)"
NUMERADOR = {
    "d1": f"vacina_tipo = '{SCR}' AND dose_grupo = '1ª dose'",
    "d2": f"(vacina_tipo = '{SCR}' AND dose_grupo = '2ª dose') OR vacina_tipo = '{SCRV}'",
}
IDADE_ALVO = 1
ANOS_TABNET = range(2017, 2023)  # anos em que a série usa o valor oficial do TabNet


def salvar(nome: str, tabela: pd.DataFrame) -> None:
    tabela = tabela.reset_index(drop=True)
    tabela.to_parquet(GOLD_DIR / f"{nome}.parquet", index=False, compression="zstd")
    tabela.to_csv(GOLD_DIR / f"{nome}.csv", index=False, encoding="utf-8", lineterminator="\n")
    print(f"{nome}: {len(tabela):,} linhas", flush=True)


def siglas() -> dict[str, str]:
    ufs = json.loads((config.BRONZE_IBGE / "uf_meta.json").read_text(encoding="utf-8"))
    return {str(u["id"]): u["sigla"] for u in ufs}


def com_brasil(df: pd.DataFrame, chaves: list[str], valores: list[str], uf_sigla: dict[str, str]) -> pd.DataFrame:
    """Soma por UF (2 primeiros dígitos do município) e acrescenta o Brasil (codigo_uf 00)."""
    uf = df.groupby(chaves + ["codigo_uf"], as_index=False, dropna=False)[valores].sum()
    br = df.groupby(chaves, as_index=False, dropna=False)[valores].sum().assign(codigo_uf="00")
    tab = pd.concat([uf, br], ignore_index=True)
    tab["uf"] = tab["codigo_uf"].map(uf_sigla).where(tab["codigo_uf"] != "00", "BR").fillna("Ignorada")
    return tab.sort_values(chaves + ["codigo_uf"]).reset_index(drop=True)


def nascidos_vivos() -> pd.DataFrame:
    nv = pd.read_parquet(config.SILVER_SINASC / "sinasc_nascidos_vivos.parquet")
    nv = (nv.groupby(["ano", "codigo_municipio_residencia", "situacao"], dropna=False, as_index=False)
          ["nascidos_vivos"].sum().rename(columns={"codigo_municipio_residencia": "codigo_municipio"}))
    nv["codigo_uf"] = nv["codigo_municipio"].str[:2]
    return nv[["ano", "codigo_municipio", "codigo_uf", "situacao", "nascidos_vivos"]]


def populacao() -> pd.DataFrame:
    pop = pd.read_parquet(config.SILVER_POPULACAO / "populacao_ibge_pop.parquet")
    pop = pop[pop["ano"] < 2000]
    pop = pop.assign(
        menor_1=np.where((pop["idade_max"] == 0).fillna(False), pop["populacao"], 0),
        um=np.where(((pop["idade_min"] == 1) & (pop["idade_max"] == 1)).fillna(False), pop["populacao"], 0),
        um_a_4=np.where(((pop["idade_min"] >= 1) & (pop["idade_max"] <= 4)).fillna(False), pop["populacao"], 0),
        fonte="IBGE/POP (DATASUS)")
    svs = pd.read_parquet(config.SILVER_POPULACAO / "populacao_svs.parquet")
    svs = svs.assign(menor_1=np.where(svs["idade"] == 0, svs["populacao"], 0),
                     um=np.where(svs["idade"] == 1, svs["populacao"], 0),
                     um_a_4=np.where(svs["idade"].between(1, 4), svs["populacao"], 0),
                     fonte="Estimativas SVS/MS (POPSVS)")
    tab = pd.concat([pop, svs], ignore_index=True)
    tab = (tab.groupby(["ano", "codigo_municipio", "fonte"], as_index=False)
           [["populacao", "menor_1", "um", "um_a_4"]].sum()
           .rename(columns={"populacao": "populacao_total", "menor_1": "populacao_menor_1",
                            "um": "populacao_1_ano", "um_a_4": "populacao_1_a_4"}))
    tab["populacao_menor_5"] = tab["populacao_menor_1"] + tab["populacao_1_a_4"]
    tab["codigo_uf"] = tab["codigo_municipio"].str[:2]
    tab["ano"] = tab["ano"].astype("int64")
    return tab[["ano", "codigo_municipio", "codigo_uf", "fonte", "populacao_total", "populacao_menor_1",
                "populacao_1_ano", "populacao_1_a_4", "populacao_menor_5"]].sort_values(["ano", "codigo_municipio"])


def doses_nominais(con) -> tuple[pd.DataFrame, int]:
    """Doses D1 e D2 em crianças de 1 ano, por ano da vacinação e município de aplicação.
    Devolve também quantos meses do último ano têm dados (para o ano corrente)."""
    filtros = " ".join(f", count(*) FILTER (WHERE {cond}) AS doses_{nome}" for nome, cond in NUMERADOR.items())
    doses = con.sql(f"""
        WITH s AS (SELECT *, {DOSE_GRUPO} AS dose_grupo FROM read_parquet('{SILVER_DOSES}')
                   WHERE idade_paciente = {IDADE_ALVO} AND data_vacinacao IS NOT NULL
                     AND year(data_vacinacao) >= {config.ANO_INICIAL_SIPNI_DOSES}
                     AND data_vacinacao <= DATE '{config.DATA_CORTE}')
        SELECT year(data_vacinacao)::BIGINT AS ano, codigo_municipio_estabelecimento AS codigo_municipio {filtros}
        FROM s GROUP BY ALL ORDER BY ALL""").df()
    ultimo_mes = con.sql(f"SELECT max(ano_mes) FROM read_parquet('{SILVER_DOSES}')").fetchall()[0][0]
    return doses, int(ultimo_mes[5:7]) if int(ultimo_mes[:4]) == doses["ano"].max() else 12


def cobertura_nominal(doses: pd.DataFrame, nv: pd.DataFrame, meses_ultimo_ano: int) -> pd.DataFrame:
    """Junta doses (por município de aplicação) e população-alvo (SINASC do ano anterior)."""
    alvo = nv.groupby(["ano", "codigo_municipio"], as_index=False)["nascidos_vivos"].sum()
    anos_sinasc = sorted(alvo["ano"].unique())
    linhas = []
    for ano in sorted(doses["ano"].unique()):
        ano_alvo = max(a for a in anos_sinasc if a <= ano - 1)
        pop = alvo[alvo["ano"] == ano_alvo][["codigo_municipio", "nascidos_vivos"]].rename(
            columns={"nascidos_vivos": "populacao_alvo"})
        d = doses[doses["ano"] == ano].merge(pop, on="codigo_municipio", how="outer")
        d["ano"] = ano
        d["ano_sinasc_populacao_alvo"] = ano_alvo
        fracao = meses_ultimo_ano / 12 if ano == doses["ano"].max() and meses_ultimo_ano < 12 else 1.0
        d["meses_com_dados"] = round(12 * fracao)
        d["populacao_alvo"] = d["populacao_alvo"] * fracao
        linhas.append(d)
    cob = pd.concat(linhas, ignore_index=True)
    for c in ["doses_d1", "doses_d2"]:
        cob[c] = cob[c].fillna(0).astype("int64")
    cob["codigo_uf"] = cob["codigo_municipio"].str[:2]
    situacao = nv.groupby("ano")["situacao"].first()
    cob["situacao_sinasc"] = cob["ano_sinasc_populacao_alvo"].map(situacao)
    return cob


def calcular_percentuais(tab: pd.DataFrame) -> pd.DataFrame:
    for c in ["d1", "d2"]:
        tab[f"cobertura_{c}_percentual"] = np.round(100 * tab[f"doses_{c}"] / tab["populacao_alvo"].where(
            tab["populacao_alvo"] > 0), 2)
    return tab


def tabnet(uf_sigla: dict[str, str]) -> pd.DataFrame:
    """Cobertura oficial do TabNet (D1 = 021, D2 = 098) por UF e Brasil, nos ANOS_TABNET."""
    referencia = config.DADOS / "referencia"
    if not referencia.exists():  # com SARAMPO_DADOS_DIR, as referências continuam as do repositório
        referencia = config.RAIZ / "data" / "referencia"
    ref = pd.read_csv(referencia / "tabnet_cobertura_uf_ano.csv", dtype={"codigo_uf": str})
    ref = ref[ref["ano"].isin(ANOS_TABNET) & ref["indicador"].isin(["triplice_viral_d1", "triplice_viral_d2"])]
    return pd.DataFrame({
        "ano": ref["ano"], "dose": ref["indicador"].str[-2:], "codigo_uf": ref["codigo_uf"],
        "uf": ref["codigo_uf"].map(uf_sigla).where(ref["codigo_uf"] != "00", "BR"),
        "doses_aplicadas": np.nan, "populacao_alvo": np.nan, "cobertura_percentual": ref["cobertura_percentual"],
        "fonte": "TabNet (SI-PNI; atualizado em maio/2023)"})


def serie_cobertura(cob_uf: pd.DataFrame, uf_sigla: dict[str, str]) -> pd.DataFrame:
    """Série oficial sempre que existe:
        1994-2016  CPNI do FTP (D1 pelo indicador do passo 13; D2 = código 098, 2013+): bate
                   com o TabNet, e traz doses e população-alvo;
        2017-2022  TabNet: o CPNI do FTP de 2017-2019 é um retrato anterior (2019 incompleto) e a
                   base nominal de 2020-2022 difere do dado oficial (ver
                   data/referencia/investigacao_divergencias.md); só o percentual;
        2023+      base nominal + SINASC (não há dado oficial exportável)."""
    hist = pd.read_parquet(config.GOLD / "sipni_historico" / "gold_hist_cobertura_municipio_ano.parquet")
    partes = []
    for dose, filtro in [("d1", hist["indicador_d1_sarampo"]), ("d2", hist["codigo_imunobiologico"] == "098")]:
        h = hist[filtro]
        h = com_brasil(h.assign(codigo_uf=h["codigo_uf"].astype(str).str.zfill(2)), ["ano"],
                       ["doses_aplicadas", "populacao_alvo"], uf_sigla)
        h["dose"] = dose
        h["fonte"] = "SI-PNI agregado (CPNI)"
        partes.append(h)
    partes = [h[~h["ano"].isin(ANOS_TABNET)] for h in partes]
    for dose in ["d1", "d2"]:
        n = cob_uf[~cob_uf["ano"].isin(ANOS_TABNET)][["ano", "codigo_uf", "uf", f"doses_{dose}", "populacao_alvo"]].rename(
            columns={f"doses_{dose}": "doses_aplicadas"})
        n["dose"] = dose
        n["fonte"] = "SI-PNI/RNDS nominal + SINASC"
        partes.append(n)
    serie = pd.concat(partes, ignore_index=True)
    serie["cobertura_percentual"] = np.round(100 * serie["doses_aplicadas"] / serie["populacao_alvo"].where(
        serie["populacao_alvo"] > 0), 2)
    serie = pd.concat([serie, tabnet(uf_sigla)], ignore_index=True)
    return (serie[["ano", "dose", "codigo_uf", "uf", "doses_aplicadas", "populacao_alvo", "cobertura_percentual", "fonte"]]
            .sort_values(["dose", "ano", "codigo_uf"]).reset_index(drop=True))


def main() -> None:
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    uf_sigla = siglas()

    nv = nascidos_vivos()
    salvar("gold_nascidos_vivos_municipio_ano", nv)
    salvar("gold_nascidos_vivos_uf_ano", com_brasil(nv, ["ano", "situacao"], ["nascidos_vivos"], uf_sigla))

    pop = populacao()
    salvar("gold_populacao_municipio_ano", pop)
    valores = ["populacao_total", "populacao_menor_1", "populacao_1_ano", "populacao_1_a_4", "populacao_menor_5"]
    salvar("gold_populacao_uf_ano", com_brasil(pop, ["ano", "fonte"], valores, uf_sigla))

    con = duckdb.connect()
    con.execute(f"SET memory_limit='{config.DUCKDB_MEMORIA}'")
    doses, meses = doses_nominais(con)
    con.close()
    cob = cobertura_nominal(doses, nv, meses)
    colunas = ["ano", "codigo_municipio", "codigo_uf", "doses_d1", "doses_d2", "populacao_alvo",
               "cobertura_d1_percentual", "cobertura_d2_percentual", "ano_sinasc_populacao_alvo",
               "situacao_sinasc", "meses_com_dados"]
    salvar("gold_cobertura_nominal_municipio_ano",
           calcular_percentuais(cob).sort_values(["ano", "codigo_municipio"], na_position="last")[colunas])
    chaves = ["ano", "ano_sinasc_populacao_alvo", "situacao_sinasc", "meses_com_dados"]
    cob_uf = calcular_percentuais(com_brasil(cob.dropna(subset=["codigo_uf"]), chaves,
                                             ["doses_d1", "doses_d2", "populacao_alvo"], uf_sigla))
    salvar("gold_cobertura_nominal_uf_ano", cob_uf[["ano", "codigo_uf", "uf"] + colunas[3:8] + colunas[8:]])
    salvar("gold_serie_cobertura_uf_ano", serie_cobertura(cob_uf, uf_sigla))


if __name__ == "__main__":
    main()
