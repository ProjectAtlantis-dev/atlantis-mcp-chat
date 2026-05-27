import atlantis
import logging
from pathlib import Path

logger = logging.getLogger("mcp_server")

# % whoami


@text("md")
@visible
async def README():
    """Show MULTIX instructions"""

    await atlantis.client_log("README running")

    md_path = Path(__file__).parent / "MULTIX.md"
    return md_path.read_text()


@text("md")
@visible
async def README_GAME():
    """Explain where the live game data model is shown."""

    await atlantis.client_log("README_GAME running")

    return """# Game Data Model

`GAME.md` was removed because it drifted from the implementation.

Use `game_overview(game_key)` as the source of truth. It renders the live model
the engine actually uses: game, bots, roles, locations, slots, and cameras.

The `SLOTS` table is the important runtime join: one row per role, joined with
that game's slot state. Its `assignment` is what the engine branches on:
`empty`, `ai`, or `human`. A user's session must be bound to a slot before they
can chat as that role.

The `CAMERA` table is separate. A user's terminal is bound to a camera location
so that shell can see what is happening there. The same session can have
multiple terminals watching different places without changing which slot the
user is playing.
"""
