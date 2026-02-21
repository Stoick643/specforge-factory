# SpecForge - Future Work

## 1. Pi Setup Skill

Create a `/setup` skill so new users can do:

```bash
git clone https://github.com/dmulej/specforge-factory.git
cd specforge-factory
pi
# then: /setup
```

Inspired by [nanoclaw](https://github.com/qwibitai/nanoclaw) pattern.

### Location
`.pi/skills/setup/SKILL.md`

### Steps
1. Check Python version (3.10+)
2. Create venv and `pip install -e .`
3. Verify: `specforge --version` + run unit tests
4. Check if Pi is available (for `--provider pi`)
5. Show usage examples

### Notes
- Read Pi skills docs before implementing: `docs/skills.md` in Pi install
- Nanoclaw reference: `C:\projects\claw\nanoclaw\.claude\skills\setup\SKILL.md`
- Keep it simple -- SpecForge setup is much simpler than nanoclaw

---

## 2. Web UI (specforge.io)

Hosted version of SpecForge. User writes a spec in the browser, gets a generated project.

### User Flow

```
1. Land on specforge.io
2. Left panel: Markdown editor (pre-filled with example spec)
3. Pick template or write your own spec
4. Click "Generate"
5. Right panel shows live progress via WebSocket:
   > Architect: Designing 13 endpoints...
   > Coder: Generating core files... routers... tests...
   > Tester: 46/49 passed, looping back...
   > Tester: 49/49 passed!
6. "Download ZIP" or "View Files" buttons appear
7. File browser: tree on left, Monaco code editor on right (read-only preview)
8. Optional: "Deploy to Fly.io" / "Push to GitHub" one-click
```

### Screens

**Screen 1 - Editor:**
- Left: Markdown editor with spec
- Bottom-left: Template dropdown (URL shortener, todo API, blog, etc.)
- Right: "Ready" status + Generate button
- Top-right: Free tier counter (2/3) + API key settings

**Screen 2 - Progress (live):**
- Left: Spec (read-only during generation)
- Right: Live streaming log of agent progress via WebSocket
- Shows each agent step, iteration count, test results in real-time

**Screen 3 - Results:**
- Download ZIP button
- View Files button
- Summary: 24 files, 49 tests passed, 2 iterations

**Screen 4 - File Browser:**
- Left: File tree (all generated files)
- Right: Monaco Editor (VS Code's editor component) showing selected file
- Syntax highlighting for Python, YAML, Dockerfile, Markdown
- Read-only preview -- click any file to inspect before downloading

### Architecture

```
Browser (SvelteKit or Next.js)
    |
    | WebSocket (live progress)
    v
FastAPI backend on Hetzner VPS ($5-10/mo)
    |
    | Runs SpecForge workflow
    | Uses user's API key or shared key (free tier)
    v
LLM API (OpenAI / Anthropic)
    |
    v
Generated files -> ZIP -> temp storage (expires 24h)
```

### Key Components

| Component | Technology |
|---|---|
| Frontend framework | SvelteKit or Next.js |
| Markdown editor | CodeMirror or Monaco |
| Code preview | Monaco Editor (VS Code in browser, free) |
| Live progress | FastAPI WebSocket |
| Background jobs | Redis + Celery (generation takes 3-10 min) |
| File storage | Local disk or S3 for ZIPs |
| Auth | GitHub OAuth (optional) |
| Hosting | Hetzner CX22 VPS (~$5/mo) |

### Revenue Model

| Tier | Price | What |
|---|---|---|
| Free | $0 | 3 generations/month, shared API key (~$0.50/gen cost) |
| BYO key | $0 | Unlimited, user provides own OpenAI/Anthropic key |
| Pro | $9/mo | 50 generations, faster models, priority queue |
| Pay-per-use | $1/gen | No subscription, Stripe payment per generation |

User's API key is never stored -- used for one generation, then discarded.

### Changes Needed in SpecForge

1. **Progress callbacks** -- agents emit events instead of printing to console:
   ```python
   def on_progress(event):
       websocket.send(event)
   ```

2. **API key injection** -- accept key per request, not from .env:
   ```python
   run_workflow(spec_text, output_dir, api_key="sk-...")
   ```

3. **ZIP packaging** -- zip output folder after generation

4. **Headless mode** -- `--quiet` flag for no Rich output (also useful for CI)

### Build Estimate

| Part | Effort |
|---|---|
| FastAPI backend (wrap existing workflow) | 1 day |
| WebSocket progress streaming | 1 day |
| Frontend: editor + progress panel | 2 days |
| Frontend: file browser + Monaco | 1 day |
| Auth + API key input + free tier | 1 day |
| Deploy to Hetzner | 0.5 day |
| **Total** | **~1 week** |

---

## 3. More Example Specs

Add more built-in specs beyond the URL shortener:

- Todo API (simple, good for demos)
- Blog API (posts, comments, auth)
- E-commerce API (products, cart, orders, Stripe)
- Chat API (WebSocket, rooms, messages)
- File storage API (upload, download, S3-compatible)

### Location
`specforge/examples/*.md`

---

## 4. GitHub Action

Publish as a GitHub Action so teams can auto-generate from specs in CI:

```yaml
on:
  push:
    paths: ['specs/*.md']
jobs:
  generate:
    steps:
      - uses: specforge/action@v1
        with:
          spec: specs/my-api.md
          api-key: ${{ secrets.OPENAI_API_KEY }}
```

Generates code and opens a PR. Lower priority than Web UI.

---

## 5. PyPI Publishing

`pip install specforge` instead of cloning the repo.
Lower priority -- repo clone + Pi setup skill is good enough for now.
