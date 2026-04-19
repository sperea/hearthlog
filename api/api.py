import os
import base64
import logging
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import Flask, request, jsonify
from PIL import Image
from slugify import slugify
import io

from hugo_runner import rebuild_site

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BLOG_CONTENT_PATH = Path(os.environ.get("BLOG_CONTENT_PATH", "/blog-content"))
AI_BOT_API_TOKEN = os.environ.get("AI_BOT_API_TOKEN", "")
HUGO_CONTAINER = os.environ.get("HUGO_CONTAINER", "hugo-generator")

MAX_IMAGE_DIMENSION = 1920
JPEG_QUALITY = 85
MAX_PHOTO_SIZE_MB = 10


def require_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("X-API-Token")
        if not token or token != AI_BOT_API_TOKEN:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


def process_image(data: bytes, filename: str) -> bytes:
    img = Image.open(io.BytesIO(data))
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    if max(img.size) > MAX_IMAGE_DIMENSION:
        img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return out.getvalue()


def save_photo(photo: dict, images_dir: Path) -> str | None:
    filename = photo.get("filename", "")
    b64_data = photo.get("data", "")
    if not filename or not b64_data:
        return None
    try:
        raw = base64.b64decode(b64_data)
        if len(raw) > MAX_PHOTO_SIZE_MB * 1024 * 1024:
            logger.warning("Photo %s exceeds %dMB, skipping", filename, MAX_PHOTO_SIZE_MB)
            return None
        processed = process_image(raw, filename)
        stem = Path(filename).stem
        dest_name = f"{slugify(stem)}.jpg"
        dest = images_dir / dest_name
        dest.write_bytes(processed)
        return dest_name
    except Exception as e:
        logger.error("Failed to process photo %s: %s", filename, e)
        return None


def build_markdown(title: str, date: str, content: str, saved_photos: list[str], date_slug: str) -> str:
    featured = f"/images/{date_slug}/{saved_photos[0]}" if saved_photos else ""
    front_matter = f"""---
title: "{title}"
date: {date}T12:00:00+02:00
draft: false
categories: ["Familiar"]
{"featured_image: \"" + featured + "\"" if featured else ""}
---

"""
    photo_block = "\n".join(
        f'![{Path(p).stem}](/images/{date_slug}/{p})' for p in saved_photos
    )
    return front_matter + content + ("\n\n" + photo_block if photo_block else "")


@app.route("/api/health", methods=["GET"])
@require_token
def health():
    return jsonify({"status": "ok", "service": "blog-api"})


@app.route("/api/posts", methods=["POST"])
@require_token
def create_post():
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "JSON body required"}), 400

    title = body.get("title", "").strip()
    content = body.get("content", "").strip()
    date_str = body.get("date", datetime.now().strftime("%Y-%m-%d"))
    photos = body.get("photos", [])

    if not title:
        return jsonify({"error": "title is required"}), 400
    if not content:
        return jsonify({"error": "content is required"}), 400

    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "date must be YYYY-MM-DD"}), 400

    date_slug = date_str
    images_dir = BLOG_CONTENT_PATH / "static" / "images" / date_slug
    images_dir.mkdir(parents=True, exist_ok=True)

    saved_photos = []
    failed_photos = []
    for photo in photos:
        saved = save_photo(photo, images_dir)
        if saved:
            saved_photos.append(saved)
        else:
            failed_photos.append(photo.get("filename", "unknown"))

    slug = slugify(title)
    post_filename = f"{date_str}-{slug}.md"
    post_path = BLOG_CONTENT_PATH / "content" / "posts" / post_filename
    markdown = build_markdown(title, date_str, content, saved_photos, date_slug)
    post_path.write_text(markdown, encoding="utf-8")
    logger.info("Post created: %s", post_filename)

    ok, msg = rebuild_site(HUGO_CONTAINER)
    if not ok:
        logger.error("Hugo rebuild failed after post creation: %s", msg)
        return jsonify({
            "status": "partial",
            "post": post_filename,
            "photos_saved": saved_photos,
            "photos_failed": failed_photos,
            "hugo_error": msg,
        }), 207

    return jsonify({
        "status": "published",
        "post": post_filename,
        "photos_saved": saved_photos,
        "photos_failed": failed_photos,
    }), 201


@app.route("/api/posts", methods=["GET"])
@require_token
def list_posts():
    posts_dir = BLOG_CONTENT_PATH / "content" / "posts"
    posts = sorted(p.name for p in posts_dir.glob("*.md")) if posts_dir.exists() else []
    return jsonify({"posts": posts})


if __name__ == "__main__":
    if not AI_BOT_API_TOKEN:
        raise RuntimeError("AI_BOT_API_TOKEN env var not set")
    app.run(host="0.0.0.0", port=5000)
