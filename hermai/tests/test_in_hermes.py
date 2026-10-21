"""The guard loaded by a real Hermes plugin loader, answering the same pre_tool_call check the agent
makes before every tool call. Skipped when Hermes is not installed."""
import os
from pathlib import Path

import pytest

pytest.importorskip("hermes_cli")


@pytest.fixture(scope="module")
def plugins(tmp_path_factory):
    home = tmp_path_factory.mktemp("hermes_home")
    (home / "plugins").mkdir()
    os.symlink(Path(__file__).resolve().parent.parent, home / "plugins" / "hermai")
    (home / "config.yaml").write_text("plugins:\n  enabled:\n    - hermai\n")
    old = os.environ.get("HERMES_HOME")
    os.environ["HERMES_HOME"] = str(home)
    from hermes_cli import plugins
    plugins.discover_plugins()
    yield plugins, home
    if old is None:
        os.environ.pop("HERMES_HOME", None)
    else:
        os.environ["HERMES_HOME"] = old


def test_unlocking_is_blocked(plugins):
    p, _ = plugins
    directive, message = p.get_pre_tool_call_directive(
        "ha_call_service", {"domain": "lock", "service": "unlock", "entity_id": "lock.front_door"})
    assert directive == "block"
    assert "lock.front_door" in message


def test_lights_and_locking_pass(plugins):
    p, _ = plugins
    assert p.get_pre_tool_call_directive(
        "ha_call_service", {"domain": "light", "service": "turn_off", "entity_id": "light.kitchen"}) == (None, None)
    assert p.get_pre_tool_call_directive(
        "ha_call_service", {"domain": "lock", "service": "lock", "entity_id": "lock.front_door"}) == (None, None)


def test_approve_mode_asks(plugins):
    p, home = plugins
    (home / "hermai").mkdir(exist_ok=True)
    (home / "hermai" / "guard.json").write_text('{"mode": "approve"}')
    try:
        directive, message = p.get_pre_tool_call_directive(
            "ha_call_service", {"domain": "cover", "service": "open_cover", "entity_id": "cover.garage_door"})
        assert directive == "approve"
        assert "cover.garage_door" in message
    finally:
        (home / "hermai" / "guard.json").unlink()


def test_pair_command_links_to_the_qr_page(plugins):
    import sys
    out = sys.modules["hermai"]._slash("pair kayla") if "hermai" in sys.modules else None
    if out is None:  # loaded under the plugin loader's own module name
        mod = next(m for name, m in sys.modules.items() if name.endswith("hermai") and hasattr(m, "_slash"))
        out = mod._slash("pair kayla")
    assert "hp1_" in out
    assert "(/api/plugins/hermai/pair?person=kayla)" in out
