# methods

the short version of how every published number was produced. the article is
at https://lockstep.greg.technology — this file is the audit trail.

## the task

the model receives one message: the one-page spec (`SEMANTICS.md`, embedded
verbatim) + a circuit as json + its input sequence, and must output the value
of every output net for every cycle, as a fenced json block of bit lists.
prompt construction: `lockstep/evalrun.py::build_prompt`. later records (852
of 1527) store the exact prompt sent verbatim; the earliest predate the field.
the prompt is fully deterministic from SEMANTICS.md + the circuit json, and
`scripts/rescore.py` proves every stored prompt regenerates byte-for-byte.

## the request

a bare chat completion via openrouter. the payload has exactly three keys —
model, messages, max_tokens — or two when openrouter reports no output cap for
a model (max_tokens is then omitted). no tools, no code execution, nothing to
call.
asserted mechanically in `tests/test_no_tools.py`. temperature and reasoning
effort: provider defaults. the one knob set is max output tokens, always the
model's maximum (clamped to context minus 16k where providers misreport).

## one shot

each (model, circuit) cell is the model's first attempt at its maximum output
budget. no best-of-n, no retries of attempts, no averaging. three things do
not consume the shot, because no reply was ever delivered: a transport error
(an http failure that never reached a model), a provider safety refusal, and
an undelivered reply (zero output tokens, or an error finish from the
provider). the same goes for a truncation capped far below the model's own
demonstrated output ceiling: openrouter routed some models across many
upstream providers with output ceilings ranging from 16k to 146k tokens
(kimi-k3 was hit hardest — several of its runs died at a 16k or 32k route
ceiling while it demonstrably produces 145k), and dying at a route ceiling is
a routing artifact, not a failure at max budget. all such cells were retried
on later days (the below-ceiling truncations with an explicit max_tokens —
batch retry3) and the first full-budget delivered attempt counts; a cell blocked in the matrix refused every time it was tried,
with a stored receipt per refusal.
early circuits first run under smaller experimental caps got fresh first
attempts at model max; the capped runs stay in the archive. selection rule as
code: `analysis/plot.py::canonical_cells`; per-attempt flags:
`results/index.csv` (canonical) and `results/all-attempts.csv` (everything).

## scoring

mechanical, no judge: extract the model's json answer (the last parseable
fenced block, with fallbacks to the whole reply and the last brace-span — see
`lockstep/evalrun.py::extract_answer`), parse with a json parser, compare bit by bit against the answer key (`keys/<circuit>.json`).
score = cycles correct before the first wrong bit; full score = pass.
malformed answer: 0. ran out of tokens mid-thought with no answer: 0
(status `truncated`, shown as "lim"). refusals and transport errors are
excluded from means. logic: `lockstep/evalrun.py::score`.

## the answer keys

every key passes a nine-way agreement check, re-runnable offline by anyone:
three simulators written from the spec alone (ours + codex's + agy's, see
`oracles/` — verbatim, with the writing agents' transcripts) and three
json-to-verilog translators, each run through icarus verilog and verilator.
(the earliest runs were gated by fewer evaluators — the jury grew over the
first days; agreement over all nine holds retroactively for every circuit and
ci re-proves it on every push to main; `uv run pytest` alone exercises the
simulators but not the external translators.) plus 1600 fuzz circuits across
two campaigns (`fuzz/` — the newer 600 store their full agreed traces, and
`scripts/fuzz_replay.py` re-verifies both from seeds, offline). the
comparator's ability to fail is itself tested:
`tests/test_metamorphic.py` proves structural mutations are caught, and
`tests/test_agreement.py` proves a single flipped bit is.

## models

10 scored models (11 ran through openrouter counting fable's refusals),
august 2026, slugs as in `results/index.csv`.
claude-fable-5 is unscored: the provider safety filter refused all 63 circuits
via openrouter (receipts: `results/records/anthropic__claude-fable-5/`, one
refusal per circuit) and also, probed on one circuit, via a direct api key on an account with a
cyber exception (`results/records/direct__claude-fable-5/`, two receipts). the same account's
claude.ai web ui answers the same prompts correctly (asserted, not receipted:
web-ui transcripts aren't exportable as records) — the block is
route-dependent.

## known limits

- upstream provider/quantization for open-weight models is whatever openrouter
  routed to; not pinned, mostly not recorded.
- generation ids exist for 852 of 1527 records (later runs); earlier ones
  predate the field. records also predate timestamp and sent-cap fields
  (added going forward), so "retried on later days" rests on the batch
  structure and the openrouter activity export, not per-record timestamps.
- one attempt per cell is noisy by construction. a model's overall number is
  a mean over its scored cells (63 for every model except opus-5,
  which is scored on 50 due to safety-filter blocks), which steadies it somewhat — but the 63
  are not independent draws (families contain near-clones, and the hardest
  tier was minted against the then-leader), so nearby rows in the ranking are
  not statistically distinguishable. read the frontier, not the decimals.
- this measures unaided serial simulation under an output-token ceiling. with
  a code tool, any of these models would score ~100%. that gap is the point.
