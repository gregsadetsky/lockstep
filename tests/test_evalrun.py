"""Parser and scorer for llm replies — no network involved."""

from lockstep.evalrun import extract_answer, score

GOLDEN = {"y": [0, 1, 1, 0], "q": [1, 1, 0, 0]}


def test_extracts_fenced_json_block() -> None:
    text = 'reasoning...\n```json\n{"y": [0, 1], "q": [1, 0]}\n```\n'
    assert extract_answer(text) == {"y": [0, 1], "q": [1, 0]}


def test_last_fenced_block_wins() -> None:
    text = '```json\n{"y": [9]}\n```\nwait, correcting:\n```json\n{"y": [0, 1]}\n```'
    assert extract_answer(text) == {"y": [0, 1]}


def test_extracts_bare_json_reply() -> None:
    assert extract_answer('{"y": [0, 1]}') == {"y": [0, 1]}


def test_extracts_trailing_object_from_prose() -> None:
    text = 'after simulating, the answer is {"y": [0, 1, 1, 0]} as shown.'
    assert extract_answer(text) == {"y": [0, 1, 1, 0]}


def test_unfenced_block_without_json_tag() -> None:
    text = 'final:\n```\n{"y": [1]}\n```'
    assert extract_answer(text) == {"y": [1]}


def test_no_json_returns_none() -> None:
    assert extract_answer("i cannot determine the trace") is None
    assert extract_answer("") is None


def test_score_exact() -> None:
    s = score(GOLDEN, {"y": [0, 1, 1, 0], "q": [1, 1, 0, 0]}, 4)
    assert s["exact"] and s["prefix_cycles"] == 4 and s["pointwise"] == 1.0


def test_score_diverges_at_cycle_2() -> None:
    s = score(GOLDEN, {"y": [0, 1, 0, 1], "q": [1, 1, 0, 0]}, 4)
    assert not s["exact"]
    assert s["prefix_cycles"] == 2
    assert s["pointwise"] == 0.75  # 6 of 8 cells right


def test_score_wrong_at_cycle_0_scores_zero_prefix() -> None:
    s = score(GOLDEN, {"y": [1, 1, 1, 0], "q": [1, 1, 0, 0]}, 4)
    assert s["prefix_cycles"] == 0
    assert not s["exact"]


def test_score_extra_keys_ignored_but_outputs_required() -> None:
    ok = score(GOLDEN, {"y": [0, 1, 1, 0], "q": [1, 1, 0, 0], "junk": [1]}, 4)
    assert ok["exact"]
    missing = score(GOLDEN, {"y": [0, 1, 1, 0]}, 4)
    assert missing["status"] == "format_error" and not missing["exact"]


def test_score_bad_shapes_are_format_errors() -> None:
    for bad in (
        {"y": [0, 1, 1], "q": [1, 1, 0, 0]},  # wrong length
        {"y": [0, 1, 1, 2], "q": [1, 1, 0, 0]},  # non-binary
        {"y": "0110", "q": [1, 1, 0, 0]},  # string not list
    ):
        assert score(GOLDEN, bad, 4)["status"] == "format_error"


def test_score_none_is_parse_error() -> None:
    s = score(GOLDEN, None, 4)
    assert s["status"] == "parse_error" and s["prefix_cycles"] == 0
