"""Every log line is one JSON object with the fields of the team's log contract, so that "everything that happened to
trace X" is one filter across the gateway, the services and the worker.

Required on every line: timestamp, level, service, version, environment, trace_id, span_id, correlation_id, event,
message, duration_ms. The domain fields are optional. What the contract says never to log is not written even if a caller
puts it on the record: the formatter writes the fields it knows and nothing else.
"""

import json
import logging
import re
import sys
import uuid
from datetime import datetime, timezone

import pytest

from apps.api.logging_setup import JsonFormatter
from catalog.adapter.inbound.http.correlation import current_correlation_id
from catalog.adapter.inbound.http.trace_context import TraceContext, current_trace

REQUIRED = {"timestamp", "level", "service", "version", "environment", "trace_id", "span_id", "correlation_id", "event",
            "message", "duration_ms"}
FORMATTER = JsonFormatter(service="catalog-api", version="2.0.0", environment="qa")
TRACE = TraceContext("7c1e5b0a93d24f68b2a4e19d3f0c8a57", "a3f91c20d4b8e657", None, "01")
# Markers, not credentials: each test looks for its marker in what was written. The address is put together here so that
# no address with a user and a password is written in the source.
MARKER = "LEAK-MARKER-DB"
ADDRESS_WITH_CREDENTIALS = "mongodb://catalog_app:" + MARKER + "@mongo:27017/catalog?authSource=catalog"


def record(level=logging.INFO, message="hello %s", args=("world",), exc_info=None, **extra) -> logging.LogRecord:
    made = logging.LogRecord("catalog", level, __file__, 1, message, args, exc_info)
    for name, value in extra.items():
        setattr(made, name, value)
    return made


def line(made: logging.LogRecord) -> dict:
    return json.loads(FORMATTER.format(made))


def test_a_line_has_every_required_field_and_nothing_else():
    assert set(line(record())) == REQUIRED


def test_a_line_says_which_service_release_and_environment_wrote_it():
    written = line(record())

    assert (written["service"], written["version"], written["environment"]) == ("catalog-api", "2.0.0", "qa")


def test_the_message_is_the_formatted_text():
    assert line(record(message="stock %s of %d", args=("low", 3)))["message"] == "stock low of 3"


def test_the_timestamp_is_iso_8601_in_utc_with_milliseconds():
    made = record()
    made.created = datetime(2026, 10, 19, 14, 58, 3, 412_000, tzinfo=timezone.utc).timestamp()

    assert line(made)["timestamp"] == "2026-10-19T14:58:03.412Z"


@pytest.mark.parametrize("python_level, contract_level", [
    (logging.DEBUG, "DEBUG"), (logging.INFO, "INFO"), (logging.WARNING, "WARN"), (logging.ERROR, "ERROR"), (logging.CRITICAL, "ERROR"),
])
def test_the_levels_are_the_four_of_the_contract(python_level, contract_level):
    assert line(record(level=python_level))["level"] == contract_level


def test_the_line_carries_the_trace_and_the_correlation_id_of_the_request_being_served():
    trace_token, correlation_token = current_trace.set(TRACE), current_correlation_id.set("b81d0e47c2a94f3c")
    try:
        written = line(record())
    finally:
        current_trace.reset(trace_token)
        current_correlation_id.reset(correlation_token)

    assert (written["trace_id"], written["span_id"], written["correlation_id"]) == (TRACE.trace_id, TRACE.span_id, "b81d0e47c2a94f3c")


def test_outside_a_request_the_ids_are_empty_not_missing():
    written = line(record())

    assert (written["trace_id"], written["span_id"], written["correlation_id"]) == ("", "", "")


def test_ids_given_on_the_record_win_over_the_ambient_ones():
    """An unhandled error is logged after the request context has ended, so the handler passes the ids itself."""
    token = current_correlation_id.set("ambient")
    try:
        written = line(record(trace_id="1" * 32, span_id="2" * 16, correlation_id="explicit"))
    finally:
        current_correlation_id.reset(token)

    assert (written["trace_id"], written["span_id"], written["correlation_id"]) == ("1" * 32, "2" * 16, "explicit")


def test_the_event_is_a_stable_name_and_the_duration_defaults_to_zero():
    plain, named = line(record()), line(record(event="product.rejected", duration_ms=41))

    assert (plain["event"], plain["duration_ms"]) == ("app.log", 0)
    assert (named["event"], named["duration_ms"]) == ("product.rejected", 41)


def test_the_domain_fields_of_the_contract_are_written_when_given():
    written = line(record(product_id="399d2ea8-1ccb-4193-8255-1b51e331984d", category="FOOD", result_count=12, attempt=2,
                          rule_code="PRODUCT_NOT_FOUND", http_status=404, method="GET", path="/api/v1/products/x"))

    assert written["product_id"] == "399d2ea8-1ccb-4193-8255-1b51e331984d" and written["category"] == "FOOD"
    assert (written["result_count"], written["attempt"], written["rule_code"], written["http_status"]) == (12, 2, "PRODUCT_NOT_FOUND", 404)
    assert (written["method"], written["path"]) == ("GET", "/api/v1/products/x")


def test_what_the_contract_says_never_to_log_is_never_written_even_if_a_caller_adds_it():
    leaks = {"authorization": "LEAK-MARKER-HEADER", "token": "LEAK-MARKER-TOKEN", "password": "LEAK-MARKER-PASSWORD",
             "email": "LEAK-MARKER-EMAIL", "user_id": "LEAK-MARKER-USER", "q": "LEAK-MARKER-SEARCH",
             "search_text": "LEAK-MARKER-SEARCH-TEXT", "image_url": "LEAK-MARKER-SIGNED-URL"}

    text = FORMATTER.format(record(**leaks))

    for value in leaks.values():
        assert value not in text
    assert set(json.loads(text)) == REQUIRED


def test_a_line_is_always_one_line_even_if_the_message_has_line_breaks():
    text = FORMATTER.format(record(message="first\nsecond\r\nthird", args=()))

    assert "\n" not in text and "\r" not in text
    assert json.loads(text)["message"] == "first\nsecond\r\nthird"


def test_a_value_json_cannot_write_by_itself_is_written_as_text_instead_of_breaking_the_log():
    written = line(record(product_id=uuid.UUID("399d2ea8-1ccb-4193-8255-1b51e331984d")))

    assert written["product_id"] == "399d2ea8-1ccb-4193-8255-1b51e331984d"


def test_an_exception_is_written_in_full_in_the_same_line():
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        written = line(record(level=logging.ERROR, message="unhandled", args=(), exc_info=sys.exc_info()))

    assert "RuntimeError: boom" in written["exception"]
    assert set(written) - {"exception"} == REQUIRED


def test_a_database_address_with_credentials_inside_an_exception_is_redacted():
    """A driver can put the connection string in its message: the log must not be where a password becomes readable."""
    try:
        raise RuntimeError("cannot connect to " + ADDRESS_WITH_CREDENTIALS)
    except RuntimeError:
        written = line(record(level=logging.ERROR, message="unhandled", args=(), exc_info=sys.exc_info()))

    assert MARKER not in written["exception"] and "catalog_app" not in written["exception"]
    assert "mongodb://***:***@mongo:27017/catalog" in written["exception"]


def test_a_database_address_with_credentials_inside_a_message_is_redacted_too():
    written = line(record(message="failed for %s", args=(ADDRESS_WITH_CREDENTIALS,)))

    assert MARKER not in written["message"]
