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


FACE_ID_ASKED = ("Waiting for Face ID: Hermai has asked {name}'s phone to confirm {what}, so it wasn't run yet. "
                 "Tell {name} to confirm it on their phone. Once they do, you'll be told to go ahead; then make "
                 "exactly this call again. Don't try any other way to do it.")


ALLOW = "allow"  # _face_id's answer for a call the phone approved


def _pre_tool_call(tool_name: str = "", args=None, tool_call_id: str = "", session_id: str = "", **_kwargs):
    if tool_name != "ha_call_service":
        return None
    try:
        verdict = _guard().verdict(tool_name, args, _settings(), call_id=tool_call_id)
        if verdict is None:
            return None
        phone = _face_id(args, session_id)
        if phone == ALLOW:
            return None
        return phone or verdict
    except Exception as e:  # Hermes skips a hook that raises, which would let the call through
        return {"action": "block", "message": f"Not allowed: Hermai's guard failed ({type(e).__name__}), so this wasn't run."}


def _confirmations():
    from hermes_constants import get_hermes_home
    return _load("hermes_hermai_confirm", "confirm.py").Confirmations(Path(get_hermes_home()) / "hermai" / "confirm.json")


def _face_id(args, session_id: str) -> dict | None:
    """On a turn from a phone whose person may do this and which has a Face ID key: ALLOW when that
    phone already approved exactly this call, else a block that asks the phone. None (the guard's own
    answer stands) on any other turn."""
    if not isinstance(args, dict) or not session_id:
        return None
    entry = _chats().entry_of_session(session_id)
    chat = str((entry or {}).get("chat") or "")
    if not chat.startswith("phone-") or not entry.get("person"):
        return None
    guard = _guard()
    what = guard.check(args, _settings().current())
    if what is None:
        return None
    people = _load("hermes_hermai_people", "people.py")
    device = _people().by_id(chat[len("phone-"):])
    if not device or device["person"] != entry["person"] or not device.get("face_id_key"):
        return None
    if not _people().may_secure(device["person"]):
        return None
    confirm = _load("hermes_hermai_confirm", "confirm.py")
    key = confirm.call_key(args)
    if _confirmations().take(session_id, key):
        return ALLOW
    _confirmations().request(session_id, device["id"], device["person"], key, what)
    return {"action": "block", "message": FACE_ID_ASKED.format(name=people.display_name(device["person"]), what=what)}


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
    speaker = entry.get("speaker")
    if isinstance(speaker, str) and speaker:
        speaker = _load("hermes_hermai_people", "people.py").display_name(speaker)
    return {"context": notes.household_note(str(entry.get("room") or ""),
                                            speaker=speaker if isinstance(speaker, str) else None)}


def _slash(args: str = "") -> str:
    words = (args or "").split()
    if words and words[0] == "pair":
        return _pair(words[1:])
    if words and words[0] == "phones":
        return _phones(words[1:])
    if words and words[0] == "restricted":
        return _restricted(words[1:])
    if words and words[0] == "voices":
        return _voices_cmd(words[1:])
    return _guard_status()


def _pair(words: list[str]) -> str:
    people = _load("hermes_hermai_people", "people.py")
    person = people.person_id(words[0]) if words else None
    if not person:
        return "Usage: /hermai pair <person>, like /hermai pair kayla"
    code, _expires = _people().start_pairing(person)
    lines = [f"Pairing code for {people.display_name(person)}'s phone, good for 15 minutes and once only:", "", code, "",
             "In the Hermai app, choose Pair this phone, enter the Hermes address and paste this code.", "",
             # Relative, so it opens on whatever address this dashboard was reached at; that page makes a
             # code of its own and shows it as a QR code with the address in it.
             f"Or scan a QR code instead: [open the pairing page](/api/plugins/hermai/pair?person={person})"]
    if person != people.OWNER:
        from hermes_constants import get_hermes_home
        if _load("hermes_hermai_voice", "voice.py").api_server() is None:
            reason = "Hermes' API server isn't set up, so Athena can't tell whose phone is speaking"
        else:
            reason = people.memory_closed(Path(get_hermes_home()) / "holonomic.json", person)
        if reason:
            lines.append(f"{people.display_name(person)}'s phone can pair, but can't talk to Athena yet: {reason}.")
    return "\n".join(lines)


def _restricted(words: list[str]) -> str:
    """Whether a person may unlock, disarm and open from their own phone, confirmed with Face ID."""
    people = _load("hermes_hermai_people", "people.py")
    person = people.person_id(words[0]) if words else None
    if not person or len(words) > 2 or (len(words) == 2 and words[1] not in ("on", "off")):
        return "Usage: /hermai restricted <person> [on|off], like /hermai restricted elliot on"
    name = people.display_name(person)
    if len(words) == 2:
        _people().set_may_secure(person, words[1] == "on")
    if _people().may_secure(person):
        return (f"{name} may unlock, disarm and open the garage from their own paired phone, confirmed with "
                "Face ID each time. Tablets and everything else still can't.")
    return f"{name} can't unlock, disarm or open the garage by voice, from any phone or tablet."


def _voices():
    from hermes_constants import get_hermes_home
    return _load("hermes_hermai_voices", "voices.py").Voices(Path(get_hermes_home()) / "hermai" / "voices.json")


def _herma_in(room_words: list[str]) -> tuple[str | None, str]:
    """The herma in the room named, or the only herma when none is named: ``(id, room)``, or
    ``(None, why not)``."""
    from hermes_constants import get_hermes_home
    hermas = _load("hermes_hermai_hermas", "hermas.py").Hermas(Path(get_hermes_home()) / "hermai" / "hermas.json").all()
    rooms = {hid: str(h.get("room") or "") for hid, h in hermas.items()}
    if not rooms:
        return None, "No hermas have said hello yet; open the Hermai app on a tablet first."
    wanted = " ".join(room_words).strip().lower()
    found = [hid for hid, room in rooms.items() if room.lower() == wanted] if wanted else list(rooms)
    if len(found) == 1:
        return found[0], rooms[found[0]]
    names = ", ".join(sorted(set(rooms.values())))
    if wanted:
        return None, f"No herma is in a room called {' '.join(room_words)}. The rooms are: {names}."
    return None, f"Say which room's herma, like /hermai voices learn elliot Kitchen. The rooms are: {names}."


def _quietly(fn) -> None:
    try:
        fn()
    except Exception:
        pass  # the herma tries again on its first recording, and says what went wrong


def _voices_cmd(words: list[str]) -> str:
    """Learning, listing and forgetting the voices the hermas know."""
    people = _load("hermes_hermai_people", "people.py")
    voices = _load("hermes_hermai_voices", "voices.py")
    store = _voices()
    usage = ("Usage: /hermai voices; /hermai voices learn <person> [room]; /hermai voices forget <person>; "
             "/hermai voices stop [room]")
    if not words:
        known = store.people()
        if not known:
            return ("No voices learned yet, so the hermas can't tell who's speaking. "
                    "/hermai voices learn <person> [room] teaches one.")
        lines = ["Voices the hermas know: " + ", ".join(people.display_name(p) for p in sorted(known)) + ".",
                 "Anyone else who speaks to a herma is a guest: nothing they say is remembered."]
        if _load("hermes_hermai_voice", "voice.py").api_server() is None:
            lines.append("But Hermes' API server isn't set up, so the hermas aren't using them yet (API_SERVER_KEY).")
        return "\n".join(lines)
    if words[0] == "learn" and len(words) >= 2:
        person = people.person_id(words[1])
        if not person or person == voices.GUEST:
            return usage
        hid, room = _herma_in(words[2:])
        if hid is None:
            return room
        if not voices.engine_installed():
            return (f"Hermes needs sherpa-onnx to learn voices. Run `hermes pm install --extra wake-sherpa`, "
                    f"then /hermai voices learn {person} again.")
        store.start_learning(hid, person)
        name = people.display_name(person)
        from hermes_constants import get_hermes_home
        # Fetch the voice model now (about 40 MB, once), so the first recording doesn't wait for it.
        embedder = voices.Embedder(Path(get_hermes_home()) / "cache" / "hermai")
        threading.Thread(target=lambda: _quietly(embedder._model), daemon=True).start()
        lines = [f"The {room} herma is ready to learn {name}'s voice. {name}, press talk and say anything you like, "
                 f"a sentence or two each time, {voices.SAMPLES} times. The herma tells you how many are left; "
                 f"none of it goes to Athena. It stops waiting in {voices.LEARN_TTL_S // 60} minutes."]
        if store.people().get(person):
            lines.append(f"Once it's done, this replaces the voice learned for {name} before.")
        reason = people.memory_closed(Path(get_hermes_home()) / "holonomic.json", person)
        if reason:
            lines.append(f"Until that's fixed, the hermas will know it's {name} but open no memories for them: {reason}.")
        return "\n".join(lines)
    if words[0] == "forget" and len(words) == 2:
        person = people.person_id(words[1])
        if not person:
            return usage
        if store.forget(person):
            return f"Forgot {people.display_name(person)}'s voice. To the hermas they're a guest now."
        return f"No voice is learned for {people.display_name(person)}."
    if words[0] == "stop":
        hid, room = _herma_in(words[1:])
        if hid is None:
            return room
        return f"The {room} herma stopped learning." if store.stop_learning(hid) else f"The {room} herma wasn't learning a voice."
    return usage


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
PERSON_ROUTES = ("/pair/claim", "/p/hello", "/p/settings", "/p/key", "/p/confirm", "/p/voice", "/p/ask", "/p/audio")


def register(ctx) -> None:
    ctx.register_hook("pre_tool_call", _pre_tool_call)
    ctx.register_hook("pre_llm_call", _pre_llm_call)
    ctx.register_command("hermai", handler=_slash,
                         description="Hermai: the guard's settings; pair <person> to pair a phone; phones to list them; "
                                     "restricted <person> on|off for Face ID unlocking from their phone; "
                                     "voices to learn who's speaking to the tablets")
    register_auth = getattr(ctx, "register_dashboard_auth_provider", None)
    if register_auth is None:
        return  # an older Hermes: phones can't pair, the tablets still work
    register_auth(_load("hermes_hermai_people", "people.py").make_provider(_people()))
    from hermes_cli.dashboard_auth.token_auth import register_token_route
    for path in PERSON_ROUTES:
        register_token_route("/api/plugins/hermai" + path)
