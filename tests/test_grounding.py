"""Grounding Validator: runs only with an answer, structured parsing, fail-closed to None."""

from __future__ import annotations

from _fakes import FakeModel

from agent_reliability.contracts import Evidence, GraphState
from agent_reliability.enums import SourceType
from agent_reliability.nodes import GroundingResult, make_grounding_node, make_llm_ground


def _state(**kw) -> GraphState:
    d = dict(
        incident_id="t",
        incident_raw="RTU-40 NW-A11 fouled coil",
        safety_critical=False,
        evidence=[Evidence(source_id="DOC-RTU-A11", source_type=SourceType.RETRIEVED_MANUAL, content="high head pressure: clean coil")],
    )
    d.update(kw)
    return GraphState(**d)


def test_does_not_run_without_proposed_answer():
    node = make_grounding_node(make_llm_ground(FakeModel(GroundingResult(answer_grounded=True))))
    assert node(_state(proposed_answer=None)) == {"answer_grounded": None}


def test_grounded_true_parsed():
    node = make_grounding_node(make_llm_ground(FakeModel(GroundingResult(answer_grounded=True))))
    assert node(_state(proposed_answer="Clean the coil.")) == {"answer_grounded": True}


def test_grounded_false_parsed():
    node = make_grounding_node(make_llm_ground(FakeModel(GroundingResult(answer_grounded=False))))
    assert node(_state(proposed_answer="Replace the compressor.")) == {"answer_grounded": False}


def test_validator_failure_leaves_none_not_false():
    # Malformed validator execution must fail to internal_error (None), NOT grounding_failure.
    node = make_grounding_node(make_llm_ground(FakeModel(ValueError("bad json"))))
    assert node(_state(proposed_answer="Clean the coil.")) == {"answer_grounded": None}
