"""One line per request, in the format of the log contract, on the trace the request belongs to.

The line is written when the request ends, so what it says (status, duration) is what the caller got. It carries the
correlation id and the trace of that request, never the query string and never a header: a visitor's search text and a
staff member's token must not be where an operator reads.
"""

import json
import logging

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from apps.api.logging_setup import JsonFormatter
from catalog.adapter.inbound.http.app import create_app

router = APIRouter()


@router.get("/ok")
def ok():
    return {"status": "fine"}


@router.get("/rule")
def rule():
    from catalog.domain.model.errors import BusinessRuleViolation

    raise BusinessRuleViolation("INV-PRODUCT-002", "not enough stock")


# A marker, not a credential; the address is put together here so that none with a user and a password is in the source.
MARKER = "LEAK-MARKER-DB"


@router.get("/boom")
def boom():
    raise RuntimeError("cannot connect to mongodb://catalog_app:" + MARKER + "@mongo:27017/catalog")


class Capture(logging.Handler):
    """Formats each record AS IT IS EMITTED, while the request is still being served, as a real handler does."""

    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.formatter = JsonFormatter(service="catalog-api", version="2.0.0", environment="qa")
        self.lines: list[dict] = []
        self.raw: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        text = self.format(record)
        self.raw.append(text)
        self.lines.append(json.loads(text))


SERVICE_LOGGERS = ("access", "catalog")   # only the service's own: the test client logs the full URL of its calls too


@pytest.fixture
def logs():
    capture = Capture()
    loggers = [logging.getLogger(name) for name in SERVICE_LOGGERS]
    previous = [logger.level for logger in loggers]
    for logger in loggers:
        logger.addHandler(capture)
        logger.setLevel(logging.INFO)
    yield capture
    for logger, level in zip(loggers, previous):
        logger.removeHandler(capture)
        logger.setLevel(level)


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(routers=[router]), raise_server_exceptions=False)


def access(lines: list[dict]) -> list[dict]:
    return [entry for entry in lines if entry["event"] == "http.request.completed"]


def test_a_request_writes_one_access_line_with_what_the_caller_got(client, logs):
    client.get("/ok")

    (entry,) = access(logs.lines)
    assert (entry["method"], entry["path"], entry["http_status"]) == ("GET", "/ok", 200)
    assert isinstance(entry["duration_ms"], int) and entry["duration_ms"] >= 0
    assert entry["level"] == "INFO" and entry["service"] == "catalog-api"


def test_the_access_line_is_on_the_correlation_id_and_the_trace_the_response_returned(client, logs):
    response = client.get("/ok", headers={"X-Correlation-Id": "e2e-trace-buy",
                                          "traceparent": "00-7c1e5b0a93d24f68b2a4e19d3f0c8a57-a3f91c20d4b8e657-01"})

    (entry,) = access(logs.lines)
    returned_trace, returned_span = response.headers["traceparent"].split("-")[1:3]
    assert entry["correlation_id"] == response.headers["x-correlation-id"] == "e2e-trace-buy"
    assert (entry["trace_id"], entry["span_id"]) == (returned_trace, returned_span)
    assert entry["trace_id"] == "7c1e5b0a93d24f68b2a4e19d3f0c8a57"


def test_a_client_error_is_information_and_a_server_error_is_an_error(client, logs):
    client.get("/rule")
    client.get("/boom")

    by_status = {entry["http_status"]: entry for entry in access(logs.lines)}
    assert by_status[422]["level"] == "INFO"       # the visitor asked for something the rules refuse: not our failure
    assert by_status[500]["level"] == "ERROR"


def test_the_query_string_is_never_written(client, logs):
    client.get("/ok?q=salmon-for-my-dog&page=2")

    assert "salmon-for-my-dog" not in "".join(logs.raw)
    assert access(logs.lines)[0]["path"] == "/ok"


def test_a_header_is_never_written(client, logs):
    client.get("/ok", headers={"Authorization": "LEAK-MARKER-HEADER", "Cookie": "LEAK-MARKER-COOKIE"})

    text = "".join(logs.raw)
    assert "LEAK-MARKER-HEADER" not in text and "LEAK-MARKER-COOKIE" not in text


def test_an_unhandled_error_is_logged_on_its_own_request_even_though_its_context_has_ended(client, logs):
    """The handler of an unhandled error runs after the request's context is gone, so it must carry the ids itself."""
    client.get("/boom", headers={"X-Correlation-Id": "trace-500",
                                 "traceparent": "00-7c1e5b0a93d24f68b2a4e19d3f0c8a57-a3f91c20d4b8e657-01"})

    failed = [entry for entry in logs.lines if entry["event"] == "http.request.failed"]
    assert len(failed) == 1
    assert failed[0]["level"] == "ERROR" and failed[0]["http_status"] == 500
    assert failed[0]["correlation_id"] == "trace-500"
    assert failed[0]["trace_id"] == "7c1e5b0a93d24f68b2a4e19d3f0c8a57"
    assert "RuntimeError" in failed[0]["exception"]


def test_a_password_inside_an_unhandled_error_never_reaches_the_log(client, logs):
    client.get("/boom")

    assert MARKER not in "".join(logs.raw)
