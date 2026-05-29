from __future__ import annotations

import os
import sqlite3
import threading
import time
from typing import Any


DB_PATH = ""
DATA_VERSION_STAT_TTL_SECONDS = 0.5
DB_WRITE_LOCK = threading.Lock()
_DB_LOCAL = threading.local()
_DATA_CACHE_LOCK = threading.Lock()
_DATA_VERSION = 0
_DB_FILE_STATE_TOKEN: tuple[tuple[str, int, int], ...] | None = None
_DB_FILE_STATE_STAT_TOKEN: tuple[tuple[str, int, int], ...] | None = None
_DB_FILE_STATE_STAT_CHECKED_AT = 0.0


def configure(*, db_path: str) -> None:
    global DB_PATH, _DB_FILE_STATE_TOKEN, _DB_FILE_STATE_STAT_TOKEN, _DB_FILE_STATE_STAT_CHECKED_AT
    _discard_thread_db_connection()
    with _DATA_CACHE_LOCK:
        DB_PATH = os.path.abspath(str(db_path or ""))
        _DB_FILE_STATE_TOKEN = None
        _DB_FILE_STATE_STAT_TOKEN = None
        _DB_FILE_STATE_STAT_CHECKED_AT = 0.0


def _db_state_token() -> tuple[tuple[str, int, int], ...]:
    token: list[tuple[str, int, int]] = []
    for path in (DB_PATH, f"{DB_PATH}-wal", f"{DB_PATH}-shm"):
        try:
            stat = os.stat(path)
            token.append((path, int(stat.st_mtime_ns), int(stat.st_size)))
        except OSError:
            token.append((path, 0, 0))
    return tuple(token)


def _cached_db_state_token() -> tuple[tuple[str, int, int], ...]:
    global _DB_FILE_STATE_STAT_TOKEN, _DB_FILE_STATE_STAT_CHECKED_AT
    now = time.monotonic()
    with _DATA_CACHE_LOCK:
        cached = _DB_FILE_STATE_STAT_TOKEN
        if cached is not None and (now - _DB_FILE_STATE_STAT_CHECKED_AT) < DATA_VERSION_STAT_TTL_SECONDS:
            return cached

        token = _db_state_token()
        _DB_FILE_STATE_STAT_TOKEN = token
        _DB_FILE_STATE_STAT_CHECKED_AT = now
        return token


def bump_data_version() -> int:
    global _DATA_VERSION, _DB_FILE_STATE_TOKEN, _DB_FILE_STATE_STAT_TOKEN, _DB_FILE_STATE_STAT_CHECKED_AT
    current_token = _db_state_token()
    checked_at = time.monotonic()
    with _DATA_CACHE_LOCK:
        _DATA_VERSION += 1
        _DB_FILE_STATE_TOKEN = current_token
        _DB_FILE_STATE_STAT_TOKEN = current_token
        _DB_FILE_STATE_STAT_CHECKED_AT = checked_at
        return _DATA_VERSION


def _current_data_version() -> int:
    global _DATA_VERSION, _DB_FILE_STATE_TOKEN
    current_token = _cached_db_state_token()
    with _DATA_CACHE_LOCK:
        if _DB_FILE_STATE_TOKEN is None:
            _DB_FILE_STATE_TOKEN = current_token
        elif current_token != _DB_FILE_STATE_TOKEN:
            _DB_FILE_STATE_TOKEN = current_token
            _DATA_VERSION += 1
        return int(_DATA_VERSION)


def _create_db_connection() -> sqlite3.Connection:
    if not DB_PATH:
        raise RuntimeError("Database path is not configured.")
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except sqlite3.OperationalError as ex:
        if "locked" not in str(ex).casefold():
            conn.close()
            raise
    try:
        conn.execute("PRAGMA synchronous=NORMAL;")
    except sqlite3.OperationalError as ex:
        if "locked" not in str(ex).casefold():
            conn.close()
            raise
    return conn


def _db_connection_alive(conn: sqlite3.Connection | None) -> bool:
    if conn is None:
        return False
    try:
        conn.execute("SELECT 1;")
        return True
    except Exception:
        return False


def _discard_thread_db_connection() -> None:
    conn = getattr(_DB_LOCAL, "conn", None)
    try:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
            conn.close()
    except Exception:
        pass
    try:
        delattr(_DB_LOCAL, "conn")
    except Exception:
        setattr(_DB_LOCAL, "conn", None)


def get_conn() -> sqlite3.Connection:
    conn = getattr(_DB_LOCAL, "conn", None)
    if not _db_connection_alive(conn):
        _discard_thread_db_connection()
        conn = _create_db_connection()
        setattr(_DB_LOCAL, "conn", conn)
    return conn


def db_exec(
    sql: str,
    params: tuple[Any, ...] = (),
    *,
    fetch: bool = False,
    fetchone: bool = False,
    commit: bool = False,
):
    conn = get_conn()
    sql_head = (sql or "").strip().split(None, 1)
    verb = sql_head[0].upper() if sql_head else ""
    is_write = commit or verb in {
        "INSERT",
        "UPDATE",
        "DELETE",
        "REPLACE",
        "CREATE",
        "ALTER",
        "DROP",
        "BEGIN",
        "COMMIT",
        "ROLLBACK",
        "VACUUM",
    }
    lock = DB_WRITE_LOCK if is_write else threading.Lock()
    with lock:
        cur = conn.cursor()
        close_conn = False
        try:
            for attempt in range(4):
                try:
                    cur.execute(sql, params)
                    break
                except sqlite3.OperationalError as ex:
                    if "locked" not in str(ex).casefold() or attempt >= 3:
                        raise
                    time.sleep(1.0 + attempt)
            rowcount = cur.rowcount
            if commit and verb not in {"COMMIT", "ROLLBACK"}:
                conn.commit()
                if verb in {"INSERT", "UPDATE", "DELETE", "REPLACE"}:
                    try:
                        if int(rowcount) != 0:
                            bump_data_version()
                    except Exception:
                        bump_data_version()
            if fetchone:
                return cur.fetchone()
            if fetch:
                return cur.fetchall()
            return None
        except Exception as ex:
            if is_write or bool(getattr(conn, "in_transaction", False)):
                try:
                    conn.rollback()
                except Exception:
                    pass
            close_conn = isinstance(ex, sqlite3.Error) and (is_write or not _db_connection_alive(conn))
            raise
        finally:
            cur.close()
            if close_conn:
                _discard_thread_db_connection()


def column_exists(table: str, col: str) -> bool:
    rows = db_exec(f"PRAGMA table_info({table});", fetch=True) or []
    return any(row[1] == col for row in rows)


def ensure_column(table: str, col: str, decl: str) -> None:
    if not column_exists(table, col):
        db_exec(f"ALTER TABLE {table} ADD COLUMN {col} {decl};", commit=True)
