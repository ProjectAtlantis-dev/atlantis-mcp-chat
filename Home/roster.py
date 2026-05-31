"""Per-game roster tools."""

import atlantis
import os
from datetime import datetime
from typing import Any, Dict, List

from dynamic_functions.Home.bot import load_bot
from dynamic_functions.Home.common import _read_json, _write_json
from dynamic_functions.Home.game import require_membership
from dynamic_functions.Home.scene import _load_scene, _scene_name, _scene_names


def _number_duplicate_display_names(rows: List[Dict[str, Any]]) -> None:
    used: set[str] = set()
    for row in rows:
        display_name = str(row.get("displayName", "")).strip()
        key = str(row.get("key", "")).strip()
        if not display_name:
            raise ValueError(f"Roster row {key!r} is missing displayName")

        if display_name not in used:
            used.add(display_name)
            continue

        count = 2
        numbered_name = f"{display_name} {count}"
        while numbered_name in used:
            count += 1
            numbered_name = f"{display_name} {count}"
        row["displayName"] = numbered_name
        used.add(numbered_name)


def _scene_roster_rows(scene: str) -> List[Dict[str, Any]]:
    """Convert a static scene into initial per-game roster rows."""
    rows: List[Dict[str, Any]] = []
    for index, slot in enumerate(_load_scene(scene)):
        if not isinstance(slot, dict):
            raise ValueError(f"Scene {scene!r} row {index} must be an object")

        key = str(slot.get("key", "")).strip()
        bot_sid = str(slot.get("bot_sid", "")).strip()
        if not key:
            raise ValueError(f"Scene {scene!r} row {index} is missing key")
        if not bot_sid:
            raise ValueError(f"Scene {scene!r} row {index} is missing bot_sid")

        bot = load_bot(bot_sid)
        rows.append({
            "key": key,
            "bot_sid": bot_sid,
            "ai": True,
            "displayName": bot["displayName"],
        })
    return rows


def _load_game_roster(game_key: str) -> List[Dict[str, Any]]:
    """Load a game's finalized roster.json, requiring it to already exist."""
    data_dir = require_membership(game_key)
    roster_path = os.path.join(data_dir, "roster.json")
    if not os.path.isfile(roster_path):
        raise RuntimeError("must create scene roster for this game first")

    rows = _read_json(roster_path)
    if not isinstance(rows, list):
        raise ValueError(f"Game {game_key!r} roster.json must be a JSON array")
    return rows


@public
async def roster_list() -> List[Dict[str, Any]]:
    """Show all generated roster rows, grouped by source scene filename."""
    rows: List[Dict[str, Any]] = []
    for scene_name in _scene_names():
        scene_rows = _scene_roster_rows(scene_name)
        _number_duplicate_display_names(scene_rows)
        rows.extend({
            "scene_name": scene_name,
            **row,
        } for row in scene_rows)
    await atlantis.client_data("Rosters", rows)
    return rows


@public
async def roster_create(game_key: str, scene: str) -> List[Dict[str, Any]]:
    """Create Data/games/<game_key>/roster.json from a static scene file."""
    data_dir = require_membership(game_key)
    scene_name = _scene_name(scene)
    rows = _scene_roster_rows(scene)
    _number_duplicate_display_names(rows)
    _write_json(os.path.join(data_dir, "roster.json"), rows)
    meta = _read_json(os.path.join(data_dir, "game.json")) or {}
    meta["roster"] = {
        "scene": scene_name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    _write_json(os.path.join(data_dir, "game.json"), meta)
    await atlantis.client_data(f"{game_key} roster", rows)
    return rows


@public
async def roster_show(game_key: str) -> List[Dict[str, Any]]:
    """Show Data/games/<game_key>/roster.json, if a scene roster has been created."""
    rows = _load_game_roster(game_key)
    await atlantis.client_data(f"{game_key} roster", rows)
    return rows
