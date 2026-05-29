from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Iterator

from core.config import DB_PATH

from .models import (
    DEFAULT_CAPACITY_SLOTS,
    DEFAULT_PLACES,
    coerce_job_status,
    coerce_priority,
    detect_vehicle_type,
    normalize_friststufe,
    normalize_place_code,
    normalize_slot_label,
    normalize_vehicle_type_code,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_LOCAL = threading.local()


def default_db_path() -> str:
    env_path = str(os.getenv("FRISTEN_DB_PATH", "") or "").strip()
    if env_path:
        return os.path.abspath(env_path)
    return os.path.abspath(str(DB_PATH))


@contextmanager
def _connect(db_path: str | None = None) -> Iterator[sqlite3.Connection]:
    target_path = db_path or default_db_path()
    use_cached_connection = db_path is None
    conn: sqlite3.Connection | None = None
    if use_cached_connection:
        cached = getattr(_REPO_LOCAL, "conn", None)
        cached_path = str(getattr(_REPO_LOCAL, "path", "") or "")
        if cached is not None and cached_path == str(target_path):
            try:
                cached.execute("SELECT 1;")
                conn = cached
            except sqlite3.Error:
                try:
                    cached.close()
                except Exception:
                    pass
                conn = None
    if conn is None:
        conn = sqlite3.connect(target_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        if use_cached_connection:
            setattr(_REPO_LOCAL, "conn", conn)
            setattr(_REPO_LOCAL, "path", str(target_path))
    try:
        yield conn
    finally:
        if not use_cached_connection:
            conn.close()


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table});").fetchall()
    return {str(row["name"]) for row in rows}


def _ensure_column(conn: sqlite3.Connection, table: str, col: str, decl: str) -> None:
    if col in _table_columns(conn, table):
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl};")


def _normalize_role_key(value: Any) -> str:
    raw = str(value or "").strip().lower()
    cleaned = "".join(char if char.isalnum() else "_" for char in raw)
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_")


def _migrate_legacy_shift_staffing(conn: sqlite3.Connection) -> None:
    legacy_columns = _table_columns(conn, "planning_shift_staffing")
    if not legacy_columns:
        return
    has_values = conn.execute("SELECT COUNT(*) AS count_value FROM planning_shift_staffing_values;").fetchone()
    if has_values and int(has_values["count_value"] or 0) > 0:
        return
    legacy_rows = conn.execute(
        """
        SELECT shift_name, weekday, workshop_capacity, service_capacity, urd_capacity
        FROM planning_shift_staffing
        ORDER BY weekday ASC, shift_name ASC;
        """
    ).fetchall()
    for row in legacy_rows:
        shift_name = str(row["shift_name"] or "").strip()
        weekday = int(row["weekday"] or 0)
        for role_key, field_name in (
            ("workshop", "workshop_capacity"),
            ("service", "service_capacity"),
            ("urd", "urd_capacity"),
        ):
            conn.execute(
                """
                INSERT INTO planning_shift_staffing_values (shift_name, weekday, role_key, capacity)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(shift_name, weekday, role_key) DO UPDATE SET
                    capacity = excluded.capacity
                ;
                """,
                (shift_name, weekday, role_key, float(row[field_name] or 0.0)),
            )


def ensure_planning_schema(db_path: str | None = None) -> None:
    with _connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS planning_places (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                code        TEXT NOT NULL UNIQUE,
                label       TEXT NOT NULL,
                active      INTEGER NOT NULL DEFAULT 1,
                sort_order  INTEGER NOT NULL DEFAULT 0,
                notes       TEXT
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS planning_vehicle_types (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                code        TEXT NOT NULL UNIQUE,
                label       TEXT NOT NULL,
                active      INTEGER NOT NULL DEFAULT 1,
                notes       TEXT
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS planning_place_rules (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                vehicle_type_id  INTEGER NOT NULL,
                place_id         INTEGER NOT NULL,
                allowed          INTEGER NOT NULL DEFAULT 1,
                priority         TEXT DEFAULT 'neutral',
                reason           TEXT,
                active           INTEGER NOT NULL DEFAULT 1,
                UNIQUE(vehicle_type_id, place_id),
                FOREIGN KEY(vehicle_type_id) REFERENCES planning_vehicle_types(id),
                FOREIGN KEY(place_id) REFERENCES planning_places(id)
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS planning_time_rules (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                friststufe         TEXT NOT NULL,
                vehicle_type_id    INTEGER,
                base_minutes       INTEGER NOT NULL DEFAULT 0,
                stand_minutes_min  INTEGER NOT NULL DEFAULT 0,
                stand_factor       REAL NOT NULL DEFAULT 1.0,
                active             INTEGER NOT NULL DEFAULT 1,
                notes              TEXT,
                FOREIGN KEY(vehicle_type_id) REFERENCES planning_vehicle_types(id)
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS planning_extra_work_types (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                code        TEXT NOT NULL UNIQUE,
                label       TEXT NOT NULL,
                minutes     INTEGER NOT NULL DEFAULT 0,
                active      INTEGER NOT NULL DEFAULT 1,
                notes       TEXT
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS planning_jobs (
                id                     INTEGER PRIMARY KEY AUTOINCREMENT,
                fahrzeug               TEXT NOT NULL,
                vehicle_type_id        INTEGER,
                friststufe             TEXT,
                source_open_task_id    INTEGER,
                required_minutes       INTEGER NOT NULL DEFAULT 0,
                planned_minutes        INTEGER NOT NULL DEFAULT 0,
                required_stand_minutes INTEGER NOT NULL DEFAULT 0,
                status                 TEXT NOT NULL DEFAULT 'draft',
                notes                  TEXT,
                created_at             TEXT,
                updated_at             TEXT,
                FOREIGN KEY(vehicle_type_id) REFERENCES planning_vehicle_types(id)
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS planning_assignments (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                planning_job_id  INTEGER NOT NULL,
                place_id         INTEGER NOT NULL,
                start_dt         TEXT NOT NULL,
                end_dt           TEXT NOT NULL,
                note             TEXT,
                created_at       TEXT,
                updated_at       TEXT,
                FOREIGN KEY(planning_job_id) REFERENCES planning_jobs(id),
                FOREIGN KEY(place_id) REFERENCES planning_places(id)
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS planning_orders (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                fahrzeug          TEXT NOT NULL,
                vehicle_type_code TEXT,
                friststufe        TEXT NOT NULL,
                order_kind        TEXT,
                zusatzarbeiten    TEXT,
                gewerke_info      TEXT,
                ecm3_start_date   TEXT,
                ecm3_start_time   TEXT,
                ecm3_end_date     TEXT,
                ecm3_end_time     TEXT,
                required_ma_8h    REAL,
                planned_ma        REAL,
                ecm4_start_date   TEXT,
                ecm4_start_time   TEXT,
                ecm4_end_date     TEXT,
                ecm4_end_time     TEXT,
                ecm4_place_code   TEXT,
                status            TEXT NOT NULL DEFAULT 'draft',
                source_origin     TEXT,
                source_open_task_id INTEGER,
                source_sheet      TEXT,
                source_row_number INTEGER,
                created_at        TEXT,
                updated_at        TEXT
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS planning_slots (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                slot_date         TEXT NOT NULL,
                slot_time         TEXT NOT NULL,
                slot_start        TEXT,
                slot_end          TEXT,
                workshop_staff    REAL,
                service_staff     REAL,
                urd_staff         REAL,
                mek_value         REAL,
                vehicle_count     REAL,
                staff_per_vehicle REAL,
                notes             TEXT,
                created_at        TEXT,
                updated_at        TEXT,
                UNIQUE(slot_date, slot_time)
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS planning_slot_assignments (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                slot_id           INTEGER NOT NULL,
                place_code        TEXT NOT NULL,
                fahrzeug          TEXT,
                planning_order_id INTEGER,
                note              TEXT,
                created_at        TEXT,
                updated_at        TEXT,
                FOREIGN KEY(slot_id) REFERENCES planning_slots(id),
                FOREIGN KEY(planning_order_id) REFERENCES planning_orders(id),
                UNIQUE(slot_id, place_code)
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS planning_slot_templates (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                slot_label  TEXT NOT NULL UNIQUE,
                start_time  TEXT,
                end_time    TEXT,
                sort_order  INTEGER NOT NULL DEFAULT 0,
                active      INTEGER NOT NULL DEFAULT 1
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS planning_shift_templates (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                shift_name    TEXT NOT NULL UNIQUE,
                start_time    TEXT NOT NULL,
                end_time      TEXT NOT NULL,
                slot_count    INTEGER NOT NULL DEFAULT 1,
                sort_order    INTEGER NOT NULL DEFAULT 0,
                active        INTEGER NOT NULL DEFAULT 1
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS planning_shift_staffing (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                shift_name         TEXT NOT NULL,
                weekday            INTEGER NOT NULL,
                workshop_capacity  REAL NOT NULL DEFAULT 0,
                service_capacity   REAL NOT NULL DEFAULT 0,
                urd_capacity       REAL NOT NULL DEFAULT 0,
                UNIQUE(shift_name, weekday)
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS planning_capacity_roles (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                role_key    TEXT NOT NULL UNIQUE,
                label       TEXT NOT NULL,
                active      INTEGER NOT NULL DEFAULT 1,
                sort_order  INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS planning_shift_staffing_values (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                shift_name  TEXT NOT NULL,
                weekday     INTEGER NOT NULL,
                role_key    TEXT NOT NULL,
                capacity    REAL NOT NULL DEFAULT 0,
                UNIQUE(shift_name, weekday, role_key)
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS planning_capacity_slots (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                slot_date         TEXT NOT NULL,
                slot_label        TEXT NOT NULL,
                workshop_capacity REAL NOT NULL DEFAULT 0,
                service_capacity  REAL NOT NULL DEFAULT 0,
                urd_capacity      REAL NOT NULL DEFAULT 0,
                allocation_mode   TEXT NOT NULL DEFAULT 'auto',
                source_name       TEXT,
                notes             TEXT,
                created_at        TEXT,
                updated_at        TEXT,
                UNIQUE(slot_date, slot_label)
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS planning_ui_settings (
                setting_key   TEXT PRIMARY KEY,
                setting_value TEXT NOT NULL DEFAULT ''
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS planning_allocations (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                capacity_slot_id  INTEGER NOT NULL,
                place_code        TEXT NOT NULL,
                planning_order_id INTEGER NOT NULL,
                fahrzeug          TEXT,
                allocated_ma      REAL NOT NULL DEFAULT 0,
                note              TEXT,
                created_at        TEXT,
                updated_at        TEXT,
                FOREIGN KEY(capacity_slot_id) REFERENCES planning_capacity_slots(id),
                FOREIGN KEY(planning_order_id) REFERENCES planning_orders(id),
                UNIQUE(capacity_slot_id, place_code)
            );
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_planning_places_active ON planning_places (active, sort_order, code);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_planning_slot_templates_active ON planning_slot_templates (active, sort_order, slot_label);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_planning_shift_templates_active ON planning_shift_templates (active, sort_order, shift_name);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_planning_shift_staffing_weekday ON planning_shift_staffing (weekday, shift_name);")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_planning_shift_staffing_values_weekday ON planning_shift_staffing_values (weekday, shift_name, role_key);"
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_planning_capacity_roles_active ON planning_capacity_roles (active, sort_order, role_key);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_planning_vehicle_types_active ON planning_vehicle_types (active, code);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_planning_time_rules_lookup ON planning_time_rules (friststufe, vehicle_type_id, active);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_planning_jobs_status ON planning_jobs (status, updated_at);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_planning_assignments_slot ON planning_assignments (place_id, start_dt, end_dt);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_planning_orders_vehicle ON planning_orders (fahrzeug, friststufe, status);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_planning_slots_day ON planning_slots (slot_date, slot_time);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_planning_slot_assignments_slot ON planning_slot_assignments (slot_id, place_code);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_planning_slot_assignments_order ON planning_slot_assignments (planning_order_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_planning_capacity_slots_day ON planning_capacity_slots (slot_date, slot_label);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_planning_allocations_slot ON planning_allocations (capacity_slot_id, place_code);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_planning_allocations_order ON planning_allocations (planning_order_id);")
        _ensure_column(conn, "planning_slot_templates", "start_time", "TEXT")
        _ensure_column(conn, "planning_slot_templates", "end_time", "TEXT")
        _ensure_column(conn, "planning_capacity_slots", "allocation_mode", "TEXT NOT NULL DEFAULT 'auto'")
        _ensure_column(conn, "planning_orders", "source_origin", "TEXT")
        _ensure_column(conn, "planning_orders", "source_open_task_id", "INTEGER")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_planning_orders_source_open ON planning_orders (source_open_task_id);")
        _migrate_legacy_shift_staffing(conn)
        conn.commit()


def list_ui_settings(*, db_path: str | None = None) -> dict[str, str]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT setting_key, setting_value
            FROM planning_ui_settings
            ORDER BY setting_key ASC;
            """
        ).fetchall()
        return {str(row["setting_key"]): str(row["setting_value"]) for row in rows}


def save_ui_settings(settings: dict[str, Any], *, db_path: str | None = None) -> None:
    with _connect(db_path) as conn:
        cur = conn.cursor()
        for key, value in settings.items():
            key_txt = str(key or "").strip()
            if not key_txt:
                continue
            cur.execute(
                """
                INSERT INTO planning_ui_settings (setting_key, setting_value)
                VALUES (?, ?)
                ON CONFLICT(setting_key) DO UPDATE SET
                    setting_value = excluded.setting_value
                ;
                """,
                (key_txt, str(value)),
            )
        conn.commit()


def seed_planning_places(db_path: str | None = None) -> None:
    with _connect(db_path) as conn:
        cur = conn.cursor()
        for index, code in enumerate(DEFAULT_PLACES, start=1):
            cur.execute(
                """
                INSERT INTO planning_places (code, label, active, sort_order, notes)
                VALUES (?, ?, 1, ?, '')
                ON CONFLICT(code) DO UPDATE SET
                    label = excluded.label,
                    sort_order = excluded.sort_order
                ;
                """,
                (code, code, index),
            )
        conn.commit()


def seed_capacity_roles(db_path: str | None = None) -> None:
    defaults = [
        ("workshop", "Werkstatt", 1, 1),
        ("service", "Service", 0, 2),
        ("urd", "URD", 0, 3),
    ]
    with _connect(db_path) as conn:
        cur = conn.cursor()
        for role_key, label, active, sort_order in defaults:
            cur.execute(
                """
                INSERT INTO planning_capacity_roles (role_key, label, active, sort_order)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(role_key) DO UPDATE SET
                    label = COALESCE(planning_capacity_roles.label, excluded.label),
                    sort_order = excluded.sort_order
                ;
                """,
                (role_key, label, active, sort_order),
            )
        conn.commit()


def list_slot_templates(*, active_only: bool = False, db_path: str | None = None) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        sql = "SELECT id, slot_label, start_time, end_time, sort_order, active FROM planning_slot_templates"
        if active_only:
            sql += " WHERE active=1"
        sql += " ORDER BY sort_order ASC, slot_label ASC;"
        rows = conn.execute(sql).fetchall()
        return _rows_to_dicts(rows)


def list_shift_templates(*, active_only: bool = False, db_path: str | None = None) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        sql = """
            SELECT id, shift_name, start_time, end_time, slot_count, sort_order, active
            FROM planning_shift_templates
        """
        if active_only:
            sql += " WHERE active=1"
        sql += " ORDER BY sort_order ASC, shift_name ASC;"
        rows = conn.execute(sql).fetchall()
        return _rows_to_dicts(rows)


def list_shift_staffing(*, db_path: str | None = None) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, shift_name, weekday, role_key, capacity
            FROM planning_shift_staffing_values
            ORDER BY weekday ASC, shift_name ASC, role_key ASC;
            """
        ).fetchall()
        return _rows_to_dicts(rows)


def list_capacity_roles(*, active_only: bool = False, db_path: str | None = None) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        sql = "SELECT id, role_key, label, active, sort_order FROM planning_capacity_roles"
        if active_only:
            sql += " WHERE active=1"
        sql += " ORDER BY sort_order ASC, role_key ASC;"
        rows = conn.execute(sql).fetchall()
        return _rows_to_dicts(rows)


def replace_places(place_codes: list[str], *, db_path: str | None = None) -> None:
    normalized = [normalize_place_code(code) for code in place_codes if normalize_place_code(code)]
    with _connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute("UPDATE planning_places SET active=0;")
        for index, code in enumerate(normalized, start=1):
            cur.execute(
                """
                INSERT INTO planning_places (code, label, active, sort_order, notes)
                VALUES (?, ?, 1, ?, '')
                ON CONFLICT(code) DO UPDATE SET
                    label = excluded.label,
                    active = 1,
                    sort_order = excluded.sort_order
                ;
                """,
                (code, code, index),
            )
        conn.commit()


def replace_slot_templates(slot_rows: list[dict[str, Any]], *, db_path: str | None = None) -> None:
    normalized: list[tuple[str, str, str]] = []
    for row in slot_rows:
        label = normalize_slot_label(row.get("slot_label"))
        start_time = str(row.get("start_time") or "").strip()
        end_time = str(row.get("end_time") or "").strip()
        if label:
            normalized.append((label, start_time, end_time))
    with _connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute("UPDATE planning_slot_templates SET active=0;")
        for index, (label, start_time, end_time) in enumerate(normalized, start=1):
            cur.execute(
                """
                INSERT INTO planning_slot_templates (slot_label, start_time, end_time, sort_order, active)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(slot_label) DO UPDATE SET
                    start_time = excluded.start_time,
                    end_time = excluded.end_time,
                    sort_order = excluded.sort_order,
                    active = 1
                ;
                """,
                (label, start_time, end_time, index),
            )
        conn.commit()


def replace_shift_templates(shift_rows: list[dict[str, Any]], *, db_path: str | None = None) -> None:
    normalized: list[tuple[str, str, str, int]] = []
    for row in shift_rows:
        shift_name = str(row.get("shift_name") or "").strip()
        start_time = str(row.get("start_time") or "").strip()
        end_time = str(row.get("end_time") or "").strip()
        try:
            slot_count = max(1, int(row.get("slot_count") or 1))
        except Exception:
            slot_count = 1
        if shift_name and start_time and end_time:
            normalized.append((shift_name, start_time, end_time, slot_count))
    with _connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute("UPDATE planning_shift_templates SET active=0;")
        for index, (shift_name, start_time, end_time, slot_count) in enumerate(normalized, start=1):
            cur.execute(
                """
                INSERT INTO planning_shift_templates (shift_name, start_time, end_time, slot_count, sort_order, active)
                VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(shift_name) DO UPDATE SET
                    start_time = excluded.start_time,
                    end_time = excluded.end_time,
                    slot_count = excluded.slot_count,
                    sort_order = excluded.sort_order,
                    active = 1
                ;
                """,
                (shift_name, start_time, end_time, slot_count, index),
            )
        conn.commit()


def replace_shift_staffing(staffing_rows: list[dict[str, Any]], *, db_path: str | None = None) -> None:
    with _connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM planning_shift_staffing_values;")
        for row in staffing_rows:
            shift_name = str(row.get("shift_name") or "").strip()
            role_key = _normalize_role_key(row.get("role_key"))
            if not shift_name:
                continue
            if not role_key:
                continue
            try:
                weekday = int(row.get("weekday"))
            except Exception:
                continue
            cur.execute(
                """
                INSERT INTO planning_shift_staffing_values (shift_name, weekday, role_key, capacity)
                VALUES (?, ?, ?, ?)
                ;
                """,
                (
                    shift_name,
                    weekday,
                    role_key,
                    float(row.get("capacity") or 0.0),
                ),
            )
        conn.commit()


def replace_capacity_roles(role_rows: list[dict[str, Any]], *, db_path: str | None = None) -> None:
    with _connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM planning_capacity_roles;")
        for index, row in enumerate(role_rows, start=1):
            role_key = _normalize_role_key(row.get("role_key"))
            label = str(row.get("label") or "").strip()
            if not role_key or not label:
                continue
            cur.execute(
                """
                INSERT INTO planning_capacity_roles (role_key, label, active, sort_order)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(role_key) DO UPDATE SET
                    label = excluded.label,
                    active = excluded.active,
                    sort_order = excluded.sort_order
                ;
                """,
                (role_key, label, int(bool(row.get("active", True))), index),
            )
        conn.commit()


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def _lookup_id_by_code(conn: sqlite3.Connection, table: str, code: str) -> int | None:
    row = conn.execute(f"SELECT id FROM {table} WHERE code=?;", (code,)).fetchone()
    return int(row["id"]) if row else None


def list_places(*, active_only: bool = False, db_path: str | None = None) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        sql = "SELECT id, code, label, active, sort_order, notes FROM planning_places"
        if active_only:
            sql += " WHERE active=1"
        sql += " ORDER BY sort_order ASC, code ASC;"
        rows = conn.execute(sql).fetchall()
        return _rows_to_dicts(rows)


def save_place(
    *,
    code: str,
    label: str,
    active: bool = True,
    sort_order: int = 0,
    notes: str = "",
    place_id: int | None = None,
    db_path: str | None = None,
) -> int:
    code_norm = normalize_place_code(code)
    label_norm = str(label or code_norm).strip() or code_norm
    with _connect(db_path) as conn:
        cur = conn.cursor()
        if place_id is None:
            cur.execute(
                """
                INSERT INTO planning_places (code, label, active, sort_order, notes)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    label = excluded.label,
                    active = excluded.active,
                    sort_order = excluded.sort_order,
                    notes = excluded.notes
                ;
                """,
                (code_norm, label_norm, int(bool(active)), int(sort_order), str(notes or "").strip()),
            )
            row = cur.execute("SELECT id FROM planning_places WHERE code=?;", (code_norm,)).fetchone()
        else:
            cur.execute(
                """
                UPDATE planning_places
                SET code=?, label=?, active=?, sort_order=?, notes=?
                WHERE id=?
                ;
                """,
                (code_norm, label_norm, int(bool(active)), int(sort_order), str(notes or "").strip(), int(place_id)),
            )
            row = cur.execute("SELECT id FROM planning_places WHERE id=?;", (int(place_id),)).fetchone()
        conn.commit()
        return int(row["id"]) if row else 0


def list_vehicle_types(*, active_only: bool = False, db_path: str | None = None) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        sql = "SELECT id, code, label, active, notes FROM planning_vehicle_types"
        if active_only:
            sql += " WHERE active=1"
        sql += " ORDER BY code ASC;"
        rows = conn.execute(sql).fetchall()
        return _rows_to_dicts(rows)


def save_vehicle_type(
    *,
    code: str,
    label: str,
    active: bool = True,
    notes: str = "",
    vehicle_type_id: int | None = None,
    db_path: str | None = None,
) -> int:
    code_norm = normalize_vehicle_type_code(code)
    label_norm = str(label or code_norm).strip() or code_norm
    with _connect(db_path) as conn:
        cur = conn.cursor()
        if vehicle_type_id is None:
            cur.execute(
                """
                INSERT INTO planning_vehicle_types (code, label, active, notes)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    label = excluded.label,
                    active = excluded.active,
                    notes = excluded.notes
                ;
                """,
                (code_norm, label_norm, int(bool(active)), str(notes or "").strip()),
            )
            row = cur.execute("SELECT id FROM planning_vehicle_types WHERE code=?;", (code_norm,)).fetchone()
        else:
            cur.execute(
                """
                UPDATE planning_vehicle_types
                SET code=?, label=?, active=?, notes=?
                WHERE id=?
                ;
                """,
                (code_norm, label_norm, int(bool(active)), str(notes or "").strip(), int(vehicle_type_id)),
            )
            row = cur.execute("SELECT id FROM planning_vehicle_types WHERE id=?;", (int(vehicle_type_id),)).fetchone()
        conn.commit()
        return int(row["id"]) if row else 0


def list_place_rules(
    *,
    vehicle_type_code: str | None = None,
    place_code: str | None = None,
    active_only: bool = False,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        clauses: list[str] = []
        params: list[Any] = []
        if vehicle_type_code:
            clauses.append("vt.code=?")
            params.append(normalize_vehicle_type_code(vehicle_type_code))
        if place_code:
            clauses.append("p.code=?")
            params.append(normalize_place_code(place_code))
        if active_only:
            clauses.append("r.active=1")
        where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(
            f"""
            SELECT
                r.id,
                r.vehicle_type_id,
                r.place_id,
                r.allowed,
                r.priority,
                r.reason,
                r.active,
                vt.code AS vehicle_type_code,
                vt.label AS vehicle_type_label,
                p.code AS place_code,
                p.label AS place_label
            FROM planning_place_rules r
            JOIN planning_vehicle_types vt ON vt.id = r.vehicle_type_id
            JOIN planning_places p ON p.id = r.place_id
            {where_sql}
            ORDER BY vt.code ASC, p.sort_order ASC, p.code ASC;
            """,
            params,
        ).fetchall()
        return _rows_to_dicts(rows)


def save_place_rule(
    *,
    vehicle_type_id: int | None = None,
    vehicle_type_code: str | None = None,
    place_id: int | None = None,
    place_code: str | None = None,
    allowed: bool = True,
    priority: str = "neutral",
    reason: str = "",
    active: bool = True,
    rule_id: int | None = None,
    db_path: str | None = None,
) -> int:
    with _connect(db_path) as conn:
        cur = conn.cursor()
        resolved_vehicle_type_id = int(vehicle_type_id) if vehicle_type_id is not None else None
        resolved_place_id = int(place_id) if place_id is not None else None
        if resolved_vehicle_type_id is None and vehicle_type_code:
            resolved_vehicle_type_id = _lookup_id_by_code(conn, "planning_vehicle_types", normalize_vehicle_type_code(vehicle_type_code))
        if resolved_place_id is None and place_code:
            resolved_place_id = _lookup_id_by_code(conn, "planning_places", normalize_place_code(place_code))
        if resolved_vehicle_type_id is None or resolved_place_id is None:
            raise ValueError("vehicle_type_id/place_id konnten nicht aufgelöst werden.")
        if rule_id is None:
            cur.execute(
                """
                INSERT INTO planning_place_rules (vehicle_type_id, place_id, allowed, priority, reason, active)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(vehicle_type_id, place_id) DO UPDATE SET
                    allowed = excluded.allowed,
                    priority = excluded.priority,
                    reason = excluded.reason,
                    active = excluded.active
                ;
                """,
                (
                    resolved_vehicle_type_id,
                    resolved_place_id,
                    int(bool(allowed)),
                    coerce_priority(priority),
                    str(reason or "").strip(),
                    int(bool(active)),
                ),
            )
            row = cur.execute(
                "SELECT id FROM planning_place_rules WHERE vehicle_type_id=? AND place_id=?;",
                (resolved_vehicle_type_id, resolved_place_id),
            ).fetchone()
        else:
            cur.execute(
                """
                UPDATE planning_place_rules
                SET vehicle_type_id=?, place_id=?, allowed=?, priority=?, reason=?, active=?
                WHERE id=?
                ;
                """,
                (
                    resolved_vehicle_type_id,
                    resolved_place_id,
                    int(bool(allowed)),
                    coerce_priority(priority),
                    str(reason or "").strip(),
                    int(bool(active)),
                    int(rule_id),
                ),
            )
            row = cur.execute("SELECT id FROM planning_place_rules WHERE id=?;", (int(rule_id),)).fetchone()
        conn.commit()
        return int(row["id"]) if row else 0


def list_time_rules(
    *,
    friststufe: str | None = None,
    vehicle_type_code: str | None = None,
    active_only: bool = False,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if friststufe:
        clauses.append("r.friststufe=?")
        params.append(normalize_friststufe(friststufe))
    if vehicle_type_code:
        clauses.append("vt.code=?")
        params.append(normalize_vehicle_type_code(vehicle_type_code))
    if active_only:
        clauses.append("r.active=1")
    where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT
                r.id,
                r.friststufe,
                r.vehicle_type_id,
                r.base_minutes,
                r.stand_minutes_min,
                r.stand_factor,
                r.active,
                r.notes,
                vt.code AS vehicle_type_code,
                vt.label AS vehicle_type_label
            FROM planning_time_rules r
            LEFT JOIN planning_vehicle_types vt ON vt.id = r.vehicle_type_id
            {where_sql}
            ORDER BY r.friststufe ASC, vt.code ASC;
            """,
            params,
        ).fetchall()
        return _rows_to_dicts(rows)


def save_time_rule(
    *,
    friststufe: str,
    base_minutes: int,
    stand_minutes_min: int = 0,
    stand_factor: float = 1.0,
    vehicle_type_id: int | None = None,
    vehicle_type_code: str | None = None,
    active: bool = True,
    notes: str = "",
    time_rule_id: int | None = None,
    db_path: str | None = None,
) -> int:
    frist_norm = normalize_friststufe(friststufe)
    with _connect(db_path) as conn:
        cur = conn.cursor()
        resolved_vehicle_type_id = int(vehicle_type_id) if vehicle_type_id is not None else None
        if resolved_vehicle_type_id is None and vehicle_type_code:
            resolved_vehicle_type_id = _lookup_id_by_code(conn, "planning_vehicle_types", normalize_vehicle_type_code(vehicle_type_code))
        if time_rule_id is None:
            cur.execute(
                """
                INSERT INTO planning_time_rules (
                    friststufe, vehicle_type_id, base_minutes, stand_minutes_min, stand_factor, active, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ;
                """,
                (
                    frist_norm,
                    resolved_vehicle_type_id,
                    int(base_minutes),
                    int(stand_minutes_min),
                    float(stand_factor),
                    int(bool(active)),
                    str(notes or "").strip(),
                ),
            )
            rule_id = int(cur.lastrowid)
        else:
            cur.execute(
                """
                UPDATE planning_time_rules
                SET friststufe=?, vehicle_type_id=?, base_minutes=?, stand_minutes_min=?, stand_factor=?, active=?, notes=?
                WHERE id=?
                ;
                """,
                (
                    frist_norm,
                    resolved_vehicle_type_id,
                    int(base_minutes),
                    int(stand_minutes_min),
                    float(stand_factor),
                    int(bool(active)),
                    str(notes or "").strip(),
                    int(time_rule_id),
                ),
            )
            rule_id = int(time_rule_id)
        conn.commit()
        return rule_id


def create_planning_job(
    *,
    fahrzeug: str,
    friststufe: str,
    source_open_task_id: int | None = None,
    vehicle_type_id: int | None = None,
    required_minutes: int = 0,
    planned_minutes: int = 0,
    required_stand_minutes: int = 0,
    status: str = "draft",
    notes: str = "",
    created_at: str | None = None,
    updated_at: str | None = None,
    db_path: str | None = None,
) -> int:
    with _connect(db_path) as conn:
        cur = conn.cursor()
        resolved_vehicle_type_id = int(vehicle_type_id) if vehicle_type_id is not None else None
        if resolved_vehicle_type_id is None:
            vehicle_type_code = detect_vehicle_type(fahrzeug)
            if vehicle_type_code:
                resolved_vehicle_type_id = _lookup_id_by_code(conn, "planning_vehicle_types", vehicle_type_code)
        cur.execute(
            """
            INSERT INTO planning_jobs (
                fahrzeug, vehicle_type_id, friststufe, source_open_task_id,
                required_minutes, planned_minutes, required_stand_minutes,
                status, notes, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ;
            """,
            (
                str(fahrzeug or "").strip(),
                resolved_vehicle_type_id,
                normalize_friststufe(friststufe),
                source_open_task_id,
                int(required_minutes),
                int(planned_minutes),
                int(required_stand_minutes),
                coerce_job_status(status),
                str(notes or "").strip(),
                created_at,
                updated_at,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def update_planning_job_metrics(
    *,
    planning_job_id: int,
    required_minutes: int,
    planned_minutes: int,
    required_stand_minutes: int,
    status: str,
    updated_at: str | None = None,
    db_path: str | None = None,
) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE planning_jobs
            SET required_minutes=?, planned_minutes=?, required_stand_minutes=?, status=?, updated_at=?
            WHERE id=?
            ;
            """,
            (
                int(required_minutes),
                int(planned_minutes),
                int(required_stand_minutes),
                coerce_job_status(status),
                updated_at,
                int(planning_job_id),
            ),
        )
        conn.commit()


def list_planning_jobs_for_day(day_iso: str, *, db_path: str | None = None) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                j.id,
                j.fahrzeug,
                j.friststufe,
                j.required_minutes,
                j.planned_minutes,
                j.required_stand_minutes,
                j.status,
                j.notes,
                j.created_at,
                j.updated_at,
                vt.code AS vehicle_type_code,
                vt.label AS vehicle_type_label
            FROM planning_jobs j
            LEFT JOIN planning_vehicle_types vt ON vt.id = j.vehicle_type_id
            WHERE EXISTS (
                SELECT 1
                FROM planning_assignments a
                WHERE a.planning_job_id = j.id
                  AND substr(a.start_dt, 1, 10) <= ?
                  AND substr(a.end_dt, 1, 10) >= ?
            )
            ORDER BY j.status ASC, j.fahrzeug ASC
            ;
            """,
            (day_iso, day_iso),
        ).fetchall()
        return _rows_to_dicts(rows)


def save_assignment(
    *,
    planning_job_id: int,
    place_id: int | None = None,
    place_code: str | None = None,
    start_dt: str,
    end_dt: str,
    note: str = "",
    created_at: str | None = None,
    updated_at: str | None = None,
    assignment_id: int | None = None,
    db_path: str | None = None,
) -> int:
    with _connect(db_path) as conn:
        cur = conn.cursor()
        resolved_place_id = int(place_id) if place_id is not None else None
        if resolved_place_id is None and place_code:
            resolved_place_id = _lookup_id_by_code(conn, "planning_places", normalize_place_code(place_code))
        if resolved_place_id is None:
            raise ValueError("place_id/place_code konnte nicht aufgelöst werden.")
        if assignment_id is None:
            cur.execute(
                """
                INSERT INTO planning_assignments (
                    planning_job_id, place_id, start_dt, end_dt, note, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ;
                """,
                (
                    int(planning_job_id),
                    resolved_place_id,
                    str(start_dt or "").strip(),
                    str(end_dt or "").strip(),
                    str(note or "").strip(),
                    created_at,
                    updated_at,
                ),
            )
            new_id = int(cur.lastrowid)
        else:
            cur.execute(
                """
                UPDATE planning_assignments
                SET planning_job_id=?, place_id=?, start_dt=?, end_dt=?, note=?, updated_at=?
                WHERE id=?
                ;
                """,
                (
                    int(planning_job_id),
                    resolved_place_id,
                    str(start_dt or "").strip(),
                    str(end_dt or "").strip(),
                    str(note or "").strip(),
                    updated_at,
                    int(assignment_id),
                ),
            )
            new_id = int(assignment_id)
        conn.commit()
        return new_id


def list_assignments_for_day(day_iso: str, *, db_path: str | None = None) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                a.id,
                a.planning_job_id,
                a.start_dt,
                a.end_dt,
                a.note,
                a.created_at,
                a.updated_at,
                p.id AS place_id,
                p.code AS place_code,
                p.label AS place_label,
                j.fahrzeug,
                j.friststufe,
                j.status
            FROM planning_assignments a
            JOIN planning_places p ON p.id = a.place_id
            JOIN planning_jobs j ON j.id = a.planning_job_id
            WHERE substr(a.start_dt, 1, 10) <= ?
              AND substr(a.end_dt, 1, 10) >= ?
            ORDER BY p.sort_order ASC, a.start_dt ASC, a.end_dt ASC
            ;
            """,
            (day_iso, day_iso),
        ).fetchall()
        return _rows_to_dicts(rows)


def save_planning_order(
    *,
    fahrzeug: str,
    friststufe: str,
    order_kind: str = "",
    zusatzarbeiten: str = "",
    gewerke_info: str = "",
    ecm3_start_date: str = "",
    ecm3_start_time: str = "",
    ecm3_end_date: str = "",
    ecm3_end_time: str = "",
    required_ma_8h: float | int | None = None,
    planned_ma: float | int | None = None,
    ecm4_start_date: str = "",
    ecm4_start_time: str = "",
    ecm4_end_date: str = "",
    ecm4_end_time: str = "",
    ecm4_place_code: str = "",
    status: str = "draft",
    source_origin: str = "",
    source_open_task_id: int | None = None,
    source_sheet: str = "",
    source_row_number: int | None = None,
    created_at: str | None = None,
    updated_at: str | None = None,
    order_id: int | None = None,
    db_path: str | None = None,
) -> int:
    fahrzeug_txt = str(fahrzeug or "").strip()
    frist_txt = normalize_friststufe(friststufe)
    vehicle_type_code = detect_vehicle_type(fahrzeug_txt)
    order_kind_txt = str(order_kind or "").strip()
    place_code_txt = normalize_place_code(ecm4_place_code) if str(ecm4_place_code or "").strip() else ""
    with _connect(db_path) as conn:
        cur = conn.cursor()
        payload = (
            fahrzeug_txt,
            vehicle_type_code or None,
            frist_txt,
            order_kind_txt or None,
            str(zusatzarbeiten or "").strip() or None,
            str(gewerke_info or "").strip() or None,
            str(ecm3_start_date or "").strip() or None,
            str(ecm3_start_time or "").strip() or None,
            str(ecm3_end_date or "").strip() or None,
            str(ecm3_end_time or "").strip() or None,
            float(required_ma_8h) if required_ma_8h not in (None, "") else None,
            float(planned_ma) if planned_ma not in (None, "") else None,
            str(ecm4_start_date or "").strip() or None,
            str(ecm4_start_time or "").strip() or None,
            str(ecm4_end_date or "").strip() or None,
            str(ecm4_end_time or "").strip() or None,
            place_code_txt or None,
            str(status or "draft").strip() or "draft",
            str(source_origin or "").strip() or None,
            int(source_open_task_id) if source_open_task_id not in (None, "") else None,
            str(source_sheet or "").strip() or None,
            int(source_row_number) if source_row_number not in (None, "") else None,
        )
        if order_id is None:
            cur.execute(
                """
                INSERT INTO planning_orders (
                    fahrzeug, vehicle_type_code, friststufe, order_kind, zusatzarbeiten, gewerke_info,
                    ecm3_start_date, ecm3_start_time, ecm3_end_date, ecm3_end_time,
                    required_ma_8h, planned_ma,
                    ecm4_start_date, ecm4_start_time, ecm4_end_date, ecm4_end_time, ecm4_place_code,
                    status, source_origin, source_open_task_id, source_sheet, source_row_number, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ;
                """,
                payload + (created_at, updated_at),
            )
            new_id = int(cur.lastrowid)
        else:
            cur.execute(
                """
                UPDATE planning_orders
                SET fahrzeug=?, vehicle_type_code=?, friststufe=?, order_kind=?, zusatzarbeiten=?, gewerke_info=?,
                    ecm3_start_date=?, ecm3_start_time=?, ecm3_end_date=?, ecm3_end_time=?,
                    required_ma_8h=?, planned_ma=?,
                    ecm4_start_date=?, ecm4_start_time=?, ecm4_end_date=?, ecm4_end_time=?, ecm4_place_code=?,
                    status=?, source_origin=?, source_open_task_id=?, source_sheet=?, source_row_number=?, updated_at=?
                WHERE id=?
                ;
                """,
                payload + (updated_at, int(order_id)),
            )
            new_id = int(order_id)
        conn.commit()
        return new_id


def get_planning_order(
    order_id: int,
    *,
    db_path: str | None = None,
) -> dict[str, Any] | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT
                id,
                fahrzeug,
                vehicle_type_code,
                friststufe,
                order_kind,
                zusatzarbeiten,
                gewerke_info,
                ecm3_start_date,
                ecm3_start_time,
                ecm3_end_date,
                ecm3_end_time,
                required_ma_8h,
                planned_ma,
                ecm4_start_date,
                ecm4_start_time,
                ecm4_end_date,
                ecm4_end_time,
                ecm4_place_code,
                status,
                source_origin,
                source_open_task_id,
                source_sheet,
                source_row_number,
                created_at,
                updated_at
            FROM planning_orders
            WHERE id=?
            LIMIT 1
            ;
            """,
            (int(order_id),),
        ).fetchone()
        return dict(row) if row else None


def list_planning_orders(
    *,
    status: str | None = None,
    fahrzeug: str | None = None,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("status=?")
        params.append(str(status).strip())
    if fahrzeug:
        clauses.append("fahrzeug LIKE ?")
        params.append(f"%{str(fahrzeug).strip()}%")
    where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT
                id,
                fahrzeug,
                vehicle_type_code,
                friststufe,
                order_kind,
                zusatzarbeiten,
                gewerke_info,
                ecm3_start_date,
                ecm3_start_time,
                ecm3_end_date,
                ecm3_end_time,
                required_ma_8h,
                planned_ma,
                ecm4_start_date,
                ecm4_start_time,
                ecm4_end_date,
                ecm4_end_time,
                ecm4_place_code,
                status,
                source_origin,
                source_open_task_id,
                source_sheet,
                source_row_number,
                created_at,
                updated_at
            FROM planning_orders
            {where_sql}
            ORDER BY
                COALESCE(ecm3_start_date, '') ASC,
                COALESCE(ecm3_start_time, '') ASC,
                fahrzeug ASC
            ;
            """,
            params,
        ).fetchall()
        return _rows_to_dicts(rows)


def list_planning_order_allocation_totals(
    *,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                planning_order_id,
                SUM(COALESCE(allocated_ma, 0)) AS allocated_total
            FROM planning_allocations
            WHERE planning_order_id IS NOT NULL
            GROUP BY planning_order_id
            ;
            """
        ).fetchall()
        return _rows_to_dicts(rows)


def save_planning_slot(
    *,
    slot_date: str,
    slot_time: str,
    slot_start: str = "",
    slot_end: str = "",
    workshop_staff: float | int | None = None,
    service_staff: float | int | None = None,
    urd_staff: float | int | None = None,
    mek_value: float | int | None = None,
    vehicle_count: float | int | None = None,
    staff_per_vehicle: float | int | None = None,
    notes: str = "",
    created_at: str | None = None,
    updated_at: str | None = None,
    slot_id: int | None = None,
    db_path: str | None = None,
) -> int:
    slot_date_txt = str(slot_date or "").strip()
    slot_time_txt = str(slot_time or "").strip()
    with _connect(db_path) as conn:
        cur = conn.cursor()
        payload = (
            slot_date_txt,
            slot_time_txt,
            str(slot_start or "").strip() or None,
            str(slot_end or "").strip() or None,
            float(workshop_staff) if workshop_staff not in (None, "") else None,
            float(service_staff) if service_staff not in (None, "") else None,
            float(urd_staff) if urd_staff not in (None, "") else None,
            float(mek_value) if mek_value not in (None, "") else None,
            float(vehicle_count) if vehicle_count not in (None, "") else None,
            float(staff_per_vehicle) if staff_per_vehicle not in (None, "") else None,
            str(notes or "").strip() or None,
        )
        if slot_id is None:
            cur.execute(
                """
                INSERT INTO planning_slots (
                    slot_date, slot_time, slot_start, slot_end,
                    workshop_staff, service_staff, urd_staff, mek_value, vehicle_count, staff_per_vehicle,
                    notes, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(slot_date, slot_time) DO UPDATE SET
                    slot_start = excluded.slot_start,
                    slot_end = excluded.slot_end,
                    workshop_staff = excluded.workshop_staff,
                    service_staff = excluded.service_staff,
                    urd_staff = excluded.urd_staff,
                    mek_value = excluded.mek_value,
                    vehicle_count = excluded.vehicle_count,
                    staff_per_vehicle = excluded.staff_per_vehicle,
                    notes = excluded.notes,
                    updated_at = excluded.updated_at
                ;
                """,
                payload + (created_at, updated_at),
            )
            row = cur.execute(
                "SELECT id FROM planning_slots WHERE slot_date=? AND slot_time=?;",
                (slot_date_txt, slot_time_txt),
            ).fetchone()
            new_id = int(row["id"]) if row else 0
        else:
            cur.execute(
                """
                UPDATE planning_slots
                SET slot_date=?, slot_time=?, slot_start=?, slot_end=?,
                    workshop_staff=?, service_staff=?, urd_staff=?, mek_value=?, vehicle_count=?, staff_per_vehicle=?,
                    notes=?, updated_at=?
                WHERE id=?
                ;
                """,
                payload + (updated_at, int(slot_id)),
            )
            new_id = int(slot_id)
        conn.commit()
        return new_id


def list_planning_slots_for_day(day_iso: str, *, db_path: str | None = None) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                slot_date,
                slot_time,
                slot_start,
                slot_end,
                workshop_staff,
                service_staff,
                urd_staff,
                mek_value,
                vehicle_count,
                staff_per_vehicle,
                notes,
                created_at,
                updated_at
            FROM planning_slots
            WHERE slot_date=?
            ORDER BY slot_time ASC
            ;
            """,
            (day_iso,),
        ).fetchall()
        return _rows_to_dicts(rows)


def save_planning_slot_assignment(
    *,
    slot_id: int,
    place_code: str,
    fahrzeug: str = "",
    planning_order_id: int | None = None,
    note: str = "",
    created_at: str | None = None,
    updated_at: str | None = None,
    assignment_id: int | None = None,
    db_path: str | None = None,
) -> int:
    place_code_txt = normalize_place_code(place_code)
    with _connect(db_path) as conn:
        cur = conn.cursor()
        payload = (
            int(slot_id),
            place_code_txt,
            str(fahrzeug or "").strip() or None,
            int(planning_order_id) if planning_order_id is not None else None,
            str(note or "").strip() or None,
        )
        if assignment_id is None:
            cur.execute(
                """
                INSERT INTO planning_slot_assignments (
                    slot_id, place_code, fahrzeug, planning_order_id, note, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(slot_id, place_code) DO UPDATE SET
                    fahrzeug = excluded.fahrzeug,
                    planning_order_id = excluded.planning_order_id,
                    note = excluded.note,
                    updated_at = excluded.updated_at
                ;
                """,
                payload + (created_at, updated_at),
            )
            row = cur.execute(
                "SELECT id FROM planning_slot_assignments WHERE slot_id=? AND place_code=?;",
                (int(slot_id), place_code_txt),
            ).fetchone()
            new_id = int(row["id"]) if row else 0
        else:
            cur.execute(
                """
                UPDATE planning_slot_assignments
                SET slot_id=?, place_code=?, fahrzeug=?, planning_order_id=?, note=?, updated_at=?
                WHERE id=?
                ;
                """,
                payload + (updated_at, int(assignment_id)),
            )
            new_id = int(assignment_id)
        conn.commit()
        return new_id


def list_slot_assignments(
    *,
    slot_date: str | None = None,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if slot_date:
        clauses.append("s.slot_date=?")
        params.append(slot_date)
    where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT
                a.id,
                a.slot_id,
                a.place_code,
                a.fahrzeug,
                a.planning_order_id,
                a.note,
                a.created_at,
                a.updated_at,
                s.slot_date,
                s.slot_time,
                o.friststufe,
                o.order_kind,
                o.status AS order_status
            FROM planning_slot_assignments a
            JOIN planning_slots s ON s.id = a.slot_id
            LEFT JOIN planning_orders o ON o.id = a.planning_order_id
            {where_sql}
            ORDER BY s.slot_date ASC, s.slot_time ASC, a.place_code ASC
            ;
            """,
            params,
        ).fetchall()
        return _rows_to_dicts(rows)


def ensure_capacity_slots_for_dates(
    slot_dates: list[str],
    *,
    slot_labels: list[str] | None = None,
    source_name: str = "default",
    db_path: str | None = None,
) -> None:
    clean_dates = [str(value or "").strip() for value in slot_dates if str(value or "").strip()]
    clean_labels = [normalize_slot_label(value) for value in (slot_labels or DEFAULT_CAPACITY_SLOTS) if normalize_slot_label(value)]
    if not clean_dates:
        return
    with _connect(db_path) as conn:
        cur = conn.cursor()
        for slot_date in clean_dates:
            for slot_label in clean_labels:
                cur.execute(
                    """
                    INSERT INTO planning_capacity_slots (
                        slot_date, slot_label, workshop_capacity, service_capacity, urd_capacity,
                        source_name, notes, created_at, updated_at
                    )
                    VALUES (?, ?, 0, 0, 0, ?, NULL, NULL, NULL)
                    ON CONFLICT(slot_date, slot_label) DO NOTHING
                    ;
                    """,
                    (slot_date, slot_label, str(source_name or "").strip() or "default"),
                )
        conn.commit()


def save_capacity_slot(
    *,
    slot_date: str,
    slot_label: str,
    workshop_capacity: float | int | None = None,
    service_capacity: float | int | None = None,
    urd_capacity: float | int | None = None,
    allocation_mode: str = "auto",
    source_name: str = "",
    notes: str = "",
    created_at: str | None = None,
    updated_at: str | None = None,
    capacity_slot_id: int | None = None,
    db_path: str | None = None,
) -> int:
    slot_date_txt = str(slot_date or "").strip()
    slot_label_txt = normalize_slot_label(slot_label)
    with _connect(db_path) as conn:
        cur = conn.cursor()
        payload = (
            slot_date_txt,
            slot_label_txt,
            float(workshop_capacity) if workshop_capacity not in (None, "") else 0.0,
            float(service_capacity) if service_capacity not in (None, "") else 0.0,
            float(urd_capacity) if urd_capacity not in (None, "") else 0.0,
            str(allocation_mode or "auto").strip().lower() or "auto",
            str(source_name or "").strip() or None,
            str(notes or "").strip() or None,
        )
        if capacity_slot_id is None:
            cur.execute(
                """
                INSERT INTO planning_capacity_slots (
                    slot_date, slot_label, workshop_capacity, service_capacity, urd_capacity, allocation_mode,
                    source_name, notes, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(slot_date, slot_label) DO UPDATE SET
                    workshop_capacity = excluded.workshop_capacity,
                    service_capacity = excluded.service_capacity,
                    urd_capacity = excluded.urd_capacity,
                    allocation_mode = excluded.allocation_mode,
                    source_name = excluded.source_name,
                    notes = excluded.notes,
                    updated_at = excluded.updated_at
                ;
                """,
                payload + (created_at, updated_at),
            )
            row = cur.execute(
                "SELECT id FROM planning_capacity_slots WHERE slot_date=? AND slot_label=?;",
                (slot_date_txt, slot_label_txt),
            ).fetchone()
            new_id = int(row["id"]) if row else 0
        else:
            cur.execute(
                """
                UPDATE planning_capacity_slots
                SET slot_date=?, slot_label=?, workshop_capacity=?, service_capacity=?, urd_capacity=?,
                    allocation_mode=?, source_name=?, notes=?, updated_at=?
                WHERE id=?
                ;
                """,
                payload + (updated_at, int(capacity_slot_id)),
            )
            new_id = int(capacity_slot_id)
        conn.commit()
        return new_id


def list_capacity_slots_for_range(
    date_from: str,
    date_to: str,
    *,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                slot_date,
                slot_label,
                workshop_capacity,
                service_capacity,
                urd_capacity,
                allocation_mode,
                source_name,
                notes,
                created_at,
                updated_at
            FROM planning_capacity_slots
            WHERE slot_date >= ?
              AND slot_date <= ?
            ORDER BY slot_date ASC, slot_label ASC
            ;
            """,
            (date_from, date_to),
        ).fetchall()
        return _rows_to_dicts(rows)


def save_planning_allocation(
    *,
    capacity_slot_id: int,
    place_code: str,
    planning_order_id: int,
    fahrzeug: str = "",
    allocated_ma: float | int | None = None,
    note: str = "",
    created_at: str | None = None,
    updated_at: str | None = None,
    allocation_id: int | None = None,
    db_path: str | None = None,
) -> int:
    place_code_txt = normalize_place_code(place_code)
    with _connect(db_path) as conn:
        cur = conn.cursor()
        payload = (
            int(capacity_slot_id),
            place_code_txt,
            int(planning_order_id),
            str(fahrzeug or "").strip() or None,
            float(allocated_ma) if allocated_ma not in (None, "") else 0.0,
            str(note or "").strip() or None,
        )
        if allocation_id is None:
            cur.execute(
                """
                INSERT INTO planning_allocations (
                    capacity_slot_id, place_code, planning_order_id, fahrzeug, allocated_ma, note, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(capacity_slot_id, place_code) DO UPDATE SET
                    planning_order_id = excluded.planning_order_id,
                    fahrzeug = excluded.fahrzeug,
                    allocated_ma = excluded.allocated_ma,
                    note = excluded.note,
                    updated_at = excluded.updated_at
                ;
                """,
                payload + (created_at, updated_at),
            )
            row = cur.execute(
                "SELECT id FROM planning_allocations WHERE capacity_slot_id=? AND place_code=?;",
                (int(capacity_slot_id), place_code_txt),
            ).fetchone()
            new_id = int(row["id"]) if row else 0
        else:
            cur.execute(
                """
                UPDATE planning_allocations
                SET capacity_slot_id=?, place_code=?, planning_order_id=?, fahrzeug=?, allocated_ma=?, note=?, updated_at=?
                WHERE id=?
                ;
                """,
                payload + (updated_at, int(allocation_id)),
            )
            new_id = int(allocation_id)
        conn.commit()
        return new_id


def save_planning_allocations_batch(
    allocation_rows: list[dict[str, Any]],
    *,
    created_at: str | None = None,
    updated_at: str | None = None,
    db_path: str | None = None,
) -> list[int]:
    saved_ids: list[int] = []
    with _connect(db_path) as conn:
        cur = conn.cursor()
        for row in allocation_rows:
            place_code_txt = normalize_place_code(row.get("place_code"))
            payload = (
                int(row.get("capacity_slot_id") or 0),
                place_code_txt,
                int(row.get("planning_order_id") or 0),
                str(row.get("fahrzeug") or "").strip() or None,
                float(row.get("allocated_ma")) if row.get("allocated_ma") not in (None, "") else 0.0,
                str(row.get("note") or "").strip() or None,
            )
            allocation_id = row.get("allocation_id")
            if allocation_id in (None, "", 0):
                cur.execute(
                    """
                    INSERT INTO planning_allocations (
                        capacity_slot_id, place_code, planning_order_id, fahrzeug, allocated_ma, note, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(capacity_slot_id, place_code) DO UPDATE SET
                        planning_order_id = excluded.planning_order_id,
                        fahrzeug = excluded.fahrzeug,
                        allocated_ma = excluded.allocated_ma,
                        note = excluded.note,
                        updated_at = excluded.updated_at
                    ;
                    """,
                    payload + (created_at, updated_at),
                )
                found = cur.execute(
                    "SELECT id FROM planning_allocations WHERE capacity_slot_id=? AND place_code=?;",
                    (int(row.get("capacity_slot_id") or 0), place_code_txt),
                ).fetchone()
                saved_ids.append(int(found["id"]) if found else 0)
            else:
                cur.execute(
                    """
                    UPDATE planning_allocations
                    SET capacity_slot_id=?, place_code=?, planning_order_id=?, fahrzeug=?, allocated_ma=?, note=?, updated_at=?
                    WHERE id=?
                    ;
                    """,
                    payload + (updated_at, int(allocation_id)),
                )
                saved_ids.append(int(allocation_id))
        conn.commit()
    return saved_ids


def replace_planning_order_block_allocations(
    *,
    planning_order_id: int,
    place_code: str,
    capacity_slot_ids: list[int],
    allocation_rows: list[dict[str, Any]],
    created_at: str | None = None,
    updated_at: str | None = None,
    db_path: str | None = None,
) -> list[int]:
    place_code_txt = normalize_place_code(place_code)
    clean_slot_ids = [int(value) for value in capacity_slot_ids if int(value or 0) > 0]
    saved_ids: list[int] = []
    with _connect(db_path) as conn:
        cur = conn.cursor()
        if clean_slot_ids:
            placeholders = ",".join("?" for _ in clean_slot_ids)
            cur.execute(
                f"""
                DELETE FROM planning_allocations
                WHERE planning_order_id=?
                  AND place_code=?
                  AND capacity_slot_id IN ({placeholders})
                ;
                """,
                [int(planning_order_id), place_code_txt, *clean_slot_ids],
            )
        for row in allocation_rows:
            row_place_code = normalize_place_code(row.get("place_code"))
            payload = (
                int(row.get("capacity_slot_id") or 0),
                row_place_code,
                int(row.get("planning_order_id") or 0),
                str(row.get("fahrzeug") or "").strip() or None,
                float(row.get("allocated_ma")) if row.get("allocated_ma") not in (None, "") else 0.0,
                str(row.get("note") or "").strip() or None,
            )
            cur.execute(
                """
                INSERT INTO planning_allocations (
                    capacity_slot_id, place_code, planning_order_id, fahrzeug, allocated_ma, note, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(capacity_slot_id, place_code) DO UPDATE SET
                    planning_order_id = excluded.planning_order_id,
                    fahrzeug = excluded.fahrzeug,
                    allocated_ma = excluded.allocated_ma,
                    note = excluded.note,
                    updated_at = excluded.updated_at
                ;
                """,
                payload + (created_at, updated_at),
            )
            found = cur.execute(
                "SELECT id FROM planning_allocations WHERE capacity_slot_id=? AND place_code=?;",
                (int(row.get("capacity_slot_id") or 0), row_place_code),
            ).fetchone()
            saved_ids.append(int(found["id"]) if found else 0)
        conn.commit()
    return saved_ids


def list_planning_allocations_for_range(
    date_from: str,
    date_to: str,
    *,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                a.id,
                a.capacity_slot_id,
                a.place_code,
                a.planning_order_id,
                a.fahrzeug,
                a.allocated_ma,
                a.note,
                a.created_at,
                a.updated_at,
                s.slot_date,
                s.slot_label,
                s.workshop_capacity,
                s.service_capacity,
                s.urd_capacity,
                o.friststufe,
                o.order_kind,
                o.required_ma_8h,
                o.planned_ma,
                o.status AS order_status
            FROM planning_allocations a
            JOIN planning_capacity_slots s ON s.id = a.capacity_slot_id
            JOIN planning_orders o ON o.id = a.planning_order_id
            WHERE s.slot_date >= ?
              AND s.slot_date <= ?
            ORDER BY s.slot_date ASC, s.slot_label ASC, a.place_code ASC
            ;
            """,
            (date_from, date_to),
        ).fetchall()
        return _rows_to_dicts(rows)


def list_planning_allocations_for_order_ids(
    planning_order_ids: list[int],
    *,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    clean_ids = [int(value) for value in planning_order_ids if int(value or 0) > 0]
    if not clean_ids:
        return []
    placeholders = ",".join("?" for _ in clean_ids)
    with _connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT
                a.id,
                a.capacity_slot_id,
                a.place_code,
                a.planning_order_id,
                a.fahrzeug,
                a.allocated_ma,
                a.note,
                a.created_at,
                a.updated_at,
                s.slot_date,
                s.slot_label,
                s.workshop_capacity,
                s.service_capacity,
                s.urd_capacity,
                o.friststufe,
                o.order_kind,
                o.required_ma_8h,
                o.planned_ma,
                o.status AS order_status
            FROM planning_allocations a
            JOIN planning_capacity_slots s ON s.id = a.capacity_slot_id
            JOIN planning_orders o ON o.id = a.planning_order_id
            WHERE a.planning_order_id IN ({placeholders})
            ORDER BY s.slot_date ASC, s.slot_label ASC, a.place_code ASC
            ;
            """,
            clean_ids,
        ).fetchall()
        return _rows_to_dicts(rows)


def delete_planning_allocation(
    *,
    allocation_id: int,
    db_path: str | None = None,
) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            DELETE FROM planning_allocations
            WHERE id=?
            ;
            """,
            (int(allocation_id),),
        )
        conn.commit()


def delete_planning_allocations_by_ids(
    allocation_ids: list[int],
    *,
    db_path: str | None = None,
) -> None:
    clean_ids = [int(value) for value in allocation_ids if int(value or 0) > 0]
    if not clean_ids:
        return
    placeholders = ",".join("?" for _ in clean_ids)
    with _connect(db_path) as conn:
        conn.execute(
            f"""
            DELETE FROM planning_allocations
            WHERE id IN ({placeholders})
            ;
            """,
            clean_ids,
        )
        conn.commit()


def delete_planning_allocations_for_order(
    *,
    planning_order_id: int,
    db_path: str | None = None,
) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            DELETE FROM planning_allocations
            WHERE planning_order_id=?
            ;
            """,
            (int(planning_order_id),),
        )
        conn.commit()


def delete_planning_allocations_for_range(
    date_from: str,
    date_to: str,
    *,
    db_path: str | None = None,
) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            DELETE FROM planning_allocations
            WHERE capacity_slot_id IN (
                SELECT id
                FROM planning_capacity_slots
                WHERE slot_date >= ?
                  AND slot_date <= ?
            )
            ;
            """,
            (str(date_from or "").strip(), str(date_to or "").strip()),
        )
        conn.commit()


def reset_capacity_allocation_mode_for_range(
    date_from: str,
    date_to: str,
    *,
    allocation_mode: str = "auto",
    updated_at: str | None = None,
    db_path: str | None = None,
) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE planning_capacity_slots
            SET allocation_mode=?, updated_at=?
            WHERE slot_date >= ?
              AND slot_date <= ?
            ;
            """,
            (
                str(allocation_mode or "auto").strip().lower() or "auto",
                updated_at,
                str(date_from or "").strip(),
                str(date_to or "").strip(),
            ),
        )
        conn.commit()


def delete_planning_order(
    *,
    order_id: int,
    db_path: str | None = None,
) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            DELETE FROM planning_allocations
            WHERE planning_order_id=?
            ;
            """,
            (int(order_id),),
        )
        conn.execute(
            """
            DELETE FROM planning_slot_assignments
            WHERE planning_order_id=?
            ;
            """,
            (int(order_id),),
        )
        conn.execute(
            """
            DELETE FROM planning_orders
            WHERE id=?
            ;
            """,
            (int(order_id),),
        )
        conn.commit()
