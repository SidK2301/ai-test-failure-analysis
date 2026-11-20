"""Run the development benchmark against a pinned local Ollama model."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from model_client import ROOT, SCHEMA, run_dev
from workflow import regrade, write_json

BASE_URL = "http://127.0.0.1:11434"
CONTEXT = 4096
MAX_TOKENS = 512
SEED = 42701
LOCAL_SCHEMA = SCHEMA.copy()
# Generate evidence before committing to a diagnosis or category.
LOCAL_SCHEMA["properties"] = {
    key: SCHEMA["properties"][key] for key in ("evidence", "status", "root_cause")
}
LOCAL_SCHEMA["required"] = list(LOCAL_SCHEMA["properties"])


class Ollama:
    def __init__(self, model, prompt, *, num_ctx=CONTEXT, max_tokens=MAX_TOKENS, seed=SEED):
        self.model = model
        self.prompt = prompt
        self.options = {
            "num_ctx": num_ctx, "num_predict": max_tokens,
            "temperature": 0, "seed": seed,
        }
        self.opener = build_opener(ProxyHandler({}))

    def request(self, path, payload=None):
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
        request = Request(BASE_URL + path, data, {"Content-Type": "application/json"})
        with self.opener.open(request, timeout=180) as response:
            return json.load(response)

    def identity(self):
        models = self.request("/api/tags")["models"]
        model = next(
            (entry for entry in models if entry["name"] == self.model and not entry.get("remote_host")),
            None,
        )
        if not model or not model.get("digest"):
            raise ValueError(f"Model {self.model} must be installed locally and have a digest")
        return {
            "model": self.model, "model_digest": model["digest"],
            "model_details": model["details"],
            "ollama_version": self.request("/api/version")["version"],
        }

    def __call__(self, visible):
        payload = {
            "model": self.model, "stream": False, "format": LOCAL_SCHEMA,
            "think": False, "truncate": False, "shift": False,
            "options": self.options,
            "messages": [
                {"role": "system", "content": self.prompt},
                {"role": "user", "content": json.dumps(visible, ensure_ascii=False)},
            ],
        }
        start = monotonic()
        attempt = {"requests": 1, "cost_usd": "0", "request_payload": payload}
        try:
            body = self.request("/api/chat", payload)
            attempt["raw_api_response"] = body
            attempt["raw_response"] = body["message"]["content"]
            attempt["input_tokens"] = body.get("prompt_eval_count")
            attempt["output_tokens"] = body.get("eval_count")
            if body.get("remote_host"):
                attempt["request_error"] = "Unexpected remote backend"
            elif body.get("done_reason") != "stop" or not body.get("done"):
                attempt["request_error"] = f"Unexpected stop reason: {body.get('done_reason')}"
            else:
                input_tokens = attempt["input_tokens"]
                if type(input_tokens) is not int or not 0 < input_tokens <= (
                    self.options["num_ctx"] - self.options["num_predict"]
                ):
                    attempt["request_error"] = "Prompt token count missing or exceeds reserved context"
        except HTTPError as error:
            with error:
                try:
                    attempt["request_error"] = f"HTTP {error.code}: {json.load(error)['error']}"
                except (ValueError, KeyError, TypeError):
                    attempt["request_error"] = f"HTTP {error.code}"
        except (URLError, OSError, ValueError, KeyError, TypeError) as error:
            attempt["request_error"] = type(error).__name__
        attempt["latency_ms"] = round((monotonic() - start) * 1000, 3)
        return attempt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--model", required=True, help="Exact local model tag")
    parser.add_argument("--digest", required=True, help="Expected local model digest")
    parser.add_argument("--ollama-version", required=True, help="Expected local Ollama version")
    args = parser.parse_args()
    prompt = (ROOT / "prompt.txt").read_bytes()
    client = Ollama(args.model, prompt.decode())
    identity = client.identity()
    if identity["model_digest"] != args.digest or identity["ollama_version"] != args.ollama_version:
        parser.error("Local model digest or Ollama version differs from the expected value")
    metadata = {
        **identity, **client.options, "backend": "ollama", "split": "dev",
        "max_tokens": client.options["num_predict"],
        "prompt_sha256": hashlib.sha256(prompt).hexdigest(),
        "git_hash": subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
        "git_status": subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain"], text=True),
    }
    args.output.mkdir(parents=True, exist_ok=False)
    artifact = run_dev(ROOT / "benchmark", client, metadata)
    (args.output / "run.json").write_bytes(write_json(artifact))
    if client.identity() != identity:
        raise RuntimeError("The local model or server changed during the run")
    scores = regrade(artifact)
    (args.output / "scores.json").write_bytes(write_json(scores))
    print(write_json(scores["overall"]).decode(), end="")


if __name__ == "__main__":
    main()
