"""Baixa todas as fontes da bronze sem acompanhamento (ex.: durante a noite).

Roda duas filas em paralelo, porque são servidores diferentes e uma não atrasa a outra:
    FTP do DATASUS:  01 SINAN, 16 população, 15 SINASC, 02 SI-PNI histórico, 04 IBGE
    S3 do MS:        03 SI-PNI nominal de jan/2020 até a data de corte, em duas filas (2020-2022
                     e 2023 em diante), porque a filtragem de cada mês é o gargalo

Para rodar sozinho:
    - cada passo que falha é repetido (até TENTATIVAS vezes, com espera crescente); todos os
      passos da bronze retomam de onde pararam, então repetir não refaz o que já foi baixado;
    - os arquivos grandes (.dbf do DPNI, .dbc do SINASC) só são baixados, sem conversão
      (SARAMPO_SO_BAIXAR=1): converter carrega o arquivo inteiro na memória e fica para depois;
    - guarda de disco: se o espaço livre (do Linux e, no WSL, do drive C: do Windows, onde fica
      o disco virtual) cair abaixo de --minimo-gb, encerra os passos e para, sem perder nada;
    - no WSL, pede ao Windows para não dormir enquanto roda (sem mudar configuração nenhuma:
      o pedido acaba junto com o script);
    - registra tudo em data/bronze/_download/: um log por passo, STATUS.txt (atualizado a cada
      minuto) e RESUMO.txt no fim.

Uso (da raiz do projeto, com o venv ativo):
    python pipeline/utilitarios/baixar_tudo.py              # data de corte = hoje
    python pipeline/utilitarios/baixar_tudo.py --verificar  # só mostra o plano e o espaço
Para deixar rodando e poder fechar a sessão SSH (no WSL, mantenha a janela do terminal aberta):
    nohup python pipeline/utilitarios/baixar_tudo.py > /dev/null 2>&1 &
Acompanhar: cat data/bronze/_download/STATUS.txt
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import date, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PIPELINE = RAIZ / "pipeline"
TENTATIVAS = 6
ESPERAS_MIN = [2, 5, 10, 20, 30]

FILAS = {
    "FTP do DATASUS": [("01", "01_bronze_sinan_sarampo.py", {}),
                       ("16", "16_bronze_populacao.py", {}),
                       ("15", "15_bronze_sinasc.py", {}),
                       ("02", "02_bronze_sipni_historico.py", {"SARAMPO_SO_BAIXAR": "1"}),
                       ("04", "04_bronze_ibge.py", {})],
    # Duas filas do passo 03 (cada uma com seu manifesto): a filtragem de cada mês é o
    # gargalo (CPU), e a banda dá conta das duas.
    "S3 do Ministério (2020-2022)": [("03a", "03_bronze_sipni_doses.py --anos 2020 2021 2022", {})],
    "S3 do Ministério (2023 em diante)": [("03b", "03_bronze_sipni_doses.py --anos {anos_recentes}", {})],
}
# Estimativa do que ainda falta baixar (GB no disco ao fim), para a checagem de espaço.
ESTIMATIVA_GB = {"01": 0.5, "16": 0.3, "15": 4.0, "02": 10.7, "04": 0.01, "03a": 20.0, "03b": 25.0}
STAGING_PICO_GB = 22  # por fila do 03, dois .zip de até ~5 GB (o atual e o próximo) + folga


class Execucao:
    def __init__(self, pasta_log: Path, minimo_gb: float):
        self.pasta_log = pasta_log
        self.minimo_gb = minimo_gb
        self.estado: dict[str, str] = {}
        self.processos: dict[str, subprocess.Popen] = {}
        self.parar = threading.Event()
        self.motivo_parada = ""
        self.inicio = datetime.now()
        self.trava = threading.Lock()

    def marcar(self, passo: str, texto: str) -> None:
        with self.trava:
            self.estado[passo] = f"{datetime.now():%H:%M} {texto}"


def espaco_livre_gb() -> dict[str, float]:
    livre = {"linux": shutil.disk_usage(RAIZ).free / 1e9}
    if Path("/mnt/c").exists():  # WSL: o disco virtual do Linux cresce dentro do C: do Windows
        livre["windows_c"] = shutil.disk_usage("/mnt/c").free / 1e9
    return livre


def rodar_passo(ex: Execucao, numero: str, script: str, env_extra: dict) -> bool:
    log = ex.pasta_log / f"passo_{numero}.log"
    for tentativa in range(1, TENTATIVAS + 1):
        if ex.parar.is_set():
            ex.marcar(numero, f"não executado ({ex.motivo_parada})")
            return False
        ex.marcar(numero, f"rodando (tentativa {tentativa}/{TENTATIVAS})")
        with log.open("a", encoding="utf-8") as saida:
            saida.write(f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S} tentativa {tentativa} =====\n")
            saida.flush()
            arquivo, *argumentos = script.split()
            proc = subprocess.Popen([sys.executable, "-u", str(PIPELINE / arquivo), *argumentos], cwd=RAIZ,
                                    stdout=saida, stderr=subprocess.STDOUT,
                                    env={**os.environ, **env_extra})
            ex.processos[numero] = proc
            codigo = proc.wait()
            ex.processos.pop(numero, None)
        if codigo == 0:
            ex.marcar(numero, f"CONCLUÍDO (tentativa {tentativa})")
            return True
        if ex.parar.is_set():
            ex.marcar(numero, f"interrompido ({ex.motivo_parada}); rode de novo para continuar")
            return False
        if tentativa < TENTATIVAS:
            espera = ESPERAS_MIN[min(tentativa - 1, len(ESPERAS_MIN) - 1)]
            ex.marcar(numero, f"falhou (código {codigo}); nova tentativa em {espera} min")
            if ex.parar.wait(espera * 60):
                continue
    ex.marcar(numero, f"FALHOU após {TENTATIVAS} tentativas (ver {log.name})")
    return False


def rodar_fila(ex: Execucao, passos: list) -> None:
    for numero, script, env_extra in passos:
        rodar_passo(ex, numero, script, env_extra)


def meses_sipni() -> str:
    m: dict = {}
    for manifesto in (RAIZ / "data" / "bronze" / "sipni_doses" / "_auditoria").glob("manifesto_*.json"):
        try:
            m.update(json.loads(manifesto.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass  # sendo regravado neste instante; aparece no próximo minuto
    if not m:
        return "-"
    contagem: dict[str, int] = {}
    for v in m.values():
        contagem[v.get("status", "?")] = contagem.get(v.get("status", "?"), 0) + 1
    atual = [k for k, v in sorted(m.items()) if v.get("status") in ("baixando", "filtrando")]
    return ", ".join(f"{k}: {n}" for k, n in sorted(contagem.items())) + (f" | agora: {atual[-1]}" if atual else "")


def escrever_status(ex: Execucao, arquivo: Path, final: bool = False) -> None:
    livre = espaco_livre_gb()
    linhas = [f"{'RESUMO FINAL' if final else 'STATUS'} do download da bronze - {datetime.now():%Y-%m-%d %H:%M}",
              f"início: {ex.inicio:%Y-%m-%d %H:%M} | decorrido: {str(datetime.now() - ex.inicio).split('.')[0]}",
              f"data de corte: {os.environ['SARAMPO_DATA_CORTE']} | SI-PNI nominal desde "
              f"{os.environ['SARAMPO_ANO_INICIAL_SIPNI_DOSES']}",
              "espaço livre: " + ", ".join(f"{k} {v:.0f} GB" for k, v in livre.items()), ""]
    for fila, passos in FILAS.items():
        linhas.append(f"[{fila}]")
        linhas += [f"  {n}  {s:<32} {ex.estado.get(n, 'aguardando')}" for n, s, _ in passos]
    linhas += ["", f"SI-PNI nominal (meses por status): {meses_sipni()}"]
    if ex.motivo_parada:
        linhas += ["", f"PARADO: {ex.motivo_parada}"]
    linhas += ["", f"logs: {ex.pasta_log}"]
    tmp = arquivo.with_suffix(".tmp")
    tmp.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    os.replace(tmp, arquivo)


def vigiar(ex: Execucao, status: Path) -> None:
    while not ex.parar.wait(60):
        livre = espaco_livre_gb()
        menor = min(livre.values())
        if menor < ex.minimo_gb:
            ex.motivo_parada = f"espaço livre abaixo de {ex.minimo_gb:.0f} GB ({menor:.0f} GB)"
            ex.parar.set()
            for proc in list(ex.processos.values()):
                proc.terminate()  # os passos gravam em .tmp: nada fica corrompido
        escrever_status(ex, status)


def manter_windows_acordado() -> subprocess.Popen | None:
    """No WSL, um PowerShell pede ao Windows para não suspender (SetThreadExecutionState) e
    fica esperando; ao ser encerrado, o pedido acaba. Não altera o plano de energia."""
    if not shutil.which("powershell.exe"):
        return None
    comando = ("$s='[DllImport(\"kernel32.dll\")] public static extern uint SetThreadExecutionState(uint f);';"
               "$k=Add-Type -MemberDefinition $s -Name Energia -Namespace Sarampo -PassThru;"
               "$null=$k::SetThreadExecutionState([uint32]'0x80000001');"
               "while($true){Start-Sleep -Seconds 60}")
    try:
        return subprocess.Popen(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", comando],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-corte", default=os.environ.get("SARAMPO_DATA_CORTE") or date.today().isoformat())
    parser.add_argument("--ano-inicial-sipni", default=os.environ.get("SARAMPO_ANO_INICIAL_SIPNI_DOSES") or "2020")
    parser.add_argument("--minimo-gb", type=float, default=40, help="para tudo se o espaço livre cair abaixo disto")
    parser.add_argument("--verificar", action="store_true", help="só mostra o plano e o espaço, sem baixar")
    args = parser.parse_args()
    os.environ["SARAMPO_DATA_CORTE"] = date.fromisoformat(args.data_corte).isoformat()
    os.environ["SARAMPO_ANO_INICIAL_SIPNI_DOSES"] = str(int(args.ano_inicial_sipni))
    corte = date.fromisoformat(os.environ["SARAMPO_DATA_CORTE"])
    anos_recentes = " ".join(str(a) for a in range(2023, corte.year + 1))
    for passos in FILAS.values():
        passos[:] = [(n, s.format(anos_recentes=anos_recentes), e) for n, s, e in passos]

    livre = espaco_livre_gb()
    necessario = sum(ESTIMATIVA_GB.values()) + STAGING_PICO_GB + args.minimo_gb
    print(f"Data de corte: {os.environ['SARAMPO_DATA_CORTE']} | SI-PNI nominal desde jan/{args.ano_inicial_sipni}")
    print("Espaço livre: " + ", ".join(f"{k} {v:.0f} GB" for k, v in livre.items()))
    print(f"Estimativa: ~{sum(ESTIMATIVA_GB.values()):.0f} GB de dados novos + {STAGING_PICO_GB} GB de pico "
          f"no staging + {args.minimo_gb:.0f} GB de margem = {necessario:.0f} GB")
    for fila, passos in FILAS.items():
        print(f"  {fila}: " + " -> ".join(n for n, _, _ in passos))
    if min(livre.values()) < necessario:
        sys.exit(f"Espaço insuficiente: precisa de ~{necessario:.0f} GB livres.")
    if args.verificar:
        return

    pasta_log = RAIZ / "data" / "bronze" / "_download" / datetime.now().strftime("%Y-%m-%d_%H%M")
    pasta_log.mkdir(parents=True, exist_ok=True)
    status = pasta_log.parent / "STATUS.txt"
    ex = Execucao(pasta_log, args.minimo_gb)
    acordado = manter_windows_acordado()
    print(f"Rodando. Acompanhe com: cat {status.relative_to(RAIZ)}"
          + (" | Windows impedido de dormir enquanto roda" if acordado else ""))

    vigia = threading.Thread(target=vigiar, args=(ex, status), daemon=True)
    vigia.start()
    filas = [threading.Thread(target=rodar_fila, args=(ex, passos), name=nome) for nome, passos in FILAS.items()]
    for t in filas:
        t.start()
    try:
        for t in filas:
            t.join()
    except KeyboardInterrupt:
        ex.motivo_parada = "interrompido pelo usuário (Ctrl+C)"
        ex.parar.set()
        for proc in list(ex.processos.values()):
            proc.terminate()
        for t in filas:
            t.join()
    finally:
        if acordado:
            acordado.terminate()
        ex.parar.set()
        escrever_status(ex, status)
        resumo = pasta_log.parent / "RESUMO.txt"
        escrever_status(ex, resumo, final=True)
        print(resumo.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
