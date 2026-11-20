# AI Test Failure Analysis Workflow

Phase 1 provides the deterministic parts of the workflow. It extracts
testcase-local evidence from JUnit XML, validates structured responses against
visible line IDs, and grades them alongside a first-error heuristic. The
[specification](eval_spec.md) defines how the grades are calculated.

Run from the project directory with Python 3.11 or later. There are no
third-party dependencies.

```sh
python3 -m unittest discover -s tests -v
python3 workflow.py parse examples/report.xml
python3 demo.py /tmp/test-failure-demo
python3 workflow.py regrade /tmp/test-failure-demo/run.json /tmp/test-failure-demo/regraded.json
cmp /tmp/test-failure-demo/scores.json /tmp/test-failure-demo/regraded.json
```

The demo uses two hard-coded responses and makes zero model requests. Its scores
verify the workflow and grader. The live model integration and benchmark belong
to the later phases.

## Held-out benchmark results

The [Phase 3 report](benchmark/phase3/README.md) summarizes the single
held-out run and links to its raw responses and scores.

To regrade the saved run offline, start in the repository root.

```sh
python3 workflow.py regrade benchmark/phase3/run.json /tmp/failure-held-out-regrade.json
cmp benchmark/phase3/scores.json /tmp/failure-held-out-regrade.json
```
