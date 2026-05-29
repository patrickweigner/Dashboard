from __future__ import annotations

from datetime import date, datetime, time, timedelta
import re
from typing import Any, Callable

import pandas as pd
from nicegui import ui


def _find_open_task_row(task_id: int, get_open_tasks_df: Callable[[], pd.DataFrame]) -> pd.Series | None:
    df = get_open_tasks_df()
    hit = df[df["id"] == int(task_id)]
    if hit.empty:
        return None
    return hit.iloc[0]


def _split_check_item_text(value: Any) -> tuple[str, str]:
    lines = [line.strip() for line in str(value or "").splitlines() if line.strip()]
    if not lines:
        return "", ""
    return lines[0], " - ".join(lines[1:])


def _format_hours_text(minutes: float) -> str:
    hours = max(0.0, float(minutes or 0.0) / 60.0)
    rounded = round(hours)
    if abs(hours - rounded) < 0.000001:
        return f"{int(rounded)} h"
    return f"{hours:.1f}".replace(".", ",") + " h"


def _frist_item_capacity_minutes(item: Any) -> float:
    text = str(item or "")
    match = re.search(r"(\d+)\s*Ma\s*-\s*([0-9]+(?:[,.][0-9]+)?)\s*h", text, flags=re.I)
    if not match:
        match = re.search(r"([0-9]+(?:[,.][0-9]+)?)\s*h", text, flags=re.I)
        if not match:
            return 0.0
        return float(str(match.group(1)).replace(",", ".")) * 60.0
    employees = max(0, int(match.group(1)))
    duration_hours = float(str(match.group(2)).replace(",", "."))
    return duration_hours * 60.0 * max(1, employees)


def _remaining_frist_minutes(items: list[str], done_bits: list[bool]) -> float:
    total = 0.0
    for index, item in enumerate(items):
        done = bool(done_bits[index]) if index < len(done_bits) else False
        if done:
            continue
        total += _frist_item_capacity_minutes(item)
    return total



def open_zus_dialog(
    task_id: int,
    refresh_fn: Callable[[], None],
    *,
    get_open_tasks_df: Callable[[], pd.DataFrame],
    is_admin: Callable[[], bool],
    _attach_dialog_tracking: Callable[[Any], None],
    _close_tracked_dialog: Callable[[Any], None],
    _calc_zus_progress: Callable[[pd.Series], tuple[int, int, list[str], list[bool]]],
    _enforce_admin_uncheck_rule: Callable[..., tuple[list[bool], bool]],
    db_exec: Callable[..., Any],
    _encode_check_list: Callable[[list[bool]], str],
    _open_tracked_dialog: Callable[[Any], None],
) -> None:
    row = _find_open_task_row(task_id, get_open_tasks_df)
    admin = is_admin()
    with ui.dialog() as dialog, ui.card().classes("dialog-card"):
        _attach_dialog_tracking(dialog)
        dialog.props("persistent")
        if row is None:
            ui.label("Auftrag nicht gefunden (ggf. bereits archiviert).")
            ui.button("Schließen", on_click=lambda d=dialog: _close_tracked_dialog(d)).props("color=primary")
        else:
            fahrzeug = str(row.get("Fahrzeug") or f"ID {task_id}")
            done, total, items, bits = _calc_zus_progress(row)
            ui.label(f"Zusatzarbeiten - {fahrzeug}").classes("dialog-title")
            if total == 0:
                ui.label("Für diesen Auftrag sind keine Zusatzarbeiten hinterlegt.").classes("text-gray-300")
                ui.button("Schließen", on_click=lambda d=dialog: _close_tracked_dialog(d)).props("color=primary")
            else:
                ui.label(f"Fortschritt: {done}/{total} erledigt").classes("dialog-progress")
                checks = []
                old_bits = list(bits)
                for i, txt in enumerate(items):
                    old_val = bool(bits[i]) if i < len(bits) else False
                    lock_uncheck = (not admin) and old_val
                    cb_classes = "dialog-check"
                    if old_val:
                        cb_classes += " dialog-check-done"
                    cb = ui.checkbox(txt.replace("\n", " / "), value=old_val).classes(cb_classes)
                    if lock_uncheck:
                        cb.disable()
                    checks.append(cb)
                with ui.row().classes("w-full justify-end gap-2 mt-3"):
                    ui.button("Abbrechen", on_click=lambda d=dialog: _close_tracked_dialog(d)).props("flat")

                    def save() -> None:
                        raw_bits = [bool(cb.value) for cb in checks]
                        new_bits, blocked = _enforce_admin_uncheck_rule(old_bits, raw_bits, admin=admin)
                        if blocked:
                            ui.notify("Abhaken kann nur als Admin rückgängig gemacht werden.", type="warning")
                        db_exec(
                            "UPDATE open_tasks SET zusatz_done=? WHERE id=?;",
                            (_encode_check_list(new_bits), int(task_id)),
                            commit=True,
                        )
                        ui.notify("Zusatzarbeiten aktualisiert.", type="positive")
                        _close_tracked_dialog(dialog)
                        refresh_fn()

                    ui.button("Speichern", on_click=save).props("color=primary")
    _open_tracked_dialog(dialog)



def open_frist_dialog(
    task_id: int,
    area_code: str,
    refresh_fn: Callable[[], None],
    *,
    get_open_tasks_df: Callable[[], pd.DataFrame],
    is_admin: Callable[[], bool],
    _attach_dialog_tracking: Callable[[Any], None],
    _close_tracked_dialog: Callable[[Any], None],
    _calc_frist_progress: Callable[..., tuple[int, int, list[str], list[bool], bool]],
    _enforce_admin_uncheck_rule: Callable[..., tuple[list[bool], bool]],
    db_exec: Callable[..., Any],
    _encode_check_list: Callable[[list[bool]], str],
    _decode_check_string: Callable[[Any, int], list[bool]],
    _open_tracked_dialog: Callable[[Any], None],
) -> None:
    row = _find_open_task_row(task_id, get_open_tasks_df)
    admin = is_admin()
    with ui.dialog() as dialog, ui.card().classes("dialog-card"):
        _attach_dialog_tracking(dialog)
        dialog.props("persistent")
        if row is None:
            ui.label("Auftrag nicht gefunden (ggf. bereits archiviert).")
            ui.button("Schließen", on_click=lambda d=dialog: _close_tracked_dialog(d)).props("color=primary")
        else:
            fahrzeug = str(row.get("Fahrzeug") or f"ID {task_id}")
            done, total, items, bits, applicable = _calc_frist_progress(row, area_code=area_code)
            work_bits = _decode_check_string(row.get("frist_in_progress"), total)
            ui.label(f"Fristarbeiten - {fahrzeug}").classes("dialog-title")
            if (not applicable) or total == 0:
                ui.label("Für diesen Auftrag sind keine Fristarbeiten vorgesehen.").classes("text-gray-300")
                ui.button("Schließen", on_click=lambda d=dialog: _close_tracked_dialog(d)).props("color=primary")
            else:
                with ui.row().classes("w-full items-center gap-3 wrap"):
                    ui.label(f"Fortschritt: {done}/{total} erledigt").classes("dialog-progress")
                    rest_label = ui.label(
                        f"Reststunden: {_format_hours_text(_remaining_frist_minutes(items, bits))}"
                    ).classes("dialog-progress")
                checks = []
                work_checks = []
                old_bits = list(bits)
                old_work_bits = list(work_bits)

                def refresh_rest_label() -> None:
                    current_done = [bool(cb.value) for cb in checks]
                    rest_label.set_text(f"Reststunden: {_format_hours_text(_remaining_frist_minutes(items, current_done))}")

                def apply_line_state(title_label, meta_label, *, done: bool, working: bool) -> None:
                    for label in (title_label, meta_label):
                        if label is None:
                            continue
                        label.classes(remove="dialog-check-done dialog-check-working")
                        if done:
                            label.classes("dialog-check-done")
                        elif working:
                            label.classes("dialog-check-working")

                with ui.row().classes("w-full dialog-frist-header no-wrap"):
                    ui.label("In Bearbeitung").classes("dialog-frist-head dialog-frist-work-head")
                    ui.element("span").classes("dialog-frist-head-spacer")
                    ui.label("Erledigt").classes("dialog-frist-head dialog-frist-done-head")
                for i, txt in enumerate(items):
                    old_val = bool(bits[i]) if i < len(bits) else False
                    old_work_val = bool(old_work_bits[i]) if i < len(old_work_bits) else False
                    lock_uncheck = (not admin) and old_val
                    work_val = old_work_val and not old_val
                    title, details = _split_check_item_text(txt)
                    with ui.row().classes("w-full items-start gap-2 no-wrap dialog-check-row dialog-frist-check-row"):
                        work_cb = ui.checkbox(value=work_val).props("dense").classes("dialog-work-check")
                        with ui.column().classes("grow gap-0"):
                            title_classes = "dialog-check-title"
                            if old_val:
                                title_classes += " dialog-check-done"
                            elif work_val:
                                title_classes += " dialog-check-working"
                            title_label = ui.label(title).classes(title_classes)
                            meta_label = None
                            if details:
                                meta_classes = "dialog-check-meta"
                                if old_val:
                                    meta_classes += " dialog-check-done"
                                elif work_val:
                                    meta_classes += " dialog-check-working"
                                meta_label = ui.label(details).classes(meta_classes)
                        cb = ui.checkbox(value=old_val).props("dense").classes("dialog-check-box dialog-done-check")
                    if lock_uncheck:
                        cb.disable()
                    if old_val:
                        work_cb.disable()
                    def on_work_change(event, done_control=cb, title_control=title_label, meta_control=meta_label) -> None:
                        apply_line_state(
                            title_control,
                            meta_control,
                            done=bool(done_control.value),
                            working=bool(event.value) and not bool(done_control.value),
                        )

                    def on_done_change(
                        event,
                        work_control=work_cb,
                        title_control=title_label,
                        meta_control=meta_label,
                    ) -> None:
                        done_value = bool(event.value)
                        if done_value:
                            work_control.value = False
                            work_control.disable()
                        else:
                            work_control.enable()
                        apply_line_state(
                            title_control,
                            meta_control,
                            done=done_value,
                            working=bool(work_control.value) and not done_value,
                        )
                        refresh_rest_label()

                    work_cb.on_value_change(on_work_change)
                    cb.on_value_change(on_done_change)
                    checks.append(cb)
                    work_checks.append(work_cb)
                with ui.row().classes("w-full justify-end gap-2 mt-3"):
                    ui.button("Abbrechen", on_click=lambda d=dialog: _close_tracked_dialog(d)).props("flat")

                    def save() -> None:
                        raw_bits = [bool(cb.value) for cb in checks]
                        new_bits, blocked = _enforce_admin_uncheck_rule(old_bits, raw_bits, admin=admin)
                        if blocked:
                            ui.notify("Abhaken kann nur als Admin rückgängig gemacht werden.", type="warning")
                        new_work_bits = [
                            bool(work_cb.value) and not bool(new_bits[index])
                            for index, work_cb in enumerate(work_checks)
                        ]
                        db_exec(
                            "UPDATE open_tasks SET frist_done=?, frist_in_progress=? WHERE id=?;",
                            (_encode_check_list(new_bits), _encode_check_list(new_work_bits), int(task_id)),
                            commit=True,
                        )
                        ui.notify("Fristarbeiten aktualisiert.", type="positive")
                        _close_tracked_dialog(dialog)
                        refresh_fn()

                    ui.button("Speichern", on_click=save).props("color=primary")
    _open_tracked_dialog(dialog)



def open_problem_dialog(
    task_id: int,
    refresh_fn: Callable[[], None],
    *,
    get_open_tasks_df: Callable[[], pd.DataFrame],
    _attach_dialog_tracking: Callable[[Any], None],
    _close_tracked_dialog: Callable[[Any], None],
    PROBLEM_OPTIONS: list[str],
    pin_problem: Callable[[int, str], None],
    _build_delay_payload: Callable[..., dict[str, Any]],
    notify_delay: Callable[[dict[str, Any]], tuple[bool, str]],
    _open_tracked_dialog: Callable[[Any], None],
) -> None:
    def _close_problem_dialog(dialog_ref) -> None:
        _close_tracked_dialog(dialog_ref)

    row = _find_open_task_row(task_id, get_open_tasks_df)
    with ui.dialog() as dialog, ui.card().classes("dialog-card"):
        _attach_dialog_tracking(dialog)
        dialog.props("persistent")
        if row is None:
            ui.label("Auftrag nicht gefunden (ggf. bereits archiviert).")
            ui.button("Schließen", on_click=lambda d=dialog: _close_problem_dialog(d)).props("color=primary")
        else:
            fahrzeug = str(row.get("Fahrzeug") or f"ID {task_id}")
            ui.label(f"Verzögerung melden - {fahrzeug}").classes("dialog-title")
            checkboxes = []
            for label in PROBLEM_OPTIONS:
                checkboxes.append((label, ui.checkbox(label).classes("dialog-check")))
            txt = ui.textarea(label="Zusätzliche Beschreibung (optional)").props("outlined").classes("w-full")
            with ui.row().classes("w-full justify-end gap-2 mt-3"):
                ui.button("Abbrechen", on_click=lambda d=dialog: _close_problem_dialog(d)).props("flat")

                def save() -> None:
                    parts = [lbl for lbl, cb in checkboxes if bool(cb.value)]
                    free = str(txt.value or "").strip()
                    if free:
                        parts.append(free)
                    if not parts:
                        ui.notify("Bitte mindestens eine Option oder Text angeben.", type="warning")
                        return
                    chosen = [lbl for lbl, cb in checkboxes if bool(cb.value)]
                    combined = ", ".join(parts)
                    pin_problem(int(task_id), combined)
                    payload = _build_delay_payload(
                        int(task_id),
                        combined,
                        options=chosen,
                        free_text=free,
                        source="verzoegerung_dialog",
                    )
                    ok, info = notify_delay(payload)
                    if ok:
                        ui.notify(f"Gespeichert + Benachrichtigung gesendet. ({info})", type="positive")
                    elif "NOTIFY_FLOW_URL fehlt" in str(info or ""):
                        ui.notify(
                            "Gespeichert. Benachrichtigung ist deaktiviert (NOTIFY_FLOW_URL fehlt).",
                            type="positive",
                        )
                    else:
                        ui.notify(f"Gespeichert, aber Benachrichtigung fehlgeschlagen: {info}", type="warning")
                    _close_problem_dialog(dialog)
                    refresh_fn()

                ui.button("Speichern", on_click=save).props("color=warning")
    _open_tracked_dialog(dialog)



def _extract_existing_problem_labels(note_text: str, PROBLEM_OPTIONS: list[str]) -> list[str]:
    if not note_text:
        return []
    low = str(note_text or "").lower()
    found: list[str] = []
    for opt in PROBLEM_OPTIONS:
        if opt.lower() in low:
            found.append(opt)
    seen: set[str] = set()
    out: list[str] = []
    for x in found:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out



def open_overdue_dialog_for(
    task_id: int,
    refresh_fn: Callable[[], None],
    *,
    db_exec: Callable[..., Any],
    _planned_deadline_dt: Callable[..., Any],
    _clean_problem_note: Callable[[Any], str],
    PROBLEM_OPTIONS: list[str],
    pin_problem: Callable[[int, str], None],
    archive_task: Callable[[int], tuple[bool, str]],
    _archive_notify_type: Callable[[bool, str], str],
    _attach_dialog_tracking: Callable[[Any], None],
    _close_tracked_dialog: Callable[[Any], None],
    _open_tracked_dialog: Callable[[Any], None],
) -> None:
    open_overdue_dialog(
        int(task_id),
        refresh_fn,
        db_exec=db_exec,
        _planned_deadline_dt=_planned_deadline_dt,
        _clean_problem_note=_clean_problem_note,
        PROBLEM_OPTIONS=PROBLEM_OPTIONS,
        pin_problem=pin_problem,
        archive_task=archive_task,
        _archive_notify_type=_archive_notify_type,
        _attach_dialog_tracking=_attach_dialog_tracking,
        _close_tracked_dialog=_close_tracked_dialog,
        _open_tracked_dialog=_open_tracked_dialog,
    )



def open_overdue_dialog(
    task_id: int,
    refresh_fn: Callable[[], None],
    *,
    db_exec: Callable[..., Any],
    _planned_deadline_dt: Callable[..., Any],
    _clean_problem_note: Callable[[Any], str],
    PROBLEM_OPTIONS: list[str],
    pin_problem: Callable[[int, str], None],
    archive_task: Callable[[int], tuple[bool, str]],
    _archive_notify_type: Callable[[bool, str], str],
    _attach_dialog_tracking: Callable[[Any], None],
    _close_tracked_dialog: Callable[[Any], None],
    _open_tracked_dialog: Callable[[Any], None],
) -> None:
    def _close_overdue_dialog(dialog_ref) -> None:
        _close_tracked_dialog(dialog_ref)

    row = db_exec(
        """
        SELECT fahrzeug, friststufe, fertig, last_problem_note, initial_fertig
        FROM open_tasks
        WHERE id=?;
        """,
        (int(task_id),),
        fetchone=True,
    )
    if not row:
        ui.notify("Datensatz nicht gefunden.", type="warning")
        return

    fzg = str(row["fahrzeug"] or "")
    frist = str(row["friststufe"] or "")
    end_dt = _planned_deadline_dt(row["fertig"])
    init_dt = _planned_deadline_dt(row["initial_fertig"], row["fertig"])
    note_raw = _clean_problem_note(row["last_problem_note"])
    end_txt = end_dt.strftime("%d.%m.%Y %H:%M") if end_dt else "-"
    init_txt = init_dt.strftime("%d.%m.%Y %H:%M") if init_dt else "-"
    existing = _extract_existing_problem_labels(note_raw, PROBLEM_OPTIONS)
    remaining = [x for x in PROBLEM_OPTIONS if x not in existing]

    with ui.dialog() as dialog, ui.card().classes("dialog-card"):
        _attach_dialog_tracking(dialog)
        dialog.props("persistent")
        ui.label("Verspätungsgrund angeben").classes("dialog-title")
        ui.label(f"Fahrzeug: {fzg}").classes("text-sm")
        ui.label(f"Frist: {frist or '-'}").classes("text-sm")
        ui.label(f"Ursprüngliche Fertigstellung: {init_txt}").classes("text-sm")
        ui.label(f"Aktuelles geplantes Ende: {end_txt}").classes("text-sm")
        ui.separator()

        exist_checks: list[tuple[str, Any]] = []
        if existing:
            ui.label("Bereits gemeldete Probleme").classes("font-bold")
            for label in existing:
                exist_checks.append((label, ui.checkbox(label)))

        new_checks: list[tuple[str, Any]] = []
        ui.label("Weitere Optionen").classes("font-bold")
        if remaining:
            for label in remaining:
                new_checks.append((label, ui.checkbox(label)))
        else:
            ui.label("Keine weiteren Optionen verfügbar.").classes("text-gray-400")

        txt = ui.textarea("Zusätzliche Beschreibung (optional)").props("outlined").classes("w-full")
        with ui.row().classes("w-full justify-end gap-2 mt-3"):
            ui.button("Abbrechen", on_click=lambda d=dialog: _close_overdue_dialog(d)).props("flat")

            def save_and_archive() -> None:
                parts = [lbl for lbl, cb in exist_checks if bool(cb.value)]
                parts.extend(lbl for lbl, cb in new_checks if bool(cb.value))
                free = str(txt.value or "").strip()
                if free:
                    parts.append(free)
                if not parts:
                    ui.notify("Bitte mindestens eine Option oder Beschreibung angeben.", type="warning")
                    return
                pin_problem(int(task_id), "Verspätungsgrund: " + ", ".join(parts))
                ok, msg = archive_task(int(task_id))
                ui.notify(msg, type=_archive_notify_type(ok, msg))
                _close_overdue_dialog(dialog)
                refresh_fn()

            ui.button("Speichern & archivieren", on_click=save_and_archive).props("color=primary")
    _open_tracked_dialog(dialog)



def open_new_order_dialog(
    refresh_fn: Callable[[], None],
    *,
    _attach_dialog_tracking: Callable[[Any], None],
    _close_tracked_dialog: Callable[[Any], None],
    _open_tracked_dialog: Callable[[Any], None],
    now_berlin: Callable[[], datetime],
    _get_existing_open_by_vehicle: Callable[[str], Any],
    as_berlin: Callable[[Any], Any],
    BERLIN: Any,
    create_or_update_open_task_manual: Callable[..., None],
) -> None:
    with ui.dialog() as dialog, ui.card().classes("dialog-card"):
        _attach_dialog_tracking(dialog)
        dialog.props("persistent")
        ui.label("Neuer Auftrag").classes("dialog-title")
        ui.label("Fahrzeug eintragen und optional Zusatzarbeiten erfassen.").classes("text-gray-300")

        fzg_input = ui.input("Fahrzeug*").props("outlined").classes("w-full")
        info_lbl = ui.label("").classes("text-sm text-gray-300")
        end_mode = ui.select(
            {
                "keep": "Aktuelles Ende behalten",
                "new": "Neues Ende festlegen",
            },
            value="new",
            label="Voraussichtliche Fertigstellung",
        ).props("outlined").classes("w-full")
        end_date = ui.date(value=now_berlin().date().isoformat()).props("mask=YYYY-MM-DD")
        end_time = ui.input("Uhrzeit (HH:MM)", value=(now_berlin() + timedelta(hours=8)).strftime("%H:%M")).props("outlined")
        zus_txt = ui.textarea(
            label="Störungen / Zusatzarbeiten (eine Zeile pro Position)",
            placeholder="- Text 1\n- Text 2",
        ).props("outlined").classes("w-full")

        def refresh_existing_info() -> None:
            fzg = str(fzg_input.value or "").strip()
            if not fzg:
                info_lbl.set_text("Bitte zuerst ein Fahrzeug eintragen.")
                end_mode.value = "new"
                return
            existing = _get_existing_open_by_vehicle(fzg)
            if not existing:
                info_lbl.set_text("Neues Fahrzeug: Frist wird als 'Störung' angelegt.")
                end_mode.value = "new"
                return
            end_raw = existing["fertig"]
            end_dt = as_berlin(pd.to_datetime(end_raw, errors="coerce"))
            end_txt = end_dt.strftime("%d.%m.%Y %H:%M") if end_dt else "-"
            info_lbl.set_text(f"Bereits vorhanden. Aktuelles Ende: {end_txt}")

        fzg_input.on_value_change(lambda _e: refresh_existing_info())
        refresh_existing_info()

        with ui.row().classes("w-full justify-end gap-2 mt-3"):
            ui.button("Abbrechen", on_click=lambda d=dialog: _close_tracked_dialog(d)).props("flat")

            def save_new_order() -> None:
                fzg = str(fzg_input.value or "").strip()
                if not fzg:
                    ui.notify("Bitte Fahrzeug eintragen.", type="warning")
                    return

                existing = _get_existing_open_by_vehicle(fzg)
                mode = str(end_mode.value or "new")
                if not existing:
                    mode = "new"

                d_raw = str(end_date.value or "").strip()
                t_raw = str(end_time.value or "").strip()
                ende_dt: datetime | None = None
                if mode == "new":
                    try:
                        d_val = date.fromisoformat(d_raw[:10])
                        if not re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?", t_raw):
                            raise ValueError("Uhrzeit ungültig")
                        parts = [int(x) for x in t_raw.split(":")]
                        h = parts[0]
                        m = parts[1]
                        ende_dt = datetime.combine(d_val, time(h, m), tzinfo=BERLIN)
                    except Exception:
                        ui.notify("Bitte gültiges Datum und Uhrzeit (HH:MM) angeben.", type="warning")
                        return

                lines = [ln.strip() for ln in str(zus_txt.value or "").splitlines() if ln.strip()]
                zus_payload = "\n".join(ln if ln.startswith("-") else f"- {ln}" for ln in lines)
                try:
                    create_or_update_open_task_manual(
                        fzg,
                        end_mode=mode,
                        ende_dt=ende_dt,
                        zusatz=zus_payload,
                    )
                    ui.notify("Auftrag gespeichert.", type="positive")
                    _close_tracked_dialog(dialog)
                    refresh_fn()
                except Exception as ex:
                    ui.notify(f"Konnte Auftrag nicht speichern: {ex}", type="negative")

            ui.button("Speichern", on_click=save_new_order).props("color=primary")

    _open_tracked_dialog(dialog)
