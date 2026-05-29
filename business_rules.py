import re


def _norm_str(x) -> str:
    if x is None:
        return ""
    return str(x).strip()


def make_sig(fahrzeug: str, friststufe: str, anfang_iso: str | None, fertig_iso: str | None) -> str:
    a = _norm_str(anfang_iso)[:16]  # YYYY-MM-DDTHH:MM
    f = _norm_str(fertig_iso)[:16]
    return f"{_norm_str(fahrzeug).lower()}|{_norm_str(friststufe).lower()}|{a}|{f}"


def frist_items_for_vehicle_and_frist(fahrzeug: str, friststufe: str, base_items: list[str]) -> list[str]:
    items = list(base_items) if base_items else []
    fzg_u = (fahrzeug or "").strip().upper()
    fr = str(friststufe or "")

    want_rundlauf = False

    if (fzg_u.startswith("VT646.") or fzg_u.startswith("ET445.")) and re.search(r"\bIS(?:4|5)\b", fr, flags=re.I):
        want_rundlauf = True

    if (fzg_u.startswith("ET4746.") or fzg_u.startswith("ET4748.")) and re.search(r"\bF3\b", fr, flags=re.I):
        want_rundlauf = True

    if fzg_u.startswith("VT1622.") and re.search(r"\bF4\b", fr, flags=re.I):
        want_rundlauf = True

    if want_rundlauf:
        items = [
            ("Calipri mit Rundlaufmessung" if str(it).casefold() == "calipri" else it)
            for it in items
        ]

    return items
