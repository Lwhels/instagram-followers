"""Comprehensive security regression and penetration defense test suite."""

import io
import os
import sys
import tempfile
import zipfile
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from instagram_analyzer.api import create_app
from instagram_analyzer.auth import hash_password, verify_password, create_access_token, decode_access_token
from instagram_analyzer.database import Database
from instagram_analyzer.models import DecisionType, RelationshipType, UserRegisterRequest
from instagram_analyzer.parser import _clean_username, ParsedEntry, parse_zip_archive
from instagram_analyzer.upload_framework import UploadSecurityError, UploadStorage
from macos.app import wait_for_server


@pytest.fixture
def client_with_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    with tempfile.TemporaryDirectory() as upload_dir:
        app = create_app(db_path=db_path, upload_dir=upload_dir)
        client = TestClient(app)
        yield client, Database(db_path=db_path)
    if os.path.exists(db_path):
        os.remove(db_path)


def test_security_headers_present(client_with_db):
    client, _ = client_with_db
    res = client.get("/api/status")
    assert res.status_code == 200
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-frame-options"] == "SAMEORIGIN"
    assert "default-src 'self'" in res.headers["content-security-policy"]


def test_sql_like_wildcard_escaping(client_with_db):
    _, db = client_with_db
    user_id = 1
    # Save a snapshot with account having underscore and literal text
    db.save_snapshot(
        name="Security Test",
        followers=[ParsedEntry("alice_test"), ParsedEntry("alice1test")],
        following=[],
        user_id=user_id,
    )

    # In SQL LIKE, '_' matches any character if unescaped!
    # With proper escaping, searching for 'alice_' should ONLY match 'alice_test', NOT 'alice1test'
    results = db.get_accounts(search="alice_", user_id=user_id)
    usernames = [a.username for a in results]
    assert "alice_test" in usernames
    assert "alice1test" not in usernames


def test_parser_username_xss_sanitization():
    # Attempt script tag injection in username
    bad_raw = "<script>alert('xss')</script>"
    clean = _clean_username(bad_raw)
    assert clean == ""
    assert "<script>" not in clean

    entry = ParsedEntry(bad_raw)
    assert "<script>" not in entry.username
    assert entry.profile_url == "https://www.instagram.com"

    # Valid Instagram handle
    assert _clean_username("valid.user_123") == "valid.user_123"
    assert _clean_username("https://www.instagram.com/valid.user_123/") == "valid.user_123"


def test_upload_storage_windows_backslash_traversal():
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = UploadStorage(base_dir=tmpdir)
        # Create a malicious zip with backslash path traversal
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("..\\..\\evil.txt", "malicious payload")
        buf.seek(0)

        with pytest.raises(UploadSecurityError, match="Malicious archive member detected"):
            storage.save_upload_stream(buf, "exploit.zip")


def test_upload_storage_symlink_rejection():
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = UploadStorage(base_dir=tmpdir)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            info = zipfile.ZipInfo("symlink_entry")
            info.external_attr = 0o120777 << 16  # Symlink attribute
            z.writestr(info, "/etc/passwd")
        buf.seek(0)

        with pytest.raises(UploadSecurityError, match="Symlinks are disallowed"):
            storage.save_upload_stream(buf, "symlink.zip")


def test_auth_registration_validation(client_with_db):
    client, _ = client_with_db
    # Invalid email format
    res = client.post("/api/auth/register", json={"email": "not-an-email", "password": "password123"})
    assert res.status_code == 422

    # Password too short
    res = client.post("/api/auth/register", json={"email": "valid@example.com", "password": "123"})
    assert res.status_code == 422

    # Password over 128 characters (DoS prevention)
    res = client.post("/api/auth/register", json={"email": "valid@example.com", "password": "a" * 200})
    assert res.status_code == 422

    # Valid user registers successfully
    res = client.post("/api/auth/register", json={"email": "alice@security.com", "password": "securepassword123"})
    assert res.status_code == 200
    assert "access_token" in res.json()


def test_desktop_wait_for_server_scheme_validation():
    # Attempting to pass external or file:// scheme to wait_for_server should immediately raise ValueError
    with pytest.raises(ValueError, match="Refusing to probe non-local server URL"):
        wait_for_server("file:///etc/passwd")

    with pytest.raises(ValueError, match="Refusing to probe non-local server URL"):
        wait_for_server("http://evil-attacker.com")
