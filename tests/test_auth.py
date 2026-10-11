"""Unit and integration tests for authentication system."""

import os
import tempfile
import pytest
from fastapi.testclient import TestClient

from instagram_analyzer.api import create_app
from instagram_analyzer.auth import hash_password, verify_password


@pytest.fixture
def auth_client():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    app = create_app(db_path=path)
    client = TestClient(app)
    yield client
    if os.path.exists(path):
        os.remove(path)


def test_password_hashing():
    pw = "SuperSecret123!"
    hashed = hash_password(pw)
    assert hashed != pw
    assert verify_password(pw, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_register_and_login_flow(auth_client):
    # 1. Register new user
    reg_res = auth_client.post("/api/auth/register", json={
        "email": "sarah@example.com",
        "password": "validpassword123",
        "display_name": "Sarah Connor"
    })
    assert reg_res.status_code == 200
    data = reg_res.json()
    assert "access_token" in data
    assert data["user"]["email"] == "sarah@example.com"
    token = data["access_token"]

    # 2. Reject duplicate email
    dup_res = auth_client.post("/api/auth/register", json={
        "email": "sarah@example.com",
        "password": "anotherpassword",
    })
    assert dup_res.status_code == 400

    # 3. Reject short password
    short_res = auth_client.post("/api/auth/register", json={
        "email": "john@example.com",
        "password": "123",
    })
    assert short_res.status_code == 400

    # 4. Login with wrong password
    wrong_res = auth_client.post("/api/auth/login", json={
        "email": "sarah@example.com",
        "password": "wrongpassword",
    })
    assert wrong_res.status_code == 401

    # 5. Login with correct password
    login_res = auth_client.post("/api/auth/login", json={
        "email": "sarah@example.com",
        "password": "validpassword123",
    })
    assert login_res.status_code == 200
    assert "access_token" in login_res.json()

    # 6. Fetch /api/auth/me with Bearer token
    me_res = auth_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "sarah@example.com"


def test_demo_auth_login(auth_client):
    res = auth_client.post("/api/auth/demo")
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["user"]["id"] == 1
