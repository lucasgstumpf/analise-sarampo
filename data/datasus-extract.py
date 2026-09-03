import urllib.request
from pathlib import Path

import pandas as pd
from dbfread import DBF
from pyreaddbc import dbc2dbf

URL = "ftp://ftp.datasus.gov.br/dissemin/publicos/SINAN/DADOS/PRELIM/EXANBR26.dbc"

NOME_BASE = "sinan_sarampo_exames_2026"

RAW_DIR = Path(__file__).parent / "raw"
PROCESSED_DIR = Path(__file__).parent / "processed"

ARQUIVO_DBC = RAW_DIR / f"{NOME_BASE}.dbc"
ARQUIVO_DBF = RAW_DIR / f"{NOME_BASE}.dbf"
ARQUIVO_CSV = PROCESSED_DIR / f"{NOME_BASE}.csv"


def baixar_dbc(url: str, destino: Path) -> None:
    print("Iniciando download...")
    urllib.request.urlretrieve(url, destino)
    print("Download concluído.")


def converter_para_dbf(origem: Path, destino: Path) -> None:
    print("Convertendo .dbc para .dbf...")
    dbc2dbf(str(origem), str(destino))


def exportar_para_csv(origem: Path, destino: Path) -> pd.DataFrame:
    print("Lendo .dbf e gerando CSV...")
    tabela = DBF(str(origem), encoding="iso-8859-1")
    df = pd.DataFrame(iter(tabela))
    df.to_csv(destino, index=False, encoding="utf-8")
    return df


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    baixar_dbc(URL, ARQUIVO_DBC)
    converter_para_dbf(ARQUIVO_DBC, ARQUIVO_DBF)
    df = exportar_para_csv(ARQUIVO_DBF, ARQUIVO_CSV)

    print(f"Processo finalizado! Arquivo gerado: {ARQUIVO_CSV} ({len(df)} registros)")


if __name__ == "__main__":
    main()
