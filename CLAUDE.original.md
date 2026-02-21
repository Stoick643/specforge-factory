You are an expert AI software engineer. Build "SpecForge" — a Spec-Driven Multi-Agent Microservice Factory (CLI version) exactly as described.

Project goal: CLI tool that takes a Markdown product spec and generates a complete, tested, Docker-ready FastAPI microservice using a self-correcting 3-agent loop (Architect → Coder → Tester, max 4 iterations).

CLI example:
specforge generate advanced-shortener-sqlite.md --output ./my-shortener

Use this built-in example spec for testing (SQLite version):

# Advanced URL Shortener API

Self-hosted TinyURL competitor with analytics – lightweight and private.

Features:
- Shorten any URL → get short code (e.g. myapp.com/abc123) or custom vanity slug
- Support custom domains (configured via env)
- QR code generation for every short link (return as image or base64)
- Click analytics per link: total clicks, unique clicks (approx via IP hash), referrer, country (from headers), timestamp
- Dashboard endpoints: list all links, edit expiry/delete, view stats
- Expiry options: never / custom date / max clicks reached
- Public shorten endpoint with rate limit (5 requests per minute per IP)
- Admin-only routes protected by JWT
- API key support for programmatic shortening (optional)

Requirements:
- SQLite only (single file database, mounted as volume on Fly.io or Docker)
- Docker + docker-compose (for local dev/testing)
- JWT authentication (simple, single admin user via env)
- Rate limiting (in-memory or DB-based, no external cache needed)
- Clean Swagger/OpenAPI docs at /docs
- Full pytest coverage (unit + integration tests)
- Deployment-friendly: single container, persistent volume for db.sqlite3
- Use async SQLAlchemy + SQLModel for the ORM

Nice-to-have extras:
- In-app simple cache (e.g. aiocache with TTL) for hot redirects if performance needed
- Base62 encoding for short codes
- Unique constraint on vanity slugs

Core tech:
- Typer for CLI
- pydantic-ai or structured outputs for Architect agent
- LangGraph for the stateful 3-agent graph
- Rich for beautiful CLI output
- Generate full project structure (app/, tests/, alembic if needed but minimal for SQLite, Dockerfile, docker-compose.yml, requirements.txt, .env.example, README.md)

Deliverables:
1. Full working repo structure
2. pyproject.toml or requirements.txt with deps
3. README with install + usage (including running the URL shortener example)
4. The tool must be able to generate the above spec successfully

Start now: project setup → Pydantic models for SystemDesign → agents → LangGraph workflow → Typer CLI.