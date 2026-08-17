-- ============================================================
-- PKG_ASK_AI — pergunta em portugues -> SQL sobre a camada Ouro
-- Board #31 · consumido pela Tela 3 do APEX (#33)
-- ============================================================
-- Implementa a capacidade do Select AI usando REST direto
-- (DBMS_CLOUD.SEND_REQUEST), porque o pacote DBMS_CLOUD_AI esta
-- quebrado nesta plataforma — ver docs/bug-selectai-ora20404.md.
--
-- Pre-requisitos (uma vez, como ADMIN):
--   · ACL para o host do provedor  — ver sql/ia/01_spike_rest_llm.sql
--   · credencial qualquer existente (a auth real vai no header)
--
-- Executar como ADMIN, na ordem deste arquivo.
-- ============================================================

-- ------------------------------------------------------------
-- 1. Configuracao — chave e modelo FORA do codigo
--    Trocar de modelo ou provedor = UPDATE nesta tabela.
-- ------------------------------------------------------------
CREATE TABLE cfg_ai (
  chave      VARCHAR2(40) PRIMARY KEY,
  valor      VARCHAR2(500) NOT NULL,
  atualizado DATE DEFAULT SYSDATE
);

INSERT INTO cfg_ai (chave, valor) VALUES
  ('endpoint', 'https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:generateContent');
INSERT INTO cfg_ai (chave, valor) VALUES
  ('credencial', 'GOOGLE_CRED');
INSERT INTO cfg_ai (chave, valor) VALUES
  ('api_key', '<COLE_A_CHAVE_AQUI>');
COMMIT;

-- A tabela guarda segredo: nao conceder SELECT a ninguem.
-- O APEX acessa a funcao (definer's rights), nunca a tabela.

-- ------------------------------------------------------------
-- 2. Log das perguntas — auditoria e base da bateria de testes (#32)
-- ------------------------------------------------------------
CREATE TABLE log_ask_ai (
  id           NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  momento      TIMESTAMP DEFAULT SYSTIMESTAMP,
  usuario      VARCHAR2(60),
  pergunta     VARCHAR2(1000),
  sql_gerado   CLOB,
  status       VARCHAR2(20),
  erro         VARCHAR2(500)
);

-- ------------------------------------------------------------
-- 3. O pacote
-- ------------------------------------------------------------
CREATE OR REPLACE PACKAGE pkg_ask_ai AS
  -- Gera o SQL a partir da pergunta. Levanta erro se o modelo
  -- devolver algo que nao seja uma consulta de leitura.
  FUNCTION gerar_sql (p_pergunta IN VARCHAR2) RETURN CLOB;

  -- Mesma coisa, mas nunca levanta erro: devolve a mensagem no
  -- lugar do SQL. Usado pela regiao do APEX.
  FUNCTION gerar_sql_seguro (p_pergunta IN VARCHAR2) RETURN CLOB;
END pkg_ask_ai;
/

CREATE OR REPLACE PACKAGE BODY pkg_ask_ai AS

  -- ---------- helpers ----------
  FUNCTION cfg (p_chave VARCHAR2) RETURN VARCHAR2 IS
    v VARCHAR2(500);
  BEGIN
    SELECT valor INTO v FROM cfg_ai WHERE chave = p_chave;
    RETURN v;
  END cfg;

  -- Descricao do esquema entregue ao modelo, montada a partir dos
  -- COMMENT ON do dicionario (aplicados por ouro_transform.py).
  -- Melhorar o comentario da coluna = melhorar o SQL gerado, sem
  -- tocar neste codigo.
  FUNCTION esquema RETURN CLOB IS
    v CLOB := 'Views disponiveis (Oracle). Use apenas estas:' || CHR(10);
  BEGIN
    FOR t IN (SELECT table_name, comments
                FROM user_tab_comments
               WHERE table_name LIKE 'GLD!_%' ESCAPE '!'
               ORDER BY table_name)
    LOOP
      v := v || CHR(10) || t.table_name || ' — ' || NVL(t.comments, '') || CHR(10);
      FOR c IN (SELECT column_name, comments
                  FROM user_col_comments
                 WHERE table_name = t.table_name
                   AND comments IS NOT NULL
                 ORDER BY column_name)
      LOOP
        v := v || '  ' || LOWER(c.column_name) || ': ' || c.comments || CHR(10);
      END LOOP;
    END LOOP;

    v := v || CHR(10)
      || 'Regras de escrita: ao listar hospitais, sempre incluir a coluna '
      || 'nome_estabelecimento (nunca devolver apenas o codigo CNES). '
      || 'Ao devolver percentuais e valores, arredondar com ROUND. '
      || 'Sempre dar apelido em portugues legivel a cada coluna do '
      || 'resultado, entre aspas duplas. Exemplo: SELECT '
      || 'nome_estabelecimento AS "Hospital", ROUND(perm_media,1) AS '
      || '"Permanencia media (dias)" FROM ... '
      || CHR(10)
      || 'Contexto: dados do SUS, municipio de Sao Paulo, competencias '
      || '202501 a 202605. Para "mes mais recente" use '
      || '(SELECT MAX(competencia) FROM GLD_OCUPACAO_MENSAL). '
      || 'Ignore hospitais com atuacao_sus_residual = 1 salvo pedido explicito.';
    RETURN v;
  END esquema;

  -- Escapa o texto para caber dentro de uma string JSON.
  -- A ordem importa: a contrabarra tem de ser tratada primeiro.
  FUNCTION escapar (p_txt CLOB) RETURN CLOB IS
    v CLOB := p_txt;
  BEGIN
    v := REPLACE(v, '\',    '\\');
    v := REPLACE(v, '"',     '\"');
    v := REPLACE(v, CHR(13), '');
    v := REPLACE(v, CHR(10), '\n');
    v := REPLACE(v, CHR(9),  ' ');
    RETURN v;
  END escapar;

  -- Remove cercas de markdown e ponto-e-virgula final
  FUNCTION limpar (p_txt CLOB) RETURN CLOB IS
    v CLOB := p_txt;
  BEGIN
    v := REGEXP_REPLACE(v, '```[[:alnum:]]*', '');
    v := REPLACE(v, '```', '');
    v := TRIM(v);
    v := RTRIM(v, ';' || CHR(10) || CHR(13) || ' ');
    RETURN v;
  END limpar;

  -- So consulta de leitura passa
  PROCEDURE validar (p_sql CLOB) IS
    v_ini VARCHAR2(10);
  BEGIN
    v_ini := UPPER(SUBSTR(TRIM(p_sql), 1, 6));
    IF v_ini NOT IN ('SELECT', 'WITH') THEN
      RAISE_APPLICATION_ERROR(-20101,
        'A resposta nao e uma consulta de leitura.');
    END IF;
    IF REGEXP_LIKE(UPPER(p_sql),
         '(^|[[:space:]])(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|EXECUTE|BEGIN)([[:space:]]|$)') THEN
      RAISE_APPLICATION_ERROR(-20102,
        'A resposta contem comando de modificacao — bloqueada.');
    END IF;
  END validar;

  -- ---------- chamada ao modelo ----------
  FUNCTION chamar (p_prompt CLOB) RETURN CLOB IS
    v_resp   DBMS_CLOUD_TYPES.resp;
    v_status NUMBER;
    v_corpo  CLOB;
    v_texto  CLOB;
    v_body   CLOB;
  BEGIN
    v_body := '{"contents":[{"parts":[{"text":"'
              || escapar(p_prompt) || '"}]}]}';

    v_resp := DBMS_CLOUD.SEND_REQUEST(
                credential_name => cfg('credencial'),
                uri             => cfg('endpoint'),
                method          => DBMS_CLOUD.METHOD_POST,
                headers         => JSON_OBJECT(
                                     'Content-Type'   VALUE 'application/json',
                                     'x-goog-api-key' VALUE cfg('api_key')),
                body            => UTL_RAW.CAST_TO_RAW(v_body));

    v_status := DBMS_CLOUD.GET_RESPONSE_STATUS_CODE(v_resp);
    v_corpo  := DBMS_CLOUD.GET_RESPONSE_TEXT(v_resp);

    IF v_status != 200 THEN
      RAISE_APPLICATION_ERROR(-20103,
        'Servico de IA retornou HTTP ' || v_status || '. ' ||
        SUBSTR(v_corpo, 1, 300));
    END IF;

    -- a resposta final e a parte SEM o atributo "thought"
    SELECT texto INTO v_texto
      FROM JSON_TABLE(v_corpo, '$.candidates[0].content.parts[*]'
             COLUMNS (texto      CLOB        PATH '$.text',
                      pensamento VARCHAR2(10) PATH '$.thought'))
     WHERE pensamento IS NULL
       AND ROWNUM = 1;

    RETURN v_texto;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      RAISE_APPLICATION_ERROR(-20104,
        'Nao foi possivel interpretar a resposta do servico de IA.');
  END chamar;

  -- ---------- API publica ----------
  FUNCTION gerar_sql (p_pergunta IN VARCHAR2) RETURN CLOB IS
    v_prompt CLOB;
    v_sql    CLOB;
    v_erro   VARCHAR2(500);
  BEGIN
    v_prompt :=
      'Voce e um gerador de SQL para Oracle Database. '
      || 'Responda APENAS com o comando SQL, sem explicacao, sem '
      || 'markdown, sem ponto e virgula final. Use somente as views '
      || 'descritas abaixo. Se a pergunta nao puder ser respondida '
      || 'com elas, responda exatamente: SELECT ''Pergunta fora do '
      || 'escopo do painel'' AS aviso FROM dual' || CHR(10) || CHR(10)
      || esquema() || CHR(10) || CHR(10)
      || 'Pergunta: ' || p_pergunta;

    v_sql := limpar(chamar(v_prompt));
    validar(v_sql);

    INSERT INTO log_ask_ai (usuario, pergunta, sql_gerado, status)
    VALUES (NVL(SYS_CONTEXT('APEX$SESSION','APP_USER'), USER),
            p_pergunta, v_sql, 'OK');
    COMMIT;

    RETURN v_sql;
  EXCEPTION
    WHEN OTHERS THEN
      -- SQLERRM e funcao PL/SQL: nao pode ir direto num comando SQL
      v_erro := SUBSTR(SQLERRM, 1, 500);
      INSERT INTO log_ask_ai (usuario, pergunta, status, erro)
      VALUES (NVL(SYS_CONTEXT('APEX$SESSION','APP_USER'), USER),
              p_pergunta, 'ERRO', v_erro);
      COMMIT;
      RAISE;
  END gerar_sql;

  FUNCTION gerar_sql_seguro (p_pergunta IN VARCHAR2) RETURN CLOB IS
    v_erro VARCHAR2(400);
  BEGIN
    IF p_pergunta IS NULL OR LENGTH(TRIM(p_pergunta)) < 5 THEN
      RETURN q'[SELECT 'Digite uma pergunta.' AS aviso FROM dual]';
    END IF;
    RETURN gerar_sql(p_pergunta);
  EXCEPTION
    WHEN OTHERS THEN
      v_erro := REPLACE(SUBSTR(SQLERRM, 1, 200), '''', '');
      RETURN q'[SELECT ']' || v_erro || q'[' AS erro FROM dual]';
  END gerar_sql_seguro;

END pkg_ask_ai;
/

-- ------------------------------------------------------------
-- 4. Acesso do APEX
--    O pacote roda com privilegios do dono (ADMIN), entao o
--    workspace nao precisa de acesso a cfg_ai nem as views.
-- ------------------------------------------------------------
GRANT EXECUTE ON pkg_ask_ai TO hospcheck_app;
CREATE OR REPLACE SYNONYM hospcheck_app.pkg_ask_ai FOR admin.pkg_ask_ai;

-- ------------------------------------------------------------
-- 5. Teste
-- ------------------------------------------------------------
SET SERVEROUTPUT ON
DECLARE
  v CLOB;
BEGIN
  v := pkg_ask_ai.gerar_sql('quais os 5 hospitais com maior ocupacao no mes mais recente');
  DBMS_OUTPUT.PUT_LINE(DBMS_LOB.SUBSTR(v, 3000, 1));
END;
/

-- Perguntas registradas:
-- SELECT momento, usuario, pergunta, status, erro FROM log_ask_ai ORDER BY id DESC;
