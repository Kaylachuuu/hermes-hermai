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

    async def fake_ask(text, herma, room, chats, url=None):
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

    async def fake_ask(text, herma, room, chats, url=None):
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
