"""
HOSPCHECK SP — Camada OURO (métricas de negócio)
Cria as views consumidas pelo APEX (M1), K-Means (M2) e Select AI (M3):

  GLD_OCUPACAO_MENSAL    taxa por hospital x mês + semáforo + tendência
  GLD_FEATURES_HOSPITAL  1 linha por hospital: features para o K-Means

Views (não tabelas): sempre refletem a Prata atual, sem recarga.
Uso: set -a; source .env; set +a && python ouro_transform.py
"""

import pandas as pd

from db import get_connection

VIEWS = [
    ("GLD_OCUPACAO_MENSAL", """
CREATE OR REPLACE VIEW gld_ocupacao_mensal AS
SELECT o.co_cnes,
       o.nome_estabelecimento,
       o.ds_tipo_unidade,
       o.competencia,
       o.paciente_dia,
       o.leito_dia,
       o.taxa_ocupacao,
       CASE
         WHEN o.taxa_ocupacao > 85 THEN 'CRITICO'
         WHEN o.taxa_ocupacao >= 70 THEN 'ATENCAO'
         ELSE 'OK'
       END AS semaforo,
       ROUND(o.taxa_ocupacao
             - LAG(o.taxa_ocupacao)
                 OVER (PARTITION BY o.co_cnes ORDER BY o.competencia), 1)
         AS var_vs_mes_anterior,
       ROUND(AVG(o.taxa_ocupacao)
               OVER (PARTITION BY o.co_cnes ORDER BY o.competencia
                     ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 1)
         AS media_movel_3m,
       RANK() OVER (PARTITION BY o.competencia
                    ORDER BY o.taxa_ocupacao DESC)
         AS ranking_no_mes
  FROM slv_ocupacao o"""),

    ("GLD_FEATURES_HOSPITAL", """
CREATE OR REPLACE VIEW gld_features_hospital AS
WITH ocup AS (
  SELECT co_cnes,
         ROUND(AVG(taxa_ocupacao), 1)    AS taxa_media,
         ROUND(MAX(taxa_ocupacao), 1)    AS taxa_max,
         ROUND(STDDEV(taxa_ocupacao), 1) AS taxa_desvio,
         COUNT(*)                        AS meses_com_dado
    FROM slv_ocupacao
   GROUP BY co_cnes
),
clin AS (
  SELECT co_cnes,
         ROUND(AVG(dias_perm), 1)                                    AS perm_media,
         ROUND(100 * SUM(diarias_uti) / NULLIF(SUM(dias_perm),0), 1) AS pct_diarias_uti,
         ROUND(100 * AVG(CASE WHEN carater_internacao = 'URGENCIA'
                              THEN 1 ELSE 0 END), 1)                 AS pct_urgencia,
         ROUND(100 * AVG(CASE WHEN complexidade = 'ALTA'
                              THEN 1 ELSE 0 END), 1)                 AS pct_alta_complex,
         ROUND(100 * AVG(fl_obito), 2)                               AS tx_mortalidade,
         ROUND(AVG(idade_anos), 1)                                   AS idade_media,
         COUNT(*)                                                    AS total_aihs
    FROM slv_internacao
   GROUP BY co_cnes
),
cap AS (
  SELECT cnes,
         ROUND(AVG(leitos_sus))    AS leitos_sus,
         ROUND(AVG(uti_total_sus)) AS leitos_uti_sus,
         MAX(ds_tipo_unidade)      AS tipo_unidade
    FROM slv_cnes_leitos
   GROUP BY cnes
)
SELECT o.co_cnes,
       h.nome_estabelecimento,
       cap.tipo_unidade,
       cap.leitos_sus,
       cap.leitos_uti_sus,
       o.taxa_media, o.taxa_max, o.taxa_desvio, o.meses_com_dado,
       c.perm_media, c.pct_diarias_uti, c.pct_urgencia,
       c.pct_alta_complex, c.tx_mortalidade, c.idade_media, c.total_aihs
  FROM ocup o
  JOIN (SELECT DISTINCT co_cnes, nome_estabelecimento FROM slv_ocupacao) h
    ON h.co_cnes = o.co_cnes
  LEFT JOIN clin c   ON c.co_cnes = o.co_cnes
  LEFT JOIN cap      ON cap.cnes  = o.co_cnes"""),
]

VALIDACOES = [
    ("Semáforo na última competência", """
SELECT semaforo, COUNT(*) hospitais
  FROM gld_ocupacao_mensal
 WHERE competencia = (SELECT MAX(competencia) FROM gld_ocupacao_mensal)
 GROUP BY semaforo ORDER BY semaforo"""),

    ("Top 10 críticos (última competência)", """
SELECT ranking_no_mes, nome_estabelecimento, taxa_ocupacao,
       var_vs_mes_anterior, media_movel_3m
  FROM gld_ocupacao_mensal
 WHERE competencia = (SELECT MAX(competencia) FROM gld_ocupacao_mensal)
 ORDER BY ranking_no_mes
 FETCH FIRST 10 ROWS ONLY"""),

    ("Features do K-Means (amostra)", """
SELECT co_cnes, nome_estabelecimento, leitos_sus, taxa_media,
       perm_media, pct_urgencia, pct_alta_complex
  FROM gld_features_hospital
 ORDER BY taxa_media DESC
 FETCH FIRST 5 ROWS ONLY"""),
]


def main():
    conn = get_connection()
    print(f"Conectado: {conn.version}")

    with conn.cursor() as cur:
        for nome, sql in VIEWS:
            print(f"→ criando {nome} ...", end=" ")
            cur.execute(sql)
            print("OK")

    for nome, sql in VALIDACOES:
        print(f"\n=== {nome} ===")
        print(pd.read_sql(sql, conn).to_string(index=False))

    conn.close()


if __name__ == "__main__":
    main()
