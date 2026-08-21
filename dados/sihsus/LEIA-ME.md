# Microdados do SIH-RD — não versionados

Os arquivos originais do SIH (AIH Reduzida) não estão neste repositório: cada
competência tem mais de 100 MB em CSV, acima do limite do GitHub.

## De onde baixar

DATASUS — Transferência de Arquivos
https://datasus.saude.gov.br/transferencia-de-arquivos/

Seleção:

| Campo | Valor |
|---|---|
| Fonte | SIHSUS |
| Modalidade | Dados |
| Tipo de Arquivo | **RD** (AIH Reduzida) |
| UF | SP |
| Competências | 01/2025 a 05/2026 |

> **Atenção:** o tipo `SP` na lista significa *Serviços Profissionais*, não São
> Paulo. Só o tipo **RD** traz `DIAS_PERM`, `CNES`, `MUNIC_MOV`, CID e
> complexidade — que é o que o projeto usa.

Os arquivos vêm no formato `RDSPaamm.dbc`, onde `aa` é o ano e `mm` o mês.

## O que fazer com eles

1. Colocar os `.dbc` nesta pasta
2. Converter para CSV:

```bash
pip install -r etl/conversao/requirements.txt
python etl/conversao/dbc_to_csv_batch.py
```

3. Subir os CSVs no bucket `hospcheck-staging` do OCI Object Storage, sem
   alterá-los — a camada Bronze é 1:1 com a fonte
4. Carregar com `sql/bronze/03_ddl_load_sih_rd.sql`

## Volume esperado

Cerca de 230 mil linhas por mês no estado de São Paulo, das quais aproximadamente
60 mil são da capital (`MUNIC_MOV = 355030`). O recorte para a capital acontece
na camada Prata, não na carga.