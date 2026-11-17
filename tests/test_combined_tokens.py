"""Unit tests for parse_combined_tokens helper in config_flow.py."""
import os
import sys

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "clphk"),
)

from const import parse_combined_tokens


def test_labeled_tokens_with_json_objects():
    raw = """
Access Token:
{"data":"NmFmYzNlM2UtZDVjMS00YWRhLWE1YTQtMTJiODBiNzMwMjEw","time":1794915903603,"expire":"Tue, 17 Nov 2026 12:45:02 GMT"}

Refresh Token:
{"data":"NmFmYzNlM2UtNWM1YS00NDM5LTgzMDQtYTkwZTBiNTMwMjBj","time":1794915903605,"expire":"2028-11-17T12:45:02.000Z"}
"""
    act, rct = parse_combined_tokens(raw)
    assert act == '{"data":"NmFmYzNlM2UtZDVjMS00YWRhLWE1YTQtMTJiODBiNzMwMjEw","time":1794915903603,"expire":"Tue, 17 Nov 2026 12:45:02 GMT"}'
    assert rct == '{"data":"NmFmYzNlM2UtNWM1YS00NDM5LTgzMDQtYTkwZTBiNTMwMjBj","time":1794915903605,"expire":"2028-11-17T12:45:02.000Z"}'


def test_single_json_dict_format():
    raw = '{"act": "NmFmYzNlM2UtZDVjMS00YWRhLWE1YTQtMTJiODBiNzMwMjEw", "rct": "NmFmYzNlM2UtNWM1YS00NDM5LTgzMDQtYTkwZTBiNTMwMjBj"}'
    act, rct = parse_combined_tokens(raw)
    assert act == "NmFmYzNlM2UtZDVjMS00YWRhLWE1YTQtMTJiODBiNzMwMjEw"
    assert rct == "NmFmYzNlM2UtNWM1YS00NDM5LTgzMDQtYTkwZTBiNTMwMjBj"


def test_two_raw_base64_lines():
    raw = """
NmFmYzNlM2UtZDVjMS00YWRhLWE1YTQtMTJiODBiNzMwMjEw
NmFmYzNlM2UtNWM1YS00NDM5LTgzMDQtYTkwZTBiNTMwMjBj
"""
    act, rct = parse_combined_tokens(raw)
    assert act == "NmFmYzNlM2UtZDVjMS00YWRhLWE1YTQtMTJiODBiNzMwMjEw"
    assert rct == "NmFmYzNlM2UtNWM1YS00NDM5LTgzMDQtYTkwZTBiNTMwMjBj"


def test_empty_or_invalid_returns_none():
    assert parse_combined_tokens("") == (None, None)
    assert parse_combined_tokens("hello world") == (None, None)
    assert parse_combined_tokens(None) == (None, None)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all combined tokens tests passed")
