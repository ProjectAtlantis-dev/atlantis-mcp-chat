"""Homepage for the Home remote."""

import atlantis


@homepage
async def homepage() -> dict:
    """Return an empty homepage and startup commands."""

    script_folder = atlantis.get_script_folder()
    if not script_folder:
        raise RuntimeError("Cannot determine homepage script folder")

    return {
        "html": "<div></div>",
        "commands": [
            f"/cd {script_folder}",
            f"/path unshift {script_folder}",
            "/terminal on",
            "/app on",
            "/callback set chat auto"
        ],
    }
