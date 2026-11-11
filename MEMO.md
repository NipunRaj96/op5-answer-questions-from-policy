# Memo

**To:** Head of Compliance, Harbour
**From:** Nipun Kumar
**Date:** 11 November 2026
**Subject:** "Ask the Policy Book": what it does, what it costs, when to stop it

## What it answers and what it refuses

Staff type a question and get one of three replies:

1. **An answer**, with the exact sentence it relied on and where that sentence is.
2. **"The available documents do not answer this question."**
3. **"Material exists, but your role is not permitted to see it."**

It answers only from documents the asker may read, and only from the version in force on the
date asked about. It does not interpret, advise, or know anything outside its documents.

## How well it works

146 test questions, one model (Qwen 3.8, 27B, served by Groq), graded by two substitute graders
(GPT-OSS 20B and 120B on Groq). The official test is harder and uses a different grader, so
read these as "close to the line", not "over it".

| | Result |
|---|---|
| Answerable questions it answered | 116 of 119 |
| Answers graded correct | 107 of 119 by one grader, 104 by the other |
| Quoted sentences that are exact | all |
| Questions outside the documents that it declined | 6 of 6, and 35 of 36 on a harder set I wrote |
| Restricted questions refused with the right message | 19 of 21 |
| Restricted text shown to someone not allowed to see it | none detected |

Cost: about USD 0.002 per question in model fees, nothing to load documents, one small server.

## What a wrong answer costs, and who pays

- **A confident wrong answer** (about 1 in 10 in testing; mostly day-counting and questions
  comparing two provisions). The officer who acts on it pays first, then the customer, then you
  with the regulator. **This is the main residual risk.**
- **"Not in the documents" when it is** (about 3 in 100). Cost: a manual search.
- **The wrong kind of refusal** (2 of 21 restricted questions). Nothing restricted is shown.
- **A leak of restricted text.** None detected, and restricted text is never given to the model.
  Not detected is not impossible: a public regulation the model already knows is the case to watch.
- **Model provider down.** It says "unavailable, retry". It never says the rule does not exist.

## How you would know it has gone stale

It cannot notice that a regulator changed something; it knows only its folder of documents.

- Monthly: compare the regulator's circular index with the folder. This is the only early warning.
- Every answer shows its source: an old document cited for a current topic is a sign.
- A branch or customer reports a withdrawn rule being quoted. By then it has already cost you.

## What keeping it current for a year takes

- **Each new circular, amendment or withdrawal:** one person adds the text and three facts (the
  date it takes effect, which document it replaces, who may read it) and restarts. About 15
  minutes, no engineer, no fee. The "replaces" link matters most: without it the old rule can
  still be quoted as current.
- **Quarterly:** the 50-answer check below.
- **When the document set grows a lot, or the provider retires the model** (the one tested is a
  preview release): an engineer re-measures the refusal settings. One to two days.

## When to pause it or send work to a person

- **Always a person:** anything quoted to a regulator or customer, any deadline counted in days,
  any comparison of two versions of a rule. Read the cited sentence, not only the answer.
- **Pause if:** a weekly sample of 50 answers checked by an analyst shows more than 5 wrong; or
  one answer cites a document the asker may not see; or one answer states a rule found in no
  document.
- **After any document update:** hold until the changed rules have been asked before and after.

## Next quarter

1. Re-test on the model you will run in production, with the official grader.
2. Agree a written convention for counting days; the test material is inconsistent on it.
3. Let it say "this rule was replaced on <date>" when asked about an old version.
