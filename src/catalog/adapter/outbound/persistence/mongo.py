"""The products of the database `catalog`, written for the collection that amaranta-shop-catalog-db creates.

It connects as catalog_app and never creates a collection or an index (norm 5.2.1). `price` and `stockQuantity` are
always written as Int64: the validator refuses a plain Python int that pymongo would encode as an int32.
"""

from datetime import datetime

from bson import Int64
from pymongo import ASCENDING
from pymongo.database import Database

from catalog.application.page import Page
from catalog.application.port.outbound.products import ProductRepository
from catalog.domain.model.category import Category
from catalog.domain.model.product import Product


class MongoProductRepository(ProductRepository):
    def __init__(self, database: Database) -> None:
        self._products = database["product"]

    def find_by_ids(self, ids: list[str]) -> list[Product]:
        return [_to_product(doc) for doc in self._products.find({"_id": {"$in": ids}})]

    def find_by_id(self, product_id: str) -> Product | None:
        doc = self._products.find_one({"_id": product_id})
        return _to_product(doc) if doc else None

    def find_active_page(self, page: int, limit: int) -> Page[Product]:
        query = {"isActive": True}
        docs = self._products.find(query).sort([("name", ASCENDING), ("_id", ASCENDING)]).skip((page - 1) * limit).limit(limit)
        return Page([_to_product(d) for d in docs], page, limit, self._products.count_documents(query))

    def try_decrement_stock(self, product_id: str, quantity: int, now: datetime) -> bool:
        # One conditional write on one document: active AND enough stock. Two requests for the last unit race the
        # SAME filter, and the database lets only one of them match. No transaction, no lock, no replica set needed.
        result = self._products.update_one(
            {"_id": product_id, "isActive": True, "stockQuantity": {"$gte": Int64(quantity)}},
            {"$inc": {"stockQuantity": Int64(-quantity)}, "$set": {"updatedAt": now}},
        )
        return result.matched_count == 1

    def increment_stock(self, product_id: str, quantity: int, now: datetime) -> None:
        # No upsert: giving units back to a product that was deleted must not bring it back.
        self._products.update_one({"_id": product_id}, {"$inc": {"stockQuantity": Int64(quantity)}, "$set": {"updatedAt": now}})


def _to_product(doc: dict) -> Product:
    return Product.reconstitute(
        id=doc["_id"], sku=doc["sku"], name=doc["name"], description=doc["description"], category=Category(doc["category"]),
        price=int(doc["price"]), stock_quantity=int(doc["stockQuantity"]), image_url=doc["imageUrl"], is_active=doc["isActive"],
        created_at=doc["createdAt"], updated_at=doc["updatedAt"])
