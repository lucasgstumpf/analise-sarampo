"""Baixa uma camada (ou parte dela) publicada no Azure para data/<camada>/, sem credencial.

Serve para reproduzir a pipeline a partir de qualquer camada: por exemplo, baixar a bronze
de uma versão e rodar silver e gold, ou baixar só a gold para os notebooks. Cada arquivo é
conferido pelo sha256 do manifesto publicado; os que já existem no disco com o mesmo
conteúdo são pulados. O manifesto da versão é gravado em data/<camada>/_manifesto.json.

Uso:
    python pipeline/baixar_azure.py gold                       # versão mais recente
    python pipeline/baixar_azure.py bronze --versao 2026-11-08
    python pipeline/baixar_azure.py bronze --prefixo ibge/ sipni_doses/_perfil_bruto/
    python pipeline/baixar_azure.py --listar silver            # versões publicadas

Enquanto os containers não tiverem acesso público, defina SARAMPO_AZURE_SAS_LEITURA.
"""

import argparse
import json
import sys
import urllib.error

import config
from comum import azure
from comum.manifesto import NOME, sha256


def baixar_camada(camada: str, versao: str | None = None, prefixos: list[str] | None = None) -> dict:
    versao = versao or azure.versao_mais_recente(camada)
    manifesto = azure.ler_json(camada, f"{versao}/{NOME}")
    pasta = config.DADOS / camada
    itens = [a for a in manifesto["arquivos"] if a.get("remoto")
             and (not prefixos or a["caminho"].startswith(tuple(prefixos)))]
    total = sum(a["bytes_remoto"] for a in itens)
    print(f"{camada} {versao}: {len(itens)} arquivos, {total / 1e9:.2f} GB para baixar (comprimido)")

    for i, item in enumerate(itens, 1):
        destino = pasta / item["caminho"]
        if destino.exists() and destino.stat().st_size == item["bytes"] and sha256(destino) == item["sha256"]:
            print(f"  [{i}/{len(itens)}] já está igual: {item['caminho']}")
            continue
        print(f"  [{i}/{len(itens)}] {item['caminho']} ({item['bytes_remoto'] / 1e6:.0f} MB)", flush=True)
        azure.baixar_arquivo(camada, versao, item, destino)

    if not prefixos:  # com prefixo, o manifesto local descreveria arquivos que não estão no disco
        (pasta / NOME).write_text(json.dumps(manifesto, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    nao_publicados = [a["caminho"] for a in manifesto["arquivos"] if not a.get("remoto")]
    if nao_publicados:
        print(f"  {len(nao_publicados)} arquivos do manifesto não são publicados "
              f"(derivados ou redundantes, ex.: {nao_publicados[0]})")
    return manifesto


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("camadas", nargs="+", choices=["bronze", "silver", "gold"])
    parser.add_argument("--versao", help="data de corte da versão (padrão: a mais recente)")
    parser.add_argument("--prefixo", nargs="+", help="só os arquivos cujo caminho começa com estes prefixos")
    parser.add_argument("--listar", action="store_true", help="só lista as versões publicadas")
    args = parser.parse_args()
    try:
        executar(args)
    except urllib.error.HTTPError as erro:
        corpo = erro.read().decode("utf-8", "replace")
        if "PublicAccessNotPermitted" in corpo or erro.code in (401, 403):
            sys.exit("O storage não permite acesso anônimo (ainda). Ative o acesso público de leitura "
                     "nos containers ou defina SARAMPO_AZURE_SAS_LEITURA com um token SAS de leitura.")
        if erro.code == 404:
            sys.exit(f"Não encontrado no Azure: {erro.url.split('?')[0]} (versão ou camada não publicada?)")
        raise


def executar(args: argparse.Namespace) -> None:
    for camada in args.camadas:
        if args.listar:
            print(camada, json.dumps(azure.ler_json(camada, "versoes.json"), ensure_ascii=False))
        else:
            baixar_camada(camada, args.versao, args.prefixo)


if __name__ == "__main__":
    sys.exit(main())
