"""Every log line is one JSON object, and carries the correlation id of the request it belongs to (norm 5.3.9)."""

import json
import logging
import sys
from datetime import datetime, timezone

from catalog.adapter.inbound.http.correlation import current_correlation_id


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line = {"@timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(), "level": record.levelname,
                "logger": record.name, "message": record.getMessage(), "correlationId": current_correlation_id.get()}
        if record.exc_info:
            line["exception"] = self.formatException(record.exc_info)
        return json.dumps(line)


class AccessFormatter(JsonFormatter):
    """The access line is already JSON (it has its own fields), so it goes out as it is."""

    def format(self, record: logging.LogRecord) -> str:
        return record.getMessage()


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    access = logging.StreamHandler(sys.stdout)
    access.setFormatter(AccessFormatter())
    logging.getLogger("access").handlers = [access]
    logging.getLogger("access").propagate = False
