"""Bounded Evidence Investigator: skip/retrieve/telemetry paths, boundedness, provenance."""

from __future__ import annotations

from agent_reliability.contracts import Evidence, GraphState
from agent_reliability.enums import SourceType
from agent_reliability.nodes import (
    MAX_RETRIEVAL_ATTEMPTS,
    EvidenceAssessment,
    Investigator,
    TriagePlan,
    ToolUnavailableError,
    make_initial_state,
)
from agent_reliability.retrieval import default_retriever


def _state(text: str = "RTU-40 unit 3 NW-A11, discharge 415 psi, condenser coil fouled.") -> GraphState:
    return make_initial_state("t", text)


def _retrieved_ids(evidence: list[Evidence]) -> list[str]:
    return [e.source_id for e in evidence if e.source_type is SourceType.RETRIEVED_MANUAL]


def test_normalizes_incident_into_provenance():
    inv = Investigator(
        triage=lambda s: TriagePlan(supplied_sufficient=True, needs_retrieval=False),
        assess=lambda s, e: EvidenceAssessment(evidence_sufficient=True),
        retriever=default_retriever(),
    )
    out = inv(_state())
    ev = out["evidence"]
    assert ev[0].source_type is SourceType.INCIDENT_PROVIDED
    assert ev[0].source_id == "incident:t"
    assert ev[0].content  # non-empty


def test_skip_branch_uses_triage_assessment_without_retrieval():
    inv = Investigator(
        triage=lambda s: TriagePlan(
            supplied_sufficient=True, needs_retrieval=False, evidence_conflict=False, gap_user_resolvable=None
        ),
        assess=lambda s, e: (_ for _ in ()).throw(AssertionError("assess must not run on skip")),
        retriever=default_retriever(),
    )
    out = inv(_state())
    assert out["evidence_sufficient"] is True
    assert out["tool_failed"] is False
    assert _retrieved_ids(out["evidence"]) == []  # no retrieval occurred


def test_required_branch_retrieves_and_sets_provenance():
    inv = Investigator(
        triage=lambda s: TriagePlan(
            supplied_sufficient=False, needs_retrieval=True, retrieval_query="NW-A11 high head pressure condenser coil"
        ),
        assess=lambda s, e: EvidenceAssessment(evidence_sufficient=True),
        retriever=default_retriever(),
    )
    out = inv(_state())
    ids = _retrieved_ids(out["evidence"])
    assert "DOC-RTU-A11" in ids
    assert all(e.content for e in out["evidence"])


def test_bounded_retrieval_stops_at_max_attempts():
    calls = {"assess": 0}

    def greedy_assess(s, e):
        calls["assess"] += 1
        return EvidenceAssessment(evidence_sufficient=False, needs_more_retrieval=True, more_query="sensor fault NW-A21")

    inv = Investigator(
        triage=lambda s: TriagePlan(supplied_sufficient=False, needs_retrieval=True, retrieval_query="NW-A11"),
        assess=greedy_assess,
        retriever=default_retriever(),
    )
    out = inv(_state())
    # Even though assess always asks for more, the loop is hard-capped.
    assert calls["assess"] == MAX_RETRIEVAL_ATTEMPTS
    assert out["evidence_sufficient"] is False


def test_telemetry_request_fails_closed_to_tool_failed():
    inv = Investigator(
        triage=lambda s: TriagePlan(supplied_sufficient=False, needs_retrieval=False, needs_live_telemetry=True),
        assess=lambda s, e: EvidenceAssessment(evidence_sufficient=True),
        retriever=default_retriever(),
    )
    out = inv(_state("Pull RTU-50 unit 1 last 24h telemetry and tell me why it trips NW-A51."))
    assert out["tool_failed"] is True
    assert out["evidence_sufficient"] is False


def test_telemetry_success_does_not_set_tool_failed():
    def ok_telemetry(state):
        return None  # a working tool

    inv = Investigator(
        triage=lambda s: TriagePlan(
            supplied_sufficient=True, needs_retrieval=False, needs_live_telemetry=True
        ),
        assess=lambda s, e: EvidenceAssessment(evidence_sufficient=True),
        retriever=default_retriever(),
        telemetry=ok_telemetry,
    )
    out = inv(_state())
    assert out["tool_failed"] is False
    assert out["evidence_sufficient"] is True


def test_default_telemetry_raises():
    import pytest

    from agent_reliability.nodes import default_telemetry

    with pytest.raises(ToolUnavailableError):
        default_telemetry(_state())


class _FailingRetriever:
    def search(self, query, k=2):
        raise RuntimeError("retrieval backend down")

    def doc(self, doc_id):  # pragma: no cover - never reached
        raise KeyError(doc_id)


def test_retrieval_failure_exposed_as_tool_failed():
    inv = Investigator(
        triage=lambda s: TriagePlan(supplied_sufficient=False, needs_retrieval=True, retrieval_query="NW-A11"),
        assess=lambda s, e: EvidenceAssessment(evidence_sufficient=True),
        retriever=_FailingRetriever(),
    )
    out = inv(_state())
    assert out["tool_failed"] is True  # clean exposure, not a crash
    assert out["evidence_sufficient"] is False


def test_gap_passthrough_from_triage_on_skip():
    inv = Investigator(
        triage=lambda s: TriagePlan(
            supplied_sufficient=False, needs_retrieval=False, gap_user_resolvable=True
        ),
        assess=lambda s, e: EvidenceAssessment(evidence_sufficient=True),
        retriever=default_retriever(),
    )
    out = inv(_state("CH-2 doesn't seem to be cooling well today."))
    assert out["gap_user_resolvable"] is True
