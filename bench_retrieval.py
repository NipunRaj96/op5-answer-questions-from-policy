"""Retrieval bake-off on the dev set. No API calls.

    python bench_retrieval.py            lexical, dense and hybrid
    python bench_retrieval.py rerank     adds cross-encoder rerankers on the best hybrid
    python bench_retrieval.py extra      stemming, BM25 parameters, document-local statistics

Columns: r@k = gold passage within the top k passages the requester may see (119 answerable
questions); blk = role-blocked questions caught by "best match is restricted" (of 21);
bad = answerable questions that rule would wrongly block (of 119); ms = search time per question.
"""
import json
import os
import sys
import time
from pathlib import Path

import bm25s
import numpy as np
from fastembed import TextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder
from sklearn.feature_extraction.text import TfidfVectorizer

REF = Path(os.environ.get("REF_DIR", "../hiring-problems/references/OP-05"))
RANK = {"public": 0, "ops": 1, "legal": 2}
docs = {d["doc_id"]: d for d in map(json.loads, (REF / "corpus/manifest.jsonl").read_text().splitlines())}
passages = [json.loads(line) for line in (REF / "corpus/passages.jsonl").read_text().splitlines()]
questions = [json.loads(line) for line in (REF / "questions_dev.jsonl").read_text().splitlines()]
level = np.array([RANK[docs[p["doc_id"]]["role"]] for p in passages])
ids = [p["passage_id"] for p in passages]
plain = [p["text"] for p in passages]
titled = [docs[p["doc_id"]]["title"] + "\n" + p["text"] for p in passages]
qtext = [q["question"] for q in questions]
rows = []


def tfidf(texts):
    v = TfidfVectorizer(sublinear_tf=True, ngram_range=(1, 2), stop_words="english")
    m = v.fit_transform(texts)
    return (v.transform(qtext) @ m.T).toarray()


def bm25(texts):
    r = bm25s.BM25()
    r.index(bm25s.tokenize(texts, stopwords="en", show_progress=False), show_progress=False)
    queries = bm25s.tokenize(qtext, stopwords="en", return_ids=False, show_progress=False)
    return np.array([r.get_scores(tokens) for tokens in queries])


def dense(model, texts):
    m = TextEmbedding(model)
    p = np.array(list(m.passage_embed(texts)))
    q = np.array(list(m.query_embed(qtext)))
    return (q / np.linalg.norm(q, axis=1, keepdims=True)) @ (p / np.linalg.norm(p, axis=1, keepdims=True)).T


def rrf(*score_sets, k=60):
    """Reciprocal rank fusion: sum of 1 / (k + rank) over the input rankings."""
    return sum(1.0 / (k + np.argsort(np.argsort(-s, axis=1), axis=1) + 1) for s in score_sets)


def rerank(model, base, texts, n=20):
    ce = TextCrossEncoder(model)
    out = -np.argsort(np.argsort(-base, axis=1), axis=1).astype(float)  # keep base order below the top n
    for qi, question in enumerate(qtext):
        top = np.argsort(-base[qi])[:n]
        out[qi, top] = 1e6 + np.array(list(ce.rerank(question, [texts[i] for i in top])))
    return out


def report(name, make):
    start = time.monotonic()
    scores = make()
    ms = (time.monotonic() - start) * 1000 / len(questions)
    hit, rr, caught, wrongly, n = {1: 0, 3: 0, 6: 0}, 0.0, 0, 0, 0
    for q, s in zip(questions, scores):
        order = np.argsort(-s, kind="stable")
        blocked = level[order[0]] > RANK[q["role"]]
        caught += blocked and q["expected_status"] == "not_permitted"
        if q["expected_status"] != "answered":
            continue
        n += 1
        wrongly += blocked
        allowed = [ids[i] for i in order if level[i] <= RANK[q["role"]]]
        position = allowed.index(q["gold_citations"][0]["section"])
        for k in hit:
            hit[k] += position < k
        rr += 1 / (position + 1) if position < 10 else 0
    row = {"name": name, **{f"r@{k}": round(v / n, 4) for k, v in hit.items()}, "mrr@10": round(rr / n, 4),
           "blk": int(caught), "bad": int(wrongly), "ms": round(ms, 1)}
    rows.append(row)
    print(f"{name:58} r@1 {row['r@1']:.3f}  r@3 {row['r@3']:.3f}  r@6 {row['r@6']:.3f}  mrr {row['mrr@10']:.3f}"
          f"  blk {row['blk']:2}/21  bad {row['bad']}  {row['ms']:7.1f} ms", flush=True)
    return scores


def bm25_with(stemmer=None, k1=1.5, b=0.75, method="lucene"):
    r = bm25s.BM25(k1=k1, b=b, method=method)
    r.index(bm25s.tokenize(plain, stopwords="en", stemmer=stemmer, show_progress=False), show_progress=False)
    queries = bm25s.tokenize(qtext, stopwords="en", stemmer=stemmer, return_ids=False, show_progress=False)
    return np.array([r.get_scores(tokens) for tokens in queries])


def doc_local():
    """BM25 inside each document, using that document's own term statistics."""
    out = np.zeros((len(questions), len(passages)))
    queries = bm25s.tokenize(qtext, stopwords="en", return_ids=False, show_progress=False)
    for doc in docs:
        idx = [i for i, p in enumerate(passages) if p["doc_id"] == doc]
        r = bm25s.BM25()
        r.index(bm25s.tokenize([plain[i] for i in idx], stopwords="en", show_progress=False), show_progress=False)
        for qi, tokens in enumerate(queries):
            try:
                out[qi, idx] = r.get_scores(tokens)
            except Exception:  # noqa: BLE001  no query term occurs in this document
                pass
    return out


def extra():
    """Attempts to break the r@6 plateau (EXPERIMENT_LOG, "Search for remaining gains")."""
    import Stemmer
    stem = Stemmer.Stemmer("english")
    base = report("bm25 default (k1 1.5, b 0.75, no stemming)", bm25_with)
    report("bm25 + stemming", lambda: bm25_with(stem))
    for k1 in (0.9, 1.2, 2.0):
        for b in (0.4, 0.6, 0.75, 0.9):
            report(f"bm25 + stemming k1 {k1} b {b}", lambda: bm25_with(stem, k1, b))
    for method in ("robertson", "atire", "bm25l", "bm25+"):
        report(f"bm25 + stemming, variant {method}", lambda: bm25_with(stem, method=method))
    local = doc_local()
    report("doc-local only", lambda: local)
    for weight in (0.25, 0.5, 1, 2, 4):
        report(f"global + {weight} x doc-local", lambda: base + weight * local)
    for k in (5, 10, 30, 60):
        report(f"rrf(global, doc-local) k={k}", lambda: rrf(base, local, k=k))
    Path("results/raw/retrieval_extra.json").write_text(json.dumps(rows, indent=2) + "\n")


if __name__ == "__main__":
    if "extra" in sys.argv:
        extra()
        sys.exit()
    report("tfidf plain (Phase 1 baseline)", lambda: tfidf(plain))
    report("tfidf +title", lambda: tfidf(titled))
    report("bm25 plain", lambda: bm25(plain))
    lexical = report("bm25 +title", lambda: bm25(titled))
    best = {}
    for model in ("BAAI/bge-small-en-v1.5", "snowflake/snowflake-arctic-embed-s",
                  "sentence-transformers/all-MiniLM-L6-v2", "BAAI/bge-base-en-v1.5"):
        report(f"dense {model} plain", lambda: dense(model, plain))
        best[model] = report(f"dense {model} +title", lambda: dense(model, titled))
        report(f"hybrid rrf(bm25, {model}) +title", lambda: rrf(lexical, best[model]))
    if "rerank" in sys.argv:
        base = rrf(lexical, best["BAAI/bge-small-en-v1.5"])
        for model in ("Xenova/ms-marco-MiniLM-L-6-v2", "Xenova/ms-marco-MiniLM-L-12-v2",
                      "jinaai/jina-reranker-v1-turbo-en", "BAAI/bge-reranker-base"):
            for texts, label in ((plain, "plain"), (titled, "+title")):
                report(f"rerank top20 {model} {label}", lambda: rerank(model, base, texts))
    Path("results/raw/retrieval_bench.json").write_text(json.dumps(rows, indent=2) + "\n")
