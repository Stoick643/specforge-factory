"""Start the SpecForge Web UI server."""

import uvicorn


def main():
    print("Starting SpecForge Web UI...")
    print("Open http://localhost:8080 in your browser")
    print()
    uvicorn.run(
        "web.backend.main:app",
        host="127.0.0.1",
        port=8080,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
