from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd


def configure(**deps) -> None:
    globals().update(deps)


def _task_rules_module():
    from core import task_rules as module

    module.configure(
        BERLIN=BERLIN,
        FRIST_CHECK_ITEMS=FRIST_CHECK_ITEMS,
        _fr_items_for_vehicle_and_frist=_fr_items_for_vehicle_and_frist,
        _configured_work_package_titles_for_vehicle_and_frist=_configured_work_package_titles_for_vehicle_and_frist,
        _build_slots_for_day=_build_slots_for_day,
        _display_vehicle_code=_display_vehicle_code,
        _norm=_norm,
        _norm_vehicle=_norm_vehicle,
        _shift_day=_shift_day,
        _slot_end_for_start=_slot_end_for_start,
        as_berlin=as_berlin,
    )
    return module


def _short_gewerk_label(text: Any) -> str:
    return _task_rules_module()._short_gewerk_label(text)


def _parse_gewerke_entries(raw_text: Any) -> list[dict[str, Any]]:
    return _task_rules_module()._parse_gewerke_entries(raw_text)


def _slot_start_for_timestamp(event_dt: datetime | None) -> datetime | None:
    return _task_rules_module()._slot_start_for_timestamp(event_dt)


def _collect_gewerke_slot_events(
    df_open: pd.DataFrame | None,
    *,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
) -> list[dict[str, Any]]:
    return _task_rules_module()._collect_gewerke_slot_events(
        df_open,
        window_start=window_start,
        window_end=window_end,
    )


def _clean_problem_note(note_text: Any) -> str:
    return _task_rules_module()._clean_problem_note(note_text)


def _vehicle_compare_key(vraw: Any) -> str:
    return _task_rules_module()._vehicle_compare_key(vraw)


def _is_urd_like(row: pd.Series, area_code: str | None = None) -> bool:
    return _task_rules_module()._is_urd_like(row, area_code=area_code)


def _is_urd_open_row(row: pd.Series) -> bool:
    return _task_rules_module()._is_urd_open_row(row)


def _parse_zusatz_items(zusatz_raw: Any) -> list[str]:
    return _task_rules_module()._parse_zusatz_items(zusatz_raw)


def _canon_zus_item_key(item: Any) -> str:
    return _task_rules_module()._canon_zus_item_key(item)


def _decode_check_string(raw: Any, length: int) -> list[bool]:
    return _task_rules_module()._decode_check_string(raw, length)


def _encode_check_list(bits: list[bool]) -> str:
    return _task_rules_module()._encode_check_list(bits)


def _frist_items_for_row(row: pd.Series) -> list[str]:
    return _task_rules_module()._frist_items_for_row(row)


def _fold_match_text(value: Any) -> str:
    return _task_rules_module()._fold_match_text(value)


def _frist_has_non_hu_component(frist_value: Any) -> bool:
    return _task_rules_module()._frist_has_non_hu_component(frist_value)


def _is_frist_check_applicable(row: pd.Series, area_code: str | None = None) -> bool:
    return _task_rules_module()._is_frist_check_applicable(row, area_code=area_code)


def _requires_overdue_reason_for_frist(frist_value: Any) -> bool:
    return _task_rules_module()._requires_overdue_reason_for_frist(frist_value)


def _calc_zus_progress(row: pd.Series) -> tuple[int, int, list[str], list[bool]]:
    return _task_rules_module()._calc_zus_progress(row)


def _calc_frist_progress(row: pd.Series, area_code: str | None) -> tuple[int, int, list[str], list[bool], bool]:
    return _task_rules_module()._calc_frist_progress(row, area_code)


def _row_allows_area(row: pd.Series, area_code: str) -> bool:
    return _task_rules_module()._row_allows_area(row, area_code)


def _normalize_workshop_area(area_code: Any) -> str:
    return _task_rules_module()._normalize_workshop_area(area_code)


def _zus_added_only(old_zus: Any, new_zus: Any) -> str:
    return _task_rules_module()._zus_added_only(old_zus, new_zus)
