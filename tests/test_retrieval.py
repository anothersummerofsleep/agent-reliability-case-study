"""Corpus loading + BM25 retriever: ranking, output format, distractor behavior."""

from __future__ import annotations

import pytest

from agent_reliability.retrieval import (
    DEFAULT_K,
    BM25Retriever,
    CorpusDoc,
    RetrievedDoc,
    default_retriever,
    load_corpus,
)

EXPECTED_IDS = {
    "DOC-RTU-A11",
    "DOC-RTU-CYCLE",
    "DOC-SENSOR-A21",
    "DOC-COMMS-A31",
    "DOC-FILT-A41",
    "DOC-AHU-VFD",
    "DOC-COMP-A51",
    "DOC-CHW-EFF",
    "DOC-RTU-COOL",
    "DOC-CHW-LOWCAP",
}
DISTRACTORS = {"DOC-RTU-CYCLE", "DOC-AHU-VFD"}


def test_corpus_loads_all_ten_docs():
    docs = load_corpus()
    assert {d.doc_id for d in docs} == EXPECTED_IDS
    assert len(docs) == 10
    assert all(d.text for d in docs)  # no empty bodies


def test_distractors_flagged():
    docs = {d.doc_id: d for d in load_corpus()}
    assert {d.doc_id for d in docs.values() if d.is_distractor} == DISTRACTORS


def test_retriever_output_format_is_ranked():
    r = default_retriever()
    hits = r.search("high head pressure NW-A11 condenser coil", k=DEFAULT_K)
    assert all(isinstance(h, RetrievedDoc) for h in hits)
    assert [h.rank for h in hits] == list(range(1, len(hits) + 1))
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)


def test_relevant_doc_ranks_first():
    r = default_retriever()
    hits = r.search("NW-A11 high head pressure fouled condenser coil", k=DEFAULT_K)
    assert hits[0].doc_id == "DOC-RTU-A11"


def test_distractor_can_be_retrieved_by_weak_lexical_query():
    # ARC-14 trap: 'short-cycling' lexically matches the DOC-RTU-CYCLE distractor.
    r = default_retriever()
    ids = {h.doc_id for h in r.search("RTU short-cycling NW-A11 discharge condenser", k=DEFAULT_K)}
    assert "DOC-RTU-CYCLE" in ids  # the trap is genuinely capable of fooling the baseline


def test_non_matching_query_retrieves_nothing():
    r = default_retriever()
    assert r.search("zzzzz qqqqq", k=DEFAULT_K) == []


def test_deterministic_ranking():
    r = default_retriever()
    a = r.search("sensor fault NW-A21 recalibrate", k=DEFAULT_K)
    b = r.search("sensor fault NW-A21 recalibrate", k=DEFAULT_K)
    assert [(h.doc_id, round(h.score, 6)) for h in a] == [(h.doc_id, round(h.score, 6)) for h in b]


def test_empty_corpus_rejected():
    with pytest.raises(ValueError):
        BM25Retriever([])


def test_manual_corpus_doc_shape():
    doc = CorpusDoc(doc_id="DOC-X", text="hello", is_distractor=False)
    assert doc.doc_id == "DOC-X" and not doc.is_distractor
