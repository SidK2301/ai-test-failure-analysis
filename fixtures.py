"""Generate a deterministic benchmark from failing unittest cases."""

import argparse
from contextlib import redirect_stdout
from dataclasses import dataclass
from itertools import combinations
import io
import json
from pathlib import Path
import random
import unittest
from xml.etree import ElementTree as XML

from workflow import parse_report, write_json

SEED = 42701
KINDS = ("cascade", "direct", "sparse")
HELD_OUT_TARGET = (10, 8, 7)


@dataclass(frozen=True)
class Scenario:
    name: str
    category: str
    operation: object
    exception: type[Exception]
    evidence: str
    mix: tuple[str, ...] = ("cascade", "cascade", "direct", "direct", "sparse")


def network(value):
    # Simulate the transport at the application boundary so generation is offline.
    raise ConnectionRefusedError(f"transport refused connection to {value}")


def assertion(value):
    assert value == "ready", f"health state must be ready, got {value}"


def dependency(value):
    __import__(f"_benchmark_missing_{value}")


def config(value):
    if value not in {"worker", "gateway"}:
        raise ValueError(f"unsupported APP_MODE {value}")


def timeout(value):
    raise TimeoutError(f"lease acquisition exceeded deadline for {value}")


def data(value):
    json.loads(f'{{"payload": {value}}}')


def other(value):
    raise PermissionError(f"sandbox policy denied access to {value}")


SPARSE_MIX = ("cascade", "cascade", "direct", "sparse", "sparse")
SCENARIOS = (
    Scenario("transport", "network", network, ConnectionRefusedError, "transport refused connection"),
    Scenario("health-state", "assertion", assertion, AssertionError, "health state must be ready"),
    Scenario("plugin-import", "missing_dependency", dependency, ModuleNotFoundError, "No module named"),
    Scenario("environment-mode", "config", config, ValueError, "unsupported APP_MODE"),
    Scenario("lease-deadline", "timeout", timeout, TimeoutError, "lease acquisition exceeded deadline"),
    Scenario("payload-decode", "data", data, json.JSONDecodeError, "Expecting value", SPARSE_MIX),
    Scenario("access-policy", "other", other, PermissionError, "sandbox policy denied access", SPARSE_MIX),
)


def choose_split(groups, seed):
    """Choose whole groups with a seeded tie-break and the closest held-out mix."""
    candidates = list(combinations(groups, len(groups) - 2))
    random.Random(seed).shuffle(candidates)

    def distance(candidate):
        counts = [sum(group.mix.count(kind) for group in candidate) for kind in KINDS]
        return sum(abs(count - target) for count, target in zip(counts, HELD_OUT_TARGET))

    return {group.name for group in min(candidates, key=distance)}


class InjectedFault(unittest.TestCase):
    def __init__(self, scenario, variant, kind):
        super().__init__()
        self.scenario = scenario
        self.variant = variant
        self.kind = kind

    def runTest(self):
        print("WARNING background cache refresh postponed")
        if self.kind == "cascade":
            print("ERROR telemetry exporter skipped optional metrics")
        try:
            self.scenario.operation(f"service_{self.variant}")
        except self.scenario.exception as error:
            if self.kind != "sparse":
                print(f"{type(error).__name__}: {error}")
            if self.kind == "direct":
                self.fail("Operation could not complete")
            if self.kind == "cascade":
                print("ERROR no result available for publication")
        self.fail("Test did not receive a result before its deadline")


def run_case(scenario, variant, kind):
    case = InjectedFault(scenario, variant, kind)
    result = unittest.TestResult()
    output = io.StringIO()
    with redirect_stdout(output):
        case.run(result)
    if len(result.failures) != 1 or result.errors:
        raise RuntimeError(f"Expected one test failure for {scenario.name}/{variant}")
    suite = XML.Element("testsuite", name="Injected faults", tests="1", failures="1")
    test = XML.SubElement(suite, "testcase", classname="Fixture")
    XML.SubElement(test, "system-out").text = output.getvalue()
    # unittest includes active exception chains for direct failures. Keep its
    # final traceback so each case has a single intended causal evidence source.
    traceback = result.failures[0][1].rsplit(
        "During handling of the above exception, another exception occurred:\n\n", 1
    )[-1]
    traceback = traceback.replace(str(Path(__file__).resolve()), "fixtures.py")
    XML.SubElement(test, "failure", type="AssertionError").text = traceback
    return XML.tostring(suite, encoding="unicode")


def generate(output, seed):
    held_out = choose_split(SCENARIOS, seed)
    reports = output / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    cases = []
    labels = {}
    for scenario in SCENARIOS:
        for variant, kind in enumerate(scenario.mix, start=1):
            case_id = f"{scenario.name}-{variant}"
            xml = run_case(scenario, variant, kind)
            (reports / f"{case_id}.xml").write_text(xml, encoding="utf-8")
            cases.append({
                "id": case_id, "scenario": scenario.name, "group": kind,
                "split": "held_out" if scenario.name in held_out else "dev",
                "report": f"reports/{case_id}.xml", "injected_category": scenario.category,
            })
            visible, = parse_report(xml)
            label = {"group": kind, "category": None, "sets": [], "context": []}
            matches = [line["id"] for line in visible["lines"] if scenario.evidence in line["text"]]
            if kind == "sparse":
                if matches:
                    raise ValueError(f"Sparse case exposes causal evidence: {case_id}")
            else:
                if len(matches) != 1:
                    raise ValueError(f"Expected exactly one visible causal line: {case_id}")
                label.update(category=scenario.category, sets=[matches])
            labels[case_id] = label
    counts = {
        split: {kind: sum(case["split"] == split and case["group"] == kind for case in cases) for kind in KINDS}
        for split in ("dev", "held_out")
    }
    (output / "manifest.json").write_bytes(write_json({"seed": seed, "counts": counts, "cases": cases}))
    (output / "labels.json").write_bytes(write_json(labels))
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    print(json.dumps(generate(args.output, args.seed), indent=2))
