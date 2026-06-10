"""Game state tools"""

import atlantis
import os
import re
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

from .bot import bot_entry_location
from .common import home_path, _read_json, _write_json
from .term import term_video, term_video_file


# ---------------------------------------------------------------------------
# Game data directory + membership
# ---------------------------------------------------------------------------

def _safe_id(value: str, label: str = "id") -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", str(value or "").strip())
    if not safe:
        raise ValueError(f"Cannot use an empty {label}")
    return safe


def game_dir(game_key: str) -> str:
    """Get a game data directory path"""
    return home_path("Data", "games", _safe_id(game_key, "game_key"))


def require_game_dir(game_key: str) -> str:
    """Get an existing game data directory"""
    path = game_dir(game_key)
    if not os.path.isdir(path):
        raise RuntimeError(f"Invalid game '{game_key}'")
    return path


def _game_roster_scene(meta: Dict[str, Any]) -> Optional[str]:
    """Return the chosen roster scene, if assigned."""
    roster_scene = str(meta.get("roster_scene") or "").strip()
    if roster_scene:
        return roster_scene

    roster = meta.get("roster") or {}
    if isinstance(roster, dict):
        scene = str(roster.get("scene", "") or "").strip()
        if scene:
            return scene
    return None


def _participant_sids(meta: Dict[str, Any]) -> list:
    members = meta.get("members") or {}
    return sorted({
        str(rec.get("sid", "") or "").strip()
        for rec in members.values()
        if isinstance(rec, dict) and str(rec.get("sid", "") or "").strip()
    })


def add_caller_membership(members: Dict[str, Any]) -> Dict[str, Any]:
    session_key = atlantis.get_session_key()
    if not session_key:
        raise RuntimeError("No session key in this call context")
    if session_key in members:
        raise RuntimeError(f"Session is already a member: {session_key}")

    members[session_key] = {
        "sid": atlantis.get_caller() or None,
        "user_game_id": atlantis.get_user_game_id(),
        "shell": atlantis.get_caller_shell_path(),
        "joined_at": datetime.now().isoformat(timespec="seconds"),
    }
    return members


def require_membership(game_key: str) -> str:
    path = require_game_dir(game_key)
    session_key = atlantis.get_session_key()
    if not session_key:
        raise RuntimeError("No session key in this call context")
    meta = _read_json(os.path.join(path, "game.json")) or {}
    members = meta.get("members") or {}
    if session_key not in members:
        raise PermissionError(f"Session is not a member of game '{game_key}'")
    return path

@public
def game_find_latest_owned() -> Optional[str]:
    """Return the newest game owned by the current caller, if one exists."""
    owner = atlantis.get_caller()
    if not owner:
        raise RuntimeError("No caller identity in this call context")

    games_root = home_path("Data", "games")
    if not os.path.isdir(games_root):
        return None

    matches = []
    for game_key in os.listdir(games_root):
        path = os.path.join(games_root, game_key)
        if not os.path.isdir(path):
            continue
        meta = _read_json(os.path.join(path, "game.json")) or {}
        if meta.get("owner") != owner:
            continue
        matches.append((os.path.getctime(path), game_key))

    if not matches:
        return None
    matches.sort(reverse=True)
    return matches[0][1]

@public
async def game_find_or_create() -> str:
    """Return the caller's newest owned game, creating one if needed.

    The current ownership policy is: reuse the caller's newest owned game; if no
    owned game exists, create one and run the normal game initialization path.
    """
    game_key = game_find_latest_owned()
    if game_key:
        data_dir = require_game_dir(game_key)
        meta = _read_json(os.path.join(data_dir, "game.json")) or {}
        members = meta.setdefault("members", {})
        session_key = atlantis.get_session_key()
        if not session_key:
            raise RuntimeError("No session key in this call context")
        if session_key not in members:
            # A new browser/session from the same caller should keep using the
            # caller's current game, but must be added as a member first.
            add_caller_membership(members)
            _write_json(os.path.join(data_dir, "game.json"), meta)
        await atlantis.client_log(f"Existing game found: {game_key}")
        await atlantis.client_command("/cursor join", {"game_key": game_key})
        await game_init(game_key)
        return game_key

    # First chat for this caller: create a game, join the cursor to it, and run
    # game_init so callbacks, roster, binding, and initial spawn are ready.
    keys = await game_new()
    game_key = keys["game_key"]
    await atlantis.client_command("/cursor join", keys)
    await game_init(game_key)
    return game_key

# % ls

# % "Hello"




@public
async def game_button():
    keys = await game_new()
    await atlantis.client_command("/cursor join", keys)
    await atlantis.client_log(f"game_init game_key: {keys['game_key']!r}")
    await game_init(keys["game_key"])
    return keys


@public
async def game_init(game_key: str):
    data_dir = require_membership(game_key)
    session_key = atlantis.get_session_key()
    roster_path = os.path.join(data_dir, "roster.json")

    callbacks = await atlantis.client_command("/callback list")
    chat_row = next(row for row in callbacks if row["mode"] == "chat")

    if not chat_row["toolPath"]:
        matches = await atlantis.client_command("/tool find chat")
        chat_tool = matches[0]
        await atlantis.client_command(f"/callback set chat {chat_tool['searchTerm']}")

        callbacks = await atlantis.client_command("/callback list")
        chat_row = next(row for row in callbacks if row["mode"] == "chat")

    await atlantis.client_log(f"chat callback: toolPath={chat_row['toolPath']!r} filename={chat_row['filename']!r}")

    if os.path.isfile(roster_path):
        roster = await atlantis.client_command("@roster_list")
    else:
        await atlantis.client_log(f"Getting scenes")
        scenes = await atlantis.client_command("@scene_list")
        if not scenes:
            raise RuntimeError("No scenes found")
        scene = scenes[0]
        roster = await atlantis.client_command(f"@roster_create {scene}")
        await atlantis.client_log(f"game scene: {scene!r}")

    caller_sid = atlantis.get_caller()
    bound_row = next((row for row in roster if row.get("session_key") == session_key), None)
    if bound_row is None and caller_sid:
        bound_row = next(
            (
                row for row in roster
                if row.get("ai") is False and row.get("sid") == caller_sid
            ),
            None,
        )
    open_slots = [row for row in roster if not str(row.get("session_key", "") or "").strip()]
    if bound_row is None and open_slots:
        bound_row = await atlantis.client_command(f"@roster_bind {open_slots[0]['key']}")
    if bound_row and not bound_row.get("cancelled") and not bound_row.get("location"):
        location = bot_entry_location(str(bound_row.get("bot_sid", "") or ""))
        await atlantis.client_command(f"@roster_spawn {bound_row['key']} {location}")
    if bound_row and not bound_row.get("cancelled"):
        from .camera import camera_follow

        await camera_follow(game_key, str(bound_row["key"]))


@public
async def game_video(video: str) -> None:
    """Play the named game background video in the terminal."""
    await term_video(f"https://pub-59cb84bebe804fd1b3257bb6c283a2b3.r2.dev/{video}")


@public
async def game_video_file(video_path: str) -> None:
    """Play a local game background video file in the terminal."""
    if not os.path.isabs(video_path):
        video_path = os.path.join(os.path.dirname(__file__), video_path)
    await term_video_file(video_path)


@public
async def game_default_background() -> None:
    """Set the game default background image."""
    await atlantis.set_background(
        os.path.join(os.path.dirname(__file__), "builder.jpg"),
        vertical_align="75%",
    )


@public
async def game_new() -> Dict[str, Any]:
    for _ in range(10):
        game_key = uuid.uuid4().hex
        data_dir = game_dir(game_key)
        if not os.path.exists(data_dir):
            break
    else:
        raise RuntimeError("Unable to allocate a unique game_key")

    data_dir = game_dir(game_key)
    os.makedirs(data_dir, exist_ok=False)
    join_password = uuid.uuid4().hex
    _write_json(os.path.join(data_dir, 'game.json'), {
        'join_password': join_password,
        'owner': atlantis.get_caller() or None,
        'user_game_id': atlantis.get_user_game_id(),
        'roster_scene': None,
        'roster_created_at': None,
        'members': add_caller_membership({}),
    })

    await atlantis.client_log(f"Game created: {game_key}")
    await game_default_background()

    return {
        "game_key": game_key,
        "join_password": join_password,
    }


@public
async def game_list() -> list:
    """List existing games, newest first"""
    games_root = home_path("Data", "games")
    if not os.path.isdir(games_root):
        return []
    entries = []
    for name in os.listdir(games_root):
        path = os.path.join(games_root, name)
        if not os.path.isdir(path):
            continue
        try:
            ts = os.path.getctime(path)
        except OSError:
            continue
        meta = _read_json(os.path.join(path, 'game.json')) or {}
        participant_sids = _participant_sids(meta)
        entries.append({
            "game_key": name,
            "user_game_id": meta.get("user_game_id"),
            "owner": meta.get("owner"),
            "roster_scene": _game_roster_scene(meta),
            "participant_count": len(participant_sids),
            "created": datetime.fromtimestamp(ts).isoformat(timespec="seconds"),
            "_ts": ts,
        })
    entries.sort(key=lambda e: e["_ts"], reverse=True)
    for e in entries:
        del e["_ts"]
    return entries


@public
async def game_show(game_key: str) -> dict:
    """Show a game's status. The owner sees full detail (join password + members);
    everyone else sees only owner, member count, and created time."""
    path = require_game_dir(game_key)
    meta = _read_json(os.path.join(path, 'game.json')) or {}
    owner = meta.get("owner", "")
    members = meta.get("members") or {}
    created = datetime.fromtimestamp(os.path.getctime(path)).isoformat(timespec="seconds")
    roster = _game_roster_scene(meta)

    if atlantis.get_caller() != owner:
        return {
            "game_key": game_key,
            "owner": owner,
            "roster_scene": roster,
            "members": _participant_sids(meta),
            "created": created,
        }

    return {
        "game_key": game_key,
        "user_game_id": meta.get("user_game_id"),
        "owner": owner,
        "roster_scene": roster,
        "roster_created_at": meta.get("roster_created_at"),
        "join_password": meta.get("join_password", ""),
        "members": [
            {
                "session_key": session_key,
                "sid": rec.get("sid"),
                "shell": rec.get("shell"),
                "user_game_id": rec.get("user_game_id"),
                "joined_at": rec.get("joined_at"),
            }
            for session_key, rec in members.items()
        ],
        "created": created,
    }


@public
async def game_password(game_key: str, new_password: str) -> None:
    """Change a game's join password. Only the owner may do this."""
    if not new_password:
        raise ValueError("new_password required")

    path = require_game_dir(game_key)
    meta = _read_json(os.path.join(path, 'game.json')) or {}
    if atlantis.get_caller() != meta.get("owner", ""):
        raise PermissionError("Only the owner may change the password")

    meta['join_password'] = new_password
    _write_json(os.path.join(path, 'game.json'), meta)
    await atlantis.client_log(f"Password to game {game_key} was changed")


@public
async def game_join() -> Dict[str, Any]:
    from .modal import modal_string

    entered_game_key = await modal_string(
        "Enter game key:",
        submit_label="Next",
        title="Join game",
        submitting_label="Checking...",
        empty_error="Enter the game key to continue.",
        autocomplete="off",
    )
    if entered_game_key is None:
        return {"cancelled": True}
    game_key = str(entered_game_key or "").strip()
    if not game_key:
        raise ValueError("game_key required")

    data_dir = require_game_dir(game_key)
    meta = _read_json(os.path.join(data_dir, 'game.json')) or {}
    if atlantis.get_caller() == meta.get("owner", ""):
        return await _game_join_authorized(game_key, data_dir, meta)

    password = await modal_string(
        f"Enter game password:",
        submit_label="Join",
        title=f"Game {game_key}",
        submitting_label="Joining...",
        empty_error="Enter the password to continue.",
        input_type="password",
        autocomplete="current-password",
    )
    if password is None:
        return {"cancelled": True}

    if meta.get('join_password') != password:
        raise ValueError(f"Incorrect password for game {game_key}")

    return await _game_join_authorized(game_key, data_dir, meta)


async def _game_join_authorized(game_key: str, data_dir: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    members = meta.setdefault('members', {})
    session_key = atlantis.get_session_key()
    if not session_key:
        raise RuntimeError("No session key in this call context")
    already_member = session_key in members
    if not already_member:
        add_caller_membership(members)
    _write_json(os.path.join(data_dir, 'game.json'), meta)
    if already_member:
        await atlantis.client_log(f"user already in game: {game_key}")
        return {"game_key": game_key}

    await atlantis.client_log(
        f"✅ {atlantis.get_caller() or atlantis.get_session_key()} joined game {game_key}"
    )
    await atlantis.client_command("/cursor join", {"game_key": game_key})
    await game_init(game_key)
    return {"game_key": game_key}
