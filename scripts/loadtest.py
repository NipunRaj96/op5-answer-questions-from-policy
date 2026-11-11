"""Service-side load check: the dev questions at concurrency 12 against a stub model.

Measures what this service adds (search, gates, validation, queueing), not provider speed: the
stub answers after STUB_DELAY seconds. A second pass makes the stub fail and expects HTTP 503.
    .venv/bin/python scripts/loadtest.py
With SERVICE_URL set it tests a service that is already running (for example the Docker image,
started with LLM_BASE_URL=http://host.docker.internal:4020) and writes LOADTEST_OUT.
"""
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REF = Path(os.environ.get("REF_DIR", "../hiring-problems/references/OP-05"))
DELAY, STUB, PORT = float(os.environ.get("STUB_DELAY", "2")), 4020, 18081
SERVICE = os.environ.get("SERVICE_URL") or f"http://127.0.0.1:{PORT}"
OUT = os.environ.get("LOADTEST_OUT", "results/raw/loadtest.json")
broken = False
REPLY = json.dumps({"choices": [{"message": {"content": json.dumps(
    {"status": "answered", "answer": "stub", "passage": 1, "quote": "x"})}}],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1}}).encode()


class Stub(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        time.sleep(0 if broken else DELAY)
        self.send_response(500 if broken else 200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(REPLY)))
        self.end_headers()
        self.wfile.write(REPLY)

    def log_message(self, *_):
        pass


def ask(q):
    body = json.dumps({k: q[k] for k in ("id", "question", "role", "as_of")}).encode()
    request = urllib.request.Request(f"{SERVICE}/ask", body, {"Content-Type": "application/json"})
    start = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=60) as r:
            status = r.status
    except urllib.error.HTTPError as e:
        status = e.code
    return status, time.monotonic() - start


def run(questions, label):
    with ThreadPoolExecutor(12) as pool:
        results = list(pool.map(ask, questions))
    seconds = sorted(s for _, s in results)
    codes = {c: sum(code == c for code, _ in results) for c in sorted({code for code, _ in results})}
    row = {"pass": label, "requests": len(results), "http": codes, "p50_s": round(seconds[len(seconds) // 2], 3),
           "p95_s": round(seconds[int(0.95 * (len(seconds) - 1))], 3), "max_s": round(seconds[-1], 3)}
    print(json.dumps(row))
    return row


if __name__ == "__main__":
    ThreadingHTTPServer.request_queue_size = 128  # the default backlog of 5 drops bursts of retries
    threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", STUB), Stub).serve_forever, daemon=True).start()
    env = {**os.environ, "CORPUS_DIR": str(REF / "corpus"), "LLM_BASE_URL": f"http://127.0.0.1:{STUB}",
           "LLM_API_KEY": "stub", "LLM_TIMEOUT": "8"}
    server = None if os.environ.get("SERVICE_URL") else subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--port", str(PORT), "--log-level", "warning"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        started = time.monotonic()
        while True:  # /healthz answers only once the index is built
            try:
                urllib.request.urlopen(f"{SERVICE}/healthz", timeout=1)
                break
            except OSError:
                if time.monotonic() - started > 60:
                    sys.exit("service did not start")
                time.sleep(0.1)
        ready = round(time.monotonic() - started, 2)
        questions = [json.loads(line) for line in (REF / "questions_dev.jsonl").read_text().splitlines()]
        rows = [{"start_to_healthz_s": ready, "stub_delay_s": DELAY}, run(questions, "stub model healthy")]
        broken = True
        rows.append(run(questions, "stub model returns HTTP 500"))
        assert set(rows[1]["http"]) == {200} and set(rows[2]["http"]) == {200, 503}
        Path(OUT).write_text(json.dumps(rows, indent=2) + "\n")
    finally:
        if server:
            server.terminate()
