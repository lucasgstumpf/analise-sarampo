import sys
import urllib.error
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from datasus_lib import extrair_csv_zip_filtrado

RAW_DIR = Path(__file__).parent / "raw"
PROCESSED_DIR = Path(__file__).parent / "processed"

# Doses de sarampo pós-2019 (SI-PNI/RNDS), registros individuais. Desde 2020 os dados
# nominais são publicados fora do FTP, em .zip mensais com TODOS os imunobiológicos
# (bucket S3 público). Baixamos cada mês e filtramos em streaming só as doses de sarampo.
URL_TEMPLATE_SIPNI = "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/PNI/csv/vacinacao_{mes}_{ano}_csv.zip"

MESES_ABREV = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

ANO_INICIAL_SIPNI = 2020
ANO_FINAL_SIPNI = 2026  # ajuste conforme necessário; meses ainda não publicados são pulados

# Filtra pela descrição (ds_nome), não pela sigla: siglas variam por fabricante/clínica
# (ex.: SCRV, SCRV-2), enquanto a descrição cobre todas as variantes de forma robusta.
def filtro_vacinas_sarampo(chunk: pd.DataFrame) -> pd.Series:
    return chunk["ds_nome"].str.contains("sarampo", case=False, na=False)

NOME_BASE_COMBINADO_SIPNI = "sipni_doses_sarampo_sipni_2020_2026"

COLUMN_MAP_SIPNI = {
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


def coletar_doses_sarampo_sipni() -> None:
    arquivo_combinado = PROCESSED_DIR / f"{NOME_BASE_COMBINADO_SIPNI}.csv"
    preparar_cabecalho = not arquivo_combinado.exists()
    total_registros = 0

    for ano in range(ANO_INICIAL_SIPNI, ANO_FINAL_SIPNI + 1):
        for mes in MESES_ABREV:
            url = URL_TEMPLATE_SIPNI.format(mes=mes, ano=ano)
            nome_base = f"sipni_doses_sarampo_sipni_{ano}_{mes}"
            try:
                df_mes = extrair_csv_zip_filtrado(
                    url,
                    nome_base,
                    filtro_vacinas_sarampo,
                    COLUMN_MAP_SIPNI,
                    RAW_DIR,
                    PROCESSED_DIR,
                )
            except urllib.error.HTTPError as erro:
                print(f"Pulando {ano}-{mes} (HTTP {erro.code}, provavelmente ainda não publicado): {url}")
                continue

            df_mes.to_csv(arquivo_combinado, mode="a", index=False, header=preparar_cabecalho, encoding="utf-8")
            preparar_cabecalho = False
            total_registros += len(df_mes)

    print(f"Série histórica combinada gerada: {arquivo_combinado} ({total_registros} registros)")


def main() -> None:
    coletar_doses_sarampo_sipni()


if __name__ == "__main__":
    main()
