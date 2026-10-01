from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_reliability.dataset import RetrievalBehavior, SeedCase, Tier, coverage, load_seed_cases
from agent_reliability.enums import AbstainReason, Decision, EscalationReason, Route


def test_loads_all_22_cases_in_order():
    cases = load_seed_cases()
    assert len(cases) == 22
    assert [c.id for c in cases] == [f"ARC-{i:02d}" for i in range(1, 23)]


def test_full_coverage_matrix():
    cov = coverage(load_seed_cases())
    assert cov["routes"] == set(Route)
    assert cov["decisions"] == set(Decision)
    assert cov["escalation_reasons"] == set(EscalationReason)
    assert cov["abstain_reasons"] == set(AbstainReason)
    assert cov["retrieval_behaviors"] == set(RetrievalBehavior)
    assert cov["tiers"] == set(Tier)


def test_per_case_reason_and_retrieval_invariants():
    for c in load_seed_cases():
        if c.expected_decision is Decision.ESCALATE:
            assert c.expected_escalation_reason is not None, c.id
        if c.expected_decision is Decision.ABSTAIN:
            assert c.expected_abstain_reason is not None, c.id
        if c.expected_retrieval_behavior is RetrievalBehavior.REQUIRED:
            assert c.expected_retrieval_ids, c.id
        if c.expected_route is Route.OUT_OF_SCOPE:
            assert c.expected_retrieval_behavior is RetrievalBehavior.NOT_APPLICABLE, c.id


def test_both_tiers_present():
    tiers = {c.tier for c in load_seed_cases()}
    assert Tier.E2E in tiers and Tier.UNIT in tiers


def test_prohibited_extra_field_rejected():
    payload = load_seed_cases()[0].model_dump()
    payload["expected_tool_call"] = "some_tool"  # tool-behavior fields are out of scope
    with pytest.raises(ValidationError):
        SeedCase.model_validate(payload)
