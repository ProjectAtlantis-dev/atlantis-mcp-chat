"""Per-game roster tools."""

import atlantis
import os
import shlex
from datetime import datetime
from typing import Any, Dict, List

from .bot import load_bot
from .common import _read_json, _write_json
from .game import require_membership
from .scene import _load_scene, _scene_name


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
            "session_key": "",
            "sid": "",
            "user_game_id": "",
            "bound_at": "",
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


def _write_game_roster(game_key: str, rows: List[Dict[str, Any]]) -> None:
    data_dir = require_membership(game_key)
    _write_json(os.path.join(data_dir, "roster.json"), rows)


@public
async def roster_list(game_key: str) -> List[Dict[str, Any]]:
    """Show this game's live roster.json, including any roster_bind changes."""
    rows = _load_game_roster(game_key)
    await atlantis.client_data(f"{game_key} roster", rows)
    return rows


@public
async def roster_create(game_key: str, scene: str) -> List[Dict[str, Any]]:
    """Create Data/games/<game_key>/roster.json from a static scene file."""
    await atlantis.client_log(f"roster_create game_key: {game_key!r} scene: {scene!r}")
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
async def roster_bind(game_key: str, slot_key: str) -> Dict[str, Any]:
    """Bind the caller's Atlantis session to a slot in this game's roster."""
    session_key = atlantis.get_session_key()
    if not session_key:
        raise RuntimeError("No session key in this call context")
    await atlantis.client_log(
        f"roster_bind game_key: {game_key!r} slot_key: {slot_key!r} session_key: {session_key!r}"
    )

    slot_key = str(slot_key or "").strip()
    if not slot_key:
        raise ValueError("slot_key required")

    rows = _load_game_roster(game_key)
    target = None
    for row in rows:
        if row.get("session_key") == session_key and row.get("key") != slot_key:
            raise RuntimeError(f"Session is already bound to slot {row.get('key')!r}")
        if str(row.get("key", "")).strip() == slot_key:
            target = row

    if target is None:
        raise ValueError(f"Unknown roster slot: {slot_key!r}")

    existing_session = str(target.get("session_key", "") or "").strip()
    if existing_session and existing_session != session_key:
        raise RuntimeError(f"Slot {slot_key!r} is already bound")

    display_name = await atlantis.client_command(
        "@modal_string "
        f"{shlex.quote('What should people call you?')} "
        f"{shlex.quote('Your name')} "
        f"{shlex.quote('')} "
        f"{shlex.quote('Join')}"
    )
    if display_name is None:
        return {"cancelled": True, "key": slot_key}
    display_name = str(display_name or "").strip()
    if not display_name:
        raise ValueError("display_name required")

    target["session_key"] = session_key
    target["sid"] = atlantis.get_caller() or ""
    target["user_game_id"] = atlantis.get_user_game_id()
    target["ai"] = False
    target["displayName"] = display_name
    target["bound_at"] = datetime.now().isoformat(timespec="seconds")

    _write_game_roster(game_key, rows)
    await atlantis.client_log(f"Saved roster binding for {game_key!r} slot {slot_key!r}")
    await atlantis.client_data(f"{game_key} roster slot", target)
    await atlantis.client_data(f"{game_key} roster", rows)
    return target


@public
async def roster_show(game_key: str) -> List[Dict[str, Any]]:
    """Show Data/games/<game_key>/roster.json, if a scene roster has been created."""
    return await roster_list(game_key)
