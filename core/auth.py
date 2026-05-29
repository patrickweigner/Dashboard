from __future__ import annotations

from typing import Any

from nicegui import app, ui

from core.config import (
    ADMIN_ROLE_STORAGE_KEY,
    LOGIN_USERNAME_STORAGE_KEY,
    ROLE_ADMIN_FULL,
    ROLE_ADMIN_SL,
    ROLE_ADMIN_WL,
    ROLE_STANDARD,
)

LOGIN_PERMISSIONS_STORAGE_KEY = "login_permissions"


def _is_admin_role(role: str) -> bool:
    return role in {ROLE_ADMIN_FULL, ROLE_ADMIN_SL, ROLE_ADMIN_WL}


def _has_login_passwords() -> bool:
    try:
        from services.user_management_service import has_users

        return bool(has_users())
    except Exception:
        return False


def _resolve_login_role(raw_password: str, username: str | None = None) -> dict[str, Any] | str | None:
    raw = str(raw_password or "").strip()
    if not raw:
        return None
    user_name = str(username or "").strip()
    if not user_name:
        return None
    try:
        from services.user_management_service import verify_login

        user = verify_login(user_name, raw)
        if user:
            return {
                "role": str(user.get("role") or ROLE_STANDARD),
                "username": str(user.get("username") or user_name),
                "permissions": dict(user.get("permissions") or {}),
            }
    except Exception:
        pass
    return None


def _login_success_text(role: str) -> str:
    if role == ROLE_ADMIN_FULL:
        return "Login aktiviert (Vollzugriff)."
    if role == ROLE_ADMIN_WL:
        return "Login aktiviert (Werkstattleitung, Archiv-Rückholung erlaubt)."
    if role == ROLE_ADMIN_SL:
        return "Login aktiviert (Schichtleitung)."
    return "Login aktiviert."


def _read_admin_role() -> str:
    try:
        role = str(app.storage.user.get(ADMIN_ROLE_STORAGE_KEY, "") or "").strip()
    except Exception:
        return ROLE_STANDARD
    return role if _is_admin_role(role) else ROLE_STANDARD


def current_role() -> str:
    return _read_admin_role()


def current_username() -> str:
    try:
        return str(app.storage.user.get(LOGIN_USERNAME_STORAGE_KEY, "") or "").strip()
    except Exception:
        return ""


def current_permissions() -> dict[str, bool]:
    try:
        raw = app.storage.user.get(LOGIN_PERMISSIONS_STORAGE_KEY, {}) or {}
    except Exception:
        return {}
    return dict(raw) if isinstance(raw, dict) else {}


def _standard_access_permissions() -> dict[str, bool]:
    try:
        from services.user_management_service import get_standard_access_permissions

        return dict(get_standard_access_permissions())
    except Exception:
        return {}


def can_view_page(page_key: str) -> bool:
    page = str(page_key or "").strip()
    permissions = current_permissions() or _standard_access_permissions()
    if permissions:
        try:
            from services.user_management_service import VIEW_PERMISSION_BY_PAGE

            permission_key = VIEW_PERMISSION_BY_PAGE.get(page)
        except Exception:
            permission_key = None
        return True if permission_key is None else bool(permissions.get(permission_key, False))
    return False


def can_edit_page(page_key: str) -> bool:
    page = str(page_key or "").strip()
    permissions = current_permissions() or _standard_access_permissions()
    if permissions:
        try:
            from services.user_management_service import EDIT_PERMISSION_BY_PAGE

            permission_key = EDIT_PERMISSION_BY_PAGE.get(page)
        except Exception:
            permission_key = None
        return True if permission_key is None else bool(permissions.get(permission_key, False))
    return False


def is_configuration_user() -> bool:
    return current_username().casefold() == "odigew" or can_view_page("configuration")


def is_admin() -> bool:
    return _is_admin_role(current_role())


def is_full_admin() -> bool:
    return current_role() == ROLE_ADMIN_FULL


def can_use_delete_functions() -> bool:
    return is_full_admin()


def can_delete_recent_done_functions() -> bool:
    return current_role() in {ROLE_ADMIN_FULL, ROLE_ADMIN_WL}


def _set_admin(
    active: bool,
    role: str = ROLE_ADMIN_FULL,
    username: str | None = None,
    permissions: dict[str, bool] | None = None,
) -> None:
    try:
        user_storage = app.storage.user
    except Exception:
        return
    if active:
        role_value = role if role in {ROLE_ADMIN_FULL, ROLE_ADMIN_SL, ROLE_ADMIN_WL} else ROLE_ADMIN_FULL
        user_storage[ADMIN_ROLE_STORAGE_KEY] = role_value
        user_name = str(username or "").strip()
        if user_name:
            user_storage[LOGIN_USERNAME_STORAGE_KEY] = user_name
        else:
            user_storage.pop(LOGIN_USERNAME_STORAGE_KEY, None)
        if permissions:
            user_storage[LOGIN_PERMISSIONS_STORAGE_KEY] = dict(permissions)
        else:
            user_storage.pop(LOGIN_PERMISSIONS_STORAGE_KEY, None)
    else:
        user_storage.pop(ADMIN_ROLE_STORAGE_KEY, None)
        user_storage.pop(LOGIN_USERNAME_STORAGE_KEY, None)
        user_storage.pop(LOGIN_PERMISSIONS_STORAGE_KEY, None)


def _logout_admin() -> None:
    _set_admin(False)
    ui.notify("Admin abgemeldet.", type="positive")
    ui.navigate.reload()


def _enforce_admin_uncheck_rule(old_bits: list[bool], new_bits: list[bool], *, admin: bool) -> tuple[list[bool], bool]:
    n = max(len(old_bits), len(new_bits))
    out: list[bool] = []
    blocked = False
    for i in range(n):
        old_v = bool(old_bits[i]) if i < len(old_bits) else False
        new_v = bool(new_bits[i]) if i < len(new_bits) else False
        if (not admin) and old_v and (not new_v):
            out.append(True)
            blocked = True
        else:
            out.append(new_v)
    return out, blocked
