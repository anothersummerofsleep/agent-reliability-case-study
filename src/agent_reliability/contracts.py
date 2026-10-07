"""Frozen Phase -1 state + output contract.

Two distinct things, kept separate on purpose:

* ``GraphState`` is the *progressive* graph state. Later-stage fields are optional
  and stay ``None`` until their owning node runs. Nothing downstream is globally
  required, so a partially-populated state is always valid to *hold*.

* ``validate_final_output`` enforces the *output* contract: the decision-specific
  invariants that must hold once the gate has produced a terminal decision. These
  are checked at the end, not baked into ``GraphState`` as global requirements.
"""

from __future__ import annotations

from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from .enums import (
    AbstainReason,
    Confidence,
    Decision,
    EscalationReason,
    Route,
    SourceType,
)


class Evidence(BaseModel):
    """A provenance-bearing evidence item. Provenance is what makes an ANSWER
    groundable; it may be requester-supplied (``incident_provided``) rather than
    retrieved. ``source_id`` and ``content`` must be non-empty so an empty item
    cannot masquerade as grounding."""

    source_id: str = Field(min_length=1)
    source_type: SourceType
    content: str = Field(min_length=1)


class GraphState(BaseModel):
    """Progressive graph state. Owner/stage noted per field group."""

    # --- intake (always present) ---
    incident_id: str
    incident_raw: str
    safety_critical: bool
    trace_id: str = Field(default_factory=lambda: uuid4().hex)

    # --- router ---
    route: Optional[Route] = None
    # abstain_reason is produced by the router; non-null iff route == OUT_OF_SCOPE.
    abstain_reason: Optional[AbstainReason] = None

    # --- Evidence Investigator (present iff it ran) ---
    evidence: Optional[list[Evidence]] = None
    evidence_sufficient: Optional[bool] = None
    evidence_conflict: Optional[bool] = None
    gap_user_resolvable: Optional[bool] = None
    tool_failed: Optional[bool] = None
    # Observed triage choices, recorded for experiment auditability only. These mirror
    # what the triage step decided (which evidence source it asked for); nothing
    # downstream (policy, graph, output contract) reads them.
    triage_needs_retrieval: Optional[bool] = None
    triage_needs_live_telemetry: Optional[bool] = None

    # --- Diagnosis Specialist (present iff it ran) ---
    confidence: Optional[Confidence] = None
    proposed_answer: Optional[str] = None
    hypotheses: list[str] = Field(default_factory=list)

    # --- Grounding Validator (present iff it ran; runs only with a proposed answer) ---
    answer_grounded: Optional[bool] = None

    # --- deterministic gate ---
    decision: Optional[Decision] = None
    clarifying_question: Optional[str] = None
    escalation_reason: Optional[EscalationReason] = None


class OutputContractError(ValueError):
    """Raised when a terminal state violates the decision-specific output contract."""


def validate_final_output(state: GraphState) -> None:
    """Enforce the per-decision output invariants on a terminal state.

    Raises ``OutputContractError`` on violation. This is the *output* contract,
    deliberately separate from the permissive progressive ``GraphState`` schema.
    """
    # Always required once we have terminated.
    if state.decision is None:
        raise OutputContractError("terminal state has no decision")
    if state.route is None:
        raise OutputContractError("terminal state has no route")
    if not state.trace_id:
        raise OutputContractError("terminal state has no trace_id")

    # Route / abstain_reason relationship (frozen contract: non-null iff OUT_OF_SCOPE).
    if state.route is Route.OUT_OF_SCOPE:
        if state.abstain_reason is None:
            raise OutputContractError("OUT_OF_SCOPE requires an abstain_reason")
    elif state.abstain_reason is not None:
        raise OutputContractError("abstain_reason set on a non-OUT_OF_SCOPE route")

    if state.decision is Decision.ANSWER:
        if state.confidence is not Confidence.HIGH:
            raise OutputContractError("ANSWER requires confidence == high")
        if state.proposed_answer is None:
            raise OutputContractError("ANSWER requires a proposed_answer")
        if state.evidence is None or len(state.evidence) == 0:
            raise OutputContractError("ANSWER requires provenance-bearing evidence")
        if state.answer_grounded is not True:
            raise OutputContractError("ANSWER requires answer_grounded is True")

    elif state.decision is Decision.ASK:
        if state.clarifying_question is None:
            raise OutputContractError("ASK requires a clarifying_question")
        if state.gap_user_resolvable is not True:
            raise OutputContractError("ASK requires gap_user_resolvable is True")

    elif state.decision is Decision.ESCALATE:
        if state.escalation_reason is None:
            raise OutputContractError("ESCALATE requires an escalation_reason")

    elif state.decision is Decision.ABSTAIN:
        if state.route is not Route.OUT_OF_SCOPE:
            raise OutputContractError("ABSTAIN requires route == OUT_OF_SCOPE")
        if state.abstain_reason is None:
            raise OutputContractError("ABSTAIN requires an abstain_reason")
