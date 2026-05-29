from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd


def configure(**deps) -> None:
    globals().update(deps)


def _core_utils_module():
    from core import utils as module

    module.configure(
        AREA_DISPLAY_NAMES=AREA_DISPLAY_NAMES,
        BERLIN=BERLIN,
        RX_VEHICLE=RX_VEHICLE,
        RX_WASH_TOKEN=RX_WASH_TOKEN,
    )
    return module


def make_sig(fahrzeug: str, friststufe: str, anfang_iso: str | None, fertig_iso: str | None) -> str:
    return _core_utils_module().make_sig(fahrzeug, friststufe, anfang_iso, fertig_iso)


def now_berlin() -> datetime:
    return _core_utils_module().now_berlin()


def _is_wash_zus_item(text: Any) -> bool:
    return _core_utils_module()._is_wash_zus_item(text)


def as_berlin(dt: Any) -> datetime | None:
    return _core_utils_module().as_berlin(dt)


def _coerce_berlin_datetime_series(series: pd.Series, *, naive: bool = False) -> pd.Series:
    return _core_utils_module()._coerce_berlin_datetime_series(series, naive=naive)


def _clean_nullable_text(value: Any) -> str:
    return _core_utils_module()._clean_nullable_text(value)


def _clean_nullable_db_text(value: Any) -> str | None:
    return _core_utils_module()._clean_nullable_db_text(value)


def _planned_deadline_text(primary_value: Any, fallback_value: Any = None) -> str:
    return _core_utils_module()._planned_deadline_text(primary_value, fallback_value)


def _planned_deadline_dt(primary_value: Any, fallback_value: Any = None) -> datetime | None:
    return _core_utils_module()._planned_deadline_dt(primary_value, fallback_value)


def fmt_dt(dt: Any) -> str:
    return _core_utils_module().fmt_dt(dt)


def fmt_duration(seconds: float) -> str:
    return _core_utils_module().fmt_duration(seconds)


def _norm(x: Any) -> str:
    return _core_utils_module()._norm(x)


def _norm_vehicle(vraw: str) -> str:
    return _core_utils_module()._norm_vehicle(vraw)


def _clean_ap(ap: Any) -> str:
    return _core_utils_module()._clean_ap(ap)


def _append_text(old_text: str, new_text: str) -> str:
    return _core_utils_module()._append_text(old_text, new_text)


def _append_unique_inline_text(old_text: Any, new_text: Any, *, sep: str = " ? ") -> str:
    return _core_utils_module()._append_unique_inline_text(old_text, new_text, sep=sep)


def _append_unique_multiline_text(old_text: Any, new_text: Any) -> str:
    return _core_utils_module()._append_unique_multiline_text(old_text, new_text)


def _display_area_name(area_code: Any) -> str:
    return _core_utils_module()._display_area_name(area_code)


def load_ecm4_planung_xlsx(excel_path: str, sheet_name: str = "ECM 4 Planung") -> pd.DataFrame:
    df = pd.read_excel(excel_path, sheet_name=sheet_name, engine="openpyxl")
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df


def _presentation_module():
    from components import presentation as module

    module.configure(
        WORKSHOP_AREAS=WORKSHOP_AREAS,
        _clean_ap=_clean_ap,
        _clean_problem_note=_clean_problem_note,
        as_berlin=as_berlin,
        now_berlin=now_berlin,
        fmt_duration=fmt_duration,
    )
    return module


def status_for_row(row: pd.Series, *, include_problem: bool = True) -> tuple[str, str]:
    return _presentation_module().status_for_row(row, include_problem=include_problem)


def status_palette(status_key: str) -> tuple[str, str]:
    return _presentation_module().status_palette(status_key)


def _badge_style(bg: str, fg: str, *, extra: str = "") -> str:
    return _presentation_module()._badge_style(bg, fg, extra=extra)


def render_badge_stack(
    label: str,
    value: str,
    bg: str,
    fg: str,
    *,
    big: bool = False,
    value_title: str | None = None,
) -> Any:
    return _presentation_module().render_badge_stack(
        label,
        value,
        bg,
        fg,
        big=big,
        value_title=value_title,
    )


def render_pill_label(
    text: str,
    bg: str,
    fg: str,
    *,
    classes: str = "",
    extra: str = "",
    tooltip: str | None = None,
) -> Any:
    return _presentation_module().render_pill_label(
        text,
        bg,
        fg,
        classes=classes,
        extra=extra,
        tooltip=tooltip,
    )


def render_time_badge(
    text: str,
    bg: str,
    fg: str,
    *,
    side: bool = False,
    multiline: bool = False,
) -> Any:
    return _presentation_module().render_time_badge(
        text,
        bg,
        fg,
        side=side,
        multiline=multiline,
    )


def badge_html(
    label: str,
    value: str,
    bg: str,
    fg: str,
    *,
    big: bool = False,
    value_id: str | None = None,
    value_title: str | None = None,
) -> str:
    return _presentation_module().badge_html(
        label,
        value,
        bg,
        fg,
        big=big,
        value_id=value_id,
        value_title=value_title,
    )


def effective_area(row: pd.Series, *, allow_pdf_fallback: bool = True) -> str:
    return _presentation_module().effective_area(row, allow_pdf_fallback=allow_pdf_fallback)


def display_workplace(row: pd.Series) -> str:
    return _presentation_module().display_workplace(row)


def format_problem_lines(note_text: Any, *, limit: int | None = None) -> list[str]:
    return _presentation_module().format_problem_lines(note_text, limit=limit)


def inject_due24_watcher(
    end_dt: datetime,
    *,
    veh_id: str | None = None,
    frist_id: str | None = None,
    start_id: str | None = None,
    end_id: str | None = None,
    area_id: str | None = None,
    cd_id: str | None = None,
    status_id: str | None = None,
    has_problem: bool = False,
) -> None:
    _presentation_module().inject_due24_watcher(
        end_dt,
        veh_id=veh_id,
        frist_id=frist_id,
        start_id=start_id,
        end_id=end_id,
        area_id=area_id,
        cd_id=cd_id,
        status_id=status_id,
        has_problem=has_problem,
    )


def render_countdown_badge(
    end_dt: datetime,
    *,
    key: str,
    badge_bg: str = "#faad14",
    badge_fg: str = "#000000",
) -> None:
    _presentation_module().render_countdown_badge(
        end_dt,
        key=key,
        badge_bg=badge_bg,
        badge_fg=badge_fg,
    )
