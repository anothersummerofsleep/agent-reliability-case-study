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


def test_allowed_behavior_is_scored():
    case = CASES["ARC-02"]  # allowed
    ran_no_fetch = score_case(
        case, _state("ARC-02", route=Route.INVESTIGATE, decision=Decision.ASK,
                     gap_user_resolvable=True, clarifying_question="?",
                     evidence=[_incident("ARC-02")]),
        contract_valid=True, latency_s=0.1,
    )
    assert ran_no_fetch.scores["retrieval_behavior_correct"] is True  # ran, no retrieval -> ok
    fetched = score_case(
        case, _state("ARC-02", route=Route.INVESTIGATE, decision=Decision.ASK,
                     gap_user_resolvable=True, clarifying_question="?",
                     evidence=[_incident("ARC-02"), _manual("DOC-CHW-EFF")]),
        contract_valid=True, latency_s=0.1,
    )
    assert fetched.scores["retrieval_behavior_correct"] is True  # retrieved -> also ok
    not_run = score_case(
        case, _state("ARC-02", route=Route.INVESTIGATE, decision=Decision.ASK,
                     gap_user_resolvable=True, clarifying_question="?", evidence=None),
        contract_valid=True, latency_s=0.1,
    )
    assert not_run.scores["retrieval_behavior_correct"] is False  # should have run


def test_distractor_counted_even_without_case_label():
    case = CASES["ARC-01"]  # no distractor_ids on this case
    s = _state("ARC-01", route=Route.INVESTIGATE, decision=Decision.ANSWER, answer_grounded=True,
               evidence=[_incident("ARC-01"), _manual("DOC-RTU-A11"), _manual("DOC-AHU-VFD")])
    r = score_case(case, s, contract_valid=True, latency_s=0.1)
    assert r.scores["distractor_pulled"] is True  # DOC-AHU-VFD is a canonical distractor
    assert r.observed["pulled_distractors"] == ["DOC-AHU-VFD"]


def test_structured_output_invalid_on_fail_closed_internal_error():
    from agent_reliability.enums import EscalationReason

    case = CASES["ARC-01"]  # gold ANSWER; a terminal internal_error means a fail-closed fault
    s = _state("ARC-01", route=Route.INVESTIGATE, decision=Decision.ESCALATE,
               escalation_reason=EscalationReason.INTERNAL_ERROR,
               evidence=[_incident("ARC-01")])
    r = score_case(case, s, contract_valid=True, latency_s=0.1)
    assert r.scores["output_contract_valid"] is True   # the terminal output is contract-valid
    assert r.scores["structured_output_valid"] is False  # but it fell closed -> not valid


def test_aggregate_survives_exception_shaped_result():
    # Mirrors run_baseline's exception path; aggregate must not KeyError.
    from agent_reliability.evaluate import CaseResult

    err = CaseResult(
        id="ARC-14", tier="E2E",
        expected={"route": "INVESTIGATE", "decision": "ANSWER", "reason": None,
                  "retrieval_behavior": "required", "retrieval_ids": ["DOC-RTU-A11"],
                  "distractor_ids": ["DOC-RTU-CYCLE"]},
        observed={"error": "boom", "retrieved_ids": [], "pulled_distractors": [],
                  "output_contract_valid": False, "latency_s": 0.0},
        scores={"route_correct": False, "decision_correct": False, "reason_correct": None,
                "retrieval_behavior_correct": None, "retrieval_source_correct": None,
                "distractor_pulled": False, "grounding_correct": None,
                "output_contract_valid": False, "structured_output_valid": False},
    )
    agg = aggregate([err])  # must not raise
    assert agg["n_cases"] == 1
    assert agg["distractor_resistance"]["clean"] == 1


def test_mechanism_state_exposes_actual_graph_state():
    from agent_reliability.enums import EscalationReason
    from agent_reliability.evaluate import mechanism_state

    s = _state("ARC-X", route=Route.INVESTIGATE, decision=Decision.ESCALATE,
               escalation_reason=EscalationReason.CONFLICT_UNRESOLVABLE,
               evidence_conflict=True, gap_user_resolvable=False, evidence_sufficient=True,
               tool_failed=False, confidence=Confidence.MEDIUM, proposed_answer="x")
    ms = mechanism_state(s)
    assert ms["evidence_conflict"] is True
    assert ms["gap_user_resolvable"] is False
    assert ms["confidence"] == "medium"
    assert ms["has_proposed_answer"] is True
    assert ms["decision"] == "ESCALATE"
    assert ms["escalation_reason"] == "conflict_unresolvable"


def test_mechanism_state_preserves_nulls():
    from agent_reliability.evaluate import mechanism_state

    ms = mechanism_state(_state("ARC-X", route=Route.INVESTIGATE, decision=Decision.ANSWER))
    assert ms["evidence_conflict"] is None  # never coerced to False
    assert ms["gap_user_resolvable"] is None
    assert ms["confidence"] is None
    assert ms["has_proposed_answer"] is False
    assert ms["escalation_reason"] is None


def test_mechanism_state_in_observed_without_changing_scores():
    case = CASES["ARC-01"]
    s = _state("ARC-01", route=Route.INVESTIGATE, decision=Decision.ANSWER, answer_grounded=True,
               evidence=[_incident("ARC-01"), _manual("DOC-RTU-A11")], evidence_conflict=False,
               confidence=Confidence.HIGH, proposed_answer="do x")
    r = score_case(case, s, contract_valid=True, latency_s=0.2)
    # scoring unchanged (same keys/values as before instrumentation)
    assert r.scores["decision_correct"] is True and r.scores["grounding_correct"] is True
    # observability present and faithful
    assert r.observed["mechanism_state"]["decision"] == "ANSWER"
    assert r.observed["mechanism_state"]["evidence_conflict"] is False
    # no secrets / credentials leak into the artifact record
    import json as _json
    blob = _json.dumps(r.observed).lower()
    assert "api" not in blob and "key" not in blob and "secret" not in blob and "token" not in blob


def test_median_even_count():
    from agent_reliability.evaluate import _median

    assert _median([0.1, 0.3, 0.5, 0.7]) == 0.4  # mean of two middles
    assert _median([0.1, 0.2, 0.9]) == 0.2       # true middle for odd count


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
