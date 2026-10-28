"""Funções de coleta e leitura de arquivos do DATASUS, usadas pelos scripts de bronze e silver.

O DATASUS publica as bases antigas por FTP em .dbc (o .dbf comprimido) ou direto em .dbf.
A camada bronze baixa o arquivo, converte para .dbf quando preciso e grava um .csv com as
colunas originais. A camada silver lê esse .csv e aplica o de-para de colunas.

Retomada: cada arquivo é gravado primeiro com a extensão .tmp e só ganha o nome final quando
termina. Assim, um arquivo com o nome final está sempre completo e as funções extrair_*
pulam as etapas cujo resultado já existe (a não ser com forcar=True).
"""

import os
import urllib.request
from pathlib import Path

import pandas as pd
from dbfread import DBF

try:
    from pyreaddbc import dbc2dbf
except ImportError:  # pyreaddbc precisa de compilador C quando não há wheel pronta
    from comum.dbc_puro import dbc2dbf

BASE_URL = "ftp://ftp.datasus.gov.br"


def construir_url(caminho: str) -> str:
    """Monta a URL completa a partir de um caminho relativo à raiz do FTP do DATASUS."""
    return f"{BASE_URL}/{caminho.lstrip('/')}"


def preparar_diretorios(*diretorios: Path) -> None:
    for diretorio in diretorios:
        diretorio.mkdir(parents=True, exist_ok=True)


def temporario(destino: Path) -> Path:
    """Caminho .tmp usado enquanto `destino` está sendo gravado."""
    return destino.with_name(destino.name + ".tmp")


def ja_existe(arquivo: Path, forcar: bool = False) -> bool:
    """True se o arquivo final já está em disco (e não vazio) e não foi pedido para refazer."""
    return not forcar and arquivo.exists() and arquivo.stat().st_size > 0


def baixar_arquivo(url: str, destino: Path) -> None:
    print(f"Baixando {url}...")
    tmp = temporario(destino)
    urllib.request.urlretrieve(url, tmp)
    os.replace(tmp, destino)
    print(f"Download concluído: {destino}")


def converter_dbc_para_dbf(origem: Path, destino: Path) -> None:
    print("Convertendo .dbc para .dbf...")
    tmp = temporario(destino)
    dbc2dbf(str(origem), str(tmp))
    os.replace(tmp, destino)


def ler_dbf(origem: Path, encoding: str = "iso-8859-1") -> pd.DataFrame:
    tabela = DBF(str(origem), encoding=encoding)
    return pd.DataFrame(iter(tabela))


def renomear_colunas(df: pd.DataFrame, mapa_colunas: dict[str, str]) -> pd.DataFrame:
    return df.rename(columns=mapa_colunas)


def dbf_para_csv(origem_dbf: Path, destino_csv: Path) -> pd.DataFrame:
    """Lê o .dbf e grava o .csv bruto (colunas originais, UTF-8)."""
    print("Lendo .dbf e gerando CSV...")
    df = ler_dbf(origem_dbf)
    tmp = temporario(destino_csv)
    df.to_csv(tmp, index=False, encoding="utf-8")
    os.replace(tmp, destino_csv)
    print(f"Arquivo gerado: {destino_csv} ({len(df)} registros)")
    return df


def extrair_dbc(caminho: str, nome_base: str, destino_dir: Path, forcar: bool = False) -> Path:
    """Bronze de uma fonte compactada (ex.: SINAN): baixa o .dbc, converte para .dbf e grava
    o .csv bruto. Os três arquivos ficam em `destino_dir`. Retorna o caminho do .csv.
    `caminho` é relativo à raiz do FTP (BASE_URL). Etapas já feitas são puladas: se o .csv
    existe, nada é refeito; se só o .dbc existe, só converte. `forcar=True` refaz tudo."""
    preparar_diretorios(destino_dir)
    arquivo_dbc = destino_dir / f"{nome_base}.dbc"
    arquivo_dbf = destino_dir / f"{nome_base}.dbf"
    arquivo_csv = destino_dir / f"{nome_base}.csv"

    if ja_existe(arquivo_csv, forcar):
        print(f"Já existe, pulando: {arquivo_csv.name}")
        return arquivo_csv
    if not ja_existe(arquivo_dbc, forcar):
        baixar_arquivo(construir_url(caminho), arquivo_dbc)
    if not ja_existe(arquivo_dbf, forcar):
        converter_dbc_para_dbf(arquivo_dbc, arquivo_dbf)
    dbf_para_csv(arquivo_dbf, arquivo_csv)
    return arquivo_csv


def extrair_dbf(caminho: str, nome_base: str, destino_dir: Path, forcar: bool = False) -> Path:
    """Bronze de uma fonte já descompactada (ex.: PNI/SI-PNI histórico): baixa o .dbf e grava
    o .csv bruto em `destino_dir`. Retorna o caminho do .csv. Pula o que já existe (se o .csv
    existe, nada é refeito; se só o .dbf existe, só gera o .csv); `forcar=True` refaz tudo."""
    preparar_diretorios(destino_dir)
    arquivo_dbf = destino_dir / f"{nome_base}.dbf"
    arquivo_csv = destino_dir / f"{nome_base}.csv"

    if ja_existe(arquivo_csv, forcar):
        print(f"Já existe, pulando: {arquivo_csv.name}")
        return arquivo_csv
    if not ja_existe(arquivo_dbf, forcar):
        baixar_arquivo(construir_url(caminho), arquivo_dbf)
    dbf_para_csv(arquivo_dbf, arquivo_csv)
    return arquivo_csv


def ler_csv_bronze(arquivo: Path) -> pd.DataFrame:
    """Lê um .csv bruto como texto, sem converter vazios em NaN, para que a silver grave
    exatamente os mesmos valores que vieram do .dbf (só com as colunas renomeadas)."""
    return pd.read_csv(arquivo, dtype=str, keep_default_na=False, na_filter=False, encoding="utf-8")
