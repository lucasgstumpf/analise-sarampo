# analise-sarampo
Repositorio referente ao trabalho da disciplina Analise Visual de Dados do Mestrado UNESP

## Estrutura de dados

Os dados são organizados por domínio, cada um com seus próprios `raw/` e `processed/`:

```
data/
├── datasus_lib.py          # funções comuns de download/conversão (DATASUS), usadas pelos dois domínios
├── sarampo/                 # casos/exames de sarampo (SINAN)
│   ├── extract.py
│   ├── raw/
│   └── processed/
└── vacinacao/                # doses aplicadas de vacina (SI-PNI/RNDS)
    ├── extract_historico.py   # cobertura vacinal 1994-2019 (FTP)
    ├── extract_recentes.py    # doses individuais pós-2019, filtradas por "sarampo" (S3)
    ├── ver_primeiras_linhas.py
    ├── raw/
    └── processed/
```

Para rodar uma extração: `python data/sarampo/extract.py` ou `python data/vacinacao/extract_historico.py` (a partir da raiz do repo, com o venv ativado).
