"""Leitura de .dbf em partes, com numpy, sem carregar o arquivo inteiro na memória.

O `dbfread` lê registro a registro em Python e o `dbf_para_csv` antigo montava um DataFrame
do arquivo todo: o DPNI (até 1,5 GB por ano) e o SINASC estouravam a RAM do WSL. Aqui o
arquivo é aberto como np.memmap (registros de tamanho fixo) e lido em blocos.

As regras de conversão são as do `dbfread` 2.0.7 + pandas, para o CSV sair igual ao de antes:
    - registro só entra se o 1º byte for " " (não apagado); para no 0x1A (fim de arquivo);
    - campo C: tira "\\0" e espaços à direita e decodifica (latin-1);
    - campo N: tira espaços e "*"; vazio -> nulo; vira int, ou float se tiver casas decimais.
      Como no DataFrame do arquivo inteiro, o tipo é o da coluna toda: se algum valor do
      arquivo é nulo ou decimal, a coluna inteira é float (ex.: "12.0"). Por isso há uma
      primeira passada rápida que só decide o tipo de cada coluna N.
    - campo D (AAAAMMDD): data "AAAA-MM-DD"; só espaços ou zeros -> nulo; data inválida -> erro.
Outros tipos de campo (L, F...) não aparecem nas bases usadas e geram erro.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pandas as pd

LINHAS_POR_BLOCO = 1_000_000


def cabecalho(origem: Path) -> tuple[int, int, int, list[tuple[str, str, int, int]]]:
    """(nº de registros, tamanho do cabeçalho, tamanho do registro, campos[(nome, tipo, tam, dec)])."""
    with open(origem, "rb") as f:
        h = f.read(32)
        registros = int.from_bytes(h[4:8], "little")
        tam_cab = int.from_bytes(h[8:10], "little")
        tam_reg = int.from_bytes(h[10:12], "little")
        campos = []
        while True:
            d = f.read(32)
            if not d or d[0] == 0x0D:
                break
            nome = d[:11].split(b"\0")[0].decode("ascii")
            campos.append((nome, chr(d[11]), d[16], d[17]))
    return registros, tam_cab, tam_reg, campos


def _mapa(origem: Path):
    registros, tam_cab, tam_reg, campos = cabecalho(origem)
    tipos = [("_sep", "S1")] + [(n, f"S{t}") for n, _, t, _ in campos]
    soma = 1 + sum(t for _, _, t, _ in campos)
    if soma < tam_reg:
        tipos.append(("_resto", f"S{tam_reg - soma}"))
    n = (os.path.getsize(origem) - tam_cab) // tam_reg
    if n == 0:
        return np.empty(0, dtype=np.dtype(tipos)), campos
    mapa = np.memmap(origem, dtype=np.dtype(tipos), mode="r", offset=tam_cab, shape=(n,))
    fim = np.flatnonzero(mapa["_sep"] == b"\x1a")  # o dbfread para no 1º marcador de fim
    if len(fim):
        mapa = mapa[: fim[0]]
    return mapa, campos


def _texto_n(valores: np.ndarray) -> pd.Series:
    """Campo N como texto já limpo (sem espaços nem '*'); '' = nulo."""
    s = pd.Series(np.char.decode(valores, "latin-1"))
    return s.str.strip().str.strip("*").str.replace(",", ".", regex=False)


def _tipos_numericos(mapa, campos) -> dict[str, str]:
    """1ª passada: decide o tipo de cada coluna N como o pandas faria com o arquivo inteiro."""
    tipos = {}
    for nome, tipo, _, _ in campos:
        if tipo != "N":
            continue
        tem_nulo = tem_decimal = tem_valor = False
        for i in range(0, len(mapa), LINHAS_POR_BLOCO):
            bloco = mapa[i:i + LINHAS_POR_BLOCO]
            texto = _texto_n(bloco[nome][bloco["_sep"] == b" "])
            vazio = texto == ""
            tem_nulo |= bool(vazio.any())
            tem_valor |= bool((~vazio).any())
            nao_inteiro = ~vazio & ~texto.str.fullmatch(r"[+-]?\d+")
            tem_decimal |= bool(nao_inteiro.any())
        tipos[nome] = "object" if not tem_valor else ("float64" if tem_nulo or tem_decimal else "int64")
    return tipos


def iterar(origem: Path, colunas: list[str] | None = None, encoding: str = "iso-8859-1",
           linhas: int = LINHAS_POR_BLOCO) -> Iterator[pd.DataFrame]:
    """Blocos do .dbf como DataFrames, com os tipos do dbfread (texto, int, float)."""
    mapa, campos = _mapa(Path(origem))
    for _, tipo, _, _ in campos:
        if tipo not in "CND":
            raise ValueError(f"{origem}: campo do tipo {tipo} não suportado")
    if colunas is not None:
        campos = [c for c in campos if c[0] in colunas]
    tipos_n = _tipos_numericos(mapa, campos)
    for i in range(0, len(mapa), linhas):
        bloco = mapa[i:i + linhas]
        bloco = bloco[bloco["_sep"] == b" "]
        dados = {}
        for nome, tipo, _, _ in campos:
            if tipo == "C":
                dados[nome] = np.char.decode(np.char.rstrip(bloco[nome], b"\0 "), encoding)
            elif tipo == "D":
                texto = pd.Series(np.char.decode(bloco[nome], "latin-1"))
                vazio = texto.str.strip(" 0") == ""
                datas = pd.to_datetime(texto.where(~vazio), format="%Y%m%d", errors="raise")
                del datas  # só valida; o texto sai do original (ano com 4 dígitos, ex. "0200")
                iso = texto.str[:4] + "-" + texto.str[4:6] + "-" + texto.str[6:8]
                dados[nome] = iso.where(~vazio, None).astype("object")
            else:
                texto = _texto_n(bloco[nome])
                if tipos_n[nome] == "object":
                    dados[nome] = pd.Series([None] * len(texto), dtype="object")
                else:
                    dados[nome] = pd.to_numeric(texto.replace("", np.nan)).astype(tipos_n[nome])
        yield pd.DataFrame(dados)


def para_csv(origem: Path, destino: Path) -> int:
    """Grava o .dbf como CSV (UTF-8, LF), em blocos. Retorna o nº de registros."""
    total = 0
    with open(destino, "w", encoding="utf-8", newline="") as f:
        for bloco in iterar(origem):
            bloco.to_csv(f, index=False, header=total == 0, lineterminator="\n")
            total += len(bloco)
    if total == 0:  # arquivo sem registros: só o cabeçalho
        _, _, _, campos = cabecalho(origem)
        destino.write_text(",".join(n for n, *_ in campos) + "\n", encoding="utf-8")
    return total
