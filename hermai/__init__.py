"""Hermai: Athena as the voice of the house, one tablet (herma) per room.

For now this plugin holds the guard in front of Home Assistant (``guard.py``): before every
``ha_call_service`` it refuses, or asks a human about, anything that would unlock, disarm or open.
``/hermai`` shows the guard's settings.
"""
from __future__ import annotations

import importlib.util
import sys
import threading
from pathlib import Path

_GUARD = "hermes_hermai_guard"
_LOADING = threading.Lock()
_SETTINGS = None


def _guard():
    """guard.py, loaded once per process under a fixed name (as Petasos loads its modules)."""
    module = sys.modules.get(_GUARD)
    if module is not None:
        return module
    with _LOADING:
        module = sys.modules.get(_GUARD)
        if module is None:
            spec = importlib.util.spec_from_file_location(_GUARD, Path(__file__).with_name("guard.py"))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module = sys.modules.setdefault(_GUARD, module)
    return module


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
    ctx.register_command("hermai", handler=_slash, description="Show what Hermai's guard allows")
