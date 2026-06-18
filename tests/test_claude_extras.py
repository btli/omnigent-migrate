from pathlib import Path

from omnigent_migrate.importers.claude_extras import (
    collect_claude_extras,
    collect_commands,
    collect_hooks,
    collect_permissions,
    collect_plugins,
    read_settings,
)
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


def test_collect_hooks_unsupported() -> None:
    led = Ledger()
    settings = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "x"}]}]}}
    hooks = collect_hooks(settings, led)
    assert hooks == settings["hooks"]
    e = next(e for e in led.entries if e.primitive == "hooks")
    assert e.status is Status.UNSUPPORTED and e.manual_step


def test_collect_commands_degraded(tmp_path: Path) -> None:
    cdir = tmp_path / ".claude" / "commands"
    cdir.mkdir(parents=True)
    (cdir / "deploy.md").write_text("---\ndescription: Deploy it\n---\nRun the deploy steps.\n")
    led = Ledger()
    cmds = collect_commands(tmp_path, led)
    assert cmds is not None and cmds[0]["name"] == "deploy"
    assert cmds[0]["description"] == "Deploy it"
    assert "deploy steps" in cmds[0]["body"]
    assert any(e.primitive == "slash_commands" and e.status is Status.DEGRADED for e in led.entries)


def test_collect_plugins_degraded(tmp_path: Path) -> None:
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "plugin.json").write_text("{}")
    led = Ledger()
    info = collect_plugins(tmp_path, {"enabledPlugins": {"a@b": True}}, led)
    assert info is not None and info["enabledPlugins"] == {"a@b": True}
    assert "plugin.json" in info["plugin_definition"]
    assert any(e.primitive == "plugins" and e.status is Status.DEGRADED for e in led.entries)


def test_coordinator_returns_all_extensions(tmp_path: Path) -> None:
    cdir = tmp_path / ".claude"
    cdir.mkdir()
    (cdir / "settings.json").write_text(
        '{"permissions": {"deny": ["Bash(rm:*)"]}, '
        '"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "x"}]}]}}'
    )
    led = Ledger()
    ext = collect_claude_extras(tmp_path, led)
    assert ext["permissions"]["deny"] == ["Bash(rm:*)"]
    assert "hooks" in ext
