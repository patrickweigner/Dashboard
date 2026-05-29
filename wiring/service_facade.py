from __future__ import annotations

from datetime import date, datetime
import re
import sqlite3
from typing import Any, Callable

import pandas as pd


def configure(**deps) -> None:
    globals().update(deps)


def _open_tasks_service_module():
    from services import open_tasks_service as service

    service.configure(
        ARCHIVE_NOTIFY_VEHICLE_TOKENS=ARCHIVE_NOTIFY_VEHICLE_TOKENS,
        _DB_WRITE_LOCK=_DB_WRITE_LOCK,
        _clean_ap=_clean_ap,
        _clean_nullable_db_text=_clean_nullable_db_text,
        _coerce_berlin_datetime_series=_coerce_berlin_datetime_series,
        _current_data_version=_current_data_version,
        _extract_last_overdue_reason=_extract_last_overdue_reason,
        _norm_vehicle=_norm_vehicle,
        _planned_deadline_dt=_planned_deadline_dt,
        _remember_recent_done=_remember_recent_done,
        _ui_page_hint=_ui_page_hint,
        as_berlin=as_berlin,
        bump_data_version=bump_data_version,
        db_exec=db_exec,
        get_conn=get_conn,
        notify_archive=notify_archive,
        now_berlin=now_berlin,
    )
    return service


def get_open_tasks_df() -> pd.DataFrame:
    return _open_tasks_service_module().get_open_tasks_df()


def _configuration_service_module():
    from services import configuration_service as service

    service.configure(
        _DB_WRITE_LOCK=_DB_WRITE_LOCK,
        _norm_vehicle=_norm_vehicle,
        bump_data_version=bump_data_version,
        db_exec=db_exec,
        get_conn=get_conn,
        now_berlin=now_berlin,
    )
    return service


def get_supported_series_frist_levels() -> dict[str, list[str]]:
    return _configuration_service_module().get_supported_series_frist_levels()


def list_series() -> list[str]:
    return _configuration_service_module().list_series()


def add_series(name: str) -> str:
    return _configuration_service_module().add_series(name)


def list_frist_levels(baureihe: str) -> list[str]:
    return _configuration_service_module().list_frist_levels(baureihe)


def list_frist_level_configs(baureihe: str) -> list[dict[str, Any]]:
    return _configuration_service_module().list_frist_level_configs(baureihe)


def frist_trigger_options() -> dict[str, str]:
    return dict(_configuration_service_module().FRIST_TRIGGER_OPTIONS)


def add_frist_level(baureihe: str, friststufe: str, trigger_type: str = "") -> str:
    return _configuration_service_module().add_frist_level(baureihe, friststufe, trigger_type)


def update_frist_level_trigger_type(baureihe: str, friststufe: str, trigger_type: str) -> bool:
    return _configuration_service_module().update_frist_level_trigger_type(baureihe, friststufe, trigger_type)


def update_frist_level_active(baureihe: str, friststufe: str, active: bool) -> bool:
    return _configuration_service_module().update_frist_level_active(baureihe, friststufe, active)


def set_all_frist_levels_active(baureihe: str, active: bool) -> int:
    return _configuration_service_module().set_all_frist_levels_active(baureihe, active)


def update_frist_level_config(baureihe: str, old_friststufe: str, new_friststufe: str, trigger_type: str) -> str:
    return _configuration_service_module().update_frist_level_config(
        baureihe,
        old_friststufe,
        new_friststufe,
        trigger_type,
    )


def delete_frist_level(baureihe: str, friststufe: str) -> bool:
    return _configuration_service_module().delete_frist_level(baureihe, friststufe)


def move_frist_level(baureihe: str, friststufe: str, direction: int) -> bool:
    return _configuration_service_module().move_frist_level(baureihe, friststufe, direction)


def list_work_packages(baureihe: str | None = None, friststufe: str | None = None) -> list[dict[str, Any]]:
    return _configuration_service_module().list_work_packages(baureihe, friststufe)


def save_work_package(
    *,
    package_id: int | None = None,
    baureihe: str,
    friststufe: str,
    title: str,
    employee_count: int,
    duration_minutes: float,
) -> int:
    return _configuration_service_module().save_work_package(
        package_id=package_id,
        baureihe=baureihe,
        friststufe=friststufe,
        title=title,
        employee_count=employee_count,
        duration_minutes=duration_minutes,
    )


def delete_work_package(package_id: int) -> bool:
    return _configuration_service_module().delete_work_package(package_id)


def move_work_package(baureihe: str, friststufe: str, package_id: int, direction: int) -> bool:
    return _configuration_service_module().move_work_package(baureihe, friststufe, package_id, direction)


def copy_series_configuration(source_series: str, target_series: str) -> bool:
    return _configuration_service_module().copy_series_configuration(source_series, target_series)


def list_vehicle_series_mappings(baureihe: str | None = None) -> list[dict[str, Any]]:
    return _configuration_service_module().list_vehicle_series_mappings(baureihe)


def save_vehicle_series_mapping(vehicle_number: str, baureihe: str) -> None:
    _configuration_service_module().save_vehicle_series_mapping(vehicle_number, baureihe)


def delete_vehicle_series_mapping(vehicle_number: str) -> bool:
    return _configuration_service_module().delete_vehicle_series_mapping(vehicle_number)


def get_vehicle_series_for_vehicle(vehicle_number: Any) -> str:
    return _configuration_service_module().get_vehicle_series_for_vehicle(vehicle_number)


def get_configured_work_package_titles_for_vehicle_and_frist(vehicle_number: Any, frist_value: Any) -> list[str]:
    return _configuration_service_module().get_configured_work_package_titles_for_vehicle_and_frist(
        vehicle_number,
        frist_value,
    )


def _user_management_service_module():
    from services import user_management_service as service

    return service


def list_users() -> list[dict[str, Any]]:
    return _user_management_service_module().list_users()


def save_user(**kwargs) -> str:
    return _user_management_service_module().save_user(**kwargs)


def get_standard_access() -> dict[str, Any]:
    return _user_management_service_module().get_standard_access()


def save_standard_access(**kwargs) -> str:
    return _user_management_service_module().save_standard_access(**kwargs)


def delete_user(username: str) -> bool:
    return _user_management_service_module().delete_user(username)


def user_permission_options() -> dict[str, str]:
    return _user_management_service_module().permission_options()


def user_role_options() -> dict[str, str]:
    return _user_management_service_module().role_options()


def _archive_service_module():
    from services import archive_service as service

    service.configure(
        _DB_WRITE_LOCK=_DB_WRITE_LOCK,
        _clean_nullable_db_text=_clean_nullable_db_text,
        _clean_nullable_text=_clean_nullable_text,
        _clean_problem_note=_clean_problem_note,
        _coerce_berlin_datetime_series=_coerce_berlin_datetime_series,
        _current_data_version=_current_data_version,
        _find_best_archive_row_for_recent=_find_best_archive_row_for_recent,
        _norm=_norm,
        _norm_vehicle=_norm_vehicle,
        as_berlin=as_berlin,
        bump_data_version=bump_data_version,
        can_delete_recent_done_functions=can_delete_recent_done_functions,
        db_exec=db_exec,
        get_conn=get_conn,
        make_sig=make_sig,
        now_berlin=now_berlin,
    )
    return service


def get_archive_df(
    limit: int | None = 500,
    *,
    date_from: date | datetime | pd.Timestamp | str | None = None,
    date_to: date | datetime | pd.Timestamp | str | None = None,
) -> pd.DataFrame:
    return _archive_service_module().get_archive_df(limit, date_from=date_from, date_to=date_to)


def _norm_status_key(status_raw: Any) -> str:
    return _archive_service_module()._norm_status_key(status_raw)


def df_to_excel_bytes(df: pd.DataFrame, sheet_name: str = "Daten") -> bytes:
    return _archive_service_module().df_to_excel_bytes(df, sheet_name=sheet_name)


def build_kpi_monthly(df_arch: pd.DataFrame) -> pd.DataFrame:
    return _archive_service_module().build_kpi_monthly(df_arch)


def build_kpi_baureihe(df_arch: pd.DataFrame) -> pd.DataFrame:
    return _archive_service_module().build_kpi_baureihe(df_arch)


def _purge_recent_done_archive(now_dt: datetime | None = None) -> None:
    _archive_service_module()._purge_recent_done_archive(now_dt=now_dt)


def _remember_recent_done(
    fahrzeug: Any,
    friststufe: Any,
    zusatzarbeiten: Any,
    done_at: datetime | None = None,
    *,
    archive_id: int | None = None,
    snapshot: dict[str, Any] | None = None,
) -> None:
    _archive_service_module()._remember_recent_done(
        fahrzeug,
        friststufe,
        zusatzarbeiten,
        done_at,
        archive_id=archive_id,
        snapshot=snapshot,
    )


def _get_prio_frist_history_maps() -> tuple[dict[str, str], dict[str, str]]:
    return _archive_service_module()._get_prio_frist_history_maps()


def get_recent_done_df(limit: int = 600) -> pd.DataFrame:
    return _archive_service_module().get_recent_done_df(limit)


def delete_recent_done_entry(entry_id: int) -> bool:
    return _archive_service_module().delete_recent_done_entry(entry_id)


def restore_recent_done_for_planning_order(planning_order_id: int) -> bool:
    return _archive_service_module().restore_recent_done_for_planning_order(int(planning_order_id))


def _workshop_state_service_module():
    from services import workshop_state_service as service

    service.configure(
        AUSSENEINSATZ_OPTIONS=AUSSENEINSATZ_OPTIONS,
        _DB_WRITE_LOCK=_DB_WRITE_LOCK,
        _attach_dialog_tracking=_attach_dialog_tracking,
        _build_ausseneinsatz_payload=_build_ausseneinsatz_payload,
        _close_tracked_dialog=_close_tracked_dialog,
        _open_tracked_dialog=_open_tracked_dialog,
        as_berlin=as_berlin,
        bump_data_version=bump_data_version,
        db_exec=db_exec,
        get_conn=get_conn,
        now_berlin=now_berlin,
        notify_delay=notify_delay,
    )
    return service


def _purge_prio_side_state(now_dt: datetime | None = None) -> None:
    _workshop_state_service_module()._purge_prio_side_state(now_dt=now_dt)


def _load_prio_side_state_map() -> dict[tuple[str, str, str], bool]:
    return _workshop_state_service_module()._load_prio_side_state_map()


def _save_prio_side_state(area: str, vehicle_key: str, row_end_iso: str, checked: bool, expires_at_iso: str) -> None:
    _workshop_state_service_module()._save_prio_side_state(area, vehicle_key, row_end_iso, checked, expires_at_iso)


def get_shopfloorboard_5s_week(iso_year: int, iso_week: int) -> dict[str, str]:
    return _workshop_state_service_module().get_shopfloorboard_5s_week(iso_year, iso_week)


def save_shopfloorboard_5s_week(
    *,
    iso_year: int,
    iso_week: int,
    fruehschicht: str,
    spaetschicht: str,
    nachtschicht: str,
) -> None:
    _workshop_state_service_module().save_shopfloorboard_5s_week(
        iso_year=iso_year,
        iso_week=iso_week,
        fruehschicht=fruehschicht,
        spaetschicht=spaetschicht,
        nachtschicht=nachtschicht,
    )


def get_ausseneinsatz_key(plan_day: date | datetime | str) -> str:
    return _workshop_state_service_module().get_ausseneinsatz_key(plan_day)


def get_ausseneinsatz_label(plan_day: date | datetime | str) -> str:
    return _workshop_state_service_module().get_ausseneinsatz_label(plan_day)


def format_ausseneinsatz_status(plan_day: date | datetime | str) -> str:
    return _workshop_state_service_module().format_ausseneinsatz_status(plan_day)


def save_ausseneinsatz(plan_day: date | datetime | str, assignment_key: str | None) -> None:
    _workshop_state_service_module().save_ausseneinsatz(plan_day, assignment_key)


def open_ausseneinsatz_dialog(plan_day: date | datetime | str, refresh_fn: Callable[[], None] | None = None) -> None:
    _workshop_state_service_module().open_ausseneinsatz_dialog(plan_day, refresh_fn=refresh_fn)


def auto_clear_shopfloorboard_5s_if_due(now_dt: datetime | None = None) -> None:
    _workshop_state_service_module().auto_clear_shopfloorboard_5s_if_due(now_dt=now_dt)


def _ecm4_service_module():
    from services import ecm4_service as service

    service.configure(
        BERLIN=BERLIN,
        _DB_WRITE_LOCK=_DB_WRITE_LOCK,
        _coerce_berlin_datetime_series=_coerce_berlin_datetime_series,
        _current_data_version=_current_data_version,
        _display_vehicle_code=_display_vehicle_code,
        _ensure_ecm4_plan_history_schema=_ensure_ecm4_plan_history_schema,
        as_berlin=as_berlin,
        bump_data_version=bump_data_version,
        db_exec=db_exec,
        get_conn=get_conn,
        now_berlin=now_berlin,
    )
    return service


def replace_ecm4_plan_in_db(plan_df: pd.DataFrame, source_name: str | None = None) -> None:
    _ecm4_service_module().replace_ecm4_plan_in_db(plan_df, source_name=source_name)


def replace_ecm4_plan(plan_df: pd.DataFrame, *, source_name: str | None = None) -> None:
    _ecm4_service_module().replace_ecm4_plan(plan_df, source_name=source_name)


def replace_rws_week_plan_in_db(plan_df: pd.DataFrame | None, source_name: str | None = None) -> None:
    _ecm4_service_module().replace_rws_week_plan_in_db(plan_df, source_name=source_name)


def load_rws_week_plan_df() -> pd.DataFrame:
    return _ecm4_service_module().load_rws_week_plan_df()


def load_ecm4_plan_df(ref_dt: datetime | date | None = None) -> pd.DataFrame:
    return _ecm4_service_module().load_ecm4_plan_df(ref_dt=ref_dt)


def _planning_service_module():
    from services import planning_service as service

    service.configure(
        BERLIN=BERLIN,
        PRIO_MAIN_AREAS=PRIO_MAIN_AREAS,
        RX_VEHICLE=RX_VEHICLE,
        SLOT_DEFS=SLOT_DEFS,
        WEEKDAY_NAMES_DE=WEEKDAY_NAMES_DE,
        _append_unique_inline_text=_append_unique_inline_text,
        _append_unique_multiline_text=_append_unique_multiline_text,
        _clean_nullable_text=_clean_nullable_text,
        _collect_gewerke_slot_events=_collect_gewerke_slot_events,
        _current_data_version=_current_data_version,
        _get_prio_frist_history_maps=_get_prio_frist_history_maps,
        _is_urd_open_row=_is_urd_open_row,
        _normalize_workshop_area=_normalize_workshop_area,
        _norm_vehicle=_norm_vehicle,
        _vehicle_compare_key=_vehicle_compare_key,
        as_berlin=as_berlin,
        get_open_tasks_df=get_open_tasks_df,
        load_ecm4_plan_df=load_ecm4_plan_df,
        load_rws_week_plan_df=load_rws_week_plan_df,
        now_berlin=now_berlin,
    )
    return service


def _shift_day(dt: datetime) -> date:
    return _planning_service_module()._shift_day(dt)


def _build_slots_for_day(day_val: date) -> list[dict[str, Any]]:
    return _planning_service_module()._build_slots_for_day(day_val)


def _shift_pair_group(label: str) -> str | None:
    return _planning_service_module()._shift_pair_group(label)


def _slot_end_for_start(start_dt: datetime) -> datetime:
    return _planning_service_module()._slot_end_for_start(start_dt)


def _next_slot_start_for_start(start_dt: datetime) -> datetime:
    return _planning_service_module()._next_slot_start_for_start(start_dt)


def _slot_label_for_start(start_dt: datetime | None) -> str | None:
    return _planning_service_module()._slot_label_for_start(start_dt)


def _clean_plan_text(value: Any) -> str:
    return _planning_service_module()._clean_plan_text(value)


def _display_vehicle_code(value: Any) -> str:
    return _planning_service_module()._display_vehicle_code(value)


def _slot_secondary_text(
    frist_value: Any,
    *,
    has_service: bool = False,
    suppress_urd: bool = False,
    with_prefix: bool = False,
) -> str:
    return _planning_service_module()._slot_secondary_text(
        frist_value,
        has_service=has_service,
        suppress_urd=suppress_urd,
        with_prefix=with_prefix,
    )


def _vehicle_keys_from_note_text(note_text: Any) -> set[str]:
    return _planning_service_module()._vehicle_keys_from_note_text(note_text)


def _note_segments_by_vehicle_key(note_text: Any) -> dict[str, str]:
    return _planning_service_module()._note_segments_by_vehicle_key(note_text)


def _note_text_for_vehicle(note_text: Any, vehicle_raw: Any) -> str:
    return _planning_service_module()._note_text_for_vehicle(note_text, vehicle_raw)


def _build_current_prio_frist_maps(df_open: pd.DataFrame | None = None) -> tuple[dict[str, str], dict[str, str]]:
    return _planning_service_module()._build_current_prio_frist_maps(df_open)


def _resolve_prio_frist(
    area_code: str,
    vehicle: Any,
    current_maps: tuple[dict[str, str], dict[str, str]],
    hist_maps: tuple[dict[str, str], dict[str, str]],
) -> str:
    return _planning_service_module()._resolve_prio_frist(area_code, vehicle, current_maps, hist_maps)


def _weekday_name_de(day_val: date) -> str:
    return _planning_service_module()._weekday_name_de(day_val)


def _build_open_task_vehicle_lookup() -> dict[str, list[dict[str, Any]]]:
    return _planning_service_module()._build_open_task_vehicle_lookup()


def _frist_for_vehicle_slot(
    open_lookup: dict[str, list[dict[str, Any]]],
    vehicle_raw: Any,
    slot_start: datetime,
    *,
    area_code: str = "",
) -> str:
    return _planning_service_module()._frist_for_vehicle_slot(
        open_lookup,
        vehicle_raw,
        slot_start,
        area_code=area_code,
    )


def _build_weekly_main_area_plan(week_start: date) -> dict[str, list[dict[str, Any]]]:
    return _planning_service_module()._build_weekly_main_area_plan(week_start)


def _build_weekly_side_area_plan(week_start: date) -> dict[str, list[dict[str, Any]]]:
    return _planning_service_module()._build_weekly_side_area_plan(week_start)


def _current_slot_vehicle_keys_from_ecm4() -> set[str]:
    return _planning_service_module()._current_slot_vehicle_keys_from_ecm4()


def _collect_ecm4_service_assignments(plan_df: pd.DataFrame) -> list[dict[str, Any]]:
    return _planning_service_module()._collect_ecm4_service_assignments(plan_df)


def _extract_last_overdue_reason(note_text: str) -> str:
    if not note_text:
        return ""
    out = ""
    for raw in str(note_text).splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^\[\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}\]\s*(.*)$", line)
        if m:
            line = m.group(1).strip()
        low = line.replace("\u00c3\u00a4", "ä").casefold()
        if low.startswith("verspaetungsgrund:") or low.startswith("verspätungsgrund:"):
            out = line.split(":", 1)[1].strip()
    return out


def add_problem(open_id: int, note: str) -> None:
    row = db_exec("SELECT last_problem_note FROM open_tasks WHERE id=?;", (int(open_id),), fetchone=True)
    old = str(row[0] if row else "").strip()
    ts = now_berlin().strftime("%d.%m.%Y %H:%M")
    line = f"[{ts}] {note.strip()}"
    new_note = _append_text(old, line)
    db_exec(
        "UPDATE open_tasks SET last_problem_note=?, last_problem_at=? WHERE id=?;",
        (new_note, now_berlin().isoformat(timespec="seconds"), int(open_id)),
        commit=True,
    )


def pin_problem(open_id: int, note: str) -> None:
    add_problem(int(open_id), str(note or "").strip())


def _notification_service_module():
    from services import notification_service as service

    service.configure(
        AUSSENEINSATZ_OPTIONS=AUSSENEINSATZ_OPTIONS,
        _clean_ap=_clean_ap,
        _collect_gewerke_slot_events=_collect_gewerke_slot_events,
        _norm_vehicle=_norm_vehicle,
        _notify_flow_url=_notify_flow_url,
        as_berlin=as_berlin,
        auto_clear_shopfloorboard_5s_if_due=auto_clear_shopfloorboard_5s_if_due,
        db_exec=db_exec,
        get_open_tasks_df=get_open_tasks_df,
        load_ecm4_plan_df=load_ecm4_plan_df,
        now_berlin=now_berlin,
    )
    return service


def notify_delay(payload: dict[str, Any]) -> tuple[bool, str]:
    return _notification_service_module().notify_delay(payload)


def notify_archive(payload: dict[str, Any]) -> tuple[bool, str]:
    return _notification_service_module().notify_archive(payload)


def check_and_send_lwu_reminders(*, window_minutes: int = 360) -> int:
    return _notification_service_module().check_and_send_lwu_reminders(window_minutes=window_minutes)


def trigger_lwu_test_next_24h(*, hours_ahead: int = 24) -> tuple[int, int]:
    return _notification_service_module().trigger_lwu_test_next_24h(hours_ahead=hours_ahead)


def start_lwu_reminder_worker() -> None:
    _notification_service_module().start_lwu_reminder_worker()


def _ui_page_hint() -> str:
    return _notification_service_module()._ui_page_hint()


def _build_delay_payload(
    open_id: int,
    reason: str,
    *,
    options: list[str] | None = None,
    free_text: str | None = None,
    source: str = "verzoegerung_dialog",
) -> dict[str, Any]:
    return _notification_service_module()._build_delay_payload(
        open_id,
        reason,
        options=options,
        free_text=free_text,
        source=source,
    )


def _build_ausseneinsatz_payload(
    *,
    plan_day: date,
    selection_key: str,
    source: str = "ausseneinsatz_dialog",
) -> dict[str, Any]:
    return _notification_service_module()._build_ausseneinsatz_payload(
        plan_day=plan_day,
        selection_key=selection_key,
        source=source,
    )


def _completion_status_for_deadline(actual_value: Any, deadline_value: Any) -> str | None:
    return _open_tasks_service_module()._completion_status_for_deadline(actual_value, deadline_value)


def _send_archive_notification(
    *,
    open_id: int,
    fahrzeug: Any,
    arbeitsplatz: Any,
    friststufe: Any,
    archived_at: datetime,
) -> tuple[bool, str]:
    return _open_tasks_service_module()._send_archive_notification(
        open_id=open_id,
        fahrzeug=fahrzeug,
        arbeitsplatz=arbeitsplatz,
        friststufe=friststufe,
        archived_at=archived_at,
    )


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
    return _open_tasks_service_module()._insert_archive_entry(
        fahrzeug=fahrzeug,
        friststufe=friststufe,
        anfang=anfang,
        fertig=fertig,
        last_problem_note=last_problem_note,
        completed_at=completed_at,
        status=status,
        status_ecm3=status_ecm3,
        initial_fertig=initial_fertig,
    )


def move_to_archive_and_delete(open_id: int) -> tuple[bool, str]:
    return _open_tasks_service_module().move_to_archive_and_delete(int(open_id))


def archive_task(open_id: int) -> tuple[bool, str]:
    return _open_tasks_service_module().archive_task(int(open_id))


def _archive_notify_type(ok: bool, msg: str) -> str:
    return _open_tasks_service_module()._archive_notify_type(ok, msg)


def _open_tasks_management_service_module():
    from services import open_tasks_management_service as service

    service.configure(
        BERLIN=BERLIN,
        WORKSHOP_AREAS=WORKSHOP_AREAS,
        _DB_WRITE_LOCK=_DB_WRITE_LOCK,
        _append_text=_append_text,
        _clean_ap=_clean_ap,
        _clean_nullable_db_text=_clean_nullable_db_text,
        _clean_nullable_text=_clean_nullable_text,
        _completion_status_for_deadline=_completion_status_for_deadline,
        _extract_last_overdue_reason=_extract_last_overdue_reason,
        _insert_archive_entry=_insert_archive_entry,
        _is_wash_zus_item=_is_wash_zus_item,
        _normalize_workshop_area=_normalize_workshop_area,
        _norm_vehicle=_norm_vehicle,
        _parse_zusatz_items=_parse_zusatz_items,
        _planned_deadline_dt=_planned_deadline_dt,
        _purge_recent_done_archive=_purge_recent_done_archive,
        _remember_recent_done=_remember_recent_done,
        _send_archive_notification=_send_archive_notification,
        _vehicle_compare_key=_vehicle_compare_key,
        as_berlin=as_berlin,
        bump_data_version=bump_data_version,
        db_exec=db_exec,
        dedupe_open_tasks_by_sig=dedupe_open_tasks_by_sig,
        get_conn=get_conn,
        make_sig=make_sig,
        now_berlin=now_berlin,
    )
    return service


def _get_existing_open_by_vehicle(fzg: str):
    return _open_tasks_management_service_module()._get_existing_open_by_vehicle(fzg)


def create_or_update_open_task_manual(
    fzg: str,
    *,
    end_mode: str,
    ende_dt: datetime | None,
    zusatz: str,
) -> None:
    _open_tasks_management_service_module().create_or_update_open_task_manual(
        fzg,
        end_mode=end_mode,
        ende_dt=ende_dt,
        zusatz=zusatz,
    )


def find_other_assigned_rows_for_same_vehicle(open_id: int, target_area: str | None = None) -> list[dict[str, Any]]:
    return _open_tasks_management_service_module().find_other_assigned_rows_for_same_vehicle(
        open_id,
        target_area=target_area,
    )


def assign_vehicle_to_area_with_shift(
    open_id: int,
    area_code: str,
    source_open_ids: list[int] | None = None,
) -> tuple[bool, str]:
    return _open_tasks_management_service_module().assign_vehicle_to_area_with_shift(
        open_id,
        area_code,
        source_open_ids=source_open_ids,
    )


def assign_area(open_id: int, area: str) -> tuple[bool, str]:
    return _open_tasks_management_service_module().assign_area(open_id, area)


def _canon_dt_for_import_compare(val: Any) -> str:
    return _open_tasks_management_service_module()._canon_dt_for_import_compare(val)


def _canon_zus_for_import_compare(val: Any) -> tuple[str, ...]:
    return _open_tasks_management_service_module()._canon_zus_for_import_compare(val)


def _db_schema_module():
    from core import db_schema as module

    module.configure(
        BERLIN=BERLIN,
        as_berlin=as_berlin,
        _clean_nullable_text=_clean_nullable_text,
        _clean_nullable_db_text=_clean_nullable_db_text,
    )
    return module


def _find_best_archive_row_for_recent(
    fahrzeug: Any,
    friststufe: Any,
    archived_at: Any,
) -> sqlite3.Row | None:
    return _db_schema_module()._find_best_archive_row_for_recent(fahrzeug, friststufe, archived_at)


def dedupe_open_tasks_by_sig() -> None:
    _db_schema_module().dedupe_open_tasks_by_sig()


def _ensure_ecm4_plan_history_schema(conn: sqlite3.Connection | None = None) -> None:
    _db_schema_module()._ensure_ecm4_plan_history_schema(conn)


def init_db() -> None:
    _db_schema_module().init_db()


def _normalize_db_datetime_placeholders() -> None:
    _db_schema_module()._normalize_db_datetime_placeholders()


def reset_all() -> None:
    _db_schema_module().reset_all()


def build_import_diff(df_norm: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    return _open_tasks_management_service_module().build_import_diff(df_norm)


def find_missing_open_tasks_for_import(df_norm: pd.DataFrame) -> list[dict[str, Any]]:
    return _open_tasks_management_service_module().find_missing_open_tasks_for_import(df_norm)


def clear_pending_missing_open_state(state: dict[str, Any] | None = None) -> None:
    _open_tasks_management_service_module().clear_pending_missing_open_state(state)


def collect_missing_open_decisions(missing_controls: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    return _open_tasks_management_service_module().collect_missing_open_decisions(missing_controls)


def apply_missing_open_decisions(decisions: list[dict[str, Any]]) -> tuple[int, int, int]:
    return _open_tasks_management_service_module().apply_missing_open_decisions(decisions)


def add_open_tasks_with_progress(df: pd.DataFrame) -> tuple[int, int, int]:
    return _open_tasks_management_service_module().add_open_tasks_with_progress(df)


def _upload_parser_service_module():
    from services import upload_parser_service as service

    service.configure(
        _append_text=_append_text,
        _clean_ap=_clean_ap,
        _clean_plan_text=_clean_plan_text,
        _norm=_norm,
        _norm_vehicle=_norm_vehicle,
        _parse_zusatz_items=_parse_zusatz_items,
    )
    return service


def parse_excel_to_df_bytes(blob: bytes) -> pd.DataFrame:
    return _upload_parser_service_module().parse_excel_to_df_bytes(blob)


def parse_rws_week_plan_from_excel(blob: bytes) -> pd.DataFrame:
    return _upload_parser_service_module().parse_rws_week_plan_from_excel(blob)
