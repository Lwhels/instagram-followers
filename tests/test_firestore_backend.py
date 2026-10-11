"""Comprehensive unit tests for Cloud Firestore backend adapter.
Verifies Document Bucketing, multi-bucket splitting, merged decisions,
metrics calculation, and batch limits.
"""

from unittest.mock import MagicMock, call
import pytest
from instagram_analyzer.firestore_backend import BUCKET_SIZE, FirestoreStorage
from instagram_analyzer.models import DecisionType, RelationshipType
from instagram_analyzer.parser import ParsedEntry


@pytest.fixture
def mock_db():
    client = MagicMock()
    batch = MagicMock()
    client.batch.return_value = batch
    return client, batch


def test_firestore_multi_bucket_splitting(mock_db):
    client, batch = mock_db
    storage = FirestoreStorage(client=client)

    # Generate 1,250 accounts (should split into 3 buckets: 500, 500, 250)
    followers = [ParsedEntry(username=f"user_{i}") for i in range(1250)]
    following = [ParsedEntry(username=f"user_{i}") for i in range(500, 1500)]

    snap_id = storage.save_snapshot(
        name="Large Snapshot",
        followers=followers,
        following=following,
        user_id="user_large",
    )

    assert snap_id.startswith("snap_")
    # Verify metadata set was called
    snap_ref = client.collection("users").document("user_large").collection("snapshots").document(snap_id)
    assert snap_ref.set.called

    # Verify 3 buckets were written to batch
    assert batch.set.call_count == 3
    assert batch.commit.called


def test_firestore_record_and_get_decisions(mock_db):
    client, batch = mock_db
    storage = FirestoreStorage(client=client)

    # 1. Record decision
    storage.record_decision(
        username="natgeo",
        decision=DecisionType.WHITELIST,
        user_id="u123",
        tags=["nature", "media"],
        notes="Verified official account",
    )

    dec_doc_ref = client.collection("users").document("u123").collection("settings").document("decisions")
    assert dec_doc_ref.set.called
    call_args = dec_doc_ref.set.call_args[0][0]
    assert "natgeo" in call_args
    assert call_args["natgeo"]["decision"] == DecisionType.WHITELIST.value
    assert call_args["natgeo"]["tags"] == ["nature", "media"]

    # 2. Get decisions when document exists
    mock_dec_snapshot = MagicMock()
    mock_dec_snapshot.exists = True
    mock_dec_snapshot.to_dict.return_value = {
        "natgeo": {"decision": "whitelist", "tags": ["nature"], "notes": "Official"},
        "spam_bot": {"decision": "unfollow_candidate", "tags": ["bot"], "notes": None},
    }
    dec_doc_ref.get.return_value = mock_dec_snapshot

    decisions = storage.get_decisions(user_id="u123")
    assert len(decisions) == 2
    assert decisions["natgeo"]["decision"] == "whitelist"

    # 3. Get decisions when document does not exist
    mock_dec_snapshot.exists = False
    mock_dec_snapshot.to_dict.return_value = None
    empty_decisions = storage.get_decisions(user_id="u123")
    assert empty_decisions == {}


def test_firestore_get_snapshot_accounts_and_metrics(mock_db):
    client, batch = mock_db
    storage = FirestoreStorage(client=client)

    # Setup mock bucket stream
    bucket_1 = MagicMock()
    bucket_1.to_dict.return_value = {
        "accounts": [
            {"u": "friend_alex", "rel": "mutual", "t": "Nov 4, 2024"},
            {"u": "fan_carol", "rel": "fan", "t": "Jan 1, 2025"},
            {"u": "celeb_elon", "rel": "unreciprocated", "t": "Oct 12, 2023"},
            {"u": "ghost_dave", "rel": "unreciprocated", "t": "Aug 5, 2022"},
        ]
    }

    snap_ref = MagicMock()
    snap_ref.collection("buckets").stream.return_value = [bucket_1]

    mock_snap_doc = MagicMock()
    mock_snap_doc.exists = True
    mock_snap_doc.to_dict.return_value = {
        "follower_count": 2,
        "following_count": 3,
    }
    snap_ref.get.return_value = mock_snap_doc

    mock_user_ref = MagicMock()
    mock_user_ref.collection("snapshots").document.return_value = snap_ref
    storage._user_ref = MagicMock(return_value=mock_user_ref)

    # Setup mock decisions
    dec_doc_ref = MagicMock()
    mock_dec = MagicMock()
    mock_dec.exists = True
    mock_dec.to_dict.return_value = {
        "celeb_elon": {"decision": "whitelist", "tags": ["tech"]},
        "ghost_dave": {"decision": "unfollow_candidate", "tags": ["inactive"]},
    }
    dec_doc_ref.get.return_value = mock_dec
    storage._decisions_ref = MagicMock(return_value=dec_doc_ref)

    # Fetch accounts
    accounts = storage.get_snapshot_accounts("snap_100", user_id="user_test")
    assert len(accounts) == 4
    alex = next(a for a in accounts if a.username == "friend_alex")
    elon = next(a for a in accounts if a.username == "celeb_elon")
    assert alex.relationship == RelationshipType.MUTUAL
    assert elon.decision == DecisionType.WHITELIST
    assert elon.tags == ["tech"]

    # Compute metrics
    metrics = storage.compute_metrics("snap_100", user_id="user_test")
    assert metrics.total_followers == 2
    assert metrics.total_following == 3
    assert metrics.mutual_count == 1
    assert metrics.fan_count == 1
    assert metrics.unreciprocated_raw_count == 2
    assert metrics.whitelisted_count == 1
    assert metrics.unfollow_candidates_count == 1
    assert metrics.actionable_unreciprocated_count == 1  # celeb_elon excluded from actionable
    assert metrics.reciprocity_rate == pytest.approx(33.33, 0.01)


def test_firestore_batch_limit_handling(mock_db):
    client, batch = mock_db
    storage = FirestoreStorage(client=client)

    # Simulate batch commit boundary when batch_count >= 400
    # Create 401 buckets (each with 1 account) by setting custom large list
    followers = [ParsedEntry(username=f"u_{i}") for i in range(405)]
    following = []

    # Patch BUCKET_SIZE temporarily
    from instagram_analyzer import firestore_backend
    original_size = firestore_backend.BUCKET_SIZE
    try:
        firestore_backend.BUCKET_SIZE = 1  # 1 account per bucket to test commit threshold
        storage.save_snapshot("Boundary Test", followers, following, user_id="u_boundary")
        # Since 405 buckets > 400 threshold, batch.commit() must have been called at least twice
        assert batch.commit.call_count >= 2
    finally:
        firestore_backend.BUCKET_SIZE = original_size
