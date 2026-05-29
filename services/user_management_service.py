from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import datetime
from typing import Any

from core import db as db_core
from core.config import ROLE_ADMIN_FULL, ROLE_ADMIN_SL, ROLE_ADMIN_WL, ROLE_STANDARD

STANDARD_ACCESS_USERNAME = "__standard_access__"


ROLE_OPTIONS: dict[str, str] = {
    ROLE_STANDARD: "Standard",
    ROLE_ADMIN_SL: "Schichtleitung",
    ROLE_ADMIN_WL: "Werkstattleitung",
    ROLE_ADMIN_FULL: "Vollzugriff",
}

PERMISSION_OPTIONS: dict[str, str] = {
    "view_home": "Start sehen",
    "view_open_tasks": "Offene Aufträge sehen",
    "edit_open_tasks": "Offene Aufträge bearbeiten",
    "view_werkstatthalle": "Werkstatthalle sehen",
    "edit_werkstatthalle": "Werkstatthalle bearbeiten",
    "view_gleisplan": "Gleisplan sehen",
    "edit_gleisplan": "Gleisplan bearbeiten",
    "view_priorisierung": "Tagesplanung sehen",
    "edit_priorisierung": "Tagesplanung bearbeiten",
    "view_wochenplanung": "Wochenplanung sehen",
    "edit_wochenplanung": "Wochenplanung bearbeiten",
    "view_shopfloorboard": "5S-Plan sehen",
    "edit_shopfloorboard": "5S-Plan bearbeiten",
    "view_upload": "Upload sehen",
    "edit_upload": "Upload bearbeiten",
    "view_archive": "Archiv sehen",
    "edit_archive": "Archiv bearbeiten",
    "view_archive_14d": "Archiv-Rückholung sehen",
    "edit_archive_14d": "Archiv-Rückholung bearbeiten",
    "view_configuration": "Konfiguration sehen",
    "edit_configuration": "Konfiguration bearbeiten",
}

VIEW_PERMISSION_BY_PAGE: dict[str, str] = {
    "home": "view_home",
    "open_tasks": "view_open_tasks",
    "werkstatthalle": "view_werkstatthalle",
    "gleisplan": "view_gleisplan",
    "priorisierung": "view_priorisierung",
    "wochenplanung": "view_wochenplanung",
    "shopfloorboard": "view_shopfloorboard",
    "upload": "view_upload",
    "archive": "view_archive",
    "archive_14d": "view_archive_14d",
    "configuration": "view_configuration",
    "planning": "view_configuration",
}

EDIT_PERMISSION_BY_PAGE: dict[str, str] = {
    "open_tasks": "edit_open_tasks",
    "werkstatthalle": "edit_werkstatthalle",
    "gleisplan": "edit_gleisplan",
    "priorisierung": "edit_priorisierung",
    "wochenplanung": "edit_wochenplanung",
    "shopfloorboard": "edit_shopfloorboard",
    "upload": "edit_upload",
    "archive": "edit_archive",
    "archive_14d": "edit_archive_14d",
    "configuration": "edit_configuration",
    "planning": "edit_configuration",
}

_ROLE_DEFAULT_PERMISSIONS: dict[str, dict[str, bool]] = {
    ROLE_STANDARD: {
        "view_home": True,
        "view_open_tasks": True,
        "view_werkstatthalle": True,
        "view_gleisplan": True,
        "view_priorisierung": True,
        "view_wochenplanung": True,
        "view_shopfloorboard": True,
    },
    ROLE_ADMIN_SL: {
        "view_home": True,
        "view_open_tasks": True,
        "edit_open_tasks": True,
        "view_werkstatthalle": True,
        "edit_werkstatthalle": True,
        "view_gleisplan": True,
        "edit_gleisplan": True,
        "view_priorisierung": True,
        "edit_priorisierung": True,
        "view_wochenplanung": True,
        "edit_wochenplanung": True,
        "view_shopfloorboard": True,
        "edit_shopfloorboard": True,
    },
    ROLE_ADMIN_WL: {},
    ROLE_ADMIN_FULL: {},
}
_ROLE_DEFAULT_PERMISSIONS[ROLE_ADMIN_WL] = {key: True for key in PERMISSION_OPTIONS}
_ROLE_DEFAULT_PERMISSIONS[ROLE_ADMIN_FULL] = {key: True for key in PERMISSION_OPTIONS}


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _clean_username(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _clean_role(value: Any) -> str:
    role = str(value or ROLE_STANDARD).strip()
    return role if role in ROLE_OPTIONS else ROLE_STANDARD


def _ensure_user_schema() -> None:
    db_core.db_exec(
        """
        CREATE TABLE IF NOT EXISTS app_users (
            username         TEXT PRIMARY KEY,
            display_name     TEXT,
            password_hash    TEXT NOT NULL,
            password_plain   TEXT DEFAULT '',
            role             TEXT NOT NULL DEFAULT 'standard',
            permissions_json TEXT NOT NULL DEFAULT '{}',
            active           INTEGER NOT NULL DEFAULT 1,
            updated_at       TEXT
        );
        """,
        commit=True,
    )
    db_core.ensure_column("app_users", "password_plain", "TEXT DEFAULT ''")


def _hash_password(password: str, *, salt: bytes | None = None, iterations: int = 240_000) -> str:
    raw = str(password or "")
    if not raw:
        raise ValueError("Bitte ein Passwort eintragen.")
    salt_bytes = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", raw.encode("utf-8"), salt_bytes, int(iterations))
    return "pbkdf2_sha256${}${}${}".format(
        int(iterations),
        base64.b64encode(salt_bytes).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def _verify_password(password: str, stored_hash: str) -> bool:
    raw = str(password or "")
    stored = str(stored_hash or "")
    if not raw or not stored:
        return False
    try:
        algorithm, iterations_raw, salt_raw, digest_raw = stored.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_raw)
        salt = base64.b64decode(salt_raw.encode("ascii"))
        expected = base64.b64decode(digest_raw.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", raw.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def normalize_permissions(role: str, permissions: Any) -> dict[str, bool]:
    role_key = _clean_role(role)
    base = dict(_ROLE_DEFAULT_PERMISSIONS.get(role_key) or {})
    raw = permissions if isinstance(permissions, dict) else {}
    for key in PERMISSION_OPTIONS:
        if key in raw:
            base[key] = bool(raw.get(key))
        else:
            base[key] = bool(base.get(key, False))
    return base


def _decode_permissions(value: Any, role: str) -> dict[str, bool]:
    try:
        decoded = json.loads(str(value or "{}"))
    except Exception:
        decoded = {}
    return normalize_permissions(role, decoded if isinstance(decoded, dict) else {})


def list_users() -> list[dict[str, Any]]:
    _ensure_user_schema()
    rows = db_core.db_exec(
        """
        SELECT username, display_name, password_plain, role, permissions_json, active, updated_at
        FROM app_users
        WHERE username<>?
        ORDER BY lower(username) ASC;
        """,
        (STANDARD_ACCESS_USERNAME,),
        fetch=True,
    ) or []
    out: list[dict[str, Any]] = []
    for row in rows:
        role = _clean_role(row["role"])
        out.append(
            {
                "username": str(row["username"] or ""),
                "display_name": str(row["display_name"] or ""),
                "password_plain": str(row["password_plain"] or ""),
                "role": role,
                "role_label": ROLE_OPTIONS.get(role, role),
                "permissions": _decode_permissions(row["permissions_json"], role),
                "active": bool(row["active"]),
                "updated_at": str(row["updated_at"] or ""),
            }
        )
    return out


def get_user(username: Any) -> dict[str, Any] | None:
    _ensure_user_schema()
    clean = _clean_username(username)
    if not clean:
        return None
    row = db_core.db_exec(
        """
        SELECT username, display_name, password_hash, password_plain, role, permissions_json, active, updated_at
        FROM app_users
        WHERE lower(trim(username))=lower(trim(?))
        LIMIT 1;
        """,
        (clean,),
        fetchone=True,
    )
    if not row:
        return None
    role = _clean_role(row["role"])
    return {
        "username": str(row["username"] or ""),
        "display_name": str(row["display_name"] or ""),
        "password_hash": str(row["password_hash"] or ""),
        "password_plain": str(row["password_plain"] or ""),
        "role": role,
        "role_label": ROLE_OPTIONS.get(role, role),
        "permissions": _decode_permissions(row["permissions_json"], role),
        "active": bool(row["active"]),
        "updated_at": str(row["updated_at"] or ""),
    }


def has_users() -> bool:
    _ensure_user_schema()
    row = db_core.db_exec(
        "SELECT COUNT(*) AS user_count FROM app_users WHERE active=1 AND username<>?;",
        (STANDARD_ACCESS_USERNAME,),
        fetchone=True,
    )
    try:
        return int(row["user_count"] or 0) > 0 if row else False
    except Exception:
        return False


def verify_login(username: Any, password: Any) -> dict[str, Any] | None:
    if _clean_username(username) == STANDARD_ACCESS_USERNAME:
        return None
    user = get_user(username)
    if not user or not bool(user.get("active")):
        return None
    if not _verify_password(str(password or ""), str(user.get("password_hash") or "")):
        return None
    return user


def save_user(
    *,
    username: str,
    original_username: str | None = None,
    password: str | None = None,
    display_name: str = "",
    role: str = ROLE_STANDARD,
    permissions: dict[str, bool] | None = None,
    active: bool = True,
) -> str:
    _ensure_user_schema()
    clean = _clean_username(username)
    if not clean:
        raise ValueError("Bitte einen Namen eintragen.")
    if clean == STANDARD_ACCESS_USERNAME:
        raise ValueError("Dieser interne Nutzername ist reserviert.")
    role_key = _clean_role(role)
    clean_permissions = normalize_permissions(role_key, permissions or {})
    original = _clean_username(original_username)
    existing = get_user(original) if original else get_user(clean)
    original_db_username = str((existing or {}).get("username") or original or "").strip()
    if original and original_db_username.casefold() != clean.casefold():
        duplicate = get_user(clean)
        if duplicate:
            raise ValueError("Dieser Name ist bereits vorhanden.")
    if existing:
        password_hash = str(existing.get("password_hash") or "")
        password_plain = str(existing.get("password_plain") or "")
        if password:
            password_hash = _hash_password(password)
            password_plain = str(password)
    else:
        if not password:
            raise ValueError("Bitte für neue Nutzer ein Passwort eintragen.")
        password_hash = _hash_password(password)
        password_plain = str(password)
    db_core.db_exec(
        """
        INSERT INTO app_users(username, display_name, password_hash, password_plain, role, permissions_json, active, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(username) DO UPDATE SET
            display_name=excluded.display_name,
            password_hash=excluded.password_hash,
            password_plain=excluded.password_plain,
            role=excluded.role,
            permissions_json=excluded.permissions_json,
            active=excluded.active,
            updated_at=excluded.updated_at;
        """,
        (
            clean,
            _clean_username(display_name) or clean,
            password_hash,
            password_plain,
            role_key,
            json.dumps(clean_permissions, ensure_ascii=False, sort_keys=True),
            1 if bool(active) else 0,
            _now_iso(),
        ),
        commit=True,
    )
    if original and original_db_username and original_db_username != clean:
        row = db_core.db_exec(
            "SELECT username FROM app_users WHERE lower(trim(username))=lower(trim(?));",
            (original_db_username,),
            fetchone=True,
        )
        if row:
            db_core.db_exec("DELETE FROM app_users WHERE username=?;", (str(row["username"] or original_db_username),), commit=True)
    return clean


def delete_user(username: Any) -> bool:
    _ensure_user_schema()
    clean = _clean_username(username)
    if not clean:
        return False
    row = db_core.db_exec("SELECT username FROM app_users WHERE lower(trim(username))=lower(trim(?));", (clean,), fetchone=True)
    if not row:
        return False
    db_core.db_exec("DELETE FROM app_users WHERE username=?;", (str(row["username"] or clean),), commit=True)
    return True


def permission_options() -> dict[str, str]:
    return dict(PERMISSION_OPTIONS)


def role_options() -> dict[str, str]:
    return dict(ROLE_OPTIONS)


def get_standard_access() -> dict[str, Any]:
    user = get_user(STANDARD_ACCESS_USERNAME)
    if user:
        return {
            "username": "Standard",
            "display_name": "Standard",
            "role": ROLE_STANDARD,
            "role_label": ROLE_OPTIONS[ROLE_STANDARD],
            "permissions": dict(user.get("permissions") or {}),
            "active": bool(user.get("active", True)),
            "updated_at": str(user.get("updated_at") or ""),
        }
    return {
        "username": "Standard",
        "display_name": "Standard",
        "role": ROLE_STANDARD,
        "role_label": ROLE_OPTIONS[ROLE_STANDARD],
        "permissions": normalize_permissions(ROLE_STANDARD, {}),
        "active": True,
        "updated_at": "",
    }


def get_standard_access_permissions() -> dict[str, bool]:
    access = get_standard_access()
    if not bool(access.get("active", True)):
        return {}
    return normalize_permissions(ROLE_STANDARD, access.get("permissions") or {})


def save_standard_access(*, permissions: dict[str, bool] | None = None, active: bool = True) -> str:
    _ensure_user_schema()
    clean_permissions = normalize_permissions(ROLE_STANDARD, permissions or {})
    existing = get_user(STANDARD_ACCESS_USERNAME)
    password_hash = str(existing.get("password_hash") or "") if existing else ""
    if not password_hash:
        password_hash = _hash_password("__standard_access_no_login__")
    db_core.db_exec(
        """
        INSERT INTO app_users(username, display_name, password_hash, password_plain, role, permissions_json, active, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(username) DO UPDATE SET
            display_name=excluded.display_name,
            password_hash=excluded.password_hash,
            password_plain=excluded.password_plain,
            role=excluded.role,
            permissions_json=excluded.permissions_json,
            active=excluded.active,
            updated_at=excluded.updated_at;
        """,
        (
            STANDARD_ACCESS_USERNAME,
            "Standard",
            password_hash,
            "",
            ROLE_STANDARD,
            json.dumps(clean_permissions, ensure_ascii=False, sort_keys=True),
            1 if bool(active) else 0,
            _now_iso(),
        ),
        commit=True,
    )
    return "Standard"
