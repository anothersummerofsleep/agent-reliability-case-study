# 0004 - Phase 1: real components, lexical retrieval, and an honest first baseline

## Context
Phase 0 proved the plumbing with behavioral stubs. Phase 1 replaces the four stubs with the
smallest real implementations and produces the first baseline against the frozen 22-case set.
The frozen Phase -1 contract, policy, enums, and dataset are authoritative and unchanged.

## Decision
- **Retriever: a hand-rolled Okapi BM25** over the 10-doc Northwind corpus, parsed from the single
  frozen source `datasets/corpus/manuals.md` (no duplicated content). No database, embeddings, or
  external service. A weak lexical baseline is deliberate: the frozen ARC-14 (`short-cycling`) and
  ARC-15 (`raise the VFD`) distractors must stay genuinely capable of fooling it. `k = 2`, frozen for
  the baseline. Zero new dependencies.
- **Evidence Investigator: a bounded loop**, not a ReAct agent.
  `normalize -> triage (LLM) -> optional bounded retrieval + assess (LLM) -> stop`. At most two
  retrieval attempts and at most two assessment calls. A telemetry request fails cleanly because the
  project has **no telemetry backend** (true system state, not engineered-to-fail), which the policy
  turns into `ESCALATE(tool_failure)`. Rule-3 is also covered deterministically by a unit test.
- **Diagnosis Specialist: one structured call** returning `hypotheses / confidence / proposed_answer /
  gap_user_resolvable`. The prompt is closed-domain: reason only from supplied evidence, emit a null
  answer rather than invent one, and no gold labels appear in the prompt. Diagnosis overwrites
  `gap_user_resolvable` only when it identifies its own (preserving the Investigator's for rules 4/5).
- **Grounding Validator: one bounded structured call** returning `answer_grounded`. It judges support
  only - no rewrite, diagnose, retrieval, or tools. **Unsupported -> False -> `grounding_failure`;
  validator exception/parse-failure -> left `None` -> terminal fallthrough -> `internal_error`.**
- **Router unchanged.** Replacing the deterministic heuristic router is not in Phase 1 scope; its
  errors are recorded honestly in the baseline rather than hidden.
- **Model** stays behind `init_chat_model`; the Phase-0-verified `google_genai:gemini-2.0-flash` is the
  baseline model, recorded in the artifact. No model-comparison experiments.
- **Evaluation** reports per dimension (route, decision, reason, retrieval-behavior, retrieval-source,
  distractor-resistance, grounding, structured-output validity, latency) with **no composite score**.
  UNIT-tier ARC-19/20 are excluded from model metrics.

## Fail-closed design
A Diagnosis parse failure leaves `confidence` unset; a Grounding failure leaves `answer_grounded`
`None`. Both resolve to `ESCALATE(internal_error)` at the terminal checkpoint, matching the frozen
truth table. This is tested with fake models that raise.

## Baseline integrity
The initial implementation commit is frozen before the baseline run. No prompt/retrieval/threshold
tuning against failing cases precedes baseline capture. A poor baseline is useful evidence and the
starting point for the next phase.

## Consequences
- The full suite (82 tests) runs offline with fake models; no API keys required.
- The live baseline run needs credentials and is a separate command
  (`python -m agent_reliability.evaluate`), mirroring the Phase 0 live check.
- No frozen Phase -1 specification was changed.
