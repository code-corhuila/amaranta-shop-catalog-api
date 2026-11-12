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


def ensure_valid_request(page: int, limit: int) -> None:
    """The one place that says what a page request may be: the first page is 1, and a page holds 1 to MAX_LIMIT items."""
    if page < 1:
        raise ValueError("page must be 1 or more")
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")
