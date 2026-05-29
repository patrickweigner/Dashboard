
from __future__ import annotations

import logging
import re
import sqlite3
from datetime import date, datetime, time
from typing import Any

import pandas as pd


logger = logging.getLogger(__name__)


def configure(**deps) -> None:
    globals().update(deps)


def _get_existing_open_by_vehicle(fzg: str) -> sqlite3.Row | None:
    key = str(fzg or "").strip()
    if not key:
        return None
    row = db_exec(
        """
        SELECT id, fahrzeug, friststufe, anfang, fertig, arbeitsplatz, zusatzarbeiten, planning_order_id
        FROM open_tasks
        WHERE lower(trim(fahrzeug))=lower(trim(?))
        ORDER BY id DESC
        LIMIT 1;
        """,
        (key,),
        fetchone=True,
    )
    if row:
        return row
    norm = (_norm_vehicle(key) or "").casefold()
    if not norm:
        return None
    rows = db_exec(
        "SELECT id, fahrzeug, friststufe, anfang, fertig, arbeitsplatz, zusatzarbeiten, planning_order_id FROM open_tasks;",
        fetch=True,
    ) or []
    for rr in rows:
        other = (_norm_vehicle(str(rr["fahrzeug"] or "")) or str(rr["fahrzeug"] or "")).casefold()
        if other and other == norm:
            return rr
    return None


def _split_iso_to_date_time(value: Any) -> tuple[str, str]:
    raw = str(value or "").strip()
    if not raw:
        return "", ""
    normalized = raw.replace("Z", "")
    if "T" in normalized:
        date_part, time_part = normalized.split("T", 1)
    elif " " in normalized:
        date_part, time_part = normalized.split(" ", 1)
    else:
        return normalized[:10], ""
    return date_part[:10], time_part[:5]


def _sync_manual_open_task_to_planner(open_task_id: int) -> None:
    row = db_exec(
        """
        SELECT id, fahrzeug, friststufe, anfang, fertig, zusatzarbeiten, gewerke, planning_order_id
        FROM open_tasks
        WHERE id=?
        LIMIT 1;
        """,
        (int(open_task_id),),
        fetchone=True,
    )
    if not row:
        return

    from app.features.planning.service import upsert_order_from_form

    start_date, start_time = _split_iso_to_date_time(row["anfang"])
    end_date, end_time = _split_iso_to_date_time(row["fertig"])
    upsert_order_from_form(
        order_id=int(row["planning_order_id"] or 0) or None,
        fahrzeug=str(row["fahrzeug"] or ""),
        friststufe=str(row["friststufe"] or ""),
        zusatzarbeiten=str(row["zusatzarbeiten"] or ""),
        gewerke_info=str(row["gewerke"] or ""),
        ecm3_start_date=start_date,
        ecm3_start_time=start_time,
        ecm3_end_date=end_date,
        ecm3_end_time=end_time,
        status="freigegeben",
        source_origin="open_tasks_manual",
        source_open_task_id=int(row["id"]),
        source_sheet="Offene Aufträge manuell",
    )


def create_or_update_open_task_manual(
    fzg: str,
    *,
    end_mode: str,
    ende_dt: datetime | None,
    zusatz: str,
) -> None:
    name = str(fzg or "").strip()
    if not name:
        raise ValueError("Fahrzeug leer.")

    existing = _get_existing_open_by_vehicle(name)
    if existing:
        oid = int(existing["id"])
        old_frist = str(existing["friststufe"] or "")
        old_anfang = str(existing["anfang"] or "") or None
        old_fertig = str(existing["fertig"] or "") or None
        old_area = str(existing["arbeitsplatz"] or "")
        old_zus = str(existing["zusatzarbeiten"] or "")
        new_zus = _append_text(old_zus, str(zusatz or "").strip())
        if end_mode == "new":
            if ende_dt is None:
                raise ValueError("Neues Ende wurde nicht gesetzt.")
            new_end = (as_berlin(ende_dt) or ende_dt).isoformat(timespec="minutes")
        else:
            new_end = old_fertig
        row = db_exec("SELECT initial_fertig FROM open_tasks WHERE id=?;", (oid,), fetchone=True)
        old_initial = str(row["initial_fertig"] or "") if row else ""
        new_initial = old_initial or (new_end or "")
        sig = make_sig(name, old_frist, old_anfang, new_end)
        db_exec(
            """
            UPDATE open_tasks
            SET anfang=?, fertig=?, arbeitsplatz=?, zusatzarbeiten=?, sig=?, initial_fertig=?
            WHERE id=?;
            """,
            (old_anfang, new_end, old_area, new_zus, sig, new_initial, oid),
            commit=True,
        )
        _sync_manual_open_task_to_planner(oid)
        return

    if ende_dt is None:
        raise ValueError("Bitte ein voraussichtliches Ende angeben.")
    end_iso = (as_berlin(ende_dt) or ende_dt).isoformat(timespec="minutes")
    frist = "Störung"
    sig = make_sig(name, frist, None, end_iso)
    conn = get_conn()
    with _DB_WRITE_LOCK:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO open_tasks (
                    fahrzeug, friststufe, anfang, fertig, arbeitsplatz, ap_pdf, zusatzarbeiten, sig, initial_fertig,
                    source_system
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (name, frist, None, end_iso, "", "", str(zusatz or "").strip(), sig, end_iso, "open_tasks_manual"),
            )
            open_task_id = int(cur.lastrowid or 0)
            conn.commit()
        finally:
            cur.close()
    bump_data_version()
    _sync_manual_open_task_to_planner(open_task_id)

def _validate_vehicle_area_assignment(open_id: int, area_code: str) -> tuple[bool, str]:
    area_code = _normalize_workshop_area(area_code)
    if area_code not in WORKSHOP_AREAS:
        return False, f"Ungültiger Bereich: {area_code or 'leer'}"

    row = db_exec(
        "SELECT ap_pdf, friststufe FROM open_tasks WHERE id=?;",
        (int(open_id),),
        fetchone=True,
    )
    if not row:
        return False, "Datensatz nicht gefunden."

    ap_src = _clean_ap(row["ap_pdf"] if row else "")
    if ap_src.casefold() == "rws":
        return False, "Auftrag mit Arbeitsplatz RWS kann nicht in der Werkstatthalle zugeordnet werden."

    frist = str(row["friststufe"] if row else "")
    is_urd = bool(re.search(r"\bURD\b", frist, flags=re.I))
    is_main_track = area_code in {"4A", "4B", "5A", "5B"}
    if is_urd and is_main_track:
        return False, "URD-Aufträge können nur dem Bereich URD zugeordnet werden."
    if (not is_urd) and area_code == "URD":
        return False, "Im Bereich URD sind nur URD-Aufträge zulässig."
    return True, ""


def find_other_assigned_rows_for_same_vehicle(open_id: int, target_area: str | None = None) -> list[dict[str, Any]]:
    row = db_exec(
        "SELECT fahrzeug FROM open_tasks WHERE id=?;",
        (int(open_id),),
        fetchone=True,
    )
    if not row:
        return []
    base_vehicle = str(row["fahrzeug"] or "").strip()
    base_key = _vehicle_compare_key(base_vehicle)
    if not base_key:
        return []

    target_area_norm = _normalize_workshop_area(target_area)
    rows = db_exec(
        """
        SELECT id, fahrzeug, friststufe, arbeitsplatz
        FROM open_tasks
        WHERE id<>?
          AND COALESCE(TRIM(arbeitsplatz), '') <> '';
        """,
        (int(open_id),),
        fetch=True,
    ) or []

    conflicts: list[dict[str, Any]] = []
    for rr in rows:
        ap = _normalize_workshop_area(rr["arbeitsplatz"])
        if ap not in WORKSHOP_AREAS:
            continue
        if target_area_norm and ap == target_area_norm:
            continue
        other_key = _vehicle_compare_key(rr["fahrzeug"])
        if other_key and other_key == base_key:
            conflicts.append(
                {
                    "id": int(rr["id"]),
                    "fahrzeug": str(rr["fahrzeug"] or "").strip(),
                    "friststufe": str(rr["friststufe"] or "").strip(),
                    "arbeitsplatz": ap,
                }
            )
    return conflicts


def assign_vehicle_to_area_with_shift(
    open_id: int,
    area_code: str,
    source_open_ids: list[int] | None = None,
) -> tuple[bool, str]:
    area_code = _normalize_workshop_area(area_code)
    ok, msg = _validate_vehicle_area_assignment(int(open_id), area_code)
    if not ok:
        return False, msg

    source_ids: list[int] = []
    for raw_id in (source_open_ids or []):
        try:
            rid = int(raw_id)
        except Exception:
            continue
        if rid != int(open_id):
            source_ids.append(rid)
    source_ids = sorted(set(source_ids))
    if not source_ids:
        source_ids = [int(x["id"]) for x in find_other_assigned_rows_for_same_vehicle(int(open_id), target_area=area_code)]

    conn = get_conn()
    cur = conn.cursor()
    try:
        with _DB_WRITE_LOCK:
            cur.execute("BEGIN;")
            for rid in source_ids:
                cur.execute("UPDATE open_tasks SET arbeitsplatz='' WHERE id=?;", (int(rid),))
            cur.execute("UPDATE open_tasks SET arbeitsplatz=? WHERE id=?;", (area_code, int(open_id)))
            conn.commit()
            bump_data_version()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        logger.exception("Fehler beim Verschieben/Zuordnen von Fahrzeug %s nach %s", open_id, area_code)
        return False, "Zuordnung konnte nicht gespeichert werden."
    finally:
        cur.close()
    return True, "Bereich gespeichert."


def assign_area(open_id: int, area: str) -> tuple[bool, str]:
    area_norm = _normalize_workshop_area(area)
    if not area_norm:
        db_exec("UPDATE open_tasks SET arbeitsplatz='' WHERE id=?;", (int(open_id),), commit=True)
        return True, "Zuordnung entfernt."
    if area_norm not in WORKSHOP_AREAS:
        return False, "Ungültiger Bereich."

    conflict_ids = [
        int(x["id"])
        for x in find_other_assigned_rows_for_same_vehicle(int(open_id), target_area=area_norm)
    ]
    return assign_vehicle_to_area_with_shift(int(open_id), area_norm, source_open_ids=conflict_ids)

def _task_type_key(frist: Any) -> str:
    s = str(frist or "").strip().casefold()
    if not s:
        return "p"
    if "urd" in s:
        return "urd"
    if s in {"k", "korrektiv"} or "korrektiv" in s:
        return "k"
    return "p"


def _canon_dt_for_import_compare(val: Any) -> str:
    txt = str(val or "").strip()
    if not txt:
        return ""
    ts = pd.to_datetime(txt, errors="coerce")
    if pd.isna(ts):
        return txt[:16]
    if isinstance(ts, pd.Timestamp):
        if ts.tzinfo is not None:
            ts = ts.tz_convert(BERLIN).tz_localize(None)
        return ts.strftime("%Y-%m-%dT%H:%M")
    return txt[:16]


def _canon_ap_for_import_compare(val: Any) -> str:
    return _clean_ap(val).casefold()


def _canon_frist_for_import_compare(val: Any) -> str:
    return str(val or "").strip().casefold()


def _canon_zus_for_import_compare(val: Any) -> tuple[str, ...]:
    items = _parse_zusatz_items(val)
    out: list[str] = []
    for item in items:
        norm = re.sub(r"\s+", " ", str(item or "").strip()).casefold()
        if norm:
            out.append(norm)
    return tuple(out)


def _canon_gewerke_for_import_compare(val: Any) -> tuple[str, ...]:
    out: list[str] = []
    for raw_line in str(val or "").splitlines():
        line = str(raw_line or "").strip()
        if not line:
            continue
        line = re.sub(r"^[\s\-•]+", "", line)
        norm = re.sub(r"\s+", " ", line).strip().casefold()
        if norm and norm not in {"nan", "nat", "none", "null"}:
            out.append(norm)
    return tuple(out)


def _extract_first_wash_zus_item(zus_raw: Any) -> str:
    for item in _parse_zusatz_items(zus_raw):
        if _is_wash_zus_item(item):
            return str(item).strip()
    return ""


def _merge_import_zus_preserving_wash(old_zus: Any, new_zus: Any) -> str:
    new_items = _parse_zusatz_items(new_zus)
    old_wash = _extract_first_wash_zus_item(old_zus)
    has_wash_in_new = any(_is_wash_zus_item(x) for x in new_items)
    merged: list[str] = []
    seen: set[str] = set()
    for item in new_items:
        key = re.sub(r"\s+", " ", str(item or "").strip()).casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(str(item).strip())
    if old_wash and not has_wash_in_new:
        key = re.sub(r"\s+", " ", old_wash).casefold()
        if key and key not in seen:
            merged.append(old_wash)
    if not merged:
        return ""
    return "\n".join(f"- {x}" for x in merged)


def _recent_done_vehicle_key(raw: Any) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    return (_norm_vehicle(s) or s).casefold()


def _recent_done_frist_key(raw: Any) -> str:
    return str(raw or "").strip().casefold()


def _recent_done_zus_key(raw: Any) -> str:
    return "||".join(_canon_zus_for_import_compare(raw))


def _load_recent_done_lookup() -> dict[tuple[str, str], list[str]]:
    rows = db_exec(
        """
        SELECT fahrzeug, friststufe, zusatzarbeiten
        FROM archive
        WHERE restore_until IS NOT NULL
          AND trim(restore_until) <> ''
          AND (restored_at IS NULL OR trim(restored_at)='');
        """,
        fetch=True,
    ) or []
    lookup: dict[tuple[str, str], list[str]] = {}
    for rr in rows:
        vk = _recent_done_vehicle_key(rr["fahrzeug"])
        fk = _recent_done_frist_key(rr["friststufe"])
        lookup.setdefault((vk, fk), []).append(str(rr["zusatzarbeiten"] or ""))
    return lookup


def _is_recent_done_match(
    lookup: dict[tuple[str, str], list[str]],
    fahrzeug: Any,
    friststufe: Any,
    zus_new: Any,
) -> bool:
    vk = _recent_done_vehicle_key(fahrzeug)
    fk = _recent_done_frist_key(friststufe)
    if not vk:
        return False
    lst = lookup.get((vk, fk)) or []
    if not lst:
        return False
    for zus_old in lst:
        zus_effective = _merge_import_zus_preserving_wash(zus_old, zus_new)
        if _canon_zus_for_import_compare(zus_old) == _canon_zus_for_import_compare(zus_effective):
            return True
    return False


def _import_change_flags(
    *,
    old_frist: Any,
    new_frist: Any,
    old_anf: Any,
    new_anf: Any,
    old_end: Any,
    new_end: Any,
    old_ecm3_end: Any,
    new_ecm3_end: Any,
    old_ap: Any,
    new_ap: Any,
    old_zus: Any,
    new_zus: Any,
    old_gewerke: Any,
    new_gewerke: Any,
) -> dict[str, bool]:
    return {
        "frist": _canon_frist_for_import_compare(old_frist) != _canon_frist_for_import_compare(new_frist),
        "start": _canon_dt_for_import_compare(old_anf) != _canon_dt_for_import_compare(new_anf),
        "end": _canon_dt_for_import_compare(old_end) != _canon_dt_for_import_compare(new_end),
        "ecm3_end": _canon_dt_for_import_compare(old_ecm3_end) != _canon_dt_for_import_compare(new_ecm3_end),
        "ap": _canon_ap_for_import_compare(old_ap) != _canon_ap_for_import_compare(new_ap),
        "zus": _canon_zus_for_import_compare(old_zus) != _canon_zus_for_import_compare(new_zus),
        "gewerke": _canon_gewerke_for_import_compare(old_gewerke) != _canon_gewerke_for_import_compare(new_gewerke),
    }


def build_import_diff(df_norm: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    if df_norm is None or df_norm.empty:
        empty = pd.DataFrame(
            columns=[
                "action",
                "Fahrzeug",
                "Friststufe",
                "Friststufe_old",
                "Friststufe_new",
                "Anfang_old",
                "Anfang_new",
                "Fertig_old",
                "Fertig_new",
                "ap_pdf_old",
                "ap_pdf_new",
                "zus_old",
                "zus_new",
                "gewerke_old",
                "gewerke_new",
                "changed_fields",
                "sig_conflict",
            ]
        )
        return empty, {"total": 0, "new": 0, "update": 0, "skip": 0, "sig_conflicts": 0}

    _purge_recent_done_archive()
    recent_done_lookup = _load_recent_done_lookup()

    rows = db_exec(
        """
        SELECT id, fahrzeug, friststufe, anfang, fertig, ecm3_fertig, ap_pdf, zusatzarbeiten, gewerke, sig
        FROM open_tasks
        ORDER BY
            CASE WHEN fertig IS NULL OR TRIM(fertig)='' THEN 1 ELSE 0 END,
            fertig DESC,
            anfang DESC,
            id DESC;
        """,
        fetch=True,
    ) or []

    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    by_vehicle_typ: dict[tuple[str, str], dict[str, Any]] = {}
    sig_map: dict[str, int] = {}
    for rr in rows:
        oid = int(rr["id"])
        fzg_key = str(rr["fahrzeug"] or "").strip()
        fr_key = str(rr["friststufe"] or "").strip()
        payload = {
            "id": oid,
            "friststufe": fr_key,
            "anfang": rr["anfang"],
            "fertig": rr["fertig"],
            "ecm3_fertig": rr["ecm3_fertig"],
            "ap_pdf": rr["ap_pdf"],
            "zus": rr["zusatzarbeiten"],
            "gewerke": rr["gewerke"],
            "sig": rr["sig"],
        }
        if (fzg_key, fr_key) not in by_key:
            by_key[(fzg_key, fr_key)] = payload
        typ_key = _task_type_key(fr_key)
        if fzg_key and (fzg_key, typ_key) not in by_vehicle_typ:
            by_vehicle_typ[(fzg_key, typ_key)] = payload
        if payload["sig"]:
            sig_map[str(payload["sig"])] = oid

    out: list[dict[str, Any]] = []
    newc = updc = skpc = sigc = 0
    for _, r in df_norm.iterrows():
        fzg = str(r.get("Fahrzeug") or "").strip()
        frist = str(r.get("Friststufe") or "").strip()
        anfang = r.get("Anfang")
        fertig = r.get("Fertig")
        ecm3_new_raw = r.get("ecm3_fertig")
        ap_pdf_new = _clean_ap(r.get("Arbeitsplatz") or "")
        zus_new_raw = str(r.get("Zusatzarbeiten") or "")
        gewerke_new = str(r.get("Gewerke") or "").strip()
        zus_new = zus_new_raw
        fr_old = ""
        new_sig = make_sig(fzg, frist, anfang, fertig)

        ex = by_key.get((fzg, frist))
        if ex is None:
            ex = by_vehicle_typ.get((fzg, _task_type_key(frist)))

        if not ex:
            anf_old = end_old = ap_old = zus_old = gewerke_old = ""
            ecm3_old = ""
            if _is_recent_done_match(recent_done_lookup, fzg, frist, zus_new_raw):
                action = "SKIP"
                skpc += 1
                changed_fields = "Erledigt (Archiv)"
            else:
                action = "NEW"
                newc += 1
                changed_fields = "Neu"
        else:
            fr_old = str(ex.get("friststufe") or "")
            anf_old = ex.get("anfang") or ""
            end_old = ex.get("fertig") or ""
            ecm3_old = ex.get("ecm3_fertig") or ""
            ap_old = ex.get("ap_pdf") or ""
            zus_old = ex.get("zus") or ""
            gewerke_old = str(ex.get("gewerke") or "")
            zus_new = _merge_import_zus_preserving_wash(zus_old, zus_new_raw)
            ecm3_new = ecm3_new_raw or ecm3_old
            flags = _import_change_flags(
                old_frist=fr_old,
                new_frist=frist,
                old_anf=anf_old,
                new_anf=anfang,
                old_end=end_old,
                new_end=fertig,
                old_ecm3_end=ecm3_old,
                new_ecm3_end=ecm3_new,
                old_ap=ap_old,
                new_ap=ap_pdf_new,
                old_zus=zus_old,
                new_zus=zus_new,
                old_gewerke=gewerke_old,
                new_gewerke=gewerke_new,
            )
            parts: list[str] = []
            if flags["frist"]:
                parts.append(f"Friststufe ({fr_old or '-'} -> {frist or '-'})")
            if flags["start"]:
                parts.append("Anfang")
            if flags["end"]:
                parts.append("Fertig")
            if flags["ecm3_end"]:
                parts.append("Interne Planzeit")
            if flags["ap"]:
                parts.append("Arbeitsplatz")
            if flags["zus"]:
                parts.append("Zusatzarbeiten")
            if flags["gewerke"]:
                parts.append("Gewerke")
            changed_fields = ", ".join(parts) if parts else ""
            if not changed_fields:
                action = "SKIP"
                skpc += 1
            else:
                action = "UPDATE"
                updc += 1

        sig_conflict = ""
        other_id = sig_map.get(new_sig)
        if other_id is not None:
            current_id = int(ex["id"]) if ex else None
            if current_id is None or current_id != int(other_id):
                sig_conflict = f"sig bereits bei id={other_id}"
                sigc += 1

        out.append(
            {
                "action": action,
                "Fahrzeug": fzg,
                "Friststufe": frist,
                "Friststufe_old": fr_old or "",
                "Friststufe_new": frist,
                "Anfang_old": str(anf_old or "")[:16],
                "Anfang_new": str(anfang or "")[:16],
                "Fertig_old": str(end_old or "")[:16],
                "Fertig_new": str(fertig or "")[:16],
                "ap_pdf_old": ap_old or "",
                "ap_pdf_new": ap_pdf_new or "",
                "zus_old": zus_old or "",
                "zus_new": zus_new or "",
                "gewerke_old": gewerke_old or "",
                "gewerke_new": gewerke_new or "",
                "changed_fields": changed_fields,
                "sig_conflict": sig_conflict,
            }
        )

    diff_df = pd.DataFrame(out)
    order = pd.Categorical(diff_df["action"], categories=["NEW", "UPDATE", "SKIP"], ordered=True)
    diff_df = diff_df.assign(_o=order).sort_values(["_o", "Fertig_new", "Fahrzeug"], na_position="last").drop(columns="_o")
    summary = {
        "total": int(len(df_norm)),
        "new": int(newc),
        "update": int(updc),
        "skip": int(skpc),
        "sig_conflicts": int(sigc),
    }
    return diff_df.reset_index(drop=True), summary


def find_missing_open_tasks_for_import(df_norm: pd.DataFrame) -> list[dict[str, Any]]:
    if df_norm is None or df_norm.empty or "Fahrzeug" not in df_norm.columns:
        return []

    import_task_keys: set[tuple[str, str]] = set()
    for _, rr in df_norm.iterrows():
        raw_fzg = str(rr.get("Fahrzeug") or "").strip()
        if not raw_fzg:
            continue
        veh_key = _norm_vehicle(raw_fzg) or raw_fzg
        typ_key = _task_type_key(rr.get("Friststufe") or "")
        import_task_keys.add((veh_key, typ_key))

    rows = db_exec(
        """
        SELECT id, fahrzeug, friststufe, anfang, fertig, initial_fertig
        FROM open_tasks
        ORDER BY fahrzeug ASC, friststufe ASC, id ASC;
        """,
        fetch=True,
    ) or []
    out: list[dict[str, Any]] = []
    now = now_berlin()
    for row in rows:
        oid = int(row["id"])
        fzg = str(row["fahrzeug"] or "").strip()
        if not fzg:
            continue
        veh_key = _norm_vehicle(fzg) or fzg
        frist_raw = str(row["friststufe"] or "").strip()
        typ_key = _task_type_key(frist_raw)
        if (veh_key, typ_key) in import_task_keys:
            continue

        fertig_dt = pd.to_datetime(row["fertig"], errors="coerce")
        default_dt = as_berlin(fertig_dt) if pd.notna(fertig_dt) else now
        if default_dt is None:
            default_dt = now

        out.append(
            {
                "id": oid,
                "fahrzeug": fzg,
                "friststufe": frist_raw,
                "typ_group": typ_key,
                "anfang": _clean_nullable_text(row["anfang"]),
                "fertig": _clean_nullable_text(row["fertig"]),
                "initial_fertig": _clean_nullable_text(row["initial_fertig"]),
                "default_end_iso": default_dt.isoformat(timespec="minutes"),
            }
        )
    return out


def _planned_end_from_missing_item(item: dict[str, Any]) -> datetime | None:
    return _planned_deadline_dt(item.get("initial_fertig"), item.get("fertig"))


def clear_pending_missing_open_state(state: dict[str, Any] | None = None) -> None:
    if state is None:
        return
    state["missing_items"] = []
    state["missing_controls"] = []


def collect_missing_open_decisions(missing_controls: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    decisions: list[dict[str, Any]] = []
    errors: list[str] = []
    for ctrl in missing_controls or []:
        item = ctrl.get("item") or {}
        oid = int(ctrl.get("id"))
        fahrzeug = str(item.get("fahrzeug") or f"ID {oid}").strip()
        action_val = str(getattr(ctrl.get("action"), "value", "") or "").strip()

        if action_val == "keep":
            decisions.append({"id": oid, "mode": "keep", "fahrzeug": fahrzeug})
            continue
        if action_val == "delete":
            decisions.append({"id": oid, "mode": "delete", "fahrzeug": fahrzeug})
            continue
        if action_val != "archive":
            errors.append(f"{fahrzeug}: Unbekannte Entscheidung.")
            continue

        d_raw = str(getattr(ctrl.get("end_date"), "value", "") or "").strip()
        t_raw = str(getattr(ctrl.get("end_time"), "value", "") or "").strip()
        try:
            d_val = date.fromisoformat(d_raw[:10])
            if not re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?", t_raw):
                raise ValueError("invalid time")
            parts = [int(x) for x in t_raw.split(":")]
            finished_dt = datetime.combine(d_val, time(parts[0], parts[1]), tzinfo=BERLIN)
        except Exception:
            errors.append(f"{fahrzeug}: Ende (Datum/Uhrzeit) fehlt oder ist ungültig.")
            continue

        overdue_reason = None
        planned_dt = _planned_end_from_missing_item(item)
        if planned_dt is not None and finished_dt > planned_dt:
            reason_parts = [label for label, cb in (ctrl.get("checks") or []) if bool(getattr(cb, "value", False))]
            free = str(getattr(ctrl.get("reason_txt"), "value", "") or "").strip()
            if free:
                reason_parts.append(free)
            if not reason_parts:
                errors.append(f"{fahrzeug}: Verspätungsgrund erforderlich.")
                continue
            overdue_reason = ", ".join(reason_parts)

        decisions.append(
            {
                "id": oid,
                "mode": "archive",
                "fahrzeug": fahrzeug,
                "finished_end_iso": finished_dt.isoformat(timespec="minutes"),
                "overdue_reason": overdue_reason,
            }
        )
    return decisions, errors


def _delete_open_task_raw(open_id: int) -> bool:
    row = db_exec("SELECT id FROM open_tasks WHERE id=?;", (int(open_id),), fetchone=True)
    if not row:
        return False
    db_exec("DELETE FROM open_tasks WHERE id=?;", (int(open_id),), commit=True)
    return True


def archive_open_task_with_manual_end_raw(open_id: int, finished_end: datetime, overdue_reason: str | None = None) -> bool:
    row = db_exec(
        """
        SELECT fahrzeug, friststufe, anfang, fertig, arbeitsplatz, ap_pdf,
               last_problem_note, last_problem_at, initial_fertig, ecm3_fertig, zusatzarbeiten, gewerke,
               zusatz_done, frist_done, planning_order_id
        FROM open_tasks
        WHERE id=?;
        """,
        (int(open_id),),
        fetchone=True,
    )
    if not row:
        return False

    fahrzeug, frist, anfang, fertig, arb, ap_pdf, note, note_at, initial_fertig, ecm3_fertig, zus, gewerke, zus_done, frist_done, planning_order_id = row
    actual_dt = as_berlin(finished_end)
    if actual_dt is None:
        return False
    archived_at = now_berlin()

    planned_dt_berlin = _planned_deadline_dt(initial_fertig, fertig)
    status = _completion_status_for_deadline(actual_dt, planned_dt_berlin)
    status_ecm3 = _completion_status_for_deadline(actual_dt, ecm3_fertig)

    if status == "verspaetet":
        arch_note = str(overdue_reason or "").strip() or _extract_last_overdue_reason(note or "")
    else:
        arch_note = ""

    archive_id = _insert_archive_entry(
        fahrzeug=fahrzeug,
        friststufe=frist,
        anfang=anfang,
        fertig=actual_dt.isoformat(timespec="minutes"),
        last_problem_note=arch_note,
        completed_at=archived_at.isoformat(timespec="seconds"),
        status=status,
        status_ecm3=status_ecm3,
        initial_fertig=(
            planned_dt_berlin.isoformat(timespec="minutes") if planned_dt_berlin else actual_dt.isoformat(timespec="minutes")
        ),
    )
    _remember_recent_done(
        fahrzeug=fahrzeug,
        friststufe=frist,
        zusatzarbeiten=zus,
        done_at=archived_at,
        archive_id=archive_id,
        snapshot={
            "anfang": anfang,
            "fertig": fertig,
            "arbeitsplatz": arb,
            "ap_pdf": ap_pdf,
            "last_problem_note": note,
            "last_problem_at": note_at,
            "initial_fertig": initial_fertig,
            "ecm3_fertig": ecm3_fertig,
            "gewerke": gewerke,
            "zusatz_done": zus_done,
            "frist_done": frist_done,
            "planning_order_id": planning_order_id,
            "source_system": "planner" if int(planning_order_id or 0) > 0 else "",
            "open_task_id": int(open_id),
        },
    )
    db_exec("DELETE FROM open_tasks WHERE id=?;", (int(open_id),), commit=True)
    if int(planning_order_id or 0) > 0:
        try:
            from app.features.planning.service import set_order_statuses

            set_order_statuses([int(planning_order_id)], status="erledigt")
        except Exception as exc:
            logger.warning("Planner-Auftrag %s konnte beim Archivieren nicht auf erledigt gesetzt werden: %s", planning_order_id, exc)
    _send_archive_notification(
        open_id=int(open_id),
        fahrzeug=fahrzeug,
        arbeitsplatz=arb or ap_pdf,
        friststufe=frist,
        archived_at=archived_at,
    )
    return True


def apply_missing_open_decisions(decisions: list[dict[str, Any]]) -> tuple[int, int, int]:
    removed = archived = kept = 0
    for dec in decisions:
        mode = str(dec.get("mode") or "")
        oid = int(dec.get("id"))
        if mode == "delete":
            if _delete_open_task_raw(oid):
                removed += 1
            continue
        if mode == "archive":
            end_dt = pd.to_datetime(dec.get("finished_end_iso"), errors="coerce")
            if pd.isna(end_dt):
                continue
            py_dt = end_dt.to_pydatetime() if isinstance(end_dt, pd.Timestamp) else end_dt
            if archive_open_task_with_manual_end_raw(oid, py_dt, overdue_reason=dec.get("overdue_reason")):
                archived += 1
            continue
        if mode == "keep":
            kept += 1
    return removed, archived, kept


def add_open_tasks_with_progress(df: pd.DataFrame) -> tuple[int, int, int]:
    """
    NiceGUI-Variante: Fuehrt den Upsert aus und bereinigt danach Sig-Dubletten.
    """
    inserted, updated, skipped = upsert_open_tasks(df)
    dedupe_open_tasks_by_sig()
    return inserted, updated, skipped


def upsert_open_tasks(import_df: pd.DataFrame) -> tuple[int, int, int]:
    if import_df.empty:
        return 0, 0, 0

    _purge_recent_done_archive()
    recent_done_lookup = _load_recent_done_lookup()

    conn = get_conn()
    cur = conn.cursor()
    inserted = updated = skipped = 0
    try:
        with _DB_WRITE_LOCK:
            cur.execute("BEGIN;")
            for _, r in import_df.iterrows():
                fzg = _clean_nullable_text(r.get("Fahrzeug"))
                frist = _clean_nullable_text(r.get("Friststufe"))
                anfang = _clean_nullable_db_text(r.get("Anfang"))
                fertig = _clean_nullable_db_text(r.get("Fertig"))
                ecm3_fertig = _clean_nullable_db_text(r.get("ecm3_fertig"))
                ap_pdf = _clean_ap(_clean_nullable_text(r.get("Arbeitsplatz")))
                zus = _clean_nullable_text(r.get("Zusatzarbeiten"))
                gewerke = _clean_nullable_text(r.get("Gewerke"))
                if not fzg:
                    skipped += 1
                    continue
                if re.search(r"\bRWS\b", frist, flags=re.I):
                    skipped += 1
                    continue

                new_sig = make_sig(fzg, frist, anfang, fertig)
                cur.execute(
                    """
                    SELECT id, friststufe, anfang, fertig, ecm3_fertig, ap_pdf, zusatzarbeiten, gewerke, sig, initial_fertig
                    FROM open_tasks
                    WHERE fahrzeug=?
                    ORDER BY
                        CASE WHEN friststufe=? THEN 0 ELSE 1 END,
                        CASE WHEN fertig IS NULL OR TRIM(fertig)='' THEN 1 ELSE 0 END,
                        fertig DESC,
                        anfang DESC,
                        id DESC
                    LIMIT 5;
                    """,
                    (fzg, frist),
                )
                candidates = cur.fetchall() or []
                existing = None
                for c in candidates:
                    if _canon_frist_for_import_compare(c[1]) == _canon_frist_for_import_compare(frist):
                        existing = c
                        break
                if existing is None:
                    tgt_type = _task_type_key(frist or "")
                    for c in candidates:
                        if _task_type_key(c[1]) == tgt_type:
                            existing = c
                            break

                if existing is None:
                    if _is_recent_done_match(recent_done_lookup, fzg, frist, zus):
                        skipped += 1
                        continue
                    cur.execute(
                        """
                        INSERT INTO open_tasks(
                            fahrzeug, friststufe, anfang, fertig, ecm3_fertig, arbeitsplatz,
                            ap_pdf, zusatzarbeiten, gewerke, sig, initial_fertig, source_system
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (fzg, frist, anfang, fertig, ecm3_fertig, "", ap_pdf, zus, gewerke, new_sig, fertig, "upload_legacy"),
                    )
                    if cur.rowcount:
                        inserted += 1
                    else:
                        skipped += 1
                    continue

                oid, old_frist, old_anf, old_end, old_ecm3, old_ap, old_zus, old_gewerke, _old_sig, old_initial = existing
                zus_effective = _merge_import_zus_preserving_wash(old_zus, zus)
                old_anf = _clean_nullable_db_text(old_anf)
                old_end = _clean_nullable_db_text(old_end)
                old_ecm3 = _clean_nullable_db_text(old_ecm3)
                old_initial = _clean_nullable_db_text(old_initial)
                ecm3_effective = ecm3_fertig or old_ecm3
                flags = _import_change_flags(
                    old_frist=old_frist,
                    new_frist=frist,
                    old_anf=old_anf,
                    new_anf=anfang,
                    old_end=old_end,
                    new_end=fertig,
                    old_ecm3_end=old_ecm3,
                    new_ecm3_end=ecm3_effective,
                    old_ap=old_ap,
                    new_ap=ap_pdf,
                    old_zus=old_zus,
                    new_zus=zus_effective,
                    old_gewerke=old_gewerke,
                    new_gewerke=gewerke,
                )
                if not any(flags.values()):
                    skipped += 1
                    continue

                cur.execute("SELECT id FROM open_tasks WHERE sig=? AND id<>?;", (new_sig, int(oid)))
                other = cur.fetchone()
                if other:
                    cur.execute("DELETE FROM open_tasks WHERE id=?;", (int(other[0]),))

                new_initial = old_initial
                if new_initial is None and fertig:
                    new_initial = fertig

                cur.execute(
                    """
                    UPDATE open_tasks
                    SET friststufe=?, anfang=?, fertig=?, ecm3_fertig=COALESCE(?, ecm3_fertig), ap_pdf=?, zusatzarbeiten=?, gewerke=?, sig=?,
                        initial_fertig=CASE
                            WHEN initial_fertig IS NULL OR lower(trim(initial_fertig)) IN ('', 'nan', 'nat', 'none', 'null')
                            THEN ?
                            ELSE initial_fertig
                        END
                    WHERE id=?;
                    """,
                    (frist, anfang, fertig, ecm3_fertig, ap_pdf, zus_effective, gewerke, new_sig, new_initial, int(oid)),
                )
                updated += 1
            conn.commit()
            if inserted or updated:
                bump_data_version()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        cur.close()

    return inserted, updated, skipped
