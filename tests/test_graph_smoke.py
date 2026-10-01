"""Graph smoke tests - prove flow end-to-end with a fake model (no API keys)."""

from __future__ import annotations

from agent_reliability.contracts import Evidence, GraphState, validate_final_output
from agent_reliability.enums import Confidence, Decision, EscalationReason, Route, SourceType
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


def test_ask_path_produces_contract_valid_output():
    # Inject an Investigator result with a user-resolvable gap so the graph emits ASK.
    def evidence_insufficient(state: GraphState) -> dict:
        return {
            "evidence": [Evidence(source_id=f"incident:{state.incident_id}", source_type=SourceType.INCIDENT_PROVIDED, content=state.incident_raw)],
            "evidence_sufficient": False,
            "evidence_conflict": False,
            "tool_failed": False,
            "gap_user_resolvable": True,
        }

    s = run_incident(
        "t4",
        "CH-2 doesn't seem to be cooling well today.",
        diagnose_fn=fake_diagnose,
        evidence_fn=evidence_insufficient,
    )
    assert s.decision is Decision.ASK
    assert s.clarifying_question is not None
    validate_final_output(s)
