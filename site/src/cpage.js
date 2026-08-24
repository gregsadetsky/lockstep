// /c/?id=<circuit name> — interactive schematic + every model's attempts.
// with no id, load the easiest starter (counter_3bit).

import { mountCircuitSim } from "./circuit.js";

const container = document.querySelector("#circuit-sim");
const title = document.querySelector("#cname");

async function main() {
  const id = new URLSearchParams(location.search).get("id") || "counter_3bit";

  const ids = await (await fetch("/circuits/index.json")).json();
  const res = await fetch(`/circuits/${encodeURIComponent(id)}.json`);
  if (!res.ok) {
    title.textContent = "not found";
    container.textContent = `no circuit named "${id}" here (yet?)`;
    return;
  }
  const circuit = await res.json();
  document.title = `${circuit.name} · Lockstep`;

  // the title is a select: jump to any circuit
  const sel = document.createElement("select");
  sel.id = "circuit-select";
  for (const i of ids) {
    const o = document.createElement("option");
    o.value = i;
    o.textContent = i;
    if (i === circuit.name) o.selected = true;
    sel.append(o);
  }
  sel.addEventListener("change", () => {
    location.search = `?id=${encodeURIComponent(sel.value)}`;
  });
  title.replaceChildren(sel);

  await mountResults(circuit);
  mountCircuitSim(container, circuit, {
    natural: circuit.gates.length > 24,
    editableInputs: true,
    note: "",
  });
}

// results first: each model's one-shot attempt; click a chip to replay its
// submitted bits against the golden trace, first wrong bit in red.
async function mountResults(circuit) {
  const res = await fetch(`/results/${encodeURIComponent(circuit.name)}.json`);
  if (!res.ok) return;
  const { golden, attempts } = await res.json();

  const holder = document.createElement("section");
  holder.id = "model-results";
  holder.innerHTML = `<h2>How the models did on this circuit</h2>
    <div class="attempts"></div><div class="replay"></div>`;
  container.parentNode.insertBefore(holder, container);

  const byModel = new Map();
  for (const a of attempts) {
    if (!byModel.has(a.model)) byModel.set(a.model, []);
    byModel.get(a.model).push(a);
  }
  const best = (rs) => Math.max(...rs.map((a) => a.prefix / a.cycles));
  const models = [...byModel.entries()].sort((x, y) => best(y[1]) - best(x[1]));

  const table = holder.querySelector(".attempts");
  const replay = holder.querySelector(".replay");
  for (const [model, rs] of models) {
    const row = document.createElement("div");
    row.className = "attempt-row";
    const chips = rs.map((a, i) => {
      const label =
        a.status === "refused" ? "refused" :
        a.status === "truncated" ? "hit output limit" :
        a.status === "parse_error" || a.status === "format_error" ? "malformed answer" :
        a.prefix === a.cycles ? "exact" : `${a.prefix}/${a.cycles}`;
      const cls =
        a.status === "refused" ? "refused" :
        a.status === "truncated" ? "lim" :
        a.status.includes("error") ? "malformed" :
        a.prefix === a.cycles ? "exact" : "partial";
      const clickable = a.answer ? ` data-i="${i}"` : " disabled";
      const tlink = a.transcript
        ? ` <a class="tlink" href="${a.transcript}" target="_blank" rel="noopener">transcript</a>`
        : "";
      return `<span class="attempt"><button class="chip ${cls}"${clickable}>${label}</button>${tlink}</span>`;
    }).join("");
    row.innerHTML = `<span class="mname">${model}</span> ${chips}`;
    row.querySelectorAll(".chip[data-i]").forEach((btn) => {
      btn.addEventListener("click", () => {
        table.querySelectorAll(".chip.sel").forEach((b) => b.classList.remove("sel"));
        btn.classList.add("sel");
        renderReplay(replay, model, rs[Number(btn.dataset.i)], golden, circuit);
      });
    });
    table.append(row);
  }
}

function renderReplay(el, model, attempt, golden, circuit) {
  const outs = circuit.outputs;
  const cycles = attempt.cycles;
  let firstWrong = -1;
  for (let t = 0; t < cycles && firstWrong === -1; t++) {
    for (const o of outs) if (attempt.answer[o][t] !== golden[o][t]) { firstWrong = t; break; }
  }
  const head = `<tr><th class="row-name">cycle</th>${Array.from({ length: cycles },
    (_, t) => `<th>${t}</th>`).join("")}</tr>`;
  const rows = outs.map((o) => {
    const cells = Array.from({ length: cycles }, (_, t) => {
      // coerce booleans so a true/false answer renders the same verdict the
      // python scorer gives it (Number(true) === 1)
      const m = Number(attempt.answer[o][t]);
      const g = golden[o][t];
      const after = firstWrong !== -1 && t > firstWrong;
      const cls = after ? "after" : m !== g ? "wrong" : "";
      const txt = !after && m !== g ? `${m}<span class="truth">${g}</span>` : `${m}`;
      return `<td class="${cls}">${txt}</td>`;
    }).join("");
    return `<tr><th class="row-name">${o}</th>${cells}</tr>`;
  }).join("");
  const verdict = firstWrong === -1
    ? `${model} was bit-for-bit exact for all ${cycles} cycles.`
    : `${model} was exact up to cycle ${firstWrong === 0 ? "0 - its very first output" : firstWrong - 1}, then wrong at cycle ${firstWrong} (red - small digit is the true bit). later cycles dimmed.`;
  el.innerHTML = `<p class="replay-verdict">${verdict}</p>
    <div class="trace"><table>${head}${rows}</table></div>`;
}

main();
