---
name: setup
description: First-time SpecForge setup. Checks Python, installs dependencies, verifies the CLI works, and runs tests. Use when someone clones the repo and wants to get started.
---

# SpecForge Setup

Run this after cloning the repo to get everything working.

**Principle:** Fix problems automatically. Only ask the user when a genuine choice is needed.

## Step 1: Check Python

```bash
python --version
```

- Need Python 3.10 or higher.
- If missing or too old, tell the user to install Python 3.10+ and provide a link: https://www.python.org/downloads/

## Step 2: Install Dependencies

```bash
pip install -e .
```

If this fails:
- Check for permission errors -- suggest `pip install --user -e .` or using a virtual environment
- Check for missing build tools -- suggest installing them
- Retry after fixing

## Step 3: Verify CLI

```bash
python -m specforge --version
```

Should print `SpecForge v0.1.0` or similar. If it fails, check the install output from Step 2.

## Step 4: Run Tests

```bash
python -m pytest tests/ -v
```

All tests should pass (currently 51). If any fail, diagnose and fix.

## Step 5: Check Pi Provider

Check if Pi is available for the `--provider pi` option (no API key needed):

```bash
pi --version
```

- If Pi is installed: tell the user they can use `--provider pi` for free generation
- If not installed: tell the user they need an API key (OpenAI, Anthropic, etc.) OR they can install Pi: `npm i -g @mariozechner/pi-coding-agent`

## Step 6: Show Getting Started

Print a summary:

```
SpecForge is ready!

Quick start:
  # Generate with Pi (no API key):
  specforge generate specforge/examples/advanced-shortener-sqlite.md --provider pi --output ./my-app --clean

  # Generate with API key:
  cp .env.example .env   # edit .env with your key
  specforge generate specforge/examples/advanced-shortener-sqlite.md --model gpt-4o --output ./my-app --clean

  # Web UI:
  python -m web.run
  # Open http://localhost:8080

  # Run tests:
  python -m pytest tests/ -v
```

## Troubleshooting

- **pip not found**: Try `python -m pip install -e .`
- **Permission denied**: Use `pip install --user -e .` or create a venv first: `python -m venv .venv && .venv/Scripts/activate`
- **Tests fail with import errors**: Make sure you ran `pip install -e .` (not just `pip install .`)
- **Pi not found on Windows**: Check `%APPDATA%/npm/pi.cmd` exists. Run `npm i -g @mariozechner/pi-coding-agent` to install.
