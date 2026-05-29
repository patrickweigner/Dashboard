from __future__ import annotations

import asyncio
import gc
import logging
import os
from pathlib import Path
import sqlite3
import threading
from typing import Any

from nicegui import app as nicegui_app


logger = logging.getLogger(__name__)

try:
    import psutil
except Exception:
    psutil = None


_STARTED = False
_TASK: asyncio.Task[None] | None = None


def _cache_len(value: Any) -> int | None:
    try:
        return len(value)
    except Exception:
        return None


def _file_size_mb(path: Path) -> float | None:
    try:
        if not path.exists():
            return None
        return round(path.stat().st_size / 1024 / 1024, 3)
    except Exception:
        return None


def _sqlite_count(db_path: Path, table_name: str) -> int | None:
    if not db_path.exists():
        return None
    conn: sqlite3.Connection | None = None
    try:
        uri_path = str(db_path).replace("\\", "/")
        conn = sqlite3.connect(f"file:{uri_path}?mode=ro", uri=True, timeout=5)
        row = conn.execute(f"SELECT COUNT(*) FROM {table_name};").fetchone()
        return int(row[0]) if row else None
    except Exception:
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _nicegui_runtime_counts() -> dict[str, int | None]:
    try:
        from nicegui.client import Client
        from nicegui.elements.timer import Timer

        clients = list(Client.instances.values())
        timers = 0
        for client in clients:
            for element in list(getattr(client, "elements", {}).values()):
                if isinstance(element, Timer) and not getattr(element, "is_deleted", False):
                    timers += 1
        return {"nicegui_clients": len(clients), "nicegui_timers": timers}
    except Exception:
        return {"nicegui_clients": None, "nicegui_timers": None}


def _project_runtime_counts() -> dict[str, int | None]:
    counts: dict[str, int | None] = {}
    try:
        from core import ui_runtime

        counts["open_dialog_ids"] = _cache_len(getattr(ui_runtime, "_OPEN_DIALOG_IDS", None))
    except Exception:
        counts["open_dialog_ids"] = None

    try:
        from services import configuration_service

        counts["vehicle_series_cache"] = _cache_len(getattr(configuration_service, "_VEHICLE_SERIES_CACHE", None))
        counts["work_package_titles_cache"] = _cache_len(
            getattr(configuration_service, "_WORK_PACKAGE_TITLES_CACHE", None)
        )
    except Exception:
        counts["vehicle_series_cache"] = None
        counts["work_package_titles_cache"] = None

    try:
        from services import ecm4_service

        counts["ecm4_result_cache"] = _cache_len(getattr(ecm4_service, "_ECM4_RESULT_CACHE", None))
        source_cache = getattr(ecm4_service, "_ECM4_SOURCE_CACHE", None)
        counts["ecm4_source_cache"] = 1 if source_cache is not None else 0
        counts["ecm4_source_rows"] = _cache_len(source_cache[1]) if source_cache is not None else 0
        counts["ecm4_source_span_rows"] = _cache_len(source_cache[2]) if source_cache is not None else 0
    except Exception:
        counts["ecm4_result_cache"] = None
        counts["ecm4_source_cache"] = None
        counts["ecm4_source_rows"] = None
        counts["ecm4_source_span_rows"] = None

    try:
        from services import planning_service

        counts["weekly_main_cache"] = _cache_len(getattr(planning_service, "_WEEKLY_MAIN_CACHE", None))
        counts["weekly_side_cache"] = _cache_len(getattr(planning_service, "_WEEKLY_SIDE_CACHE", None))
        slot_cache = getattr(planning_service, "_CURRENT_SLOT_KEYS_CACHE", None)
        counts["current_slot_keys_cache"] = _cache_len(slot_cache[3]) if slot_cache is not None else 0
    except Exception:
        counts["weekly_main_cache"] = None
        counts["weekly_side_cache"] = None
        counts["current_slot_keys_cache"] = None

    return counts


def _database_runtime_counts() -> dict[str, float | int | None]:
    try:
        from core import db

        db_path_raw = str(getattr(db, "DB_PATH", "") or "")
        if not db_path_raw:
            from core.config import DB_PATH as config_db_path

            db_path_raw = str(config_db_path)
        db_path = Path(db_path_raw)
    except Exception:
        db_path = Path("fristenplanung.db")

    return {
        "db_mb": _file_size_mb(db_path),
        "db_wal_mb": _file_size_mb(Path(str(db_path) + "-wal")),
        "db_shm_mb": _file_size_mb(Path(str(db_path) + "-shm")),
        "ecm4_plan_hist_rows": _sqlite_count(db_path, "ecm4_plan_hist"),
        "ecm4_plan_rows": _sqlite_count(db_path, "ecm4_plan"),
    }


def log_runtime_diagnostics() -> None:
    """Log technical runtime counters only; no secrets, payloads, or user data."""
    try:
        process = psutil.Process() if psutil is not None else None
        values: dict[str, Any] = {
            "ram_mb": round(process.memory_info().rss / 1024 / 1024, 1) if process is not None else None,
            "cpu_percent": process.cpu_percent(interval=None) if process is not None else None,
            "threads": threading.active_count(),
            "gc_counts": gc.get_count(),
        }
        values.update(_nicegui_runtime_counts())
        values.update(_project_runtime_counts())
        values.update(_database_runtime_counts())

        logger.warning(
            "runtime_diagnostics "
            + " ".join(f"{key}={value!r}" for key, value in sorted(values.items()))
        )
    except Exception as exc:
        logger.warning("runtime_diagnostics_failed: %s", exc)


async def _diagnostics_loop(interval_seconds: float) -> None:
    while True:
        log_runtime_diagnostics()
        await asyncio.sleep(interval_seconds)


def _start_background_task(interval_seconds: float) -> None:
    global _TASK
    if _TASK is not None and not _TASK.done():
        return
    try:
        loop = asyncio.get_running_loop()
        _TASK = loop.create_task(_diagnostics_loop(interval_seconds), name="runtime-diagnostics")
    except Exception as exc:
        logger.warning("runtime_diagnostics_start_failed: %s", exc)


def _stop_background_task() -> None:
    global _TASK
    if _TASK is not None and not _TASK.done():
        _TASK.cancel()
    _TASK = None


def start_diagnostics_if_enabled() -> None:
    """Register one global startup task when APP_DIAGNOSTICS=1 is set."""
    global _STARTED
    if os.getenv("APP_DIAGNOSTICS") != "1":
        return
    if _STARTED:
        return
    _STARTED = True

    try:
        interval_seconds = float(os.getenv("APP_DIAGNOSTICS_INTERVAL_SECONDS", "300"))
    except Exception:
        interval_seconds = 300.0
    if interval_seconds <= 0:
        interval_seconds = 300.0

    # Use NiceGUI's app startup hook and an asyncio task, not ui.timer, so this is
    # registered once for the process and never once per page or browser client.
    try:
        nicegui_app.on_startup(lambda: _start_background_task(interval_seconds))
        nicegui_app.on_shutdown(_stop_background_task)
    except Exception as exc:
        _STARTED = False
        logger.warning("runtime_diagnostics_register_failed: %s", exc)
