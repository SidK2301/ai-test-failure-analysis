# Held-out benchmark results

Qwen3 4B usually located the causal line, often chose the wrong category, and
never abstained on the sparse cases.

- **First causal pick:** 17/18 for the model versus 8/18 for the heuristic. On cascades, it was 10/10 versus 0/10.
- **Category accuracy:** 6/18. The model labeled the remaining 12 diagnosable cases as missing dependencies.
- **Abstention:** 0/7. Every sparse case was diagnosed as a timeout.

Qwen3 4B (Q4_K_M) ran on local Ollama 0.40.16 using the frozen configuration
(tag `phase-2-freeze`, commit `f743d2b`).
The run produced 6 correct outcomes across 25 cases.

| Case group | Cases | Correct diagnoses | Wrong diagnoses | Correct abstentions | False abstentions | False diagnoses | Workflow errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Cascade | 10 | 4 | 6 | 0 | 0 | 0 | 0 |
| Direct | 8 | 2 | 6 | 0 | 0 | 0 | 0 |
| Sparse | 7 | 0 | 0 | 0 | 0 | 7 | 0 |
| Overall | 25 | 6 | 12 | 0 | 0 | 7 | 0 |

| Metric | Result |
| --- | ---: |
| Category accuracy | 6/18 |
| Strict evidence accuracy | 15/18 |
| Full evidence-set coverage | 17/18 |
| Model first causal pick | 17/18 |
| First-error heuristic causal pick | 8/18 |
| Causal line cited after the first citation | 0 |
| Failures due only to unlabeled extra citations | 0 |
| Raw citation validity | 29/29 |

The category, evidence, and first-pick metrics use the 18 diagnosable cases.

The benchmark made 25 local generation requests.
Ollama reported 14700 input tokens and
1536 output tokens. Summed request latency was
42.24 seconds.
The requests incurred $0 in API charges.

## Error analysis

- The model correctly diagnosed all four visible connection refusals and two
  explicit lease timeouts. It correctly identified the category in 6 of 18
  diagnosable cases.
- It classified all 12 other diagnosable failures as missing dependencies,
  including unsupported configuration values, invalid JSON, and permission
  errors. **Prompt-example bias:** Several explanations echoed the
  missing-plugin example in the frozen prompt even when the cited line
  identified a different cause. On `environment-mode-1`, the model cited
  line 3, which reports an unsupported application mode, and described a
  failed plugin import. This pattern suggests the example influenced the
  4B model's classifications. The run did not isolate the example's effect.
- All seven sparse responses took the generic test deadline as evidence for a
  timeout. The visible logs establish the missing result and leave its cause
  inconclusive. Each response counts as a false diagnosis.
- The model found a causal first citation in all 10 cascade cases, compared
  with 0 for the first-error heuristic. The heuristic selected the earlier
  telemetry error in each cascade. On direct cases the model found the causal
  line in 7 of 8, compared with 8 of 8 for the heuristic.

## Limitations

- The benchmark has seven scenario groups across both splits. Variants within
  a group share the same underlying fault, so the cases are correlated.
- Every cascade fixture puts the same telemetry error first. The heuristic's
  0/10 on cascades measures its behavior against that distractor pattern.
- The results come from one run of one quantized 4B model.
- This held-out set has now been seen. Evaluate prompt revisions on a fresh
  held-out set or label any rerun on these cases as post-freeze.

## Run provenance

A preflight attempt imported an experimental adapter from the staging
directory and sent five transport-case requests with reasoning enabled. Four
returned before the fifth was interrupted. Those requests are excluded from
the frozen run and were not used to tune the model or grader. The corrected
runner verifies the source paths, frozen file hashes, local model digest,
Ollama version, and request settings before generation. It sent each held-out
case once under the frozen configuration. No post-hoc rescoring was applied.

The [run artifact](run.json) contains the exact request and returned response
for every scored case. The [score report](scores.json) includes per-case
grades and can be reproduced offline.
