"""Unit tests for FollowerEngine and heuristics."""

import os
import tempfile
import pytest
from instagram_analyzer.database import Database
from instagram_analyzer.engine import FollowerEngine, suggest_tags
from instagram_analyzer.models import DecisionType, RelationshipType


@pytest.fixture
def temp_engine():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = FollowerEngine(db_path=path)
    yield engine
    if os.path.exists(path):
        os.remove(path)


def test_suggest_tags():
    assert "tech" in suggest_tags("dev_sarah")
    assert "fitness" in suggest_tags("gym_beast_john")
    assert "brand_or_media" in suggest_tags("nike_official")
    assert "creative" in suggest_tags("vintage_photo_sf")


def test_load_sample_demo(temp_engine):
    snap_id = temp_engine.load_sample_demo("Demo Test")
    assert snap_id is not None

    metrics = temp_engine.recompute(snap_id)
    assert metrics.total_followers > 50
    assert metrics.total_following > 50
    assert metrics.mutual_count > 0
    assert metrics.unreciprocated_raw_count > 0

    # Swipe right on a celeb
    m = temp_engine.swipe("natgeo", DecisionType.WHITELIST, tags=["media"])
    assert m.whitelisted_count == 1

    # Batch decision
    m2 = temp_engine.batch_decide(["wired", "openai"], DecisionType.WHITELIST, tags=["tech"])
    assert m2.whitelisted_count == 3


def test_export_formats(temp_engine):
    snap_id = temp_engine.load_sample_demo("Demo Export")

    csv_data = temp_engine.export_data(format_type="csv", snapshot_id=snap_id)
    assert "username,relationship,decision" in csv_data

    json_data = temp_engine.export_data(format_type="json", snapshot_id=snap_id)
    assert '"username"' in json_data

    md_data = temp_engine.export_data(format_type="markdown", snapshot_id=snap_id)
    assert "# Instagram Follower Audit Checklist" in md_data
