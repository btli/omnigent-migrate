from pathlib import Path

from omnigent_migrate.importers.claude_code import ClaudeCodeImporter
from omnigent_migrate.ledger import Ledger, Status

FIXTURE = Path(__file__).parent / "fixtures" / "claude_project"


def test_imports_core_primitives() -> None:
    led = Ledger()
    bundle = ClaudeCodeImporter().to_bundle(FIXTURE, led)
    prompt = bundle.config["prompt"]
    # prompt is a PERSONA, not the CLAUDE.md content (fixture has a sub-agent -> orchestrator)
    assert "orchestrator for the claude_project repository" in prompt
    assert "- reviewer: Reviews diffs" in prompt
    assert "CLAUDE.md" in prompt  # pointer, not content
    assert "lead for the demo app" not in prompt  # CLAUDE.md content must NOT be inlined
    # memory recorded translated-in-place (left in repo, harness auto-loads it)
    mem = next(e for e in led.entries if e.primitive == "memory")
    assert mem.status is Status.TRANSLATED and "left in place" in mem.note
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
    # Plan 2: deferred primitives now examined + carried in extensions
    assert bundle.extensions["permissions"]["deny"] == ["Bash(rm:*)"]
    assert "hooks" in bundle.extensions
    assert bundle.extensions["commands"][0]["name"] == "deploy"
    assert bundle.extensions["plugins"]["enabledPlugins"] == {"superpowers@official": True}
    assert "guardrails" not in bundle.config  # sandbox is the boundary; no auto-guardrail
    by_primitive = {e.primitive: e.status for e in led.entries}
    assert by_primitive["permissions"] is Status.DEGRADED
    assert by_primitive["hooks"] is Status.UNSUPPORTED
    assert by_primitive["slash_commands"] is Status.DEGRADED
    assert by_primitive["plugins"] is Status.DEGRADED


def test_detect() -> None:
    assert ClaudeCodeImporter().detect(FIXTURE) is True


# C1: malformed YAML in a sub-agent .md must not abort the whole import
def test_malformed_subagent_frontmatter_does_not_abort(tmp_path: Path) -> None:
    """A tab-broken frontmatter in a sub-agent file must yield a bundle, not raise."""
    (tmp_path / ".claude").mkdir()
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir()
    # Tab inside YAML block triggers ruamel ScannerError
    (agents_dir / "broken.md").write_text("---\n\tname: broken-agent\n---\nDo the thing.\n")
    led = Ledger()
    bundle = ClaudeCodeImporter().to_bundle(tmp_path, led)
    # The sub-agent must still be present in the bundle using the filename stem as name
    assert "broken" in bundle.agents


# C1: non-dict (scalar) frontmatter in a sub-agent file must not abort the whole import
def test_scalar_subagent_frontmatter_does_not_abort(tmp_path: Path) -> None:
    """A scalar YAML frontmatter in a sub-agent file must yield a bundle, not raise."""
    (tmp_path / ".claude").mkdir()
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir()
    (agents_dir / "scalar.md").write_text("---\njust a string\n---\nDo stuff.\n")
    led = Ledger()
    bundle = ClaudeCodeImporter().to_bundle(tmp_path, led)
    assert "scalar" in bundle.agents
