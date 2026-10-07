"""Diagnostic instrumentation: logging occurs; fail-closed behavior is unchanged."""

from __future__ import annotations

import logging

from _fakes import FakeModel

from agent_reliability.contracts import Evidence, GraphState
from agent_reliability.enums import Confidence, SourceType
from agent_reliability.nodes import (
    DiagnosisOutput,
    EvidenceAssessment,
    GroundingResult,
    Investigator,
    TriagePlan,
    make_diagnosis_node,
    make_grounding_node,
    make_initial_state,
    make_llm_diagnose,
    make_llm_ground,
)
from agent_reliability.retrieval import default_retriever

LOGGER = "agent_reliability.diagnostics"


def _state(**kw) -> GraphState:
    d = dict(
        incident_id="ARC-TEST",
        incident_raw="RTU-40 NW-A11 fouled coil",
        safety_critical=False,
        evidence=[Evidence(source_id="incident:ARC-TEST", source_type=SourceType.INCIDENT_PROVIDED, content="x")],
    )
    d.update(kw)
    return GraphState(**d)


def test_diagnosis_exception_is_logged_and_still_fails_closed(caplog):
    with caplog.at_level(logging.ERROR, logger=LOGGER):
        out = make_diagnosis_node(make_llm_diagnose(FakeModel(ValueError("bad json"))))(_state())
    assert out == {}  # fail-closed behavior identical
    assert "DIAGNOSIS ERROR" in caplog.text
    assert "ARC-TEST" in caplog.text
    assert "ValueError" in caplog.text


def test_successful_diagnosis_is_logged(caplog):
    model = FakeModel(DiagnosisOutput(confidence=Confidence.HIGH, proposed_answer="Clean coil.", hypotheses=["a", "b"]))
    with caplog.at_level(logging.INFO, logger=LOGGER):
        out = make_diagnosis_node(make_llm_diagnose(model))(_state())
    assert out["confidence"] is Confidence.HIGH  # behavior unchanged
    assert "DIAGNOSIS id=ARC-TEST" in caplog.text
    assert "confidence=high" in caplog.text
    assert "has_answer=True" in caplog.text


def test_grounding_exception_is_logged_and_leaves_none(caplog):
    with caplog.at_level(logging.ERROR, logger=LOGGER):
        out = make_grounding_node(make_llm_ground(FakeModel(ValueError("bad"))))(_state(proposed_answer="Clean coil."))
    assert out == {"answer_grounded": None}  # still fail-closed to internal_error, not False
    assert "GROUNDING ERROR" in caplog.text
    assert "ARC-TEST" in caplog.text


def test_triage_is_logged(caplog):
    inv = Investigator(
        triage=lambda s: TriagePlan(supplied_sufficient=True, needs_retrieval=False, gap_user_resolvable=None),
        assess=lambda s, e, p: EvidenceAssessment(evidence_sufficient=True),
        retriever=default_retriever(),
    )
    with caplog.at_level(logging.INFO, logger=LOGGER):
        inv(make_initial_state("ARC-TEST", "RTU-40 NW-A11 fouled coil"))
    assert "TRIAGE id=ARC-TEST" in caplog.text
    assert "needs_retrieval=False" in caplog.text
