from __future__ import annotations

import math
from copy import deepcopy
from typing import Any


EBERSWALDE_LAGEPLAN_TEMPLATE_KEY = "eberswalde_lageplan"
EBERSWALDE_LAGEPLAN_TEMPLATE_LABEL = "Eberswalde Lageplan"


def _pt(x_pct: float, y_pct: float) -> dict[str, float]:
    return {"x_pct": round(float(x_pct), 3), "y_pct": round(float(y_pct), 3)}


GLEISPLAN_TEMPLATE_ASPECT = 1501 / 1058
SWITCH_TEMPLATE_W = 3.7
SWITCH_TEMPLATE_H = 2.0
SWITCH_TEMPLATE_MAIN_Y_RATIO = 0.28
SWITCH_TEMPLATE_HEEL_X_RATIO = 0.80
SWITCH_TEMPLATE_BRANCH_X_RATIO = 0.06
SWITCH_TEMPLATE_BRANCH_Y_RIGHT = 1.35
SWITCH_TEMPLATE_BRANCH_Y_LEFT = -0.75
SWITCH_TEMPLATE_TANGENT_LEAD_PCT = 0.12


def _visual_angle(a: tuple[float, float], b: tuple[float, float]) -> float:
    dx = float(b[0]) - float(a[0])
    dy = (float(b[1]) - float(a[1])) / GLEISPLAN_TEMPLATE_ASPECT
    return (math.degrees(math.atan2(dy, dx)) + 360.0) % 360.0


def _angle_delta(a: float, b: float) -> float:
    return abs(((float(a) - float(b) + 180.0) % 360.0) - 180.0)


def _point_from_dir(point: dict[str, Any], direction_deg: float, distance_pct: float = SWITCH_TEMPLATE_TANGENT_LEAD_PCT) -> dict[str, float]:
    angle = math.radians(float(direction_deg))
    return _pt(
        float(point.get("x_pct") or 0) + (math.cos(angle) * distance_pct),
        float(point.get("y_pct") or 0) + (math.sin(angle) * distance_pct * GLEISPLAN_TEMPLATE_ASPECT),
    )


def _relative_route_point_for_item(
    *,
    item_id: str,
    point: dict[str, Any],
    anchor_role: str,
    name: str,
) -> dict[str, Any]:
    item = _template_items_by_id().get(str(item_id or "").strip().upper()) or {}
    x_pct = float(point.get("x_pct") or point.get("x") or 0)
    y_pct = float(point.get("y_pct") or point.get("y") or 0)
    return {
        "anchor": anchor_role,
        "name": name,
        "x_pct": round(x_pct, 3),
        "y_pct": round(y_pct, 3),
        "dx_pct": round(x_pct - float(item.get("x_pct") or 0), 3),
        "dy_pct": round(y_pct - float(item.get("y_pct") or 0), 3),
    }


def _switch_local_to_board(
    center_x_pct: float,
    center_y_pct: float,
    rotation_deg: float,
    x_ratio: float,
    y_ratio: float,
) -> tuple[float, float]:
    local_x = SWITCH_TEMPLATE_W * float(x_ratio)
    local_y = SWITCH_TEMPLATE_H * float(y_ratio)
    dx = (local_x - (SWITCH_TEMPLATE_W / 2.0)) * GLEISPLAN_TEMPLATE_ASPECT
    dy = local_y - (SWITCH_TEMPLATE_H / 2.0)
    angle = math.radians(float(rotation_deg))
    rotated_x = (dx * math.cos(angle)) - (dy * math.sin(angle))
    rotated_y = (dx * math.sin(angle)) + (dy * math.cos(angle))
    return (
        float(center_x_pct) + (rotated_x / GLEISPLAN_TEMPLATE_ASPECT),
        float(center_y_pct) + rotated_y,
    )


def _switch_port_ratios(handedness: str, *, branch_x_ratio: float = SWITCH_TEMPLATE_BRANCH_X_RATIO) -> dict[str, tuple[float, float]]:
    branch_y_ratio = SWITCH_TEMPLATE_BRANCH_Y_LEFT if str(handedness).strip().lower() == "left" else SWITCH_TEMPLATE_BRANCH_Y_RIGHT
    return {
        "straight": (1.0, SWITCH_TEMPLATE_MAIN_Y_RATIO),
        "stem": (0.0, SWITCH_TEMPLATE_MAIN_Y_RATIO),
        "branch": (branch_x_ratio, branch_y_ratio),
    }


def _polyline(*points: tuple[float, float], label: tuple[float, float] | None = None) -> dict[str, Any]:
    route_points = [_pt(x, y) for x, y in points]
    route: dict[str, Any] = {
        "type": "polyline",
        "points": route_points,
        "start": route_points[0],
        "end": route_points[-1],
    }
    if label:
        route["label_position"] = _pt(*label)
    return route


def _path(
    d: str,
    *points: tuple[float, float],
    label: tuple[float, float] | None = None,
) -> dict[str, Any]:
    route_points = [_pt(x, y) for x, y in points]
    route: dict[str, Any] = {
        "type": "path",
        "d": " ".join(str(d).split()),
        "points": route_points,
        "start": route_points[0],
        "end": route_points[-1],
    }
    if label:
        route["label_position"] = _pt(*label)
    return route


def _item(
    item_id: str,
    item_type: str,
    label: str,
    x_pct: float,
    y_pct: float,
    w_pct: float,
    h_pct: float,
    *,
    rotation: float = 0,
    color: str = "",
    sort_order: int = 1000,
    title: str = "",
    curve_radius: float = 0,
    switch_port2_x_ratio: float = 0.0,
    switch_port2_y_ratio: float = 0.28,
    switch_port3_x_ratio: float = 0.06,
    switch_port3_y_ratio: float = 1.35,
) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "item_type": item_type,
        "label": label,
        "title": title,
        "x_pct": x_pct,
        "y_pct": y_pct,
        "w_pct": w_pct,
        "h_pct": h_pct,
        "rotation": rotation,
        "color": color,
        "curve_radius": curve_radius,
        "switch_port2_x_ratio": switch_port2_x_ratio,
        "switch_port2_y_ratio": switch_port2_y_ratio,
        "switch_port3_x_ratio": switch_port3_x_ratio,
        "switch_port3_y_ratio": switch_port3_y_ratio,
        "sort_order": sort_order,
    }


def _street(item_id: str, x_pct: float, y_pct: float, w_pct: float, h_pct: float, *, rotation: float = 0) -> dict[str, Any]:
    return _item(
        item_id,
        "street",
        "Strasse",
        x_pct,
        y_pct,
        w_pct,
        h_pct,
        rotation=rotation,
        color="rgba(244,114,182,.42)",
        sort_order=20,
    )


def _anchor(item_id: str, x_pct: float, y_pct: float, *, label: str = "") -> dict[str, Any]:
    return _item(item_id, "anchor", label or item_id, x_pct - 1.0, y_pct - 1.0, 2.0, 2.0, sort_order=700)


def _switch(
    item_id: str,
    label: str,
    x_pct: float,
    y_pct: float,
    *,
    rotation: float = 0,
    switch_port2_x_ratio: float = 0.0,
    switch_port2_y_ratio: float = 0.28,
    switch_port3_x_ratio: float = 0.06,
    switch_port3_y_ratio: float = 1.35,
) -> dict[str, Any]:
    return _item(
        item_id,
        "switch",
        label,
        x_pct,
        y_pct,
        3.7,
        2.0,
        rotation=rotation,
        color="#f59e0b",
        sort_order=600,
        switch_port2_x_ratio=switch_port2_x_ratio,
        switch_port2_y_ratio=switch_port2_y_ratio,
        switch_port3_x_ratio=switch_port3_x_ratio,
        switch_port3_y_ratio=switch_port3_y_ratio,
    )


def _switch_center(
    item_id: str,
    label: str,
    x_pct: float,
    y_pct: float,
    *,
    rotation: float = 0,
    switch_port2_x_ratio: float = 0.0,
    switch_port2_y_ratio: float = SWITCH_TEMPLATE_MAIN_Y_RATIO,
    switch_port3_x_ratio: float = SWITCH_TEMPLATE_BRANCH_X_RATIO,
    switch_port3_y_ratio: float = SWITCH_TEMPLATE_BRANCH_Y_RIGHT,
) -> dict[str, Any]:
    return _switch(
        item_id,
        label,
        x_pct - (SWITCH_TEMPLATE_W / 2.0),
        y_pct - (SWITCH_TEMPLATE_H / 2.0),
        rotation=rotation,
        switch_port2_x_ratio=switch_port2_x_ratio,
        switch_port2_y_ratio=switch_port2_y_ratio,
        switch_port3_x_ratio=switch_port3_x_ratio,
        switch_port3_y_ratio=switch_port3_y_ratio,
    )


def _buffer_stop(item_id: str, label: str, x_pct: float, y_pct: float, *, rotation: float = 0) -> dict[str, Any]:
    return _item(
        item_id,
        "buffer_stop",
        label,
        x_pct,
        y_pct,
        2.6,
        7.0,
        rotation=rotation,
        color="#dc2626",
        sort_order=610,
    )


def _connection(
    source_item_id: str,
    target_item_id: str,
    *,
    route_key: str,
    label: str = "",
    source_port: str = "",
    target_port: str = "",
    source_anchor: str = "center",
    target_anchor: str = "center",
) -> dict[str, Any]:
    route = _anchored_route(
        EBERSWALDE_TRACK_ROUTES[route_key],
        source_item_id=source_item_id,
        target_item_id=target_item_id,
        source_anchor=source_anchor,
        target_anchor=target_anchor,
    )
    return {
        "source_item_id": source_item_id,
        "target_item_id": target_item_id,
        "source_port": source_port,
        "target_port": target_port,
        "label": label,
        "connection_type": "track",
        "curve_pct": 0,
        "path_points": [],
        "route": route,
    }


EBERSWALDE_LAGEPLAN_HALL_TRACKS: tuple[dict[str, Any], ...] = (
    {
        "area_code": "4B",
        "track_label": "4B",
        "position_label": "oben links",
        "workshop_area": "4B",
        "sync_enabled": True,
    },
    {
        "area_code": "4A",
        "track_label": "4A",
        "position_label": "oben rechts",
        "workshop_area": "4A",
        "sync_enabled": True,
    },
    {
        "area_code": "5B",
        "track_label": "5B",
        "position_label": "unten links",
        "workshop_area": "5B",
        "sync_enabled": True,
    },
    {
        "area_code": "5A",
        "track_label": "5A",
        "position_label": "unten rechts",
        "workshop_area": "5A",
        "sync_enabled": True,
    },
)


EBERSWALDE_SWITCH_CONFIGS: dict[str, dict[str, Any]] = {
    "WEICHE_A14": {
        "label": "A14", "x": 31.6, "y": 14.0, "rotation": 8, "handedness": "right",
        "extra_anchors": {
            "stem": {"x": 30.0, "y": 13.8, "dir": 188},
            "straight": {"x": 33.1, "y": 14.4, "dir": 8},
            "branch": {"x": 32.1, "y": 15.2, "dir": 74},
        },
    },
    "WEICHE_A11": {"label": "A11", "x": 34.0, "y": 35.1, "rotation": 1, "handedness": "right"},
    "WEICHE_A9": {
        "label": "A9", "x": 44.0, "y": 39.0, "rotation": 12, "handedness": "left",
        "extra_anchors": {
            "stem": {"x": 42.5, "y": 38.5, "dir": 190},
            "straight": {"x": 45.5, "y": 40.0, "dir": 10},
            "branch": {"x": 43.8, "y": 38.8, "dir": 230},
            "branch_gl10": {"x": 42.0, "y": 37.1, "dir": 190},
        },
    },
    "WEICHE_A10": {"label": "A10", "x": 45.8, "y": 40.1, "rotation": 0, "handedness": "right"},
    "WEICHE_A8": {"label": "A8", "x": 50.4, "y": 40.1, "rotation": 0, "handedness": "right"},
    "WEICHE_A12": {"label": "A12", "x": 36.7, "y": 43.5, "rotation": 0, "handedness": "right"},
    "WEICHE_A16": {
        "label": "A16", "x": 28.2, "y": 43.5, "rotation": 0, "handedness": "right",
        "extra_anchors": {
            "stem": {"x": 26.6, "y": 43.5, "dir": 180},
            "straight": {"x": 29.8, "y": 43.5, "dir": 0},
        },
    },
    "WEICHE_A17": {
        "label": "A17", "x": 8.8, "y": 45.3, "rotation": -4, "handedness": "right", "branch_x_ratio": 1.08,
        "extra_anchors": {
            "stem": {"x": 7.5, "y": 45.4, "dir": 185},
            "straight": {"x": 10.5, "y": 44.8, "dir": 350},
            "branch": {"x": 9.0, "y": 46.5, "dir": 92},
        },
    },
    "WEICHE_A18": {
        "label": "A18", "x": 5.2, "y": 44.3, "rotation": 12, "handedness": "left",
        "extra_anchors": {
            "branch": {"x": 4.2, "y": 44.0, "dir": 270},
            "straight": {"x": 6.2, "y": 45.2, "dir": 10},
        },
    },
    "WEICHE_A6": {
        "label": "A6", "x": 81.8, "y": 47.0, "rotation": 52, "handedness": "right",
        "extra_anchors": {
            "stem": {"x": 80.2, "y": 46.4, "dir": 210},
            "straight": {"x": 81.8, "y": 47.0, "dir": 225},
            "branch": {"x": 82.5, "y": 48.5, "dir": 105},
        },
    },
    "WEICHE_A5": {
        "label": "A5", "x": 80.8, "y": 59.0, "rotation": 18, "handedness": "right", "branch_x_ratio": 1.08,
        "extra_anchors": {
            "stem": {"x": 80.8, "y": 59.0, "dir": 282},
            "branch": {"x": 83.0, "y": 61.0, "dir": 55},
            "hall4": {"x": 78.9, "y": 57.4, "dir": 188},
            "hall5": {"x": 78.9, "y": 59.0, "dir": 180},
        },
    },
    "WEICHE_A3": {
        "label": "A3", "x": 87.9, "y": 65.4, "rotation": 60, "handedness": "right",
        "extra_anchors": {
            "stem": {"x": 87.6, "y": 65.0, "dir": 235},
            "straight": {"x": 88.9, "y": 67.3, "dir": 72},
        },
    },
    "WEICHE_A2": {
        "label": "A2", "x": 90.2, "y": 72.6, "rotation": 76, "handedness": "right",
        "extra_anchors": {
            "stem": {"x": 90.0, "y": 72.5, "dir": 250},
            "straight": {"x": 90.9, "y": 75.0, "dir": 78},
        },
    },
    "WEICHE_A1": {
        "label": "A1", "x": 93.0, "y": 85.8, "rotation": 89, "handedness": "right",
        "extra_anchors": {
            "stem": {"x": 93.0, "y": 85.8, "dir": 260},
            "straight": {"x": 93.4, "y": 91.0, "dir": 90},
        },
    },
}


def _switch_anchor_point(
    center_x_pct: float,
    center_y_pct: float,
    rotation_deg: float,
    x_ratio: float,
    y_ratio: float,
    *,
    direction_to_ratio: tuple[float, float],
) -> dict[str, float]:
    point = _switch_local_to_board(center_x_pct, center_y_pct, rotation_deg, x_ratio, y_ratio)
    direction_point = _switch_local_to_board(center_x_pct, center_y_pct, rotation_deg, *direction_to_ratio)
    return {
        **_pt(*point),
        "dir": round(_visual_angle(direction_point, point), 3),
    }


def _switch_topology(config: dict[str, Any]) -> dict[str, Any]:
    center_x = float(config["x"])
    center_y = float(config["y"])
    rotation = float(config.get("rotation") or 0)
    handedness = str(config.get("handedness") or "right").strip().lower()
    branch_x_ratio = float(config.get("branch_x_ratio") or SWITCH_TEMPLATE_BRANCH_X_RATIO)
    ratios = _switch_port_ratios(handedness, branch_x_ratio=branch_x_ratio)
    heel_ratio = (
        ratios["stem"][0] + ((ratios["straight"][0] - ratios["stem"][0]) * SWITCH_TEMPLATE_HEEL_X_RATIO),
        ratios["stem"][1] + ((ratios["straight"][1] - ratios["stem"][1]) * SWITCH_TEMPLATE_HEEL_X_RATIO),
    )
    anchors: dict[str, dict[str, Any]] = {
        "stem": _switch_anchor_point(center_x, center_y, rotation, *ratios["stem"], direction_to_ratio=ratios["straight"]),
        "straight": _switch_anchor_point(center_x, center_y, rotation, *ratios["straight"], direction_to_ratio=ratios["stem"]),
        "branch": _switch_anchor_point(center_x, center_y, rotation, *ratios["branch"], direction_to_ratio=heel_ratio),
    }
    for name, data in (config.get("extra_anchors") or {}).items():
        anchors[str(name)] = {
            **_pt(float(data.get("x") or center_x), float(data.get("y") or center_y)),
            "dir": round(float(data.get("dir") or 0), 3),
        }
    return {
        "label": str(config.get("label") or ""),
        "position": _pt(center_x, center_y),
        "rotation": rotation,
        "handedness": handedness,
        "branch_x_ratio": branch_x_ratio,
        "branch_y_ratio": _switch_port_ratios(handedness, branch_x_ratio=branch_x_ratio)["branch"][1],
        "anchors": anchors,
    }


EBERSWALDE_SWITCHES: dict[str, dict[str, Any]] = {
    switch_id: _switch_topology(config)
    for switch_id, config in EBERSWALDE_SWITCH_CONFIGS.items()
}


def _eberswalde_switch_item(item_id: str) -> dict[str, Any]:
    config = EBERSWALDE_SWITCH_CONFIGS[item_id]
    handedness = str(config.get("handedness") or "right")
    branch_x_ratio = float(config.get("branch_x_ratio") or SWITCH_TEMPLATE_BRANCH_X_RATIO)
    branch_y_ratio = _switch_port_ratios(handedness, branch_x_ratio=branch_x_ratio)["branch"][1]
    return _switch_center(
        item_id,
        str(config.get("label") or item_id),
        float(config.get("x") or 0),
        float(config.get("y") or 0),
        rotation=float(config.get("rotation") or 0),
        switch_port3_x_ratio=branch_x_ratio,
        switch_port3_y_ratio=branch_y_ratio,
    )


EBERSWALDE_TRACK_ROUTES: dict[str, dict[str, Any]] = {
    "gl12_w_a14": _path(
        "M 4.0 7.4 C 12.0 8.8, 22.0 11.4, 31.6 14.0",
        (4.0, 7.4), (12.0, 8.8), (22.0, 11.4), (31.6, 14.0),
        label=(12.5, 8.6),
    ),
    "gl12_a14_a6": _path(
        "M 31.6 14.0 C 39.0 15.1, 48.0 17.0, 58.0 20.1 C 70.0 24.0, 79.0 36.0, 81.8 47.0",
        (31.6, 14.0), (39.0, 15.1), (48.0, 17.0), (58.0, 20.1), (70.0, 24.0), (79.0, 36.0), (81.8, 47.0),
        label=(58.0, 19.4),
    ),
    "gl13_a14_a9": _path(
        "M 31.6 14.0 C 35.0 16.5, 36.4 25.0, 39.4 31.5 C 40.7 34.3, 42.6 37.2, 44.0 39.0",
        (31.6, 14.0), (35.0, 16.5), (36.4, 25.0), (39.4, 31.5), (42.6, 37.2), (44.0, 39.0),
        label=(38.2, 27.0),
    ),
    "gl10_w_a9": _path(
        "M 26.4 32.0 L 36.6 32.0 C 39.6 33.0, 42.2 36.5, 44.0 39.0",
        (26.4, 32.0), (36.6, 32.0), (40.0, 33.3), (42.2, 36.5), (44.0, 39.0),
        label=(31.8, 31.5),
    ),
    "gl1a_w_a11": _path(
        "M 9.3 20.7 L 9.3 30.2 C 9.6 34.0, 13.1 36.2, 18.5 36.2 L 34.0 35.1",
        (9.3, 20.7), (9.3, 30.2), (13.1, 36.2), (20.5, 36.2), (30.0, 35.8), (34.0, 35.1),
        label=(18.4, 35.6),
    ),
    "gl1b_w_a11": _path(
        "M 6.5 20.5 L 6.5 34.6 C 6.8 39.3, 11.6 41.1, 17.3 41.1 L 27.0 41.0 C 30.2 40.4, 32.8 36.8, 34.0 35.1",
        (6.5, 20.5), (6.5, 34.6), (11.6, 41.1), (20.0, 41.1), (27.0, 41.0), (31.5, 37.4), (34.0, 35.1),
        label=(18.5, 40.6),
    ),
    "gl1_a11_a9": _path("M 34.0 35.1 C 37.0 34.7, 41.0 36.6, 44.0 39.0", (34.0, 35.1), (37.0, 34.7), (41.0, 36.6), (44.0, 39.0), label=(38.0, 35.5)),
    "gl1_a9_a10": _path("M 44.0 39.0 C 44.5 39.6, 45.1 40.0, 45.8 40.1", (44.0, 39.0), (44.5, 39.6), (45.8, 40.1)),
    "gl1_a10_a8": _polyline((45.8, 40.1), (50.4, 40.1), label=(47.8, 39.4)),
    "gl2_a16_a12": _path("M 28.2 43.5 C 30.5 43.5, 34.0 43.5, 36.7 43.5", (28.2, 43.5), (30.5, 43.5), (36.7, 43.5), label=(32.5, 42.9)),
    "gl2_a12_a8": _path(
        "M 36.7 43.5 C 38.8 41.5, 42.0 40.1, 45.8 40.1 C 47.5 40.1, 49.2 40.1, 50.4 40.1",
        (36.7, 43.5), (38.8, 41.5), (42.0, 40.1), (45.8, 40.1), (50.4, 40.1),
        label=(42.0, 41.7),
    ),
    "gl1_a8_join_a6": _path(
        "M 50.4 40.1 C 58.5 39.8, 66.5 38.6, 74.0 40.6 C 77.6 41.6, 80.0 44.2, 81.8 47.0",
        (50.4, 40.1), (58.5, 39.8), (66.5, 38.6), (74.0, 40.6), (78.8, 43.4), (81.8, 47.0),
        label=(67.5, 39.5),
    ),
    "gl3_a12_join_a6": _path(
        "M 36.7 43.5 C 39.5 47.0, 44.5 48.9, 51.2 48.9 L 66.5 48.9 C 73.0 48.6, 78.0 47.7, 81.8 47.0",
        (36.7, 43.5), (39.5, 47.0), (44.5, 48.9), (55.5, 48.9), (66.5, 48.9), (76.5, 47.8), (81.8, 47.0),
        label=(67.0, 48.2),
    ),
    "join_a6_a6": _path("M 78.2 44.5 C 79.5 45.2, 80.8 46.0, 81.8 47.0", (78.2, 44.5), (79.5, 45.2), (81.8, 47.0)),
    "a6_a5": _path(
        "M 81.8 47.0 C 84.7 50.2, 85.6 55.0, 80.8 59.0",
        (81.8, 47.0), (84.7, 50.2), (85.6, 55.0), (80.8, 59.0),
        label=(83.4, 52.1),
    ),
    "a5_a3": _path("M 80.8 59.0 C 84.0 61.0, 86.4 63.4, 87.9 65.4", (80.8, 59.0), (84.0, 61.0), (86.4, 63.4), (87.9, 65.4)),
    "a3_a2": _path("M 87.9 65.4 C 88.9 67.5, 89.6 70.1, 90.2 72.6", (87.9, 65.4), (88.9, 67.5), (90.2, 72.6)),
    "a2_a1": _path("M 90.2 72.6 C 91.7 77.3, 92.6 82.0, 93.0 85.8", (90.2, 72.6), (91.7, 77.3), (92.6, 82.0), (93.0, 85.8)),
    "a1_bottom": _path("M 93.0 85.8 C 93.4 89.5, 93.4 94.4, 93.4 97.0", (93.0, 85.8), (93.4, 89.5), (93.4, 97.0)),
    "gl4a_w_a18": _path(
        "M 3.8 17.0 L 3.8 32.8 C 4.0 38.6, 4.6 42.5, 5.2 44.3",
        (3.8, 17.0), (3.8, 32.8), (4.6, 42.5), (5.2, 44.3),
        label=(4.2, 25.0),
    ),
    "a18_a17": _polyline((5.2, 44.3), (8.8, 45.3)),
    "a17_a16": _path("M 8.8 45.3 C 12.5 47.6, 17.8 46.5, 22.8 44.3 C 24.8 43.5, 26.8 43.4, 28.2 43.5", (8.8, 45.3), (12.5, 47.6), (17.8, 46.5), (22.8, 44.3), (28.2, 43.5)),
    "a17_join_hall_w": _path("M 8.8 45.3 C 8.7 45.7, 8.7 46.1, 8.7 46.5", (8.8, 45.3), (8.7, 45.7), (8.7, 46.5)),
    "join_hall_gl4_w": _path("M 8.7 46.5 C 12.0 50.3, 16.7 52.1, 22.0 52.3", (8.7, 46.5), (12.0, 50.3), (16.7, 52.1), (22.0, 52.3), label=(17.6, 51.7)),
    "join_hall_gl5_w": _path("M 8.7 46.5 C 11.3 53.0, 16.0 56.8, 22.0 57.4", (8.7, 46.5), (11.3, 53.0), (16.0, 56.8), (22.0, 57.4), label=(17.7, 56.8)),
    "hall_gl4": _polyline((22.0, 52.3), (64.0, 52.3), label=(40.8, 51.8)),
    "hall_gl5": _polyline((22.0, 57.4), (64.0, 57.4), label=(40.8, 58.0)),
    "hall_gl4_e": _path("M 64.0 52.3 L 68.5 52.3 C 73.5 52.5, 77.6 55.6, 80.8 59.0", (64.0, 52.3), (68.5, 52.3), (73.5, 52.5), (77.6, 55.6), (80.8, 59.0), label=(68.8, 51.8)),
    "hall_gl5_e": _path("M 64.0 57.4 L 72.0 57.4 C 75.7 57.4, 78.8 58.1, 80.8 59.0", (64.0, 57.4), (72.0, 57.4), (78.8, 58.1), (80.8, 59.0), label=(68.7, 58.0)),
}


EBERSWALDE_LAGEPLAN_LAYOUT_ITEMS: tuple[dict[str, Any], ...] = (
    _street("STRASSE_NORD_WEST", 7.8, 3.5, 18.0, 3.0, rotation=8),
    _street("STRASSE_NORD_VERT", 17.0, 5.0, 18.5, 3.3, rotation=90),
    _street("STRASSE_NORD_UNTEN", 19.0, 20.2, 25.5, 3.2),
    _street("STRASSE_MITTE_UNTEN", 45.8, 25.0, 16.5, 3.4),
    _street("STRASSE_MITTE_KNICK", 59.0, 25.6, 9.8, 3.4, rotation=35),
    _street("STRASSE_OST_OBEN", 58.0, 33.0, 16.0, 3.5, rotation=90),
    _street("STRASSE_HALL_LINKS", 20.5, 46.0, 12.0, 4.0, rotation=90),
    _street("STRASSE_HALL_OBEN", 22.6, 49.7, 40.7, 3.8),
    _street("STRASSE_HALL_RECHTS", 62.2, 45.0, 19.0, 4.0, rotation=90),
    _street("STRASSE_WEST_SUED", 8.2, 58.0, 22.0, 4.0),
    _street("STRASSE_UNTER_HALLE", 20.0, 60.2, 42.0, 4.0),
    _item("STRASSE_HOF_UNTEN", "street", "Strasse", 35.0, 62.0, 29.0, 11.0, color="rgba(244,114,182,.42)", curve_radius=2, sort_order=20),
    _street("STRASSE_OST_DIAGONAL", 64.4, 54.8, 8.8, 4.0, rotation=-42),
    _item("HALL_MAIN", "hall", "Werkstatt mit Gleishalle", 22.5, 50.0, 41.5, 10.5, color="#d1d5db", sort_order=120),
    _item("ARA_BEREICH", "building", "ARA", 47.3, 45.9, 11.5, 5.2, color="rgba(254,240,138,.82)", sort_order=110),
    _item("URD_BEREICH", "building", "URD", 42.1, 14.6, 8.7, 5.3, rotation=7, color="rgba(254,240,138,.82)", sort_order=110),
    _item("TANK", "building", "WC / VE / Tankstelle", 62.3, 38.9, 9.9, 4.8, color="#15803d", sort_order=110),
    _eberswalde_switch_item("WEICHE_A14"),
    _eberswalde_switch_item("WEICHE_A11"),
    _eberswalde_switch_item("WEICHE_A9"),
    _eberswalde_switch_item("WEICHE_A10"),
    _eberswalde_switch_item("WEICHE_A8"),
    _eberswalde_switch_item("WEICHE_A12"),
    _eberswalde_switch_item("WEICHE_A16"),
    _eberswalde_switch_item("WEICHE_A17"),
    _eberswalde_switch_item("WEICHE_A18"),
    _eberswalde_switch_item("WEICHE_A6"),
    _eberswalde_switch_item("WEICHE_A5"),
    _eberswalde_switch_item("WEICHE_A3"),
    _eberswalde_switch_item("WEICHE_A2"),
    _eberswalde_switch_item("WEICHE_A1"),
    _buffer_stop("PRELLBOCK_GL12_W", "GL12", 2.9, 5.9, rotation=-78),
    _buffer_stop("PRELLBOCK_GL10_W", "GL10", 24.9, 28.9, rotation=-90),
    _buffer_stop("PRELLBOCK_4A_W", "4a", 2.5, 14.4),
    _buffer_stop("PRELLBOCK_1B_W", "1b", 5.2, 18.0),
    _buffer_stop("PRELLBOCK_1A_W", "1a", 8.0, 18.2),
    _anchor("JOIN_A6_W", 78.2, 44.5),
    _anchor("JOIN_HALL_W", 8.7, 46.5),
    _anchor("HALL_GL4_W", 22.0, 52.3),
    _anchor("HALL_GL4_E", 64.0, 52.3),
    _anchor("HALL_GL5_W", 22.0, 57.4),
    _anchor("HALL_GL5_E", 64.0, 57.4),
    _anchor("ANCH_GL12_A1_BOTTOM", 93.4, 97.0),
)


def _template_items_by_id() -> dict[str, dict[str, Any]]:
    return {str(item.get("item_id") or "").strip().upper(): dict(item) for item in EBERSWALDE_LAGEPLAN_LAYOUT_ITEMS}


def _anchor_point_for_route(
    *,
    item_id: str,
    endpoint: dict[str, Any],
    anchor_role: str,
    anchor_name: str,
) -> dict[str, Any]:
    items_by_id = _template_items_by_id()
    clean_item_id = str(item_id or "").strip().upper()
    item = items_by_id.get(clean_item_id) or {}
    switch_anchor = ((EBERSWALDE_SWITCHES.get(clean_item_id) or {}).get("anchors") or {}).get(str(anchor_name or "").strip())
    if isinstance(switch_anchor, dict):
        x_pct = float(switch_anchor.get("x_pct") or 0)
        y_pct = float(switch_anchor.get("y_pct") or 0)
        direction = switch_anchor.get("dir")
    else:
        x_pct = float(endpoint.get("x_pct") or endpoint.get("x") or 0)
        y_pct = float(endpoint.get("y_pct") or endpoint.get("y") or 0)
        direction = endpoint.get("dir")
    out: dict[str, Any] = {
        "anchor": anchor_role,
        "name": anchor_name,
        "x_pct": round(x_pct, 3),
        "y_pct": round(y_pct, 3),
        "dx_pct": round(x_pct - float(item.get("x_pct") or 0), 3),
        "dy_pct": round(y_pct - float(item.get("y_pct") or 0), 3),
    }
    if direction is not None:
        out["dir"] = round(float(direction), 3)
    return out


def _anchored_route(
    route: dict[str, Any],
    *,
    source_item_id: str,
    target_item_id: str,
    source_anchor: str,
    target_anchor: str,
) -> dict[str, Any]:
    clean_route = deepcopy(route)
    points = [dict(point) for point in clean_route.get("points") or [] if isinstance(point, dict)]
    if len(points) < 2:
        return clean_route
    points[0] = _anchor_point_for_route(
        item_id=source_item_id,
        endpoint=points[0],
        anchor_role="from",
        anchor_name=source_anchor,
    )
    points[-1] = _anchor_point_for_route(
        item_id=target_item_id,
        endpoint=points[-1],
        anchor_role="to",
        anchor_name=target_anchor,
    )
    inserted_switch_lead = False
    if source_item_id in EBERSWALDE_SWITCHES and points[0].get("dir") is not None:
        source_lead = _point_from_dir(points[0], float(points[0]["dir"]))
        points.insert(
            1,
            _relative_route_point_for_item(
                item_id=source_item_id,
                point=source_lead,
                anchor_role="from",
                name=f"{source_anchor}_tangent",
            ),
        )
        inserted_switch_lead = True
    if target_item_id in EBERSWALDE_SWITCHES and points[-1].get("dir") is not None:
        target_lead = _point_from_dir(points[-1], float(points[-1]["dir"]))
        points.insert(
            -1,
            _relative_route_point_for_item(
                item_id=target_item_id,
                point=target_lead,
                anchor_role="to",
                name=f"{target_anchor}_tangent",
            ),
        )
        inserted_switch_lead = True
    clean_route["type"] = "smooth" if bool(route.get("type") == "path" or len(points) > 2) else "polyline"
    clean_route["smooth"] = bool(route.get("type") == "path" or len(points) > 2)
    clean_route["points"] = points
    clean_route["start"] = points[0]
    clean_route["end"] = points[-1]
    clean_route["source_anchor"] = source_anchor
    clean_route["target_anchor"] = target_anchor
    clean_route.pop("d", None)
    return clean_route


EBERSWALDE_LAGEPLAN_CONNECTIONS: tuple[dict[str, Any], ...] = (
    _connection("PRELLBOCK_GL12_W", "WEICHE_A14", label="GL12", target_port="2", route_key="gl12_w_a14", source_anchor="track_end", target_anchor="stem"),
    _connection("WEICHE_A14", "WEICHE_A6", label="GL12 / URD", source_port="1", target_port="2", route_key="gl12_a14_a6", source_anchor="straight", target_anchor="straight"),
    _connection("WEICHE_A14", "WEICHE_A9", label="GL13", source_port="3", target_port="2", route_key="gl13_a14_a9", source_anchor="branch", target_anchor="branch"),
    _connection("PRELLBOCK_GL10_W", "WEICHE_A9", label="GL10", target_port="3", route_key="gl10_w_a9", source_anchor="track_end", target_anchor="branch_gl10"),
    _connection("PRELLBOCK_1A_W", "WEICHE_A11", label="GL1a", target_port="2", route_key="gl1a_w_a11", source_anchor="track_end", target_anchor="stem"),
    _connection("PRELLBOCK_1B_W", "WEICHE_A11", label="GL1b", target_port="3", route_key="gl1b_w_a11", source_anchor="track_end", target_anchor="branch"),
    _connection("WEICHE_A11", "WEICHE_A9", label="GL1", source_port="1", target_port="2", route_key="gl1_a11_a9", source_anchor="straight", target_anchor="stem"),
    _connection("WEICHE_A9", "WEICHE_A10", label="", source_port="1", target_port="2", route_key="gl1_a9_a10", source_anchor="straight", target_anchor="stem"),
    _connection("WEICHE_A10", "WEICHE_A8", label="GL1", source_port="1", target_port="2", route_key="gl1_a10_a8", source_anchor="straight", target_anchor="stem"),
    _connection("WEICHE_A16", "WEICHE_A12", label="GL2", source_port="1", target_port="2", route_key="gl2_a16_a12", source_anchor="straight", target_anchor="stem"),
    _connection("WEICHE_A12", "WEICHE_A8", label="GL2", source_port="1", target_port="3", route_key="gl2_a12_a8", source_anchor="straight", target_anchor="branch"),
    _connection("WEICHE_A8", "JOIN_A6_W", label="GL1", source_port="1", route_key="gl1_a8_join_a6", source_anchor="straight", target_anchor="center"),
    _connection("WEICHE_A12", "JOIN_A6_W", label="GL3 / ARA", source_port="3", route_key="gl3_a12_join_a6", source_anchor="branch", target_anchor="center"),
    _connection("JOIN_A6_W", "WEICHE_A6", target_port="1", route_key="join_a6_a6", source_anchor="center", target_anchor="stem"),
    _connection("WEICHE_A6", "WEICHE_A5", source_port="3", target_port="2", route_key="a6_a5", source_anchor="branch", target_anchor="stem"),
    _connection("WEICHE_A5", "WEICHE_A3", source_port="1", target_port="2", route_key="a5_a3", source_anchor="branch", target_anchor="stem"),
    _connection("WEICHE_A3", "WEICHE_A2", source_port="1", target_port="2", route_key="a3_a2", source_anchor="straight", target_anchor="stem"),
    _connection("WEICHE_A2", "WEICHE_A1", source_port="1", target_port="2", route_key="a2_a1", source_anchor="straight", target_anchor="stem"),
    _connection("WEICHE_A1", "ANCH_GL12_A1_BOTTOM", source_port="1", route_key="a1_bottom", source_anchor="straight", target_anchor="center"),
    _connection("PRELLBOCK_4A_W", "WEICHE_A18", label="GL4a", target_port="2", route_key="gl4a_w_a18", source_anchor="track_end", target_anchor="branch"),
    _connection("WEICHE_A18", "WEICHE_A17", source_port="1", target_port="2", route_key="a18_a17", source_anchor="straight", target_anchor="stem"),
    _connection("WEICHE_A17", "WEICHE_A16", source_port="1", target_port="2", route_key="a17_a16", source_anchor="straight", target_anchor="stem"),
    _connection("WEICHE_A17", "JOIN_HALL_W", source_port="3", route_key="a17_join_hall_w", source_anchor="branch", target_anchor="center"),
    _connection("JOIN_HALL_W", "HALL_GL4_W", label="GL4", route_key="join_hall_gl4_w", source_anchor="center", target_anchor="center"),
    _connection("JOIN_HALL_W", "HALL_GL5_W", label="GL5", route_key="join_hall_gl5_w", source_anchor="center", target_anchor="center"),
    _connection("HALL_GL4_W", "HALL_GL4_E", label="GL4", route_key="hall_gl4", source_anchor="center", target_anchor="center"),
    _connection("HALL_GL5_W", "HALL_GL5_E", label="GL5", route_key="hall_gl5", source_anchor="center", target_anchor="center"),
    _connection("HALL_GL4_E", "WEICHE_A5", label="GL4", target_port="3", route_key="hall_gl4_e", source_anchor="center", target_anchor="hall4"),
    _connection("HALL_GL5_E", "WEICHE_A5", label="GL5", target_port="3", route_key="hall_gl5_e", source_anchor="center", target_anchor="hall5"),
)


EBERSWALDE_SWITCH_REQUIRED_CONNECTIONS: dict[str, int] = {
    "WEICHE_A14": 3,
    "WEICHE_A11": 3,
    "WEICHE_A9": 3,
    "WEICHE_A10": 2,
    "WEICHE_A8": 3,
    "WEICHE_A12": 3,
    "WEICHE_A16": 2,
    "WEICHE_A17": 3,
    "WEICHE_A18": 2,
    "WEICHE_A6": 3,
    "WEICHE_A5": 3,
    "WEICHE_A3": 2,
    "WEICHE_A2": 2,
    "WEICHE_A1": 2,
}


def _template_item_center(item: dict[str, Any]) -> tuple[float, float]:
    return (
        float(item.get("x_pct") or 0) + (float(item.get("w_pct") or 0) / 2.0),
        float(item.get("y_pct") or 0) + (float(item.get("h_pct") or 0) / 2.0),
    )


def _template_anchor_points(item_id: str, items_by_id: dict[str, dict[str, Any]]) -> list[tuple[str, tuple[float, float]]]:
    clean_id = str(item_id or "").strip().upper()
    if clean_id in EBERSWALDE_SWITCHES:
        anchors = EBERSWALDE_SWITCHES[clean_id].get("anchors") or {}
        return [
            (str(name), (float(point.get("x_pct") or 0), float(point.get("y_pct") or 0)))
            for name, point in anchors.items()
            if isinstance(point, dict)
        ]
    item = items_by_id.get(clean_id) or {}
    if not item:
        return []
    return [("center", _template_item_center(item))]


def _template_distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return (((a[0] - b[0]) ** 2) + ((a[1] - b[1]) ** 2)) ** 0.5


def _template_orientation(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return ((b[1] - a[1]) * (c[0] - b[0])) - ((b[0] - a[0]) * (c[1] - b[1]))


def _template_segments_intersect(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
) -> bool:
    if max(a[0], b[0]) < min(c[0], d[0]) or max(c[0], d[0]) < min(a[0], b[0]):
        return False
    if max(a[1], b[1]) < min(c[1], d[1]) or max(c[1], d[1]) < min(a[1], b[1]):
        return False
    o1 = _template_orientation(a, b, c)
    o2 = _template_orientation(a, b, d)
    o3 = _template_orientation(c, d, a)
    o4 = _template_orientation(c, d, b)
    return (o1 * o2 < 0) and (o3 * o4 < 0)


def _template_route_self_intersections(points: list[dict[str, Any]]) -> list[str]:
    coords = [
        (float(point.get("x_pct") or 0), float(point.get("y_pct") or 0))
        for point in points
        if isinstance(point, dict)
    ]
    errors: list[str] = []
    if len(coords) < 4:
        return errors
    for first_index in range(len(coords) - 1):
        a = coords[first_index]
        b = coords[first_index + 1]
        for second_index in range(first_index + 2, len(coords) - 1):
            if second_index == first_index + 1:
                continue
            if first_index == 0 and second_index == len(coords) - 2:
                continue
            c = coords[second_index]
            d = coords[second_index + 1]
            if _template_segments_intersect(a, b, c, d):
                errors.append(f"Segment {first_index + 1}-{first_index + 2} kreuzt {second_index + 1}-{second_index + 2}")
    return errors


def validate_gleisplan_template(template: dict[str, Any], *, endpoint_tolerance_pct: float = 0.15) -> dict[str, Any]:
    items = [dict(item) for item in (template.get("layout_items") or ())]
    connections = [dict(connection) for connection in (template.get("connections") or ())]
    items_by_id = {str(item.get("item_id") or "").strip().upper(): item for item in items}
    switch_ids = {
        str(item.get("item_id") or "").strip().upper()
        for item in items
        if str(item.get("item_type") or "").strip().lower() == "switch"
    }
    buffer_stop_ids = {
        str(item.get("item_id") or "").strip().upper()
        for item in items
        if str(item.get("item_type") or "").strip().lower() == "buffer_stop"
    }
    degrees: dict[str, int] = {item_id: 0 for item_id in items_by_id}
    invalid_connections: list[str] = []
    route_endpoint_errors: list[str] = []
    switch_direction_errors: list[str] = []
    route_self_crossing_errors: list[str] = []
    for connection in connections:
        source = str(connection.get("source_item_id") or "").strip().upper()
        target = str(connection.get("target_item_id") or "").strip().upper()
        label = str(connection.get("label") or "").strip() or f"{source}->{target}"
        if source not in items_by_id or target not in items_by_id:
            invalid_connections.append(f"{label}: {source} -> {target}")
            continue
        degrees[source] = degrees.get(source, 0) + 1
        degrees[target] = degrees.get(target, 0) + 1
        route = connection.get("route") or {}
        if not isinstance(route, dict):
            continue
        route_points = [point for point in (route.get("points") or []) if isinstance(point, dict)]
        for error in _template_route_self_intersections(route_points):
            route_self_crossing_errors.append(f"{label}: {error}")
        for side, item_id, point_key, anchor_role in (("Start", source, "start", "from"), ("Ende", target, "end", "to")):
            point = route.get(point_key) or {}
            if not isinstance(point, dict):
                route_endpoint_errors.append(f"{label}: {side} ohne Route-Punkt ({item_id})")
                continue
            endpoint_point = route_points[0] if anchor_role == "from" and route_points else route_points[-1] if route_points else point
            if str(endpoint_point.get("anchor") or "").strip().lower() != anchor_role:
                route_endpoint_errors.append(f"{label}: {side} ist kein dynamischer {anchor_role}-Anker ({item_id})")
                continue
            if endpoint_point.get("dx_pct") is None or endpoint_point.get("dy_pct") is None:
                route_endpoint_errors.append(f"{label}: {side} {item_id} hat keinen relativen Anker-Offset")
                continue
            source_item = items_by_id.get(item_id) or {}
            rendered_point = (
                float(source_item.get("x_pct") or 0) + float(endpoint_point.get("dx_pct") or 0),
                float(source_item.get("y_pct") or 0) + float(endpoint_point.get("dy_pct") or 0),
            )
            route_point = (float(point.get("x_pct") or 0), float(point.get("y_pct") or 0))
            dynamic_distance = _template_distance(rendered_point, route_point)
            if dynamic_distance > 0.15:
                route_endpoint_errors.append(
                    f"{label}: {side} {item_id} dynamischer Anker weicht {dynamic_distance:.2f}% vom Route-Punkt ab"
                )
                continue
            item_anchor_name = str(endpoint_point.get("name") or "").strip()
            if item_id in EBERSWALDE_SWITCHES and item_anchor_name:
                switch_anchor = ((EBERSWALDE_SWITCHES[item_id].get("anchors") or {}).get(item_anchor_name) or {})
                if switch_anchor:
                    best_name = item_anchor_name
                    best_point = (float(switch_anchor.get("x_pct") or 0), float(switch_anchor.get("y_pct") or 0))
                else:
                    anchors = _template_anchor_points(item_id, items_by_id)
                    best_name, best_point = min(anchors, key=lambda anchor: _template_distance(route_point, anchor[1]))
            else:
                best_name = item_anchor_name or "relative"
                best_point = rendered_point
            distance = _template_distance(route_point, best_point)
            if distance > endpoint_tolerance_pct:
                route_endpoint_errors.append(
                    f"{label}: {side} {item_id} liegt {distance:.2f}% von Anker {best_name} entfernt"
                )
            if item_id in switch_ids and len(route_points) >= 2:
                expected_dir = endpoint_point.get("dir")
                if expected_dir is None and item_id in EBERSWALDE_SWITCHES and item_anchor_name:
                    expected_dir = (((EBERSWALDE_SWITCHES[item_id].get("anchors") or {}).get(item_anchor_name) or {}).get("dir"))
                if expected_dir is None:
                    switch_direction_errors.append(f"{label}: {side} {item_id}.{item_anchor_name or '?'} ohne Port-Richtung")
                    continue
                if anchor_role == "from":
                    actual_dir = _visual_angle(
                        (float(route_points[0].get("x_pct") or 0), float(route_points[0].get("y_pct") or 0)),
                        (float(route_points[1].get("x_pct") or 0), float(route_points[1].get("y_pct") or 0)),
                    )
                else:
                    actual_dir = _visual_angle(
                        (float(route_points[-1].get("x_pct") or 0), float(route_points[-1].get("y_pct") or 0)),
                        (float(route_points[-2].get("x_pct") or 0), float(route_points[-2].get("y_pct") or 0)),
                    )
                delta = _angle_delta(actual_dir, float(expected_dir))
                if delta > 15.0:
                    switch_direction_errors.append(
                        f"{label}: {side} {item_id}.{item_anchor_name or '?'} Richtungsfehler {delta:.1f}deg "
                        f"(Route {actual_dir:.1f}deg, Port {float(expected_dir):.1f}deg)"
                    )

    switch_errors: list[str] = []
    for switch_id in sorted(switch_ids):
        required = int(EBERSWALDE_SWITCH_REQUIRED_CONNECTIONS.get(switch_id, 2))
        count = degrees.get(switch_id, 0)
        if count < 2:
            switch_errors.append(f"{switch_id}: nur {count} Verbindung(en)")
        elif count < required:
            switch_errors.append(f"{switch_id}: {count} Verbindung(en), erwartet mindestens {required}")

    buffer_errors: list[str] = []
    for buffer_id in sorted(buffer_stop_ids):
        count = degrees.get(buffer_id, 0)
        if count != 1:
            buffer_errors.append(f"{buffer_id}: {count} Verbindung(en), erwartet genau 1")

    join_position_errors: list[str] = []
    switch_positions = {
        switch_id: (
            float((data.get("position") or {}).get("x_pct") or 0),
            float((data.get("position") or {}).get("y_pct") or 0),
        )
        for switch_id, data in EBERSWALDE_SWITCHES.items()
    }
    for item_id, item in items_by_id.items():
        if not item_id.startswith("JOIN_"):
            continue
        center = _template_item_center(item)
        for switch_id, switch_point in switch_positions.items():
            if _template_distance(center, switch_point) <= 0.75:
                join_position_errors.append(f"{item_id} liegt auf {switch_id}")

    switch_overlay_errors: list[str] = [
        f"{switch_id}: nicht als Verbindungsknoten genutzt"
        for switch_id in sorted(switch_ids)
        if degrees.get(switch_id, 0) <= 0
    ]

    return {
        "ok": not any((switch_errors, buffer_errors, invalid_connections, route_endpoint_errors, switch_direction_errors, route_self_crossing_errors, join_position_errors, switch_overlay_errors)),
        "switch_connection_counts": {switch_id: degrees.get(switch_id, 0) for switch_id in sorted(switch_ids)},
        "buffer_stop_connection_counts": {buffer_id: degrees.get(buffer_id, 0) for buffer_id in sorted(buffer_stop_ids)},
        "switch_errors": switch_errors,
        "buffer_errors": buffer_errors,
        "invalid_connections": invalid_connections,
        "route_endpoint_errors": route_endpoint_errors,
        "switch_direction_errors": switch_direction_errors,
        "route_self_crossing_errors": route_self_crossing_errors,
        "join_position_errors": join_position_errors,
        "switch_overlay_errors": switch_overlay_errors,
    }


def format_gleisplan_template_validation(validation: dict[str, Any]) -> list[str]:
    def section(label: str, key: str) -> str:
        values = validation.get(key) or []
        return f"- {label}: OK" if not values else f"- {label}: FEHLER: " + "; ".join(str(value) for value in values)

    return [
        "Template-Pruefung Eberswalde:",
        section("Weichen verbunden", "switch_errors"),
        section("Prellboecke verbunden", "buffer_errors"),
        section("Verbindungen mit ungültigen Endpunkten", "invalid_connections"),
        section("Routen-Endpunkte an Objekt-Ankern", "route_endpoint_errors"),
        section("Weichen-Port-Richtungen", "switch_direction_errors"),
        section("Selbstkreuzende Routen", "route_self_crossing_errors"),
        section("JOIN-Punkte auf Weichenpositionen", "join_position_errors"),
        section("Weichen nur optisch auf Route", "switch_overlay_errors"),
    ]


GLEISPLAN_LAYOUT_TEMPLATES: dict[str, dict[str, Any]] = {
    EBERSWALDE_LAGEPLAN_TEMPLATE_KEY: {
        "key": EBERSWALDE_LAGEPLAN_TEMPLATE_KEY,
        "label": EBERSWALDE_LAGEPLAN_TEMPLATE_LABEL,
        "layout_items": EBERSWALDE_LAGEPLAN_LAYOUT_ITEMS,
        "connections": EBERSWALDE_LAGEPLAN_CONNECTIONS,
        "hall_tracks": EBERSWALDE_LAGEPLAN_HALL_TRACKS,
        "track_routes": EBERSWALDE_TRACK_ROUTES,
        "switches": EBERSWALDE_SWITCHES,
    }
}
