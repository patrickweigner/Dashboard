from datetime import datetime, time, timedelta
import io
import re
from zoneinfo import ZoneInfo

import pandas as pd

BERLIN = ZoneInfo("Europe/Berlin")


def _norm_cell(x) -> str:
    if x is None or pd.isna(x):
        return ""
    return str(x).strip()


def _time_to_hhmm(x) -> str | None:
    if x is None or pd.isna(x):
        return None

    if isinstance(x, datetime):
        return x.strftime("%H:%M")
    if hasattr(x, "hour") and hasattr(x, "minute"):
        return f"{int(x.hour):02d}:{int(x.minute):02d}"

    if isinstance(x, (int, float)):
        secs = int(round(float(x) * 24 * 3600))
        h = (secs // 3600) % 24
        m = (secs % 3600) // 60
        return f"{h:02d}:{m:02d}"

    s = str(x).strip()
    m = re.match(r"^(\d{1,2})[:.](\d{2})$", s)
    if m:
        return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"
    return s if s else None


def _parse_hhmm_to_minutes(value) -> int | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    m = re.match(r"^(\d{1,2})[:.](\d{2})$", s)
    if not m:
        return None
    hh = int(m.group(1))
    mm = int(m.group(2))
    if hh < 0 or hh > 23 or mm < 0 or mm > 59:
        return None
    return hh * 60 + mm


def parse_ecm4_plan_from_excel(uploaded_file) -> pd.DataFrame:
    """
    Liest 'ECM 4 Planung' und liefert Long-DF (für ecm4_plan):
      slot_start (tz=Berlin), orig_date (date), zeit (HH:MM), hinweis (Gewerke),
      area (4A/4B/5A/5B/SERVICE/URD/ARA/RWS), fahrzeug
    """
    data = uploaded_file.getvalue() if hasattr(uploaded_file, "getvalue") else uploaded_file
    xls = pd.ExcelFile(io.BytesIO(data))

    if "ECM 4 Planung" not in xls.sheet_names:
        raise ValueError("Sheet 'ECM 4 Planung' nicht gefunden.")

    raw = pd.read_excel(io.BytesIO(data), sheet_name="ECM 4 Planung", header=None)

    header = [str(v).strip().upper() if pd.notna(v) else "" for v in raw.iloc[1].tolist()]

    def _hidx(*names):
        for n in names:
            n = (n or "").strip().upper()
            if n in header:
                return header.index(n)
        return None

    area_order = ["4A", "4B", "5A", "5B", "SERVICE", "URD", "ARA", "RWS"]

    col_datum = _hidx("DATUM", "DATE")
    col_time = _hidx("SLOT BEGINN", "SLOT-BEGINN", "SLOT", "BEGINN", "SCHICHT", "ZEIT")
    col_hint = _hidx("GEWERKE / WICHTIGE TERMINE", "GEWERKE", "WICHTIGE TERMINE")

    area_cols = {}
    for area in area_order:
        idx = _hidx(area)
        if idx is not None:
            area_cols[area] = idx

    if col_datum is None or col_time is None:
        col_datum = 0
        col_time = 1
    if col_hint is None:
        col_hint = 2

    if not area_cols:
        area_cols = {
            "4A": 4,
            "4B": 5,
            "5A": 6,
            "5B": 7,
            "SERVICE": 9,
            "URD": 10,
            "ARA": 11,
            "RWS": 12,
        }

    data_start = 2
    max_scan = min(len(raw), 20)
    for i in range(0, max_scan):
        d = pd.to_datetime(raw.iloc[i, col_datum], errors="coerce")
        t = _time_to_hhmm(raw.iloc[i, col_time])
        if pd.notna(d) and t:
            data_start = i
            break

    df = raw.iloc[data_start:].copy()

    out = pd.DataFrame()
    out["orig_date"] = pd.to_datetime(df.iloc[:, col_datum], errors="coerce").dt.date
    out["orig_date"] = out["orig_date"].ffill()
    out["zeit"] = df.iloc[:, col_time].apply(_time_to_hhmm)
    out["hinweis"] = df.iloc[:, col_hint].apply(lambda x: (_norm_cell(x) or None))

    for area, col_idx in area_cols.items():
        if col_idx < df.shape[1]:
            out[area] = df.iloc[:, col_idx].apply(lambda x: (_norm_cell(x) or None))
        else:
            out[area] = None

    def _row_empty(row):
        if pd.isna(row.get("orig_date")):
            return True
        mins = _parse_hhmm_to_minutes(row.get("zeit"))
        if mins is None:
            return True
        if row.get("hinweis"):
            return False
        return all((row.get(a) is None) or (str(row.get(a)).strip() == "") for a in area_cols.keys())

    out = out[~out.apply(_row_empty, axis=1)].reset_index(drop=True)

    slot_starts = []
    cur_date = None
    last_minutes = None
    roll_days = 0

    shift_cutoff_mins = 6 * 60

    for _, row in out.iterrows():
        d = row["orig_date"]
        t = row["zeit"]

        if d != cur_date:
            cur_date = d
            last_minutes = None
            roll_days = 0

        mins = _parse_hhmm_to_minutes(t)
        if mins is None:
            slot_starts.append(pd.NaT)
            continue
        hh = mins // 60
        mm = mins % 60

        if last_minutes is not None and mins < last_minutes:
            roll_days += 1

        if mins < shift_cutoff_mins and roll_days == 0:
            roll_days = 1

        last_minutes = mins

        dt = datetime.combine(d, time(hh, mm)) + timedelta(days=roll_days)
        dt = dt.replace(tzinfo=BERLIN)
        slot_starts.append(dt)

    out["slot_start"] = slot_starts

    rows = []
    for _, row in out.iterrows():
        for area in area_cols.keys():
            rows.append(
                {
                    "slot_start": row["slot_start"],
                    "orig_date": row["orig_date"],
                    "zeit": row["zeit"],
                    "hinweis": row.get("hinweis"),
                    "area": area,
                    "fahrzeug": row.get(area),
                }
            )

    plan = pd.DataFrame(rows)
    plan = plan[plan["slot_start"].notna()].copy()
    return plan
