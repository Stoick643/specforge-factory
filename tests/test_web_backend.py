"""Tests for the SpecForge Web backend."""

import pytest
from fastapi.testclient import TestClient

from web.backend.main import app, _jobs


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_jobs():
    """Clear job store between tests."""
    _jobs.clear()
    yield
    _jobs.clear()


class TestHealthEndpoint:
    def test_health(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data


class TestExamplesEndpoint:
    def test_list_examples(self, client):
        resp = client.get("/api/examples")
        assert resp.status_code == 200
        data = resp.json()
        assert "examples" in data
        assert len(data["examples"]) >= 1
        # Check the URL shortener example is there
        names = [e["name"] for e in data["examples"]]
        assert "advanced-shortener-sqlite" in names

    def test_example_has_content(self, client):
        resp = client.get("/api/examples")
        example = resp.json()["examples"][0]
        assert "title" in example
        assert "content" in example
        assert len(example["content"]) > 100  # Not empty


class TestJobFiles:
    def test_get_files_not_found(self, client):
        resp = client.get("/api/jobs/nonexistent/files")
        assert resp.status_code == 200  # Returns error in body
        # Job doesn't exist

    def test_get_files_exists(self, client):
        _jobs["test-123"] = {
            "files": {"app/main.py": "print('hello')"},
            "status": "success",
        }
        resp = client.get("/api/jobs/test-123/files")
        assert resp.status_code == 200
        data = resp.json()
        assert data["files"]["app/main.py"] == "print('hello')"
        assert data["status"] == "success"


class TestDownloadZip:
    def test_download_not_found(self, client):
        resp = client.get("/api/jobs/nonexistent/download")
        assert resp.status_code == 404

    def test_download_zip(self, client):
        _jobs["test-456"] = {
            "files": {
                "app/main.py": "from fastapi import FastAPI\napp = FastAPI()",
                "requirements.txt": "fastapi\nuvicorn",
            },
            "status": "success",
        }
        resp = client.get("/api/jobs/test-456/download")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
        assert "test-456.zip" in resp.headers["content-disposition"]
        # Verify it's actually a valid ZIP
        import zipfile
        from io import BytesIO
        zf = zipfile.ZipFile(BytesIO(resp.content))
        names = zf.namelist()
        assert "app/main.py" in names
        assert "requirements.txt" in names
        assert zf.read("requirements.txt").decode() == "fastapi\nuvicorn"


class TestFrontendServing:
    def test_serves_index_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"SpecForge" in resp.content
        assert b"monaco-editor" in resp.content

    def test_serves_html_content_type(self, client):
        resp = client.get("/")
        assert "text/html" in resp.headers.get("content-type", "")


class TestWebSocketGenerate:
    def test_empty_spec_returns_error(self, client):
        with client.websocket_connect("/ws/generate") as ws:
            ws.send_json({"spec": "", "api_key": "test"})
            data = ws.receive_json()
            assert data["event"] == "error"
            assert "Empty" in data["message"]
