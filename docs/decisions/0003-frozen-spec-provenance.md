# 0003 - Where the frozen design came from

## Context
The Phase 0 code implements a specification that was frozen *before* any implementation, in an
eval-first design phase. That phase deliberately let evaluation-case design and independent
adversarial review change the architecture on paper, where changes are cheap.

## What the review cycle changed (design history)
- A provisional third route (`DIAGNOSE_DIRECT`) was **removed** after it failed an explicit
  "produce >=3 natural cases" test; every genuine diagnosis benefits from the manual.
- Progressive/stage-aware state was adopted: later-stage fields are absent until their node
  runs, and the policy never truthiness-coerces a `None`.
- Retrieval behavior was separated from routing (a four-value `expected_retrieval_behavior`).
- Provenance was modelled with four `source_type`s; **evidence presence is not grounding**.
- The router produces `abstain_reason` so the ABSTAIN reasons are reachable and fail closed.
- A bounded **Grounding Validator** was added to separate grounding from evidence presence.
- The safety detector gained negation/isolation handling.
- The final policy gained a rule-7 guard so `high confidence + missing answer` fails closed to
  `internal_error` rather than colliding with `grounding_failure`.

## Consequence
The deterministic policy (`policy.evaluate_policy`) and the reason enums are the settled output
of that process. This repo treats them as frozen: change them only if implementation exposes a
concrete defect, and re-run the independent review before doing so.
