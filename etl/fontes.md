# Fontes de dados

| Dado | Fonte | Como obter | Papel no pipeline |
|---|---|---|---|
| Dias de permanência (paciente-dia) | TabNet SMS-SP — "Internações Hospitalares do SUS no MSP a partir de 2008" | prefeitura.sp.gov.br → Saúde → TabNet → Produção hospitalar. Linha: Estab.Saúde · Coluna: Ano/mês compet. · Conteúdo: Dias Perm · Período: Out/2024–Mai/2026 | Numerador da taxa de ocupação |
| Leitos SUS por estabelecimento | DATASUS/DEMAS — base "Hospitais e Leitos" (Leitos_2025.csv, Leitos_2026.csv) | Portal de dados abertos do Ministério da Saúde | Denominador (leito-dia = leitos × dias do mês) |
| Microdados SIH (RDSP) — opcional | DATASUS Transferência de Arquivos: Fonte=SIHSUS · Tipo=RD · UF=SP | datasus.saude.gov.br/transferencia-de-arquivos | Features do K-Means (M2): complexidade, CID, permanência por AIH |

Staging: OCI Object Storage, bucket `hospcheck-staging` (sa-saopaulo-1).
Os arquivos entram no bucket SEM manipulação — a Bronze é 1:1 com a fonte e toda tratativa é SQL (ver sql/03_prata_views.sql).
