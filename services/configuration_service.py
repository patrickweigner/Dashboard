from __future__ import annotations

from datetime import datetime
import re
import threading
from typing import Any


_DEFAULTS_SEEDED = False
_LOOKUP_CACHE_LOCK = threading.Lock()
_LOOKUP_CACHE_VERSION: int | None = None
_VEHICLE_SERIES_CACHE: dict[tuple[int, str], str] = {}
_WORK_PACKAGE_TITLES_CACHE: dict[tuple[int, str, str], tuple[str, ...]] = {}
_CONFIG_SCHEMA_ENSURED = False

FRIST_TRIGGER_DEFAULT = "time"
GENERAL_SERIES_NAME = "Allgemein"
GENERAL_FRIST_LEVEL = "Allgemein"
FRIST_TRIGGER_OPTIONS: dict[str, str] = {
    "kilometer": "Kilometerfrist",
    "time": "Zeitfrist",
    "operating_hours": "Betriebsstundenfrist",
}


def configure(**deps) -> None:
    globals().update(deps)


def _now_iso() -> str:
    try:
        return now_berlin().isoformat(timespec="seconds")
    except Exception:
        return datetime.now().isoformat(timespec="seconds")


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _case_key(value: Any) -> str:
    return _clean_text(value).casefold()


def _clean_trigger_type(value: Any) -> str:
    raw = _case_key(value)
    aliases = {
        "kilometer": "kilometer",
        "kilometerfrist": "kilometer",
        "km": "kilometer",
        "time": "time",
        "zeit": "time",
        "zeitfrist": "time",
        "betriebsstunden": "operating_hours",
        "betriebsstundenfrist": "operating_hours",
        "operating_hours": "operating_hours",
        "operatinghours": "operating_hours",
    }
    return aliases.get(raw, FRIST_TRIGGER_DEFAULT)


def _require_trigger_type(value: Any) -> str:
    if not _clean_text(value):
        raise ValueError("Bitte eine Fristauslösung auswählen.")
    return _clean_trigger_type(value)


def _is_general_series_name(value: Any) -> bool:
    return _case_key(value) == _case_key(GENERAL_SERIES_NAME)


def frist_trigger_label(value: Any) -> str:
    return FRIST_TRIGGER_OPTIONS.get(_clean_trigger_type(value), FRIST_TRIGGER_OPTIONS[FRIST_TRIGGER_DEFAULT])


def _column_exists(table: str, column: str) -> bool:
    rows = db_exec(f"PRAGMA table_info({table});", fetch=True) or []
    return any(str(row["name"] if "name" in row.keys() else row[1]) == column for row in rows)


def _ensure_configuration_schema() -> None:
    global _CONFIG_SCHEMA_ENSURED
    if _CONFIG_SCHEMA_ENSURED:
        return
    if not _column_exists("work_package_frist_levels", "trigger_type"):
        db_exec(
            "ALTER TABLE work_package_frist_levels ADD COLUMN trigger_type TEXT NOT NULL DEFAULT 'time';",
            commit=True,
        )
    if not _column_exists("work_package_frist_levels", "active"):
        db_exec(
            "ALTER TABLE work_package_frist_levels ADD COLUMN active INTEGER NOT NULL DEFAULT 1;",
            commit=True,
        )
    _CONFIG_SCHEMA_ENSURED = True


def _normalize_vehicle_key(vehicle_number: Any) -> str:
    raw = _clean_text(vehicle_number)
    if not raw:
        return ""
    try:
        norm = _norm_vehicle(raw)
    except Exception:
        norm = ""
    key = str(norm or raw).strip()
    key = re.sub(r"^(?:ET|VT)(?=\d)", "", key, flags=re.I)
    return key.casefold()


def _vehicle_number_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    raw = _clean_text(row.get("vehicle_key") or row.get("vehicle_number"))
    key = _normalize_vehicle_key(raw) or raw.casefold()
    numbers = tuple(int(part) for part in re.findall(r"\d+", key))
    return (numbers, key, _case_key(row.get("vehicle_number")))


def _duration_is_half_hour_step(duration_minutes: float) -> bool:
    return abs((float(duration_minutes) / 30.0) - round(float(duration_minutes) / 30.0)) < 0.000001


def _duration_hours_label(duration_minutes: Any) -> str:
    try:
        hours = float(duration_minutes) / 60.0
    except Exception:
        hours = 0.0
    rounded_full_hour = round(hours)
    if abs(hours - rounded_full_hour) < 0.000001:
        return f"{int(rounded_full_hour)} h"
    return f"{hours:.1f}".replace(".", ",") + " h"


def _work_package_check_label(row: dict[str, Any]) -> str:
    title = _clean_text(row.get("title"))
    if not title:
        return ""
    try:
        employees = int(row.get("employee_count") or 0)
    except Exception:
        employees = 0
    frist = _clean_text(row.get("display_friststufe") or row.get("friststufe"))
    show_frist = bool(row.get("show_frist_suffix"))
    frist_suffix = f" ({frist})" if show_frist and frist else ""
    try:
        duration_minutes = float(row.get("duration_minutes") or 0)
    except Exception:
        duration_minutes = 0.0
    if employees <= 0 and duration_minutes <= 0:
        return f"{title}{frist_suffix}"
    return f"{title}{frist_suffix}\n{employees} Ma - {_duration_hours_label(row.get('duration_minutes'))}"


def _lookup_cache_version() -> int:
    version_fn = globals().get("_current_data_version")
    if not callable(version_fn):
        from core import db as _core_db

        version_fn = _core_db._current_data_version
    try:
        from core import db as _core_db

        if getattr(_core_db, "_DB_FILE_STATE_TOKEN", None) is not None:
            version = int(getattr(_core_db, "_DATA_VERSION"))
        else:
            version = int(version_fn())
    except Exception:
        version = int(version_fn())
    global _LOOKUP_CACHE_VERSION
    with _LOOKUP_CACHE_LOCK:
        if _LOOKUP_CACHE_VERSION != version:
            # Configuration lookups depend on DB-backed settings; the data version
            # counter changes after writes or observed external DB changes, so stale
            # entries are dropped without re-checking the file state for every row.
            _VEHICLE_SERIES_CACHE.clear()
            _WORK_PACKAGE_TITLES_CACHE.clear()
            _LOOKUP_CACHE_VERSION = version
    return version


def _ensure_default_configuration() -> None:
    global _DEFAULTS_SEEDED
    _ensure_configuration_schema()
    if _DEFAULTS_SEEDED:
        return

    now = _now_iso()
    db_exec(
        """
        INSERT INTO work_package_series(name, sort_order, updated_at)
        VALUES (?, 0, ?)
        ON CONFLICT(name) DO UPDATE SET
            sort_order=CASE WHEN sort_order IS NULL OR sort_order > 0 THEN 0 ELSE sort_order END,
            updated_at=excluded.updated_at;
        """,
        (GENERAL_SERIES_NAME, now),
        commit=True,
    )
    db_exec(
        """
        INSERT OR IGNORE INTO work_package_frist_levels(baureihe, friststufe, trigger_type, active, sort_order, updated_at)
        VALUES (?, ?, ?, 1, 10, ?);
        """,
        (GENERAL_SERIES_NAME, GENERAL_FRIST_LEVEL, FRIST_TRIGGER_DEFAULT, now),
        commit=True,
    )
    rows = db_exec(
        """
        SELECT baureihe, friststufe
        FROM work_packages
        WHERE TRIM(COALESCE(baureihe, '')) <> '';
        """,
        fetch=True,
    ) or []
    for row in rows:
        series = _clean_text(row["baureihe"])
        frist = _clean_text(row["friststufe"])
        if not series:
            continue
        db_exec(
            """
            INSERT OR IGNORE INTO work_package_series(name, sort_order, updated_at)
            VALUES (?, 1000, ?);
            """,
            (series, now),
            commit=True,
        )
        if frist:
            db_exec(
                """
                INSERT OR IGNORE INTO work_package_frist_levels(baureihe, friststufe, trigger_type, sort_order, updated_at)
                VALUES (?, ?, ?, 1000, ?);
                """,
                (series, frist, FRIST_TRIGGER_DEFAULT, now),
                commit=True,
            )

    rows = db_exec(
        """
        SELECT DISTINCT baureihe
        FROM vehicle_series_map
        WHERE TRIM(COALESCE(baureihe, '')) <> '';
        """,
        fetch=True,
    ) or []
    for row in rows:
        series = _clean_text(row["baureihe"])
        if series:
            db_exec(
                """
                INSERT OR IGNORE INTO work_package_series(name, sort_order, updated_at)
                VALUES (?, 1000, ?);
                """,
                (series, now),
                commit=True,
            )

    copy_series_configuration("4748 Desiro ML", "4746 Desiro ML")
    _DEFAULTS_SEEDED = True


def list_series() -> list[str]:
    _ensure_default_configuration()
    rows = db_exec(
        """
        SELECT name
        FROM work_package_series
        ORDER BY CASE WHEN lower(trim(name))=lower(trim(?)) THEN 0 ELSE 1 END, sort_order ASC, name ASC;
        """,
        (GENERAL_SERIES_NAME,),
        fetch=True,
    ) or []
    return [_clean_text(row["name"]) for row in rows if _clean_text(row["name"])]


def _resolve_series_name(value: Any) -> str:
    _ensure_default_configuration()
    raw = _clean_text(value)
    if not raw:
        return ""
    row = db_exec(
        """
        SELECT name
        FROM work_package_series
        WHERE lower(trim(name))=lower(trim(?))
        LIMIT 1;
        """,
        (raw,),
        fetchone=True,
    )
    return _clean_text(row["name"]) if row else ""


def add_series(name: str) -> str:
    _ensure_default_configuration()
    series = _clean_text(name)
    if not series:
        raise ValueError("Bitte einen Namen für die Baureihe eintragen.")
    if _resolve_series_name(series):
        raise ValueError("Diese Baureihe ist bereits vorhanden.")
    row = db_exec("SELECT COALESCE(MAX(sort_order), 0) AS max_sort FROM work_package_series;", fetchone=True)
    try:
        sort_order = int(row["max_sort"] or 0) + 10 if row else 10
    except Exception:
        sort_order = 10
    db_exec(
        """
        INSERT INTO work_package_series(name, sort_order, updated_at)
        VALUES (?, ?, ?);
        """,
        (series, sort_order, _now_iso()),
        commit=True,
    )
    return series


def list_frist_levels(baureihe: str) -> list[str]:
    _ensure_default_configuration()
    series = _resolve_series_name(baureihe)
    if not series:
        return []
    rows = db_exec(
        """
        SELECT friststufe
        FROM work_package_frist_levels
        WHERE baureihe=?
        ORDER BY sort_order ASC, friststufe ASC;
        """,
        (series,),
        fetch=True,
    ) or []
    return [_clean_text(row["friststufe"]) for row in rows if _clean_text(row["friststufe"])]


def list_frist_level_configs(baureihe: str) -> list[dict[str, Any]]:
    _ensure_default_configuration()
    series = _resolve_series_name(baureihe)
    if not series:
        return []
    rows = db_exec(
        """
        SELECT friststufe, trigger_type, active, sort_order, updated_at
        FROM work_package_frist_levels
        WHERE baureihe=?
        ORDER BY sort_order ASC, friststufe ASC;
        """,
        (series,),
        fetch=True,
    ) or []
    return [
        {
            "friststufe": _clean_text(row["friststufe"]),
            "trigger_type": _clean_trigger_type(row["trigger_type"]),
            "trigger_label": frist_trigger_label(row["trigger_type"]),
            "active": bool(row["active"]),
            "sort_order": int(row["sort_order"] or 0),
            "updated_at": _clean_text(row["updated_at"]),
        }
        for row in rows
        if _clean_text(row["friststufe"])
    ]


def _resolve_frist_level(baureihe: str, value: Any) -> str:
    series = _resolve_series_name(baureihe)
    raw = _clean_text(value)
    if not series or not raw:
        return ""
    row = db_exec(
        """
        SELECT friststufe
        FROM work_package_frist_levels
        WHERE baureihe=? AND lower(trim(friststufe))=lower(trim(?))
        LIMIT 1;
        """,
        (series, raw),
        fetchone=True,
    )
    return _clean_text(row["friststufe"]) if row else ""


def add_frist_level(baureihe: str, friststufe: str, trigger_type: str = "") -> str:
    _ensure_default_configuration()
    series = _resolve_series_name(baureihe)
    frist = _clean_text(friststufe)
    trigger = _require_trigger_type(trigger_type)
    if not series:
        raise ValueError("Bitte zuerst eine gültige Baureihe auswählen.")
    if _is_general_series_name(series):
        raise ValueError("In Allgemein koennen keine Friststufen erstellt werden.")
    if not frist:
        raise ValueError("Bitte eine Friststufe eintragen.")
    if _resolve_frist_level(series, frist):
        raise ValueError("Diese Friststufe ist für die Baureihe bereits vorhanden.")
    row = db_exec(
        """
        SELECT COALESCE(MAX(sort_order), 0) AS max_sort
        FROM work_package_frist_levels
        WHERE baureihe=?;
        """,
        (series,),
        fetchone=True,
    )
    try:
        sort_order = int(row["max_sort"] or 0) + 10 if row else 10
    except Exception:
        sort_order = 10
    db_exec(
        """
        INSERT INTO work_package_frist_levels(baureihe, friststufe, trigger_type, sort_order, updated_at)
        VALUES (?, ?, ?, ?, ?);
        """,
        (series, frist, trigger, sort_order, _now_iso()),
        commit=True,
    )
    return frist


def update_frist_level_trigger_type(baureihe: str, friststufe: str, trigger_type: str) -> bool:
    _ensure_default_configuration()
    series = _resolve_series_name(baureihe)
    is_general = _is_general_series_name(series)
    frist = _resolve_frist_level(series, GENERAL_FRIST_LEVEL if is_general else friststufe)
    if not series:
        raise ValueError("Ungültige Baureihe.")
    if not frist:
        raise ValueError("Friststufe nicht gefunden.")
    db_exec(
        """
        UPDATE work_package_frist_levels
        SET trigger_type=?, updated_at=?
        WHERE baureihe=? AND friststufe=?;
        """,
        (_clean_trigger_type(trigger_type), _now_iso(), series, frist),
        commit=True,
    )
    return True


def update_frist_level_active(baureihe: str, friststufe: str, active: bool) -> bool:
    _ensure_default_configuration()
    series = _resolve_series_name(baureihe)
    frist = _resolve_frist_level(series, friststufe)
    if not series:
        raise ValueError("Ungültige Baureihe.")
    if not frist:
        raise ValueError("Friststufe nicht gefunden.")
    db_exec(
        """
        UPDATE work_package_frist_levels
        SET active=?, updated_at=?
        WHERE baureihe=? AND friststufe=?;
        """,
        (1 if bool(active) else 0, _now_iso(), series, frist),
        commit=True,
    )
    return True


def set_all_frist_levels_active(baureihe: str, active: bool) -> int:
    _ensure_default_configuration()
    series = _resolve_series_name(baureihe)
    if not series:
        raise ValueError("Ungültige Baureihe.")
    db_exec(
        """
        UPDATE work_package_frist_levels
        SET active=?, updated_at=?
        WHERE baureihe=?;
        """,
        (1 if bool(active) else 0, _now_iso(), series),
        commit=True,
    )
    row = db_exec(
        "SELECT COUNT(*) AS level_count FROM work_package_frist_levels WHERE baureihe=?;",
        (series,),
        fetchone=True,
    )
    try:
        return int(row["level_count"] or 0) if row else 0
    except Exception:
        return 0


def update_frist_level_config(baureihe: str, old_friststufe: str, new_friststufe: str, trigger_type: str) -> str:
    _ensure_default_configuration()
    series = _resolve_series_name(baureihe)
    old_frist = _resolve_frist_level(series, old_friststufe)
    new_frist = _clean_text(new_friststufe)
    trigger = _clean_trigger_type(trigger_type)
    if not series:
        raise ValueError("Ungültige Baureihe.")
    if not old_frist:
        raise ValueError("Friststufe nicht gefunden.")
    if not new_frist:
        raise ValueError("Bitte eine Friststufe eintragen.")

    existing = _resolve_frist_level(series, new_frist)
    if existing and _case_key(existing) != _case_key(old_frist):
        raise ValueError("Diese Friststufe ist für die Baureihe bereits vorhanden.")

    now = _now_iso()
    conn = get_conn()
    with _DB_WRITE_LOCK:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                UPDATE work_package_frist_levels
                SET friststufe=?, trigger_type=?, updated_at=?
                WHERE baureihe=? AND friststufe=?;
                """,
                (new_frist, trigger, now, series, old_frist),
            )
            cur.execute(
                """
                UPDATE work_packages
                SET friststufe=?, updated_at=?
                WHERE baureihe=? AND friststufe=?;
                """,
                (new_frist, now, series, old_frist),
            )
            conn.commit()
        finally:
            cur.close()
    bump_data_version()
    return new_frist


def delete_frist_level(baureihe: str, friststufe: str) -> bool:
    _ensure_default_configuration()
    series = _resolve_series_name(baureihe)
    frist = _resolve_frist_level(series, friststufe)
    if not series:
        raise ValueError("Ungültige Baureihe.")
    if not frist:
        raise ValueError("Friststufe nicht gefunden.")
    row = db_exec(
        """
        SELECT COUNT(*) AS package_count
        FROM work_packages
        WHERE baureihe=? AND friststufe=?;
        """,
        (series, frist),
        fetchone=True,
    )
    try:
        package_count = int(row["package_count"] or 0) if row else 0
    except Exception:
        package_count = 0
    if package_count > 0:
        raise ValueError("Friststufe kann erst gelöscht werden, wenn keine Arbeitspakete mehr zugeordnet sind.")
    db_exec(
        """
        DELETE FROM work_package_frist_levels
        WHERE baureihe=? AND friststufe=?;
        """,
        (series, frist),
        commit=True,
    )
    return True


def move_frist_level(baureihe: str, friststufe: str, direction: int) -> bool:
    _ensure_default_configuration()
    series = _resolve_series_name(baureihe)
    frist = _resolve_frist_level(series, friststufe)
    if not series:
        raise ValueError("Ungültige Baureihe.")
    if not frist:
        raise ValueError("Friststufe nicht gefunden.")
    step = -1 if int(direction or 0) < 0 else 1
    rows = db_exec(
        """
        SELECT friststufe
        FROM work_package_frist_levels
        WHERE baureihe=?
        ORDER BY sort_order ASC, friststufe ASC;
        """,
        (series,),
        fetch=True,
    ) or []
    levels = [_clean_text(row["friststufe"]) for row in rows if _clean_text(row["friststufe"])]
    try:
        current_index = levels.index(frist)
    except ValueError:
        return False
    new_index = current_index + step
    if new_index < 0 or new_index >= len(levels):
        return False
    levels[current_index], levels[new_index] = levels[new_index], levels[current_index]

    conn = get_conn()
    with _DB_WRITE_LOCK:
        cur = conn.cursor()
        try:
            now = _now_iso()
            for index, level in enumerate(levels, start=1):
                cur.execute(
                    """
                    UPDATE work_package_frist_levels
                    SET sort_order=?, updated_at=?
                    WHERE baureihe=? AND friststufe=?;
                    """,
                    (index * 10, now, series, level),
                )
            conn.commit()
        finally:
            cur.close()
    bump_data_version()
    return True


def get_supported_series_frist_levels() -> dict[str, list[str]]:
    return {series: list_frist_levels(series) for series in list_series()}


def list_work_packages(baureihe: str | None = None, friststufe: str | None = None) -> list[dict[str, Any]]:
    _ensure_default_configuration()
    params: list[Any] = []
    where_parts: list[str] = []
    series = _resolve_series_name(baureihe) if baureihe else ""
    if baureihe and not series:
        return []
    if series:
        where_parts.append("baureihe=?")
        params.append(series)
        frist = _resolve_frist_level(series, friststufe) if friststufe else ""
        if friststufe and not frist:
            return []
        if frist:
            where_parts.append("friststufe=?")
            params.append(frist)

    where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    rows = db_exec(
        f"""
        SELECT id, baureihe, friststufe, title, employee_count, duration_minutes, sort_order, updated_at
        FROM work_packages
        {where}
        ORDER BY baureihe ASC, friststufe ASC, sort_order ASC, id ASC;
        """,
        tuple(params),
        fetch=True,
    ) or []
    return [dict(row) for row in rows]


def _next_work_package_sort_order(baureihe: str, friststufe: str) -> int:
    row = db_exec(
        """
        SELECT COALESCE(MAX(sort_order), 0) AS max_sort
        FROM work_packages
        WHERE baureihe=? AND friststufe=?;
        """,
        (baureihe, friststufe),
        fetchone=True,
    )
    try:
        return int(row["max_sort"] or 0) + 10 if row else 10
    except Exception:
        return 10


def save_work_package(
    *,
    package_id: int | None = None,
    baureihe: str,
    friststufe: str,
    title: str,
    employee_count: int,
    duration_minutes: float,
) -> int:
    _ensure_default_configuration()
    series = _resolve_series_name(baureihe)
    is_general = _is_general_series_name(series)
    frist = _resolve_frist_level(series, GENERAL_FRIST_LEVEL if is_general else friststufe)
    clean_title = _clean_text(title)
    if not series:
        raise ValueError("Ungültige Baureihe.")
    if not frist:
        raise ValueError("Ungültige Friststufe.")
    if not clean_title:
        raise ValueError("Bitte einen Titel eintragen.")
    try:
        employees = int(employee_count)
    except Exception as exc:
        raise ValueError("Mitarbeiteranzahl muss eine Zahl sein.") from exc
    if is_general:
        employees = max(0, employees)
    elif employees < 1:
        raise ValueError("Mitarbeiteranzahl muss mindestens 1 sein.")
    try:
        duration = float(duration_minutes)
    except Exception as exc:
        raise ValueError("Dauer muss eine Zahl sein.") from exc
    if is_general:
        duration = max(0.0, duration)
    elif duration < 30:
        raise ValueError("Dauer muss mindestens 0,5 Stunden betragen.")
    if duration > 0 and not _duration_is_half_hour_step(duration):
        raise ValueError("Dauer darf nur in 0,5-Stunden-Schritten gespeichert werden.")

    duplicate = db_exec(
        """
        SELECT id
        FROM work_packages
        WHERE baureihe=? AND friststufe=? AND lower(trim(title))=lower(trim(?))
          AND (? IS NULL OR id<>?)
        LIMIT 1;
        """,
        (series, frist, clean_title, int(package_id) if package_id else None, int(package_id) if package_id else None),
        fetchone=True,
    )
    if duplicate:
        raise ValueError("Dieses Arbeitspaket ist für die Friststufe bereits vorhanden.")

    updated_at = _now_iso()
    if package_id:
        db_exec(
            """
            UPDATE work_packages
            SET baureihe=?, friststufe=?, title=?, employee_count=?, duration_minutes=?, updated_at=?
            WHERE id=?;
            """,
            (series, frist, clean_title, employees, duration, updated_at, int(package_id)),
            commit=True,
        )
        return int(package_id)

    sort_order = _next_work_package_sort_order(series, frist)
    conn = get_conn()
    with _DB_WRITE_LOCK:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO work_packages(
                    baureihe, friststufe, title, employee_count, duration_minutes, sort_order, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (series, frist, clean_title, employees, duration, sort_order, updated_at),
            )
            new_id = int(cur.lastrowid or 0)
            conn.commit()
        finally:
            cur.close()
    bump_data_version()
    return new_id


def delete_work_package(package_id: int) -> bool:
    row = db_exec("SELECT id FROM work_packages WHERE id=?;", (int(package_id),), fetchone=True)
    if not row:
        return False
    db_exec("DELETE FROM work_packages WHERE id=?;", (int(package_id),), commit=True)
    return True


def copy_series_configuration(source_series: str, target_series: str) -> bool:
    _ensure_configuration_schema()
    source = _clean_text(source_series)
    target = _clean_text(target_series)
    if not source or not target or _case_key(source) == _case_key(target):
        return False
    source_row = db_exec(
        """
        SELECT name
        FROM work_package_series
        WHERE lower(trim(name))=lower(trim(?))
        LIMIT 1;
        """,
        (source,),
        fetchone=True,
    )
    if not source_row:
        return False
    source = _clean_text(source_row["name"])
    target_row = db_exec(
        """
        SELECT name
        FROM work_package_series
        WHERE lower(trim(name))=lower(trim(?))
        LIMIT 1;
        """,
        (target,),
        fetchone=True,
    )
    changed = False
    now = _now_iso()
    if target_row:
        target = _clean_text(target_row["name"])
    else:
        sort_row = db_exec("SELECT COALESCE(MAX(sort_order), 0) AS max_sort FROM work_package_series;", fetchone=True)
        try:
            sort_order = int(sort_row["max_sort"] or 0) + 10 if sort_row else 10
        except Exception:
            sort_order = 10
        db_exec(
            """
            INSERT INTO work_package_series(name, sort_order, updated_at)
            VALUES (?, ?, ?);
            """,
            (target, sort_order, now),
            commit=True,
        )
        changed = True

    source_levels = db_exec(
        """
                SELECT friststufe, trigger_type, active, sort_order
                FROM work_package_frist_levels
        WHERE baureihe=?
        ORDER BY sort_order ASC, friststufe ASC;
        """,
        (source,),
        fetch=True,
    ) or []
    for level in source_levels:
        frist = _clean_text(level["friststufe"])
        if not frist:
            continue
        existing_level = db_exec(
            """
            SELECT friststufe
            FROM work_package_frist_levels
            WHERE baureihe=? AND lower(trim(friststufe))=lower(trim(?))
            LIMIT 1;
            """,
            (target, frist),
            fetchone=True,
        )
        if not existing_level:
            db_exec(
                """
                INSERT INTO work_package_frist_levels(baureihe, friststufe, trigger_type, active, sort_order, updated_at)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    target,
                    frist,
                    _clean_trigger_type(level["trigger_type"]),
                    1 if bool(level["active"]) else 0,
                    int(level["sort_order"] or 0),
                    now,
                ),
                commit=True,
            )
            changed = True

    source_packages = db_exec(
        """
        SELECT friststufe, title, employee_count, duration_minutes, sort_order
        FROM work_packages
        WHERE baureihe=?
        ORDER BY friststufe ASC, sort_order ASC, id ASC;
        """,
        (source,),
        fetch=True,
    ) or []
    for package in source_packages:
        frist = _clean_text(package["friststufe"])
        title = _clean_text(package["title"])
        if not frist or not title:
            continue
        target_frist_row = db_exec(
            """
            SELECT friststufe
            FROM work_package_frist_levels
            WHERE baureihe=? AND lower(trim(friststufe))=lower(trim(?))
            LIMIT 1;
            """,
            (target, frist),
            fetchone=True,
        )
        if not target_frist_row:
            continue
        target_frist = _clean_text(target_frist_row["friststufe"])
        existing_package = db_exec(
            """
            SELECT id
            FROM work_packages
            WHERE baureihe=? AND friststufe=? AND lower(trim(title))=lower(trim(?))
            LIMIT 1;
            """,
            (target, target_frist, title),
            fetchone=True,
        )
        if existing_package:
            continue
        db_exec(
            """
            INSERT INTO work_packages(
                baureihe, friststufe, title, employee_count, duration_minutes, sort_order, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                target,
                target_frist,
                title,
                int(package["employee_count"] or 1),
                float(package["duration_minutes"] or 0),
                int(package["sort_order"] or 0),
                now,
            ),
            commit=True,
        )
        changed = True

    if changed:
        bump_data_version()
    return changed


def move_work_package(baureihe: str, friststufe: str, package_id: int, direction: int) -> bool:
    _ensure_default_configuration()
    series = _resolve_series_name(baureihe)
    frist = _resolve_frist_level(series, friststufe)
    if not series:
        raise ValueError("Ungültige Baureihe.")
    if not frist:
        raise ValueError("Ungültige Friststufe.")
    step = -1 if int(direction or 0) < 0 else 1
    rows = db_exec(
        """
        SELECT id
        FROM work_packages
        WHERE baureihe=? AND friststufe=?
        ORDER BY sort_order ASC, id ASC;
        """,
        (series, frist),
        fetch=True,
    ) or []
    package_ids = [int(row["id"]) for row in rows]
    try:
        current_index = package_ids.index(int(package_id))
    except ValueError:
        return False
    new_index = current_index + step
    if new_index < 0 or new_index >= len(package_ids):
        return False
    package_ids[current_index], package_ids[new_index] = package_ids[new_index], package_ids[current_index]

    conn = get_conn()
    with _DB_WRITE_LOCK:
        cur = conn.cursor()
        try:
            now = _now_iso()
            for index, current_id in enumerate(package_ids, start=1):
                cur.execute(
                    """
                    UPDATE work_packages
                    SET sort_order=?, updated_at=?
                    WHERE id=? AND baureihe=? AND friststufe=?;
                    """,
                    (index * 10, now, int(current_id), series, frist),
                )
            conn.commit()
        finally:
            cur.close()
    bump_data_version()
    return True


def list_vehicle_series_mappings(baureihe: str | None = None) -> list[dict[str, Any]]:
    _ensure_default_configuration()
    series = _resolve_series_name(baureihe) if baureihe else ""
    if baureihe and not series:
        return []
    where = "WHERE baureihe=?" if series else ""
    params = (series,) if series else ()
    rows = db_exec(
        f"""
        SELECT vehicle_number, vehicle_key, baureihe, updated_at
        FROM vehicle_series_map
        {where}
        ORDER BY vehicle_number ASC;
        """,
        params,
        fetch=True,
    ) or []
    return sorted((dict(row) for row in rows), key=_vehicle_number_sort_key)


def save_vehicle_series_mapping(vehicle_number: str, baureihe: str) -> None:
    _ensure_default_configuration()
    vehicle = _clean_text(vehicle_number)
    series = _resolve_series_name(baureihe)
    vehicle_key = _normalize_vehicle_key(vehicle)
    if not vehicle:
        raise ValueError("Bitte eine Fahrzeugnummer eintragen.")
    if not series:
        raise ValueError("Ungültige Baureihe.")
    if _is_general_series_name(series):
        raise ValueError("In Allgemein koennen keine Fahrzeugnummern erstellt werden.")
    if not vehicle_key:
        raise ValueError("Fahrzeugnummer konnte nicht verarbeitet werden.")
    db_exec(
        """
        INSERT INTO vehicle_series_map(vehicle_number, vehicle_key, baureihe, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(vehicle_number) DO UPDATE SET
            vehicle_key=excluded.vehicle_key,
            baureihe=excluded.baureihe,
            updated_at=excluded.updated_at;
        """,
        (vehicle, vehicle_key, series, _now_iso()),
        commit=True,
    )


def delete_vehicle_series_mapping(vehicle_number: str) -> bool:
    vehicle = _clean_text(vehicle_number)
    if not vehicle:
        return False
    row = db_exec(
        "SELECT vehicle_number FROM vehicle_series_map WHERE vehicle_number=?;",
        (vehicle,),
        fetchone=True,
    )
    if not row:
        return False
    db_exec("DELETE FROM vehicle_series_map WHERE vehicle_number=?;", (vehicle,), commit=True)
    return True


def get_vehicle_series_for_vehicle(vehicle_number: Any) -> str:
    _ensure_default_configuration()
    vehicle = _clean_text(vehicle_number)
    if not vehicle:
        return ""
    version = _lookup_cache_version()
    cache_key = (version, vehicle)
    with _LOOKUP_CACHE_LOCK:
        cached = _VEHICLE_SERIES_CACHE.get(cache_key)
    if cached is not None:
        return cached

    vehicle_key = _normalize_vehicle_key(vehicle)
    row = db_exec(
        """
        SELECT baureihe
        FROM vehicle_series_map
        WHERE lower(trim(vehicle_number))=lower(trim(?))
           OR vehicle_key=?
        ORDER BY CASE WHEN lower(trim(vehicle_number))=lower(trim(?)) THEN 0 ELSE 1 END
        LIMIT 1;
        """,
        (vehicle, vehicle_key, vehicle),
        fetchone=True,
    )
    result = _resolve_series_name(row["baureihe"]) if row else ""
    with _LOOKUP_CACHE_LOCK:
        if _LOOKUP_CACHE_VERSION == version:
            _VEHICLE_SERIES_CACHE[cache_key] = result
    return result


def _frist_value_matches_level(frist_value: Any, configured_level: str) -> bool:
    raw = _clean_text(frist_value)
    level = _clean_text(configured_level)
    if not raw or not level:
        return False
    if _case_key(raw) == _case_key(level):
        return True
    pattern = rf"(?<![A-Z0-9]){re.escape(level)}(?![A-Z0-9])"
    return bool(re.search(pattern, raw, flags=re.I))


def _frist_level_match_position(frist_value: Any, configured_level: str) -> int:
    raw = _clean_text(frist_value)
    level = _clean_text(configured_level)
    if not raw or not level:
        return 1_000_000
    if _case_key(raw) == _case_key(level):
        return 0
    pattern = rf"(?<![A-Z0-9]){re.escape(level)}(?![A-Z0-9])"
    match = re.search(pattern, raw, flags=re.I)
    return int(match.start()) if match else 1_000_000


def _configured_frist_level_rows(baureihe: str, *, active_only: bool = False) -> list[dict[str, Any]]:
    series = _resolve_series_name(baureihe)
    if not series:
        return []
    rows = list_frist_level_configs(series)
    if active_only:
        rows = [row for row in rows if bool(row.get("active", True))]
    return rows


def _matching_configured_friststufen(baureihe: str, frist_value: Any, *, active_only: bool = False) -> list[str]:
    rows = _configured_frist_level_rows(baureihe, active_only=active_only)
    if not rows:
        return []
    levels = [_clean_text(row.get("friststufe")) for row in rows if _clean_text(row.get("friststufe"))]
    matched = [level for level in levels if _frist_value_matches_level(frist_value, level)]
    return sorted(
        matched,
        key=lambda level: (_frist_level_match_position(frist_value, level), levels.index(level)),
    )


def _matching_configured_friststufe(baureihe: str, frist_value: Any) -> str:
    series = _resolve_series_name(baureihe)
    if not series:
        return ""
    matches = _matching_configured_friststufen(series, frist_value)
    return matches[0] if matches else ""


def _fallback_general_frist_levels() -> list[str]:
    rows = _configured_frist_level_rows(GENERAL_SERIES_NAME, active_only=True)
    levels = [_clean_text(row.get("friststufe")) for row in rows if _clean_text(row.get("friststufe"))]
    if levels:
        return levels
    return [GENERAL_FRIST_LEVEL] if _resolve_frist_level(GENERAL_SERIES_NAME, GENERAL_FRIST_LEVEL) else []


def _combined_work_package_labels(baureihe: str, frist_levels: list[str]) -> tuple[str, ...]:
    combined: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    show_frist_suffix = len(frist_levels) > 1
    for frist in frist_levels:
        for row in list_work_packages(baureihe, frist):
            title = _clean_text(row.get("title"))
            if not title:
                continue
            key = _case_key(title)
            if key not in combined:
                combined[key] = {
                    "title": title,
                    "frist_levels": [],
                    "employee_count": 0,
                    "duration_minutes": 0.0,
                }
                order.append(key)
            item = combined[key]
            if frist not in item["frist_levels"]:
                item["frist_levels"].append(frist)
            try:
                item["employee_count"] = max(int(item["employee_count"] or 0), int(row.get("employee_count") or 0))
            except Exception:
                pass
            try:
                item["duration_minutes"] = float(item["duration_minutes"] or 0.0) + float(row.get("duration_minutes") or 0.0)
            except Exception:
                pass

    labels: list[str] = []
    for key in order:
        item = combined[key]
        labels.append(
            _work_package_check_label(
                {
                    "title": item["title"],
                    "display_friststufe": "+".join(item["frist_levels"]),
                    "show_frist_suffix": show_frist_suffix,
                    "employee_count": item["employee_count"],
                    "duration_minutes": item["duration_minutes"],
                }
            )
        )
    return tuple(label for label in labels if label)


def get_configured_work_package_titles_for_vehicle_and_frist(vehicle_number: Any, frist_value: Any) -> list[str]:
    _ensure_default_configuration()
    version = _lookup_cache_version()
    vehicle = _clean_text(vehicle_number)
    frist_raw = _clean_text(frist_value)
    cache_key = (version, vehicle, frist_raw)
    with _LOOKUP_CACHE_LOCK:
        cached = _WORK_PACKAGE_TITLES_CACHE.get(cache_key)
    if cached is not None:
        return list(cached)

    series = get_vehicle_series_for_vehicle(vehicle_number)
    frist_levels = _matching_configured_friststufen(series, frist_value, active_only=True) if series else []
    if not frist_levels:
        series = _resolve_series_name(GENERAL_SERIES_NAME)
        frist_levels = _fallback_general_frist_levels()
    result = _combined_work_package_labels(series, frist_levels) if series and frist_levels else ()
    with _LOOKUP_CACHE_LOCK:
        if _LOOKUP_CACHE_VERSION == version:
            _WORK_PACKAGE_TITLES_CACHE[cache_key] = result
    return list(result)
