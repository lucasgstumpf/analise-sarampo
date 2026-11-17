"""Publica uma camada local (data/<camada>/) no Azure Blob Storage. PRECISA DE CREDENCIAL.

É o único script que escreve no storage; baixar (pipeline/baixar_azure.py) não precisa de
credencial. A credencial é um token SAS com permissão de escrita (criar, escrever, listar e
ler) nos containers, lido da variável de ambiente SARAMPO_AZURE_SAS: só o trecho depois do
"?", nunca gravado em arquivo nem em log.

O que faz, para cada camada:
    1. regera data/<camada>/_manifesto.json (para descrever exatamente o que está no disco);
    2. envia cada arquivo comprimido com zstd para <camada>/<versao>/<caminho>.zst, em blocos,
       com o sha256 do original como metadado; se for interrompido, rodar de novo pula os
       arquivos que já estão lá com o mesmo sha256;
    3. envia o manifesto com o caminho e o tamanho remotos de cada arquivo;
    4. atualiza <camada>/versoes.json: "ultima" passa a ser esta versão (a recomendada);
       --nota VERSAO TEXTO anota uma versão (ex.: "provisória, substituída por ...").
A versão é a data de corte (config.DATA_CORTE). Uma versão já publicada não é sobrescrita,
a não ser com --substituir. Arquivos derivados ou redundantes (NAO_PUBLICAR) ficam no
manifesto, marcados como não publicados.

Uso:
    export SARAMPO_AZURE_SAS='sv=...&sig=...'
    SARAMPO_DATA_CORTE=2026-11-08 python pipeline/publicar_azure.py bronze silver gold
"""

import argparse
import base64
import fnmatch
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from compression import zstd
from xml.sax.saxutils import escape

import config
from comum import azure, manifesto as manifesto_camada

NIVEL_ZSTD = 9
BLOCO_ENVIO = 64 * 1024 * 1024
# Derivados de outro arquivo da mesma camada (o .csv sai do .dbf, que sai do .dbc) ou junções:
# não precisam ir para o storage. O .dbc do SINAN (original do DATASUS) é publicado.
NAO_PUBLICAR = {
    "bronze": ["*.dbf", "sipni_doses/*_completo.csv"],
    "silver": [],
    "gold": [],
}


def _sas() -> str:
    sas = os.environ.get("SARAMPO_AZURE_SAS", "").lstrip("?")
    if "sig=" not in sas:
        sys.exit("Defina SARAMPO_AZURE_SAS com um token SAS de escrita (o trecho depois do '?').")
    return sas


def _requisicao(metodo: str, url: str, dados: bytes = b"", cabecalhos: dict | None = None) -> None:
    cab = {"x-ms-version": azure.VERSAO_API, "Content-Length": str(len(dados)), **(cabecalhos or {})}
    for tentativa in range(1, azure.TENTATIVAS + 1):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=dados, method=metodo, headers=cab), timeout=300):
                return
        except urllib.error.HTTPError as erro:
            if erro.code < 500 or tentativa == azure.TENTATIVAS:
                # a URL tem o token: a mensagem mostra só o código e o motivo
                raise SystemExit(f"Azure respondeu {erro.code} {erro.reason} em {metodo} "
                                 f"{url.split('?')[0]}: {erro.read()[:300]!r}") from None
        except (urllib.error.URLError, TimeoutError):
            if tentativa == azure.TENTATIVAS:
                raise SystemExit(f"Falha de rede em {metodo} {url.split('?')[0]}") from None
        time.sleep(2 ** tentativa)


def existe(container: str, caminho: str, sas: str) -> bool:
    try:
        azure.abrir(container, caminho, sas).close()
        return True
    except urllib.error.HTTPError as erro:
        if erro.code == 404:
            return False
        raise


def ja_enviado(container: str, caminho: str, sha256: str, sas: str) -> int | None:
    """Tamanho do blob se ele já foi enviado completo a partir do mesmo arquivo (metadado
    sha256 igual ao do manifesto); None se não existe ou é de outro conteúdo. É o que permite
    retomar uma publicação interrompida sem reenviar o que já subiu."""
    req = urllib.request.Request(azure.url_blob(container, caminho, sas), method="HEAD",
                                 headers={"x-ms-version": azure.VERSAO_API})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            if resp.headers.get("x-ms-meta-sha256") == sha256:
                return int(resp.headers["Content-Length"])
    except urllib.error.HTTPError as erro:
        if erro.code != 404:
            raise SystemExit(f"Azure respondeu {erro.code} ao consultar {caminho}") from None
    return None


def enviar_bytes(container: str, caminho: str, dados: bytes, tipo: str, sas: str) -> None:
    _requisicao("PUT", azure.url_blob(container, caminho, sas), dados,
                {"x-ms-blob-type": "BlockBlob", "Content-Type": tipo})


def enviar_comprimido(container: str, caminho: str, origem, sas: str, sha256: str = "") -> int:
    """Comprime `origem` com zstd e envia como block blob, um bloco de ~64 MB por vez.
    Devolve o tamanho comprimido."""
    url = azure.url_blob(container, caminho, sas)
    compressor = zstd.ZstdCompressor(level=NIVEL_ZSTD)
    ids, pendente, total = [], bytearray(), 0

    def enviar_bloco(dados: bytes) -> None:
        bloco_id = base64.b64encode(f"{len(ids):08d}".encode()).decode()
        _requisicao("PUT", f"{url}&comp=block&blockid={urllib.parse.quote(bloco_id)}", dados)
        ids.append(bloco_id)

    with origem.open("rb") as f:
        while parte := f.read(16 * 1024 * 1024):
            pendente += compressor.compress(parte)
            while len(pendente) >= BLOCO_ENVIO:
                enviar_bloco(bytes(pendente[:BLOCO_ENVIO])); total += BLOCO_ENVIO
                del pendente[:BLOCO_ENVIO]
    pendente += compressor.flush()
    if pendente or not ids:
        enviar_bloco(bytes(pendente)); total += len(pendente)

    lista = "<?xml version=\"1.0\" encoding=\"utf-8\"?><BlockList>" + "".join(
        f"<Latest>{escape(i)}</Latest>" for i in ids) + "</BlockList>"
    _requisicao("PUT", f"{url}&comp=blocklist", lista.encode(),
                {"Content-Type": "application/xml", "x-ms-blob-content-type": "application/zstd",
                 **({"x-ms-meta-sha256": sha256} if sha256 else {})})
    return total


def publicar(camada: str, substituir: bool, sas: str, notas_novas: list | None = None) -> None:
    versao = config.DATA_CORTE.isoformat()
    if existe(camada, f"{versao}/{manifesto_camada.NOME}", sas) and not substituir:
        sys.exit(f"{camada} {versao} já está publicada. Use --substituir para sobrescrever.")

    print(f"== {camada} {versao}")
    caminho_manifesto = manifesto_camada.gerar(camada)
    manifesto = json.loads(caminho_manifesto.read_text(encoding="utf-8"))
    pasta = config.DADOS / camada
    excluir = NAO_PUBLICAR[camada]

    publicar_itens = [a for a in manifesto["arquivos"] if not any(fnmatch.fnmatch(a["caminho"], p) for p in excluir)]
    print(f"   {len(publicar_itens)} de {len(manifesto['arquivos'])} arquivos, "
          f"{sum(a['bytes'] for a in publicar_itens) / 1e9:.2f} GB antes da compressão")
    for i, item in enumerate(publicar_itens, 1):
        inicio = time.time()
        item["remoto"] = item["caminho"] + ".zst"
        destino = f"{versao}/{item['remoto']}"
        tamanho = ja_enviado(camada, destino, item["sha256"], sas) if item.get("sha256") else None
        if tamanho is not None:
            item["bytes_remoto"] = tamanho
            print(f"   [{i}/{len(publicar_itens)}] {item['caminho']}: já enviado", flush=True)
            continue
        item["bytes_remoto"] = enviar_comprimido(camada, destino, pasta / item["caminho"], sas, item.get("sha256", ""))
        print(f"   [{i}/{len(publicar_itens)}] {item['caminho']}: {item['bytes'] / 1e6:.0f} -> "
              f"{item['bytes_remoto'] / 1e6:.0f} MB ({time.time() - inicio:.0f} s)", flush=True)

    manifesto["publicacao"] = {"versao": versao, "compressao": f"zstd nível {NIVEL_ZSTD}",
                               "nao_publicados": excluir}
    corpo = json.dumps(manifesto, indent=2, ensure_ascii=False).encode("utf-8")
    enviar_bytes(camada, f"{versao}/{manifesto_camada.NOME}", corpo, "application/json", sas)

    versoes = azure.ler_json(camada, "versoes.json", sas) if existe(camada, "versoes.json", sas) else {}
    lista = sorted(set(versoes.get("versoes", [])) | {versao})
    notas = {**versoes.get("notas", {}), **dict(notas_novas or [])}
    # "ultima" é a versão publicada por último (a recomendada), não a de data mais alta: uma
    # reconstrução completa pode ter data de corte anterior a uma versão provisória.
    conteudo = {"ultima": versao, "versoes": lista}
    if notas:
        conteudo["notas"] = notas
    enviar_bytes(camada, "versoes.json", json.dumps(conteudo, indent=2, ensure_ascii=False).encode("utf-8"),
                 "application/json", sas)
    total = sum(a.get("bytes_remoto", 0) for a in manifesto["arquivos"])
    print(f"   publicado: {total / 1e9:.2f} GB em {azure.URL_CONTA}/{camada}/{versao}/")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("camadas", nargs="+", choices=["bronze", "silver", "gold"])
    parser.add_argument("--substituir", action="store_true", help="sobrescreve uma versão já publicada")
    parser.add_argument("--nota", nargs=2, action="append", metavar=("VERSAO", "TEXTO"),
                        help="anota uma versão no versoes.json (ex.: que ela foi substituída)")
    args = parser.parse_args()
    if not config.DATA_CORTE_EXPLICITA:
        sys.exit("Defina SARAMPO_DATA_CORTE (a data de corte da execução que gerou estes dados): "
                 "ela vira o nome da versão publicada.")
    sas = _sas()
    for camada in args.camadas:
        publicar(camada, args.substituir, sas, args.nota)


if __name__ == "__main__":
    main()
