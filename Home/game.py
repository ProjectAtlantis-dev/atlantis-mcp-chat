"""Game state tools"""

import atlantis
import base64
import json
import mimetypes
import os
import re
from datetime import datetime
from typing import Dict, Any, Optional

from .common import home_path, _read_json, _write_json
from .term import term_background_video, term_background_video_file, term_player


GAME_STATE_RUNNING = "running"
GAME_STATE_STOPPED = "stopped"
GAME_STATES = {GAME_STATE_RUNNING, GAME_STATE_STOPPED}


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


def _normalize_game_state(state: Any) -> str:
    state_key = str(state or "").strip().lower() or GAME_STATE_STOPPED
    if state_key not in GAME_STATES:
        raise ValueError(f"game state must be one of: {', '.join(sorted(GAME_STATES))}")
    return state_key


def _game_state(meta: Dict[str, Any]) -> str:
    return _normalize_game_state(meta.get("state") or GAME_STATE_STOPPED)


def _game_is_running(game_key: str) -> bool:
    return _game_state(_game_read(game_key)) == GAME_STATE_RUNNING


def _game_summary(game_key: str, meta: Dict[str, Any], created_ts: float) -> Dict[str, Any]:
    return {
        "game_key": game_key,
        "user_game_id": meta.get("user_game_id"),
        "owner": meta.get("owner"),
        "state": _game_state(meta),
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


@visible
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
            "state": _game_state(meta),
            "roster_scene": roster,
            "members": _participant_sids(meta),
            "created": created,
        }

    return {
        "game_key": game_key,
        "user_game_id": meta.get("user_game_id"),
        "owner": owner,
        "state": _game_state(meta),
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


async def _game_set_state(game_key: str, state: str) -> dict:
    meta = _game_read(game_key)
    if atlantis.get_caller() != meta.get("owner", ""):
        raise PermissionError("Only the owner may change the game state")

    state_key = _normalize_game_state(state)
    meta["state"] = state_key
    _game_update(game_key, meta)
    await atlantis.client_log(f"Game {game_key} is now {state_key}")
    return {"game_key": game_key, "state": state_key}


@public
async def game_start(game_key: str) -> dict:
    """Set a game state to running."""
    return await _game_set_state(game_key, GAME_STATE_RUNNING)


@public
async def game_stop(game_key: str) -> dict:
    """Set a game state to stopped."""
    return await _game_set_state(game_key, GAME_STATE_STOPPED)


# % game_find_or_create

# % _game_rows()

# % game show

# % game overview


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
