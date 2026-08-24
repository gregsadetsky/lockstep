# ledger reconcile

`openrouter-activity.csv` is openrouter's own account activity export for this
project's api key (exported 2026-08-26, covering 2026-08-23 03:39 utc through
2026-08-25 23:58 utc — the entire project; rows for unrelated keys on the same
account were filtered out). it is the third-party ledger the stored records
can be checked against.

the arithmetic, as of the frozen dataset (1519 records):

- 1497 ledger rows (every api call ever made with the key, including retries,
  refusals, cancelled streams, and calls whose records predate id storage).
- 844 records store a generation id. 808 match a ledger row directly.
- 36 do not, and every one is explained:
  - 1 went through the direct anthropic api (fable probe), not openrouter.
  - 35 are opus-5 safety refusals with empty usage: the moderation block fired
    upstream before any generation was created, so openrouter returned a
    response id but recorded no generation in the billing ledger (nothing
    generated, nothing billed). refusals that did bill prompt tokens (all 63
    of fable's, 6 of opus's) appear in the ledger normally.
- 689 ledger rows have no matching stored record id: the early era's records
  predate the generation-id field (675 records), plus deleted-and-retried
  transport errors and the cancelled streams of one aborted (unstarted) run.

to re-run the match: join `generation_id` between the csv and
`results/records/*/*.json`.
