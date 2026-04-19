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
- Ports 8082 (blog) and 5000 (API) available

### Deploy

```bash
git clone <repo>
cd hearthlog

cp .env.example .env
nano .env  # Set BLOG_PASSWORD and AI_BOT_API_TOKEN

./scripts/deploy.sh
```

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
