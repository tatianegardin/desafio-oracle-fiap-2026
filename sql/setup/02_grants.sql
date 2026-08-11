-- ============================================================
-- Acessos — executar como ADMIN sempre que criar/recriar objetos
-- GRANT nao e herdado: objeto novo = GRANT novo.
-- ============================================================

-- ------------------------------------------------------------
-- 1. Membros do time (usuarios de banco, consultas ad-hoc)
--    Exemplo com MARCO — repetir para os demais usuarios do grupo.
--    Cada um roda no inicio da sessao:
--      ALTER SESSION SET CURRENT_SCHEMA = ADMIN;
--    ou prefixa os objetos com admin.
-- ------------------------------------------------------------

-- Bronze
GRANT SELECT ON brz_sih_tabnet_raw        TO MARCO;
GRANT SELECT ON brz_cnes_leitos_raw       TO MARCO;
GRANT SELECT ON brz_sih_rd_raw            TO MARCO;
GRANT SELECT ON brz_cid_subcategorias_raw TO MARCO;
GRANT SELECT ON brz_cid_capitulos_raw     TO MARCO;

-- Prata
GRANT SELECT ON slv_sih_diasperm          TO MARCO;
GRANT SELECT ON slv_cnes_leitos           TO MARCO;
GRANT SELECT ON slv_internacao            TO MARCO;
GRANT SELECT ON slv_ocupacao              TO MARCO;
GRANT SELECT ON dim_cid                   TO MARCO;

-- Ouro
GRANT SELECT ON gld_ocupacao_mensal       TO MARCO;
GRANT SELECT ON gld_features_hospital     TO MARCO;
GRANT SELECT ON gld_kpi_rede              TO MARCO;
GRANT SELECT ON gld_cluster               TO MARCO;
GRANT SELECT ON gld_fatores_hospital      TO MARCO;

-- ------------------------------------------------------------
-- 2. Workspace do APEX (schema HOSPCHECK_APP)
--    Regra de arquitetura: o app consome APENAS views GLD_*.
--    Os sinonimos permitem consultar sem prefixo de schema.
-- ------------------------------------------------------------
GRANT SELECT ON gld_ocupacao_mensal   TO hospcheck_app;
GRANT SELECT ON gld_features_hospital TO hospcheck_app;
GRANT SELECT ON gld_kpi_rede          TO hospcheck_app;
GRANT SELECT ON gld_cluster           TO hospcheck_app;
GRANT SELECT ON gld_fatores_hospital  TO hospcheck_app;

CREATE OR REPLACE SYNONYM hospcheck_app.gld_ocupacao_mensal   FOR admin.gld_ocupacao_mensal;
CREATE OR REPLACE SYNONYM hospcheck_app.gld_features_hospital FOR admin.gld_features_hospital;
CREATE OR REPLACE SYNONYM hospcheck_app.gld_kpi_rede          FOR admin.gld_kpi_rede;
CREATE OR REPLACE SYNONYM hospcheck_app.gld_cluster           FOR admin.gld_cluster;
CREATE OR REPLACE SYNONYM hospcheck_app.gld_fatores_hospital  FOR admin.gld_fatores_hospital;

-- ------------------------------------------------------------
-- 3. Conferir o que esta concedido
-- ------------------------------------------------------------
-- SELECT grantee, table_name, privilege
--   FROM user_tab_privs
--  WHERE grantee IN ('MARCO','HOSPCHECK_APP')
--  ORDER BY grantee, table_name;
