from typing import Any

from omnigent_migrate.distill.archetypes import LIBRARY
from omnigent_migrate.distill.schema import ProjectProfile
from omnigent_migrate.distill.selector.anthropic import AnthropicSelector


class _ToolUse:
    type = "tool_use"

    def __init__(self, data: dict[str, Any]) -> None:
        self.input = data


class _Resp:
    def __init__(self, data: dict[str, Any]) -> None:
        self.content = [_ToolUse(data)]


class _StubClient:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data
        self.messages = self

    def create(self, **_: Any) -> _Resp:
        return _Resp(self._data)


def _canned() -> dict[str, Any]:
    return {
        "orchestrator": {"persona": "You are the orchestrator for demo."},
        "workers": [{"name": "claude_code", "harness": "claude-native", "persona": "impl"}],
        "reviewer": {"name": "reviewer", "harness": "pi", "persona": "review"},
        "specialists": [{"archetype": "backend", "name": "backend", "persona": "be",
                         "skills": [], "harness": "claude-native", "rationale": "fastapi"}],
        "skills_instead": [],
    }


def test_anthropic_selector_parses_tool_output() -> None:
    sel = AnthropicSelector(client=_StubClient(_canned()))
    team = sel.propose(ProjectProfile(name="demo", frameworks=["fastapi"]), LIBRARY)
    assert team.specialists[0].archetype == "backend"


def test_anthropic_selector_falls_back_on_error() -> None:
    class _Boom:
        messages = property(lambda self: (_ for _ in ()).throw(RuntimeError("no")))
    sel = AnthropicSelector(client=_Boom())
    team = sel.propose(ProjectProfile(name="demo", db=["drizzle"]), LIBRARY)  # RuleSelector path
    assert {s.archetype for s in team.specialists} == {"db-migrations"}
