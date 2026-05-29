from __future__ import annotations

from typing import Any, Callable

import pandas as pd
from nicegui import ui


def render(
    *,
    render_nav: Callable[[], None],
    is_admin: Callable[[], bool],
    can_use_delete_functions: Callable[[], bool],
    as_berlin: Callable[[Any], Any],
    now_berlin: Callable[[], Any],
    problem_options: list[str],
    parse_ecm4_plan_from_excel: Callable[[bytes], pd.DataFrame] | None,
    parse_excel_to_df_bytes: Callable[[bytes], pd.DataFrame],
    build_import_diff: Callable[[pd.DataFrame], tuple[pd.DataFrame, dict[str, int]]],
    find_missing_open_tasks_for_import: Callable[[pd.DataFrame], list[dict[str, Any]]],
    clear_pending_missing_open_state: Callable[[dict[str, Any] | None], None],
    parse_rws_week_plan_from_excel: Callable[[bytes], pd.DataFrame],
    canon_dt_for_import_compare: Callable[[Any], str],
    canon_zus_for_import_compare: Callable[[Any], tuple[str, ...]],
    zus_added_only: Callable[[Any, Any], str],
    collect_missing_open_decisions: Callable[[list[dict[str, Any]]], tuple[list[dict[str, Any]], list[str]]],
    apply_missing_open_decisions: Callable[[list[dict[str, Any]]], tuple[int, int, int]],
    add_open_tasks_with_progress: Callable[[pd.DataFrame], tuple[int, int, int]],
    replace_ecm4_plan_in_db: Callable[..., None],
    replace_rws_week_plan_in_db: Callable[..., None],
    reset_all: Callable[[], None],
) -> None:
    render_nav()
    ui.label("Excel Upload / Verwaltung").classes("page-title")
    if not is_admin():
        ui.label("Diese Seite ist nur für Admins verfügbar.").classes("text-amber-3")
        return
    can_delete = can_use_delete_functions()

    state: dict[str, Any] = {
        "df": None,
        "ecm4_df": None,
        "rws_df": None,
        "filename": "",
        "diff_df": None,
        "summary": None,
        "missing_items": [],
        "missing_controls": [],
    }
    preview = ui.column().classes("w-full gap-2 upload-page")
    upload_slot = ui.column().classes("w-full")

    def render_preview() -> None:
        preview.clear()
        with preview:
            df = state.get("df")
            if df is None:
                ui.label("Keine Datei geladen.").classes("text-white")
                return
            ui.label(f"Datei: {state.get('filename') or '-'}").classes("text-white")
            ui.label(f"Datensätze: {len(df)}").classes("text-white")
            if df.empty:
                ui.label("Datei gelesen, aber keine gültigen Zeilen gefunden.").classes("text-white")
                return

            summary = state.get("summary") or {}
            with ui.row().classes("w-full gap-3 items-stretch wrap upload-summary-row"):
                for title, value in [
                    ("Gesamt", int(summary.get("total", len(df)))),
                    ("Neu", int(summary.get("new", 0))),
                    ("Update", int(summary.get("update", 0))),
                    ("Skip", int(summary.get("skip", 0))),
                    ("Sig-Konflikte", int(summary.get("sig_conflicts", 0))),
                ]:
                    with ui.card().classes("kpi-card"):
                        ui.label(title).classes("text-sm text-white")
                        ui.label(str(value)).classes("text-3xl font-bold")
                with ui.card().classes("kpi-card upload-actions-card"):
                    ui.label("Aktionen").classes("text-sm text-white")
                    with ui.column().classes("w-full gap-2"):
                        ui.button("Import starten", on_click=lambda: do_import()).props("color=primary").classes(
                            "btn-big w-full"
                        )
                        ui.button("Vorschau leeren", on_click=lambda: clear_preview()).classes("btn-remove btn-big w-full")

            missing_items = state.get("missing_items") or []
            state["missing_controls"] = []
            if missing_items:
                with ui.card().classes("w-full upload-panel missing-open-card"):
                    ui.label("Fehlende offene Aufträge (nicht im Upload enthalten)").classes("missing-open-title")
                    ui.label(
                        "Bitte pro Eintrag wählen: offen lassen, als geschoben entfernen oder mit Endzeit archivieren."
                    ).classes("text-sm text-white")
                    for item in missing_items:
                        oid = int(item.get("id"))
                        fzg = str(item.get("fahrzeug") or f"ID {oid}")
                        fr = str(item.get("friststufe") or "").strip() or "-"
                        def_dt = as_berlin(pd.to_datetime(item.get("default_end_iso"), errors="coerce")) or now_berlin()
                        with ui.card().classes("w-full missing-open-item"):
                            with ui.row().classes("w-full items-center gap-3"):
                                ui.label(f"{fzg} | {fr}").classes("grow font-bold missing-open-vehicle")
                                action_options = {
                                    "keep": "Offen lassen",
                                    "delete": "Als geschoben entfernen",
                                    "archive": "Erledigt archivieren",
                                }
                                action = ui.select(
                                    action_options,
                                    value="keep",
                                    label="Aktion",
                                ).props("outlined dense").classes("min-w-[280px] upload-field")

                            end_wrap = ui.row().classes("w-full gap-2 items-center")
                            with end_wrap:
                                end_date = ui.date(value=def_dt.date().isoformat()).props("mask=YYYY-MM-DD").classes(
                                    "upload-field"
                                )
                                end_time = ui.input("Uhrzeit (HH:MM)", value=def_dt.strftime("%H:%M")).props("outlined").classes(
                                    "upload-field"
                                )
                            end_wrap.bind_visibility_from(action, "value", lambda v: str(v or "") == "archive")

                            reason_wrap = ui.column().classes("w-full gap-1")
                            with reason_wrap:
                                ui.label("Verspätungsgrund (nur bei verspäteter Archivierung erforderlich)").classes(
                                    "text-xs text-white"
                                )
                                checks: list[tuple[str, Any]] = []
                                for opt in problem_options:
                                    checks.append((opt, ui.checkbox(opt)))
                                reason_txt = ui.input("Freitext (optional)").props("outlined").classes("w-full upload-field")
                            reason_wrap.bind_visibility_from(action, "value", lambda v: str(v or "") == "archive")

                            state["missing_controls"].append(
                                {
                                    "id": oid,
                                    "item": item,
                                    "action": action,
                                    "end_date": end_date,
                                    "end_time": end_time,
                                    "checks": checks,
                                    "reason_txt": reason_txt,
                                }
                            )

            diff_df = state.get("diff_df")
            if isinstance(diff_df, pd.DataFrame) and not diff_df.empty:
                view = diff_df.copy()
                if "action" in view.columns:
                    action_norm = view["action"].astype(str).str.upper().str.strip()
                    view = view[action_norm.isin(["NEW", "UPDATE"])].copy()
                else:
                    view = view.iloc[0:0].copy()

                if {"Anfang_old", "Anfang_new"}.issubset(view.columns):
                    start_unchanged = view.apply(
                        lambda rr: canon_dt_for_import_compare(rr.get("Anfang_old", ""))
                        == canon_dt_for_import_compare(rr.get("Anfang_new", "")),
                        axis=1,
                    )
                    view.loc[start_unchanged, ["Anfang_old", "Anfang_new"]] = ""

                if {"Fertig_old", "Fertig_new"}.issubset(view.columns):
                    end_unchanged = view.apply(
                        lambda rr: canon_dt_for_import_compare(rr.get("Fertig_old", ""))
                        == canon_dt_for_import_compare(rr.get("Fertig_new", "")),
                        axis=1,
                    )
                    view.loc[end_unchanged, ["Fertig_old", "Fertig_new"]] = ""

                if {"zus_old", "zus_new"}.issubset(view.columns):
                    zus_unchanged = view.apply(
                        lambda rr: canon_zus_for_import_compare(rr.get("zus_old", ""))
                        == canon_zus_for_import_compare(rr.get("zus_new", "")),
                        axis=1,
                    )
                    view["zus_added"] = view.apply(
                        lambda rr: zus_added_only(rr.get("zus_old", ""), rr.get("zus_new", "")),
                        axis=1,
                    )
                    view["zus_removed"] = view.apply(
                        lambda rr: zus_added_only(rr.get("zus_new", ""), rr.get("zus_old", "")),
                        axis=1,
                    )
                    view.loc[zus_unchanged, ["zus_added", "zus_removed"]] = ""
                else:
                    view["zus_added"] = ""
                    view["zus_removed"] = ""

                show_cols = [
                    "action",
                    "Fahrzeug",
                    "Friststufe",
                    "Anfang_old",
                    "Anfang_new",
                    "Fertig_old",
                    "Fertig_new",
                    "zus_added",
                    "zus_removed",
                    "sig_conflict",
                ]
                view = view[show_cols].copy().rename(
                    columns={
                        "action": "Aktion",
                        "Anfang_old": "Anfang (alt)",
                        "Anfang_new": "Anfang (neu)",
                        "Fertig_old": "Fertig (alt)",
                        "Fertig_new": "Fertig (neu)",
                        "zus_added": "Neue Zusatzarbeit",
                        "zus_removed": "Entfernte Zusatzarbeiten",
                        "sig_conflict": "Sig-Konflikt",
                    }
                )
                with ui.card().classes("w-full upload-panel import-diff-card"):
                    ui.label(f"Import-Diff (Vorschau) - Zeilen: {len(view)}").classes("text-lg text-white")
                    if view.empty:
                        ui.label("Keine Neu/Update-Zeilen in der aktuellen Datei gefunden.").classes("text-sm text-white")
                    sample = view.head(500).copy()
                    columns = [{"name": c, "label": c, "field": c} for c in sample.columns]
                    rows = sample.fillna("").to_dict(orient="records")
                    ui.table(columns=columns, rows=rows, row_key="Fahrzeug").classes("w-full upload-preview-table")

    async def on_upload(e) -> None:
        try:
            payload: bytes | None = None

            up_file = getattr(e, "file", None)
            if up_file is not None and hasattr(up_file, "read"):
                maybe = up_file.read()
                payload = await maybe if hasattr(maybe, "__await__") else maybe

            if payload is None:
                raw_content = getattr(e, "content", None)
                if raw_content is not None:
                    payload = raw_content.read() if hasattr(raw_content, "read") else raw_content

            if isinstance(payload, bytearray):
                payload = bytes(payload)
            elif isinstance(payload, memoryview):
                payload = payload.tobytes()

            if not payload:
                ui.notify("Datei ist leer.", type="warning")
                return
            name_from_file = str(getattr(up_file, "name", "") or "") if up_file is not None else ""
            state["filename"] = name_from_file or str(getattr(e, "name", "") or "")
            df = parse_excel_to_df_bytes(payload)
            state["df"] = df
            state["ecm4_df"] = None
            state["rws_df"] = None
            diff_df, summary = build_import_diff(df)
            missing = find_missing_open_tasks_for_import(df)
            state["diff_df"] = diff_df
            state["summary"] = summary
            clear_pending_missing_open_state(state)
            state["missing_items"] = missing
            if callable(parse_ecm4_plan_from_excel):
                try:
                    ecm4_df = parse_ecm4_plan_from_excel(payload)
                    state["ecm4_df"] = ecm4_df
                except Exception as ex:
                    state["ecm4_df"] = None
                    ui.notify(f"ECM4-Parsing fehlgeschlagen: {ex}", type="warning")
            else:
                ui.notify(
                    "ECM4-Parser nicht geladen: Tagesplanungsdaten werden aus diesem Upload nicht übernommen.",
                    type="warning",
                )
            try:
                state["rws_df"] = parse_rws_week_plan_from_excel(payload)
            except Exception as ex:
                state["rws_df"] = pd.DataFrame(columns=["fahrzeug", "start", "end"])
                ui.notify(f"RWS-Parsing fehlgeschlagen: {ex}", type="warning")
            render_preview()
            render_upload_panel()
            ecm4_cnt = int(len(state["ecm4_df"])) if isinstance(state.get("ecm4_df"), pd.DataFrame) else 0
            rws_cnt = int(len(state["rws_df"])) if isinstance(state.get("rws_df"), pd.DataFrame) else 0
            ui.notify(
                f"Datei geladen: {len(df)} Datensätze | Diff: Neu {summary.get('new', 0)}, Update {summary.get('update', 0)} | Fehlend: {len(missing)} | ECM4: {ecm4_cnt} | RWS-Woche: {rws_cnt}",
                type="positive",
            )
        except Exception as ex:
            ui.notify(f"Upload fehlgeschlagen: {ex}", type="negative")

    def render_upload_panel() -> None:
        upload_slot.clear()
        if state.get("df") is not None:
            return
        with upload_slot:
            with ui.card().classes("w-full upload-panel upload-page"):
                ui.label("Excel-Datei hochladen").classes("text-lg text-white")
                ui.upload(
                    label="Excel auswählen",
                    on_upload=on_upload,
                    auto_upload=True,
                    max_files=1,
                ).props("accept=.xlsx,.xlsm,.xls").classes("w-full upload-field")
                ui.label("Vorschau zeigt automatisch nur Neu/Update.").classes("text-sm text-white")

    def clear_preview() -> None:
        state.update(
            {
                "df": None,
                "ecm4_df": None,
                "rws_df": None,
                "filename": "",
                "diff_df": None,
                "summary": None,
            }
        )
        clear_pending_missing_open_state(state)
        render_upload_panel()
        render_preview()

    def do_import() -> None:
        df = state.get("df")
        if df is None:
            ui.notify("Bitte erst eine Datei hochladen.", type="warning")
            return
        try:
            decisions, decision_errors = collect_missing_open_decisions(state.get("missing_controls") or [])
            if decision_errors:
                for msg in decision_errors[:8]:
                    ui.notify(msg, type="warning")
                if len(decision_errors) > 8:
                    ui.notify(f"Weitere Fehler: {len(decision_errors) - 8}", type="warning")
                return
            removed, archived, kept = apply_missing_open_decisions(decisions)
            ins, upd, skp = add_open_tasks_with_progress(df)
            ecm4_df = state.get("ecm4_df")
            rws_df = state.get("rws_df")
            ecm4_cnt = 0
            rws_cnt = 0
            if isinstance(ecm4_df, pd.DataFrame) and not ecm4_df.empty:
                replace_ecm4_plan_in_db(ecm4_df, source_name=state.get("filename"))
                ecm4_cnt = len(ecm4_df)
            if isinstance(rws_df, pd.DataFrame):
                replace_rws_week_plan_in_db(rws_df, source_name=state.get("filename"))
                rws_cnt = len(rws_df)
            ui.notify(
                f"Import fertig. Neu: {ins}, Aktualisiert: {upd}, übersprungen: {skp}, Fehlende -> Entfernt: {removed}, Archiviert: {archived}, Offen: {kept}, ECM4: {ecm4_cnt}, RWS-Woche: {rws_cnt}",
                type="positive",
            )
            clear_preview()
        except Exception as ex:
            ui.notify(f"Import fehlgeschlagen: {ex}", type="negative")

    if can_delete:
        with ui.card().classes("w-full upload-panel upload-page") as reset_panel:
            ui.label("Daten zurücksetzen").classes("text-lg text-white")
            ui.label("Zum Bestätigen LOESCHEN eingeben.").classes("text-sm text-white")
            reset_confirm = ui.input("Bestätigung").props("outlined").classes("min-w-[320px] upload-field")

        def do_reset_all() -> None:
            token = str(reset_confirm.value or "").strip().upper()
            if token != "LOESCHEN":
                ui.notify("Nicht bestätigt. Bitte LOESCHEN eingeben.", type="warning")
                return
            try:
                reset_all()
                ui.notify("Alle Tabellen wurden geleert.", type="positive")
                clear_preview()
                reset_confirm.value = ""
            except Exception as ex:
                ui.notify(f"Zurücksetzen fehlgeschlagen: {ex}", type="negative")

        with reset_panel:
            ui.button("Alles löschen", on_click=do_reset_all).classes("btn-remove btn-big")

    render_upload_panel()
    render_preview()
