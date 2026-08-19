# Pipeline Python — ingestão da API e camadas Prata e Ouro

Orquestra as etapas que montam o banco depois que os CSVs já estão na Bronze.
Python coordena; o SQL executa dentro do banco (o dado não viaja).

## Setup (uma vez)

1. `pip install -r requirements.txt`
2. Descompacte o wallet do ADB (Database connection → Download wallet) dentro de
   `wallet/` — os arquivos `tnsnames.ora`, `cwallet.sso` etc.
3. Copie `.env.example` para `.env` e preencha as senhas (o `.env` não vai pro Git)

## Uso

```bash
python run_pipeline.py                # tudo: api → prata → ouro → modelo
python run_pipeline.py --sem-modelo   # sem o K-Means
python run_pipeline.py --ouro         # só a camada Ouro (o caso mais comum)
python run_pipeline.py --api          # só a ingestão da API
```

Roda de qualquer diretório: `python etl/pipeline/run_pipeline.py`.
O orquestrador carrega o `.env` sozinho, cronometra cada etapa e interrompe se
alguma falhar — evitando rodar a Ouro sobre uma Prata quebrada.

## Ordem de dependência

```
CSVs (sql/bronze/) ──▶ bronze_api_cnes.py ──▶ prata_transform.py ──▶ ouro_transform.py
                                                                             ▲
                                              analytics/kmeans.py ───────────┘
                                              (GLD_CLUSTER; as views de
                                               fatores só têm dado depois dele)
```

A etapa da API depende da Bronze dos CSVs: ela percorre os CNES que já existem em
`BRZ_CNES_LEITOS_RAW` e complementa cada um — não traz estabelecimento novo.

## Arquivos

| Arquivo | Papel |
|---|---|
| `db.py` | Conexão única com o ADB via wallet — usada por todos os scripts e pelo notebook do K-Means |
| `run_pipeline.py` | Orquestrador: executa as etapas na ordem, com cronômetro e parada em erro |
| `bronze_api_cnes.py` | Busca o cadastro do CNES na API de dados abertos e grava o JSON cru em `BRZ_CNES_API_RAW` |
| `prata_transform.py` | Bronze → Prata: recorte da capital, tipos, domínios, parse do JSON, chaves e comentários |
| `ouro_transform.py` | Prata → Ouro: 8 views de negócio, comentários e annotations |

No Colab: upload do `wallet.zip`, definir `os.environ["ADB_PASSWORD"]` e
`from db import get_connection`.

## Regra de negócio: atuação SUS residual

`GLD_FEATURES_HOSPITAL.ATUACAO_SUS_RESIDUAL = 1` marca hospitais com
`total_aihs < 300` no recorte de 17 meses (jan/2025-mai/2026). Esses
hospitais saem do ranking (`GLD_OCUPACAO_MENSAL.ranking_no_mes`), das
médias da rede (`GLD_KPI_REDE`) e da matriz do K-Means — mas continuam
visíveis nas views, com a flag marcada (`semaforo = 'RESIDUAL'`).

Evidências por trás do corte (300, não é número arbitrário):

1. **Salto de ~3x na distribuição**: o 5º colocado (por `total_aihs`)
   tem 257 AIHs, o 6º tem 800 — depois disso a distribuição sobe
   suave, sem outro salto.
2. **Descontinuidade de presença**: os 5 hospitais abaixo do salto têm
   1, 5, 8, 10 e 16 meses com dado (de 17 possíveis); a partir do
   salto, praticamente todos têm os 17 meses completos. Não são
   hospitais pequenos e estáveis — são hospitais com atuação
   intermitente/marginal na rede SUS no período.

Com poucas dezenas de AIHs, percentuais (urgência, complexidade, UTI)
viram artefato de amostra pequena, não característica do hospital —
ex.: Hospital do Coração (1 AIH) e Hospital Japonês Santa Cruz (38
AIHs em 10 meses, "97% de urgência"). A régua conecta com o pitch do
projeto ("172 cadastrados, ~102 ativos"): define objetivamente o que
conta como hospital SUS ativo pra fins de benchmarking.
