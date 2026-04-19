import base64
import io
import os
import pytest
from PIL import Image


TEST_TOKEN = "test-token-hearthlog"


def make_jpeg(width: int = 100, height: int = 100) -> bytes:
    img = Image.new("RGB", (width, height), color=(120, 100, 80))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


@pytest.fixture()
def content_dir(tmp_path):
    (tmp_path / "content" / "posts").mkdir(parents=True)
    (tmp_path / "static" / "images").mkdir(parents=True)
    return tmp_path


@pytest.fixture()
def app(content_dir, monkeypatch):
    monkeypatch.setenv("AI_BOT_API_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("BLOG_CONTENT_PATH", str(content_dir))

    import importlib
    import api as api_module
    importlib.reload(api_module)

    api_module.app.config["TESTING"] = True
    return api_module.app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def auth(client):
    return {"X-API-Token": TEST_TOKEN}


@pytest.fixture()
def mock_hugo_ok(monkeypatch):
    monkeypatch.setattr("api.rebuild_site", lambda *a, **kw: (True, "built"))


@pytest.fixture()
def mock_hugo_fail(monkeypatch):
    monkeypatch.setattr("api.rebuild_site", lambda *a, **kw: (False, "hugo exploded"))
