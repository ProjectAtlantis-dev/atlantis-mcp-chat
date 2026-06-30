"""Static regression checks for standalone picker entrypoints."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return ROOT.joinpath(path).read_text(encoding="utf-8")


class PickerContractTest(unittest.TestCase):
    def test_scene_pick_visible_entrypoint_takes_no_params(self) -> None:
        source = _source("Home/scene.py")
        function_source = source.split("async def scene_pick(", 1)[1].split("\n\n\n@public", 1)[0]

        self.assertTrue(function_source.startswith(") -> Optional[str]:"))
        self.assertIn("return await _scene_pick_dialog()", function_source)
        self.assertNotIn("heading:", function_source)

    def test_scene_picker_uses_modal_menu(self) -> None:
        source = _source("Home/scene.py")
        picker_source = source.split("async def _scene_pick_dialog(", 1)[1].split(
            "\n\n@public\nasync def scene_list", 1
        )[0]

        self.assertIn("modal_menu(", picker_source)
        self.assertIn('title: str = "Scene"', picker_source)
        self.assertIn('heading: str = "Select scene"', picker_source)
        self.assertIn('"column_headers": ["Scene", "Slots"]', source)

    def test_game_init_uses_scene_picker_helper(self) -> None:
        source = _source("Home/runner.py")

        self.assertIn("from .scene import _scene_pick_dialog", source)
        self.assertIn("scene = await _scene_pick_dialog()", source)
        self.assertNotIn("async def _game_pick_scene(", source)

    def test_game_pick_visible_entrypoint_takes_no_params(self) -> None:
        source = _source("Home/game.py")
        function_source = source.split("async def game_pick(", 1)[1].split("\n\n\n@public", 1)[0]

        self.assertTrue(function_source.startswith(") -> Optional[str]:"))
        self.assertIn("return await _game_pick_dialog()", function_source)
        self.assertNotIn("heading:", function_source)
        self.assertNotIn("games:", function_source)

    def test_game_find_or_create_uses_game_picker_helper(self) -> None:
        source = _source("Home/runner.py")

        self.assertIn("from .game import (", source)
        self.assertIn("_game_pick_dialog,", source)
        self.assertIn("game_key = await _game_pick_dialog(", source)
        self.assertNotIn("async def _game_pick(", source)


if __name__ == "__main__":
    unittest.main()
