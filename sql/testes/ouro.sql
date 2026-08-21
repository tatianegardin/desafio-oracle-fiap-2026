-- ============================================================
-- TESTES CAMADA OURO — SELECTs de conferência
-- ============================================================
-- Rodar no Database Actions ou no APEX (SQL Commands) depois de
-- executar etl/pipeline/ouro_transform.py e analytics/kmeans.py.
--
-- As mesmas consultas rodam automaticamente ao final do
-- ouro_transform.py; este arquivo permite conferir a camada sem
-- montar o ambiente Python.
--
-- Valores de referência apurados em 20/ago/2026 — se o pipeline
-- for reexecutado sobre uma base diferente, reapurar.
-- ============================================================


-- ==================== INTEGRIDADE ====================

-- 1. Duplicidade: linhas devem ser iguais a hospitais distintos
--    em TODAS as competências. Se alguma linha voltar, há hospital
--    duplicado — foi o caso do CNES 2084139 (dois nomes para o
--    mesmo código em SLV_OCUPACAO), corrigido com MAX(nome).
SELECT competencia,
       COUNT(*)                  AS linhas,
       COUNT(DISTINCT co_cnes)   AS hospitais
  FROM gld_ocupacao_mensal
 GROUP BY competencia
HAVING COUNT(*) > COUNT(DISTINCT co_cnes)
 ORDER BY competencia;
-- Esperado: nenhuma linha.


-- 2. Uma linha por hospital na view de features
SELECT co_cnes, COUNT(*) AS linhas
  FROM gld_features_hospital
 GROUP BY co_cnes
HAVING COUNT(*) > 1;
-- Esperado: nenhuma linha.


-- 3. Cobertura das coordenadas (mapa)
SELECT COUNT(*)                        AS hospitais,
       COUNT(latitude)                 AS com_coordenada,
       COUNT(*) - COUNT(latitude)      AS sem_coordenada
  FROM gld_features_hospital
 WHERE atuacao_sus_residual = 0;
-- Esperado: sem_coordenada = 0.


-- ==================== VOLUMETRIA ====================

-- 4. Universo: total, ativos e residuais
SELECT COUNT(*)                                                   AS total,
       COUNT(CASE WHEN atuacao_sus_residual = 0 THEN 1 END)       AS ativos,
       COUNT(CASE WHEN atuacao_sus_residual = 1 THEN 1 END)       AS residuais
  FROM gld_features_hospital;
-- Referência: 83 · 78 · 5.


-- 5. Quem são os residuais e por quê
SELECT nome_estabelecimento, total_aihs, meses_com_dado
  FROM gld_features_hospital
 WHERE atuacao_sus_residual = 1
 ORDER BY total_aihs;
-- Referência: 5 hospitais, de 1 a 257 AIHs em 17 competências.


-- ==================== SEMÁFORO E KPIs ====================

-- 6. Semáforo na última competência
SELECT semaforo, COUNT(DISTINCT co_cnes) AS hospitais
  FROM gld_ocupacao_mensal
 WHERE competencia = (SELECT MAX(competencia) FROM gld_ocupacao_mensal)
 GROUP BY semaforo
 ORDER BY DECODE(semaforo, 'CRITICO', 1, 'ATENCAO', 2, 'OK', 3, 'RESIDUAL', 4);
-- Referência (05/2026): 18 · 17 · 42 · 3.


-- 7. KPIs da rede por competência
SELECT competencia_label, hospitais_total, hospitais_ativos, hospitais_residuais,
       leitos_sus, internacoes, ocupacao_rede, ocupacao_media_simples,
       criticos, atencao, ok
  FROM gld_kpi_rede
 ORDER BY competencia;
-- Esperado: 17 linhas, de 202501 a 202605.


-- 8. Top 10 do ranking na última competência
SELECT ranking_no_mes, nome_estabelecimento, taxa_ocupacao,
       var_vs_mes_anterior, media_movel_3m
  FROM gld_ocupacao_mensal
 WHERE competencia = (SELECT MAX(competencia) FROM gld_ocupacao_mensal)
   AND ranking_no_mes IS NOT NULL
 ORDER BY ranking_no_mes
 FETCH FIRST 10 ROWS ONLY;


-- ==================== CLUSTER E FATORES ====================

-- 9. Tamanho e ocupação média de cada perfil
SELECT cluster_nome,
       COUNT(*)                     AS hospitais,
       ROUND(AVG(taxa_media), 1)    AS ocupacao_media
  FROM gld_fatores_hospital
 GROUP BY cluster_nome
 ORDER BY hospitais DESC;
-- Referência: Gerais/urgência 48 · Pequenos especializados 14 ·
--             Grandes/ensino 8 · Longa permanência 8.


-- 10. Validação externa do cluster contra atividade de ensino
--     Campo do CNES que NÃO entrou nas features do modelo.
SELECT c.cluster_nome,
       COUNT(*)                                 AS hospitais,
       SUM(f.tem_atividade_ensino)              AS com_ensino,
       ROUND(100 * AVG(f.tem_atividade_ensino)) AS pct_com_ensino
  FROM gld_features_hospital f
  JOIN gld_cluster c ON c.co_cnes = f.co_cnes
 WHERE c.cluster_id IS NOT NULL
 GROUP BY c.cluster_nome
 ORDER BY pct_com_ensino DESC;
-- Referência: Grandes/ensino em 100%.


-- 11. Distribuição do fator dominante entre os críticos históricos
SELECT fator_dominante, COUNT(*) AS hospitais
  FROM gld_fatores_hospital
 WHERE taxa_media > 85
 GROUP BY fator_dominante
 ORDER BY hospitais DESC;
-- Referência: Volume 9 · Multifatorial 4 · Permanência 2 ·
--             Gravidade 2 · Complexidade 1 · Sem pressão 1.


-- 12. Hospitais críticos com fator, evidência e posição no grupo
SELECT nome_estabelecimento, cluster_nome,
       taxa_media, taxa_cluster, dif_taxa_pp,
       rank_no_cluster || '/' || n_cluster AS posicao,
       fator_dominante, evidencia, z_fator
  FROM gld_fatores_hospital
 WHERE taxa_media > 85
 ORDER BY taxa_media DESC;
-- Referência: 19 hospitais.


-- ==================== TERRITÓRIO E SAZONALIDADE ====================

-- 13. Ocupação por zona na última competência
SELECT zona,
       SUM(hospitais)                                            AS hospitais,
       SUM(criticos)                                             AS criticos,
       ROUND(100 * SUM(paciente_dia) / NULLIF(SUM(leito_dia), 0), 1) AS ocupacao
  FROM gld_regional
 WHERE competencia = (SELECT MAX(competencia) FROM gld_regional)
 GROUP BY zona
 ORDER BY ocupacao DESC;
-- Referência: Extremo Leste 80,7% · Centro 52,3%.


-- 14. O padrão regional se repete na série?
SELECT zona,
       ROUND(MIN(100 * paciente_dia / NULLIF(leito_dia, 0)), 1) AS ocupacao_min,
       ROUND(MAX(100 * paciente_dia / NULLIF(leito_dia, 0)), 1) AS ocupacao_max
  FROM (SELECT competencia, zona,
               SUM(paciente_dia) AS paciente_dia,
               SUM(leito_dia)    AS leito_dia
          FROM gld_regional
         GROUP BY competencia, zona)
 GROUP BY zona
 ORDER BY ocupacao_max DESC;
-- Esperado: as faixas das zonas não se cruzam — a desigualdade
-- territorial é estrutural, não sazonal.


-- 15. Sazonalidade por estação
SELECT estacao,
       COUNT(*)                                   AS meses,
       ROUND(AVG(ocupacao_rede), 1)               AS ocupacao_media,
       ROUND(AVG(desvio_vs_media_periodo), 1)     AS desvio_medio_pp
  FROM gld_sazonalidade
 GROUP BY estacao
 ORDER BY desvio_medio_pp DESC;
-- Referência: Inverno +1,3 p.p. · Verão −1,0 p.p. O efeito é fraco
-- e o período cobre um único inverno — não sustenta afirmação de
-- padrão sazonal.


-- ==================== PERFIL CLÍNICO ====================

-- 16. O que mais interna crianças e idosos
SELECT faixa_etaria, ds_cid, internacoes, perm_media, tx_mortalidade
  FROM (SELECT d.*,
               ROW_NUMBER() OVER (PARTITION BY faixa_etaria
                                  ORDER BY internacoes DESC) rn
          FROM gld_diagnosticos d
         WHERE faixa_etaria IN ('Crianca (1 a 11)', 'Idoso (60 ou mais)'))
 WHERE rn <= 5
 ORDER BY faixa_etaria, internacoes DESC;