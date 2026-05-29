from __future__ import annotations

from datetime import datetime
import logging
import sqlite3
from typing import Any

from core import db as db_core
from core.config import DB_PATH


BERLIN = None
as_berlin = None
_clean_nullable_text = None
_clean_nullable_db_text = None

logger = logging.getLogger(__name__)


def configure(**deps) -> None:
    globals().update(deps)


def _find_best_archive_row_for_recent(
    fahrzeug: Any,
    friststufe: Any,
    archived_at: Any,
) -> sqlite3.Row | None:
    veh_raw = _clean_nullable_text(fahrzeug)
    if not veh_raw:
        return None
    fr_raw = _clean_nullable_text(friststufe)
    rows = db_core.db_exec(
        """
        SELECT id, fahrzeug, friststufe, anfang, fertig, completed_at, last_problem_note, initial_fertig
        FROM archive
        WHERE lower(trim(fahrzeug))=?
          AND lower(trim(coalesce(friststufe, '')))=?
        ORDER BY completed_at DESC, id DESC;
        """,
        (veh_raw.casefold(), fr_raw.casefold()),
        fetch=True,
    ) or []
    if not rows:
        return None
    rows = sorted(
        rows,
        key=lambda rr: (
            as_berlin(rr["completed_at"]) or datetime.min.replace(tzinfo=BERLIN),
            int(rr["id"] or 0),
        ),
        reverse=True,
    )

    target_dt = as_berlin(archived_at)
    if target_dt is None:
        return rows[0]

    best_row: sqlite3.Row | None = None
    best_delta: float | None = None
    for rr in rows:
        cand_dt = as_berlin(rr["completed_at"])
        if cand_dt is None:
            continue
        delta = abs((cand_dt - target_dt).total_seconds())
        if best_delta is None or delta < best_delta:
            best_row = rr
            best_delta = delta
    return best_row or rows[0]


def _legacy_table_exists(table_name: str) -> bool:
    row = db_core.db_exec(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?;",
        (str(table_name),),
        fetchone=True,
    )
    return row is not None


def _legacy_columns(table_name: str) -> set[str]:
    conn = db_core.get_conn()
    rows = conn.execute(f"PRAGMA table_info({table_name});").fetchall()
    return {str(row["name"] if isinstance(row, sqlite3.Row) else row[1]) for row in rows}


def _select_legacy_expr(columns: set[str], column: str, fallback: str = "NULL") -> str:
    return column if column in columns else f"{fallback} AS {column}"


def _migrate_and_drop_legacy_restore_archive() -> None:
    legacy_table = "archive_done_14d"
    if not _legacy_table_exists(legacy_table):
        return

    columns = _legacy_columns(legacy_table)
    select_parts = [
        _select_legacy_expr(columns, "id"),
        _select_legacy_expr(columns, "fahrzeug"),
        _select_legacy_expr(columns, "friststufe"),
        _select_legacy_expr(columns, "zusatzarbeiten"),
        _select_legacy_expr(columns, "archive_id"),
        _select_legacy_expr(columns, "arbeitsplatz"),
        _select_legacy_expr(columns, "ap_pdf"),
        _select_legacy_expr(columns, "last_problem_note"),
        _select_legacy_expr(columns, "last_problem_at"),
        _select_legacy_expr(columns, "initial_fertig"),
        _select_legacy_expr(columns, "ecm3_fertig"),
        _select_legacy_expr(columns, "gewerke"),
        _select_legacy_expr(columns, "zusatz_done"),
        _select_legacy_expr(columns, "frist_done"),
        _select_legacy_expr(columns, "planning_order_id"),
        _select_legacy_expr(columns, "source_system"),
        _select_legacy_expr(columns, "archived_open_task_id"),
        _select_legacy_expr(columns, "expires_at"),
        _select_legacy_expr(columns, "archived_at"),
    ]
    rows = db_core.db_exec(f"SELECT {', '.join(select_parts)} FROM {legacy_table};", fetch=True) or []
    for rr in rows:
        archive_id = int(rr["archive_id"] or 0)
        arch_row = None
        if archive_id <= 0:
            arch_row = _find_best_archive_row_for_recent(rr["fahrzeug"], rr["friststufe"], rr["archived_at"])
            archive_id = int(arch_row["id"]) if arch_row is not None else 0
        if archive_id <= 0:
            continue
        db_core.db_exec(
            """
            UPDATE archive
            SET zusatzarbeiten=CASE WHEN zusatzarbeiten IS NULL OR trim(zusatzarbeiten)='' THEN ? ELSE zusatzarbeiten END,
                arbeitsplatz=CASE WHEN arbeitsplatz IS NULL OR trim(arbeitsplatz)='' THEN ? ELSE arbeitsplatz END,
                ap_pdf=CASE WHEN ap_pdf IS NULL OR trim(ap_pdf)='' THEN ? ELSE ap_pdf END,
                last_problem_note=CASE WHEN last_problem_note IS NULL OR trim(last_problem_note)='' THEN ? ELSE last_problem_note END,
                last_problem_at=CASE WHEN last_problem_at IS NULL OR trim(last_problem_at)='' THEN ? ELSE last_problem_at END,
                initial_fertig=CASE WHEN initial_fertig IS NULL OR lower(trim(initial_fertig)) IN ('', 'nan', 'nat', 'none', 'null') THEN ? ELSE initial_fertig END,
                ecm3_fertig=CASE WHEN ecm3_fertig IS NULL OR trim(ecm3_fertig)='' THEN ? ELSE ecm3_fertig END,
                gewerke=CASE WHEN gewerke IS NULL OR trim(gewerke)='' THEN ? ELSE gewerke END,
                zusatz_done=CASE WHEN zusatz_done IS NULL OR trim(zusatz_done)='' THEN ? ELSE zusatz_done END,
                frist_done=CASE WHEN frist_done IS NULL OR trim(frist_done)='' THEN ? ELSE frist_done END,
                planning_order_id=COALESCE(planning_order_id, ?),
                source_system=CASE WHEN source_system IS NULL OR trim(source_system)='' THEN ? ELSE source_system END,
                archived_open_task_id=COALESCE(archived_open_task_id, ?),
                restore_until=CASE WHEN restore_until IS NULL OR trim(restore_until)='' THEN ? ELSE restore_until END
            WHERE id=?;
            """,
            (
                rr["zusatzarbeiten"],
                rr["arbeitsplatz"],
                rr["ap_pdf"],
                rr["last_problem_note"],
                rr["last_problem_at"],
                rr["initial_fertig"],
                rr["ecm3_fertig"],
                rr["gewerke"],
                rr["zusatz_done"],
                rr["frist_done"],
                rr["planning_order_id"],
                rr["source_system"],
                rr["archived_open_task_id"],
                rr["expires_at"],
                archive_id,
            ),
            commit=True,
        )

    db_core.db_exec(f"DROP TABLE IF EXISTS {legacy_table};", commit=True)


def dedupe_open_tasks_by_sig() -> None:
    db_core.db_exec(
        """
        DELETE FROM open_tasks
        WHERE id IN (
            SELECT t1.id
            FROM open_tasks t1
            JOIN open_tasks t2
              ON t1.sig = t2.sig
             AND t1.sig IS NOT NULL
             AND t1.sig <> ''
             AND t1.id > t2.id
        );
        """,
        commit=True,
    )


def _ensure_ecm4_plan_history_schema(conn: sqlite3.Connection | None = None) -> None:
    local_conn = conn or db_core.get_conn()
    cur = local_conn.cursor()
    try:
        try:
            cur.execute("ALTER TABLE ecm4_plan ADD COLUMN imported_at TEXT;")
        except Exception:
            pass
        try:
            cur.execute("ALTER TABLE ecm4_plan ADD COLUMN source_name TEXT;")
        except Exception:
            pass

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ecm4_plan_hist (
                slot_start  TEXT NOT NULL,
                orig_date   TEXT,
                zeit        TEXT,
                hinweis     TEXT,
                area        TEXT NOT NULL,
                fahrzeug    TEXT,
                imported_at TEXT,
                source_name TEXT
            );
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ecm4_plan_hist_imported ON ecm4_plan_hist (imported_at);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ecm4_plan_hist_slot ON ecm4_plan_hist (slot_start);")
        local_conn.commit()
    finally:
        cur.close()


def init_db() -> None:
    db_core.db_exec(
        """
        CREATE TABLE IF NOT EXISTS open_tasks (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            fahrzeug          TEXT NOT NULL,
            friststufe        TEXT,
            anfang            TEXT,
            fertig            TEXT,
            ecm3_fertig       TEXT,
            arbeitsplatz      TEXT,
            last_problem_note TEXT,
            last_problem_at   TEXT,
            sig               TEXT
        );
        """,
        commit=True,
    )
    db_core.ensure_column("open_tasks", "zusatzarbeiten", "TEXT")
    db_core.ensure_column("open_tasks", "gewerke", "TEXT")
    db_core.ensure_column("open_tasks", "ap_pdf", "TEXT")
    db_core.ensure_column("open_tasks", "initial_fertig", "TEXT")
    db_core.ensure_column("open_tasks", "ecm3_fertig", "TEXT")
    db_core.ensure_column("open_tasks", "zusatz_done", "TEXT")
    db_core.ensure_column("open_tasks", "frist_done", "TEXT")
    db_core.ensure_column("open_tasks", "frist_in_progress", "TEXT")
    db_core.ensure_column("open_tasks", "planning_order_id", "INTEGER")
    db_core.ensure_column("open_tasks", "source_system", "TEXT")

    db_core.db_exec(
        """
        CREATE TABLE IF NOT EXISTS archive (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            fahrzeug          TEXT NOT NULL,
            friststufe        TEXT,
            anfang            TEXT,
            fertig            TEXT,
            last_problem_note TEXT,
            completed_at      TEXT,
            status            TEXT,
            status_ecm3       TEXT,
            initial_fertig    TEXT
        );
        """,
        commit=True,
    )
    db_core.ensure_column("archive", "status_ecm3", "TEXT")
    db_core.ensure_column("archive", "zusatzarbeiten", "TEXT")
    db_core.ensure_column("archive", "gewerke", "TEXT")
    db_core.ensure_column("archive", "arbeitsplatz", "TEXT")
    db_core.ensure_column("archive", "ap_pdf", "TEXT")
    db_core.ensure_column("archive", "last_problem_at", "TEXT")
    db_core.ensure_column("archive", "ecm3_fertig", "TEXT")
    db_core.ensure_column("archive", "zusatz_done", "TEXT")
    db_core.ensure_column("archive", "frist_done", "TEXT")
    db_core.ensure_column("archive", "planning_order_id", "INTEGER")
    db_core.ensure_column("archive", "source_system", "TEXT")
    db_core.ensure_column("archive", "archived_open_task_id", "INTEGER")
    db_core.ensure_column("archive", "restore_until", "TEXT")
    db_core.ensure_column("archive", "restored_at", "TEXT")
    _migrate_and_drop_legacy_restore_archive()
    db_core.db_exec(
        """
        CREATE TABLE IF NOT EXISTS shopfloorboard_5s (
            iso_year      INTEGER NOT NULL,
            iso_week      INTEGER NOT NULL,
            fruehschicht  TEXT,
            spaetschicht  TEXT,
            nachtschicht  TEXT,
            updated_at    TEXT,
            PRIMARY KEY (iso_year, iso_week)
        );
        """,
        commit=True,
    )
    db_core.db_exec(
        """
        CREATE TABLE IF NOT EXISTS ausseneinsatz_plan (
            plan_date      TEXT PRIMARY KEY,
            assignment_key TEXT,
            updated_at     TEXT
        );
        """,
        commit=True,
    )
    db_core.db_exec(
        """
        CREATE TABLE IF NOT EXISTS ecm4_plan (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            slot_start   TEXT NOT NULL,
            orig_date    TEXT,
            zeit         TEXT,
            hinweis      TEXT,
            area         TEXT NOT NULL,
            fahrzeug     TEXT
        );
        """,
        commit=True,
    )
    db_core.ensure_column("ecm4_plan", "imported_at", "TEXT")
    db_core.ensure_column("ecm4_plan", "source_name", "TEXT")
    _ensure_ecm4_plan_history_schema()
    db_core.db_exec(
        """
        CREATE TABLE IF NOT EXISTS rws_week_plan (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            fahrzeug     TEXT NOT NULL,
            start_dt     TEXT NOT NULL,
            end_dt       TEXT NOT NULL,
            imported_at  TEXT,
            source_name  TEXT
        );
        """,
        commit=True,
    )
    db_core.db_exec(
        """
        CREATE TABLE IF NOT EXISTS lwu_reminder_log (
            id          TEXT PRIMARY KEY,
            fahrzeug    TEXT,
            area        TEXT,
            planned_at  TEXT,
            sent_at     TEXT
        );
        """,
        commit=True,
    )
    db_core.db_exec(
        """
        CREATE TABLE IF NOT EXISTS prio_side_state (
            area        TEXT NOT NULL,
            vehicle_key TEXT NOT NULL,
            row_end     TEXT NOT NULL,
            checked     INTEGER NOT NULL DEFAULT 0,
            updated_at  TEXT,
            expires_at  TEXT NOT NULL,
            PRIMARY KEY (area, vehicle_key, row_end)
        );
        """,
        commit=True,
    )
    db_core.db_exec(
        """
        CREATE TABLE IF NOT EXISTS gleisplan_assignments (
            track_id       TEXT PRIMARY KEY,
            vehicle_number TEXT NOT NULL,
            updated_at     TEXT
        );
        """,
        commit=True,
    )
    db_core.db_exec(
        """
        CREATE TABLE IF NOT EXISTS gleisplan_layout_items (
            item_id    TEXT PRIMARY KEY,
            item_type  TEXT NOT NULL,
            label      TEXT NOT NULL,
            title      TEXT,
            x_pct      REAL NOT NULL DEFAULT 10,
            y_pct      REAL NOT NULL DEFAULT 10,
            w_pct      REAL NOT NULL DEFAULT 12,
            h_pct      REAL NOT NULL DEFAULT 8,
            rotation   REAL NOT NULL DEFAULT 0,
            color      TEXT,
            curve_radius REAL NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT
        );
        """,
        commit=True,
    )
    db_core.ensure_column("gleisplan_layout_items", "curve_radius", "REAL NOT NULL DEFAULT 0")
    db_core.db_exec(
        """
        CREATE TABLE IF NOT EXISTS gleisplan_connections (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            source_item_id TEXT NOT NULL,
            target_item_id TEXT NOT NULL,
            source_port    TEXT,
            target_port    TEXT,
            label          TEXT,
            connection_type TEXT,
            curve_pct      REAL NOT NULL DEFAULT 0,
            path_points_json TEXT,
            route_json     TEXT,
            updated_at     TEXT
        );
        """,
        commit=True,
    )
    db_core.ensure_column("gleisplan_connections", "curve_pct", "REAL NOT NULL DEFAULT 0")
    db_core.ensure_column("gleisplan_connections", "source_port", "TEXT")
    db_core.ensure_column("gleisplan_connections", "target_port", "TEXT")
    db_core.ensure_column("gleisplan_connections", "path_points_json", "TEXT")
    db_core.ensure_column("gleisplan_connections", "route_json", "TEXT")
    db_core.db_exec(
        """
        CREATE TABLE IF NOT EXISTS gleisplan_settings (
            setting_key  TEXT PRIMARY KEY,
            setting_json TEXT NOT NULL,
            updated_at   TEXT
        );
        """,
        commit=True,
    )
    db_core.db_exec(
        """
        CREATE TABLE IF NOT EXISTS gleisplan_hall_tracks (
            area_code      TEXT PRIMARY KEY,
            track_label    TEXT NOT NULL,
            position_label TEXT,
            workshop_area  TEXT,
            sync_enabled   INTEGER NOT NULL DEFAULT 1,
            updated_at     TEXT
        );
        """,
        commit=True,
    )
    db_core.db_exec(
        """
        CREATE TABLE IF NOT EXISTS workshop_hall_tiles (
            tile_key      TEXT PRIMARY KEY,
            tile_type     TEXT NOT NULL DEFAULT 'area',
            display_label TEXT NOT NULL,
            content_area  TEXT,
            active        INTEGER NOT NULL DEFAULT 1,
            highlighted   INTEGER NOT NULL DEFAULT 1,
            sort_order    INTEGER NOT NULL DEFAULT 0,
            updated_at    TEXT
        );
        """,
        commit=True,
    )
    db_core.db_exec(
        """
        CREATE TABLE IF NOT EXISTS workshop_hall_texts (
            text_key   TEXT PRIMARY KEY,
            text_value TEXT NOT NULL,
            updated_at TEXT
        );
        """,
        commit=True,
    )
    db_core.db_exec(
        """
        CREATE TABLE IF NOT EXISTS work_package_series (
            name       TEXT PRIMARY KEY,
            sort_order INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT
        );
        """,
        commit=True,
    )
    db_core.db_exec(
        """
        CREATE TABLE IF NOT EXISTS work_package_frist_levels (
            baureihe   TEXT NOT NULL,
            friststufe TEXT NOT NULL,
            trigger_type TEXT NOT NULL DEFAULT 'time',
            active INTEGER NOT NULL DEFAULT 1,
            sort_order INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT,
            PRIMARY KEY (baureihe, friststufe)
        );
        """,
        commit=True,
    )
    db_core.ensure_column("work_package_frist_levels", "trigger_type", "TEXT NOT NULL DEFAULT 'time'")
    db_core.ensure_column("work_package_frist_levels", "active", "INTEGER NOT NULL DEFAULT 1")
    db_core.db_exec(
        """
        CREATE TABLE IF NOT EXISTS work_packages (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            baureihe         TEXT NOT NULL,
            friststufe       TEXT NOT NULL,
            title            TEXT NOT NULL,
            employee_count   INTEGER NOT NULL DEFAULT 1,
            duration_minutes REAL NOT NULL DEFAULT 0,
            sort_order       INTEGER NOT NULL DEFAULT 0,
            updated_at       TEXT
        );
        """,
        commit=True,
    )
    db_core.db_exec(
        """
        CREATE TABLE IF NOT EXISTS vehicle_series_map (
            vehicle_number TEXT PRIMARY KEY,
            vehicle_key    TEXT NOT NULL,
            baureihe       TEXT NOT NULL,
            updated_at     TEXT
        );
        """,
        commit=True,
    )
    db_core.db_exec(
        """
        CREATE TABLE IF NOT EXISTS app_users (
            username         TEXT PRIMARY KEY,
            display_name     TEXT,
            password_hash    TEXT NOT NULL,
            password_plain   TEXT DEFAULT '',
            role             TEXT NOT NULL DEFAULT 'standard',
            permissions_json TEXT NOT NULL DEFAULT '{}',
            active           INTEGER NOT NULL DEFAULT 1,
            updated_at       TEXT
        );
        """,
        commit=True,
    )
    db_core.ensure_column("app_users", "password_plain", "TEXT DEFAULT ''")
    db_core.db_exec("CREATE INDEX IF NOT EXISTS idx_open_fzg_frist ON open_tasks (fahrzeug, friststufe);", commit=True)
    db_core.db_exec("CREATE INDEX IF NOT EXISTS idx_open_sig ON open_tasks (sig);", commit=True)
    db_core.db_exec("CREATE INDEX IF NOT EXISTS idx_open_planning_order ON open_tasks (planning_order_id);", commit=True)
    db_core.db_exec("CREATE INDEX IF NOT EXISTS idx_archive_completed ON archive (completed_at);", commit=True)
    db_core.db_exec("CREATE INDEX IF NOT EXISTS idx_archive_restore ON archive (restore_until, restored_at);", commit=True)
    db_core.db_exec("CREATE INDEX IF NOT EXISTS idx_archive_planning_order ON archive (planning_order_id);", commit=True)
    db_core.db_exec("CREATE INDEX IF NOT EXISTS idx_ecm4_slot ON ecm4_plan (slot_start);", commit=True)
    db_core.db_exec("CREATE INDEX IF NOT EXISTS idx_ecm4_area ON ecm4_plan (area);", commit=True)
    db_core.db_exec("CREATE INDEX IF NOT EXISTS idx_ecm4_imported ON ecm4_plan (imported_at);", commit=True)
    db_core.db_exec("CREATE INDEX IF NOT EXISTS idx_rws_week_start ON rws_week_plan (start_dt);", commit=True)
    db_core.db_exec("CREATE INDEX IF NOT EXISTS idx_lwu_rem_planned ON lwu_reminder_log (planned_at);", commit=True)
    db_core.db_exec("CREATE INDEX IF NOT EXISTS idx_prio_side_exp ON prio_side_state (expires_at);", commit=True)
    db_core.db_exec("CREATE INDEX IF NOT EXISTS idx_work_package_frist_levels_lookup ON work_package_frist_levels (baureihe, sort_order, friststufe);", commit=True)
    db_core.db_exec("CREATE INDEX IF NOT EXISTS idx_work_packages_lookup ON work_packages (baureihe, friststufe, sort_order, id);", commit=True)
    db_core.db_exec("CREATE INDEX IF NOT EXISTS idx_vehicle_series_map_key ON vehicle_series_map (vehicle_key);", commit=True)
    _normalize_db_datetime_placeholders()


def _normalize_db_datetime_placeholders() -> None:
    datetime_columns = {
        "open_tasks": ("anfang", "fertig", "ecm3_fertig", "last_problem_at", "initial_fertig"),
        "archive": ("anfang", "fertig", "completed_at", "initial_fertig", "last_problem_at", "ecm3_fertig", "restore_until", "restored_at"),
        "ecm4_plan": ("slot_start", "orig_date", "imported_at"),
        "ecm4_plan_hist": ("slot_start", "orig_date", "imported_at"),
        "rws_week_plan": ("start_dt", "end_dt", "imported_at"),
        "lwu_reminder_log": ("planned_at", "sent_at"),
        "prio_side_state": ("updated_at", "expires_at"),
        "gleisplan_assignments": ("updated_at",),
        "gleisplan_layout_items": ("updated_at",),
        "gleisplan_connections": ("updated_at",),
        "gleisplan_hall_tracks": ("updated_at",),
        "workshop_hall_tiles": ("updated_at",),
        "workshop_hall_texts": ("updated_at",),
        "ausseneinsatz_plan": ("updated_at",),
        "shopfloorboard_5s": ("updated_at",),
        "work_package_series": ("updated_at",),
        "work_package_frist_levels": ("updated_at",),
        "work_packages": ("updated_at",),
        "vehicle_series_map": ("updated_at",),
        "app_users": ("updated_at",),
    }
    changed = False
    conn = db_core.get_conn()
    with db_core.DB_WRITE_LOCK:
        cur = conn.cursor()
        try:
            for table_name, columns in datetime_columns.items():
                for column_name in columns:
                    cur.execute(
                        f"""
                        UPDATE {table_name}
                        SET {column_name}=NULL
                        WHERE {column_name} IS NOT NULL
                          AND lower(trim({column_name})) IN ('', 'nan', 'nat', 'none', 'null');
                        """
                    )
                    changed = changed or int(cur.rowcount or 0) > 0
            conn.commit()
        finally:
            cur.close()
    if changed:
        db_core.bump_data_version()


def _vacuum_db_best_effort() -> None:
    vac_conn: sqlite3.Connection | None = None
    try:
        vac_conn = sqlite3.connect(DB_PATH, timeout=30.0)
        vac_conn.execute("PRAGMA busy_timeout=30000;")
        vac_conn.execute("VACUUM;")
        vac_conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        vac_conn.commit()
    except Exception as ex:
        logger.warning("VACUUM nach reset_all übersprungen: %s", ex)
    finally:
        try:
            if vac_conn is not None:
                vac_conn.close()
        except Exception:
            pass


def reset_all() -> None:
    for table in (
        "open_tasks",
        "archive",
        "shopfloorboard_5s",
        "ecm4_plan",
        "ecm4_plan_hist",
        "rws_week_plan",
        "lwu_reminder_log",
        "prio_side_state",
        "gleisplan_assignments",
        "gleisplan_layout_items",
        "gleisplan_connections",
        "gleisplan_hall_tracks",
    ):
        db_core.db_exec(f"DELETE FROM {table};", commit=True)
    _vacuum_db_best_effort()
