"""Hermai's guard: keeps Athena's hands off the locks, the alarm and the garage.

The Home Assistant plugin gives Athena one tool that can call any Home Assistant service
(``ha_call_service``). This module decides, before each call runs, whether it would unlock, disarm
or open something, and if so refuses it or asks for a human's approval, as the settings say.

Securing the house stays allowed by default: locking a door, arming the alarm and closing the garage.
Anything the guard cannot be sure about, such as a call aimed at a whole area, is treated as unsafe.

Settings live in ``<Hermes home>/hermai/guard.json``; every key is optional:

    {
      "mode": "block",                       # "block", or "approve" to ask on Hermes' approval prompt
      "allow_securing": true,                # lock, arm and close without asking
      "guarded_entities": ["switch.gate"],   # more entities to treat like a lock
      "guarded_scripts": ["script.unlock"]   # scripts, scenes or automations that unlock or open
    }
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

TOOL = "ha_call_service"

GUARDED_DOMAINS = frozenset({"lock", "alarm_control_panel"})
# Domains where an entity whose id names the garage is taken to be the garage door or its opener.
GARAGE_DOMAINS = frozenset({"cover", "switch", "button", "input_boolean"})
# Domains that can reach a guarded entity when a call names an area, a device or everything.
BROAD_REACH = frozenset({"lock", "alarm_control_panel", "cover", "switch", "button", "homeassistant"})
# Ways of aiming a call at many entities at once.
BROAD_KEYS = ("area_id", "device_id", "floor_id", "label_id")
# Domains whose items can do anything; guarded only when listed in guarded_scripts.
RUNNERS = frozenset({"script", "scene", "automation"})

SECURING = frozenset({
    ("lock", "lock"),
    ("alarm_control_panel", "alarm_arm_away"), ("alarm_control_panel", "alarm_arm_home"),
    ("alarm_control_panel", "alarm_arm_night"), ("alarm_control_panel", "alarm_arm_vacation"),
    ("alarm_control_panel", "alarm_arm_custom_bypass"),
    ("cover", "close_cover"),
})

DEFAULTS = {"mode": "block", "allow_securing": True, "guarded_entities": [], "guarded_scripts": []}

BLOCKED = ("Not allowed: Hermai keeps locks, the alarm and the garage out of reach, so {what} was not done. "
           "Tell the person to use the Home Assistant app for this.")
APPROVE = "Athena wants to {what}. Allow it this once?"


class Settings:
    """``guard.json``, read again whenever it changes. A missing file means the defaults; a broken
    one also means the defaults, and ``problem`` says what is wrong, so a typo never loosens the guard."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.problem = ""
        self._stamp = None
        self._values = dict(DEFAULTS)

    def current(self) -> dict:
        try:
            stat = self.path.stat()
            stamp = (stat.st_mtime_ns, stat.st_size)
        except FileNotFoundError:
            self._stamp, self._values, self.problem = None, dict(DEFAULTS), ""
            return self._values
        if stamp != self._stamp:
            self._stamp = stamp
            try:
                self._values, self.problem = parse(json.loads(self.path.read_text(encoding="utf-8"))), ""
            except (OSError, ValueError) as e:
                self._values, self.problem = dict(DEFAULTS), f"{self.path}: {e}; using the defaults"
        return self._values


def parse(raw) -> dict:
    """Settings from the file's contents, with each key checked. Raises ValueError on a bad value."""
    if not isinstance(raw, dict):
        raise ValueError("expected an object")
    unknown = set(raw) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"unknown settings: {', '.join(sorted(unknown))}")
    values = {**DEFAULTS, **raw}
    if values["mode"] not in ("block", "approve"):
        raise ValueError('mode is "block" or "approve"')
    if not isinstance(values["allow_securing"], bool):
        raise ValueError("allow_securing is true or false")
    for key in ("guarded_entities", "guarded_scripts"):
        items = values[key]
        if not (isinstance(items, list) and all(isinstance(i, str) and "." in i for i in items)):
            raise ValueError(f"{key} is a list of entity ids, like \"switch.gate\"")
        values[key] = [i.strip().lower() for i in items]
    return values


def _data(args: dict) -> dict:
    data = args.get("data")
    if isinstance(data, str):  # XML tool calling sends data as a JSON string
        data = json.loads(data) if data.strip() else {}
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("data is not an object")
    return data


def _ids(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip().lower() for part in value.split(",") if part.strip()]
    if isinstance(value, list):
        return [part.strip().lower() for part in value if isinstance(part, str) and part.strip()]
    raise ValueError("entity_id is not a string or a list")


def targets(args: dict) -> tuple[list[str], bool]:
    """The entities a call names, and whether it also reaches further (an area, a device, everything)."""
    data = _data(args)
    target = data.get("target") if isinstance(data.get("target"), dict) else {}
    ids = _ids(args.get("entity_id")) + _ids(data.get("entity_id")) + _ids(target.get("entity_id"))
    broad = "all" in ids or any(data.get(k) or target.get(k) for k in BROAD_KEYS)
    return [i for i in ids if i != "all"], broad


def is_guarded_entity(entity: str, settings: dict) -> bool:
    domain = entity.split(".", 1)[0]
    if domain in GUARDED_DOMAINS or entity in settings["guarded_entities"]:
        return True
    if domain in RUNNERS:
        return entity in settings["guarded_scripts"]
    return domain in GARAGE_DOMAINS and "garage" in entity


def check(args: dict, settings: dict) -> str | None:
    """What a call would do to a guarded thing, in a few words, or None when it is safe."""
    domain = str(args.get("domain") or "").strip().lower()
    service = str(args.get("service") or "").strip().lower()
    entities, broad = targets(args)
    if settings["allow_securing"] and (domain, service) in SECURING:
        return None  # these only ever lock, arm or close, however many things they reach
    guarded = [e for e in entities if is_guarded_entity(e, settings)]
    if domain in RUNNERS and f"{domain}.{service}" in settings["guarded_scripts"]:
        guarded.append(f"{domain}.{service}")
    what = f"{domain}.{service}"
    if guarded:
        return f"{what} on {', '.join(guarded)}"
    if domain in GUARDED_DOMAINS:
        return what
    if domain in BROAD_REACH and (broad or not entities):
        return f"{what} on everything it reaches"
    return None


def verdict(tool_name: str, args, settings: Settings, call_id: str = "") -> dict | None:
    """The pre_tool_call answer for one tool call. Fails closed: if the call can't be read, it's blocked.

    An approval is keyed to this one call, so answering "always" or "session" on Hermes' prompt still
    allows only this call: the next unlock asks again."""
    if tool_name != TOOL:
        return None
    values = settings.current()
    try:
        what = check(args if isinstance(args, dict) else {}, values)
    except (ValueError, TypeError) as e:
        return {"action": "block", "message": f"Not allowed: Hermai couldn't read this call ({e}), so it wasn't run."}
    if what is None:
        return None
    if values["mode"] == "approve":
        return {"action": "approve", "message": APPROVE.format(what=what), "rule_key": f"hermai:{what}:{call_id or uuid.uuid4().hex}"}
    return {"action": "block", "message": BLOCKED.format(what=what)}
