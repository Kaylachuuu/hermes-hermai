"""Hermai: Athena as the voice of the house, one tablet (herma) per room.

- ``guard.py`` stands in front of Home Assistant: before every ``ha_call_service`` it refuses, or
  asks a human about, anything that would unlock, disarm or open. ``/hermai`` shows its settings.
- ``dashboard/plugin_api.py`` is the backend the hermas talk to (``/api/plugins/hermai/``), with
  ``voice.py`` running their turns with Athena and ``hermas.py`` keeping each tablet's room.
- The ``pre_llm_call`` hook tells Athena, on each turn from a herma, which room she's speaking in
  and that the tablet is shared; on a turn from a paired phone, whose phone it is.
- ``people.py`` is Hermai's own sign-in for people's phones: ``/hermai pair <person>`` makes a
  one-time code, and the phone trades it for a token that opens Hermai's person routes only.
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


def _people():
    from hermes_constants import get_hermes_home
    return _load("hermes_hermai_people", "people.py").shared(Path(get_hermes_home()) / "hermai" / "people.json")


def _pre_llm_call(session_id: str = "", parent_session_id: str = "", **_kwargs):
    """On a turn in a herma's or a paired phone's chat, the note about where it came from; on any
    other chat, nothing."""
    try:
        entry = _chats().entry_of_session(session_id, parent_session_id)
    except Exception:
        return None
    if entry is None:
        return None
    notes = _load("hermes_hermai_hermas", "hermas.py")
    if entry.get("person"):
        name = _load("hermes_hermai_people", "people.py").display_name(entry["person"])
        return {"context": notes.personal_note(name, entry.get("device") or "phone",
                                                       short=bool(entry.get("short")))}
    return {"context": notes.household_note(str(entry.get("room") or ""))}


def _slash(args: str = "") -> str:
    words = (args or "").split()
    if words and words[0] == "pair":
        return _pair(words[1:])
    if words and words[0] == "phones":
        return _phones(words[1:])
    return _guard_status()


def _pair(words: list[str]) -> str:
    people = _load("hermes_hermai_people", "people.py")
    person = people.person_id(words[0]) if words else None
    if not person:
        return "Usage: /hermai pair <person>, like /hermai pair kayla"
    code, _expires = _people().start_pairing(person)
    lines = [f"Pairing code for {people.display_name(person)}'s phone, good for 15 minutes and once only:", "", code, "",
             "In the Hermai app, choose Pair this phone, enter the Hermes address and paste this code."]
    if person != people.OWNER:
        from hermes_constants import get_hermes_home
        if _load("hermes_hermai_voice", "voice.py").api_server() is None:
            reason = "Hermes' API server isn't set up, so Athena can't tell whose phone is speaking"
        else:
            reason = people.memory_closed(Path(get_hermes_home()) / "holonomic.json", person)
        if reason:
            lines.append(f"{people.display_name(person)}'s phone can pair, but can't talk to Athena yet: {reason}.")
    return "\n".join(lines)


def _phones(words: list[str]) -> str:
    people = _load("hermes_hermai_people", "people.py")
    if words[:1] == ["remove"] and len(words) == 2:
        return "Removed." if _people().revoke(words[1]) else f"No paired phone with the id {words[1]}."
    devices = _people().devices()
    if not devices:
        return "No phones are paired with Hermai. /hermai pair <person> makes a pairing code."
    lines = ["Paired phones (/hermai phones remove <id> to unpair one):"]
    for d in sorted(devices, key=lambda d: d.get("paired", 0)):
        lines.append(f"  {d['id']}  {people.display_name(d.get('person') or '?')}: {d.get('name') or 'Phone'}")
    return "\n".join(lines)


def _guard_status() -> str:
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


# Routes a paired phone's token (or a pairing code, for the first) opens. Exact paths only: anything
# else under /api/plugins/hermai/ still needs a dashboard sign-in.
PERSON_ROUTES = ("/pair/claim", "/p/hello", "/p/settings", "/p/voice", "/p/ask", "/p/audio")


def register(ctx) -> None:
    ctx.register_hook("pre_tool_call", _pre_tool_call)
    ctx.register_hook("pre_llm_call", _pre_llm_call)
    ctx.register_command("hermai", handler=_slash,
                         description="Hermai: the guard's settings; pair <person> to pair a phone; phones to list them")
    register_auth = getattr(ctx, "register_dashboard_auth_provider", None)
    if register_auth is None:
        return  # an older Hermes: phones can't pair, the tablets still work
    register_auth(_load("hermes_hermai_people", "people.py").make_provider(_people()))
    from hermes_cli.dashboard_auth.token_auth import register_token_route
    for path in PERSON_ROUTES:
        register_token_route("/api/plugins/hermai" + path)
