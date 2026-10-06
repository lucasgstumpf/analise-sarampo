import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from datasus_lib import renomear_colunas

PROCESSED_DIR = Path(__file__).parent / "processed"

# Os .zip mensais têm vários GB: o download (temporário) vai para o HD D:, não para o
# disco do projeto. Sobrescreva com a variável de ambiente SARAMPO_STAGING_DIR se precisar.
STAGING_DIR = Path(os.environ.get("SARAMPO_STAGING_DIR", r"D:\analise-sarampo\staging"))
# Auditoria (manifesto JSON + log) fica em processed/_auditoria, junto do resultado.
AUDIT_DIR = PROCESSED_DIR / "_auditoria"
MANIFESTO = AUDIT_DIR / "manifesto.json"
LOG_FILE = AUDIT_DIR / "extract_recentes.log"

# Doses de sarampo pós-2019 (SI-PNI/RNDS), registros individuais. Desde 2020 os dados
# nominais são publicados fora do FTP, em .zip mensais com TODOS os imunobiológicos
# (bucket S3 público). Baixamos cada mês, filtramos em streaming só as doses de sarampo,
# guardamos o filtrado e apagamos o .zip original.
URL_TEMPLATE_SIPNI = "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/PNI/csv/vacinacao_{mes}_{ano}_csv.zip"

MESES_ABREV = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

# Período a coletar. Meses ainda não publicados são registrados como "nao_publicado".
PERIODO = [(2025, mes) for mes in range(1, 13)]  # jan-dez/2025
TAMANHO_CHUNK = 200_000
MAX_TENTATIVAS_DOWNLOAD = 5


# Filtra pela descrição (ds_nome), não pela sigla: siglas variam por fabricante/clínica
# (ex.: SCRV, SCRV-2), enquanto a descrição cobre todas as variantes de forma robusta.
def filtro_vacinas_sarampo(chunk: pd.DataFrame) -> pd.Series:
    return chunk["ds_nome"].str.contains("sarampo", case=False, na=False)


NOME_BASE_COMBINADO_SIPNI = "sipni_doses_sarampo_sipni_2025_completo"

COLUMN_MAP_SIPNI = {
    "co_documento": "codigo_documento",
    "co_paciente": "codigo_paciente_anonimizado",
    "tp_sexo_paciente": "sexo_paciente",
    "co_raca_cor_paciente": "codigo_raca_cor_paciente",
    "no_raca_cor_paciente": "raca_cor_paciente",
    "co_municipio_paciente": "codigo_municipio_paciente",
    "co_pais_paciente": "codigo_pais_paciente",
    "no_municipio_paciente": "municipio_paciente",
    "no_pais_paciente": "pais_paciente",
    "sg_uf_paciente": "uf_paciente",
    "nu_cep_paciente": "cep_paciente",
    "ds_nacionalidade_paciente": "nacionalidade_paciente",
    "no_etnia_indigena_paciente": "etnia_indigena_paciente",
    "co_etnia_indigena_paciente": "codigo_etnia_indigena_paciente",
    "co_cnes_estabelecimento": "codigo_cnes_estabelecimento",
    "no_razao_social_estabelecimento": "razao_social_estabelecimento",
    "no_fantasia_estalecimento": "nome_fantasia_estabelecimento",
    "co_municipio_estabelecimento": "codigo_municipio_estabelecimento",
    "no_municipio_estabelecimento": "municipio_estabelecimento",
    "sg_uf_estabelecimento": "uf_estabelecimento",
    "co_troca_documento": "codigo_documento_substituido",
    "co_vacina": "codigo_vacina",
    "sg_imunobiologico": "sigla_vacina",
    "dt_vacina": "data_vacinacao",
    "co_dose_vacina": "codigo_dose_vacina",
    "ds_tipo_dose": "descricao_dose_vacina",
    "co_local_aplicacao": "codigo_local_aplicacao",
    "ds_local_aplicacao": "descricao_local_aplicacao",
    "co_via_administracao": "codigo_via_administracao",
    "ds_via_administracao": "descricao_via_administracao",
    "co_lote_vacina": "lote_vacina",
    "ds_vacina_fabricante": "fabricante_vacina",
    "dt_entrada_rnds": "data_entrada_rnds",
    "co_sistema_origem": "codigo_sistema_origem",
    "ds_sistema_origem": "sistema_origem",
    "st_documento": "status_documento",
    "co_estrategia_vacinacao": "codigo_estrategia_vacinacao",
    "no_estrategia": "estrategia_vacinacao",
    "co_origem_registro": "codigo_origem_registro",
    "ds_origem_registro": "origem_registro",
    "co_vacina_grupo_atendimento": "codigo_grupo_atendimento",
    "no_grupo_atendimento": "grupo_atendimento",
    "co_categoria": "codigo_categoria_atendimento",
    "ds_categoria": "categoria_atendimento",
    "co_vacina_fabricante": "codigo_fabricante_vacina",
    "ds_nome": "descricao_vacina",
    "ds_condicao_maternal": "condicao_maternal",
    "co_tipo_estabelecimento": "codigo_tipo_estabelecimento",
    "ds_tipo_estabelecimento": "tipo_estabelecimento",
    "co_natureza_estabelecimento": "codigo_natureza_estabelecimento",
    "ds_natureza_estabelecimento": "natureza_estabelecimento",
    "nu_idade_paciente": "idade_paciente",
    "co_condicao_maternal": "codigo_condicao_maternal",
    "no_uf_paciente": "nome_uf_paciente",
    "no_uf_estabelecimento": "nome_uf_estabelecimento",
    "dt_deletado_rnds": "data_delecao_rnds",
}

log = logging.getLogger("extract_recentes")


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


def filtrar_zip_para_csv(arquivo_zip: Path, destino: Path) -> tuple[int, int]:
    """Lê o CSV dentro do .zip em chunks e grava só as doses de sarampo (colunas já
    renomeadas) em `destino`. Retorna (linhas_lidas, linhas_sarampo)."""
    tmp = destino.with_suffix(".tmp")
    lidas = mantidas = 0
    primeiro = True
    with zipfile.ZipFile(arquivo_zip) as z:
        csvs = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if len(csvs) != 1:
            raise ValueError(f"Esperava 1 CSV no zip, encontrei: {z.namelist()}")
        with z.open(csvs[0]) as f:
            for chunk in pd.read_csv(
                f, sep=";", encoding="latin-1", dtype=str, chunksize=TAMANHO_CHUNK, on_bad_lines="skip"
            ):
                lidas += len(chunk)
                sel = renomear_colunas(chunk[filtro_vacinas_sarampo(chunk)], COLUMN_MAP_SIPNI)
                sel.to_csv(tmp, mode="w" if primeiro else "a", index=False, header=primeiro, encoding="utf-8")
                primeiro = False
                mantidas += len(sel)
    if primeiro:
        tmp.write_text("", encoding="utf-8")
    os.replace(tmp, destino)  # só ganha o nome final se terminou por completo
    return lidas, mantidas


def processar_mes(ano: int, mes: int, manifesto: dict) -> None:
    chave = f"{ano}-{mes:02d}"
    abrev = MESES_ABREV[mes - 1]
    url = URL_TEMPLATE_SIPNI.format(mes=abrev, ano=ano)
    saida = PROCESSED_DIR / f"sipni_doses_sarampo_sipni_{ano}_{abrev}.csv"
    zip_path = STAGING_DIR / f"vacinacao_{abrev}_{ano}_csv.zip"

    if manifesto.get(chave, {}).get("status") == "concluido" and saida.exists():
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
    lidas, mantidas = filtrar_zip_para_csv(zip_path, saida)

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
    arquivos = [
        Path(m["arquivo_saida"])
        for chave, m in sorted(manifesto.items())
        if chave in {f"{a}-{mes:02d}" for a, mes in PERIODO}  # o manifesto acumula outros períodos
        if m.get("status") == "concluido" and Path(m["arquivo_saida"]).stat().st_size > 0
    ]
    destino = PROCESSED_DIR / f"{NOME_BASE_COMBINADO_SIPNI}.csv"
    tmp = destino.with_suffix(".tmp")
    total = 0
    for arquivo in arquivos:
        for chunk in pd.read_csv(arquivo, dtype=str, chunksize=TAMANHO_CHUNK):
            chunk.to_csv(tmp, mode="a" if total else "w", index=False, header=not total, encoding="utf-8")
            total += len(chunk)
    if arquivos:
        os.replace(tmp, destino)
    log.info("Combinado: %s (%d registros, %d meses)", destino, total, len(arquivos))


def coletar_doses_sarampo_sipni() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    configurar_log()
    manifesto = carregar_manifesto()
    log.info("Início. Staging: %s | Meses: %s", STAGING_DIR, [f"{a}-{m:02d}" for a, m in PERIODO])

    for ano, mes in PERIODO:
        try:
            processar_mes(ano, mes, manifesto)
        except Exception as erro:  # registra e segue para o próximo mês; rerodar retoma
            log.exception("%d-%02d falhou", ano, mes)
            atualizar(manifesto, f"{ano}-{mes:02d}", status="falhou", erro=repr(erro))

    combinar_meses(manifesto)
    resumo = {k: v.get("status") for k, v in sorted(manifesto.items())}
    log.info("Resumo: %s", resumo)
    if "falhou" in resumo.values():
        sys.exit(1)


def main() -> None:
    coletar_doses_sarampo_sipni()


if __name__ == "__main__":
    main()
