from __future__ import annotations

from typing import Any, Callable

from nicegui import ui


_OPEN_DIALOG_IDS: set[int] = set()


def _umlautify_text(value: Any) -> Any:
    if not isinstance(value, str) or not value:
        return value
    out = str(value)
    for _ in range(2):
        try:
            fixed = out.encode("latin-1").decode("utf-8")
        except UnicodeError:
            break
        if fixed == out:
            break
        out = fixed
    return out


def _umlautify_options(options: Any) -> Any:
    if isinstance(options, dict):
        return {k: _umlautify_text(v) for k, v in options.items()}
    if isinstance(options, list):
        out_list: list[Any] = []
        for item in options:
            if isinstance(item, str):
                out_list.append(_umlautify_text(item))
            elif isinstance(item, dict):
                cp = dict(item)
                if isinstance(cp.get("label"), str):
                    cp["label"] = _umlautify_text(cp["label"])
                out_list.append(cp)
            else:
                out_list.append(item)
        return out_list
    if isinstance(options, tuple):
        return tuple(_umlautify_options(list(options)))
    return options


def _patch_ui_umlauts() -> None:
    if bool(getattr(ui, "_umlaut_patch_active", False)):
        return

    _orig_label = ui.label
    _orig_button = ui.button
    _orig_notify = ui.notify
    _orig_input = ui.input
    _orig_textarea = ui.textarea
    _orig_select = ui.select
    _orig_checkbox = ui.checkbox
    _orig_upload = ui.upload
    _orig_table = ui.table

    def _with_select_popup_defaults(element: Any) -> Any:
        try:
            element.props("popup-content-class=area-select-popup behavior=menu")
            element._props["options-cover"] = False
        except Exception:
            pass
        return element

    def _label_wrapper(text: Any = "", *args, **kwargs):
        return _orig_label(_umlautify_text(text), *args, **kwargs)

    def _button_wrapper(text: Any = "", *args, **kwargs):
        if "text" in kwargs:
            kwargs["text"] = _umlautify_text(kwargs["text"])
            return _orig_button(*args, **kwargs)
        return _orig_button(_umlautify_text(text), *args, **kwargs)

    def _notify_wrapper(message: Any = None, *args, **kwargs):
        if "message" in kwargs:
            kwargs["message"] = _umlautify_text(kwargs["message"])
            return _orig_notify(*args, **kwargs)
        return _orig_notify(_umlautify_text(message), *args, **kwargs)

    def _input_wrapper(label: Any = None, *args, **kwargs):
        if "label" in kwargs:
            kwargs["label"] = _umlautify_text(kwargs["label"])
            return _orig_input(*args, **kwargs)
        return _orig_input(_umlautify_text(label), *args, **kwargs)

    def _textarea_wrapper(label: Any = None, *args, **kwargs):
        if "label" in kwargs:
            kwargs["label"] = _umlautify_text(kwargs["label"])
            return _orig_textarea(*args, **kwargs)
        return _orig_textarea(_umlautify_text(label), *args, **kwargs)

    def _select_wrapper(options: Any = None, *args, **kwargs):
        if "options" in kwargs:
            kwargs["options"] = _umlautify_options(kwargs["options"])
            if "label" in kwargs:
                kwargs["label"] = _umlautify_text(kwargs["label"])
            return _with_select_popup_defaults(_orig_select(*args, **kwargs))
        if "label" in kwargs:
            kwargs["label"] = _umlautify_text(kwargs["label"])
        return _with_select_popup_defaults(_orig_select(_umlautify_options(options), *args, **kwargs))

    def _checkbox_wrapper(text: Any = "", *args, **kwargs):
        if "text" in kwargs:
            kwargs["text"] = _umlautify_text(kwargs["text"])
            return _orig_checkbox(*args, **kwargs)
        return _orig_checkbox(_umlautify_text(text), *args, **kwargs)

    def _upload_wrapper(*args, **kwargs):
        if "label" in kwargs:
            kwargs["label"] = _umlautify_text(kwargs["label"])
            return _orig_upload(*args, **kwargs)
        if args and isinstance(args[0], str):
            args = (_umlautify_text(args[0]),) + tuple(args[1:])
        return _orig_upload(*args, **kwargs)

    def _table_wrapper(*args, **kwargs):
        if "columns" in kwargs:
            cols = kwargs["columns"]
        elif args:
            cols = args[0]
        else:
            cols = None

        if isinstance(cols, list):
            new_cols: list[Any] = []
            for col in cols:
                if isinstance(col, dict):
                    cp = dict(col)
                    if isinstance(cp.get("label"), str):
                        cp["label"] = _umlautify_text(cp["label"])
                    new_cols.append(cp)
                else:
                    new_cols.append(col)
            if "columns" in kwargs:
                kwargs["columns"] = new_cols
            else:
                args = (new_cols,) + tuple(args[1:])
        return _orig_table(*args, **kwargs)

    ui.label = _label_wrapper
    ui.button = _button_wrapper
    ui.notify = _notify_wrapper
    ui.input = _input_wrapper
    ui.textarea = _textarea_wrapper
    ui.select = _select_wrapper
    ui.checkbox = _checkbox_wrapper
    ui.upload = _upload_wrapper
    ui.table = _table_wrapper
    setattr(ui, "_umlaut_patch_active", True)


def _mark_dialog_open(dialog: Any) -> None:
    _OPEN_DIALOG_IDS.add(id(dialog))


def _mark_dialog_closed(dialog: Any) -> None:
    _OPEN_DIALOG_IDS.discard(id(dialog))


def _has_open_dialog() -> bool:
    return bool(_OPEN_DIALOG_IDS)


def _attach_dialog_tracking(dialog: Any) -> None:
    try:
        dialog.on("show", lambda _e, d=dialog: _mark_dialog_open(d))
        dialog.on("hide", lambda _e, d=dialog: _mark_dialog_closed(d))
    except Exception:
        pass


def _open_tracked_dialog(dialog: Any) -> None:
    _mark_dialog_open(dialog)
    dialog.open()


def _close_tracked_dialog(dialog: Any) -> None:
    try:
        dialog.close()
    finally:
        _mark_dialog_closed(dialog)


def _refresh_when_no_dialog(refresh_fn: Callable[[], None]) -> bool:
    if _has_open_dialog():
        return False
    refresh_fn()
    return True


def create_page_timer(interval: float, callback: Callable[[], Any]) -> Any:
    """Create a page-bound timer and remove it before NiceGUI deletes its client.

    NiceGUI page timers are elements. If their client is deleted while the timer
    task is still sleeping, the timer cleanup can otherwise touch a deleted
    parent slot on the next tick.
    """

    state: dict[str, bool] = {"closed": False}
    holder: dict[str, Any] = {}

    def _guarded_callback() -> Any:
        timer = holder.get("timer")
        if state["closed"] or bool(getattr(timer, "is_deleted", False)):
            return None
        try:
            return callback()
        except RuntimeError as exc:
            if "parent slot of the element has been deleted" in str(exc):
                state["closed"] = True
                _cancel_timer(timer)
                return None
            raise

    def _cancel_timer(timer: Any) -> None:
        if timer is None:
            return
        try:
            timer.cancel(with_current_invocation=True)
        except TypeError:
            try:
                timer.cancel()
            except Exception:
                pass
        except Exception:
            pass

    def _cleanup_timer(*_args: Any) -> None:
        state["closed"] = True
        timer = holder.get("timer")
        _cancel_timer(timer)
        if timer is None or bool(getattr(timer, "is_deleted", False)):
            return
        try:
            timer.delete()
        except RuntimeError as exc:
            if "parent slot of the element has been deleted" not in str(exc):
                raise
        except Exception:
            pass

    timer = ui.timer(interval, _guarded_callback)
    holder["timer"] = timer
    try:
        ui.context.client.on_delete(_cleanup_timer)
    except Exception:
        pass
    return timer


def ensure_problem_state() -> None:
    return


def ensure_overdue_state() -> None:
    return
