"""The ONLY place where an error becomes a status code (norm 5.3, spec section 8.3).

The domain raises typed errors and does not know what a 422 is. Every error answers with the same envelope
{error, message, details?, traceId}, the unexpected ones included, and the detail of those goes to the log only:
a client never sees a driver message or an address.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from catalog.application.errors import ProductNotFoundError
from catalog.domain.model.errors import BusinessRuleViolation

LOG = logging.getLogger("catalog")


class UnauthorizedError(Exception):
    """No token, or a token that is invalid or expired. Answered 401."""


class ForbiddenError(Exception):
    """A valid token whose role may not do this. Answered 403."""


def envelope(request: Request, status: int, code: str, message: str, details: list[dict] | None = None) -> JSONResponse:
    trace_id = getattr(request.state, "correlation_id", "")
    body = {"error": code, "message": message, "traceId": trace_id}
    if details:
        body["details"] = details
    return JSONResponse(body, status_code=status, headers={"X-Correlation-Id": trace_id} if trace_id else None)


def _field(location: tuple) -> str:
    """('body', 'items', 0, 'quantity') -> 'items[0].quantity'; the part that says where it came from is dropped."""
    out = ""
    for part in location[1:]:
        out += f"[{part}]" if isinstance(part, int) else ("." if out else "") + str(part)
    return out or str(location[0])


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation(request: Request, error: RequestValidationError):
        if any(e["type"] == "json_invalid" for e in error.errors()):
            return envelope(request, 400, "VALIDATION_ERROR", "the body is not valid JSON")
        details = [{"field": _field(tuple(e["loc"])), "message": e["msg"]} for e in error.errors()]
        return envelope(request, 400, "VALIDATION_ERROR", "the request has invalid fields", details)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, error: StarletteHTTPException):
        if error.status_code == 404:
            return envelope(request, 404, "NOT_FOUND", "no such route")
        if error.status_code == 405:
            return envelope(request, 405, "NOT_FOUND", "method not allowed on this route")
        return envelope(request, error.status_code, "VALIDATION_ERROR", "the request cannot be processed")

    @app.exception_handler(BusinessRuleViolation)
    async def rule(request: Request, error: BusinessRuleViolation):
        return envelope(request, 422, "BUSINESS_RULE_VIOLATION", error.message, [{"field": "rule", "message": error.rule_id}])

    @app.exception_handler(ProductNotFoundError)
    async def not_found(request: Request, error: ProductNotFoundError):
        return envelope(request, 404, "NOT_FOUND", "the product does not exist")

    @app.exception_handler(UnauthorizedError)
    async def unauthorized(request: Request, error: UnauthorizedError):
        return envelope(request, 401, "UNAUTHORIZED", str(error))

    @app.exception_handler(ForbiddenError)
    async def forbidden(request: Request, error: ForbiddenError):
        return envelope(request, 403, "FORBIDDEN", str(error))

    @app.exception_handler(Exception)
    async def unexpected(request: Request, error: Exception):
        # This handler runs after the request's context has ended, so the ids come from the request itself.
        trace = getattr(request.state, "trace", None)
        LOG.error("unhandled error", exc_info=error,
                  extra={"event": "http.request.failed", "http_status": 500,
                         "correlation_id": getattr(request.state, "correlation_id", ""),
                         "trace_id": trace.trace_id if trace else "", "span_id": trace.span_id if trace else ""})
        return envelope(request, 500, "INTERNAL_ERROR", "unexpected error")
