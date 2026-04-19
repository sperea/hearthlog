import os
import re
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


def posts_dir() -> Path:
    return BLOG_CONTENT_PATH / "content" / "posts"


def resolve_post(slug: str) -> Path | None:
    """Find post file by slug (filename without .md)."""
    p = posts_dir() / f"{slug}.md"
    return p if p.exists() else None


def process_image(data: bytes, filename: str) -> bytes:
    img = Image.open(io.BytesIO(data))
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    if max(img.size) > MAX_IMAGE_DIMENSION:
        img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return out.getvalue()


def save_photo(photo: dict, images_dir: Path) -> tuple[str, None] | tuple[None, str]:
    filename = photo.get("filename", "") or "unknown"
    b64_data = photo.get("data", "")
    if not b64_data:
        return None, f"'{filename}': no data provided"
    try:
        raw = base64.b64decode(b64_data)
        size_mb = len(raw) / (1024 * 1024)
        if len(raw) > MAX_PHOTO_SIZE_MB * 1024 * 1024:
            logger.warning("Photo %s exceeds %dMB (%.1fMB), skipping", filename, MAX_PHOTO_SIZE_MB, size_mb)
            return None, (
                f"'{filename}' exceeds {MAX_PHOTO_SIZE_MB}MB limit "
                f"(actual: {size_mb:.1f}MB). Resize to max 1920px, quality 85%."
            )
        processed = process_image(raw, filename)
        dest_name = f"{slugify(Path(filename).stem)}.jpg"
        (images_dir / dest_name).write_bytes(processed)
        return dest_name, None
    except Exception as e:
        logger.error("Failed to process photo %s: %s", filename, e)
        return None, f"'{filename}': processing error — {e}"


def build_markdown(title: str, date: str, content: str, saved_photos: list[str], date_slug: str, draft: bool = False) -> str:
    featured = f"/images/{date_slug}/{saved_photos[0]}" if saved_photos else ""
    featured_line = f'featured_image: "{featured}"' if featured else ""
    front_matter = (
        f'---\ntitle: "{title}"\n'
        f"date: {date}T12:00:00+02:00\n"
        f"draft: {'true' if draft else 'false'}\n"
        f'categories: ["Familiar"]\n'
        f"{featured_line}\n"
        f"---\n\n"
    )
    photo_block = "\n".join(
        f'![{Path(p).stem}](/images/{date_slug}/{p})' for p in saved_photos
    )
    return front_matter + content + ("\n\n" + photo_block if photo_block else "")


def parse_frontmatter_field(text: str, field: str) -> str | None:
    m = re.search(rf'^{field}:\s*"?([^"\n]+)"?', text, re.MULTILINE)
    return m.group(1).strip() if m else None


def set_frontmatter_field(text: str, field: str, value: str) -> str:
    return re.sub(
        rf'^({field}:\s*).*$',
        lambda m: f'{field}: {value}',
        text,
        flags=re.MULTILINE,
    )


def rebuild_or_error(container: str) -> tuple[dict, int] | None:
    ok, msg = rebuild_site(container)
    if not ok:
        return {"hugo_error": msg}, 207
    return None


# ── Health ────────────────────────────────────────────────────────────────────

@app.route("/api/health", methods=["GET"])
@require_token
def health():
    return jsonify({"status": "ok", "service": "blog-api"})


# ── List posts ────────────────────────────────────────────────────────────────

@app.route("/api/posts", methods=["GET"])
@require_token
def list_posts():
    d = posts_dir()
    posts = sorted(p.name for p in d.glob("*.md")) if d.exists() else []
    return jsonify({"posts": posts})


# ── Get single post ───────────────────────────────────────────────────────────

@app.route("/api/posts/<slug>", methods=["GET"])
@require_token
def get_post(slug: str):
    post = resolve_post(slug)
    if not post:
        return jsonify({"error": "Post not found"}), 404
    text = post.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    body = parts[2].lstrip("\n") if len(parts) >= 3 else text
    return jsonify({
        "slug": slug,
        "title": parse_frontmatter_field(text, "title") or "",
        "date": parse_frontmatter_field(text, "date") or "",
        "draft": "draft: true" in text,
        "content": body,
    })


# ── Create post ───────────────────────────────────────────────────────────────

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

    images_dir = BLOG_CONTENT_PATH / "static" / "images" / date_str
    images_dir.mkdir(parents=True, exist_ok=True)

    saved_photos, failed_photos = [], []
    for photo in photos:
        saved, error = save_photo(photo, images_dir)
        if saved:
            saved_photos.append(saved)
        else:
            failed_photos.append(error)

    slug = slugify(title)
    post_filename = f"{date_str}-{slug}.md"
    post_path = posts_dir() / post_filename
    posts_dir().mkdir(parents=True, exist_ok=True)
    post_path.write_text(
        build_markdown(title, date_str, content, saved_photos, date_str),
        encoding="utf-8",
    )
    logger.info("Post created: %s", post_filename)

    ok, msg = rebuild_site(HUGO_CONTAINER)
    base = {"post": post_filename, "photos_saved": saved_photos, "photos_failed": failed_photos}
    if not ok:
        return jsonify({"status": "partial", "hugo_error": msg, **base}), 207
    return jsonify({"status": "published", **base}), 201


# ── Update post ───────────────────────────────────────────────────────────────

@app.route("/api/posts/<slug>", methods=["PUT"])
@require_token
def update_post(slug: str):
    post = resolve_post(slug)
    if not post:
        return jsonify({"error": "Post not found"}), 404

    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "JSON body required"}), 400

    current = post.read_text(encoding="utf-8")

    title = body.get("title", parse_frontmatter_field(current, "title") or "").strip()
    content_new = body.get("content", "").strip()
    date_str = body.get("date", parse_frontmatter_field(current, "date") or datetime.now().strftime("%Y-%m-%d"))
    photos = body.get("photos", [])
    was_draft = "draft: true" in current

    if not title:
        return jsonify({"error": "title is required"}), 400
    if not content_new:
        return jsonify({"error": "content is required"}), 400

    if len(date_str) > 10:
        date_str = date_str[:10]

    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "date must be YYYY-MM-DD"}), 400

    images_dir = BLOG_CONTENT_PATH / "static" / "images" / date_str
    images_dir.mkdir(parents=True, exist_ok=True)

    saved_photos, failed_photos = [], []
    for photo in photos:
        saved, error = save_photo(photo, images_dir)
        if saved:
            saved_photos.append(saved)
        else:
            failed_photos.append(error)

    post.write_text(
        build_markdown(title, date_str, content_new, saved_photos, date_str, draft=was_draft),
        encoding="utf-8",
    )
    logger.info("Post updated: %s", slug)

    ok, msg = rebuild_site(HUGO_CONTAINER)
    base = {"post": slug + ".md", "photos_saved": saved_photos, "photos_failed": failed_photos}
    if not ok:
        return jsonify({"status": "partial", "hugo_error": msg, **base}), 207
    return jsonify({"status": "updated", **base}), 200


# ── Toggle draft ──────────────────────────────────────────────────────────────

@app.route("/api/posts/<slug>/draft", methods=["PATCH"])
@require_token
def toggle_draft(slug: str):
    post = resolve_post(slug)
    if not post:
        return jsonify({"error": "Post not found"}), 404

    body = request.get_json(silent=True) or {}
    if "draft" not in body:
        return jsonify({"error": "draft field required (true or false)"}), 400

    draft = bool(body["draft"])
    text = post.read_text(encoding="utf-8")
    updated = set_frontmatter_field(text, "draft", "true" if draft else "false")
    post.write_text(updated, encoding="utf-8")
    logger.info("Post %s draft=%s", slug, draft)

    ok, msg = rebuild_site(HUGO_CONTAINER)
    if not ok:
        return jsonify({"status": "partial", "draft": draft, "hugo_error": msg}), 207
    return jsonify({"status": "updated", "post": slug + ".md", "draft": draft}), 200


# ── Delete post ───────────────────────────────────────────────────────────────

@app.route("/api/posts/<slug>", methods=["DELETE"])
@require_token
def delete_post(slug: str):
    post = resolve_post(slug)
    if not post:
        return jsonify({"error": "Post not found"}), 404

    post.unlink()
    logger.info("Post deleted: %s", slug)

    ok, msg = rebuild_site(HUGO_CONTAINER)
    if not ok:
        return jsonify({"status": "partial", "hugo_error": msg}), 207
    return jsonify({"status": "deleted", "post": slug + ".md"}), 200


if __name__ == "__main__":
    if not AI_BOT_API_TOKEN:
        raise RuntimeError("AI_BOT_API_TOKEN env var not set")
    app.run(host="0.0.0.0", port=5000)
