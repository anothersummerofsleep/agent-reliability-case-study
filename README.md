# Agent Reliability Case Study

An **evaluation-first** LangGraph agent for equipment-operations incident support, built as an
engineering case study in agent *reliability*: the interesting part is not the agent, it is the
deterministic policy, the evaluation harness, and the trace-driven improvement loop around it.

> **Status: Phase 0 (plumbing).** The frozen design contract exists; this phase proves it can be
> represented in code, that the deterministic policy is implemented and unit-tested, that state flows
> through a minimal LangGraph, and that one real model call is traceable in LangSmith. The full
> Evidence Investigator, retrieval, Diagnosis reasoning, and Grounding Validator semantics come later.

## What this is, honestly

- **Portfolio-scale**, **evaluation-first**, **production-oriented**. It is a case study, not a
  production system.
- The domain is a **fictional** commercial-HVAC equipment family ("Northwind"). Every incident,
  alarm code, and manual is invented. There is **no** real production traffic, **no** real enterprise
  users, and **no** proprietary or employer data of any kind.
- It does **not** represent 2+ years of production-agent tenure. It is one carefully-engineered,
  deeply-evaluated system.

## Design in one paragraph

An incident enters, is routed (`INVESTIGATE` or `OUT_OF_SCOPE`), and flows through an Evidence
Investigator, a Diagnosis Specialist, and a bounded Grounding Validator. A single **deterministic
policy** (one pure function, evaluated at three checkpoints) decides the final outcome:
`ANSWER | ASK | ESCALATE | ABSTAIN`. The model never decides whether to abstain; a policy does. State
is **progressive** (later-stage fields are absent until their node runs), and the policy uses explicit
guarded comparisons so a missing value never silently satisfies a later rule.

## Quickstart

```bash
uv sync --extra dev        # create the venv and install deps
uv run pytest              # run the deterministic suite (no API keys needed)
```

The test suite (contracts, policy, safety detector, dataset, and a graph smoke test) runs fully
offline using a fake model. To exercise a **real** model call and see a LangSmith trace:

```bash
cp .env.example .env       # then fill in GOOGLE_API_KEY and LANGSMITH_API_KEY
uv run python -m agent_reliability.graph "RTU-40 unit 3 tripped NW-A11, discharge 415 psi, coil fouled"
```

Secrets come from environment variables only; `.env` is gitignored.

## Layout

```
src/agent_reliability/   contracts, enums, deterministic policy, safety detector, graph, nodes, model, dataset
datasets/                the 22 frozen seed evaluation cases + fictional Northwind corpus
tests/                   deterministic contract / policy / safety / dataset / graph-smoke tests
docs/decisions/          architecture decision records
```

## License

Deferred. This repository is private during development; the license decision is part of a dedicated
pre-publication review.
