# AI Test Failure Analysis Workflow

This Python workflow reads failed tests from JUnit XML and sends each test's
numbered log lines to a local model through Ollama. The model returns a cause
category, an explanation, and citations, or marks the evidence insufficient.
Python validates the citation IDs and scores the diagnoses against labeled
faults and a first-error heuristic. Saved runs can be regraded offline.

## Held-out findings

Qwen3 4B usually found the causal line, often chose the wrong category, and
never abstained on the sparse cases.

- **Evidence selection:** 17/18 first picks were causal, versus 8/18 for the heuristic. On cascades, the comparison was 10/10 versus 0/10.
- **Category accuracy:** 6/18. The model labeled the other 12 diagnosable cases as missing dependencies.
- **Abstention:** 0/7. The model diagnosed every sparse case as a timeout.

See the [full report](benchmark/phase3/README.md) for the 25-case breakdown,
limitations, and raw results. The [evaluation spec](eval_spec.md) defines the
grading rules.

## Run with Ollama

Use Python 3.11 or later, Ollama 0.40.16, and the Qwen3 4B model. From the
repository root, start Ollama locally in a separate terminal with the frozen
server settings.

```sh
env OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NO_CLOUD=1 OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 ollama serve
```

Download the model and run the 10 development cases into a new output directory.
The runner verifies the model digest and Ollama version.

```sh
ollama pull qwen3:4b
python3 ollama_client.py /tmp/failure-dev-ollama \
  --model qwen3:4b \
  --digest 359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7 \
  --ollama-version 0.40.16
```

## Regrade offline

These commands reproduce the saved held-out scores and check byte equality.

```sh
python3 workflow.py regrade benchmark/phase3/run.json /tmp/failure-held-out-regrade.json
cmp benchmark/phase3/scores.json /tmp/failure-held-out-regrade.json
```
