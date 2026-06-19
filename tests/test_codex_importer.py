from pathlib import Path

from omnigent_migrate.importers.codex import CodexImporter
from omnigent_migrate.ledger import Ledger, Status

FIXTURE = Path(__file__).parent / "fixtures" / "codex_project"
CONFIG = FIXTURE / "config.toml"


def test_detect() -> None:
    assert CodexImporter().detect(FIXTURE) is True


def test_imports_codex_setup() -> None:
    led = Ledger()
    bundle = CodexImporter().to_bundle(FIXTURE, led, config_path=CONFIG)
    cfg = bundle.config
    # AGENTS.md -> persona prompt (not inlined)
    prompt = cfg["prompt"]
    assert "coding agent working in the codex_project repository" in prompt
    assert "AGENTS.md" in prompt  # pointer
    assert "lead for the demo Codex app" not in prompt  # content not inlined
    mem = next(e for e in led.entries if e.primitive == "memory")
    assert mem.status is Status.TRANSLATED and "left in place" in mem.note
    # model -> executor.model (top-level) + harness via resolve_harness
    assert cfg["executor"]["model"] == "gpt-5.5"
    assert cfg["executor"]["config"]["harness"] == "codex"
    assert cfg["executor"]["context_window"] == 1000000
    # solo bundle — no orchestrator shape
    assert "spawn" not in cfg
    assert bundle.agents == {}
    # mcp_servers -> tools.<name>
    assert cfg["tools"]["github"]["type"] == "mcp"
    assert cfg["tools"]["github"]["command"] == "npx"
    # approval/sandbox carried DEGRADED in the sidecar (sandbox is the boundary)
    assert bundle.extensions["approvals"]["approval_policy"] == "on-request"
    assert bundle.extensions["approvals"]["sandbox_mode"] == "workspace-write"
    by_primitive = {e.primitive: e.status for e in led.entries}
    assert by_primitive["model"] is Status.TRANSLATED
    assert by_primitive["mcp_server"] is Status.TRANSLATED
    assert by_primitive["approvals"] is Status.DEGRADED
    # connectors noted (not carried verbatim — may hold secrets)
    assert by_primitive["connectors"] is Status.DEGRADED


def test_missing_config_is_lenient(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("Be a good agent.\n")
    led = Ledger()
    bundle = CodexImporter().to_bundle(tmp_path, led, config_path=tmp_path / "nope.toml")
    assert "coding agent working in the" in bundle.config["prompt"]
    assert bundle.config["executor"]["config"]["harness"] == "codex"  # default codex harness
