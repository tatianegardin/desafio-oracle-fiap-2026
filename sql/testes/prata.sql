-- ============================================================
-- TESTES CAMADA PRATA — SELECTs de conferência (rodar no DBeaver)
-- ============================================================

-- ==================== SLV_INTERNACAO ====================

SELECT co_cnes,
       competencia,
       n_aih,
       dt_internacao,
       dt_saida,
       dias_perm,
       qt_diarias,
       diarias_uti,
       val_total,
       val_uti,
       sexo,
       idade_anos,
       fl_obito,
       cid_principal,
       complexidade,
       carater_internacao,
       procedimento
  FROM slv_internacao
 ORDER BY competencia, co_cnes
 FETCH FIRST 20 ROWS ONLY;

SELECT competencia,
       complexidade,
       COUNT(*)                    AS qtd_internacoes,
       SUM(dias_perm)              AS paciente_dia,
       ROUND(AVG(dias_perm), 1)    AS permanencia_media,
       SUM(fl_obito)               AS obitos
  FROM slv_internacao
 GROUP BY competencia, complexidade
 ORDER BY competencia, complexidade;

-- ==================== SLV_CNES_LEITOS ====================

SELECT competencia,
       cnes,
       nome_estabelecimento,
       razao_social,
       tp_gestao,
       ds_tipo_unidade,
       natureza_juridica,
       desc_natureza_juridica,
       leitos_existentes,
       leitos_sus,
       uti_total_exist,
       uti_total_sus
  FROM slv_cnes_leitos
 ORDER BY competencia, cnes
 FETCH FIRST 20 ROWS ONLY;

SELECT ds_tipo_unidade,
       COUNT(DISTINCT cnes)   AS qtd_hospitais,
       SUM(leitos_sus)        AS total_leitos_sus,
       SUM(uti_total_sus)     AS total_uti_sus
  FROM slv_cnes_leitos
 GROUP BY ds_tipo_unidade
 ORDER BY total_leitos_sus DESC;

-- ==================== SLV_SIH_DIASPERM ====================

SELECT co_cnes,
       no_estabelecimento,
       competencia,
       dias_perm
  FROM slv_sih_diasperm
 ORDER BY competencia, co_cnes
 FETCH FIRST 20 ROWS ONLY;

SELECT competencia,
       COUNT(DISTINCT co_cnes) AS qtd_hospitais,
       SUM(dias_perm)          AS total_paciente_dia,
       ROUND(AVG(dias_perm),1) AS media_por_hospital
  FROM slv_sih_diasperm
 GROUP BY competencia
 ORDER BY competencia;

-- ==================== SLV_OCUPACAO ====================

SELECT co_cnes,
       nome_estabelecimento,
       ds_tipo_unidade,
       competencia,
       paciente_dia,
       leito_dia,
       taxa_ocupacao
  FROM slv_ocupacao
 ORDER BY competencia, taxa_ocupacao DESC
 FETCH FIRST 20 ROWS ONLY;

SELECT ds_tipo_unidade,
       COUNT(*)                     AS qtd_registros,
       ROUND(AVG(taxa_ocupacao), 1) AS taxa_media,
       ROUND(MIN(taxa_ocupacao), 1) AS taxa_min,
       ROUND(MAX(taxa_ocupacao), 1) AS taxa_max
  FROM slv_ocupacao
 GROUP BY ds_tipo_unidade
 ORDER BY taxa_media DESC;
