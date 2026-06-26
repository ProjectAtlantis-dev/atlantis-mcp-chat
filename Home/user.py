"""User/session-scoped tools."""

import atlantis
import base64
import json
import mimetypes
import os

from .term import term_background_video, term_background_video_file, term_player


USER_DEFAULT_BACKGROUND_ALIGN = "75%"


@visible
def _user_default_background_path() -> str:
    return os.path.join(os.path.dirname(__file__), "builder.jpg")


def _image_data_url(image_path: str) -> str:
    mime_type, _ = mimetypes.guess_type(image_path)
    if not mime_type or not mime_type.startswith("image/"):
        mime_type = "image/jpeg"
    with open(image_path, "rb") as image:
        encoded = base64.b64encode(image.read()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


async def _restore_user_default_background_when_background_video_ends() -> None:
    background_url = _image_data_url(_user_default_background_path())
    await atlantis.client_terminal_script(f"""
(function(){{
  var backgroundUrl = {json.dumps(background_url)};
  var verticalAlign = {json.dumps(USER_DEFAULT_BACKGROUND_ALIGN)};

  function restoreDefaultBackground() {{
    var chatFeedback = document.getElementById('chatFeedback');
    if (!chatFeedback) return;

    var oldMedia = document.querySelectorAll(
      '#feedbackBgVideo, video[data-background-video="true"], iframe[data-background-player="true"]'
    );
    for (var i = 0; i < oldMedia.length; i++) {{
      try {{
        if (oldMedia[i].pause) oldMedia[i].pause();
        oldMedia[i].removeAttribute('src');
        if (oldMedia[i].load) oldMedia[i].load();
      }} catch (_err) {{}}
      oldMedia[i].remove();
    }}

    chatFeedback.style.background = 'black';
    chatFeedback.style.backgroundImage = 'url(' + JSON.stringify(backgroundUrl) + ')';
    chatFeedback.style.backgroundSize = 'cover';
    chatFeedback.style.backgroundPosition = 'center ' + verticalAlign;
    chatFeedback.style.backgroundRepeat = 'no-repeat';
  }}

  function attachBackgroundVideoRestoreHook() {{
    var backgroundVideos = document.querySelectorAll('video[data-background-video="true"]');
    var backgroundVideo = backgroundVideos.length ? backgroundVideos[backgroundVideos.length - 1] : null;
    if (!backgroundVideo) return false;
    if (backgroundVideo.dataset.userDefaultRestoreAttached === 'true') return true;
    backgroundVideo.dataset.userDefaultRestoreAttached = 'true';
    backgroundVideo.addEventListener('ended', function() {{
      setTimeout(restoreDefaultBackground, 0);
    }}, {{ once: true }});
    backgroundVideo.addEventListener('error', function() {{
      setTimeout(restoreDefaultBackground, 0);
    }}, {{ once: true }});
    return true;
  }}

  if (attachBackgroundVideoRestoreHook()) return;
  var attempts = 0;
  var timer = setInterval(function() {{
    attempts += 1;
    if (attachBackgroundVideoRestoreHook() || attempts >= 300) clearInterval(timer);
  }}, 100);
}})();
""")


@public
async def user_background_video(video_name: str) -> None:
    """Play the named user background video in the terminal."""
    await term_background_video(f"https://pub-59cb84bebe804fd1b3257bb6c283a2b3.r2.dev/{video_name}")
    await _restore_user_default_background_when_background_video_ends()


@public
async def user_background_player(url: str) -> None:
    """Show a user background player for the URL."""
    await term_player(url)


@public
async def user_background_video_file(video_path: str) -> None:
    """Play a local user background video file in the terminal."""
    if not os.path.isabs(video_path):
        video_path = os.path.join(os.path.dirname(__file__), video_path)
    await term_background_video_file(video_path)
    await _restore_user_default_background_when_background_video_ends()


@public
async def user_background_default() -> None:
    """Set the user default background image."""
    await atlantis.set_background(
        _user_default_background_path(),
        vertical_align=USER_DEFAULT_BACKGROUND_ALIGN,
    )
