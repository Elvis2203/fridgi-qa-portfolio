"""Serve a built frontend and isolated sample-only API. No credentials required."""

import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from demo.server import demo_app  # noqa: E402 -- allow launch before editable installation

if __name__ == "__main__":
    uvicorn.run(demo_app(ROOT), host="127.0.0.1", port=8010)
