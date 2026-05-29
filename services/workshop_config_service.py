from __future__ import annotations

from typing import Any, Callable


WORKSHOP_TILE_TYPE_OPTIONS: dict[str, str] = {
    "area": "Arbeitsplatz-Kachel",
    "due_soon": "24h-fällig-Kachel",
}

WORKSHOP_TEXT_FIELDS: list[tuple[str, str]] = [
    ("page_title", "Seitentitel"),
    ("external_button", "Button Außeneinsatz"),
    ("legend_current_vehicle", "Legende aktuelles Fahrzeug"),
    ("no_admin_text", "Hinweis ohne Admin-Recht"),
    ("assign_button", "Button freie Kachel"),
    ("remove_button", "Button Zuordnung entfernen"),
    ("assign_select_label", "Auswahl-Label Fahrzeug"),
    ("assign_confirm_button", "Button Zuordnen"),
    ("assign_cancel_button", "Button Abbrechen"),
    ("assign_empty_text", "Text ohne passende Aufträge"),
    ("done_button", "Button Erledigt"),
    ("frist_button", "Button Fristarbeiten"),
    ("zus_button", "Button Zusatzarbeiten"),
    ("delay_button", "Button Verzögerung melden"),
    ("problem_label", "Problem-Box Titel"),
    ("problem_badge", "Problem-Badge"),
    ("due_empty_text", "24h-Kachel ohne Einträge"),
]

WORKSHOP_TEXT_DEFAULTS: dict[str, str] = {
    "page_title": "Werkstatthalle",
    "external_button": "Außeneinsatz",
    "legend_current_vehicle": "Gelb = aktuell zu bearbeitendes Fahrzeug",
    "no_admin_text": "Nur Admin kann Zuordnungen ändern.",
    "assign_button": "Fahrzeug zuordnen",
    "remove_button": "Entfernen",
    "assign_select_label": "Fahrzeug",
    "assign_confirm_button": "Zuordnen",
    "assign_cancel_button": "Abbrechen",
    "assign_empty_text": "Keine passenden unzugeordneten Aufträge.",
    "done_button": "Erledigt",
    "frist_button": "Fristarbeiten",
    "zus_button": "Zusatzarbeiten",
    "delay_button": "Verzögerung melden",
    "problem_label": "Problem(e):",
    "problem_badge": "Problem gemeldet",
    "due_empty_text": "Keine Einträge in den nächsten 24 Stunden.",
}
WORKSHOP_TEXT_LEGACY_DEFAULTS: dict[str, str] = {
    "external_button": "Ausseneinsatz",
    "no_admin_text": "Nur Admin kann Zuordnungen aendern.",
    "assign_empty_text": "Keine passenden unzugeordneten Auftraege.",
    "delay_button": "Verzoegerung melden",
    "due_empty_text": "Keine Eintraege in den naechsten 24 Stunden.",
}

DEFAULT_DUE_TILE_LABEL = "In 24 Std fällig (unzugeordnet)"
LEGACY_DUE_TILE_LABEL = "In 24 Std faellig (unzugeordnet)"


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _clean_tile_key(value: Any) -> str:
    clean = str(value or "").strip().upper().replace(" ", "_")
    return "".join(ch for ch in clean if ch.isalnum() or ch in {"_", "-"})


def _clean_tile_type(value: Any) -> str:
    tile_type = str(value or "area").strip().lower()
    return tile_type if tile_type in WORKSHOP_TILE_TYPE_OPTIONS else "area"


def _clean_area(value: Any) -> str:
    return str(value or "").strip().upper()


def _ensure_workshop_config_schema(db_exec: Callable[..., Any]) -> None:
    db_exec(
        """
        CREATE TABLE IF NOT EXISTS workshop_hall_tiles (
            tile_key      TEXT PRIMARY KEY,
            tile_type     TEXT NOT NULL DEFAULT 'area',
            display_label TEXT NOT NULL,
            content_area  TEXT,
            active        INTEGER NOT NULL DEFAULT 1,
            highlighted   INTEGER NOT NULL DEFAULT 1,
            sort_order    INTEGER NOT NULL DEFAULT 0,
            updated_at    TEXT
        );
        """,
        commit=True,
    )
    db_exec(
        """
        CREATE TABLE IF NOT EXISTS workshop_hall_texts (
            text_key   TEXT PRIMARY KEY,
            text_value TEXT NOT NULL,
            updated_at TEXT
        );
        """,
        commit=True,
    )


def _default_area_tiles(default_area_tiles: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    source = default_area_tiles or [
        {"key": "4B", "area_code": "4B", "display_label": "4B"},
        {"key": "4A", "area_code": "4A", "display_label": "4A"},
        {"key": "5A", "area_code": "5A", "display_label": "5A"},
        {"key": "5B", "area_code": "5B", "display_label": "5B"},
    ]
    out: list[dict[str, Any]] = []
    seen_content: set[str] = set()
    for index, raw in enumerate(source):
        area = _clean_area(raw.get("area_code") or raw.get("content_area") or raw.get("key"))
        key = _clean_tile_key(raw.get("key") or area)
        if not area or not key:
            continue
        seen_content.add(area)
        out.append(
            {
                "tile_key": key,
                "tile_type": "area",
                "display_label": _clean_text(raw.get("display_label") or area) or area,
                "content_area": area,
                "active": True,
                "highlighted": True,
                "sort_order": (index + 1) * 10,
            }
        )
    if "URD" not in seen_content:
        out.append(
            {
                "tile_key": "URD",
                "tile_type": "area",
                "display_label": "URD",
                "content_area": "URD",
                "active": True,
                "highlighted": True,
                "sort_order": (len(out) + 1) * 10,
            }
        )
    out.append(
        {
            "tile_key": "DUE_SOON",
            "tile_type": "due_soon",
            "display_label": DEFAULT_DUE_TILE_LABEL,
            "content_area": "",
            "active": True,
            "highlighted": True,
            "sort_order": (len(out) + 1) * 10,
        }
    )
    return out


def _seed_workshop_config_defaults(
    db_exec: Callable[..., Any],
    *,
    default_area_tiles: list[dict[str, Any]] | None = None,
    seed_tiles: bool = True,
    updated_at: str = "",
) -> None:
    _ensure_workshop_config_schema(db_exec)
    if seed_tiles:
        row = db_exec("SELECT COUNT(*) AS c FROM workshop_hall_tiles;", fetchone=True)
        tile_count = int(row["c"] or 0) if row else 0
        if tile_count <= 0:
            for tile in _default_area_tiles(default_area_tiles):
                save_workshop_hall_tile(db_exec, updated_at=updated_at, **tile)
        else:
            due_row = db_exec(
                "SELECT display_label FROM workshop_hall_tiles WHERE tile_key=?;",
                ("DUE_SOON",),
                fetchone=True,
            )
            if due_row and str(due_row["display_label"] or "").strip() == LEGACY_DUE_TILE_LABEL:
                db_exec(
                    "UPDATE workshop_hall_tiles SET display_label=?, updated_at=? WHERE tile_key=?;",
                    (DEFAULT_DUE_TILE_LABEL, updated_at, "DUE_SOON"),
                    commit=True,
                )

    for key, value in WORKSHOP_TEXT_DEFAULTS.items():
        db_exec(
            """
            INSERT INTO workshop_hall_texts(text_key, text_value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(text_key) DO NOTHING;
            """,
            (key, value, updated_at),
            commit=True,
        )
        legacy_value = WORKSHOP_TEXT_LEGACY_DEFAULTS.get(key)
        if legacy_value:
            db_exec(
                "UPDATE workshop_hall_texts SET text_value=?, updated_at=? WHERE text_key=? AND text_value=?;",
                (value, updated_at, key, legacy_value),
                commit=True,
            )


def load_workshop_hall_texts(db_exec: Callable[..., Any]) -> dict[str, str]:
    _seed_workshop_config_defaults(db_exec, seed_tiles=False)
    rows = db_exec(
        "SELECT text_key, text_value FROM workshop_hall_texts;",
        fetch=True,
    ) or []
    texts = dict(WORKSHOP_TEXT_DEFAULTS)
    for row in rows:
        key = str(row["text_key"] or "").strip()
        if key in texts:
            value = str(row["text_value"] or "").strip()
            texts[key] = value or WORKSHOP_TEXT_DEFAULTS[key]
    return texts


def save_workshop_hall_texts(
    db_exec: Callable[..., Any],
    *,
    texts: dict[str, Any],
    updated_at: str = "",
) -> None:
    _ensure_workshop_config_schema(db_exec)
    for key, _label in WORKSHOP_TEXT_FIELDS:
        value = str((texts or {}).get(key) or WORKSHOP_TEXT_DEFAULTS.get(key, "")).strip()
        db_exec(
            """
            INSERT INTO workshop_hall_texts(text_key, text_value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(text_key) DO UPDATE SET
                text_value=excluded.text_value,
                updated_at=excluded.updated_at;
            """,
            (key, value, updated_at),
            commit=True,
        )


def load_workshop_hall_tiles(
    db_exec: Callable[..., Any],
    *,
    default_area_tiles: list[dict[str, Any]] | None = None,
    include_inactive: bool = True,
) -> list[dict[str, Any]]:
    _seed_workshop_config_defaults(db_exec, default_area_tiles=default_area_tiles)
    where = "" if include_inactive else "WHERE active=1"
    rows = db_exec(
        f"""
        SELECT tile_key, tile_type, display_label, content_area, active, highlighted, sort_order, updated_at
        FROM workshop_hall_tiles
        {where}
        ORDER BY sort_order ASC, tile_key ASC;
        """,
        fetch=True,
    ) or []
    out: list[dict[str, Any]] = []
    for row in rows:
        tile_type = _clean_tile_type(row["tile_type"])
        key = _clean_tile_key(row["tile_key"])
        label = _clean_text(row["display_label"]) or key
        out.append(
            {
                "tile_key": key,
                "tile_type": tile_type,
                "display_label": label,
                "content_area": _clean_area(row["content_area"]),
                "active": bool(row["active"]),
                "highlighted": bool(row["highlighted"]),
                "sort_order": int(row["sort_order"] or 0),
                "updated_at": str(row["updated_at"] or ""),
            }
        )
    return out


def load_workshop_hall_config(
    db_exec: Callable[..., Any],
    *,
    default_area_tiles: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "texts": load_workshop_hall_texts(db_exec),
        "tiles": load_workshop_hall_tiles(
            db_exec,
            default_area_tiles=default_area_tiles,
            include_inactive=False,
        ),
    }


def save_workshop_hall_tile(
    db_exec: Callable[..., Any],
    *,
    tile_key: str,
    tile_type: str = "area",
    display_label: str,
    content_area: str = "",
    active: bool = True,
    highlighted: bool = True,
    sort_order: int = 0,
    updated_at: str = "",
) -> tuple[bool, str]:
    _ensure_workshop_config_schema(db_exec)
    clean_key = _clean_tile_key(tile_key)
    clean_type = _clean_tile_type(tile_type)
    clean_label = _clean_text(display_label)
    clean_area = _clean_area(content_area)
    if not clean_key:
        return False, "Bitte einen Kachel-Code eintragen."
    if not clean_label:
        return False, "Bitte einen Kachel-Titel eintragen."
    if clean_type == "area" and not clean_area:
        return False, "Bitte einen Arbeitsplatz-Bezug eintragen."
    try:
        sort_value = int(sort_order or 0)
    except Exception:
        sort_value = 0
    db_exec(
        """
        INSERT INTO workshop_hall_tiles(
            tile_key, tile_type, display_label, content_area, active, highlighted, sort_order, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(tile_key) DO UPDATE SET
            tile_type=excluded.tile_type,
            display_label=excluded.display_label,
            content_area=excluded.content_area,
            active=excluded.active,
            highlighted=excluded.highlighted,
            sort_order=excluded.sort_order,
            updated_at=excluded.updated_at;
        """,
        (
            clean_key,
            clean_type,
            clean_label,
            clean_area if clean_type == "area" else "",
            1 if bool(active) else 0,
            1 if bool(highlighted) else 0,
            sort_value,
            updated_at,
        ),
        commit=True,
    )
    return True, "Kachel gespeichert."


def delete_workshop_hall_tile(db_exec: Callable[..., Any], *, tile_key: str) -> tuple[bool, str]:
    _ensure_workshop_config_schema(db_exec)
    clean_key = _clean_tile_key(tile_key)
    if not clean_key:
        return False, "Kachel nicht gefunden."
    db_exec("DELETE FROM workshop_hall_tiles WHERE tile_key=?;", (clean_key,), commit=True)
    return True, "Kachel gelöscht."


def reorder_workshop_hall_tiles(
    db_exec: Callable[..., Any],
    *,
    tile_keys: list[str],
    updated_at: str = "",
) -> None:
    _ensure_workshop_config_schema(db_exec)
    for index, raw_key in enumerate(tile_keys):
        key = _clean_tile_key(raw_key)
        if not key:
            continue
        db_exec(
            "UPDATE workshop_hall_tiles SET sort_order=?, updated_at=? WHERE tile_key=?;",
            ((index + 1) * 10, updated_at, key),
            commit=True,
        )


def reset_workshop_hall_config(
    db_exec: Callable[..., Any],
    *,
    default_area_tiles: list[dict[str, Any]] | None = None,
    updated_at: str = "",
) -> None:
    _ensure_workshop_config_schema(db_exec)
    db_exec("DELETE FROM workshop_hall_tiles;", commit=True)
    db_exec("DELETE FROM workshop_hall_texts;", commit=True)
    _seed_workshop_config_defaults(db_exec, default_area_tiles=default_area_tiles, updated_at=updated_at)
