"""Passo 16 (bronze) - Estimativas de população por município, série anual (DATASUS/IBGE).

Fonte: FTP do DATASUS, as mesmas estimativas usadas pelo TabNet e pelo Ministério da Saúde
como denominador de taxas:
    dissemin/publicos/IBGE/POP/POPBR{AA}.zip       1980-2012 (estimativas IBGE/DATASUS)
    dissemin/publicos/IBGE/POPSVS/POPSBR{AA}.zip   2000 em diante (estimativas da SVS/MS,
                                                   por município, sexo e faixa etária)
Baixa todos os arquivos dos dois diretórios (são pequenos, ~0,25 GB no total). A sobreposição
2000-2012 é proposital: a silver escolhe a série (POPSVS onde houver) e registra a escolha.

Complementa o passo 04, que traz só um ano da tabela 6579 do SIDRA para os mapas.

Saída: data/bronze/populacao/{POP,POPSVS}/<arquivo como no FTP>
       e, ao lado de cada um, <arquivo>.origem.json (URL, data, tamanho e sha256)
Uso:   python pipeline/16_bronze_populacao.py [--forcar]
"""

import config
from comum.datasus import baixar_arquivo, construir_url, ja_existe, listar_ftp

DIRETORIOS = {"POP": "dissemin/publicos/IBGE/POP", "POPSVS": "dissemin/publicos/IBGE/POPSVS"}


def main() -> None:
    for pasta, diretorio in DIRETORIOS.items():
        destino = config.BRONZE_POPULACAO / pasta
        destino.mkdir(parents=True, exist_ok=True)
        arquivos = listar_ftp(diretorio)
        print(f"{diretorio}: {len(arquivos)} arquivos, {sum(arquivos.values()) / 1e6:.0f} MB")
        for nome in sorted(arquivos):
            arquivo = destino / nome
            if ja_existe(arquivo, config.FORCAR_DOWNLOAD):
                continue
            baixar_arquivo(construir_url(f"{diretorio}/{nome}"), arquivo)


if __name__ == "__main__":
    main()
