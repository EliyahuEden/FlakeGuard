# Demonstration data and evaluation

## Reproducing the demonstration

```bash
flakeguard demo --with-local
python scripts/import_examples.py
flakeguard evaluate --output docs/evidence/evaluation.json
```

- **Synthetic:** 30 seeded daily runs × 12 scenarios × 2 explicit browsers = **720
  executions**. Includes passing, deterministic regression, retry-recovered timing and
  connection failures, shared state, setup failures, browser-specific behavior, new
  regression, duration growth, skipped, unknown and rare failures. Browser behavior here
  is simulated report data, not an executed cross-browser suite.
- **Executed with injected conditions:** 12 actual pytest runs × 6 cases = **72
  execution records**. Includes a real loopback TCP connection refusal and controlled
  assertion, scheduler-model timing, state and fixture failures. JUnit correctly leaves
  retries unknown. The intentionally failing tests live outside the platform's default
  test paths.
- **Actual CommerceGuard reports:** 119 records, 118 ordinary and one injected defect
  record, imported independently of the synthetic demo.

The synthetic demo is idempotent. Existing executed demo runs are not rerun with changed
durations; to regenerate them explicitly:

```bash
flakeguard reset-demo
flakeguard demo --with-local
```

Reset only removes runs marked `source=demo` in reserved demo repositories. It preserves
ordinary imported projects.

## Measured evaluation

Results are stored in [evaluation JSON](evidence/evaluation.json) and summarized in the
[validation evidence](VALIDATION.md).

| Measure | Result |
| --- | --- |
| Diagnostic classification, 32 authored cases | 29/32 correct (90.625% accuracy), 93.18% macro precision, 90.625% macro recall |
| Ambiguous injected cases | 3, classified `unknown` |
| Intermittent-scenario detection | 3 of 4 scenario types found (100% precision, 75% recall) |
| Fingerprint normalization | 12/12 authored pairs correctly grouped or separated |

These are **synthetic** evaluation results on data the author wrote. They show the
heuristics behave as designed; they are not estimates of real-world root-cause
accuracy.
