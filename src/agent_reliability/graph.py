"""Phase 0 LangGraph skeleton.

Straight-through plumbing that applies the single deterministic policy
(``policy.evaluate_policy``) at three checkpoints via checkpoint nodes + conditional
edges:

    intake -> router -> [A] -> evidence -> [B] -> diagnosis -> grounding -> [C] -> finalize

[A] and [B] are non-terminal (a no-decision result is CONTINUE); [C] is terminal (a
no-decision fallthrough fails closed to internal_error inside the policy). There is
exactly one policy function; the checkpoints are three call sites of it.
"""

from __future__ import annotations

import os
import sys

from langgraph.graph import END, START, StateGraph

from .contracts import GraphState, validate_final_output
from .model import make_chat_model
from .nodes import (
    DiagnoseFn,
    EvidenceFn,
    GroundFn,
    RouterFn,
    default_evidence,
    default_ground,
    default_router,
    intake,
    make_diagnosis_node,
    make_evidence_node,
    make_grounding_node,
    make_initial_state,
    make_llm_diagnose,
    make_router_node,
)
from .policy import evaluate_policy


def _make_checkpoint(*, terminal: bool):
    def _node(state: GraphState) -> dict:
        result = evaluate_policy(state, terminal=terminal)
        if result is None:
            return {}  # CONTINUE
        update: dict = {
            "decision": result.decision,
            "escalation_reason": result.escalation_reason,
        }
        if result.abstain_reason is not None:
            update["abstain_reason"] = result.abstain_reason
        return update

    return _node


def _branch(next_node: str):
    def _route(state: GraphState) -> str:
        return "finalize" if state.decision is not None else next_node

    return _route


def _finalize(state: GraphState) -> dict:
    return {}


def build_graph(
    *,
    diagnose_fn: DiagnoseFn | None = None,
    ground_fn: GroundFn | None = None,
    router_fn: RouterFn | None = None,
    evidence_fn: EvidenceFn | None = None,
):
    """Compile the Phase 0 graph. Inject fakes for offline tests; leave ``diagnose_fn``
    as ``None`` for a lazily-constructed real model on live runs."""
    router_fn = router_fn or default_router
    evidence_fn = evidence_fn or default_evidence
    ground_fn = ground_fn or default_ground

    if diagnose_fn is None:

        def diagnose_fn(state: GraphState):  # lazy: only builds the model when invoked
            return make_llm_diagnose(make_chat_model())(state)

    g = StateGraph(GraphState)
    g.add_node("intake", intake)
    g.add_node("router", make_router_node(router_fn))
    g.add_node("checkpoint_a", _make_checkpoint(terminal=False))
    g.add_node("evidence", make_evidence_node(evidence_fn))
    g.add_node("checkpoint_b", _make_checkpoint(terminal=False))
    g.add_node("diagnosis", make_diagnosis_node(diagnose_fn))
    g.add_node("grounding", make_grounding_node(ground_fn))
    g.add_node("checkpoint_c", _make_checkpoint(terminal=True))
    g.add_node("finalize", _finalize)

    g.add_edge(START, "intake")
    g.add_edge("intake", "router")
    g.add_edge("router", "checkpoint_a")
    g.add_conditional_edges(
        "checkpoint_a", _branch("evidence"), {"finalize": "finalize", "evidence": "evidence"}
    )
    g.add_edge("evidence", "checkpoint_b")
    g.add_conditional_edges(
        "checkpoint_b", _branch("diagnosis"), {"finalize": "finalize", "diagnosis": "diagnosis"}
    )
    g.add_edge("diagnosis", "grounding")
    g.add_edge("grounding", "checkpoint_c")
    g.add_edge("checkpoint_c", "finalize")
    g.add_edge("finalize", END)
    return g.compile()


def _coerce_state(result) -> GraphState:
    if isinstance(result, GraphState):
        return result
    if isinstance(result, dict):
        return GraphState.model_validate(result)
    return GraphState.model_validate(dict(result))


def run_incident(
    incident_id: str,
    incident_raw: str,
    *,
    diagnose_fn: DiagnoseFn | None = None,
    ground_fn: GroundFn | None = None,
    router_fn: RouterFn | None = None,
    evidence_fn: EvidenceFn | None = None,
    validate: bool = True,
) -> GraphState:
    """Run one incident end-to-end and return the terminal state."""
    graph = build_graph(
        diagnose_fn=diagnose_fn,
        ground_fn=ground_fn,
        router_fn=router_fn,
        evidence_fn=evidence_fn,
    )
    result = graph.invoke(make_initial_state(incident_id, incident_raw))
    state = _coerce_state(result)
    if validate:
        validate_final_output(state)
    return state


def _main(argv: list[str]) -> int:
    incident = argv[1] if len(argv) > 1 else "RTU-40 unit 3 tripped NW-A11, discharge 415 psi, condenser coil fouled"
    tracing = os.environ.get("LANGSMITH_TRACING", "").lower() in ("1", "true", "yes")
    state = run_incident("cli-001", incident)
    print(f"incident   : {incident}")
    print(f"trace_id   : {state.trace_id}")
    print(f"route      : {state.route.value if state.route else None}")
    print(f"decision   : {state.decision.value if state.decision else None}")
    if state.escalation_reason:
        print(f"escalation : {state.escalation_reason.value}")
    if state.abstain_reason and state.decision and state.decision.value == 'ABSTAIN':
        print(f"abstain    : {state.abstain_reason.value}")
    if state.proposed_answer:
        print(f"answer     : {state.proposed_answer}")
    print(f"langsmith  : {'tracing ON (see your LANGSMITH_PROJECT)' if tracing else 'tracing OFF (set LANGSMITH_TRACING=true)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
