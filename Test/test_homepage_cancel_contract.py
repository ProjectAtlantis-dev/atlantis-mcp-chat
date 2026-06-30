"""Static regression checks for homepage menu cancellation handling."""

from pathlib import Path
import unittest


HOMEPAGE_SOURCE = Path(__file__).resolve().parents[1] / "Home" / "homepage.py"


def _homepage_source() -> str:
    return HOMEPAGE_SOURCE.read_text(encoding="utf-8")


class HomepageCancelContractTest(unittest.TestCase):
    def test_first_menu_acknowledges_top_level_cancel(self) -> None:
        source = _homepage_source().split("async def first_menu(", 1)[1].split(
            "\n\n\n@public\n@homepage", 1
        )[0]

        self.assertIn("if choice is None:", source)
        self.assertIn('await atlantis.client_log("Home menu cancelled.")', source)

    def test_first_menu_acknowledges_nested_game_cancel(self) -> None:
        source = _homepage_source().split("async def first_menu(", 1)[1].split(
            "\n\n\n@public\n@homepage", 1
        )[0]

        self.assertIn("except RuntimeError as exc:", source)
        self.assertIn('"cancelled" not in str(exc).lower()', source)
        self.assertIn("await atlantis.client_log(str(exc))", source)


if __name__ == "__main__":
    unittest.main()
