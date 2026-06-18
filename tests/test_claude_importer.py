from pathlib import Path

from omnigent_migrate.importers.claude_code import ClaudeCodeImporter
from omnigent_migrate.ledger import Ledger, Status

FIXTURE = Path(__file__).parent / "fixtures" / "claude_project"


def test_imports_core_primitives() -> None:
    led = Ledger()
    bundle = ClaudeCodeImporter().to_bundle(FIXTURE, led)
    # memory -> prompt
    assert "lead for the demo app" in bundle.config["prompt"]
    # subagent -> agents/ + tools.agents + spawn (orchestrator shape)
    assert "reviewer" in bundle.agents
    assert bundle.agents["reviewer"]["executor"]["config"]["harness"] == "claude-sdk"  # sonnet -> claude-sdk
    assert bundle.config["spawn"] is True
    assert bundle.config["tools"]["agents"] == ["reviewer"]
    # MCP server -> tools.<name>
    assert bundle.config["tools"]["github"]["type"] == "mcp"
    assert bundle.config["tools"]["github"]["command"] == "npx"
    # skills recorded as translated-in-place
    statuses = {(e.primitive, e.status) for e in led.entries}
    assert ("skills", Status.TRANSLATED) in statuses
    assert ("subagent", Status.TRANSLATED) in statuses
    # honest scope: the report discloses what was NOT examined
    assert any("Hooks" in n for n in led.notes)


def test_detect() -> None:
    assert ClaudeCodeImporter().detect(FIXTURE) is True
