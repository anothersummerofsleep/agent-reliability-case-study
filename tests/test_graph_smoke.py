"""Graph smoke tests - prove flow end-to-end with a fake model (no API keys)."""

from __future__ import annotations

from agent_reliability.contracts import GraphState, validate_final_output
from agent_reliability.enums import Confidence, Decision, EscalationReason, Route
from agent_reliability.graph import run_incident
from agent_reliability.nodes import DiagnosisOutput


def fake_diagnose(state: GraphState) -> DiagnosisOutput:
    return DiagnosisOutput(
        confidence=Confidence.HIGH,
        proposed_answer="Clean the condenser coil and verify head pressure normalises.",
        hypotheses=["fouled condenser coil"],
    )


def test_investigate_answer_end_to_end():
    s = run_incident(
        "t1",
        "RTU-40 unit 3 tripped NW-A11, discharge 415 psi, condenser coil fouled.",
        diagnose_fn=fake_diagnose,
    )
    assert s.route is Route.INVESTIGATE
    assert s.decision is Decision.ANSWER
    validate_final_output(s)


def test_out_of_scope_abstains():
    s = run_incident(
        "t2",
        "Which chiller brand and model should we buy to replace our aging units?",
        diagnose_fn=fake_diagnose,
    )
    assert s.route is Route.OUT_OF_SCOPE
    assert s.decision is Decision.ABSTAIN
    assert s.abstain_reason is not None


def test_safety_short_circuits_before_diagnosis():
    s = run_incident(
        "t3",
        "Burning smell and smoke near the AHU-2 motor starter; unit still running.",
        diagnose_fn=fake_diagnose,
    )
    assert s.decision is Decision.ESCALATE
    assert s.escalation_reason is EscalationReason.SAFETY
