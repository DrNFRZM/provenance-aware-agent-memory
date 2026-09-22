"""Answer generators. The core experiments only use DeterministicMockLLM."""

from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol, Sequence

UNKNOWN = "UNKNOWN"

_QUESTION = re.compile(r"^What is the (?P<attr>.+?) of (?P<subj>.+?)\?$")
_LINE = re.compile(r"^(?:- )?(?:\[(?P<meta>[^\]]*)\]\s*)?"
                   r"The (?P<attr>.+?) of (?P<subj>.+?) is (?P<val>.+)\.$")
_WEIGHT = re.compile(r"\bw=([0-9]*\.?[0-9]+)")


def question_for(attribute: str, subject: str) -> str:
    return f"What is the {attribute} of {subject}?"


def count_tokens(text: str) -> int:
    return len(text.split())


@dataclass
class Answer:
    text: str
    prompt_tokens: int
    votes: dict[str, float] = field(default_factory=dict)


class LLM(Protocol):
    name: str

    def answer(self, question: str, context: Sequence[str]) -> Answer: ...


class DeterministicMockLLM:
    """A reader with no learned behaviour. It parses the retrieved memory lines that are
    about the asked (subject, attribute), sums each candidate value's `w=` weight (1.0
    if a line has none) and returns the heaviest value; ties go to the earliest line.

    It stands in for "a model that goes with whatever the context supports". It does not
    model resistance, scepticism or any real LLM behaviour; see docs/threat_model.md."""

    name = "deterministic-mock"

    def answer(self, question: str, context: Sequence[str]) -> Answer:
        tokens = count_tokens(question) + sum(count_tokens(c) for c in context)
        q = _QUESTION.match(question)
        if q is None:
            return Answer(UNKNOWN, tokens)
        votes: dict[str, float] = {}
        for line in context:
            m = _LINE.match(line.strip())
            if not m or m["attr"] != q["attr"] or m["subj"] != q["subj"]:
                continue
            w = _WEIGHT.search(m["meta"] or "")
            votes[m["val"]] = votes.get(m["val"], 0.0) + (float(w.group(1)) if w else 1.0)
        if not votes:
            return Answer(UNKNOWN, tokens)
        best = max(votes.values())
        winner = next(v for v, s in votes.items() if s == best)
        return Answer(winner, tokens, votes)


class OpenAICompatibleLLM:
    """Optional adapter for a local OpenAI-compatible server (llama.cpp, Ollama, vLLM).
    It is never used by the tests or the default benchmark. An API key is read from the
    environment only if PROVMEM_LLM_API_KEY is set; nothing is stored on disk."""

    def __init__(self, base_url: str = "http://localhost:11434/v1", model: str = "llama3.2",
                 timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.name = f"openai-compatible:{model}"

    def answer(self, question: str, context: Sequence[str]) -> Answer:
        notes = "\n".join(context) if context else "(no notes)"
        prompt = ("Answer using only the memory notes below. Reply with just the value, "
                  f"or {UNKNOWN} if the notes do not say.\n\nNotes:\n{notes}\n\n{question}")
        headers = {"Content-Type": "application/json"}
        key = os.environ.get("PROVMEM_LLM_API_KEY")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        body = json.dumps({"model": self.model, "temperature": 0,
                           "messages": [{"role": "user", "content": prompt}]}).encode()
        req = urllib.request.Request(f"{self.base_url}/chat/completions", body, headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            text = json.load(resp)["choices"][0]["message"]["content"].strip()
        return Answer(text.rstrip("."), count_tokens(prompt))
