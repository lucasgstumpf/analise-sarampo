"""Passo 03 (bronze) - Doses individuais de vacinas com sarampo, SI-PNI/RNDS, 2025 em diante.

Fonte: desde 2020 os dados nominais (anonimizados) do SI-PNI são publicados fora do FTP, em
.zip mensais com TODOS os imunobiológicos (bucket S3 público do Ministério da Saúde):
    https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/PNI/csv/vacinacao_{mmm}_{AAAA}_csv.zip

Cada .zip tem 1-2 GB. Para cada mês de config.PERIODO_SIPNI_DOSES:
    1. baixa o .zip para STAGING_DIR (com retomada via HTTP Range e novas tentativas);
    2. lê o CSV de dentro do .zip em pedaços e guarda só as doses de sarampo, já com as
       colunas renomeadas (comum.dicionarios.COLUNAS_SIPNI);
    3. aproveita a mesma leitura para guardar um retrato da base COMPLETA (todas as vacinas):
       doses por imunobiológico e um perfil de cada coluna (% vazio, valores distintos);
    4. apaga o .zip só depois de o filtrado estar gravado e registrado no manifesto.

Exceção à regra da bronze: aqui o dado já sai filtrado e renomeado, porque guardar os .zip
completos ocuparia dezenas de GB por ano. A limpeza de verdade fica no passo 07.

Auditoria: manifesto.json (uma entrada por mês, com status, tamanhos, linhas lidas e
mantidas) e extract_recentes.log. Se o processo cair, rodar de novo retoma de onde parou:
meses "concluido" (com o CSV em disco) são pulados, meses "nao_publicado" ou "falhou" são
tentados de novo, e um .zip pela metade no staging continua do byte onde parou. Se o .zip
estiver corrompido, ele é apagado e baixado do zero automaticamente (uma vez). Com
--forcar, todos os meses do período são baixados de novo; com --meses AAAA-MM [...], só os
meses indicados são (re)processados, mesmo que já estejam concluídos.

Saída: data/bronze/sipni_doses/sipni_doses_sarampo_sipni_{AAAA}_{mmm}.csv  (um por mês)
       data/bronze/sipni_doses/sipni_doses_sarampo_sipni_2025_{AAAA}_completo.csv  (junção)
       data/bronze/sipni_doses/_auditoria/{manifesto.json, extract_recentes.log}
       data/bronze/sipni_doses/_perfil_bruto/imunobiologicos_{AAAA}_{mmm}.csv
       data/bronze/sipni_doses/_perfil_bruto/perfil_colunas_{AAAA}_{mmm}.csv
Uso:   python pipeline/03_bronze_sipni_doses.py [--forcar] [--meses 2026-01 2026-02]
       (variável de ambiente SARAMPO_STAGING_DIR muda a pasta temporária dos .zip)
"""

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile
import zlib
from datetime import datetime
from pathlib import Path

import pandas as pd

import config
from comum.datasus import renomear_colunas
from comum.dicionarios import COLUNAS_SIPNI, filtro_vacinas_sarampo

URL_TEMPLATE_SIPNI = "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/PNI/csv/vacinacao_{mes}_{ano}_csv.zip"

SAIDA_DIR = config.BRONZE_SIPNI_DOSES
AUDIT_DIR = config.BRONZE_SIPNI_DOSES_AUDITORIA
MANIFESTO = AUDIT_DIR / "manifesto.json"
LOG_FILE = AUDIT_DIR / "extract_recentes.log"
NOME_BASE_COMBINADO = f"sipni_doses_sarampo_sipni_2025_{config.ANO_FINAL_SIPNI_DOSES}_completo"
MAX_TENTATIVAS_DOWNLOAD = 5
# Erros de leitura que indicam .zip danificado (e não problema no código ou nos dados).
ZIP_CORROMPIDO = (zipfile.BadZipFile, zlib.error, EOFError)

log = logging.getLogger("bronze_sipni_doses")


def arquivo_mensal(ano: int, mes: int) -> Path:
    return SAIDA_DIR / f"sipni_doses_sarampo_sipni_{ano}_{config.MESES_ABREV[mes - 1]}.csv"


def configurar_log() -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    for handler in (logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler()):
        handler.setFormatter(fmt)
        log.addHandler(handler)
    log.setLevel(logging.INFO)


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


# Manifesto de auditoria: uma entrada por mês, regravada de forma atômica a cada mudança
# de etapa. Se o processo cair, a próxima execução sabe exatamente o que já foi concluído.
def carregar_manifesto() -> dict:
    if MANIFESTO.exists():
        return json.loads(MANIFESTO.read_text(encoding="utf-8"))
    return {}


def salvar_manifesto(manifesto: dict) -> None:
    tmp = MANIFESTO.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifesto, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, MANIFESTO)


def atualizar(manifesto: dict, chave: str, **campos) -> None:
    manifesto.setdefault(chave, {}).update(campos, atualizado_em=agora())
    salvar_manifesto(manifesto)


def tamanho_remoto(url: str) -> int:
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return int(resp.headers["Content-Length"])


def baixar_com_retomada(url: str, destino: Path, tamanho_esperado: int) -> None:
    """Download em streaming com retomada (HTTP Range) e novas tentativas: se a conexão
    cair, continua do byte onde parou em vez de recomeçar vários GB."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    for tentativa in range(1, MAX_TENTATIVAS_DOWNLOAD + 1):
        baixado = destino.stat().st_size if destino.exists() else 0
        if baixado == tamanho_esperado:
            return
        if baixado > tamanho_esperado:
            destino.unlink()
            baixado = 0
        try:
            req = urllib.request.Request(url, headers={"Range": f"bytes={baixado}-"} if baixado else {})
            with urllib.request.urlopen(req, timeout=60) as resp:
                if baixado and resp.status != 206:  # servidor ignorou o Range: recomeça
                    baixado = 0
                with open(destino, "ab" if baixado else "wb") as arquivo:
                    while bloco := resp.read(1024 * 1024):
                        arquivo.write(bloco)
        except (urllib.error.URLError, OSError, TimeoutError) as erro:
            if isinstance(erro, urllib.error.HTTPError) and erro.code in (403, 404):
                raise
            log.warning("Download interrompido (tentativa %d/%d): %s", tentativa, MAX_TENTATIVAS_DOWNLOAD, erro)
            time.sleep(5 * tentativa)
    if not destino.exists() or destino.stat().st_size != tamanho_esperado:
        raise IOError(f"Download incompleto de {url}")


class PerfilBruto:
    """Retrato da base mensal completa (todas as vacinas), montado chunk a chunk durante o
    filtro: doses por imunobiológico e, para cada coluna, quantos valores vazios e quantos
    valores distintos (contados até LIMITE_DISTINTOS, para não estourar a memória com as
    colunas de identificador). Alimenta os notebooks 02 e 03 via gold (passo 10)."""

    LIMITE_DISTINTOS = 100_000

    def __init__(self) -> None:
        self.linhas = 0
        self.vazios: pd.Series | None = None
        self.distintos: dict[str, set | None] = {}
        self.exemplo: dict[str, str] = {}
        self.contagem: pd.Series | None = None

    def adicionar(self, chunk: pd.DataFrame) -> None:
        self.linhas += len(chunk)
        vazios = chunk.isna().sum()
        self.vazios = vazios if self.vazios is None else self.vazios.add(vazios, fill_value=0)
        for coluna in chunk.columns:
            valores = self.distintos.setdefault(coluna, set())
            if valores is None:
                continue
            nao_vazios = chunk[coluna].dropna()
            if coluna not in self.exemplo and len(nao_vazios):
                self.exemplo[coluna] = nao_vazios.iat[0]
            valores.update(nao_vazios.unique())
            if len(valores) > self.LIMITE_DISTINTOS:
                self.distintos[coluna] = None  # alta cardinalidade: para de contar
        por_vacina = chunk.groupby(["ds_nome", "sg_imunobiologico"], dropna=False).size()
        self.contagem = por_vacina if self.contagem is None else self.contagem.add(por_vacina, fill_value=0)

    def gravar(self, ano: int, mes: int) -> None:
        abrev = config.MESES_ABREV[mes - 1]
        pasta = config.BRONZE_SIPNI_PERFIL_BRUTO
        pasta.mkdir(parents=True, exist_ok=True)
        contagem = self.contagem.astype("int64").rename("doses").reset_index()
        contagem.columns = ["ds_nome", "sg_imunobiologico", "doses"]
        contagem.sort_values("doses", ascending=False).to_csv(
            pasta / f"imunobiologicos_{ano}_{abrev}.csv", index=False, encoding="utf-8")
        perfil = pd.DataFrame({
            "coluna": list(self.distintos),
            "linhas": self.linhas,
            "vazios": [int(self.vazios.get(c, 0)) for c in self.distintos],
            "distintos": [len(v) if v is not None else None for v in self.distintos.values()],
            "distintos_acima_do_limite": [v is None for v in self.distintos.values()],
            "exemplo": [self.exemplo.get(c) for c in self.distintos],
        })
        perfil.to_csv(pasta / f"perfil_colunas_{ano}_{abrev}.csv", index=False, encoding="utf-8")


def filtrar_zip_para_csv(arquivo_zip: Path, destino: Path, perfil: PerfilBruto | None = None) -> tuple[int, int]:
    """Lê o CSV dentro do .zip em chunks e grava só as doses de sarampo (colunas já
    renomeadas) em `destino`. Se `perfil` for passado, também acumula nele o retrato da
    base completa. Retorna (linhas_lidas, linhas_sarampo)."""
    tmp = destino.with_suffix(".tmp")
    lidas = mantidas = 0
    primeiro = True
    with zipfile.ZipFile(arquivo_zip) as z:
        csvs = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if len(csvs) != 1:
            raise ValueError(f"Esperava 1 CSV no zip, encontrei: {z.namelist()}")
        with z.open(csvs[0]) as f:
            for chunk in pd.read_csv(
                f, sep=";", encoding="latin-1", dtype=str, chunksize=config.TAMANHO_CHUNK, on_bad_lines="skip"
            ):
                lidas += len(chunk)
                if perfil is not None:
                    perfil.adicionar(chunk)
                sel = renomear_colunas(chunk[filtro_vacinas_sarampo(chunk)], COLUNAS_SIPNI)
                sel.to_csv(tmp, mode="w" if primeiro else "a", index=False, header=primeiro, encoding="utf-8")
                primeiro = False
                mantidas += len(sel)
    if primeiro:
        tmp.write_text("", encoding="utf-8")
    os.replace(tmp, destino)  # só ganha o nome final se terminou por completo
    return lidas, mantidas


def processar_mes(ano: int, mes: int, manifesto: dict, refazer: bool = False) -> None:
    chave = f"{ano}-{mes:02d}"
    abrev = config.MESES_ABREV[mes - 1]
    url = URL_TEMPLATE_SIPNI.format(mes=abrev, ano=ano)
    saida = arquivo_mensal(ano, mes)
    zip_path = config.STAGING_DIR / f"vacinacao_{abrev}_{ano}_csv.zip"

    concluido = manifesto.get(chave, {}).get("status") == "concluido" and saida.exists()
    if concluido and not (config.FORCAR_DOWNLOAD or refazer):
        log.info("%s já concluído, pulando.", chave)
        return

    inicio = time.time()
    atualizar(manifesto, chave, status="baixando", url=url, iniciado_em=agora(), erro=None)
    try:
        tamanho = tamanho_remoto(url)
    except urllib.error.HTTPError as erro:
        if erro.code in (403, 404):
            log.warning("%s não publicado (HTTP %s): %s", chave, erro.code, url)
            atualizar(manifesto, chave, status="nao_publicado", erro=f"HTTP {erro.code}")
            return
        raise
    log.info("%s: baixando %.2f GB para %s", chave, tamanho / 1e9, zip_path)
    atualizar(manifesto, chave, tamanho_zip_bytes=tamanho)
    baixar_com_retomada(url, zip_path, tamanho)

    atualizar(manifesto, chave, status="filtrando")
    log.info("%s: filtrando sarampo...", chave)
    try:
        perfil = PerfilBruto()
        lidas, mantidas = filtrar_zip_para_csv(zip_path, saida, perfil)
    except ZIP_CORROMPIDO as erro:
        # O tamanho bate, mas o conteúdo não (ex.: retomada de um download antigo depois de
        # o arquivo ser republicado). Apaga o .zip e baixa do zero, uma vez.
        log.warning("%s: zip corrompido (%s); apagando e baixando do zero.", chave, erro)
        zip_path.unlink()
        atualizar(manifesto, chave, status="baixando", erro=f"zip corrompido, baixado de novo: {erro!r}")
        baixar_com_retomada(url, zip_path, tamanho)
        atualizar(manifesto, chave, status="filtrando")
        perfil = PerfilBruto()
        lidas, mantidas = filtrar_zip_para_csv(zip_path, saida, perfil)
    perfil.gravar(ano, mes)

    atualizar(
        manifesto, chave, status="concluido", linhas_lidas=lidas, linhas_sarampo=mantidas,
        arquivo_saida=str(saida), tamanho_saida_bytes=saida.stat().st_size,
        duracao_s=round(time.time() - inicio), concluido_em=agora(),
    )
    # Só apaga a base original depois de o filtrado estar gravado e registrado.
    zip_path.unlink()
    atualizar(manifesto, chave, zip_removido=True)
    log.info("%s: %d doses de sarampo em %d linhas; zip removido.", chave, mantidas, lidas)


def combinar_meses(manifesto: dict) -> None:
    """Junta os CSVs mensais concluídos num arquivo só. O caminho de cada mês é recalculado
    a partir de config (e não lido do manifesto), para continuar funcionando se a pasta
    do projeto mudar de lugar."""
    arquivos = [
        arquivo_mensal(ano, mes)
        for ano, mes in config.PERIODO_SIPNI_DOSES  # o manifesto pode acumular outros períodos
        if manifesto.get(f"{ano}-{mes:02d}", {}).get("status") == "concluido"
        and arquivo_mensal(ano, mes).exists() and arquivo_mensal(ano, mes).stat().st_size > 0
    ]
    destino = SAIDA_DIR / f"{NOME_BASE_COMBINADO}.csv"
    tmp = destino.with_suffix(".tmp")
    total = 0
    for arquivo in arquivos:
        for chunk in pd.read_csv(arquivo, dtype=str, chunksize=config.TAMANHO_CHUNK):
            chunk.to_csv(tmp, mode="a" if total else "w", index=False, header=not total, encoding="utf-8")
            total += len(chunk)
    if arquivos:
        os.replace(tmp, destino)
    log.info("Combinado: %s (%d registros, %d meses)", destino, total, len(arquivos))


def main() -> None:
    parser = argparse.ArgumentParser(description="Bronze das doses do SI-PNI (2025+).")
    parser.add_argument("--forcar", action="store_true", help="baixa de novo todos os meses do período")
    parser.add_argument("--meses", nargs="+", metavar="AAAA-MM", help="(re)processa só estes meses")
    args = parser.parse_args()
    meses = config.PERIODO_SIPNI_DOSES
    if args.meses:
        pedidos = {tuple(int(x) for x in m.split("-")) for m in args.meses}
        meses = [am for am in meses if am in pedidos]

    SAIDA_DIR.mkdir(parents=True, exist_ok=True)
    config.STAGING_DIR.mkdir(parents=True, exist_ok=True)
    configurar_log()
    manifesto = carregar_manifesto()
    log.info("Início. Staging: %s | Meses: %s", config.STAGING_DIR, [f"{a}-{m:02d}" for a, m in meses])

    for ano, mes in meses:
        try:
            processar_mes(ano, mes, manifesto, refazer=bool(args.meses))
        except Exception as erro:  # registra e segue para o próximo mês; rerodar retoma
            log.exception("%d-%02d falhou", ano, mes)
            atualizar(manifesto, f"{ano}-{mes:02d}", status="falhou", erro=repr(erro))

    combinar_meses(manifesto)
    resumo = {k: v.get("status") for k, v in sorted(manifesto.items())}
    log.info("Resumo: %s", resumo)
    if "falhou" in resumo.values():
        sys.exit(1)


if __name__ == "__main__":
    main()
