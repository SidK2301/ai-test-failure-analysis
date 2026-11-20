import unittest
from unittest.mock import patch

from ollama_client import Ollama


class OllamaTests(unittest.TestCase):
    def test_schema_context_and_content(self):
        client = Ollama("unit-test:latest", "test prompt")
        with patch.object(client, "request", return_value={
            "message": {"thinking": "internal", "content": "{}"},
            "done": True, "done_reason": "stop", "prompt_eval_count": 50, "eval_count": 2,
        }) as request:
            result = client({"lines": []})
        path, payload = request.call_args.args
        self.assertEqual(path, "/api/chat")
        self.assertEqual(len(payload["format"]["anyOf"]), 2)
        self.assertEqual(payload["options"]["num_ctx"], 4096)
        self.assertFalse(payload["truncate"])
        self.assertFalse(payload["shift"])
        self.assertEqual(result["raw_response"], "{}")
        self.assertNotIn("request_error", result)

    def test_insufficient_context(self):
        client = Ollama("unit-test:latest", "test prompt")
        with patch.object(client, "request", return_value={
            "message": {"content": "{}"},
            "done": True, "done_reason": "stop", "prompt_eval_count": 3900,
        }):
            self.assertIn("request_error", client({"lines": []}))
