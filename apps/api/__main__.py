"""python -m apps.api: reads the environment, builds the service and serves it."""

import logging
import os

import uvicorn

from apps.api.composition import build_app
from apps.api.logging_setup import configure_logging
from apps.api.settings import SERVICE_NAME, Settings


def main() -> None:
    settings = Settings.from_env(os.environ)
    configure_logging(SERVICE_NAME, settings.service_version, settings.environment)
    logging.getLogger("catalog").info("%s %s starting on port %d", SERVICE_NAME, settings.service_version, settings.port,
                                      extra={"event": "service.starting"})
    uvicorn.run(build_app(settings), host="0.0.0.0", port=settings.port, log_config=None, access_log=False,
                timeout_keep_alive=settings.keep_alive_seconds, timeout_graceful_shutdown=settings.graceful_shutdown_seconds)


if __name__ == "__main__":
    main()
