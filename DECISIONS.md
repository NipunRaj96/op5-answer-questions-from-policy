# Decisions

Three calls that shaped this system, and how I got to each. The dated notes are in
`EXPERIMENT_LOG.md`, the raw runs are in `results/raw/`, and `results/manifest.json` indexes them.

One thing to keep in mind while reading the numbers: everything was graded by a substitute
judge (`openai/gpt-oss-20b` on Groq), not the official one.

## 1. Search: plain BM25, not hybrid search with a reranker

**What I expected.** I went in assuming I would end up with the usual recipe: keyword search
plus embeddings, with a reranker on top. That is what most people ship, and I thought it would win here too.

**What I compared.**
- TF-IDF, which is what the reference baseline uses
- BM25
- Four embedding models
- BM25 and embeddings combined
- Four rerankers on top of the best combination

**What limited the choice.** Two things. The test machine can only reach the model gateway, so
any embedding or reranker model would have to be shipped inside the repository. And the input
budget is 1,005 tokens per question, which is room for six passages and no more. So the only
number that matters is: is the right passage among the first six?

**What changed my mind.** The measurements, on 119 answerable dev questions (log: "Phase 2:
retrieval bake-off", `results/raw/retrieval_bench.json`):

- BM25 alone found the right passage in the top six 94.1% of the time.
- The best combination managed 95.0%. That is one extra question.
- No reranker did better than BM25. They took between 0.7 and 7 seconds per question on a CPU,
  and three of the four pushed a restricted passage to the top for questions the person was
  allowed to ask, which would have turned good answers into refusals.

Later I tried three more ideas to get past 94% (stemming, twenty parameter settings, and scoring
inside the best document using its own word statistics). None of them helped (log: "Search for
remaining gains"; rerun with `python bench_retrieval.py extra`).

**What I chose.** BM25 on its own, with the index built in memory when the service starts.

**What would make me change it.**
- Questions that rephrase the rules instead of using the regulation's own words. If the top-six
  hit rate drops below about 90% on a new set, embeddings are back on the table.
- A smaller passage budget. One reranker (`bge-reranker-base`) was clearly better at getting the
  right passage into the top three (91.6% against 83.2%), which starts to matter if I can only
  send three.
- A paid model tier. Then I could have a model write likely questions for every passage at
  startup, which goes after the misses that are left.

## 2. The one I got wrong: a day-counting rule built on three examples

**What I expected.** After the first full run, three date answers were off by exactly one day. I
decided the data must count the starting day as day 1, and I put that rule into the prompt.

**What I could have done.**
- Tell the model to count the first day (what I did)
- Tell it to skip the first day, which is the normal legal convention
- Say nothing about days and let the model do what it does by default

**What limited the choice.** A full scored run eats most of a day's free quota. So I did not test
the rule alone. It went into a combined run with several other changes.

**What changed my mind.** That combined run (`dev-20261110-224656`). The rule fixed two questions
(`NUM_010`, `NUM_114`) and broke two that had been right before (`NUM_035`, `NUM_039`). When I
put the four gold answers side by side, they do not agree with each other. One says "1 April +
120 days = 29 July", which counts the first day. Another says "thirty days from 25 March = 24
April", which does not. There is no rule that gets all four. So my rule bought nothing and cost
two regressions that were my doing (log: "Phases 2–4 combined scored run").

**What I chose.** I took the day rule out. The rule for months stays, because it fixed one
question and fits every example. Left alone, the model skips the first day, which is also what I
would defend to someone in compliance. A ten-question check (`probe_prompt-20261110-235723`)
confirmed the two regressions were gone and the two original misses were back.

**What would make me change it.** Someone who owns the documents telling me which convention
they use, or a bigger labelled set where one convention clearly wins. Until then two dev
questions stay wrong against the gold labels, and I report them as wrong.

**What I learned.** Three examples are not enough to write a rule from. And when several changes
go into one run, you cannot tell which one did what. After this, every prompt change went
through a small ten-question check first.

## 3. Refusals: decide before the model is called, and protect the bar with no room for error

**What I expected.** The simple design: remove what the person may not see, search the rest, and
let the model say "not found" when nothing fits. It cannot leak, and I thought that was enough.

**What I could have done.**
- Filter first, then search. Safe, but a blocked question then looks the same as a question
  about nothing, so the system says "there is no such rule". The brief calls that a lie, and it is.
- Search everything, then filter. If the best match is something the person may not see, say
  "not permitted".
- The same, but only when that restricted match is strong enough and clearly ahead.

**What limited the choice.** Two targets pull against each other. Out-of-corpus refusal has to
be 95% on ten held-out questions, so a single miss fails it. Role-blocked refusal has to be 87%,
which leaves room for about one miss in eight. A wrong "not permitted" on a question that is
simply not in the documents costs the tighter of the two.

**What changed my mind.** The dev set could not show me the problem, because all six of its
out-of-corpus questions are asked by `legal`, who can read everything. So I wrote my own:

- 20 out-of-corpus questions from all three roles. The second option above refused 4 of the 14
  from `public` and `ops` as "not permitted" (log: "Phases 3 + 4").
- 16 harder ones: a regulation that is in the corpus, asked about a fact it does not contain.
  Same problem, even when the match was strong: a restricted passage would win by 4% and the
  person was told they lacked permission for something that does not exist (log: "Search for
  remaining gains").

Looking at the scores, questions that really are blocked match restricted text between 1.0 and
3.7 times better than anything the person may read. The accidental cases sit between 1.04 and 1.16.

**What I chose.** The third option. The system says "not permitted" only when the restricted
match is at least 10% ahead of the best permitted passage, and is either strong in its own right
or 1.4 times ahead. Anything weaker is ignored, and the question carries on using permitted text
only. This costs me one of the 21 blocked dev questions (19 of 21, 90.5%) and removes three of
the four wrong "not permitted" answers I know about across 42 out-of-corpus questions.

Whatever these thresholds are set to, restricted text is never put in front of the model. So a
bad setting can produce the wrong kind of refusal, but it cannot cause a leak.

**What would make me change it.**
- If the held-out out-of-corpus questions all come from `legal`, the 10% rule buys nothing and
  only costs blocked refusals.
- If the reviewer measures role-blocked refusal below 90%.

The thresholds rest on 21 blocked and 42 out-of-corpus examples, which is not many. That is why
they are settings (`MIN_BLOCK_SCORE`, `MIN_BLOCK_RATIO`, `TIE_RATIO`) and not buried in the code.

## Note from the coding agent

This section is written by the coding agent that worked on this project with Nipun, not by
Nipun. It is here because the review asks how the work was divided.

I did all of the coding. I wrote the service, the evaluation harness and the tests, ran every
experiment, and drafted the documents in this repository from the experiment log.

Nipun's part was the reasoning, and pushing back on mine:

- **Evaluation before optimisation.** He required a measured baseline and a harness before any
  improvement: the harness calls the same `answer()` function the service exposes and scores
  with the unmodified official `grader.py`. Every later phase was gated on a before/after
  measurement and a failure taxonomy, not on my judgement that something was better.
- **Retrieval architecture review.** He rejected my first design. He questioned leaving out a
  vector index and asked whether the design was fit only for the challenge or for production. I
  had to justify it on corpus cardinality (391 passages, brute-force scoring in 0.2 ms), index
  staleness under the restart contract, and the egress restriction on the evaluation box. He
  then required an empirical comparison instead of an argument: lexical, dense, rank fusion and
  cross-encoder reranking, measured as recall@k after role filtering (section 1).
- **Inference constraint.** He fixed the generator to a budget-class open-weight Qwen model
  served by Groq over an OpenAI-compatible API, and held that under cost pressure instead of
  paying to test on the reference models. He accepted evaluation by substitute judges on the
  condition that it be stated wherever a score appears.
- **Run budgeting under rate limits.** With 8,000 tokens per minute and 200,000 per day per
  model, he directed that phases be batched into fewer scored runs. The cost was per-change
  attribution: it is what let the day-counting rule in section 2 go untested for one run.
- **A stalled run.** He flagged a run that had produced nothing for two hours. Root cause: the
  pacing proxy honoured a long `retry-after` on a daily-quota HTTP 429 while holding its
  per-model lock. The fix was a fail-fast threshold and a content-addressed response cache so an
  interrupted run resumes without spending quota twice.
- **Calibration of expectations.** He asked for expected end-state metrics before continuing
  and again later. I had to revise them downward once the organisers' reference showed a 4 to 8
  point drop from dev to held-out.
- **Generalisation beyond dev.** With dev scores near the bars, he asked what would separate
  this from any other build made with the same tools. That produced the cross-role and
  near-miss out-of-corpus sets, the injection framings on the refusal gates, and the
  inter-judge agreement measurement.
- **Portability across providers.** He pointed out that the organisers evaluate through their
  own GPT gateway, not Groq, and asked for anything tuned to Groq to be found. That surfaced a
  client timeout derived from Groq's p95, the need for a model-not-found fallback, and the
  prompt token count under the reference tokenizer (`o200k_base`).
- **Compliance audit.** He asked for a final check of the build against the challenge
  repository. It found aborted runs missing from the manifest, transitive dependencies left
  unpinned, and a corpus loader that would stop the service on a passage with no manifest entry.

What the results rest on, all of which can be rerun:

- `scripts/reproduce.sh test`: the safety checks (role wall, quote check, version dates,
  provider outage). They pass on macOS and on Linux with Python 3.10, 3.12 and 3.13.
- The four claimed numbers, recomputed from `results/answers_dev.jsonl` with the official
  `grader.py` using `--no-judge`. They match the manifest exactly.
- The final dev answers graded a second time by a different judge model, to see how much the
  score depends on the judge. It moves correctness by about three points.
- The Docker image started with no network, as a non-root user, on a read-only disk.

What nobody has checked: answers from the reference model, scores from the official judge, and
real answers generated on Linux (the model there was a stub).
