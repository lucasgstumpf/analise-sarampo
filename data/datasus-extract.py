import urllib.request
from pathlib import Path

import pandas as pd
from dbfread import DBF
from pyreaddbc import dbc2dbf

URL = "ftp://ftp.datasus.gov.br/dissemin/publicos/SINAN/DADOS/PRELIM/EXANBR26.dbc"

NOME_BASE = "sinan_sarampo_exames_2026"

RAW_DIR = Path(__file__).parent / "raw"
PROCESSED_DIR = Path(__file__).parent / "processed"

ARQUIVO_DBC = RAW_DIR / f"{NOME_BASE}.dbc"
ARQUIVO_DBF = RAW_DIR / f"{NOME_BASE}.dbf"
ARQUIVO_CSV_RAW = RAW_DIR / f"{NOME_BASE}.csv"
ARQUIVO_CSV = PROCESSED_DIR / f"{NOME_BASE}.csv"

# De-para de colunas do SINAN (ficha de Sarampo/Rubéola - EXAN) para nomes legíveis.
# Mantém apenas as colunas que existem de fato no extrato baixado do DATASUS;
# colunas não mapeadas permanecem com o nome original.
COLUMN_MAP = {
    # 1. Identificação da notificação
    "TP_NOT": "tipo_notificacao",
    "ID_AGRAVO": "codigo_agravo",
    "CS_SUSPEIT": "suspeita_diagnostica",
    "DT_NOTIFIC": "data_notificacao",
    "SEM_NOT": "semana_epidemiologica_notificacao",
    "NU_ANO": "ano_notificacao",
    "SG_UF_NOT": "uf_notificacao",
    "ID_MUNICIP": "municipio_notificacao",
    "ID_REGIONA": "regional_saude_notificacao",
    "ID_UNIDADE": "unidade_notificadora",
    # 2. Sintomas / investigação inicial
    "DT_SIN_PRI": "data_primeiros_sintomas",
    "SEM_PRI": "semana_epidemiologica_primeiros_sintomas",
    # 3. Dados demográficos do paciente
    "ANO_NASC": "ano_nascimento",
    "NU_IDADE_N": "idade",
    "CS_SEXO": "sexo",
    "CS_GESTANT": "situacao_gestacional",
    "CS_RACA": "raca_cor",
    "CS_ESCOL_N": "escolaridade",
    "SG_UF": "uf_residencia",
    "ID_MN_RESI": "municipio_residencia",
    "ID_RG_RESI": "regional_saude_residencia",
    "ID_PAIS": "pais_residencia",
    "NDUPLIC_N": "numero_duplicidade",
    # 4. Controle de fluxo do sistema
    "DT_DIGITA": "data_digitacao",
    "DT_TRANSUS": "data_transferencia_unidade_sistema",
    "DT_TRANSDM": "data_transferencia_municipio",
    "DT_TRANSSM": "data_transferencia_estado_municipio",
    "DT_TRANSRM": "data_transferencia_regional_municipio",
    "DT_TRANSRS": "data_transferencia_regional_estado",
    "DT_TRANSSE": "data_transferencia_estado_nacional",
    "CS_FLXRET": "fluxo_retorno",
    "FLXRECEBI": "fluxo_recebido",
    "MIGRADO_W": "migrado_sistema_antigo",
    # 5. Investigação / vacinação
    "DT_INVEST": "data_investigacao",
    "ID_OCUPA_N": "ocupacao",
    "CS_VACINA": "historico_vacinal",
    "DT_DOSE_N": "data_ultima_dose",
    "CS_FONTE": "fonte_informacao_vacinal",
    # 6. Sinais clínicos
    "DT_INICIO_": "data_inicio_exantema",
    "DT_FEBRE": "data_febre",
    "ID_TOSSE": "tosse",
    "ID_CORIZA": "coriza",
    "ID_CONJUNT": "conjuntivite",
    "ID_ARTRALG": "artralgia",
    "ID_GANGLIO": "linfadenopatia",
    "ID_RETRO": "dor_retro_orbital",
    "ID_HOSPIT": "hospitalizado",
    "DT_INTERNA": "data_internacao",
    "UF_H": "uf_hospital",
    "NM_MUN_HOS": "municipio_hospital",
    # 7. Coleta de amostras / sorologia
    "DT_COL_1": "data_coleta_amostra_1",
    "DT_COL_2": "data_coleta_amostra_2",
    "ID_S1_IGM": "amostra1_igm",
    "ID_S1_IGG": "amostra1_igg",
    "ID_S1_IGM_": "amostra1_igm_rubeola",
    "ID_S1_IGG_": "amostra1_igg_rubeola",
    "ID_S1_IG_1": "amostra1_resultado_1",
    "ID_S1_IG_2": "amostra1_resultado_2",
    "ID_S2_IGM": "amostra2_igm",
    "ID_S2_IGG": "amostra2_igg",
    "ID_S2_IGM_": "amostra2_igm_rubeola",
    "ID_S2_IGG_": "amostra2_igg_rubeola",
    "ID_S2_IG_1": "amostra2_resultado_1",
    "ID_S2_IG_2": "amostra2_resultado_2",
    "ID_RE_IGM": "reinvestigacao_igm",
    "ID_RE_IGG": "reinvestigacao_igg",
    "ID_RE_IGM_": "reinvestigacao_igm_rubeola",
    "ID_RE_IGG_": "reinvestigacao_igg_rubeola",
    "ID_RE_IG_1": "reinvestigacao_resultado_1",
    "ID_RE_IG_2": "reinvestigacao_resultado_2",
    "TPEXANTE": "tipo_exantema",
    "ID_SANGUE": "coleta_sangue",
    "ID_URINA": "coleta_urina",
    "ID_SECRECA": "coleta_secrecao",
    "ID_LIQUOR": "coleta_liquor",
    "ID_ETIOLOG": "agente_etiologico",
    "ETIOL_OUTR": "agente_etiologico_outro",
    # 8. Situação vacinal e faixa etária (campos derivados)
    "CS_VACINAL": "situacao_vacinal",
    "MENOR_5ANO": "faixa_etaria_menor_5_anos",
    "DE5A14ANOS": "faixa_etaria_5_a_14_anos",
    "DE15A39ANO": "faixa_etaria_15_a_39_anos",
    "INT_TEMPO": "intervalo_tempo",
    # 9. Conclusão e encerramento
    "CLASSI_FIN": "classificacao_final",
    "CRITERIO": "criterio_confirmacao",
    "CS_DESCART": "criterio_descarte",
    "TPAUTOCTO": "caso_autoctone",
    "COUFINF": "uf_provavel_infeccao",
    "COPAISINF": "pais_provavel_infeccao",
    "COMUNINF": "municipio_provavel_infeccao",
    "EVOLUCAO": "evolucao_caso",
    "DT_OBITO": "data_obito",
    "DT_ENCERRA": "data_encerramento",
    # 10. Deslocamentos no período de transmissibilidade (até 3 registros)
    "DT_DESC1": "data_deslocamento_1",
    "DT_DESC2": "data_deslocamento_2",
    "DT_DESC3": "data_deslocamento_3",
    "CO_UF_DES1": "uf_deslocamento_1",
    "CO_UF_DES2": "uf_deslocamento_2",
    "CO_UF_DES3": "uf_deslocamento_3",
    "MUN_DES1": "municipio_deslocamento_1",
    "MUN_DES2": "municipio_deslocamento_2",
    "MUN_DES3": "municipio_deslocamento_3",
    "PA_DES1": "pais_deslocamento_1",
    "PA_DES2": "pais_deslocamento_2",
    "PA_DES3": "pais_deslocamento_3",
    "DS_TRANS1": "descricao_local_deslocamento_1",
    "DS_TRANS2": "descricao_local_deslocamento_2",
    "DS_TRANS3": "descricao_local_deslocamento_3",
}


def baixar_dbc(url: str, destino: Path) -> None:
    print("Iniciando download...")
    urllib.request.urlretrieve(url, destino)
    print("Download concluído.")


def converter_para_dbf(origem: Path, destino: Path) -> None:
    print("Convertendo .dbc para .dbf...")
    dbc2dbf(str(origem), str(destino))


def renomear_colunas(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns=COLUMN_MAP)


def exportar_para_csv(origem: Path, destino_raw: Path, destino_processado: Path) -> pd.DataFrame:
    print("Lendo .dbf e gerando CSV...")
    tabela = DBF(str(origem), encoding="iso-8859-1")
    df_raw = pd.DataFrame(iter(tabela))
    df_raw.to_csv(destino_raw, index=False, encoding="utf-8")

    df = renomear_colunas(df_raw)
    df.to_csv(destino_processado, index=False, encoding="utf-8")
    return df


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    baixar_dbc(URL, ARQUIVO_DBC)
    converter_para_dbf(ARQUIVO_DBC, ARQUIVO_DBF)
    df = exportar_para_csv(ARQUIVO_DBF, ARQUIVO_CSV_RAW, ARQUIVO_CSV)

    print(f"Processo finalizado! Arquivo gerado: {ARQUIVO_CSV} ({len(df)} registros)")


if __name__ == "__main__":
    main()
