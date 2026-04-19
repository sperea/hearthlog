# Hearthlog 🪵

Private self-hosted family blog powered by Hugo, protected by password, with a REST API so an AI bot can publish posts and photos automatically.

> *Hearth* + *log*. The digital corner where family memories live.

## Why this exists

I wanted a private family diary — travel photos, everyday moments, memories that don't get lost in the chaos of WhatsApp groups. No social media, no third-party services — just something ours, on our own server.

The problem was friction. A blog that requires opening an admin panel, writing markdown, and manually triggering a deploy is a blog nobody actually uses day-to-day. The solution was connecting it to [OpenClaw](https://github.com/SergioOpenClaw/openclaw), my personal AI assistant. I send a Telegram message with photos and text, and it publishes the post automatically via API. No friction, no computer needed, from the phone at any moment.

Hearthlog is the result: a fast, private, self-hosted static blog manageable through an AI bot.

## Stack

- **Hugo** — static site generator
- **Nginx** — web server with HTTP Basic Auth
- **Python/Flask** — REST API for the bot
- **Docker Compose** — orchestration

## Architecture

```
AI_BOT (Telegram/etc.)
    │
    ▼ POST /api/posts
┌──────────────────────────────────────────┐
│  hearthlog-api :5000                     │
│  • Validates token                       │
│  • Saves photos (resized to 1920px)      │
│  • Creates .md in content/posts/         │
│  • Runs: docker exec hugo-generator hugo │
└──────────────────────────────────────────┘
    │
    ▼ hugo --minify → public/
┌──────────────────────────────────────────┐
│  blog-familiar :8082                     │
│  Nginx serves public/ with Basic Auth    │
└──────────────────────────────────────────┘
    │
    ▼
Family accesses with password
```

## Project structure

```
hearthlog/
├── docker-compose.yml
├── .env                        # Do not commit
├── .env.example
├── blog-content/
│   ├── content/posts/          # Markdown posts (written by API)
│   ├── static/images/          # Photos organized by date
│   ├── themes/familia/         # Custom Hugo theme
│   └── config.toml
├── nginx/
│   ├── nginx.conf
│   └── auth.htpasswd           # Generated at deploy, do not commit
├── api/
│   ├── api.py
│   ├── hugo_runner.py
│   ├── requirements.txt
│   └── Dockerfile
└── scripts/
    ├── deploy.sh
    └── backup.sh
```

## Setup

### Requirements

- Docker and Docker Compose
- Ports 8081, 8082 (blog) and 5000 (API) available

### Deploy

```bash
git clone <repo>
cd hearthlog

cp .env.example .env
nano .env  # Set BLOG_PASSWORD and AI_BOT_API_TOKEN

./scripts/deploy.sh
```

### Ports

The blog is served on two ports so you can choose how to expose it:

| Port | Access | Use case |
|------|--------|----------|
| `8082` | Password protected (HTTP Basic Auth) | Private family access — share only with family |
| `8081` | No authentication | Public access — expose via reverse proxy if you want the blog open to anyone |
| `5000` | Token protected | Bot API — never expose publicly |

Both ports serve identical content. Nginx handles auth on `:80` (mapped to 8082) and serves without auth on `:81` (mapped to 8081).

### Environment variables

| Variable | Description |
|----------|-------------|
| `BLOG_PASSWORD` | Password for family access to the blog |
| `AI_BOT_API_TOKEN` | Secret token to authenticate the bot |

> **Important:** Never commit `.env` or `nginx/auth.htpasswd`. Both are in `.gitignore`.

## Bot API

### Authentication

All requests require the header:

```
X-API-Token: <AI_BOT_API_TOKEN>
```

### Endpoints

#### `GET /api/health`

Check the API is running.

```bash
curl -H "X-API-Token: $AI_BOT_API_TOKEN" \
  http://localhost:5000/api/health
```

#### `POST /api/posts`

Publish a post with optional photos.

```bash
curl -X POST \
  -H "X-API-Token: $AI_BOT_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Day in the mountains",
    "content": "We went to the mountains today and it was amazing...",
    "date": "2026-04-19",
    "photos": [
      {"filename": "photo1.jpg", "data": "<base64>"},
      {"filename": "photo2.jpg", "data": "<base64>"}
    ]
  }' \
  http://localhost:5000/api/posts
```

**Success (`201`):**
```json
{
  "status": "published",
  "post": "2026-04-19-day-in-the-mountains.md",
  "photos_saved": ["day-in-the-mountains.jpg"],
  "photos_failed": []
}
```

**Partial (`207`)** — post saved but Hugo build failed:
```json
{
  "status": "partial",
  "post": "2026-04-19-day-in-the-mountains.md",
  "hugo_error": "..."
}
```

#### `GET /api/posts`

List all existing posts.

### Limits

- Max photo size: 10 MB
- Photos are automatically resized to max 1920px and converted to JPEG (quality 85)

## OpenClaw integration guide

This section is written for OpenClaw (or any AI bot) to understand exactly how to interact with the API.

### Base URL

```
http://192.168.1.139:5000
```

Always verify the API is reachable before attempting any operation:

```
GET /api/health
```

Expected response: `{"status": "ok", "service": "blog-api"}`

---

### Authentication

Every request must include this header. No exceptions — missing or wrong token returns `401`.

```
X-API-Token: <token from .env AI_BOT_API_TOKEN>
```

---

### The slug

Posts are identified by their **slug** — the filename without `.md`. Example:

```
filename:  2026-04-19-trip-to-the-mountains.md
slug:      2026-04-19-trip-to-the-mountains
```

The slug is returned in every response that creates or modifies a post. Use `GET /api/posts` to list all slugs.

---

### Photo object (used in POST and PUT)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `filename` | string | **yes** | Original filename with extension (`foto.jpg`, `imagen.png`). Used to generate the saved name. |
| `data` | string | **yes** | File content encoded as **base64**. Accepted: JPEG, PNG, WebP, GIF. Max: **10 MB**. |

Photos are automatically resized to max 1920px, converted to JPEG (quality 85), and saved to `/static/images/YYYY-MM-DD/slugified-name.jpg`. The first photo becomes the featured image on the home page.

---

### Common response codes

| Code | Meaning |
|------|---------|
| `200` | OK |
| `201` | Created |
| `207` | Partial — operation succeeded but Hugo rebuild failed. Content is saved. Report to Sergio. |
| `400` | Bad request — check `error` field |
| `401` | Wrong or missing token |
| `404` | Post not found |
| `500` | Server crash — report to Sergio with full response |

---

### Endpoints

#### `GET /api/health` — Health check

```
GET /api/health
```

```json
{"status": "ok", "service": "blog-api"}
```

---

#### `GET /api/posts` — List all posts

```
GET /api/posts
```

```json
{
  "posts": [
    "2026-04-01-easter-weekend.md",
    "2026-04-19-trip-to-the-mountains.md"
  ]
}
```

---

#### `GET /api/posts/<slug>` — Read a post

Returns the full post data. Use this before editing to check current content.

```
GET /api/posts/2026-04-19-trip-to-the-mountains
```

```json
{
  "slug": "2026-04-19-trip-to-the-mountains",
  "title": "Trip to the mountains",
  "date": "2026-04-19T12:00:00+02:00",
  "draft": false,
  "content": "---\ntitle: \"Trip to the mountains\"\n..."
}
```

---

#### `POST /api/posts` — Create a post

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | **yes** | Post title. Cannot be blank. |
| `content` | string | **yes** | Body text. Plain text or Markdown. Cannot be blank. |
| `date` | string | no | `YYYY-MM-DD`. Defaults to today. |
| `photos` | array | no | List of photo objects. |

```json
{
  "title": "Trip to the mountains",
  "content": "We drove up early in the morning.\n\nThe views were incredible.",
  "date": "2026-04-19",
  "photos": [
    {"filename": "mountains.jpg", "data": "<base64>"},
    {"filename": "family.jpg",    "data": "<base64>"}
  ]
}
```

**`201` Success:**
```json
{
  "status": "published",
  "post": "2026-04-19-trip-to-the-mountains.md",
  "photos_saved": ["mountains.jpg", "family.jpg"],
  "photos_failed": []
}
```

**`207` Partial** — post saved, Hugo failed:
```json
{
  "status": "partial",
  "post": "2026-04-19-trip-to-the-mountains.md",
  "photos_saved": ["mountains.jpg"],
  "photos_failed": ["family.jpg"],
  "hugo_error": "..."
}
```

---

#### `PUT /api/posts/<slug>` — Update a post

Replaces title, content, date, and optionally adds new photos. Preserves the current draft status.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | **yes** | New title. |
| `content` | string | **yes** | New body text. Replaces the previous content entirely. |
| `date` | string | no | New date in `YYYY-MM-DD`. Keeps current date if omitted. |
| `photos` | array | no | New photos to add. |

```json
{
  "title": "Trip to the mountains (updated)",
  "content": "We drove up early. The views were incredible. Updated with more details.",
  "date": "2026-04-19"
}
```

**`200` Success:**
```json
{
  "status": "updated",
  "post": "2026-04-19-trip-to-the-mountains.md",
  "photos_saved": [],
  "photos_failed": []
}
```

---

#### `PATCH /api/posts/<slug>/draft` — Show or hide a post

Sets the post as draft (hidden from the blog) or published (visible).

```json
{"draft": true}
```

- `true` — post is hidden from the blog immediately
- `false` — post is visible on the blog again

**`200` Success:**
```json
{
  "status": "updated",
  "post": "2026-04-19-trip-to-the-mountains.md",
  "draft": true
}
```

---

#### `DELETE /api/posts/<slug>` — Delete a post

Permanently deletes the post file and rebuilds the site. Photos saved to disk are **not** deleted.

```
DELETE /api/posts/2026-04-19-trip-to-the-mountains
```

**`200` Success:**
```json
{
  "status": "deleted",
  "post": "2026-04-19-trip-to-the-mountains.md"
}
```

---

### Step-by-step flows

#### Publish from a Telegram message

1. Call `GET /api/health` — if not `200`, stop and notify Sergio.
2. Extract text as `content`. Infer or ask for a title.
3. Encode each attached photo to base64, build the `photos` array.
4. Set `date` to today (`YYYY-MM-DD`).
5. Call `POST /api/posts`.
6. `201` → confirm: *"Published: [title]"*.
7. `207` → confirm post saved, warn Hugo failed, notify Sergio.
8. `400/401/500` → do not retry silently — report error with details.

#### Edit an existing post

1. Call `GET /api/posts` to find the slug.
2. Call `GET /api/posts/<slug>` to read current content.
3. Modify what's needed, call `PUT /api/posts/<slug>` with full title + content.
4. Confirm result to user.

#### Hide a post temporarily

1. Find the slug via `GET /api/posts`.
2. Call `PATCH /api/posts/<slug>/draft` with `{"draft": true}`.
3. To restore: same endpoint with `{"draft": false}`.

---

### Content formatting tips

- `content` supports Markdown. Use `\n\n` for paragraph breaks.
- Photos are appended automatically after the content — do not insert `![...]()` manually.
- The first photo becomes the featured image on the home page.
- Filenames are slugified automatically: `"Mi Foto.JPG"` → `mi-foto.jpg`.

---

## Testing

The API has a full test suite covering authentication, post creation, photo processing, and error handling.

```bash
docker exec hearthlog-api pytest test_api.py -v
```

32 tests across 5 groups:

| Group | Tests | Covers |
|-------|-------|--------|
| `TestAuth` | 4 | Missing token, wrong token, empty token, valid token |
| `TestHealth` | 1 | Health endpoint response |
| `TestCreatePostValidation` | 6 | Missing body, title, content, blank title, bad date format, invalid date value |
| `TestCreatePost` | 7 | 201 response, file created on disk, slug generation, frontmatter correctness, default date, Hugo failure → 207, post saved even if Hugo fails |
| `TestPhotos` | 11 | Single photo, saved to disk, multiple photos, resize to 1920px, RGBA→RGB conversion, invalid base64 skipped, oversized photo skipped, missing filename, filename slugified, featured image in frontmatter, photo embedded in markdown |
| `TestListPosts` | 3 | Empty list, sorted list, only `.md` files returned |

To run with coverage:

```bash
docker exec hearthlog-api pytest test_api.py -v --cov=api --cov-report=term-missing
```

## Maintenance

### Backup

```bash
./scripts/backup.sh
```

Saves `content/posts/` and `static/images/` to `backups/`. Keeps the last 30 backups automatically.

### Logs

```bash
docker compose logs -f hearthlog-api   # Bot operations
docker compose logs -f blog-familiar   # Blog access
```

### Update

```bash
docker compose pull
docker compose up -d
```

## Portainer

All services are manageable from Portainer. Containers:

- `blog-familiar` — Nginx + blog
- `hearthlog-api` — Flask API
- `hugo-generator` — Hugo (triggered by the API to rebuild the site)

## License

MIT — see [LICENSE](LICENSE).
