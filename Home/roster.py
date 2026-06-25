"""Per-game roster tools."""

import atlantis
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from .bot import load_bot
from .common import _read_json, _write_json
from .game import require_membership
from .location import _connects_to, _require_leaf, load_location
from .modal import modal_string
from .scene import _load_scene, _scene_name, _scene_names


def _number_duplicate_display_names(rows: List[Dict[str, Any]]) -> None:
    used: set[str] = set()
    for row in rows:
        raw_display_name = row.get("displayName")
        if raw_display_name is None:
            continue
        display_name = str(raw_display_name).strip()
        if not display_name:
            continue

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

        load_bot(bot_sid)
        rows.append({
            "key": key,
            "bot_sid": bot_sid,
            "ai": True,
            "displayName": None,
            "location": None,
            "spawned_at": None,
            "session_key": None,
            "sid": None,
            "user_game_id": None,
            "bound_at": None,
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


def _find_roster_row(rows: List[Dict[str, Any]], sid_or_key: str) -> Dict[str, Any]:
    """Find one roster row by slot key, human sid, or AI bot sid."""
    needle = str(sid_or_key or "").strip()
    if not needle:
        raise ValueError("sid required")

    matches: List[Dict[str, Any]] = []
    for row in rows:
        candidates = [row.get("key")]
        if row.get("ai") is False:
            candidates.append(row.get("sid"))
        else:
            candidates.append(row.get("bot_sid"))
        if needle in candidates:
            matches.append(row)

    if not matches:
        raise ValueError(f"Unknown roster sid or slot: {needle!r}")
    if len(matches) > 1:
        keys = ", ".join(row["key"] for row in matches)
        raise ValueError(f"Roster id {needle!r} is ambiguous; use one of these slot keys: {keys}")
    return matches[0]


def _write_game_roster(game_key: str, rows: List[Dict[str, Any]]) -> None:
    data_dir = require_membership(game_key)
    _write_json(os.path.join(data_dir, "roster.json"), rows)


def _roster_rows() -> List[Dict[str, Any]]:
    """Pure data: scene roster definitions. No client side effects."""
    rows: List[Dict[str, Any]] = []

    for scene_name in _scene_names():
        for row in _scene_roster_rows(scene_name):
            out = dict(row)
            out["scene_name"] = scene_name
            rows.append(out)
    return rows


def _display_roster_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Project live roster rows into the table order shown to users."""
    columns = [
        "key",
        "bot_sid",
        "ai",
        "displayName",
        "sid",
        "location",
        "session_key",
        "bound_at",
        "spawned_at",
    ]
    return [
        {column: row.get(column, "") for column in columns}
        for row in rows
    ]


@public
async def roster_list(game_key: str) -> List[Dict[str, Any]]:
    """Show this game's live roster.json, including any roster_bind changes."""
    rows = _load_game_roster(game_key)
    await atlantis.client_data(f"{game_key} roster", _display_roster_rows(rows))
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
    meta["roster_scene"] = scene_name
    meta["roster_created_at"] = datetime.now().isoformat(timespec="seconds")
    meta.pop("roster", None)
    _write_json(os.path.join(data_dir, "game.json"), meta)
    await atlantis.client_data(f"{game_key} roster", _display_roster_rows(rows))
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
        if row.get("key") == slot_key:
            target = row

    if target is None:
        raise ValueError(f"Unknown roster slot: {slot_key!r}")

    existing_session = target.get("session_key")
    if existing_session and existing_session != session_key:
        raise RuntimeError(f"Slot {slot_key!r} is already bound")

    display_name = await modal_string(
        f"What name should people call {slot_key}?",
        title="Roster",
        submit_label="Join",
    )
    if display_name is None:
        return {"cancelled": True, "key": slot_key}
    display_name = str(display_name or "").strip()
    if not display_name:
        raise ValueError("display_name required")

    target["session_key"] = session_key
    target["sid"] = atlantis.get_caller() or None
    target["user_game_id"] = atlantis.get_user_game_id()
    target["ai"] = False
    target["displayName"] = display_name
    target["bound_at"] = datetime.now().isoformat(timespec="seconds")

    _write_game_roster(game_key, rows)
    await atlantis.client_log(f"Saved roster binding for {game_key!r} slot {slot_key!r}")
    await atlantis.client_data(f"{game_key} roster slot", _display_roster_rows([target])[0])
    await atlantis.client_data(f"{game_key} roster", _display_roster_rows(rows))
    return target


def _movement_log_label(reason: str) -> str:
    reason = str(reason or "move").strip() or "move"
    labels = {
        "spawn": "spawn",
        "teleport": "teleport",
        "move": "move",
    }
    return labels.get(reason, reason or "move")


async def _notify_roster_slot_moved(game_key: str, target: Dict[str, Any], location: Optional[str]) -> None:
    from .camera import camera_slot_moved

    await camera_slot_moved(game_key, target["key"], location)


def _require_adjacent_move(previous: str, location: str) -> None:
    if not previous:
        raise RuntimeError("Roster slot has no current location; use roster_spawn or roster_teleport first")
    if previous == location:
        return

    from_previous = {str(name or "").strip() for name in _connects_to(previous)}
    from_location = {str(name or "").strip() for name in _connects_to(location)}
    if location in from_previous or previous in from_location:
        return

    allowed = sorted(name for name in (from_previous | from_location) if name)
    suffix = f" Adjacent locations: {', '.join(allowed)}." if allowed else ""
    raise ValueError(f"Cannot move from {previous!r} to non-adjacent location {location!r}.{suffix}")


async def _roster_move(game_key: str, sid_or_slot: str, location: str, reason: str = "move") -> Dict[str, Any]:
    """Move a roster slot to a Location.

    `sid_or_slot` may be a roster slot key, a bound human sid, or an AI bot sid.
    If a bot sid appears more than once in the roster, use the slot key.
    """
    load_location(location)
    _require_leaf(location)

    rows = _load_game_roster(game_key)
    target = _find_roster_row(rows, sid_or_slot)
    previous = target.get("location") or ""
    movement_reason = str(reason or "move").strip() or "move"
    if movement_reason == "move":
        _require_adjacent_move(previous, location)
    target["location"] = location
    if not target.get("spawned_at") or movement_reason == "spawn":
        target["spawned_at"] = datetime.now().isoformat(timespec="seconds")

    _write_game_roster(game_key, rows)
    log_label = _movement_log_label(movement_reason)
    await atlantis.client_log(
        f"{log_label}: {target.get('displayName', sid_or_slot)} -> {location}"
        + (f" from {previous}" if previous and previous != location else "")
    )
    await atlantis.client_data(f"{game_key} roster slot", _display_roster_rows([target])[0])
    await atlantis.client_data(f"{game_key} roster", _display_roster_rows(rows))
    await _notify_roster_slot_moved(game_key, target, location)
    return target


@public
async def roster_move(game_key: str, sid_or_slot: str, location: str) -> Dict[str, Any]:
    """Move a roster slot to an adjacent Location."""
    return await _roster_move(game_key, sid_or_slot, location, reason="move")


@public
async def roster_spawn(game_key: str, sid_or_slot: str, location: str) -> Dict[str, Any]:
    """Spawn a roster slot by moving it to a Location."""
    return await _roster_move(game_key, sid_or_slot, location, reason="spawn")


@public
async def roster_teleport(game_key: str, sid_or_slot: str, location: str) -> Dict[str, Any]:
    """Teleport a roster slot to a Location."""
    return await _roster_move(game_key, sid_or_slot, location, reason="teleport")


@public
async def roster_despawn(game_key: str, sid: str) -> Dict[str, Any]:
    """Remove a roster entry from its current Location."""
    rows = _load_game_roster(game_key)
    target = _find_roster_row(rows, sid)
    previous = target.get("location") or ""
    target["location"] = None
    target["spawned_at"] = None

    _write_game_roster(game_key, rows)
    await atlantis.client_log(
        f"despawn: {target.get('displayName', sid)}"
        + (f" from {previous}" if previous else "")
    )
    await atlantis.client_data(f"{game_key} roster slot", _display_roster_rows([target])[0])
    await atlantis.client_data(f"{game_key} roster", _display_roster_rows(rows))
    await _notify_roster_slot_moved(game_key, target, None)
    return target


@public
async def roster_show(game_key: str) -> List[Dict[str, Any]]:
    """Show Data/games/<game_key>/roster.json, if a scene roster has been created."""
    return await roster_list(game_key)
