"""Reuses the X-Correlation-Id the gateway set, or creates one, and returns it (norm 5.3.9).

It goes into the request state, so the traceId of any error carries it, and into a context variable, so every log line
of the request does. One access line per request, in JSON: never the payload and never the token.
"""

import json
import logging
import time
import uuid
from contextvars import ContextVar

HEADER = "x-correlation-id"
current_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")
ACCESS = logging.getLogger("access")


class CorrelationMiddleware:
    """A plain ASGI middleware: unlike BaseHTTPMiddleware it keeps the context of the request intact."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        received = dict(scope["headers"]).get(HEADER.encode(), b"").decode("latin-1")
        correlation_id = received if received.strip() and len(received) <= 128 else str(uuid.uuid4())
        scope.setdefault("state", {})["correlation_id"] = correlation_id
        token = current_correlation_id.set(correlation_id)
        started, status = time.perf_counter(), 500

        async def send_with_id(message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != HEADER.encode()]
                message["headers"] = headers + [(HEADER.encode(), correlation_id.encode("latin-1"))]
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            ACCESS.info(json.dumps({"method": scope["method"], "path": scope["path"], "status": status,
                                    "durationMs": round((time.perf_counter() - started) * 1000),
                                    "correlationId": correlation_id}))
            current_correlation_id.reset(token)
