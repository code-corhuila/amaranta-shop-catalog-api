"""Errors of the application layer, as opposed to the invariants of the domain."""


class ProductNotFoundError(Exception):
    """There is no product with that id. Answered 404 NOT_FOUND."""

    def __init__(self, product_id: str) -> None:
        super().__init__(f"product {product_id} was not found")
        self.product_id = product_id
