"""Camada gold: tabelas agregadas (pequenas) a partir da silver, prontas para os notebooks e
para ferramentas de BI. Cada tabela sai em .parquet e em .csv (UTF-8) em processed/gold/."""

from pathlib import Path

import numpy as np
import pandas as pd

PROCESSED_DIR = Path(__file__).parent / "processed"
SILVER = PROCESSED_DIR / "silver" / "vacinacao_sarampo_sipni.parquet"
DIM_MUNICIPIOS = PROCESSED_DIR / "silver" / "dim_municipios.csv"
GOLD_DIR = PROCESSED_DIR / "gold"

ROTULO_DOSE = {0: "Dose zero", 1: "1ª dose", 2: "2ª dose", 3: "3ª dose ou mais", 4: "3ª dose ou mais"}
FAIXAS_ATRASO = [-1, 0, 7, 30, 90, np.inf]
ROTULOS_ATRASO = ["Mesmo dia", "1-7 dias", "8-30 dias", "31-90 dias", "> 90 dias"]


def classificar_dose(df: pd.DataFrame) -> pd.Series:
    """Dose como aparece no cartão: usa o número da descrição; quando a descrição é só "Dose"
    (sem número), usa a ordem da dose do paciente na janela; reforços/adicionais ficam à parte."""
    reforco = df["descricao_dose_vacina"].str.contains("Refor|Adicional|Revacina", na=False) & df["dose_numero"].isna()
    numero = df["dose_numero"].fillna(df["ordem_dose_paciente"].clip(upper=3)).astype(int)
    dose = numero.map(ROTULO_DOSE).astype("string")
    return dose.mask(reforco, "Reforço/adicional")


def salvar(nome: str, tabela: pd.DataFrame) -> None:
    tabela = tabela.reset_index(drop=True)
    tabela.to_parquet(GOLD_DIR / f"{nome}.parquet", index=False, compression="zstd")
    tabela.to_csv(GOLD_DIR / f"{nome}.csv", index=False, encoding="utf-8")
    print(f"{nome}: {len(tabela):,} linhas")


def main() -> None:
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(SILVER)
    df["dose_grupo"] = classificar_dose(df)
    df["faixa_atraso"] = pd.cut(df["atraso_registro_dias"].astype(float), FAIXAS_ATRASO,
                                labels=ROTULOS_ATRASO).astype("string")
    dim = pd.read_csv(DIM_MUNICIPIOS)
    salvar("dim_municipios", dim)

    # Série diária nacional
    dia = df.groupby(["data_vacinacao", "dose_grupo"], as_index=False).size().rename(columns={"size": "doses"})
    salvar("gold_doses_dia", dia)

    # UF x mês x vacina x dose
    uf = (df.groupby(["ano_mes", "uf_paciente", "vacina_tipo", "dose_grupo"], dropna=False, as_index=False)
            .size().rename(columns={"size": "doses"}))
    salvar("gold_doses_uf_mes", uf)

    # Município (residência do paciente) x mês
    mun = (df.assign(d1=df["dose_grupo"].eq("1ª dose"), d2=df["dose_grupo"].eq("2ª dose"),
                     crianca_1a4=df["idade_paciente"].between(1, 4))
             .groupby(["codigo_municipio_paciente", "ano_mes"], as_index=False)
             .agg(doses=("d1", "size"), doses_d1=("d1", "sum"), doses_d2=("d2", "sum"),
                  doses_criancas_1a4=("crianca_1a4", "sum"),
                  pacientes_unicos=("codigo_paciente_anonimizado", "nunique")))
    mun["codigo_municipio"] = pd.to_numeric(mun["codigo_municipio_paciente"])
    mun = mun.merge(dim, on="codigo_municipio", how="left").drop(columns=["codigo_municipio"])
    salvar("gold_municipio_mes", mun)

    # Perfil demográfico
    perfil = (df.groupby(["ano_mes", "uf_paciente", "sexo_paciente", "faixa_etaria", "raca_cor_paciente", "dose_grupo"],
                         dropna=False, as_index=False).size().rename(columns={"size": "doses"}))
    salvar("gold_perfil", perfil)

    # Idade simples x dose (0 a 100+), para pirâmide/curva de idade
    idade = (df.groupby(["idade_paciente", "dose_grupo", "vacina_tipo"], as_index=False)
               .size().rename(columns={"size": "doses"}))
    salvar("gold_idade_dose", idade)

    # Coorte de crianças de 1 a 4 anos (idade mais recente do paciente): quantas receberam 1 e 2 doses
    criancas = df[df["idade_paciente"].between(1, 4)]
    por_crianca = (criancas.groupby("codigo_paciente_anonimizado")
                   .agg(codigo_municipio_paciente=("codigo_municipio_paciente", "last"),
                        uf_paciente=("uf_paciente", "last"),
                        doses=("data_vacinacao", "nunique"), idade=("idade_paciente", "max")))
    coorte = (por_crianca.assign(com_1_dose=True, com_2_ou_mais=por_crianca["doses"] >= 2)
              .groupby(["uf_paciente", "codigo_municipio_paciente"], dropna=False, as_index=False)
              .agg(criancas_vacinadas=("com_1_dose", "sum"), criancas_com_2_ou_mais_doses=("com_2_ou_mais", "sum")))
    coorte["codigo_municipio"] = pd.to_numeric(coorte["codigo_municipio_paciente"])
    coorte = coorte.merge(dim[["codigo_municipio", "municipio"]], on="codigo_municipio", how="left")
    coorte["prop_com_2_ou_mais"] = (coorte["criancas_com_2_ou_mais_doses"] / coorte["criancas_vacinadas"]).round(4)
    salvar("gold_coorte_criancas_municipio", coorte.drop(columns=["codigo_municipio"]))

    # Qualidade: atraso do registro no RNDS
    atraso = (df.groupby(["ano_mes", "uf_paciente", "faixa_atraso"], dropna=False, as_index=False)
                .size().rename(columns={"size": "doses"}))
    salvar("gold_atraso_registro", atraso)

    # Onde e por qual estratégia a dose foi aplicada
    estab = (df.groupby(["ano_mes", "uf_estabelecimento", "tipo_estabelecimento", "natureza_estabelecimento",
                         "estrategia_vacinacao"], dropna=False, as_index=False)
               .size().rename(columns={"size": "doses"}))
    salvar("gold_estabelecimento", estab)

    # KPIs mensais
    kpi = df.groupby("ano_mes").agg(
        doses=("dose_grupo", "size"), pacientes_unicos=("codigo_paciente_anonimizado", "nunique"),
        pct_criancas_1a4=("idade_paciente", lambda s: round(100 * s.between(1, 4).mean(), 2)),
        pct_rotina=("estrategia_vacinacao", lambda s: round(100 * s.eq("Rotina").mean(), 2)),
        mediana_atraso_dias=("atraso_registro_dias", "median"),
        pct_registro_ate_7d=("atraso_registro_dias", lambda s: round(100 * (s <= 7).mean(), 2)),
        ufs=("uf_paciente", "nunique"), municipios=("codigo_municipio_paciente", "nunique"),
    ).reset_index()
    salvar("gold_kpis_mensais", kpi)


if __name__ == "__main__":
    main()
