// simulator for the lockstep netlist format (see SEMANTICS.md):
// NAND-only gates, DFFs, implicit clock.
//
// settle(inputs)  — combinational pass only: what every net reads right now,
//                   given the current flip-flop state and these input values.
// clock(inputs)   — settle, then the clock edge: every dff loads its d.
//                   returns the settled nets for the cycle just recorded.

export function createSim(circuit) {
  let state = {};
  let cycle = 0;

  function reset() {
    state = {};
    for (const f of circuit.dffs) state[f.q] = f.init;
    cycle = 0;
  }

  function settle(inputVals = {}) {
    const nets = { ...state };
    for (const name of circuit.inputs) nets[name] = inputVals[name] ?? 0;
    // gates may be listed in any order; sweep until all computed (acyclic)
    const pending = [...circuit.gates];
    while (pending.length > 0) {
      let progressed = false;
      for (let i = 0; i < pending.length; ) {
        const g = pending[i];
        if (nets[g.a] !== undefined && nets[g.b] !== undefined) {
          nets[g.y] = 1 - (nets[g.a] & nets[g.b]);
          pending.splice(i, 1);
          progressed = true;
        } else {
          i += 1;
        }
      }
      if (!progressed) throw new Error("undriven net or combinational loop");
    }
    return nets;
  }

  function clock(inputVals = {}) {
    const nets = settle(inputVals);
    const next = {};
    for (const f of circuit.dffs) next[f.q] = nets[f.d];
    state = next;
    cycle += 1;
    return nets;
  }

  reset();
  return {
    reset,
    settle,
    clock,
    get cycle() { return cycle; },
  };
}
