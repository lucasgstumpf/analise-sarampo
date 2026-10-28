"""Passo 10 (gold) - Retrato da base mensal COMPLETA do SI-PNI (todas as vacinas, não só sarampo).

Entrada: data/bronze/sipni_doses/_perfil_bruto/{imunobiologicos,perfil_colunas}_{AAAA}_{mmm}.csv
         (gerados pelo passo 03 enquanto filtra cada mês)

O pipeline guarda só as doses de sarampo, mas o passo 03 lê a base inteira de cada mês e
aproveita para resumir: quantas doses de cada imunobiológico e como está cada coluna
(% vazio, valores distintos). Estas tabelas alimentam os notebooks 02 (estrutura da base
bruta) e 03 (panorama de todas as vacinas).

Meses processados antes desta funcionalidade não têm o retrato; para gerá-lo, reprocesse o
mês: python pipeline/03_bronze_sipni_doses.py --meses 2026-01

Saída: data/gold/sipni_todas_vacinas/gold_imunobiologicos_mes.{parquet,csv}
           mês x imunobiológico (ds_nome) x sigla x doses, com a marca contem_sarampo
       data/gold/sipni_todas_vacinas/gold_perfil_colunas_bruto.{parquet,csv}
           mês x coluna original x linhas, vazios, % vazio, distintos e um valor de exemplo
Uso:   python pipeline/10_gold_sipni_todas_vacinas.py
"""

import re

import pandas as pd

import config
from comum.dicionarios import COLUNAS_SIPNI

GOLD_DIR = config.GOLD / "sipni_todas_vacinas"
PADRAO = re.compile(r"_(\d{4})_([a-z]{3})\.csv$")


def ler_mensais(prefixo: str) -> pd.DataFrame:
    """Junta os CSVs mensais do perfil bruto, com a coluna ano_mes (AAAA-MM)."""
    partes = []
    for arquivo in sorted(config.BRONZE_SIPNI_PERFIL_BRUTO.glob(f"{prefixo}_*.csv")):
        m = PADRAO.search(arquivo.name)
        if not m or m.group(2) not in config.MESES_ABREV:
            continue
        ano_mes = f"{m.group(1)}-{config.MESES_ABREV.index(m.group(2)) + 1:02d}"
        partes.append(pd.read_csv(arquivo, dtype={"exemplo": str}).assign(ano_mes=ano_mes))
    if not partes:
        raise SystemExit(f"Nenhum {prefixo}_*.csv em {config.BRONZE_SIPNI_PERFIL_BRUTO}. "
                         "Rode o passo 03 com --meses AAAA-MM para gerar o retrato de algum mês.")
    return pd.concat(partes, ignore_index=True).sort_values("ano_mes", kind="stable")


def salvar(nome: str, tabela: pd.DataFrame) -> None:
    tabela = tabela.reset_index(drop=True)
    tabela.to_parquet(GOLD_DIR / f"{nome}.parquet", index=False, compression="zstd")
    tabela.to_csv(GOLD_DIR / f"{nome}.csv", index=False, encoding="utf-8")
    print(f"{nome}: {len(tabela):,} linhas ({tabela['ano_mes'].nunique()} meses)")


def main() -> None:
    GOLD_DIR.mkdir(parents=True, exist_ok=True)

    vacinas = ler_mensais("imunobiologicos")
    vacinas["contem_sarampo"] = vacinas["ds_nome"].str.contains("sarampo", case=False, na=False)
    salvar("gold_imunobiologicos_mes", vacinas[["ano_mes", "ds_nome", "sg_imunobiologico", "contem_sarampo", "doses"]])

    perfil = ler_mensais("perfil_colunas")
    perfil["pct_vazios"] = (100 * perfil["vazios"] / perfil["linhas"]).round(4)
    perfil["nome_legivel"] = perfil["coluna"].map(COLUNAS_SIPNI)
    # Exemplo só para colunas categóricas: em identificadores e textos livres ele não ajuda.
    perfil.loc[perfil["distintos_acima_do_limite"], "exemplo"] = None
    salvar("gold_perfil_colunas_bruto", perfil[["ano_mes", "coluna", "nome_legivel", "linhas", "vazios", "pct_vazios",
                                                 "distintos", "distintos_acima_do_limite", "exemplo"]])


if __name__ == "__main__":
    main()
