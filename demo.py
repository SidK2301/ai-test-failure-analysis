"""Save a mock run containing one supported diagnosis and one abstention."""

import argparse
import json
from pathlib import Path

from workflow import capture, regrade, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = Path(__file__).with_name("examples") / "report.xml"
    labels = {
        "test-1": {"category": "network", "sets": [[2, 3]], "context": [1], "group": "cascade"},
        "test-2": {"category": None, "sets": [], "context": [], "group": "sparse"},
    }
    responses = {
        "test-1": {
            "root_cause": {
                "category": "network",
                "explanation": "The refused connection stopped the network client.",
            },
            "evidence": [2, 3],
            "status": "diagnosed",
        },
        "test-2": {"root_cause": None, "evidence": [], "status": "insufficient_evidence"},
    }

    def respond(test):
        return {"raw_response": json.dumps(responses[test["id"]]), "requests": 0}

    artifact = capture(report.read_bytes(), labels, respond, metadata={"mode": "mock"})
    (args.output / "run.json").write_bytes(write_json(artifact))
    (args.output / "scores.json").write_bytes(write_json(regrade(artifact)))


if __name__ == "__main__":
    main()
