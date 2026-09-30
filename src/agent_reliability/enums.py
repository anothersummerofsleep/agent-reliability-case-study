"""Frozen Phase -1 enums.

These are the exact route / decision / reason vocabularies from the frozen
specification. String values are the wire form used in the seed dataset.
"""

from __future__ import annotations

from enum import Enum


class Route(str, Enum):
    INVESTIGATE = "INVESTIGATE"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class Decision(str, Enum):
    ANSWER = "ANSWER"
    ASK = "ASK"
    ESCALATE = "ESCALATE"
    ABSTAIN = "ABSTAIN"


class EscalationReason(str, Enum):
    SAFETY = "safety"
    TOOL_FAILURE = "tool_failure"
    EVIDENCE_UNRESOLVABLE = "evidence_unresolvable"
    CONFLICT_UNRESOLVABLE = "conflict_unresolvable"
    LOW_CONFIDENCE = "low_confidence"
    GROUNDING_FAILURE = "grounding_failure"
    INTERNAL_ERROR = "internal_error"


class AbstainReason(str, Enum):
    OUT_OF_DOMAIN = "out_of_domain"
    UNSUPPORTED_INFERENCE = "unsupported_inference"
    NO_ACTIONABLE_ISSUE = "no_actionable_issue"


class Confidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SourceType(str, Enum):
    INCIDENT_PROVIDED = "incident_provided"
    TOOL_TELEMETRY = "tool_telemetry"
    RETRIEVED_MANUAL = "retrieved_manual"
    RETRIEVED_HISTORY = "retrieved_history"
