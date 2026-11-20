import unittest
from unittest.mock import patch

from held_out import FrozenOllama
from ollama_client import Ollama


class FrozenRequestTests(unittest.TestCase):
    @patch.object(Ollama, "request")
    def test_mismatch_rejected_before_request(self, transport):
        client = FrozenOllama("unit-test:latest", "prompt", request_settings={"think": False})
        with self.assertRaisesRegex(RuntimeError, "differed from the freeze"):
            client.request("/api/chat", {"think": True})
        transport.assert_not_called()

    @patch.object(Ollama, "request")
    def test_matching_request_reaches_transport(self, transport):
        client = FrozenOllama("unit-test:latest", "prompt", request_settings={"think": False})
        client.request("/api/chat", {"think": False})
        transport.assert_called_once_with("/api/chat", {"think": False})
