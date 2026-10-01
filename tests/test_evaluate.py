"""Evaluation scoring logic (pure, offline): per-dimension scoring + aggregation."""

from __future__ import annotations

from agent_reliability.contracts import Evidence, GraphState
from agent_reliability.dataset import load_seed_cases
from agent_reliability.enums import (
    Confidence,
    Decision,
    EscalationReason,
    Route,
    SourceType,
)
from agent_reliability.evaluate import aggregate, observed_retrieval_behavior, retrieved_ids, score_case

CASES = {c.id: c for c in load_seed_cases()}


def _incident(cid: str) -> Evidence:
    return Evidence(source_id=f"incident:{cid}", source_type=SourceType.INCIDENT_PROVIDED, content="x")


def _manual(doc_id: str) -> Evidence:
    return Evidence(source_id=doc_id, source_type=SourceType.RETRIEVED_MANUAL, content="y")


def _state(cid, **kw) -> GraphState:
    d = dict(incident_id=cid, incident_raw="x", safety_critical=False)
    d.update(kw)
    return GraphState(**d)


def test_retrieved_ids_and_behavior_helpers():
    s = _state("t", evidence=[_incident("t"), _manual("DOC-RTU-A11")])
    assert retrieved_ids(s) == ["DOC-RTU-A11"]
    assert observed_retrieval_behavior(s) == "retrieved"
    assert observed_retrieval_behavior(_state("t", evidence=[_incident("t")])) == "no_retrieval"
    assert observed_retrieval_behavior(_state("t", evidence=None)) == "not_run"


def test_perfect_answer_case_scores_all_correct():
    case = CASES["ARC-01"]  # INVESTIGATE / ANSWER / required DOC-RTU-A11
    s = _state(
        "ARC-01",
        route=Route.INVESTIGATE,
        decision=Decision.ANSWER,
        confidence=Confidence.HIGH,
        proposed_answer="Clean the coil.",
        answer_grounded=True,
        evidence=[_incident("ARC-01"), _manual("DOC-RTU-A11")],
    )
    r = score_case(case, s, contract_valid=True, latency_s=0.5)
    assert r.scores["route_correct"] is True
    assert r.scores["decision_correct"] is True
    assert r.scores["retrieval_behavior_correct"] is True
    assert r.scores["retrieval_source_correct"] is True
    assert r.scores["grounding_correct"] is True
    assert r.scores["distractor_pulled"] is False
    assert r.scores["structured_output_valid"] is True


def test_retrieval_source_miss_detected():
    case = CASES["ARC-01"]
    s = _state(
        "ARC-01",
        route=Route.INVESTIGATE,
        decision=Decision.ANSWER,
        answer_grounded=True,
        evidence=[_incident("ARC-01"), _manual("DOC-SENSOR-A21")],  # wrong doc
    )
    r = score_case(case, s, contract_valid=True, latency_s=0.1)
    assert r.scores["retrieval_behavior_correct"] is True  # it did retrieve
    assert r.scores["retrieval_source_correct"] is False  # but not the expected doc


def test_distractor_pulled_flagged():
    case = CASES["ARC-14"]  # distractor DOC-RTU-CYCLE
    s = _state(
        "ARC-14",
        route=Route.INVESTIGATE,
        decision=Decision.ANSWER,
        answer_grounded=True,
        evidence=[_incident("ARC-14"), _manual("DOC-RTU-A11"), _manual("DOC-RTU-CYCLE")],
    )
    r = score_case(case, s, contract_valid=True, latency_s=0.1)
    assert r.scores["distractor_pulled"] is True
    assert r.scores["retrieval_source_correct"] is True  # expected doc still present


def test_skip_behavior_scored():
    case = CASES["ARC-16"]  # expected skip
    s = _state(
        "ARC-16",
        route=Route.INVESTIGATE,
        decision=Decision.ANSWER,
        answer_grounded=True,
        evidence=[_incident("ARC-16")],  # ran, no retrieval
    )
    r = score_case(case, s, contract_valid=True, latency_s=0.1)
    assert r.scores["retrieval_behavior_correct"] is True
    assert r.scores["retrieval_source_correct"] is None  # n/a for skip


def test_not_applicable_behavior_scored():
    case = CASES["ARC-11"]  # OUT_OF_SCOPE / ABSTAIN / not_applicable
    s = _state(
        "ARC-11",
        route=Route.OUT_OF_SCOPE,
        decision=Decision.ABSTAIN,
        abstain_reason=None,
        evidence=None,  # Investigator never ran
    )
    # give it the right abstain reason
    s.abstain_reason = case.expected_abstain_reason
    r = score_case(case, s, contract_valid=True, latency_s=0.1)
    assert r.scores["retrieval_behavior_correct"] is True
    assert r.scores["reason_correct"] is True


def test_escalation_reason_mismatch_detected():
    case = CASES["ARC-03"]  # ESCALATE(evidence_unresolvable)
    s = _state(
        "ARC-03",
        route=Route.INVESTIGATE,
        decision=Decision.ESCALATE,
        escalation_reason=EscalationReason.LOW_CONFIDENCE,  # wrong reason
        evidence=[_incident("ARC-03"), _manual("DOC-COMMS-A31")],
    )
    r = score_case(case, s, contract_valid=True, latency_s=0.1)
    assert r.scores["decision_correct"] is True
    assert r.scores["reason_correct"] is False


def test_aggregate_has_no_composite_and_counts_applicable_only():
    case = CASES["ARC-01"]
    good = score_case(
        case,
        _state("ARC-01", route=Route.INVESTIGATE, decision=Decision.ANSWER, answer_grounded=True,
               evidence=[_incident("ARC-01"), _manual("DOC-RTU-A11")]),
        contract_valid=True,
        latency_s=0.2,
    )
    bad = score_case(
        case,
        _state("ARC-01", route=Route.OUT_OF_SCOPE, decision=Decision.ABSTAIN,
               evidence=[_incident("ARC-01")]),
        contract_valid=False,
        latency_s=0.4,
    )
    agg = aggregate([good, bad])
    assert "composite" not in agg and "agent_score" not in agg
    assert agg["route_correct"] == {"passed": 1, "total": 2, "rate": 0.5, "failed_cases": ["ARC-01"]}
    assert agg["n_cases"] == 2
    assert agg["latency_s"]["max"] == 0.4
