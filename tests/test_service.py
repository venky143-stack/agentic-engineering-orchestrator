import importlib
from fastapi.testclient import TestClient


def make_client(tmp_path, monkeypatch):
    import service.app as module
    monkeypatch.setattr(module, "DB_PATH", tmp_path / "test.db")
    module.initialize_db()
    return module, TestClient(module.app)


def test_create_redirect_and_analytics(tmp_path, monkeypatch):
    module, client = make_client(tmp_path, monkeypatch)
    response = client.post("/api/urls", json={"url": "https://example.com/some/path"})
    assert response.status_code == 201
    data = response.json()
    assert data["code"]
    assert data["original_url"] == "https://example.com/some/path"
    redirect = client.get(f"/{data['code']}", follow_redirects=False)
    assert redirect.status_code == 307
    assert redirect.headers["location"] == "https://example.com/some/path"
    analytics = client.get(f"/api/urls/{data['code']}/analytics")
    assert analytics.status_code == 200
    assert analytics.json()["click_count"] == 1


def test_invalid_url_rejected(tmp_path, monkeypatch):
    _, client = make_client(tmp_path, monkeypatch)
    response = client.post("/api/urls", json={"url": "javascript:alert(1)"})
    assert response.status_code == 422


def test_unknown_code_returns_404(tmp_path, monkeypatch):
    _, client = make_client(tmp_path, monkeypatch)
    assert client.get("/missing-code").status_code == 404
    assert client.get("/api/urls/missing-code/analytics").status_code == 404
