# HOSPCHECK SP — Painel Inteligente de Ocupação Hospitalar

**FIAP · Oracle Challenge 2026 · Turma 1TSCOA · Grupo 22**
Felipe Costas Meneses · Luís Alberto Alarcão Magalhães · Marco Antônio Andrade de Paula · Tatiane Lacerda Gardin

---

## O problema

O CNES sabe quantos leitos existem. O SIH sabe quantos pacientes os ocuparam e por quantos
dias. **Nenhum sistema público cruza os dois** — e sem esse cruzamento, gestores decidem
alocação de recursos sem saber quais hospitais operam no limite.

Este projeto calcula a taxa de ocupação real dos hospitais SUS da capital paulista a partir
de dados abertos do DATASUS:

```
taxa de ocupação = paciente-dia ÷ leito-dia

paciente-dia = dias de permanência das internações (SIH)
leito-dia    = leitos SUS × dias do mês (CNES)
```

Referência ANS: operação saudável entre 75% e 85%; acima disso aumentam eventos adversos e
infecção hospitalar.

## O que a solução entrega

| Módulo | Pergunta que responde |
|---|---|
| **M1 — Painel de Ocupação** | Quais hospitais estão no limite? Estão melhorando ou piorando? |
| **M2 — Benchmarking e Fatores** | Comparado a quem? E **por quê** este hospital está pressionado? |
| **M3 — Perguntas em português** | Qualquer pergunta acima, sem saber SQL |

O diferencial do M2: o K-Means agrupa hospitais por **perfil assistencial** e cada unidade é
comparada com os **pares do seu grupo**, não com a rede inteira. Comparar um hospital
psiquiátrico (permanência de 23 dias) com um pronto-socorro (5 dias) não produz decisão útil.

## Arquitetura

```
        FONTES                    INGESTÃO              PROCESSAMENTO            CONSUMO
┌──────────────────────┐   ┌──────────────────┐   ┌──────────────────┐   ┌──────────────┐
│ SIH-RD (relacional)  │──▶│ Object Storage   │──▶│  BRONZE  cru     │   │ APEX      M1 │
│ Leitos, TabNet, CID  │   │ + COPY_DATA      │   │     ↓            │──▶│ K-Means   M2 │
│         (CSV)        │   │                  │   │  PRATA   tipado  │   │ Pergunte  M3 │
├──────────────────────┤   ├──────────────────┤   │     ↓            │   │ à IA         │
│ CNES API   (JSON)    │──▶│ Python + urllib  │──▶│  OURO    negócio │   └──────────────┘
└──────────────────────┘   └──────────────────┘   └──────────────────┘
                                       Oracle Autonomous AI Database 26ai
```

**Camadas**

- **Bronze** — dado como veio da fonte, 1:1, sem tratamento. Auditabilidade: dá para provar
  que o número do painel vem do arquivo original do DATASUS.
- **Prata** — recorte da capital, conversão de tipos, domínios decodificados, parse do JSON,
  chaves e relacionamentos declarados.
- **Ouro** — 8 views com métricas de negócio: ocupação com semáforo, features do modelo,
  fatores de pressão, perfil clínico, sazonalidade e território.

**Decisão de arquitetura: ELT, não ETL.** A transformação acontece **dentro do banco** —
Python orquestra, SQL executa, o dado não viaja. Python é usado onde SQL não alcança:
conversão `.dbc`→`.csv`, consumo da API e K-Means.

**Tecnologias:** Oracle Autonomous AI Database 26ai (Always Free) · OCI Object Storage ·
Oracle APEX · PL/SQL e SQL analítico (window functions, `UNPIVOT`, `JSON_VALUE`) ·
Python (`oracledb`, `pandas`, `scikit-learn`, `matplotlib`) · LLM via REST para o M3.

## Estrutura do repositório

```
sql/
  setup/          credencial DBMS_CLOUD, grants e ACL do provedor de IA
  bronze/         DDL e carga dos CSVs (COPY_DATA)
  ia/             spike e pacote PKG_ASK_AI (M3)
  testes/         consultas de conferência
etl/
  fontes.md       de onde vem cada dado, com links e formato
  conversao/      conversores .dbc (DATASUS) → .csv
  pipeline/       orquestração Python: API, Prata, Ouro
analytics/
  kmeans.py       modelo de agrupamento → GLD_CLUSTER
  METODOLOGIA.md  features, escolha do K, método do fator dominante
dados/            arquivos originais (sihsus não versionado, ver LEIA-ME)
docs/             handoff, diagrama ER e registro de decisões
```

## Como reproduzir

**Pré-requisitos:** ADB 26ai Always Free provisionado, bucket `hospcheck-staging` criado,
wallet baixado, Python 3.10+.

**1. Baixar os dados** (fontes e links em `etl/fontes.md`) e subir no bucket sem alterá-los.
Os `.dbc` do SIH precisam ser convertidos antes:

```bash
pip install -r etl/conversao/requirements.txt
python etl/conversao/dbc_to_csv_batch.py
```

**2. Carregar a Bronze dos CSVs** — no Database Actions, como ADMIN, na ordem:

```
sql/setup/01_credencial.sql      (preencher usuário OCI + Auth Token)
sql/bronze/01_ddl_tabnet_leitos.sql
sql/bronze/02_load_tabnet_leitos.sql
sql/bronze/03_ddl_load_sih_rd.sql
sql/bronze/04_ddl_load_cid.sql
```

**3. Rodar o pipeline** — um comando monta o resto do banco:

```bash
cd etl/pipeline
pip install -r requirements.txt
cp .env.example .env             # preencher as senhas
unzip wallet.zip -d wallet/      # wallet do ADB

python run_pipeline.py
```

Executa, na ordem: ingestão da API do CNES (JSON) → Prata → Ouro → K-Means.
Cada etapa imprime validações ao final.

**4. Liberar o acesso do APEX e habilitar o M3:**

```
sql/setup/02_grants.sql      (acesso do APEX às views Ouro)
sql/setup/03_acl_llm.sql     (ACL de rede + credencial do provedor de IA)
sql/ia/02_ask_ai.sql         (pacote PKG_ASK_AI — preencher a chave em CFG_AI)
```

> **O passo 4 precisa rodar sempre depois do pipeline, não só na primeira vez.**
> `GRANT` não é herdado: objeto recriado perde os acessos anteriores. O
> `kmeans.py` faz `DROP TABLE gld_cluster` antes de gravar, então a tabela nasce
> sem grant e sem sinônimo a cada execução do modelo — e as telas de Benchmarking
> e Fatores de Pressão param com `ORA-00942`, junto com as perguntas do M3 sobre
> perfil assistencial.

## Decisões documentadas

| Assunto | Onde |
|---|---|
| Features do modelo, escolha do K, método do fator dominante | `analytics/METODOLOGIA.md` |
| Critério de "atuação SUS residual" (corte de 300 internações) | `etl/pipeline/README.md` |
| Bug de plataforma no Select AI e rota adotada | `docs/bug-selectai-ora20404.md` |
| Estado do projeto, convenções e armadilhas conhecidas | `docs/HANDOFF_DETALHADO.md` |

## Status

- [x] Bronze — 4 fontes carregadas (relacional, JSON e CSV)
- [x] Prata — 6 tabelas com tipos, domínios, chaves e relacionamentos
- [x] Ouro — 8 views de negócio, com comentários e annotations no dicionário
- [x] M1 — Painel de ocupação no APEX (6 páginas)
- [x] M2 — K-Means com 4 perfis + fatores de pressão
- [x] M3 — Perguntas em linguagem natural gerando SQL
- [x] Mapa dos hospitais e análise regional por zona
- [x] Bateria de validação do M3 (40 perguntas, 34 acertos) e diagrama ER

## Licença

Código sob licença MIT (ver `LICENSE`). Os dados utilizados são públicos,
provenientes do DATASUS e do Ministério da Saúde, e mantêm suas respectivas
condições de uso.