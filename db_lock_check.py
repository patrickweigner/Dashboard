from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.config import DB_PATH


def main() -> int:
    try:
        conn = sqlite3.connect(DB_PATH, timeout=2.0)
        try:
            conn.execute("PRAGMA busy_timeout=2000;")
            conn.execute("BEGIN IMMEDIATE;")
            conn.rollback()
        finally:
            conn.close()
    except sqlite3.OperationalError as exc:
        if "locked" in str(exc).casefold():
            print(f'[FEHLER] SQLite-Datenbank ist gesperrt: "{DB_PATH}"')
            return 2
        print(f"[FEHLER] SQLite-Pruefung fehlgeschlagen: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
