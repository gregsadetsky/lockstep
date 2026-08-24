# results

every model attempt ever made, verbatim — nothing deleted, nothing rewritten.

`records/<model>/<circuit>__s<sample>__<batch>.json` — one file per attempt,
byte-identical to what the harness wrote at run time: the exact prompt, the
full response, the reasoning transcript (where the provider returns one),
token usage, and the mechanical score.

batches (the tag at the end of each filename):
- `feel1` — the original runs, some early ones under smaller experimental
  token caps before the "always model max" rule
- `max1` — reruns at each model's maximum output budget
- `retry1` — later-day retries of cells whose every earlier record was a
  safety refusal
- `retry2` — later-day retries of cells whose reply was never delivered
  (zero output tokens, or an error finish from the provider)
- `retry3` — retries, at an explicit max_tokens, of cells whose only attempts
  had been truncated at a provider route ceiling far below the model's max
- `retry4` — same explicit-max_tokens treatment for the last two cells that
  had never had a reply delivered on any earlier try
- `fable-retest` — refusal receipts for claude-fable-5 via a second api route

`index.csv` — exactly the attempts the matrix presents: one row per
(model, circuit) cell, the one-shot selection: the model's first delivered attempt
at its max budget (`max1` beats `feel1` at the same sample index). safety
refusals, transport errors, and undelivered replies don't consume the shot —
those cells were retried, and a cell refused every time shows as blocked.
the rule is code, not curation: `analysis/plot.py::canonical_cells`.

`all-attempts.csv` — the full ledger, one row per stored attempt, the scored
one flagged `canonical=1`. regenerate both csvs with
`uv run python scripts/make_index.py`.

to re-derive every score and prompt from raw materials:
`uv run python scripts/rescore.py` (no api key needed).

`provenance/` — the per-batch run summaries as printed at run time. note:
these summaries average over every record in their batch (refusals and
truncations in the denominator), which is NOT the published scoring rule —
they are historical receipts, not results. the published numbers come from
`index.csv` only.
