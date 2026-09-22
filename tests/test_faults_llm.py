import io
import json
import random

import pytest

from provmem.faults import FaultMode, FaultSpec, forge_entries, plan_false_values
from provmem.llm import UNKNOWN, DeterministicMockLLM, OpenAICompatibleLLM, question_for
from provmem.schema import EvidenceKind


def _forge(world, mode, **kw):
    spec = FaultSpec(mode=mode, **kw)
    values = plan_false_values(world, world.facts[:4], random.Random(3))
    return values, forge_entries(spec, world, "A5", 1, ["A0", "A1", "A2"], values, 3)


def test_false_values_are_plausible_and_never_the_truth(world):
    values = plan_false_values(world, world.facts, random.Random(0))
    assert set(values) == set(world.facts)
    assert all(v != world.truth[k] for k, v in values.items())
    pool_of = {"lead researcher": "person", "founding cycle": "cycle"}
    for (subject, attr), v in values.items():
        if attr in pool_of:
            assert v in world.pools[pool_of[attr]]


def test_plain_mode_cites_documents_that_do_not_exist(world):
    values, entries = _forge(world, FaultMode.PLAIN)
    assert len(entries) == 4
    assert all(e.evidence.kind is EvidenceKind.DOCUMENT and e.evidence.ref not in world.catalog
               for e in entries)
    assert {e.origin for e in entries} == {"A5"} and all(e.hop_count == 0 for e in entries)


def test_forged_meta_uses_valid_refs_and_impersonates_an_honest_origin(world):
    values, entries = _forge(world, FaultMode.FORGED_META)
    assert all(world.catalog[e.evidence.ref] == e.claim.key for e in entries)
    assert {e.origin for e in entries} == {"A1"}
    assert all(e.confidence == 0.99 and e.hop_count == 0 for e in entries)


def test_sybil_mode_fabricates_distinct_origins(world):
    values, entries = _forge(world, FaultMode.SYBIL, sybil_ids=3)
    assert len(entries) == 12 and len({e.origin for e in entries}) == 3
    assert all(o.startswith("sybil-") for o in {e.origin for e in entries})


def test_forged_content_is_only_invented_facts(world):
    _, entries = _forge(world, FaultMode.FORGED_META)
    for e in entries:
        assert e.claim.subject in world.subjects
        assert e.content == e.claim.render()


def test_mock_reader_sums_weights_and_breaks_ties_by_order():
    llm = DeterministicMockLLM()
    q = question_for("lead researcher", "Kelvara Station")
    ctx = [
        "- [w=0.30 origin=A1] The lead researcher of Kelvara Station is Ilsa Voren.",
        "- [w=0.20 origin=A2] The lead researcher of Kelvara Station is Tovan Keld.",
        "- [w=0.20 origin=A3] The lead researcher of Kelvara Station is Tovan Keld.",
    ]
    assert llm.answer(q, ctx).text == "Tovan Keld"
    assert llm.answer(q, ctx[:1] + ["- The lead researcher of Kelvara Station is Zed Qual."]).text == "Zed Qual"
    tie = ["- The lead researcher of Kelvara Station is Ilsa Voren.",
           "- The lead researcher of Kelvara Station is Tovan Keld."]
    assert llm.answer(q, tie).text == "Ilsa Voren"


def test_mock_reader_ignores_other_facts_and_abstains():
    llm = DeterministicMockLLM()
    q = question_for("lead researcher", "Kelvara Station")
    ctx = ["- The primary instrument of Kelvara Station is Quon resonator.",
           "- The lead researcher of Other Station is Ilsa Voren."]
    assert llm.answer(q, ctx).text == UNKNOWN
    assert llm.answer("not a question", ctx).text == UNKNOWN


def test_mock_reader_counts_prompt_tokens():
    a = DeterministicMockLLM().answer("What is the founding cycle of X Guild?",
                                      ["- The founding cycle of X Guild is cycle 3100."])
    assert a.prompt_tokens == 8 + 10


def test_optional_adapter_request_shape_without_network(monkeypatch):
    captured = {}

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data)
        captured["timeout"] = timeout
        payload = {"choices": [{"message": {"content": "cycle 3100."}}]}
        return Response(json.dumps(payload).encode())

    monkeypatch.delenv("PROVMEM_LLM_API_KEY", raising=False)
    monkeypatch.setattr("provmem.llm.urllib.request.urlopen", fake_urlopen)
    llm = OpenAICompatibleLLM(base_url="http://localhost:9/v1/")
    answer = llm.answer("What is the founding cycle of X Guild?", [])
    assert answer.text == "cycle 3100"
    assert captured["url"] == "http://localhost:9/v1/chat/completions"
    assert captured["body"]["temperature"] == 0
    assert "Authorization" not in captured["headers"]
