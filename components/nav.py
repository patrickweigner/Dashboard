from __future__ import annotations

from typing import Any, Callable

from nicegui import ui


def render_nav(
    *,
    ensure_problem_state: Callable[[], None],
    ensure_overdue_state: Callable[[], None],
    auto_clear_shopfloorboard_5s_if_due: Callable[[], None],
    start_lwu_reminder_worker: Callable[[], None],
    is_admin: Callable[[], bool],
    is_configuration_user: Callable[[], bool],
    can_view_page: Callable[[str], bool],
    has_login_passwords: Callable[[], bool],
    logout_admin: Callable[[], None],
    open_admin_login_dialog: Callable[[], None],
    show_db_path_in_nav: bool,
    db_path: str,
    btn_bg: str,
) -> None:
    ensure_problem_state()
    ensure_overdue_state()
    ui.colors(
        primary=btn_bg,
        secondary="#262730",
        accent="#0d6efd",
        dark="#0e1117",
        positive="#52c41a",
        negative="#ff4d4f",
        warning="#faad14",
        info="#31ccec",
    )
    auto_clear_shopfloorboard_5s_if_due()
    start_lwu_reminder_worker()
    admin_active = is_admin()
    configuration_active = is_configuration_user()
    with ui.row().classes("w-full items-center gap-2 nav-row"):
        if can_view_page("home"):
            ui.button("Start", icon="home", on_click=lambda: ui.navigate.to("/")).classes("nav-btn")
        if can_view_page("open_tasks"):
            ui.button("Offene Aufträge", icon="assignment", on_click=lambda: ui.navigate.to("/offen")).classes("nav-btn")
        if can_view_page("werkstatthalle"):
            ui.button("Werkstatthalle", icon="build", on_click=lambda: ui.navigate.to("/werkstatthalle")).classes("nav-btn")
        if can_view_page("gleisplan"):
            ui.button("Gleisplan", icon="route", on_click=lambda: ui.navigate.to("/gleisplan")).classes("nav-btn")
        if can_view_page("priorisierung"):
            ui.button("Tagesplanung", icon="star", on_click=lambda: ui.navigate.to("/tagesplanung")).classes("nav-btn")
        if can_view_page("wochenplanung"):
            ui.button("Wochenplanung", icon="calendar_month", on_click=lambda: ui.navigate.to("/wochenplanung")).classes("nav-btn")
        if can_view_page("shopfloorboard"):
            ui.button("5S-Plan", icon="factory", on_click=lambda: ui.navigate.to("/shopfloorboard")).classes("nav-btn")
        if configuration_active and can_view_page("configuration"):
            ui.button("Konfiguration", icon="settings", on_click=lambda: ui.navigate.to("/konfiguration")).classes("nav-btn")
        if admin_active and can_view_page("planning"):
            ui.button("Planung", icon="event_note", on_click=lambda: ui.navigate.to("/planung")).classes("nav-btn")
        if can_view_page("upload"):
            ui.button("Upload", icon="upload_file", on_click=lambda: ui.navigate.to("/upload")).classes("nav-btn")
        if can_view_page("archive"):
            ui.button("Archiv", icon="inventory_2", on_click=lambda: ui.navigate.to("/archiv")).classes("nav-btn")
        ui.space()
        if has_login_passwords():
            if admin_active:
                ui.button("Logout", icon="logout", on_click=logout_admin).classes("nav-btn nav-btn-admin")
            else:
                ui.button("Login", icon="login", on_click=lambda: open_admin_login_dialog()).classes("nav-btn nav-btn-admin")
        else:
            ui.label("Keine Nutzer angelegt").classes("text-xs text-amber-3")
        if show_db_path_in_nav:
            ui.label(f"DB: {db_path}").classes("text-xs text-gray-300")


def open_admin_login_dialog(
    *,
    attach_dialog_tracking: Callable[[Any], None],
    close_tracked_dialog: Callable[[Any], None],
    has_login_passwords: Callable[[], bool],
    resolve_login_role: Callable[..., Any],
    set_admin: Callable[..., None],
    login_success_text: Callable[[str], str],
    open_tracked_dialog: Callable[[Any], None],
    on_success: Callable[[], None] | None = None,
    reload_on_success: bool = True,
    title: str = "Login",
    hint: str | None = None,
) -> None:
    with ui.dialog() as dialog, ui.card().classes("dialog-card"):
        attach_dialog_tracking(dialog)
        dialog.props("persistent")
        ui.label(title).classes("dialog-title")
        if hint:
            ui.label(hint).classes("text-sm text-gray-300")
        username = ui.input("Name").props("outlined").classes("w-full admin-login-input")
        pw = ui.input("Passwort").props("outlined type=password").classes("w-full admin-login-input")
        with ui.row().classes("w-full justify-end gap-2 mt-3"):
            ui.button("Abbrechen", on_click=lambda d=dialog: close_tracked_dialog(d)).props("flat").classes(
                "admin-login-cancel"
            )

            def do_login() -> None:
                raw = str(pw.value or "").strip()
                user_name = str(username.value or "").strip()
                resolved = resolve_login_role(raw, user_name)
                if not has_login_passwords():
                    ui.notify("Keine aktiven Nutzer angelegt.", type="warning")
                    return
                if isinstance(resolved, dict):
                    role = str(resolved.get("role") or "")
                    resolved_username = str(resolved.get("username") or user_name).strip()
                    permissions = dict(resolved.get("permissions") or {})
                else:
                    role = str(resolved or "")
                    resolved_username = user_name
                    permissions = {}
                if role:
                    set_admin(True, role, resolved_username, permissions)
                    ui.notify(login_success_text(role), type="positive")
                    close_tracked_dialog(dialog)
                    if on_success is not None:
                        on_success()
                    elif reload_on_success:
                        ui.navigate.reload()
                else:
                    ui.notify("Falscher Benutzer oder falsches Passwort.", type="negative")

            ui.button("Login", on_click=do_login).props("color=primary")
    open_tracked_dialog(dialog)
