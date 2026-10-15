from typing import Protocol


class IdGenerator(Protocol):
    def new_id(self) -> str:
        """A new product id, a UUID in text form."""
