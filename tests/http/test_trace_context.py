"""The service joins the trace of the caller (W3C Trace Context), or starts one, and says which trace it is on.

The gateway creates the trace and sends `traceparent`; this service keeps the trace id, makes a span of its own and
returns it, so the line of a log, the span of a database call and a complaint with a reference all lead to one request.
A header that cannot be trusted never breaks a request: it is ignored and a new trace starts.
"""

import re

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from catalog.adapter.inbound.http.app import create_app
from catalog.adapter.inbound.http.trace_context import (
    TraceContext,
    continue_trace,
    current_trace,
    format_traceparent,
    parse_traceparent,
    start_trace,
)

TRACE_ID = "7c1e5b0a93d24f68b2a4e19d3f0c8a57"
CALLER_SPAN = "a3f91c20d4b8e657"
VALID = f"00-{TRACE_ID}-{CALLER_SPAN}-01"
TRACEPARENT = re.compile(r"^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$")

router = APIRouter()


@router.get("/whoami")
def whoami():
    trace = current_trace.get()
    return {"trace_id": trace.trace_id, "span_id": trace.span_id, "parent_span_id": trace.parent_span_id}


client = TestClient(create_app(routers=[router]))


def test_a_valid_traceparent_is_read_field_by_field():
    parsed = parse_traceparent(VALID)

    assert (parsed.trace_id, parsed.parent_id, parsed.flags) == (TRACE_ID, CALLER_SPAN, "01")


@pytest.mark.parametrize("value", [
    None,
    "",
    "garbage",
    f"00-{TRACE_ID}-{CALLER_SPAN}",                       # a field is missing
    f"00-{TRACE_ID[:-1]}-{CALLER_SPAN}-01",               # a trace id of 31 characters
    f"00-{TRACE_ID}-{CALLER_SPAN[:-1]}-01",               # a span id of 15 characters
    f"00-{TRACE_ID.upper()}-{CALLER_SPAN}-01",            # the specification asks for lowercase
    f"00-{'0' * 32}-{CALLER_SPAN}-01",                    # the all-zero trace id is invalid
    f"00-{TRACE_ID}-{'0' * 16}-01",                       # and so is the all-zero span id
    f"ff-{TRACE_ID}-{CALLER_SPAN}-01",                    # version ff is invalid
    f"00-{TRACE_ID}-{CALLER_SPAN}-01-extra",              # version 00 has exactly four fields
    f"00-{TRACE_ID}-{CALLER_SPAN}-zz",                    # the flags are hexadecimal
    f" {VALID}",                                          # nothing is trimmed: it is not what was sent
    "00-" + "g" * 32 + f"-{CALLER_SPAN}-01",
    "x" * 5000,
])
def test_a_value_that_cannot_be_trusted_is_refused(value):
    assert parse_traceparent(value) is None


def test_a_later_version_is_read_by_its_first_four_fields():
    parsed = parse_traceparent(f"01-{TRACE_ID}-{CALLER_SPAN}-01-whatever-the-future-adds")

    assert (parsed.trace_id, parsed.parent_id) == (TRACE_ID, CALLER_SPAN)


def test_continuing_a_trace_keeps_its_id_and_makes_a_span_of_our_own():
    ours = continue_trace(parse_traceparent(VALID))

    assert ours.trace_id == TRACE_ID
    assert ours.parent_span_id == CALLER_SPAN
    assert re.fullmatch(r"[0-9a-f]{16}", ours.span_id) and ours.span_id not in ("0" * 16, CALLER_SPAN)
    assert ours.flags == "01"


def test_the_decision_to_sample_made_by_the_caller_is_kept():
    ours = continue_trace(parse_traceparent(f"00-{TRACE_ID}-{CALLER_SPAN}-00"))

    assert ours.flags == "00"


def test_starting_a_trace_makes_a_fresh_id_and_no_parent():
    one, other = start_trace(), start_trace()

    assert re.fullmatch(r"[0-9a-f]{32}", one.trace_id) and one.trace_id != "0" * 32
    assert one.parent_span_id is None
    assert one.trace_id != other.trace_id


def test_a_context_is_written_as_a_traceparent_the_next_service_can_read():
    written = format_traceparent(TraceContext(TRACE_ID, "e2b46d0a7f19c853", CALLER_SPAN, "01"))

    assert written == f"00-{TRACE_ID}-e2b46d0a7f19c853-01"
    assert parse_traceparent(written).parent_id == "e2b46d0a7f19c853"


def test_a_request_with_a_trace_is_answered_on_the_same_trace_with_a_span_of_its_own():
    response = client.get("/whoami", headers={"traceparent": VALID})

    assert TRACEPARENT.match(response.headers["traceparent"])
    returned_trace, returned_span = response.headers["traceparent"].split("-")[1:3]
    assert returned_trace == TRACE_ID
    assert returned_span != CALLER_SPAN
    # What the code of the request saw is what the response says, so a log line and the header agree.
    assert response.json() == {"trace_id": TRACE_ID, "span_id": returned_span, "parent_span_id": CALLER_SPAN}


def test_a_request_without_a_trace_starts_one_and_says_so():
    response = client.get("/whoami")

    assert TRACEPARENT.match(response.headers["traceparent"])
    assert response.json()["parent_span_id"] is None
    assert response.json()["trace_id"] == response.headers["traceparent"].split("-")[1]


@pytest.mark.parametrize("value", ["garbage", f"00-{'0' * 32}-{CALLER_SPAN}-01", "x" * 5000])
def test_a_broken_header_never_breaks_the_request(value):
    response = client.get("/whoami", headers={"traceparent": value})

    assert response.status_code == 200
    assert response.json()["trace_id"] != TRACE_ID and TRACEPARENT.match(response.headers["traceparent"])


def test_two_requests_never_share_a_span():
    first, second = client.get("/whoami"), client.get("/whoami")

    assert first.json()["span_id"] != second.json()["span_id"]
    assert first.json()["trace_id"] != second.json()["trace_id"]


def test_the_trace_ends_with_the_request():
    client.get("/whoami", headers={"traceparent": VALID})

    assert current_trace.get() is None


def test_an_error_answer_is_on_the_trace_too():
    response = client.get("/no/such/route", headers={"traceparent": VALID})

    assert response.status_code == 404
    assert response.headers["traceparent"].split("-")[1] == TRACE_ID
