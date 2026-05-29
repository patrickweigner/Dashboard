
from __future__ import annotations

from datetime import date, datetime, time
from typing import Callable

from nicegui import ui


def configure(**deps) -> None:
    globals().update(deps)


def _purge_prio_side_state(now_dt: datetime | None = None) -> None:
    now_loc = as_berlin(now_dt or now_berlin()) or now_berlin()
    rows = db_exec("SELECT area, vehicle_key, row_end, expires_at FROM prio_side_state;", fetch=True) or []
    delete_keys = [
        (
            str(rr["area"] or "").strip().upper(),
            str(rr["vehicle_key"] or "").strip(),
            str(rr["row_end"] or "").strip(),
        )
        for rr in rows
        if as_berlin(rr["expires_at"]) is not None and as_berlin(rr["expires_at"]) <= now_loc
    ]
    if not delete_keys:
        return
    conn = get_conn()
    with _DB_WRITE_LOCK:
        cur = conn.cursor()
        try:
            cur.executemany(
                "DELETE FROM prio_side_state WHERE area=? AND vehicle_key=? AND row_end=?;",
                delete_keys,
            )
            conn.commit()
        finally:
            cur.close()
    bump_data_version()


def _load_prio_side_state_map() -> dict[tuple[str, str, str], bool]:
    rows = db_exec(
        "SELECT area, vehicle_key, row_end, checked FROM prio_side_state;",
        fetch=True,
    ) or []
    out: dict[tuple[str, str, str], bool] = {}
    for rr in rows:
        area = str(rr["area"] or "").strip().upper()
        veh = str(rr["vehicle_key"] or "").strip()
        row_end = str(rr["row_end"] or "").strip()
        if not area or not veh or not row_end:
            continue
        try:
            checked = bool(int(rr["checked"] or 0))
        except Exception:
            checked = False
        out[(area, veh, row_end)] = checked
    return out


def _save_prio_side_state(area: str, vehicle_key: str, row_end_iso: str, checked: bool, expires_at_iso: str) -> None:
    area_norm = str(area or "").strip().upper()
    veh_norm = str(vehicle_key or "").strip()
    row_end_norm = str(row_end_iso or "").strip()
    exp_norm = str(expires_at_iso or "").strip()
    if not area_norm or not veh_norm or not row_end_norm or not exp_norm:
        return
    db_exec(
        """
        INSERT INTO prio_side_state(area, vehicle_key, row_end, checked, updated_at, expires_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(area, vehicle_key, row_end) DO UPDATE SET
            checked=excluded.checked,
            updated_at=excluded.updated_at,
            expires_at=excluded.expires_at;
        """,
        (
            area_norm,
            veh_norm,
            row_end_norm,
            1 if checked else 0,
            now_berlin().isoformat(timespec="seconds"),
            exp_norm,
        ),
        commit=True,
    )


def get_shopfloorboard_5s_week(iso_year: int, iso_week: int) -> dict[str, str]:
    row = db_exec(
        """
        SELECT fruehschicht, spaetschicht, nachtschicht
        FROM shopfloorboard_5s
        WHERE iso_year=? AND iso_week=?;
        """,
        (int(iso_year), int(iso_week)),
        fetchone=True,
    )
    if not row:
        return {"fruehschicht": "", "spaetschicht": "", "nachtschicht": ""}
    return {
        "fruehschicht": str(row["fruehschicht"] or ""),
        "spaetschicht": str(row["spaetschicht"] or ""),
        "nachtschicht": str(row["nachtschicht"] or ""),
    }


def save_shopfloorboard_5s_week(
    *,
    iso_year: int,
    iso_week: int,
    fruehschicht: str,
    spaetschicht: str,
    nachtschicht: str,
) -> None:
    now_iso = now_berlin().isoformat(timespec="seconds")
    db_exec(
        """
        INSERT INTO shopfloorboard_5s (
            iso_year, iso_week, fruehschicht, spaetschicht, nachtschicht, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(iso_year, iso_week) DO UPDATE SET
            fruehschicht=excluded.fruehschicht,
            spaetschicht=excluded.spaetschicht,
            nachtschicht=excluded.nachtschicht,
            updated_at=excluded.updated_at;
        """,
        (
            int(iso_year),
            int(iso_week),
            str(fruehschicht or "").strip(),
            str(spaetschicht or "").strip(),
            str(nachtschicht or "").strip(),
            now_iso,
        ),
        commit=True,
    )


def _plan_date_iso(plan_day: date | datetime | str) -> str:
    if isinstance(plan_day, datetime):
        plan_day = plan_day.date()
    if isinstance(plan_day, date):
        return plan_day.isoformat()
    raw = str(plan_day or "").strip()
    try:
        return date.fromisoformat(raw[:10]).isoformat()
    except Exception:
        return raw[:10]


def get_ausseneinsatz_key(plan_day: date | datetime | str) -> str:
    row = db_exec(
        """
        SELECT assignment_key
        FROM ausseneinsatz_plan
        WHERE plan_date=?;
        """,
        (_plan_date_iso(plan_day),),
        fetchone=True,
    )
    if not row:
        return ""
    key = str(row["assignment_key"] or "").strip()
    return key if key in AUSSENEINSATZ_OPTIONS else ""


def get_ausseneinsatz_label(plan_day: date | datetime | str) -> str:
    return str(AUSSENEINSATZ_OPTIONS.get(get_ausseneinsatz_key(plan_day), "") or "")


def format_ausseneinsatz_status(plan_day: date | datetime | str) -> str:
    plan_date_txt = _plan_date_iso(plan_day)
    try:
        plan_date = date.fromisoformat(plan_date_txt)
        day_label = plan_date.strftime("%d.%m.%Y")
    except Exception:
        day_label = plan_date_txt
    label = get_ausseneinsatz_label(plan_date_txt)
    if label:
        return f"Außeneinsatz {day_label}: {label}"
    return f"Kein Außeneinsatz für {day_label} gesetzt."


def save_ausseneinsatz(plan_day: date | datetime | str, assignment_key: str | None) -> None:
    plan_date_txt = _plan_date_iso(plan_day)
    key = str(assignment_key or "").strip()
    if key not in AUSSENEINSATZ_OPTIONS:
        db_exec(
            "DELETE FROM ausseneinsatz_plan WHERE plan_date=?;",
            (plan_date_txt,),
            commit=True,
        )
        return

    db_exec(
        """
        INSERT INTO ausseneinsatz_plan (plan_date, assignment_key, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(plan_date) DO UPDATE SET
            assignment_key=excluded.assignment_key,
            updated_at=excluded.updated_at;
        """,
        (
            plan_date_txt,
            key,
            now_berlin().isoformat(timespec="seconds"),
        ),
        commit=True,
    )


def open_ausseneinsatz_dialog(plan_day: date | datetime | str, refresh_fn: Callable[[], None] | None = None) -> None:
    plan_date_txt = _plan_date_iso(plan_day)
    try:
        plan_date = date.fromisoformat(plan_date_txt)
    except Exception:
        plan_date = now_berlin().date()
    current_key = None

    with ui.dialog() as dialog, ui.card().classes("dialog-card"):
        _attach_dialog_tracking(dialog)
        dialog.props("persistent")
        ui.label(f"Außeneinsatz - {plan_date:%d.%m.%Y}").classes("dialog-title")
        ui.label("Mitarbeiterkombination auswählen").classes("text-lg font-bold text-gray-300")
        sel = ui.radio(
            AUSSENEINSATZ_OPTIONS,
            value=current_key or None,
        ).props("dense").classes("w-[620px] max-w-full ausseneinsatz-radio")

        with ui.row().classes("w-full items-center justify-between gap-2 mt-3 wrap"):
            def do_save() -> None:
                if sel.value in (None, ""):
                    ui.notify("Bitte eine Besetzung auswählen.", type="warning")
                    return
                payload = _build_ausseneinsatz_payload(
                    plan_day=plan_date,
                    selection_key=str(sel.value),
                )
                ok, info = notify_delay(payload)
                if ok:
                    ui.notify(f"Außeneinsatz gemeldet. ({info})", type="positive")
                    _close_tracked_dialog(dialog)
                    if refresh_fn:
                        refresh_fn()
                    return
                if "NOTIFY_FLOW_URL fehlt" in str(info or ""):
                    ui.notify(
                        "Außeneinsatz wurde nicht gesendet, weil NOTIFY_FLOW_URL nicht konfiguriert ist.",
                        type="warning",
                    )
                    return
                ui.notify(f"Außeneinsatz konnte nicht gesendet werden: {info}", type="warning")

            ui.button("Abbrechen", on_click=lambda d=dialog: _close_tracked_dialog(d)).props("flat")
            ui.button("Speichern", on_click=do_save).props("color=primary").classes("btn-big")

    _open_tracked_dialog(dialog)


def auto_clear_shopfloorboard_5s_if_due(now_dt: datetime | None = None) -> None:
    now_loc = as_berlin(now_dt or now_berlin()) or now_berlin()
    if now_loc.weekday() != 6 or now_loc.time() < time(20, 0):
        return
    iso = now_loc.isocalendar()
    iso_year = int(iso.year)
    iso_week = int(iso.week)
    cur_vals = get_shopfloorboard_5s_week(iso_year, iso_week)
    if not any(str(cur_vals.get(k, "") or "").strip() for k in ("fruehschicht", "spaetschicht", "nachtschicht")):
        return
    save_shopfloorboard_5s_week(
        iso_year=iso_year,
        iso_week=iso_week,
        fruehschicht="",
        spaetschicht="",
        nachtschicht="",
    )
