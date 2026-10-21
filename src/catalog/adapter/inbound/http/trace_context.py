"""Which trace a request belongs to, and which span is ours (W3C Trace Context, https://www.w3.org/TR/trace-context/).

The gateway starts the trace and sends it as `traceparent`. This service keeps the trace id, makes a span of its own and
returns it, so a log line, a database call and a complaint with a reference all lead to the same request. The
`X-Correlation-Id` of norm 5.3.9 keeps working next to it (correlation.py): the two are adopted side by side.

A header that cannot be trusted never breaks a request: it is ignored and a new trace starts.
"""

import re
import secrets
from contextvars import ContextVar
from dataclasses import dataclass

HEADER = "traceparent"
VERSION = "00"
SAMPLED = "01"
_MAX_LENGTH = 512   # a version 00 header is 55 characters; a later version may add fields, but not kilobytes
_TRACEPARENT = re.compile(r"([0-9a-f]{2})-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})(-.*)?", re.DOTALL)
_NO_TRACE, _NO_SPAN = "0" * 32, "0" * 16


@dataclass(frozen=True)
class Traceparent:
    """What a caller sent: its trace, the span that called us (our parent) and its flags."""

    trace_id: str
    parent_id: str
    flags: str


@dataclass(frozen=True)
class TraceContext:
    """Where this request stands: its trace, our own span and the span of the caller, if there was one."""

    trace_id: str
    span_id: str
    parent_span_id: str | None
    flags: str


current_trace: ContextVar[TraceContext | None] = ContextVar("trace", default=None)


def parse_traceparent(value: str | None) -> Traceparent | None:
    """The fields of a valid header, or None. Strict, as the specification asks: lowercase hexadecimal, no all-zero ids."""
    if not value or len(value) > _MAX_LENGTH:
        return None
    match = _TRACEPARENT.fullmatch(value)
    if not match:
        return None
    version, trace_id, parent_id, flags, extra = match.groups()
    if version == "ff" or trace_id == _NO_TRACE or parent_id == _NO_SPAN:
        return None
    if version == VERSION and extra:   # version 00 has exactly four fields; a later one is read by its first four
        return None
    return Traceparent(trace_id, parent_id, flags)


def start_trace() -> TraceContext:
    return TraceContext(_random_hex(16), _random_hex(8), None, SAMPLED)


def continue_trace(received: Traceparent) -> TraceContext:
    """The same trace, a span of our own, and the caller's span as its parent. The caller's decision to sample is kept."""
    return TraceContext(received.trace_id, _random_hex(8), received.parent_id, received.flags)


def format_traceparent(trace: TraceContext) -> str:
    return f"{VERSION}-{trace.trace_id}-{trace.span_id}-{trace.flags}"


def _random_hex(byte_count: int) -> str:
    """Random, and never all zeros (the specification calls that id invalid)."""
    while True:
        value = secrets.token_hex(byte_count)
        if value.strip("0"):
            return value


class TraceContextMiddleware:
    """A plain ASGI middleware, like the correlation one: it keeps the context of the request intact."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        received = parse_traceparent(dict(scope["headers"]).get(HEADER.encode(), b"").decode("latin-1"))
        trace = continue_trace(received) if received else start_trace()
        scope.setdefault("state", {})["trace"] = trace
        token = current_trace.set(trace)

        async def send_with_trace(message) -> None:
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != HEADER.encode()]
                message["headers"] = headers + [(HEADER.encode(), format_traceparent(trace).encode("ascii"))]
            await send(message)

        try:
            await self.app(scope, receive, send_with_trace)
        finally:
            current_trace.reset(token)
