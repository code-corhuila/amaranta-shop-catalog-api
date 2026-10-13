#!/usr/bin/env bash
# The service as it will run: the container image, a real MongoDB built by catalog-db, and real HTTP. It is the demo of
# the catalog, end to end, with Docker only:
#
#   bash scripts/smoke-test.sh          # needs the catalog-db repository next to this one, or CATALOG_DB_DIR
#
# It proves that the image boots, that a visitor browses the ten seeded products without a token, that the admin routes
# are closed by role, that Sales' two internal endpoints take and give back stock in the real database, that a
# reservation of more than there is takes nothing, and the claim of ADR-010: 30 simultaneous requests for 5 units
# end with exactly 5 reservations and a stock of 0, never below.
set -euo pipefail
cd "$(dirname "$0")/.."
# Git Bash on Windows must not rewrite the container paths given to docker, but openssl (a Windows program) does need
# its own paths converted: so the switch is set for docker only.
docker() { MSYS_NO_PATHCONV=1 command docker "$@"; }

CATALOG_DB_DIR="$(cd "${CATALOG_DB_DIR:-../amaranta-shop-catalog-db}" 2> /dev/null && { pwd -W 2> /dev/null || pwd; })" \
  || { echo "catalog-db not found: clone it next to this repository or set CATALOG_DB_DIR" >&2; exit 1; }

ID=$$
NET="catalog-smoke-net-$ID"; DB="catalog-smoke-mongo-$ID"; API="catalog-smoke-api-$ID"
ADMIN=amaranta_admin
PW="$(openssl rand -hex 16)"; APP_PW="$(openssl rand -hex 16)"
WORK="$(mktemp -d)"
cleanup() { docker rm -f "$DB" "$API" > /dev/null 2>&1 || true; docker network rm "$NET" > /dev/null 2>&1 || true; rm -rf "$WORK"; }
trap cleanup EXIT
fail() { echo "FAIL: $*" >&2; docker logs --tail 20 "$API" >&2 || true; exit 1; }
step() { echo "== $*"; }

# ---- a signing key for the test: only its PUBLIC half goes to the service ------------------------------------
openssl genrsa -out "$WORK/private.pem" 2048 2> /dev/null
PUBLIC="$(openssl rsa -in "$WORK/private.pem" -pubout 2> /dev/null | awk '{printf "%s\\n", $0}')"
b64url() { openssl base64 -A | tr '+/' '-_' | tr -d '='; }
token() { # token <role>: a valid RS256 token, expiring in 2030
  local head body sig
  head="$(printf '{"alg":"RS256","typ":"JWT"}' | b64url)"
  body="$(printf '{"sub":"33333333-3333-4333-8333-333333333333","role":"%s","exp":1893456000}' "$1" | b64url)"
  sig="$(printf '%s.%s' "$head" "$body" | openssl dgst -sha256 -sign "$WORK/private.pem" | b64url)"
  echo "$head.$body.$sig"
}

# ---- the platform: database, structure, service --------------------------------------------------------------
step "database and structure (catalog-db)"
docker network create "$NET" > /dev/null
docker build -q -t catalog-db-liquibase:smoke -f "$CATALOG_DB_DIR/deploy/liquibase.Dockerfile" "$CATALOG_DB_DIR/deploy" > /dev/null
docker run -d --name "$DB" --network "$NET" --network-alias mongo -e MONGO_INITDB_ROOT_USERNAME="$ADMIN" \
  -e MONGO_INITDB_ROOT_PASSWORD="$PW" mongo:7.0 > /dev/null
until docker logs "$DB" 2>&1 | grep -q "MongoDB init process complete"; do sleep 1; done
mongo_admin() { docker exec -i "$DB" mongosh --quiet -u "$ADMIN" -p "$PW" --authenticationDatabase admin --eval "$1"; }
until mongo_admin "db.adminCommand('ping').ok" 2> /dev/null | grep -qx 1; do sleep 1; done
mongo_admin "db.getSiblingDB('catalog').createUser({ user: 'catalog_app', pwd: '$APP_PW', roles: [{ role: 'readWrite', db: 'catalog' }] })" > /dev/null
docker run --rm --network "$NET" -v "$CATALOG_DB_DIR:/workspace:ro" -e LIQUIBASE_COMMAND_USERNAME="$ADMIN" \
  -e LIQUIBASE_COMMAND_PASSWORD="$PW" --entrypoint liquibase catalog-db-liquibase:smoke \
  --search-path=/workspace --changelog-file=changelog/changelog-master.yaml \
  --database-changelog-table-name=databasechangelog_catalog --database-changelog-lock-table-name=databasechangeloglock_catalog \
  --url="mongodb://mongo:27017/catalog?authSource=admin" update 2>&1 | grep -E "^Run:|ERROR|rror:" || true

step "the service (the container image)"
docker build -q -f deploy/Dockerfile -t catalog-api:smoke . > /dev/null
docker run -d --name "$API" --network "$NET" --network-alias catalog-api \
  -e "MONGODB_URI=mongodb://catalog_app:$APP_PW@mongo:27017/catalog?authSource=catalog" -e "JWT_PUBLIC_KEY=$PUBLIC" \
  catalog-api:smoke > /dev/null

api() { docker run --rm --network "$NET" curlimages/curl:latest -s -w '\n%{http_code}' "$@"; }
code() { tail -1; }
for _ in $(seq 1 60); do api http://catalog-api:8082/health 2> /dev/null | code | grep -qx 200 && break; sleep 1; done
[ "$(api http://catalog-api:8082/health | code)" = "200" ] || fail "the service did not come up"
BASE=http://catalog-api:8082
stock_of() { mongo_admin "db.getSiblingDB('catalog').product.findOne({_id: '$1'}).stockQuantity.toString()"; }
FOOD=399d2ea8-1ccb-4193-8255-1b51e331984d   # FOOD-001 Croquetas Adulto Salmon 15kg: the id the monolith issued

step "1. a visitor browses the shop without a token: the ten seeded products"
out="$(api "$BASE/api/v1/products?limit=100")"
[ "$(echo "$out" | code)" = "200" ] || fail "the public list must be 200"
[ "$(echo "$out" | grep -o '"id"' | wc -l)" = "10" ] || fail "the list must hold the ten seeded products"

step "2. the admin routes are closed by role: 401, 403, then 200"
[ "$(api "$BASE/api/v1/admin/products" | code)" = "401" ] || fail "no token must be 401"
[ "$(api "$BASE/api/v1/admin/products" -H "Authorization: Bearer $(token CUSTOMER)" | code)" = "403" ] || fail "a customer must be 403"
[ "$(api "$BASE/api/v1/admin/products" -H "Authorization: Bearer $(token ADMIN)" | code)" = "200" ] || fail "an admin must be 200"

step "3. Sales reserves 2 units: the lines come back and the stock falls in the real database"
before="$(stock_of $FOOD)"
reserve() { api -X POST "$BASE/internal/products/reserve-stock" -H 'Content-Type: application/json' -d "{\"items\":[{\"productId\":\"$FOOD\",\"quantity\":$1}]}"; }
out="$(reserve 2)"
[ "$(echo "$out" | code)" = "200" ] && echo "$out" | grep -q '"unitPriceAmount":189000' || fail "reserve must answer the line with its price: $out"
[ "$(stock_of $FOOD)" = "$((before - 2))" ] || fail "the stock did not fall by 2"

step "4. more than there is: 422 INV-PRODUCT-002 and nothing is taken"
now="$(stock_of $FOOD)"
out="$(reserve 1000)"
[ "$(echo "$out" | code)" = "422" ] && echo "$out" | grep -q INV-PRODUCT-002 || fail "must be 422 INV-PRODUCT-002: $out"
[ "$(stock_of $FOOD)" = "$now" ] || fail "a rejected reservation changed the stock"

step "5. Sales gives the 2 units back: 204 and the stock is whole again"
[ "$(api -X POST "$BASE/internal/products/release-stock" -H 'Content-Type: application/json' \
  -d "{\"items\":[{\"productId\":\"$FOOD\",\"quantity\":2}]}" | code)" = "204" ] || fail "release must be 204"
[ "$(stock_of $FOOD)" = "$before" ] || fail "the stock is not whole again"

step "6. THE CLAIM OF ADR-010: 30 simultaneous requests for 5 units -> exactly 5 reservations, stock 0, never below"
curl_auth="Authorization: Bearer $(token ADMIN)"
api -X PATCH "$BASE/api/v1/admin/products/$FOOD/stock" -H "$curl_auth" -H 'Content-Type: application/json' -d '{"stockQuantity":5}' > /dev/null
wins="$(docker run --rm --network "$NET" curlimages/curl:latest sh -c "seq 30 | xargs -P 30 -I{} curl -s -o /dev/null -w '%{http_code}\n' -X POST $BASE/internal/products/reserve-stock -H 'Content-Type: application/json' -d '{\"items\":[{\"productId\":\"$FOOD\",\"quantity\":1}]}'" | grep -c '^200$')"
[ "$wins" = "5" ] || fail "exactly 5 of 30 must win, $wins did"
[ "$(stock_of $FOOD)" = "0" ] || fail "the stock must end at 0"

step "7. the admin creates a product, a duplicate sku is 422, and deleting is 204"
NEW='{"sku":"SMOKE-001","name":"Smoke toy","description":"d","category":"TOYS","price":7000,"stockQuantity":3,"imageUrl":"https://example.test/s.png"}'
create() { api -X POST "$BASE/api/v1/admin/products" -H "$curl_auth" -H 'Content-Type: application/json' -d "$NEW"; }
out="$(create)"
[ "$(echo "$out" | code)" = "201" ] || fail "create must be 201: $out"
new_id="$(echo "$out" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)"
[ "$(create | code)" = "422" ] || fail "a duplicate sku must be 422"
[ "$(api -X DELETE "$BASE/api/v1/admin/products/$new_id" -H "$curl_auth" | code)" = "204" ] || fail "delete must be 204"

echo "OK: image, real MongoDB, public and admin routes, Sales' endpoints and the race of ADR-010"
