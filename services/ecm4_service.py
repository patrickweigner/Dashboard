
from __future__ import annotations

from datetime import date, datetime, time
import threading
import pandas as pd


_CACHE_LOCK = threading.Lock()
_RWS_CACHE: tuple[int, pd.DataFrame] | None = None
_ECM4_SOURCE_CACHE: tuple[int, pd.DataFrame, pd.DataFrame] | None = None
_ECM4_RESULT_CACHE: dict[tuple[int, str], pd.DataFrame] = {}


def configure(**deps) -> None:
    globals().update(deps)


def replace_ecm4_plan_in_db(plan_df: pd.DataFrame, source_name: str | None = None) -> None:
    if plan_df is None or plan_df.empty:
        return

    conn = get_conn()
    cur = conn.cursor()
    imported_at = now_berlin().isoformat(timespec="seconds")
    src = (str(source_name).strip() if source_name else "") or None
    _ensure_ecm4_plan_history_schema(conn)

    rows: list[tuple[str, str | None, str | None, str | None, str, str | None, str, str | None]] = []
    for _, rr in plan_df.iterrows():
        slot = as_berlin(rr.get("slot_start"))
        if slot is None:
            continue
        orig_date_txt = None
        try:
            raw = rr.get("orig_date")
            if raw is not None and pd.notna(raw):
                orig_date_txt = str(pd.to_datetime(raw, errors="coerce").date())
        except Exception:
            orig_date_txt = None
        rows.append(
            (
                slot.isoformat(timespec="seconds"),
                orig_date_txt,
                str(rr.get("zeit") or "").strip() or None,
                str(rr.get("hinweis") or "").strip() or None,
                str(rr.get("area") or "").strip().upper(),
                str(rr.get("fahrzeug") or "").strip() or None,
                imported_at,
                src,
            )
        )

    try:
        with _DB_WRITE_LOCK:
            cur.execute("BEGIN;")

            cur.execute(
                """
                SELECT DISTINCT imported_at
                FROM ecm4_plan
                WHERE imported_at IS NOT NULL AND imported_at <> '';
                """
            )
            imported_vals = [r[0] for r in (cur.fetchall() or []) if r and r[0]]
            if len(imported_vals) == 1:
                old_imp = imported_vals[0]
                cur.execute("SELECT 1 FROM ecm4_plan_hist WHERE imported_at=? LIMIT 1;", (old_imp,))
                if cur.fetchone() is None:
                    cur.execute(
                        """
                        INSERT INTO ecm4_plan_hist (
                            slot_start, orig_date, zeit, hinweis, area, fahrzeug, imported_at, source_name
                        )
                        SELECT
                            slot_start, orig_date, zeit, hinweis, area, fahrzeug, imported_at, source_name
                        FROM ecm4_plan;
                        """
                    )

            cur.execute("DELETE FROM ecm4_plan;")
            if rows:
                cur.executemany(
                    """
                    INSERT INTO ecm4_plan (
                        slot_start, orig_date, zeit, hinweis, area, fahrzeug, imported_at, source_name
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    rows,
                )
            conn.commit()
            bump_data_version()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        cur.close()


def replace_ecm4_plan(plan_df: pd.DataFrame, *, source_name: str | None = None) -> None:
    replace_ecm4_plan_in_db(plan_df, source_name=source_name)


def replace_rws_week_plan_in_db(plan_df: pd.DataFrame | None, source_name: str | None = None) -> None:
    conn = get_conn()
    cur = conn.cursor()
    imported_at = now_berlin().isoformat(timespec="seconds")
    src = (str(source_name).strip() if source_name else "") or None
    rows: list[tuple[str, str, str, str, str | None]] = []

    if isinstance(plan_df, pd.DataFrame) and not plan_df.empty:
        for _, rr in plan_df.iterrows():
            fahrzeug = _display_vehicle_code(rr.get("fahrzeug"))
            start_dt = as_berlin(rr.get("start"))
            end_dt = as_berlin(rr.get("end"))
            if not fahrzeug or start_dt is None or end_dt is None:
                continue
            rows.append(
                (
                    fahrzeug,
                    start_dt.isoformat(timespec="minutes"),
                    end_dt.isoformat(timespec="minutes"),
                    imported_at,
                    src,
                )
            )

    try:
        with _DB_WRITE_LOCK:
            cur.execute("BEGIN;")
            cur.execute("DELETE FROM rws_week_plan;")
            if rows:
                cur.executemany(
                    """
                    INSERT INTO rws_week_plan (fahrzeug, start_dt, end_dt, imported_at, source_name)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    rows,
                )
            conn.commit()
        bump_data_version()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        cur.close()


def load_rws_week_plan_df() -> pd.DataFrame:
    global _RWS_CACHE
    ver = _current_data_version()
    with _CACHE_LOCK:
        cached = _RWS_CACHE
        if cached and cached[0] == ver:
            return cached[1].copy(deep=True)

    rows = db_exec(
        """
        SELECT fahrzeug, start_dt, end_dt, imported_at, source_name
        FROM rws_week_plan
        ORDER BY start_dt ASC, fahrzeug ASC;
        """,
        fetch=True,
    ) or []
    cols = ["fahrzeug", "start", "end", "imported_at", "source_name"]
    df = pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)
    for col in ("start", "end", "imported_at"):
        df[col] = _coerce_berlin_datetime_series(df[col])
    if df.empty:
        with _CACHE_LOCK:
            _RWS_CACHE = (ver, df.copy(deep=True))
        return df
    out = df.sort_values(["start", "end", "fahrzeug"], ascending=[True, True, True], na_position="last").reset_index(drop=True)
    with _CACHE_LOCK:
        if _current_data_version() == ver:
            _RWS_CACHE = (ver, out.copy(deep=True))
    return out


def _ref_cache_key(ref_dt: datetime | date | None) -> str:
    if ref_dt is None:
        ref_local = now_berlin().replace(second=0, microsecond=0)
        return f"now:{ref_local.isoformat(timespec='minutes')}"
    if isinstance(ref_dt, date) and not isinstance(ref_dt, datetime):
        return f"day:{ref_dt.isoformat()}"
    ref_local = as_berlin(ref_dt)
    if ref_local is None:
        return "none"
    return f"dt:{ref_local.replace(second=0, microsecond=0).isoformat(timespec='minutes')}"


def _load_ecm4_source_frames() -> tuple[int, pd.DataFrame, pd.DataFrame]:
    global _ECM4_SOURCE_CACHE
    ver = _current_data_version()
    with _CACHE_LOCK:
        cached = _ECM4_SOURCE_CACHE
        if cached and cached[0] == ver:
            return cached

    try:
        _ensure_ecm4_plan_history_schema()
    except Exception:
        pass

    select_cols = ["slot_start", "orig_date", "zeit", "hinweis", "area", "fahrzeug", "imported_at", "source_name"]
    sql_cols = ", ".join(select_cols)

    rows_active = db_exec(
        f"""
        SELECT {sql_cols}
        FROM ecm4_plan
        ORDER BY slot_start ASC, area ASC;
        """,
        fetch=True,
    ) or []
    try:
        rows_hist = db_exec(
            f"""
            SELECT {sql_cols}
            FROM ecm4_plan_hist;
            """,
            fetch=True,
        ) or []
    except Exception:
        rows_hist = []

    if not rows_active and not rows_hist:
        df = pd.DataFrame(columns=select_cols + ["_slot_utc"])
        spans = pd.DataFrame(columns=["imported_at", "plan_min", "plan_max", "_imported_sort"])
    else:
        df = pd.DataFrame([dict(r) for r in rows_active] + [dict(r) for r in rows_hist])
        df["_slot_utc"] = pd.to_datetime(df["slot_start"], utc=True, errors="coerce")
        df = df[df["_slot_utc"].notna()].copy()
        if df.empty:
            df = pd.DataFrame(columns=select_cols + ["_slot_utc"])
            spans = pd.DataFrame(columns=["imported_at", "plan_min", "plan_max", "_imported_sort"])
        else:
            df["slot_start"] = _coerce_berlin_datetime_series(df["slot_start"])
            df["orig_date"] = _coerce_berlin_datetime_series(df["orig_date"], naive=True).dt.date
            spans = (
                df.groupby("imported_at", dropna=False)["_slot_utc"]
                .agg(plan_min="min", plan_max="max")
                .reset_index()
            )
            spans = spans[spans["imported_at"].notna() & (spans["imported_at"].astype(str).str.strip() != "")].copy()
            spans["_imported_sort"] = _coerce_berlin_datetime_series(spans["imported_at"])

    result = (ver, df, spans)
    with _CACHE_LOCK:
        if _current_data_version() == ver:
            _ECM4_SOURCE_CACHE = result
            stale_keys = [key for key in _ECM4_RESULT_CACHE if key[0] != ver]
            for key in stale_keys:
                _ECM4_RESULT_CACHE.pop(key, None)
    return result


def load_ecm4_plan_df(ref_dt: datetime | date | None = None) -> pd.DataFrame:
    """
    Laedt den ECM4-Plan für einen Referenzzeitpunkt (Standard: jetzt in Berlin).
    Beruecksichtigt aktive und historische Import-Versionen.
    """
    if ref_dt is None:
        ref_dt = now_berlin()
    if isinstance(ref_dt, date) and not isinstance(ref_dt, datetime):
        ref_dt = datetime.combine(ref_dt, time(12, 0), tzinfo=BERLIN)
    elif isinstance(ref_dt, datetime) and ref_dt.tzinfo is None:
        ref_dt = ref_dt.replace(tzinfo=BERLIN)

    ver = _current_data_version()

    select_cols = ["slot_start", "orig_date", "zeit", "hinweis", "area", "fahrzeug", "imported_at", "source_name"]
    _, df, spans = _load_ecm4_source_frames()
    if df.empty:
        return pd.DataFrame(columns=select_cols)

    ref_utc = pd.Timestamp(ref_dt).tz_convert("UTC")
    if spans.empty:
        result_cache_key = (ver, "all:no-spans")
        with _CACHE_LOCK:
            cached = _ECM4_RESULT_CACHE.get(result_cache_key)
            if cached is not None:
                return cached.copy(deep=True)
        out = df.drop(columns=["_slot_utc"]).sort_values(["slot_start", "area"]).reset_index(drop=True)
        with _CACHE_LOCK:
            if _current_data_version() == ver:
                if len(_ECM4_RESULT_CACHE) >= 64:
                    _ECM4_RESULT_CACHE.clear()
                _ECM4_RESULT_CACHE[result_cache_key] = out.copy(deep=True)
        return out

    in_range = spans[(spans["plan_min"] <= ref_utc) & (spans["plan_max"] >= ref_utc)]
    if not in_range.empty:
        chosen_imp = in_range.sort_values(
            ["_imported_sort", "imported_at"],
            ascending=[False, False],
            na_position="last",
        ).iloc[0]["imported_at"]
    else:
        def _dist(row: pd.Series) -> pd.Timedelta:
            if ref_utc < row["plan_min"]:
                return row["plan_min"] - ref_utc
            if ref_utc > row["plan_max"]:
                return ref_utc - row["plan_max"]
            return pd.Timedelta(0)

        spans["_dist"] = spans.apply(_dist, axis=1)
        chosen_imp = spans.sort_values(
            ["_dist", "_imported_sort", "imported_at"],
            ascending=[True, False, False],
            na_position="last",
        ).iloc[0]["imported_at"]

    result_cache_key = (ver, f"import:{chosen_imp}")
    with _CACHE_LOCK:
        cached = _ECM4_RESULT_CACHE.get(result_cache_key)
        if cached is not None:
            return cached.copy(deep=True)

    out = (
        df[df["imported_at"] == chosen_imp]
        .drop(columns=["_slot_utc"])
        .sort_values(["slot_start", "area"])
        .reset_index(drop=True)
    )
    with _CACHE_LOCK:
        if _current_data_version() == ver:
            if len(_ECM4_RESULT_CACHE) >= 64:
                _ECM4_RESULT_CACHE.clear()
            _ECM4_RESULT_CACHE[result_cache_key] = out.copy(deep=True)
    return out
