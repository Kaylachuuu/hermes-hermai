"""Hermai's own sign-ins for people's phones."""
import json

import people


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def test_a_code_pairs_one_phone_once(tmp_path):
    p = people.People(tmp_path / "people.json", clock=Clock())
    code, expires = p.start_pairing("elliot")
    assert code.startswith(people.CODE_PREFIX) and expires == 1000 + people.PAIR_TTL_S
    assert p.pairing_person(code) == "elliot"
    token, person, device_id = p.claim(code, "Elliot's  iPhone")
    assert token.startswith(people.TOKEN_PREFIX) and person == "elliot"
    assert p.device(token) == {"id": device_id, "person": "elliot", "name": "Elliot's iPhone", "short": False, "face_id_key": None}
    assert p.claim(code, "again") is None and p.pairing_person(code) is None


def test_codes_expire(tmp_path):
    clock = Clock()
    p = people.People(tmp_path / "people.json", clock=clock)
    code, _ = p.start_pairing("kayla")
    clock.t += people.PAIR_TTL_S + 1
    assert p.pairing_person(code) is None and p.claim(code, "x") is None


def test_only_hashes_are_kept(tmp_path):
    p = people.People(tmp_path / "people.json", clock=Clock())
    code, _ = p.start_pairing("kayla")
    token, _, _ = p.claim(code, "Pixel")
    stored = (tmp_path / "people.json").read_text()
    assert code not in stored and token not in stored
    assert oct((tmp_path / "people.json").stat().st_mode)[-3:] == "600"
    assert json.loads(stored)["devices"]


def test_a_phone_can_be_unpaired(tmp_path):
    p = people.People(tmp_path / "people.json", clock=Clock())
    token, _, device_id = p.claim(p.start_pairing("kayla")[0], "Pixel")
    assert [d["id"] for d in p.devices()] == [device_id]
    assert p.revoke(device_id) and p.device(token) is None and not p.revoke(device_id)


def test_strangers_get_nothing(tmp_path):
    p = people.People(tmp_path / "people.json", clock=Clock())
    assert p.device("hm1_nope") is None and p.device("") is None and p.device(None) is None
    assert p.pairing_person("hp1_nope") is None and p.pairing_person("hm1_x") is None


def test_ids_and_names():
    assert people.person_id(" Elliot ") == "elliot" and people.person_id("../x") is None
    assert people.person_id("") is None and people.person_id(None) is None
    assert people.device_name(None) == "Phone" and people.device_name("x" * 99) == "x" * people.DEVICE_NAME_MAX
    assert people.display_name("kayla") == "Kayla"


def test_memory_is_apart_only_when_holonomic_knows_the_person(tmp_path):
    cfg = tmp_path / "holonomic.json"
    assert people.memory_closed(cfg, "kayla") is None  # the owner, always
    assert "one person" in people.memory_closed(cfg, "elliot")  # no file yet
    cfg.write_text(json.dumps({"people": {"elliot": {}}}))
    assert "owner" in people.memory_closed(cfg, "elliot")
    cfg.write_text(json.dumps({"owner": "kayla", "people": {"elliot": {"remembered": False}}}))
    assert people.memory_closed(cfg, "elliot") is None  # not remembered: a guest, which holonomic handles
    assert "isn't among" in people.memory_closed(cfg, "ty")
    cfg.write_text("{not json")
    assert "can't be read" in people.memory_closed(cfg, "elliot")


def test_short_replies_is_kept_per_phone(tmp_path):
    p = people.People(tmp_path / "people.json", clock=Clock())
    token, _, _ = p.claim(p.start_pairing("kayla")[0], "iPhone")
    assert p.device(token)["short"] is False
    assert p.set_short(token, True) and p.device(token)["short"] is True
    assert not p.set_short("hm1_nope", True)
