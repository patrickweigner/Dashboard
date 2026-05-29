from __future__ import annotations

from typing import Any, Callable

import pandas as pd
from nicegui import ui


def _split_check_item_text(value: Any) -> tuple[str, str]:
    lines = [line.strip() for line in str(value or "").splitlines() if line.strip()]
    if not lines:
        return "", ""
    return lines[0], " - ".join(lines[1:])


def render_legend() -> None:
    with ui.row().classes("w-full legend-row"):
        for text, cls in [
            ("Grün = im Plan", "legend-green"),
            ("Gelb = < 24 Std.", "legend-yellow"),
            ("Gelb = Problem gemeldet", "legend-yellow-problem"),
            ("Rot = überfällig", "legend-red"),
        ]:
            with ui.row().classes("items-center gap-2 legend-item"):
                ui.element("span").classes(f"legend-pill {cls}")
                ui.label(text).classes("legend-text")


def _source_label(value: Any) -> tuple[str, str, str] | None:
    raw = str(value or "").strip().lower()
    if raw == "planner":
        return ("Planner", "#dbeafe", "#1e3a8a")
    if raw == "open_tasks_manual":
        return ("Manuelle Anlage", "#fef3c7", "#92400e")
    if raw == "upload_legacy":
        return ("Legacy-Upload", "#e5e7eb", "#374151")
    return None


def build_task_card(
    row: pd.Series,
    refresh_fn,
    *,
    show_area_controls: bool = False,
    fmt_dt: Callable[[Any], str],
    effective_area: Callable[..., str],
    display_workplace: Callable[[pd.Series], str],
    status_for_row: Callable[..., tuple[str, str]],
    status_palette: Callable[[str], tuple[str, str]],
    calc_zus_progress: Callable[[pd.Series], tuple[int, int, list[str], list[bool]]],
    calc_frist_progress: Callable[..., tuple[int, int, list[str], list[bool], bool]],
    decode_check_string: Callable[[Any, int], list[bool]],
    clean_problem_note: Callable[[Any], str],
    as_berlin: Callable[[Any], Any],
    is_admin: Callable[[], bool],
    enforce_admin_uncheck_rule: Callable[..., tuple[list[bool], bool]],
    db_exec: Callable[..., Any],
    encode_check_list: Callable[[list[bool]], str],
    render_badge_stack: Callable[..., Any],
    workshop_areas: list[str],
    assign_area: Callable[[int, str], tuple[bool, str]],
    complete_task_action: Callable[[int, Callable[[], None]], None],
    open_zus_dialog: Callable[[int, Callable[[], None]], None],
    open_frist_dialog: Callable[[int, str, Callable[[], None]], None],
    open_problem_dialog: Callable[..., None],
    inject_due24_watcher: Callable[..., None],
    format_problem_lines: Callable[..., list[str]],
    render_pill_label: Callable[..., Any],
) -> None:
    rid = int(row["id"])
    fzg = str(row.get("Fahrzeug") or "")
    frist = str(row.get("Friststufe") or "") or "-"
    st_txt = fmt_dt(row.get("Anfang"))
    end_txt = fmt_dt(row.get("Fertig"))
    area_manual = effective_area(row, allow_pdf_fallback=False)
    area_display = display_workplace(row)

    status_key, status_text = status_for_row(row)
    stat_bg, stat_fg = status_palette(status_key)
    done_zus, total_zus, zus_items, zus_bits = calc_zus_progress(row)
    done_fr, total_fr, fr_items, fr_bits, fr_app = calc_frist_progress(row, area_code=None)
    fr_work_bits = decode_check_string(row.get("frist_in_progress"), total_fr)
    note = clean_problem_note(row.get("last_problem_note"))
    has_problem = bool(note)
    end_dt = as_berlin(row.get("Fertig"))
    admin = bool(is_admin())
    source_info = _source_label(row.get("source_system"))

    veh_id = None
    end_id = None
    status_id = None
    workshop_area_options = list(workshop_areas)

    def _render_inline_check_list(
        *,
        column_name: str,
        items: list[str],
        bits: list[bool],
        work_bits: list[bool] | None = None,
    ) -> None:
        if not items:
            return

        old_bits = list(bits)
        checks: list[Any] = []
        work_checks: list[Any] = []

        def persist() -> None:
            raw_bits = [bool(cb.value) for cb in checks]
            new_bits, blocked = enforce_admin_uncheck_rule(old_bits, raw_bits, admin=admin)
            if blocked:
                ui.notify("Abhaken kann nur als Admin rückgängig gemacht werden.", type="warning")
            if column_name == "frist_done":
                current_work_bits = [bool(cb.value) for cb in work_checks]
                new_work_bits = [
                    bool(current_work_bits[index]) and not bool(done)
                    for index, done in enumerate(new_bits)
                ]
                db_exec(
                    "UPDATE open_tasks SET frist_done=?, frist_in_progress=? WHERE id=?;",
                    (encode_check_list(new_bits), encode_check_list(new_work_bits), rid),
                    commit=True,
                )
                row["frist_in_progress"] = encode_check_list(new_work_bits)
            else:
                db_exec(
                    f"UPDATE open_tasks SET {column_name}=? WHERE id=?;",
                    (encode_check_list(new_bits), rid),
                    commit=True,
                )
            row[column_name] = encode_check_list(new_bits)
            old_bits[:] = new_bits
            refresh_fn()

        def persist_work() -> None:
            raw_bits = [
                bool(cb.value) and not bool(old_bits[index] if index < len(old_bits) else False)
                for index, cb in enumerate(work_checks)
            ]
            db_exec(
                "UPDATE open_tasks SET frist_in_progress=? WHERE id=?;",
                (encode_check_list(raw_bits), rid),
                commit=True,
            )
            row["frist_in_progress"] = encode_check_list(raw_bits)
            refresh_fn()

        with ui.column().classes("w-full gap-1 mt-2 task-check-list"):
            if column_name == "frist_done":
                with ui.row().classes("w-full task-frist-header no-wrap"):
                    ui.label("In Bearbeitung").classes("task-frist-head task-frist-work-head")
                    ui.element("span").classes("task-frist-head-spacer")
                    ui.label("Erledigt").classes("task-frist-head task-frist-done-head")
            for idx, txt in enumerate(items):
                old_val = bool(old_bits[idx]) if idx < len(old_bits) else False
                lock_uncheck = (not admin) and old_val
                work_val = bool((work_bits or [])[idx]) if work_bits is not None and idx < len(work_bits) else False
                work_val = work_val and not old_val
                row_classes = "w-full items-start gap-2 no-wrap task-check-row"
                if column_name == "frist_done":
                    row_classes += " task-frist-check-row"
                with ui.row().classes(row_classes):
                    if column_name == "frist_done":
                        work_cb = ui.checkbox(value=work_val, on_change=lambda _e: persist_work()).props("dense")
                        work_cb.classes("task-check-box task-work-box")
                        if old_val:
                            work_cb.disable()
                        work_checks.append(work_cb)
                        title, details = _split_check_item_text(txt)
                        with ui.column().classes("task-check-copy grow gap-0"):
                            title_classes = "task-check-text task-check-title"
                            if old_val:
                                title_classes += " task-check-done"
                            elif work_val:
                                title_classes += " task-check-working"
                            ui.label(title).classes(title_classes)
                            if details:
                                meta_classes = "task-check-meta"
                                if old_val:
                                    meta_classes += " task-check-done"
                                elif work_val:
                                    meta_classes += " task-check-working"
                                ui.label(details).classes(meta_classes)
                    else:
                        text_classes = "task-check-text grow"
                        if old_val:
                            text_classes += " task-check-done"
                        ui.label(str(txt).replace("\n", " / ")).classes(text_classes)
                    cb = ui.checkbox(value=old_val, on_change=lambda _e: persist()).props("dense")
                    cb.classes("task-check-box task-done-box" if column_name == "frist_done" else "task-check-box")
                    if lock_uncheck:
                        cb.disable()
                    checks.append(cb)

    with ui.card().classes("task-shell open-task-card"):
        with ui.row().classes("w-full items-start gap-3 no-wrap open-task-grid"):
            with ui.column().classes("task-col task-col-fzg task-col-ratio-22"):
                veh_badge = render_badge_stack("Fahrzeug", fzg or "-", stat_bg, stat_fg, big=True)
                veh_id = veh_badge.html_id
                with ui.column().classes("w-full gap-2 mt-2"):
                    _render_inline_check_list(
                        column_name="zusatz_done",
                        items=zus_items,
                        bits=zus_bits,
                    )

            with ui.column().classes("task-col task-col-ratio-13"):
                render_badge_stack("Frist", frist, "#f0f2f5", "#000000", big=True)
                with ui.column().classes("w-full gap-2 mt-2"):
                    if fr_app:
                        _render_inline_check_list(
                            column_name="frist_done",
                            items=fr_items,
                            bits=fr_bits,
                            work_bits=fr_work_bits,
                        )

            with ui.column().classes("task-col task-col-ratio-13"):
                render_badge_stack("Start", st_txt, "#f0f2f5", "#000000", big=True)

            with ui.column().classes("task-col task-col-ratio-16"):
                end_badge = render_badge_stack("Ende", end_txt, stat_bg, stat_fg, big=True)
                end_id = end_badge.html_id
                status_badge = render_pill_label(
                    status_text,
                    stat_bg,
                    stat_fg,
                    classes="task-status slot-pill",
                    extra="display:inline-flex",
                )
                status_id = status_badge.html_id
                if source_info:
                    src_label, src_bg, src_fg = source_info
                    render_pill_label(
                        src_label,
                        src_bg,
                        src_fg,
                        classes="task-status slot-pill mt-2",
                        extra="display:inline-flex",
                    )

            with ui.column().classes("task-col task-col-ratio-12"):
                render_badge_stack("Arbeitsplatz", area_display or "-", "#f0f2f5", "#000000", big=True)
                if show_area_controls:
                    area_select = ui.select(
                        options=[""] + workshop_area_options,
                        value=area_manual if area_manual in workshop_area_options else "",
                        label="Bereich",
                    ).props("outlined dense").classes("w-full mt-2")

                    def save_area() -> None:
                        ok, msg = assign_area(rid, str(area_select.value or ""))
                        ui.notify(msg, type="positive" if ok else "negative")
                        refresh_fn()

                    ui.button("Bereich speichern", on_click=save_area).classes("btn-big mt-1")

            with ui.column().classes("task-actions task-col-ratio-09"):
                def done_task() -> None:
                    complete_task_action(rid, refresh_fn)

                ui.button("Erledigt", icon="check_circle", on_click=done_task).classes("btn-big btn-done")
                ui.button(
                    "Verzögerung melden",
                    icon="report_problem",
                    on_click=lambda rid=rid: open_problem_dialog(rid, refresh_fn),
                ).classes("btn-big btn-warn")

        if end_dt:
            inject_due24_watcher(
                end_dt,
                veh_id=veh_id,
                end_id=end_id,
                status_id=status_id,
                has_problem=has_problem,
            )

        if note:
            with ui.element("div").classes("problem-box problemline w-full"):
                ui.label("Problem(e):").classes("font-bold")
                for line in format_problem_lines(note):
                    ui.label(line).classes("text-sm")
