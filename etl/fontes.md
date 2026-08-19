# Fontes de dados

Todas públicas e gratuitas. O desafio pede o uso de **três formatos** — relacional,
JSON e CSV — e cada fonte entra no formato que faz sentido para ela.

| # | Fonte | Formato | Papel |
|---|---|---|---|
| 1 | SIH-RD (microdados de internação) | relacional (CSV → tabela) | volume transacional: quem internou, por quanto tempo, com qual diagnóstico |
| 2 | CNES via API de dados abertos | **JSON** (semiestruturado) | cadastro do estabelecimento: geolocalização, estrutura, ensino |
| 3 | Leitos, TabNet e CID-10 | **CSV** | capacidade instalada, paciente-dia agregado e dicionário de diagnósticos |

Chave de integração em todo o projeto: o **código CNES** do estabelecimento.

Staging: OCI Object Storage, bucket `hospcheck-staging` (sa-saopaulo-1). Os arquivos
entram no bucket **sem manipulação** — a Bronze é 1:1 com a fonte e toda a tratativa
acontece nas camadas Prata e Ouro.

---

## 1. Microdados SIH-RD — internações

**Fonte:** DATASUS — Transferência de Arquivos
**Link:** https://datasus.saude.gov.br/transferencia-de-arquivos/

**Seleção:** Fonte = `SIHSUS` · Modalidade = `Dados` · Tipo de Arquivo = **`RD`** · UF = `SP` ·
competências desejadas → arquivos `RDSPaamm.dbc`.

> ⚠️ **Não confundir:** o tipo `SP` na lista significa *Serviços Profissionais*, não São Paulo.
> Só o tipo **RD** (AIH Reduzida) traz `DIAS_PERM`, `CNES`, `MUNIC_MOV`, CID e complexidade.

Converter com `etl/conversao/dbc_to_csv.py` (ou `dbc_to_csv_batch.py` para lote) → CSV UTF-8,
114 colunas, ~230 mil linhas/mês no estado e ~60 mil na capital.

Arquivos não versionados (>100 MB cada) — ver `dados/sihsus/LEIA-ME.md`.
Carga: `sql/bronze/03_ddl_load_sih_rd.sql`.

---

## 2. CNES via API — cadastro dos estabelecimentos (JSON)

**Fonte:** Ministério da Saúde — API de Dados Abertos
**Endpoint:** `https://apidadosabertos.saude.gov.br/cnes/estabelecimentos/{cnes}`
**Documentação:** https://apidadosabertos.saude.gov.br/v1/

Público, sem autenticação. Traz atributos que o arquivo CSV de leitos **não tem**:

- `latitude` e `longitude` — habilitam o mapa dos hospitais
- `estabelecimento_possui_centro_cirurgico` / `_obstetrico` / `_neonatal`
- `codigo_atividade_ensino_unidade` — valida externamente o perfil "Grandes / ensino"
  identificado pelo K-Means
- `descricao_turno_atendimento` — identifica unidades de plantão 24h
- `bairro_estabelecimento` e `codigo_cep_estabelecimento`

Ingestão: `etl/pipeline/bronze_api_cnes.py` (etapa `--api` do pipeline). O script percorre
os CNES que **já existem** na Bronze do CSV de leitos e complementa cada um — a API não
introduz estabelecimento novo. O payload é gravado como veio, em coluna JSON.

---

## 3a. Leitos SUS por estabelecimento (CSV)

**Fonte:** Ministério da Saúde / DEMAS — dataset "Hospitais e Leitos"
**Link:** https://dadosabertos.saude.gov.br/dataset/hospitais-e-leitos

Baixar os arquivos anuais (`Leitos_2025.csv`, `Leitos_2026.csv`). Trazem o Brasil inteiro,
uma linha por estabelecimento × competência mensal; o recorte de SP capital
(`CO_IBGE = '355030'`) é feito na camada Prata.

Formato: latin1, separador `;`, 35 colunas. Arquivos em `dados/leitos/`.
Carga: `sql/bronze/02_load_tabnet_leitos.sql`.

## 3b. Dias de permanência — paciente-dia (CSV)

**Fonte:** TabNet SMS-SP — "Internações Hospitalares do SUS no Município de São Paulo a partir de 2008"
**Link:** http://tabnet.saude.prefeitura.sp.gov.br/cgi/deftohtm3.exe?secretarias/saude/TABNET/AIH2008/aihnet2008.def
**Notas técnicas:** https://prefeitura.sp.gov.br/web/saude/w/tabnet/6477

**Como tabular:** Linha = `Estab.Saúde-Cidade` · Coluna = `Ano/mês de competência` ·
Conteúdo = `Dias Perm` · Período = Out/2024 – Mai/2026 · exportar em CSV.

Formato: latin1, `;`, 3 linhas de título + cabeçalho, meses em colunas, `-` = sem valor.
Arquivo em `dados/tabnet/`. Carga: `sql/bronze/02_load_tabnet_leitos.sql`.

> O mesmo formulário exporta **AIHs pagas**, óbitos e diárias de UTI — útil para
> calcular permanência média sem depender do microdado.

## 3c. CID-10 — dicionário de diagnósticos (CSV)

**Fonte:** DATASUS — Tabelas da CID-10 (arquivo `CID10CSV.ZIP`, ~300 KB)
**Link:** http://www2.datasus.gov.br/cid10/V2008/download.htm

Do ZIP usamos dois arquivos: `CID-10-SUBCATEGORIAS.CSV` (12.451 códigos + descrição, casa
direto com `cid_principal` da `SLV_INTERNACAO`) e `CID-10-CAPITULOS.CSV` (22 capítulos com
as faixas `CATINIC`–`CATFIM`, permite agrupar por "doenças respiratórias", "neoplasias" etc.).

Formato: latin1, `;`. Arquivos em `dados/cid/`.
Carga: `sql/bronze/04_ddl_load_cid.sql`.
