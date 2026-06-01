"""Bot tools

A bot is the canonical character/persona/engine unit. Its primary key is the
folder name `sid` under Game/Bots/<sid>/. Prompt, image, default location, and
model settings all live on the bot.
"""

import atlantis
import base64
import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, TypedDict

from .common import _ensure_thumb, home_path, _require_str
from .location import _leaf_location_keys

logger = logging.getLogger("mcp_server")


class BotConfigT(TypedDict):
    """A bot's config.json, normalized into a guaranteed-populated record.

    Core fields (displayName, defaultLocation, provider, model) are required and
    validated at load; the rest carry typed empty-string defaults.
    """
    sid: str
    displayName: str
    defaultLocation: str
    provider: str
    model: str
    baseUrl: str
    apiKeyEnv: str
    image: str


def _bots_dir() -> str:
    return home_path("Game", "Bots")


def _load_bot_json(bot_sid: str) -> dict:
    """Read a bot config."""
    config_path = os.path.join(_bots_dir(), bot_sid, "config.json")
    if os.path.isfile(config_path):
        with open(config_path) as f:
            return json.load(f)
    return {}


def _load_bot_prompt(bot_sid: str) -> str:
    """Read a bot prompt."""
    prompt_path = os.path.join(_bots_dir(), bot_sid, "prompt.md")
    if os.path.isfile(prompt_path):
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


_PROMPT_NAME_RE = re.compile(
    r"\{\{\s*(?:(?P<self>name|self_name)|(?P<kind>name|bot_name)\s*:\s*(?P<sid>[A-Za-z0-9_.-]+))\s*\}\}"
)
_PROMPT_ANY_PLACEHOLDER_RE = re.compile(r"\{\{[^{}]+\}\}")


def _normalize_roster_names(roster_names: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    """Normalize a finalized roster mapping of bot sid -> in-game display name."""
    if not roster_names:
        return {}

    names: Dict[str, str] = {}
    for raw_sid, raw_name in roster_names.items():
        sid = str(raw_sid).strip()
        name = str(raw_name).strip()
        if not sid:
            raise ValueError("Roster contains an empty bot sid")
        if not name:
            raise ValueError(f"Roster name for bot {sid!r} is empty")
        _validate_bot(sid)
        names[sid] = name
    return names


def bot_roster_name(bot_sid: str, roster_names: Optional[Mapping[str, str]] = None) -> str:
    """Return the finalized in-game name for a bot sid."""
    _validate_bot(bot_sid)
    names = _normalize_roster_names(roster_names)
    if bot_sid in names:
        return names[bot_sid]
    raw = _load_bot_json(bot_sid)
    default_name = str(raw.get("displayName", bot_sid) or bot_sid).strip()
    return default_name or bot_sid


def render_bot_prompt(bot_sid: str, roster_names: Optional[Mapping[str, str]] = None) -> str:
    """Render Game/Bots/<sid>/prompt.md with finalized roster names.

    Supported placeholders:
    - {{name}} or {{self_name}} for the current bot
    - {{name:<sid>}} or {{bot_name:<sid>}} for another bot in the roster
    """
    _validate_bot(bot_sid)
    names = _normalize_roster_names(roster_names)
    template = _load_bot_prompt(bot_sid)

    def replace_name(match: re.Match[str]) -> str:
        referenced_sid = match.group("sid") or bot_sid
        return bot_roster_name(referenced_sid, names)

    rendered = _PROMPT_NAME_RE.sub(replace_name, template)
    unresolved = _PROMPT_ANY_PLACEHOLDER_RE.search(rendered)
    if unresolved:
        raise ValueError(
            f"Unsupported prompt placeholder {unresolved.group(0)!r} in bot {bot_sid!r}"
        )
    return rendered


def _validate_default_location(bot_sid: str, location: str) -> None:
    """Validate a bot defaultLocation against standable location keys."""
    if not location:
        return
    valid_locations = set(_leaf_location_keys())
    if location not in valid_locations:
        valid = ", ".join(sorted(valid_locations)) or "none"
        raise ValueError(
            f"Bot {bot_sid!r} has invalid defaultLocation {location!r}. "
            f"Expected one of: {valid}"
        )


def _bot_rows() -> List[Dict[str, Any]]:
    """Pure data: list available bots. No client side effects."""
    bots_dir = _bots_dir()
    bots: List[Dict[str, Any]] = []
    if not os.path.isdir(bots_dir):
        return bots
    for entry in sorted(os.listdir(bots_dir)):
        entry_dir = os.path.join(bots_dir, entry)
        if not os.path.isdir(entry_dir) or entry.startswith(".") or entry == "__pycache__":
            continue
        bot_data = _load_bot_json(entry)
        mtimes = []
        for sub_root, _dirs, sub_files in os.walk(entry_dir):
            for filename in sub_files:
                mtimes.append(os.path.getmtime(os.path.join(sub_root, filename)))
        updated = datetime.fromtimestamp(max(mtimes)).strftime('%Y-%m-%d %H:%M') if mtimes else ''

        provider = bot_data.get("provider", "")
        model = bot_data.get("model", "")
        model_label = f"{provider}: {model}" if provider and model else (model or provider)
        default_location = str(bot_data.get("defaultLocation", "") or "")
        _validate_default_location(entry, default_location)

        image_data = ""
        image_file = bot_data.get("image", "")
        if image_file:
            image_path = os.path.join(entry_dir, image_file)
            if os.path.isfile(image_path):
                thumb = _ensure_thumb(image_path)
                if thumb:
                    ext = os.path.splitext(thumb)[1].lower().lstrip(".")
                    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "gif": "gif", "webp": "webp"}.get(ext, "jpeg")
                    with open(thumb, "rb") as img:
                        b64 = base64.b64encode(img.read()).decode("ascii")
                    image_data = f"data:image/{mime};base64,{b64}"

        bots.append({
            "sid": entry,
            "displayName": bot_data.get("displayName", entry),
            "image": image_data,
            "defaultLocation": default_location,
            "prompt": render_bot_prompt(entry),
            "promptTemplate": _load_bot_prompt(entry),
            "model": model_label,
            "updated": updated,
        })
    return bots


@public
async def bot_list() -> List[Dict[str, Any]]:
    """List bots — config metadata only."""
    bots = _bot_rows()
    await atlantis.client_data("Bots", bots, column_formatter={
        "prompt": {"type": "markdown", "maxWidth": "80ch"},
        "promptTemplate": {"type": "markdown", "maxWidth": "80ch"},
    })
    return bots


@public
async def prompt_assemble(bot_sid: str, roster_names: Optional[Dict[str, str]] = None) -> str:
    """Render a bot prompt using a finalized roster mapping of bot sid -> desired name."""
    return render_bot_prompt(bot_sid, roster_names)


@public
async def prompt_aassemble(bot_sid: str, roster_names: Optional[Dict[str, str]] = None) -> str:
    """Backward-compatible typo alias for prompt_assemble."""
    return await prompt_assemble(bot_sid, roster_names)


def bot_default_location(bot_sid: str) -> Optional[str]:
    """Return a bot-specific default location from config.json, if set."""
    location = _load_bot_json(bot_sid).get("defaultLocation", "")
    default_location = str(location).strip()
    _validate_default_location(bot_sid, default_location)
    return default_location or None


def bot_entry_location(bot_sid: str) -> str:
    """Return the entry location for a bot, or raise if not configured."""
    location = bot_default_location(bot_sid)
    if not location:
        raise ValueError(
            f"No defaultLocation configured for bot {bot_sid!r}. "
            f"Set defaultLocation in the bot config.json."
        )
    return location


def _validate_bot(bot_sid: str) -> None:
    """Validate a bot folder."""
    if not os.path.isdir(os.path.join(_bots_dir(), bot_sid)):
        raise ValueError(f"Bot folder not found: {bot_sid}")


def load_bot(bot_sid: str) -> BotConfigT:
    """Load a bot's config as a typed, fully-populated record.

    The single boundary where a loose config.json becomes a known shape. Raises
    if the sid has no folder (foreign-key check) or if a core field is missing —
    a malformed bot fails loudly here instead of rendering a half-blank row.
    """
    _validate_bot(bot_sid)
    raw = _load_bot_json(bot_sid)
    label = f"Bot {bot_sid!r} config.json"
    return BotConfigT(
        sid=bot_sid,
        displayName=_require_str(raw, "displayName", label),
        defaultLocation=_require_str(raw, "defaultLocation", label),
        provider=_require_str(raw, "provider", label),
        model=_require_str(raw, "model", label),
        baseUrl=str(raw.get("baseUrl", "")),
        apiKeyEnv=str(raw.get("apiKeyEnv", "")),
        image=str(raw.get("image", "")),
    )
