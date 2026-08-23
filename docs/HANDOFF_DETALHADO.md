# HOSPCHECK SP — Handoff (19/ago/2026)

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
63,4 mil internações/mês. Nosso cruzamento: 83 hospitais no período, 78 com atuação SUS ativa.

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
| `GLD_OCUPACAO_MENSAL` | hospital × mês | Visão Geral — taxa, semáforo, LAG, média móvel, ranking, **lat/long, zona, bairro** |
| `GLD_KPI_REDE` | competência | Visão Geral e Home — KPIs da rede |
| `GLD_FEATURES_HOSPITAL` | hospital | matriz do K-Means + atributos da API |
| `GLD_FATORES_HOSPITAL` | hospital | Benchmarking e Fatores de Pressão — z-score no cluster, fator dominante, insight, recomendação |
| `GLD_PERFIL_CLINICO` | hospital × mês × faixa etária × capítulo CID | M3 — perguntas epidemiológicas |
| `GLD_DIAGNOSTICOS` | faixa etária × CID | M3 — o que mais interna cada faixa |
| `GLD_SAZONALIDADE` | competência | análise de sazonalidade (não virou tela — efeito fraco no período) |
| `GLD_REGIONAL` | competência × zona × bairro | Distribuição Regional — ocupação por território |

`GLD_CLUSTER` (tabela) é gravada por `analytics/kmeans.py`.
`GLD_FATORES_HOSPITAL` usa `FORCE` — nasce inválida e se valida sozinha quando a
`GLD_CLUSTER` aparece.

### Números de sanidade
- 83 hospitais no período · 78 ativos · 5 com atuação SUS residual (< 300 AIHs)
- Na competência 05/2026: 80 hospitais com movimento — 18 críticos · 17 atenção
  · 42 adequados · 3 residuais
- Clusters: Gerais/urgência 48 · Pequenos especializados 14 · Longa permanência 8
  · Grandes/ensino 8
- Ocupação por zona (mai/26): Extremo Leste 80,7% · Centro 52,3%
- Sazonalidade: Inverno +1,3 p.p. · Verão −1,0 p.p. frente à média do período
- IPq-HCFMUSP com ~160%: leitos subdeclarados no CNES — achado conhecido, não corrigir
- Perfil clínico cobre ~12% menos internações que a Prata: a `GLD_DIAGNOSTICOS`
  faz join com a features, e 11 CNES têm AIH no SIH-RD sem leito cadastrado
  no CNES. Afeta mais cirurgias eletivas — fimose cai de 7.111 para 3.718 em
  crianças, invertendo a ordem do topo (asma passa a liderar)

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

**Armadilha: recriar view apaga os comentários.** O `CREATE OR REPLACE VIEW`
descarta todos os `COMMENT ON COLUMN` do objeto. Como o prompt do
`PKG_ASK_AI` é montado a partir deles, a IA para de responder
silenciosamente — a view funciona, as telas funcionam, mas o M3 passa a
devolver "pergunta fora do escopo" porque não enxerga mais o esquema.

Por isso o `ouro_transform.py` aplica os comentários depois de criar as
views, na lista `COMENTARIOS`. Quem recriar uma view manualmente precisa
reaplicar os comentários dela.

**Comentários são instrução, não só descrição.** O texto vai direto para o
prompt do modelo. Descrição melhor gera SQL melhor — mas texto que soe como
aviso ou ressalva pode alterar o comportamento. Manter objetivo e factual.

## 8. Frentes de trabalho

**APEX (E4) — concluído.** Seis páginas no workspace `WKSP_HOSPCHECK`, app 100,
consumindo apenas views `GLD_*`:

| Página | Conteúdo |
|---|---|
| 1 — Home | capa: contexto, método, KPIs da rede, limitações declaradas |
| 2 — Visão Geral | filtros, 4 KPIs, semáforo de 4 faixas, tendência com linha de crítico, ranking |
| 3 — Benchmarking por Cluster | scatter PCA dos 4 grupos, card do hospital vs pares, insight automático |
| 4 — Pergunte à IA | campo livre + `PKG_ASK_AI`, painel do SQL gerado |
| 5 — Fatores de Pressão | z-score no cluster, 9 colunas, distribuição por fator |
| 6 — Distribuição Regional | mapa dos 80 hospitais por semáforo, ocupação por zona |

**K-Means (E3) — concluído.** 4 clusters sobre 78 hospitais ativos. Método,
escolha do K e validação externa em `analytics/METODOLOGIA.md`.

**Dados extras (opcional).** AIHs pagas por hospital × mês no TabNet (mesma tabulação, outro
conteúdo) → permanência média mais robusta · competências RDSP de abr–dez/25.

---

## 9. Pendências

**Técnicas**
- Bateria de 20 perguntas do M3 (#32) — validar e contar acertos usando `LOG_ASK_AI`
- Diagrama ER (#6) — Data Modeler sobre as tabelas; as FKs já estão declaradas
- `sql/testes/` cobre só a Prata; não há arquivo de conferência da Ouro
- Instituto Suel Abujamra tem 2 meses de dado em 17 e não é marcado como residual
  (a régua olha só `total_aihs`, não `meses_com_dado`) — limitação conhecida

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
