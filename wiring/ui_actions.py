from __future__ import annotations

from typing import Callable

import pandas as pd
from nicegui import ui


def configure(**deps) -> None:
    globals().update(deps)


def render_nav() -> None:
    from components.nav import render_nav as _render_nav

    _render_nav(
        ensure_problem_state=ensure_problem_state,
        ensure_overdue_state=ensure_overdue_state,
        auto_clear_shopfloorboard_5s_if_due=auto_clear_shopfloorboard_5s_if_due,
        start_lwu_reminder_worker=start_lwu_reminder_worker,
        is_admin=is_admin,
        is_configuration_user=is_configuration_user,
        can_view_page=can_view_page,
        has_login_passwords=_has_login_passwords,
        logout_admin=_logout_admin,
        open_admin_login_dialog=open_admin_login_dialog,
        show_db_path_in_nav=SHOW_DB_PATH_IN_NAV,
        db_path=DB_PATH,
        btn_bg=BTN_BG,
    )


def open_admin_login_dialog(
    *,
    on_success: Callable[[], None] | None = None,
    reload_on_success: bool = True,
    title: str = "Login",
    hint: str | None = None,
) -> None:
    from components.nav import open_admin_login_dialog as _open_admin_login_dialog

    _open_admin_login_dialog(
        attach_dialog_tracking=_attach_dialog_tracking,
        close_tracked_dialog=_close_tracked_dialog,
        has_login_passwords=_has_login_passwords,
        resolve_login_role=_resolve_login_role,
        set_admin=_set_admin,
        login_success_text=_login_success_text,
        open_tracked_dialog=_open_tracked_dialog,
        on_success=on_success,
        reload_on_success=reload_on_success,
        title=title,
        hint=hint,
    )


def render_legend() -> None:
    from components.task_cards import render_legend as _render_legend

    _render_legend()


def build_task_card(row: pd.Series, refresh_fn, *, show_area_controls: bool = False) -> None:
    from components.task_cards import build_task_card as _build_task_card

    _build_task_card(
        row,
        refresh_fn,
        show_area_controls=show_area_controls,
        fmt_dt=fmt_dt,
        effective_area=effective_area,
        display_workplace=display_workplace,
        status_for_row=status_for_row,
        status_palette=status_palette,
        calc_zus_progress=_calc_zus_progress,
        calc_frist_progress=_calc_frist_progress,
        decode_check_string=_decode_check_string,
        clean_problem_note=_clean_problem_note,
        as_berlin=as_berlin,
        is_admin=is_admin,
        enforce_admin_uncheck_rule=_enforce_admin_uncheck_rule,
        db_exec=db_exec,
        encode_check_list=_encode_check_list,
        render_badge_stack=render_badge_stack,
        workshop_areas=WORKSHOP_AREAS,
        assign_area=assign_area,
        complete_task_action=complete_task_action,
        open_zus_dialog=open_zus_dialog,
        open_frist_dialog=open_frist_dialog,
        open_problem_dialog=open_problem_dialog,
        inject_due24_watcher=inject_due24_watcher,
        format_problem_lines=format_problem_lines,
        render_pill_label=render_pill_label,
    )


def open_zus_dialog(task_id: int, refresh_fn: Callable[[], None]) -> None:
    from components.dialogs import open_zus_dialog as _open_zus_dialog

    _open_zus_dialog(
        task_id,
        refresh_fn,
        get_open_tasks_df=get_open_tasks_df,
        is_admin=is_admin,
        _attach_dialog_tracking=_attach_dialog_tracking,
        _close_tracked_dialog=_close_tracked_dialog,
        _calc_zus_progress=_calc_zus_progress,
        _enforce_admin_uncheck_rule=_enforce_admin_uncheck_rule,
        db_exec=db_exec,
        _encode_check_list=_encode_check_list,
        _open_tracked_dialog=_open_tracked_dialog,
    )


def open_frist_dialog(task_id: int, area_code: str, refresh_fn: Callable[[], None]) -> None:
    from components.dialogs import open_frist_dialog as _open_frist_dialog

    _open_frist_dialog(
        task_id,
        area_code,
        refresh_fn,
        get_open_tasks_df=get_open_tasks_df,
        is_admin=is_admin,
        _attach_dialog_tracking=_attach_dialog_tracking,
        _close_tracked_dialog=_close_tracked_dialog,
        _calc_frist_progress=_calc_frist_progress,
        _enforce_admin_uncheck_rule=_enforce_admin_uncheck_rule,
        db_exec=db_exec,
        _encode_check_list=_encode_check_list,
        _decode_check_string=_decode_check_string,
        _open_tracked_dialog=_open_tracked_dialog,
    )


def open_problem_dialog(task_id: int, refresh_fn: Callable[[], None]) -> None:
    from components.dialogs import open_problem_dialog as _open_problem_dialog

    _open_problem_dialog(
        task_id,
        refresh_fn,
        get_open_tasks_df=get_open_tasks_df,
        _attach_dialog_tracking=_attach_dialog_tracking,
        _close_tracked_dialog=_close_tracked_dialog,
        PROBLEM_OPTIONS=PROBLEM_OPTIONS,
        pin_problem=pin_problem,
        _build_delay_payload=_build_delay_payload,
        notify_delay=notify_delay,
        _open_tracked_dialog=_open_tracked_dialog,
    )


def open_overdue_dialog_for(task_id: int, refresh_fn: Callable[[], None]) -> None:
    from components.dialogs import open_overdue_dialog_for as _open_overdue_dialog_for

    _open_overdue_dialog_for(
        task_id,
        refresh_fn,
        db_exec=db_exec,
        _planned_deadline_dt=_planned_deadline_dt,
        _clean_problem_note=_clean_problem_note,
        PROBLEM_OPTIONS=PROBLEM_OPTIONS,
        pin_problem=pin_problem,
        archive_task=archive_task,
        _archive_notify_type=_archive_notify_type,
        _attach_dialog_tracking=_attach_dialog_tracking,
        _close_tracked_dialog=_close_tracked_dialog,
        _open_tracked_dialog=_open_tracked_dialog,
    )


def open_overdue_dialog(task_id: int, refresh_fn: Callable[[], None]) -> None:
    from components.dialogs import open_overdue_dialog as _open_overdue_dialog

    _open_overdue_dialog(
        task_id,
        refresh_fn,
        db_exec=db_exec,
        _planned_deadline_dt=_planned_deadline_dt,
        _clean_problem_note=_clean_problem_note,
        PROBLEM_OPTIONS=PROBLEM_OPTIONS,
        pin_problem=pin_problem,
        archive_task=archive_task,
        _archive_notify_type=_archive_notify_type,
        _attach_dialog_tracking=_attach_dialog_tracking,
        _close_tracked_dialog=_close_tracked_dialog,
        _open_tracked_dialog=_open_tracked_dialog,
    )


def complete_task_action(task_id: int, refresh_fn: Callable[[], None]) -> None:
    if not is_admin():
        open_admin_login_dialog(
            on_success=lambda tid=int(task_id): complete_task_action(tid, refresh_fn),
            reload_on_success=False,
            title="Passwort für Erledigt",
        )
        return
    row = db_exec("SELECT initial_fertig, fertig, friststufe FROM open_tasks WHERE id=?;", (int(task_id),), fetchone=True)
    if not row:
        ui.notify("Datensatz nicht gefunden.", type="warning")
        refresh_fn()
        return
    init_dt = _planned_deadline_dt(row["initial_fertig"], row["fertig"])
    if _requires_overdue_reason_for_frist(row["friststufe"]) and init_dt and now_berlin() > init_dt:
        open_overdue_dialog_for(int(task_id), refresh_fn)
        return
    ok, msg = archive_task(int(task_id))
    ui.notify(msg, type=_archive_notify_type(ok, msg))
    refresh_fn()


def open_new_order_dialog(refresh_fn: Callable[[], None]) -> None:
    from components.dialogs import open_new_order_dialog as _open_new_order_dialog

    _open_new_order_dialog(
        refresh_fn,
        _attach_dialog_tracking=_attach_dialog_tracking,
        _close_tracked_dialog=_close_tracked_dialog,
        _open_tracked_dialog=_open_tracked_dialog,
        now_berlin=now_berlin,
        _get_existing_open_by_vehicle=_get_existing_open_by_vehicle,
        as_berlin=as_berlin,
        BERLIN=BERLIN,
        create_or_update_open_task_manual=create_or_update_open_task_manual,
    )
