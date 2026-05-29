
from __future__ import annotations

from datetime import date, datetime, timedelta
import io
import re
from typing import Any

import pandas as pd


def configure(**deps) -> None:
    globals().update(deps)


def _load_fzg_zusatz_raw(blob: bytes) -> pd.DataFrame:
    bio = io.BytesIO(blob)
    try:
        # TODO: Move Excel parsing to a worker if large uploads start blocking the UI.
        return pd.read_excel(bio, sheet_name="Fzg Zusatzarbeiten", header=None, engine="openpyxl")
    except Exception:
        bio.seek(0)
        return pd.read_excel(bio, sheet_name=0, header=None, engine="openpyxl")


def _norm_sheet_header(value: Any) -> str:
    txt = str(value or "")
    txt = txt.replace("\r", " ").replace("\n", " ")
    txt = re.sub(r"\s+", " ", txt).strip().casefold()
    return txt


def _find_fzg_zusatz_header_row(raw: pd.DataFrame) -> int:
    for i in range(0, min(len(raw), 30)):
        a = str(raw.iat[i, 0]) if raw.shape[1] > 0 and not pd.isna(raw.iat[i, 0]) else ""
        b = str(raw.iat[i, 1]) if raw.shape[1] > 1 and not pd.isna(raw.iat[i, 1]) else ""
        if "fzg" in a.lower() and "zusatz" in b.lower():
            return i
    return 2


def _find_header_col_idx(header_cells: list[str], *needles: str) -> int | None:
    tokens = [str(x or "").strip().casefold() for x in needles if str(x or "").strip()]
    if not tokens:
        return None
    for idx, header in enumerate(header_cells):
        if all(token in header for token in tokens):
            return idx
    return None


def _build_fzg_zusatz_layout(raw: pd.DataFrame) -> dict[str, Any]:
    header_row = _find_fzg_zusatz_header_row(raw)
    header_cells = [_norm_sheet_header(v) for v in raw.iloc[header_row].tolist()]

    gewerke_idx = _find_header_col_idx(header_cells, "gewerke")
    legacy_offset = 1 if gewerke_idx is not None else 0

    layout = {
        "header_row": header_row,
        "data_start": header_row + 1,
        "vehicle": _find_header_col_idx(header_cells, "fzg"),
        "zus": _find_header_col_idx(header_cells, "zusatz"),
        "gewerke": gewerke_idx,
        "typ": _find_header_col_idx(header_cells, "p / k / urd"),
        "frist": _find_header_col_idx(header_cells, "friststufe"),
        "ecm3_start_date": _find_header_col_idx(header_cells, "ecm iii", "start", "fahrzeug in we"),
        "ecm3_start_time": _find_header_col_idx(header_cells, "ecm iii", "start zeit"),
        "ecm3_end_date": _find_header_col_idx(header_cells, "ecm iii", "ende", "fahrzeug in we"),
        "ecm3_end_time": _find_header_col_idx(header_cells, "ecm iii", "ende zeit"),
        "ecm4_start_date": _find_header_col_idx(header_cells, "ecm iv", "start", "datum"),
        "ecm4_start_time": _find_header_col_idx(header_cells, "ecm iv", "start", "zeit"),
        "ecm4_end_date": _find_header_col_idx(header_cells, "ecm iv", "ende", "datum"),
        "ecm4_end_time": _find_header_col_idx(header_cells, "ecm iv", "ende", "zeit"),
        "ap": _find_header_col_idx(header_cells, "gleisbelegung"),
    }

    defaults = {
        "vehicle": 0,
        "zus": 1,
        "gewerke": 2 if gewerke_idx is not None else None,
        "typ": 2 + legacy_offset,
        "frist": 3 + legacy_offset,
        "ecm3_start_date": 4 + legacy_offset,
        "ecm3_start_time": 5 + legacy_offset,
        "ecm3_end_date": 6 + legacy_offset,
        "ecm3_end_time": 7 + legacy_offset,
        "ecm4_start_date": 10 + legacy_offset,
        "ecm4_start_time": 11 + legacy_offset,
        "ecm4_end_date": 12 + legacy_offset,
        "ecm4_end_time": 13 + legacy_offset,
        "ap": 14 + legacy_offset,
    }
    for key, default_idx in defaults.items():
        if layout.get(key) is None and default_idx is not None:
            layout[key] = default_idx
    return layout


def _sheet_row_value(row: pd.Series, idx: int | None) -> Any:
    if idx is None or idx < 0 or idx >= len(row):
        return None
    return row.iloc[idx]

def _merge_gewerke_into_zusatzarbeiten(zus_raw: Any, gewerke_raw: Any) -> str:
    zus_items = _parse_zusatz_items(zus_raw)
    gewerke_items = _parse_zusatz_items(gewerke_raw)
    merged: list[str] = []
    seen: set[str] = set()

    for item in zus_items + gewerke_items:
        norm = re.sub(r"\s+", " ", str(item or "").strip()).casefold()
        if not norm or norm in seen:
            continue
        seen.add(norm)
        merged.append(str(item).strip())

    if not merged:
        return ""
    return "\n".join(f"- {item}" for item in merged)

def parse_excel_to_df_bytes(blob: bytes) -> pd.DataFrame:
    raw = _load_fzg_zusatz_raw(blob)
    if raw is None or raw.empty:
        return pd.DataFrame(
            columns=["Fahrzeug", "Zusatzarbeiten", "Gewerke", "Friststufe", "Anfang", "Fertig", "Arbeitsplatz", "ecm3_fertig"]
        )

    layout = _build_fzg_zusatz_layout(raw)
    start_idx = int(layout.get("data_start") or 0)

    def norm_frist(v: Any) -> str:
        if v is None or (isinstance(v, float) and pd.isna(v)) or pd.isna(v):
            return ""
        if isinstance(v, int) or (isinstance(v, float) and float(v).is_integer()):
            return str(int(v))
        return str(v).strip()

    def time_to_hm(v: Any) -> tuple[int, int] | None:
        if v is None or (isinstance(v, float) and pd.isna(v)) or pd.isna(v):
            return None
        if hasattr(v, "hour") and hasattr(v, "minute") and not isinstance(v, (str, int, float)):
            return int(v.hour), int(v.minute)
        if isinstance(v, (int, float)) and 0 <= float(v) < 1.0:
            secs = int(round(float(v) * 86400))
            return secs // 3600, (secs % 3600) // 60
        s = str(v).strip()
        m = re.search(r"(\d{1,2})[:.](\d{2})", s)
        if m:
            return int(m.group(1)), int(m.group(2))
        return None

    def combine_dt(dv: Any, tv: Any) -> datetime | None:
        if dv is None or (isinstance(dv, float) and pd.isna(dv)) or pd.isna(dv):
            return None
        d = pd.to_datetime(dv, errors="coerce", dayfirst=True)
        if pd.isna(d):
            return None
        hm = time_to_hm(tv)
        if hm is None:
            return datetime(int(d.year), int(d.month), int(d.day), 0, 0)
        h, m = hm
        return datetime(int(d.year), int(d.month), int(d.day), int(h), int(m))

    def single_excel_dt(v: Any) -> datetime | None:
        if v is None or (isinstance(v, float) and pd.isna(v)) or pd.isna(v):
            return None
        if isinstance(v, pd.Timestamp):
            return v.to_pydatetime()
        if isinstance(v, datetime):
            return v
        if isinstance(v, date):
            return datetime(int(v.year), int(v.month), int(v.day), 0, 0)
        if isinstance(v, (int, float)):
            if 0 <= float(v) < 1.0:
                return None
            try:
                ts = pd.Timestamp("1899-12-30") + pd.to_timedelta(float(v), unit="D")
                return ts.to_pydatetime()
            except Exception:
                return None
        ts = pd.to_datetime(v, errors="coerce", dayfirst=True)
        if pd.isna(ts):
            return None
        if isinstance(ts, pd.Timestamp):
            return ts.to_pydatetime()
        return None

    rows: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for i in range(start_idx, len(raw)):
        r = raw.iloc[i]
        veh_raw = _norm(_sheet_row_value(r, layout.get("vehicle")))
        veh = _norm_vehicle(veh_raw) or veh_raw
        zus = _norm(_sheet_row_value(r, layout.get("zus")))
        gewerke = _norm(_sheet_row_value(r, layout.get("gewerke")))
        typ = _norm(_sheet_row_value(r, layout.get("typ")))
        frist = norm_frist(_sheet_row_value(r, layout.get("frist")))
        ecm3_end = combine_dt(
            _sheet_row_value(r, layout.get("ecm3_end_date")),
            _sheet_row_value(r, layout.get("ecm3_end_time")),
        )
        start_d = _sheet_row_value(r, layout.get("ecm4_start_date"))
        start_t = _sheet_row_value(r, layout.get("ecm4_start_time"))
        end_d = _sheet_row_value(r, layout.get("ecm4_end_date"))
        end_t = _sheet_row_value(r, layout.get("ecm4_end_time"))
        ap = _clean_ap(_sheet_row_value(r, layout.get("ap")))

        if not any([veh, zus, gewerke, typ, frist, ap]) and pd.isna(pd.to_datetime(start_d, errors="coerce")) and pd.isna(
            pd.to_datetime(end_d, errors="coerce")
        ):
            continue

        if veh:
            current = {
                "Fahrzeug": veh,
                "Zusatzarbeiten": zus,
                "Gewerke": gewerke,
                "Friststufe": frist,
                "_typ": typ,
                "_start": combine_dt(start_d, start_t),
                "_end": combine_dt(end_d, end_t),
                "_ecm3_end": ecm3_end,
                "Arbeitsplatz": ap,
            }
            rows.append(current)
            continue

        if current is not None:
            if zus:
                current["Zusatzarbeiten"] = _append_text(str(current.get("Zusatzarbeiten") or ""), zus)
            if gewerke:
                current["Gewerke"] = _append_text(str(current.get("Gewerke") or ""), gewerke)
            if not current.get("Friststufe") and frist:
                current["Friststufe"] = frist
            if not current.get("_typ") and typ:
                current["_typ"] = typ
            if not current.get("Arbeitsplatz") and ap:
                current["Arbeitsplatz"] = ap
            if current.get("_start") is None:
                current["_start"] = combine_dt(start_d, start_t)
            if current.get("_end") is None:
                current["_end"] = combine_dt(end_d, end_t)
            if current.get("_ecm3_end") is None:
                current["_ecm3_end"] = ecm3_end

    out = []
    for rec in rows:
        veh = str(rec.get("Fahrzeug") or "").strip()
        if not veh:
            continue
        fr = _norm(rec.get("Friststufe") or "")
        typ = _norm(rec.get("_typ") or "").casefold()
        ap = _clean_ap(rec.get("Arbeitsplatz") or "")

        is_typ_k = bool(re.fullmatch(r"k(?:orrektiv)?", typ)) or ("korrektiv" in typ)
        is_typ_urd = "urd" in typ
        if is_typ_k:
            fr = "Korrektiv"
        if is_typ_urd:
            fr = "URD"
            ap = "URD"

        zus_combined = _merge_gewerke_into_zusatzarbeiten(rec.get("Zusatzarbeiten") or "", rec.get("Gewerke") or "")
        st_dt = rec.get("_start")
        en_dt = rec.get("_end")
        ecm3_dt = rec.get("_ecm3_end")
        anfang = st_dt.isoformat(timespec="minutes") if isinstance(st_dt, datetime) else None
        fertig = en_dt.isoformat(timespec="minutes") if isinstance(en_dt, datetime) else None
        ecm3_fertig = ecm3_dt.isoformat(timespec="minutes") if isinstance(ecm3_dt, datetime) else None

        if veh and (anfang or fertig or ecm3_fertig or is_typ_k or is_typ_urd):
            out.append(
                {
                    "Fahrzeug": veh,
                    "Zusatzarbeiten": zus_combined,
                    "Gewerke": _norm(rec.get("Gewerke") or ""),
                    "Friststufe": fr,
                    "Anfang": anfang[:16] if anfang else None,
                    "Fertig": fertig[:16] if fertig else None,
                    "Arbeitsplatz": ap,
                    "ecm3_fertig": ecm3_fertig[:16] if ecm3_fertig else None,
                }
            )

    df = pd.DataFrame(
        out,
        columns=["Fahrzeug", "Zusatzarbeiten", "Gewerke", "Friststufe", "Anfang", "Fertig", "Arbeitsplatz", "ecm3_fertig"],
    )
    if not df.empty:
        df = df[~df["Friststufe"].astype(str).str.contains(r"\bRWS\b", case=False, regex=True, na=False)].copy()
        df = df.drop_duplicates(subset=["Fahrzeug", "Friststufe", "Anfang", "Fertig"]).reset_index(drop=True)
    return df


def parse_rws_week_plan_from_excel(blob: bytes) -> pd.DataFrame:
    raw = _load_fzg_zusatz_raw(blob)
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["fahrzeug", "start", "end"])

    layout = _build_fzg_zusatz_layout(raw)
    start_idx = int(layout.get("data_start") or 0)

    def _time_to_hm(v: Any) -> tuple[int, int] | None:
        if v is None or (isinstance(v, float) and pd.isna(v)) or pd.isna(v):
            return None
        if hasattr(v, "hour") and hasattr(v, "minute") and not isinstance(v, (str, int, float)):
            return int(v.hour), int(v.minute)
        if isinstance(v, (int, float)) and 0 <= float(v) < 1.0:
            secs = int(round(float(v) * 86400))
            return secs // 3600, (secs % 3600) // 60
        s = str(v).strip()
        m = re.search(r"(\d{1,2})[:.](\d{2})", s)
        if m:
            return int(m.group(1)), int(m.group(2))
        return None

    def _combine_dt(dv: Any, tv: Any) -> datetime | None:
        if dv is None or (isinstance(dv, float) and pd.isna(dv)) or pd.isna(dv):
            return None
        d = pd.to_datetime(dv, errors="coerce", dayfirst=True)
        if pd.isna(d):
            return None
        hm = _time_to_hm(tv)
        if hm is None:
            return datetime(int(d.year), int(d.month), int(d.day), 0, 0)
        h, m = hm
        return datetime(int(d.year), int(d.month), int(d.day), int(h), int(m))

    def _pick_dt(row: pd.Series, date_idx_primary: int, time_idx_primary: int, date_idx_fallback: int, time_idx_fallback: int) -> datetime | None:
        dt = _combine_dt(row.iloc[date_idx_primary], row.iloc[time_idx_primary])
        if dt is not None:
            return dt
        return _combine_dt(row.iloc[date_idx_fallback], row.iloc[time_idx_fallback])

    rows: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for i in range(start_idx, len(raw)):
        r = raw.iloc[i]
        veh_raw = _norm(_sheet_row_value(r, layout.get("vehicle")))
        veh = _norm_vehicle(veh_raw) or veh_raw
        frist = _clean_plan_text(_sheet_row_value(r, layout.get("frist")))
        start_dt = _pick_dt(
            r,
            int(layout.get("ecm3_start_date") or 0),
            int(layout.get("ecm3_start_time") or 0),
            int(layout.get("ecm4_start_date") or 0),
            int(layout.get("ecm4_start_time") or 0),
        )
        end_dt = _pick_dt(
            r,
            int(layout.get("ecm3_end_date") or 0),
            int(layout.get("ecm3_end_time") or 0),
            int(layout.get("ecm4_end_date") or 0),
            int(layout.get("ecm4_end_time") or 0),
        )
        is_rws = bool(re.search(r"\bRWS\b", frist, flags=re.I))

        if veh:
            current = None
            if not is_rws:
                continue
            if start_dt is None and end_dt is None:
                continue
            if start_dt is None and end_dt is not None:
                start_dt = end_dt - timedelta(hours=4)
            if end_dt is None and start_dt is not None:
                end_dt = start_dt + timedelta(hours=4)
            if start_dt is None or end_dt is None:
                continue
            current = {"fahrzeug": veh, "start": start_dt, "end": end_dt}
            rows.append(current)
            continue

        if current is not None:
            if current.get("start") is None and start_dt is not None:
                current["start"] = start_dt
            if current.get("end") is None and end_dt is not None:
                current["end"] = end_dt

    out = pd.DataFrame(rows, columns=["fahrzeug", "start", "end"])
    if not out.empty:
        out = out.dropna(subset=["fahrzeug", "start", "end"]).copy()
        out = out.drop_duplicates(subset=["fahrzeug", "start", "end"]).reset_index(drop=True)
    return out
