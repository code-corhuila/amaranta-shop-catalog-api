#!/usr/bin/env bash
# Python without installing Python: every command runs in the official image, so it behaves on your machine as it
# does in CI. Arguments are the command to run; the dependencies are installed first (cached in a Docker volume):
#
#   bash scripts/py.sh pytest                  # every test
#   bash scripts/py.sh pytest tests/domain -q  # only some
#
# PY_DOCKER_ARGS adds docker options, for example a network and the variables of the integration tests.
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1   # Git Bash on Windows must not rewrite the container paths below

# shellcheck disable=SC2086  # PY_DOCKER_ARGS is a list of options on purpose
exec docker run --rm \
  -v "$PWD:/src" -v amaranta-catalog-pip:/root/.cache/pip -w /src \
  -e PYTHONDONTWRITEBYTECODE=1 -e PIP_DISABLE_PIP_VERSION_CHECK=1 \
  ${PY_DOCKER_ARGS:-} \
  python:3.12-slim sh -c 'pip install -q -e ".[dev]" && exec "$@"' sh "$@"
