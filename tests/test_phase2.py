import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fixtures import SEED, generate
from model_client import Claude, ROOT, run_dev
from workflow import regrade, write_json

ABSTAIN = '{"root_cause":null,"evidence":[],"status":"insufficient_evidence"}'


class BenchmarkTests(unittest.TestCase):
    def test_split_and_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(generate(root, SEED), {
                "dev": {"cascade": 4, "direct": 4, "sparse": 2},
                "held_out": {"cascade": 10, "direct": 8, "sparse": 7},
            })
            manifest = json.loads((root / "manifest.json").read_bytes())
            for group in {case["scenario"] for case in manifest["cases"]}:
                self.assertEqual(len({case["split"] for case in manifest["cases"] if case["scenario"] == group}), 1)
            artifact = run_dev(root, lambda _: ABSTAIN, {})
            self.assertEqual(regrade(artifact)["overall"]["outcomes"]["false_abstention"], 8)

    def test_committed_dev_inputs_only(self):
        requests = []

        def respond(visible):
            requests.append(visible)
            self.assertEqual(set(visible), {"id", "name", "classname", "lines", "dropped_lines"})
            return {"raw_response": ABSTAIN, "requests": 0}

        artifact = run_dev(ROOT / "benchmark", respond, {"mode": "mock"})
        manifest = json.loads((ROOT / "benchmark" / "manifest.json").read_bytes())
        self.assertEqual(
            [record["visible"]["id"] for record in artifact["cases"]],
            [case["id"] for case in manifest["cases"] if case["split"] == "dev"],
        )
        self.assertEqual(len(requests), 10)
        self.assertEqual(write_json(regrade(artifact)), write_json(regrade(json.loads(write_json(artifact)))))


class ClientTests(unittest.TestCase):
    @patch("model_client.urlopen")
    def test_structured_output_single_request(self, transport):
        transport.return_value = io.BytesIO(json.dumps({
            "model": "test-model",
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": ABSTAIN}],
            "usage": {"input_tokens": 100, "output_tokens": 25},
        }).encode())
        client = Claude("test-key", "test-model", "test prompt")
        result = client({"lines": []})
        transport.assert_called_once()
        request = transport.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(json.loads(payload["messages"][0]["content"]), {"lines": []})
        self.assertEqual(result["raw_response"], ABSTAIN)
        self.assertEqual(result["input_tokens"], 100)
        self.assertEqual(result["requests"], 1)
