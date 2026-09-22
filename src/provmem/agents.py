"""An honest agent: a ledger, a retriever, a reader, and a relay policy."""

from __future__ import annotations

from dataclasses import dataclass

from .ledger import Ledger
from .llm import LLM, Answer, question_for
from .quarantine import QuarantineState, Retraction
from .retrieval import Retrieved, Retriever
from .schema import Claim, Evidence, MemoryEntry
from .verify import Verifier


@dataclass
class Message:
    sender: str
    receiver: str
    entries: list[MemoryEntry]


class Agent:
    def __init__(self, agent_id: str, ledger: Ledger, retriever: Retriever, llm: LLM, rng,
                 verifier: Verifier | None, quarantine: QuarantineState | None) -> None:
        self.id = agent_id
        self.ledger = ledger
        self.retriever = retriever
        self.llm = llm
        self.rng = rng
        self.verifier = verifier
        self.quarantine = quarantine

    def observe(self, claim: Claim, evidence: Evidence, confidence: float, round_: int) -> None:
        self.ledger.add(MemoryEntry(
            uid=self.ledger.next_uid(), content=claim.render(), claim=claim, origin=self.id,
            origin_round=round_, evidence=evidence, confidence=confidence, hop_count=0,
            received_round=round_))

    def receive(self, msg: Message, round_: int) -> None:
        for e in msg.entries:
            self.ledger.add(e.relayed(msg.sender, self.ledger.next_uid(), round_))

    def _handle_refuted(self, e: MemoryEntry) -> None:
        if self.quarantine is not None:
            self.quarantine.on_refuted(self.ledger, e, self.id)

    def relay_batch(self, now: int, share: int) -> list[MemoryEntry]:
        """Sample entries to forward, keeping only those this agent's own retrieval policy
        would accept. Under NAIVE everything is forwarded."""
        pool = [e for e in self.ledger.entries if e.active]
        if not pool:
            return []
        sample = self.rng.sample(pool, min(len(pool), share * 3))
        out: list[MemoryEntry] = []
        for e in sample:
            if len(out) >= share:
                break
            accepted, refuted = self.retriever.judge(self.ledger, e, now, self.id, charge=True)
            if refuted:
                self._handle_refuted(e)
            if accepted:
                out.append(e)
        return out

    def housekeeping(self, now: int, inbox: list[Retraction], audit_budget: int) -> None:
        if self.quarantine is None:
            return
        for r in inbox:
            self.quarantine.on_retraction(self.ledger, r, self.id, self.verifier, now)
        self.quarantine.audit(self.ledger, self.id, self.verifier, now, audit_budget)

    def ask(self, attribute: str, subject: str, now: int, dry: bool = False,
            exclude=None) -> tuple[Answer, Retrieved]:
        question = question_for(attribute, subject)
        got = self.retriever.retrieve(self.ledger, question, now, self.id, dry=dry,
                                      exclude=exclude)
        if not dry:
            for e in got.newly_refuted:
                self._handle_refuted(e)
        return self.llm.answer(question, got.lines), got
