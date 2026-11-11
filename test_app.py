"""Smallest checks that fail if the safety logic breaks. Run: python test_app.py (no API key needed)."""
import json
import os
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

import app

CORPUS_DIR = os.environ.get("CORPUS_DIR", "../hiring-problems/references/OP-05/corpus")
CORPUS = app.Corpus(CORPUS_DIR)
RESTRICTED = "What is the permitted range for a hardship plan term?"  # lives in the ops-only Harbour policy


class FakeLLM:
    def __init__(self, reply=None, fail=False, missing=None):
        self.reply, self.fail, self.prompts, self.models, self.missing = reply, fail, [], [], missing
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, messages, model=None, **_):
        self.prompts.append(messages[-1]["content"])
        self.models.append(model)
        if model == self.missing:
            raise type("NotFoundError", (Exception,), {})("no such model")
        if self.fail:
            raise TimeoutError("upstream down")
        return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
                               choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(self.reply)))])


def test():
    # Role-blocked: refused as "not permitted", no citation, and the model is never called.
    fake = FakeLLM()
    body, _ = app.answer(CORPUS, RESTRICTED, "public", client=fake)
    assert body["status"] == "not_permitted" and body["citations"] == [] and not fake.prompts

    # No restricted passage text ever enters a prompt for a lower role.
    restricted = [p["text"] for p, lvl in zip(CORPUS.passages, CORPUS.level) if lvl > 0]
    fake = FakeLLM({"status": "not_in_corpus"})
    for question in ("What must an AMC board of directors contain?", "auction of state government securities"):
        app.answer(CORPUS, question, "public", client=fake)
    assert not any(text in prompt for prompt in fake.prompts for text in restricted)

    # A quote the model invented is replaced by verbatim passage text.
    fake = FakeLLM({"status": "answered", "answer": "One to six months.", "passage": 1, "quote": "made up words"})
    body, meta = app.answer(CORPUS, RESTRICTED, "ops", client=fake)
    cite = body["citations"][0]
    passage = next(p for p in CORPUS.passages if p["passage_id"] == cite["section"])
    assert meta["quote_repaired"] and app.norm(cite["quote"]) in app.norm(passage["text"])

    # An answer that repeats 12+ consecutive words of a restricted document is withheld.
    stolen = " ".join(restricted[5].split()[:20])
    fake = FakeLLM({"status": "answered", "answer": stolen, "passage": 1, "quote": "x"})
    body, meta = app.answer(CORPUS, "What must an AMC board of directors contain?", "public", client=fake)
    assert body["status"] != "answered" and body["citations"] == [] and stolen not in body["answer"]

    # A weak match on a restricted passage is "nothing found", not "not permitted".
    body, _ = app.answer(CORPUS, "What stamp duty is payable on the transfer of mutual fund units between investors?",
                         "public", client=FakeLLM(fail=True))
    assert body["status"] == "not_in_corpus"

    # Garbage or an outage from the model becomes a refusal with no citation, never a crash.
    for fake in (FakeLLM(fail=True), FakeLLM({"status": "answered", "answer": "x", "passage": 99})):
        body, meta = app.answer(CORPUS, RESTRICTED, "ops", client=fake)
        assert body["status"] == "not_in_corpus" and body["citations"] == [] and "error" in meta
    # A gateway that does not serve the configured model: switch to the reference model, once.
    fake = FakeLLM({"status": "answered", "answer": "x", "passage": 1, "quote": "x"}, missing=app.MODEL)
    body, meta = app.answer(CORPUS, RESTRICTED, "ops", client=fake)
    assert body["status"] == "answered" and fake.models == [app.MODEL, app.FALLBACK_MODEL] and "error" not in meta
    app.answer(CORPUS, RESTRICTED, "ops", client=fake)
    assert fake.models[2:] == [app.FALLBACK_MODEL] and meta["model"] == app.FALLBACK_MODEL
    app.active["model"] = app.MODEL

    # Freshness: a superseding version replaces the old one from its effective date, not before,
    # and stays behind the same role wall. Built the way the update pack is: a revised CORPUS_DIR.
    with tempfile.TemporaryDirectory() as tmp:
        new = Path(shutil.copytree(CORPUS_DIR, Path(tmp) / "corpus"))
        old_id, new_id = "HARBOUR_internal_servicing_policy", "HARBOUR_internal_servicing_policy_v2"
        with open(new / "passages.jsonl", "a") as f:
            for p in CORPUS.passages:
                if p["doc_id"] == old_id:
                    f.write(json.dumps({"passage_id": p["passage_id"].replace(old_id, new_id), "doc_id": new_id,
                                        "text": p["text"].replace("six whole months", "nine whole months")}) + "\n")
        # No text file for v2, and one passage from a document the manifest does not list:
        # the service must still start, and must not serve the orphan.
        with open(new / "passages.jsonl", "a") as f:
            f.write(json.dumps({"passage_id": "GHOST#s1", "doc_id": "GHOST", "text": "hardship plan loan on the book ghost rule"}) + "\n")
        with open(new / "manifest.jsonl", "a") as f:
            f.write(json.dumps({**CORPUS.docs[old_id], "doc_id": new_id, "effective_date": "2027-01-01",
                                "supersedes": [old_id], "text_path": "text/v2.txt"}) + "\n")
        updated = app.Corpus(str(new))
        assert all(p["doc_id"] != "GHOST" for p in updated.passages)
        question = "How long must a loan be on the book before a hardship plan can be applied?"
        for as_of, now, gone in (("2026-06-01", "six whole months", "nine whole months"),
                                 ("2031-01-01", "nine whole months", "six whole months")):
            fake = FakeLLM({"status": "answered", "answer": "x", "passage": 1, "quote": "x"})
            body, _ = app.answer(updated, question, "ops", as_of, client=fake)
            assert now in fake.prompts[0] and gone not in fake.prompts[0], as_of
            assert (body["citations"][0]["doc_id"] == new_id) == (as_of > "2027")
        body, _ = app.answer(updated, question, "public", "2031-01-01", client=FakeLLM(fail=True))
        assert body["status"] == "not_permitted" and body["citations"] == []
    print("ok")


if __name__ == "__main__":
    test()
