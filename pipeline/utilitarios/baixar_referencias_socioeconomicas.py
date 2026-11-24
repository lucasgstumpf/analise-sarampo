"""Baixa e consolida as referências oficiais socioeconômicas (IBGE SIDRA) e eleitorais (TSE)
para data/referencia/, seguindo o padrão de rastreabilidade do repositório (arquivos originais
em data/referencia/fontes/ + CSVs limpos em data/referencia/ + sha256).

Fontes oficiais consultadas:
  1. IBGE / SIDRA (API v3 de Agregados — PNAD Contínua Anual, 2024 e 2025):
     - Tabela 7531, variável 10824, classificação 1019[49243] (Total):
       Rendimento médio mensal real domiciliar per capita, a preços médios do ano (R$)
     - Tabela 7435, variável 10681:
       Índice de Gini do rendimento domiciliar per capita, a preços médios do ano
  2. TSE — Portal de Dados Abertos (Eleições Gerais 2022, votação por partido/município/zona):
     - votacao_partido_munzona_2022.zip -> votacao_partido_munzona_2022_BR.csv
       (agregado para o 2º turno presidencial por UF e Brasil)

Uso (da raiz do repositório):
    python pipeline/utilitarios/baixar_referencias_socioeconomicas.py
"""
import gzip
import hashlib
import io
import json
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
REF_DIR = RAIZ / "data" / "referencia"
FONTES_DIR = REF_DIR / "fontes"
HOJE = date.today().isoformat()

URL_SIDRA_RENDA = (
    "https://servicodados.ibge.gov.br/api/v3/agregados/7531/periodos/2024|2025/"
    "variaveis/10824?localidades=N1[all]|N3[all]&classificacao=1019[49243]"
)
URL_SIDRA_GINI = (
    "https://servicodados.ibge.gov.br/api/v3/agregados/7435/periodos/2024|2025/"
    "variaveis/10681?localidades=N1[all]|N3[all]"
)
URL_TSE_ZIP = (
    "https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_partido_munzona/"
    "votacao_partido_munzona_2022.zip"
)


def baixar_bytes(url: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (analise-sarampo/UNESP)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def mapa_ufs() -> dict[str, str]:
    meta = json.loads((RAIZ / "data" / "gold" / "ibge" / "uf_meta.json").read_text(encoding="utf-8"))
    mapa = {str(u["id"]): u["sigla"] for u in meta}
    mapa["1"] = "BR"
    return mapa


def processar_ibge() -> list[tuple[Path, str]]:
    FONTES_DIR.mkdir(parents=True, exist_ok=True)
    id_sigla = mapa_ufs()

    print("Baixando IBGE SIDRA 7531 (Renda per capita 2024-2025)...")
    raw_renda = baixar_bytes(URL_SIDRA_RENDA)
    arq_renda = FONTES_DIR / f"ibge_sidra_7531_renda_per_capita_2024_2025_{HOJE}.json"
    arq_renda.write_bytes(raw_renda)

    print("Baixando IBGE SIDRA 7435 (Índice de Gini 2024-2025)...")
    raw_gini = baixar_bytes(URL_SIDRA_GINI)
    arq_gini = FONTES_DIR / f"ibge_sidra_7435_gini_2024_2025_{HOJE}.json"
    arq_gini.write_bytes(raw_gini)

    dados_renda = json.loads(raw_renda.decode("utf-8"))[0]["resultados"][0]["series"]
    dados_gini = json.loads(raw_gini.decode("utf-8"))[0]["resultados"][0]["series"]

    gini_map = {}
    for item in dados_gini:
        loc_id = str(item["localidade"]["id"])
        for ano, val in item["serie"].items():
            gini_map[(loc_id, int(ano))] = float(val) if val not in (None, "-", "..", "...") else None

    linhas = []
    for item in dados_renda:
        loc_id = str(item["localidade"]["id"])
        nome = item["localidade"]["nome"]
        uf = id_sigla.get(loc_id, loc_id)
        nivel = "brasil" if loc_id == "1" else "uf"
        for ano_str, val in item["serie"].items():
            ano = int(ano_str)
            linhas.append({
                "nivel": nivel,
                "codigo_uf": "00" if loc_id == "1" else loc_id.zfill(2),
                "uf": uf,
                "nome": nome,
                "ano": ano,
                "renda_per_capita_reais": float(val) if val not in (None, "-", "..", "...") else None,
                "indice_gini": gini_map.get((loc_id, ano)),
                "fonte": "IBGE/SIDRA PNAD Contínua Anual (tabelas 7531 e 7435)",
                "consultado_em": HOJE,
            })

    df = pd.DataFrame(linhas).sort_values(["ano", "codigo_uf"]).reset_index(drop=True)
    destino = REF_DIR / "ibge_renda_gini_uf_2024_2025.csv"
    df.to_csv(destino, index=False, encoding="utf-8", lineterminator="\n")
    print(f"Salvo {destino.name}: {len(df)} linhas (BR 2024 = R$ {df[(df['uf']=='BR')&(df['ano']==2024)]['renda_per_capita_reais'].iloc[0]:.0f}, BR 2025 = R$ {df[(df['uf']=='BR')&(df['ano']==2025)]['renda_per_capita_reais'].iloc[0]:.0f})")
    return [(arq_renda, URL_SIDRA_RENDA), (arq_gini, URL_SIDRA_GINI)]


def processar_tse() -> list[tuple[Path, str]]:
    FONTES_DIR.mkdir(parents=True, exist_ok=True)
    print("Baixando TSE Dados Abertos (votacao_partido_munzona_2022.zip, ~26 MB)...")
    raw_zip = baixar_bytes(URL_TSE_ZIP, timeout=240)

    with zipfile.ZipFile(io.BytesIO(raw_zip)) as zf:
        membro_br = [n for n in zf.namelist() if n.endswith("_BR.csv")][0]
        raw_br = zf.read(membro_br)

    arq_tse = FONTES_DIR / f"tse_votacao_partido_munzona_2022_BR_{HOJE}.csv.gz"
    with gzip.open(arq_tse, "wb", compresslevel=9) as gz:
        gz.write(raw_br)

    df_br = pd.read_csv(io.BytesIO(raw_br), sep=";", encoding="latin1", low_memory=False)
    # 2º turno presidencial (NR_TURNO == 2, CD_CARGO == 1)
    t2 = df_br[(df_br["NR_TURNO"] == 2) & (df_br["CD_CARGO"] == 1)].copy()
    col_votos = "QT_VOTOS_NOMINAIS_VALIDOS" if "QT_VOTOS_NOMINAIS_VALIDOS" in t2.columns else "QT_VOTOS_NOMINAIS"
    if "QT_VOTOS_NOMINAIS" in t2.columns and col_votos not in t2.columns:
        col_votos = "QT_VOTOS_NOMINAIS"
    print(f"  Coluna de votos TSE usada: {col_votos} | Partidos no 2º turno: {sorted(t2['SG_PARTIDO'].unique())}")

    agg = t2.groupby(["SG_UF", "SG_PARTIDO"], as_index=False)[col_votos].sum()
    piv = agg.pivot(index="SG_UF", columns="SG_PARTIDO", values=col_votos).fillna(0).astype(int)

    # Inclui linha consolidada Brasil (todos os votos válidos, incluindo Exterior ZZ, como oficial do TSE)
    br_row = pd.DataFrame([piv.sum()], index=["BR"])
    piv = pd.concat([br_row, piv.sort_index()])
    piv["votos_validos"] = piv["PT"] + piv["PL"]
    piv["pct_lula_pt"] = (piv["PT"] / piv["votos_validos"] * 100).round(2)
    piv["pct_bolsonaro_pl"] = (piv["PL"] / piv["votos_validos"] * 100).round(2)
    piv["vencedor"] = piv.apply(lambda r: "Lula (PT)" if r["PT"] >= r["PL"] else "Bolsonaro (PL)", axis=1)

    out = pd.DataFrame({
        "nivel": ["brasil" if idx == "BR" else ("exterior" if idx == "ZZ" else "uf") for idx in piv.index],
        "uf": piv.index,
        "votos_lula_pt": piv["PT"].values,
        "votos_bolsonaro_pl": piv["PL"].values,
        "votos_validos": piv["votos_validos"].values,
        "pct_lula_pt": piv["pct_lula_pt"].values,
        "pct_bolsonaro_pl": piv["pct_bolsonaro_pl"].values,
        "vencedor": piv["vencedor"].values,
        "fonte": "TSE Dados Abertos (votacao_partido_munzona_2022_BR.csv, 2º turno Presidente)",
        "consultado_em": HOJE,
    })

    destino = REF_DIR / "tse_eleicao_2022_2turno_uf.csv"
    out.to_csv(destino, index=False, encoding="utf-8", lineterminator="\n")
    br = out[out["uf"] == "BR"].iloc[0]
    print(f"Salvo {destino.name}: {len(out)} linhas (BR: Lula {br['pct_lula_pt']:.2f}% [{br['votos_lula_pt']:,}] vs Bolsonaro {br['pct_bolsonaro_pl']:.2f}% [{br['votos_bolsonaro_pl']:,}])")
    return [(arq_tse, URL_TSE_ZIP)]


def main() -> None:
    originais = processar_ibge() + processar_tse()
    print("\n=== HASHES SHA-256 DOS ARQUIVOS ORIGINAIS (para data/referencia/README.md) ===")
    for arq, url in originais:
        print(f"{sha256_arquivo(arq)}  fontes/{arq.name}  ({arq.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
