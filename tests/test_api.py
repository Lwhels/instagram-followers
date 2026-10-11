"""Unit tests for FastAPI endpoints."""

import os
import tempfile
import pytest
from fastapi.testclient import TestClient
from instagram_analyzer.api import create_app
from instagram_analyzer.models import DecisionType, RelationshipType


@pytest.fixture
def client():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    app = create_app(db_path=path)
    test_client = TestClient(app)
    yield test_client
    if os.path.exists(path):
        os.remove(path)


def test_status_empty(client):
    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["has_data"] is False


def test_demo_load_and_metrics(client):
    res = client.post("/api/demo/load?snapshot_name=TestDemo")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["snapshot_id"] == 1
    assert data["metrics"]["total_followers"] > 0

    # Get metrics endpoint
    res_m = client.get("/api/metrics")
    assert res_m.status_code == 200
    metrics = res_m.json()
    assert metrics["total_following"] > 0

    # Get accounts
    res_acc = client.get("/api/accounts?limit=10")
    assert res_acc.status_code == 200
    accounts = res_acc.json()
    assert len(accounts) == 10

    # Get swipe deck
    res_deck = client.get("/api/swipe/deck?limit=5")
    assert res_deck.status_code == 200
    deck = res_deck.json()
    assert len(deck) > 0
    candidate = deck[0]["username"]

    # Swipe right (whitelist)
    res_swipe = client.post("/api/swipe/decision", json={
        "username": candidate,
        "decision": DecisionType.WHITELIST.value,
        "tags": ["celeb"]
    })
    assert res_swipe.status_code == 200
    assert res_swipe.json()["metrics"]["whitelisted_count"] >= 1

    # Undo
    res_undo = client.post("/api/swipe/undo")
    assert res_undo.status_code == 200
    assert res_undo.json()["restored"]["username"] == candidate

    # Recompute
    res_recompute = client.post("/api/recompute")
    assert res_recompute.status_code == 200

    # Export
    res_exp = client.get("/api/export?format=csv")
    assert res_exp.status_code == 200
    assert "text/csv" in res_exp.headers["content-type"]

    # Index page
    res_html = client.get("/")
    assert res_html.status_code == 200
    assert "Follower Vault" in res_html.text
