import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from forge.api import create_app
from forge.runtime import Runtime, Settings, Store
from forge.tools import Result, Tools


def test_boundary_and_optimistic_edit(repo):
    tools = Tools(repo)
    assert tools.call("read_file", {"path": "../secret"}).status == "failed"
    assert tools.call("read_file", {"path": ".git/config"}).status == "failed"
    assert tools.call("read_file", {"path": ".env"}).status == "failed"
    assert tools.call("shell", {"command": "git push"}).status == "blocked"
    result = tools.call("read_file", {"path": "hello.py"})
    args = {"path": "hello.py", "expected_sha256": result.data["sha256"], "content": "fixed"}
    assert tools.call("apply_patch", args).status == "succeeded"
    assert tools.call("apply_patch", args).status == "blocked"


def test_journal_replay(tmp_path):
    store = Store(tmp_path)
    count = []

    def action():
        count.append(1)
        return Result(status="succeeded", summary="done")

    assert store.once("run", "call", action).status == "succeeded"
    assert store.once("run", "call", action).status == "succeeded"
    assert len(count) == 1
    with store.connect() as db:
        db.execute("INSERT INTO journal VALUES('run','uncertain','started','')")
    assert store.once("run", "uncertain", action).status == "blocked"
    assert len(count) == 1


def test_demo_plan_and_approval(repo, tmp_path):
    runtime = Runtime(Settings(data_dir=str(tmp_path / "data"), _env_file=None))
    state = runtime.create(str(repo), "Fix addition")
    assert runtime.run(state["run_id"])["status"] == "awaiting_approval"
    assert runtime.run(state["run_id"])["status"] == "awaiting_approval"
    result = runtime.run(state["run_id"], approve=True)
    assert result["status"] == "demo_complete"
    assert result["verification"] == {}
    assert "return a - b" in (repo / "hello.py").read_text()


class Scripted:
    def __init__(self, messages):
        self.messages = iter(messages)

    def complete(self, messages, use_tools=True):
        return next(self.messages), {"prompt_tokens": 10, "completion_tokens": 5}


def msg(text):
    return {"role": "assistant", "content": text}


def test_scripted_edit_and_real_verifier_contract(repo, tmp_path, monkeypatch):
    original = (repo / "hello.py").read_bytes()
    call = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "edit",
                "type": "function",
                "function": {
                    "name": "apply_patch",
                    "arguments": json.dumps(
                        {
                            "path": "hello.py",
                            "expected_sha256": hashlib.sha256(original).hexdigest(),
                            "content": "def add(a,b):\n    return a+b\n",
                        }
                    ),
                },
            }
        ],
    }
    model = Scripted([msg("Inspect and fix"), call, msg("Implementation updated")])
    monkeypatch.setattr(
        Tools, "verify", lambda self: Result(status="succeeded", summary="test double", data={"exit_code": 0})
    )
    runtime = Runtime(Settings(data_dir=str(tmp_path / "data"), demo_mode=False, _env_file=None), model)
    run = runtime.create(str(repo), "Fix addition")["run_id"]
    runtime.run(run)
    result = runtime.run(run, approve=True)
    assert result["status"] == "succeeded"
    assert "return a+b" in result["diff"]
    assert (repo / "hello.py").read_bytes() == original
    assert result["usage"]["prompt_tokens"] == 30


@pytest.mark.parametrize("verification,expected", [("failed", "failed"), ("blocked", "blocked")])
def test_verification_failure_never_success(repo, tmp_path, monkeypatch, verification, expected):
    monkeypatch.setattr(Tools, "verify", lambda self: Result(status=verification, summary="test double"))
    model = Scripted([msg("plan"), msg("done"), msg("repair"), msg("repair again")])
    runtime = Runtime(Settings(data_dir=str(tmp_path / "data"), demo_mode=False, _env_file=None), model)
    run = runtime.create(str(repo), "Fix")["run_id"]
    runtime.run(run)
    assert runtime.run(run, approve=True)["status"] == expected


def test_budget(repo, tmp_path):
    runtime = Runtime(
        Settings(data_dir=str(tmp_path / "data"), demo_mode=False, max_model_calls=1, _env_file=None),
        Scripted([msg("plan")]),
    )
    run = runtime.create(str(repo), "Fix")["run_id"]
    runtime.run(run)
    assert runtime.run(run, approve=True)["reason"] == "model_call_budget_exhausted"


def test_api_and_cross_origin(repo, tmp_path):
    with TestClient(create_app(Settings(data_dir=str(tmp_path / "data"), _env_file=None))) as client:
        assert (
            client.post("/api/runs", headers={"Origin": "https://evil.invalid"}, json={}).status_code == 403
        )
        result = client.post("/api/runs", json={"repository": str(repo), "task": "Inspect"})
        run = result.json()["run_id"]
        assert client.get(f"/api/runs/{run}").json()["status"] == "awaiting_approval"
        assert client.post(f"/api/runs/{run}/start").status_code == 200
        assert client.get(f"/api/runs/{run}").json()["status"] == "demo_complete"
        assert "data:" in client.get(f"/api/runs/{run}/events").text
        assert client.get(f"/api/runs/{run}/artifacts").json()["verification"] == {}
