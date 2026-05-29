from __future__ import annotations

import re
from typing import Any


DEFAULT_PLACES = ["4A", "4B", "5A", "5B", "ARA"]
DEFAULT_CAPACITY_SLOTS = [
    "2:00 - 6:00",
    "6:00 - 10:00",
    "10:00 - 14:18",
    "14:00 - 18:00",
    "18:00 - 22:18",
    "21:42 - 2:00",
]
DEFAULT_RULE_PRIORITY = "neutral"
RULE_PRIORITIES = ("preferred", "neutral", "discouraged")
JOB_STATUS_DRAFT = "draft"
JOB_STATUS_PLANNED = "planned"
JOB_STATUS_CONFLICT = "conflict"
JOB_STATUSES = (JOB_STATUS_DRAFT, JOB_STATUS_PLANNED, JOB_STATUS_CONFLICT)

_RX_VEHICLE_TYPE = re.compile(r"\b([A-Z]{2,4}\s*\d{2,5})", re.I)


def normalize_place_code(value: Any) -> str:
    text = str(value or "").strip().upper()
    return re.sub(r"\s+", "", text)


def normalize_friststufe(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().upper())


def normalize_vehicle_type_code(value: Any) -> str:
    text = str(value or "").strip().upper()
    return re.sub(r"\s+", "", text)


def detect_vehicle_type(fahrzeug: Any) -> str:
    text = str(fahrzeug or "").strip().upper()
    if not text:
        return ""
    match = _RX_VEHICLE_TYPE.search(text)
    if not match:
        return ""
    return normalize_vehicle_type_code(match.group(1))


def coerce_priority(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in RULE_PRIORITIES else DEFAULT_RULE_PRIORITY


def coerce_job_status(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in JOB_STATUSES else JOB_STATUS_DRAFT


def normalize_slot_label(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())
