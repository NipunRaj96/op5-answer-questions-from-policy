"""Run a question set through answer(), score it with the official grader, record the run.

    python evaluate.py --no-llm              retrieval and role-gate numbers only, no API calls
    python evaluate.py                       full dev run, graded with the rubric judge
    python evaluate.py --split heldout       answers only (gold is withheld)
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import app

REF = Path(os.environ.get("REF_DIR", "../hiring-problems/references/OP-05"))
CORPUS_DIR = os.environ.get("CORPUS_DIR", str(REF / "corpus"))
# USD per million tokens (input, output), MODELS.md pins verified 2026-09-06.
# Groq rates from https://console.groq.com/docs/models, retrieved 2026-11-10.
PRICES = {"gpt-5-mini-2025-08-07": (0.25, 2.00), "gpt-4.1-mini-2025-04-14": (0.40, 1.60),
          "qwen/qwen3.8-27b": (0.80, 4.00), "openai/gpt-oss-20b": (0.075, 0.30)}
PRICE_SOURCE = "https://console.groq.com/docs/models, retrieved 2026-11-10"
PROVIDER = os.environ.get("UPSTREAM_BASE_URL") or os.environ.get("LLM_BASE_URL")  # the proxy is local plumbing
CONCURRENCY = int(os.environ.get("EVAL_CONCURRENCY", "12"))  # lower it on rate-limited tiers


def retrieval_report(corpus, questions):
    """What search alone gets right. Needs gold, costs nothing."""
    hits = {1: 0, 3: 0, 6: 0}
    answerable = [q for q in questions if q["expected_status"] == "answered"]
    gates = {}
    for q in questions:
        order, scores = corpus.search(q["question"], q.get("as_of"))
        gate = (app.gate(corpus, order, scores, q["role"]) if len(order) else "not_in_corpus") or "to_model"
        key = (q["expected_status"], gate)
        gates[key] = gates.get(key, 0) + 1
        if q["expected_status"] == "answered":
            allowed = [corpus.passages[i]["passage_id"] for i in order if corpus.level[i] <= app.RANK[q["role"]]]
            gold = {c["section"] for c in q["gold_citations"]}
            for k in hits:
                hits[k] += bool(gold & set(allowed[:k]))
    report = {f"recall@{k}": round(v / max(len(answerable), 1), 4) for k, v in hits.items()}
    report["gates (expected -> decided before the model)"] = {f"{a} -> {b}": n for (a, b), n in sorted(gates.items())}
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "heldout"], default="dev")
    ap.add_argument("--file", help="other question file with gold, e.g. dev_extra/ooc_synthetic.jsonl")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--note", default="")
    a = ap.parse_args()

    qfile = Path(a.file) if a.file else REF / f"questions_{a.split}.jsonl"
    name = qfile.stem.replace("questions_", "")
    questions = [json.loads(line) for line in qfile.read_text().splitlines() if line.strip()]
    corpus = app.Corpus(CORPUS_DIR)

    if a.no_llm:
        print(json.dumps(retrieval_report(corpus, questions), indent=2))
        return

    quota_hit = []

    def one(q):
        if quota_hit:
            return None
        # Only the allowlisted fields reach the system, same as the official runner.
        body, meta = app.answer(corpus, q["question"], q["role"], q.get("as_of"))
        if "RateLimitError" in meta.get("error", ""):
            quota_hit.append(q["id"])
        return {"id": q["id"], **body}, meta

    started = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    run_id = f"{name}-{time.strftime('%Y%m%d-%H%M%S')}"
    with ThreadPoolExecutor(CONCURRENCY) as pool:
        results = list(pool.map(one, questions))
    if quota_hit:
        # A rate-limited answer is a refusal that says nothing about the system: record no run.
        done = sum(r is not None for r in results) - len(quota_hit)
        sys.exit(f"provider quota hit after {done}/{len(questions)} questions; nothing recorded. "
                 "Rerun later: the pacing proxy cache resumes where this stopped.")

    out = Path("results")
    raw = out / "raw" / f"{run_id}.jsonl"
    raw.write_text("".join(json.dumps({**body, "meta": meta}) + "\n" for body, meta in results))
    answers = out / f"answers_{name}.jsonl"
    answers.write_text("".join(json.dumps(body) + "\n" for body, _ in results))
    if name == "dev":  # the problem statement names this path, the submission schema the one above
        (out / "answers.jsonl").write_text(answers.read_text())

    n = len(results)
    tokens_in = sum(m["input_tokens"] for _, m in results)
    tokens_out = sum(m["output_tokens"] for _, m in results)
    latencies = sorted(m["latency_ms"] for _, m in results)
    price = PRICES.get(app.MODEL)
    run = {"run_id": run_id, "started": started, "split": name, "model": app.MODEL, "gen_extra": app.GEN_EXTRA,
           "provider": PROVIDER, "price_source": PRICE_SOURCE, "judge_model": os.environ.get("JUDGE_MODEL"),
           "seed": None, "status": "completed", "note": a.note, "concurrency": CONCURRENCY,
           "input_sha256": hashlib.sha256(qfile.read_bytes()).hexdigest(), "raw_path": str(raw),
           "questions": n, "errors": sum("error" in m for _, m in results),
           "input_tokens_per_question": round(tokens_in / n, 1), "output_tokens_per_question": round(tokens_out / n, 1),
           "latency_p95_ms": latencies[int(0.95 * (n - 1))],
           "cost_usd": round((tokens_in * price[0] + tokens_out * price[1]) / 1e6, 4) if price else None}

    if "expected_status" in questions[0]:
        run["retrieval"] = retrieval_report(corpus, questions)
        report = out / "raw" / f"{run_id}.report.json"
        cmd = [sys.executable, str(REF / "grader.py"), "--pred", str(answers), "--gold", str(qfile),
               "--corpus", str(Path(CORPUS_DIR) / "manifest.jsonl"), "--report", str(report)]
        graded = subprocess.run(cmd + (["--no-judge"] if a.no_judge else []), capture_output=True, text=True)
        if graded.returncode:
            run["status"] = "grader_failed"
            print(graded.stderr or graded.stdout, file=sys.stderr)
        else:
            run["grader"] = json.loads(graded.stdout)
            run["report_path"] = str(report)
            if run["grader"]["judge_errors"]:
                run["status"] = "judge_incomplete"  # usually judge quota; rerun to finish from cache

    manifest_path = out / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"claimed": {}, "runs": []}
    manifest["runs"].append(run)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(run, indent=2))


if __name__ == "__main__":
    main()
