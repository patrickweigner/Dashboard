from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

import pandas as pd
from nicegui import ui

from core.ui_runtime import create_page_timer
from services.gleisplan_service import (
    HALL_TRACK_LABELS,
    HALL_TRACKS,
    SWITCH_BRANCH_HEEL_X_RATIO,
    SWITCH_BRANCH_PORT_X_RATIO,
    SWITCH_BRANCH_PORT_Y_RATIO,
    SWITCH_MAIN_RAIL_Y_RATIO,
    build_gleisplan_model,
    build_vehicle_catalog,
    delete_gleisplan_assignment,
    find_open_task_for_vehicle,
    load_gleisplan_assignments,
    load_gleisplan_connections,
    load_gleisplan_hall_tracks,
    load_gleisplan_layout_items,
    save_gleisplan_assignment,
)


def _progress_text(prefix: str, progress: dict[str, Any] | None) -> str:
    if not progress:
        return f"{prefix}: -"
    total = int(progress.get("total") or 0)
    if total <= 0:
        return f"{prefix}: -"
    done = int(progress.get("done") or 0)
    return f"{prefix}: {done}/{total}"


def _source_text(vehicle: dict[str, Any]) -> str:
    source = str(vehicle.get("source") or "").strip()
    if source == "werkstatthalle":
        return "Werkstatthalle"
    if source == "gleisplan+open_tasks":
        return "Gleisplan + Auftrag"
    if source == "gleisplan":
        return "Gleisplan"
    return ""


def _render_vehicle_block(vehicle: dict[str, Any] | None, *, compact: bool = False) -> None:
    if not vehicle:
        with ui.element("div").classes("gleisplan-empty-vehicle"):
            ui.label("frei").classes("gleisplan-empty-label")
        return

    status_bg = str(vehicle.get("status_bg") or "#64748b")
    status_fg = str(vehicle.get("status_fg") or "#f8fafc")
    card_cls = "gleisplan-vehicle-card gleisplan-vehicle-card-compact" if compact else "gleisplan-vehicle-card"
    with ui.element("div").classes(card_cls).style(f"--vehicle-status-bg:{status_bg};"):
        with ui.row().classes("w-full items-start justify-between gap-2 no-wrap"):
            ui.label(str(vehicle.get("vehicle_label") or "-")).classes("gleisplan-vehicle-title")
            status_text = str(vehicle.get("status_text") or "").strip()
            if status_text and not compact:
                ui.label(status_text).classes("gleisplan-status-pill").style(
                    f"background:{status_bg}; color:{status_fg};"
                )
        meta_parts = []
        series = str(vehicle.get("series_label") or "").strip()
        if series:
            meta_parts.append(series)
        if bool(vehicle.get("has_open_task")):
            meta_parts.append(f"Frist {vehicle.get('frist_label') or '-'}")
            meta_parts.append(f"Ende {vehicle.get('end_label') or '-'}")
        source = _source_text(vehicle)
        if source and not compact:
            meta_parts.append(source)
        if meta_parts:
            ui.label(" | ".join(meta_parts)).classes("gleisplan-vehicle-meta")
        if bool(vehicle.get("has_open_task")) and not compact:
            with ui.row().classes("w-full gap-2 wrap"):
                ui.label(_progress_text("Frist", vehicle.get("frist_progress"))).classes("gleisplan-mini-pill")
                ui.label(_progress_text("Zusatz", vehicle.get("zus_progress"))).classes("gleisplan-mini-pill")


def _item_style(item: dict[str, Any]) -> str:
    return (
        f"left:{float(item.get('x_pct') or 0):.3f}%;"
        f"top:{float(item.get('y_pct') or 0):.3f}%;"
        f"width:{float(item.get('w_pct') or 10):.3f}%;"
        f"height:{float(item.get('h_pct') or 8):.3f}%;"
        f"transform:rotate({float(item.get('rotation') or 0):.3f}deg);"
        f"--layout-color:{str(item.get('color') or '').strip() or '#dc2626'};"
        f"--curve-radius:{float(item.get('curve_radius') or 0):.3f}%;"
    )


def _render_gleishalle(model: dict[str, Any], item: dict[str, Any]) -> None:
    hall_grid = model.get("hall_grid") or ()
    occupancy = model.get("hall_occupancy") or {}

    with ui.element("div").classes("gleishalle-panel gleishalle-panel-map gleisplan-layout-object").style(_item_style(item)):
        with ui.row().classes("w-full items-center justify-between gap-2"):
            ui.label("Werkstatt mit Gleishalle").classes("gleishalle-title")
            ui.label("Quelle: Werkstatthalle / Gleisplan").classes("gleishalle-source")
        with ui.element("div").classes("gleishalle-grid-2x2"):
            for row in hall_grid:
                for area_code in row:
                    slot = occupancy.get(area_code) or {}
                    position_label = str(slot.get("position_label") or HALL_TRACK_LABELS.get(str(area_code), ""))
                    vehicle = slot.get("vehicle")
                    extras = slot.get("extras") or []
                    with ui.element("div").classes("gleishalle-cell"):
                        with ui.row().classes("w-full items-center justify-between gap-2"):
                            ui.label(str(area_code)).classes("gleishalle-area")
                            ui.label(position_label).classes("gleishalle-position")
                        _render_vehicle_block(vehicle, compact=True)
                        if extras:
                            ui.label(f"+ {len(extras)} weitere").classes("gleisplan-extra-label")


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
    point = _switch_local_geometry(item).get(f"port{port}") or _switch_local_geometry(item)["port1"]
    return (
        f"left:calc({point[0] * 100:.3f}% - 6px);"
        f"top:calc({point[1] * 100:.3f}% - 6px);right:auto;bottom:auto;"
    )


def _switch_anchor_debug_style(item: dict[str, Any], anchor: str) -> str:
    port_by_anchor = {"straight": "1", "stem": "2", "branch": "3"}
    port = port_by_anchor.get(str(anchor), "1")
    point = _switch_local_geometry(item).get(f"port{port}") or _switch_local_geometry(item)["port1"]
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


def _render_switch_symbol(label: str, item: dict[str, Any]) -> None:
    with ui.element("div").classes("gleisplan-switch-symbol"):
        ui.html(_switch_svg_markup(item), sanitize=False)
        ui.element("div").classes("gleisplan-switch-hatch")
        ui.element("div").classes("gleisplan-switch-heel")
        for anchor_name in ("stem", "straight", "branch"):
            ui.element("div").classes(
                f"gleisplan-switch-anchor-debug anchor-{anchor_name}"
            ).style(_switch_anchor_debug_style(item, anchor_name)).props(f'data-anchor="{anchor_name}"')
        ui.label("1").classes("gleisplan-switch-port-label port-1").style(_switch_port_label_style(item, "1"))
        ui.label("2").classes("gleisplan-switch-port-label port-2").style(_switch_port_label_style(item, "2"))
        ui.label("3").classes("gleisplan-switch-port-label port-3").style(_switch_port_label_style(item, "3"))
        ui.label(label).classes("gleisplan-switch-node-label")


def _render_buffer_stop_symbol(label: str) -> None:
    with ui.element("div").classes("gleisplan-buffer-stop-symbol"):
        ui.element("div").classes("gleisplan-buffer-stop-rail")
        ui.element("div").classes("gleisplan-buffer-stop-beam")
        ui.element("div").classes("gleisplan-buffer-stop-post")
        ui.label(label).classes("gleisplan-buffer-stop-label")


def _render_layout_item(item: dict[str, Any]) -> None:
    item_id = str(item.get("id") or item.get("item_id") or "")
    item_type = str(item.get("item_type") or "track").strip().lower()
    if item_type in {"track", "anchor"}:
        return
    if item_type == "hall" or item_id in HALL_TRACKS:
        return
    if item_type == "street":
        ui.element("div").classes("gleisplan-layout-object gleisplan-map-street").style(_item_style(item))
        return
    if item_type == "building":
        with ui.element("div").classes(f"gleisplan-layout-object gleisplan-map-{item_type}").style(_item_style(item)):
            ui.label(str(item.get("label") or "")).classes("gleisplan-layout-label")
        return
    if item_type == "switch":
        with ui.element("div").classes("gleisplan-layout-object gleisplan-map-switch").style(_item_style(item)):
            _render_switch_symbol(str(item.get("label") or ""), item)
        return
    if item_type == "buffer_stop":
        with ui.element("div").classes("gleisplan-layout-object gleisplan-map-buffer-stop").style(_item_style(item)):
            _render_buffer_stop_symbol(str(item.get("label") or ""))
        return
    with ui.element("div").classes("gleisplan-track-node gleisplan-layout-object").style(_item_style(item)):
        with ui.row().classes("w-full items-center justify-between gap-2 no-wrap"):
            ui.label(str(item.get("label") or "")).classes("gleisplan-track-node-label")
            ui.label(str(item.get("title") or "")).classes("gleisplan-track-node-title")
        ui.element("div").classes("gleisplan-track-node-line")
        _render_vehicle_block(item.get("vehicle"), compact=True)


def _route_path_d(route: dict[str, Any] | None) -> str:
    if not isinstance(route, dict):
        return ""
    route_type = str(route.get("type") or "").strip().lower()
    d = str(route.get("d") or "").strip()
    if route_type == "path" and d:
        return d
    points: list[tuple[float, float]] = []
    for point in route.get("points") or []:
        if not isinstance(point, dict):
            continue
        try:
            points.append((float(point.get("x_pct", point.get("x"))), float(point.get("y_pct", point.get("y")))))
        except Exception:
            continue
    if len(points) < 2:
        start = route.get("start") if isinstance(route.get("start"), dict) else None
        end = route.get("end") if isinstance(route.get("end"), dict) else None
        if start and end:
            try:
                points = [
                    (float(start.get("x_pct", start.get("x"))), float(start.get("y_pct", start.get("y")))),
                    (float(end.get("x_pct", end.get("x"))), float(end.get("y_pct", end.get("y")))),
                ]
            except Exception:
                points = []
    if len(points) < 2:
        return ""
    if route.get("smooth") and len(points) > 2:
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
    return " ".join(
        [f"M {points[0][0]:.3f} {points[0][1]:.3f}"]
        + [f"L {x:.3f} {y:.3f}" for x, y in points[1:]]
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
    x1 = float(connection.get("x_pct") or 0)
    y1 = float(connection.get("y_pct") or 0)
    x2 = float(connection.get("x2_pct") if connection.get("x2_pct") is not None else x1)
    y2 = float(connection.get("y2_pct") if connection.get("y2_pct") is not None else y1)
    if path_points or has_lead:
        points = [(x1, y1)]
        if connection.get("source_lead_x_pct") is not None and connection.get("source_lead_y_pct") is not None:
            points.append((float(connection.get("source_lead_x_pct") or 0), float(connection.get("source_lead_y_pct") or 0)))
        for point in path_points:
            if isinstance(point, dict):
                points.append((float(point.get("x_pct") or 0), float(point.get("y_pct") or 0)))
        if connection.get("target_lead_x_pct") is not None and connection.get("target_lead_y_pct") is not None:
            points.append((float(connection.get("target_lead_x_pct") or 0), float(connection.get("target_lead_y_pct") or 0)))
        points.append((x2, y2))
        if len(points) == 2:
            return f"M {x1:.3f} {y1:.3f} L {x2:.3f} {y2:.3f}"
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


def _connection_vehicle_style(position: dict[str, Any]) -> str:
    return (
        f"left:{float(position.get('x_pct') or 0):.3f}%;"
        f"top:{float(position.get('y_pct') or 0):.3f}%;"
    )


def _render_connection(connection: dict[str, Any]) -> None:
    line_type = str(connection.get("connection_type") or "track").strip().lower()
    classes = "gleisplan-connection-svg connection-street" if line_type == "street" else "gleisplan-connection-svg"
    path_d = _connection_path_d(connection)
    ui.html(
        (
            f'<svg class="{classes}" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">'
            f'<path class="gleisplan-connection-path" d="{path_d}" />'
            "</svg>"
        ),
        sanitize=False,
    )
    label = str(connection.get("label") or "").strip()
    vehicle_positions = connection.get("vehicle_positions") or []
    if label:
        ui.label(label).classes("gleisplan-connection-label").style(_connection_label_style(connection))
    for position in vehicle_positions:
        vehicle = position.get("vehicle") if isinstance(position, dict) else None
        if not vehicle:
            continue
        with ui.element("div").classes("gleisplan-connection-info").style(_connection_vehicle_style(position)):
            _render_vehicle_block(vehicle, compact=True)


def _render_plan(model: dict[str, Any]) -> None:
    items = model.get("layout_items") or []
    connections = model.get("connections") or []
    ui.add_body_html(
        "<script>(()=>{const apply=()=>{const enabled=new URLSearchParams(window.location.search).get('debug_switch_ports')==='1';"
        "document.querySelectorAll('.gleisplan-map').forEach(el=>el.classList.toggle('show-switch-anchors',enabled));};"
        "const enabled=new URLSearchParams(window.location.search).get('debug_switch_ports')==='1';"
        "apply();requestAnimationFrame(apply);"
        "if(enabled){const observer=new MutationObserver(apply);observer.observe(document.body,{childList:true,subtree:true});"
        "setTimeout(()=>{apply();observer.disconnect();},3000);}})();</script>"
    )
    background_items = [
        item for item in items
        if str(item.get("item_type") or "").strip().lower() in {"building", "street", "hall"}
    ]
    foreground_items = [
        item for item in items
        if str(item.get("item_type") or "").strip().lower() not in {"building", "street", "hall"}
    ]
    with ui.element("div").classes("gleisplan-map gleisplan-map-pdf"):
        for item in background_items:
            if str(item.get("item_type") or "").strip().lower() == "hall":
                _render_gleishalle(model, item)
            else:
                _render_layout_item(item)
        for connection in connections:
            _render_connection(connection)
        for item in foreground_items:
            _render_layout_item(item)


def _render_assignment_panel(
    *,
    model: dict[str, Any],
    df_open: pd.DataFrame,
    admin: bool,
    db_exec: Callable[..., Any],
    now_berlin: Callable[[], datetime],
    norm_vehicle: Callable[[str], str],
    row_allows_area: Callable[[pd.Series, str], bool],
    assign_area: Callable[[int, str], tuple[bool, str]],
    refresh: Callable[[], None],
    using_fallback_catalog: bool,
) -> None:
    with ui.element("div").classes("gleisplan-side-panel"):
        ui.label("Gleis zuordnen").classes("gleisplan-panel-title")
        if using_fallback_catalog:
            ui.label("Fallback: Keine Fahrzeugnummern in der Konfiguration gefunden.").classes("gleisplan-muted")
        if not admin:
            ui.label("Nur Admin kann Zuordnungen ändern.").classes("gleisplan-muted")
            return

        vehicle_options = model.get("vehicle_options") or {}
        track_options = model.get("track_options") or {}
        if not vehicle_options:
            ui.label("Keine Fahrzeuge in der Konfiguration hinterlegt.").classes("gleisplan-muted")
            return
        if not track_options:
            ui.label("Keine benannten Gleisverbindungen vorhanden.").classes("gleisplan-muted")
            return

        default_track = next(iter(track_options.keys()), None)
        target_select = ui.select(track_options, value=default_track, label="Gleis").props(
            "outlined dense popup-content-class=area-select-popup"
        ).classes("w-full gleisplan-select")
        vehicle_select = ui.select(vehicle_options, value=None, label="Fahrzeugnummer").props(
            "outlined dense popup-content-class=area-select-popup"
        ).classes("w-full gleisplan-select")

        def do_assign() -> None:
            target_track = str(target_select.value or "").strip().upper()
            vehicle = str(vehicle_select.value or "").strip()
            if not target_track:
                ui.notify("Bitte ein Gleis auswählen.", type="warning")
                return
            if not vehicle:
                ui.notify("Bitte ein Fahrzeug auswählen.", type="warning")
                return

            if target_track in (model.get("hall_occupancy") or {}):
                hall_slot = (model.get("hall_occupancy") or {}).get(target_track) or {}
                sync_enabled = bool(hall_slot.get("sync_enabled", True))
                sync_area = str(hall_slot.get("workshop_area") or target_track).strip().upper()
                open_row = find_open_task_for_vehicle(df_open, vehicle, norm_vehicle=norm_vehicle)
                if sync_enabled and open_row is not None:
                    try:
                        if callable(row_allows_area) and not row_allows_area(open_row, sync_area):
                            ui.notify("Dieses offene Fahrzeug passt nicht zu diesem Hallengleis.", type="warning")
                            return
                        open_id = int(open_row.get("id") or 0)
                    except Exception:
                        open_id = 0
                    if open_id > 0:
                        ok, msg = assign_area(open_id, sync_area)
                        ui.notify(msg, type="positive" if ok else "negative")
                        if ok:
                            delete_gleisplan_assignment(db_exec, track_id=target_track)
                            refresh()
                        return

            ok, msg = save_gleisplan_assignment(
                db_exec,
                track_id=target_track,
                vehicle_number=vehicle,
                updated_at=now_berlin().isoformat(timespec="seconds"),
            )
            ui.notify(msg, type="positive" if ok else "negative")
            if ok:
                refresh()

        def do_clear() -> None:
            target_track = str(target_select.value or "").strip().upper()
            vehicle = str(vehicle_select.value or "").strip()
            ok, msg = delete_gleisplan_assignment(
                db_exec,
                track_id=target_track,
                vehicle_number=vehicle,
                updated_at=now_berlin().isoformat(timespec="seconds"),
            )
            ui.notify(msg, type="positive" if ok else "negative")
            if ok:
                refresh()

        ui.button("Zuordnen", icon="add_location_alt", on_click=do_assign).classes("btn-big w-full")
        ui.button("Ausgewählte Zuordnung entfernen", icon="clear", on_click=do_clear).classes("btn-remove btn-big w-full")


def render(
    *,
    refresh_interval_seconds: float,
    render_nav: Callable[[], None],
    now_berlin: Callable[[], datetime],
    get_open_tasks_df: Callable[[], pd.DataFrame],
    list_vehicle_series_mappings: Callable[..., list[dict[str, Any]]],
    db_exec: Callable[..., Any],
    normalize_workshop_area: Callable[[Any], str],
    norm_vehicle: Callable[[str], str],
    fmt_dt: Callable[[Any], str],
    status_for_row: Callable[..., tuple[str, str]],
    status_palette: Callable[[str], tuple[str, str]],
    calc_frist_progress: Callable[..., tuple[int, int, list[str], list[bool], bool]],
    calc_zus_progress: Callable[..., tuple[int, int, list[str], list[bool]]],
    get_vehicle_series_for_vehicle: Callable[[Any], str],
    is_admin: Callable[[], bool],
    row_allows_area: Callable[[pd.Series, str], bool],
    assign_area: Callable[[int, str], tuple[bool, str]],
    refresh_when_no_dialog: Callable[[Callable[[], None]], None],
) -> None:
    render_nav()
    with ui.row().classes("w-full items-center justify-between gap-3 wrap"):
        ui.label("Gleisplan").classes("page-title")
        ui.label(now_berlin().strftime("%d.%m.%Y %H:%M")).classes("gleisplan-clock")

    body = ui.column().classes("w-full gap-3 gleisplan-page")

    @ui.refreshable
    def content() -> None:
        body.clear()
        df_open = get_open_tasks_df().copy()
        vehicle_catalog, using_fallback_catalog = build_vehicle_catalog(list_vehicle_series_mappings(), df_open)
        layout_items = load_gleisplan_layout_items(db_exec)
        connections = load_gleisplan_connections(db_exec, layout_items=layout_items)
        hall_tracks = load_gleisplan_hall_tracks(db_exec)
        assignments = load_gleisplan_assignments(db_exec)
        model = build_gleisplan_model(
            df_open,
            assignments=assignments,
            vehicle_catalog=vehicle_catalog,
            layout_items=layout_items,
            connections=connections,
            hall_tracks=hall_tracks,
            normalize_workshop_area=normalize_workshop_area,
            norm_vehicle=norm_vehicle,
            fmt_dt=fmt_dt,
            status_for_row=status_for_row,
            status_palette=status_palette,
            calc_frist_progress=calc_frist_progress,
            calc_zus_progress=calc_zus_progress,
            get_vehicle_series_for_vehicle=get_vehicle_series_for_vehicle,
        )
        with body:
            with ui.element("div").classes("gleisplan-layout"):
                with ui.element("div").classes("gleisplan-main"):
                    _render_plan(model)
                _render_assignment_panel(
                    model=model,
                    df_open=df_open,
                    admin=is_admin(),
                    db_exec=db_exec,
                    now_berlin=now_berlin,
                    norm_vehicle=norm_vehicle,
                    row_allows_area=row_allows_area,
                    assign_area=assign_area,
                    refresh=content.refresh,
                    using_fallback_catalog=using_fallback_catalog,
                )

    content()
    def _auto_refresh_gleisplan() -> None:
        if is_admin():
            return
        refresh_when_no_dialog(content.refresh)

    create_page_timer(float(refresh_interval_seconds), _auto_refresh_gleisplan)
