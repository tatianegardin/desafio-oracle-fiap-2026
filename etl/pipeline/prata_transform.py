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
     "BEGIN EXECUTE IMMEDIATE 'DROP TABLE slv_internacao PURGE'; "
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
     "BEGIN EXECUTE IMMEDIATE 'DROP TABLE slv_cnes_leitos PURGE'; "
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
       uti_neonatal_exist, uti_neonatal_sus
  FROM brz_cnes_leitos_raw
 WHERE co_ibge = '355030'"""),

    ("indice leitos hospital x competencia",
     "CREATE INDEX ix_slv_leitos_cnes_comp ON slv_cnes_leitos (cnes, competencia)"),

    # --- dias de permanencia (TabNet), formato largo -> longo ---
    ("drop slv_sih_diasperm (se existir)",
     "BEGIN EXECUTE IMMEDIATE 'DROP TABLE slv_sih_diasperm PURGE'; "
     "EXCEPTION WHEN OTHERS THEN IF SQLCODE != -942 THEN RAISE; END IF; END;"),

    ("criar slv_sih_diasperm", """
CREATE TABLE slv_sih_diasperm AS
SELECT LPAD(REGEXP_SUBSTR(estab_cidade, '^\\d+'), 7, '0')      AS co_cnes,
       TRIM(REGEXP_REPLACE(estab_cidade, '^\\d+\\s*', ''))      AS no_estabelecimento,
       competencia,
       TO_NUMBER(dias)                                        AS dias_perm
  FROM brz_sih_tabnet_raw
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
     "BEGIN EXECUTE IMMEDIATE 'DROP TABLE slv_ocupacao PURGE'; "
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
    conn.commit()

    for nome, sql in VALIDACOES:
        print(f"\n=== {nome} ===")
        print(pd.read_sql(sql, conn).to_string(index=False))

    conn.close()


if __name__ == "__main__":
    main()
