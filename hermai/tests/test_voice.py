"""Herma voice turns against a stand-in for the dashboard's chat connection."""
import asyncio
import io
import json
import wave

import pytest

import hermas
import voice

websockets = pytest.importorskip("websockets")


def wav(frames: bytes, rate: int = 24000) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames)
    return out.getvalue()


def test_join_wavs_keeps_every_chunk():
    joined = voice.join_wavs([wav(b"\x01\x00" * 10), wav(b"\x02\x00" * 5)])
    with wave.open(io.BytesIO(joined)) as r:
        assert r.getnframes() == 15 and r.getframerate() == 24000


class FakeGateway:
    """Speaks just enough of tui_gateway's JSON-RPC: ready, create/resume, submit, a reply."""

    def __init__(self):
        self.calls = []
        self.declined = []
        self.stored = {"stored-1"}
        self.compressed = False

    async def handler(self, ws):
        await ws.send(json.dumps({"jsonrpc": "2.0", "method": "event",
                                  "params": {"type": "gateway.ready", "payload": {}}}))
        async for raw in ws:
            frame = json.loads(raw)
            if "method" not in frame:  # our answer to the server's request
                self.declined.append(frame)
                continue
            method, params, rid = frame["method"], frame["params"], frame["id"]
            self.calls.append((method, params))
            if method == "session.create":
                result = {"session_id": "live-1", "stored_session_id": "stored-1"}
            elif method == "session.resume":
                if params["session_id"] not in self.stored:
                    await ws.send(json.dumps({"jsonrpc": "2.0", "id": rid,
                                              "error": {"code": 4001, "message": "not found"}}))
                    continue
                result = {"session_id": "live-2",
                          "stored_session_id": "stored-2" if self.compressed else params["session_id"]}
            elif method == "prompt.submit":
                sid = params["session_id"]
                await ws.send(json.dumps({"jsonrpc": "2.0", "id": rid, "result": {"status": "streaming"}}))
                await ws.send(json.dumps({"jsonrpc": "2.0", "id": "srv-1", "method": "approval",
                                          "params": {"session_id": sid}}))
                for kind, payload in (("message.delta", {"text": "The kitchen "}),
                                      ("message.delta", {"text": "lights are off."}),
                                      ("message.complete", {"text": "The kitchen lights are off.",
                                                            "status": "complete"})):
                    await ws.send(json.dumps({"jsonrpc": "2.0", "method": "event", "params": {
                        "type": kind, "session_id": sid, "payload": payload}}))
                continue
            else:
                result = {}
            await ws.send(json.dumps({"jsonrpc": "2.0", "id": rid, "result": result}))


def run_turns(tmp_path, *texts, herma="kitchen-tab", room="Kitchen", gateway=None):
    gateway = gateway or FakeGateway()
    chats = voice.Chats(tmp_path / "chats.json")

    async def go():
        async with websockets.serve(gateway.handler, "127.0.0.1", 0) as server:
            url = f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}/api/ws"
            return [await voice.ask(t, herma, room, chats, url=url) for t in texts]

    return asyncio.run(go()), gateway, chats


def test_first_turn_opens_the_rooms_chat_and_later_turns_resume_it(tmp_path):
    replies, gateway, chats = run_turns(tmp_path, "Lights off", "Thanks")
    assert replies == ["The kitchen lights are off."] * 2
    assert [m for m, _ in gateway.calls] == ["session.create", "prompt.submit", "session.resume", "prompt.submit"]
    assert gateway.calls[0][1] == {"title": "Hermai · Kitchen", "source": "hermai"}
    assert gateway.calls[1][1] == {"session_id": "live-1", "text": "Lights off", "voice_turn": True,
                                   "surface": "voice-live"}
    assert gateway.calls[3][1]["session_id"] == "live-2"
    assert chats.get("kitchen-tab") == "stored-1"
    assert chats.room_of_session("stored-1") == "Kitchen"
    # The approval request was declined rather than left hanging.
    assert gateway.declined and gateway.declined[0]["id"] == "srv-1" and "error" in gateway.declined[0]


def test_a_compressed_chat_is_followed(tmp_path):
    gateway = FakeGateway()
    gateway.compressed = True
    voice.Chats(tmp_path / "chats.json").set("kitchen-tab", "stored-1", "Kitchen")
    _, _, chats = run_turns(tmp_path, "Hi", gateway=gateway)
    assert chats.get("kitchen-tab") == "stored-2"
    assert chats.room_of_session("stored-2") == "Kitchen" and chats.room_of_session("stored-1") is None


def test_a_chat_deleted_elsewhere_is_replaced(tmp_path):
    voice.Chats(tmp_path / "chats.json").set("kitchen-tab", "gone", "Kitchen")
    replies, gateway, chats = run_turns(tmp_path, "Hello")
    assert replies == ["The kitchen lights are off."]
    assert [m for m, _ in gateway.calls] == ["session.resume", "session.create", "prompt.submit"]
    assert chats.get("kitchen-tab") == "stored-1"


def test_room_of_session_only_knows_herma_chats(tmp_path):
    chats = voice.Chats(tmp_path / "chats.json")
    chats.set("kitchen-tab", "s-k", "Kitchen")
    chats.set("living-tab", "s-l", "Living room")
    assert chats.room_of_session("other", "s-l") == "Living room"
    assert chats.room_of_session("other") is None
    assert chats.room_of_session("", "") is None


def test_replies_keep_only_the_newest():
    replies = voice.Replies(keep=2)
    keys = [replies.put(bytes([i])) for i in range(3)]
    assert replies.get(keys[0]) is None and replies.get(keys[2]) == b"\x02"


def test_hermas_and_rooms_are_checked():
    assert hermas.herma_id("kitchen-tab") == "kitchen-tab"
    assert hermas.herma_id("../etc") is None and hermas.herma_id("") is None and hermas.herma_id(3) is None
    assert hermas.room_name("  Living   room ") == "Living room"
    assert hermas.room_name("") is None and hermas.room_name("x" * 100) is None


def test_hello_keeps_the_room_and_listening(tmp_path):
    h = hermas.Hermas(tmp_path / "hermas.json", clock=lambda: 100)
    assert h.hello("kitchen-tab", "Kitchen") == {"room": "Kitchen", "last_seen": 100, "listening": "push_to_talk"}
    h.hello("kitchen-tab", "Dining room")
    assert h.get("kitchen-tab")["room"] == "Dining room"
    assert h.get("nope") is None


def test_the_household_note_names_the_room():
    note = hermas.household_note("Kitchen")
    assert "Kitchen herma" in note and "don't assume it's Kayla" in note


def test_the_household_note_gives_the_time(monkeypatch):
    monkeypatch.setenv("TZ", "America/Denver")
    import time
    time.tzset()
    try:
        note = hermas.household_note("Kitchen", now=1792442460)  # 2026-10-19 20:41 UTC
        assert "It is Monday 19 October 2026, 2:41 PM MDT." in note
    finally:
        monkeypatch.delenv("TZ")
        time.tzset()
