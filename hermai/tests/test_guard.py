import json

import pytest

import guard

D = dict(guard.DEFAULTS)


def call(domain, service, entity_id=None, data=None):
    args = {"domain": domain, "service": service}
    if entity_id is not None:
        args["entity_id"] = entity_id
    if data is not None:
        args["data"] = data
    return args


@pytest.mark.parametrize("args", [
    call("light", "turn_off", "light.kitchen"),
    call("light", "turn_on", data={"area_id": "kitchen"}),
    call("climate", "set_temperature", "climate.hall", {"temperature": 21}),
    call("media_player", "media_pause", "media_player.living_room"),
    call("cover", "open_cover", "cover.living_room_blinds"),
    call("switch", "turn_on", "switch.kettle"),
    call("scene", "turn_on", "scene.movie_night"),
    call("homeassistant", "turn_off", "light.porch"),
])
def test_everyday_calls_pass(args):
    assert guard.check(args, D) is None


@pytest.mark.parametrize("args", [
    call("lock", "unlock", "lock.front_door"),
    call("lock", "open", "lock.front_door"),
    call("lock", "unlock"),
    call("alarm_control_panel", "alarm_disarm", "alarm_control_panel.home", {"code": "1234"}),
    call("alarm_control_panel", "alarm_trigger", "alarm_control_panel.home"),
    call("cover", "open_cover", "cover.garage_door"),
    call("cover", "toggle", "cover.garage_door"),
    call("cover", "set_cover_position", "cover.garage_door", {"position": 50}),
    call("cover", "stop_cover", "cover.garage_door"),
    call("switch", "turn_on", "switch.garage_opener"),
    call("button", "press", "button.garage_door_open"),
    call("homeassistant", "toggle", "cover.garage_door"),
    call("homeassistant", "turn_on", "lock.back_door"),
])
def test_unlocking_disarming_and_opening_the_garage_are_caught(args):
    assert guard.check(args, D)


@pytest.mark.parametrize("args", [
    call("lock", "lock", "lock.front_door"),
    call("lock", "lock", "all"),
    call("lock", "lock", data={"area_id": "downstairs"}),
    call("alarm_control_panel", "alarm_arm_away", "alarm_control_panel.home"),
    call("alarm_control_panel", "alarm_arm_night", "alarm_control_panel.home"),
    call("cover", "close_cover", "cover.garage_door"),
])
def test_securing_is_allowed_by_default(args):
    assert guard.check(args, D) is None


def test_securing_can_be_guarded_too():
    strict = {**D, "allow_securing": False}
    assert guard.check(call("lock", "lock", "lock.front_door"), strict)
    assert guard.check(call("cover", "close_cover", "cover.garage_door"), strict)


@pytest.mark.parametrize("args", [
    call("cover", "open_cover", data={"area_id": "garage"}),
    call("cover", "open_cover", "all"),
    call("cover", "open_cover"),
    call("homeassistant", "turn_on", data={"device_id": "abc123"}),
    call("switch", "turn_on", data={"target": {"area_id": "garage"}}),
])
def test_calls_that_reach_unnamed_things_are_caught(args):
    assert guard.check(args, D)


def test_every_way_of_naming_an_entity_is_read():
    assert guard.check(call("lock", "unlock", data={"entity_id": "lock.front_door"}), D)
    assert guard.check(call("homeassistant", "turn_on", data={"entity_id": ["light.hall", "lock.side"]}), D)
    assert guard.check(call("homeassistant", "turn_on", data={"target": {"entity_id": "lock.side"}}), D)
    assert guard.check(call("homeassistant", "turn_on", "light.hall, lock.side"), D)
    assert guard.check(call("homeassistant", "turn_on", "LOCK.Side"), D)
    assert guard.check(call("homeassistant", "turn_on", data=json.dumps({"entity_id": "lock.side"})), D)


def test_listed_entities_and_scripts_are_guarded():
    s = {**D, "guarded_entities": ["switch.gate"], "guarded_scripts": ["script.let_guest_in", "scene.away_off"]}
    assert guard.check(call("switch", "turn_on", "switch.gate"), s)
    assert guard.check(call("script", "turn_on", "script.let_guest_in"), s)
    assert guard.check(call("script", "let_guest_in"), s)
    assert guard.check(call("scene", "turn_on", "scene.away_off"), s)
    assert guard.check(call("script", "turn_on", "script.bedtime"), s) is None


def test_verdict_blocks_and_explains():
    settings = guard.Settings.__new__(guard.Settings)
    settings.current = lambda: D
    v = guard.verdict("ha_call_service", call("lock", "unlock", "lock.front_door"), settings)
    assert v["action"] == "block"
    assert "lock.unlock on lock.front_door" in v["message"]
    assert guard.verdict("ha_call_service", call("light", "turn_on", "light.hall"), settings) is None
    assert guard.verdict("terminal", {"command": "ls"}, settings) is None


def test_verdict_approval_is_for_this_call_only():
    settings = guard.Settings.__new__(guard.Settings)
    settings.current = lambda: {**D, "mode": "approve"}
    a = guard.verdict("ha_call_service", call("lock", "unlock", "lock.front_door"), settings, call_id="c1")
    b = guard.verdict("ha_call_service", call("lock", "unlock", "lock.front_door"), settings, call_id="c2")
    assert a["action"] == b["action"] == "approve"
    assert a["rule_key"] != b["rule_key"]


@pytest.mark.parametrize("data", ["{not json", 42, ["lock.front_door"]])
def test_unreadable_calls_are_blocked(data):
    settings = guard.Settings.__new__(guard.Settings)
    settings.current = lambda: D
    v = guard.verdict("ha_call_service", call("homeassistant", "turn_on", data=data), settings)
    assert v["action"] == "block"


def test_settings_file(tmp_path):
    path = tmp_path / "guard.json"
    s = guard.Settings(path)
    assert s.current() == D and not s.problem
    path.write_text(json.dumps({"mode": "approve", "guarded_entities": ["Switch.Gate"]}))
    assert s.current()["mode"] == "approve"
    assert s.current()["guarded_entities"] == ["switch.gate"]
    path.write_text(json.dumps({"mode": "allow"}))
    assert s.current() == D and "mode" in s.problem
    path.write_text("{oops")
    assert s.current() == D and s.problem
    path.write_text(json.dumps({"allow_unlocking": True}))
    assert s.current() == D and "unknown" in s.problem
