# Phase 2 development results

These runs used Qwen3 4B (Q4_K_M) in Ollama 0.40.16 on an Apple Silicon Mac
with 16 GiB of unified memory. All runs used the same ten development cases.
No held-out case was sent to the model.

| Dev configuration | Correct diagnoses | Correct abstentions | First causal pick | Workflow errors |
| --- | ---: | ---: | ---: | ---: |
| initial | 0/8 | 2/2 | 0/8 | 0 |
| tuned | 4/8 | 0/2 | 7/8 | 0 |
| evidence-first | 0/8 | 0/2 | 0/8 | 10 |
| strict | 0/8 | 0/2 | 8/8 | 0 |
| reasoning | 1/8 | 0/2 | 1/8 | 9 |

The freeze selects **tuned** by total correct dev outcomes, with fewer
workflow errors as the first tie-break and causal first picks as the second.
The original heuristic was retained as the
first-error baseline and found the causal line in 4 of 8 diagnosable dev cases.
Filtering fixture-specific warnings would change the comparison.

The initial smoke test sent the longest development input and saw 527 prompt
tokens. Ollama rejected a deliberately oversized synthetic request with HTTP 400.
The model used a 4,096-token context. Smoke requests are separate from the table.

Prior runs store the visible lines and the benchmark case ID, replacing the
per-report ID `test-1` in the score artifact. Later runs also store the exact
request payload. Scores can be regenerated with the offline regrade command.

These scores reflect a small controlled development benchmark. Phase 3 will
score the frozen configuration on 25 held-out cases.
