import pytest
from app import app as appmod

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(appmod, "DB", str(tmp_path / "t.db"))
    return appmod.app.test_client()

def test_health(client):
    assert client.get("/health").json["status"] == "ok"

def test_notes_require_login(client):
    assert client.get("/api/notes").status_code == 401

def test_register_login_crud(client):
    creds = {"username": "a", "password": "b"}
    assert client.post("/api/register", json=creds).status_code == 201
    assert client.post("/api/login", json=creds).status_code == 200
    nid = client.post("/api/notes", json={"title": "t", "body": "x"}).json["id"]
    assert len(client.get("/api/notes").json) == 1
    assert client.put(f"/api/notes/{nid}", json={"title": "t2"}).status_code == 200
    assert client.delete(f"/api/notes/{nid}").status_code == 200