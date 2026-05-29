from __future__ import annotations

import asyncio
import os

from nicegui import app, ui


def configure(**deps) -> None:
    globals().update(deps)


def initialize_app() -> None:
    def _install_windows_connection_reset_filter() -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if getattr(loop, "_fristen_connection_reset_filter", False):
            return
        previous_handler = loop.get_exception_handler()

        def _handle_loop_exception(loop: asyncio.AbstractEventLoop, context: dict) -> None:
            exc = context.get("exception")
            handle_text = str(context.get("handle") or "")
            if (
                isinstance(exc, ConnectionResetError)
                and getattr(exc, "winerror", None) == 10054
                and "_ProactorBasePipeTransport._call_connection_lost" in handle_text
            ):
                return
            if previous_handler is not None:
                previous_handler(loop, context)
            else:
                loop.default_exception_handler(context)

        loop.set_exception_handler(_handle_loop_exception)
        setattr(loop, "_fristen_connection_reset_filter", True)

    app.on_startup(_install_windows_connection_reset_filter)
    register_global_head_html(
        browser_html_zoom=BROWSER_HTML_ZOOM,
        disconnect_reload_seconds=APP_DISCONNECT_RELOAD_SECONDS,
        native_html_zoom=NATIVE_HTML_ZOOM,
        open_item_gap_px=OPEN_ITEM_GAP_PX,
        open_item_font_size_px=OPEN_ITEM_FONT_SIZE_PX,
        open_item_font_weight=OPEN_ITEM_FONT_WEIGHT,
        open_item_line_height=OPEN_ITEM_LINE_HEIGHT,
    )
    assets_dir = os.path.join(BASE_DIR, "assets")
    if os.path.isdir(assets_dir):
        app.add_static_files("/assets", assets_dir)
    init_db()
    auto_clear_shopfloorboard_5s_if_due()
    start_lwu_reminder_worker()
    from core.diagnostics import start_diagnostics_if_enabled

    start_diagnostics_if_enabled()


def run_app() -> None:
    run_kwargs = {
        "host": APP_HOST,
        "port": APP_PORT,
        "title": "Fristenplanung Live V1",
        "reload": False,
        "show": False,
        "storage_secret": APP_STORAGE_SECRET,
        "reconnect_timeout": APP_RECONNECT_TIMEOUT_SECONDS,
        "binding_refresh_interval": APP_BINDING_REFRESH_INTERVAL_SECONDS,
    }
    if NATIVE_MODE:
        run_kwargs.update(
            {
                "native": True,
                "window_size": (4096, 2160),
                "fullscreen": True,
                "host": APP_HOST or "127.0.0.1",
                "port": (APP_PORT if APP_PORT_RAW else None),
            }
        )
    ui.run(**run_kwargs)
