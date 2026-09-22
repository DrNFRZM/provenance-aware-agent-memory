# Interview guide

Twenty-six hard questions about this project and the ideas under it, with the answers I would
give. Where an answer leans on a measurement, the number comes from `results/quick/`
(8 seeds, mock reader); seed-to-seed spreads are descriptive, not confidence intervals.
Where I do not know, the answer says so.

Sections: provenance and trust (1-6), similarity and embeddings (7-10), poisoning (11-14),
false positives and calibration (15-19), overhead (20-21), limits and honesty (22-26).

---

## Provenance and trust

**1. In one sentence, what is your claim?**
In a synthetic multi-agent gossip world, provenance recorded as *metadata* only protects
against an attacker who forges it badly; the protection that held up came from an
independent check and from distrusting an origin after a refutation. That is an empirical
observation about one simulator and a mock reader, not a general result.

**2. What is provenance, precisely, in your schema? Why not just "source"?**
Provenance is what tells you how a claim reached this copy: originating agent, origin round,
evidence kind and reference, source-reported confidence, hop count, the chain of relayers, and
who handed it over. "Source" collapses these. They differ in who can forge them: the receiver
sets `received_from` and the last hop, which are unforgeable under my transport assumption;
everything the originator writes is forgeable. Separating them is what makes the threat model
statable.

**3. Your trust score is a hand-weighted average. Why should anyone believe it?**
They should not believe it as a model of truth. The weights (evidence 5, confidence 2, hop 3,
agreement 6, recency 2) were fixed before running experiments so I could not fit them to the
simulator. It is a transparent baseline that lets me ablate fields. The ablation is the real
content: against a careless fabricator evidence carries the score (dropping it takes false
retrieval from 0.122 to 0.524). Against a forger, the full score fails; agreement alone helps
only while the attacker is limited to one claimed identity. A learned score would need real data
and an adversary in the loop.

**4. Why is a weighted *average* a bad way to combine provenance fields against an adversary?**
An average lets attacker-controlled fields outvote the one hard-to-forge field. Here four
forgeable fields total weight 12 against agreement's 6. Using agreement *alone* dropped
forged_meta false retrieval to 0.053 with zero acceptance of injected entries, but the full
score left it at 0.711. In a worst-case setting you want a conjunction or a min over
unforgeable checks, not a mean over everything.

**5. What did "hop count" actually buy?**
Very little, and at a price. Cutting off beyond one relay reduced forged_meta ASR from 0.247 to
0.189, but rejected 10.4% of true entries in the control (clean accuracy about 3.6 points
lower). Cut-offs at two or more relays changed little in these eight runs. The intuition (older
relays are less reliable) is fine, but it penalises honest information exactly as much as
false, and the attacker can claim hop 0.

**6. What is the difference between independent verification and trusting evidence?**
Evidence is a claim *about* support ("see document 17"). Verification obtains the support
from somewhere the claimant does not control. In my forged_meta tier the forger cites a real
document id and passes every evidence check; only the archive lookup catches it. So the
security value of strategy 4 is entirely in the archive, and depends on coverage (0.5 by
default), correctness and independence from the attacker.

## Similarity and embeddings

**7. Why does similarity retrieval fail here? Is that an embedder problem?**
Not primarily. In the hashing representation, a query about a fact is about as close to a false
claim about that fact as to the true one because they differ only in the value;
`test_similarity_cannot_tell_true_from_false_value` checks that the gap is under 0.15 cosine.
A better embedder could change the ranking and measured rates, but similarity still represents
relevance rather than factual support. Truth needs another signal.

**8. Your embedder is hashing, not semantic. Doesn't that invalidate the results?**
It limits them. Reproducibility with no model download was the goal, and this hashing embedder has
the property I needed: near-equal similarity for true and false claims on the same fact. I expect,
but have not demonstrated, similar ambiguity with a semantic embedder. Its lexical nature
affects ranking noise: an early version ranked by `similarity * trust` and
let trusted entries about the wrong fact outrank the right one, because same-attribute facts
were about 0.6 similar to the query against 0.8 for the target. With a sharper embedder that
artefact may shrink. I have not run `SentenceTransformerEmbedder` through the benchmark.

**9. Could an attacker win retrieval by crafting text that is more similar to the query?**
In a real system, yes, and it is a separate attack class (retrieval-ranking manipulation). My
attacker writes the same rendered sentence as an honest one, so it cannot beat honest entries
on similarity, only tie. I do not model embedding-space attacks. If the attacker could win
similarity, trust gating with over-fetch (pool 4k) becomes less reliable, since the pool itself
could be filled with attacker text.

**10. Why gate on trust instead of ranking by similarity times trust?**
I tried ranking first and it hurt: trust from other facts' entries reordered results. Gating
keeps similarity as the relevance signal and uses trust as a filter and as the reader's vote
weight. The cost is over-fetching a pool and possibly returning fewer than k lines (the reader
may abstain). `rank="product"` is still an option; I have not benchmarked it.

## Poisoning

**11. How is this different from RAG corpus poisoning?**
The entry point differs: here the false claim arrives *through an agent's memory or relay*,
with provenance the writer chose, and it spreads because honest agents forward what they hold.
Corpus poisoning attacks a static index. The shared piece is that retrieval cannot tell them
apart by similarity. The extra piece here is propagation: whether honest agents become vectors.

**12. What does your propagation metric measure, and why did you change it?**
`propagation_final` counts (agent, target) slots whose stored false copy came from *another
honest agent*, that is, spread that needed honest relaying. My first attacker pushed every
round, so every agent got a direct copy and honest relays were deduplicated against it;
"secondary" propagation was 0.00 for every strategy. Now the attacker injects once to two seed
agents and anything else must travel through honest relays. Result: naive 0.425, provenance
0.000 against a plain fabricator, and provenance 0.425 against forged_meta (no change), quarantine 0.046.

**13. Your sybil tier beats the provenance strategy. Isn't that just a straw man?**
It is a stress test of one design choice: agreement is the highest-weighted field, and it
counts distinct origin identities. If identities are free to mint, distinct-origin counting
is not evidence of independence. It was 3 fabricated origins against 2 honest sources, so the
outcome (0.515 versus 0.457 for naive) partly reflects that ratio. The general point stands:
agreement is only as good as the cost of creating identities.

**14. Your evasive attacker defeats everything. What's the takeaway?**
That verification coverage is a security boundary. An attacker who knows which facts are
uncoverable gets ASR 0.48 to 0.55 against every strategy. It assumes the attacker knows coverage,
which may be unrealistic, but it removes any impression that the quarantine result generalises
beyond facts the system can check. The defence is to raise coverage or to weight
unverifiable facts more sceptically, which I did not test.

## False positives and calibration

**15. How do you define a false positive and a false negative here?**
On final ledgers, every entry is either true-valued or false-valued. A false positive is a
true-valued entry the policy would reject; a false negative is a false-valued (or injected)
entry it would accept. Computed by the same acceptance rule used for relaying, ignoring top-k. At
the default threshold true entries rejected were 0.000 to 0.003 in the control, and injected
entries accepted were 1.000 (naive, confidence, provenance under forged_meta), 0.736 (verified),
0.114 (quarantine).

**16. Where do false positives actually hurt?**
Three places. A high threshold: provenance at 0.65 rejected 4.2% of true entries and dropped
clean accuracy to 0.868; at 0.8 clean accuracy was 0.386 and the reader abstained 61.6% of the
time, which "defends" by not answering. A noisy verifier: with 10% verdict error, quarantine
clean accuracy fell from 0.939 to 0.840 and rejection rose from 0.030 to 0.181, because the
cascade turns each wrong refutation into distrust of an honest origin. And impersonation:
under forged_meta quarantine rejected 3.0% of true entries versus 0.3% in the control.

**17. Is your trust score calibrated?**
No, and I did not measure it. It is a score that orders entries, compared to a threshold I
set. Calibration would mean that among entries with T = 0.7, about 70% are true; I have no
reason to think so and did not test it. The threshold sweeps are a substitute: they show the
operating curve directly without pretending the number is a probability.

**18. What is the difference between source confidence and model confidence?**
Source confidence is a number an originator attaches to a claim it makes. It is a statement,
so an attacker can write any value (my forgers wrote 0.90 and 0.99, honest agents 0.70 to
0.95). Model confidence is the reader model's own uncertainty over its answer (token
probabilities or a stated estimate). Only the latter can be calibrated against outcomes, and
even it says nothing about whether the memory it read was true. The confidence strategy was the
worst in the first three attack tiers (0.208, 0.268, 0.523 ASR) and a 0.8 confidence threshold pushed forged_meta
ASR to 0.556, from 0.268, by discarding honest entries and keeping the attacker's 0.99.

**19. Would learning per-origin reliability fix this?**
It helps against an origin that lies repeatedly and cannot be Sybil-ed, and my quarantine
cascade is a crude version (two refutations from an origin quarantine its unverified entries).
Its failure modes are known: cold start, an attacker who builds reputation on covered facts and
spends it on uncovered ones, and identity minting. I did not implement or test a learned
version; the roadmap lists it.

## Computational overhead

**20. What does it cost?**
Per query, with k = 3 and no attack: context grows from 36.7 to 51.7 whitespace tokens (1.41x)
with provenance annotations, 54.7 (1.49x) with verification state. Candidates scored per
query go from 3 to 12 (pool of 4k). Verification costs about 196 archive lookups per 700 queries
(0.28 per query) at 50% coverage, growing about linearly with agents (roughly 200 at 6, 625 at 16).
Quarantine adds 18% to 21% more messages in forged_meta runs and 43% in sybil, from retraction
broadcasts. I did not measure wall-clock.

**21. Is that overhead worth it?**
I did not measure wall-clock time or the cost of a real verifier, so I cannot make that claim.
The measured token cost comes from annotations; if the reader ignores them, that cost buys
nothing, which I cannot test with a mock. Verification is where the security value came from,
so a deployment question is how to spend those lookups where expected value is highest:
conflicted claims first, as the audit does.

## Limits and honesty

**22. Can provenance itself be falsified?**
Yes; that is the central design fact. Everything the originator writes can be forged:
origin, round, evidence, confidence, claimed hop count. My tiers escalate from a nonexistent
citation to a valid one plus impersonation to fabricated identities. Making provenance
unforgeable needs machinery I do not implement: signatures over content and metadata,
attested writers, or a trusted memory API. I assume the transport reports the true sender
(`received_from`). If that fails, hop counts and propagation tracking fail too.

**23. Why should I trust a mock LLM result?**
You should trust it for what it is: a controlled reader that isolates retrieval. It obeys
the `w=` annotation exactly, cannot be argued with and has no priors, so it is favourable to
provenance-aware prompts in one way and unrealistic in others. A real model may ignore weights,
be swayed by fluent false text, or notice conflicts. I would not transfer any number from here
to a deployed system.

**24. Your quarantine result looks strong. What are you not telling me?**
Four things. The verifier is an oracle. Coverage is global, so every recipient can refute the
same claims and the retraction mechanism did nothing (outputs identical without it; that is
structural, not evidence that retractions are useless). The cascade gets nearly all the gain
(no-cascade ASR 0.145 against 0.071 in forged_meta), needs at least two refutations from one
origin, and did nothing at coverage 0.25. And it fails against the evasive attacker (0.552).

**25. How should I describe uncertainty in these results?**
Descriptively. There are eight paired seeds, and `summary.csv` reports sample standard deviations,
not confidence intervals. For forged metadata, the provenance-minus-naive ASR difference is
+0.110 ± 0.043 across seeds and is positive in all eight. That is consistent within this
simulator, but the seeds are not independent observations of real agent systems, so I make no
population-level claim. Seeds 1000+ were not used for a design decision, but I did inspect seeds
0 and 1 during development and chose gossip volume from seeds 0 to 3, so even that guard is weak.

**26. If you had two more weeks, what would you do first, and what would change your mind?**
First, put a real open-weights model behind `OpenAICompatibleLLM` with and without the
provenance annotations, since that decides whether the metadata is useful to a model or only to
my filter. Second, sign entries and rerun the forged and sybil tiers. Third, replace the oracle
verifier with a noisy attacker-correlated one. I would revise the conclusion if a real reader
made annotations *more* effective than my filter (metadata matters more than I found) or if
noise in a realistic verifier erased the quarantine advantage (the main positive result was
fragile).
