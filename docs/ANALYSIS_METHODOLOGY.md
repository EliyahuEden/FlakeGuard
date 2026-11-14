# Analysis methodology

## Observation contract

A logical execution has a final raw outcome. `passed`, `failed`, and `timedOut` are eligible; `skipped`, `unknown`, and `interrupted` are excluded from rates but included in totals. Expected Playwright outcome is preserved for inspection, while current metrics describe raw execution behavior, including expected-failure tests.

Ordinary JUnit contains final observations and does not establish whether an unreported retry occurred. Its retry fields stay unknown. Playwright retry indices are preserved when present. Initial-pass metrics require an explicit index-zero eligible attempt. Retry recovery requires an observed failed/timed-out attempt followed by a final pass in the same execution. No retry probability is inferred from separate runs.

## Metric formulas

Let `N` be eligible executions, `P` final passes, `F` final failures/timeouts, `K` eligible executions with known retry data, `R` observed retry recoveries, `I` initially failed eligible executions that were actually retried, and `A` observations with explicit eligible initial-attempt information.

| Output | Definition |
|---|---|
| Pass/failure rate | `P/N`, `F/N` |
| First-attempt pass rate | explicit initial passes / `A` |
| Retry recovery rate | `R/I`; not divided by every failed execution or every retry attempt |
| Reliability score | `100 * (P-R)/N` |
| Suspicion score | `100 * (0.7 * R/K + 0.3 * alternation_fraction)`; missing `K` contributes zero observed recovery evidence |
| Duration | Sum of complete observed attempt durations for an execution; average over eligible complete-duration executions |
| Recent reliability change | Pass fraction in last five eligible observations minus the preceding up-to-five observations, null until prior observations exist |
| Newly failing observation | A final failure whose preceding eligible observation in the same test/branch/environment/provenance passed |
| Pattern occurrence | Failed **attempt** count; separate execution, run, and affected-test counts avoid denominator confusion |

All zero denominators return null except the internal suspicion component, which has zero observed supporting evidence. No null metric is displayed as a measured zero. Histories are ordered by run time, run ID, and execution ID. Time-source fallback may limit chronological conclusions.

## Reliability categories

Cohort key: test ID + branch + browser/environment key + provenance. Project is already part of test ID. Require at least five eligible executions and three distinct runs before applying the main labels.

1. Below either sample threshold: `insufficient_history`.
2. Every eligible final outcome failed/timed out: `consistently_failing`.
3. At least two observed retry recoveries, **or** both pass/fail outcomes with at least two across-run alternations and suspicion score at least 12: `suspected_flaky`.
4. All eligible outcomes passed with zero observed retry recoveries: `consistently_passing`.
5. Otherwise: `intermittent_failures`.

For alternation, repeated executions within a run contribute one outcome only if they agree. Ambiguous runs are excluded from this component. Adjacent retained run outcomes produce a transition if they differ. This prevents repeat-each observations in one build from manufacturing across-build evidence. Multiple recovered retries in one execution still count as one recovered observation.

The score weights and threshold are transparent design choices, not statistically learned constants. A stable regression introduced after one change produces a single transition and is not automatically flaky. Low-frequency instability can stay below the threshold: the standard evaluation misses the setup-failure scenario. Environment/automation causes remain distinct questions from observing intermittent behavior.

The 95% Wilson interval estimates the observed final pass proportion, using `z=1.96`. It assumes independent Bernoulli observations; correlated runs can make it optimistic. It is not a confidence that a test is flaky. Retry-unknown histories can overestimate reliability.

## Fingerprinting and similarity

`normalize-v1` strips ANSI escapes, normalizes timestamps, UUIDs, memory addresses, request/trace IDs, temporary paths and code locations, removes stack frame lines, collapses whitespace, and lowercases. It intentionally preserves assertion values, selectors, HTTP status codes, and error types. Use the error message when supplied, falling back to the stack and then a labeled missing-diagnostic marker.

Fingerprint = SHA-256 of `normalize-v1 + NUL + normalized diagnostic`. Exact groups are deterministic across builds. A separate SequenceMatcher pass suggests similarly worded pairs at similarity ≥0.85, limited to 200 sorted patterns. These suggestions never merge groups. Different bugs can emit identical messages; the system claims textual recurrence only.

First-seen history queries the whole repository/provenance history rather than resetting at a date filter. `new_in_selection` means the selection contains the historical first occurrence; it does not mean a defect was introduced by a particular commit. Correlation with commits and newly failing observations helps an engineer investigate but does not prove causation.

## Classification rules

Rules run in deterministic precedence order:

1. Explicit transport/resource/browser-process signals (connection refused, DNS failure, crashed browser, memory/disk exhaustion, unavailable service): suspected infrastructure, moderate evidence.
2. Fixture, locator ambiguity, isolation, or shared-state signals: suspected automation, moderate evidence.
3. Assertion comparisons: suspected application, low evidence; moderate with at least three consecutive final failures in a matching test history.
4. Timeout alone or no recognized signals: unknown, low evidence.

Observed retry recovery can change an unknown/application suggestion to suspected automation with low evidence and prompts comparison of retry traces. This is deliberately only a suggestion: application races can also recover. Three or more tests with the same pattern and ≥50% of eligible execution outcomes in a run add a shared-dependency investigation signal; they do not establish infrastructure causality.

Every result includes signals, qualitative evidence strength, a limitation statement, and suggested investigation steps. No rules assign a calibrated probability or suppress a quality gate.

## Evaluation boundaries

The 32-case diagnostic dataset has eight authored injected examples per label, including three deliberately ambiguous text cases. The observed confusion matrix, precision, recall, and F1 are computed from predictions, not typed into a dashboard. The data is small and not independently held out. Reported 90.625% accuracy and 93.18% macro precision are **synthetic diagnostic-set measurements only**.

Twelve labeled diagnostic pairs evaluate normalization grouping/separation, not root-cause equivalence. The seeded demo evaluates four known intermittent scenario names; the detector finds three and misses one (precision 1.0, recall 0.75). The real CommerceGuard fixtures verify ingestion correctness and persistence only; their presence does not establish real-world classification precision.
