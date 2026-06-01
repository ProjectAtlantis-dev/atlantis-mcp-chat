"""Game chat callback — main game tick. Fired on every transcript change."""

import atlantis
import logging
import os
from typing import Any, Dict, List, Optional


from .chat import (
    analyze_participants, fetch_transcript,
)
from .common import _read_json
from .game import _game_roster_scene, require_game_dir
from .roster import _load_game_roster
from .turn import bot_turn

logger = logging.getLogger("mcp_server")

_BUSY_KEY = "chat_busy"
_LAST_CHAT_KEY_PREFIX = "chat_last_seen:"
_CHAT_LOOP_COUNT_PREFIX = "chat_loop_count:"
_MAX_BOT_CHAIN = 4


def _require_roster_assigned(game_key: str) -> None:
    """Fail early if chat starts before this game has a created roster."""
    data_dir = require_game_dir(game_key)
    meta = _read_json(os.path.join(data_dir, "game.json")) or {}
    if not _game_roster_scene(meta):
        raise RuntimeError(f"Game {game_key!r} has no roster assigned yet")
    if not os.path.isfile(os.path.join(data_dir, "roster.json")):
        raise RuntimeError(f"Game {game_key!r} has no roster.json yet")


@public
@chat
async def chat_callback(game_key: str):
    """Game tick: fired on every transcript change. The speaker is read from the transcript itself."""
    if not atlantis.get_session_key():
        logger.warning("chat_callback fired without session context, skipping")
        return
    _require_roster_assigned(game_key)

    request_id = atlantis.get_request_id() or "unknown"
    if atlantis.session_shared.get(_BUSY_KEY):
        logger.debug(f"chat_callback busy, skipping {request_id}")
        return

    atlantis.session_shared.set(_BUSY_KEY, request_id)
    try:
        await _handle_chat(game_key)
    finally:
        atlantis.session_shared.remove(_BUSY_KEY)


async def _handle_chat(game_key: str):
    raw_transcript, transcript = await fetch_transcript(game_key)
    participants = analyze_participants(raw_transcript)
    speaker_sid = participants.get("last_speaker")
    if not speaker_sid:
        await atlantis.client_log("No chat speaker found in transcript")
        return

    signature = _last_chat_signature(raw_transcript)
    if signature:
        last_key = f"{_LAST_CHAT_KEY_PREFIX}{game_key}"
        if atlantis.session_shared.get(last_key) == signature:
            logger.debug("chat_callback duplicate transcript trigger, skipping")
            return
        atlantis.session_shared.set(last_key, signature)

    roster = _load_game_roster(game_key)
    speaker = _find_roster_speaker(roster, speaker_sid)
    if not speaker:
        raise RuntimeError(f"Chat speaker {speaker_sid!r} is not in this game's roster")

    location = str(speaker.get("location", "") or "").strip()
    if not location:
        raise RuntimeError(f"Chat speaker {speaker_sid!r} has not spawned into a location yet")

    occupants = _location_occupants(roster, location)
    if not occupants:
        await atlantis.client_log(f"Room [{location}] is empty")
        return
    await atlantis.client_log(
        f"Room [{location}]: {', '.join(_display_name(row) for row in occupants)}"
    )
    if len(occupants) == 1:
        await atlantis.client_log(f"{_display_name(speaker)} is alone in {location}")
        return

    loop_count = _next_loop_count(game_key, speaker)
    if loop_count > _MAX_BOT_CHAIN:
        logger.debug("chat_callback bot chain limit reached, skipping")
        return

    # Convo rule: among the speaker's current room occupants, pick the first AI
    # roster member that did not just speak.
    bots = [
        row for row in occupants
        if _is_ai(row) and row.get("bot_sid") and row.get("key") != speaker.get("key")
    ]
    if not bots:
        await atlantis.client_log(f"No AI roster member in {location} available to respond")
        return

    bot_record = bots[0]
    await atlantis.client_log(
        f"Next roster speaker: {bot_record.get('displayName', bot_record.get('bot_sid', 'bot'))}"
    )
    await _respond_as_bot(game_key=game_key, bot_record=bot_record, transcript=transcript, roster=roster)


def _next_loop_count(game_key: str, speaker: Optional[Dict[str, Any]]) -> int:
    key = f"{_CHAT_LOOP_COUNT_PREFIX}{game_key}"
    if not speaker or not _is_ai(speaker):
        atlantis.session_shared.set(key, 0)
        return 0
    count = int(atlantis.session_shared.get(key) or 0) + 1
    atlantis.session_shared.set(key, count)
    return count


def _last_chat_signature(raw_transcript: List[Dict[str, Any]]) -> str:
    for msg in reversed(raw_transcript):
        if msg.get("type") != "chat":
            continue
        sid = str(msg.get("sid") or "")
        if not sid or sid == "system":
            continue
        if "thinking" in str(msg.get("who") or "").lower():
            continue
        content = str(msg.get("content") or "")
        if not content.strip():
            continue
        timestamp = str(msg.get("created_at") or msg.get("created_at_str") or "")
        return "|".join([sid, timestamp, content[:200]])
    return ""


def _is_ai(row: Dict[str, Any]) -> bool:
    return row.get("ai") is not False


def _display_name(row: Dict[str, Any]) -> str:
    return str(row.get("displayName") or row.get("bot_sid") or row.get("sid") or row.get("key") or "unknown")


def _location_occupants(roster: List[Dict[str, Any]], location: str) -> List[Dict[str, Any]]:
    return [
        row for row in roster
        if str(row.get("location", "") or "").strip() == location
    ]


def _find_roster_speaker(roster: List[Dict[str, Any]], speaker_sid: str) -> Optional[Dict[str, Any]]:
    for row in roster:
        if not _is_ai(row) and row.get("sid") == speaker_sid:
            return row
    for row in roster:
        if _is_ai(row) and row.get("bot_sid") == speaker_sid:
            return row
    return None



async def greet_entrant(game_key: str, entrant_sid: str, location: str):
    """Fire an in-character greeting from a bot already at `location` toward a newcomer."""
    raise NotImplementedError("greet_entrant: slot system removed — needs reimplementation")


async def _respond_as_bot(*, game_key: str, bot_record: dict, transcript: list, roster: list):
    bot_sid = str(bot_record.get("bot_sid") or "").strip()
    if not bot_sid:
        raise ValueError(f"Roster row {bot_record.get('key')!r} has no bot_sid")

    roster_names = {
        str(row.get("bot_sid")): str(row.get("displayName"))
        for row in roster
        if row.get("bot_sid") and row.get("displayName")
    }
    await atlantis.client_log(
        "respond_as_bot start: "
        f"game={game_key!r} slot={bot_record.get('key')!r} "
        f"bot_sid={bot_sid!r} display={bot_record.get('displayName')!r} "
        f"transcript={len(transcript)}"
    )
    logger.info(
        "Dispatching bot turn: game=%s slot=%s bot_sid=%s display=%s transcript=%s roster_names=%s",
        game_key,
        bot_record.get("key"),
        bot_sid,
        bot_record.get("displayName"),
        len(transcript),
        roster_names,
    )
    try:
        result = await bot_turn(
            bot_sid=bot_sid,
            transcript=transcript,
            roster_names=roster_names,
        )
    except Exception as e:
        logger.exception("respond_as_bot failed")
        await atlantis.client_log(f"respond_as_bot failed: {type(e).__name__}: {e}")
        raise

    await atlantis.client_log(
        f"respond_as_bot done: bot_sid={bot_sid!r} chars={len(result or '')}"
    )
    return result
