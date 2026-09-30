from __future__ import annotations

import pytest

from agent_reliability.contracts import (
    Evidence,
    GraphState,
    OutputContractError,
    validate_final_output,
)
from agent_reliability.enums import Confidence, Decision, Route, SourceType

EV = [Evidence(source_id="i", source_type=SourceType.INCIDENT_PROVIDED, content="c")]


def base(**kw) -> GraphState:
    d = dict(incident_id="t", incident_raw="x", safety_critical=False)
    d.update(kw)
    return GraphState(**d)


def test_progressive_state_is_optional_downstream():
    s = base()
    assert s.route is None
    assert s.confidence is None
    assert s.evidence is None
    assert s.answer_grounded is None
    assert s.hypotheses == []
    assert s.trace_id  # auto-generated, always present


def test_answer_output_valid():
    s = base(route=Route.INVESTIGATE, decision=Decision.ANSWER, confidence=Confidence.HIGH, proposed_answer="do x", answer_grounded=True, evidence=EV)
    validate_final_output(s)


def test_answer_missing_answer_raises():
    s = base(route=Route.INVESTIGATE, decision=Decision.ANSWER, confidence=Confidence.HIGH, proposed_answer=None, answer_grounded=True, evidence=EV)
    with pytest.raises(OutputContractError):
        validate_final_output(s)


def test_answer_missing_grounding_raises():
    s = base(route=Route.INVESTIGATE, decision=Decision.ANSWER, confidence=Confidence.HIGH, proposed_answer="x", answer_grounded=None, evidence=EV)
    with pytest.raises(OutputContractError):
        validate_final_output(s)


def test_ask_requires_question_and_gap():
    with pytest.raises(OutputContractError):
        validate_final_output(base(route=Route.INVESTIGATE, decision=Decision.ASK, clarifying_question=None, gap_user_resolvable=True))
    validate_final_output(base(route=Route.INVESTIGATE, decision=Decision.ASK, clarifying_question="q?", gap_user_resolvable=True))


def test_escalate_requires_reason():
    with pytest.raises(OutputContractError):
        validate_final_output(base(route=Route.INVESTIGATE, decision=Decision.ESCALATE, escalation_reason=None))


def test_abstain_requires_reason():
    with pytest.raises(OutputContractError):
        validate_final_output(base(route=Route.OUT_OF_SCOPE, decision=Decision.ABSTAIN, abstain_reason=None))
