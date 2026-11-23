"""Conversão .dbc -> .dbf compilada com numba (sem compilador C).

Mesmo algoritmo do `dbc_puro` (tradução do blast.c de Mark Adler, PKWare DCL "implode"),
compilado na primeira chamada. Dois ganhos sobre a versão em Python puro:
    - velocidade: ~100x mais rápido (os 3,4 GB de .dbc do SINASC passam de horas para minutos);
    - memória: o tamanho do .dbf sai do cabeçalho (registros x tamanho do registro), então a
      saída é um np.memmap em disco, e não um bytearray do arquivo inteiro na memória.
O resultado é byte a byte igual ao do `dbc_puro` (ver `verificar_igual_ao_puro`).
"""

from pathlib import Path

import numpy as np
from numba import njit

from comum import dbc_puro


def _tabela(compactado: list[int]) -> tuple[np.ndarray, np.ndarray]:
    contagem, simbolos = dbc_puro._construir(compactado)
    return np.array(contagem, dtype=np.int32), np.array(simbolos, dtype=np.int32)


LIT_C, LIT_S = _tabela(dbc_puro.LITLEN)
LEN_C, LEN_S = _tabela(dbc_puro.LENLEN)
DIST_C, DIST_S = _tabela(dbc_puro.DISTLEN)
BASE = np.array(dbc_puro.BASE, dtype=np.int32)
EXTRA = np.array(dbc_puro.EXTRA, dtype=np.int32)


@njit(cache=True)
def _blast(dados, saida, lit_c, lit_s, len_c, len_s, dist_c, dist_s, base, extra):
    """Descomprime `dados` em `saida`. Retorna o nº de bytes escritos (-1..-4 = erro)."""
    pos = 0
    buf = 0
    cnt = 0
    n_dados = dados.shape[0]
    n_saida = saida.shape[0]
    out = 0

    # cabeçalho: lit (0/1) e dic (4..6)
    while cnt < 16:
        if pos >= n_dados:
            return -1
        buf |= np.int64(dados[pos]) << cnt
        pos += 1
        cnt += 8
    lit = buf & 255
    buf >>= 8
    dic = buf & 255
    buf >>= 8
    cnt -= 16
    if lit > 1 or dic < 4 or dic > 6:
        return -2

    while True:
        # 1 bit: literal (0) ou cópia (1)
        if cnt < 1:
            if pos >= n_dados:
                return -1
            buf |= np.int64(dados[pos]) << cnt
            pos += 1
            cnt += 8
        flag = buf & 1
        buf >>= 1
        cnt -= 1

        if flag:
            # comprimento (Huffman LEN)
            code = 0
            first = 0
            index = 0
            simbolo = -1
            for comprimento in range(1, 14):
                if cnt < 1:
                    if pos >= n_dados:
                        return -1
                    buf |= np.int64(dados[pos]) << cnt
                    pos += 1
                    cnt += 8
                code |= (buf & 1) ^ 1
                buf >>= 1
                cnt -= 1
                n = len_c[comprimento]
                if code < first + n:
                    simbolo = len_s[index + code - first]
                    break
                index += n
                first = (first + n) << 1
                code <<= 1
            if simbolo < 0:
                return -3
            e = extra[simbolo]
            while cnt < e:
                if pos >= n_dados:
                    return -1
                buf |= np.int64(dados[pos]) << cnt
                pos += 1
                cnt += 8
            tam = base[simbolo] + (buf & ((1 << e) - 1))
            buf >>= e
            cnt -= e
            if tam == 519:
                return out

            nbits = 2 if tam == 2 else dic
            # distância (Huffman DIST)
            code = 0
            first = 0
            index = 0
            simbolo = -1
            for comprimento in range(1, 14):
                if cnt < 1:
                    if pos >= n_dados:
                        return -1
                    buf |= np.int64(dados[pos]) << cnt
                    pos += 1
                    cnt += 8
                code |= (buf & 1) ^ 1
                buf >>= 1
                cnt -= 1
                n = dist_c[comprimento]
                if code < first + n:
                    simbolo = dist_s[index + code - first]
                    break
                index += n
                first = (first + n) << 1
                code <<= 1
            if simbolo < 0:
                return -3
            while cnt < nbits:
                if pos >= n_dados:
                    return -1
                buf |= np.int64(dados[pos]) << cnt
                pos += 1
                cnt += 8
            dist = (simbolo << nbits) + (buf & ((1 << nbits) - 1)) + 1
            buf >>= nbits
            cnt -= nbits
            if dist > out:
                return -4
            if out + tam > n_saida:
                return -5
            inicio = out - dist
            for i in range(tam):  # pode sobrepor: byte a byte
                saida[out] = saida[inicio + i]
                out += 1
        else:
            if lit:
                code = 0
                first = 0
                index = 0
                simbolo = -1
                for comprimento in range(1, 14):
                    if cnt < 1:
                        if pos >= n_dados:
                            return -1
                        buf |= np.int64(dados[pos]) << cnt
                        pos += 1
                        cnt += 8
                    code |= (buf & 1) ^ 1
                    buf >>= 1
                    cnt -= 1
                    n = lit_c[comprimento]
                    if code < first + n:
                        simbolo = lit_s[index + code - first]
                        break
                    index += n
                    first = (first + n) << 1
                    code <<= 1
                if simbolo < 0:
                    return -3
                valor = simbolo
            else:
                while cnt < 8:
                    if pos >= n_dados:
                        return -1
                    buf |= np.int64(dados[pos]) << cnt
                    pos += 1
                    cnt += 8
                valor = buf & 255
                buf >>= 8
                cnt -= 8
            if out >= n_saida:
                return -5
            saida[out] = valor
            out += 1


def dbc2dbf(origem: str, destino: str) -> None:
    """Converte `origem` (.dbc) em `destino` (.dbf). O tamanho esperado vem do cabeçalho
    do .dbf (nº de registros x tamanho + cabeçalho + marcador de fim opcional)."""
    dados = np.fromfile(origem, dtype=np.uint8)
    cabecalho = int(dados[8]) | int(dados[9]) << 8
    registros = int.from_bytes(dados[4:8].tobytes(), "little")
    tam_registro = int(dados[10]) | int(dados[11]) << 8
    corpo_max = registros * tam_registro + 1  # +1: marcador 0x1A de fim de arquivo, se houver
    tmp = Path(destino)
    with tmp.open("wb") as f:
        f.write(dados[:cabecalho].tobytes())
        f.truncate(cabecalho + corpo_max)
    mapa = np.memmap(tmp, dtype=np.uint8, mode="r+", offset=cabecalho, shape=(corpo_max,))
    n = _blast(dados[cabecalho + 4:], mapa, LIT_C, LIT_S, LEN_C, LEN_S, DIST_C, DIST_S, BASE, EXTRA)
    mapa.flush()
    del mapa
    if n < 0:
        tmp.unlink(missing_ok=True)
        raise ValueError(f"{origem}: .dbc inválido (código {n})")
    with tmp.open("r+b") as f:
        f.truncate(cabecalho + n)


def verificar_igual_ao_puro(origem: str, pasta_tmp: Path) -> bool:
    """Confere, num arquivo pequeno, que a saída é idêntica à do `dbc_puro`."""
    a, b = pasta_tmp / "rapido.dbf", pasta_tmp / "puro.dbf"
    dbc2dbf(origem, str(a))
    dbc_puro.dbc2dbf(origem, str(b))
    return a.read_bytes() == b.read_bytes()
