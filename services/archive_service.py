
from __future__ import annotations

from datetime import date, datetime, timedelta
import io
import re
import threading
from typing import Any

import pandas as pd


_CACHE_LOCK = threading.Lock()
_ARCHIVE_BASE_CACHE: tuple[int, pd.DataFrame] | None = None
_RECENT_DONE_CACHE: tuple[int, pd.DataFrame] | None = None
_PRIO_FRIST_HISTORY_CACHE: tuple[int, dict[str, str], dict[str, str]] | None = None


def configure(**deps) -> None:
    globals().update(deps)


def _load_archive_base_df_uncached() -> pd.DataFrame:
    rows = db_exec(
        """
        SELECT id, fahrzeug, friststufe, anfang, fertig, completed_at, status, status_ecm3, last_problem_note
        FROM archive
        WHERE restored_at IS NULL OR trim(restored_at)=''
        ORDER BY completed_at DESC, id DESC;
        """,
        fetch=True,
    ) or []
    cols = ["id", "fahrzeug", "friststufe", "anfang", "fertig", "completed_at", "status", "status_ecm3", "last_problem_note"]
    if rows:
        df = pd.DataFrame([dict(r) for r in rows])
        for c in cols:
            if c not in df.columns:
                df[c] = pd.NA
        df = df[cols].copy()
    else:
        df = pd.DataFrame(columns=cols)
    if df.empty:
        return df
    for c in ("anfang", "fertig", "completed_at"):
        df[c] = _coerce_berlin_datetime_series(df[c], naive=True)
    return df.sort_values(["completed_at", "id"], ascending=[False, False], na_position="last").reset_index(drop=True)


def _get_archive_base_df_cached() -> pd.DataFrame:
    global _ARCHIVE_BASE_CACHE
    ver = _current_data_version()
    with _CACHE_LOCK:
        cached = _ARCHIVE_BASE_CACHE
        if cached and cached[0] == ver:
            return cached[1].copy(deep=True)
    fresh = _load_archive_base_df_uncached()
    with _CACHE_LOCK:
        if _current_data_version() == ver:
            _ARCHIVE_BASE_CACHE = (ver, fresh.copy(deep=True))
    return fresh


def get_archive_df(
    limit: int | None = 500,
    *,
    date_from: date | datetime | pd.Timestamp | str | None = None,
    date_to: date | datetime | pd.Timestamp | str | None = None,
) -> pd.DataFrame:
    df = _get_archive_base_df_cached()
    if df.empty:
        return df.copy(deep=True)

    mask = pd.Series(True, index=df.index)
    if date_from is not None:
        ts_from = pd.to_datetime(date_from, errors="coerce")
        if not pd.isna(ts_from):
            ts_from = pd.Timestamp(ts_from)
            if isinstance(date_from, date) and not isinstance(date_from, datetime):
                ts_from = ts_from.replace(hour=0, minute=0, second=0, microsecond=0)
            mask &= (df["completed_at"] >= ts_from)

    if date_to is not None:
        ts_to = pd.to_datetime(date_to, errors="coerce")
        if not pd.isna(ts_to):
            ts_to = pd.Timestamp(ts_to)
            if isinstance(date_to, date) and not isinstance(date_to, datetime):
                ts_to = ts_to.replace(hour=0, minute=0, second=0, microsecond=0) + pd.Timedelta(days=1)
                mask &= (df["completed_at"] < ts_to)
            else:
                mask &= (df["completed_at"] <= ts_to)

    out = df[mask].copy()
    if limit is not None:
        out = out.head(max(0, int(limit)))
    return out.reset_index(drop=True)


def _norm_status_key(status_raw: Any) -> str:
    s = str(status_raw or "").strip()
    for bad, good in {
        "\u00c3\u00a4": "ä",
        "\u00c3\u00b6": "ö",
        "\u00c3\u00bc": "ü",
        "\u00c3\u009f": "ß",
        "\u00c3\u0178": "ß",
    }.items():
        s = s.replace(bad, good)
    s = s.casefold()
    s = s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return s


def df_to_excel_bytes(df: pd.DataFrame, sheet_name: str = "Daten") -> bytes:
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    bio.seek(0)
    return bio.read()


def build_kpi_monthly(df_arch: pd.DataFrame) -> pd.DataFrame:
    if df_arch is None or df_arch.empty:
        return pd.DataFrame(columns=["Monat", "Gesamt", "Pünktlich", "Verspätet", "Quote_Pünktlich_%"])
    df = df_arch.copy()
    df["completed_at"] = pd.to_datetime(df["completed_at"], errors="coerce")
    df["Monat"] = df["completed_at"].dt.strftime("%Y-%m")
    status_key = df["status"].apply(_norm_status_key)
    df["_is_ontime"] = status_key.isin({"puenktlich", "punktlich"}).astype("int8")
    df["_is_late"] = status_key.isin({"verspaetet", "verspatet"}).astype("int8")
    out = (
        df.groupby("Monat", dropna=True)
        .agg(
            Gesamt=("status", "size"),
            Pünktlich=("_is_ontime", "sum"),
            Verspätet=("_is_late", "sum"),
        )
        .reset_index()
    )
    out["Quote_Pünktlich_%"] = (out["Pünktlich"] * 100.0 / out["Gesamt"]).round(1)
    return out.sort_values("Monat").reset_index(drop=True)


def build_kpi_baureihe(df_arch: pd.DataFrame) -> pd.DataFrame:
    if df_arch is None or df_arch.empty:
        return pd.DataFrame(columns=["Baureihe", "Gesamt", "Pünktlich", "Verspätet", "Quote_Pünktlich_%"])

    df = df_arch.copy()
    veh = df["fahrzeug"].astype(str).str.strip()
    head = veh.str.split(".", n=1).str[0]
    df["Baureihe"] = head.str.extract(r"(\d+)$", expand=False).fillna("")
    keep = {"445", "3462", "4746", "4748", "1622"}
    df = df[df["Baureihe"].isin(keep)].copy()
    if df.empty:
        return pd.DataFrame(columns=["Baureihe", "Gesamt", "Pünktlich", "Verspätet", "Quote_Pünktlich_%"])

    status_key = df["status"].apply(_norm_status_key)
    df["_is_ontime"] = status_key.isin({"puenktlich", "punktlich"}).astype("int8")
    df["_is_late"] = status_key.isin({"verspaetet", "verspatet"}).astype("int8")
    out = (
        df.groupby("Baureihe", dropna=True)
        .agg(
            Gesamt=("status", "size"),
            Pünktlich=("_is_ontime", "sum"),
            Verspätet=("_is_late", "sum"),
        )
        .reset_index()
    )
    out["Quote_Pünktlich_%"] = (out["Pünktlich"] * 100.0 / out["Gesamt"]).round(1)
    order = ["445", "3462", "4746", "4748", "1622"]
    out["__o"] = out["Baureihe"].apply(lambda x: order.index(x) if x in order else 999)
    return out.sort_values(["__o", "Baureihe"]).drop(columns="__o").reset_index(drop=True)


def _get_prio_frist_history_maps() -> tuple[dict[str, str], dict[str, str]]:
    global _PRIO_FRIST_HISTORY_CACHE
    ver = _current_data_version()
    with _CACHE_LOCK:
        cached = _PRIO_FRIST_HISTORY_CACHE
        if cached and cached[0] == ver:
            return dict(cached[1]), dict(cached[2])

    main_map: dict[str, str] = {}
    urd_map: dict[str, str] = {}

    def _feed(df_hist: pd.DataFrame) -> None:
        if df_hist is None or df_hist.empty:
            return
        for _, rr in df_hist.iterrows():
            veh_raw = _norm(rr.get("fahrzeug"))
            if not veh_raw:
                continue
            veh_norm = _norm_vehicle(veh_raw) or veh_raw
            fr_raw = _norm(rr.get("friststufe"))
            fr_txt = fr_raw if fr_raw else "-"
            is_urd = bool(re.search(r"\bURD\b", fr_txt, flags=re.I))
            target = urd_map if is_urd else main_map
            if veh_norm not in target:
                target[veh_norm] = fr_txt
            if veh_raw not in target:
                target[veh_raw] = fr_txt

    # Restore-faehige Archivzeilen sind bereits im einheitlichen Archiv enthalten.
    _feed(_get_recent_done_base_cached())
    _feed(_get_archive_base_df_cached())

    with _CACHE_LOCK:
        if _current_data_version() == ver:
            _PRIO_FRIST_HISTORY_CACHE = (ver, dict(main_map), dict(urd_map))

    return main_map, urd_map


def _get_recent_done_base_cached() -> pd.DataFrame:
    global _RECENT_DONE_CACHE
    ver = _current_data_version()
    with _CACHE_LOCK:
        cached = _RECENT_DONE_CACHE
        if cached and cached[0] == ver:
            return cached[1].copy(deep=True)
    fresh = _load_recent_done_base_uncached()
    with _CACHE_LOCK:
        if _current_data_version() == ver:
            _RECENT_DONE_CACHE = (ver, fresh.copy(deep=True))
    return fresh


def get_recent_done_df(limit: int = 600) -> pd.DataFrame:
    _purge_recent_done_archive()
    df = _get_recent_done_base_cached()
    if limit is not None:
        df = df.head(max(0, int(limit))).copy()
    if not df.empty:
        now = now_berlin()
        df["resttage"] = (df["expires_at"] - pd.Timestamp(now)).dt.total_seconds() / 86400.0
        df["resttage"] = df["resttage"].fillna(0).astype(float).round(1)
    else:
        df["resttage"] = pd.Series(dtype=float)
    return df


# Unified archive model:
# archive is the single source for KPI data and for short-term restore.
def _purge_recent_done_archive(now_dt: datetime | None = None) -> None:
    now_loc = as_berlin(now_dt or now_berlin()) or now_berlin()
    conn = get_conn()
    changed = False
    with _DB_WRITE_LOCK:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                UPDATE archive
                SET restore_until=NULL
                WHERE restore_until IS NOT NULL
                  AND trim(restore_until) <> ''
                  AND datetime(restore_until) <= datetime(?);
                """,
                (now_loc.isoformat(timespec="seconds"),),
            )
            changed = cur.rowcount > 0
            conn.commit()
        finally:
            cur.close()
    if changed:
        bump_data_version()


def _remember_recent_done(
    fahrzeug: Any,
    friststufe: Any,
    zusatzarbeiten: Any,
    done_at: datetime | None = None,
    *,
    archive_id: int | None = None,
    snapshot: dict[str, Any] | None = None,
) -> None:
    archive_id_val = int(archive_id or 0)
    if archive_id_val <= 0:
        return
    snap = dict(snapshot or {})
    done_loc = as_berlin(done_at or now_berlin()) or now_berlin()
    restore_until = done_loc + timedelta(days=14)
    planning_order_id = int(snap.get("planning_order_id") or 0) or None
    archived_open_task_id = int(snap.get("open_task_id") or snap.get("archived_open_task_id") or 0) or None
    source_system = _clean_nullable_text(snap.get("source_system")) or ("planner" if planning_order_id else None)
    db_exec(
        """
        UPDATE archive
        SET zusatzarbeiten=?,
            gewerke=?,
            arbeitsplatz=?,
            ap_pdf=?,
            last_problem_at=?,
            ecm3_fertig=?,
            zusatz_done=?,
            frist_done=?,
            planning_order_id=?,
            source_system=?,
            archived_open_task_id=?,
            restore_until=?,
            restored_at=NULL
        WHERE id=?;
        """,
        (
            _clean_nullable_text(zusatzarbeiten),
            _clean_nullable_text(snap.get("gewerke")),
            _clean_nullable_text(snap.get("arbeitsplatz")),
            _clean_nullable_text(snap.get("ap_pdf")),
            _clean_nullable_db_text(snap.get("last_problem_at")),
            _clean_nullable_db_text(snap.get("ecm3_fertig")),
            _clean_nullable_text(snap.get("zusatz_done")),
            _clean_nullable_text(snap.get("frist_done")),
            planning_order_id,
            source_system,
            archived_open_task_id,
            restore_until.isoformat(timespec="seconds"),
            archive_id_val,
        ),
        commit=True,
    )
    _purge_recent_done_archive(now_dt=done_loc)


def _load_recent_done_base_uncached() -> pd.DataFrame:
    rows = db_exec(
        """
        SELECT id, fahrzeug, friststufe, zusatzarbeiten, completed_at AS archived_at, restore_until AS expires_at
        FROM archive
        WHERE restore_until IS NOT NULL
          AND trim(restore_until) <> ''
          AND (restored_at IS NULL OR trim(restored_at)='')
        ORDER BY completed_at DESC, id DESC;
        """,
        fetch=True,
    ) or []
    cols = ["id", "fahrzeug", "friststufe", "zusatzarbeiten", "archived_at", "expires_at"]
    df = pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame(columns=cols)
    for c in cols:
        if c not in df.columns:
            df[c] = pd.NA
    df = df[cols].copy()
    for c in ("archived_at", "expires_at"):
        df[c] = _coerce_berlin_datetime_series(df[c])
    if df.empty:
        return df
    return df.sort_values(["archived_at", "id"], ascending=[False, False], na_position="last").reset_index(drop=True)


def _restore_archive_entry(archive_id: int) -> bool:
    row = db_exec(
        """
        SELECT id, fahrzeug, friststufe, zusatzarbeiten, gewerke,
               anfang, fertig, arbeitsplatz, ap_pdf,
               last_problem_note, last_problem_at, initial_fertig, ecm3_fertig,
               zusatz_done, frist_done, planning_order_id, source_system, archived_open_task_id, completed_at
        FROM archive
        WHERE id=?
          AND (restored_at IS NULL OR trim(restored_at)='')
        LIMIT 1;
        """,
        (int(archive_id),),
        fetchone=True,
    )
    if not row:
        return False
    fahrzeug = str(row["fahrzeug"] or "").strip()
    if not fahrzeug:
        return False
    frist = str(row["friststufe"] or "").strip()
    anfang = _clean_nullable_db_text(row["anfang"])
    fertig = _clean_nullable_db_text(row["fertig"])
    sig = make_sig(fahrzeug, frist, anfang, fertig)
    planning_order_id = int(row["planning_order_id"] or 0) or None
    source_system = _clean_nullable_text(row["source_system"]) or ("planner" if planning_order_id else None)
    archived_open_task_id = int(row["archived_open_task_id"] or 0) or None

    conn = get_conn()
    with _DB_WRITE_LOCK:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT id
                FROM open_tasks
                WHERE sig=?
                   OR (
                        lower(trim(fahrzeug))=?
                    AND lower(trim(coalesce(friststufe, '')))=?
                    AND coalesce(anfang, '')=coalesce(?, '')
                    AND coalesce(fertig, '')=coalesce(?, '')
                   )
                ORDER BY id DESC
                LIMIT 1;
                """,
                (sig, fahrzeug.casefold(), frist.casefold(), anfang, fertig),
            )
            existing = cur.fetchone()
            values = (
                fahrzeug,
                frist,
                anfang,
                fertig,
                _clean_nullable_text(row["arbeitsplatz"]),
                _clean_nullable_text(row["ap_pdf"]),
                _clean_nullable_text(row["zusatzarbeiten"]),
                _clean_nullable_text(row["gewerke"]),
                _clean_problem_note(row["last_problem_note"]),
                _clean_nullable_db_text(row["last_problem_at"]),
                sig,
                _clean_nullable_db_text(row["initial_fertig"]) or fertig,
                _clean_nullable_db_text(row["ecm3_fertig"]),
                _clean_nullable_text(row["zusatz_done"]),
                _clean_nullable_text(row["frist_done"]),
                planning_order_id,
                source_system,
            )
            if existing:
                cur.execute(
                    """
                    UPDATE open_tasks
                    SET fahrzeug=?, friststufe=?, anfang=?, fertig=?, arbeitsplatz=?, ap_pdf=?,
                        zusatzarbeiten=?, gewerke=?, last_problem_note=?, last_problem_at=?, sig=?, initial_fertig=?, ecm3_fertig=?,
                        zusatz_done=?, frist_done=?, planning_order_id=?, source_system=?
                    WHERE id=?;
                    """,
                    values + (int(existing["id"]),),
                )
            else:
                can_reuse_open_id = False
                if archived_open_task_id:
                    cur.execute("SELECT id FROM open_tasks WHERE id=?;", (int(archived_open_task_id),))
                    can_reuse_open_id = cur.fetchone() is None
                id_columns = "id, " if can_reuse_open_id else ""
                id_placeholders = "?, " if can_reuse_open_id else ""
                id_values = (int(archived_open_task_id),) if can_reuse_open_id else ()
                cur.execute(
                    f"""
                    INSERT INTO open_tasks(
                        {id_columns}fahrzeug, friststufe, anfang, fertig, arbeitsplatz, ap_pdf,
                        zusatzarbeiten, gewerke, last_problem_note, last_problem_at, sig, initial_fertig, ecm3_fertig,
                        zusatz_done, frist_done, planning_order_id, source_system
                    ) VALUES ({id_placeholders}?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    id_values + values,
                )
            cur.execute(
                "UPDATE archive SET restored_at=?, restore_until=NULL WHERE id=?;",
                (now_berlin().isoformat(timespec="seconds"), int(archive_id)),
            )
            conn.commit()
        finally:
            cur.close()
    bump_data_version()
    return True


def restore_recent_done_for_planning_order(planning_order_id: int) -> bool:
    order_id = int(planning_order_id or 0)
    if order_id <= 0:
        return False
    row = db_exec(
        """
        SELECT id
        FROM archive
        WHERE planning_order_id=?
          AND (restored_at IS NULL OR trim(restored_at)='')
        ORDER BY completed_at DESC, id DESC
        LIMIT 1;
        """,
        (order_id,),
        fetchone=True,
    )
    if row:
        return _restore_archive_entry(int(row["id"]))
    return False


def delete_recent_done_entry(entry_id: int) -> bool:
    if not can_delete_recent_done_functions():
        return False
    if _restore_archive_entry(int(entry_id)):
        return True
    return False
