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
