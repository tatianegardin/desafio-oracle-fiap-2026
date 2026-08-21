"""
HOSPCHECK SP — Orquestrador da camada Prata via Python
Executa as transformações DENTRO do banco (o dado não sai do ADB);
pandas entra só para exibir as validações.

Dependências: pip install oracledb pandas
Conexão: lib/db.py (wallet + variáveis de ambiente — ver .env.example)

Uso (a partir da raiz do repo):
    set -a; source .env; set +a
    python prata_transform.py
"""

import pandas as pd

from db import get_connection

TRANSFORMACOES = [
    # (nome, sql) — mesma lógica do sql/06_prata_sih_rd.sql
    ("drop slv_internacao (se existir)",
     "BEGIN EXECUTE IMMEDIATE 'DROP TABLE slv_internacao CASCADE CONSTRAINTS PURGE'; "
     "EXCEPTION WHEN OTHERS THEN IF SQLCODE != -942 THEN RAISE; END IF; END;"),

    ("criar slv_internacao", """
CREATE TABLE slv_internacao AS
SELECT LPAD(cnes, 7, '0')                                   AS co_cnes,
       ano_cmpt || mes_cmpt                                 AS competencia,
       n_aih,
       TO_DATE(dt_inter DEFAULT NULL ON CONVERSION ERROR, 'YYYYMMDD') AS dt_internacao,
       TO_DATE(dt_saida DEFAULT NULL ON CONVERSION ERROR, 'YYYYMMDD') AS dt_saida,
       TO_NUMBER(dias_perm  DEFAULT NULL ON CONVERSION ERROR) AS dias_perm,
       TO_NUMBER(qt_diarias DEFAULT NULL ON CONVERSION ERROR) AS qt_diarias,
       TO_NUMBER(uti_mes_to DEFAULT NULL ON CONVERSION ERROR) AS diarias_uti,
       TO_NUMBER(val_tot DEFAULT NULL ON CONVERSION ERROR,
                 '999999999990D99', 'NLS_NUMERIC_CHARACTERS=''.,''') AS val_total,
       TO_NUMBER(val_uti DEFAULT NULL ON CONVERSION ERROR,
                 '999999999990D99', 'NLS_NUMERIC_CHARACTERS=''.,''') AS val_uti,
       CASE sexo WHEN '1' THEN 'M' WHEN '3' THEN 'F' ELSE 'IGN' END AS sexo,
       CASE cod_idade
         WHEN '4' THEN TO_NUMBER(idade DEFAULT NULL ON CONVERSION ERROR)
         WHEN '3' THEN ROUND(TO_NUMBER(idade DEFAULT NULL ON CONVERSION ERROR)/12, 1)
         WHEN '2' THEN ROUND(TO_NUMBER(idade DEFAULT NULL ON CONVERSION ERROR)/365, 2)
       END                                                   AS idade_anos,
       CASE WHEN morte = '1' THEN 1 ELSE 0 END               AS fl_obito,
       diag_princ                                            AS cid_principal,
       CASE complex WHEN '02' THEN 'MEDIA' WHEN '03' THEN 'ALTA'
                    ELSE 'OUTRA' END                         AS complexidade,
       CASE car_int WHEN '01' THEN 'ELETIVO' WHEN '02' THEN 'URGENCIA'
                    ELSE 'OUTRO' END                         AS carater_internacao,
       proc_rea                                              AS procedimento
  FROM brz_sih_rd_raw
 WHERE munic_mov = '355030'"""),

    ("indice hospital x competencia",
     "CREATE INDEX ix_slv_int_cnes_comp ON slv_internacao (co_cnes, competencia)"),

    # --- leitos (CNES), recorte SP capital ---
    ("drop slv_cnes_leitos (se existir)",
     "BEGIN EXECUTE IMMEDIATE 'DROP TABLE slv_cnes_leitos CASCADE CONSTRAINTS PURGE'; "
     "EXCEPTION WHEN OTHERS THEN IF SQLCODE != -942 THEN RAISE; END IF; END;"),

    ("criar slv_cnes_leitos", """
CREATE TABLE slv_cnes_leitos AS
SELECT comp AS competencia, cnes, nome_estabelecimento, razao_social,
       tp_gestao, co_tipo_unidade, ds_tipo_unidade,
       natureza_juridica, desc_natureza_juridica,
       leitos_existentes, leitos_sus,
       uti_total_exist, uti_total_sus,
       uti_adulto_exist, uti_adulto_sus,
       uti_pediatrico_exist, uti_pediatrico_sus,
       uti_neonatal_exist, uti_neonatal_sus,
       -- localizacao: base da analise regional (board #40)
       no_bairro,
       co_cep,
       -- Zona a partir do prefixo do CEP. Os Correios organizam a capital
       -- em faixas por regiao: 01 centro, 02 norte, 03 leste, 04 sul,
       -- 05 oeste e 08 extremo leste. E uma aproximacao geografica
       -- (o CEP e do endereco do estabelecimento, nao da area de
       -- cobertura assistencial), suficiente para agrupar a rede.
       CASE SUBSTR(co_cep, 1, 2)
         WHEN '01' THEN 'Centro'
         WHEN '02' THEN 'Zona Norte'
         WHEN '03' THEN 'Zona Leste'
         WHEN '04' THEN 'Zona Sul'
         WHEN '05' THEN 'Zona Oeste'
         WHEN '08' THEN 'Extremo Leste'
         ELSE 'Nao identificada'
       END AS zona
  FROM brz_cnes_leitos_raw
 WHERE co_ibge = '355030'"""),

    ("indice leitos hospital x competencia",
     "CREATE INDEX ix_slv_leitos_cnes_comp ON slv_cnes_leitos (cnes, competencia)"),

    # --- dias de permanencia (TabNet), formato largo -> longo ---
    ("drop slv_sih_diasperm (se existir)",
     "BEGIN EXECUTE IMMEDIATE 'DROP TABLE slv_sih_diasperm CASCADE CONSTRAINTS PURGE'; "
     "EXCEPTION WHEN OTHERS THEN IF SQLCODE != -942 THEN RAISE; END IF; END;"),

    ("criar slv_sih_diasperm", """
CREATE TABLE slv_sih_diasperm AS
SELECT CAST(LPAD(REGEXP_SUBSTR(estab_cidade, '^\\d+'), 7, '0') AS VARCHAR2(7)) AS co_cnes,
       TRIM(REGEXP_REPLACE(estab_cidade, '^\\d+\\s*', ''))      AS no_estabelecimento,
       -- UNPIVOT com rotulos literais gera CHAR(6), nao VARCHAR2(6);
       -- CAST evita ORA-02267 na FK contra slv_cnes_leitos.competencia
       CAST(competencia AS VARCHAR2(6)) AS competencia,
       TO_NUMBER(dias)                                        AS dias_perm
  FROM brz_sih_tabnet_raw
  -- As competencias de 2024 (out a dez) vem no arquivo do TabNet e entram
  -- aqui, mas nao aparecem nas views da Ouro: o JOIN com SLV_CNES_LEITOS
  -- as descarta, porque o CNES carregado comeca em 2025. O projeto trabalha
  -- com as 17 competencias de 202501 a 202605. Mantidas na lista para o caso
  -- de o CNES de 2024 ser carregado depois.
  UNPIVOT (dias FOR competencia IN (
    m_202410 AS '202410', m_202411 AS '202411', m_202412 AS '202412',
    m_202501 AS '202501', m_202502 AS '202502', m_202503 AS '202503',
    m_202504 AS '202504', m_202505 AS '202505', m_202506 AS '202506',
    m_202507 AS '202507', m_202508 AS '202508', m_202509 AS '202509',
    m_202510 AS '202510', m_202511 AS '202511', m_202512 AS '202512',
    m_202601 AS '202601', m_202602 AS '202602', m_202603 AS '202603',
    m_202604 AS '202604', m_202605 AS '202605'))
 WHERE REGEXP_LIKE(estab_cidade, '^\\d')
   AND dias <> '-'"""),

    ("indice diasperm hospital x competencia",
     "CREATE INDEX ix_slv_diasperm_cnes_comp ON slv_sih_diasperm (co_cnes, competencia)"),

    # --- ocupacao: paciente-dia x leito-dia ---
    ("drop slv_ocupacao (se existir)",
     "BEGIN EXECUTE IMMEDIATE 'DROP TABLE slv_ocupacao CASCADE CONSTRAINTS PURGE'; "
     "EXCEPTION WHEN OTHERS THEN IF SQLCODE != -942 THEN RAISE; END IF; END;"),

    ("criar slv_ocupacao", """
CREATE TABLE slv_ocupacao AS
SELECT s.co_cnes,
       c.nome_estabelecimento,
       c.ds_tipo_unidade,
       s.competencia,
       s.dias_perm AS paciente_dia,
       c.leitos_sus * EXTRACT(DAY FROM LAST_DAY(TO_DATE(s.competencia,'YYYYMM'))) AS leito_dia,
       ROUND(100 * s.dias_perm /
             NULLIF(c.leitos_sus * EXTRACT(DAY FROM LAST_DAY(TO_DATE(s.competencia,'YYYYMM'))), 0), 1) AS taxa_ocupacao
  FROM slv_sih_diasperm s
  JOIN slv_cnes_leitos  c
    ON c.cnes = s.co_cnes AND c.competencia = s.competencia"""),

    # DIM_CID como TABELA (era view): permite PK e ser alvo de FK,
    # e passa a ficar versionada aqui junto com o resto da Prata.
    ("drop dim_cid (se existir)",
     "BEGIN EXECUTE IMMEDIATE 'DROP TABLE dim_cid CASCADE CONSTRAINTS PURGE'; "
     "EXCEPTION WHEN OTHERS THEN IF SQLCODE != -942 THEN RAISE; END IF; END;"),

    ("drop view dim_cid (versao antiga, se existir)",
     "BEGIN EXECUTE IMMEDIATE 'DROP VIEW dim_cid'; "
     "EXCEPTION WHEN OTHERS THEN IF SQLCODE != -942 THEN RAISE; END IF; END;"),

    ("criar dim_cid", """
CREATE TABLE dim_cid AS
SELECT s.subcat                AS co_cid,
       s.descricao             AS ds_cid,
       s.descrabrev            AS ds_cid_abrev,
       TO_NUMBER(c.numcap)     AS nr_capitulo,
       c.descricao             AS ds_capitulo
  FROM brz_cid_subcategorias_raw s
  LEFT JOIN brz_cid_capitulos_raw c
    ON SUBSTR(s.subcat, 1, 3) BETWEEN c.catinic AND c.catfim"""),


    # Parse do JSON da API do CNES. A Bronze guarda o documento como
    # veio; aqui ele vira colunas tipadas, como qualquer outra fonte.
    ("drop slv_estabelecimento (se existir)",
     "BEGIN EXECUTE IMMEDIATE 'DROP TABLE slv_estabelecimento PURGE'; "
     "EXCEPTION WHEN OTHERS THEN IF SQLCODE != -942 THEN RAISE; END IF; END;"),

    ("criar slv_estabelecimento", """
CREATE TABLE slv_estabelecimento AS
SELECT co_cnes,
       JSON_VALUE(payload, '$.nome_fantasia')                         AS nome_fantasia,
       JSON_VALUE(payload, '$.nome_razao_social')                     AS razao_social,
       JSON_VALUE(payload, '$.bairro_estabelecimento')                AS bairro,
       JSON_VALUE(payload, '$.codigo_cep_estabelecimento')            AS cep,
       JSON_VALUE(payload, '$.endereco_estabelecimento')              AS logradouro,
       JSON_VALUE(payload, '$.latitude_estabelecimento_decimo_grau'
                  RETURNING NUMBER)                                   AS latitude,
       JSON_VALUE(payload, '$.longitude_estabelecimento_decimo_grau'
                  RETURNING NUMBER)                                   AS longitude,
       JSON_VALUE(payload, '$.descricao_turno_atendimento')           AS turno_atendimento,
       JSON_VALUE(payload, '$.descricao_esfera_administrativa')       AS esfera_administrativa,
       -- atributos estruturais que o arquivo de leitos nao traz
       CASE JSON_VALUE(payload, '$.estabelecimento_possui_centro_cirurgico')
            WHEN '1' THEN 1 ELSE 0 END                                AS tem_centro_cirurgico,
       CASE JSON_VALUE(payload, '$.estabelecimento_possui_centro_obstetrico')
            WHEN '1' THEN 1 ELSE 0 END                                AS tem_centro_obstetrico,
       CASE JSON_VALUE(payload, '$.estabelecimento_possui_centro_neonatal')
            WHEN '1' THEN 1 ELSE 0 END                                AS tem_centro_neonatal,
       CASE JSON_VALUE(payload, '$.estabelecimento_possui_atendimento_hospitalar')
            WHEN '1' THEN 1 ELSE 0 END                                AS tem_atend_hospitalar,
       -- codigo 04 = unidade sem atividade de ensino; demais indicam ensino/pesquisa
       CASE WHEN JSON_VALUE(payload, '$.codigo_atividade_ensino_unidade')
                 NOT IN ('04') THEN 1 ELSE 0 END                      AS tem_atividade_ensino,
       JSON_VALUE(payload, '$.codigo_atividade_ensino_unidade')       AS co_atividade_ensino,
       TO_DATE(JSON_VALUE(payload, '$.data_atualizacao'), 'YYYY-MM-DD') AS data_atualizacao_cnes
  FROM brz_cnes_api_raw
 WHERE http_status = 200"""),

]

CHAVES = [
    # --- chaves primarias / unicas ---
    # RELY explicito: as FKs abaixo sao RELY DISABLE (nao custam validacao
    # em CTAS de milhoes de linhas), e o Oracle exige que a PK/UK referenciada
    # tambem seja RELY para aceitar uma FK RELY (ORA-25158 se nao for).
    "ALTER TABLE dim_cid ADD CONSTRAINT pk_dim_cid PRIMARY KEY (co_cid) RELY",
    "ALTER TABLE slv_cnes_leitos ADD CONSTRAINT pk_slv_cnes_leitos PRIMARY KEY (cnes, competencia) RELY",
    "ALTER TABLE slv_sih_diasperm ADD CONSTRAINT pk_slv_sih_diasperm PRIMARY KEY (co_cnes, competencia) RELY",
    "ALTER TABLE slv_ocupacao ADD CONSTRAINT pk_slv_ocupacao PRIMARY KEY (co_cnes, competencia) RELY",

    # --- chaves estrangeiras ---
    "ALTER TABLE slv_ocupacao ADD CONSTRAINT fk_ocup_leitos "
    "FOREIGN KEY (co_cnes, competencia) "
    "REFERENCES slv_cnes_leitos (cnes, competencia) RELY DISABLE NOVALIDATE",

    "ALTER TABLE slv_ocupacao ADD CONSTRAINT fk_ocup_diasperm "
    "FOREIGN KEY (co_cnes, competencia) "
    "REFERENCES slv_sih_diasperm (co_cnes, competencia) RELY DISABLE NOVALIDATE",

    "ALTER TABLE slv_internacao ADD CONSTRAINT fk_intern_leitos "
    "FOREIGN KEY (co_cnes, competencia) "
    "REFERENCES slv_cnes_leitos (cnes, competencia) RELY DISABLE NOVALIDATE",

    "ALTER TABLE slv_internacao ADD CONSTRAINT fk_intern_cid "
    "FOREIGN KEY (cid_principal) "
    "REFERENCES dim_cid (co_cid) RELY DISABLE NOVALIDATE",
]

# ANNOTATIONS (Oracle 23ai/26ai) — metadados estruturados chave-valor,
# complementares ao COMMENT ON (texto livre). Consultaveis em
# USER_ANNOTATIONS_USAGE e usados por ferramentas de catalogo e IA.
ANOTACOES = [
    """ALTER TABLE slv_estabelecimento ANNOTATIONS (ADD OR REPLACE
         Camada 'Prata', Grao 'um estabelecimento',
         Fonte 'API dados abertos CNES (JSON)',
         Formato 'semiestruturado',
         Uso 'geolocalizacao para mapa e atributos estruturais')""",
    """ALTER TABLE slv_internacao ANNOTATIONS (ADD OR REPLACE
         Camada 'Prata', Grao 'uma internacao (AIH)',
         Fonte 'SIH-RD / DATASUS', Recorte 'municipio 355030 - Sao Paulo capital',
         Volume 'aproximadamente 60 mil linhas por competencia')""",

    """ALTER TABLE slv_ocupacao ANNOTATIONS (ADD OR REPLACE
         Camada 'Prata', Grao 'hospital x competencia',
         Fonte 'SIH/TabNet + CNES', Metrica 'paciente-dia dividido por leito-dia')""",

    """ALTER TABLE slv_cnes_leitos ANNOTATIONS (ADD OR REPLACE
         Camada 'Prata', Grao 'estabelecimento x competencia',
         Fonte 'CNES / DEMAS', Recorte 'municipio 355030 - Sao Paulo capital')""",

    """ALTER TABLE slv_sih_diasperm ANNOTATIONS (ADD OR REPLACE
         Camada 'Prata', Grao 'hospital x competencia',
         Fonte 'TabNet SMS-SP', Observacao 'fonte oficial agregada de paciente-dia')""",

    """ALTER TABLE dim_cid ANNOTATIONS (ADD OR REPLACE
         Camada 'Prata', Tipo 'dimensao', Grao 'codigo CID-10',
         Fonte 'DATASUS CID-10 versao 2008')""",
]

COMENTARIOS = [
    "COMMENT ON TABLE slv_estabelecimento IS 'Cadastro do estabelecimento vindo da API do CNES em JSON, ja tipado: localizacao geografica, atributos estruturais e atividade de ensino. Grao: um estabelecimento'",
    "COMMENT ON COLUMN slv_estabelecimento.latitude IS 'Latitude em grau decimal, permite plotar o hospital em mapa'",
    "COMMENT ON COLUMN slv_estabelecimento.longitude IS 'Longitude em grau decimal, permite plotar o hospital em mapa'",
    "COMMENT ON COLUMN slv_estabelecimento.bairro IS 'Bairro do estabelecimento conforme a API do CNES'",
    "COMMENT ON COLUMN slv_estabelecimento.tem_centro_cirurgico IS 'Sinalizador 1 quando o estabelecimento possui centro cirurgico'",
    "COMMENT ON COLUMN slv_estabelecimento.tem_centro_obstetrico IS 'Sinalizador 1 quando possui centro obstetrico, indica maternidade'",
    "COMMENT ON COLUMN slv_estabelecimento.tem_centro_neonatal IS 'Sinalizador 1 quando possui centro neonatal'",
    "COMMENT ON COLUMN slv_estabelecimento.tem_atividade_ensino IS 'Sinalizador 1 quando a unidade tem atividade de ensino ou pesquisa registrada no CNES'",
    "COMMENT ON COLUMN slv_estabelecimento.turno_atendimento IS 'Turno de funcionamento declarado, identifica unidades de plantao 24 horas'",
    "COMMENT ON COLUMN slv_cnes_leitos.no_bairro IS 'Bairro do endereco do estabelecimento, conforme cadastro CNES'",
    "COMMENT ON COLUMN slv_cnes_leitos.co_cep IS 'CEP do estabelecimento'",
    "COMMENT ON COLUMN slv_cnes_leitos.zona IS 'Zona da capital derivada do prefixo do CEP: Centro, Zona Norte, Zona Leste, Zona Sul, Zona Oeste ou Extremo Leste'",
    "COMMENT ON COLUMN slv_internacao.competencia IS 'Competencia de faturamento no formato AAAAMM'",
    "COMMENT ON COLUMN slv_internacao.qt_diarias IS 'Quantidade de diarias faturadas na internacao'",
    "COMMENT ON COLUMN slv_internacao.val_uti IS 'Valor faturado referente a UTI, em reais'",
    "COMMENT ON COLUMN slv_internacao.sexo IS 'Sexo do paciente: M, F ou IGN quando ignorado'",
    "COMMENT ON COLUMN slv_internacao.procedimento IS 'Codigo do procedimento realizado, tabela SIGTAP'",
    "COMMENT ON COLUMN slv_ocupacao.co_cnes IS 'Codigo CNES do hospital, 7 digitos'",
    "COMMENT ON COLUMN slv_ocupacao.competencia IS 'Competencia no formato AAAAMM'",
    "COMMENT ON COLUMN slv_ocupacao.nome_estabelecimento IS 'Nome do hospital conforme cadastro CNES'",
    "COMMENT ON COLUMN slv_ocupacao.ds_tipo_unidade IS 'Tipo da unidade: hospital geral, especializado, pronto socorro e outros'",
    "COMMENT ON COLUMN slv_cnes_leitos.cnes IS 'Codigo CNES do estabelecimento, 7 digitos'",
    "COMMENT ON COLUMN slv_cnes_leitos.competencia IS 'Competencia no formato AAAAMM'",
    "COMMENT ON COLUMN slv_cnes_leitos.nome_estabelecimento IS 'Nome do estabelecimento conforme cadastro CNES'",
    "COMMENT ON COLUMN slv_cnes_leitos.razao_social IS 'Razao social da mantenedora'",
    "COMMENT ON COLUMN slv_cnes_leitos.tp_gestao IS 'Tipo de gestao: M municipal, E estadual, D dupla'",
    "COMMENT ON COLUMN slv_cnes_leitos.desc_natureza_juridica IS 'Natureza juridica: publico, privado, filantropico e outros'",
    "COMMENT ON COLUMN slv_cnes_leitos.uti_adulto_sus IS 'Leitos de UTI adulto disponibilizados ao SUS'",
    "COMMENT ON COLUMN slv_cnes_leitos.uti_pediatrico_sus IS 'Leitos de UTI pediatrica disponibilizados ao SUS'",
    "COMMENT ON COLUMN slv_cnes_leitos.uti_neonatal_sus IS 'Leitos de UTI neonatal disponibilizados ao SUS'",
    "COMMENT ON COLUMN slv_sih_diasperm.co_cnes IS 'Codigo CNES do hospital, 7 digitos'",
    "COMMENT ON COLUMN slv_sih_diasperm.competencia IS 'Competencia no formato AAAAMM'",
    "COMMENT ON COLUMN slv_sih_diasperm.no_estabelecimento IS 'Nome do hospital conforme o TabNet'",
    "COMMENT ON COLUMN dim_cid.ds_cid_abrev IS 'Descricao abreviada do diagnostico'",
    "COMMENT ON COLUMN dim_cid.nr_capitulo IS 'Numero do capitulo da CID-10, de 1 a 22'",
    "COMMENT ON TABLE slv_internacao IS 'Microdados de internacao (AIH) do SIH padronizados: recorte Sao Paulo capital, tipos convertidos e dominios decodificados. Grao: uma internacao'",
    "COMMENT ON COLUMN slv_internacao.co_cnes IS 'Codigo CNES do hospital, 7 digitos com zeros a esquerda'",
    "COMMENT ON COLUMN slv_internacao.competencia IS 'Competencia de faturamento no formato AAAAMM'",
    "COMMENT ON COLUMN slv_internacao.n_aih IS 'Numero da Autorizacao de Internacao Hospitalar'",
    "COMMENT ON COLUMN slv_internacao.dt_internacao IS 'Data de entrada do paciente'",
    "COMMENT ON COLUMN slv_internacao.dt_saida IS 'Data de alta ou obito'",
    "COMMENT ON COLUMN slv_internacao.dias_perm IS 'Dias de permanencia da internacao'",
    "COMMENT ON COLUMN slv_internacao.diarias_uti IS 'Quantidade de diarias em UTI'",
    "COMMENT ON COLUMN slv_internacao.val_total IS 'Valor total faturado da internacao em reais'",
    "COMMENT ON COLUMN slv_internacao.idade_anos IS 'Idade do paciente em anos, normalizada a partir do codigo de idade do SIH'",
    "COMMENT ON COLUMN slv_internacao.fl_obito IS 'Sinalizador 1 quando a internacao terminou em obito'",
    "COMMENT ON COLUMN slv_internacao.cid_principal IS 'Diagnostico principal em CID-10, sem ponto. Cruza com DIM_CID'",
    "COMMENT ON COLUMN slv_internacao.complexidade IS 'Complexidade do procedimento: MEDIA, ALTA ou OUTRA'",
    "COMMENT ON COLUMN slv_internacao.carater_internacao IS 'Carater da internacao: ELETIVO, URGENCIA ou OUTRO'",

    "COMMENT ON TABLE slv_ocupacao IS 'Taxa de ocupacao por hospital e competencia: cruzamento de paciente-dia do SIH com leito-dia do CNES. Grao: um hospital por mes'",
    "COMMENT ON COLUMN slv_ocupacao.paciente_dia IS 'Soma dos dias de permanencia no mes, vem do TabNet'",
    "COMMENT ON COLUMN slv_ocupacao.leito_dia IS 'Leitos SUS multiplicados pelos dias do mes'",
    "COMMENT ON COLUMN slv_ocupacao.taxa_ocupacao IS 'Percentual: paciente_dia dividido por leito_dia vezes 100'",

    "COMMENT ON TABLE slv_cnes_leitos IS 'Leitos por estabelecimento e competencia, recorte do municipio de Sao Paulo (IBGE 355030). Grao: um estabelecimento por mes'",
    "COMMENT ON COLUMN slv_cnes_leitos.leitos_sus IS 'Leitos disponibilizados ao SUS'",
    "COMMENT ON COLUMN slv_cnes_leitos.leitos_existentes IS 'Total de leitos do estabelecimento, SUS e nao SUS'",
    "COMMENT ON COLUMN slv_cnes_leitos.uti_total_sus IS 'Leitos de UTI disponibilizados ao SUS'",
    "COMMENT ON COLUMN slv_cnes_leitos.ds_tipo_unidade IS 'Tipo da unidade: hospital geral, especializado, pronto socorro e outros'",

    "COMMENT ON TABLE slv_sih_diasperm IS 'Dias de permanencia por hospital e competencia, despivotado do TabNet da Secretaria Municipal de Saude. Grao: um hospital por mes'",
    "COMMENT ON COLUMN slv_sih_diasperm.dias_perm IS 'Soma dos dias de internacao no mes, fonte oficial agregada'",

    "COMMENT ON TABLE dim_cid IS 'Dicionario CID-10: codigo, descricao e capitulo. Fonte DATASUS'",
    "COMMENT ON COLUMN dim_cid.co_cid IS 'Codigo da subcategoria CID-10, 4 caracteres sem ponto'",
    "COMMENT ON COLUMN dim_cid.ds_cid IS 'Descricao completa do diagnostico'",
    "COMMENT ON COLUMN dim_cid.ds_capitulo IS 'Capitulo da CID-10, agrupa por sistema ou natureza da doenca'",
]

VALIDACOES = [
    ("Volume por competência", """
SELECT competencia, COUNT(*) aihs, SUM(dias_perm) paciente_dia,
       ROUND(AVG(dias_perm),1) perm_media, SUM(fl_obito) obitos
  FROM slv_internacao GROUP BY competencia ORDER BY competencia"""),

    ("Prova real RD x TabNet", """
SELECT r.competencia, r.pd_rd, t.pd_tabnet,
       ROUND(100*(r.pd_rd - t.pd_tabnet)/NULLIF(t.pd_tabnet,0),1) AS dif_pct
  FROM (SELECT competencia, SUM(dias_perm) pd_rd
          FROM slv_internacao GROUP BY competencia) r
  JOIN (SELECT competencia, SUM(dias_perm) pd_tabnet
          FROM slv_sih_diasperm GROUP BY competencia) t
    ON t.competencia = r.competencia
 ORDER BY r.competencia"""),
]


def main():
    conn = get_connection()
    print(f"Conectado: {conn.version}")

    with conn.cursor() as cur:
        for nome, sql in TRANSFORMACOES:
            print(f"→ {nome} ...", end=" ")
            cur.execute(sql)
            print("OK")

        print(f"→ aplicando {len(COMENTARIOS)} comentarios ...", end=" ")
        ok = 0
        for c in COMENTARIOS:
            try:
                cur.execute(c)
                ok += 1
            except Exception as e:
                print(f"\n   aviso: {c[:60]}... -> {e}")
        print(f"{ok}/{len(COMENTARIOS)} OK")

        print(f"→ aplicando {len(CHAVES)} chaves (PK/FK) ...", end=" ")
        ok_ch = 0
        for c in CHAVES:
            try:
                cur.execute(c)
                ok_ch += 1
            except Exception as e:
                print(f"\n   aviso: {c[:55]}... -> {e}")
        print(f"{ok_ch}/{len(CHAVES)} OK")

        # annotations sao recurso do 23ai/26ai; se a versao nao suportar,
        # o script segue (os comentarios ja cobrem a documentacao)
        print(f"→ aplicando {len(ANOTACOES)} annotations ...", end=" ")
        ok_an = 0
        for a in ANOTACOES:
            try:
                cur.execute(a)
                ok_an += 1
            except Exception as e:
                print(f"\n   aviso: {e}")
        print(f"{ok_an}/{len(ANOTACOES)} OK")
    conn.commit()

    for nome, sql in VALIDACOES:
        print(f"\n=== {nome} ===")
        print(pd.read_sql(sql, conn).to_string(index=False))

    conn.close()


if __name__ == "__main__":
    main()
