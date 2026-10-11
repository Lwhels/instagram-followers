"""Unit tests for Instagram export parser."""

import json
import zipfile
import io
import pytest
from instagram_analyzer.parser import (
    parse_html_content,
    parse_json_content,
    parse_text_lines,
    parse_zip_archive,
    _clean_username,
)


def test_clean_username():
    assert _clean_username("john_doe") == "john_doe"
    assert _clean_username("@John_Doe") == "john_doe"
    assert _clean_username("https://www.instagram.com/alice.smith/") == "alice.smith"
    assert _clean_username("https://instagram.com/_u/bob_ross") == "bob_ross"


def test_parse_html_content():
    sample_html = """
    <!DOCTYPE html>
    <html>
    <body>
        <div class="pam uiBoxWhite">
            <div class="_a6-p">
                <div>
                    <div><a target="_blank" href="https://www.instagram.com/charlie_brown">charlie_brown</a></div>
                    <div>Nov 04, 2024 4:41 pm</div>
                </div>
            </div>
        </div>
        <div class="pam uiBoxWhite">
            <div class="_a6-p">
                <div>
                    <div><a target="_blank" href="https://www.instagram.com/snoopy_official">snoopy_official</a></div>
                    <div>Oct 12, 2023 1:15 am</div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    entries = parse_html_content(sample_html)
    assert len(entries) == 2
    assert entries[0].username == "charlie_brown"
    assert entries[0].timestamp_str == "Nov 04, 2024 4:41 pm"
    assert entries[1].username == "snoopy_official"
    assert entries[1].timestamp_str == "Oct 12, 2023 1:15 am"


def test_parse_json_content_format_a():
    sample_json = json.dumps([
        {
            "title": "",
            "string_list_data": [
                {
                    "href": "https://www.instagram.com/lucy_vanpelt",
                    "value": "lucy_vanpelt",
                    "timestamp": 1700000000
                }
            ]
        },
        {
            "title": "",
            "string_list_data": [
                {
                    "href": "https://www.instagram.com/linus_blanket",
                    "value": "linus_blanket",
                    "timestamp": 1705000000
                }
            ]
        }
    ])
    entries = parse_json_content(sample_json)
    assert len(entries) == 2
    assert entries[0].username == "lucy_vanpelt"
    assert entries[1].username == "linus_blanket"
    assert entries[0].timestamp_str is not None


def test_parse_json_content_format_b():
    sample_json = json.dumps({
        "relationships_following": [
            {
                "title": "",
                "string_list_data": [{"value": "woodstock_bird", "href": "https://www.instagram.com/woodstock_bird"}]
            }
        ]
    })
    entries = parse_json_content(sample_json)
    assert len(entries) == 1
    assert entries[0].username == "woodstock_bird"


def test_parse_text_lines():
    text = """
    # My friends
    user_one
    @user_two
    https://instagram.com/user_three
    """
    entries = parse_text_lines(text)
    assert len(entries) == 3
    assert [e.username for e in entries] == ["user_one", "user_two", "user_three"]


def test_parse_zip_archive():
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as z:
        followers_html = '<a href="https://www.instagram.com/follower_alice">follower_alice</a>'
        following_html = '<a href="https://www.instagram.com/following_bob">following_bob</a>'
        z.writestr("followers_and_following/followers_1.html", followers_html)
        z.writestr("followers_and_following/following.html", following_html)

    zip_buffer.seek(0)
    followers, following = parse_zip_archive(zip_buffer)
    assert len(followers) == 1
    assert followers[0].username == "follower_alice"
    assert len(following) == 1
    assert following[0].username == "following_bob"
