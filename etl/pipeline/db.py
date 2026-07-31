"""
Conexão única com o Oracle Autonomous Database via wallet.
Usada por prata_transform.py, ouro_transform.py e o notebook do K-Means.

Variáveis de ambiente esperadas (ver .env.example):
    ADB_USER      usuário/schema (ex.: ADMIN)
    ADB_PASSWORD  senha do usuário acima
    ADB_DSN       alias de tnsnames.ora (ex.: hospcheck_medium)
"""

import os

import oracledb

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WALLET_DIR = os.path.join(BASE_DIR, "wallet")


def _load_env_file(path):
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


_load_env_file(os.path.join(BASE_DIR, ".env"))


def get_connection():
    return oracledb.connect(
        user=os.environ["ADB_USER"],
        password=os.environ["ADB_PASSWORD"],
        dsn=os.environ["ADB_DSN"],
        config_dir=WALLET_DIR,
        wallet_location=WALLET_DIR,
        wallet_password=os.environ.get("ADB_WALLET_PASSWORD") or None,
    )
