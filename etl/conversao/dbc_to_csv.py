"""
Converte arquivos .dbc do DATASUS para .csv
Dependências: pip install dbc-to-dbf dbfread
"""

import csv
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

from dbctodbf import DBCDecompress
from dbfread import DBF


def dbc_to_csv(dbc_path: str, csv_path: Optional[str] = None, encoding: str = "latin-1") -> str:
    dbc_path = Path(dbc_path)
    if not dbc_path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {dbc_path}")

    if csv_path is None:
        csv_path = dbc_path.with_suffix(".csv")
    csv_path = Path(csv_path)

    with tempfile.NamedTemporaryFile(suffix=".dbf", delete=False) as tmp:
        dbf_path = tmp.name

    try:
        print(f"Descomprimindo {dbc_path.name} → DBF temporário...")
        DBCDecompress().decompressFile(str(dbc_path), dbf_path)

        print("Lendo DBF e convertendo para CSV...")
        table = DBF(dbf_path, encoding=encoding, ignore_missing_memofile=True)

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=table.field_names)
            writer.writeheader()
            for record in table:
                writer.writerow(record)

        print(f"CSV gerado: {csv_path}  ({csv_path.stat().st_size:,} bytes)")
        return str(csv_path)

    finally:
        os.unlink(dbf_path)


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        # padrão: converte o arquivo DBC do diretório atual
        dbc_files = list(Path(".").glob("*.dbc"))
        if not dbc_files:
            print("Uso: python dbc_to_csv.py arquivo.dbc [saida.csv]")
            sys.exit(1)
        dbc_file = dbc_files[0]
        print(f"Arquivo encontrado automaticamente: {dbc_file}")
    else:
        dbc_file = args[0]

    output = args[1] if len(args) > 1 else None
    dbc_to_csv(dbc_file, output)
