"""The composition root: the ONE place that knows every concrete type and every limit (norm 5.3.10).

The core knows only its ports; here each port gets its adapter. Tests hand in their own repository, clock and ids.
"""

import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone

from fastapi import FastAPI
from pymongo import MongoClient

from apps.api.settings import Settings
from catalog.adapter.inbound.http.admin import admin_router
from catalog.adapter.inbound.http.app import create_app
from catalog.adapter.inbound.http.auth import Rs256Verifier
from catalog.adapter.inbound.http.internal import internal_router
from catalog.adapter.inbound.http.public import public_router
from catalog.adapter.outbound.persistence.mongo import MongoProductRepository
from catalog.application.port.outbound.products import ProductRepository
from catalog.application.usecase.admin import build_admin_ports
from catalog.application.usecase.browse import GetProductService, ListActiveProductsService
from catalog.application.usecase.release_stock import ReleaseStockService
from catalog.application.usecase.reserve_stock import ReserveStockService


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class UuidGenerator:
    def new_id(self) -> str:
        return str(uuid.uuid4())


def mongo_repository(settings: Settings) -> MongoProductRepository:
    client = MongoClient(settings.mongodb_uri, tz_aware=True, maxPoolSize=settings.mongo_pool_max,
                         serverSelectionTimeoutMS=settings.mongo_server_selection_ms, connectTimeoutMS=settings.mongo_connect_ms,
                         socketTimeoutMS=settings.mongo_socket_ms)
    return MongoProductRepository(client.get_default_database())   # the database named in the URI: catalog


def build_app(settings: Settings, products: ProductRepository | None = None, clock=None, ids=None,
              time_source: Callable[[], float] = time.time) -> FastAPI:
    products = products or mongo_repository(settings)
    clock = clock or SystemClock()
    ids = ids or UuidGenerator()
    verifier = Rs256Verifier(settings.jwt_public_key, clock=time_source)
    return create_app(routers=[
        public_router(ListActiveProductsService(products), GetProductService(products)),
        internal_router(ReserveStockService(products, clock), ReleaseStockService(products, clock)),
        admin_router(build_admin_ports(products, clock, ids), verifier),
    ])
