# amaranta-shop-catalog-api

> catalog bounded context: service API

Part of the **Amaranta Shop** distributed system — team `amaranta-shop`, Grupo 2.
Governance and documentation live in [`amaranta-shop-docs`](https://github.com/code-corhuila/amaranta-shop-docs).

## Branching

Three permanent branches. **None of them accepts a direct commit** — you enter through a child
branch and leave through a Pull Request.

```
develop  <--PR--  feat/... fix/... chore/...
qa       <--PR--  qa/...
main     <--PR--  release/...  hotfix/...
```

Promotion happens **by re-application** (`git cherry-pick -x`), never by merging one permanent
branch into another: `merge develop -> qa` and `merge qa -> main` do not exist in this model.

`main` requires **1 approval from `ariel5253`**. On `develop` and `qa` the team sets its own review
rule.

Full policy: `00-governance/branching-policy.md` in `amaranta-shop-docs`.

## Role in the system

The service of the **catalog** domain: browse the products, administer them, and reserve or release stock for Sales.
It owns the *data* of the `catalog` database and never its structure: collections, validator and indexes come from
`amaranta-shop-catalog-db`, and this service never creates one (norm 5.2.1). It is the second service extracted from
the monolith ([spec](https://github.com/code-corhuila/amaranta-shop-docs/blob/main/specs/checkout.md), DP-8).

## Depends on

- `amaranta-shop-catalog-db` on `amaranta-shop-infra-mongo`: the structure, and `catalog_app`, the only user it connects
  with (Annex J, J.4). Its validator is the last defence of the stock: it refuses a stock below zero.
- `amaranta-shop-security`: only its **public** key, to verify tokens. No service holds the private one.
- Nobody else. Catalog calls no other service.

## Stack

Python 3.12, FastAPI and pymongo, hexagonal, from the layout of the teacher's Java template (he has no Python one)
([ADR-012](https://github.com/code-corhuila/amaranta-shop-docs/blob/main/05-architecture/decisions/records/ADR-012-stack-of-extracted-services.md)).
Built with **TDD**: every rule has a named test, written before the code that makes it pass. Built on **DDD**: the
domain is the Product aggregate. Specified first (**SDD**): the spec says what must be true, this repository proves it.

## Layout and the rule that matters

```
src/catalog/domain/            the Product aggregate and its typed errors. Imports only the standard library
src/catalog/application/       ports (inbound: what is offered; outbound: what is needed) and the use cases
src/catalog/adapter/inbound/   HTTP: authentication, validation, the error envelope, correlation, routes
src/catalog/adapter/outbound/  MongoDB: the product repository
apps/api/                      the composition root: the only place that knows every concrete type and every limit
deploy/                        Dockerfile and compose.yml of this service only
scripts/py.sh                  Python in Docker, so nothing is installed and the build is the same everywhere
tests/                         unit, HTTP and integration tests
```

The dependency arrows point **towards the domain**. Java makes that a compile error; Python does not, so
`tests/test_architecture.py` makes it a test: the domain and the application may import only the standard library and
each other, and the build fails if FastAPI, pymongo or PyJWT appears there. The domain raises typed errors and does not
know what a `422` is: the status is decided in one place in the HTTP adapter.

## The contract

Public paths go through the gateway as `/api/v1/products*`, before and after the move out of the monolith. Every error is
`{error, message, details?, traceId}` and the status is decided in one place (`errors.py`).

| Route | Who | Answers |
|---|---|---|
| `GET /api/v1/products?page=&limit=` | **nobody needs a token** (buying needs no account, so neither does browsing) | `{data, meta}`, the active products sorted by name, `limit` 1-100 (20 by default); a product out of stock is listed with `inStock: false`; `400` naming `page` or `limit` |
| `GET /api/v1/products/{id}` | nobody | the product; `404` if it does not exist or is inactive; `400` for a malformed id |
| `GET /api/v1/admin/products` | `ADMIN` | the same list with the inactive products too |
| `POST /api/v1/admin/products` | `ADMIN` | `201` + `Location`; `400` one entry per invalid field; `422 SKU_ALREADY_EXISTS` |
| `PATCH /api/v1/admin/products/{id}` | `ADMIN` | only the fields given; `400` if none |
| `PATCH /api/v1/admin/products/{id}/stock` | `ADMIN` | the stock set exactly (0 or more) |
| `POST /api/v1/admin/products/{id}/activate` and `/deactivate` | `ADMIN` | the product |
| `DELETE /api/v1/admin/products/{id}` | `ADMIN` | `204`. Safe: an order keeps its own copy of the name and the price |
| `POST /internal/products/reserve-stock` | **internal only** | `{items:[{productId, quantity}]}` -> `{lines:[{productId, productName, unitPriceAmount, quantity}]}`; `422` naming `PRODUCT_NOT_FOUND` or `INV-PRODUCT-002`; takes every line or none |
| `POST /internal/products/release-stock` | **internal only** | `204`; a product that no longer exists is skipped |
| `GET /health` | nobody | `200`, no token |

The `/internal` routes ask for no token because **the gateway never publishes them**: only the services on the platform
network can reach them (spec OD-3). Each service validates the token itself, with RS256 only; the gateway only checks that
one exists, and lets the public routes through for the same reason `POST /orders` is let through.

## How to build, test and run

You need only Docker. Nothing is installed: Python, MongoDB and Liquibase all run in containers.

```bash
bash scripts/py.sh pytest               # every test; the 15 that need the database are skipped, not failed
bash scripts/integration-test.sh        # the repository against a real MongoDB, as catalog_app
bash scripts/smoke-test.sh              # the container, a real MongoDB and real HTTP
docker build -f deploy/Dockerfile -t catalog-api .    # the container image
```

The last two need the `amaranta-shop-catalog-db` repository next to this one (or `CATALOG_DB_DIR`): they build the real
database with its Liquibase. The smoke test is the demo of the catalog in one command, and it proves the claim of ADR-010:
**30 simultaneous requests for 5 units end with exactly 5 reservations and a stock of 0, never below.** In CI those run when
the repository variable `CATALOG_DB_CHECKOUT` is `true`.

## Configuration

Every variable has a placeholder in `.env.example`; the real values never enter the repository.

| Variable | What it is |
|---|---|
| `PORT` | HTTP port, 8082 |
| `MONGODB_URI` | the database `catalog`, as `catalog_app`. Required: the service refuses to start without it |
| `JWT_PUBLIC_KEY` or `JWT_PUBLIC_KEY_FILE` | public key of `amaranta-shop-security`. Required |
| `MONGO_POOL_MAX`, `MONGO_SERVER_SELECTION_MS`, `MONGO_CONNECT_MS`, `MONGO_SOCKET_MS` | the limits of the pool and the timeouts (10, 3 s, 2 s, 5 s) |
| `KEEP_ALIVE_SECONDS`, `GRACEFUL_SHUTDOWN_SECONDS` | 60 and 20 |

## The rules and the tests that prove them

Each rule is a named test, written before the code (TDD). A rule without a test is an intention, not a rule.

| Rule | What it says | Test |
|---|---|---|
| INV-PRODUCT-002 | the stock never goes below zero | `test_product.py` (the aggregate), the validator of `catalog-db` (the last defence) |
| INV-PRODUCT-004 to 010 | sku, name, stock, price, description, image and category limits | `test_product.py` |
| RN-08 | stock is reserved and released only here, all or nothing | `test_stock_use_cases.py` |
| RN-09 | a reservation that cannot be completed gives back what it took | `test_losing_the_race_for_a_later_line_gives_the_earlier_lines_back` (mutation-checked) |
| CA-C3.6 | two requests for the last unit: exactly one wins | `test_many_requests_for_the_last_units_never_take_more_than_there_are` (20 threads, real MongoDB) and step 6 of the smoke test (30 HTTP requests) |
| ADR-010 | money and stock are written as `long` | `test_taking_units_decrements_in_one_write_and_keeps_the_type_long` |
| ADR-010 | reservation is one conditional write, no transaction | `MongoProductRepository.try_decrement_stock` and the race tests above |
| Annex C | authentication: no token, wrong algorithm, expired, forged | `test_authentication.py`, `test_service_as_a_whole.py` |
| Annex C | one error envelope, correlation id, unknown route, malformed JSON | `test_error_envelope.py` |
| Annex C | bounded list, `400` naming the field | `test_public_catalog_routes.py`, `test_admin_product_routes.py` |
| Annex J | `catalog_app` cannot create a collection or reach another database | `test_the_service_user_cannot_create_a_collection_or_read_another_database` |
| norm 5.3.3 | the core imports no framework and no driver | `test_architecture.py` |

## Decisions and residues, declared

- **The list contract changes** from the monolith's `{items, page, pageSize, total}` to the course's `{data, meta}` with
  `limit`, as the Sales list did (spec HU-X3): `apps/web` must read `data` and `meta.total` and ask for `limit`. The fields of a
  product are the monolith's.
- **The image upload of the monolith is not in this cut**: an image is a URL. Storing files is a decision of its own (a bucket,
  or a volume) and not part of the catalog's data.
- **Mongo is a single node, no replica set**: nothing here needs a multi-document transaction (ADR-010).
- **Python must send `long`**: the validator of `catalog-db` refuses an int32, so every write goes through `bson.Int64`.
- **The interactive API docs are off**: a service of the platform exposes its contract, not a way to try it.

## Status

Complete for the catalog: domain, use cases, HTTP, MongoDB, the composition root and the container, with the end-to-end
demo. Next in the system: `amaranta-shop-api-gateway` routes `/api/v1/products*` here (public) and keeps `/internal` out; the
contract suite of the spec (section 8.5) runs against `sales-api` and this service together.
