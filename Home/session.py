"""Session identity tools — what atlantis hands us for this call."""

import atlantis


@visible
async def session_show() -> str:
    """Print the atlantis session key for this call (user_game_id:caller)."""
    key = atlantis.get_session_key()
    if not key:
        raise RuntimeError("No session key in this call context")
    return key
