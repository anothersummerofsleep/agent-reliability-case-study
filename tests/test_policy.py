"""Deterministic policy coverage - the policy is exercised more deeply than the graph.

Every reachable decision/reason branch, the rule-7 guard vs rule-8 collision, and the
'None never triggers a later rule' guarantee.
"""

from __future__ import annotations

from agent_reliability.contracts import Evidence, GraphState
from agent_reliability.enums import (
    AbstainReason,
    Confidence,
    Decision,
    EscalationReason,
    Route,
    SourceType,
)
from agent_reliability.policy import evaluate_policy

EV = [Evidence(source_id="i", source_type=SourceType.INCIDENT_PROVIDED, content="c")]


def mk(**kw) -> GraphState:
    base = dict(incident_id="t", incident_raw="x", safety_critical=False)
    base.update(kw)
    return GraphState(**base)


def test_safety_is_first_even_over_scope():
    r = evaluate_policy(
        mk(safety_critical=True, route=Route.OUT_OF_SCOPE, abstain_reason=AbstainReason.OUT_OF_DOMAIN),
        terminal=True,
    )
    assert r.decision is Decision.ESCALATE and r.escalation_reason is EscalationReason.SAFETY


def test_out_of_scope_valid_reason_abstains():
    r = evaluate_policy(mk(route=Route.OUT_OF_SCOPE, abstain_reason=AbstainReason.UNSUPPORTED_INFERENCE), terminal=True)
    assert r.decision is Decision.ABSTAIN and r.abstain_reason is AbstainReason.UNSUPPORTED_INFERENCE


def test_out_of_scope_missing_reason_fails_closed():
    r = evaluate_policy(mk(route=Route.OUT_OF_SCOPE, abstain_reason=None), terminal=True)
    assert r.decision is Decision.ESCALATE and r.escalation_reason is EscalationReason.INTERNAL_ERROR


def test_tool_failure():
    r = evaluate_policy(mk(route=Route.INVESTIGATE, tool_failed=True), terminal=True)
    assert r.escalation_reason is EscalationReason.TOOL_FAILURE


def test_conflict_ask():
    r = evaluate_policy(mk(route=Route.INVESTIGATE, evidence_conflict=True, gap_user_resolvable=True), terminal=True)
    assert r.decision is Decision.ASK


def test_conflict_escalate_on_false_gap():
    r = evaluate_policy(mk(route=Route.INVESTIGATE, evidence_conflict=True, gap_user_resolvable=False), terminal=True)
    assert r.escalation_reason is EscalationReason.CONFLICT_UNRESOLVABLE


def test_conflict_escalate_on_none_gap():
    r = evaluate_policy(mk(route=Route.INVESTIGATE, evidence_conflict=True, gap_user_resolvable=None), terminal=True)
    assert r.escalation_reason is EscalationReason.CONFLICT_UNRESOLVABLE


def test_insufficient_ask():
    r = evaluate_policy(mk(route=Route.INVESTIGATE, evidence_sufficient=False, gap_user_resolvable=True), terminal=True)
    assert r.decision is Decision.ASK


def test_insufficient_escalate():
    r = evaluate_policy(mk(route=Route.INVESTIGATE, evidence_sufficient=False, gap_user_resolvable=False), terminal=True)
    assert r.escalation_reason is EscalationReason.EVIDENCE_UNRESOLVABLE


def test_low_confidence_ask():
    r = evaluate_policy(
        mk(route=Route.INVESTIGATE, evidence_sufficient=True, evidence_conflict=False, confidence=Confidence.MEDIUM, gap_user_resolvable=True),
        terminal=True,
    )
    assert r.decision is Decision.ASK


def test_low_confidence_escalate():
    r = evaluate_policy(
        mk(route=Route.INVESTIGATE, evidence_sufficient=True, evidence_conflict=False, confidence=Confidence.LOW, gap_user_resolvable=False),
        terminal=True,
    )
    assert r.escalation_reason is EscalationReason.LOW_CONFIDENCE


def test_high_confidence_missing_answer_internal_error():
    r = evaluate_policy(
        mk(route=Route.INVESTIGATE, evidence_sufficient=True, evidence_conflict=False, confidence=Confidence.HIGH, proposed_answer=None, evidence=EV),
        terminal=True,
    )
    assert r.escalation_reason is EscalationReason.INTERNAL_ERROR


def test_grounding_failure():
    r = evaluate_policy(
        mk(route=Route.INVESTIGATE, evidence_sufficient=True, evidence_conflict=False, confidence=Confidence.HIGH, proposed_answer="x", answer_grounded=False, evidence=EV),
        terminal=True,
    )
    assert r.escalation_reason is EscalationReason.GROUNDING_FAILURE


def test_rule7_guard_precedes_grounding_rule8():
    # high + no answer + answer_grounded False -> internal_error (rule 7), NOT grounding_failure
    r = evaluate_policy(
        mk(route=Route.INVESTIGATE, evidence_sufficient=True, evidence_conflict=False, confidence=Confidence.HIGH, proposed_answer=None, answer_grounded=False, evidence=EV),
        terminal=True,
    )
    assert r.escalation_reason is EscalationReason.INTERNAL_ERROR


def test_answer():
    r = evaluate_policy(
        mk(route=Route.INVESTIGATE, evidence_sufficient=True, evidence_conflict=False, confidence=Confidence.HIGH, proposed_answer="do x", answer_grounded=True, evidence=EV),
        terminal=True,
    )
    assert r.decision is Decision.ANSWER


def test_malformed_terminal_fails_closed():
    # high + answer present + answer_grounded None -> terminal fallthrough -> internal_error
    r = evaluate_policy(
        mk(route=Route.INVESTIGATE, evidence_sufficient=True, evidence_conflict=False, confidence=Confidence.HIGH, proposed_answer="x", answer_grounded=None, evidence=EV),
        terminal=True,
    )
    assert r.decision is Decision.ESCALATE and r.escalation_reason is EscalationReason.INTERNAL_ERROR


def test_continue_is_none_before_terminal():
    assert evaluate_policy(mk(route=Route.INVESTIGATE), terminal=False) is None


def test_none_confidence_does_not_trigger_low_confidence():
    assert evaluate_policy(mk(route=Route.INVESTIGATE, evidence_sufficient=True, evidence_conflict=False, confidence=None), terminal=False) is None


def test_none_sufficient_does_not_trigger_insufficient():
    assert evaluate_policy(mk(route=Route.INVESTIGATE, evidence_sufficient=None), terminal=False) is None


def test_answer_never_a_fallthrough_when_ungrounded():
    # high + answer + evidence but answer_grounded None -> not ANSWER; CONTINUE at non-terminal
    r = evaluate_policy(
        mk(route=Route.INVESTIGATE, evidence_sufficient=True, evidence_conflict=False, confidence=Confidence.HIGH, proposed_answer="x", answer_grounded=None, evidence=EV),
        terminal=False,
    )
    assert r is None
