# 0001 - Phase 0 scope: prove the plumbing, not the system

## Context
Phase -1 froze the full design (state contract, deterministic policy, reason enums, the
22-case seed set, retrieval/provenance model, safety detector). Phase 0's only job is to
prove that contract can be represented cleanly in code and that the pieces connect.

## Decision
- Implement the **frozen state contract** as Pydantic models, keeping *progressive graph
  state* (downstream fields optional until their node runs) separate from the *output
  contract* (per-decision invariants checked at the end).
- Implement the **single authoritative policy** (`policy.evaluate_policy`) exactly as frozen,
  applied at three checkpoints in the graph. One copy of the rules; the checkpoints are call
  sites, not duplicates.
- Build a **two-route** LangGraph skeleton (`intake -> router -> evidence -> diagnosis ->
  grounding`) with real graph edges but **stub** Investigator/router/grounding logic. Only the
  Diagnosis node drives a real (or fake) model, to prove one traceable LLM call.
- **Materialize all 22 frozen cases** as JSONL and validate them (schema + coverage). No
  scoring against the agent yet.
- Favor **deterministic tests**: the policy is exercised far more deeply than the graph.

## Stubs (explicitly not the real system)
The router is a keyword heuristic, the Evidence Investigator is a passthrough that performs no
retrieval, and the Grounding Validator thinly treats any proposed answer as grounded. Real
retrieval, diagnosis, and support-checking semantics arrive in later phases.

## Consequences
- The full deterministic suite runs offline with a fake model (no API keys).
- The one thing Phase 0 cannot self-verify without credentials is a **live** model call +
  LangSmith trace; that is a manual check once a key is present (see README).
