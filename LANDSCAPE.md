# Landscape: what exists, what I measured, what I kept

Setting: 391 passages (median 393 characters), three roles, 1,005 input tokens per question, and
an evaluation box whose only egress is the model gateway. `r@6` = gold passage among the six
sent to the model, on 119 answerable dev questions. Raw numbers: `results/raw/retrieval_bench.json`;
dates and method: `EXPERIMENT_LOG.md`.

## Kept

| Component | Evidence |
|---|---|
| BM25 (`bm25s`; Robertson and Zaragoza) | r@6 0.941, 0.2 ms per query, no model weights to download |
| In-memory index rebuilt at start, no vector database | builds in 0.03 s; nothing survives a restart, so nothing can go stale |
| JSON mode plus validation in code | schema validity 1.00 on every run |
| Quote check and 12-token overlap guard, both the grader's own logic | verbatim 1.00; 0 role violations detected |

## Measured and dropped

| Component | Evidence | Why dropped |
|---|---|---|
| TF-IDF with bigrams (the reference baseline's retriever) | r@6 0.891 | 5 points below BM25 |
| Dense retrieval, four models via `fastembed` (bge-small, bge-base, arctic-embed-s, MiniLM) | r@6 0.78–0.91, 130–1,150 ms | questions reuse the regulation's own words; lexical match wins |
| Hybrid BM25 + dense, reciprocal rank fusion (Cormack et al., 2009) | best 0.950 | one question better; needs vendored weights and 200 ms |
| Cross-encoder rerankers on the top 20 (two MS MARCO MiniLM, Jina turbo, bge-reranker-base) | r@6 0.87–0.93, 0.7–7 s on CPU | equal or worse; three of four put a restricted passage on top for answerable questions |
| Stemming, 20 BM25 parameter settings, document titles in passages | r@6 0.92–0.94 | a plateau |
| Ranking inside the best document with its own term statistics | r@6 0.73–0.93 | worse; my hypothesis about the remaining misses was wrong |
| Showing `as_of` to the model | caused 4 of 15 wrong answers | the model un-applied amendments; dates moved to retrieval |
| A day-counting rule in the prompt | fixed 2, broke 2 | gold answers are inconsistent (`DECISIONS.md` 2) |

## Considered, not measured

An unmeasured rejection is an opinion, so these are labelled as such.

- **Vector databases** (pgvector, Qdrant, FAISS): brute force over 391 passages takes 0.2 ms.
  Worth it above roughly 100k passages or when updates must not need a restart.
- **Frameworks** (LangChain, LlamaIndex, Haystack): the request path is one search and one model
  call. Worth it for multi-step retrieval.
- **Index-time enrichment** (doc2query, contextual chunk headers): the likeliest remaining
  retrieval gain, because the misses share no distinguishing word with the question. Needs about
  390 model calls at every start, more than my provider tier allows in a day.
- **A second retrieval pass after a refusal**: one or two dev questions, at the price of a
  second chance to fabricate on the bar that allows no miss.
- **Prompt-injection classifiers** (for example Llama Prompt Guard): the role comes from the
  request field and restricted text never enters a prompt, so an injected instruction has
  nothing to unlock. Five injection framings of 146 questions changed no outcome toward disclosure.
- **Managed retrieval products**: no per-passage role filter or passage-id citations.

## Models (all on Groq)

| Role | Model | Note |
|---|---|---|
| Generator | `qwen/qwen3.8-27b`, `reasoning_effort: low` | budget class by size; USD 0.80 / 4.00 per million tokens (https://console.groq.com/docs/models, 2026-11-10); p95 1.78 s per call |
| Development judge | `openai/gpt-oss-20b` | stand-in for the official judge |
| Second judge | `openai/gpt-oss-120b` | grades only; used to measure judge noise |
| Not tested | `gpt-5-mini-2025-08-07`, `gpt-4.1-mini-2025-04-14` | no claim made; GPT-5 mini is only a fallback if the gateway lacks Qwen |

## Data

IndiaFinBench (https://huggingface.co/datasets/Rajveer-code/IndiaFinBench, CC BY 4.0). Three
findings shaped the work: dev gold answers count days inconsistently; 3 of 7 retrieval "misses"
are label artefacts; every dev out-of-corpus question is asked by `legal`, so dev cannot show
out-of-corpus questions being refused as "not permitted". I wrote 36 questions to cover that
(`dev_extra/`).
