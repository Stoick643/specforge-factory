# Advanced URL Shortener API

Self-hosted TinyURL competitor with analytics - lightweight and private.

## Features
- Shorten any URL to get short code (e.g. myapp.com/abc123) or custom vanity slug
- Support custom domains (configured via env)
- QR code generation for every short link (return as image or base64)
- Click analytics per link: total clicks, unique clicks (approx via IP hash), referrer, country (from headers), timestamp
- Dashboard endpoints: list all links, edit expiry/delete, view stats
- Expiry options: never / custom date / max clicks reached
- Public shorten endpoint with rate limit (5 requests per minute per IP)
- Admin-only routes protected by JWT
- API key support for programmatic shortening (optional)

## Requirements
- SQLite only (single file database, mounted as volume on Fly.io or Docker)
- Docker + docker-compose (for local dev/testing)
- JWT authentication (simple, single admin user via env)
- Rate limiting (in-memory or DB-based, no external cache needed)
- Clean Swagger/OpenAPI docs at /docs
- Full pytest coverage (unit + integration tests)
- Deployment-friendly: single container, persistent volume for db.sqlite3
- Use async SQLAlchemy + SQLModel for the ORM

## Nice-to-have extras
- In-app simple cache (e.g. aiocache with TTL) for hot redirects if performance needed
- Base62 encoding for short codes
- Unique constraint on vanity slugs
