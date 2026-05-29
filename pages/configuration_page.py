from __future__ import annotations

import json
import math
import os
import shutil
from datetime import datetime
from typing import Any, Callable

from nicegui import ui

from core.config import DB_PATH
from services.gleisplan_service import (
    CONNECTABLE_ITEM_TYPES,
    HALL_TRACK_LABELS,
    SWITCH_BRANCH_HEEL_X_RATIO,
    SWITCH_BRANCH_PORT_X_RATIO,
    SWITCH_BRANCH_PORT_Y_RATIO,
    SWITCH_MAIN_RAIL_Y_RATIO,
    add_gleisplan_connection_path_point,
    apply_eberswalde_pdf_trace_geometry,
    build_hall_track_grid,
    connection_port_options_for_item,
    delete_gleisplan_connection,
    delete_gleisplan_connection_path_point,
    delete_gleisplan_hall_track,
    delete_gleisplan_layout_item,
    load_gleisplan_connections,
    load_gleisplan_hall_tracks,
    load_gleisplan_layout_items,
    load_gleisplan_pdf_trace_settings,
    make_gleisplan_item_id_for_type_label,
    ordered_hall_track_codes,
    reset_gleisplan_pdf_trace_settings,
    reset_gleisplan_connection_route_shape,
    reset_gleisplan_layout_to_default,
    save_gleisplan_connection,
    save_gleisplan_hall_track,
    save_gleisplan_layout_item,
    save_gleisplan_pdf_trace_settings,
    smooth_gleisplan_connection_route,
    update_gleisplan_connection_curve,
    update_gleisplan_connection_path_point,
    update_gleisplan_layout_item_geometry,
    update_gleisplan_layout_item_position,
)
from services.workshop_config_service import (
    WORKSHOP_TEXT_FIELDS,
    WORKSHOP_TILE_TYPE_OPTIONS,
    delete_workshop_hall_tile,
    load_workshop_hall_texts,
    load_workshop_hall_tiles,
    reorder_workshop_hall_tiles,
    reset_workshop_hall_config,
    save_workshop_hall_texts,
    save_workshop_hall_tile,
)


ALL_FRISTS = "__all__"
MULTI_FRISTS = "__multi__"
ALL_WORK_PACKAGES = "__all_work_packages__"
NEW_FRIST = "__new__"
GENERAL_SERIES_NAME = "Allgemein"
GENERAL_FRIST_LEVEL = "Allgemein"
GLEISPLAN_BOARD_ASPECT = 1501 / 1058
HALL_POSITION_OPTIONS: dict[str, str] = {
    "oben links": "oben links",
    "oben rechts": "oben rechts",
    "unten links": "unten links",
    "unten rechts": "unten rechts",
}


def _duration_hours(value_minutes: Any) -> float:
    try:
        minutes = float(value_minutes)
    except Exception:
        return 0.0
    return minutes / 60.0


def _duration_hours_text(value_minutes: Any) -> str:
    hours = _duration_hours(value_minutes)
    return f"{hours:.1f}".replace(".", ",") + " h"


def _duration_input_value(value_minutes: Any) -> float:
    hours = _duration_hours(value_minutes)
    if hours < 0.5:
        return 0.5
    return round(hours * 2) / 2


def _work_package_total_minutes(package: dict[str, Any]) -> float:
    try:
        duration = float(package.get("duration_minutes") or 0)
    except Exception:
        duration = 0.0
    try:
        employees = int(package.get("employee_count") or 0)
    except Exception:
        employees = 0
    return duration * max(0, employees)


def _package_capacity_minutes(package: dict[str, Any]) -> float:
    try:
        return float(package.get("_total_capacity_minutes"))
    except Exception:
        return _work_package_total_minutes(package)


def _case_key(value: Any) -> str:
    return str(value or "").strip().casefold()


def _is_general_series(series: Any) -> bool:
    return _case_key(series) == _case_key(GENERAL_SERIES_NAME)


def _selected_frist_levels(state: dict[str, Any], levels: list[str]) -> list[str]:
    raw_multi = state.get("frist_filters")
    if isinstance(raw_multi, list):
        selected = [str(item or "").strip() for item in raw_multi]
    else:
        selected = []
    legacy = str(state.get("frist_filter") or ALL_FRISTS).strip()
    if not selected and legacy and legacy != ALL_FRISTS:
        selected = [legacy]
    valid = [level for level in levels if level in selected]
    state["frist_filters"] = valid
    state["frist_filter"] = valid[0] if len(valid) == 1 else ALL_FRISTS
    return valid


def _selected_package_title(state: dict[str, Any], available_titles: list[str]) -> str:
    selected = str(state.get("package_filter") or ALL_WORK_PACKAGES).strip()
    if selected != ALL_WORK_PACKAGES and selected not in available_titles:
        selected = ALL_WORK_PACKAGES
    state["package_filter"] = selected
    return selected


def _aggregate_packages_for_selected_frists(packages: list[dict[str, Any]], selected_frists: list[str]) -> list[dict[str, Any]]:
    if len(selected_frists) <= 1:
        return [dict(package) for package in packages]
    combined: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for package in packages:
        title = str(package.get("title") or "").strip()
        if not title:
            continue
        key = _case_key(title)
        if key not in combined:
            combined[key] = {
                "_aggregate": True,
                "_aggregate_items": [],
                "_total_capacity_minutes": 0.0,
                "id": 0,
                "baureihe": package.get("baureihe"),
                "friststufe": "",
                "title": title,
                "employee_count": 0,
                "duration_minutes": 0.0,
                "sort_order": package.get("sort_order") or 0,
            }
            order.append(key)
        item = combined[key]
        row = dict(package)
        item["_aggregate_items"].append(row)
        frist = str(row.get("friststufe") or "").strip()
        frists = [x for x in str(item.get("friststufe") or "").split("+") if x]
        if frist and frist not in frists:
            frists.append(frist)
        item["friststufe"] = "+".join(frists)
        try:
            item["employee_count"] = max(int(item.get("employee_count") or 0), int(row.get("employee_count") or 0))
        except Exception:
            pass
        try:
            item["duration_minutes"] = float(item.get("duration_minutes") or 0) + float(row.get("duration_minutes") or 0)
        except Exception:
            pass
        item["_total_capacity_minutes"] = float(item.get("_total_capacity_minutes") or 0) + _work_package_total_minutes(row)
    return [combined[key] for key in order]


def _is_half_hour_step(value_hours: float) -> bool:
    return abs((float(value_hours) * 2.0) - round(float(value_hours) * 2.0)) < 0.000001


def _select_props() -> str:
    return "outlined dense popup-content-class=area-select-popup behavior=menu"


def _coerce_trace_float(value: Any, default: float, lower: float, upper: float) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = float(default)
    return max(float(lower), min(float(upper), parsed))


def _coerce_trace_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().casefold() in {"1", "true", "yes", "ja", "on"}


def _normalize_trace_settings(settings: Any) -> dict[str, Any]:
    raw = settings if isinstance(settings, dict) else {}
    return {
        "enabled": _coerce_trace_bool(raw.get("enabled")),
        "opacity": _coerce_trace_float(raw.get("opacity"), 0.45, 0.2, 0.8),
        "x": _coerce_trace_float(raw.get("x"), 0.0, -100.0, 100.0),
        "y": _coerce_trace_float(raw.get("y"), 0.0, -100.0, 100.0),
        "scale_x": _coerce_trace_float(raw.get("scale_x"), 1.0, 0.5, 2.0),
        "scale_y": _coerce_trace_float(raw.get("scale_y"), 1.0, 0.5, 2.0),
        "rotation": _coerce_trace_float(raw.get("rotation"), 0.0, -15.0, 15.0),
        "hide_grid": _coerce_trace_bool(raw.get("hide_grid")),
        "fade_foreground": _coerce_trace_bool(raw.get("fade_foreground")),
        "hide_labels": _coerce_trace_bool(raw.get("hide_labels")),
    }


def _get_gleisplan_trace_settings(state: dict[str, Any], db_exec: Callable[..., Any]) -> dict[str, Any]:
    if not state.get("gleisplan_pdf_trace_loaded"):
        state["gleisplan_pdf_trace_settings"] = load_gleisplan_pdf_trace_settings(db_exec)
        state["gleisplan_pdf_trace_loaded"] = True
    settings = _normalize_trace_settings(state.get("gleisplan_pdf_trace_settings"))
    state["gleisplan_pdf_trace_settings"] = settings
    return settings


def _set_trace_setting(
    state: dict[str, Any],
    key: str,
    value: Any,
    *,
    refresh: Callable[[], None],
) -> None:
    settings = _normalize_trace_settings(state.get("gleisplan_pdf_trace_settings"))
    settings[key] = value
    state["gleisplan_pdf_trace_settings"] = _normalize_trace_settings(settings)
    refresh()


def _adjust_trace_setting(
    state: dict[str, Any],
    key: str,
    delta: float,
    *,
    refresh: Callable[[], None],
) -> None:
    settings = _normalize_trace_settings(state.get("gleisplan_pdf_trace_settings"))
    settings[key] = float(settings.get(key) or 0.0) + float(delta)
    state["gleisplan_pdf_trace_settings"] = _normalize_trace_settings(settings)
    refresh()


def _drag_over_line_js() -> str:
    return (
        "(event) => {"
        "event.preventDefault();"
        "const el = event.currentTarget;"
        "const rect = el.getBoundingClientRect();"
        "const after = event.clientY >= rect.top + rect.height / 2;"
        "el.classList.toggle('cfg-drop-after', after);"
        "el.classList.toggle('cfg-drop-before', !after);"
        "}"
    )


def _drag_clear_line_js() -> str:
    return (
        "(event) => {"
        "const el = event.currentTarget;"
        "el.classList.remove('cfg-drop-before');"
        "el.classList.remove('cfg-drop-after');"
        "}"
    )


def _drop_emit_line_js() -> str:
    return (
        "(event) => {"
        "event.preventDefault();"
        "const el = event.currentTarget;"
        "const rect = el.getBoundingClientRect();"
        "const placement = event.clientY >= rect.top + rect.height / 2 ? 'after' : 'before';"
        "el.classList.remove('cfg-drop-before');"
        "el.classList.remove('cfg-drop-after');"
        "emit({source: event.dataTransfer.getData('text/plain'), placement});"
        "}"
    )


def _drag_over_tile_js() -> str:
    return (
        "(event) => {"
        "event.preventDefault();"
        "const el = event.currentTarget;"
        "const rect = el.getBoundingClientRect();"
        "const after = event.clientY >= rect.top + rect.height / 2;"
        "el.classList.toggle('cfg-workshop-drop-after', after);"
        "el.classList.toggle('cfg-workshop-drop-before', !after);"
        "}"
    )


def _drag_clear_tile_js() -> str:
    return (
        "(event) => {"
        "const el = event.currentTarget;"
        "el.classList.remove('cfg-workshop-drop-before');"
        "el.classList.remove('cfg-workshop-drop-after');"
        "}"
    )


def _drop_emit_tile_js() -> str:
    return (
        "(event) => {"
        "event.preventDefault();"
        "const el = event.currentTarget;"
        "const rect = el.getBoundingClientRect();"
        "const placement = event.clientY >= rect.top + rect.height / 2 ? 'after' : 'before';"
        "el.classList.remove('cfg-workshop-drop-before');"
        "el.classList.remove('cfg-workshop-drop-after');"
        "emit({source: event.dataTransfer.getData('text/plain'), placement});"
        "}"
    )


def _trigger_label(trigger_options: dict[str, str], value: Any) -> str:
    key = str(value or "time")
    return str(trigger_options.get(key) or trigger_options.get("time") or key)


def _render_breadcrumb(parts: list[tuple[str, Callable[[], None] | None]]) -> None:
    with ui.row().classes("cfg-breadcrumb"):
        for index, (label, action) in enumerate(parts):
            if index > 0:
                ui.label("-").classes("cfg-breadcrumb-separator")
            item = ui.label(label).classes("cfg-breadcrumb-current" if action is None else "cfg-breadcrumb-link")
            if action is not None:
                item.on("click", lambda _event=None, callback=action: callback())


def render(
    *,
    render_nav: Callable[[], None],
    is_configuration_user: Callable[[], bool],
    open_admin_login_dialog: Callable[..., None],
    get_supported_series_frist_levels: Callable[[], dict[str, list[str]]],
    frist_trigger_options: Callable[[], dict[str, str]],
    list_series: Callable[[], list[str]],
    add_series: Callable[[str], str],
    list_frist_levels: Callable[[str], list[str]],
    list_frist_level_configs: Callable[[str], list[dict[str, Any]]],
    add_frist_level: Callable[..., str],
    update_frist_level_trigger_type: Callable[[str, str, str], bool],
    update_frist_level_active: Callable[[str, str, bool], bool],
    set_all_frist_levels_active: Callable[[str, bool], int],
    update_frist_level_config: Callable[[str, str, str, str], str],
    delete_frist_level: Callable[[str, str], bool],
    move_frist_level: Callable[[str, str, int], bool],
    list_work_packages: Callable[..., list[dict[str, Any]]],
    save_work_package: Callable[..., int],
    delete_work_package: Callable[[int], bool],
    move_work_package: Callable[[str, str, int, int], bool],
    list_vehicle_series_mappings: Callable[..., list[dict[str, Any]]],
    save_vehicle_series_mapping: Callable[[str, str], None],
    delete_vehicle_series_mapping: Callable[[str], bool],
    list_users: Callable[[], list[dict[str, Any]]],
    save_user: Callable[..., str],
    get_standard_access: Callable[[], dict[str, Any]],
    save_standard_access: Callable[..., str],
    delete_user: Callable[[str], bool],
    user_permission_options: Callable[[], dict[str, str]],
    user_role_options: Callable[[], dict[str, str]],
    workshop_areas: list[str],
    db_exec: Callable[..., Any],
    now_berlin: Callable[[], datetime],
) -> None:
    render_nav()

    state: dict[str, Any] = {
        "view": "home",
        "selected_series": "",
        "frist_filter": ALL_FRISTS,
        "frist_filters": [],
        "package_filter": ALL_WORK_PACKAGES,
        "edit_vehicle": None,
        "gleisplan_draw_street": False,
        "gleisplan_selected_item": "",
        "gleisplan_connection_source": "",
        "gleisplan_pending_positions": {},
        "gleisplan_pdf_trace_settings": None,
        "gleisplan_pdf_trace_loaded": False,
    }

    page = ui.column().classes("config-page w-full gap-3")
    with page:
        if not is_configuration_user():
            ui.label("Konfiguration").classes("page-title")
            with ui.element("section").classes("cfg-page-head"):
                ui.label("Zugriff geschützt").classes("cfg-eyebrow")
                ui.label("Diese Seite ist nur für den Benutzer ODIGEw sichtbar.").classes("cfg-heading")
                ui.label("Bitte mit Benutzer ODIGEw und gültigem Passwort anmelden.").classes("cfg-subtle")
                ui.button(
                    "Login",
                    on_click=lambda: open_admin_login_dialog(
                        title="Login für Konfiguration",
                        hint="Bitte als Benutzer ODIGEw anmelden.",
                    ),
                ).classes("cfg-btn-primary")
            return

        ui.add_body_html(
            """
            <script>
              (function () {
                var ROOT = window.parent || window;
                try {
                  ROOT.__fristenConfigurationPageActive = true;
                  ROOT.document.documentElement.setAttribute("data-fristen-configuration-page", "1");
                  if (ROOT._dueTickerId) {
                    ROOT.clearInterval(ROOT._dueTickerId);
                    ROOT._dueTickerId = null;
                  }
                  ROOT._dueWatcherMap = {};
                } catch (e) {}
              })();
            </script>
            """
        )

        body = ui.column().classes("w-full gap-3")

        def go_home() -> None:
            state["view"] = "home"
            state["selected_series"] = ""
            state["frist_filter"] = ALL_FRISTS
            state["frist_filters"] = []
            state["package_filter"] = ALL_WORK_PACKAGES
            state["edit_vehicle"] = None
            state["gleisplan_draw_street"] = False
            state["gleisplan_selected_item"] = ""
            state["gleisplan_connection_source"] = ""
            state["gleisplan_pending_positions"] = {}
            content.refresh()

        def go_users() -> None:
            state["view"] = "users"
            state["selected_series"] = ""
            state["edit_vehicle"] = None
            content.refresh()

        def go_series_overview() -> None:
            state["view"] = "series_overview"
            state["selected_series"] = ""
            state["frist_filter"] = ALL_FRISTS
            state["frist_filters"] = []
            state["package_filter"] = ALL_WORK_PACKAGES
            state["edit_vehicle"] = None
            state["gleisplan_draw_street"] = False
            state["gleisplan_selected_item"] = ""
            state["gleisplan_connection_source"] = ""
            state["gleisplan_pending_positions"] = {}
            content.refresh()

        def go_gleisplan() -> None:
            state["view"] = "gleisplan"
            state["selected_series"] = ""
            state["frist_filter"] = ALL_FRISTS
            state["frist_filters"] = []
            state["package_filter"] = ALL_WORK_PACKAGES
            state["edit_vehicle"] = None
            content.refresh()

        def go_werkstatthalle() -> None:
            state["view"] = "werkstatthalle"
            state["selected_series"] = ""
            state["frist_filter"] = ALL_FRISTS
            state["frist_filters"] = []
            state["package_filter"] = ALL_WORK_PACKAGES
            state["edit_vehicle"] = None
            content.refresh()

        def open_series(series: str) -> None:
            state["view"] = "series_detail"
            state["selected_series"] = str(series or "").strip()
            state["frist_filter"] = ALL_FRISTS
            state["frist_filters"] = []
            state["package_filter"] = ALL_WORK_PACKAGES
            state["edit_vehicle"] = None
            content.refresh()

        @ui.refreshable
        def content() -> None:
            body.clear()
            with body:
                view = str(state.get("view") or "home")
                if view == "series_overview":
                    _render_series_overview(
                        list_series=list_series,
                        add_series=add_series,
                        open_series=open_series,
                        go_home=go_home,
                        refresh=content.refresh,
                    )
                elif view == "series_detail":
                    _render_series_detail(
                        state=state,
                        series=str(state.get("selected_series") or ""),
                        list_frist_levels=list_frist_levels,
                        list_frist_level_configs=list_frist_level_configs,
                        add_frist_level=add_frist_level,
                        update_frist_level_trigger_type=update_frist_level_trigger_type,
                        update_frist_level_active=update_frist_level_active,
                        set_all_frist_levels_active=set_all_frist_levels_active,
                        update_frist_level_config=update_frist_level_config,
                        frist_trigger_options=frist_trigger_options,
                        delete_frist_level=delete_frist_level,
                        move_frist_level=move_frist_level,
                        list_work_packages=list_work_packages,
                        save_work_package=save_work_package,
                        delete_work_package=delete_work_package,
                        move_work_package=move_work_package,
                        list_vehicle_series_mappings=list_vehicle_series_mappings,
                        save_vehicle_series_mapping=save_vehicle_series_mapping,
                        delete_vehicle_series_mapping=delete_vehicle_series_mapping,
                        go_home=go_home,
                        go_series_overview=go_series_overview,
                        refresh=content.refresh,
                    )
                elif view == "users":
                    _render_user_management(
                        list_users=list_users,
                        save_user=save_user,
                        get_standard_access=get_standard_access,
                        save_standard_access=save_standard_access,
                        delete_user=delete_user,
                        user_permission_options=user_permission_options,
                        user_role_options=user_role_options,
                        go_home=go_home,
                        refresh=content.refresh,
                    )
                elif view == "gleisplan":
                    _render_gleisplan_config(
                        state=state,
                        db_exec=db_exec,
                        now_berlin=now_berlin,
                        go_home=go_home,
                        refresh=content.refresh,
                    )
                elif view == "werkstatthalle":
                    _render_workshop_hall_config(
                        db_exec=db_exec,
                        now_berlin=now_berlin,
                        workshop_areas=workshop_areas,
                        go_home=go_home,
                        refresh=content.refresh,
                    )
                else:
                    _render_home(
                        go_series_overview=go_series_overview,
                        go_gleisplan=go_gleisplan,
                        go_werkstatthalle=go_werkstatthalle,
                        go_users=go_users,
                    )

        content()


def _render_home(
    *,
    go_series_overview: Callable[[], None],
    go_gleisplan: Callable[[], None],
    go_werkstatthalle: Callable[[], None],
    go_users: Callable[[], None],
) -> None:
    _render_breadcrumb([("Konfiguration", None)])
    ui.button("Fahrzeuge", icon="directions_railway", on_click=go_series_overview).classes(
        "cfg-btn-open cfg-entry-button"
    )
    ui.button("Nutzer", icon="manage_accounts", on_click=go_users).classes("cfg-btn-open cfg-entry-button")
    ui.button("Werkstatthalle", icon="build", on_click=go_werkstatthalle).classes("cfg-btn-open cfg-entry-button")
    ui.button("Gleisplan", icon="route", on_click=go_gleisplan).classes("cfg-btn-open cfg-entry-button")
    ui.button("Planung", icon="event_note", on_click=lambda: ui.navigate.to("/konfiguration/planung")).classes(
        "cfg-btn-open cfg-entry-button"
    )


def _render_user_management(
    *,
    list_users: Callable[[], list[dict[str, Any]]],
    save_user: Callable[..., str],
    get_standard_access: Callable[[], dict[str, Any]],
    save_standard_access: Callable[..., str],
    delete_user: Callable[[str], bool],
    user_permission_options: Callable[[], dict[str, str]],
    user_role_options: Callable[[], dict[str, str]],
    go_home: Callable[[], None],
    refresh: Callable[[], None],
) -> None:
    users = list_users()
    standard_access = get_standard_access()
    role_options = user_role_options()
    permission_options = user_permission_options()
    _render_breadcrumb([("Konfiguration", go_home), ("Nutzer", None)])
    with ui.row().classes("cfg-action-row"):
        ui.button(
            "Nutzer hinzufügen",
            icon="person_add",
            on_click=lambda: _open_user_dialog(
                user=None,
                save_user=save_user,
                role_options=role_options,
                permission_options=permission_options,
                refresh=refresh,
            ),
        ).classes("cfg-btn-primary")

    with ui.column().classes("w-full gap-2"):
        with ui.row().classes("cfg-row-card items-center gap-3 no-wrap"):
            enabled_permissions = [
                label
                for key, label in permission_options.items()
                if bool((standard_access.get("permissions") or {}).get(key))
            ]
            status = "aktiv" if bool(standard_access.get("active", True)) else "deaktiviert"
            ui.label("Standard").classes("min-w-[180px] font-bold")
            ui.label("ohne Login").classes("min-w-[160px] cfg-subtle")
            ui.label(status).classes("cfg-subtle")
            ui.label(f"{len(enabled_permissions)} Rechte").classes("grow cfg-subtle")
            ui.button(
                "Bearbeiten",
                on_click=lambda: _open_standard_access_dialog(
                    standard_access=standard_access,
                    save_standard_access=save_standard_access,
                    permission_options=permission_options,
                    refresh=refresh,
                ),
            ).classes("cfg-btn-secondary")

        if not users:
            ui.label("Noch keine Login-Nutzer in der Datenbank angelegt.").classes("cfg-empty")

        for user in users:
            permissions = dict(user.get("permissions") or {})
            enabled_permissions = [label for key, label in permission_options.items() if bool(permissions.get(key))]
            with ui.row().classes("cfg-row-card items-center gap-3 no-wrap"):
                status = "aktiv" if bool(user.get("active", True)) else "deaktiviert"
                password_text = str(user.get("password_plain") or "").strip()
                ui.label(str(user.get("username") or "")).classes("min-w-[180px] font-bold")
                ui.label(str(user.get("role_label") or user.get("role") or "")).classes("cfg-pill")
                ui.label(f"Passwort: {password_text}" if password_text else "Passwort: nicht lesbar").classes("cfg-subtle")
                ui.label(status).classes("cfg-subtle")
                ui.label(f"{len(enabled_permissions)} Rechte").classes("grow cfg-subtle")
                ui.button(
                    "Bearbeiten",
                    on_click=lambda item=dict(user): _open_user_dialog(
                        user=item,
                        save_user=save_user,
                        role_options=role_options,
                        permission_options=permission_options,
                        refresh=refresh,
                    ),
                ).classes("cfg-btn-secondary")
                ui.button(
                    "Löschen",
                    on_click=lambda item=dict(user): _open_delete_user_dialog(
                        username=str(item.get("username") or ""),
                        delete_user=delete_user,
                        refresh=refresh,
                    ),
                ).classes("cfg-btn-danger")


def _open_user_dialog(
    *,
    user: dict[str, Any] | None,
    save_user: Callable[..., str],
    role_options: dict[str, str],
    permission_options: dict[str, str],
    refresh: Callable[[], None],
) -> None:
    edit = dict(user or {})
    permissions = dict(edit.get("permissions") or {})
    if not edit:
        permissions = {
            "view_home": True,
            "view_open_tasks": True,
            "view_werkstatthalle": True,
            "view_gleisplan": True,
            "view_priorisierung": True,
            "view_wochenplanung": True,
            "view_shopfloorboard": True,
        }
    with ui.dialog() as dialog, ui.card().classes("cfg-dialog-card"):
        ui.label("Nutzer bearbeiten" if edit else "Nutzer hinzufügen").classes("dialog-title")
        username_input = ui.input("Name", value=str(edit.get("username") or "")).props("outlined dense").classes("w-full")
        password_value = str(edit.get("password_plain") or "")
        password_input = ui.input(
            "Passwort",
            value=password_value,
        ).props("outlined dense").classes("w-full")
        if edit and not password_value:
            ui.label("Dieses Passwort liegt bisher nur als Hash vor. Leer lassen, um es unverändert zu behalten.").classes(
                "cfg-subtle"
            )
        role_select = ui.select(
            role_options,
            value=str(edit.get("role") or "standard"),
            label="Rolle",
        ).props(_select_props()).classes("w-full")
        active_checkbox = ui.checkbox("Aktiv", value=bool(edit.get("active", True))).props("dense")
        ui.label("Berechtigungen").classes("cfg-section-title")
        permission_controls: dict[str, Any] = {}
        with ui.element("div").classes("cfg-grid"):
            for key, label in permission_options.items():
                permission_controls[key] = ui.checkbox(label, value=bool(permissions.get(key, False))).props("dense")

        with ui.row().classes("w-full justify-end gap-2 mt-3"):
            ui.button("Abbrechen", on_click=dialog.close).classes("cfg-btn-secondary")

            def save() -> None:
                try:
                    selected_permissions = {key: bool(ctrl.value) for key, ctrl in permission_controls.items()}
                    save_user(
                        username=str(username_input.value or ""),
                        original_username=str(edit.get("username") or "") or None,
                        display_name=str(username_input.value or ""),
                        password=str(password_input.value or "") or None,
                        role=str(role_select.value or "standard"),
                        permissions=selected_permissions,
                        active=bool(active_checkbox.value),
                    )
                    ui.notify("Nutzer gespeichert.", type="positive")
                    dialog.close()
                    refresh()
                except Exception as ex:
                    ui.notify(f"Konnte Nutzer nicht speichern: {ex}", type="negative")

            ui.button("Speichern", on_click=save).classes("cfg-btn-primary")
    dialog.open()


def _open_standard_access_dialog(
    *,
    standard_access: dict[str, Any],
    save_standard_access: Callable[..., str],
    permission_options: dict[str, str],
    refresh: Callable[[], None],
) -> None:
    permissions = dict(standard_access.get("permissions") or {})
    with ui.dialog() as dialog, ui.card().classes("cfg-dialog-card"):
        ui.label("Standardzugriff ohne Login").classes("dialog-title")
        ui.label("Diese Rechte gelten für alle, die nicht angemeldet sind.").classes("cfg-subtle")
        active_checkbox = ui.checkbox("Aktiv", value=bool(standard_access.get("active", True))).props("dense")
        ui.label("Berechtigungen").classes("cfg-section-title")
        permission_controls: dict[str, Any] = {}
        with ui.element("div").classes("cfg-grid"):
            for key, label in permission_options.items():
                permission_controls[key] = ui.checkbox(label, value=bool(permissions.get(key, False))).props("dense")

        with ui.row().classes("w-full justify-end gap-2 mt-3"):
            ui.button("Abbrechen", on_click=dialog.close).classes("cfg-btn-secondary")

            def save() -> None:
                try:
                    selected_permissions = {key: bool(ctrl.value) for key, ctrl in permission_controls.items()}
                    save_standard_access(
                        permissions=selected_permissions,
                        active=bool(active_checkbox.value),
                    )
                    ui.notify("Standardzugriff gespeichert.", type="positive")
                    dialog.close()
                    refresh()
                except Exception as ex:
                    ui.notify(f"Konnte Standardzugriff nicht speichern: {ex}", type="negative")

            ui.button("Speichern", on_click=save).classes("cfg-btn-primary")
    dialog.open()


def _open_delete_user_dialog(
    *,
    username: str,
    delete_user: Callable[[str], bool],
    refresh: Callable[[], None],
) -> None:
    clean = str(username or "").strip()
    with ui.dialog() as dialog, ui.card().classes("cfg-dialog-card"):
        ui.label("Nutzer löschen").classes("dialog-title")
        ui.label(f"Soll der Nutzer {clean} wirklich gelöscht werden?").classes("cfg-subtle")
        with ui.row().classes("w-full justify-end gap-2 mt-3"):
            ui.button("Abbrechen", on_click=dialog.close).classes("cfg-btn-secondary")

            def confirm() -> None:
                if delete_user(clean):
                    ui.notify("Nutzer gelöscht.", type="positive")
                else:
                    ui.notify("Nutzer nicht gefunden.", type="warning")
                dialog.close()
                refresh()

            ui.button("Löschen", on_click=confirm).classes("cfg-btn-danger")
    dialog.open()


def _render_workshop_hall_config(
    *,
    db_exec: Callable[..., Any],
    now_berlin: Callable[[], datetime],
    workshop_areas: list[str],
    go_home: Callable[[], None],
    refresh: Callable[[], None],
) -> None:
    texts = load_workshop_hall_texts(db_exec)
    tiles = load_workshop_hall_tiles(db_exec)
    active_tiles = [tile for tile in tiles if bool(tile.get("active", True))]
    inactive_tiles = [tile for tile in tiles if not bool(tile.get("active", True))]
    area_options = {"": "Kein Arbeitsplatz"}
    for area in workshop_areas:
        area_key = str(area or "").strip().upper()
        if area_key:
            area_options[area_key] = area_key

    _render_breadcrumb([("Konfiguration", go_home), ("Werkstatthalle", None)])

    def tile_type_label(tile: dict[str, Any]) -> str:
        return str(WORKSHOP_TILE_TYPE_OPTIONS.get(str(tile.get("tile_type") or "area"), "Arbeitsplatz-Kachel"))

    def tile_content_label(tile: dict[str, Any]) -> str:
        if str(tile.get("tile_type") or "").strip().lower() == "due_soon":
            return "Inhalt: unzugeordnete Aufträge, die in 24 Stunden fällig werden"
        area = str(tile.get("content_area") or "").strip().upper()
        return f"Inhalt: Arbeitsplatz {area or '-'}"

    def set_tile_active(tile: dict[str, Any], active: bool) -> None:
        ok, msg = save_workshop_hall_tile(
            db_exec,
            tile_key=str(tile.get("tile_key") or ""),
            tile_type=str(tile.get("tile_type") or "area"),
            display_label=str(tile.get("display_label") or ""),
            content_area=str(tile.get("content_area") or ""),
            active=bool(active),
            highlighted=bool(tile.get("highlighted", True)),
            sort_order=int(tile.get("sort_order") or 0),
            updated_at=now_berlin().isoformat(timespec="seconds"),
        )
        ui.notify(msg, type="positive" if ok else "negative")
        if ok:
            refresh()

    def drop_tile(event, target_key: str) -> None:
        args = event.args or {}
        source_key = str(args.get("source") if isinstance(args, dict) else "").strip().upper()
        target = str(target_key or "").strip().upper()
        placement = str(args.get("placement") if isinstance(args, dict) else "before").strip().lower()
        active_keys = [str(tile.get("tile_key") or "").strip().upper() for tile in active_tiles]
        active_keys = [key for key in active_keys if key]
        if not source_key or source_key == target or source_key not in active_keys or target not in active_keys:
            return
        active_keys.remove(source_key)
        insert_index = active_keys.index(target) + (1 if placement == "after" else 0)
        active_keys.insert(insert_index, source_key)
        inactive_keys = [str(tile.get("tile_key") or "").strip().upper() for tile in inactive_tiles]
        reorder_workshop_hall_tiles(
            db_exec,
            tile_keys=active_keys + [key for key in inactive_keys if key and key not in active_keys],
            updated_at=now_berlin().isoformat(timespec="seconds"),
        )
        ui.notify("Kachel verschoben.", type="positive")
        refresh()

    def move_tile(tile_key: str, direction: int) -> None:
        active_keys = [str(tile.get("tile_key") or "").strip().upper() for tile in active_tiles]
        active_keys = [key for key in active_keys if key]
        key = str(tile_key or "").strip().upper()
        if key not in active_keys:
            return
        source_index = active_keys.index(key)
        target_index = source_index + int(direction)
        if target_index < 0 or target_index >= len(active_keys):
            return
        active_keys[source_index], active_keys[target_index] = active_keys[target_index], active_keys[source_index]
        inactive_keys = [str(tile.get("tile_key") or "").strip().upper() for tile in inactive_tiles]
        reorder_workshop_hall_tiles(
            db_exec,
            tile_keys=active_keys + [inactive_key for inactive_key in inactive_keys if inactive_key],
            updated_at=now_berlin().isoformat(timespec="seconds"),
        )
        ui.notify("Kachel verschoben.", type="positive")
        refresh()

    with ui.row().classes("cfg-action-row"):
        next_sort = max([int(tile.get("sort_order") or 0) for tile in tiles] or [0]) + 10
        ui.button(
            "Kachel hinzufügen",
            icon="add",
            on_click=lambda: _open_workshop_tile_dialog(
                db_exec=db_exec,
                now_berlin=now_berlin,
                area_options=area_options,
                refresh=refresh,
                sort_order=next_sort,
            ),
        ).classes("cfg-btn-primary")

        def reset_config() -> None:
            reset_workshop_hall_config(
                db_exec,
                updated_at=now_berlin().isoformat(timespec="seconds"),
            )
            ui.notify("Werkstatthalle-Konfiguration zurückgesetzt.", type="positive")
            refresh()

        ui.button("Standard wiederherstellen", icon="restart_alt", on_click=reset_config).classes("cfg-btn-secondary")

    with ui.element("section").classes("cfg-panel"):
        ui.label("Kachel-Layout").classes("cfg-section-title")
        ui.label("Diese Vorschau entspricht der Reihenfolge auf der Seite Werkstatthalle. Kacheln ziehen, um sie zu verschieben.").classes(
            "cfg-subtle"
        )
        if not active_tiles:
            ui.label("Keine aktiven Kacheln konfiguriert.").classes("cfg-empty")
        else:
            with ui.element("div").classes("cfg-workshop-layout-preview mt-3"):
                for index, tile in enumerate(active_tiles):
                    tile_key = str(tile.get("tile_key") or "").strip().upper()
                    classes = "cfg-workshop-tile"
                    if not bool(tile.get("highlighted", True)):
                        classes += " cfg-workshop-tile-muted"
                    with ui.element("div").classes(classes).props("draggable=true") as tile_el:
                        tile_el.on(
                            "dragstart",
                            js_handler=f"(event) => event.dataTransfer.setData('text/plain', {tile_key!r})",
                        )
                        tile_el.on("dragover", js_handler=_drag_over_tile_js())
                        tile_el.on("dragleave", js_handler=_drag_clear_tile_js())
                        tile_el.on("dragend", js_handler=_drag_clear_tile_js())
                        tile_el.on(
                            "drop",
                            lambda event, target=tile_key: drop_tile(event, target),
                            js_handler=_drop_emit_tile_js(),
                        )
                        with ui.row().classes("w-full items-center justify-between gap-2"):
                            ui.label(f"Position {index + 1}").classes("cfg-mini-label")
                            ui.icon("drag_indicator").classes("cfg-workshop-drag-icon")
                        ui.label(str(tile.get("display_label") or tile_key)).classes("cfg-workshop-tile-title")
                        ui.label(tile_content_label(tile)).classes("cfg-workshop-tile-meta")
                        with ui.row().classes("w-full gap-2 mt-2 wrap"):
                            left_btn = ui.button(
                                "Links",
                                icon="keyboard_arrow_left",
                                on_click=lambda key=tile_key: move_tile(key, -1),
                            ).classes("cfg-btn-secondary")
                            if index <= 0:
                                left_btn.disable()
                            right_btn = ui.button(
                                "Rechts",
                                icon="keyboard_arrow_right",
                                on_click=lambda key=tile_key: move_tile(key, 1),
                            ).classes("cfg-btn-secondary")
                            if index >= len(active_tiles) - 1:
                                right_btn.disable()
                            ui.button(
                                "Bearbeiten",
                                icon="edit",
                                on_click=lambda current=dict(tile): _open_workshop_tile_dialog(
                                    db_exec=db_exec,
                                    now_berlin=now_berlin,
                                    area_options=area_options,
                                    refresh=refresh,
                                    tile=current,
                                ),
                            ).classes("cfg-btn-secondary grow")
                            ui.button(
                                "Ausblenden",
                                icon="visibility_off",
                                on_click=lambda current=dict(tile): set_tile_active(current, False),
                            ).classes("cfg-btn-secondary grow")

        if inactive_tiles:
            ui.label("Ausgeblendete Kacheln").classes("cfg-section-title mt-4")
            with ui.column().classes("w-full gap-2 mt-2"):
                for tile in inactive_tiles:
                    tile_key = str(tile.get("tile_key") or "").strip().upper()
                    with ui.element("div").classes("cfg-row-card"):
                        with ui.row().classes("w-full items-center gap-3 wrap"):
                            ui.label(tile_key).classes("cfg-pill")
                            ui.label(str(tile.get("display_label") or tile_key)).classes("font-bold")
                            ui.label(tile_content_label(tile)).classes("grow cfg-subtle")
                            ui.button(
                                "Bearbeiten",
                                icon="edit",
                                on_click=lambda current=dict(tile): _open_workshop_tile_dialog(
                                    db_exec=db_exec,
                                    now_berlin=now_berlin,
                                    area_options=area_options,
                                    refresh=refresh,
                                    tile=current,
                                ),
                            ).classes("cfg-btn-secondary")
                            ui.button(
                                "Einblenden",
                                icon="visibility",
                                on_click=lambda current=dict(tile): set_tile_active(current, True),
                            ).classes("cfg-btn-primary")

    with ui.element("section").classes("cfg-panel"):
        ui.label("Texte").classes("cfg-section-title")
        ui.label("Diese Texte erscheinen direkt in der Werkstatthalle.").classes("cfg-subtle")
        text_controls: dict[str, Any] = {}
        with ui.element("div").classes("cfg-grid mt-3"):
            for key, label in WORKSHOP_TEXT_FIELDS:
                text_controls[key] = ui.input(label, value=str(texts.get(key) or "")).props("outlined dense").classes(
                    "w-full"
                )

        def save_texts() -> None:
            save_workshop_hall_texts(
                db_exec,
                texts={key: str(ctrl.value or "") for key, ctrl in text_controls.items()},
                updated_at=now_berlin().isoformat(timespec="seconds"),
            )
            ui.notify("Werkstatthalle-Texte gespeichert.", type="positive")
            refresh()

        with ui.row().classes("w-full justify-end mt-3"):
            ui.button("Texte speichern", icon="save", on_click=save_texts).classes("cfg-btn-primary")

def _open_workshop_tile_dialog(
    *,
    db_exec: Callable[..., Any],
    now_berlin: Callable[[], datetime],
    area_options: dict[str, str],
    refresh: Callable[[], None],
    tile: dict[str, Any] | None = None,
    sort_order: int = 100,
) -> None:
    edit = dict(tile or {})
    is_edit = bool(edit)
    tile_key = str(edit.get("tile_key") or "").strip().upper()
    with ui.dialog() as dialog, ui.card().classes("cfg-dialog-card"):
        ui.label("Werkstatthalle-Kachel bearbeiten" if is_edit else "Werkstatthalle-Kachel hinzufügen").classes(
            "dialog-title"
        )
        key_props = "outlined dense readonly" if is_edit else "outlined dense"
        key_input = ui.input("Kachel-Code", value=tile_key).props(key_props).classes("w-full")
        label_input = ui.input("Kachel-Titel", value=str(edit.get("display_label") or "")).props("outlined dense").classes("w-full")
        type_select = ui.select(
            WORKSHOP_TILE_TYPE_OPTIONS,
            value=str(edit.get("tile_type") or "area"),
            label="Typ",
        ).props(_select_props()).classes("w-full")
        area_select = ui.select(
            area_options,
            value=str(edit.get("content_area") or ""),
            label="Inhaltsbezug",
        ).props(_select_props()).classes("w-full")
        sort_input = ui.number(
            "Reihenfolge",
            value=int(edit.get("sort_order") or sort_order),
            format="%d",
        ).props("outlined dense").classes("w-full")
        active_checkbox = ui.checkbox("Aktiv", value=bool(edit.get("active", True))).props("dense")
        highlighted_checkbox = ui.checkbox("Hervorgehoben", value=bool(edit.get("highlighted", True))).props("dense")

        with ui.row().classes("w-full justify-end gap-2 mt-3"):
            ui.button("Abbrechen", on_click=dialog.close).classes("cfg-btn-secondary")

            def save() -> None:
                ok, msg = save_workshop_hall_tile(
                    db_exec,
                    tile_key=tile_key if is_edit else str(key_input.value or ""),
                    tile_type=str(type_select.value or "area"),
                    display_label=str(label_input.value or ""),
                    content_area=str(area_select.value or ""),
                    active=bool(active_checkbox.value),
                    highlighted=bool(highlighted_checkbox.value),
                    sort_order=int(sort_input.value or 0),
                    updated_at=now_berlin().isoformat(timespec="seconds"),
                )
                ui.notify(msg, type="positive" if ok else "negative")
                if ok:
                    dialog.close()
                    refresh()

            ui.button("Speichern", icon="save", on_click=save).classes("cfg-btn-primary")
    dialog.open()


def _layout_item_style(item: dict[str, Any]) -> str:
    return (
        f"left:{float(item.get('x_pct') or 0):.3f}%;"
        f"top:{float(item.get('y_pct') or 0):.3f}%;"
        f"width:{float(item.get('w_pct') or 10):.3f}%;"
        f"height:{float(item.get('h_pct') or 8):.3f}%;"
        f"transform:rotate({float(item.get('rotation') or 0):.3f}deg);"
        f"--layout-color:{str(item.get('color') or '').strip() or '#dc2626'};"
        f"--curve-radius:{float(item.get('curve_radius') or 0):.3f}%;"
    )


def _switch_ratio(item: dict[str, Any], key: str, default: float) -> float:
    try:
        value = float(item.get(key))
    except Exception:
        value = float(default)
    return max(-2.0, min(3.0, value))


def _switch_local_geometry(item: dict[str, Any]) -> dict[str, tuple[float, float]]:
    port1 = (1.0, SWITCH_MAIN_RAIL_Y_RATIO)
    port2 = (
        _switch_ratio(item, "switch_port2_x_ratio", 0.0),
        _switch_ratio(item, "switch_port2_y_ratio", SWITCH_MAIN_RAIL_Y_RATIO),
    )
    heel = (
        port2[0] + ((port1[0] - port2[0]) * SWITCH_BRANCH_HEEL_X_RATIO),
        port2[1] + ((port1[1] - port2[1]) * SWITCH_BRANCH_HEEL_X_RATIO),
    )
    port3 = (
        _switch_ratio(item, "switch_port3_x_ratio", SWITCH_BRANCH_PORT_X_RATIO),
        _switch_ratio(item, "switch_port3_y_ratio", SWITCH_BRANCH_PORT_Y_RATIO),
    )
    return {"port1": port1, "port2": port2, "heel": heel, "port3": port3}


def _switch_port_label_style(item: dict[str, Any], port: str) -> str:
    geometry = _switch_local_geometry(item)
    point = geometry.get(f"port{port}") or geometry["port1"]
    return (
        f"left:calc({point[0] * 100:.3f}% - 6px);"
        f"top:calc({point[1] * 100:.3f}% - 6px);right:auto;bottom:auto;"
    )


def _switch_anchor_debug_style(item: dict[str, Any], anchor: str) -> str:
    port_by_anchor = {"straight": "1", "stem": "2", "branch": "3"}
    point = _switch_local_geometry(item).get(f"port{port_by_anchor.get(str(anchor), '1')}") or _switch_local_geometry(item)["port1"]
    return (
        f"left:calc({point[0] * 100:.3f}% - 5px);"
        f"top:calc({point[1] * 100:.3f}% - 5px);"
    )


def _switch_svg_markup(item: dict[str, Any]) -> str:
    geometry = _switch_local_geometry(item)
    p1 = geometry["port1"]
    p2 = geometry["port2"]
    p3 = geometry["port3"]
    heel = geometry["heel"]
    return (
        '<svg class="gleisplan-switch-svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">'
        f'<line class="gleisplan-switch-svg-rail gleisplan-switch-main-line" '
        f'x1="{p2[0] * 100:.3f}" y1="{p2[1] * 100:.3f}" x2="{p1[0] * 100:.3f}" y2="{p1[1] * 100:.3f}"></line>'
        f'<line class="gleisplan-switch-svg-rail gleisplan-switch-branch-line" '
        f'x1="{p3[0] * 100:.3f}" y1="{p3[1] * 100:.3f}" x2="{heel[0] * 100:.3f}" y2="{heel[1] * 100:.3f}"></line>'
        "</svg>"
    )


def _connection_style(connection: dict[str, Any]) -> str:
    return (
        f"left:{float(connection.get('x_pct') or 0):.3f}%;"
        f"top:{float(connection.get('y_pct') or 0):.3f}%;"
        f"width:{float(connection.get('length_pct') or 0):.3f}%;"
        f"transform:translateY(-50%) rotate({float(connection.get('rotation') or 0):.3f}deg);"
    )


def _route_points(route: dict[str, Any] | None) -> list[tuple[float, float]]:
    if not isinstance(route, dict):
        return []
    points: list[tuple[float, float]] = []
    for point in route.get("points") or []:
        if not isinstance(point, dict):
            continue
        try:
            points.append((float(point.get("x_pct", point.get("x"))), float(point.get("y_pct", point.get("y")))))
        except Exception:
            continue
    if len(points) >= 2:
        return points
    start = route.get("start") if isinstance(route.get("start"), dict) else None
    end = route.get("end") if isinstance(route.get("end"), dict) else None
    if not start or not end:
        return points
    try:
        return [
            (float(start.get("x_pct", start.get("x"))), float(start.get("y_pct", start.get("y")))),
            (float(end.get("x_pct", end.get("x"))), float(end.get("y_pct", end.get("y")))),
        ]
    except Exception:
        return points


def _route_path_d(route: dict[str, Any] | None) -> str:
    if not isinstance(route, dict):
        return ""
    route_type = str(route.get("type") or "").strip().lower()
    d = str(route.get("d") or "").strip()
    if route_type == "path" and d:
        return d
    points = _route_points(route)
    if len(points) < 2:
        return ""
    if route.get("smooth") and len(points) > 2:
        return _catmull_connection_path_d(points)
    return " ".join(
        [f"M {points[0][0]:.3f} {points[0][1]:.3f}"]
        + [f"L {x:.3f} {y:.3f}" for x, y in points[1:]]
    )


def _route_point_at(route: dict[str, Any] | None, t: float) -> tuple[float, float]:
    points = _route_points(route)
    if not points:
        return 0.0, 0.0
    if len(points) == 1:
        return points[0]
    clean_t = max(0.0, min(1.0, float(t)))
    lengths: list[float] = []
    total = 0.0
    for start, end in zip(points, points[1:]):
        length = math.sqrt(((end[0] - start[0]) ** 2) + ((end[1] - start[1]) ** 2))
        lengths.append(length)
        total += length
    if total <= 0.000001:
        return points[0]
    target = clean_t * total
    walked = 0.0
    for index, length in enumerate(lengths):
        start = points[index]
        end = points[index + 1]
        if walked + length >= target or index == len(lengths) - 1:
            local_t = 0.0 if length <= 0.000001 else (target - walked) / length
            return (
                start[0] + ((end[0] - start[0]) * local_t),
                start[1] + ((end[1] - start[1]) * local_t),
            )
        walked += length
    return points[-1]


def _connection_path_points(connection: dict[str, Any]) -> list[tuple[float, float]]:
    x1 = float(connection.get("x_pct") or 0)
    y1 = float(connection.get("y_pct") or 0)
    x2 = float(connection.get("x2_pct") if connection.get("x2_pct") is not None else x1)
    y2 = float(connection.get("y2_pct") if connection.get("y2_pct") is not None else y1)
    points = [(x1, y1)]
    if connection.get("source_lead_x_pct") is not None and connection.get("source_lead_y_pct") is not None:
        points.append((float(connection.get("source_lead_x_pct") or 0), float(connection.get("source_lead_y_pct") or 0)))
    for point in connection.get("path_points") or []:
        if not isinstance(point, dict):
            continue
        points.append((float(point.get("x_pct") or 0), float(point.get("y_pct") or 0)))
    if connection.get("target_lead_x_pct") is not None and connection.get("target_lead_y_pct") is not None:
        points.append((float(connection.get("target_lead_x_pct") or 0), float(connection.get("target_lead_y_pct") or 0)))
    points.append((x2, y2))
    return points


def _catmull_connection_path_d(points: list[tuple[float, float]]) -> str:
    if not points:
        return ""
    if len(points) == 1:
        return f"M {points[0][0]:.3f} {points[0][1]:.3f}"
    if len(points) == 2:
        return f"M {points[0][0]:.3f} {points[0][1]:.3f} L {points[1][0]:.3f} {points[1][1]:.3f}"
    parts = [f"M {points[0][0]:.3f} {points[0][1]:.3f}"]
    for index in range(len(points) - 1):
        p0 = points[index - 1] if index > 0 else points[index]
        p1 = points[index]
        p2 = points[index + 1]
        p3 = points[index + 2] if index + 2 < len(points) else p2
        c1x = p1[0] + ((p2[0] - p0[0]) / 6.0)
        c1y = p1[1] + ((p2[1] - p0[1]) / 6.0)
        c2x = p2[0] - ((p3[0] - p1[0]) / 6.0)
        c2y = p2[1] - ((p3[1] - p1[1]) / 6.0)
        parts.append(f"C {c1x:.3f} {c1y:.3f} {c2x:.3f} {c2y:.3f} {p2[0]:.3f} {p2[1]:.3f}")
    return " ".join(parts)


def _catmull_connection_point(points: list[tuple[float, float]], t: float) -> tuple[float, float]:
    if not points:
        return 0.0, 0.0
    if len(points) == 1:
        return points[0]
    clean_t = max(0.0, min(1.0, float(t)))
    segments = len(points) - 1
    raw_index = clean_t * segments
    index = min(segments - 1, int(math.floor(raw_index)))
    local_t = raw_index - index
    p0 = points[index - 1] if index > 0 else points[index]
    p1 = points[index]
    p2 = points[index + 1]
    p3 = points[index + 2] if index + 2 < len(points) else p2
    tt = local_t * local_t
    ttt = tt * local_t
    return (
        0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * local_t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * tt + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * ttt),
        0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * local_t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * tt + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * ttt),
    )


def _connection_path_d(connection: dict[str, Any]) -> str:
    route_d = _route_path_d(connection.get("route"))
    if route_d:
        return route_d
    path_points = connection.get("path_points") or []
    has_lead = (
        connection.get("source_lead_x_pct") is not None
        or connection.get("target_lead_x_pct") is not None
    )
    if path_points or has_lead:
        return _catmull_connection_path_d(_connection_path_points(connection))
    x1 = float(connection.get("x_pct") or 0)
    y1 = float(connection.get("y_pct") or 0)
    x2 = float(connection.get("x2_pct") if connection.get("x2_pct") is not None else x1)
    y2 = float(connection.get("y2_pct") if connection.get("y2_pct") is not None else y1)
    cx = float(connection.get("control_x_pct") if connection.get("control_x_pct") is not None else (x1 + x2) / 2)
    cy = float(connection.get("control_y_pct") if connection.get("control_y_pct") is not None else (y1 + y2) / 2)
    if abs(float(connection.get("curve_pct") or 0)) < 0.001:
        return f"M {x1:.3f} {y1:.3f} L {x2:.3f} {y2:.3f}"
    return f"M {x1:.3f} {y1:.3f} Q {cx:.3f} {cy:.3f} {x2:.3f} {y2:.3f}"


def _connection_label_style(connection: dict[str, Any]) -> str:
    return (
        f"left:{float(connection.get('label_x_pct') or connection.get('x_pct') or 0):.3f}%;"
        f"top:{float(connection.get('label_y_pct') or connection.get('y_pct') or 0):.3f}%;"
    )


def _connection_handle_style(connection: dict[str, Any]) -> str:
    return (
        f"left:{float(connection.get('control_x_pct') or connection.get('x_pct') or 0):.3f}%;"
        f"top:{float(connection.get('control_y_pct') or connection.get('y_pct') or 0):.3f}%;"
    )


def _connection_path_point_style(point: dict[str, Any]) -> str:
    return (
        f"left:{float(point.get('x_pct') or 0):.3f}%;"
        f"top:{float(point.get('y_pct') or 0):.3f}%;"
    )


def _connection_route_points_for_edit(connection: dict[str, Any]) -> list[dict[str, Any]]:
    route = connection.get("route") or {}
    if not isinstance(route, dict):
        return []
    points: list[dict[str, Any]] = []
    for point in route.get("points") or []:
        if not isinstance(point, dict):
            continue
        if point.get("x_pct") is None or point.get("y_pct") is None:
            continue
        points.append(
            {
                "x": float(point.get("x_pct") or 0),
                "y": float(point.get("y_pct") or 0),
                "anchor": str(point.get("anchor") or "").strip(),
                "name": str(point.get("name") or "").strip(),
            }
        )
    return points


def _connection_editable_route_point_indices(connection: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    route = connection.get("route") or {}
    if not isinstance(route, dict):
        return []
    out: list[tuple[int, dict[str, Any]]] = []
    for index, point in enumerate(route.get("points") or []):
        if not isinstance(point, dict):
            continue
        if str(point.get("anchor") or "").strip().lower() in {"from", "to"}:
            continue
        if point.get("x_pct") is None or point.get("y_pct") is None:
            continue
        out.append((index, point))
    return out


def _connection_chord_style(connection: dict[str, Any]) -> str:
    return (
        f"left:{float(connection.get('x_pct') or 0):.3f}%;"
        f"top:{float(connection.get('y_pct') or 0):.3f}%;"
        f"width:{float(connection.get('length_pct') or 0):.3f}%;"
        f"transform:translateY(-50%) rotate({float(connection.get('rotation') or 0):.3f}deg);"
    )


def _connection_point_at(connection: dict[str, Any], t: float) -> tuple[float, float]:
    if connection.get("route"):
        return _route_point_at(connection.get("route"), t)
    path_points = connection.get("path_points") or []
    if path_points:
        return _catmull_connection_point(_connection_path_points(connection), t)
    x1 = float(connection.get("x_pct") or 0)
    y1 = float(connection.get("y_pct") or 0)
    x2 = float(connection.get("x2_pct") if connection.get("x2_pct") is not None else x1)
    y2 = float(connection.get("y2_pct") if connection.get("y2_pct") is not None else y1)
    cx = float(connection.get("control_x_pct") if connection.get("control_x_pct") is not None else (x1 + x2) / 2)
    cy = float(connection.get("control_y_pct") if connection.get("control_y_pct") is not None else (y1 + y2) / 2)
    clean_t = max(0.0, min(1.0, float(t)))
    if abs(float(connection.get("curve_pct") or 0)) < 0.001:
        return x1 + ((x2 - x1) * clean_t), y1 + ((y2 - y1) * clean_t)
    inv = 1.0 - clean_t
    return (
        (inv * inv * x1) + (2.0 * inv * clean_t * cx) + (clean_t * clean_t * x2),
        (inv * inv * y1) + (2.0 * inv * clean_t * cy) + (clean_t * clean_t * y2),
    )


def _connection_hitbox_segment_styles(connection: dict[str, Any], *, segments: int = 7) -> list[str]:
    out: list[str] = []
    segment_count = max(1, int(segments or 1))
    for index in range(segment_count):
        x1, y1 = _connection_point_at(connection, index / segment_count)
        x2, y2 = _connection_point_at(connection, (index + 1) / segment_count)
        dx = x2 - x1
        dy = y2 - y1
        visual_dy = dy / GLEISPLAN_BOARD_ASPECT
        length = math.sqrt((dx * dx) + (visual_dy * visual_dy))
        if length <= 0.05:
            continue
        rotation = math.degrees(math.atan2(visual_dy, dx))
        out.append(
            f"left:{x1:.3f}%;top:{y1:.3f}%;width:{length:.3f}%;"
            f"transform:translateY(-50%) rotate({rotation:.3f}deg);"
        )
    return out


def _item_type_label(item_type: Any) -> str:
    labels = {
        "anchor": "Verbindungspunkt",
        "track": "Verbindungspunkt",
        "hall": "Halle",
        "building": "Gebaeude",
        "street": "Strasse",
        "switch": "Weiche",
        "buffer_stop": "Prellbock",
    }
    return labels.get(str(item_type or "").strip().lower(), str(item_type or ""))


def _connected_connection_drag_payload(item_id: str, connections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clean_id = str(item_id or "").strip().upper()
    out: list[dict[str, Any]] = []
    for connection in connections:
        source_id = str(connection.get("source_item_id") or "").strip().upper()
        target_id = str(connection.get("target_item_id") or "").strip().upper()
        if clean_id not in {source_id, target_id}:
            continue
        route = connection.get("route") or {}
        out.append(
            {
                "id": int(connection.get("id") or 0),
                "source": source_id,
                "target": target_id,
                "fixedRoute": bool(connection.get("route")),
                "routeSmooth": bool(route.get("smooth")),
                "routePoints": [
                    {
                        "x": float(point.get("x_pct") or 0),
                        "y": float(point.get("y_pct") or 0),
                        "anchor": str(point.get("anchor") or "").strip(),
                        "name": str(point.get("name") or "").strip(),
                        "dx": float(point.get("dx_pct") or 0),
                        "dy": float(point.get("dy_pct") or 0),
                    }
                    for point in (route.get("points") or [])
                    if isinstance(point, dict) and point.get("x_pct") is not None and point.get("y_pct") is not None
                ],
                "sourcePort": str(connection.get("source_port") or "").strip(),
                "targetPort": str(connection.get("target_port") or "").strip(),
                "x1": float(connection.get("x_pct") or 0),
                "y1": float(connection.get("y_pct") or 0),
                "x2": float(connection.get("x2_pct") if connection.get("x2_pct") is not None else connection.get("x_pct") or 0),
                "y2": float(connection.get("y2_pct") if connection.get("y2_pct") is not None else connection.get("y_pct") or 0),
                "sourceLead": (
                    {
                        "x": float(connection.get("source_lead_x_pct") or 0),
                        "y": float(connection.get("source_lead_y_pct") or 0),
                    }
                    if connection.get("source_lead_x_pct") is not None and connection.get("source_lead_y_pct") is not None
                    else None
                ),
                "targetLead": (
                    {
                        "x": float(connection.get("target_lead_x_pct") or 0),
                        "y": float(connection.get("target_lead_y_pct") or 0),
                    }
                    if connection.get("target_lead_x_pct") is not None and connection.get("target_lead_y_pct") is not None
                    else None
                ),
                "curve": float(connection.get("curve_pct") or 0),
                "pathPoints": [
                    {"x": float(point.get("x_pct") or 0), "y": float(point.get("y_pct") or 0)}
                    for point in (connection.get("path_points") or [])
                    if isinstance(point, dict)
                ],
            }
        )
    return out


def _drag_item_js_handler(
    item_id: str,
    connections: list[dict[str, Any]] | None = None,
    *,
    item_type: str = "",
    connectable: bool = False,
) -> str:
    connection_payload = _connected_connection_drag_payload(item_id, connections or [])
    clean_item_type = str(item_type or "").strip().lower()
    return (
        "(event) => {"
        "if (event.button !== 0) return;"
        "const el = event.currentTarget;"
        "const board = el.closest('.gleisplan-editor-board');"
        "if (!board) return;"
        "if ((event.detail || 0) > 1) {"
        "event.preventDefault();"
        "event.stopPropagation();"
        "el.dataset.gleisplanEditOpening = String(Date.now());"
        f"emit({{item_id: {item_id!r}, mode: 'edit'}});"
        "return;"
        "}"
        "event.preventDefault();"
        "event.stopPropagation();"
        "const rect = board.getBoundingClientRect();"
        "try { el.setPointerCapture(event.pointerId); } catch (_err) {}"
        "const boxWidthPct = ((el.offsetWidth || el.getBoundingClientRect().width) / rect.width) * 100;"
        "const boxHeightPct = ((el.offsetHeight || el.getBoundingClientRect().height) / rect.height) * 100;"
        "const maxX = Math.max(0, 100 - boxWidthPct);"
        "const maxY = Math.max(0, 100 - boxHeightPct);"
        "const startClientX = event.clientX;"
        "const startClientY = event.clientY;"
        "const styleStartX = Number.parseFloat(String(el.style.left || ''));"
        "const styleStartY = Number.parseFloat(String(el.style.top || ''));"
        "const startX = Number.isFinite(styleStartX) ? styleStartX : ((el.offsetLeft || 0) / rect.width) * 100;"
        "const startY = Number.isFinite(styleStartY) ? styleStartY : ((el.offsetTop || 0) / rect.height) * 100;"
        f"const draggedItemId = {str(item_id or '').strip().upper()!r};"
        f"const draggedItemType = {clean_item_type!r};"
        f"const isConnectable = {'true' if connectable else 'false'};"
        f"const connectedConnections = {json.dumps(connection_payload, ensure_ascii=True)};"
        "const pendingKey = `gleisplan.pendingPosition.${draggedItemId}`;"
        "const rememberPendingPosition = (x, y) => {"
        "try { window.localStorage.setItem(pendingKey, JSON.stringify({x:x, y:y, t:Date.now()})); } catch (_err) {}"
        "};"
        "const readPct = (value, fallback) => { const parsed = Number.parseFloat(String(value || '')); return Number.isFinite(parsed) ? parsed : fallback; };"
        "const localPointToBoard = (itemX, itemY, itemW, itemH, rotationDeg, localX, localY) => {"
        "const angle = (rotationDeg || 0) * Math.PI / 180;"
        "const cx = itemX + (itemW / 2);"
        "const cy = itemY + (itemH / 2);"
        "const scaleX = rect.width / 100;"
        "const scaleY = rect.height / 100;"
        "const dx = (localX - (itemW / 2)) * scaleX;"
        "const dy = (localY - (itemH / 2)) * scaleY;"
        "const rotatedX = (dx * Math.cos(angle)) - (dy * Math.sin(angle));"
        "const rotatedY = (dx * Math.sin(angle)) + (dy * Math.cos(angle));"
        "return {x: cx + (rotatedX / scaleX), y: cy + (rotatedY / scaleY)};"
        "};"
        "const shiftedSwitchPoint = (itemX, itemY, itemW, itemH, rotationDeg, port) => {"
        "const cleanPort = String(port || '1');"
        "let selected;"
        "let opposite;"
        "const port1 = {x: itemW, y: itemH * 0.28};"
        "const port2 = {x: itemW * readPct(el.dataset.switchPort2X, 0), y: itemH * readPct(el.dataset.switchPort2Y, 0.28)};"
        "const heel = {x: port2.x + ((port1.x - port2.x) * 0.80), y: port2.y + ((port1.y - port2.y) * 0.80)};"
        "const port3 = {x: itemW * readPct(el.dataset.switchPort3X, 0.06), y: itemH * readPct(el.dataset.switchPort3Y, 1.35)};"
        "if (cleanPort === '2') {"
        "selected = localPointToBoard(itemX, itemY, itemW, itemH, rotationDeg, port2.x, port2.y);"
        "opposite = localPointToBoard(itemX, itemY, itemW, itemH, rotationDeg, port1.x, port1.y);"
        "} else if (cleanPort === '3') {"
        "selected = localPointToBoard(itemX, itemY, itemW, itemH, rotationDeg, port3.x, port3.y);"
        "opposite = localPointToBoard(itemX, itemY, itemW, itemH, rotationDeg, heel.x, heel.y);"
        "} else {"
        "selected = localPointToBoard(itemX, itemY, itemW, itemH, rotationDeg, port1.x, port1.y);"
        "opposite = localPointToBoard(itemX, itemY, itemW, itemH, rotationDeg, port2.x, port2.y);"
        "}"
        "return selected;"
        "};"
        "const switchLeadPoint = (itemX, itemY, itemW, itemH, rotationDeg, port) => {"
        "const cleanPort = String(port || '1');"
        "let selected;"
        "let opposite;"
        "const port1 = {x: itemW, y: itemH * 0.28};"
        "const port2 = {x: itemW * readPct(el.dataset.switchPort2X, 0), y: itemH * readPct(el.dataset.switchPort2Y, 0.28)};"
        "const heel = {x: port2.x + ((port1.x - port2.x) * 0.80), y: port2.y + ((port1.y - port2.y) * 0.80)};"
        "const port3 = {x: itemW * readPct(el.dataset.switchPort3X, 0.06), y: itemH * readPct(el.dataset.switchPort3Y, 1.35)};"
        "if (cleanPort === '2') {"
        "selected = localPointToBoard(itemX, itemY, itemW, itemH, rotationDeg, port2.x, port2.y);"
        "opposite = localPointToBoard(itemX, itemY, itemW, itemH, rotationDeg, port1.x, port1.y);"
        "} else if (cleanPort === '3') {"
        "selected = localPointToBoard(itemX, itemY, itemW, itemH, rotationDeg, port3.x, port3.y);"
        "opposite = localPointToBoard(itemX, itemY, itemW, itemH, rotationDeg, heel.x, heel.y);"
        "} else {"
        "selected = localPointToBoard(itemX, itemY, itemW, itemH, rotationDeg, port1.x, port1.y);"
        "opposite = localPointToBoard(itemX, itemY, itemW, itemH, rotationDeg, port2.x, port2.y);"
        "}"
        "const dx = selected.x - opposite.x;"
        "const dy = selected.y - opposite.y;"
        "const length = Math.sqrt((dx * dx) + (dy * dy)) || 0;"
        "if (length <= 0.000001) return null;"
        "const lead = Math.min(1.35, length * 0.42);"
        "return {x: selected.x + ((dx / length) * lead), y: selected.y + ((dy / length) * lead)};"
        "};"
        "const bufferStopPoint = (itemX, itemY, itemW, itemH, rotationDeg) => {"
        "const extension = Math.min(0.45, itemH * 0.06);"
        "return localPointToBoard(itemX, itemY, itemW, itemH, rotationDeg, itemW / 2, itemH + extension);"
        "};"
        "const currentDraggedConnectionPoint = (port, target, shifted) => {"
        "const itemX = readPct(el.style.left, startX);"
        "const itemY = readPct(el.style.top, startY);"
        "const itemW = readPct(el.style.width, boxWidthPct);"
        "const itemH = readPct(el.style.height, boxHeightPct);"
        "let rotationValue = 0;"
        "const transformValue = String(el.style.transform || '');"
        "const rotationMatch = transformValue.match(/rotate\\((-?[0-9.]+)deg\\)/);"
        "if (rotationMatch) rotationValue = Number.parseFloat(rotationMatch[1]) || 0;"
        "if (draggedItemType === 'switch') return shiftedSwitchPoint(itemX, itemY, itemW, itemH, rotationValue, port);"
        "if (draggedItemType === 'buffer_stop') return bufferStopPoint(itemX, itemY, itemW, itemH, rotationValue);"
        "return shifted;"
        "};"
        "const currentDraggedSwitchLeadPoint = (port) => {"
        "const itemX = readPct(el.style.left, startX);"
        "const itemY = readPct(el.style.top, startY);"
        "const itemW = readPct(el.style.width, boxWidthPct);"
        "const itemH = readPct(el.style.height, boxHeightPct);"
        "let rotationValue = 0;"
        "const transformValue = String(el.style.transform || '');"
        "const rotationMatch = transformValue.match(/rotate\\((-?[0-9.]+)deg\\)/);"
        "if (rotationMatch) rotationValue = Number.parseFloat(rotationMatch[1]) || 0;"
        "return switchLeadPoint(itemX, itemY, itemW, itemH, rotationValue, port);"
        "};"
        "const catmull = (pts, t) => {"
        "if (pts.length <= 1) return pts[0] || {x:0,y:0};"
        "const segments = pts.length - 1;"
        "const raw = Math.max(0, Math.min(1, t)) * segments;"
        "const i = Math.min(segments - 1, Math.floor(raw));"
        "const lt = raw - i;"
        "const p0 = pts[i - 1] || pts[i];"
        "const p1 = pts[i];"
        "const p2 = pts[i + 1];"
        "const p3 = pts[i + 2] || p2;"
        "const tt = lt * lt;"
        "const ttt = tt * lt;"
        "return {x: 0.5*((2*p1.x)+(-p0.x+p2.x)*lt+(2*p0.x-5*p1.x+4*p2.x-p3.x)*tt+(-p0.x+3*p1.x-3*p2.x+p3.x)*ttt),"
        "y: 0.5*((2*p1.y)+(-p0.y+p2.y)*lt+(2*p0.y-5*p1.y+4*p2.y-p3.y)*tt+(-p0.y+3*p1.y-3*p2.y+p3.y)*ttt)};"
        "};"
        "const buildConnectionPath = (x1, y1, x2, y2, curve, pathPoints, sourceLead, targetLead) => {"
        "const pts = [{x:x1,y:y1}, ...(sourceLead ? [sourceLead] : []), ...(pathPoints || []), ...(targetLead ? [targetLead] : []), {x:x2,y:y2}];"
        "if ((pathPoints && pathPoints.length) || sourceLead || targetLead) {"
        "if (pts.length === 2) return `M ${x1.toFixed(3)} ${y1.toFixed(3)} L ${x2.toFixed(3)} ${y2.toFixed(3)}`;"
        "let d = `M ${pts[0].x.toFixed(3)} ${pts[0].y.toFixed(3)}`;"
        "for (let i = 0; i < pts.length - 1; i += 1) {"
        "const p0 = pts[i - 1] || pts[i];"
        "const p1 = pts[i];"
        "const p2 = pts[i + 1];"
        "const p3 = pts[i + 2] || p2;"
        "const c1x = p1.x + ((p2.x - p0.x) / 6);"
        "const c1y = p1.y + ((p2.y - p0.y) / 6);"
        "const c2x = p2.x - ((p3.x - p1.x) / 6);"
        "const c2y = p2.y - ((p3.y - p1.y) / 6);"
        "d += ` C ${c1x.toFixed(3)} ${c1y.toFixed(3)} ${c2x.toFixed(3)} ${c2y.toFixed(3)} ${p2.x.toFixed(3)} ${p2.y.toFixed(3)}`;"
        "}"
        "return d;"
        "}"
        "if (Math.abs(curve || 0) < 0.001) return `M ${x1.toFixed(3)} ${y1.toFixed(3)} L ${x2.toFixed(3)} ${y2.toFixed(3)}`;"
        "const dx = x2 - x1;"
        "const dy = y2 - y1;"
        "const length = Math.sqrt((dx * dx) + (dy * dy)) || 1;"
        "const cx = ((x1 + x2) / 2) + ((-dy / length) * curve);"
        "const cy = ((y1 + y2) / 2) + ((dx / length) * curve);"
        "return `M ${x1.toFixed(3)} ${y1.toFixed(3)} Q ${cx.toFixed(3)} ${cy.toFixed(3)} ${x2.toFixed(3)} ${y2.toFixed(3)}`;"
        "};"
        "const buildRoutePath = (pts, smooth) => {"
        "if (!pts || pts.length <= 0) return '';"
        "if (pts.length === 1) return `M ${pts[0].x.toFixed(3)} ${pts[0].y.toFixed(3)}`;"
        "if (!smooth || pts.length <= 2) return `M ${pts[0].x.toFixed(3)} ${pts[0].y.toFixed(3)} ` + pts.slice(1).map((p) => `L ${p.x.toFixed(3)} ${p.y.toFixed(3)}`).join(' ');"
        "let d = `M ${pts[0].x.toFixed(3)} ${pts[0].y.toFixed(3)}`;"
        "for (let i = 0; i < pts.length - 1; i += 1) {"
        "const p0 = pts[i - 1] || pts[i];"
        "const p1 = pts[i];"
        "const p2 = pts[i + 1];"
        "const p3 = pts[i + 2] || p2;"
        "const c1x = p1.x + ((p2.x - p0.x) / 6);"
        "const c1y = p1.y + ((p2.y - p0.y) / 6);"
        "const c2x = p2.x - ((p3.x - p1.x) / 6);"
        "const c2y = p2.y - ((p3.y - p1.y) / 6);"
        "d += ` C ${c1x.toFixed(3)} ${c1y.toFixed(3)} ${c2x.toFixed(3)} ${c2y.toFixed(3)} ${p2.x.toFixed(3)} ${p2.y.toFixed(3)}`;"
        "}"
        "return d;"
        "};"
        "const routePointAt = (pts, t) => {"
        "if (!pts || pts.length <= 0) return {x:0,y:0};"
        "if (pts.length === 1) return pts[0];"
        "const lengths = [];"
        "let total = 0;"
        "for (let i = 0; i < pts.length - 1; i += 1) { const dx = pts[i+1].x - pts[i].x; const dy = pts[i+1].y - pts[i].y; const len = Math.sqrt((dx*dx)+(dy*dy)); lengths.push(len); total += len; }"
        "if (total <= 0.000001) return pts[0];"
        "let target = Math.max(0, Math.min(1, t)) * total;"
        "let walked = 0;"
        "for (let i = 0; i < lengths.length; i += 1) {"
        "const len = lengths[i];"
        "if (walked + len >= target || i === lengths.length - 1) { const lt = len <= 0.000001 ? 0 : (target - walked) / len; return {x: pts[i].x + ((pts[i+1].x - pts[i].x) * lt), y: pts[i].y + ((pts[i+1].y - pts[i].y) * lt)}; }"
        "walked += len;"
        "}"
        "return pts[pts.length - 1];"
        "};"
        "const currentRoutePoints = (meta, deltaX, deltaY) => {"
        "const currentItemX = readPct(el.style.left, startX);"
        "const currentItemY = readPct(el.style.top, startY);"
        "return (meta.routePoints || []).map((point) => {"
        "if (point.anchor === 'from' && meta.source === draggedItemId) return {...point, x: currentItemX + (Number(point.dx) || 0), y: currentItemY + (Number(point.dy) || 0)};"
        "if (point.anchor === 'to' && meta.target === draggedItemId) return {...point, x: currentItemX + (Number(point.dx) || 0), y: currentItemY + (Number(point.dy) || 0)};"
        "return {x: Number(point.x) || 0, y: Number(point.y) || 0, anchor: point.anchor || '', dx: Number(point.dx) || 0, dy: Number(point.dy) || 0};"
        "});"
        "};"
        "const updateConnectedConnections = (deltaX, deltaY) => {"
        "connectedConnections.forEach((meta) => {"
        "if (!meta.id) return;"
        "const path = board.querySelector(`.gleisplan-editor-connection-path[data-connection-id='${meta.id}']`);"
        "const hitPath = board.querySelector(`.gleisplan-editor-connection-hit-path[data-connection-id='${meta.id}']`);"
        "const label = board.querySelector(`.gleisplan-editor-connection-label[data-connection-id='${meta.id}']`);"
        "if (meta.fixedRoute) {"
        "const routePts = currentRoutePoints(meta, deltaX, deltaY);"
        "if (!routePts.length) return;"
        "const d = buildRoutePath(routePts, !!meta.routeSmooth);"
        "const start = routePts[0];"
        "const end = routePts[routePts.length - 1];"
        "[path, hitPath].forEach((node) => { if (!node) return; node.setAttribute('d', d); node.dataset.x1Pct = start.x.toFixed(3); node.dataset.y1Pct = start.y.toFixed(3); node.dataset.x2Pct = end.x.toFixed(3); node.dataset.y2Pct = end.y.toFixed(3); });"
        "if (label) { const mid = routePointAt(routePts, 0.5); label.style.left = mid.x.toFixed(3) + '%'; label.style.top = mid.y.toFixed(3) + '%'; }"
        "return;"
        "}"
        "const sourceMoved = meta.source === draggedItemId;"
        "const targetMoved = meta.target === draggedItemId;"
        "let x1 = (sourceMoved ? meta.x1 + deltaX : meta.x1);"
        "let y1 = (sourceMoved ? meta.y1 + deltaY : meta.y1);"
        "let x2 = (targetMoved ? meta.x2 + deltaX : meta.x2);"
        "let y2 = (targetMoved ? meta.y2 + deltaY : meta.y2);"
        "let sourceLead = meta.sourceLead || null;"
        "let targetLead = meta.targetLead || null;"
        "if (sourceMoved) {"
        "const point = currentDraggedConnectionPoint(meta.sourcePort, {x: x2, y: y2}, {x: x1, y: y1});"
        "x1 = point.x; y1 = point.y;"
        "if (draggedItemType === 'switch') sourceLead = currentDraggedSwitchLeadPoint(meta.sourcePort);"
        "}"
        "if (targetMoved) {"
        "const point = currentDraggedConnectionPoint(meta.targetPort, {x: x1, y: y1}, {x: x2, y: y2});"
        "x2 = point.x; y2 = point.y;"
        "if (draggedItemType === 'switch') targetLead = currentDraggedSwitchLeadPoint(meta.targetPort);"
        "}"
        "let pathPoints = meta.pathPoints || [];"
        "try {"
        "const storedSource = path || hitPath;"
        "const stored = storedSource ? JSON.parse(storedSource.dataset.pathPoints || 'null') : null;"
        "if (Array.isArray(stored)) pathPoints = stored.map((point) => ({x: Number(point.x), y: Number(point.y)}));"
        "} catch (_err) {}"
        "const d = buildConnectionPath(x1, y1, x2, y2, meta.curve || 0, pathPoints, sourceLead, targetLead);"
        "const serialized = JSON.stringify(pathPoints);"
        "if (path) { path.setAttribute('d', d); path.dataset.x1Pct = x1.toFixed(3); path.dataset.y1Pct = y1.toFixed(3); path.dataset.x2Pct = x2.toFixed(3); path.dataset.y2Pct = y2.toFixed(3); path.dataset.pathPoints = serialized; path.dataset.hasSourceLead = sourceLead ? '1' : '0'; path.dataset.hasTargetLead = targetLead ? '1' : '0'; if (sourceLead) { path.dataset.sourceLeadXPct = sourceLead.x.toFixed(3); path.dataset.sourceLeadYPct = sourceLead.y.toFixed(3); } if (targetLead) { path.dataset.targetLeadXPct = targetLead.x.toFixed(3); path.dataset.targetLeadYPct = targetLead.y.toFixed(3); } }"
        "if (hitPath) { hitPath.setAttribute('d', d); hitPath.dataset.x1Pct = x1.toFixed(3); hitPath.dataset.y1Pct = y1.toFixed(3); hitPath.dataset.x2Pct = x2.toFixed(3); hitPath.dataset.y2Pct = y2.toFixed(3); hitPath.dataset.pathPoints = serialized; hitPath.dataset.hasSourceLead = sourceLead ? '1' : '0'; hitPath.dataset.hasTargetLead = targetLead ? '1' : '0'; if (sourceLead) { hitPath.dataset.sourceLeadXPct = sourceLead.x.toFixed(3); hitPath.dataset.sourceLeadYPct = sourceLead.y.toFixed(3); } if (targetLead) { hitPath.dataset.targetLeadXPct = targetLead.x.toFixed(3); hitPath.dataset.targetLeadYPct = targetLead.y.toFixed(3); } }"
        "if (label) {"
        "let mid;"
        "if (pathPoints.length || sourceLead || targetLead) { mid = catmull([{x:x1,y:y1}, ...(sourceLead ? [sourceLead] : []), ...pathPoints, ...(targetLead ? [targetLead] : []), {x:x2,y:y2}], 0.5); }"
        "else {"
        "const dx = x2 - x1;"
        "const dy = y2 - y1;"
        "const length = Math.sqrt((dx * dx) + (dy * dy)) || 1;"
        "const cx = ((x1 + x2) / 2) + ((-dy / length) * (meta.curve || 0));"
        "const cy = ((y1 + y2) / 2) + ((dx / length) * (meta.curve || 0));"
        "mid = Math.abs(meta.curve || 0) < 0.001 ? {x:(x1+x2)/2,y:(y1+y2)/2} : {x:(0.25*x1)+(0.5*cx)+(0.25*x2), y:(0.25*y1)+(0.5*cy)+(0.25*y2)};"
        "}"
        "label.style.left = mid.x.toFixed(3) + '%';"
        "label.style.top = mid.y.toFixed(3) + '%';"
        "}"
        "});"
        "};"
        "connectedConnections.forEach((meta) => {"
        "if (meta.fixedRoute) return;"
        "const path = board.querySelector(`.gleisplan-editor-connection-path[data-connection-id='${meta.id}']`);"
        "const hitPath = board.querySelector(`.gleisplan-editor-connection-hit-path[data-connection-id='${meta.id}']`);"
        "const source = path || hitPath;"
        "if (!source) return;"
        "meta.x1 = Number.parseFloat(source.dataset.x1Pct || meta.x1 || 0);"
        "meta.y1 = Number.parseFloat(source.dataset.y1Pct || meta.y1 || 0);"
        "meta.x2 = Number.parseFloat(source.dataset.x2Pct || meta.x2 || 0);"
        "meta.y2 = Number.parseFloat(source.dataset.y2Pct || meta.y2 || 0);"
        "meta.sourceLead = source.dataset.hasSourceLead === '1' ? {x: Number.parseFloat(source.dataset.sourceLeadXPct || '0'), y: Number.parseFloat(source.dataset.sourceLeadYPct || '0')} : meta.sourceLead;"
        "meta.targetLead = source.dataset.hasTargetLead === '1' ? {x: Number.parseFloat(source.dataset.targetLeadXPct || '0'), y: Number.parseFloat(source.dataset.targetLeadYPct || '0')} : meta.targetLead;"
        "});"
        "let moved = false;"
        "el.classList.add('is-dragging');"
        "const move = (ev) => {"
        "const deltaX = ev.clientX - startClientX;"
        "const deltaY = ev.clientY - startClientY;"
        "if (Math.sqrt((deltaX * deltaX) + (deltaY * deltaY)) > 3) moved = true;"
        "let x = startX + ((deltaX / rect.width) * 100);"
        "let y = startY + ((deltaY / rect.height) * 100);"
        "x = Math.max(0, Math.min(maxX, x));"
        "y = Math.max(0, Math.min(maxY, y));"
        "if (moved) {"
        "el.style.left = x.toFixed(3) + '%';"
        "el.style.top = y.toFixed(3) + '%';"
        "el.dataset.gleisplanX = x.toFixed(3);"
        "el.dataset.gleisplanY = y.toFixed(3);"
        "rememberPendingPosition(x, y);"
        "updateConnectedConnections(x - startX, y - startY);"
        "}"
        "};"
        "let finished = false;"
        "const up = () => {"
        "if (finished) return;"
        "finished = true;"
        "document.removeEventListener('pointermove', move);"
        "document.removeEventListener('pointerup', up);"
        "document.removeEventListener('pointercancel', up);"
        "el.classList.remove('is-dragging');"
        "if (!moved) {"
        "board.querySelectorAll('.gleisplan-editor-item.is-selected, .gleisplan-editor-item.is-connection-source').forEach((node) => {"
        "node.classList.remove('is-selected');"
        "node.classList.remove('is-connection-source');"
        "});"
        "el.classList.add('is-selected');"
        "if (isConnectable) el.classList.add('is-connection-source');"
        "board.querySelectorAll('.gleisplan-editor-connection-svg.is-connected-selected, .gleisplan-editor-connection-path.is-connected-selected, .gleisplan-editor-connection-hit-path.is-connected-selected, .gleisplan-editor-connection-label.is-connected-selected').forEach((node) => node.classList.remove('is-connected-selected'));"
        "board.querySelectorAll('.is-connection-selected').forEach((node) => node.classList.remove('is-connection-selected'));"
        "connectedConnections.forEach((meta) => {"
        "const path = board.querySelector(`.gleisplan-editor-connection-path[data-connection-id='${meta.id}']`);"
        "const hitPath = board.querySelector(`.gleisplan-editor-connection-hit-path[data-connection-id='${meta.id}']`);"
        "const label = board.querySelector(`.gleisplan-editor-connection-label[data-connection-id='${meta.id}']`);"
        "const svg = path ? path.closest('.gleisplan-editor-connection-svg') : hitPath ? hitPath.closest('.gleisplan-editor-connection-svg') : null;"
        "[svg, path, hitPath, label].forEach((node) => { if (node) node.classList.add('is-connected-selected'); });"
        "});"
        f"emit({{item_id: {item_id!r}, mode: 'select'}});"
        "return;"
        "}"
        "const x = Number.parseFloat(el.dataset.gleisplanX || '0');"
        "const y = Number.parseFloat(el.dataset.gleisplanY || '0');"
        "rememberPendingPosition(x, y);"
        f"emit({{item_id: {item_id!r}, mode: 'move', x_pct: x, y_pct: y}});"
        "const saveButton = board.closest('.cfg-gleisplan-editor-panel')?.querySelector('.cfg-save-gleisplan-layout');"
        "if (saveButton) saveButton.classList.add('has-unsaved');"
        "};"
        "document.addEventListener('pointermove', move);"
        "document.addEventListener('pointerup', up);"
        "document.addEventListener('pointercancel', up);"
        "}"
    )


def _resize_street_js_handler(item_id: str, rotation: float) -> str:
    return (
        "(event) => {"
        "if (event.button !== 0) return;"
        "event.preventDefault();"
        "event.stopPropagation();"
        "const handle = event.currentTarget;"
        "const el = handle.closest('.gleisplan-editor-item');"
        "const board = handle.closest('.gleisplan-editor-board');"
        "if (!el || !board) return;"
        "const rect = board.getBoundingClientRect();"
        "const elRect = el.getBoundingClientRect();"
        "const startClientX = event.clientX;"
        "const startClientY = event.clientY;"
        "const startWidthPct = (elRect.width / rect.width) * 100;"
        f"const angle = ({float(rotation):.6f}) * Math.PI / 180;"
        "el.classList.add('is-resizing');"
        "const move = (ev) => {"
        "const dx = ev.clientX - startClientX;"
        "const dy = ev.clientY - startClientY;"
        "const projected = (dx * Math.cos(angle)) + (dy * Math.sin(angle));"
        "let width = startWidthPct + ((projected / rect.width) * 100);"
        "width = Math.max(2, Math.min(100, width));"
        "el.style.width = width.toFixed(3) + '%';"
        "el.dataset.gleisplanW = width.toFixed(3);"
        "};"
        "const up = () => {"
        "document.removeEventListener('pointermove', move);"
        "document.removeEventListener('pointerup', up);"
        "el.classList.remove('is-resizing');"
        "const width = Number.parseFloat(el.dataset.gleisplanW || startWidthPct.toFixed(3));"
        f"emit({{item_id: {item_id!r}, width: width}});"
        "};"
        "document.addEventListener('pointermove', move);"
        "document.addEventListener('pointerup', up);"
        "}"
    )


def _resize_street_width_js_handler(item_id: str, rotation: float, height_pct: float) -> str:
    return (
        "(event) => {"
        "if (event.button !== 0) return;"
        "event.preventDefault();"
        "event.stopPropagation();"
        "const handle = event.currentTarget;"
        "const el = handle.closest('.gleisplan-editor-item');"
        "const board = handle.closest('.gleisplan-editor-board');"
        "if (!el || !board) return;"
        "const rect = board.getBoundingClientRect();"
        "const startClientX = event.clientX;"
        "const startClientY = event.clientY;"
        f"const startHeightPct = {float(height_pct):.6f};"
        f"const angle = ({float(rotation):.6f}) * Math.PI / 180;"
        "const px = -Math.sin(angle);"
        "const py = Math.cos(angle);"
        "el.classList.add('is-resizing');"
        "const move = (ev) => {"
        "const dx = ev.clientX - startClientX;"
        "const dy = ev.clientY - startClientY;"
        "const projected = (dx * px) + (dy * py);"
        "let height = startHeightPct + ((projected / rect.height) * 100);"
        "height = Math.max(1, Math.min(100, height));"
        "el.style.height = height.toFixed(3) + '%';"
        "el.dataset.gleisplanH = height.toFixed(3);"
        "};"
        "const up = () => {"
        "document.removeEventListener('pointermove', move);"
        "document.removeEventListener('pointerup', up);"
        "el.classList.remove('is-resizing');"
        "const height = Number.parseFloat(el.dataset.gleisplanH || startHeightPct.toFixed(3));"
        f"emit({{item_id: {item_id!r}, h_pct: height}});"
        "};"
        "document.addEventListener('pointermove', move);"
        "document.addEventListener('pointerup', up);"
        "}"
    )


def _rotate_item_js_handler(
    item_id: str,
    rotation: float,
    connections: list[dict[str, Any]] | None = None,
    *,
    item_type: str = "",
) -> str:
    connection_payload = _connected_connection_drag_payload(item_id, connections or [])
    clean_item_type = str(item_type or "").strip().lower()
    return (
        "(event) => {"
        "if (event.button !== 0) return;"
        "event.preventDefault();"
        "event.stopPropagation();"
        "const handle = event.currentTarget;"
        "const el = handle.closest('.gleisplan-editor-item');"
        "const board = handle.closest('.gleisplan-editor-board');"
        "if (!el || !board) return;"
        f"const rotatedItemId = {str(item_id or '').strip().upper()!r};"
        f"const rotatedItemType = {clean_item_type!r};"
        f"const connectedConnections = {json.dumps(connection_payload, ensure_ascii=True)};"
        "const elRect = el.getBoundingClientRect();"
        "const cx = elRect.left + elRect.width / 2;"
        "const cy = elRect.top + elRect.height / 2;"
        f"const startRotation = {float(rotation):.6f};"
        "const startAngle = Math.atan2(event.clientY - cy, event.clientX - cx) * 180 / Math.PI;"
        "const boardRect = board.getBoundingClientRect();"
        "const itemX = () => Number.parseFloat(String(el.style.left || '')) || 0;"
        "const itemY = () => Number.parseFloat(String(el.style.top || '')) || 0;"
        "const itemW = () => ((el.offsetWidth || el.getBoundingClientRect().width) / boardRect.width) * 100;"
        "const itemH = () => ((el.offsetHeight || el.getBoundingClientRect().height) / boardRect.height) * 100;"
        "const itemRotation = () => Number.parseFloat(el.dataset.gleisplanRotation || String(startRotation)) || 0;"
        "const localPointToBoard = (localX, localY) => {"
        "const w = itemW();"
        "const h = itemH();"
        "const angle = itemRotation() * Math.PI / 180;"
        "const centerX = itemX() + (w / 2);"
        "const centerY = itemY() + (h / 2);"
        "const scaleX = boardRect.width / 100;"
        "const scaleY = boardRect.height / 100;"
        "const dx = (localX - (w / 2)) * scaleX;"
        "const dy = (localY - (h / 2)) * scaleY;"
        "const rotatedX = (dx * Math.cos(angle)) - (dy * Math.sin(angle));"
        "const rotatedY = (dx * Math.sin(angle)) + (dy * Math.cos(angle));"
        "return {x: centerX + (rotatedX / scaleX), y: centerY + (rotatedY / scaleY)};"
        "};"
        "const switchPoints = (port) => {"
        "const w = itemW();"
        "const h = itemH();"
        "const readRatio = (value, fallback) => { const parsed = Number.parseFloat(String(value || '')); return Number.isFinite(parsed) ? parsed : fallback; };"
        "const port1 = {x: w, y: h * 0.28};"
        "const port2 = {x: w * readRatio(el.dataset.switchPort2X, 0), y: h * readRatio(el.dataset.switchPort2Y, 0.28)};"
        "const heel = {x: port2.x + ((port1.x - port2.x) * 0.80), y: port2.y + ((port1.y - port2.y) * 0.80)};"
        "const port3 = {x: w * readRatio(el.dataset.switchPort3X, 0.06), y: h * readRatio(el.dataset.switchPort3Y, 1.35)};"
        "const cleanPort = String(port || '1');"
        "if (cleanPort === '2') return [localPointToBoard(port2.x, port2.y), localPointToBoard(port1.x, port1.y)];"
        "if (cleanPort === '3') {"
        "return [localPointToBoard(port3.x, port3.y), localPointToBoard(heel.x, heel.y)];"
        "}"
        "return [localPointToBoard(port1.x, port1.y), localPointToBoard(port2.x, port2.y)];"
        "};"
        "const switchConnectionPoint = (port) => switchPoints(port)[0];"
        "const switchLeadPoint = (port) => {"
        "const pts = switchPoints(port);"
        "const selected = pts[0];"
        "const opposite = pts[1];"
        "const dx = selected.x - opposite.x;"
        "const dy = selected.y - opposite.y;"
        "const length = Math.sqrt((dx * dx) + (dy * dy)) || 0;"
        "if (length <= 0.000001) return null;"
        "const lead = Math.min(1.35, length * 0.42);"
        "return {x: selected.x + ((dx / length) * lead), y: selected.y + ((dy / length) * lead)};"
        "};"
        "const bufferStopPoint = () => {"
        "const w = itemW();"
        "const h = itemH();"
        "const extension = Math.min(0.45, h * 0.06);"
        "return localPointToBoard(w / 2, h + extension);"
        "};"
        "const catmull = (pts, t) => {"
        "if (pts.length <= 1) return pts[0] || {x:0,y:0};"
        "const segments = pts.length - 1;"
        "const raw = Math.max(0, Math.min(1, t)) * segments;"
        "const i = Math.min(segments - 1, Math.floor(raw));"
        "const lt = raw - i;"
        "const p0 = pts[i - 1] || pts[i];"
        "const p1 = pts[i];"
        "const p2 = pts[i + 1];"
        "const p3 = pts[i + 2] || p2;"
        "const tt = lt * lt;"
        "const ttt = tt * lt;"
        "return {x: 0.5*((2*p1.x)+(-p0.x+p2.x)*lt+(2*p0.x-5*p1.x+4*p2.x-p3.x)*tt+(-p0.x+3*p1.x-3*p2.x+p3.x)*ttt),"
        "y: 0.5*((2*p1.y)+(-p0.y+p2.y)*lt+(2*p0.y-5*p1.y+4*p2.y-p3.y)*tt+(-p0.y+3*p1.y-3*p2.y+p3.y)*ttt)};"
        "};"
        "const buildPath = (x1, y1, x2, y2, curve, pathPoints, sourceLead, targetLead) => {"
        "const pts = [{x:x1,y:y1}, ...(sourceLead ? [sourceLead] : []), ...(pathPoints || []), ...(targetLead ? [targetLead] : []), {x:x2,y:y2}];"
        "if ((pathPoints && pathPoints.length) || sourceLead || targetLead) {"
        "if (pts.length === 2) return `M ${x1.toFixed(3)} ${y1.toFixed(3)} L ${x2.toFixed(3)} ${y2.toFixed(3)}`;"
        "let d = `M ${pts[0].x.toFixed(3)} ${pts[0].y.toFixed(3)}`;"
        "for (let i = 0; i < pts.length - 1; i += 1) {"
        "const p0 = pts[i - 1] || pts[i];"
        "const p1 = pts[i];"
        "const p2 = pts[i + 1];"
        "const p3 = pts[i + 2] || p2;"
        "const c1x = p1.x + ((p2.x - p0.x) / 6);"
        "const c1y = p1.y + ((p2.y - p0.y) / 6);"
        "const c2x = p2.x - ((p3.x - p1.x) / 6);"
        "const c2y = p2.y - ((p3.y - p1.y) / 6);"
        "d += ` C ${c1x.toFixed(3)} ${c1y.toFixed(3)} ${c2x.toFixed(3)} ${c2y.toFixed(3)} ${p2.x.toFixed(3)} ${p2.y.toFixed(3)}`;"
        "}"
        "return d;"
        "}"
        "if (Math.abs(curve || 0) < 0.001) return `M ${x1.toFixed(3)} ${y1.toFixed(3)} L ${x2.toFixed(3)} ${y2.toFixed(3)}`;"
        "const dx = x2 - x1;"
        "const dy = y2 - y1;"
        "const length = Math.sqrt((dx * dx) + (dy * dy)) || 1;"
        "const cpx = ((x1 + x2) / 2) + ((-dy / length) * curve);"
        "const cpy = ((y1 + y2) / 2) + ((dx / length) * curve);"
        "return `M ${x1.toFixed(3)} ${y1.toFixed(3)} Q ${cpx.toFixed(3)} ${cpy.toFixed(3)} ${x2.toFixed(3)} ${y2.toFixed(3)}`;"
        "};"
        "const recalcConnections = () => {"
        "connectedConnections.forEach((meta) => {"
        "if (!meta.id) return;"
        "if (meta.fixedRoute) return;"
        "const path = board.querySelector(`.gleisplan-editor-connection-path[data-connection-id='${meta.id}']`);"
        "const hitPath = board.querySelector(`.gleisplan-editor-connection-hit-path[data-connection-id='${meta.id}']`);"
        "const label = board.querySelector(`.gleisplan-editor-connection-label[data-connection-id='${meta.id}']`);"
        "const source = path || hitPath;"
        "let x1 = Number.parseFloat(source?.dataset.x1Pct || meta.x1 || 0);"
        "let y1 = Number.parseFloat(source?.dataset.y1Pct || meta.y1 || 0);"
        "let x2 = Number.parseFloat(source?.dataset.x2Pct || meta.x2 || 0);"
        "let y2 = Number.parseFloat(source?.dataset.y2Pct || meta.y2 || 0);"
        "let sourceLead = source?.dataset.hasSourceLead === '1' ? {x: Number.parseFloat(source.dataset.sourceLeadXPct || '0'), y: Number.parseFloat(source.dataset.sourceLeadYPct || '0')} : null;"
        "let targetLead = source?.dataset.hasTargetLead === '1' ? {x: Number.parseFloat(source.dataset.targetLeadXPct || '0'), y: Number.parseFloat(source.dataset.targetLeadYPct || '0')} : null;"
        "if (meta.source === rotatedItemId) {"
        "const point = rotatedItemType === 'switch' ? switchConnectionPoint(meta.sourcePort) : (rotatedItemType === 'buffer_stop' ? bufferStopPoint() : {x:x1,y:y1});"
        "x1 = point.x; y1 = point.y;"
        "sourceLead = rotatedItemType === 'switch' ? switchLeadPoint(meta.sourcePort) : null;"
        "}"
        "if (meta.target === rotatedItemId) {"
        "const point = rotatedItemType === 'switch' ? switchConnectionPoint(meta.targetPort) : (rotatedItemType === 'buffer_stop' ? bufferStopPoint() : {x:x2,y:y2});"
        "x2 = point.x; y2 = point.y;"
        "targetLead = rotatedItemType === 'switch' ? switchLeadPoint(meta.targetPort) : null;"
        "}"
        "let pathPoints = meta.pathPoints || [];"
        "try {"
        "const stored = source ? JSON.parse(source.dataset.pathPoints || 'null') : null;"
        "if (Array.isArray(stored)) pathPoints = stored.map((point) => ({x: Number(point.x), y: Number(point.y)}));"
        "} catch (_err) {}"
        "const d = buildPath(x1, y1, x2, y2, meta.curve || 0, pathPoints, sourceLead, targetLead);"
        "const serialized = JSON.stringify(pathPoints);"
        "[path, hitPath].forEach((node) => {"
        "if (!node) return;"
        "node.setAttribute('d', d);"
        "node.dataset.x1Pct = x1.toFixed(3);"
        "node.dataset.y1Pct = y1.toFixed(3);"
        "node.dataset.x2Pct = x2.toFixed(3);"
        "node.dataset.y2Pct = y2.toFixed(3);"
        "node.dataset.pathPoints = serialized;"
        "node.dataset.hasSourceLead = sourceLead ? '1' : '0';"
        "node.dataset.hasTargetLead = targetLead ? '1' : '0';"
        "if (sourceLead) { node.dataset.sourceLeadXPct = sourceLead.x.toFixed(3); node.dataset.sourceLeadYPct = sourceLead.y.toFixed(3); }"
        "if (targetLead) { node.dataset.targetLeadXPct = targetLead.x.toFixed(3); node.dataset.targetLeadYPct = targetLead.y.toFixed(3); }"
        "});"
        "if (label) {"
        "const pts = [{x:x1,y:y1}, ...(sourceLead ? [sourceLead] : []), ...pathPoints, ...(targetLead ? [targetLead] : []), {x:x2,y:y2}];"
        "const mid = pts.length > 2 ? catmull(pts, 0.5) : {x: (x1 + x2) / 2, y: (y1 + y2) / 2};"
        "label.style.left = mid.x.toFixed(3) + '%';"
        "label.style.top = mid.y.toFixed(3) + '%';"
        "}"
        "});"
        "};"
        "el.classList.add('is-resizing');"
        "const move = (ev) => {"
        "const angle = Math.atan2(ev.clientY - cy, ev.clientX - cx) * 180 / Math.PI;"
        "let rotation = startRotation + (angle - startAngle);"
        "el.style.transform = `rotate(${rotation.toFixed(3)}deg)`;"
        "el.dataset.gleisplanRotation = rotation.toFixed(3);"
        "recalcConnections();"
        "};"
        "const up = () => {"
        "document.removeEventListener('pointermove', move);"
        "document.removeEventListener('pointerup', up);"
        "document.removeEventListener('pointercancel', up);"
        "el.classList.remove('is-resizing');"
        "const rotation = Number.parseFloat(el.dataset.gleisplanRotation || startRotation.toFixed(3));"
        "recalcConnections();"
        f"emit({{item_id: {item_id!r}, rotation: rotation}});"
        "};"
        "document.addEventListener('pointermove', move);"
        "document.addEventListener('pointerup', up);"
        "document.addEventListener('pointercancel', up);"
        "}"
    )


def _curve_street_js_handler(item_id: str, curve_radius: float) -> str:
    return (
        "(event) => {"
        "if (event.button !== 0) return;"
        "event.preventDefault();"
        "event.stopPropagation();"
        "const handle = event.currentTarget;"
        "const el = handle.closest('.gleisplan-editor-item');"
        "if (!el) return;"
        "const startClientY = event.clientY;"
        f"const startCurve = {float(curve_radius):.6f};"
        "el.classList.add('is-resizing');"
        "const move = (ev) => {"
        "let curve = startCurve + ((startClientY - ev.clientY) / 6);"
        "curve = Math.max(0, Math.min(100, curve));"
        "el.style.setProperty('--curve-radius', curve.toFixed(3) + '%');"
        "el.dataset.gleisplanCurve = curve.toFixed(3);"
        "};"
        "const up = () => {"
        "document.removeEventListener('pointermove', move);"
        "document.removeEventListener('pointerup', up);"
        "el.classList.remove('is-resizing');"
        "const curve = Number.parseFloat(el.dataset.gleisplanCurve || startCurve.toFixed(3));"
        f"emit({{item_id: {item_id!r}, curve_radius: curve}});"
        "};"
        "document.addEventListener('pointermove', move);"
        "document.addEventListener('pointerup', up);"
        "}"
    )


def _switch_port_handle_js_handler(item_id: str, port: str) -> str:
    clean_port = "3" if str(port) == "3" else "2"
    return (
        "(event) => {"
        "if (event.button !== 0) return;"
        "event.preventDefault();"
        "event.stopPropagation();"
        "const handle = event.currentTarget;"
        "const el = handle.closest('[data-gleisplan-item-id]');"
        "const board = el ? el.closest('.gleisplan-editor-board') : null;"
        "if (!el || !board) return;"
        f"const itemId = {str(item_id or '').strip().upper()!r};"
        f"const port = {clean_port!r};"
        "try { handle.setPointerCapture(event.pointerId); } catch (_err) {}"
        "const read = (value, fallback) => { const parsed = Number.parseFloat(String(value || '')); return Number.isFinite(parsed) ? parsed : fallback; };"
        "const clamp = (value) => Math.max(-2, Math.min(3, value));"
        "const currentRatios = () => ({p2x: read(el.dataset.switchPort2X, 0), p2y: read(el.dataset.switchPort2Y, 0.28), p3x: read(el.dataset.switchPort3X, 0.06), p3y: read(el.dataset.switchPort3Y, 1.35)});"
        "const itemBox = () => {"
        "const boardRect = board.getBoundingClientRect();"
        "const w = ((el.offsetWidth || el.getBoundingClientRect().width) / boardRect.width) * 100;"
        "const h = ((el.offsetHeight || el.getBoundingClientRect().height) / boardRect.height) * 100;"
        "const x = read(el.style.left, 0);"
        "const y = read(el.style.top, 0);"
        "const match = String(el.style.transform || '').match(/rotate\\((-?[0-9.]+)deg\\)/);"
        "return {boardRect, w, h, x, y, rotation: match ? read(match[1], 0) : 0};"
        "};"
        "const localToClient = (box, lxRatio, lyRatio) => {"
        "const sx = box.boardRect.width / 100;"
        "const sy = box.boardRect.height / 100;"
        "const angle = box.rotation * Math.PI / 180;"
        "const cx = box.boardRect.left + ((box.x + (box.w / 2)) / 100) * box.boardRect.width;"
        "const cy = box.boardRect.top + ((box.y + (box.h / 2)) / 100) * box.boardRect.height;"
        "const dx = ((lxRatio * box.w) - (box.w / 2)) * sx;"
        "const dy = ((lyRatio * box.h) - (box.h / 2)) * sy;"
        "return {x: cx + (dx * Math.cos(angle)) - (dy * Math.sin(angle)), y: cy + (dx * Math.sin(angle)) + (dy * Math.cos(angle))};"
        "};"
        "const clientToLocalPx = (box, clientX, clientY) => {"
        "const sx = box.boardRect.width / 100;"
        "const sy = box.boardRect.height / 100;"
        "const angle = box.rotation * Math.PI / 180;"
        "const cx = box.boardRect.left + ((box.x + (box.w / 2)) / 100) * box.boardRect.width;"
        "const cy = box.boardRect.top + ((box.y + (box.h / 2)) / 100) * box.boardRect.height;"
        "const dx = clientX - cx;"
        "const dy = clientY - cy;"
        "return {x: (dx * Math.cos(angle)) + (dy * Math.sin(angle)), y: (-dx * Math.sin(angle)) + (dy * Math.cos(angle)), sx, sy};"
        "};"
        "const anchorAndEndpoint = (ratios) => {"
        "const p1 = {x: 1, y: 0.28};"
        "const p2 = {x: ratios.p2x, y: ratios.p2y};"
        "const heel = {x: p2.x + ((p1.x - p2.x) * 0.80), y: p2.y + ((p1.y - p2.y) * 0.80)};"
        "const p3 = {x: ratios.p3x, y: ratios.p3y};"
        "return port === '2' ? {anchor: p1, endpoint: p2} : {anchor: heel, endpoint: p3};"
        "};"
        "const updateVisual = () => {"
        "const ratios = currentRatios();"
        "const p1 = {x: 100, y: 28};"
        "const p2 = {x: ratios.p2x * 100, y: ratios.p2y * 100};"
        "const heel = {x: p2.x + ((p1.x - p2.x) * 0.80), y: p2.y + ((p1.y - p2.y) * 0.80)};"
        "const p3 = {x: ratios.p3x * 100, y: ratios.p3y * 100};"
        "const main = el.querySelector('.gleisplan-switch-main-line');"
        "const branch = el.querySelector('.gleisplan-switch-branch-line');"
        "if (main) { main.setAttribute('x1', p2.x.toFixed(3)); main.setAttribute('y1', p2.y.toFixed(3)); main.setAttribute('x2', p1.x.toFixed(3)); main.setAttribute('y2', p1.y.toFixed(3)); }"
        "if (branch) { branch.setAttribute('x1', p3.x.toFixed(3)); branch.setAttribute('y1', p3.y.toFixed(3)); branch.setAttribute('x2', heel.x.toFixed(3)); branch.setAttribute('y2', heel.y.toFixed(3)); }"
        "const port2 = el.querySelector('.gleisplan-switch-port-label.port-2');"
        "const port3 = el.querySelector('.gleisplan-switch-port-label.port-3');"
        "if (port2) { port2.style.left = `calc(${p2.x.toFixed(3)}% - 6px)`; port2.style.top = `calc(${p2.y.toFixed(3)}% - 6px)`; }"
        "if (port3) { port3.style.left = `calc(${p3.x.toFixed(3)}% - 6px)`; port3.style.top = `calc(${p3.y.toFixed(3)}% - 6px)`; }"
        "};"
        "const startBox = itemBox();"
        "const startPair = anchorAndEndpoint(currentRatios());"
        "const anchorPx = localToClient(startBox, startPair.anchor.x, startPair.anchor.y);"
        "const endpointPx = localToClient(startBox, startPair.endpoint.x, startPair.endpoint.y);"
        "const fixedLength = Math.max(1, Math.hypot(endpointPx.x - anchorPx.x, endpointPx.y - anchorPx.y));"
        "handle.classList.add('is-dragging');"
        "const move = (ev) => {"
        "const box = itemBox();"
        "const ratios = currentRatios();"
        "const pair = anchorAndEndpoint(ratios);"
        "const cursor = clientToLocalPx(box, ev.clientX, ev.clientY);"
        "const anchorLocal = {x: pair.anchor.x * box.w, y: pair.anchor.y * box.h};"
        "const targetLocal = {x: (box.w / 2) + (cursor.x / cursor.sx), y: (box.h / 2) + (cursor.y / cursor.sy)};"
        "const anchorLocalPx = {x: (anchorLocal.x - (box.w / 2)) * cursor.sx, y: (anchorLocal.y - (box.h / 2)) * cursor.sy};"
        "const targetLocalPx = {x: (targetLocal.x - (box.w / 2)) * cursor.sx, y: (targetLocal.y - (box.h / 2)) * cursor.sy};"
        "let vx = targetLocalPx.x - anchorLocalPx.x;"
        "let vy = targetLocalPx.y - anchorLocalPx.y;"
        "let len = Math.hypot(vx, vy);"
        "if (len < 0.001) return;"
        "vx = (vx / len) * fixedLength;"
        "vy = (vy / len) * fixedLength;"
        "const endpointLocal = {x: anchorLocal.x + (vx / cursor.sx), y: anchorLocal.y + (vy / cursor.sy)};"
        "if (port === '2') { el.dataset.switchPort2X = clamp(endpointLocal.x / box.w).toFixed(6); el.dataset.switchPort2Y = clamp(endpointLocal.y / box.h).toFixed(6); }"
        "else { el.dataset.switchPort3X = clamp(endpointLocal.x / box.w).toFixed(6); el.dataset.switchPort3Y = clamp(endpointLocal.y / box.h).toFixed(6); }"
        "updateVisual();"
        "if (window.__gleisplanRecalculateEditorConnections) window.__gleisplanRecalculateEditorConnections(itemId);"
        "};"
        "const up = () => {"
        "document.removeEventListener('pointermove', move);"
        "document.removeEventListener('pointerup', up);"
        "document.removeEventListener('pointercancel', up);"
        "handle.classList.remove('is-dragging');"
        "const ratios = currentRatios();"
        "if (port === '2') emit({item_id:itemId, switch_port2_x_ratio: ratios.p2x, switch_port2_y_ratio: ratios.p2y});"
        "else emit({item_id:itemId, switch_port3_x_ratio: ratios.p3x, switch_port3_y_ratio: ratios.p3y});"
        "};"
        "document.addEventListener('pointermove', move);"
        "document.addEventListener('pointerup', up);"
        "document.addEventListener('pointercancel', up);"
        "};"
    )


def _curve_connection_js_handler(connection: dict[str, Any]) -> str:
    connection_id = int(connection.get("id") or 0)
    x1 = float(connection.get("x_pct") or 0)
    y1 = float(connection.get("y_pct") or 0)
    x2 = float(connection.get("x2_pct") if connection.get("x2_pct") is not None else x1)
    y2 = float(connection.get("y2_pct") if connection.get("y2_pct") is not None else y1)
    curve = float(connection.get("curve_pct") or 0)
    return (
        "(event) => {"
        "if (event.button !== 0) return;"
        "event.preventDefault();"
        "event.stopPropagation();"
        "const handle = event.currentTarget;"
        "const board = handle.closest('.gleisplan-editor-board');"
        "if (!board) return;"
        "const rect = board.getBoundingClientRect();"
        f"const connectionId = {connection_id};"
        f"const x1 = {x1:.6f};"
        f"const y1 = {y1:.6f};"
        f"const x2 = {x2:.6f};"
        f"const y2 = {y2:.6f};"
        f"const startCurve = {curve:.6f};"
        "const dx = x2 - x1;"
        "const dy = y2 - y1;"
        "const length = Math.sqrt((dx * dx) + (dy * dy)) || 1;"
        "const nx = -dy / length;"
        "const ny = dx / length;"
        "const midX = (x1 + x2) / 2;"
        "const midY = (y1 + y2) / 2;"
        "const path = board.querySelector(`path[data-connection-id='${connectionId}']`);"
        "const label = board.querySelector(`.gleisplan-editor-connection-label[data-connection-id='${connectionId}']`);"
        "const setCurve = (curveValue) => {"
        "const cx = midX + (nx * curveValue);"
        "const cy = midY + (ny * curveValue);"
        "handle.style.left = cx.toFixed(3) + '%';"
        "handle.style.top = cy.toFixed(3) + '%';"
        "handle.dataset.gleisplanCurve = curveValue.toFixed(3);"
        "if (path) {"
        "const d = Math.abs(curveValue) < 0.001"
        "? `M ${x1.toFixed(3)} ${y1.toFixed(3)} L ${x2.toFixed(3)} ${y2.toFixed(3)}`"
        ": `M ${x1.toFixed(3)} ${y1.toFixed(3)} Q ${cx.toFixed(3)} ${cy.toFixed(3)} ${x2.toFixed(3)} ${y2.toFixed(3)}`;"
        "path.setAttribute('d', d);"
        "}"
        "if (label) {"
        "const lx = (0.25 * x1) + (0.50 * cx) + (0.25 * x2);"
        "const ly = (0.25 * y1) + (0.50 * cy) + (0.25 * y2);"
        "label.style.left = lx.toFixed(3) + '%';"
        "label.style.top = ly.toFixed(3) + '%';"
        "}"
        "};"
        "handle.classList.add('is-dragging');"
        "const move = (ev) => {"
        "const px = ((ev.clientX - rect.left) / rect.width) * 100;"
        "const py = ((ev.clientY - rect.top) / rect.height) * 100;"
        "let curveValue = ((px - midX) * nx) + ((py - midY) * ny);"
        "curveValue = Math.max(-100, Math.min(100, curveValue));"
        "setCurve(curveValue);"
        "};"
        "const up = () => {"
        "document.removeEventListener('pointermove', move);"
        "document.removeEventListener('pointerup', up);"
        "handle.classList.remove('is-dragging');"
        "const curveValue = Number.parseFloat(handle.dataset.gleisplanCurve || startCurve.toFixed(3));"
        "emit({connection_id: connectionId, curve_pct: curveValue});"
        "};"
        "document.addEventListener('pointermove', move);"
        "document.addEventListener('pointerup', up);"
        "move(event);"
        "}"
    )


def _add_connection_path_point_js_handler(connection: dict[str, Any]) -> str:
    connection_id = int(connection.get("id") or 0)
    x1 = float(connection.get("x_pct") or 0)
    y1 = float(connection.get("y_pct") or 0)
    x2 = float(connection.get("x2_pct") if connection.get("x2_pct") is not None else x1)
    y2 = float(connection.get("y2_pct") if connection.get("y2_pct") is not None else y1)
    path_points = [
        {"x": float(point.get("x_pct") or 0), "y": float(point.get("y_pct") or 0)}
        for point in (connection.get("path_points") or [])
        if isinstance(point, dict)
    ]
    route_points = _connection_route_points_for_edit(connection)
    has_route = bool(route_points)
    editable_points = route_points[1:-1] if len(route_points) >= 2 else path_points
    return (
        "(event) => {"
        "if (event.button !== 0) return;"
        "const hitPath = event.target && event.target.closest ? event.target.closest('.gleisplan-editor-connection-hit-path') : null;"
        f"if (!hitPath || hitPath.dataset.connectionId !== String({connection_id})) return;"
        "event.preventDefault();"
        "event.stopPropagation();"
        "const clickNow = Date.now();"
        "const lastClick = Number.parseFloat(hitPath.dataset.gleisplanLastClickAt || '0') || 0;"
        "const isDoubleClick = (event.detail || 0) > 1 || (lastClick && clickNow - lastClick < 360);"
        "hitPath.dataset.gleisplanLastClickAt = String(clickNow);"
        "if (isDoubleClick) {"
        "hitPath.dataset.gleisplanEditOpening = String(clickNow);"
        "emit({connection_id: " + str(connection_id) + ", mode: 'edit'});"
        "return;"
        "}"
        "const board = hitPath.closest('.gleisplan-editor-board');"
        "if (!board) return;"
        "const rect = board.getBoundingClientRect();"
        f"const connectionId = {connection_id};"
        f"const hasRoute = {'true' if has_route else 'false'};"
        f"const initialPathPoints = {json.dumps(editable_points, ensure_ascii=True)};"
        "const path = board.querySelector(`.gleisplan-editor-connection-path[data-connection-id='${connectionId}']`);"
        "const pathHitbox = board.querySelector(`.gleisplan-editor-connection-hit-path[data-connection-id='${connectionId}']`);"
        "const label = board.querySelector(`.gleisplan-editor-connection-label[data-connection-id='${connectionId}']`);"
        "const svg = path ? path.closest('.gleisplan-editor-connection-svg') : (pathHitbox ? pathHitbox.closest('.gleisplan-editor-connection-svg') : null);"
        "const selectConnection = () => {"
        "board.querySelectorAll('.is-connection-selected').forEach((node) => node.classList.remove('is-connection-selected'));"
        "[svg, path, pathHitbox, label].forEach((node) => { if (node) node.classList.add('is-connection-selected'); });"
        "board.querySelectorAll(`.gleisplan-connection-path-point-handle[data-connection-id='${connectionId}']`).forEach((node) => node.classList.add('is-connection-selected'));"
        "};"
        "selectConnection();"
        "let pathPoints = initialPathPoints.map((point) => ({x: point.x, y: point.y}));"
        "try {"
        "const storedSource = path || pathHitbox;"
        "const stored = storedSource ? JSON.parse(storedSource.dataset.pathPoints || storedSource.dataset.routeInnerPoints || 'null') : null;"
        "if (Array.isArray(stored)) pathPoints = stored.map((point) => ({x: Number(point.x), y: Number(point.y)}));"
        "} catch (_err) {}"
        "const originalD = path ? path.getAttribute('d') : (pathHitbox ? pathHitbox.getAttribute('d') : '');"
        "const originalSerialized = JSON.stringify(pathPoints);"
        "const originalLabelLeft = label ? label.style.left : '';"
        "const originalLabelTop = label ? label.style.top : '';"
        "const readNumber = (value, fallback) => { const parsed = Number.parseFloat(String(value || '')); return Number.isFinite(parsed) ? parsed : fallback; };"
        "const pointSource = path || pathHitbox || hitPath;"
        f"const fallbackStart = {{x:{x1:.6f}, y:{y1:.6f}}};"
        f"const fallbackEnd = {{x:{x2:.6f}, y:{y2:.6f}}};"
        "const start = {x: readNumber(pointSource ? pointSource.dataset.x1Pct : null, fallbackStart.x), y: readNumber(pointSource ? pointSource.dataset.y1Pct : null, fallbackStart.y)};"
        "const end = {x: readNumber(pointSource ? pointSource.dataset.x2Pct : null, fallbackEnd.x), y: readNumber(pointSource ? pointSource.dataset.y2Pct : null, fallbackEnd.y)};"
        "const startClientX = event.clientX;"
        "const startClientY = event.clientY;"
        "const clicked = {x: ((event.clientX - rect.left) / rect.width) * 100, y: ((event.clientY - rect.top) / rect.height) * 100};"
        "const distanceToSegment = (p, a, b) => {"
        "const dx = b.x - a.x;"
        "const dy = b.y - a.y;"
        "const len = (dx * dx) + (dy * dy);"
        "if (len <= 0.000001) return ((p.x - a.x) ** 2) + ((p.y - a.y) ** 2);"
        "const t = Math.max(0, Math.min(1, (((p.x - a.x) * dx) + ((p.y - a.y) * dy)) / len));"
        "const px = a.x + (dx * t);"
        "const py = a.y + (dy * t);"
        "return ((p.x - px) ** 2) + ((p.y - py) ** 2);"
        "};"
        "const basePoints = [start, ...pathPoints, end];"
        "let insertIndex = pathPoints.length;"
        "let bestDistance = Number.POSITIVE_INFINITY;"
        "for (let i = 0; i < basePoints.length - 1; i += 1) {"
        "const distance = distanceToSegment(clicked, basePoints[i], basePoints[i + 1]);"
        "if (distance < bestDistance) { bestDistance = distance; insertIndex = i; }"
        "}"
        "let handle = null;"
        "let pointInserted = false;"
        "const catmull = (pts, t) => {"
        "if (pts.length <= 1) return pts[0] || {x:0,y:0};"
        "const segments = pts.length - 1;"
        "const raw = Math.max(0, Math.min(1, t)) * segments;"
        "const i = Math.min(segments - 1, Math.floor(raw));"
        "const lt = raw - i;"
        "const p0 = pts[i - 1] || pts[i];"
        "const p1 = pts[i];"
        "const p2 = pts[i + 1];"
        "const p3 = pts[i + 2] || p2;"
        "const tt = lt * lt;"
        "const ttt = tt * lt;"
        "return {x: 0.5*((2*p1.x)+(-p0.x+p2.x)*lt+(2*p0.x-5*p1.x+4*p2.x-p3.x)*tt+(-p0.x+3*p1.x-3*p2.x+p3.x)*ttt),"
        "y: 0.5*((2*p1.y)+(-p0.y+p2.y)*lt+(2*p0.y-5*p1.y+4*p2.y-p3.y)*tt+(-p0.y+3*p1.y-3*p2.y+p3.y)*ttt)};"
        "};"
        "const buildPath = () => {"
        "const pts = [start, ...pathPoints, end];"
        "if (pts.length === 2) return `M ${pts[0].x.toFixed(3)} ${pts[0].y.toFixed(3)} L ${pts[1].x.toFixed(3)} ${pts[1].y.toFixed(3)}`;"
        "let d = `M ${pts[0].x.toFixed(3)} ${pts[0].y.toFixed(3)}`;"
        "for (let i = 0; i < pts.length - 1; i += 1) {"
        "const p0 = pts[i - 1] || pts[i];"
        "const p1 = pts[i];"
        "const p2 = pts[i + 1];"
        "const p3 = pts[i + 2] || p2;"
        "const c1x = p1.x + ((p2.x - p0.x) / 6);"
        "const c1y = p1.y + ((p2.y - p0.y) / 6);"
        "const c2x = p2.x - ((p3.x - p1.x) / 6);"
        "const c2y = p2.y - ((p3.y - p1.y) / 6);"
        "d += ` C ${c1x.toFixed(3)} ${c1y.toFixed(3)} ${c2x.toFixed(3)} ${c2y.toFixed(3)} ${p2.x.toFixed(3)} ${p2.y.toFixed(3)}`;"
        "}"
        "return d;"
        "};"
        "const renderPath = () => {"
        "const d = buildPath();"
        "const serialized = JSON.stringify(pathPoints);"
        "if (path) { path.setAttribute('d', d); path.dataset.pathPoints = serialized; path.dataset.routeInnerPoints = serialized; }"
        "if (pathHitbox) { pathHitbox.setAttribute('d', d); pathHitbox.dataset.pathPoints = serialized; pathHitbox.dataset.routeInnerPoints = serialized; }"
        "};"
        "const setPoint = (x, y) => {"
        "if (!pointInserted) {"
        "pathPoints.splice(insertIndex, 0, clicked);"
        "handle = document.createElement('div');"
        "handle.className = 'gleisplan-connection-path-point-handle is-dragging is-connection-selected';"
        "handle.dataset.connectionId = String(connectionId);"
        "board.appendChild(handle);"
        "handle.addEventListener('pointerdown', startHandleDrag);"
        "pointInserted = true;"
        "}"
        "const px = Math.max(0, Math.min(100, x));"
        "const py = Math.max(0, Math.min(100, y));"
        "pathPoints[insertIndex] = {x: px, y: py};"
        "handle.style.left = px.toFixed(3) + '%';"
        "handle.style.top = py.toFixed(3) + '%';"
        "handle.dataset.gleisplanX = px.toFixed(3);"
        "handle.dataset.gleisplanY = py.toFixed(3);"
        "renderPath();"
        "if (label) {"
        "const mid = catmull([start, ...pathPoints, end], 0.5);"
        "label.style.left = mid.x.toFixed(3) + '%';"
        "label.style.top = mid.y.toFixed(3) + '%';"
        "}"
        "};"
        "let moved = false;"
        "const move = (ev) => {"
        "const clientDeltaX = ev.clientX - startClientX;"
        "const clientDeltaY = ev.clientY - startClientY;"
        "const distance = Math.sqrt((clientDeltaX * clientDeltaX) + (clientDeltaY * clientDeltaY));"
        "if (!moved && distance <= 3) return;"
        "moved = true;"
        "const x = ((ev.clientX - rect.left) / rect.width) * 100;"
        "const y = ((ev.clientY - rect.top) / rect.height) * 100;"
        "setPoint(x, y);"
        "};"
        "let saved = false;"
        "const up = () => {"
        "document.removeEventListener('pointermove', move);"
        "document.removeEventListener('pointerup', up);"
        "document.removeEventListener('pointercancel', up);"
        "if (handle) handle.classList.remove('is-dragging');"
        "if (!moved) {"
        "if (pointInserted) pathPoints.splice(insertIndex, 1);"
        "if (path && originalD) { path.setAttribute('d', originalD); path.dataset.pathPoints = originalSerialized; }"
        "if (pathHitbox && originalD) { pathHitbox.setAttribute('d', originalD); pathHitbox.dataset.pathPoints = originalSerialized; }"
        "if (handle) handle.remove();"
        "if (label) {"
        "label.style.left = originalLabelLeft;"
        "label.style.top = originalLabelTop;"
        "}"
        "return;"
        "}"
        "const x = Number.parseFloat(handle.dataset.gleisplanX || clicked.x.toFixed(3));"
        "const y = Number.parseFloat(handle.dataset.gleisplanY || clicked.y.toFixed(3));"
        "if (saved) {"
        "emit({connection_id: connectionId, point_index: hasRoute ? insertIndex + 1 : insertIndex, x_pct: x, y_pct: y, mode: 'update'});"
        "} else {"
        "saved = true;"
        "emit({connection_id: connectionId, x_pct: x, y_pct: y, insert_index: hasRoute ? insertIndex + 1 : insertIndex});"
        "}"
        "};"
        "const startHandleDrag = (startEvent) => {"
        "if (startEvent.button !== 0) return;"
        "startEvent.preventDefault();"
        "startEvent.stopPropagation();"
        "selectConnection();"
        "handle.classList.add('is-dragging');"
        "document.addEventListener('pointermove', move);"
        "document.addEventListener('pointerup', up);"
        "move(startEvent);"
        "};"
        "document.addEventListener('pointermove', move);"
        "document.addEventListener('pointerup', up);"
        "document.addEventListener('pointercancel', up);"
        "}"
    )


def _move_connection_path_point_js_handler(connection: dict[str, Any], point_index: int) -> str:
    connection_id = int(connection.get("id") or 0)
    x1 = float(connection.get("x_pct") or 0)
    y1 = float(connection.get("y_pct") or 0)
    x2 = float(connection.get("x2_pct") if connection.get("x2_pct") is not None else x1)
    y2 = float(connection.get("y2_pct") if connection.get("y2_pct") is not None else y1)
    path_points = [
        {"x": float(point.get("x_pct") or 0), "y": float(point.get("y_pct") or 0)}
        for point in (connection.get("path_points") or [])
        if isinstance(point, dict)
    ]
    route_points = _connection_route_points_for_edit(connection)
    has_route = bool(route_points)
    editable_points = route_points[1:-1] if len(route_points) >= 2 else path_points
    client_point_index = int(point_index) - 1 if has_route else int(point_index)
    return (
        "(event) => {"
        "if (event.button !== 0) return;"
        "event.preventDefault();"
        "event.stopPropagation();"
        "const handle = event.currentTarget;"
        "const board = handle.closest('.gleisplan-editor-board');"
        "if (!board) return;"
        "const rect = board.getBoundingClientRect();"
        f"const connectionId = {connection_id};"
        f"const pointIndex = {client_point_index};"
        f"const emitPointIndex = {int(point_index)};"
        f"const initialPathPoints = {json.dumps(editable_points, ensure_ascii=True)};"
        "const path = board.querySelector(`.gleisplan-editor-connection-path[data-connection-id='${connectionId}']`);"
        "const pathHitbox = board.querySelector(`.gleisplan-editor-connection-hit-path[data-connection-id='${connectionId}']`);"
        "const label = board.querySelector(`.gleisplan-editor-connection-label[data-connection-id='${connectionId}']`);"
        "const svg = path ? path.closest('.gleisplan-editor-connection-svg') : (pathHitbox ? pathHitbox.closest('.gleisplan-editor-connection-svg') : null);"
        "board.querySelectorAll('.is-connection-selected').forEach((node) => node.classList.remove('is-connection-selected'));"
        "[svg, path, pathHitbox, label].forEach((node) => { if (node) node.classList.add('is-connection-selected'); });"
        "board.querySelectorAll(`.gleisplan-connection-path-point-handle[data-connection-id='${connectionId}']`).forEach((node) => node.classList.add('is-connection-selected'));"
        "let pathPoints = initialPathPoints.map((point) => ({x: point.x, y: point.y}));"
        "try {"
        "const storedSource = path || pathHitbox;"
        "const stored = storedSource ? JSON.parse(storedSource.dataset.pathPoints || storedSource.dataset.routeInnerPoints || 'null') : null;"
        "if (Array.isArray(stored)) pathPoints = stored.map((point) => ({x: Number(point.x), y: Number(point.y)}));"
        "} catch (_err) {}"
        "const readNumber = (value, fallback) => { const parsed = Number.parseFloat(String(value || '')); return Number.isFinite(parsed) ? parsed : fallback; };"
        "const pointSource = path || pathHitbox;"
        f"const fallbackStart = {{x:{x1:.6f}, y:{y1:.6f}}};"
        f"const fallbackEnd = {{x:{x2:.6f}, y:{y2:.6f}}};"
        "const start = {x: readNumber(pointSource ? pointSource.dataset.x1Pct : null, fallbackStart.x), y: readNumber(pointSource ? pointSource.dataset.y1Pct : null, fallbackStart.y)};"
        "const end = {x: readNumber(pointSource ? pointSource.dataset.x2Pct : null, fallbackEnd.x), y: readNumber(pointSource ? pointSource.dataset.y2Pct : null, fallbackEnd.y)};"
        "const catmull = (pts, t) => {"
        "if (pts.length <= 1) return pts[0] || {x:0,y:0};"
        "const segments = pts.length - 1;"
        "const raw = Math.max(0, Math.min(1, t)) * segments;"
        "const i = Math.min(segments - 1, Math.floor(raw));"
        "const lt = raw - i;"
        "const p0 = pts[i - 1] || pts[i];"
        "const p1 = pts[i];"
        "const p2 = pts[i + 1];"
        "const p3 = pts[i + 2] || p2;"
        "const tt = lt * lt;"
        "const ttt = tt * lt;"
        "return {x: 0.5*((2*p1.x)+(-p0.x+p2.x)*lt+(2*p0.x-5*p1.x+4*p2.x-p3.x)*tt+(-p0.x+3*p1.x-3*p2.x+p3.x)*ttt),"
        "y: 0.5*((2*p1.y)+(-p0.y+p2.y)*lt+(2*p0.y-5*p1.y+4*p2.y-p3.y)*tt+(-p0.y+3*p1.y-3*p2.y+p3.y)*ttt)};"
        "};"
        "const buildPath = () => {"
        "const pts = [start, ...pathPoints, end];"
        "if (pts.length === 2) return `M ${pts[0].x.toFixed(3)} ${pts[0].y.toFixed(3)} L ${pts[1].x.toFixed(3)} ${pts[1].y.toFixed(3)}`;"
        "let d = `M ${pts[0].x.toFixed(3)} ${pts[0].y.toFixed(3)}`;"
        "for (let i = 0; i < pts.length - 1; i += 1) {"
        "const p0 = pts[i - 1] || pts[i];"
        "const p1 = pts[i];"
        "const p2 = pts[i + 1];"
        "const p3 = pts[i + 2] || p2;"
        "const c1x = p1.x + ((p2.x - p0.x) / 6);"
        "const c1y = p1.y + ((p2.y - p0.y) / 6);"
        "const c2x = p2.x - ((p3.x - p1.x) / 6);"
        "const c2y = p2.y - ((p3.y - p1.y) / 6);"
        "d += ` C ${c1x.toFixed(3)} ${c1y.toFixed(3)} ${c2x.toFixed(3)} ${c2y.toFixed(3)} ${p2.x.toFixed(3)} ${p2.y.toFixed(3)}`;"
        "}"
        "return d;"
        "};"
        "const renderPath = () => {"
        "const d = buildPath();"
        "const serialized = JSON.stringify(pathPoints);"
        "if (path) { path.setAttribute('d', d); path.dataset.pathPoints = serialized; path.dataset.routeInnerPoints = serialized; }"
        "if (pathHitbox) { pathHitbox.setAttribute('d', d); pathHitbox.dataset.pathPoints = serialized; pathHitbox.dataset.routeInnerPoints = serialized; }"
        "};"
        "const setPoint = (x, y) => {"
        "const px = Math.max(0, Math.min(100, x));"
        "const py = Math.max(0, Math.min(100, y));"
        "if (!pathPoints[pointIndex]) return;"
        "pathPoints[pointIndex] = {x: px, y: py};"
        "handle.style.left = px.toFixed(3) + '%';"
        "handle.style.top = py.toFixed(3) + '%';"
        "handle.dataset.gleisplanX = px.toFixed(3);"
        "handle.dataset.gleisplanY = py.toFixed(3);"
        "renderPath();"
        "if (label) {"
        "const mid = catmull([start, ...pathPoints, end], 0.5);"
        "label.style.left = mid.x.toFixed(3) + '%';"
        "label.style.top = mid.y.toFixed(3) + '%';"
        "}"
        "};"
        "handle.classList.add('is-dragging');"
        "const move = (ev) => {"
        "const x = ((ev.clientX - rect.left) / rect.width) * 100;"
        "const y = ((ev.clientY - rect.top) / rect.height) * 100;"
        "setPoint(x, y);"
        "};"
        "const up = () => {"
        "document.removeEventListener('pointermove', move);"
        "document.removeEventListener('pointerup', up);"
        "handle.classList.remove('is-dragging');"
        "const x = Number.parseFloat(handle.dataset.gleisplanX || '0');"
        "const y = Number.parseFloat(handle.dataset.gleisplanY || '0');"
        "emit({connection_id: connectionId, point_index: emitPointIndex, x_pct: x, y_pct: y});"
        "};"
        "document.addEventListener('pointermove', move);"
        "document.addEventListener('pointerup', up);"
        "move(event);"
        "}"
    )


def _delete_connection_path_point_js_handler(connection_id: int, point_index: int) -> str:
    return (
        "(event) => {"
        "event.preventDefault();"
        "event.stopPropagation();"
        f"emit({{connection_id: {int(connection_id)}, point_index: {int(point_index)}}});"
        "}"
    )


def _draw_street_js_handler() -> str:
    return (
        "(event) => {"
        "if (event.button !== 0) return;"
        "const board = event.currentTarget;"
        "if (event.target !== board) return;"
        "event.preventDefault();"
        "const rect = board.getBoundingClientRect();"
        "const thicknessPct = 3.0;"
        "const startClientX = event.clientX;"
        "const startClientY = event.clientY;"
        "const startX = ((event.clientX - rect.left) / rect.width) * 100;"
        "const startY = ((event.clientY - rect.top) / rect.height) * 100;"
        "const topY = Math.max(0, Math.min(97, startY - (thicknessPct / 2)));"
        "const preview = document.createElement('div');"
        "preview.className = 'gleisplan-editor-street-preview';"
        "preview.style.left = startX.toFixed(3) + '%';"
        "preview.style.top = topY.toFixed(3) + '%';"
        "board.appendChild(preview);"
        "let lengthPct = 0;"
        "let rotation = 0;"
        "const move = (ev) => {"
        "const dx = ev.clientX - startClientX;"
        "const dy = ev.clientY - startClientY;"
        "const lengthPx = Math.sqrt((dx * dx) + (dy * dy));"
        "lengthPct = (lengthPx / rect.width) * 100;"
        "rotation = Math.atan2(dy, dx) * 180 / Math.PI;"
        "preview.style.width = Math.max(0, lengthPct).toFixed(3) + '%';"
        "preview.style.transform = `rotate(${rotation.toFixed(3)}deg)`;"
        "};"
        "const up = () => {"
        "document.removeEventListener('pointermove', move);"
        "document.removeEventListener('pointerup', up);"
        "preview.remove();"
        "if (lengthPct >= 2) {"
        "emit({x: startX, y: topY, length: lengthPct, rotation: rotation});"
        "}"
        "};"
        "document.addEventListener('pointermove', move);"
        "document.addEventListener('pointerup', up);"
        "move(event);"
        "}"
    )


def _clear_gleisplan_config_selection_js_handler() -> str:
    return (
        "(event) => {"
        "if (event.button !== 0) return;"
        "const board = event.currentTarget;"
        "if (event.target !== board) return;"
        "event.preventDefault();"
        "document.querySelectorAll('.gleisplan-editor-item.is-selected, .gleisplan-editor-item.is-connection-source, .cfg-gleisplan-list-row.is-selected, .cfg-gleisplan-list-row.is-connection-source').forEach((node) => {"
        "node.classList.remove('is-selected');"
        "node.classList.remove('is-connection-source');"
        "});"
        "document.querySelectorAll('.gleisplan-editor-connection-svg.is-connected-selected, .gleisplan-editor-connection-path.is-connected-selected, .gleisplan-editor-connection-hit-path.is-connected-selected, .gleisplan-editor-connection-label.is-connected-selected').forEach((node) => node.classList.remove('is-connected-selected'));"
        "document.querySelectorAll('.is-connection-selected').forEach((node) => node.classList.remove('is-connection-selected'));"
        "emit({});"
        "}"
    )


def _dblclick_editor_item_js_handler() -> str:
    return (
        "(event) => {"
        "event.preventDefault();"
        "event.stopPropagation();"
        "const el = event.currentTarget;"
        "const openedAt = Number.parseFloat(el.dataset.gleisplanEditOpening || '0') || 0;"
        "if (openedAt && Date.now() - openedAt < 800) return;"
        "el.dataset.gleisplanEditOpening = String(Date.now());"
        "emit({});"
        "}"
    )


def _dblclick_editor_connection_js_handler(connection_id: int) -> str:
    return (
        "(event) => {"
        "const path = event.target && event.target.closest ? event.target.closest('.gleisplan-editor-connection-hit-path, .gleisplan-editor-connection-path') : null;"
        f"if (!path || path.dataset.connectionId !== String({int(connection_id)})) return;"
        "event.preventDefault();"
        "event.stopPropagation();"
        "const openedAt = Number.parseFloat(path.dataset.gleisplanEditOpening || '0') || 0;"
        "if (openedAt && Date.now() - openedAt < 800) return;"
        "path.dataset.gleisplanEditOpening = String(Date.now());"
        "emit({});"
        "}"
    )


def _clear_gleisplan_config_selection(*, state: dict[str, Any], refresh: Callable[[], None]) -> None:
    if not str(state.get("gleisplan_selected_item") or "").strip() and not str(
        state.get("gleisplan_connection_source") or ""
    ).strip():
        return
    state["gleisplan_selected_item"] = ""
    state["gleisplan_connection_source"] = ""


def _save_gleisplan_pdf_trace_action(
    *,
    state: dict[str, Any],
    db_exec: Callable[..., Any],
    now_berlin: Callable[[], datetime],
) -> None:
    updated_at = now_berlin().isoformat(timespec="seconds")
    ok, msg = save_gleisplan_pdf_trace_settings(
        db_exec,
        _normalize_trace_settings(state.get("gleisplan_pdf_trace_settings")),
        updated_at=updated_at,
    )
    ui.notify(msg, type="positive" if ok else "warning")


def _reset_gleisplan_pdf_trace_action(
    *,
    state: dict[str, Any],
    db_exec: Callable[..., Any],
    now_berlin: Callable[[], datetime],
    refresh: Callable[[], None],
) -> None:
    updated_at = now_berlin().isoformat(timespec="seconds")
    ok, msg = reset_gleisplan_pdf_trace_settings(db_exec, updated_at=updated_at)
    state["gleisplan_pdf_trace_settings"] = load_gleisplan_pdf_trace_settings(db_exec)
    state["gleisplan_pdf_trace_loaded"] = True
    ui.notify("PDF-Kalibrierung zurückgesetzt." if ok else msg, type="positive" if ok else "warning")
    refresh()


def _backup_live_db_for_gleisplan_geometry(now_berlin: Callable[[], datetime]) -> str:
    db_path = os.path.abspath(str(DB_PATH or ""))
    if not db_path or not os.path.exists(db_path):
        raise FileNotFoundError("SQLite-Datenbank nicht gefunden.")
    timestamp = now_berlin().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(os.path.dirname(db_path), "backups")
    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(backup_dir, f"fristenplanung_before_eberswalde_pdf_geometry_{timestamp}.db")
    shutil.copy2(db_path, backup_path)
    for suffix in ("-wal", "-shm"):
        sidecar = f"{db_path}{suffix}"
        if os.path.exists(sidecar):
            shutil.copy2(sidecar, f"{backup_path}{suffix}")
    return backup_path


def _apply_eberswalde_pdf_geometry_action(
    *,
    db_exec: Callable[..., Any],
    now_berlin: Callable[[], datetime],
    refresh: Callable[[], None],
) -> None:
    try:
        backup_path = _backup_live_db_for_gleisplan_geometry(now_berlin)
        ok, msg = apply_eberswalde_pdf_trace_geometry(
            db_exec,
            updated_at=now_berlin().isoformat(timespec="seconds"),
        )
    except Exception as exc:
        ui.notify(f"Eberswalde-Geometrie nicht gespeichert: {exc}", type="negative")
        return
    ui.notify(f"{msg} Backup: {backup_path}", type="positive" if ok else "warning")
    if ok:
        refresh()


def _save_gleisplan_editor_changes_js_handler() -> str:
    return (
        "(event) => {"
        "event.preventDefault();"
        "event.stopPropagation();"
        "const items = [];"
        "try {"
        "for (let index = 0; index < window.localStorage.length; index += 1) {"
        "const key = window.localStorage.key(index);"
        "if (!key || !key.startsWith('gleisplan.pendingPosition.')) continue;"
        "const itemId = key.substring('gleisplan.pendingPosition.'.length).trim().toUpperCase();"
        "const data = JSON.parse(window.localStorage.getItem(key) || 'null');"
        "if (!itemId || !data) continue;"
        "const x = Number(data.x);"
        "const y = Number(data.y);"
        "if (!Number.isFinite(x) || !Number.isFinite(y)) continue;"
        "items.push({item_id: itemId, x: x, y: y});"
        "}"
        "} catch (_err) {}"
        "emit({items: items});"
        "}"
    )


def _save_gleisplan_editor_changes_from_event(
    event,
    *,
    state: dict[str, Any],
    db_exec: Callable[..., Any],
    now_berlin: Callable[[], datetime],
    refresh: Callable[[], None],
) -> None:
    args = event.args or {}
    raw_items = args.get("items") if isinstance(args, dict) else []
    pending_positions = state.setdefault("gleisplan_pending_positions", {})
    if not isinstance(pending_positions, dict):
        pending_positions = {}
        state["gleisplan_pending_positions"] = pending_positions
    items_by_id: dict[str, dict[str, float]] = {}
    for pending_id, pending_value in pending_positions.items():
        item_id = str(pending_id or "").strip().upper()
        if not item_id or not isinstance(pending_value, dict):
            continue
        try:
            x_pct = float(pending_value.get("x"))
            y_pct = float(pending_value.get("y"))
        except Exception:
            continue
        items_by_id[item_id] = {"x": x_pct, "y": y_pct}
    if isinstance(raw_items, list):
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            item_id = str(raw.get("item_id") or "").strip().upper()
            try:
                x_pct = float(raw.get("x"))
                y_pct = float(raw.get("y"))
            except Exception:
                continue
            if item_id:
                items_by_id[item_id] = {"x": x_pct, "y": y_pct}
    if not items_by_id:
        ui.notify("Keine ungespeicherten Gleisplan-Änderungen.", type="info")
        return
    saved_ids: list[str] = []
    for item_id, position in items_by_id.items():
        x_pct = float(position["x"])
        y_pct = float(position["y"])
        ok, msg = update_gleisplan_layout_item_position(
            db_exec,
            item_id=item_id,
            x_pct=x_pct,
            y_pct=y_pct,
            updated_at=now_berlin().isoformat(timespec="seconds"),
        )
        if ok:
            saved_ids.append(item_id)
        else:
            ui.notify(msg, type="warning")
    if not saved_ids:
        ui.notify("Keine Gleisplan-Änderungen gespeichert.", type="warning")
        return
    for item_id in saved_ids:
        pending_positions.pop(item_id, None)
    keys = json.dumps([f"gleisplan.pendingPosition.{item_id}" for item_id in saved_ids], ensure_ascii=True)
    ui.run_javascript(
        f"""
        try {{
          ({keys}).forEach((key) => window.localStorage.removeItem(key));
        }} catch (_err) {{}}
        """
    )
    ui.notify(f"{len(saved_ids)} Gleisplan-Änderung(en) gespeichert.", type="positive")
    refresh()


def _gleisplan_editor_restore_body_script() -> str:
    return """
    <script>
      (function () {
        var ROOT = window.parent || window;
        var applyPending = function () {
          try {
            var pending = {};
            ROOT.document.querySelectorAll('[data-gleisplan-item-id]').forEach(function (node) {
              var itemId = String(node.dataset.gleisplanItemId || '').trim().toUpperCase();
              if (!itemId) return;
              var raw = ROOT.localStorage.getItem('gleisplan.pendingPosition.' + itemId);
              if (!raw) return;
              var data = JSON.parse(raw);
              if (!data || !Number.isFinite(Number(data.x)) || !Number.isFinite(Number(data.y))) return;
              pending[itemId] = { x: Number(data.x), y: Number(data.y) };
              var leftValue = Number(data.x).toFixed(3) + '%';
              var topValue = Number(data.y).toFixed(3) + '%';
              var xValue = Number(data.x).toFixed(3);
              var yValue = Number(data.y).toFixed(3);
              if (node.style.left !== leftValue) node.style.left = leftValue;
              if (node.style.top !== topValue) node.style.top = topValue;
              if (node.dataset.gleisplanX !== xValue) node.dataset.gleisplanX = xValue;
              if (node.dataset.gleisplanY !== yValue) node.dataset.gleisplanY = yValue;
            });
            var readPct = function (value, fallback) {
              var parsed = Number.parseFloat(String(value || ''));
              return Number.isFinite(parsed) ? parsed : fallback;
            };
            var itemMeta = function (itemId) {
              var item = ROOT.document.querySelector('[data-gleisplan-item-id="' + itemId + '"]');
              if (!item) return null;
              var transform = String(item.style.transform || '');
              var match = transform.match(/rotate\\((-?[0-9.]+)deg\\)/);
              return {
                node: item,
                type: String(item.dataset.gleisplanItemType || '').trim().toLowerCase(),
                x: readPct(item.style.left, 0),
                y: readPct(item.style.top, 0),
                w: readPct(item.style.width, 0),
                h: readPct(item.style.height, 0),
                rotation: match ? (Number.parseFloat(match[1]) || 0) : 0,
                port2X: readPct(item.dataset.switchPort2X, 0),
                port2Y: readPct(item.dataset.switchPort2Y, 0.28),
                port3X: readPct(item.dataset.switchPort3X, 0.06),
                port3Y: readPct(item.dataset.switchPort3Y, 1.35),
              };
            };
            var localPointToBoard = function (item, localX, localY) {
              var boardNode = ROOT.document.querySelector('.gleisplan-editor-board');
              var boardRect = boardNode ? boardNode.getBoundingClientRect() : { width: 1, height: 1 };
              var scaleX = Math.max(0.000001, (boardRect.width || 1) / 100);
              var scaleY = Math.max(0.000001, (boardRect.height || 1) / 100);
              var angle = (item.rotation || 0) * Math.PI / 180;
              var cx = item.x + (item.w / 2);
              var cy = item.y + (item.h / 2);
              var dx = (localX - (item.w / 2)) * scaleX;
              var dy = (localY - (item.h / 2)) * scaleY;
              var rotatedX = (dx * Math.cos(angle)) - (dy * Math.sin(angle));
              var rotatedY = (dx * Math.sin(angle)) + (dy * Math.cos(angle));
              return {
                x: cx + (rotatedX / scaleX),
                y: cy + (rotatedY / scaleY),
              };
            };
            var shiftedSwitchPoint = function (item, port) {
              var cleanPort = String(port || '1');
              var selected;
              var opposite;
              var port1 = { x: item.w, y: item.h * 0.28 };
              var port2 = { x: item.w * item.port2X, y: item.h * item.port2Y };
              var heel = { x: port2.x + ((port1.x - port2.x) * 0.80), y: port2.y + ((port1.y - port2.y) * 0.80) };
              var port3 = { x: item.w * item.port3X, y: item.h * item.port3Y };
            if (cleanPort === '2') {
                selected = localPointToBoard(item, port2.x, port2.y);
                opposite = localPointToBoard(item, port1.x, port1.y);
              } else if (cleanPort === '3') {
                selected = localPointToBoard(item, port3.x, port3.y);
                opposite = localPointToBoard(item, heel.x, heel.y);
              } else {
                selected = localPointToBoard(item, port1.x, port1.y);
                opposite = localPointToBoard(item, port2.x, port2.y);
              }
              return selected;
            };
            var switchLeadPoint = function (item, port) {
              var cleanPort = String(port || '1');
              var selected;
              var opposite;
              var port1 = { x: item.w, y: item.h * 0.28 };
              var port2 = { x: item.w * item.port2X, y: item.h * item.port2Y };
              var heel = { x: port2.x + ((port1.x - port2.x) * 0.80), y: port2.y + ((port1.y - port2.y) * 0.80) };
              var port3 = { x: item.w * item.port3X, y: item.h * item.port3Y };
            if (cleanPort === '2') {
                selected = localPointToBoard(item, port2.x, port2.y);
                opposite = localPointToBoard(item, port1.x, port1.y);
              } else if (cleanPort === '3') {
                selected = localPointToBoard(item, port3.x, port3.y);
                opposite = localPointToBoard(item, heel.x, heel.y);
              } else {
                selected = localPointToBoard(item, port1.x, port1.y);
                opposite = localPointToBoard(item, port2.x, port2.y);
              }
              var dx = selected.x - opposite.x;
              var dy = selected.y - opposite.y;
              var length = Math.sqrt((dx * dx) + (dy * dy)) || 0;
              if (length <= 0.000001) return null;
              var lead = Math.min(1.35, length * 0.42);
              return { x: selected.x + ((dx / length) * lead), y: selected.y + ((dy / length) * lead) };
            };
            var bufferStopPoint = function (item) {
              var extension = Math.min(0.45, item.h * 0.06);
              return localPointToBoard(item, item.w / 2, item.h + extension);
            };
            var sidePoint = function (item, other) {
              var angle = (item.rotation || 0) * Math.PI / 180;
              var ux = Math.cos(angle);
              var uy = Math.sin(angle);
              var cx = item.x + (item.w / 2);
              var cy = item.y + (item.h / 2);
              var dot = ((other.x - cx) * ux) + ((other.y - cy) * uy);
              return localPointToBoard(item, dot >= 0 ? item.w : 0, item.h / 2);
            };
            var connectionPoint = function (item, otherPoint, port) {
              if (!item) return otherPoint;
              if (item.type === 'switch') return shiftedSwitchPoint(item, port);
              if (item.type === 'buffer_stop') return bufferStopPoint(item);
              if (item.type === 'hall') {
                var cells = Array.prototype.slice.call(item.node.querySelectorAll('[data-hall-track-code]'));
                var cleanPort = String(port || '').trim().toUpperCase();
                var cellIndex = cells.findIndex(function (cell) {
                  return String(cell.dataset.hallTrackCode || '').trim().toUpperCase() === cleanPort;
                });
                var columns = 2;
                var rows = Math.max(1, Math.ceil(Math.max(1, cells.length) / columns));
                var rowIndex = cellIndex >= 0 ? Math.floor(cellIndex / columns) : Math.floor(rows / 2);
                var localY = ((rowIndex + 0.5) / rows) * item.h;
                return localPointToBoard(item, otherPoint.x >= item.x + (item.w / 2) ? item.w : 0, localY);
              }
              return sidePoint(item, otherPoint);
            };
            var catmullPoint = function (pts, fraction) {
              if (!pts.length) return { x: 0, y: 0 };
              if (pts.length === 1) return pts[0];
              var segments = pts.length - 1;
              var raw = Math.max(0, Math.min(1, fraction)) * segments;
              var i = Math.min(segments - 1, Math.floor(raw));
              var lt = raw - i;
              var p0 = pts[i - 1] || pts[i];
              var p1 = pts[i];
              var p2 = pts[i + 1];
              var p3 = pts[i + 2] || p2;
              var tt = lt * lt;
              var ttt = tt * lt;
              return {
                x: 0.5 * ((2 * p1.x) + (-p0.x + p2.x) * lt + (2 * p0.x - 5 * p1.x + 4 * p2.x - p3.x) * tt + (-p0.x + 3 * p1.x - 3 * p2.x + p3.x) * ttt),
                y: 0.5 * ((2 * p1.y) + (-p0.y + p2.y) * lt + (2 * p0.y - 5 * p1.y + 4 * p2.y - p3.y) * tt + (-p0.y + 3 * p1.y - 3 * p2.y + p3.y) * ttt),
              };
            };
            var buildPath = function (x1, y1, x2, y2, curve, pathPoints, sourceLead, targetLead) {
              var pts = [{ x: x1, y: y1 }]
                .concat(sourceLead ? [sourceLead] : [], pathPoints || [], targetLead ? [targetLead] : [], [{ x: x2, y: y2 }]);
              if ((pathPoints && pathPoints.length) || sourceLead || targetLead) {
                if (pts.length === 2) return 'M ' + x1.toFixed(3) + ' ' + y1.toFixed(3) + ' L ' + x2.toFixed(3) + ' ' + y2.toFixed(3);
                var d = 'M ' + pts[0].x.toFixed(3) + ' ' + pts[0].y.toFixed(3);
                for (var i = 0; i < pts.length - 1; i += 1) {
                  var p0 = pts[i - 1] || pts[i];
                  var p1 = pts[i];
                  var p2 = pts[i + 1];
                  var p3 = pts[i + 2] || p2;
                  var c1x = p1.x + ((p2.x - p0.x) / 6);
                  var c1y = p1.y + ((p2.y - p0.y) / 6);
                  var c2x = p2.x - ((p3.x - p1.x) / 6);
                  var c2y = p2.y - ((p3.y - p1.y) / 6);
                  d += ' C ' + c1x.toFixed(3) + ' ' + c1y.toFixed(3) + ' ' + c2x.toFixed(3) + ' ' + c2y.toFixed(3) + ' ' + p2.x.toFixed(3) + ' ' + p2.y.toFixed(3);
                }
                return d;
              }
              if (Math.abs(curve || 0) < 0.001) return 'M ' + x1.toFixed(3) + ' ' + y1.toFixed(3) + ' L ' + x2.toFixed(3) + ' ' + y2.toFixed(3);
              var dx = x2 - x1;
              var dy = y2 - y1;
              var length = Math.sqrt((dx * dx) + (dy * dy)) || 1;
              var cx = ((x1 + x2) / 2) + ((-dy / length) * curve);
              var cy = ((y1 + y2) / 2) + ((dx / length) * curve);
              return 'M ' + x1.toFixed(3) + ' ' + y1.toFixed(3) + ' Q ' + cx.toFixed(3) + ' ' + cy.toFixed(3) + ' ' + x2.toFixed(3) + ' ' + y2.toFixed(3);
            };
            var metaCenter = function (meta) {
              return { x: meta.x + (meta.w / 2), y: meta.y + (meta.h / 2) };
            };
            var recalculateConnections = function (filterItemIds) {
              var filter = {};
              if (Array.isArray(filterItemIds)) {
                filterItemIds.forEach(function (itemId) {
                  var clean = String(itemId || '').trim().toUpperCase();
                  if (clean) filter[clean] = true;
                });
              } else {
                var cleanFilter = String(filterItemIds || '').trim().toUpperCase();
                if (cleanFilter) filter[cleanFilter] = true;
              }
              var hasFilter = Object.keys(filter).length > 0;
              ROOT.document.querySelectorAll('.gleisplan-editor-connection-hit-path').forEach(function (hitPath) {
                var sourceId = String(hitPath.dataset.sourceItemId || '').trim().toUpperCase();
                var targetId = String(hitPath.dataset.targetItemId || '').trim().toUpperCase();
                if (hasFilter && !filter[sourceId] && !filter[targetId]) return;
                var connectionId = hitPath.dataset.connectionId;
                var path = ROOT.document.querySelector('.gleisplan-editor-connection-path[data-connection-id="' + connectionId + '"]');
                var source = path || hitPath;
                var x1 = readPct(source.dataset.x1Pct, 0);
                var y1 = readPct(source.dataset.y1Pct, 0);
                var x2 = readPct(source.dataset.x2Pct, x1);
                var y2 = readPct(source.dataset.y2Pct, y1);
                var sourceMeta = itemMeta(sourceId);
                var targetMeta = itemMeta(targetId);
                var sourceLead = source.dataset.hasSourceLead === '1'
                  ? { x: readPct(source.dataset.sourceLeadXPct, 0), y: readPct(source.dataset.sourceLeadYPct, 0) }
                  : null;
                var targetLead = source.dataset.hasTargetLead === '1'
                  ? { x: readPct(source.dataset.targetLeadXPct, 0), y: readPct(source.dataset.targetLeadYPct, 0) }
                  : null;
                if (sourceMeta) {
                  var p1 = connectionPoint(sourceMeta, targetMeta ? metaCenter(targetMeta) : { x: x2, y: y2 }, hitPath.dataset.sourcePort || '');
                  x1 = p1.x; y1 = p1.y;
                  sourceLead = sourceMeta.type === 'switch' ? switchLeadPoint(sourceMeta, hitPath.dataset.sourcePort || '') : null;
                }
                if (targetMeta) {
                  var p2 = connectionPoint(targetMeta, sourceMeta ? metaCenter(sourceMeta) : { x: x1, y: y1 }, hitPath.dataset.targetPort || '');
                  x2 = p2.x; y2 = p2.y;
                  targetLead = targetMeta.type === 'switch' ? switchLeadPoint(targetMeta, hitPath.dataset.targetPort || '') : null;
                }
                var pathPoints = [];
                try {
                  var stored = JSON.parse(source.dataset.pathPoints || '[]');
                  if (Array.isArray(stored)) {
                    pathPoints = stored.map(function (point) { return { x: Number(point.x), y: Number(point.y) }; });
                  }
                } catch (e) {}
                var curve = readPct(source.dataset.curvePct, 0);
                var d = buildPath(x1, y1, x2, y2, curve, pathPoints, sourceLead, targetLead);
                [path, hitPath].forEach(function (node) {
                  if (!node) return;
                  if (node.getAttribute('d') !== d) node.setAttribute('d', d);
                  if (node.dataset.x1Pct !== x1.toFixed(3)) node.dataset.x1Pct = x1.toFixed(3);
                  if (node.dataset.y1Pct !== y1.toFixed(3)) node.dataset.y1Pct = y1.toFixed(3);
                  if (node.dataset.x2Pct !== x2.toFixed(3)) node.dataset.x2Pct = x2.toFixed(3);
                  if (node.dataset.y2Pct !== y2.toFixed(3)) node.dataset.y2Pct = y2.toFixed(3);
                  if (node.dataset.hasSourceLead !== (sourceLead ? '1' : '0')) node.dataset.hasSourceLead = sourceLead ? '1' : '0';
                  if (node.dataset.hasTargetLead !== (targetLead ? '1' : '0')) node.dataset.hasTargetLead = targetLead ? '1' : '0';
                  if (sourceLead) {
                    if (node.dataset.sourceLeadXPct !== sourceLead.x.toFixed(3)) node.dataset.sourceLeadXPct = sourceLead.x.toFixed(3);
                    if (node.dataset.sourceLeadYPct !== sourceLead.y.toFixed(3)) node.dataset.sourceLeadYPct = sourceLead.y.toFixed(3);
                  }
                  if (targetLead) {
                    if (node.dataset.targetLeadXPct !== targetLead.x.toFixed(3)) node.dataset.targetLeadXPct = targetLead.x.toFixed(3);
                    if (node.dataset.targetLeadYPct !== targetLead.y.toFixed(3)) node.dataset.targetLeadYPct = targetLead.y.toFixed(3);
                  }
                });
                var label = ROOT.document.querySelector('.gleisplan-editor-connection-label[data-connection-id="' + connectionId + '"]');
                if (label) {
                  var mid;
                  if (pathPoints.length || sourceLead || targetLead) {
                    mid = catmullPoint(
                      [{ x: x1, y: y1 }].concat(sourceLead ? [sourceLead] : [], pathPoints, targetLead ? [targetLead] : [], [{ x: x2, y: y2 }]),
                      0.5
                    );
                  } else {
                    var ldx = x2 - x1;
                    var ldy = y2 - y1;
                    var llen = Math.sqrt((ldx * ldx) + (ldy * ldy)) || 1;
                    var cx2 = ((x1 + x2) / 2) + ((-ldy / llen) * curve);
                    var cy2 = ((y1 + y2) / 2) + ((ldx / llen) * curve);
                    mid = Math.abs(curve || 0) < 0.001
                      ? { x: (x1 + x2) / 2, y: (y1 + y2) / 2 }
                      : { x: (0.25 * x1) + (0.5 * cx2) + (0.25 * x2), y: (0.25 * y1) + (0.5 * cy2) + (0.25 * y2) };
                  }
                  var labelLeft = mid.x.toFixed(3) + '%';
                  var labelTop = mid.y.toFixed(3) + '%';
                  if (label.style.left !== labelLeft) label.style.left = labelLeft;
                  if (label.style.top !== labelTop) label.style.top = labelTop;
                }
              });
            };
            ROOT.__gleisplanRecalculateEditorConnections = recalculateConnections;
            var pendingIds = Object.keys(pending);
            recalculateConnections(pendingIds.length ? pendingIds : null);
          } catch (e) {}
        };
        var scheduleApplyPending = function () {
          if (ROOT.__gleisplanPendingApplyScheduled) return;
          ROOT.__gleisplanPendingApplyScheduled = true;
          ROOT.requestAnimationFrame(function () {
            ROOT.__gleisplanPendingApplyScheduled = false;
            applyPending();
          });
        };
        ROOT.__gleisplanApplyPendingPositions = applyPending;
        applyPending();
        ROOT.requestAnimationFrame(applyPending);
        ROOT.setTimeout(applyPending, 80);
        if (ROOT.__gleisplanPendingPositionObserver) {
          try { ROOT.__gleisplanPendingPositionObserver.disconnect(); } catch (_err) {}
          ROOT.__gleisplanPendingPositionObserver = null;
        }
        if (!ROOT.__gleisplanPendingPositionObserver) {
          ROOT.__gleisplanPendingPositionObserver = new MutationObserver(function (mutations) {
            var shouldApply = false;
            for (var index = 0; index < mutations.length; index += 1) {
              var mutation = mutations[index];
              if (mutation.type === 'childList') {
                shouldApply = mutation.addedNodes && mutation.addedNodes.length > 0;
              }
              if (shouldApply) break;
            }
            if (shouldApply) scheduleApplyPending();
          });
          ROOT.__gleisplanPendingPositionObserver.observe(ROOT.document.documentElement, {
            childList: true,
            subtree: true
          });
        }
      })();
    </script>
    """


def _render_editor_connection(
    connection: dict[str, Any],
    *,
    db_exec: Callable[..., Any],
    now_berlin: Callable[[], datetime],
    item_options: dict[str, str],
    items_by_id: dict[str, dict[str, Any]],
    selected_item: str = "",
    refresh: Callable[[], None],
) -> None:
    connection_id = int(connection.get("id") or 0)
    connection_type = str(connection.get("connection_type") or "track").strip().lower()
    source_id = str(connection.get("source_item_id") or "").strip().upper()
    target_id = str(connection.get("target_item_id") or "").strip().upper()
    selected_id = str(selected_item or "").strip().upper()
    svg_classes = "gleisplan-editor-connection-svg"
    if connection_type == "street":
        svg_classes += " cfg-street"
    if selected_id and selected_id in {source_id, target_id}:
        svg_classes += " is-connected-selected"
    path_d = _connection_path_d(connection)
    has_fixed_route = bool(connection.get("route"))
    route_points_for_edit = _connection_route_points_for_edit(connection)
    editor_points = route_points_for_edit[1:-1] if has_fixed_route and len(route_points_for_edit) >= 2 else [
        {"x": float(point.get("x_pct") or 0), "y": float(point.get("y_pct") or 0)}
        for point in (connection.get("path_points") or [])
        if isinstance(point, dict)
    ]
    path_points_json = json.dumps(editor_points, ensure_ascii=True)
    x1 = float(connection.get("x_pct") or 0)
    y1 = float(connection.get("y_pct") or 0)
    x2 = float(connection.get("x2_pct") if connection.get("x2_pct") is not None else x1)
    y2 = float(connection.get("y2_pct") if connection.get("y2_pct") is not None else y1)
    curve = float(connection.get("curve_pct") or 0)
    path_data_attrs = (
        f'data-connection-id="{connection_id}" '
        f'data-source-item-id="{str(connection.get("source_item_id") or "").strip().upper()}" '
        f'data-target-item-id="{str(connection.get("target_item_id") or "").strip().upper()}" '
        f'data-source-port="{str(connection.get("source_port") or "").strip()}" '
        f'data-target-port="{str(connection.get("target_port") or "").strip()}" '
        f'data-x1-pct="{x1:.3f}" data-y1-pct="{y1:.3f}" '
        f'data-x2-pct="{x2:.3f}" data-y2-pct="{y2:.3f}" '
        f'data-source-lead-x-pct="{float(connection.get("source_lead_x_pct") or 0):.3f}" '
        f'data-source-lead-y-pct="{float(connection.get("source_lead_y_pct") or 0):.3f}" '
        f'data-target-lead-x-pct="{float(connection.get("target_lead_x_pct") or 0):.3f}" '
        f'data-target-lead-y-pct="{float(connection.get("target_lead_y_pct") or 0):.3f}" '
        f'data-has-source-lead="{"1" if connection.get("source_lead_x_pct") is not None and connection.get("source_lead_y_pct") is not None else "0"}" '
        f'data-has-target-lead="{"1" if connection.get("target_lead_x_pct") is not None and connection.get("target_lead_y_pct") is not None else "0"}" '
        f'data-fixed-route="{"1" if has_fixed_route else "0"}" '
        f'data-route-smooth="{"1" if bool((connection.get("route") or {}).get("smooth")) else "0"}" '
        f"data-curve-pct=\"{curve:.3f}\" data-path-points='{path_points_json}' data-route-inner-points='{path_points_json}'"
    )
    svg_el = ui.html(
        (
        f'<svg class="{svg_classes}" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">'
            f'<path class="gleisplan-editor-connection-hit-path" {path_data_attrs} d="{path_d}" />'
            f'<path class="gleisplan-editor-connection-path" {path_data_attrs} d="{path_d}" />'
            "</svg>"
        ),
        sanitize=False,
    )
    label = str(connection.get("label") or "").strip()
    if label:
        label_classes = "gleisplan-editor-connection-label"
        if selected_id and selected_id in {source_id, target_id}:
            label_classes += " is-connected-selected"
        ui.label(label).classes(label_classes).style(_connection_label_style(connection)).props(
            f'data-connection-id="{connection_id}"'
        )
    if connection_id > 0:
        svg_el.on(
            "dblclick",
            lambda event, row=dict(connection): _open_gleisplan_connection_dialog(
                db_exec=db_exec,
                now_berlin=now_berlin,
                item_options=item_options,
                items_by_id=items_by_id,
                refresh=refresh,
                edit_connection=row,
            ),
            js_handler=_dblclick_editor_connection_js_handler(connection_id),
        )
        if connection_type != "street":
            svg_el.on(
                "pointerdown",
                lambda event, row=dict(connection): _add_gleisplan_connection_path_point_from_event(
                    event,
                    db_exec=db_exec,
                    now_berlin=now_berlin,
                    refresh=refresh,
                    item_options=item_options,
                    items_by_id=items_by_id,
                    edit_connection=row,
                ),
                js_handler=_add_connection_path_point_js_handler(connection),
            )
            if has_fixed_route:
                editable_points = _connection_editable_route_point_indices(connection)
            else:
                editable_points = [
                    (point_index, point)
                    for point_index, point in enumerate(connection.get("path_points") or [])
                    if isinstance(point, dict)
                ]
            if editable_points:
                for point_index, point in editable_points:
                    ui.element("div").classes("gleisplan-connection-path-point-handle").props(
                        f'data-connection-id="{connection_id}"'
                    ).style(_connection_path_point_style(point)).on(
                        "pointerdown",
                        lambda event: _update_gleisplan_connection_path_point_from_event(
                            event,
                            db_exec=db_exec,
                            now_berlin=now_berlin,
                            refresh=refresh,
                        ),
                        js_handler=_move_connection_path_point_js_handler(connection, point_index),
                    ).on(
                        "contextmenu",
                        lambda event: _delete_gleisplan_connection_path_point_from_event(
                            event,
                            db_exec=db_exec,
                            now_berlin=now_berlin,
                            refresh=refresh,
                        ),
                        js_handler=_delete_connection_path_point_js_handler(connection_id, point_index),
                    )


def _render_gleisplan_config(
    *,
    state: dict[str, Any],
    db_exec: Callable[..., Any],
    now_berlin: Callable[[], datetime],
    go_home: Callable[[], None],
    refresh: Callable[[], None],
) -> None:
    layout_items = [dict(item) for item in load_gleisplan_layout_items(db_exec)]
    pending_positions = state.setdefault("gleisplan_pending_positions", {})
    if not isinstance(pending_positions, dict):
        pending_positions = {}
        state["gleisplan_pending_positions"] = pending_positions
    valid_item_ids = {str(item.get("item_id") or "").strip().upper() for item in layout_items}
    for pending_id in list(pending_positions.keys()):
        if str(pending_id or "").strip().upper() not in valid_item_ids:
            pending_positions.pop(pending_id, None)
    for item in layout_items:
        item_id_for_pending = str(item.get("item_id") or "").strip().upper()
        pending = pending_positions.get(item_id_for_pending)
        if not isinstance(pending, dict):
            continue
        try:
            item["x_pct"] = float(pending.get("x"))
            item["y_pct"] = float(pending.get("y"))
        except Exception:
            continue
    connections = load_gleisplan_connections(db_exec, layout_items=layout_items)
    hall_tracks = load_gleisplan_hall_tracks(db_exec)
    items_by_id = {str(item.get("item_id") or "").strip().upper(): dict(item) for item in layout_items}
    item_options = {
        str(item.get("item_id") or ""): f"{item.get('label') or item.get('item_id')} ({item.get('item_type')})"
        for item in layout_items
        if str(item.get("item_id") or "").strip()
    }
    selected_item = str(state.get("gleisplan_selected_item") or "").strip().upper()
    connection_source = str(state.get("gleisplan_connection_source") or "").strip().upper()
    if selected_item and selected_item not in items_by_id:
        selected_item = ""
        state["gleisplan_selected_item"] = ""
    if connection_source and connection_source not in items_by_id:
        connection_source = ""
        state["gleisplan_connection_source"] = ""
    draw_street = bool(state.get("gleisplan_draw_street"))
    trace_settings = _get_gleisplan_trace_settings(state, db_exec)
    trace_visible = bool(trace_settings.get("enabled"))
    trace_opacity = int(round(float(trace_settings.get("opacity") or 0.45) * 100))

    restore_body_script = _gleisplan_editor_restore_body_script()
    restore_js = restore_body_script.replace("<script>", "", 1).replace("</script>", "", 1)
    ui.add_body_html(restore_body_script)
    ui.timer(0.05, lambda js=restore_js: ui.run_javascript(js), once=True)
    _render_breadcrumb([("Konfiguration", go_home), ("Gleisplan", None)])
    with ui.row().classes("cfg-action-row"):
        ui.button(
            "Objekt hinzufügen",
            icon="add",
            on_click=lambda: _open_gleisplan_item_dialog(
                db_exec=db_exec,
                now_berlin=now_berlin,
                refresh=refresh,
            ),
        ).classes("cfg-btn-primary")
        ui.button(
            "Strasse zeichnen beenden" if draw_street else "Strasse einzeichnen",
            icon="gesture",
            on_click=lambda: (
                state.__setitem__("gleisplan_draw_street", not bool(state.get("gleisplan_draw_street"))),
                refresh(),
            ),
        ).classes("cfg-btn-primary" if draw_street else "cfg-btn-secondary")
        ui.button(
            "Speichern",
            icon="save",
        ).classes("cfg-btn-primary cfg-save-gleisplan-layout").on(
            "click",
            lambda event: _save_gleisplan_editor_changes_from_event(
                event,
                state=state,
                db_exec=db_exec,
                now_berlin=now_berlin,
                refresh=refresh,
            ),
            js_handler=_save_gleisplan_editor_changes_js_handler(),
        )
        ui.button(
            "Eberswalde Lageplan laden",
            icon="map",
            on_click=lambda: _open_reset_gleisplan_layout_dialog(
                db_exec=db_exec,
                now_berlin=now_berlin,
                refresh=refresh,
            ),
        ).classes("cfg-btn-secondary")
        ui.button(
            "Eberswalde-Geometrie aus PDF-Trace neu initialisieren",
            icon="route",
            on_click=lambda: _apply_eberswalde_pdf_geometry_action(
                db_exec=db_exec,
                now_berlin=now_berlin,
                refresh=refresh,
            ),
        ).classes("cfg-btn-secondary")
        ui.button(
            "PDF-Vorlage ausblenden" if trace_visible else "PDF-Vorlage anzeigen",
            icon="image",
            on_click=lambda: (
                _set_trace_setting(
                    state,
                    "enabled",
                    not bool(_normalize_trace_settings(state.get("gleisplan_pdf_trace_settings")).get("enabled")),
                    refresh=refresh,
                )
            ),
        ).classes("cfg-btn-primary" if trace_visible else "cfg-btn-secondary")
        ui.button(
            "PDF kalibrieren",
            icon="tune",
            on_click=lambda: (
                state.__setitem__(
                    "gleisplan_pdf_trace_settings",
                    {
                        **_normalize_trace_settings(state.get("gleisplan_pdf_trace_settings")),
                        "enabled": True,
                        "hide_grid": True,
                        "fade_foreground": True,
                    },
                ),
                refresh(),
            ),
        ).classes("cfg-btn-secondary")
        opacity_select = ui.select(
            {20: "20%", 30: "30%", 40: "40%", 45: "45%", 50: "50%", 60: "60%", 70: "70%", 80: "80%"},
            value=trace_opacity,
            label="PDF-Transparenz",
        ).props(_select_props()).classes("min-w-[150px]")
        opacity_select.on_value_change(
            lambda event: (
                _set_trace_setting(
                    state,
                    "opacity",
                    max(20, min(80, int(event.value or 45))) / 100,
                    refresh=refresh,
                )
            )
        )
        if connection_source:
            source_label = item_options.get(connection_source, connection_source)
            ui.button(
                f"Auswahl: {source_label}",
                icon="link",
                on_click=lambda: (
                    state.__setitem__("gleisplan_connection_source", ""),
                    refresh(),
                ),
            ).classes("cfg-btn-secondary")

    with ui.element("section").classes("cfg-trace-panel"):
        ui.label("PDF-Kalibrierung").classes("cfg-mini-label")
        with ui.row().classes("cfg-trace-row"):
            ui.button("Links", icon="keyboard_arrow_left", on_click=lambda: _adjust_trace_setting(state, "x", -0.5, refresh=refresh)).classes("cfg-btn-secondary")
            ui.button("Rechts", icon="keyboard_arrow_right", on_click=lambda: _adjust_trace_setting(state, "x", 0.5, refresh=refresh)).classes("cfg-btn-secondary")
            ui.button("Oben", icon="keyboard_arrow_up", on_click=lambda: _adjust_trace_setting(state, "y", -0.5, refresh=refresh)).classes("cfg-btn-secondary")
            ui.button("Unten", icon="keyboard_arrow_down", on_click=lambda: _adjust_trace_setting(state, "y", 0.5, refresh=refresh)).classes("cfg-btn-secondary")
            ui.button("Breiter", icon="open_in_full", on_click=lambda: _adjust_trace_setting(state, "scale_x", 0.005, refresh=refresh)).classes("cfg-btn-secondary")
            ui.button("Schmaler", icon="close_fullscreen", on_click=lambda: _adjust_trace_setting(state, "scale_x", -0.005, refresh=refresh)).classes("cfg-btn-secondary")
            ui.button("Hoeher", icon="unfold_more", on_click=lambda: _adjust_trace_setting(state, "scale_y", 0.005, refresh=refresh)).classes("cfg-btn-secondary")
            ui.button("Flacher", icon="unfold_less", on_click=lambda: _adjust_trace_setting(state, "scale_y", -0.005, refresh=refresh)).classes("cfg-btn-secondary")
        with ui.row().classes("cfg-trace-row"):
            x_input = ui.number("PDF X %", value=float(trace_settings.get("x") or 0.0)).props("outlined dense step=0.25").classes("cfg-trace-number")
            x_input.on_value_change(lambda event: _set_trace_setting(state, "x", event.value, refresh=refresh))
            y_input = ui.number("PDF Y %", value=float(trace_settings.get("y") or 0.0)).props("outlined dense step=0.25").classes("cfg-trace-number")
            y_input.on_value_change(lambda event: _set_trace_setting(state, "y", event.value, refresh=refresh))
            scale_x_input = ui.number("Scale X", value=float(trace_settings.get("scale_x") or 1.0)).props("outlined dense step=0.0025").classes("cfg-trace-number")
            scale_x_input.on_value_change(lambda event: _set_trace_setting(state, "scale_x", event.value, refresh=refresh))
            scale_y_input = ui.number("Scale Y", value=float(trace_settings.get("scale_y") or 1.0)).props("outlined dense step=0.0025").classes("cfg-trace-number")
            scale_y_input.on_value_change(lambda event: _set_trace_setting(state, "scale_y", event.value, refresh=refresh))
            rotation_input = ui.number("Rotation", value=float(trace_settings.get("rotation") or 0.0)).props("outlined dense step=0.05").classes("cfg-trace-number")
            rotation_input.on_value_change(lambda event: _set_trace_setting(state, "rotation", event.value, refresh=refresh))
        with ui.row().classes("cfg-trace-row"):
            hide_grid_input = ui.checkbox("Raster ausblenden", value=bool(trace_settings.get("hide_grid"))).props("dense").classes("cfg-trace-check")
            hide_grid_input.on_value_change(lambda event: _set_trace_setting(state, "hide_grid", bool(event.value), refresh=refresh))
            fade_input = ui.checkbox("Nicht ausgewaehlte Linien transparent", value=bool(trace_settings.get("fade_foreground"))).props("dense").classes("cfg-trace-check")
            fade_input.on_value_change(lambda event: _set_trace_setting(state, "fade_foreground", bool(event.value), refresh=refresh))
            hide_labels_input = ui.checkbox("Labels ausblenden", value=bool(trace_settings.get("hide_labels"))).props("dense").classes("cfg-trace-check")
            hide_labels_input.on_value_change(lambda event: _set_trace_setting(state, "hide_labels", bool(event.value), refresh=refresh))
            ui.button(
                "Kalibrierung speichern",
                icon="save",
                on_click=lambda: _save_gleisplan_pdf_trace_action(
                    state=state,
                    db_exec=db_exec,
                    now_berlin=now_berlin,
                ),
            ).classes("cfg-btn-primary")
            ui.button(
                "Kalibrierung zurücksetzen",
                icon="restart_alt",
                on_click=lambda: _reset_gleisplan_pdf_trace_action(
                    state=state,
                    db_exec=db_exec,
                    now_berlin=now_berlin,
                    refresh=refresh,
                ),
            ).classes("cfg-btn-secondary")

    with ui.row().classes("cfg-side-by-side"):
        with ui.element("section").classes("cfg-panel cfg-gleisplan-editor-panel"):
            ui.label("Plan-Editor").classes("cfg-section-title")
            ui.label("PDF als Vorlage einblenden, rote Verbindung anklicken und die Editor-Linie mit Stuetzpunkten auf das PDF-Gleis nachziehen. Gespeichert wird die rote Verbindung, nicht die Vorlage.").classes("cfg-subtle")
            ui.add_body_html(
                "<script>(()=>{const apply=()=>{const enabled=new URLSearchParams(window.location.search).get('debug_switch_ports')==='1';"
                "document.querySelectorAll('.gleisplan-editor-board').forEach(el=>el.classList.toggle('show-switch-anchors',enabled));};"
                "const enabled=new URLSearchParams(window.location.search).get('debug_switch_ports')==='1';"
                "apply();requestAnimationFrame(apply);"
                "if(enabled){const observer=new MutationObserver(apply);observer.observe(document.body,{childList:true,subtree:true});"
                "setTimeout(()=>{apply();observer.disconnect();},3000);}})();</script>"
            )
            board_classes = "gleisplan-editor-board draw-street-active" if draw_street else "gleisplan-editor-board"
            if trace_visible:
                board_classes += " show-pdf-trace"
            if bool(trace_settings.get("hide_grid")):
                board_classes += " hide-editor-grid"
            if bool(trace_settings.get("fade_foreground")):
                board_classes += " trace-fade-foreground"
            if bool(trace_settings.get("hide_labels")):
                board_classes += " hide-editor-labels"
            trace_style = (
                f"--pdf-trace-opacity:{float(trace_settings.get('opacity') or 0.45):.3f};"
                f"--pdf-trace-x:{float(trace_settings.get('x') or 0.0):.3f}%;"
                f"--pdf-trace-y:{float(trace_settings.get('y') or 0.0):.3f}%;"
                f"--pdf-trace-scale-x:{float(trace_settings.get('scale_x') or 1.0):.5f};"
                f"--pdf-trace-scale-y:{float(trace_settings.get('scale_y') or 1.0):.5f};"
                f"--pdf-trace-rotation:{float(trace_settings.get('rotation') or 0.0):.3f}deg;"
            )
            with ui.element("div").classes(board_classes).style(trace_style) as board_el:
                ui.element("div").classes("gleisplan-pdf-trace")
                if draw_street:
                    board_el.on(
                        "pointerdown",
                        lambda event: _create_drawn_gleisplan_street(
                            event,
                            db_exec=db_exec,
                            now_berlin=now_berlin,
                            refresh=refresh,
                        ),
                        js_handler=_draw_street_js_handler(),
                    )
                else:
                    board_el.on(
                        "pointerdown",
                        lambda event: _clear_gleisplan_config_selection(state=state, refresh=refresh),
                        js_handler=_clear_gleisplan_config_selection_js_handler(),
                    )
                for connection in connections:
                    _render_editor_connection(
                        connection,
                        db_exec=db_exec,
                        now_berlin=now_berlin,
                        item_options=item_options,
                        items_by_id=items_by_id,
                        selected_item=selected_item,
                        refresh=refresh,
                    )

                for item in layout_items:
                    item_id = str(item.get("item_id") or "").strip()
                    item_type = str(item.get("item_type") or "track").strip().lower()
                    if item_type == "track":
                        item_type = "anchor"
                    item_classes = f"gleisplan-editor-item item-{item_type}"
                    if item_id.upper() == selected_item:
                        item_classes += " is-selected"
                    if item_id.upper() == connection_source:
                        item_classes += " is-connection-source"
                    with ui.element("div").classes(item_classes).style(_layout_item_style(item)) as item_el:
                        item_el.props(
                            f'data-gleisplan-item-id="{item_id.upper()}" '
                            f'data-gleisplan-item-type="{item_type}" '
                            f'data-switch-port2-x="{float(item.get("switch_port2_x_ratio") or 0):.6f}" '
                            f'data-switch-port2-y="{float(item.get("switch_port2_y_ratio") or SWITCH_MAIN_RAIL_Y_RATIO):.6f}" '
                            f'data-switch-port3-x="{float(item.get("switch_port3_x_ratio") or SWITCH_BRANCH_PORT_X_RATIO):.6f}" '
                            f'data-switch-port3-y="{float(item.get("switch_port3_y_ratio") or SWITCH_BRANCH_PORT_Y_RATIO):.6f}"'
                        )
                        item_el.on(
                            "pointerdown",
                            lambda event, current_id=item_id: _handle_gleisplan_editor_item_event(
                                event,
                                state=state,
                                layout_items=layout_items,
                                db_exec=db_exec,
                                now_berlin=now_berlin,
                                refresh=refresh,
                                fallback_item_id=current_id,
                            ),
                            js_handler=_drag_item_js_handler(
                                item_id,
                                connections,
                                item_type=item_type,
                                connectable=item_type in CONNECTABLE_ITEM_TYPES,
                            ),
                        )
                        item_el.on(
                            "dblclick",
                            lambda event, row=dict(item): _open_gleisplan_item_dialog(
                                db_exec=db_exec,
                                now_berlin=now_berlin,
                                refresh=refresh,
                                edit_item=row,
                            ),
                            js_handler=_dblclick_editor_item_js_handler(),
                        )
                        if item_type == "anchor":
                            ui.label(str(item.get("label") or item_id)).classes("gleisplan-editor-anchor-label")
                        elif item_type == "switch":
                            _render_config_switch_symbol(
                                item=item,
                                db_exec=db_exec,
                                now_berlin=now_berlin,
                                refresh=refresh,
                            )
                        elif item_type == "buffer_stop":
                            _render_config_buffer_stop_symbol(str(item.get("label") or item_id))
                        elif item_type == "hall":
                            _render_config_hall_symbol(str(item.get("label") or item_id), hall_tracks)
                        elif item_type == "street":
                            pass
                        else:
                            ui.label(str(item.get("label") or item_id)).classes("gleisplan-editor-item-label")
                            ui.label(_item_type_label(item_type)).classes("gleisplan-editor-item-type")
                        if item_type == "street":
                            ui.element("div").classes("gleisplan-street-resize-handle").on(
                                "pointerdown",
                                lambda event, current_id=item_id: _update_gleisplan_item_geometry_from_event(
                                    event,
                                    db_exec=db_exec,
                                    now_berlin=now_berlin,
                                    refresh=refresh,
                                    fallback_item_id=current_id,
                                ),
                                js_handler=_resize_street_js_handler(item_id, float(item.get("rotation") or 0)),
                            )
                            ui.element("div").classes("gleisplan-street-width-handle").on(
                                "pointerdown",
                                lambda event, current_id=item_id: _update_gleisplan_item_geometry_from_event(
                                    event,
                                    db_exec=db_exec,
                                    now_berlin=now_berlin,
                                    refresh=refresh,
                                    fallback_item_id=current_id,
                                ),
                                js_handler=_resize_street_width_js_handler(
                                    item_id,
                                    float(item.get("rotation") or 0),
                                    float(item.get("h_pct") or 3),
                                ),
                            )
                            ui.element("div").classes("gleisplan-rotate-handle").on(
                                "pointerdown",
                                lambda event, current_id=item_id: _update_gleisplan_item_geometry_from_event(
                                    event,
                                    db_exec=db_exec,
                                    now_berlin=now_berlin,
                                    refresh=refresh,
                                    fallback_item_id=current_id,
                                ),
                                js_handler=_rotate_item_js_handler(
                                    item_id,
                                    float(item.get("rotation") or 0),
                                    connections,
                                    item_type=item_type,
                                ),
                            )
                            ui.element("div").classes("gleisplan-curve-handle").on(
                                "pointerdown",
                                lambda event, current_id=item_id: _update_gleisplan_item_geometry_from_event(
                                    event,
                                    db_exec=db_exec,
                                    now_berlin=now_berlin,
                                    refresh=refresh,
                                    fallback_item_id=current_id,
                                ),
                                js_handler=_curve_street_js_handler(item_id, float(item.get("curve_radius") or 0)),
                            )
                        elif item_type in {"switch", "buffer_stop"}:
                            ui.element("div").classes("gleisplan-rotate-handle").on(
                                "pointerdown",
                                lambda event, current_id=item_id: _update_gleisplan_item_geometry_from_event(
                                    event,
                                    db_exec=db_exec,
                                    now_berlin=now_berlin,
                                    refresh=refresh,
                                    fallback_item_id=current_id,
                                ),
                                js_handler=_rotate_item_js_handler(
                                    item_id,
                                    float(item.get("rotation") or 0),
                                    connections,
                                    item_type=item_type,
                                ),
                            )


def _is_track_or_switch(item: dict[str, Any] | None) -> bool:
    return str((item or {}).get("item_type") or "").strip().lower() in CONNECTABLE_ITEM_TYPES


def _can_auto_connect_gleisplan_items(first: dict[str, Any] | None, second: dict[str, Any] | None) -> bool:
    first_type = str((first or {}).get("item_type") or "").strip().lower()
    second_type = str((second or {}).get("item_type") or "").strip().lower()
    return first_type in CONNECTABLE_ITEM_TYPES and second_type in CONNECTABLE_ITEM_TYPES


def _render_selected_gleisplan_item_controls(
    *,
    item: dict[str, Any],
    db_exec: Callable[..., Any],
    now_berlin: Callable[[], datetime],
    hall_tracks: dict[str, dict[str, Any]] | None = None,
    refresh: Callable[[], None],
) -> None:
    item_id = str(item.get("item_id") or "").strip().upper()
    item_type = str(item.get("item_type") or "").strip().lower()
    if item_type == "track":
        item_type = "anchor"
    if item_type not in {"street", "switch", "buffer_stop", "hall"}:
        return

    with ui.element("section").classes("cfg-selected-editor"):
        ui.label(f"Auswahl: {item.get('label') or item_id}").classes("cfg-section-title")
        if item_type == "hall":
            ui.label("Gleishalle bearbeiten").classes("cfg-subtle")
            _render_hall_track_controls(
                db_exec=db_exec,
                now_berlin=now_berlin,
                hall_tracks=hall_tracks or {},
                refresh=refresh,
            )
            return
        if item_type == "street":
            ui.label("Strasse bearbeiten").classes("cfg-subtle")
            with ui.row().classes("w-full gap-2"):
                length_input = ui.number("Laenge %", value=float(item.get("w_pct") or 12)).props("outlined dense min=2 max=100 step=0.1").classes("grow")
                width_input = ui.number("Breite %", value=float(item.get("h_pct") or 3)).props("outlined dense min=1 max=100 step=0.1").classes("grow")
            with ui.row().classes("w-full gap-2"):
                rotation_input = ui.number("Ausrichtung", value=float(item.get("rotation") or 0)).props("outlined dense step=1").classes("grow")
                curve_input = ui.number("Kurvenradius", value=float(item.get("curve_radius") or 0)).props("outlined dense min=0 max=100 step=1").classes("grow")

            def save_street() -> None:
                ok, msg = update_gleisplan_layout_item_geometry(
                    db_exec,
                    item_id=item_id,
                    w_pct=float(length_input.value or 2),
                    h_pct=float(width_input.value or 1),
                    rotation=float(rotation_input.value or 0),
                    curve_radius=float(curve_input.value or 0),
                    updated_at=now_berlin().isoformat(timespec="seconds"),
                )
                ui.notify(msg, type="positive" if ok else "negative")
                if ok:
                    refresh()

            ui.button("Strasse speichern", icon="save", on_click=save_street).classes("cfg-btn-primary")
            return

        rotation_input = ui.number("Ausrichtung", value=float(item.get("rotation") or 0)).props("outlined dense step=1").classes("w-full")
        with ui.row().classes("w-full gap-2"):
            def rotate(delta: float) -> None:
                current = float(rotation_input.value or 0)
                rotation_input.value = current + delta

            ui.button("-15", on_click=lambda: rotate(-15)).classes("cfg-btn-secondary")
            ui.button("+15", on_click=lambda: rotate(15)).classes("cfg-btn-secondary")

        def save_symbol_rotation() -> None:
            ok, msg = update_gleisplan_layout_item_geometry(
                db_exec,
                item_id=item_id,
                rotation=float(rotation_input.value or 0),
                updated_at=now_berlin().isoformat(timespec="seconds"),
            )
            ui.notify(msg, type="positive" if ok else "negative")
            if ok:
                refresh()

        button_label = "Prellbock drehen" if item_type == "buffer_stop" else "Weiche drehen"
        ui.button(button_label, icon="rotate_right", on_click=save_symbol_rotation).classes("cfg-btn-primary")
        with ui.row().classes("w-full gap-2 mt-2"):
            width_input = ui.number("Breite %", value=float(item.get("w_pct") or 4)).props(
                "outlined dense min=2 max=30 step=0.1"
            ).classes("grow")
            height_input = ui.number("Hoehe %", value=float(item.get("h_pct") or 2)).props(
                "outlined dense min=2 max=30 step=0.1"
            ).classes("grow")

        def save_symbol_size() -> None:
            ok, msg = update_gleisplan_layout_item_geometry(
                db_exec,
                item_id=item_id,
                w_pct=float(width_input.value or 2),
                h_pct=float(height_input.value or 2),
                updated_at=now_berlin().isoformat(timespec="seconds"),
            )
            ui.notify(msg, type="positive" if ok else "negative")
            if ok:
                refresh()

        ui.button("Größe speichern", icon="straighten", on_click=save_symbol_size).classes("cfg-btn-secondary")


def _select_gleisplan_config_item(
    *,
    item_id: str,
    state: dict[str, Any],
    layout_items: list[dict[str, Any]],
    db_exec: Callable[..., Any],
    now_berlin: Callable[[], datetime],
    refresh: Callable[[], None],
) -> None:
    clean_id = str(item_id or "").strip().upper()
    items_by_id = {str(item.get("item_id") or "").strip().upper(): dict(item) for item in layout_items}
    item = items_by_id.get(clean_id)
    if not item:
        return

    previous_selected = str(state.get("gleisplan_selected_item") or "").strip().upper()
    previous_source = str(state.get("gleisplan_connection_source") or "").strip().upper()
    state["gleisplan_selected_item"] = clean_id
    source_id = previous_source
    if not _is_track_or_switch(item):
        state["gleisplan_connection_source"] = ""
        return

    if not source_id:
        state["gleisplan_connection_source"] = clean_id
        return
    if source_id == clean_id:
        return

    source_item = items_by_id.get(source_id)
    if not _can_auto_connect_gleisplan_items(source_item, item):
        state["gleisplan_connection_source"] = clean_id
        ui.notify("Bitte Gleis, Weiche oder Prellbock auswählen.", type="warning")
        return

    state["gleisplan_connection_source"] = ""
    _open_gleisplan_connection_name_dialog(
        db_exec=db_exec,
        now_berlin=now_berlin,
        refresh=refresh,
        source_item=source_item or {},
        target_item=item,
    )


def _render_hall_track_controls(
    *,
    db_exec: Callable[..., Any],
    now_berlin: Callable[[], datetime],
    hall_tracks: dict[str, dict[str, Any]],
    refresh: Callable[[], None],
) -> None:
    ui.label("Gleisnamen, Position in der Werkstatthalle und Synchronisierung").classes("cfg-subtle")
    with ui.column().classes("w-full gap-2"):
        for area_code in ordered_hall_track_codes(hall_tracks):
            config = hall_tracks.get(area_code) or {}
            with ui.element("div").classes("cfg-row-card"):
                with ui.row().classes("w-full items-center justify-between gap-2"):
                    with ui.row().classes("items-center gap-2 wrap"):
                        ui.label(area_code).classes("cfg-pill")
                    if area_code not in {"4B", "4A", "5A", "5B"}:
                        def delete_hall_track(_event=None, current_area=area_code) -> None:
                            ok, msg = delete_gleisplan_hall_track(db_exec, area_code=current_area)
                            ui.notify(msg, type="positive" if ok else "negative")
                            if ok:
                                refresh()

                        ui.button("Löschen", icon="delete", on_click=delete_hall_track).classes("cfg-btn-danger")
                with ui.row().classes("w-full gap-2 items-end wrap"):
                    label_input = ui.input(
                        "Gleisname",
                        value=str(config.get("track_label") or area_code),
                    ).props("outlined dense").classes("grow min-w-[170px]")
                    current_position = str(config.get("position_label") or HALL_TRACK_LABELS.get(area_code, "")).strip()
                    position_input = ui.select(
                        HALL_POSITION_OPTIONS,
                        value=current_position if current_position in HALL_POSITION_OPTIONS else None,
                        label="Position",
                    ).props(_select_props()).classes("grow min-w-[150px]")
                    workshop_input = ui.input(
                        "Werkstatthalle-Arbeitsplatz",
                        value=str(config.get("workshop_area") or area_code),
                    ).props("outlined dense").classes("grow min-w-[170px]")
                    sync_checkbox = ui.checkbox(
                        "Mit Werkstatthalle synchronisieren",
                        value=bool(config.get("sync_enabled", True)),
                    ).props("dense")

                    def save_hall_track(
                        _event=None,
                        current_area=area_code,
                        label_ctrl=label_input,
                        position_ctrl=position_input,
                        workshop_ctrl=workshop_input,
                        sync_ctrl=sync_checkbox,
                    ) -> None:
                        ok, msg = save_gleisplan_hall_track(
                            db_exec,
                            area_code=current_area,
                            track_label=str(label_ctrl.value or ""),
                            position_label=str(position_ctrl.value or ""),
                            workshop_area=str(workshop_ctrl.value or ""),
                            sync_enabled=bool(sync_ctrl.value),
                            updated_at=now_berlin().isoformat(timespec="seconds"),
                        )
                        ui.notify(msg, type="positive" if ok else "negative")
                        if ok:
                            refresh()

                    ui.button("Speichern", icon="save", on_click=save_hall_track).classes("cfg-btn-primary")

        with ui.element("div").classes("cfg-row-card"):
            ui.label("Hallengleis hinzufügen").classes("cfg-section-title")
            with ui.row().classes("w-full gap-2 items-end wrap"):
                new_code_input = ui.input("Code / Arbeitsplatz", value="").props("outlined dense").classes("grow min-w-[150px]")
                new_label_input = ui.input("Gleisname", value="").props("outlined dense").classes("grow min-w-[170px]")
                new_position_input = ui.select(
                    HALL_POSITION_OPTIONS,
                    value=None,
                    label="Position",
                ).props(_select_props()).classes("grow min-w-[150px]")
                new_sync_checkbox = ui.checkbox("Mit Werkstatthalle synchronisieren", value=True).props("dense")

                def add_hall_track() -> None:
                    code = str(new_code_input.value or "").strip()
                    label = str(new_label_input.value or "").strip() or code
                    ok, msg = save_gleisplan_hall_track(
                        db_exec,
                        area_code=code,
                        track_label=label,
                        position_label=str(new_position_input.value or ""),
                        workshop_area=code,
                        sync_enabled=bool(new_sync_checkbox.value),
                        updated_at=now_berlin().isoformat(timespec="seconds"),
                    )
                    ui.notify(msg, type="positive" if ok else "negative")
                    if ok:
                        refresh()

                ui.button("Hinzufuegen", icon="add", on_click=add_hall_track).classes("cfg-btn-primary")


def _handle_gleisplan_editor_item_event(
    event,
    *,
    state: dict[str, Any],
    layout_items: list[dict[str, Any]],
    db_exec: Callable[..., Any],
    now_berlin: Callable[[], datetime],
    refresh: Callable[[], None],
    fallback_item_id: str,
) -> None:
    args = event.args or {}
    item_id = str(args.get("item_id") if isinstance(args, dict) else fallback_item_id).strip()
    mode = str(args.get("mode") if isinstance(args, dict) else "").strip().lower()
    if mode == "edit":
        item = {str(row.get("item_id") or "").strip().upper(): dict(row) for row in layout_items}.get(item_id.upper())
        if item:
            _open_gleisplan_item_dialog(
                db_exec=db_exec,
                now_berlin=now_berlin,
                refresh=refresh,
                edit_item=item,
            )
        return
    if mode == "select":
        _select_gleisplan_config_item(
            item_id=item_id,
            state=state,
            layout_items=layout_items,
            db_exec=db_exec,
            now_berlin=now_berlin,
            refresh=refresh,
        )
        return
    if mode == "move":
        state["gleisplan_selected_item"] = item_id.upper()
        try:
            x_pct = float(args.get("x_pct"))
            y_pct = float(args.get("y_pct"))
        except Exception:
            return
        pending_positions = state.setdefault("gleisplan_pending_positions", {})
        if not isinstance(pending_positions, dict):
            pending_positions = {}
            state["gleisplan_pending_positions"] = pending_positions
        pending_positions[item_id.upper()] = {"x": x_pct, "y": y_pct}
        return

    try:
        x_pct = float(args.get("x"))
        y_pct = float(args.get("y"))
    except Exception:
        return
    state["gleisplan_selected_item"] = item_id.upper()
    ok, msg = update_gleisplan_layout_item_position(
        db_exec,
        item_id=item_id,
        x_pct=x_pct,
        y_pct=y_pct,
        updated_at=now_berlin().isoformat(timespec="seconds"),
    )
    if not ok:
        ui.notify(msg, type="warning")
        return
    item = {str(row.get("item_id") or "").strip().upper(): dict(row) for row in layout_items}.get(item_id.upper()) or {}
    if str(item.get("item_type") or "").strip().lower() == "street":
        refresh()


def _update_gleisplan_item_geometry_from_event(
    event,
    *,
    db_exec: Callable[..., Any],
    now_berlin: Callable[[], datetime],
    refresh: Callable[[], None],
    fallback_item_id: str,
) -> None:
    args = event.args or {}
    item_id = str(args.get("item_id") if isinstance(args, dict) else fallback_item_id).strip()
    try:
        w_pct = float(args["width"]) if "width" in args else None
        h_pct = float(args["h_pct"]) if "h_pct" in args else None
        rotation = float(args["rotation"]) if "rotation" in args else None
        curve_radius = float(args["curve_radius"]) if "curve_radius" in args else None
        switch_port2_x_ratio = float(args["switch_port2_x_ratio"]) if "switch_port2_x_ratio" in args else None
        switch_port2_y_ratio = float(args["switch_port2_y_ratio"]) if "switch_port2_y_ratio" in args else None
        switch_port3_x_ratio = float(args["switch_port3_x_ratio"]) if "switch_port3_x_ratio" in args else None
        switch_port3_y_ratio = float(args["switch_port3_y_ratio"]) if "switch_port3_y_ratio" in args else None
    except Exception:
        return
    ok, msg = update_gleisplan_layout_item_geometry(
        db_exec,
        item_id=item_id,
        w_pct=w_pct,
        h_pct=h_pct,
        rotation=rotation,
        curve_radius=curve_radius,
        switch_port2_x_ratio=switch_port2_x_ratio,
        switch_port2_y_ratio=switch_port2_y_ratio,
        switch_port3_x_ratio=switch_port3_x_ratio,
        switch_port3_y_ratio=switch_port3_y_ratio,
        updated_at=now_berlin().isoformat(timespec="seconds"),
    )
    if not ok:
        ui.notify(msg, type="warning")
        return
    refresh()


def _update_gleisplan_connection_curve_from_event(
    event,
    *,
    db_exec: Callable[..., Any],
    now_berlin: Callable[[], datetime],
    refresh: Callable[[], None],
) -> None:
    args = event.args or {}
    try:
        connection_id = int(args.get("connection_id") if isinstance(args, dict) else 0)
        curve_pct = float(args.get("curve_pct") if isinstance(args, dict) else 0)
    except Exception:
        return
    ok, msg = update_gleisplan_connection_curve(
        db_exec,
        connection_id=connection_id,
        curve_pct=curve_pct,
        updated_at=now_berlin().isoformat(timespec="seconds"),
    )
    if ok:
        refresh()
    else:
        ui.notify(msg, type="warning")


def _add_gleisplan_connection_path_point_from_event(
    event,
    *,
    db_exec: Callable[..., Any],
    now_berlin: Callable[[], datetime],
    refresh: Callable[[], None],
    item_options: dict[str, str] | None = None,
    items_by_id: dict[str, dict[str, Any]] | None = None,
    edit_connection: dict[str, Any] | None = None,
) -> None:
    args = event.args or {}
    if isinstance(args, dict) and str(args.get("mode") or "").strip().lower() == "edit":
        if item_options is not None and items_by_id is not None:
            _open_gleisplan_connection_dialog(
                db_exec=db_exec,
                now_berlin=now_berlin,
                item_options=item_options,
                items_by_id=items_by_id,
                refresh=refresh,
                edit_connection=dict(edit_connection or {}),
            )
        return
    try:
        connection_id = int(args.get("connection_id") if isinstance(args, dict) else 0)
        x_pct = float(args.get("x_pct") if isinstance(args, dict) else 0)
        y_pct = float(args.get("y_pct") if isinstance(args, dict) else 0)
        insert_index = int(args.get("insert_index")) if isinstance(args, dict) and args.get("insert_index") is not None else None
    except Exception:
        return
    if isinstance(args, dict) and str(args.get("mode") or "").strip().lower() == "update":
        try:
            point_index = int(args.get("point_index"))
        except Exception:
            return
        ok, msg = update_gleisplan_connection_path_point(
            db_exec,
            connection_id=connection_id,
            point_index=point_index,
            x_pct=x_pct,
            y_pct=y_pct,
            updated_at=now_berlin().isoformat(timespec="seconds"),
        )
        if not ok:
            ui.notify(msg, type="warning")
        return
    ok, msg = add_gleisplan_connection_path_point(
        db_exec,
        connection_id=connection_id,
        x_pct=x_pct,
        y_pct=y_pct,
        insert_index=insert_index,
        updated_at=now_berlin().isoformat(timespec="seconds"),
    )
    if not ok:
        ui.notify(msg, type="warning")


def _update_gleisplan_connection_path_point_from_event(
    event,
    *,
    db_exec: Callable[..., Any],
    now_berlin: Callable[[], datetime],
    refresh: Callable[[], None],
) -> None:
    args = event.args or {}
    try:
        connection_id = int(args.get("connection_id") if isinstance(args, dict) else 0)
        point_index = int(args.get("point_index") if isinstance(args, dict) else -1)
        x_pct = float(args.get("x_pct") if isinstance(args, dict) else 0)
        y_pct = float(args.get("y_pct") if isinstance(args, dict) else 0)
    except Exception:
        return
    ok, msg = update_gleisplan_connection_path_point(
        db_exec,
        connection_id=connection_id,
        point_index=point_index,
        x_pct=x_pct,
        y_pct=y_pct,
        updated_at=now_berlin().isoformat(timespec="seconds"),
    )
    if ok:
        refresh()
    else:
        ui.notify(msg, type="warning")


def _delete_gleisplan_connection_path_point_from_event(
    event,
    *,
    db_exec: Callable[..., Any],
    now_berlin: Callable[[], datetime],
    refresh: Callable[[], None],
) -> None:
    args = event.args or {}
    try:
        connection_id = int(args.get("connection_id") if isinstance(args, dict) else 0)
        point_index = int(args.get("point_index") if isinstance(args, dict) else -1)
    except Exception:
        return
    ok, msg = delete_gleisplan_connection_path_point(
        db_exec,
        connection_id=connection_id,
        point_index=point_index,
        updated_at=now_berlin().isoformat(timespec="seconds"),
    )
    ui.notify(msg, type="positive" if ok else "warning")
    if ok:
        refresh()


def _render_config_switch_symbol(
    *,
    item: dict[str, Any],
    db_exec: Callable[..., Any],
    now_berlin: Callable[[], datetime],
    refresh: Callable[[], None],
) -> None:
    item_id = str(item.get("item_id") or "").strip().upper()
    label = str(item.get("label") or item_id)
    with ui.element("div").classes("gleisplan-switch-symbol gleisplan-switch-symbol-editor"):
        ui.html(_switch_svg_markup(item), sanitize=False)
        ui.element("div").classes("gleisplan-switch-hatch")
        ui.element("div").classes("gleisplan-switch-heel")
        for anchor_name in ("stem", "straight", "branch"):
            ui.element("div").classes(
                f"gleisplan-switch-anchor-debug anchor-{anchor_name}"
            ).style(_switch_anchor_debug_style(item, anchor_name)).props(f'data-anchor="{anchor_name}"')
        ui.label("1").classes("gleisplan-switch-port-label port-1").style(_switch_port_label_style(item, "1"))
        port2_label = ui.label("2").classes("gleisplan-switch-port-label port-2 gleisplan-switch-angle-handle").style(
            _switch_port_label_style(item, "2")
        )
        port3_label = ui.label("3").classes("gleisplan-switch-port-label port-3 gleisplan-switch-angle-handle").style(
            _switch_port_label_style(item, "3")
        )
        for port, handle in (("2", port2_label), ("3", port3_label)):
            handle.on(
                "pointerdown",
                lambda event, current_id=item_id: _update_gleisplan_item_geometry_from_event(
                    event,
                    db_exec=db_exec,
                    now_berlin=now_berlin,
                    refresh=refresh,
                    fallback_item_id=current_id,
                ),
                js_handler=_switch_port_handle_js_handler(item_id, port),
            )
        ui.label(label).classes("gleisplan-switch-node-label")


def _render_config_buffer_stop_symbol(label: str) -> None:
    with ui.element("div").classes("gleisplan-buffer-stop-symbol gleisplan-buffer-stop-symbol-editor"):
        ui.element("div").classes("gleisplan-buffer-stop-rail")
        ui.element("div").classes("gleisplan-buffer-stop-beam")
        ui.element("div").classes("gleisplan-buffer-stop-post")
        ui.label(label).classes("gleisplan-buffer-stop-label")


def _render_config_hall_symbol(label: str, hall_tracks: dict[str, dict[str, Any]]) -> None:
    ui.label(label).classes("gleisplan-editor-hall-title")
    with ui.element("div").classes("gleisplan-editor-hall-grid"):
        for row in build_hall_track_grid(hall_tracks):
            for area_code in row:
                config = hall_tracks.get(area_code) or {}
                position_label = str(
                    config.get("position_label") or HALL_TRACK_LABELS.get(str(area_code), "")
                )
                with ui.element("div").classes("gleisplan-editor-hall-cell").props(
                    f'data-hall-track-code="{str(area_code).strip().upper()}"'
                ):
                    ui.label(str(area_code)).classes("gleisplan-editor-hall-track")
                    ui.label(position_label).classes("gleisplan-editor-hall-position")


def _create_drawn_gleisplan_street(
    event,
    *,
    db_exec: Callable[..., Any],
    now_berlin: Callable[[], datetime],
    refresh: Callable[[], None],
) -> None:
    args = event.args or {}
    if not isinstance(args, dict):
        return
    try:
        x_pct = float(args.get("x"))
        y_pct = float(args.get("y"))
        length_pct = float(args.get("length"))
        rotation = float(args.get("rotation"))
    except Exception:
        return
    if length_pct < 2:
        return
    item_id = make_gleisplan_item_id_for_type_label(db_exec, item_type="street", label="Strasse")
    ok, msg = save_gleisplan_layout_item(
        db_exec,
        item_id=item_id,
        item_type="street",
        label="Strasse",
        title="",
        x_pct=max(0.0, min(100.0, x_pct)),
        y_pct=max(0.0, min(97.0, y_pct)),
        w_pct=max(2.0, min(100.0, length_pct)),
        h_pct=3.0,
        rotation=rotation,
        color="#d1d5db",
        sort_order=900,
        updated_at=now_berlin().isoformat(timespec="seconds"),
    )
    ui.notify(msg, type="positive" if ok else "negative")
    if ok:
        refresh()


def _save_dragged_gleisplan_item(
    event,
    *,
    db_exec: Callable[..., Any],
    now_berlin: Callable[[], datetime],
    refresh: Callable[[], None],
    fallback_item_id: str,
) -> None:
    args = event.args or {}
    item_id = str(args.get("item_id") if isinstance(args, dict) else fallback_item_id).strip()
    try:
        x_pct = float(args.get("x"))
        y_pct = float(args.get("y"))
    except Exception:
        return
    ok, msg = update_gleisplan_layout_item_position(
        db_exec,
        item_id=item_id,
        x_pct=x_pct,
        y_pct=y_pct,
        updated_at=now_berlin().isoformat(timespec="seconds"),
    )
    if ok:
        refresh()
    else:
        ui.notify(msg, type="warning")


def _open_gleisplan_connection_name_dialog(
    *,
    db_exec: Callable[..., Any],
    now_berlin: Callable[[], datetime],
    refresh: Callable[[], None],
    source_item: dict[str, Any],
    target_item: dict[str, Any],
) -> None:
    source_id = str(source_item.get("item_id") or "").strip().upper()
    target_id = str(target_item.get("item_id") or "").strip().upper()
    source_label = str(source_item.get("label") or source_id).strip()
    target_label = str(target_item.get("label") or target_id).strip()
    hall_tracks = load_gleisplan_hall_tracks(db_exec)
    source_is_hall = str(source_item.get("item_type") or "").strip().lower() == "hall"
    target_is_hall = str(target_item.get("item_type") or "").strip().lower() == "hall"
    with ui.dialog() as dialog, ui.card().classes("cfg-dialog-card"):
        ui.label("Gleisname für Verbindung").classes("dialog-title")
        ui.label(f"{source_label} -> {target_label}").classes("cfg-subtle")
        label_input = ui.input("Gleisname").props("outlined dense autofocus").classes("w-full")
        source_port_select = None
        target_port_select = None
        source_port_options = connection_port_options_for_item(source_item, hall_tracks=hall_tracks)
        target_port_options = connection_port_options_for_item(target_item, hall_tracks=hall_tracks)
        if source_is_hall or len(source_port_options) > 1:
            source_port_select = ui.select(
                source_port_options,
                value=None if source_is_hall else "",
                label=f"Linie / Hallengleis an {source_label}",
            ).props(_select_props()).classes("w-full")
        if target_is_hall or len(target_port_options) > 1:
            target_port_select = ui.select(
                target_port_options,
                value=None if target_is_hall else "",
                label=f"Linie / Hallengleis an {target_label}",
            ).props(_select_props()).classes("w-full")
        with ui.row().classes("w-full justify-end gap-2 mt-3"):
            ui.button("Abbrechen", on_click=lambda: (dialog.close(), refresh())).classes("cfg-btn-secondary")

            def save() -> None:
                gleis_name = str(label_input.value or "").strip()
                if not gleis_name:
                    ui.notify("Bitte den Gleisnamen eintragen.", type="warning")
                    return
                if source_is_hall and (not source_port_select or not str(source_port_select.value or "").strip()):
                    ui.notify(f"Bitte Hallengleis an {source_label} auswählen.", type="warning")
                    return
                if target_is_hall and (not target_port_select or not str(target_port_select.value or "").strip()):
                    ui.notify(f"Bitte Hallengleis an {target_label} auswählen.", type="warning")
                    return
                ok, msg = save_gleisplan_connection(
                    db_exec,
                    source_item_id=source_id,
                    target_item_id=target_id,
                    source_port=str(source_port_select.value or "") if source_port_select else "",
                    target_port=str(target_port_select.value or "") if target_port_select else "",
                    label=gleis_name,
                    connection_type="track",
                    updated_at=now_berlin().isoformat(timespec="seconds"),
                )
                ui.notify(msg, type="positive" if ok else "negative")
                if ok:
                    dialog.close()
                    refresh()

            ui.button("Verbindung speichern", icon="add_link", on_click=save).classes("cfg-btn-primary")
    dialog.open()


def _open_gleisplan_item_dialog(
    *,
    db_exec: Callable[..., Any],
    now_berlin: Callable[[], datetime],
    refresh: Callable[[], None],
    edit_item: dict[str, Any] | None = None,
) -> None:
    edit = dict(edit_item or {})
    edit_type = str(edit.get("item_type") or "switch").strip().lower()
    if edit_type == "track":
        edit_type = "anchor"
    type_options = {
        "switch": "Weiche",
        "hall": "Halle",
        "buffer_stop": "Prellbock",
        "anchor": "Verbindungspunkt",
        "building": "Gebaeude",
        "street": "Strasse / Flaeche",
    }
    with ui.dialog() as dialog, ui.card().classes("cfg-dialog-card"):
        ui.label("Gleisplan-Objekt bearbeiten" if edit else "Gleisplan-Objekt erstellen").classes("dialog-title")
        with ui.row().classes("w-full gap-2 items-end wrap"):
            if edit:
                ui.input("ID", value=str(edit.get("item_id") or "")).props("outlined dense readonly").classes("grow min-w-[180px]")
            type_select = ui.select(
                type_options,
                value=edit_type if edit_type in type_options else "switch",
                label="Typ",
            ).props(_select_props()).classes("grow min-w-[160px]")
            label_input = ui.input("Bezeichnung", value=str(edit.get("label") or "")).props("outlined dense").classes("grow min-w-[220px]")
        with ui.row().classes("w-full gap-2 items-end wrap"):
            x_input = ui.number("X %", value=float(edit.get("x_pct") or 10)).props("outlined dense min=0 max=100 step=0.1").classes("grow min-w-[105px]")
            y_input = ui.number("Y %", value=float(edit.get("y_pct") or 10)).props("outlined dense min=0 max=100 step=0.1").classes("grow min-w-[105px]")
            w_input = ui.number("Breite %", value=float(edit.get("w_pct") or 12)).props("outlined dense min=2 max=100 step=0.1").classes("grow min-w-[120px]")
            h_input = ui.number("Hoehe %", value=float(edit.get("h_pct") or 8)).props("outlined dense min=1 max=100 step=0.1").classes("grow min-w-[120px]")
        with ui.row().classes("w-full gap-2 items-end wrap"):
            rot_input = ui.number("Drehung", value=float(edit.get("rotation") or 0)).props("outlined dense step=1").classes("grow min-w-[130px]")
            color_input = ui.input("Farbe", value=str(edit.get("color") or "")).props("outlined dense").classes("grow min-w-[150px]")
            curve_input = ui.number("Kurvenradius", value=float(edit.get("curve_radius") or 0)).props("outlined dense min=0 max=100 step=1").classes("grow min-w-[150px]")
        if edit and edit_type == "hall":
            ui.separator().classes("w-full opacity-30")
            ui.label("Hallengleise").classes("cfg-section-title")
            _render_hall_track_controls(
                db_exec=db_exec,
                now_berlin=now_berlin,
                hall_tracks=load_gleisplan_hall_tracks(db_exec),
                refresh=refresh,
            )
        with ui.row().classes("w-full justify-end gap-2 mt-3"):
            if edit:
                def delete_item() -> None:
                    ok, msg = delete_gleisplan_layout_item(db_exec, item_id=str(edit.get("item_id") or ""))
                    ui.notify(msg, type="positive" if ok else "negative")
                    if ok:
                        dialog.close()
                        refresh()

                ui.button("Löschen", icon="delete", on_click=delete_item).classes("cfg-btn-danger")
            ui.button("Abbrechen", on_click=dialog.close).classes("cfg-btn-secondary")

            def save() -> None:
                selected_type = str(type_select.value or "switch")
                label_value = str(label_input.value or "").strip()
                if not label_value:
                    ui.notify("Bitte eine Bezeichnung eintragen.", type="warning")
                    return
                item_id_value = str(edit.get("item_id") or "").strip()
                if not edit:
                    item_id_value = make_gleisplan_item_id_for_type_label(
                        db_exec,
                        item_type=selected_type,
                        label=label_value,
                    )
                w_value = float(w_input.value or 12)
                h_value = float(h_input.value or 8)
                if not edit and selected_type == "switch" and abs(w_value - 12) < 0.001 and abs(h_value - 8) < 0.001:
                    w_value = 4.2
                    h_value = 2.0
                if not edit and selected_type == "buffer_stop" and abs(w_value - 12) < 0.001 and abs(h_value - 8) < 0.001:
                    w_value = 2.6
                    h_value = 7.0
                if not edit and selected_type == "anchor" and abs(w_value - 12) < 0.001 and abs(h_value - 8) < 0.001:
                    w_value = 1.4
                    h_value = 1.4
                dialog.close()
                ok, msg = save_gleisplan_layout_item(
                    db_exec,
                    item_id=item_id_value,
                    item_type=selected_type,
                    label=label_value,
                    title="",
                    x_pct=float(x_input.value or 0),
                    y_pct=float(y_input.value or 0),
                    w_pct=w_value,
                    h_pct=h_value,
                    rotation=float(rot_input.value or 0),
                    color=str(color_input.value or ""),
                    curve_radius=float(curve_input.value or 0),
                    switch_port2_x_ratio=float(edit.get("switch_port2_x_ratio", 0.0) or 0.0),
                    switch_port2_y_ratio=float(edit.get("switch_port2_y_ratio", SWITCH_MAIN_RAIL_Y_RATIO) or SWITCH_MAIN_RAIL_Y_RATIO),
                    switch_port3_x_ratio=float(edit.get("switch_port3_x_ratio", SWITCH_BRANCH_PORT_X_RATIO) or SWITCH_BRANCH_PORT_X_RATIO),
                    switch_port3_y_ratio=float(edit.get("switch_port3_y_ratio", SWITCH_BRANCH_PORT_Y_RATIO) or SWITCH_BRANCH_PORT_Y_RATIO),
                    sort_order=int(edit.get("sort_order") or 1000),
                    updated_at=now_berlin().isoformat(timespec="seconds"),
                    allow_update=bool(edit),
                )
                ui.notify(msg, type="positive" if ok else "negative")
                if ok:
                    refresh()

            ui.button("Speichern", on_click=save).classes("cfg-btn-primary")
    dialog.open()


def _open_gleisplan_connection_dialog(
    *,
    db_exec: Callable[..., Any],
    now_berlin: Callable[[], datetime],
    item_options: dict[str, str],
    items_by_id: dict[str, dict[str, Any]],
    refresh: Callable[[], None],
    edit_connection: dict[str, Any] | None = None,
) -> None:
    edit = dict(edit_connection or {})
    hall_tracks = load_gleisplan_hall_tracks(db_exec)
    source_item = items_by_id.get(str(edit.get("source_item_id") or "").strip().upper()) or {}
    target_item = items_by_id.get(str(edit.get("target_item_id") or "").strip().upper()) or {}
    with ui.dialog() as dialog, ui.card().classes("cfg-dialog-card"):
        ui.label("Gleisplan-Verbindung bearbeiten" if edit else "Gleisplan-Verbindung erstellen").classes("dialog-title")
        with ui.row().classes("w-full gap-2 items-end wrap"):
            source_select = ui.select(
                item_options,
                value=str(edit.get("source_item_id") or "") or None,
                label="Von Objekt",
            ).props(_select_props()).classes("grow min-w-[240px]")
            target_select = ui.select(
                item_options,
                value=str(edit.get("target_item_id") or "") or None,
                label="Zu Objekt",
            ).props(_select_props()).classes("grow min-w-[240px]")
        with ui.row().classes("w-full gap-2 items-end wrap"):
            source_options_initial = (
                connection_port_options_for_item(source_item, hall_tracks=hall_tracks)
                if source_item
                else {"": "Automatisch", "1": "Linie 1", "2": "Linie 2", "3": "Linie 3"}
            )
            target_options_initial = (
                connection_port_options_for_item(target_item, hall_tracks=hall_tracks)
                if target_item
                else {"": "Automatisch", "1": "Linie 1", "2": "Linie 2", "3": "Linie 3"}
            )
            source_port_value = str(edit.get("source_port") or "")
            target_port_value = str(edit.get("target_port") or "")
            source_port_select = ui.select(
                source_options_initial,
                value=source_port_value if source_port_value in source_options_initial else None,
                label="Linie / Hallengleis am Von-Objekt",
            ).props(_select_props()).classes("grow min-w-[240px]")
            target_port_select = ui.select(
                target_options_initial,
                value=target_port_value if target_port_value in target_options_initial else None,
                label="Linie / Hallengleis am Zu-Objekt",
            ).props(_select_props()).classes("grow min-w-[240px]")
        with ui.row().classes("w-full gap-2 items-end wrap"):
            type_select = ui.select(
                {"track": "Gleis"},
                value="track",
                label="Verbindungstyp",
            ).props(_select_props()).classes("grow min-w-[120px]")
            label_input = ui.input("Gleisname / Bezeichnung", value=str(edit.get("label") or "")).props("outlined dense").classes("grow min-w-[240px]")
            curve_input = ui.number("Kurve", value=float(edit.get("curve_pct") or 0)).props("outlined dense min=-100 max=100 step=1").classes("grow min-w-[120px]")

        def update_manual_port_options() -> None:
            source_item_current = items_by_id.get(str(source_select.value or "").strip().upper()) or {}
            target_item_current = items_by_id.get(str(target_select.value or "").strip().upper()) or {}
            source_options = connection_port_options_for_item(source_item_current, hall_tracks=hall_tracks)
            target_options = connection_port_options_for_item(target_item_current, hall_tracks=hall_tracks)
            source_port_select.options = source_options
            target_port_select.options = target_options
            if str(source_port_select.value or "") not in source_options:
                source_port_select.value = "" if "" in source_options else None
            if str(target_port_select.value or "") not in target_options:
                target_port_select.value = "" if "" in target_options else None
            source_port_select.update()
            target_port_select.update()

        source_select.on_value_change(lambda _event: update_manual_port_options())
        target_select.on_value_change(lambda _event: update_manual_port_options())

        with ui.row().classes("w-full justify-end gap-2 mt-3"):
            if edit:
                def delete_connection() -> None:
                    ok, msg = delete_gleisplan_connection(db_exec, connection_id=int(edit.get("id") or 0))
                    ui.notify(msg, type="positive" if ok else "negative")
                    if ok:
                        dialog.close()
                        refresh()

                ui.button("Löschen", icon="delete", on_click=delete_connection).classes("cfg-btn-danger")
                ui.button(
                    "Verbindung glätten",
                    icon="timeline",
                    on_click=lambda: _smooth_gleisplan_connection_action(
                        db_exec=db_exec,
                        now_berlin=now_berlin,
                        connection_id=int(edit.get("id") or 0),
                        refresh=refresh,
                    ),
                ).classes("cfg-btn-secondary")
                ui.button(
                    "Verbindung zurücksetzen",
                    icon="restart_alt",
                    on_click=lambda: _reset_gleisplan_connection_shape_action(
                        db_exec=db_exec,
                        now_berlin=now_berlin,
                        connection_id=int(edit.get("id") or 0),
                        refresh=refresh,
                    ),
                ).classes("cfg-btn-secondary")
            ui.button("Abbrechen", on_click=dialog.close).classes("cfg-btn-secondary")

            def save() -> None:
                current_source_item = items_by_id.get(str(source_select.value or "").strip().upper()) or {}
                current_target_item = items_by_id.get(str(target_select.value or "").strip().upper()) or {}
                if str(current_source_item.get("item_type") or "").strip().lower() == "hall" and not str(source_port_select.value or "").strip():
                    ui.notify("Bitte Hallengleis am Von-Objekt auswählen.", type="warning")
                    return
                if str(current_target_item.get("item_type") or "").strip().lower() == "hall" and not str(target_port_select.value or "").strip():
                    ui.notify("Bitte Hallengleis am Zu-Objekt auswählen.", type="warning")
                    return
                ok, msg = save_gleisplan_connection(
                    db_exec,
                    source_item_id=str(source_select.value or ""),
                    target_item_id=str(target_select.value or ""),
                    source_port=str(source_port_select.value or ""),
                    target_port=str(target_port_select.value or ""),
                    label=str(label_input.value or ""),
                    connection_type="track",
                    curve_pct=float(curve_input.value or 0),
                    updated_at=now_berlin().isoformat(timespec="seconds"),
                    connection_id=int(edit.get("id") or 0) or None,
                )
                ui.notify(msg, type="positive" if ok else "negative")
                if ok:
                    dialog.close()
                    refresh()

            ui.button("Speichern", on_click=save).classes("cfg-btn-primary")
    dialog.open()


def _open_delete_gleisplan_item_dialog(
    *,
    db_exec: Callable[..., Any],
    item: dict[str, Any],
    refresh: Callable[[], None],
) -> None:
    with ui.dialog() as dialog, ui.card().classes("cfg-dialog-card"):
        ui.label("Gleisplan-Objekt löschen").classes("dialog-title")
        ui.label(f"Soll {item.get('label') or item.get('item_id')} wirklich gelöscht werden?").classes("cfg-subtle")
        with ui.row().classes("w-full justify-end gap-2 mt-3"):
            ui.button("Abbrechen", on_click=dialog.close).classes("cfg-btn-secondary")

            def confirm() -> None:
                ok, msg = delete_gleisplan_layout_item(db_exec, item_id=str(item.get("item_id") or ""))
                ui.notify(msg, type="positive" if ok else "negative")
                if ok:
                    dialog.close()
                    refresh()

            ui.button("Löschen", on_click=confirm).classes("cfg-btn-danger")
    dialog.open()


def _delete_gleisplan_connection_action(
    *,
    db_exec: Callable[..., Any],
    connection_id: int,
    refresh: Callable[[], None],
) -> None:
    ok, msg = delete_gleisplan_connection(db_exec, connection_id=connection_id)
    ui.notify(msg, type="positive" if ok else "negative")
    if ok:
        refresh()


def _add_gleisplan_connection_path_point_action(
    *,
    db_exec: Callable[..., Any],
    now_berlin: Callable[[], datetime],
    connection_id: int,
    refresh: Callable[[], None],
) -> None:
    ok, msg = add_gleisplan_connection_path_point(
        db_exec,
        connection_id=connection_id,
        updated_at=now_berlin().isoformat(timespec="seconds"),
    )
    ui.notify(msg, type="positive" if ok else "negative")
    if ok:
        refresh()


def _delete_gleisplan_connection_path_points_action(
    *,
    db_exec: Callable[..., Any],
    now_berlin: Callable[[], datetime],
    connection_id: int,
    refresh: Callable[[], None],
) -> None:
    ok, msg = delete_gleisplan_connection_path_point(
        db_exec,
        connection_id=connection_id,
        point_index=None,
        updated_at=now_berlin().isoformat(timespec="seconds"),
    )
    ui.notify(msg, type="positive" if ok else "negative")
    if ok:
        refresh()


def _smooth_gleisplan_connection_action(
    *,
    db_exec: Callable[..., Any],
    now_berlin: Callable[[], datetime],
    connection_id: int,
    refresh: Callable[[], None],
) -> None:
    ok, msg = smooth_gleisplan_connection_route(
        db_exec,
        connection_id=connection_id,
        updated_at=now_berlin().isoformat(timespec="seconds"),
    )
    ui.notify(msg, type="positive" if ok else "warning")
    if ok:
        refresh()


def _reset_gleisplan_connection_shape_action(
    *,
    db_exec: Callable[..., Any],
    now_berlin: Callable[[], datetime],
    connection_id: int,
    refresh: Callable[[], None],
) -> None:
    ok, msg = reset_gleisplan_connection_route_shape(
        db_exec,
        connection_id=connection_id,
        updated_at=now_berlin().isoformat(timespec="seconds"),
    )
    ui.notify(msg, type="positive" if ok else "warning")
    if ok:
        refresh()


def _open_reset_gleisplan_layout_dialog(
    *,
    db_exec: Callable[..., Any],
    now_berlin: Callable[[], datetime],
    refresh: Callable[[], None],
) -> None:
    with ui.dialog() as dialog, ui.card().classes("cfg-dialog-card"):
        ui.label("Eberswalde Lageplan laden").classes("dialog-title")
        ui.label("Dabei werden Layout-Objekte und Verbindungen gelöscht und aus der Vorlage neu erstellt.").classes("cfg-subtle")
        with ui.row().classes("w-full justify-end gap-2 mt-3"):
            ui.button("Abbrechen", on_click=dialog.close).classes("cfg-btn-secondary")

            def confirm() -> None:
                ok, msg = reset_gleisplan_layout_to_default(
                    db_exec,
                    updated_at=now_berlin().isoformat(timespec="seconds"),
                )
                ui.notify(msg, type="positive" if ok else "negative")
                if ok:
                    dialog.close()
                    refresh()

            ui.button("Vorlage laden", on_click=confirm).classes("cfg-btn-danger")
    dialog.open()


def _render_series_overview(
    *,
    list_series: Callable[[], list[str]],
    add_series: Callable[[str], str],
    open_series: Callable[[str], None],
    go_home: Callable[[], None],
    refresh: Callable[[], None],
) -> None:
    series_names = list_series()
    _render_breadcrumb([("Konfiguration", go_home), ("Baureihen", None)])
    with ui.row().classes("cfg-action-row"):
        ui.button(
            "Baureihe hinzufügen",
            on_click=lambda: _open_series_dialog(add_series=add_series, refresh=refresh),
        ).classes("cfg-btn-primary")

    if not series_names:
        ui.label("Noch keine Baureihen vorhanden.").classes("cfg-empty")
        return

    with ui.element("div").classes("cfg-grid"):
        for series in series_names:
            ui.button(series, on_click=lambda s=series: open_series(s)).classes("cfg-btn-open cfg-entry-button w-full")


def _render_series_detail(
    *,
    state: dict[str, Any],
    series: str,
    list_frist_levels: Callable[[str], list[str]],
    list_frist_level_configs: Callable[[str], list[dict[str, Any]]],
    add_frist_level: Callable[..., str],
    update_frist_level_trigger_type: Callable[[str, str, str], bool],
    update_frist_level_active: Callable[[str, str, bool], bool],
    set_all_frist_levels_active: Callable[[str, bool], int],
    update_frist_level_config: Callable[[str, str, str, str], str],
    frist_trigger_options: Callable[[], dict[str, str]],
    delete_frist_level: Callable[[str, str], bool],
    move_frist_level: Callable[[str, str, int], bool],
    list_work_packages: Callable[..., list[dict[str, Any]]],
    save_work_package: Callable[..., int],
    delete_work_package: Callable[[int], bool],
    move_work_package: Callable[[str, str, int, int], bool],
    list_vehicle_series_mappings: Callable[..., list[dict[str, Any]]],
    save_vehicle_series_mapping: Callable[[str, str], None],
    delete_vehicle_series_mapping: Callable[[str], bool],
    go_home: Callable[[], None],
    go_series_overview: Callable[[], None],
    refresh: Callable[[], None],
) -> None:
    if not series:
        ui.label("Keine Baureihe ausgewählt.").classes("cfg-empty")
        ui.button("Zurück zur Baureihenübersicht", on_click=go_series_overview).classes("cfg-btn-secondary")
        return

    is_general = _is_general_series(series)
    level_configs = list_frist_level_configs(series)
    levels = [str(item.get("friststufe") or "").strip() for item in level_configs if str(item.get("friststufe") or "").strip()]
    level_config_by_name = {str(item.get("friststufe") or "").strip(): dict(item) for item in level_configs}
    state["_frist_level_config_by_name"] = level_config_by_name
    trigger_options = frist_trigger_options()
    selected_frists = _selected_frist_levels(state, levels)
    active_trigger_types = {
        str(config.get("trigger_type") or "time")
        for config in level_config_by_name.values()
        if bool(config.get("active", True))
    }
    single_trigger_select_mode = len(active_trigger_types) <= 1
    state["_frist_single_select_mode"] = single_trigger_select_mode
    seen_triggers: set[str] = set()
    valid_selected_frists: list[str] = []
    if single_trigger_select_mode and len(selected_frists) > 1:
        valid_selected_frists = selected_frists[:1]
    else:
        for selected_level in selected_frists:
            trigger_type = str(level_config_by_name.get(selected_level, {}).get("trigger_type") or "time")
            if trigger_type in seen_triggers:
                continue
            seen_triggers.add(trigger_type)
            valid_selected_frists.append(selected_level)
    if valid_selected_frists != selected_frists:
        selected_frists = valid_selected_frists
        state["frist_filters"] = selected_frists
        state["frist_filter"] = selected_frists[0] if len(selected_frists) == 1 else ALL_FRISTS
    all_series_packages = list_work_packages(series, None)
    available_package_titles = sorted(
        {str(row.get("title") or "").strip() for row in all_series_packages if str(row.get("title") or "").strip()},
        key=str.casefold,
    )
    selected_package = _selected_package_title(state, available_package_titles)

    packages = [dict(package) for package in all_series_packages]
    if selected_frists:
        packages = [package for package in packages if str(package.get("friststufe") or "").strip() in selected_frists]
    if selected_package != ALL_WORK_PACKAGES:
        packages = [package for package in packages if _case_key(package.get("title")) == _case_key(selected_package)]
        level_order = {level: index for index, level in enumerate(levels)}
        packages.sort(
            key=lambda package: (
                level_order.get(str(package.get("friststufe") or "").strip(), len(level_order) + 1),
                int(package.get("sort_order") or 0),
                int(package.get("id") or 0),
            )
        )
    packages = _aggregate_packages_for_selected_frists(packages, selected_frists)

    _render_breadcrumb([("Konfiguration", go_home), ("Baureihen", go_series_overview), (series, None)])
    with ui.row().classes("cfg-action-row"):
        ui.button("Zurück", on_click=go_series_overview).classes("cfg-btn-secondary")
        if not is_general:
            ui.button(
                "Fahrzeug hinzufügen",
                on_click=lambda: _open_vehicle_dialog(
                    series=series,
                    save_vehicle_series_mapping=save_vehicle_series_mapping,
                    delete_vehicle_series_mapping=delete_vehicle_series_mapping,
                    refresh=refresh,
                ),
            ).classes("cfg-btn-primary")
            ui.button(
                "Friststufe hinzufügen",
                on_click=lambda: _open_frist_dialog(
                    series=series,
                    add_frist_level=add_frist_level,
                    trigger_options=trigger_options,
                    refresh=refresh,
                ),
            ).classes("cfg-btn-secondary")
        ui.button(
            "Arbeitspaket hinzufügen",
            on_click=lambda: _open_package_dialog(
                series=series,
                list_frist_levels=list_frist_levels,
                add_frist_level=add_frist_level,
                trigger_options=trigger_options,
                save_work_package=save_work_package,
                refresh=refresh,
                default_frist=selected_frists[0] if len(selected_frists) == 1 else None,
            ),
        ).classes("cfg-btn-primary")

    filter_options = {ALL_FRISTS: "Alle Friststufen"}
    selected_filter_value = selected_frists[0] if len(selected_frists) == 1 else ALL_FRISTS
    if len(selected_frists) > 1:
        filter_options[MULTI_FRISTS] = "Mehrfachauswahl: " + " + ".join(selected_frists)
        selected_filter_value = MULTI_FRISTS
    filter_options.update({level: level for level in levels})
    package_filter_options = {ALL_WORK_PACKAGES: "Alle Arbeitspakete"}
    package_filter_options.update({title: title for title in available_package_titles})
    total_duration_minutes = sum(_package_capacity_minutes(package) for package in packages)
    package_label = "Arbeitspaket" if len(packages) == 1 else "Arbeitspakete"

    with ui.row().classes("cfg-side-by-side"):
        if not is_general:
            with ui.element("section").classes("cfg-panel cfg-side-panel"):
                ui.label("Fahrzeugnummern dieser Baureihe").classes("cfg-section-title")
                _render_series_vehicle_numbers(
                    series=series,
                    list_vehicle_series_mappings=list_vehicle_series_mappings,
                    save_vehicle_series_mapping=save_vehicle_series_mapping,
                    delete_vehicle_series_mapping=delete_vehicle_series_mapping,
                    refresh=refresh,
                )

            with ui.element("section").classes("cfg-panel cfg-side-panel"):
                with ui.column().classes("w-full gap-3"):
                    ui.label("Friststufen").classes("cfg-section-title")
                    if levels:
                        all_active = all(bool(level_config_by_name.get(level, {}).get("active", True)) for level in levels)
                        with ui.row().classes("w-full items-center gap-2 no-wrap"):
                            all_active_checkbox = ui.checkbox(
                                "Alle in offenen Aufträgen verwenden",
                                value=all_active,
                            ).props("dense")

                            def change_all_active(event) -> None:
                                try:
                                    set_all_frist_levels_active(series, bool(event.value))
                                    ui.notify("Friststufen-Auswahl gespeichert.", type="positive")
                                    refresh()
                                except Exception as ex:
                                    ui.notify(f"Konnte Friststufen-Auswahl nicht speichern: {ex}", type="negative")

                            all_active_checkbox.on_value_change(change_all_active)
                        with ui.column().classes("cfg-frist-list"):
                            for level in levels:
                                _render_draggable_frist_level(
                                    levels=levels,
                                    series=series,
                                    level=level,
                                    level_config=level_config_by_name.get(level, {}),
                                    selected_frists=selected_frists,
                                    state=state,
                                    trigger_options=trigger_options,
                                    update_frist_level_active=update_frist_level_active,
                                    update_frist_level_config=update_frist_level_config,
                                    move_frist_level=move_frist_level,
                                    delete_frist_level=delete_frist_level,
                                    refresh=refresh,
                                )
                    else:
                        ui.label("Noch keine Friststufen für diese Baureihe.").classes("cfg-subtle")

        with ui.element("section").classes("cfg-panel cfg-side-panel"):
            with ui.column().classes("w-full gap-3"):
                with ui.column().classes("w-full gap-2"):
                    ui.label("Arbeitspakete anzeigen").classes("cfg-section-title")
                    with ui.row().classes("w-full gap-2 items-end no-wrap cfg-filter-row"):
                        frist_filter = None
                        if not is_general:
                            frist_filter = ui.select(
                                filter_options,
                                value=selected_filter_value,
                                label="Friststufe filtern",
                            ).props(_select_props()).classes("grow")
                        package_filter = ui.select(
                            package_filter_options,
                            value=selected_package,
                            label="Arbeitspaket filtern",
                        ).props(_select_props()).classes("grow")
                    with ui.row().classes("w-full gap-2 wrap"):
                        ui.label(f"{len(packages)} {package_label}").classes("cfg-kpi")
                        if not is_general:
                            ui.label(f"Gesamtstunden: {_duration_hours_text(total_duration_minutes)}").classes("cfg-kpi")

                    def change_filter(event) -> None:
                        value = str(event.value or ALL_FRISTS)
                        if value == MULTI_FRISTS:
                            return
                        state["frist_filters"] = [] if value == ALL_FRISTS else [value]
                        state["frist_filter"] = value if value != ALL_FRISTS else ALL_FRISTS
                        refresh()

                    def change_package_filter(event) -> None:
                        state["package_filter"] = str(event.value or ALL_WORK_PACKAGES)
                        refresh()

                    if frist_filter is not None:
                        frist_filter.on_value_change(change_filter)
                    package_filter.on_value_change(change_package_filter)

                _render_work_package_table(
                    packages=packages,
                    series=series,
                    selected_frists=selected_frists,
                    list_frist_levels=list_frist_levels,
                    add_frist_level=add_frist_level,
                    trigger_options=trigger_options,
                    save_work_package=save_work_package,
                    delete_work_package=delete_work_package,
                    move_work_package=move_work_package,
                    is_general_series=is_general,
                    refresh=refresh,
                )


def _render_work_package_table(
    *,
    packages: list[dict[str, Any]],
    series: str,
    selected_frists: list[str],
    list_frist_levels: Callable[[str], list[str]],
    add_frist_level: Callable[..., str],
    trigger_options: dict[str, str],
    save_work_package: Callable[..., int],
    delete_work_package: Callable[[int], bool],
    move_work_package: Callable[[str, str, int, int], bool],
    refresh: Callable[[], None],
    is_general_series: bool = False,
) -> None:
    if not packages:
        ui.label("Keine Arbeitspakete für die aktuelle Auswahl vorhanden.").classes("cfg-empty")
        return

    can_reorder = bool(is_general_series) or len(selected_frists) == 1
    package_ids = [int(package.get("id") or 0) for package in packages]

    def drop_on_target(event, target_package_id: int) -> None:
        if not can_reorder:
            return
        args = event.args or {}
        source_raw = str(args.get("source") if isinstance(args, dict) else "").strip()
        placement = str(args.get("placement") if isinstance(args, dict) else "before").strip()
        try:
            source_package_id = int(source_raw)
            target_id = int(target_package_id)
        except Exception:
            ui.notify("Arbeitspaket konnte nicht verschoben werden.", type="warning")
            return
        if source_package_id <= 0 or target_id <= 0 or source_package_id == target_id:
            return
        try:
            source_index = package_ids.index(source_package_id)
            target_index = package_ids.index(target_id)
        except ValueError:
            ui.notify("Arbeitspaket konnte nicht verschoben werden.", type="warning")
            return

        insert_index = target_index + (1 if placement == "after" else 0)
        if source_index < insert_index:
            insert_index -= 1
        if insert_index == source_index:
            return
        direction = 1 if insert_index > source_index else -1
        moved = False
        try:
            for _ in range(abs(insert_index - source_index)):
                reorder_frist = GENERAL_FRIST_LEVEL if is_general_series else str(selected_frists[0] if selected_frists else "")
                moved = move_work_package(series, reorder_frist, source_package_id, direction) or moved
            if moved:
                ui.notify("Arbeitspaket verschoben.", type="positive")
            refresh()
        except Exception as ex:
            ui.notify(f"Konnte Arbeitspaket nicht verschieben: {ex}", type="negative")

    with ui.column().classes("w-full gap-2 mt-3"):
        for package in packages:
            package_id = int(package.get("id") or 0)
            item_classes = "cfg-row-card items-center gap-3 no-wrap"
            if can_reorder and package_id > 0:
                item_classes += " cfg-frist-item"
            with ui.row().classes(item_classes) as item:
                if can_reorder and package_id > 0:
                    item.props("draggable=true")
                    item.on(
                        "dragstart",
                        js_handler=f"(event) => event.dataTransfer.setData('text/plain', {package_id!r})",
                    )
                    item.on("dragover", js_handler=_drag_over_line_js())
                    item.on("dragleave", js_handler=_drag_clear_line_js())
                    item.on("dragend", js_handler=_drag_clear_line_js())
                    item.on(
                        "drop",
                        lambda event, target_id=package_id: drop_on_target(event, target_id),
                        js_handler=_drop_emit_line_js(),
                    )
                if is_general_series:
                    ui.label("Standard").classes("cfg-pill")
                else:
                    ui.label(str(package.get("friststufe") or "")).classes("cfg-pill")
                with ui.column().classes("grow gap-1"):
                    ui.label(str(package.get("title") or "")).classes("font-bold")
                    if package.get("_aggregate"):
                        ui.label(
                            f"{int(package.get('employee_count') or 0)} Mitarbeiter - Gesamtzeit: {_duration_hours_text(_package_capacity_minutes(package))}"
                        ).classes("cfg-subtle")
                        for detail in package.get("_aggregate_items") or []:
                            detail_minutes = float(detail.get("duration_minutes") or 0)
                            detail_total = _work_package_total_minutes(detail)
                            total_suffix = ""
                            if abs(detail_total - detail_minutes) > 0.000001:
                                total_suffix = f" (gesamt {_duration_hours_text(detail_total)})"
                            ui.label(
                                f"{detail.get('friststufe') or '-'}: {_duration_hours_text(detail.get('duration_minutes'))}"
                                f" - {int(detail.get('employee_count') or 0)} Mitarbeiter{total_suffix}"
                            ).classes("cfg-package-detail")
                    else:
                        if is_general_series and int(package.get("employee_count") or 0) <= 0 and float(package.get("duration_minutes") or 0) <= 0:
                            ui.label("Standardarbeitspaket").classes("cfg-subtle")
                        else:
                            ui.label(
                                f"{int(package.get('employee_count') or 0)} Mitarbeiter - {_duration_hours_text(package.get('duration_minutes'))}"
                            ).classes("cfg-subtle")

                def edit_current(row: dict[str, Any] = package) -> None:
                    aggregate_items = [dict(item) for item in (row.get("_aggregate_items") or [])]
                    if row.get("_aggregate") and len(aggregate_items) > 1:
                        _open_multi_package_dialog(
                            series=series,
                            package=dict(row),
                            save_work_package=save_work_package,
                            refresh=refresh,
                        )
                        return
                    edit_row = aggregate_items[0] if aggregate_items else dict(row)
                    _open_package_dialog(
                        series=series,
                        list_frist_levels=list_frist_levels,
                        add_frist_level=add_frist_level,
                        trigger_options=trigger_options,
                        save_work_package=save_work_package,
                        refresh=refresh,
                        edit_package=edit_row,
                    )

                ui.button("Bearbeiten", on_click=edit_current).classes("cfg-btn-secondary")

                ui.button(
                    "Löschen",
                    on_click=lambda row=package: _open_delete_work_package_dialog(
                        package=dict(row),
                        delete_work_package=delete_work_package,
                        refresh=refresh,
                    ),
                ).classes("cfg-btn-danger")


def _render_draggable_frist_level(
    *,
    levels: list[str],
    series: str,
    level: str,
    level_config: dict[str, Any],
    selected_frists: list[str],
    state: dict[str, Any],
    trigger_options: dict[str, str],
    update_frist_level_active: Callable[[str, str, bool], bool],
    update_frist_level_config: Callable[[str, str, str, str], str],
    move_frist_level: Callable[[str, str, int], bool],
    delete_frist_level: Callable[[str, str], bool],
    refresh: Callable[[], None],
) -> None:
    def select_level(current_level: str = level) -> None:
        current_selected = list(selected_frists)
        if bool(state.get("_frist_single_select_mode")):
            current_selected = [] if current_level in current_selected and len(current_selected) == 1 else [current_level]
        elif current_level in current_selected:
            current_selected.remove(current_level)
        else:
            current_trigger = str((level_config or {}).get("trigger_type") or "time")
            for selected_level in current_selected:
                selected_config = state.get("_frist_level_config_by_name", {}).get(selected_level, {})
                if str(selected_config.get("trigger_type") or "time") == current_trigger:
                    ui.notify(
                        "Mehrere Friststufen mit gleicher Fristauslösung können nicht gemeinsam ausgewählt werden.",
                        type="warning",
                    )
                    return
            current_selected.append(current_level)
        state["frist_filters"] = current_selected
        state["frist_filter"] = current_selected[0] if len(current_selected) == 1 else ALL_FRISTS
        refresh()

    def drop_on_target(event, target_level: str = level) -> None:
        args = event.args or {}
        source_level = str(args.get("source") if isinstance(args, dict) else "").strip()
        placement = str(args.get("placement") if isinstance(args, dict) else "before").strip()
        if not source_level or source_level == target_level:
            return
        try:
            source_index = levels.index(source_level)
            target_index = levels.index(target_level)
        except ValueError:
            ui.notify("Friststufe konnte nicht verschoben werden.", type="warning")
            return

        insert_index = target_index + (1 if placement == "after" else 0)
        if source_index < insert_index:
            insert_index -= 1
        if insert_index == source_index:
            return
        direction = 1 if insert_index > source_index else -1
        moved = False
        try:
            for _ in range(abs(insert_index - source_index)):
                moved = move_frist_level(series, source_level, direction) or moved
            if moved:
                ui.notify("Friststufe verschoben.", type="positive")
            refresh()
        except Exception as ex:
            ui.notify(f"Konnte Friststufe nicht verschieben: {ex}", type="negative")

    item_classes = "cfg-frist-item items-center gap-2"
    if level in selected_frists:
        item_classes += " cfg-frist-item-selected"
    if not bool(level_config.get("active", True)):
        item_classes += " opacity-60"
    with ui.row().classes(item_classes) as item:
        item.props("draggable=true")
        item.on("click", lambda _event=None, current_level=level: select_level(current_level))
        item.on(
            "dragstart",
            js_handler=f"(event) => event.dataTransfer.setData('text/plain', {level!r})",
        )
        item.on(
            "dragover",
            js_handler=_drag_over_line_js(),
        )
        item.on("dragleave", js_handler=_drag_clear_line_js())
        item.on("dragend", js_handler=_drag_clear_line_js())
        item.on(
            "drop",
            drop_on_target,
            js_handler=_drop_emit_line_js(),
        )
        active_checkbox = ui.checkbox(value=bool(level_config.get("active", True))).props("dense")
        active_checkbox.tooltip("In offenen Aufträgen verwenden")

        def change_active(event, current_level: str = level) -> None:
            try:
                update_frist_level_active(series, current_level, bool(event.value))
                ui.notify("Friststufe aktiviert." if bool(event.value) else "Friststufe deaktiviert.", type="positive")
                refresh()
            except Exception as ex:
                ui.notify(f"Konnte Friststufe nicht speichern: {ex}", type="negative")

        active_checkbox.on_value_change(change_active)
        active_checkbox.on("click", js_handler="(event) => event.stopPropagation()")
        ui.label(level).classes("cfg-pill")
        with ui.column().classes("grow gap-0 min-w-[140px]"):
            ui.label("Fristauslösung").classes("cfg-mini-label")
            ui.label(_trigger_label(trigger_options, level_config.get("trigger_type"))).classes("cfg-subtle")
        edit_button = ui.button(
            "Bearbeiten",
            on_click=lambda current_level=level, current_config=dict(level_config): _open_edit_frist_dialog(
                series=series,
                level=current_level,
                level_config=current_config,
                trigger_options=trigger_options,
                update_frist_level_config=update_frist_level_config,
                state=state,
                refresh=refresh,
            ),
        ).classes("cfg-btn-secondary").props("dense")
        edit_button.on("click", js_handler="(event) => event.stopPropagation()")
        delete_button = ui.button(
            "Löschen",
            on_click=lambda current_level=level: _open_delete_frist_dialog(
                series=series,
                level=current_level,
                state=state,
                delete_frist_level=delete_frist_level,
                refresh=refresh,
            ),
        ).classes("cfg-btn-danger").props("dense")
        delete_button.on("click", js_handler="(event) => event.stopPropagation()")


def _render_series_vehicle_numbers(
    *,
    series: str,
    list_vehicle_series_mappings: Callable[..., list[dict[str, Any]]],
    save_vehicle_series_mapping: Callable[[str, str], None],
    delete_vehicle_series_mapping: Callable[[str], bool],
    refresh: Callable[[], None],
) -> None:
    rows = list_vehicle_series_mappings(series)
    if not rows:
        ui.label("Noch keine Fahrzeugnummern für diese Baureihe zugeordnet.").classes("cfg-empty")
        return

    with ui.column().classes("w-full gap-2 mt-3"):
        for row in rows:
            with ui.row().classes("cfg-row-card items-center gap-3 no-wrap"):
                ui.label(str(row.get("vehicle_number") or "")).classes("min-w-[220px] font-bold")
                ui.label(str(row.get("baureihe") or "")).classes("grow cfg-subtle")

                def edit_mapping(item=row) -> None:
                    _open_vehicle_dialog(
                        series=series,
                        save_vehicle_series_mapping=save_vehicle_series_mapping,
                        delete_vehicle_series_mapping=delete_vehicle_series_mapping,
                        refresh=refresh,
                        edit_mapping=dict(item),
                    )

                ui.button("Bearbeiten", on_click=edit_mapping).classes("cfg-btn-secondary")
                ui.button(
                    "Löschen",
                    on_click=lambda item=row: _open_delete_vehicle_dialog(
                        vehicle_number=str(item.get("vehicle_number") or ""),
                        delete_vehicle_series_mapping=delete_vehicle_series_mapping,
                        refresh=refresh,
                    ),
                ).classes("cfg-btn-danger")


def _open_vehicle_dialog(
    *,
    series: str,
    save_vehicle_series_mapping: Callable[[str, str], None],
    delete_vehicle_series_mapping: Callable[[str], bool],
    refresh: Callable[[], None],
    edit_mapping: dict[str, Any] | None = None,
) -> None:
    edit = dict(edit_mapping or {})
    title = "Fahrzeug bearbeiten" if edit else "Fahrzeug hinzufügen"
    with ui.dialog() as dialog, ui.card().classes("cfg-dialog-card"):
        ui.label(title).classes("dialog-title")
        ui.label(f"Baureihe: {series}").classes("cfg-subtle")
        vehicle_input = ui.input(
            "Fahrzeugnummer",
            value=str(edit.get("vehicle_number") or ""),
        ).props("outlined dense").classes("w-full")
        with ui.row().classes("w-full justify-end gap-2 mt-3"):
            ui.button("Abbrechen", on_click=dialog.close).classes("cfg-btn-secondary")

            def save() -> None:
                old_vehicle = str(edit.get("vehicle_number") or "").strip()
                new_vehicle = str(vehicle_input.value or "").strip()
                try:
                    save_vehicle_series_mapping(new_vehicle, series)
                    if old_vehicle and old_vehicle != new_vehicle:
                        delete_vehicle_series_mapping(old_vehicle)
                    ui.notify("Fahrzeugnummer gespeichert.", type="positive")
                    dialog.close()
                    refresh()
                except Exception as ex:
                    ui.notify(f"Konnte Fahrzeugnummer nicht speichern: {ex}", type="negative")

            ui.button("Speichern", on_click=save).classes("cfg-btn-primary")
    dialog.open()


def _open_delete_vehicle_dialog(
    *,
    vehicle_number: str,
    delete_vehicle_series_mapping: Callable[[str], bool],
    refresh: Callable[[], None],
) -> None:
    vehicle = str(vehicle_number or "").strip()
    with ui.dialog() as dialog, ui.card().classes("cfg-dialog-card"):
        ui.label("Fahrzeugnummer löschen").classes("dialog-title")
        ui.label(f"Soll die Fahrzeugnummer {vehicle} wirklich gelöscht werden?").classes("cfg-subtle")
        with ui.row().classes("w-full justify-end gap-2 mt-3"):
            ui.button("Abbrechen", on_click=dialog.close).classes("cfg-btn-secondary")

            def confirm() -> None:
                if delete_vehicle_series_mapping(vehicle):
                    ui.notify("Fahrzeugnummer gelöscht.", type="positive")
                else:
                    ui.notify("Fahrzeugnummer nicht gefunden.", type="warning")
                dialog.close()
                refresh()

            ui.button("Löschen", on_click=confirm).classes("cfg-btn-danger")
    dialog.open()


def _open_delete_work_package_dialog(
    *,
    package: dict[str, Any],
    delete_work_package: Callable[[int], bool],
    refresh: Callable[[], None],
) -> None:
    items = list(package.get("_aggregate_items") or [])
    if not items:
        items = [package]
    package_ids = [int(item.get("id") or 0) for item in items if int(item.get("id") or 0) > 0]
    title = str(package.get("title") or "").strip()
    is_aggregate = bool(package.get("_aggregate")) and len(package_ids) > 1
    with ui.dialog() as dialog, ui.card().classes("cfg-dialog-card"):
        ui.label("Arbeitspaket löschen").classes("dialog-title")
        if is_aggregate:
            ui.label(
                f"Sollen alle {len(package_ids)} Einträge des zusammengefassten Arbeitspakets {title} gelöscht werden?"
            ).classes("cfg-subtle")
        else:
            ui.label(f"Soll das Arbeitspaket {title} wirklich gelöscht werden?").classes("cfg-subtle")
        with ui.row().classes("w-full justify-end gap-2 mt-3"):
            ui.button("Abbrechen", on_click=dialog.close).classes("cfg-btn-secondary")

            def confirm() -> None:
                deleted = 0
                for package_id in package_ids:
                    if delete_work_package(package_id):
                        deleted += 1
                if deleted:
                    ui.notify("Arbeitspaket gelöscht.", type="positive")
                else:
                    ui.notify("Arbeitspaket nicht gefunden.", type="warning")
                dialog.close()
                refresh()

            ui.button("Löschen", on_click=confirm).classes("cfg-btn-danger")
    dialog.open()


def _open_delete_frist_dialog(
    *,
    series: str,
    level: str,
    state: dict[str, Any],
    delete_frist_level: Callable[[str, str], bool],
    refresh: Callable[[], None],
) -> None:
    with ui.dialog() as dialog, ui.card().classes("cfg-dialog-card"):
        ui.label("Friststufe löschen").classes("dialog-title")
        ui.label(f"Soll die Friststufe {level} für {series} wirklich gelöscht werden?").classes("cfg-subtle")
        with ui.row().classes("w-full justify-end gap-2 mt-3"):
            ui.button("Abbrechen", on_click=dialog.close).classes("cfg-btn-secondary")

            def confirm() -> None:
                try:
                    if delete_frist_level(series, level):
                        if state.get("frist_filter") == level:
                            state["frist_filter"] = ALL_FRISTS
                        ui.notify("Friststufe gelöscht.", type="positive")
                    else:
                        ui.notify("Friststufe nicht gefunden.", type="warning")
                    dialog.close()
                    refresh()
                except Exception as ex:
                    ui.notify(f"Konnte Friststufe nicht löschen: {ex}", type="negative")

            ui.button("Löschen", on_click=confirm).classes("cfg-btn-danger")
    dialog.open()


def _open_series_dialog(*, add_series: Callable[[str], str], refresh: Callable[[], None]) -> None:
    with ui.dialog() as dialog, ui.card().classes("cfg-dialog-card"):
        ui.label("Neue Baureihe hinzufügen").classes("dialog-title")
        name_input = ui.input("Name der Baureihe").props("outlined dense").classes("w-full")
        with ui.row().classes("w-full justify-end gap-2 mt-3"):
            ui.button("Abbrechen", on_click=dialog.close).classes("cfg-btn-secondary")

            def save() -> None:
                try:
                    add_series(str(name_input.value or ""))
                    ui.notify("Baureihe gespeichert.", type="positive")
                    dialog.close()
                    refresh()
                except Exception as ex:
                    ui.notify(f"Konnte Baureihe nicht speichern: {ex}", type="negative")

            ui.button("Speichern", on_click=save).classes("cfg-btn-primary")
    dialog.open()


def _open_frist_dialog(
    *,
    series: str,
    add_frist_level: Callable[..., str],
    trigger_options: dict[str, str],
    refresh: Callable[[], None],
) -> None:
    with ui.dialog() as dialog, ui.card().classes("cfg-dialog-card"):
        ui.label(f"Friststufe für Baureihe {series} hinzufügen").classes("dialog-title")
        frist_input = ui.input("Name der Friststufe").props("outlined dense").classes("w-full")
        ui.label("Fristauslösung").classes("cfg-subtle")
        trigger_choice = ui.radio(trigger_options, value=None).props("inline").classes("w-full")
        with ui.row().classes("w-full justify-end gap-2 mt-3"):
            ui.button("Abbrechen", on_click=dialog.close).classes("cfg-btn-secondary")

            def save() -> None:
                try:
                    if not str(trigger_choice.value or "").strip():
                        raise ValueError("Bitte eine Fristauslösung auswählen.")
                    add_frist_level(series, str(frist_input.value or ""), str(trigger_choice.value or ""))
                    ui.notify("Friststufe gespeichert.", type="positive")
                    dialog.close()
                    refresh()
                except Exception as ex:
                    ui.notify(f"Konnte Friststufe nicht speichern: {ex}", type="negative")

            ui.button("Speichern", on_click=save).classes("cfg-btn-primary")
    dialog.open()


def _open_edit_frist_dialog(
    *,
    series: str,
    level: str,
    level_config: dict[str, Any],
    trigger_options: dict[str, str],
    update_frist_level_config: Callable[[str, str, str, str], str],
    state: dict[str, Any],
    refresh: Callable[[], None],
) -> None:
    current_trigger = str(level_config.get("trigger_type") or "time")
    with ui.dialog() as dialog, ui.card().classes("cfg-dialog-card"):
        ui.label(f"Friststufe für {series} bearbeiten").classes("dialog-title")
        name_input = ui.input("Name der Friststufe", value=str(level or "")).props("outlined dense").classes("w-full")
        ui.label("Fristauslösung").classes("cfg-subtle")
        trigger_radio = ui.radio(trigger_options, value=current_trigger).props("inline").classes("w-full")
        with ui.row().classes("w-full justify-end gap-2 mt-3"):
            ui.button("Abbrechen", on_click=dialog.close).classes("cfg-btn-secondary")

            def save() -> None:
                try:
                    new_level = update_frist_level_config(
                        series,
                        level,
                        str(name_input.value or ""),
                        str(trigger_radio.value or "time"),
                    )
                    selected = [
                        new_level if str(item or "").strip() == str(level or "").strip() else str(item or "").strip()
                        for item in (state.get("frist_filters") or [])
                        if str(item or "").strip()
                    ]
                    state["frist_filters"] = selected
                    state["frist_filter"] = selected[0] if len(selected) == 1 else ALL_FRISTS
                    ui.notify("Friststufe gespeichert.", type="positive")
                    dialog.close()
                    refresh()
                except Exception as ex:
                    ui.notify(f"Konnte Friststufe nicht speichern: {ex}", type="negative")

            ui.button("Speichern", on_click=save).classes("cfg-btn-primary")
    dialog.open()


def _open_package_dialog(
    *,
    series: str,
    list_frist_levels: Callable[[str], list[str]],
    add_frist_level: Callable[..., str],
    trigger_options: dict[str, str],
    save_work_package: Callable[..., int],
    refresh: Callable[[], None],
    edit_package: dict[str, Any] | None = None,
    default_frist: str | None = None,
) -> None:
    edit = dict(edit_package or {})
    is_general = _is_general_series(series)
    levels = list_frist_levels(series)
    selected_frist = GENERAL_FRIST_LEVEL if is_general else str(edit.get("friststufe") or default_frist or (levels[0] if levels else NEW_FRIST))
    title = str(edit.get("title") or "")
    employees = int(edit.get("employee_count") or (0 if is_general else 1))
    duration = 0.0 if is_general else _duration_input_value(edit.get("duration_minutes"))
    frist_options = {level: level for level in levels}
    if selected_frist and selected_frist != NEW_FRIST and selected_frist not in frist_options:
        frist_options[selected_frist] = selected_frist
    if not is_general:
        frist_options[NEW_FRIST] = "Neue Friststufe anlegen"
    select_value = selected_frist if selected_frist in frist_options else NEW_FRIST
    dialog_title = (
        f"Arbeitspaket für Baureihe {series} bearbeiten"
        if edit
        else f"Arbeitspaket für Baureihe {series} erstellen"
    )

    with ui.dialog() as dialog, ui.card().classes("cfg-dialog-card"):
        ui.label(dialog_title).classes("dialog-title")
        if is_general:
            ui.label("Standardarbeitspaket ohne Friststufe, Mitarbeiteranzahl und Dauer.").classes("cfg-subtle")
            frist_select = None
            new_frist_input = None
            new_frist_trigger = None
        else:
            ui.label("Vorhandene Friststufe auswählen oder eine neue Friststufe anlegen.").classes("cfg-subtle")
            frist_select = ui.select(frist_options, value=select_value, label="Friststufe").props(_select_props()).classes("w-full")
            with ui.column().classes("w-full") as new_frist_row:
                new_frist_input = ui.input("Neue Friststufe").props("outlined dense").classes("w-full")
                ui.label("Fristauslösung der neuen Friststufe").classes("cfg-subtle")
                new_frist_trigger = ui.radio(trigger_options, value=None).props("inline").classes("w-full")
            new_frist_row.visible = select_value == NEW_FRIST
            new_frist_row.bind_visibility_from(frist_select, "value", lambda value: str(value or "") == NEW_FRIST)
        title_input = ui.input("Titel").props("outlined dense").classes("w-full")
        title_input.value = title
        if is_general:
            employee_input = None
            duration_input = None
        else:
            with ui.row().classes("w-full gap-3"):
                employee_input = ui.number("Mitarbeiter", value=employees).props("outlined dense min=1 step=1").classes("grow")
                duration_input = ui.number("Dauer (Stunden)", value=duration).props("outlined dense min=0.5 step=0.5").classes("grow")

        with ui.row().classes("w-full justify-end gap-2 mt-3"):
            ui.button("Abbrechen", on_click=dialog.close).classes("cfg-btn-secondary")

            def save() -> None:
                try:
                    if is_general:
                        frist = GENERAL_FRIST_LEVEL
                    elif str(frist_select.value or "") == NEW_FRIST:
                        new_frist = str(new_frist_input.value or "").strip()
                        if not str(new_frist_trigger.value or "").strip():
                            raise ValueError("Bitte eine Fristauslösung auswählen.")
                        frist = add_frist_level(series, new_frist, str(new_frist_trigger.value or ""))
                    else:
                        frist = str(frist_select.value or "").strip()
                    if not frist:
                        raise ValueError("Bitte eine Friststufe auswählen oder neu eintragen.")
                    duration_hours = 0.0 if is_general else float(duration_input.value or 0)
                    if not is_general:
                        if duration_hours < 0.5:
                            raise ValueError("Dauer muss mindestens 0,5 Stunden betragen.")
                        if not _is_half_hour_step(duration_hours):
                            raise ValueError("Dauer darf nur in 0,5-Stunden-Schritten gespeichert werden.")
                    save_work_package(
                        package_id=int(edit["id"]) if edit else None,
                        baureihe=series,
                        friststufe=frist,
                        title=str(title_input.value or ""),
                        employee_count=0 if is_general else int(employee_input.value or 0),
                        duration_minutes=duration_hours * 60.0,
                    )
                    ui.notify("Arbeitspaket gespeichert.", type="positive")
                    dialog.close()
                    refresh()
                except Exception as ex:
                    ui.notify(f"Konnte Arbeitspaket nicht speichern: {ex}", type="negative")

            ui.button("Speichern", on_click=save).classes("cfg-btn-primary")
    dialog.open()


def _open_multi_package_dialog(
    *,
    series: str,
    package: dict[str, Any],
    save_work_package: Callable[..., int],
    refresh: Callable[[], None],
) -> None:
    items = [dict(item) for item in (package.get("_aggregate_items") or []) if int(item.get("id") or 0) > 0]
    items.sort(key=lambda row: str(row.get("friststufe") or ""))
    if len(items) <= 1:
        ui.notify("Für dieses Arbeitspaket gibt es keine zusammengefassten Einträge.", type="warning")
        return

    title = str(package.get("title") or items[0].get("title") or "")
    with ui.dialog() as dialog, ui.card().classes("cfg-dialog-card"):
        ui.label(f"Zusammengefasstes Arbeitspaket für {series} bearbeiten").classes("dialog-title")
        ui.label("Stunden und Mitarbeiter werden je Friststufe einzeln gespeichert.").classes("cfg-subtle")
        title_input = ui.input("Titel", value=title).props("outlined dense").classes("w-full")
        editors: list[tuple[dict[str, Any], Any, Any]] = []
        with ui.column().classes("w-full gap-2"):
            for item in items:
                frist = str(item.get("friststufe") or "").strip()
                with ui.element("div").classes("cfg-row-card"):
                    with ui.row().classes("w-full items-center gap-2 wrap"):
                        ui.label(frist or "-").classes("cfg-pill")
                        employee_input = ui.number(
                            "Mitarbeiter",
                            value=int(item.get("employee_count") or 1),
                        ).props("outlined dense min=1 step=1").classes("grow min-w-[150px]")
                        duration_input = ui.number(
                            "Dauer (Stunden)",
                            value=_duration_input_value(item.get("duration_minutes")),
                        ).props("outlined dense min=0.5 step=0.5").classes("grow min-w-[170px]")
                    editors.append((item, employee_input, duration_input))

        with ui.row().classes("w-full justify-end gap-2 mt-3"):
            ui.button("Abbrechen", on_click=dialog.close).classes("cfg-btn-secondary")

            def save() -> None:
                try:
                    clean_title = str(title_input.value or "").strip()
                    if not clean_title:
                        raise ValueError("Bitte einen Titel eintragen.")
                    for item, employee_input, duration_input in editors:
                        duration_hours = float(duration_input.value or 0)
                        if duration_hours < 0.5:
                            raise ValueError("Dauer muss mindestens 0,5 Stunden betragen.")
                        if not _is_half_hour_step(duration_hours):
                            raise ValueError("Dauer darf nur in 0,5-Stunden-Schritten gespeichert werden.")
                        employees = int(employee_input.value or 0)
                        if employees < 1:
                            raise ValueError("Mitarbeiteranzahl muss mindestens 1 sein.")
                        save_work_package(
                            package_id=int(item["id"]),
                            baureihe=series,
                            friststufe=str(item.get("friststufe") or ""),
                            title=clean_title,
                            employee_count=employees,
                            duration_minutes=duration_hours * 60.0,
                        )
                    ui.notify("Arbeitspaket je Friststufe gespeichert.", type="positive")
                    dialog.close()
                    refresh()
                except Exception as ex:
                    ui.notify(f"Konnte Arbeitspaket nicht speichern: {ex}", type="negative")

            ui.button("Speichern", on_click=save).classes("cfg-btn-primary")
    dialog.open()
