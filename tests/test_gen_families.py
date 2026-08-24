"""The structured generators must produce what they claim: chains must be
maximally deep, rule 30 netlists must actually compute rule 30."""

from lockstep.gen import (
    ca_netlist,
    ca_params,
    chain_netlist,
    mix_netlist,
    perm_netlist,
    rule30_netlist,
)
from lockstep.netlist import stats
from lockstep.sim import simulate


def test_chain_depth_equals_gate_count() -> None:
    nl = chain_netlist(seed=7, n_gates=50, n_dffs=6, cycles=8)
    assert stats(nl)["depth"] == 50


def test_mix_every_dff_has_own_cone() -> None:
    nl = mix_netlist(seed=7, n_dffs=8, gates_per_dff=4, cycles=8)
    assert len(nl.gates) == 32
    assert len({f.d for f in nl.dffs}) == 8  # each dff fed by its own cone tip


def test_rule30_netlist_matches_direct_implementation() -> None:
    k, cycles, seed = 11, 20, 3
    nl = rule30_netlist(k=k, cycles=cycles, seed=seed)
    out = simulate(nl)

    # direct rule 30 on a ring, from the same init the netlist embeds
    state = [f.init for f in nl.dffs]
    for t in range(cycles):
        for i, cell in enumerate(f"c{j}" for j in range(k)):
            if cell in out:
                assert out[cell][t] == state[i], f"cell {cell} cycle {t}"
        state = [
            state[(i - 1) % k] ^ (state[i] | state[(i + 1) % k]) for i in range(k)
        ]


def test_rule30_gate_and_dff_counts() -> None:
    nl = rule30_netlist(k=16, cycles=32, seed=0)
    assert len(nl.gates) == 7 * 16
    assert len(nl.dffs) == 16
    assert stats(nl)["live_dffs"] == 16  # ring: every cell influences outputs


def test_ca_netlist_matches_direct_rule_for_random_rules() -> None:
    # the anti-recognition CA: gate construction must implement exactly the
    # rule table ca_params drew, verified against a direct implementation
    for seed in (11, 12, 13, 14):
        k, cycles = 9, 15
        nl = ca_netlist(seed, k=k, cycles=cycles)
        rule, init = ca_params(seed, k)
        out = simulate(nl)
        state = list(init)
        for t in range(cycles):
            for i in range(k):
                cell = f"s{i}"
                if cell in out:
                    assert out[cell][t] == state[i], f"seed {seed} cell {i} cycle {t}"
            state = [
                (rule >> ((state[(i - 1) % k] << 2) | (state[i] << 1) | state[(i + 1) % k])) & 1
                for i in range(k)
            ]


def test_ca_net_names_are_neutral() -> None:
    nl = ca_netlist(seed=99, k=8, cycles=10)
    assert nl.name == "x99"
    for g in nl.gates:
        assert g.y.startswith("w"), g.y  # no or7/nm3-style hints


def test_perm_netlist_is_pure_bookkeeping() -> None:
    nl = perm_netlist(seed=6, n_dffs=10, cycles=12, n_inputs=2)
    assert nl.gates == ()  # zero logic — full dff land
    # verify against direct simulation of the wiring: each dff copies its d
    wiring = {f.q: f.d for f in nl.dffs}
    state = {f.q: f.init for f in nl.dffs}
    out = simulate(nl)
    for t in range(nl.cycles):
        for o in nl.outputs:
            assert out[o][t] == state[o], f"{o} cycle {t}"
        values = dict(state)
        for name in nl.inputs:
            values[name] = nl.trace[name][t]
        state = {q: values[d] for q, d in wiring.items()}


def test_chain_with_zero_dffs_is_pure_nand() -> None:
    nl = chain_netlist(seed=6, n_gates=40, n_dffs=0, cycles=8)
    assert nl.dffs == ()
    assert stats(nl)["depth"] == 40


def test_families_are_deterministic_per_seed() -> None:
    a = chain_netlist(seed=42, n_gates=20, n_dffs=4, cycles=6)
    b = chain_netlist(seed=42, n_gates=20, n_dffs=4, cycles=6)
    assert a == b
    assert simulate(a) == simulate(b)
