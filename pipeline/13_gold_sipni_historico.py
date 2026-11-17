"""Passo 13 (gold) - SI-PNI histórico (1994-2019) e série anual consolidada da vacinação contra sarampo.

Entrada: data/silver/sipni_historico/sipni_doses_aplicadas_agregado_{AAAA}.csv  (passo 06, DPNI)
         data/silver/sipni_historico/sipni_cobertura_vacinal_{AAAA}.csv         (passo 06, CPNI)
         data/silver/sipni_doses/vacinacao_sarampo_sipni.parquet                (passo 07, nominal 2020+)

Lê os arquivos POR ANO, e não os combinados *_1994_2019.csv: o layout das duas bases muda no
meio da série e o combinado usa o cabeçalho do primeiro ano para todos.
    DPNI (doses)     1994-2003: anual, 7 colunas    | 2004-2019: mensal (ano_mes), 12 colunas
    CPNI (cobertura) 1994-2012: com faixa etária e dose (FX_ETARIA, DOSE), decimal com ponto
                     2013-2019: sem faixa nem dose (o código já diz a dose), decimal com vírgula
O código de município vem com 7 dígitos (com verificador) até 2012 e com 6 depois; aqui fica
sempre com 6, como na base nominal e na dim_municipios.

Só entram as vacinas com componente de sarampo. Os códigos foram conferidos contra os números
conhecidos da série (campanhas de 1997, 2004, 2008 e 2014; coberturas de SCR D1 em ~90-110%).
Rubéola monovalente (DPNI 17) fica de fora; a "Tetravalente" DTP/Hib (DPNI 26) também.

Avisos de qualidade, refletidos em gold_serie_fontes:
    - 2019 está incompleto (o SI-PNI agregado foi descontinuado na migração para o RNDS);
    - se a base nominal for baixada a partir de um ano depois de 2020
      (SARAMPO_ANO_INICIAL_SIPNI_DOSES), os anos do meio ficam como lacuna;
    - o ano corrente é parcial.

Saída: data/gold/sipni_historico/
    gold_hist_doses_municipio_ano     ano x município x imunobiológico x dose (DPNI 1994-2019)
    gold_hist_doses_uf_mes            mês x UF x tipo de vacina (DPNI 2004-2019, que é mensal)
    gold_hist_cobertura_municipio_ano ano x município x imunobiológico x dose x faixa (CPNI)
    gold_hist_cobertura_d1_uf_ano     cobertura da 1ª dose contra sarampo por UF e ano (indicador único)
                                      (D2: o CPNI só publica a cobertura da 2ª dose a partir de 2013,
                                      código 098, que está na gold_hist_cobertura_municipio_ano)
    gold_serie_anual_doses_uf         ano x UF x tipo de vacina, 1994-2019 (DPNI) + 2020+ (nominal)
    gold_serie_fontes                 ano x fonte, granularidade e situação dos dados (1994-hoje)
Uso:   python pipeline/13_gold_sipni_historico.py
"""

import json

import pandas as pd
import pyarrow.parquet as pq

import config

GOLD_DIR = config.GOLD / "sipni_historico"
ANOS = range(1994, 2020)
LINHAS_CHUNK = 2_000_000

# DPNI (doses aplicadas): código do imunobiológico -> (descrição, tipo de vacina). Os nomes
# dos tipos são os mesmos de VACINA_TIPO no passo 07, para a série juntar as duas fontes.
SCR, SR, SCRV, MONO = "Tríplice viral (SCR)", "Dupla viral (SR)", "Tetra viral (SCRV)", "Monovalente"
IMUNO_DOSES = {
    "18": ("Sarampo", MONO),
    "21": ("Tríplice Viral (SCR)", SCR),
    "23": ("Dupla Viral (rotina) (SR)", SR),
    "24": ("Tríplice Viral (implantação) (SRC)", SCR),
    "25": ("Tríplice Viral (seguimento) (SRC)", SCR),
    "55": ("Dupla Viral (mulheres idade fértil) (SR)", SR),
    "56": ("Tríplice Viral (campanha) (SCR)", SCR),
    "57": ("Tríplice Viral (mulheres idade fértil) (SCR)", SCR),
    "65": ("Tríplice Viral (mulheres idade fértil camp) (SCR)", SCR),
    "66": ("Tríplice Viral (homens campanha) (SCR)", SCR),
    "68": ("Dupla Viral (mulheres idade fértil campanha) (SR)", SR),
    "69": ("Dupla Viral (homens campanha) (SR)", SR),
    "70": ("Tríplice Viral (homens) (SCR)", SCR),
    "71": ("Dupla Viral (homens) (SR)", SR),
    "89": ("Tetraviral (sarampo, rubéola, caxumba e varicela)", SCRV),
    "97": ("Quádrupla viral", SCRV),
}
DOSE_DPNI = {
    "01": "1ª dose", "02": "2ª dose", "03": "3ª dose", "04": "Dose única", "05": "1º reforço",
    "06": "2º reforço", "07": "4ª dose", "08": "Dose", "09": "Dose única", "10": "Revacinação",
    "32": "1ª dose", "33": "2ª dose", "34": "3ª dose", "35": "4ª dose", "36": "Dose inicial",
    "37": "Dose adicional",
}

# CPNI (cobertura): mesmo sistema de códigos nos dois layouts (conferido pelos valores).
IMUNO_COBERTURA = {
    "018": "Sarampo (monovalente)",
    "021": "Tríplice Viral (SCR)",      # a partir de 2013 é só a D1
    "098": "Tríplice Viral (SCR) D2",   # só 2013+
    "097": "Tetra Viral (SCR+VZ)",      # só 2013+
}


def indicador_d1(ano: int, codigo: str, dose: str) -> bool:
    """Linha que representa a cobertura da 1ª dose contra sarampo naquele ano (uma por
    município). Escolha analítica, conferida pela cobertura nacional de cada código:
        1994-2002  monovalente (018, dose 01): a SCR ainda estava em implantação nos estados
        2003       SCR (021, dose 01): ano da troca, o 018 cai para ~4%
        2004-2012  SCR (021, dose D1): de 2006 a 2011 há também 021/01, com outra população-alvo
        2013-2019  SCR D1 (021: o layout novo não tem coluna de dose)"""
    if ano <= 2002:
        return codigo == "018" and dose == "01"
    if ano == 2003:
        return codigo == "021" and dose == "01"
    if ano <= 2012:
        return codigo == "021" and dose == "D1"
    return codigo == "021"


def municipio_6_digitos(codigo: pd.Series) -> pd.Series:
    """7 dígitos (com verificador, até 2012) -> 6; os de 6 ficam como estão."""
    codigo = codigo.str.strip()
    return codigo.where(codigo.str.len() != 7, codigo.str[:6]).astype("string")


def numero(serie: pd.Series) -> pd.Series:
    """Número com ponto ou vírgula decimal (o CPNI 2013+ usa vírgula)."""
    return pd.to_numeric(serie.str.replace(",", ".", regex=False), errors="coerce")


def salvar(nome: str, tabela: pd.DataFrame) -> None:
    tabela.to_parquet(GOLD_DIR / f"{nome}.parquet", index=False, compression="zstd")
    tabela.to_csv(GOLD_DIR / f"{nome}.csv", index=False, encoding="utf-8", lineterminator="\n")
    print(f"{nome}: {len(tabela):,} linhas")


def ler_doses() -> tuple[pd.DataFrame, pd.DataFrame]:
    """DPNI, ano a ano em pedaços, só as vacinas com sarampo. Devolve (por município x ano,
    por UF x mês)."""
    por_municipio, por_mes = [], []
    for ano in ANOS:
        arquivo = config.SILVER_SIPNI_HISTORICO / f"sipni_doses_aplicadas_agregado_{ano}.csv"
        colunas = pd.read_csv(arquivo, nrows=0).columns
        usar = ["codigo_uf", "codigo_municipio", "codigo_imunobiologico", "codigo_dose", "doses_aplicadas"]
        if "ano_mes" in colunas:
            usar.append("ano_mes")
        for chunk in pd.read_csv(arquivo, dtype=str, usecols=usar, chunksize=LINHAS_CHUNK):
            chunk = chunk[chunk["codigo_imunobiologico"].isin(IMUNO_DOSES.keys())].copy()
            if chunk.empty:
                continue
            chunk["ano"] = ano
            chunk["codigo_municipio"] = municipio_6_digitos(chunk["codigo_municipio"])
            chunk["doses_aplicadas"] = numero(chunk["doses_aplicadas"]).fillna(0).astype("int64")
            chunk["vacina_tipo"] = chunk["codigo_imunobiologico"].map(lambda c: IMUNO_DOSES[c][1])
            por_municipio.append(chunk.groupby(
                ["ano", "codigo_uf", "codigo_municipio", "codigo_imunobiologico", "codigo_dose"],
                as_index=False)["doses_aplicadas"].sum())
            if "ano_mes" in chunk:
                por_mes.append(chunk.groupby(["ano_mes", "codigo_uf", "vacina_tipo"], as_index=False)["doses_aplicadas"].sum())
        print(f"  DPNI {ano} lido", flush=True)

    chaves = ["ano", "codigo_uf", "codigo_municipio", "codigo_imunobiologico", "codigo_dose"]
    mun = pd.concat(por_municipio).groupby(chaves, as_index=False)["doses_aplicadas"].sum()
    mun = mun[mun["doses_aplicadas"] != 0]
    mun["imunobiologico"] = mun["codigo_imunobiologico"].map(lambda c: IMUNO_DOSES[c][0])
    mun["vacina_tipo"] = mun["codigo_imunobiologico"].map(lambda c: IMUNO_DOSES[c][1])
    mun["dose"] = mun["codigo_dose"].map(DOSE_DPNI).fillna("Outra")
    mun = mun[chaves[:4] + ["imunobiologico", "vacina_tipo", "codigo_dose", "dose", "doses_aplicadas"]]

    mes = pd.concat(por_mes).groupby(["ano_mes", "codigo_uf", "vacina_tipo"], as_index=False)["doses_aplicadas"].sum()
    mes["ano_mes"] = mes["ano_mes"].str[:4] + "-" + mes["ano_mes"].str[4:6]
    return mun.sort_values(chaves).reset_index(drop=True), mes.sort_values(["ano_mes", "codigo_uf"]).reset_index(drop=True)


def ler_cobertura() -> pd.DataFrame:
    """CPNI, ano a ano, só as vacinas com sarampo, nos dois layouts."""
    partes = []
    for ano in ANOS:
        df = pd.read_csv(config.SILVER_SIPNI_HISTORICO / f"sipni_cobertura_vacinal_{ano}.csv", dtype=str)
        df = df[df["codigo_imunobiologico"].isin(IMUNO_COBERTURA.keys())].copy()
        partes.append(pd.DataFrame({
            "ano": ano,
            "codigo_uf": df["codigo_uf"],
            "codigo_municipio": municipio_6_digitos(df["codigo_municipio"]),
            "codigo_imunobiologico": df["codigo_imunobiologico"],
            "imunobiologico": df["codigo_imunobiologico"].map(IMUNO_COBERTURA),
            "dose_original": df["DOSE"] if "DOSE" in df else pd.NA,
            "faixa_etaria_original": df["FX_ETARIA"] if "FX_ETARIA" in df else pd.NA,
            "doses_aplicadas": numero(df["doses_aplicadas"]),
            "populacao_alvo": numero(df["populacao_alvo"]),
            "cobertura_vacinal_percentual": numero(df["cobertura_vacinal_percentual"]),
        }))
    cob = pd.concat(partes, ignore_index=True)
    cob["indicador_d1_sarampo"] = [
        indicador_d1(a, c, d if isinstance(d, str) else "")
        for a, c, d in zip(cob["ano"], cob["codigo_imunobiologico"], cob["dose_original"])
    ]
    for coluna in ["codigo_uf", "codigo_municipio", "codigo_imunobiologico", "imunobiologico",
                   "dose_original", "faixa_etaria_original"]:
        cob[coluna] = cob[coluna].astype("string")
    return cob


def cobertura_d1_uf(cob: pd.DataFrame, uf_sigla: dict[str, str]) -> pd.DataFrame:
    """Cobertura agregada por UF e Brasil, recalculada (soma das doses / soma da população),
    só com as linhas do indicador de 1ª dose."""
    d1 = cob[cob["indicador_d1_sarampo"]]
    uf = d1.groupby(["ano", "codigo_uf"], as_index=False)[["doses_aplicadas", "populacao_alvo"]].sum()
    br = d1.groupby("ano", as_index=False)[["doses_aplicadas", "populacao_alvo"]].sum().assign(codigo_uf="00")
    tab = pd.concat([uf, br], ignore_index=True)
    tab["uf"] = tab["codigo_uf"].map(uf_sigla).where(tab["codigo_uf"] != "00", "BR")
    tab["imunobiologico"] = tab["ano"].map(lambda a: IMUNO_COBERTURA["018" if a <= 2002 else "021"])
    tab["cobertura_d1_percentual"] = (100 * tab["doses_aplicadas"] / tab["populacao_alvo"]).round(2)
    return tab[["ano", "codigo_uf", "uf", "imunobiologico", "doses_aplicadas", "populacao_alvo",
                "cobertura_d1_percentual"]].sort_values(["ano", "codigo_uf"]).reset_index(drop=True)


def doses_nominais_por_ano() -> pd.DataFrame:
    """Base nominal (2020+): doses por ano da vacinação x UF de aplicação x tipo de vacina,
    para ficar comparável ao DPNI (que conta onde a dose foi aplicada). Agregado no duckdb:
    a silver 2020+ não cabe na memória."""
    import duckdb
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{config.DUCKDB_MEMORIA}'")
    silver = config.SILVER_SIPNI_DOSES / "vacinacao_sarampo_sipni.parquet"
    # Só os anos cobertos pelo download: doses de anos anteriores registradas com atraso (e
    # datas digitadas erradas, ex.: 1900) ficariam com o ano incompleto e ficam fora da série.
    tabela = con.sql(f"""
        SELECT year(data_vacinacao)::BIGINT AS ano, uf_estabelecimento AS uf, vacina_tipo,
               count(*) AS doses_aplicadas
        FROM read_parquet('{silver}')
        WHERE data_vacinacao IS NOT NULL AND year(data_vacinacao) >= {config.ANO_INICIAL_SIPNI_DOSES}
          AND uf_estabelecimento IS NOT NULL AND vacina_tipo IS NOT NULL
        GROUP BY ALL ORDER BY ALL""").df()
    con.close()
    return tabela


def main() -> None:
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    uf_sigla = {str(u["id"]): u["sigla"] for u in json.loads((config.BRONZE_IBGE / "uf_meta.json").read_text(encoding="utf-8"))}

    mun, mes = ler_doses()
    salvar("gold_hist_doses_municipio_ano", mun)
    mes["uf"] = mes["codigo_uf"].map(uf_sigla).fillna("Ignorada")
    salvar("gold_hist_doses_uf_mes", mes[["ano_mes", "codigo_uf", "uf", "vacina_tipo", "doses_aplicadas"]])

    cob = ler_cobertura()
    salvar("gold_hist_cobertura_municipio_ano", cob)
    salvar("gold_hist_cobertura_d1_uf_ano", cobertura_d1_uf(cob, uf_sigla))

    # Série anual: DPNI (1994-2019) + nominal (2020+), na mesma granularidade.
    hist = mun.groupby(["ano", "codigo_uf", "vacina_tipo"], as_index=False)["doses_aplicadas"].sum()
    hist["uf"] = hist["codigo_uf"].map(uf_sigla).fillna("Ignorada")  # 00 = UF ignorada (poucas dezenas de doses)
    hist["fonte"] = "SI-PNI agregado (DPNI)"
    nominal = doses_nominais_por_ano()
    nominal["fonte"] = "SI-PNI/RNDS nominal"
    serie = pd.concat([hist[["ano", "uf", "vacina_tipo", "doses_aplicadas", "fonte"]], nominal], ignore_index=True)
    serie["ano"] = serie["ano"].astype(int)
    salvar("gold_serie_anual_doses_uf", serie.sort_values(["ano", "uf", "vacina_tipo"]).reset_index(drop=True))

    # Uma linha por ano, de 1994 até hoje, dizendo de onde vem o dado e se ele está completo.
    hoje = config.DATA_CORTE.year
    anos_nominais = set(nominal["ano"].astype(int))
    fontes = []
    for ano in range(ANOS.start, hoje + 1):
        if ano in ANOS:
            fonte, grao = "SI-PNI agregado (DPNI + CPNI)", "município x ano" + (" x mês" if ano >= 2004 else "")
            situacao = "incompleto: SI-PNI agregado descontinuado durante 2019" if ano == 2019 else "completo"
        elif ano in anos_nominais:
            fonte, grao = "SI-PNI/RNDS nominal", "dose individual"
            situacao = "parcial: ano corrente" if ano == hoje else "completo"
        else:
            fonte, grao, situacao = None, None, "lacuna: base nominal não baixada (passo 03)"
        fontes.append({"ano": ano, "fonte": fonte, "granularidade": grao, "situacao": situacao,
                       "tem_doses": ano in ANOS or ano in anos_nominais,
                       "tem_cobertura": ano in ANOS})
    salvar("gold_serie_fontes", pd.DataFrame(fontes))


if __name__ == "__main__":
    main()
