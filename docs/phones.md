# Phones (Hermai's own sign-ins)

A phone pairs with Hermai once and then talks to Athena with its own token. The token only opens Hermai's phone routes; it can't reach the rest of the dashboard, the WebUI or any other plugin. Phase 2b builds on this for family away from home, with WireGuard in the app.

## Pair a phone

Either:

- Open `http://<hermes>:9119/api/plugins/hermai/pair?person=kayla` in a browser that's signed in to the dashboard. It shows a QR code for the Hermai app to scan, with the server's address in it, and the code as text.
- Or type `/hermai pair kayla` in a WebUI chat. It prints the code; enter the Hermes address and paste the code in the app.

A code works once, for 15 minutes. Person ids are lowercase, like `kayla`, `elliot`, `ty`, `savannah`.

## See and remove phones

`/hermai phones` lists paired phones with their ids. `/hermai phones remove <id>` unpairs one; its token stops working at once.

## Who may talk

Only Kayla's phones, for now. Anyone else's phone can pair, but Athena refuses their turns until Hermes can keep each person's memories apart (see [holonomic.md](holonomic.md#where-stamping-stands-2026-10-19)). Otherwise what they say would land in Kayla's memories, and she might recall Kayla's to them.

## How it works

- `hermai/people.py` keeps paired phones in `<Hermes home>/hermai/people.json` (mode 600): only SHA-256 hashes of codes and tokens, with each phone's person, name and when it was paired and last seen.
- The plugin registers a dashboard sign-in provider, `hermai-devices`, that recognises only Hermai codes (`hp1_…`) and tokens (`hm1_…`). It has no login page and makes no dashboard sessions.
- Hermes' token sign-in seam opens exactly these paths to it: `/api/plugins/hermai/pair/claim` (a code, once), and `/p/hello`, `/p/voice`, `/p/ask`, `/p/audio` (a phone token). Everything else under `/api/plugins/hermai/` still needs the dashboard sign-in.
- Each phone has its own chat, "Hermai · Kayla's iPhone", and Athena is told whose phone it is on every turn.
