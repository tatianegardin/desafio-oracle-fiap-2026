-- ============================================================
-- CID-10: Bronze (arquivos oficiais DATASUS, 1:1) + Prata (DIM_CID)
-- Fonte: http://www2.datasus.gov.br/cid10/V2008/download.htm (CID10CSV.ZIP)
-- Subir no bucket: CID-10-SUBCATEGORIAS.CSV e CID-10-CAPITULOS.CSV
-- ============================================================

-- ------------------------------------------------------------
-- PASSO 1 — BRONZE: layout oficial dos arquivos
-- ------------------------------------------------------------
CREATE TABLE brz_cid_subcategorias_raw (
  subcat     VARCHAR2(4),
  classif    VARCHAR2(5),
  restrsexo  VARCHAR2(5),
  causaobito VARCHAR2(5),
  descricao  VARCHAR2(400),
  descrabrev VARCHAR2(120),
  refer      VARCHAR2(60),
  excluidos  VARCHAR2(400)
);

CREATE TABLE brz_cid_capitulos_raw (
  numcap     VARCHAR2(4),
  catinic    VARCHAR2(3),
  catfim     VARCHAR2(3),
  descricao  VARCHAR2(400),
  descrabrev VARCHAR2(120)
);

-- ------------------------------------------------------------
-- PASSO 2 — Carga (mesma credencial de sempre)
-- ------------------------------------------------------------
BEGIN
  DBMS_CLOUD.COPY_DATA(
    table_name      => 'BRZ_CID_SUBCATEGORIAS_RAW',
    credential_name => 'OBJ_STORE_CRED',
    file_uri_list   => 'https://objectstorage.sa-saopaulo-1.oraclecloud.com/n/gr2bf1uzkrub/b/hospcheck-staging/o/CID-10-SUBCATEGORIAS.CSV',
    format          => JSON_OBJECT(
                         'type'         VALUE 'csv',
                         'delimiter'    VALUE ';',
                         'skipheaders'  VALUE '1',
                         'characterset' VALUE 'WE8MSWIN1252',
                         'ignoremissingcolumns' VALUE 'true',
                         'rejectlimit'  VALUE '100'
                       )
  );
END;
/

BEGIN
  DBMS_CLOUD.COPY_DATA(
    table_name      => 'BRZ_CID_CAPITULOS_RAW',
    credential_name => 'OBJ_STORE_CRED',
    file_uri_list   => 'https://objectstorage.sa-saopaulo-1.oraclecloud.com/n/gr2bf1uzkrub/b/hospcheck-staging/o/CID-10-CAPITULOS.CSV',
    format          => JSON_OBJECT(
                         'type'         VALUE 'csv',
                         'delimiter'    VALUE ';',
                         'skipheaders'  VALUE '1',
                         'characterset' VALUE 'WE8MSWIN1252',
                         'ignoremissingcolumns' VALUE 'true',
                         'rejectlimit'  VALUE '100'
                       )
  );
END;
/

-- ------------------------------------------------------------
-- PASSO 3 — PRATA: DIM_CID (subcategoria + capítulo)
-- O capítulo é achado por faixa: a categoria (3 primeiros chars
-- do código) fica entre CATINIC e CATFIM do capítulo.
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW dim_cid AS
SELECT s.subcat                          AS co_cid,
       s.descricao                       AS ds_cid,
       s.descrabrev                      AS ds_cid_abrev,
       TO_NUMBER(c.numcap)               AS nr_capitulo,
       c.descricao                       AS ds_capitulo
  FROM brz_cid_subcategorias_raw s
  LEFT JOIN brz_cid_capitulos_raw c
    ON SUBSTR(s.subcat, 1, 3) BETWEEN c.catinic AND c.catfim;

-- ------------------------------------------------------------
-- PASSO 4 — Validação
-- ------------------------------------------------------------
-- ~12 mil subcategorias, 22 capítulos, e nenhum órfão de capítulo:
SELECT (SELECT COUNT(*) FROM brz_cid_subcategorias_raw) subcategorias,
       (SELECT COUNT(*) FROM brz_cid_capitulos_raw)     capitulos,
       (SELECT COUNT(*) FROM dim_cid WHERE nr_capitulo IS NULL) sem_capitulo
  FROM dual;

-- A pergunta que motivou tudo: o que mais interna CRIANÇAS (<12 anos)?
SELECT d.ds_cid_abrev, COUNT(*) internacoes
  FROM slv_internacao i
  JOIN dim_cid d ON d.co_cid = i.cid_principal
 WHERE i.idade_anos < 12
 GROUP BY d.ds_cid_abrev
 ORDER BY internacoes DESC
 FETCH FIRST 15 ROWS ONLY;

-- E o que mais interna IDOSOS (65+)?
SELECT d.ds_cid_abrev, COUNT(*) internacoes
  FROM slv_internacao i
  JOIN dim_cid d ON d.co_cid = i.cid_principal
 WHERE i.idade_anos >= 65
 GROUP BY d.ds_cid_abrev
 ORDER BY internacoes DESC
 FETCH FIRST 15 ROWS ONLY;

-- Bônus: capítulos por faixa etária (visão epidemiológica)
SELECT d.ds_capitulo,
       SUM(CASE WHEN i.idade_anos < 12  THEN 1 ELSE 0 END) criancas,
       SUM(CASE WHEN i.idade_anos >= 65 THEN 1 ELSE 0 END) idosos
  FROM slv_internacao i
  JOIN dim_cid d ON d.co_cid = i.cid_principal
 GROUP BY d.ds_capitulo
 ORDER BY idosos DESC;
