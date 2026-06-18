from pathlib import Path

from omnigent_migrate.importers.claude_extras import collect_permissions, read_settings
from omnigent_migrate.ledger import Ledger, Status


def test_collect_permissions_carries_and_degrades() -> None:
    led = Ledger()
    settings = {"permissions": {"allow": ["Read"], "deny": ["Bash(rm:*)"], "defaultMode": "acceptEdits"}}
    perms = collect_permissions(settings, led)
    assert perms == settings["permissions"]
    e = next(e for e in led.entries if e.primitive == "permissions")
    assert e.status is Status.DEGRADED and e.manual_step


def test_collect_permissions_absent_is_noop() -> None:
    led = Ledger()
    assert collect_permissions({}, led) is None
    assert led.entries == []


def test_read_settings_merges_local(tmp_path: Path) -> None:
    cdir = tmp_path / ".claude"
    cdir.mkdir()
    (cdir / "settings.json").write_text('{"permissions": {"allow": ["Read"]}}')
    (cdir / "settings.local.json").write_text('{"enabledPlugins": {"x@y": true}}')
    s = read_settings(tmp_path)
    assert s["permissions"]["allow"] == ["Read"]
    assert s["enabledPlugins"] == {"x@y": True}
