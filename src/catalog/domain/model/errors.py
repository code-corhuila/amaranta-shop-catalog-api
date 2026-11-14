"""The typed errors of the domain.

Each carries the id of the rule that was broken (INV-PRODUCT-002...), so a client can branch on it without parsing a
message. The domain does not know what a 422 is: the HTTP adapter decides the status, in one place.
"""


class DomainError(Exception):
    def __init__(self, rule_id: str, message: str) -> None:
        super().__init__(message)
        self.rule_id = rule_id
        self.message = message


class BusinessRuleViolation(DomainError):
    """An invariant of the domain would be broken. Answered as 422 BUSINESS_RULE_VIOLATION."""
