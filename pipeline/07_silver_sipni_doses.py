"""Passo 07 (silver) - Doses de vacinas com sarampo (SI-PNI/RNDS), limpas e tipadas.

Entrada: data/bronze/sipni_doses/sipni_doses_sarampo_sipni_{AAAA}_{mmm}.csv  (passo 03)

Regras aplicadas, mês a mês:
    - mantém só as colunas úteis para a análise (56 -> ~30; ver COLUNAS);
    - remove os diluentes (DILSCR, DILSR), que entram no filtro por terem "sarampo" no nome
      mas não são doses;
    - converte datas e idade, padroniza sexo, tipo de vacina, faixa etária e número da dose;
    - calcula o atraso entre a aplicação e o registro no RNDS;
    - remove documentos duplicados entre meses (o mesmo codigo_documento pode ser
      republicado num mês seguinte);
    - numera as doses de cada paciente dentro da janela (ordem_dose_paciente).
Os nomes de município saem da tabela de doses e vão para uma dimensão à parte.

Saída: data/silver/sipni_doses/vacinacao_sarampo_sipni.parquet  (1 linha = 1 dose)
       data/silver/sipni_doses/dim_municipios.csv
       data/silver/sipni_doses/_auditoria/processamento_resumo.json  (funil por mês)
Uso:   python pipeline/07_silver_sipni_doses.py [--retomar]   (--retomar: reaproveita as partes já gravadas)

Memória: cada mês é lido em blocos de 500 mil linhas e gravado como uma parte em parquet; a
numeração por paciente e a ordenação final ficam com o duckdb, que usa o disco
(data/silver/sipni_doses/_duckdb_tmp) quando passa de SARAMPO_DUCKDB_MEMORIA (padrão 3GB).
"""

import json
import os
import re
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

import config

BRONZE_DIR = config.BRONZE_SIPNI_DOSES
SILVER_DIR = config.SILVER_SIPNI_DOSES
SAIDA = SILVER_DIR / "vacinacao_sarampo_sipni.parquet"
SAIDA_MUNICIPIOS = SILVER_DIR / "dim_municipios.csv"
SAIDA_RESUMO = config.SILVER_SIPNI_DOSES_AUDITORIA / "processamento_resumo.json"

# CSVs mensais gerados pelo passo 03 (o "completo"/"jan_jun" são só junções deles).
PADRAO_MENSAL = re.compile(r"sipni_doses_sarampo_sipni_(\d{4})_([a-z]{3})\.csv$")
MESES = config.MESES_ABREV

# Só as colunas úteis para a análise. Foram descartadas: as 100% vazias/constantes
# (data_delecao_rnds, status_documento), os códigos que só repetem a descrição ao lado, os
# textos livres de alta cardinalidade (razão social, nome fantasia, lote, CEP) e
# os nomes de município/UF, que ficam na dim_municipios.csv em vez de repetidos por linha.
COLUNAS = [
    "codigo_documento", "codigo_paciente_anonimizado", "sexo_paciente", "raca_cor_paciente",
    "codigo_municipio_paciente", "uf_paciente", "nacionalidade_paciente", "etnia_indigena_paciente",
    "codigo_cnes_estabelecimento", "codigo_municipio_estabelecimento", "uf_estabelecimento",
    "codigo_documento_substituido", "sigla_vacina", "data_vacinacao", "descricao_dose_vacina",
    "data_entrada_rnds", "estrategia_vacinacao", "categoria_atendimento", "tipo_estabelecimento",
    "natureza_estabelecimento", "idade_paciente",
    "descricao_vacina", "fabricante_vacina",  # nome completo do imunobiológico e fabricante
    "municipio_paciente", "municipio_estabelecimento",  # só para montar a dim_municipios
]
CATEGORICAS = [
    "sexo_paciente", "raca_cor_paciente", "uf_paciente", "nacionalidade_paciente",
    "etnia_indigena_paciente", "uf_estabelecimento", "sigla_vacina", "descricao_dose_vacina",
    "estrategia_vacinacao", "categoria_atendimento", "tipo_estabelecimento", "natureza_estabelecimento",
    "descricao_vacina", "fabricante_vacina",
]

SEXO = {"M": "Masculino", "F": "Feminino", "I": "Ignorado"}
VACINA_TIPO = {
    "SCR": "Tríplice viral (SCR)", "SCRV": "Tetra viral (SCRV)", "SCRV-2": "Tetra viral (SCRV)",
    "SR": "Dupla viral (SR)", "Sarampo": "Monovalente",
}
# Faixas etárias (idade em anos completos); a vacinação de rotina se concentra em 1-4 anos.
FAIXAS_IDADE = [0, 1, 2, 5, 10, 15, 20, 30, 40, 50, 60, 200]
ROTULOS_IDADE = ["<1", "1", "2-4", "5-9", "10-14", "15-19", "20-29", "30-39", "40-49", "50-59", "60+"]

# Diluentes (DILSCR, DILSR) aparecem na base porque o nome contém "sarampo", mas não são doses.
SIGLAS_DILUENTE = ("DIL",)

# "Dose"/"Única"/"1ª Dose"... vêm da base com acentos; normaliza para um esquema de dose numérico.
DOSE_NUMERO = {
    "Dose Zero": 0, "Dose Inicial": 1, "1ª Dose": 1, "Única": 1, "1ª Dose Revacinação": 1,
    "1ª Dose Dobrada": 1, "2ª Dose": 2, "2ª Dose Revacinação": 2, "2ª Dose Dobrada": 2,
    "2ª Dose Fracionada": 2, "3ª Dose": 3, "4ª Dose": 4,
}


def arquivos_mensais() -> list[tuple[int, int, Path]]:
    """CSVs mensais da bronze, em ordem cronológica: [(ano, mês, caminho), ...]."""
    achados = []
    for arq in BRONZE_DIR.glob("sipni_doses_sarampo_sipni_*.csv"):
        m = PADRAO_MENSAL.search(arq.name)
        if m and m.group(2) in MESES:
            achados.append((int(m.group(1)), MESES.index(m.group(2)) + 1, arq))
    return sorted(achados)


def tratar_mes(df: pd.DataFrame, ano: int, mes: int) -> pd.DataFrame:
    """Aplica as regras de limpeza da silver a um mês da bronze."""
    df = df[COLUNAS].copy()

    df = df[~df["sigla_vacina"].str.upper().str.startswith(SIGLAS_DILUENTE, na=False)]

    df["data_vacinacao"] = pd.to_datetime(df["data_vacinacao"], errors="coerce")
    df["data_entrada_rnds"] = pd.to_datetime(df["data_entrada_rnds"], errors="coerce")
    df["idade_paciente"] = pd.to_numeric(df["idade_paciente"], errors="coerce").astype("Int16")
    df["substituiu_documento"] = df["codigo_documento_substituido"].notna()
    df["ano_mes"] = f"{ano}-{mes:02d}"
    # A data de vacinação nem sempre cai no mês do arquivo (a publicação é por data de
    # entrada no RNDS); mantém-se o registro e sinaliza para o filtro de análise.
    df["vacinacao_fora_do_mes"] = (df["data_vacinacao"].dt.year != ano) | (df["data_vacinacao"].dt.month != mes)

    # Dose como número (0 = dose zero, 1, 2...) + descrição original; reforços/adicional ficam sem número.
    df["dose_numero"] = df["descricao_dose_vacina"].map(DOSE_NUMERO).astype("Int8")

    df["sexo_paciente"] = df["sexo_paciente"].map(SEXO).fillna("Ignorado")
    df["vacina_tipo"] = df["sigla_vacina"].map(VACINA_TIPO).fillna("Outra")
    df["faixa_etaria"] = pd.cut(
        df["idade_paciente"].astype("float"), FAIXAS_IDADE, labels=ROTULOS_IDADE, right=False
    ).astype("string")
    # Atraso entre aplicar a dose e o registro chegar ao RNDS (dias); negativo = data inconsistente.
    df["atraso_registro_dias"] = (df["data_entrada_rnds"] - df["data_vacinacao"]).dt.days.astype("Int32")

    for col in CATEGORICAS:
        df[col] = df[col].astype("string")
    return df


# Tipos da silver (como o pandas gravava antes): o duckdb devolve string e é convertido de volta.
TIPOS_PARQUET = {"idade_paciente": pa.int16(), "dose_numero": pa.int8(), "atraso_registro_dias": pa.int32(),
                 "ordem_dose_paciente": pa.int32(), "doses_paciente_janela": pa.int32(),
                 "data_vacinacao": pa.timestamp("us"), "data_entrada_rnds": pa.timestamp("us"),
                 "substituiu_documento": pa.bool_(), "vacinacao_fora_do_mes": pa.bool_()}
LINHAS_CHUNK = 500_000
LINHAS_POR_GRUPO = 1_000_000
LINHAS_POR_FATIA = int(os.environ.get("SARAMPO_LINHAS_POR_FATIA") or 3_000_000)  # gravação em fatias de data
COLUNAS_DIM = ["codigo_municipio_paciente", "municipio_paciente", "uf_paciente",
               "codigo_municipio_estabelecimento", "municipio_estabelecimento", "uf_estabelecimento"]


class Vistos:
    """Hashes dos codigo_documento já gravados (dedup entre meses e dentro do mês): um vetor
    ordenado dos meses anteriores e os blocos do mês atual, consultados por busca binária."""

    def __init__(self) -> None:
        self.base = np.empty(0, dtype=np.uint64)
        self.mes: list[np.ndarray] = []

    @staticmethod
    def _contem(ordenado: np.ndarray, h: np.ndarray) -> np.ndarray:
        if not len(ordenado):
            return np.zeros(len(h), dtype=bool)
        i = np.searchsorted(ordenado, h).clip(max=len(ordenado) - 1)
        return ordenado[i] == h

    def duplicados(self, h: np.ndarray) -> np.ndarray:
        dup = self._contem(self.base, h) | pd.Series(h).duplicated().to_numpy()
        for bloco in self.mes:
            dup |= self._contem(bloco, h)
        self.mes.append(np.sort(h[~dup]))
        return dup

    def fechar_mes(self) -> None:
        self.base = np.sort(np.concatenate([self.base, *self.mes]))
        self.mes = []


def processar_meses(arquivos, pasta_partes: Path) -> dict:
    """1ª etapa: cada mês da bronze, em blocos, vira uma parte em parquet (regras de limpeza e
    dedup). `seq` guarda a ordem original (mês, linha), usada nos desempates como no pandas."""
    vistos, resumo, seq = Vistos(), {}, 0
    for ano, mes, arq in arquivos:
        chave = f"{ano}-{mes:02d}"
        lidas = apos_diluente = duplicadas = fora = 0
        caminho = pasta_partes / f"doses_{chave}.parquet"
        escritor = escritor_dim = None
        for bruto in pd.read_csv(arq, dtype=str, usecols=COLUNAS, chunksize=LINHAS_CHUNK):
            lidas += len(bruto)
            df = tratar_mes(bruto, ano, mes)
            del bruto
            apos_diluente += len(df)
            duplicado = vistos.duplicados(pd.util.hash_array(df["codigo_documento"].to_numpy(dtype=object)))
            df = df[~duplicado]
            duplicadas += int(duplicado.sum())
            fora += int(df["vacinacao_fora_do_mes"].sum())
            dim = pa.Table.from_pandas(df[COLUNAS_DIM].astype("string"), preserve_index=False)
            df = df.drop(columns=["codigo_documento", "codigo_documento_substituido",
                                  "municipio_paciente", "municipio_estabelecimento"])
            df.insert(0, "seq", np.arange(seq, seq + len(df), dtype=np.int64))
            seq += len(df)
            tabela = pa.Table.from_pandas(df, preserve_index=False)
            if escritor is None:
                escritor = pq.ParquetWriter(caminho, tabela.schema, compression="zstd")
                escritor_dim = pq.ParquetWriter(pasta_partes / f"dim_{chave}.parquet", dim.schema, compression="zstd")
            escritor.write_table(tabela.cast(escritor.schema))
            escritor_dim.write_table(dim.cast(escritor_dim.schema))
        if escritor is not None:
            escritor.close()
            escritor_dim.close()
        vistos.fechar_mes()
        resumo[chave] = {"linhas_csv": lidas, "diluentes_removidos": lidas - apos_diluente,
                         "duplicadas_removidas": duplicadas, "linhas_finais": apos_diluente - duplicadas,
                         "vacinacao_fora_do_mes": fora}
        print(chave, resumo[chave], flush=True)
    return resumo


def conectar(pasta_tmp: Path):
    import duckdb
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{config.DUCKDB_MEMORIA}'")
    con.execute(f"SET temp_directory='{pasta_tmp}'")
    con.execute("SET max_temp_directory_size='200GiB'")
    con.execute("SET preserve_insertion_order=true")  # sem isso, o resultado do ORDER BY chega em lotes fora de ordem
    return con


def numerar_doses(con, pasta_partes: Path, pasta_num: Path, grupos: int = 16) -> None:
    """Numera as doses de cada paciente: ordem por data (vazias no fim) e, no empate, pela ordem
    original (`seq`); e o total de doses do paciente. Roda em `grupos` partes (pacientes
    separados pelo hash do código), só com as colunas necessárias, para caber na memória.
    O resultado não depende do hash: todas as doses de um paciente caem no mesmo grupo."""
    p = "codigo_paciente_anonimizado"
    for g in range(grupos):
        con.execute(f"""
            COPY (
                SELECT seq, data_vacinacao,
                       row_number() OVER (PARTITION BY {p} ORDER BY data_vacinacao NULLS LAST, seq)::INTEGER AS ordem,
                       count(*) OVER (PARTITION BY {p})::INTEGER AS total
                FROM read_parquet('{pasta_partes}/doses_*.parquet', union_by_name=true)
                WHERE {p} IS NOT NULL AND hash({p}) % {grupos} = {g}
            ) TO '{pasta_num}/num_{g:02d}.parquet' (FORMAT parquet, COMPRESSION zstd)""")
        print(f"  numeração: grupo {g + 1}/{grupos}", flush=True)


def fatias_por_data(con, pasta_partes: Path, maximo: int = LINHAS_POR_FATIA) -> list[tuple[str, str] | None]:
    """Intervalos de data de vacinação [início, fim) com até ~`maximo` linhas cada, em ordem;
    None no fim = linhas sem data."""
    meses = con.sql(f"""
        SELECT date_trunc('month', data_vacinacao) AS m, count(*) AS n
        FROM read_parquet('{pasta_partes}/doses_*.parquet', union_by_name=true)
        WHERE data_vacinacao IS NOT NULL GROUP BY 1 ORDER BY 1""").fetchall()
    fatias, inicio, soma = [], None, 0
    for i, (m, n) in enumerate(meses):
        inicio = inicio or m
        soma += n
        proximo = meses[i + 1][0] if i + 1 < len(meses) else None
        if soma >= maximo or proximo is None:
            fim = proximo.isoformat() if proximo is not None else "9999-12-31"
            fatias.append((inicio.isoformat(), fim))
            inicio, soma = None, 0
    return fatias + [None]


def gravar_silver(con, pasta_partes: Path, pasta_num: Path, destino: Path) -> int:
    """2ª etapa (duckdb, fora da memória): numera as doses de cada paciente e grava a silver.

    A descrição da dose muitas vezes vem só como "Dose" (16% das linhas): a ordem real da dose
    do paciente dentro da janela dos dados resolve essa ambiguidade. Limite: doses anteriores à
    janela não são vistas, então `ordem_dose_paciente` é um mínimo.

    Equivale ao pandas de antes: ordenar (paciente, data) de forma estável, cumcount + 1 e o
    tamanho do grupo; depois ordenar por data de forma estável (vazios no fim). A gravação é
    feita em fatias de data, já na ordem final, para nunca ordenar a base inteira de uma vez."""
    p = "codigo_paciente_anonimizado"
    numerar_doses(con, pasta_partes, pasta_num)
    colunas = [c for c in pq.read_schema(sorted(pasta_partes.glob("doses_*.parquet"))[0]).names if c != "seq"]
    selecao = ", ".join(f"d.{c}" for c in colunas)
    total, escritor = 0, None
    try:
        for fatia in fatias_por_data(con, pasta_partes):
            if fatia is None:
                filtro_d, filtro_n = "d.data_vacinacao IS NULL", "data_vacinacao IS NULL"
            else:
                faixa = f"BETWEEN TIMESTAMP '{fatia[0]}' AND TIMESTAMP '{fatia[1]}' - INTERVAL 1 MICROSECOND"
                filtro_d, filtro_n = f"d.data_vacinacao {faixa}", f"data_vacinacao {faixa}"
            consulta = f"""
                SELECT {selecao}, n.ordem AS ordem_dose_paciente, n.total AS doses_paciente_janela
                FROM read_parquet('{pasta_partes}/doses_*.parquet', union_by_name=true) d
                LEFT JOIN (SELECT seq, ordem, total FROM read_parquet('{pasta_num}/num_*.parquet')
                           WHERE {filtro_n}) n USING (seq)
                WHERE {filtro_d}
                ORDER BY d.data_vacinacao NULLS LAST, d.{p} NULLS LAST, d.seq"""
            for lote in con.execute(consulta).to_arrow_reader(LINHAS_POR_GRUPO):
                tabela = pa.Table.from_batches([lote])
                if escritor is None:
                    schema = pa.schema([pa.field(c, TIPOS_PARQUET.get(c, pa.large_string()))
                                        for c in tabela.schema.names])
                    escritor = pq.ParquetWriter(destino, schema, compression="zstd", compression_level=9)
                if tabela.num_rows:
                    escritor.write_table(tabela.cast(escritor.schema), row_group_size=LINHAS_POR_GRUPO)
                total += tabela.num_rows
            print(f"  gravação: {fatia or 'sem data'} -> {total:,} linhas", flush=True)
    finally:
        if escritor is not None:
            escritor.close()
    return total


def montar_dim_municipios(con, pasta_partes: Path) -> pd.DataFrame:
    """Um nome e uma UF por código de município (o valor mais frequente; no empate, o menor,
    como o mode() do pandas), juntando os municípios do paciente e do estabelecimento."""
    origem = f"read_parquet('{pasta_partes}/dim_*.parquet')"
    con.execute(f"""
        CREATE OR REPLACE TEMP VIEW mun AS
        SELECT codigo_municipio_paciente AS codigo_municipio, municipio_paciente AS municipio, uf_paciente AS uf FROM {origem}
        UNION ALL
        SELECT codigo_municipio_estabelecimento, municipio_estabelecimento, uf_estabelecimento FROM {origem}""")

    def moda(coluna: str) -> str:
        return f"""
            SELECT codigo_municipio, {coluna} FROM (
                SELECT codigo_municipio, {coluna},
                       row_number() OVER (PARTITION BY codigo_municipio ORDER BY n DESC, {coluna}) AS r
                FROM (SELECT codigo_municipio, {coluna}, count(*) AS n FROM mun
                      WHERE codigo_municipio IS NOT NULL AND {coluna} IS NOT NULL GROUP BY ALL))
            WHERE r = 1"""
    return con.execute(f"""
        SELECT c.codigo_municipio, m.municipio, u.uf
        FROM (SELECT DISTINCT codigo_municipio FROM mun WHERE codigo_municipio IS NOT NULL) c
        LEFT JOIN ({moda("municipio")}) m USING (codigo_municipio)
        LEFT JOIN ({moda("uf")}) u USING (codigo_municipio)
        ORDER BY c.codigo_municipio""").df()


def main() -> None:
    arquivos = arquivos_mensais()
    print(f"{len(arquivos)} arquivos mensais: {arquivos[0][0]}-{arquivos[0][1]:02d} a {arquivos[-1][0]}-{arquivos[-1][1]:02d}")
    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    pasta_partes, pasta_tmp = SILVER_DIR / "_partes", SILVER_DIR / "_duckdb_tmp"
    pasta_num = SILVER_DIR / "_numeracao"
    resumo_partes = pasta_partes / "_resumo.json"
    # --retomar: reaproveita a 1ª etapa (as partes por mês) se ela terminou numa execução anterior.
    if "--retomar" in sys.argv and resumo_partes.exists():
        resumo = json.loads(resumo_partes.read_text(encoding="utf-8"))
        print(f"Retomando: {len(resumo)} meses já processados em {pasta_partes}")
    else:
        shutil.rmtree(pasta_partes, ignore_errors=True)
        pasta_partes.mkdir()
        resumo = processar_meses(arquivos, pasta_partes)
        resumo_partes.write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    for pasta in (pasta_tmp, pasta_num):
        shutil.rmtree(pasta, ignore_errors=True)
        pasta.mkdir()
    con = conectar(pasta_tmp)
    tmp = SAIDA.with_suffix(".tmp")
    total = gravar_silver(con, pasta_partes, pasta_num, tmp)
    tmp.replace(SAIDA)
    montar_dim_municipios(con, pasta_partes).to_csv(SAIDA_MUNICIPIOS, index=False, encoding="utf-8", lineterminator="\n")
    con.close()
    for pasta in (pasta_partes, pasta_tmp, pasta_num):
        shutil.rmtree(pasta)

    SAIDA_RESUMO.parent.mkdir(parents=True, exist_ok=True)
    SAIDA_RESUMO.write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    if total != sum(r["linhas_finais"] for r in resumo.values()):
        raise SystemExit(f"silver com {total} linhas, mas o funil soma outro total")
    print(f"\n{SAIDA.name}: {total} linhas, {SAIDA.stat().st_size / 1e6:.0f} MB")


if __name__ == "__main__":
    main()
