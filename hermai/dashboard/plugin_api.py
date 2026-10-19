"""Hermai routes, mounted at /api/plugins/hermai/.

The dashboard's own login decides who may reach these routes; a herma signs in once and sends its
session token like any other dashboard client. Nothing here touches Petasos's routes or files.
"""
from __future__ import annotations

import asyncio
import importlib.util
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
