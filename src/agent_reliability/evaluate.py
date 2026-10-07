"""Phase 1 baseline evaluation harness.

Two layers, kept separate so the scoring logic is unit-testable offline:

* ``score_case`` / ``aggregate`` are pure functions over a terminal ``GraphState`` and
  the gold ``SeedCase``. They encode the per-dimension scoring and never touch a model.
* ``run_baseline`` executes the real graph live over the E2E cases, scores each, and
  writes a reproducible baseline artifact. It needs credentials; the pure layer does not.

Dimensions are reported separately. There is deliberately NO composite "agent score".
Fault-injection cases (UNIT tier: ARC-19/20) are excluded from model metrics - they are
controlled contract/validator tests, not model-performance examples.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .contracts import GraphState, OutputContractError, validate_final_output
from .dataset import DEFAULT_DATASET, RetrievalBehavior, SeedCase, Tier, load_seed_cases
from .enums import Decision, EscalationReason, Route, SourceType
from .model import DEFAULT_MODEL_ID
from .retrieval import DEFAULT_K, load_corpus

DEFAULT_ARTIFACT = Path(__file__).resolve().parents[2] / "baselines" / "baseline-v1.json"

_CANONICAL_DISTRACTORS: Optional[set[str]] = None


def canonical_distractors() -> set[str]:
    """Doc ids flagged as distractors in the corpus (retrieving any is a precision error,
    regardless of whether a given case named it as its targeted trap)."""
    global _CANONICAL_DISTRACTORS
    if _CANONICAL_DISTRACTORS is None:
        _CANONICAL_DISTRACTORS = {d.doc_id for d in load_corpus() if d.is_distractor}
    return _CANONICAL_DISTRACTORS


# --- pure scoring ---------------------------------------------------------
def retrieved_ids(state: GraphState) -> list[str]:
    """Retrieved-manual source ids, in retrieval order (provenance lives in evidence)."""
    return [
        e.source_id
        for e in (state.evidence or [])
        if e.source_type is SourceType.RETRIEVED_MANUAL
    ]


def observed_retrieval_behavior(state: GraphState) -> str:
    """Infer what the Investigator actually did, from state alone."""
    if state.evidence is None:
        return "not_run"  # Investigator never executed (safety/scope short-circuit)
    return "retrieved" if retrieved_ids(state) else "no_retrieval"


def mechanism_state(state: GraphState) -> dict:
    """Serialize the already-computed terminal graph state for experiment auditability.
    Observability only: no recomputation, no reinterpretation, no scoring impact. Optional
    values stay null (never coerced)."""
    return {
        "evidence_sufficient": state.evidence_sufficient,
        "evidence_conflict": state.evidence_conflict,
        "gap_user_resolvable": state.gap_user_resolvable,
        "tool_failed": state.tool_failed,
        "triage_needs_retrieval": state.triage_needs_retrieval,
        "triage_needs_live_telemetry": state.triage_needs_live_telemetry,
        "confidence": state.confidence.value if state.confidence else None,
        "has_proposed_answer": state.proposed_answer is not None,
        "answer_grounded": state.answer_grounded,
        "decision": state.decision.value if state.decision else None,
        "escalation_reason": state.escalation_reason.value if state.escalation_reason else None,
        "abstain_reason": state.abstain_reason.value if state.abstain_reason else None,
    }


def _reason_fields(case: SeedCase, state: GraphState):
    """Return (expected_reason_value, observed_reason_value) or (None, None) if n/a."""
    if case.expected_decision is Decision.ESCALATE:
        exp = case.expected_escalation_reason.value if case.expected_escalation_reason else None
        obs = state.escalation_reason.value if state.escalation_reason else None
        return exp, obs
    if case.expected_decision is Decision.ABSTAIN:
        exp = case.expected_abstain_reason.value if case.expected_abstain_reason else None
        obs = state.abstain_reason.value if state.abstain_reason else None
        return exp, obs
    return None, None


@dataclass
class CaseResult:
    id: str
    tier: str
    expected: dict
    observed: dict
    scores: dict


def score_case(
    case: SeedCase,
    state: GraphState,
    *,
    contract_valid: bool,
    latency_s: float,
    distractors: Optional[set[str]] = None,
) -> CaseResult:
    """Score one executed case against its gold label across the measured dimensions."""
    distractors = canonical_distractors() if distractors is None else distractors
    r_ids = retrieved_ids(state)
    behavior = observed_retrieval_behavior(state)
    exp_reason, obs_reason = _reason_fields(case, state)

    route_correct = state.route == case.expected_route
    decision_correct = state.decision == case.expected_decision

    # reason correctness only where the expected decision carries a reason
    reason_correct: Optional[bool]
    reason_correct = (exp_reason == obs_reason) if exp_reason is not None else None

    # retrieval-behavior correctness (all four frozen categories are scored)
    eb = case.expected_retrieval_behavior
    if eb is RetrievalBehavior.REQUIRED:
        behavior_correct: Optional[bool] = behavior == "retrieved"
    elif eb is RetrievalBehavior.SKIP:
        behavior_correct = behavior == "no_retrieval"
    elif eb is RetrievalBehavior.NOT_APPLICABLE:
        behavior_correct = behavior == "not_run"
    else:  # allowed: Investigator must run; fetch or skip both pass, not_run fails
        behavior_correct = behavior in ("retrieved", "no_retrieval")

    # retrieval-source correctness (only meaningful for 'required')
    if eb is RetrievalBehavior.REQUIRED:
        source_correct: Optional[bool] = set(case.expected_retrieval_ids).issubset(set(r_ids))
    else:
        source_correct = None

    # distractor precision: retrieving ANY canonical distractor is an error
    pulled_distractors = sorted(set(r_ids) & distractors)
    distractor_pulled = bool(pulled_distractors)

    # grounding correctness where gold behavior exists (ANSWER expects grounded True)
    grounding_correct: Optional[bool]
    grounding_correct = (state.answer_grounded is True) if case.expected_decision is Decision.ANSWER else None

    # structured-output validity: contract-valid AND not a fail-closed internal_error.
    # In the E2E set internal_error is never the gold outcome, so a terminal internal_error
    # signals a structured-output / fail-closed fault (malformed diagnosis or grounding).
    fell_closed = state.decision is Decision.ESCALATE and state.escalation_reason is EscalationReason.INTERNAL_ERROR
    structured_output_valid = contract_valid and not fell_closed

    return CaseResult(
        id=case.id,
        tier=case.tier.value,
        expected={
            "route": case.expected_route.value,
            "decision": case.expected_decision.value,
            "reason": exp_reason,
            "retrieval_behavior": eb.value,
            "retrieval_ids": case.expected_retrieval_ids,
            "distractor_ids": case.distractor_ids,
        },
        observed={
            "route": state.route.value if state.route else None,
            "decision": state.decision.value if state.decision else None,
            "reason": obs_reason,
            "retrieval_behavior": behavior,
            "retrieved_ids": r_ids,
            "pulled_distractors": pulled_distractors,
            "answer_grounded": state.answer_grounded,
            "output_contract_valid": contract_valid,
            "latency_s": round(latency_s, 4),
            "trace_id": state.trace_id,
            "mechanism_state": mechanism_state(state),
        },
        scores={
            "route_correct": route_correct,
            "decision_correct": decision_correct,
            "reason_correct": reason_correct,
            "retrieval_behavior_correct": behavior_correct,
            "retrieval_source_correct": source_correct,
            "distractor_pulled": distractor_pulled,
            "grounding_correct": grounding_correct,
            "output_contract_valid": contract_valid,
            "structured_output_valid": structured_output_valid,
        },
    )


def _rate(results: list[CaseResult], key: str) -> dict:
    """Pass-rate over cases where the dimension is applicable (non-None)."""
    applicable = [(r.id, r.scores[key]) for r in results if r.scores[key] is not None]
    passed = [cid for cid, v in applicable if v is True]
    failed = [cid for cid, v in applicable if v is False]
    return {
        "passed": len(passed),
        "total": len(applicable),
        "rate": round(len(passed) / len(applicable), 4) if applicable else None,
        "failed_cases": failed,
    }


def _median(xs: list[float]) -> Optional[float]:
    if not xs:
        return None
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else round((s[mid - 1] + s[mid]) / 2, 4)


def aggregate(results: list[CaseResult]) -> dict:
    """Per-dimension aggregates. No composite score, by design."""
    latencies = [r.observed.get("latency_s", 0.0) for r in results]
    n = len(latencies)
    # distractor resistance is measured over EVERY case: retrieving any canonical
    # distractor is a precision error, not only on cases that named it as their trap.
    pulled = [
        {"id": r.id, "distractors": r.observed.get("pulled_distractors", [])}
        for r in results
        if r.scores.get("distractor_pulled")
    ]
    return {
        "n_cases": len(results),
        "route_correct": _rate(results, "route_correct"),
        "decision_correct": _rate(results, "decision_correct"),
        "reason_correct": _rate(results, "reason_correct"),
        "retrieval_behavior_correct": _rate(results, "retrieval_behavior_correct"),
        "retrieval_source_correct": _rate(results, "retrieval_source_correct"),
        "grounding_correct": _rate(results, "grounding_correct"),
        "output_contract_valid": _rate(results, "output_contract_valid"),
        "structured_output_valid": _rate(results, "structured_output_valid"),
        "distractor_resistance": {
            "clean": len(results) - len(pulled),
            "total": len(results),
            "pulled_distractor": pulled,
        },
        "latency_s": {
            "mean": round(sum(latencies) / n, 4) if n else None,
            "median": _median(latencies),
            "max": max(latencies) if n else None,
        },
    }


# --- live baseline runner -------------------------------------------------
def _git_commit() -> Optional[str]:
    try:
        root = Path(__file__).resolve().parents[2]
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip()
    except Exception:
        return None


def run_baseline(
    *,
    dataset: Path | str | None = None,
    out_path: Path | str | None = None,
    model_id: Optional[str] = None,
) -> dict:
    """Execute the real graph over the E2E cases, score, and write the baseline artifact.

    Requires live credentials. UNIT-tier cases are excluded (covered by deterministic
    tests). Imports the graph lazily so this module stays importable without model deps.
    """
    from .graph import run_incident

    cases = [c for c in load_seed_cases(dataset) if c.tier is Tier.E2E]
    model_id = model_id or os.environ.get("MODEL_ID", DEFAULT_MODEL_ID)

    results: list[CaseResult] = []
    for case in cases:
        start = time.perf_counter()
        try:
            state = run_incident(case.id, case.input, validate=False)
        except Exception as exc:  # a crash is a (bad) baseline result, recorded not hidden
            latency = time.perf_counter() - start
            exp_reason = (
                case.expected_escalation_reason.value if case.expected_escalation_reason
                else case.expected_abstain_reason.value if case.expected_abstain_reason
                else None
            )
            results.append(
                CaseResult(
                    id=case.id,
                    tier=case.tier.value,
                    expected={
                        "route": case.expected_route.value,
                        "decision": case.expected_decision.value,
                        "reason": exp_reason,
                        "retrieval_behavior": case.expected_retrieval_behavior.value,
                        "retrieval_ids": case.expected_retrieval_ids,
                        "distractor_ids": case.distractor_ids,
                    },
                    observed={
                        "error": repr(exc),
                        "retrieved_ids": [],
                        "pulled_distractors": [],
                        "output_contract_valid": False,
                        "latency_s": round(latency, 4),
                        "mechanism_state": None,
                    },
                    scores={
                        "route_correct": False,
                        "decision_correct": False,
                        "reason_correct": None,
                        "retrieval_behavior_correct": None,
                        "retrieval_source_correct": None,
                        "distractor_pulled": False,
                        "grounding_correct": None,
                        "output_contract_valid": False,
                        "structured_output_valid": False,
                    },
                )
            )
            continue
        latency = time.perf_counter() - start
        try:
            validate_final_output(state)
            contract_valid = True
        except OutputContractError:
            contract_valid = False
        results.append(score_case(case, state, contract_valid=contract_valid, latency_s=latency))

    dataset_path = Path(dataset) if dataset else DEFAULT_DATASET
    artifact = {
        "baseline": "v1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_commit(),
        "model_id": model_id,
        "retrieval_k": DEFAULT_K,
        "dataset": {
            "path": dataset_path.name,
            "tier": "E2E",
            "n_cases": len(cases),
            "case_ids": [c.id for c in cases],
        },
        "aggregate": aggregate(results),
        "cases": [asdict(r) for r in results],
    }

    out = Path(out_path) if out_path else DEFAULT_ARTIFACT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    return artifact


def _print_summary(artifact: dict) -> None:
    agg = artifact["aggregate"]
    print(f"baseline   : {artifact['baseline']}  model={artifact['model_id']}  k={artifact['retrieval_k']}")
    print(f"commit     : {artifact['git_commit']}")
    print(f"cases      : {agg['n_cases']} (E2E)")
    for dim in (
        "route_correct",
        "decision_correct",
        "reason_correct",
        "retrieval_behavior_correct",
        "retrieval_source_correct",
        "grounding_correct",
        "output_contract_valid",
        "structured_output_valid",
    ):
        d = agg[dim]
        print(f"  {dim:28s}: {d['passed']}/{d['total']} (rate={d['rate']})  fail={d['failed_cases']}")
    dr = agg["distractor_resistance"]
    print(f"  {'distractor_resistance':28s}: {dr['clean']}/{dr['total']} clean  pulled={dr['pulled_distractor']}")
    lat = agg["latency_s"]
    print(f"  {'latency_s':28s}: mean={lat['mean']} median={lat['median']} max={lat['max']}")


def _main(argv: list[str]) -> int:
    # Diagnostic logging to stderr so the per-case TRIAGE / DIAGNOSIS / GROUNDING lines
    # and any swallowed-exception traces are visible during a debug run.
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s | %(message)s",
        stream=sys.stderr,
    )
    try:
        from dotenv import load_dotenv

        load_dotenv(override=False)
    except ImportError:
        pass
    out_path = argv[1] if len(argv) > 1 else None
    artifact = run_baseline(out_path=out_path)
    _print_summary(artifact)
    print(f"\nwrote artifact: {out_path or DEFAULT_ARTIFACT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
