"""Per-game roster tools."""

import atlantis
import os
from datetime import datetime
from typing import Any, Dict, List

from dynamic_functions.Home.bot import load_bot
from dynamic_functions.Home.common import _read_json, _write_json
from dynamic_functions.Home.game import require_membership
from dynamic_functions.Home.scene import _load_scene, _scene_name


def _scene_roster_rows(scene: str) -> List[Dict[str, Any]]:
    """Convert a static scene into initial per-game roster rows."""
    rows: List[Dict[str, Any]] = []
    for index, slot in enumerate(_load_scene(scene)):
        if not isinstance(slot, dict):
            raise ValueError(f"Scene {scene!r} row {index} must be an object")

        name = str(slot.get("name", "")).strip()
        bot_sid = str(slot.get("bot_sid", "")).strip()
        if not name:
            raise ValueError(f"Scene {scene!r} row {index} is missing name")
        if not bot_sid:
            raise ValueError(f"Scene {scene!r} row {index} is missing bot_sid")

        load_bot(bot_sid)
        rows.append({
            **slot,
            "name": name,
            "bot_sid": bot_sid,
            "ai": True,
            "finalName": name,
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
async def roster_create(game_key: str, scene: str) -> List[Dict[str, Any]]:
    """Create Data/games/<game_key>/roster.json from a static scene file."""
    data_dir = require_membership(game_key)
    scene_name = _scene_name(scene)
    rows = _scene_roster_rows(scene)
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
