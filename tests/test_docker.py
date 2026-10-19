import os

import pytest

from forge.tools import Tools

pytestmark = pytest.mark.skipif(
    os.environ.get("FORGE_DOCKER_TESTS") != "1", reason="Explicit Docker integration opt-in required"
)


def test_real_container_verifies_and_preserves_files(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "test_example.py").write_text("def test_sum():\n    assert 2 + 3 == 5\n", encoding="utf-8")
    tools = Tools(source, timeout=60)
    result = tools.verify()
    assert result.status == "succeeded", result.model_dump()
    assert result.data["exit_code"] == 0
    (source / "test_example.py").write_text("def test_sum():\n    assert 2 + 3 == 6\n", encoding="utf-8")
    assert tools.verify().status == "failed"


def test_external_acceptance_is_separate(tmp_path):
    source = tmp_path / "source"
    acceptance = tmp_path / "acceptance"
    source.mkdir()
    acceptance.mkdir()
    (source / "solution.py").write_text("def add(a,b):\n    return a+b\n", encoding="utf-8")
    (acceptance / "test_contract.py").write_text(
        "from solution import add\n\ndef test_add():\n    assert add(2,3)==5\n", encoding="utf-8"
    )
    result = Tools(source).verify(acceptance)
    assert result.status == "succeeded", result.model_dump()
