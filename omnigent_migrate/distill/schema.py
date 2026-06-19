"""Pydantic models for the distiller: the project profile, the archetype library,
and the proposed agent team (also the Anthropic tool-output schema)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ProjectProfile(BaseModel):
    name: str
    languages: list[str] = Field(default_factory=list)
    package_managers: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    db: list[str] = Field(default_factory=list)
    infra: list[str] = Field(default_factory=list)
    test: list[str] = Field(default_factory=list)
    data_ml: list[str] = Field(default_factory=list)
    mobile: list[str] = Field(default_factory=list)
    security: list[str] = Field(default_factory=list)
    ci: list[str] = Field(default_factory=list)
    docs: bool = False
    repo_shape: dict[str, Any] = Field(default_factory=dict)
    existing: dict[str, Any] = Field(default_factory=dict)


class Archetype(BaseModel):
    id: str
    kind: Literal["core", "specialist"]
    triggers: list[str] = Field(default_factory=list)
    persona_template: str
    default_skills: list[str] = Field(default_factory=list)
    harness: str = "claude-sdk"
    model: str | None = None
    guardrails_hint: str | None = None


class WorkerSpec(BaseModel):
    name: str
    harness: str
    model: str | None = None
    persona: str


class SpecialistSpec(BaseModel):
    archetype: str
    name: str
    persona: str
    skills: list[str] = Field(default_factory=list)
    harness: str = "claude-sdk"
    model: str | None = None
    rationale: str = ""


class SkillInstead(BaseModel):
    concern: str
    why: str


class Team(BaseModel):
    orchestrator: dict[str, str]
    workers: list[WorkerSpec]
    reviewer: WorkerSpec
    specialists: list[SpecialistSpec] = Field(default_factory=list)
    skills_instead: list[SkillInstead] = Field(default_factory=list)
