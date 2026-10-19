# The lock, alarm and garage guard

The Home Assistant plugin gives Athena one tool, `ha_call_service`, that can call any Home Assistant service. The Hermai plugin checks every such call before it runs.

| Call | What happens |
| --- | --- |
| Unlock or open a lock | Refused |
| Disarm or trigger the alarm | Refused |
| Open, stop, move or toggle the garage door, or press its opener | Refused |
| Lock a door, arm the alarm, close the garage | Allowed |
| A call aimed at an area, a device or `all` that could reach a lock, cover, switch or button | Refused, since the guard can't see what it reaches |
| A call the guard can't read | Refused |
| Lights, climate, media and everything else | Allowed |

When it refuses, Athena is told why and to send the person to the Home Assistant app.

## Install

On the Hermes server, as the user Hermes runs as:

```sh
sync-plugin hermai --restart
```

Then turn it on with `hermes plugins enable hermai` (or from the `hermes plugins` menu) and restart again. `/hermai` in chat shows what the guard allows.

## Settings

Optional, in `<Hermes home>/hermai/guard.json`. Changes apply on the next call; no restart needed.

```json
{
  "mode": "block",
  "allow_securing": true,
  "guarded_entities": ["cover.overhead_door"],
  "guarded_scripts": ["script.let_guest_in"]
}
```

- `mode`: `"block"` refuses. `"approve"` asks on Hermes' approval prompt instead. Each approval covers only that one call, so "always" still asks again next time.
- `allow_securing`: `false` guards locking, arming and closing too.
- `guarded_entities`: anything else to treat like a lock. The garage is found by `garage` in a cover, switch, button or input_boolean's entity id. A garage door named otherwise belongs here.
- `guarded_scripts`: scripts, scenes or automations that unlock or open something. Others run freely.

A broken file is ignored and the defaults are used, so a typo never loosens the guard. `/hermai` shows the problem.

## Limits

- It guards `ha_call_service` only. If Athena has a terminal tool and the Home Assistant token in her environment, she could reach the API another way. Keep the token out of tools she can run commands with.
- Per-person settings (never, or confirm on Kayla's phone) come with voice recognition in phase 3. Until then the setting above applies to everyone.
