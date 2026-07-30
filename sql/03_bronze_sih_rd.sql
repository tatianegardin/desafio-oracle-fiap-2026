-- ============================================================
-- BRONZE: SIH-RD (AIH Reduzida) — microdados DATASUS
-- Arquivos RDSPaamm.csv convertidos de .dbc (etl/conversao/)
-- 114 colunas, 1:1 com o layout RD. Tudo VARCHAR2 de propósito:
-- fidelidade ao dado cru; conversao de tipos acontece na Prata.
-- ============================================================

CREATE TABLE brz_sih_rd_raw (
  uf_zi        VARCHAR2(15),
  ano_cmpt     VARCHAR2(15),
  mes_cmpt     VARCHAR2(15),
  espec        VARCHAR2(15),
  cgc_hosp     VARCHAR2(20),
  n_aih        VARCHAR2(20),
  ident        VARCHAR2(15),
  cep          VARCHAR2(15),
  munic_res    VARCHAR2(15),
  nasc         VARCHAR2(15),
  sexo         VARCHAR2(15),
  uti_mes_in   VARCHAR2(15),
  uti_mes_an   VARCHAR2(15),
  uti_mes_al   VARCHAR2(15),
  uti_mes_to   VARCHAR2(15),
  marca_uti    VARCHAR2(15),
  uti_int_in   VARCHAR2(15),
  uti_int_an   VARCHAR2(15),
  uti_int_al   VARCHAR2(15),
  uti_int_to   VARCHAR2(15),
  diar_acom    VARCHAR2(15),
  qt_diarias   VARCHAR2(15),
  proc_solic   VARCHAR2(15),
  proc_rea     VARCHAR2(15),
  val_sh       VARCHAR2(15),
  val_sp       VARCHAR2(15),
  val_sadt     VARCHAR2(15),
  val_rn       VARCHAR2(15),
  val_acomp    VARCHAR2(15),
  val_ortp     VARCHAR2(15),
  val_sangue   VARCHAR2(15),
  val_sadtsr   VARCHAR2(15),
  val_transp   VARCHAR2(15),
  val_obsang   VARCHAR2(15),
  val_ped1ac   VARCHAR2(15),
  val_tot      VARCHAR2(15),
  val_uti      VARCHAR2(15),
  us_tot       VARCHAR2(15),
  dt_inter     VARCHAR2(15),
  dt_saida     VARCHAR2(15),
  diag_princ   VARCHAR2(15),
  diag_secun   VARCHAR2(15),
  cobranca     VARCHAR2(15),
  natureza     VARCHAR2(15),
  nat_jur      VARCHAR2(15),
  gestao       VARCHAR2(15),
  rubrica      VARCHAR2(15),
  ind_vdrl     VARCHAR2(15),
  munic_mov    VARCHAR2(15),
  cod_idade    VARCHAR2(15),
  idade        VARCHAR2(15),
  dias_perm    VARCHAR2(15),
  morte        VARCHAR2(15),
  nacional     VARCHAR2(15),
  num_proc     VARCHAR2(20),
  car_int      VARCHAR2(15),
  tot_pt_sp    VARCHAR2(15),
  cpf_aut      VARCHAR2(20),
  homonimo     VARCHAR2(15),
  num_filhos   VARCHAR2(15),
  instru       VARCHAR2(15),
  cid_notif    VARCHAR2(15),
  contracep1   VARCHAR2(15),
  contracep2   VARCHAR2(15),
  gestrisco    VARCHAR2(15),
  insc_pn      VARCHAR2(15),
  seq_aih5     VARCHAR2(15),
  cbor         VARCHAR2(15),
  cnaer        VARCHAR2(15),
  vincprev     VARCHAR2(15),
  gestor_cod   VARCHAR2(15),
  gestor_tp    VARCHAR2(15),
  gestor_cpf   VARCHAR2(20),
  gestor_dt    VARCHAR2(15),
  cnes         VARCHAR2(15),
  cnpj_mant    VARCHAR2(20),
  infehosp     VARCHAR2(15),
  cid_asso     VARCHAR2(15),
  cid_morte    VARCHAR2(15),
  complex      VARCHAR2(15),
  financ       VARCHAR2(15),
  faec_tp      VARCHAR2(15),
  regct        VARCHAR2(15),
  raca_cor     VARCHAR2(15),
  etnia        VARCHAR2(15),
  sequencia    VARCHAR2(15),
  remessa      VARCHAR2(30),
  aud_just     VARCHAR2(100),
  sis_just     VARCHAR2(100),
  val_sh_fed   VARCHAR2(15),
  val_sp_fed   VARCHAR2(15),
  val_sh_ges   VARCHAR2(15),
  val_sp_ges   VARCHAR2(15),
  val_uci      VARCHAR2(15),
  marca_uci    VARCHAR2(15),
  diagsec1     VARCHAR2(15),
  diagsec2     VARCHAR2(15),
  diagsec3     VARCHAR2(15),
  diagsec4     VARCHAR2(15),
  diagsec5     VARCHAR2(15),
  diagsec6     VARCHAR2(15),
  diagsec7     VARCHAR2(15),
  diagsec8     VARCHAR2(15),
  diagsec9     VARCHAR2(15),
  tpdisec1     VARCHAR2(15),
  tpdisec2     VARCHAR2(15),
  tpdisec3     VARCHAR2(15),
  tpdisec4     VARCHAR2(15),
  tpdisec5     VARCHAR2(15),
  tpdisec6     VARCHAR2(15),
  tpdisec7     VARCHAR2(15),
  tpdisec8     VARCHAR2(15),
  tpdisec9     VARCHAR2(15),
  fonte_orc    VARCHAR2(15)
);

-- ------------------------------------------------------------
-- Carga: o curinga RDSP*.csv pega TODAS as competências que
-- estiverem no bucket, de uma vez. Recarga: fazer TRUNCATE antes,
-- ou COPY_DATA de um arquivo específico para append de mês novo.
-- ------------------------------------------------------------
BEGIN
  DBMS_CLOUD.COPY_DATA(
    table_name      => 'BRZ_SIH_RD_RAW',
    credential_name => 'OBJ_STORE_CRED',
    file_uri_list   => 'https://objectstorage.sa-saopaulo-1.oraclecloud.com/n/gr2bf1uzkrub/b/hospcheck-staging/o/RDSP*.csv',
    format          => JSON_OBJECT(
                         'type'         VALUE 'csv',
                         'delimiter'    VALUE ',',
                         'skipheaders'  VALUE '1',
                         'characterset' VALUE 'AL32UTF8',
                         'ignoremissingcolumns' VALUE 'true',
                         'rejectlimit'  VALUE '10000'
                       )
  );
END;
/

-- ------------------------------------------------------------
-- Validação
-- Referência: RDSP2601 = 237.622 registros (estado), sendo
-- 59.860 da capital (MUNIC_MOV = 355030) — bate com os
-- ~63 mil/mês do pitch. Total esperado ~230 mil × nº de meses.
-- ------------------------------------------------------------
SELECT ano_cmpt, mes_cmpt,
       COUNT(*)                                        AS aihs_estado,
       SUM(CASE WHEN munic_mov = '355030' THEN 1 END)  AS aihs_capital
  FROM brz_sih_rd_raw
 GROUP BY ano_cmpt, mes_cmpt
 ORDER BY ano_cmpt, mes_cmpt;

-- Cargas com erro/rejeicoes:
-- SELECT * FROM user_load_operations ORDER BY start_time DESC FETCH FIRST 5 ROWS ONLY;
