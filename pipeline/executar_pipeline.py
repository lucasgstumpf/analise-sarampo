"""Executa os passos numerados do pipeline em ordem (bronze, silver, gold; validação por último) e grava o manifesto de cada camada.

Cada passo roda num processo Python separado, como se fosse chamado à mão, e o executor
para no primeiro que falhar (o passo 03 sai com erro quando algum mês falha, por exemplo).

Uso (a partir da raiz do projeto, com o venv ativado):
    python pipeline/executar_pipeline.py                    # todos os passos
    python pipeline/executar_pipeline.py --camada silver gold
    python pipeline/executar_pipeline.py --passos 07 09
    python pipeline/executar_pipeline.py --listar           # só mostra os passos
    python pipeline/executar_pipeline.py --passos 01 --forcar   # baixa o SINAN de novo
    python pipeline/executar_pipeline.py --manifesto gold       # só regera data/gold/_manifesto.json
    python pipeline/executar_pipeline.py --camada gold --origem azure --versao 2026-11-08
                                                   # baixa a silver dessa versão e refaz a gold
    SARAMPO_DATA_CORTE=2026-11-08 python pipeline/executar_pipeline.py   # reproduz uma execução

Atenção: os passos de bronze baixam dados da internet. O 03 baixa 1-2 GB por mês do
SI-PNI e leva horas na primeira vez. Nas execuções seguintes, todos os passos de bronze
pulam o que já está em disco; --forcar faz os passos escolhidos baixarem tudo de novo.
"""

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

PASTA = Path(__file__).resolve().parent
# O que cada camada lê das anteriores, para --origem azure baixar só o necessário
# (None = a camada inteira; lista = só os caminhos com esses prefixos).
ENTRADAS = {
    "silver": {"bronze": None},
    "gold": {"silver": None, "bronze": ["ibge/", "sipni_doses/_perfil_bruto/"]},
}
PADRAO_PASSO = re.compile(r"^(\d{2})_(bronze|silver|gold)_.+\.py$")


def descobrir_passos() -> list[tuple[str, str, Path]]:
    """[(numero, camada, arquivo), ...] em ordem numérica."""
    passos = []
    for arquivo in sorted(PASTA.glob("[0-9][0-9]_*.py")):
        m = PADRAO_PASSO.match(arquivo.name)
        if m:
            passos.append((m.group(1), m.group(2), arquivo))
    # Camada antes do número: passos acrescentados depois (ex.: 15 e 16, de bronze) rodam
    # junto com a camada deles, e não depois da gold.
    # A validação (14) compara a gold inteira com as referências: roda por último na gold.
    return sorted(passos, key=lambda p: (["bronze", "silver", "gold"].index(p[1]),
                                         "_validacao" in p[2].name, p[0]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--camada", nargs="+", choices=["bronze", "silver", "gold"], help="só os passos destas camadas")
    parser.add_argument("--passos", nargs="+", help="só estes números de passo (ex.: 05 07)")
    parser.add_argument("--listar", action="store_true", help="lista os passos e sai")
    parser.add_argument("--forcar", action="store_true", help="bronze baixa de novo mesmo o que já existe")
    parser.add_argument("--origem", choices=["local", "azure"], default="local",
                        help="azure: antes de cada camada, baixa do Azure as camadas de que ela depende "
                             "(a bronze sempre vem da fonte, DATASUS/IBGE)")
    parser.add_argument("--versao", help="com --origem azure: versão (data de corte) a baixar; padrão: a mais recente")
    parser.add_argument("--manifesto", nargs="*", choices=["bronze", "silver", "gold"], metavar="CAMADA",
                        help="só (re)gera o _manifesto.json destas camadas (todas, se nenhuma for dada) e sai")
    args = parser.parse_args()

    sys.path.insert(0, str(PASTA))
    import config
    from comum import manifesto

    if args.manifesto is not None:
        for camada in args.manifesto or ["bronze", "silver", "gold"]:
            manifesto.gerar(camada)
        return

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

    # Uma só data de corte para todos os passos (cada passo é um processo novo e, sem isto,
    # uma execução que atravessa a meia-noite do fim do mês usaria períodos diferentes).
    if args.origem == "azure" and args.versao and not config.DATA_CORTE_EXPLICITA:
        os.environ["SARAMPO_DATA_CORTE"] = args.versao  # reproduzir a versão = usar a data de corte dela
        config.DATA_CORTE = config.date.fromisoformat(args.versao)
        config.DATA_CORTE_EXPLICITA = True
    os.environ["SARAMPO_DATA_CORTE"] = config.DATA_CORTE.isoformat()
    aviso = "" if config.DATA_CORTE_EXPLICITA else "  (padrão: hoje; para reproduzir, defina SARAMPO_DATA_CORTE)"
    print(f"\nData de corte: {config.DATA_CORTE.isoformat()}{aviso}")

    if args.origem == "azure":
        from baixar_azure import baixar_camada
        camadas = list(dict.fromkeys(c for _, c, _ in passos))
        pedidos: dict[str, list[str] | None] = {}
        for camada in camadas:
            for anterior, prefixos in ENTRADAS.get(camada, {}).items():
                if anterior in camadas:
                    continue  # vai ser gerada nesta mesma execução
                atual = pedidos.get(anterior, [])
                pedidos[anterior] = None if prefixos is None or atual is None else atual + prefixos
        for anterior, prefixos in pedidos.items():
            print(f"\n===== Baixando entrada do Azure: {anterior} {'(tudo)' if prefixos is None else prefixos} =====")
            baixar_camada(anterior, args.versao, prefixos)

    for numero, camada, arquivo in passos:
        print(f"\n===== Passo {numero} ({camada}): {arquivo.name} =====", flush=True)
        inicio = time.time()
        comando = [sys.executable, str(arquivo)] + (["--forcar"] if args.forcar else [])
        resultado = subprocess.run(comando, cwd=PASTA.parent)
        if resultado.returncode != 0:
            sys.exit(f"Passo {numero} falhou (código {resultado.returncode}). Os seguintes não foram executados.")
        print(f"Passo {numero} concluído em {time.time() - inicio:.0f} s")

    # Manifesto de cada camada que rodou: arquivos, hashes, código e ambiente usados.
    print()
    for camada in dict.fromkeys(c for _, c, _ in passos):
        manifesto.gerar(camada)


if __name__ == "__main__":
    main()
