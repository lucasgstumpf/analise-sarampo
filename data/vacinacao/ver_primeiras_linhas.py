from pathlib import Path

import pandas as pd


arquivo_csv = Path(__file__).parent / "raw" / "vacinacao_jan_2026.csv"
df = pd.read_csv(arquivo_csv, sep=";", encoding="latin1")

print(df.head(15))