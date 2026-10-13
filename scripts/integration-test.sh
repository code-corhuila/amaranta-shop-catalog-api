#!/usr/bin/env bash
# The integration tests against a real MongoDB 7 with the database of amaranta-shop-catalog-db. Needs only Docker and
# a checkout of the catalog-db repository next to this one (or CATALOG_DB_DIR pointing at it):
#
#   bash scripts/integration-test.sh            # or pass pytest arguments: bash scripts/integration-test.sh -k race
#
# It starts a throwaway MongoDB, creates catalog_app the way amaranta-shop-infra-mongo does, builds the collection, the
# validator, the indexes, the seed and the roles with the Liquibase of catalog-db, and runs the tests as catalog_app, the
# user the service really connects with. Without TEST_MONGODB_URI those tests are skipped, not failed (Annex C).
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1   # Git Bash on Windows must not rewrite the container paths below

# pwd -W gives the Windows path under Git Bash, which is what Docker Desktop mounts; elsewhere plain pwd.
CATALOG_DB_DIR="$(cd "${CATALOG_DB_DIR:-../amaranta-shop-catalog-db}" 2> /dev/null && { pwd -W 2> /dev/null || pwd; })" \
  || { echo "catalog-db not found: clone it next to this repository or set CATALOG_DB_DIR" >&2; exit 1; }
[ -f "$CATALOG_DB_DIR/changelog/changelog-master.yaml" ] || { echo "$CATALOG_DB_DIR is not the catalog-db repository" >&2; exit 1; }

NAME="catalog-api-it-$$"
NET="catalog-api-net-$$"
ADMIN=amaranta_admin
PW="$(openssl rand -hex 16)"       # a throwaway instance with throwaway passwords: nothing to version
APP_PW="$(openssl rand -hex 16)"

docker network create "$NET" > /dev/null
docker build -q -t catalog-db-liquibase:it -f "$CATALOG_DB_DIR/deploy/liquibase.Dockerfile" "$CATALOG_DB_DIR/deploy" > /dev/null
docker run -d --rm --name "$NAME" --network "$NET" --network-alias mongo \
  -e MONGO_INITDB_ROOT_USERNAME="$ADMIN" -e MONGO_INITDB_ROOT_PASSWORD="$PW" mongo:7.0 > /dev/null
trap 'docker rm -f "$NAME" > /dev/null 2>&1 || true; docker network rm "$NET" > /dev/null 2>&1 || true' EXIT
# The image starts a temporary server to run its init, then restarts: wait for the real one.
until docker logs "$NAME" 2>&1 | grep -q "MongoDB init process complete"; do sleep 1; done
mongo_admin() { docker exec -i "$NAME" mongosh --quiet -u "$ADMIN" -p "$PW" --authenticationDatabase admin "$@"; }
until mongo_admin --eval "db.adminCommand('ping').ok" 2> /dev/null | grep -qx 1; do sleep 1; done

# What amaranta-shop-infra-mongo does at the start of the instance: the login user of the domain.
mongo_admin --eval "db.getSiblingDB('catalog').createUser({ user: 'catalog_app', pwd: '$APP_PW', roles: [{ role: 'readWrite', db: 'catalog' }] })" > /dev/null

# What catalog-db does: the collection, its validator, its indexes, the seed and the roles.
docker run --rm --network "$NET" -v "$CATALOG_DB_DIR:/workspace:ro" \
  -e LIQUIBASE_COMMAND_USERNAME="$ADMIN" -e LIQUIBASE_COMMAND_PASSWORD="$PW" \
  --entrypoint liquibase catalog-db-liquibase:it \
  --search-path=/workspace --changelog-file=changelog/changelog-master.yaml \
  --database-changelog-table-name=databasechangelog_catalog \
  --database-changelog-lock-table-name=databasechangeloglock_catalog \
  --url="mongodb://mongo:27017/catalog?authSource=admin" update 2>&1 | grep -E "UPDATE SUMMARY|^Run:|ERROR|rror:" || true

PY_DOCKER_ARGS="--network $NET \
  -e TEST_MONGODB_URI=mongodb://catalog_app:$APP_PW@mongo:27017/catalog?authSource=catalog \
  -e TEST_MONGODB_ADMIN_URI=mongodb://$ADMIN:$PW@mongo:27017/catalog?authSource=admin" \
  bash scripts/py.sh pytest "$@"
