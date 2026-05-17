"""Smoke tests for the Phase 0 scaffold.

These tests do not exercise any functionality. They exist to confirm that:
1. The Python environment is wired up.
2. pytest discovers and runs tests.
3. The core/ and demos/ packages are importable.
"""


def test_python_environment_works():
    assert 1 + 1 == 2


def test_core_package_importable():
    import core

    assert core is not None


def test_demos_package_importable():
    import demos

    assert demos is not None
