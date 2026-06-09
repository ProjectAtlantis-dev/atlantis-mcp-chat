"""Homepage for the Home remote."""

import atlantis


@homepage
async def homepage() -> dict:
    """Return an empty homepage and startup commands."""

    app_path = atlantis.get_script_folder()
    app_commands = [
        f"/cd {app_path}",
        f"/path unshift {app_path}",
    ] if app_path else []

    return {
        "html": "<div></div>",
        "commands": [
            *app_commands,
            "/terminal on",
            "/app on",
            "/callback set chat auto"
        ],
    }
