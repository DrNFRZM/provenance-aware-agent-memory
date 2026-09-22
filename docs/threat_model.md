# Threat model

This is a defensive study of one narrow failure mode: **an unreliable peer writes a false
claim into a shared or relayed memory, and other agents later retrieve it as if it were
trustworthy.** The point is to measure whether recording and using provenance changes that.

## Scope and safety statement

* Every fact is invented: fictional stations, planets and guilds with syllable-generated
  names, and attribute values drawn from generated pools ("lead researcher", "orbital
  period", "primary instrument"). A false claim is another value from the same pool.
* Nothing models real people, real organisations, real vulnerabilities, or instructions
  that could cause harm. There are no exploits, payloads, prompt-injection strings, or
  network attacks in the repository.
* The adversary is a *behavioural model inside a simulation*. It cannot touch anything
  outside the process.

## What is being protected

An agent's answer to a factual question that its memory can, in principle, support
correctly. The property of interest is *integrity of retrieved context*, not
confidentiality or availability.

## System and trust assumptions

| # | assumption | why it is made | what breaks if false |
|---|---|---|---|
| A1 | Claim extraction (free text -> subject/attribute/value) is accurate | isolates memory effects from parsing errors | agreement and indexing become unreliable |
| A2 | `received_from` is the true immediate sender (transport identity is unforgeable) | needed for hop counting and for the secondary-propagation metric | attacker can hide the injection path |
| A3 | Each agent's own ledger and verification state is not tampered with | local state is the trust anchor | a compromised host defeats everything here |
| A4 | The verifier archive is correct for the facts it covers and independent of the agents | this is what "independent verification" means | a poisoned archive turns the strongest defence into the strongest attack |
| A5 | The attacker knows the metadata format and the public document catalogue | conservative; security by obscurity is not assumed | none (it is the safe assumption) |
| A6 | Honest agents make occasional honest errors (2%) with normal-looking metadata | prevents "everything wrong is an attack" | detection numbers would look better than they should |

## Adversary tiers (the `FaultMode`s)

All tiers inject coordinated false claims about a few targeted facts in a single burst to
a few seed agents. Any spread beyond the seeds happens through honest relaying, which is
what `propagation_final` measures.

| tier | mode | what the adversary controls | what it cannot control |
|---|---|---|---|
| T0 | `none` | nothing (silent peers; matched control population) | - |
| T1 | `plain` | content, confidence 0.90, evidence *kind*; cites a document that does not exist | it cannot make a nonexistent document resolve |
| T2 | `forged_meta` | T1 plus: cites the **real** catalogue id, confidence 0.99, claimed hop 0, impersonates an honest agent as `origin` | the claim's content is still not supported by the archive |
| T3 | `sybil` | T2 plus several fabricated origin identities to fake independent agreement | same |
| T4 | `sybil_evasive` | T3 plus it targets only facts the verifier does not cover (assumes knowledge of verifier coverage) | nothing stops it on uncovered facts; this is a *limit* test |

T4 is undefined when fewer than the requested number of uncovered facts exist. The simulator
rejects that configuration instead of silently attacking covered facts; accordingly, the coverage
sweep stops at 0.75 for `sybil_evasive` and does not report a misleading 1.0-coverage point.

Collusion is also modelled by raising the number of faulty agents (`n_faulty`); colluders
share the same false value, and in `forged_meta` each impersonates a different honest agent.

## Security reasoning per strategy

**1. Naive similarity.** Similarity is computed from text. A false claim about a fact is,
by construction, about as similar to a query about that fact as the true claim is (the test
`test_similarity_cannot_tell_true_from_false_value` pins this). Retrieval therefore cannot
separate them, and whichever the reader prefers wins. This is the baseline vulnerability,
not a defect of any particular embedder.

**2. Similarity + confidence.** Confidence is asserted by the source. An attacker sets it
higher than any honest value. The strategy can therefore *increase* attack success
(expected under T2/T3; measured in the research note). Confidence is only informative if it
is calibrated *and* unforgeable.

**3. Provenance-aware.** Uses evidence resolvability, hop distance, cross-origin agreement
and recency. Sound against T1 because a citation that does not resolve is a cheap,
attacker-uncontrollable signal. Weak against T2 because every field it reads can be copied
from an honest entry. Against T3 it is worse than useless when fabricated origins
outnumber honest ones, because agreement is *the* highest-weighted field and is exactly
what a sybil inflates.

**4. Provenance + independent verification.** Adds a check whose answer the attacker does
not control. The security value comes entirely from where the verifier's answer comes from,
not from the provenance fields. Limits: coverage (uncovered facts stay unverified), verifier
noise, and cost per lookup. T4 defeats it by choosing facts outside coverage.

**5. Quarantine and repair.** Turns each refutation into evidence about the *origin* and
about *peers*: the refuted claim is hidden, the origin's other unverified entries are
quarantined, and peers are told. This can generalise a few covered detections into
protection for uncovered facts, provided the attacker reuses an origin identity across
facts. Costs: (a) impersonation turns the cascade into a framing attack, because the
"origin" that gets punished is an honest agent; (b) retractions are themselves messages an
attacker could forge (not modelled; see below); (c) a real system needs an appeals path.

## Can provenance itself be falsified?

Yes, and the design assumes it. In the schema table (`docs/memory_model.md`) only
receiver-side fields are trusted. The tiers above are ordered by how much provenance the
attacker forges. The consistent finding to look for in the results is that *provenance
that the attacker can write does not add security beyond what an unforgeable check adds*;
what it does add is a cheap way to discount lazy attackers (T1) and to decide where to spend
the expensive checks.

Unforgeable provenance in practice needs a mechanism this project does not implement:
cryptographic signatures over content and metadata by a key the attacker does not hold,
transparency logs, or a trusted execution boundary around the memory writer. The
simulation stands in for such a mechanism with the `received_from` assumption (A2) and the
verifier archive (A4).

## Out of scope (not modelled)

* **False retractions** (an adversary sending retractions to suppress true claims) and other
  attacks on the repair channel. The quorum rule is a mitigation that is not attacked here.
* **Compromised or poisoned verifier archive.**
* **Adaptive attackers** who probe the threshold. Only one adaptation is modelled (T4:
  target uncovered facts).
* **Embedding-space attacks** (crafting text to win similarity for unrelated queries).
* **Prompt-injection or instruction-bearing memories.** Claims here are inert facts.
* **Real LLM behaviour.** The reader is a deterministic mock. It cannot be talked into
  anything, ignore a warning, or hedge; real models can do all three.
* **Privacy, availability and cost-of-service attacks** on the memory store.
* **Claim-extraction errors and value normalisation** (A1).
* **Non-stationary truth.** Facts never change, so "old but true" and "new but false" are
  never in tension. Recency is therefore probably under-tested.

## What a positive result would and would not show

It would show that, in a synthetic setting where claim structure and sender identity are
given, provenance fields plus an independent check change what a simple reader retrieves and
answers, and by how much per unit of overhead. It would *not* show that a deployed agent
with a real LLM, free-text memory and an attacker who can write memory directly is safe.
