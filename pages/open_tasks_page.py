from __future__ import annotations

from datetime import timedelta
import logging
import time
from typing import Callable

import pandas as pd
from nicegui import ui

from core.ui_runtime import create_page_timer


OPEN_TASKS_FORCE_REFRESH_SECONDS = 60.0
logger = logging.getLogger(__name__)


def render(
    *,
    render_nav: Callable[[], None],
    open_new_order_dialog: Callable[[Callable[[], None]], None],
    render_legend: Callable[[], None],
    get_open_tasks_df: Callable[[], pd.DataFrame],
    build_task_card: Callable[..., None],
    refresh_when_no_dialog: Callable[[Callable[[], None]], bool],
    current_data_version: Callable[[], int],
) -> None:
    render_nav()
    with ui.column().classes("w-full open-tasks-page"):
        with ui.row().classes("w-full items-center justify-between gap-3 wrap open-command-row"):
            ui.label("Offene Aufträge").classes("page-title open-page-title")
            ui.button(
                "Neuer Auftrag",
                icon="add_task",
                on_click=lambda: open_new_order_dialog(content.refresh),
            ).classes("btn-big open-new-order-btn")
        with ui.element("div").classes("open-legend-wrap"):
            render_legend()

        task_col = ui.column().classes("w-full gap-3 open-task-list")

    @ui.refreshable
    def content() -> None:
        df = get_open_tasks_df()
        task_col.clear()
        with task_col:
            if df.empty:
                with ui.element("div").classes("open-empty-state"):
                    ui.label("Keine offenen Aufträge.").classes("text-lg text-gray-300")
                return

            by_frist_urd = df["Friststufe"].astype(str).str.contains(r"\bURD\b", case=False, na=False)
            ap_norm = df["Arbeitsplatz"].fillna("").astype(str).str.strip().str.casefold()
            ap_pdf_norm = df.get("ap_pdf", pd.Series([""] * len(df))).fillna("").astype(str).str.strip().str.casefold()
            by_urd = by_frist_urd | ap_norm.isin({"urd", "omb-neustrelitz"}) | ap_pdf_norm.isin(
                {"urd", "omb-neustrelitz"}
            )

            df_urd = df[by_urd].copy()
            df_main = df[~by_urd].copy()
            fertig_dt = pd.to_datetime(df.get("Fertig"), errors="coerce", utc=True)
            now_utc = pd.Timestamp.now(tz="UTC")
            overdue_count = int((fertig_dt.notna() & (fertig_dt < now_utc)).sum())
            due24_count = int((fertig_dt.notna() & (fertig_dt >= now_utc) & (fertig_dt <= now_utc + timedelta(hours=24))).sum())
            problem_count = (
                df.get("last_problem_note", pd.Series([""] * len(df)))
                .fillna("")
                .astype(str)
                .str.strip()
                .ne("")
                .sum()
            )

            def render_stat(label: str, value: int, kind: str) -> None:
                with ui.element("div").classes(f"open-stat open-stat-{kind}"):
                    ui.label(str(value)).classes("open-stat-value")
                    ui.label(label).classes("open-stat-label")

            with ui.element("div").classes("open-summary-row"):
                render_stat("Gesamt", int(len(df)), "total")
                render_stat("In 24h", due24_count, "due")
                render_stat("Überfällig", overdue_count, "late")
                render_stat("Problem", int(problem_count), "problem")

            def _sort_df(dfx: pd.DataFrame) -> pd.DataFrame:
                if dfx.empty:
                    return dfx
                return dfx.sort_values(by=["Fertig", "Anfang", "Fahrzeug"], ascending=[True, True, True], na_position="last")

            sections = [
                ("Fristen", _sort_df(df_main)),
                ("URD", _sort_df(df_urd)),
            ]
            shown_any = False
            for title, sdf in sections:
                if sdf.empty:
                    continue
                if shown_any:
                    ui.separator().classes("open-section-separator")
                with ui.row().classes("w-full items-end justify-between gap-2 wrap open-section-head"):
                    ui.label(title).classes("section-title open-section-title")
                    ui.label(f"{len(sdf)} Auftrag/Aufträge").classes("open-section-count")
                for _, row in sdf.iterrows():
                    build_task_card(row, content.refresh, show_area_controls=False)
                shown_any = True

    content()
    last_render_version = current_data_version()
    last_refresh_at = time.monotonic()

    def maybe_refresh_open_tasks() -> None:
        nonlocal last_render_version, last_refresh_at
        try:
            current_version = current_data_version()
            now = time.monotonic()
            version_changed = current_version != last_render_version
            force_due = now - last_refresh_at >= OPEN_TASKS_FORCE_REFRESH_SECONDS
            if not version_changed and not force_due:
                return

            if refresh_when_no_dialog(content.refresh):
                last_render_version = current_data_version()
                last_refresh_at = time.monotonic()
        except Exception:
            logger.exception("Failed to refresh open tasks page")

    create_page_timer(5.0, maybe_refresh_open_tasks)
