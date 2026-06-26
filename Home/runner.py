"""Game flow orchestration — the @public join/create/resume entry points and
their UI pickers. This layer sits above the game-record foundation (.game) and
the camera/roster views, so it may import all of them without a cycle."""

import atlantis
import humanize
import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from urllib.parse import urlencode

from .bot import bot_entry_location
from .camera import _camera_follow_slot
from .modal import modal_menu, modal_string
from .game import (
    GAME_STATE_STOPPED,
    _caller_is_member,
    _caller_session_keys,
    _game_create,
    _game_read,
    _game_read_from_dir,
    _game_rows,
    _game_update,
    add_caller_membership,
    game_background_default,
    game_dir,
    require_membership,
)


def _roster_slot_state(row: Dict[str, Any]) -> str:
    if row.get("ai") is True:
        return "AI"
    if row.get("ai") is False or row.get("session_key") or row.get("sid"):
        return "Human"
    return "Empty"


def _roster_slot_name(row: Dict[str, Any]) -> str:
    state = _roster_slot_state(row)
    if state == "Empty":
        return "-"
    return str(row.get("displayName") or row.get("sid") or row.get("bot_sid") or "-")


def _caller_roster_row(roster: list, session_key: str, caller_sid: Optional[str]) -> Optional[Dict[str, Any]]:
    row = next((row for row in roster if row.get("session_key") == session_key), None)
    if row is not None:
        return row
    if caller_sid:
        return next(
            (
                row for row in roster
                if row.get("ai") is False and row.get("sid") == caller_sid
            ),
            None,
        )
    return None


async def _game_resume(game_key: str) -> str:
    meta = _game_read(game_key)
    members = meta.setdefault("members", {})
    session_key = atlantis.get_session_key()
    if not session_key:
        raise RuntimeError("No session key in this call context")
    if not _caller_is_member(meta, session_key):
        raise PermissionError(f"Session is not a member of game '{game_key}'")
    if session_key not in members:
        add_caller_membership(members)
        _game_update(game_key, meta)
    await atlantis.client_log(f"Existing game found: {game_key}")
    await atlantis.client_command("/cursor join", {"game_key": game_key})
    await game_init(game_key)
    return game_key


async def _game_redirect_if_user_game_mismatch(game_key: str) -> bool:
    meta = _game_read(game_key)
    target_user_game_id = meta.get("user_game_id")
    if target_user_game_id is None:
        return False

    current_user_game_id = atlantis.get_user_game_id()
    if str(target_user_game_id) == str(current_user_game_id):
        return False

    sid = str(meta.get("owner") or atlantis.get_caller() or "").strip()
    query = {"game": str(target_user_game_id)}
    if sid:
        query["sid"] = sid
    url = f"chat.html?{urlencode(query)}"
    await atlantis.client_log(f"Redirecting to game window: {url}")
    await atlantis.client_script(f"window.location.assign({url!r});")
    return True


def _format_game_menu_age(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "Unknown"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return raw
    return humanize.naturaltime(datetime.now() - parsed)


async def _game_pick(
    games: Optional[list] = None,
    heading: str = "Choose a game",
) -> Optional[str]:
    if games is None:
        games = _game_rows()
    games = sorted(games, key=lambda game: str(game.get("created") or ""), reverse=True)
    if not games:
        raise RuntimeError("No existing games found")

    choices = []
    for game in games:
        game_key = str(game.get("game_key", "")).strip()
        if not game_key:
            continue
        user_cnt = game.get("user_cnt")
        choices.append({
            "id": game_key,
            "text": game_key[:4],
            "columns": [
                game_key[:4],
                _format_game_menu_age(game.get("created")),
                str(game.get("owner") or "Unknown owner"),
                str(game.get("roster_scene") or "No scene"),
                str(user_cnt) if isinstance(user_cnt, int) else "-",
            ],
            "column_headers": ["Key", "Started", "Owner", "Scene", "Players"],
            "game_key": game_key,
        })

    if not choices:
        raise RuntimeError("No existing games found")

    choice = await modal_menu(
        choices,
        title="Game",
        heading=heading,
    )
    if choice is None:
        return None
    game_key = str(choice.get("game_key") or choice.get("id") or "").strip()
    if not game_key:
        return None
    if await _game_redirect_if_user_game_mismatch(game_key):
        return None
    return game_key


async def _game_pick_scene(heading: str = "Choose a scene") -> Optional[str]:
    await atlantis.client_log("Getting scenes")
    scenes = await atlantis.client_command("@scene_list")
    if not scenes:
        raise RuntimeError("No scenes found")

    choices = []
    for scene in scenes:
        scene_name = str(scene or "").strip()
        if not scene_name:
            continue
        choices.append({
            "id": scene_name,
            "text": scene_name,
            "scene": scene_name,
        })

    if not choices:
        raise RuntimeError("No scenes found")

    choice = await modal_menu(
        choices,
        title="Scene",
        heading=heading,
        width_ratio=0.5,
    )
    if choice is None:
        return None

    scene = str(choice.get("scene") or choice.get("id") or "").strip()
    return scene or None

@visible
async def roster_edit(
    heading: str = "Roster",
) -> Optional[Dict[str, Any]]:
    while True:
        roster = await atlantis.client_command("@roster_list")
        slot_choices = []
        for row in roster:
            slot_key = str(row.get("key") or "").strip()
            if not slot_key:
                continue
            state = _roster_slot_state(row)
            slot_choices.append({
                "id": slot_key,
                "text": slot_key,
                "columns": [
                    slot_key,
                    str(row.get("bot_sid") or ""),
                    state,
                    _roster_slot_name(row),
                ],
                "column_headers": ["Slot", "Default", "State", "Name"],
                "slot_key": slot_key,
            })

        if not slot_choices:
            raise RuntimeError("No roster slots found")

        slot_choices.append({
            "id": "__ok__",
            "text": "OK",
            "columns": ["OK", "", "", ""],
            "column_headers": ["Slot", "Default", "State", "Name"],
        })

        slot_choice = await modal_menu(
            slot_choices,
            title="Roster",
            heading=heading,
            width_ratio=0.67,
        )
        if slot_choice is None:
            return None
        if slot_choice.get("id") == "__ok__":
            roster = await atlantis.client_command("@roster_list")
            return _caller_roster_row(roster, atlantis.get_session_key() or "", atlantis.get_caller())

        slot_key = str(slot_choice.get("slot_key") or slot_choice.get("id") or "").strip()
        if not slot_key:
            return None

        state_choice = await modal_menu(
            [
                {"id": "empty", "text": "Empty"},
                {"id": "ai", "text": "AI"},
                {"id": "human", "text": "Human"},
            ],
            title="Roster",
            heading=f"{slot_key}: choose state",
            width_ratio=0.42,
        )
        if state_choice is None:
            continue

        state = str(state_choice.get("id") or "").strip().lower()
        display_name = None
        if state == "human":
            display_name = await modal_string(
                f"What name should people call {slot_key}?",
                title="Roster - Human",
                submit_label="Join",
            )
            if display_name is None:
                continue
            display_name = str(display_name or "").strip()
            if not display_name:
                raise ValueError("display_name required")

        await atlantis.client_command(
            "@roster_set_slot",
            {
                "slot_key": slot_key,
                "state": state,
                "display_name": display_name,
            },
        )


@public
async def game_new() -> Dict[str, Any]:
    """Main entry point for creating a new game"""
    for _ in range(10):
        game_key = uuid.uuid4().hex
        data_dir = game_dir(game_key)
        if not os.path.exists(data_dir):
            break
    else:
        raise RuntimeError("Unable to allocate a unique game_key")

    await atlantis.client_log("Creating new game")

    join_password = uuid.uuid4().hex
    _game_create(game_key, {
        'join_password': join_password,
        'owner': atlantis.get_caller() or None,
        'user_game_id': atlantis.get_user_game_id(),
        'state': GAME_STATE_STOPPED,
        'roster_scene': None,
        'roster_created_at': None,
        'members': add_caller_membership({}),
    })

    await atlantis.client_log(f"Game created: {game_key}")
    await game_background_default()

    return {
        "game_key": game_key,
        "join_password": join_password,
    }


async def _game_create_and_enter(log_init: bool = False) -> Dict[str, Any]:
    keys = await game_new()
    await atlantis.client_command("/cursor join", keys)
    if log_init:
        await atlantis.client_log(f"game_init game_key: {keys['game_key']!r}")
    await game_init(keys["game_key"])
    return keys


@public
async def game_join(require_other_owner: bool = False) -> Dict[str, Any]:
    """Join existing game"""
    entered_game_key = await modal_string(
        "Enter game key:",
        submit_label="Next",
        title="Game",
        submitting_label="Checking...",
        empty_error="Enter the game key to continue.",
        autocomplete="off",
    )
    if entered_game_key is None:
        return {"cancelled": True}
    game_key = str(entered_game_key or "").strip()
    if not game_key:
        raise ValueError("game_key required")

    meta = _game_read(game_key)
    if require_other_owner and atlantis.get_caller() == meta.get("owner", ""):
        raise PermissionError("Join game requires a game owned by someone else")
    return await _game_join_or_prompt(game_key, meta)


async def _game_join_or_prompt(game_key: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    session_key = atlantis.get_session_key()
    if not session_key:
        raise RuntimeError("No session key in this call context")
    if _caller_is_member(meta, session_key) or atlantis.get_caller() == meta.get("owner", ""):
        return await _game_join_authorized(game_key, meta)

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

    return await _game_join_authorized(game_key, meta)


def _game_candidates(games: list, action: str) -> list:
    if action not in {"join", "resume"}:
        raise ValueError(f"Unknown game candidate action: {action!r}")

    session_key = atlantis.get_session_key()
    if not session_key:
        raise RuntimeError("No session key in this call context")
    caller = atlantis.get_caller()
    candidates = []
    for game in games:
        game_key = str(game.get("game_key") or "").strip()
        if not game_key:
            continue
        meta = _game_read(game_key)
        is_member = _caller_is_member(meta, session_key)
        is_owner = bool(caller and meta.get("owner") == caller)
        if action == "join" and not is_member and not is_owner:
            candidates.append(game)
        elif action == "resume" and is_member:
            candidates.append(game)
    return candidates


async def _game_join_authorized(game_key: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    members = meta.setdefault('members', {})
    session_key = atlantis.get_session_key()
    if not session_key:
        raise RuntimeError("No session key in this call context")
    already_member = session_key in members
    if not already_member:
        add_caller_membership(members)
    _game_update(game_key, meta)
    if already_member:
        await atlantis.client_log(f"user already in game: {game_key}")
        return {"game_key": game_key}

    await atlantis.client_log(
        f"✅ {atlantis.get_caller() or atlantis.get_session_key()} joined game {game_key}"
    )
    await atlantis.client_command("/cursor join", {"game_key": game_key})
    await game_init(game_key)
    return {"game_key": game_key}


@public
async def game_find_or_create() -> str:
    """Ask whether to resume an existing game or create a new one."""
    games = _game_rows()
    joinable_games = _game_candidates(games, "join")
    resumable_games = _game_candidates(games, "resume")
    choices: list[Dict[str, Any]] = [{"id": "create", "text": "Create new game"}]
    if resumable_games:
        choices.append({"id": "resume", "text": "Resume existing game"})
    choices.append({
        "id": "join",
        "text": "Join game",
        "disabled": not joinable_games,
    })

    choice = await modal_menu(
        choices,
        title="Game Action",
        heading="What do you want to do?",
        width_ratio=0.5,
    )
    if choice is None:
        raise RuntimeError("Game selection cancelled")

    await atlantis.client_log(f"game_find_or_create selected: {choice.get('id')!r}")

    if choice.get("id") == "create":
        return (await _game_create_and_enter())["game_key"]

    if choice.get("id") == "join":
        game_key = await _game_pick(
            games=joinable_games,
            heading="Choose a game to join",
        )
        if not game_key:
            raise RuntimeError("Game selection cancelled")
        meta = _game_read(game_key)
        result = await _game_join_or_prompt(game_key, meta)
        if result.get("cancelled"):
            raise RuntimeError("Game selection cancelled")
        game_key = str(result.get("game_key") or "").strip()
        if not game_key:
            raise RuntimeError("Game join did not return a game_key")
        return game_key

    if choice.get("id") == "resume":
        game_key = await _game_pick(games=resumable_games, heading="Choose a game to resume")
        if not game_key:
            raise RuntimeError("Game selection cancelled")
        return await _game_resume(game_key)

    raise ValueError(f"Unknown game choice: {choice.get('id')!r}")


@public
async def game_init(game_key: str):

    await atlantis.client_log("*** GAME INIT ***")

    """Idempotent game setup"""

    # % atlantis "get_session_key"


    # make sure game exists
    data_dir = require_membership(game_key)
    session_key = atlantis.get_session_key()
    if not session_key:
        raise RuntimeError("No session key in this call context")
    roster_path = os.path.join(data_dir, "roster.json")

    # make sure chat callback is set
    callbacks = await atlantis.client_command("/callback list")
    chat_row = next(row for row in callbacks if row["mode"] == "chat")

    if not chat_row["toolPath"]:
        await atlantis.client_command("callback set chat auto")

        callbacks = await atlantis.client_command("/callback list")
        chat_row = next(row for row in callbacks if row["mode"] == "chat")



    await atlantis.client_log(f"chat callback: toolPath={chat_row['toolPath']!r} filename={chat_row['filename']!r}")

    if os.path.isfile(roster_path):
        roster = await atlantis.client_command("@roster_list")
    else:
        scene = await _game_pick_scene()
        if not scene:
            raise RuntimeError("Scene selection cancelled")
        roster = await atlantis.client_command(f"@roster_create {scene}")
        await atlantis.client_log(f"game scene: {scene!r}")

    bound_row = _caller_roster_row(roster, session_key, atlantis.get_caller())
    if bound_row is None:
        bound_row = await roster_edit()
    if bound_row and not bound_row.get("cancelled") and not bound_row.get("location"):
        location = bot_entry_location(bound_row["bot_sid"])
        await atlantis.client_command(f"@roster_spawn {bound_row['key']} {location}")
    if bound_row and not bound_row.get("cancelled"):

        meta = _game_read_from_dir(data_dir)
        await _camera_follow_slot(
            game_key,
            bound_row["key"],
            replace_session_keys=_caller_session_keys(meta, session_key),
        )
