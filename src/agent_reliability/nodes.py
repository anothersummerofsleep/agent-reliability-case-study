"""Graph nodes - Phase 1 real implementations.

The Phase 0 behavioral stubs are replaced with the smallest real implementations of
the four components: a bounded Evidence Investigator (triage -> optional bounded
retrieval -> assessment), a structured Diagnosis Specialist, and a bounded Grounding
Validator. The router stays the deterministic Phase 0 heuristic (router replacement is
not in Phase 1 scope); its errors are recorded honestly in the baseline.

All model-backed steps are injected as plain callables so the whole graph runs offline
against fakes. Fail-closed behavior is deliberate: a Diagnosis parse failure leaves
``confidence`` unset and a Grounding Validator failure leaves ``answer_grounded`` None,
both of which the terminal policy checkpoint turns into ESCALATE(internal_error).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from pydantic import BaseModel, Field

from .contracts import Evidence, GraphState
from .enums import AbstainReason, Confidence, Route, SourceType
from .retrieval import DEFAULT_K, BM25Retriever, default_retriever
from .safety import detect_safety_critical

# Injected function signatures.
DiagnoseFn = Callable[[GraphState], "DiagnosisOutput"]
GroundFn = Callable[[GraphState], Optional[bool]]
RouterFn = Callable[[GraphState], tuple[Route, Optional[AbstainReason]]]
EvidenceFn = Callable[[GraphState], dict]

# Bounded-loop limits (frozen for the baseline; do not tune before baseline capture).
MAX_RETRIEVAL_ATTEMPTS = 2
MAX_TOOL_RETRIES = 2


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


# --- router (deterministic heuristic; replacement is out of Phase 1 scope) -
_PURCHASE_CUES = ("should we buy", "which brand", "what model should", "recommend", "which chiller")
_ADMIN_CUES = ("warranty claim", "file the warranty", "email procurement", "purchase order")
_EQUIPMENT_CUES = ("rtu", "ahu", "chiller", "ch-", "nw-a", "compressor", "condenser", "chws", "chwr", "psi", "alarm")


def default_router(state: GraphState) -> tuple[Route, Optional[AbstainReason]]:
    """Deterministic router heuristic (Phase 0/1). The real classifier is a later phase."""
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


# --- Evidence Investigator (Phase 1, bounded) -----------------------------
class TriagePlan(BaseModel):
    """First-pass plan from the already-supplied evidence (no retrieval yet)."""

    supplied_sufficient: bool
    needs_retrieval: bool
    retrieval_query: str = ""
    needs_live_telemetry: bool = False
    evidence_conflict: bool = False
    gap_user_resolvable: Optional[bool] = None


class EvidenceAssessment(BaseModel):
    """Assessment after a retrieval attempt, with the gathered evidence in hand."""

    evidence_sufficient: bool
    evidence_conflict: bool = False
    gap_user_resolvable: Optional[bool] = None
    needs_more_retrieval: bool = False
    more_query: str = ""


TriageFn = Callable[[GraphState], TriagePlan]
AssessFn = Callable[[GraphState, list[Evidence]], EvidenceAssessment]
TelemetryFn = Callable[[GraphState], None]  # raises on failure


class ToolUnavailableError(RuntimeError):
    """Raised when a live tool (e.g. telemetry) is requested but has no backend."""


def default_telemetry(state: GraphState) -> None:
    # There is no live telemetry backend in this project. A request to pull telemetry
    # therefore fails cleanly - this is the true system state, not engineered-to-fail
    # infrastructure. The policy turns bounded tool failure into ESCALATE(tool_failure).
    raise ToolUnavailableError("no telemetry backend configured")


def _incident_evidence(state: GraphState) -> Evidence:
    return Evidence(
        source_id=f"incident:{state.incident_id}",
        source_type=SourceType.INCIDENT_PROVIDED,
        content=state.incident_raw,
    )


@dataclass
class Investigator:
    """Bounded Evidence Investigator. Deterministic control flow around injected
    model steps; at most ``MAX_RETRIEVAL_ATTEMPTS`` retrievals, never a ReAct loop."""

    triage: TriageFn
    assess: AssessFn
    retriever: BM25Retriever
    telemetry: TelemetryFn = default_telemetry
    k: int = DEFAULT_K

    def __call__(self, state: GraphState) -> dict:
        evidence: list[Evidence] = [_incident_evidence(state)]
        plan = self.triage(state)

        # Live-telemetry branch: attempt the (unbacked) tool with bounded retries.
        if plan.needs_live_telemetry:
            if self._telemetry_fails(state):
                return {
                    "evidence": evidence,
                    "evidence_sufficient": False,
                    "evidence_conflict": False,
                    "gap_user_resolvable": plan.gap_user_resolvable,
                    "tool_failed": True,
                }

        # Skip-retrieval branch: triage doubles as the assessment.
        if not plan.needs_retrieval:
            return {
                "evidence": evidence,
                "evidence_sufficient": plan.supplied_sufficient,
                "evidence_conflict": plan.evidence_conflict,
                "gap_user_resolvable": plan.gap_user_resolvable,
                "tool_failed": False,
            }

        # Bounded retrieval branch.
        query = plan.retrieval_query or state.incident_raw
        retrieved: list[str] = []
        assessment: Optional[EvidenceAssessment] = None
        for _ in range(MAX_RETRIEVAL_ATTEMPTS):
            try:
                hits = self.retriever.search(query, k=self.k)
            except Exception:
                # Retrieval (a tool) failed: expose it cleanly as tool failure rather
                # than crash, so the policy produces ESCALATE(tool_failure).
                return {
                    "evidence": evidence,
                    "evidence_sufficient": False,
                    "evidence_conflict": False,
                    "gap_user_resolvable": plan.gap_user_resolvable,
                    "tool_failed": True,
                }
            for hit in hits:
                if hit.doc_id in retrieved:
                    continue
                retrieved.append(hit.doc_id)
                doc = self.retriever.doc(hit.doc_id)
                evidence.append(
                    Evidence(
                        source_id=hit.doc_id,
                        source_type=SourceType.RETRIEVED_MANUAL,
                        content=doc.text,
                    )
                )
            assessment = self.assess(state, evidence)
            if assessment.evidence_sufficient or not assessment.needs_more_retrieval:
                break
            query = assessment.more_query or query

        assert assessment is not None  # MAX_RETRIEVAL_ATTEMPTS >= 1
        return {
            "evidence": evidence,
            "evidence_sufficient": assessment.evidence_sufficient,
            "evidence_conflict": assessment.evidence_conflict,
            "gap_user_resolvable": assessment.gap_user_resolvable,
            "tool_failed": False,
        }

    def _telemetry_fails(self, state: GraphState) -> bool:
        for _ in range(MAX_TOOL_RETRIES):
            try:
                self.telemetry(state)
            except Exception:
                continue
            else:
                return False
        return True


_TRIAGE_SYSTEM = (
    "You are the evidence-gathering step of a Northwind HVAC incident assistant. Looking "
    "only at the incident text and the information it already supplies, decide: "
    "(1) supplied_sufficient - is the supplied information already enough to diagnose; "
    "(2) needs_retrieval - should you look up a Northwind manual document, and if so give a "
    "short retrieval_query; (3) needs_live_telemetry - does the request require pulling live "
    "equipment telemetry that is not already included; (4) evidence_conflict - do the supplied "
    "readings contradict each other; (5) gap_user_resolvable - if something is missing, could "
    "the requester plausibly supply it (true), does it need a technician/inspection (false), or "
    "is nothing missing (null). Reason only from the incident text. Do not invent readings."
)

_ASSESS_SYSTEM = (
    "You are assessing gathered evidence for a Northwind HVAC incident. You are given the "
    "incident and the evidence collected so far (incident-provided facts and retrieved manual "
    "excerpts). Decide: evidence_sufficient (enough to diagnose), evidence_conflict (a genuine "
    "contradiction in the readings), gap_user_resolvable (true if a missing detail the requester "
    "could supply would resolve it, false if it needs a technician/inspection, null if nothing is "
    "missing), and needs_more_retrieval (true only if one more lookup with a refined more_query is "
    "clearly warranted). Reason only from the provided evidence."
)


def _evidence_block(evidence: list[Evidence]) -> str:
    return "\n".join(f"[{e.source_id}] {e.content}" for e in evidence)


def make_llm_investigator(model, retriever: BM25Retriever | None = None) -> Investigator:
    """Build a real Investigator whose triage and assessment are structured LLM calls."""
    retriever = retriever or default_retriever()
    triage_model = model.with_structured_output(TriagePlan)
    assess_model = model.with_structured_output(EvidenceAssessment)

    def _triage(state: GraphState) -> TriagePlan:
        messages = [("system", _TRIAGE_SYSTEM), ("human", f"Incident: {state.incident_raw}")]
        return triage_model.invoke(messages)

    def _assess(state: GraphState, evidence: list[Evidence]) -> EvidenceAssessment:
        messages = [
            ("system", _ASSESS_SYSTEM),
            ("human", f"Incident: {state.incident_raw}\n\nEvidence:\n{_evidence_block(evidence)}"),
        ]
        return assess_model.invoke(messages)

    return Investigator(triage=_triage, assess=_assess, retriever=retriever)


def make_evidence_node(evidence_fn: EvidenceFn) -> Callable[[GraphState], dict]:
    def _node(state: GraphState) -> dict:
        return evidence_fn(state)

    return _node


# --- Diagnosis Specialist (Phase 1, structured) ---------------------------
class DiagnosisOutput(BaseModel):
    confidence: Confidence
    proposed_answer: Optional[str] = None
    hypotheses: list[str] = Field(default_factory=list)
    # Set only when Diagnosis identifies a genuine remaining gap (rule 6 ASK/ESCALATE).
    gap_user_resolvable: Optional[bool] = None


_DIAGNOSIS_SYSTEM = (
    "You are a diagnosis specialist for Northwind HVAC equipment. Base your reasoning ONLY on "
    "the supplied evidence: the incident-provided facts and any retrieved Northwind manual "
    "excerpts. Do not use outside HVAC knowledge that is not present in the evidence - this "
    "benchmark is deliberately closed-domain. Return: hypotheses (short list), confidence "
    "('low', 'medium', or 'high'), proposed_answer (the recommended next action, or null if the "
    "evidence does not support a confident recommendation), and gap_user_resolvable (true only if "
    "a specific detail the requester could supply would resolve a remaining uncertainty, else "
    "null). If you must rely on unstated knowledge to answer, lower your confidence and set "
    "proposed_answer to null instead."
)


def make_llm_diagnose(model) -> DiagnoseFn:
    structured = model.with_structured_output(DiagnosisOutput)

    def _diagnose(state: GraphState) -> DiagnosisOutput:
        messages = [
            ("system", _DIAGNOSIS_SYSTEM),
            (
                "human",
                f"Incident: {state.incident_raw}\n\nEvidence:\n{_evidence_block(state.evidence or [])}",
            ),
        ]
        return structured.invoke(messages)

    return _diagnose


def make_diagnosis_node(diagnose_fn: DiagnoseFn) -> Callable[[GraphState], dict]:
    def _node(state: GraphState) -> dict:
        try:
            out = diagnose_fn(state)
        except Exception:
            return {}  # fail-closed: no confidence -> ESCALATE(internal_error) at terminal
        if out is None:
            return {}
        # Diagnosis owns gap_user_resolvable at the terminal checkpoint (rule 6). It runs
        # after checkpoint B has already consumed the Investigator's value for rules 4/5,
        # so Diagnosis always writes its own value - including an explicit None - to avoid
        # a stale Investigator gap misrouting ASK vs ESCALATE(low_confidence).
        return {
            "confidence": out.confidence,
            "proposed_answer": out.proposed_answer,
            "hypotheses": out.hypotheses,
            "gap_user_resolvable": out.gap_user_resolvable,
        }

    return _node


# --- Grounding Validator (Phase 1, bounded) -------------------------------
class GroundingResult(BaseModel):
    answer_grounded: bool
    rationale: str = ""


_GROUNDING_SYSTEM = (
    "You are a grounding validator. Decide ONLY whether the substantive claims in the proposed "
    "answer are supported by the supplied evidence. Do NOT rewrite the answer, do NOT diagnose "
    "independently, do NOT suggest improvements, do NOT call tools or retrieve more evidence. "
    "Return answer_grounded true only if every substantive claim in the proposed answer is "
    "supported by the evidence; otherwise false."
)


def make_llm_ground(model) -> GroundFn:
    structured = model.with_structured_output(GroundingResult)

    def _ground(state: GraphState) -> Optional[bool]:
        messages = [
            ("system", _GROUNDING_SYSTEM),
            (
                "human",
                f"Proposed answer: {state.proposed_answer}\n\nEvidence:\n{_evidence_block(state.evidence or [])}",
            ),
        ]
        return structured.invoke(messages).answer_grounded

    return _ground


def make_grounding_node(ground_fn: GroundFn) -> Callable[[GraphState], dict]:
    def _node(state: GraphState) -> dict:
        # The validator runs only when a proposed answer exists.
        if state.proposed_answer is None:
            return {"answer_grounded": None}
        try:
            grounded = ground_fn(state)
        except Exception:
            # Malformed validator execution -> leave None -> ESCALATE(internal_error).
            return {"answer_grounded": None}
        return {"answer_grounded": grounded}

    return _node
