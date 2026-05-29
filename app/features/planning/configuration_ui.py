from __future__ import annotations

from typing import Any, Callable

from nicegui import ui

from .service import (
    get_planner_configuration,
    save_planner_configuration,
    save_planner_ui_settings,
)


def _safe_float(value: Any) -> float:
    try:
        if isinstance(value, str):
            cleaned = value.strip().replace(",", ".")
            return float(cleaned or 0)
        return float(value or 0)
    except Exception:
        return 0.0


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


def _normalize_role_key(value: Any) -> str:
    raw = str(value or "").strip().lower()
    cleaned = "".join(char if char.isalnum() else "_" for char in raw)
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_")


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


def _weekday_labels_de() -> list[str]:
    return ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


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


def render_planner_configuration_form(
    *,
    on_saved: Callable[[], None] | None = None,
    on_cancel: Callable[[], None] | None = None,
    cancel_label: str = "Abbrechen",
) -> None:
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
        ui.notify("Planner-Konfiguration gespeichert.", type="positive")
        if on_saved:
            on_saved()

    with ui.row().classes("w-full justify-end gap-2"):
        if on_cancel:
            ui.button(cancel_label, on_click=on_cancel).classes("btn-big")
        ui.button("Speichern", on_click=_save_config).classes("btn-big")
