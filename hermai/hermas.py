"""The hermas Hermai knows: each tablet's id, its room and how it listens.

Kept in ``<Hermes home>/hermai/hermas.json``, apart from Petasos's devices. A herma says hello
when its app starts, with the room set on the tablet; later the dashboard's Rooms page sets it.
"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

HERMA_ID_MAX = 64
ROOM_MAX = 48
LISTENING = ("push_to_talk", "wake_word")


def herma_id(value) -> str | None:
    """A herma's id as the app sends it, or None if it isn't one."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if 0 < len(value) <= HERMA_ID_MAX and all(c.isalnum() or c in "-_." for c in value):
        return value
    return None


def room_name(value) -> str | None:
    """A room's name, tidied, or None if it isn't one."""
    if not isinstance(value, str):
        return None
    value = " ".join(value.split())
    if 0 < len(value) <= ROOM_MAX and value.isprintable():
        return value
    return None


class Hermas:
    def __init__(self, path: Path, clock=time.time) -> None:
        self.path = path
        self.clock = clock
        self._lock = threading.Lock()

    def hello(self, herma: str, room: str) -> dict:
        """Record a herma starting up; its settings come back."""
        with self._lock:
            data = self._read()
            entry = data.get(herma) if isinstance(data.get(herma), dict) else {}
            entry.update({"room": room, "last_seen": int(self.clock())})
            entry.setdefault("listening", "push_to_talk")
            data[herma] = entry
            self._write(data)
            return dict(entry)

    def get(self, herma: str) -> dict | None:
        with self._lock:
            entry = self._read().get(herma)
            return dict(entry) if isinstance(entry, dict) else None

    def seen(self, herma: str) -> None:
        with self._lock:
            data = self._read()
            if isinstance(data.get(herma), dict):
                data[herma]["last_seen"] = int(self.clock())
                self._write(data)

    def all(self) -> dict:
        with self._lock:
            return {k: dict(v) for k, v in self._read().items() if isinstance(v, dict)}

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)


WAKE_NAME = "athena"
WAKE_LIKENESS = 0.82  # athina, atena, thena and athene pass; tina doesn't
NOT_WAKE = frozenset({"athens"})
_WORD = re.compile(r"[A-Za-z']+")
_LEAD = " ,.!?:;-–—"


def after_wake(heard: str) -> str | None:
    """What was said after "Hey Athena" in a wake word's recording, or None when no "Athena" was
    heard at all: the tablet's listener is lenient, so this is the check that it really was her name.
    The recording starts a moment before the wake word, so anything before her name is dropped."""
    import difflib
    for m in _WORD.finditer(heard):
        word = m.group().lower().removesuffix("'s")
        if word not in NOT_WAKE and difflib.SequenceMatcher(None, word, WAKE_NAME).ratio() >= WAKE_LIKENESS:
            rest = heard[m.end():].lstrip(_LEAD).strip()
            return rest or "Hey Athena."
    return None


def _it_is(now: float | None) -> str:
    """The time on Hermes' clock, so Athena never has to guess it."""
    stamp = time.localtime(time.time() if now is None else now)
    clock = time.strftime("%A %d %B %Y, %I:%M %p", stamp).replace(" 0", " ")
    zone = time.strftime("%Z", stamp)
    return f"It is {clock}{' ' + zone if zone else ''}."


# Athena once told Kayla she was unlocking a door the house doesn't have.
HONEST = ("Only say you've done something to the house once the Home Assistant call for it has succeeded; "
          "if no such device exists, or the call was refused, say so plainly.")


def household_note(room: str, now: float | None = None, speaker: str | None = None) -> str:
    """What Athena is told on every turn from a herma. ``speaker`` is who the voice matched, "" for
    no one (a guest), or None when no voices are learned and the herma can't tell."""
    where = f"the {room} herma" if room else "a herma"
    if speaker:
        who = (f"By their voice, this is {speaker}. That's a good match, not proof, so if anything "
               "they ask doesn't fit, check before sharing anything private.")
    elif speaker == "":
        who = ("Their voice didn't match anyone in the household, so treat them as a guest: nothing "
               "is remembered from this chat, and don't share anyone's personal details.")
    else:
        who = ("Anyone in the household, or a guest, may be speaking, so don't assume it's Kayla; "
               "ask who's asking before anything personal.")
    return (f"[Hermai] {_it_is(now)} This message came through {where}, a shared tablet in the house. "
            f"{who} Your reply is spoken aloud in the room: keep it short and plain, with no "
            "markdown or lists. When asked to control something without naming a room, it means this room. " + HONEST)


def personal_note(person: str, device: str, now: float | None = None, short: bool = False) -> str:
    """What Athena is told on every turn from a paired phone. ``short`` is the phone's Short replies
    setting; otherwise she answers as fully as in a chat."""
    length = ("keep it short and plain" if short else
              "answer as fully as you would in a chat, but in plain spoken sentences")
    return (f"[Hermai] {_it_is(now)} This message came from {person}'s own phone "
            f"({device}), signed in to Hermai as {person}, so it's {person} speaking. They may be away from "
            f"the house. Your reply is read aloud to them, usually in earbuds: {length}, with no markdown, "
            "lists or links. If they ask about a room without naming it, ask which one. " + HONEST)
