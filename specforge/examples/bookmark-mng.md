# Personal Bookmark Manager API

Self-hosted private bookmark organizer (Raindrop.io / Linkding alternative – lightweight, privacy-first).

Features:
- Save any URL with auto-fetched title, description, favicon, and optional screenshot/preview image data
- Add custom tags (multiple per bookmark), notes, and categories/folders (hierarchical support)
- Full-text search across titles, descriptions, notes, tags, and URLs
- Smart filtering: by tag combinations, date added, unread status
- Import/export bookmarks (Netscape HTML format, CSV, JSON)
- Browser extension-friendly endpoints (POST to save from anywhere)
- Dashboard endpoints: list bookmarks (paginated), edit/delete, mark as read/unread
- Optional archive/full-page snapshot (save HTML or PDF of page at save time)
- Public/private visibility per bookmark (shareable read-only links)
- Rate limiting on public save endpoint (if exposed)

Requirements:
- SQLite only (single file database, mounted as persistent volume on Fly.io or Docker)
- Docker + docker-compose (for local dev/testing)
- JWT authentication (single user or multi-user with simple roles)
- Clean Swagger/OpenAPI docs at /docs
- Full pytest coverage (unit + integration tests)
- Deployment-friendly: single container, persistent volume for db.sqlite3 + any archived files
- Use async SQLAlchemy + SQLModel for the ORM

Nice-to-have extras:
- In-app simple cache (e.g. aiocache with TTL) for frequent searches/lists
- Auto-fetch metadata (title, description, image) using requests + beautifulsoup or similar
- Dark mode support in any frontend data
- Dead link checker (optional background job)