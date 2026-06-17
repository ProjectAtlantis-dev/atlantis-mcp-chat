"""Game state tools"""

import atlantis
import base64
import humanize
import json
import mimetypes
import os
import re
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from urllib.parse import urlencode

from .bot import bot_entry_location
from .common import home_path, _read_json, _write_json
from .term import term_background_video, term_background_video_file, term_player


# ---------------------------------------------------------------------------
# Game record CRUD + membership
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


def _game_json_path(game_key: str) -> str:
    return os.path.join(require_game_dir(game_key), "game.json")


def _game_json_path_in_dir(data_dir: str) -> str:
    return os.path.join(data_dir, "game.json")


def _game_read(game_key: str) -> Dict[str, Any]:
    return _read_json(_game_json_path(game_key)) or {}


def _game_read_from_dir(data_dir: str) -> Dict[str, Any]:
    return _read_json(_game_json_path_in_dir(data_dir)) or {}


def _game_create(game_key: str, meta: Dict[str, Any]) -> None:
    data_dir = game_dir(game_key)
    os.makedirs(data_dir, exist_ok=False)
    _write_json(_game_json_path_in_dir(data_dir), meta)


def _game_update(game_key: str, meta: Dict[str, Any]) -> None:
    _write_json(_game_json_path(game_key), meta)


def _game_summary(game_key: str, meta: Dict[str, Any], created_ts: float) -> Dict[str, Any]:
    return {
        "game_key": game_key,
        "user_game_id": meta.get("user_game_id"),
        "owner": meta.get("owner"),
        "roster_scene": _game_roster_scene(meta),
        "user_cnt": len(_participant_sids(meta)),
        "created": datetime.fromtimestamp(created_ts).isoformat(timespec="seconds"),
        "_ts": created_ts,
    }


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
    sids: set[str] = set()
    if isinstance(members, dict):
        for rec in members.values():
            if not isinstance(rec, dict):
                continue
            sid = str(rec.get("sid") or "").strip()
            if sid:
                sids.add(sid)
    return sorted(sids)


def _caller_session_keys(meta: Dict[str, Any], session_key: str) -> list:
    caller_sid = atlantis.get_caller()
    members = meta.get("members") or {}
    session_keys = {session_key}
    if caller_sid and isinstance(members, dict):
        for member_session_key, rec in members.items():
            if not isinstance(rec, dict):
                continue
            if rec.get("sid") == caller_sid:
                session_keys.add(member_session_key)
    return sorted(session_keys)


def _caller_is_member(meta: Dict[str, Any], session_key: str) -> bool:
    members = meta.get("members") or {}
    if not isinstance(members, dict):
        return False
    if session_key in members:
        return True

    caller_sid = atlantis.get_caller()
    if not caller_sid:
        return False
    return any(
        isinstance(rec, dict) and rec.get("sid") == caller_sid
        for rec in members.values()
    )


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
    meta = _game_read_from_dir(path)
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
        meta = _game_read_from_dir(path)
        if meta.get("owner") != owner:
            continue
        matches.append((os.path.getctime(path), game_key))

    if not matches:
        return None
    matches.sort(reverse=True)
    return matches[0][1]


@public
async def game_find_current() -> str:
    """Return the existing game for the current Atlantis game window/session."""
    user_game_id = atlantis.get_user_game_id()
    if user_game_id is None:
        raise RuntimeError("No user_game_id in this call context")

    session_key = atlantis.get_session_key()
    if not session_key:
        raise RuntimeError("No session key in this call context")

    matches = []
    for game in _game_rows():
        if str(game.get("user_game_id")) != str(user_game_id):
            continue

        game_key = str(game.get("game_key") or "").strip()
        if not game_key:
            continue

        meta = _game_read(game_key)
        members = meta.get("members") or {}
        if isinstance(members, dict) and session_key in members:
            matches.append(game_key)

    if not matches:
        raise RuntimeError(
            f"No existing game found for user_game_id={user_game_id!r} "
            f"session_key={session_key!r}"
        )
    if len(matches) > 1:
        raise RuntimeError(
            f"Multiple existing games found for user_game_id={user_game_id!r} "
            f"session_key={session_key!r}: {', '.join(matches)}"
        )
    return matches[0]


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
    from .modal import modal_menu

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

_GAME_DEFAULT_BACKGROUND_ALIGN = "75%"


def _game_default_background_path() -> str:
    return os.path.join(os.path.dirname(__file__), "builder.jpg")


def _image_data_url(image_path: str) -> str:
    mime_type, _ = mimetypes.guess_type(image_path)
    if not mime_type or not mime_type.startswith("image/"):
        mime_type = "image/jpeg"
    with open(image_path, "rb") as image:
        encoded = base64.b64encode(image.read()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


async def _restore_game_default_background_when_background_video_ends() -> None:
    background_url = _image_data_url(_game_default_background_path())
    await atlantis.client_terminal_script(f"""
(function(){{
  var backgroundUrl = {json.dumps(background_url)};
  var verticalAlign = {json.dumps(_GAME_DEFAULT_BACKGROUND_ALIGN)};

  function restoreDefaultBackground() {{
    var chatFeedback = document.getElementById('chatFeedback');
    if (!chatFeedback) return;

    var oldMedia = document.querySelectorAll(
      '#feedbackBgVideo, video[data-background-video="true"], iframe[data-background-player="true"]'
    );
    for (var i = 0; i < oldMedia.length; i++) {{
      try {{
        if (oldMedia[i].pause) oldMedia[i].pause();
        oldMedia[i].removeAttribute('src');
        if (oldMedia[i].load) oldMedia[i].load();
      }} catch (_err) {{}}
      oldMedia[i].remove();
    }}

    chatFeedback.style.background = 'black';
    chatFeedback.style.backgroundImage = 'url(' + JSON.stringify(backgroundUrl) + ')';
    chatFeedback.style.backgroundSize = 'cover';
    chatFeedback.style.backgroundPosition = 'center ' + verticalAlign;
    chatFeedback.style.backgroundRepeat = 'no-repeat';
  }}

  function attachBackgroundVideoRestoreHook() {{
    var backgroundVideos = document.querySelectorAll('video[data-background-video="true"]');
    var backgroundVideo = backgroundVideos.length ? backgroundVideos[backgroundVideos.length - 1] : null;
    if (!backgroundVideo) return false;
    if (backgroundVideo.dataset.gameDefaultRestoreAttached === 'true') return true;
    backgroundVideo.dataset.gameDefaultRestoreAttached = 'true';
    backgroundVideo.addEventListener('ended', function() {{
      setTimeout(restoreDefaultBackground, 0);
    }}, {{ once: true }});
    backgroundVideo.addEventListener('error', function() {{
      setTimeout(restoreDefaultBackground, 0);
    }}, {{ once: true }});
    return true;
  }}

  if (attachBackgroundVideoRestoreHook()) return;
  var attempts = 0;
  var timer = setInterval(function() {{
    attempts += 1;
    if (attachBackgroundVideoRestoreHook() || attempts >= 300) clearInterval(timer);
  }}, 100);
}})();
""")


@public
async def game_background_video(video_name: str) -> None:
    """Play the named game background video in the terminal."""
    """timestamp test"""
    await term_background_video(f"https://pub-59cb84bebe804fd1b3257bb6c283a2b3.r2.dev/{video_name}")
    await _restore_game_default_background_when_background_video_ends()


@public
async def game_player(url: str) -> None:
    """Show a game background player for the URL."""
    await term_player(url)


@public
async def game_background_video_file(video_path: str) -> None:
    """Play a local game background video file in the terminal."""
    if not os.path.isabs(video_path):
        video_path = os.path.join(os.path.dirname(__file__), video_path)
    await term_background_video_file(video_path)
    await _restore_game_default_background_when_background_video_ends()


@public
async def game_background_default() -> None:
    """Set the game default background image."""
    await atlantis.set_background(
        _game_default_background_path(),
        vertical_align=_GAME_DEFAULT_BACKGROUND_ALIGN,
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

    join_password = uuid.uuid4().hex
    _game_create(game_key, {
        'join_password': join_password,
        'owner': atlantis.get_caller() or None,
        'user_game_id': atlantis.get_user_game_id(),
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


def _game_rows() -> list:
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
        meta = _game_read_from_dir(path)
        entries.append(_game_summary(name, meta, ts))
    entries.sort(key=lambda e: e["_ts"], reverse=True)
    for e in entries:
        del e["_ts"]
    return entries


@public
async def game_list() -> list:
    """List existing games, newest first"""
    rows = _game_rows()
    await atlantis.client_data("Games", rows, column_formatter={
        "created": {"type": "when"},
    })
    return rows


@public
async def game_show(game_key: str) -> dict:
    """Show a game's status. The owner sees full detail (join password + members);
    everyone else sees only owner, member count, and created time."""
    path = require_game_dir(game_key)
    meta = _game_read(game_key)
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

    meta = _game_read(game_key)
    if atlantis.get_caller() != meta.get("owner", ""):
        raise PermissionError("Only the owner may change the password")

    meta['join_password'] = new_password
    _game_update(game_key, meta)
    await atlantis.client_log(f"Password to game {game_key} was changed")


@public
async def game_join(require_other_owner: bool = False) -> Dict[str, Any]:
    """Join existing game"""
    from .modal import modal_string

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
    from .modal import modal_string

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
    from .modal import modal_menu

    games = _game_rows()
    joinable_games = _game_candidates(games, "join")
    resumable_games = _game_candidates(games, "resume")
    choices = [{"id": "create", "text": "Create new game"}]
    if joinable_games:
        choices.append({"id": "join", "text": "Join game"})
    if resumable_games:
        choices.append({"id": "resume", "text": "Resume existing game"})

    choice = await modal_menu(
        choices,
        title="Game",
        heading="What do you want to do?",
        width_ratio=0.5,
    )
    if choice is None:
        raise RuntimeError("Game selection cancelled")

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

# % ls

# % "Hello"







# % game video notLove_mobile.mp4


# % term glass


# % ls atl*

# % atlantis "get_session_key"

# % atlantis "get_caller"

# % atlantis "get_user_game_id"

# % atlantis "get_caller_shell_path"

# % cat atlantis

# % cursor show

@public
async def game_init(game_key: str):
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
    open_slots = [row for row in roster if not row.get("session_key")]
    if bound_row is None and open_slots:
        bound_row = await atlantis.client_command(f"@roster_bind {open_slots[0]['key']}")
    if bound_row and not bound_row.get("cancelled") and not bound_row.get("location"):
        location = bot_entry_location(bound_row["bot_sid"])
        await atlantis.client_command(f"@roster_spawn {bound_row['key']} {location}")
    if bound_row and not bound_row.get("cancelled"):
        from .camera import _camera_follow_slot

        meta = _game_read_from_dir(data_dir)
        await _camera_follow_slot(
            game_key,
            bound_row["key"],
            replace_session_keys=_caller_session_keys(meta, session_key),
        )
