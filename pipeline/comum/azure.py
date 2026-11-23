"""Leitura das camadas publicadas no Azure Blob Storage (sem credencial).

Organização no storage (um container por camada: bronze, silver, gold):

    <camada>/versoes.json                     {"ultima": "2026-11-08", "versoes": [...]}
    <camada>/<versao>/_manifesto.json         manifesto da camada (comum/manifesto.py) + campos
                                              "remoto" e "bytes_remoto" de cada arquivo publicado
    <camada>/<versao>/<caminho>.zst           cada arquivo comprimido com zstd

A versão é a data de corte da execução que gerou a camada. Ao baixar, cada arquivo é
descomprimido para os mesmos bytes do original e o sha256 é conferido com o manifesto.

O download é anônimo (containers com acesso público de leitura). Enquanto o acesso público
não estiver ligado, defina SARAMPO_AZURE_SAS_LEITURA com um token SAS de leitura (só o
trecho depois do "?"). A publicação, que precisa de credencial de escrita, fica à parte, em
pipeline/publicar_azure.py.
"""

import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from compression import zstd
from pathlib import Path

URL_CONTA = os.environ.get("SARAMPO_AZURE_URL", "https://sarampo.blob.core.windows.net").rstrip("/")
VERSAO_API = "2023-11-03"
TENTATIVAS = 5
BLOCO = 16 * 1024 * 1024


def url_blob(container: str, caminho: str, sas: str | None = None) -> str:
    url = f"{URL_CONTA}/{container}/{urllib.parse.quote(caminho)}"
    return f"{url}?{sas.lstrip('?')}" if sas else url


def _sas_leitura() -> str | None:
    return os.environ.get("SARAMPO_AZURE_SAS_LEITURA") or None


def abrir(container: str, caminho: str, sas: str | None = None):
    """Resposta HTTP de um blob, com novas tentativas em erro de rede ou 5xx."""
    sas = sas if sas is not None else _sas_leitura()
    req = urllib.request.Request(url_blob(container, caminho, sas), headers={"x-ms-version": VERSAO_API})
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            return urllib.request.urlopen(req, timeout=120)
        except urllib.error.HTTPError as erro:
            if erro.code < 500 or tentativa == TENTATIVAS:
                raise
        except (urllib.error.URLError, TimeoutError):
            if tentativa == TENTATIVAS:
                raise
        time.sleep(2 ** tentativa)
    raise AssertionError("inalcançável")


def ler_json(container: str, caminho: str, sas: str | None = None) -> dict:
    with abrir(container, caminho, sas) as resp:
        return json.loads(resp.read().decode("utf-8"))


def versao_mais_recente(camada: str) -> str:
    return ler_json(camada, "versoes.json")["ultima"]


def baixar_arquivo(camada: str, versao: str, item: dict, destino: Path) -> None:
    """Baixa <versao>/<item.remoto>, descomprime em streaming e só dá o nome final ao arquivo
    se o sha256 bater com o do manifesto."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(destino.name + ".tmp")
    h = hashlib.sha256()
    descompressor = zstd.ZstdDecompressor()
    with abrir(camada, f"{versao}/{item['remoto']}") as resp, tmp.open("wb") as saida:
        while bloco := resp.read(BLOCO):
            dados = descompressor.decompress(bloco)
            h.update(dados)
            saida.write(dados)
    if h.hexdigest() != item["sha256"]:
        tmp.unlink()
        raise IOError(f"sha256 não confere para {item['caminho']}: o download veio corrompido ou "
                      "o manifesto não corresponde aos arquivos publicados")
    os.replace(tmp, destino)
