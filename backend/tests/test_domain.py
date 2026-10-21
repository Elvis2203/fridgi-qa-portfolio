import pytest

from app.domain import InvalidBatch, comparison_key, parse_batch


def test_parsing_preserves_original_input_and_custom_foods():
    entries = parse_batch("  nduja ,\r\nstracchino\n homemade  tomato sauce \n")
    assert [entry.display_name for entry in entries] == [
        "nduja",
        "stracchino",
        "homemade tomato sauce",
    ]
    assert entries[-1].original_input == " homemade  tomato sauce "


def test_comparison_is_conservative_and_unicode_aware():
    assert comparison_key(" CHICKEN ") == comparison_key("Chicken")
    assert comparison_key("cafe\u0301") == comparison_key("café")
    for first, second in [
        ("tomato", "cherry tomatoes"),
        ("cafe", "café"),
        ("rice", "rice flour"),
        ("chicken", "leftover roast chicken"),
        ("a-b", "a b"),
        ("Ａ", "A"),
    ]:
        assert comparison_key(first) != comparison_key(second)


@pytest.mark.parametrize("text", ["", " , \r\n\t", "a" * 101, "a," * 51, "x" * 10001, "a\x00b"])
def test_invalid_batches_are_rejected(text):
    with pytest.raises(InvalidBatch):
        parse_batch(text)


def test_valid_limits_use_unicode_code_points_and_cleaned_names():
    assert len(parse_batch(" " * 9900 + "a" * 100)[0].display_name) == 100
    assert len(parse_batch(",".join(["🍅" * 100] * 50))) == 50
