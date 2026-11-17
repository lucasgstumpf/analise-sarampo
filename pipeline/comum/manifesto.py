"""Manifesto de uma camada (bronze, silver ou gold): o que tem nela e como foi gerada.

Grava data/<camada>/_manifesto.json com:
    - parâmetros da execução (data de corte, períodos, ano da população);
    - código (commit do git e se havia alterações não commitadas);
    - ambiente (Python, sistema, versões dos pacotes, conversor de .dbc usado);
    - um registro por arquivo: caminho relativo, bytes, sha256 e, para .parquet, linhas e schema.

Dois manifestos com os mesmos `arquivos` descrevem exatamente os mesmos dados; é o que a
verificação de reprodutibilidade compara. Arquivos de controle que mudam a cada execução
(logs, manifesto de download com horários) ficam marcados com "volatil": true e não entram
na comparação.
"""

import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

import config

NOME = "_manifesto.json"
# Temporários e logs de execução (não são dados): staging de download, partes do passo 07,
# logs do download noturno; e a cópia antiga de jan/2026 vinda do Azure (_divisao).
IGNORAR_PASTAS = {"_staging", "_divisao", "__pycache__", "_download", "_partes", "_numeracao", "_duckdb_tmp"}
IGNORAR_NOMES = {"_download_nohup.log"}
IGNORAR_SUFIXOS = {".tmp"}
VOLATEIS = {"extract_recentes.log", "manifesto.json"}  # registram horários de cada execução
PACOTES = ["pandas", "numpy", "pyarrow", "dbfread", "duckdb", "numba"]


def sha256(arquivo: Path, bloco: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with arquivo.open("rb") as f:
        while parte := f.read(bloco):
            h.update(parte)
    return h.hexdigest()


def _git(*args: str) -> str | None:
    try:
        return subprocess.run(["git", *args], cwd=config.RAIZ, capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _versao(pacote: str) -> str | None:
    try:
        return metadata.version(pacote)
    except metadata.PackageNotFoundError:
        return None


def _conversor_dbc() -> str:
    try:
        import numba  # noqa: F401
        return "comum/dbc_rapido.py (numba)"
    except ImportError:
        return "comum/dbc_puro.py"

def _registro(arquivo: Path, pasta: Path) -> dict:
    item = {"caminho": arquivo.relative_to(pasta).as_posix(), "bytes": arquivo.stat().st_size,
            "sha256": sha256(arquivo)}
    if arquivo.name in VOLATEIS or arquivo.name.endswith(".origem.json"):  # têm a data do download
        item["volatil"] = True
    if arquivo.suffix == ".parquet":
        import pyarrow.parquet as pq
        meta = pq.read_metadata(arquivo)
        item["linhas"] = meta.num_rows
        item["schema"] = {campo.name: str(campo.type) for campo in meta.schema.to_arrow_schema()}
    return item


def listar(pasta: Path) -> list[Path]:
    return sorted(
        a for a in pasta.rglob("*")
        if a.is_file() and a.name != NOME and a.suffix not in IGNORAR_SUFIXOS and a.name not in IGNORAR_NOMES
        and not IGNORAR_PASTAS.intersection(a.relative_to(pasta).parts)
    )


def gerar(camada: str) -> Path:
    pasta = config.DADOS / camada
    manifesto = {
        "camada": camada,
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "parametros": {
            "data_corte": config.DATA_CORTE.isoformat(),
            "data_corte_explicita": config.DATA_CORTE_EXPLICITA,
            "ano_inicial_sipni_doses": config.ANO_INICIAL_SIPNI_DOSES,
            "ano_populacao_ibge": config.ANO_POPULACAO_IBGE,
        },
        "codigo": {
            "commit": _git("rev-parse", "HEAD"),
            "alteracoes_locais": bool(_git("status", "--porcelain", "--", "pipeline")),
        },
        "ambiente": {
            "python": platform.python_version(),
            "sistema": f"{platform.system()} {platform.machine()}",
            "pacotes": {p: _versao(p) for p in PACOTES},
            "conversor_dbc": _conversor_dbc(),
        },
        "arquivos": [_registro(a, pasta) for a in listar(pasta)],
    }
    destino = pasta / NOME
    destino.write_text(json.dumps(manifesto, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    total = sum(a["bytes"] for a in manifesto["arquivos"])
    print(f"Manifesto {camada}: {len(manifesto['arquivos'])} arquivos, {total / 1e9:.2f} GB -> {destino}")
    return destino


def comparar(a: dict, b: dict) -> list[str]:
    """Diferenças entre os arquivos (não voláteis) de dois manifestos da mesma camada."""
    def indice(m: dict) -> dict:
        return {x["caminho"]: x["sha256"] for x in m["arquivos"] if not x.get("volatil")}
    ia, ib = indice(a), indice(b)
    difs = [f"só no primeiro: {c}" for c in sorted(ia.keys() - ib.keys())]
    difs += [f"só no segundo: {c}" for c in sorted(ib.keys() - ia.keys())]
    difs += [f"conteúdo diferente: {c}" for c in sorted(ia.keys() & ib.keys()) if ia[c] != ib[c]]
    return difs


if __name__ == "__main__":
    for nome in sys.argv[1:] or ["bronze", "silver", "gold"]:
        gerar(nome)
