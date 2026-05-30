"""Role tools

A *role* is a character in the game — the welded unit of persona + engine.
There is no separate bot: the role carries its own model. Each role folder
Game/Roles/<key>/ holds config.json (displayName, defaultLocation, purpose,
plus the LLM engine fields model/baseUrl/apiKeyEnv/image) and prompt.md. The
lobby UI shows a roster of roles; each gets a runtime slot
assignment (empty, AI-driven, or human-driven) once a scenario instantiates it.
"""

import atlantis
import base64
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from dynamic_functions.Home.common import _roles_dir, _ensure_thumb

logger = logging.getLogger("mcp_server")


def _load_role_json(role_name: str) -> dict:
    """Read a role config"""
    rjson = os.path.join(_roles_dir(), role_name, "config.json")
    if os.path.isfile(rjson):
        with open(rjson) as f:
            return json.load(f)
    return {}


def _role_rows() -> List[Dict[str, Any]]:
    """Pure data: list available roles. No client side effects."""
    roles_dir = _roles_dir()
    roles: List[Dict[str, Any]] = []
    if not os.path.isdir(roles_dir):
        return roles
    for entry in sorted(os.listdir(roles_dir)):
        entry_dir = os.path.join(roles_dir, entry)
        if not os.path.isdir(entry_dir) or entry.startswith(".") or entry == "__pycache__":
            continue
        role_data = _load_role_json(entry)
        mtimes = []
        for sub_root, _dirs, sub_files in os.walk(entry_dir):
            for filename in sub_files:
                mtimes.append(os.path.getmtime(os.path.join(sub_root, filename)))
        updated = datetime.fromtimestamp(max(mtimes)).strftime('%Y-%m-%d %H:%M') if mtimes else ''

        # Engine fields folded up from the retired bot config — the role now
        # carries its own model + image.
        provider = role_data.get("provider", "")
        model = role_data.get("model", "")
        model_label = f"{provider}: {model}" if provider and model else (model or provider)

        image_data = ""
        image_file = role_data.get("image", "")
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

        roles.append({
            "name": entry,
            "displayName": role_data.get("displayName", entry),
            "defaultLocation": role_data.get("defaultLocation", ""),
            "purpose": role_data.get("purpose", ""),
            "model": model_label,
            "image": image_data,
            "updated": updated,
        })
    return roles


@public
async def role_list() -> List[Dict[str, Any]]:
    """List roles (playable units) — config metadata only."""
    roles = _role_rows()
    await atlantis.client_data("Roles", roles)
    return roles


def role_default_location(role: str) -> Optional[str]:
    """Return a role-specific default location from config.json, if set."""
    location = _load_role_json(role).get("defaultLocation", "")
    return str(location).strip() or None


def role_entry_location(role: str) -> str:
    """Return the entry location for a role, or raise if not configured."""
    location = role_default_location(role)
    if not location:
        raise ValueError(
            f"No defaultLocation configured for role {role!r}. "
            f"Set defaultLocation in the role config.json."
        )
    return location


def _validate_role(role: str) -> None:
    """Validate a role folder"""
    if not os.path.isdir(os.path.join(_roles_dir(), role)):
        raise ValueError(f"Role folder not found: {role}")
