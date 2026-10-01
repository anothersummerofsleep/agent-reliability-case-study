"""Diagnosis Specialist: structured-output parsing, gap merge, fail-closed behavior."""

from __future__ import annotations

from _fakes import FakeModel

from agent_reliability.contracts import Evidence, GraphState
from agent_reliability.enums import Confidence, SourceType
from agent_reliability.nodes import DiagnosisOutput, make_diagnosis_node, make_llm_diagnose


def _state(**kw) -> GraphState:
    d = dict(
        incident_id="t",
        incident_raw="RTU-40 NW-A11 fouled coil",
        safety_critical=False,
        evidence=[Evidence(source_id="incident:t", source_type=SourceType.INCIDENT_PROVIDED, content="x")],
    )
    d.update(kw)
    return GraphState(**d)


def test_structured_output_parsed_onto_state():
    model = FakeModel(
        DiagnosisOutput(confidence=Confidence.HIGH, proposed_answer="Clean the coil.", hypotheses=["fouled coil"])
    )
    node = make_diagnosis_node(make_llm_diagnose(model))
    update = node(_state())
    assert update["confidence"] is Confidence.HIGH
    assert update["proposed_answer"] == "Clean the coil."
    assert update["hypotheses"] == ["fouled coil"]


def test_gap_set_only_when_diagnosis_returns_one():
    without = make_diagnosis_node(
        make_llm_diagnose(FakeModel(DiagnosisOutput(confidence=Confidence.MEDIUM, proposed_answer=None)))
    )(_state())
    assert "gap_user_resolvable" not in without  # preserves the Investigator's value

    withgap = make_diagnosis_node(
        make_llm_diagnose(
            FakeModel(DiagnosisOutput(confidence=Confidence.MEDIUM, proposed_answer=None, gap_user_resolvable=True))
        )
    )(_state())
    assert withgap["gap_user_resolvable"] is True


def test_parse_failure_fails_closed():
    # A model that raises (e.g. structured-output parse failure) leaves confidence unset,
    # which the terminal policy checkpoint turns into ESCALATE(internal_error).
    node = make_diagnosis_node(make_llm_diagnose(FakeModel(ValueError("bad json"))))
    assert node(_state()) == {}


def test_none_output_fails_closed():
    node = make_diagnosis_node(lambda s: None)
    assert node(_state()) == {}
