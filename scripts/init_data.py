"""
Inicializa el Mock HIS (SQLite) y el índice vectorial de manuales (ChromaDB).

Uso:
    python scripts/init_data.py           # crea lo que falte, conserva reservas e historial
    python scripts/init_data.py --reset   # BORRA reservas, memoria y traza, y reindexa los manuales
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import DB_PATH
from src.rag_engine import RAGEngine
from src.tools_agenda import get_db_connection, init_database


def main() -> None:
    parser = argparse.ArgumentParser(description="Inicializa BD SQLite e índice vectorial de SaludConecta")
    parser.add_argument("--reset", action="store_true", help="borra reservas, memoria y traza; reindexa manuales")
    args = parser.parse_args()

    init_database(force_reset=args.reset)
    engine = RAGEngine(force_reindex=args.reset)

    conn = get_db_connection()
    citas = conn.execute("SELECT COUNT(*) FROM citas").fetchone()[0]
    pacientes = conn.execute("SELECT COUNT(*) FROM pacientes").fetchone()[0]
    conn.close()

    print(f"SQLite: {DB_PATH} | {citas} cupos | {pacientes} pacientes simulados")
    print(f"ChromaDB: {engine.persist_directory} | {engine.vector_store._collection.count()} fragmentos")


if __name__ == "__main__":
    main()
