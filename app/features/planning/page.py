from __future__ import annotations

from datetime import date, datetime, timedelta
import re
from typing import Any, Callable

from nicegui import ui
from wiring import service_facade as app_services

from .configuration_ui import render_planner_configuration_form
from .models import DEFAULT_CAPACITY_SLOTS
from .repository import (
    list_planning_allocations_for_range,
)
from .service import (
    allocate_order_to_capacity,
    allocate_orders_to_capacity_batch,
    clear_week_allocations,
    assign_order_to_slot,
    create_order_from_form,
    create_slot,
    get_order_board,
    get_planner_configuration,
    get_slot_board,
    get_week_board,
    replace_order_block_allocations,
    remove_allocation,
    remove_allocations,
    remove_order_allocations,
    remove_order,
    set_order_statuses,
    sync_order_schedule_from_allocations,
    save_planner_configuration,
    save_planner_ui_settings,
    save_capacity_from_form,
    upsert_order_from_form,
)


def _slot_ma_to_required_units(value: Any) -> float:
    return _safe_float(value) / 2.0


def _render_planning_breadcrumb(parts: list[tuple[str, Callable[[], None] | None]]) -> None:
    with ui.row().classes("cfg-breadcrumb"):
        for index, (label, action) in enumerate(parts):
            if index > 0:
                ui.label("-").classes("cfg-breadcrumb-separator")
            item = ui.label(label).classes("cfg-breadcrumb-current" if action is None else "cfg-breadcrumb-link")
            if action is not None:
                item.on("click", lambda _event=None, callback=action: callback())


def _admin_guard(
    render_nav_fn: Callable[[], None],
    is_admin_fn: Callable[[], bool],
    breadcrumb: list[tuple[str, Callable[[], None] | None]] | None = None,
) -> bool:
    render_nav_fn()
    if breadcrumb:
        _render_planning_breadcrumb(breadcrumb)
    if not is_admin_fn():
        ui.label("Diese Seite ist nur für Admins verfügbar.").classes("text-amber-3")
        return False
    return True


def _week_start(day_value: date) -> date:
    return day_value - timedelta(days=day_value.weekday())


def _weekday_name_de(day_value: date) -> str:
    return ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"][day_value.weekday()]


def _weekday_labels_de() -> list[str]:
    return ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


def _safe_float(value: Any) -> float:
    try:
        if isinstance(value, str):
            cleaned = value.strip().replace(",", ".")
            return float(cleaned or 0)
        return float(value or 0)
    except Exception:
        return 0.0


def _vehicle_option_sort_key(value: Any) -> tuple[Any, ...]:
    text = str(value or "").strip()
    numbers = tuple(int(part) for part in re.findall(r"\d+", text))
    return (numbers, text.casefold())


def _configured_vehicle_group_options() -> tuple[list[str], set[str], set[str]]:
    try:
        mappings = app_services.list_vehicle_series_mappings()
        series_order = app_services.list_series()
    except Exception:
        mappings = []
        series_order = []

    grouped: dict[str, set[str]] = {}
    for row in mappings:
        vehicle = str(row.get("vehicle_number") or "").strip()
        series = str(row.get("baureihe") or "").strip() or "Ohne Baureihe"
        if not vehicle:
            continue
        grouped.setdefault(series, set()).add(vehicle)

    ordered_series = [series for series in series_order if series in grouped]
    ordered_series.extend(sorted((series for series in grouped if series not in set(ordered_series)), key=str.casefold))

    options: list[str] = []
    headers: set[str] = set()
    vehicles: set[str] = set()
    for series in ordered_series:
        header = f"- {series} -"
        headers.add(header)
        options.append(header)
        for vehicle in sorted(grouped.get(series, set()), key=_vehicle_option_sort_key):
            options.append(vehicle)
            vehicles.add(vehicle)

    if not options:
        empty_header = "Keine Fahrzeugnummern in der Konfiguration"
        options.append(empty_header)
        headers.add(empty_header)
    return options, headers, vehicles


class _VehicleDropdownValue:
    def __init__(self, value: str | None = None) -> None:
        self.value = value


def _render_configured_vehicle_select(label: str, selected_vehicle: Any = "") -> tuple[Any, set[str]]:
    options, headers, vehicles = _configured_vehicle_group_options()
    selected_text = str(selected_vehicle or "").strip()
    value = selected_text if selected_text in vehicles else None
    state = _VehicleDropdownValue(value)

    with ui.column().classes("w-full gap-1 planning-vehicle-dropdown"):
        ui.label(label).classes("planning-vehicle-dropdown-label")
        dropdown_button = ui.button(value or "Fahrzeug auswählen", icon="directions_railway").props(
            "no-caps align=between"
        ).classes("w-full planning-vehicle-dropdown-btn")

        def choose_vehicle(vehicle: str) -> None:
            state.value = vehicle
            dropdown_button.set_text(vehicle)

        with dropdown_button:
            with ui.menu().props("max-height=420px").classes("planning-vehicle-menu") as menu:
                for option in options:
                    if option in headers:
                        ui.label(option.strip("- ")).classes("planning-vehicle-menu-header")
                    else:
                        ui.menu_item(
                            option,
                            on_click=lambda _=None, vehicle=option: (choose_vehicle(vehicle), menu.close()),
                        ).classes("planning-vehicle-menu-item")

        if not vehicles:
            dropdown_button.disable()
            ui.label("Keine Fahrzeugnummern in der Konfiguration hinterlegt.").classes("planning-note text-amber-3")
        elif selected_text and selected_text not in vehicles:
            ui.label(
                f"Das bisherige Fahrzeug {selected_text} ist nicht in der Konfiguration hinterlegt."
            ).classes("planning-note text-amber-3")

    return state, vehicles


def _setting_enabled(settings: dict[str, Any], key: str, default: bool = True) -> bool:
    value = settings.get(key)
    if value is None:
        return default
    return str(value).strip().lower() not in {"0", "false", "nein", "no", "off", ""}


def _setting_float(settings: dict[str, Any], key: str, default: float) -> float:
    value = settings.get(key)
    if value is None:
        return default
    parsed = _safe_float(value)
    return parsed if parsed >= 0 else default


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


def _normalize_role_key(value: Any) -> str:
    raw = str(value or "").strip().lower()
    cleaned = re.sub(r"[^a-z0-9]+", "_", raw)
    return cleaned.strip("_")


def _build_slot_rows_from_shifts(shift_rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    slot_rows: list[dict[str, str]] = []
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
            label = f"{_format_minutes_as_hhmm(current)} - {_format_minutes_as_hhmm(next_value)}"
            if label not in seen:
                seen.add(label)
                slot_rows.append(
                    {
                        "slot_label": label,
                        "start_time": _format_minutes_as_hhmm(current),
                        "end_time": _format_minutes_as_hhmm(next_value),
                    }
                )
            current = next_value
    return slot_rows


def _slot_sort_key(slot_date_iso: str, slot_label: str) -> tuple[str, int, str]:
    try:
        index = DEFAULT_CAPACITY_SLOTS.index(str(slot_label or ""))
    except ValueError:
        index = 999
    return (str(slot_date_iso or ""), index, str(slot_label or ""))


def _append_multiline_entry(base_value: Any, entry: Any) -> str:
    base = str(base_value or "").strip()
    item = str(entry or "").strip()
    if not item:
        return base
    if not base:
        return item
    lines = [line.strip() for line in base.splitlines() if line.strip()]
    if item in lines:
        return "\n".join(lines)
    lines.append(item)
    return "\n".join(lines)


def _parse_multiline_entries(value: Any) -> list[str]:
    return [line.strip() for line in str(value or "").splitlines() if line.strip()]


def _order_status_label(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"entwurf", "draft", "in_erstellung", "erstellung", ""}:
        return "In Erstellung"
    if raw in {"in_planung", "planung", "in planung"}:
        return "In Planung"
    if raw in {"freigegeben", "released"}:
        return "Freigegeben"
    if raw in {"erledigt"}:
        return "Erledigt"
    if raw in {"storniert"}:
        return "Storniert"
    if raw == "partial":
        return "Teilweise"
    if raw == "overplanned":
        return "Zu viel geplant"
    if raw == "planned":
        return "Eingeplant"
    if raw == "conflict":
        return "Konflikt"
    if raw == "done":
        return "Voll eingeplant"
    return "Offen"


def _order_status_class(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"entwurf", "draft", "in_erstellung", "erstellung", ""}:
        return "is-open"
    if raw in {"in_planung", "planung", "in planung"}:
        return "is-partial"
    if raw in {"freigegeben", "released"}:
        return "is-planned"
    if raw in {"erledigt"}:
        return "is-done"
    if raw in {"storniert"}:
        return "is-conflict"
    if raw == "partial":
        return "is-partial"
    if raw == "overplanned":
        return "is-overplanned"
    if raw == "planned":
        return "is-planned"
    if raw == "conflict":
        return "is-conflict"
    if raw == "done":
        return "is-done"
    return "is-open"


def _planning_source_label(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw == "open_tasks_manual":
        return "Manuelle Anlage"
    if raw == "upload_legacy":
        return "Legacy-Upload"
    return "Planner"


def register_planning_pages(
    render_nav_fn: Callable[[], None],
    is_admin_fn: Callable[[], bool],
    is_configuration_user_fn: Callable[[], bool] | None = None,
) -> None:
    ui.add_head_html(
        """
        <style>
          .planning-page,
          .planning-page * {
            color: #f3f4f6;
          }
          .planning-page .q-field__native,
          .planning-page .q-field__input,
          .planning-page .q-field__label,
          .planning-page .q-field__marginal,
          .planning-page .q-field__prepend,
          .planning-page .q-field__append {
            color: #ffffff !important;
          }
          .planning-page .q-field__control:before,
          .planning-page .q-field__control:after {
            border-color: rgba(255,255,255,.92) !important;
          }
          .planning-grid-2 {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 14px;
            width: 100%;
          }
          .planning-card {
            width: 100%;
            min-width: 0;
          }
          .planning-page-title-btn {
            padding: 0;
            margin: 0;
            min-height: auto;
            justify-content: flex-start;
            color: #f8fafc !important;
            opacity: 1 !important;
          }
          .planning-page-title-btn .q-btn__content {
            justify-content: flex-start;
          }
          .planning-page-title-btn .q-btn__content span {
            color: #f8fafc !important;
          }
          .planning-section-title {
            font-size: 1.15rem;
            font-weight: 900;
            color: #f3f4f6;
          }
          .planning-note {
            font-size: .9rem;
            color: rgba(243,244,246,.88);
          }
          .planning-vehicle-dropdown-label {
            font-size: .82rem;
            font-weight: 900;
            color: rgba(243,244,246,.9);
          }
          .planning-vehicle-dropdown-btn {
            min-height: 52px;
            justify-content: space-between;
            border: 1px solid rgba(255,255,255,.92) !important;
            border-radius: 4px !important;
            background: #242432 !important;
            box-shadow: none !important;
          }
          .planning-vehicle-dropdown-btn .q-btn__content {
            width: 100%;
            justify-content: space-between;
          }
          .planning-vehicle-menu {
            width: min(440px, calc(100vw - 32px));
            max-height: 420px;
            overflow-y: auto;
            background: #111827;
            border: 1px solid rgba(148,163,184,.28);
            border-radius: 10px;
          }
          .planning-vehicle-menu-header {
            padding: 10px 14px 7px 14px;
            color: #bfdbfe !important;
            font-weight: 950;
            background: #0f172a;
            border-top: 1px solid rgba(148,163,184,.22);
            border-bottom: 1px solid rgba(148,163,184,.12);
            cursor: default;
          }
          .planning-vehicle-menu-item {
            min-height: 38px;
            color: #f8fafc !important;
            font-weight: 800;
          }
          .planning-table-card .q-table td,
          .planning-table-card .q-table th {
            font-size: .92rem;
          }
          .planning-week-toolbar {
            align-items: center;
          }
          .planning-week-label {
            font-size: 1.1rem;
            font-weight: 900;
            color: #f3f4f6;
          }
          .planning-week-layout {
            display: grid;
            grid-template-columns: minmax(280px, 340px) minmax(0, 1fr);
            gap: 14px;
            width: 100%;
          }
          .planning-orders-panel {
            position: sticky;
            top: 10px;
            align-self: start;
            max-height: calc(100vh - 128px);
            overflow-y: auto;
            overscroll-behavior: contain;
            scrollbar-gutter: stable;
          }
          .planning-week-board {
            min-width: 0;
          }
          .planning-day-grid {
            display: flex;
            flex-direction: column;
            gap: 10px;
            width: 100%;
          }
          .planning-day-column {
            display: flex;
            flex-direction: column;
            gap: 8px;
            min-width: 0;
          }
          .planning-day-card {
            background: rgba(255,255,255,.03);
            border: 1px solid rgba(255,255,255,.07);
            border-radius: 14px;
            padding: 10px;
            min-width: 0;
          }
          .planning-day-card.planning-day-today {
            border-color: rgba(255,217,102,.9);
            box-shadow: inset 0 0 0 1px rgba(255,217,102,.32);
          }
          .planning-day-name {
            font-size: .92rem;
            font-weight: 900;
            line-height: 1.1;
          }
          .planning-day-date {
            font-size: .78rem;
            color: rgba(243,244,246,.84);
            margin-bottom: 6px;
          }
          .planning-day-summary {
            font-size: .76rem;
            font-weight: 700;
            color: rgba(243,244,246,.9);
            margin-bottom: 8px;
          }
          .planning-day-summary.is-overbooked {
            color: #fca5a5;
          }
          .planning-day-matrix {
            display: grid;
            gap: 6px;
            width: 100%;
            min-width: 0;
            align-items: stretch;
          }
          .planning-range-help {
            border: 1px solid rgba(255,255,255,.10);
            background: rgba(255,255,255,.04);
            border-radius: 12px;
            padding: 10px;
            margin-bottom: 10px;
          }
          .planning-range-help.is-active {
            border-color: rgba(96,165,250,.55);
            background: rgba(59,130,246,.12);
          }
          .planning-matrix-head {
            font-size: .72rem;
            font-weight: 900;
            color: rgba(243,244,246,.9);
            padding: 6px 4px;
            text-align: center;
          }
          .planning-matrix-corner {
            text-align: left;
            color: rgba(243,244,246,.68);
          }
          .planning-slot-label {
            font-size: .72rem;
            font-weight: 900;
            line-height: 1.15;
            padding: 8px 6px;
            border-radius: 10px;
            background: rgba(255,255,255,.04);
            border: 1px solid rgba(255,255,255,.07);
          }
          .planning-slot-mode-row {
            display: grid;
            grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
            align-items: center;
            column-gap: 4px;
            width: 100%;
          }
          .planning-slot-mode-text {
            font-size: .58rem;
            font-weight: 800;
            line-height: 1;
            letter-spacing: .01em;
            color: rgba(243,244,246,.72);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
          }
          .planning-slot-mode-text.is-active {
            color: #f9fafb;
          }
          .planning-slot-mode-text.is-left {
            text-align: left;
          }
          .planning-slot-mode-text.is-right {
            text-align: right;
          }
          .planning-slot-mode-row .q-toggle {
            transform: scale(.76);
            transform-origin: center;
            margin: 0 -6px;
          }
          .planning-slot-capacity {
            font-size: .72rem;
            color: rgba(243,244,246,.82);
          }
          .planning-slot-capacity.is-balanced {
            color: #86efac;
          }
          .planning-slot-capacity.is-overbooked {
            color: #fca5a5;
          }
          .planning-slot-capacity.is-missing {
            color: #facc15;
          }
          .planning-place-chip {
            width: 100%;
            border-radius: 10px;
            padding: 10px 8px;
            border: 1px solid rgba(148,163,184,.24);
            background: linear-gradient(180deg, #1f2937 0%, #111827 100%);
            color: #f8fafc;
            cursor: pointer;
            line-height: 1.15;
            min-height: 86px;
            transition: transform .08s ease, border-color .12s ease, box-shadow .12s ease, background .12s ease;
            box-shadow: inset 0 0 0 1px rgba(255,255,255,.14);
            display: flex;
            flex-direction: column;
            justify-content: center;
            gap: 4px;
            text-align: left;
            user-select: none;
          }
          .planning-place-chip.is-busy {
            background: linear-gradient(180deg, #346cbb 0%, #214b84 100%);
            color: #ffffff;
            border-color: rgba(191,219,254,.92);
            box-shadow: inset 0 0 0 1px rgba(219,234,254,.34), 0 0 0 1px rgba(30,64,175,.22);
          }
          .planning-place-chip.is-frozen {
            background: linear-gradient(180deg, #4b5563 0%, #1f2937 100%);
            border-color: rgba(209,213,219,.72);
            box-shadow: inset 0 0 0 1px rgba(255,255,255,.16), 0 0 0 1px rgba(75,85,99,.28);
          }
          .planning-place-chip.is-balanced {
            background: linear-gradient(180deg, #2f6f49 0%, #25563a 100%);
            color: #ffffff;
          }
          .planning-place-chip.is-overbooked {
            background: linear-gradient(180deg, #a13333 0%, #7f1d1d 100%);
            color: #ffffff;
          }
          .planning-place-chip.is-frozen,
          .planning-place-chip.is-frozen.is-balanced,
          .planning-place-chip.is-frozen.is-overbooked {
            background: linear-gradient(180deg, #4b5563 0%, #1f2937 100%);
            border-color: rgba(209,213,219,.72);
            box-shadow: inset 0 0 0 1px rgba(255,255,255,.16), 0 0 0 1px rgba(75,85,99,.28);
          }
          .planning-place-chip.is-missing {
            background: linear-gradient(180deg, #312a12 0%, #221d0d 100%);
            color: #ffffff;
            border-color: rgba(250,204,21,.45);
          }
          .planning-place-chip.is-drop-target {
            outline: 2px dashed rgba(96,165,250,.95);
            outline-offset: 2px;
            transform: scale(1.01);
          }
          .planning-place-chip.is-range-start {
            outline: 2px solid rgba(96,165,250,.95);
            outline-offset: 1px;
          }
          .planning-place-chip.is-range-preview {
            box-shadow: inset 0 0 0 999px rgba(96,165,250,.22);
          }
          .planning-place-chip.is-ecm3-window {
            border-color: rgba(134,239,172,.85);
            box-shadow: inset 0 0 0 1px rgba(134,239,172,.35);
          }
          .planning-place-chip.is-gewerke-window {
            border-color: rgba(56,189,248,.95);
            box-shadow: inset 0 0 0 1px rgba(56,189,248,.50), 0 0 0 1px rgba(56,189,248,.24);
          }
          .planning-place-chip.is-outside-ecm3 {
            border-color: rgba(248,113,113,.40);
          }
          .planning-place-chip.is-range-preview.is-ecm3-window,
          .planning-place-chip.is-range-preview.is-gewerke-window {
            box-shadow: inset 0 0 0 999px rgba(96,165,250,.22), inset 0 0 0 2px rgba(56,189,248,.46);
          }
          .planning-place-chip:hover {
            transform: translateY(-1px);
            border-color: rgba(255,255,255,.45);
            box-shadow: inset 0 0 0 1px rgba(255,255,255,.18), 0 6px 18px rgba(0,0,0,.18);
          }
          .planning-place-name {
            display: block;
            font-size: .78rem;
            font-weight: 900;
            opacity: .78;
            margin-bottom: 2px;
          }
          .planning-place-status {
            display: block;
            font-size: .72rem;
            font-weight: 900;
            letter-spacing: .03em;
            text-transform: uppercase;
            opacity: .9;
            margin-bottom: 4px;
          }
          .planning-place-main {
            display: block;
            font-size: 1.02rem;
            font-weight: 900;
            line-height: 1.1;
          }
          .planning-place-sub {
            display: block;
            font-size: .86rem;
            font-weight: 700;
            opacity: .9;
            line-height: 1.15;
          }
          .planning-place-ma-controls {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 4px;
            margin-top: 6px;
          }
          .planning-place-ma-value {
            min-width: 34px;
            text-align: center;
            font-size: .86rem;
            font-weight: 900;
            color: inherit;
          }
          .planning-place-ma-input {
            width: 68px;
          }
          .planning-place-ma-input .q-field__control {
            min-height: 28px !important;
            height: 28px !important;
          }
          .planning-place-ma-input .q-field__native,
          .planning-place-ma-input input {
            text-align: center;
            font-size: .82rem;
            font-weight: 900;
          }
          .planning-place-ma-btn {
            min-width: 22px;
            min-height: 22px;
            border-radius: 999px;
            border: 1px solid rgba(255,255,255,.18);
            background: rgba(255,255,255,.10);
            color: inherit;
            font-size: .78rem;
            font-weight: 900;
            line-height: 1;
            cursor: pointer;
          }
          .planning-place-ma-open {
            margin-top: 6px;
            align-self: flex-start;
            border-radius: 999px;
            border: 1px solid rgba(255,255,255,.18);
            background: rgba(255,255,255,.10);
            color: inherit;
            font-size: .74rem;
            font-weight: 900;
            padding: 4px 8px;
            cursor: pointer;
          }
          .planning-order-item {
            border: 1px solid rgba(255,255,255,.07);
            border-radius: 12px;
            padding: 10px;
            background: rgba(255,255,255,.03);
            margin-bottom: 8px;
            cursor: pointer;
          }
          .planning-order-item.is-partial {
            border-color: rgba(250,204,21,.42);
            background: rgba(250,204,21,.08);
          }
          .planning-order-item.is-active {
            border-color: rgba(96,165,250,.72);
            box-shadow: inset 0 0 0 1px rgba(96,165,250,.45);
            background: rgba(59,130,246,.12);
          }
          .planning-order-item.is-done {
            border-color: rgba(134,239,172,.42);
            background: rgba(34,197,94,.10);
          }
          .planning-order-item.is-overplanned {
            border-color: rgba(248,113,113,.52);
            background: rgba(248,113,113,.12);
          }
          .planning-order-item.has-open-gewerke {
            border-color: rgba(250,204,21,.70);
            box-shadow: inset 0 0 0 1px rgba(250,204,21,.35);
          }
          .planning-gewerke-status {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            width: fit-content;
            margin-top: 5px;
            padding: 3px 8px;
            border-radius: 999px;
            border: 1px solid rgba(134,239,172,.32);
            color: rgba(220,252,231,.95);
            background: rgba(34,197,94,.10);
            font-size: .72rem;
            font-weight: 900;
          }
          .planning-gewerke-status.is-open {
            border-color: rgba(250,204,21,.62);
            color: rgba(254,249,195,.96);
            background: rgba(250,204,21,.12);
          }
          .planning-order-main {
            font-size: .88rem;
            font-weight: 900;
            color: #f3f4f6;
          }
          .planning-order-sub {
            font-size: .76rem;
            color: rgba(243,244,246,.86);
          }
          .planning-order-progress {
            width: 100%;
            height: 8px;
            border-radius: 999px;
            background: rgba(255,255,255,.10);
            overflow: hidden;
            margin: 7px 0 5px;
          }
          .planning-order-progress-bar {
            height: 100%;
            background: #93c47d;
          }
          .planning-active-order {
            border: 1px solid rgba(96,165,250,.45);
            background: rgba(59,130,246,.10);
            border-radius: 12px;
            padding: 10px;
            margin-bottom: 10px;
          }
          .planning-form-list {
            display: flex;
            flex-direction: column;
            gap: 10px;
            width: 100%;
          }
          .planning-form-item {
            border: 1px solid rgba(255,255,255,.10);
            border-radius: 14px;
            padding: 12px;
            background: rgba(255,255,255,.04);
          }
          .planning-form-item.is-clickable {
            cursor: pointer;
            transition: transform .12s ease, border-color .12s ease, background .12s ease;
          }
          .planning-form-item.is-clickable:hover {
            transform: translateY(-1px);
            border-color: rgba(96,165,250,.45);
            background: rgba(59,130,246,.08);
          }
          .planning-form-item.is-selected {
            border-color: rgba(96,165,250,.75);
            background: rgba(59,130,246,.14);
            box-shadow: inset 0 0 0 1px rgba(96,165,250,.28);
          }
          .planning-form-item-head {
            display: flex;
            justify-content: space-between;
            gap: 10px;
            align-items: baseline;
            margin-bottom: 6px;
          }
          .planning-form-item-main {
            font-size: 1rem;
            font-weight: 900;
            line-height: 1.15;
            color: #f3f4f6;
          }
          .planning-form-item-status {
            font-size: .72rem;
            font-weight: 900;
            text-transform: uppercase;
            letter-spacing: .03em;
            color: #e2e8f0;
            padding: 4px 8px;
            border-radius: 999px;
            background: rgba(148,163,184,.18);
            border: 1px solid rgba(148,163,184,.34);
            white-space: nowrap;
          }
          .planning-form-item-status.is-open {
            background: rgba(148,163,184,.16);
            border-color: rgba(148,163,184,.34);
          }
          .planning-form-item-status.is-partial {
            background: rgba(250,204,21,.16);
            border-color: rgba(250,204,21,.38);
            color: #fef3c7;
          }
          .planning-form-item-status.is-planned {
            background: rgba(74,222,128,.16);
            border-color: rgba(74,222,128,.38);
            color: #dcfce7;
          }
          .planning-form-item-status.is-conflict {
            background: rgba(248,113,113,.16);
            border-color: rgba(248,113,113,.38);
            color: #fecaca;
          }
          .planning-form-item-status.is-done {
            background: rgba(96,165,250,.16);
            border-color: rgba(96,165,250,.38);
            color: #dbeafe;
          }
          .planning-form-item-status.is-overplanned {
            background: rgba(248,113,113,.18);
            border-color: rgba(248,113,113,.42);
            color: #fecaca;
          }
          .planning-form-item-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 8px 14px;
            width: 100%;
          }
          .planning-form-item-row {
            display: flex;
            flex-direction: column;
            gap: 2px;
            min-width: 0;
          }
          .planning-form-item-label {
            font-size: .72rem;
            font-weight: 800;
            color: rgba(243,244,246,.72);
            text-transform: uppercase;
            letter-spacing: .03em;
          }
          .planning-form-item-value {
            font-size: .92rem;
            font-weight: 700;
            color: #f8fafc;
            overflow-wrap: anywhere;
          }
          .planning-form-empty {
            font-size: .95rem;
            color: rgba(243,244,246,.82);
          }
          .planning-entry-list {
            display: flex;
            flex-direction: column;
            gap: 8px;
            width: 100%;
            margin-top: 8px;
          }
          .planning-entry-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 10px;
            border: 1px solid rgba(255,255,255,.10);
            border-radius: 12px;
            background: rgba(255,255,255,.05);
            padding: 8px 10px;
          }
          .planning-entry-text {
            font-size: .92rem;
            font-weight: 700;
            color: #f8fafc;
            overflow-wrap: anywhere;
          }
          .planning-entry-empty {
            font-size: .85rem;
            color: rgba(243,244,246,.72);
          }
          .planning-hub-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 18px;
            width: 100%;
            margin-top: 18px;
          }
          .planning-hub-tile {
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            min-height: 190px;
            padding: 20px;
            border-radius: 18px;
            border: 1px solid rgba(148,163,184,.22);
            background: linear-gradient(180deg, rgba(30,41,59,.95) 0%, rgba(15,23,42,.98) 100%);
            box-shadow: 0 18px 40px rgba(0,0,0,.22);
            cursor: pointer;
            transition: transform .15s ease, border-color .15s ease, box-shadow .15s ease;
          }
          .planning-hub-tile:hover {
            transform: translateY(-2px);
            border-color: rgba(96,165,250,.5);
            box-shadow: 0 24px 50px rgba(0,0,0,.28);
          }
          .planning-hub-eyebrow {
            font-size: .82rem;
            font-weight: 800;
            letter-spacing: .04em;
            text-transform: uppercase;
            color: rgba(191,219,254,.9);
          }
          .planning-hub-title {
            font-size: 1.45rem;
            font-weight: 900;
            line-height: 1.1;
            color: #f8fafc;
          }
          .planning-hub-text {
            font-size: .98rem;
            line-height: 1.45;
            color: rgba(226,232,240,.88);
          }
          .planning-hub-actions {
            display: flex;
            justify-content: flex-end;
            width: 100%;
            margin-top: 8px;
          }
          .planning-hub-stats {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 10px;
            width: 100%;
            margin-top: 16px;
          }
          .planning-hub-stat {
            border: 1px solid rgba(148,163,184,.18);
            border-radius: 12px;
            background: rgba(255,255,255,.035);
            padding: 12px;
          }
          .planning-hub-stat.is-warning {
            border-color: rgba(248,113,113,.45);
            background: rgba(248,113,113,.10);
          }
          .planning-hub-stat-label {
            font-size: .78rem;
            font-weight: 800;
            text-transform: uppercase;
            color: rgba(226,232,240,.72);
          }
          .planning-hub-stat-value {
            font-size: 1.7rem;
            font-weight: 900;
            line-height: 1.1;
            color: #f8fafc;
          }
          .planning-hub-stat-sub {
            font-size: .78rem;
            color: rgba(226,232,240,.78);
          }
          .planning-setup-card {
            max-width: 760px;
            margin: 40px auto 0 auto;
            text-align: center;
          }
          .planning-config-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 14px;
            width: 100%;
          }
          .planning-config-panel {
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 14px;
            background: rgba(255,255,255,.03);
            padding: 12px;
          }
          .planning-config-panel-title {
            font-size: .95rem;
            font-weight: 900;
            margin-bottom: 8px;
          }
          @media (max-width: 1350px) {
            .planning-grid-2 {
              grid-template-columns: minmax(0, 1fr);
            }
            .planning-week-layout {
              grid-template-columns: minmax(0, 1fr);
            }
            .planning-orders-panel {
              position: static;
              max-height: none;
              overflow-y: visible;
            }
            .planning-form-item-grid {
              grid-template-columns: minmax(0, 1fr);
            }
            .planning-config-grid {
              grid-template-columns: minmax(0, 1fr);
            }
            .planning-hub-grid {
              grid-template-columns: minmax(0, 1fr);
            }
            .planning-hub-stats {
              grid-template-columns: minmax(0, 1fr);
            }
          }
        </style>
        """,
        shared=True,
    )

    def _open_planner_config_dialog(on_saved: Callable[[], None] | None = None) -> None:
        config = get_planner_configuration()
        place_entries = [str(row.get("code") or "") for row in config.get("places", [])]
        role_entries = [
            {
                "role_key": str(row.get("role_key") or ""),
                "label": str(row.get("label") or ""),
                "active": bool(row.get("active")),
            }
            for row in config.get("capacity_roles", [])
        ]
        shift_entries = [
            {
                "shift_name": str(row.get("shift_name") or ""),
                "start_time": str(row.get("start_time") or ""),
                "end_time": str(row.get("end_time") or ""),
                "slot_count": int(row.get("slot_count") or 1),
            }
            for row in config.get("shift_templates", [])
        ]
        staffing_map = {
            (
                str(row.get("shift_name") or ""),
                int(row.get("weekday") or 0),
                str(row.get("role_key") or ""),
            ): _safe_float(row.get("capacity"))
            for row in config.get("shift_staffing", [])
        }
        ui_settings = config.get("ui_settings", {})
        with ui.dialog() as dialog, ui.card().classes("w-[620px] max-w-full upload-panel planning-page"):
            ui.label("Planner-Konfiguration").classes("planning-section-title")
            ui.label(
                "Hier könnt ihr die Arbeitsplätze, Schichten und die Regelbesetzung für diese Werkstatt festlegen."
            ).classes("planning-note")
            with ui.element("div").classes("planning-config-grid"):
                with ui.element("div").classes("planning-config-panel"):
                    ui.label("Arbeitsplätze / Gleise").classes("planning-config-panel-title")
                    with ui.row().classes("w-full gap-2 items-end wrap"):
                        add_place = ui.input("Arbeitsplatz hinzufügen").props("outlined").classes("grow min-w-[220px]")

                        def _add_place() -> None:
                            value = str(add_place.value or "").strip()
                            if not value:
                                return
                            if value not in place_entries:
                                place_entries.append(value)
                            add_place.value = ""
                            render_place_list.refresh()

                        ui.button("Hinzufügen", on_click=_add_place).classes("btn-big")

                    @ui.refreshable
                    def render_place_list() -> None:
                        if not place_entries:
                            ui.label("Noch keine Arbeitsplätze hinterlegt.").classes("planning-entry-empty")
                            return
                        with ui.element("div").classes("planning-entry-list"):
                            for index, entry in enumerate(list(place_entries)):
                                with ui.element("div").classes("planning-entry-item"):
                                    ui.label(entry).classes("planning-entry-text")
                                    ui.button(
                                        "X",
                                        on_click=lambda _=None, idx=index: (
                                            place_entries.pop(idx),
                                            render_place_list.refresh(),
                                        ),
                                    ).props("dense flat color=negative").classes("min-w-0")

                    render_place_list()

                with ui.element("div").classes("planning-config-panel"):
                    ui.label("Mitarbeiterbereiche").classes("planning-config-panel-title")
                    with ui.row().classes("w-full gap-2 items-end wrap"):
                        add_role_label = ui.input("Bereich hinzufügen").props("outlined").classes("grow min-w-[220px]")

                        def _add_role() -> None:
                            label = str(add_role_label.value or "").strip()
                            role_key = _normalize_role_key(label)
                            if not label or not role_key:
                                return
                            if any(str(role.get("role_key") or "") == role_key for role in role_entries):
                                ui.notify("Dieser Mitarbeiterbereich ist bereits vorhanden.", type="warning")
                                return
                            role_entries.append({"role_key": role_key, "label": label, "active": True})
                            add_role_label.value = ""
                            render_role_list.refresh()
                            render_staffing_editor.refresh()

                        ui.button("Hinzufügen", on_click=_add_role).classes("btn-big")

                    @ui.refreshable
                    def render_role_list() -> None:
                        if not role_entries:
                            ui.label("Noch keine Mitarbeiterbereiche hinterlegt.").classes("planning-entry-empty")
                            return
                        with ui.element("div").classes("planning-entry-list"):
                            for index, role in enumerate(list(role_entries)):
                                with ui.element("div").classes("planning-entry-item"):
                                    active_checkbox = ui.checkbox(value=bool(role.get("active"))).props("dense")
                                    label_input = ui.input(value=str(role.get("label") or "")).props("outlined dense").classes("grow")
                                    ui.label(str(role.get("role_key") or "")).classes("planning-note")

                                    def _save_role_state(
                                        _e=None,
                                        current_role=role,
                                        active_ctrl=active_checkbox,
                                        label_ctrl=label_input,
                                    ) -> None:
                                        current_role["active"] = bool(active_ctrl.value)
                                        current_role["label"] = str(label_ctrl.value or "").strip() or str(current_role.get("role_key") or "")
                                        render_staffing_editor.refresh()

                                    active_checkbox.on_value_change(_save_role_state)
                                    label_input.on_value_change(_save_role_state)
                                    ui.button(
                                        "X",
                                        on_click=lambda _=None, idx=index: (
                                            role_entries.pop(idx),
                                            render_role_list.refresh(),
                                            render_staffing_editor.refresh(),
                                        ),
                                    ).props("dense flat color=negative").classes("min-w-0")

                    render_role_list()

                with ui.element("div").classes("planning-config-panel"):
                    ui.label("Schichten").classes("planning-config-panel-title")
                    with ui.row().classes("w-full gap-2 items-end wrap"):
                        add_shift_name = ui.input("Name").props("outlined").classes("grow min-w-[120px]")
                        add_shift_start = ui.input("Start").props("type=time outlined").classes("grow min-w-[120px]")
                        add_shift_end = ui.input("Ende").props("type=time outlined").classes("grow min-w-[120px]")
                        add_shift_split = ui.number("Slots", value=1, format="%.0f").props("outlined min=1 step=1").classes("w-[90px]")

                        def _add_shift() -> None:
                            shift_name = str(add_shift_name.value or "").strip()
                            start_time = str(add_shift_start.value or "").strip()
                            end_time = str(add_shift_end.value or "").strip()
                            slot_count = max(1, int(_safe_float(add_shift_split.value) or 1))
                            if not shift_name or not start_time or not end_time:
                                return
                            if not any(str(item.get("shift_name") or "") == shift_name for item in shift_entries):
                                shift_entries.append(
                                    {
                                        "shift_name": shift_name,
                                        "start_time": start_time,
                                        "end_time": end_time,
                                        "slot_count": slot_count,
                                    }
                                )
                            add_shift_name.value = ""
                            add_shift_start.value = ""
                            add_shift_end.value = ""
                            add_shift_split.value = 1
                            render_shift_list.refresh()
                            render_staffing_editor.refresh()
                            render_slot_preview.refresh()

                        ui.button("Hinzufügen", on_click=_add_shift).classes("btn-big")

                    @ui.refreshable
                    def render_shift_list() -> None:
                        if not shift_entries:
                            ui.label("Noch keine Schichten hinterlegt.").classes("planning-entry-empty")
                            return
                        with ui.element("div").classes("planning-entry-list"):
                            for index, entry in enumerate(list(shift_entries)):
                                with ui.element("div").classes("planning-entry-item"):
                                    ui.label(
                                        f'{entry.get("shift_name") or "-"} | {entry.get("start_time") or "--:--"} - {entry.get("end_time") or "--:--"} | {entry.get("slot_count") or 1} Slots'
                                    ).classes("planning-entry-text")
                                    ui.button(
                                        "X",
                                        on_click=lambda _=None, idx=index: (
                                            shift_entries.pop(idx),
                                            render_shift_list.refresh(),
                                            render_staffing_editor.refresh(),
                                            render_slot_preview.refresh(),
                                        ),
                                    ).props("dense flat color=negative").classes("min-w-0")

                    render_shift_list()

                with ui.element("div").classes("planning-config-panel"):
                    ui.label("Regelbesetzung je Wochentag").classes("planning-config-panel-title")

                    @ui.refreshable
                    def render_staffing_editor() -> None:
                        if not shift_entries:
                            ui.label("Zuerst bitte mindestens eine Schicht anlegen.").classes("planning-entry-empty")
                            return
                        for weekday, weekday_label in enumerate(_weekday_labels_de()):
                            ui.label(weekday_label).classes("planning-note")
                            for shift in shift_entries:
                                shift_name = str(shift.get("shift_name") or "")
                                with ui.row().classes("w-full gap-2 items-end wrap mb-2"):
                                    ui.label(shift_name).classes("planning-entry-text")
                                    active_roles = [row for row in role_entries if bool(row.get("active"))]
                                    role_inputs: dict[str, Any] = {}
                                    for role in active_roles:
                                        role_key = str(role.get("role_key") or "")
                                        role_label = str(role.get("label") or role_key)
                                        role_input = ui.number(
                                            role_label,
                                            value=_safe_float(staffing_map.get((shift_name, weekday, role_key), 0.0)),
                                            format="%.1f",
                                        ).props("outlined").classes("w-[110px]")
                                        role_inputs[role_key] = role_input

                                    def _save_staffing(
                                        _e=None,
                                        current_shift_name=shift_name,
                                        current_weekday=weekday,
                                        current_inputs=role_inputs,
                                    ) -> None:
                                        for role_key, ctrl in current_inputs.items():
                                            staffing_map[(current_shift_name, current_weekday, role_key)] = _safe_float(ctrl.value)

                                    for ctrl in role_inputs.values():
                                        ctrl.on_value_change(_save_staffing)

                    render_staffing_editor()

                with ui.element("div").classes("planning-config-panel"):
                    ui.label("Abgeleitete Zeitslots").classes("planning-config-panel-title")

                    @ui.refreshable
                    def render_slot_preview() -> None:
                        slot_rows = _build_slot_rows_from_shifts(shift_entries)
                        if not slot_rows:
                            ui.label("Noch keine Zeitslots ableitbar.").classes("planning-entry-empty")
                            return
                        with ui.element("div").classes("planning-entry-list"):
                            for row in slot_rows:
                                with ui.element("div").classes("planning-entry-item"):
                                    ui.label(
                                        f'{row.get("start_time") or "--:--"} - {row.get("end_time") or "--:--"}'
                                    ).classes("planning-entry-text")

                    render_slot_preview()

                with ui.element("div").classes("planning-config-panel"):
                    ui.label("Startseite").classes("planning-config-panel-title")
                    show_open_orders = ui.checkbox(
                        "Offene Aufträge anzeigen",
                        value=_setting_enabled(ui_settings, "home_show_open_orders", True),
                    )
                    show_partial_orders = ui.checkbox(
                        "Teilweise eingeplant anzeigen",
                        value=_setting_enabled(ui_settings, "home_show_partial_orders", True),
                    )
                    show_done_orders = ui.checkbox(
                        "Voll eingeplant anzeigen",
                        value=_setting_enabled(ui_settings, "home_show_done_orders", True),
                    )
                    overplanned_threshold = ui.number(
                        "Zu viel MA ab",
                        value=_setting_float(ui_settings, "overplanned_threshold", 0.5),
                        format="%.1f",
                    ).props("outlined min=0 step=0.5").classes("w-full")

            def _save_config() -> None:
                places = [item.strip() for item in place_entries if str(item).strip()]
                shift_rows = [item for item in shift_entries if str(item.get("shift_name") or "").strip()]
                slots = _build_slot_rows_from_shifts(shift_rows)
                staffing_rows = []
                active_role_keys = {str(role.get("role_key") or "") for role in role_entries}
                for (shift_name, weekday, role_key), capacity_value in staffing_map.items():
                    if not any(str(item.get("shift_name") or "") == shift_name for item in shift_rows):
                        continue
                    if role_key not in active_role_keys:
                        continue
                    staffing_rows.append(
                        {
                            "shift_name": shift_name,
                            "weekday": weekday,
                            "role_key": role_key,
                            "capacity": _safe_float(capacity_value),
                        }
                    )
                if not places or not slots:
                    ui.notify("Bitte mindestens einen Arbeitsplatz und eine Schicht hinterlegen.", type="warning")
                    return
                save_planner_configuration(
                    place_codes=places,
                    slot_rows=slots,
                    shift_rows=shift_rows,
                    staffing_rows=staffing_rows,
                    capacity_roles=role_entries,
                )
                save_planner_ui_settings(
                    {
                        "home_show_open_orders": bool(show_open_orders.value),
                        "home_show_partial_orders": bool(show_partial_orders.value),
                        "home_show_done_orders": bool(show_done_orders.value),
                        "overplanned_threshold": _safe_float(overplanned_threshold.value),
                    }
                )
                dialog.close()
                ui.notify("Planner-Konfiguration gespeichert.", type="positive")
                if on_saved:
                    on_saved()

            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Abbrechen", on_click=dialog.close).classes("btn-big")
                ui.button("Speichern", on_click=_save_config).classes("btn-big")
        dialog.open()

    def _open_planner_config_dialog(on_saved: Callable[[], None] | None = None) -> None:
        with ui.dialog() as dialog, ui.card().classes("w-[620px] max-w-full upload-panel planning-page"):
            def _saved() -> None:
                dialog.close()
                if on_saved:
                    on_saved()

            render_planner_configuration_form(
                on_saved=_saved,
                on_cancel=dialog.close,
                cancel_label="Abbrechen",
            )
        dialog.open()

    @ui.page("/konfiguration/planung")
    def page_configuration_planning() -> None:
        render_nav_fn()
        allowed_fn = is_configuration_user_fn or is_admin_fn
        if not allowed_fn():
            ui.label("Konfiguration").classes("page-title")
            ui.label("Diese Seite ist nur für Konfigurationsbenutzer verfügbar.").classes("text-amber-3")
            return
        _render_planning_breadcrumb([("Konfiguration", lambda: ui.navigate.to("/konfiguration")), ("Planung", None)])
        with ui.card().classes("w-full upload-panel planning-page"):
            render_planner_configuration_form(
                on_cancel=lambda: ui.navigate.to("/konfiguration"),
                cancel_label="Zurück",
            )

    @ui.page("/planung")
    def page_planning_home() -> None:
        if not _admin_guard(render_nav_fn, is_admin_fn):
            return
        config = get_planner_configuration()
        ui_settings = config.get("ui_settings", {})
        order_board = get_order_board()
        order_rows = order_board.get("orders", [])
        open_count = sum(1 for row in order_rows if str(row.get("progress_state") or "") == "open")
        partial_count = sum(1 for row in order_rows if str(row.get("progress_state") or "") == "partial")
        done_count = sum(1 for row in order_rows if str(row.get("progress_state") or "") in {"done", "overplanned"})
        ui.label("Willkommen in der Planungsebene").classes("planning-note")
        def _open_planner_config_dialog_from_home() -> None:
            _open_planner_config_dialog(
                on_saved=lambda: ui.run_javascript("window.location.reload()"),
            )

        with ui.element("div").classes("planning-hub-actions"):
            ui.button("Optionen", on_click=_open_planner_config_dialog_from_home).classes("btn-big")
        visible_stats = []
        if _setting_enabled(ui_settings, "home_show_open_orders", True):
            visible_stats.append(("Offen", open_count, "noch nicht eingeplant", False))
        if _setting_enabled(ui_settings, "home_show_partial_orders", True):
            visible_stats.append(("Teilweise", partial_count, "bereits begonnen", False))
        if _setting_enabled(ui_settings, "home_show_done_orders", True):
            visible_stats.append(("Voll eingeplant", done_count, "voll eingeplant", False))
        if visible_stats:
            with ui.element("div").classes("planning-hub-stats"):
                for label, value, sub_text, warning in visible_stats:
                    stat_classes = "planning-hub-stat"
                    if warning:
                        stat_classes += " is-warning"
                    with ui.element("div").classes(stat_classes):
                        ui.label(label).classes("planning-hub-stat-label")
                        ui.label(str(value)).classes("planning-hub-stat-value")
                        ui.label(sub_text).classes("planning-hub-stat-sub")
        with ui.element("div").classes("planning-hub-grid"):
            with ui.element("div").classes("planning-hub-tile").on("click", lambda: ui.navigate.to("/planung/operativ")):
                ui.label("Planung").classes("planning-hub-eyebrow")
                ui.label("Operative Planung").classes("planning-hub-title")
                ui.label(
                    "Hier plant ihr Fahrzeuge auf Arbeitsgleise, verteilt Mitarbeiter und steuert die laufende Woche."
                ).classes("planning-hub-text")
            with ui.element("div").classes("planning-hub-tile").on("click", lambda: ui.navigate.to("/planung/formular")):
                ui.label("Planung").classes("planning-hub-eyebrow")
                ui.label("Auftragsplanung").classes("planning-hub-title")
                ui.label(
                    "Hier legt ihr Planungsaufträge an, pflegt Zusatzarbeiten und bearbeitet bestehende Aufträge."
                ).classes("planning-hub-text")

    @ui.page("/planung/operativ")
    def page_planning_week() -> None:
        if not _admin_guard(
            render_nav_fn,
            is_admin_fn,
            [("Planung", lambda: ui.navigate.to("/planung")), ("Operative Planung", None)],
        ):
            return
        today = date.today()
        state: dict[str, Any] = {
            "week_start": _week_start(today).isoformat(),
            "active_order_id": None,
            "range_start": None,
            "edit_block": None,
            "history_order_id": None,
            "board_cache": None,
            "board_cache_week_start": None,
            "planner_config_cache": None,
            "suppress_week_input_refresh": False,
        }

        with ui.row().classes("w-full gap-3 wrap planning-week-toolbar"):
            week_input = ui.input("Wochenstart", value=state["week_start"]).props("type=date outlined").classes(
                "w-full max-w-[220px] prio-day-input"
            )
            week_label = ui.label("").classes("planning-week-label")

            def _open_planner_config_dialog() -> None:
                config = get_planner_configuration()
                place_entries = [str(row.get("code") or "") for row in config.get("places", [])]
                role_entries = [
                    {
                        "role_key": str(row.get("role_key") or ""),
                        "label": str(row.get("label") or ""),
                        "active": bool(row.get("active")),
                    }
                    for row in config.get("capacity_roles", [])
                ]
                shift_entries = [
                    {
                        "shift_name": str(row.get("shift_name") or ""),
                        "start_time": str(row.get("start_time") or ""),
                        "end_time": str(row.get("end_time") or ""),
                        "slot_count": int(row.get("slot_count") or 1),
                    }
                    for row in config.get("shift_templates", [])
                ]
                staffing_map = {
                    (
                        str(row.get("shift_name") or ""),
                        int(row.get("weekday") or 0),
                        str(row.get("role_key") or ""),
                    ): _safe_float(row.get("capacity"))
                    for row in config.get("shift_staffing", [])
                }
                ui_settings = config.get("ui_settings", {})
                with ui.dialog() as dialog, ui.card().classes("w-[620px] max-w-full upload-panel planning-page"):
                    ui.label("Planner-Konfiguration").classes("planning-section-title")
                    ui.label(
                        "Hier könnt ihr die Arbeitsplätze, Schichten und die Regelbesetzung für diese Werkstatt festlegen."
                    ).classes("planning-note")
                    with ui.element("div").classes("planning-config-grid"):
                        with ui.element("div").classes("planning-config-panel"):
                            ui.label("Arbeitsplätze / Gleise").classes("planning-config-panel-title")
                            with ui.row().classes("w-full gap-2 items-end wrap"):
                                add_place = ui.input("Arbeitsplatz hinzufügen").props("outlined").classes("grow min-w-[220px]")

                                def _add_place() -> None:
                                    value = str(add_place.value or "").strip()
                                    if not value:
                                        return
                                    if value not in place_entries:
                                        place_entries.append(value)
                                    add_place.value = ""
                                    render_place_list.refresh()

                                ui.button("Hinzufügen", on_click=_add_place).classes("btn-big")

                            @ui.refreshable
                            def render_place_list() -> None:
                                if not place_entries:
                                    ui.label("Noch keine Arbeitsplätze hinterlegt.").classes("planning-entry-empty")
                                    return
                                with ui.element("div").classes("planning-entry-list"):
                                    for index, entry in enumerate(list(place_entries)):
                                        with ui.element("div").classes("planning-entry-item"):
                                            ui.label(entry).classes("planning-entry-text")
                                            ui.button(
                                                "X",
                                                on_click=lambda _=None, idx=index: (
                                                    place_entries.pop(idx),
                                                    render_place_list.refresh(),
                                                ),
                                            ).props("dense flat color=negative").classes("min-w-0")

                            render_place_list()

                        with ui.element("div").classes("planning-config-panel"):
                            ui.label("Mitarbeiterbereiche").classes("planning-config-panel-title")
                            with ui.row().classes("w-full gap-2 items-end wrap"):
                                add_role_label = ui.input("Bereich hinzufügen").props("outlined").classes("grow min-w-[220px]")

                                def _add_role() -> None:
                                    label = str(add_role_label.value or "").strip()
                                    role_key = _normalize_role_key(label)
                                    if not label or not role_key:
                                        return
                                    if any(str(role.get("role_key") or "") == role_key for role in role_entries):
                                        ui.notify("Dieser Mitarbeiterbereich ist bereits vorhanden.", type="warning")
                                        return
                                    role_entries.append(
                                        {
                                            "role_key": role_key,
                                            "label": label,
                                            "active": True,
                                        }
                                    )
                                    add_role_label.value = ""
                                    render_role_list.refresh()
                                    render_staffing_editor.refresh()

                                ui.button("Hinzufügen", on_click=_add_role).classes("btn-big")

                            @ui.refreshable
                            def render_role_list() -> None:
                                if not role_entries:
                                    ui.label("Noch keine Mitarbeiterbereiche hinterlegt.").classes("planning-entry-empty")
                                    return
                                with ui.element("div").classes("planning-entry-list"):
                                    for index, role in enumerate(list(role_entries)):
                                        with ui.element("div").classes("planning-entry-item"):
                                            active_checkbox = ui.checkbox(value=bool(role.get("active"))).props("dense")
                                            label_input = ui.input(
                                                value=str(role.get("label") or "")
                                            ).props("outlined dense").classes("grow")
                                            ui.label(str(role.get("role_key") or "")).classes("planning-note")

                                            def _save_role_state(
                                                _e=None,
                                                current_role=role,
                                                active_ctrl=active_checkbox,
                                                label_ctrl=label_input,
                                            ) -> None:
                                                current_role["active"] = bool(active_ctrl.value)
                                                current_role["label"] = str(label_ctrl.value or "").strip() or str(current_role.get("role_key") or "")
                                                render_staffing_editor.refresh()

                                            active_checkbox.on_value_change(_save_role_state)
                                            label_input.on_value_change(_save_role_state)
                                            ui.button(
                                                "X",
                                                on_click=lambda _=None, idx=index: (
                                                    role_entries.pop(idx),
                                                    render_role_list.refresh(),
                                                    render_staffing_editor.refresh(),
                                                ),
                                            ).props("dense flat color=negative").classes("min-w-0")

                            render_role_list()

                        with ui.element("div").classes("planning-config-panel"):
                            ui.label("Schichten").classes("planning-config-panel-title")
                            with ui.row().classes("w-full gap-2 items-end wrap"):
                                add_shift_name = ui.input("Name").props("outlined").classes("grow min-w-[120px]")
                                add_shift_start = ui.input("Start").props("type=time outlined").classes("grow min-w-[120px]")
                                add_shift_end = ui.input("Ende").props("type=time outlined").classes("grow min-w-[120px]")
                                add_shift_split = ui.number("Slots", value=1, format="%.0f").props("outlined min=1 step=1").classes("w-[90px]")

                                def _add_shift() -> None:
                                    shift_name = str(add_shift_name.value or "").strip()
                                    start_time = str(add_shift_start.value or "").strip()
                                    end_time = str(add_shift_end.value or "").strip()
                                    slot_count = max(1, int(_safe_float(add_shift_split.value) or 1))
                                    if not shift_name or not start_time or not end_time:
                                        return
                                    if not any(str(item.get("shift_name") or "") == shift_name for item in shift_entries):
                                        shift_entries.append(
                                            {
                                                "shift_name": shift_name,
                                                "start_time": start_time,
                                                "end_time": end_time,
                                                "slot_count": slot_count,
                                            }
                                        )
                                    add_shift_name.value = ""
                                    add_shift_start.value = ""
                                    add_shift_end.value = ""
                                    add_shift_split.value = 1
                                    render_shift_list.refresh()
                                    render_staffing_editor.refresh()
                                    render_slot_preview.refresh()

                                ui.button("Hinzufügen", on_click=_add_shift).classes("btn-big")

                            @ui.refreshable
                            def render_shift_list() -> None:
                                if not shift_entries:
                                    ui.label("Noch keine Schichten hinterlegt.").classes("planning-entry-empty")
                                    return
                                with ui.element("div").classes("planning-entry-list"):
                                    for index, entry in enumerate(list(shift_entries)):
                                        with ui.element("div").classes("planning-entry-item"):
                                            ui.label(
                                                f'{entry.get("shift_name") or "-"} | {entry.get("start_time") or "--:--"} - {entry.get("end_time") or "--:--"} | {entry.get("slot_count") or 1} Slots'
                                            ).classes("planning-entry-text")
                                            ui.button(
                                                "X",
                                                on_click=lambda _=None, idx=index: (
                                                    shift_entries.pop(idx),
                                                    render_shift_list.refresh(),
                                                    render_staffing_editor.refresh(),
                                                    render_slot_preview.refresh(),
                                                ),
                                            ).props("dense flat color=negative").classes("min-w-0")

                            render_shift_list()

                        with ui.element("div").classes("planning-config-panel"):
                            ui.label("Regelbesetzung je Wochentag").classes("planning-config-panel-title")

                            @ui.refreshable
                            def render_staffing_editor() -> None:
                                if not shift_entries:
                                    ui.label("Zuerst bitte mindestens eine Schicht anlegen.").classes("planning-entry-empty")
                                    return
                                for weekday, weekday_label in enumerate(_weekday_labels_de()):
                                    ui.label(weekday_label).classes("planning-note")
                                    for shift in shift_entries:
                                        shift_name = str(shift.get("shift_name") or "")
                                        with ui.row().classes("w-full gap-2 items-end wrap mb-2"):
                                            ui.label(shift_name).classes("planning-entry-text")
                                            active_roles = [row for row in role_entries if bool(row.get("active"))]
                                            role_inputs: dict[str, Any] = {}
                                            for role in active_roles:
                                                role_key = str(role.get("role_key") or "")
                                                role_label = str(role.get("label") or role_key)
                                                role_input = ui.number(
                                                    role_label,
                                                    value=_safe_float(staffing_map.get((shift_name, weekday, role_key), 0.0)),
                                                    format="%.1f",
                                                ).props("outlined").classes("w-[110px]")
                                                role_inputs[role_key] = role_input

                                            def _save_staffing(
                                                _e=None,
                                                current_shift_name=shift_name,
                                                current_weekday=weekday,
                                                current_inputs=role_inputs,
                                            ) -> None:
                                                for role_key, ctrl in current_inputs.items():
                                                    staffing_map[(current_shift_name, current_weekday, role_key)] = _safe_float(ctrl.value)

                                            for ctrl in role_inputs.values():
                                                ctrl.on_value_change(_save_staffing)

                            render_staffing_editor()

                        with ui.element("div").classes("planning-config-panel"):
                            ui.label("Abgeleitete Zeitslots").classes("planning-config-panel-title")

                            @ui.refreshable
                            def render_slot_preview() -> None:
                                slot_rows = _build_slot_rows_from_shifts(shift_entries)
                                if not slot_rows:
                                    ui.label("Noch keine Zeitslots ableitbar.").classes("planning-entry-empty")
                                    return
                                with ui.element("div").classes("planning-entry-list"):
                                    for row in slot_rows:
                                        with ui.element("div").classes("planning-entry-item"):
                                            ui.label(
                                                f'{row.get("start_time") or "--:--"} - {row.get("end_time") or "--:--"}'
                                            ).classes("planning-entry-text")

                            render_slot_preview()

                        with ui.element("div").classes("planning-config-panel"):
                            ui.label("Startseite").classes("planning-config-panel-title")
                            show_open_orders = ui.checkbox(
                                "Offene Aufträge anzeigen",
                                value=_setting_enabled(ui_settings, "home_show_open_orders", True),
                            )
                            show_partial_orders = ui.checkbox(
                                "Teilweise eingeplant anzeigen",
                                value=_setting_enabled(ui_settings, "home_show_partial_orders", True),
                            )
                            show_done_orders = ui.checkbox(
                                "Voll eingeplant anzeigen",
                                value=_setting_enabled(ui_settings, "home_show_done_orders", True),
                            )
                            overplanned_threshold = ui.number(
                                "Zu viel MA ab",
                                value=_setting_float(ui_settings, "overplanned_threshold", 0.5),
                                format="%.1f",
                            ).props("outlined min=0 step=0.5").classes("w-full")

                    def _save_config() -> None:
                        places = [item.strip() for item in place_entries if str(item).strip()]
                        shift_rows = [item for item in shift_entries if str(item.get("shift_name") or "").strip()]
                        slots = _build_slot_rows_from_shifts(shift_rows)
                        staffing_rows = []
                        active_role_keys = {str(role.get("role_key") or "") for role in role_entries}
                        for (shift_name, weekday, role_key), capacity_value in staffing_map.items():
                            if not any(str(item.get("shift_name") or "") == shift_name for item in shift_rows):
                                continue
                            if role_key not in active_role_keys:
                                continue
                            staffing_rows.append(
                                {
                                    "shift_name": shift_name,
                                    "weekday": weekday,
                                    "role_key": role_key,
                                    "capacity": _safe_float(capacity_value),
                                }
                            )
                        if not places or not slots:
                            ui.notify("Bitte mindestens einen Arbeitsplatz und eine Schicht hinterlegen.", type="warning")
                            return
                        save_planner_configuration(
                            place_codes=places,
                            slot_rows=slots,
                            shift_rows=shift_rows,
                            staffing_rows=staffing_rows,
                            capacity_roles=role_entries,
                        )
                        save_planner_ui_settings(
                            {
                                "home_show_open_orders": bool(show_open_orders.value),
                                "home_show_partial_orders": bool(show_partial_orders.value),
                                "home_show_done_orders": bool(show_done_orders.value),
                                "overplanned_threshold": _safe_float(overplanned_threshold.value),
                            }
                        )
                        state["board_cache"] = None
                        state["board_cache_week_start"] = None
                        state["planner_config_cache"] = None
                        dialog.close()
                        ui.notify("Planner-Konfiguration gespeichert.", type="positive")
                        body.clear()
                        render_week.refresh()

                    with ui.row().classes("w-full justify-end gap-2"):
                        ui.button("Abbrechen", on_click=dialog.close).classes("btn-big")
                        ui.button("Speichern", on_click=_save_config).classes("btn-big")
                dialog.open()

            def _open_planner_config_dialog() -> None:
                with ui.dialog() as dialog, ui.card().classes("w-[620px] max-w-full upload-panel planning-page"):
                    def _saved() -> None:
                        state["board_cache"] = None
                        state["board_cache_week_start"] = None
                        state["planner_config_cache"] = None
                        dialog.close()
                        body.clear()
                        render_week.refresh()

                    render_planner_configuration_form(
                        on_saved=_saved,
                        on_cancel=dialog.close,
                        cancel_label="Abbrechen",
                    )
                dialog.open()

            def _invalidate_board_cache() -> None:
                state["board_cache"] = None
                state["board_cache_week_start"] = None

            def _get_planner_config_cached() -> dict[str, Any]:
                cached = state.get("planner_config_cache")
                if isinstance(cached, dict):
                    return cached
                config = get_planner_configuration()
                state["planner_config_cache"] = config
                return config

            def _set_current_week() -> None:
                state["week_start"] = _week_start(date.today()).isoformat()
                state["suppress_week_input_refresh"] = True
                week_input.value = state["week_start"]
                state["suppress_week_input_refresh"] = False
                render_week.refresh()

            def _step_week(delta_days: int) -> None:
                current = date.fromisoformat(str(week_input.value or state["week_start"]))
                new_start = (current + timedelta(days=delta_days)).isoformat()
                state["week_start"] = new_start
                state["suppress_week_input_refresh"] = True
                week_input.value = new_start
                state["suppress_week_input_refresh"] = False
                render_week.refresh()

            def _clear_current_week() -> None:
                current_week = _current_week_start()
                with ui.dialog() as dialog, ui.card().classes("w-[420px] max-w-full upload-panel planning-page"):
                    ui.label("Aktuelle Woche leeren").classes("planning-section-title")
                    ui.label(
                        f"Aktive Einplanungen von {current_week:%d.%m.%Y} bis {(current_week + timedelta(days=6)):%d.%m.%Y} werden gelöscht. Erledigte/eingefrorene Aufträge bleiben erhalten."
                    ).classes("planning-note")

                    def _confirm_clear() -> None:
                        result = clear_week_allocations(week_start_iso=current_week.isoformat())
                        state["active_order_id"] = None
                        state["range_start"] = None
                        state["edit_block"] = None
                        _invalidate_board_cache()
                        dialog.close()
                        deleted_count = int(result.get("deleted_allocations") or 0)
                        kept_frozen = int(result.get("kept_frozen_allocations") or 0)
                        if deleted_count > 0:
                            suffix = f" {kept_frozen} eingefrorene Einplanung(en) blieben erhalten." if kept_frozen else ""
                            ui.notify(f"{deleted_count} aktive Einplanungen der aktuellen Woche wurden gelöscht.{suffix}", type="positive")
                        elif kept_frozen:
                            ui.notify(f"Keine aktiven Einplanungen gelöscht. {kept_frozen} eingefrorene Einplanung(en) blieben erhalten.", type="info")
                        else:
                            ui.notify("In dieser Woche waren keine Einplanungen vorhanden.", type="info")
                        render_week.refresh()

                    with ui.row().classes("w-full justify-end gap-2"):
                        ui.button("Abbrechen", on_click=dialog.close).classes("btn-big")
                        ui.button("Woche leeren", on_click=_confirm_clear).props("color=negative").classes("btn-big")
                dialog.open()

            ui.button("Vorherige Woche", on_click=lambda: _step_week(-7)).classes("btn-big")
            ui.button("Diese Woche", on_click=_set_current_week).classes("btn-big")
            ui.button("Nächste Woche", on_click=lambda: _step_week(7)).classes("btn-big")
            ui.button("Woche leeren", on_click=_clear_current_week).props("color=negative").classes("btn-big")
            ui.button("Optionen", on_click=_open_planner_config_dialog).classes("btn-big")

        body = ui.column().classes("w-full gap-3 planning-page")

        def _current_week_start() -> date:
            raw_value = str(week_input.value or state["week_start"] or "").strip()
            try:
                picked_day = date.fromisoformat(raw_value)
            except ValueError:
                picked_day = _week_start(date.today())
            normalized = _week_start(picked_day)
            state["week_start"] = normalized.isoformat()
            if str(week_input.value or "") != state["week_start"]:
                state["suppress_week_input_refresh"] = True
                week_input.value = state["week_start"]
                state["suppress_week_input_refresh"] = False
            return normalized

        @ui.refreshable
        def render_week() -> None:
            body.clear()
            week_start = _current_week_start()
            week_end = week_start + timedelta(days=6)
            week_label.set_text(f"KW-Ansicht {week_start:%d.%m.%Y} - {week_end:%d.%m.%Y}")
            planner_config = _get_planner_config_cached()
            if planner_config.get("needs_setup"):
                with body:
                    with ui.card().classes("w-full upload-panel planning-card planning-page planning-setup-card"):
                        ui.label("Konfiguration starten").classes("planning-section-title")
                        ui.label(
                            "Bevor ihr mit der Planung startet, hinterlegt bitte zuerst die Arbeitsplätze und Zeitslots für diese Werkstatt."
                        ).classes("planning-note")
                        ui.button("Konfiguration starten", on_click=_open_planner_config_dialog).classes("btn-big")
                return
            overplanned_threshold = _setting_float(
                planner_config.get("ui_settings", {}),
                "overplanned_threshold",
                0.5,
            )
            board = state.get("board_cache")
            if state.get("board_cache_week_start") != week_start.isoformat() or not isinstance(board, dict):
                board = get_week_board(week_start.isoformat())
                state["board_cache"] = board
                state["board_cache_week_start"] = week_start.isoformat()
            orders = board.get("orders", [])
            open_orders = board.get("open_orders", [])
            completed_orders = board.get("completed_orders", [])
            places = board.get("places", [])
            week_dates = [date.fromisoformat(day_iso) for day_iso in board.get("week_dates", [])]
            day_summaries = board.get("day_summaries", {})
            capacity_rows = board.get("capacity_slots", [])
            allocation_rows = board.get("allocations", [])
            order_allocation_rows = board.get("order_allocations", allocation_rows)
            slot_templates = board.get("slot_templates", [])
            capacity_roles = board.get("capacity_roles", [])
            slot_role_capacities = board.get("slot_role_capacities", {})
            slot_template_map = {str(row.get("slot_label") or ""): row for row in slot_templates}

            capacity_map = {
                (str(row.get("slot_date") or ""), str(row.get("slot_label") or "")): row for row in capacity_rows
            }
            allocation_map = {
                (str(row.get("slot_date") or ""), str(row.get("slot_label") or ""), str(row.get("place_code") or "")): row
                for row in allocation_rows
            }
            allocations_by_slot: dict[tuple[str, str], list[dict[str, Any]]] = {}
            allocations_by_id: dict[int, dict[str, Any]] = {}
            allocations_by_order: dict[int, list[dict[str, Any]]] = {}
            allocated_by_slot: dict[tuple[str, str], float] = {}
            for row in allocation_rows:
                slot_key = (str(row.get("slot_date") or ""), str(row.get("slot_label") or ""))
                allocations_by_slot.setdefault(slot_key, []).append(row)
                allocation_id = int(row.get("id") or 0)
                if allocation_id > 0:
                    allocations_by_id[allocation_id] = row
                order_id = int(row.get("planning_order_id") or 0)
                if order_id > 0:
                    allocations_by_order.setdefault(order_id, []).append(row)
                allocated_by_slot[slot_key] = allocated_by_slot.get(slot_key, 0.0) + _safe_float(row.get("allocated_ma"))
            current_slot_order = {
                str(slot_label): index for index, slot_label in enumerate(board.get("slot_labels", []))
            }
            slot_day_offsets: dict[str, int] = {}
            previous_start_minutes: int | None = None
            current_day_offset = 0
            for slot_label in board.get("slot_labels", []):
                label_text = str(slot_label or "")
                slot_template = slot_template_map.get(label_text) or {}
                start_text = str(slot_template.get("start_time") or "").strip()
                if not start_text:
                    label_parts = label_text.replace("–", "-").split("-", 1)
                    if len(label_parts) == 2:
                        start_text = label_parts[0].strip()
                start_minutes = _parse_hhmm_to_minutes(start_text)
                if start_minutes is not None:
                    if previous_start_minutes is not None and start_minutes < previous_start_minutes:
                        current_day_offset += 1
                    previous_start_minutes = start_minutes
                slot_day_offsets[label_text] = current_day_offset

            def _current_slot_sort_key(slot_date_iso: str, slot_label: str) -> tuple[str, int, str]:
                return (
                    str(slot_date_iso or ""),
                    current_slot_order.get(str(slot_label or ""), 999),
                    str(slot_label or ""),
                )

            order_options = {"": "Bitte Auftrag wählen"}
            for order in open_orders:
                order_options[str(order["id"])] = (
                    f'{order["fahrzeug"]} | {order["friststufe"]} | Rest {order.get("remaining_total") or 0:.1f}'
                )

            def _open_capacity_dialog(slot_date_iso: str, slot_label: str) -> None:
                capacity_row = capacity_map.get((slot_date_iso, slot_label)) or {}
                with ui.dialog() as dialog, ui.card().classes("w-[420px] max-w-full upload-panel planning-page"):
                    ui.label("Kapazität pflegen").classes("planning-section-title")
                    ui.label(f"{slot_date_iso} | {slot_label}").classes("planning-note")
                    workshop_capacity = ui.number(
                        "Werkstatt-MA anwesend",
                        value=_safe_float(capacity_row.get("workshop_capacity")),
                        format="%.2f",
                    ).props("outlined").classes("w-full")
                    service_capacity = ui.number(
                        "Service-MA",
                        value=_safe_float(capacity_row.get("service_capacity")),
                        format="%.2f",
                    ).props("outlined").classes("w-full")
                    urd_capacity = ui.number(
                        "URD-MA",
                        value=_safe_float(capacity_row.get("urd_capacity")),
                        format="%.2f",
                    ).props("outlined").classes("w-full")
                    source_name = ui.input("Quelle", value=str(capacity_row.get("source_name") or "manuell")).props(
                        "outlined"
                    ).classes("w-full")
                    notes = ui.input("Hinweis", value=str(capacity_row.get("notes") or "")).props("outlined").classes("w-full")

                    def _save_capacity() -> None:
                        save_capacity_from_form(
                            slot_date=slot_date_iso,
                            slot_label=slot_label,
                            workshop_capacity=workshop_capacity.value,
                            service_capacity=service_capacity.value,
                            urd_capacity=urd_capacity.value,
                            source_name=str(source_name.value or ""),
                            notes=str(notes.value or ""),
                        )
                        _invalidate_board_cache()
                        dialog.close()
                        ui.notify("Kapazität gespeichert.", type="positive")
                        render_week.refresh()

                    with ui.row().classes("w-full justify-end gap-2"):
                        ui.button("Abbrechen", on_click=dialog.close).classes("btn-big")
                        ui.button("Speichern", on_click=_save_capacity).classes("btn-big")
                dialog.open()

            active_order = next(
                (row for row in orders if int(row.get("id") or 0) == int(state.get("active_order_id") or 0)),
                None,
            )
            range_start = state.get("range_start") if isinstance(state.get("range_start"), dict) else None
            edit_block = state.get("edit_block") if isinstance(state.get("edit_block"), dict) else None
            history_order = next(
                (row for row in orders if int(row.get("id") or 0) == int(state.get("history_order_id") or 0)),
                None,
            )
            active_order_window_cache: tuple[datetime, datetime] | None | bool = False
            active_order_gewerke_cache: list[datetime] | None = None
            slot_interval_cache: dict[tuple[str, str], tuple[datetime, datetime] | None] = {}
            order_gewerke_cache: dict[int, list[datetime]] = {}
            order_allocation_intervals_cache: dict[int, list[tuple[datetime, datetime]]] = {}
            order_gewerke_status_cache: dict[int, dict[str, Any]] = {}

            def _refresh_week_soon(delay: float = 0.05) -> None:
                ui.timer(delay, render_week.refresh, once=True)

            def _current_active_order() -> dict[str, Any] | None:
                active_id = int(state.get("active_order_id") or 0)
                if active_id <= 0:
                    return None
                return next((row for row in orders if int(row.get("id") or 0) == active_id), None)

            def _is_done_status(value: Any) -> bool:
                return str(value or "").strip().lower() in {"erledigt", "done"}

            def _parse_planning_datetime(day_value: Any, time_value: Any) -> datetime | None:
                day_text = str(day_value or "").strip()
                time_text = str(time_value or "").strip() or "00:00"
                if not day_text:
                    return None
                try:
                    return datetime.fromisoformat(f"{day_text}T{time_text[:5]}")
                except ValueError:
                    return None

            def _active_order_window() -> tuple[datetime, datetime] | None:
                nonlocal active_order_window_cache
                if active_order_window_cache is not False:
                    return active_order_window_cache
                if active_order is None:
                    active_order_window_cache = None
                    return None
                start_dt = _parse_planning_datetime(
                    active_order.get("ecm3_start_date"),
                    active_order.get("ecm3_start_time"),
                )
                end_dt = _parse_planning_datetime(
                    active_order.get("ecm3_end_date"),
                    active_order.get("ecm3_end_time"),
                )
                if not start_dt or not end_dt or end_dt <= start_dt:
                    active_order_window_cache = None
                    return None
                active_order_window_cache = (start_dt, end_dt)
                return start_dt, end_dt

            def _slot_times(slot_label: str) -> tuple[str, str] | None:
                slot_template = slot_template_map.get(str(slot_label or "")) or {}
                start_text = str(slot_template.get("start_time") or "").strip()
                end_text = str(slot_template.get("end_time") or "").strip()
                if not start_text or not end_text:
                    label_parts = str(slot_label or "").replace("–", "-").split("-", 1)
                    if len(label_parts) == 2:
                        start_text = label_parts[0].strip()
                        end_text = label_parts[1].strip()
                if not start_text or not end_text:
                    return None
                return start_text, end_text

            def _slot_interval(slot_date_iso: str, slot_label: str) -> tuple[datetime, datetime] | None:
                cache_key = (str(slot_date_iso or ""), str(slot_label or ""))
                if cache_key in slot_interval_cache:
                    return slot_interval_cache[cache_key]
                slot_times = _slot_times(slot_label)
                if not slot_times:
                    slot_interval_cache[cache_key] = None
                    return None
                start_text, end_text = slot_times
                day_offset = slot_day_offsets.get(str(slot_label or ""), 0)
                start_dt = _parse_planning_datetime(slot_date_iso, start_text)
                end_dt = _parse_planning_datetime(slot_date_iso, end_text)
                if not start_dt or not end_dt:
                    slot_interval_cache[cache_key] = None
                    return None
                if day_offset:
                    start_dt += timedelta(days=day_offset)
                    end_dt += timedelta(days=day_offset)
                if end_dt <= start_dt:
                    end_dt += timedelta(days=1)
                slot_interval_cache[cache_key] = (start_dt, end_dt)
                return start_dt, end_dt

            def _slot_within_active_window(slot_date_iso: str, slot_label: str) -> bool:
                order_window = _active_order_window()
                slot_window = _slot_interval(slot_date_iso, slot_label)
                if not order_window or not slot_window:
                    return False
                order_start, order_end = order_window
                slot_start, _ = slot_window
                return order_start <= slot_start < order_end

            def _slot_marks_active_gewerke(slot_date_iso: str, slot_label: str) -> bool:
                slot_window = _slot_interval(slot_date_iso, slot_label)
                if not slot_window:
                    return False
                slot_start, slot_end = slot_window
                return any(slot_start <= gewerk_dt < slot_end for gewerk_dt in _active_order_gewerke_datetimes())

            def _order_gewerke_datetimes(order: dict[str, Any] | None) -> list[datetime]:
                if order is None:
                    return []
                order_id = int(order.get("id") or 0)
                if order_id in order_gewerke_cache:
                    return order_gewerke_cache[order_id]
                values: list[datetime] = []
                for entry in _parse_multiline_entries(order.get("gewerke_info") or ""):
                    date_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", entry)
                    day_text = date_match.group(1) if date_match else ""
                    if not day_text:
                        german_date_match = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(\d{2,4})\b", entry)
                        if german_date_match:
                            day, month, year = german_date_match.groups()
                            year_value = int(year)
                            if year_value < 100:
                                year_value += 2000
                            day_text = f"{year_value:04d}-{int(month):02d}-{int(day):02d}"
                    time_match = re.search(r"\b(\d{1,2}:\d{2})\b", entry)
                    if not day_text or not time_match:
                        continue
                    parsed = _parse_planning_datetime(day_text, time_match.group(1))
                    if parsed:
                        values.append(parsed)
                order_gewerke_cache[order_id] = values
                return values

            def _active_order_has_gewerke() -> bool:
                return bool(_order_gewerke_datetimes(active_order))

            def _active_order_gewerke_datetimes() -> list[datetime]:
                nonlocal active_order_gewerke_cache
                if active_order_gewerke_cache is not None:
                    return active_order_gewerke_cache
                active_order_gewerke_cache = _order_gewerke_datetimes(active_order)
                return active_order_gewerke_cache

            def _order_allocation_intervals(order: dict[str, Any] | None) -> list[tuple[datetime, datetime]]:
                if order is None:
                    return []
                order_id = int(order.get("id") or 0)
                if order_id in order_allocation_intervals_cache:
                    return order_allocation_intervals_cache[order_id]
                intervals: list[tuple[datetime, datetime]] = []
                for row in order_allocation_rows:
                    if int(row.get("planning_order_id") or 0) != order_id:
                        continue
                    interval = _slot_interval(str(row.get("slot_date") or ""), str(row.get("slot_label") or ""))
                    if interval:
                        intervals.append(interval)
                order_allocation_intervals_cache[order_id] = intervals
                return intervals

            def _format_gewerk_datetime(value: datetime) -> str:
                return f"{_weekday_name_de(value.date())[:2]} {value:%d.%m. %H:%M}"

            def _order_gewerke_status(order: dict[str, Any] | None) -> dict[str, Any]:
                if order is None:
                    return {"total": 0, "covered": 0, "open": []}
                order_id = int(order.get("id") or 0)
                if order_id in order_gewerke_status_cache:
                    return order_gewerke_status_cache[order_id]
                gewerke = _order_gewerke_datetimes(order)
                intervals = _order_allocation_intervals(order)
                open_gewerke = [
                    gewerk_dt
                    for gewerk_dt in gewerke
                    if not any(start_dt <= gewerk_dt < end_dt for start_dt, end_dt in intervals)
                ]
                status = {
                    "total": len(gewerke),
                    "covered": max(0, len(gewerke) - len(open_gewerke)),
                    "open": open_gewerke,
                }
                order_gewerke_status_cache[order_id] = status
                return status

            def _gewerke_status_text(order: dict[str, Any] | None, *, detailed: bool = False) -> str:
                status = _order_gewerke_status(order)
                total = int(status.get("total") or 0)
                covered = int(status.get("covered") or 0)
                open_values = list(status.get("open") or [])
                if total <= 0:
                    return ""
                if open_values:
                    if detailed:
                        next_items = ", ".join(_format_gewerk_datetime(value) for value in open_values[:3])
                        more_text = f" +{len(open_values) - 3}" if len(open_values) > 3 else ""
                        return f"Gewerke offen: {len(open_values)} ({next_items}{more_text})"
                    return f"Gewerke offen: {len(open_values)} | {covered}/{total} abgedeckt"
                return f"Gewerke abgedeckt: {covered}/{total}"

            def _can_release_order(order: dict[str, Any] | None) -> bool:
                if order is None:
                    return False
                if str(order.get("status") or "").strip().lower() == "freigegeben":
                    return False
                if str(order.get("progress_state") or "").strip().lower() not in {"done", "overplanned"}:
                    return False
                return not bool(_order_gewerke_status(order).get("open"))

            def _release_order_from_slot_planner(order_id: int) -> None:
                changed = set_order_statuses([int(order_id)], status="freigegeben")
                if not changed:
                    ui.notify("Auftrag konnte nicht freigegeben werden.", type="warning")
                    return
                _invalidate_board_cache()
                ui.notify("Auftrag freigegeben und an Offene Aufträge übergeben.", type="positive")
                render_week.refresh()

            def _release_all_visible_completed_orders() -> None:
                releasable_ids = [
                    int(order.get("id") or 0)
                    for order in completed_orders
                    if int(order.get("id") or 0) > 0 and _can_release_order(order)
                ]
                if not releasable_ids:
                    ui.notify("Keine freigabefähigen voll eingeplanten Aufträge gefunden.", type="info")
                    return
                changed = set_order_statuses(releasable_ids, status="freigegeben")
                if not changed:
                    ui.notify("Aufträge konnten nicht freigegeben werden.", type="warning")
                    return
                _invalidate_board_cache()
                ui.notify(f"{len(changed)} Auftrag/Aufträge freigegeben und an Offene Aufträge übergeben.", type="positive")
                render_week.refresh()

            def _restore_history_order(order_id: int) -> None:
                order = next((row for row in orders if int(row.get("id") or 0) == int(order_id or 0)), None)
                if not order:
                    ui.notify("Historischer Auftrag wurde nicht gefunden.", type="warning")
                    return
                with ui.dialog() as dialog, ui.card().classes("w-[460px] max-w-full upload-panel planning-page"):
                    ui.label("Aus Historie holen?").classes("planning-section-title")
                    ui.label(
                        "Der Auftrag erscheint danach wieder unter Offene Aufträge und muss später erneut abgeschlossen werden."
                    ).classes("planning-note")
                    ui.label(f'{order.get("fahrzeug") or "-"} | {order.get("friststufe") or "-"}').classes("planning-order-main")

                    def _confirm_restore() -> None:
                        restored_from_archive = app_services.restore_recent_done_for_planning_order(int(order_id))
                        changed = set_order_statuses([int(order_id)], status="freigegeben")
                        if not changed:
                            ui.notify("Auftrag konnte nicht aus der Historie geholt werden.", type="warning")
                            return
                        state["history_order_id"] = None
                        _invalidate_board_cache()
                        dialog.close()
                        message = (
                            "Auftrag wurde aus dem Archiv zurückgeholt und wieder geöffnet."
                            if restored_from_archive
                            else "Auftrag wurde wieder geöffnet und an Offene Aufträge übergeben."
                        )
                        ui.notify(message, type="positive")
                        render_week.refresh()

                    with ui.row().classes("w-full justify-end gap-2"):
                        ui.button("Abbrechen", on_click=dialog.close).classes("btn-big")
                        ui.button("Aus Historie holen", on_click=_confirm_restore).props("color=warning").classes("btn-big")
                dialog.open()

            def _range_outside_active_window(slot_rows_to_check: list[dict[str, Any]]) -> bool:
                order_window = _active_order_window()
                if not order_window or not slot_rows_to_check:
                    return False
                order_start, order_end = order_window
                intervals = [
                    _slot_interval(str(row.get("slot_date") or ""), str(row.get("slot_label") or ""))
                    for row in slot_rows_to_check
                ]
                clean_intervals = [item for item in intervals if item is not None]
                if not clean_intervals:
                    return False
                planned_start = min(item[0] for item in clean_intervals)
                planned_end = max(item[1] for item in clean_intervals)
                return planned_start < order_start or planned_end > order_end

            def _range_slot_rows(place_code: str, start_marker: dict[str, Any], end_marker: dict[str, Any]) -> list[dict[str, Any]]:
                start_key = _current_slot_sort_key(str(start_marker.get("slot_date") or ""), str(start_marker.get("slot_label") or ""))
                end_key = _current_slot_sort_key(str(end_marker.get("slot_date") or ""), str(end_marker.get("slot_label") or ""))
                low_key, high_key = (start_key, end_key) if start_key <= end_key else (end_key, start_key)
                rows: list[dict[str, Any]] = []
                for row in capacity_rows:
                    row_key = _current_slot_sort_key(str(row.get("slot_date") or ""), str(row.get("slot_label") or ""))
                    if low_key <= row_key <= high_key:
                        rows.append(row)
                rows.sort(key=lambda row: _current_slot_sort_key(str(row.get("slot_date") or ""), str(row.get("slot_label") or "")))
                return rows

            def _contiguous_block(allocation: dict[str, Any]) -> list[dict[str, Any]]:
                place_code = str(allocation.get("place_code") or "")
                order_id = int(allocation.get("planning_order_id") or 0)
                target_key = _current_slot_sort_key(str(allocation.get("slot_date") or ""), str(allocation.get("slot_label") or ""))
                ordered_slots = sorted(
                    capacity_rows,
                    key=lambda row: _current_slot_sort_key(str(row.get("slot_date") or ""), str(row.get("slot_label") or "")),
                )
                keyed_slots = [
                    (
                        _current_slot_sort_key(str(row.get("slot_date") or ""), str(row.get("slot_label") or "")),
                        str(row.get("slot_date") or ""),
                        str(row.get("slot_label") or ""),
                    )
                    for row in ordered_slots
                ]
                try:
                    current_index = next(index for index, item in enumerate(keyed_slots) if item[0] == target_key)
                except StopIteration:
                    return [allocation]

                def _same_block_at(index: int) -> dict[str, Any] | None:
                    if index < 0 or index >= len(keyed_slots):
                        return None
                    _, slot_date_iso, slot_label = keyed_slots[index]
                    row = allocation_map.get((slot_date_iso, slot_label, place_code))
                    if not row:
                        return None
                    return row if int(row.get("planning_order_id") or 0) == order_id else None

                start_index = current_index
                while start_index - 1 >= 0 and _same_block_at(start_index - 1):
                    start_index -= 1
                end_index = current_index
                while end_index + 1 < len(keyed_slots) and _same_block_at(end_index + 1):
                    end_index += 1

                block_rows: list[dict[str, Any]] = []
                for index in range(start_index, end_index + 1):
                    row = _same_block_at(index)
                    if row:
                        block_rows.append(row)
                return block_rows or [allocation]

            def _preview_contains(slot_date_iso: str, slot_label: str, place_code: str) -> bool:
                if edit_block:
                    return str(edit_block.get("place_code") or "") == str(place_code)
                return bool(range_start and str(range_start.get("place_code") or "") == str(place_code))

            def _confirm_range_allocation(end_slot_date_iso: str, end_slot_label: str, place_code: str) -> None:
                active_order = _current_active_order()
                range_start = state.get("range_start") if isinstance(state.get("range_start"), dict) else None
                edit_block = state.get("edit_block") if isinstance(state.get("edit_block"), dict) else None
                if active_order is None:
                    ui.notify("Bitte zuerst links einen Auftrag auswählen.", type="warning")
                    return
                if not range_start and not edit_block:
                    return
                if range_start and str(range_start.get("place_code") or "") != str(place_code):
                    ui.notify("Start und Ende müssen auf demselben Arbeitsplatz liegen.", type="warning")
                    return
                end_marker = {"slot_date": end_slot_date_iso, "slot_label": end_slot_label, "place_code": place_code}
                start_marker = range_start
                if edit_block and int(edit_block.get("order_id") or 0) == int(active_order.get("id") or 0):
                    block_start = edit_block.get("block_start") if isinstance(edit_block.get("block_start"), dict) else None
                    block_end = edit_block.get("block_end") if isinstance(edit_block.get("block_end"), dict) else None
                    if not block_start or not block_end:
                        ui.notify("Blockgrenzen konnten nicht ermittelt werden.", type="warning")
                        return
                    if str(edit_block.get("place_code") or "") != str(place_code):
                        ui.notify("Start und Ende müssen auf demselben Arbeitsplatz liegen.", type="warning")
                        return
                    block_start_key = _current_slot_sort_key(
                        str(block_start.get("slot_date") or ""),
                        str(block_start.get("slot_label") or ""),
                    )
                    target_key = _current_slot_sort_key(end_slot_date_iso, end_slot_label)
                    if target_key < block_start_key:
                        start_marker = end_marker
                        end_marker = block_end
                    else:
                        start_marker = block_start
                if not start_marker:
                    return
                slot_rows = _range_slot_rows(place_code, start_marker, end_marker)
                if not slot_rows:
                    ui.notify("Im gewählten Bereich wurden keine Slots gefunden.", type="warning")
                    return
                if _range_outside_active_window(slot_rows):
                    warning_text = "Der gewählte Bereich liegt außerhalb des ECM3-Zeitfensters."
                    if _active_order_has_gewerke():
                        warning_text += " Für diesen Auftrag sind Gewerke hinterlegt."
                    ui.notify(warning_text, type="warning")
                conflict_rows = []
                slot_allocated_totals = {
                    (str(row.get("slot_date") or ""), str(row.get("slot_label") or "")): allocated_by_slot.get(
                        (str(row.get("slot_date") or ""), str(row.get("slot_label") or "")),
                        0.0,
                    )
                    for row in slot_rows
                }
                proposal: list[dict[str, Any]] = []
                same_vehicle_conflicts: list[str] = []
                active_order_id = int(active_order.get("id") or 0)
                active_fahrzeug = str(active_order.get("fahrzeug") or "").strip()
                for slot_row in slot_rows:
                    slot_date_iso = str(slot_row.get("slot_date") or "")
                    slot_label = str(slot_row.get("slot_label") or "")
                    existing = allocation_map.get((slot_date_iso, slot_label, place_code))
                    if existing and int(existing.get("planning_order_id") or 0) != int(active_order.get("id") or 0):
                        conflict_rows.append(f"{slot_date_iso} | {slot_label}")
                        continue
                    slot_allocations = allocations_by_slot.get((slot_date_iso, slot_label), [])
                    same_vehicle_elsewhere = next(
                        (
                            row
                            for row in slot_allocations
                            if str(row.get("place_code") or "") != str(place_code)
                            and (
                                int(row.get("planning_order_id") or 0) == active_order_id
                                or str(row.get("fahrzeug") or "").strip() == active_fahrzeug
                            )
                        ),
                        None,
                    )
                    if same_vehicle_elsewhere:
                        same_vehicle_conflicts.append(
                            f"{slot_date_iso} | {slot_label} bereits auf {same_vehicle_elsewhere.get('place_code') or '-'}"
                        )
                        continue
                    allocated_sum = slot_allocated_totals.get((slot_date_iso, slot_label), 0.0)
                    existing_same = _safe_float(existing.get("allocated_ma")) if existing else 0.0
                    slot_capacity = _safe_float(slot_row.get("workshop_capacity"))
                    effective_allocated = max(0.0, allocated_sum - existing_same)
                    proposal.append(
                        {
                            "slot_row": slot_row,
                            "existing": existing,
                            "existing_same": existing_same,
                            "slot_capacity": slot_capacity,
                            "effective_allocated": effective_allocated,
                        }
                    )
                if conflict_rows:
                    ui.notify(
                        "Der Bereich enthält bereits andere Belegungen: " + ", ".join(conflict_rows[:4]),
                        type="warning",
                    )
                    return
                if same_vehicle_conflicts:
                    ui.notify(
                        "Dieses Fahrzeug ist im Bereich bereits auf einem anderen Arbeitsgleis eingeplant: "
                        + ", ".join(same_vehicle_conflicts[:4]),
                        type="warning",
                    )
                    return
                start_label = f'{start_marker.get("slot_date")} | {start_marker.get("slot_label")}'
                end_label = f'{end_marker.get("slot_date")} | {end_marker.get("slot_label")}'
                is_editing_active_order = bool(
                    edit_block and int(edit_block.get("order_id") or 0) == int(active_order.get("id") or 0)
                )
                edit_allocation_ids: set[int] = set()
                edit_capacity_slot_ids: list[int] = []
                original_edit_rows: dict[tuple[str, str], dict[str, Any]] = {}
                if is_editing_active_order:
                    original_block_start = edit_block.get("block_start") if isinstance(edit_block.get("block_start"), dict) else None
                    original_block_end = edit_block.get("block_end") if isinstance(edit_block.get("block_end"), dict) else None
                    if original_block_start and original_block_end:
                        original_block_slots = _range_slot_rows(place_code, original_block_start, original_block_end)
                        edit_capacity_slot_ids = [int(row.get("id") or 0) for row in original_block_slots if int(row.get("id") or 0) > 0]
                        original_slot_keys = {
                            (str(row.get("slot_date") or ""), str(row.get("slot_label") or ""))
                            for row in original_block_slots
                        }
                        edit_allocation_ids = {
                            int(row.get("id") or 0)
                            for row in allocations_by_order.get(int(active_order.get("id") or 0), [])
                            if int(row.get("id") or 0) > 0
                            and str(row.get("place_code") or "") == str(place_code)
                            and (str(row.get("slot_date") or ""), str(row.get("slot_label") or "")) in original_slot_keys
                        }
                        original_edit_rows = {
                            (str(row.get("slot_date") or ""), str(row.get("slot_label") or "")): row
                            for allocation_id in edit_allocation_ids
                            for row in [allocations_by_id.get(int(allocation_id))]
                            if row
                        }
                    else:
                        edit_allocation_ids = {
                            int(value)
                            for value in (edit_block.get("allocation_ids") or [])
                            if int(value or 0) > 0
                        }
                affected_slot_keys = {
                    (str(row.get("slot_date") or ""), str(row.get("slot_label") or ""))
                    for row in slot_rows
                }
                new_slot_keys = set(affected_slot_keys)
                if is_editing_active_order:
                    affected_slot_keys.update(
                        {
                            (str(row.get("slot_date") or ""), str(row.get("slot_label") or ""))
                            for allocation_id in edit_allocation_ids
                            for row in [allocations_by_id.get(int(allocation_id))]
                            if row
                        }
                    )
                slot_existing_rows: dict[tuple[str, str], list[dict[str, Any]]] = {}
                for slot_key in slot_allocated_totals:
                    for row in allocations_by_slot.get(slot_key, []):
                        if int(row.get("id") or 0) in edit_allocation_ids:
                            continue
                        if (
                            is_editing_active_order
                            and int(row.get("planning_order_id") or 0) == int(active_order.get("id") or 0)
                            and str(row.get("place_code") or "") == str(place_code)
                        ):
                            continue
                        slot_existing_rows.setdefault(slot_key, []).append(row)
                batch_rows: list[dict[str, Any]] = []
                for item in proposal:
                    slot_row = item["slot_row"]
                    slot_date_iso = str(slot_row.get("slot_date") or "")
                    slot_label = str(slot_row.get("slot_label") or "")
                    slot_key = (slot_date_iso, slot_label)
                    existing_rows = list(slot_existing_rows.get(slot_key, []))
                    slot_capacity = _safe_float(slot_row.get("workshop_capacity"))
                    slot_mode = _slot_mode(slot_date_iso, slot_label)
                    preserved_row = original_edit_rows.get(slot_key)
                    if preserved_row and slot_mode == "manual":
                        for row_data in existing_rows:
                            batch_rows.append(
                                {
                                    "allocation_id": row_data.get("id"),
                                    "planning_order_id": int(row_data.get("planning_order_id") or 0),
                                    "capacity_slot_id": int(row_data.get("capacity_slot_id") or 0),
                                    "place_code": str(row_data.get("place_code") or ""),
                                    "fahrzeug": str(row_data.get("fahrzeug") or ""),
                                    "allocated_ma": _safe_float(row_data.get("allocated_ma")),
                                    "note": str(row_data.get("note") or ""),
                                }
                            )
                        batch_rows.append(
                            {
                                "allocation_id": None,
                                "planning_order_id": int(active_order.get("id") or 0),
                                "capacity_slot_id": int(slot_row.get("id") or 0),
                                "place_code": place_code,
                                "fahrzeug": str(active_order.get("fahrzeug") or ""),
                                "allocated_ma": _safe_float(preserved_row.get("allocated_ma")),
                                "note": f"Bereichsplanung {start_label} bis {end_label}",
                            }
                        )
                        continue
                    final_rows = existing_rows + [
                        {
                            "id": None,
                            "planning_order_id": int(active_order.get("id") or 0),
                            "capacity_slot_id": int(slot_row.get("id") or 0),
                            "place_code": place_code,
                            "fahrzeug": str(active_order.get("fahrzeug") or ""),
                            "note": f"Bereichsplanung {start_label} bis {end_label}",
                        }
                    ]
                    if slot_mode != "auto":
                        shares = [_safe_float(row.get("allocated_ma")) for row in existing_rows] + [0.0]
                    elif slot_capacity <= 0:
                        shares = [0.0 for _ in final_rows]
                    else:
                        vehicle_count = len(final_rows)
                        rounded_capacity = max(0, int(round(slot_capacity)))
                        base_share = rounded_capacity // vehicle_count if vehicle_count else 0
                        remainder = rounded_capacity % vehicle_count if vehicle_count else 0
                        shares = [float(base_share + (1 if index < remainder else 0)) for index in range(vehicle_count)]
                    for row_data, share in zip(final_rows, shares):
                        batch_rows.append(
                            {
                                "allocation_id": row_data.get("id"),
                                "planning_order_id": int(row_data.get("planning_order_id") or 0),
                                "capacity_slot_id": int(row_data.get("capacity_slot_id") or 0),
                                "place_code": str(row_data.get("place_code") or ""),
                                "fahrzeug": str(row_data.get("fahrzeug") or ""),
                                "allocated_ma": share,
                                "note": str(row_data.get("note") or ""),
                            }
                        )
                if is_editing_active_order:
                    replace_order_block_allocations(
                        planning_order_id=int(active_order.get("id") or 0),
                        place_code=place_code,
                        capacity_slot_ids=edit_capacity_slot_ids,
                        allocation_rows=batch_rows,
                    )
                    removed_slot_keys = affected_slot_keys - new_slot_keys
                    if removed_slot_keys:
                        _redistribute_slot_set(removed_slot_keys)
                else:
                    allocate_orders_to_capacity_batch(
                        batch_rows,
                        sync_schedule_order_ids=[int(active_order.get("id") or 0)],
                    )
                state["active_order_id"] = None
                state["range_start"] = None
                state["edit_block"] = None
                try:
                    target_week_start = _week_start(date.fromisoformat(str(end_marker.get("slot_date") or ""))).isoformat()
                    state["week_start"] = target_week_start
                    state["suppress_week_input_refresh"] = True
                    week_input.value = target_week_start
                    state["suppress_week_input_refresh"] = False
                except ValueError:
                    state["suppress_week_input_refresh"] = False
                _invalidate_board_cache()
                ui.notify("Fahrzeug im Bereich eingeplant. Mitarbeiter können jetzt direkt im Slot gesetzt werden.", type="positive")
                _refresh_week_soon()

            def _redistribute_slot_ma(day_iso: str, slot_label: str, *, force: bool = False) -> None:
                _redistribute_slot_set({(day_iso, slot_label)}, force=force)

            def _slot_mode(day_iso: str, slot_label: str) -> str:
                capacity_row = capacity_map.get((day_iso, slot_label)) or {}
                return str(capacity_row.get("allocation_mode") or "auto").strip().lower() or "auto"

            def _set_slot_mode(day_iso: str, slot_label: str, mode: str) -> None:
                capacity_row = capacity_map.get((day_iso, slot_label)) or {}
                save_capacity_from_form(
                    slot_date=day_iso,
                    slot_label=slot_label,
                    workshop_capacity=_safe_float(capacity_row.get("workshop_capacity")),
                    service_capacity=_safe_float(capacity_row.get("service_capacity")),
                    urd_capacity=_safe_float(capacity_row.get("urd_capacity")),
                    allocation_mode=str(mode or "auto").strip().lower() or "auto",
                    source_name=str(capacity_row.get("source_name") or ""),
                    notes=str(capacity_row.get("notes") or ""),
                )

            def _role_capacity_field(role_key: str) -> str | None:
                mapping = {
                    "workshop": "workshop_capacity",
                    "service": "service_capacity",
                    "urd": "urd_capacity",
                }
                return mapping.get(str(role_key or "").strip().lower())

            def _change_role_capacity(day_iso: str, slot_label: str, role_key: str, delta: float) -> None:
                field_name = _role_capacity_field(role_key)
                if not field_name:
                    ui.notify("Dieser Mitarbeiterbereich kann aktuell nicht direkt im Slot angepasst werden.", type="warning")
                    return
                capacity_row = capacity_map.get((day_iso, slot_label)) or {}
                workshop_capacity = _safe_float(capacity_row.get("workshop_capacity"))
                service_capacity = _safe_float(capacity_row.get("service_capacity"))
                urd_capacity = _safe_float(capacity_row.get("urd_capacity"))
                current_value = {
                    "workshop_capacity": workshop_capacity,
                    "service_capacity": service_capacity,
                    "urd_capacity": urd_capacity,
                }.get(field_name, 0.0)
                new_value = max(0.0, current_value + float(delta or 0.0))
                if field_name == "workshop_capacity":
                    workshop_capacity = new_value
                elif field_name == "service_capacity":
                    service_capacity = new_value
                elif field_name == "urd_capacity":
                    urd_capacity = new_value
                save_capacity_from_form(
                    slot_date=day_iso,
                    slot_label=slot_label,
                    workshop_capacity=workshop_capacity,
                    service_capacity=service_capacity,
                    urd_capacity=urd_capacity,
                    allocation_mode="manual",
                    source_name="manuell",
                    notes=str(capacity_row.get("notes") or ""),
                )
                _invalidate_board_cache()
                render_week.refresh()

            def _redistribute_slot_set(slot_keys: set[tuple[str, str]], *, force: bool = False) -> None:
                if not slot_keys:
                    return
                grouped_days: dict[str, set[str]] = {}
                for day_iso, slot_label in slot_keys:
                    grouped_days.setdefault(str(day_iso), set()).add(str(slot_label))
                fresh_by_day: dict[str, list[dict[str, Any]]] = {}
                for day_iso in grouped_days:
                    fresh_by_day[day_iso] = list_planning_allocations_for_range(day_iso, day_iso)
                batch_rows: list[dict[str, Any]] = []
                for day_iso, slot_labels_for_day in grouped_days.items():
                    fresh_rows = fresh_by_day.get(day_iso, [])
                    for slot_label in slot_labels_for_day:
                        if not force and _slot_mode(day_iso, slot_label) != "auto":
                            continue
                        slot_capacity = _safe_float(capacity_map.get((day_iso, slot_label), {}).get("workshop_capacity"))
                        slot_allocations = [
                            row
                            for row in fresh_rows
                            if str(row.get("slot_date") or "") == day_iso and str(row.get("slot_label") or "") == slot_label
                        ]
                        if not slot_allocations:
                            continue
                        if slot_capacity <= 0:
                            for row in slot_allocations:
                                batch_rows.append(
                                    {
                                        "allocation_id": int(row.get("id") or 0),
                                        "planning_order_id": int(row.get("planning_order_id") or 0),
                                        "capacity_slot_id": int(row.get("capacity_slot_id") or 0),
                                        "place_code": str(row.get("place_code") or ""),
                                        "fahrzeug": str(row.get("fahrzeug") or ""),
                                        "allocated_ma": 0.0,
                                        "note": str(row.get("note") or ""),
                                    }
                                )
                            continue
                        vehicle_count = len(slot_allocations)
                        rounded_capacity = max(0, int(round(slot_capacity)))
                        base_share = rounded_capacity // vehicle_count if vehicle_count else 0
                        remainder = rounded_capacity % vehicle_count if vehicle_count else 0
                        for index, row in enumerate(slot_allocations):
                            share = float(base_share + (1 if index < remainder else 0))
                            batch_rows.append(
                                {
                                    "allocation_id": int(row.get("id") or 0),
                                    "planning_order_id": int(row.get("planning_order_id") or 0),
                                    "capacity_slot_id": int(row.get("capacity_slot_id") or 0),
                                    "place_code": str(row.get("place_code") or ""),
                                    "fahrzeug": str(row.get("fahrzeug") or ""),
                                    "allocated_ma": share,
                                    "note": str(row.get("note") or ""),
                                }
                            )
                if batch_rows:
                    allocate_orders_to_capacity_batch(batch_rows, sync_schedule_order_ids=[])

            def _toggle_slot_mode(day_iso: str, slot_label: str, mode_value: Any) -> None:
                new_mode = "manual" if bool(mode_value) else "auto"
                _set_slot_mode(day_iso, slot_label, new_mode)
                if new_mode == "auto":
                    _redistribute_slot_ma(day_iso, slot_label, force=True)
                _invalidate_board_cache()
                render_week.refresh()

            def _set_allocation_ma(day_iso: str, slot_label: str, place_code: str, new_amount_raw: Any) -> None:
                allocation = allocation_map.get((day_iso, slot_label, place_code)) or {}
                if not allocation:
                    return
                new_amount = max(0.0, _safe_float(new_amount_raw))
                slot_capacity = _safe_float(capacity_map.get((day_iso, slot_label), {}).get("workshop_capacity"))
                slot_allocated_total = allocated_by_slot.get((day_iso, slot_label), 0.0)
                current_cell_amount = _safe_float(allocation.get("allocated_ma"))
                other_allocated = max(0.0, slot_allocated_total - current_cell_amount)
                if slot_capacity <= 0 and new_amount > 0:
                    ui.notify(
                        f"Für {day_iso} | {slot_label} ist noch keine Anwesenheit hinterlegt.",
                        type="warning",
                    )
                    return
                allocate_order_to_capacity(
                    planning_order_id=int(allocation.get("planning_order_id") or 0),
                    capacity_slot_id=int(allocation.get("capacity_slot_id") or 0),
                    place_code=place_code,
                    fahrzeug=str(allocation.get("fahrzeug") or ""),
                    allocated_ma=new_amount,
                    note=str(allocation.get("note") or ""),
                    sync_schedule=False,
                )
                if _slot_mode(day_iso, slot_label) != "manual":
                    _set_slot_mode(day_iso, slot_label, "manual")
                _invalidate_board_cache()
                if slot_capacity > 0 and (other_allocated + new_amount) > slot_capacity:
                    ui.notify(
                        f"{day_iso} | {slot_label} ist jetzt überplant. Der Slot wird rot markiert.",
                        type="warning",
                    )
                render_week.refresh()

            def _change_allocation_ma(day_iso: str, slot_label: str, place_code: str, delta: float) -> None:
                allocation = allocation_map.get((day_iso, slot_label, place_code)) or {}
                current_amount = _safe_float(allocation.get("allocated_ma"))
                _set_allocation_ma(day_iso, slot_label, place_code, current_amount + float(delta or 0.0))

            def _open_ma_editor(day_iso: str, slot_label: str, place_code: str) -> None:
                allocation = allocation_map.get((day_iso, slot_label, place_code)) or {}
                if not allocation:
                    return
                slot_capacity = _safe_float(capacity_map.get((day_iso, slot_label), {}).get("workshop_capacity"))
                slot_allocated_total = allocated_by_slot.get((day_iso, slot_label), 0.0)
                current_cell_amount = _safe_float(allocation.get("allocated_ma"))
                other_allocated = max(0.0, slot_allocated_total - current_cell_amount)
                free_for_this_cell = max(0.0, slot_capacity - other_allocated) if slot_capacity > 0 else 0.0

                with ui.dialog() as dialog, ui.card().classes("w-[360px] max-w-full upload-panel planning-page"):
                    ui.label("Mitarbeiter zuweisen").classes("planning-section-title")
                    ui.label(
                        f'{allocation.get("fahrzeug") or "-"} | {day_iso} | {slot_label} | {place_code}'
                    ).classes("planning-note")
                    ui.label(
                        f"Anwesend {slot_capacity:.1f} | Bereits anders verplant {other_allocated:.1f} | Frei für dieses Fahrzeug {free_for_this_cell:.1f}"
                    ).classes("planning-note")
                    ma_value = ui.number(
                        "Mitarbeiter im 4h-Slot",
                        value=current_cell_amount,
                        format="%.1f",
                    ).props("outlined step=1 min=0").classes("w-full")

                    with ui.row().classes("w-full justify-center gap-2"):
                        ui.button("−1", on_click=lambda: setattr(ma_value, "value", max(0.0, _safe_float(ma_value.value) - 1.0))).classes("btn-big")
                        ui.button("+1", on_click=lambda: setattr(ma_value, "value", _safe_float(ma_value.value) + 1.0)).classes("btn-big")

                    def _save_ma() -> None:
                        requested = max(0.0, _safe_float(ma_value.value))
                        if slot_capacity <= 0 and requested > 0:
                            ui.notify("Für diesen Slot ist noch keine Anwesenheit hinterlegt.", type="warning")
                            return
                        if slot_capacity > 0 and requested > free_for_this_cell:
                            ui.notify(f"Maximal möglich sind {free_for_this_cell:.1f} MA.", type="warning")
                            return
                        _set_allocation_ma(day_iso, slot_label, place_code, requested)
                        dialog.close()

                    with ui.row().classes("w-full justify-end gap-2"):
                        ui.button("Abbrechen", on_click=dialog.close).classes("btn-big")
                        ui.button("Speichern", on_click=_save_ma).classes("btn-big")
                dialog.open()

            def _start_edit_block(existing: dict[str, Any], place_code: str) -> None:
                if _is_done_status(existing.get("order_status")):
                    state["history_order_id"] = int(existing.get("planning_order_id") or 0)
                    state["active_order_id"] = None
                    state["range_start"] = None
                    state["edit_block"] = None
                    ui.notify("Erledigter Auftrag ist eingefroren. Links kannst du ihn bei Bedarf aus der Historie holen.", type="info")
                    render_week.refresh()
                    return
                block_rows = _contiguous_block(existing)
                block_start = block_rows[0]
                state["active_order_id"] = int(existing.get("planning_order_id") or 0)
                state["range_start"] = {
                    "slot_date": str(block_start.get("slot_date") or ""),
                    "slot_label": str(block_start.get("slot_label") or ""),
                    "place_code": place_code,
                }
                state["edit_block"] = {
                    "order_id": int(existing.get("planning_order_id") or 0),
                    "place_code": place_code,
                    "allocation_ids": [int(row.get("id") or 0) for row in block_rows],
                    "selected_allocation_id": int(existing.get("id") or 0),
                    "selected_slot": {
                        "slot_date": str(existing.get("slot_date") or ""),
                        "slot_label": str(existing.get("slot_label") or ""),
                        "place_code": place_code,
                    },
                    "block_start": {
                        "slot_date": str(block_rows[0].get("slot_date") or ""),
                        "slot_label": str(block_rows[0].get("slot_label") or ""),
                        "place_code": place_code,
                    },
                    "block_end": {
                        "slot_date": str(block_rows[-1].get("slot_date") or ""),
                        "slot_label": str(block_rows[-1].get("slot_label") or ""),
                        "place_code": place_code,
                    },
                }
                ui.notify("Bearbeitungsmodus aktiv. Jetzt neuen Endslot klicken.", type="info")
                render_week.refresh()

            def _current_edit_block() -> dict[str, Any] | None:
                current = state.get("edit_block")
                return current if isinstance(current, dict) else None

            def _selected_edit_allocation(current_edit_block: dict[str, Any]) -> dict[str, Any] | None:
                selected_allocation_id = int(current_edit_block.get("selected_allocation_id") or 0)
                if selected_allocation_id > 0 and selected_allocation_id in allocations_by_id:
                    return allocations_by_id[selected_allocation_id]
                selected_slot = current_edit_block.get("selected_slot") if isinstance(current_edit_block.get("selected_slot"), dict) else None
                if selected_slot:
                    row = allocation_map.get(
                        (
                            str(selected_slot.get("slot_date") or ""),
                            str(selected_slot.get("slot_label") or ""),
                            str(selected_slot.get("place_code") or ""),
                        )
                    )
                    if row and int(row.get("planning_order_id") or 0) == int(current_edit_block.get("order_id") or 0):
                        return row
                return None

            def _edit_block_rows(current_edit_block: dict[str, Any]) -> list[dict[str, Any]]:
                selected_row = _selected_edit_allocation(current_edit_block)
                if selected_row:
                    return _contiguous_block(selected_row)
                block_start = current_edit_block.get("block_start") if isinstance(current_edit_block.get("block_start"), dict) else None
                block_end = current_edit_block.get("block_end") if isinstance(current_edit_block.get("block_end"), dict) else None
                place_code = str(current_edit_block.get("place_code") or "")
                order_id = int(current_edit_block.get("order_id") or 0)
                if not block_start or not block_end or not place_code or order_id <= 0:
                    return []
                slot_rows = _range_slot_rows(place_code, block_start, block_end)
                return [
                    row
                    for slot_row in slot_rows
                    for row in [
                        allocation_map.get(
                            (
                                str(slot_row.get("slot_date") or ""),
                                str(slot_row.get("slot_label") or ""),
                                place_code,
                            )
                        )
                    ]
                    if row and int(row.get("planning_order_id") or 0) == order_id
                ]

            def _remove_selected_slot() -> None:
                current_edit_block = _current_edit_block()
                if not current_edit_block:
                    return
                target_row = _selected_edit_allocation(current_edit_block)
                if not target_row:
                    ui.notify("Der ausgewählte Slot wurde nicht gefunden.", type="warning")
                    return
                selected_allocation_id = int(target_row.get("id") or 0)
                if selected_allocation_id <= 0:
                    ui.notify("Kein Slot zum Löschen ausgewählt.", type="warning")
                    return
                removed_day = str(target_row.get("slot_date") or "")
                removed_slot = str(target_row.get("slot_label") or "")
                removed_order_id = int(target_row.get("planning_order_id") or 0)
                remove_allocation(allocation_id=selected_allocation_id, sync_schedule=False)
                _redistribute_slot_ma(removed_day, removed_slot)
                if removed_order_id > 0:
                    sync_order_schedule_from_allocations(planning_order_id=removed_order_id, reset_release=True)
                state["active_order_id"] = None
                state["range_start"] = None
                state["edit_block"] = None
                _invalidate_board_cache()
                ui.notify("Slot entfernt.", type="positive")
                render_week.refresh()

            def _remove_active_block() -> None:
                current_edit_block = _current_edit_block()
                if not current_edit_block:
                    return
                block_rows = _edit_block_rows(current_edit_block)
                if not block_rows:
                    ui.notify("Kein Block zum Löschen ausgewählt.", type="warning")
                    return
                allocation_ids = {
                    int(row.get("id") or 0)
                    for row in block_rows
                    if int(row.get("id") or 0) > 0
                }
                affected_slots = {
                    (str(row.get("slot_date") or ""), str(row.get("slot_label") or ""))
                    for row in block_rows
                }
                affected_order_ids = {
                    int(row.get("planning_order_id") or 0)
                    for row in block_rows
                    if int(row.get("planning_order_id") or 0) > 0
                }
                remove_allocations(allocation_ids=list(allocation_ids), sync_schedule=False)
                _redistribute_slot_set(affected_slots)
                for order_id in affected_order_ids:
                    sync_order_schedule_from_allocations(planning_order_id=order_id, reset_release=True)
                state["active_order_id"] = None
                state["range_start"] = None
                state["edit_block"] = None
                _invalidate_board_cache()
                ui.notify("Block entfernt.", type="positive")
                render_week.refresh()

            def _start_additional_block() -> None:
                if active_order is None:
                    return
                state["range_start"] = None
                state["edit_block"] = None
                ui.notify("Zusatzblock aktiv. Jetzt Startslot für diesen Auftrag wählen.", type="info")

            def _select_order_from_panel(order_id: int) -> None:
                selected_order = next((row for row in orders if int(row.get("id") or 0) == int(order_id or 0)), None)
                state["active_order_id"] = int(order_id or 0)
                state["range_start"] = None
                state["edit_block"] = None
                state["history_order_id"] = None
                start_date_raw = str((selected_order or {}).get("ecm3_start_date") or "").strip()
                if start_date_raw:
                    try:
                        target_week_start = _week_start(date.fromisoformat(start_date_raw)).isoformat()
                        if target_week_start != str(state.get("week_start") or ""):
                            state["week_start"] = target_week_start
                            state["suppress_week_input_refresh"] = True
                            week_input.value = target_week_start
                            state["suppress_week_input_refresh"] = False
                            _invalidate_board_cache()
                    except ValueError:
                        state["suppress_week_input_refresh"] = False
                render_week.refresh()

            def _start_order_edit_from_panel(order_id: int) -> None:
                allocation = next(
                    (row for row in order_allocation_rows if int(row.get("planning_order_id") or 0) == int(order_id or 0)),
                    None,
                )
                if not allocation:
                    _select_order_from_panel(order_id)
                    return
                _start_edit_block(allocation, str(allocation.get("place_code") or ""))

            def _remove_all_active_order_blocks() -> None:
                if active_order is None:
                    return
                active_order_id = int(active_order.get("id") or 0)
                if active_order_id <= 0:
                    return
                affected_slots = {
                    (str(row.get("slot_date") or ""), str(row.get("slot_label") or ""))
                    for row in allocation_rows
                    if int(row.get("planning_order_id") or 0) == active_order_id
                }
                remove_order_allocations(planning_order_id=active_order_id)
                if affected_slots:
                    _redistribute_slot_set(affected_slots, force=True)
                state["active_order_id"] = None
                state["range_start"] = None
                state["edit_block"] = None
                state["history_order_id"] = None
                _invalidate_board_cache()
                ui.notify("Alle Blöcke dieses Auftrags wurden entfernt.", type="positive")
                render_week.refresh()

            def _handle_cell_click(slot_date_iso: str, slot_label: str, place_code: str) -> None:
                current_active_order = _current_active_order()
                current_range_start = state.get("range_start") if isinstance(state.get("range_start"), dict) else None
                existing = allocation_map.get((slot_date_iso, slot_label, place_code)) or {}
                if existing and _is_done_status(existing.get("order_status")):
                    _start_edit_block(existing, place_code)
                    return
                if existing and current_range_start is None and (
                    current_active_order is None
                    or int(existing.get("planning_order_id") or 0) == int(current_active_order.get("id") or 0)
                ):
                    _start_edit_block(existing, place_code)
                    return
                if current_active_order is None:
                    ui.notify("Bitte zuerst links einen Auftrag auswählen.", type="warning")
                    return
                if current_range_start is None:
                    state["range_start"] = {"slot_date": slot_date_iso, "slot_label": slot_label, "place_code": place_code}
                    ui.notify("Startslot gesetzt. Jetzt Endslot anklicken.", type="info")
                    return
                _confirm_range_allocation(slot_date_iso, slot_label, place_code)

            def _handle_drop(event: Any, slot_date_iso: str, slot_label: str, place_code: str) -> None:
                raw_order_id = None
                if hasattr(event, "args") and isinstance(event.args, dict):
                    raw_order_id = event.args.get("order_id")
                try:
                    preferred_order_id = int(raw_order_id) if raw_order_id not in (None, "", "null") else None
                except Exception:
                    preferred_order_id = None
                if preferred_order_id is not None:
                    state["active_order_id"] = preferred_order_id
                    state["range_start"] = {"slot_date": slot_date_iso, "slot_label": slot_label, "place_code": place_code}
                    ui.notify("Auftrag aufgenommen. Jetzt Endslot anklicken.", type="info")

            with body:
                with ui.element("div").classes("planning-week-layout"):
                    with ui.card().classes("upload-panel planning-card planning-page planning-orders-panel"):
                        ui.label(f"Planungsaufträge ({len(open_orders)} in Planung)").classes("planning-section-title")
                        ui.label(
                            "Links wählt ihr den Auftrag insgesamt aus. In der Tafel bearbeitet ihr immer nur den angeklickten durchgehenden Block."
                        ).classes("planning-note")
                        help_classes = "planning-range-help"
                        if range_start:
                            help_classes += " is-active"
                        with ui.element("div").classes(help_classes):
                            if active_order is None:
                                with ui.column().classes("w-full gap-1"):
                                    ui.label("1. Links Auftrag wählen.").classes("planning-note")
                                    ui.label("2. Startslot klicken oder Auftrag auf Startslot ziehen.").classes("planning-note")
                                    ui.label("3. Endslot klicken.").classes("planning-note")
                            elif edit_block is not None:
                                block_start = edit_block.get("block_start") if isinstance(edit_block.get("block_start"), dict) else {}
                                block_end = edit_block.get("block_end") if isinstance(edit_block.get("block_end"), dict) else {}
                                ui.label(
                                    f'Bearbeitungsmodus: Block auf {edit_block.get("place_code")} von {block_start.get("slot_date")} | {block_start.get("slot_label")} bis {block_end.get("slot_date")} | {block_end.get("slot_label")}. Jetzt Zielslot klicken: innerhalb/danach kürzt oder verlängert das Ende, davor zieht den Start nach vorne.'
                                ).classes("planning-note")
                            elif range_start is None:
                                ui.label(
                                    f'Aktiver Auftrag: {active_order.get("fahrzeug") or "-"} | Rest (8h) {active_order.get("remaining_total") or 0:.1f}. Jetzt Startslot auf dem gewünschten Gleis anklicken.'
                                ).classes("planning-note")
                            else:
                                ui.label(
                                    f'Start gesetzt: {range_start.get("slot_date")} | {range_start.get("slot_label")} | {range_start.get("place_code")}. Jetzt Endslot anklicken.'
                                ).classes("planning-note")
                        if history_order is not None:
                            with ui.element("div").classes("planning-active-order"):
                                ui.label("Eingefrorener historischer Auftrag").classes("planning-section-title")
                                ui.label(
                                    f'{history_order.get("fahrzeug") or "-"} | {history_order.get("friststufe") or "-"}'
                                ).classes("planning-order-main")
                                ui.label(
                                    "Dieser Auftrag ist erledigt/archiviert. Die Slotbelegung bleibt sichtbar, kann aber nicht bearbeitet werden."
                                ).classes("planning-note")
                                with ui.row().classes("w-full gap-2 mt-2"):
                                    ui.button(
                                        "Auswahl aufheben",
                                        on_click=lambda: (
                                            state.__setitem__("history_order_id", None),
                                            render_week.refresh(),
                                        ),
                                    ).classes("btn-big")
                                    ui.button(
                                        "Aus Historie holen",
                                        on_click=lambda _=None, oid=int(history_order.get("id") or 0): _restore_history_order(oid),
                                    ).props("color=warning").classes("btn-big")
                        elif active_order is not None:
                            with ui.element("div").classes("planning-active-order"):
                                ui.label("Aktiver Auftrag für die Tafel").classes("planning-section-title")
                                ui.label(
                                    f'{active_order.get("fahrzeug") or "-"} | {active_order.get("friststufe") or "-"} | Rest (8h) {active_order.get("remaining_total") or 0:.1f}'
                                ).classes("planning-order-main")
                                ecm3_text = (
                                    f'ECM3: {active_order.get("ecm3_start_date") or "-"} {active_order.get("ecm3_start_time") or ""} '
                                    f'bis {active_order.get("ecm3_end_date") or "-"} {active_order.get("ecm3_end_time") or ""}'
                                )
                                if _active_order_has_gewerke():
                                    ecm3_text += " | Gewerke"
                                ui.label(ecm3_text).classes("planning-order-sub")
                                active_gewerke_text = _gewerke_status_text(active_order, detailed=True)
                                if active_gewerke_text:
                                    active_gewerke_status = _order_gewerke_status(active_order)
                                    status_classes = "planning-gewerke-status"
                                    if active_gewerke_status.get("open"):
                                        status_classes += " is-open"
                                    ui.label(active_gewerke_text).classes(status_classes)
                                with ui.row().classes("w-full gap-2 mt-2"):
                                    ui.button("Zusätzlichen Block", on_click=_start_additional_block).classes("btn-big")
                                    if _safe_float(active_order.get("allocated_total")) > 0:
                                        ui.button("Alle Blöcke löschen", on_click=_remove_all_active_order_blocks).classes("btn-big")
                                    ui.button(
                                        "Auswahl aufheben",
                                        on_click=lambda: (
                                            state.__setitem__("active_order_id", None),
                                            state.__setitem__("range_start", None),
                                            state.__setitem__("edit_block", None),
                                            state.__setitem__("history_order_id", None),
                                            render_week.refresh(),
                                        ),
                                    ).classes("btn-big")
                                    if edit_block is not None:
                                        ui.button("Slot löschen", on_click=_remove_selected_slot).classes("btn-big")
                                        ui.button("Block löschen", on_click=_remove_active_block).classes("btn-big")
                        for order in open_orders:
                            zeitfenster = (
                                f'{order.get("ecm3_start_date") or "-"} {order.get("ecm3_start_time") or ""} '
                                f'-> {order.get("ecm3_end_date") or "-"} {order.get("ecm3_end_time") or ""}'
                            )
                            item_classes = "planning-order-item"
                            if str(order.get("progress_state") or "") == "partial":
                                item_classes += " is-partial"
                            gewerke_status = _order_gewerke_status(order)
                            if gewerke_status.get("open"):
                                item_classes += " has-open-gewerke"
                            if int(order.get("id") or 0) == int(state.get("active_order_id") or 0):
                                item_classes += " is-active"
                            with ui.element("div").classes(item_classes).props("draggable").on(
                                "click",
                                lambda _=None, order_id=int(order.get("id") or 0): _select_order_from_panel(order_id),
                            ).on(
                                "dragstart",
                                js_handler=f"(e) => {{ window.planningDragOrderId = {int(order.get('id') or 0)}; emit({{order_id: {int(order.get('id') or 0)}}}); }}",
                            ).on(
                                "dragend",
                                js_handler="() => { window.planningDragOrderId = null; }",
                            ):
                                ui.label(f'{order.get("fahrzeug") or "-"} | {order.get("friststufe") or "-"}').classes(
                                    "planning-order-main"
                                )
                                ui.label(_order_status_label(order.get("status"))).classes(
                                    f'planning-form-item-status {_order_status_class(order.get("status"))}'
                                )
                                ui.label(
                                    f'Art: {order.get("order_kind") or "-"} | Bedarf (8h): {order.get("required_total") or 0:.1f} | Verplant (8h): {order.get("allocated_total") or 0:.1f} | Rest (8h): {order.get("remaining_total") or 0:.1f}'
                                ).classes("planning-order-sub")
                                with ui.element("div").classes("planning-order-progress"):
                                    ui.element("div").classes("planning-order-progress-bar").style(
                                        f"width: {max(0.0, min(100.0, float(order.get('progress_ratio') or 0.0) * 100.0)):.1f}%;"
                                    )
                                ui.label(zeitfenster).classes("planning-order-sub")
                                gewerke_text = _gewerke_status_text(order)
                                if gewerke_text:
                                    status_classes = "planning-gewerke-status"
                                    if gewerke_status.get("open"):
                                        status_classes += " is-open"
                                    ui.label(gewerke_text).classes(status_classes)
                                if str(order.get("zusatzarbeiten") or "").strip():
                                    ui.label(str(order.get("zusatzarbeiten") or "")).classes("planning-order-sub")
                        if not open_orders:
                            ui.label("Aktuell sind keine Aufträge in der Slotplanung sichtbar.").classes("planning-note")
                        if completed_orders:
                            ui.separator().classes("my-2")
                            ui.label(f"Voll eingeplant ({len(completed_orders)})").classes("planning-section-title")
                            releasable_count = sum(1 for order in completed_orders if _can_release_order(order))
                            if releasable_count:
                                ui.button(
                                    f"Alle freigeben ({releasable_count})",
                                    on_click=_release_all_visible_completed_orders,
                                ).classes("btn-big w-full mb-2")
                            for order in completed_orders:
                                item_classes = "planning-order-item is-done"
                                if _safe_float(order.get("overallocated_total")) > overplanned_threshold:
                                    item_classes += " is-overplanned"
                                gewerke_status = _order_gewerke_status(order)
                                if gewerke_status.get("open"):
                                    item_classes += " has-open-gewerke"
                                if int(order.get("id") or 0) == int(state.get("active_order_id") or 0):
                                    item_classes += " is-active"
                                with ui.element("div").classes(item_classes).props("draggable").on(
                                    "click",
                                    lambda _=None, order_id=int(order.get("id") or 0): _start_order_edit_from_panel(order_id),
                                ).on(
                                    "dragstart",
                                    js_handler=f"(e) => {{ window.planningDragOrderId = {int(order.get('id') or 0)}; emit({{order_id: {int(order.get('id') or 0)}}}); }}",
                                ).on(
                                    "dragend",
                                    js_handler="() => { window.planningDragOrderId = null; }",
                                ):
                                    ui.label(f'{order.get("fahrzeug") or "-"} | {order.get("friststufe") or "-"}').classes(
                                        "planning-order-main"
                                    )
                                    ui.label(_order_status_label(order.get("status"))).classes(
                                        f'planning-form-item-status {_order_status_class(order.get("status"))}'
                                    )
                                    sub_text = (
                                        f'Bedarf (8h) {order.get("required_total") or 0:.1f} | '
                                        f'Verplant (8h) {order.get("allocated_total") or 0:.1f}'
                                    )
                                    ui.label(sub_text).classes("planning-order-sub")
                                    gewerke_text = _gewerke_status_text(order)
                                    if gewerke_text:
                                        status_classes = "planning-gewerke-status"
                                        if gewerke_status.get("open"):
                                            status_classes += " is-open"
                                        ui.label(gewerke_text).classes(status_classes)
                                    if _can_release_order(order):
                                        ui.button(
                                            "Freigeben",
                                            on_click=lambda _=None, oid=int(order.get("id") or 0): _release_order_from_slot_planner(oid),
                                        ).classes("btn-big mt-2")
                    with ui.column().classes("w-full gap-2 planning-week-board"):
                        with ui.element("div").classes("planning-day-grid"):
                            for day_value in week_dates:
                                day_iso = day_value.isoformat()
                                summary = day_summaries.get(day_iso) or {"capacity": 0.0, "allocated": 0.0}
                                summary_classes = "planning-day-summary"
                                if _safe_float(summary.get("allocated")) > _safe_float(summary.get("capacity")):
                                    summary_classes += " is-overbooked"
                                card_classes = "planning-day-card planning-day-today" if day_value == today else "planning-day-card"
                                with ui.element("div").classes(f"planning-day-column {card_classes}"):
                                    ui.label(_weekday_name_de(day_value)).classes("planning-day-name")
                                    ui.label(day_value.strftime("%d.%m.%Y")).classes("planning-day-date")
                                    ui.label(
                                        f"Werkstatt {_safe_float(summary.get('allocated')):.1f}/{_safe_float(summary.get('capacity')):.1f}"
                                    ).classes(summary_classes)
                                    matrix_columns = max(1, len(places))
                                    with ui.element("div").classes("planning-day-matrix").style(
                                        f"grid-template-columns: minmax(88px, 110px) repeat({matrix_columns}, minmax(120px, 1fr));"
                                    ):
                                        ui.label("Slot").classes("planning-matrix-head planning-matrix-corner")
                                        for place in places:
                                            ui.label(str(place.get("code") or "")).classes("planning-matrix-head")
                                        for slot_label in board.get("slot_labels", []):
                                            slot_template = slot_template_map.get(str(slot_label) or "") or {}
                                            slot_display = (
                                                f'{slot_template.get("start_time") or ""} - {slot_template.get("end_time") or ""}'.strip(" -")
                                                or str(slot_label or "")
                                            )
                                            capacity_row = capacity_map.get((day_iso, slot_label)) or {}
                                            slot_key = (day_iso, str(slot_label))
                                            allocated_sum = allocated_by_slot.get(slot_key, 0.0)
                                            slot_capacity = _safe_float(capacity_row.get("workshop_capacity"))
                                            slot_role_values = slot_role_capacities.get(f"{day_iso}|{slot_label}", {})
                                            slot_mode = _slot_mode(day_iso, slot_label)
                                            slot_in_ecm3_window = _slot_within_active_window(day_iso, slot_label)
                                            has_gewerke_window = _slot_marks_active_gewerke(day_iso, slot_label)
                                            cap_class = "planning-slot-capacity"
                                            if slot_capacity <= 0:
                                                cap_class += " is-missing"
                                            if slot_capacity > 0 and allocated_sum >= slot_capacity:
                                                cap_class += " is-balanced"
                                            if slot_capacity > 0 and allocated_sum > slot_capacity:
                                                cap_class += " is-overbooked"
                                            with ui.column().classes("gap-1"):
                                                ui.label(slot_display).classes("planning-slot-label")
                                                with ui.row().classes("planning-slot-mode-row"):
                                                    auto_classes = "planning-slot-mode-text"
                                                    if slot_mode != "manual":
                                                        auto_classes += " is-active"
                                                    ui.label("Auto").classes(auto_classes)
                                                    mode_switch = ui.switch(
                                                        value=(slot_mode == "manual"),
                                                    ).props("dense color=amber")
                                                    mode_switch.on_value_change(
                                                        lambda e, d=day_iso, s=slot_label: _toggle_slot_mode(d, s, e.value)
                                                    )
                                                    manual_classes = "planning-slot-mode-text"
                                                    if slot_mode == "manual":
                                                        manual_classes += " is-active"
                                                    ui.label("Hand").classes(manual_classes)
                                                for role in capacity_roles:
                                                    role_key = str(role.get("role_key") or "")
                                                    role_label = str(role.get("label") or role_key)
                                                    role_capacity = _safe_float(slot_role_values.get(role_key))
                                                    role_allocated = allocated_sum if role_key == "workshop" else 0.0
                                                    role_class = cap_class if role_key == "workshop" else "planning-slot-capacity"
                                                    with ui.row().classes("items-center gap-1 no-wrap"):
                                                        ui.label(
                                                            f"{role_label} {role_allocated:.1f}/{role_capacity:.1f}"
                                                        ).classes(role_class)
                                                        if _role_capacity_field(role_key):
                                                            ui.button(
                                                                "-",
                                                                on_click=lambda _=None, d=day_iso, s=slot_label, rk=role_key: _change_role_capacity(d, s, rk, -1.0),
                                                            ).props("dense flat color=white").classes("planning-place-ma-btn")
                                                            ui.button(
                                                                "+",
                                                                on_click=lambda _=None, d=day_iso, s=slot_label, rk=role_key: _change_role_capacity(d, s, rk, 1.0),
                                                            ).props("dense flat color=white").classes("planning-place-ma-btn")
                                            for place in places:
                                                place_code = str(place.get("code") or "")
                                                allocation = allocation_map.get((day_iso, slot_label, place_code)) or {}
                                                busy = bool(allocation)
                                                frozen = busy and _is_done_status(allocation.get("order_status"))
                                                chip_class = "planning-place-chip"
                                                if busy:
                                                    chip_class += " is-busy"
                                                if frozen:
                                                    chip_class += " is-frozen"
                                                elif slot_capacity <= 0:
                                                    chip_class += " is-missing"
                                                if active_order is not None:
                                                    if has_gewerke_window:
                                                        chip_class += " is-gewerke-window"
                                                    elif slot_in_ecm3_window:
                                                        chip_class += " is-ecm3-window"
                                                    else:
                                                        chip_class += " is-outside-ecm3"
                                                if busy and not frozen and slot_capacity > 0 and allocated_sum >= slot_capacity:
                                                    chip_class += " is-balanced"
                                                if busy and not frozen and slot_capacity > 0 and allocated_sum > slot_capacity:
                                                    chip_class += " is-overbooked"
                                                if range_start and str(range_start.get("slot_date") or "") == day_iso and str(range_start.get("slot_label") or "") == slot_label and str(range_start.get("place_code") or "") == place_code:
                                                    chip_class += " is-range-start"
                                                elif _preview_contains(day_iso, slot_label, place_code):
                                                    chip_class += " is-range-preview"
                                                status_label = "Erledigt" if frozen else "Belegt" if busy else "Frei"
                                                main_label = (
                                                    str(allocation.get("fahrzeug") or "-")
                                                    if busy
                                                    else ("Ende wählen" if state.get("active_order_id") and range_start else "Start wählen" if state.get("active_order_id") else "Start/Ende klicken")
                                                )
                                                sub_label = (
                                                    "Eingefroren"
                                                    if frozen
                                                    else f"FZG MA {_safe_float(allocation.get('allocated_ma')):.1f}"
                                                    if busy
                                                    else (
                                                        "Gewerke-Zeitfenster"
                                                        if has_gewerke_window
                                                        else "ECM3-Zeitfenster"
                                                        if slot_in_ecm3_window
                                                        else "Außerhalb ECM3"
                                                        if active_order is not None
                                                        else "Mitarbeiter später"
                                                        if slot_capacity <= 0
                                                        else "Platz verfügbar"
                                                    )
                                                )
                                                with ui.element("div").classes(chip_class).on(
                                                    "click",
                                                    lambda _=None, d=day_iso, s=slot_label, p=place_code: _handle_cell_click(d, s, p),
                                                ).on(
                                                    "dragover",
                                                    js_handler="(e) => { e.preventDefault(); e.currentTarget.classList.add('is-drop-target'); }",
                                                ).on(
                                                    "dragleave",
                                                    js_handler="(e) => { e.currentTarget.classList.remove('is-drop-target'); }",
                                                ).on(
                                                    "drop",
                                                    lambda e, d=day_iso, s=slot_label, p=place_code: _handle_drop(e, d, s, p),
                                                    js_handler="(e) => { e.preventDefault(); e.currentTarget.classList.remove('is-drop-target'); emit({order_id: window.planningDragOrderId || null}); }",
                                                ):
                                                    ui.label(status_label).classes("planning-place-status")
                                                    ui.label(main_label).classes("planning-place-main")
                                                    ui.label(sub_label).classes("planning-place-sub")
                                                    if busy and not frozen:
                                                        with ui.row().classes("planning-place-ma-controls").on(
                                                            "click",
                                                            js_handler="(e) => { e.stopPropagation(); }",
                                                        ):
                                                            ui.button(
                                                                "-",
                                                                on_click=lambda _=None, d=day_iso, s=slot_label, p=place_code: _change_allocation_ma(d, s, p, -1.0),
                                                            ).props("dense flat color=white").classes("planning-place-ma-btn")
                                                            ui.label(
                                                                f'{_safe_float(allocation.get("allocated_ma")):.1f}'
                                                            ).classes("planning-place-ma-value")
                                                            ui.button(
                                                                "+",
                                                                on_click=lambda _=None, d=day_iso, s=slot_label, p=place_code: _change_allocation_ma(d, s, p, 1.0),
                                                            ).props("dense flat color=white").classes("planning-place-ma-btn")

        def _on_week_input_change(_e: Any = None) -> None:
            if state.get("suppress_week_input_refresh"):
                return
            raw_value = str(week_input.value or "").strip()
            try:
                normalized = _week_start(date.fromisoformat(raw_value)).isoformat()
            except ValueError:
                normalized = state["week_start"]
            if normalized == str(state.get("week_start") or "") and raw_value == normalized:
                return
            state["week_start"] = normalized
            if raw_value != normalized:
                state["suppress_week_input_refresh"] = True
                week_input.value = normalized
                state["suppress_week_input_refresh"] = False
            render_week.refresh()

        week_input.on_value_change(_on_week_input_change)
        render_week()

    @ui.page("/planung/formular")
    def page_planning_board() -> None:
        if not _admin_guard(
            render_nav_fn,
            is_admin_fn,
            [("Planung", lambda: ui.navigate.to("/planung")), ("Auftragsplanung", None)],
        ):
            return
        state: dict[str, Any] = {"selected_ids": set(), "view_mode": "board", "status_filter": "all", "search_text": ""}
        body = ui.column().classes("w-full gap-3 planning-page")

        @ui.refreshable
        def render_order_form() -> None:
            body.clear()
            orders_data = get_order_board()
            orders = orders_data.get("orders", [])
            order_map = {int(row.get("id") or 0): row for row in orders if int(row.get("id") or 0) > 0}
            selected_ids = {int(value) for value in state.get("selected_ids", set()) if int(value or 0) in order_map}
            state["selected_ids"] = selected_ids

            def _filtered_orders() -> list[dict[str, Any]]:
                status_filter = str(state.get("status_filter") or "all").strip().lower()
                search_text = str(state.get("search_text") or "").strip().lower()
                filtered: list[dict[str, Any]] = []
                for row in orders:
                    row_status = str(row.get("status") or "in_erstellung").strip().lower()
                    if status_filter != "all" and row_status != status_filter:
                        continue
                    haystack = " ".join(
                        [
                            str(row.get("fahrzeug") or ""),
                            str(row.get("friststufe") or ""),
                            str(row.get("order_kind") or ""),
                            str(row.get("zusatzarbeiten") or ""),
                            str(row.get("gewerke_info") or ""),
                        ]
                    ).lower()
                    if search_text and search_text not in haystack:
                        continue
                    filtered.append(row)
                return filtered

            filtered_orders = _filtered_orders()
            status_groups = {
                "in_erstellung": [row for row in filtered_orders if str(row.get("status") or "in_erstellung").strip().lower() == "in_erstellung"],
                "in_planung": [row for row in filtered_orders if str(row.get("status") or "").strip().lower() == "in_planung"],
                "freigegeben": [row for row in filtered_orders if str(row.get("status") or "").strip().lower() == "freigegeben"],
            }
            status_counts = {
                "in_erstellung": sum(1 for row in orders if str(row.get("status") or "in_erstellung").strip().lower() == "in_erstellung"),
                "in_planung": sum(1 for row in orders if str(row.get("status") or "").strip().lower() == "in_planung"),
                "freigegeben": sum(1 for row in orders if str(row.get("status") or "").strip().lower() == "freigegeben"),
            }

            def _open_order_dialog(order_id: int | None = None) -> None:
                selected = order_map.get(int(order_id or 0)) if order_id else None
                zus_entries = _parse_multiline_entries((selected or {}).get("zusatzarbeiten") or "")
                raw_gewerk_entries = _parse_multiline_entries((selected or {}).get("gewerke_info") or "")
                zus_items = [{"text": entry} for entry in zus_entries] or [{"text": ""}]

                def _parse_gewerk_entry(entry: str) -> dict[str, str]:
                    text = str(entry or "").strip()
                    date_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
                    time_match = re.search(r"\b(\d{1,2}:\d{2})\b", text)
                    date_value = date_match.group(1) if date_match else ""
                    time_value = time_match.group(1) if time_match else ""
                    cleaned = text
                    if date_value:
                        cleaned = cleaned.replace(date_value, "", 1).strip()
                    if time_value:
                        cleaned = cleaned.replace(time_value, "", 1).strip()
                    cleaned = cleaned.lstrip("|- ").strip()
                    return {"text": cleaned, "date": date_value, "time": time_value}

                gewerk_items = [_parse_gewerk_entry(entry) for entry in raw_gewerk_entries] or [
                    {"text": "", "date": "", "time": ""}
                ]

                with ui.dialog() as dialog, ui.card().classes("w-[820px] max-w-full upload-panel planning-page"):
                    ui.label("Auftrag bearbeiten" if selected else "Neuer Auftrag").classes("planning-section-title")
                    order_fzg, order_vehicle_values = _render_configured_vehicle_select(
                        "Fahrzeug",
                        str((selected or {}).get("fahrzeug") or ""),
                    )
                    order_frist = ui.input("Friststufe", value=str((selected or {}).get("friststufe") or ""), placeholder="z. B. IS1").props("outlined").classes("w-full")
                    order_kind = ui.input("Art p / k / URD", value=str((selected or {}).get("order_kind") or ""), placeholder="p").props("outlined").classes("w-full")
                    order_status_options = {"in_erstellung": "In Erstellung", "in_planung": "In Planung"}
                    if str((selected or {}).get("status") or "").strip().lower() == "freigegeben":
                        order_status_options["freigegeben"] = "Freigegeben"
                    order_status = ui.select(
                        order_status_options,
                        value=str((selected or {}).get("status") or "in_erstellung"),
                        label="Status",
                    ).props("outlined").classes("w-full")
                    with ui.row().classes("w-full gap-2 wrap"):
                        order_ecm3_start_date = ui.input("ECM3 Start Datum", value=str((selected or {}).get("ecm3_start_date") or "")).props("type=date outlined").classes("grow min-w-[180px] prio-day-input")
                        order_ecm3_start_time = ui.input("ECM3 Start Zeit", value=str((selected or {}).get("ecm3_start_time") or "")).props("type=time outlined").classes("grow min-w-[180px]")
                    with ui.row().classes("w-full gap-2 wrap"):
                        order_ecm3_end_date = ui.input("ECM3 Ende Datum", value=str((selected or {}).get("ecm3_end_date") or "")).props("type=date outlined").classes("grow min-w-[180px] prio-day-input")
                        order_ecm3_end_time = ui.input("ECM3 Ende Zeit", value=str((selected or {}).get("ecm3_end_time") or "")).props("type=time outlined").classes("grow min-w-[180px]")
                    order_required = ui.number("Benötigte MA (8h)", value=_safe_float((selected or {}).get("required_ma_8h")), format="%.2f").props("outlined").classes("w-full")

                    ui.label("Zusatzarbeiten").classes("planning-note")

                    @ui.refreshable
                    def render_zus_items() -> None:
                        with ui.column().classes("w-full gap-2"):
                            for index, item in enumerate(list(zus_items)):
                                with ui.row().classes("w-full gap-2 items-center"):
                                    zus_input = ui.input(
                                        f"Zusatzarbeit {index + 1}",
                                        value=str(item.get("text") or ""),
                                        placeholder="Zusatzarbeit eingeben",
                                    ).props("outlined").classes("grow")
                                    zus_input.on_value_change(
                                        lambda e, idx=index: zus_items.__setitem__(idx, {"text": str(e.value or "")})
                                    )
                                    ui.button(
                                        "X",
                                        on_click=lambda _=None, idx=index: (
                                            zus_items.pop(idx),
                                            zus_items.append({"text": ""}) if not zus_items else None,
                                            render_zus_items.refresh(),
                                        ),
                                    ).props("flat color=negative")
                            ui.button(
                                "Zusatzarbeit hinzufügen",
                                on_click=lambda: (zus_items.append({"text": ""}), render_zus_items.refresh()),
                            ).classes("btn-big self-start")

                    render_zus_items()

                    ui.label("Gewerke").classes("planning-note mt-2")

                    @ui.refreshable
                    def render_gewerk_items() -> None:
                        with ui.column().classes("w-full gap-2"):
                            for index, item in enumerate(list(gewerk_items)):
                                with ui.row().classes("w-full gap-2 items-center wrap"):
                                    gewerk_text = ui.input(
                                        f"Gewerk {index + 1}",
                                        value=str(item.get("text") or ""),
                                        placeholder="Gewerk / Hinweis",
                                    ).props("outlined").classes("grow min-w-[240px]")
                                    gewerk_date = ui.input(
                                        "Tag",
                                        value=str(item.get("date") or ""),
                                    ).props("type=date outlined").classes("min-w-[180px] prio-day-input")
                                    gewerk_time = ui.input(
                                        "Zeit",
                                        value=str(item.get("time") or ""),
                                    ).props("type=time outlined").classes("min-w-[160px]")
                                    gewerk_text.on_value_change(
                                        lambda e, idx=index: gewerk_items[idx].__setitem__("text", str(e.value or ""))
                                    )
                                    gewerk_date.on_value_change(
                                        lambda e, idx=index: gewerk_items[idx].__setitem__("date", str(e.value or ""))
                                    )
                                    gewerk_time.on_value_change(
                                        lambda e, idx=index: gewerk_items[idx].__setitem__("time", str(e.value or ""))
                                    )
                                    ui.button(
                                        "X",
                                        on_click=lambda _=None, idx=index: (
                                            gewerk_items.pop(idx),
                                            gewerk_items.append({"text": "", "date": "", "time": ""}) if not gewerk_items else None,
                                            render_gewerk_items.refresh(),
                                        ),
                                    ).props("flat color=negative")
                            ui.button(
                                "Gewerk hinzufügen",
                                on_click=lambda: (
                                    gewerk_items.append({"text": "", "date": "", "time": ""}),
                                    render_gewerk_items.refresh(),
                                ),
                            ).classes("btn-big self-start")

                    render_gewerk_items()

                    def _save_dialog(target_status: str | None = None) -> None:
                        vehicle_value = str(order_fzg.value or "").strip()
                        if not vehicle_value or vehicle_value not in order_vehicle_values:
                            ui.notify("Bitte Fahrzeug aus der Konfiguration auswählen.", type="warning")
                            return
                        if not str(order_frist.value or "").strip():
                            ui.notify("Bitte Fahrzeug und Friststufe ausfüllen.", type="warning")
                            return
                        zus_lines = [str(item.get("text") or "").strip() for item in zus_items if str(item.get("text") or "").strip()]
                        gewerk_lines: list[str] = []
                        for item in gewerk_items:
                            gewerk_text = str(item.get("text") or "").strip()
                            gewerk_date = str(item.get("date") or "").strip()
                            gewerk_time = str(item.get("time") or "").strip()
                            if not gewerk_text and not gewerk_date and not gewerk_time:
                                continue
                            if not gewerk_text or not gewerk_date or not gewerk_time:
                                ui.notify("Bitte jedes Gewerk mit Text, Tag und Zeit vollständig angeben.", type="warning")
                                return
                            gewerk_lines.append(f"{gewerk_date} {gewerk_time} | {gewerk_text}")
                        final_status = str(target_status or order_status.value or "in_erstellung")
                        upsert_order_from_form(
                            order_id=int((selected or {}).get("id") or 0) or None,
                            fahrzeug=vehicle_value,
                            friststufe=str(order_frist.value or ""),
                            order_kind=str(order_kind.value or ""),
                            zusatzarbeiten="\n".join(zus_lines),
                            gewerke_info="\n".join(gewerk_lines),
                            ecm3_start_date=str(order_ecm3_start_date.value or ""),
                            ecm3_start_time=str(order_ecm3_start_time.value or ""),
                            ecm3_end_date=str(order_ecm3_end_date.value or ""),
                            ecm3_end_time=str(order_ecm3_end_time.value or ""),
                            required_ma_8h=order_required.value,
                            planned_ma=None,
                            status=final_status,
                        )
                        dialog.close()
                        ui.notify(f'Planungsauftrag als "{_order_status_label(final_status)}" gespeichert.', type="positive")
                        render_order_form.refresh()

                    with ui.row().classes("w-full justify-end gap-2 mt-2"):
                        if selected:
                            ui.button(
                                "Löschen",
                                on_click=lambda: (
                                    remove_order(order_id=int(selected.get("id") or 0)),
                                    dialog.close(),
                                    ui.notify("Planungsauftrag gelöscht.", type="positive"),
                                    render_order_form.refresh(),
                                ),
                            ).props("color=negative").classes("btn-big")
                        ui.button("Abbrechen", on_click=dialog.close).classes("btn-big")
                        ui.button("Speichern", on_click=lambda: _save_dialog(None)).classes("btn-big")
                        ui.button("In Erstellung", on_click=lambda: _save_dialog("in_erstellung")).classes("btn-big")
                        ui.button("In Planung", on_click=lambda: _save_dialog("in_planung")).classes("btn-big")
                dialog.open()

            def _toggle_selected(order_id: int, checked: bool) -> None:
                current = set(state.get("selected_ids", set()))
                if checked:
                    current.add(int(order_id))
                else:
                    current.discard(int(order_id))
                state["selected_ids"] = current
                render_order_form.refresh()

            def _apply_bulk_status(new_status: str) -> None:
                if not selected_ids:
                    ui.notify("Bitte zuerst Aufträge markieren.", type="warning")
                    return
                changed = set_order_statuses(sorted(selected_ids), status=new_status)
                state["selected_ids"] = set()
                ui.notify(f"{len(changed)} Auftrag/Aufträge aktualisiert.", type="positive")
                render_order_form.refresh()

            def _render_order_card(row: dict[str, Any]) -> None:
                order_id = int(row.get("id") or 0)
                with ui.card().classes("upload-panel planning-card planning-page planning-order-item"):
                    with ui.row().classes("w-full items-start gap-2"):
                        checkbox = ui.checkbox(value=order_id in selected_ids).props("dense")
                        checkbox.on_value_change(lambda e, oid=order_id: _toggle_selected(oid, bool(e.value)))
                        with ui.column().classes("grow gap-1"):
                            ui.label(f'{row.get("fahrzeug") or "-"} | {row.get("friststufe") or "-"}').classes("planning-form-item-main")
                            ui.label(_order_status_label(row.get("status"))).classes(
                                f'planning-form-item-status {_order_status_class(row.get("status"))}'
                            )
                            ui.label(_planning_source_label(row.get("source_origin"))).classes("planning-note")
                        ui.button("Bearbeiten", on_click=lambda _=None, oid=order_id: _open_order_dialog(oid)).classes("btn-big")
                    with ui.element("div").classes("planning-form-item-grid"):
                        for label, value in [
                            ("Art", row.get("order_kind") or "-"),
                            ("MA Bedarf", f'{_safe_float(row.get("required_ma_8h")):.1f}'),
                            ("ECM3", f'{row.get("ecm3_start_date") or "-"} {row.get("ecm3_start_time") or ""} -> {row.get("ecm3_end_date") or "-"} {row.get("ecm3_end_time") or ""}'),
                            ("Zusatzarbeiten", row.get("zusatzarbeiten") or "-"),
                        ]:
                            with ui.element("div").classes("planning-form-item-row"):
                                ui.label(label).classes("planning-form-item-label")
                                ui.label(str(value or "-")).classes("planning-form-item-value")
                    with ui.row().classes("w-full gap-2 mt-2 wrap"):
                        if str(row.get("status") or "") != "in_erstellung":
                            ui.button("In Erstellung", on_click=lambda _=None, oid=order_id: (set_order_statuses([oid], status="in_erstellung"), render_order_form.refresh())).classes("btn-big")
                        if str(row.get("status") or "") != "in_planung":
                            ui.button("In Planung", on_click=lambda _=None, oid=order_id: (set_order_statuses([oid], status="in_planung"), render_order_form.refresh())).classes("btn-big")

            with body:
                with ui.row().classes("w-full items-center gap-3 wrap"):
                    ui.button("Neuer Auftrag", on_click=lambda: _open_order_dialog(None)).classes("btn-big")
                    view_mode = ui.toggle({"board": "Board", "list": "Liste"}, value=str(state.get("view_mode") or "board")).props("unelevated toggle-color=primary color=grey-8 text-color=white no-caps")
                    status_filter = ui.select({"all": "Alle", "in_erstellung": "In Erstellung", "in_planung": "In Planung", "freigegeben": "Freigegeben"}, value=str(state.get("status_filter") or "all"), label="Status").props("outlined dense").classes("min-w-[180px]")
                    search_input = ui.input("Suche", value=str(state.get("search_text") or "")).props("outlined dense").classes("grow min-w-[220px]")

                    def _update_controls() -> None:
                        state["view_mode"] = str(view_mode.value or "board")
                        state["status_filter"] = str(status_filter.value or "all")
                        state["search_text"] = str(search_input.value or "")
                        render_order_form.refresh()

                    view_mode.on_value_change(lambda _e: _update_controls())
                    status_filter.on_value_change(lambda _e: _update_controls())
                    search_input.on_value_change(lambda _e: _update_controls())

                with ui.row().classes("w-full gap-3 wrap"):
                    for status_key, label in [("in_erstellung", "In Erstellung"), ("in_planung", "In Planung"), ("freigegeben", "Freigegeben")]:
                        with ui.card().classes("kpi-card"):
                            ui.label(label).classes("text-sm text-white")
                            ui.label(str(status_counts[status_key])).classes("text-3xl font-bold")

                if selected_ids:
                    with ui.card().classes("w-full upload-panel planning-card planning-page"):
                        with ui.row().classes("w-full items-center gap-2 wrap"):
                            ui.label(f"{len(selected_ids)} ausgewählt").classes("planning-section-title")
                            ui.button("In Erstellung", on_click=lambda: _apply_bulk_status("in_erstellung")).classes("btn-big")
                            ui.button("In Planung", on_click=lambda: _apply_bulk_status("in_planung")).classes("btn-big")
                            ui.button("Auswahl aufheben", on_click=lambda: (state.__setitem__("selected_ids", set()), render_order_form.refresh())).classes("btn-big")

                if str(state.get("view_mode") or "board") == "list":
                    with ui.column().classes("w-full gap-2"):
                        if not filtered_orders:
                            ui.label("Keine Aufträge für den aktuellen Filter.").classes("planning-form-empty")
                        for row in filtered_orders:
                            _render_order_card(row)
                else:
                    with ui.element("div").classes("planning-grid-2"):
                        for status_key, title in [("in_erstellung", "In Erstellung"), ("in_planung", "In Planung"), ("freigegeben", "Freigegeben")]:
                            with ui.card().classes("upload-panel planning-card planning-page"):
                                ui.label(f"{title} ({len(status_groups[status_key])})").classes("planning-section-title")
                                if not status_groups[status_key]:
                                    ui.label("Keine Aufträge.").classes("planning-form-empty")
                                else:
                                    for row in status_groups[status_key]:
                                        _render_order_card(row)

        render_order_form()
        return
        state: dict[str, Any] = {"day": date.today().isoformat()}
        body = ui.column().classes("w-full gap-3 planning-page")

        with ui.card().classes("w-full upload-panel planning-card planning-page"):
            ui.label("Planungstag").classes("planning-section-title")
            ui.label("Erste operative Sicht für Aufträge, Slots und Hallenbelegung.").classes("planning-note")
            day_input = ui.input("Datum", value=state["day"]).props("type=date outlined").classes("w-full max-w-[260px] prio-day-input")

        def _current_day() -> str:
            return str(day_input.value or state["day"] or "").strip() or date.today().isoformat()

        @ui.refreshable
        def render_board() -> None:
            body.clear()
            board_day = _current_day()
            orders_data = get_order_board()
            slot_data = get_slot_board(board_day)
            orders = orders_data.get("orders", [])
            slots = slot_data.get("slots", [])
            assignments = slot_data.get("assignments", [])
            places = slot_data.get("places", [])

            order_options = {"": "Bitte Auftrag wählen"}
            for order in orders:
                order_options[str(order["id"])] = f'{order["fahrzeug"]} | {order["friststufe"]}'
            slot_options = {"": "Bitte Slot wählen"}
            for slot in slots:
                slot_options[str(slot["id"])] = f'{slot["slot_date"]} {slot["slot_time"]}'
            place_options = {"": "Bitte Arbeitsplatz wählen"}
            for place in places:
                place_options[str(place["code"])] = str(place["code"])

            with body:
                with ui.element("div").classes("planning-grid-2"):
                    with ui.card().classes("upload-panel planning-card planning-page"):
                        ui.label("Auftragsplanung").classes("planning-section-title")
                        order_fzg, order_vehicle_values = _render_configured_vehicle_select("Fahrzeug")
                        order_frist = ui.input("Friststufe", placeholder="z. B. L2 / IS5").props("outlined").classes("w-full")
                        order_kind = ui.input("Art p / k / URD", placeholder="p").props("outlined").classes("w-full")
                        order_zus = ui.textarea("Zusatzarbeiten").props("outlined").classes("w-full")
                        order_gewerke = ui.input("Gewerke / Hinweis").props("outlined").classes("w-full")
                        with ui.row().classes("w-full gap-2 wrap"):
                            order_ecm3_start_date = ui.input("ECM3 Start Datum").props("type=date outlined").classes("grow min-w-[180px] prio-day-input")
                            order_ecm3_start_time = ui.input("ECM3 Start Zeit").props("type=time outlined").classes("grow min-w-[180px]")
                        with ui.row().classes("w-full gap-2 wrap"):
                            order_ecm3_end_date = ui.input("ECM3 Ende Datum").props("type=date outlined").classes("grow min-w-[180px] prio-day-input")
                            order_ecm3_end_time = ui.input("ECM3 Ende Zeit").props("type=time outlined").classes("grow min-w-[180px]")
                        with ui.row().classes("w-full gap-2 wrap"):
                            order_required = ui.number("Benötigte MA (8h)", value=0, format="%.2f").props("outlined").classes(
                                "grow min-w-[180px]"
                            )
                            order_planned = ui.number("Geplante MA", value=0, format="%.2f").props("outlined").classes(
                                "grow min-w-[180px]"
                            )

                        def _save_order() -> None:
                            vehicle_value = str(order_fzg.value or "").strip()
                            if not vehicle_value or vehicle_value not in order_vehicle_values:
                                ui.notify("Bitte Fahrzeug aus der Konfiguration auswählen.", type="warning")
                                return
                            if not str(order_frist.value or "").strip():
                                ui.notify("Bitte Fahrzeug und Friststufe ausfüllen.", type="warning")
                                return
                            create_order_from_form(
                                fahrzeug=vehicle_value,
                                friststufe=str(order_frist.value or ""),
                                order_kind=str(order_kind.value or ""),
                                zusatzarbeiten=str(order_zus.value or ""),
                                gewerke_info=str(order_gewerke.value or ""),
                                ecm3_start_date=str(order_ecm3_start_date.value or ""),
                                ecm3_start_time=str(order_ecm3_start_time.value or ""),
                                ecm3_end_date=str(order_ecm3_end_date.value or ""),
                                ecm3_end_time=str(order_ecm3_end_time.value or ""),
                                required_ma_8h=order_required.value,
                                planned_ma=order_planned.value,
                            )
                            ui.notify("Planungsauftrag gespeichert.", type="positive")
                            render_board.refresh()

                        ui.button("Planungsauftrag speichern", on_click=_save_order).classes("btn-big mt-2")

                    with ui.card().classes("upload-panel planning-card planning-page"):
                        ui.label("Slot anlegen").classes("planning-section-title")
                        slot_date = ui.input("Slot-Datum", value=board_day).props("type=date outlined").classes("w-full prio-day-input")
                        slot_time = ui.input("Slot-Zeit", placeholder="06:00").props("type=time outlined").classes("w-full")
                        with ui.row().classes("w-full gap-2 wrap"):
                            workshop_staff = ui.number("Werkstatt", value=0, format="%.2f").props("outlined").classes(
                                "grow min-w-[120px]"
                            )
                            service_staff = ui.number("Service", value=0, format="%.2f").props("outlined").classes(
                                "grow min-w-[120px]"
                            )
                            urd_staff = ui.number("URD", value=0, format="%.2f").props("outlined").classes("grow min-w-[120px]")
                        with ui.row().classes("w-full gap-2 wrap"):
                            mek_value = ui.number("MEK", value=0, format="%.2f").props("outlined").classes("grow min-w-[120px]")
                            vehicle_count = ui.number("Anzahl Fzg.", value=0, format="%.2f").props("outlined").classes(
                                "grow min-w-[120px]"
                            )
                            staff_per_vehicle = ui.number("MA je Fzg.", value=0, format="%.2f").props("outlined").classes(
                                "grow min-w-[120px]"
                            )
                        slot_notes = ui.input("Hinweis").props("outlined").classes("w-full")

                        def _save_slot() -> None:
                            if not str(slot_date.value or "").strip() or not str(slot_time.value or "").strip():
                                ui.notify("Bitte Datum und Slot-Zeit angeben.", type="warning")
                                return
                            create_slot(
                                slot_date=str(slot_date.value or ""),
                                slot_time=str(slot_time.value or ""),
                                workshop_staff=workshop_staff.value,
                                service_staff=service_staff.value,
                                urd_staff=urd_staff.value,
                                mek_value=mek_value.value,
                                vehicle_count=vehicle_count.value,
                                staff_per_vehicle=staff_per_vehicle.value,
                                notes=str(slot_notes.value or ""),
                            )
                            ui.notify("Slot gespeichert.", type="positive")
                            render_board.refresh()

                        ui.button("Slot speichern", on_click=_save_slot).classes("btn-big mt-2")

                with ui.card().classes("w-full upload-panel planning-card planning-page"):
                    ui.label("Auftrag einem Slot zuweisen").classes("planning-section-title")
                    with ui.row().classes("w-full gap-2 wrap"):
                        assignment_order = ui.select(order_options, value="", label="Auftrag").props("outlined dense").classes(
                            "grow min-w-[220px]"
                        )
                        assignment_slot = ui.select(slot_options, value="", label="Slot").props("outlined dense").classes(
                            "grow min-w-[220px]"
                        )
                        assignment_place = ui.select(place_options, value="", label="Arbeitsplatz").props("outlined dense").classes(
                            "grow min-w-[220px]"
                        )
                    assignment_note = ui.input("Hinweis").props("outlined").classes("w-full")

                    def _save_assignment() -> None:
                        raw_order = str(assignment_order.value or "").strip()
                        raw_slot = str(assignment_slot.value or "").strip()
                        raw_place = str(assignment_place.value or "").strip()
                        if not raw_order or not raw_slot or not raw_place:
                            ui.notify("Bitte Auftrag, Slot und Arbeitsplatz wählen.", type="warning")
                            return
                        order_row = next((row for row in orders if str(row["id"]) == raw_order), None)
                        if order_row is None:
                            ui.notify("Der gewählte Auftrag wurde nicht gefunden.", type="warning")
                            return
                        assign_order_to_slot(
                            planning_order_id=int(raw_order),
                            slot_id=int(raw_slot),
                            place_code=raw_place,
                            fahrzeug=str(order_row.get("fahrzeug") or ""),
                            note=str(assignment_note.value or ""),
                        )
                        ui.notify("Auftrag dem Slot zugewiesen.", type="positive")
                        render_board.refresh()

                    ui.button("Zuweisung speichern", on_click=_save_assignment).classes("btn-big mt-2")

                with ui.element("div").classes("planning-grid-2"):
                    with ui.card().classes("upload-panel planning-card planning-page planning-table-card"):
                        ui.label(f"Planungsaufträge ({len(orders)})").classes("planning-section-title")
                        order_rows = [
                            {
                                **row,
                                "zeitfenster": f'{row.get("ecm3_start_date") or "-"} {row.get("ecm3_start_time") or ""} -> {row.get("ecm3_end_date") or "-"} {row.get("ecm3_end_time") or ""}',
                                "ecm4_platz": row.get("ecm4_place_code") or "-",
                            }
                            for row in orders
                        ]
                        order_columns = [
                            {"name": "fahrzeug", "label": "Fahrzeug", "field": "fahrzeug"},
                            {"name": "friststufe", "label": "Friststufe", "field": "friststufe"},
                            {"name": "order_kind", "label": "Art", "field": "order_kind"},
                            {"name": "required_ma_8h", "label": "MA Bedarf", "field": "required_ma_8h"},
                            {"name": "planned_ma", "label": "MA Geplant", "field": "planned_ma"},
                            {"name": "zeitfenster", "label": "ECM3 Zeitfenster", "field": "zeitfenster"},
                            {"name": "status", "label": "Status", "field": "status"},
                        ]
                        ui.table(columns=order_columns, rows=order_rows, row_key="id").classes("w-full upload-preview-table")

                    with ui.card().classes("upload-panel planning-card planning-page planning-table-card"):
                        ui.label(f"Slots und Belegung am {board_day}").classes("planning-section-title")
                        assignment_map = {}
                        for row in assignments:
                            slot_key = f'{row.get("slot_date")} {row.get("slot_time")}'
                            assignment_map[(slot_key, str(row.get("place_code") or ""))] = str(row.get("fahrzeug") or "") or "belegt"
                        slot_rows: list[dict[str, Any]] = []
                        for slot in slots:
                            slot_key = f'{slot.get("slot_date")} {slot.get("slot_time")}'
                            slot_row = {
                                "slot_key": slot_key,
                                "slot_time": slot.get("slot_time"),
                                "workshop_staff": slot.get("workshop_staff"),
                                "service_staff": slot.get("service_staff"),
                                "urd_staff": slot.get("urd_staff"),
                                "vehicle_count": slot.get("vehicle_count"),
                            }
                            for place in places:
                                place_code = str(place.get("code") or "")
                                slot_row[f"place_{place_code}"] = assignment_map.get((slot_key, place_code), "")
                            slot_rows.append(slot_row)
                        slot_columns = [
                            {"name": "slot_time", "label": "Slot", "field": "slot_time"},
                            {"name": "workshop_staff", "label": "Werkstatt", "field": "workshop_staff"},
                            {"name": "service_staff", "label": "Service", "field": "service_staff"},
                            {"name": "urd_staff", "label": "URD", "field": "urd_staff"},
                            {"name": "vehicle_count", "label": "Fzg.", "field": "vehicle_count"},
                        ]
                        for place in places:
                            place_code = str(place.get("code") or "")
                            slot_columns.append({"name": f"place_{place_code}", "label": place_code, "field": f"place_{place_code}"})
                        ui.table(columns=slot_columns, rows=slot_rows, row_key="slot_key").classes("w-full upload-preview-table")

        day_input.on_value_change(lambda _e: render_board.refresh())
        render_board()
