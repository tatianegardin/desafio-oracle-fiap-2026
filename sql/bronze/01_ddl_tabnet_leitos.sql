-- ============================================================
-- BRONZE: tabelas 1:1 com os CSVs originais (board #4)
-- Dado cru, sem tratamento — fidelidade total à fonte DATASUS/TabNet
-- ============================================================

-- TabNet SMS-SP (Dias Perm): 1 coluna por mês, exatamente como o arquivo
CREATE TABLE brz_sih_tabnet_raw (
  estab_cidade VARCHAR2(300),
  m_202410 VARCHAR2(20), m_202411 VARCHAR2(20), m_202412 VARCHAR2(20),
  m_202501 VARCHAR2(20), m_202502 VARCHAR2(20), m_202503 VARCHAR2(20),
  m_202504 VARCHAR2(20), m_202505 VARCHAR2(20), m_202506 VARCHAR2(20),
  m_202507 VARCHAR2(20), m_202508 VARCHAR2(20), m_202509 VARCHAR2(20),
  m_202510 VARCHAR2(20), m_202511 VARCHAR2(20), m_202512 VARCHAR2(20),
  m_202601 VARCHAR2(20), m_202602 VARCHAR2(20), m_202603 VARCHAR2(20),
  m_202604 VARCHAR2(20), m_202605 VARCHAR2(20),
  total    VARCHAR2(20)
);

-- CNES Leitos: todas as 35 colunas do arquivo original (Brasil inteiro)
CREATE TABLE brz_cnes_leitos_raw (
  comp                  VARCHAR2(6),
  regiao                VARCHAR2(20),
  uf                    VARCHAR2(2),
  co_ibge               VARCHAR2(7),
  municipio             VARCHAR2(100),
  motivo_desabilitacao  VARCHAR2(100),
  cnes                  VARCHAR2(7),
  nome_estabelecimento  VARCHAR2(200),
  razao_social          VARCHAR2(200),
  tp_gestao             VARCHAR2(2),
  co_tipo_unidade       VARCHAR2(5),
  ds_tipo_unidade       VARCHAR2(100),
  natureza_juridica     VARCHAR2(10),
  desc_natureza_juridica VARCHAR2(100),
  no_logradouro         VARCHAR2(200),
  nu_endereco           VARCHAR2(30),
  no_complemento        VARCHAR2(100),
  no_bairro             VARCHAR2(100),
  co_cep                VARCHAR2(10),
  nu_telefone           VARCHAR2(30),
  no_email              VARCHAR2(100),
  leitos_existentes     NUMBER,
  leitos_sus            NUMBER,
  uti_total_exist       NUMBER,
  uti_total_sus         NUMBER,
  uti_adulto_exist      NUMBER,
  uti_adulto_sus        NUMBER,
  uti_pediatrico_exist  NUMBER,
  uti_pediatrico_sus    NUMBER,
  uti_neonatal_exist    NUMBER,
  uti_neonatal_sus      NUMBER,
  uti_queimado_exist    NUMBER,
  uti_queimado_sus      NUMBER,
  uti_coronariana_exist NUMBER,
  uti_coronariana_sus   NUMBER
);
