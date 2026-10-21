import io
import os
import wave
from pathlib import Path

import pytest

import voices


def _v(*xs):
    """A voiceprint pointing mostly along the axes given."""
    vec = [0.0] * 8
    for i, x in enumerate(xs):
        vec[i] = x
    return voices._unit(vec)


ELLIOT = [_v(1, 0.1 * i, 0.05) for i in range(5)]
TY = [_v(0.1, 1, 0.1 * i) for i in range(5)]


def _learn(store, herma, person, samples):
    store.start_learning(herma, person)
    outcomes = [store.add_sample(herma, s)[0] for s in samples]
    return outcomes


def test_a_voice_takes_five_samples(tmp_path):
    store = voices.Voices(tmp_path / "voices.json")
    assert _learn(store, "kitchen", "elliot", ELLIOT) == ["more"] * 4 + ["done"]
    assert store.people() == {"elliot": 5}
    assert store.learning("kitchen") is None
    assert oct(os.stat(tmp_path / "voices.json").st_mode & 0o777) == "0o600"


def test_a_sample_from_someone_else_is_turned_away(tmp_path):
    store = voices.Voices(tmp_path / "voices.json")
    store.start_learning("kitchen", "elliot")
    assert store.add_sample("kitchen", ELLIOT[0])[0] == "more"
    assert store.add_sample("kitchen", TY[0]) == ("different", "elliot", 4)
    assert store.learning("kitchen")["have"] == 1


def test_matching_knows_each_voice_and_calls_the_rest_guests(tmp_path):
    store = voices.Voices(tmp_path / "voices.json")
    _learn(store, "kitchen", "elliot", ELLIOT)
    _learn(store, "kitchen", "ty", TY)
    assert store.match(_v(1, 0.2, 0))[0] == "elliot"
    assert store.match(_v(0, 1, 0.2))[0] == "ty"
    assert store.match(_v(0, 0, 1))[0] is None          # nobody's
    assert store.match(_v(1, 1, 0.1))[0] is None        # too close to call between the two


def test_no_voices_means_no_match(tmp_path):
    assert voices.Voices(tmp_path / "voices.json").match(_v(1))[0] is None


def test_learning_stops_waiting(tmp_path):
    now = [1000.0]
    store = voices.Voices(tmp_path / "voices.json", clock=lambda: now[0])
    store.start_learning("kitchen", "elliot")
    now[0] += voices.LEARN_TTL_S + 1
    assert store.learning("kitchen") is None
    assert store.add_sample("kitchen", ELLIOT[0])[0] == "none"


def test_forgetting_a_voice(tmp_path):
    store = voices.Voices(tmp_path / "voices.json")
    _learn(store, "kitchen", "elliot", ELLIOT)
    assert store.forget("elliot") and not store.forget("elliot")
    assert store.people() == {}


def _wav(seconds, rate=16000):
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\0\0" * int(seconds * rate))
    return out.getvalue()


def test_short_recordings_have_no_voiceprint(tmp_path):
    assert voices.Embedder(tmp_path).embed(_wav(0.5)) is None  # never loads the model


def test_a_non_wav_is_refused():
    with pytest.raises(voices.VoiceprintError):
        voices.pcm(b"not audio")


# The real model on real voices, when both are at hand: HERMAI_VOICE_MODEL is the .onnx file and
# HERMAI_TEST_VOICES a folder of <speaker>-*.wav recordings, 16 kHz mono, three or more each.
@pytest.mark.skipif(not (os.environ.get("HERMAI_VOICE_MODEL") and os.environ.get("HERMAI_TEST_VOICES")),
                    reason="no voice model or test voices")
def test_the_model_tells_real_voices_apart(tmp_path):
    pytest.importorskip("sherpa_onnx")
    model = Path(os.environ["HERMAI_VOICE_MODEL"])
    (tmp_path / voices.MODEL_NAME).symlink_to(model)
    embedder = voices.Embedder(tmp_path)
    by_speaker = {}
    for f in sorted(Path(os.environ["HERMAI_TEST_VOICES"]).glob("*.wav")):
        by_speaker.setdefault(f.name.split("-")[0], []).append(embedder.embed(f.read_bytes()))
    store = voices.Voices(tmp_path / "voices.json")
    for speaker, prints in by_speaker.items():
        store._write({"people": {**store._read()["people"], speaker: {"samples": prints[:-1], "learned": 0}},
                      "learning": {}})
    for speaker, prints in by_speaker.items():
        assert store.match(prints[-1])[0] == speaker, (speaker, store.match(prints[-1]))
