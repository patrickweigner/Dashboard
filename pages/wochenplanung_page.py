from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable

from nicegui import ui

from core.ui_runtime import create_page_timer


def render(
    *,
    render_nav: Callable[[], None],
    now_berlin: Callable[[], datetime],
    build_weekly_main_area_plan: Callable[[date], dict[str, list[dict[str, Any]]]],
    build_weekly_side_area_plan: Callable[[date], dict[str, list[dict[str, Any]]]],
    refresh_when_no_dialog: Callable[[Callable[[], None]], None],
) -> None:
    render_nav()
    today = now_berlin().date()
    iso = today.isocalendar()
    iso_year = int(iso.year)
    iso_week = int(iso.week)
    week_start = date.fromisocalendar(iso_year, iso_week, 1)
    week_end = date.fromisocalendar(iso_year, iso_week, 7)
    state: dict[str, str] = {"view": "main"}

    with ui.row().classes("w-full items-center gap-3 wrap"):
        ui.label("🗓️ Wochenplanung").classes("page-title")
        view_toggle = ui.toggle(
            {
                "main": "4A / 4B / 5A / 5B",
                "side": "ARA / URD / RWS",
            },
            value=state["view"],
        ).props("unelevated toggle-color=primary color=grey-8 text-color=white no-caps")
        ui.label(f"KW {iso_week:02d} ({week_start:%d.%m.%Y} - {week_end:%d.%m.%Y})").classes("weekplan-week-label")

    body = ui.column().classes("w-full gap-2 week-plan-page")

    @ui.refreshable
    def content() -> None:
        if str(state.get("view") or "main") == "side":
            week_plan = build_weekly_side_area_plan(week_start)
            area_order = ["ARA", "URD", "RWS"]
        else:
            week_plan = build_weekly_main_area_plan(week_start)
            area_order = ["5A", "5B", "4A", "4B"]

        body.clear()
        with body:
            with ui.element("div").classes("weekplan-grid"):
                for area_code in area_order:
                    area_days = week_plan.get(area_code) or []
                    with ui.card().classes("weekplan-card"):
                        with ui.row().classes("w-full items-center justify-between gap-2 weekplan-card-head"):
                            ui.label(area_code).classes("weekplan-area")
                        with ui.element("div").classes("weekplan-days"):
                            for day in area_days:
                                day_cls = "weekplan-day weekplan-day-today" if bool(day.get("is_today")) else "weekplan-day"
                                with ui.element("div").classes(day_cls):
                                    ui.label(str(day.get("day_name") or "")).classes("weekplan-day-name")
                                    ui.label(str(day.get("date_label") or "")).classes("weekplan-day-date")
                                    with ui.column().classes("w-full gap-2"):
                                        for slot in day.get("slots") or []:
                                            slot_cls = (
                                                "weekplan-slot weekplan-slot-busy"
                                                if bool(slot.get("occupied"))
                                                else "weekplan-slot weekplan-slot-free"
                                            )
                                            with ui.element("div").classes(slot_cls):
                                                ui.label(str(slot.get("label") or "")).classes("weekplan-slot-time")
                                                ui.label(str(slot.get("vehicle") or "")).classes("weekplan-slot-main")
                                                ui.label(str(slot.get("frist") or "")).classes("weekplan-slot-sub")

    def _on_view_change(e) -> None:
        state["view"] = str(e.value or "main")
        content.refresh()

    view_toggle.on_value_change(_on_view_change)
    content()
    create_page_timer(60.0, lambda: refresh_when_no_dialog(content.refresh))
