"""Consulta a cobertura vacinal oficial no TabNet do DATASUS e grava como referência.

Fonte: TabNet "Imunizações - Cobertura - Brasil" (bd_pni/cpnibr.def), SI-PNI/CGPNI/SVS/MS,
       http://tabnet.datasus.gov.br/cgi/dhdat.exe?bd_pni/cpnibr.def  (1994 a 2022)
Parâmetros (os mesmos de quem preenche o formulário à mão):
    Linha = Unidade da Federação | Coluna = Ano | Medida = o indicador | Períodos = todos
    Sem filtros (todas as regiões e UFs) | Formato = tabela, exportada em CSV
Indicadores: Tríplice Viral D1 (021), Tríplice Viral D2 (098), Tetra Viral (097), Sarampo (018).

O TabNet avisa: "Não considerar na extração dos dados do TABNET Cobertura Vacinal a coluna e
linha com o TOTAL" (o total soma populações de vacinas diferentes); por isso o total não é
guardado. A partir de 2023 os dados estão só nos painéis do infoms.saude.gov.br, que não
exportam.

Saída: data/referencia/fontes/tabnet_cpni_{indicador}[_brasil]_{AAAA-MM-DD}.csv  (CSVs exportados,
           como vieram: por UF e nacional; o Brasil vem da consulta nacional, Linha = Ano)
       data/referencia/tabnet_cobertura_uf_ano.csv
           indicador, codigo_imunobiologico, codigo_uf, uf, ano, cobertura_percentual, consultado_em
Uso:   python pipeline/utilitarios/consultar_tabnet.py
       (é uma referência: rodar de novo cria arquivos novos em fontes/ com a data da consulta)
"""

import csv
import hashlib
import io
import re
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

BASE = "http://tabnet.datasus.gov.br/cgi/"
DEF = "bd_pni/cpnibr.def"
INDICADORES = {  # rótulo no formulário -> (nome curto, código do imunobiológico no CPNI)
    "Tríplice Viral  D1": ("triplice_viral_d1", "021"),
    "Tríplice Viral  D2": ("triplice_viral_d2", "098"),
    "Tetra Viral(SRC+VZ)": ("tetra_viral", "097"),
    "Sarampo": ("sarampo_monovalente", "018"),
}
REFERENCIA = config.RAIZ / "data" / "referencia"
CABECALHO = {"User-Agent": "Mozilla/5.0 (pipeline sarampo; consulta TabNet)"}


def baixar(url: str, dados: bytes | None = None) -> bytes:
    req = urllib.request.Request(url, data=dados, headers=CABECALHO)
    with urllib.request.urlopen(req, timeout=180) as resp:
        return resp.read()


def opcao(pagina: str, select: str, rotulo: str) -> str:
    bloco = re.search(r'NAME="%s"[^>]*>(.*?)</SELECT>' % re.escape(select), pagina, re.S | re.I).group(1)
    for valor, texto in re.findall(r'<option value="([^"]*)"[^>]*>([^<\n]*)', bloco, re.I):
        if texto.strip() == rotulo.strip():
            return valor
    raise KeyError(f"opção {rotulo!r} não encontrada em {select}")


def consultar(pagina: str, rotulo: str, nacional: bool = False) -> bytes:
    """Por UF (Linha = UF, Coluna = Ano) ou nacional (Linha = Ano, sem coluna)."""
    anos = re.findall(r'<option value="(\d{4}\|\d{4}\|4)"', pagina)
    linha_coluna = ([("Linha", opcao(pagina, "Linha", "Ano")), ("Coluna", "--Não-Ativa--")] if nacional else
                    [("Linha", opcao(pagina, "Linha", "Unidade da Federação")), ("Coluna", opcao(pagina, "Coluna", "Ano"))])
    campos = (linha_coluna + [
               ("Incremento", opcao(pagina, "Incremento", rotulo))]
              + [("PAno", a) for a in anos]
              + [("SRegião", "TODAS_AS_CATEGORIAS__"), ("SUnidade da Federação", "TODAS_AS_CATEGORIAS__"),
                 ("formato", "table"), ("mostre", "Mostra")])
    resposta = baixar(BASE + "webtabx.exe?" + DEF, urllib.parse.urlencode(campos, encoding="latin-1").encode())
    link = re.search(rb'HREF=(csv/[^>\s]+\.csv)', resposta, re.I)
    if not link:
        raise RuntimeError(f"o TabNet não devolveu o CSV de {rotulo!r}")
    return baixar(BASE + link.group(1).decode())


def ler_csv_tabnet(conteudo: bytes) -> tuple[list[str], list[list[str]]]:
    linhas = list(csv.reader(io.StringIO(conteudo.decode("latin-1")), delimiter=";"))
    i = next(n for n, l in enumerate(linhas) if l and l[0].strip('"').startswith("Unidade da Federa"))
    cab = [c.strip() for c in linhas[i]]
    dados = []
    for l in linhas[i + 1:]:
        if not l or not re.match(r"\d{2} ", l[0].strip()):
            if l and l[0].strip().startswith("Total"):
                continue
            if dados:
                break
            continue
        dados.append([c.strip() for c in l])
    return cab, dados


def main() -> None:
    hoje = date.today().isoformat()
    (REFERENCIA / "fontes").mkdir(parents=True, exist_ok=True)
    pagina = baixar(BASE + "dhdat.exe?" + DEF).decode("latin-1")
    saida = []
    for rotulo, (nome, codigo) in INDICADORES.items():
        bruto = consultar(pagina, rotulo)
        arquivo = REFERENCIA / "fontes" / f"tabnet_cpni_{nome}_{hoje}.csv"
        arquivo.write_bytes(bruto)
        print(f"{arquivo.name}: {len(bruto)} bytes, sha256 {hashlib.sha256(bruto).hexdigest()}")
        cab, dados = ler_csv_tabnet(bruto)
        anos = [c for c in cab[1:] if re.fullmatch(r"\d{4}", c)]
        for linha in dados:
            cod, nome_uf = linha[0].split(" ", 1)
            for ano, valor in zip(cab[1:], linha[1:]):
                if ano not in anos or valor in ("", "-"):
                    continue
                saida.append({"indicador": nome, "codigo_imunobiologico": codigo, "codigo_uf": cod,
                              "uf": nome_uf.strip(), "ano": int(ano),
                              "cobertura_percentual": float(valor.replace(".", "").replace(",", ".")),
                              "consultado_em": hoje})
        # Brasil: consulta nacional (Linha = Ano), e não a linha "Total" da tabela por UF.
        bruto = consultar(pagina, rotulo, nacional=True)
        arquivo = REFERENCIA / "fontes" / f"tabnet_cpni_{nome}_brasil_{hoje}.csv"
        arquivo.write_bytes(bruto)
        print(f"{arquivo.name}: {len(bruto)} bytes, sha256 {hashlib.sha256(bruto).hexdigest()}")
        for linha in csv.reader(io.StringIO(bruto.decode("latin-1")), delimiter=";"):
            if len(linha) >= 2 and re.fullmatch(r"\d{4}", linha[0].strip()) and linha[1].strip() not in ("", "-"):
                saida.append({"indicador": nome, "codigo_imunobiologico": codigo, "codigo_uf": "00", "uf": "Brasil",
                              "ano": int(linha[0]), "consultado_em": hoje,
                              "cobertura_percentual": float(linha[1].replace(".", "").replace(",", "."))})
    destino = REFERENCIA / "tabnet_cobertura_uf_ano.csv"
    with destino.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["indicador", "codigo_imunobiologico", "codigo_uf", "uf", "ano",
                                         "cobertura_percentual", "consultado_em"], lineterminator="\n")
        w.writeheader()
        w.writerows(sorted(saida, key=lambda r: (r["indicador"], r["ano"], r["codigo_uf"])))
    print(f"{destino.name}: {len(saida)} linhas")


if __name__ == "__main__":
    main()
