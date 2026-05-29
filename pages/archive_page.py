from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable

import pandas as pd
from nicegui import ui

from core.ui_runtime import create_page_timer


def render(
    *,
    render_nav: Callable[[], None],
    is_admin: Callable[[], bool],
    can_delete_recent_done_functions: Callable[[], bool],
    purge_recent_done_archive: Callable[[], None],
    get_recent_done_df: Callable[..., pd.DataFrame],
    delete_recent_done_entry: Callable[[int], bool],
    now_berlin: Callable[[], datetime],
    get_archive_df: Callable[..., pd.DataFrame],
    norm_status_key: Callable[[Any], str],
    build_kpi_monthly: Callable[[pd.DataFrame], pd.DataFrame],
    build_kpi_baureihe: Callable[[pd.DataFrame], pd.DataFrame],
    df_to_excel_bytes: Callable[..., bytes],
    refresh_when_no_dialog: Callable[[Callable[[], None]], None],
) -> None:
    _norm_status_key = norm_status_key
    _refresh_when_no_dialog = refresh_when_no_dialog
    render_nav()
    ui.label("Archiv").classes("page-title")
    if not is_admin():
        ui.label("Diese Seite ist nur für Admins verfügbar.").classes("text-amber-3")
        return

    can_restore = can_delete_recent_done_functions()
    now_local = now_berlin()
    current_year = int(now_local.year)
    iso_now = now_local.isocalendar()
    current_kw = int(iso_now.week) if int(iso_now.year) == current_year else 1
    weeks_in_year = int(date(current_year, 12, 28).isocalendar().week)

    week_labels: list[str] = []
    week_ranges: dict[str, tuple[date, date]] = {}
    for kw in range(1, weeks_in_year + 1):
        kw_start = date.fromisocalendar(current_year, kw, 1)
        kw_end = date.fromisocalendar(current_year, kw, 7)
        label = f"KW {kw:02d} ({kw_start:%d.%m.} - {kw_end:%d.%m.%Y})"
        week_labels.append(label)
        week_ranges[label] = (kw_start, kw_end)
    default_week = week_labels[max(0, min(len(week_labels) - 1, current_kw - 1))] if week_labels else ""

    state: dict[str, Any] = {
        "week": default_week,
        "q_fzg": "",
        "q_frist": "",
        "sort_by": "completed_at",
    }

    with ui.row().classes("w-full gap-2 items-end wrap archive-page"):
        week_select = ui.select(week_labels, value=state["week"], label=f"Kalenderwoche {current_year}").props(
            "outlined dense"
        ).classes("min-w-[340px] archive-field")
        q_fzg = ui.input("Fahrzeug-Filter").props("outlined dense").classes("min-w-[260px] archive-field")
        q_frist = ui.input("Friststufe-Filter").props("outlined dense").classes("min-w-[260px] archive-field")
        sort_select = ui.select(
            {
                "completed_at": "Erledigt am",
                "status": "Fertigstellungsstatus ECM IV",
                "status_ecm3": "Fertigstellungsstatus ECM III",
                "fahrzeug": "Fahrzeug",
                "friststufe": "Friststufe",
                "anfang": "Anfang",
                "fertig": "Fertig",
            },
            value=state["sort_by"],
            label="Sortierung",
        ).props("outlined dense").classes("min-w-[220px] archive-field")

    box = ui.column().classes("w-full gap-3 archive-page")

    def _download_excel(df_xlsx: pd.DataFrame, *, filename: str, sheet: str) -> None:
        try:
            ui.download(df_to_excel_bytes(df_xlsx, sheet_name=sheet), filename=filename)
        except Exception as ex:
            ui.notify(f"Export fehlgeschlagen: {ex}", type="negative")

    @ui.refreshable
    def content() -> None:
        box.clear()
        with box:
            week_label = str(state.get("week") or default_week)
            if week_label not in week_ranges and week_labels:
                week_label = week_labels[0]
                state["week"] = week_label

            d_from, d_to = week_ranges.get(week_label, (now_local.date(), now_local.date()))

            df_arch = get_archive_df(limit=None, date_from=d_from, date_to=d_to)
            purge_recent_done_archive()
            df_restore = get_recent_done_df(limit=5000)

            ui.label("Rückholbare Aufträge").classes("text-lg")
            if df_restore.empty:
                ui.label("Keine aktuell rückholbaren Aufträge.").classes("text-gray-300")
            else:
                restore_view = df_restore.copy()
                q_fzg_val_restore = str(state.get("q_fzg") or "").strip()
                q_frist_val_restore = str(state.get("q_frist") or "").strip()
                if q_fzg_val_restore:
                    restore_view = restore_view[
                        restore_view["fahrzeug"].astype(str).str.contains(q_fzg_val_restore, case=False, na=False)
                    ]
                if q_frist_val_restore:
                    restore_view = restore_view[
                        restore_view["friststufe"].astype(str).str.contains(q_frist_val_restore, case=False, na=False)
                    ]
                restore_view = restore_view.sort_values(["archived_at", "expires_at"], ascending=[False, False], na_position="last")
                with ui.row().classes("w-full gap-3"):
                    with ui.card().classes("kpi-card"):
                        ui.label("Rückholbar").classes("text-sm text-gray-300")
                        ui.label(str(len(restore_view))).classes("text-3xl font-bold")
                    with ui.card().classes("kpi-card"):
                        ui.label("Frist").classes("text-sm text-gray-300")
                        ui.label("14 Tage").classes("text-3xl font-bold")

                if can_restore:
                    for _, rr in restore_view.iterrows():
                        archive_id = int(rr["id"])
                        fzg = str(rr.get("fahrzeug") or f"ID {archive_id}")
                        frist = str(rr.get("friststufe") or "").strip() or "-"
                        archived_at = pd.to_datetime(rr.get("archived_at"), errors="coerce")
                        expires_at = pd.to_datetime(rr.get("expires_at"), errors="coerce")
                        archived_txt = archived_at.strftime("%d.%m.%Y %H:%M") if not pd.isna(archived_at) else "-"
                        expires_txt = expires_at.strftime("%d.%m.%Y %H:%M") if not pd.isna(expires_at) else "-"

                        def restore_entry(archive_id=archive_id) -> None:
                            if not can_delete_recent_done_functions():
                                return
                            ok = delete_recent_done_entry(archive_id)
                            if ok:
                                ui.notify("Auftrag aus dem Archiv zurückgeholt.", type="positive")
                            else:
                                ui.notify("Rückholung nicht möglich oder bereits erledigt.", type="warning")
                            content.refresh()

                        with ui.row().classes("w-full items-center gap-3"):
                            ui.label(f"{fzg} | {frist}").classes("grow")
                            ui.label(f"Erledigt: {archived_txt}").classes("text-sm text-gray-300")
                            ui.label(f"Rückholbar bis: {expires_txt}").classes("text-sm text-gray-300")
                            ui.button("Aus Archiv zurückholen", on_click=restore_entry).props("color=warning").classes("btn-big")
                else:
                    ui.label("Rückholung ist nur mit Bearbeitungsrechten möglich.").classes("text-gray-300")

            if df_arch.empty:
                ui.label("Keine archivierten Aufträge im Zeitraum.")
                return

            status_norm = df_arch["status"].apply(_norm_status_key)
            total = int(len(df_arch))
            ontime = int(status_norm.isin({"puenktlich", "punktlich"}).sum())
            late = int(status_norm.isin({"verspaetet", "verspatet"}).sum())
            with ui.row().classes("w-full gap-3"):
                for title, value in [("Archiviert (Zeitraum)", total), ("Pünktlich", ontime), ("Verspätet", late)]:
                    with ui.card().classes("kpi-card"):
                        ui.label(title).classes("text-sm text-gray-300")
                        ui.label(str(value)).classes("text-3xl font-bold")

            kpi_mon = build_kpi_monthly(df_arch)
            ui.label("KPI je Monat (pünktlich / verspätet)").classes("text-lg")
            if kpi_mon.empty:
                ui.label("Keine Daten im Zeitraum für Monats-KPIs.").classes("text-gray-300")
            else:
                with ui.row().classes("w-full gap-2"):
                    ui.button(
                        "KPI je Monat (Excel)",
                        on_click=lambda df_xlsx=kpi_mon.copy(): _download_excel(
                            df_xlsx,
                            filename=f"KPI_Monat_{now_berlin():%Y-%m-%d_%H-%M}.xlsx",
                            sheet="KPI_Monat",
                        ),
                    ).classes("btn-big")

            kpi_b = build_kpi_baureihe(df_arch)
            ui.label("KPI je Baureihe").classes("text-lg")
            if kpi_b.empty:
                ui.label("Keine Daten für Baureihen-KPI im Zeitraum.").classes("text-gray-300")
            else:
                kpi_cols = [{"name": c, "label": c, "field": c} for c in kpi_b.columns]
                kpi_rows = kpi_b.fillna("").to_dict(orient="records")
                ui.table(columns=kpi_cols, rows=kpi_rows, row_key="Baureihe").classes("w-full archive-table")
                with ui.row().classes("w-full gap-2"):
                    ui.button(
                        "KPI je Baureihe (Excel)",
                        on_click=lambda df_xlsx=kpi_b.copy(): _download_excel(
                            df_xlsx,
                            filename=f"KPI_Baureihe_{now_berlin():%Y-%m-%d_%H-%M}.xlsx",
                            sheet="KPI_Baureihe",
                        ),
                    ).classes("btn-big")

            ui.label("Archiv-Liste").classes("text-lg")
            view = df_arch.copy()
            q_fzg_val = str(state.get("q_fzg") or "").strip()
            q_frist_val = str(state.get("q_frist") or "").strip()
            if q_fzg_val:
                view = view[view["fahrzeug"].astype(str).str.contains(q_fzg_val, case=False, na=False)]
            if q_frist_val:
                view = view[view["friststufe"].astype(str).str.contains(q_frist_val, case=False, na=False)]

            sort_by = str(state.get("sort_by") or "completed_at")
            if sort_by in {"completed_at", "anfang", "fertig"}:
                view = view.sort_values(by=[sort_by], ascending=False, na_position="last")
            else:
                view = view.sort_values(by=[sort_by], ascending=True, na_position="last")

            view_show = view.copy()
            for col in ("anfang", "fertig", "completed_at"):
                view_show[col] = pd.to_datetime(view_show[col], errors="coerce").dt.strftime("%d.%m.%Y %H:%M").fillna("")
            view_show = view_show.rename(
                columns={
                    "fahrzeug": "Fahrzeug",
                    "friststufe": "Friststufe",
                    "anfang": "Anfang",
                    "fertig": "Fertig",
                    "completed_at": "Erledigt am",
                    "status": "Fertigstellungsstatus ECM IV",
                    "status_ecm3": "Fertigstellungsstatus ECM III",
                    "last_problem_note": "Hinweis",
                }
            )
            table_cols = [
                "Fahrzeug",
                "Friststufe",
                "Anfang",
                "Fertig",
                "Hinweis",
                "Erledigt am",
                "Fertigstellungsstatus ECM IV",
                "Fertigstellungsstatus ECM III",
            ]
            for col in table_cols:
                if col not in view_show.columns:
                    view_show[col] = ""
            view_show = view_show[table_cols]

            with ui.row().classes("w-full gap-2 wrap"):
                ui.button(
                    "Gefilterte Ansicht (Excel)",
                    on_click=lambda df_xlsx=view_show.copy(): _download_excel(
                        df_xlsx,
                        filename=f"Archiv_gefiltert_{now_berlin():%Y-%m-%d_%H-%M}.xlsx",
                        sheet="Archiv_gefilt",
                    ),
                ).classes("btn-big")

                full = get_archive_df(limit=None)
                full_show = full.copy()
                for col in ("anfang", "fertig", "completed_at"):
                    full_show[col] = pd.to_datetime(full_show[col], errors="coerce").dt.strftime("%d.%m.%Y %H:%M").fillna("")
                full_show = full_show.rename(
                    columns={
                        "fahrzeug": "Fahrzeug",
                        "friststufe": "Friststufe",
                        "anfang": "Anfang",
                        "fertig": "Fertig",
                        "completed_at": "Erledigt am",
                        "status": "Fertigstellungsstatus ECM IV",
                        "status_ecm3": "Fertigstellungsstatus ECM III",
                        "last_problem_note": "Hinweis",
                    }
                )
                for col in table_cols:
                    if col not in full_show.columns:
                        full_show[col] = ""
                full_show = full_show[table_cols]

                ui.button(
                    "Komplettes Archiv (Excel)",
                    on_click=lambda df_xlsx=full_show.copy(): _download_excel(
                        df_xlsx,
                        filename=f"Archiv_gesamt_{now_berlin():%Y-%m-%d_%H-%M}.xlsx",
                        sheet="Archiv_gesamt",
                    ),
                ).classes("btn-big")

            rows = view_show.fillna("").to_dict(orient="records")
            columns = [{"name": c, "label": c, "field": c} for c in view_show.columns]
            ui.table(columns=columns, rows=rows, row_key="Fahrzeug").classes("w-full archive-table")

    def _on_week_change(e) -> None:
        state["week"] = str(e.value or default_week)
        content.refresh()

    def _on_fzg_change(e) -> None:
        state["q_fzg"] = str(e.value or "")
        content.refresh()

    def _on_frist_change(e) -> None:
        state["q_frist"] = str(e.value or "")
        content.refresh()

    def _on_sort_change(e) -> None:
        state["sort_by"] = str(e.value or "completed_at")
        content.refresh()

    week_select.on_value_change(_on_week_change)
    q_fzg.on_value_change(_on_fzg_change)
    q_frist.on_value_change(_on_frist_change)
    sort_select.on_value_change(_on_sort_change)

    content()
    create_page_timer(5.0, lambda: _refresh_when_no_dialog(content.refresh))
