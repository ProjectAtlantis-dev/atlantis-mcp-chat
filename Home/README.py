import atlantis
from pathlib import Path


@text("md")
@visible
async def README():
    """Show atlantis-mcp-chat runtime notes."""

    await atlantis.client_log("README running")

    md_path = Path(__file__).parent.parent / "README.md"
    return md_path.read_text(encoding="utf-8")
