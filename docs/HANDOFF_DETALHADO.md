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

**MVP:** painel sobre Oracle ADB 26ai cruzando CNES × SIH para os ~100 hospitais SUS ativos de
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
CSVs originais → OCI Object Storage → ADB 26ai: Bronze → Prata → Ouro → APEX / K-Means / M3
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
| Cadastro CNES (**JSON**) | API `apidadosabertos.saude.gov.br/cnes/estabelecimentos/{cnes}` | geolocalização, estrutura, atividade de ensino |
| CID-10 | www2.datasus.gov.br/cid10/V2008/download.htm | traduzir código → doença |

Carregado: TabNet out/24–mai/26 · Leitos 2025 + jan–jun/26 · RDSP jan–mar/25 e jan–mai/26 · CID-10 completo.

---

## 4. Infraestrutura OCI

- **Tenancy** fiaptgardin (root) · **Região** Brazil East / `sa-saopaulo-1`
- **ADB principal:** `hospcheck` (26ai Always Free) — schema dono de tudo: **ADMIN**
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
| Objeto | Fonte | Formato | Volume | Notas |
|---|---|---|---|---|
| `BRZ_SIH_TABNET_RAW` | TabNet | CSV | ~104 linhas | 1 coluna por mês, tudo VARCHAR2 |
| `BRZ_CNES_LEITOS_RAW` | Leitos 25+26 | CSV | ~129 mil | 35 colunas, Brasil inteiro |
| `BRZ_SIH_RD_RAW` | RDSP | CSV | ~230 mil/mês | 114 colunas, todas VARCHAR2 |
| `BRZ_CID_SUBCATEGORIAS_RAW` | CID-10 | CSV | 12.451 | código + descrição |
| `BRZ_CID_CAPITULOS_RAW` | CID-10 | CSV | 22 | faixas `catinic`–`catfim` |
| `BRZ_CNES_API_RAW` | API dados abertos | **JSON** | ~150 | payload como veio; carregada por `bronze_api_cnes.py` |

### Prata — tabelas (criadas por `etl/pipeline/prata_transform.py`)
| Objeto | Grão | Conteúdo |
|---|---|---|
| `SLV_SIH_DIASPERM` | hospital × mês | UNPIVOT do TabNet: `co_cnes` (LPAD 7), `competencia`, `dias_perm` |
| `SLV_CNES_LEITOS` | estab × mês | recorte `co_ibge='355030'`; leitos, UTI, tipo, **bairro, CEP e zona** (derivada do prefixo do CEP) |
| `SLV_INTERNACAO` | 1 linha por AIH (capital) | tipos convertidos, `idade_anos` normalizada, `fl_obito`, complexidade, caráter, CID |
| `SLV_OCUPACAO` | hospital × mês | `paciente_dia`, `leito_dia`, `taxa_ocupacao` |
| `SLV_ESTABELECIMENTO` | 1 por estabelecimento | **parse do JSON da API**: lat/long, centro cirúrgico/obstétrico/neonatal, atividade de ensino, turno |
| `DIM_CID` | 1 por código | código → descrição → capítulo |

Chaves declaradas: 5 PKs e 4 FKs (`RELY DISABLE NOVALIDATE`) — importam para o
Select AI (relacionamentos são metadados que o modelo usa) e para o diagrama ER.
Comentários e annotations aplicados a cada execução.

### Ouro — views (criadas por `etl/pipeline/ouro_transform.py`)
| Objeto | Grão | Serve a |
|---|---|---|
| `GLD_OCUPACAO_MENSAL` | hospital × mês | Tela 1 — taxa, semáforo, LAG, média móvel, ranking, **lat/long, zona, bairro** |
| `GLD_KPI_REDE` | competência | Tela 1 — KPIs da rede |
| `GLD_FEATURES_HOSPITAL` | hospital | matriz do K-Means + atributos da API |
| `GLD_FATORES_HOSPITAL` | hospital | Telas 2 e 4 — z-score no cluster, fator dominante, insight, recomendação |
| `GLD_PERFIL_CLINICO` | hospital × mês × faixa etária × capítulo CID | M3 — perguntas epidemiológicas |
| `GLD_DIAGNOSTICOS` | faixa etária × CID | M3 — o que mais interna cada faixa |
| `GLD_SAZONALIDADE` | competência | Tela 4 — estação do ano e desvio vs. média |
| `GLD_REGIONAL` | competência × zona × bairro | Tela 4 — ocupação por território |

`GLD_CLUSTER` (tabela) é gravada por `analytics/kmeans.py`.
`GLD_FATORES_HOSPITAL` usa `FORCE` — nasce inválida e se valida sozinha quando a
`GLD_CLUSTER` aparece.

### Números de sanidade
- 84 hospitais no painel · 79 ativos · 5 com atuação SUS residual (< 300 AIHs)
- Última competência: 18 críticos · 17 atenção · 42 adequados · 3 residuais
- Clusters: Gerais/urgência 49 · Pequenos especializados 14 · Longa permanência 8 · Grandes/ensino 8
- Ocupação por zona (mai/26): Extremo Leste 80,7% · Centro 52,3%
- Sazonalidade: Inverno +1,3 p.p. · Verão −1,0 p.p. frente à média do período
- IPq-HCFMUSP com ~160%: leitos subdeclarados no CNES — achado conhecido, não corrigir

### A criar
Nada estrutural pendente. `PKG_TRANSFORM` (#17) foi descartado por decisão da
equipe: a lógica fica em Python orquestrando SQL (ELT), e isso é explicado na
apresentação.

## 6. Este repositório

```
README.md              visão geral, arquitetura e como reproduzir
.gitignore             bloqueia dados/sihsus, wallet, .env, __pycache__
sql/
  setup/               01 credencial DBMS_CLOUD · 02 grants
  bronze/              01–04: DDL e carga dos CSVs via COPY_DATA
  ia/                  01 spike REST · 02 pacote PKG_ASK_AI
  testes/              consultas de conferência da Prata
etl/
  fontes.md            de onde vem cada dado, links e formato
  conversao/           dbc_to_csv.py e dbc_to_csv_batch.py
  pipeline/
    db.py              conexão única via wallet
    run_pipeline.py    orquestrador: api → prata → ouro → modelo
    bronze_api_cnes.py ingestão da API do CNES (JSON)
    prata_transform.py Bronze → Prata
    ouro_transform.py  Prata → Ouro
analytics/
  kmeans.py            modelo → GLD_CLUSTER
  METODOLOGIA.md       features, escolha do K, validação externa, fator dominante
dados/                 originais; sihsus não versionado
docs/                  este handoff e o registro do bug do Select AI
```

**Rodar do zero:** carregar os CSVs com `sql/setup/01` + `sql/bronze/01–04`,
depois `python etl/pipeline/run_pipeline.py`, e por fim `sql/setup/02_grants.sql`.

**Execuções parciais:** `--api` · `--prata` · `--ouro` · `--modelo` · `--sem-modelo`.
Tudo idempotente.

## 7. M3 / Select AI — resolvido

**O caminho oficial (`DBMS_CLOUD_AI`) está quebrado nesta plataforma.** A
funcionalidade foi entregue chamando o modelo por REST com
`DBMS_CLOUD.SEND_REQUEST`.

Em produção hoje: pacote `PKG_ASK_AI` (`sql/ia/02_ask_ai.sql`), provedor Google
com modelo `gemma-4-31b-it`, chave e modelo em tabela de configuração `CFG_AI`,
log de todas as perguntas em `LOG_ASK_AI`, e guarda que aceita apenas `SELECT`.

O prompt é montado a partir dos **comentários do dicionário** — melhorar a
documentação de uma coluna melhora o SQL gerado, sem tocar no código.

Cronologia completa do diagnóstico, as armadilhas da integração no APEX e o que
declarar na apresentação: **`docs/bug-selectai-ora20404.md`**.

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

## 9. Pendências

**Técnicas**
- Bateria de 20 perguntas do M3 (#32) — validar e contar acertos usando `LOG_ASK_AI`
- Diagrama ER (#6) — Data Modeler sobre as tabelas; as FKs já estão declaradas
- Mapa dos hospitais no APEX — coordenadas prontas em `GLD_OCUPACAO_MENSAL`
- Sinalizar visualmente ocupação acima de 100% (caso IPq)
- `sql/testes/` cobre só a Prata; não há arquivo de conferência da Ouro

**Entrega (Sprint 2 — 01/09/2026)**
- PPTX com os tópicos do pitch · vídeo de até 5 min no YouTube
- Tornar o app APEX público (link funcionando vale 10% da nota)
- Planilha `Informacoes_Finais_Projeto_Integrantes` · documentação de gestão atualizada
- ZIP único com todos os entregáveis

## 10. Perguntas de negócio que o projeto responde

**Situação:** quais hospitais estão >85% agora? · quantos em cada faixa do semáforo? · estão
melhorando ou piorando? · onde há capacidade ociosa? · existe sazonalidade? · quantos hospitais
cadastrados de fato operam (gap de 40%)?

**Diagnóstico:** quem é comparável com quem? · como este hospital está frente aos pares? ·
**por que** está saturado (volume, permanência, gravidade, complexidade)? · qual a ação indicada?

**Acesso:** qualquer uma das anteriores perguntada em português por um gestor sem SQL (M3),
incluindo recortes clínicos via `DIM_CID` (o que mais interna crianças? e idosos?).

**Síntese:** *onde o dinheiro público faz mais diferença — em qual hospital, por qual motivo?*
