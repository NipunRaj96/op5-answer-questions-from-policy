"""Local pacing proxy for rate-limited provider tiers. Development tooling, not part of the service.

Forwards OpenAI-style POSTs to UPSTREAM_BASE_URL one at a time per model, waits out
tokens-per-minute limits instead of failing, and appends every call's usage to a ledger.
Point LLM_BASE_URL at it:  http://127.0.0.1:$PROXY_PORT
"""
import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

UPSTREAM = os.environ["UPSTREAM_BASE_URL"].rstrip("/")
LEDGER = os.environ.get("LEDGER", "results/raw/ledger.jsonl")
HEADROOM = int(os.environ.get("PROXY_TOKEN_HEADROOM", "3500"))  # tokens that must be free before the next call
MAX_WAIT = float(os.environ.get("PROXY_MAX_WAIT", "90"))  # longest retry-after worth sleeping through
USE_CACHE = os.environ.get("PROXY_CACHE", "1") == "1"
ORG = re.compile(r"org_[a-z0-9]{10,}")  # provider account id in error bodies: keep it out of the ledger
CACHE = Path(".cache/llm")
CACHE.mkdir(parents=True, exist_ok=True)
locks, ready_at, ledger_lock =defaultdict(threading.Lock), defaultdict(float), threading.Lock()


class Proxy(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        model = json.loads(body).get("model", "")
        request = urllib.request.Request(UPSTREAM + self.path, data=body, headers={
            "Content-Type": "application/json", "Authorization": self.headers.get("Authorization", ""),
            "User-Agent": "pacing-proxy/1.0"})
        waited = 0.0
        # Identical request, identical reply: an interrupted run resumes without spending quota twice.
        # Submitted runs must be made with PROXY_CACHE=0 so every answer is freshly generated.
        cached = CACHE / (hashlib.sha256(self.path.encode() + body).hexdigest() + ".json")
        if USE_CACHE and cached.exists():
            return self.reply(200, cached.read_bytes(), model, 0.0, hit=True)
        with locks[model]:
            for _ in range(10):
                pause = max(0.0, ready_at[model] - time.monotonic())
                time.sleep(pause)
                waited += pause
                sent = time.monotonic()
                try:
                    with urllib.request.urlopen(request, timeout=120) as r:
                        status, headers, data = r.status, r.headers, r.read()
                except urllib.error.HTTPError as e:
                    status, headers, data = e.code, e.headers, e.read()
                took = time.monotonic() - sent
                if status == 429:
                    retry = float(headers.get("retry-after") or 10)
                    if retry > MAX_WAIT:  # daily quota, not the per-minute bucket: fail now, never hang
                        break
                    ready_at[model] = time.monotonic() + retry
                    continue
                limit = int(headers.get("x-ratelimit-limit-tokens") or 0)
                remaining = int(headers.get("x-ratelimit-remaining-tokens") or HEADROOM)
                if limit and remaining < HEADROOM:  # the bucket refills at limit/60 tokens per second
                    ready_at[model] = time.monotonic() + (min(HEADROOM, limit) - remaining) / (limit / 60)
                break
        if status == 200 and USE_CACHE:
            cached.write_bytes(data)
        self.reply(status, data, model, waited, took=took)

    def reply(self, status, data, model, waited, hit=False, took=None):
        try:
            usage = json.loads(data).get("usage") or {}
        except ValueError:
            usage = {}
        with ledger_lock, open(LEDGER, "a") as f:
            f.write(json.dumps({"ts": time.time(), "model": model, "status": status, "paced_seconds": round(waited, 2),
                                "upstream_seconds": None if took is None else round(took, 3),
                                "cache_hit": hit, "error": None if status == 200 else ORG.sub("org_REDACTED", data[:400].decode("utf-8", "replace")),
                                "prompt_tokens": usage.get("prompt_tokens"),
                                "completion_tokens": usage.get("completion_tokens")}) + "\n")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("PROXY_PORT", "4010"))), Proxy).serve_forever()
