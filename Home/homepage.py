"""Dashboard homepage card for the Home remote."""

import json
import uuid
from html import escape
from typing import Any, Dict, Optional

import atlantis


def _esc(value: Any) -> str:
    return escape(str(value or ""), quote=True)


def _card_button(label: str, command: str) -> str:
    label_html = _esc(label)
    command_attr = _esc(command)
    return f"""
        <button type="button"
                data-home-command="{command_attr}"
                style="position:relative; z-index:10; cursor:pointer;
                       font:inherit; font-size:clamp(10pt, 2vmin, 18pt);
                       color:#14ffd0; background:#14ffd015;
                       border:1px solid #14ffd040; border-radius:8px;
                       padding:clamp(4px, 0.8vmin, 10px) clamp(6px, 1vmin, 12px) clamp(2px, 0.4vmin, 6px);
                       text-align:center; align-self:stretch;">
            {label_html}
        </button>
    """


@homepage
async def homepage(dashboard: Optional[Dict[str, Any]] = None) -> str:
    """Return the dashboard card HTML fragment for this remote."""

    card_id = f"home-dashboard-{uuid.uuid4().hex[:8]}"
    card_id_html = _esc(card_id)
    card_id_js = json.dumps(card_id)
    exec_shell_js = json.dumps(atlantis.get_exec_shell_path())

    actions_html = f"""
        <div style="display:flex; flex-direction:column; align-items:center;
                    gap:clamp(10px, 1.8vmin, 20px);">
            {_card_button("New Game", "@game_button")}
            {_card_button("Join existing game", "@game_join")}
        </div>
    """

    script = f"""
(function() {{
  var cardId = {card_id_js};
  var execShell = {exec_shell_js};
  var attempts = 0;

  function bind() {{
    var root = document.getElementById(cardId);
    if (!root) {{
      attempts += 1;
      if (attempts < 80) setTimeout(bind, 50);
      return;
    }}

    root.querySelectorAll("[data-home-command]").forEach(function(button) {{
      if (button.dataset.homeBound === "1") return;
      button.dataset.homeBound = "1";
      button.addEventListener("click", async function(event) {{
        event.stopPropagation();
        var command = button.getAttribute("data-home-command");
        if (!command || !window._accessToken || typeof sendChatter !== "function") return;
        await sendChatter(window._accessToken, command, {{}}, execShell);
      }});
    }});
  }}

  requestAnimationFrame(bind);
}})()
"""
    await atlantis.client_script(script)

    return f"""<div id="{card_id_html}" class="homeDashboardActions"
        style="width:100%; box-sizing:border-box;">
        {actions_html}
    </div>"""
