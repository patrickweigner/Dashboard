
from __future__ import annotations

import copy
from datetime import date, datetime, time, timedelta
import re
import threading
from typing import Any

import pandas as pd


_CACHE_LOCK = threading.Lock()
_WEEKLY_MAIN_CACHE: dict[tuple[int, str, str], dict[str, list[dict[str, Any]]]] = {}
_WEEKLY_SIDE_CACHE: dict[tuple[int, str, str], dict[str, list[dict[str, Any]]]] = {}
_CURRENT_SLOT_KEYS_CACHE: tuple[int, pd.Timestamp | None, pd.Timestamp | None, frozenset[str]] | None = None


def configure(**deps) -> None:
    globals().update(deps)


def _weekly_cache_key(week_start: date, today: date) -> tuple[int, str, str]:
    return (_current_data_version(), week_start.isoformat(), today.isoformat())


def _slot_keys_data_version() -> int:
    version_fn = globals().get("_current_data_version")
    if not callable(version_fn):
        from core import db as _core_db

        version_fn = _core_db._current_data_version
    try:
        from core import db as _core_db

        if version_fn is _core_db._current_data_version and getattr(_core_db, "_DB_FILE_STATE_TOKEN", None) is not None:
            return int(getattr(_core_db, "_DATA_VERSION"))
    except Exception:
        pass
    return int(version_fn())


def _get_weekly_cache(
    cache: dict[tuple[int, str, str], dict[str, list[dict[str, Any]]]],
    key: tuple[int, str, str],
) -> dict[str, list[dict[str, Any]]] | None:
    with _CACHE_LOCK:
        cached = cache.get(key)
        if cached is None:
            return None
        return copy.deepcopy(cached)


def _set_weekly_cache(
    cache: dict[tuple[int, str, str], dict[str, list[dict[str, Any]]]],
    key: tuple[int, str, str],
    value: dict[str, list[dict[str, Any]]],
) -> None:
    with _CACHE_LOCK:
        stale_keys = [cache_key for cache_key in cache if cache_key[0] != key[0]]
        for stale_key in stale_keys:
            cache.pop(stale_key, None)
        if len(cache) >= 16:
            cache.clear()
        cache[key] = copy.deepcopy(value)


def _get_current_slot_keys_cache(version: int, now_utc: pd.Timestamp) -> set[str] | None:
    with _CACHE_LOCK:
        cached = _CURRENT_SLOT_KEYS_CACHE
        if cached is None:
            return None
        cached_version, valid_from, valid_until, keys = cached
        if cached_version != version:
            return None
        if valid_from is not None and now_utc < valid_from:
            return None
        if valid_until is not None and now_utc >= valid_until:
            return None
        return set(keys)


def _set_current_slot_keys_cache(
    version: int,
    valid_from: pd.Timestamp | None,
    valid_until: pd.Timestamp | None,
    keys: set[str],
) -> None:
    global _CURRENT_SLOT_KEYS_CACHE
    with _CACHE_LOCK:
        # ECM4 imports bump the data version; slot boundaries expire the cache while time moves on.
        _CURRENT_SLOT_KEYS_CACHE = (version, valid_from, valid_until, frozenset(keys))


def _shift_day(dt: datetime) -> date:
    return (dt - timedelta(days=1)).date() if dt.time() < time(6, 0) else dt.date()


def _build_slots_for_day(day_val: date) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    shift_cutoff = time(6, 0)
    for st_t, en_t, label, mode in SLOT_DEFS:
        start_day = day_val + timedelta(days=1) if st_t < shift_cutoff else day_val
        st_dt = datetime.combine(start_day, st_t, tzinfo=BERLIN)
        if mode == "next" or en_t <= st_t:
            end_day = start_day + timedelta(days=1)
        else:
            end_day = start_day
        en_dt = datetime.combine(end_day, en_t, tzinfo=BERLIN)
        out.append({"start": st_dt, "end": en_dt, "label": label})
    out.sort(key=lambda x: x["start"])
    return out


def _shift_pair_group(label: str) -> str | None:
    lbl = str(label or "").strip()
    if lbl in {"6:00 - 10:00", "10:00 - 14:18"}:
        return "s1"
    if lbl in {"14:00 - 18:00", "18:00 - 22:18"}:
        return "s2"
    if lbl in {"21:42 - 2:00", "2:00 - 6:00"}:
        return "s3"
    return None


def _slot_end_for_start(start_dt: datetime) -> datetime:
    st_local = as_berlin(start_dt) or start_dt
    st_t = st_local.time().replace(tzinfo=None, second=0, microsecond=0)
    for s_st, s_en, _lbl, mode in SLOT_DEFS:
        if s_st == st_t:
            end_day = st_local.date() + timedelta(days=1) if (mode == "next" or s_en <= s_st) else st_local.date()
            return datetime.combine(end_day, s_en, tzinfo=BERLIN)
    return st_local + timedelta(hours=4)


def _next_slot_start_for_start(start_dt: datetime) -> datetime:
    st_local = as_berlin(start_dt) or start_dt
    base = st_local.date()
    starts: list[datetime] = []
    for day_val in (base - timedelta(days=1), base, base + timedelta(days=1)):
        for s in _build_slots_for_day(day_val):
            starts.append(s["start"])
    after = [x for x in starts if x > st_local]
    if after:
        return min(after)
    return _slot_end_for_start(st_local)


def _slot_label_for_start(start_dt: datetime | None) -> str | None:
    if start_dt is None:
        return None
    st_local = as_berlin(start_dt) or start_dt
    st_t = st_local.time().replace(tzinfo=None, second=0, microsecond=0)
    for def_st, _def_en, lbl, _mode in SLOT_DEFS:
        if st_t == def_st:
            return lbl
    return None


def _clean_plan_text(value: Any) -> str:
    txt = _clean_nullable_text(value)
    if txt in {"-", "—"}:
        return ""
    return txt


def _display_vehicle_code(value: Any) -> str:
    txt = _clean_plan_text(value)
    if not txt:
        return ""
    return _norm_vehicle(txt) or txt


def _slot_secondary_text(
    frist_value: Any,
    *,
    has_service: bool = False,
    suppress_urd: bool = False,
    with_prefix: bool = False,
) -> str:
    frist_txt = _clean_plan_text(frist_value)
    if suppress_urd and frist_txt and re.search(r"\bURD\b", frist_txt, flags=re.I):
        frist_txt = ""
    parts: list[str] = []
    if frist_txt:
        parts.append(f"Frist: {frist_txt}" if with_prefix else frist_txt)
    if has_service:
        parts.append("Service")
    return " · ".join(parts)


def _vehicle_keys_from_note_text(note_text: Any) -> set[str]:
    keys: set[str] = set()
    txt = str(note_text or "")
    for m in RX_VEHICLE.finditer(txt):
        prefix = (m.group(1) or "").upper().strip()
        num = (m.group(2) or "").strip()
        key = ((prefix + num).replace(" ", "") if prefix else num).casefold()
        if key:
            keys.add(key)
    return keys


def _note_segments_by_vehicle_key(note_text: Any) -> dict[str, str]:
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


def _note_text_for_vehicle(note_text: Any, vehicle_raw: Any) -> str:
    txt = _clean_plan_text(note_text)
    if not txt:
        return ""
    segments = _note_segments_by_vehicle_key(txt)
    if not segments:
        return txt
    target = _vehicle_compare_key(vehicle_raw)
    if not target:
        return ""
    return str(segments.get(target) or "").strip()


def _build_current_prio_frist_maps(df_open: pd.DataFrame | None = None) -> tuple[dict[str, str], dict[str, str]]:
    df_src = df_open if df_open is not None else get_open_tasks_df()
    frist_by_vehicle: dict[str, str] = {}
    frist_by_vehicle_urd: dict[str, str] = {}
    if df_src is None or df_src.empty:
        return frist_by_vehicle, frist_by_vehicle_urd

    for _, rr in df_src.iterrows():
        veh_raw = _clean_plan_text(rr.get("Fahrzeug"))
        if not veh_raw:
            continue
        veh = _display_vehicle_code(veh_raw) or veh_raw
        fr = _clean_plan_text(rr.get("Friststufe"))
        target = frist_by_vehicle_urd if _is_urd_open_row(rr) else frist_by_vehicle
        if veh not in target or target[veh] in {"", "-"}:
            target[veh] = fr

    return frist_by_vehicle, frist_by_vehicle_urd


def _resolve_prio_frist(
    area_code: str,
    vehicle: Any,
    current_maps: tuple[dict[str, str], dict[str, str]],
    hist_maps: tuple[dict[str, str], dict[str, str]],
) -> str:
    veh = _display_vehicle_code(vehicle)
    if not veh:
        return "-"
    cur_main, cur_urd = current_maps
    hist_main, hist_urd = hist_maps
    if _normalize_workshop_area(area_code) == "URD":
        return cur_urd.get(veh) or hist_urd.get(veh) or "-"
    return cur_main.get(veh) or hist_main.get(veh) or "-"


def _weekday_name_de(day_val: date) -> str:
    idx = int(day_val.weekday())
    if 0 <= idx < len(WEEKDAY_NAMES_DE):
        return WEEKDAY_NAMES_DE[idx]
    return day_val.strftime("%A")


def _build_open_task_vehicle_lookup() -> dict[str, list[dict[str, Any]]]:
    df = get_open_tasks_df().copy()
    lookup: dict[str, list[dict[str, Any]]] = {}
    if df.empty:
        return lookup

    for _, rr in df.iterrows():
        vehicle_key = _vehicle_compare_key(rr.get("Fahrzeug"))
        if not vehicle_key:
            continue
        lookup.setdefault(vehicle_key, []).append(
            {
                "frist": _clean_plan_text(rr.get("Friststufe")),
                "start": as_berlin(rr.get("Anfang")),
                "end": as_berlin(rr.get("Fertig")),
            }
        )
    return lookup


def _frist_for_vehicle_slot(
    open_lookup: dict[str, list[dict[str, Any]]],
    vehicle_raw: Any,
    slot_start: datetime,
    *,
    area_code: str = "",
) -> str:
    vehicle_key = _vehicle_compare_key(_display_vehicle_code(vehicle_raw))
    if not vehicle_key:
        return ""

    candidates = open_lookup.get(vehicle_key) or []
    if not candidates:
        return ""

    slot_end = _slot_end_for_start(slot_start)
    area_norm = _normalize_workshop_area(area_code)
    best_frist = ""
    best_score: tuple[Any, ...] | None = None

    for idx, item in enumerate(candidates):
        frist = _clean_plan_text(item.get("frist"))
        start_dt = as_berlin(item.get("start"))
        end_dt = as_berlin(item.get("end"))
        has_window = start_dt is not None or end_dt is not None
        exact_start = bool(start_dt is not None and abs((start_dt - slot_start).total_seconds()) < 60)

        overlaps = False
        if start_dt is not None and end_dt is not None:
            overlaps = start_dt < slot_end and end_dt > slot_start
        elif start_dt is not None:
            overlaps = start_dt < slot_end
        elif end_dt is not None:
            overlaps = end_dt > slot_start

        anchor = start_dt or end_dt or slot_start
        distance = abs((anchor - slot_start).total_seconds()) if isinstance(anchor, datetime) else 0.0
        is_urd = "urd" in frist.casefold()

        score = (
            1 if (area_norm in PRIO_MAIN_AREAS and is_urd) else 0,
            0 if overlaps else 1,
            0 if exact_start else 1,
            0 if has_window else 1,
            distance,
            idx,
        )
        if best_score is None or score < best_score:
            best_score = score
            best_frist = frist

    return best_frist


def _build_weekly_main_area_plan(week_start: date) -> dict[str, list[dict[str, Any]]]:
    today = now_berlin().date()
    cache_key = _weekly_cache_key(week_start, today)
    cached = _get_weekly_cache(_WEEKLY_MAIN_CACHE, cache_key)
    if cached is not None:
        return cached
    areas = list(PRIO_MAIN_AREAS)
    df_open = get_open_tasks_df()
    open_lookup = _build_open_task_vehicle_lookup()
    current_frist_maps = _build_current_prio_frist_maps(df_open)
    hist_frist_maps = _get_prio_frist_history_maps()
    gewerke_events = _collect_gewerke_slot_events(df_open)
    out: dict[str, list[dict[str, Any]]] = {area: [] for area in areas}

    for day_offset in range(7):
        day_val = week_start + timedelta(days=day_offset)
        plan_df = load_ecm4_plan_df(ref_dt=day_val)
        plan_service_rows = _collect_ecm4_service_assignments(plan_df)
        tasks_by_area: dict[str, list[dict[str, Any]]] = {}
        service_slots: set[tuple[str, datetime]] = set()
        day_slots = _build_slots_for_day(day_val)
        day_slot_keys = {slot["start"].isoformat(timespec="minutes") for slot in day_slots}

        if not plan_df.empty:
            for _, rr in plan_df.iterrows():
                area_code = _normalize_workshop_area(rr.get("area"))
                slot_start = as_berlin(rr.get("slot_start"))
                if slot_start is None:
                    continue
                vehicle = _display_vehicle_code(rr.get("fahrzeug"))
                if area_code in {"RWS", "SERVICE"}:
                    continue
                if not vehicle:
                    continue
                frist = _resolve_prio_frist(area_code, vehicle, current_frist_maps, hist_frist_maps)
                tasks_by_area.setdefault(area_code, []).append(
                    {
                        "fahrzeug": vehicle,
                        "frist": frist,
                        "hinweis": None,
                        "hinweis_overview": None,
                        "start": slot_start,
                        "end": _slot_end_for_start(slot_start),
                        "slot_based": True,
                    }
                )

            track_refs_by_vehicle: dict[str, list[dict[str, Any]]] = {}
            for area_code in areas:
                for task in tasks_by_area.get(area_code, []) or []:
                    if not bool(task.get("slot_based")):
                        continue
                    veh = _clean_plan_text(task.get("fahrzeug"))
                    task_start = as_berlin(task.get("start"))
                    if not veh or task_start is None:
                        continue
                    track_refs_by_vehicle.setdefault(_vehicle_compare_key(veh), []).append(
                        {"area": area_code, "start": task_start, "veh": veh}
                    )

            for refs in track_refs_by_vehicle.values():
                refs.sort(key=lambda item: item["start"])

            def _task_at_exact_slot(area_code: str, slot_dt: datetime) -> dict[str, Any] | None:
                for task in tasks_by_area.get(area_code, []) or []:
                    if not bool(task.get("slot_based")):
                        continue
                    task_start = as_berlin(task.get("start"))
                    if task_start is None:
                        continue
                    if abs((task_start - slot_dt).total_seconds()) < 60:
                        return task
                return None

            for event in gewerke_events:
                slot_dt = as_berlin(event.get("start"))
                vehicle_key = str(event.get("vehicle_key") or "").strip()
                if slot_dt is None or slot_dt.isoformat(timespec="minutes") not in day_slot_keys or not vehicle_key:
                    continue
                refs = track_refs_by_vehicle.get(vehicle_key) or []
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
                    prev_delta = (slot_dt - prev_ref["start"]).total_seconds()
                    next_delta = (next_ref["start"] - slot_dt).total_seconds()
                    chosen_ref = prev_ref if prev_delta <= next_delta else next_ref
                elif prev_ref is not None:
                    chosen_ref = prev_ref
                elif next_ref is not None:
                    chosen_ref = next_ref
                if chosen_ref is None:
                    continue

                target_area = _normalize_workshop_area(chosen_ref.get("area"))
                hint_label = _clean_plan_text(event.get("label"))
                hint_overview = _clean_plan_text(event.get("overview"))
                existing = _task_at_exact_slot(target_area, slot_dt)
                if existing and _clean_plan_text(existing.get("fahrzeug")):
                    if _vehicle_compare_key(existing.get("fahrzeug")) == vehicle_key:
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
                    next_start = as_berlin(next_same_area.get("start"))
                    if next_start is not None:
                        if next_start.date() == slot_dt.date():
                            suffix = f"Fristarbeiten erst ab {next_start.strftime('%H:%M')}"
                        else:
                            suffix = f"Fristarbeiten erst ab {next_start.strftime('%d.%m %H:%M')}"
                        hint_aug = _append_unique_inline_text(hint_aug, suffix)
                        overview_aug = _append_unique_inline_text(overview_aug, suffix)

                tasks_by_area.setdefault(target_area, []).append(
                    {
                        "fahrzeug": str(chosen_ref.get("veh") or "").strip(),
                        "frist": "",
                        "hinweis": hint_aug or None,
                        "hinweis_overview": overview_aug or None,
                        "start": slot_dt,
                        "end": _slot_end_for_start(slot_dt),
                        "slot_based": True,
                        "suppress_frist": True,
                    }
                )

        for area_code, tasks in list(tasks_by_area.items()):
            tasks.sort(
                key=lambda item: (
                    as_berlin(item.get("start")) or datetime.min.replace(tzinfo=BERLIN),
                    as_berlin(item.get("end")) or datetime.max.replace(tzinfo=BERLIN),
                )
            )

        for task in plan_service_rows:
            vehicle_key = _vehicle_compare_key(task.get("fahrzeug"))
            slot_start = as_berlin(task.get("start"))
            if vehicle_key and slot_start is not None:
                service_slots.add((vehicle_key, slot_start))

        def _pick_task_for_slot(area_code: str, slot_start: datetime) -> dict[str, Any] | None:
            for task in tasks_by_area.get(area_code, []) or []:
                task_start = as_berlin(task.get("start"))
                if task_start is None:
                    continue
                if abs((task_start - slot_start).total_seconds()) < 60:
                    return task
            return None

        for area_code in areas:
            slots: list[dict[str, Any]] = []
            for slot in day_slots:
                task = _pick_task_for_slot(area_code, slot["start"])
                vehicle = _display_vehicle_code((task or {}).get("fahrzeug"))
                hint = _clean_plan_text((task or {}).get("hinweis"))
                frist_value = _clean_plan_text((task or {}).get("frist"))
                suppress_frist = bool((task or {}).get("suppress_frist"))
                vehicle_key = _vehicle_compare_key(vehicle)
                has_service = bool(vehicle_key and (vehicle_key, slot["start"]) in service_slots)
                if suppress_frist:
                    frist = ""
                elif vehicle:
                    frist = _frist_for_vehicle_slot(open_lookup, vehicle, slot["start"], area_code=area_code) or frist_value
                else:
                    frist = frist_value
                secondary = _slot_secondary_text(
                    frist,
                    has_service=False,
                    suppress_urd=True,
                    with_prefix=False,
                )
                sub_parts: list[str] = []
                if secondary:
                    sub_parts.append(secondary)
                elif has_service:
                    sub_parts.append("Service")
                if hint:
                    sub_parts.append(hint)
                occupied = bool(vehicle or frist_value or hint)
                slots.append(
                    {
                        "label": str(slot["label"]),
                        "occupied": occupied,
                        "vehicle": vehicle or ("Gewerk" if occupied else "Frei"),
                        "vehicle_key": vehicle_key,
                        "frist": " · ".join(part for part in sub_parts if part),
                    }
                )

            out[area_code].append(
                {
                    "day_name": _weekday_name_de(day_val),
                    "date_label": day_val.strftime("%d.%m.%Y"),
                    "is_today": day_val == today,
                    "slots": slots,
                }
            )

    for area_code in areas:
        flat_slots: list[dict[str, Any]] = []
        for day in out.get(area_code) or []:
            for slot in day.get("slots") or []:
                flat_slots.append(slot)

        idx = 0
        while idx < len(flat_slots):
            if bool(flat_slots[idx].get("occupied")):
                idx += 1
                continue

            gap_start = idx
            while idx < len(flat_slots) and (not bool(flat_slots[idx].get("occupied"))):
                idx += 1
            gap_end = idx - 1

            prev_slot = flat_slots[gap_start - 1] if gap_start > 0 else None
            next_slot = flat_slots[idx] if idx < len(flat_slots) else None
            if prev_slot is None or next_slot is None:
                continue

            prev_key = str(prev_slot.get("vehicle_key") or "").strip()
            next_key = str(next_slot.get("vehicle_key") or "").strip()
            prev_vehicle = _display_vehicle_code(prev_slot.get("vehicle"))
            next_vehicle = _display_vehicle_code(next_slot.get("vehicle"))
            if not prev_key or not next_key or prev_key != next_key:
                continue
            if not prev_vehicle or not next_vehicle or prev_vehicle != next_vehicle:
                continue

            for fill_idx in range(gap_start, gap_end + 1):
                flat_slots[fill_idx]["occupied"] = True
                flat_slots[fill_idx]["vehicle"] = prev_vehicle
                flat_slots[fill_idx]["vehicle_key"] = prev_key
                flat_slots[fill_idx]["frist"] = "belegt"

    _set_weekly_cache(_WEEKLY_MAIN_CACHE, cache_key, out)
    return out


def _build_weekly_side_area_plan(week_start: date) -> dict[str, list[dict[str, Any]]]:
    today = now_berlin().date()
    cache_key = _weekly_cache_key(week_start, today)
    cached = _get_weekly_cache(_WEEKLY_SIDE_CACHE, cache_key)
    if cached is not None:
        return cached
    areas = ["ARA", "URD", "RWS"]
    current_frist_maps = _build_current_prio_frist_maps()
    hist_frist_maps = _get_prio_frist_history_maps()
    out: dict[str, list[dict[str, Any]]] = {area: [] for area in areas}
    rws_df = load_rws_week_plan_df()
    rws_tasks: list[dict[str, Any]] = []
    if not rws_df.empty:
        for _, rr in rws_df.iterrows():
            vehicle = _display_vehicle_code(rr.get("fahrzeug"))
            start_dt = as_berlin(rr.get("start"))
            end_dt = as_berlin(rr.get("end"))
            if not vehicle or start_dt is None or end_dt is None:
                continue
            rws_tasks.append(
                {
                    "fahrzeug": vehicle,
                    "start": start_dt,
                    "end": end_dt,
                }
            )
        rws_tasks.sort(key=lambda item: (item["start"], item["end"], str(item.get("fahrzeug") or "")))

    for day_offset in range(7):
        day_val = week_start + timedelta(days=day_offset)
        plan_df = load_ecm4_plan_df(ref_dt=day_val)
        tasks_by_area: dict[str, list[dict[str, Any]]] = {"ARA": [], "URD": []}

        if not plan_df.empty:
            for _, rr in plan_df.iterrows():
                area_code = _normalize_workshop_area(rr.get("area"))
                if area_code not in {"ARA", "URD"}:
                    continue
                slot_start = as_berlin(rr.get("slot_start"))
                if slot_start is None:
                    continue
                vehicle = _display_vehicle_code(rr.get("fahrzeug"))
                if not vehicle:
                    continue
                frist = _resolve_prio_frist(area_code, vehicle, current_frist_maps, hist_frist_maps)
                raw_hint = _clean_plan_text(rr.get("hinweis"))
                tasks_by_area[area_code].append(
                    {
                        "fahrzeug": vehicle,
                        "frist": frist,
                        "hinweis": _note_text_for_vehicle(raw_hint, vehicle) or None,
                        "start": slot_start,
                        "end": _slot_end_for_start(slot_start),
                    }
                )

        for area_code, tasks in tasks_by_area.items():
            tasks.sort(
                key=lambda item: (
                    as_berlin(item.get("start")) or datetime.min.replace(tzinfo=BERLIN),
                    as_berlin(item.get("end")) or datetime.max.replace(tzinfo=BERLIN),
                )
            )

        def _pick_exact_slot_task(area_code: str, slot_start: datetime) -> dict[str, Any] | None:
            for task in tasks_by_area.get(area_code, []) or []:
                task_start = as_berlin(task.get("start"))
                if task_start is None:
                    continue
                if abs((task_start - slot_start).total_seconds()) < 60:
                    return task
            return None

        def _pick_rws_task(slot_start: datetime, slot_end: datetime) -> dict[str, Any] | None:
            for task in rws_tasks:
                task_start = as_berlin(task.get("start"))
                task_end = as_berlin(task.get("end"))
                if task_start is None or task_end is None:
                    continue
                if task_start < slot_end and task_end > slot_start:
                    return task
            return None

        day_slots = _build_slots_for_day(day_val)
        for area_code in areas:
            slots: list[dict[str, Any]] = []
            for slot in day_slots:
                if area_code == "RWS":
                    task = _pick_rws_task(slot["start"], slot["end"])
                else:
                    task = _pick_exact_slot_task(area_code, slot["start"])

                vehicle = _display_vehicle_code((task or {}).get("fahrzeug"))
                occupied = bool(vehicle)
                slots.append(
                    {
                        "label": str(slot["label"]),
                        "occupied": occupied,
                        "vehicle": vehicle or "Frei",
                        "frist": "",
                    }
                )

            out[area_code].append(
                {
                    "day_name": _weekday_name_de(day_val),
                    "date_label": day_val.strftime("%d.%m.%Y"),
                    "is_today": day_val == today,
                    "slots": slots,
                }
            )

    _set_weekly_cache(_WEEKLY_SIDE_CACHE, cache_key, out)
    return out

def _current_slot_vehicle_keys_from_ecm4() -> set[str]:
    version = _slot_keys_data_version()
    now_utc = pd.Timestamp(now_berlin()).tz_convert("UTC")
    cached = _get_current_slot_keys_cache(version, now_utc)
    if cached is not None:
        return cached

    df = load_ecm4_plan_df()
    if df.empty:
        _set_current_slot_keys_cache(version, None, None, set())
        return set()
    tmp = df.copy()
    tmp["slot_start"] = pd.to_datetime(tmp["slot_start"], utc=True, errors="coerce")
    tmp = tmp[tmp["slot_start"].notna()].copy()
    if tmp.empty:
        _set_current_slot_keys_cache(version, None, None, set())
        return set()
    slots = sorted(tmp["slot_start"].dropna().drop_duplicates().tolist())
    from bisect import bisect_right

    raw_idx = int(bisect_right(slots, now_utc) - 1)
    if raw_idx < 0:
        idx = 0
        valid_from = None
    elif raw_idx >= len(slots):
        idx = len(slots) - 1
        valid_from = slots[idx]
    else:
        idx = raw_idx
        valid_from = slots[idx]
    cur_slot = slots[idx]
    valid_until = slots[idx + 1] if idx + 1 < len(slots) else None
    cur = tmp[tmp["slot_start"] == cur_slot].copy()
    keys: set[str] = set()
    for _, rr in cur.iterrows():
        veh_raw = str(rr.get("fahrzeug") or "").strip()
        if not veh_raw:
            continue
        veh = _norm_vehicle(veh_raw) or veh_raw
        keys.add(veh.casefold())
    _set_current_slot_keys_cache(version, valid_from, valid_until, keys)
    return keys

def _collect_ecm4_service_assignments(plan_df: pd.DataFrame) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if plan_df is None or plan_df.empty:
        return out

    for _, rr in plan_df.iterrows():
        area_code = _normalize_workshop_area(rr.get("area")).replace(" ", "")
        if area_code != "SERVICE":
            continue
        vehicle = _display_vehicle_code(rr.get("fahrzeug"))
        slot_start = as_berlin(rr.get("slot_start"))
        if not vehicle or slot_start is None:
            continue
        out.append(
            {
                "fahrzeug": vehicle,
                "start": slot_start,
                "end": _slot_end_for_start(slot_start),
            }
        )

    out.sort(
        key=lambda item: (
            as_berlin(item.get("start")) or datetime.min.replace(tzinfo=BERLIN),
            str(item.get("fahrzeug") or ""),
        )
    )
    return out
