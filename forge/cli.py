import json

import typer

from forge.runtime import Runtime, Settings

app = typer.Typer(help="Forge Agent Lite: plan, approve, inspect and verify local coding tasks")


def output(value):
    typer.echo(json.dumps(value, ensure_ascii=False, indent=2))


@app.command()
def run(repository: str, task: str, approve: bool = False):
    runtime = Runtime(Settings())
    state = runtime.create(repository, task)
    state = runtime.run(state["run_id"])
    if approve and state["status"] == "awaiting_approval":
        state = runtime.run(state["run_id"], approve=True)
    output(state)


@app.command()
def start(run_id: str):
    output(Runtime(Settings()).run(run_id, approve=True))


@app.command()
def resume(run_id: str):
    output(Runtime(Settings()).run(run_id, resume=True))


@app.command()
def cancel(run_id: str):
    Runtime(Settings()).store.cancel(run_id)
    output({"status": "cancellation_requested"})


@app.command()
def show(run_id: str):
    output(Runtime(Settings()).store.get(run_id))


@app.command()
def demo():
    """Create the original calculator example and print its repository path."""
    from pathlib import Path

    from forge.demo import prepare

    output({"repository": prepare(Path(Settings().data_dir))})


@app.command()
def serve(port: int = 8001):
    import uvicorn

    uvicorn.run("forge.api:app", host="127.0.0.1", port=port)


if __name__ == "__main__":
    app()
