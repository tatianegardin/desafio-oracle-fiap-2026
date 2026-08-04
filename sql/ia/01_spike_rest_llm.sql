-- ============================================================
-- SPIKE — Pergunta em portugues → SQL, via REST direto (board #30)
-- ============================================================
-- Rota ADOTADA para o M3. Chama o LLM com DBMS_CLOUD.SEND_REQUEST,
-- sem o pacote DBMS_CLOUD_AI (Select AI), que esta quebrado nesta
-- plataforma — ver docs/bug-selectai-ora20404.md.
--
-- Provedor validado: Google AI · modelo gemma-4-31b-it
-- Chave gratuita: https://aistudio.google.com → "Get API key"
--
-- ATENCAO: nunca commitar este arquivo com a chave preenchida.
-- Na implementacao final (board #31) a chave sai do script e vai
-- para uma tabela de configuracao com acesso restrito.
--
-- Executar com F5 (Run Script) e ler a aba "Saida do Script":
-- respostas grandes quebram a grade do Database Actions.
-- ============================================================

-- ------------------------------------------------------------
-- 1. ACL — autorizar o banco a alcancar a API (uma vez por usuario)
--    A ACL e por PRINCIPAL: cada usuario que for chamar precisa
--    da sua (ajustar principal_name).
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

-- Conferir:
-- SELECT host, principal, privilege FROM dba_host_aces WHERE host LIKE '%google%';

-- ------------------------------------------------------------
-- 2. Credencial
--    O SEND_REQUEST exige o parametro credential_name, mas a
--    autenticacao real do Google vai no header x-goog-api-key.
--    Qualquer credencial existente serve. Credenciais sao por
--    schema: cada usuario cria a sua.
-- ------------------------------------------------------------
-- BEGIN
--   DBMS_CLOUD.CREATE_CREDENTIAL('GOOGLE_CRED', 'GOOGLE', 'nao-usado');
-- END;
-- /

-- ------------------------------------------------------------
-- 3. Listar modelos disponiveis para a chave
--    Faca isto SEMPRE antes de fixar um modelo: os provedores
--    aposentam e renomeiam modelos sem aviso.
--    Procure por "name": "models/..." com generateContent.
-- ------------------------------------------------------------
SET SERVEROUTPUT ON
DECLARE
  resp DBMS_CLOUD_TYPES.resp;
BEGIN
  resp := DBMS_CLOUD.SEND_REQUEST(
            credential_name => 'GOOGLE_CRED',
            uri     => 'https://generativelanguage.googleapis.com/v1beta/models',
            method  => DBMS_CLOUD.METHOD_GET,
            headers => JSON_OBJECT('x-goog-api-key' VALUE '<API_KEY>'));
  DBMS_OUTPUT.PUT_LINE(DBMS_LOB.SUBSTR(DBMS_CLOUD.GET_RESPONSE_TEXT(resp), 32000, 1));
END;
/

-- ------------------------------------------------------------
-- 4. Teste de conectividade — esperado HTTP: 200
-- ------------------------------------------------------------
SET SERVEROUTPUT ON
DECLARE
  resp DBMS_CLOUD_TYPES.resp;
BEGIN
  resp := DBMS_CLOUD.SEND_REQUEST(
            credential_name => 'GOOGLE_CRED',
            uri     => 'https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:generateContent',
            method  => DBMS_CLOUD.METHOD_POST,
            headers => JSON_OBJECT('Content-Type'   VALUE 'application/json',
                                   'x-goog-api-key' VALUE '<API_KEY>'),
            body    => UTL_RAW.CAST_TO_RAW(
              '{"contents":[{"parts":[{"text":"Diga apenas: ola, estou funcionando dentro do Oracle"}]}]}'));

  DBMS_OUTPUT.PUT_LINE('HTTP: ' || DBMS_CLOUD.GET_RESPONSE_STATUS_CODE(resp));
  DBMS_OUTPUT.PUT_LINE(DBMS_LOB.SUBSTR(DBMS_CLOUD.GET_RESPONSE_TEXT(resp), 3000, 1));
END;
/

-- ------------------------------------------------------------
-- 5. O que importa: pergunta em portugues → SQL
--
--    Estrutura do prompt que funcionou:
--      1) papel do modelo  ("gerador de SQL para Oracle")
--      2) esquema          (view + colunas, com semantica e formato)
--      3) regras de saida  ("apenas o SQL, sem markdown, sem ;")
--      4) a pergunta
--
--    SQL obtido no spike, correto de primeira:
--      SELECT nome_estabelecimento FROM GLD_OCUPACAO_MENSAL
--       WHERE competencia = (SELECT MAX(competencia) FROM GLD_OCUPACAO_MENSAL)
--       ORDER BY taxa_ocupacao DESC FETCH FIRST 5 ROWS ONLY
-- ------------------------------------------------------------
SET SERVEROUTPUT ON
DECLARE
  resp   DBMS_CLOUD_TYPES.resp;
  prompt VARCHAR2(4000);
BEGIN
  prompt := 'Voce e um gerador de SQL para Oracle. Esquema disponivel: '
    || 'view GLD_OCUPACAO_MENSAL com colunas: co_cnes, nome_estabelecimento, ds_tipo_unidade, '
    || 'competencia (texto formato YYYYMM), paciente_dia, leito_dia, taxa_ocupacao (percentual), '
    || 'semaforo (OK, ATENCAO ou CRITICO), var_vs_mes_anterior, media_movel_3m, ranking_no_mes. '
    || 'Responda APENAS com o comando SQL, sem explicacao, sem markdown, sem ponto e virgula final. '
    || 'Pergunta: quais os 5 hospitais com maior taxa de ocupacao na competencia mais recente?';

  resp := DBMS_CLOUD.SEND_REQUEST(
            credential_name => 'GOOGLE_CRED',
            uri     => 'https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:generateContent',
            method  => DBMS_CLOUD.METHOD_POST,
            headers => JSON_OBJECT('Content-Type'   VALUE 'application/json',
                                   'x-goog-api-key' VALUE '<API_KEY>'),
            body    => UTL_RAW.CAST_TO_RAW(
              '{"contents":[{"parts":[{"text":"' || REPLACE(prompt, '"', '\"') || '"}]}]}'));

  DBMS_OUTPUT.PUT_LINE('HTTP: ' || DBMS_CLOUD.GET_RESPONSE_STATUS_CODE(resp));
  DBMS_OUTPUT.PUT_LINE(DBMS_LOB.SUBSTR(DBMS_CLOUD.GET_RESPONSE_TEXT(resp), 8000, 1));
END;
/

-- ============================================================
-- FORMATO DA RESPOSTA (essencial para o parse do ASK_AI)
--
-- {"candidates":[{"content":{"parts":[
--     {"text":"...raciocinio...","thought":true},   <- IGNORAR
--     {"text":"SELECT ..."}                          <- RESPOSTA FINAL
--   ],"role":"model"},"finishReason":"STOP"}],
--  "usageMetadata":{...contagem de tokens...}}
--
-- Regra: percorrer candidates[0].content.parts e usar a parte que
-- NAO tem o atributo "thought" (JSON_TABLE ou JSON_QUERY sobre o CLOB).
-- ============================================================
