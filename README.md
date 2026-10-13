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

## How to build and test

You need only Docker.

```bash
bash scripts/py.sh pytest                          # every test
docker build -f deploy/Dockerfile -t catalog-api . # the container image
```

## Configuration

Every variable has a placeholder in `.env.example`; the real values never enter the repository.

| Variable | What it is |
|---|---|
| `PORT` | HTTP port, 8082 |
| `MONGODB_URI` | the database `catalog`, as `catalog_app` (never the administrator) |
| `JWT_PUBLIC_KEY` or `JWT_PUBLIC_KEY_FILE` | public key of `amaranta-shop-security` |

## Status

Skeleton: the packages exist, the architecture test guards the core, and the image builds. Next, each its own pull
request and each test-first: `feat/product-domain`, `feat/stock-use-cases`, `feat/mongo-product-repository`,
`feat/http-envelope-and-auth`, `feat/internal-stock-routes`, `feat/public-catalog-routes`, `feat/admin-product-routes`
and `feat/composition-root`.
