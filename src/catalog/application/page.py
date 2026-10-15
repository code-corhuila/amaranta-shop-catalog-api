from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")

MAX_LIMIT = 100


@dataclass(frozen=True)
class Page(Generic[T]):
    """One bounded page of a list. A list is never unbounded: no query can come back with a million rows one day."""

    data: list[T]
    page: int
    limit: int
    total: int

    @property
    def total_pages(self) -> int:
        return -(-self.total // self.limit)
