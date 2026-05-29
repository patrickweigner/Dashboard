from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any

import pandas as pd


logger = logging.getLogger(__name__)
_CACHE_LOCK = threading.Lock()
_OPEN_TASKS_CACHE: tuple[int, pd.DataFrame] | None = None


def configure(**deps) -> None:
    globals().update(deps)


def _load_open_tasks_df_uncached() -> pd.DataFrame:
    rows = db_exec(
        """
        SELECT id, fahrzeug, friststufe, anfang, fertig, arbeitsplatz, ap_pdf,
               zusatzarbeiten, gewerke, last_problem_note, last_problem_at, initial_fertig, ecm3_fertig,
               zusatz_done, frist_done, frist_in_progress, planning_order_id, source_system
        FROM open_tasks
        ORDER BY
            CASE WHEN fertig IS NULL OR TRIM(fertig)='' THEN 1 ELSE 0 END,
            fertig ASC,
            anfang ASC,
            fahrzeug ASC;
        """,
        fetch=True,
    ) or []
    cols = [
        "id",
        "Fahrzeug",
        "Friststufe",
        "Anfang",
        "Fertig",
        "Arbeitsplatz",
        "ap_pdf",
        "Zusatzarbeiten",
        "Gewerke",
        "last_problem_note",
        "last_problem_at",
        "initial_fertig",
        "ecm3_fertig",
        "zusatz_done",
        "frist_done",
        "frist_in_progress",
        "planning_order_id",
        "source_system",
    ]
    df = pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)
    for col in ("Anfang", "Fertig", "last_problem_at", "initial_fertig", "ecm3_fertig"):
        df[col] = _coerce_berlin_datetime_series(df[col])
    return df


def get_open_tasks_df() -> pd.DataFrame:
    global _OPEN_TASKS_CACHE
    ver = _current_data_version()
    with _CACHE_LOCK:
        cached = _OPEN_TASKS_CACHE
        if cached and cached[0] == ver:
            return cached[1].copy(deep=True)
    fresh = _load_open_tasks_df_uncached()
    with _CACHE_LOCK:
        if _current_data_version() == ver:
            _OPEN_TASKS_CACHE = (ver, fresh.copy(deep=True))
    return fresh


def _build_archive_payload(
    *,
    open_id: int,
    fahrzeug: Any,
    arbeitsplatz: Any,
    friststufe: Any,
    archived_at: datetime,
) -> dict[str, Any]:
    fahrzeug_txt = str(fahrzeug or "").strip()
    arbeitsplatz_txt = _clean_ap(arbeitsplatz)
    frist_txt = str(friststufe or "").strip()
    return {
        "event": "task_archived",
        "source": "archive_task",
        "open_id": int(open_id),
        "fahrzeug": fahrzeug_txt,
        "arbeitsplatz": arbeitsplatz_txt,
        "friststufe": frist_txt,
        "archived_at": archived_at.isoformat(timespec="seconds"),
        "page": _ui_page_hint(),
        "message": f"Fahrzeug {fahrzeug_txt or '-'} wurde am Arbeitsplatz {arbeitsplatz_txt or '-'} archiviert.",
    }


def _completion_status_for_deadline(actual_value: Any, deadline_value: Any) -> str | None:
    actual_dt = as_berlin(actual_value)
    deadline_dt = as_berlin(deadline_value)
    if actual_dt is None or deadline_dt is None:
        return None
    return "verspaetet" if actual_dt > deadline_dt else "puenktlich"


def _archive_notification_needed(fahrzeug: Any) -> bool:
    raw = str(fahrzeug or "").strip()
    if not raw:
        return False
    candidates = [raw, _norm_vehicle(raw)]
    for candidate in candidates:
        txt = str(candidate or "").strip()
        if not txt:
            continue
        if any(token in txt for token in ARCHIVE_NOTIFY_VEHICLE_TOKENS):
            return True
    return False


def _send_archive_notification(
    *,
    open_id: int,
    fahrzeug: Any,
    arbeitsplatz: Any,
    friststufe: Any,
    archived_at: datetime,
) -> tuple[bool, str]:
    if not _archive_notification_needed(fahrzeug):
        return True, "nicht erforderlich"
    notify_payload = _build_archive_payload(
        open_id=int(open_id),
        fahrzeug=fahrzeug,
        arbeitsplatz=arbeitsplatz,
        friststufe=friststufe,
        archived_at=archived_at,
    )
    ok_notify, info_notify = notify_archive(notify_payload)
    if not ok_notify:
        logger.warning("Archiv-Benachrichtigung konnte nicht gesendet werden: %s", info_notify)
    return ok_notify, str(info_notify or "")


def _insert_archive_entry(
    *,
    fahrzeug: Any,
    friststufe: Any,
    anfang: Any,
    fertig: Any,
    last_problem_note: Any,
    completed_at: Any,
    status: Any,
    status_ecm3: Any,
    initial_fertig: Any,
) -> int | None:
    anfang = _clean_nullable_db_text(anfang)
    fertig = _clean_nullable_db_text(fertig)
    completed_at = _clean_nullable_db_text(completed_at)
    initial_fertig = _clean_nullable_db_text(initial_fertig)
    conn = get_conn()
    with _DB_WRITE_LOCK:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO archive(
                    fahrzeug, friststufe, anfang, fertig, last_problem_note, completed_at, status, status_ecm3, initial_fertig
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    fahrzeug,
                    friststufe,
                    anfang,
                    fertig,
                    last_problem_note,
                    completed_at,
                    status,
                    status_ecm3,
                    initial_fertig,
                ),
            )
            archive_id = int(cur.lastrowid or 0) or None
            conn.commit()
        finally:
            cur.close()
    bump_data_version()
    return archive_id


def move_to_archive_and_delete(open_id: int) -> tuple[bool, str]:
    row = db_exec(
        """
        SELECT fahrzeug, friststufe, anfang, fertig,
               arbeitsplatz, ap_pdf, last_problem_note, last_problem_at,
               zusatzarbeiten, gewerke, initial_fertig, ecm3_fertig, zusatz_done, frist_done,
               planning_order_id
        FROM open_tasks
        WHERE id=?;
        """,
        (int(open_id),),
        fetchone=True,
    )
    if not row:
        return False, "Datensatz nicht gefunden."

    (
        fahrzeug,
        frist,
        anfang,
        fertig,
        arb,
        ap_pdf,
        note,
        note_at,
        zus,
        gewerke,
        initial_fertig,
        ecm3_fertig,
        zus_done,
        frist_done,
        planning_order_id,
    ) = row
    now = now_berlin()
    now_iso = now.isoformat()

    basis_dt_berlin = _planned_deadline_dt(initial_fertig, fertig)
    status = _completion_status_for_deadline(now, basis_dt_berlin)
    status_ecm3 = _completion_status_for_deadline(now, ecm3_fertig)

    arch_note = _extract_last_overdue_reason(str(note or "")) if status == "verspaetet" else ""

    archive_id = _insert_archive_entry(
        fahrzeug=fahrzeug,
        friststufe=frist,
        anfang=anfang,
        fertig=(basis_dt_berlin.isoformat() if basis_dt_berlin else _clean_nullable_db_text(fertig)),
        last_problem_note=arch_note,
        completed_at=now_iso,
        status=status,
        status_ecm3=status_ecm3,
        initial_fertig=(basis_dt_berlin.isoformat() if basis_dt_berlin else _clean_nullable_db_text(fertig)),
    )
    _remember_recent_done(
        fahrzeug=fahrzeug,
        friststufe=frist,
        zusatzarbeiten=zus,
        done_at=now,
        archive_id=archive_id,
        snapshot={
            "anfang": anfang,
            "fertig": fertig,
            "arbeitsplatz": arb,
            "ap_pdf": ap_pdf,
            "last_problem_note": note,
            "last_problem_at": note_at,
            "initial_fertig": initial_fertig,
            "ecm3_fertig": ecm3_fertig,
            "gewerke": gewerke,
            "zusatz_done": zus_done,
            "frist_done": frist_done,
            "planning_order_id": planning_order_id,
            "source_system": "planner" if int(planning_order_id or 0) > 0 else "",
            "open_task_id": int(open_id),
        },
    )
    db_exec("DELETE FROM open_tasks WHERE id=?;", (int(open_id),), commit=True)
    if int(planning_order_id or 0) > 0:
        try:
            from app.features.planning.service import set_order_statuses

            set_order_statuses([int(planning_order_id)], status="erledigt")
        except Exception as exc:
            logger.warning("Planner-Auftrag %s konnte beim Archivieren nicht auf erledigt gesetzt werden: %s", planning_order_id, exc)
    ok_notify, info_notify = _send_archive_notification(
        open_id=int(open_id),
        fahrzeug=fahrzeug,
        arbeitsplatz=arb or ap_pdf,
        friststufe=frist,
        archived_at=now,
    )
    if str(info_notify or "").strip().casefold() == "nicht erforderlich":
        return True, "Auftrag archiviert."
    if not ok_notify:
        return True, f"Auftrag archiviert, aber Archiv-Benachrichtigung fehlgeschlagen: {info_notify}"
    return True, f"Auftrag archiviert. Archiv-Benachrichtigung gesendet. ({info_notify})"


def archive_task(open_id: int) -> tuple[bool, str]:
    return move_to_archive_and_delete(int(open_id))


def _archive_notify_type(ok: bool, msg: str) -> str:
    if not ok:
        return "negative"
    if "fehlgeschlagen" in str(msg or "").casefold():
        return "warning"
    return "positive"
