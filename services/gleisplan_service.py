from __future__ import annotations

import math
import json
import re
from typing import Any, Callable

import pandas as pd

from services.gleisplan_templates import (
    EBERSWALDE_LAGEPLAN_TEMPLATE_KEY,
    GLEISPLAN_LAYOUT_TEMPLATES,
    format_gleisplan_template_validation,
    validate_gleisplan_template,
)

HALL_TRACK_GRID: tuple[tuple[str, str], tuple[str, str]] = (("4B", "4A"), ("5B", "5A"))
HALL_TRACKS: tuple[str, ...] = tuple(area for row in HALL_TRACK_GRID for area in row)

HALL_TRACK_LABELS: dict[str, str] = {
    "4B": "oben links",
    "4A": "oben rechts",
    "5B": "unten links",
    "5A": "unten rechts",
}
HALL_POSITION_ORDER: dict[str, int] = {
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
_DEFAULT_HALL_TRACK_ORDER: dict[str, int] = {area: index for index, area in enumerate(HALL_TRACKS)}

DEFAULT_HALL_TRACK_CONFIG: dict[str, dict[str, Any]] = {
    area: {
        "area_code": area,
        "track_label": area,
        "position_label": HALL_TRACK_LABELS.get(area, ""),
        "workshop_area": area,
        "sync_enabled": True,
        "active": True,
    }
    for area in HALL_TRACKS
}

LAYOUT_ITEM_TYPES: set[str] = {"anchor", "track", "hall", "building", "street", "switch", "buffer_stop"}
CONNECTABLE_ITEM_TYPES: set[str] = {"anchor", "hall", "switch", "buffer_stop"}
SWITCH_CONNECTION_PORTS: tuple[str, str, str] = ("1", "2", "3")
SINGLE_CONNECTION_PORT_TYPES: set[str] = {"buffer_stop"}
SWITCH_CONNECTION_OVERLAP_PCT = 1.15
BUFFER_STOP_CONNECTION_OVERLAP_PCT = 1.25
GLEISPLAN_RENDER_ASPECT = 1501 / 1058
SWITCH_MAIN_RAIL_Y_RATIO = 0.28
SWITCH_BRANCH_HEEL_X_RATIO = 0.80
SWITCH_BRANCH_PORT_X_RATIO = 0.06
SWITCH_BRANCH_PORT_Y_RATIO = 1.35
BUFFER_STOP_CONNECTION_EXTENSION_PCT = 0.45
SWITCH_PORT_RATIO_MIN = -2.0
SWITCH_PORT_RATIO_MAX = 3.0
LAYOUT_ITEM_ID_PREFIX_BY_TYPE: dict[str, str] = {
    "switch": "WEICHE",
    "buffer_stop": "PRELLBOCK",
    "anchor": "VERBINDUNGSPUNKT",
    "track": "VERBINDUNGSPUNKT",
    "hall": "HALLE",
    "building": "GEBAEUDE",
    "street": "STRASSE",
}

TRACK_DEFINITIONS: tuple[dict[str, str], ...] = (
    {"id": "GL12_NORD", "label": "GL 12", "title": "Nordbogen / Zufahrt", "css": "track-gl12-nord"},
    {"id": "URD", "label": "URD", "title": "URD", "css": "track-urd"},
    {"id": "GL10", "label": "GL 10", "title": "Gleis 10", "css": "track-gl10"},
    {"id": "GL1A", "label": "GL 1a", "title": "Westliche Abstellung oben", "css": "track-gl1a"},
    {"id": "GL1B", "label": "GL 1b", "title": "Westliche Abstellung unten", "css": "track-gl1b"},
    {"id": "GL1", "label": "GL 1", "title": "Mittelgleis", "css": "track-gl1"},
    {"id": "GL2", "label": "GL 2", "title": "Gleis 2 / Tankstelle", "css": "track-gl2"},
    {"id": "GL3", "label": "GL 3", "title": "Gleis 3 / ARA", "css": "track-gl3"},
    {"id": "ARA", "label": "ARA", "title": "ARA", "css": "track-ara"},
    {"id": "4B", "label": "4B", "title": "Gleishalle 4B", "css": "track-hall-4b"},
    {"id": "4A", "label": "4A", "title": "Gleishalle 4A", "css": "track-hall-4a"},
    {"id": "5A", "label": "5A", "title": "Gleishalle 5A", "css": "track-hall-5a"},
    {"id": "5B", "label": "5B", "title": "Gleishalle 5B", "css": "track-hall-5b"},
    {"id": "GL4_OST", "label": "GL 4", "title": "Ostgleis 4", "css": "track-gl4-ost"},
    {"id": "GL5_OST", "label": "GL 5", "title": "Ostgleis 5", "css": "track-gl5-ost"},
    {"id": "GL12_OST", "label": "GL 12", "title": "Ostbogen / Ausfahrt", "css": "track-gl12-ost"},
)

TRACK_BY_ID: dict[str, dict[str, str]] = {track["id"]: dict(track) for track in TRACK_DEFINITIONS}

FUTURE_EXTENSION_HOOKS: dict[str, list[dict[str, Any]]] = {
    "arrivals_today": [],
    "departures_today": [],
    "status_overrides": [],
    "vehicle_details": [],
    "filters": [],
}

GLEISPLAN_PDF_TRACE_SETTING_KEY = "pdf_trace"
DEFAULT_GLEISPLAN_PDF_TRACE_SETTINGS: dict[str, Any] = {
    "enabled": False,
    "opacity": 0.45,
    "x": 0.0,
    "y": 0.0,
    "scale_x": 1.0,
    "scale_y": 1.0,
    "rotation": 0.0,
    "hide_grid": False,
    "fade_foreground": False,
    "hide_labels": False,
}


DEFAULT_LAYOUT_ITEMS: tuple[dict[str, Any], ...] = (
    {"item_id": "GL12_NORD", "item_type": "track", "label": "GL 12", "title": "Nordbogen / Zufahrt", "x_pct": 7, "y_pct": 6.5, "w_pct": 12, "h_pct": 8, "rotation": 8, "color": "#dc2626", "sort_order": 10},
    {"item_id": "URD", "item_type": "track", "label": "URD", "title": "URD", "x_pct": 41, "y_pct": 13, "w_pct": 10, "h_pct": 7, "rotation": 7, "color": "#111827", "sort_order": 20},
    {"item_id": "GL12_OST", "item_type": "track", "label": "GL 12", "title": "Ostbogen / Ausfahrt", "x_pct": 72, "y_pct": 23, "w_pct": 12, "h_pct": 8, "rotation": 10, "color": "#dc2626", "sort_order": 30},
    {"item_id": "GL10", "item_type": "track", "label": "GL 10", "title": "Gleis 10", "x_pct": 27.5, "y_pct": 27, "w_pct": 10, "h_pct": 7, "rotation": 0, "color": "#dc2626", "sort_order": 40},
    {"item_id": "GL1A", "item_type": "track", "label": "GL 1a", "title": "Westliche Abstellung oben", "x_pct": 12.5, "y_pct": 33.5, "w_pct": 13, "h_pct": 7, "rotation": 0, "color": "#dc2626", "sort_order": 50},
    {"item_id": "GL1B", "item_type": "track", "label": "GL 1b", "title": "Westliche Abstellung unten", "x_pct": 10.4, "y_pct": 39.5, "w_pct": 13, "h_pct": 7, "rotation": 0, "color": "#dc2626", "sort_order": 60},
    {"item_id": "GL1", "item_type": "track", "label": "GL 1", "title": "Mittelgleis", "x_pct": 35.5, "y_pct": 39, "w_pct": 10, "h_pct": 7, "rotation": 0, "color": "#dc2626", "sort_order": 70},
    {"item_id": "GL2", "item_type": "track", "label": "GL 2", "title": "Gleis 2 / Tankstelle", "x_pct": 41.5, "y_pct": 44, "w_pct": 10, "h_pct": 7, "rotation": 0, "color": "#dc2626", "sort_order": 80},
    {"item_id": "ARA", "item_type": "track", "label": "ARA", "title": "ARA", "x_pct": 48, "y_pct": 47.5, "w_pct": 10, "h_pct": 7, "rotation": 0, "color": "#111827", "sort_order": 90},
    {"item_id": "GL3", "item_type": "track", "label": "GL 3", "title": "Gleis 3 / ARA", "x_pct": 56, "y_pct": 51.5, "w_pct": 10, "h_pct": 7, "rotation": 0, "color": "#111827", "sort_order": 100},
    {"item_id": "GL4_OST", "item_type": "track", "label": "GL 4", "title": "Ostgleis 4", "x_pct": 67, "y_pct": 57, "w_pct": 10, "h_pct": 8, "rotation": 0, "color": "#dc2626", "sort_order": 110},
    {"item_id": "GL5_OST", "item_type": "track", "label": "GL 5", "title": "Ostgleis 5", "x_pct": 67, "y_pct": 64, "w_pct": 10, "h_pct": 8, "rotation": 0, "color": "#dc2626", "sort_order": 120},
    {"item_id": "HALL_MAIN", "item_type": "hall", "label": "Werkstatt mit Gleishalle", "title": "Werkstatt mit Gleishalle", "x_pct": 23, "y_pct": 58, "w_pct": 36, "h_pct": 25, "rotation": 0, "color": "#d1d5db", "sort_order": 130},
    {"item_id": "BUILDING_NORTH", "item_type": "building", "label": "Gebaeude Nord", "title": "Gebaeude Nord", "x_pct": 17, "y_pct": 4, "w_pct": 26, "h_pct": 22, "rotation": 0, "color": "rgba(254,202,202,.62)", "sort_order": 200},
    {"item_id": "BUILDING_YARD", "item_type": "building", "label": "Werkstattumfeld", "title": "Werkstattumfeld", "x_pct": 33, "y_pct": 29, "w_pct": 30, "h_pct": 50, "rotation": 0, "color": "rgba(254,202,202,.62)", "sort_order": 210},
    {"item_id": "KALTLAGER", "item_type": "building", "label": "Kaltlager", "title": "Kaltlager", "x_pct": 4, "y_pct": 73, "w_pct": 8, "h_pct": 13, "rotation": -45, "color": "#d1d5db", "sort_order": 220},
    {"item_id": "TANK", "item_type": "building", "label": "WC / VE / Tankstelle", "title": "Tankstelle", "x_pct": 61.5, "y_pct": 43.5, "w_pct": 9.5, "h_pct": 3, "rotation": 0, "color": "#15803d", "sort_order": 230},
    {"item_id": "SW_A8", "item_type": "switch", "label": "A8 / A10", "title": "Weiche A8 / A10", "x_pct": 46, "y_pct": 43.4, "w_pct": 6, "h_pct": 3, "rotation": 0, "color": "#f59e0b", "sort_order": 300},
    {"item_id": "SW_A5", "item_type": "switch", "label": "A5 / A6", "title": "Weiche A5 / A6", "x_pct": 82, "y_pct": 60.5, "w_pct": 6, "h_pct": 3, "rotation": 0, "color": "#f59e0b", "sort_order": 310},
)

DEFAULT_CONNECTIONS: tuple[dict[str, Any], ...] = (
    {"source_item_id": "GL12_NORD", "target_item_id": "URD", "label": "Nordbogen", "connection_type": "track"},
    {"source_item_id": "URD", "target_item_id": "GL12_OST", "label": "GL12 Ost", "connection_type": "track"},
    {"source_item_id": "GL1A", "target_item_id": "GL1", "label": "GL1a-GL1", "connection_type": "track"},
    {"source_item_id": "GL1B", "target_item_id": "GL1", "label": "GL1b-GL1", "connection_type": "track"},
    {"source_item_id": "GL10", "target_item_id": "GL1", "label": "GL10-GL1", "connection_type": "track"},
    {"source_item_id": "GL1", "target_item_id": "GL2", "label": "A8", "connection_type": "track"},
    {"source_item_id": "GL2", "target_item_id": "ARA", "label": "ARA", "connection_type": "track"},
    {"source_item_id": "ARA", "target_item_id": "GL3", "label": "ARA-GL3", "connection_type": "track"},
    {"source_item_id": "GL3", "target_item_id": "GL4_OST", "label": "GL4", "connection_type": "track"},
    {"source_item_id": "GL3", "target_item_id": "GL5_OST", "label": "GL5", "connection_type": "track"},
    {"source_item_id": "GL4_OST", "target_item_id": "GL12_OST", "label": "Ostbogen", "connection_type": "track"},
    {"source_item_id": "GL5_OST", "target_item_id": "GL12_OST", "label": "A5", "connection_type": "track"},
    {"source_item_id": "HALL_MAIN", "target_item_id": "GL4_OST", "label": "Halle GL4", "connection_type": "track"},
    {"source_item_id": "HALL_MAIN", "target_item_id": "GL5_OST", "label": "Halle GL5", "connection_type": "track"},
)


def _layout_item_id(value: Any) -> str:
    raw = str(value or "").strip().upper()
    raw = re.sub(r"[^A-Z0-9_]+", "_", raw)
    raw = re.sub(r"_+", "_", raw).strip("_")
    return raw[:48]


def make_unique_gleisplan_item_id(db_exec: Callable[..., Any], prefix: str) -> str:
    ensure_gleisplan_layout_schema(db_exec)
    clean_prefix = _layout_item_id(prefix) or "OBJ"
    rows = db_exec("SELECT item_id FROM gleisplan_layout_items WHERE item_id LIKE ?;", (f"{clean_prefix}_%",), fetch=True) or []
    used = {
        str(_row_value(row, "item_id", 0) or "").strip().upper()
        for row in rows
    }
    for index in range(1, 10000):
        candidate = f"{clean_prefix}_{index:02d}"
        if candidate not in used:
            return candidate
    return f"{clean_prefix}_{len(used) + 1:04d}"[:48]


def make_gleisplan_item_id_for_type_label(db_exec: Callable[..., Any], *, item_type: str, label: str) -> str:
    ensure_gleisplan_layout_schema(db_exec)
    clean_type = str(item_type or "anchor").strip().lower()
    if clean_type == "track":
        clean_type = "anchor"
    prefix = LAYOUT_ITEM_ID_PREFIX_BY_TYPE.get(clean_type, _layout_item_id(clean_type) or "OBJEKT")
    label_slug = _layout_item_id(label) or "OHNE_BEZEICHNUNG"
    rows = db_exec(
        "SELECT item_id FROM gleisplan_layout_items WHERE item_id LIKE ?;",
        (f"{prefix}_%",),
        fetch=True,
    ) or []
    existing = {str(_row_value(row, "item_id", 0) or "").strip().upper() for row in rows}
    pattern = re.compile(rf"^{re.escape(prefix)}_(\d+)(?:_|$)")
    max_sequence = 0
    for item_id in existing:
        match = pattern.match(item_id)
        if match:
            max_sequence = max(max_sequence, _coerce_int(match.group(1), 0))
    sequence = max_sequence + 1
    for _ in range(10000):
        candidate = f"{prefix}_{sequence}_{label_slug}"[:48]
        if candidate not in existing:
            return candidate
        sequence += 1
    return f"{prefix}_{sequence}"[:48]


def _now_text(now_berlin: Callable[[], Any] | None = None) -> str:
    if callable(now_berlin):
        try:
            return now_berlin().isoformat(timespec="seconds")
        except Exception:
            pass
    return ""


def _hall_track_sort_key(area_code: str) -> tuple[int, int, str]:
    code = str(area_code or "").strip().upper()
    default_index = _DEFAULT_HALL_TRACK_ORDER.get(code)
    if default_index is not None:
        return (0, default_index, code)
    return (1, 9999, code.casefold())


def ordered_hall_track_codes(hall_tracks: dict[str, dict[str, Any]] | None = None) -> list[str]:
    if hall_tracks is None:
        codes = {str(area or "").strip().upper() for area in HALL_TRACKS}
    else:
        codes = {str(area or "").strip().upper() for area in hall_tracks.keys()}
    return sorted((code for code in codes if code), key=_hall_track_sort_key)


def build_hall_track_grid(hall_tracks: dict[str, dict[str, Any]] | None = None, *, columns: int = 2) -> tuple[tuple[str, ...], ...]:
    hall_tracks = hall_tracks or {}
    def grid_sort_key(code: str) -> tuple[int, int, str]:
        config = hall_tracks.get(code) or DEFAULT_HALL_TRACK_CONFIG.get(code, {})
        position = str(config.get("position_label") or HALL_TRACK_LABELS.get(code, "")).strip().casefold()
        if position in HALL_POSITION_ORDER:
            return (0, HALL_POSITION_ORDER[position], code)
        return (1, _hall_track_sort_key(code)[1], code)

    codes = sorted(ordered_hall_track_codes(hall_tracks), key=grid_sort_key)
    col_count = max(1, int(columns or 2))
    return tuple(tuple(codes[index : index + col_count]) for index in range(0, len(codes), col_count))


def ensure_gleisplan_assignment_schema(db_exec: Callable[..., Any]) -> None:
    db_exec(
        """
        CREATE TABLE IF NOT EXISTS gleisplan_assignments (
            track_id       TEXT PRIMARY KEY,
            vehicle_number TEXT NOT NULL,
            updated_at     TEXT
        );
        """,
        commit=True,
    )


def ensure_gleisplan_layout_schema(db_exec: Callable[..., Any]) -> None:
    ensure_gleisplan_assignment_schema(db_exec)
    db_exec(
        """
        CREATE TABLE IF NOT EXISTS gleisplan_layout_items (
            item_id    TEXT PRIMARY KEY,
            item_type  TEXT NOT NULL,
            label      TEXT NOT NULL,
            title      TEXT,
            x_pct      REAL NOT NULL DEFAULT 10,
            y_pct      REAL NOT NULL DEFAULT 10,
            w_pct      REAL NOT NULL DEFAULT 12,
            h_pct      REAL NOT NULL DEFAULT 8,
            rotation   REAL NOT NULL DEFAULT 0,
            color      TEXT,
            curve_radius REAL NOT NULL DEFAULT 0,
            switch_port2_x_ratio REAL NOT NULL DEFAULT 0,
            switch_port2_y_ratio REAL NOT NULL DEFAULT 0.28,
            switch_port3_x_ratio REAL NOT NULL DEFAULT 0.06,
            switch_port3_y_ratio REAL NOT NULL DEFAULT 1.35,
            sort_order INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT
        );
        """,
        commit=True,
    )
    try:
        db_exec("ALTER TABLE gleisplan_layout_items ADD COLUMN curve_radius REAL NOT NULL DEFAULT 0;", commit=True)
    except Exception:
        pass
    for column, default in (
        ("switch_port2_x_ratio", "0"),
        ("switch_port2_y_ratio", str(SWITCH_MAIN_RAIL_Y_RATIO)),
        ("switch_port3_x_ratio", str(SWITCH_BRANCH_PORT_X_RATIO)),
        ("switch_port3_y_ratio", str(SWITCH_BRANCH_PORT_Y_RATIO)),
    ):
        try:
            db_exec(
                f"ALTER TABLE gleisplan_layout_items ADD COLUMN {column} REAL NOT NULL DEFAULT {default};",
                commit=True,
            )
        except Exception:
            pass
    db_exec(
        """
        UPDATE gleisplan_layout_items
        SET w_pct=4.2, h_pct=2.0
        WHERE item_type='switch'
          AND ABS(COALESCE(w_pct, 0) - 12.0) < 0.001
          AND ABS(COALESCE(h_pct, 0) - 8.0) < 0.001;
        """,
        commit=True,
    )
    db_exec(
        """
        CREATE TABLE IF NOT EXISTS gleisplan_connections (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            source_item_id TEXT NOT NULL,
            target_item_id TEXT NOT NULL,
            source_port    TEXT,
            target_port    TEXT,
            label          TEXT,
            connection_type TEXT,
            curve_pct      REAL NOT NULL DEFAULT 0,
            path_points_json TEXT,
            route_json     TEXT,
            updated_at     TEXT
        );
        """,
        commit=True,
    )
    try:
        db_exec("ALTER TABLE gleisplan_connections ADD COLUMN curve_pct REAL NOT NULL DEFAULT 0;", commit=True)
    except Exception:
        pass
    try:
        db_exec("ALTER TABLE gleisplan_connections ADD COLUMN source_port TEXT;", commit=True)
    except Exception:
        pass
    try:
        db_exec("ALTER TABLE gleisplan_connections ADD COLUMN target_port TEXT;", commit=True)
    except Exception:
        pass
    try:
        db_exec("ALTER TABLE gleisplan_connections ADD COLUMN path_points_json TEXT;", commit=True)
    except Exception:
        pass
    try:
        db_exec("ALTER TABLE gleisplan_connections ADD COLUMN route_json TEXT;", commit=True)
    except Exception:
        pass
    db_exec(
        """
        CREATE TABLE IF NOT EXISTS gleisplan_settings (
            setting_key  TEXT PRIMARY KEY,
            setting_json TEXT NOT NULL,
            updated_at   TEXT
        );
        """,
        commit=True,
    )
    db_exec(
        """
        CREATE TABLE IF NOT EXISTS gleisplan_hall_tracks (
            area_code      TEXT PRIMARY KEY,
            track_label    TEXT NOT NULL,
            position_label TEXT,
            workshop_area  TEXT,
            sync_enabled   INTEGER NOT NULL DEFAULT 1,
            active         INTEGER NOT NULL DEFAULT 1,
            updated_at     TEXT
        );
        """,
        commit=True,
    )
    try:
        db_exec("ALTER TABLE gleisplan_hall_tracks ADD COLUMN active INTEGER NOT NULL DEFAULT 1;", commit=True)
    except Exception:
        pass


def ensure_gleisplan_hall_schema(db_exec: Callable[..., Any]) -> None:
    ensure_gleisplan_layout_schema(db_exec)


def _row_to_hall_track(row: Any) -> dict[str, Any]:
    area_code = str(_row_value(row, "area_code", 0) or "").strip().upper()
    default = DEFAULT_HALL_TRACK_CONFIG.get(area_code, {})
    return {
        "area_code": area_code,
        "track_label": str(_row_value(row, "track_label", 1) or default.get("track_label") or area_code).strip(),
        "position_label": str(_row_value(row, "position_label", 2) or default.get("position_label") or "").strip(),
        "workshop_area": str(_row_value(row, "workshop_area", 3) or default.get("workshop_area") or area_code).strip().upper(),
        "sync_enabled": bool(_coerce_int(_row_value(row, "sync_enabled", 4), 1)),
        "updated_at": str(_row_value(row, "updated_at", 5) or "").strip(),
        "active": bool(_coerce_int(_row_value(row, "active", 6), 1)),
    }


def load_gleisplan_hall_tracks(db_exec: Callable[..., Any]) -> dict[str, dict[str, Any]]:
    ensure_gleisplan_hall_schema(db_exec)
    _reconcile_hall_track_ids_from_labels(db_exec)
    rows = db_exec(
        """
        SELECT area_code, track_label, position_label, workshop_area, sync_enabled, updated_at, active
        FROM gleisplan_hall_tracks;
        """,
        fetch=True,
    ) or []
    out: dict[str, dict[str, Any]] = {}
    inactive: set[str] = set()
    for row in rows:
        config = _row_to_hall_track(row)
        area_code = str(config.get("area_code") or "").strip().upper()
        if not area_code:
            continue
        if not bool(config.get("active", True)):
            inactive.add(area_code)
            continue
        out[area_code] = config
    for area, config in DEFAULT_HALL_TRACK_CONFIG.items():
        if area not in out and area not in inactive:
            out[area] = dict(config)
    return out


def _reconcile_hall_track_ids_from_labels(db_exec: Callable[..., Any]) -> None:
    for _ in range(12):
        rows = db_exec(
            """
            SELECT area_code, track_label, position_label, workshop_area, sync_enabled, updated_at, active
            FROM gleisplan_hall_tracks
            WHERE active=1;
            """,
            fetch=True,
        ) or []
        changed = False
        for row in rows:
            config = _row_to_hall_track(row)
            area = str(config.get("area_code") or "").strip().upper()
            label_area = _layout_item_id(config.get("track_label"))
            if not area or not label_area or area == label_area:
                continue
            ok, _msg = save_gleisplan_hall_track(
                db_exec,
                area_code=area,
                track_label=str(config.get("track_label") or ""),
                position_label=str(config.get("position_label") or ""),
                workshop_area=str(config.get("workshop_area") or ""),
                sync_enabled=bool(config.get("sync_enabled", True)),
                updated_at=_now_text(),
            )
            if ok:
                changed = True
                break
        if not changed:
            return


def _rename_hall_track_references(db_exec: Callable[..., Any], *, old_area: str, new_area: str) -> None:
    if not old_area or not new_area or old_area == new_area:
        return
    db_exec(
        "UPDATE gleisplan_assignments SET track_id=? WHERE track_id=?;",
        (new_area, old_area),
        commit=True,
    )
    db_exec(
        """
        UPDATE gleisplan_connections
        SET source_port=?
        WHERE source_port=?
          AND source_item_id IN (SELECT item_id FROM gleisplan_layout_items WHERE item_type='hall');
        """,
        (new_area, old_area),
        commit=True,
    )
    db_exec(
        """
        UPDATE gleisplan_connections
        SET target_port=?
        WHERE target_port=?
          AND target_item_id IN (SELECT item_id FROM gleisplan_layout_items WHERE item_type='hall');
        """,
        (new_area, old_area),
        commit=True,
    )


def _deactivate_virtual_default_hall_track(
    db_exec: Callable[..., Any],
    *,
    area_code: str,
    updated_at: str,
) -> None:
    area = _layout_item_id(area_code)
    if area not in HALL_TRACKS:
        return
    default = DEFAULT_HALL_TRACK_CONFIG.get(area, {})
    db_exec(
        """
        INSERT INTO gleisplan_hall_tracks(area_code, track_label, position_label, workshop_area, sync_enabled, active, updated_at)
        VALUES (?, ?, ?, ?, ?, 0, ?)
        ON CONFLICT(area_code) DO UPDATE SET
            active=0,
            updated_at=excluded.updated_at;
        """,
        (
            area,
            str(default.get("track_label") or area),
            str(default.get("position_label") or ""),
            str(default.get("workshop_area") or area),
            1 if bool(default.get("sync_enabled", True)) else 0,
            updated_at,
        ),
        commit=True,
    )


def _fetch_hall_track_row(db_exec: Callable[..., Any], area_code: str) -> dict[str, Any] | None:
    area = _layout_item_id(area_code)
    if not area:
        return None
    row = db_exec(
        """
        SELECT area_code, track_label, position_label, workshop_area, sync_enabled, updated_at, active
        FROM gleisplan_hall_tracks
        WHERE area_code=?;
        """,
        (area,),
        fetchone=True,
    )
    return _row_to_hall_track(row) if row else None


def save_gleisplan_hall_track(
    db_exec: Callable[..., Any],
    *,
    area_code: str,
    track_label: str,
    position_label: str = "",
    workshop_area: str = "",
    sync_enabled: bool = True,
    updated_at: str = "",
) -> tuple[bool, str]:
    ensure_gleisplan_hall_schema(db_exec)
    old_area = _layout_item_id(area_code)
    if not old_area:
        return False, "Bitte einen eindeutigen Gleiscode eintragen."
    label = str(track_label or "").strip()
    if not label:
        return False, "Bitte einen Gleisnamen eintragen."
    area = _layout_item_id(label)
    if not area:
        return False, "Aus dem Gleisnamen konnte keine technische ID gebildet werden."
    if area != old_area:
        target_row = _fetch_hall_track_row(db_exec, area)
        if target_row is None and area in HALL_TRACKS:
            target_default = DEFAULT_HALL_TRACK_CONFIG.get(area, {})
            db_exec(
                """
                INSERT INTO gleisplan_hall_tracks(area_code, track_label, position_label, workshop_area, sync_enabled, active, updated_at)
                VALUES (?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(area_code) DO NOTHING;
                """,
                (
                    area,
                    old_area,
                    str(target_default.get("position_label") or ""),
                    old_area,
                    1 if bool(target_default.get("sync_enabled", True)) else 0,
                    updated_at,
                ),
                commit=True,
            )
            target_row = _fetch_hall_track_row(db_exec, area)
        if target_row and bool(target_row.get("active", True)):
            target_label_area = _layout_item_id(target_row.get("track_label"))
            if target_label_area != old_area:
                return False, f"Technische ID {area} existiert bereits."
            temp_area = _layout_item_id(f"TMP_{old_area}_{area}") or f"TMP_{old_area}_{area}"
            while _fetch_hall_track_row(db_exec, temp_area):
                temp_area = _layout_item_id(f"{temp_area}_X") or f"TMP_{old_area}_{area}_X"
            db_exec(
                "UPDATE gleisplan_hall_tracks SET area_code=? WHERE area_code=?;",
                (temp_area, area),
                commit=True,
            )
            _rename_hall_track_references(db_exec, old_area=area, new_area=temp_area)
            db_exec(
                "UPDATE gleisplan_hall_tracks SET area_code=? WHERE area_code=?;",
                (area, old_area),
                commit=True,
            )
            _rename_hall_track_references(db_exec, old_area=old_area, new_area=area)
            db_exec(
                "UPDATE gleisplan_hall_tracks SET area_code=? WHERE area_code=?;",
                (old_area, temp_area),
                commit=True,
            )
            _rename_hall_track_references(db_exec, old_area=temp_area, new_area=old_area)
        else:
            old_row = _fetch_hall_track_row(db_exec, old_area)
            if old_row and bool(old_row.get("active", True)):
                db_exec(
                    "UPDATE gleisplan_hall_tracks SET area_code=? WHERE area_code=?;",
                    (area, old_area),
                    commit=True,
                )
                _rename_hall_track_references(db_exec, old_area=old_area, new_area=area)
            if old_area in HALL_TRACKS:
                _deactivate_virtual_default_hall_track(db_exec, area_code=old_area, updated_at=updated_at)
    default = DEFAULT_HALL_TRACK_CONFIG.get(area) or DEFAULT_HALL_TRACK_CONFIG.get(old_area, {})
    db_exec(
        """
        INSERT INTO gleisplan_hall_tracks(area_code, track_label, position_label, workshop_area, sync_enabled, active, updated_at)
        VALUES (?, ?, ?, ?, ?, 1, ?)
        ON CONFLICT(area_code) DO UPDATE SET
            track_label=excluded.track_label,
            position_label=excluded.position_label,
            workshop_area=excluded.workshop_area,
            sync_enabled=excluded.sync_enabled,
            active=1,
            updated_at=excluded.updated_at;
        """,
        (
            area,
            label,
            str(position_label or default.get("position_label") or "").strip(),
            str(workshop_area or default.get("workshop_area") or area).strip().upper(),
            1 if sync_enabled else 0,
            updated_at,
        ),
        commit=True,
    )
    return True, "Hallengleis gespeichert."


def delete_gleisplan_hall_track(db_exec: Callable[..., Any], *, area_code: str) -> tuple[bool, str]:
    ensure_gleisplan_hall_schema(db_exec)
    area = _layout_item_id(area_code)
    if not area:
        return False, "Hallengleis nicht gefunden."
    if area in HALL_TRACKS:
        return False, "Standard-Hallengleise können nicht gelöscht werden."
    db_exec("DELETE FROM gleisplan_assignments WHERE track_id=?;", (area,), commit=True)
    db_exec("DELETE FROM gleisplan_hall_tracks WHERE area_code=?;", (area,), commit=True)
    return True, "Hallengleis gelöscht."


def seed_default_gleisplan_layout(db_exec: Callable[..., Any], *, updated_at: str = "") -> None:
    ensure_gleisplan_layout_schema(db_exec)
    row = db_exec("SELECT COUNT(*) AS c FROM gleisplan_layout_items;", fetchone=True)
    try:
        count = int(row["c"] if hasattr(row, "keys") else row[0])
    except Exception:
        count = 0
    if count > 0:
        return

    apply_gleisplan_layout_template(
        db_exec,
        template_key=EBERSWALDE_LAGEPLAN_TEMPLATE_KEY,
        updated_at=updated_at,
        clear_assignments=False,
    )


def list_gleisplan_layout_templates() -> dict[str, str]:
    return {
        str(key): str(value.get("label") or key)
        for key, value in GLEISPLAN_LAYOUT_TEMPLATES.items()
    }


def apply_gleisplan_layout_template(
    db_exec: Callable[..., Any],
    *,
    template_key: str = EBERSWALDE_LAGEPLAN_TEMPLATE_KEY,
    updated_at: str = "",
    clear_assignments: bool = True,
) -> tuple[bool, str]:
    ensure_gleisplan_layout_schema(db_exec)
    clean_key = str(template_key or EBERSWALDE_LAGEPLAN_TEMPLATE_KEY).strip() or EBERSWALDE_LAGEPLAN_TEMPLATE_KEY
    template = GLEISPLAN_LAYOUT_TEMPLATES.get(clean_key)
    if not template:
        return False, "Gleisplan-Vorlage nicht gefunden."
    validation = validate_gleisplan_template(template)
    for line in format_gleisplan_template_validation(validation):
        print(line)
    if not validation.get("ok"):
        return False, "Gleisplan-Vorlage ist fachlich inkonsistent. Details stehen im Server-Log."

    if clear_assignments:
        db_exec("DELETE FROM gleisplan_assignments WHERE track_id LIKE 'CONN_%';", commit=True)
    db_exec("DELETE FROM gleisplan_connections;", commit=True)
    db_exec("DELETE FROM gleisplan_layout_items;", commit=True)

    for hall_track in template.get("hall_tracks") or ():
        save_gleisplan_hall_track(
            db_exec,
            area_code=str(hall_track.get("area_code") or ""),
            track_label=str(hall_track.get("track_label") or ""),
            position_label=str(hall_track.get("position_label") or ""),
            workshop_area=str(hall_track.get("workshop_area") or ""),
            sync_enabled=bool(hall_track.get("sync_enabled", True)),
            updated_at=updated_at,
        )
    for item in template.get("layout_items") or ():
        clean_item = dict(item)
        clean_type = str(clean_item.get("item_type") or "anchor").strip().lower()
        if clean_type == "track":
            clean_type = "anchor"
        db_exec(
            """
            INSERT INTO gleisplan_layout_items(
                item_id, item_type, label, title, x_pct, y_pct, w_pct, h_pct, rotation, color, curve_radius,
                switch_port2_x_ratio, switch_port2_y_ratio, switch_port3_x_ratio, switch_port3_y_ratio,
                sort_order, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                _layout_item_id(clean_item.get("item_id")),
                clean_type if clean_type in LAYOUT_ITEM_TYPES else "anchor",
                str(clean_item.get("label") or clean_item.get("item_id") or "").strip(),
                str(clean_item.get("title") or "").strip(),
                max(0.0, min(100.0, _coerce_float(clean_item.get("x_pct"), 10))),
                max(0.0, min(100.0, _coerce_float(clean_item.get("y_pct"), 10))),
                max(2.0, min(100.0, _coerce_float(clean_item.get("w_pct"), 12))),
                max(1.0 if clean_type == "street" else 2.0, min(100.0, _coerce_float(clean_item.get("h_pct"), 8))),
                _coerce_float(clean_item.get("rotation"), 0),
                str(clean_item.get("color") or "").strip(),
                max(0.0, min(100.0, _coerce_float(clean_item.get("curve_radius"), 0))),
                _coerce_switch_port_ratio(clean_item.get("switch_port2_x_ratio"), 0.0),
                _coerce_switch_port_ratio(clean_item.get("switch_port2_y_ratio"), SWITCH_MAIN_RAIL_Y_RATIO),
                _coerce_switch_port_ratio(clean_item.get("switch_port3_x_ratio"), SWITCH_BRANCH_PORT_X_RATIO),
                _coerce_switch_port_ratio(clean_item.get("switch_port3_y_ratio"), SWITCH_BRANCH_PORT_Y_RATIO),
                _coerce_int(clean_item.get("sort_order"), 1000),
                updated_at,
            ),
            commit=True,
        )
    for connection in template.get("connections") or ():
        clean_connection = dict(connection)
        route_json = _serialize_connection_route(clean_connection.get("route"))
        if route_json:
            path_points = []
        else:
            path_points = clean_connection.get("path_points")
            if path_points is None:
                path_points = clean_connection.get("points")
        db_exec(
            """
            INSERT INTO gleisplan_connections(source_item_id, target_item_id, source_port, target_port, label, connection_type, curve_pct, path_points_json, route_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                _layout_item_id(clean_connection.get("source_item_id")),
                _layout_item_id(clean_connection.get("target_item_id")),
                str(clean_connection.get("source_port") or "").strip(),
                str(clean_connection.get("target_port") or "").strip(),
                str(clean_connection.get("label") or "").strip(),
                str(clean_connection.get("connection_type") or "track").strip().lower() or "track",
                max(-100.0, min(100.0, _coerce_float(clean_connection.get("curve_pct"), 0))),
                _serialize_connection_path_points(path_points),
                route_json,
                updated_at,
            ),
            commit=True,
        )

    label = str(template.get("label") or clean_key)
    return True, f"Vorlage {label} geladen."


def apply_eberswalde_pdf_trace_geometry(
    db_exec: Callable[..., Any],
    *,
    updated_at: str = "",
) -> tuple[bool, str]:
    ensure_gleisplan_layout_schema(db_exec)
    template = GLEISPLAN_LAYOUT_TEMPLATES.get(EBERSWALDE_LAGEPLAN_TEMPLATE_KEY)
    if not template:
        return False, "Eberswalde-Geometrie nicht gefunden."
    validation = validate_gleisplan_template(template)
    for line in format_gleisplan_template_validation(validation):
        print(line)
    if not validation.get("ok"):
        return False, "Eberswalde-Geometrie ist fachlich inkonsistent. Details stehen im Server-Log."

    item_count = 0
    connection_updates = 0
    connection_inserts = 0
    for item in template.get("layout_items") or ():
        clean_item = dict(item)
        clean_type = str(clean_item.get("item_type") or "anchor").strip().lower()
        if clean_type == "track":
            clean_type = "anchor"
        item_id = _layout_item_id(clean_item.get("item_id"))
        if not item_id:
            continue
        db_exec(
            """
            INSERT INTO gleisplan_layout_items(
                item_id, item_type, label, title, x_pct, y_pct, w_pct, h_pct, rotation, color, curve_radius,
                switch_port2_x_ratio, switch_port2_y_ratio, switch_port3_x_ratio, switch_port3_y_ratio,
                sort_order, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(item_id) DO UPDATE SET
                item_type=excluded.item_type,
                label=excluded.label,
                title=excluded.title,
                x_pct=excluded.x_pct,
                y_pct=excluded.y_pct,
                w_pct=excluded.w_pct,
                h_pct=excluded.h_pct,
                rotation=excluded.rotation,
                color=excluded.color,
                curve_radius=excluded.curve_radius,
                switch_port2_x_ratio=excluded.switch_port2_x_ratio,
                switch_port2_y_ratio=excluded.switch_port2_y_ratio,
                switch_port3_x_ratio=excluded.switch_port3_x_ratio,
                switch_port3_y_ratio=excluded.switch_port3_y_ratio,
                sort_order=excluded.sort_order,
                updated_at=excluded.updated_at;
            """,
            (
                item_id,
                clean_type if clean_type in LAYOUT_ITEM_TYPES else "anchor",
                str(clean_item.get("label") or clean_item.get("item_id") or "").strip(),
                str(clean_item.get("title") or "").strip(),
                max(0.0, min(100.0, _coerce_float(clean_item.get("x_pct"), 10))),
                max(0.0, min(100.0, _coerce_float(clean_item.get("y_pct"), 10))),
                max(2.0, min(100.0, _coerce_float(clean_item.get("w_pct"), 12))),
                max(1.0 if clean_type == "street" else 2.0, min(100.0, _coerce_float(clean_item.get("h_pct"), 8))),
                _coerce_float(clean_item.get("rotation"), 0),
                str(clean_item.get("color") or "").strip(),
                max(0.0, min(100.0, _coerce_float(clean_item.get("curve_radius"), 0))),
                _coerce_switch_port_ratio(clean_item.get("switch_port2_x_ratio"), 0.0),
                _coerce_switch_port_ratio(clean_item.get("switch_port2_y_ratio"), SWITCH_MAIN_RAIL_Y_RATIO),
                _coerce_switch_port_ratio(clean_item.get("switch_port3_x_ratio"), SWITCH_BRANCH_PORT_X_RATIO),
                _coerce_switch_port_ratio(clean_item.get("switch_port3_y_ratio"), SWITCH_BRANCH_PORT_Y_RATIO),
                _coerce_int(clean_item.get("sort_order"), 1000),
                updated_at,
            ),
            commit=True,
        )
        item_count += 1

    for connection in template.get("connections") or ():
        clean_connection = dict(connection)
        source = _layout_item_id(clean_connection.get("source_item_id"))
        target = _layout_item_id(clean_connection.get("target_item_id"))
        source_port = str(clean_connection.get("source_port") or "").strip()
        target_port = str(clean_connection.get("target_port") or "").strip()
        route_json = _serialize_connection_route(clean_connection.get("route"))
        if not source or not target:
            continue
        existing = db_exec(
            """
            SELECT id
            FROM gleisplan_connections
            WHERE source_item_id=?
              AND target_item_id=?
              AND COALESCE(source_port, '')=?
              AND COALESCE(target_port, '')=?
            ORDER BY id ASC
            LIMIT 1;
            """,
            (source, target, source_port, target_port),
            fetchone=True,
        )
        if existing:
            db_exec(
                """
                UPDATE gleisplan_connections
                SET label=?, connection_type=?, curve_pct=0, path_points_json='', route_json=?, updated_at=?
                WHERE id=?;
                """,
                (
                    str(clean_connection.get("label") or "").strip(),
                    str(clean_connection.get("connection_type") or "track").strip().lower() or "track",
                    route_json,
                    updated_at,
                    int(_row_value(existing, "id", 0) or 0),
                ),
                commit=True,
            )
            connection_updates += 1
        else:
            db_exec(
                """
                INSERT INTO gleisplan_connections(source_item_id, target_item_id, source_port, target_port, label, connection_type, curve_pct, path_points_json, route_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 0, '', ?, ?);
                """,
                (
                    source,
                    target,
                    source_port,
                    target_port,
                    str(clean_connection.get("label") or "").strip(),
                    str(clean_connection.get("connection_type") or "track").strip().lower() or "track",
                    route_json,
                    updated_at,
                ),
                commit=True,
            )
            connection_inserts += 1

    return (
        True,
        f"Eberswalde-Geometrie aktualisiert: {item_count} Objekte, {connection_updates} Verbindungen aktualisiert, {connection_inserts} ergaenzt.",
    )


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _coerce_bool_setting(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    raw = str(value or "").strip().casefold()
    if raw in {"1", "true", "yes", "ja", "on"}:
        return True
    if raw in {"0", "false", "no", "nein", "off"}:
        return False
    return bool(default)


def normalize_gleisplan_pdf_trace_settings(settings: Any) -> dict[str, Any]:
    raw = settings if isinstance(settings, dict) else {}
    merged = dict(DEFAULT_GLEISPLAN_PDF_TRACE_SETTINGS)
    merged.update(raw)
    return {
        "enabled": _coerce_bool_setting(merged.get("enabled"), False),
        "opacity": max(0.2, min(0.8, _coerce_float(merged.get("opacity"), 0.45))),
        "x": max(-100.0, min(100.0, _coerce_float(merged.get("x"), 0.0))),
        "y": max(-100.0, min(100.0, _coerce_float(merged.get("y"), 0.0))),
        "scale_x": max(0.5, min(2.0, _coerce_float(merged.get("scale_x"), 1.0))),
        "scale_y": max(0.5, min(2.0, _coerce_float(merged.get("scale_y"), 1.0))),
        "rotation": max(-15.0, min(15.0, _coerce_float(merged.get("rotation"), 0.0))),
        "hide_grid": _coerce_bool_setting(merged.get("hide_grid"), False),
        "fade_foreground": _coerce_bool_setting(merged.get("fade_foreground"), False),
        "hide_labels": _coerce_bool_setting(merged.get("hide_labels"), False),
    }


def load_gleisplan_pdf_trace_settings(db_exec: Callable[..., Any]) -> dict[str, Any]:
    ensure_gleisplan_layout_schema(db_exec)
    row = db_exec(
        "SELECT setting_json FROM gleisplan_settings WHERE setting_key=?;",
        (GLEISPLAN_PDF_TRACE_SETTING_KEY,),
        fetchone=True,
    )
    if not row:
        return dict(DEFAULT_GLEISPLAN_PDF_TRACE_SETTINGS)
    raw = str(_row_value(row, "setting_json", 0) or "").strip()
    if not raw:
        return dict(DEFAULT_GLEISPLAN_PDF_TRACE_SETTINGS)
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = {}
    return normalize_gleisplan_pdf_trace_settings(parsed)


def save_gleisplan_pdf_trace_settings(
    db_exec: Callable[..., Any],
    settings: Any,
    *,
    updated_at: str = "",
) -> tuple[bool, str]:
    ensure_gleisplan_layout_schema(db_exec)
    clean_settings = normalize_gleisplan_pdf_trace_settings(settings)
    db_exec(
        """
        INSERT INTO gleisplan_settings(setting_key, setting_json, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(setting_key) DO UPDATE SET
            setting_json=excluded.setting_json,
            updated_at=excluded.updated_at;
        """,
        (
            GLEISPLAN_PDF_TRACE_SETTING_KEY,
            json.dumps(clean_settings, ensure_ascii=True, sort_keys=True),
            updated_at,
        ),
        commit=True,
    )
    return True, "PDF-Kalibrierung gespeichert."


def reset_gleisplan_pdf_trace_settings(
    db_exec: Callable[..., Any],
    *,
    updated_at: str = "",
) -> tuple[bool, str]:
    return save_gleisplan_pdf_trace_settings(
        db_exec,
        dict(DEFAULT_GLEISPLAN_PDF_TRACE_SETTINGS),
        updated_at=updated_at,
    )


def _coerce_switch_port_ratio(value: Any, default: float) -> float:
    return max(SWITCH_PORT_RATIO_MIN, min(SWITCH_PORT_RATIO_MAX, _coerce_float(value, default)))


def _row_to_layout_item(row: Any) -> dict[str, Any]:
    item_id = str(_row_value(row, "item_id", 0) or "").strip().upper()
    item_type = str(_row_value(row, "item_type", 1) or "track").strip().lower()
    if item_type == "track":
        item_type = "anchor"
    if item_type not in LAYOUT_ITEM_TYPES:
        item_type = "anchor"
    return {
        "item_id": item_id,
        "id": item_id,
        "item_type": item_type,
        "label": str(_row_value(row, "label", 2) or item_id).strip(),
        "title": str(_row_value(row, "title", 3) or "").strip(),
        "x_pct": _coerce_float(_row_value(row, "x_pct", 4), 10),
        "y_pct": _coerce_float(_row_value(row, "y_pct", 5), 10),
        "w_pct": _coerce_float(_row_value(row, "w_pct", 6), 12),
        "h_pct": _coerce_float(_row_value(row, "h_pct", 7), 8),
        "rotation": _coerce_float(_row_value(row, "rotation", 8), 0),
        "color": str(_row_value(row, "color", 9) or "").strip(),
        "curve_radius": _coerce_float(_row_value(row, "curve_radius", 10), 0),
        "switch_port2_x_ratio": _coerce_switch_port_ratio(_row_value(row, "switch_port2_x_ratio", 11), 0.0),
        "switch_port2_y_ratio": _coerce_switch_port_ratio(
            _row_value(row, "switch_port2_y_ratio", 12), SWITCH_MAIN_RAIL_Y_RATIO
        ),
        "switch_port3_x_ratio": _coerce_switch_port_ratio(
            _row_value(row, "switch_port3_x_ratio", 13), SWITCH_BRANCH_PORT_X_RATIO
        ),
        "switch_port3_y_ratio": _coerce_switch_port_ratio(
            _row_value(row, "switch_port3_y_ratio", 14), SWITCH_BRANCH_PORT_Y_RATIO
        ),
        "sort_order": _coerce_int(_row_value(row, "sort_order", 15), 0),
        "updated_at": str(_row_value(row, "updated_at", 16) or "").strip(),
    }


def load_gleisplan_layout_items(db_exec: Callable[..., Any], *, seed_defaults: bool = True) -> list[dict[str, Any]]:
    ensure_gleisplan_layout_schema(db_exec)
    if seed_defaults:
        seed_default_gleisplan_layout(db_exec)
    rows = db_exec(
        """
        SELECT item_id, item_type, label, title, x_pct, y_pct, w_pct, h_pct, rotation, color, curve_radius,
               switch_port2_x_ratio, switch_port2_y_ratio, switch_port3_x_ratio, switch_port3_y_ratio,
               sort_order, updated_at
        FROM gleisplan_layout_items
        ORDER BY sort_order ASC, item_id ASC;
        """,
        fetch=True,
    ) or []
    return [_row_to_layout_item(row) for row in rows if str(_row_value(row, "item_id", 0) or "").strip()]


def layout_items_by_id(layout_items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item.get("item_id") or "").strip().upper(): dict(item) for item in layout_items}


def _connection_assignment_track_id(connection_id: Any) -> str:
    try:
        value = int(connection_id)
    except Exception:
        value = 0
    return f"CONN_{value}" if value > 0 else ""


def _parse_connection_path_points(value: Any) -> list[dict[str, float]]:
    text = str(value or "").strip()
    if not text:
        return []
    try:
        raw_points = json.loads(text)
    except Exception:
        return []
    if not isinstance(raw_points, list):
        return []
    points: list[dict[str, float]] = []
    for raw in raw_points[:12]:
        if not isinstance(raw, dict):
            continue
        points.append(
            {
                "x_pct": max(0.0, min(100.0, _coerce_float(raw.get("x_pct", raw.get("x")), 0))),
                "y_pct": max(0.0, min(100.0, _coerce_float(raw.get("y_pct", raw.get("y")), 0))),
            }
        )
    return points


def _serialize_connection_path_points(points: list[dict[str, Any]] | None) -> str:
    clean: list[dict[str, float]] = []
    for raw in points or []:
        if not isinstance(raw, dict):
            continue
        clean.append(
            {
                "x_pct": round(max(0.0, min(100.0, _coerce_float(raw.get("x_pct", raw.get("x")), 0))), 3),
                "y_pct": round(max(0.0, min(100.0, _coerce_float(raw.get("y_pct", raw.get("y")), 0))), 3),
            }
        )
        if len(clean) >= 12:
            break
    return json.dumps(clean, ensure_ascii=True, separators=(",", ":")) if clean else ""


def _clean_route_point(value: Any) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    anchor = str(value.get("anchor") or "").strip().lower()
    if anchor in {"from", "to"}:
        out: dict[str, Any] = {
            "anchor": anchor,
            "name": str(value.get("name") or "").strip() or ("from" if anchor == "from" else "to"),
            "dx_pct": round(_coerce_float(value.get("dx_pct", value.get("dx")), 0), 3),
            "dy_pct": round(_coerce_float(value.get("dy_pct", value.get("dy")), 0), 3),
        }
        if "x_pct" in value or "x" in value:
            out["x_pct"] = round(max(0.0, min(100.0, _coerce_float(value.get("x_pct", value.get("x")), 0))), 3)
        if "y_pct" in value or "y" in value:
            out["y_pct"] = round(max(0.0, min(100.0, _coerce_float(value.get("y_pct", value.get("y")), 0))), 3)
        return out
    if "x_pct" in value or "x" in value:
        x_value = value.get("x_pct", value.get("x"))
    else:
        x_value = None
    if "y_pct" in value or "y" in value:
        y_value = value.get("y_pct", value.get("y"))
    else:
        y_value = None
    if x_value is None or y_value is None:
        return None
    return {
        "x_pct": round(max(0.0, min(100.0, _coerce_float(x_value, 0))), 3),
        "y_pct": round(max(0.0, min(100.0, _coerce_float(y_value, 0))), 3),
    }


def _is_route_anchor_point(point: dict[str, Any] | None) -> bool:
    if not isinstance(point, dict):
        return False
    return str(point.get("anchor") or "").strip().lower() in {"from", "to"}


def _parse_route_path_endpoint(d: str, *, first: bool) -> dict[str, float] | None:
    numbers = re.findall(r"-?\d+(?:\.\d+)?", str(d or ""))
    if len(numbers) < 2:
        return None
    offset = 0 if first else len(numbers) - 2
    return _clean_route_point({"x": numbers[offset], "y": numbers[offset + 1]})


def _parse_connection_route(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        raw_route = dict(value)
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except Exception:
            return None
        if not isinstance(parsed, dict):
            return None
        raw_route = parsed
    route_type = str(raw_route.get("type") or "").strip().lower()
    d = str(raw_route.get("d") or "").strip()
    points = [
        point
        for point in (_clean_route_point(raw) for raw in (raw_route.get("points") or [])[:64])
        if point is not None
    ]
    if not route_type:
        route_type = "path" if d else "polyline"
    if route_type not in {"path", "polyline", "bezier", "smooth"}:
        route_type = "path" if d else "polyline"
    if route_type == "smooth":
        raw_route["smooth"] = True
    if route_type == "path" and not d:
        route_type = "polyline"
    if route_type in {"polyline", "smooth"} and len(points) < 2:
        return None
    start = _clean_route_point(raw_route.get("start"))
    end = _clean_route_point(raw_route.get("end"))
    if not start:
        start = points[0] if points else _parse_route_path_endpoint(d, first=True)
    if not end:
        end = points[-1] if points else _parse_route_path_endpoint(d, first=False)
    if not start or not end:
        return None
    label_position = _clean_route_point(raw_route.get("label_position") or raw_route.get("label"))
    route: dict[str, Any] = {
        "type": route_type,
        "start": start,
        "end": end,
    }
    if d:
        route["d"] = d
    if points:
        route["points"] = points
    if bool(raw_route.get("smooth")) or route_type == "smooth":
        route["smooth"] = True
    if label_position:
        route["label_position"] = label_position
    return route


def _serialize_connection_route(route: dict[str, Any] | None) -> str:
    clean_route = _parse_connection_route(route)
    if not clean_route:
        return ""
    return json.dumps(clean_route, ensure_ascii=True, separators=(",", ":"))


def _route_points(route: dict[str, Any] | None) -> list[tuple[float, float]]:
    clean_route = _parse_connection_route(route)
    if not clean_route:
        return []
    points = [
        (_coerce_float(point.get("x_pct"), 0), _coerce_float(point.get("y_pct"), 0))
        for point in clean_route.get("points") or []
        if isinstance(point, dict)
        and point.get("x_pct") is not None
        and point.get("y_pct") is not None
    ]
    if len(points) >= 2:
        return points
    start = clean_route.get("start") or {}
    end = clean_route.get("end") or {}
    return [
        (_coerce_float(start.get("x_pct"), 0), _coerce_float(start.get("y_pct"), 0)),
        (_coerce_float(end.get("x_pct"), 0), _coerce_float(end.get("y_pct"), 0)),
    ]


def _resolve_route_anchor_point(
    route_point: dict[str, Any],
    *,
    item: dict[str, Any],
    other_item: dict[str, Any],
    port: str,
    hall_tracks: dict[str, dict[str, Any]] | None = None,
) -> tuple[float, float]:
    if route_point.get("dx_pct") is not None and route_point.get("dy_pct") is not None:
        return (
            _coerce_float(item.get("x_pct"), 0) + _coerce_float(route_point.get("dx_pct"), 0),
            _coerce_float(item.get("y_pct"), 0) + _coerce_float(route_point.get("dy_pct"), 0),
        )
    return _connection_point_for_item(item, other_item, port=port, hall_tracks=hall_tracks)


def _resolve_connection_route(
    route: dict[str, Any] | None,
    *,
    source_item: dict[str, Any],
    target_item: dict[str, Any],
    source_port: str,
    target_port: str,
    hall_tracks: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    clean_route = _parse_connection_route(route)
    if not clean_route:
        return None
    resolved = dict(clean_route)
    resolved_points: list[dict[str, Any]] = []
    for point in clean_route.get("points") or []:
        if not isinstance(point, dict):
            continue
        out = dict(point)
        anchor = str(point.get("anchor") or "").strip().lower()
        if anchor == "from":
            x_pct, y_pct = _resolve_route_anchor_point(
                point,
                item=source_item,
                other_item=target_item,
                port=source_port,
                hall_tracks=hall_tracks,
            )
            out["x_pct"] = round(max(0.0, min(100.0, x_pct)), 3)
            out["y_pct"] = round(max(0.0, min(100.0, y_pct)), 3)
        elif anchor == "to":
            x_pct, y_pct = _resolve_route_anchor_point(
                point,
                item=target_item,
                other_item=source_item,
                port=target_port,
                hall_tracks=hall_tracks,
            )
            out["x_pct"] = round(max(0.0, min(100.0, x_pct)), 3)
            out["y_pct"] = round(max(0.0, min(100.0, y_pct)), 3)
        resolved_points.append(out)
    if resolved_points:
        resolved["points"] = resolved_points
        resolved["start"] = resolved_points[0]
        resolved["end"] = resolved_points[-1]
    return resolved


def _route_point_at(route: dict[str, Any] | None, fraction: float) -> tuple[float, float]:
    points = _route_points(route)
    if not points:
        return 0.0, 0.0
    if len(points) == 1:
        return points[0]
    clean_t = max(0.0, min(1.0, float(fraction)))
    lengths: list[float] = []
    total = 0.0
    for start, end in zip(points, points[1:]):
        length = math.sqrt(((end[0] - start[0]) ** 2) + ((end[1] - start[1]) ** 2))
        lengths.append(length)
        total += length
    if total <= 0.000001:
        return points[0]
    target = clean_t * total
    walked = 0.0
    for index, length in enumerate(lengths):
        start = points[index]
        end = points[index + 1]
        if walked + length >= target or index == len(lengths) - 1:
            local_t = 0.0 if length <= 0.000001 else (target - walked) / length
            return (
                start[0] + ((end[0] - start[0]) * local_t),
                start[1] + ((end[1] - start[1]) * local_t),
            )
        walked += length
    return points[-1]


def save_gleisplan_layout_item(
    db_exec: Callable[..., Any],
    *,
    item_id: str,
    item_type: str,
    label: str,
    title: str = "",
    x_pct: float = 10,
    y_pct: float = 10,
    w_pct: float = 12,
    h_pct: float = 8,
    rotation: float = 0,
    color: str = "",
    curve_radius: float = 0,
    switch_port2_x_ratio: float = 0.0,
    switch_port2_y_ratio: float = SWITCH_MAIN_RAIL_Y_RATIO,
    switch_port3_x_ratio: float = SWITCH_BRANCH_PORT_X_RATIO,
    switch_port3_y_ratio: float = SWITCH_BRANCH_PORT_Y_RATIO,
    sort_order: int = 1000,
    updated_at: str = "",
    allow_update: bool = True,
) -> tuple[bool, str]:
    ensure_gleisplan_layout_schema(db_exec)
    clean_id = _layout_item_id(item_id)
    clean_type = str(item_type or "track").strip().lower()
    if clean_type == "track":
        clean_type = "anchor"
    if clean_type not in LAYOUT_ITEM_TYPES:
        return False, "Unbekannter Objekttyp."
    clean_label = str(label or "").strip()
    if not clean_id:
        return False, "Bitte eine ID eintragen."
    if not clean_label:
        return False, "Bitte eine Bezeichnung eintragen."
    if not allow_update:
        existing = db_exec("SELECT item_id FROM gleisplan_layout_items WHERE item_id=?;", (clean_id,), fetchone=True)
        if existing:
            return False, "Diese ID ist bereits vorhanden. Bitte eine andere ID verwenden."
    db_exec(
        """
        INSERT INTO gleisplan_layout_items(
            item_id, item_type, label, title, x_pct, y_pct, w_pct, h_pct, rotation, color, curve_radius,
            switch_port2_x_ratio, switch_port2_y_ratio, switch_port3_x_ratio, switch_port3_y_ratio,
            sort_order, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(item_id) DO UPDATE SET
            item_type=excluded.item_type,
            label=excluded.label,
            title=excluded.title,
            x_pct=excluded.x_pct,
            y_pct=excluded.y_pct,
            w_pct=excluded.w_pct,
            h_pct=excluded.h_pct,
            rotation=excluded.rotation,
            color=excluded.color,
            curve_radius=excluded.curve_radius,
            switch_port2_x_ratio=excluded.switch_port2_x_ratio,
            switch_port2_y_ratio=excluded.switch_port2_y_ratio,
            switch_port3_x_ratio=excluded.switch_port3_x_ratio,
            switch_port3_y_ratio=excluded.switch_port3_y_ratio,
            sort_order=excluded.sort_order,
            updated_at=excluded.updated_at;
        """,
        (
            clean_id,
            clean_type,
            clean_label,
            str(title or "").strip(),
            max(0.0, min(100.0, _coerce_float(x_pct, 10))),
            max(0.0, min(100.0, _coerce_float(y_pct, 10))),
            max(2.0, min(100.0, _coerce_float(w_pct, 12))),
            max(1.0 if clean_type == "street" else 2.0, min(100.0, _coerce_float(h_pct, 8))),
            _coerce_float(rotation, 0),
            str(color or "").strip(),
            max(0.0, min(100.0, _coerce_float(curve_radius, 0))),
            _coerce_switch_port_ratio(switch_port2_x_ratio, 0.0),
            _coerce_switch_port_ratio(switch_port2_y_ratio, SWITCH_MAIN_RAIL_Y_RATIO),
            _coerce_switch_port_ratio(switch_port3_x_ratio, SWITCH_BRANCH_PORT_X_RATIO),
            _coerce_switch_port_ratio(switch_port3_y_ratio, SWITCH_BRANCH_PORT_Y_RATIO),
            _coerce_int(sort_order, 1000),
            updated_at,
        ),
        commit=True,
    )
    if clean_type == "street":
        _merge_overlapping_gleisplan_streets(db_exec, anchor_item_id=clean_id, updated_at=updated_at)
    return True, "Gleisplan-Objekt gespeichert."


def update_gleisplan_layout_item_position(
    db_exec: Callable[..., Any],
    *,
    item_id: str,
    x_pct: float,
    y_pct: float,
    updated_at: str = "",
) -> tuple[bool, str]:
    clean_id = _layout_item_id(item_id)
    if not clean_id:
        return False, "Objekt nicht gefunden."
    row = db_exec("SELECT item_id, item_type FROM gleisplan_layout_items WHERE item_id=?;", (clean_id,), fetchone=True)
    if not row:
        return False, "Objekt nicht gefunden."
    db_exec(
        """
        UPDATE gleisplan_layout_items
        SET x_pct=?, y_pct=?, updated_at=?
        WHERE item_id=?;
        """,
        (
            max(0.0, min(100.0, _coerce_float(x_pct, 10))),
            max(0.0, min(100.0, _coerce_float(y_pct, 10))),
            updated_at,
            clean_id,
        ),
        commit=True,
    )
    if str(_row_value(row, "item_type", 1) or "").strip().lower() == "street":
        _merge_overlapping_gleisplan_streets(db_exec, anchor_item_id=clean_id, updated_at=updated_at)
    return True, "Position gespeichert."


def update_gleisplan_layout_item_size(
    db_exec: Callable[..., Any],
    *,
    item_id: str,
    w_pct: float,
    h_pct: float | None = None,
    updated_at: str = "",
) -> tuple[bool, str]:
    clean_id = _layout_item_id(item_id)
    if not clean_id:
        return False, "Objekt nicht gefunden."
    row = db_exec(
        "SELECT item_id, item_type, h_pct FROM gleisplan_layout_items WHERE item_id=?;",
        (clean_id,),
        fetchone=True,
    )
    if not row:
        return False, "Objekt nicht gefunden."
    current_h = _coerce_float(_row_value(row, "h_pct", 2), 3)
    new_h = current_h if h_pct is None else _coerce_float(h_pct, current_h)
    item_type = str(_row_value(row, "item_type", 1) or "").strip().lower()
    db_exec(
        """
        UPDATE gleisplan_layout_items
        SET w_pct=?, h_pct=?, updated_at=?
        WHERE item_id=?;
        """,
        (
            max(2.0, min(100.0, _coerce_float(w_pct, 12))),
            max(1.0 if item_type == "street" else 2.0, min(100.0, new_h)),
            updated_at,
            clean_id,
        ),
        commit=True,
    )
    if item_type == "street":
        _merge_overlapping_gleisplan_streets(db_exec, anchor_item_id=clean_id, updated_at=updated_at)
    return True, "Größe gespeichert."


def update_gleisplan_layout_item_geometry(
    db_exec: Callable[..., Any],
    *,
    item_id: str,
    w_pct: float | None = None,
    h_pct: float | None = None,
    rotation: float | None = None,
    curve_radius: float | None = None,
    switch_port2_x_ratio: float | None = None,
    switch_port2_y_ratio: float | None = None,
    switch_port3_x_ratio: float | None = None,
    switch_port3_y_ratio: float | None = None,
    updated_at: str = "",
) -> tuple[bool, str]:
    clean_id = _layout_item_id(item_id)
    if not clean_id:
        return False, "Objekt nicht gefunden."
    row = db_exec(
        """
        SELECT item_id, item_type, w_pct, h_pct, rotation, curve_radius,
               switch_port2_x_ratio, switch_port2_y_ratio, switch_port3_x_ratio, switch_port3_y_ratio
        FROM gleisplan_layout_items
        WHERE item_id=?;
        """,
        (clean_id,),
        fetchone=True,
    )
    if not row:
        return False, "Objekt nicht gefunden."
    item_type = str(_row_value(row, "item_type", 1) or "").strip().lower()
    new_w = _coerce_float(w_pct, _row_value(row, "w_pct", 2)) if w_pct is not None else _coerce_float(_row_value(row, "w_pct", 2), 12)
    new_h = _coerce_float(h_pct, _row_value(row, "h_pct", 3)) if h_pct is not None else _coerce_float(_row_value(row, "h_pct", 3), 8)
    new_rotation = _coerce_float(rotation, _row_value(row, "rotation", 4)) if rotation is not None else _coerce_float(_row_value(row, "rotation", 4), 0)
    new_curve = _coerce_float(curve_radius, _row_value(row, "curve_radius", 5)) if curve_radius is not None else _coerce_float(_row_value(row, "curve_radius", 5), 0)
    new_port2_x = (
        _coerce_switch_port_ratio(switch_port2_x_ratio, _row_value(row, "switch_port2_x_ratio", 6))
        if switch_port2_x_ratio is not None
        else _coerce_switch_port_ratio(_row_value(row, "switch_port2_x_ratio", 6), 0.0)
    )
    new_port2_y = (
        _coerce_switch_port_ratio(switch_port2_y_ratio, _row_value(row, "switch_port2_y_ratio", 7))
        if switch_port2_y_ratio is not None
        else _coerce_switch_port_ratio(_row_value(row, "switch_port2_y_ratio", 7), SWITCH_MAIN_RAIL_Y_RATIO)
    )
    new_port3_x = (
        _coerce_switch_port_ratio(switch_port3_x_ratio, _row_value(row, "switch_port3_x_ratio", 8))
        if switch_port3_x_ratio is not None
        else _coerce_switch_port_ratio(_row_value(row, "switch_port3_x_ratio", 8), SWITCH_BRANCH_PORT_X_RATIO)
    )
    new_port3_y = (
        _coerce_switch_port_ratio(switch_port3_y_ratio, _row_value(row, "switch_port3_y_ratio", 9))
        if switch_port3_y_ratio is not None
        else _coerce_switch_port_ratio(_row_value(row, "switch_port3_y_ratio", 9), SWITCH_BRANCH_PORT_Y_RATIO)
    )
    db_exec(
        """
        UPDATE gleisplan_layout_items
        SET w_pct=?, h_pct=?, rotation=?, curve_radius=?,
            switch_port2_x_ratio=?, switch_port2_y_ratio=?,
            switch_port3_x_ratio=?, switch_port3_y_ratio=?,
            updated_at=?
        WHERE item_id=?;
        """,
        (
            max(2.0, min(100.0, new_w)),
            max(1.0 if item_type == "street" else 2.0, min(100.0, new_h)),
            new_rotation,
            max(0.0, min(100.0, new_curve)),
            new_port2_x,
            new_port2_y,
            new_port3_x,
            new_port3_y,
            updated_at,
            clean_id,
        ),
        commit=True,
    )
    if item_type == "street":
        _merge_overlapping_gleisplan_streets(db_exec, anchor_item_id=clean_id, updated_at=updated_at)
    return True, "Geometrie gespeichert."


def delete_gleisplan_layout_item(db_exec: Callable[..., Any], *, item_id: str) -> tuple[bool, str]:
    ensure_gleisplan_layout_schema(db_exec)
    clean_id = _layout_item_id(item_id)
    if clean_id in HALL_TRACKS:
        return False, "Hallengleise können nicht gelöscht werden."
    if not clean_id:
        return False, "Objekt nicht gefunden."
    connection_rows = db_exec(
        "SELECT id FROM gleisplan_connections WHERE source_item_id=? OR target_item_id=?;",
        (clean_id, clean_id),
        fetch=True,
    ) or []
    for row in connection_rows:
        connection_track_id = _connection_assignment_track_id(_row_value(row, "id", 0))
        if connection_track_id:
            db_exec("DELETE FROM gleisplan_assignments WHERE track_id=?;", (connection_track_id,), commit=True)
    db_exec("DELETE FROM gleisplan_connections WHERE source_item_id=? OR target_item_id=?;", (clean_id, clean_id), commit=True)
    db_exec("DELETE FROM gleisplan_assignments WHERE track_id=?;", (clean_id,), commit=True)
    db_exec("DELETE FROM gleisplan_layout_items WHERE item_id=?;", (clean_id,), commit=True)
    return True, "Gleisplan-Objekt gelöscht."


def _angle_delta_180(a: float, b: float) -> float:
    return abs(((float(a) - float(b) + 90.0) % 180.0) - 90.0)


def _center_of_item(item: dict[str, Any]) -> tuple[float, float]:
    return (
        _coerce_float(item.get("x_pct"), 0) + _coerce_float(item.get("w_pct"), 0) / 2.0,
        _coerce_float(item.get("y_pct"), 0) + _coerce_float(item.get("h_pct"), 0) / 2.0,
    )


def _item_axis(item: dict[str, Any]) -> tuple[float, float]:
    angle = math.radians(_coerce_float(item.get("rotation"), 0))
    return math.cos(angle), math.sin(angle)


def _local_point_to_board(item: dict[str, Any], local_x: float, local_y: float) -> tuple[float, float]:
    x = _coerce_float(item.get("x_pct"), 0)
    y = _coerce_float(item.get("y_pct"), 0)
    w = _coerce_float(item.get("w_pct"), 0)
    h = _coerce_float(item.get("h_pct"), 0)
    cx = x + (w / 2.0)
    cy = y + (h / 2.0)
    angle = math.radians(_coerce_float(item.get("rotation"), 0))
    aspect = GLEISPLAN_RENDER_ASPECT if GLEISPLAN_RENDER_ASPECT > 0 else 1.0
    dx = (local_x - (w / 2.0)) * aspect
    dy = local_y - (h / 2.0)
    rotated_x = (dx * math.cos(angle)) - (dy * math.sin(angle))
    rotated_y = (dx * math.sin(angle)) + (dy * math.cos(angle))
    return (
        cx + (rotated_x / aspect),
        cy + rotated_y,
    )


def _nearest_point(points: list[tuple[float, float]], target: tuple[float, float]) -> tuple[float, float]:
    if not points:
        return target
    tx, ty = target
    return min(points, key=lambda point: ((point[0] - tx) ** 2) + ((point[1] - ty) ** 2))


def _switch_connection_point_for_target(item: dict[str, Any], port: str, target: tuple[float, float]) -> tuple[float, float]:
    points = _switch_connection_points(item, port)
    if len(points) < 2:
        return _nearest_point(points, target)
    return points[0]


def _switch_connection_lead_point(item: dict[str, Any], port: str) -> tuple[float, float] | None:
    points = _switch_connection_points(item, port)
    if len(points) < 2:
        return None
    selected, opposite = points[0], points[1]
    dx = selected[0] - opposite[0]
    dy = selected[1] - opposite[1]
    length = math.sqrt((dx * dx) + (dy * dy))
    if length <= 0.000001:
        return None
    lead = min(1.35, length * 0.42)
    return selected[0] + ((dx / length) * lead), selected[1] + ((dy / length) * lead)


def _switch_connection_points(item: dict[str, Any], port: str) -> list[tuple[float, float]]:
    w = max(0.0, _coerce_float(item.get("w_pct"), 0))
    h = max(0.0, _coerce_float(item.get("h_pct"), 0))
    main_y = h * SWITCH_MAIN_RAIL_Y_RATIO
    port1 = (w, main_y)
    port2 = (
        w * _coerce_switch_port_ratio(item.get("switch_port2_x_ratio"), 0.0),
        h * _coerce_switch_port_ratio(item.get("switch_port2_y_ratio"), SWITCH_MAIN_RAIL_Y_RATIO),
    )
    heel = (
        port2[0] + ((port1[0] - port2[0]) * SWITCH_BRANCH_HEEL_X_RATIO),
        port2[1] + ((port1[1] - port2[1]) * SWITCH_BRANCH_HEEL_X_RATIO),
    )
    port3 = (
        w * _coerce_switch_port_ratio(item.get("switch_port3_x_ratio"), SWITCH_BRANCH_PORT_X_RATIO),
        h * _coerce_switch_port_ratio(item.get("switch_port3_y_ratio"), SWITCH_BRANCH_PORT_Y_RATIO),
    )
    clean_port = str(port or "1").strip()
    if clean_port == "2":
        return [
            _local_point_to_board(item, port2[0], port2[1]),
            _local_point_to_board(item, port1[0], port1[1]),
        ]
    if clean_port == "3":
        return [
            _local_point_to_board(item, port3[0], port3[1]),
            _local_point_to_board(item, heel[0], heel[1]),
        ]
    return [
        _local_point_to_board(item, port1[0], port1[1]),
        _local_point_to_board(item, port2[0], port2[1]),
    ]


def _hall_connection_point_for_port(
    item: dict[str, Any],
    port: str,
    *,
    target: tuple[float, float] | None = None,
    hall_tracks: dict[str, dict[str, Any]] | None = None,
) -> tuple[float, float] | None:
    clean_port = str(port or "").strip().upper()
    if not clean_port:
        return None
    grid = build_hall_track_grid(hall_tracks)
    if not grid:
        return None
    rows = len(grid)
    columns = max((len(row) for row in grid), default=0)
    if rows <= 0 or columns <= 0:
        return None
    for row_index, row in enumerate(grid):
        for column_index, area_code in enumerate(row):
            if str(area_code or "").strip().upper() != clean_port:
                continue
            width = max(0.0, _coerce_float(item.get("w_pct"), 0))
            height = max(0.0, _coerce_float(item.get("h_pct"), 0))
            cell_top = row_index * (height / rows)
            cell_bottom = (row_index + 1) * (height / rows)
            cell_mid_y = (cell_top + cell_bottom) / 2.0
            candidates = [(0.0, cell_mid_y), (width, cell_mid_y)]
            board_candidates = [_local_point_to_board(item, x, y) for x, y in candidates]
            if target is None:
                return board_candidates[0]
            tx, ty = target
            return min(board_candidates, key=lambda point: ((point[0] - tx) ** 2) + ((point[1] - ty) ** 2))
    return None


def _connection_point_for_item(
    item: dict[str, Any],
    other_item: dict[str, Any],
    *,
    port: str = "",
    hall_tracks: dict[str, dict[str, Any]] | None = None,
) -> tuple[float, float]:
    item_type = str(item.get("item_type") or "").strip().lower()
    cx, cy = _center_of_item(item)
    ox, oy = _center_of_item(other_item)
    if item_type == "hall":
        hall_point = _hall_connection_point_for_port(item, port, target=(ox, oy), hall_tracks=hall_tracks)
        if hall_point is not None:
            return hall_point
    if item_type == "switch":
        return _switch_connection_point_for_target(item, port, (ox, oy))
    if item_type == "buffer_stop":
        width = max(0.0, _coerce_float(item.get("w_pct"), 0))
        height = max(0.0, _coerce_float(item.get("h_pct"), 0))
        extension = min(BUFFER_STOP_CONNECTION_EXTENSION_PCT, height * 0.06)
        return _local_point_to_board(item, width / 2.0, height + extension)
    ux, uy = _item_axis(item)
    dot = ((ox - cx) * ux) + ((oy - cy) * uy)
    side = 1.0 if dot >= 0 else -1.0
    width = _coerce_float(item.get("w_pct"), 0)
    if item_type == "switch":
        offset = width * 0.50
    elif item_type == "track":
        offset = width * 0.50
    else:
        offset = width * 0.50
    return cx + (ux * offset * side), cy + (uy * offset * side)


def _street_centerline(item: dict[str, Any]) -> tuple[float, float, float, float, float, float]:
    x = _coerce_float(item.get("x_pct"), 0)
    y = _coerce_float(item.get("y_pct"), 0)
    w = _coerce_float(item.get("w_pct"), 0)
    h = _coerce_float(item.get("h_pct"), 0)
    ux, uy = _item_axis(item)
    start_x = x
    start_y = y + h / 2.0
    return start_x, start_y, start_x + (ux * w), start_y + (uy * w), ux, uy


def _connection_ports_for_item(
    item: dict[str, Any],
    *,
    hall_tracks: dict[str, dict[str, Any]] | None = None,
) -> tuple[str, ...]:
    item_type = str((item or {}).get("item_type") or "").strip().lower()
    if item_type == "switch":
        return SWITCH_CONNECTION_PORTS
    if item_type == "hall":
        ports = tuple(ordered_hall_track_codes(hall_tracks))
        return ports or HALL_TRACKS
    if item_type in SINGLE_CONNECTION_PORT_TYPES:
        return ("1",)
    return ("",)


def _normalize_connection_port(
    item: dict[str, Any],
    value: Any,
    *,
    hall_tracks: dict[str, dict[str, Any]] | None = None,
) -> str:
    ports = _connection_ports_for_item(item, hall_tracks=hall_tracks)
    if ports == ("",):
        return ""
    raw = str(value or "").strip()
    if raw in ports:
        return raw
    return ""


def _used_connection_ports(
    db_exec: Callable[..., Any],
    *,
    item_id: str,
    exclude_connection_id: int | None = None,
) -> set[str]:
    clean_id = _layout_item_id(item_id)
    if not clean_id:
        return set()
    rows = db_exec(
        """
        SELECT id, source_item_id, target_item_id, source_port, target_port
        FROM gleisplan_connections
        WHERE source_item_id=? OR target_item_id=?;
        """,
        (clean_id, clean_id),
        fetch=True,
    ) or []
    used: set[str] = set()
    excluded = int(exclude_connection_id or 0)
    for row in rows:
        row_id = _coerce_int(_row_value(row, "id", 0), 0)
        if excluded and row_id == excluded:
            continue
        source_id = str(_row_value(row, "source_item_id", 1) or "").strip().upper()
        if source_id == clean_id:
            used.add(str(_row_value(row, "source_port", 3) or "").strip())
            continue
        used.add(str(_row_value(row, "target_port", 4) or "").strip())
    return used


def _resolve_connection_port(
    db_exec: Callable[..., Any],
    *,
    item: dict[str, Any],
    other_item: dict[str, Any] | None = None,
    requested_port: Any,
    exclude_connection_id: int | None = None,
    hall_tracks: dict[str, dict[str, Any]] | None = None,
) -> tuple[bool, str, str]:
    ports = _connection_ports_for_item(item, hall_tracks=hall_tracks)
    if ports == ("",):
        return True, "", ""
    item_label = str(item.get("label") or item.get("item_id") or "Objekt").strip()
    requested = _normalize_connection_port(item, requested_port, hall_tracks=hall_tracks)
    used = _used_connection_ports(
        db_exec,
        item_id=str(item.get("item_id") or ""),
        exclude_connection_id=exclude_connection_id,
    )
    if "" in used:
        used.update(port for port in ports[:1] if port)
    if requested:
        if requested in used:
            return False, requested, f"{item_label}: Linie {requested} ist bereits verbunden."
        return True, requested, ""
    if str(item.get("item_type") or "").strip().lower() == "switch" and other_item:
        other_center = _center_of_item(other_item)
        free_ports = [port for port in ports if port not in used]
        if free_ports:
            return True, min(
                free_ports,
                key=lambda port: (
                    (_switch_connection_points(item, port)[0][0] - other_center[0]) ** 2
                    + (_switch_connection_points(item, port)[0][1] - other_center[1]) ** 2
                ),
            ), ""
    for port in ports:
        if port not in used:
            return True, port, ""
    return False, "", f"{item_label}: alle Linien sind bereits verbunden."


def _repair_switch_connection_ports(db_exec: Callable[..., Any], items: dict[str, dict[str, Any]]) -> None:
    switch_ids = {
        item_id
        for item_id, item in items.items()
        if str(item.get("item_type") or "").strip().lower() == "switch"
    }
    if not switch_ids:
        return
    rows = db_exec(
        """
        SELECT id, source_item_id, target_item_id, source_port, target_port
        FROM gleisplan_connections
        WHERE source_item_id IN (SELECT item_id FROM gleisplan_layout_items WHERE item_type='switch')
           OR target_item_id IN (SELECT item_id FROM gleisplan_layout_items WHERE item_type='switch');
        """,
        fetch=True,
    ) or []
    sides_by_switch: dict[str, list[dict[str, Any]]] = {switch_id: [] for switch_id in switch_ids}
    for row in rows:
        connection_id = _coerce_int(_row_value(row, "id", 0), 0)
        source_id = str(_row_value(row, "source_item_id", 1) or "").strip().upper()
        target_id = str(_row_value(row, "target_item_id", 2) or "").strip().upper()
        if connection_id <= 0:
            continue
        if source_id in switch_ids and target_id in items:
            sides_by_switch[source_id].append(
                {
                    "connection_id": connection_id,
                    "column": "source_port",
                    "current_port": str(_row_value(row, "source_port", 3) or "").strip(),
                    "other_item": items[target_id],
                }
            )
        if target_id in switch_ids and source_id in items:
            sides_by_switch[target_id].append(
                {
                    "connection_id": connection_id,
                    "column": "target_port",
                    "current_port": str(_row_value(row, "target_port", 4) or "").strip(),
                    "other_item": items[source_id],
                }
            )

    for switch_id, sides in sides_by_switch.items():
        if not sides:
            continue
        switch_item = items.get(switch_id) or {}
        current_port_counts: dict[str, int] = {}
        for side in sides:
            current_port = str(side.get("current_port") or "").strip()
            if current_port in SWITCH_CONNECTION_PORTS:
                current_port_counts[current_port] = current_port_counts.get(current_port, 0) + 1

        assigned_ports: set[str] = {
            str(side.get("current_port") or "").strip()
            for side in sides
            if current_port_counts.get(str(side.get("current_port") or "").strip(), 0) == 1
        }
        remaining = [
            side
            for side in sides
            if current_port_counts.get(str(side.get("current_port") or "").strip(), 0) != 1
        ]
        assignments: list[tuple[int, str, str]] = []
        while remaining:
            candidates: list[tuple[float, int, str]] = []
            for side_index, side in enumerate(remaining):
                other_center = _center_of_item(side["other_item"])
                for port in SWITCH_CONNECTION_PORTS:
                    if port in assigned_ports:
                        continue
                    endpoint = _switch_connection_points(switch_item, port)[0]
                    distance = ((endpoint[0] - other_center[0]) ** 2) + ((endpoint[1] - other_center[1]) ** 2)
                    keep_penalty = 0.0 if str(side.get("current_port") or "") == port else 0.0001
                    candidates.append((distance + keep_penalty, side_index, port))
            if not candidates:
                break
            _score, side_index, port = min(candidates, key=lambda item: item[0])
            side = remaining.pop(side_index)
            assigned_ports.add(port)
            if str(side.get("current_port") or "") != port:
                assignments.append((int(side["connection_id"]), str(side["column"]), port))
        for connection_id, column, port in assignments:
            if column not in {"source_port", "target_port"}:
                continue
            db_exec(
                f"UPDATE gleisplan_connections SET {column}=? WHERE id=?;",
                (port, connection_id),
                commit=True,
            )


def connection_port_options_for_item(
    item: dict[str, Any] | None,
    *,
    hall_tracks: dict[str, dict[str, Any]] | None = None,
) -> dict[str, str]:
    item = item or {}
    ports = _connection_ports_for_item(item, hall_tracks=hall_tracks)
    if ports == ("",):
        return {"": "Automatisch"}
    if str(item.get("item_type") or "").strip().lower() == "hall":
        options: dict[str, str] = {}
        for port in ports:
            config = (hall_tracks or {}).get(port) or DEFAULT_HALL_TRACK_CONFIG.get(port, {})
            technical_label = str(port or "").strip()
            track_label = str(config.get("track_label") or port).strip()
            label = technical_label if track_label.upper() == technical_label.upper() else f"{technical_label} ({track_label})"
            position = str(config.get("position_label") or HALL_TRACK_LABELS.get(port, "")).strip()
            options[port] = f"{label} - {position}" if position else label
        return options
    return {"": "Automatisch (nächste freie Linie)"} | {port: f"Linie {port}" for port in ports}


def _path_point_tuple(point: dict[str, Any]) -> tuple[float, float]:
    return _coerce_float(point.get("x_pct"), 0), _coerce_float(point.get("y_pct"), 0)


def _catmull_rom_point(points: list[tuple[float, float]], fraction: float) -> tuple[float, float]:
    if not points:
        return 0.0, 0.0
    if len(points) == 1:
        return points[0]
    t = max(0.0, min(1.0, float(fraction)))
    segments = len(points) - 1
    raw_index = t * segments
    index = min(segments - 1, int(math.floor(raw_index)))
    local_t = raw_index - index
    p0 = points[index - 1] if index > 0 else points[index]
    p1 = points[index]
    p2 = points[index + 1]
    p3 = points[index + 2] if index + 2 < len(points) else p2
    tt = local_t * local_t
    ttt = tt * local_t
    return (
        0.5
        * (
            (2.0 * p1[0])
            + (-p0[0] + p2[0]) * local_t
            + (2.0 * p0[0] - 5.0 * p1[0] + 4.0 * p2[0] - p3[0]) * tt
            + (-p0[0] + 3.0 * p1[0] - 3.0 * p2[0] + p3[0]) * ttt
        ),
        0.5
        * (
            (2.0 * p1[1])
            + (-p0[1] + p2[1]) * local_t
            + (2.0 * p0[1] - 5.0 * p1[1] + 4.0 * p2[1] - p3[1]) * tt
            + (-p0[1] + 3.0 * p1[1] - 3.0 * p2[1] + p3[1]) * ttt
        ),
    )


def _quadratic_connection_point(
    start: tuple[float, float],
    control: tuple[float, float],
    end: tuple[float, float],
    fraction: float,
) -> tuple[float, float]:
    t = max(0.0, min(1.0, float(fraction)))
    inv = 1.0 - t
    return (
        (inv * inv * start[0]) + (2.0 * inv * t * control[0]) + (t * t * end[0]),
        (inv * inv * start[1]) + (2.0 * inv * t * control[1]) + (t * t * end[1]),
    )


def _segment_intersection_params(
    p: tuple[float, float],
    r: tuple[float, float],
    q: tuple[float, float],
    s: tuple[float, float],
) -> tuple[float, float] | None:
    cross = r[0] * s[1] - r[1] * s[0]
    if abs(cross) < 0.000001:
        return None
    qmp = (q[0] - p[0], q[1] - p[1])
    t = (qmp[0] * s[1] - qmp[1] * s[0]) / cross
    u = (qmp[0] * r[1] - qmp[1] * r[0]) / cross
    return t, u


def _point_segment_distance(point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]) -> float:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length_sq = (dx * dx) + (dy * dy)
    if length_sq <= 0.000001:
        return math.sqrt(((point[0] - start[0]) ** 2) + ((point[1] - start[1]) ** 2))
    t = max(0.0, min(1.0, (((point[0] - start[0]) * dx) + ((point[1] - start[1]) * dy)) / length_sq))
    px = start[0] + (dx * t)
    py = start[1] + (dy * t)
    return math.sqrt(((point[0] - px) ** 2) + ((point[1] - py) ** 2))


def _segment_distance(
    a0: tuple[float, float],
    a1: tuple[float, float],
    b0: tuple[float, float],
    b1: tuple[float, float],
) -> float:
    ar = (a1[0] - a0[0], a1[1] - a0[1])
    bs = (b1[0] - b0[0], b1[1] - b0[1])
    intersection = _segment_intersection_params(a0, ar, b0, bs)
    if intersection is not None:
        t, u = intersection
        if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
            return 0.0
    return min(
        _point_segment_distance(a0, b0, b1),
        _point_segment_distance(a1, b0, b1),
        _point_segment_distance(b0, a0, a1),
        _point_segment_distance(b1, a0, a1),
    )


def _ensure_gleisplan_street_connection(
    db_exec: Callable[..., Any],
    *,
    source_item_id: str,
    target_item_id: str,
    updated_at: str = "",
) -> None:
    source = _layout_item_id(source_item_id)
    target = _layout_item_id(target_item_id)
    if not source or not target or source == target:
        return
    existing = db_exec(
        """
        SELECT id FROM gleisplan_connections
        WHERE (
                source_item_id=? AND target_item_id=?
                AND COALESCE(source_port, '')=? AND COALESCE(target_port, '')=?
              )
           OR (
                source_item_id=? AND target_item_id=?
                AND COALESCE(source_port, '')=? AND COALESCE(target_port, '')=?
              )
        LIMIT 1;
        """,
        (
            source,
            target,
            clean_source_port,
            clean_target_port,
            target,
            source,
            clean_target_port,
            clean_source_port,
        ),
        fetchone=True,
    )
    if existing:
        return
    db_exec(
        """
        INSERT INTO gleisplan_connections(source_item_id, target_item_id, source_port, target_port, label, connection_type, curve_pct, path_points_json, route_json, updated_at)
        VALUES (?, ?, '', '', '', 'street', 0, '', '', ?);
        """,
        (source, target, updated_at),
        commit=True,
    )


def _merge_overlapping_gleisplan_streets(
    db_exec: Callable[..., Any],
    *,
    anchor_item_id: str,
    updated_at: str = "",
) -> None:
    clean_anchor = _layout_item_id(anchor_item_id)
    if not clean_anchor:
        return
    rows = db_exec(
        """
        SELECT item_id, item_type, label, title, x_pct, y_pct, w_pct, h_pct, rotation, color, curve_radius,
               switch_port2_x_ratio, switch_port2_y_ratio, switch_port3_x_ratio, switch_port3_y_ratio,
               sort_order, updated_at
        FROM gleisplan_layout_items
        WHERE item_type='street';
        """,
        fetch=True,
    ) or []
    streets = [_row_to_layout_item(row) for row in rows]
    anchor = next((item for item in streets if item.get("item_id") == clean_anchor), None)
    if not anchor:
        return

    ax0, ay0, ax1, ay1, ux, uy = _street_centerline(anchor)
    px, py = -uy, ux
    anchor_rotation = _coerce_float(anchor.get("rotation"), 0)
    anchor_height = _coerce_float(anchor.get("h_pct"), 3)
    min_t = 0.0
    max_t = _coerce_float(anchor.get("w_pct"), 0)
    merged_ids: list[str] = []
    merged_height = anchor_height

    for street in streets:
        sid = str(street.get("item_id") or "").strip().upper()
        if sid == clean_anchor:
            continue
        sx0, sy0, sx1, sy1, _sux, _suy = _street_centerline(street)
        angle_delta = _angle_delta_180(anchor_rotation, _coerce_float(street.get("rotation"), 0))
        other_height = _coerce_float(street.get("h_pct"), anchor_height)
        if angle_delta > 8.0:
            continue
        sx0, sy0, sx1, sy1, _sux, _suy = _street_centerline(street)
        t0 = ((sx0 - ax0) * ux) + ((sy0 - ay0) * uy)
        t1 = ((sx1 - ax0) * ux) + ((sy1 - ay0) * uy)
        n0 = ((sx0 - ax0) * px) + ((sy0 - ay0) * py)
        n1 = ((sx1 - ax0) * px) + ((sy1 - ay0) * py)
        other_min = min(t0, t1)
        other_max = max(t0, t1)
        gap = max(other_min - max_t, min_t - other_max, 0.0)
        other_height = _coerce_float(street.get("h_pct"), anchor_height)
        tolerance = max(anchor_height, other_height) + 1.5
        if gap > 1.5 or max(abs(n0), abs(n1)) > tolerance:
            continue
        min_t = min(min_t, other_min)
        max_t = max(max_t, other_max)
        merged_height = max(merged_height, other_height)
        merged_ids.append(sid)

    if not merged_ids:
        return

    new_start_x = ax0 + (ux * min_t)
    new_start_y = ay0 + (uy * min_t)
    new_width = max(2.0, max_t - min_t)
    db_exec(
        """
        UPDATE gleisplan_layout_items
        SET x_pct=?, y_pct=?, w_pct=?, h_pct=?, updated_at=?
        WHERE item_id=?;
        """,
        (
            max(0.0, min(100.0, new_start_x)),
            max(0.0, min(100.0, new_start_y - (merged_height / 2.0))),
            min(100.0, new_width),
            max(1.0, min(100.0, merged_height)),
            updated_at,
            clean_anchor,
        ),
        commit=True,
    )
    for merged_id in merged_ids:
        db_exec("DELETE FROM gleisplan_connections WHERE source_item_id=? OR target_item_id=?;", (merged_id, merged_id), commit=True)
        db_exec("DELETE FROM gleisplan_layout_items WHERE item_id=?;", (merged_id,), commit=True)


def _row_to_connection(
    row: Any,
    items: dict[str, dict[str, Any]],
    *,
    hall_tracks: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    source = str(_row_value(row, "source_item_id", 1) or "").strip().upper()
    target = str(_row_value(row, "target_item_id", 2) or "").strip().upper()
    connection_id = _coerce_int(_row_value(row, "id", 0), 0)
    source_item = items.get(source) or {}
    target_item = items.get(target) or {}
    source_port = str(_row_value(row, "source_port", 3) or "").strip()
    target_port = str(_row_value(row, "target_port", 4) or "").strip()
    x1, y1 = _connection_point_for_item(source_item, target_item, port=source_port, hall_tracks=hall_tracks)
    x2, y2 = _connection_point_for_item(target_item, source_item, port=target_port, hall_tracks=hall_tracks)
    source_lead = (
        _switch_connection_lead_point(source_item, source_port)
        if str(source_item.get("item_type") or "").strip().lower() == "switch"
        else None
    )
    target_lead = (
        _switch_connection_lead_point(target_item, target_port)
        if str(target_item.get("item_type") or "").strip().lower() == "switch"
        else None
    )
    dx = x2 - x1
    dy = y2 - y1
    length_pct = max(0.0, math.sqrt(dx * dx + dy * dy))
    curve_pct = max(-100.0, min(100.0, _coerce_float(_row_value(row, "curve_pct", 7), 0)))
    if length_pct > 0:
        normal_x = -dy / length_pct
        normal_y = dx / length_pct
    else:
        normal_x = 0.0
        normal_y = -1.0
    control_x = ((x1 + x2) / 2.0) + (normal_x * curve_pct)
    control_y = ((y1 + y2) / 2.0) + (normal_y * curve_pct)
    path_points = _parse_connection_path_points(_row_value(row, "path_points_json", 8))
    route_raw = _parse_connection_route(_row_value(row, "route_json", 9))
    route = _resolve_connection_route(
        route_raw,
        source_item=source_item,
        target_item=target_item,
        source_port=source_port,
        target_port=target_port,
        hall_tracks=hall_tracks,
    )
    if route:
        start = route.get("start") or {}
        end = route.get("end") or {}
        x1 = _coerce_float(start.get("x_pct"), x1)
        y1 = _coerce_float(start.get("y_pct"), y1)
        x2 = _coerce_float(end.get("x_pct"), x2)
        y2 = _coerce_float(end.get("y_pct"), y2)
        source_lead = None
        target_lead = None
        dx = x2 - x1
        dy = y2 - y1
        length_pct = max(0.0, math.sqrt(dx * dx + dy * dy))
        control_x = (x1 + x2) / 2.0
        control_y = (y1 + y2) / 2.0
        label_position = route.get("label_position") or {}
        if label_position:
            label_x = _coerce_float(label_position.get("x_pct"), x1)
            label_y = _coerce_float(label_position.get("y_pct"), y1)
        else:
            label_x, label_y = _route_point_at(route, 0.5)
    elif path_points:
        label_x, label_y = _catmull_rom_point([(x1, y1), *[_path_point_tuple(point) for point in path_points], (x2, y2)], 0.5)
    else:
        label_x, label_y = _quadratic_connection_point((x1, y1), (control_x, control_y), (x2, y2), 0.5)
    return {
        "id": connection_id,
        "source_item_id": source,
        "target_item_id": target,
        "source_port": source_port,
        "target_port": target_port,
        "label": str(_row_value(row, "label", 5) or "").strip(),
        "connection_type": str(_row_value(row, "connection_type", 6) or "track").strip().lower() or "track",
        "curve_pct": curve_pct,
        "path_points": path_points,
        "points": [{"x": point["x_pct"], "y": point["y_pct"]} for point in path_points],
        "path_points_json": _serialize_connection_path_points(path_points),
        "route": route,
        "route_json": _serialize_connection_route(route_raw),
        "updated_at": str(_row_value(row, "updated_at", 10) or "").strip(),
        "x_pct": x1,
        "y_pct": y1,
        "x2_pct": x2,
        "y2_pct": y2,
        "source_lead_x_pct": source_lead[0] if source_lead else None,
        "source_lead_y_pct": source_lead[1] if source_lead else None,
        "target_lead_x_pct": target_lead[0] if target_lead else None,
        "target_lead_y_pct": target_lead[1] if target_lead else None,
        "control_x_pct": control_x,
        "control_y_pct": control_y,
        "label_x_pct": label_x,
        "label_y_pct": label_y,
        "length_pct": length_pct,
        "rotation": math.degrees(math.atan2(dy, dx)) if dx or dy else 0.0,
    }


def load_gleisplan_connections(
    db_exec: Callable[..., Any],
    *,
    layout_items: list[dict[str, Any]] | None = None,
    hall_tracks: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    ensure_gleisplan_layout_schema(db_exec)
    items = layout_items_by_id(layout_items or load_gleisplan_layout_items(db_exec))
    hall_tracks = hall_tracks if hall_tracks is not None else load_gleisplan_hall_tracks(db_exec)
    _repair_switch_connection_ports(db_exec, items)
    rows = db_exec(
        """
        SELECT id, source_item_id, target_item_id, source_port, target_port, label, connection_type, curve_pct, path_points_json, route_json, updated_at
        FROM gleisplan_connections
        WHERE COALESCE(connection_type, 'track') != 'street'
        ORDER BY id ASC;
        """,
        fetch=True,
    ) or []
    out: list[dict[str, Any]] = []
    for row in rows:
        source = str(_row_value(row, "source_item_id", 1) or "").strip().upper()
        target = str(_row_value(row, "target_item_id", 2) or "").strip().upper()
        if source in items and target in items:
            out.append(_row_to_connection(row, items, hall_tracks=hall_tracks))
    return out


def save_gleisplan_connection(
    db_exec: Callable[..., Any],
    *,
    source_item_id: str,
    target_item_id: str,
    source_port: str = "",
    target_port: str = "",
    label: str = "",
    connection_type: str = "track",
    curve_pct: float = 0,
    path_points: list[dict[str, Any]] | None = None,
    points: list[dict[str, Any]] | None = None,
    route: dict[str, Any] | None = None,
    updated_at: str = "",
    connection_id: int | None = None,
) -> tuple[bool, str]:
    ensure_gleisplan_layout_schema(db_exec)
    source = _layout_item_id(source_item_id)
    target = _layout_item_id(target_item_id)
    if not source or not target or source == target:
        return False, "Bitte zwei unterschiedliche Objekte verbinden."
    items = layout_items_by_id(load_gleisplan_layout_items(db_exec))
    if source not in items or target not in items:
        return False, "Verbindungsziel nicht gefunden."
    clean_connection_id = int(connection_id or 0)
    hall_tracks = load_gleisplan_hall_tracks(db_exec)
    ok, clean_source_port, msg = _resolve_connection_port(
        db_exec,
        item=items[source],
        other_item=items[target],
        requested_port=source_port,
        exclude_connection_id=clean_connection_id,
        hall_tracks=hall_tracks,
    )
    if not ok:
        return False, msg
    ok, clean_target_port, msg = _resolve_connection_port(
        db_exec,
        item=items[target],
        other_item=items[source],
        requested_port=target_port,
        exclude_connection_id=clean_connection_id,
        hall_tracks=hall_tracks,
    )
    if not ok:
        return False, msg
    conn_type = str(connection_type or "track").strip().lower()
    if conn_type not in {"track", "street"}:
        conn_type = "track"
    if path_points is None and points is not None:
        path_points = points
    clean_path_points_json = _serialize_connection_path_points(path_points)
    clean_route_json = _serialize_connection_route(route)
    if connection_id:
        existing_connection = None
        if path_points is None or route is None:
            existing_connection = db_exec(
                "SELECT path_points_json, route_json FROM gleisplan_connections WHERE id=?;",
                (int(connection_id),),
                fetchone=True,
            )
        if path_points is None:
            clean_path_points_json = str(_row_value(existing_connection, "path_points_json", 0) or "").strip()
        if route is None:
            clean_route_json = str(_row_value(existing_connection, "route_json", 1) or "").strip()
        db_exec(
            """
            UPDATE gleisplan_connections
            SET source_item_id=?, target_item_id=?, source_port=?, target_port=?, label=?, connection_type=?, curve_pct=?, path_points_json=?, route_json=?, updated_at=?
            WHERE id=?;
            """,
            (
                source,
                target,
                clean_source_port,
                clean_target_port,
                str(label or "").strip(),
                conn_type,
                max(-100.0, min(100.0, _coerce_float(curve_pct, 0))),
                clean_path_points_json,
                clean_route_json,
                updated_at,
                int(connection_id),
            ),
            commit=True,
        )
        return True, "Verbindung gespeichert."
    existing = db_exec(
        """
        SELECT id FROM gleisplan_connections
        WHERE (
                source_item_id=? AND target_item_id=?
                AND COALESCE(source_port, '')=? AND COALESCE(target_port, '')=?
              )
           OR (
                source_item_id=? AND target_item_id=?
                AND COALESCE(source_port, '')=? AND COALESCE(target_port, '')=?
              )
        LIMIT 1;
        """,
        (
            source,
            target,
            clean_source_port,
            clean_target_port,
            target,
            source,
            clean_target_port,
            clean_source_port,
        ),
        fetchone=True,
    )
    if existing:
        return True, "Verbindung besteht für diese Linie bereits."
    db_exec(
        """
        INSERT INTO gleisplan_connections(source_item_id, target_item_id, source_port, target_port, label, connection_type, curve_pct, path_points_json, route_json, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            source,
            target,
            clean_source_port,
            clean_target_port,
            str(label or "").strip(),
            conn_type,
            max(-100.0, min(100.0, _coerce_float(curve_pct, 0))),
            clean_path_points_json,
            clean_route_json,
            updated_at,
        ),
        commit=True,
    )
    return True, "Verbindung gespeichert."


def update_gleisplan_connection_curve(
    db_exec: Callable[..., Any],
    *,
    connection_id: int,
    curve_pct: float,
    updated_at: str = "",
) -> tuple[bool, str]:
    ensure_gleisplan_layout_schema(db_exec)
    try:
        clean_id = int(connection_id)
    except Exception:
        clean_id = 0
    if clean_id <= 0:
        return False, "Verbindung nicht gefunden."
    row = db_exec("SELECT id FROM gleisplan_connections WHERE id=?;", (clean_id,), fetchone=True)
    if not row:
        return False, "Verbindung nicht gefunden."
    db_exec(
        """
        UPDATE gleisplan_connections
        SET curve_pct=?, path_points_json='', updated_at=?
        WHERE id=?;
        """,
        (max(-100.0, min(100.0, _coerce_float(curve_pct, 0))), updated_at, clean_id),
        commit=True,
    )
    return True, "Verbindungskurve gespeichert."


def _load_connection_for_path_edit(db_exec: Callable[..., Any], connection_id: int) -> dict[str, Any] | None:
    layout_items = load_gleisplan_layout_items(db_exec)
    connections = load_gleisplan_connections(db_exec, layout_items=layout_items)
    for connection in connections:
        if int(connection.get("id") or 0) == int(connection_id):
            return connection
    return None


def _connection_route_for_edit(connection: dict[str, Any]) -> dict[str, Any] | None:
    route = _parse_connection_route(connection.get("route") or connection.get("route_json"))
    if not route:
        return None
    points = [dict(point) for point in (route.get("points") or []) if isinstance(point, dict)]
    if len(points) < 2:
        return None
    route = dict(route)
    route["type"] = "smooth"
    route["smooth"] = True
    route["points"] = points
    route["start"] = points[0]
    route["end"] = points[-1]
    return route


def _save_connection_route_for_edit(
    db_exec: Callable[..., Any],
    *,
    connection_id: int,
    route: dict[str, Any],
    updated_at: str,
) -> None:
    route = dict(route)
    points = [dict(point) for point in (route.get("points") or []) if isinstance(point, dict)]
    if len(points) >= 2:
        route["points"] = points
        route["start"] = points[0]
        route["end"] = points[-1]
    route["type"] = "smooth"
    route["smooth"] = True
    db_exec(
        "UPDATE gleisplan_connections SET curve_pct=0, path_points_json='', route_json=?, updated_at=? WHERE id=?;",
        (_serialize_connection_route(route), updated_at, int(connection_id)),
        commit=True,
    )


def _route_insert_index_for_point(route_points: list[dict[str, Any]], x: float, y: float) -> int:
    if len(route_points) < 2:
        return 1
    clean_insert_index = len(route_points) - 1
    best_distance = float("inf")
    for index in range(len(route_points) - 1):
        ax = _coerce_float(route_points[index].get("x_pct"), 0)
        ay = _coerce_float(route_points[index].get("y_pct"), 0)
        bx = _coerce_float(route_points[index + 1].get("x_pct"), 0)
        by = _coerce_float(route_points[index + 1].get("y_pct"), 0)
        dx = bx - ax
        dy = by - ay
        length_sq = (dx * dx) + (dy * dy)
        if length_sq <= 0.000001:
            distance = ((x - ax) ** 2) + ((y - ay) ** 2)
        else:
            t = max(0.0, min(1.0, (((x - ax) * dx) + ((y - ay) * dy)) / length_sq))
            px = ax + (dx * t)
            py = ay + (dy * t)
            distance = ((x - px) ** 2) + ((y - py) ** 2)
        if distance < best_distance:
            best_distance = distance
            clean_insert_index = index + 1
    return max(1, min(len(route_points) - 1, clean_insert_index))


def add_gleisplan_connection_path_point(
    db_exec: Callable[..., Any],
    *,
    connection_id: int,
    x_pct: float | None = None,
    y_pct: float | None = None,
    insert_index: int | None = None,
    updated_at: str = "",
) -> tuple[bool, str]:
    ensure_gleisplan_layout_schema(db_exec)
    try:
        clean_id = int(connection_id)
    except Exception:
        clean_id = 0
    if clean_id <= 0:
        return False, "Verbindung nicht gefunden."
    connection = _load_connection_for_path_edit(db_exec, clean_id)
    if not connection:
        return False, "Verbindung nicht gefunden."
    route = _connection_route_for_edit(connection)
    if route:
        route_points = [dict(point) for point in (route.get("points") or []) if isinstance(point, dict)]
        manual_count = sum(1 for point in route_points if not _is_route_anchor_point(point))
        if manual_count >= 32:
            return False, "Maximal 32 manuelle Stuetzpunkte je Route."
        if x_pct is None or y_pct is None:
            x, y = _route_point_at(route, 0.5)
        else:
            x = max(0.0, min(100.0, _coerce_float(x_pct, 0)))
            y = max(0.0, min(100.0, _coerce_float(y_pct, 0)))
        if insert_index is not None:
            try:
                clean_insert_index = max(1, min(len(route_points) - 1, int(insert_index)))
            except Exception:
                clean_insert_index = _route_insert_index_for_point(route_points, x, y)
        else:
            clean_insert_index = _route_insert_index_for_point(route_points, x, y)
        route_points.insert(clean_insert_index, {"x_pct": round(x, 3), "y_pct": round(y, 3)})
        route["points"] = route_points
        _save_connection_route_for_edit(
            db_exec,
            connection_id=clean_id,
            route=route,
            updated_at=updated_at,
        )
        return True, "Route-Stuetzpunkt hinzugefuegt."
    points = list(connection.get("path_points") or [])
    if len(points) >= 12:
        return False, "Maximal 12 Stuetzpunkte je Verbindung."
    if x_pct is None or y_pct is None:
        x, y = _quadratic_connection_point(
            (float(connection.get("x_pct") or 0), float(connection.get("y_pct") or 0)),
            (float(connection.get("control_x_pct") or 0), float(connection.get("control_y_pct") or 0)),
            (float(connection.get("x2_pct") or 0), float(connection.get("y2_pct") or 0)),
            0.5,
        )
    else:
        x = max(0.0, min(100.0, _coerce_float(x_pct, 0)))
        y = max(0.0, min(100.0, _coerce_float(y_pct, 0)))

    path = [
        (float(connection.get("x_pct") or 0), float(connection.get("y_pct") or 0)),
        *[_path_point_tuple(point) for point in points],
        (float(connection.get("x2_pct") or 0), float(connection.get("y2_pct") or 0)),
    ]
    if insert_index is not None:
        try:
            clean_insert_index = max(0, min(len(points), int(insert_index)))
        except Exception:
            clean_insert_index = len(points)
    else:
        clean_insert_index = len(points)
        best_distance = float("inf")
        for index in range(len(path) - 1):
            ax, ay = path[index]
            bx, by = path[index + 1]
            dx = bx - ax
            dy = by - ay
            length_sq = (dx * dx) + (dy * dy)
            if length_sq <= 0.000001:
                distance = ((x - ax) ** 2) + ((y - ay) ** 2)
            else:
                t = max(0.0, min(1.0, (((x - ax) * dx) + ((y - ay) * dy)) / length_sq))
                px = ax + (dx * t)
                py = ay + (dy * t)
                distance = ((x - px) ** 2) + ((y - py) ** 2)
            if distance < best_distance:
                best_distance = distance
                clean_insert_index = index
    points.insert(clean_insert_index, {"x_pct": x, "y_pct": y})
    db_exec(
        "UPDATE gleisplan_connections SET curve_pct=0, path_points_json=?, updated_at=? WHERE id=?;",
        (_serialize_connection_path_points(points), updated_at, clean_id),
        commit=True,
    )
    return True, "Stuetzpunkt hinzugefuegt."


def update_gleisplan_connection_path_point(
    db_exec: Callable[..., Any],
    *,
    connection_id: int,
    point_index: int,
    x_pct: float,
    y_pct: float,
    updated_at: str = "",
) -> tuple[bool, str]:
    ensure_gleisplan_layout_schema(db_exec)
    try:
        clean_id = int(connection_id)
        index = int(point_index)
    except Exception:
        clean_id = 0
        index = -1
    connection = _load_connection_for_path_edit(db_exec, clean_id)
    if not connection:
        return False, "Verbindung nicht gefunden."
    route = _connection_route_for_edit(connection)
    if route:
        route_points = [dict(point) for point in (route.get("points") or []) if isinstance(point, dict)]
        if index < 0 or index >= len(route_points) or _is_route_anchor_point(route_points[index]):
            return False, "Route-Stuetzpunkt nicht gefunden."
        route_points[index] = {
            "x_pct": round(max(0.0, min(100.0, _coerce_float(x_pct, 0))), 3),
            "y_pct": round(max(0.0, min(100.0, _coerce_float(y_pct, 0))), 3),
        }
        route["points"] = route_points
        _save_connection_route_for_edit(
            db_exec,
            connection_id=clean_id,
            route=route,
            updated_at=updated_at,
        )
        return True, "Route-Stuetzpunkt gespeichert."
    points = list(connection.get("path_points") or [])
    if index < 0 or index >= len(points):
        return False, "Stuetzpunkt nicht gefunden."
    points[index] = {
        "x_pct": max(0.0, min(100.0, _coerce_float(x_pct, 0))),
        "y_pct": max(0.0, min(100.0, _coerce_float(y_pct, 0))),
    }
    db_exec(
        "UPDATE gleisplan_connections SET path_points_json=?, updated_at=? WHERE id=?;",
        (_serialize_connection_path_points(points), updated_at, clean_id),
        commit=True,
    )
    return True, "Stuetzpunkt gespeichert."


def delete_gleisplan_connection_path_point(
    db_exec: Callable[..., Any],
    *,
    connection_id: int,
    point_index: int | None = None,
    updated_at: str = "",
) -> tuple[bool, str]:
    ensure_gleisplan_layout_schema(db_exec)
    try:
        clean_id = int(connection_id)
    except Exception:
        clean_id = 0
    connection = _load_connection_for_path_edit(db_exec, clean_id)
    if not connection:
        return False, "Verbindung nicht gefunden."
    route = _connection_route_for_edit(connection)
    if route:
        route_points = [dict(point) for point in (route.get("points") or []) if isinstance(point, dict)]
        if point_index is None:
            if len(route_points) >= 2:
                route_points = [route_points[0], route_points[-1]]
            else:
                route_points = []
        else:
            try:
                index = int(point_index)
            except Exception:
                index = -1
            if index < 0 or index >= len(route_points) or _is_route_anchor_point(route_points[index]):
                return False, "Route-Stuetzpunkt nicht gefunden."
            route_points.pop(index)
        if len(route_points) < 2:
            return False, "Route braucht Start- und Endanker."
        route["points"] = route_points
        _save_connection_route_for_edit(
            db_exec,
            connection_id=clean_id,
            route=route,
            updated_at=updated_at,
        )
        return True, "Route-Stuetzpunkt entfernt."
    if point_index is None:
        points: list[dict[str, float]] = []
    else:
        try:
            index = int(point_index)
        except Exception:
            index = -1
        points = list(connection.get("path_points") or [])
        if index < 0 or index >= len(points):
            return False, "Stuetzpunkt nicht gefunden."
        points.pop(index)
    db_exec(
        "UPDATE gleisplan_connections SET path_points_json=?, updated_at=? WHERE id=?;",
        (_serialize_connection_path_points(points), updated_at, clean_id),
        commit=True,
    )
    return True, "Stuetzpunkt entfernt."


def smooth_gleisplan_connection_route(
    db_exec: Callable[..., Any],
    *,
    connection_id: int,
    updated_at: str = "",
) -> tuple[bool, str]:
    ensure_gleisplan_layout_schema(db_exec)
    try:
        clean_id = int(connection_id)
    except Exception:
        clean_id = 0
    connection = _load_connection_for_path_edit(db_exec, clean_id)
    if not connection:
        return False, "Verbindung nicht gefunden."
    route = _connection_route_for_edit(connection)
    if not route:
        points = [
            {"x_pct": round(float(connection.get("x_pct") or 0), 3), "y_pct": round(float(connection.get("y_pct") or 0), 3)},
            *[dict(point) for point in (connection.get("path_points") or []) if isinstance(point, dict)],
            {"x_pct": round(float(connection.get("x2_pct") or 0), 3), "y_pct": round(float(connection.get("y2_pct") or 0), 3)},
        ]
        route = {"type": "smooth", "smooth": True, "points": points, "start": points[0], "end": points[-1]}
    route["type"] = "smooth"
    route["smooth"] = True
    _save_connection_route_for_edit(
        db_exec,
        connection_id=clean_id,
        route=route,
        updated_at=updated_at,
    )
    return True, "Verbindung wird als weiche Route gerendert."


def reset_gleisplan_connection_route_shape(
    db_exec: Callable[..., Any],
    *,
    connection_id: int,
    updated_at: str = "",
) -> tuple[bool, str]:
    ensure_gleisplan_layout_schema(db_exec)
    try:
        clean_id = int(connection_id)
    except Exception:
        clean_id = 0
    connection = _load_connection_for_path_edit(db_exec, clean_id)
    if not connection:
        return False, "Verbindung nicht gefunden."
    route = _connection_route_for_edit(connection)
    if route:
        points = [dict(point) for point in (route.get("points") or []) if isinstance(point, dict)]
        if len(points) < 2:
            return False, "Route braucht Start- und Endanker."
        route["points"] = [points[0], points[-1]]
        _save_connection_route_for_edit(
            db_exec,
            connection_id=clean_id,
            route=route,
            updated_at=updated_at,
        )
        return True, "Route auf Start-/Endanker zurückgesetzt."
    db_exec(
        "UPDATE gleisplan_connections SET curve_pct=0, path_points_json='', updated_at=? WHERE id=?;",
        (updated_at, clean_id),
        commit=True,
    )
    return True, "Verbindungsform zurückgesetzt."


def delete_gleisplan_connection(db_exec: Callable[..., Any], *, connection_id: int) -> tuple[bool, str]:
    ensure_gleisplan_layout_schema(db_exec)
    connection_track_id = _connection_assignment_track_id(connection_id)
    if connection_track_id:
        db_exec("DELETE FROM gleisplan_assignments WHERE track_id=?;", (connection_track_id,), commit=True)
    db_exec("DELETE FROM gleisplan_connections WHERE id=?;", (int(connection_id),), commit=True)
    return True, "Verbindung gelöscht."


def reset_gleisplan_layout_to_default(db_exec: Callable[..., Any], *, updated_at: str = "") -> tuple[bool, str]:
    return apply_gleisplan_layout_template(
        db_exec,
        template_key=EBERSWALDE_LAGEPLAN_TEMPLATE_KEY,
        updated_at=updated_at,
    )


def _valid_assignment_tracks(db_exec: Callable[..., Any]) -> set[str]:
    layout_items = load_gleisplan_layout_items(db_exec)
    valid = set(ordered_hall_track_codes(load_gleisplan_hall_tracks(db_exec)))
    for connection in load_gleisplan_connections(db_exec, layout_items=layout_items):
        track_id = _connection_assignment_track_id(connection.get("id"))
        if track_id:
            valid.add(track_id)
    return valid


def _parse_assignment_vehicles(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = None
    if isinstance(parsed, list):
        raw_values = parsed
    else:
        raw_values = [part for part in re.split(r"[\n;]+", text) if part]
    vehicles: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        vehicle = str(raw or "").strip()
        if not vehicle:
            continue
        key = vehicle.casefold()
        if key in seen:
            continue
        seen.add(key)
        vehicles.append(vehicle)
    return vehicles


def _serialize_assignment_vehicles(vehicles: list[str]) -> str:
    clean: list[str] = []
    seen: set[str] = set()
    for raw in vehicles:
        vehicle = str(raw or "").strip()
        if not vehicle:
            continue
        key = vehicle.casefold()
        if key in seen:
            continue
        seen.add(key)
        clean.append(vehicle)
    return json.dumps(clean, ensure_ascii=True, separators=(",", ":"))


def assignment_vehicles(assignments: dict[str, list[str]] | None, track_id: str) -> list[str]:
    value = (assignments or {}).get(str(track_id or "").strip().upper())
    if isinstance(value, list):
        return list(value)
    return _parse_assignment_vehicles(value)


def load_gleisplan_assignments(db_exec: Callable[..., Any]) -> dict[str, list[str]]:
    ensure_gleisplan_assignment_schema(db_exec)
    rows = db_exec(
        """
        SELECT track_id, vehicle_number
        FROM gleisplan_assignments
        WHERE TRIM(COALESCE(track_id, '')) <> ''
          AND TRIM(COALESCE(vehicle_number, '')) <> '';
        """,
        fetch=True,
    ) or []
    valid_tracks = _valid_assignment_tracks(db_exec)
    out: dict[str, list[str]] = {}
    for row in rows:
        track_id = str(row["track_id"] if isinstance(row, dict) or hasattr(row, "keys") else row[0]).strip().upper()
        vehicles = _parse_assignment_vehicles(row["vehicle_number"] if isinstance(row, dict) or hasattr(row, "keys") else row[1])
        if track_id in valid_tracks and vehicles:
            out[track_id] = vehicles
    return out


def save_gleisplan_assignment(
    db_exec: Callable[..., Any],
    *,
    track_id: str,
    vehicle_number: str,
    updated_at: str,
) -> tuple[bool, str]:
    ensure_gleisplan_assignment_schema(db_exec)
    track_norm = str(track_id or "").strip().upper()
    vehicle = str(vehicle_number or "").strip()
    if track_norm not in _valid_assignment_tracks(db_exec):
        return False, "Unbekanntes Gleis."
    if not vehicle:
        return False, "Bitte ein Fahrzeug auswählen."
    existing = db_exec(
        "SELECT vehicle_number FROM gleisplan_assignments WHERE track_id=?;",
        (track_norm,),
        fetchone=True,
    )
    vehicles = _parse_assignment_vehicles(_row_value(existing, "vehicle_number", 0) if existing else "")
    if vehicle.casefold() not in {item.casefold() for item in vehicles}:
        vehicles.append(vehicle)
    db_exec(
        """
        INSERT INTO gleisplan_assignments(track_id, vehicle_number, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(track_id) DO UPDATE SET
            vehicle_number=excluded.vehicle_number,
            updated_at=excluded.updated_at;
        """,
        (track_norm, _serialize_assignment_vehicles(vehicles), updated_at),
        commit=True,
    )
    return True, "Gleisplan-Zuordnung gespeichert."


def delete_gleisplan_assignment(
    db_exec: Callable[..., Any],
    *,
    track_id: str,
    vehicle_number: str = "",
    updated_at: str = "",
) -> tuple[bool, str]:
    ensure_gleisplan_assignment_schema(db_exec)
    track_norm = str(track_id or "").strip().upper()
    if track_norm not in _valid_assignment_tracks(db_exec):
        return False, "Unbekanntes Gleis."
    vehicle = str(vehicle_number or "").strip()
    if vehicle:
        existing = db_exec(
            "SELECT vehicle_number FROM gleisplan_assignments WHERE track_id=?;",
            (track_norm,),
            fetchone=True,
        )
        vehicles = _parse_assignment_vehicles(_row_value(existing, "vehicle_number", 0) if existing else "")
        remaining = [item for item in vehicles if item.casefold() != vehicle.casefold()]
        if remaining:
            db_exec(
                "UPDATE gleisplan_assignments SET vehicle_number=?, updated_at=? WHERE track_id=?;",
                (_serialize_assignment_vehicles(remaining), updated_at, track_norm),
                commit=True,
            )
        else:
            db_exec("DELETE FROM gleisplan_assignments WHERE track_id=?;", (track_norm,), commit=True)
        return True, "Gleisplan-Zuordnung entfernt."
    db_exec("DELETE FROM gleisplan_assignments WHERE track_id=?;", (track_norm,), commit=True)
    return True, "Gleisplan-Zuordnung entfernt."


def _row_value(row: Any, key: str, fallback_index: int | None = None) -> Any:
    try:
        if hasattr(row, "keys") and key in row.keys():
            return row[key]
    except Exception:
        pass
    if isinstance(row, dict):
        return row.get(key)
    if fallback_index is not None:
        try:
            return row[fallback_index]
        except Exception:
            return None
    return None


def _normalize_area(value: Any, normalize_workshop_area: Callable[[Any], str] | None) -> str:
    if callable(normalize_workshop_area):
        return str(normalize_workshop_area(value) or "").strip().upper()
    return str(value or "").strip().upper()


def _vehicle_keys(value: Any, norm_vehicle: Callable[[str], str] | None = None) -> set[str]:
    raw = str(value or "").strip()
    if not raw:
        return set()

    def compact(text: Any) -> str:
        return "".join(ch for ch in str(text or "").casefold() if ch.isalnum())

    keys = {compact(raw)}
    if callable(norm_vehicle):
        try:
            normed = str(norm_vehicle(raw) or "").strip()
            if normed:
                keys.add(compact(normed))
        except Exception:
            pass

    numeric = "".join(ch if ch.isdigit() else " " for ch in raw).split()
    if numeric:
        last_num = numeric[-1].lstrip("0") or "0"
        keys.add(f"num{last_num}")
    return {key for key in keys if key}


def _safe_vehicle_series(
    vehicle_label: str,
    get_vehicle_series_for_vehicle: Callable[[Any], str] | None,
) -> str:
    if callable(get_vehicle_series_for_vehicle):
        try:
            return str(get_vehicle_series_for_vehicle(vehicle_label) or "").strip()
        except Exception:
            return ""
    return ""


def _build_vehicle_entry_from_open_row(
    row: pd.Series,
    area_code: str,
    *,
    fmt_dt: Callable[[Any], str] | None = None,
    status_for_row: Callable[..., tuple[str, str]] | None = None,
    status_palette: Callable[[str], tuple[str, str]] | None = None,
    calc_frist_progress: Callable[..., tuple[int, int, list[str], list[bool], bool]] | None = None,
    calc_zus_progress: Callable[..., tuple[int, int, list[str], list[bool]]] | None = None,
    get_vehicle_series_for_vehicle: Callable[[Any], str] | None = None,
    source: str = "open_tasks",
) -> dict[str, Any]:
    vehicle_label = str(row.get("Fahrzeug") or "").strip() or "-"
    frist_label = str(row.get("Friststufe") or "").strip() or "-"
    end_value = row.get("Fertig")
    end_label = str(fmt_dt(end_value) if callable(fmt_dt) else end_value or "").strip() or "-"
    series_label = _safe_vehicle_series(vehicle_label, get_vehicle_series_for_vehicle)

    status_key = "neutral"
    status_text = ""
    status_bg = "#64748b"
    status_fg = "#f8fafc"
    if callable(status_for_row):
        try:
            status_key, status_text = status_for_row(row, include_problem=True)
        except Exception:
            status_key, status_text = "neutral", ""
    if callable(status_palette):
        try:
            status_bg, status_fg = status_palette(status_key)
        except Exception:
            status_bg, status_fg = "#64748b", "#f8fafc"

    frist_progress = None
    if callable(calc_frist_progress):
        try:
            done, total, _items, _checks, applicable = calc_frist_progress(row, area_code=area_code)
            frist_progress = {"done": int(done), "total": int(total), "applicable": bool(applicable)}
        except Exception:
            frist_progress = None

    zus_progress = None
    if callable(calc_zus_progress):
        try:
            done, total, _items, _checks = calc_zus_progress(row)
            zus_progress = {"done": int(done), "total": int(total)}
        except Exception:
            zus_progress = None

    return {
        "id": int(row.get("id") or 0),
        "area": area_code,
        "vehicle_label": vehicle_label,
        "series_label": series_label,
        "frist_label": frist_label,
        "end_label": end_label,
        "status_key": status_key,
        "status_text": status_text,
        "status_bg": status_bg,
        "status_fg": status_fg,
        "frist_progress": frist_progress,
        "zus_progress": zus_progress,
        "source": source,
        "has_open_task": True,
    }


def _build_vehicle_entry_from_assignment(
    vehicle_number: str,
    *,
    track_id: str,
    vehicle_catalog: dict[str, dict[str, str]],
    open_task_index: dict[str, pd.Series],
    norm_vehicle: Callable[[str], str] | None = None,
    fmt_dt: Callable[[Any], str] | None = None,
    status_for_row: Callable[..., tuple[str, str]] | None = None,
    status_palette: Callable[[str], tuple[str, str]] | None = None,
    calc_frist_progress: Callable[..., tuple[int, int, list[str], list[bool], bool]] | None = None,
    calc_zus_progress: Callable[..., tuple[int, int, list[str], list[bool]]] | None = None,
    get_vehicle_series_for_vehicle: Callable[[Any], str] | None = None,
) -> dict[str, Any]:
    for key in _vehicle_keys(vehicle_number, norm_vehicle):
        open_row = open_task_index.get(key)
        if open_row is not None:
            entry = _build_vehicle_entry_from_open_row(
                open_row,
                track_id,
                fmt_dt=fmt_dt,
                status_for_row=status_for_row,
                status_palette=status_palette,
                calc_frist_progress=calc_frist_progress,
                calc_zus_progress=calc_zus_progress,
                get_vehicle_series_for_vehicle=get_vehicle_series_for_vehicle,
                source="gleisplan+open_tasks",
            )
            entry["vehicle_label"] = str(vehicle_number or entry.get("vehicle_label") or "").strip()
            if not entry.get("series_label"):
                entry["series_label"] = str((vehicle_catalog.get(vehicle_number) or {}).get("baureihe") or "").strip()
            return entry

    catalog_entry = vehicle_catalog.get(vehicle_number) or {}
    return {
        "id": 0,
        "area": track_id,
        "vehicle_label": vehicle_number,
        "series_label": str(catalog_entry.get("baureihe") or "").strip(),
        "frist_label": "-",
        "end_label": "-",
        "status_key": "manual",
        "status_text": "ohne offenen Auftrag",
        "status_bg": "#475569",
        "status_fg": "#f8fafc",
        "frist_progress": None,
        "zus_progress": None,
        "source": "gleisplan",
        "has_open_task": False,
    }


def _open_task_index(
    df_open: pd.DataFrame | None,
    *,
    norm_vehicle: Callable[[str], str] | None = None,
) -> dict[str, pd.Series]:
    if df_open is None or df_open.empty:
        return {}
    df = df_open.copy()
    if "Fahrzeug" not in df.columns:
        return {}
    if "Fertig" not in df.columns:
        df["Fertig"] = ""
    df["__gleisplan_end"] = pd.to_datetime(df["Fertig"], errors="coerce")
    df = df.sort_values(["__gleisplan_end", "Fahrzeug"], na_position="last").reset_index(drop=True)
    out: dict[str, pd.Series] = {}
    for _, row in df.iterrows():
        for key in _vehicle_keys(row.get("Fahrzeug"), norm_vehicle):
            out.setdefault(key, row)
    return out


def build_vehicle_catalog(
    mappings: list[dict[str, Any]] | None,
    df_open: pd.DataFrame | None = None,
) -> tuple[dict[str, dict[str, str]], bool]:
    catalog: dict[str, dict[str, str]] = {}
    for raw in mappings or []:
        vehicle = str(raw.get("vehicle_number") or "").strip()
        if not vehicle:
            continue
        catalog[vehicle] = {
            "vehicle_number": vehicle,
            "baureihe": str(raw.get("baureihe") or "").strip(),
            "source": "configuration",
        }
    if catalog:
        return catalog, False

    if df_open is None or df_open.empty or "Fahrzeug" not in df_open.columns:
        return {}, False

    for raw_vehicle in df_open["Fahrzeug"].dropna().astype(str).sort_values().tolist():
        vehicle = str(raw_vehicle or "").strip()
        if vehicle:
            catalog.setdefault(
                vehicle,
                {
                    "vehicle_number": vehicle,
                    "baureihe": "",
                    "source": "fallback_open_tasks",
                },
            )
    return catalog, bool(catalog)


def build_vehicle_select_options(vehicle_catalog: dict[str, dict[str, str]]) -> dict[str, str]:
    options: dict[str, str] = {}
    for vehicle, item in sorted(vehicle_catalog.items(), key=lambda kv: kv[0].casefold()):
        series = str(item.get("baureihe") or "").strip()
        source = str(item.get("source") or "").strip()
        suffix_parts = []
        if series:
            suffix_parts.append(series)
        if source == "fallback_open_tasks":
            suffix_parts.append("offener Auftrag")
        suffix = f" | {' | '.join(suffix_parts)}" if suffix_parts else ""
        options[vehicle] = f"{vehicle}{suffix}"
    return options


def build_track_select_options(
    layout_items: list[dict[str, Any]] | None = None,
    connections: list[dict[str, Any]] | None = None,
    hall_tracks: dict[str, dict[str, Any]] | None = None,
) -> dict[str, str]:
    options: dict[str, str] = {}
    for connection in connections or []:
        track_id = str(connection.get("assignment_track_id") or _connection_assignment_track_id(connection.get("id"))).strip().upper()
        if not track_id:
            continue
        label = str(connection.get("label") or "").strip()
        if not label:
            continue
        source = str(connection.get("source_item_id") or "").strip()
        target = str(connection.get("target_item_id") or "").strip()
        suffix = f"{source} -> {target}" if source and target else "Verbindung"
        options.setdefault(track_id, f"{label} - {suffix}")
    for area in ordered_hall_track_codes(hall_tracks):
        config = (hall_tracks or {}).get(area) or DEFAULT_HALL_TRACK_CONFIG.get(area, {})
        label = str(config.get("track_label") or area).strip()
        position = str(config.get("position_label") or "").strip()
        suffix = f" - {position}" if position else ""
        options.setdefault(area, f"{label}{suffix}")
    return options


def find_open_task_for_vehicle(
    df_open: pd.DataFrame | None,
    vehicle_number: str,
    *,
    norm_vehicle: Callable[[str], str] | None = None,
) -> pd.Series | None:
    index = _open_task_index(df_open, norm_vehicle=norm_vehicle)
    for key in _vehicle_keys(vehicle_number, norm_vehicle):
        row = index.get(key)
        if row is not None:
            return row
    return None


def build_gleishalle_occupancy(
    df_open: pd.DataFrame | None,
    *,
    manual_assignments: dict[str, list[str]] | None = None,
    vehicle_catalog: dict[str, dict[str, str]] | None = None,
    hall_tracks: dict[str, dict[str, Any]] | None = None,
    normalize_workshop_area: Callable[[Any], str] | None = None,
    norm_vehicle: Callable[[str], str] | None = None,
    fmt_dt: Callable[[Any], str] | None = None,
    status_for_row: Callable[..., tuple[str, str]] | None = None,
    status_palette: Callable[[str], tuple[str, str]] | None = None,
    calc_frist_progress: Callable[..., tuple[int, int, list[str], list[bool], bool]] | None = None,
    calc_zus_progress: Callable[..., tuple[int, int, list[str], list[bool]]] | None = None,
    get_vehicle_series_for_vehicle: Callable[[Any], str] | None = None,
) -> dict[str, dict[str, Any]]:
    hall_tracks = {area: dict(config) for area, config in (hall_tracks or DEFAULT_HALL_TRACK_CONFIG).items()}
    hall_codes = ordered_hall_track_codes(hall_tracks)
    occupancy: dict[str, dict[str, Any]] = {}
    for area in hall_codes:
        config = hall_tracks.get(area) or DEFAULT_HALL_TRACK_CONFIG.get(area, {})
        occupancy[area] = {
            "area": area,
            "track_label": str(config.get("track_label") or area).strip(),
            "position_label": str(config.get("position_label") or HALL_TRACK_LABELS.get(area, "")).strip(),
            "workshop_area": str(config.get("workshop_area") or area).strip().upper(),
            "sync_enabled": bool(config.get("sync_enabled", True)),
            "vehicle": None,
            "extras": [],
        }

    manual_assignments = manual_assignments or {}
    vehicle_catalog = vehicle_catalog or {}
    open_index = _open_task_index(df_open, norm_vehicle=norm_vehicle)

    if df_open is not None and not df_open.empty:
        df = df_open.copy()
        if "Arbeitsplatz" not in df.columns:
            df["Arbeitsplatz"] = ""
        if "Fahrzeug" not in df.columns:
            df["Fahrzeug"] = ""
        if "Fertig" not in df.columns:
            df["Fertig"] = ""

        df["__gleisplan_area"] = df["Arbeitsplatz"].apply(lambda value: _normalize_area(value, normalize_workshop_area))
        df["__gleisplan_end"] = pd.to_datetime(df["Fertig"], errors="coerce")
        df = df.sort_values(["__gleisplan_end", "Fahrzeug"], na_position="last").reset_index(drop=True)

        for area in hall_codes:
            if not bool(occupancy[area].get("sync_enabled")):
                continue
            workshop_area = str(occupancy[area].get("workshop_area") or area).strip().upper()
            rows = df[df["__gleisplan_area"] == workshop_area].copy()
            if rows.empty:
                continue

            primary = _build_vehicle_entry_from_open_row(
                rows.iloc[0],
                workshop_area,
                fmt_dt=fmt_dt,
                status_for_row=status_for_row,
                status_palette=status_palette,
                calc_frist_progress=calc_frist_progress,
                calc_zus_progress=calc_zus_progress,
                get_vehicle_series_for_vehicle=get_vehicle_series_for_vehicle,
                source="werkstatthalle",
            )
            extras = [
                _build_vehicle_entry_from_open_row(
                    rr,
                    workshop_area,
                    fmt_dt=fmt_dt,
                    status_for_row=status_for_row,
                    status_palette=status_palette,
                    calc_frist_progress=calc_frist_progress,
                    calc_zus_progress=calc_zus_progress,
                    get_vehicle_series_for_vehicle=get_vehicle_series_for_vehicle,
                    source="werkstatthalle",
                )
                for _, rr in rows.iloc[1:].iterrows()
            ]
            occupancy[area]["vehicle"] = primary
            occupancy[area]["extras"] = extras

    for area in hall_codes:
        if occupancy[area]["vehicle"] is not None:
            continue
        assigned_vehicles = assignment_vehicles(manual_assignments, area)
        if not assigned_vehicles:
            continue
        occupancy[area]["vehicle"] = _build_vehicle_entry_from_assignment(
            assigned_vehicles[0],
            track_id=area,
            vehicle_catalog=vehicle_catalog,
            open_task_index=open_index,
            norm_vehicle=norm_vehicle,
            fmt_dt=fmt_dt,
            status_for_row=status_for_row,
            status_palette=status_palette,
            calc_frist_progress=calc_frist_progress,
            calc_zus_progress=calc_zus_progress,
            get_vehicle_series_for_vehicle=get_vehicle_series_for_vehicle,
        )
        occupancy[area]["extras"] = [
            _build_vehicle_entry_from_assignment(
                assigned_vehicle,
                track_id=area,
                vehicle_catalog=vehicle_catalog,
                open_task_index=open_index,
                norm_vehicle=norm_vehicle,
                fmt_dt=fmt_dt,
                status_for_row=status_for_row,
                status_palette=status_palette,
                calc_frist_progress=calc_frist_progress,
                calc_zus_progress=calc_zus_progress,
                get_vehicle_series_for_vehicle=get_vehicle_series_for_vehicle,
            )
            for assigned_vehicle in assigned_vehicles[1:]
        ]

    return occupancy


def _connection_bezier_point(connection: dict[str, Any], t: float) -> tuple[float, float]:
    route = _parse_connection_route(connection.get("route") or connection.get("route_json"))
    if route:
        return _route_point_at(route, t)
    x1 = _coerce_float(connection.get("x_pct"), 0)
    y1 = _coerce_float(connection.get("y_pct"), 0)
    x2 = _coerce_float(connection.get("x2_pct"), x1)
    y2 = _coerce_float(connection.get("y2_pct"), y1)
    path_points = list(connection.get("path_points") or [])
    if path_points:
        return _catmull_rom_point([(x1, y1), *[_path_point_tuple(point) for point in path_points], (x2, y2)], t)
    cx = _coerce_float(connection.get("control_x_pct"), (x1 + x2) / 2.0)
    cy = _coerce_float(connection.get("control_y_pct"), (y1 + y2) / 2.0)
    clean_t = max(0.0, min(1.0, float(t)))
    if abs(_coerce_float(connection.get("curve_pct"), 0)) < 0.001:
        return x1 + ((x2 - x1) * clean_t), y1 + ((y2 - y1) * clean_t)
    return _quadratic_connection_point((x1, y1), (cx, cy), (x2, y2), clean_t)


def build_gleisplan_model(
    df_open: pd.DataFrame | None,
    *,
    assignments: dict[str, list[str]] | None = None,
    vehicle_catalog: dict[str, dict[str, str]] | None = None,
    layout_items: list[dict[str, Any]] | None = None,
    connections: list[dict[str, Any]] | None = None,
    hall_tracks: dict[str, dict[str, Any]] | None = None,
    normalize_workshop_area: Callable[[Any], str] | None = None,
    norm_vehicle: Callable[[str], str] | None = None,
    fmt_dt: Callable[[Any], str] | None = None,
    status_for_row: Callable[..., tuple[str, str]] | None = None,
    status_palette: Callable[[str], tuple[str, str]] | None = None,
    calc_frist_progress: Callable[..., tuple[int, int, list[str], list[bool], bool]] | None = None,
    calc_zus_progress: Callable[..., tuple[int, int, list[str], list[bool]]] | None = None,
    get_vehicle_series_for_vehicle: Callable[[Any], str] | None = None,
) -> dict[str, Any]:
    assignments = assignments or {}
    vehicle_catalog = vehicle_catalog or {}
    layout_items = [dict(item) for item in (layout_items or DEFAULT_LAYOUT_ITEMS)]
    connections = [dict(item) for item in (connections or [])]
    hall_tracks = {area: dict(config) for area, config in (hall_tracks or DEFAULT_HALL_TRACK_CONFIG).items()}
    open_index = _open_task_index(df_open, norm_vehicle=norm_vehicle)
    hall_occupancy = build_gleishalle_occupancy(
        df_open,
        manual_assignments=assignments,
        vehicle_catalog=vehicle_catalog,
        hall_tracks=hall_tracks,
        normalize_workshop_area=normalize_workshop_area,
        norm_vehicle=norm_vehicle,
        fmt_dt=fmt_dt,
        status_for_row=status_for_row,
        status_palette=status_palette,
        calc_frist_progress=calc_frist_progress,
        calc_zus_progress=calc_zus_progress,
        get_vehicle_series_for_vehicle=get_vehicle_series_for_vehicle,
    )

    layout_cards: list[dict[str, Any]] = []
    for item in layout_items:
        track_id = str(item.get("item_id") or item.get("id") or "").strip().upper()
        item_type = str(item.get("item_type") or "track").strip().lower()
        if item_type == "track":
            item_type = "anchor"
        vehicle = None
        if item_type == "hall":
            pass
        elif track_id in HALL_TRACKS:
            vehicle = (hall_occupancy.get(track_id) or {}).get("vehicle")
        elif item_type == "track" and assignment_vehicles(assignments, track_id):
            assigned_for_item = assignment_vehicles(assignments, track_id)
            vehicle = _build_vehicle_entry_from_assignment(
                assigned_for_item[0],
                track_id=track_id,
                vehicle_catalog=vehicle_catalog,
                open_task_index=open_index,
                norm_vehicle=norm_vehicle,
                fmt_dt=fmt_dt,
                status_for_row=status_for_row,
                status_palette=status_palette,
                calc_frist_progress=calc_frist_progress,
                calc_zus_progress=calc_zus_progress,
                get_vehicle_series_for_vehicle=get_vehicle_series_for_vehicle,
            )
        layout_cards.append(
            {
                **item,
                "id": track_id,
                "vehicle": vehicle,
                "manual_assignment": assignment_vehicles(assignments, track_id),
                "is_hall": item_type == "hall",
                "is_assignable": item_type == "track" or track_id in HALL_TRACKS,
            }
        )

    connection_cards: list[dict[str, Any]] = []
    for connection in connections:
        track_id = _connection_assignment_track_id(connection.get("id"))
        vehicle = None
        assigned_vehicles = assignment_vehicles(assignments, track_id)
        vehicle_entries = [
            _build_vehicle_entry_from_assignment(
                assigned_vehicle,
                track_id=track_id,
                vehicle_catalog=vehicle_catalog,
                open_task_index=open_index,
                norm_vehicle=norm_vehicle,
                fmt_dt=fmt_dt,
                status_for_row=status_for_row,
                status_palette=status_palette,
                calc_frist_progress=calc_frist_progress,
                calc_zus_progress=calc_zus_progress,
                get_vehicle_series_for_vehicle=get_vehicle_series_for_vehicle,
            )
            for assigned_vehicle in assigned_vehicles
        ]
        if vehicle_entries:
            vehicle = vehicle_entries[0]
        vehicle_positions: list[dict[str, Any]] = []
        count = len(vehicle_entries)
        for index, entry in enumerate(vehicle_entries):
            fraction = 0.5 if count == 1 else (index + 1) / (count + 1)
            px, py = _connection_bezier_point(connection, fraction)
            vehicle_positions.append({"vehicle": entry, "x_pct": px, "y_pct": py, "fraction": fraction})
        connection_cards.append(
            {
                **connection,
                "assignment_track_id": track_id,
                "vehicle": vehicle,
                "vehicles": vehicle_entries,
                "vehicle_positions": vehicle_positions,
                "manual_assignment": assigned_vehicles,
                "is_assignable": bool(track_id),
            }
        )

    return {
        "hall_grid": build_hall_track_grid(hall_tracks),
        "hall_tracks": hall_tracks,
        "hall_occupancy": hall_occupancy,
        "layout_items": layout_cards,
        "tracks": [item for item in layout_cards if str(item.get("item_type") or "") in CONNECTABLE_ITEM_TYPES],
        "connections": connection_cards,
        "track_options": build_track_select_options(layout_cards, connection_cards, hall_tracks),
        "vehicle_options": build_vehicle_select_options(vehicle_catalog),
        "future_hooks": dict(FUTURE_EXTENSION_HOOKS),
    }
