"""Game state tools"""

import atlantis
import json
import os
import re
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

from dynamic_functions.Home.common import home_path, _read_json, _write_json
from dynamic_functions.Home.location import _location_rows

from dynamic_functions.Home.bot import _bot_rows
from dynamic_functions.Home.term import term_video, term_video_file


# ---------------------------------------------------------------------------
# Game data directory + membership
# ---------------------------------------------------------------------------

def _safe_id(value: str, label: str = "id") -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", str(value or "").strip())
    if not safe:
        raise ValueError(f"Cannot use an empty {label}")
    return safe


def game_dir(game_key: str) -> str:
    """Get a game data directory path"""
    return home_path("Data", "games", _safe_id(game_key, "game_key"))


def require_game_dir(game_key: str) -> str:
    """Get an existing game data directory"""
    path = game_dir(game_key)
    if not os.path.isdir(path):
        raise RuntimeError(f"Invalid game '{game_key}'")
    return path


def create_game_dir(game_key: str) -> str:
    """Create a game data directory"""
    path = game_dir(game_key)
    os.makedirs(path, exist_ok=False)
    return path


def _game_roster_scene(meta: Dict[str, Any]) -> Optional[str]:
    """Return the chosen roster scene, if assigned."""
    roster = meta.get("roster") or {}
    if isinstance(roster, dict):
        scene = str(roster.get("scene", "") or "").strip()
        if scene:
            return scene
    return None


def add_caller_membership(members: Dict[str, Any]) -> Dict[str, Any]:
    """Record the calling session in a members map, keyed by session key.

    The one place a membership record is shaped — used by game_new for the
    creator and game_join for everyone else, so the two stay identical. Raises
    if there is no session to enroll, or if this session/shell is already
    enrolled; returns the same map for chaining.
    """
    session_key = atlantis.get_session_key()
    if not session_key:
        raise RuntimeError("No session key in this call context")
    if session_key in members:
        raise RuntimeError(f"Session is already a member: {session_key}")

    shell = atlantis.get_caller_shell_path() or ""
    if shell and any(rec.get("shell") == shell for rec in members.values()):
        raise RuntimeError(f"Shell is already a member: {shell}")

    members[session_key] = {
        "sid": atlantis.get_caller() or "",
        "user_game_id": atlantis.get_user_game_id(),
        "shell": shell,
        "joined_at": datetime.now().isoformat(timespec="seconds"),
    }
    return members


def require_membership(game_key: str) -> str:
    """Authorize the calling session against a game; return its data dir.

    The single gate every game-scoped tool calls first: the game must exist and
    the caller's session must already be a member — seeded by game_new for the
    creator, or recorded by game_join for everyone else. Raises for an unknown
    game or a non-member session; never returns for an unauthorized caller.
    """
    path = require_game_dir(game_key)
    session_key = atlantis.get_session_key()
    if not session_key:
        raise RuntimeError("No session key in this call context")
    meta = _read_json(os.path.join(path, "game.json")) or {}
    members = meta.get("members") or {}
    if session_key not in members:
        raise PermissionError(f"Session is not a member of game '{game_key}'")
    return path


@button("New Chat")
@public
async def game_button():
    """Create a new chat session"""
    settings = await atlantis.client_command("@game_init")


@public
async def game_init():
    """Create a new game, then capture its keys server-side via the cursor."""
    keys = await game_new()
    await atlantis.client_command("/cursor join", keys)

    callbacks = await atlantis.client_command("/callback list")
    chat_row = next(row for row in callbacks if row["mode"] == "chat")

    if not chat_row["toolPath"]:
        matches = await atlantis.client_command("/tool find chat")
        chat_tool = matches[0]
        await atlantis.client_command(f"/callback set chat {chat_tool['searchTerm']}")

        callbacks = await atlantis.client_command("/callback list")
        chat_row = next(row for row in callbacks if row["mode"] == "chat")

    await atlantis.client_log(
        f"chat callback: toolPath={chat_row['toolPath']!r} filename={chat_row['filename']!r}"
    )

    #await term_video("https://pub-59cb84bebe804fd1b3257bb6c283a2b3.r2.dev/notLove_mobile.mp4")


@public
async def game_video(video: str) -> None:
    """Play the named game background video in the terminal."""
    await term_video(f"https://pub-59cb84bebe804fd1b3257bb6c283a2b3.r2.dev/{video}")


@public
async def game_video_file(video_path: str) -> None:
    """Play a local game background video file in the terminal."""
    if not os.path.isabs(video_path):
        video_path = os.path.join(os.path.dirname(__file__), video_path)
    await term_video_file(video_path)


@public
async def game_background() -> None:
    """Set the game background image."""
    await atlantis.set_background(
        os.path.join(os.path.dirname(__file__), "builder.jpg"),
        vertical_align="75%",
    )


@public
async def game_new() -> Dict[str, Any]:
    """Create a new game session"""
    for _ in range(10):
        game_key = uuid.uuid4().hex
        data_dir = game_dir(game_key)
        if not os.path.exists(data_dir):
            break
    else:
        raise RuntimeError("Unable to allocate a unique game_key")

    data_dir = create_game_dir(game_key)
    join_password = uuid.uuid4().hex
    _write_json(os.path.join(data_dir, 'game.json'), {
        'join_password': join_password,
        'owner': atlantis.get_caller() or '',
        'user_game_id': atlantis.get_user_game_id(),
        'members': add_caller_membership({}),
    })


    # Register the chat callback bound to this game_key so it survives restart
    # via the boot-time re-registration scan.
    # await atlantis.client_command(f'/callback set chat chat_callback {game_key}')

    await atlantis.client_log(f"Game created: {game_key}")
    await game_background()

    return {
        "game_key": game_key,
        "join_password": join_password,
    }


@public
async def game_list() -> list:
    """List existing games, newest first"""
    games_root = home_path("Data", "games")
    if not os.path.isdir(games_root):
        return []
    entries = []
    for name in os.listdir(games_root):
        path = os.path.join(games_root, name)
        if not os.path.isdir(path):
            continue
        try:
            ts = os.path.getctime(path)
        except OSError:
            continue
        meta = _read_json(os.path.join(path, 'game.json')) or {}
        entries.append({
            "game_key": name,
            "user_game_id": meta.get("user_game_id"),
            "owner": meta.get("owner", ""),
            "roster": _game_roster_scene(meta) or "",
            "created": datetime.fromtimestamp(ts).isoformat(timespec="seconds"),
            "_ts": ts,
        })
    entries.sort(key=lambda e: e["_ts"], reverse=True)
    for e in entries:
        del e["_ts"]
    return entries


@public
async def game_show(game_key: str) -> dict:
    """Show a game's status. The owner sees full detail (join password + members);
    everyone else sees only owner, member count, and created time."""
    path = require_game_dir(game_key)
    meta = _read_json(os.path.join(path, 'game.json')) or {}
    owner = meta.get("owner", "")
    members = meta.get("members") or {}
    created = datetime.fromtimestamp(os.path.getctime(path)).isoformat(timespec="seconds")
    roster = _game_roster_scene(meta)

    if atlantis.get_caller() != owner:
        sids = sorted({rec.get("sid", "") for rec in members.values() if rec.get("sid")})
        return {
            "game_key": game_key,
            "owner": owner,
            "roster": roster,
            "members": sids,
            "created": created,
        }

    return {
        "game_key": game_key,
        "user_game_id": meta.get("user_game_id"),
        "owner": owner,
        "roster": roster,
        "join_password": meta.get("join_password", ""),
        "members": [
            {
                "session_key": session_key,
                "sid": rec.get("sid", ""),
                "shell": rec.get("shell", ""),
                "user_game_id": rec.get("user_game_id"),
                "joined_at": rec.get("joined_at", ""),
            }
            for session_key, rec in members.items()
        ],
        "created": created,
    }


@public
async def game_password(game_key: str, new_password: str) -> None:
    """Change a game's join password. Only the owner may do this."""
    if not new_password:
        raise ValueError("new_password required")

    path = require_game_dir(game_key)
    meta = _read_json(os.path.join(path, 'game.json')) or {}
    if atlantis.get_caller() != meta.get("owner", ""):
        raise PermissionError("Only the owner may change the password")

    meta['join_password'] = new_password
    _write_json(os.path.join(path, 'game.json'), meta)
    await atlantis.client_log(f"Password to game {game_key} was changed")


@public
async def game_join_interactive(game_key: str) -> Dict[str, Any]:
    """Prompt the caller for the join password, then call game_join."""
    from dynamic_functions.Home.modal import modal_string

    if not game_key:
        raise ValueError("game_key required")
    password = await modal_string(
        f"Enter game password:",
        submit_label="Join",
        title=f"Game {game_key}",
        submitting_label="Joining...",
        empty_error="Enter the password to continue.",
        input_type="password",
        autocomplete="current-password",
    )
    if password is None:
        return {"cancelled": True}
    return await game_join(game_key, password)

# % game list

# % game show



@button("Join Other Chat")
@public
async def game_join_interactive_latest() -> Dict[str, Any]:
    """Prompt for the password to join the owner's most recently created game."""
    owner = str(atlantis.get_default_owner() or "").strip()
    if not owner:
        raise RuntimeError("No default owner in this call context")

    games = await game_list()
    owned_games = [game for game in games if game.get("owner") == owner]
    if not owned_games:
        raise RuntimeError(f"No games exist for owner {owner!r}")
    return await game_join_interactive(owned_games[0]["game_key"])


@public
async def game_join(game_key: str, password: str) -> Dict[str, Any]:
    """Join a specific game by its password and enroll the caller."""
    if not game_key:
        raise ValueError("game_key required")
    if not password:
        raise ValueError("Password required")

    data_dir = require_game_dir(game_key)
    meta = _read_json(os.path.join(data_dir, 'game.json')) or {}
    if meta.get('join_password') != password:
        raise ValueError("Incorrect password")

    add_caller_membership(meta.setdefault('members', {}))
    _write_json(os.path.join(data_dir, 'game.json'), meta)
    await atlantis.client_log(
        f"✅ {atlantis.get_caller() or atlantis.get_session_key()} joined game {game_key}"
    )
    #await game_background()
    #await game_init(game_key)
    return {"game_key": game_key}


@public
async def game_rejoin(game_key: str):
    """Rejoin a game without a password — allowed only if the caller's sid is already a member.

    The reconnect path: a returning sid on a fresh session registers that session
    as a new member entry. No-op if this session is already enrolled. A sid that
    was never a member must use game_join with the password instead.
    """
    path = require_game_dir(game_key)
    meta = _read_json(os.path.join(path, 'game.json')) or {}
    members = meta.get('members') or {}

    caller_sid = atlantis.get_caller()
    if not caller_sid:
        raise RuntimeError("No caller identity in this call context")
    if caller_sid not in {rec.get('sid') for rec in members.values()}:
        raise PermissionError(f"Not a member of game '{game_key}' — password required to join")

    session_key = atlantis.get_session_key()
    if session_key not in members:
        add_caller_membership(members)
    rec = members[session_key]
    rec["rejoined_at"] = datetime.now().isoformat(timespec="seconds")
    rec["rejoin_count"] = int(rec.get("rejoin_count", 0)) + 1
    meta['members'] = members
    _write_json(os.path.join(path, 'game.json'), meta)
    await atlantis.client_log(f"✅ {caller_sid} rejoined game {game_key}")
    #await game_background()
    #await game_init(game_key)
    #return {"game_key": game_key}


@visible
async def game_overview(game_key: str) -> None:
    """Show the game state diagram — scenes, roster, bots, locations, and cameras."""
    from dynamic_functions.Home.camera import _camera_rows
    from dynamic_functions.Home.roster import _number_duplicate_display_names, _scene_roster_rows
    from dynamic_functions.Home.scene import _load_scene, _scene_names
    data_dir = require_membership(game_key)

    meta = _read_json(os.path.join(data_dir, "game.json")) or {}
    roster_scene = _game_roster_scene(meta) or ""
    bot_rows = _bot_rows()
    loc_rows = _location_rows()
    camera_rows = _camera_rows(game_key)
    scene_names = _scene_names()
    scene_rows = [
        {"name": scene, "slots": len(_load_scene(scene))}
        for scene in scene_names
    ]
    roster_rows = []
    for scene_name in scene_names:
        scene_roster_rows = _scene_roster_rows(scene_name)
        _number_duplicate_display_names(scene_roster_rows)
        roster_rows.extend({
            "scene_name": scene_name,
            **row,
        } for row in scene_roster_rows)

    # Build an HTML table
    def _trunc(s, n=40):
        s = str(s or "")
        return s[:n] if len(s) > n else s

    def _esc(s):
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    uid = uuid.uuid4().hex[:8]

    def _table(entity_id, title, headers, rows, dynamic=False, row_classes=None, tone=""):
        """Build one entity table. row_classes, if given, is a per-row CSS class."""
        scoped_id = f"{entity_id}-{uid}"
        cls = f"er-entity-{uid}"
        if dynamic:
            cls += f" er-dynamic-{uid}"
        if tone:
            cls += f" er-tone-{tone}-{uid}"
        h = "".join(f"<th>{_esc(c)}</th>" for c in headers)
        body = ""
        for i, row in enumerate(rows):
            rc = row_classes[i] if row_classes else ""
            tr = f'<tr class="{rc}">' if rc else "<tr>"
            body += tr + "".join(f"<td>{_esc(v)}</td>" for v in row) + "</tr>"
        if not rows:
            body = f'<tr><td colspan="{len(headers)}" style="color:#888;font-style:italic">empty</td></tr>'
        return (
            f'<div class="{cls}" id="{scoped_id}">'
            f'<div class="er-title-{uid}">{_esc(title)}</div>'
            f'<table><tr>{h}</tr>{body}</table></div>'
        )

    tables = []
    tables.append(_table("ent-game", "GAME", ["key", "roster_scene"], [[game_key, roster_scene]], dynamic=True))
    tables.append(_table("ent-scene", "SCENE", ["name", "slots"],
        [[s["name"], s["slots"]] for s in scene_rows]))
    tables.append(_table("ent-roster", "ROSTER", ["scene_name", "key", "displayName", "bot_sid", "ai"],
        [[r.get("scene_name", ""), r.get("key", ""), r.get("displayName", ""), r.get("bot_sid", ""), r.get("ai", "")] for r in roster_rows],
        dynamic=True,
        tone="green"))
    tables.append(_table("ent-bot", "BOT", ["sid", "displayName", "defaultLocation", "model"],
        [[b["sid"], b["displayName"], b["defaultLocation"], b.get("model", "")] for b in bot_rows]))
    tables.append(_table("ent-location", "LOCATION", ["name", "displayName", "parent", "connects_to", "description"],
        [[l["name"], l["displayName"], l.get("parent", ""), l["connects_to"], _trunc(l.get("description", ""))] for l in loc_rows],
        row_classes=["" if l["is_leaf"] else f"er-nonleaf-{uid}" for l in loc_rows]))
    tables.append(_table("ent-camera", "CAMERA", ["location", "terminal"],
        [[c["location"], c["terminal"]] for c in camera_rows], dynamic=True))

    # Relationships
    relationships = [
        (f"ent-game-{uid}", f"ent-roster-{uid}", "has roster"),
        (f"ent-game-{uid}", f"ent-camera-{uid}", "has cameras"),
        (f"ent-roster-{uid}", f"ent-scene-{uid}", "scene_name"),
        (f"ent-roster-{uid}", f"ent-bot-{uid}", "bot_sid"),
        (f"ent-location-{uid}", f"ent-location-{uid}", "connects to"),
        (f"ent-location-{uid}", f"ent-location-{uid}", "parent"),
        (f"ent-location-{uid}", f"ent-bot-{uid}", "defaultLocation"),
        (f"ent-location-{uid}", f"ent-camera-{uid}", "location"),
    ]

    rels_json = json.dumps(relationships)

    html = f"""
<style>
  #er-wrapper-{uid} {{
    position: relative;
    padding: 24px;
    width: 100%;
    box-sizing: border-box;
  }}
  #er-wrapper-{uid} .er-entity-{uid} {{
    min-width: 150px;
  }}
  #er-wrapper-{uid} #er-stage-{uid} {{
    position: relative;
  }}
  #er-wrapper-{uid} #er-stage-{uid}.er-measuring-{uid} {{
    display: flex;
    flex-wrap: wrap;
    gap: 24px;
    align-items: flex-start;
  }}
  #er-wrapper-{uid} #er-stage-{uid}.er-laid-out-{uid} .er-entity-{uid} {{
    position: absolute;
  }}
  #er-wrapper-{uid} .er-entity-{uid} {{
    background: #1e1e2e;
    border: 1px solid #555;
    border-radius: 6px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
  }}
  #er-wrapper-{uid} .er-title-{uid} {{
    background: #3b3b5c;
    color: #e0e0ff;
    font-weight: bold;
    padding: 6px 10px;
    text-align: center;
    border-radius: 6px 6px 0 0;
    font-size: 13px;
    letter-spacing: 1px;
  }}
  #er-wrapper-{uid} .er-dynamic-{uid} {{
    background: #1e2e22;
    border-color: #4a7a5a;
  }}
  #er-wrapper-{uid} .er-dynamic-{uid} .er-title-{uid} {{
    background: #2f5c42;
    color: #d0ffe0;
  }}
  #er-wrapper-{uid} .er-entity-{uid} table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
    color: #ccc;
  }}
  #er-wrapper-{uid} .er-entity-{uid} th {{
    background: #2a2a40;
    color: #aaa;
    padding: 4px 8px;
    text-align: left;
    border-bottom: 1px solid #444;
    font-weight: normal;
    font-size: 11px;
  }}
  #er-wrapper-{uid} .er-dynamic-{uid} th {{
    background: #223a2c;
    color: #a8c8b0;
  }}
  #er-wrapper-{uid} .er-tone-green-{uid} {{
    background: #16281d;
    border-color: #3f8f58;
  }}
  #er-wrapper-{uid} .er-tone-green-{uid} .er-title-{uid} {{
    background: #27613b;
    color: #d8ffe1;
  }}
  #er-wrapper-{uid} .er-tone-green-{uid} th {{
    background: #203827;
    color: #a7d8b4;
  }}
  #er-wrapper-{uid} .er-tone-orange-{uid} {{
    background: #302114;
    border-color: #b36a2c;
  }}
  #er-wrapper-{uid} .er-tone-orange-{uid} .er-title-{uid} {{
    background: #8b4b1f;
    color: #ffe1c2;
  }}
  #er-wrapper-{uid} .er-tone-orange-{uid} th {{
    background: #442b18;
    color: #e5b083;
  }}
  #er-wrapper-{uid} .er-entity-{uid} td {{
    padding: 3px 8px;
    border-bottom: 1px solid #333;
    white-space: pre-line;
  }}
  #er-wrapper-{uid} .er-entity-{uid} tr:last-child td {{
    border-bottom: none;
  }}
  #er-wrapper-{uid} .er-nonleaf-{uid} td {{
    color: #666;
    font-style: italic;
  }}
  #er-wrapper-{uid} #er-svg-{uid} {{
    position: absolute;
    top: 0;
    left: 0;
    pointer-events: none;
    overflow: visible;
  }}
</style>
<div class="er-wrapper" id="er-wrapper-{uid}">
  <div id="er-stage-{uid}" class="er-measuring-{uid}">
    {''.join(tables)}
    <svg id="er-svg-{uid}" xmlns="http://www.w3.org/2000/svg"></svg>
  </div>
</div>
"""

    await atlantis.client_html(html)

    # Load ELK with client_script
    elk_loader = (
        'if (!window.ELK) {'
        '  var resolve; var p = new Promise(function(r) { resolve = r; });'
        '  var xhr = new XMLHttpRequest();'
        '  xhr.open("GET", "https://cdn.jsdelivr.net/npm/elkjs@0.9.3/lib/elk.bundled.js", true);'
        '  xhr.onload = function() {'
        '    if (xhr.status === 200) {'
        '      var _define = window.define;'
        '      try { window.define = undefined; (0, eval)(xhr.responseText); }'
        '      catch(e) { console.error("[ER] ELK eval failed", e); }'
        '      finally { window.define = _define; }'
        '    }'
        '    resolve();'
        '  };'
        '  xhr.onerror = function() { console.error("[ER] failed to fetch elkjs"); resolve(); };'
        '  xhr.send();'
        '  await p;'
        '}'
    )
    await atlantis.client_script(f'(async function() {{ {elk_loader} }})()')

    # Run the ELK layout
    layout_script = (
        f'(async function() {{'
        f'  await new Promise(function(r) {{ requestAnimationFrame(function() {{ requestAnimationFrame(r); }}); }});'
        f'  var uid = "{uid}";'
        f'  var rels = {rels_json};'
        f'  var stage = document.getElementById("er-stage-" + uid);'
        f'  var svg = document.getElementById("er-svg-" + uid);'
        f'  if (!stage || !svg) {{ console.error("[ER] stage/svg not found", uid); return; }}'
        f'  if (!window.ELK) {{ console.error("[ER] ELK not loaded"); return; }}'
        f'  var SVG_NS = "http://www.w3.org/2000/svg";'
        f'  var entities = stage.querySelectorAll(".er-entity-{uid}");'
        f'  var wrapper = document.getElementById("er-wrapper-" + uid);'
        f'  var availW = wrapper ? wrapper.clientWidth - 48 : 800;'
        f'  var nodes = [];'
        f'  entities.forEach(function(el) {{'
        f'    var r = el.getBoundingClientRect();'
        f'    nodes.push({{ id: el.id, width: Math.ceil(r.width), height: Math.ceil(r.height) }});'
        f'  }});'
        f'  var edges = rels.map(function(rel, i) {{'
        f'    return {{'
        f'      id: "e" + i,'
        f'      sources: [rel[0]],'
        f'      targets: [rel[1]],'
        f'      labels: [{{ text: rel[2], width: rel[2].length * 6 + 4, height: 12 }}]'
        f'    }};'
        f'  }});'
        f'  var graph = {{'
        f'    id: "root",'
        f'    layoutOptions: {{'
        f'      "elk.algorithm": "layered",'
        f'      "elk.direction": "DOWN",'
        f'      "elk.edgeRouting": "ORTHOGONAL",'
        f'      "elk.spacing.nodeNode": "60",'
        f'      "elk.spacing.edgeNode": "25",'
        f'      "elk.spacing.edgeEdge": "15",'
        f'      "elk.layered.spacing.nodeNodeBetweenLayers": "80",'
        f'      "elk.layered.spacing.edgeNodeBetweenLayers": "30",'
        f'      "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",'
        f'      "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES"'
        f'    }},'
        f'    children: nodes,'
        f'    edges: edges'
        f'  }};'
        f'  var elk = new ELK();'
        f'  elk.layout(graph).then(function(g) {{'
        f'    stage.classList.remove("er-measuring-{uid}");'
        f'    stage.classList.add("er-laid-out-{uid}");'
        f'    var W = Math.ceil(g.width) + 20;'
        f'    var H = Math.ceil(g.height) + 20;'
        f'    var useW = Math.max(W, availW);'
        f'    var scaleX = W > 0 ? useW / W : 1;'
        f'    g.children.forEach(function(n) {{'
        f'      var el = document.getElementById(n.id);'
        f'      if (!el) return;'
        f'      el.style.left = Math.round(n.x * scaleX) + "px";'
        f'      el.style.top = n.y + "px";'
        f'      el.style.width = Math.round(n.width * scaleX) + "px";'
        f'    }});'
        f'    stage.style.width = useW + "px";'
        f'    stage.style.height = H + "px";'
        f'    svg.setAttribute("width", useW);'
        f'    svg.setAttribute("height", H);'
        f'    svg.setAttribute("viewBox", "0 0 " + useW + " " + H);'
        f'    while (svg.firstChild) svg.removeChild(svg.firstChild);'
        f'    (g.edges || []).forEach(function(e) {{'
        f'      (e.sections || []).forEach(function(sec) {{'
        f'        var pts = [sec.startPoint].concat(sec.bendPoints || []).concat([sec.endPoint]);'
        f'        var d = "M " + pts.map(function(p) {{ return Math.round(p.x * scaleX) + "," + p.y; }}).join(" L ");'
        f'        var path = document.createElementNS(SVG_NS, "path");'
        f'        path.setAttribute("d", d);'
        f'        path.setAttribute("fill", "none");'
        f'        path.setAttribute("stroke", "#888");'
        f'        path.setAttribute("stroke-width", "1.5");'
        f'        svg.appendChild(path);'
        f'      }});'
        f'      (e.labels || []).forEach(function(lbl) {{'
        f'        var bg = document.createElementNS(SVG_NS, "rect");'
        f'        bg.setAttribute("x", Math.round(lbl.x * scaleX) - 2);'
        f'        bg.setAttribute("y", lbl.y - 1);'
        f'        bg.setAttribute("width", lbl.width + 4);'
        f'        bg.setAttribute("height", lbl.height + 2);'
        f'        bg.setAttribute("fill", "#1e1e2e");'
        f'        bg.setAttribute("opacity", "0.85");'
        f'        svg.appendChild(bg);'
        f'        var t = document.createElementNS(SVG_NS, "text");'
        f'        t.setAttribute("x", Math.round(lbl.x * scaleX));'
        f'        t.setAttribute("y", lbl.y + lbl.height - 2);'
        f'        t.setAttribute("fill", "#aaa");'
        f'        t.setAttribute("font-size", "10");'
        f'        t.setAttribute("font-family", "sans-serif");'
        f'        t.textContent = lbl.text;'
        f'        svg.appendChild(t);'
        f'      }});'
        f'    }});'
        f'  }}).catch(function(err) {{ console.error("[ER] ELK layout failed", err); }});'
        f'}})()')

    await atlantis.client_script(layout_script)
