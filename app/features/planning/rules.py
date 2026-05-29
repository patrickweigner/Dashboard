from __future__ import annotations

from typing import Any

from .models import DEFAULT_RULE_PRIORITY, normalize_place_code, normalize_vehicle_type_code
from .repository import list_place_rules, list_places


def is_place_allowed(vehicle_type_code: str, place_code: str, *, db_path: str | None = None) -> tuple[bool, str]:
    vehicle_norm = normalize_vehicle_type_code(vehicle_type_code)
    place_norm = normalize_place_code(place_code)
    if not vehicle_norm or not place_norm:
        return False, "Fahrzeugtyp oder Arbeitsplatz fehlt."

    matching_rules = list_place_rules(
        vehicle_type_code=vehicle_norm,
        place_code=place_norm,
        active_only=True,
        db_path=db_path,
    )
    if matching_rules:
        rule = matching_rules[0]
        allowed = bool(rule.get("allowed"))
        reason = str(rule.get("reason") or "").strip()
        if allowed:
            return True, reason or "Arbeitsplatz ist für den Fahrzeugtyp erlaubt."
        return False, reason or "Arbeitsplatz ist für den Fahrzeugtyp ausgeschlossen."

    return True, "Keine Ausnahme hinterlegt. Arbeitsplatz ist standardmäßig erlaubt."


def get_allowed_places(vehicle_type_code: str, *, db_path: str | None = None) -> list[str]:
    vehicle_norm = normalize_vehicle_type_code(vehicle_type_code)
    if not vehicle_norm:
        return []
    places = list_places(active_only=True, db_path=db_path)
    rules = list_place_rules(vehicle_type_code=vehicle_norm, active_only=True, db_path=db_path)
    blocked_codes = {str(rule.get("place_code") or "").strip() for rule in rules if not bool(rule.get("allowed"))}
    return [str(place.get("code") or "").strip() for place in places if str(place.get("code") or "").strip() not in blocked_codes]


def get_place_rule_summary(vehicle_type_code: str, *, db_path: str | None = None) -> list[dict[str, Any]]:
    vehicle_norm = normalize_vehicle_type_code(vehicle_type_code)
    places = list_places(active_only=True, db_path=db_path)
    rules = {
        str(item.get("place_code") or "").strip(): item
        for item in list_place_rules(vehicle_type_code=vehicle_norm, active_only=True, db_path=db_path)
    }
    summary: list[dict[str, Any]] = []
    for place in places:
        code = str(place.get("code") or "").strip()
        rule = rules.get(code)
        allowed = True if rule is None else bool(rule.get("allowed"))
        reason = str(rule.get("reason") or "").strip() if rule else "Keine Ausnahme hinterlegt."
        summary.append(
            {
                "place_code": code,
                "place_label": str(place.get("label") or code),
                "allowed": allowed,
                "priority": str(rule.get("priority") or DEFAULT_RULE_PRIORITY) if rule else DEFAULT_RULE_PRIORITY,
                "reason": reason,
            }
        )
    return summary
