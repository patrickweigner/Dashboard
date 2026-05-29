
from __future__ import annotations

from datetime import datetime
import re
from typing import Any

import pandas as pd


def configure(**deps) -> None:
    globals().update(deps)


def make_sig(fahrzeug: str, friststufe: str, anfang_iso: str | None, fertig_iso: str | None) -> str:
    a = str(anfang_iso or "").strip()[:16]
    f = str(fertig_iso or "").strip()[:16]
    return f"{str(fahrzeug or '').strip().lower()}|{str(friststufe or '').strip().lower()}|{a}|{f}"


def now_berlin() -> datetime:
    return datetime.now(BERLIN)

def _is_wash_zus_item(text: Any) -> bool:
    s = str(text or "").strip()
    if not s:
        return False
    s = s.replace("\u00c3\u00a4", "ä").replace("\u00c3\u00b6", "ö").replace("\u00c3\u00bc", "ü")
    if RX_WASH_TOKEN.search(s):
        return True
    norm = s.casefold()
    norm = norm.replace("ae", "a").replace("ä", "a")
    norm = re.sub(r"[^a-z0-9]+", "", norm)
    return "fahrzeugwasche" in norm


def as_berlin(dt: Any) -> datetime | None:
    if dt is None or pd.isna(dt):
        return None
    if isinstance(dt, pd.Timestamp):
        if dt.tzinfo is None:
            return dt.tz_localize(BERLIN).to_pydatetime()
        return dt.tz_convert(BERLIN).to_pydatetime()
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=BERLIN)
        return dt.astimezone(BERLIN)
    ts = pd.to_datetime(dt, errors="coerce")
    if pd.isna(ts):
        return None
    if isinstance(ts, pd.Timestamp):
        if ts.tzinfo is None:
            return ts.tz_localize(BERLIN).to_pydatetime()
        return ts.tz_convert(BERLIN).to_pydatetime()
    return None


def _to_datetime_mixed(value: Any, *, utc: bool = False) -> Any:
    try:
        return pd.to_datetime(value, errors="coerce", utc=utc, format="mixed")
    except TypeError:
        return pd.to_datetime(value, errors="coerce", utc=utc)


def _coerce_berlin_datetime_series(series: pd.Series, *, naive: bool = False) -> pd.Series:
    if series.empty:
        return pd.Series(dtype="datetime64[ns]", index=series.index, name=series.name)

    text = series.astype("string")
    tz_mask = text.str.contains(r"(?:Z|[+-]\d{2}:?\d{2})\s*$", na=False, regex=True)

    aware = _to_datetime_mixed(series.where(tz_mask), utc=True)
    aware = aware.dt.tz_convert(BERLIN)

    naive_src = series.where(~tz_mask)
    naive_parsed = _to_datetime_mixed(naive_src)

    if naive:
        aware_part = aware.dt.tz_localize(None)
        out = aware_part.combine_first(naive_parsed)
    else:
        naive_part = naive_parsed.dt.tz_localize(BERLIN, ambiguous="NaT", nonexistent="shift_forward")
        out = aware.combine_first(naive_part)

    return pd.Series(out, index=series.index, name=series.name)


def _clean_nullable_text(value: Any) -> str:
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


def _clean_nullable_db_text(value: Any) -> str | None:
    txt = _clean_nullable_text(value)
    return txt or None


def _planned_deadline_text(primary_value: Any, fallback_value: Any = None) -> str:
    primary_txt = _clean_nullable_text(primary_value)
    if primary_txt:
        return primary_txt
    return _clean_nullable_text(fallback_value)


def _planned_deadline_dt(primary_value: Any, fallback_value: Any = None) -> datetime | None:
    txt = _planned_deadline_text(primary_value, fallback_value)
    if not txt:
        return None
    return as_berlin(txt)


def fmt_dt(dt: Any) -> str:
    dtx = as_berlin(dt)
    if not dtx:
        return "-"
    return dtx.strftime("%d.%m.%Y %H:%M")


def fmt_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h} Std {m} Min {s} Sek"


def _norm(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, float) and pd.isna(x):
        return ""
    return str(x).strip()


def _norm_vehicle(vraw: str) -> str:
    s = _norm(vraw)
    m = RX_VEHICLE.search(s)
    if not m:
        return ""
    prefix = (m.group(1) or "").upper().strip()
    num = m.group(2)
    return (prefix + num).replace(" ", "") if prefix else num


def _clean_ap(ap: Any) -> str:
    s = _norm(ap).replace("\u00A0", " ").strip()
    if re.fullmatch(r"[-\u2013\u2014]+", s):
        return ""
    return s


def _append_text(old_text: str, new_text: str) -> str:
    left = (old_text or "").strip()
    right = (new_text or "").strip()
    if not right:
        return left
    if not left:
        return right
    sep = "\n" if not left.endswith("\n") else ""
    return left + sep + right


def _append_unique_inline_text(old_text: Any, new_text: Any, *, sep: str = " · ") -> str:
    left = str(old_text or "").strip()
    right = str(new_text or "").strip()
    if not right:
        return left
    if not left:
        return right
    old_parts = [str(x).strip() for x in left.split(sep) if str(x).strip()]
    seen = {part.casefold() for part in old_parts}
    if right.casefold() in seen:
        return left
    old_parts.append(right)
    return sep.join(old_parts)


def _append_unique_multiline_text(old_text: Any, new_text: Any) -> str:
    left = str(old_text or "").strip()
    right = str(new_text or "").strip()
    if not right:
        return left
    if not left:
        return right
    old_lines = [str(x).strip() for x in left.splitlines() if str(x).strip()]
    seen = {line.casefold() for line in old_lines}
    if right.casefold() in seen:
        return left
    old_lines.append(right)
    return "\n".join(old_lines)


def _display_area_name(area_code: Any) -> str:
    code = str(area_code or "").strip().upper()
    return AREA_DISPLAY_NAMES.get(code, code)
