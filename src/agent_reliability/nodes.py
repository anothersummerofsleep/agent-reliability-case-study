"""Phase 0 graph nodes - plumbing only.

Real Investigator / retrieval / Diagnosis / Grounding semantics come later. These are
the minimum stubs needed to prove flow, with the model-dependent parts injected so the
graph is testable offline. The one exception is ``diagnosis``, which drives a real (or
fake) chat model to prove one traceable LLM call.
"""

from __future__ import annotations

from typing import Callable, Optional

from pydantic import BaseModel, Field

from .contracts import Evidence, GraphState
from .enums import AbstainReason, Confidence, Route, SourceType
from .safety import detect_safety_critical

# Injected function signatures.
DiagnoseFn = Callable[[GraphState], "DiagnosisOutput"]
GroundFn = Callable[[GraphState], Optional[bool]]
RouterFn = Callable[[GraphState], tuple[Route, Optional[AbstainReason]]]
EvidenceFn = Callable[[GraphState], dict]


class DiagnosisOutput(BaseModel):
    confidence: Confidence
    proposed_answer: Optional[str] = None
    hypotheses: list[str] = Field(default_factory=list)


def make_initial_state(incident_id: str, incident_raw: str) -> GraphState:
    """Build a fully-valid initial state (intake computes safety deterministically)."""
    return GraphState(
        incident_id=incident_id,
        incident_raw=incident_raw,
        safety_critical=detect_safety_critical(incident_raw),
    )


# --- intake ---------------------------------------------------------------
def intake(state: GraphState) -> dict:
    # Idempotent: safety is deterministic and owned by intake; recomputing keeps the
    # node visible in the trace without manufacturing values.
    return {"safety_critical": detect_safety_critical(state.incident_raw)}


# --- router (Phase 0 stub) ------------------------------------------------
_PURCHASE_CUES = ("should we buy", "which brand", "what model should", "recommend", "which chiller")
_ADMIN_CUES = ("warranty claim", "file the warranty", "email procurement", "purchase order")
_EQUIPMENT_CUES = ("rtu", "ahu", "chiller", "ch-", "nw-a", "compressor", "condenser", "chws", "chwr", "psi", "alarm")


def default_router(state: GraphState) -> tuple[Route, Optional[AbstainReason]]:
    """Deterministic Phase 0 router stub. The real classifier comes later."""
    t = state.incident_raw.lower()
    if any(c in t for c in _PURCHASE_CUES):
        return Route.OUT_OF_SCOPE, AbstainReason.UNSUPPORTED_INFERENCE
    if any(c in t for c in _ADMIN_CUES):
        return Route.OUT_OF_SCOPE, AbstainReason.NO_ACTIONABLE_ISSUE
    if not any(c in t for c in _EQUIPMENT_CUES):
        return Route.OUT_OF_SCOPE, AbstainReason.OUT_OF_DOMAIN
    return Route.INVESTIGATE, None


def make_router_node(router_fn: RouterFn) -> Callable[[GraphState], dict]:
    def _node(state: GraphState) -> dict:
        route, abstain_reason = router_fn(state)
        return {"route": route, "abstain_reason": abstain_reason}

    return _node


# --- evidence investigator (Phase 0 passthrough stub) ---------------------
def default_evidence(state: GraphState) -> dict:
    """Passthrough stub: normalize the incident into one incident_provided item and
    report sufficiency. No retrieval - the real Investigator arrives later."""
    item = Evidence(
        source_id=f"incident:{state.incident_id}",
        source_type=SourceType.INCIDENT_PROVIDED,
        content=state.incident_raw,
    )
    return {
        "evidence": [item],
        "evidence_sufficient": True,
        "evidence_conflict": False,
        "tool_failed": False,
        "gap_user_resolvable": None,
    }


def make_evidence_node(evidence_fn: EvidenceFn) -> Callable[[GraphState], dict]:
    def _node(state: GraphState) -> dict:
        return evidence_fn(state)

    return _node


# --- diagnosis (thin real/fake model call) --------------------------------
_DIAGNOSIS_SYSTEM = (
    "You are a diagnosis specialist for Northwind HVAC equipment. Given the incident and "
    "the gathered evidence, return your diagnostic confidence ('low', 'medium', or 'high'), a "
    "concise proposed_answer (the recommended next action) or null if you cannot answer, and a "
    "short list of hypotheses. Base it only on the provided evidence."
)


def make_llm_diagnose(model) -> DiagnoseFn:
    structured = model.with_structured_output(DiagnosisOutput)

    def _diagnose(state: GraphState) -> DiagnosisOutput:
        evidence_text = "\n".join(e.content for e in (state.evidence or []))
        messages = [
            ("system", _DIAGNOSIS_SYSTEM),
            ("human", f"Incident: {state.incident_raw}\n\nEvidence:\n{evidence_text}"),
        ]
        return structured.invoke(messages)

    return _diagnose


def make_diagnosis_node(diagnose_fn: DiagnoseFn) -> Callable[[GraphState], dict]:
    def _node(state: GraphState) -> dict:
        out = diagnose_fn(state)
        return {
            "confidence": out.confidence,
            "proposed_answer": out.proposed_answer,
            "hypotheses": out.hypotheses,
        }

    return _node


# --- grounding validator (Phase 0 stub) -----------------------------------
def default_ground(state: GraphState) -> Optional[bool]:
    """Phase 0 stub: runs only when there is a proposed answer; thinly treats any
    proposed answer as grounded. Real support-checking semantics come later."""
    if state.proposed_answer is None:
        return None
    return True


def make_grounding_node(ground_fn: GroundFn) -> Callable[[GraphState], dict]:
    def _node(state: GraphState) -> dict:
        # The validator runs only when a proposed answer exists.
        if state.proposed_answer is None:
            return {"answer_grounded": None}
        return {"answer_grounded": ground_fn(state)}

    return _node
