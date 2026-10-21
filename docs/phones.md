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

Kayla's phones always. Anyone else's phone talks once both of these are true, and is refused (with the reason) until then:

1. Hermes' API server is running with its key (`API_SERVER_KEY` in `~/.hermes/.env`; Hermai reaches it on loopback, port `API_SERVER_PORT` or 8642). Phone turns go through it labelled `person:<id>`, which is how Athena's memory knows who is speaking. The phone's token decides the id; nothing said in a message can change it.
2. Holonomic is set up for more than one person: `holonomic.json` has `"owner": "kayla"` and lists the person under `people`, for example `"people": {"elliot": {"remembered": true}}`. Each person then gets memories of their own, and `"remembered": false` means Athena keeps nothing for them.

Without both, what they said would land in Kayla's memories, and she might recall Kayla's to them.

The tablets send unlabelled turns, which open Kayla's memories, until they've learned a voice; then they label each turn with who is speaking, or a guest ([voices.md](voices.md)).

## How it works

- `hermai/people.py` keeps paired phones in `<Hermes home>/hermai/people.json` (mode 600): only SHA-256 hashes of codes and tokens, with each phone's person, name and when it was paired and last seen.
- The plugin registers a dashboard sign-in provider, `hermai-devices`, that recognises only Hermai codes (`hp1_…`) and tokens (`hm1_…`). It has no login page and makes no dashboard sessions.
- Hermes' token sign-in seam opens exactly these paths to it: `/api/plugins/hermai/pair/claim` (a code, once), and `/p/hello`, `/p/voice`, `/p/ask`, `/p/audio` (a phone token). Everything else under `/api/plugins/hermai/` still needs the dashboard sign-in.
- Each phone has its own chat, "Hermai · Kayla's iPhone", and Athena is told whose phone it is on every turn.

## The iPhone app on TestFlight

GitHub builds, signs and uploads the iPhone app to TestFlight on each push to main that changes `ios/`
(or from the iPhone app workflow's Run button). It needs these repo secrets, under Settings, Secrets and
variables, Actions:

- `ASC_KEY_ID` and `ASC_ISSUER_ID`: an App Store Connect team key with App Manager access (Users and Access,
  Integrations, Team Keys).
- `ASC_KEY_P8`: the whole text of that key's .p8 file.
- `APPLE_TEAM_ID`: the team id from developer.apple.com, Membership details.

The App IDs `io.github.kaylachuuu.hermai` and `io.github.kaylachuuu.hermai.tunnel` (with Network Extensions)
and an App Store Connect app for the first one come first. Without the secrets the upload step is skipped.

The app says it uses no non-exempt encryption (`ITSAppUsesNonExemptEncryption`), so TestFlight asks no export
questions. WireGuard is standard, publicly available encryption; if the app ever goes on the App Store, check
that answer with Apple's export compliance guidance first.

## Trying the iPhone app with a free Apple account

A free account (a Personal Team in Xcode) can put Hermai on your own iPhone from a Mac, with three limits:
no VPN of its own (Apple gives free accounts no VPN extensions, so use the WireGuard app), the phone is
plugged in to install, and each install stops opening after 7 days until it's installed again.

On the Mac, with Xcode installed:

1. `brew install xcodegen`, then `git clone https://github.com/Kaylachuuu/hermes-hermai.git` and
   `cd hermes-hermai/ios` (until the PR merges, first `git checkout claude/project-thread-bkcgqj`).
2. `xcodegen generate --spec project-personal.yml && open HermaiPersonal.xcodeproj`
3. In Xcode, Settings, Accounts: add your Apple ID. Then select the Hermai target, Signing & Capabilities,
   and pick your name (Personal Team) as the Team.
4. Plug in the iPhone and unlock it. On the phone, turn on Settings, Privacy & Security, Developer Mode
   (it restarts). Choose the iPhone at the top of Xcode and press Run.
5. The first time, the phone says the developer isn't trusted: Settings, General, VPN & Device Management,
   your Apple ID, Trust. Then open Hermai and pair it.

After 7 days, plug it in and press Run again; pairing and settings stay.
