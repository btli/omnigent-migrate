"""Fidelity ledger: record per-primitive translation decisions + render the report."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    TRANSLATED = "translated"
    DEGRADED = "degraded"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class LedgerEntry:
    primitive: str
    source_ref: str
    status: Status
    note: str = ""
    manual_step: str = ""


@dataclass
class Ledger:
    entries: list[LedgerEntry] = field(default_factory=list)

    def record(
        self,
        primitive: str,
        source_ref: str,
        status: Status,
        note: str = "",
        manual_step: str = "",
    ) -> None:
        self.entries.append(LedgerEntry(primitive, source_ref, status, note, manual_step))

    def summary(self) -> dict[Status, int]:
        out = {s: 0 for s in Status}
        for e in self.entries:
            out[e.status] += 1
        return out

    def render_markdown(self) -> str:
        s = self.summary()
        lines = [
            "# Migration Report",
            "",
            f"**{s[Status.TRANSLATED]} translated · {s[Status.DEGRADED]} degraded · "
            f"{s[Status.UNSUPPORTED]} unsupported**",
            "",
        ]
        for status in Status:
            rows = [e for e in self.entries if e.status is status]
            if not rows:
                continue
            lines.append(f"## {status.value.title()}")
            for e in rows:
                line = f"- **{e.primitive}** ({e.source_ref})"
                if e.note:
                    line += f" — {e.note}"
                lines.append(line)
                if e.manual_step:
                    lines.append(f"  - Manual: {e.manual_step}")
            lines.append("")
        return "\n".join(lines)
