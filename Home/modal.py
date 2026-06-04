"""Modal UI tools"""

import atlantis
import asyncio
import html as html_lib
import json
import uuid
from typing import Optional


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
  #displayname-{uid} {{
    box-sizing: border-box;
    width: 100%;
    min-width: min(100%, 320px);
    padding: 28px;
    color: #f7f4ea;
    background:
      linear-gradient(to bottom, rgba(20, 34, 48, 0.96), rgba(20, 50, 60, 0.96)),
      radial-gradient(circle at 18% 20%, rgba(20, 255, 208, 0.22), transparent 34%);
    border: 1px solid rgba(20, 255, 208, 0.42);
    border-radius: 8px;
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }}
  #displayname-{uid} h2 {{
    margin: 10px 0 28px;
    font-size: 30px;
    line-height: 1.1;
    color: #fffaf0;
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
    if (!host) return;
    var rect = host.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    host.style.left = "50%";
    host.style.top = "50%";
    host.style.right = "auto";
    host.style.bottom = "auto";
    host.style.transform = "translate(-50%, -50%)";
    host.style.margin = "0";
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
