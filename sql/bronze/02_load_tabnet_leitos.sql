-- ============================================================
-- Carga BRONZE via DBMS_CLOUD.COPY_DATA (board #3)
-- Bucket: hospcheck-staging · sa-saopaulo-1 · arquivos ORIGINAIS
-- Pré-requisito: 00_credencial.sql executado
-- ============================================================

-- TabNet: pula 4 linhas (título, subtítulo, período, cabeçalho); latin1; ';'
BEGIN
  DBMS_CLOUD.COPY_DATA(
    table_name      => 'BRZ_SIH_TABNET_RAW',
    credential_name => 'OBJ_STORE_CRED',
    file_uri_list   => 'https://objectstorage.sa-saopaulo-1.oraclecloud.com/n/gr2bf1uzkrub/b/hospcheck-staging/o/hospcheckA201312192_29_138_8.csv',
    format          => JSON_OBJECT(
                         'type'         VALUE 'csv',
                         'delimiter'    VALUE ';',
                         'skipheaders'  VALUE '4',
                         'characterset' VALUE 'WE8MSWIN1252',
                         'ignoremissingcolumns' VALUE 'true',
                         'rejectlimit'  VALUE '100'
                       )
  );
END;
/

-- CNES Leitos 2026 + 2025 (mesma tabela; COPY_DATA faz append)
BEGIN
  DBMS_CLOUD.COPY_DATA(
    table_name      => 'BRZ_CNES_LEITOS_RAW',
    credential_name => 'OBJ_STORE_CRED',
    file_uri_list   => 'https://objectstorage.sa-saopaulo-1.oraclecloud.com/n/gr2bf1uzkrub/b/hospcheck-staging/o/hospcheckLeitos_2026.csv',
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
    table_name      => 'BRZ_CNES_LEITOS_RAW',
    credential_name => 'OBJ_STORE_CRED',
    file_uri_list   => 'https://objectstorage.sa-saopaulo-1.oraclecloud.com/n/gr2bf1uzkrub/b/hospcheck-staging/o/hospcheckLeitos_2025.csv',
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
