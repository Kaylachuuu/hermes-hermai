"""Face ID confirmations: requests, signatures and one-time approvals."""
import base64

import pytest

import confirm

ec = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ec")
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def phone_key():
    """A P-256 key like the phone's Secure Enclave one, and its public key as iOS exports it."""
    private = ec.generate_private_key(ec.SECP256R1())
    raw = private.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return private, base64.b64encode(raw).decode()


def sign(private, text):
    return base64.b64encode(private.sign(text.encode(), ec.ECDSA(hashes.SHA256()))).decode()


UNLOCK = {"domain": "lock", "service": "unlock", "entity_id": "lock.front_door"}


def test_an_approval_is_signed_once_and_used_once(tmp_path):
    private, public = phone_key()
    c = confirm.Confirmations(tmp_path / "confirm.json", clock=Clock())
    key = confirm.call_key(UNLOCK)
    req = c.request("s1", "dev1", "kayla", key, "lock.unlock on lock.front_door")
    assert c.waiting_for("dev1")[0]["id"] == req["id"]
    assert not c.take("s1", key)  # not approved yet
    assert c.approve(req["id"], "dev1", sign(private, "something else"), public) is None
    assert c.approve(req["id"], "dev2", sign(private, req["challenge"]), public) is None  # another phone
    other, other_public = phone_key()
    assert c.approve(req["id"], "dev1", sign(other, req["challenge"]), public) is None  # another key
    assert c.approve(req["id"], "dev1", sign(private, req["challenge"]), public)["what"].startswith("lock.unlock")
    assert c.waiting_for("dev1") == []
    assert not c.take("s2", key)  # another chat
    assert not c.take("s1", confirm.call_key({**UNLOCK, "entity_id": "lock.back_door"}))  # another call
    assert c.take("s1", key)
    assert not c.take("s1", key)  # once only


def test_requests_and_approvals_expire(tmp_path):
    private, public = phone_key()
    clock = Clock()
    c = confirm.Confirmations(tmp_path / "confirm.json", clock=clock)
    key = confirm.call_key(UNLOCK)
    req = c.request("s1", "dev1", "kayla", key, "unlock")
    clock.t += confirm.TTL_S + 1
    assert c.approve(req["id"], "dev1", sign(private, req["challenge"]), public) is None
    req = c.request("s1", "dev1", "kayla", key, "unlock")
    assert c.approve(req["id"], "dev1", sign(private, req["challenge"]), public)
    clock.t += confirm.TTL_S + 1
    assert not c.take("s1", key)


def test_public_keys_are_checked():
    _, public = phone_key()
    assert confirm.valid_public_key(public)
    assert not confirm.valid_public_key("bm90IGEga2V5")
    assert not confirm.valid_public_key(None)
