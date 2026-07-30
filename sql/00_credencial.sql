-- Credencial de acesso ao OCI Object Storage (executar UMA vez, como dono do schema)
-- ATENCAO: NUNCA commitar este arquivo com valores reais.
-- username = usuario OCI (My profile) | password = Auth Token (My profile > Auth tokens)
BEGIN
  DBMS_CLOUD.CREATE_CREDENTIAL(
    credential_name => 'OBJ_STORE_CRED',
    username        => '<SEU_USUARIO_OCI>',
    password        => '<SEU_AUTH_TOKEN>'
  );
END;
/
