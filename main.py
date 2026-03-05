"""
anonymyzr
---------
Privacy proxy for OpenClaw ↔ Claude API.

Intercepts Anthropic Messages API calls, anonymizes PII in requests
using local GLiNER + Faker (no data leaves the machine during detection),
forwards to Claude, then deanonymizes the response.

Usage:
    python main.py

OpenClaw config (openclaw.json):
    {
      "provider": {
        "api": "anthropic-messages",
        "url": "http://localhost:8080",
        "apiKey": "sk-ant-..."
      }
    }

Or via environment variable:
    ANTHROPIC_BASE_URL=http://localhost:8080
"""

import os

import uvicorn
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    host = os.environ.get("ANONYMYZR_HOST", "127.0.0.1")
    port = int(os.environ.get("ANONYMYZR_PORT", "8080"))

    print(f"[anonymyzr] Starting on http://{host}:{port}")
    print(f"[anonymyzr] Point OpenClaw base_url → http://{host}:{port}")

    uvicorn.run(
        "proxy.server:app",
        host=host,
        port=port,
        log_level="info",
        reload=False,
    )
