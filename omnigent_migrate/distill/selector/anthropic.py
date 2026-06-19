"""Embedded Claude selector. Forces a tool call whose input_schema is the Team
schema, validates the result, and falls back to RuleSelector on any failure."""

from __future__ import annotations

import json
from typing import Any

from omnigent_migrate.distill.archetypes import LIBRARY
from omnigent_migrate.distill.schema import Archetype, ProjectProfile, Team
from omnigent_migrate.distill.selector.base import RuleSelector

_RUBRIC = (
    "You design an Omnigent agent team for a project. Always include the orchestrator, "
    "two implementer workers (claude_code on claude-native, codex on codex-native), and a "
    "reviewer. Add a specialist sub-agent ONLY when its concern is a substantial/recurring "
    "slice of the work, benefits from isolated context or its own tools, or needs an "
    "independent perspective; otherwise route that concern to skills_instead. Personas are "
    "role descriptions that point at the repo's own docs/skills — never inline project docs."
)


def _make_client() -> Any:
    from anthropic import Anthropic

    return Anthropic()  # reads ANTHROPIC_API_KEY from env


class AnthropicSelector:
    def __init__(self, client: Any | None = None, model: str = "claude-opus-4-8") -> None:
        self._client = client
        self._model = model
        self._fallback = RuleSelector()

    def propose(self, profile: ProjectProfile, library: list[Archetype]) -> Team:
        try:
            client = self._client or _make_client()
            tool = {
                "name": "emit_team",
                "description": "Return the proposed Omnigent agent team.",
                "input_schema": Team.model_json_schema(),
            }
            lib = [a.model_dump(include={"id", "kind", "triggers"}) for a in library]
            resp = client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=_RUBRIC,
                tools=[tool],
                tool_choice={"type": "tool", "name": "emit_team"},
                messages=[{
                    "role": "user",
                    "content": (
                        "PROJECT PROFILE:\n" + profile.model_dump_json(indent=2)
                        + "\n\nARCHETYPE LIBRARY (ids/kinds/triggers):\n" + json.dumps(lib)
                        + "\n\nReturn the team via emit_team."
                    ),
                }],
            )
            for block in resp.content:
                if getattr(block, "type", None) == "tool_use":
                    return Team.model_validate(block.input)
            raise ValueError("no tool_use block in response")
        except Exception:
            return self._fallback.propose(profile, library or LIBRARY)
