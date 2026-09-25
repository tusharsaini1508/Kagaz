"""pytest only: tag customer isolation tests with the ``isolation`` marker.

CI runs ``pytest -m isolation`` first and on its own (ci.yml). Every test in a
module named ``test_isolation_*.py`` gets the marker, so an isolation test
cannot be forgotten. The tests themselves are plain unittest and do not import
pytest, so ``python -m unittest`` runs them too.

Changing what CI selects is Vrushit's call; this file needs his OK before any
pull request.
"""

from typing import Any


def pytest_configure(config: Any) -> None:
    config.addinivalue_line(
        "markers", "isolation: proves one customer cannot reach another customer's data"
    )


def pytest_collection_modifyitems(items: list[Any]) -> None:
    for item in items:
        module_name = item.module.__name__.rsplit(".", 1)[-1]
        if module_name.startswith("test_isolation_"):
            item.add_marker("isolation")
