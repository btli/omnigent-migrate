"""Map a source model string to an Omnigent harness (a fidelity surface)."""

from __future__ import annotations


def resolve_harness(model: str | None, source: str) -> tuple[str, str | None]:
    """Return (harness, note); note is None only when the mapping is unambiguous."""
    m = (model or "").lower()
    if not m:
        default = "codex" if source == "codex" else "claude-sdk"
        return default, f"no model specified; defaulted to {default}"
    if any(k in m for k in ("claude", "sonnet", "opus", "haiku")) or m.startswith("anthropic"):
        return "claude-sdk", None
    if m.startswith(("gpt", "o1", "o3", "o4")) or "codex" in m:
        return "codex", None
    if "gemini" in m or "antigravity" in m:
        return "antigravity", "antigravity harness is gated until feat/antigravity ships"
    return "pi", f"unrecognized model {model!r}; routed to pi (multi-model gateway) — verify"
