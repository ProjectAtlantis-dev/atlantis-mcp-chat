"""Terminal display tools"""

import atlantis

@public
async def terminal_video(url: str) -> None:
    """Play a terminal background video in the feedback div."""
    await atlantis.set_background_video(
        url,
        vertical_align="center",
        loop=False,
        muted=True,
        autoplay=True,
        plays_inline=True,
        remove_on_ended=True,
        toggle_audio=True,
    )

@public
async def terminal_restore() -> None:
    """Remove frosted styling from terminal feedback bubbles."""
    await atlantis.client_script("""
(function(){
  var fb = document.getElementById('feedback');
  if (window.terminalFrostBorderTimer) clearTimeout(window.terminalFrostBorderTimer);
  if (fb) fb.classList.remove('frosted');
  var s = document.getElementById('frostStyle');
  if (s) s.remove();
})();
""")

@visible
async def terminal_show() -> str:
    """Print the atlantis terminal key for this call (session key + shell)."""
    key = atlantis.get_terminal_key()
    if not key:
        raise RuntimeError("No terminal key in this call context")
    return key
