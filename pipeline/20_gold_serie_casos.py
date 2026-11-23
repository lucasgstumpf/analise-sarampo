"""Passo 20 (gold) - Série histórica de casos confirmados e óbitos por sarampo, 1990 até hoje.

Entrada: data/gold/sinan/gold_sinan_notificacoes.parquet       (passo 11; SINAN 2007+)
         data/referencia/ms_sarampo_casos_obitos_1990_2026.csv   (tabela oficial do MS)

O SINAN do FTP do DATASUS começa em 2007; antes disso, a única série consolidada é a tabela
oficial do Ministério da Saúde (CGVDI/SVSA), transcrita em data/referencia. Esta tabela junta
as duas, por UF e Brasil:
    1990-2006   casos e óbitos da tabela oficial do MS (fonte = "MS/CGVDI")
    2007-hoje   casos e óbitos calculados do SINAN (fonte = "SINAN"), com a mesma definição
                da validação (passo 14): caso confirmado = classificacao_final 1, por ano de
                notificação e UF de residência (de notificação, se a residência está vazia);
                óbito = caso confirmado com evolucao_caso 2
Em todos os anos ficam também as colunas da tabela oficial (casos_oficial_ms, obitos_oficial_ms),
para quem preferir a série oficial inteira ou quiser ver a diferença (passo 14).

Saída: data/gold/sinan/gold_serie_casos_obitos_uf_ano.{parquet,csv}
           nivel (uf, brasil), codigo (sigla ou BR), ano, casos_confirmados, obitos, fonte,
           casos_oficial_ms, obitos_oficial_ms
Uso:   python pipeline/20_gold_serie_casos.py
"""

import importlib
import json

import pandas as pd

import config

validacao = importlib.import_module("14_gold_validacao")
GOLD_DIR = config.GOLD / "sinan"
ANO_INICIO_SINAN = 2007


def main() -> None:
    uf_sigla = {str(u["id"]): u["sigla"] for u in
                json.loads((config.BRONZE_IBGE / "uf_meta.json").read_text(encoding="utf-8"))}
    ref = pd.read_csv(validacao.REFERENCIAS / f"{validacao.REF_CASOS}.csv", keep_default_na=False)
    ref = ref[ref["nivel"].isin(["uf", "brasil"])][["nivel", "codigo", "ano", "casos_confirmados", "obitos"]]
    sinan = validacao.sinan_por_ano_uf(uf_sigla)
    sinan = sinan[sinan["ano"].between(ANO_INICIO_SINAN, config.DATA_CORTE.year)]

    antes = ref[ref["ano"] < ANO_INICIO_SINAN].assign(fonte="MS/CGVDI (tabela oficial)")
    depois = sinan[["nivel", "codigo", "ano", "casos_confirmados", "obitos"]].assign(fonte="SINAN (FTP DATASUS)")
    serie = pd.concat([antes, depois], ignore_index=True)
    oficial = ref.rename(columns={"casos_confirmados": "casos_oficial_ms", "obitos": "obitos_oficial_ms"})
    serie = serie.merge(oficial, on=["nivel", "codigo", "ano"], how="outer")
    serie = serie[serie["ano"] <= config.DATA_CORTE.year]
    # Anos do SINAN sem nenhum caso numa UF: a UF não aparece no SINAN, mas a contagem é 0.
    sinan_anos = serie["ano"] >= ANO_INICIO_SINAN
    for c in ["casos_confirmados", "obitos"]:
        serie.loc[sinan_anos, c] = serie.loc[sinan_anos, c].fillna(0)
        serie[c] = serie[c].astype("Int64")
    serie.loc[sinan_anos, "fonte"] = serie.loc[sinan_anos, "fonte"].fillna("SINAN (FTP DATASUS)")
    for c in ["casos_oficial_ms", "obitos_oficial_ms"]:
        serie[c] = serie[c].astype("Int64")
    serie["nivel_ordem"] = serie["nivel"].map({"brasil": 0, "uf": 1})
    serie = serie.sort_values(["nivel_ordem", "codigo", "ano"]).drop(columns="nivel_ordem").reset_index(drop=True)

    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    nome = "gold_serie_casos_obitos_uf_ano"
    serie.to_parquet(GOLD_DIR / f"{nome}.parquet", index=False, compression="zstd")
    serie.to_csv(GOLD_DIR / f"{nome}.csv", index=False, encoding="utf-8", lineterminator="\n")
    br = serie[serie["nivel"] == "brasil"].set_index("ano")[["casos_confirmados", "obitos", "fonte"]]
    print(br.to_string())
    print(f"{nome}: {len(serie):,} linhas")


if __name__ == "__main__":
    main()
