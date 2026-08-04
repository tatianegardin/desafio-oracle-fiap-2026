-- ============================================================
-- BRONZE — CID-10 (dicionario oficial DATASUS)
-- Arquivos do CID10CSV.ZIP: SUBCATEGORIAS e CAPITULOS
-- Fonte: http://www2.datasus.gov.br/cid10/V2008/download.htm
-- ============================================================
-- Tabela de dimensao: alimenta a DIM_CID na Prata, usada para
-- traduzir codigo em nome de doenca no painel e nas perguntas
-- em linguagem natural (M3).
--
-- Pre-requisitos: sql/setup/01_credencial.sql executado e os
-- dois CSVs presentes no bucket hospcheck-staging.
-- ============================================================

-- ------------------------------------------------------------
-- DDL — layout oficial dos arquivos
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
-- Carga — latin1 e ';', como os demais arquivos do DATASUS
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
-- Validacao — esperado: 12.451 subcategorias e 22 capitulos
-- ------------------------------------------------------------
SELECT (SELECT COUNT(*) FROM brz_cid_subcategorias_raw) AS subcategorias,
       (SELECT COUNT(*) FROM brz_cid_capitulos_raw)     AS capitulos
  FROM dual;
