"""Passo 11 (gold) - Notificações de sarampo/rubéola do SINAN prontas para análise, 2007-2026.

Entrada: data/silver/sinan_sarampo/sinan_sarampo_exames_{AAAA}.csv  (passo 05)

A ficha do SINAN tem 107 colunas, a maioria de controle do sistema. Aqui ficam só as
usadas na análise (tempo, lugar, pessoa, sintomas, vacinação, classificação e desfecho),
com os códigos convertidos para número e as datas para data, além de duas colunas
derivadas: idade em anos (decodificada do campo idade do SINAN) e faixa etária. Uma linha
por notificação; a base inteira cabe em poucos MB.

Os códigos seguem o dicionário do SINAN (ex.: 1 = Sim, 2 = Não, 9 = Ignorado nos sintomas);
os rótulos ficam nos notebooks.

Saída: data/gold/sinan/gold_sinan_notificacoes.{parquet,csv}
       data/gold/sinan/gold_sinan_qualidade_colunas.{parquet,csv}
           ano do arquivo x coluna da silver (todas as 107) x % vazio
Uso:   python pipeline/11_gold_sinan.py
"""

import pandas as pd

import config
from comum.datasus import ler_csv_bronze

GOLD_DIR = config.GOLD / "sinan"

COLUNAS_CODIGO = [
    "ano_notificacao", "semana_epidemiologica_notificacao", "uf_notificacao", "municipio_notificacao",
    "uf_residencia", "municipio_residencia", "idade", "raca_cor", "escolaridade", "situacao_gestacional",
    "tosse", "coriza", "conjuntivite", "artralgia", "linfadenopatia", "hospitalizado",
    "historico_vacinal", "situacao_vacinal", "classificacao_final", "criterio_confirmacao",
    "caso_autoctone", "uf_provavel_infeccao", "evolucao_caso",
]
COLUNAS_DATA = [
    "data_notificacao", "data_primeiros_sintomas", "data_inicio_exantema", "data_ultima_dose",
    "data_obito", "data_encerramento",
]
COLUNAS_TEXTO = ["sexo"]

FAIXAS = [0, 1, 5, 15, 40, 60, 120]
ROTULOS_FAIXAS = ["<1", "1-4", "5-14", "15-39", "40-59", "60+"]


def decodificar_idade(codigo: pd.Series) -> pd.Series:
    """Idade do SINAN em anos. O 1º dígito é a unidade (1 = horas, 2 = dias, 3 = meses,
    4 = anos) e os outros três, o valor: 4012 = 12 anos, 3006 = 6 meses = 0,5 ano."""
    unidade = codigo // 1000
    valor = codigo % 1000
    anos = pd.Series(pd.NA, index=codigo.index, dtype="Float64")
    anos = anos.mask(unidade == 4, valor).mask(unidade == 3, valor / 12).mask(unidade.isin([1, 2]), 0.0)
    return anos


def main() -> None:
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    notificacoes, qualidade = [], []
    for ano in config.ANOS_SINAN:
        ano4 = config.ano_4_digitos(ano)
        df = ler_csv_bronze(config.SILVER_SINAN / f"sinan_sarampo_exames_{ano4}.csv").replace("", pd.NA)
        qualidade.append(pd.DataFrame({
            "ano_arquivo": int(ano4), "coluna": df.columns,
            "pct_vazios": (100 * df.isna().mean()).round(4).values,
        }))

        g = pd.DataFrame({"ano_arquivo": int(ano4)}, index=df.index)
        for coluna in COLUNAS_CODIGO:
            g[coluna] = pd.to_numeric(df[coluna], errors="coerce").astype("Int64")
        for coluna in COLUNAS_DATA:
            g[coluna] = pd.to_datetime(df[coluna], errors="coerce")
        for coluna in COLUNAS_TEXTO:
            g[coluna] = df[coluna].astype("string")
        g["idade_anos"] = decodificar_idade(g["idade"])
        g["faixa_etaria"] = pd.cut(g["idade_anos"].astype(float), FAIXAS, labels=ROTULOS_FAIXAS,
                                   right=False).astype("string")
        notificacoes.append(g)

    notificacoes = pd.concat(notificacoes, ignore_index=True)
    notificacoes.to_parquet(GOLD_DIR / "gold_sinan_notificacoes.parquet", index=False, compression="zstd")
    notificacoes.to_csv(GOLD_DIR / "gold_sinan_notificacoes.csv", index=False, encoding="utf-8")
    print(f"gold_sinan_notificacoes: {len(notificacoes):,} linhas x {notificacoes.shape[1]} colunas")

    qualidade = pd.concat(qualidade, ignore_index=True)
    qualidade.to_parquet(GOLD_DIR / "gold_sinan_qualidade_colunas.parquet", index=False, compression="zstd")
    qualidade.to_csv(GOLD_DIR / "gold_sinan_qualidade_colunas.csv", index=False, encoding="utf-8")
    print(f"gold_sinan_qualidade_colunas: {len(qualidade):,} linhas")


if __name__ == "__main__":
    main()
