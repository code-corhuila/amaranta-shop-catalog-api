"""One line per request, written when it ends: what the caller got and how long it took (norm 5.3.9).

It sits inside the correlation and trace middlewares, so the line is on the request's own ids. It writes the method and
the path and never the query string (a visitor's search text) and never a header (a staff member's token).
"""

import logging
import time

ACCESS = logging.getLogger("access")
EVENT = "http.request.completed"


class AccessLogMiddleware:
    """A plain ASGI middleware, like the others: it keeps the context of the request intact."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started, status = time.perf_counter(), 500   # 500 until a response starts: an error that escapes ends as one

        async def note_status(message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, note_status)
        finally:
            ACCESS.log(logging.ERROR if status >= 500 else logging.INFO, "%s %s", scope["method"], scope["path"],
                       extra={"event": EVENT, "method": scope["method"], "path": scope["path"], "http_status": status,
                              "duration_ms": round((time.perf_counter() - started) * 1000)})
