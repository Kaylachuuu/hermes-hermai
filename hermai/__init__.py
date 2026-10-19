"""Hermai: Athena as the voice of the house, one tablet (herma) per room.

- ``guard.py`` stands in front of Home Assistant: before every ``ha_call_service`` it refuses, or
  asks a human about, anything that would unlock, disarm or open. ``/hermai`` shows its settings.
- ``dashboard/plugin_api.py`` is the backend the hermas talk to (``/api/plugins/hermai/``), with
  ``voice.py`` running their turns with Athena and ``hermas.py`` keeping each tablet's room.
- The ``pre_llm_call`` hook tells Athena, on each turn from a herma, which room she's speaking in
  and that the tablet is shared.
"""
from __future__ import annotations

import importlib.util
import sys
import threading
from pathlib import Path

_LOADING = threading.Lock()
_SETTINGS = None
_CHATS = None


def _load(name: str, filename: str):
    """A module beside this file, loaded once per process under a fixed name (as Petasos loads its
    modules), so the dashboard routes and these hooks share it."""
    module = sys.modules.get(name)
    if module is not None:
        return module
    with _LOADING:
        module = sys.modules.get(name)
        if module is None:
            spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module = sys.modules.setdefault(name, module)
    return module


def _guard():
    return _load("hermes_hermai_guard", "guard.py")


def _settings():
    global _SETTINGS
    if _SETTINGS is None:
        from hermes_constants import get_hermes_home
        _SETTINGS = _guard().Settings(Path(get_hermes_home()) / "hermai" / "guard.json")
    return _SETTINGS


def _pre_tool_call(tool_name: str = "", args=None, tool_call_id: str = "", **_kwargs):
    if tool_name != "ha_call_service":
        return None
    try:
        return _guard().verdict(tool_name, args, _settings(), call_id=tool_call_id)
    except Exception as e:  # Hermes skips a hook that raises, which would let the call through
        return {"action": "block", "message": f"Not allowed: Hermai's guard failed ({type(e).__name__}), so this wasn't run."}


def _chats():
    global _CHATS
    if _CHATS is None:
        from hermes_constants import get_hermes_home
        _CHATS = _load("hermes_hermai_voice", "voice.py").Chats(Path(get_hermes_home()) / "hermai" / "chats.json")
    return _CHATS


def _pre_llm_call(session_id: str = "", parent_session_id: str = "", **_kwargs):
    """On a turn in a herma's chat, the room and shared-tablet note; on any other chat, nothing."""
    try:
        room = _chats().room_of_session(session_id, parent_session_id)
    except Exception:
        return None
    if room is None:
        return None
    return {"context": _load("hermes_hermai_hermas", "hermas.py").household_note(room)}


def _slash(_args: str = "") -> str:
    settings = _settings()
    values = settings.current()
    securing = "allowed" if values["allow_securing"] else "guarded too"
    unsafe = "refused" if values["mode"] == "block" else "asked about on Hermes' approval prompt"
    lines = [f"Hermai guard: unlocking, disarming and opening the garage are {unsafe}.",
             f"Locking, arming and closing: {securing}."]
    if values["guarded_entities"]:
        lines.append("Also guarded: " + ", ".join(values["guarded_entities"]))
    if values["guarded_scripts"]:
        lines.append("Guarded scripts and scenes: " + ", ".join(values["guarded_scripts"]))
    lines.append(f"Settings: {settings.path}" + ("" if settings.path.exists() else " (not created; defaults in use)"))
    if settings.problem:
        lines.append(f"Problem: {settings.problem}")
    return "\n".join(lines)


def register(ctx) -> None:
    ctx.register_hook("pre_tool_call", _pre_tool_call)
    ctx.register_hook("pre_llm_call", _pre_llm_call)
    ctx.register_command("hermai", handler=_slash, description="Show what Hermai's guard allows")
