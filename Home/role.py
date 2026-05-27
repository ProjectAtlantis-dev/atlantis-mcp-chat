"""Role tools

A *role* is a playable unit in the game. The lobby UI shows a roster of roles;
each one has a runtime slot assignment: empty, AI-driven, or human-driven. A
role is just config metadata (displayName, defaultLocation, defaultBot,
purpose); AI prompt material for a role-specific bot lives in
Game/Slots/<role>_<bot>/prompt.md.
"""

import atlantis
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from dynamic_functions.Home.common import _roles_dir

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
        roles.append({
            "name": entry,
            "displayName": role_data.get("displayName", entry),
            "defaultLocation": role_data.get("defaultLocation", ""),
            "defaultBot": role_data.get("defaultBot", ""),
            "purpose": role_data.get("purpose", ""),
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
