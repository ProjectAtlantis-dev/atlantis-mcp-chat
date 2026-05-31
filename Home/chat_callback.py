"""Game chat callback — main game tick. Fired on every transcript change."""

import atlantis
import logging

from dynamic_functions.Home.chat import (
    analyze_participants, fetch_transcript,
)
from dynamic_functions.Home.turn import bot_turn

logger = logging.getLogger("mcp_server")

_BUSY_KEY = "chat_busy"


@public
@chat
async def chat_callback(game_key: str):
    """Game tick: fired on every transcript change. The speaker is read from the transcript itself."""
    if not atlantis.get_session_key():
        logger.warning("chat_callback fired without session context, skipping")
        return

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
    raise NotImplementedError("_handle_chat: slot system removed — needs reimplementation")



async def greet_entrant(game_key: str, entrant_sid: str, location: str):
    """Fire an in-character greeting from a bot already at `location` toward a newcomer."""
    raise NotImplementedError("greet_entrant: slot system removed — needs reimplementation")


async def _respond_as_bot(*, game_key: str, bot_record: dict, transcript: list):
    raise NotImplementedError("_respond_as_bot: slot system removed — needs reimplementation")
