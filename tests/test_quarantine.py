from conftest import false_value_for, make_entry
from provmem.quarantine import QuarantineState, Retraction
from provmem.schema import Verification
from provmem.verify import Verifier


def test_refuted_entry_is_quarantined_and_retracted(world, ledger):
    k = world.facts[0]
    bad = make_entry(world, k, false_value_for(world, k), uid="bad", origin="A9")
    ledger.add(bad)
    st = QuarantineState()
    st.on_refuted(ledger, bad, "A0")
    assert bad.verification is Verification.QUARANTINED
    assert ledger.for_key(k) == []
    assert st.outbox == [Retraction("A0", k, bad.claim.value)]


def test_cascade_quarantines_other_unverified_entries_from_a_repeat_offender(world, ledger):
    keys = world.facts[:4]
    for i, k in enumerate(keys[:2]):
        ledger.add(make_entry(world, k, false_value_for(world, k), uid=f"bad{i}", origin="A9"))
    survivor = make_entry(world, keys[2], uid="s", origin="A9")
    verified = make_entry(world, keys[3], uid="v", origin="A9")
    verified.verification = Verification.VERIFIED
    bystander = make_entry(world, keys[2], uid="b", origin="A1")
    for e in (survivor, verified, bystander):
        ledger.add(e)
    st = QuarantineState(suspicion_limit=2)
    st.on_refuted(ledger, ledger.entries[0], "A0")
    assert survivor.active and verified.active
    st.on_refuted(ledger, ledger.entries[1], "A0")
    assert not survivor.active and verified.active and bystander.active


def test_retraction_quorum_is_required_when_the_agent_cannot_verify(world, ledger):
    k = world.facts[0]
    fv = false_value_for(world, k)
    e = make_entry(world, k, fv, uid="x", origin="A9")
    ledger.add(e)
    ver = Verifier(world, coverage=0.0)
    st = QuarantineState(retraction_quorum=2)
    st.on_retraction(ledger, Retraction("A1", k, fv), "A0", ver, 1)
    assert e.active
    st.on_retraction(ledger, Retraction("A2", k, fv), "A0", ver, 1)
    assert not e.active


def test_retraction_cannot_quarantine_an_entry_the_agent_verified_as_true(world, ledger):
    k = world.facts[0]
    e = make_entry(world, k, uid="t", origin="A9")
    ledger.add(e)
    ver = Verifier(world, coverage=1.0)
    st = QuarantineState(retraction_quorum=1)
    st.on_retraction(ledger, Retraction("A1", k, e.claim.value), "A0", ver, 1)
    assert e.active and e.verification is Verification.VERIFIED


def test_audit_spends_its_budget_on_conflicted_claims_first(world, ledger):
    k1, k2 = world.facts[0], world.facts[1]
    ledger.add(make_entry(world, k2, uid="calm", origin="A1"))
    ledger.add(make_entry(world, k1, uid="t", origin="A1"))
    bad = make_entry(world, k1, false_value_for(world, k1), uid="bad", origin="A9")
    ledger.add(bad)
    ver = Verifier(world, coverage=1.0)
    QuarantineState().audit(ledger, "A0", ver, 1, budget=1)
    assert ver.calls == 1
    assert {e.uid for e in ledger.entries if e.verified_round is not None} <= {"t", "bad"}
