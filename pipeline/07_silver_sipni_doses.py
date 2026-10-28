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
Uso:   python pipeline/07_silver_sipni_doses.py   (precisa de ~5 GB de RAM)
"""

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

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


def numerar_doses_por_paciente(df: pd.DataFrame) -> pd.DataFrame:
    """A descrição da dose muitas vezes vem só como "Dose" (16% das linhas). A ordem real da
    dose de cada paciente dentro da janela dos dados (2025+) resolve essa ambiguidade. Limite:
    doses anteriores à janela não são vistas, então `ordem_dose_paciente` é um mínimo."""
    df = df.sort_values(["codigo_paciente_anonimizado", "data_vacinacao"], kind="stable")
    grupo = df.groupby("codigo_paciente_anonimizado", sort=False)
    df["ordem_dose_paciente"] = (grupo.cumcount() + 1).astype("Int32")
    df["doses_paciente_janela"] = grupo["ordem_dose_paciente"].transform("size").astype("Int32")
    return df.sort_values(["data_vacinacao"], kind="stable").reset_index(drop=True)


def montar_dim_municipios(pedacos: list[pd.DataFrame]) -> pd.DataFrame:
    """Um nome e uma UF por código de município (o valor mais frequente), juntando os
    municípios de residência do paciente e do estabelecimento."""
    paciente = pd.concat(p[["codigo_municipio_paciente", "municipio_paciente", "uf_paciente"]].set_axis(
        ["codigo_municipio", "municipio", "uf"], axis=1) for p in pedacos)
    estab = pd.concat(p[["codigo_municipio_estabelecimento", "municipio_estabelecimento", "uf_estabelecimento"]].set_axis(
        ["codigo_municipio", "municipio", "uf"], axis=1) for p in pedacos)
    dim = pd.concat([paciente, estab]).dropna(subset=["codigo_municipio"])
    dim = dim.groupby("codigo_municipio", as_index=False).agg(
        municipio=("municipio", lambda s: s.mode().iat[0] if s.notna().any() else None),
        uf=("uf", lambda s: s.mode().iat[0] if s.notna().any() else None),
    )
    return dim.sort_values("codigo_municipio")


def main() -> None:
    arquivos = arquivos_mensais()
    print(f"{len(arquivos)} arquivos mensais: {arquivos[0][0]}-{arquivos[0][1]:02d} a {arquivos[-1][0]}-{arquivos[-1][1]:02d}")

    vistos = np.empty(0, dtype=np.uint64)  # hash dos codigo_documento já gravados (dedup entre meses)
    dim_pedacos, resumo, meses = [], {}, []

    for ano, mes, arq in arquivos:
        chave = f"{ano}-{mes:02d}"
        df = pd.read_csv(arq, dtype=str)
        lidas = len(df)
        df = tratar_mes(df, ano, mes)
        apos_diluente = len(df)

        hashes = pd.util.hash_array(df["codigo_documento"].to_numpy(dtype=object))
        duplicado = np.isin(hashes, vistos) | pd.Series(hashes).duplicated().to_numpy()
        df = df[~duplicado]
        vistos = np.concatenate([vistos, hashes[~duplicado]])

        dim_pedacos.append(df[["codigo_municipio_paciente", "municipio_paciente", "uf_paciente",
                               "codigo_municipio_estabelecimento", "municipio_estabelecimento", "uf_estabelecimento"]])
        meses.append(df.drop(columns=["codigo_documento", "codigo_documento_substituido",
                                      "municipio_paciente", "municipio_estabelecimento"]))

        resumo[chave] = {
            "linhas_csv": lidas, "diluentes_removidos": lidas - apos_diluente,
            "duplicadas_removidas": int(duplicado.sum()), "linhas_finais": len(df),
            "vacinacao_fora_do_mes": int(df["vacinacao_fora_do_mes"].sum()),
        }
        print(chave, resumo[chave])

    silver = numerar_doses_por_paciente(pd.concat(meses, ignore_index=True))
    del meses
    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SAIDA.with_suffix(".tmp")
    silver.to_parquet(tmp, index=False, compression="zstd", compression_level=9, row_group_size=1_000_000)
    tmp.replace(SAIDA)

    montar_dim_municipios(dim_pedacos).to_csv(SAIDA_MUNICIPIOS, index=False, encoding="utf-8")
    SAIDA_RESUMO.parent.mkdir(parents=True, exist_ok=True)
    SAIDA_RESUMO.write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    total = sum(r["linhas_finais"] for r in resumo.values())
    print(f"\n{SAIDA.name}: {total} linhas, {SAIDA.stat().st_size / 1e6:.0f} MB")


if __name__ == "__main__":
    main()
