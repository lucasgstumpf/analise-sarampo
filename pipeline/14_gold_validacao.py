"""Passo 14 (gold) - Validação da gold contra as referências oficiais do Ministério da Saúde.

Entrada: data/gold/sinan/gold_sinan_notificacoes.parquet          (passo 11)
         data/gold/sipni_historico, data/gold/demografia            (passos 13 e 19, cobertura)
         data/referencia/ms_sarampo_casos_obitos_1990_2026.csv      (transcrito dos PDFs do MS)
         data/referencia/tabnet_cobertura_uf_ano.csv                (TabNet, utilitarios/consultar_tabnet.py)
         data/referencia/divergencias_conhecidas.csv                (diferenças já analisadas)

Compara, ano a ano, no Brasil e em cada UF, os casos confirmados e os óbitos por sarampo da
gold com a tabela oficial, e a cobertura vacinal por UF com o TabNet (ver comparar_cobertura). Definição conferida contra a própria tabela (ver
data/referencia/README.md): caso confirmado = classificacao_final 1, por ano de notificação
e UF de residência (ou de notificação, quando a residência está vazia); óbito = caso
confirmado com evolucao_caso 2.

Cada comparação recebe um status:
    OK          |gold - oficial| <= max(TOLERANCIA_ABSOLUTA, TOLERANCIA_RELATIVA * oficial)
    PRELIMINAR  fora da tolerância, mas no ano da data de corte ou no anterior, que a fonte
                ainda revisa ("dados preliminares sujeitos a revisão")
    EXPLICADA   fora da tolerância e registrada, com justificativa, em divergencias_conhecidas.csv
    DIVERGENTE  fora da tolerância e sem explicação: precisa ser investigada
Com SARAMPO_VALIDACAO_ESTRITA=1, o passo termina com erro se houver alguma DIVERGENTE (para
o executor parar antes de publicar).

Saída: data/gold/validacao/gold_validacao_referencias.{parquet,csv}  (uma linha por comparação)
       data/gold/validacao/gold_validacao_resumo.{parquet,csv}       (contagem por métrica e status)
Uso:   python pipeline/14_gold_validacao.py
"""

import json
import os
import sys

import numpy as np
import pandas as pd

import config

GOLD_DIR = config.GOLD / "validacao"
REFERENCIAS = config.DADOS / "referencia"
if not REFERENCIAS.exists():  # com SARAMPO_DADOS_DIR, as referências continuam as do repositório
    REFERENCIAS = config.RAIZ / "data" / "referencia"
REF_CASOS = "ms_sarampo_casos_obitos_1990_2026"
REF_COBERTURA = "tabnet_cobertura_uf_ano"
TOLERANCIA_COBERTURA_CPNI = 0.05     # pontos percentuais: mesmo dado (CPNI), só recalculado
TOLERANCIA_COBERTURA_NOMINAL = 5.0   # pontos percentuais: base nominal + SINASC x dado oficial
# Indicador do TabNet -> (código CPNI, dose da cobertura nominal 2020+)
INDICADORES_COBERTURA = {"triplice_viral_d1": ("021", "d1"), "triplice_viral_d2": ("098", "d2"),
                         "tetra_viral": ("097", None), "sarampo_monovalente": ("018", None)}

TOLERANCIA_ABSOLUTA = 10      # casos ou óbitos
TOLERANCIA_RELATIVA = 0.05    # 5% do valor oficial
ESTRITA = os.environ.get("SARAMPO_VALIDACAO_ESTRITA") == "1"


def sinan_por_ano_uf(uf_sigla: dict[str, str]) -> pd.DataFrame:
    g = pd.read_parquet(config.GOLD / "sinan" / "gold_sinan_notificacoes.parquet",
                        columns=["ano_notificacao", "uf_residencia", "uf_notificacao", "classificacao_final",
                                 "evolucao_caso"])
    c = g[g["classificacao_final"] == 1].copy()
    c["obito"] = (c["evolucao_caso"] == 2).fillna(False).astype(int)  # evolução vazia não é óbito
    # UF de residência; sem residência (ex.: migrantes em RR em 2018), a UF de notificação.
    uf = c["uf_residencia"].fillna(c["uf_notificacao"])
    c["codigo"] = uf.astype("string").map(uf_sigla).fillna("Ignorada")
    uf = (c.groupby(["codigo", "ano_notificacao"]).agg(casos_confirmados=("obito", "size"), obitos=("obito", "sum"))
          .reset_index().assign(nivel="uf"))
    br = (c.groupby("ano_notificacao").agg(casos_confirmados=("obito", "size"), obitos=("obito", "sum"))
          .reset_index().assign(nivel="brasil", codigo="BR"))
    return pd.concat([uf, br], ignore_index=True).rename(columns={"ano_notificacao": "ano"})


def comparar(gold: pd.DataFrame, ref: pd.DataFrame, anos: range) -> pd.DataFrame:
    ref = ref[ref["nivel"].isin(["uf", "brasil"]) & ref["ano"].isin(anos)]
    chaves = ["nivel", "codigo", "ano"]
    linhas = []
    for metrica in ["casos_confirmados", "obitos"]:
        m = ref[chaves + [metrica]].merge(gold[chaves + [metrica]], on=chaves, how="outer",
                                          suffixes=("_referencia", "_gold"))
        m = m[m["ano"].isin(anos)]
        linhas.append(pd.DataFrame({
            "referencia": REF_CASOS, "metrica": metrica, "nivel": m["nivel"], "codigo": m["codigo"],
            "ano": m["ano"].astype(int),
            "valor_gold": m[f"{metrica}_gold"].fillna(0).astype(int),
            "valor_referencia": m[f"{metrica}_referencia"].astype("Int64"),
        }))
    t = pd.concat(linhas, ignore_index=True)
    t["diferenca"] = t["valor_gold"] - t["valor_referencia"]
    t["diferenca_pct"] = (100 * t["diferenca"] / t["valor_referencia"].replace(0, pd.NA)).astype("Float64").round(2)
    t["tolerancia"] = np.maximum(TOLERANCIA_ABSOLUTA, TOLERANCIA_RELATIVA * t["valor_referencia"].fillna(0)).round(1)
    return t


def classificar(t: pd.DataFrame) -> pd.DataFrame:
    conhecidas = pd.read_csv(REFERENCIAS / "divergencias_conhecidas.csv", dtype={"ano": "Int64"}, keep_default_na=False)
    chave = ["referencia", "metrica", "nivel", "codigo", "ano"]
    # codigo "*" = todas as UFs daquele ano (ex.: uma fonte inteira desatualizada naquele ano)
    exatas = conhecidas[conhecidas["codigo"] != "*"]
    todas = conhecidas[conhecidas["codigo"] == "*"].drop(columns="codigo")
    t = t.merge(exatas[chave + ["justificativa"]], on=chave, how="left")
    geral = t[chave].merge(todas[[c for c in chave if c != "codigo"] + ["justificativa"]],
                           on=[c for c in chave if c != "codigo"], how="left")["justificativa"]
    t["justificativa"] = t["justificativa"].fillna(pd.Series(geral.to_numpy(), index=t.index))
    dentro = t["diferenca"].abs() <= t["tolerancia"]
    sem_referencia = t["valor_referencia"].isna() | t["valor_gold"].isna()  # ex.: UF "Ignorada" no SINAN
    preliminar = t["ano"] >= config.DATA_CORTE.year - 1
    t["status"] = np.select(
        [dentro & ~sem_referencia, t["justificativa"].notna(), preliminar, sem_referencia],
        ["OK", "EXPLICADA", "PRELIMINAR", "SEM_REFERENCIA"], default="DIVERGENTE")
    return t.sort_values(["metrica", "nivel", "codigo", "ano"]).reset_index(drop=True)


def comparar_cobertura(uf_sigla: dict[str, str]) -> pd.DataFrame:
    """Cobertura por UF e ano contra o TabNet (SI-PNI). Duas comparações:
    - 1994-2019 (CPNI): a gold recalcula a cobertura de cada código (soma das doses / soma da
      população-alvo de todas as linhas do código, como o TabNet); deve bater (0,05 p.p.);
    - 2020-2022 (nominal + SINASC, passo 19): metodologia própria, tolerância de 5 p.p."""
    arquivo = REFERENCIAS / f"{REF_COBERTURA}.csv"
    if not arquivo.exists():
        return pd.DataFrame()
    ref = pd.read_csv(arquivo, dtype={"codigo_imunobiologico": str, "codigo_uf": str})
    ref["codigo"] = ref["codigo_uf"].map(uf_sigla).where(ref["codigo_uf"] != "00", "BR")
    hist = pd.read_parquet(config.GOLD / "sipni_historico" / "gold_hist_cobertura_municipio_ano.parquet",
                           columns=["ano", "codigo_uf", "codigo_imunobiologico", "doses_aplicadas", "populacao_alvo"])
    hist = hist.groupby(["ano", "codigo_uf", "codigo_imunobiologico"], as_index=False)[
        ["doses_aplicadas", "populacao_alvo"]].sum()
    hist["codigo"] = hist["codigo_uf"].astype(str).str.zfill(2).map(uf_sigla)
    brasil = hist.groupby(["ano", "codigo_imunobiologico"], as_index=False)[["doses_aplicadas", "populacao_alvo"]].sum()
    hist = pd.concat([hist, brasil.assign(codigo="BR")], ignore_index=True)
    hist["valor_gold"] = 100 * hist["doses_aplicadas"] / hist["populacao_alvo"].where(hist["populacao_alvo"] > 0)
    nominal_arq = config.GOLD / "demografia" / "gold_cobertura_nominal_uf_ano.parquet"
    nominal = pd.read_parquet(nominal_arq) if nominal_arq.exists() else None
    linhas = []
    for indicador, (codigo, dose) in INDICADORES_COBERTURA.items():
        r = ref[ref["indicador"] == indicador]
        h = r[r["ano"] <= 2019].merge(hist[hist["codigo_imunobiologico"] == codigo][["ano", "codigo", "valor_gold"]],
                                      on=["ano", "codigo"], how="left")
        h["tolerancia"] = TOLERANCIA_COBERTURA_CPNI
        h["fonte_gold"] = "CPNI recalculado"
        linhas.append(h)
        if dose and nominal is not None:
            n = nominal[["ano", "uf", f"cobertura_{dose}_percentual"]].rename(
                columns={"uf": "codigo", f"cobertura_{dose}_percentual": "valor_gold"})
            m = r[r["ano"] >= 2020].merge(n, on=["ano", "codigo"], how="left")
            m["tolerancia"] = TOLERANCIA_COBERTURA_NOMINAL
            m["fonte_gold"] = "nominal + SINASC"
            linhas.append(m)
    t = pd.concat(linhas, ignore_index=True)
    return pd.DataFrame({
        "referencia": REF_COBERTURA, "metrica": "cobertura_" + t["indicador"],
        "nivel": np.where(t["codigo"] == "BR", "brasil", "uf"),
        "codigo": t["codigo"], "ano": t["ano"].astype(int), "valor_gold": t["valor_gold"].round(2),
        "valor_referencia": t["cobertura_percentual"], "fonte_gold": t["fonte_gold"],
        "diferenca": (t["valor_gold"] - t["cobertura_percentual"]).round(2), "tolerancia": t["tolerancia"],
    })


def salvar(nome: str, tabela: pd.DataFrame) -> None:
    tabela.to_parquet(GOLD_DIR / f"{nome}.parquet", index=False, compression="zstd")
    tabela.to_csv(GOLD_DIR / f"{nome}.csv", index=False, encoding="utf-8", lineterminator="\n")


def main() -> None:
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    uf_sigla = {str(u["id"]): u["sigla"] for u in
                json.loads((config.BRONZE_IBGE / "uf_meta.json").read_text(encoding="utf-8"))}
    ref = pd.read_csv(REFERENCIAS / f"{REF_CASOS}.csv", keep_default_na=False)
    gold = sinan_por_ano_uf(uf_sigla)
    anos = range(int(gold["ano"].min()), config.DATA_CORTE.year + 1)

    t = comparar(gold, ref, anos)
    cobertura = comparar_cobertura(uf_sigla)
    if len(cobertura):
        # Valor 0 no TabNet com população-alvo vazia na gold = código ainda não usado no ano.
        cobertura = cobertura[~((cobertura["valor_referencia"] == 0) & cobertura["valor_gold"].isna())]
        t = pd.concat([t, cobertura], ignore_index=True)
    t = classificar(t)
    salvar("gold_validacao_referencias", t)
    resumo = t.groupby(["metrica", "nivel", "status"]).size().unstack(fill_value=0).reset_index()
    salvar("gold_validacao_resumo", resumo)

    print(f"Referência: {REF_CASOS} | anos {anos.start}-{anos.stop - 1} | tolerância: "
          f"max({TOLERANCIA_ABSOLUTA}, {TOLERANCIA_RELATIVA:.0%} do oficial)")
    print(resumo.to_string(index=False))
    divergentes = t[t["status"] == "DIVERGENTE"]
    if len(divergentes):
        print(f"\n{len(divergentes)} comparações DIVERGENTES (gold x oficial), as maiores:")
        print(divergentes.reindex(divergentes["diferenca"].abs().sort_values(ascending=False).index)
              .head(15)[["metrica", "nivel", "codigo", "ano", "valor_gold", "valor_referencia", "diferenca"]]
              .to_string(index=False))
        if ESTRITA:
            sys.exit("Validação estrita: há divergências sem explicação (SARAMPO_VALIDACAO_ESTRITA=1).")


if __name__ == "__main__":
    main()
