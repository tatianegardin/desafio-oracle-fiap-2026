-- Acesso de leitura para os membros do grupo (ajustar usuarios)
GRANT SELECT ON brz_sih_tabnet_raw  TO MARCO;
GRANT SELECT ON brz_cnes_leitos_raw TO MARCO;
GRANT SELECT ON slv_sih_diasperm    TO MARCO;
GRANT SELECT ON slv_cnes_leitos     TO MARCO;
GRANT SELECT ON slv_ocupacao        TO MARCO;
-- Dica: cada membro roda 'ALTER SESSION SET CURRENT_SCHEMA = ADMIN;' no inicio da sessao
