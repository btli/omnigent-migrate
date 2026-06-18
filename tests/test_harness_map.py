from omnigent_migrate.harness_map import resolve_harness


def test_resolve_harness() -> None:
    assert resolve_harness("claude-opus-4-8", "claude_code") == ("claude-sdk", None)
    assert resolve_harness("sonnet", "claude_code") == ("claude-sdk", None)
    assert resolve_harness("gpt-5.5", "codex") == ("codex", None)
    h, note = resolve_harness("gemini-3-pro", "claude_code")
    assert h == "antigravity" and note and "gated" in note
    h, note = resolve_harness(None, "codex")
    assert h == "codex" and note
    h, note = resolve_harness("llama-3", "claude_code")
    assert h == "pi" and note
