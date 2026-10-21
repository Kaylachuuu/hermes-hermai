"""Face ID for the locks, the alarm and the garage, from a person's own phone.

The guard refuses unlocking, disarming and opening on every other path. On a turn from a paired phone
whose person may do these things, and which has a Face ID key, it refuses the call once and asks that
phone instead:

1. The guard records the request here (``confirm.json``): which chat, which phone, exactly which call,
   and a random challenge. Athena is told the phone is asking.
2. The phone's reply carries the request. The app asks for Face ID, which unlocks a key that lives in
   the phone's Secure Enclave and never leaves it, and signs the challenge with it.
3. ``approve`` checks the signature against the public key the phone registered when it was set up.
   Hermai then tells Athena, in the same chat, to go ahead.
4. When Athena makes the call again, ``take`` finds the approval for that exact call in that chat and
   uses it up, and the guard lets it through once.

A request lasts two minutes, an approval works once, and both are tied to the call's exact arguments,
so approving "open the garage" can't open the front door. The phone's token alone can't approve:
it takes the signature, and the signature takes Face ID.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import time
from pathlib import Path

TTL_S = 120

_LOCK = threading.Lock()


def call_key(args: dict) -> str:
    """A fingerprint of a Home Assistant call's exact arguments."""
    raw = json.dumps(args if isinstance(args, dict) else {}, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def verify(public_key_b64: str, challenge: str, signature_b64: str) -> bool:
    """Whether ``signature`` (DER ECDSA over SHA-256) signs ``challenge`` with the phone's P-256 key
    (an uncompressed point, as iOS exports it)."""
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), base64.b64decode(public_key_b64))
        key.verify(base64.b64decode(signature_b64), challenge.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def valid_public_key(public_key_b64) -> bool:
    if not isinstance(public_key_b64, str):
        return False
    try:
        from cryptography.hazmat.primitives.asymmetric import ec
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), base64.b64decode(public_key_b64))
        return True
    except (ValueError, TypeError):
        return False


class Confirmations:
    """Requests waiting for a phone's Face ID, and approvals waiting to be used."""

    def __init__(self, path: Path, clock=time.time) -> None:
        self.path = Path(path)
        self.clock = clock

    def request(self, session: str, device: str, person: str, key: str, what: str) -> dict:
        """A new request for this exact call, replacing any earlier one for the same call in this chat."""
        with _LOCK:
            data = self._read()
            data = {i: r for i, r in data.items() if not (r["session"] == session and r["key"] == key)}
            rid = secrets.token_hex(8)
            entry = {"session": session, "device": device, "person": person, "key": key, "what": what,
                     "challenge": f"hermai-confirm:{rid}:{secrets.token_urlsafe(24)}",
                     "created": self.clock(), "approved": None}
            data[rid] = entry
            self._write(data)
        return {"id": rid, **entry}

    def waiting_for(self, device: str, since: float = 0) -> list[dict]:
        """This phone's requests not yet approved, newest last."""
        with _LOCK:
            data = self._read()
        found = [{"id": i, **r} for i, r in data.items()
                 if r["device"] == device and not r["approved"] and r["created"] >= since]
        return sorted(found, key=lambda r: r["created"])

    def approve(self, rid: str, device: str, signature: str, public_key: str) -> dict | None:
        """The request, approved, when ``signature`` signs its challenge with this phone's key."""
        with _LOCK:
            data = self._read()
            entry = data.get(rid) if isinstance(rid, str) else None
            if not entry or entry["device"] != device or entry["approved"]:
                return None
            if not public_key or not verify(public_key, entry["challenge"], signature):
                return None
            entry["approved"] = self.clock()
            self._write(data)
        return {"id": rid, **entry}

    def take(self, session: str, key: str) -> bool:
        """Uses up an approval for this exact call in this chat, if there is one."""
        with _LOCK:
            data = self._read()
            for rid, entry in data.items():
                if entry["session"] == session and entry["key"] == key and entry["approved"]:
                    del data[rid]
                    self._write(data)
                    return True
        return False

    def _read(self) -> dict:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        now = self.clock()
        fields = ("session", "device", "person", "key", "what", "challenge", "created")
        return {i: r for i, r in (raw.items() if isinstance(raw, dict) else [])
                if isinstance(r, dict) and all(k in r for k in fields)
                and now - float(r.get("approved") or r["created"]) < TTL_S}

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        tmp.chmod(0o600)
        tmp.replace(self.path)
