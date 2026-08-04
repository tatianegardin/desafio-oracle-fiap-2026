# HOSPCHECK SP — Painel Inteligente de Ocupação Hospitalar (São Paulo Capital)

FIAP · Oracle Challenge 2026 · Turma 1TSCOA
Felipe Costas Meneses · Luís Alberto Alarcão Magalhães · Marco Antônio Andrade de Paula · Tatiane Lacerda Gardin

## O problema

O CNES sabe quantos leitos existem; o SIH sabe quantos pacientes os ocuparam e por quanto tempo. Nenhum sistema aberto cruza os dois. Este projeto calcula a **taxa de ocupação real** dos ~100 hospitais SUS ativos da capital paulista:

```
taxa de ocupação = paciente-dia ÷ leito-dia
paciente-dia = Dias_Perm (SIH/TabNet) · leito-dia = leitos SUS (CNES) × dias do mês
```

Referência ANS: operação saudável entre 75–85%; acima disso aumentam eventos adversos.

## Arquitetura (pipeline Oracle Cloud Always Free)

```
DATASUS/TabNet → OCI Object Storage → ADB 26ai (Bronze → Prata → Ouro)
                  (staging, dado cru)    ├─ APEX (painel M1)
                                         ├─ K-Means via Colab (M2)
                                         └─ Select AI (M3)
```

- **Bronze**: dado cru, 1:1 com os arquivos originais (`sql/01`, `sql/02`)
- **Prata**: tratativa 100% em SQL — UNPIVOT, limpeza, recorte SP capital, cálculo da taxa (`sql/03`)
- **Ouro**: métricas de negócio para APEX/Select AI (em construção)

## Estrutura do repositório

```
sql/              scripts na ordem de execução (00 credencial → 04 validação)
etl/
  fontes.md       onde e como baixar cada fonte de dados
  conversao/      conversores .dbc (DATASUS) → .csv
dados/
  leitos/         CNES — leitos por estabelecimento (arquivos originais)
  tabnet/         TabNet SMS-SP — dias de permanência (arquivo original)
  sihsus/         RDSP convertidos (não versionados — ver LEIA-ME da pasta)
analytics/        notebooks do K-Means (em construção)
```

## Como reproduzir

1. Provisionar ADB 26ai Always Free + bucket `hospcheck-staging` no OCI
2. Subir os arquivos de `dados/` no bucket sem alterá-los (fontes em `etl/fontes.md`)
3. Executar os scripts de `sql/` na ordem: `00_credencial` (preencher usuário OCI + Auth Token — nunca commitar preenchido) → `01_bronze_ddl` → `02_bronze_load` → `03_prata_views` → `04_validacao`
4. Conferir os resultados esperados comentados no `04_validacao.sql`

## Status (jul/2026)

- [x] ADB provisionado + wallet validado
- [x] Camada Bronze: tabelas criadas e dados carregados via DBMS_CLOUD
- [ ] Camada Prata (views de tratativa — script pronto em sql/03)
- [ ] Camada Ouro (views de negócio, features do K-Means)
- [ ] Dashboard APEX (M1) · K-Means (M2) · Select AI (M3)
