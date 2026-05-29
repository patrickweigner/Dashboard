from __future__ import annotations

from datetime import date, datetime, time, timedelta
import re
from typing import Any

import pandas as pd


BERLIN = None
FRIST_CHECK_ITEMS: list[str] = []
_fr_items_for_vehicle_and_frist = None
_configured_work_package_titles_for_vehicle_and_frist = None
_build_slots_for_day = None
_display_vehicle_code = None
_norm = None
_norm_vehicle = None
_shift_day = None
_slot_end_for_start = None
as_berlin = None


def configure(**deps) -> None:
    globals().update(deps)


def _short_gewerk_label(text: Any) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "").strip())
    if not cleaned:
        return ""
    m = re.search(r"\bzeros\s+([a-z0-9]+)\b", cleaned, flags=re.I)
    if m:
        return str(m.group(1) or "").strip().upper()
    for pat, label in [
        (r"\bUT\b", "UT"),
        (r"\bMT\b", "MT"),
        (r"\bLWU\b", "LWU"),
        (r"\bGL\b", "GL"),
        (r"\bEBT\b", "EBT"),
    ]:
        if re.search(pat, cleaned, flags=re.I):
            return label
    if re.search(r"\batlas\s+copco\b", cleaned, flags=re.I):
        return "Atlas Copco"
    return cleaned


def _parse_gewerke_entries_legacy(raw_text: Any) -> list[dict[str, Any]]:
    txt = str(raw_text or "")
    if not txt.strip():
        return []

    out: list[dict[str, Any]] = []
    rx = re.compile(
        r"^\s*[-•]?\s*(\d{1,2}\.\d{1,2}\.\d{2,4})\s*,\s*(\d{1,2}:\d{2})(?:\s*uhr)?\s*(?:(?::|,|--?>)\s*)?(.+?)\s*$",
        flags=re.I,
    )
    for raw_line in txt.splitlines():
        line = str(raw_line or "").strip()
        if not line:
            continue
        m = rx.match(line)
        if not m:
            continue
        date_txt = str(m.group(1) or "").strip()
        time_txt = str(m.group(2) or "").strip()
        detail_txt = re.sub(r"\s+", " ", str(m.group(3) or "").strip(" ,-:>"))
        if not detail_txt:
            continue

        event_dt: datetime | None = None
        for fmt in ("%d.%m.%y %H:%M", "%d.%m.%Y %H:%M"):
            try:
                event_dt = datetime.strptime(f"{date_txt} {time_txt}", fmt).replace(tzinfo=BERLIN)
                break
            except ValueError:
                continue
        if event_dt is None:
            continue

        out.append(
            {
                "timestamp": event_dt,
                "text": detail_txt,
                "label": _short_gewerk_label(detail_txt),
                "item_key": _canon_zus_item_key(re.sub(r"^\s*[-•]\s*", "", line, flags=re.I)),
            }
        )
    return out


def _strip_gewerk_prefix(text: Any) -> str:
    return re.sub(
        r"^\s*(?:[-*]|\u2022|\u00e2\u20ac\u00a2|\u00c3\u00a2\u00e2\u201a\u00ac\u00c2\u00a2)?\s*",
        "",
        str(text or "").strip(),
        flags=re.I,
    )


def _clean_gewerk_detail(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip(" ,-:>")).strip()


def _parse_gewerk_date(date_txt: Any) -> date | None:
    raw = str(date_txt or "").strip()
    if not raw:
        return None
    for fmt in ("%d.%m.%y", "%d.%m.%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _coerce_gewerk_date(value: Any) -> date | None:
    if value is None:
        return None
    dt = as_berlin(value) if callable(as_berlin) else None
    if dt is not None:
        return dt.date()
    try:
        ts = pd.to_datetime(value, errors="coerce", dayfirst=True)
    except Exception:
        return None
    if pd.isna(ts):
        return None
    if isinstance(ts, pd.Timestamp):
        return ts.date()
    if isinstance(ts, datetime):
        return ts.date()
    return None


def _first_gewerk_date(raw_text: Any) -> date | None:
    for m in re.finditer(r"\b(\d{1,2}\.\d{1,2}\.\d{2,4})\b", str(raw_text or "")):
        parsed = _parse_gewerk_date(m.group(1))
        if parsed is not None:
            return parsed
    return None


def _gewerk_midnight(day_val: date) -> datetime:
    return datetime.combine(day_val, time(0, 0), tzinfo=BERLIN)


def _parse_gewerk_datetime(date_txt: Any, hour_txt: Any, minute_txt: Any = None) -> datetime | None:
    day_val = _parse_gewerk_date(date_txt)
    if day_val is None:
        return None
    try:
        hour_val = int(str(hour_txt or "").strip())
        minute_val = 0 if minute_txt is None or str(minute_txt).strip() == "" else int(str(minute_txt).strip())
    except ValueError:
        return None
    if not (0 <= hour_val <= 23 and 0 <= minute_val <= 59):
        return None
    return datetime(day_val.year, day_val.month, day_val.day, hour_val, minute_val, tzinfo=BERLIN)


def _gewerk_event_payload(
    *,
    timestamp: datetime,
    text: str,
    item_key_text: str,
    has_time: bool,
) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "text": text,
        "label": _short_gewerk_label(text),
        "item_key": _canon_zus_item_key(_strip_gewerk_prefix(item_key_text)),
        "has_time": bool(has_time),
        "date_only": not bool(has_time),
    }


def _parse_gewerke_entries(raw_text: Any, *, fallback_date: Any = None) -> list[dict[str, Any]]:
    txt = str(raw_text or "")
    if not txt.strip():
        return []

    out: list[dict[str, Any]] = []
    prefix = r"\s*(?:(?:[-*]|\u2022|\u00e2\u20ac\u00a2|\u00c3\u00a2\u00e2\u201a\u00ac\u00c2\u00a2)\s*)?"
    rx_with_time = re.compile(
        rf"^{prefix}(\d{{1,2}}\.\d{{1,2}}\.\d{{2,4}})\s*,\s*(\d{{1,2}})(?::(\d{{2}}))?\s*(?:uhr)?\s*(?:(?::|,|--?>)\s*)?(.+?)\s*$",
        flags=re.I,
    )
    rx_date_only = re.compile(
        rf"^{prefix}(\d{{1,2}}\.\d{{1,2}}\.\d{{2,4}})\s*(?:(?::|,|--?>)\s*)?(.+?)\s*$",
        flags=re.I,
    )
    fallback_day = _first_gewerk_date(txt) or _coerce_gewerk_date(fallback_date)

    for raw_line in txt.splitlines():
        line = str(raw_line or "").strip()
        if not line:
            continue

        m = rx_with_time.match(line)
        if m:
            detail_txt = _clean_gewerk_detail(m.group(4))
            event_dt = _parse_gewerk_datetime(m.group(1), m.group(2), m.group(3))
            if event_dt is None or not detail_txt:
                continue
            out.append(
                _gewerk_event_payload(
                    timestamp=event_dt,
                    text=detail_txt,
                    item_key_text=line,
                    has_time=True,
                )
            )
            continue

        m = rx_date_only.match(line)
        if m:
            day_val = _parse_gewerk_date(m.group(1))
            detail_txt = _clean_gewerk_detail(m.group(2))
            if day_val is None or not detail_txt:
                continue
            out.append(
                _gewerk_event_payload(
                    timestamp=_gewerk_midnight(day_val),
                    text=detail_txt,
                    item_key_text=line,
                    has_time=False,
                )
            )
            continue

        detail_txt = _clean_gewerk_detail(_strip_gewerk_prefix(line))
        if fallback_day is None or not detail_txt:
            continue
        out.append(
            _gewerk_event_payload(
                timestamp=_gewerk_midnight(fallback_day),
                text=detail_txt,
                item_key_text=line,
                has_time=False,
            )
        )
    return out


def _slot_start_for_timestamp(event_dt: datetime | None) -> datetime | None:
    ts = as_berlin(event_dt)
    if ts is None:
        return None
    for slot in _build_slots_for_day(_shift_day(ts)):
        if slot["start"] <= ts < slot["end"]:
            return slot["start"]
    return None


def _collect_gewerke_slot_events(
    df_open: pd.DataFrame | None,
    *,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
) -> list[dict[str, Any]]:
    if df_open is None or df_open.empty or "Gewerke" not in df_open.columns:
        return []

    start_dt = as_berlin(window_start)
    end_dt = as_berlin(window_end)
    out: list[dict[str, Any]] = []

    for _, rr in df_open.iterrows():
        vehicle = _display_vehicle_code(rr.get("Fahrzeug"))
        vehicle_key = _vehicle_compare_key(vehicle)
        if not vehicle_key:
            continue
        fallback_date = None
        for fallback_col in ("Anfang", "Fertig", "ecm3_fertig", "initial_fertig"):
            fallback_candidate = rr.get(fallback_col)
            if _coerce_gewerk_date(fallback_candidate) is not None:
                fallback_date = fallback_candidate
                break
        for event in _parse_gewerke_entries(rr.get("Gewerke"), fallback_date=fallback_date):
            event_ts = as_berlin(event.get("timestamp"))
            has_time = bool(event.get("has_time", True))
            if event_ts is None:
                continue
            if has_time:
                slot_start = _slot_start_for_timestamp(event.get("timestamp"))
                if slot_start is None:
                    continue
                event_end = _slot_end_for_start(slot_start)
            else:
                slot_start = event_ts
                event_end = event_ts + timedelta(days=1)
            if start_dt is not None and slot_start < start_dt:
                continue
            if end_dt is not None and slot_start >= end_dt:
                continue
            source_id = int(rr.get("id") or 0) if str(rr.get("id") or "").strip() else 0
            out.append(
                {
                    "fahrzeug": vehicle,
                    "vehicle_key": vehicle_key,
                    "start": slot_start,
                    "display_start": event_ts,
                    "end": event_end,
                    "label": str(event.get("label") or "").strip(),
                    "overview": str(event.get("text") or "").strip(),
                    "has_time": has_time,
                    "date_only": not has_time,
                    "source_rows": [{"id": source_id, "item_key": str(event.get("item_key") or "").strip()}],
                }
            )

    return sorted(
        out,
        key=lambda item: (
            as_berlin(item.get("display_start")) or as_berlin(item.get("start")) or datetime.min.replace(tzinfo=BERLIN),
            str(item.get("fahrzeug") or "").casefold(),
        ),
    )


def _clean_problem_note(note_text: Any) -> str:
    txt = _norm(note_text)
    if not txt:
        return ""
    if txt.casefold() in {"nan", "nat", "none", "null"}:
        return ""
    out: list[str] = []
    for raw in txt.splitlines():
        line = str(raw or "").strip()
        if not line:
            continue
        m = re.match(r"^\[(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})\]\s*(.*)$", line)
        payload = m.group(3).strip() if m else line
        if payload.casefold() in {"none", "nan", "nat", "null", "-"}:
            continue
        out.append(line)
    return "\n".join(out).strip()


def _vehicle_compare_key(vraw: Any) -> str:
    raw = str(vraw or "").strip()
    if not raw:
        return ""
    return (_norm_vehicle(raw) or raw).casefold()


def _is_urd_like(row: pd.Series, area_code: str | None = None) -> bool:
    frist = str(row.get("Friststufe") or "").casefold()
    ap = str(row.get("Arbeitsplatz") or "").strip().casefold()
    ap_pdf = str(row.get("ap_pdf") or "").strip().casefold()
    area_norm = str(area_code or "").strip().upper()
    return (
        area_norm == "URD"
        or ("urd" in frist)
        or ap in {"urd", "omb-neustrelitz"}
        or ap_pdf in {"urd", "omb-neustrelitz"}
    )


def _is_urd_open_row(row: pd.Series) -> bool:
    fr = str(row.get("Friststufe") or "").strip()
    ap = str(row.get("Arbeitsplatz") or "").strip().casefold()
    ap_pdf = str(row.get("ap_pdf") or "").strip().casefold()
    return (
        bool(re.search(r"\bURD\b", fr, flags=re.I))
        or ap in {"urd", "omb-neustrelitz"}
        or ap_pdf in {"urd", "omb-neustrelitz"}
    )


def _parse_zusatz_items(zusatz_raw: Any) -> list[str]:
    if not zusatz_raw:
        return []
    items: list[str] = []
    current: list[str] = []
    for raw in str(zusatz_raw).splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("-"):
            if current:
                items.append("\n".join(current).strip())
            current = [line[1:].strip()]
        else:
            if not current:
                current = [line]
            else:
                current.append(line)
    if current:
        items.append("\n".join(current).strip())
    return [x for x in items if x]


def _canon_zus_item_key(item: Any) -> str:
    return re.sub(r"\s+", " ", str(item or "").strip()).casefold()


def _decode_check_string(raw: Any, length: int) -> list[bool]:
    if length <= 0:
        return []
    txt = str(raw or "").strip()
    if not txt:
        return [False] * length
    parts = [p.strip() for p in txt.split(",") if p.strip() != ""]
    bits = [p == "1" for p in parts]
    if len(bits) < length:
        bits.extend([False] * (length - len(bits)))
    return bits[:length]


def _encode_check_list(bits: list[bool]) -> str:
    return ",".join("1" if bool(x) else "0" for x in bits)


def _repair_common_mojibake_text(value: Any) -> str:
    out = str(value or "")
    for bad, good in {
        "\u00c3\u00a4": "ä",
        "\u00c3\u00b6": "ö",
        "\u00c3\u00bc": "ü",
        "\u00c3\u0084": "Ä",
        "\u00c3\u201e": "Ä",
        "\u00c3\u0096": "Ö",
        "\u00c3\u2013": "Ö",
        "\u00c3\u009c": "Ü",
        "\u00c3\u0152": "Ü",
        "\u00c3\u009f": "ß",
        "\u00c3\u0178": "ß",
    }.items():
        out = out.replace(bad, good)
    for _ in range(2):
        try:
            fixed = out.encode("latin-1").decode("utf-8")
        except UnicodeError:
            break
        if fixed == out:
            break
        out = fixed
    return out


def _frist_items_for_row(row: pd.Series) -> list[str]:
    fahrzeug = str(row.get("Fahrzeug") or "")
    frist = str(row.get("Friststufe") or "")
    if callable(_configured_work_package_titles_for_vehicle_and_frist):
        try:
            configured = _configured_work_package_titles_for_vehicle_and_frist(fahrzeug, frist)
            if isinstance(configured, list):
                return [str(x) for x in configured if str(x).strip()]
        except Exception:
            pass
    if callable(_fr_items_for_vehicle_and_frist):
        try:
            out = _fr_items_for_vehicle_and_frist(fahrzeug, frist, FRIST_CHECK_ITEMS)
            if isinstance(out, list):
                return [str(x) for x in out]
        except Exception:
            pass
    return list(FRIST_CHECK_ITEMS)


def _fold_match_text(value: Any) -> str:
    txt = _repair_common_mojibake_text(value).casefold()
    return txt.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")


def _frist_has_non_hu_component(frist_value: Any) -> bool:
    txt = _fold_match_text(frist_value)
    if not txt:
        return False
    for raw_part in re.split(r"[\s/,+;|()_-]+", txt):
        part = re.sub(r"[^a-z0-9]", "", raw_part)
        if not part:
            continue
        if part == "hu":
            continue
        if part.startswith("verl"):
            continue
        if part.startswith("hu") and "verl" in part:
            continue
        return True
    return False


def _is_frist_check_applicable(row: pd.Series, area_code: str | None = None) -> bool:
    frist = _fold_match_text(row.get("Friststufe") or "")
    ap = str(row.get("Arbeitsplatz") or "").strip().casefold()
    ap_pdf = str(row.get("ap_pdf") or "").strip().casefold()
    if _is_urd_like(row, area_code=area_code):
        return False
    configured_items = _frist_items_for_row(row)
    if configured_items:
        return True
    if "hu" in frist and not _frist_has_non_hu_component(frist):
        return False
    if "stoerung" in frist or "störung" in frist:
        return False
    if "korrektiv" in frist or frist == "k":
        return False
    if ap == "rws" or ap_pdf == "rws":
        return False
    return False


def _requires_overdue_reason_for_frist(frist_value: Any) -> bool:
    frist = re.sub(r"\s+", " ", _fold_match_text(frist_value)).strip()
    if not frist or not re.search(r"[a-z0-9]", frist):
        return False
    if "urd" in frist:
        return False
    if frist == "k" or "korrektiv" in frist:
        return False
    if "stoerung" in frist:
        return False
    return True


def _calc_zus_progress(row: pd.Series) -> tuple[int, int, list[str], list[bool]]:
    items = _parse_zusatz_items(row.get("Zusatzarbeiten"))
    total = len(items)
    bits = _decode_check_string(row.get("zusatz_done"), total)
    done = sum(1 for x in bits if x)
    return done, total, items, bits


def _calc_frist_progress(row: pd.Series, area_code: str | None) -> tuple[int, int, list[str], list[bool], bool]:
    applicable = _is_frist_check_applicable(row, area_code=area_code)
    items = _frist_items_for_row(row)
    total = len(items) if applicable else 0
    bits = _decode_check_string(row.get("frist_done"), total)
    done = sum(1 for x in bits if x)
    return done, total, items, bits, applicable


def _row_allows_area(row: pd.Series, area_code: str) -> bool:
    area_norm = str(area_code or "").strip().upper()
    ap_pdf = str(row.get("ap_pdf") or "").strip().casefold()
    if ap_pdf == "rws":
        return False
    is_urd_task = _is_urd_like(row)
    if area_norm == "URD":
        return is_urd_task
    return not is_urd_task


def _normalize_workshop_area(area_code: Any) -> str:
    return str(area_code or "").strip().upper()


def _zus_added_only(old_zus: Any, new_zus: Any) -> str:
    old_items = _parse_zusatz_items(old_zus)
    new_items = _parse_zusatz_items(new_zus)
    old_norm = {re.sub(r"\s+", " ", str(x).strip()).casefold() for x in old_items if str(x).strip()}
    out: list[str] = []
    seen: set[str] = set()
    for item in new_items:
        raw = str(item or "").strip()
        if not raw:
            continue
        norm = re.sub(r"\s+", " ", raw).casefold()
        if norm in old_norm or norm in seen:
            continue
        seen.add(norm)
        out.append(raw)
    return "\n".join(out)
