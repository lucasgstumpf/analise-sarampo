"""Executa os passos numerados do pipeline em ordem (01 -> 09).

Cada passo roda num processo Python separado, como se fosse chamado à mão, e o executor
para no primeiro que falhar (o passo 03 sai com erro quando algum mês falha, por exemplo).

Uso (a partir da raiz do projeto, com o venv ativado):
    python pipeline/executar_pipeline.py                    # todos os passos
    python pipeline/executar_pipeline.py --camada silver gold
    python pipeline/executar_pipeline.py --passos 07 09
    python pipeline/executar_pipeline.py --listar           # só mostra os passos
    python pipeline/executar_pipeline.py --passos 01 --forcar   # baixa o SINAN de novo

Atenção: os passos de bronze baixam dados da internet. O 03 baixa 1-2 GB por mês do
SI-PNI e leva horas na primeira vez. Nas execuções seguintes, todos os passos de bronze
pulam o que já está em disco; --forcar faz os passos escolhidos baixarem tudo de novo.
"""

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

PASTA = Path(__file__).resolve().parent
PADRAO_PASSO = re.compile(r"^(\d{2})_(bronze|silver|gold)_.+\.py$")


def descobrir_passos() -> list[tuple[str, str, Path]]:
    """[(numero, camada, arquivo), ...] em ordem numérica."""
    passos = []
    for arquivo in sorted(PASTA.glob("[0-9][0-9]_*.py")):
        m = PADRAO_PASSO.match(arquivo.name)
        if m:
            passos.append((m.group(1), m.group(2), arquivo))
    return passos


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--camada", nargs="+", choices=["bronze", "silver", "gold"], help="só os passos destas camadas")
    parser.add_argument("--passos", nargs="+", help="só estes números de passo (ex.: 05 07)")
    parser.add_argument("--listar", action="store_true", help="lista os passos e sai")
    parser.add_argument("--forcar", action="store_true", help="bronze baixa de novo mesmo o que já existe")
    args = parser.parse_args()

    passos = descobrir_passos()
    if args.camada:
        passos = [p for p in passos if p[1] in args.camada]
    if args.passos:
        pedidos = {n.zfill(2) for n in args.passos}
        passos = [p for p in passos if p[0] in pedidos]

    for numero, camada, arquivo in passos:
        print(f"{numero}  {camada:<6}  {arquivo.name}")
    if args.listar or not passos:
        return

    for numero, camada, arquivo in passos:
        print(f"\n===== Passo {numero} ({camada}): {arquivo.name} =====", flush=True)
        inicio = time.time()
        comando = [sys.executable, str(arquivo)] + (["--forcar"] if args.forcar else [])
        resultado = subprocess.run(comando, cwd=PASTA.parent)
        if resultado.returncode != 0:
            sys.exit(f"Passo {numero} falhou (código {resultado.returncode}). Os seguintes não foram executados.")
        print(f"Passo {numero} concluído em {time.time() - inicio:.0f} s")


if __name__ == "__main__":
    main()
