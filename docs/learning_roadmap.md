# Learning roadmap

A path from this repository to work that would actually answer the question it asks.
Steps are ordered by how much they reduce the biggest uncertainty (does any of this
survive contact with a real model?), not by difficulty.

## 0. Read the code in this order (one evening)

1. `schema.py` and `docs/memory_model.md`: what is stored, and which fields are forgeable.
2. `scoring.py`, `retrieval.py`: five strategies in about 200 lines.
3. `world.py`, `faults.py`: the entire fault model. Convince yourself it is harmless and
   that the tiers are ordered by attacker power.
4. `simulation.py`: the gossip loop and metrics. Find where `received_from` is set and why
   it is the only trusted provenance field.
5. `tests/test_scoring.py::test_forged_metadata_can_beat_honest_entry_without_agreement`:
   the smallest demonstration of why metadata alone is not security.

## 1. Close the biggest validity gap: a real reader (1-2 weeks)

* Run `OpenAICompatibleLLM` against a local open-weights model (llama.cpp, Ollama, vLLM).
  Keep `w=` annotations and provenance lines; add a variant with no annotations.
* Measure how often the model *follows the weights* versus majority or first-line bias.
  If the model ignores provenance annotations, the retrieval gate is doing all the work
  and the prompt formatting is decoration.
* Report per-model results; do not average across models.

## 2. Replace the toy embedder (a few days)

* Use `SentenceTransformerEmbedder` (`pip install -e ".[embeddings]"`) and rerun
  `bench`. Check that the false/true similarity gap is still small and that the pool
  size (`pool_factor`) is still adequate. Try `rank="product"` again.
* Add a hard-negative set: memories about *similar* facts with different subjects.

## 3. Make provenance unforgeable, then see what is left (2-4 weeks)

* Sign each entry (Ed25519 over canonical JSON of content + provenance fields); verify at
  receipt; store the signer id, not a self-declared origin.
* Rerun T2 and T3. The expected outcome is that impersonation and sybil identities are
  harder to mount, and the question becomes key management and who is allowed to sign.
* Compare against the unsigned results honestly: what did signing buy that verification
  did not?

## 4. Calibration (1-2 weeks)

* Treat `confidence` as a claim about accuracy and measure it: reliability diagrams and
  expected calibration error for honest agents' stated confidence versus correctness.
* Learn per-origin reliability online (Beta-Bernoulli posteriors updated by verification
  outcomes) and compare to the fixed-weight trust score. Watch for the cold-start problem
  and for an attacker who builds reputation first.

## 5. Stronger attackers (open-ended)

* Adaptive attacker that observes which claims get accepted and adjusts confidence,
  evidence and hop claims (a bandit against the acceptance rule).
* False retractions against the quarantine channel.
* Poisoning the verifier archive at a small rate, to measure how the best defence degrades.
* Time-varying facts, so that "newer" and "true" can disagree.

## 6. Reading

* Provenance in data systems: Buneman, Khanna and Tan,
  [*Why and Where: A Characterization of Data Provenance*](https://doi.org/10.1007/3-540-44503-X_20);
  and the W3C [PROV Data Model](https://www.w3.org/TR/prov-dm/).
* Trust and reputation in distributed systems: Kamvar, Schlosser and Garcia-Molina,
  [*The EigenTrust Algorithm for Reputation Management in P2P Networks*](https://doi.org/10.1145/775152.775242);
  and Douceur, [*The Sybil Attack*](https://www.microsoft.com/en-us/research/publication/the-sybil-attack/).
* Poisoning of retrieval-augmented systems: search for "RAG poisoning", "corpus
  poisoning" and "memory injection" in the last two years of security venues, and read them
  for what they *assume the attacker can write*, not for their headline attack success.
* Calibration: Guo et al.,
  [*On Calibration of Modern Neural Networks*](https://proceedings.mlr.press/v70/guo17a.html);
  then the literature on verbalised versus token-level confidence in language models.
* Gossip protocols: Demers et al.,
  [*Epidemic Algorithms for Replicated Database Maintenance*](https://doi.org/10.1145/41840.41841),
  for the propagation model behind `share_per_round` and `fanout`.

## 7. A publishable version would need

Real LLM readers on at least two open models; a semantic embedder; a memory built from
free text with extraction errors; at least one attacker that adapts; a pre-specified uncertainty
analysis matched to the sampling design; a pre-registered primary metric; and a clear statement
of what the memory writer can and cannot forge.
