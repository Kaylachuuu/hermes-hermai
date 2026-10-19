# Hermai phase 0: Athena controls the house from chat

Goal: Athena can see and control Home Assistant from the Hermes WebUI. No tablets and no new code yet.

## 1. Make a Home Assistant user for Hermes

1. In Home Assistant, go to **Settings → People → Users → Add user**. Name it `Hermes`, and leave "Administrator" off.
2. Sign in as that user once, open its **Profile → Security → Long-lived access tokens**, and create a token named `Hermes`. Copy it; it's shown only once.

A separate user means you can see what Hermes did in Home Assistant's logbook, and revoke its token without touching yours.

## 2. Install the plugin on Hermes

On the Hermes server, for Athena's profile:

```sh
hermes plugins install homeassistant
```

(Add `-p <profile>` if Athena runs in a named profile.)

Then add to that profile's `.env` (`~/.hermes/.env` by default):

```sh
HASS_TOKEN=<the token from step 1>
HASS_URL=http://<home-assistant-address>:8123
```

Restart Hermes. With the token set, the `homeassistant` toolset turns on by itself: `ha_list_entities`, `ha_get_state`, `ha_list_services`, `ha_call_service`.

Check the token works from the Hermes server:

```sh
curl -H "Authorization: Bearer <token>" http://<home-assistant-address>:8123/api/
```

It should answer `{"message": "API running."}`.

## 3. Try it in the WebUI

Ask Athena, in this order:

1. "What lights are in the kitchen?" (she should list them)
2. "Is the living room light on?"
3. "Turn off the kitchen lights."

If she can't find a room, check its devices have an Area in Home Assistant. Her room lookup matches area and friendly names.

## 4. Leave state-change events off for now

The plugin can also forward Home Assistant events to Athena (`platforms.homeassistant.extra.watch_domains` in `config.yaml`). By default it forwards nothing, and that's right for now. It comes back in a later phase, when Athena speaks up on a herma.

## Locks, alarm and garage

The plugin blocks only shell and scripting services. It does **not** block locks, the alarm panel or garage doors, and Home Assistant gives a non-admin user the same control over devices as an admin. Until Hermai's permission guard exists, Athena can operate them if asked.

The guard is the first piece of Hermai code: a check in front of `ha_call_service` that refuses `lock`, `alarm_control_panel` and garage `cover` entities unless the speaker's setting allows it with a phone confirmation.

## Done when

- Athena lists, reads and controls lights in at least two rooms from the WebUI.
- Home Assistant's logbook shows those changes made by the Hermes user.
