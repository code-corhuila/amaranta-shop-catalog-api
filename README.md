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

The service of the catalog domain: browse the products and reserve or release stock. The reservation is one atomic conditional update on one document, so the stock never goes negative.

## Depends on

`amaranta-shop-catalog-db` (the structure) on `amaranta-shop-infra-mongo` (the instance), and the public key of `amaranta-shop-security` to verify tokens.

## How to run

Nothing to run yet. Once the code lands: `python -m venv .venv`, install the dependencies, `pytest` for the tests, and start it with the variables of `.env.example`.

## Stack

Python 3.12 or later, hexagonal ([ADR-012](https://github.com/code-corhuila/amaranta-shop-docs/blob/main/05-architecture/decisions/records/ADR-012-stack-of-extracted-services.md)). The teacher has no Python template, so it mirrors the layout of the Java one: a core with no framework imports, adapters and one composition root. The web framework is chosen in the service's plan.

## Status

**Skeleton.** Only the base of a code repository is here (norm 5.1); nothing in it runs yet, and this README says so
on purpose. Next pull request: `feat/product-domain`: the `Product` aggregate with reserve and release, tests first.
