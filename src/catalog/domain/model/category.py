from enum import Enum


class Category(str, Enum):
    """The five categories of the shop. The validator of catalog-db refuses any other value."""

    FOOD = "FOOD"
    ACCESSORIES = "ACCESSORIES"
    HYGIENE = "HYGIENE"
    MEDICATION = "MEDICATION"
    TOYS = "TOYS"
