"""Utilitário - move os dados da estrutura antiga (data/<dominio>/raw|processed) para a
estrutura medalhão (data/bronze|silver|gold/<fonte>), sem baixar nada de novo.

Só MOVE arquivos (renomeia, é instantâneo no mesmo disco); não apaga nenhum dado. Depois
de mover, corrige os caminhos absolutos gravados no manifesto do passo 03 e remove as
pastas antigas que ficaram vazias. Arquivos .py e qualquer arquivo sem regra conhecida
ficam onde estão e são listados no fim.

Por padrão só mostra o que faria (simulação). Para mover de verdade:
    python pipeline/utilitarios/migrar_estrutura_antiga.py --executar

Pode rodar mais de uma vez: o que já foi movido não está mais na origem, e um destino que
já existe nunca é sobrescrito (vira conflito na listagem).
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

ANTIGO_SARAMPO = config.DADOS / "sarampo"
ANTIGO_VACINACAO = config.DADOS / "vacinacao"
ANTIGO_GEO = config.DADOS / "geo"

HISTORICO = ("sipni_cobertura_vacinal_", "sipni_doses_aplicadas_agregado_")


def pasta_nova(arquivo: Path) -> Path | None:
    """Pasta nova de um arquivo da estrutura antiga, ou None se não houver regra."""
    if arquivo.suffix == ".py":
        return None
    nome = arquivo.name
    rel = arquivo.relative_to(config.DADOS).parts  # ex.: ("vacinacao", "processed", "gold", "x.csv")

    if rel[:2] == ("sarampo", "raw"):
        return config.BRONZE_SINAN
    if rel[:2] == ("sarampo", "processed"):
        return config.SILVER_SINAN

    if rel[:2] == ("vacinacao", "raw"):
        return config.BRONZE_SIPNI_HISTORICO if nome.startswith(HISTORICO) else config.BRONZE_SIPNI_MANUAL
    if rel[:2] == ("vacinacao", "processed"):
        sub = rel[2] if len(rel) > 3 else None
        if sub == "silver":
            return config.SILVER_SIPNI_DOSES
        if sub == "gold":
            return config.GOLD_VACINACAO
        if sub == "_auditoria":
            if nome == "processamento_resumo.json":
                return config.SILVER_SIPNI_DOSES_AUDITORIA
            return config.BRONZE_SIPNI_DOSES_AUDITORIA
        if sub is None:
            if nome.startswith(HISTORICO):
                return config.SILVER_SIPNI_HISTORICO
            if nome.startswith("sipni_doses_sarampo_sipni_"):
                return config.BRONZE_SIPNI_DOSES
            return config.BRONZE_SIPNI_MANUAL  # ex.: vacinacao_sarampo_2026_jan.csv, amostras

    if rel[0] == "geo" and len(rel) == 2:
        if nome == "populacao_municipios.csv":
            return config.SILVER_IBGE
        if nome in ("uf.json", "municipios.json", "uf_meta.json"):
            return config.BRONZE_IBGE
        if nome == "pop.json":
            return config.BRONZE_IBGE
    return None


def destino_de(arquivo: Path) -> Path | None:
    """Caminho novo do arquivo (mesmo nome, na pasta nova), ou None se não houver regra."""
    pasta = pasta_nova(arquivo)
    if pasta is None:
        return None
    nome = "populacao_sidra.json" if arquivo.name == "pop.json" else arquivo.name  # nome novo no passo 04
    return pasta / nome


def corrigir_manifesto(executar: bool) -> None:
    """O passo 03 grava o caminho absoluto de cada CSV mensal; aponta para a pasta nova.
    Troca só o trecho data/vacinacao/processed pelo novo, mantendo o separador original
    (assim o caminho continua no formato do Windows mesmo se a migração rodar em outro SO)."""
    manifesto = config.BRONZE_SIPNI_DOSES_AUDITORIA / "manifesto.json"
    if not manifesto.exists():
        manifesto = ANTIGO_VACINACAO / "processed" / "_auditoria" / "manifesto.json"  # simulação
    if not manifesto.exists():
        return
    dados = json.loads(manifesto.read_text(encoding="utf-8"))
    alterados = 0
    for entrada in dados.values():
        antigo = entrada.get("arquivo_saida")
        if not antigo:
            continue
        sep = "\\" if "\\" in antigo else "/"
        trecho_antigo = sep.join(["data", "vacinacao", "processed", ""])
        trecho_novo = sep.join(["data", "bronze", "sipni_doses", ""])
        if trecho_antigo in antigo:
            entrada["arquivo_saida"] = antigo.replace(trecho_antigo, trecho_novo)
            alterados += 1
    print(f"Manifesto: {alterados} caminhos {'corrigidos' if executar else 'seriam corrigidos'}.")
    if executar and alterados:
        tmp = manifesto.with_suffix(".tmp")
        tmp.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, manifesto)


def remover_pastas_vazias(raiz: Path) -> None:
    for pasta in sorted((p for p in raiz.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if not any(pasta.iterdir()):
            try:
                pasta.rmdir()
            except OSError as erro:  # sem permissão para apagar: a pasta vazia fica
                print(f"Não consegui remover a pasta vazia {pasta}: {erro}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--executar", action="store_true", help="move de verdade (sem isso, só simula)")
    args = parser.parse_args()

    movidos, conflitos, sem_regra = 0, [], []
    for raiz in (ANTIGO_SARAMPO, ANTIGO_VACINACAO, ANTIGO_GEO):
        if not raiz.exists():
            continue
        for arquivo in sorted(p for p in raiz.rglob("*") if p.is_file()):
            destino = destino_de(arquivo)
            if destino is None:
                sem_regra.append(arquivo)
                continue
            if destino.exists():
                conflitos.append((arquivo, destino))
                continue
            print(f"{arquivo.relative_to(config.RAIZ)}  ->  {destino.relative_to(config.RAIZ)}")
            if args.executar:
                destino.parent.mkdir(parents=True, exist_ok=True)
                os.replace(arquivo, destino)
            movidos += 1

    print(f"\n{movidos} arquivos {'movidos' if args.executar else 'seriam movidos'}.")
    corrigir_manifesto(args.executar)
    if conflitos:
        print("\nConflitos (destino já existe, nada foi feito):")
        for origem, destino in conflitos:
            print(f"  {origem.relative_to(config.RAIZ)}  x  {destino.relative_to(config.RAIZ)}")
    if sem_regra:
        print("\nFicaram no lugar (sem regra de migração):")
        for arquivo in sem_regra:
            print(f"  {arquivo.relative_to(config.RAIZ)}")
    if args.executar:
        for raiz in (ANTIGO_SARAMPO, ANTIGO_VACINACAO, ANTIGO_GEO):
            if raiz.exists():
                remover_pastas_vazias(raiz)
                if not any(raiz.iterdir()):
                    try:
                        raiz.rmdir()
                    except OSError as erro:
                        print(f"Não consegui remover a pasta vazia {raiz}: {erro}")
    else:
        print("\nSimulação. Rode com --executar para mover.")


if __name__ == "__main__":
    main()
