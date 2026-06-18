"""Tests for F1 (transport-less MCP UNSUPPORTED) and F2 (unknown config key disclosure).

TDD: these tests are written BEFORE the fixes and must fail first, then pass after.
"""

from __future__ import annotations

import json
from pathlib import Path

from omnigent_migrate.importers._util import mcp_tool_entry
from omnigent_migrate.importers.claude_code import ClaudeCodeImporter
from omnigent_migrate.importers.codex import CodexImporter
from omnigent_migrate.ledger import Ledger, Status


# ---------------------------------------------------------------------------
# F1 helper unit tests
# ---------------------------------------------------------------------------


def test_mcp_tool_entry_no_transport_returns_none() -> None:
    """mcp_tool_entry({}) must return None — no representable transport."""
    assert mcp_tool_entry({}) is None


def test_mcp_tool_entry_type_only_returns_none() -> None:
    """mcp_tool_entry({'type': 'mcp'}) must return None — still no transport."""
    assert mcp_tool_entry({"type": "mcp"}) is None


def test_mcp_tool_entry_command_returns_dict() -> None:
    """mcp_tool_entry with a command must still return a dict (not None)."""
    result = mcp_tool_entry({"command": "npx", "args": ["-y", "tool"]})
    assert result is not None
    assert result["type"] == "mcp"
    assert result["command"] == "npx"


def test_mcp_tool_entry_url_returns_dict() -> None:
    """mcp_tool_entry with a url must still return a dict (not None)."""
    result = mcp_tool_entry({"url": "https://example.com/mcp"})
    assert result is not None
    assert result["type"] == "mcp"
    assert result["url"] == "https://example.com/mcp"


# ---------------------------------------------------------------------------
# F1 Claude importer: transport-less server -> UNSUPPORTED + absent from tools
# ---------------------------------------------------------------------------


def test_claude_importer_no_transport_server_is_unsupported(tmp_path: Path) -> None:
    """A Claude MCP server with no command/url must be recorded UNSUPPORTED, not TRANSLATED."""
    mcp_data = {"mcpServers": {"weird": {"timeout": 30}}}
    (tmp_path / ".mcp.json").write_text(json.dumps(mcp_data))

    led = Ledger()
    bundle = ClaudeCodeImporter().to_bundle(tmp_path, led)

    # Must NOT appear in tools
    tools = bundle.config.get("tools", {})
    assert "weird" not in tools, "transport-less server must not appear in config tools"

    # Must be recorded as UNSUPPORTED
    unsupported_refs = [
        e.source_ref for e in led.entries
        if e.primitive == "mcp_server" and e.status is Status.UNSUPPORTED
    ]
    assert any("weird" in ref for ref in unsupported_refs), (
        "transport-less server must be recorded UNSUPPORTED"
    )


def test_claude_importer_valid_server_still_translated(tmp_path: Path) -> None:
    """A valid MCP server must still be TRANSLATED even when another entry has no transport."""
    mcp_data = {
        "mcpServers": {
            "good": {"command": "npx", "args": ["-y", "good-tool"]},
            "bad": {"timeout": 30},
        }
    }
    (tmp_path / ".mcp.json").write_text(json.dumps(mcp_data))

    led = Ledger()
    bundle = ClaudeCodeImporter().to_bundle(tmp_path, led)

    tools = bundle.config.get("tools", {})
    assert "good" in tools, "valid server must appear in tools"
    assert "bad" not in tools, "transport-less server must not appear in tools"

    statuses = {
        (e.primitive, e.source_ref.split(":")[-1], e.status)
        for e in led.entries
        if e.primitive == "mcp_server"
    }
    assert (".mcp.json:good", Status.TRANSLATED) in {(s[1], s[2]) for s in statuses} or any(
        e.primitive == "mcp_server" and "good" in e.source_ref and e.status is Status.TRANSLATED
        for e in led.entries
    )
    assert any(
        e.primitive == "mcp_server" and "bad" in e.source_ref and e.status is Status.UNSUPPORTED
        for e in led.entries
    )


# ---------------------------------------------------------------------------
# F1 Codex importer: transport-less server -> UNSUPPORTED + absent from tools
# ---------------------------------------------------------------------------


def test_codex_importer_no_transport_server_is_unsupported(tmp_path: Path) -> None:
    """A Codex MCP server with no command/url must be recorded UNSUPPORTED, not TRANSLATED."""
    config_toml = "[mcp_servers.weird]\ntimeout = 30\n"
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(config_toml)

    led = Ledger()
    bundle = CodexImporter().to_bundle(tmp_path, led, config_path=cfg_path)

    tools = bundle.config.get("tools", {})
    assert "weird" not in tools, "transport-less server must not appear in config tools"

    assert any(
        e.primitive == "mcp_server" and "weird" in e.source_ref and e.status is Status.UNSUPPORTED
        for e in led.entries
    ), "transport-less codex server must be recorded UNSUPPORTED"


# ---------------------------------------------------------------------------
# F2 Codex importer: unknown top-level key -> UNSUPPORTED disclosure
# ---------------------------------------------------------------------------


def test_codex_importer_unknown_key_is_disclosed(tmp_path: Path) -> None:
    """An unknown top-level config key must be disclosed as UNSUPPORTED, not silently dropped."""
    config_toml = "model = \"gpt-4\"\nfoo_bar = 1\n"
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(config_toml)

    led = Ledger()
    CodexImporter().to_bundle(tmp_path, led, config_path=cfg_path)

    unsupported = [
        e for e in led.entries
        if e.primitive == "codex_config" and e.status is Status.UNSUPPORTED
    ]
    assert unsupported, "unknown config key must produce a codex_config UNSUPPORTED entry"
    assert any("foo_bar" in e.note for e in unsupported), (
        "UNSUPPORTED note must name the unknown key"
    )


def test_codex_importer_unknown_history_key_is_disclosed(tmp_path: Path) -> None:
    """history = {} is an unknown key that must be disclosed."""
    config_toml = "[history]\npersistence = \"none\"\n"
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(config_toml)

    led = Ledger()
    CodexImporter().to_bundle(tmp_path, led, config_path=cfg_path)

    assert any(
        e.primitive == "codex_config" and e.status is Status.UNSUPPORTED
        and "history" in e.note
        for e in led.entries
    ), "unknown 'history' key must be disclosed as UNSUPPORTED"


def test_codex_importer_known_keys_not_in_residue(tmp_path: Path) -> None:
    """Known keys (model, mcp_servers, etc.) must NOT produce an extra UNSUPPORTED residue row."""
    config_toml = 'model = "gpt-4"\n[mcp_servers.gh]\ncommand = "npx"\n'
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(config_toml)

    led = Ledger()
    CodexImporter().to_bundle(tmp_path, led, config_path=cfg_path)

    # No codex_config UNSUPPORTED entry (model + mcp_servers are known)
    residue_entries = [
        e for e in led.entries
        if e.primitive == "codex_config" and e.status is Status.UNSUPPORTED
    ]
    assert not residue_entries, (
        "known keys must not produce a residue UNSUPPORTED entry"
    )
