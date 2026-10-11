"""Unit tests ensuring multi-tenant data isolation."""

import os
import tempfile
import pytest
from fastapi.testclient import TestClient

from instagram_analyzer.api import create_app
from instagram_analyzer.models import DecisionType


@pytest.fixture
def multi_tenant_client():
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    app = create_app(db_path=db_path)
    client = TestClient(app)
    yield client
    if os.path.exists(db_path):
        os.remove(db_path)


def test_user_data_isolation(multi_tenant_client):
    client = multi_tenant_client

    # User A
    user_a = client.post("/api/auth/register", json={
        "email": "userA@test.com",
        "password": "passwordA123"
    }).json()
    headers_a = {"Authorization": f"Bearer {user_a['access_token']}"}

    # User B
    user_b = client.post("/api/auth/register", json={
        "email": "userB@test.com",
        "password": "passwordB123"
    }).json()
    headers_b = {"Authorization": f"Bearer {user_b['access_token']}"}

    # User A seeds demo data
    demo_a = client.post("/api/demo/load?snapshot_name=UserA_Data", headers=headers_a).json()
    snap_a_id = demo_a["snapshot_id"]

    # Verify User A has snapshots
    snaps_a = client.get("/api/snapshots", headers=headers_a).json()
    assert len(snaps_a) == 1
    assert snaps_a[0]["name"] == "UserA_Data"

    # Verify User B has NO snapshots yet (complete isolation!)
    snaps_b = client.get("/api/snapshots", headers=headers_b).json()
    assert len(snaps_b) == 0

    # User A swipes on an account
    client.post("/api/swipe/decision", json={
        "username": "natgeo",
        "decision": DecisionType.WHITELIST.value,
        "tags": ["nature"]
    }, headers=headers_a)

    # Check metrics for A
    metrics_a = client.get("/api/metrics", headers=headers_a).json()
    assert metrics_a["whitelisted_count"] >= 1

    # Check metrics for B (still 0 data)
    metrics_b = client.get("/api/metrics", headers=headers_b).json()
    assert metrics_b["total_following"] == 0
    assert metrics_b["whitelisted_count"] == 0
