"""The dependency rule, as a test (norm 5.3.3, Annex C).

In Java the core is a module that cannot import Spring, so the rule is a compile error. Python has no such wall, so
this test builds it: the domain and the application import only the standard library and each other. The adapters
and the composition root are the only places where FastAPI, pymongo or PyJWT may appear.
"""

import ast
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "catalog"
CORE = [SRC / "domain", SRC / "application"]
ALLOWED_PREFIXES = ("catalog",)


def imported_modules(path: Path) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.append(node.module)
    return modules


def core_files() -> list[Path]:
    return [p for root in CORE for p in root.rglob("*.py")]


def test_the_core_imports_only_the_standard_library_and_itself():
    offenders = {}
    for path in core_files():
        bad = [m for m in imported_modules(path)
               if m.split(".")[0] not in sys.stdlib_module_names and not m.startswith(ALLOWED_PREFIXES)]
        if bad:
            offenders[str(path.relative_to(SRC))] = bad
    assert offenders == {}, f"the core imports a framework or a driver: {offenders}"


def test_the_core_never_imports_an_adapter():
    offenders = {str(p.relative_to(SRC)): m for p in core_files() for m in imported_modules(p) if m.startswith("catalog.adapter")}
    assert offenders == {}, f"the core depends on an adapter: {offenders}"


def test_the_architecture_test_can_see_the_core():
    assert core_files(), "no core files found: the paths of this test are wrong, so it would pass for nothing"
