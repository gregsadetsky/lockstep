"""Seeded circuit generators. All acyclic by construction: gates only read
nets that already exist (inputs, dff outputs, earlier gate outputs); dff
d-inputs may reference any net, which is how feedback forms.

Families:
- random_netlist: unstructured DAG (baseline difficulty)
- chain_netlist:  depth-maximized — every gate feeds the next, depth == gates
- mix_netlist:    dense state feedback — every dff's next value is a cone
                  whose leaves are random dffs/inputs (state width x cycles)
- rule30_netlist: rule 30 cellular automaton on a ring — chaotic, no
                  recognition or periodicity shortcuts
"""

from __future__ import annotations

import random

from .netlist import Dff, Gate, Netlist, from_dict


def random_netlist(
    seed: int,
    n_inputs: int = 3,
    n_gates: int = 10,
    n_dffs: int = 2,
    cycles: int = 12,
) -> Netlist:
    rng = random.Random(seed)
    inputs = [f"in{i}" for i in range(n_inputs)]
    qs = [f"q{i}" for i in range(n_dffs)]
    pool = inputs + qs
    gates: list[Gate] = []
    for i in range(n_gates):
        y = f"n{i}"
        gates.append(Gate(rng.choice(pool), rng.choice(pool), y))
        pool.append(y)
    dffs = [Dff(d=rng.choice(pool), q=qs[i], init=rng.randint(0, 1)) for i in range(n_dffs)]
    n_out = rng.randint(1, min(4, len(pool)))
    outputs = sorted(rng.sample(pool, n_out))
    trace = {n: [rng.randint(0, 1) for _ in range(cycles)] for n in inputs}
    return _build(f"rand_s{seed}_g{n_gates}_d{n_dffs}", inputs, outputs, gates, dffs, trace, cycles)


def _build(
    name: str,
    inputs: list[str],
    outputs: list[str],
    gates: list[Gate],
    dffs: list[Dff],
    trace: dict[str, list[int]],
    cycles: int,
) -> Netlist:
    # round-trip through from_dict so generated circuits pass the same
    # validation as hand-written ones
    return from_dict(
        {
            "name": name,
            "inputs": inputs,
            "outputs": outputs,
            "gates": [{"type": "NAND", "a": g.a, "b": g.b, "y": g.y} for g in gates],
            "dffs": [{"d": f.d, "q": f.q, "init": f.init} for f in dffs],
            "trace": trace,
            "cycles": cycles,
        }
    )


def chain_netlist(
    seed: int,
    n_gates: int = 100,
    n_dffs: int = 12,
    cycles: int = 24,
    n_inputs: int = 3,
) -> Netlist:
    rng = random.Random(seed)
    inputs = [f"in{i}" for i in range(n_inputs)]
    qs = [f"q{i}" for i in range(n_dffs)]
    pool = inputs + qs
    gates: list[Gate] = []
    prev = rng.choice(pool)
    for i in range(n_gates):
        y = f"n{i}"
        gates.append(Gate(prev, rng.choice(pool), y))  # depth == i+1 by construction
        pool.append(y)
        prev = y
    tail = [g.y for g in gates[-max(2 * n_dffs, n_gates // 4) :]]
    dffs = [Dff(d=rng.choice(tail), q=qs[i], init=rng.randint(0, 1)) for i in range(n_dffs)]
    outputs = sorted({gates[-1].y, *rng.sample(qs, min(3, n_dffs))})
    trace = {n: [rng.randint(0, 1) for _ in range(cycles)] for n in inputs}
    return _build(
        f"chain_s{seed}_g{n_gates}_d{n_dffs}", inputs, outputs, gates, dffs, trace, cycles
    )


def mix_netlist(
    seed: int,
    n_dffs: int = 16,
    gates_per_dff: int = 5,
    cycles: int = 40,
    n_inputs: int = 2,
) -> Netlist:
    rng = random.Random(seed)
    inputs = [f"in{i}" for i in range(n_inputs)]
    qs = [f"q{i}" for i in range(n_dffs)]
    gates: list[Gate] = []
    dffs: list[Dff] = []
    for i in range(n_dffs):
        cone: list[str] = []
        for j in range(gates_per_dff):
            # chain within the cone so every gate is live: a = previous cone
            # gate (fresh dff/input leaf for the first), b = random dff/input
            a = cone[-1] if cone else rng.choice(qs + inputs)
            y = f"c{i}_{j}"
            gates.append(Gate(a, rng.choice(qs + inputs), y))
            cone.append(y)
        dffs.append(Dff(d=cone[-1], q=qs[i], init=rng.randint(0, 1)))
    outputs = sorted(rng.sample(qs, min(6, n_dffs)))
    trace = {n: [rng.randint(0, 1) for _ in range(cycles)] for n in inputs}
    return _build(
        f"mix_s{seed}_d{n_dffs}_c{cycles}", inputs, outputs, gates, dffs, trace, cycles
    )


def perm_netlist(
    seed: int,
    n_dffs: int = 24,
    cycles: int = 40,
    n_inputs: int = 2,
) -> Netlist:
    """'full dff land': ZERO gates — every dff's d is another dff's q (a fixed
    random permutation), except a few injection dffs fed by inputs (fresh bits
    each cycle, so the state never becomes periodic). isolates pure state
    bookkeeping from boolean logic ('full nand land' is chain_netlist with
    n_dffs=0)."""
    rng = random.Random(seed)
    inputs = [f"in{i}" for i in range(n_inputs)]
    qs = [f"q{i}" for i in range(n_dffs)]
    perm = list(range(n_dffs))
    rng.shuffle(perm)
    inject = rng.sample(range(n_dffs), n_inputs)
    dffs = []
    for i in range(n_dffs):
        if i in inject:
            d = inputs[inject.index(i)]
        else:
            d = qs[perm[i]]
        dffs.append(Dff(d=d, q=qs[i], init=rng.randint(0, 1)))
    outputs = sorted(rng.sample(qs, min(8, n_dffs)))
    trace = {n: [rng.randint(0, 1) for _ in range(cycles)] for n in inputs}
    return _build(f"perm_s{seed}_d{n_dffs}_c{cycles}", inputs, outputs, [], dffs, trace, cycles)


def ca_params(seed: int, k: int) -> tuple[int, list[int]]:
    """Deterministic (rule, init) for ca_netlist — public so tests can verify
    the gate construction against a direct implementation of the same rule."""
    rng = random.Random(seed ^ 0xCA)
    while True:
        rule = rng.randint(1, 254)
        if 0 < rule.bit_count() < 8:
            break
    init = [rng.randint(0, 1) for _ in range(k)]
    if not any(init):
        init[0] = 1
    return rule, init


def ca_netlist(seed: int, k: int = 10, cycles: int = 24) -> Netlist:
    """Elementary cellular automaton on a ring with a RANDOM rule table —
    anti-recognition variant of rule30: there is no famous name to spot, the
    rule is synthesized as sum-of-products NAND logic, and every net name is
    neutral (w1, w2, ... / s0..s{k-1}); the circuit name is an opaque x{seed}.
    Some rules settle quickly (easy), some are chaotic (hard) — the golden
    sims decide, difficulty is not guaranteed per seed."""
    rule, init = ca_params(seed, k)
    gates: list[Gate] = []
    counter = 0

    def nand(a: str, b: str) -> str:
        nonlocal counter
        counter += 1
        y = f"w{counter}"
        gates.append(Gate(a, b, y))
        return y

    def not_(a: str) -> str:
        return nand(a, a)

    def and_(a: str, b: str) -> str:
        return not_(nand(a, b))

    def or_(a: str, b: str) -> str:
        return nand(not_(a), not_(b))

    cells = [f"s{i}" for i in range(k)]
    dffs: list[Dff] = []
    for i in range(k):
        left, mid, right = cells[(i - 1) % k], cells[i], cells[(i + 1) % k]
        inv = {left: not_(left), mid: not_(mid), right: not_(right)}
        terms = []
        for n in range(8):
            if not (rule >> n) & 1:
                continue
            la = left if n & 4 else inv[left]
            mb = mid if n & 2 else inv[mid]
            rc = right if n & 1 else inv[right]
            terms.append(and_(and_(la, mb), rc))
        acc = terms[0]
        for t in terms[1:]:
            acc = or_(acc, t)
        dffs.append(Dff(d=acc, q=cells[i], init=init[i]))
    outputs = cells[::2]
    return _build(f"x{seed}", [], outputs, gates, dffs, {}, cycles)


def rule30_netlist(k: int = 16, cycles: int = 32, seed: int = 0) -> Netlist:
    """Rule 30 on a ring of k cells: c[i]' = c[i-1] XOR (c[i] OR c[i+1])."""
    rng = random.Random(seed)
    init = [rng.randint(0, 1) for _ in range(k)]
    if not any(init):
        init[0] = 1
    cells = [f"c{i}" for i in range(k)]
    gates: list[Gate] = []
    dffs: list[Dff] = []
    for i in range(k):
        left, mid, right = cells[(i - 1) % k], cells[i], cells[(i + 1) % k]
        nm, nr, orr = f"nm{i}", f"nr{i}", f"or{i}"
        gates.append(Gate(mid, mid, nm))  # NOT mid
        gates.append(Gate(right, right, nr))  # NOT right
        gates.append(Gate(nm, nr, orr))  # OR(mid, right)
        t1, t2, t3, x = f"t1_{i}", f"t2_{i}", f"t3_{i}", f"x{i}"
        gates.append(Gate(left, orr, t1))
        gates.append(Gate(left, t1, t2))
        gates.append(Gate(orr, t1, t3))
        gates.append(Gate(t2, t3, x))  # XOR(left, OR(mid, right))
        dffs.append(Dff(d=x, q=cells[i], init=init[i]))
    outputs = cells[::2]
    return _build(f"rule30_k{k}_c{cycles}_s{seed}", [], outputs, gates, dffs, {}, cycles)
