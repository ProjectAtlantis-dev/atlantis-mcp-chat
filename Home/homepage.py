"""Homepage for the Home remote."""

from typing import Optional

import atlantis


@public
async def home_menu() -> Optional[str]:
    """Let the user choose where to go next."""
    from .modal import modal_menu

    choice = await modal_menu(
        [
            {"id": "explore_demo_folder", "text": "Explore demo folder"},
            {"id": "bots", "text": "To the bots"},
        ],
        title="Home",
        heading="Where do you want to go?",
        width_ratio=0.5,
    )
    if choice is None:
        return None

    choice_id = str(choice["id"])
    if choice_id == "explore_demo_folder":
        commands = [
            "cd ../..",
            "cd Demo"
        ]
        await atlantis.client_command("/script", {"commands":commands})
    return choice_id


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
            "term default",
            "game default background",
            "home menu"
        ],
    }
