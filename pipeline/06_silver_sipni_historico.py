"""Passo 06 (silver) - SI-PNI histórico (CPNI e DPNI) com colunas legíveis, 1994-2019.

Entrada: data/bronze/sipni_historico/*.csv  (passo 02)

Aplica o de-para de colunas (COLUNAS_CPNI / COLUNAS_DPNI) em cada ano e junta cada base
numa série única. O DPNI é grande, então é escrito ano a ano (append) num arquivo
temporário, que só ganha o nome final no fim; rodar de novo não duplica linhas.

Saída: data/silver/sipni_historico/sipni_cobertura_vacinal_{AAAA}.csv
       data/silver/sipni_historico/sipni_cobertura_vacinal_1994_2019.csv
       data/silver/sipni_historico/sipni_doses_aplicadas_agregado_{AAAA}.csv
       data/silver/sipni_historico/sipni_doses_aplicadas_agregado_1994_2019.csv
Uso:   python pipeline/06_silver_sipni_historico.py
"""

import os

import pandas as pd

import config
from comum.datasus import renomear_colunas

LINHAS_CHUNK = 1_000_000
from comum.dicionarios import COLUNAS_CPNI, COLUNAS_DPNI


def colunas_da_serie(prefixo: str, mapa_colunas: dict[str, str]) -> list[str]:
    """União das colunas (já renomeadas) de todos os anos, na ordem em que aparecem. O layout
    muda no meio da série (CPNI em 2013, DPNI em 2004): o combinado precisa ter todas, senão
    os anos com menos colunas ficam desalinhados sob o cabeçalho do primeiro ano."""
    colunas: list[str] = []
    for ano in config.ANOS_SIPNI_HISTORICO:
        arquivo = config.BRONZE_SIPNI_HISTORICO / f"{prefixo}_{config.ano_4_digitos(ano)}.csv"
        for coluna in pd.read_csv(arquivo, nrows=0).rename(columns=mapa_colunas).columns:
            if coluna not in colunas:
                colunas.append(coluna)
    return colunas


def limpar_serie(prefixo: str, mapa_colunas: dict[str, str]) -> None:
    """Renomeia cada ano e escreve a série combinada em streaming (pouca memória). No combinado,
    as colunas que um ano não tem ficam vazias."""
    destino_dir = config.SILVER_SIPNI_HISTORICO
    destino_dir.mkdir(parents=True, exist_ok=True)
    combinado = destino_dir / f"{prefixo}_1994_2019.csv"
    tmp = combinado.with_suffix(".tmp")
    colunas = colunas_da_serie(prefixo, mapa_colunas)
    total = 0
    for ano in config.ANOS_SIPNI_HISTORICO:
        nome = f"{prefixo}_{config.ano_4_digitos(ano)}.csv"
        tmp_ano = (destino_dir / nome).with_suffix(".tmp")
        n_ano = 0
        # Em blocos: os anos maiores do DPNI (8 milhões de linhas) não cabem inteiros na memória.
        for df in pd.read_csv(config.BRONZE_SIPNI_HISTORICO / nome, dtype=str, keep_default_na=False,
                              na_filter=False, encoding="utf-8", chunksize=LINHAS_CHUNK):
            df = renomear_colunas(df, mapa_colunas)
            df.to_csv(tmp_ano, mode="a" if n_ano else "w", index=False, header=not n_ano,
                      encoding="utf-8", lineterminator="\n")
            df.reindex(columns=colunas, fill_value="").to_csv(
                tmp, mode="a" if total else "w", index=False, header=not total, encoding="utf-8", lineterminator="\n")
            n_ano += len(df)
            total += len(df)
        os.replace(tmp_ano, destino_dir / nome)
        print(f"{nome}: {n_ano} registros", flush=True)
    os.replace(tmp, combinado)
    print(f"Série histórica combinada gerada: {combinado} ({total} registros)")


def main() -> None:
    limpar_serie("sipni_cobertura_vacinal", COLUNAS_CPNI)
    limpar_serie("sipni_doses_aplicadas_agregado", COLUNAS_DPNI)


if __name__ == "__main__":
    main()
