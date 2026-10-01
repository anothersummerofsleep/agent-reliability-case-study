"""Seed evaluation dataset: schema + loader for the 22 frozen cases.

Phase 0 only loads and validates the cases (and the coverage they must satisfy). It
does NOT score them against the agent - that is a later phase.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import AbstainReason, Decision, EscalationReason, Route

DEFAULT_DATASET = Path(__file__).resolve().parents[2] / "datasets" / "incidents.seed.jsonl"


class RetrievalBehavior(str, Enum):
    REQUIRED = "required"
    SKIP = "skip"
    ALLOWED = "allowed"
    NOT_APPLICABLE = "not_applicable"


class Tier(str, Enum):
    E2E = "E2E"
    UNIT = "UNIT"


class SeedCase(BaseModel):
    # Reject unknown fields so a prohibited tool-behavior field (deliberately out of
    # scope) cannot silently enter the dataset schema.
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    input: str
    expected_route: Route
    expected_decision: Decision
    expected_escalation_reason: Optional[EscalationReason] = None
    expected_abstain_reason: Optional[AbstainReason] = None
    expected_retrieval_behavior: RetrievalBehavior
    expected_retrieval_ids: list[str] = Field(default_factory=list)
    distractor_ids: list[str] = Field(default_factory=list)
    signals: dict = Field(default_factory=dict)
    tier: Tier
    tests: str

    @model_validator(mode="after")
    def _check_reason_and_retrieval(self) -> "SeedCase":
        if self.expected_decision is Decision.ESCALATE and self.expected_escalation_reason is None:
            raise ValueError(f"{self.id}: ESCALATE case needs expected_escalation_reason")
        if self.expected_decision is Decision.ABSTAIN and self.expected_abstain_reason is None:
            raise ValueError(f"{self.id}: ABSTAIN case needs expected_abstain_reason")
        if self.expected_retrieval_behavior is RetrievalBehavior.REQUIRED and not self.expected_retrieval_ids:
            raise ValueError(f"{self.id}: 'required' retrieval needs at least one expected_retrieval_id")
        if self.expected_route is Route.OUT_OF_SCOPE and self.expected_retrieval_behavior is not RetrievalBehavior.NOT_APPLICABLE:
            raise ValueError(f"{self.id}: OUT_OF_SCOPE must be retrieval not_applicable")
        return self


def load_seed_cases(path: Path | str | None = None) -> list[SeedCase]:
    p = Path(path) if path is not None else DEFAULT_DATASET
    cases: list[SeedCase] = []
    with p.open("r", encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                cases.append(SeedCase.model_validate(json.loads(raw)))
            except Exception as exc:  # pragma: no cover - surfaced by the loader test
                raise ValueError(f"{p}:{line_no}: {exc}") from exc
    return cases


def coverage(cases: list[SeedCase]) -> dict[str, set]:
    return {
        "routes": {c.expected_route for c in cases},
        "decisions": {c.expected_decision for c in cases},
        "escalation_reasons": {c.expected_escalation_reason for c in cases if c.expected_escalation_reason},
        "abstain_reasons": {c.expected_abstain_reason for c in cases if c.expected_abstain_reason},
        "retrieval_behaviors": {c.expected_retrieval_behavior for c in cases},
        "tiers": {c.tier for c in cases},
    }
