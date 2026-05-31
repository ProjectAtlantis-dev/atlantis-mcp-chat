"""Slots — which bot each game actor is driving.

A slot is the per-game runtime seat for one bot sid. `_slot_rows` is an outer
join of static bots with Data/games/<key>/slots.json so every bot always has
one row. The row tells the engine whether the bot is empty, AI-driven, or
human-driven.

Users have two independent bindings:
- their session binds to a slot when they drive a bot;
- each terminal binds to a camera when that shell watches a location.
"""

import atlantis
import os
from datetime import datetime
from typing import Any, Dict, List

from dynamic_functions.Home.common import (
    _read_json,
    _write_json,
    home_path,
)
from dynamic_functions.Home.bot import _bots_dir, bot_entry_location
from dynamic_functions.Home.game import require_game_dir, require_membership


def _slots_path(game_key: str) -> str:
    return os.path.join(require_game_dir(game_key), "slots.json")


def _load_slots(game_key: str) -> Dict[str, Dict[str, Any]]:
    return _read_json(_slots_path(game_key), {}) or {}


def _save_slots(game_key: str, slots: Dict[str, Dict[str, Any]]) -> None:
    _write_json(_slots_path(game_key), slots)


def _list_bot_sids() -> List[str]:
    d = _bots_dir()
    if not os.path.isdir(d):
        return []
    return sorted(
        entry for entry in os.listdir(d)
        if os.path.isdir(os.path.join(d, entry))
        and not entry.startswith(".") and entry != "__pycache__"
    )


def _bot_config(bot_sid: str) -> Dict[str, Any]:
    p = os.path.join(_bots_dir(), bot_sid, "config.json")
    return _read_json(p, {}) or {}


def _slot_assignment(state: Dict[str, Any]) -> str:
    """Return the engine assignment for a slot: empty, ai, or human."""
    if state.get("assignment") in {"empty", "ai", "human"}:
        return str(state["assignment"])
    if state.get("sessionKey"):
        return "human"
    if state.get("currentOccupant"):
        return "ai"
    return "empty"


def _slot_rows(game_key: str) -> List[Dict[str, Any]]:
    """Pure data: bot outer join with live slot state. No client side effects."""
    live = _load_slots(game_key)
    rows: List[Dict[str, Any]] = []
    for bot_sid in _list_bot_sids():
        cfg = _bot_config(bot_sid)
        state = live.get(bot_sid, {})
        start = str(cfg.get("defaultLocation", "") or "")
        rows.append({
            "botSid": bot_sid,
            "displayName": cfg.get("displayName", bot_sid),
            "assignment": _slot_assignment(state),
            "currentOccupant": state.get("currentOccupant", ""),
            "currentDisplayName": state.get("currentDisplayName", ""),
            "sessionKey": state.get("sessionKey", ""),
            "startLocation": start,
            "currentLocation": state.get("currentLocation", ""),
        })
    return rows


def slot_occupants_at(game_key: str, location: str) -> List[Dict[str, Any]]:
    """Slot rows actually present in `location` (currentLocation only)."""
    out: List[Dict[str, Any]] = []
    for row in _slot_rows(game_key):
        if row["assignment"] == "empty":
            continue
        if not row["currentOccupant"] or row["currentLocation"] != location:
            continue
        out.append({
            "occupant": row["currentOccupant"],
            "displayName": row["currentDisplayName"] or row["currentOccupant"],
            "botSid": row["botSid"],
            "assignment": row["assignment"],
        })
    return out


def slot_location(game_key: str, sid: str) -> str:
    """Return the current location of the slot occupied by `sid`, or raise."""
    if not sid:
        raise ValueError("slot_location: empty sid")
    for row in _slot_rows(game_key):
        if row["currentOccupant"] == sid:
            if not row["currentLocation"]:
                raise ValueError(f"{sid!r} is bound to {row['botSid']!r} but has not been spawned into a location")
            return row["currentLocation"]
    raise ValueError(f"no slot found for occupant {sid!r}")


@public
async def slot_list(game_key: str) -> List[Dict[str, Any]]:
    """Show runtime slots — one row per bot."""
    require_membership(game_key)
    rows = _slot_rows(game_key)
    await atlantis.client_data("Slots", rows)
    return rows


async def _render_slots(game_key: str) -> List[Dict[str, Any]]:
    """Push the slot table to the client and return the rows."""
    rows = _slot_rows(game_key)
    await atlantis.client_data("Slots", rows)
    return rows


@visible
async def slot_bind(game_key: str, bot_sid: str) -> Dict[str, str]:
    """Bind the calling session to a bot slot.

    This is the session-side counterpart to `camera_bind`: a session controls
    which bot the user can chat as, while each terminal separately controls
    what location that shell is watching.
    """
    require_membership(game_key)
    if bot_sid not in _list_bot_sids():
        raise ValueError(f"Unknown bot: {bot_sid}")

    session_key = atlantis.get_session_key()
    if not session_key:
        raise RuntimeError("No session key in this call context")

    caller = atlantis.get_caller() or session_key

    slots = _load_slots(game_key)

    for slot_bot_sid, state in list(slots.items()):
        if slot_bot_sid != bot_sid and state.get("sessionKey") == session_key:
            state.pop("sessionKey", None)
            state.pop("currentDisplayName", None)
            state.pop("currentLocation", None)
            state["assignment"] = "empty"
            state["currentOccupant"] = ""

    state = slots.setdefault(bot_sid, {})
    existing_session = state.get("sessionKey")
    if existing_session and existing_session != session_key:
        raise ValueError(f"Bot {bot_sid!r} is already bound to another session")

    state.update({
        "assignment": "human",
        "currentOccupant": caller,
        "currentDisplayName": caller,
        "sessionKey": session_key,
    })
    _save_slots(game_key, slots)

    await _render_slots(game_key)
    return {
        "botSid": bot_sid,
        "assignment": "human",
        "currentOccupant": caller,
        "sessionKey": session_key,
        "currentLocation": state.get("currentLocation", ""),
    }


@visible
async def slot_spawn(game_key: str, location: str = "") -> Dict[str, str]:
    """Place the calling session's bound slot into a location.

    Spawn is separate from bind: binding says which bot you drive, spawning
    puts that bot into the world. If `location` is omitted, the bot's
    defaultLocation is used.
    """
    require_membership(game_key)

    session_key = atlantis.get_session_key()
    if not session_key:
        raise RuntimeError("No session key in this call context")

    slots = _load_slots(game_key)
    bound_bot_sid = next(
        (bot_sid for bot_sid, state in slots.items() if state.get("sessionKey") == session_key),
        None,
    )
    if not bound_bot_sid:
        raise ValueError("This session is not bound to any slot — call slot_bind first")

    target = location or bot_entry_location(bound_bot_sid)
    slots[bound_bot_sid]["currentLocation"] = target
    _save_slots(game_key, slots)

    display = slots[bound_bot_sid].get("currentDisplayName") or slots[bound_bot_sid].get("currentOccupant", "")
    await atlantis.client_log(f"{display} has entered the {target}")
    await _render_slots(game_key)
    return {"botSid": bound_bot_sid, "currentLocation": target}


# ---------------------------------------------------------------------------
# Prompt assembly.
# ---------------------------------------------------------------------------

def load_bot_prompt(bot_sid: str) -> str:
    """Read a bot's prompt.md."""
    path = os.path.join(home_path("Game", "Bots", bot_sid), "prompt.md")
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def slot_prompt(
    bot_sid: str,
    location: str = "",
) -> str:
    """Assemble the full system prompt for an AI-driven bot.

    Static character/appearance text comes from Game/Bots/<sid>/prompt.md;
    the setting and current time are layered on at runtime.
    """
    from dynamic_functions.Home.location import location_compose_descriptions

    parts: List[str] = ["## Director's Note\n\nWe are striving for realistic dialog."]

    setting = location_compose_descriptions(location) if location else ""
    if setting:
        parts.append(f"## Setting\n\n{setting}")

    parts.append(load_bot_prompt(bot_sid))
    parts.append(f"## Current Time\n\n{datetime.now().strftime('%Y-%m-%d %H:%M')}")

    return "\n\n".join(parts)
