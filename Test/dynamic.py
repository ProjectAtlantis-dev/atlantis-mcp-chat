import atlantis
import json
import logging
import os
import re
from datetime import datetime

logger = logging.getLogger("dynamic_function")


def _foobar_safe_id(value):
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", str(value or "").strip())
    if not safe:
        raise RuntimeError("Dynamic foobar requires a terminal key")
    return safe


def _foobar_display_path(parts):
    return "." if not parts else "./" + "/".join(parts)


def _foobar_state_path():
    terminal_key = _foobar_safe_id(atlantis.get_terminal_key())
    return os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "Data",
            "dynamic",
            "Test",
            "foobar",
            f"{terminal_key}.json",
        )
    )


def _foobar_load_state():
    state_path = _foobar_state_path()
    try:
        with open(state_path, "r", encoding="utf-8") as state_file:
            state = json.load(state_file)
    except FileNotFoundError:
        state = {}
    parts = state.get("path", [])
    return state_path, [str(part) for part in parts] if isinstance(parts, list) else []


def _foobar_save_state(state_path, parts):
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    state = {
        "terminal_key": atlantis.get_terminal_key(),
        "path": parts,
        "display_path": _foobar_display_path(parts),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    tmp_path = f"{state_path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as state_file:
        json.dump(state, state_file, indent=2)
        state_file.write("\n")
    os.replace(tmp_path, state_path)


def _foobar_entries(parts):
    if not parts:
        return [
            {"name": "colors", "type": "directory", "description": "Generated color directories"},
            {"name": "numbers", "type": "directory", "description": "Generated number directories"},
            {"name": "hello", "type": "tool", "description": "Say hello from the dynamic folder", "params": ["name"]},
            {"name": "whereami", "type": "tool", "description": "Show the provider-owned virtual path"},
        ]
    if parts == ["colors"]:
        return [
            {"name": name, "type": "directory", "description": f"Generated {name} directory"}
            for name in ("red", "green", "blue")
        ]
    if parts == ["numbers"]:
        return [
            {"name": str(number), "type": "directory", "description": f"Generated number {number}"}
            for number in range(1, 6)
        ]
    if len(parts) == 2 and parts[0] in ("colors", "numbers"):
        return [
            {"name": "describe", "type": "tool", "description": f"Describe {'/'.join(parts)}"},
            {"name": "whereami", "type": "tool", "description": "Show the provider-owned virtual path"},
        ]
    return []


def _foobar_child_names(parts):
    return {
        entry["name"]
        for entry in _foobar_entries(parts)
        if entry.get("type") == "directory"
    }


@dynamic
async def foobar(
    operation: str = "ls",
    path: str = ".",
    target: str = ".",
    args: list = None,
):
    """
    Provider-owned dynamic folder mounted at Test/foobar.

    Navigation state is persisted as readable JSON per Atlantis terminal.
    """
    args = args if isinstance(args, list) else []
    state_path, parts = _foobar_load_state()
    logger.info(
        "Dynamic foobar operation=%r path=%r target=%r state_path=%r parts=%r args=%r",
        operation,
        path,
        target,
        state_path,
        parts,
        args,
    )

    if operation == "ls":
        return {
            "displayPath": _foobar_display_path(parts),
            "entries": _foobar_entries(parts),
        }

    if operation == "cd":
        candidate = list(parts)
        for segment in str(target or ".").replace("\\", "/").split("/"):
            if not segment or segment == ".":
                continue
            if segment == "..":
                if candidate:
                    candidate.pop()
                    continue
                try:
                    os.remove(state_path)
                except FileNotFoundError:
                    pass
                return {"displayPath": "", "exit": True}
            if segment not in _foobar_child_names(candidate):
                raise ValueError(
                    f"Dynamic directory not found: "
                    f"{_foobar_display_path(candidate)}/{segment}"
                )
            candidate.append(segment)

        _foobar_save_state(state_path, candidate)
        return {"displayPath": _foobar_display_path(candidate)}

    if operation == "run":
        available_tools = {
            entry["name"]
            for entry in _foobar_entries(parts)
            if entry.get("type") != "directory"
        }
        if target not in available_tools:
            raise ValueError(
                f"Dynamic command not found in {_foobar_display_path(parts)}: {target}"
            )
        if target == "hello":
            name = str(args[0]) if args else "world"
            return f"Hello, {name}, from Test/foobar."
        if target == "whereami":
            return _foobar_display_path(parts)
        if target == "describe":
            return {
                "path": _foobar_display_path(parts),
                "value": parts[-1],
                "kind": parts[0],
            }

    raise ValueError(f"Unsupported dynamic folder operation: {operation}")
