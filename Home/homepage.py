"""Homepage for the Home remote."""


@homepage
async def homepage() -> dict:
    """Return an empty homepage and startup commands."""

    return {
        "html": "<div></div>",
        "commands": [
            "/terminal on",
            "/app on",
            "/callback set chat auto"
        ],
    }
