"""The composition root reads its configuration once and refuses to start on a missing or a wrong piece.

The format of the log lines is in test_log_contract.py.
"""

import pytest

from apps.api.settings import Settings
from tests.http.signing import PUBLIC_PEM

# The address is put together here: no address with a user and a password is written in the source.
ENV = {"MONGODB_URI": "mongodb://catalog_app:" + "FAKE-DB-MARKER" + "@mongo:27017/catalog?authSource=catalog",
       "JWT_PUBLIC_KEY": PUBLIC_PEM.replace("\n", "\\n")}


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


# who wrote the log line (the log contract) ----------------------------------------------------------------------------

def test_the_release_and_the_environment_default_to_dev():
    settings = Settings.from_env(ENV)

    assert (settings.service_version, settings.environment) == ("dev", "dev")


def test_the_release_and_the_environment_come_from_the_environment_of_the_container():
    settings = Settings.from_env({**ENV, "SERVICE_VERSION": "2.0.0", "ENVIRONMENT": "qa"})

    assert (settings.service_version, settings.environment) == ("2.0.0", "qa")


@pytest.mark.parametrize("environment", ["dev", "qa", "main"])
def test_the_three_environments_of_the_platform_are_accepted(environment):
    assert Settings.from_env({**ENV, "ENVIRONMENT": environment}).environment == environment


@pytest.mark.parametrize("environment", ["prod", "QA", "", "staging"])
def test_an_unknown_environment_is_refused_so_that_data_of_two_never_mixes(environment):
    with pytest.raises(ValueError, match="ENVIRONMENT"):
        Settings.from_env({**ENV, "ENVIRONMENT": environment})


def test_a_blank_release_is_refused_because_a_failure_could_not_be_tied_to_a_release():
    with pytest.raises(ValueError, match="SERVICE_VERSION"):
        Settings.from_env({**ENV, "SERVICE_VERSION": "  "})
