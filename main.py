from __future__ import annotations

from datetime import time
import re
from typing import Any, Callable
from zoneinfo import ZoneInfo

import pandas as pd
from nicegui import ui

from core import db as _core_db
from core import ui_runtime as _ui_runtime
from core.auth import (
    _enforce_admin_uncheck_rule,
    _has_login_passwords,
    _login_success_text,
    _logout_admin,
    _resolve_login_role,
    _set_admin,
    can_delete_recent_done_functions,
    can_edit_page,
    can_use_delete_functions,
    can_view_page,
    is_admin,
    is_configuration_user,
    is_full_admin,
)
from core.config import (
    APP_BINDING_REFRESH_INTERVAL_SECONDS,
    APP_DISCONNECT_RELOAD_SECONDS,
    APP_HOST,
    APP_PORT,
    APP_PORT_RAW,
    APP_RECONNECT_TIMEOUT_SECONDS,
    APP_STORAGE_SECRET,
    BASE_DIR,
    BROWSER_HTML_ZOOM,
    DB_PATH,
    NATIVE_HTML_ZOOM,
    NATIVE_MODE,
    PRIORISIERUNG_REFRESH_SECONDS,
    SHOW_DB_PATH_IN_NAV,
    WERKSTATTHALLE_REFRESH_SECONDS,
    _notify_flow_url,
)


BERLIN = ZoneInfo("Europe/Berlin")
WORKSHOP_AREAS = ["4A", "4B", "5A", "5B", "URD"]
WEEKDAY_NAMES_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
RX_VEHICLE = re.compile(r"\b(?:(ET|VT)\s*)?(\d{3,5}\.\d{1,3})\b", re.I)
FRIST_CHECK_ITEMS = [
    "Sichtprüfung",
    "Calipri",
    "Bremse",
    "Außentüren",
    "Schiebetritte",
    "Innenraum",
    "Dach",
    "Außenbereich",
]
PROBLEM_OPTIONS = [
    "Personalmangel",
    "Außeneinsatz",
    "Fehlende Berechtigung zur vollständigen Abarbeitung der Frist",
    "Zusätzliche Störungen am Fahrzeug",
]
WASH_ZUS_LABEL = "Fahrzeugwäsche"
RX_WASH_TOKEN = re.compile(r"\bfahrzeugw(?:ae|a)sche\b", re.I)
PRIO_MAIN_AREAS = ["4A", "4B", "5A", "5B"]
PRIO_SIDE_AREAS = ["ARA", "URD", "SERVICE"]
PRIO_AREAS = PRIO_MAIN_AREAS + PRIO_SIDE_AREAS
AREA_DISPLAY_NAMES = {"SERVICE": "Gewerke"}
SLOT_DEFS = [
    (time(2, 0), time(6, 0), "2:00 - 6:00", "same"),
    (time(6, 0), time(10, 0), "6:00 - 10:00", "same"),
    (time(10, 0), time(14, 18), "10:00 - 14:18", "same"),
    (time(14, 0), time(18, 0), "14:00 - 18:00", "same"),
    (time(18, 0), time(22, 18), "18:00 - 22:18", "same"),
    (time(21, 42), time(2, 0), "21:42 - 2:00", "next"),
]
TIME_BG = {
    "2:00 - 6:00": ("#6fa8dc", "#000000"),
    "6:00 - 10:00": ("#93c47d", "#000000"),
    "10:00 - 14:18": ("#93c47d", "#000000"),
    "14:00 - 18:00": ("#ffd966", "#000000"),
    "18:00 - 22:18": ("#ffd966", "#000000"),
    "21:42 - 2:00": ("#6fa8dc", "#000000"),
}
SHOPFLOOR_WEEK_TASKS = [
    "Rundumblick während der Arbeit auf Ordnung und Sauberkeit in/um die Werkstatthalle",
    "Bei Verstößen direktes Gespräch mit dem Mitarbeiter suchen",
    "Beim Schichteinstieg Feedback in die Gruppe (positiv und negativ)",
]
OPEN_ZUS_BELOW_BADGE_GAP_PX = 10.0
OPEN_FRIST_BELOW_BADGE_GAP_PX = 10.0
OPEN_ITEM_GAP_PX = 10.0
OPEN_ITEM_LINE_HEIGHT = 1.08
OPEN_ITEM_FONT_SIZE_PX = 18
OPEN_ITEM_FONT_WEIGHT = 700
ARCHIVE_NOTIFY_VEHICLE_TOKENS = ("3462", "4746", "4748")
BTN_BG = "#111827"
BTN_BG_HOVER = "#0b1220"
BTN_FG = "#f3f4f6"
BTN_BORDER = "rgba(255,255,255,.18)"
CURRENT_SLOT_VEHICLE_COLOR = "#faad14"
AUSSENEINSATZ_OPTIONS = {
    "facharbeiter_2": "2 Facharbeiter",
    "service_facharbeiter": "1 Facharbeiter und 1 Servicemitarbeiter",
    "facharbeiter_helfer": "1 Facharbeiter und 1 Produktionshelfer",
    "service_helfer": "1 Servicemitarbeiter und 1 Produktionshelfer",
}

try:
    from business_rules import frist_items_for_vehicle_and_frist as _fr_items_for_vehicle_and_frist
except Exception:
    _fr_items_for_vehicle_and_frist = None

try:
    from ecm4_parser import parse_ecm4_plan_from_excel as _parse_ecm4_plan_from_excel
except Exception:
    _parse_ecm4_plan_from_excel = None

try:
    from app.features.planning.service import initialize_planning_module as _initialize_planning_module
except Exception:
    _initialize_planning_module = None

try:
    from app.features.planning.page import register_planning_pages as _register_planning_pages
except Exception:
    _register_planning_pages = None

_core_db.configure(db_path=DB_PATH)
_DB_WRITE_LOCK = _core_db.DB_WRITE_LOCK
bump_data_version = _core_db.bump_data_version
_current_data_version = _core_db._current_data_version
get_conn = _core_db.get_conn
db_exec = _core_db.db_exec
column_exists = _core_db.column_exists
ensure_column = _core_db.ensure_column

_ui_runtime._patch_ui_umlauts()
_attach_dialog_tracking = _ui_runtime._attach_dialog_tracking
_close_tracked_dialog = _ui_runtime._close_tracked_dialog
_has_open_dialog = _ui_runtime._has_open_dialog
_open_tracked_dialog = _ui_runtime._open_tracked_dialog
_refresh_when_no_dialog = _ui_runtime._refresh_when_no_dialog
ensure_problem_state = _ui_runtime.ensure_problem_state
ensure_overdue_state = _ui_runtime.ensure_overdue_state


def _clean_problem_note_proxy(note_text: Any) -> str:
    return _clean_problem_note(note_text)


def _core_facade_module():
    from wiring import core_facade as module

    module.configure(
        AREA_DISPLAY_NAMES=AREA_DISPLAY_NAMES,
        BERLIN=BERLIN,
        RX_VEHICLE=RX_VEHICLE,
        RX_WASH_TOKEN=RX_WASH_TOKEN,
        WORKSHOP_AREAS=WORKSHOP_AREAS,
        _clean_problem_note=_clean_problem_note_proxy,
    )
    return module


_core_facade = _core_facade_module()
make_sig = _core_facade.make_sig
now_berlin = _core_facade.now_berlin
_is_wash_zus_item = _core_facade._is_wash_zus_item
as_berlin = _core_facade.as_berlin
_coerce_berlin_datetime_series = _core_facade._coerce_berlin_datetime_series
_clean_nullable_text = _core_facade._clean_nullable_text
_clean_nullable_db_text = _core_facade._clean_nullable_db_text
_planned_deadline_text = _core_facade._planned_deadline_text
_planned_deadline_dt = _core_facade._planned_deadline_dt
fmt_dt = _core_facade.fmt_dt
fmt_duration = _core_facade.fmt_duration
_norm = _core_facade._norm
_norm_vehicle = _core_facade._norm_vehicle
_clean_ap = _core_facade._clean_ap
_append_text = _core_facade._append_text
_append_unique_inline_text = _core_facade._append_unique_inline_text
_append_unique_multiline_text = _core_facade._append_unique_multiline_text
_display_area_name = _core_facade._display_area_name
load_ecm4_planung_xlsx = _core_facade.load_ecm4_planung_xlsx


def _build_slots_for_day_proxy(day_val):
    return _build_slots_for_day(day_val)


def _display_vehicle_code_proxy(value):
    return _display_vehicle_code(value)


def _shift_day_proxy(dt):
    return _shift_day(dt)


def _slot_end_for_start_proxy(start_dt):
    return _slot_end_for_start(start_dt)


def _configured_work_package_titles_proxy(fahrzeug, friststufe):
    service = globals().get("_service_facade")
    if service is None:
        return []
    return service.get_configured_work_package_titles_for_vehicle_and_frist(fahrzeug, friststufe)


def _task_rules_facade_module():
    from wiring import task_rules_facade as module

    module.configure(
        BERLIN=BERLIN,
        FRIST_CHECK_ITEMS=FRIST_CHECK_ITEMS,
        _fr_items_for_vehicle_and_frist=_fr_items_for_vehicle_and_frist,
        _configured_work_package_titles_for_vehicle_and_frist=_configured_work_package_titles_proxy,
        _build_slots_for_day=_build_slots_for_day_proxy,
        _display_vehicle_code=_display_vehicle_code_proxy,
        _norm=_norm,
        _norm_vehicle=_norm_vehicle,
        _shift_day=_shift_day_proxy,
        _slot_end_for_start=_slot_end_for_start_proxy,
        as_berlin=as_berlin,
    )
    return module


_task_rules_facade = _task_rules_facade_module()
_short_gewerk_label = _task_rules_facade._short_gewerk_label
_parse_gewerke_entries = _task_rules_facade._parse_gewerke_entries
_slot_start_for_timestamp = _task_rules_facade._slot_start_for_timestamp
_collect_gewerke_slot_events = _task_rules_facade._collect_gewerke_slot_events
_clean_problem_note = _task_rules_facade._clean_problem_note
_vehicle_compare_key = _task_rules_facade._vehicle_compare_key
_is_urd_like = _task_rules_facade._is_urd_like
_is_urd_open_row = _task_rules_facade._is_urd_open_row
_parse_zusatz_items = _task_rules_facade._parse_zusatz_items
_canon_zus_item_key = _task_rules_facade._canon_zus_item_key
_decode_check_string = _task_rules_facade._decode_check_string
_encode_check_list = _task_rules_facade._encode_check_list
_frist_items_for_row = _task_rules_facade._frist_items_for_row
_fold_match_text = _task_rules_facade._fold_match_text
_frist_has_non_hu_component = _task_rules_facade._frist_has_non_hu_component
_is_frist_check_applicable = _task_rules_facade._is_frist_check_applicable
_requires_overdue_reason_for_frist = _task_rules_facade._requires_overdue_reason_for_frist
_calc_zus_progress = _task_rules_facade._calc_zus_progress
_calc_frist_progress = _task_rules_facade._calc_frist_progress
_row_allows_area = _task_rules_facade._row_allows_area
_normalize_workshop_area = _task_rules_facade._normalize_workshop_area
_zus_added_only = _task_rules_facade._zus_added_only


def _service_facade_module():
    from wiring import service_facade as module

    module.configure(
        ARCHIVE_NOTIFY_VEHICLE_TOKENS=ARCHIVE_NOTIFY_VEHICLE_TOKENS,
        AUSSENEINSATZ_OPTIONS=AUSSENEINSATZ_OPTIONS,
        BERLIN=BERLIN,
        PRIO_MAIN_AREAS=PRIO_MAIN_AREAS,
        RX_VEHICLE=RX_VEHICLE,
        SLOT_DEFS=SLOT_DEFS,
        WEEKDAY_NAMES_DE=WEEKDAY_NAMES_DE,
        WORKSHOP_AREAS=WORKSHOP_AREAS,
        _DB_WRITE_LOCK=_DB_WRITE_LOCK,
        _append_text=_append_text,
        _append_unique_inline_text=_append_unique_inline_text,
        _append_unique_multiline_text=_append_unique_multiline_text,
        _attach_dialog_tracking=_attach_dialog_tracking,
        _clean_ap=_clean_ap,
        _clean_nullable_db_text=_clean_nullable_db_text,
        _clean_nullable_text=_clean_nullable_text,
        _clean_problem_note=_clean_problem_note,
        _close_tracked_dialog=_close_tracked_dialog,
        _coerce_berlin_datetime_series=_coerce_berlin_datetime_series,
        _collect_gewerke_slot_events=_collect_gewerke_slot_events,
        _current_data_version=_current_data_version,
        _is_urd_open_row=_is_urd_open_row,
        _is_wash_zus_item=_is_wash_zus_item,
        _norm=_norm,
        _norm_vehicle=_norm_vehicle,
        _normalize_workshop_area=_normalize_workshop_area,
        _notify_flow_url=_notify_flow_url,
        _open_tracked_dialog=_open_tracked_dialog,
        _parse_zusatz_items=_parse_zusatz_items,
        _planned_deadline_dt=_planned_deadline_dt,
        _vehicle_compare_key=_vehicle_compare_key,
        as_berlin=as_berlin,
        bump_data_version=bump_data_version,
        can_delete_recent_done_functions=can_delete_recent_done_functions,
        db_exec=db_exec,
        get_conn=get_conn,
        make_sig=make_sig,
        now_berlin=now_berlin,
    )
    return module


_service_facade = _service_facade_module()
get_open_tasks_df = _service_facade.get_open_tasks_df
get_supported_series_frist_levels = _service_facade.get_supported_series_frist_levels
list_series = _service_facade.list_series
add_series = _service_facade.add_series
list_frist_levels = _service_facade.list_frist_levels
list_frist_level_configs = _service_facade.list_frist_level_configs
frist_trigger_options = _service_facade.frist_trigger_options
add_frist_level = _service_facade.add_frist_level
update_frist_level_trigger_type = _service_facade.update_frist_level_trigger_type
update_frist_level_active = _service_facade.update_frist_level_active
set_all_frist_levels_active = _service_facade.set_all_frist_levels_active
update_frist_level_config = _service_facade.update_frist_level_config
delete_frist_level = _service_facade.delete_frist_level
move_frist_level = _service_facade.move_frist_level
list_work_packages = _service_facade.list_work_packages
save_work_package = _service_facade.save_work_package
delete_work_package = _service_facade.delete_work_package
move_work_package = _service_facade.move_work_package
list_vehicle_series_mappings = _service_facade.list_vehicle_series_mappings
save_vehicle_series_mapping = _service_facade.save_vehicle_series_mapping
delete_vehicle_series_mapping = _service_facade.delete_vehicle_series_mapping
get_vehicle_series_for_vehicle = _service_facade.get_vehicle_series_for_vehicle
get_configured_work_package_titles_for_vehicle_and_frist = (
    _service_facade.get_configured_work_package_titles_for_vehicle_and_frist
)
list_users = _service_facade.list_users
save_user = _service_facade.save_user
get_standard_access = _service_facade.get_standard_access
save_standard_access = _service_facade.save_standard_access
delete_user = _service_facade.delete_user
user_permission_options = _service_facade.user_permission_options
user_role_options = _service_facade.user_role_options
get_archive_df = _service_facade.get_archive_df
_norm_status_key = _service_facade._norm_status_key
df_to_excel_bytes = _service_facade.df_to_excel_bytes
build_kpi_monthly = _service_facade.build_kpi_monthly
build_kpi_baureihe = _service_facade.build_kpi_baureihe
_purge_recent_done_archive = _service_facade._purge_recent_done_archive
_remember_recent_done = _service_facade._remember_recent_done
_get_prio_frist_history_maps = _service_facade._get_prio_frist_history_maps
get_recent_done_df = _service_facade.get_recent_done_df
delete_recent_done_entry = _service_facade.delete_recent_done_entry
_purge_prio_side_state = _service_facade._purge_prio_side_state
_load_prio_side_state_map = _service_facade._load_prio_side_state_map
_save_prio_side_state = _service_facade._save_prio_side_state
get_shopfloorboard_5s_week = _service_facade.get_shopfloorboard_5s_week
save_shopfloorboard_5s_week = _service_facade.save_shopfloorboard_5s_week
get_ausseneinsatz_key = _service_facade.get_ausseneinsatz_key
get_ausseneinsatz_label = _service_facade.get_ausseneinsatz_label
format_ausseneinsatz_status = _service_facade.format_ausseneinsatz_status
save_ausseneinsatz = _service_facade.save_ausseneinsatz
open_ausseneinsatz_dialog = _service_facade.open_ausseneinsatz_dialog
auto_clear_shopfloorboard_5s_if_due = _service_facade.auto_clear_shopfloorboard_5s_if_due
replace_ecm4_plan_in_db = _service_facade.replace_ecm4_plan_in_db
replace_ecm4_plan = _service_facade.replace_ecm4_plan
replace_rws_week_plan_in_db = _service_facade.replace_rws_week_plan_in_db
load_rws_week_plan_df = _service_facade.load_rws_week_plan_df
load_ecm4_plan_df = _service_facade.load_ecm4_plan_df
_shift_day = _service_facade._shift_day
_build_slots_for_day = _service_facade._build_slots_for_day
_shift_pair_group = _service_facade._shift_pair_group
_slot_end_for_start = _service_facade._slot_end_for_start
_next_slot_start_for_start = _service_facade._next_slot_start_for_start
_slot_label_for_start = _service_facade._slot_label_for_start
_clean_plan_text = _service_facade._clean_plan_text
_display_vehicle_code = _service_facade._display_vehicle_code
_slot_secondary_text = _service_facade._slot_secondary_text
_vehicle_keys_from_note_text = _service_facade._vehicle_keys_from_note_text
_note_segments_by_vehicle_key = _service_facade._note_segments_by_vehicle_key
_note_text_for_vehicle = _service_facade._note_text_for_vehicle
_build_current_prio_frist_maps = _service_facade._build_current_prio_frist_maps
_resolve_prio_frist = _service_facade._resolve_prio_frist
_weekday_name_de = _service_facade._weekday_name_de
_build_open_task_vehicle_lookup = _service_facade._build_open_task_vehicle_lookup
_frist_for_vehicle_slot = _service_facade._frist_for_vehicle_slot
_build_weekly_main_area_plan = _service_facade._build_weekly_main_area_plan
_build_weekly_side_area_plan = _service_facade._build_weekly_side_area_plan
_current_slot_vehicle_keys_from_ecm4 = _service_facade._current_slot_vehicle_keys_from_ecm4
_collect_ecm4_service_assignments = _service_facade._collect_ecm4_service_assignments
_extract_last_overdue_reason = _service_facade._extract_last_overdue_reason
add_problem = _service_facade.add_problem
pin_problem = _service_facade.pin_problem
notify_delay = _service_facade.notify_delay
notify_archive = _service_facade.notify_archive
check_and_send_lwu_reminders = _service_facade.check_and_send_lwu_reminders
trigger_lwu_test_next_24h = _service_facade.trigger_lwu_test_next_24h
start_lwu_reminder_worker = _service_facade.start_lwu_reminder_worker
_ui_page_hint = _service_facade._ui_page_hint
_build_delay_payload = _service_facade._build_delay_payload
_build_ausseneinsatz_payload = _service_facade._build_ausseneinsatz_payload
_completion_status_for_deadline = _service_facade._completion_status_for_deadline
_send_archive_notification = _service_facade._send_archive_notification
_insert_archive_entry = _service_facade._insert_archive_entry
move_to_archive_and_delete = _service_facade.move_to_archive_and_delete
archive_task = _service_facade.archive_task
_archive_notify_type = _service_facade._archive_notify_type
_get_existing_open_by_vehicle = _service_facade._get_existing_open_by_vehicle
create_or_update_open_task_manual = _service_facade.create_or_update_open_task_manual
find_other_assigned_rows_for_same_vehicle = _service_facade.find_other_assigned_rows_for_same_vehicle
assign_vehicle_to_area_with_shift = _service_facade.assign_vehicle_to_area_with_shift
assign_area = _service_facade.assign_area
_canon_dt_for_import_compare = _service_facade._canon_dt_for_import_compare
_canon_zus_for_import_compare = _service_facade._canon_zus_for_import_compare
_find_best_archive_row_for_recent = _service_facade._find_best_archive_row_for_recent
dedupe_open_tasks_by_sig = _service_facade.dedupe_open_tasks_by_sig
_ensure_ecm4_plan_history_schema = _service_facade._ensure_ecm4_plan_history_schema
init_db = _service_facade.init_db
_normalize_db_datetime_placeholders = _service_facade._normalize_db_datetime_placeholders
reset_all = _service_facade.reset_all
build_import_diff = _service_facade.build_import_diff
find_missing_open_tasks_for_import = _service_facade.find_missing_open_tasks_for_import
clear_pending_missing_open_state = _service_facade.clear_pending_missing_open_state
collect_missing_open_decisions = _service_facade.collect_missing_open_decisions
apply_missing_open_decisions = _service_facade.apply_missing_open_decisions
add_open_tasks_with_progress = _service_facade.add_open_tasks_with_progress
parse_excel_to_df_bytes = _service_facade.parse_excel_to_df_bytes
parse_rws_week_plan_from_excel = _service_facade.parse_rws_week_plan_from_excel


status_for_row = _core_facade.status_for_row
status_palette = _core_facade.status_palette
_badge_style = _core_facade._badge_style
render_badge_stack = _core_facade.render_badge_stack
render_pill_label = _core_facade.render_pill_label
render_time_badge = _core_facade.render_time_badge
badge_html = _core_facade.badge_html
effective_area = _core_facade.effective_area
display_workplace = _core_facade.display_workplace
format_problem_lines = _core_facade.format_problem_lines
inject_due24_watcher = _core_facade.inject_due24_watcher
render_countdown_badge = _core_facade.render_countdown_badge


def _ui_actions_module():
    from wiring import ui_actions as module

    module.configure(
        BERLIN=BERLIN,
        BTN_BG=BTN_BG,
        DB_PATH=DB_PATH,
        OPEN_FRIST_BELOW_BADGE_GAP_PX=OPEN_FRIST_BELOW_BADGE_GAP_PX,
        OPEN_ZUS_BELOW_BADGE_GAP_PX=OPEN_ZUS_BELOW_BADGE_GAP_PX,
        PROBLEM_OPTIONS=PROBLEM_OPTIONS,
        SHOW_DB_PATH_IN_NAV=SHOW_DB_PATH_IN_NAV,
        WORKSHOP_AREAS=WORKSHOP_AREAS,
        _archive_notify_type=_archive_notify_type,
        _attach_dialog_tracking=_attach_dialog_tracking,
        _build_delay_payload=_build_delay_payload,
        _calc_frist_progress=_calc_frist_progress,
        _calc_zus_progress=_calc_zus_progress,
        _clean_problem_note=_clean_problem_note,
        _close_tracked_dialog=_close_tracked_dialog,
        _decode_check_string=_decode_check_string,
        _encode_check_list=_encode_check_list,
        _enforce_admin_uncheck_rule=_enforce_admin_uncheck_rule,
        _get_existing_open_by_vehicle=_get_existing_open_by_vehicle,
        _has_login_passwords=_has_login_passwords,
        _login_success_text=_login_success_text,
        _logout_admin=_logout_admin,
        _open_tracked_dialog=_open_tracked_dialog,
        _planned_deadline_dt=_planned_deadline_dt,
        _requires_overdue_reason_for_frist=_requires_overdue_reason_for_frist,
        _resolve_login_role=_resolve_login_role,
        _set_admin=_set_admin,
        archive_task=archive_task,
        as_berlin=as_berlin,
        assign_area=assign_area,
        auto_clear_shopfloorboard_5s_if_due=auto_clear_shopfloorboard_5s_if_due,
        create_or_update_open_task_manual=create_or_update_open_task_manual,
        db_exec=db_exec,
        display_workplace=display_workplace,
        effective_area=effective_area,
        ensure_overdue_state=ensure_overdue_state,
        ensure_problem_state=ensure_problem_state,
        fmt_dt=fmt_dt,
        format_problem_lines=format_problem_lines,
        get_open_tasks_df=get_open_tasks_df,
        can_view_page=can_view_page,
        inject_due24_watcher=inject_due24_watcher,
        is_admin=is_admin,
        is_configuration_user=is_configuration_user,
        notify_delay=notify_delay,
        now_berlin=now_berlin,
        pin_problem=pin_problem,
        render_badge_stack=render_badge_stack,
        render_pill_label=render_pill_label,
        start_lwu_reminder_worker=start_lwu_reminder_worker,
        status_for_row=status_for_row,
        status_palette=status_palette,
    )
    return module


def _page_routes_module():
    from wiring import page_routes as module

    module.configure(
        BERLIN=BERLIN,
        CURRENT_SLOT_VEHICLE_COLOR=CURRENT_SLOT_VEHICLE_COLOR,
        PRIO_MAIN_AREAS=PRIO_MAIN_AREAS,
        PRIO_SIDE_AREAS=PRIO_SIDE_AREAS,
        PRIORISIERUNG_REFRESH_SECONDS=PRIORISIERUNG_REFRESH_SECONDS,
        PROBLEM_OPTIONS=PROBLEM_OPTIONS,
        RX_VEHICLE=RX_VEHICLE,
        SHOPFLOOR_WEEK_TASKS=SHOPFLOOR_WEEK_TASKS,
        TIME_BG=TIME_BG,
        WASH_ZUS_LABEL=WASH_ZUS_LABEL,
        WERKSTATTHALLE_REFRESH_SECONDS=WERKSTATTHALLE_REFRESH_SECONDS,
        WORKSHOP_AREAS=WORKSHOP_AREAS,
        _append_unique_inline_text=_append_unique_inline_text,
        _append_unique_multiline_text=_append_unique_multiline_text,
        _badge_style=_badge_style,
        _build_slots_for_day=_build_slots_for_day,
        _build_weekly_main_area_plan=_build_weekly_main_area_plan,
        _build_weekly_side_area_plan=_build_weekly_side_area_plan,
        _calc_frist_progress=_calc_frist_progress,
        _calc_zus_progress=_calc_zus_progress,
        _canon_dt_for_import_compare=_canon_dt_for_import_compare,
        _canon_zus_for_import_compare=_canon_zus_for_import_compare,
        _canon_zus_item_key=_canon_zus_item_key,
        _clean_problem_note=_clean_problem_note,
        _collect_ecm4_service_assignments=_collect_ecm4_service_assignments,
        _collect_gewerke_slot_events=_collect_gewerke_slot_events,
        _current_data_version=_current_data_version,
        _current_slot_vehicle_keys_from_ecm4=_current_slot_vehicle_keys_from_ecm4,
        _decode_check_string=_decode_check_string,
        _display_area_name=_display_area_name,
        _encode_check_list=_encode_check_list,
        _get_prio_frist_history_maps=_get_prio_frist_history_maps,
        _has_open_dialog=_has_open_dialog,
        _is_urd_open_row=_is_urd_open_row,
        _is_wash_zus_item=_is_wash_zus_item,
        _load_prio_side_state_map=_load_prio_side_state_map,
        _next_slot_start_for_start=_next_slot_start_for_start,
        _norm_status_key=_norm_status_key,
        _norm_vehicle=_norm_vehicle,
        _normalize_workshop_area=_normalize_workshop_area,
        _parse_ecm4_plan_from_excel=_parse_ecm4_plan_from_excel,
        _parse_zusatz_items=_parse_zusatz_items,
        _purge_prio_side_state=_purge_prio_side_state,
        _purge_recent_done_archive=_purge_recent_done_archive,
        _refresh_when_no_dialog=_refresh_when_no_dialog,
        _row_allows_area=_row_allows_area,
        _save_prio_side_state=_save_prio_side_state,
        _shift_day=_shift_day,
        _shift_pair_group=_shift_pair_group,
        _slot_end_for_start=_slot_end_for_start,
        _slot_label_for_start=_slot_label_for_start,
        _slot_secondary_text=_slot_secondary_text,
        _zus_added_only=_zus_added_only,
        add_frist_level=add_frist_level,
        add_open_tasks_with_progress=add_open_tasks_with_progress,
        add_series=add_series,
        apply_missing_open_decisions=apply_missing_open_decisions,
        archive_task=archive_task,
        as_berlin=as_berlin,
        assign_area=assign_area,
        assign_vehicle_to_area_with_shift=assign_vehicle_to_area_with_shift,
        build_import_diff=build_import_diff,
        build_kpi_baureihe=build_kpi_baureihe,
        build_kpi_monthly=build_kpi_monthly,
        build_task_card=build_task_card,
        can_delete_recent_done_functions=can_delete_recent_done_functions,
        can_edit_page=can_edit_page,
        can_use_delete_functions=can_use_delete_functions,
        can_view_page=can_view_page,
        clear_pending_missing_open_state=clear_pending_missing_open_state,
        collect_missing_open_decisions=collect_missing_open_decisions,
        complete_task_action=complete_task_action,
        db_exec=db_exec,
        delete_frist_level=delete_frist_level,
        delete_vehicle_series_mapping=delete_vehicle_series_mapping,
        delete_work_package=delete_work_package,
        delete_recent_done_entry=delete_recent_done_entry,
        df_to_excel_bytes=df_to_excel_bytes,
        delete_user=delete_user,
        find_missing_open_tasks_for_import=find_missing_open_tasks_for_import,
        find_other_assigned_rows_for_same_vehicle=find_other_assigned_rows_for_same_vehicle,
        fmt_dt=fmt_dt,
        format_problem_lines=format_problem_lines,
        get_archive_df=get_archive_df,
        get_supported_series_frist_levels=get_supported_series_frist_levels,
        get_open_tasks_df=get_open_tasks_df,
        get_recent_done_df=get_recent_done_df,
        get_shopfloorboard_5s_week=get_shopfloorboard_5s_week,
        get_vehicle_series_for_vehicle=get_vehicle_series_for_vehicle,
        inject_due24_watcher=inject_due24_watcher,
        is_admin=is_admin,
        is_configuration_user=is_configuration_user,
        is_full_admin=is_full_admin,
        frist_trigger_options=frist_trigger_options,
        list_frist_levels=list_frist_levels,
        list_frist_level_configs=list_frist_level_configs,
        list_series=list_series,
        list_vehicle_series_mappings=list_vehicle_series_mappings,
        list_work_packages=list_work_packages,
        list_users=list_users,
        get_standard_access=get_standard_access,
        save_standard_access=save_standard_access,
        load_ecm4_plan_df=load_ecm4_plan_df,
        move_frist_level=move_frist_level,
        move_work_package=move_work_package,
        now_berlin=now_berlin,
        open_ausseneinsatz_dialog=open_ausseneinsatz_dialog,
        open_admin_login_dialog=open_admin_login_dialog,
        open_frist_dialog=open_frist_dialog,
        open_new_order_dialog=open_new_order_dialog,
        open_problem_dialog=open_problem_dialog,
        open_zus_dialog=open_zus_dialog,
        parse_excel_to_df_bytes=parse_excel_to_df_bytes,
        parse_rws_week_plan_from_excel=parse_rws_week_plan_from_excel,
        render_countdown_badge=render_countdown_badge,
        render_legend=render_legend,
        render_nav=render_nav,
        render_pill_label=render_pill_label,
        render_time_badge=render_time_badge,
        replace_ecm4_plan_in_db=replace_ecm4_plan_in_db,
        replace_rws_week_plan_in_db=replace_rws_week_plan_in_db,
        reset_all=reset_all,
        save_vehicle_series_mapping=save_vehicle_series_mapping,
        save_user=save_user,
        save_work_package=save_work_package,
        save_shopfloorboard_5s_week=save_shopfloorboard_5s_week,
        status_for_row=status_for_row,
        status_palette=status_palette,
        trigger_lwu_test_next_24h=trigger_lwu_test_next_24h,
        update_frist_level_trigger_type=update_frist_level_trigger_type,
        update_frist_level_active=update_frist_level_active,
        update_frist_level_config=update_frist_level_config,
        set_all_frist_levels_active=set_all_frist_levels_active,
        user_permission_options=user_permission_options,
        user_role_options=user_role_options,
    )
    return module


def _bootstrap_module():
    from wiring import bootstrap as module

    from components.styles import register_global_head_html

    module.configure(
        APP_BINDING_REFRESH_INTERVAL_SECONDS=APP_BINDING_REFRESH_INTERVAL_SECONDS,
        APP_DISCONNECT_RELOAD_SECONDS=APP_DISCONNECT_RELOAD_SECONDS,
        APP_HOST=APP_HOST,
        APP_PORT=APP_PORT,
        APP_PORT_RAW=APP_PORT_RAW,
        APP_RECONNECT_TIMEOUT_SECONDS=APP_RECONNECT_TIMEOUT_SECONDS,
        APP_STORAGE_SECRET=APP_STORAGE_SECRET,
        BASE_DIR=BASE_DIR,
        BROWSER_HTML_ZOOM=BROWSER_HTML_ZOOM,
        NATIVE_HTML_ZOOM=NATIVE_HTML_ZOOM,
        NATIVE_MODE=NATIVE_MODE,
        OPEN_ITEM_FONT_SIZE_PX=OPEN_ITEM_FONT_SIZE_PX,
        OPEN_ITEM_FONT_WEIGHT=OPEN_ITEM_FONT_WEIGHT,
        OPEN_ITEM_GAP_PX=OPEN_ITEM_GAP_PX,
        OPEN_ITEM_LINE_HEIGHT=OPEN_ITEM_LINE_HEIGHT,
        auto_clear_shopfloorboard_5s_if_due=auto_clear_shopfloorboard_5s_if_due,
        init_db=init_db,
        register_global_head_html=register_global_head_html,
        start_lwu_reminder_worker=start_lwu_reminder_worker,
    )
    return module


def render_nav() -> None:
    _ui_actions_module().render_nav()


def open_admin_login_dialog(
    *,
    on_success: Callable[[], None] | None = None,
    reload_on_success: bool = True,
    title: str = "Login",
    hint: str | None = None,
) -> None:
    _ui_actions_module().open_admin_login_dialog(
        on_success=on_success,
        reload_on_success=reload_on_success,
        title=title,
        hint=hint,
    )


def render_legend() -> None:
    _ui_actions_module().render_legend()


def build_task_card(row: pd.Series, refresh_fn, *, show_area_controls: bool = False) -> None:
    _ui_actions_module().build_task_card(
        row,
        refresh_fn,
        show_area_controls=show_area_controls,
    )

def open_zus_dialog(task_id: int, refresh_fn: Callable[[], None]) -> None:
    _ui_actions_module().open_zus_dialog(task_id, refresh_fn)


def open_frist_dialog(task_id: int, area_code: str, refresh_fn: Callable[[], None]) -> None:
    _ui_actions_module().open_frist_dialog(task_id, area_code, refresh_fn)


def open_problem_dialog(task_id: int, refresh_fn: Callable[[], None]) -> None:
    _ui_actions_module().open_problem_dialog(task_id, refresh_fn)


def open_overdue_dialog_for(task_id: int, refresh_fn: Callable[[], None]) -> None:
    _ui_actions_module().open_overdue_dialog_for(task_id, refresh_fn)


def open_overdue_dialog(task_id: int, refresh_fn: Callable[[], None]) -> None:
    _ui_actions_module().open_overdue_dialog(task_id, refresh_fn)

def complete_task_action(task_id: int, refresh_fn: Callable[[], None]) -> None:
    _ui_actions_module().complete_task_action(task_id, refresh_fn)


def open_new_order_dialog(refresh_fn: Callable[[], None]) -> None:
    _ui_actions_module().open_new_order_dialog(refresh_fn)


if callable(_initialize_planning_module):
    _initialize_planning_module()

if callable(_register_planning_pages):
    _register_planning_pages(render_nav, is_admin, is_configuration_user)

@ui.page("/")
def page_home() -> None:
    _page_routes_module().page_home()


@ui.page("/offen")
def page_open_tasks() -> None:
    _page_routes_module().page_open_tasks()


@ui.page("/werkstatthalle")
def page_werkstatthalle() -> None:
    _page_routes_module().page_werkstatthalle()


@ui.page("/gleisplan")
def page_gleisplan() -> None:
    _page_routes_module().page_gleisplan()


@ui.page("/tagesplanung")
@ui.page("/priorisierung")
def page_priorisierung() -> None:
    _page_routes_module().page_priorisierung()


@ui.page("/shopfloorboard")
def page_shopfloorboard() -> None:
    _page_routes_module().page_shopfloorboard()


@ui.page("/konfiguration")
def page_configuration() -> None:
    _page_routes_module().page_configuration()


@ui.page("/wochenplanung")
def page_wochenplanung() -> None:
    _page_routes_module().page_wochenplanung()


@ui.page("/archiv_14d")
def page_archive_14d() -> None:
    _page_routes_module().page_archive_14d()


@ui.page("/upload")
def page_upload() -> None:
    _page_routes_module().page_upload()


@ui.page("/archiv")
def page_archive() -> None:
    _page_routes_module().page_archive()


_bootstrap_module().initialize_app()

if __name__ == "__main__":
    _bootstrap_module().run_app()
