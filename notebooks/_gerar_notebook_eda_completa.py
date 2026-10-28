"""Gera o notebook 08 (EDA completa da vacinação contra sarampo, sobre as tabelas gold). Rodar da raiz do projeto."""
from pathlib import Path

import nbformat as nbf

SETUP = '''from pathlib import Path

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
pd.options.display.max_columns = 40

GOLD = Path("..") / "data" / "gold" / "vacinacao"
SEM = "Sem registro"
ORDEM_IDADE = ["<1", "1", "2-4", "5-9", "10-14", "15-19", "20-29", "30-39", "40-49", "50-59", "60+"]


def ler(nome):
    return pd.read_parquet(GOLD / f"{nome}.parquet")


def tabela(dados, linhas, colunas):
    """Doses somadas por linhas x colunas (equivale ao crosstab sobre a base dose a dose)."""
    return dados.pivot_table(index=linhas, columns=colunas, values="doses", aggfunc="sum", fill_value=0, observed=True)


def quantil_ponderado(valores, pesos, q):
    """Quantil de uma variável guardada como (valor, nº de ocorrências)."""
    ordem = np.argsort(valores)
    v, w = np.asarray(valores, dtype=float)[ordem], np.asarray(pesos, dtype=float)[ordem]
    acum = np.cumsum(w) / w.sum()
    return np.array([v[np.searchsorted(acum, x)] for x in np.atleast_1d(q)])


def milhar(ax, eixo="y"):
    fmt = mtick.FuncFormatter(lambda v, _: f"{v:,.0f}".replace(",", "."))
    (ax.yaxis if eixo == "y" else ax.xaxis).set_major_formatter(fmt)


def titulo(ax, texto):
    ax.set_title(texto, loc="left", fontweight="bold")


def empilhado_pct(ax, tabela, cores=None, legenda_col=4):
    """Barras empilhadas 100%: tabela com linhas = categorias do eixo x, colunas = fatias."""
    pct = tabela.div(tabela.sum(axis=1), axis=0) * 100
    base = np.zeros(len(pct))
    for cor, col in zip(cores or CATEGORICAL, pct.columns):
        ax.bar(pct.index.astype(str), pct[col], bottom=base, label=col, color=cor)
        base += pct[col].values
    ax.set_ylabel("% das doses"); ax.set_ylim(0, 100)
    ax.legend(frameon=False, ncol=legenda_col, loc="upper center", bbox_to_anchor=(0.5, -0.22))
    return pct
'''

cells = []
md = lambda t: cells.append(("md", t))
code = lambda t: cells.append(("code", t))

md("""# EDA completa - Vacinação contra sarampo (SI-PNI/RNDS)

Análise exploratória de todas as doses de vacinas com componente de sarampo (tríplice viral SCR, tetra viral SCRV, dupla viral SR), a partir das **tabelas gold** em `data/gold/vacinacao/`. Cada tabela gold é uma contagem de doses por combinação de variáveis, feita pelo `pipeline/09_gold_vacinacao.py` sobre a base silver (uma linha por dose); aqui só somamos as contagens, então os números são os mesmos que sairiam da silver, sem precisar dela.

Complementa os notebooks anteriores:
- [05-silver-qualidade-vacinacao.ipynb](05-silver-qualidade-vacinacao.ipynb): qualidade e funil de processamento.
- [06-gold-panorama-vacinacao.ipynb](06-gold-panorama-vacinacao.ipynb) e [07-gold-criancas-municipios-atraso.ipynb](07-gold-criancas-municipios-atraso.ipynb): panorama e crianças/municípios.

Índice: 1. Visão geral · 2. Tempo · 3. Vacina e dose · 4. Pessoa e intervalo entre doses · 5. Demografia · 6. Geografia e deslocamento · 7. Estabelecimentos · 8. Estratégias · 9. Adultos · 10. Síntese""")

md("## 1. Visão geral")
code(SETUP + """
resumo = ler("gold_resumo_geral").iloc[0]
dia = ler("gold_doses_dia")
perfil = ler("gold_perfil")
print(f"{resumo['doses']:,} doses | {resumo['pacientes_distintos']:,} pacientes distintos | "
      f"{resumo['data_vacinacao_min']:%d/%m/%Y} a {resumo['data_vacinacao_max']:%d/%m/%Y}")

dic = ler("gold_qualidade_colunas").set_index("coluna").rename(columns={"pct_nulos": "% nulos", "unicos": "únicos"})
dic[["tipo", "% nulos", "únicos", "exemplo"]]""")

md("## 2. Tempo")
md("### 2.1 Ano contra ano: 2025 x 2026\\nCompara, mês a mês, os meses que existem nos dois anos.")
code("""dia["ano"] = dia["data_vacinacao"].dt.year
dia["mes"] = dia["data_vacinacao"].dt.month
por_mes = dia.groupby(["mes", "ano"])["doses"].sum().unstack()
sem = por_mes[[2025, 2026]].dropna()
meses = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
fig, ax = plt.subplots(figsize=(9, 4))
x = np.arange(len(sem))
ax.bar(x - 0.2, sem[2025], 0.4, label="2025", color=MUTED)
ax.bar(x + 0.2, sem[2026], 0.4, label="2026", color=BLUE)
ax.set_xticks(x); ax.set_xticklabels([meses[m - 1] for m in sem.index])
titulo(ax, "Doses por mês: 2025 x 2026"); ax.set_ylabel("N de doses"); milhar(ax); ax.legend(frameon=False)
plt.tight_layout(); plt.show()
var = (sem[2026] / sem[2025] - 1) * 100
print("Variação 2026/2025 por mês (%):", var.round(1).to_dict())
print(f"Meses comparados: 2025 = {sem[2025].sum():,.0f} | 2026 = {sem[2026].sum():,.0f} | {(sem[2026].sum()/sem[2025].sum()-1)*100:+.1f}%")""")

md("### 2.2 Dia da semana e dia do mês\\nA vacinação de rotina ocorre em dias úteis; o dia do mês revela efeitos de fim de mês e de registro em lote.")
code("""dias = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
dow = dia.groupby(dia["data_vacinacao"].dt.dayofweek)["doses"].sum().sort_index()
dom = dia.groupby(dia["data_vacinacao"].dt.day)["doses"].sum().sort_index()
fig, axes = plt.subplots(1, 2, figsize=(14, 4))
axes[0].bar(dias, dow.values, color=[BLUE] * 5 + [CATEGORICAL[1]] * 2); titulo(axes[0], "Doses por dia da semana"); milhar(axes[0])
axes[1].bar(dom.index, dom.values, color=BLUE); titulo(axes[1], "Doses por dia do mês"); milhar(axes[1]); axes[1].set_xlabel("Dia do mês")
plt.tight_layout(); plt.show()
print(f"Fim de semana: {(dow[5] + dow[6]) / dow.sum() * 100:.1f}% das doses")""")

md("### 2.3 Calendário: mês x dia da semana\\nMostra se campanhas de sábado (dia D) mudam o padrão semanal em algum mês.")
code("""cal = dia.groupby(["ano_mes", dia["data_vacinacao"].dt.dayofweek])["doses"].sum().unstack().fillna(0)
cal = cal.div(cal.sum(axis=1), axis=0) * 100
cal.columns = dias
fig, ax = plt.subplots(figsize=(9, 7))
im = ax.imshow(cal.values, aspect="auto", cmap="Blues")
ax.set_xticks(range(7)); ax.set_xticklabels(cal.columns); ax.set_yticks(range(len(cal))); ax.set_yticklabels(cal.index); ax.grid(False)
for i in range(cal.shape[0]):
    for j in range(cal.shape[1]):
        ax.text(j, i, f"{cal.values[i, j]:.0f}", ha="center", va="center", fontsize=8,
                color="white" if cal.values[i, j] > cal.values.max() * 0.6 else TEXT_PRIMARY)
titulo(ax, "% das doses do mês em cada dia da semana")
fig.colorbar(im, ax=ax, shrink=0.6); plt.tight_layout(); plt.show()""")

md("## 3. Vacina e dose")
md("### 3.1 Tipo de vacina x faixa etária\\nCada faixa etária tem um produto característico: a tetra viral (SCRV) é dada aos 15 meses; a SCR cobre o resto.")
code("""t = tabela(perfil, "faixa_etaria", "vacina_tipo").reindex(ORDEM_IDADE)
fig, ax = plt.subplots(figsize=(10, 4.5))
pct = empilhado_pct(ax, t, legenda_col=4)
titulo(ax, "Vacina aplicada por faixa etária (% das doses)"); ax.set_xlabel("Faixa etária (anos)")
plt.tight_layout(); plt.show()
pct.round(1)""")

md("### 3.2 Número da dose x faixa etária\\nO número da dose (`dose_grupo`) é classificado no passo 09: número da descrição da dose, ou a ordem do paciente na janela quando a descrição é só “Dose”; reforços ficam à parte.")
code("""ordem_dose = ["Dose zero", "1ª dose", "2ª dose", "3ª dose ou mais", "Reforço/adicional"]
t = tabela(perfil, "faixa_etaria", "dose_grupo").reindex(index=ORDEM_IDADE, columns=ordem_dose).fillna(0)
fig, ax = plt.subplots(figsize=(10, 4.5))
empilhado_pct(ax, t, legenda_col=5); titulo(ax, "Número da dose por faixa etária (% das doses)"); ax.set_xlabel("Faixa etária (anos)")
plt.tight_layout(); plt.show()""")

md("""## 4. Pessoa e intervalo entre doses
### 4.1 Do intervalo 1ª -> 2ª dose
Pacientes com ao menos duas doses na janela (excluindo IDs com mais de 10 doses, provável colisão). O calendário prevê a 2ª dose (tetra viral) aos 15 meses; intervalos muito curtos indicam registro duplicado ou dose de bloqueio, e muito longos, esquema atrasado.""")
code("""par = ler("gold_intervalo_doses").dropna(subset=["intervalo_dias"])
par["intervalo_dias"] = par["intervalo_dias"].astype(int)
n_par = par["pacientes"].sum()
q = quantil_ponderado(par["intervalo_dias"], par["pacientes"], [.1, .25, .5, .75, .9])
media = np.average(par["intervalo_dias"], weights=par["pacientes"])
print(f"{n_par:,} pacientes com 1ª e 2ª dose na janela")
print(f"média {media:.0f} | P10 {q[0]:.0f} | P25 {q[1]:.0f} | mediana {q[2]:.0f} | P75 {q[3]:.0f} | P90 {q[4]:.0f} | "
      f"mín {par['intervalo_dias'].min()} | máx {par['intervalo_dias'].max()}")
pct_de = lambda cond: par.loc[cond, "pacientes"].sum() / n_par * 100
print(f"Mesmo dia: {pct_de(par['intervalo_dias'] == 0):.1f}% | até 30 dias: {pct_de(par['intervalo_dias'] <= 30):.1f}% | mais de 1 ano: {pct_de(par['intervalo_dias'] > 365):.1f}%")

fig, ax = plt.subplots(figsize=(11, 4))
ax.hist(par["intervalo_dias"].clip(upper=540), bins=90, weights=par["pacientes"], color=BLUE)
titulo(ax, "Intervalo entre a 1ª e a 2ª dose (dias; >= 540 agrupado)")
ax.set_xlabel("Dias"); ax.set_ylabel("N de pacientes"); milhar(ax)
plt.tight_layout(); plt.show()""")

md("Mediana do intervalo por idade na 1ª dose (crianças de 0 a 10 anos):")
code("""g = (par[par["idade_primeira_dose"].between(0, 10)].groupby("idade_primeira_dose")
       .apply(lambda x: pd.Series({"median": quantil_ponderado(x["intervalo_dias"], x["pacientes"], .5)[0],
                                   "count": x["pacientes"].sum()})))
g = g[g["count"] > 500]
fig, ax = plt.subplots(figsize=(8, 4))
ax.bar(g.index.astype(int).astype(str), g["median"], color=BLUE)
titulo(ax, "Mediana do intervalo 1ª -> 2ª dose por idade na 1ª dose"); ax.set_xlabel("Idade na 1ª dose (anos)"); ax.set_ylabel("Dias")
plt.tight_layout(); plt.show()""")

md("## 5. Demografia")
md("### 5.1 Sexo por faixa etária")
code("""t = tabela(perfil, "faixa_etaria", "sexo_paciente").reindex(ORDEM_IDADE)
razao = (t["Masculino"] / t["Feminino"]).round(3)
fig, ax = plt.subplots(figsize=(10, 4))
ax.bar(razao.index.astype(str), razao.values, color=BLUE); ax.axhline(1, color=CATEGORICAL[1], linestyle="--")
titulo(ax, "Razão homens/mulheres nas doses, por faixa etária"); ax.set_xlabel("Faixa etária (anos)")
plt.tight_layout(); plt.show()
print("Ignorado:", f"{perfil.loc[perfil['sexo_paciente'] == 'Ignorado', 'doses'].sum():,}")""")

md("""### 5.2 Raça/cor por faixa etária
"Sem informação" alto em alguma faixa significa que o preenchimento varia com o serviço de origem, o que limita análises de equidade.""")
code("""perfil["raca"] = perfil["raca_cor_paciente"].astype("string").fillna(SEM)
t = tabela(perfil, "faixa_etaria", "raca").reindex(ORDEM_IDADE)
ordem_col = t.sum().sort_values(ascending=False).index
fig, ax = plt.subplots(figsize=(11, 4.5))
pct = empilhado_pct(ax, t[ordem_col], legenda_col=6); titulo(ax, "Raça/cor por faixa etária (% das doses)"); ax.set_xlabel("Faixa etária (anos)")
plt.tight_layout(); plt.show()
raca = perfil.groupby("raca")["doses"].sum()
print((raca / raca.sum() * 100).sort_values(ascending=False).round(1).to_dict())""")

md("### 5.3 Nacionalidade e povos indígenas")
code("""ne = ler("gold_nacionalidade_etnia")
nac = (ne.assign(nac=ne["nacionalidade_paciente"].map({"B": "Brasileiro", "E": "Estrangeiro", "N": "Naturalizado"}).fillna(SEM))
         .groupby("nac")["doses"].sum().sort_values(ascending=False))
etnia = ne.dropna(subset=["etnia_indigena_paciente"]).groupby("etnia_indigena_paciente")["doses"].sum()
ind = etnia.sort_values(ascending=False).head(15).iloc[::-1]
fig, axes = plt.subplots(1, 2, figsize=(14, 4.5), gridspec_kw={"width_ratios": [1, 2]})
axes[0].bar(nac.index, nac.values, color=CATEGORICAL[: len(nac)]); titulo(axes[0], "Nacionalidade"); milhar(axes[0])
axes[0].set_yscale("log")
axes[1].barh(ind.index.astype(str), ind.values, color=BLUE); titulo(axes[1], f"15 etnias com mais doses (de {len(etnia)} registradas)"); milhar(axes[1], "x"); axes[1].grid(axis="y", visible=False)
plt.tight_layout(); plt.show()
print("Doses em pessoas com etnia indígena informada:", f"{etnia.sum():,}", f"({etnia.sum() / ne['doses'].sum() * 100:.2f}%)")""")

md("## 6. Geografia e deslocamento")
md("### 6.1 Perfil etário de cada UF\\nUFs com mais doses em adultos indicam mais bloqueios/campanhas de atualização; as com mais crianças, vacinação de rotina.")
code("""GRUPO_ETARIO = {"<1": "<1", "1": "1-4", "2-4": "1-4", "5-9": "5-19", "10-14": "5-19", "15-19": "5-19"}
perfil["grupo_etario"] = perfil["faixa_etaria"].astype("string").map(lambda f: GRUPO_ETARIO.get(f, "20+") if pd.notna(f) else pd.NA)
t = tabela(perfil, "uf_paciente", "grupo_etario")[["<1", "1-4", "5-19", "20+"]]
t = t[t.sum(axis=1) > 5000]
t = t.loc[(t["20+"] / t.sum(axis=1)).sort_values().index]
fig, ax = plt.subplots(figsize=(11, 5))
pct = empilhado_pct(ax, t, cores=[CATEGORICAL[2], BLUE, CATEGORICAL[3], CATEGORICAL[1]], legenda_col=4)
titulo(ax, "Perfil etário das doses por UF (ordenado pela % de adultos)")
ax.tick_params(axis="x", rotation=90); plt.tight_layout(); plt.show()
print("Maior % de adultos (20+):", pct["20+"].nlargest(3).round(1).to_dict(), "| menor:", pct["20+"].nsmallest(3).round(1).to_dict())""")

md("""### 6.2 Deslocamento interestadual
Doses aplicadas em UF diferente da de residência do paciente (fronteiras, trabalho, turismo, registro errado).""")
code("""v = ler("gold_fluxo_uf").dropna(subset=["uf_paciente", "uf_estabelecimento"])
v["fora"] = v["uf_paciente"] != v["uf_estabelecimento"]
pct_fora = v.loc[v["fora"], "doses"].sum() / v["doses"].sum() * 100
print(f"Doses aplicadas fora da UF de residência: {v.loc[v['fora'], 'doses'].sum():,} ({pct_fora:.2f}%)")
por_uf_tot = v.groupby("uf_paciente")["doses"].sum()
por_uf = v[v["fora"]].groupby("uf_paciente")["doses"].sum().reindex(por_uf_tot.index, fill_value=0) / por_uf_tot * 100
por_uf = por_uf[por_uf_tot > 5000].sort_values()
fig, ax = plt.subplots(figsize=(8, 7))
ax.barh(por_uf.index, por_uf.values, color=BLUE); titulo(ax, "% das doses de cada UF aplicadas em outra UF"); ax.set_xlabel("%"); ax.grid(axis="y", visible=False)
plt.tight_layout(); plt.show()
fluxo = v[v["fora"]].set_index(["uf_paciente", "uf_estabelecimento"])["doses"].nlargest(10)
print("Maiores fluxos (residência -> aplicação):"); fluxo""")

md("### 6.3 Concentração por município\\nQuão concentradas estão as doses nos maiores municípios.")
code("""pm = ler("gold_municipio_mes").groupby("codigo_municipio_paciente")["doses"].sum().sort_values(ascending=False)
acum = pm.cumsum() / pm.sum() * 100
fig, axes = plt.subplots(1, 2, figsize=(14, 4.5))
axes[0].hist(np.log10(pm.values), bins=40, color=BLUE); titulo(axes[0], "Municípios por nº de doses (escala log10)"); axes[0].set_xlabel("log10(doses no município)")
axes[1].plot(np.arange(1, len(acum) + 1) / len(acum) * 100, acum.values, color=BLUE, linewidth=2); axes[1].plot([0, 100], [0, 100], color=MUTED, linestyle="--")
titulo(axes[1], "Curva de concentração de doses entre municípios"); axes[1].set_xlabel("% dos municípios (do maior ao menor)"); axes[1].set_ylabel("% acumulado das doses")
plt.tight_layout(); plt.show()
n = len(pm)
print(f"{n:,} municípios | 10 maiores = {pm.head(10).sum() / pm.sum() * 100:.1f}% das doses | 10% maiores ({int(n * .1)} municípios) = {pm.head(int(n * .1)).sum() / pm.sum() * 100:.1f}%")""")

md("## 7. Estabelecimentos")
md("### 7.1 Concentração por estabelecimento (CNES)")
code("""pe = (ler("gold_estabelecimento_cnes").dropna(subset=["codigo_cnes_estabelecimento"])
        .groupby("codigo_cnes_estabelecimento")["doses"].sum().sort_values(ascending=False))
acum = pe.cumsum() / pe.sum() * 100
fig, axes = plt.subplots(1, 2, figsize=(14, 4.5))
axes[0].hist(np.log10(pe.values), bins=40, color=BLUE); titulo(axes[0], "Estabelecimentos por nº de doses (log10)"); axes[0].set_xlabel("log10(doses no estabelecimento)")
axes[1].plot(np.arange(1, len(acum) + 1) / len(acum) * 100, acum.values, color=BLUE, linewidth=2); axes[1].plot([0, 100], [0, 100], color=MUTED, linestyle="--")
titulo(axes[1], "Curva de concentração entre estabelecimentos"); axes[1].set_xlabel("% dos estabelecimentos"); axes[1].set_ylabel("% acumulado das doses")
plt.tight_layout(); plt.show()
n = len(pe)
print(f"{n:,} estabelecimentos | 10% maiores = {pe.head(int(n * .1)).sum() / pe.sum() * 100:.1f}% das doses | mediana = {pe.median():.0f} doses/estabelecimento | maior = {pe.iloc[0]:,}")""")

md("### 7.2 Tipo de estabelecimento por faixa etária\\nOnde cada público é vacinado (UBS, clínica privada, hospital...).")
code("""ef = ler("gold_estrategia_faixa")
for coluna in ["tipo_estabelecimento", "natureza_estabelecimento", "estrategia_vacinacao"]:
    ef[coluna] = ef[coluna].astype("string").fillna(SEM)
top = ef.groupby("tipo_estabelecimento")["doses"].sum().nlargest(5).index
ef["tipo_estab_g"] = ef["tipo_estabelecimento"].where(ef["tipo_estabelecimento"].isin(top), "Outros")
t = tabela(ef, "faixa_etaria", "tipo_estab_g").reindex(ORDEM_IDADE)
fig, ax = plt.subplots(figsize=(11, 4.5))
empilhado_pct(ax, t, legenda_col=3); titulo(ax, "Tipo de estabelecimento por faixa etária (% das doses)"); ax.set_xlabel("Faixa etária (anos)")
plt.tight_layout(); plt.show()""")

md("### 7.3 Rede privada ao longo do tempo\\nParticipação do setor privado (natureza jurídica de entidade empresarial) nas doses de cada mês.")
code("""nat = tabela(ef, "ano_mes", "natureza_estabelecimento")
print("Naturezas:", nat.sum().sort_values(ascending=False).to_dict())
pct = nat.div(nat.sum(axis=1), axis=0) * 100
fig, ax = plt.subplots(figsize=(11, 4))
for cor, col in zip(CATEGORICAL, pct.sum().sort_values(ascending=False).index[:4]):
    ax.plot(pct.index, pct[col], label=col, color=cor, linewidth=2, marker="o", markersize=3)
titulo(ax, "% das doses por natureza jurídica do estabelecimento"); ax.set_ylabel("%"); ax.tick_params(axis="x", rotation=60); ax.legend(frameon=False)
plt.tight_layout(); plt.show()""")

md("## 8. Estratégias de vacinação")
code("""top = ef.groupby("estrategia_vacinacao")["doses"].sum().nlargest(5).index
ef["estrategia_g"] = ef["estrategia_vacinacao"].where(ef["estrategia_vacinacao"].isin(top), "Outras")
fora = ef[ef["estrategia_g"] != "Rotina"]
t = tabela(fora, "ano_mes", "estrategia_g")
fig, axes = plt.subplots(1, 2, figsize=(15, 4.5), gridspec_kw={"width_ratios": [3, 2]})
base = np.zeros(len(t))
for cor, col in zip(CATEGORICAL, t.columns):
    axes[0].bar(t.index, t[col], bottom=base, label=col, color=cor); base += t[col].values
titulo(axes[0], "Doses fora da rotina por estratégia e mês"); axes[0].tick_params(axis="x", rotation=60); milhar(axes[0])
axes[0].legend(frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.28))
t2 = tabela(fora, "faixa_etaria", "estrategia_g").reindex(ORDEM_IDADE)
pct = t2.div(t2.sum(axis=1), axis=0) * 100
b = np.zeros(len(pct))
for cor, col in zip(CATEGORICAL, pct.columns):
    axes[1].bar(pct.index.astype(str), pct[col], bottom=b, color=cor); b += pct[col].values
titulo(axes[1], "Composição da vacinação fora da rotina por idade (%)"); axes[1].set_xlabel("Faixa etária")
plt.tight_layout(); plt.show()
pct_rotina = ef.loc[ef["estrategia_g"] == "Rotina", "doses"].sum() / ef["doses"].sum() * 100
print(f"Rotina: {pct_rotina:.1f}% das doses")""")

md("### Categoria de atendimento\\nCampo preenchido só em parte dos registros (o percentual aparece abaixo); indica os públicos-alvo prioritários.")
code("""ca = ler("gold_categoria_atendimento")
cat = ca.dropna(subset=["categoria_atendimento"]).groupby("categoria_atendimento")["doses"].sum().sort_values(ascending=False)
print(f"Preenchido em {cat.sum() / ca['doses'].sum() * 100:.1f}% das doses")
cat.head(10).iloc[::-1].plot.barh(figsize=(8, 4), color=BLUE); titulo(plt.gca(), "Categorias de atendimento mais frequentes"); plt.gca().grid(axis="y", visible=False)
plt.tight_layout(); plt.show()""")

md("""## 9. Adultos e campanhas de atualização
Adultos de 20 a 59 anos raramente entram na rotina. Picos nessa faixa apontam para bloqueios de surto ou campanhas de atualização.""")
code("""ad = perfil[perfil["faixa_etaria"].isin(["20-29", "30-39", "40-49", "50-59"])]
por_mes = ad.groupby("ano_mes")["doses"].sum()
total = perfil.groupby("ano_mes")["doses"].sum()
fig, axes = plt.subplots(1, 2, figsize=(14, 4))
axes[0].bar(por_mes.index, por_mes.values, color=BLUE); titulo(axes[0], "Doses em adultos (20-59 anos) por mês"); axes[0].tick_params(axis="x", rotation=60); milhar(axes[0])
axes[1].plot(por_mes.index, (por_mes / total * 100).values, color=CATEGORICAL[1], linewidth=2, marker="o"); titulo(axes[1], "% das doses do mês em adultos 20-59"); axes[1].tick_params(axis="x", rotation=60)
plt.tight_layout(); plt.show()
uf_ad = ad.groupby("uf_paciente")["doses"].sum().nlargest(8)
print("UFs com mais doses em adultos:", uf_ad.to_dict())""")

md("### Adultos: campanhas por UF e mês\\nCélula = doses em adultos 20-59 na UF e mês, relativo à média da UF (100 = média). Manchas escuras isoladas = ação pontual.")
code("""h = tabela(ad, "uf_paciente", "ano_mes")
h = h[h.sum(axis=1) > 5000]
rel = h.div(h.mean(axis=1), axis=0) * 100
rel = rel.loc[h.sum(axis=1).sort_values(ascending=False).index]
fig, ax = plt.subplots(figsize=(12, 7))
im = ax.imshow(rel.values, aspect="auto", cmap="Blues")
ax.set_xticks(range(rel.shape[1])); ax.set_xticklabels(rel.columns, rotation=60); ax.set_yticks(range(rel.shape[0])); ax.set_yticklabels(rel.index); ax.grid(False)
titulo(ax, "Doses em adultos 20-59 por UF e mês (100 = média da UF)"); fig.colorbar(im, ax=ax, shrink=0.6)
plt.tight_layout(); plt.show()""")

md("## 10. Síntese")
code("""tot = perfil["doses"].sum()
idade = ler("gold_idade_dose")
pct_idade = lambda a, b: idade.loc[idade["idade_paciente"].between(a, b), "doses"].sum() / tot * 100
pct_vacina = perfil.groupby("vacina_tipo")["doses"].sum() / tot * 100
privada = ef.loc[ef["natureza_estabelecimento"].isin(["ENTIDADES EMPRESARIAIS", "PESSOAS FISICAS"]), "doses"].sum() / ef["doses"].sum() * 100
print("SÍNTESE DA BASE")
print(f"- {tot:,} doses em {resumo['meses']} meses; {resumo['pacientes_distintos']:,} pacientes distintos; {resumo['municipios_residencia']:,} municípios de residência; {resumo['estabelecimentos']:,} estabelecimentos.")
print(f"- Crianças de 1-4 anos: {pct_idade(1, 4):.1f}% das doses; adultos 20-59: {pct_idade(20, 59):.1f}%.")
print(f"- SCR: {pct_vacina.get('Tríplice viral (SCR)', 0):.1f}% | SCRV: {pct_vacina.get('Tetra viral (SCRV)', 0):.1f}% | SR: {pct_vacina.get('Dupla viral (SR)', 0):.1f}%.")
print(f"- Rotina: {pct_rotina:.1f}% | rede privada (entidades empresariais e pessoas físicas): {privada:.1f}%.")
print(f"- Intervalo mediano 1ª -> 2ª dose: {quantil_ponderado(par['intervalo_dias'], par['pacientes'], .5)[0]:.0f} dias.")
print(f"- Doses aplicadas fora da UF de residência: {pct_fora:.2f}%.")""")

md("""## Próximos passos
1. **Denominador populacional** (IBGE/SINASC por município e idade) para transformar doses em **cobertura vacinal** por município.
2. **Casos confirmados** (SINAN) x vacinação: cruzar surtos com queda de cobertura/atraso da 2ª dose, com os dados de `data/gold/sinan/`.
3. **Bloqueios**: usar os picos em adultos e a estratégia "Intensificação"/"Monitoramento" para identificar ações de resposta a surtos.
4. **Mapas** por município (malha IBGE) com as tabelas gold.""")


def build():
    n = nbf.v4.new_notebook()
    n.cells = [nbf.v4.new_markdown_cell(c[1]) if c[0] == "md" else nbf.v4.new_code_cell(c[1]) for c in cells]
    n.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
    nbf.write(n, Path("notebooks") / "08-eda-completa-vacinacao-sarampo.ipynb")
    print("ok")


if __name__ == "__main__":
    build()
