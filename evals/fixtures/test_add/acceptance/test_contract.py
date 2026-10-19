from pathlib import Path

from solution import add


def test_contract():
    assert add(2, 3) == 5
    tests = Path("/workspace/test_solution.py").read_text()
    assert "assert" in tests and "add(" in tests
