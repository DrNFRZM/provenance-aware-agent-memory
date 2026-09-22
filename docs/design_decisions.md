# Design decisions

Each entry: the decision, why, and what it costs. Items marked **(found by running it)**
came from a bug or a confound observed during development, not from planning.

## Scope

**Small simulation, not an agent framework.** About 1,500 non-blank lines of package code, no agent
loop library, no vector database. The question is about what retrieval selects and what
the reader does with it; a framework would add surface without adding validity.

**Dataclasses, not Pydantic.** The schema needs validation of three invariants
(confidence range, non-negative hop, content equals claim). `__post_init__` covers that
and keeps the dependency set to numpy, pandas and matplotlib.

**Structured claims next to free-text `content`.** Indexing and agreement need
(subject, attribute, value). Real memories are text. The gap is assumption A1 in the
threat model.

## Retrieval

**Hashing embedder by default.** Bit-for-bit reproducibility with no model download. Its
lexical nature is a limitation, but the property the study needs (a query is about equally
close to true and false claims about the same fact) holds for this embedder and is pinned by
a test. A semantic embedder may change the candidate ranking and must be measured rather than
assumed. `SentenceTransformerEmbedder` is an optional drop-in; it has not been run through
the benchmark.

**Trust gates and weights; similarity ranks. (found by running it)** First version ranked by
`similarity * trust`. In an early single-seed smoke run the verifying strategies scored
clean accuracy 0.90 and 0.69 versus 0.98 for naive in a no-attack scenario, even though
almost no true entries were being rejected. The cause appeared to be ranking: with a lexical
embedder the similarity gap between the asked fact (about 0.8) and same-attribute facts
about other subjects (about 0.6) is small, so a high-trust entry about the wrong fact
could beat a modest-trust entry about the right one. Trust now filters and weights the
reader's vote, and `rank="product"` remains available. After the change, a later single-seed
smoke run showed all five strategies within a few points of each other in the no-attack scenario
(0.88 to 0.90). No number in the results uses the old ranking, and `rank="product"` has not been
benchmarked.

**Over-fetch then filter.** The pool is `4k`. If most pool entries are rejected, the reader
sees fewer than `k` lines, and may abstain. That is a real cost of gating and shows up as
`clean_unknown_final`.

**Verification is lazy and cached.** Only pool entries are verified, once per entry.
This is why verifier lookups are a countable overhead metric rather than a constant.

## Trust score

**Weighted mean of five components with hand-set weights.** Weights (5, 2, 3, 6, 2) were fixed
before any experiment. Fitting them on the same simulator would mostly measure how well the
simulator can be overfit. The ablation experiment shows which fields matter under each
adversary, which is the more honest way to present sensitivity.

**Agreement counts distinct origins, not copies.** Otherwise gossip inflates the agreement
of whatever spreads fastest, including falsehood.

**Verification is a state adjustment and a hard gate, not one more weighted field.** A refuted
claim should not be rescuable by a high evidence score.

## Simulation

**Matched control (found by running it).** First version had `fault=None` meaning "no extra
peers". Honest-population size and message loss then differed between control and attack
runs, and naive clean accuracy differed by 20 points for a reason unrelated to the attack.
`FaultMode.NONE` keeps the same silent peer slots so that clean-accuracy comparisons are
paired.

**Single injection burst (found by running it).** With the attacker pushing every round,
every honest agent got a direct copy of every false claim. Later honest relays were
deduplicated against that direct copy, so "secondary" propagation measured 0.00 for every
strategy including naive. Now the attacker pushes once to `push_fanout` seed agents and
anything beyond them must travel through honest relaying. Exposure and propagation are
reported separately.

**Relay decisions use the sender's own retrieval policy.** Defended agents stop forwarding
what they would not retrieve. This is where propagation is actually reduced; retrieval-time
filtering alone would leave false entries sitting in every ledger.

**Answer-flip via counterfactual retrieval.** Attack success rate says "wrong answer".
Flip rate says "wrong answer that would have been right without the false entries about that
fact", which is the closer analogue of "the injected claim changed the answer". The
counterfactual retrieval is side-effect free (`dry=True`).

**FP/FN are computed on ledgers, not queries.** `judge` applies the acceptance rule to every
stored entry at the last round. It ignores top-k truncation, so it is the property of the
policy, not of one query.

**Recovery is censored, not imputed.** If ASR never returns to <= 0.05, `recovered = 0` and
`recovery_rounds` is set to the observable horizon. Read the two columns together.

**Process determinism.** All randomness is `random.Random` seeded from a blake2b digest of
(seed, label). Python's salted `hash()` is never used, sets are not iterated to make
decisions, and the parallel runner preserves job order. A test checks identical output for
1 and 2 workers, and byte-identical CSVs across invocations.

**Held-out evaluation seeds.** Development and tests used seeds below 1000. Reported runs use
1000 and above. This is a weak guard (the simulator is small, and I saw several strategies'
outputs on seeds 0 and 1 while developing), but it keeps the reported seeds out of every
design choice made here. The one calibration made against data, gossip volume (10 entries
per message, fanout 3), was chosen from no-attack naive clean accuracy on seeds 0 to 3.

## Reader

**Deterministic mock, weighted plurality.** It makes the study a study of retrieval.
It also flatters provenance-aware strategies, since it obeys `w=` perfectly and a real model
might not, and it never gets talked into anything. The limitation is repeated in the
research note because it is the biggest one.

**Optional local adapter.** `OpenAICompatibleLLM` speaks to a local OpenAI-compatible
endpoint using only the standard library. It is untested against a live server, not used in
any reported number, and never required.

## Things deliberately not built

Cryptographic provenance, a learned trust model, confidence calibration, time-varying
facts, LLM-based claim extraction, and retraction attacks. Each is discussed as a limit in
the research note rather than half-implemented.
