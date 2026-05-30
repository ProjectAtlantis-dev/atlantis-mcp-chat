"""Slots — which role each game actor is driving.

A *slot* is the per-game runtime seat for one role. `_slot_rows` is an outer
join of static roles with Data/games/<key>/slots.json so every role always has
one row. The row tells the engine whether the role is empty, AI-driven, or
human-driven.

Users have two independent bindings:
- their session binds to a slot when they play a role;
- each terminal binds to a camera when that shell watches a location.

AI prompt variants still live under Game/Slots/<role>_<bot>/, but that directory
is prompt/config material for an AI assignment, not the slot identity itself.
"""

import atlantis
import os
from datetime import datetime
from typing import Any, Dict, List

from dynamic_functions.Home.common import (
    _read_json,
    _write_json,
    _roles_dir,
    home_path,
    require_game_dir,
    require_membership,
)
from dynamic_functions.Home.role import role_entry_location


def _slots_path(game_key: str) -> str:
    return os.path.join(require_game_dir(game_key), "slots.json")


def _load_slots(game_key: str) -> Dict[str, Dict[str, Any]]:
    return _read_json(_slots_path(game_key), {}) or {}


def _save_slots(game_key: str, slots: Dict[str, Dict[str, Any]]) -> None:
    _write_json(_slots_path(game_key), slots)


def _list_role_keys() -> List[str]:
    d = _roles_dir()
    if not os.path.isdir(d):
        return []
    return sorted(
        entry for entry in os.listdir(d)
        if os.path.isdir(os.path.join(d, entry))
        and not entry.startswith(".") and entry != "__pycache__"
    )


def _role_config(role: str) -> Dict[str, Any]:
    p = os.path.join(_roles_dir(), role, "config.json")
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
    """Pure data: role outer join with live slot state. No client side effects."""
    live = _load_slots(game_key)
    rows: List[Dict[str, Any]] = []
    for role in _list_role_keys():
        cfg = _role_config(role)
        state = live.get(role, {})
        start = str(cfg.get("defaultLocation", "") or "")
        rows.append({
            "role": role,
            "roleDisplayName": cfg.get("displayName", role),
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
            "role": row["role"],
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
                raise ValueError(f"{sid!r} is bound to {row['role']!r} but has not been spawned into a location")
            return row["currentLocation"]
    raise ValueError(f"no slot found for occupant {sid!r}")


@public
async def slot_list(game_key: str) -> List[Dict[str, Any]]:
    """Show runtime slots — one row per role."""
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
async def slot_bind(game_key: str, role: str) -> Dict[str, str]:
    """Bind the calling session to a role slot.

    This is the session-side counterpart to `camera_bind`: a session controls
    what role the user can chat as, while each terminal separately controls
    what location that shell is watching.
    """
    require_membership(game_key)
    if role not in _list_role_keys():
        raise ValueError(f"Unknown role: {role}")

    session_key = atlantis.get_session_key()
    if not session_key:
        raise RuntimeError("No session key in this call context")

    caller = atlantis.get_caller() or session_key

    slots = _load_slots(game_key)

    for slot_role, state in list(slots.items()):
        if slot_role != role and state.get("sessionKey") == session_key:
            state.pop("sessionKey", None)
            state.pop("currentDisplayName", None)
            state.pop("currentLocation", None)
            state["assignment"] = "empty"
            state["currentOccupant"] = ""

    state = slots.setdefault(role, {})
    existing_session = state.get("sessionKey")
    if existing_session and existing_session != session_key:
        raise ValueError(f"Role {role!r} is already bound to another session")

    state.update({
        "assignment": "human",
        "currentOccupant": caller,
        "currentDisplayName": caller,
        "sessionKey": session_key,
    })
    _save_slots(game_key, slots)

    await _render_slots(game_key)
    return {
        "role": role,
        "assignment": "human",
        "currentOccupant": caller,
        "sessionKey": session_key,
        "currentLocation": state.get("currentLocation", ""),
    }


@visible
async def slot_spawn(game_key: str, location: str = "") -> Dict[str, str]:
    """Place the calling session's bound slot into a location.

    Spawn is separate from bind: binding says which role you play, spawning
    puts that role into the world. If `location` is omitted, the role's
    defaultLocation is used.
    """
    require_membership(game_key)

    session_key = atlantis.get_session_key()
    if not session_key:
        raise RuntimeError("No session key in this call context")

    slots = _load_slots(game_key)
    bound_role = next(
        (role for role, state in slots.items() if state.get("sessionKey") == session_key),
        None,
    )
    if not bound_role:
        raise ValueError("This session is not bound to any slot — call slot_bind first")

    target = location or role_entry_location(bound_role)
    slots[bound_role]["currentLocation"] = target
    _save_slots(game_key, slots)

    display = slots[bound_role].get("currentDisplayName") or slots[bound_role].get("currentOccupant", "")
    await atlantis.client_log(f"{display} has entered the {target}")
    await _render_slots(game_key)
    return {"role": bound_role, "currentLocation": target}


# ---------------------------------------------------------------------------
# Prompt assembly — AI role assignments use per-(role, bot) prompt material.
# ---------------------------------------------------------------------------

def _slot_key(role: str, bot: str) -> str:
    return f"{role}_{bot}"


def _slot_dir(role: str, bot: str) -> str:
    return home_path("Game", "Slots", _slot_key(role, bot))


def load_slot_prompt(role: str, bot: str) -> str:
    """Read the static consolidated prompt.md for a role-specific bot prompt."""
    path = os.path.join(_slot_dir(role, bot), "prompt.md")
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def build_interaction_context(
    caller: str,
    prior_interaction_count: int,
    last_interaction_at: str,
    first_name: str = "",
) -> str:
    """Note describing how well the bot knows this caller and when they last spoke."""
    if not caller:
        return ""

    display_name = first_name or caller

    hour = datetime.now().hour
    late_night = hour >= 22 or hour < 5

    if prior_interaction_count <= 0:
        if late_night:
            note = f"This is your first interaction with {display_name}. It's late — welcome them warmly."
        else:
            note = f"This is your first interaction with {display_name}. Introduce yourself and help them get oriented."
    elif prior_interaction_count == 1:
        note = f"You have interacted with {display_name} once before. Greet them like someone you remember, but don't overdo it."
    elif prior_interaction_count <= 5:
        note = f"You have interacted with {display_name} {prior_interaction_count} times before. They're still fairly new — keep context light."
    else:
        note = f"You have interacted with {display_name} {prior_interaction_count} times before. They're familiar — skip the intros and be casual."

    if last_interaction_at and prior_interaction_count > 0:
        try:
            elapsed = datetime.now() - datetime.fromisoformat(last_interaction_at)
            days = elapsed.days
            hours = elapsed.seconds // 3600
            if days > 30:
                note += f" It has been about {days // 30} month(s) since your last interaction — maybe acknowledge it's been a while."
            elif days > 0:
                note += f" It has been about {days} day(s) since your last interaction."
            elif hours > 0:
                note += f" Your last interaction was about {hours} hour(s) ago."
            else:
                note += " Your last interaction was moments ago."
        except (ValueError, TypeError):
            pass

    return note


def slot_prompt(
    role: str,
    bot: str,
    location: str = "",
    speaker_name: str = "",
    prior_interaction_count: int = 0,
    last_interaction_at: str = "",
) -> str:
    """Assemble the full system prompt for an AI-driven role.

    Static character/appearance/role text comes from Game/Slots/<role>_<bot>/;
    the setting, current time, and interaction history are layered on at runtime.
    """
    from dynamic_functions.Home.location import location_compose_descriptions

    parts: List[str] = ["## Director's Note\n\nWe are striving for realistic dialog."]

    setting = location_compose_descriptions(location) if location else ""
    if setting:
        parts.append(f"## Setting\n\n{setting}")

    parts.append(load_slot_prompt(role, bot))
    parts.append(f"## Current Time\n\n{datetime.now().strftime('%Y-%m-%d %H:%M')}")

    note = build_interaction_context(
        speaker_name, prior_interaction_count, last_interaction_at, speaker_name
    )
    if note:
        parts.append(f"## Interaction History\n\n{note}")

    return "\n\n".join(parts)
