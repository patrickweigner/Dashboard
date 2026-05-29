from __future__ import annotations

from datetime import timedelta
from typing import Any, Callable

import pandas as pd
from nicegui import ui

from core.ui_runtime import create_page_timer
from services.gleisplan_service import HALL_TRACK_LABELS, load_gleisplan_hall_tracks, ordered_hall_track_codes
from services.workshop_config_service import load_workshop_hall_config, load_workshop_hall_texts


_MAIN_HALL_POSITIONS: tuple[str, str, str, str] = ("oben links", "oben rechts", "unten links", "unten rechts")


def _hall_position_index(value: Any, fallback: int) -> int:
    text = str(value or "").strip().casefold()
    aliases = {
        "oben links": 0,
        "links oben": 0,
        "top left": 0,
        "oben rechts": 1,
        "rechts oben": 1,
        "top right": 1,
        "unten links": 2,
        "links unten": 2,
        "bottom left": 2,
        "unten rechts": 3,
        "rechts unten": 3,
        "bottom right": 3,
    }
    return aliases.get(text, max(0, min(3, int(fallback or 0))))


def _workshop_hall_slots(
    hall_tracks: dict[str, dict[str, Any]],
    workshop_areas: list[str],
) -> list[dict[str, str]]:
    main_areas = {"4A", "4B", "5A", "5B"}
    configured: list[tuple[int, dict[str, str]]] = []
    for default_index, track_code in enumerate(ordered_hall_track_codes(hall_tracks)):
        config = hall_tracks.get(track_code) or {}
        workshop_area = str(config.get("workshop_area") or track_code).strip().upper()
        if workshop_area not in main_areas or workshop_area not in {str(area).strip().upper() for area in workshop_areas}:
            continue
        fallback_position = HALL_TRACK_LABELS.get(track_code, "")
        position_index = _hall_position_index(config.get("position_label") or fallback_position, default_index)
        configured.append(
            (
                position_index,
                {
                    "key": str(track_code).strip().upper(),
                    "area_code": workshop_area,
                    "display_label": str(config.get("track_label") or track_code).strip() or track_code,
                },
            )
        )

    slots: list[dict[str, str] | None] = [None, None, None, None]
    overflow: list[dict[str, str]] = []
    for position_index, slot in sorted(configured, key=lambda item: (item[0], item[1]["key"])):
        if 0 <= position_index < len(slots) and slots[position_index] is None:
            slots[position_index] = slot
        else:
            overflow.append(slot)

    for index, slot in enumerate(list(slots)):
        if slot is None and overflow:
            slots[index] = overflow.pop(0)

    fallback_by_position = [
        {"key": "4B", "area_code": "4B", "display_label": "4B"},
        {"key": "4A", "area_code": "4A", "display_label": "4A"},
        {"key": "5A", "area_code": "5A", "display_label": "5A"},
        {"key": "5B", "area_code": "5B", "display_label": "5B"},
    ]
    for index, fallback in enumerate(fallback_by_position):
        if slots[index] is None:
            slots[index] = fallback
    return [slot for slot in slots if slot is not None]


def render(
    *,
    refresh_interval_seconds: float,
    render_nav: Callable[[], None],
    open_ausseneinsatz_dialog: Callable[[Any], None],
    shift_day: Callable[[Any], Any],
    now_berlin: Callable[[], Any],
    current_slot_vehicle_color: str,
    workshop_areas: list[str],
    is_admin: Callable[[], bool],
    get_open_tasks_df: Callable[[], pd.DataFrame],
    current_slot_vehicle_keys_from_ecm4: Callable[[], set[str]],
    fmt_dt: Callable[[Any], str],
    find_other_assigned_rows_for_same_vehicle: Callable[..., list[dict[str, Any]]],
    db_exec: Callable[..., Any],
    normalize_workshop_area: Callable[[Any], str],
    assign_vehicle_to_area_with_shift: Callable[..., tuple[bool, str]],
    row_allows_area: Callable[[pd.Series, str], bool],
    assign_area: Callable[[int, str], tuple[bool, str]],
    as_berlin: Callable[[Any], Any],
    norm_vehicle: Callable[[str], str],
    clean_problem_note: Callable[[Any], str],
    status_for_row: Callable[..., tuple[str, str]],
    status_palette: Callable[[str], tuple[str, str]],
    calc_frist_progress: Callable[..., tuple[int, int, list[str], list[bool], bool]],
    calc_zus_progress: Callable[..., tuple[int, int, list[str], list[bool]]],
    render_pill_label: Callable[..., Any],
    badge_style: Callable[..., str],
    format_problem_lines: Callable[..., list[str]],
    inject_due24_watcher: Callable[..., None],
    complete_task_action: Callable[[int, Callable[[], None]], None],
    open_frist_dialog: Callable[..., None],
    open_zus_dialog: Callable[..., None],
    open_problem_dialog: Callable[..., None],
    render_countdown_badge: Callable[..., None],
    has_open_dialog: Callable[[], bool],
) -> None:
    WORKSHOP_AREAS = workshop_areas
    CURRENT_SLOT_VEHICLE_COLOR = current_slot_vehicle_color
    _shift_day = shift_day
    _current_slot_vehicle_keys_from_ecm4 = current_slot_vehicle_keys_from_ecm4
    _normalize_workshop_area = normalize_workshop_area
    _row_allows_area = row_allows_area
    _norm_vehicle = norm_vehicle
    _clean_problem_note = clean_problem_note
    _calc_frist_progress = calc_frist_progress
    _calc_zus_progress = calc_zus_progress
    _badge_style = badge_style
    _has_open_dialog = has_open_dialog
    initial_texts = load_workshop_hall_texts(db_exec)
    render_nav()

    with ui.column().classes("w-full werkstatthalle-page"):
        with ui.column().classes("w-full gap-2 workshop-command-row"):
            ui.label(initial_texts.get("page_title") or "Werkstatthalle").classes("page-title workshop-page-title")
            with ui.row().classes("items-center gap-3 wrap workshop-command-tools"):
                ui.button(
                    initial_texts.get("external_button") or "Außeneinsatz",
                    icon="engineering",
                    on_click=lambda: open_ausseneinsatz_dialog(_shift_day(now_berlin())),
                ).classes("btn-big workshop-external-btn")
                with ui.row().classes("items-center gap-2 legend-item workshop-legend"):
                    ui.element("span").classes("legend-pill").style(
                        f"background:{CURRENT_SLOT_VEHICLE_COLOR};background-color:{CURRENT_SLOT_VEHICLE_COLOR};"
                    )
                    legend_text = initial_texts.get("legend_current_vehicle") or "Gelb = aktuell zu bearbeitendes Fahrzeug"
                    ui.label(legend_text).classes("legend-text")

        body = ui.column().classes("w-full gap-3 workshop-content")
    state: dict[str, Any] = {
        "pending_shift": {area: None for area in WORKSHOP_AREAS},
        "assign_mode": {area: False for area in WORKSHOP_AREAS},
    }
    highlighted_areas = {"4A", "4B", "5A", "5B", "URD"}

    @ui.refreshable
    def content() -> None:
        body.clear()
        admin = is_admin()
        df = get_open_tasks_df().copy()
        if "Arbeitsplatz" not in df.columns:
            df["Arbeitsplatz"] = ""
        df["area_manual"] = df["Arbeitsplatz"].fillna("").astype(str).str.strip().str.upper()
        df.loc[~df["area_manual"].isin(WORKSHOP_AREAS), "area_manual"] = ""
        df["__fertig_sort"] = pd.to_datetime(df.get("Fertig"), errors="coerce")
        df = df.sort_values(["__fertig_sort", "Fahrzeug"], na_position="last").reset_index(drop=True)
        unassigned = df[df["area_manual"] == ""].copy()
        prio_cur_keys = _current_slot_vehicle_keys_from_ecm4()
        hall_tracks = load_gleisplan_hall_tracks(db_exec)
        default_hall_slots = _workshop_hall_slots(hall_tracks, WORKSHOP_AREAS)
        workshop_config = load_workshop_hall_config(db_exec, default_area_tiles=default_hall_slots)
        texts = dict(workshop_config.get("texts") or {})
        hall_tiles = list(workshop_config.get("tiles") or [])

        due_now = now_berlin()
        due_soon = due_now + timedelta(hours=24)
        due_rows: list[pd.Series] = []
        for _, due_candidate in unassigned.iterrows():
            due_end_dt = as_berlin(due_candidate.get("Fertig"))
            if due_end_dt is not None and due_now <= due_end_dt <= due_soon:
                due_rows.append(due_candidate)

        def option_label(row: pd.Series) -> str:
            fzg = str(row.get("Fahrzeug") or "—")
            fr = str(row.get("Friststufe") or "—")
            end_txt = fmt_dt(row.get("Fertig"))
            return f"{fzg} - {fr} - {end_txt}"

        def render_area_slot(slot: dict[str, Any] | str) -> None:
            if isinstance(slot, dict):
                area_code = str(slot.get("content_area") or slot.get("area_code") or slot.get("key") or "").strip().upper()
                display_label = str(slot.get("display_label") or area_code).strip()
                highlighted = bool(slot.get("highlighted", True))
            else:
                area_code = str(slot or "").strip().upper()
                display_label = area_code
                highlighted = area_code in highlighted_areas
            state["pending_shift"].setdefault(area_code, None)
            state["assign_mode"].setdefault(area_code, False)
            rows = df[df["area_manual"] == area_code].copy()
            rows = rows.sort_values(["__fertig_sort", "Fahrzeug"], na_position="last")
            occupied = rows.iloc[0] if not rows.empty else None
            extras = max(0, len(rows) - 1)
            pending_by_area = state["pending_shift"]
            assign_mode_by_area = state["assign_mode"]
            if occupied is not None:
                pending_by_area[area_code] = None
                assign_mode_by_area[area_code] = False

            slot_state_cls = "hall-slot-occupied" if occupied is not None else "hall-slot-empty"
            slot_cls = f"{'hall-slot hall-slot-active' if highlighted else 'hall-slot hall-slot-passive'} {slot_state_cls}"
            with ui.card().classes(slot_cls):
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label(display_label).classes("hall-slot-title")
                    if occupied is not None and admin:
                        rid = int(occupied["id"])

                        def clear_area(rid=rid) -> None:
                            ok, msg = assign_area(rid, "")
                            ui.notify(msg, type="positive" if ok else "negative")
                            content.refresh()

                        ui.button(texts.get("remove_button") or "Entfernen", icon="close", on_click=clear_area).classes("btn-remove")
                    else:
                        ui.element("span")

                if occupied is None:
                    if not admin:
                        ui.label(texts.get("no_admin_text") or "Nur Admin kann Zuordnungen ändern.").classes("text-gray-400")
                        return
                    if not bool(assign_mode_by_area.get(area_code)):
                        def open_assign(area_name=area_code) -> None:
                            assign_mode_by_area[area_name] = True
                            pending_by_area[area_name] = None
                            content.refresh()

                        ui.button(
                            texts.get("assign_button") or "Fahrzeug zuordnen",
                            icon="add_circle",
                            on_click=open_assign,
                        ).classes("btn-big btn-area-assign w-full")
                        return

                    pending = pending_by_area.get(area_code)
                    if isinstance(pending, dict):
                        pending_open_id = int(pending.get("open_id") or 0)
                        if pending_open_id <= 0:
                            pending_by_area[area_code] = None
                            content.refresh()
                            return

                        conflicts = find_other_assigned_rows_for_same_vehicle(pending_open_id, target_area=area_code)
                        if not conflicts:
                            pending_by_area[area_code] = None
                            ui.notify("Konflikt ist nicht mehr vorhanden. Bitte Zuordnung erneut ausführen.", type="warning")
                            content.refresh()
                            return

                        row_target = db_exec(
                            "SELECT fahrzeug FROM open_tasks WHERE id=?;",
                            (pending_open_id,),
                            fetchone=True,
                        )
                        veh_name = str((row_target["fahrzeug"] if row_target else pending.get("fahrzeug")) or "").strip()
                        src_areas = sorted(
                            {
                                _normalize_workshop_area(c.get("arbeitsplatz"))
                                for c in conflicts
                                if _normalize_workshop_area(c.get("arbeitsplatz"))
                            }
                        )
                        src_text = ", ".join(src_areas) if src_areas else "einem anderen Bereich"
                        veh_text = veh_name or "Das Fahrzeug"
                        ui.label(
                            f"{veh_text} ist bereits in {src_text} zugeordnet. Soll es nach {area_code} geschoben werden?"
                        ).classes("text-amber-2")
                        with ui.row().classes("w-full gap-2"):
                            def do_shift_yes(
                                open_id=pending_open_id,
                                area_name=area_code,
                                conflict_ids=[int(c["id"]) for c in conflicts],
                            ) -> None:
                                ok, msg = assign_vehicle_to_area_with_shift(
                                    int(open_id),
                                    area_name,
                                    source_open_ids=conflict_ids,
                                )
                                pending_by_area[area_name] = None
                                assign_mode_by_area[area_name] = False
                                ui.notify(
                                    "Fahrzeug wurde verschoben und zugeordnet." if ok else (msg or "Umschieben nicht möglich."),
                                    type="positive" if ok else "warning",
                                )
                                content.refresh()

                            def do_shift_no(area_name=area_code) -> None:
                                pending_by_area[area_name] = None
                                assign_mode_by_area[area_name] = False
                                ui.notify("Verschieben abgebrochen.", type="warning")
                                content.refresh()

                            ui.button("Ja, schieben", icon="swap_horiz", on_click=do_shift_yes).classes("btn-big btn-area-assign grow")
                            ui.button("Nein", icon="close", on_click=do_shift_no).classes("btn-remove grow")
                    else:
                        opts_df = unassigned[unassigned.apply(lambda rr: _row_allows_area(rr, area_code), axis=1)]
                        if opts_df.empty:
                            ui.label(texts.get("assign_empty_text") or "Keine passenden unzugeordneten Aufträge.").classes("text-gray-400")
                            def cancel_assign_empty(area_name=area_code) -> None:
                                assign_mode_by_area[area_name] = False
                                pending_by_area[area_name] = None
                                content.refresh()

                            ui.button(
                                texts.get("assign_cancel_button") or "Abbrechen",
                                icon="close",
                                on_click=cancel_assign_empty,
                            ).classes("btn-remove btn-big w-full")
                        else:
                            opts = {int(rr["id"]): option_label(rr) for _, rr in opts_df.iterrows()}
                            sel = ui.select(opts, value=None, label=texts.get("assign_select_label") or "Fahrzeug").props(
                                "outlined dense popup-content-class=area-select-popup"
                            ).classes(
                                "w-full area-select"
                            )

                            def do_assign(sel=sel, area_name=area_code) -> None:
                                if sel.value in (None, ""):
                                    ui.notify("Bitte ein Fahrzeug auswählen.", type="warning")
                                    return
                                chosen_id = int(sel.value)
                                conflicts = find_other_assigned_rows_for_same_vehicle(chosen_id, target_area=area_name)
                                if conflicts:
                                    row_target = db_exec(
                                        "SELECT fahrzeug FROM open_tasks WHERE id=?;",
                                        (chosen_id,),
                                        fetchone=True,
                                    )
                                    pending_by_area[area_name] = {
                                        "open_id": chosen_id,
                                        "fahrzeug": str(row_target["fahrzeug"] if row_target else "").strip(),
                                    }
                                    content.refresh()
                                    return
                                ok, msg = assign_area(chosen_id, area_name)
                                ui.notify(msg, type="positive" if ok else "negative")
                                if ok:
                                    assign_mode_by_area[area_name] = False
                                    pending_by_area[area_name] = None
                                content.refresh()

                            with ui.row().classes("w-full gap-2"):
                                ui.button(
                                    texts.get("assign_confirm_button") or "Zuordnen",
                                    icon="check_circle",
                                    on_click=do_assign,
                                ).classes("btn-big btn-area-assign grow")

                                def cancel_assign(area_name=area_code) -> None:
                                    assign_mode_by_area[area_name] = False
                                    pending_by_area[area_name] = None
                                    content.refresh()

                                ui.button(
                                    texts.get("assign_cancel_button") or "Abbrechen",
                                    icon="close",
                                    on_click=cancel_assign,
                                ).classes("btn-remove btn-big grow")
                    return

                rid = int(occupied["id"])
                fzg = str(occupied.get("Fahrzeug") or "—")
                frist = str(occupied.get("Friststufe") or "—")
                end_dt = as_berlin(occupied.get("Fertig"))
                end_txt = fmt_dt(occupied.get("Fertig"))
                fzg_key = (_norm_vehicle(fzg) or fzg).casefold()
                highlight_red = (area_code in {"4A", "4B", "5A", "5B"}) and bool(fzg_key) and (fzg_key in prio_cur_keys)
                fzg_color = CURRENT_SLOT_VEHICLE_COLOR if highlight_red else "#f5f7fa"
                fzg_title = "Im aktuellen Slot der Tagesplanung" if highlight_red else ""
                hall_fzg = ui.label(fzg).classes("hall-fzg").style(f"color:{fzg_color};")
                if fzg_title:
                    hall_fzg.tooltip(fzg_title)
                ui.label(f"Frist: {frist}  |  Ende: {end_txt}").classes("hall-meta")

                note = _clean_problem_note(occupied.get("last_problem_note"))
                status_key, status_text = status_for_row(occupied, include_problem=True)
                stat_bg, stat_fg = status_palette(status_key)

                fr_done, fr_total, _, _, fr_app = _calc_frist_progress(occupied, area_code=area_code)
                if (not fr_app) or fr_total == 0:
                    fr_txt, fr_bg, fr_fg = "Frist: -", "#adb5bd", "#ffffff"
                elif fr_done >= fr_total:
                    fr_txt, fr_bg, fr_fg = f"{fr_done}/{fr_total} Frist erledigt", "#52c41a", "#ffffff"
                else:
                    fr_txt, fr_bg, fr_fg = f"{fr_done}/{fr_total} Frist erledigt", "#0d6efd", "#ffffff"

                zus_done, zus_total, _, _ = _calc_zus_progress(occupied)
                if zus_total == 0:
                    zus_txt, zus_bg, zus_fg = "Zusatz: -", "#adb5bd", "#ffffff"
                elif zus_done >= zus_total:
                    zus_txt, zus_bg, zus_fg = f"{zus_done}/{zus_total} Zusatz erledigt", "#52c41a", "#ffffff"
                else:
                    zus_txt, zus_bg, zus_fg = f"{zus_done}/{zus_total} Zusatz erledigt", "#0d6efd", "#ffffff"

                with ui.row().classes("w-full items-center gap-2 wrap"):
                    status_badge = render_pill_label(status_text, stat_bg, stat_fg, classes="slot-pill")
                    status_id = status_badge.html_id
                    ui.label(fr_txt).classes("slot-pill").style(_badge_style(fr_bg, fr_fg))
                    ui.label(zus_txt).classes("slot-pill").style(_badge_style(zus_bg, zus_fg))
                    if note:
                        tip_lines = format_problem_lines(note, limit=8)
                        tip_txt = "Problem(e):\n" + "\n".join(tip_lines) if tip_lines else "Problem gemeldet"
                        render_pill_label(
                            texts.get("problem_badge") or "Problem gemeldet",
                            "#ffeb3b",
                            "#000000",
                            classes="slot-pill",
                            tooltip=tip_txt,
                        )

                if end_dt:
                    inject_due24_watcher(
                        end_dt,
                        status_id=status_id,
                        has_problem=bool(note),
                    )

                with ui.row().classes("w-full hall-actions gap-2 wrap"):
                    def done_task(rid=rid) -> None:
                        complete_task_action(rid, content.refresh)

                    ui.button(texts.get("done_button") or "Erledigt", icon="check_circle", on_click=done_task).classes("btn-big btn-done grow")

                    btn_frist = ui.button(
                        texts.get("frist_button") or "Fristarbeiten",
                        icon="playlist_add_check",
                        on_click=lambda rid=rid, area_code=area_code: open_frist_dialog(rid, area_code, content.refresh),
                    ).classes("btn-big grow")
                    if (not fr_app) or fr_total == 0:
                        btn_frist.disable()

                    btn_zus = ui.button(
                        texts.get("zus_button") or "Zusatzarbeiten",
                        icon="add_task",
                        on_click=lambda rid=rid: open_zus_dialog(rid, content.refresh),
                    ).classes("btn-big grow")
                    if zus_total == 0:
                        btn_zus.disable()

                    ui.button(
                        texts.get("delay_button") or "Verzögerung melden",
                        icon="report_problem",
                        on_click=lambda rid=rid: open_problem_dialog(rid, content.refresh),
                    ).classes("btn-big btn-warn grow")

                if note:
                    with ui.element("div").classes("problem-box problemline w-full"):
                        ui.label(texts.get("problem_label") or "Problem(e):").classes("font-bold")
                        for line in format_problem_lines(note, limit=6):
                            ui.label(line).classes("text-sm")
                if extras > 0:
                    ui.label(f"+ {extras} weitere Zuordnung(en) auf diesem Bereich").classes("text-xs text-amber-3")

        def render_due_tile(tile: dict[str, Any]) -> None:
            with ui.card().classes("due-card"):
                ui.label(str(tile.get("display_label") or "In 24 Std fällig (unzugeordnet)")).classes("due-title")
                if not due_rows:
                    ui.label(texts.get("due_empty_text") or "Keine Eintraege in den naechsten 24 Stunden.").classes("text-gray-300")
                else:
                    for rr in due_rows:
                        with ui.card().classes("due-row-card"):
                            rr_id = int(rr.get("id") or 0)
                            rr_end_dt = as_berlin(rr.get("Fertig"))
                            ui.label(str(rr.get("Fahrzeug") or "—")).classes("due-fzg")
                            ui.label(f"Frist: {rr.get('Friststufe') or '-'}  |  Ende: {fmt_dt(rr.get('Fertig'))}").classes(
                                "due-meta"
                            )
                            if rr_end_dt is not None:
                                render_countdown_badge(
                                    rr_end_dt,
                                    key=f"due_{rr_id}",
                                    badge_bg="#faad14",
                                    badge_fg="#000000",
                                )

        with body:
            if not hall_tiles:
                ui.label("Keine aktiven Kacheln konfiguriert.").classes("text-gray-300")
                return
            with ui.grid(columns=2).classes("w-full gap-3 hall-grid hall-bottom-grid"):
                for tile in hall_tiles:
                    if str(tile.get("tile_type") or "").strip().lower() == "due_soon":
                        render_due_tile(tile)
                    else:
                        render_area_slot(tile)

    content()

    def _auto_refresh_werkstatthalle() -> None:
        if _has_open_dialog():
            return
        if not is_admin():
            content.refresh()

    create_page_timer(float(refresh_interval_seconds), _auto_refresh_werkstatthalle)
