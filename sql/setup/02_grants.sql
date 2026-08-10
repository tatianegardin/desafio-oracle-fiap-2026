-- ============================================================
-- Acessos — executar como ADMIN apos criar/recriar objetos
-- Lembre: GRANT nao e herdado. Objeto novo = GRANT novo.
-- ============================================================

-- ------------------------------------------------------------
-- 1. Membros do time (usuarios de banco, para consultas ad-hoc)
--    Cada um deve rodar no inicio da sessao:
--      ALTER SESSION SET CURRENT_SCHEMA = ADMIN;
--    ou prefixar os objetos com admin.
-- ------------------------------------------------------------
GRANT SELECT ON brz_sih_tabnet_raw    TO MARCO;
GRANT SELECT ON brz_cnes_leitos_raw   TO MARCO;
GRANT SELECT ON slv_sih_diasperm      TO MARCO;
GRANT SELECT ON slv_cnes_leitos       TO MARCO;
GRANT SELECT ON slv_internacao        TO MARCO;
GRANT SELECT ON slv_ocupacao          TO MARCO;
GRANT SELECT ON gld_ocupacao_mensal   TO MARCO;
GRANT SELECT ON gld_features_hospital TO MARCO;
GRANT SELECT ON gld_kpi_rede          TO MARCO;

-- ------------------------------------------------------------
-- 2. Workspace do APEX (schema HOSPCHECK_APP)
--    Regra de arquitetura: o app consome APENAS views GLD_*.
--    Os sinonimos permitem consultar sem prefixo de schema.
-- ------------------------------------------------------------
GRANT SELECT ON gld_ocupacao_mensal   TO hospcheck_app;
GRANT SELECT ON gld_features_hospital TO hospcheck_app;
GRANT SELECT ON gld_kpi_rede          TO hospcheck_app;

CREATE OR REPLACE SYNONYM hospcheck_app.gld_ocupacao_mensal   FOR admin.gld_ocupacao_mensal;
CREATE OR REPLACE SYNONYM hospcheck_app.gld_features_hospital FOR admin.gld_features_hospital;
CREATE OR REPLACE SYNONYM hospcheck_app.gld_kpi_rede          FOR admin.gld_kpi_rede;

-- ------------------------------------------------------------
-- 3. A criar (descomentar quando os objetos existirem)
-- ------------------------------------------------------------
-- GRANT SELECT ON gld_cluster           TO hospcheck_app;
-- GRANT SELECT ON gld_fatores_hospital  TO hospcheck_app;
-- CREATE OR REPLACE SYNONYM hospcheck_app.gld_cluster          FOR admin.gld_cluster;
-- CREATE OR REPLACE SYNONYM hospcheck_app.gld_fatores_hospital FOR admin.gld_fatores_hospital;

-- ------------------------------------------------------------
-- Conferir o que esta concedido:
--   SELECT grantee, table_name, privilege FROM user_tab_privs
--    WHERE grantee IN ('MARCO','HOSPCHECK_APP') ORDER BY grantee, table_name;
-- ------------------------------------------------------------
