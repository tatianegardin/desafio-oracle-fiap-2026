# Pipeline Python — conexão ADB + camadas Prata e Ouro

## Setup (uma vez)

1. `pip install -r requirements.txt`
2. Descompacte o conteúdo do wallet do ADB (Database connection → Download wallet)
   dentro de `pipeline/wallet/` (os arquivos tnsnames.ora, cwallet.sso etc.)
3. Copie `.env.example` para `.env` e preencha as senhas (o `.env` não vai pro Git)

## Uso (a partir desta pasta)

```bash
set -a; source .env; set +a
python prata_transform.py   # Bronze → Prata (SLV_INTERNACAO)
python ouro_transform.py    # Prata → Ouro (GLD_OCUPACAO_MENSAL, GLD_FEATURES_HOSPITAL)
```

## Arquivos

| Arquivo | Papel |
|---|---|
| `db.py` | Conexão única com o ADB via wallet (usada por todos os scripts e pelo notebook do K-Means) |
| `prata_transform.py` | Padroniza o microdado SIH-RD: recorte capital, tipos, domínios → `SLV_INTERNACAO` |
| `ouro_transform.py` | Métricas de negócio: ocupação mensal com semáforo/tendência e features por hospital pro K-Means |

No Colab: upload do wallet.zip + `os.environ["ADB_PASSWORD"]=...` e `from db import get_connection`.

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
