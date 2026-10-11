"""Unit tests for SQLite database layer."""

import os
import tempfile
import pytest
from instagram_analyzer.database import Database
from instagram_analyzer.models import DecisionType, RelationshipType
from instagram_analyzer.parser import ParsedEntry


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(db_path=path)
    yield db
    if os.path.exists(path):
        os.remove(path)


def test_save_snapshot_and_metrics(temp_db):
    followers = [
        ParsedEntry(username="alice", timestamp_str="Jan 01, 2025"),
        ParsedEntry(username="bob", timestamp_str="Jan 02, 2025"),
        ParsedEntry(username="carol", timestamp_str="Jan 03, 2025"),
    ]
    following = [
        ParsedEntry(username="alice"),
        ParsedEntry(username="david"),
        ParsedEntry(username="eva"),
    ]

    snap_id = temp_db.save_snapshot(name="Test Snapshot 1", followers=followers, following=following)
    assert snap_id == 1

    metrics = temp_db.compute_metrics(snap_id)
    assert metrics.total_followers == 3
    assert metrics.total_following == 3
    assert metrics.mutual_count == 1  # alice
    assert metrics.fan_count == 2     # bob, carol
    assert metrics.unreciprocated_raw_count == 2  # david, eva
    assert metrics.actionable_unreciprocated_count == 2
    assert metrics.reciprocity_rate == pytest.approx(33.33, 0.01)


def test_record_decision_and_undo(temp_db):
    followers = [ParsedEntry(username="alice")]
    following = [ParsedEntry(username="alice"), ParsedEntry(username="celeb_brand")]

    snap_id = temp_db.save_snapshot(name="Snap", followers=followers, following=following)

    # Initial metrics
    m1 = temp_db.compute_metrics(snap_id)
    assert m1.actionable_unreciprocated_count == 1
    assert m1.whitelisted_count == 0

    # Whitelist celeb_brand
    temp_db.record_decision("celeb_brand", DecisionType.WHITELIST, tags=["celebrity"])
    m2 = temp_db.compute_metrics(snap_id)
    assert m2.whitelisted_count == 1
    assert m2.actionable_unreciprocated_count == 0  # Recomputed: whitelisted accounts excluded!

    # Test swipe deck: celeb_brand is no longer in pending deck
    deck = temp_db.get_swipe_deck(snap_id)
    assert len(deck) == 0

    # Undo decision
    undone = temp_db.undo_last_decision()
    assert undone["username"] == "celeb_brand"
    assert undone["restored_decision"] == "unreviewed"

    m3 = temp_db.compute_metrics(snap_id)
    assert m3.whitelisted_count == 0
    assert m3.actionable_unreciprocated_count == 1

    deck_after_undo = temp_db.get_swipe_deck(snap_id)
    assert len(deck_after_undo) == 1
    assert deck_after_undo[0].username == "celeb_brand"


def test_get_accounts_filter(temp_db):
    followers = [ParsedEntry(username="friend_one")]
    following = [ParsedEntry(username="friend_one"), ParsedEntry(username="foe_two")]

    snap_id = temp_db.save_snapshot(name="Snap", followers=followers, following=following)
    temp_db.record_decision("foe_two", DecisionType.UNFOLLOW_CANDIDATE, tags=["inactive"])

    # Search filter
    res = temp_db.get_accounts(snap_id, search="friend")
    assert len(res) == 1
    assert res[0].username == "friend_one"

    # Decision filter
    res_dec = temp_db.get_accounts(snap_id, decision=DecisionType.UNFOLLOW_CANDIDATE)
    assert len(res_dec) == 1
    assert res_dec[0].username == "foe_two"
    assert res_dec[0].tags == ["inactive"]


def test_diff_snapshots(temp_db):
    # Snapshot 1
    snap1 = temp_db.save_snapshot(
        "Jan 2025",
        followers=[ParsedEntry("alice"), ParsedEntry("bob")],
        following=[ParsedEntry("alice"), ParsedEntry("charlie")],
    )

    # Snapshot 2: bob unfollowed you, diana followed you, you unfollowed charlie, you followed eva
    snap2 = temp_db.save_snapshot(
        "Feb 2025",
        followers=[ParsedEntry("alice"), ParsedEntry("diana")],
        following=[ParsedEntry("alice"), ParsedEntry("eva")],
    )

    diff = temp_db.diff_snapshots(snap1, snap2)
    assert [a.username for a in diff.lost_followers] == ["bob"]
    assert [a.username for a in diff.new_followers] == ["diana"]
    assert [a.username for a in diff.unfollowed_by_you] == ["charlie"]
    assert [a.username for a in diff.new_following] == ["eva"]
