# Evaluation specification

## Inputs

Read JUnit XML with a `testsuites` or `testsuite` root. Analyze each testcase
with a direct `failure` or `error` child. Keep test identities distinct even
when names repeat. Use testcase-local evidence in report order: system-out,
system-err, then failure material (failure and error messages and bodies in XML
order). Preserve order within each source. Report order does not imply chronology.
Suite-level logs are outside this input format.

Keep the first 120 stdout lines, first 80 stderr lines, and up to 100 failure
lines. For an overflowing failure source, keep the first 60 and last 40.
Record dropped line counts for each source. Cap each retained line at 1,000
characters, mark clipped lines, and then assign consecutive IDs starting at 1.
The model and heuristic receive the same visible lines. Labels refer to those
lines. Repairs to fixtures and labels happen before the held-out freeze.

## Responses

Each response is one JSON object with exactly root_cause, evidence, and status.
A diagnosed response has a root_cause object with exactly category and a
nonblank explanation. Categories are network, assertion, missing_dependency,
config, timeout, data, and other. The category other matches only other.
Evidence is an ordered list of one to three distinct integer IDs from the
visible lines. Put the strongest causal citation first. An insufficient_evidence
response has a null root_cause and an empty evidence list.

Use one model request per failed testcase in the live benchmark. A failed
request, malformed JSON, incompatible shape, or invalid ID is a workflow error.
Score the first attempt. Measure raw citation validity before rejection using
all entries in parsed evidence lists as the denominator. A raw entry is valid
if it is an integer ID in the visible input. Report a zero denominator as 0/0.

## Labels and grades

Label against visible input. A diagnosable case has an expected category,
one or more acceptable nonempty evidence sets, and optional context IDs.
An inconclusive case has none of those labels. The injected cause remains
fixture metadata. A lucky guess on an inconclusive case is a false diagnosis.

Evidence passes if the citations contain a complete acceptable set and every
citation is in the union of acceptable sets and context IDs. A correct diagnosis
also requires the expected category. A valid diagnosis failing either check is
a wrong diagnosis. Count a failure as due only to an unlabeled extra citation
if the category is right, a complete set is covered, and an extra ID is outside
the allowed union. All IDs must already have passed validation.

Diagnosable cases map to correct diagnosis, wrong diagnosis, false abstention,
or workflow error. Inconclusive cases map to correct abstention, false
diagnosis, or workflow error. Each case contributes to exactly one cell.
Check that the six counts sum to the number of cases.

Compare one pick each on diagnosable cases: the model's first citation and the
heuristic's first match in report order. Each earns a hit if the pick is in any
acceptable set. An abstention, lack of a match, or workflow error is a miss for
the respective system. Count a model ordering failure when a valid response's
first citation misses and a later citation hits. The draft heuristic is the
case-insensitive regex `\\b(?:errors?|exceptions?|[A-Za-z_][A-Za-z_0-9]*(?:Error|Exception))\\b`.
Tune it on dev only and freeze it before held-out evaluation.

Report outcome counts overall and by group. Report category accuracy, strict
evidence accuracy, full evidence-set coverage (regardless of allowed extras),
and both first-pick hit rates as counts over all diagnosable cases. Abstentions
and workflow errors contribute misses to each model metric. Also report ordering
failures, extra-citation-only failures, raw citation validity, requests, token
usage, available cost, and latency. Preserve unknown cost as unknown.

## Splits and freeze

Generate actual JUnit reports from a Python fixture project with injected faults.
Before labeling, assign whole scenario groups with a seeded stratified random
assignment using the per-group mix of cascade, direct, and sparse variants.
Record the seed and actual counts. Aim for about 10 development cases and 25
held-out cases (10 cascade, 8 direct, 7 sparse). Keep mixed groups intact.

Tune the prompt and regex on development cases only. Freeze the prompt, regex,
parser and truncation code, labels, manifest, and this spec in a tagged commit
before sending held-out cases to the model.

## Run artifacts and offline regrading

Save model ID, parameters including temperature and max tokens, git hash,
prompt version, and exact heuristic regex. Save each case's visible input,
labels, raw response or request failure, and request count, token counts,
cost, and latency when available. Keep the raw benchmark artifact separate
from the score report. Regrading is offline and uses the recorded regex and
saved data. Stable JSON serialization and case ordering make the score report
byte-reproducible for the same saved artifacts and grader version.

Save the frozen score before error analysis. Label any rescoring post-hoc
and report repeat runs individually. Verify byte-identical regrades from mock
artifacts in Phase 1 and held-out artifacts in Phase 3.
