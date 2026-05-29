from __future__ import annotations

import html
import json
import re
from datetime import datetime
from typing import Any

import pandas as pd
from nicegui import ui


WORKSHOP_AREAS: list[str] = []
_clean_ap = None
_clean_problem_note = None
as_berlin = None
now_berlin = None
fmt_duration = None

STATUS_CLASS = {
    "green": "status-green",
    "yellow": "status-yellow",
    "yellow_problem": "status-yellow-problem",
    "red": "status-red",
    "neutral": "status-neutral",
}

def configure(
    *,
    WORKSHOP_AREAS: list[str],
    _clean_ap,
    _clean_problem_note,
    as_berlin,
    now_berlin,
    fmt_duration,
) -> None:
    globals()["WORKSHOP_AREAS"] = list(WORKSHOP_AREAS)
    globals()["_clean_ap"] = _clean_ap
    globals()["_clean_problem_note"] = _clean_problem_note
    globals()["as_berlin"] = as_berlin
    globals()["now_berlin"] = now_berlin
    globals()["fmt_duration"] = fmt_duration


def status_for_row(row: pd.Series, *, include_problem: bool = True) -> tuple[str, str]:
    end_dt = as_berlin(row.get("Fertig"))
    has_problem = bool(_clean_problem_note(row.get("last_problem_note")))
    if end_dt is None:
        return "neutral", "Kein Ende"
    diff = (end_dt - now_berlin()).total_seconds()
    if diff <= 0:
        return "red", f"Fristfertigstellung seit {fmt_duration(abs(diff))}"
    if diff <= 24 * 3600:
        if include_problem and has_problem:
            return "yellow_problem", f"Fristfertigstellung in {fmt_duration(diff)}"
        return "yellow", f"Fristfertigstellung in {fmt_duration(diff)}"
    if include_problem and has_problem:
        return "yellow_problem", "Problem gemeldet"
    return "green", "Im Plan"


def status_palette(status_key: str) -> tuple[str, str]:
    if status_key == "green":
        return "#52c41a", "#ffffff"
    if status_key == "yellow":
        return "#faad14", "#000000"
    if status_key == "yellow_problem":
        return "#ffeb3b", "#000000"
    if status_key == "red":
        return "#ff4d4f", "#ffffff"
    return "#f0f2f5", "#000000"


def _badge_style(bg: str, fg: str, *, extra: str = "") -> str:
    parts = [
        f"background:{bg} !important",
        f"background-color:{bg} !important",
        f"color:{fg} !important",
        f"-webkit-text-fill-color:{fg} !important",
    ]
    extra_txt = str(extra or "").strip().strip(";")
    if extra_txt:
        parts.append(extra_txt)
    return ";".join(parts) + ";"


def _html_to_multiline_text(value: Any) -> str:
    txt = re.sub(r"(?i)<br\s*/?>", "\n", str(value or ""))
    txt = re.sub(r"<[^>]+>", "", txt)
    return html.unescape(txt)


def render_badge_stack(
    label: str,
    value: str,
    bg: str,
    fg: str,
    *,
    big: bool = False,
    value_title: str | None = None,
) -> Any:
    label_size_class = "badge-label-big" if big else "badge-label-small"
    value_size_class = "badge-pill-big" if big else "badge-pill-small"
    with ui.column().classes("badge-stack"):
        ui.label(str(label)).classes(f"badge-label {label_size_class}")
        badge = ui.label(str(value)).classes(f"badge-pill {value_size_class}").style(_badge_style(bg, fg))
        if value_title:
            badge.tooltip(str(value_title))
    return badge


def render_pill_label(
    text: str,
    bg: str,
    fg: str,
    *,
    classes: str = "",
    extra: str = "",
    tooltip: str | None = None,
) -> Any:
    pill = ui.label(str(text))
    if classes:
        pill.classes(classes)
    pill.style(_badge_style(bg, fg, extra=extra))
    if tooltip:
        pill.tooltip(str(tooltip))
    return pill


def render_time_badge(
    text: str,
    bg: str,
    fg: str,
    *,
    side: bool = False,
    multiline: bool = False,
) -> Any:
    time_classes = "tl-time"
    if side:
        time_classes += " tl-side-time"
    extra = ""
    if multiline:
        extra = "white-space:pre-line;line-height:1.12;min-width:240px;text-align:center"
    content = _html_to_multiline_text(text) if multiline else str(text or "")
    return ui.label(content).classes(time_classes).style(_badge_style(bg, fg, extra=extra))


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
    lsize = "20px" if big else "16px"
    vsize = "30px" if big else "22px"
    id_attr = f" id='{html.escape(str(value_id), quote=True)}'" if value_id else ""
    title_attr = f" title='{html.escape(str(value_title), quote=True)}'" if value_title else ""
    pill_style = _badge_style(bg, fg, extra=f"font-size:{vsize}")
    return (
        "<div class='badge-stack'>"
        f"<div class='badge-label' style='font-size:{lsize}'>{html.escape(str(label))}</div>"
        f"<div{id_attr}{title_attr} class='badge-pill' style='{pill_style}'>{html.escape(str(value))}</div>"
        "</div>"
    )


def effective_area(row: pd.Series, *, allow_pdf_fallback: bool = True) -> str:
    manual = str(row.get("Arbeitsplatz") or "").strip().upper()
    if manual in WORKSHOP_AREAS:
        return manual
    if not allow_pdf_fallback:
        return ""
    ap_pdf = str(row.get("ap_pdf") or "").strip().upper()
    if ap_pdf in WORKSHOP_AREAS:
        return ap_pdf
    return ""


def display_workplace(row: pd.Series) -> str:
    manual = _clean_ap(row.get("Arbeitsplatz"))
    if manual:
        return manual
    return _clean_ap(row.get("ap_pdf"))


def format_problem_lines(note_text: Any, *, limit: int | None = None) -> list[str]:
    lines = [x.strip() for x in str(note_text or "").splitlines() if str(x).strip()]
    if limit and limit > 0:
        lines = lines[-limit:]
    out: list[str] = []
    for line in lines:
        m = re.match(r"^\[(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})\]\s*(.*)$", line)
        if m:
            dd, tt, txt = m.group(1), m.group(2), m.group(3).strip()
            if str(txt or "").strip().casefold() in {"none", "nan", "nat", "null"}:
                continue
            out.append(f"{txt or '-'} (gemeldet {dd} {tt})")
        else:
            if str(line or "").strip().casefold() in {"none", "nan", "nat", "null"}:
                continue
            out.append(line)
    return out


def _inject_live_countdown(
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
    end_loc = as_berlin(end_dt)
    if end_loc is None:
        return

    def js_value(value: str | None) -> str:
        return json.dumps(str(value)) if value else "null"

    ui.add_body_html(
        f"""
        <script>
        (function() {{
            var ROOT = window.parent || window;
            var opts = {{
                endMs:{int(end_loc.timestamp() * 1000)},
                vehId:{js_value(veh_id)},
                fristId:{js_value(frist_id)},
                startId:{js_value(start_id)},
                endId:{js_value(end_id)},
                areaId:{js_value(area_id)},
                cdId:{js_value(cd_id)},
                statusId:{js_value(status_id)},
                hasProblem:{str(bool(has_problem)).lower()},
                green:"#52c41a", greenFg:"#ffffff",
                yellow:"#faad14", yellowFg:"#000000",
                bright:"#ffeb3b", brightFg:"#000000",
                red:"#ff4d4f", redFg:"#ffffff"
            }};
            var tries = 0;
            function go() {{
                var fn = ROOT._watch_due_and_overdue;
                if (typeof fn === "function") {{ fn(opts); return; }}
                tries++;
                if (tries < 60) setTimeout(go, 50);
            }}
            go();
        }})();
        </script>
        """
    )


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
    _inject_live_countdown(
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
    end_loc = as_berlin(end_dt)
    if end_loc is None:
        return
    diff_sec = max(0, (end_loc - now_berlin()).total_seconds())
    _ = key
    badge = render_pill_label(
        f"Fristfertigstellung in {fmt_duration(diff_sec)}",
        badge_bg,
        badge_fg,
        classes="slot-pill",
        extra="display:inline-block",
    )
    inject_due24_watcher(end_loc, cd_id=badge.html_id, has_problem=False)
