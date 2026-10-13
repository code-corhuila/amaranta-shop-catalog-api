from collections.abc import Iterable

from fastapi import APIRouter, FastAPI

from catalog.adapter.inbound.http.correlation import CorrelationMiddleware
from catalog.adapter.inbound.http.errors import register_error_handlers


def create_app(routers: Iterable[APIRouter] = ()) -> FastAPI:
    """The HTTP application: the routers it is given, the error envelope and the correlation id.

    The interactive documentation is off: a service of the platform exposes its contract, not a way to try it.
    """
    app = FastAPI(title="catalog-api", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(CorrelationMiddleware)
    register_error_handlers(app)

    @app.get("/health")
    def health() -> dict[str, str]:
        """Liveness probe. Outside /api/, so it needs no token."""
        return {"status": "ok"}

    for router in routers:
        app.include_router(router)
    return app
