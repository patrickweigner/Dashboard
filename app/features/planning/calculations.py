from __future__ import annotations

from datetime import datetime
from typing import Any


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def resolve_time_rule(rules: list[dict[str, Any]], vehicle_type_code: str, friststufe: str) -> dict[str, Any] | None:
    vehicle_norm = str(vehicle_type_code or "").strip().upper()
    frist_norm = str(friststufe or "").strip().upper()
    best_specific: dict[str, Any] | None = None
    best_generic: dict[str, Any] | None = None
    for rule in rules:
        if str(rule.get("friststufe") or "").strip().upper() != frist_norm:
            continue
        rule_vehicle = str(rule.get("vehicle_type_code") or "").strip().upper()
        if rule_vehicle and rule_vehicle == vehicle_norm:
            best_specific = rule
            break
        if not rule_vehicle:
            best_generic = rule
    return best_specific or best_generic


def calculate_required_minutes(base_minutes: int, extra_minutes: int) -> int:
    return max(0, int(base_minutes) + int(extra_minutes))


def calculate_planned_minutes(start_dt: Any, end_dt: Any) -> int:
    start = _parse_dt(start_dt)
    end = _parse_dt(end_dt)
    if start is None or end is None:
        return 0
    delta_seconds = max(0.0, (end - start).total_seconds())
    return int(round(delta_seconds / 60.0))


def calculate_required_stand_minutes(required_minutes: int, stand_factor: float, stand_minutes_min: int) -> int:
    computed = int(round(max(0, int(required_minutes)) * float(stand_factor)))
    return max(int(stand_minutes_min), computed)


def build_capacity_result(
    *,
    base_minutes: int,
    extra_minutes: int,
    stand_factor: float,
    stand_minutes_min: int,
    planned_minutes: int,
) -> dict[str, Any]:
    required_minutes = calculate_required_minutes(base_minutes, extra_minutes)
    required_stand_minutes = calculate_required_stand_minutes(required_minutes, stand_factor, stand_minutes_min)
    delta_minutes = int(planned_minutes) - int(required_minutes)
    stand_delta_minutes = int(planned_minutes) - int(required_stand_minutes)
    return {
        "required_minutes": required_minutes,
        "planned_minutes": int(planned_minutes),
        "required_stand_minutes": required_stand_minutes,
        "delta_minutes": delta_minutes,
        "stand_delta_minutes": stand_delta_minutes,
        "fits_required_time": delta_minutes >= 0,
        "fits_required_stand_time": stand_delta_minutes >= 0,
    }
