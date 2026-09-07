"""Biblioteca de coleta de dados do DATASUS.

Funções reutilizáveis para baixar arquivos .dbc, convertê-los para .dbf
e exportá-los para CSV (bruto e com colunas renomeadas), usadas pelos
scripts de extração específicos (ex.: sinan-sarampo.py, sipni-sarampo.py).
"""

import urllib.request
from collections.abc import Callable
from pathlib import Path

import pandas as pd
from dbfread import DBF
from pyreaddbc import dbc2dbf

BASE_URL = "ftp://ftp.datasus.gov.br"


def construir_url(caminho: str) -> str:
    return f"{BASE_URL}/{caminho.lstrip('/')}"


def preparar_diretorios(*diretorios: Path) -> None:
    for diretorio in diretorios:
        diretorio.mkdir(parents=True, exist_ok=True)


def baixar_arquivo(url: str, destino: Path) -> None:
    print(f"Baixando {url}...")
    urllib.request.urlretrieve(url, destino)
    print(f"Download concluído: {destino}")


def converter_dbc_para_dbf(origem: Path, destino: Path) -> None:
    print("Convertendo .dbc para .dbf...")
    dbc2dbf(str(origem), str(destino))


def ler_dbf(origem: Path, encoding: str = "iso-8859-1") -> pd.DataFrame:
    tabela = DBF(str(origem), encoding=encoding)
    return pd.DataFrame(iter(tabela))


def renomear_colunas(df: pd.DataFrame, mapa_colunas: dict[str, str]) -> pd.DataFrame:
    return df.rename(columns=mapa_colunas)


def exportar_para_csv(
    origem_dbf: Path,
    destino_raw: Path,
    destino_processado: Path,
    mapa_colunas: dict[str, str],
) -> pd.DataFrame:
    print("Lendo .dbf e gerando CSV...")
    df_raw = ler_dbf(origem_dbf)
    df_raw.to_csv(destino_raw, index=False, encoding="utf-8")

    df = renomear_colunas(df_raw, mapa_colunas)
    df.to_csv(destino_processado, index=False, encoding="utf-8")
    return df


def _gerar_csvs_e_reportar(
    arquivo_dbf: Path,
    arquivo_csv_raw: Path,
    arquivo_csv_processado: Path,
    mapa_colunas: dict[str, str],
) -> pd.DataFrame:
    df = exportar_para_csv(arquivo_dbf, arquivo_csv_raw, arquivo_csv_processado, mapa_colunas)
    print(f"Processo finalizado! Arquivo gerado: {arquivo_csv_processado} ({len(df)} registros)")
    return df


def extrair_dbc(
    caminho: str,
    nome_base: str,
    mapa_colunas: dict[str, str],
    raw_dir: Path,
    processed_dir: Path,
) -> pd.DataFrame:
    """Baixa um .dbc do DATASUS, converte para .dbf e exporta para CSV (raw e processado).
    `caminho` é relativo à raiz do FTP (BASE_URL). Para fontes compactadas (ex.: SINAN)."""
    preparar_diretorios(raw_dir, processed_dir)

    arquivo_dbc = raw_dir / f"{nome_base}.dbc"
    arquivo_dbf = raw_dir / f"{nome_base}.dbf"
    arquivo_csv_raw = raw_dir / f"{nome_base}.csv"
    arquivo_csv_processado = processed_dir / f"{nome_base}.csv"

    baixar_arquivo(construir_url(caminho), arquivo_dbc)
    converter_dbc_para_dbf(arquivo_dbc, arquivo_dbf)
    return _gerar_csvs_e_reportar(arquivo_dbf, arquivo_csv_raw, arquivo_csv_processado, mapa_colunas)


def extrair_dbf(
    caminho: str,
    nome_base: str,
    mapa_colunas: dict[str, str],
    raw_dir: Path,
    processed_dir: Path,
) -> pd.DataFrame:
    """Baixa um .dbf já descompactado do DATASUS (ex.: PNI/SI-PNI) e exporta para CSV
    (raw e processado). `caminho` é relativo à raiz do FTP (BASE_URL)."""
    preparar_diretorios(raw_dir, processed_dir)

    arquivo_dbf = raw_dir / f"{nome_base}.dbf"
    arquivo_csv_raw = raw_dir / f"{nome_base}.csv"
    arquivo_csv_processado = processed_dir / f"{nome_base}.csv"

    baixar_arquivo(construir_url(caminho), arquivo_dbf)
    return _gerar_csvs_e_reportar(arquivo_dbf, arquivo_csv_raw, arquivo_csv_processado, mapa_colunas)


def extrair_csv_zip_filtrado(
    url: str,
    nome_base: str,
    filtro: Callable[[pd.DataFrame], pd.Series],
    mapa_colunas: dict[str, str],
    raw_dir: Path,
    processed_dir: Path,
    separador: str = ";",
    encoding: str = "latin-1",
    tamanho_chunk: int = 200_000,
) -> pd.DataFrame:
    """Baixa um .zip de uma URL qualquer contendo um CSV grande e filtra em streaming
    (por chunks), mantendo só as linhas onde `filtro(chunk)` for True. Usado para as
    bases mensais do SI-PNI/RNDS (vários GB/mês, fora do FTP). `filtro` é uma função
    (em vez de uma lista de valores) para permitir filtrar por texto livre, não só por
    igualdade de coluna. O .zip é removido ao final; só o CSV filtrado é mantido."""
    preparar_diretorios(raw_dir, processed_dir)

    arquivo_zip = raw_dir / f"{nome_base}.zip"
    arquivo_csv_raw = raw_dir / f"{nome_base}.csv"
    arquivo_csv_processado = processed_dir / f"{nome_base}.csv"

    baixar_arquivo(url, arquivo_zip)

    print("Filtrando...")
    partes = [
        chunk[filtro(chunk)]
        for chunk in pd.read_csv(
            arquivo_zip,
            sep=separador,
            encoding=encoding,
            dtype=str,
            chunksize=tamanho_chunk,
            on_bad_lines="skip",
        )
    ]
    df_raw = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
    df_raw.to_csv(arquivo_csv_raw, index=False, encoding="utf-8")

    df = renomear_colunas(df_raw, mapa_colunas)
    df.to_csv(arquivo_csv_processado, index=False, encoding="utf-8")

    arquivo_zip.unlink()

    print(f"Processo finalizado! Arquivo gerado: {arquivo_csv_processado} ({len(df)} registros)")
    return df
