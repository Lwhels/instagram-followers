"""Unit tests for the upload framework and asynchronous job processing."""

import io
import os
import tempfile
import zipfile
import pytest
from fastapi.testclient import TestClient

from instagram_analyzer.api import create_app
from instagram_analyzer.upload_framework import UploadSecurityError, UploadStorage


@pytest.fixture
def upload_env():
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    staging_dir = tempfile.mkdtemp()
    app = create_app(db_path=db_path, upload_dir=staging_dir)
    client = TestClient(app)
    yield client, staging_dir
    if os.path.exists(db_path):
        os.remove(db_path)
    if os.path.exists(staging_dir):
        import shutil
        shutil.rmtree(staging_dir)


def test_upload_storage_zip_slip_prevention():
    staging = tempfile.mkdtemp()
    storage = UploadStorage(base_dir=staging)

    # Create malicious zip with path traversal
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as z:
        z.writestr("../../etc/passwd", "malicious payload")
    zip_buf.seek(0)

    with pytest.raises(UploadSecurityError) as exc_info:
        storage.save_upload_stream(zip_buf, "evil.zip")
    assert "Malicious archive member detected" in str(exc_info.value)


def test_async_upload_start_and_polling(upload_env):
    client, staging = upload_env

    # Register user
    reg = client.post("/api/auth/register", json={
        "email": "uploader@test.com",
        "password": "mypassword123"
    }).json()
    token = reg["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Prepare legitimate zip export
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as z:
        z.writestr("followers_and_following/followers_1.html", '<a href="https://instagram.com/fan_girl">fan_girl</a>')
        z.writestr("followers_and_following/following.html", '<a href="https://instagram.com/celeb_star">celeb_star</a>')
    zip_buf.seek(0)

    # Post async upload
    files = {"file": ("export.zip", zip_buf, "application/zip")}
    data = {"snapshot_name": "Async Snapshot"}
    res = client.post("/api/uploads/start", data=data, files=files, headers=headers)

    assert res.status_code == 202
    job_data = res.json()
    job_id = job_data["job_id"]
    assert job_id is not None

    # Poll status
    poll_res = client.get(f"/api/uploads/{job_id}", headers=headers)
    assert poll_res.status_code == 200
    assert poll_res.json()["job_id"] == job_id
