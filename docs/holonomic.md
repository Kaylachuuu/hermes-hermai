# Holonomic and Hermai: who is speaking

Holonomic (hermes-holonomic-memory) keeps a separate memory store per person from 0.34.0. This is how Hermai tells it who is speaking. The holonomic side follows `persona/multi-user.md` sections 6, 6.1 and 7 in the project files.

## What Hermai adds or changes (decided by Kayla)

1. **Identity is a voiceprint, attached per turn.** Each turn from a herma carries the speaker as a person id plus a confidence. A confident match opens that person's store for that turn; an unsure or unknown voice opens no personal store. This keeps the design's rule that a store never opens from words in a message, since the match is attached by Hermes, not said.
2. **The speaker can change every turn in the same session.** A room's chat is one Hermes session shared by everyone in the room. The open store follows the turn's speaker, not the session. Recall and writes for a turn use only that speaker's store. Core already gives providers `turn_author` in `sync_turn` and `author_id` in `on_turn_start` (`agent/memory_provider.py:133`, `:154`).
3. **No room store.** The room's own record is the Hermes chat history. Holonomic keeps nothing per room.
4. **Guests are never remembered.** Unknown voices get no store and nothing is written about them.
5. **Per-person "remembered by Athena" setting.** Set on a People page in the dashboard (Hermai builds the page). When it's off for a person, holonomic writes nothing for them. Default proposal: it also recalls nothing from their store, so off means treated like a guest except she knows their name. Confirm with Kayla if you'd rather keep recall.
6. **Person ids.** `kayla` (the existing owner store), `elliot`, `ty`, `savannah`. The mapping from a voiceprint to a person id lives in Hermai's config, not in anything she can write.
7. **Recall in shared rooms.** Decided: she may recall the speaker's own memories aloud, but stays discreet with private things when others might hear. Hermai's shared-device note tells her this; nothing needed in holonomic unless you see a place it belongs.
8. **Backups and restores** stay command line or dashboard only, as section 6.1 has them. Never by voice.

## Dependency on the Hermai side (not yours, for awareness)

Petasos sends each turn over the dashboard's `/api/ws`, and a Hermai backend built the same way would too, and Hermes refuses a client-stamped author there (`tui_gateway/methods_prompt.py:762`, error 4124: "turn author is stamped by the gateway, never by a client"). Hermai's backend will need a server-side way to stamp the speaker on a turn. Hermai owns that; holonomic just needs to read the author core passes it.

## Timing

Needed before Hermai phase 3 (voice recognition). Phases 0 to 2 run single-speaker and don't need it. Suggested order: per-person stores with the isolation test, then per-turn store switching, then backup/restore per audience, then the shared idle scheduler.

## Agreed contract (hermes-entelechy, 2026-10-19)

- Hermai stamps each herma turn's author id as `person:<id>` (`kayla`, `elliot`, `ty`, `savannah`) only on a confident voiceprint match, else `person:guest`. Holonomic reads it from `on_turn_start` `author_id` / `sync_turn` `turn_author`.
- Once a session has had one `person:` turn, an unstamped turn in it opens no store. Sessions never stamped keep the owner store as today.
- The People page writes `holonomic.json`: `owner` (`"kayla"`) and `people` (`{"elliot": {"remembered": true}, ...}`). `remembered: false` means nothing written or recalled.
- Holonomic's own plan is in the project files at `hermai/holonomic-multi-user-plan.md`.
- Update 2026-10-19 (holonomic 0.34.0 built, awaiting Kayla's merge): Hermai must stamp EVERY herma turn, `person:<id>` or `person:guest`. An unstamped first turn of a new room session would open Kayla's store. Until voice recognition exists (phases 1-2), herma turns are stamped `person:guest`, so nothing said at a herma is remembered yet. Libraries are per person; subagents get no memory once people are set.

## Where stamping stands (2026-10-19)

Not built yet. Herma and phone turns go over `/api/ws` like Petasos's and carry no author, so once holonomic 0.34.0 is merged they open Kayla's store. That's right while Kayla is the only one using them, and wrong for anyone else. Until stamping works:

- Paired phones belonging to anyone but Kayla can pair but are refused when they try to talk (`people.py`, `/p/` routes).
- The tablets should only be used by Kayla.

The likely path: Hermes' API server takes an `author` object on `POST /api/sessions/{id}/chat` (`gateway/platforms/api_server.py`, `_request_turn_author`), which labels the turn for memory. Hermai would send person turns there from the server side, with the author from the phone's token or the voiceprint match. That needs the API server running with its key, so it's checked before phase 2b.
