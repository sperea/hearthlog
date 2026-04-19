"""
Test suite for the Hearthlog API.
Run: pytest test_api.py -v
"""
import base64
import io
import os
from pathlib import Path

import pytest
from PIL import Image

from conftest import make_jpeg, b64, TEST_TOKEN


# ── Auth ──────────────────────────────────────────────────────────────────────

class TestAuth:
    def test_no_token_returns_401(self, client):
        assert client.get("/api/health").status_code == 401

    def test_wrong_token_returns_401(self, client):
        r = client.get("/api/health", headers={"X-API-Token": "wrong"})
        assert r.status_code == 401

    def test_empty_token_returns_401(self, client):
        r = client.get("/api/health", headers={"X-API-Token": ""})
        assert r.status_code == 401

    def test_valid_token_passes(self, client, auth, mock_hugo_ok):
        assert client.get("/api/health", headers=auth).status_code == 200


# ── Health ────────────────────────────────────────────────────────────────────

class TestHealth:
    def test_returns_ok(self, client, auth):
        r = client.get("/api/health", headers=auth)
        data = r.get_json()
        assert data["status"] == "ok"
        assert data["service"] == "blog-api"


# ── Create post — validation ──────────────────────────────────────────────────

class TestCreatePostValidation:
    def test_no_body_returns_400(self, client, auth, mock_hugo_ok):
        r = client.post("/api/posts", headers=auth, content_type="application/json")
        assert r.status_code == 400

    def test_missing_title_returns_400(self, client, auth, mock_hugo_ok):
        r = client.post("/api/posts", headers=auth, json={
            "content": "texto"
        })
        assert r.status_code == 400
        assert "title" in r.get_json()["error"]

    def test_missing_content_returns_400(self, client, auth, mock_hugo_ok):
        r = client.post("/api/posts", headers=auth, json={
            "title": "Título"
        })
        assert r.status_code == 400
        assert "content" in r.get_json()["error"]

    def test_blank_title_returns_400(self, client, auth, mock_hugo_ok):
        r = client.post("/api/posts", headers=auth, json={
            "title": "   ", "content": "texto"
        })
        assert r.status_code == 400

    def test_invalid_date_format_returns_400(self, client, auth, mock_hugo_ok):
        r = client.post("/api/posts", headers=auth, json={
            "title": "Test", "content": "texto", "date": "19-04-2026"
        })
        assert r.status_code == 400
        assert "date" in r.get_json()["error"]

    def test_invalid_date_value_returns_400(self, client, auth, mock_hugo_ok):
        r = client.post("/api/posts", headers=auth, json={
            "title": "Test", "content": "texto", "date": "2026-13-99"
        })
        assert r.status_code == 400


# ── Create post — success ─────────────────────────────────────────────────────

class TestCreatePost:
    def test_minimal_post_returns_201(self, client, auth, mock_hugo_ok):
        r = client.post("/api/posts", headers=auth, json={
            "title": "Día en el parque",
            "content": "Hoy fuimos al parque.",
        })
        assert r.status_code == 201
        data = r.get_json()
        assert data["status"] == "published"
        assert data["photos_saved"] == []
        assert data["photos_failed"] == []

    def test_post_file_created(self, client, auth, mock_hugo_ok, content_dir):
        client.post("/api/posts", headers=auth, json={
            "title": "Viaje a la montaña",
            "content": "Fuimos a la montaña.",
            "date": "2026-04-19",
        })
        posts = list((content_dir / "content" / "posts").glob("*.md"))
        assert len(posts) == 1
        assert posts[0].name == "2026-04-19-viaje-a-la-montana.md"

    def test_post_filename_slug(self, client, auth, mock_hugo_ok, content_dir):
        client.post("/api/posts", headers=auth, json={
            "title": "¡Feliz cumpleaños, mamá!",
            "content": "texto",
            "date": "2026-06-01",
        })
        posts = list((content_dir / "content" / "posts").glob("*.md"))
        assert posts[0].name == "2026-06-01-feliz-cumpleanos-mama.md"

    def test_post_frontmatter_content(self, client, auth, mock_hugo_ok, content_dir):
        client.post("/api/posts", headers=auth, json={
            "title": "Vacaciones",
            "content": "Este verano lo pasamos genial.",
            "date": "2026-08-01",
        })
        md = (content_dir / "content" / "posts" / "2026-08-01-vacaciones.md").read_text()
        assert 'title: "Vacaciones"' in md
        assert "date: 2026-08-01" in md
        assert "draft: false" in md
        assert "Este verano lo pasamos genial." in md

    def test_date_defaults_to_today(self, client, auth, mock_hugo_ok, content_dir):
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        client.post("/api/posts", headers=auth, json={
            "title": "Post sin fecha", "content": "texto"
        })
        posts = list((content_dir / "content" / "posts").glob("*.md"))
        assert posts[0].name.startswith(today)

    def test_hugo_failure_returns_207(self, client, auth, mock_hugo_fail):
        r = client.post("/api/posts", headers=auth, json={
            "title": "Test", "content": "texto"
        })
        assert r.status_code == 207
        data = r.get_json()
        assert data["status"] == "partial"
        assert "hugo_error" in data

    def test_post_still_saved_on_hugo_failure(self, client, auth, mock_hugo_fail, content_dir):
        client.post("/api/posts", headers=auth, json={
            "title": "Post guardado", "content": "texto", "date": "2026-05-01"
        })
        posts = list((content_dir / "content" / "posts").glob("*.md"))
        assert len(posts) == 1


# ── Photos ────────────────────────────────────────────────────────────────────

class TestPhotos:
    def test_post_with_photo_returns_201(self, client, auth, mock_hugo_ok):
        r = client.post("/api/posts", headers=auth, json={
            "title": "Foto del jardín",
            "content": "El jardín está precioso.",
            "date": "2026-04-20",
            "photos": [{"filename": "jardin.jpg", "data": b64(make_jpeg())}],
        })
        assert r.status_code == 201
        data = r.get_json()
        assert len(data["photos_saved"]) == 1
        assert data["photos_failed"] == []

    def test_photo_file_saved_to_disk(self, client, auth, mock_hugo_ok, content_dir):
        client.post("/api/posts", headers=auth, json={
            "title": "Playa",
            "content": "Sol y mar.",
            "date": "2026-07-15",
            "photos": [{"filename": "playa.jpg", "data": b64(make_jpeg())}],
        })
        images = list((content_dir / "static" / "images" / "2026-07-15").glob("*.jpg"))
        assert len(images) == 1

    def test_multiple_photos(self, client, auth, mock_hugo_ok, content_dir):
        photos = [
            {"filename": f"foto{i}.jpg", "data": b64(make_jpeg())} for i in range(3)
        ]
        r = client.post("/api/posts", headers=auth, json={
            "title": "Tres fotos",
            "content": "texto",
            "date": "2026-04-21",
            "photos": photos,
        })
        assert r.status_code == 201
        assert len(r.get_json()["photos_saved"]) == 3

    def test_large_photo_resized(self, client, auth, mock_hugo_ok, content_dir):
        r = client.post("/api/posts", headers=auth, json={
            "title": "Foto grande",
            "content": "texto",
            "date": "2026-04-22",
            "photos": [{"filename": "grande.jpg", "data": b64(make_jpeg(3000, 2000))}],
        })
        assert r.status_code == 201
        saved = list((content_dir / "static" / "images" / "2026-04-22").glob("*.jpg"))
        img = Image.open(saved[0])
        assert max(img.size) <= 1920

    def test_rgba_photo_converted_to_rgb(self, client, auth, mock_hugo_ok, content_dir):
        buf = io.BytesIO()
        Image.new("RGBA", (100, 100), (255, 0, 0, 128)).save(buf, format="PNG")
        r = client.post("/api/posts", headers=auth, json={
            "title": "PNG con alfa",
            "content": "texto",
            "date": "2026-04-23",
            "photos": [{"filename": "alpha.png", "data": b64(buf.getvalue())}],
        })
        assert r.status_code == 201
        assert len(r.get_json()["photos_saved"]) == 1

    def test_invalid_base64_photo_skipped(self, client, auth, mock_hugo_ok):
        r = client.post("/api/posts", headers=auth, json={
            "title": "Foto mala",
            "content": "texto",
            "date": "2026-04-24",
            "photos": [{"filename": "mala.jpg", "data": "esto-no-es-base64!!!"}],
        })
        assert r.status_code in (201, 207)
        data = r.get_json()
        assert "mala.jpg" in data["photos_failed"]
        assert data["photos_saved"] == []

    def test_photo_exceeding_size_limit_skipped(self, client, auth, mock_hugo_ok, monkeypatch):
        monkeypatch.setattr("api.MAX_PHOTO_SIZE_MB", 0)
        r = client.post("/api/posts", headers=auth, json={
            "title": "Foto enorme",
            "content": "texto",
            "date": "2026-04-25",
            "photos": [{"filename": "enorme.jpg", "data": b64(make_jpeg())}],
        })
        data = r.get_json()
        assert "enorme.jpg" in data["photos_failed"]

    def test_photo_without_filename_skipped(self, client, auth, mock_hugo_ok):
        r = client.post("/api/posts", headers=auth, json={
            "title": "Sin nombre",
            "content": "texto",
            "photos": [{"data": b64(make_jpeg())}],
        })
        data = r.get_json()
        assert data["photos_saved"] == []

    def test_photo_filename_slugified(self, client, auth, mock_hugo_ok, content_dir):
        client.post("/api/posts", headers=auth, json={
            "title": "Test slug",
            "content": "texto",
            "date": "2026-04-26",
            "photos": [{"filename": "Mi Foto Bonita.jpg", "data": b64(make_jpeg())}],
        })
        images = list((content_dir / "static" / "images" / "2026-04-26").glob("*.jpg"))
        assert images[0].name == "mi-foto-bonita.jpg"

    def test_featured_image_in_frontmatter(self, client, auth, mock_hugo_ok, content_dir):
        client.post("/api/posts", headers=auth, json={
            "title": "Con portada",
            "content": "texto",
            "date": "2026-04-27",
            "photos": [{"filename": "portada.jpg", "data": b64(make_jpeg())}],
        })
        md = (content_dir / "content" / "posts" / "2026-04-27-con-portada.md").read_text()
        assert "featured_image" in md
        assert "2026-04-27" in md

    def test_photo_embedded_in_markdown(self, client, auth, mock_hugo_ok, content_dir):
        client.post("/api/posts", headers=auth, json={
            "title": "Fotos en texto",
            "content": "texto",
            "date": "2026-04-28",
            "photos": [{"filename": "img.jpg", "data": b64(make_jpeg())}],
        })
        md = (content_dir / "content" / "posts" / "2026-04-28-fotos-en-texto.md").read_text()
        assert "![" in md
        assert "/images/2026-04-28/" in md


# ── List posts ────────────────────────────────────────────────────────────────

class TestListPosts:
    def test_empty_list(self, client, auth):
        r = client.get("/api/posts", headers=auth)
        assert r.status_code == 200
        assert r.get_json()["posts"] == []

    def test_lists_existing_posts(self, client, auth, mock_hugo_ok, content_dir):
        for title, date in [("Uno", "2026-01-01"), ("Dos", "2026-02-01")]:
            client.post("/api/posts", headers=auth, json={
                "title": title, "content": "texto", "date": date
            })
        r = client.get("/api/posts", headers=auth)
        posts = r.get_json()["posts"]
        assert len(posts) == 2
        assert posts == sorted(posts)

    def test_only_md_files_listed(self, client, auth, content_dir):
        (content_dir / "content" / "posts" / "draft.txt").write_text("x")
        r = client.get("/api/posts", headers=auth)
        assert r.get_json()["posts"] == []


# ── Get single post ───────────────────────────────────────────────────────────

class TestGetPost:
    def test_get_existing_post(self, client, auth, mock_hugo_ok):
        client.post("/api/posts", headers=auth, json={
            "title": "Mi post", "content": "Contenido aquí.", "date": "2026-05-01"
        })
        r = client.get("/api/posts/2026-05-01-mi-post", headers=auth)
        assert r.status_code == 200
        data = r.get_json()
        assert data["slug"] == "2026-05-01-mi-post"
        assert "Mi post" in data["title"]
        assert data["draft"] is False

    def test_get_nonexistent_post_returns_404(self, client, auth):
        assert client.get("/api/posts/no-existe", headers=auth).status_code == 404


# ── Update post ───────────────────────────────────────────────────────────────

class TestUpdatePost:
    def _create(self, client, auth):
        client.post("/api/posts", headers=auth, json={
            "title": "Post original", "content": "Texto original.", "date": "2026-05-10"
        })
        return "2026-05-10-post-original"

    def test_update_returns_200(self, client, auth, mock_hugo_ok):
        slug = self._create(client, auth)
        r = client.put(f"/api/posts/{slug}", headers=auth, json={
            "title": "Post original", "content": "Texto actualizado."
        })
        assert r.status_code == 200
        assert r.get_json()["status"] == "updated"

    def test_update_changes_content_on_disk(self, client, auth, mock_hugo_ok, content_dir):
        slug = self._create(client, auth)
        client.put(f"/api/posts/{slug}", headers=auth, json={
            "title": "Post original", "content": "Nuevo contenido editado."
        })
        md = (content_dir / "content" / "posts" / f"{slug}.md").read_text()
        assert "Nuevo contenido editado." in md
        assert "Texto original." not in md

    def test_update_nonexistent_returns_404(self, client, auth, mock_hugo_ok):
        r = client.put("/api/posts/no-existe", headers=auth, json={
            "title": "x", "content": "y"
        })
        assert r.status_code == 404

    def test_update_missing_content_returns_400(self, client, auth, mock_hugo_ok):
        slug = self._create(client, auth)
        r = client.put(f"/api/posts/{slug}", headers=auth, json={"title": "x"})
        assert r.status_code == 400

    def test_update_preserves_draft_status(self, client, auth, mock_hugo_ok, content_dir):
        slug = self._create(client, auth)
        client.patch(f"/api/posts/{slug}/draft", headers=auth, json={"draft": True})
        client.put(f"/api/posts/{slug}", headers=auth, json={
            "title": "Post original", "content": "Nuevo texto."
        })
        md = (content_dir / "content" / "posts" / f"{slug}.md").read_text()
        assert "draft: true" in md

    def test_update_with_new_photos(self, client, auth, mock_hugo_ok, content_dir):
        slug = self._create(client, auth)
        r = client.put(f"/api/posts/{slug}", headers=auth, json={
            "title": "Post original",
            "content": "Con foto nueva.",
            "date": "2026-05-10",
            "photos": [{"filename": "nueva.jpg", "data": b64(make_jpeg())}],
        })
        assert r.status_code == 200
        assert len(r.get_json()["photos_saved"]) == 1

    def test_update_hugo_failure_returns_207(self, client, auth, mock_hugo_ok, mock_hugo_fail, content_dir):
        slug = self._create(client, auth)
        r = client.put(f"/api/posts/{slug}", headers=auth, json={
            "title": "Post original", "content": "texto"
        })
        assert r.status_code == 207


# ── Draft toggle ──────────────────────────────────────────────────────────────

class TestDraftToggle:
    def _create(self, client, auth):
        client.post("/api/posts", headers=auth, json={
            "title": "Post visible", "content": "texto", "date": "2026-06-01"
        })
        return "2026-06-01-post-visible"

    def test_set_draft_true_returns_200(self, client, auth, mock_hugo_ok):
        slug = self._create(client, auth)
        r = client.patch(f"/api/posts/{slug}/draft", headers=auth, json={"draft": True})
        assert r.status_code == 200
        assert r.get_json()["draft"] is True

    def test_set_draft_false_returns_200(self, client, auth, mock_hugo_ok):
        slug = self._create(client, auth)
        client.patch(f"/api/posts/{slug}/draft", headers=auth, json={"draft": True})
        r = client.patch(f"/api/posts/{slug}/draft", headers=auth, json={"draft": False})
        assert r.status_code == 200
        assert r.get_json()["draft"] is False

    def test_draft_true_written_to_file(self, client, auth, mock_hugo_ok, content_dir):
        slug = self._create(client, auth)
        client.patch(f"/api/posts/{slug}/draft", headers=auth, json={"draft": True})
        md = (content_dir / "content" / "posts" / f"{slug}.md").read_text()
        assert "draft: true" in md

    def test_draft_false_written_to_file(self, client, auth, mock_hugo_ok, content_dir):
        slug = self._create(client, auth)
        client.patch(f"/api/posts/{slug}/draft", headers=auth, json={"draft": True})
        client.patch(f"/api/posts/{slug}/draft", headers=auth, json={"draft": False})
        md = (content_dir / "content" / "posts" / f"{slug}.md").read_text()
        assert "draft: false" in md
        assert "draft: true" not in md

    def test_draft_nonexistent_post_returns_404(self, client, auth):
        r = client.patch("/api/posts/no-existe/draft", headers=auth, json={"draft": True})
        assert r.status_code == 404

    def test_missing_draft_field_returns_400(self, client, auth, mock_hugo_ok):
        slug = self._create(client, auth)
        r = client.patch(f"/api/posts/{slug}/draft", headers=auth, json={})
        assert r.status_code == 400


# ── Delete post ───────────────────────────────────────────────────────────────

class TestDeletePost:
    def _create(self, client, auth):
        client.post("/api/posts", headers=auth, json={
            "title": "Post a borrar", "content": "texto", "date": "2026-07-01"
        })
        return "2026-07-01-post-a-borrar"

    def test_delete_returns_200(self, client, auth, mock_hugo_ok):
        slug = self._create(client, auth)
        r = client.delete(f"/api/posts/{slug}", headers=auth)
        assert r.status_code == 200
        assert r.get_json()["status"] == "deleted"

    def test_delete_removes_file(self, client, auth, mock_hugo_ok, content_dir):
        slug = self._create(client, auth)
        client.delete(f"/api/posts/{slug}", headers=auth)
        assert not (content_dir / "content" / "posts" / f"{slug}.md").exists()

    def test_delete_nonexistent_returns_404(self, client, auth):
        r = client.delete("/api/posts/no-existe", headers=auth)
        assert r.status_code == 404

    def test_deleted_post_gone_from_list(self, client, auth, mock_hugo_ok):
        slug = self._create(client, auth)
        client.delete(f"/api/posts/{slug}", headers=auth)
        posts = client.get("/api/posts", headers=auth).get_json()["posts"]
        assert f"{slug}.md" not in posts

    def test_delete_hugo_failure_returns_207(self, client, auth, mock_hugo_ok, mock_hugo_fail, content_dir):
        slug = self._create(client, auth)
        r = client.delete(f"/api/posts/{slug}", headers=auth)
        assert r.status_code == 207
