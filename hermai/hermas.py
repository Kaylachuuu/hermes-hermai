"""The hermas Hermai knows: each tablet's id, its room and how it listens.

Kept in ``<Hermes home>/hermai/hermas.json``, apart from Petasos's devices. A herma says hello
when its app starts, with the room set on the tablet; later the dashboard's Rooms page sets it.
"""
from __future__ import annotations

import json
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


def _it_is(now: float | None) -> str:
    """The time on Hermes' clock, so Athena never has to guess it."""
    stamp = time.localtime(time.time() if now is None else now)
    clock = time.strftime("%A %d %B %Y, %I:%M %p", stamp).replace(" 0", " ")
    zone = time.strftime("%Z", stamp)
    return f"It is {clock}{' ' + zone if zone else ''}."


def household_note(room: str, now: float | None = None) -> str:
    """What Athena is told on every turn from a herma."""
    where = f"the {room} herma" if room else "a herma"
    return (f"[Hermai] {_it_is(now)} This message came through {where}, a shared tablet in the house. Anyone in the "
            "household, or a guest, may be speaking, so don't assume it's Kayla; ask who's asking before "
            "anything personal. Your reply is spoken aloud in the room: keep it short and plain, with no "
            "markdown or lists. When asked to control something without naming a room, it means this room.")


def personal_note(person: str, device: str, now: float | None = None) -> str:
    """What Athena is told on every turn from a paired phone."""
    return (f"[Hermai] {_it_is(now)} This message came from {person}'s own phone "
            f"({device}), signed in to Hermai as {person}, so it's {person} speaking. They may be away from "
            "the house. Your reply is spoken aloud: keep it short and plain, with no markdown or lists. "
            "If they ask about a room without naming it, ask which one.")
