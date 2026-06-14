"""Homepage for the Home remote."""

import atlantis

@public
@homepage
async def homepage() -> dict:
    """Return startup commands."""

    # this folder
    script_folder = atlantis.get_script_folder()
    if not script_folder:
        raise RuntimeError("Cannot determine homepage script folder")

    return {
        "commands": [
            f"/cd {script_folder}",
            f"/path unshift {script_folder}",
            "/terminal on",
            "app on",
            "game find or create"
        ],
    }
