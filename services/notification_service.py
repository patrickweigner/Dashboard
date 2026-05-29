
from __future__ import annotations

from datetime import date, datetime, timedelta
import hashlib
import logging
import re
import threading
from typing import Any

import pandas as pd
import requests
from nicegui import ui


logger = logging.getLogger(__name__)
_LWU_WORKER_LOCK = threading.Lock()
_LWU_WORKER_STARTED = False


def configure(**deps) -> None:
    globals().update(deps)


def notify_delay(payload: dict[str, Any]) -> tuple[bool, str]:
    url = _notify_flow_url()
    if not url:
        return False, "NOTIFY_FLOW_URL fehlt in .streamlit/secrets.toml"
    try:
        # TODO: Queue HTTP notifications off the UI path if webhook latency becomes visible.
        r = requests.post(url, json=payload, timeout=10)
        ok = 200 <= int(r.status_code) < 300
        if ok:
            return True, f"POST ok ({int(r.status_code)})"
        return False, f"POST {int(r.status_code)}: {str(r.text or '')[:300]}"
    except Exception as ex:
        logger.exception("notify_delay fehlgeschlagen")
        return False, f"POST Exception: {ex}"


def notify_archive(payload: dict[str, Any]) -> tuple[bool, str]:
    url = _notify_flow_url()
    if not url:
        return False, "NOTIFY_FLOW_URL fehlt in .streamlit/secrets.toml"
    try:
        # TODO: Queue HTTP notifications off the UI path if webhook latency becomes visible.
        r = requests.post(url, json=payload, timeout=10)
        ok = 200 <= int(r.status_code) < 300
        if ok:
            return True, f"POST ok ({int(r.status_code)})"
        return False, f"POST {int(r.status_code)}: {str(r.text or '')[:300]}"
    except Exception as ex:
        logger.exception("notify_archive fehlgeschlagen")
        return False, f"POST Exception: {ex}"


def _lwu_log_id(fahrzeug: str, area: str, planned_at_iso: str) -> str:
    base = f"{str(fahrzeug or '').strip()}|{str(area or '').strip()}|{planned_at_iso}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def _lwu_already_sent(log_id: str) -> bool:
    row = db_exec("SELECT 1 FROM lwu_reminder_log WHERE id=?;", (str(log_id),), fetchone=True)
    return bool(row)


def _mark_lwu_sent(log_id: str, fahrzeug: str, area: str, planned_at_iso: str) -> None:
    now = now_berlin().isoformat()
    db_exec(
        """
        INSERT OR IGNORE INTO lwu_reminder_log (id, fahrzeug, area, planned_at, sent_at)
        VALUES (?, ?, ?, ?, ?);
        """,
        (
            log_id,
            str(fahrzeug or "").strip(),
            str(area or "").strip(),
            str(planned_at_iso or "").strip(),
            now,
        ),
        commit=True,
    )


def _build_lwu_payload(*, fahrzeug: str, area: str, planned_at: datetime, note: str) -> dict[str, Any]:
    now = now_berlin()
    return {
        "event": "lwu_reminder",
        "source": "ecm4_plan",
        "fahrzeug": str(fahrzeug or "").strip(),
        "area": str(area or "").strip(),
        "planned_at": as_berlin(planned_at).isoformat(),
        "note": str(note or "").strip(),
        "reported_at": now.isoformat(),
        "page": "background",
    }


def _collect_lwu_candidates_from_ecm4(df_plan: pd.DataFrame) -> list[dict[str, Any]]:
    """
    Baut robuste LWU-Kandidaten aus dem ECM4-Plan.
    Wichtig: Fahrzeugnummer kommt bevorzugt aus Hinweis (Spalte C),
    weil die Bereichsspalten oft ein anderes Fahrzeug enthalten.
    """
    if df_plan is None or df_plan.empty:
        return []

    tmp = df_plan.copy()
    tmp["hinweis"] = tmp["hinweis"].fillna("").astype(str)
    tmp["fahrzeug"] = tmp["fahrzeug"].fillna("").astype(str)
    tmp = tmp[tmp["hinweis"].str.contains(r"\bLWU\b", case=False, regex=True, na=False)].copy()
    if tmp.empty:
        return []

    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for _, rr in tmp.iterrows():
        st_dt = as_berlin(rr.get("slot_start"))
        if st_dt is None:
            continue
        note = str(rr.get("hinweis") or "").strip()
        area = str(rr.get("area") or "").strip()
        area_vehicle_raw = str(rr.get("fahrzeug") or "").strip()
        note_vehicle = _norm_vehicle(note)
        area_vehicle = _norm_vehicle(area_vehicle_raw) or area_vehicle_raw
        fahrzeug = (note_vehicle or area_vehicle).strip()
        if not fahrzeug:
            continue

        if note_vehicle:
            area_for_payload = area if (area_vehicle and note_vehicle.casefold() == area_vehicle.casefold()) else ""
        else:
            area_for_payload = area if area_vehicle else ""

        key = (st_dt.isoformat(), fahrzeug.casefold(), note.casefold())
        cur = by_key.get(key)
        if cur is None:
            by_key[key] = {
                "planned_at": st_dt,
                "fahrzeug": fahrzeug,
                "area": area_for_payload,
                "note": note,
            }
        elif (not cur.get("area")) and area_for_payload:
            cur["area"] = area_for_payload

    return sorted(by_key.values(), key=lambda x: x["planned_at"])


def _collect_lwu_candidates_from_gewerke(df_open: pd.DataFrame) -> list[dict[str, Any]]:
    if df_open is None or df_open.empty:
        return []

    by_row_id: dict[int, pd.Series] = {}
    for _, rr in df_open.iterrows():
        row_id = int(rr.get("id") or 0) if str(rr.get("id") or "").strip() else 0
        if row_id > 0:
            by_row_id[row_id] = rr

    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for event in _collect_gewerke_slot_events(df_open):
        if not bool(event.get("has_time", True)):
            continue
        note = str(event.get("overview") or "").strip()
        if not re.search(r"\bLWU\b", note, flags=re.I):
            continue
        planned_at = as_berlin(event.get("display_start")) or as_berlin(event.get("start"))
        if planned_at is None:
            continue
        fahrzeug = str(event.get("fahrzeug") or "").strip()
        if not fahrzeug:
            continue

        area = ""
        for src in list(event.get("source_rows") or []):
            row_id = int(src.get("id") or 0)
            rr = by_row_id.get(row_id)
            if rr is None:
                continue
            area = _clean_ap(rr.get("Arbeitsplatz") or rr.get("ap_pdf") or "")
            if area:
                break

        key = (planned_at.isoformat(), fahrzeug.casefold(), note.casefold())
        if key not in by_key:
            by_key[key] = {
                "planned_at": planned_at,
                "fahrzeug": fahrzeug,
                "area": area,
                "note": note,
            }
        elif (not by_key[key].get("area")) and area:
            by_key[key]["area"] = area

    return sorted(by_key.values(), key=lambda x: x["planned_at"])


def _collect_lwu_candidates() -> list[dict[str, Any]]:
    df_open = get_open_tasks_df()
    candidates = _collect_lwu_candidates_from_gewerke(df_open)
    if candidates:
        return candidates
    try:
        df_plan = load_ecm4_plan_df(ref_dt=now_berlin() + timedelta(hours=24))
    except Exception:
        return []
    return _collect_lwu_candidates_from_ecm4(df_plan)


def check_and_send_lwu_reminders(*, window_minutes: int = 360) -> int:
    """
    Sucht ECM4-Plan-Zeilen, deren 'hinweis' (Spalte C) 'LWU' enthält
    und sendet 24h vorher 1x eine Benachrichtigung.

    window_minutes=360 bedeutet: wenn Server mal 1-2h hängt, wird's trotzdem noch gesendet
    (bis max. 6h nach dem 24h-Punkt).
    """
    now = now_berlin()
    candidates = _collect_lwu_candidates()
    if not candidates:
        return 0

    sent = 0
    for cand in candidates:
        st_dt = cand["planned_at"]
        remind_at = st_dt - timedelta(hours=24)
        if now < remind_at:
            continue
        if now > (remind_at + timedelta(minutes=int(window_minutes))):
            continue

        fahrzeug = str(cand.get("fahrzeug") or "").strip()
        area = str(cand.get("area") or "").strip()
        note = str(cand.get("note") or "").strip()
        planned_iso = st_dt.isoformat()
        log_id = _lwu_log_id(fahrzeug, area, planned_iso)
        if _lwu_already_sent(log_id):
            continue

        payload = _build_lwu_payload(fahrzeug=fahrzeug, area=area, planned_at=st_dt, note=note)
        ok, info = notify_delay(payload)
        if ok:
            _mark_lwu_sent(log_id, fahrzeug, area, planned_iso)
            sent += 1
        else:
            logger.warning("LWU Reminder konnte nicht gesendet werden: %s", info)

    return sent


def trigger_lwu_test_next_24h(*, hours_ahead: int = 24) -> tuple[int, int]:
    """
    Manueller Test-Trigger aus der Priorisierung:
    sendet LWU-Events für alle Einträge in den nächsten `hours_ahead` Stunden.
    Der Reminder-Log wird bewusst ignoriert, damit die URL testbar bleibt.
    """
    now = now_berlin()
    horizon = now + timedelta(hours=int(hours_ahead))
    candidates = _collect_lwu_candidates()
    if not candidates:
        return 0, 0

    matched = 0
    sent = 0
    for cand in candidates:
        st_dt = cand["planned_at"]
        if st_dt < now or st_dt > horizon:
            continue
        matched += 1
        payload = _build_lwu_payload(
            fahrzeug=str(cand.get("fahrzeug") or "").strip(),
            area=str(cand.get("area") or "").strip(),
            planned_at=st_dt,
            note=str(cand.get("note") or "").strip(),
        )
        payload["source"] = "ecm4_plan_test_button"
        payload["page"] = "priorisierung_test"
        ok, info = notify_delay(payload)
        if ok:
            sent += 1
        else:
            logger.warning("LWU Test-Trigger konnte nicht gesendet werden: %s", info)

    return sent, matched


def _lwu_worker_loop() -> None:
    while True:
        try:
            auto_clear_shopfloorboard_5s_if_due()
            check_and_send_lwu_reminders(window_minutes=360)
        except Exception:
            logger.exception("LWU worker error")
        threading.Event().wait(60)


def start_lwu_reminder_worker() -> None:
    global _LWU_WORKER_STARTED
    with _LWU_WORKER_LOCK:
        if _LWU_WORKER_STARTED:
            return
        _LWU_WORKER_STARTED = True
        t = threading.Thread(target=_lwu_worker_loop, name="lwu_reminder_worker", daemon=True)
        t.start()


def _ui_page_hint() -> str:
    try:
        client = ui.context.client  # type: ignore[attr-defined]
        page = getattr(client, "page", None)
        if page is not None:
            return str(getattr(page, "path", "") or "").strip()
    except Exception:
        pass
    return ""


def _build_delay_payload(
    open_id: int,
    reason: str,
    *,
    options: list[str] | None = None,
    free_text: str | None = None,
    source: str = "verzoegerung_dialog",
) -> dict[str, Any]:
    row = db_exec(
        "SELECT fahrzeug, friststufe, arbeitsplatz, fertig, initial_fertig FROM open_tasks WHERE id=?;",
        (int(open_id),),
        fetchone=True,
    )
    fahrzeug = row["fahrzeug"] if row else None
    friststufe = row["friststufe"] if row else None
    arbeitsplatz = row["arbeitsplatz"] if row else None
    fertig = row["fertig"] if row else None
    initial_fertig = row["initial_fertig"] if row else None
    selected = [str(x).strip() for x in (options or []) if str(x).strip()]
    return {
        "event": "delay_reported",
        "source": source,
        "open_id": int(open_id),
        "fahrzeug": fahrzeug,
        "friststufe": friststufe,
        "arbeitsplatz": arbeitsplatz,
        "fertig": fertig,
        "initial_fertig": initial_fertig,
        "reason": str(reason or "").strip(),
        "options": ", ".join(selected),
        "options_count": len(selected),
        "free_text": str(free_text or "").strip(),
        "reported_at": now_berlin().isoformat(timespec="seconds"),
        "page": _ui_page_hint(),
    }


def _build_ausseneinsatz_payload(
    *,
    plan_day: date,
    selection_key: str,
    source: str = "ausseneinsatz_dialog",
) -> dict[str, Any]:
    selection_key_txt = str(selection_key or "").strip()
    selection_label = str(AUSSENEINSATZ_OPTIONS.get(selection_key_txt, "") or "")
    return {
        "event": "ausseneinsatz_reported",
        "source": source,
        "page": _ui_page_hint(),
        "reported_at": now_berlin().isoformat(timespec="seconds"),
        "fahrzeug": None,
        "friststufe": None,
        "arbeitsplatz": None,
        "open_id": None,
        "fertig": None,
        "initial_fertig": None,
        "reason": "Außeneinsatz",
        "options": selection_label,
        "options_count": 1 if selection_label else 0,
        "free_text": "",
        "area": None,
        "planned_at": plan_day.isoformat(),
        "note": selection_key_txt,
        "archived_at": None,
        "message": f"Außeneinsatz für {plan_day:%d.%m.%Y}: {selection_label or '-'}",
    }
