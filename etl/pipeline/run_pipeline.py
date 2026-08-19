"""
HOSPCHECK SP — orquestrador do pipeline.

Executa as etapas na ordem correta de dependencia:

    API    -> BRZ_CNES_API_RAW (cadastro do CNES em JSON)
    Prata  -> tabelas SLV_* (recorte capital, tipos, dominios)
    Ouro   -> views GLD_* + comentarios + annotations
    Modelo -> K-Means, grava GLD_CLUSTER
              (a GLD_FATORES_HOSPITAL so retorna dados depois desta etapa)

A Bronze dos CSVs nao entra aqui: e carregada uma vez por competencia
via DBMS_CLOUD.COPY_DATA (ver sql/bronze/). A etapa "api" complementa
essa Bronze com o cadastro em JSON e depende dela — por isso e a
primeira do pipeline.

Uso, a partir desta pasta (etl/pipeline):

    python run_pipeline.py                # tudo
    python run_pipeline.py --ouro         # so a camada Ouro
    python run_pipeline.py --api          # so a ingestao da API
    python run_pipeline.py --prata --ouro # Prata e Ouro, sem o modelo
    python run_pipeline.py --sem-modelo   # tudo menos o K-Means

Tambem roda de qualquer lugar, ex.: python etl/pipeline/run_pipeline.py

Requer o .env preenchido nesta pasta (ver .env.example).
"""

import argparse
import runpy
import sys
import time
from pathlib import Path

PIPELINE = Path(__file__).resolve().parent
RAIZ = PIPELINE.parent.parent

ETAPAS = [
    ("api",    PIPELINE / "bronze_api_cnes.py", "API CNES -> Bronze (cadastro em JSON)"),
    ("prata",  PIPELINE / "prata_transform.py", "Bronze -> Prata (tabelas SLV_*)"),
    ("ouro",   PIPELINE / "ouro_transform.py",  "Prata -> Ouro (views GLD_*, comentarios, annotations)"),
    ("modelo", RAIZ / "analytics" / "kmeans.py", "K-Means -> GLD_CLUSTER"),
]


def carregar_env() -> None:
    """Le o .env de etl/pipeline sem exigir python-dotenv."""
    env = PIPELINE / ".env"
    if not env.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env)
    except ImportError:
        import os
        for linha in env.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


def executar(caminho: Path, descricao: str) -> float:
    print("\n" + "=" * 70)
    print(f"  {descricao}")
    print(f"  {caminho.relative_to(RAIZ)}")
    print("=" * 70)
    inicio = time.time()
    # os scripts importam db.py, que vive em etl/pipeline
    if str(PIPELINE) not in sys.path:
        sys.path.insert(0, str(PIPELINE))
    runpy.run_path(str(caminho), run_name="__main__")
    return time.time() - inicio


def main() -> int:
    p = argparse.ArgumentParser(description="Pipeline HOSPCHECK SP")
    p.add_argument("--api",    action="store_true", help="ingestao da API do CNES (JSON)")
    p.add_argument("--prata",  action="store_true", help="camada Prata")
    p.add_argument("--ouro",   action="store_true", help="camada Ouro")
    p.add_argument("--modelo", action="store_true", help="K-Means")
    p.add_argument("--sem-modelo", action="store_true", help="tudo menos o K-Means")
    args = p.parse_args()

    escolhidas = {n for n in ("api", "prata", "ouro", "modelo") if getattr(args, n)}
    if not escolhidas:
        escolhidas = ({"api", "prata", "ouro"} if args.sem_modelo
                      else {"api", "prata", "ouro", "modelo"})

    carregar_env()

    tempos = []
    for nome, caminho, descricao in ETAPAS:
        if nome not in escolhidas:
            continue
        if not caminho.exists():
            print(f"\n[erro] nao encontrado: {caminho}")
            return 1
        try:
            tempos.append((descricao, executar(caminho, descricao)))
        except Exception as e:
            print(f"\n[falhou] {descricao}: {e}")
            print("As etapas seguintes nao foram executadas.")
            return 1

    print("\n" + "=" * 70)
    print("  Concluido")
    for descricao, seg in tempos:
        print(f"    {seg:6.1f}s  {descricao}")
    print("=" * 70)
    if "modelo" not in escolhidas:
        print("\nNota: o K-Means nao rodou. A GLD_FATORES_HOSPITAL continua")
        print("com os clusters da execucao anterior.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
