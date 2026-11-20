# Phase 2 development benchmark

The checked-in reports capture 35 actual unittest failures from a small fault
fixture. It simulates application failures offline. The benchmark measures
behavior on this controlled fixture and shares failure patterns across scenario
groups. It does not estimate performance on production CI logs.

The generator enumerates assignments of five whole scenario groups to held-out
and two to development, minimizes absolute deviation from the held-out group
targets, and chooses among tied assignments using seed 42701. It selects the
split before labeling against parsed, retained lines. See the manifest for
actual counts. Use the checked-in reports for evaluation since Python traceback
format can vary across versions. Regenerate separately with:

```sh
python3 fixtures.py /tmp/failure-fixtures
```

Run the development set with an existing Anthropic API key in
`ANTHROPIC_API_KEY` and a structured-output-capable model identifier in
`CLAUDE_MODEL`. Use an unused output directory:

```sh
python3 model_client.py /tmp/failure-dev-run
python3 workflow.py regrade /tmp/failure-dev-run/run.json /tmp/failure-dev-run/regrade.json
cmp /tmp/failure-dev-run/scores.json /tmp/failure-dev-run/regrade.json
```

The client attempts one request per dev case. The saved artifact records the
model parameters and raw API response, when available. Temperature is unset
and the provider controls sampling. Optional `--price-per-million INPUT OUTPUT`
records a USD estimate using the supplied per-million token rates. Unknown
cost stays unset. Prompt and heuristic tuning happen on dev only. A freeze tag
is due after dev iteration.

[Claude Messages API](https://platform.claude.com/docs/en/api/messages/create)
