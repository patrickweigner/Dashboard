from __future__ import annotations

import os
import secrets

try:
    import tomllib
except Exception:
    tomllib = None


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PARENT_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))
APP_STATE_DIR = os.path.join(os.getenv("LOCALAPPDATA") or BASE_DIR, "FristenLiveV1")
ADMIN_ROLE_STORAGE_KEY = "admin_role"
LOGIN_USERNAME_STORAGE_KEY = "login_username"
STORAGE_SECRET_FILE = os.path.join(APP_STATE_DIR, "storage_secret.txt")

ROLE_STANDARD = "standard"
ROLE_ADMIN_FULL = "admin_full"
ROLE_ADMIN_SL = "admin_sl"
ROLE_ADMIN_WL = "admin_wl"

BROWSER_HTML_ZOOM = 0.8
NATIVE_HTML_ZOOM = 0.5


def _default_db_path() -> str:
    env_path = str(os.getenv("FRISTEN_DB_PATH", "") or "").strip()
    if env_path:
        return os.path.abspath(env_path)

    candidates = [
        os.path.abspath(os.path.join(BASE_DIR, "fristenplanung.db")),
        os.path.abspath(os.path.join(BASE_DIR, "..", "fristenplanung.db")),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return candidates[-1]


def _load_storage_secret() -> str:
    env_value = str(os.getenv("FRISTEN_STORAGE_SECRET", "") or "").strip()
    if env_value:
        return env_value

    try:
        with open(STORAGE_SECRET_FILE, "r", encoding="utf-8") as handle:
            stored_value = str(handle.read() or "").strip()
            if stored_value:
                return stored_value
    except OSError:
        pass

    generated_value = secrets.token_hex(32)
    try:
        os.makedirs(APP_STATE_DIR, exist_ok=True)
        with open(STORAGE_SECRET_FILE, "w", encoding="utf-8") as handle:
            handle.write(generated_value)
    except OSError:
        pass
    return generated_value


def _notify_secrets_paths() -> list[str]:
    return [
        os.path.join(BASE_DIR, ".streamlit", "secrets.toml"),
        os.path.join(PARENT_DIR, ".streamlit", "secrets.toml"),
    ]


def _config_from_env_or_secrets(*keys: str, invalid_values: set[str] | None = None) -> str:
    invalid = {str(v).strip().casefold() for v in (invalid_values or set()) if str(v).strip()}
    for key in keys:
        env_val = str(os.getenv(str(key), "") or "").strip()
        if env_val and env_val.casefold() not in invalid:
            return env_val
    if tomllib is None:
        return ""
    for path in _notify_secrets_paths():
        if not os.path.exists(path):
            continue
        try:
            with open(path, "rb") as handle:
                data = tomllib.load(handle) or {}
            for key in keys:
                value = str(data.get(str(key), "") or "").strip()
                if value and value.casefold() not in invalid:
                    return value
        except Exception:
            continue
    return ""


def _notify_flow_url() -> str:
    return _config_from_env_or_secrets("NOTIFY_FLOW_URL")


def _float_env(key: str, default: float) -> float:
    raw = str(os.getenv(key, "") or "").strip()
    if not raw:
        return float(default)
    try:
        value = float(raw)
    except Exception:
        return float(default)
    return value if value > 0 else float(default)


DB_PATH = _default_db_path()
APP_HOST = os.getenv("FRISTEN_LIVE_HOST", "0.0.0.0")
APP_PORT_RAW = str(os.getenv("FRISTEN_LIVE_PORT", "") or "").strip()
APP_PORT = int(APP_PORT_RAW) if APP_PORT_RAW else 8502
APP_STORAGE_SECRET = _load_storage_secret()
NATIVE_MODE = str(os.getenv("FRISTEN_LIVE_NATIVE", "") or "").strip().lower() in {"1", "true", "yes", "on"}
SHOW_DB_PATH_IN_NAV = str(os.getenv("FRISTEN_SHOW_DB_PATH", "") or "").strip().lower() in {"1", "true", "yes", "on"}
WERKSTATTHALLE_REFRESH_SECONDS = _float_env("FRISTEN_WERKSTATTHALLE_REFRESH_SECONDS", 5.0)
PRIORISIERUNG_REFRESH_SECONDS = _float_env("FRISTEN_PRIORISIERUNG_REFRESH_SECONDS", 5.0)
APP_RECONNECT_TIMEOUT_SECONDS = _float_env("FRISTEN_RECONNECT_TIMEOUT_SECONDS", 30.0)
APP_BINDING_REFRESH_INTERVAL_SECONDS = _float_env("FRISTEN_BINDING_REFRESH_INTERVAL_SECONDS", 0.2)
APP_DISCONNECT_RELOAD_SECONDS = _float_env("FRISTEN_DISCONNECT_RELOAD_SECONDS", 20.0)
