"""Deterministic JUnit analysis and offline benchmark scoring."""

import argparse
from collections import Counter
from decimal import Decimal
import json
from pathlib import Path
import re
from xml.etree import ElementTree

CATEGORIES = {"network", "assertion", "missing_dependency", "config", "timeout", "data", "other"}
ERROR_PATTERN = r"\b(?:errors?|exceptions?|[A-Za-z_][A-Za-z_0-9]*(?:Error|Exception))\b"
OUTCOMES = (
    "correct_diagnosis", "wrong_diagnosis", "correct_abstention",
    "false_abstention", "false_diagnosis", "workflow_error",
)
SOURCE_LIMITS = {"system-out": 120, "system-err": 80, "failure": 100}
MAX_LINE_LENGTH = 1000


def parse_report(xml):
    root = ElementTree.fromstring(xml)
    for element in root.iter():
        element.tag = element.tag.rsplit("}", 1)[-1]
    if root.tag not in {"testsuite", "testsuites"}:
        raise ValueError("Expected a JUnit testsuite or testsuites root")

    failed = []
    for index, testcase in enumerate(root.iter("testcase"), start=1):
        problems = [child for child in testcase if child.tag in {"failure", "error"}]
        if not problems:
            continue

        sources = {}
        for name in ("system-out", "system-err"):
            sources[name] = [
                line for node in testcase.findall(name)
                for line in "".join(node.itertext()).splitlines()
            ]
        sources["failure"] = [
            line for problem in problems
            for text in (problem.get("message", ""), "".join(problem.itertext()))
            for line in text.splitlines()
        ]
        visible = []
        dropped = {}
        for source, limit in SOURCE_LIMITS.items():
            lines = sources[source]
            dropped[source] = max(0, len(lines) - limit)
            if source == "failure" and dropped[source]:
                retained = lines[:60] + lines[-40:]
            else:
                retained = lines[:limit]
            for line in retained:
                visible.append({
                    "id": len(visible) + 1,
                    "source": source,
                    "text": line[:MAX_LINE_LENGTH],
                    "clipped": len(line) > MAX_LINE_LENGTH,
                })
        failed.append({
            "id": f"test-{index}", "name": testcase.get("name", ""),
            "classname": testcase.get("classname", ""), "lines": visible,
            "dropped_lines": dropped,
        })
    return failed


def validate(raw, ids):
    if not isinstance(raw, str):
        return None, 0, 0
    try:
        response = json.loads(raw)
    except (ValueError, RecursionError):
        return None, 0, 0
    if not isinstance(response, dict):
        return None, 0, 0

    evidence = response.get("evidence")
    citations = evidence if isinstance(evidence, list) else []
    valid = sum(type(item) is int and item in ids for item in citations)
    counts = (valid, len(citations))
    if response.keys() != {"root_cause", "evidence", "status"} or not isinstance(evidence, list):
        return None, *counts

    cause = response["root_cause"]
    if response["status"] == "insufficient_evidence" and cause is None and not evidence:
        return response, *counts
    if (
        response["status"] == "diagnosed"
        and isinstance(cause, dict)
        and cause.keys() == {"category", "explanation"}
        and isinstance(cause["category"], str)
        and cause["category"] in CATEGORIES
        and isinstance(cause["explanation"], str)
        and cause["explanation"].strip()
        and 1 <= valid == len(evidence) <= 3
        and len(set(evidence)) == len(evidence)
    ):
        return response, *counts
    return None, *counts


def capture(xml, labels, respond, *, metadata=None, heuristic_pattern=ERROR_PATTERN):
    """Call the injected responder once per case and save artifacts for regrading.

    The responder returns raw JSON text or a mapping with raw_response and
    optional request_error, input_tokens, output_tokens, cost_usd, latency_ms.
    """
    cases = parse_report(xml)
    if labels.keys() != {case["id"] for case in cases}:
        raise ValueError("Labels must match the failed testcase IDs")
    records = []
    for case in cases:
        result = respond(case)
        if not isinstance(result, dict):
            result = {"raw_response": result}
        records.append({"visible": case, "label": labels[case["id"]], "attempt": result})
    return {
        "version": 1, "metadata": metadata or {}, "heuristic_pattern": heuristic_pattern,
        "cases": records,
    }


def grade(case, heuristic_pattern=ERROR_PATTERN):
    lines = case["visible"]["lines"]
    ids = {line["id"] for line in lines}
    label = case["label"]
    category = label["category"]
    acceptable = [set(evidence) for evidence in label["sets"]]
    causal = set().union(*acceptable)
    context = set(label["context"])
    diagnosable = category is not None
    if (
        (diagnosable and (category not in CATEGORIES or not acceptable))
        or (not diagnosable and (acceptable or context))
        or any(not evidence or len(evidence) > 3 for evidence in acceptable)
        or not (causal | context) <= ids
    ):
        raise ValueError(f'Invalid benchmark label for {case["visible"]["id"]}')

    attempt = case["attempt"]
    response, valid, total = validate(attempt.get("raw_response"), ids)
    heuristic = re.compile(heuristic_pattern, re.IGNORECASE)
    first_error = next((line["id"] for line in lines if heuristic.search(line["text"])), None)
    result = {
        "id": case["visible"]["id"], "group": label["group"], "diagnosable": diagnosable,
        "model_hit": False, "heuristic_hit": first_error in causal,
        "category_correct": False, "evidence_correct": False, "coverage": False,
        "ordering_failure": False, "extra_citation_only": False,
        "valid_citations": valid, "citations": total,
    }
    if attempt.get("request_error") is not None or response is None:
        outcome = "workflow_error"
    elif response["status"] == "insufficient_evidence":
        outcome = "false_abstention" if diagnosable else "correct_abstention"
    elif not diagnosable:
        outcome = "false_diagnosis"
    else:
        evidence = response["evidence"]
        cited = set(evidence)
        model_hit = evidence[0] in causal
        category_correct = response["root_cause"]["category"] == category
        coverage = any(evidence_set <= cited for evidence_set in acceptable)
        extra = bool(cited - (causal | context))
        evidence_correct = coverage and not extra
        result.update(
            model_hit=model_hit, category_correct=category_correct,
            coverage=coverage, evidence_correct=evidence_correct,
            ordering_failure=not model_hit and bool(cited & causal),
            extra_citation_only=category_correct and coverage and extra,
        )
        outcome = "correct_diagnosis" if category_correct and evidence_correct else "wrong_diagnosis"
    result["outcome"] = outcome
    return result


def summarize(grades):
    outcomes = Counter(result["outcome"] for result in grades)
    assert not (outcomes.keys() - set(OUTCOMES)) and sum(outcomes.values()) == len(grades)
    summary = {"cases": len(grades), "outcomes": {key: outcomes[key] for key in OUTCOMES}}
    diagnosable = [result for result in grades if result["diagnosable"]]
    for key in ("model_hit", "heuristic_hit", "category_correct", "evidence_correct", "coverage"):
        summary[key] = {"hits": sum(result[key] for result in diagnosable), "total": len(diagnosable)}
    for key in ("ordering_failure", "extra_citation_only"):
        summary[key] = sum(result[key] for result in grades)
    summary["citation_validity"] = {
        "hits": sum(result["valid_citations"] for result in grades),
        "total": sum(result["citations"] for result in grades),
    }
    return summary


def regrade(artifact):
    if artifact["version"] != 1:
        raise ValueError("Unsupported run artifact version")
    grades = [grade(case, artifact["heuristic_pattern"]) for case in artifact["cases"]]
    groups = sorted({result["group"] for result in grades})
    attempts = [case["attempt"] for case in artifact["cases"]]
    usage = {"attempts": len(attempts)}
    for key in ("requests", "input_tokens", "output_tokens", "cost_usd", "latency_ms"):
        values = [attempt[key] for attempt in attempts if attempt.get(key) is not None]
        total = sum(Decimal(str(value)) for value in values)
        usage[key] = {"total": str(total) if values else None, "recorded": len(values)}
    return {
        "overall": summarize(grades),
        "by_group": {
            group: summarize([result for result in grades if result["group"] == group])
            for group in groups
        },
        "cases": grades,
        "usage": usage,
    }


def write_json(data):
    return (json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    parse_command = commands.add_parser("parse", help="Show the visible input for each failure")
    parse_command.add_argument("report", type=Path)
    grade_command = commands.add_parser("regrade", help="Score saved responses offline")
    grade_command.add_argument("artifact", type=Path)
    grade_command.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.command == "parse":
        print(write_json(parse_report(args.report.read_bytes())).decode(), end="")
    else:
        args.output.write_bytes(write_json(regrade(json.loads(args.artifact.read_bytes()))))


if __name__ == "__main__":
    main()
