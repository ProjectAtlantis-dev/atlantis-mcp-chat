"""Scene tools

A scene is a named roster of slots — a list of {key, bot_sid} entries that
seed a game's cast. Its identity is the filename: Game/Scenes/<name>.json, the
same way a bot's identity is its folder name.
"""

import atlantis
import logging
import os
import re
from typing import Any, Dict, List

from .common import home_path, _read_json
from .bot import load_bot

logger = logging.getLogger("mcp_server")


def _scenes_dir() -> str:
    return home_path("Game", "Scenes")


def _scene_name(scene: str) -> str:
    """Normalize a scene name or filename to a safe Game/Scenes key."""
    name = str(scene or "").strip()
    if name.endswith(".json"):
        name = name[: -len(".json")]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        raise ValueError(f"Invalid scene name: {scene!r}")
    return name


def _scene_path(scene: str) -> str:
    return os.path.join(_scenes_dir(), f"{_scene_name(scene)}.json")


def _load_scene(scene: str) -> List[Dict[str, str]]:
    """Load a scene's slots — Game/Scenes/<scene>.json, an array of {key, bot_sid}."""
    slots = _read_json(_scene_path(scene))
    if slots is None:
        raise ValueError(f"Unknown scene: {scene!r}")
    if not isinstance(slots, list):
        raise ValueError(f"Scene {scene!r} must be a JSON array")
    return slots


def _scene_names() -> List[str]:
    """List scene names — the filenames under Game/Scenes/, minus .json."""
    scenes_dir = _scenes_dir()
    names = []
    for entry in os.listdir(scenes_dir):
        if entry.startswith(".") or not entry.endswith(".json"):
            continue
        names.append(entry[: -len(".json")])
    return sorted(names)


def _scene_rows() -> List[Dict[str, Any]]:
    """Pure data for scene_list: one row per scene definition."""
    return [
        {"name": name, "slots": len(_load_scene(name))}
        for name in _scene_names()
    ]


@public
async def scene_list() -> List[str]:
    """List available scenes by name."""
    rows = _scene_rows()
    await atlantis.client_data("Scenes", rows)
    return [row["name"] for row in rows]


@public
async def scene_show(scene: str) -> List[Dict[str, Any]]:
    """Show a scene's slots exactly as scene-definition rows.

    Resolving the sid doubles as foreign-key validation: an unknown bot_sid
    raises rather than rendering a dangling row.
    """
    rows = _load_scene(scene)
    for row in rows:
        load_bot(row["bot_sid"])
    await atlantis.client_data(scene, rows)
    return rows
