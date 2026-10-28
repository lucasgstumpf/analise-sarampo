"""Dicionários de-para (nome original -> nome legível) de cada fonte e o filtro de sarampo.

Ficam num módulo só porque são usados em mais de um passo: a bronze do SI-PNI nominal usa
o filtro e o de-para já no download (para não guardar dezenas de GB), a silver das demais
fontes usa o de-para ao limpar o .csv bruto, e os utilitários reaproveitam os dois.
"""

import pandas as pd

# De-para de colunas do SINAN (ficha de Sarampo/Rubéola - EXAN) para nomes legíveis.
COLUNAS_SINAN = {
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


# Cobertura vacinal (CPNI), SI-PNI 1994-2019: um registro por município x imunobiológico x ano.
COLUNAS_CPNI = {
    "ANO": "ano",
    "UF": "codigo_uf",
    "MUNIC": "codigo_municipio",
    "IMUNO": "codigo_imunobiologico",
    "QT_DOSE": "doses_aplicadas",
    "POP": "populacao_alvo",
    "COBERT": "cobertura_vacinal_percentual",
}


# Doses aplicadas agregadas (DPNI), SI-PNI 1994-2019: mesma fonte do CPNI, mas com
# granularidade mensal e por faixa etária (CPNI é só anual).
COLUNAS_DPNI = {
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


# Doses individuais do SI-PNI/RNDS (2020+), publicadas em .zip mensais no S3.
COLUNAS_SIPNI = {
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


def filtro_vacinas_sarampo(chunk: pd.DataFrame) -> pd.Series:
    """Linhas cuja vacina tem componente de sarampo. Filtra pela descrição (ds_nome), não
    pela sigla: siglas variam por fabricante/clínica (ex.: SCRV, SCRV-2), enquanto a
    descrição cobre todas as variantes. Espera as colunas com o nome original da fonte."""
    return chunk["ds_nome"].str.contains("sarampo", case=False, na=False)
