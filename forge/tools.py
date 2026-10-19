"""Explicit tools, no arbitrary host shell. Repository code runs only in Docker."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Result(BaseModel):
    status: Literal["succeeded", "failed", "blocked"]
    summary: str
    data: dict = Field(default_factory=dict)


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = "."


class SearchArgs(Args):
    query: str = Field(min_length=1, max_length=200)


class PatchArgs(Args):
    expected_sha256: str = Field(description="SHA256 returned by read_file; use 'new' for a new file")
    content: str = Field(max_length=100000, description="Complete new UTF-8 file content")


class EmptyArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


SPECS = {
    "list_files": (Args, "List source files under a relative path"),
    "read_file": (Args, "Read UTF-8 file and SHA256 for an optimistic, checked edit"),
    "search_text": (SearchArgs, "Search literal text in source files"),
    "apply_patch": (PatchArgs, "Replace/create one file with SHA256 precondition; no host command execution"),
    "run_tests": (EmptyArgs, "Run repository pytest suite in an offline, resource-limited Docker container"),
    "git_diff": (EmptyArgs, "Show tracked diff and new text files"),
}


def schemas():
    return [
        {
            "type": "function",
            "function": {"name": name, "description": desc, "parameters": model.model_json_schema()},
        }
        for name, (model, desc) in SPECS.items()
    ]


def git(root: Path, *args: str, timeout=30):
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    result = subprocess.run(
        ["git", "-c", "core.hooksPath=", "-c", "core.fsmonitor=false", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
    )
    if result.returncode:
        raise ValueError(result.stderr[:1000])
    return result.stdout


class Tools:
    def __init__(self, workspace: Path, image="forge-runner:local", timeout=60):
        self.workspace = workspace.resolve()
        self.image, self.timeout = image, timeout

    def resolve(self, name: str) -> Path:
        path = (self.workspace / name).resolve()
        if not path.is_relative_to(self.workspace):
            raise ValueError("Path escapes the workspace")
        parts = path.relative_to(self.workspace).parts
        if any(
            p.lower() in {".git", ".env", ".venv", "node_modules", ".data"}
            or p.lower().startswith(".env.")
            or ":" in p
            or p.lower().endswith((".pem", ".key"))
            for p in parts
        ):
            raise ValueError("Protected path")
        # Do not allow symlink ancestors, even when their target happens to be in workspace.
        cursor = self.workspace / name
        while cursor != self.workspace and cursor.is_relative_to(self.workspace):
            if cursor.is_symlink() or (hasattr(cursor, "is_junction") and cursor.is_junction()):
                raise ValueError("Links are not tool-editable")
            cursor = cursor.parent
        return path

    def files(self, name="."):
        base = self.resolve(name)
        result = []
        for parent, dirs, files in os.walk(base, followlinks=False):
            dirs[:] = sorted(
                d
                for d in dirs
                if not d.startswith(".")
                and d not in {"node_modules", "__pycache__"}
                and not (Path(parent) / d).is_symlink()
            )
            for filename in sorted(files):
                candidate = Path(parent) / filename
                try:
                    self.resolve(str(candidate.relative_to(self.workspace)))
                except ValueError:
                    continue
                if candidate.stat().st_size <= 100000:
                    result.append(candidate)
                if len(result) >= 500:
                    return result
        return result

    def diff(self):
        changed = git(self.workspace, "diff", "--name-only", "-z", "HEAD").split("\0")
        allowed = []
        for name in filter(None, changed):
            try:
                self.resolve(name)
                allowed.append(name)
            except ValueError:
                continue
        diff = (
            git(self.workspace, "diff", "--no-ext-diff", "--no-textconv", "HEAD", "--", *allowed)
            if allowed
            else ""
        )
        new = git(self.workspace, "ls-files", "--others", "--exclude-standard", "-z").split("\0")
        for name in filter(None, new):
            try:
                path = self.resolve(name)
            except ValueError:
                continue
            if path.stat().st_size <= 100000:
                diff += f"\n--- /dev/null\n+++ b/{name}\n" + "\n".join(
                    "+" + line for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
                )
        return diff[:200000]

    def verify(self, acceptance: Path | None = None):
        # No Docker socket, no host env, read-only mounts, no shell interpolation.
        command = [
            "docker",
            "run",
            "--rm",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--memory=256m",
            "--cpus=1",
            "--pids-limit=64",
            "--user=65534:65534",
            "--tmpfs=/tmp:rw,nosuid,size=64m",
            "-e",
            "PYTHONDONTWRITEBYTECODE=1",
            "-e",
            "PYTHONPATH=/workspace",
            "--mount",
            f"type=bind,source={self.workspace},target=/workspace,readonly",
            "-w",
            "/workspace",
        ]
        if acceptance:
            command += ["--mount", f"type=bind,source={acceptance.resolve()},target=/acceptance,readonly"]
        command += ["--pull=never", self.image, "python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
        if acceptance:
            command += ["/acceptance", "--confcutdir=/acceptance", "-o", "addopts="]
        # A cid file allows timed-out containers to be killed rather than left running.
        import tempfile

        with tempfile.TemporaryDirectory() as temp:
            cidfile = Path(temp) / "cid"
            command[2:2] = ["--cidfile", str(cidfile)]
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=self.timeout,
                )
                code = result.returncode
                status = "succeeded" if code == 0 else ("blocked" if code == 125 else "failed")
                return Result(
                    status=status,
                    summary="pytest in Docker",
                    data={
                        "exit_code": code,
                        "output": (result.stdout + result.stderr)[-16000:],
                        "command": "python -m pytest -q -p no:cacheprovider",
                        "runner": "docker",
                    },
                )
            except FileNotFoundError:
                return Result(status="blocked", summary="Docker is not installed")
            except subprocess.TimeoutExpired:
                if cidfile.exists():
                    try:
                        subprocess.run(
                            ["docker", "rm", "-f", cidfile.read_text().strip()],
                            capture_output=True,
                            timeout=10,
                        )
                    except (OSError, subprocess.TimeoutExpired):
                        pass
                return Result(status="blocked", summary="Docker verification timed out")

    def call(self, name: str, raw: dict) -> Result:
        try:
            if name not in SPECS:
                return Result(status="blocked", summary="Unknown tool")
            args = SPECS[name][0].model_validate(raw)
            if name == "run_tests":
                return self.verify()
            if name == "git_diff":
                return Result(status="succeeded", summary="Diff", data={"diff": self.diff()})
            if name == "list_files":
                return Result(
                    status="succeeded",
                    summary="Files (max 500)",
                    data={"files": [str(p.relative_to(self.workspace)) for p in self.files(args.path)]},
                )
            if name == "search_text":
                matches = []
                for path in self.files(args.path):
                    for i, line in enumerate(
                        path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
                    ):
                        if args.query in line:
                            matches.append(
                                {"path": str(path.relative_to(self.workspace)), "line": i, "text": line[:300]}
                            )
                            if len(matches) >= 100:
                                break
                    if len(matches) >= 100:
                        break
                return Result(status="succeeded", summary="Matches (max 100)", data={"matches": matches})
            path = self.resolve(args.path)
            if name == "read_file":
                if path.stat().st_size > 100000:
                    raise ValueError("File exceeds 100 KB")
                data = path.read_bytes()
                return Result(
                    status="succeeded",
                    summary="File",
                    data={"content": data.decode("utf-8"), "sha256": hashlib.sha256(data).hexdigest()},
                )
            if name == "apply_patch":
                actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "new"
                if actual != args.expected_sha256:
                    return Result(status="blocked", summary="File changed; read it again before editing")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(args.content, encoding="utf-8", newline="\n")
                return Result(status="succeeded", summary="File updated", data={"path": args.path})
        except (ValueError, OSError) as exc:
            return Result(status="failed", summary=str(exc)[:500])
        return Result(status="failed", summary="Unhandled tool")


def serialize(result: Result):
    return json.dumps(result.model_dump(), ensure_ascii=False)
