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

import config
from comum.datasus import ler_csv_bronze, renomear_colunas
from comum.dicionarios import COLUNAS_CPNI, COLUNAS_DPNI


def limpar_serie(prefixo: str, mapa_colunas: dict[str, str]) -> None:
    """Renomeia cada ano e escreve a série combinada em streaming (pouca memória)."""
    destino_dir = config.SILVER_SIPNI_HISTORICO
    destino_dir.mkdir(parents=True, exist_ok=True)
    combinado = destino_dir / f"{prefixo}_1994_2019.csv"
    tmp = combinado.with_suffix(".tmp")
    total = 0
    for ano in config.ANOS_SIPNI_HISTORICO:
        nome = f"{prefixo}_{config.ano_4_digitos(ano)}.csv"
        df = renomear_colunas(ler_csv_bronze(config.BRONZE_SIPNI_HISTORICO / nome), mapa_colunas)
        df.to_csv(destino_dir / nome, index=False, encoding="utf-8")
        df.to_csv(tmp, mode="a" if total else "w", index=False, header=not total, encoding="utf-8")
        total += len(df)
        print(f"{nome}: {len(df)} registros")
    os.replace(tmp, combinado)
    print(f"Série histórica combinada gerada: {combinado} ({total} registros)")


def main() -> None:
    limpar_serie("sipni_cobertura_vacinal", COLUNAS_CPNI)
    limpar_serie("sipni_doses_aplicadas_agregado", COLUNAS_DPNI)


if __name__ == "__main__":
    main()
