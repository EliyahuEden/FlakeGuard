# GitHub Actions integration

FlakeGuard can pull test reports from GitHub Actions artifacts and feed results back
into a workflow summary. It never writes to GitHub.

## Synchronizing artifacts

Set `GITHUB_REPOSITORIES=owner/repository` on the server. For private repositories, set
`GITHUB_TOKEN` to a fine-grained token limited to that repository with **Actions: read**.
Public repositories can be read anonymously subject to GitHub's rate limits, although
downloading artifacts needs a token in practice. No write permission is used. Permission
requirements are documented by
[GitHub's artifact API](https://docs.github.com/en/rest/actions/artifacts).

```bash
flakeguard sync owner/repository --max-runs 20 --artifact-pattern '*playwright-json*'
```

The workspace also supports repository configuration and manual sync. Export JSON
reports into a dedicated artifact so HTML reports, metadata JSON and a second JUnit
representation are not accidentally imported. Completed runs are checked newest first;
successfully processed run attempts are skipped. Failed, missing and partially expired
imports remain visible and eligible for a later retry. Sync is synchronous and bounded
to the selected recent runs; it is not an unattended scheduler.

Upload the report from your workflow like this:

```yaml
- uses: actions/upload-artifact@v4
  if: always()
  with:
    name: playwright-json-results
    path: test-results/results.json
```

## Feedback inside a workflow

```bash
flakeguard summary 1 --output quality-summary.md
# Inside GitHub Actions:
flakeguard summary 1 --github-summary
```

See [the workflow example](../examples/github/quality-summary.yml) and the
[sample summary](evidence/sample-summary.md). Keep the test step's original exit status:
FlakeGuard never makes suspected flaky failures harmless. PR comments and scheduled
background sync are not implemented.

## Live verification

On 17 November 2026 the synchronization was exercised live against
`EliyahuEden/CommerceGuard` with a read-scope token and a local scratch database. It
downloaded the `playwright-json-results` artifact from two hosted regression runs and
imported 156 executions from each. A third run without that artifact was recorded as a
retryable error, as designed.
