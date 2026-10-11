"""Unit tests for the Firestore backend adapter and Document Bucketing pattern."""

from unittest.mock import MagicMock
import pytest
from instagram_analyzer.firestore_backend import FirestoreStorage
from instagram_analyzer.models import DecisionType, RelationshipType
from instagram_analyzer.parser import ParsedEntry


def test_firestore_bucketing_logic():
    # Mock Firestore Client
    mock_client = MagicMock()
    mock_batch = MagicMock()
    mock_client.batch.return_value = mock_batch

    storage = FirestoreStorage(client=mock_client)

    followers = [ParsedEntry(username="alice"), ParsedEntry(username="bob")]
    following = [ParsedEntry(username="alice"), ParsedEntry(username="charlie")]

    snap_id = storage.save_snapshot("Test Snap", followers, following, user_id="test_user_1")
    assert snap_id.startswith("snap_")
    assert mock_batch.set.called
    assert mock_batch.commit.called


def test_firestore_record_decision():
    mock_client = MagicMock()
    storage = FirestoreStorage(client=mock_client)

    storage.record_decision(
        username="natgeo",
        decision=DecisionType.WHITELIST,
        user_id="test_user_2",
        tags=["media"]
    )
    assert mock_client.collection.called
