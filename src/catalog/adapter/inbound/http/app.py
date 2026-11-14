from collections.abc import Iterable

from fastapi import APIRouter, FastAPI

from catalog.adapter.inbound.http.access_log import AccessLogMiddleware
from catalog.adapter.inbound.http.correlation import CorrelationMiddleware
from catalog.adapter.inbound.http.errors import register_error_handlers
from catalog.adapter.inbound.http.trace_context import TraceContextMiddleware


def create_app(routers: Iterable[APIRouter] = ()) -> FastAPI:
    """The HTTP application: the routers it is given, the error envelope, the correlation id, the trace and the access line.

    The interactive documentation is off: a service of the platform exposes its contract, not a way to try it.
    """
    app = FastAPI(title="catalog-api", docs_url=None, redoc_url=None, openapi_url=None)
    # The last one added is the outermost. The access line is innermost so that it is written on the ids of the request.
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(CorrelationMiddleware)
    app.add_middleware(TraceContextMiddleware)
    register_error_handlers(app)

    @app.get("/health")
    def health() -> dict[str, str]:
        """Liveness probe. Outside /api/, so it needs no token."""
        return {"status": "ok"}

    for router in routers:
        app.include_router(router)
    return app
