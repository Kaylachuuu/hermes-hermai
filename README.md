# hermes-hermai

Hermai ("HER-my", plural of herma): the herms Athenians set at the door of each house to watch over it. Here, each herma is a tablet on a room's wall, and together they make Athena the voice of the house.

Each herma talks to Athena on Hermes through Hermai's own backend, and she controls the smart home through Home Assistant. Hermai follows Petasos's design but is kept apart from it: its own plugin, devices, chats, settings and storage, so nothing crosses between the car and the house.

## Status

Phase 0, with the first code: the guard that keeps Athena's hands off locks, the alarm and the garage.

- **Plan:** the living plan, with decisions and the architecture, is the Hermai plan doc: https://claude.ai/code/artifact/2da05236-48f0-4ad1-96a2-6ee914978334
- **Phase 0:** Athena controls the house from the Hermes WebUI. Setup steps: [docs/phase-0-setup.md](docs/phase-0-setup.md).
- **Guard:** what it refuses and how to install it: [docs/guard.md](docs/guard.md).
- **Memory per person:** what Hermai and holonomic agreed: [docs/holonomic.md](docs/holonomic.md).

## The pieces

| Piece | Where | State |
| --- | --- | --- |
| Tablets | Samsung Galaxy Tab Active3, Android 13, one per room, wall-mounted on chargers | Ready |
| Android app | This repo, the Hermai app for the tablets | Phase 1 |
| Voice turns, one chat per herma | This repo, the `hermai` plugin's backend (separate from Petasos) | Phase 1 |
| Home Assistant tools | Official `homeassistant` plugin from the Hermes catalog | Phase 0 |
| Permission guard | This repo, `hermai/`: a Hermes `pre_tool_call` hook in front of `ha_call_service` | Built; per-person settings in phase 3 |
| Voice recognition | Voiceprints on Hermes (SpeechBrain ECAPA) | Phase 3 |
| Memory per person | `hermes-holonomic-memory` 0.34.0 | Built, awaiting merge |
| Tone | Audio to Athena, or an "ears" model on the 16 GB V100 | Phase 4 |

## Phases

0. Athena controls the house from chat.
1. One herma, push-to-talk on the side key.
2. A herma in every room, each with its own chat; wake word as a per-room option.
3. Who's speaking: voiceprints, the People page with per-person permissions and memory, the household chat of room moves.
4. Hearing tone.

## Household

Kayla, Elliot, Ty and Savannah are enrolled. Guests are never remembered and get limited controls. Locks, alarm and garage are never controlled by voice alone: each person's setting is either never, or with a confirmation on Kayla's phone.

## Tests

```sh
python -m pytest hermai/tests
```

`test_in_hermes.py` loads the plugin into a real Hermes and is skipped when Hermes isn't installed.
