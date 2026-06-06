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


@visible
async def homepage(dashboard: Optional[Dict[str, Any]] = None) -> str:
    """Return the dashboard card HTML fragment for this remote."""

    dashboard = dashboard or {}
    name = _esc(dashboard.get("name") or dashboard.get("remote_name") or "Home")
    owner = _esc(dashboard.get("owner") or "")
    description = "hello world"
    image = ""
    card_id = f"home-dashboard-{uuid.uuid4().hex[:8]}"
    card_id_html = _esc(card_id)
    card_id_js = json.dumps(card_id)
    exec_shell_js = json.dumps(atlantis.get_exec_shell_path())

    media_html = (
        f"""
        <img src="{_esc(image)}"
             style="height:40%; min-height:140px; max-height:240px; max-width:100%; aspect-ratio:1 / 1;
                    border-radius:12px; object-fit:cover; border:2px solid #444;" />
        """
        if image
        else """
        <div style="height:40%; min-height:140px; max-height:240px; max-width:100%; aspect-ratio:1 / 1;
                    border-radius:12px; background:#222; display:flex; align-items:center; justify-content:center;
                    font-size:clamp(20px, 4vmin, 48px); border:2px solid #444;">
            🏠
        </div>
        """
    )

    actions_html = f"""
        <div style="display:flex; flex-direction:column; align-items:center;
                    gap:clamp(10px, 1.8vmin, 20px); margin-top:clamp(10px, 1.8vmin, 20px);">
            {_card_button("New Game", "@game_button")}
            {_card_button("Join existing game", "@game_join")}
        </div>
    """

    owner_html = (
        f"""
        <div style="font-size:clamp(9pt, 1.5vmin, 14pt); color:#555;
                    text-align:center; margin-top:auto; display:flex; justify-content:center; align-items:center;
                    gap:6px; flex-wrap:wrap;">
            <span>{owner}</span>
        </div>
        """
        if owner
        else ""
    )

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
      button.addEventListener("click", async function() {{
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

    return f"""<div id="{card_id_html}" class="homeDashboardCard"
        style="height:100%; width:100%; display:flex; flex-direction:column; align-items:center;
               justify-content:flex-start; gap:clamp(8px, 1.5vmin, 16px); box-sizing:border-box;">
        <div style="font-size:clamp(10pt, 1.8vmin, 16pt); color:#666; text-align:center; word-break:break-word;">
            {name}
        </div>
        {media_html}
        <div style="position:absolute; top:8px; right:10px;">
            <span style="color:#0f0; font-size:clamp(10pt, 1.5vmin, 16pt);">●</span>
        </div>
        <div style="font-size:clamp(12pt, 2.5vmin, 22pt); color:#aaa; text-align:center; word-break:break-word;">
            {description}
        </div>
        {actions_html}
        {owner_html}
    </div>"""
