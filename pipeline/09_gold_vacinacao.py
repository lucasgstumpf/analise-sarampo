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

Como a silver não cabe mais na memória (série 2020+), as agregações são consultas SQL do
duckdb sobre o parquet, com as mesmas regras da versão em pandas:
    - "dropna=False": os vazios formam um grupo próprio; "dropna=True": linhas com vazio em
      alguma chave ficam de fora;
    - médias de colunas com vazio (idade, atraso) ignoram os vazios, como o pandas;
    - arredondamentos com np.round (metade para o par), como o pandas.
As linhas saem ordenadas pelas chaves (vazios no fim).

Saída: data/gold/vacinacao/{tabela}.{parquet,csv}
Uso:   python pipeline/09_gold_vacinacao.py
"""

import json
import shutil

import duckdb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

import config

SILVER = config.SILVER_SIPNI_DOSES / "vacinacao_sarampo_sipni.parquet"
DIM_MUNICIPIOS = config.SILVER_SIPNI_DOSES / "dim_municipios.csv"
RESUMO_PROCESSAMENTO = config.SILVER_SIPNI_DOSES_AUDITORIA / "processamento_resumo.json"
GOLD_DIR = config.GOLD_VACINACAO
TMP_DIR = config.DUCKDB_TMP / "09"

# Dose como aparece no cartão: o número da descrição; quando a descrição é só "Dose" (sem
# número), a ordem da dose do paciente na janela (até 3); reforços/adicionais ficam à parte.
DOSE_GRUPO = """
    CASE
        WHEN coalesce(regexp_matches(descricao_dose_vacina, 'Refor|Adicional|Revacina'), false)
             AND dose_numero IS NULL THEN 'Reforço/adicional'
        ELSE CASE coalesce(dose_numero::INTEGER, least(ordem_dose_paciente, 3))
            WHEN 0 THEN 'Dose zero' WHEN 1 THEN '1ª dose' WHEN 2 THEN '2ª dose'
            WHEN 3 THEN '3ª dose ou mais' WHEN 4 THEN '3ª dose ou mais' END
    END"""
# pd.cut(atraso, [-1, 0, 7, 30, 90, inf]): intervalos fechados à direita.
FAIXA_ATRASO = """
    CASE
        WHEN atraso_registro_dias IS NULL OR atraso_registro_dias <= -1 THEN NULL
        WHEN atraso_registro_dias <= 0 THEN 'Mesmo dia'
        WHEN atraso_registro_dias <= 7 THEN '1-7 dias'
        WHEN atraso_registro_dias <= 30 THEN '8-30 dias'
        WHEN atraso_registro_dias <= 90 THEN '31-90 dias'
        ELSE '> 90 dias'
    END"""


def conectar() -> duckdb.DuckDBPyConnection:
    shutil.rmtree(TMP_DIR, ignore_errors=True)
    TMP_DIR.mkdir(parents=True)
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{config.DUCKDB_MEMORIA}'")
    con.execute(f"SET temp_directory='{TMP_DIR}'")
    con.execute("SET max_temp_directory_size='200GiB'")
    # `linha` = posição na silver (ordem por data), para "o último valor" e "o primeiro exemplo".
    con.execute(f"""
        CREATE VIEW s AS
        SELECT *, file_row_number AS linha,
               {DOSE_GRUPO} AS dose_grupo,
               {FAIXA_ATRASO} AS faixa_atraso
        FROM read_parquet('{SILVER}', file_row_number=true)""")
    return con


def para_pandas(tabela: pa.Table) -> pd.DataFrame:
    """Inteiros com vazio continuam inteiros (Int64) e texto vira 'string', como antes."""
    mapa = {pa.int8(): pd.Int8Dtype(), pa.int16(): pd.Int16Dtype(), pa.int32(): pd.Int32Dtype(),
            pa.int64(): pd.Int64Dtype(), pa.string(): pd.StringDtype(), pa.large_string(): pd.StringDtype()}
    return tabela.to_pandas(types_mapper=mapa.get)


def consulta(con, sql: str) -> pd.DataFrame:
    return para_pandas(con.sql(sql).to_arrow_table())


def contar(con, colunas: list[str], dropna: bool = False, origem: str = "s") -> pd.DataFrame:
    """Nº de doses (linhas da silver) por combinação de `colunas`."""
    chaves = ", ".join(colunas)
    filtro = ("WHERE " + " AND ".join(f"{c} IS NOT NULL" for c in colunas)) if dropna else ""
    ordem = ", ".join(f"{c} NULLS LAST" for c in colunas)
    return consulta(con, f"SELECT {chaves}, count(*) AS doses FROM {origem} {filtro} GROUP BY ALL ORDER BY {ordem}")


def salvar(nome: str, tabela: pd.DataFrame) -> None:
    """Grava a tabela em GOLD_DIR como .parquet (zstd) e .csv (UTF-8)."""
    tabela = tabela.reset_index(drop=True)
    tabela.to_parquet(GOLD_DIR / f"{nome}.parquet", index=False, compression="zstd")
    tabela.to_csv(GOLD_DIR / f"{nome}.csv", index=False, encoding="utf-8", lineterminator="\n")
    print(f"{nome}: {len(tabela):,} linhas", flush=True)


def municipio_mes(con, dim: pd.DataFrame) -> pd.DataFrame:
    mun = consulta(con, """
        SELECT codigo_municipio_paciente, ano_mes, count(*) AS doses,
               count(*) FILTER (WHERE dose_grupo = '1ª dose') AS doses_d1,
               count(*) FILTER (WHERE dose_grupo = '2ª dose') AS doses_d2,
               count(*) FILTER (WHERE idade_paciente BETWEEN 1 AND 4) AS doses_criancas_1a4,
               count(DISTINCT codigo_paciente_anonimizado) AS pacientes_unicos
        FROM s WHERE codigo_municipio_paciente IS NOT NULL
        GROUP BY ALL ORDER BY codigo_municipio_paciente, ano_mes""")
    mun["codigo_municipio"] = pd.to_numeric(mun["codigo_municipio_paciente"])
    return mun.merge(dim, on="codigo_municipio", how="left").drop(columns=["codigo_municipio"])


def coorte_criancas(con, dim: pd.DataFrame) -> pd.DataFrame:
    """Crianças de 1 a 4 anos: município/UF da dose mais recente com valor, nº de datas de dose."""
    coorte = consulta(con, """
        WITH por_crianca AS (
            SELECT codigo_paciente_anonimizado,
                   arg_max(codigo_municipio_paciente, linha) FILTER (WHERE codigo_municipio_paciente IS NOT NULL)
                       AS codigo_municipio_paciente,
                   arg_max(uf_paciente, linha) FILTER (WHERE uf_paciente IS NOT NULL) AS uf_paciente,
                   count(DISTINCT data_vacinacao) AS doses
            FROM s WHERE idade_paciente BETWEEN 1 AND 4
            GROUP BY codigo_paciente_anonimizado)
        SELECT uf_paciente, codigo_municipio_paciente, count(*) AS criancas_vacinadas,
               count(*) FILTER (WHERE doses >= 2) AS criancas_com_2_ou_mais_doses
        FROM por_crianca GROUP BY ALL
        ORDER BY uf_paciente NULLS LAST, codigo_municipio_paciente NULLS LAST""")
    coorte["codigo_municipio"] = pd.to_numeric(coorte["codigo_municipio_paciente"])
    coorte = coorte.merge(dim[["codigo_municipio", "municipio"]], on="codigo_municipio", how="left")
    coorte["prop_com_2_ou_mais"] = (coorte["criancas_com_2_ou_mais_doses"] / coorte["criancas_vacinadas"]).round(4)
    return coorte.drop(columns=["codigo_municipio"])


def kpis_mensais(con) -> pd.DataFrame:
    kpi = consulta(con, """
        SELECT ano_mes, count(*) AS doses, count(DISTINCT codigo_paciente_anonimizado) AS pacientes_unicos,
               (count(*) FILTER (WHERE idade_paciente BETWEEN 1 AND 4))::DOUBLE / count(idade_paciente) AS crianca,
               (count(*) FILTER (WHERE estrategia_vacinacao = 'Rotina'))::DOUBLE / count(*) AS rotina,
               quantile_cont(atraso_registro_dias, 0.5) AS mediana_atraso_dias,
               (count(*) FILTER (WHERE atraso_registro_dias <= 7))::DOUBLE / count(atraso_registro_dias) AS ate_7d,
               count(DISTINCT uf_paciente) AS ufs, count(DISTINCT codigo_municipio_paciente) AS municipios
        FROM s GROUP BY ano_mes ORDER BY ano_mes""")
    for nova, antiga in [("pct_criancas_1a4", "crianca"), ("pct_rotina", "rotina"), ("pct_registro_ate_7d", "ate_7d")]:
        kpi[nova] = np.round(100 * kpi.pop(antiga).astype(float), 2)
    return kpi[["ano_mes", "doses", "pacientes_unicos", "pct_criancas_1a4", "pct_rotina", "mediana_atraso_dias",
                "pct_registro_ate_7d", "ufs", "municipios"]]


def resumo_geral(con) -> pd.DataFrame:
    return consulta(con, """
        WITH pp AS (SELECT count(*) AS n FROM s WHERE codigo_paciente_anonimizado IS NOT NULL
                    GROUP BY codigo_paciente_anonimizado)
        SELECT (SELECT count(*) FROM s) AS doses,
               (SELECT count(*) FROM pp) AS pacientes_distintos,
               count(DISTINCT ano_mes) AS meses, min(ano_mes) AS primeiro_mes, max(ano_mes) AS ultimo_mes,
               min(data_vacinacao) AS data_vacinacao_min, max(data_vacinacao) AS data_vacinacao_max,
               count(DISTINCT codigo_municipio_paciente) AS municipios_residencia,
               count(DISTINCT codigo_cnes_estabelecimento) AS estabelecimentos,
               count(DISTINCT etnia_indigena_paciente) AS etnias_indigenas,
               count(*) FILTER (WHERE vacinacao_fora_do_mes) AS vacinacao_fora_do_mes,
               count(*) FILTER (WHERE atraso_registro_dias < 0) AS atraso_negativo,
               count(*) FILTER (WHERE atraso_registro_dias IS NULL) AS atraso_ausente,
               count(*) FILTER (WHERE idade_paciente IS NULL) AS idade_ausente,
               count(*) FILTER (WHERE idade_paciente > 100) AS idade_maior_100,
               count(*) FILTER (WHERE idade_paciente > 110) AS idade_maior_110,
               (SELECT count(*) FROM pp WHERE n > 10) AS pacientes_mais_10_doses,
               (SELECT coalesce(sum(n), 0) FROM pp WHERE n > 10)::BIGINT AS doses_pacientes_mais_10_doses
        FROM s""")


def qualidade_colunas(con) -> pd.DataFrame:
    """Uma linha por coluna da silver: tipo (como está no parquet), % vazio, nº de valores
    distintos e o valor mais frequente (para colunas com até 5.000 valores distintos)."""
    schema = pq.read_schema(SILVER)
    total = con.execute("SELECT count(*) FROM s").fetchall()[0][0]
    linhas = []
    for campo in schema:
        c = campo.name
        nao_nulos, unicos, exemplo = con.execute(
            f"SELECT count({c}), count(DISTINCT {c}), arg_min({c}, linha) FILTER (WHERE {c} IS NOT NULL) FROM s").fetchall()[0]
        frequente = pct_frequente = None
        if unicos and unicos <= 5000:
            valor, n = con.execute(
                f"SELECT {c}, count(*) AS n FROM s WHERE {c} IS NOT NULL GROUP BY 1 ORDER BY n DESC, 1 LIMIT 1").fetchall()[0]
            frequente, pct_frequente = str(valor), round(100 * n / nao_nulos, 2)
        linhas.append({
            "coluna": c, "tipo": str(campo.type), "pct_nulos": round(100 * (total - nao_nulos) / total, 4),
            "unicos": unicos, "mais_frequente": frequente, "pct_mais_frequente": pct_frequente,
            "exemplo": None if exemplo is None else str(exemplo),
        })
    return pd.DataFrame(linhas)


def intervalo_entre_doses(con) -> pd.DataFrame:
    """Para pacientes com 2 a 10 doses na janela: dias entre a 1ª e a 2ª dose e idade na 1ª.
    (Mais de 10 doses indica provável colisão do identificador anonimizado.)"""
    return consulta(con, """
        WITH base AS (SELECT codigo_paciente_anonimizado AS p, ordem_dose_paciente AS o, data_vacinacao, idade_paciente
                      FROM s WHERE doses_paciente_janela BETWEEN 2 AND 10 AND ordem_dose_paciente <= 2)
        SELECT d1.idade_paciente AS idade_primeira_dose,
               floor(epoch(d2.data_vacinacao - d1.data_vacinacao) / 86400)::INTEGER AS intervalo_dias,
               count(*) AS pacientes
        FROM (SELECT * FROM base WHERE o = 1) d1 JOIN (SELECT * FROM base WHERE o = 2) d2 USING (p)
        GROUP BY ALL ORDER BY idade_primeira_dose NULLS LAST, intervalo_dias NULLS LAST""")


def main() -> None:
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    con = conectar()
    dim = pd.read_csv(DIM_MUNICIPIOS)
    salvar("dim_municipios", dim)

    salvar("gold_doses_dia", contar(con, ["data_vacinacao", "ano_mes", "dose_grupo", "vacina_tipo"], dropna=True))
    salvar("gold_doses_uf_mes", contar(con, ["ano_mes", "uf_paciente", "vacina_tipo", "dose_grupo"]))
    salvar("gold_municipio_mes", municipio_mes(con, dim))
    salvar("gold_perfil", contar(con, ["ano_mes", "uf_paciente", "sexo_paciente", "faixa_etaria", "raca_cor_paciente",
                                       "vacina_tipo", "dose_grupo"]))
    # Idade simples x dose (sem limite superior; idade ausente fica de fora, ver gold_resumo_geral)
    salvar("gold_idade_dose", contar(con, ["ano_mes", "idade_paciente", "dose_grupo", "vacina_tipo"], dropna=True))
    salvar("gold_coorte_criancas_municipio", coorte_criancas(con, dim))
    salvar("gold_atraso_registro", contar(con, ["ano_mes", "uf_paciente", "faixa_atraso"]))
    salvar("gold_estabelecimento", contar(con, ["ano_mes", "uf_estabelecimento", "tipo_estabelecimento",
                                                "natureza_estabelecimento", "estrategia_vacinacao"]))
    salvar("gold_kpis_mensais", kpis_mensais(con))

    # ---------------------------------------------------------------- detalhe e qualidade
    salvar("gold_resumo_geral", resumo_geral(con))
    salvar("gold_qualidade_colunas", qualidade_colunas(con))
    funil = pd.DataFrame(json.loads(RESUMO_PROCESSAMENTO.read_text(encoding="utf-8"))).T
    salvar("gold_funil_processamento", funil.rename_axis("ano_mes").reset_index())
    salvar("gold_doses_por_paciente", consulta(con, """
        SELECT n AS doses_na_janela, count(*) AS pacientes FROM (
            SELECT count(*) AS n FROM s WHERE codigo_paciente_anonimizado IS NOT NULL GROUP BY codigo_paciente_anonimizado)
        GROUP BY n ORDER BY n"""))
    con.execute("CREATE VIEW s_ordem AS SELECT *, least(ordem_dose_paciente, 4) AS ordem_dose FROM s")
    salvar("gold_dose_descricao_ordem", contar(con, ["ano_mes", "descricao_dose_vacina", "ordem_dose"], origem="s_ordem"))
    salvar("gold_atraso_dias", contar(con, ["atraso_registro_dias"], dropna=True))
    salvar("gold_intervalo_doses", intervalo_entre_doses(con))
    salvar("gold_estrategia_faixa", contar(con, ["ano_mes", "faixa_etaria", "tipo_estabelecimento",
                                                 "natureza_estabelecimento", "estrategia_vacinacao"]))
    salvar("gold_categoria_atendimento", contar(con, ["ano_mes", "categoria_atendimento"]))
    salvar("gold_nacionalidade_etnia", contar(con, ["nacionalidade_paciente", "etnia_indigena_paciente"]))
    salvar("gold_fluxo_uf", contar(con, ["uf_paciente", "uf_estabelecimento"]))
    salvar("gold_estabelecimento_cnes", contar(con, ["codigo_cnes_estabelecimento", "uf_estabelecimento",
                                                     "tipo_estabelecimento", "natureza_estabelecimento"]))
    salvar("gold_vacina_fabricante", contar(con, ["ano_mes", "descricao_vacina", "sigla_vacina", "vacina_tipo",
                                                  "fabricante_vacina"]))
    con.close()
    shutil.rmtree(TMP_DIR, ignore_errors=True)


if __name__ == "__main__":
    main()
