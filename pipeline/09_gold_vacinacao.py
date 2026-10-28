"""Passo 09 (gold) - Tabelas agregadas da vacinação contra sarampo, prontas para análise.

Entrada: data/silver/sipni_doses/vacinacao_sarampo_sipni.parquet e dim_municipios.csv  (passo 07)

Cada tabela é pequena e sai em .parquet e em .csv (UTF-8). A gold tem tudo o que os
notebooks 04 a 09 precisam: eles não leem a silver, então quem receber só a pasta gold
consegue rodá-los.

Panorama (notebooks 06, 07 e 09):
    dim_municipios                   código, nome e UF de cada município
    gold_doses_dia                   dia x mês do arquivo x grupo de dose x tipo de vacina
    gold_doses_uf_mes                UF x mês x tipo de vacina x dose
    gold_municipio_mes               município de residência x mês (doses, D1, D2, 1-4 anos, pacientes)
    gold_perfil                      mês x UF x sexo x faixa etária x raça/cor x vacina x dose
    gold_idade_dose                  mês x idade simples x dose x tipo de vacina
    gold_coorte_criancas_municipio   crianças de 1-4 anos vacinadas e com 2+ doses, por município
    gold_atraso_registro             mês x UF x faixa de atraso do registro no RNDS
    gold_estabelecimento             mês x UF x tipo/natureza do estabelecimento x estratégia
    gold_kpis_mensais                indicadores-resumo por mês
Detalhe e qualidade (notebooks 04, 05, 08 e 09):
    gold_resumo_geral                uma linha com os totais da base (doses, pacientes, datas...)
    gold_qualidade_colunas           % vazio, valores distintos e valor mais frequente de cada coluna
    gold_funil_processamento         linhas removidas por regra da silver, por mês
    gold_doses_por_paciente          nº de pacientes por nº de doses na janela
    gold_dose_descricao_ordem        mês x descrição da dose x ordem da dose do paciente
    gold_atraso_dias                 dias de atraso do registro (valor exato) x doses
    gold_intervalo_doses             idade na 1ª dose x dias entre 1ª e 2ª dose x pacientes
    gold_estrategia_faixa            mês x faixa etária x tipo/natureza do estabelecimento x estratégia
    gold_categoria_atendimento       mês x categoria de atendimento
    gold_nacionalidade_etnia         nacionalidade x etnia indígena
    gold_fluxo_uf                    UF de residência x UF de aplicação
    gold_estabelecimento_cnes        doses por estabelecimento (CNES), com UF, tipo e natureza
    gold_vacina_fabricante           mês x descrição/sigla/tipo de vacina x fabricante

Saída: data/gold/vacinacao/{tabela}.{parquet,csv}
Uso:   python pipeline/09_gold_vacinacao.py
"""

import json

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

import config

SILVER = config.SILVER_SIPNI_DOSES / "vacinacao_sarampo_sipni.parquet"
DIM_MUNICIPIOS = config.SILVER_SIPNI_DOSES / "dim_municipios.csv"
RESUMO_PROCESSAMENTO = config.SILVER_SIPNI_DOSES_AUDITORIA / "processamento_resumo.json"
GOLD_DIR = config.GOLD_VACINACAO

ROTULO_DOSE = {0: "Dose zero", 1: "1ª dose", 2: "2ª dose", 3: "3ª dose ou mais", 4: "3ª dose ou mais"}
FAIXAS_ATRASO = [-1, 0, 7, 30, 90, np.inf]
ROTULOS_ATRASO = ["Mesmo dia", "1-7 dias", "8-30 dias", "31-90 dias", "> 90 dias"]
# O mês fica como texto (usado em min/max); as demais colunas de texto viram categoria, o que
# corta a RAM pela metade. Toda agregação por categoria usa observed=True (só valores presentes).
TEXTO_SEM_CATEGORIA = {"ano_mes"}


def ler_silver() -> tuple[pd.DataFrame, dict[str, str]]:
    """Lê a silver já com o texto repetitivo como categoria (mesmos valores, menos memória) e
    devolve também o tipo de cada coluna no parquet."""
    tabela = pq.read_table(SILVER)
    tipos = {campo.name: str(campo.type) for campo in tabela.schema}
    texto = [campo.name for campo in tabela.schema
             if (pa.types.is_string(campo.type) or pa.types.is_large_string(campo.type))
             and campo.name not in TEXTO_SEM_CATEGORIA]
    df = tabela.to_pandas(categories=texto, self_destruct=True, split_blocks=True)
    del tabela
    return df, tipos


def classificar_dose(df: pd.DataFrame) -> pd.Series:
    """Dose como aparece no cartão: usa o número da descrição; quando a descrição é só "Dose"
    (sem número), usa a ordem da dose do paciente na janela; reforços/adicionais ficam à parte."""
    reforco = df["descricao_dose_vacina"].str.contains("Refor|Adicional|Revacina", na=False) & df["dose_numero"].isna()
    numero = df["dose_numero"].fillna(df["ordem_dose_paciente"].clip(upper=3)).astype(int)
    dose = numero.map(ROTULO_DOSE).astype("string")
    return dose.mask(reforco, "Reforço/adicional")


def contar(df: pd.DataFrame, colunas: list[str], dropna: bool = False) -> pd.DataFrame:
    """Nº de doses (linhas da silver) por combinação de `colunas`."""
    return df.groupby(colunas, dropna=dropna, as_index=False, observed=True).size().rename(columns={"size": "doses"})


def qualidade_colunas(df: pd.DataFrame, tipos: dict[str, str]) -> pd.DataFrame:
    """Uma linha por coluna da silver: tipo (como está no parquet), % vazio, nº de valores
    distintos e o valor mais frequente (para colunas com até 5.000 valores distintos)."""
    linhas = []
    for coluna in df.columns:
        serie = df[coluna]
        unicos = serie.nunique()
        frequente = pct_frequente = None
        if unicos and unicos <= 5000:
            contagem = serie.value_counts(normalize=True)
            frequente, pct_frequente = str(contagem.index[0]), round(100 * contagem.iloc[0], 2)
        exemplo = serie.dropna()
        linhas.append({
            "coluna": coluna, "tipo": tipos[coluna], "pct_nulos": round(100 * serie.isna().mean(), 4),
            "unicos": unicos, "mais_frequente": frequente, "pct_mais_frequente": pct_frequente,
            "exemplo": str(exemplo.iat[0]) if len(exemplo) else None,
        })
    return pd.DataFrame(linhas)


def intervalo_entre_doses(df: pd.DataFrame) -> pd.DataFrame:
    """Para pacientes com 2 a 10 doses na janela: dias entre a 1ª e a 2ª dose e idade na 1ª.
    (Mais de 10 doses indica provável colisão do identificador anonimizado.)"""
    base = df.loc[df["doses_paciente_janela"].between(2, 10),
                  ["codigo_paciente_anonimizado", "ordem_dose_paciente", "data_vacinacao", "idade_paciente"]]
    base["paciente"] = base["codigo_paciente_anonimizado"].cat.codes  # número do paciente: junção mais leve
    d1 = base[base["ordem_dose_paciente"] == 1].set_index("paciente")
    d2 = base[base["ordem_dose_paciente"] == 2].set_index("paciente")
    par = d1[["data_vacinacao", "idade_paciente"]].join(d2[["data_vacinacao"]], rsuffix="_2", how="inner")
    par = pd.DataFrame({
        "idade_primeira_dose": par["idade_paciente"],
        "intervalo_dias": (par["data_vacinacao_2"] - par["data_vacinacao"]).dt.days.astype("Int32"),
    })
    return (par.groupby(["idade_primeira_dose", "intervalo_dias"], dropna=False, as_index=False)
               .size().rename(columns={"size": "pacientes"}))


def salvar(nome: str, tabela: pd.DataFrame) -> None:
    """Grava a tabela em GOLD_DIR como .parquet (zstd) e .csv (UTF-8). Categorias voltam a ser texto."""
    tabela = tabela.reset_index(drop=True)
    for coluna in tabela.columns[tabela.dtypes == "category"]:
        tabela[coluna] = tabela[coluna].astype("string")
    tabela.to_parquet(GOLD_DIR / f"{nome}.parquet", index=False, compression="zstd")
    tabela.to_csv(GOLD_DIR / f"{nome}.csv", index=False, encoding="utf-8")
    print(f"{nome}: {len(tabela):,} linhas")


def main() -> None:
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    df, tipos_silver = ler_silver()
    df["dose_grupo"] = classificar_dose(df)
    df["faixa_atraso"] = pd.cut(df["atraso_registro_dias"].astype(float), FAIXAS_ATRASO,
                                labels=ROTULOS_ATRASO).astype("string")
    dim = pd.read_csv(DIM_MUNICIPIOS)
    salvar("dim_municipios", dim)

    # Série diária nacional
    dia = contar(df, ["data_vacinacao", "ano_mes", "dose_grupo", "vacina_tipo"], dropna=True)
    salvar("gold_doses_dia", dia)

    # UF x mês x vacina x dose
    uf = (df.groupby(["ano_mes", "uf_paciente", "vacina_tipo", "dose_grupo"], dropna=False, as_index=False, observed=True)
            .size().rename(columns={"size": "doses"}))
    salvar("gold_doses_uf_mes", uf)

    # Município (residência do paciente) x mês
    mun = (df.assign(d1=df["dose_grupo"].eq("1ª dose"), d2=df["dose_grupo"].eq("2ª dose"),
                     crianca_1a4=df["idade_paciente"].between(1, 4))
             .groupby(["codigo_municipio_paciente", "ano_mes"], as_index=False, observed=True)
             .agg(doses=("d1", "size"), doses_d1=("d1", "sum"), doses_d2=("d2", "sum"),
                  doses_criancas_1a4=("crianca_1a4", "sum"),
                  pacientes_unicos=("codigo_paciente_anonimizado", "nunique")))
    mun["codigo_municipio"] = pd.to_numeric(mun["codigo_municipio_paciente"].astype("string"))
    mun = mun.merge(dim, on="codigo_municipio", how="left").drop(columns=["codigo_municipio"])
    salvar("gold_municipio_mes", mun)

    # Perfil demográfico
    perfil = contar(df, ["ano_mes", "uf_paciente", "sexo_paciente", "faixa_etaria", "raca_cor_paciente",
                         "vacina_tipo", "dose_grupo"])
    salvar("gold_perfil", perfil)

    # Idade simples x dose (sem limite superior; idade ausente fica de fora, ver gold_resumo_geral)
    idade = contar(df, ["ano_mes", "idade_paciente", "dose_grupo", "vacina_tipo"], dropna=True)
    salvar("gold_idade_dose", idade)

    # Coorte de crianças de 1 a 4 anos (idade mais recente do paciente): quantas receberam 1 e 2 doses
    criancas = df[df["idade_paciente"].between(1, 4)]
    por_crianca = (criancas.groupby(criancas["codigo_paciente_anonimizado"].cat.codes)
                   .agg(codigo_municipio_paciente=("codigo_municipio_paciente", "last"),
                        uf_paciente=("uf_paciente", "last"),
                        doses=("data_vacinacao", "nunique"), idade=("idade_paciente", "max")))
    coorte = (por_crianca.assign(com_1_dose=True, com_2_ou_mais=por_crianca["doses"] >= 2)
              .groupby(["uf_paciente", "codigo_municipio_paciente"], dropna=False, as_index=False, observed=True)
              .agg(criancas_vacinadas=("com_1_dose", "sum"), criancas_com_2_ou_mais_doses=("com_2_ou_mais", "sum")))
    coorte["codigo_municipio"] = pd.to_numeric(coorte["codigo_municipio_paciente"].astype("string"))
    coorte = coorte.merge(dim[["codigo_municipio", "municipio"]], on="codigo_municipio", how="left")
    coorte["prop_com_2_ou_mais"] = (coorte["criancas_com_2_ou_mais_doses"] / coorte["criancas_vacinadas"]).round(4)
    salvar("gold_coorte_criancas_municipio", coorte.drop(columns=["codigo_municipio"]))
    del criancas, por_crianca

    # Qualidade: atraso do registro no RNDS
    atraso = (df.groupby(["ano_mes", "uf_paciente", "faixa_atraso"], dropna=False, as_index=False, observed=True)
                .size().rename(columns={"size": "doses"}))
    salvar("gold_atraso_registro", atraso)

    # Onde e por qual estratégia a dose foi aplicada
    estab = (df.groupby(["ano_mes", "uf_estabelecimento", "tipo_estabelecimento", "natureza_estabelecimento",
                         "estrategia_vacinacao"], dropna=False, as_index=False, observed=True)
               .size().rename(columns={"size": "doses"}))
    salvar("gold_estabelecimento", estab)

    # KPIs mensais
    kpi = df.groupby("ano_mes", observed=True).agg(
        doses=("dose_grupo", "size"), pacientes_unicos=("codigo_paciente_anonimizado", "nunique"),
        pct_criancas_1a4=("idade_paciente", lambda s: round(100 * s.between(1, 4).mean(), 2)),
        pct_rotina=("estrategia_vacinacao", lambda s: round(100 * s.eq("Rotina").mean(), 2)),
        mediana_atraso_dias=("atraso_registro_dias", "median"),
        pct_registro_ate_7d=("atraso_registro_dias", lambda s: round(100 * (s <= 7).mean(), 2)),
        ufs=("uf_paciente", "nunique"), municipios=("codigo_municipio_paciente", "nunique"),
    ).reset_index()
    salvar("gold_kpis_mensais", kpi)

    # ---------------------------------------------------------------- detalhe e qualidade
    por_paciente = df.groupby("codigo_paciente_anonimizado", observed=True).size()
    atraso_dias = df["atraso_registro_dias"]
    idade_pac = df["idade_paciente"]
    resumo = pd.DataFrame([{
        "doses": len(df),
        "pacientes_distintos": por_paciente.size,
        "meses": df["ano_mes"].nunique(),
        "primeiro_mes": df["ano_mes"].min(), "ultimo_mes": df["ano_mes"].max(),
        "data_vacinacao_min": df["data_vacinacao"].min(), "data_vacinacao_max": df["data_vacinacao"].max(),
        "municipios_residencia": df["codigo_municipio_paciente"].nunique(),
        "estabelecimentos": df["codigo_cnes_estabelecimento"].nunique(),
        "etnias_indigenas": df["etnia_indigena_paciente"].nunique(),
        "vacinacao_fora_do_mes": int(df["vacinacao_fora_do_mes"].sum()),
        "atraso_negativo": int((atraso_dias < 0).sum()),
        "atraso_ausente": int(atraso_dias.isna().sum()),
        "idade_ausente": int(idade_pac.isna().sum()),
        "idade_maior_100": int((idade_pac > 100).sum()), "idade_maior_110": int((idade_pac > 110).sum()),
        "pacientes_mais_10_doses": int((por_paciente > 10).sum()),
        "doses_pacientes_mais_10_doses": int(por_paciente[por_paciente > 10].sum()),
    }])
    salvar("gold_resumo_geral", resumo)
    salvar("gold_qualidade_colunas", qualidade_colunas(df.drop(columns=["dose_grupo", "faixa_atraso"]), tipos_silver))

    funil = pd.DataFrame(json.loads(RESUMO_PROCESSAMENTO.read_text(encoding="utf-8"))).T
    salvar("gold_funil_processamento", funil.rename_axis("ano_mes").reset_index())

    salvar("gold_doses_por_paciente",
           por_paciente.value_counts().sort_index().rename_axis("doses_na_janela").rename("pacientes").reset_index())
    salvar("gold_dose_descricao_ordem", contar(
        df.assign(ordem_dose=df["ordem_dose_paciente"].clip(upper=4)), ["ano_mes", "descricao_dose_vacina", "ordem_dose"]))
    salvar("gold_atraso_dias", contar(df, ["atraso_registro_dias"], dropna=True))
    salvar("gold_intervalo_doses", intervalo_entre_doses(df))
    salvar("gold_estrategia_faixa", contar(df, ["ano_mes", "faixa_etaria", "tipo_estabelecimento",
                                                "natureza_estabelecimento", "estrategia_vacinacao"]))
    salvar("gold_categoria_atendimento", contar(df, ["ano_mes", "categoria_atendimento"]))
    salvar("gold_nacionalidade_etnia", contar(df, ["nacionalidade_paciente", "etnia_indigena_paciente"]))
    salvar("gold_fluxo_uf", contar(df, ["uf_paciente", "uf_estabelecimento"]))
    salvar("gold_estabelecimento_cnes", contar(df, ["codigo_cnes_estabelecimento", "uf_estabelecimento",
                                                    "tipo_estabelecimento", "natureza_estabelecimento"]))
    if "descricao_vacina" not in df.columns:
        raise SystemExit("A silver não tem descricao_vacina/fabricante_vacina: rode de novo o passo 07.")
    salvar("gold_vacina_fabricante", contar(df, ["ano_mes", "descricao_vacina", "sigla_vacina", "vacina_tipo",
                                                 "fabricante_vacina"]))


if __name__ == "__main__":
    main()
