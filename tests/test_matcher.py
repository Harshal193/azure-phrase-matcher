import pytest
from matcher import normalize, load_phrases, find_closest, extract_phrase


def test_normalize_lowercases_and_collapses_whitespace():
    assert normalize("  Hello   WORLD \n") == "hello world"


def test_normalize_blank_is_empty():
    assert normalize("   ") == ""


def test_find_closest_exact_match_scores_one():
    assert find_closest("hello world", ["goodbye", "hello world"]) == ("hello world", 1.0)


def test_find_closest_picks_near_miss():
    phrases = ["good morning", "good night", "see you soon"]
    assert find_closest("gud mornin", phrases)[0] == "good morning"


def test_find_closest_is_deterministic():
    phrases = ["alpha", "alphas", "beta"]
    assert find_closest("alph", phrases) == find_closest("alph", phrases)


def test_find_closest_tie_returns_earlier_phrase():
    # "aa" scores 0.5 against both "ab" and "ba"
    assert find_closest("aa", ["ab", "ba"])[0] == "ab"


def test_find_closest_handles_accented_text():  # Review Focus 4
    assert find_closest("café", ["cafe", "tea"])[0] == "cafe"


def test_find_closest_handles_very_long_input():  # Review Focus 5
    phrase, score = find_closest("x" * 10_000, ["hello", "world"])
    assert phrase in ["hello", "world"]
    assert 0.0 <= score <= 1.0


def test_load_phrases_reads_json_array(tmp_path):
    f = tmp_path / "p.json"
    f.write_text('["one", "two"]', encoding="utf-8")
    assert load_phrases(f) == ["one", "two"]


@pytest.mark.parametrize("content", ["[]", '["ok", 5]', '{"a": 1}'])
def test_load_phrases_rejects_bad_content(tmp_path, content):
    f = tmp_path / "p.json"
    f.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        load_phrases(f)


def test_extract_phrase_returns_stripped_value():
    assert extract_phrase({"phrase": "  hi  "}) == "hi"


@pytest.mark.parametrize("payload", [
    {"phrase": "   "},   # Review Focus 1
    {"phrase": 5},       # Review Focus 2
    {"phrase": None},    # Review Focus 2
    {"phrase": ["hi"]},  # Review Focus 2
    {},
    None,
    ["hi"],
])
def test_extract_phrase_rejects_bad_input(payload):
    with pytest.raises(ValueError, match="non-empty string"):
        extract_phrase(payload)
