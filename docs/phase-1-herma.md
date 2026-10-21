# Phase 1: one herma

One tablet, push-to-talk: hold the button on the screen, or the side key, say something, let go, and Athena answers out loud. The tablet's chat shows in the Hermes WebUI as "Hermai · <room>".

## On Hermes

1. Update the plugin: `sync-plugin hermai --restart` (add `--branch claude/project-thread-bkcgqj` until this is merged). The first time, run `hermes plugins enable hermai` too. The plugin now has the routes the tablets use, at `/api/plugins/hermai/`.
2. Make sure speech is set up in `config.yaml`: `stt:` for hearing and `tts:` for Athena's voice. These are the same settings Petasos uses, so if the Car Thing talks, a herma will too.
3. The dashboard has to be reachable from the tablet, for example `http://10.0.0.20:9119`, with password sign-in turned on. That's already true if the Car Thing works.

## Get the app

Each push that touches `android/` builds the app on GitHub. Open the repo's **Actions** tab, pick the latest **Herma app** run, and download **hermai-herma-apk** at the bottom. Unzip it to get `app-debug.apk`.

Install it on the tablet or phone by opening the file there (allow installs from your browser or Files app when asked), or from a computer with `adb install -r app-debug.apk`. Later builds install over the top, with settings kept.

## Set it up

The first time it opens, the app asks for:

- **Hermes dashboard address:** `http://10.0.0.20:9119`, or the address WireGuard gives you away from home.
- **Username and password:** your dashboard sign-in. The app keeps a renewable sign-in, never the password.
- **Room:** the room this tablet lives in, like Living room. Athena takes "turn off the lights" to mean this room.
- **Talk key (optional):** tap **Set talk key** and press the side key (the Active Key on the Tab Active3). If nothing happens, Samsung is keeping that key for itself: in Android's Settings, under Advanced features > Active Key, set it to no app, then try again. A volume key works too.

Tap **Settings** at the bottom of the main screen (or long-press the room name) to come back to these settings.

## Away from home

With WireGuard on, use the Hermes server's home address (`10.0.0.20:9119`). The peer needs `AllowedIPs` that cover the home network.

## What to try

- "What's the temperature in here?" or "Turn on the living room lights."
- "Unlock the front door." Athena should say she can't, because the guard blocks it.
- Open the Hermes WebUI and find the chat named "Hermai · <room>". Your turns and her replies are there.

## What's not here yet

- Who's speaking: see [voices.md](voices.md). Until a voice is learned, herma turns open Kayla's memories, so only Kayla should use them.
- Wake word (phase 2).
- The tablet signs in as you. Herma-only sign-ins that can do nothing but talk come before the tablets go on the walls for good.
