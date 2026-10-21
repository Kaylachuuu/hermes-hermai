"""Who is speaking to a herma, by the sound of their voice.

Each person teaches a herma their voice once: ``/hermai voices learn elliot kitchen`` turns the
kitchen herma's next few recordings into samples of Elliot's voice instead of turns with Athena.
After that, every recording a herma sends is compared with the voices learned so far. A close
enough match says who is speaking; anything else is a guest.

A voiceprint is a fingerprint of how a voice sounds (192 numbers from NVIDIA's TitaNet small
speaker model, run with sherpa-onnx, which Hermes' wake word engine uses too). It is a good guess,
not proof: a recording of someone's voice can pass for them. So a match only decides whose
memories Athena may use; it never unlocks, disarms or opens anything.

Voiceprints live in ``<Hermes home>/hermai/voices.json``, readable by Hermes alone. The model is
downloaded once, about 40 MB, to ``<Hermes home>/cache/hermai/``.
"""
from __future__ import annotations

import array
import hashlib
import io
import json
import math
import threading
import time
import uuid
import wave
from pathlib import Path

MODEL_NAME = "nemo_en_titanet_small.onnx"
MODEL_URL = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/"
             + MODEL_NAME)
MODEL_SHA256 = "ad4a1802485d8b34c722d2a9d04249662f2ece5d28a7a039063ca22f515a789e"

SAMPLES = 5            # recordings it takes to learn a voice
MIN_SECONDS = 1.5      # shorter recordings say too little about the voice
LEARN_TTL_S = 10 * 60  # how long a herma waits for the samples once asked to learn
# Cosine similarity with a person's voice. On test recordings the same speaker scored 0.72 to 0.84
# and different speakers 0.34 at most; a match also has to beat the next closest voice by MARGIN.
MATCH = 0.55
MARGIN = 0.12
SAME_SPEAKER = 0.45    # while learning: a sample less like the others than this is someone else
GUEST = "guest"        # not a person's id; holonomic opens no memories for "person:guest"


class VoiceprintError(RuntimeError):
    pass


def _unit(vector) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / norm for x in vector]


def _dot(a, b) -> float:
    return sum(x * y for x, y in zip(a, b))


def centroid(samples: list[list[float]]) -> list[float]:
    return _unit([sum(col) for col in zip(*samples)])


def pcm(audio: bytes) -> tuple[int, list[float]]:
    """A WAV recording's sample rate and its first channel as floats from -1 to 1."""
    try:
        with wave.open(io.BytesIO(audio)) as w:
            if w.getsampwidth() != 2:
                raise VoiceprintError("recordings are 16-bit WAV")
            rate, channels = w.getframerate(), w.getnchannels()
            frames = array.array("h", w.readframes(w.getnframes()))
    except (wave.Error, EOFError) as exc:
        raise VoiceprintError(f"not a WAV recording ({exc})") from None
    return rate, [x / 32768.0 for x in frames[::channels]]


def engine_installed() -> bool:
    import importlib.util
    return importlib.util.find_spec("sherpa_onnx") is not None


class Embedder:
    """The speaker model, loaded on first use. Installing sherpa-onnx (Hermes' ``wake-sherpa``
    extra) and downloading the model happen then too, once."""

    def __init__(self, cache: Path) -> None:
        self.cache = cache
        self._extractor = None
        self._lock = threading.Lock()

    def _model(self) -> Path:
        path = self.cache / MODEL_NAME
        if path.is_file():
            return path
        import urllib.request
        self.cache.mkdir(parents=True, exist_ok=True)
        part = path.with_suffix(f".{uuid.uuid4().hex[:8]}.part")  # two downloads at once can't mix
        urllib.request.urlretrieve(MODEL_URL, part)
        digest = hashlib.sha256(part.read_bytes()).hexdigest()
        if digest != MODEL_SHA256:
            part.unlink(missing_ok=True)
            raise VoiceprintError(f"the downloaded voice model isn't the expected one (sha256 {digest[:12]})")
        part.replace(path)
        return path

    def _load(self):
        if self._extractor is None:
            try:
                import sherpa_onnx
            except ImportError:
                try:
                    import pm
                    pm.ensure_import("wake-sherpa")
                    import sherpa_onnx
                except Exception as exc:
                    raise VoiceprintError("sherpa-onnx isn't installed; run "
                                          f"`hermes pm install --extra wake-sherpa` ({exc})"[:300]) from None
            config = sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(self._model()), num_threads=1)
            self._extractor = sherpa_onnx.SpeakerEmbeddingExtractor(config)
        return self._extractor

    def embed(self, audio: bytes) -> list[float] | None:
        """The voiceprint of one recording, or None when it's too short to tell."""
        rate, samples = pcm(audio)
        if len(samples) < MIN_SECONDS * rate:
            return None
        with self._lock:
            extractor = self._load()
            stream = extractor.create_stream()
            stream.accept_waveform(rate, samples)
            stream.input_finished()
            return _unit(extractor.compute(stream))


class Voices:
    """The voices learned, and any herma waiting for samples:
    ``{"people": {person: {"samples": [...], "learned": t}}, "learning": {herma: {...}}}``.
    A file, not memory: the ``/hermai`` command and the herma routes can run in different processes."""

    def __init__(self, path: Path, clock=time.time) -> None:
        self.path = path
        self.clock = clock
        self._lock = threading.Lock()

    def people(self) -> dict[str, int]:
        """Each person whose voice is learned, with how many samples."""
        with self._lock:
            return {p: len(v["samples"]) for p, v in self._read()["people"].items()}

    def forget(self, person: str) -> bool:
        with self._lock:
            data = self._read()
            found = data["people"].pop(person, None) is not None
            data["learning"] = {h: v for h, v in data["learning"].items() if v.get("person") != person}
            self._write(data)
            return found

    def start_learning(self, herma: str, person: str) -> None:
        """The herma's next SAMPLES recordings are ``person``'s voice. Starts the voice afresh."""
        with self._lock:
            data = self._read()
            data["learning"][herma] = {"person": person, "samples": [], "until": int(self.clock()) + LEARN_TTL_S}
            self._write(data)

    def stop_learning(self, herma: str) -> bool:
        with self._lock:
            data = self._read()
            found = data["learning"].pop(herma, None) is not None
            self._write(data)
            return found

    def learning(self, herma: str) -> dict | None:
        """``{"person", "have", "until"}`` while the herma is learning a voice."""
        with self._lock:
            entry = self._read()["learning"].get(herma)
        if not entry:
            return None
        return {"person": entry["person"], "have": len(entry["samples"]), "until": entry["until"]}

    def add_sample(self, herma: str, voiceprint: list[float]) -> tuple[str, str, int]:
        """Takes one recording while learning: ``(outcome, person, samples still wanted)``, where
        outcome is "more", "done" or "different" (it didn't sound like the samples before it)."""
        with self._lock:
            data = self._read()
            entry = data["learning"].get(herma)
            if not entry:
                return "none", "", 0
            person, samples = entry["person"], entry["samples"]
            if samples and _dot(centroid(samples), voiceprint) < SAME_SPEAKER:
                return "different", person, SAMPLES - len(samples)
            samples.append([round(x, 6) for x in voiceprint])
            if len(samples) < SAMPLES:
                self._write(data)
                return "more", person, SAMPLES - len(samples)
            data["people"][person] = {"samples": samples, "learned": int(self.clock())}
            del data["learning"][herma]
            self._write(data)
            return "done", person, 0

    def match(self, voiceprint: list[float]) -> tuple[str | None, float]:
        """Whose voice this is, or None for a guest, with how close the best match was."""
        with self._lock:
            people = self._read()["people"]
        scores = sorted(((_dot(centroid(v["samples"]), voiceprint), p) for p, v in people.items()
                         if v.get("samples")), reverse=True)
        if not scores:
            return None, 0.0
        best, person = scores[0]
        runner_up = scores[1][0] if len(scores) > 1 else -1.0
        if best >= MATCH and best - runner_up >= MARGIN:
            return person, best
        return None, best

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        for table in ("people", "learning"):
            if not isinstance(data.get(table), dict):
                data[table] = {}
        now = self.clock()
        data["learning"] = {h: v for h, v in data["learning"].items()
                            if isinstance(v, dict) and v.get("until", 0) > now and isinstance(v.get("samples"), list)}
        data["people"] = {p: v for p, v in data["people"].items()
                          if isinstance(v, dict) and isinstance(v.get("samples"), list)}
        return data

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data) + "\n", encoding="utf-8")
        tmp.chmod(0o600)
        tmp.replace(self.path)


def learn_prompt(outcome: str, name: str, left: int) -> str:
    """What the herma says back while learning a voice."""
    if outcome == "short":
        return f"That was a bit short, {name}. Say a full sentence or two."
    if outcome == "different":
        return f"That didn't sound like the same person. {name}, say something else, please."
    if outcome == "done":
        return f"Thanks, {name}. I'll know your voice now."
    return f"Got it. {left} more, {name}. Say anything you like, a sentence or two."
