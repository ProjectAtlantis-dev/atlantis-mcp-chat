"""Static regression checks for modal menu geometry.

The Atlantis modal UI is generated as HTML/CSS/JS inside Home/modal.py, so these
checks intentionally inspect source text instead of importing the module.
"""

from pathlib import Path
import re
import unittest


MODAL_SOURCE = Path(__file__).resolve().parents[1] / "Home" / "modal.py"


def _modal_source() -> str:
    return MODAL_SOURCE.read_text(encoding="utf-8")


def _menu_panel_css_rule(source: str) -> str:
    match = re.search(
        r"\.jsPanel:has\(#modalmenu-\{uid\}\) \{\{(?P<body>.*?)\n  \}\}",
        source,
        re.DOTALL,
    )
    if not match:
        raise AssertionError("modal menu jsPanel CSS rule not found")
    return match.group("body")


class ModalLayoutContractTest(unittest.TestCase):
    def test_menu_panel_css_only_controls_horizontal_geometry(self) -> None:
        rule = _menu_panel_css_rule(_modal_source())

        self.assertIn("width:", rule)
        self.assertIn("width: auto !important", rule)
        self.assertIn("min-width: 0 !important", rule)
        self.assertIn("left:", rule)
        self.assertIn("transform: translateX(-50%)", rule)
        self.assertNotIn("--modal-menu-width", rule)
        self.assertNotIn("100vw *", rule)
        self.assertNotIn("top:", rule)
        self.assertNotIn("height:", rule)
        self.assertNotIn("overflow:", rule)

    def test_menu_vertical_geometry_stays_measured_in_script(self) -> None:
        source = _modal_source()

        self.assertIn("var adjustedRect = host.getBoundingClientRect();", source)
        self.assertIn("var viewportMargin = 16;", source)
        self.assertIn('host.style.transform = "translateX(-50%)";', source)

    def test_modal_host_selection_does_not_grab_broad_jspanel_wrapper(self) -> None:
        source = _modal_source()

        self.assertNotIn('closest(".jsPanel")', source)
        self.assertNotIn("closest('.jsPanel')", source)

    def test_menu_width_is_driven_by_choice_text_measurements(self) -> None:
        source = _modal_source().split("async def modal_menu(", 1)[1]

        self.assertIn("var needed = 0;", source)
        self.assertIn(": textWidth(button) + horizontalBox(buttonStyle);", source)
        self.assertIn('host.style.minWidth = "0";', source)
        self.assertIn("var finalWidth = Math.min(targetWidth, viewportMax);", source)
        self.assertNotIn("var needed = 320;", source)
        self.assertNotIn("Math.max(320, targetWidth)", source)
        self.assertNotIn("originalWidth *", source)

    def test_menu_supports_disabled_choices(self) -> None:
        source = _modal_source().split("async def modal_menu(", 1)[1]

        self.assertIn("disabled_attr =", source)
        self.assertIn("aria-disabled=", source)
        self.assertIn("var enabledButtons = buttons.filter", source)
        self.assertIn("if (button.disabled) return;", source)


if __name__ == "__main__":
    unittest.main()
