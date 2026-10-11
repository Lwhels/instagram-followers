"""Additional comprehensive tests for API endpoints and file upload workflows."""

import io
import json
import os
import tempfile
import zipfile
import pytest
from fastapi.testclient import TestClient
from instagram_analyzer.api import create_app
from instagram_analyzer.models import DecisionType, RelationshipType


@pytest.fixture
def client_with_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    app = create_app(db_path=path)
    test_client = TestClient(app)
    yield test_client
    if os.path.exists(path):
        os.remove(path)


def test_batch_decision(client_with_db):
    client_with_db.post("/api/demo/load")
    res = client_with_db.post("/api/batch/decision", json={
        "usernames": ["natgeo", "nasa", "wired"],
        "decision": DecisionType.WHITELIST.value,
        "tags": ["trusted"]
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["updated_count"] == 3
    assert data["metrics"]["whitelisted_count"] >= 3


def test_snapshots_list_and_diff(client_with_db):
    client_with_db.post("/api/demo/load?snapshot_name=Snap1")
    client_with_db.post("/api/demo/load?snapshot_name=Snap2")

    res_list = client_with_db.get("/api/snapshots")
    assert res_list.status_code == 200
    snaps = res_list.json()
    assert len(snaps) == 2

    res_diff = client_with_db.post(f"/api/snapshots/diff?snapshot_a_id={snaps[0]['id']}&snapshot_b_id={snaps[1]['id']}")
    assert res_diff.status_code == 200
    diff = res_diff.json()
    assert "snapshot_a_name" in diff


def test_upload_html_files(client_with_db):
    followers_html = '<a href="https://instagram.com/user_a">user_a</a>'
    following_html = '<a href="https://instagram.com/user_a">user_a</a><a href="https://instagram.com/user_b">user_b</a>'

    files = {
        "followers_file": ("followers.html", io.BytesIO(followers_html.encode("utf-8")), "text/html"),
        "following_file": ("following.html", io.BytesIO(following_html.encode("utf-8")), "text/html"),
    }
    data = {"snapshot_name": "UploadTest"}

    res = client_with_db.post("/api/upload", data=data, files=files)
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["success"] is True
    assert res_data["metrics"]["total_following"] == 2
    assert res_data["metrics"]["total_followers"] == 1
    assert res_data["metrics"]["mutual_count"] == 1
    assert res_data["metrics"]["unreciprocated_raw_count"] == 1


def test_upload_zip_archive(client_with_db):
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as z:
        z.writestr("followers_and_following/followers_1.html", '<a href="https://instagram.com/fan_1">fan_1</a>')
        z.writestr("followers_and_following/following.html", '<a href="https://instagram.com/idol_1">idol_1</a>')
    zip_buf.seek(0)

    files = {
        "zip_file": ("export.zip", zip_buf, "application/zip"),
    }
    res = client_with_db.post("/api/upload", data={"snapshot_name": "ZipTest"}, files=files)
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["success"] is True
    assert res_data["metrics"]["total_following"] == 1
    assert res_data["metrics"]["total_followers"] == 1
