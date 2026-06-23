"""Homepage for the Home remote."""

from pathlib import Path
from typing import Optional

import atlantis


@public
async def first_menu():
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

    script_folder = atlantis.get_script_folder()

    choice_id = str(choice["id"])
    if choice_id == "explore_demo_folder":
        commands = [
            f"/cd {script_folder}",
            "cd ../..",
            "cd Demo"
        ]
        await atlantis.client_command("/script", {"commands":commands})

        img_path = Path(__file__).absolute().parents[4] / "sitting_coffee.png"
        await atlantis.client_image(
            str(img_path),
            content="Demo folder coming right up, but if you want to do anything cool you need to mount a filesystem...",
            max_width="25vw",
        )

        await atlantis.client_command("/script", {"commands":["ls"]})



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
            "term_default",
            "game_background_default",
            "first_menu"
        ],
    }
