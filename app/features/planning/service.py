from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any

from core import db as db_core
from core.config import DB_PATH
from core.utils import make_sig

from .calculations import build_capacity_result, calculate_planned_minutes, resolve_time_rule
from .models import (
    DEFAULT_CAPACITY_SLOTS,
    JOB_STATUS_CONFLICT,
    JOB_STATUS_DRAFT,
    JOB_STATUS_PLANNED,
    detect_vehicle_type,
    normalize_place_code,
)
from .repository import (
    create_planning_job,
    delete_planning_allocation,
    delete_planning_allocations_by_ids,
    delete_planning_allocations_for_order,
    delete_planning_allocations_for_range,
    delete_planning_order,
    ensure_planning_schema,
    ensure_capacity_slots_for_dates,
    get_planning_order,
    list_assignments_for_day,
    list_capacity_roles,
    list_capacity_slots_for_range,
    list_planning_allocations_for_range,
    list_planning_allocations_for_order_ids,
    list_planning_order_allocation_totals,
    list_planning_orders,
    list_planning_slots_for_day,
    list_places,
    list_place_rules,
    list_shift_staffing,
    list_shift_templates,
    list_slot_templates,
    list_planning_jobs_for_day,
    list_slot_assignments,
    list_time_rules,
    list_ui_settings,
    list_vehicle_types,
    replace_places,
    replace_capacity_roles,
    replace_planning_order_block_allocations,
    reset_capacity_allocation_mode_for_range,
    replace_shift_staffing,
    replace_shift_templates,
    replace_slot_templates,
    save_planning_order,
    save_capacity_slot,
    save_ui_settings,
    save_planning_allocation,
    save_planning_allocations_batch,
    save_planning_slot,
    save_planning_slot_assignment,
    save_assignment,
    seed_capacity_roles,
    seed_planning_places,
    update_planning_job_metrics,
)
from .rules import is_place_allowed


_INITIALIZED_DB_KEYS: set[str] = set()
DEFAULT_UI_SETTINGS: dict[str, str] = {
    "home_show_open_orders": "1",
    "home_show_partial_orders": "1",
    "home_show_done_orders": "1",
    "overplanned_threshold": "0.5",
}


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _active_db_path(db_path: str | None = None) -> str:
    return str(db_path or db_core.DB_PATH or DB_PATH)


def _slot_ma_to_required_units(value: float | int | None) -> float:
    return float(value or 0.0) / 2.0


def _parse_hhmm_to_minutes(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text or ":" not in text:
        return None
    try:
        hours, minutes = text.split(":", 1)
        hour_i = int(hours)
        minute_i = int(minutes)
    except Exception:
        return None
    if hour_i < 0 or hour_i > 23 or minute_i < 0 or minute_i > 59:
        return None
    return (hour_i * 60) + minute_i


def _format_minutes_as_hhmm(value: int) -> str:
    normalized = int(value) % (24 * 60)
    return f"{normalized // 60:02d}:{normalized % 60:02d}"


def _combine_date_time_to_iso(date_value: Any, time_value: Any) -> str | None:
    date_txt = str(date_value or "").strip()
    time_txt = str(time_value or "").strip()
    if not date_txt:
        return None
    if not time_txt:
        return date_txt
    return f"{date_txt}T{time_txt}"


def _normalize_source_origin(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"open_tasks_manual", "upload_legacy", "planner"}:
        return raw
    return "planner"


def _normalize_release_status(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"draft", "entwurf", "in_erstellung", "erstellung", ""}:
        return "in_erstellung"
    if raw in {"in_planung", "planung", "in planung"}:
        return "in_planung"
    if raw in {"freigegeben", "released"}:
        return "freigegeben"
    if raw in {"done", "erledigt"}:
        return "erledigt"
    if raw in {"storniert", "cancelled", "canceled"}:
        return "storniert"
    return raw or "in_erstellung"


def _parse_slot_interval(slot_date: Any, slot_label: Any) -> tuple[str, str, str, str]:
    day_text = str(slot_date or "").strip()
    label_text = str(slot_label or "").replace("–", "-").strip()
    if not day_text or "-" not in label_text:
        return "", "", "", ""
    start_text, end_text = [part.strip() for part in label_text.split("-", 1)]
    if len(start_text) < 5 or len(end_text) < 5:
        return "", "", "", ""
    end_day = day_text
    start_minutes = _parse_hhmm_to_minutes(start_text)
    end_minutes = _parse_hhmm_to_minutes(end_text)
    if start_minutes is not None and end_minutes is not None and end_minutes <= start_minutes:
        try:
            end_day = (date.fromisoformat(day_text) + timedelta(days=1)).isoformat()
        except ValueError:
            end_day = day_text
    return day_text, start_text[:5], end_day, end_text[:5]


def _sync_order_schedule_from_allocations(
    planning_order_id: int,
    *,
    reset_release: bool = False,
    db_path: str | None = None,
) -> None:
    order = get_planning_order(int(planning_order_id), db_path=db_path)
    if not order:
        return
    allocation_rows = list_planning_allocations_for_order_ids([int(planning_order_id)], db_path=db_path)
    ecm4_start_date = ""
    ecm4_start_time = ""
    ecm4_end_date = ""
    ecm4_end_time = ""
    ecm4_place_code = ""
    if allocation_rows:
        first_row = allocation_rows[0]
        last_row = allocation_rows[-1]
        start_date, start_time, _, _ = _parse_slot_interval(first_row.get("slot_date"), first_row.get("slot_label"))
        _, _, end_date, end_time = _parse_slot_interval(last_row.get("slot_date"), last_row.get("slot_label"))
        ecm4_start_date = start_date
        ecm4_start_time = start_time
        ecm4_end_date = end_date
        ecm4_end_time = end_time
        place_codes = [str(row.get("place_code") or "").strip() for row in allocation_rows if str(row.get("place_code") or "").strip()]
        unique_places = list(dict.fromkeys(place_codes))
        ecm4_place_code = ", ".join(unique_places)
    current_status = _normalize_release_status(order.get("status"))
    next_status = "in_planung" if reset_release and current_status == "freigegeben" else current_status
    save_planning_order(
        order_id=int(planning_order_id),
        fahrzeug=str(order.get("fahrzeug") or ""),
        friststufe=str(order.get("friststufe") or ""),
        order_kind=str(order.get("order_kind") or ""),
        zusatzarbeiten=str(order.get("zusatzarbeiten") or ""),
        gewerke_info=str(order.get("gewerke_info") or ""),
        ecm3_start_date=str(order.get("ecm3_start_date") or ""),
        ecm3_start_time=str(order.get("ecm3_start_time") or ""),
        ecm3_end_date=str(order.get("ecm3_end_date") or ""),
        ecm3_end_time=str(order.get("ecm3_end_time") or ""),
        required_ma_8h=order.get("required_ma_8h"),
        planned_ma=order.get("planned_ma"),
        ecm4_start_date=ecm4_start_date,
        ecm4_start_time=ecm4_start_time,
        ecm4_end_date=ecm4_end_date,
        ecm4_end_time=ecm4_end_time,
        ecm4_place_code=ecm4_place_code,
        status=next_status,
        source_origin=str(order.get("source_origin") or ""),
        source_open_task_id=order.get("source_open_task_id"),
        source_sheet=str(order.get("source_sheet") or ""),
        source_row_number=order.get("source_row_number"),
        created_at=str(order.get("created_at") or "") or None,
        updated_at=_now_iso(),
        db_path=db_path,
    )
    _sync_open_task_from_planning_order(int(planning_order_id), db_path=db_path)


def _sync_order_schedules_from_allocations_fast(
    planning_order_ids: set[int],
    *,
    reset_release: bool = True,
    db_path: str | None = None,
) -> None:
    clean_ids = {int(value) for value in planning_order_ids if int(value or 0) > 0}
    if not clean_ids:
        return
    now_iso = _now_iso()
    conn = sqlite3.connect(_active_db_path(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        for order_id in clean_ids:
            order = cur.execute("SELECT * FROM planning_orders WHERE id=? LIMIT 1;", (int(order_id),)).fetchone()
            if order is None:
                continue
            allocation_rows = cur.execute(
                """
                SELECT a.place_code, s.slot_date, s.slot_label
                FROM planning_allocations a
                JOIN planning_capacity_slots s ON s.id = a.capacity_slot_id
                WHERE a.planning_order_id=?
                ORDER BY s.slot_date ASC, s.slot_label ASC, a.place_code ASC
                ;
                """,
                (int(order_id),),
            ).fetchall()
            ecm4_start_date = ""
            ecm4_start_time = ""
            ecm4_end_date = ""
            ecm4_end_time = ""
            ecm4_place_code = ""
            if allocation_rows:
                first_row = allocation_rows[0]
                last_row = allocation_rows[-1]
                start_date, start_time, _, _ = _parse_slot_interval(first_row["slot_date"], first_row["slot_label"])
                _, _, end_date, end_time = _parse_slot_interval(last_row["slot_date"], last_row["slot_label"])
                ecm4_start_date = start_date
                ecm4_start_time = start_time
                ecm4_end_date = end_date
                ecm4_end_time = end_time
                place_codes = [str(row["place_code"] or "").strip() for row in allocation_rows if str(row["place_code"] or "").strip()]
                ecm4_place_code = ", ".join(dict.fromkeys(place_codes))
            current_status = _normalize_release_status(order["status"])
            next_status = "in_planung" if reset_release and current_status == "freigegeben" else current_status
            source_origin = _normalize_source_origin(order["source_origin"])
            source_open_task_id = int(order["source_open_task_id"] or 0)
            next_source_open_task_id = source_open_task_id
            should_be_visible = next_status != "erledigt" and (
                source_origin == "open_tasks_manual" or next_status == "freigegeben"
            )
            if not should_be_visible and source_origin != "open_tasks_manual":
                cur.execute("DELETE FROM open_tasks WHERE planning_order_id=?;", (int(order_id),))
                if source_open_task_id > 0:
                    cur.execute("DELETE FROM open_tasks WHERE id=?;", (source_open_task_id,))
                next_source_open_task_id = 0
            cur.execute(
                """
                UPDATE planning_orders
                SET ecm4_start_date=?, ecm4_start_time=?, ecm4_end_date=?, ecm4_end_time=?,
                    ecm4_place_code=?, status=?, source_open_task_id=?, updated_at=?
                WHERE id=?
                ;
                """,
                (
                    ecm4_start_date or None,
                    ecm4_start_time or None,
                    ecm4_end_date or None,
                    ecm4_end_time or None,
                    normalize_place_code(ecm4_place_code) if ecm4_place_code else None,
                    next_status,
                    int(next_source_open_task_id) if int(next_source_open_task_id or 0) > 0 else None,
                    now_iso,
                    int(order_id),
                ),
            )
        conn.commit()
    finally:
        conn.close()
    db_core.bump_data_version()


def _sync_open_task_from_planning_order(
    planning_order_id: int,
    *,
    db_path: str | None = None,
) -> None:
    order = get_planning_order(int(planning_order_id), db_path=db_path)
    if not order:
        return

    fahrzeug = str(order.get("fahrzeug") or "").strip()
    friststufe = str(order.get("friststufe") or "").strip()
    if not fahrzeug:
        return

    source_origin = _normalize_source_origin(order.get("source_origin"))
    release_status = _normalize_release_status(order.get("status"))
    ecm3_start_iso = _combine_date_time_to_iso(order.get("ecm3_start_date"), order.get("ecm3_start_time"))
    ecm3_end_iso = _combine_date_time_to_iso(order.get("ecm3_end_date"), order.get("ecm3_end_time"))
    ecm4_start_iso = _combine_date_time_to_iso(order.get("ecm4_start_date"), order.get("ecm4_start_time"))
    ecm4_end_iso = _combine_date_time_to_iso(order.get("ecm4_end_date"), order.get("ecm4_end_time"))
    start_iso = ecm4_start_iso or ecm3_start_iso
    end_iso = ecm4_end_iso or ecm3_end_iso
    ecm3_fertig_iso = ecm3_end_iso or end_iso
    ecm4_place_code = str(order.get("ecm4_place_code") or "").strip()
    zusatzarbeiten = str(order.get("zusatzarbeiten") or "").strip()
    gewerke_info = str(order.get("gewerke_info") or "").strip()
    source_open_task_id = int(order.get("source_open_task_id") or 0)

    sig = make_sig(fahrzeug, friststufe, start_iso, end_iso)

    should_be_visible = release_status != "erledigt" and (
        source_origin == "open_tasks_manual" or release_status == "freigegeben"
    )
    if not should_be_visible and source_origin != "open_tasks_manual" and source_open_task_id <= 0:
        return

    conn = sqlite3.connect(_active_db_path(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        with db_core.DB_WRITE_LOCK:
            cur = conn.cursor()
            try:
                target_row = None
                if source_open_task_id > 0:
                    target_row = cur.execute(
                        "SELECT id, initial_fertig FROM open_tasks WHERE id=?;",
                        (source_open_task_id,),
                    ).fetchone()
                if target_row is None:
                    target_row = cur.execute(
                        "SELECT id, initial_fertig FROM open_tasks WHERE planning_order_id=?;",
                        (int(planning_order_id),),
                    ).fetchone()

                if not should_be_visible:
                    if target_row is not None:
                        cur.execute("DELETE FROM open_tasks WHERE id=?;", (int(target_row["id"]),))
                    conn.commit()
                    source_open_task_id = 0 if source_origin != "open_tasks_manual" else source_open_task_id
                elif target_row is None:
                    cur.execute(
                        """
                        INSERT INTO open_tasks (
                            fahrzeug, friststufe, anfang, fertig, ecm3_fertig, arbeitsplatz,
                            ap_pdf, zusatzarbeiten, gewerke, sig, initial_fertig, planning_order_id, source_system
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            fahrzeug,
                            friststufe or None,
                            start_iso,
                            end_iso,
                            ecm3_fertig_iso,
                            "",
                            ecm4_place_code,
                            zusatzarbeiten,
                            gewerke_info,
                            sig,
                            end_iso,
                            int(planning_order_id),
                            source_origin,
                        ),
                    )
                    if source_open_task_id <= 0:
                        source_open_task_id = int(cur.lastrowid or 0)
                elif target_row is not None:
                    initial_fertig = str(target_row["initial_fertig"] or "").strip() or end_iso
                    cur.execute(
                        """
                        UPDATE open_tasks
                        SET fahrzeug=?, friststufe=?, anfang=?, fertig=?, ecm3_fertig=?,
                            ap_pdf=?, zusatzarbeiten=?, gewerke=?, sig=?, initial_fertig=?,
                            planning_order_id=?, source_system=?
                        WHERE id=?
                        ;
                        """,
                        (
                            fahrzeug,
                            friststufe or None,
                            start_iso,
                            end_iso,
                            ecm3_fertig_iso,
                            ecm4_place_code,
                            zusatzarbeiten,
                            gewerke_info,
                            sig,
                            initial_fertig,
                            int(planning_order_id),
                            source_origin,
                            int(target_row["id"]),
                        ),
                    )
                    if source_open_task_id <= 0:
                        source_open_task_id = int(target_row["id"] or 0)
                conn.commit()
            finally:
                cur.close()
        db_core.bump_data_version()
    finally:
        conn.close()

    if int(source_open_task_id or 0) != int(order.get("source_open_task_id") or 0):
        save_planning_order(
            order_id=int(planning_order_id),
            fahrzeug=fahrzeug,
            friststufe=friststufe,
            order_kind=str(order.get("order_kind") or ""),
            zusatzarbeiten=zusatzarbeiten,
            gewerke_info=gewerke_info,
            ecm3_start_date=str(order.get("ecm3_start_date") or ""),
            ecm3_start_time=str(order.get("ecm3_start_time") or ""),
            ecm3_end_date=str(order.get("ecm3_end_date") or ""),
            ecm3_end_time=str(order.get("ecm3_end_time") or ""),
            required_ma_8h=order.get("required_ma_8h"),
            planned_ma=order.get("planned_ma"),
            ecm4_start_date=str(order.get("ecm4_start_date") or ""),
            ecm4_start_time=str(order.get("ecm4_start_time") or ""),
            ecm4_end_date=str(order.get("ecm4_end_date") or ""),
            ecm4_end_time=str(order.get("ecm4_end_time") or ""),
            ecm4_place_code=ecm4_place_code,
            status=release_status,
            source_origin=source_origin,
            source_open_task_id=(int(source_open_task_id) if int(source_open_task_id or 0) > 0 else None),
            source_sheet=str(order.get("source_sheet") or ""),
            source_row_number=order.get("source_row_number"),
            updated_at=_now_iso(),
            created_at=str(order.get("created_at") or "") or None,
            db_path=db_path,
        )


def _enrich_orders_with_allocation_totals(
    orders: list[dict[str, Any]],
    allocation_totals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    allocated_by_order = {
        int(row.get("planning_order_id") or 0): _slot_ma_to_required_units(row.get("allocated_total") or 0.0)
        for row in allocation_totals
        if int(row.get("planning_order_id") or 0) > 0
    }
    enriched_orders: list[dict[str, Any]] = []
    for row in orders:
        order_id = int(row.get("id") or 0)
        required_total = float(row.get("planned_ma") or row.get("required_ma_8h") or 0.0)
        allocated_total = allocated_by_order.get(order_id, 0.0)
        remaining_total = max(0.0, required_total - allocated_total)
        overallocated_total = max(0.0, allocated_total - required_total) if required_total > 0 else 0.0
        progress_ratio = (allocated_total / required_total) if required_total > 0 else 0.0
        progress_state = "open"
        if overallocated_total > 0:
            progress_state = "overplanned"
        elif required_total > 0 and remaining_total <= 0:
            progress_state = "done"
        elif allocated_total > 0:
            progress_state = "partial"
        enriched_orders.append(
            {
                **row,
                "required_total": required_total,
                "allocated_total": allocated_total,
                "remaining_total": remaining_total,
                "overallocated_total": overallocated_total,
                "progress_ratio": progress_ratio,
                "progress_state": progress_state,
            }
        )
    return enriched_orders


def _build_slot_rows_from_shifts(shift_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    slot_rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in shift_rows:
        shift_name = str(row.get("shift_name") or "").strip()
        start_time = str(row.get("start_time") or "").strip()
        end_time = str(row.get("end_time") or "").strip()
        start_minutes = _parse_hhmm_to_minutes(start_time)
        end_minutes = _parse_hhmm_to_minutes(end_time)
        try:
            slot_count = max(1, int(row.get("slot_count") or 1))
        except Exception:
            slot_count = 1
        if not shift_name or start_minutes is None or end_minutes is None:
            continue
        duration = end_minutes - start_minutes
        if duration <= 0:
            duration += 24 * 60
        slot_length = max(1, duration // slot_count)
        current = start_minutes
        for index in range(slot_count):
            next_value = end_minutes if index == slot_count - 1 else current + slot_length
            slot_label = f"{_format_minutes_as_hhmm(current)} - {_format_minutes_as_hhmm(next_value)}"
            if slot_label not in seen:
                seen.add(slot_label)
                slot_rows.append(
                    {
                        "shift_name": shift_name,
                        "slot_label": slot_label,
                        "start_time": _format_minutes_as_hhmm(current),
                        "end_time": _format_minutes_as_hhmm(next_value),
                    }
                )
            current = next_value
    return slot_rows


def _sync_week_capacity_from_staffing(
    *,
    week_dates: list[str],
    slot_templates: list[dict[str, Any]],
    shift_templates: list[dict[str, Any]] | None = None,
    staffing_rows: list[dict[str, Any]] | None = None,
    active_roles: list[dict[str, Any]] | None = None,
    existing_capacity_rows: list[dict[str, Any]] | None = None,
    db_path: str | None = None,
) -> bool:
    shift_templates = shift_templates if shift_templates is not None else list_shift_templates(active_only=True, db_path=db_path)
    staffing_rows = staffing_rows if staffing_rows is not None else list_shift_staffing(db_path=db_path)
    active_roles = active_roles if active_roles is not None else list_capacity_roles(active_only=True, db_path=db_path)
    if not week_dates or not slot_templates or not shift_templates:
        return False

    derived_slots = _build_slot_rows_from_shifts(shift_templates)
    shift_name_by_label = {
        str(row.get("slot_label") or ""): str(row.get("shift_name") or "")
        for row in derived_slots
        if str(row.get("slot_label") or "").strip()
    }
    active_role_keys = {str(row.get("role_key") or "") for row in active_roles if str(row.get("role_key") or "").strip()}
    staffing_map = {
        (
            str(row.get("shift_name") or ""),
            int(row.get("weekday") or 0),
            str(row.get("role_key") or ""),
        ): float(row.get("capacity") or 0.0)
        for row in staffing_rows
    }
    existing_rows = {
        (str(row.get("slot_date") or ""), str(row.get("slot_label") or "")): row
        for row in (
            existing_capacity_rows
            if existing_capacity_rows is not None
            else list_capacity_slots_for_range(week_dates[0], week_dates[-1], db_path=db_path)
        )
    }

    changed = False
    for slot_date in week_dates:
        weekday = date.fromisoformat(slot_date).weekday()
        for template in slot_templates:
            slot_label = str(template.get("slot_label") or "")
            shift_name = shift_name_by_label.get(slot_label, "")
            if not shift_name:
                continue
            existing = existing_rows.get((slot_date, slot_label)) or {}
            source_name = str(existing.get("source_name") or "").strip().lower()
            allocation_mode = str(existing.get("allocation_mode") or "auto").strip().lower() or "auto"
            if source_name == "manuell":
                continue
            workshop_capacity = staffing_map.get((shift_name, weekday, "workshop"), 0.0) if "workshop" in active_role_keys else 0.0
            service_capacity = staffing_map.get((shift_name, weekday, "service"), 0.0) if "service" in active_role_keys else 0.0
            urd_capacity = staffing_map.get((shift_name, weekday, "urd"), 0.0) if "urd" in active_role_keys else 0.0
            existing_workshop = float(existing.get("workshop_capacity") or 0.0)
            existing_service = float(existing.get("service_capacity") or 0.0)
            existing_urd = float(existing.get("urd_capacity") or 0.0)
            existing_notes = str(existing.get("notes") or "")
            if (
                existing
                and existing_workshop == workshop_capacity
                and existing_service == service_capacity
                and existing_urd == urd_capacity
                and source_name == "regelbesetzung"
            ):
                continue
            save_capacity_slot(
                slot_date=slot_date,
                slot_label=slot_label,
                workshop_capacity=workshop_capacity,
                service_capacity=service_capacity,
                urd_capacity=urd_capacity,
                allocation_mode=allocation_mode,
                source_name="regelbesetzung",
                notes=existing_notes,
                capacity_slot_id=int(existing.get("id") or 0) or None,
                updated_at=_now_iso(),
                db_path=db_path,
            )
            changed = True
    return changed


def initialize_planning_module(db_path: str | None = None) -> None:
    db_key = os.path.abspath(str(db_path)) if db_path else "__default__"
    if db_key in _INITIALIZED_DB_KEYS:
        return
    ensure_planning_schema(db_path)
    seed_planning_places(db_path)
    seed_capacity_roles(db_path)
    _INITIALIZED_DB_KEYS.add(db_key)


def get_planning_master_data(*, db_path: str | None = None) -> dict[str, Any]:
    return {
        "places": list_places(active_only=False, db_path=db_path),
        "capacity_roles": list_capacity_roles(active_only=False, db_path=db_path),
        "shift_templates": list_shift_templates(active_only=False, db_path=db_path),
        "shift_staffing": list_shift_staffing(db_path=db_path),
        "slot_templates": list_slot_templates(active_only=False, db_path=db_path),
        "vehicle_types": list_vehicle_types(active_only=False, db_path=db_path),
        "place_rules": list_place_rules(active_only=False, db_path=db_path),
        "time_rules": list_time_rules(active_only=False, db_path=db_path),
    }


def get_planner_configuration(*, db_path: str | None = None) -> dict[str, Any]:
    initialize_planning_module(db_path)
    places = list_places(active_only=True, db_path=db_path)
    slot_templates = list_slot_templates(active_only=True, db_path=db_path)
    ui_settings = {**DEFAULT_UI_SETTINGS, **list_ui_settings(db_path=db_path)}
    return {
        "places": places,
        "capacity_roles": list_capacity_roles(active_only=False, db_path=db_path),
        "shift_templates": list_shift_templates(active_only=True, db_path=db_path),
        "shift_staffing": list_shift_staffing(db_path=db_path),
        "slot_templates": slot_templates,
        "slot_labels": [str(row.get("slot_label") or "") for row in slot_templates],
        "ui_settings": ui_settings,
        "needs_setup": (len(places) == 0 or len(slot_templates) == 0),
    }


def save_planner_ui_settings(settings: dict[str, Any], *, db_path: str | None = None) -> None:
    initialize_planning_module(db_path)
    normalized: dict[str, str] = {}
    for key, value in settings.items():
        key_txt = str(key or "").strip()
        if not key_txt:
            continue
        if key_txt == "overplanned_threshold":
            normalized[key_txt] = str(float(value or 0.0))
        else:
            normalized[key_txt] = "1" if bool(value) else "0"
    save_ui_settings(normalized, db_path=db_path)


def save_planner_configuration(
    *,
    place_codes: list[str],
    slot_rows: list[dict[str, Any]],
    shift_rows: list[dict[str, Any]] | None = None,
    staffing_rows: list[dict[str, Any]] | None = None,
    capacity_roles: list[dict[str, Any]] | None = None,
    db_path: str | None = None,
) -> None:
    initialize_planning_module(db_path)
    replace_places(place_codes, db_path=db_path)
    replace_slot_templates(slot_rows, db_path=db_path)
    if capacity_roles is not None:
        replace_capacity_roles(capacity_roles, db_path=db_path)
    if shift_rows is not None:
        replace_shift_templates(shift_rows, db_path=db_path)
    if staffing_rows is not None:
        replace_shift_staffing(staffing_rows, db_path=db_path)


def calculate_job_snapshot(
    *,
    fahrzeug: str,
    friststufe: str,
    start_dt: str,
    end_dt: str,
    extra_minutes: int = 0,
    db_path: str | None = None,
) -> dict[str, Any]:
    vehicle_type_code = detect_vehicle_type(fahrzeug)
    all_rules = list_time_rules(active_only=True, db_path=db_path)
    time_rule = resolve_time_rule(all_rules, vehicle_type_code, friststufe)
    base_minutes = int((time_rule or {}).get("base_minutes") or 0)
    stand_minutes_min = int((time_rule or {}).get("stand_minutes_min") or 0)
    stand_factor = float((time_rule or {}).get("stand_factor") or 1.0)
    planned_minutes = calculate_planned_minutes(start_dt, end_dt)
    result = build_capacity_result(
        base_minutes=base_minutes,
        extra_minutes=int(extra_minutes),
        stand_factor=stand_factor,
        stand_minutes_min=stand_minutes_min,
        planned_minutes=planned_minutes,
    )
    result["vehicle_type_code"] = vehicle_type_code
    result["time_rule"] = time_rule
    return result


def validate_assignment(
    *,
    fahrzeug: str,
    friststufe: str,
    place_code: str,
    start_dt: str,
    end_dt: str,
    extra_minutes: int = 0,
    db_path: str | None = None,
) -> dict[str, Any]:
    snapshot = calculate_job_snapshot(
        fahrzeug=fahrzeug,
        friststufe=friststufe,
        start_dt=start_dt,
        end_dt=end_dt,
        extra_minutes=extra_minutes,
        db_path=db_path,
    )
    allowed, reason = is_place_allowed(snapshot.get("vehicle_type_code", ""), place_code, db_path=db_path)
    status = JOB_STATUS_PLANNED
    if not allowed or not snapshot.get("fits_required_time") or not snapshot.get("fits_required_stand_time"):
        status = JOB_STATUS_CONFLICT
    if not snapshot.get("time_rule"):
        status = JOB_STATUS_DRAFT
    snapshot["place_allowed"] = allowed
    snapshot["place_message"] = reason
    snapshot["status"] = status
    return snapshot


def create_job_from_form(
    *,
    fahrzeug: str,
    friststufe: str,
    place_code: str,
    start_dt: str,
    end_dt: str,
    extra_minutes: int = 0,
    notes: str = "",
    source_open_task_id: int | None = None,
    db_path: str | None = None,
) -> dict[str, Any]:
    validation = validate_assignment(
        fahrzeug=fahrzeug,
        friststufe=friststufe,
        place_code=place_code,
        start_dt=start_dt,
        end_dt=end_dt,
        extra_minutes=extra_minutes,
        db_path=db_path,
    )
    now_iso = _now_iso()
    planning_job_id = create_planning_job(
        fahrzeug=fahrzeug,
        friststufe=friststufe,
        source_open_task_id=source_open_task_id,
        required_minutes=int(validation["required_minutes"]),
        planned_minutes=int(validation["planned_minutes"]),
        required_stand_minutes=int(validation["required_stand_minutes"]),
        status=str(validation["status"] or JOB_STATUS_DRAFT),
        notes=notes,
        created_at=now_iso,
        updated_at=now_iso,
        db_path=db_path,
    )
    assignment_id = save_assignment(
        planning_job_id=planning_job_id,
        place_code=place_code,
        start_dt=start_dt,
        end_dt=end_dt,
        note=notes,
        created_at=now_iso,
        updated_at=now_iso,
        db_path=db_path,
    )
    validation["planning_job_id"] = planning_job_id
    validation["assignment_id"] = assignment_id
    return validation


def create_or_update_assignment(
    *,
    planning_job_id: int,
    fahrzeug: str,
    friststufe: str,
    place_code: str,
    start_dt: str,
    end_dt: str,
    extra_minutes: int = 0,
    assignment_id: int | None = None,
    db_path: str | None = None,
) -> dict[str, Any]:
    validation = validate_assignment(
        fahrzeug=fahrzeug,
        friststufe=friststufe,
        place_code=place_code,
        start_dt=start_dt,
        end_dt=end_dt,
        extra_minutes=extra_minutes,
        db_path=db_path,
    )
    now_iso = _now_iso()
    saved_assignment_id = save_assignment(
        planning_job_id=planning_job_id,
        place_code=place_code,
        start_dt=start_dt,
        end_dt=end_dt,
        updated_at=now_iso,
        assignment_id=assignment_id,
        db_path=db_path,
    )
    update_planning_job_metrics(
        planning_job_id=planning_job_id,
        required_minutes=int(validation["required_minutes"]),
        planned_minutes=int(validation["planned_minutes"]),
        required_stand_minutes=int(validation["required_stand_minutes"]),
        status=str(validation["status"] or JOB_STATUS_DRAFT),
        updated_at=now_iso,
        db_path=db_path,
    )
    validation["assignment_id"] = saved_assignment_id
    return validation


def get_day_plan(day_iso: str, *, db_path: str | None = None) -> dict[str, Any]:
    return {
        "jobs": list_planning_jobs_for_day(day_iso, db_path=db_path),
        "assignments": list_assignments_for_day(day_iso, db_path=db_path),
        "places": list_places(active_only=True, db_path=db_path),
    }


def create_order_from_form(
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
    status: str = "draft",
    source_origin: str = "planner",
    source_open_task_id: int | None = None,
    source_sheet: str = "Fzg Zusatzarbeiten",
    source_row_number: int | None = None,
    db_path: str | None = None,
) -> int:
    initialize_planning_module(db_path)
    now_iso = _now_iso()
    order_id = save_planning_order(
        fahrzeug=fahrzeug,
        friststufe=friststufe,
        order_kind=order_kind,
        zusatzarbeiten=zusatzarbeiten,
        gewerke_info=gewerke_info,
        ecm3_start_date=ecm3_start_date,
        ecm3_start_time=ecm3_start_time,
        ecm3_end_date=ecm3_end_date,
        ecm3_end_time=ecm3_end_time,
        required_ma_8h=required_ma_8h,
        planned_ma=planned_ma,
        status=status,
        source_origin=source_origin,
        source_open_task_id=source_open_task_id,
        source_sheet=source_sheet,
        source_row_number=source_row_number,
        created_at=now_iso,
        updated_at=now_iso,
        db_path=db_path,
    )
    _sync_open_task_from_planning_order(order_id, db_path=db_path)
    return order_id


def upsert_order_from_form(
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
    status: str = "draft",
    source_origin: str = "planner",
    source_open_task_id: int | None = None,
    source_sheet: str = "Fzg Zusatzarbeiten",
    source_row_number: int | None = None,
    order_id: int | None = None,
    db_path: str | None = None,
) -> int:
    initialize_planning_module(db_path)
    now_iso = _now_iso()
    saved_order_id = save_planning_order(
        fahrzeug=fahrzeug,
        friststufe=friststufe,
        order_kind=order_kind,
        zusatzarbeiten=zusatzarbeiten,
        gewerke_info=gewerke_info,
        ecm3_start_date=ecm3_start_date,
        ecm3_start_time=ecm3_start_time,
        ecm3_end_date=ecm3_end_date,
        ecm3_end_time=ecm3_end_time,
        required_ma_8h=required_ma_8h,
        planned_ma=planned_ma,
        status=status,
        source_origin=source_origin,
        source_open_task_id=source_open_task_id,
        source_sheet=source_sheet,
        source_row_number=source_row_number,
        order_id=order_id,
        updated_at=now_iso,
        created_at=(now_iso if order_id is None else None),
        db_path=db_path,
    )
    _sync_open_task_from_planning_order(saved_order_id, db_path=db_path)
    return saved_order_id


def create_slot(
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
    db_path: str | None = None,
) -> int:
    initialize_planning_module(db_path)
    now_iso = _now_iso()
    return save_planning_slot(
        slot_date=slot_date,
        slot_time=slot_time,
        slot_start=slot_start,
        slot_end=slot_end,
        workshop_staff=workshop_staff,
        service_staff=service_staff,
        urd_staff=urd_staff,
        mek_value=mek_value,
        vehicle_count=vehicle_count,
        staff_per_vehicle=staff_per_vehicle,
        notes=notes,
        created_at=now_iso,
        updated_at=now_iso,
        db_path=db_path,
    )


def assign_order_to_slot(
    *,
    planning_order_id: int,
    slot_id: int,
    place_code: str,
    fahrzeug: str,
    note: str = "",
    db_path: str | None = None,
) -> dict[str, Any]:
    initialize_planning_module(db_path)
    now_iso = _now_iso()
    assignment_id = save_planning_slot_assignment(
        slot_id=slot_id,
        place_code=place_code,
        fahrzeug=fahrzeug,
        planning_order_id=planning_order_id,
        note=note,
        created_at=now_iso,
        updated_at=now_iso,
        db_path=db_path,
    )
    return {
        "assignment_id": assignment_id,
        "planning_order_id": int(planning_order_id),
        "slot_id": int(slot_id),
        "place_code": place_code,
        "fahrzeug": fahrzeug,
    }


def get_order_board(*, status: str | None = None, fahrzeug: str | None = None, db_path: str | None = None) -> dict[str, Any]:
    initialize_planning_module(db_path)
    orders = list_planning_orders(status=status, fahrzeug=fahrzeug, db_path=db_path)
    allocation_totals = list_planning_order_allocation_totals(db_path=db_path)
    enriched_orders = _enrich_orders_with_allocation_totals(orders, allocation_totals)
    return {
        "orders": enriched_orders,
        "places": list_places(active_only=True, db_path=db_path),
    }


def set_order_statuses(
    order_ids: list[int],
    *,
    status: str,
    db_path: str | None = None,
) -> list[int]:
    initialize_planning_module(db_path)
    normalized_status = _normalize_release_status(status)
    changed_ids: list[int] = []
    for raw_id in order_ids:
        order_id = int(raw_id or 0)
        if order_id <= 0:
            continue
        order = get_planning_order(order_id, db_path=db_path)
        if not order:
            continue
        save_planning_order(
            order_id=order_id,
            fahrzeug=str(order.get("fahrzeug") or ""),
            friststufe=str(order.get("friststufe") or ""),
            order_kind=str(order.get("order_kind") or ""),
            zusatzarbeiten=str(order.get("zusatzarbeiten") or ""),
            gewerke_info=str(order.get("gewerke_info") or ""),
            ecm3_start_date=str(order.get("ecm3_start_date") or ""),
            ecm3_start_time=str(order.get("ecm3_start_time") or ""),
            ecm3_end_date=str(order.get("ecm3_end_date") or ""),
            ecm3_end_time=str(order.get("ecm3_end_time") or ""),
            required_ma_8h=order.get("required_ma_8h"),
            planned_ma=order.get("planned_ma"),
            ecm4_start_date=str(order.get("ecm4_start_date") or ""),
            ecm4_start_time=str(order.get("ecm4_start_time") or ""),
            ecm4_end_date=str(order.get("ecm4_end_date") or ""),
            ecm4_end_time=str(order.get("ecm4_end_time") or ""),
            ecm4_place_code=str(order.get("ecm4_place_code") or ""),
            status=normalized_status,
            source_origin=str(order.get("source_origin") or ""),
            source_open_task_id=order.get("source_open_task_id"),
            source_sheet=str(order.get("source_sheet") or ""),
            source_row_number=order.get("source_row_number"),
            created_at=str(order.get("created_at") or "") or None,
            updated_at=_now_iso(),
            db_path=db_path,
        )
        _sync_open_task_from_planning_order(order_id, db_path=db_path)
        changed_ids.append(order_id)
    return changed_ids


def get_slot_board(day_iso: str, *, db_path: str | None = None) -> dict[str, Any]:
    initialize_planning_module(db_path)
    return {
        "slots": list_planning_slots_for_day(day_iso, db_path=db_path),
        "assignments": list_slot_assignments(slot_date=day_iso, db_path=db_path),
        "places": list_places(active_only=True, db_path=db_path),
    }


def save_capacity_from_form(
    *,
    slot_date: str,
    slot_label: str,
    workshop_capacity: float | int | None = None,
    service_capacity: float | int | None = None,
    urd_capacity: float | int | None = None,
    allocation_mode: str = "auto",
    source_name: str = "",
    notes: str = "",
    db_path: str | None = None,
) -> int:
    initialize_planning_module(db_path)
    now_iso = _now_iso()
    return save_capacity_slot(
        slot_date=slot_date,
        slot_label=slot_label,
        workshop_capacity=workshop_capacity,
        service_capacity=service_capacity,
        urd_capacity=urd_capacity,
        allocation_mode=allocation_mode,
        source_name=source_name,
        notes=notes,
        created_at=now_iso,
        updated_at=now_iso,
        db_path=db_path,
    )


def allocate_order_to_capacity(
    *,
    planning_order_id: int,
    capacity_slot_id: int,
    place_code: str,
    fahrzeug: str,
    allocated_ma: float | int | None = None,
    note: str = "",
    sync_schedule: bool = True,
    db_path: str | None = None,
) -> dict[str, Any]:
    initialize_planning_module(db_path)
    now_iso = _now_iso()
    allocation_id = save_planning_allocation(
        capacity_slot_id=capacity_slot_id,
        place_code=place_code,
        planning_order_id=planning_order_id,
        fahrzeug=fahrzeug,
        allocated_ma=allocated_ma,
        note=note,
        created_at=now_iso,
        updated_at=now_iso,
        db_path=db_path,
    )
    if sync_schedule:
        _sync_order_schedule_from_allocations(int(planning_order_id), db_path=db_path)
    return {
        "allocation_id": allocation_id,
        "planning_order_id": int(planning_order_id),
        "capacity_slot_id": int(capacity_slot_id),
        "place_code": place_code,
        "fahrzeug": fahrzeug,
        "allocated_ma": float(allocated_ma or 0),
    }


def allocate_orders_to_capacity_batch(
    allocation_rows: list[dict[str, Any]],
    *,
    sync_schedule_order_ids: list[int] | None = None,
    db_path: str | None = None,
) -> list[int]:
    initialize_planning_module(db_path)
    now_iso = _now_iso()
    saved_ids = save_planning_allocations_batch(
        allocation_rows,
        created_at=now_iso,
        updated_at=now_iso,
        db_path=db_path,
    )
    if sync_schedule_order_ids is None:
        touched_order_ids = {
            int(row.get("planning_order_id") or 0)
            for row in allocation_rows
            if int(row.get("planning_order_id") or 0) > 0
        }
    else:
        touched_order_ids = {int(value or 0) for value in sync_schedule_order_ids if int(value or 0) > 0}
    for order_id in touched_order_ids:
        _sync_order_schedule_from_allocations(order_id, reset_release=True, db_path=db_path)
    return saved_ids


def replace_order_block_allocations(
    *,
    planning_order_id: int,
    place_code: str,
    capacity_slot_ids: list[int],
    allocation_rows: list[dict[str, Any]],
    db_path: str | None = None,
) -> list[int]:
    initialize_planning_module(db_path)
    now_iso = _now_iso()
    saved_ids = replace_planning_order_block_allocations(
        planning_order_id=planning_order_id,
        place_code=place_code,
        capacity_slot_ids=capacity_slot_ids,
        allocation_rows=allocation_rows,
        created_at=now_iso,
        updated_at=now_iso,
        db_path=db_path,
    )
    _sync_order_schedules_from_allocations_fast({int(planning_order_id)}, reset_release=True, db_path=db_path)
    return saved_ids


def remove_allocation(
    *,
    allocation_id: int,
    sync_schedule: bool = True,
    db_path: str | None = None,
) -> None:
    initialize_planning_module(db_path)
    conn = sqlite3.connect(_active_db_path(db_path), timeout=30.0)
    try:
        touched_row = conn.execute(
            "SELECT planning_order_id FROM planning_allocations WHERE id=?;",
            (int(allocation_id),),
        ).fetchone()
    finally:
        conn.close()
    delete_planning_allocation(allocation_id=allocation_id, db_path=db_path)
    touched_order_id = int(touched_row[0] or 0) if touched_row else 0
    if sync_schedule and touched_order_id > 0:
        _sync_order_schedules_from_allocations_fast({touched_order_id}, reset_release=True, db_path=db_path)


def remove_allocations(
    *,
    allocation_ids: list[int],
    sync_schedule: bool = True,
    db_path: str | None = None,
) -> None:
    clean_ids = [int(value) for value in allocation_ids if int(value or 0) > 0]
    if not clean_ids:
        return
    placeholders = ",".join("?" for _ in clean_ids)
    conn = sqlite3.connect(_active_db_path(db_path), timeout=30.0)
    try:
        rows = conn.execute(
            f"SELECT DISTINCT planning_order_id FROM planning_allocations WHERE id IN ({placeholders});",
            clean_ids,
        ).fetchall()
    finally:
        conn.close()
    touched_order_ids = {int(row[0] or 0) for row in rows if int(row[0] or 0) > 0}
    delete_planning_allocations_by_ids(clean_ids, db_path=db_path)
    if sync_schedule:
        _sync_order_schedules_from_allocations_fast(touched_order_ids, reset_release=True, db_path=db_path)


def sync_order_schedule_from_allocations(
    *,
    planning_order_id: int,
    reset_release: bool = True,
    db_path: str | None = None,
) -> None:
    initialize_planning_module(db_path)
    _sync_order_schedules_from_allocations_fast({int(planning_order_id)}, reset_release=reset_release, db_path=db_path)


def remove_order_allocations(
    *,
    planning_order_id: int,
    db_path: str | None = None,
) -> None:
    initialize_planning_module(db_path)
    delete_planning_allocations_for_order(planning_order_id=planning_order_id, db_path=db_path)
    _sync_order_schedules_from_allocations_fast({int(planning_order_id)}, reset_release=True, db_path=db_path)


def _clear_week_allocations_legacy_unused(
    *,
    week_start_iso: str,
    db_path: str | None = None,
) -> dict[str, int]:
    initialize_planning_module(db_path)
    week_start = date.fromisoformat(str(week_start_iso))
    week_end = week_start + timedelta(days=6)
    existing_rows = list_planning_allocations_for_range(week_start.isoformat(), week_end.isoformat(), db_path=db_path)
    touched_order_ids = {
        int(row.get("planning_order_id") or 0)
        for row in existing_rows
        if int(row.get("planning_order_id") or 0) > 0
    }
    delete_planning_allocations_for_range(week_start.isoformat(), week_end.isoformat(), db_path=db_path)
    remaining_rows = list_planning_allocations_for_range(week_start.isoformat(), week_end.isoformat(), db_path=db_path)
    if remaining_rows:
        raise RuntimeError("Die Woche konnte nicht vollständig geleert werden.")
    reset_capacity_allocation_mode_for_range(
        week_start.isoformat(),
        week_end.isoformat(),
        allocation_mode="auto",
        updated_at=_now_iso(),
        db_path=db_path,
    )
    _sync_order_schedules_from_allocations_fast(touched_order_ids, reset_release=True, db_path=db_path)
    db_core.bump_data_version()
    return {"deleted_allocations": len(existing_rows), "touched_orders": len(touched_order_ids)}


def clear_week_allocations(
    *,
    week_start_iso: str,
    db_path: str | None = None,
) -> dict[str, int]:
    initialize_planning_module(db_path)
    week_start = date.fromisoformat(str(week_start_iso))
    week_end = week_start + timedelta(days=6)
    week_start_text = week_start.isoformat()
    week_end_text = week_end.isoformat()
    conn = sqlite3.connect(_active_db_path(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        existing_rows = conn.execute(
            """
            SELECT a.id, a.planning_order_id, COALESCE(o.status, '') AS order_status
            FROM planning_allocations a
            JOIN planning_capacity_slots s ON s.id = a.capacity_slot_id
            LEFT JOIN planning_orders o ON o.id = a.planning_order_id
            WHERE s.slot_date >= ?
              AND s.slot_date <= ?
            ;
            """,
            (week_start_text, week_end_text),
        ).fetchall()
        touched_order_ids = {
            int(row["planning_order_id"] or 0)
            for row in existing_rows
            if int(row["planning_order_id"] or 0) > 0
            and _normalize_release_status(row["order_status"]) != "erledigt"
        }
        frozen_count = sum(1 for row in existing_rows if _normalize_release_status(row["order_status"]) == "erledigt")
        conn.execute(
            """
            DELETE FROM planning_allocations
            WHERE capacity_slot_id IN (
                SELECT id
                FROM planning_capacity_slots
                WHERE slot_date >= ?
                  AND slot_date <= ?
            )
              AND planning_order_id NOT IN (
                SELECT id
                FROM planning_orders
                WHERE lower(trim(COALESCE(status, ''))) IN ('erledigt', 'done')
              )
            ;
            """,
            (week_start_text, week_end_text),
        )
        remaining_count = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM planning_allocations a
                JOIN planning_capacity_slots s ON s.id = a.capacity_slot_id
                WHERE s.slot_date >= ?
                  AND s.slot_date <= ?
                ;
                """,
                (week_start_text, week_end_text),
            ).fetchone()[0]
            or 0
        )
        if remaining_count:
            active_remaining_count = int(
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM planning_allocations a
                    JOIN planning_capacity_slots s ON s.id = a.capacity_slot_id
                    LEFT JOIN planning_orders o ON o.id = a.planning_order_id
                    WHERE s.slot_date >= ?
                      AND s.slot_date <= ?
                      AND lower(trim(COALESCE(o.status, ''))) NOT IN ('erledigt', 'done')
                    ;
                    """,
                    (week_start_text, week_end_text),
                ).fetchone()[0]
                or 0
            )
            if active_remaining_count:
                raise RuntimeError("Die Woche konnte nicht vollständig geleert werden.")
        conn.execute(
            """
            UPDATE planning_capacity_slots
            SET allocation_mode='auto', updated_at=?
            WHERE slot_date >= ?
              AND slot_date <= ?
            ;
            """,
            (_now_iso(), week_start_text, week_end_text),
        )
        conn.commit()
    finally:
        conn.close()
    _sync_order_schedules_from_allocations_fast(touched_order_ids, reset_release=True, db_path=db_path)
    db_core.bump_data_version()
    deleted_count = max(0, len(existing_rows) - int(remaining_count or 0))
    return {
        "deleted_allocations": deleted_count,
        "touched_orders": len(touched_order_ids),
        "kept_frozen_allocations": int(frozen_count),
    }


def remove_order(
    *,
    order_id: int,
    db_path: str | None = None,
) -> None:
    initialize_planning_module(db_path)
    db_core.db_exec(
        "DELETE FROM open_tasks WHERE planning_order_id=?;",
        (int(order_id),),
        commit=True,
    )
    delete_planning_order(order_id=order_id, db_path=db_path)
    db_core.bump_data_version()


def get_week_board(week_start_iso: str, *, db_path: str | None = None) -> dict[str, Any]:
    initialize_planning_module(db_path)
    week_start = date.fromisoformat(str(week_start_iso))
    week_dates = [(week_start + timedelta(days=offset)).isoformat() for offset in range(7)]
    active_roles = list_capacity_roles(active_only=True, db_path=db_path)
    shift_templates = list_shift_templates(active_only=True, db_path=db_path)
    staffing_rows = list_shift_staffing(db_path=db_path)
    slot_templates = list_slot_templates(active_only=True, db_path=db_path)
    slot_labels = [str(row.get("slot_label") or "") for row in slot_templates] or list(DEFAULT_CAPACITY_SLOTS)
    ensure_capacity_slots_for_dates(week_dates, slot_labels=slot_labels, db_path=db_path)
    date_from = week_dates[0]
    date_to = week_dates[-1]
    capacity_rows = list_capacity_slots_for_range(date_from, date_to, db_path=db_path)
    capacity_changed = _sync_week_capacity_from_staffing(
        week_dates=week_dates,
        slot_templates=slot_templates,
        shift_templates=shift_templates,
        staffing_rows=staffing_rows,
        active_roles=active_roles,
        existing_capacity_rows=capacity_rows,
        db_path=db_path,
    )
    if capacity_changed:
        capacity_rows = list_capacity_slots_for_range(date_from, date_to, db_path=db_path)
    allocation_rows = list_planning_allocations_for_range(date_from, date_to, db_path=db_path)
    orders = list_planning_orders(db_path=db_path)
    places = list_places(active_only=True, db_path=db_path)

    slot_order = {label: index for index, label in enumerate(slot_labels)}
    capacity_rows.sort(
        key=lambda row: (
            str(row.get("slot_date") or ""),
            slot_order.get(str(row.get("slot_label") or ""), 999),
            str(row.get("slot_label") or ""),
        )
    )
    allocation_rows.sort(
        key=lambda row: (
            str(row.get("slot_date") or ""),
            slot_order.get(str(row.get("slot_label") or ""), 999),
            str(row.get("place_code") or ""),
        )
    )

    derived_slots = _build_slot_rows_from_shifts(shift_templates)
    shift_name_by_label = {
        str(row.get("slot_label") or ""): str(row.get("shift_name") or "")
        for row in derived_slots
        if str(row.get("slot_label") or "").strip()
    }
    staffing_map = {
        (
            str(row.get("shift_name") or ""),
            int(row.get("weekday") or 0),
            str(row.get("role_key") or ""),
        ): float(row.get("capacity") or 0.0)
        for row in staffing_rows
    }
    role_capacity_map: dict[tuple[str, str], dict[str, float]] = {}
    for row in capacity_rows:
        slot_date = str(row.get("slot_date") or "")
        slot_label = str(row.get("slot_label") or "")
        weekday = date.fromisoformat(slot_date).weekday()
        shift_name = shift_name_by_label.get(slot_label, "")
        role_values: dict[str, float] = {}
        for role in active_roles:
            role_key = str(role.get("role_key") or "")
            if role_key == "workshop":
                role_values[role_key] = float(row.get("workshop_capacity") or 0.0)
            elif role_key == "service":
                role_values[role_key] = float(row.get("service_capacity") or 0.0)
            elif role_key == "urd":
                role_values[role_key] = float(row.get("urd_capacity") or 0.0)
            else:
                role_values[role_key] = staffing_map.get((shift_name, weekday, role_key), 0.0)
        role_capacity_map[(slot_date, slot_label)] = role_values

    day_summaries: dict[str, dict[str, float]] = {
        day_iso: {"capacity": 0.0, "allocated": 0.0} for day_iso in week_dates
    }
    for row in capacity_rows:
        day_iso = str(row.get("slot_date") or "")
        day_summaries.setdefault(day_iso, {"capacity": 0.0, "allocated": 0.0})
        day_summaries[day_iso]["capacity"] += float(row.get("workshop_capacity") or 0.0)
    for row in allocation_rows:
        day_iso = str(row.get("slot_date") or "")
        day_summaries.setdefault(day_iso, {"capacity": 0.0, "allocated": 0.0})
        day_summaries[day_iso]["allocated"] += float(row.get("allocated_ma") or 0.0)

    order_rows = _enrich_orders_with_allocation_totals(orders, list_planning_order_allocation_totals(db_path=db_path))
    order_allocation_rows = list_planning_allocations_for_order_ids(
        [int(row.get("id") or 0) for row in order_rows],
        db_path=db_path,
    )
    open_orders: list[dict[str, Any]] = []
    completed_orders: list[dict[str, Any]] = []
    for row in order_rows:
        normalized_status = _normalize_release_status(row.get("status"))
        if normalized_status in {"in_erstellung", "erledigt"}:
            continue
        if str(row.get("progress_state") or "") in {"done", "overplanned"}:
            completed_orders.append(row)
        else:
            open_orders.append(row)

    return {
        "week_start": week_dates[0],
        "week_end": week_dates[-1],
        "week_dates": week_dates,
        "slot_labels": list(slot_labels),
        "slot_templates": slot_templates,
        "capacity_roles": active_roles,
        "slot_role_capacities": {
            f"{slot_date}|{slot_label}": values for (slot_date, slot_label), values in role_capacity_map.items()
        },
        "capacity_slots": capacity_rows,
        "allocations": allocation_rows,
        "order_allocations": order_allocation_rows,
        "orders": order_rows,
        "open_orders": open_orders,
        "completed_orders": completed_orders,
        "places": places,
        "day_summaries": day_summaries,
    }
