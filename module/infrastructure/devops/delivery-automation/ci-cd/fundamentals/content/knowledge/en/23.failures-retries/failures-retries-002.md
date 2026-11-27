# Failing Fast When an Error Already Disqualifies a Change

A CI/CD pipeline can run for many minutes or hours, but not every error requires waiting until the end to draw a conclusion. If the source code does not compile, dependencies cannot be resolved, a migration is invalid, or a required check has clearly failed, downstream dependent steps typically lose their value. Continuing to run them only burns runner capacity, extends feedback time, and forces developers to wait longer to learn that their change needs fixing.

**Fail fast** is the principle of stopping early once there is strong enough evidence that a change cannot pass mandatory requirements. Pipelines should prioritize fast, decisive checks, stop work that depends on a failed result, and preserve the logs and reports needed for investigation. Failing fast must preserve failure status; it must never turn a failure into a success or skip required checks.

## 1. What problem does fail fast solve?

A typical pipeline consists of many steps: configuration validation, dependency installation, linting, compilation, unit tests, integration tests, security scans, packaging, and artifact publishing. If compilation fails yet the pipeline still runs integration tests, publishing, or deployment, many later steps will fail in a cascade for the exact same reason.

Fail fast helps:

- Shorten the time from commit to actionable feedback.
- Reduce runner minutes and compute spent on work that is no longer eligible to proceed.
- Avoid generating secondary error logs that obscure the initial root cause.
- Prevent publishing or deploying a change that already failed a mandatory gate.
- Free up queues so other changes can be validated sooner.

For example, a syntax error in a core module causes the build to fail. Continuing to run browser tests, build images, and deploy to staging does not uncover any useful additional cause. The pipeline should stop dependent steps, preserve compiler logs, and surface the first error.

However, not every failure means the entire pipeline should stop immediately. If linting, unit tests, and dependency scanning are independent checks, a team may want them all to run so developers receive broader feedback in a single pass. Fail fast should be applied according to dependency relationships and the diagnostic value of each step.

## 2. Distinguishing fail fast, fail job, and fail pipeline

These three concepts are related but not synonymous:

| Concept | Meaning | Example |
|---|---|---|
| Fail fast | Stop unnecessary work immediately upon a decisive failure | Compilation fails, so integration tests do not run |
| Fail job | A job finishes with a failed status | A unit test fails an assertion |
| Fail pipeline | Overall outcome fails to meet requirements | A required job fails or is cancelled outside policy |

One job can fail while independent jobs continue running to gather results. A pipeline can still fail overall even if several other jobs succeed. Conversely, a cancelled or skipped job must never automatically count as passing.

It helps to distinguish further:

- **Failure:** a command or check ran and did not pass.
- **Cancelled:** work was stopped by a user, timeout, newer workflow, or fail-fast.
- **Skipped:** work did not run due to conditions or unmet dependencies.
- **Success:** work ran and met its defined criteria.

Fail fast typically produces cancelled or skipped statuses on steps that are no longer needed. The final gate needs to know which job failed first, which jobs were cancelled due to dependencies, and which jobs were legitimately skipped.

## 3. Ordering the pipeline by cost and dependencies

One way to apply fail fast is to place fast, low-cost checks that can disqualify a change early in the pipeline.

Reference order:

1. Validate file formats, configuration, and pipeline syntax.
2. Check dependency manifests, lockfiles, and baseline security conditions.
3. Run linting, formatting, and static validation.
4. Perform initial compilation or build.
5. Run unit tests.
6. Verify required modules or runtime matrices.
7. Run integration tests and contract tests.
8. Run end-to-end, performance, or dedicated-environment tests.
9. Package, sign, publish artifacts, and deploy.

This order is not a rigid rule. If fast static analysis can run in parallel with compilation without resource contention, run them in parallel. If a check requires a built artifact, it must depend on a successful build.

You can model the dependency graph as follows:

~~~mermaid
flowchart TD
    A[Checkout and validate inputs] --> B[Lint and static checks]
    A --> C[Resolve dependencies]
    B --> D[Compile/build]
    C --> D
    D --> E[Unit tests]
    E --> F[Integration tests]
    F --> G[E2E and release checks]
    G --> H[Publish artifact]
    H --> I[Deploy]
~~~

If B or C fails, D and its downstream steps do not need to run. If another independent check still offers diagnostic value, it may continue according to policy.

Do not order solely by shortest runtime. A fast check that frequently emits noisy failures can halt the pipeline unnecessarily. Prioritize fast, stable, high-confidence checks capable of disqualifying a change early.

## 4. Determining which failures qualify for early stop

Not all warnings or transient errors carry the same severity. Before enabling fail fast, classify the outcomes.

| Failure group | Examples | Typical appropriate action |
|---|---|---|
| Deterministic code failure | Compile error, syntax error, assertion failure | Stop dependent steps |
| Required policy violation | Secret scan detects credential, license policy violated | Block pipeline per policy |
| Invalid input | Schema mismatch in manifest, missing required parameter | Stop before allocating resources |
| Dependency/environment transient | Registry timeout, temporary runner disconnect | Bounded retry before concluding |
| Advisory warning | Non-blocking benchmark slightly exceeds advisory threshold | Log warning and continue |
| Insufficient evidence | Missing report, telemetry unavailable | Wait, retry, or mark unverified |
| Independent failure | Lint fails while security scan still adds value | Independent check may continue |

A deterministic failure is rarely solved by retrying. Re-running compilation on the same source with the same compiler rarely fixes a syntax error. Conversely, a timeout downloading a dependency may be transient; retry according to policy before stopping the entire pipeline.

Stop conditions must be defined upfront. Never allow an arbitrary script to ignore errors just to keep the pipeline green.

## 5. Stopping dependent steps while keeping valuable independent ones

The pipeline graph shows which step needs outputs from which predecessor. When a node fails, directly or indirectly dependent nodes cannot proceed meaningfully.

For example:

- Compilation fails: do not run unit tests that need freshly compiled bytecode.
- Artifact was not produced: do not run image scans or deployments on that artifact.
- Migration validation fails: do not run application tests expecting the new schema.
- Secret scan detects a real credential: do not publish an artifact containing leaked data.
- Lint fails: an independent security scan may still run if the goal is providing broader feedback.

This differs from stopping the entire workflow whenever any job fails. If an independent job can catch another critical bug at reasonable cost, letting it finish can be worthwhile.

One design pattern is dividing the pipeline into groups:

- **Prerequisite gates:** foundational checks; failure stops dependent steps.
- **Independent diagnostics:** standalone checks that run in parallel and report separately.
- **Release gates:** mandatory checks before publishing or deploying.
- **Evidence collection:** collecting reports/logs after checks finish, even on failure.

## 6. GitHub Actions example: stopping a matrix when one configuration fails

GitHub Actions supports `strategy.fail-fast` for matrix jobs. The default value is `true`. When one job in the matrix fails, in-progress or queued jobs in the same matrix may be cancelled.

Example:

~~~yaml
name: Runtime compatibility

on:
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: true
      matrix:
        java: ['17', '21']
        os: [ubuntu-latest, windows-latest]

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: ${{ matrix.java }}

      - name: Run tests on Unix
        if: runner.os != 'Windows'
        run: ./mvnw --batch-mode verify

      - name: Run tests on Windows
        if: runner.os == 'Windows'
        run: .\mvnw.cmd --batch-mode verify
~~~

If one OS/JDK combination fails, the remaining combinations in the same matrix may be cancelled. This saves compute once the failure is already sufficient to reject the change.

However, the matrix may cancel before revealing whether the failure is isolated to a specific OS or runtime. For cross-platform compatibility bugs, that information is sometimes critical. When full results are needed, set `fail-fast: false` so every combination runs and collects reports.

Do not confuse `strategy.fail-fast` with ignoring errors. The first failing job must still cause the matrix and pipeline to reflect a failed status accurately.

## 7. When should matrix fail-fast be disabled?

There are cases where the full matrix should run even after one combination fails:

- Pinpointing exactly which runtime or OS is broken.
- Assessing blast radius across multiple architectures.
- Collecting results during a major JDK or dependency upgrade.
- Running nightly regressions for complete reporting.
- Gathering evidence for a known incident.
- Evaluating a change expected to behave differently across platforms.

Example:

~~~yaml
strategy:
  fail-fast: false
  matrix:
    java: ['17', '21']
    os: [ubuntu-latest, windows-latest]
~~~

In this mode, the pipeline consumes more resources but delivers a fuller picture. Jobs must still return their true statuses; `fail-fast: false` does not turn failures into successes.

Different policies can apply by workflow type: standard pull requests prioritize fast feedback; nightly or release qualification workflows prioritize complete matrix coverage. Document the rationale clearly so operators understand why the two workflows behave differently.

## 8. Collecting reports before a job terminates

Stopping early does not mean losing evidence. A failing test job should still upload JUnit XML files, logs, and diagnostic files before the runner exits.

Example:

~~~yaml
- name: Run tests
  run: ./mvnw --batch-mode verify

- name: Upload test reports
  if: ${{ always() }}
  uses: actions/upload-artifact@v4
  with:
    name: test-reports-${{ github.run_id }}-${{ github.run_attempt }}
    path: |
      **/target/surefire-reports/**
      **/target/failsafe-reports/**
    if-no-files-found: warn
    retention-days: 14
~~~

The upload step uses `always()` so it gets a chance to run after tests fail. The job still fails if required tests fail. Never put `continue-on-error: true` on tests just to upload reports.

For jobs cancelled immediately by fail-fast, cleanup or upload steps may not execute depending on timing and how the platform terminates jobs. Therefore:

- Stream important logs continuously where possible.
- Place collection steps right after the commands generating evidence.
- Do not rely solely on a single long final step.
- Use off-runner log stores for systems requiring durable evidence.
- Distinguish missing reports because tests never started from reports lost because the job was cancelled.

## 9. Fail fast in shell scripts

Shell scripts can keep running after a command fails unless written explicitly. A common Bash pattern:

~~~bash
set -euo pipefail

./scripts/validate-inputs.sh
./mvnw --batch-mode -DskipTests package
./mvnw --batch-mode test
~~~

- `-e` tells the shell to exit when certain commands fail, though exceptions exist inside conditionals and control structures.
- `-u` fails when referencing unset variables.
- `pipefail` preserves failures from commands inside shell pipelines.

Do not treat `set -e` as a complete error-handling mechanism. If you need to collect reports or run cleanup after a command fails, capture the exit code and return the right final status explicitly:

~~~bash
set +e
./mvnw --batch-mode verify
test_status=$?
./scripts/collect-test-reports.sh
report_status=$?
set -e

if [ "$test_status" -ne 0 ]; then
  exit "$test_status"
fi

exit "$report_status"
~~~

If the report collection step is also mandatory, capture and evaluate both exit codes. Never let a succeeding cleanup command overwrite the original test failure.

In PowerShell, inspect `$LASTEXITCODE` after native programs and explicitly exit with the appropriate code. Do not assume a subsequent PowerShell cmdlet preserves the previous process's exit code.

## 10. Fail fast in build tools and test runners

Build tools provide options to control how failures in a module or task are handled.

In the Maven reactor:

- `-ff` / `--fail-fast`: stop the reactor on the first error.
- `-fae` / `--fail-at-end`: continue independent modules that can still run, then report failure at the end.
- `-fn` / `--fail-never`: never fail the build due to reactor errors; avoid using this for required gates.

In Gradle, default behavior stops scheduling dependent tasks on error; the `--continue` option lets tasks not dependent on the failed task continue running to gather more results.

Choose the mode based on your goal:

| Goal | Suitable strategy |
|---|---|
| Pull request needing fast feedback | Stop early on prerequisites or dependent modules |
| Monorepo with independent modules | Continue independent modules for broader feedback |
| Nightly regression | Collect full results and reports |
| Release gate | Never ignore any mandatory failure |
| Environment failure debugging | Controlled reruns preserving per-attempt reports |

Read documentation for your exact build tool and test runner version. A single flag can alter the behavior of the entire reactor or task graph; do not enable it just because the name sounds right.

## 11. Failing fast without skipping mandatory checks

Fail fast decides when to stop work that is no longer meaningful; it does not alter the list of required conditions.

For example, if linting fails, integration tests depending on the build may be skipped. However, if an independent security scan is still designated as a required check, the team must decide whether to let the scan run to provide feedback or stop everything per policy. Either way, the final status must still reflect the lint failure.

Key principles:

- Never use `|| true`, `exit 0`, or `continue-on-error` to mask mandatory failures.
- Jobs cancelled by fail-fast must not be treated as passing.
- Jobs skipped due to upstream failures should be explained in the summary.
- Required gates must verify the exact required set of results.
- If a tool cannot reach a conclusion, its status is inconclusive or failed per policy.
- Only publish/deploy once all mandatory prerequisites have passed.

A green pipeline must mean every mandatory requirement has been verified. Failing fast only eliminates redundant steps; it never lowers quality standards.

## 12. Balancing fail fast with sufficient diagnostics

Stopping too aggressively on the very first error can force developers to fix issues one by one across multiple commit cycles. Running everything even after compilation fails wastes time and bloats logs without adding useful signal.

How to strike the balance:

- Stop steps that depend on missing or invalid outputs.
- Allow independent checks to proceed when they add diagnostic value.
- Use structured reports to surface multiple errors in one run.
- Cap runtime and resources for diagnostic jobs.
- Include logs, test reports, and metadata in artifacts.
- Separate fast PR workflows from full nightly suites when goals diverge.

For instance, consider a monorepo with 20 independent modules. If module A fails to compile, there is no reason to run module A's integration tests, yet modules B through T can still run linting or unit tests. Stopping the entire repository deprives unrelated teams of feedback; continuing every step of module A wastes resources.

Fail fast should apply per dependency branch rather than acting as a blanket global kill switch across every job.

## 13. Retries are not a substitute for fail fast

Retries fit transient errors capable of self-recovery, not deterministic logic errors.

| Failure type | Should retry? | Rationale |
|---|---|---|
| Compile error | No | Same source yields the same error |
| Assertion failure | Usually no | Code or test needs fixing |
| Schema validation failure | No | Input remains invalid |
| Registry timeout | Bounded | May be a temporary network issue |
| HTTP 429/503 from dependency | Controlled | Needs backoff and honoring `Retry-After` |
| Runner disconnected | Job may retry | Must verify whether job had side effects |
| Flaky test | By policy only | Must retain first result and flag as flaky |
| Deploy timeout | No blind retry | Operation may have partially completed |

A retry policy should specify max attempts, exponential backoff, jitter, timeouts, and stop conditions. Never retry non-idempotent operations without an idempotency key or state verification mechanism.

Never retry indefinitely to turn a deterministic bug into an accidental green pipeline. If the first attempt fails and a later attempt passes, retain both outcomes to investigate flaky behavior.

## 14. Cancelling stale workflows when new commits arrive

In pull request CI, a new commit renders results from an earlier workflow obsolete. Cancelling the stale workflow focuses runners on the latest source version.

GitHub Actions example:

~~~yaml
concurrency:
  group: ci-${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true
~~~

This configuration groups runs of the same workflow and pull request/ref into a concurrency group; when a new run starts, the older in-progress run can be cancelled.

Scope this carefully:

- Suitable for CI checks that can safely re-run on new commits.
- Do not apply blindly to release workflows or deployments actively mutating production.
- Never cancel a database migration or data mutation mid-flight without safety guarantees.
- Ensure cancelled status is never interpreted as passing.
- Preserve required evidence before a workflow is superseded.

Cancelling stale runs and matrix fail-fast are distinct mechanisms. One cancels an older run because newer code arrived; the other stops jobs within the same matrix when one combination fails.

## 15. Managing timeouts and avoiding hung jobs

Fail fast also relates to timeouts. A job that stops responding can tie up a runner and stall a pipeline indefinitely if unbounded.

Set timeouts according to job type:

- Linting and static checks: short.
- Compile/build: based on module size and caching.
- Unit tests: based on suite baseline duration.
- Integration/E2E: longer due to backing services.
- Performance tests: defined duration and load profile.
- Deploy: dedicated timeouts for rollout and health verification.

Timeouts must be wide enough to avoid false failures from occasional slow runners, yet short enough to reclaim resources when a job hangs. When a timeout occurs, save logs and service states where possible.

Do not treat timeouts as automatic retries. A timed-out job may have already caused partial side effects; verify current state before re-running.

## 16. Observing and measuring fail fast effectiveness

Fail fast is only beneficial if it reduces feedback time without sacrificing too much diagnostic information.

Metrics to track:

| Metric | Meaning |
|---|---|
| Time to first failure | Elapsed time from start to first decisive error |
| Time to feedback | Elapsed time until developer receives actionable results |
| Wasted runner minutes | Runner time spent on steps later cancelled or invalidated |
| Cancelled job count | Number of jobs cancelled due to fail-fast or new commits |
| Diagnostic completeness | Share of failures with sufficient reports/logs to investigate |
| Retry rate | Share of jobs or tests requiring retries |
| Flaky test rate | Share of unstable tests |
| False cancellation | Cases where cancellation discarded needed results |
| Pipeline duration | Overall duration segmented by workflow type |

If cancelled jobs spike while time to feedback fails to drop, fail-fast may be enabled at the wrong level or repeatedly cancelling valuable independent jobs. If diagnostic completeness drops, improve log and report collection before stopping jobs.

Compare metrics by workflow type and change size. Do not optimize for a single global average when nightly, pull request, and release pipelines serve different goals.

## 17. Example design: fast CI for pull requests and thorough checks for nightly

Pull requests typically prioritize quick feedback. Nightly runs can prioritize broad coverage and complete reporting.

| Workflow | Goal | Stopping approach |
|---|---|---|
| Pull request | Fast feedback on changes | Fail fast on builds and matrices where appropriate |
| Main branch | Verify merged changes | Run required gates; preserve diagnostics |
| Nightly | Detect cross-environment regressions | May disable matrix fail-fast for full results |
| Release qualification | Prove artifact is release-ready | Never skip required checks |
| Incident reproduction | Gather evidence | Run controlled test scope, retain all attempts |

Do not substitute nightly results for required checks on the current commit if artifacts, sources, or environments differ. Every result must be tied to a specific commit and run identity.

## 18. Checklist for applying fail fast

Before enabling or modifying a fail-fast policy, check:

- [ ] Prerequisites and inter-job dependencies are clearly mapped.
- [ ] Fast, stable, decisive checks are prioritized early.
- [ ] Deterministic failures are not retried pointlessly.
- [ ] Steps depending on failed outputs are stopped.
- [ ] Independent checks with diagnostic value are evaluated to continue.
- [ ] Matrix fail-fast matches the goal of fast feedback vs. complete results.
- [ ] Cancelled/skipped jobs are never treated as success.
- [ ] Reports and logs are collected when tests fail.
- [ ] Scripts preserve exit codes and do not mask failures.
- [ ] Required gates are still verified before publishing/deploying.
- [ ] Retries have caps, backoff, and idempotency conditions.
- [ ] Stale workflows are cancelled only when operations can be cancelled safely.
- [ ] Timeouts match each job type.
- [ ] Metrics exist to evaluate time to feedback and diagnostic completeness.
- [ ] Pull request, nightly, and release pipelines have tailored policies matching their goals.

Fail fast works best when a pipeline knows exactly which error disqualifies a change, which steps depend on that outcome, and what evidence must still be retained. Stopping only the work that no longer has value speeds up feedback, saves runner capacity, and ensures every required gate truthfully reflects the state of the change.
