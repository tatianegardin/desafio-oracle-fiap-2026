-- ============================================================
-- HOSPCHECK SP — Pre-requisitos de rede para o M3 (Select AI)
-- ============================================================
-- Executar UMA VEZ, como ADMIN, antes de sql/ia/02_ask_ai.sql.
-- Sem estes dois objetos o PKG_ASK_AI falha com ORA-24247
-- (acesso de rede negado) ou ORA-20401 (credencial inexistente).
--
-- A investigacao que levou a esta rota (REST em vez de
-- DBMS_CLOUD_AI) esta em docs/bug-selectai-ora20404.md; o spike
-- exploratorio em sql/ia/01_spike_rest_llm.sql.
-- ============================================================

-- ------------------------------------------------------------
-- 1. ACL — autoriza o banco a alcancar a API do provedor
--
--    A ACL e por PRINCIPAL: cada usuario que for chamar a API
--    precisa da sua. O PKG_ASK_AI roda como ADMIN (dono do
--    pacote), entao e o ADMIN que precisa da permissao —
--    nao o schema do APEX.
-- ------------------------------------------------------------
BEGIN
  DBMS_NETWORK_ACL_ADMIN.APPEND_HOST_ACE(
    host => 'generativelanguage.googleapis.com',
    ace  => xs$ace_type(privilege_list => xs$name_list('http'),
                        principal_name => 'ADMIN',
                        principal_type => xs_acl.ptype_db)
  );
END;
/

-- ------------------------------------------------------------
-- 2. Credencial
--
--    DBMS_CLOUD.SEND_REQUEST exige o parametro credential_name,
--    mas a autenticacao real do Google vai no header
--    x-goog-api-key. Ou seja: o conteudo desta credencial nao e
--    usado — ela existe so para satisfazer a assinatura da API.
--    Credenciais sao por schema; criar no mesmo schema do pacote.
-- ------------------------------------------------------------
BEGIN
  DBMS_CLOUD.CREATE_CREDENTIAL(
    credential_name => 'GOOGLE_CRED',
    username        => 'GOOGLE',
    password        => 'nao-usado');
EXCEPTION
  WHEN OTHERS THEN
    IF SQLCODE = -20022 THEN NULL;   -- ja existe
    ELSE RAISE;
    END IF;
END;
/

-- ------------------------------------------------------------
-- 3. Conferencia
-- ------------------------------------------------------------
-- SELECT host, principal, privilege
--   FROM dba_host_aces
--  WHERE host LIKE '%googleapis%';
--
-- SELECT credential_name, username, enabled
--   FROM user_credentials
--  WHERE credential_name = 'GOOGLE_CRED';