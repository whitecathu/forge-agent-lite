"""Only --live executes an agent. Manifest checks are never task success rates."""

import argparse
import hashlib
import json
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from forge.runtime import Runtime, Settings
from forge.tools import Tools, git

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--max-calls", type=int, default=20, help="Per task, including planning")
    parser.add_argument("--output", default="artifacts/evaluation.json")
    args = parser.parse_args()
    config = Settings()
    if not 1 <= args.limit <= 12 or not 1 <= args.max_calls <= 20:
        parser.error("limit must be 1..12 and max-calls must be 1..20")
    raw = (ROOT / "evals/cases.json").read_bytes()
    cases = json.loads(raw)["cases"][: args.limit]
    for case in cases:
        fixture = ROOT / "evals" / case["fixture"]
        if (
            not (fixture / "repo/solution.py").is_file()
            or not (fixture / "acceptance/test_contract.py").is_file()
        ):
            parser.error("Missing self-contained fixture: " + case["id"])
    if not args.live:
        report = {
            "mode": "manifest_validation",
            "cases": len(cases),
            "task_success_rate": None,
            "note": "No model or task execution. This is a fixture completeness check.",
        }
    else:
        if not config.llm_api_key or not config.llm_model:
            parser.error("Configure LLM_API_KEY and LLM_MODEL before --live")
        config.demo_mode = False
        config.max_model_calls = args.max_calls
        batch = ROOT / ".data" / ("evaluation-" + str(time.time_ns()))
        config.data_dir = str(batch / "runtime")
        runtime = Runtime(config)
        results = []
        for case in cases:
            fixture = ROOT / "evals" / case["fixture"]
            repo = batch / "sources" / case["id"]
            shutil.copytree(fixture / "repo", repo)
            subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
            git(repo, "add", ".")
            git(
                repo,
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "commit",
                "-m",
                "fixture",
            )
            started = time.perf_counter()
            state = runtime.create(str(repo), case["task"])
            state = runtime.run(state["run_id"])
            if state["status"] == "awaiting_approval":
                state = runtime.run(state["run_id"], approve=True)
            acceptance = Tools(Path(state["workspace"]), config.runner_image, config.test_timeout).verify(
                fixture / "acceptance"
            )
            results.append(
                {
                    "id": case["id"],
                    "run_id": state["run_id"],
                    "status": state["status"],
                    "passed": state["status"] == "succeeded" and acceptance.status == "succeeded",
                    "acceptance": acceptance.model_dump(),
                    "verification": state["verification"],
                    "model_calls": state["calls"],
                    "repairs": state["repairs"],
                    "tokens": state["usage"],
                    "reason": state["reason"],
                    "latency_ms": round((time.perf_counter() - started) * 1000),
                }
            )
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True
        ).stdout.strip()
        report = {
            "mode": "live",
            "model": config.llm_model,
            "code_commit": commit,
            "dataset_sha256": hashlib.sha256(raw).hexdigest(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "task_success_rate": sum(r["passed"] for r in results) / len(results),
            "cases": len(results),
            "max_model_calls_per_task": args.max_calls,
            "results": results,
            "cost": None,
            "cost_note": "No pricing configured. Token usage is reported without inventing costs.",
        }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {"mode": report["mode"], "cases": report["cases"], "output": str(output)}, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()
