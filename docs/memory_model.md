# Memory model

This file is the contract between `src/provmem/schema.py`, `scoring.py`, `retrieval.py`
and the experiments. If code and this document disagree, that is a bug in one of them.

## 1. The memory entry

An entry is one agent's stored copy of one claim. Two agents that hold "the same" fact
hold two entries.

| field | type | meaning | who sets it | can a peer forge it? |
|---|---|---|---|---|
| `uid` | str | local id, `"<owner>#<n>"` | owner ledger | irrelevant |
| `content` | str | the text a reader sees; must equal `claim.render()` | originator | yes (it is the payload) |
| `claim` | (subject, attribute, value) | structured form used for indexing and agreement | originator | yes |
| `origin` | str | the agent that first asserted the claim | originator | **yes** (impersonation, fabricated identities) |
| `origin_round` | int | round of first assertion | originator | yes |
| `evidence.kind` | document / observation / hearsay / none | what the originator says supports the claim | originator | yes |
| `evidence.ref` | str | e.g. a document id | originator | yes, but see below |
| `confidence` | float in [0,1] | **source-reported** assertion strength | originator | yes |
| `hop_count` | int >= 0 | relays between origin and this copy, as claimed, plus one per receipt | claimed by sender, +1 by receiver | the claimed part, yes |
| `received_from` | agent id or None | who handed this copy over | receiver (transport) | **no**, by assumption |
| `received_round` | int | round this copy was stored | receiver | no |
| `lineage` | tuple of agent ids | relayers, in order, as claimed + receiver-appended sender | sender/receiver | earlier part yes, last hop no |
| `verification` | unverified / verified / refuted / quarantined | local verification state | receiver | no (never copied between agents) |
| `verified_round` | int or None | when the verdict was obtained; None means never checked | receiver | no |
| `trust_score` | float or None | last trust computed **by this agent**; agent-local | receiver | no |
| `parent` | uid or None | the sender's entry this was copied from | receiver | no |

Design consequences:

* Only `received_from`, `received_round`, the last element of `lineage`, and the receiver-local
  state (`verification`, `verified_round`, `trust_score`) are assumed trustworthy. Everything
  the originator wrote can be falsified. `docs/threat_model.md` shows how far that matters.
* `confidence` is the originator's *stated* certainty. It is not a calibrated probability
  and it is not the reader model's certainty about its own answer (see
  `docs/interview_guide.md`).
* Relaying copies provenance fields unchanged and adds a hop. It never copies verification
  or trust state; each agent decides for itself.
* A ledger stores at most one copy per `(origin, subject, attribute, value)`. If a copy
  arrives over a shorter path, the stored copy adopts the shorter path.

JSON Lines is the on-disk format (`dump_jsonl` / `load_jsonl`), one entry per line with
sorted keys, so serialisation is byte-stable.

## 2. Trust score (provenance)

For an entry `e` held by agent `a` at round `now`, with `P` the active entries in `a`'s
ledger about the same `(subject, attribute)`:

```
T_prov(e) = sum_f  w_f * x_f(e)  /  sum_f w_f          over enabled fields f
```

| field `f` | weight `w_f` | component `x_f(e)` in [0,1] |
|---|---|---|
| evidence | 5 | DOCUMENT whose `ref` resolves in the public catalogue **to this claim's fact**: 1.0. DOCUMENT with unresolvable or mismatched ref: 0.1. OBSERVATION: 0.7. HEARSAY: 0.3. NONE: 0.2 |
| confidence | 2 | `e.confidence` |
| hop | 3 | `gamma ** e.hop_count`, gamma = 0.85 |
| agreement | 6 | `share * (1 - 0.5 ** S)`, where S = number of distinct origins in `P` asserting `e`'s value and `share = S / (sum over values of distinct origins asserting that value)` |
| recency | 2 | `0.5 ** ((now - origin_round) / 8)` |

The weights are relative and were fixed before any experiment was run. They are a
hand-set prior, not a fitted model. Ablations set a field's weight to 0 (`without`) or
every other weight to 0 (`only`).

Agreement counts *distinct origin identities*, not copies: four relayed copies of one
origin's claim count once. It is also the only component that depends on other entries,
and the only one an attacker can inflate with fabricated identities (see `sybil`).

### Verification adjustment (strategies 4 and 5 only)

```
verified     : T = T_prov + (1 - T_prov) * 0.7
unverified   : T = T_prov
refuted      : hard reject (T = 0, excluded at any threshold)
quarantined  : hard reject
```

The verifier looks a claim up in a reference archive that is independent of the agents.
It covers a fraction `coverage` of facts; uncovered facts stay `unverified`. With
probability `noise` a covered verdict is flipped. Only lookups that reach the archive count
toward `verifier_lookups`; each entry is checked at most once (the verdict is cached).

## 3. Retrieval

`query -> Retrieved(entries, trusts, lines)`

1. Embed the query; compute cosine similarity to every **active** (non-quarantined) entry.
2. Naive: take the top `k`, done.
3. Otherwise take a candidate pool of the top `pool_factor * k` (default 4k) by similarity.
4. For each pool entry compute the strategy's trust `T` (table below). Entries with
   `hop_count > max_hops` (if set) and refuted/quarantined entries are hard-rejected.
5. Drop entries with `T < threshold` (default 0.5).
6. Rank survivors by similarity (default) or by `similarity * T` (`rank="product"`), take `k`.
7. Render each entry as a line for the reader; the trust value is passed as `w=`.

| # | strategy | trust `T` | provenance shown to the reader | extra machinery |
|---|---|---|---|---|
| 1 | `naive` | none (similarity only) | none | none |
| 2 | `confidence` | `e.confidence` | `w` | none |
| 3 | `provenance` | `T_prov` | `w origin hop ev conf` | none |
| 4 | `verified` | `T_prov` + verification adjustment | adds `ver` | lazy verification of pool entries |
| 5 | `quarantine` | as 4 | as 4 | quarantine, origin-suspicion cascade, retractions with quorum, periodic audit |

Example rendered line for strategy 4:

```
- [w=0.78 origin=A2 hop=1 ev=document conf=0.86 ver=unverified] The lead researcher of Xoraethum Station is Ilsa Voren.
```

### Why trust gates instead of ranking

The first implementation ranked by `similarity * T`. With a lexical embedder the margin
between a relevant and an irrelevant entry is small (about 0.8 versus 0.6 cosine in this
world), so a high-trust entry about a *different* fact could outrank a lower-trust entry
about the asked fact. Trust is therefore a gate and a reader weight by default, and
`rank="product"` is kept as an option. See `docs/design_decisions.md`.

### Acceptance (`Retriever.judge`)

The same trust and gates, without similarity or top-k, define whether an entry is
"accepted". It is used (a) to decide which entries an agent will relay to peers and (b) to
compute false-positive rejection and false-negative acceptance over final ledgers.

## 4. The reader

`DeterministicMockLLM` parses the retrieved lines that match the asked
(subject, attribute), sums `w` per candidate value (1.0 when a line carries no `w`), and
answers with the heaviest value; ties go to the earliest line; no matching line gives
`UNKNOWN`. It has no learned behaviour. It exists so that differences between strategies
are attributable to *what was retrieved*, not to a model's mood. It is also the largest
external-validity gap in the study; see `docs/research_note.md`.

## 5. Quarantine and repair (strategy 5)

* **Refutation -> quarantine.** A refuted entry is hidden from retrieval and relaying.
* **Origin-suspicion cascade.** When one origin has been refuted on `suspicion_limit`
  (default 2) different facts, all its other entries that are not `verified` are
  quarantined. This is a blast-radius control. It also creates collateral damage if the
  origin field was impersonated (measured, see the research note).
* **Retractions.** An agent that quarantines a claim tells its peers. A receiver
  quarantines matching entries if it can itself refute them, or if `retraction_quorum`
  (default 2) distinct peers retracted the same claim and it cannot verify the entry as true.
* **Audit.** Each round an agent spends up to `audit_budget` (default 6) verifier lookups
  on unchecked entries, claims with conflicting values first.

## 6. Metrics

Definitions are exact; every CSV column maps to one.

| metric | definition |
|---|---|
| `asr_*` (attack success rate) | fraction of (honest agent, targeted fact) answers that are a **false value** (an `UNKNOWN` is not counted) |
| `false_retrieval_rate` | fraction of targeted queries, in rounds at/after injection, where at least one false entry about the asked fact was in the retrieved context |
| `answer_flip_rate` | fraction of targeted queries where the answer was false **and** a counterfactual retrieval that excludes false entries about that fact would have answered correctly |
| `exposure_final` | fraction of (honest agent, target) slots holding an active injected false entry at the last round |
| `propagation_final` | as exposure, but only counting slots whose stored false copy was received from another honest agent (spread that needed honest relaying) |
| `clean_accuracy_*` | correctness on non-targeted probe facts; `clean_unknown_final` is the abstain share |
| `fp_reject_rate` | fraction of **true-valued** entries in honest ledgers at the last round that `judge` rejects |
| `fn_accept_rate` / `fn_accept_injected` | fraction of false-valued entries / injected false entries that `judge` accepts |
| `recovery_rounds` | rounds after injection until ASR is <= 0.05 and stays there; censored at the horizon (`recovered = 0`) |
| `context_tokens_per_query` | whitespace tokens of question + retrieved lines, per query |
| `scored_per_query` | number of candidate entries whose trust was computed, per query |
| `verifier_lookups` | archive lookups (covered facts only), whole run |
| `messages` | gossip messages plus retraction broadcasts |
