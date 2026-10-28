"""Conversão .dbc -> .dbf em Python puro (sem compilador C).

Alternativa ao pyreaddbc para quando ele não instala (ex.: versões novas do Python no
Windows, sem wheel pronta). O .dbc do DATASUS é o cabeçalho do .dbf sem compressão, 4 bytes
de CRC e o restante comprimido com o PKWare DCL "implode"; aqui o restante é descomprimido
com uma tradução do blast.c de Mark Adler (zlib/contrib/blast).
"""

from pathlib import Path

MAXBITS = 13

# Tabelas de comprimentos de código compactadas (byte = (repetições - 1) << 4 | comprimento).
LITLEN = [
    11, 124, 8, 7, 28, 7, 188, 13, 76, 4, 10, 8, 12, 10, 12, 10, 8, 23, 8, 9, 7, 6, 7, 8, 7, 6,
    55, 8, 23, 24, 12, 11, 7, 9, 11, 12, 6, 7, 22, 5, 7, 24, 6, 11, 9, 6, 7, 22, 7, 11, 38, 7,
    9, 8, 25, 11, 8, 11, 9, 12, 8, 12, 5, 38, 5, 38, 5, 11, 7, 5, 6, 21, 6, 10, 53, 8, 7, 24, 10,
    27, 44, 253, 253, 253, 252, 252, 252, 13, 12, 45, 12, 45, 12, 61, 12, 45, 44, 173,
]
LENLEN = [2, 35, 36, 53, 38, 23]
DISTLEN = [2, 20, 53, 230, 247, 151, 248]
BASE = [3, 2, 4, 5, 6, 7, 8, 9, 10, 12, 16, 24, 40, 72, 136, 264]
EXTRA = [0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8]


def _construir(compactado: list[int]) -> tuple[list[int], list[int]]:
    comprimentos = []
    for byte in compactado:
        comprimentos += [byte & 15] * ((byte >> 4) + 1)
    contagem = [0] * (MAXBITS + 1)
    for c in comprimentos:
        contagem[c] += 1
    # Símbolos ordenados por comprimento do código e, dentro dele, pelo valor do símbolo.
    simbolos = sorted((c, s) for s, c in enumerate(comprimentos) if c)
    return contagem, [s for _, s in simbolos]


LITCODE, LENCODE, DISTCODE = _construir(LITLEN), _construir(LENLEN), _construir(DISTLEN)


class _Leitor:
    def __init__(self, dados: bytes):
        self.dados, self.pos, self.buf, self.cnt = dados, 0, 0, 0

    def bits(self, n: int) -> int:
        while self.cnt < n:
            if self.pos >= len(self.dados):
                raise ValueError("dbc truncado")
            self.buf |= self.dados[self.pos] << self.cnt
            self.pos += 1
            self.cnt += 8
        val = self.buf & ((1 << n) - 1)
        self.buf >>= n
        self.cnt -= n
        return val

    def decodificar(self, tabela: tuple[list[int], list[int]]) -> int:
        contagem, simbolos = tabela
        code = first = index = 0
        for comprimento in range(1, MAXBITS + 1):
            code |= self.bits(1) ^ 1  # os códigos do implode vêm com os bits invertidos
            n = contagem[comprimento]
            if code < first + n:
                return simbolos[index + code - first]
            index += n
            first = (first + n) << 1
            code <<= 1
        raise ValueError("código de Huffman inválido")


def descomprimir_blast(dados: bytes) -> bytes:
    s = _Leitor(dados)
    lit, dic = s.bits(8), s.bits(8)
    if lit > 1 or not 4 <= dic <= 6:
        raise ValueError("cabeçalho implode inválido")
    saida = bytearray()
    while True:
        if s.bits(1):
            simbolo = s.decodificar(LENCODE)
            comprimento = BASE[simbolo] + s.bits(EXTRA[simbolo])
            if comprimento == 519:  # código de fim
                return bytes(saida)
            nbits = 2 if comprimento == 2 else dic
            dist = (s.decodificar(DISTCODE) << nbits) + s.bits(nbits) + 1
            if dist > len(saida):
                raise ValueError("distância além do início")
            inicio = len(saida) - dist
            for i in range(comprimento):  # pode sobrepor, então copia byte a byte
                saida.append(saida[inicio + i])
        else:
            saida.append(s.decodificar(LITCODE) if lit else s.bits(8))


def dbc2dbf(origem: str, destino: str) -> None:
    dados = Path(origem).read_bytes()
    tamanho_cabecalho = int.from_bytes(dados[8:10], "little")
    corpo = descomprimir_blast(dados[tamanho_cabecalho + 4:])
    Path(destino).write_bytes(dados[:tamanho_cabecalho] + corpo)
