# Ask the Policy Book (OP-05)

A question-answering service over a small regulatory corpus. It answers only from passages the
requester's role may read and that are in force on the date asked about, cites one passage
verbatim, and otherwise refuses in one of two distinct ways.

```
POST /ask      {id, question, role, as_of}  ->  {id, status, answer, citations: [{doc_id, section, quote}]}
GET  /healthz  200 once the index is built
```

`status` is `answered`, `not_in_corpus` or `not_permitted`. A model outage is HTTP 503, never a
refusal.

## Limitations, first

- **Not shown to clear the bars on held-out.** On dev, every bar is met under one stand-in judge
  (correctness 0.899) and two are missed under a second (correctness 0.874, contradiction 5 of
  8). The published reference attempt loses 4 to 8 points from dev to held-out.
- **Everything was tested on Groq-hosted open-weight models only** (table below). The challenge's
  reference generator (`gpt-5-mini-2025-08-07`) and official judge (`gpt-4.1-mini-2025-04-14`)
  were never called. Scores from the official judge will differ; judge disagreement is measured
  below.
- **Latency at concurrency 12 is not measured against the provider.** My tier allows 8,000
  tokens per minute. Measured instead: provider time per call run one at a time (p95 1.8 s), and
  service overhead at concurrency 12 against a stub (under 0.2 s).
- **Input tokens are 4.4% under the cap** as counted for Qwen (14% under with the GPT tokenizer),
  and the margin depends on the question mix.
- **Linux was tested without a real model.** The image and a clean Python 3.10 container start,
  pass the safety checks and serve 12 concurrent requests, but the model behind them was a stub:
  no Groq quota was left that day. Every scored answer was produced on macOS.
- **Refusal thresholds rest on little data**: 21 blocked and 42 out-of-corpus examples.
- Two dev date questions are wrong by the gold labels and will stay wrong (`DECISIONS.md` 2).

## Tested on

Every recorded run used these models through one provider. Nothing else was called.

| Role | Model id | Provider | Settings | USD per million tokens (in / out) |
|---|---|---|---|---|
| Generator (the only model the service calls) | `qwen/qwen3.8-27b`, 27B open-weight, listed as Preview | Groq, `https://api.groq.com/openai/v1` | `reasoning_effort: low`, JSON mode, `max_completion_tokens` 1500, provider default temperature | 0.80 / 4.00 |
| Development judge for `grader.py` | `openai/gpt-oss-20b` | Groq | grader defaults | 0.075 / 0.30 |
| Second judge, used once to measure judge noise | `openai/gpt-oss-120b` | Groq | grader defaults | not used for cost; grades only, never answers |

Model ids are as returned by Groq's `/models` endpoint on 2026-11-11; I did not record a weight
revision hash. Prices: https://console.groq.com/docs/models, retrieved 2026-11-10. Runs were made
on Groq's free tier (8,000 tokens per minute, 200,000 tokens per day per model), one call at a
time through `scripts/pacing_proxy.py`; that is why provider latency under concurrency is not
reported. The generator model and its options are the code defaults (`GEN_MODEL`, `GEN_EXTRA`);
pointing `LLM_BASE_URL` at another OpenAI-compatible gateway works, but no other model has been
measured, so no claim is made for one.

**If the gateway does not serve `qwen/qwen3.8-27b`** (HTTP 404 for the model), the service
switches to `GEN_FALLBACK_MODEL`, default `gpt-5-mini-2025-08-07`, the challenge's reference
generator, and logs `model_fallback`. The request shape is valid for it (`max_completion_tokens`,
`reasoning_effort: low`, JSON mode, no `temperature`), and the model timeout (20 s) allows for a
slower provider than Groq. That path is checked with a fake model only: **no answer quality is
claimed on GPT-5 mini.** To use it directly: `GEN_MODEL=gpt-5-mini-2025-08-07`.

## Results (dev, 146 questions)

Generator `qwen/qwen3.8-27b` on Groq. Judge columns name the Groq-hosted model that graded.

| Metric | Bar | Phase 1 baseline | Phases 2–4 | **Final** | Final, second judge |
|---|---|---|---|---|---|
| Run | | `dev-20261110-180527` | `dev-20261110-224656` | `dev-20261111-105319` | same answers |
| Judge | | gpt-oss-20b | gpt-oss-20b | gpt-oss-20b | gpt-oss-120b |
| Coverage | ≥ 0.87 | 0.9328 | 0.9748 | **0.9748** | 0.9748 |
| Correctness | ≥ 0.88 | 0.7815 | 0.8739 | **0.8992** | 0.8739 (below) |
| Correctness, contradiction (n=8) | ≥ 0.88 | 0.75 | 0.75 | **1.00** | 0.625 (below) |
| Correctness, temporal (n=19) | ≥ 0.88 | 0.8947 | 0.9474 | **0.9474** | 0.9474 |
| Quote verbatim | ≥ 0.92 | 1.00 | 1.00 | **1.00** | 1.00 |
| Citation support | ≥ 0.82 | 0.8661 | 0.8718 | **0.8889** | 0.8974 |
| Out-of-corpus refusal (6 dev) | ≥ 0.95, 0 fabricated | 1.00, 0 | 1.00, 0 | **1.00, 0** | 1.00, 0 |
| Role violations detected | 0 | 0 | 0 | **0** | 0 |
| Role-blocked refusal (21) | ≥ 0.87 | 0.9048 | 0.9048 | **0.9048** | 0.9048 |
| Input / output tokens per question | ≤ 1,005 / 743 | 759 / 350 | 897 / 326 | **960 / 316** | |
| Model cost per question | | USD 0.0020 | USD 0.0020 | **USD 0.0020** | |

Read the last two columns together. The two judges give the same correctness verdict on 107 of
116 answered questions. On the nine where they differ the answer usually matches the gold
answer and adds an explanation or a proviso (for example gold "No", answer "No, because…").
Correct by both judges: 101 of 119 (0.849). Correct by at least one: 110 of 119 (0.924). The
honest statement is that dev correctness is 0.85 to 0.92 depending on the judge, and the
official judge is neither of these.

Other measurements:

| What | Result | Evidence |
|---|---|---|
| My out-of-corpus set, far from the corpus (20 questions, mixed roles) | 19 refused correctly, 1 refused as "not permitted", 0 fabricated | `ooc_synthetic-20261110-224630` |
| My out-of-corpus set, near misses (16: regulation in corpus, fact absent) | 16 refused correctly, 0 fabricated; 14 of them reached the model and it declined | `ooc_nearmiss-20261111-115656` |
| Version update (v2 of a document effective 2027) | old text before the date, new text after, role wall kept | `test_app.py` |
| Provider time per generator call, one at a time (137 calls) | p50 0.97 s, p95 1.78 s, max 4.6 s | `results/raw/ledger.jsonl` |
| Service overhead at concurrency 12 (stub model answering in 2.0 s), macOS | p95 2.18 s; outage returns 503 in about 1 s | `results/raw/loadtest.json` |
| Same, Docker image on Linux arm64, non-root, read-only filesystem | p95 2.10 s; outage returns 503 in about 1 s | `results/raw/loadtest_docker.json` |
| Docker image with `--network none` | `/healthz` 200, refusals decided before the model still served, model path 503 in 0.9 s, safety checks pass | `EXPERIMENT_LOG.md` |
| Clean `python:3.10-slim`, `scripts/reproduce.sh` from scratch | installs, safety checks pass, search and gate numbers identical to macOS | `EXPERIMENT_LOG.md` |
| Index build | under 1 s, no model calls, no cost | service log `index_seconds` |
| Total model usage for all runs at list price | USD 1.18 (actual charge 0, free tier) | `results/manifest.json` |

Input tokens sit 4.4% under the cap on the dev mix as counted by Groq for Qwen, where 23 of 146
questions are refused before any model call; a call that reaches the model averages 1,140. The
same prompts counted with the GPT tokenizer (`o200k_base`, the reference model's) come to 861
per question and 1,023 per model call, so on the reference model the cap holds with 14% to
spare on this mix and is exceeded only if almost no question is refused before the model.

## Required analysis

### Failure taxonomy, and which change moved which category

119 answerable dev questions, judge `gpt-oss-20b`. Details per run in `EXPERIMENT_LOG.md`.

| Cause | Phase 1 baseline | Phases 2–4 | Final | What moved it |
|---|---|---|---|---|
| Wrong, gold passage was in the prompt | 14 | 12 | 8 | Removing `as_of` from the prompt (the model was "un-applying" amendments); the yes/no rule; forbidding added dates. A day-counting rule fixed 2 and broke 2, and was removed |
| Refused, gold passage not retrieved | 7 | 3 | 3 | TF-IDF → BM25 |
| Wrong, gold passage not retrieved | 4 | 0 | 1 | TF-IDF → BM25 |
| Refused, gold passage was in the prompt | 1 | 0 | 0 | Prompt wording on when to refuse |
| **Total wrong** | **26** | **15** | **12** | |

What did not move anything: embeddings, hybrid search, four rerankers, stemming, a BM25
parameter grid, document-local term statistics (`LANDSCAPE.md`).

### The two slices, separately

**Contradiction** (8 answerable on dev, plus 3 role-blocked). 6 of 8 → 6 of 8 → 8 of 8 under
the first judge; 5 of 8 under the second. These questions ask whether two provisions or two
versions of one provision say the same thing; gold is one word. The real failure was hedging:
"Not entirely…" where gold is "Yes" (`CON_036`), fixed by requiring the answer to start with Yes
or No. The rest is judge behaviour: the three answers the second judge rejects say "No" as gold
does and then explain. How the system resolves a contradiction: among passages in force, the
later effective date prevails and the answer states the current rule; a superseded document is
not in the prompt at all. It picks a winner. It does not present both or escalate, and it does
not know that an internal rule binds ahead of a regulator's unless the dates say so.

**Temporal** (19 answerable). 17 → 18 → 18 under both judges. The baseline failures came from
showing the model the question's `as_of` date: it answered with the pre-amendment rule although
the passage already contained the amended text. Dates now act only in retrieval. The remaining
failure (`TMP_008`) adds a correct proviso that both judges reject.

### What breaks under the update pack

Handled and tested with a fake model (`test_app.py`): a superseding version linked by
`supersedes` replaces the old one from its effective date, not before; the role wall follows the
version in force; a restart serves nothing from removed files. Not tested with a real model.

- **An amendment that is not linked by `supersedes`.** Both documents are in force by metadata.
  The system then depends on the model obeying "the later date prevails". This is the weakest
  point and the first thing I would test with the real pack.
- **A withdrawal notice that is not linked.** The withdrawn rule stays in force by metadata and
  can be cited as current. If it is linked, the old rule disappears and the answer is the
  notice, or "not in the documents" when the notice shares few words with the question.
- **A historical question asked with today's `as_of`.** It gets the current version or a refusal;
  old versions are reachable only through an earlier `as_of`.
- **A version that changes who may read it.** The overlap guard compares answers with every
  document above the requester's role regardless of date, so a requester may be refused text
  they were entitled to on the date asked about. It fails closed, as the grader's check does.
- **Refusal thresholds.** BM25 scores depend on corpus statistics. A handful of new documents
  will not move them; a much larger corpus will, and `evaluate.py --no-llm` must be rerun.

### A document type it has never seen

The system does not parse documents: it reads `passages.jsonl` as plain text. A table arrives
as words without rows and columns, so a figure looked up from a table is likely to be wrong or
refused. Very short passages (an FAQ, a one-line memo) are favoured by BM25 length
normalisation and would upset refusal thresholds tuned on prose of about 400 characters. Text in
another language or from a scan would match almost nothing and be refused as "not in the
documents", which is false. Nothing detects that a document is of a new kind, and nothing warns
anyone. The failure direction is mostly refusal, because the model is told to decline when the
passages do not state the answer, but that is a tendency I measured on regulations, not a
guarantee for other material. Before enabling a new type I would run a sample of questions
through `evaluate.py --no-llm` and read the gate table.

### Leak: what is impossible and what is only unlikely

Impossible by construction: restricted passage text reaching the model (the prompt is built
only from passages at or below the requester's role, asserted in `test_app.py`; the model has no
tool to fetch anything); a citation to a restricted document (citations come only from those
passages); a refusal naming a document (refusal texts are fixed strings).

Blocked by a check, not by construction: an answer that repeats 12 or more consecutive words
also present in a restricted document, when the same text exists at two access levels.

Only unlikely: the model answering from memory. Several restricted documents are public
regulations a model may know. The gate refuses when restricted text is the best match, the
prompt forbids answering from memory, and on 14 near-miss questions that reached the model it
declined every time; but one blocked dev question (`TMP_013`) is answered from permitted text.
No overlap with restricted text was detected there. Semantic leakage is not ruled out.

## How a request is handled

1. **Search everything in force.** BM25 over all passages whose document has taken effect on
   `as_of` and has not been superseded by then (`Corpus.search`).
2. **Refuse before the model where the scores already decide it** (`gate`): restricted text is
   clearly the best match → `not_permitted`; nothing permitted resembles the question →
   `not_in_corpus`. About one request in six ends here, with no model call.
3. **Ask the model** with the six best permitted passages, each headed by its effective date.
   Restricted text is never placed in a prompt. `as_of` and the role are not shown to the model.
4. **Check the reply in code**: schema; the quote must be inside the cited passage under the
   grader's normalisation, else it is replaced by the passage text; any 12-token run shared with
   a document above the requester's role withholds the answer.

The index is BM25 in memory, rebuilt from `CORPUS_DIR` at every start (under a second, no model
calls, no cost), so a restart with a revised corpus cannot serve removed text.

## Run it

Needs Python 3.10+ and network once for `pip install` (or the Docker build). Inputs: `CORPUS_DIR`, `PORT`, `LLM_BASE_URL`, `LLM_API_KEY`; optional
`GEN_MODEL` (default `qwen/qwen3.8-27b`) and `GEN_EXTRA` (JSON of extra request options, default
`{"reasoning_effort": "low"}`; set `'{}'` for a model that rejects it). See `.env.example`.

```bash
scripts/reproduce.sh serve    # the service on $PORT
scripts/reproduce.sh test     # safety checks with a fake model: no key, no network
scripts/reproduce.sh eval     # dev set -> results/answers_dev.jsonl, graded, appended to results/manifest.json
scripts/reproduce.sh eval --no-llm                              # search and gate numbers only
scripts/reproduce.sh eval --file dev_extra/ooc_nearmiss.jsonl   # any question file with gold
scripts/reproduce.sh load     # concurrency 12 against a stub model
```

Dependencies install from `./wheels` when that directory exists (no network), otherwise from
PyPI; the install is skipped when the packages already import. `Dockerfile` installs at build
time and runs as `nobody`.

`scripts/pacing_proxy.py` is development tooling for a rate-limited tier: it paces calls, caches
identical requests on disk so an interrupted run can resume, and writes
`results/raw/ledger.jsonl`. The service does not need it.

## Reproducibility facts

- **Benchmark:** `Deployment-inc/Deployment.inc-Hiring-Problems` at commit
  `d87699bb97de6504b33f681eed66918a4d433ba0`. `grader.py`, `rubric.md`, the corpus and the
  question files are used unmodified from `references/OP-05`; `REF_DIR` points at that folder.
- **Dependencies:** every package is pinned in `requirements.txt` (direct pins in
  `requirements.in`), checked on Linux with Python 3.10, 3.12 and 3.13.
- **Models:** see "Tested on". No seed is set: the provider's default sampling is used, so a
  rerun will not reproduce answers word for word.
- **Runs:** `results/manifest.json` lists every run, including four that were aborted or only
  diagnostic (provider quota, laptop closed). Aborted runs wrote no answers file; their model
  calls are in `results/raw/ledger.jsonl`. The reported result is the single run
  `dev-20261111-105319`, not the best of several.
- **Spend:** USD 1.18 at list prices for every call in the ledger, aborted runs included.
- **Held-out:** no held-out answers were generated and no held-out score is claimed. I looked at
  the held-out file only for its tag and role counts.

## Where the evidence is

| Question | File |
|---|---|
| What was tried, in order, including what failed | `EXPERIMENT_LOG.md` |
| Why BM25, why the counting rule was removed, why the gates look as they do | `DECISIONS.md` |
| What exists and what was measured against it | `LANDSCAPE.md` |
| What a compliance owner should know | `MEMO.md` |
| Every run: model, tokens, cost, grader summary | `results/manifest.json` |
| Per-question answers, metadata and grader verdicts | `results/raw/<run_id>.jsonl`, `.report.json` |
| Every model call: tokens, provider time, pacing, errors | `results/raw/ledger.jsonl` |
| Retrieval bake-off and plateau experiments | `bench_retrieval.py`, `results/raw/retrieval_bench.json`, `retrieval_extra.json` |
| Service-side load test | `scripts/loadtest.py`, `results/raw/loadtest.json` |
| My own out-of-corpus sets | `dev_extra/` |

## Files

`app.py` is the whole service (about 230 lines). `evaluate.py` runs a question file through the
same `answer()` function the service uses and calls the unmodified official `grader.py`.
`test_app.py` holds the checks that must never fail: role wall, quote repair, overlap guard,
outage handling, version dates.
