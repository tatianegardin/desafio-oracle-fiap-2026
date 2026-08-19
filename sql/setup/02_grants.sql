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
GRANT SELECT ON gld_perfil_clinico        TO MARCO;
GRANT SELECT ON gld_diagnosticos          TO MARCO;
GRANT SELECT ON gld_sazonalidade          TO MARCO;
GRANT SELECT ON gld_regional              TO MARCO;

-- ------------------------------------------------------------
-- 2. Workspace do APEX
--
--    ATENCAO ao nome do schema: o parsing schema da aplicacao e
--    WKSP_HOSPCHECK (criado pelo APEX junto com o workspace), e NAO
--    HOSPCHECK_APP — este ultimo foi criado por engano no inicio do
--    projeto e nao e usado por nada. Conferir sempre em:
--    App Builder > aplicacao > Edit Application Properties >
--    Security > Parsing Schema.
--
--    Regra de arquitetura: o app consome APENAS views GLD_* e o
--    pacote PKG_ASK_AI. Os sinonimos permitem chamar sem prefixo.
-- ------------------------------------------------------------
GRANT SELECT ON gld_ocupacao_mensal   TO wksp_hospcheck;
GRANT SELECT ON gld_features_hospital TO wksp_hospcheck;
GRANT SELECT ON gld_kpi_rede          TO wksp_hospcheck;
GRANT SELECT ON gld_cluster           TO wksp_hospcheck;
GRANT SELECT ON gld_fatores_hospital  TO wksp_hospcheck;
GRANT SELECT ON gld_perfil_clinico    TO wksp_hospcheck;
GRANT SELECT ON gld_diagnosticos      TO wksp_hospcheck;
GRANT SELECT ON gld_sazonalidade      TO wksp_hospcheck;
GRANT SELECT ON gld_regional          TO wksp_hospcheck;

CREATE OR REPLACE SYNONYM wksp_hospcheck.gld_ocupacao_mensal   FOR admin.gld_ocupacao_mensal;
CREATE OR REPLACE SYNONYM wksp_hospcheck.gld_features_hospital FOR admin.gld_features_hospital;
CREATE OR REPLACE SYNONYM wksp_hospcheck.gld_kpi_rede          FOR admin.gld_kpi_rede;
CREATE OR REPLACE SYNONYM wksp_hospcheck.gld_cluster           FOR admin.gld_cluster;
CREATE OR REPLACE SYNONYM wksp_hospcheck.gld_fatores_hospital  FOR admin.gld_fatores_hospital;
CREATE OR REPLACE SYNONYM wksp_hospcheck.gld_perfil_clinico    FOR admin.gld_perfil_clinico;
CREATE OR REPLACE SYNONYM wksp_hospcheck.gld_diagnosticos      FOR admin.gld_diagnosticos;
CREATE OR REPLACE SYNONYM wksp_hospcheck.gld_sazonalidade      FOR admin.gld_sazonalidade;
CREATE OR REPLACE SYNONYM wksp_hospcheck.gld_regional          FOR admin.gld_regional;

-- Pacote da funcionalidade "Pergunte a IA" (M3). O pacote roda com
-- privilegios do dono, entao o workspace nao precisa de acesso a
-- CFG_AI (que guarda a chave) nem as tabelas consultadas.
GRANT EXECUTE ON pkg_ask_ai TO wksp_hospcheck;
CREATE OR REPLACE SYNONYM wksp_hospcheck.pkg_ask_ai FOR admin.pkg_ask_ai;

-- ------------------------------------------------------------
-- 3. Conferir o que esta concedido
-- ------------------------------------------------------------
-- SELECT grantee, table_name, privilege
--   FROM user_tab_privs
--  WHERE grantee IN ('MARCO','WKSP_HOSPCHECK')
--  ORDER BY grantee, table_name;
