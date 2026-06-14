"""Modal UI tools"""

import atlantis
import asyncio
import html as html_lib
import json
import uuid
from typing import Any, Dict, List, Optional


def _modal_shell_css(
    selector: str,
    *,
    padding: int,
    heading_margin: str,
    heading_font_size: int,
    heading_line_height: float,
) -> str:
    return f"""
  {selector} {{
    box-sizing: border-box;
    width: 100%;
    min-width: min(100%, 320px);
    padding: {padding}px;
    color: #f7f4ea;
    background:
      linear-gradient(to bottom, rgba(20, 34, 48, 0.96), rgba(20, 50, 60, 0.96)),
      radial-gradient(circle at 18% 20%, rgba(20, 255, 208, 0.22), transparent 34%);
    border: 1px solid rgba(20, 255, 208, 0.42);
    border-radius: 8px;
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }}
  {selector} h2 {{
    margin: {heading_margin};
    font-size: {heading_font_size}px;
    line-height: {heading_line_height};
    color: #fffaf0;
  }}
"""


@public
@visible
async def modal_string(
    modal_text: str,
    title: str = "",
    heading: str = "",
    submit_label: str = "Submit",
    submitting_label: str = "Submitting...",
    empty_error: str = "Enter a value to continue.",
    input_type: str = "text",
    autocomplete: str = "off",
) -> Optional[str]:
    """Pop up a modal asking the caller for a string.

    Returns None if the user closes/cancels the modal without submitting.
    """
    uid = uuid.uuid4().hex[:8]
    modal_string_id = f"modal_string:{uid}"
    modal_string_id_js = json.dumps(modal_string_id)
    modal_text_html = html_lib.escape(modal_text or "Enter a value")
    heading_block = f"<h2>{html_lib.escape(heading)}</h2>" if heading else ""
    submit_label_html = html_lib.escape(submit_label)
    submitting_label_js = json.dumps(submitting_label)
    empty_error_js = json.dumps(empty_error)
    input_type_html = html_lib.escape(input_type)
    autocomplete_html = html_lib.escape(autocomplete)
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    atlantis.session_shared.set(f"{modal_string_id}:future", future)
    html = f"""
<style>
{_modal_shell_css(f"#displayname-{uid}", padding=28, heading_margin="10px 0 28px", heading_font_size=30, heading_line_height=1.1)}
  #displayname-{uid} {{
    width: 100%;
    visibility: hidden;
  }}
  #displayname-{uid} form {{
    display: grid;
    gap: 12px;
    width: 100%;
  }}
  #displayname-{uid} label {{
    color: #fffaf0;
    font-size: 22px;
    font-weight: 700;
  }}
  #displayname-{uid} input {{
    box-sizing: border-box;
    width: 100%;
    min-height: 42px;
    padding: 0 12px;
    color: #fffaf0;
    background: rgba(7, 15, 22, 0.58);
    border: 1px solid rgba(20, 255, 208, 0.42);
    border-radius: 6px;
    font: inherit;
    font-size: 20px;
  }}
  #displayname-{uid} input:focus {{
    outline: 2px solid rgba(20, 255, 208, 0.45);
    outline-offset: 2px;
  }}
  #displayname-{uid} .err {{
    color: #ffb4a8;
    font-size: 13px;
  }}
  #displayname-{uid} .err:empty {{
    display: none;
  }}
  #displayname-{uid} button {{
    justify-self: center;
    min-height: 40px;
    padding: 0 16px;
    color: #fffaf0;
    background: linear-gradient(to bottom, #1a8a78, #143a52);
    border: 0;
    border-radius: 6px;
    font: inherit;
    font-weight: 700;
    cursor: pointer;
  }}
  #displayname-{uid} button:hover {{
    background: linear-gradient(to bottom, #22b89e, #1a527a);
  }}
  #displayname-{uid} button:disabled {{
    cursor: default;
    opacity: 0.65;
  }}
</style>
<section id="displayname-{uid}" aria-label="Input">
  {heading_block}
  <form id="displayname-form-{uid}">
    <label for="displayname-input-{uid}">{modal_text_html}</label>
    <input id="displayname-input-{uid}" name="value" type="{input_type_html}" autocomplete="{autocomplete_html}" maxlength="200" required autofocus>
    <div id="displayname-err-{uid}" class="err" aria-live="polite"></div>
    <button id="displayname-btn-{uid}" type="submit">{submit_label_html}</button>
  </form>
</section>
"""
    modal_id = await atlantis.client_modal(html, title=title or " ")
    atlantis.session_shared.set(f"{modal_string_id}:modal_id", modal_id)

    # Route modal-originated commands (cancel / submit) to this tool call's
    # exec shell so they nest inside the modal_string subshell rather than
    # polluting the user's parent shell history.
    #
    # WHY THIS IS REQUIRED (do not remove the 4th arg to sendChatter below):
    #   - Every @visible/@chat tool call spawns an isolated callback shell on
    #     the Node side via Session.spawnShell(parent, 'tool', isBackground=True).
    #     That shell gets a FLAT name like "37" (not "2.36.1") precisely so the
    #     tool's internal chatter (modals, scripts, log lines, button click
    #     callbacks) stays out of the user's command history on "2.36".
    #   - The Node engage handler defaults missing shellPath to the websocket's
    #     root working shell (app_server.ts ~line 2131:
    #     `targetShellPath = params.shellPath ?? session.getWorkingPath(rootShellPath)`).
    #     There is no server-side awareness of "the currently active tool
    #     callback shell" - it can't infer "37" from the websocket alone,
    #     since multiple tool calls can be in flight at once.
    #   - Therefore: if `exec_shell_js` is omitted from the sendChatter calls
    #     below, modal_string_click/_cancel will be routed to the user's main
    #     shell ("2.X") instead of "37.1". Visible symptom: the click event
    #     shows up as a sibling of the modal_string command in /history.
    #   - The matching Node-side fix that lets the data-callback render skip
    #     auto-display correctly is in Session.ts handleMcpCallback's
    #     `messageType === "data"` branch, which explicitly marks the caller's
    #     shell. See the comment there for the symmetric explanation.
    exec_shell_js = json.dumps(atlantis.get_exec_shell_path())

    script = f"""
(function() {{
  var settled = false;
  var observer = null;
  function cleanup() {{ if (observer) {{ try {{ observer.disconnect(); }} catch (e) {{}} observer = null; }} }}
  function reveal(root) {{
    root.style.visibility = "visible";
  }}
  function centerDialog(root) {{
    var host = null;
    var node = root;
    for (var i = 0; i < 8 && node && node !== document.body; i++) {{
      var style = window.getComputedStyle(node);
      var rect = node.getBoundingClientRect();
      var fillsViewport = rect.width >= window.innerWidth * 0.9 && rect.height >= window.innerHeight * 0.9;
      if ((style.position === "fixed" || style.position === "absolute") && !fillsViewport) {{
        host = node;
        break;
      }}
      node = node.parentElement;
    }}
    if (!host) {{
      reveal(root);
      return;
    }}
    var rect = host.getBoundingClientRect();
    if (!rect.width || !rect.height) {{
      reveal(root);
      return;
    }}
    if (!host.dataset.modalStringOriginalWidth) {{
      host.dataset.modalStringOriginalWidth = String(rect.width);
    }}
    var originalWidth = Number(host.dataset.modalStringOriginalWidth) || rect.width;
    var targetWidth = Math.round(originalWidth * 0.5);
    var viewportMax = Math.max(320, window.innerWidth - 32);
    host.style.width = Math.min(Math.max(320, targetWidth), viewportMax) + "px";
    host.style.maxWidth = "calc(100vw - 32px)";
    host.style.left = "50%";
    host.style.top = "50%";
    host.style.right = "auto";
    host.style.bottom = "auto";
    host.style.transform = "translate(-50%, -50%)";
    host.style.margin = "0";
    reveal(root);
  }}
  function scheduleCenter(root) {{
    centerDialog(root);
    requestAnimationFrame(function() {{
      centerDialog(root);
      setTimeout(function() {{ centerDialog(root); }}, 180);
    }});
  }}
  async function cancel() {{
    if (settled) return;
    settled = true;
    cleanup();
    if (!window._accessToken) return;
    try {{
      await sendChatter(window._accessToken, "@modal_string_cancel", {{
        modal_string_id: {modal_string_id_js}
      }}, {exec_shell_js});
    }} catch (e) {{}}
  }}
  function bind() {{
    var root = document.getElementById("displayname-{uid}");
    var form = document.getElementById("displayname-form-{uid}");
    var button = document.getElementById("displayname-btn-{uid}");
    var input = document.getElementById("displayname-input-{uid}");
    var error = document.getElementById("displayname-err-{uid}");
    if (!root || !form || !button || !input) return;
    function focusInput() {{ input.focus({{ preventScroll: true }}); input.select(); }}
    scheduleCenter(root);
    focusInput();
    setTimeout(function() {{ scheduleCenter(root); focusInput(); }}, 120);
    form.addEventListener("submit", async function(event) {{
      event.preventDefault();
      if (settled) return;
      if (!window._accessToken) return;
      var value = input.value.trim();
      if (!value) {{ if (error) error.textContent = {empty_error_js}; input.focus(); return; }}
      if (error) error.textContent = "";
      button.disabled = true;
      button.textContent = {submitting_label_js};
      settled = true;
      cleanup();
      await sendChatter(window._accessToken, "@modal_string_click", {{
        modal_string_id: {modal_string_id_js},
        display_name: value
      }}, {exec_shell_js});
    }});
    observer = new MutationObserver(function() {{
      if (!document.body.contains(root)) {{ cancel(); }}
    }});
    observer.observe(document.body, {{ childList: true, subtree: true }});
  }}
  requestAnimationFrame(function() {{ requestAnimationFrame(bind); }});
}})()
"""
    await atlantis.client_script(script)
    try:
        return await future
    finally:
        atlantis.session_shared.remove(f"{modal_string_id}:future")
        atlantis.session_shared.remove(f"{modal_string_id}:modal_id")


@public
@visible
async def modal_menu(
    choices: List[Dict[str, Any]],
    title: str = "",
    heading: str = "",
    width_ratio: float = 0.67,
) -> Optional[Dict[str, Any]]:
    """Pop up a modal menu and return the selected choice object.

    Returns None if the user closes/cancels the modal without selecting.
    """
    if not isinstance(choices, list) or not choices:
        raise ValueError("choices must be a non-empty array")

    choice_by_id: Dict[str, Dict[str, Any]] = {}
    choice_buttons = []
    for choice in choices:
        if not isinstance(choice, dict):
            raise ValueError("each choice must be an object")
        choice_id = str(choice.get("id", "")).strip()
        choice_text = str(choice.get("text", "")).strip()
        if not choice_id:
            raise ValueError("each choice requires a non-empty id")
        if not choice_text:
            raise ValueError("each choice requires a non-empty text")
        if choice_id in choice_by_id:
            raise ValueError(f"duplicate choice id: {choice_id!r}")
        choice_by_id[choice_id] = choice
        columns = choice.get("columns")
        if isinstance(columns, list) and columns:
            button_content = (
                '<span class="menu-choice-grid">'
                + "".join(
                    f'<span class="menu-choice-cell">{html_lib.escape(str(column or ""))}</span>'
                    for column in columns
                )
                + "</span>"
            )
        else:
            button_content = html_lib.escape(choice_text)
        choice_buttons.append(
            '<button type="button" class="menu-choice" role="menuitem" '
            f'data-choice-id="{html_lib.escape(choice_id, quote=True)}">'
            f"{button_content}</button>"
        )

    uid = uuid.uuid4().hex[:8]
    modal_menu_id = f"modal_menu:{uid}"
    modal_menu_id_js = json.dumps(modal_menu_id)
    width_ratio = max(0.25, min(1.0, float(width_ratio or 0.67)))
    width_ratio_js = json.dumps(width_ratio)
    heading_block = f"<h2>{html_lib.escape(heading)}</h2>" if heading else ""
    table_headers = None
    for choice in choices:
        headers = choice.get("column_headers")
        if isinstance(headers, list) and headers:
            table_headers = headers
            break
    header_block = ""
    if table_headers:
        header_block = (
            '<div class="menu-header" aria-hidden="true">'
            + "".join(
                f'<span class="menu-header-cell">{html_lib.escape(str(header or ""))}</span>'
                for header in table_headers
            )
            + "</div>"
        )
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    atlantis.session_shared.set(f"{modal_menu_id}:future", future)
    atlantis.session_shared.set(f"{modal_menu_id}:choices", choice_by_id)
    html = f"""
<style>
{_modal_shell_css(f"#modalmenu-{uid}", padding=22, heading_margin="4px 0 16px", heading_font_size=24, heading_line_height=1.15)}
  #modalmenu-{uid} {{
    width: 100%;
    visibility: hidden;
  }}
  #modalmenu-{uid} .menu-list {{
    display: grid;
    gap: 8px;
    width: 100%;
  }}
  #modalmenu-{uid} .menu-header {{
    display: grid;
    grid-template-columns: minmax(118px, 1.1fr) minmax(74px, 0.75fr) minmax(74px, 0.75fr) minmax(58px, 0.55fr);
    gap: 10px;
    padding: 0 14px 2px;
    color: rgba(255, 250, 240, 0.68);
    font-size: 12px;
    font-weight: 800;
    letter-spacing: 0;
    text-transform: uppercase;
  }}
  #modalmenu-{uid} .menu-header-cell {{
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }}
  #modalmenu-{uid} .menu-choice {{
    box-sizing: border-box;
    width: 100%;
    min-height: 42px;
    padding: 0 14px;
    color: #fffaf0;
    background: rgba(7, 15, 22, 0.58);
    border: 1px solid rgba(20, 255, 208, 0.34);
    border-radius: 6px;
    font: inherit;
    font-size: 18px;
    font-weight: 400;
    text-align: left;
    cursor: pointer;
  }}
  #modalmenu-{uid} .menu-choice-grid {{
    display: grid;
    grid-template-columns: minmax(118px, 1.1fr) minmax(74px, 0.75fr) minmax(74px, 0.75fr) minmax(58px, 0.55fr);
    gap: 10px;
    align-items: center;
  }}
  #modalmenu-{uid} .menu-choice-cell {{
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }}
  #modalmenu-{uid} .menu-choice:hover,
  #modalmenu-{uid} .menu-choice:focus {{
    background: rgba(20, 255, 208, 0.14);
    border-color: rgba(20, 255, 208, 0.62);
    outline: none;
  }}
  #modalmenu-{uid} .menu-choice:disabled {{
    cursor: default;
    opacity: 0.65;
  }}
</style>
<section id="modalmenu-{uid}" aria-label="Menu">
  {heading_block}
  <div class="menu-list" role="menu">
    {header_block}
    {"".join(choice_buttons)}
  </div>
</section>
"""
    modal_id = await atlantis.client_modal(html, title=title or " ")
    atlantis.session_shared.set(f"{modal_menu_id}:modal_id", modal_id)
    exec_shell_js = json.dumps(atlantis.get_exec_shell_path())

    script = f"""
(function() {{
  var settled = false;
  var observer = null;
  function cleanup() {{ if (observer) {{ try {{ observer.disconnect(); }} catch (e) {{}} observer = null; }} }}
  function reveal(root) {{
    root.style.visibility = "visible";
  }}
  function centerDialog(root) {{
    var host = null;
    var node = root;
    for (var i = 0; i < 8 && node && node !== document.body; i++) {{
      var style = window.getComputedStyle(node);
      var rect = node.getBoundingClientRect();
      var fillsViewport = rect.width >= window.innerWidth * 0.9 && rect.height >= window.innerHeight * 0.9;
      if ((style.position === "fixed" || style.position === "absolute") && !fillsViewport) {{
        host = node;
        break;
      }}
      node = node.parentElement;
    }}
    if (!host) {{
      reveal(root);
      return;
    }}
    var rect = host.getBoundingClientRect();
    if (!rect.width || !rect.height) {{
      reveal(root);
      return;
    }}
    if (!host.dataset.modalMenuOriginalWidth) {{
      host.dataset.modalMenuOriginalWidth = String(rect.width);
    }}
    var originalWidth = Number(host.dataset.modalMenuOriginalWidth) || rect.width;
    var targetWidth = Math.round(originalWidth * {width_ratio_js});
    var viewportMax = Math.max(320, window.innerWidth - 32);
    host.style.width = Math.min(Math.max(320, targetWidth), viewportMax) + "px";
    host.style.maxWidth = "calc(100vw - 32px)";
    host.style.left = "50%";
    host.style.top = "50%";
    host.style.right = "auto";
    host.style.bottom = "auto";
    host.style.transform = "translate(-50%, -50%)";
    host.style.margin = "0";
    reveal(root);
  }}
  function scheduleCenter(root) {{
    centerDialog(root);
    requestAnimationFrame(function() {{
      centerDialog(root);
      setTimeout(function() {{ centerDialog(root); }}, 180);
    }});
  }}
  async function cancel() {{
    if (settled) return;
    settled = true;
    cleanup();
    if (!window._accessToken) return;
    try {{
      await sendChatter(window._accessToken, "@modal_menu_cancel", {{
        modal_menu_id: {modal_menu_id_js}
      }}, {exec_shell_js});
    }} catch (e) {{}}
  }}
  function bind() {{
    var root = document.getElementById("modalmenu-{uid}");
    if (!root) return;
    var buttons = Array.prototype.slice.call(root.querySelectorAll(".menu-choice"));
    if (!buttons.length) return;
    scheduleCenter(root);
    buttons[0].focus({{ preventScroll: true }});
    setTimeout(function() {{ scheduleCenter(root); }}, 120);
    buttons.forEach(function(button) {{
      button.addEventListener("click", async function() {{
        if (settled) return;
        if (!window._accessToken) return;
        var choiceId = button.getAttribute("data-choice-id") || "";
        buttons.forEach(function(btn) {{ btn.disabled = true; }});
        settled = true;
        cleanup();
        await sendChatter(window._accessToken, "@modal_menu_select", {{
          modal_menu_id: {modal_menu_id_js},
          choice_id: choiceId
        }}, {exec_shell_js});
      }});
      button.addEventListener("keydown", function(event) {{
        var index = buttons.indexOf(button);
        if (event.key === "ArrowDown") {{
          event.preventDefault();
          buttons[(index + 1) % buttons.length].focus({{ preventScroll: true }});
        }} else if (event.key === "ArrowUp") {{
          event.preventDefault();
          buttons[(index + buttons.length - 1) % buttons.length].focus({{ preventScroll: true }});
        }} else if (event.key === "Enter" || event.key === " ") {{
          event.preventDefault();
          button.click();
        }}
      }});
    }});
    observer = new MutationObserver(function() {{
      if (!document.body.contains(root)) {{ cancel(); }}
    }});
    observer.observe(document.body, {{ childList: true, subtree: true }});
  }}
  requestAnimationFrame(function() {{ requestAnimationFrame(bind); }});
}})()
"""
    await atlantis.client_script(script)
    try:
        return await future
    finally:
        atlantis.session_shared.remove(f"{modal_menu_id}:future")
        atlantis.session_shared.remove(f"{modal_menu_id}:modal_id")
        atlantis.session_shared.remove(f"{modal_menu_id}:choices")


@public
@visible
async def modal_string_click(modal_string_id: str, display_name: str) -> None:
    """Handle the display-name modal submit."""
    display_name = (display_name or "").strip()
    if not display_name:
        raise ValueError("display_name is required")
    modal_key = f"{modal_string_id}:modal_id"
    future_key = f"{modal_string_id}:future"
    modal_id = atlantis.session_shared.get(modal_key)
    if modal_id:
        await atlantis.client_modal_close(modal_id)
        atlantis.session_shared.remove(modal_key)
    future = atlantis.session_shared.get(future_key)
    if future is None:
        raise ValueError("Display-name modal is no longer active")
    if not future.done():
        future.set_result(display_name)


@public
@visible
async def modal_string_cancel(modal_string_id: str) -> None:
    """Handle the user closing the modal without submitting."""
    modal_key = f"{modal_string_id}:modal_id"
    future_key = f"{modal_string_id}:future"
    modal_id = atlantis.session_shared.get(modal_key)
    if modal_id:
        try:
            await atlantis.client_modal_close(modal_id)
        except Exception:
            pass
        atlantis.session_shared.remove(modal_key)
    future = atlantis.session_shared.get(future_key)
    if future is not None and not future.done():
        future.set_result(None)


@public
@visible
async def modal_menu_select(modal_menu_id: str, choice_id: str) -> None:
    """Handle a modal menu selection."""
    choice_id = (choice_id or "").strip()
    if not choice_id:
        raise ValueError("choice_id is required")
    modal_key = f"{modal_menu_id}:modal_id"
    future_key = f"{modal_menu_id}:future"
    choices_key = f"{modal_menu_id}:choices"
    modal_id = atlantis.session_shared.get(modal_key)
    if modal_id:
        await atlantis.client_modal_close(modal_id)
        atlantis.session_shared.remove(modal_key)
    choices = atlantis.session_shared.get(choices_key) or {}
    choice = choices.get(choice_id)
    if choice is None:
        raise ValueError(f"Unknown menu choice: {choice_id!r}")
    future = atlantis.session_shared.get(future_key)
    if future is None:
        raise ValueError("Menu modal is no longer active")
    if not future.done():
        future.set_result(choice)


@public
@visible
async def modal_menu_cancel(modal_menu_id: str) -> None:
    """Handle the user closing a modal menu without selecting."""
    modal_key = f"{modal_menu_id}:modal_id"
    future_key = f"{modal_menu_id}:future"
    modal_id = atlantis.session_shared.get(modal_key)
    if modal_id:
        try:
            await atlantis.client_modal_close(modal_id)
        except Exception:
            pass
        atlantis.session_shared.remove(modal_key)
    future = atlantis.session_shared.get(future_key)
    if future is not None and not future.done():
        future.set_result(None)
