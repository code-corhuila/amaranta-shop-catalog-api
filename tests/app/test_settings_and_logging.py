"""The composition root reads its configuration once, refuses to start on a missing piece, and logs in JSON."""

import json
import logging

import pytest

from apps.api.logging_setup import JsonFormatter
from apps.api.settings import Settings
from catalog.adapter.inbound.http.correlation import current_correlation_id
from tests.http.signing import PUBLIC_PEM

ENV = {"MONGODB_URI": "mongodb://catalog_app:secret@mongo:27017/catalog?authSource=catalog", "JWT_PUBLIC_KEY": PUBLIC_PEM.replace("\n", "\\n")}


def test_the_defaults_are_the_limits_the_norm_asks_to_be_declared():
    settings = Settings.from_env(ENV)

    assert settings.port == 8082
    assert (settings.mongo_pool_max, settings.mongo_server_selection_ms, settings.mongo_socket_ms) == (10, 3_000, 5_000)
    assert (settings.keep_alive_seconds, settings.graceful_shutdown_seconds) == (60, 20)


def test_everything_can_be_overridden_from_the_environment():
    settings = Settings.from_env({**ENV, "PORT": "9000", "MONGO_POOL_MAX": "25"})

    assert (settings.port, settings.mongo_pool_max) == (9000, 25)


def test_the_public_key_can_come_from_a_file(tmp_path):
    key_file = tmp_path / "public.pem"
    key_file.write_text(PUBLIC_PEM)

    settings = Settings.from_env({"MONGODB_URI": ENV["MONGODB_URI"], "JWT_PUBLIC_KEY_FILE": str(key_file)})

    assert "BEGIN PUBLIC KEY" in settings.jwt_public_key


@pytest.mark.parametrize("missing", ["MONGODB_URI", "JWT_PUBLIC_KEY"])
def test_it_refuses_to_start_without_the_database_or_the_key(missing):
    env = {k: v for k, v in ENV.items() if k != missing}

    with pytest.raises(ValueError, match=missing if missing == "MONGODB_URI" else "JWT_PUBLIC_KEY"):
        Settings.from_env(env)


def test_a_log_line_is_one_json_object_that_carries_the_correlation_id():
    record = logging.LogRecord("catalog", logging.WARNING, __file__, 1, "stock %s", ("low",), None)
    token = current_correlation_id.set("trace-7")
    try:
        line = json.loads(JsonFormatter().format(record))
    finally:
        current_correlation_id.reset(token)

    assert (line["level"], line["logger"], line["message"], line["correlationId"]) == ("WARNING", "catalog", "stock low", "trace-7")
    assert "@timestamp" in line


def test_an_exception_is_logged_in_full_in_the_same_json_line():
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        import sys
        record = logging.LogRecord("catalog", logging.ERROR, __file__, 1, "unhandled", (), sys.exc_info())

    assert "RuntimeError: boom" in json.loads(JsonFormatter().format(record))["exception"]
