# reproducing

everything below runs offline (no api key) except the last step.

## setup

    uv sync
    brew install icarus-verilog verilator   # iverilog >= 12, verilator >= 5
                                            # (tested: iverilog 13.0, verilator 5.050)

## checks, in increasing cost

    # 1. test suite (~1 min; verilog tests self-skip if tools missing)
    uv run pytest -q

    # 2. re-derive every published score and prompt from raw materials (~1 min)
    uv run python scripts/rescore.py

    # 3. one circuit through all nine evaluators (~seconds)
    uv run python -m lockstep.harness circuits/xor_from_nand.json

    # 4. every evaluated circuit through all nine evaluators (~14 min; needs the verilog toolchain)
    uv run python -m lockstep.harness circuits/*.json circuits/*/*.json

    # 5. replay both committed fuzz campaigns from their seeds (~minutes, no toolchain)
    uv run python scripts/fuzz_replay.py

    # 6. fresh nine-way fuzz campaign on new seeds (~minutes; needs the verilog toolchain)
    uv run python -m lockstep.harness --fuzz-v2 25 --seed 12345 --build build-myfuzz

    # 7. regenerate every chart from the records
    uv run python analysis/plot.py

    # 8. regenerate the per-attempt index
    uv run python scripts/make_index.py

## run a live cell yourself (needs an openrouter key AND the verilog toolchain
## from setup — the golden gate runs all nine evaluators before any api call)

    cp .env.example .env    # put your OPENROUTER_API_KEY in it
    uv run python -m lockstep.evalrun --out results/mine \
      --models google/gemini-3.7-flash --circuits circuits/nand_chain_2.json --samples 1

the golden gate runs first (all nine evaluators must agree on the circuit),
then one api call, then mechanical scoring. the record lands in
`results/mine/` with the verbatim prompt and response.

note: runs are idempotent — existing records are skipped on rerun. that
includes error records: if a call fails (bad key, network), delete its json
from your --out dir before retrying, or the retry will be skipped.
