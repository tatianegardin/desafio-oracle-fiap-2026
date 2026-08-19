"""
HOSPCHECK SP — Camada BRONZE via API (formato JSON)

Terceira fonte do desafio, em formato semiestruturado:
    SIH-RD ..... relacional  (CSV -> COPY_DATA, sql/bronze/03)
    CNES ....... JSON        (API -> este script)
    auxiliares . CSV         (sql/bronze/02 e 04)

Busca o cadastro de cada estabelecimento na API de dados abertos do
Ministerio da Saude e grava o payload EXATAMENTE como veio, sem
tratamento. O parse acontece na Prata (prata_transform.py).

Endpoint publico, sem autenticacao:
    https://apidadosabertos.saude.gov.br/cnes/estabelecimentos/{cnes}

Dependencia (Bronze -> Bronze): a lista de estabelecimentos a buscar
sai de BRZ_CNES_LEITOS_RAW, carregada do CSV. A API apenas
COMPLEMENTA cada CNES que ja existe ali — nao traz hospital novo.
Ordem: carregar os CSVs (sql/bronze/) antes de rodar este script.

O JSON traz o que o CSV de leitos nao tem: latitude e longitude
(habilitam mapa), centro cirurgico, centro obstetrico, centro
neonatal, atividade de ensino, turno de atendimento e bairro.

Uso, a partir da raiz do repositorio:
    python run_pipeline.py --api      # so esta etapa
    python run_pipeline.py            # pipeline completo
"""

import json
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from db import get_connection

API = "https://apidadosabertos.saude.gov.br/cnes/estabelecimentos/{}"
TIMEOUT = 20
TENTATIVAS = 3
PARALELISMO = 5      # gentil com uma API publica

DDL = """
CREATE TABLE brz_cnes_api_raw (
  co_cnes      VARCHAR2(7) PRIMARY KEY,
  payload      CLOB,
  http_status  NUMBER,
  data_carga   DATE DEFAULT SYSDATE,
  CONSTRAINT ck_brz_cnes_api_json CHECK (payload IS JSON)
)
"""

COMENTARIOS = [
    "COMMENT ON TABLE brz_cnes_api_raw IS 'Cadastro de estabelecimentos vindo da API de dados abertos do CNES, em JSON, como recebido. Fonte semiestruturada do desafio'",
    "COMMENT ON COLUMN brz_cnes_api_raw.co_cnes IS 'Codigo CNES do estabelecimento, 7 digitos'",
    "COMMENT ON COLUMN brz_cnes_api_raw.payload IS 'Documento JSON retornado pela API, sem tratamento'",
    "COMMENT ON COLUMN brz_cnes_api_raw.http_status IS 'Codigo HTTP da resposta; apenas 200 e considerado na Prata'",
]


def buscar(co_cnes: str):
    """Uma chamada a API, com tentativas. Devolve (cnes, status, corpo)."""
    url = API.format(int(co_cnes))
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            req = urllib.request.Request(
                url, headers={"Accept": "application/json",
                              "User-Agent": "HOSPCHECK-SP/1.0 (FIAP Oracle Challenge)"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                corpo = r.read().decode("utf-8")
                json.loads(corpo)          # valida antes de gravar
                return co_cnes, r.status, corpo
        except urllib.error.HTTPError as e:
            return co_cnes, e.code, None   # 404 e resposta legitima, nao adianta repetir
        except Exception:
            if tentativa == TENTATIVAS:
                return co_cnes, None, None
    return co_cnes, None, None


def main():
    conn = get_connection()
    print(f"Conectado: {conn.version}")

    with conn.cursor() as cur:
        # tabela (idempotente)
        try:
            cur.execute(DDL)
            print("→ tabela brz_cnes_api_raw criada")
        except Exception as e:
            if "ORA-00955" in str(e):       # ja existe
                print("→ tabela brz_cnes_api_raw ja existe")
            else:
                raise

        # universo: o que veio do CSV de leitos
        cur.execute("""
            SELECT DISTINCT LPAD(cnes, 7, '0')
              FROM brz_cnes_leitos_raw
             WHERE co_ibge = '355030'
               AND NVL(leitos_sus, 0) > 0
             ORDER BY 1
        """)
        cnes = [linha[0] for linha in cur.fetchall()]

    print(f"→ estabelecimentos a consultar: {len(cnes)}")

    resultados, falhas = [], 0
    with ThreadPoolExecutor(max_workers=PARALELISMO) as pool:
        for i, (co, status, corpo) in enumerate(pool.map(buscar, cnes), 1):
            if status == 200 and corpo:
                resultados.append({"co_cnes": co, "payload": corpo, "http_status": status})
            else:
                falhas += 1
            if i % 25 == 0 or i == len(cnes):
                print(f"   {i}/{len(cnes)} consultados", end="\r")

    print(f"\n→ respostas validas: {len(resultados)} | falhas: {falhas}")

    with conn.cursor() as cur:
        # binds nomeados (nao :1/:2/:3): payload e http_status se repetem
        # no MERGE. Cada linha precisa ser um DICT (nao tupla) para o
        # oracledb reaproveitar o mesmo valor nas ocorrencias repetidas
        # do bind — com tupla ele conta ocorrencia por ocorrencia (5 em
        # vez de 3) e falha com DPY-4009.
        # Sem setinputsizes: payload e CLOB com CHECK (... IS JSON) e o
        # hint de tamanho (32767) faz o driver travar em ORA-03106. Os
        # payloads sao pequenos (~2KB), o driver infere o tipo sozinho.
        cur.executemany("""
            MERGE INTO brz_cnes_api_raw t
            USING (SELECT :co_cnes AS co_cnes FROM dual) s
               ON (t.co_cnes = s.co_cnes)
             WHEN MATCHED THEN
               UPDATE SET payload = :payload, http_status = :http_status, data_carga = SYSDATE
             WHEN NOT MATCHED THEN
               INSERT (co_cnes, payload, http_status) VALUES (s.co_cnes, :payload, :http_status)
        """, resultados)

        for c in COMENTARIOS:
            try:
                cur.execute(c)
            except Exception as e:
                print(f"   aviso no comentario: {e}")

    conn.commit()

    # validacao
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*),
                   COUNT(CASE WHEN JSON_VALUE(payload,
                         '$.latitude_estabelecimento_decimo_grau') IS NOT NULL THEN 1 END),
                   COUNT(CASE WHEN JSON_VALUE(payload,
                         '$.estabelecimento_possui_centro_cirurgico') = '1' THEN 1 END)
              FROM brz_cnes_api_raw
        """)
        total, com_coord, com_cirurgico = cur.fetchone()

    print(f"\n=== BRZ_CNES_API_RAW ===")
    print(f"  estabelecimentos gravados : {total}")
    print(f"  com coordenada geografica : {com_coord}")
    print(f"  com centro cirurgico      : {com_cirurgico}")

    conn.close()


if __name__ == "__main__":
    main()
