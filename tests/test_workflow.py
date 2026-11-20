import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from workflow import capture, grade, parse_report, regrade, write_json

REPORT = """<testsuite>
  <testcase classname="Demo" name="checkout">
    <failure message="TimeoutError: checkout timed out">trace</failure>
    <system-out>WARN cached value
ERROR connection refused
network client stopped</system-out>
    <system-err>retry scheduled</system-err>
  </testcase>
  <testcase name="skipped"><skipped /></testcase>
</testsuite>"""
LABEL = {"group": "cascade", "category": "network", "sets": [[2, 3]], "context": [1]}


def diagnosis(*ids, category="network"):
    return json.dumps({
        "root_cause": {"category": category, "explanation": "Connection refused."},
        "evidence": list(ids),
        "status": "diagnosed",
    })


ABSTAIN = '{"root_cause":null,"evidence":[],"status":"insufficient_evidence"}'


class GoldenGraderTests(unittest.TestCase):
    def check(self, raw, label=LABEL):
        case = capture(REPORT, {"test-1": label}, lambda _: raw)["cases"][0]
        return grade(case)

    def test_two_line_cause(self):
        self.assertEqual(self.check(diagnosis(2, 3))["outcome"], "correct_diagnosis")
        result = self.check(diagnosis(2))
        self.assertTrue(result["model_hit"])
        self.assertFalse(result["coverage"])

    def test_right_category_weak_evidence(self):
        result = self.check(diagnosis(1))
        self.assertEqual(result["outcome"], "wrong_diagnosis")
        self.assertTrue(result["category_correct"])
        self.assertFalse(result["evidence_correct"])

    def test_lucky_sparse_guess(self):
        label = {"group": "sparse", "category": None, "sets": [], "context": []}
        self.assertEqual(self.check(diagnosis(2), label)["outcome"], "false_diagnosis")
        self.assertEqual(self.check(ABSTAIN, label)["outcome"], "correct_abstention")

    def test_invalid_id(self):
        result = self.check(diagnosis(2, 99))
        self.assertEqual(result["outcome"], "workflow_error")
        self.assertEqual((result["valid_citations"], result["citations"]), (1, 2))

    def test_four_citations(self):
        result = self.check(diagnosis(2, 3, 1, 4))
        self.assertEqual(result["outcome"], "workflow_error")
        self.assertEqual(result["valid_citations"], 4)

    def test_abstention_misses(self):
        result = self.check(ABSTAIN)
        self.assertEqual(result["outcome"], "false_abstention")
        self.assertFalse(result["model_hit"])

    def test_causal_line_cited_second(self):
        result = self.check(diagnosis(1, 2, 3))
        self.assertEqual(result["outcome"], "correct_diagnosis")
        self.assertFalse(result["model_hit"])
        self.assertTrue(result["coverage"])
        self.assertTrue(result["ordering_failure"])

    def test_unlabeled_extra_citation(self):
        result = self.check(diagnosis(2, 3, 4))
        self.assertEqual(result["outcome"], "wrong_diagnosis")
        self.assertTrue(result["extra_citation_only"])

    def test_invalid_json(self):
        self.assertEqual(self.check("{")["outcome"], "workflow_error")

    def test_invalid_status_shape(self):
        raw = json.dumps({"root_cause": None, "evidence": [2], "status": "insufficient_evidence"})
        self.assertEqual(self.check(raw)["outcome"], "workflow_error")


class PipelineTests(unittest.TestCase):
    def test_per_source_truncation_and_numbering(self):
        stdout = "\n".join(f"stdout {i}" for i in range(130))
        trace = "\n".join(f"trace {i}" for i in range(110))
        xml = f'<testsuite><testcase name="x"><failure>{trace}</failure><system-out>{stdout}</system-out></testcase></testsuite>'
        test, = parse_report(xml)
        self.assertEqual(test["dropped_lines"], {"system-out": 10, "system-err": 0, "failure": 10})
        self.assertEqual(test["lines"][119]["text"], "stdout 119")
        self.assertEqual(test["lines"][120]["text"], "trace 0")
        self.assertEqual(test["lines"][180]["text"], "trace 70")
        self.assertEqual(test["lines"][-1], {"id": 220, "source": "failure", "text": "trace 109", "clipped": False})

    def test_mock_capture_and_byte_identical_offline_regrade(self):
        xml = REPORT.replace("</testsuite>", '<testcase name="checkout"><error message="timeout" /></testcase></testsuite>')
        labels = {
            "test-1": LABEL,
            "test-3": {"group": "sparse", "category": None, "sets": [], "context": []},
        }
        seen = []

        def mock(test):
            seen.append(test["id"])
            self.assertNotIn("label", test)
            return diagnosis(2, 3) if test["id"] == "test-1" else ABSTAIN

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.json"
            artifact = capture(xml, labels, mock)
            self.assertEqual(seen, ["test-1", "test-3"])
            expected = write_json(regrade(artifact))
            path.write_bytes(write_json(artifact))
            with patch("socket.socket", side_effect=AssertionError("network access")):
                actual = write_json(regrade(json.loads(path.read_bytes())))
            self.assertEqual(actual, expected)
        summary = json.loads(expected)["overall"]
        self.assertEqual(sum(summary["outcomes"].values()), 2)
        self.assertEqual(summary["outcomes"]["correct_diagnosis"], 1)
        self.assertEqual(summary["outcomes"]["correct_abstention"], 1)
