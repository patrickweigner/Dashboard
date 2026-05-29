from __future__ import annotations

from datetime import date, datetime, timedelta
from bisect import bisect_right
import re
from typing import Any, Callable

import pandas as pd
from nicegui import ui

from core.ui_runtime import create_page_timer


def render(*, refresh_interval_seconds: float, **deps) -> None:
    # Transitional bridge for the large Tagesplanung page: inject the existing
    # helpers/constants unchanged so the page can live outside main.py first.
    globals().update(deps)
    render_nav()
    now = now_berlin()
    shift_day = _shift_day(now)
    state: dict[str, Any] = {"day": shift_day.isoformat()}
    def _selected_prio_day() -> date:
        try:
            return date.fromisoformat(str(day_input.value or state["day"]))
        except Exception:
            return shift_day

    def run_lwu_test() -> None:
        sent, matched = trigger_lwu_test_next_24h(hours_ahead=24)
        if matched == 0:
            ui.notify("Kein LWU-Eintrag in den nächsten 24 Stunden gefunden.", type="warning")
        elif sent > 0:
            ui.notify(f"LWU-Test ausgeloest: {sent}/{matched} Trigger erfolgreich.", type="positive")
        else:
            ui.notify(f"{matched} LWU-Einträge gefunden, aber kein Trigger war erfolgreich.", type="warning")

    with ui.column().classes("w-full prio-page"):
        with ui.column().classes("w-full gap-2 prio-command-row"):
            ui.label("Tagesplanung").classes("page-title prio-page-title")
            with ui.row().classes("items-center gap-3 wrap prio-command-tools"):
                with ui.column().classes("gap-1 prio-date-control"):
                    ui.label("Tag auswählen").classes("prio-control-label")
                    day_input = ui.input(value=state["day"]).props("type=date outlined dense").classes("min-w-[200px] prio-day-input")
                ui.button(
                    "Außeneinsatz",
                    icon="engineering",
                    on_click=lambda: open_ausseneinsatz_dialog(_selected_prio_day()),
                ).classes("btn-big prio-external-btn")
                with ui.row().classes("items-center gap-2 legend-item prio-side-legend prio-deadline-legend"):
                    ui.element("span").classes("legend-pill legend-yellow")
                    ui.label("Orange = Fristende").classes("legend-text")
        body = ui.column().classes("w-full gap-3 prio-content")

    def _to_berlin_dt(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, pd.Timestamp):
            value = value.to_pydatetime()
        if not isinstance(value, datetime):
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=BERLIN)
        return value.astimezone(BERLIN)

    def _fmt_area_range_label(
        start_value: Any,
        end_value: Any,
        *,
        force_end_time_only: bool = False,
        to_berlin_dt_fn: Callable[[Any], datetime | None] | None = None,
    ) -> str:
        to_dt = to_berlin_dt_fn or _to_berlin_dt
        st_dt = to_dt(start_value)
        en_dt = to_dt(end_value)
        if st_dt is None:
            return ""
        if en_dt is None:
            return st_dt.strftime("%d.%m %H:%M")
        if force_end_time_only or st_dt.date() == en_dt.date():
            return f"{st_dt.strftime('%d.%m %H:%M')} - {en_dt.strftime('%H:%M')}"
        return f"{st_dt.strftime('%d.%m %H:%M')} - {en_dt.strftime('%d.%m %H:%M')}"

    def _vehicle_match_key(v: str) -> str:
        vv = str(v or "").strip()
        return (_norm_vehicle(vv) or vv).casefold()

    def _vehicle_keys_from_note(note_text: str) -> set[str]:
        keys: set[str] = set()
        txt = str(note_text or "")
        for m in RX_VEHICLE.finditer(txt):
            prefix = (m.group(1) or "").upper().strip()
            num = (m.group(2) or "").strip()
            key = ((prefix + num).replace(" ", "") if prefix else num).casefold()
            if key:
                keys.add(key)
        return keys

    def _note_segments_by_vehicle(note_text: str) -> dict[str, str]:
        txt = str(note_text or "")
        if not txt:
            return {}
        matches = list(RX_VEHICLE.finditer(txt))
        if not matches:
            return {}
        out: dict[str, str] = {}
        for idx, match in enumerate(matches):
            prefix = (match.group(1) or "").upper().strip()
            vehicle_num = (match.group(2) or "").strip()
            key = ((prefix + vehicle_num).replace(" ", "") if prefix else vehicle_num).casefold()
            if not key:
                continue
            seg_start = match.end()
            seg_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(txt)
            segment = txt[seg_start:seg_end]
            segment = re.sub(r"\s+", " ", segment).strip(" /,;:-")
            out[key] = segment
        return out

    def _note_for_vehicle(
        note_text: str,
        vehicle_raw: str,
        *,
        vehicle_match_key_fn: Callable[[Any], str] | None = None,
    ) -> str:
        txt = _clean_prio_text(note_text)
        if not txt:
            return ""
        segments = _note_segments_by_vehicle(txt)
        if not segments:
            return txt
        target = (vehicle_match_key_fn or _vehicle_match_key)(vehicle_raw)
        if not target:
            return ""
        return str(segments.get(target) or "").strip()

    def _clean_prio_text(value: Any) -> str:
        if value is None:
            return ""
        try:
            if pd.isna(value):
                return ""
        except Exception:
            pass
        txt = str(value).strip()
        if txt.casefold() in {"nan", "nat", "none", "null"}:
            return ""
        return txt

    def _display_ecm4_vehicle_code(
        value: Any,
        *,
        norm_vehicle_fn: Callable[[Any], str] | None = None,
    ) -> str:
        txt = _clean_prio_text(value)
        if txt in {"-", "\u2014", "\u00e2\u20ac\u201d"}:
            return ""
        return (norm_vehicle_fn or _norm_vehicle)(txt) or txt

    def _build_ecm4_prio_snapshot(
        df_plan: pd.DataFrame,
        frist_by_vehicle: dict[str, str],
        frist_by_vehicle_urd: dict[str, str],
        hist_frist_by_vehicle: dict[str, str],
        hist_frist_by_vehicle_urd: dict[str, str],
        *,
        norm_vehicle_fn: Callable[[Any], str] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
        normalize_vehicle = norm_vehicle_fn or _norm_vehicle
        plan_service_rows: list[dict[str, Any]] = []
        tasks_by_area: dict[str, list[dict[str, Any]]] = {}
        if df_plan.empty:
            return plan_service_rows, tasks_by_area

        row_values = df_plan.reindex(columns=("area", "fahrzeug", "slot_start")).itertuples(index=False, name=None)
        for area_value, vehicle_value, slot_start_value in row_values:
            area_raw = _clean_prio_text(area_value)
            if not area_raw:
                continue
            area = area_raw.upper().replace(" ", "")

            if area == "SERVICE":
                vehicle = _display_ecm4_vehicle_code(vehicle_value, norm_vehicle_fn=normalize_vehicle)
                slot_start = as_berlin(slot_start_value)
                if vehicle and slot_start is not None:
                    plan_service_rows.append(
                        {
                            "fahrzeug": vehicle,
                            "start": slot_start,
                            "end": _slot_end_for_start(slot_start),
                        }
                    )
                continue

            if area == "RWS":
                continue

            veh_raw = _clean_prio_text(vehicle_value)
            if not veh_raw:
                continue
            veh = normalize_vehicle(veh_raw) or veh_raw
            st_dt = as_berlin(slot_start_value)
            if st_dt is None:
                continue
            en_dt = _slot_end_for_start(st_dt)
            fr = (
                frist_by_vehicle_urd.get(veh)
                if area == "URD"
                else frist_by_vehicle.get(veh)
            ) or ""
            if not fr:
                fr = (
                    hist_frist_by_vehicle_urd.get(veh)
                    if area == "URD"
                    else hist_frist_by_vehicle.get(veh)
                ) or ""
            if not fr:
                fr = "-"
            tasks_by_area.setdefault(area, []).append(
                {
                    "fahrzeug": veh,
                    "frist": fr,
                    "hinweis": None,
                    "hinweis_overview": None,
                    "start": st_dt,
                    "end": en_dt,
                    "slot_based": True,
                }
            )

        plan_service_rows.sort(
            key=lambda item: (
                as_berlin(item.get("start")) or datetime.min.replace(tzinfo=BERLIN),
                str(item.get("fahrzeug") or ""),
            )
        )
        return plan_service_rows, tasks_by_area

    @ui.refreshable
    def content() -> None:
        try:
            sel_date = date.fromisoformat(str(day_input.value or state["day"]))
        except Exception:
            sel_date = shift_day
        now = now_berlin()

        norm_vehicle_cache: dict[str, str] = {}
        vehicle_match_key_cache: dict[str, str] = {}
        wash_vehicle_key_cache: dict[str, str] = {}
        urd_vehicle_key_cache: dict[str, str] = {}

        def memo_norm_vehicle(value: Any) -> str:
            cache_key = str(value or "")
            if cache_key not in norm_vehicle_cache:
                norm_vehicle_cache[cache_key] = _norm_vehicle(cache_key)
            return norm_vehicle_cache[cache_key]

        def memo_vehicle_match_key(value: Any) -> str:
            cache_key = str(value or "")
            if cache_key not in vehicle_match_key_cache:
                vv = cache_key.strip()
                vehicle_match_key_cache[cache_key] = (memo_norm_vehicle(vv) or vv).casefold()
            return vehicle_match_key_cache[cache_key]

        def memo_wash_vehicle_key(value: Any) -> str:
            cache_key = str(value or "")
            if cache_key not in wash_vehicle_key_cache:
                vv = cache_key.strip()
                wash_vehicle_key_cache[cache_key] = (memo_norm_vehicle(vv) or vv).casefold()
            return wash_vehicle_key_cache[cache_key]

        def memo_urd_vehicle_key(value: Any) -> str:
            cache_key = str(value or "")
            if cache_key not in urd_vehicle_key_cache:
                vv = cache_key.strip()
                if not vv:
                    urd_vehicle_key_cache[cache_key] = ""
                else:
                    m = RX_VEHICLE.search(vv)
                    urd_vehicle_key_cache[cache_key] = (
                        str(m.group(2) or "").strip().casefold()
                        if m
                        else vv.casefold()
                    )
            return urd_vehicle_key_cache[cache_key]

        to_berlin_dt_cache: dict[tuple[Any, ...], datetime | None] = {}

        def to_berlin_dt_cache_key(value: Any) -> tuple[Any, ...]:
            if value is None:
                return ("none", None)
            try:
                hash(value)
                return (type(value).__module__, type(value).__qualname__, value)
            except Exception:
                return (type(value).__module__, type(value).__qualname__, id(value))

        def memo_to_berlin_dt(value: Any) -> datetime | None:
            cache_key = to_berlin_dt_cache_key(value)
            if cache_key not in to_berlin_dt_cache:
                to_berlin_dt_cache[cache_key] = _to_berlin_dt(value)
            return to_berlin_dt_cache[cache_key]

        def memo_fmt_area_range_label(
            start_value: Any,
            end_value: Any,
            *,
            force_end_time_only: bool = False,
        ) -> str:
            return _fmt_area_range_label(
                start_value,
                end_value,
                force_end_time_only=force_end_time_only,
                to_berlin_dt_fn=memo_to_berlin_dt,
            )

        body.clear()
        with body:
            # --- Slotfenster analog Streamlit ---
            day_slots = _build_slots_for_day(sel_date)
            cur_slot_start: datetime | None = None
            next_slot_start: datetime | None = None
            shift_pair_slot_start: datetime | None = None
            prev_slot: dict[str, Any] | None = None
            if sel_date == shift_day:
                slot_stream = (
                    _build_slots_for_day(sel_date - timedelta(days=1))
                    + _build_slots_for_day(sel_date)
                    + _build_slots_for_day(sel_date + timedelta(days=1))
                )
                slot_stream.sort(key=lambda s: s["start"])
                starts = [s["start"] for s in slot_stream]
                from bisect import bisect_right

                cur_idx = bisect_right(starts, now) - 1
                if cur_idx < 0:
                    cur_idx = 0
                if cur_idx >= len(slot_stream):
                    cur_idx = len(slot_stream) - 1

                if cur_idx > 0:
                    prev_slot = slot_stream[cur_idx - 1]

                cur_slot = slot_stream[cur_idx]
                cur_slot_start = cur_slot["start"]
                cur_group = _shift_pair_group(cur_slot.get("label"))
                if cur_group:
                    mates = [
                        s
                        for i, s in enumerate(slot_stream)
                        if i != cur_idx and _shift_pair_group(s.get("label")) == cur_group
                    ]
                    if mates:
                        shift_pair_slot_start = min(
                            mates,
                            key=lambda s: abs((s["start"] - cur_slot["start"]).total_seconds()),
                        )["start"]

                win_slots = slot_stream[cur_idx : cur_idx + 6]
                if not win_slots:
                    win_slots = _build_slots_for_day(sel_date)
                next_slot_start = win_slots[1]["start"] if len(win_slots) > 1 else None
            else:
                win_slots = _build_slots_for_day(sel_date)
                prev_day_slots = _build_slots_for_day(sel_date - timedelta(days=1))
                prev_slot = prev_day_slots[-1] if prev_day_slots else None

            # --- Frist-Index aus offenen Aufträgen ---
            frist_by_vehicle: dict[str, str] = {}
            frist_by_vehicle_urd: dict[str, str] = {}
            df_open = get_open_tasks_df()
            if not df_open.empty:
                for _, rr in df_open.iterrows():
                    veh_raw = _clean_prio_text(rr.get("Fahrzeug"))
                    if not veh_raw:
                        continue
                    key = memo_norm_vehicle(veh_raw) or veh_raw
                    fr = _clean_prio_text(rr.get("Friststufe"))
                    tgt = frist_by_vehicle_urd if _is_urd_open_row(rr) else frist_by_vehicle
                    if key not in tgt or tgt[key] in {"", "-"}:
                        tgt[key] = fr

            hist_frist_by_vehicle, hist_frist_by_vehicle_urd = _get_prio_frist_history_maps()
            gewerke_events = _collect_gewerke_slot_events(df_open)

            # --- ECM4-Belegung laden ---
            df_plan = load_ecm4_plan_df(ref_dt=sel_date)
            plan_service_rows, tasks_by_area = _build_ecm4_prio_snapshot(
                df_plan,
                frist_by_vehicle,
                frist_by_vehicle_urd,
                hist_frist_by_vehicle,
                hist_frist_by_vehicle_urd,
                norm_vehicle_fn=memo_norm_vehicle,
            )

            # URD-Aufträge aus open_tasks zusätzlich als Zeitraum
            if not df_open.empty:
                for _, rr in df_open.iterrows():
                    ap = _clean_prio_text(rr.get("Arbeitsplatz")).upper()
                    if ap != "URD":
                        continue
                    veh_raw = _clean_prio_text(rr.get("Fahrzeug"))
                    if not veh_raw:
                        continue
                    veh = memo_norm_vehicle(veh_raw) or veh_raw
                    st_dt = as_berlin(rr.get("Anfang"))
                    en_dt = as_berlin(rr.get("Fertig"))
                    if st_dt is None and en_dt is None:
                        continue
                    if isinstance(st_dt, pd.Timestamp):
                        st_dt = st_dt.to_pydatetime()
                    if isinstance(en_dt, pd.Timestamp):
                        en_dt = en_dt.to_pydatetime()
                    if st_dt is None and en_dt is not None:
                        st_dt = en_dt - timedelta(hours=4)
                    if en_dt is None and st_dt is not None:
                        en_dt = st_dt + timedelta(hours=4)
                    exists = False
                    for tt in tasks_by_area.get("URD", []) or []:
                        t_st = memo_to_berlin_dt(tt.get("start"))
                        t_en = memo_to_berlin_dt(tt.get("end"))
                        if (
                            str(tt.get("fahrzeug") or "").strip() == veh
                            and t_st is not None
                            and t_en is not None
                            and abs((t_st - st_dt).total_seconds()) < 60
                            and abs((t_en - en_dt).total_seconds()) < 60
                        ):
                            exists = True
                            break
                    if exists:
                        continue
                    tasks_by_area.setdefault("URD", []).append(
                        {
                            "fahrzeug": veh,
                            "frist": "URD",
                            "hinweis": None,
                            "start": st_dt,
                            "end": en_dt,
                            "slot_based": False,
                        }
                    )

            for area in list(tasks_by_area.keys()):
                tasks_by_area[area].sort(
                    key=lambda x: (
                        memo_to_berlin_dt(x.get("start")) or datetime.min.replace(tzinfo=BERLIN),
                        memo_to_berlin_dt(x.get("end")) or datetime.max.replace(tzinfo=BERLIN),
                    )
                )

            # Letztes Ende pro Bereich/Fahrzeug (für orange Markierung im letzten relevanten Slot)
            last_end_by_area_vehicle: dict[tuple[str, str], datetime] = {}
            for _a, lst in tasks_by_area.items():
                for tt in lst:
                    veh_key = str(tt.get("fahrzeug") or "").strip()
                    te = memo_to_berlin_dt(tt.get("end"))
                    if not veh_key or te is None:
                        continue
                    k = (_a, veh_key)
                    prev = last_end_by_area_vehicle.get(k)
                    if prev is None or te > prev:
                        last_end_by_area_vehicle[k] = te

            # Gewerke-Logik: Slot-Events kommen aus Fzg Zusatzarbeiten / Spalte C.
            try:
                track_areas = set(PRIO_MAIN_AREAS)
                track_refs_by_vehicle: dict[str, list[dict[str, Any]]] = {}

                for _area in track_areas:
                    for tt in tasks_by_area.get(_area, []) or []:
                        if not bool(tt.get("slot_based")):
                            continue
                        veh = _clean_prio_text(tt.get("fahrzeug"))
                        st_dt = memo_to_berlin_dt(tt.get("start"))
                        if not veh or st_dt is None:
                            continue
                        vk = memo_vehicle_match_key(veh)
                        track_refs_by_vehicle.setdefault(vk, []).append(
                            {"area": _area, "start": st_dt, "veh": veh}
                        )

                for _vk in track_refs_by_vehicle:
                    track_refs_by_vehicle[_vk].sort(key=lambda x: x["start"])

                def _task_at_exact_slot(area: str, slot_dt: datetime) -> dict[str, Any] | None:
                    for tt in tasks_by_area.get(area, []) or []:
                        if not bool(tt.get("slot_based")):
                            continue
                        ts = memo_to_berlin_dt(tt.get("start"))
                        if ts is None:
                            continue
                        if abs((ts - slot_dt).total_seconds()) < 60:
                            return tt
                    return None

                for event in gewerke_events:
                    slot_dt = memo_to_berlin_dt(event.get("start"))
                    vehicle = str(event.get("fahrzeug") or "").strip()
                    vk = memo_vehicle_match_key(vehicle)
                    if slot_dt is None or not vk:
                        continue
                    event_has_time = bool(event.get("has_time", True))
                    event_end = memo_to_berlin_dt(event.get("end"))
                    if event_end is None:
                        event_end = _slot_end_for_start(slot_dt) if event_has_time else slot_dt
                    tasks_by_area.setdefault("SERVICE", []).append(
                        {
                            "fahrzeug": vehicle,
                            "frist": "",
                            "hinweis": _clean_prio_text(event.get("label")) or None,
                            "hinweis_overview": _clean_prio_text(event.get("overview")) or None,
                            "start": slot_dt,
                            "display_start": memo_to_berlin_dt(event.get("display_start")),
                            "end": event_end,
                            "slot_based": event_has_time,
                            "suppress_frist": True,
                            "is_gewerk": True,
                            "date_only": bool(event.get("date_only")),
                            "source_rows": list(event.get("source_rows") or []),
                        }
                    )

                    if not event_has_time:
                        continue

                    refs = track_refs_by_vehicle.get(vk) or []
                    if not refs:
                        continue

                    prev_ref = None
                    next_ref = None
                    for ref in refs:
                        if ref["start"] <= slot_dt:
                            prev_ref = ref
                        else:
                            next_ref = ref
                            break

                    chosen_ref = None
                    if prev_ref is not None and next_ref is not None:
                        d_prev = (slot_dt - prev_ref["start"]).total_seconds()
                        d_next = (next_ref["start"] - slot_dt).total_seconds()
                        chosen_ref = prev_ref if d_prev <= d_next else next_ref
                    elif prev_ref is not None:
                        chosen_ref = prev_ref
                    elif next_ref is not None:
                        chosen_ref = next_ref
                    if chosen_ref is None:
                        continue

                    target_area = str(chosen_ref["area"] or "").strip().upper()
                    if target_area not in track_areas:
                        continue

                    existing = _task_at_exact_slot(target_area, slot_dt)
                    hint_label = _clean_prio_text(event.get("label"))
                    hint_overview = _clean_prio_text(event.get("overview"))
                    if existing and str(existing.get("fahrzeug") or "").strip():
                        if memo_vehicle_match_key(str(existing.get("fahrzeug") or "")) == vk:
                            existing["hinweis"] = _append_unique_inline_text(existing.get("hinweis"), hint_label)
                            existing["hinweis_overview"] = _append_unique_multiline_text(existing.get("hinweis_overview"), hint_overview)
                        continue

                    next_same_area = next(
                        (ref for ref in refs if ref["area"] == target_area and ref["start"] > slot_dt),
                        None,
                    )
                    hint_aug = hint_label
                    overview_aug = hint_overview
                    if next_same_area is not None and "fristarbeiten erst ab" not in hint_aug.casefold():
                        nst = memo_to_berlin_dt(next_same_area["start"])
                        if nst is not None:
                            if nst.date() == slot_dt.date():
                                suffix = f"Fristarbeiten erst ab {nst.strftime('%H:%M')}"
                            else:
                                suffix = f"Fristarbeiten erst ab {nst.strftime('%d.%m %H:%M')}"
                            hint_aug = _append_unique_inline_text(hint_aug, suffix)
                            overview_aug = _append_unique_inline_text(overview_aug, suffix)

                    tasks_by_area.setdefault(target_area, []).append(
                        {
                            "fahrzeug": str(chosen_ref["veh"] or "").strip(),
                            "frist": "",
                            "hinweis": hint_aug or None,
                            "hinweis_overview": overview_aug or None,
                            "start": slot_dt,
                            "end": _slot_end_for_start(slot_dt),
                            "slot_based": True,
                            "suppress_frist": True,
                            "is_gewerk": True,
                        }
                    )

                for _a in list(tasks_by_area.keys()):
                    tasks_by_area[_a].sort(
                        key=lambda x: (
                            memo_to_berlin_dt(x.get("start")) or datetime.min.replace(tzinfo=BERLIN),
                            memo_to_berlin_dt(x.get("end")) or datetime.max.replace(tzinfo=BERLIN),
                        )
                    )
            except Exception:
                pass

            def _find_wash_item_index(items: list[str]) -> int | None:
                for i, item in enumerate(items):
                    if _is_wash_zus_item(item):
                        return i
                return None

            def _ensure_wash_zusatz_entry(zus_raw: str) -> tuple[str, bool]:
                old = str(zus_raw or "").strip()
                items = _parse_zusatz_items(old)
                if _find_wash_item_index(items) is not None:
                    return old, False
                base = old
                if base and not re.search(r"(?m)^\s*-", base):
                    lines = base.splitlines()
                    if lines:
                        lines[0] = "- " + lines[0].lstrip()
                        base = "\n".join(lines)
                entry = f"- {WASH_ZUS_LABEL}"
                if not base:
                    return entry, True
                if base.endswith("\n"):
                    return base + entry, True
                return base + "\n" + entry, True

            def _wash_done_from_row(zus_raw: str, done_raw: str) -> bool:
                items = _parse_zusatz_items(zus_raw)
                idx = _find_wash_item_index(items)
                if idx is None:
                    return False
                bits = _decode_check_string(str(done_raw or ""), len(items))
                return bool(bits[idx]) if idx < len(bits) else False

            def _set_wash_done_for_row(zus_raw: str, done_raw: str, checked: bool) -> str | None:
                items = _parse_zusatz_items(zus_raw)
                idx = _find_wash_item_index(items)
                if idx is None:
                    return None
                bits = _decode_check_string(str(done_raw or ""), len(items))
                bits[idx] = bool(checked)
                return _encode_check_list(bits)

            def _wash_vehicle_key(v: str) -> str:
                return memo_wash_vehicle_key(v)

            def _urd_vehicle_key(v: str) -> str:
                return memo_urd_vehicle_key(v)

            def _slot_index_key(value: Any) -> datetime | None:
                dt = memo_to_berlin_dt(value)
                if dt is None:
                    return None
                return dt.replace(second=0, microsecond=0)

            # Reale SERVICE-Belegung bleibt getrennt von der neuen Gewerke-Kachel.
            service_windows_by_vehicle: dict[str, list[tuple[datetime, datetime, bool]]] = {}
            for tt in plan_service_rows:
                veh_key = _clean_prio_text(tt.get("fahrzeug"))
                ts = memo_to_berlin_dt(tt.get("start"))
                te = memo_to_berlin_dt(tt.get("end"))
                if not veh_key or ts is None or te is None:
                    continue
                service_windows_by_vehicle.setdefault(veh_key, []).append((ts, te, True))
            for key in service_windows_by_vehicle:
                service_windows_by_vehicle[key].sort(key=lambda x: (x[0], x[1]))

            service_slot_index: dict[str, dict[datetime, list[tuple[datetime, datetime, bool]]]] = {}
            service_range_index: dict[str, list[tuple[datetime, datetime, bool]]] = {}
            for veh_key, windows in service_windows_by_vehicle.items():
                slot_buckets: dict[datetime, list[tuple[datetime, datetime, bool]]] = {}
                range_windows: list[tuple[datetime, datetime, bool]] = []
                for ts, te, is_slot_based in windows:
                    if is_slot_based:
                        slot_key = _slot_index_key(ts)
                        if slot_key is not None:
                            slot_buckets.setdefault(slot_key, []).append((ts, te, is_slot_based))
                    else:
                        range_windows.append((ts, te, is_slot_based))
                service_slot_index[veh_key] = slot_buckets
                service_range_index[veh_key] = range_windows

            def _has_service_in_slot(veh_key: str, slot_start: datetime | None, slot_end: datetime | None) -> bool:
                if not veh_key or slot_start is None or slot_end is None:
                    return False
                slot_key = _slot_index_key(slot_start)
                if slot_key is not None:
                    for candidate_key in (
                        slot_key - timedelta(minutes=1),
                        slot_key,
                        slot_key + timedelta(minutes=1),
                    ):
                        for ts, _te, _is_slot_based in service_slot_index.get(veh_key, {}).get(candidate_key, []):
                            if abs((ts - slot_start).total_seconds()) < 60:
                                return True
                for ts, te, _is_slot_based in service_range_index.get(veh_key, []):
                    if ts < slot_end and te > slot_start:
                        return True
                return False

            slot_task_index: dict[str, dict[datetime, list[tuple[int, dict[str, Any], datetime, datetime]]]] = {}
            range_task_index: dict[str, list[tuple[int, dict[str, Any], datetime, datetime]]] = {}
            for area_name, area_tasks in tasks_by_area.items():
                area_norm = str(area_name or "").strip().upper()
                slot_buckets: dict[datetime, list[tuple[int, dict[str, Any], datetime, datetime]]] = {}
                range_tasks: list[tuple[int, dict[str, Any], datetime, datetime]] = []
                for task_order, task in enumerate(area_tasks or []):
                    ts = memo_to_berlin_dt(task.get("start"))
                    te = memo_to_berlin_dt(task.get("end"))
                    if ts is None or te is None:
                        continue
                    if bool(task.get("slot_based")):
                        slot_key = _slot_index_key(ts)
                        if slot_key is not None:
                            slot_buckets.setdefault(slot_key, []).append((task_order, task, ts, te))
                    else:
                        range_tasks.append((task_order, task, ts, te))
                slot_task_index[area_norm] = slot_buckets
                range_task_index[area_norm] = range_tasks

            def _pick_task_for_slot(area: str, slot_start: datetime, slot_end: datetime) -> dict[str, Any] | None:
                area_norm = str(area or "").strip().upper()
                hits: list[tuple[datetime, int, dict[str, Any]]] = []
                slot_key = _slot_index_key(slot_start)
                if slot_key is not None:
                    for candidate_key in (
                        slot_key - timedelta(minutes=1),
                        slot_key,
                        slot_key + timedelta(minutes=1),
                    ):
                        for task_order, tt, ts, _te in slot_task_index.get(area_norm, {}).get(candidate_key, []):
                            if abs((ts - slot_start).total_seconds()) < 60:
                                hits.append((ts, task_order, tt))
                for task_order, tt, ts, te in range_task_index.get(area_norm, []):
                    if ts < slot_end and te > slot_start:
                        hits.append((ts, task_order, tt))
                if not hits:
                    return None
                hits.sort(key=lambda x: (x[0], x[1]))
                return hits[0][2]

            _pick_cache: dict[tuple[str, datetime, datetime], dict[str, Any] | None] = {}
            _empty_day_cache: dict[str, bool] = {}
            _next_planned_after_day_cache: dict[str, dict[str, Any] | None] = {}

            def _pick_cached(area: str, slot_start: datetime, slot_end: datetime) -> dict[str, Any] | None:
                k = (str(area or "").upper(), slot_start, slot_end)
                if k in _pick_cache:
                    return _pick_cache[k]
                out = _pick_task_for_slot(area, slot_start, slot_end)
                _pick_cache[k] = out
                return out

            def _task_has_prio_content(task: dict[str, Any] | None) -> bool:
                if not task:
                    return False
                return bool(
                    _clean_prio_text(task.get("fahrzeug"))
                    or _clean_prio_text(task.get("frist"))
                    or _clean_prio_text(task.get("hinweis"))
                )

            def _day_slots_empty_for_area(area: str) -> bool:
                area_norm = str(area or "").strip().upper()
                if area_norm not in {"4A", "4B", "5A", "5B"}:
                    return False
                if area_norm in _empty_day_cache:
                    return _empty_day_cache[area_norm]

                is_empty = True
                for s in day_slots:
                    if _task_has_prio_content(_pick_cached(area_norm, s["start"], s["end"])):
                        is_empty = False
                        break
                _empty_day_cache[area_norm] = is_empty
                return is_empty

            def _next_planned_task_after_day(area: str) -> dict[str, Any] | None:
                area_norm = str(area or "").strip().upper()
                if area_norm not in {"4A", "4B", "5A", "5B"}:
                    return None
                if area_norm in _next_planned_after_day_cache:
                    return _next_planned_after_day_cache[area_norm]

                threshold = day_slots[-1]["end"] if day_slots else None
                best_task: dict[str, Any] | None = None
                best_start: datetime | None = None
                for tt in tasks_by_area.get(area_norm, []) or []:
                    if not _task_has_prio_content(tt):
                        continue
                    ts = memo_to_berlin_dt(tt.get("start"))
                    if ts is None or threshold is None or ts < threshold:
                        continue
                    if best_start is None or ts < best_start:
                        best_task = tt
                        best_start = ts

                _next_planned_after_day_cache[area_norm] = best_task
                return best_task

            def _build_area_rows(area: str, *, show_all_entries: bool = False) -> list[dict[str, Any]]:
                rows: list[dict[str, Any]] = []
                if show_all_entries:
                    area_tasks_raw = list(tasks_by_area.get(area, []) or [])
                    area_tasks: list[dict[str, Any]] = []
                    for tt in area_tasks_raw:
                        t_end = memo_to_berlin_dt(tt.get("end"))
                        if t_end is not None and now.date() >= (t_end.date() + timedelta(days=7)):
                            continue
                        area_tasks.append(tt)

                    norm_rows: list[dict[str, Any]] = []
                    for idx, tt in enumerate(area_tasks):
                        st_dt = memo_to_berlin_dt(tt.get("start"))
                        en_dt = memo_to_berlin_dt(tt.get("end")) or st_dt
                        if bool(tt.get("slot_based")) and st_dt is not None:
                            en_dt = _next_slot_start_for_start(st_dt)

                        veh_raw = _clean_prio_text(tt.get("fahrzeug"))
                        veh_key = memo_vehicle_match_key(veh_raw) if veh_raw else ""
                        bucket_key = veh_key or (veh_raw.casefold() if veh_raw else f"__row_{idx}")
                        norm_rows.append(
                            {
                                "task": tt,
                                "slot_start": st_dt,
                                "slot_end": en_dt,
                                "veh_key": veh_key,
                                "bucket_key": bucket_key,
                            }
                        )

                    norm_rows.sort(
                        key=lambda x: (
                            x["slot_start"] or datetime.min.replace(tzinfo=BERLIN),
                            x["bucket_key"],
                        )
                    )

                    if area == "SERVICE":
                        for item in norm_rows:
                            task = item.get("task") or {}
                            row_start = memo_to_berlin_dt(task.get("display_start")) or item.get("slot_start")
                            row_end = item.get("slot_end")
                            if bool(task.get("date_only")) and row_start is not None:
                                label_plain = row_start.strftime("%d.%m")
                            else:
                                label_plain = memo_fmt_area_range_label(row_start, None, force_end_time_only=False)
                            rows.append(
                                {
                                    "label": label_plain,
                                    "label_html": label_plain,
                                    "task": task,
                                    "slot_start": row_start,
                                    "slot_end": row_end,
                                    "cls": "",
                                    "is_prev_slot": False,
                                }
                            )
                        rows.sort(
                            key=lambda x: (
                                memo_to_berlin_dt(x.get("slot_start")) or datetime.min.replace(tzinfo=BERLIN),
                                str(x.get("label") or ""),
                            )
                        )
                        if not rows:
                            rows.append(
                                {
                                    "label": "",
                                    "task": None,
                                    "slot_start": None,
                                    "slot_end": None,
                                    "cls": "",
                                    "is_prev_slot": False,
                                }
                            )
                        return rows

                    by_vehicle: dict[str, list[dict[str, Any]]] = {}
                    for item in norm_rows:
                        by_vehicle.setdefault(str(item["bucket_key"]), []).append(item)

                    for bucket_items in by_vehicle.values():
                        if not bucket_items:
                            continue
                        bucket_items.sort(key=lambda x: x["slot_start"] or datetime.min.replace(tzinfo=BERLIN))

                        segments: list[dict[str, datetime | None]] = []
                        merge_tol = timedelta(minutes=1)
                        for item in bucket_items:
                            seg_start = memo_to_berlin_dt(item.get("slot_start"))
                            seg_end = memo_to_berlin_dt(item.get("slot_end")) or seg_start
                            if not segments:
                                segments.append({"start": seg_start, "end": seg_end})
                                continue
                            prev_seg = segments[-1]
                            contiguous = (
                                seg_start is not None
                                and prev_seg["end"] is not None
                                and seg_start <= (prev_seg["end"] + merge_tol)
                            )
                            if contiguous:
                                if seg_end is not None and (
                                    prev_seg["end"] is None or seg_end > prev_seg["end"]
                                ):
                                    prev_seg["end"] = seg_end
                            else:
                                segments.append({"start": seg_start, "end": seg_end})

                        first_item = bucket_items[0]
                        label_parts = [
                            memo_fmt_area_range_label(seg.get("start"), seg.get("end"), force_end_time_only=False)
                            for seg in segments
                        ]
                        label_parts = [x for x in label_parts if x]
                        label_plain = " | ".join(label_parts) if label_parts else ""
                        label_html = "<br>".join(label_parts) if label_parts else ""

                        row_start = segments[0]["start"] if segments else first_item.get("slot_start")
                        row_end = segments[-1]["end"] if segments else first_item.get("slot_end")

                        rows.append(
                            {
                                "label": label_plain,
                                "label_html": label_html,
                                "task": first_item.get("task"),
                                "slot_start": row_start,
                                "slot_end": row_end,
                                "cls": "",
                                "is_prev_slot": False,
                            }
                        )

                    rows.sort(
                        key=lambda x: (
                            memo_to_berlin_dt(x.get("slot_start")) or datetime.min.replace(tzinfo=BERLIN),
                            str(x.get("label") or ""),
                        )
                    )
                    if not rows:
                        rows.append(
                            {
                                "label": "",
                                "task": None,
                                "slot_start": None,
                                "slot_end": None,
                                "cls": "",
                                "is_prev_slot": False,
                            }
                        )
                    return rows

                if area in {"4A", "4B", "5A", "5B", "SERVICE"} and prev_slot is not None:
                    rows.append(
                        {
                            "label": prev_slot["label"],
                            "task": _pick_cached(area, prev_slot["start"], prev_slot["end"]),
                            "slot_start": prev_slot["start"],
                            "slot_end": prev_slot["end"],
                            "cls": "shiftmate" if (shift_pair_slot_start and prev_slot["start"] == shift_pair_slot_start) else "",
                            "is_prev_slot": True,
                        }
                    )
                for s in win_slots:
                    cls = ""
                    if cur_slot_start and s["start"] == cur_slot_start:
                        cls = "now"
                    elif shift_pair_slot_start and s["start"] == shift_pair_slot_start:
                        cls = "shiftmate"
                    elif next_slot_start and s["start"] == next_slot_start:
                        cls = "next"
                    rows.append(
                        {
                            "label": s["label"],
                            "task": _pick_cached(area, s["start"], s["end"]),
                            "slot_start": s["start"],
                            "slot_end": s["end"],
                            "cls": cls,
                            "is_prev_slot": False,
                        }
                    )
                return rows

            def render_prio_summary() -> None:
                main_rows: list[dict[str, Any]] = []
                side_rows: list[dict[str, Any]] = []
                vehicles: set[str] = set()
                for area in PRIO_MAIN_AREAS:
                    for rr in _build_area_rows(area, show_all_entries=False):
                        task = rr.get("task") or {}
                        if _task_has_prio_content(task):
                            main_rows.append(rr)
                            veh = _clean_prio_text(task.get("fahrzeug"))
                            if veh:
                                vehicles.add(veh)
                for area in ("ARA", "URD", "SERVICE"):
                    for rr in _build_area_rows(area, show_all_entries=True):
                        task = rr.get("task") or {}
                        if _task_has_prio_content(task):
                            side_rows.append(rr)

                current_label = _slot_label_for_start(cur_slot_start) if cur_slot_start else "-"
                summary_items = [
                    ("Slot", current_label or "-", "slot"),
                    ("Hauptslots", str(len(main_rows)), "main"),
                    ("Fahrzeuge", str(len(vehicles)), "vehicles"),
                    ("Nebenbereiche", str(len(side_rows)), "side"),
                ]
                with ui.element("div").classes("prio-summary-row"):
                    for label, value, kind in summary_items:
                        with ui.element("div").classes(f"prio-stat prio-stat-{kind}"):
                            ui.label(value).classes("prio-stat-value")
                            ui.label(label).classes("prio-stat-label")

            _purge_prio_side_state(now)
            prio_side_state_map = _load_prio_side_state_map()
            admin = is_admin()

            ara_wash_vehicle_keys = {
                _wash_vehicle_key(str(t.get("fahrzeug") or ""))
                for t in (tasks_by_area.get("ARA", []) or [])
                if str(t.get("fahrzeug") or "").strip()
            }
            urd_vehicle_keys = {
                _urd_vehicle_key(str(t.get("fahrzeug") or ""))
                for t in (tasks_by_area.get("URD", []) or [])
                if str(t.get("fahrzeug") or "").strip()
            }

            ara_wash_open_rows_by_vehicle: dict[str, list[dict[str, Any]]] = {}
            urd_open_rows_by_vehicle: dict[str, list[dict[str, Any]]] = {}
            df_open_for_side = df_open.copy()
            if ara_wash_vehicle_keys and not df_open_for_side.empty:
                changed_zus = False
                for _, rr in df_open_for_side.iterrows():
                    veh_raw = str(rr.get("Fahrzeug") or "").strip()
                    if not veh_raw:
                        continue
                    vk = _wash_vehicle_key(veh_raw)
                    if vk not in ara_wash_vehicle_keys:
                        continue
                    row_id = int(rr.get("id"))
                    old_zus = str(rr.get("Zusatzarbeiten") or "")
                    new_zus, added = _ensure_wash_zusatz_entry(old_zus)
                    if not added:
                        continue
                    db_exec(
                        "UPDATE open_tasks SET zusatzarbeiten=? WHERE id=?;",
                        (new_zus, row_id),
                        commit=True,
                    )
                    changed_zus = True
                if changed_zus:
                    df_open_for_side = get_open_tasks_df()

            if not df_open_for_side.empty:
                for _, rr in df_open_for_side.iterrows():
                    veh_raw = str(rr.get("Fahrzeug") or "").strip()
                    if not veh_raw:
                        continue
                    vk_ara = _wash_vehicle_key(veh_raw)
                    if vk_ara in ara_wash_vehicle_keys:
                        ara_wash_open_rows_by_vehicle.setdefault(vk_ara, []).append(
                            {
                                "id": int(rr.get("id")),
                                "zusatz": str(rr.get("Zusatzarbeiten") or ""),
                                "zusatz_done": str(rr.get("zusatz_done") or ""),
                            }
                        )
                    vk_urd = _urd_vehicle_key(veh_raw)
                    if vk_urd in urd_vehicle_keys and _is_urd_open_row(rr):
                        urd_open_rows_by_vehicle.setdefault(vk_urd, []).append(
                            {
                                "id": int(rr.get("id")),
                            }
                        )

            gewerke_open_rows_by_id: dict[int, dict[str, Any]] = {}
            if not df_open_for_side.empty:
                for _, rr in df_open_for_side.iterrows():
                    row_id = int(rr.get("id") or 0)
                    if row_id <= 0:
                        continue
                    gewerke_open_rows_by_id[row_id] = {
                        "id": row_id,
                        "zusatz": str(rr.get("Zusatzarbeiten") or ""),
                        "zusatz_done": str(rr.get("zusatz_done") or ""),
                    }

            def _gewerke_indices_for_row(row_payload: dict[str, Any], item_keys: list[str]) -> list[int]:
                key_set = {str(x or "").strip() for x in item_keys if str(x or "").strip()}
                if not key_set:
                    return []
                items = _parse_zusatz_items(str(row_payload.get("zusatz") or ""))
                out_idx: list[int] = []
                for idx, item in enumerate(items):
                    if _canon_zus_item_key(item) in key_set:
                        out_idx.append(idx)
                return out_idx

            def _gewerke_state_for_sources(source_rows: list[dict[str, Any]]) -> tuple[bool, bool]:
                matched = False
                all_checked = True
                for src in source_rows or []:
                    row_id = int(src.get("id") or 0)
                    row_payload = gewerke_open_rows_by_id.get(row_id)
                    if not row_payload:
                        continue
                    idxs = _gewerke_indices_for_row(row_payload, [str(src.get("item_key") or "")])
                    if not idxs:
                        continue
                    matched = True
                    items = _parse_zusatz_items(str(row_payload.get("zusatz") or ""))
                    bits = _decode_check_string(str(row_payload.get("zusatz_done") or ""), len(items))
                    if not all(bits[idx] for idx in idxs):
                        all_checked = False
                return matched, (matched and all_checked)

            def _set_gewerke_state_for_sources(source_rows: list[dict[str, Any]], checked: bool) -> bool:
                changed = False
                for src in source_rows or []:
                    row_id = int(src.get("id") or 0)
                    row_payload = gewerke_open_rows_by_id.get(row_id)
                    if not row_payload:
                        continue
                    idxs = _gewerke_indices_for_row(row_payload, [str(src.get("item_key") or "")])
                    if not idxs:
                        continue
                    items = _parse_zusatz_items(str(row_payload.get("zusatz") or ""))
                    old_done = str(row_payload.get("zusatz_done") or "")
                    bits = _decode_check_string(old_done, len(items))
                    new_bits = list(bits)
                    for idx in idxs:
                        if 0 <= idx < len(new_bits):
                            new_bits[idx] = bool(checked)
                    new_done = _encode_check_list(new_bits)
                    if new_done == old_done:
                        continue
                    db_exec(
                        "UPDATE open_tasks SET zusatz_done=? WHERE id=?;",
                        (new_done, row_id),
                        commit=True,
                    )
                    row_payload["zusatz_done"] = new_done
                    changed = True
                return changed

            def _row_state_keys(slot_start: datetime | None, slot_end: datetime | None) -> tuple[str, str]:
                end_dt = memo_to_berlin_dt(slot_end) or memo_to_berlin_dt(slot_start)
                if end_dt is None:
                    fallback_now = now_berlin()
                    return "", (fallback_now + timedelta(days=7)).isoformat(timespec="seconds")
                row_end_iso = end_dt.isoformat(timespec="seconds")
                expires_iso = (end_dt + timedelta(days=7)).isoformat(timespec="seconds")
                return row_end_iso, expires_iso

            def _wash_state_for_vehicle(vehicle_key: str) -> tuple[bool, bool]:
                rows = ara_wash_open_rows_by_vehicle.get(vehicle_key, [])
                if not rows:
                    return False, False
                done_vals = [
                    _wash_done_from_row(str(rr.get("zusatz") or ""), str(rr.get("zusatz_done") or ""))
                    for rr in rows
                ]
                return True, bool(done_vals) and all(done_vals)

            def _set_wash_state_for_vehicle(vehicle_key: str, checked: bool) -> bool:
                changed = False
                for rr in ara_wash_open_rows_by_vehicle.get(vehicle_key, []):
                    row_id = int(rr.get("id"))
                    zus_raw = str(rr.get("zusatz") or "")
                    old_done = str(rr.get("zusatz_done") or "")
                    new_done = _set_wash_done_for_row(zus_raw, old_done, checked)
                    if new_done is None or new_done == old_done:
                        continue
                    db_exec(
                        "UPDATE open_tasks SET zusatz_done=? WHERE id=?;",
                        (new_done, row_id),
                        commit=True,
                    )
                    rr["zusatz_done"] = new_done
                    changed = True
                return changed

            def _archive_urd_rows_for_vehicle(vehicle_key: str) -> int:
                if not vehicle_key:
                    return 0
                archived = 0
                for rr in urd_open_rows_by_vehicle.get(vehicle_key, []):
                    oid = int(rr.get("id"))
                    ok, _msg = archive_task(oid)
                    if ok:
                        archived += 1
                return archived

            def _render_area(area: str, *, show_all_entries: bool = False) -> None:
                with ui.card().classes("tl-card"):
                    with ui.row().classes("w-full items-center justify-center gap-3 wrap tl-card-head"):
                        ui.label(_display_area_name(area)).classes("tl-card-title tl-card-title-inline")
                        if (not show_all_entries) and _day_slots_empty_for_area(area):
                            next_task = _next_planned_task_after_day(area)
                            next_vehicle = _clean_prio_text((next_task or {}).get("fahrzeug"))
                            next_start = memo_to_berlin_dt((next_task or {}).get("start"))
                            if next_vehicle:
                                next_text = f"Nächstes Fahrzeug: {next_vehicle}"
                                if next_start:
                                    next_text = f"{next_text} ab {next_start.strftime('%d.%m %H:%M')}"
                                ui.label(next_text).classes("tl-card-next")
                    rows = _build_area_rows(area, show_all_entries=show_all_entries)

                    if not rows:
                        ui.label(" ").classes("empty")
                        return

                    for rr in rows:
                        task = rr["task"]
                        slot_start = rr["slot_start"]
                        slot_end = rr["slot_end"]
                        slot_end_dt = memo_to_berlin_dt(slot_end)
                        label = str(rr["label"])
                        label_html = str(rr.get("label_html") or "").strip()
                        cls = str(rr.get("cls") or "")
                        is_prev_slot = bool(rr.get("is_prev_slot"))
                        slot_lbl = _slot_label_for_start(slot_start) or label
                        bg, fg = TIME_BG.get(slot_lbl, ("#9ca3af", "#000000"))
                        task_veh = _clean_prio_text((task or {}).get("fahrzeug"))
                        task_frist = _clean_prio_text((task or {}).get("frist"))
                        task_hinweis = _clean_prio_text((task or {}).get("hinweis"))
                        task_has_content = bool(task_veh or task_frist or task_hinweis)
                        if task is None or (not task_has_content):
                            bg, fg = ("#9ca3af", "#000000")
                        if slot_end_dt is not None and slot_end_dt <= now:
                            bg, fg = ("#9ca3af", "#000000")

                        row_classes = f"w-full items-start gap-2 tl-item {cls}"
                        if not show_all_entries:
                            row_classes += " tl-item-main"
                        with ui.row().classes(row_classes):
                            if show_all_entries and task is not None and label_html:
                                render_time_badge(label_html, bg, fg, multiline=True)
                            else:
                                render_time_badge(label, bg, fg)
                            with ui.column().classes("grow gap-0"):
                                if task is None or (not task_has_content):
                                    ui.label(" ").classes("tl-veh tl-veh-placeholder")
                                    ui.label(" ").classes("tl-hint tl-hint-placeholder")
                                    continue
                                veh_raw = task_veh
                                veh_key = veh_raw
                                veh_color = ""
                                hint_color = ""

                                suppress_frist = bool(task.get("suppress_frist"))
                                fr = task_frist or "-"
                                if not fr:
                                    fr = "-"
                                hint_parts: list[str] = []
                                has_service = bool(
                                    area in {"4A", "4B", "5A", "5B"} and _has_service_in_slot(veh_key, slot_start, slot_end)
                                )
                                if area == "SERVICE":
                                    if fr and not suppress_frist:
                                        secondary = _slot_secondary_text(
                                            fr,
                                            has_service=False,
                                            suppress_urd=False,
                                            with_prefix=True,
                                        )
                                        if secondary:
                                            hint_parts.append(secondary)
                                else:
                                    if not suppress_frist:
                                        secondary = _slot_secondary_text(
                                            fr,
                                            has_service=has_service,
                                            suppress_urd=area in {"4A", "4B", "5A", "5B"},
                                            with_prefix=True,
                                        )
                                        if secondary:
                                            hint_parts.append(secondary)

                                if (not show_all_entries) and (not suppress_frist):
                                    v = (veh_raw or "").upper().replace(" ", "")
                                    need_rl = False
                                    if v.startswith(("VT646.", "ET445.")) and re.search(r"\bIS(?:4|5)\b", fr, flags=re.I):
                                        need_rl = True
                                    elif v.startswith(("ET4746.", "ET4748.")) and re.search(r"\bF3\b", fr, flags=re.I):
                                        need_rl = True
                                    elif v.startswith("VT1622.") and re.search(r"\bF4\b", fr, flags=re.I):
                                        need_rl = True
                                    if need_rl:
                                        hint_parts.append("Rundlaufmessung")

                                note_raw = _note_for_vehicle(
                                    task.get("hinweis"),
                                    veh_raw,
                                    vehicle_match_key_fn=memo_vehicle_match_key,
                                )
                                if note_raw:
                                    hint_parts.append(note_raw)

                                te = memo_to_berlin_dt(task.get("end"))
                                last_te = memo_to_berlin_dt(last_end_by_area_vehicle.get((area, veh_key)))
                                eff_start = memo_to_berlin_dt(slot_start)
                                if (
                                    (not show_all_entries)
                                    and (not suppress_frist)
                                    and bool(veh_key)
                                    and te is not None
                                    and last_te is not None
                                    and te == last_te
                                    and slot_end_dt is not None
                                    and eff_start is not None
                                    and te <= slot_end_dt
                                    and te > eff_start
                                ):
                                    veh_color = "#faad14"
                                    hint_color = "#faad14"

                                hint_text = " · ".join(x for x in hint_parts if str(x or "").strip())
                                veh_lbl = ui.label(veh_raw or " ").classes("tl-veh")
                                if show_all_entries:
                                    veh_lbl.style("font-size:1.80rem; line-height:1.05;")
                                elif veh_color:
                                    veh_lbl.style(f"color:{veh_color};")

                                hint_lbl = ui.label(hint_text or " ").classes("tl-hint")
                                if hint_color:
                                    hint_lbl.style(f"color:{hint_color};")

            def _render_side_area(area: str) -> None:
                area_norm = str(area or "").strip().upper()
                rows = _build_area_rows(area_norm, show_all_entries=True)
                with ui.card().classes("tl-card"):
                    ui.label(_display_area_name(area_norm)).classes("tl-card-title")
                    if not rows:
                        ui.label(" ").classes("empty")
                        return

                    for rr in rows:
                        task = rr["task"]
                        slot_start = memo_to_berlin_dt(rr.get("slot_start"))
                        slot_end = memo_to_berlin_dt(rr.get("slot_end"))
                        label = str(rr.get("label") or "")
                        label_html = str(rr.get("label_html") or "").strip()
                        row_end_iso, expires_at_iso = _row_state_keys(slot_start, slot_end)
                        color_anchor = memo_to_berlin_dt((task or {}).get("start")) if area_norm == "SERVICE" else slot_start
                        slot_lbl = _slot_label_for_start(color_anchor)
                        bg, fg = TIME_BG.get(slot_lbl or label, ("#9ca3af", "#000000"))
                        task_veh = _clean_prio_text((task or {}).get("fahrzeug"))
                        task_frist = _clean_prio_text((task or {}).get("frist"))
                        task_hinweis = _clean_prio_text((task or {}).get("hinweis"))
                        task_hinweis_overview = _clean_prio_text((task or {}).get("hinweis_overview"))
                        task_has_content = bool(task_veh or task_frist or task_hinweis or task_hinweis_overview)
                        if task is None or (not task_has_content):
                            bg, fg = ("#9ca3af", "#000000")

                        veh_raw = task_veh
                        source_rows = list((task or {}).get("source_rows") or [])
                        vehicle_key = _urd_vehicle_key(veh_raw) if area_norm == "URD" else _wash_vehicle_key(veh_raw)
                        has_open = bool(urd_open_rows_by_vehicle.get(vehicle_key, [])) if area_norm == "URD" else False
                        default_checked = False
                        if task is not None and task_has_content:
                            if area_norm == "URD":
                                default_checked = bool(prio_side_state_map.get((area_norm, vehicle_key, row_end_iso), False))
                            elif area_norm == "SERVICE":
                                has_open, default_checked = _gewerke_state_for_sources(source_rows)
                            else:
                                has_open, wash_done = _wash_state_for_vehicle(vehicle_key)
                                persisted = bool(prio_side_state_map.get((area_norm, vehicle_key, row_end_iso), False))
                                default_checked = bool(wash_done or persisted)

                        if default_checked:
                            bg, fg = ("#9ca3af", "#000000")

                        with ui.row().classes("w-full items-start gap-2 tl-item no-wrap"):
                            if task is not None and task_has_content and label_html:
                                render_time_badge(label_html, bg, fg, side=True, multiline=True)
                            else:
                                render_time_badge(label, bg, fg, side=True)
                            veh_style = "color:#16a34a;" if default_checked else ""
                            with ui.column().classes("grow min-w-0 gap-0 tl-side-content"):
                                ui.label(veh_raw or " ").classes("tl-veh tl-side-veh").style(veh_style)
                                if area_norm == "SERVICE":
                                    hint_style = "font-size:1.05rem; line-height:1.15;"
                                    if default_checked:
                                        hint_style += "color:#16a34a;"
                                    ui.label(task_hinweis_overview or " ").classes("tl-hint tl-side-hint").style(hint_style)

                            if task is None or (not task_has_content):
                                ui.label(" ")
                                continue

                            lock_uncheck = (not admin) and default_checked
                            cb = ui.checkbox(value=default_checked).props("dense").classes("tl-side-check")
                            if lock_uncheck:
                                cb.disable()

                            def _on_side_change(
                                e,
                                *,
                                area_name=area_norm,
                                veh_key=vehicle_key,
                                task_sources=source_rows,
                                old_checked=default_checked,
                                has_open_rows=has_open,
                                row_end=row_end_iso,
                                expires=expires_at_iso,
                            ) -> None:
                                requested = bool(e.value)
                                checked = requested
                                if (not admin) and old_checked and (not checked):
                                    ui.notify("Abhaken kann nur als Admin rückgängig gemacht werden.", type="warning")
                                    content.refresh()
                                    return
                                if checked == old_checked:
                                    return

                                open_tasks_changed = False
                                if area_name == "URD":
                                    if checked and has_open_rows:
                                        moved = _archive_urd_rows_for_vehicle(veh_key)
                                        open_tasks_changed = moved > 0
                                elif area_name == "SERVICE":
                                    if has_open_rows:
                                        open_tasks_changed = _set_gewerke_state_for_sources(task_sources, checked)
                                else:
                                    if has_open_rows:
                                        open_tasks_changed = _set_wash_state_for_vehicle(veh_key, checked)

                                if area_name != "SERVICE" and veh_key and row_end:
                                    _save_prio_side_state(area_name, veh_key, row_end, checked, expires)
                                    prio_side_state_map[(area_name, veh_key, row_end)] = checked

                                if open_tasks_changed:
                                    ui.notify("Tagesplanungsstatus aktualisiert.", type="positive")
                                content.refresh()

                            cb.on_value_change(_on_side_change)

            with ui.element("div").classes("tl-grid-4"):
                for area in PRIO_MAIN_AREAS:
                    _render_area(area, show_all_entries=False)

            with ui.element("div").classes("tl-grid-3"):
                _render_side_area("ARA")
                _render_side_area("URD")
                _render_side_area("SERVICE")

            other_areas = sorted(
                a for a in tasks_by_area.keys() if a not in set(PRIO_MAIN_AREAS + PRIO_SIDE_AREAS) and a != "RWS"
            )
            if other_areas:
                with ui.element("div").classes("tl-grid-1"):
                    for area in other_areas:
                        _render_area(area, show_all_entries=False)

    day_input.on_value_change(lambda _e: content.refresh())
    content()
    create_page_timer(float(refresh_interval_seconds), lambda: _refresh_when_no_dialog(content.refresh))
