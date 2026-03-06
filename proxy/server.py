"""
server.py
---------
FastAPI proxy that speaks the Anthropic Messages API.

OpenClaw (and any other Anthropic API client) points its base_url here.
The proxy intercepts requests, anonymizes PII, forwards to Claude,
then deanonymizes the response before returning it.

Streaming note (v1):
  The proxy internally fetches a non-streaming response from Claude so
  it can deanonymize the complete text before returning. If the client
  requested streaming, we simulate a valid SSE stream from the full
  response. This adds ~0 overhead vs true streaming for typical agentic
  workloads. True pass-through streaming (with a sliding-window
  deanonymizer) is planned for v2.
"""

import json
import os
import uuid
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .deanonymizer import deanonymize, deanonymize_content_blocks
from .detector import detect_entities
from .log import log_error, log_request, log_response
from .mapper import mapper
from .synthesizer import synthesize

app = FastAPI(title="anonymyzr", description="Privacy proxy for Claude / Anthropic API")

CLAUDE_API_URL = os.environ.get("ANTHROPIC_API_URL", "https://api.anthropic.com/v1/messages")
ANTHROPIC_VERSION = "2023-06-01"

# Structural keys that must never be anonymized
_PASSTHROUGH_KEYS = {
    "type", "role", "id", "name", "input_schema", "cache_control",
    "tool_use_id", "model", "stop_reason", "stop_sequence",
}


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def _session_id(request: Request) -> str:
    return request.headers.get("x-anonymyzr-session", str(uuid.uuid4()))


def _api_key(request: Request) -> str:
    key = (
        request.headers.get("x-api-key")
        or request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        or os.environ.get("ANTHROPIC_API_KEY", "")
    )
    if not key:
        raise HTTPException(status_code=401, detail="No Anthropic API key provided.")
    return key


# ---------------------------------------------------------------------------
# Anonymization helpers
# ---------------------------------------------------------------------------

def _anonymize_text(session_id: str, text: str) -> str:
    """Detect entities in text and replace with synthetic equivalents."""
    entities = detect_entities(text)  # sorted right-to-left by position
    for entity in entities:
        synthetic = synthesize(session_id, entity["text"], entity["label"])
        text = text[: entity["start"]] + synthetic + text[entity["end"] :]
    return text


def _anonymize_value(session_id: str, value: Any) -> Any:
    """Recursively anonymize any JSON-like value."""
    if isinstance(value, str):
        return _anonymize_text(session_id, value)
    if isinstance(value, list):
        return [_anonymize_value(session_id, item) for item in value]
    if isinstance(value, dict):
        return {
            k: (v if k in _PASSTHROUGH_KEYS else _anonymize_value(session_id, v))
            for k, v in value.items()
        }
    return value


def _anonymize_messages(session_id: str, messages: list) -> list:
    """Anonymize the content of each message, leaving role/id intact."""
    result = []
    for msg in messages:
        anon = dict(msg)
        if "content" in anon:
            anon["content"] = _anonymize_value(session_id, anon["content"])
        result.append(anon)
    return result


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/v1/messages")
async def proxy_messages(request: Request):
    session_id = _session_id(request)
    api_key = _api_key(request)

    body = await request.json()
    wants_stream = body.get("stream", False)

    log_request(session_id, body.get("model", "unknown"), len(body.get("messages", [])))

    # --- Anonymize request ---
    if "messages" in body:
        body["messages"] = _anonymize_messages(session_id, body["messages"])

    if "system" in body:
        if isinstance(body["system"], str):
            body["system"] = _anonymize_text(session_id, body["system"])
        elif isinstance(body["system"], list):
            body["system"] = _anonymize_value(session_id, body["system"])

    # Force non-streaming so we can deanonymize the full response
    body["stream"] = False

    # --- Forward to Claude ---
    forward_headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    for passthrough in ("anthropic-beta",):
        if passthrough in request.headers:
            forward_headers[passthrough] = request.headers[passthrough]

    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(CLAUDE_API_URL, json=body, headers=forward_headers)

    if resp.status_code != 200:
        log_error(session_id, f"Claude returned {resp.status_code}")
        return JSONResponse(status_code=resp.status_code, content=resp.json())

    response_data = resp.json()

    # --- Deanonymize response ---
    swaps = 0
    if "content" in response_data:
        response_data["content"], swaps = deanonymize_content_blocks(session_id, response_data["content"])
    log_response(session_id, response_data.get("stop_reason", "unknown"), swaps)

    response_headers = {"x-anonymyzr-session": session_id}

    if wants_stream:
        return StreamingResponse(
            _simulate_sse(response_data),
            media_type="text/event-stream",
            headers=response_headers,
        )

    return JSONResponse(content=response_data, headers=response_headers)


@app.delete("/v1/sessions/{session_id}")
async def clear_session(session_id: str):
    """Explicitly clear a session's mapping table."""
    mapper.clear_session(session_id)
    return {"cleared": session_id}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "anonymyzr", "sessions": len(mapper.list_sessions())}


# ---------------------------------------------------------------------------
# SSE simulation
# ---------------------------------------------------------------------------

async def _simulate_sse(data: dict):
    """
    Re-emit a complete Anthropic response as a valid SSE stream.
    Chunks text content into ~20-character deltas to mimic real streaming.
    """
    msg_id = data.get("id", f"msg_{uuid.uuid4().hex[:24]}")
    model = data.get("model", "")
    usage = data.get("usage", {})

    def sse(event: str, payload: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(payload)}\n\n"

    yield sse("message_start", {
        "type": "message_start",
        "message": {
            "id": msg_id, "type": "message", "role": "assistant",
            "content": [], "model": model,
            "stop_reason": None, "stop_sequence": None,
            "usage": usage,
        },
    })

    for idx, block in enumerate(data.get("content", [])):
        btype = block.get("type")

        yield sse("content_block_start", {
            "type": "content_block_start",
            "index": idx,
            "content_block": {"type": btype, "text": ""} if btype == "text" else block,
        })

        if btype == "text":
            text = block.get("text", "")
            for i in range(0, len(text), 20):
                yield sse("content_block_delta", {
                    "type": "content_block_delta",
                    "index": idx,
                    "delta": {"type": "text_delta", "text": text[i:i + 20]},
                })

        yield sse("content_block_stop", {"type": "content_block_stop", "index": idx})

    yield sse("message_delta", {
        "type": "message_delta",
        "delta": {
            "stop_reason": data.get("stop_reason", "end_turn"),
            "stop_sequence": data.get("stop_sequence"),
        },
        "usage": usage,
    })

    yield sse("message_stop", {"type": "message_stop"})
