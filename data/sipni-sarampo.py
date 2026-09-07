from pathlib import Path

import pandas as pd

from datasus_lib import extrair_dbf

RAW_DIR = Path(__file__).parent / "raw"
PROCESSED_DIR = Path(__file__).parent / "processed"

# 1) Cobertura vacinal (CPNI), Brasil, 1994-2019 - FTP, um arquivo por ano.
CAMINHO_TEMPLATE_CPNI = "dissemin/publicos/PNI/DADOS/CPNIBR{ano}.DBF"

ANOS_1994_2019 = [f"{a:02d}" for a in range(94, 100)] + [f"{a:02d}" for a in range(0, 20)]

NOME_BASE_COMBINADO_CPNI = "sipni_cobertura_vacinal_1994_2019"

COLUMN_MAP_CPNI = {
    "ANO": "ano",
    "UF": "codigo_uf",
    "MUNIC": "codigo_municipio",
    "IMUNO": "codigo_imunobiologico",
    "QT_DOSE": "doses_aplicadas",
    "POP": "populacao_alvo",
    "COBERT": "cobertura_vacinal_percentual",
}

# 2) Doses aplicadas agregadas (DPNI), Brasil, 1994-2019 - mesma fonte do CPNI, mas
# com granularidade mensal e por faixa etária (CPNI é só anual).
CAMINHO_TEMPLATE_DPNI = "dissemin/publicos/PNI/DADOS/DPNIBR{ano}.DBF"

NOME_BASE_COMBINADO_DPNI = "sipni_doses_aplicadas_agregado_1994_2019"

COLUMN_MAP_DPNI = {
    "ANO": "ano",
    "ANOMES": "ano_mes",
    "MES": "mes",
    "UF": "codigo_uf",
    "MUNIC": "codigo_municipio",
    "FX_ETARIA": "faixa_etaria",
    "IMUNO": "codigo_imunobiologico",
    "DOSE": "codigo_dose",
    "QT_DOSE": "doses_aplicadas",
    "DOSE1": "indicador_dose_1",
    "DOSEN": "indicador_dose_reforco",
    "DIFER": "indicador_dose_diferida",
}

def coletar_cobertura_vacinal() -> None:
    dataframes = []
    for ano in ANOS_1994_2019:
        caminho = CAMINHO_TEMPLATE_CPNI.format(ano=ano)
        nome_base = f"sipni_cobertura_vacinal_20{ano}" if ano < "50" else f"sipni_cobertura_vacinal_19{ano}"
        df_ano = extrair_dbf(caminho, nome_base, COLUMN_MAP_CPNI, RAW_DIR, PROCESSED_DIR)
        dataframes.append(df_ano)

    df_combinado = pd.concat(dataframes, ignore_index=True)
    arquivo_combinado = PROCESSED_DIR / f"{NOME_BASE_COMBINADO_CPNI}.csv"
    df_combinado.to_csv(arquivo_combinado, index=False, encoding="utf-8")
    print(f"Série histórica combinada gerada: {arquivo_combinado} ({len(df_combinado)} registros)")


def coletar_doses_aplicadas_agregado() -> None:
    arquivo_combinado = PROCESSED_DIR / f"{NOME_BASE_COMBINADO_DPNI}.csv"
    preparar_cabecalho = not arquivo_combinado.exists()
    total_registros = 0

    for ano in ANOS_1994_2019:
        caminho = CAMINHO_TEMPLATE_DPNI.format(ano=ano)
        nome_base = f"sipni_doses_aplicadas_agregado_20{ano}" if ano < "50" else f"sipni_doses_aplicadas_agregado_19{ano}"
        df_ano = extrair_dbf(caminho, nome_base, COLUMN_MAP_DPNI, RAW_DIR, PROCESSED_DIR)

        df_ano.to_csv(arquivo_combinado, mode="a", index=False, header=preparar_cabecalho, encoding="utf-8")
        preparar_cabecalho = False
        total_registros += len(df_ano)

    print(f"Série histórica combinada gerada: {arquivo_combinado} ({total_registros} registros)")


def main() -> None:
    coletar_cobertura_vacinal()
    coletar_doses_aplicadas_agregado()


if __name__ == "__main__":
    main()
