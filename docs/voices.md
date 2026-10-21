# Who's speaking: voices on the hermas

Each person teaches the hermas their voice once. After that, every recording a herma sends is matched against the voices it knows. A match tells Athena who is speaking and opens that person's memories. Anyone the hermas don't recognise is a guest: their chat opens no memories, and nothing they say is remembered.

## What it needs

- **Hermes' API server**, with `API_SERVER_KEY` set, the same as for other people's phones. That's the only way Hermai can label a turn with who is speaking. Without it the hermas keep working the old way (unlabelled, so Kayla's memories) even when voices are learned.
- **Memory per person** in `holonomic.json`: `owner: "kayla"` and each other person under `people`. A person the hermas recognise but holonomic doesn't list gets no memories, the same as a guest.
- **sherpa-onnx**, which Hermes' wake word engine uses too. If it's missing, `/hermai voices learn` says so. Install it with `hermes pm install --extra wake-sherpa`.
- **The voice model**, NVIDIA's TitaNet small (about 40 MB, CC-BY-4.0). It's downloaded once to `<Hermes home>/cache/hermai/` and checked against a known hash.

## Teaching a voice

1. In a Hermes chat, run `/hermai voices learn elliot Kitchen`. The room is the herma's room. You can leave it out when there's only one herma.
2. Elliot presses talk on that herma and says a sentence or two, five times. The herma says how many recordings are left. None of this goes to Athena.
3. The herma says "Thanks, Elliot. I'll know your voice now."

Some recordings don't count. A very short one is turned away. So is one that sounds like a different person from the earlier samples, in case someone else grabbed the tablet. The herma stops waiting after ten minutes. `/hermai voices stop Kitchen` stops it sooner.

Learning a voice on the tablet it'll be used on works best, because the samples carry that room's microphone and echo. One herma is enough to start. A voice learned on one herma works on all of them.

## Day to day

- `/hermai voices` lists the voices learned.
- `/hermai voices learn <person>` again replaces that person's voice, once the new samples are in.
- `/hermai voices forget <person>` deletes their voice. To the hermas they're a guest again.

Each speaker has their own chat on each herma, such as "Hermai · Kitchen · Elliot", so one person never sees another's conversation. A guest's chat starts afresh after half an hour unused. Typing on a herma's screen has no voice, so a typed turn is a guest's once any voice is learned.

## What a voice can't do

A voiceprint is a good guess, not proof. Someone could play a recording of your voice to a herma. So a match only decides whose memories Athena uses and how she talks to them. It never unlocks, disarms or opens anything. The guard refuses those on every herma turn, whoever's voice it is. Face ID on your own phone is the only way through.

## How the matching works

Each recording becomes a voiceprint: 192 numbers that describe how the voice sounds. A person's voice is the average of their five samples. A recording is that person's when it's close enough (cosine similarity 0.55 or more) and clearly closer to them than to anyone else (by 0.12). On test recordings, the same speaker scored 0.72 to 0.84 and different speakers 0.34 at most.

Voiceprints are kept in `<Hermes home>/hermai/voices.json`, readable by Hermes alone. They aren't recordings: the audio itself isn't kept.
