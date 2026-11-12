"""The configuration of the service, read once. Every limit has a value here (norm 5.3.10); a secret has none."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

SERVICE_NAME = "catalog-api"
ENVIRONMENTS = ("dev", "qa", "main")   # the three of the platform (Annex J): their data never mixes


@dataclass(frozen=True)
class Settings:
    port: int
    mongodb_uri: str
    jwt_public_key: str
    service_version: str                # the release that is running: it is on every log line, to tie a failure to it
    environment: str                    # dev, qa or main: it is on every log line, to keep the three apart
    mongo_pool_max: int                 # connections in the pool
    mongo_server_selection_ms: int      # wait for a server: the pool, the cluster, the network
    mongo_connect_ms: int
    mongo_socket_ms: int                # time per operation
    keep_alive_seconds: int
    graceful_shutdown_seconds: int

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Settings":
        """Refuses to start on a missing piece: a service that cannot verify tokens or reach its database must not boot."""
        if not env.get("MONGODB_URI"):
            raise ValueError("MONGODB_URI is required: the database `catalog`, as catalog_app")
        key = env.get("JWT_PUBLIC_KEY") or (Path(env["JWT_PUBLIC_KEY_FILE"]).read_text() if env.get("JWT_PUBLIC_KEY_FILE") else "")
        if not key:
            raise ValueError("set JWT_PUBLIC_KEY or JWT_PUBLIC_KEY_FILE: the service verifies tokens itself")
        version, environment = env.get("SERVICE_VERSION", "dev"), env.get("ENVIRONMENT", "dev")
        if not version.strip():
            raise ValueError("SERVICE_VERSION must not be blank: a failure could not be tied to a release")
        if environment not in ENVIRONMENTS:
            raise ValueError(f"ENVIRONMENT must be one of {', '.join(ENVIRONMENTS)}, not {environment!r}")
        return cls(port=int(env.get("PORT", 8082)), mongodb_uri=env["MONGODB_URI"], jwt_public_key=key,
                   service_version=version.strip(), environment=environment,
                   mongo_pool_max=int(env.get("MONGO_POOL_MAX", 10)),
                   mongo_server_selection_ms=int(env.get("MONGO_SERVER_SELECTION_MS", 3_000)),
                   mongo_connect_ms=int(env.get("MONGO_CONNECT_MS", 2_000)),
                   mongo_socket_ms=int(env.get("MONGO_SOCKET_MS", 5_000)),
                   keep_alive_seconds=int(env.get("KEEP_ALIVE_SECONDS", 60)),
                   graceful_shutdown_seconds=int(env.get("GRACEFUL_SHUTDOWN_SECONDS", 20)))
