"""Original sample repository: a small broken calculator, created only on explicit request."""

import subprocess
from pathlib import Path

from forge.tools import git


def prepare(root: Path) -> str:
    repo = root.resolve() / "demo-repository"
    if not (repo / ".git").exists():
        repo.mkdir(parents=True, exist_ok=True)
        (repo / "README.md").write_text(
            "# Demo calculator\n\nFix add(a, b) and add regression tests.\n", encoding="utf-8"
        )
        (repo / "calculator.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
        (repo / "test_calculator.py").write_text(
            "from calculator import add\n\ndef test_add():\n    assert add(2, 3) == 5\n", encoding="utf-8"
        )
        subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
        git(repo, "add", ".")
        git(
            repo,
            "-c",
            "user.name=Forge Demo",
            "-c",
            "user.email=demo@example.invalid",
            "commit",
            "-m",
            "Initial demo fixture",
        )
    return str(repo)
