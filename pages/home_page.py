from __future__ import annotations

from typing import Callable

from nicegui import ui


def render(
    *,
    render_nav: Callable[[], None],
    is_admin: Callable[[], bool],
    is_configuration_user: Callable[[], bool],
) -> None:
    render_nav()
    admin_active = is_admin()
    configuration_active = is_configuration_user()
    ui.label("Fristenplanung - Start").classes("page-title")
    ui.label("Schnellzugriff auf alle Bereiche").classes("text-gray-300")
    with ui.column().classes("w-full gap-4 mt-4"):
        ui.button("Offene Aufträge", icon="assignment", on_click=lambda: ui.navigate.to("/offen")).classes("home-btn")
        ui.button("Werkstatthalle", icon="build", on_click=lambda: ui.navigate.to("/werkstatthalle")).classes("home-btn")
        ui.button("Gleisplan", icon="route", on_click=lambda: ui.navigate.to("/gleisplan")).classes("home-btn")
        ui.button("Tagesplanung", icon="star", on_click=lambda: ui.navigate.to("/tagesplanung")).classes("home-btn")
        ui.button("Wochenplanung", icon="calendar_month", on_click=lambda: ui.navigate.to("/wochenplanung")).classes("home-btn")
        ui.button("5S-Plan", icon="factory", on_click=lambda: ui.navigate.to("/shopfloorboard")).classes("home-btn")
        if configuration_active:
            ui.button("Konfiguration", icon="settings", on_click=lambda: ui.navigate.to("/konfiguration")).classes("home-btn")
        if admin_active:
            ui.button("Planung", icon="event_note", on_click=lambda: ui.navigate.to("/planung")).classes("home-btn")
            ui.button("Archiv", icon="inventory_2", on_click=lambda: ui.navigate.to("/archiv")).classes("home-btn")
