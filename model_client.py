"""Anthropic Messages client and development-only benchmark runner."""

import argparse
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import subprocess
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from workflow import CATEGORIES, ERROR_PATTERN, capture, regrade, write_json

URL = "https://api.anthropic.com/v1/messages"
ROOT = Path(__file__).resolve().parent
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["root_cause", "evidence", "status"],
    "properties": {
        "root_cause": {
            "anyOf": [
                {"type": "null"},
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["category", "explanation"],
                    "properties": {
                        "category": {"type": "string", "enum": sorted(CATEGORIES)},
                        "explanation": {"type": "string"},
                    },
                },
            ],
        },
        "evidence": {"type": "array", "items": {"type": "integer"}},
        "status": {"type": "string", "enum": ["diagnosed", "insufficient_evidence"]},
    },
}


class Claude:
    def __init__(self, key, model, prompt, *, max_tokens=512, prices=None):
        self.key = key
        self.model = model
        self.prompt = prompt
        self.max_tokens = max_tokens
        self.prices = prices

    def __call__(self, visible):
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": self.prompt,
            "messages": [{"role": "user", "content": json.dumps(visible, ensure_ascii=False)}],
            "output_config": {"format": {"type": "json_schema", "schema": SCHEMA}},
        }
        request = Request(URL, json.dumps(payload).encode(), headers={
            "x-api-key": self.key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }, method="POST")
        start = monotonic()
        attempt = {"requests": 1}
        try:
            with urlopen(request, timeout=60) as response:
                body = json.load(response)
            attempt["raw_api_response"] = body
            attempt["raw_response"] = "".join(
                block["text"] for block in body["content"] if block.get("type") == "text"
            )
            attempt["returned_model"] = body.get("model")
            usage = body.get("usage", {})
            attempt["input_tokens"] = usage.get("input_tokens")
            attempt["output_tokens"] = usage.get("output_tokens")
            if self.prices and all(usage.get(key) is not None for key in ("input_tokens", "output_tokens")):
                input_price, output_price = self.prices
                cost = (input_price * usage["input_tokens"] + output_price * usage["output_tokens"]) / 1_000_000
                attempt["cost_usd"] = str(cost)
            if body.get("stop_reason") != "end_turn":
                attempt["request_error"] = f"Unexpected stop reason: {body.get('stop_reason')}"
        except HTTPError as error:
            attempt["request_error"] = f"HTTP {error.code}"
            error.close()
        except (URLError, OSError, ValueError, KeyError, TypeError) as error:
            attempt["request_error"] = type(error).__name__
        attempt["latency_ms"] = round((monotonic() - start) * 1000, 3)
        return attempt


def run_dev(benchmark, respond, metadata):
    manifest = json.loads((benchmark / "manifest.json").read_bytes())
    labels = json.loads((benchmark / "labels.json").read_bytes())
    records = []
    for item in manifest["cases"]:
        if item["split"] != "dev":
            continue
        xml = (benchmark / item["report"]).read_bytes()
        artifact = capture(xml, {"test-1": labels[item["id"]]}, respond)
        record, = artifact["cases"]
        record["visible"]["id"] = item["id"]
        records.append(record)
    if not records:
        raise ValueError("The manifest has no development cases")
    return {"version": 1, "metadata": metadata, "heuristic_pattern": ERROR_PATTERN, "cases": records}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New output directory")
    parser.add_argument("--benchmark", type=Path, default=ROOT / "benchmark")
    parser.add_argument("--model", default=os.environ.get("CLAUDE_MODEL"))
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--price-per-million", nargs=2, type=Decimal, metavar=("INPUT", "OUTPUT"))
    args = parser.parse_args()

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key or not args.model:
        parser.error("Set ANTHROPIC_API_KEY and pass --model or set CLAUDE_MODEL")
    if args.max_tokens < 1:
        parser.error("--max-tokens must be positive")
    if args.price_per_million and any(not price.is_finite() or price < 0 for price in args.price_per_million):
        parser.error("Token prices must be finite and nonnegative")
    prompt = (ROOT / "prompt.txt").read_bytes()
    metadata = {
        "split": "dev", "model": args.model, "temperature": None, "max_tokens": args.max_tokens,
        "prompt_sha256": hashlib.sha256(prompt).hexdigest(),
        "git_hash": subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
        "git_status": subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain"], text=True),
        "price_per_million_usd": [str(price) for price in args.price_per_million] if args.price_per_million else None,
    }
    args.output.mkdir(parents=True, exist_ok=False)
    client = Claude(key, args.model, prompt.decode(), max_tokens=args.max_tokens, prices=args.price_per_million)
    artifact = run_dev(args.benchmark, client, metadata)
    (args.output / "run.json").write_bytes(write_json(artifact))
    scores = regrade(artifact)
    (args.output / "scores.json").write_bytes(write_json(scores))
    print(write_json(scores["overall"]).decode(), end="")


if __name__ == "__main__":
    main()
