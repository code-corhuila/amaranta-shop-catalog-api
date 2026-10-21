"""Every log line is one JSON object in the format of the team's log contract (norm 5.3.9).

Required on every line: timestamp, level, service, version, environment, trace_id, span_id, correlation_id, event, message
and duration_ms. The optional domain fields are the ones in WRITTEN_WHEN_GIVEN. Nothing else a caller puts on a record is
written: that is how the contract's "never log" list (tokens, identities, search text, passwords) holds even on the day
someone forgets it.
"""

import json
import logging
import re
import sys
from datetime import datetime, timezone

from catalog.adapter.inbound.http.correlation import current_correlation_id
from catalog.adapter.inbound.http.trace_context import current_trace

LEVELS = {"WARNING": "WARN", "CRITICAL": "ERROR"}   # the contract has four levels: DEBUG, INFO, WARN, ERROR
DEFAULT_EVENT = "app.log"
WRITTEN_WHEN_GIVEN = ("http_status", "method", "path", "product_id", "category", "result_count", "attempt", "rule_code")
# The credentials part of an address, scheme://<user>:<password>@host/db: a driver can put it in an error message.
_ADDRESS_CREDENTIALS = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@")


def redact(text: str) -> str:
    return _ADDRESS_CREDENTIALS.sub(r"\1***:***@", text)


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str, version: str, environment: str) -> None:
        super().__init__()
        self._identity = {"service": service, "version": version, "environment": environment}

    def format(self, record: logging.LogRecord) -> str:
        trace = current_trace.get()
        line = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": LEVELS.get(record.levelname, record.levelname),
            **self._identity,
            # An id on the record wins over the ambient one: an unhandled error is logged after its request has ended.
            "trace_id": getattr(record, "trace_id", trace.trace_id if trace else ""),
            "span_id": getattr(record, "span_id", trace.span_id if trace else ""),
            "correlation_id": getattr(record, "correlation_id", current_correlation_id.get()),
            "event": getattr(record, "event", DEFAULT_EVENT),
            "message": redact(record.getMessage()),
            "duration_ms": getattr(record, "duration_ms", 0),
        }
        line.update({name: getattr(record, name) for name in WRITTEN_WHEN_GIVEN if hasattr(record, name)})
        if record.exc_info:
            line["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(line, default=str)


def configure_logging(service: str, version: str, environment: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service, version, environment))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
