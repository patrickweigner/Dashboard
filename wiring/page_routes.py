from __future__ import annotations

import importlib
import sys
from pathlib import Path


_APP_DIR = Path(__file__).resolve().parents[1]
_APP_DIR_TEXT = str(_APP_DIR)
if _APP_DIR_TEXT not in sys.path:
    sys.path.insert(0, _APP_DIR_TEXT)


def _module_belongs_to_app(module) -> bool:
    candidates = []
    module_file = getattr(module, "__file__", None)
    if module_file:
        candidates.append(module_file)
    candidates.extend(getattr(module, "__path__", []) or [])
    for candidate in candidates:
        try:
            Path(candidate).resolve().relative_to(_APP_DIR)
            return True
        except (OSError, ValueError):
            continue
    return False


def _import_page_render(module_name: str):
    qualified_name = f"pages.{module_name}"
    try:
        return importlib.import_module(qualified_name).render
    except ModuleNotFoundError as exc:
        if exc.name not in {"pages", qualified_name}:
            raise
        pages_module = sys.modules.get("pages")
        if pages_module is not None and _module_belongs_to_app(pages_module):
            raise
        sys.modules.pop("pages", None)
        importlib.invalidate_caches()
        return importlib.import_module(qualified_name).render


def configure(**deps) -> None:
    globals().update(deps)


def _ensure_page_permission(page_key: str) -> bool:
    can_view = globals().get("can_view_page")
    if callable(can_view) and not bool(can_view(page_key)):
        render_nav()
        from nicegui import ui

        ui.label("Kein Zugriff").classes("page-title")
        ui.label("Dieser Nutzer darf diese Seite nicht sehen.").classes("text-gray-400")
        return False
    return True


def page_home() -> None:
    if not _ensure_page_permission("home"):
        return
    render = _import_page_render("home_page")

    render(
        render_nav=render_nav,
        is_admin=is_admin,
        is_configuration_user=is_configuration_user,
    )


def page_open_tasks() -> None:
    if not _ensure_page_permission("open_tasks"):
        return
    render = _import_page_render("open_tasks_page")

    render(
        render_nav=render_nav,
        open_new_order_dialog=open_new_order_dialog,
        render_legend=render_legend,
        get_open_tasks_df=get_open_tasks_df,
        build_task_card=build_task_card,
        refresh_when_no_dialog=_refresh_when_no_dialog,
        current_data_version=_current_data_version,
    )


def page_werkstatthalle() -> None:
    if not _ensure_page_permission("werkstatthalle"):
        return
    render = _import_page_render("werkstatthalle_page")

    render(
        refresh_interval_seconds=WERKSTATTHALLE_REFRESH_SECONDS,
        render_nav=render_nav,
        open_ausseneinsatz_dialog=open_ausseneinsatz_dialog,
        shift_day=_shift_day,
        now_berlin=now_berlin,
        current_slot_vehicle_color=CURRENT_SLOT_VEHICLE_COLOR,
        workshop_areas=WORKSHOP_AREAS,
        is_admin=is_admin,
        get_open_tasks_df=get_open_tasks_df,
        current_slot_vehicle_keys_from_ecm4=_current_slot_vehicle_keys_from_ecm4,
        fmt_dt=fmt_dt,
        find_other_assigned_rows_for_same_vehicle=find_other_assigned_rows_for_same_vehicle,
        db_exec=db_exec,
        normalize_workshop_area=_normalize_workshop_area,
        assign_vehicle_to_area_with_shift=assign_vehicle_to_area_with_shift,
        row_allows_area=_row_allows_area,
        assign_area=assign_area,
        as_berlin=as_berlin,
        norm_vehicle=_norm_vehicle,
        clean_problem_note=_clean_problem_note,
        status_for_row=status_for_row,
        status_palette=status_palette,
        calc_frist_progress=_calc_frist_progress,
        calc_zus_progress=_calc_zus_progress,
        render_pill_label=render_pill_label,
        badge_style=_badge_style,
        format_problem_lines=format_problem_lines,
        inject_due24_watcher=inject_due24_watcher,
        complete_task_action=complete_task_action,
        open_frist_dialog=open_frist_dialog,
        open_zus_dialog=open_zus_dialog,
        open_problem_dialog=open_problem_dialog,
        render_countdown_badge=render_countdown_badge,
        has_open_dialog=_has_open_dialog,
    )


def page_gleisplan() -> None:
    if not _ensure_page_permission("gleisplan"):
        return
    render = _import_page_render("gleisplan_page")

    render(
        refresh_interval_seconds=WERKSTATTHALLE_REFRESH_SECONDS,
        render_nav=render_nav,
        now_berlin=now_berlin,
        get_open_tasks_df=get_open_tasks_df,
        list_vehicle_series_mappings=list_vehicle_series_mappings,
        db_exec=db_exec,
        normalize_workshop_area=_normalize_workshop_area,
        norm_vehicle=_norm_vehicle,
        fmt_dt=fmt_dt,
        status_for_row=status_for_row,
        status_palette=status_palette,
        calc_frist_progress=_calc_frist_progress,
        calc_zus_progress=_calc_zus_progress,
        get_vehicle_series_for_vehicle=get_vehicle_series_for_vehicle,
        is_admin=is_admin,
        row_allows_area=_row_allows_area,
        assign_area=assign_area,
        refresh_when_no_dialog=_refresh_when_no_dialog,
    )


def page_priorisierung() -> None:
    if not _ensure_page_permission("priorisierung"):
        return
    render = _import_page_render("priorisierung_page")

    render(
        refresh_interval_seconds=PRIORISIERUNG_REFRESH_SECONDS,
        render_nav=render_nav,
        now_berlin=now_berlin,
        _shift_day=_shift_day,
        open_ausseneinsatz_dialog=open_ausseneinsatz_dialog,
        is_full_admin=is_full_admin,
        trigger_lwu_test_next_24h=trigger_lwu_test_next_24h,
        BERLIN=BERLIN,
        PRIO_MAIN_AREAS=PRIO_MAIN_AREAS,
        PRIO_SIDE_AREAS=PRIO_SIDE_AREAS,
        RX_VEHICLE=RX_VEHICLE,
        TIME_BG=TIME_BG,
        WASH_ZUS_LABEL=WASH_ZUS_LABEL,
        _append_unique_inline_text=_append_unique_inline_text,
        _append_unique_multiline_text=_append_unique_multiline_text,
        _build_slots_for_day=_build_slots_for_day,
        _canon_zus_item_key=_canon_zus_item_key,
        _collect_ecm4_service_assignments=_collect_ecm4_service_assignments,
        _collect_gewerke_slot_events=_collect_gewerke_slot_events,
        _decode_check_string=_decode_check_string,
        _display_area_name=_display_area_name,
        _encode_check_list=_encode_check_list,
        _get_prio_frist_history_maps=_get_prio_frist_history_maps,
        _is_urd_open_row=_is_urd_open_row,
        _is_wash_zus_item=_is_wash_zus_item,
        _load_prio_side_state_map=_load_prio_side_state_map,
        _next_slot_start_for_start=_next_slot_start_for_start,
        _norm_vehicle=_norm_vehicle,
        _parse_zusatz_items=_parse_zusatz_items,
        _purge_prio_side_state=_purge_prio_side_state,
        _refresh_when_no_dialog=_refresh_when_no_dialog,
        _save_prio_side_state=_save_prio_side_state,
        _shift_pair_group=_shift_pair_group,
        _slot_end_for_start=_slot_end_for_start,
        _slot_label_for_start=_slot_label_for_start,
        _slot_secondary_text=_slot_secondary_text,
        archive_task=archive_task,
        as_berlin=as_berlin,
        db_exec=db_exec,
        get_open_tasks_df=get_open_tasks_df,
        is_admin=is_admin,
        load_ecm4_plan_df=load_ecm4_plan_df,
        render_time_badge=render_time_badge,
    )


def page_shopfloorboard() -> None:
    if not _ensure_page_permission("shopfloorboard"):
        return
    render = _import_page_render("shopfloorboard_page")

    render(
        render_nav=render_nav,
        now_berlin=now_berlin,
        get_shopfloorboard_5s_week=get_shopfloorboard_5s_week,
        save_shopfloorboard_5s_week=save_shopfloorboard_5s_week,
        shopfloor_week_tasks=SHOPFLOOR_WEEK_TASKS,
    )


def page_configuration() -> None:
    if not _ensure_page_permission("configuration"):
        return
    render = _import_page_render("configuration_page")

    render(
        render_nav=render_nav,
        is_configuration_user=is_configuration_user,
        open_admin_login_dialog=open_admin_login_dialog,
        get_supported_series_frist_levels=get_supported_series_frist_levels,
        frist_trigger_options=frist_trigger_options,
        list_series=list_series,
        add_series=add_series,
        list_frist_levels=list_frist_levels,
        list_frist_level_configs=list_frist_level_configs,
        add_frist_level=add_frist_level,
        update_frist_level_trigger_type=update_frist_level_trigger_type,
        update_frist_level_active=update_frist_level_active,
        set_all_frist_levels_active=set_all_frist_levels_active,
        update_frist_level_config=update_frist_level_config,
        delete_frist_level=delete_frist_level,
        move_frist_level=move_frist_level,
        list_work_packages=list_work_packages,
        save_work_package=save_work_package,
        delete_work_package=delete_work_package,
        move_work_package=move_work_package,
        list_vehicle_series_mappings=list_vehicle_series_mappings,
        save_vehicle_series_mapping=save_vehicle_series_mapping,
        delete_vehicle_series_mapping=delete_vehicle_series_mapping,
        list_users=list_users,
        save_user=save_user,
        get_standard_access=get_standard_access,
        save_standard_access=save_standard_access,
        delete_user=delete_user,
        user_permission_options=user_permission_options,
        user_role_options=user_role_options,
        workshop_areas=WORKSHOP_AREAS,
        db_exec=db_exec,
        now_berlin=now_berlin,
    )


def page_wochenplanung() -> None:
    if not _ensure_page_permission("wochenplanung"):
        return
    render = _import_page_render("wochenplanung_page")

    render(
        render_nav=render_nav,
        now_berlin=now_berlin,
        build_weekly_main_area_plan=_build_weekly_main_area_plan,
        build_weekly_side_area_plan=_build_weekly_side_area_plan,
        refresh_when_no_dialog=_refresh_when_no_dialog,
    )


def page_archive_14d() -> None:
    from nicegui import ui

    ui.navigate.to("/archiv")


def page_upload() -> None:
    if not _ensure_page_permission("upload"):
        return
    render = _import_page_render("upload_page")

    render(
        render_nav=render_nav,
        is_admin=is_admin,
        can_use_delete_functions=can_use_delete_functions,
        as_berlin=as_berlin,
        now_berlin=now_berlin,
        problem_options=PROBLEM_OPTIONS,
        parse_ecm4_plan_from_excel=_parse_ecm4_plan_from_excel,
        parse_excel_to_df_bytes=parse_excel_to_df_bytes,
        build_import_diff=build_import_diff,
        find_missing_open_tasks_for_import=find_missing_open_tasks_for_import,
        clear_pending_missing_open_state=clear_pending_missing_open_state,
        parse_rws_week_plan_from_excel=parse_rws_week_plan_from_excel,
        canon_dt_for_import_compare=_canon_dt_for_import_compare,
        canon_zus_for_import_compare=_canon_zus_for_import_compare,
        zus_added_only=_zus_added_only,
        collect_missing_open_decisions=collect_missing_open_decisions,
        apply_missing_open_decisions=apply_missing_open_decisions,
        add_open_tasks_with_progress=add_open_tasks_with_progress,
        replace_ecm4_plan_in_db=replace_ecm4_plan_in_db,
        replace_rws_week_plan_in_db=replace_rws_week_plan_in_db,
        reset_all=reset_all,
    )


def page_archive() -> None:
    if not _ensure_page_permission("archive"):
        return
    render = _import_page_render("archive_page")

    render(
        render_nav=render_nav,
        is_admin=is_admin,
        can_delete_recent_done_functions=can_delete_recent_done_functions,
        purge_recent_done_archive=_purge_recent_done_archive,
        get_recent_done_df=get_recent_done_df,
        delete_recent_done_entry=delete_recent_done_entry,
        now_berlin=now_berlin,
        get_archive_df=get_archive_df,
        norm_status_key=_norm_status_key,
        build_kpi_monthly=build_kpi_monthly,
        build_kpi_baureihe=build_kpi_baureihe,
        df_to_excel_bytes=df_to_excel_bytes,
        refresh_when_no_dialog=_refresh_when_no_dialog,
    )
