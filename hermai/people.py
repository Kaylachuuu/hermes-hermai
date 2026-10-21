"""Hermai's own sign-ins: a person's phone pairs once and then carries a token that works only on
Hermai's person routes (``/api/plugins/hermai/p/...``), never on the rest of the dashboard.

Kayla starts a pairing in Hermes (``/hermai pair elliot``, or the pairing route from a signed-in
dashboard). That makes a one-time code, good for 15 minutes, which the phone trades for its own
device token. Only hashes of codes and tokens are kept, in ``<Hermes home>/hermai/people.json``.

Each token says whose phone it is. That's a firmer answer to "who is speaking" than a voiceprint,
but until Hermes can stamp a turn's author for memory (see docs/holonomic.md), only the owner's
phones may talk: anyone else's turns would land in the owner's memories.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from pathlib import Path

TOKEN_PREFIX = "hm1_"  # a paired phone's token
CODE_PREFIX = "hp1_"   # a one-time pairing code
PAIR_TTL_S = 15 * 60
OWNER = "kayla"
DEVICE_NAME_MAX = 40
_PERSON = re.compile(r"[a-z][a-z0-9-]{0,31}")


def person_id(value) -> str | None:
    """A person's id, like "kayla" or "elliot", or None if it isn't one."""
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    return value if _PERSON.fullmatch(value) else None


def device_name(value) -> str:
    if not isinstance(value, str):
        return "Phone"
    value = " ".join(value.split())[:DEVICE_NAME_MAX]
    return value if value and value.isprintable() else "Phone"


def display_name(person: str) -> str:
    return person.replace("-", " ").title()


def memory_closed(holonomic_json: Path, person: str) -> str | None:
    """Why ``person``'s turns couldn't yet be kept apart from the owner's memories, or None when
    they can: holonomic is set up for more than one person (``people`` in holonomic.json) and
    knows them, so a turn stamped ``person:<id>`` opens their own store, or none."""
    if person == OWNER:
        return None
    try:
        cfg = json.loads(Path(holonomic_json).read_text(encoding="utf-8"))
    except FileNotFoundError:
        cfg = {}
    except (OSError, ValueError):
        return "Athena's memory settings (holonomic.json) can't be read"
    known = cfg.get("people") if isinstance(cfg, dict) else None
    if not isinstance(known, dict) or not known:
        return "Athena's memory is set up for one person only (no people in holonomic.json)"
    if str(cfg.get("owner") or "").strip().lower() != OWNER:
        return f"holonomic.json doesn't name {display_name(OWNER)} as the owner"
    if person not in {str(k).strip().lower() for k in known}:
        return f"{display_name(person)} isn't among the people in holonomic.json"
    return None


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


class People:
    """Paired phones and pairings in progress."""

    def __init__(self, path: Path, clock=time.time) -> None:
        self.path = path
        self.clock = clock
        self._lock = threading.Lock()

    def start_pairing(self, person: str) -> tuple[str, int]:
        """A one-time code for ``person``'s phone and when it expires."""
        code = CODE_PREFIX + secrets.token_urlsafe(32)
        expires = int(self.clock()) + PAIR_TTL_S
        with self._lock:
            data = self._read()
            now = self.clock()
            data["pairings"] = {k: v for k, v in data["pairings"].items() if v.get("expires", 0) > now}
            data["pairings"][_hash(code)] = {"person": person, "expires": expires}
            self._write(data)
        return code, expires

    def pairing_person(self, code: str) -> str | None:
        """Whose pairing a code is, while it's still good."""
        if not isinstance(code, str) or not code.startswith(CODE_PREFIX):
            return None
        with self._lock:
            entry = self._find(self._read()["pairings"], code)
        if entry and entry.get("expires", 0) > self.clock():
            return entry.get("person")
        return None

    def claim(self, code: str, name: str) -> tuple[str, str, str] | None:
        """Trades a pairing code for a device token: ``(token, person, device id)``. A code works once."""
        with self._lock:
            data = self._read()
            key = self._key(data["pairings"], code)
            entry = data["pairings"].pop(key, None) if key else None
            if not entry or entry.get("expires", 0) <= self.clock():
                self._write(data)
                return None
            token = TOKEN_PREFIX + secrets.token_urlsafe(32)
            digest = _hash(token)
            data["devices"][digest] = {"person": entry["person"], "name": device_name(name),
                                       "paired": int(self.clock()), "last_seen": int(self.clock())}
            self._write(data)
        return token, entry["person"], digest[:12]

    def device(self, token: str) -> dict | None:
        """The paired phone a token belongs to: ``{"id", "person", "name", "short"}``."""
        if not isinstance(token, str) or not token.startswith(TOKEN_PREFIX):
            return None
        with self._lock:
            data = self._read()
            key = self._key(data["devices"], token)
            if key is None:
                return None
            entry = data["devices"][key]
            if self.clock() - entry.get("last_seen", 0) > 60:
                entry["last_seen"] = int(self.clock())
                self._write(data)
            return {"id": key[:12], "person": entry.get("person"), "name": entry.get("name") or "Phone",
                    "short": bool(entry.get("short"))}

    def set_short(self, token: str, short: bool) -> bool:
        """Whether Athena keeps her replies to this phone brief (its Short replies setting)."""
        if not isinstance(token, str) or not token.startswith(TOKEN_PREFIX):
            return False
        with self._lock:
            data = self._read()
            key = self._key(data["devices"], token)
            if key is None:
                return False
            data["devices"][key]["short"] = bool(short)
            self._write(data)
            return True

    def devices(self) -> list[dict]:
        with self._lock:
            return [{"id": k[:12], **v} for k, v in self._read()["devices"].items()]

    def revoke(self, device_id: str) -> bool:
        with self._lock:
            data = self._read()
            keys = [k for k in data["devices"] if k[:12] == device_id]
            for k in keys:
                del data["devices"][k]
            if keys:
                self._write(data)
            return bool(keys)

    @staticmethod
    def _key(table: dict, secret: str) -> str | None:
        if not isinstance(secret, str) or not secret:
            return None
        digest = _hash(secret)
        for key in table:
            if hmac.compare_digest(key, digest):
                return key
        return None

    def _find(self, table: dict, secret: str) -> dict | None:
        key = self._key(table, secret)
        return table.get(key) if key else None

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        for table in ("devices", "pairings"):
            if not isinstance(data.get(table), dict):
                data[table] = {}
        return data

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        tmp.chmod(0o600)
        tmp.replace(self.path)


_SHARED: dict[Path, People] = {}
_SHARED_LOCK = threading.Lock()


def shared(path: Path) -> People:
    """One People per file in this process, so the routes and the sign-in provider share a lock."""
    with _SHARED_LOCK:
        return _SHARED.setdefault(Path(path), People(Path(path)))


def make_provider(people: People):
    """The dashboard sign-in provider that recognises Hermai's codes and tokens, and nothing else.
    It has no login page and no dashboard sessions: a Hermai token only opens Hermai's person routes."""
    from hermes_cli.dashboard_auth import DashboardAuthProvider, TokenPrincipal

    class HermaiDevices(DashboardAuthProvider):
        name = "hermai-devices"
        display_name = "Hermai phones"
        supports_token = True
        supports_session = False

        def verify_token(self, *, token: str):
            if token.startswith(TOKEN_PREFIX):
                device = people.device(token)
                if device:
                    return TokenPrincipal(principal=f"hermai-device:{device['id']}", provider=self.name,
                                          scopes=("hermai",))
            elif token.startswith(CODE_PREFIX):
                person = people.pairing_person(token)
                if person:
                    return TokenPrincipal(principal=f"hermai-pairing:{person}", provider=self.name,
                                          scopes=("hermai-pair",))
            return None

        def start_login(self, *, redirect_uri: str):
            raise NotImplementedError("Hermai phones have no login page")

        def complete_login(self, *, code: str, state: str, code_verifier: str, redirect_uri: str):
            raise NotImplementedError("Hermai phones have no login page")

        def verify_session(self, *, access_token: str):
            return None

        def refresh_session(self, *, refresh_token: str):
            raise NotImplementedError("Hermai phones have no dashboard sessions")

        def revoke_session(self, *, refresh_token: str) -> None:
            return None

    return HermaiDevices()
