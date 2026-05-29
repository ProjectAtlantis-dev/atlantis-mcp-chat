"""Terminal display tools"""

import atlantis
import json

@public
async def terminal_video(url: str) -> None:
    """Play a terminal background video in the feedback div."""
    await atlantis.client_script("""
(function(){
    var host = document.getElementById('chatFeedback');
    if (!host) return;
    if (document.getElementById('feedbackBgVideo')) return; // idempotent
    var v = document.createElement('video');
    v.id = 'feedbackBgVideo';
    v.src = __VIDEO_URL__;
    v.autoplay = true; v.loop = false; v.muted = true; v.playsInline = true;
    v.style.cssText =
      'position:absolute; inset:0; width:100%; height:100%;' +
      'object-fit:cover; z-index:0; pointer-events:none;';
    host.prepend(v);
    // Lift chat, input, and terminal/app chrome above the video.
    var liftChrome = function(){
      var ids = ['feedback', 'chatEditorArea', 'terminal-window-wrapper', 'terminal-title-bar'];
      ids.forEach(function(id){
        var el = document.getElementById(id);
        if (el) { el.style.position='relative'; el.style.zIndex='1'; }
      });
    };
    liftChrome();
    var observer = new MutationObserver(liftChrome);
    observer.observe(host, { childList:true, subtree:true });
    v.addEventListener('ended', function(){
      host.removeEventListener('click', toggleMute);
      observer.disconnect();
      v.remove();
    }, { once: true });
    v.play && v.play();
    // Start muted for autoplay, then let clicks in the video area toggle audio.
    var toggleMute = function(e){
      if (e.target.closest('.chatbox-receiver, .chatbox-sender, #chatEditorArea, #chatButtons, #terminal-title-bar, button, [role="button"], a, input, textarea, select')) return;
      v.muted = !v.muted;
      if (!v.ended && v.play) v.play();
    };
    host.addEventListener('click', toggleMute);
})();
""".replace("__VIDEO_URL__", json.dumps(url)))

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
