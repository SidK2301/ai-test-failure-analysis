"""Run the Phase 3 benchmark once against the Phase 2 freeze."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

import ollama_client
import workflow
from workflow import grade, parse_report, regrade, write_json


class FrozenOllama(ollama_client.Ollama):
    def __init__(self, model, prompt, *, request_settings, **options):
        super().__init__(model, prompt, **options)
        self.request_settings = request_settings

    def request(self, path, payload=None):
        if path == "/api/chat" and any(
            payload.get(key) != value for key, value in self.request_settings.items()
        ):
            raise RuntimeError("Blocked an Ollama request that differed from the freeze")
        return super().request(path, payload)


def read_json(path):
    return json.loads(path.read_bytes())


def run(root, output):
    for module in (ollama_client, workflow):
        if Path(module.__file__).resolve().parent != root.resolve():
            raise RuntimeError(f"Loaded {module.__name__} outside the frozen repository")
    ref = "phase-2-freeze^{}"
    commit = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", ref], text=True
    ).strip()
    freeze = json.loads(subprocess.check_output(
        ["git", "-C", str(root), "show", f"{commit}:benchmark/phase2/frozen.json"]
    ))
    for name, digest in freeze["sha256"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Frozen input changed: {name}")

    manifest = read_json(root / "benchmark/manifest.json")
    labels = read_json(root / "benchmark/labels.json")
    pattern = freeze["heuristic_pattern"]
    prepared = []
    for item in manifest["cases"]:
        if item["split"] != "held_out":
            continue
        visible, = parse_report((root / "benchmark" / item["report"]).read_bytes())
        case = {"visible": visible, "label": labels[item["id"]], "attempt": {}}
        grade(case, pattern)
        prepared.append((item["id"], case))
    if len(prepared) != 25 or len({case_id for case_id, _ in prepared}) != 25:
        raise ValueError("Expected exactly 25 unique held-out cases")

    config = freeze["run_configuration"]
    prompt = (root / "prompt.txt").read_text(encoding="utf-8")
    client = FrozenOllama(
        config["model"], prompt, num_ctx=config["num_ctx"], max_tokens=config["max_tokens"],
        seed=config["seed"], request_settings=freeze["request_settings"],
    )
    identity = client.identity()
    if any(identity[key] != config[key] for key in identity):
        raise ValueError("The running Ollama model or server differs from the freeze")
    if client.options != freeze["request_settings"]["options"]:
        raise ValueError("Ollama options differ from the freeze")

    output.mkdir(parents=True, exist_ok=False)
    cases = []
    with (output / "attempts.jsonl").open("x", encoding="utf-8") as checkpoint:
        for case_id, case in prepared:
            attempt = client(case["visible"])
            case["attempt"] = attempt
            case["visible"] = {**case["visible"], "id": case_id}
            cases.append(case)
            checkpoint.write(json.dumps(case, sort_keys=True, ensure_ascii=False) + "\n")
            checkpoint.flush()
            os.fsync(checkpoint.fileno())
            print(f"{len(cases)}/{len(prepared)} {case_id} {grade(case, pattern)['outcome']}", flush=True)

    artifact = {
        "version": 1, "heuristic_pattern": pattern, "cases": cases,
        "metadata": {
            **config, "split": "held_out", "git_hash": commit, "freeze_tag": freeze["tag"],
            "request_settings": freeze["request_settings"],
            "server_environment_requested": freeze["server_environment"],
        },
    }
    (output / "run.json").write_bytes(write_json(artifact))
    if client.identity() != identity:
        raise RuntimeError("The local model or server changed during the run")
    (output / "scores.json").write_bytes(write_json(regrade(artifact)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New directory for the single held-out run")
    args = parser.parse_args()
    run(Path.cwd(), args.output)
