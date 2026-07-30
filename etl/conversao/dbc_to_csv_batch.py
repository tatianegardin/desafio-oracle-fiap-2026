"""
Converte em lote todos os arquivos .dbc do DATASUS para .csv.
Percorre as pastas informadas (recursivamente) e gera um .csv ao lado de cada .dbc.

Dependências: pip install dbc-to-dbf dbfread
Uso:
    python dbc_to_csv_batch.py
    python dbc_to_csv_batch.py "pasta1" "pasta2"
"""

import csv
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

from dbctodbf import DBCDecompress
from dbfread import DBF

# Pastas padrão (relativas a este script) usadas se nenhum argumento for passado
PASTAS_PADRAO = [
    "dados-para-converter/arquivo (1)",
    "dados-para-converter/arquivo (2)",
]


def dbc_to_csv(dbc_path: Path, csv_path: Optional[Path] = None, encoding: str = "latin-1") -> Path:
    if csv_path is None:
        csv_path = dbc_path.with_suffix(".csv")

    with tempfile.NamedTemporaryFile(suffix=".dbf", delete=False) as tmp:
        dbf_path = tmp.name

    try:
        DBCDecompress().decompressFile(str(dbc_path), dbf_path)
        table = DBF(dbf_path, encoding=encoding, ignore_missing_memofile=True)

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=table.field_names)
            writer.writeheader()
            for record in table:
                writer.writerow(record)

        return csv_path
    finally:
        os.unlink(dbf_path)


def converter_pasta(pasta: Path) -> None:
    dbc_files = sorted(pasta.glob("*.dbc"))
    if not dbc_files:
        print(f"[{pasta}] Nenhum arquivo .dbc encontrado.")
        return

    print(f"\n=== Pasta: {pasta} ({len(dbc_files)} arquivo(s)) ===")
    for dbc_file in dbc_files:
        csv_file = dbc_file.with_suffix(".csv")
        try:
            print(f"  Convertendo {dbc_file.name} -> {csv_file.name} ...")
            dbc_to_csv(dbc_file, csv_file)
            print(f"    OK ({csv_file.stat().st_size:,} bytes)")
        except Exception as e:
            print(f"    ERRO ao converter {dbc_file.name}: {e}")


def main():
    args = sys.argv[1:]
    pastas = args if args else PASTAS_PADRAO

    script_dir = Path(__file__).resolve().parent
    for pasta_str in pastas:
        pasta = Path(pasta_str)
        if not pasta.is_absolute():
            pasta = script_dir / pasta
        if not pasta.is_dir():
            print(f"Pasta não encontrada: {pasta}")
            continue
        converter_pasta(pasta)


if __name__ == "__main__":
    main()
