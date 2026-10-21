"""Hermai's routes inside a real Hermes dashboard, with Athena's side faked. Skipped when Hermes
is not installed."""
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("hermes_cli")
pytest.importorskip("fastapi")


@pytest.fixture(scope="module")
def hermes(tmp_path_factory):
    home = tmp_path_factory.mktemp("hermes_home")
    (home / "plugins").mkdir()
    os.symlink(Path(__file__).resolve().parent.parent, home / "plugins" / "hermai")
    (home / "config.yaml").write_text("plugins:\n  enabled:\n    - hermai\n")
    old = os.environ.get("HERMES_HOME")
    os.environ["HERMES_HOME"] = str(home)
    os.environ["HERMES_DASHBOARD_SESSION_TOKEN"] = "test-token"
    from fastapi.testclient import TestClient
    from hermes_cli import web_server
    import model_tools  # noqa: F401  (plugin discovery)
    with TestClient(web_server.app) as client:
        client.headers["Authorization"] = "Bearer test-token"
        yield client, home
    if old is None:
        os.environ.pop("HERMES_HOME", None)
    else:
        os.environ["HERMES_HOME"] = old


def test_routes_need_the_dashboard_login(hermes):
    client, _ = hermes
    r = client.post("/api/plugins/hermai/hello", json={"herma": "kitchen-tab", "room": "Kitchen"},
                    headers={"Authorization": ""})
    assert r.status_code == 401


def test_hello_registers_a_herma(hermas_hello):
    body, home = hermas_hello
    assert body == {"herma": "kitchen-tab", "room": "Kitchen", "listening": "push_to_talk", "agent": "Athena"}
    assert (home / "hermai" / "hermas.json").is_file()


@pytest.fixture
def hermas_hello(hermes):
    client, home = hermes
    r = client.post("/api/plugins/hermai/hello", json={"herma": "kitchen-tab", "room": "Kitchen"})
    assert r.status_code == 200, r.text
    return r.json(), home


def test_bad_hellos_are_refused(hermes):
    client, _ = hermes
    assert client.post("/api/plugins/hermai/hello", json={"herma": "../x", "room": "Kitchen"}).status_code == 400
    assert client.post("/api/plugins/hermai/hello", json={"herma": "a", "room": ""}).status_code == 400


def test_an_unknown_herma_says_hello_first(hermes):
    client, _ = hermes
    r = client.post("/api/plugins/hermai/ask?herma=stranger", json={"text": "hi"})
    assert r.status_code == 404


def test_a_typed_turn_comes_back_with_audio(hermes, hermas_hello, monkeypatch):
    client, _ = hermes
    voice = sys.modules["hermes_hermai_voice"]
    seen = {}

    async def fake_ask(text, herma, room, chats, url=None, **_kw):
        seen.update(text=text, herma=herma, room=room)
        return "Done."

    monkeypatch.setattr(voice, "ask", fake_ask)
    monkeypatch.setattr(voice, "speak", lambda text: b"RIFF-fake")
    r = client.post("/api/plugins/hermai/ask?herma=kitchen-tab", json={"text": " lights off "})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["heard"] == "lights off" and body["reply"] == "Done."
    assert seen == {"text": "lights off", "herma": "kitchen-tab", "room": "Kitchen"}
    audio = client.get(f"/api/plugins/hermai/voice/audio/{body['audio']}")
    assert audio.status_code == 200 and audio.content == b"RIFF-fake"
    assert client.get("/api/plugins/hermai/voice/audio/nope").status_code == 404


def test_a_recording_is_transcribed_first(hermes, hermas_hello, monkeypatch):
    client, _ = hermes
    voice = sys.modules["hermes_hermai_voice"]

    async def fake_ask(text, herma, room, chats, url=None, **_kw):
        return f"You said {text}."

    monkeypatch.setattr(voice, "transcribe", lambda audio: "good night" if audio == b"RIFFwav" else "")
    monkeypatch.setattr(voice, "ask", fake_ask)
    monkeypatch.setattr(voice, "speak", lambda text: b"RIFF")
    r = client.post("/api/plugins/hermai/voice?herma=kitchen-tab", content=b"RIFFwav",
                    headers={"Content-Type": "audio/wav"})
    assert r.status_code == 200, r.text
    assert r.json()["heard"] == "good night" and r.json()["reply"] == "You said good night."
    silent = client.post("/api/plugins/hermai/voice?herma=kitchen-tab", content=b"RIFFquiet").json()
    assert silent == {"heard": "", "reply": "", "audio": None}


def test_the_room_note_reaches_athena_only_in_herma_chats(hermes, hermas_hello):
    _, home = hermes
    sys.modules["hermes_hermai_voice"].Chats(home / "hermai" / "chats.json").set("kitchen-tab", "s-kitchen", "Kitchen")
    from hermes_cli.lifecycle import invoke_hook
    notes = [r for r in invoke_hook("pre_llm_call", session_id="s-kitchen", parent_session_id="") if r]
    assert len(notes) == 1 and "Kitchen herma" in notes[0]["context"]
    assert [r for r in invoke_hook("pre_llm_call", session_id="other", parent_session_id="") if r] == []


def _pair(client, home, person):
    people = sys.modules["hermes_hermai_people"]
    code, _ = people.shared(home / "hermai" / "people.json").start_pairing(person)
    return code


def test_a_phone_pairs_and_talks(hermes, monkeypatch):
    monkeypatch.delenv("API_SERVER_KEY", raising=False)  # the owner falls back to the chat connection
    client, home = hermes
    code = _pair(client, home, "kayla")
    claimed = client.post("/api/plugins/hermai/pair/claim", json={"device": "iPhone"},
                          headers={"Authorization": f"Bearer {code}"})
    assert claimed.status_code == 200, claimed.text
    token = claimed.json()["token"]
    assert claimed.json()["may_talk"] is True
    # A code works once.
    again = client.post("/api/plugins/hermai/pair/claim", json={}, headers={"Authorization": f"Bearer {code}"})
    assert again.status_code == 401

    phone = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/plugins/hermai/p/hello", headers=phone).json()["name"] == "Kayla"
    voice = sys.modules["hermes_hermai_voice"]
    seen = {}

    async def fake_ask(text, herma, room, chats, url=None, title=None, about=None):
        seen.update(herma=herma, title=title, about=about)
        chats.set(herma, "s-phone", room, about)
        return "Hi Kayla."

    monkeypatch.setattr(voice, "ask", fake_ask)
    monkeypatch.setattr(voice, "speak", lambda text: b"RIFF-phone")
    r = client.post("/api/plugins/hermai/p/ask", json={"text": "hello"}, headers=phone)
    assert r.status_code == 200, r.text
    assert seen["title"] == "Hermai · Kayla's iPhone" and seen["about"] == {"person": "kayla", "device": "iPhone", "short": False}
    audio = client.get(f"/api/plugins/hermai/p/audio?key={r.json()['audio']}", headers=phone)
    assert audio.content == b"RIFF-phone"

    from hermes_cli.lifecycle import invoke_hook
    notes = [x for x in invoke_hook("pre_llm_call", session_id="s-phone", parent_session_id="") if x]
    assert "Kayla's own phone (iPhone)" in notes[0]["context"]
    assert "as fully as you would in a chat" in notes[0]["context"]

    # Short replies is this phone's own setting.
    assert client.post("/api/plugins/hermai/p/settings", json={"short": "yes"}, headers=phone).status_code == 400
    assert client.post("/api/plugins/hermai/p/settings", json={"short": True}, headers=phone).json() == {"short": True}
    assert client.post("/api/plugins/hermai/p/hello", headers=phone).json()["short"] is True
    client.post("/api/plugins/hermai/p/ask", json={"text": "again"}, headers=phone)
    assert seen["about"]["short"] is True
    notes = [x for x in invoke_hook("pre_llm_call", session_id="s-phone", parent_session_id="") if x]
    assert "keep it short" in notes[0]["context"]


def test_a_phone_token_opens_nothing_else(hermes):
    client, home = hermes
    code = _pair(client, home, "kayla")
    token = client.post("/api/plugins/hermai/pair/claim", json={}, headers={"Authorization": f"Bearer {code}"}).json()["token"]
    phone = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/plugins/hermai/status", headers=phone).status_code == 401
    assert client.post("/api/plugins/hermai/ask?herma=x", json={"text": "hi"}, headers=phone).status_code == 401
    assert client.get("/api/sessions", headers=phone).status_code == 401
    # And the dashboard sign-in doesn't open the phone routes.
    assert client.post("/api/plugins/hermai/p/hello").status_code == 401
    # A pairing code isn't a phone token.
    code2 = _pair(client, home, "kayla")
    assert client.post("/api/plugins/hermai/p/hello", headers={"Authorization": f"Bearer {code2}"}).status_code == 401


def test_others_phones_pair_but_cannot_talk_yet(hermes, monkeypatch):
    client, home = hermes
    monkeypatch.delenv("API_SERVER_KEY", raising=False)
    code = _pair(client, home, "elliot")
    claimed = client.post("/api/plugins/hermai/pair/claim", json={}, headers={"Authorization": f"Bearer {code}"}).json()
    assert claimed["may_talk"] is False
    phone = {"Authorization": f"Bearer {claimed['token']}"}
    r = client.post("/api/plugins/hermai/p/ask", json={"text": "hi"}, headers=phone)
    assert r.status_code == 403 and "API server" in r.json()["detail"]

    # With the API server but holonomic still set up for one person, still no.
    monkeypatch.setenv("API_SERVER_KEY", "k" * 40)
    r = client.post("/api/plugins/hermai/p/ask", json={"text": "hi"}, headers=phone)
    assert r.status_code == 403 and "one person" in r.json()["detail"]


def test_others_phones_talk_as_themselves_once_memory_is_apart(hermes, monkeypatch):
    import json
    client, home = hermes
    monkeypatch.setenv("API_SERVER_KEY", "k" * 40)
    (home / "holonomic.json").write_text(json.dumps({"owner": "kayla", "people": {"elliot": {"remembered": True}}}))
    try:
        code = _pair(client, home, "elliot")
        claimed = client.post("/api/plugins/hermai/pair/claim", json={"device": "Pixel"},
                              headers={"Authorization": f"Bearer {code}"}).json()
        assert claimed["may_talk"] is True
        voice = sys.modules["hermes_hermai_voice"]
        seen = {}

        def fake_ask_as(text, chat, chats, author, title, about=None, api=None):
            seen.update(author=author, title=title)
            chats.set(chat, "s-elliot", "", about)
            return "Hi Elliot."

        async def no_ws(*_a, **_kw):
            raise AssertionError("a labelled turn never goes through the chat connection")

        monkeypatch.setattr(voice, "ask_as", fake_ask_as)
        monkeypatch.setattr(voice, "ask", no_ws)
        monkeypatch.setattr(voice, "speak", lambda text: b"RIFF")
        r = client.post("/api/plugins/hermai/p/ask", json={"text": "hello"},
                        headers={"Authorization": f"Bearer {claimed['token']}"})
        assert r.status_code == 200, r.text
        assert seen["author"] == {"id": "person:elliot", "name": "Elliot"}
        assert seen["title"] == "Hermai · Elliot's Pixel"
    finally:
        (home / "holonomic.json").unlink()


def test_pairing_page_needs_the_dashboard_sign_in(hermes):
    client, _ = hermes
    assert client.get("/api/plugins/hermai/pair?person=kayla", headers={"Authorization": ""}).status_code == 401
    page = client.get("/api/plugins/hermai/pair?person=kayla")
    assert page.status_code == 200 and "hp1_" in page.text
    assert "QRCode" in page.text or "<svg" in page.text  # drawn by the page without the qrcode package


def test_face_id_lets_one_unlock_through_from_kaylas_phone(hermes, monkeypatch):
    import base64
    ec = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ec")
    from cryptography.hazmat.primitives import hashes, serialization
    from hermes_cli.lifecycle import invoke_hook
    client, home = hermes
    monkeypatch.delenv("API_SERVER_KEY", raising=False)
    code = _pair(client, home, "kayla")
    token = client.post("/api/plugins/hermai/pair/claim", json={"device": "Face"},
                        headers={"Authorization": f"Bearer {code}"}).json()["token"]
    phone = {"Authorization": f"Bearer {token}"}
    unlock = {"domain": "lock", "service": "unlock", "entity_id": "lock.front_door"}

    def guard(session="s-face"):
        return [r for r in invoke_hook("pre_tool_call", tool_name="ha_call_service", args=dict(unlock),
                                       tool_call_id="c1", session_id=session) if r]

    client.get("/api/plugins/hermai/status")  # loads the voice module
    voice = sys.modules["hermes_hermai_voice"]
    asked = []

    async def fake_ask(text, herma, room, chats, url=None, title=None, about=None):
        chats.set(herma, "s-face", room, about)
        asked.append((text, guard()))
        return "One moment."

    monkeypatch.setattr(voice, "ask", fake_ask)
    monkeypatch.setattr(voice, "speak", lambda text: b"RIFF")

    # Without a Face ID key the guard refuses as always.
    r = client.post("/api/plugins/hermai/p/ask", json={"text": "unlock the front door"}, headers=phone).json()
    assert "confirm" not in r and "Not allowed" in asked[-1][1][0]["message"]

    private = ec.generate_private_key(ec.SECP256R1())
    public = base64.b64encode(private.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)).decode()
    assert client.post("/api/plugins/hermai/p/key", json={"public_key": public}, headers=phone).json() == {"key": True}
    assert client.post("/api/plugins/hermai/p/hello", headers=phone).json()["face_id"] == {"key": True, "allowed": True}
    other = base64.b64encode(ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)).decode()
    assert client.post("/api/plugins/hermai/p/key", json={"public_key": other}, headers=phone).status_code == 409

    r = client.post("/api/plugins/hermai/p/ask", json={"text": "unlock the front door"}, headers=phone).json()
    assert "Waiting for Face ID" in asked[-1][1][0]["message"]
    req = r["confirm"]
    assert req["what"] == "lock.unlock on lock.front_door"

    bad = base64.b64encode(private.sign(b"not the challenge", ec.ECDSA(hashes.SHA256()))).decode()
    assert client.post("/api/plugins/hermai/p/confirm", json={"id": req["id"], "signature": bad},
                       headers=phone).status_code == 403

    good = base64.b64encode(private.sign(req["challenge"].encode(), ec.ECDSA(hashes.SHA256()))).decode()
    r = client.post("/api/plugins/hermai/p/confirm", json={"id": req["id"], "signature": good}, headers=phone)
    assert r.status_code == 200, r.text
    text, verdicts = asked[-1]
    assert "confirmed with Face ID" in text and verdicts == []  # let through, once
    assert "Not allowed" in guard()[0]["message"] or "Waiting" in guard()[0]["message"]  # and not again
    assert "Not allowed" in guard("s-elsewhere")[0]["message"]  # other chats: the guard as always

    # Turned off for Kayla, her phone gets the plain refusal.
    sys.modules["hermes_hermai_people"].shared(home / "hermai" / "people.json").set_may_secure("kayla", False)
    assert "Not allowed" in guard()[0]["message"]


def test_a_herma_learns_a_voice_then_knows_who_is_speaking(hermes, hermas_hello, monkeypatch):
    import json
    from hermes_cli.lifecycle import invoke_hook
    client, home = hermes
    monkeypatch.setenv("API_SERVER_KEY", "k" * 40)
    (home / "holonomic.json").write_text(json.dumps({"owner": "kayla", "people": {"elliot": {"remembered": True}}}))
    client.get("/api/plugins/hermai/status")  # loads the modules
    voice, voices = sys.modules["hermes_hermai_voice"], sys.modules["hermes_hermai_voices"]
    unit = voices._unit
    prints = {b"RIFF-elliot": unit([1, 0.1, 0]), b"RIFF-elliot2": unit([1, 0, 0.1]),
              b"RIFF-stranger": unit([0, 0, 1]), b"RIFF-ty": unit([0, 1, 0])}
    monkeypatch.setattr(voices.Embedder, "embed", lambda self, audio: prints.get(audio))
    monkeypatch.setattr(voices.Embedder, "_model", lambda self: None)
    monkeypatch.setattr(voices, "engine_installed", lambda: True)
    monkeypatch.setattr(voice, "transcribe", lambda audio: "" if audio == b"RIFF-quiet" else "hello there")
    monkeypatch.setattr(voice, "speak", lambda text: b"RIFF")
    asked = []

    def fake_ask_as(text, chat, chats, author, title, about=None, api=None):
        chats.set(chat, f"s-{chat}", "", about)
        asked.append({"chat": chat, "author": author, "title": title})
        return "Hi."

    async def no_ws(*_a, **_kw):
        raise AssertionError("once voices are learned, herma turns are labelled")

    try:
        # Before any voice is learned, the herma's turns go the old way.
        assert "voices" in client.get("/api/plugins/hermai/status").json()
        hermai = next(m for name, m in sys.modules.items() if name.endswith("hermai") and hasattr(m, "_slash"))
        out = hermai._slash("voices learn elliot kitchen")
        assert "ready to learn Elliot's voice" in out
        monkeypatch.setattr(voice, "ask_as", fake_ask_as)
        monkeypatch.setattr(voice, "ask", no_ws)

        r = client.post("/api/plugins/hermai/voice?herma=kitchen-tab", content=b"RIFF-elliot").json()
        assert r["reply"].startswith("Got it. 4 more") and r["audio"]
        r = client.post("/api/plugins/hermai/voice?herma=kitchen-tab", content=b"RIFF-ty").json()
        assert "didn't sound like the same person" in r["reply"]
        r = client.post("/api/plugins/hermai/voice?herma=kitchen-tab", content=b"RIFF-short").json()
        assert "a bit short" in r["reply"]
        for _ in range(3):
            client.post("/api/plugins/hermai/voice?herma=kitchen-tab", content=b"RIFF-elliot2")
        r = client.post("/api/plugins/hermai/voice?herma=kitchen-tab", content=b"RIFF-elliot").json()
        assert r["reply"] == "Thanks, Elliot. I'll know your voice now."
        assert asked == []  # learning never reached Athena
        assert "Elliot" in hermai._slash("voices")

        r = client.post("/api/plugins/hermai/voice?herma=kitchen-tab", content=b"RIFF-elliot2").json()
        assert r["reply"] == "Hi."
        assert asked[-1] == {"chat": "kitchen-tab~elliot", "author": {"id": "person:elliot", "name": "Elliot"},
                             "title": "Hermai · Kitchen · Elliot"}
        notes = [n for n in invoke_hook("pre_llm_call", session_id="s-kitchen-tab~elliot", parent_session_id="") if n]
        assert "By their voice, this is Elliot" in notes[0]["context"]
        guarded = [g for g in invoke_hook("pre_tool_call", tool_name="ha_call_service",
                                          args={"domain": "lock", "service": "unlock", "entity_id": "lock.front_door"},
                                          tool_call_id="c1", session_id="s-kitchen-tab~elliot") if g]
        assert "Not allowed" in guarded[0]["message"]  # a voice never unlocks anything

        client.post("/api/plugins/hermai/voice?herma=kitchen-tab", content=b"RIFF-stranger")
        assert asked[-1]["chat"] == "kitchen-tab~guest"
        assert asked[-1]["author"] == {"id": "person:guest", "name": "Guest"}
        notes = [n for n in invoke_hook("pre_llm_call", session_id="s-kitchen-tab~guest", parent_session_id="") if n]
        assert "treat them as a guest" in notes[0]["context"]
        client.post("/api/plugins/hermai/ask?herma=kitchen-tab", json={"text": "typed"})
        assert asked[-1]["chat"] == "kitchen-tab~guest"  # typing has no voice

        assert "Forgot Elliot's voice" in hermai._slash("voices forget elliot")
    finally:
        (home / "holonomic.json").unlink()


def test_a_guests_chat_starts_afresh_after_a_while(hermes, hermas_hello, monkeypatch):
    client, home = hermes
    client.get("/api/plugins/hermai/status")
    voice = sys.modules["hermes_hermai_voice"]
    api = next(m for name, m in sys.modules.items() if hasattr(m, "_turn") and hasattr(m, "GUEST_IDLE_S"))
    chats = voice.Chats(home / "hermai" / "chats.json")
    chats.set("kitchen-tab~guest", "s-old", "Kitchen", {"speaker": "", "last": 1})
    seen = []

    def fake_ask_as(text, chat, chats, author, title, about=None, api=None):
        seen.append(chats.get(chat))
        chats.set(chat, "s-new", "", about)
        return "Hi."

    monkeypatch.setattr(voice, "ask_as", fake_ask_as)
    monkeypatch.setattr(voice, "speak", lambda text: b"RIFF")
    import asyncio
    asyncio.run(api._turn("hello", "kitchen-tab", "Kitchen", ""))
    asyncio.run(api._turn("again", "kitchen-tab", "Kitchen", ""))
    assert seen == [None, "s-new"]
