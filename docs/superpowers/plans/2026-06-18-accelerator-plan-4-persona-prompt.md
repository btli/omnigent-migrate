# Omnigent Migration Accelerator — Plan 4 (correct the prompt model: persona, not project memory)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`. **Hard scope rule: implement ONLY your dispatched task, commit, STOP.**

**Goal:** Fix a core conceptual error in both importers. `prompt` must be the **agent's persona/role** (like Polly and Debby — "You are X, you do Y, your sub-agents are Z"), NOT a dump of the project's `CLAUDE.md`/`AGENTS.md`. Those files are **project context** that the harness auto-loads from the repo at cwd=project (exactly like skills) — they stay in the repo and are recorded translated-in-place. The persona instead *points* the agent at them.

**Why:** Polly's and Debby's `prompt` fields are pure personas; no Omnigent example inlines a project's CLAUDE.md (verified — `rg CLAUDE.md examples/` is empty). The bundle defines the *agent*; the repo provides the *context*. Inlining CLAUDE.md both misuses `prompt` and duplicates context the harness already reads.

**Decision (locked with the user):** persona **+ a CLAUDE.md/AGENTS.md pointer** — the persona names the repo and tells the agent to follow the repo's CLAUDE.md/AGENTS.md and `.claude/skills/` (a one-line pointer, not the content).

**Architecture:** A shared `build_persona()` in `_util.py`; both importers (1) record memory files translated-in-place instead of inlining, and (2) set `prompt = build_persona(...)`. Sub-agent prompts (`.claude/agents/*.md` body) are unchanged — the body *is* that sub-agent's persona.

**Tech Stack:** unchanged (uv, ruff, mypy --strict, pytest). Build on `feat/mvp`.

## Global Constraints

- `uv` only; no `# noqa`/`# type: ignore`; strict TDD; `mypy --strict` clean.
- `prompt` is a PERSONA. CLAUDE.md/AGENTS.md are NEVER inlined into `config.yaml` — they are recorded `TRANSLATED` with the note "left in place; the harness auto-loads it at cwd=project" (parallel to skills).
- Sub-agent body → sub-agent `prompt` stays as-is.

**Verified facts:** Polly (`examples/polly/config.yaml`) and Debby (`examples/debby/config.yaml`) both use persona prompts; neither references any project doc. `os_env.cwd: "."` means the harness runs at the project root, where Claude (claude-sdk/native) auto-loads `CLAUDE.md` and Codex auto-loads `AGENTS.md`.

---

### Task 1: `build_persona` in `_util.py`

**Files:** Modify `omnigent_migrate/importers/_util.py`; Test `tests/test_util_persona.py`.

**Interfaces:**
- Produces: `build_persona(project_name: str, memory_files: list[str], skills_present: bool, agents: list[tuple[str, str]]) -> str` — `agents` is `(name, description)` pairs; non-empty ⇒ orchestrator persona, empty ⇒ solo coding-agent persona. Always ends with a trailing newline.

- [ ] **Step 1: Failing test** (`tests/test_util_persona.py`):
```python
from omnigent_migrate.importers._util import build_persona


def test_solo_persona_points_at_repo_context() -> None:
    p = build_persona("askcv.ai", ["CLAUDE.md"], skills_present=True, agents=[])
    assert "coding agent working in the askcv.ai repository" in p
    assert "Follow the guidance in the repo's CLAUDE.md" in p
    assert "skills under .claude/skills/" in p
    assert "orchestrator" not in p


def test_orchestrator_persona_lists_subagents() -> None:
    p = build_persona("remote-dev", ["CLAUDE.md", "AGENTS.md"], skills_present=False,
                      agents=[("reviewer", "Reviews diffs"), ("ui", "Designs UI")])
    assert "orchestrator for the remote-dev repository" in p
    assert "- reviewer: Reviews diffs" in p
    assert "- ui: Designs UI" in p
    assert "delegate" in p.lower()
    assert "CLAUDE.md / AGENTS.md" in p


def test_persona_with_no_context_is_clean() -> None:
    p = build_persona("x", [], skills_present=False, agents=[])
    assert p.strip() == "You are a coding agent working in the x repository."
```
- [ ] **Step 2:** `uv run pytest tests/test_util_persona.py -q` → FAIL.
- [ ] **Step 3: Implement** — append to `omnigent_migrate/importers/_util.py`:
```python
def build_persona(
    project_name: str,
    memory_files: list[str],
    skills_present: bool,
    agents: list[tuple[str, str]],
) -> str:
    """The agent's persona (its role) — NOT the project's docs. Points the agent at
    the repo's CLAUDE.md/AGENTS.md/skills, which the harness auto-loads at cwd=project."""
    refs: list[str] = []
    if memory_files:
        refs.append("the guidance in the repo's " + " / ".join(memory_files))
    if skills_present:
        refs.append("the skills under .claude/skills/")
    follow = (" Follow " + " and ".join(refs) + ".") if refs else ""
    if agents:
        roster = "\n".join(f"  - {name}: {desc}" for name, desc in agents)
        return (
            f"You are the orchestrator for the {project_name} repository. You coordinate "
            "specialized sub-agents and delegate work to them rather than doing it yourself. "
            f"Your sub-agents:\n{roster}\n"
            "Decompose each request, route each part to the most appropriate sub-agent, and "
            f"integrate their results.{follow}\n"
        )
    return f"You are a coding agent working in the {project_name} repository.{follow}\n"
```
- [ ] **Step 4:** `uv run pytest tests/test_util_persona.py -q` → PASS. `uv run pytest -q && uv run ruff check && uv run mypy omnigent_migrate` → clean.
- [ ] **Step 5:** `git add -A && git commit -m "feat: build_persona — agent role prompt that points at repo context"`. **STOP.**

---

### Task 2: Claude importer → persona prompt + repo-side memory

**Files:** Modify `omnigent_migrate/importers/claude_code.py`; Modify `tests/test_claude_importer.py`.

**Interfaces:** Consumes `build_persona` (Task 1).

- [ ] **Step 1: Update the test first.** In `tests/test_claude_importer.py` `test_imports_core_primitives`, REPLACE the line `assert "lead for the demo app" in bundle.config["prompt"]` with:
```python
    prompt = bundle.config["prompt"]
    # prompt is a PERSONA, not the CLAUDE.md content (fixture has a sub-agent -> orchestrator)
    assert "orchestrator for the claude_project repository" in prompt
    assert "- reviewer: Reviews diffs" in prompt
    assert "CLAUDE.md" in prompt  # pointer, not content
    assert "lead for the demo app" not in prompt  # CLAUDE.md content must NOT be inlined
    # memory recorded translated-in-place (left in repo, harness auto-loads it)
    mem = next(e for e in led.entries if e.primitive == "memory")
    assert mem.status is Status.TRANSLATED and "left in place" in mem.note
```
- [ ] **Step 2:** `uv run pytest tests/test_claude_importer.py -q` → FAIL (prompt is still the CLAUDE.md dump).
- [ ] **Step 3: Implement** in `omnigent_migrate/importers/claude_code.py`:
  1. Add `build_persona` to the `_util` import.
  2. REPLACE the memory block at the top of `to_bundle`:
```python
        prompt = ""
        for mem in ("CLAUDE.md", "AGENTS.md"):
            p = project / mem
            if p.is_file():
                prompt += p.read_text() + "\n"
                ledger.record("memory", mem, Status.TRANSLATED)
        if not prompt:
            prompt = "You are a coding agent for this repository. Follow its conventions.\n"
            ledger.record("memory", "(none)", Status.DEGRADED, "no CLAUDE.md/AGENTS.md; used a default")
```
     with (record the files, do NOT inline; the prompt is built later from the persona):
```python
        memory_files = [m for m in ("CLAUDE.md", "AGENTS.md") if (project / m).is_file()]
        for m in memory_files:
            ledger.record(
                "memory", m, Status.TRANSLATED,
                "left in place; the harness auto-loads it at cwd=project",
            )
```
  3. The skills block already computes whether skills exist; capture it as a bool. Where it does `if skills_dir.is_dir(): n = sum(...); if n: ledger.record("skills", ...)`, set `skills_present = bool(n)` (initialize `skills_present = False` before the block).
  4. Build the prompt from the persona AFTER the `agents` dict and `skills_present` are known, and use it in `config`. Replace `"prompt": prompt,` in the `config` dict with `"prompt": build_persona(project.name, memory_files, skills_present, [(a, agents[a]["description"]) for a in sorted(agents)]),` — or assign `prompt = build_persona(...)` just before building `config` and keep `"prompt": prompt`. (The sub-agent descriptions come from `agents[a]["description"]`.)
- [ ] **Step 4:** `uv run pytest -q` → PASS (the orchestrator persona test + all others). `uv run ruff check && uv run mypy omnigent_migrate` → clean.
- [ ] **Step 5:** `git add -A && git commit -m "fix: Claude importer emits a persona prompt; CLAUDE.md/AGENTS.md stay repo-side"`. **STOP.**

---

### Task 3: Codex importer → persona prompt + repo-side memory

**Files:** Modify `omnigent_migrate/importers/codex.py`; Modify `tests/test_codex_importer.py`.

**Interfaces:** Consumes `build_persona` (Task 1). Codex is solo ⇒ `agents=[]`.

- [ ] **Step 1: Update the test first.** In `tests/test_codex_importer.py` `test_imports_codex_setup`, REPLACE `assert "lead for the demo Codex app" in cfg["prompt"]` with:
```python
    prompt = cfg["prompt"]
    assert "coding agent working in the codex_project repository" in prompt
    assert "AGENTS.md" in prompt  # pointer
    assert "lead for the demo Codex app" not in prompt  # content not inlined
    mem = next(e for e in led.entries if e.primitive == "memory")
    assert mem.status is Status.TRANSLATED and "left in place" in mem.note
```
Also update `test_missing_config_is_lenient`: replace `assert "good agent" in bundle.config["prompt"]` with `assert "coding agent working in the" in bundle.config["prompt"]`.
- [ ] **Step 2:** `uv run pytest tests/test_codex_importer.py -q` → FAIL.
- [ ] **Step 3: Implement** in `omnigent_migrate/importers/codex.py`:
  1. Add `build_persona` to the `_util` import.
  2. REPLACE the memory block:
```python
        prompt = ""
        for mem in ("AGENTS.md", "CLAUDE.md"):
            p = project / mem
            if not p.is_file():
                continue
            try:
                text = p.read_text()
            except (OSError, UnicodeDecodeError):
                ledger.record("memory", mem, Status.UNSUPPORTED, "unreadable")
                continue
            prompt += text + "\n"
            ledger.record("memory", mem, Status.TRANSLATED)
        if not prompt:
            prompt = "You are a coding agent for this repository. Follow its conventions.\n"
            ledger.record("memory", "(none)", Status.DEGRADED, "no AGENTS.md/CLAUDE.md; used a default")
```
     with (record presence translated-in-place; no inlining; reads are just `.is_file()` checks so no read errors to guard):
```python
        memory_files = [m for m in ("AGENTS.md", "CLAUDE.md") if (project / m).is_file()]
        for m in memory_files:
            ledger.record(
                "memory", m, Status.TRANSLATED,
                "left in place; the harness auto-loads it at cwd=project",
            )
```
  3. Where `config` is built, set `"prompt": build_persona(project.name, memory_files, False, []),` (solo, no skills scan in the codex importer). (Remove the now-unused local `prompt` variable.)
- [ ] **Step 4:** `uv run pytest -q` → PASS. `uv run ruff check && uv run mypy omnigent_migrate` → clean.
- [ ] **Step 5: Re-smoke** to see the corrected prompts on real projects:
```bash
cd /Users/bryanli/Projects/btli/omnigent-migrate
uv run omnigent-migrate from-claude /Users/bryanli/Projects/btli/remote-dev -o /tmp/rd-claude && sed -n '/^prompt:/,/^[a-z]/p' /tmp/rd-claude/config.yaml | head -15
uv run omnigent-migrate from-codex /Users/bryanli/Projects/btli/remote-dev -o /tmp/rd-codex && sed -n '/^prompt:/,/^[a-z]/p' /tmp/rd-codex/config.yaml | head -8
```
Expected: short persona prompts (orchestrator for the claude path with the 7 sub-agents listed + a CLAUDE.md/AGENTS.md pointer; a solo coding-agent persona for codex), NOT the CLAUDE.md dump. Both bundles still validate. Record the persona in the commit message.
- [ ] **Step 6:** `git add -A && git commit -m "fix: Codex importer emits a persona prompt; AGENTS.md stays repo-side"`. **STOP.**

---

## Self-Review

**Coverage:** persona helper (Task 1) ✓ · Claude importer persona + repo-side memory (Task 2) ✓ · Codex importer persona + repo-side memory (Task 3) ✓ · sub-agent body→prompt unchanged ✓ · memory recorded translated-in-place, never inlined ✓.

**Placeholder scan:** none — full code + expected output.

**Type consistency:** `build_persona(project_name, memory_files, skills_present, agents)->str` used identically by both importers; `agents` is `(name, description)` pairs (claude passes the sorted roster, codex passes `[]`).
