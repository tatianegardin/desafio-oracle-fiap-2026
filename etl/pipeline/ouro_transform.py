"""
HOSPCHECK SP — Camada OURO (métricas de negócio)
Cria as views consumidas pelo APEX (M1), K-Means (M2) e Select AI (M3):

  GLD_OCUPACAO_MENSAL    taxa por hospital x mês + semáforo + tendência
  GLD_FEATURES_HOSPITAL  1 linha por hospital: features para o K-Means
  GLD_KPI_REDE           indicadores da rede por competência (KPIs da Tela 1)
  GLD_PERFIL_CLINICO     internações por hospital, faixa etária e capítulo da CID
  GLD_DIAGNOSTICOS       diagnósticos mais frequentes por faixa etária
  GLD_FATORES_HOSPITAL   hospital x média do cluster, fator dominante e insight
                         (Telas 2 e 4 — depende da GLD_CLUSTER, criada por analytics/kmeans.py)

Views (não tabelas): sempre refletem a Prata atual, sem recarga.
Uso: set -a; source .env; set +a && python ouro_transform.py
"""

import pandas as pd

from db import get_connection

# REGRA "ATUACAO SUS RESIDUAL" (definida em GLD_FEATURES_HOSPITAL, herdada
# pelas demais views por JOIN — não duplicar o número 300 em outro lugar).
#
# Corte: total_aihs < 300 no recorte de 17 meses (jan/2025-mai/2026).
# Evidências que sustentam o corte (não é arbitrário):
#   1. Salto de ~3x na distribuição: o 5o colocado tem 257 AIHs, o 6o tem
#      800 — depois disso a distribuição sobe suave, sem outro salto.
#   2. Descontinuidade de presença: os 5 hospitais abaixo do salto têm
#      1, 5, 8, 10 e 16 meses com dado (de 17 possíveis); a partir do
#      salto, praticamente todos têm os 17 meses completos. Ou seja,
#      não são hospitais pequenos e estáveis — são hospitais com
#      atuação intermitente/marginal na rede SUS no período.
# Efeito prático: com poucas dezenas de AIHs, percentuais (urgência,
# complexidade, UTI) viram artefato de amostra pequena — ex.: Hospital
# do Coração (1 AIH) e Hospital Japonês Santa Cruz (38 AIHs em 10
# meses, "97% de urgência"). Esses hospitais continuam visíveis no
# painel (flag ATUACAO_SUS_RESIDUAL=1), mas saem do ranking, do
# cálculo de médias da rede e da matriz do K-Means.
VIEWS = [
    ("GLD_FEATURES_HOSPITAL", """
CREATE OR REPLACE VIEW gld_features_hospital AS
WITH ocup AS (
  SELECT co_cnes,
         ROUND(AVG(taxa_ocupacao), 1)    AS taxa_media,
         ROUND(MAX(taxa_ocupacao), 1)    AS taxa_max,
         ROUND(STDDEV(taxa_ocupacao), 1) AS taxa_desvio,
         COUNT(*)                        AS meses_com_dado
    FROM slv_ocupacao
   GROUP BY co_cnes
),
clin AS (
  SELECT co_cnes,
         ROUND(AVG(dias_perm), 1)                                    AS perm_media,
         ROUND(100 * SUM(diarias_uti) / NULLIF(SUM(dias_perm),0), 1) AS pct_diarias_uti,
         ROUND(100 * AVG(CASE WHEN carater_internacao = 'URGENCIA'
                              THEN 1 ELSE 0 END), 1)                 AS pct_urgencia,
         ROUND(100 * AVG(CASE WHEN complexidade = 'ALTA'
                              THEN 1 ELSE 0 END), 1)                 AS pct_alta_complex,
         ROUND(100 * AVG(fl_obito), 2)                               AS tx_mortalidade,
         ROUND(AVG(idade_anos), 1)                                   AS idade_media,
         COUNT(*)                                                    AS total_aihs,
         -- proxy de densidade tecnologica: quanto custa a internacao media.
         -- e a evidencia do fator "Complexidade" na Tela 4.
         ROUND(SUM(val_total) / NULLIF(COUNT(*),0))                  AS val_medio_aih
    FROM slv_internacao
   GROUP BY co_cnes
),
cap AS (
  SELECT cnes,
         ROUND(AVG(leitos_sus))    AS leitos_sus,
         ROUND(AVG(uti_total_sus)) AS leitos_uti_sus,
         MAX(ds_tipo_unidade)      AS tipo_unidade
    FROM slv_cnes_leitos
   GROUP BY cnes
)
SELECT o.co_cnes,
       h.nome_estabelecimento,
       cap.tipo_unidade,
       cap.leitos_sus,
       cap.leitos_uti_sus,
       o.taxa_media, o.taxa_max, o.taxa_desvio, o.meses_com_dado,
       c.perm_media, c.pct_diarias_uti, c.pct_urgencia,
       c.pct_alta_complex, c.tx_mortalidade, c.idade_media, c.total_aihs,
       c.val_medio_aih,
       CASE WHEN NVL(c.total_aihs, 0) < 300 THEN 1 ELSE 0 END AS atuacao_sus_residual
  FROM ocup o
  -- GROUP BY co_cnes (e nao DISTINCT co_cnes, nome): o CNES 2084139 aparece
  -- com dois nomes em competencias diferentes ("HOSPITAL MUNICIPAL DR BENEDITO
  -- MONTENEGRO" e "HOSP MUN J IVA BENEDITO MONTENEGRO" — renomeacao no CNES).
  -- Com DISTINCT o par (cnes, nome) devolvia 2 linhas e duplicava o hospital
  -- em todas as views a jusante. MAX escolhe um nome de forma deterministica.
  JOIN (SELECT co_cnes, MAX(nome_estabelecimento) AS nome_estabelecimento
          FROM slv_ocupacao
         GROUP BY co_cnes) h
    ON h.co_cnes = o.co_cnes
  LEFT JOIN clin c   ON c.co_cnes = o.co_cnes
  LEFT JOIN cap      ON cap.cnes  = o.co_cnes"""),

    ("GLD_OCUPACAO_MENSAL", """
CREATE OR REPLACE VIEW gld_ocupacao_mensal AS
SELECT o.co_cnes,
       o.nome_estabelecimento,
       o.ds_tipo_unidade,
       o.competencia,
       o.paciente_dia,
       o.leito_dia,
       o.taxa_ocupacao,
       NVL(f.atuacao_sus_residual, 1) AS atuacao_sus_residual,
       CASE
         WHEN NVL(f.atuacao_sus_residual, 1) = 1 THEN 'RESIDUAL'
         WHEN o.taxa_ocupacao > 85 THEN 'CRITICO'
         WHEN o.taxa_ocupacao >= 70 THEN 'ATENCAO'
         ELSE 'OK'
       END AS semaforo,
       ROUND(o.taxa_ocupacao
             - LAG(o.taxa_ocupacao)
                 OVER (PARTITION BY o.co_cnes ORDER BY o.competencia), 1)
         AS var_vs_mes_anterior,
       ROUND(AVG(o.taxa_ocupacao)
               OVER (PARTITION BY o.co_cnes ORDER BY o.competencia
                     ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 1)
         AS media_movel_3m,
       -- ranking só entre hospitais de atuacao SUS ativa (residual fica sem rank)
       CASE WHEN NVL(f.atuacao_sus_residual, 1) = 0 THEN
         RANK() OVER (PARTITION BY o.competencia, NVL(f.atuacao_sus_residual, 1)
                      ORDER BY o.taxa_ocupacao DESC)
       END AS ranking_no_mes
  FROM slv_ocupacao o
  LEFT JOIN gld_features_hospital f ON f.co_cnes = o.co_cnes"""),

    ("GLD_KPI_REDE", """
CREATE OR REPLACE VIEW gld_kpi_rede AS
WITH universo AS (
  SELECT DISTINCT competencia, co_cnes, atuacao_sus_residual
    FROM gld_ocupacao_mensal
),
leitos AS (
  SELECT c.competencia, SUM(c.leitos_sus) AS leitos_sus
    FROM slv_cnes_leitos c
    JOIN universo u
      ON u.competencia = c.competencia
     AND u.co_cnes     = c.cnes
   WHERE u.atuacao_sus_residual = 0
   GROUP BY c.competencia
),
internacoes AS (
  SELECT i.competencia, COUNT(*) AS internacoes
    FROM slv_internacao i
    JOIN universo u
      ON u.competencia = i.competencia
     AND u.co_cnes     = i.co_cnes
   WHERE u.atuacao_sus_residual = 0
   GROUP BY i.competencia
)
SELECT o.competencia,
       TO_CHAR(TO_DATE(o.competencia,'YYYYMM'),'fmMon/YYYY')              AS competencia_label,
       COUNT(*)                                                           AS hospitais_total,
       COUNT(CASE WHEN o.atuacao_sus_residual = 0 THEN 1 END)             AS hospitais_ativos,
       COUNT(CASE WHEN o.atuacao_sus_residual = 1 THEN 1 END)             AS hospitais_residuais,
       COUNT(CASE WHEN o.semaforo = 'CRITICO' THEN 1 END)                 AS criticos,
       COUNT(CASE WHEN o.semaforo = 'ATENCAO' THEN 1 END)                 AS atencao,
       COUNT(CASE WHEN o.semaforo = 'OK'      THEN 1 END)                 AS ok,
       ROUND(100 * SUM(CASE WHEN o.atuacao_sus_residual = 0 THEN o.paciente_dia END)
                 / NULLIF(SUM(CASE WHEN o.atuacao_sus_residual = 0 THEN o.leito_dia END), 0), 1)
         AS ocupacao_rede,
       ROUND(AVG(CASE WHEN o.atuacao_sus_residual = 0 THEN o.taxa_ocupacao END), 1)
         AS ocupacao_media_simples,
       l.leitos_sus,
       i.internacoes
  FROM gld_ocupacao_mensal o
  LEFT JOIN leitos      l ON l.competencia = o.competencia
  LEFT JOIN internacoes i ON i.competencia = o.competencia
 GROUP BY o.competencia, l.leitos_sus, i.internacoes"""),

    ("GLD_FATORES_HOSPITAL", """
CREATE OR REPLACE FORCE VIEW gld_fatores_hospital AS
WITH base AS (
  SELECT f.co_cnes,
         f.nome_estabelecimento,
         f.tipo_unidade,
         f.leitos_sus,
         c.cluster_id,
         c.cluster_nome,
         c.pca_x,
         c.pca_y,
         c.dist_centroide,
         f.taxa_media,
         f.total_aihs,
         f.perm_media,
         f.tx_mortalidade,
         f.val_medio_aih
    FROM gld_features_hospital f
    JOIN gld_cluster c ON c.co_cnes = f.co_cnes
   WHERE f.atuacao_sus_residual = 0
     AND c.cluster_id IS NOT NULL
),
comp AS (
  SELECT b.*,
         -- media do grupo (o "hospital medio" do cluster)
         ROUND(AVG(taxa_media)     OVER (PARTITION BY cluster_id), 1) AS taxa_cluster,
         ROUND(AVG(total_aihs)     OVER (PARTITION BY cluster_id))    AS aihs_cluster,
         ROUND(AVG(perm_media)     OVER (PARTITION BY cluster_id), 1) AS perm_cluster,
         ROUND(AVG(tx_mortalidade) OVER (PARTITION BY cluster_id), 2) AS mort_cluster,
         ROUND(AVG(val_medio_aih)  OVER (PARTITION BY cluster_id))    AS val_aih_cluster,
         COUNT(*)                  OVER (PARTITION BY cluster_id)     AS n_cluster,
         RANK() OVER (PARTITION BY cluster_id ORDER BY taxa_media DESC) AS rank_no_cluster,
         -- z-score: quantos desvios-padrao o hospital esta acima dos pares
         (total_aihs     - AVG(total_aihs)     OVER (PARTITION BY cluster_id))
           / NULLIF(STDDEV(total_aihs)     OVER (PARTITION BY cluster_id), 0) AS z_volume,
         (perm_media     - AVG(perm_media)     OVER (PARTITION BY cluster_id))
           / NULLIF(STDDEV(perm_media)     OVER (PARTITION BY cluster_id), 0) AS z_permanencia,
         (tx_mortalidade - AVG(tx_mortalidade) OVER (PARTITION BY cluster_id))
           / NULLIF(STDDEV(tx_mortalidade) OVER (PARTITION BY cluster_id), 0) AS z_gravidade,
         (val_medio_aih  - AVG(val_medio_aih)  OVER (PARTITION BY cluster_id))
           / NULLIF(STDDEV(val_medio_aih)  OVER (PARTITION BY cluster_id), 0) AS z_complexidade
    FROM base b
),
fator AS (
  SELECT comp.*,
         GREATEST(NVL(z_volume,-99), NVL(z_permanencia,-99),
                  NVL(z_gravidade,-99), NVL(z_complexidade,-99)) AS z_max
    FROM comp
)
SELECT co_cnes, nome_estabelecimento, tipo_unidade, leitos_sus,
       cluster_id, cluster_nome, n_cluster, pca_x, pca_y, dist_centroide,
       -- desempenho do hospital x pares
       taxa_media, taxa_cluster,
       ROUND(taxa_media - taxa_cluster, 1) AS dif_taxa_pp,
       rank_no_cluster,
       total_aihs,    aihs_cluster,
       perm_media,    perm_cluster,
       tx_mortalidade, mort_cluster,
       val_medio_aih, val_aih_cluster,
       ROUND(z_volume, 2)       AS z_volume,
       ROUND(z_permanencia, 2)  AS z_permanencia,
       ROUND(z_gravidade, 2)    AS z_gravidade,
       ROUND(z_complexidade, 2) AS z_complexidade,
       ROUND(z_max, 2)          AS z_fator,
       -- corte em z < 1: abaixo disso nenhuma dimensao se destaca o
       -- suficiente dos pares — a pressao e distribuida (Multifatorial).
       -- hospital com ocupacao abaixo da media do grupo nao esta sob
       -- pressao: falar em "fator dominante" nesse caso confunde. O que
       -- interessa ali e a folga (capacidade ociosa), nao a causa.
       CASE
         WHEN taxa_media < taxa_cluster       THEN 'SEM PRESSAO'
         WHEN z_max <= 0                      THEN 'SEM PRESSAO'
         WHEN z_max < 1                       THEN 'MULTIFATORIAL'
         WHEN z_max = NVL(z_permanencia,-99)  THEN 'PERMANENCIA'
         WHEN z_max = NVL(z_gravidade,-99)    THEN 'GRAVIDADE'
         WHEN z_max = NVL(z_complexidade,-99) THEN 'COMPLEXIDADE'
         ELSE 'VOLUME'
       END AS fator_dominante,
       -- evidencia exibida ao lado do badge (Tela 4)
       CASE
         WHEN taxa_media < taxa_cluster       THEN TO_CHAR(ABS(ROUND(taxa_media - taxa_cluster,1)), 'FM990D0')
                                                   || ' p.p. abaixo dos pares'
         WHEN z_max <= 0                      THEN 'sem desvio frente aos pares'
         WHEN z_max = NVL(z_permanencia,-99)  THEN TO_CHAR(perm_media, 'FM990D0') || ' dias'
         WHEN z_max = NVL(z_gravidade,-99)    THEN 'mort. ' || TO_CHAR(tx_mortalidade, 'FM990D00') || '%'
         WHEN z_max = NVL(z_complexidade,-99) THEN 'AIH R$ ' || TO_CHAR(val_medio_aih, 'FM999G999')
         ELSE TO_CHAR(total_aihs, 'FM999G999') || ' intern.'
       END
       || CASE WHEN z_max > 0 AND z_max < 1 THEN ' (tendência)' ELSE '' END AS evidencia,
       -- frase pronta para o card (Telas 2 e 4)
       CASE
         WHEN taxa_media < taxa_cluster THEN
              'Ocupacao abaixo dos pares do grupo — ha folga de capacidade'
         WHEN z_max <= 0 THEN 'Abaixo da media dos pares em todas as dimensoes'
         WHEN z_max < 1  THEN 'Pressao distribuida — nenhuma dimensao se destaca frente aos pares'
         WHEN z_max = NVL(z_permanencia,-99) THEN
              'Permanência ' || TO_CHAR(ROUND(100*(perm_media - perm_cluster)
                 / NULLIF(perm_cluster,0))) || '% acima do grupo — gargalo na gestão de altas'
         WHEN z_max = NVL(z_gravidade,-99) THEN
              'Mortalidade ' || TO_CHAR(ROUND(100*(tx_mortalidade - mort_cluster)
                 / NULLIF(mort_cluster,0))) || '% acima do grupo — perfil de maior gravidade'
         WHEN z_max = NVL(z_complexidade,-99) THEN
              'Custo médio por internação ' || TO_CHAR(ROUND(100*(val_medio_aih - val_aih_cluster)
                 / NULLIF(val_aih_cluster,0))) || '% acima do grupo — alta densidade tecnológica'
         ELSE 'Volume de internações ' || TO_CHAR(ROUND(100*(total_aihs - aihs_cluster)
                 / NULLIF(aihs_cluster,0))) || '% acima do grupo — pressão de porta de entrada'
       END AS insight,
       -- recomendacao de gestao (quadro "Traducao para a gestao")
       CASE
         WHEN taxa_media < taxa_cluster       THEN 'Capacidade ociosa — candidato a receber demanda pela regulacao'
         WHEN z_max <= 0                      THEN 'Sem sinal de pressao assistencial'
         WHEN z_max < 1                       THEN 'Pressao distribuida, sem causa isolada — monitorar'
         WHEN z_max = NVL(z_permanencia,-99)  THEN 'Revisar processo de alta e retaguarda'
         WHEN z_max = NVL(z_gravidade,-99)    THEN 'Avaliar papel de referência regional'
         WHEN z_max = NVL(z_complexidade,-99) THEN 'Avaliar custo e densidade tecnológica'
         ELSE 'Reforçar porta de entrada ou redistribuir demanda'
       END AS recomendacao
  FROM fator"""),

    ("GLD_PERFIL_CLINICO", """
CREATE OR REPLACE FORCE VIEW gld_perfil_clinico AS
SELECT i.competencia,
       i.co_cnes,
       f.nome_estabelecimento,
       f.tipo_unidade,
       CASE
         WHEN i.idade_anos <  1  THEN 'Menor de 1 ano'
         WHEN i.idade_anos < 12  THEN 'Crianca (1 a 11)'
         WHEN i.idade_anos < 18  THEN 'Adolescente (12 a 17)'
         WHEN i.idade_anos < 60  THEN 'Adulto (18 a 59)'
         WHEN i.idade_anos IS NOT NULL THEN 'Idoso (60 ou mais)'
       END                                        AS faixa_etaria,
       d.nr_capitulo,
       NVL(d.ds_capitulo, 'Capitulo nao identificado') AS ds_capitulo,
       COUNT(*)                                   AS internacoes,
       ROUND(AVG(i.dias_perm), 1)                 AS perm_media,
       SUM(i.dias_perm)                           AS paciente_dia,
       SUM(i.fl_obito)                            AS obitos,
       ROUND(100 * AVG(i.fl_obito), 2)            AS tx_mortalidade,
       ROUND(SUM(i.val_total))                    AS valor_total,
       ROUND(AVG(i.idade_anos), 1)                AS idade_media
  FROM slv_internacao i
  JOIN gld_features_hospital f
    ON f.co_cnes = i.co_cnes
   AND f.atuacao_sus_residual = 0
  LEFT JOIN dim_cid d
    ON d.co_cid = i.cid_principal
 GROUP BY i.competencia, i.co_cnes, f.nome_estabelecimento, f.tipo_unidade,
          CASE
            WHEN i.idade_anos <  1  THEN 'Menor de 1 ano'
            WHEN i.idade_anos < 12  THEN 'Crianca (1 a 11)'
            WHEN i.idade_anos < 18  THEN 'Adolescente (12 a 17)'
            WHEN i.idade_anos < 60  THEN 'Adulto (18 a 59)'
            WHEN i.idade_anos IS NOT NULL THEN 'Idoso (60 ou mais)'
          END,
          d.nr_capitulo, d.ds_capitulo"""),

    ("GLD_DIAGNOSTICOS", """
CREATE OR REPLACE FORCE VIEW gld_diagnosticos AS
SELECT CASE
         WHEN i.idade_anos <  1  THEN 'Menor de 1 ano'
         WHEN i.idade_anos < 12  THEN 'Crianca (1 a 11)'
         WHEN i.idade_anos < 18  THEN 'Adolescente (12 a 17)'
         WHEN i.idade_anos < 60  THEN 'Adulto (18 a 59)'
         WHEN i.idade_anos IS NOT NULL THEN 'Idoso (60 ou mais)'
       END                                        AS faixa_etaria,
       i.cid_principal                            AS co_cid,
       NVL(d.ds_cid_abrev, 'Nao identificado')    AS ds_cid,
       NVL(d.ds_capitulo, 'Capitulo nao identificado') AS ds_capitulo,
       COUNT(*)                                   AS internacoes,
       ROUND(AVG(i.dias_perm), 1)                 AS perm_media,
       SUM(i.fl_obito)                            AS obitos,
       ROUND(100 * AVG(i.fl_obito), 2)            AS tx_mortalidade,
       ROUND(AVG(i.idade_anos), 1)                AS idade_media,
       COUNT(DISTINCT i.co_cnes)                  AS hospitais
  FROM slv_internacao i
  JOIN gld_features_hospital f
    ON f.co_cnes = i.co_cnes
   AND f.atuacao_sus_residual = 0
  LEFT JOIN dim_cid d
    ON d.co_cid = i.cid_principal
 GROUP BY CASE
            WHEN i.idade_anos <  1  THEN 'Menor de 1 ano'
            WHEN i.idade_anos < 12  THEN 'Crianca (1 a 11)'
            WHEN i.idade_anos < 18  THEN 'Adolescente (12 a 17)'
            WHEN i.idade_anos < 60  THEN 'Adulto (18 a 59)'
            WHEN i.idade_anos IS NOT NULL THEN 'Idoso (60 ou mais)'
          END,
          i.cid_principal, d.ds_cid_abrev, d.ds_capitulo"""),
]

# Comentarios do dicionario: alem de documentar, sao lidos pelo
# PKG_ASK_AI para montar o prompt do modelo (M3). Descricao boa aqui
# = SQL melhor gerado. Reaplicados a cada execucao porque CREATE OR
# REPLACE VIEW pode descarta-los.
# ANNOTATIONS (Oracle 23ai/26ai) — metadados estruturados em pares
# chave-valor, complementares ao COMMENT ON (que e texto livre).
# Consultaveis em USER_ANNOTATIONS_USAGE. Documentam camada, fonte,
# grao e a qual modulo do produto cada view serve.
ANOTACOES = [
    """ALTER VIEW gld_perfil_clinico ANNOTATIONS (ADD OR REPLACE
         Camada 'Ouro', Grao 'hospital x competencia x faixa etaria x capitulo CID',
         Fonte 'SLV_INTERNACAO + DIM_CID', Modulo 'M3 - Perguntas em linguagem natural')""",

    """ALTER VIEW gld_diagnosticos ANNOTATIONS (ADD OR REPLACE
         Camada 'Ouro', Grao 'faixa etaria x codigo CID',
         Fonte 'SLV_INTERNACAO + DIM_CID', Modulo 'M3 - Perguntas em linguagem natural')""",
    """ALTER VIEW gld_ocupacao_mensal ANNOTATIONS (ADD OR REPLACE
         Camada 'Ouro', Grao 'hospital x competencia',
         Fonte 'SIH/TabNet + CNES', Modulo 'M1 - Painel de Ocupacao',
         Metrica 'paciente-dia / leito-dia')""",

    """ALTER VIEW gld_kpi_rede ANNOTATIONS (ADD OR REPLACE
         Camada 'Ouro', Grao 'competencia',
         Fonte 'GLD_OCUPACAO_MENSAL + Prata', Modulo 'M1 - Painel de Ocupacao',
         Uso 'KPIs da tela de visao geral')""",

    """ALTER VIEW gld_features_hospital ANNOTATIONS (ADD OR REPLACE
         Camada 'Ouro', Grao 'hospital',
         Fonte 'SIH/RD + CNES', Modulo 'M2 - Benchmarking',
         Uso 'matriz de entrada do K-Means')""",

    """ALTER VIEW gld_fatores_hospital ANNOTATIONS (ADD OR REPLACE
         Camada 'Ouro', Grao 'hospital',
         Fonte 'GLD_FEATURES_HOSPITAL + GLD_CLUSTER',
         Modulo 'M2 - Fatores de Pressao',
         Metodo 'z-score dentro do cluster, piso de relevancia 1 desvio')""",
]

COMENTARIOS = [
    "COMMENT ON TABLE gld_perfil_clinico IS 'Perfil epidemiologico das internacoes: quantas internacoes, permanencia e mortalidade por hospital, competencia, faixa etaria e capitulo da CID-10. Grao: hospital x mes x faixa etaria x capitulo'",
    "COMMENT ON COLUMN gld_perfil_clinico.faixa_etaria IS 'Faixa etaria do paciente: Menor de 1 ano, Crianca (1 a 11), Adolescente (12 a 17), Adulto (18 a 59) ou Idoso (60 ou mais)'",
    "COMMENT ON COLUMN gld_perfil_clinico.ds_capitulo IS 'Capitulo da CID-10, agrupa diagnosticos por sistema ou natureza da doenca. Ex.: doencas do aparelho respiratorio, neoplasias, gravidez e parto'",
    "COMMENT ON COLUMN gld_perfil_clinico.internacoes IS 'Quantidade de internacoes no recorte'",
    "COMMENT ON COLUMN gld_perfil_clinico.paciente_dia IS 'Soma dos dias de permanencia no recorte'",
    "COMMENT ON COLUMN gld_perfil_clinico.valor_total IS 'Valor total faturado no recorte, em reais'",

    "COMMENT ON TABLE gld_diagnosticos IS 'Diagnosticos mais frequentes por faixa etaria em toda a rede e todo o periodo. Responde o que mais interna criancas, idosos e demais faixas. Grao: faixa etaria x codigo CID'",
    "COMMENT ON COLUMN gld_diagnosticos.co_cid IS 'Codigo CID-10 do diagnostico principal'",
    "COMMENT ON COLUMN gld_diagnosticos.ds_cid IS 'Nome do diagnostico. Use esta coluna para exibir a doenca, nao o codigo'",
    "COMMENT ON COLUMN gld_diagnosticos.hospitais IS 'Quantos hospitais distintos registraram esse diagnostico'",
    "COMMENT ON COLUMN gld_features_hospital.atuacao_sus_residual IS 'Sinalizador 1 para hospitais com menos de 300 internacoes no periodo, excluidos das analises e do modelo'",
    "COMMENT ON COLUMN gld_fatores_hospital.z_volume IS 'Desvios-padrao do volume de internacoes frente aos pares do grupo. Positivo indica volume acima dos semelhantes'",
    "COMMENT ON COLUMN gld_fatores_hospital.z_permanencia IS 'Desvios-padrao da permanencia media frente aos pares do grupo'",
    "COMMENT ON COLUMN gld_fatores_hospital.z_gravidade IS 'Desvios-padrao da mortalidade frente aos pares do grupo'",
    "COMMENT ON COLUMN gld_fatores_hospital.z_complexidade IS 'Desvios-padrao do valor medio por internacao frente aos pares do grupo'",
    # Identificadores e nomes: sem comentario a coluna fica invisivel para o
    # PKG_ASK_AI (que monta o prompt so com colunas comentadas) — e o modelo
    # acaba devolvendo codigo em vez de nome.
    "COMMENT ON COLUMN gld_ocupacao_mensal.nome_estabelecimento IS 'Nome do hospital. Use esta coluna para identificar o hospital nos resultados, nao o codigo CNES'",
    "COMMENT ON COLUMN gld_ocupacao_mensal.ds_tipo_unidade IS 'Tipo da unidade: hospital geral, hospital especializado, pronto socorro e outros'",
    "COMMENT ON COLUMN gld_features_hospital.co_cnes IS 'Codigo CNES do estabelecimento, 7 digitos. Chave de ligacao entre as views'",
    "COMMENT ON COLUMN gld_features_hospital.nome_estabelecimento IS 'Nome do hospital. Use esta coluna para identificar o hospital nos resultados, nao o codigo CNES'",
    "COMMENT ON COLUMN gld_features_hospital.tipo_unidade IS 'Tipo da unidade segundo o CNES'",
    "COMMENT ON COLUMN gld_features_hospital.leitos_uti_sus IS 'Leitos de UTI disponibilizados ao SUS'",
    "COMMENT ON COLUMN gld_features_hospital.taxa_max IS 'Maior ocupacao mensal observada no periodo'",
    "COMMENT ON COLUMN gld_features_hospital.taxa_desvio IS 'Desvio-padrao da ocupacao entre os meses: mede oscilacao'",
    "COMMENT ON COLUMN gld_features_hospital.meses_com_dado IS 'Quantidade de competencias com movimento registrado'",
    "COMMENT ON COLUMN gld_kpi_rede.competencia IS 'Competencia no formato AAAAMM'",
    "COMMENT ON COLUMN gld_kpi_rede.hospitais_total IS 'Total de hospitais no mes, incluindo os de atuacao residual'",
    "COMMENT ON COLUMN gld_kpi_rede.hospitais_residuais IS 'Hospitais com atuacao SUS marginal, excluidos das analises'",
    "COMMENT ON COLUMN gld_kpi_rede.atencao IS 'Hospitais com ocupacao entre 70 e 85 por cento'",
    "COMMENT ON COLUMN gld_kpi_rede.ok IS 'Hospitais com ocupacao abaixo de 70 por cento'",
    "COMMENT ON COLUMN gld_kpi_rede.ocupacao_media_simples IS 'Media aritmetica das taxas dos hospitais, sem ponderar por porte'",
    "COMMENT ON COLUMN gld_fatores_hospital.co_cnes IS 'Codigo CNES do estabelecimento, 7 digitos'",
    "COMMENT ON COLUMN gld_fatores_hospital.nome_estabelecimento IS 'Nome do hospital. Use esta coluna para identificar o hospital nos resultados, nao o codigo CNES'",
    "COMMENT ON COLUMN gld_fatores_hospital.tipo_unidade IS 'Tipo da unidade segundo o CNES'",
    "COMMENT ON COLUMN gld_fatores_hospital.leitos_sus IS 'Leitos SUS do hospital'",
    "COMMENT ON COLUMN gld_fatores_hospital.taxa_media IS 'Ocupacao media do hospital no periodo completo'",
    "COMMENT ON COLUMN gld_fatores_hospital.perm_media IS 'Permanencia media do hospital, em dias'",
    "COMMENT ON COLUMN gld_fatores_hospital.perm_cluster IS 'Permanencia media dos hospitais do mesmo perfil'",
    "COMMENT ON COLUMN gld_fatores_hospital.total_aihs IS 'Total de internacoes do hospital no periodo'",
    "COMMENT ON COLUMN gld_fatores_hospital.aihs_cluster IS 'Media de internacoes dos hospitais do mesmo perfil'",
    "COMMENT ON COLUMN gld_fatores_hospital.tx_mortalidade IS 'Percentual de internacoes com obito no hospital'",
    "COMMENT ON COLUMN gld_fatores_hospital.mort_cluster IS 'Mortalidade media dos hospitais do mesmo perfil'",
    "COMMENT ON COLUMN gld_fatores_hospital.val_medio_aih IS 'Valor medio faturado por internacao, em reais'",
    "COMMENT ON COLUMN gld_fatores_hospital.val_aih_cluster IS 'Valor medio por internacao dos hospitais do mesmo perfil'",
    "COMMENT ON COLUMN gld_fatores_hospital.cluster_id IS 'Identificador numerico do perfil, use cluster_nome para exibir'",
    "COMMENT ON COLUMN gld_fatores_hospital.dist_centroide IS 'Distancia ao centro do proprio grupo: quanto menor, mais tipico do perfil'",
    "COMMENT ON TABLE gld_ocupacao_mensal IS 'Taxa de ocupacao por hospital e competencia mensal, com semaforo, tendencia e ranking. Grao: um hospital por mes'",
    "COMMENT ON COLUMN gld_ocupacao_mensal.co_cnes IS 'Codigo CNES do estabelecimento, 7 digitos'",
    "COMMENT ON COLUMN gld_ocupacao_mensal.competencia IS 'Competencia no formato texto AAAAMM, de 202501 a 202605'",
    "COMMENT ON COLUMN gld_ocupacao_mensal.paciente_dia IS 'Soma dos dias de permanencia das internacoes no mes'",
    "COMMENT ON COLUMN gld_ocupacao_mensal.leito_dia IS 'Leitos SUS multiplicados pelos dias do mes: capacidade instalada'",
    "COMMENT ON COLUMN gld_ocupacao_mensal.taxa_ocupacao IS 'Percentual de ocupacao: paciente_dia dividido por leito_dia. Acima de 100 indica leitos subdeclarados no CNES'",
    "COMMENT ON COLUMN gld_ocupacao_mensal.semaforo IS 'Classificacao: CRITICO acima de 85 por cento, ATENCAO entre 70 e 85, OK abaixo de 70, RESIDUAL para hospitais de atuacao SUS marginal'",
    "COMMENT ON COLUMN gld_ocupacao_mensal.var_vs_mes_anterior IS 'Variacao da taxa em pontos percentuais frente ao mes anterior'",
    "COMMENT ON COLUMN gld_ocupacao_mensal.media_movel_3m IS 'Media movel da taxa nos ultimos 3 meses, suaviza oscilacoes pontuais'",
    "COMMENT ON COLUMN gld_ocupacao_mensal.ranking_no_mes IS 'Posicao do hospital na competencia, 1 e a maior ocupacao. Nulo para atuacao residual'",
    "COMMENT ON COLUMN gld_ocupacao_mensal.atuacao_sus_residual IS 'Sinalizador 1 para hospitais com menos de 300 internacoes no periodo, excluidos das analises'",

    "COMMENT ON TABLE gld_kpi_rede IS 'Indicadores consolidados da rede hospitalar por competencia. Grao: uma competencia'",
    "COMMENT ON COLUMN gld_kpi_rede.competencia_label IS 'Competencia formatada para exibicao, exemplo Mai/2026'",
    "COMMENT ON COLUMN gld_kpi_rede.hospitais_ativos IS 'Quantidade de hospitais com atuacao SUS efetiva no mes'",
    "COMMENT ON COLUMN gld_kpi_rede.leitos_sus IS 'Total de leitos SUS dos hospitais ativos'",
    "COMMENT ON COLUMN gld_kpi_rede.internacoes IS 'Numero de internacoes (AIH) no mes. Nulo em competencias sem microdado carregado'",
    "COMMENT ON COLUMN gld_kpi_rede.ocupacao_rede IS 'Ocupacao da rede ponderada pelo porte: soma de paciente_dia dividida pela soma de leito_dia'",
    "COMMENT ON COLUMN gld_kpi_rede.criticos IS 'Hospitais com ocupacao acima de 85 por cento no mes'",

    "COMMENT ON TABLE gld_features_hospital IS 'Perfil consolidado de cada hospital no periodo completo, usado como entrada do modelo de agrupamento. Grao: um hospital'",
    "COMMENT ON COLUMN gld_features_hospital.leitos_sus IS 'Leitos SUS disponiveis, indicador de porte'",
    "COMMENT ON COLUMN gld_features_hospital.taxa_media IS 'Ocupacao media do hospital nas 17 competencias'",
    "COMMENT ON COLUMN gld_features_hospital.perm_media IS 'Tempo medio de permanencia por internacao, em dias'",
    "COMMENT ON COLUMN gld_features_hospital.pct_urgencia IS 'Percentual de internacoes de urgencia sobre o total, o restante e eletivo'",
    "COMMENT ON COLUMN gld_features_hospital.pct_alta_complex IS 'Percentual de internacoes de alta complexidade'",
    "COMMENT ON COLUMN gld_features_hospital.pct_diarias_uti IS 'Percentual de diarias em UTI sobre o total de dias de internacao'",
    "COMMENT ON COLUMN gld_features_hospital.tx_mortalidade IS 'Percentual de internacoes com obito'",
    "COMMENT ON COLUMN gld_features_hospital.idade_media IS 'Idade media dos pacientes internados, em anos'",
    "COMMENT ON COLUMN gld_features_hospital.total_aihs IS 'Total de internacoes no periodo'",
    "COMMENT ON COLUMN gld_features_hospital.val_medio_aih IS 'Valor medio faturado por internacao em reais, proxy de densidade tecnologica'",

    "COMMENT ON TABLE gld_fatores_hospital IS 'Compara cada hospital com a media dos pares do seu grupo e identifica o fator que explica a pressao assistencial. Grao: um hospital'",
    "COMMENT ON COLUMN gld_fatores_hospital.cluster_nome IS 'Perfil assistencial do hospital: Grandes / ensino, Gerais / urgencia, Pequenos especializados ou Longa permanencia'",
    "COMMENT ON COLUMN gld_fatores_hospital.n_cluster IS 'Quantidade de hospitais no mesmo perfil'",
    "COMMENT ON COLUMN gld_fatores_hospital.taxa_cluster IS 'Ocupacao media dos hospitais do mesmo perfil'",
    "COMMENT ON COLUMN gld_fatores_hospital.dif_taxa_pp IS 'Diferenca em pontos percentuais entre a ocupacao do hospital e a media do seu perfil'",
    "COMMENT ON COLUMN gld_fatores_hospital.rank_no_cluster IS 'Posicao do hospital dentro do proprio perfil, 1 e a maior ocupacao'",
    "COMMENT ON COLUMN gld_fatores_hospital.fator_dominante IS 'Causa provavel da pressao: VOLUME, PERMANENCIA, GRAVIDADE, COMPLEXIDADE, MULTIFATORIAL quando nenhuma se destaca, ou SEM PRESSAO quando o hospital esta abaixo dos pares em tudo'",
    "COMMENT ON COLUMN gld_fatores_hospital.z_fator IS 'Quantos desvios-padrao o hospital esta acima da media do seu perfil na dimensao dominante'",
    "COMMENT ON COLUMN gld_fatores_hospital.evidencia IS 'Valor observado da dimensao dominante, formatado para exibicao'",
    "COMMENT ON COLUMN gld_fatores_hospital.insight IS 'Leitura em linguagem natural do desvio encontrado'",
    "COMMENT ON COLUMN gld_fatores_hospital.recomendacao IS 'Direcao de investigacao sugerida ao gestor, nao e prescricao clinica'",
    "COMMENT ON COLUMN gld_fatores_hospital.pca_x IS 'Coordenada horizontal da projecao bidimensional usada no grafico de dispersao'",
    "COMMENT ON COLUMN gld_fatores_hospital.pca_y IS 'Coordenada vertical da projecao bidimensional usada no grafico de dispersao'",
]

VALIDACOES = [
    ("Semáforo na última competência", """
SELECT semaforo, COUNT(*) hospitais
  FROM gld_ocupacao_mensal
 WHERE competencia = (SELECT MAX(competencia) FROM gld_ocupacao_mensal)
 GROUP BY semaforo ORDER BY semaforo"""),

    ("Top 10 críticos (última competência)", """
SELECT ranking_no_mes, nome_estabelecimento, taxa_ocupacao,
       var_vs_mes_anterior, media_movel_3m
  FROM gld_ocupacao_mensal
 WHERE competencia = (SELECT MAX(competencia) FROM gld_ocupacao_mensal)
   AND ranking_no_mes IS NOT NULL
 ORDER BY ranking_no_mes
 FETCH FIRST 10 ROWS ONLY"""),

    ("Hospitais com atuação SUS residual (fora do ranking/cluster)", """
SELECT nome_estabelecimento, total_aihs, meses_com_dado
  FROM gld_features_hospital
 WHERE atuacao_sus_residual = 1
 ORDER BY total_aihs"""),

    ("Features do K-Means (amostra, só ativos)", """
SELECT co_cnes, nome_estabelecimento, leitos_sus, taxa_media,
       perm_media, pct_urgencia, pct_alta_complex
  FROM gld_features_hospital
 WHERE atuacao_sus_residual = 0
 ORDER BY taxa_media DESC
 FETCH FIRST 5 ROWS ONLY"""),

    ("KPIs da rede por competência", """
SELECT competencia_label, hospitais_total, hospitais_ativos, hospitais_residuais,
       leitos_sus, internacoes, ocupacao_rede, criticos, atencao, ok
  FROM gld_kpi_rede
 ORDER BY competencia"""),

    ("O que mais interna criancas e idosos", """
SELECT faixa_etaria, ds_cid, internacoes, perm_media, tx_mortalidade
  FROM (SELECT d.*, ROW_NUMBER() OVER (PARTITION BY faixa_etaria
                                       ORDER BY internacoes DESC) rn
          FROM gld_diagnosticos d
         WHERE faixa_etaria IN ('Crianca (1 a 11)', 'Idoso (60 ou mais)'))
 WHERE rn <= 5
 ORDER BY faixa_etaria, internacoes DESC"""),

    ("Distribuição dos fatores de pressão", """
SELECT fator_dominante, COUNT(*) hospitais
  FROM gld_fatores_hospital
 GROUP BY fator_dominante
 ORDER BY hospitais DESC"""),

    ("Fatores — top 10 por ocupação (Telas 2 e 4)", """
SELECT nome_estabelecimento, cluster_nome,
       taxa_media, taxa_cluster, dif_taxa_pp,
       rank_no_cluster || '/' || n_cluster AS posicao,
       fator_dominante, evidencia
  FROM gld_fatores_hospital
 ORDER BY taxa_media DESC
 FETCH FIRST 10 ROWS ONLY"""),
]


def main():
    conn = get_connection()
    print(f"Conectado: {conn.version}")

    with conn.cursor() as cur:
        for nome, sql in VIEWS:
            print(f"→ criando {nome} ...", end=" ")
            cur.execute(sql)
            print("OK")

        print(f"→ aplicando {len(COMENTARIOS)} comentarios ...", end=" ")
        aplicados = 0
        for c in COMENTARIOS:
            try:
                cur.execute(c)
                aplicados += 1
            except Exception as e:
                print(f"\n   aviso: {c[:60]}... -> {e}")
        print(f"{aplicados}/{len(COMENTARIOS)} OK")

        # annotations sao recurso do 23ai/26ai; se a versao nao suportar,
        # o script segue sem elas (os comentarios ja cobrem a documentacao)
        print(f"→ aplicando {len(ANOTACOES)} annotations ...", end=" ")
        ok_anot = 0
        for a in ANOTACOES:
            try:
                cur.execute(a)
                ok_anot += 1
            except Exception as e:
                print(f"\n   aviso: {e}")
        print(f"{ok_anot}/{len(ANOTACOES)} OK")

    for nome, sql in VALIDACOES:
        print(f"\n=== {nome} ===")
        print(pd.read_sql(sql, conn).to_string(index=False))

    conn.close()


if __name__ == "__main__":
    main()
