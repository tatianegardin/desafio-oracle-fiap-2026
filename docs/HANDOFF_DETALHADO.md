# HOSPCHECK SP — Handoff (04/ago/2026)

Contexto completo do projeto para quem entra agora (humano ou IA).
Reflete o que está **de fato** neste repositório e no banco.

---

## 1. O projeto

**Oracle Challenge FIAP 2026 · Turma 1TSCOA.** Felipe Costas Meneses (RM568983),
Marco Antônio Andrade de Paula (RM570169), Luís Alberto Alarcão Magalhães (RM572481),
Tatiane Lacerda Gardin (RM568830).

**Problema:** o CNES sabe quantos leitos existem; o SIH sabe quantos pacientes os ocuparam e por
quantos dias. Nenhum sistema público cruza os dois — gestores decidem alocação sem saber quais
hospitais operam no limite.

**MVP:** painel sobre Oracle ADB 23ai cruzando CNES × SIH para os ~100 hospitais SUS ativos de
SP capital, em 3 módulos:
- **M1** Painel de Ocupação (APEX): taxa real, semáforo, ranking, tendência
- **M2** Benchmarking e Fatores de Pressão (K-Means): clusters + fator dominante de saturação
- **M3** Perguntas em português: NL → SQL sobre a camada Ouro

**A métrica:**
```
taxa_ocupacao = paciente_dia / leito_dia
paciente_dia  = SUM(DIAS_PERM)            (SIH)
leito_dia     = LEITOS_SUS × dias_do_mês  (CNES)
Semáforo (ref. ANS): <70% OK · 70–85% ATENCAO · >85% CRITICO
```

**Âncoras do pitch:** 172 hospitais cadastrados / ~102 ativos (gap 40%) · 15.487 leitos SUS ·
63,4 mil internações/mês. Nosso cruzamento: 84 hospitais casados, 83 com taxa calculável.

**Entrega ~28/ago.** Board: `github.com/users/tatianegardin/projects/4`.
Épicos: E1 Banco · E2 ETL · E3 Analytics · E4 APEX · E5 Select AI · E6 Entrega.

---

## 2. Decisão de arquitetura

```
CSVs originais → OCI Object Storage → ADB 23ai: Bronze → Prata → Ouro → APEX / K-Means / M3
```

- **ELT, não ETL**: o dado é transformado dentro do banco. Python orquestra, SQL executa.
- **Bronze**: 1:1 com o arquivo original, tudo texto, sem tratamento (auditabilidade).
- **Prata**: recorte SP capital, tipos, domínios decodificados. **Materializada como TABELAS**
  (decisão de 04/ago — antes eram views; migrado para tabelas por performance).
- **Ouro**: métricas de negócio (views) consumidas por APEX, K-Means e M3.
- Python só onde SQL não alcança: conversão `.dbc`→`.csv`, orquestração, K-Means, chamadas REST de IA.

---

## 3. Fontes de dados

Detalhes, links e formatos em **`etl/fontes.md`**. Resumo:

| Dado | Fonte | Papel |
|---|---|---|
| Dias de permanência | TabNet SMS-SP (tabulação por hospital × mês) | paciente-dia (numerador) |
| Leitos SUS | dadosabertos.saude.gov.br → "Hospitais e Leitos" | leito-dia (denominador) |
| Microdados SIH-RD | DATASUS Transferência de Arquivos (Tipo **RD**, UF SP) | features do K-Means, perfil clínico |
| CID-10 | www2.datasus.gov.br/cid10/V2008/download.htm | traduzir código → doença |

Carregado: TabNet out/24–mai/26 · Leitos 2025 + jan–jun/26 · RDSP jan–mar/25 e jan–mai/26 · CID-10 completo.

---

## 4. Infraestrutura OCI

- **Tenancy** fiaptgardin (root) · **Região** Brazil East / `sa-saopaulo-1`
- **ADB principal:** `hospcheck` (23ai Always Free) — schema dono de tudo: **ADMIN**
- **ADB secundário:** `hospcheck2` — criado só para isolar o bug do Select AI; descartável
- **Bucket:** `hospcheck-staging` · namespace `gr2bf1uzkrub`
  Alguns objetos têm o prefixo "hospcheck" colado no nome (`hospcheckLeitos_2026.csv`,
  `hospcheckA201312192_29_138_8.csv`) — as URIs nos scripts refletem isso
- **Credencial banco→bucket:** `OBJ_STORE_CRED` (usuário OCI + Auth Token)
- **IAM:** usuários dos colegas no Identity Domain (ex.: MARCO) + grupo `hospcheck-team` + policies
- **Wallet:** em `etl/pipeline/wallet/` — **ignorado pelo git**, cada um baixa o seu

---

## 5. Objetos no banco (schema ADMIN)

### Bronze — tabelas, dado cru
| Objeto | Fonte | Volume | Notas |
|---|---|---|---|
| `BRZ_SIH_TABNET_RAW` | TabNet | ~104 linhas | 1 coluna por mês (`m_202410`…`m_202605`) + total, tudo VARCHAR2 |
| `BRZ_CNES_LEITOS_RAW` | Leitos 25+26 | ~129 mil | 35 colunas, Brasil inteiro |
| `BRZ_SIH_RD_RAW` | RDSP | ~230 mil/mês | 114 colunas, todas VARCHAR2, estado inteiro |
| `BRZ_CID_SUBCATEGORIAS_RAW` | CID-10 | 12.451 | código de 4 caracteres + descrição |
| `BRZ_CID_CAPITULOS_RAW` | CID-10 | 22 | faixas `catinic`–`catfim` |

### Prata — **tabelas** (criadas por `etl/pipeline/prata_transform.py`)
| Objeto | Grão | Conteúdo |
|---|---|---|
| `SLV_SIH_DIASPERM` | hospital × mês | UNPIVOT do TabNet: `co_cnes` (LPAD 7), `competencia` (YYYYMM), `dias_perm`. Descarta linha 'Total' e valores `-` |
| `SLV_CNES_LEITOS` | estab × mês | Recorte `co_ibge='355030'`: leitos_sus, uti_*, tipo de unidade, natureza jurídica |
| `SLV_INTERNACAO` | 1 linha por AIH (capital) | RD padronizado: valores/dias NUMBER, datas DATE, `idade_anos` normalizada (cod_idade 2=dias, 3=meses, 4=anos), `fl_obito`, `complexidade` MEDIA/ALTA, `carater_internacao` ELETIVO/URGENCIA, `cid_principal` |
| `SLV_OCUPACAO` | hospital × mês | `paciente_dia`, `leito_dia` (leitos × dias do mês via LAST_DAY), `taxa_ocupacao` |
| `DIM_CID` | 1 linha por código | código → descrição → capítulo (JOIN por faixa `SUBSTR(subcat,1,3) BETWEEN catinic AND catfim`) |

Todas com índice em `(co_cnes, competencia)` onde aplicável.
Recriação: rodar `prata_transform.py` (faz DROP + CTAS). Views antigas removidas por `sql/drop_slv_views_teste.sql`.

### Ouro — views (criadas por `etl/pipeline/ouro_transform.py`)
| Objeto | Grão | Conteúdo |
|---|---|---|
| `GLD_OCUPACAO_MENSAL` | hospital × mês | taxa + `semaforo` + `var_vs_mes_anterior` (LAG) + `media_movel_3m` (AVG OVER 2 PRECEDING) + `ranking_no_mes` (RANK) |
| `GLD_FEATURES_HOSPITAL` | 1 linha por hospital | matriz do K-Means: porte, leitos UTI, taxa média/máx/desvio, permanência média, % diárias UTI, % urgência, % alta complexidade, mortalidade, idade média, total AIHs |

### A criar
`GLD_CLUSTER` (resultado do K-Means) · `GLD_FATORES_HOSPITAL` (#38) · função `ASK_AI` (#31) ·
`PKG_TRANSFORM` (#17) · opcional: `GLD_PERFIL_CLINICO` (faixa etária × capítulo CID)

### Números de sanidade (conferir após qualquer mudança)
- `SLV_SIH_DIASPERM` = 1.696 linhas · hospitais cruzados em 202601 ≈ 84
- Top ocupação mai/26: **IPq-HCFMUSP ~160%** (leitos subdeclarados no CNES — achado conhecido,
  não "corrigir" na marra), Waldomiro de Paula ~100%, Campo Limpo ~99%
- Distribuição jan–mai/26: 2 hospitais >100% · ~20 críticos · ~14 atenção · ~47 OK
- RDSP 2601: 237.622 AIHs no estado / 59.860 na capital
- Prova real RD × TabNet (soma de `dias_perm` por competência): diferenças de poucos % são normais

---

## 6. Este repositório

```
README.md               visão geral  (⚠️ seção "Como reproduzir"/"Status" desatualizada — ver §9)
.gitignore              bloqueia: dados/sihsus/*, *.dbc, *.zip, wallet*, *.pem, .env, __pycache__
sql/
  00_credencial.sql     DBMS_CLOUD.CREATE_CREDENTIAL (placeholders — nunca commitar preenchido)
  01_bronze_ddl.sql     CREATE TABLE das tabelas Bronze
  02_bronze_load.sql    COPY_DATA (TabNet skipheaders=4 · leitos skipheaders=1 · WE8MSWIN1252 · ';')
  08_prata_testes.sql   SELECTs de conferência da Prata (rodar no DBeaver)
  90_grants.sql         GRANT SELECT para os usuários do grupo
  drop_slv_views_teste.sql   remove as views antigas da Prata antes de recriar como tabelas
etl/
  fontes.md             de onde vem cada dado, com links e formato
  conversao/            dbc_to_csv.py e dbc_to_csv_batch.py (.dbc DATASUS → .csv)
  pipeline/
    db.py               conexão única com o ADB via wallet · get_connection() e read_df()
    prata_transform.py  Bronze → Prata (4 tabelas + índices)
    ouro_transform.py   Prata → Ouro (2 views) + validações
    .env.example        modelo das variáveis (o .env real não é versionado)
    requirements.txt    oracledb, pandas
    wallet/             wallet do ADB — conteúdo ignorado pelo git
dados/
  leitos/ tabnet/       arquivos originais versionados
  sihsus/               só LEIA-ME (RDSP passa de 100 MB por arquivo)
docs/
  bug-selectai-ora20404.md   cronologia do bug do Select AI (leitura obrigatória para o M3)
  HANDOFF_DETALHADO.md       este arquivo
analytics/              reservado para o notebook do K-Means
```

**Como rodar do zero:** `sql/00` → `sql/01` → `sql/02` → `etl/pipeline/prata_transform.py`
→ `etl/pipeline/ouro_transform.py` → conferir com `sql/08_prata_testes.sql` → `sql/90_grants.sql`.

**Python:** `pip install -r etl/pipeline/requirements.txt`, wallet descompactado em
`etl/pipeline/wallet/`, `.env` preenchido a partir do `.env.example`, rodar de dentro de `etl/pipeline/`.

---

## 7. M3 / Select AI — o que aconteceu e a rota adotada

**Resumo: `DBMS_CLOUD_AI` está quebrado nesta plataforma. REST direto funciona e é a rota do M3.**

O caminho oficial (perfil `DBMS_CLOUD_AI` + OCI GenAI) falha com `ORA-20404` apontando para
`https://inference.generativeai.<regiao>.oci.my$cloud_domain/...` — variável interna não substituída
pelo domínio real. Reproduzido em 2 instâncias ADB, 3 configurações e 2 provedores; com provedor
Google a chamada trava até o timeout de 5 min do gateway (aparece como "parsererror" na tela).
Não é rede nem permissão: `DBMS_CLOUD.SEND_REQUEST` para o mesmo host responde em segundos.
Cronologia completa e evidências: **`docs/bug-selectai-ora20404.md`**.

**Rota validada (spike aprovado):** chamar o LLM por REST, sem o pacote defeituoso.

```sql
resp := DBMS_CLOUD.SEND_REQUEST(
  credential_name => 'GOOGLE_CRED',   -- parâmetro obrigatório; auth real vai no header
  uri     => 'https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:generateContent',
  method  => DBMS_CLOUD.METHOD_POST,
  headers => JSON_OBJECT('Content-Type'   VALUE 'application/json',
                         'x-goog-api-key' VALUE '<CHAVE>'),
  body    => UTL_RAW.CAST_TO_RAW('{"contents":[{"parts":[{"text":"<PROMPT>"}]}]}'));
```

- Pré-requisito: ACL para `generativelanguage.googleapis.com` (`DBMS_NETWORK_ACL_ADMIN.APPEND_HOST_ACE`)
- Modelo: **`gemma-4-31b-it`** — os Gemini 2.0/2.5 retornam 429 (cota zerada no free tier).
  Sempre listar `GET /v1beta/models` antes de fixar um nome: eles mudam sem aviso
- Resposta: `candidates[0].content.parts[]` — partes com `"thought": true` são raciocínio;
  **a resposta final é a parte sem essa flag**
- Prompt validado: papel ("gerador de SQL para Oracle") + esquema da view + regras
  ("apenas o SQL, sem markdown, sem `;`") + pergunta → gerou SQL Oracle correto de primeira
  (subquery com `MAX(competencia)`, `ORDER BY`, `FETCH FIRST`)

**A fazer (#31):** função `ASK_AI(pergunta, modo)` com chave e modelo em tabela de configuração,
modos `showsql`/`runsql`, guarda aceitando apenas `SELECT`, tratamento de HTTP ≠ 200.
**A chave usada no spike precisa ser regenerada** (circulou em texto plano).

---

## 8. Frentes de trabalho

**APEX (E4 — prioridade 1).** Workspace no ADB principal → app → Página 1: KPI cards (contagem por
`semaforo` na última competência), Interactive Report do ranking com badge colorido, gráfico de
tendência (`media_movel_3m`). Consumir **apenas as views `GLD_*`**, nunca Prata/Bronze direto.
Página 2 (Benchmarking) depende do `GLD_CLUSTER`.

**K-Means (E3).** Colab → `from db import get_connection, read_df` →
`read_df("SELECT * FROM gld_features_hospital")` → tratar NULLs (nem todo hospital tem RD) →
StandardScaler (escalas muito diferentes: leitos 5–900, taxa 0–100) → elbow K=2..10 (esperado K≈4-5)
→ gravar `co_cnes` + cluster em `GLD_CLUSTER` → z-score do hospital vs média do cluster para os
fatores de pressão (#38/#39). Plano B oficial: agrupamento por porte em SQL (#23).

**Dados extras (opcional).** AIHs pagas por hospital × mês no TabNet (mesma tabulação, outro
conteúdo) → permanência média mais robusta · competências RDSP de abr–dez/25 · `GLD_PERFIL_CLINICO`.

**Board/entrega (E6).** Marcar concluídos: #3 #4 #5 #14 #15 #16 #18 #19 #30 · #17 parcial ·
#31 re-escopado para "função ASK_AI via REST". Diagrama ER (#6) no Data Modeler.

---

## 9. Pendências conhecidas do repositório

- **README desatualizado**: a seção "Como reproduzir" cita `sql/03_prata_views` e `sql/04_validacao`,
  que não existem mais (Prata virou Python); o "Status" ainda marca Prata e Ouro como pendentes.
- **Bronze de RD e CID sem script versionado**: as tabelas `BRZ_SIH_RD_RAW`, `BRZ_CID_*` existem no
  banco, mas o DDL/carga não está em `sql/`. Se alguém precisar recriar o ambiente do zero, hoje falta.
- **`dados/cid/`** não está no repositório (os CSVs da CID-10 estão só locais/no bucket).
- **Spikes do Select AI** não versionados: a rota que funciona está documentada na §7 deste arquivo.

---

## 10. Perguntas de negócio que o projeto responde

**Situação:** quais hospitais estão >85% agora? · quantos em cada faixa do semáforo? · estão
melhorando ou piorando? · onde há capacidade ociosa? · existe sazonalidade? · quantos hospitais
cadastrados de fato operam (gap de 40%)?

**Diagnóstico:** quem é comparável com quem? · como este hospital está frente aos pares? ·
**por que** está saturado (volume, permanência, gravidade, complexidade)? · qual a ação indicada?

**Acesso:** qualquer uma das anteriores perguntada em português por um gestor sem SQL (M3),
incluindo recortes clínicos via `DIM_CID` (o que mais interna crianças? e idosos?).

**Síntese:** *onde o dinheiro público faz mais diferença — em qual hospital, por qual motivo?*
