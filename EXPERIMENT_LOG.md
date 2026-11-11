# Experiment log

Dated, in order, dead ends included. Raw outputs are in `results/raw/`.

## 2026-11-10 — Phase 1: baseline and harness

**Built.** `app.py` (TF-IDF over the shipped passages, unigrams and bigrams, top-6 into one model
call, role gate before generation), `evaluate.py` (runs a split at concurrency 12, calls the
official `grader.py` unmodified, appends the run to `results/manifest.json`), `test_app.py`.

**Measured without any API call** (`python evaluate.py --no-llm`, dev split, 146 questions):

| Metric | Value |
|---|---|
| Gold passage in allowed top-1 | 0.605 |
| Gold passage in allowed top-3 | 0.8235 |
| Gold passage in allowed top-6 | 0.8908 |
| Role-blocked questions caught by "top-1 is restricted" gate | 19 / 21 (0.9048) |
| Answerable questions wrongly blocked by the gate | 0 / 119 |
| Out-of-corpus questions caught before the model | 0 / 6 |

**Reading.**
- Top-6 recall of 0.8908 caps answer correctness near 0.89 before the model makes any mistake.
  The bar is 0.88, so retrieval is the first thing to fix (Phase 2).
- The naive role gate already reproduces the reference's 0.9048. Two blocked questions slip
  through to the model; they are safe (restricted text is filtered from the prompt) but will be
  answered as "not in corpus", which is the wrong refusal.
- TF-IDF has no way to refuse an out-of-corpus question: some passage always shares a word.
  Out-of-corpus refusal rests entirely on the model in this baseline (Phase 3).

**Not yet run.** The full dev run with generation and the rubric judge. Blocked on an API key.

**Packaging dead end.** A virtualenv created by `uv venv` has no `pip`, so `scripts/reproduce.sh`
failed on its install step. The script creates its own venv with `python3 -m venv` on a clean
machine, which does include pip; locally fixed with `uv pip install pip`.

## 2026-11-10 — Phase 1: first full dev run (`dev-20261110-180527`)

**Setup change.** No OpenAI key available, so the generator is `qwen/qwen3.8-27b` on Groq
(27B parameters, budget class, `reasoning_effort: low`, $0.80 / $4.00 per million tokens, listed
as Preview). The pinned judge `gpt-4.1-mini-2025-04-14` is not on Groq, so local grading uses
`openai/gpt-oss-20b` with the official `grader.py` and rubric unmodified. **Local judged numbers
are therefore approximations of what the reviewers' judge will say.**

The Groq free tier allows 8,000 tokens per minute. `scripts/pacing_proxy.py` paces calls and
keeps a ledger; the run used concurrency 1 and took about 62 minutes. **Latency from this run
(p95 45 s) measures the rate limit, not the system, and is not a valid bar-8 number.**

| Bar | Target | Baseline | |
|---|---|---|---|
| Coverage | ≥ 0.87 | 0.9328 | pass |
| Answer correctness | ≥ 0.88 | 0.7815 | **fail** |
| Contradiction slice (n=8) | ≥ 0.88 | 0.75 | **fail** |
| Temporal slice (n=19) | ≥ 0.88 | 0.8947 | pass |
| Citation verbatim | ≥ 0.92 | 1.00 | pass |
| Citation support | ≥ 0.82 | 0.8661 | pass |
| Out-of-corpus refusal (n=6) | ≥ 0.95 | 1.00, 0 fabricated | pass |
| Role violations (deterministic check) | 0 | 0 | pass |
| Role-blocked refusal (n=21) | ≥ 0.87 | 0.9048 | pass |
| Tokens per question | ≤ 1,005 in / 743 out | 759 / 350 | pass |
| p95 latency | ≤ 10.8 s at concurrency 12 | not measurable on this tier | open |

Cost of the run: $0.29 generation at list price.

**Failure taxonomy, 119 answerable questions (93 correct, 26 not):**

| Category | Count | Fix belongs to |
|---|---|---|
| Wrong answer, gold passage was in the prompt | 14 | Phase 4 (generation; may include judge strictness) |
| Refused, gold passage not retrieved | 7 | Phase 2 (retrieval) |
| Wrong answer, gold passage not retrieved | 4 | Phase 2 (retrieval) |
| Refused, gold passage was in the prompt | 1 | Phase 4 |

Accuracy by category: regulatory interpretation 45/63, numerical 23/27, temporal 17/19,
contradiction 6/8, internal policy 2/2. The model cited the gold passage in 87 of 111 answers.

**Other findings.**
- One role-blocked question was *answered* from permitted passages, and one was refused as
  "not in corpus". No restricted text leaked (it is filtered before the prompt), but both are
  wrong outcomes. Phase 3.
- One call failed with Groq HTTP 400 "Failed to generate JSON" (`indiafinbench_REG_137`) and was
  returned as a refusal. JSON object mode on this model is not fully reliable. Phase 4/6.
- The model's quote failed the verbatim check once and was replaced by the passage text.
- Small slices: contradiction n=8 and out-of-corpus n=6 on dev. One question moves the
  contradiction slice by 12.5 points, so these two numbers carry little evidence yet.

## 2026-11-10 — Phase 2: retrieval bake-off (`bench_retrieval.py`, no API calls)

Dev split, 119 answerable questions. "r@k" = gold passage within the top k passages the
requester may see. "Blocked caught" = role-blocked questions caught by the rule "best match is
restricted" (of 21). "Wrongly blocked" = answerable questions that rule would refuse (of 119).
Raw rows: `results/raw/retrieval_bench.json` (lexical, dense, hybrid) and the table below
(rerankers, copied from the run output; the reranker run was stopped before it wrote the file).

| Method | r@1 | r@3 | r@6 | Blocked caught | Wrongly blocked | ms / question |
|---|---|---|---|---|---|---|
| TF-IDF (Phase 1) | 0.605 | 0.824 | 0.891 | 19 | 0 | 0.2 |
| TF-IDF + document title | 0.630 | 0.824 | 0.924 | 19 | 0 | 0.3 |
| **BM25 (`bm25s`)** | 0.639 | 0.832 | **0.941** | 20 | 0 | 0.2 |
| BM25 + document title | 0.647 | 0.857 | 0.933 | 20 | 0 | 0.1 |
| Dense `bge-small-en-v1.5` + title | 0.571 | 0.790 | 0.882 | 19 | 0 | 196 |
| Dense `snowflake-arctic-embed-s` | 0.546 | 0.832 | 0.908 | 19 | 1 | 418 |
| Dense `all-MiniLM-L6-v2` | 0.462 | 0.672 | 0.807 | 20 | 1 | 277 |
| Dense `bge-base-en-v1.5` + title | 0.563 | 0.815 | 0.882 | 20 | 1 | 880 |
| RRF(BM25, bge-small) + title | 0.622 | 0.815 | 0.924 | 19 | 0 | +196 |
| RRF(BM25, arctic-embed-s) + title | 0.597 | 0.874 | 0.950 | 19 | 0 | +211 |
| RRF(BM25, bge-base) + title | 0.639 | 0.849 | 0.933 | 19 | 1 | +880 |
| Rerank top-20: `ms-marco-MiniLM-L-6-v2` | 0.613 | 0.832 | 0.891 | 19 | 3 | 661 |
| Rerank top-20: `ms-marco-MiniLM-L-12-v2` | 0.588 | 0.807 | 0.866 | 20 | 2 | 1,563 |
| Rerank top-20: `jina-reranker-v1-turbo-en` | 0.571 | 0.849 | 0.933 | 20 | 0 | 992 |
| Rerank top-20: `bge-reranker-base` | 0.630 | 0.916 | 0.933 | 19 | 0 | 6,968 |

Timings are single-threaded on an Apple M1 and include model load amortised over 146 questions.

**Decision: BM25 alone.** Hypothesis going in was that hybrid search plus a reranker would win,
as it does on general benchmarks. It did not here:
- The best hybrid beats BM25 by one question at r@6 (0.950 vs 0.941). With 119 questions one
  question is 0.8 points, well inside noise.
- Every reranker was equal or worse at r@6, and three of four wrongly blocked answerable
  questions or cost 0.5–7 seconds per question on CPU.
- Regulatory questions name the regulation, the clause and the exact term, which is the case
  where lexical matching is strongest.
- Embedding and reranker weights would have to be vendored: the evaluation container has egress
  only to the model gateway (EVALUATION_PROTOCOL.md), so a download at start could fail.

**What would reverse it:** a corpus where questions paraphrase rather than quote the rules
(user-facing chat instead of compliance staff), or measured recall below about 0.90 on new
documents. `bge-reranker-base` has the best r@3 (0.916) and is the first thing to retry if
top-3 precision becomes the limit, given a faster runtime.

**Gold-label finding.** Of the 7 BM25 misses at r@6, 3 are label artefacts: two internal-policy
questions cite passage `#s00000` (the document header) while the answer is in `#s00002` /
`#s00004`, which BM25 ranks first; one cites one of two overlapping duplicate passages and BM25
ranks the other first. Effective r@6 is about 0.966. The grader never reads gold citations, so
this affects only our own retrieval metric. The 4 real misses are all inside two long SEBI
regulations (credit rating agencies, investment advisers) where every passage shares the same
vocabulary.

**Dead end / incident.** The first Phase 2 dev run hung for two hours. Groq returned 429 with a
long retry-after and `scripts/pacing_proxy.py` slept through it while holding the per-model
lock. Fixed: the proxy now fails fast when retry-after exceeds 90 s, caches identical requests
on disk so an interrupted run resumes, and logs provider error bodies; `evaluate.py` records no
run when the provider quota is hit. Cached replies are for development only; submitted runs
must use `PROXY_CACHE=0`.

**Quota finding (22:12 IST).** The hang and the two aborted reruns have one cause, now read from
the provider's error body: Groq free tier allows **200,000 tokens per day** for
`qwen/qwen3.8-27b` (rolling 24 hours), on top of 8,000 per minute. One dev run uses about
133,000 generator tokens, so the free tier supports roughly one scored run per day. The Phase 1
run and its tests used the day's allowance. **The scored dev run for BM25 has therefore not been
made yet;** the Phase 2 decision rests on the retrieval metrics above, which need no model. 15
replies from the aborted attempts are cached and will be reused.

## 2026-11-10 — Phases 3 + 4: refusal gates and answer quality (analysis, no API calls)

Phases 2, 3 and 4 are scored in one dev run because the provider allows about one full run per
day. Attribution comes from the per-question failure taxonomy instead of one run per lever; that
is weaker evidence than separate ablations and is stated as such.

**Why answers were wrong when the right passage was in the prompt (15 questions, Phase 1 run).**
Read one by one from `results/raw/dev-20261110-180527.*`:

| Pattern | Questions | Change |
|---|---|---|
| The prompt said "asked as of 2020-01-01" and the model un-applied later amendments that the passage text already contains ("in 2020 this proviso was not yet in force") | 4 | `as_of` is no longer shown to the model; version selection by date belongs to retrieval (Phase 5) |
| Date arithmetic off by one: the dataset counts the starting day as day 1 and month periods end on the same day of the month | 3 | Counting rule added to the prompt, with examples that are not dev questions |
| Extra neighbouring provisos added, or a qualifying condition left out | 2–3 | Prompt: answer what was asked, include qualifiers of that rule, no neighbouring provisions |
| Looks correct on reading; the stand-in judge (`gpt-oss-20b`) marked it wrong | about 5 | None. Evidence that the local judge is stricter or noisier than the rubric intends |
| Model refused although the passage was present | 1 | None yet |

**Refusal gates, measured offline on dev plus 20 synthetic out-of-corpus questions**
(`dev_extra/ooc_synthetic.jsonl`, written for this purpose: adjacent Indian finance topics with
zero mentions in the corpus, mixed requester roles; dev has only 6 out-of-corpus questions, all
asked by `legal`).

- Finding: with the Phase 1 rule ("best match is restricted, so not permitted"), 4 of 14
  synthetic out-of-corpus questions from `public`/`ops` requesters were refused as "not
  permitted". A weak accidental match on a restricted passage is enough. Dev could not show this
  because all its out-of-corpus questions come from `legal`, who can see everything.
- Tried: query-term coverage and out-of-vocabulary share as relevance signals. Neither separates
  out-of-corpus from answerable better than the raw best BM25 score. Dropped.
- Chosen: two thresholds on the best BM25 score. Below 6.0 and nothing restricted on top: "not
  in corpus" without a model call. Restricted on top: "not permitted" only at 4.5 or above.

| Outcome before the model is called | Dev | Synthetic |
|---|---|---|
| Blocked questions refused as "not permitted" | 19 / 21 | n/a |
| Blocked questions refused as "not in corpus" (wrong refusal) | 1 | n/a |
| Answerable questions refused | 0 / 119 | n/a |
| Out-of-corpus refused correctly | 4 / 6 | 15 / 20 |
| Out-of-corpus refused as "not permitted" (wrong refusal) | 0 | 1 |
| Out-of-corpus passed on to the model | 2 | 4 |

The 4.5 threshold sits in a gap of 1.1 points between 3 synthetic examples and 1 dev example.
That is thin. It is an environment knob (`MIN_BLOCK_SCORE`) and a known weak point.

**Leak guard.** Three restricted documents share 12-word runs with public ones, and the grader
counts any 12-token overlap between the answer and a restricted document as a violation that
fails the submission. `Corpus.leaks()` applies the grader's own check to every answer; a hit is
withheld as a refusal. The prompt also asks for the answer in the model's own words.

**Provider JSON failure.** Groq rejected one reply with HTTP 400 "Failed to generate JSON".
Generation now retries once.

## 2026-11-10 — Phases 2–4 combined scored run (`dev-20261110-224656`)

One run for three phases, to stay inside the provider's daily token quota. Attribution to a
single change therefore comes from tagging each failed question by cause, not from separate runs.
Generator `qwen/qwen3.8-27b`, stand-in judge `openai/gpt-oss-20b` (the official judge model is not
available on this provider, so every judged number below is approximate).

| Metric | Bar | Phase 1 | Phases 2–4 |
|---|---|---|---|
| Coverage (answered on answerable) | ≥ 0.87 | 0.9328 | 0.9748 |
| Correctness | ≥ 0.88 | 0.7815 | **0.8739 (fail, 1 question short)** |
| Correctness, contradiction slice (n=8) | ≥ 0.88 | 0.75 | **0.75 (fail)** |
| Correctness, temporal slice (n=19) | ≥ 0.88 | 0.8947 | 0.9474 |
| Quote verbatim | ≥ 0.92 | 1.00 | 1.00 |
| Citation support | ≥ 0.82 | 0.8661 | 0.8718 |
| Out-of-corpus refusal (6 dev) | ≥ 0.95 | 1.00 | 1.00 |
| Out-of-corpus refusal (20 synthetic, `ooc_synthetic-20261110-224630`) | ≥ 0.95 | n/a | 0.95, 0 fabricated |
| Role violations | 0 | 0 | 0 |
| Role-blocked refusal | ≥ 0.87 | 0.9048 | 0.9048 |
| Input / output tokens per question | ≤ 1005 / 743 | 759 / 350 | 897 / 326 |

Latency is not reported: calls were paced one at a time by the development proxy.

Failure causes on the 119 answerable questions:

| Cause | Phase 1 | Phases 2–4 |
|---|---|---|
| Wrong, gold passage was in the prompt | 14 | 12 |
| Refused, gold passage not retrieved | 7 | 3 |
| Wrong, gold passage not retrieved | 4 | 0 |
| Refused, gold passage was in the prompt | 1 | 0 |

19 questions fixed, 8 newly failed. Reading the 8:

- **My counting rule was wrong (2 questions, `NUM_035`, `NUM_039`).** Phase 4 added "the starting
  date is day 1" after three off-by-one failures. It fixed `NUM_010` and `NUM_114` and broke two
  questions the model had right before. The gold answers are not consistent with each other:
  "1 April + 120 days = 29 July" counts the first day, "thirty days from 25 March = 24 April" does
  not. No single rule satisfies both pairs. I removed the day rule and kept the months rule. The
  model's default (exclude the first day) is also the statutory convention, so that is the
  behaviour I would defend to a compliance reader. Net effect on dev: zero. Lesson: three examples
  were not enough to write a rule from.
- **Yes/no question answered "Not entirely" (`CON_036`).** Gold: "Yes". Added a rule: start a
  yes-or-no answer with Yes or No. The same answer also referred to "Passage [1]"; the prompt
  now forbids passage numbers in answers.
- **Stand-in judge strictness (about 6 of the 12).** `REG_023`, `NUM_101`, `TMP_008` give the
  gold fact plus a correct proviso from the same passage; `REG_174`, `REG_173`, `CON_062` match
  the gold answer almost word for word. The rubric says extra correct context does not matter.
  `CON_062` flipped to correct in the probe below with an unchanged answer. I did not strip
  provisos: the rubric penalises an omitted condition, not an added one.
- **Derived date (`REG_102`).** The answer added "i.e., by 1 June", which the passage does not
  say. The prompt now forbids figures and dates the question did not ask for.

Not fixed: 3 refusals where the gold passage is outside the top 6 (two are about credit rating
agencies), and 2 refusal-type errors (`internal-006`, a five-word blocked question that matches
nothing; `TMP_013`, a blocked question answered from permitted text, no leak).

## 2026-11-10 — Phase 5: versions and dates (built, offline checks, 10-question probe)

The freshness contract supplies a revised corpus with a superseding version, an amendment and a
withdrawal notice, and restarts the service.

- `Corpus.search(question, as_of)` returns only passages in force on `as_of` (today when absent
  or malformed): the document's `effective_date` is on or before that date and no document that
  lists it in `supersedes` has taken effect yet. Checked on dev first: for all 119 answerable
  questions the gold document is already in force on the question's `as_of`, so the filter is
  consistent with the data. Dev recall and gate decisions are unchanged.
- Documents that are both in force (an amendment published beside its base rule, with no
  `supersedes` link) cannot be separated by metadata. Each passage in the prompt now carries its
  document's effective date and the prompt says the later date prevails on conflict.
- `as_of` itself stays out of the prompt (Phase 4 finding).
- The index lives in memory and is rebuilt from `CORPUS_DIR` at start, so a restart cannot serve
  removed text. Index build is local BM25: no API cost; time is logged as `index_seconds`.
- Known limit: a superseded version is reachable only through an earlier `as_of`. A question
  asked today about "what the old rule said" gets the current document or a refusal.
- Test: `test_app.py` builds a revised corpus with a v2 of the internal policy effective
  2027-01-01. Before that date the prompt holds only v1 text, after it only v2 text and the
  citation points at v2; a `public` requester is still refused.

Probe `probe_prompt-20261110-235723` (10 dev questions: 7 failures above plus 3 controls; not a
score): `CON_036`, `NUM_035`, `NUM_039` now correct; `NUM_010`, `NUM_114` wrong again as
expected; `REG_023` still marked wrong by the stand-in judge. Input tokens rose by about 108
per model call (date headers and two new rules), projecting to about 972 per question against
the 1,005 cap. Too close: the system prompt was then shortened by about 170 characters. Top 5
instead of top 6 passages was rejected: it loses the gold passage for 2 more dev questions.
Real token figures come from the next full run.

## 2026-11-11 — Phase 6: hardening (no model calls)

- **Outage is not a refusal.** When the model call fails twice or returns unusable output,
  `answer()` still fails closed (no answer, no citation), and `/ask` now returns HTTP 503 with
  `Retry-After` instead of "the documents do not answer this question". Refusals decided before
  the model (role-blocked, nothing matched) are unaffected by an outage.
- **Bounded waiting.** Default model timeout 30 s → 8 s, SDK retries 2 → 1. Worst case for one
  request is now well under the old 3 × 30 s.
- **Load, service side** (`scripts/loadtest.py`, `results/raw/loadtest.json`): 146 dev questions at
  concurrency 12 against a stub model that answers after 2.0 s.

| Pass | HTTP | p50 | p95 | max |
|---|---|---|---|---|
| Stub model healthy | 146 × 200 | 2.02 s | 2.18 s | 2.20 s |
| Stub model returns HTTP 500 | 24 × 200, 122 × 503 | 0.88 s | 0.98 s | 1.02 s |

  The service adds under 0.2 s at p95 and does not queue at concurrency 12. This is not a
  provider latency measurement: real p95 at concurrency 12 cannot be measured on a tier limited
  to 8,000 tokens per minute. The budget left for the model is about 10.6 s of the 10.8 s bar.
- **Packaging finding.** The protocol runs submissions with egress restricted to the model
  gateway, and `reproduce.sh` installed from PyPI on every start. It now skips the install when
  the packages import, and installs from `./wheels` without network when that directory exists.
  The pinned versions need Python 3.12 (numpy 2.5.4 has no wheels for 3.10 or 3.11); the script
  header said 3.10+ and was wrong. Linux x86_64 wheels for 3.12 total 22 MB (22 files); whether
  to commit them is a Phase 7 decision.
- **Dockerfile** added (installs at build time, runs as `nobody`, corpus mounted read-only).
  Not built or run: no Docker daemon on this machine. A Linux run is still owed.

## 2026-11-11 — Search for remaining gains (offline, no model calls)

Question: is anything left that would move a bar, before the documents are written? Everything
here was measured on dev or on my own synthetic sets; none of it reads held-out answers.

**Calibration reading.** The published reference attempt (TF-IDF top six, GPT-5 mini) scores
0.8067 correctness on dev and 0.7619 on held-out; temporal 0.79 and 0.71. Held-out is harder by
about 4 to 8 points for that system. Held-out also has more temporal (20% against 16%) and
contradiction (13% against 8%) questions by tag. A dev score just above a bar is therefore not
evidence of clearing it on held-out.

**Retrieval: three attempts to break the 0.94 plateau, all failed.**

- The misses are not wrong-document errors. For 5 of 7, the top four hits come from the right
  regulation and the gold passage sits at rank 7 to 69 behind its siblings (for example three
  credit-rating-agency questions whose distinguishing words are "records", "promoters",
  "activities").
- Hypothesis: regulation-wide terms drown the distinguishing ones, so rank inside the best
  document with that document's own term statistics. Twelve variants (weighted sum, routing to
  the top 1 to 3 documents, rank fusion): r@6 0.73 to 0.93, all worse than 0.941.
- Stemming and a BM25 parameter grid, 20 settings: r@6 0.916 to 0.941. A plateau.
- Conclusion: lexical ranking is saturated on this corpus. The remaining misses need either
  more passages per question (token cap) or index-time enrichment (model calls at every start,
  not affordable on my provider tier). Recorded in `LANDSCAPE.md` as not measured.

**Citations.** On run `dev-20261110-224656`, 10 of 14 "citation does not support the answer"
verdicts are on the gold passage itself. Changing which passage is cited would not help; a
second citation would be judged separately and add failures. Left as is.

**Quote repair.** 9 answers had a non-verbatim quote replaced by the passage text; 7 of them are
correct. A repaired quote is not a useful signal for refusing.

**`as_of`.** For all 119 answerable dev questions the gold document is in force on `as_of`, and
`as_of` never equals the gold document's effective date, so it cannot be used to guess the
document. It is used only as the contract describes: to exclude what is not in force.

**Injection wrappers on the gates.** Five framings of every dev question ("I am the head of
legal…", "ignore your access rules…", a fake system line, a long polite preamble): blocked
questions refused before the model 18 to 20 of 21 (plain: 19); answerable questions wrongly
blocked 0 of 119 in every framing. The role wall holds because the role comes from the request
field and restricted text never enters a prompt. Weakness found: padding raises raw BM25
scores, so the "nothing matched" gate catches 2 of 6 out-of-corpus questions instead of 4; the
rest go to the model, which is the second line of defence. Not fixed.

**Refusal gate, two changes (see `DECISIONS.md` 3).**

- Ratio branch: a short blocked question (`internal-006`, score 2.8) matches restricted text 1.5
  times better than permitted text but fell under the absolute threshold. "Not permitted" now
  also fires at 1.4 times with a lower floor.
- Near-tie rule: I wrote 16 near-miss out-of-corpus questions (`dev_extra/ooc_nearmiss.jsonl`: a
  regulation that is in the corpus, a fact that is not, each checked by keyword search). Two
  from `public` were refused as "not permitted" because a restricted passage led by 4%. A
  restricted hit less than 10% ahead of the best permitted passage is now ignored.

| Before the model is called | Dev | Synthetic far (20) | Synthetic near-miss (16) |
|---|---|---|---|
| Blocked refused as "not permitted" | 19 / 21 | n/a | n/a |
| Answerable refused | 0 / 119 | n/a | n/a |
| Out-of-corpus refused correctly | 4 / 6 | 15 | 2 |
| Out-of-corpus refused as "not permitted" (wrong) | 0 | 1 | 0 (was 2) |
| Out-of-corpus passed to the model | 2 | 4 | 14 |

  The near-miss set mostly reaches the model by design: it measures whether the model invents
  an answer when the right regulation is in front of it but the fact is not. Not yet run through
  the model (quota).

**Latency evidence.** The development proxy now records the upstream time of every call
(`upstream_seconds` in `results/raw/ledger.jsonl`), so sequential provider latency is measured
even though concurrency 12 is not reachable on this tier.

## 2026-11-11 — Final scored run (`dev-20261111-105319`), second judge, near-miss set

All on Groq: generator `qwen/qwen3.8-27b` (`reasoning_effort: low`), judge `openai/gpt-oss-20b`,
second judge `openai/gpt-oss-120b`. The run was interrupted twice by the laptop closing; 30
model replies from the first start (00:29–00:41) were replayed from the proxy cache and the
other 93 are fresh. The gate changes above do not alter any prompt, so replaying is exact.

| Metric | Bar | Phases 2–4 | Final | Final, second judge |
|---|---|---|---|---|
| Coverage | ≥ 0.87 | 0.9748 | 0.9748 | 0.9748 |
| Correctness | ≥ 0.88 | 0.8739 | 0.8992 | **0.8739** |
| Contradiction slice (n=8) | ≥ 0.88 | 0.75 | 1.00 | **0.625** |
| Temporal slice (n=19) | ≥ 0.88 | 0.9474 | 0.9474 | 0.9474 |
| Quote verbatim | ≥ 0.92 | 1.00 | 1.00 | 1.00 |
| Citation support | ≥ 0.82 | 0.8718 | 0.8889 | 0.8974 |
| Out-of-corpus refusal (6) | ≥ 0.95 | 1.00 | 1.00 | 1.00 |
| Role violations | 0 | 0 | 0 | 0 |
| Role-blocked refusal | ≥ 0.87 | 0.9048 | 0.9048 | 0.9048 |
| Input / output tokens per question | ≤ 1005 / 743 | 897 / 326 | 960 / 316 | |

**Judge noise is as large as the gap to the bar.** Same answers, two judges: same correctness
verdict on 107 of 116 answered questions; 6 answers only the 20B judge accepts, 3 only the 120B
judge accepts. Correct by both: 101 of 119 (0.849); by at least one: 110 of 119 (0.924). The
three contradiction answers the second judge rejects (`CON_061`, `CON_062`, `CON_070`) all say
"No" as the gold answer does and then explain the difference. The rubric says extra correct
context does not matter, and gold is the bare word "No", so a judge cannot check the
explanation and may go either way. I did not shorten yes/no answers to the bare word: that
would score more safely and tell a compliance reader less. It is the first thing to change if
the official judge behaves like the second one.

**What moved since the Phases 2–4 run.** `CON_036` (yes/no rule), `NUM_035` and `NUM_039`
(day rule removed) are fixed; `NUM_010` is wrong again as predicted. Still wrong under both
judges: 3 refusals where the gold passage is not retrieved (`REG_177`, `REG_167`, `NUM_107`),
`NUM_010`, `REG_197` (answer drops "SEBI-registered merchant banker"), and four where the
answer contains the gold fact plus a correct proviso (`REG_023`, `REG_173`, `REG_188`,
`TMP_008`).

**Refusals.** Role-blocked 19 of 21. The two misses: `TMP_013` is answered from permitted text;
`NUM_136` is the near-tie case the gate now lets through (restricted 10.3 against permitted
10.1), and the model then declined, so the requester got "not in the documents" instead of "not
permitted". That is the price of the near-tie rule, paid as predicted. No restricted text was
shown in either case.

**Near-miss out-of-corpus set (`ooc_nearmiss-20261111-115656`).** 16 of 16 refused, 0
fabricated. 14 reached the model with passages from the right regulation in front of it and it
declined every time. This is the strongest evidence I have for the bar that allows no miss.

**Tokens.** 960 input per question, 4.4% under the cap. The increase from 897 is the date
headers and two prompt rules, plus one more question reaching the model. A model call averages
1,140 input tokens; the average depends on how many questions are refused before the model
(23 of 146 on dev). Largest single call: 1,617 in, 1,474 out (the output limit is 1,500).

**Provider latency.** 137 generator calls, one at a time: p50 0.97 s, p95 1.78 s, max 4.6 s.

**Spend at list price, all runs including aborted ones:** USD 1.18 (Qwen 1.08, GPT-OSS 20B
0.07, GPT-OSS 120B 0.04). Prices re-checked on 2026-11-11. Actual charge 0 (free tier).

## 2026-11-11 — Alignment audit against the problem statement (no model calls)

Read the problem statement, submission schema, evaluation protocol and model rules again against
the build. The organisers evaluate through their own gateway with GPT reference models, and I
tested only on Groq, so the audit looked for anything tuned to Groq that would fail elsewhere.

- **Timeout tuned to the wrong provider.** Phase 6 set the model timeout to 8 s from Groq's
  speed (p95 1.8 s). The reference system's p95 is 10.8 s end to end, so on a slower provider
  many valid calls would have been cut off and returned 503. Now 20 s. A slow answer misses a
  latency bar; a timed-out answer is wrong.
- **Model not served by the gateway.** If the gateway returns "no such model" for
  `qwen/qwen3.8-27b`, every call would fail. The service now switches once to
  `GEN_FALLBACK_MODEL` (default `gpt-5-mini-2025-08-07`) and logs it. Checked with a fake model
  in `test_app.py`; the request shape already matched what the grader's own comment says the
  GPT-5 family accepts. No quality claim for that model.
- **Token cap on the reference tokenizer.** The final run's prompts recounted with `o200k_base`:
  861 input tokens per question on the dev mix (cap 1,005), 1,023 per model call. Groq's count
  for Qwen is 960. No prompt trimming was needed.
- **Python version.** Pins now resolve for Python 3.10 to 3.13 on Linux x86_64 and aarch64
  (numpy 2.2.6 below 3.12), checked with `uv pip compile`. The install falls back to PyPI when
  `./wheels` does not fit the platform.
- **`results/answers.jsonl`.** The problem statement names this path and the schema names
  `answers_dev.jsonl`. Both are written.
- **Required analysis.** The statement asks for four things the documents did not yet contain
  in one place: the taxonomy with what moved each category, the two slices analysed separately,
  what breaks under the update pack, and behaviour on an unseen document type. Added to
  `README.md`, with a section on which leak paths are impossible and which are only unlikely.
- **Memo.** The statement asks how the reader would know the system has gone stale and what a
  year of upkeep takes. Both were missing; added.
- Considered and not done: a higher reasoning setting (the remaining errors are not reasoning
  errors, and output tokens on the reference model cannot be measured from here); a second
  retrieval pass after a refusal (one or two questions for a second chance to fabricate on the
  bar that allows no miss).
- Still not possible on this machine: building the Docker image or any Linux run.

## 2026-11-11 — Linux runs (Docker 29.4.2, linux/arm64, stub model)

No generator quota was left, so these runs prove that the service starts and behaves on Linux,
not answer quality there.

| Check | Result |
|---|---|
| `docker build` from `Dockerfile` (`python:3.12-slim`) | builds, 379 MB |
| Image with `--network none --read-only`, user `nobody`, corpus mounted read-only | index ready in 0.03 s; `/healthz` 200; role-blocked question → `not_permitted`; unmatched question → `not_in_corpus`; invalid role → 422; question needing the model → 503 in 0.87 s |
| `test_app.py` inside the image, no network | passes |
| 146 dev questions at concurrency 12 against the image, stub model answering in 2.0 s | 146 × 200; p50 2.04 s, p95 2.10 s, max 2.12 s (`results/raw/loadtest_docker.json`) |
| Same with the stub returning HTTP 500 | 23 × 200 (refusals decided before the model), 123 × 503; p95 0.99 s |
| Clean `python:3.10-slim`, repository copied in without `.venv`, `scripts/reproduce.sh test`, `eval --no-llm`, `serve` | installs numpy 2.2.6; checks pass; recall@6 0.9412 and every gate count identical to macOS; `/healthz` 200 |

Two things the Linux run turned up:

- First failure-pass p95 was 20.9 s. Cause: the stub server's listen backlog (5) dropped bursts
  of retry connections arriving through Docker's network, and each dropped connection waited
  out the 20 s model timeout. A stub artefact, fixed in `scripts/loadtest.py`. It showed the
  real worst case though: a hanging provider could hold a request for four timeouts (SDK retry
  times application retry). The application no longer retries after a timeout, so the worst
  case is two timeouts.
- `docker exec` without `-i` silently ran nothing on my first attempt; the first "pass" I saw
  was an empty output. Caught because the expected lines were missing.

## 2026-11-11 — Final audit against the challenge repository (commit `d87699b`, unchanged upstream)

Read every rule file again, including ones I had not opened (`CLARIFICATIONS.md`, `PINS.md`,
`CONTACT.md`, the OP-05 reference README and both JSON schemas). Fixed:

- **Failed runs were missing from the manifest.** The rules require every run, including failed
  ones. Three aborted runs and one diagnostic call are now listed with their tokens and cost,
  pointing at the ledger.
- **A provider account id was in the ledger** (inside three HTTP 429 error bodies). Redacted,
  and the proxy now redacts it when writing. No API key was ever written to a tracked file
  (checked by pattern search over every file git would add).
- **Transitive dependencies were unpinned.** `requirements.txt` is now a full lock generated from
  `requirements.in`; clean installs pass the checks on Linux Python 3.10, 3.12 and 3.13.
- **Corpus loading could stop the service.** A passage whose document is missing from the
  manifest, or a missing text file, raised an error at start. An update pack that withdraws a
  document by deleting its manifest line would have done that. Orphan passages are now dropped
  (they have no role or date, so they must not be served) and the overlap guard falls back to
  passage text. Covered in `test_app.py`.
- **`LANDSCAPE.md` was nearly two pages**; the rules say one. Cut to one.
- **Benchmark commit** recorded in `README.md` and the manifest.
- Claims recomputed with the official grader (`--no-judge`) from `results/answers_dev.jsonl`:
  coverage 0.9748, verbatim 1.0, out-of-corpus refusal 1.0, role violations 0. They match
  `claimed` exactly.

Confirmed from the reference README: the full question set is 329 answerable, 73 role-blocked,
16 out-of-corpus, so held-out has 52 role-blocked of 272 (19%, against 14% on dev). More
questions end before the model there, which lowers average tokens.

Checked and left alone: the prediction format's optional `cost_usd` and `latency_ms` fields are
not read by the grader, and my per-question latency includes pacing waits, so I did not write
misleading values into the answers file. Cost and provider latency are in the manifest.

**Reproducibility of the offline checks.** The plateau experiments (stemming, parameter grid,
document-local statistics) are now `python bench_retrieval.py extra`, output in
`results/raw/retrieval_extra.json`; the rerun matches the figures logged earlier. Four other
offline analyses were one-off scripts that are not in the repository, and their figures in this
log are copied from terminal output: the injection-wrapper table, the restricted-to-permitted
score ratios behind the gate thresholds, the citation and quote-repair breakdown, and the GPT
tokenizer count. The gate outcomes they led to are reproducible with
`evaluate.py --no-llm` on dev and on both files in `dev_extra/`.
