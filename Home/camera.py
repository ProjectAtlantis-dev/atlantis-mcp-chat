"""Cameras — where each terminal is looking.

A *camera* is one terminal's viewpoint: it maps a terminal_key (the PK,
atlantis session_key narrowed to one shell — i.e. sessionKey + shell) to the
Location that terminal is currently watching.

The mapping is per game and lives in Data/games/<key>/cameras.json. The stored
file starts empty; bindings appear only as terminals are assigned to locations.
The *view* (`_camera_rows`), however, is an outer join against standable
locations — see that function.
"""

import atlantis
import os
from typing import Any, Dict, List

from dynamic_functions.Home.common import (
    _read_json,
    _write_json,
    require_game_dir,
    require_membership,
)
from dynamic_functions.Home.location import (
    _leaf_location_keys,
    _load_location,
    _require_leaf,
    location_image_path,
)


# ---------------------------------------------------------------------------
# Camera store — terminal_key -> location, per game
# ---------------------------------------------------------------------------

def _cameras_path(game_key: str) -> str:
    return os.path.join(require_game_dir(game_key), "cameras.json")


def _load_cameras(game_key: str) -> Dict[str, Dict[str, str]]:
    return _read_json(_cameras_path(game_key), {}) or {}


def _save_cameras(game_key: str, cameras: Dict[str, Dict[str, str]]) -> None:
    _write_json(_cameras_path(game_key), cameras)


def _camera_rows(game_key: str) -> List[Dict[str, str]]:
    """Pure data: outer join of standable locations against bound terminals.

    Mirrors `_slot_rows` (one row per bot): exactly one row per leaf location.
    Every terminal watching it — a single user's many shells, or many users — is
    stacked newline-separated in the `terminal` cell; a location nobody is
    watching gets an empty `terminal`. No client side effects.
    """
    cameras = _load_cameras(game_key)
    by_location: Dict[str, List[str]] = {}
    for terminal_key, entry in cameras.items():
        by_location.setdefault(entry["location"], []).append(terminal_key)
    return [
        {"location": location, "terminal": "\n".join(sorted(by_location.get(location, [])))}
        for location in _leaf_location_keys()
    ]


async def _render_cameras(game_key: str) -> List[Dict[str, str]]:
    """Push the camera table to the client and return the rows."""
    rows = _camera_rows(game_key)
    await atlantis.client_data("Cameras", rows, column_formatter={
        "terminal": {"type": "pre"},
    })
    return rows


@public
async def camera_list(game_key: str) -> List[Dict[str, str]]:
    """Show which Location each terminal is watching in this game."""
    require_membership(game_key)
    return await _render_cameras(game_key)


@visible
async def camera_bind(game_key: str, location: str, align: str = "") -> Dict[str, str]:
    """Bind the calling terminal to a Location, establishing its camera.

    The terminal_key (sessionKey + shell) of the calling shell starts watching
    `location`, and the terminal's background is repainted to that location's
    image. This is the invariant: a bound terminal always shows the location it
    is watching. Re-binding the same terminal simply moves its camera — each
    terminal watches exactly one place. The location must be standable (a leaf)
    and have an image; containers, unknown names, and imageless leaves are
    rejected before anything is mutated.

    `align` is forwarded to set_background's vertical_align; if empty, the
    location's `defaultCameraAlign` is used (which is required to be set).
    """
    require_membership(game_key)
    terminal_key = atlantis.get_terminal_key()
    if not terminal_key:
        raise RuntimeError("No terminal key in this call context")
    loc = _load_location(location)
    if not loc:
        raise ValueError(f"Unknown location: {location}")
    _require_leaf(location)
    background = location_image_path(location)  # resolve + validate before mutating
    if not align:
        align = loc.get("defaultCameraAlign", "")
        if not align:
            raise ValueError(f"Location {location!r} has no defaultCameraAlign set")

    cameras = _load_cameras(game_key)
    cameras[terminal_key] = {"location": location, "align": align}
    _save_cameras(game_key, cameras)

    await atlantis.set_background(background, vertical_align=align)
    await _render_cameras(game_key)
    return {"terminal": terminal_key, "location": location, "align": align}
