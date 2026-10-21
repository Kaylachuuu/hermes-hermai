"""Hermai routes, mounted at /api/plugins/hermai/.

The dashboard's own login decides who may reach these routes; a herma signs in once and sends its
session token like any other dashboard client. Nothing here touches Petasos's routes or files.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

router = APIRouter()

MAX_SPEECH_BYTES = 10 * 1024 * 1024  # about five minutes of 16 kHz mono WAV

_LOADING = threading.Lock()
_STATE_LOCK = threading.Lock()  # apart from _LOADING, which _state() needs while holding this
_STATE = None


def _load(name: str, filename: str):
    """A module beside this folder, loaded once per process under a fixed name, published only
    once fully loaded (routes run on several threads at once)."""
    module = sys.modules.get(name)
    if module is not None:
        return module
    with _LOADING:
        module = sys.modules.get(name)
        if module is None:
            spec = importlib.util.spec_from_file_location(name, Path(__file__).parent.parent / filename)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module = sys.modules.setdefault(name, module)
    return module


def _voice():
    return _load("hermes_hermai_voice", "voice.py")


def _hermas_module():
    return _load("hermes_hermai_hermas", "hermas.py")


def _state():
    """The hermas, their chats and the spoken replies waiting to be fetched, under <Hermes home>/hermai/."""
    global _STATE
    with _STATE_LOCK:
        if _STATE is None:
            from hermes_constants import get_hermes_home
            root = Path(get_hermes_home()) / "hermai"
            voice = _voice()
            _STATE = (_hermas_module().Hermas(root / "hermas.json"), voice.Chats(root / "chats.json"), voice.Replies())
        return _STATE


def _known(herma: str) -> tuple[str, str]:
    """The herma's id and room, or 404 if it hasn't said hello."""
    hermas = _state()[0]
    hid = _hermas_module().herma_id(herma)
    entry = hermas.get(hid) if hid else None
    if entry is None:
        raise HTTPException(status_code=404, detail="unknown herma; it says hello first")
    hermas.seen(hid)
    return hid, entry.get("room") or ""


@router.post("/hello")
def hello(body: dict) -> dict:
    """A herma starting up: its id and room in, its settings out."""
    mod = _hermas_module()
    hid = mod.herma_id(body.get("herma") if isinstance(body, dict) else None)
    room = mod.room_name(body.get("room") if isinstance(body, dict) else None)
    if not hid:
        raise HTTPException(status_code=400, detail=f"herma is an id of 1 to {mod.HERMA_ID_MAX} letters, digits, - _ or .")
    if not room:
        raise HTTPException(status_code=400, detail=f"room is a name of 1 to {mod.ROOM_MAX} characters")
    entry = _state()[0].hello(hid, room)
    return {"herma": hid, "room": entry["room"], "listening": entry["listening"], "agent": "Athena"}


@router.post("/voice")
async def voice(request: Request, herma: str = "") -> dict:
    """A recording in (WAV body); what was heard, Athena's reply and an id for its audio out."""
    hid, room = _known(herma)
    audio = await request.body()
    if not audio:
        raise HTTPException(status_code=400, detail="empty recording")
    if len(audio) > MAX_SPEECH_BYTES:
        raise HTTPException(status_code=413, detail="recording too long")
    v = _voice()
    try:
        heard = await asyncio.get_running_loop().run_in_executor(None, v.transcribe, audio)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"couldn't transcribe: {exc}"[:300]) from None
    if not heard:
        return {"heard": "", "reply": "", "audio": None}
    return {"heard": heard, **await _turn(heard, hid, room)}


@router.post("/ask")
async def ask(body: dict, herma: str = "") -> dict:
    """Typed words in; Athena's reply and an id for its audio out."""
    hid, room = _known(herma)
    text = body.get("text") if isinstance(body, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(status_code=400, detail="text required")
    return {"heard": text.strip(), **await _turn(text.strip(), hid, room)}


async def _turn(text: str, herma: str, room: str) -> dict:
    v = _voice()
    _, chats, replies = _state()
    try:
        return await v.turn(text, herma, room, chats, replies)
    except v.VoiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None


@router.get("/voice/audio/{key}")
def voice_audio(key: str) -> Response:
    audio = _state()[2].get(key)
    if audio is None:
        raise HTTPException(status_code=404, detail="that reply is gone; ask again")
    return Response(audio, media_type="audio/wav")


@router.get("/status")
def status() -> dict:
    return {"hermas": _state()[0].all()}


# --- paired phones -------------------------------------------------------------------------------
# These routes take a Hermai token (or, for /pair/claim, a pairing code) instead of a dashboard
# sign-in; the plugin registers them with Hermes' token sign-in, and the token says whose phone it is.

def _people_module():
    return _load("hermes_hermai_people", "people.py")


def _people():
    from hermes_constants import get_hermes_home
    return _people_module().shared(Path(get_hermes_home()) / "hermai" / "people.json")


def _bearer(request: Request) -> str:
    auth = request.headers.get("authorization") or ""
    return auth[7:].strip() if auth[:7].lower() == "bearer " else ""


def _principal(request: Request, scope: str):
    principal = getattr(request.state, "token_principal", None)
    if principal is None or principal.provider != "hermai-devices" or scope not in principal.scopes:
        raise HTTPException(status_code=401, detail="this route takes a Hermai phone's sign-in")
    return principal


def _phone(request: Request) -> dict:
    """The paired phone making this request: ``{"id", "person", "name"}``."""
    _principal(request, "hermai")
    device = _people().device(_bearer(request))
    if device is None:
        raise HTTPException(status_code=401, detail="this phone isn't paired any more")
    return device


def _holonomic_json() -> Path:
    from hermes_constants import get_hermes_home
    return Path(get_hermes_home()) / "holonomic.json"


def _why_not_talk(person: str) -> str | None:
    """Why this person's phone can't talk to Athena yet, or None when it can. The owner always can;
    anyone else needs their turns labelled with who is speaking (the API server) and holonomic set
    up to keep their memories apart, so nothing they say opens the owner's."""
    people = _people_module()
    if person == people.OWNER:
        return None
    if _voice().api_server() is None:
        return "Hermes' API server isn't set up, so Athena can't tell whose phone is speaking"
    return people.memory_closed(_holonomic_json(), person)


def _may_talk(device: dict) -> None:
    reason = _why_not_talk(device["person"])
    if reason:
        name = _people_module().display_name(device["person"])
        raise HTTPException(status_code=403, detail=f"{name}'s phone can't talk to Athena yet: {reason}.")


@router.post("/pair/claim")
def pair_claim(request: Request, body: dict) -> dict:
    """A phone trading its one-time pairing code (sent as its bearer token) for its own token."""
    _principal(request, "hermai-pair")
    name = body.get("device") if isinstance(body, dict) else None
    claimed = _people().claim(_bearer(request), name)
    if claimed is None:
        raise HTTPException(status_code=401, detail="that pairing code has expired or was used already")
    token, person, device_id = claimed
    people = _people_module()
    return {"token": token, "person": person, "name": people.display_name(person), "device": device_id,
            "agent": "Athena", "may_talk": _why_not_talk(person) is None}


@router.post("/p/hello")
def phone_hello(request: Request) -> dict:
    device = _phone(request)
    people = _people_module()
    return {"person": device["person"], "name": people.display_name(device["person"]), "device": device["name"],
            "agent": "Athena", "may_talk": _why_not_talk(device["person"]) is None}


def _phone_chat(device: dict) -> tuple[str, dict, str]:
    """The phone's chat key, what the turn note needs, and the chat's title."""
    name = _people_module().display_name(device["person"])
    return (f"phone-{device['id']}", {"person": device["person"], "device": device["name"]},
            f"Hermai · {name}'s {device['name']}")


async def _phone_turn(text: str, device: dict) -> dict:
    v = _voice()
    _, chats, replies = _state()
    key, about, title = _phone_chat(device)
    # Labelled with who is speaking whenever the API server is there; the owner's phone falls back
    # to the dashboard's chat connection without it (unlabelled turns are hers to holonomic).
    author = None
    if v.api_server() is not None:
        author = {"id": f"person:{device['person']}", "name": _people_module().display_name(device["person"])}
    try:
        return await v.turn(text, key, "", chats, replies, title=title, about=about, author=author)
    except v.VoiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None


@router.post("/p/voice")
async def phone_voice(request: Request) -> dict:
    device = _phone(request)
    _may_talk(device)
    audio = await request.body()
    if not audio:
        raise HTTPException(status_code=400, detail="empty recording")
    if len(audio) > MAX_SPEECH_BYTES:
        raise HTTPException(status_code=413, detail="recording too long")
    v = _voice()
    try:
        heard = await asyncio.get_running_loop().run_in_executor(None, v.transcribe, audio)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"couldn't transcribe: {exc}"[:300]) from None
    if not heard:
        return {"heard": "", "reply": "", "audio": None}
    return {"heard": heard, **await _phone_turn(heard, device)}


@router.post("/p/ask")
async def phone_ask(request: Request, body: dict) -> dict:
    device = _phone(request)
    _may_talk(device)
    text = body.get("text") if isinstance(body, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(status_code=400, detail="text required")
    return {"heard": text.strip(), **await _phone_turn(text.strip(), device)}


@router.get("/p/audio")
def phone_audio(request: Request, key: str = "") -> Response:
    _phone(request)
    return voice_audio(key)


@router.get("/pair")
def pair_page(request: Request, person: str = "") -> Response:
    """A page for a signed-in browser: a pairing code for ``person``'s phone, as a QR code the
    Hermai app scans (with this server's address in it) and as text."""
    from fastapi.responses import HTMLResponse
    import html
    people = _people_module()
    pid = people.person_id(person)
    if not pid:
        raise HTTPException(status_code=400, detail="add ?person=<id>, like ?person=kayla")
    code, _expires = _people().start_pairing(pid)
    server = str(request.base_url).rstrip("/")
    link = f"hermai://pair?server={server}&code={code}"
    try:
        import qrcode
        import qrcode.image.svg
        img = qrcode.make(link, image_factory=qrcode.image.svg.SvgPathImage, box_size=12)
        qr = img.to_string(encoding="unicode")
    except Exception:
        # Without the qrcode package, the page draws the code itself (qrcodejs, kept beside this file).
        text = json.dumps(link).replace("<", "\\u003c")  # nothing in it can close the script
        script = (Path(__file__).parent / "vendor" / "qrcode.min.js").read_text(encoding="utf-8")
        qr = (f"<div id=qr></div><script>{script}</script><script>new QRCode(document.getElementById('qr'), "
              f"{{text: {text}, width: 320, height: 320, correctLevel: QRCode.CorrectLevel.M}});</script>")
    who = html.escape(people.display_name(pid))
    reason = _why_not_talk(pid)
    note = "" if reason is None else f"<p>{who}'s phone can pair now, but can't talk to Athena yet: {html.escape(reason)}.</p>"
    body = (f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
            f"<title>Pair {who}'s phone</title><body style='font-family:system-ui;max-width:32rem;margin:2rem auto;padding:0 1rem'>"
            f"<h1>Pair {who}'s phone</h1><p>In the Hermai app, tap <b>Pair this phone</b> and scan this. "
            f"It works once, within 15 minutes.</p><div style='background:#fff;padding:1rem;display:inline-block'>{qr}</div>"
            f"<p>Or enter <b>{html.escape(server)}</b> and this code:</p>"
            f"<p style='word-break:break-all;font-family:monospace'>{html.escape(code)}</p>{note}</body>")
    return HTMLResponse(body, headers={"Cache-Control": "no-store"})
