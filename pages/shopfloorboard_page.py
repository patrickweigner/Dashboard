from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable, Iterable

from nicegui import ui


def render(
    *,
    render_nav: Callable[[], None],
    now_berlin: Callable[[], datetime],
    get_shopfloorboard_5s_week: Callable[[int, int], dict[str, str]],
    save_shopfloorboard_5s_week: Callable[..., None],
    shopfloor_week_tasks: Iterable[str],
) -> None:
    render_nav()
    ui.label("5S-Plan").classes("page-title")

    today = now_berlin().date()
    iso = today.isocalendar()
    iso_year = int(iso.year)
    iso_week = int(iso.week)
    week_start = date.fromisocalendar(iso_year, iso_week, 1)
    week_end = date.fromisocalendar(iso_year, iso_week, 7)
    values = get_shopfloorboard_5s_week(iso_year, iso_week)

    ui.label(f"KW {iso_week:02d} ({week_start:%d.%m.%Y} - {week_end:%d.%m.%Y})").classes("shop-week-label")

    shift_defs = [
        ("Frühschicht", "fruehschicht", "#93c47d"),
        ("Spätschicht", "spaetschicht", "#ffd966"),
        ("Nachtschicht", "nachtschicht", "#6fa8dc"),
    ]
    shift_inputs: dict[str, Any] = {}

    with ui.card().classes("shop-card w-full"):
        with ui.column().classes("w-full gap-3"):
            for label, field, color in shift_defs:
                with ui.row().classes("w-full items-center gap-3 shop-shift-row"):
                    ui.label(label).classes("shop-shift-label").style(f"color:{color};")
                    inp = ui.input(value=values.get(field, "")).props("outlined").classes("grow shop-shift-input")
                    shift_inputs[field] = inp

        def save_week() -> None:
            save_shopfloorboard_5s_week(
                iso_year=iso_year,
                iso_week=iso_week,
                fruehschicht=str(shift_inputs["fruehschicht"].value or ""),
                spaetschicht=str(shift_inputs["spaetschicht"].value or ""),
                nachtschicht=str(shift_inputs["nachtschicht"].value or ""),
            )
            ui.notify("5S-Wochenplan gespeichert.", type="positive")

        ui.button("Speichern", on_click=save_week).props("color=primary").classes("btn-big mt-2")

    with ui.card().classes("shop-card w-full"):
        ui.label("Aufgaben der 5S Paten").classes("shop-title")
        for txt in shopfloor_week_tasks:
            ui.label(f"- {txt}").classes("shop-task")
