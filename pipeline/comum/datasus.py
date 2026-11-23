"""Funções de coleta e leitura de arquivos do DATASUS, usadas pelos scripts de bronze e silver.

O DATASUS publica as bases antigas por FTP em .dbc (o .dbf comprimido) ou direto em .dbf.
A camada bronze baixa o arquivo, converte para .dbf quando preciso e grava um .csv com as
colunas originais. A camada silver lê esse .csv e aplica o de-para de colunas.

Retomada: cada arquivo é gravado primeiro com a extensão .tmp e só ganha o nome final quando
termina. Assim, um arquivo com o nome final está sempre completo e as funções extrair_*
pulam as etapas cujo resultado já existe (a não ser com forcar=True).
"""

import ftplib
import hashlib
import json
import os
import shutil
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dbfread import DBF

from comum import dbf_rapido

try:  # numba: rápido e sem compilador C; dbc_puro (Python puro) só se o numba não instalar
    from comum.dbc_rapido import dbc2dbf
except ImportError:
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


# SARAMPO_SO_BAIXAR=1: os extrair_* só baixam o arquivo original (.dbc/.dbf) e param, sem
# converter. A conversão de arquivos grandes (DPNI, SINASC) usa muita memória e pode rodar
# depois, com acompanhamento; assim o download pode ficar sozinho (ex.: durante a noite).
SO_BAIXAR = os.environ.get("SARAMPO_SO_BAIXAR") == "1"
TENTATIVAS = 6


def _baixar_uma_vez(url: str, tmp: Path) -> None:
    """Um download com timeout de 2 min sem dados. O FTP do DATASUS às vezes não manda a
    confirmação de fim de transferência (226) depois de arquivos grandes, e o urlretrieve
    ficava esperando para sempre; aqui essa espera é ignorada e o que vale é o tamanho."""
    resp = urllib.request.urlopen(url, timeout=120)
    try:
        esperado = int(resp.headers.get("Content-length") or 0) or None
        with tmp.open("wb") as f:
            shutil.copyfileobj(resp, f, 8 * 1024 * 1024)
    finally:
        try:
            resp.close()
        except (OSError, TimeoutError, EOFError, ftplib.Error):
            pass  # servidor não confirmou o fim; o tamanho é conferido abaixo
    if esperado is not None and tmp.stat().st_size != esperado:
        raise OSError(f"download incompleto: {tmp.stat().st_size} de {esperado} bytes")


def baixar_arquivo(url: str, destino: Path) -> None:
    """Baixa com novas tentativas (espera crescente, até ~5 min entre elas). O arquivo só ganha
    o nome final se o download terminou e o tamanho confere; ao lado fica <arquivo>.origem.json
    com a URL, a data, o tamanho e o sha256 (procedência de cada arquivo da bronze)."""
    print(f"Baixando {url}...", flush=True)
    tmp = temporario(destino)
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            _baixar_uma_vez(url, tmp)
            break
        except (urllib.error.URLError, OSError, TimeoutError, EOFError, ftplib.Error) as erro:
            tmp.unlink(missing_ok=True)
            if tentativa == TENTATIVAS:
                raise
            espera = min(300, 10 * 2 ** tentativa)
            print(f"  falhou (tentativa {tentativa}/{TENTATIVAS}): {erro}; nova tentativa em {espera} s", flush=True)
            time.sleep(espera)
    h = hashlib.sha256()
    with tmp.open("rb") as f:
        while bloco := f.read(8 * 1024 * 1024):
            h.update(bloco)
    origem = {"url": url, "baixado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "bytes": tmp.stat().st_size, "sha256": h.hexdigest()}
    os.replace(tmp, destino)
    destino.with_name(destino.name + ".origem.json").write_text(
        json.dumps(origem, indent=2) + "\n", encoding="utf-8")
    print(f"Download concluído: {destino} ({origem['bytes'] / 1e6:.0f} MB)", flush=True)


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


def dbf_para_csv(origem_dbf: Path, destino_csv: Path) -> int:
    """Grava o .csv bruto do .dbf (colunas originais, UTF-8), lendo em blocos (ver comum/dbf_rapido.py,
    que reproduz a conversão do dbfread + pandas). Retorna o nº de registros."""
    print("Lendo .dbf e gerando CSV (em blocos)...", flush=True)
    tmp = temporario(destino_csv)
    total = dbf_rapido.para_csv(origem_dbf, tmp)
    os.replace(tmp, destino_csv)
    print(f"Arquivo gerado: {destino_csv} ({total} registros)", flush=True)
    return total


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
    if SO_BAIXAR:
        return arquivo_dbc
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
    if SO_BAIXAR:
        return arquivo_dbf
    dbf_para_csv(arquivo_dbf, arquivo_csv)
    return arquivo_csv


def ler_csv_bronze(arquivo: Path) -> pd.DataFrame:
    """Lê um .csv bruto como texto, sem converter vazios em NaN, para que a silver grave
    exatamente os mesmos valores que vieram do .dbf (só com as colunas renomeadas)."""
    return pd.read_csv(arquivo, dtype=str, keep_default_na=False, na_filter=False, encoding="utf-8")


def listar_ftp(caminho_dir: str) -> dict[str, int]:
    """Arquivos de um diretório do FTP do DATASUS: {nome: bytes}. A listagem vem no formato do
    servidor (data, hora, tamanho, nome). Serve para saber o que existe antes de baixar, em vez
    de tentar a URL e esperar o erro de arquivo inexistente."""
    url = construir_url(caminho_dir.rstrip("/") + "/")
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            with urllib.request.urlopen(url, timeout=120) as resp:
                linhas = resp.read().decode("latin-1").splitlines()
            break
        except (urllib.error.URLError, OSError, TimeoutError):
            if tentativa == TENTATIVAS:
                raise
            time.sleep(min(300, 10 * 2 ** tentativa))
    arquivos = {}
    for linha in linhas:
        partes = linha.split()
        if len(partes) >= 4 and partes[2].isdigit():
            arquivos[partes[-1]] = int(partes[2])
    return arquivos
