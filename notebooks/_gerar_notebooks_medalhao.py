"""Gera os notebooks 05-07 (silver/gold da vacinação contra sarampo). Rodar da raiz do projeto."""
from pathlib import Path

import nbformat as nbf

SETUP = '''from pathlib import Path
import json

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
import pandas as pd

# Paleta categorica validada (blue, orange, aqua, yellow, magenta, green, violet, red)
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
BLUE = "#2a78d6"
TEXT_PRIMARY, TEXT_SECONDARY, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#fcfcfb"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "axes.edgecolor": GRID,
    "axes.labelcolor": TEXT_SECONDARY, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "text.color": TEXT_PRIMARY, "xtick.color": MUTED, "ytick.color": MUTED, "font.size": 10,
    "axes.spines.top": False, "axes.spines.right": False,
})
pd.options.display.float_format = "{:,.2f}".format

PROCESSED = Path("..") / "data" / "vacinacao" / "processed"
SILVER = PROCESSED / "silver" / "vacinacao_sarampo_sipni.parquet"
GOLD = PROCESSED / "gold"


def milhar(ax, eixo="y"):
    fmt = mtick.FuncFormatter(lambda v, _: f"{v:,.0f}".replace(",", "."))
    (ax.yaxis if eixo == "y" else ax.xaxis).set_major_formatter(fmt)


def titulo(ax, texto):
    ax.set_title(texto, loc="left", fontweight="bold")
'''


def nb(cells, path):
    n = nbf.v4.new_notebook()
    n.cells = [nbf.v4.new_markdown_cell(c[1]) if c[0] == "md" else nbf.v4.new_code_cell(c[1]) for c in cells]
    n.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
    nbf.write(n, path)


# ---------------------------------------------------------------- 05 silver
nb05 = [
    ("md", """# Camada Silver - Qualidade da base de vacinação contra sarampo

Este notebook audita a **silver**: `data/vacinacao/processed/silver/vacinacao_sarampo_sipni.parquet`, uma linha por dose de vacina com componente de sarampo (SCR, SCRV, SR), de **jan/2025 a jun/2026**.

Arquitetura em camadas (medalhão):

| Camada | O que é | Onde / como é gerada |
|---|---|---|
| **Bronze** | CSVs mensais do SI-PNI/RNDS já filtrados para sarampo, sem tratamento | `processed/sipni_doses_sarampo_sipni_AAAA_mmm.csv` - `extract_recentes.py` |
| **Silver** | Limpa, tipada, enxuta (56 -> 28 colunas), sem duplicatas e sem diluentes | `processed/silver/` - `processar_vacinacao.py` |
| **Gold** | Tabelas agregadas pequenas, prontas para visualização e BI | `processed/gold/` - `gerar_gold.py` |

Ver [06-gold-panorama-vacinacao.ipynb](06-gold-panorama-vacinacao.ipynb) e [07-gold-criancas-municipios-atraso.ipynb](07-gold-criancas-municipios-atraso.ipynb) para as análises sobre a gold."""),
    ("md", "## 1. Setup"),
    ("code", SETUP + '''
df = pd.read_parquet(SILVER)
print(f"{df.shape[0]:,} linhas x {df.shape[1]} colunas | {SILVER.stat().st_size/1e6:,.0f} MB em disco | {df.memory_usage(deep=True).sum()/1e9:.1f} GB em RAM")
df.head(3).T'''),
    ("md", "## 2. Funil de processamento (bronze -> silver)\nQuantas linhas cada regra da silver removeu, por mês."),
    ("code", '''resumo = pd.DataFrame(json.loads((PROCESSED / "_auditoria" / "processamento_resumo.json").read_text(encoding="utf-8"))).T
resumo.index.name = "ano_mes"
display(resumo)
print("Total bronze:", f"{resumo.linhas_csv.sum():,}", "| diluentes removidos:", f"{resumo.diluentes_removidos.sum():,}",
      "| duplicadas removidas:", f"{resumo.duplicadas_removidas.sum():,}", "| silver:", f"{resumo.linhas_finais.sum():,}")'''),
    ("md", "## 3. Completude\nPercentual de valores ausentes por coluna. Colunas quase vazias (etnia, condição maternal etc.) só fazem sentido em subpopulações."),
    ("code", '''nulos = (df.isna().mean() * 100).sort_values()
fig, ax = plt.subplots(figsize=(8, 8))
ax.barh(nulos.index, nulos.values, color=[CATEGORICAL[1] if v > 5 else BLUE for v in nulos.values])
titulo(ax, "% de valores ausentes por coluna da silver")
ax.set_xlabel("% ausente (laranja: > 5%)")
ax.grid(axis="y", visible=False)
plt.tight_layout(); plt.show()
nulos[nulos > 0].round(2)'''),
    ("md", "## 4. Colunas categóricas\nCardinalidade e categorias dominantes: base para decidir o que vira filtro/cor nas visualizações."),
    ("code", '''cats = ["sexo_paciente", "raca_cor_paciente", "nacionalidade_paciente", "vacina_tipo", "sigla_vacina",
        "descricao_dose_vacina", "estrategia_vacinacao", "categoria_atendimento", "natureza_estabelecimento"]
resumo_cat = pd.DataFrame({
    "unicos": [df[c].nunique() for c in cats],
    "mais_frequente": [df[c].value_counts().index[0] for c in cats],
    "% mais_frequente": [100 * df[c].value_counts(normalize=True).iloc[0] for c in cats],
}, index=cats)
resumo_cat'''),
    ("md", """## 5. Idade
A idade vem em anos completos. Vacinação em massa de sarampo concentra-se em crianças pequenas; valores muito altos são candidatos a erro de digitação."""),
    ("code", '''idade = df["idade_paciente"].dropna().astype(int)
fig, ax = plt.subplots(figsize=(10, 4))
cont = idade.clip(upper=100).value_counts().sort_index()
ax.bar(cont.index, cont.values, color=BLUE, width=0.85)
titulo(ax, "Doses por idade do paciente (>= 100 agrupado em 100)")
ax.set_xlabel("Idade (anos)"); ax.set_ylabel("N de doses"); milhar(ax)
ax.set_yscale("log")
plt.tight_layout(); plt.show()
print("Idade > 100 anos:", f"{(idade > 100).sum():,}", "| idade > 110:", f"{(idade > 110).sum():,}", "| idade ausente:", df["idade_paciente"].isna().sum())'''),
    ("md", """## 6. Pacientes com muitas doses
`codigo_paciente_anonimizado` permite seguir a mesma pessoa. Poucas doses por pessoa são esperadas (esquema de 2 doses). Valores extremos indicam **colisão de identificador** (mesmo hash para pessoas diferentes, p.ex. CPF/CNS inválido) e devem ser filtrados em análises por paciente."""),
    ("code", '''por_paciente = df.groupby("codigo_paciente_anonimizado").size()
dist = por_paciente.clip(upper=6).value_counts().sort_index()
dist.index = [str(i) if i < 6 else "6+" for i in dist.index]
fig, ax = plt.subplots(figsize=(7, 4))
ax.bar(dist.index, dist.values, color=BLUE)
titulo(ax, "Pacientes por nº de doses na janela (jan/2025 - jun/2026)")
ax.set_xlabel("N de doses do paciente"); ax.set_ylabel("N de pacientes"); milhar(ax)
for i, v in enumerate(dist.values):
    ax.text(i, v, f"{v:,.0f}".replace(",", "."), ha="center", va="bottom", fontsize=9)
plt.tight_layout(); plt.show()
print("Pacientes únicos:", f"{por_paciente.size:,}")
print("Pacientes com > 10 doses (provável colisão de ID):", f"{(por_paciente > 10).sum():,}", "-> doses:", f"{por_paciente[por_paciente > 10].sum():,}")'''),
    ("md", """## 7. Descrição da dose x ordem real da dose
16% das linhas trazem a dose só como "Dose", sem número. A silver calcula `ordem_dose_paciente` (1ª, 2ª... dose do paciente **dentro da janela**) para resolver isso. Limite: doses aplicadas antes de jan/2025 não aparecem, então a ordem é um **mínimo**."""),
    ("code", '''ct = pd.crosstab(df["descricao_dose_vacina"], df["ordem_dose_paciente"].clip(upper=4))
ct = ct.loc[ct.sum(axis=1).sort_values(ascending=False).index].head(8)
ct.columns = ["1º na janela", "2º na janela", "3º na janela", "4º+ na janela"]
ct'''),
    ("md", "## 8. Registro no RNDS: atraso e datas inconsistentes"),
    ("code", '''at = df["atraso_registro_dias"].dropna().astype(int)
print("Datas de vacinação fora do mês do arquivo:", int(df["vacinacao_fora_do_mes"].sum()))
print("Registro antes da vacinação (atraso < 0):", int((at < 0).sum()))
print(at.describe(percentiles=[.5, .75, .9, .99]).round(1).to_string())'''),
    ("md", """## Conclusões da auditoria
- A silver está **sem duplicatas** de documento e sem diluentes; o funil (seção 2) documenta tudo o que saiu.
- A **data de vacinação sempre cai no mês do arquivo**, então `ano_mes` pode ser usado com segurança como período.
- Análises **por paciente** devem excluir pacientes com número absurdo de doses (colisão de ID).
- Para **cobertura vacinal** ainda falta o denominador populacional (IBGE/SINASC); as tabelas gold contam doses e pacientes vacinados, não cobertura."""),
]

# ---------------------------------------------------------------- 06 gold panorama
nb06 = [
    ("md", """# Camada Gold - Panorama da vacinação contra sarampo (jan/2025 - jun/2026)

Análises sobre as tabelas agregadas da **gold** (`data/vacinacao/processed/gold/`), geradas por `gerar_gold.py` a partir da silver. Todas cabem em memória e carregam em segundos.

Ver a auditoria da base em [05-silver-qualidade-vacinacao.ipynb](05-silver-qualidade-vacinacao.ipynb). Aqui, **dose** significa dose aplicada (não pessoa) e a "n-ésima dose" combina a descrição do registro com a ordem do paciente na janela."""),
    ("md", "## 1. Setup e KPIs mensais"),
    ("code", SETUP + '''
kpi = pd.read_parquet(GOLD / "gold_kpis_mensais.parquet")
uf_mes = pd.read_parquet(GOLD / "gold_doses_uf_mes.parquet")
dia = pd.read_parquet(GOLD / "gold_doses_dia.parquet")
perfil = pd.read_parquet(GOLD / "gold_perfil.parquet")
idade = pd.read_parquet(GOLD / "gold_idade_dose.parquet")

print(f"Doses no período: {kpi.doses.sum():,} | pacientes-mês: {kpi.pacientes_unicos.sum():,}")
kpi'''),
    ("md", "## 2. Doses por mês e por dose"),
    ("code", '''ordem_dose = ["Dose zero", "1ª dose", "2ª dose", "3ª dose ou mais", "Reforço/adicional"]
m = uf_mes.pivot_table(index="ano_mes", columns="dose_grupo", values="doses", aggfunc="sum").reindex(columns=ordem_dose).fillna(0)
fig, ax = plt.subplots(figsize=(11, 4.5))
base = np.zeros(len(m))
for cor, col in zip(CATEGORICAL, m.columns):
    ax.bar(m.index, m[col], bottom=base, label=col, color=cor)
    base += m[col].values
titulo(ax, "Doses de vacina com componente sarampo por mês")
ax.set_ylabel("N de doses"); milhar(ax)
ax.tick_params(axis="x", rotation=60)
ax.legend(frameon=False, ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.25))
plt.tight_layout(); plt.show()'''),
    ("md", "## 3. Série diária (média móvel de 7 dias)\nPicos e vales semanais (fins de semana, feriados) somem na média móvel e deixam a tendência e as campanhas visíveis."),
    ("code", '''d = dia.groupby("data_vacinacao")["doses"].sum().asfreq("D").fillna(0)
mm = d.rolling(7, center=True).mean()
fig, ax = plt.subplots(figsize=(11, 4))
ax.plot(d.index, d.values, color=MUTED, alpha=0.35, linewidth=0.8, label="Diário")
ax.plot(mm.index, mm.values, color=BLUE, linewidth=2, label="Média móvel 7 dias")
titulo(ax, "Doses aplicadas por dia")
ax.set_ylabel("N de doses"); milhar(ax); ax.legend(frameon=False)
plt.tight_layout(); plt.show()
print(f"Maior média semanal: {mm.max():,.0f} doses/dia, em torno de {mm.idxmax():%d/%m/%Y}")'''),
    ("md", "## 4. Tipo de vacina\nA tríplice viral (SCR) domina; a tetra viral (SCRV) cobre a dose aos 15 meses."),
    ("code", '''t = uf_mes.pivot_table(index="ano_mes", columns="vacina_tipo", values="doses", aggfunc="sum").fillna(0)
t = t.div(t.sum(axis=1), axis=0) * 100
fig, ax = plt.subplots(figsize=(11, 4))
t.plot.area(ax=ax, color=CATEGORICAL[: t.shape[1]], linewidth=0)
titulo(ax, "Participação de cada vacina nas doses do mês (%)")
ax.set_ylabel("%"); ax.set_xlabel(""); ax.set_ylim(0, 100)
ax.tick_params(axis="x", rotation=60)
ax.legend(frameon=False, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.28))
plt.tight_layout(); plt.show()'''),
    ("md", "## 5. Geografia: UF de residência do paciente"),
    ("code", '''uf = uf_mes.groupby("uf_paciente")["doses"].sum().sort_values()
fig, ax = plt.subplots(figsize=(8, 8))
ax.barh(uf.index.astype(str), uf.values, color=BLUE)
titulo(ax, "Doses por UF do paciente (jan/2025 - jun/2026)")
ax.set_xlabel("N de doses"); milhar(ax, "x"); ax.grid(axis="y", visible=False)
plt.tight_layout(); plt.show()'''),
    ("md", """### Calendário por UF
Cada célula é o volume do mês **relativo à média da própria UF** (100 = média). Assim se comparam ritmos entre UFs grandes e pequenas; células escuras = mês mais forte."""),
    ("code", '''h = uf_mes.pivot_table(index="uf_paciente", columns="ano_mes", values="doses", aggfunc="sum").fillna(0)
h = h[h.sum(axis=1) > 5000]
rel = h.div(h.mean(axis=1), axis=0) * 100
rel = rel.loc[h.sum(axis=1).sort_values(ascending=False).index]
fig, ax = plt.subplots(figsize=(12, 8))
im = ax.imshow(rel.values, aspect="auto", cmap="Blues")
ax.set_xticks(range(rel.shape[1])); ax.set_xticklabels(rel.columns, rotation=60)
ax.set_yticks(range(rel.shape[0])); ax.set_yticklabels(rel.index)
ax.grid(False)
titulo(ax, "Volume mensal relativo à média da UF (100 = média)")
fig.colorbar(im, ax=ax, shrink=0.6)
plt.tight_layout(); plt.show()'''),
    ("md", "## 6. Perfil demográfico"),
    ("code", '''fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
sx = perfil.groupby("sexo_paciente")["doses"].sum().sort_values(ascending=False)
axes[0].bar(sx.index, sx.values, color=CATEGORICAL[: len(sx)]); titulo(axes[0], "Sexo"); milhar(axes[0])
ordem = ["<1", "1", "2-4", "5-9", "10-14", "15-19", "20-29", "30-39", "40-49", "50-59", "60+"]
fx = perfil.groupby("faixa_etaria")["doses"].sum().reindex(ordem)
axes[1].bar(fx.index, fx.values, color=BLUE); titulo(axes[1], "Faixa etária (anos)"); milhar(axes[1])
axes[1].tick_params(axis="x", rotation=45)
rc = perfil.groupby("raca_cor_paciente")["doses"].sum().sort_values()
axes[2].barh(rc.index, rc.values, color=BLUE); titulo(axes[2], "Raça/cor"); milhar(axes[2], "x"); axes[2].grid(axis="y", visible=False)
plt.tight_layout(); plt.show()
(fx / fx.sum() * 100).round(1).rename("% das doses")'''),
    ("md", """### Idade e dose
Doses por idade simples, por número de dose: a 1ª dose se concentra em 1 ano (12 meses) e a 2ª, em 1-2 anos (15 meses/tetra viral); a cauda adulta indica bloqueios e campanhas de atualização."""),
    ("code", '''ia = idade.assign(idade=idade["idade_paciente"].clip(upper=80)).pivot_table(
    index="idade", columns="dose_grupo", values="doses", aggfunc="sum").fillna(0)
fig, ax = plt.subplots(figsize=(11, 4.5))
for cor, col in zip(CATEGORICAL, [c for c in ["1ª dose", "2ª dose", "Dose zero", "Reforço/adicional"] if c in ia.columns]):
    ax.plot(ia.index, ia[col], label=col, color=cor, linewidth=2)
titulo(ax, "Doses por idade do paciente e número da dose (>= 80 agrupado)")
ax.set_xlabel("Idade (anos)"); ax.set_ylabel("N de doses"); milhar(ax); ax.set_yscale("log")
ax.legend(frameon=False)
plt.tight_layout(); plt.show()'''),
    ("md", """## 7. Evolução dos KPIs
Além do volume, o mix do mês mostra mudanças de perfil: menos crianças de 1-4 anos e menos doses de rotina indicam campanhas/bloqueios com público mais amplo."""),
    ("code", '''fig, axes = plt.subplots(1, 2, figsize=(14, 4))
axes[0].plot(kpi["ano_mes"], kpi["pct_criancas_1a4"], color=BLUE, linewidth=2, marker="o")
titulo(axes[0], "% das doses em crianças de 1 a 4 anos"); axes[0].tick_params(axis="x", rotation=60)
axes[1].plot(kpi["ano_mes"], kpi["pct_rotina"], color=CATEGORICAL[1], linewidth=2, marker="o")
titulo(axes[1], "% das doses em estratégia de rotina"); axes[1].tick_params(axis="x", rotation=60)
plt.tight_layout(); plt.show()'''),
    ("md", """## Leituras
- O volume mensal oscila entre ~465 mil e ~825 mil doses; jul-set/2025 concentram os meses mais fortes, seguidos de queda em nov-dez.
- A participação da rotina cai de ~96% para ~88% no meio de 2025 e recupera depois, sinal de ações extras (campanhas/intensificação) naquele período.
- A gold conta **doses**. Para **cobertura** é preciso dividir pelo público-alvo (SINASC/IBGE por município), o próximo passo natural."""),
]

# ---------------------------------------------------------------- 07 gold criancas/municipios/atraso
nb07 = [
    ("md", """# Camada Gold - Crianças, municípios, estratégias e qualidade do registro

Continuação de [06-gold-panorama-vacinacao.ipynb](06-gold-panorama-vacinacao.ipynb), com as tabelas gold mais analíticas:

- **Coorte de crianças de 1-4 anos** por município (quantas receberam 1 e 2+ doses).
- **Estabelecimentos e estratégias** de vacinação.
- **Atraso** entre aplicar a dose e o registro chegar ao RNDS."""),
    ("md", "## 1. Setup"),
    ("code", SETUP + '''
coorte = pd.read_parquet(GOLD / "gold_coorte_criancas_municipio.parquet")
mun_mes = pd.read_parquet(GOLD / "gold_municipio_mes.parquet")
estab = pd.read_parquet(GOLD / "gold_estabelecimento.parquet")
atraso = pd.read_parquet(GOLD / "gold_atraso_registro.parquet")
print({n: len(t) for n, t in [("coorte", coorte), ("municipio_mes", mun_mes), ("estabelecimento", estab), ("atraso", atraso)]})'''),
    ("md", """## 2. Crianças de 1 a 4 anos: quem completou o esquema?
`criancas_vacinadas` = crianças distintas de 1-4 anos com ao menos uma dose na janela; `com_2_ou_mais` = com doses em ao menos duas datas diferentes. **Não é cobertura vacinal**: o denominador é quem já foi vacinado, não a população de crianças. Mede o quanto quem entrou no esquema **retornou** para a 2ª dose."""),
    ("code", '''uf = coorte.groupby("uf_paciente")[["criancas_vacinadas", "criancas_com_2_ou_mais_doses"]].sum()
uf["prop"] = uf["criancas_com_2_ou_mais_doses"] / uf["criancas_vacinadas"] * 100
uf = uf[uf["criancas_vacinadas"] > 1000].sort_values("prop")
media = uf["criancas_com_2_ou_mais_doses"].sum() / uf["criancas_vacinadas"].sum() * 100
fig, ax = plt.subplots(figsize=(8, 8))
ax.barh(uf.index.astype(str), uf["prop"], color=BLUE)
ax.axvline(media, color=CATEGORICAL[1], linestyle="--", linewidth=1.5)
ax.text(media, -0.9, f" média {media:.1f}%", color=CATEGORICAL[1], fontsize=9)
titulo(ax, "% das crianças de 1-4 anos vacinadas que já têm 2 ou mais doses")
ax.set_xlabel("%"); ax.grid(axis="y", visible=False)
plt.tight_layout(); plt.show()'''),
    ("md", "### Distribuição entre municípios (mín. 100 crianças vacinadas)"),
    ("code", '''c = coorte[coorte["criancas_vacinadas"] >= 100].copy()
fig, ax = plt.subplots(figsize=(9, 4))
ax.hist(c["prop_com_2_ou_mais"] * 100, bins=40, color=BLUE)
ax.axvline(c["prop_com_2_ou_mais"].median() * 100, color=CATEGORICAL[1], linestyle="--")
titulo(ax, f"Municípios por % de crianças com 2+ doses (n = {len(c):,})")
ax.set_xlabel("% com 2 ou mais doses"); ax.set_ylabel("N de municípios")
plt.tight_layout(); plt.show()

cols = ["municipio", "uf_paciente", "criancas_vacinadas", "prop_com_2_ou_mais"]
print("Menores proporções:"); display(c.nsmallest(10, "prop_com_2_ou_mais")[cols])
print("Maiores proporções:"); display(c.nlargest(10, "prop_com_2_ou_mais")[cols])'''),
    ("md", "## 3. Municípios com mais doses"),
    ("code", '''top = mun_mes.groupby(["codigo_municipio_paciente", "municipio", "uf"], as_index=False)["doses"].sum().nlargest(15, "doses").iloc[::-1]
fig, ax = plt.subplots(figsize=(8, 5.5))
ax.barh(top["municipio"] + " (" + top["uf"] + ")", top["doses"], color=BLUE)
titulo(ax, "15 municípios com mais doses aplicadas a residentes")
milhar(ax, "x"); ax.grid(axis="y", visible=False)
plt.tight_layout(); plt.show()'''),
    ("md", "## 4. Estratégia e tipo de estabelecimento"),
    ("code", '''e = estab.pivot_table(index="ano_mes", columns="estrategia_vacinacao", values="doses", aggfunc="sum").fillna(0)
share_rotina = e["Rotina"].sum() / e.sum().sum() * 100
principais = e.drop(columns="Rotina").sum().nlargest(5).index
fora = e[principais].copy(); fora["Outras"] = e.drop(columns=list(principais) + ["Rotina"]).sum(axis=1)
fig, ax = plt.subplots(figsize=(11, 4.5))
base = np.zeros(len(fora))
for cor, col in zip(CATEGORICAL, fora.columns):
    ax.bar(fora.index, fora[col], bottom=base, label=col, color=cor); base += fora[col].values
titulo(ax, f"Doses fora da rotina por estratégia (rotina omitida: {share_rotina:.0f}% do total)")
ax.set_ylabel("N de doses"); milhar(ax); ax.tick_params(axis="x", rotation=60)
ax.legend(frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.28))
plt.tight_layout(); plt.show()'''),
    ("code", '''sem = "Sem registro"
tipo = estab.fillna({"tipo_estabelecimento": sem}).groupby("tipo_estabelecimento")["doses"].sum().nlargest(10).iloc[::-1]
nat = estab.fillna({"natureza_estabelecimento": sem}).groupby("natureza_estabelecimento")["doses"].sum()
fig, axes = plt.subplots(1, 2, figsize=(14, 4.5), gridspec_kw={"width_ratios": [2, 1]})
axes[0].barh(tipo.index.str.slice(0, 45), tipo.values, color=BLUE); titulo(axes[0], "Top 10 tipos de estabelecimento"); milhar(axes[0], "x"); axes[0].grid(axis="y", visible=False)
axes[1].bar(nat.index.str.slice(0, 22), nat.values, color=CATEGORICAL[: len(nat)]); titulo(axes[1], "Natureza jurídica"); milhar(axes[1]); axes[1].tick_params(axis="x", rotation=30)
plt.tight_layout(); plt.show()'''),
    ("md", """## 5. Atraso no registro (qualidade do dado)
Diferença entre a data da dose e a data em que o registro entrou no RNDS. Atraso alto significa que os números **mais recentes ficam subestimados** até os registros chegarem; cuidado ao interpretar os últimos meses."""),
    ("code", '''ordem = ["Mesmo dia", "1-7 dias", "8-30 dias", "31-90 dias", "> 90 dias"]
a = atraso.pivot_table(index="ano_mes", columns="faixa_atraso", values="doses", aggfunc="sum").reindex(columns=ordem).fillna(0)
a = a.div(a.sum(axis=1), axis=0) * 100
fig, ax = plt.subplots(figsize=(11, 4.5))
base = np.zeros(len(a))
for cor, col in zip(["#2a78d6", "#1baf7a", "#eda100", "#eb6834", "#e34948"], a.columns):
    ax.bar(a.index, a[col], bottom=base, label=col, color=cor); base += a[col].values
titulo(ax, "Tempo entre a dose e o registro no RNDS (% das doses do mês)")
ax.set_ylabel("%"); ax.tick_params(axis="x", rotation=60)
ax.legend(frameon=False, ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.28))
plt.tight_layout(); plt.show()'''),
    ("code", '''por_uf = atraso.pivot_table(index="uf_paciente", columns="faixa_atraso", values="doses", aggfunc="sum").fillna(0)
por_uf["total"] = por_uf.sum(axis=1)
por_uf = por_uf[por_uf["total"] > 5000]
s = ((por_uf["31-90 dias"] + por_uf["> 90 dias"]) / por_uf["total"] * 100).sort_values()
fig, ax = plt.subplots(figsize=(8, 8))
ax.barh(s.index.astype(str), s.values, color=BLUE)
titulo(ax, "% das doses registradas com mais de 30 dias de atraso, por UF")
ax.set_xlabel("%"); ax.grid(axis="y", visible=False)
plt.tight_layout(); plt.show()'''),
    ("md", """## Leituras
- A proporção de crianças de 1-4 anos com 2+ doses varia entre UFs e municípios: candidata a mapa e a priorização de busca ativa.
- Municípios com poucas crianças produzem proporções instáveis (por isso o corte mínimo de 100).
- O atraso de registro é heterogêneo entre UFs e caiu ao longo de 2025, o que também afeta quão "completo" está o mês mais recente."""),
]

if __name__ == "__main__":
    for nome, cells in [("05-silver-qualidade-vacinacao", nb05), ("06-gold-panorama-vacinacao", nb06),
                        ("07-gold-criancas-municipios-atraso", nb07)]:
        nb(cells, Path("notebooks") / f"{nome}.ipynb")
        print("ok", nome)
