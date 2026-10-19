import json

from test_agent import msg

from forge.runtime import Runtime, Settings


def test_cancel_then_resume_preserves_journal(repo, tmp_path):
    settings = Settings(data_dir=str(tmp_path / "runs"), demo_mode=False, _env_file=None)
    runtime = Runtime(settings)
    state = runtime.create(str(repo), "Inspect only")
    run = state["run_id"]

    class CancelAfterCall:
        def __init__(self):
            self.count = 0

        def complete(self, messages, use_tools=True):
            self.count += 1
            if self.count == 1:
                return msg("Inspect first"), {}
            runtime.store.cancel(run)
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "list-once",
                        "type": "function",
                        "function": {"name": "list_files", "arguments": json.dumps({"path": "."})},
                    }
                ],
            }, {}

    runtime.model = CancelAfterCall()
    runtime.run(run)
    result = runtime.run(run, approve=True)
    assert result["status"] == "interrupted"
    assert result["phase"] == "tools"
    # Resume with a zero remaining budget: pending tool executes, the next model step stops.
    resumed = Runtime(settings)
    resumed.settings.max_model_calls = 2
    result = resumed.run(run, resume=True)
    assert result["reason"] == "model_call_budget_exhausted"
    events = resumed.store.events(run)
    assert sum(e["event"] == "tool" and e["data"]["id"] == "list-once" for e in events) == 1


def test_live_failure_does_not_fallback_to_demo(repo, tmp_path):
    runtime = Runtime(
        Settings(data_dir=str(tmp_path / "runs"), demo_mode=False, llm_api_key="", _env_file=None)
    )
    run = runtime.create(str(repo), "Inspect")["run_id"]
    result = runtime.run(run)
    assert result["status"] == "failed"
    assert result["reason"] == "ValueError"
    assert not any(e["event"] == "demo" for e in runtime.store.events(run))


def test_symlink_escape(repo, tmp_path):
    import os

    import pytest

    from forge.tools import Tools

    outside = tmp_path / "outside.txt"
    outside.write_text("private", encoding="utf-8")
    try:
        os.symlink(outside, repo / "linked.txt")
    except OSError:
        pytest.skip("OS does not grant symlink creation")
    assert Tools(repo).call("read_file", {"path": "linked.txt"}).status == "failed"
