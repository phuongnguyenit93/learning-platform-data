# Retaining Reports Sufficient to Diagnose Failures Beyond Just a Red Status

A red pipeline status only indicates that a step failed to complete under configured conditions. It does not answer the more important questions: **what failed, where did it happen, with which inputs, was it a product defect or an environment issue, and what evidence is needed to reproduce it?**

If CI stores only a pass/fail status and discards logs when the job ends, developers must re-run the pipeline or guess the cause. That slows down fixes and can let transient failures vanish before they are investigated. A solid testing strategy treats reports, logs, and metadata as first-class outputs of every run. These outputs must be detailed enough to pinpoint failures, linked to the commit and environment, and collected even when tests fail.

## 1. Test Status vs. Diagnostic Evidence

Status is the summary verdict of a job or pipeline. Diagnostic evidence is the data explaining why that verdict occurred.

| Information | Question answered | Examples |
|---|---|---|
| Pipeline status | Did the run satisfy its conditions? | `success`, `failure`, `cancelled` |
| Test summary | How many tests ran and what were the counts? | 240 passed, 2 failed, 3 skipped |
| Test report | Which specific test case failed? | suite name, test name, assertion, stack trace |
| Build log | Which command and stage failed? | Maven test, compiler, dependency resolution |
| Environment metadata | In what environment did the failure happen? | JDK 21, Linux x64, integration profile |
| Runtime evidence | How did backing systems behave? | service logs, database logs, container status |
| Trace or correlation ID | Which components did the failing request traverse? | trace ID, request ID |
| Source/artifact identity | Which code and artifact version does the failure belong to? | commit SHA, pipeline run ID, artifact digest |

A good report should answer at least five questions:

1. **What failed?** Specific test name, step, assertion, or operation.
2. **Where and when did it fail?** Suite, job, environment, timestamp, and duration.
3. **Which inputs were used?** Commit, configuration, dependencies, test data, and artifacts.
4. **Can it be reproduced?** Exact command, random seed, service versions, and environment conditions.
5. **Where is the evidence?** Machine-readable report, logs, traces, screenshots, or related artifacts.

Never force investigators to infer everything from one massive log file. Produce a readable summary alongside structured reports and links to detailed evidence.

## 2. Designing an Output Contract for Each Testing Stage

Every test job should publish its inputs, results, and evidence according to a consistent contract.

| Component | Contents to retain |
|---|---|
| Identity | Repository, commit SHA, pipeline run ID, job ID, attempt |
| Test scope | Suite, module, test type, selected profile or tag |
| Environment | OS, architecture, runtime, toolchain, container image |
| Dependencies | Lockfile hash, dependency versions, service image versions |
| Execution | Command executed, start/end timestamps, duration, timeout |
| Result | Total tests, passed, failed, errored, skipped, aborted |
| Failure detail | Test case, expected/actual, exception, stack trace |
| Supporting evidence | Logs, dumps, traces, screenshots, service status |
| Classification | Product defect, test defect, infrastructure, configuration, or flaky |
| Retention | Storage location, access permissions, and retention period |

Not every job produces the same set of reports. Unit tests typically need JUnit XML or equivalent; browser tests may need screenshots and video; integration tests may need database or message broker logs. Even so, jobs should share naming conventions, metadata schemas, and storage paths so investigators do not have to learn a brand-new workflow per module.

Example diagnostic directory tree:

~~~text
test-diagnostics/
├── summary/
│   ├── test-summary.md
│   └── run-metadata.json
├── reports/
│   ├── surefire/
│   ├── failsafe/
│   └── coverage/
├── logs/
│   ├── application.log
│   └── test-runner.log
└── attachments/
    ├── screenshots/
    └── thread-dumps/
~~~

This is a reference layout. Do not create empty placeholder files for inapplicable evidence types. What matters is that the report states which data was produced, which data is absent, and why.

## 3. Using Machine-Readable Report Formats

Plain-text logs help humans read linearly but are hard to aggregate reliably across jobs. Structured reports allow CI to render failed test cases, tally counts, compare history, and trigger alerts.

Common formats:

| Format | Purpose | Ecosystem examples |
|---|---|---|
| JUnit XML | Test suite and test case outcomes | JUnit, TestNG, Maven Surefire/Failsafe, many other frameworks |
| TRX | Microsoft ecosystem test outcomes | `dotnet test`, Visual Studio Test |
| JSON report | Structured outcomes with extensible metadata | Playwright, custom test runners |
| HTML report | Interactive reports for investigators | Allure, Playwright HTML |
| LCOV/Cobertura/JaCoCo XML | Code coverage data | Java, JavaScript, and coverage tools |
| SARIF | Static analysis or security scan findings | Code scanning, static analysis |

Minimal JUnit XML example:

~~~xml
<testsuite name="OrderServiceTest"
           tests="3"
           failures="1"
           errors="0"
           skipped="1"
           time="2.41">
  <testcase name="createsOrder" classname="OrderServiceTest" time="0.82"/>
  <testcase name="rejectsInvalidAddress" classname="OrderServiceTest" time="0.21">
    <failure message="expected 400 but was 500">
      AssertionError: expected status 400, actual 500
      at OrderServiceTest.rejectsInvalidAddress(OrderServiceTest.java:84)
    </failure>
  </testcase>
  <testcase name="handlesUnavailablePayment" classname="OrderServiceTest" time="0">
    <skipped message="requires payment sandbox"/>
  </testcase>
</testsuite>
~~~

From this report, the system determines that the suite contains three tests, one failed, one was skipped, and precisely which assertion broke. A red status line cannot provide that level of detail.

Distinguish `failures` and `errors` according to framework conventions. A failure is typically an assertion mismatch; an error is typically an unexpected exception or execution fault outside assertions. Exact categorization depends on the report generator, so preserve the original report and avoid guessing from raw log text.

## 4. Recording Context to Reproduce Failures

A failing test case may depend on runtime version, operating system, configuration, data, or external services. Storing only the test name is insufficient.

Metadata to attach to every run:

- Exact repository and commit SHA.
- Branch, tag, or pull request; trigger event type.
- Pipeline run ID, job ID, and attempt number.
- Workflow or pipeline definition version if separate from the source commit.
- Runner image, OS, architecture, and runtime versions.
- Compiler, package manager, and test tool versions.
- Dependency lockfile hash or dependency graph snapshot where appropriate.
- Active profiles, feature flags, and non-sensitive configuration variables.
- Image versions of databases, brokers, and backing services.
- Test suite, test filter, and exact command executed.
- Test data fixture or random seed if tests use randomness.
- Timestamp, timezone, duration, timeout, and retry count.
- Artifact digest if tests run against a packaged artifact.

Example JSON metadata:

~~~json
{
  "repository": "example/order-service",
  "commit": "a1b2c3d4",
  "pipelineRunId": "8421",
  "job": "integration-test",
  "attempt": 1,
  "runner": {
    "os": "linux",
    "architecture": "x64",
    "image": "ubuntu-24.04"
  },
  "runtime": {
    "java": "21",
    "maven": "3.9"
  },
  "test": {
    "suite": "integration",
    "profile": "ci",
    "seed": 91827
  },
  "services": {
    "postgres": "16",
    "redis": "7"
  }
}
~~~

This is an illustrative example. Populate values from the job's real environment. Never write tokens, passwords, connection strings containing credentials, or full environment variable dumps into metadata. When a setting involves a secret, log only the configuration key name or reference version.

For randomized tests, seeds enable replaying the identical input sequence. For time-dependent tests, record timestamps and timezones. For distributed tests, include trace IDs or correlation IDs to stitch logs across services.

## 5. Collecting Reports Even When Tests Fail

A common mistake is uploading reports only after tests succeed. When tests fail, the job exits early and vital evidence is discarded alongside the ephemeral runner.

Configure report collection using your platform's appropriate conditional execution. In GitHub Actions, `if: always()` runs artifact upload after prior steps succeed, fail, or are skipped, provided the job reaches that step.

Example for a Java Maven project:

~~~yaml
name: Java test diagnostics

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 25

    steps:
      - uses: actions/checkout@v4

      - name: Set up Java
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven

      - name: Run verification
        run: ./mvnw --batch-mode verify

      - name: Upload test diagnostics
        if: ${{ always() }}
        uses: actions/upload-artifact@v4
        with:
          name: test-diagnostics-${{ github.run_id }}-${{ github.run_attempt }}
          path: |
            **/target/surefire-reports/**
            **/target/failsafe-reports/**
            **/target/site/jacoco/**
            logs/test/**
          if-no-files-found: warn
          retention-days: 14
~~~

Maven Surefire normally writes unit test reports under `target/surefire-reports`; Maven Failsafe normally writes integration test reports under `target/failsafe-reports`. Actual paths may vary by module or plugin configuration. If a job fails before tests execute, missing reports are possible; `if-no-files-found: warn` distinguishes missing files from upload failures.

Place the upload step after evidence-generating steps and configure it to run on failure. If the runner crashes abruptly, is forcibly cancelled, or the platform experiences an outage, that step still might not execute. For critical systems, consider streaming logs continuously to a log store or observability platform to reduce reliance on end-of-job steps.

Never use `success()` on a diagnostic upload step when the goal is preserving evidence from failed tests. Likewise, never apply `always()` indiscriminately to privileged or side-effect-producing tasks; restrict it to collecting and archiving required evidence.

## 6. Combining Summaries, Reports, and Logs

Each type of evidence serves a distinct purpose:

- **Summary:** lets readers quickly see test counts, failing tests, and links to reports.
- **Structured report:** identifies the exact test case, status, assertion, and stack trace.
- **Execution log:** shows event ordering, executed commands, timestamps, and runtime details.
- **Service log:** explains behavior inside databases, brokers, APIs, or backing containers.
- **Trace and correlation ID:** links a single request across multiple services.
- **Attachments:** screenshots, videos, heap dumps, or thread dumps when needed by the test type.

A summary should put key facts at the top:

~~~text
Test result: FAILED
Commit: a1b2c3d4
Run: 8421 / attempt 1
Suite: integration
Duration: 06m 18s

Tests: 240
Passed: 237
Failed: 2
Errors: 0
Skipped: 1

Failed cases:
- OrderServiceTest.rejectsInvalidAddress
  Expected HTTP 400, actual HTTP 500
- PaymentFlowTest.retriesAfterGatewayTimeout
  Timed out waiting for payment status

Evidence:
- JUnit XML: test-diagnostics/reports/failsafe/
- Application log: test-diagnostics/logs/application.log
- Run metadata: test-diagnostics/summary/run-metadata.json
~~~

A summary does not replace raw reports. It gives investigators a starting point to know which file to open first. Keep summaries concise rather than pasting entire stack traces into pull request comments.

## 7. Collecting Contextual Logs Without Creating Noise

Too little logging fails to explain errors; too much logging buries signals and inflates storage costs.

Useful logs typically include:

- Consistent timestamps, ideally in UTC or with explicit timezone offsets.
- Log levels such as DEBUG, INFO, WARN, and ERROR.
- Service, module, test suite, and test case names.
- Run ID, job ID, attempt, and correlation ID.
- Clear message describing the event or error.
- Exception type and stack trace on failure.
- Duration of key operations.
- State of dependencies or backing services at the time of failure.

Structured log example:

~~~json
{
  "timestamp": "2026-11-18T08:30:12.420Z",
  "level": "ERROR",
  "service": "order-service",
  "test": "PaymentFlowTest.retriesAfterGatewayTimeout",
  "runId": "8421",
  "correlationId": "req-7f31",
  "event": "payment_status_timeout",
  "elapsedMs": 15000,
  "dependency": "payment-sandbox"
}
~~~

Never log only a bare message like `test failed`. Equally, avoid enabling DEBUG across the entire system in every pipeline if log volume explodes. Default to INFO and enable targeted DEBUG logging for the specific module or test under investigation.

When a request traverses multiple services, correlation IDs connect all related logs. In systems supporting distributed tracing, log the trace ID and link to the corresponding trace. Never generate a brand-new correlation ID at each downstream hop if you need to stitch one request flow together.

## 8. Capturing Evidence Appropriate to Each Test Type

Not every test type needs the exact same evidence bundle.

| Test type | Evidence to retain |
|---|---|
| Unit test | JUnit XML, stack trace, test output |
| Integration test | JUnit XML, application logs, service/container logs, dependency states |
| API test | Sanitized requests/responses, status codes, latency, correlation ID |
| Browser E2E | Failure screenshots, video or trace, console logs, network failures |
| Performance test | Throughput results, latency percentiles, error rate, load profile |
| Contract test | Contract mismatch reports, schemas/versions, provider/consumer details |
| Post-deploy smoke test | Deployment revision, endpoints, responses, health checks, verification timestamp |
| Static analysis | SARIF or equivalent report, rule ID, file, and line number |

For browser tests, capture screenshots on failure tagged with test name, timestamp, and run ID. Videos or traces help diagnose race conditions but consume heavy storage; enable them selectively for critical suites or failed retries.

For performance tests, never store only a pass/fail verdict. Archive load profile, virtual user counts, warm-up duration, measurement duration, input datasets, p50/p95/p99 latency, throughput, and error rate. Without load configuration, two performance reports cannot be compared meaningfully.

For post-deploy smoke tests, record deployment revision and artifact digest so you know the exact version verified. A health check result unlinked from a revision is hard to use during release investigations.

## 9. Classifying Failures to Choose the Right Action

Not every test failure is an application defect. A reporting strategy should distinguish causes based on evidence.

| Failure category | Common symptoms | Investigation direction |
|---|---|---|
| Product defect | Assertion reveals wrong behavior, reproduces reliably | Inspect code, requirements, and recent changes |
| Test defect | Broken test setup, faulty assertion, invalid fixture | Inspect test code, data, and assumptions |
| Environment/configuration | Missing variable, wrong profile, wrong permissions or endpoint | Compare configuration and environment metadata |
| Infrastructure | Runner disconnect, service unavailable, disk full | Inspect runner, network, and backing services |
| Timeout/resource | OOM, CPU throttling, exhausted pool, expired deadline | Check resource budgets and concurrency |
| Flaky test | Same commit and conditions yield unstable outcomes | Save attempts, seeds, timestamps, and traces |
| Dependency failure | Registry outage, yanked package, unresolvable dependency | Check dependency graph, repositories, and caches |

Never automatically classify every timeout as an infrastructure error. A slow endpoint may be an application regression. Check timestamps, traces, service logs, and history to isolate the cause.

When evidence is insufficient, mark the failure as unclassified or pending investigation. Mislabeling a root cause can lead teams to overlook real product bugs or waste time debugging the wrong component.

## 10. Handling Flaky Tests and Retaining Attempt History

Flaky tests can pass or fail across runs even when source code and inputs appear unchanged. Causes include race conditions, time dependencies, shared test data, execution ordering, unstable networks, or resource contention.

When retries occur, record every attempt's outcome:

| Attempt | Outcome | Duration | Seed/Context | Notes |
|---|---|---:|---|---|
| 1 | Failed | 4m 12s | seed 91827 | Timed out waiting for event |
| 2 | Passed | 3m 58s | seed 91827 | Retry succeeded |

Never record only the final `passed` status. If attempt 1 failed before a retry passed, make the instability explicitly visible. Retries can reduce temporary disruption, yet they do not prove the test is reliable.

A sound policy can:

- Cap the maximum number of retries.
- Retain reports and logs from every attempt.
- Flag tests as flaky when repeating patterns emerge.
- Track flake rates by test, module, and time.
- File remediation tasks instead of ignoring flaky tests indefinitely.
- Prevent retries from masking critical defects or mutating production data.

If quarantining a flaky test, record an owner, reason, review deadline, and scope of impact. Quarantined tests should remain visible in aggregate reporting rather than disappearing silently.

## 11. Coverage and Quality Need Context

Coverage shows which code executed during a test run, yet a percentage alone never explains whether tests actually asserted the right behavior.

Coverage reports should record:

- Tool and version that generated the report.
- Commit SHA and executed test suite.
- Line coverage, branch coverage, or project-defined metrics.
- Measured modules/packages.
- Changed files or uncovered code regions where applicable.
- Policy thresholds and comparison results.

For example, coverage dropping from 82% to 78% could reflect newly added untested code, or it could stem from altered measurement scope or a skipped suite. Inspect per-module reports alongside code diffs to interpret the shift.

Static analysis and security scan reports must also retain rule IDs, severities, files, line numbers, tool name, and ruleset version. Storing only an issue count or a red status does not give developers enough information to locate and fix violations.

## 12. Protecting Sensitive Data in Reports and Artifacts

Test reports can contain sensitive data: access tokens, passwords, connection strings, user records, emails, request bodies, or internal details. Gathering richer evidence does not mean storing raw sensitive payloads.

Apply these safeguards:

1. **Redact before saving:** strip tokens, passwords, cookies, authorization headers, and sensitive fields from logs and request/response captures.
2. **Never dump full environments:** log only non-sensitive variables needed for diagnostics.
3. **Use synthetic data:** prefer fixtures and synthetic test datasets over production data.
4. **Restrict read access:** limit artifacts containing logs or screenshots to authorized groups.
5. **Enforce retention:** keep artifacts only as long as needed for debugging and auditing, then delete per policy.
6. **Control sharing:** never attach internal logs or customer data to public pull requests.
7. **Inspect artifacts before upload:** keep configuration files and credentials out of report directories.

If a secret leaks into logs, treat it as a credential exposure incident: revoke or rotate the credential, restrict artifact access, and purge copies per procedure. Deleting a log line in the UI alone does not guarantee all cached copies are gone.

## 13. Retention and Evidence Traceability

Reports must persist long enough for investigation without being kept forever for no reason. Retention policies can vary by pipeline type:

| Run type | Reference retention policy |
|---|---|
| Standard pull request | Short retention, long enough for review and fixes |
| Main branch build | Longer retention for regression comparison |
| Release candidate | Retain reports alongside artifacts and approvals |
| Production release | Per audit requirements and organizational policy |
| Security incident | Retain per incident investigation procedures |
| Performance baseline | Retain historical data for trend comparison |

Exact periods depend on storage capacity, regulations, and operational needs. Name artifacts so they trace cleanly to run ID and attempt—for instance, `test-diagnostics-8421-1`. Internal metadata must still record commit SHA and job ID so traceability does not depend solely on filenames.

Verify that artifact uploads succeed and remain downloadable. A green upload step containing none of the required reports still fails its purpose. Log collected file counts or report manifests, and warn whenever an expected report type is missing.

## 14. Workflow for Investigating a Red Pipeline

When a pipeline fails, follow a structured sequence to cut diagnosis time:

1. **Read the summary:** identify the failing job, suite, and first failing test case; review pass/fail/skip counts.
2. **Verify identity:** confirm commit SHA, run ID, attempt, and artifact digest.
3. **Open structured reports:** inspect assertions, exceptions, stack traces, and test durations.
4. **Inspect logs around failure time:** correlate test logs with application and service logs.
5. **Check environment:** compare runtimes, dependencies, profiles, service images, and resources against the last passing run.
6. **Classify root cause:** product, test, environment, infrastructure, resource, dependency, or flaky.
7. **Reproduce under control:** use the exact commit, test filter, seed, and reproducible configuration.
8. **Record findings:** link the fix issue or pull request back to the original run and report.

Avoid blindly re-running the entire pipeline repeatedly without saving each attempt's outputs. Doing so can erase initial failure clues, especially for race conditions or load-sensitive defects.

## 15. Example: Report Structure for a Test Run

An integration test run for an ordering service might produce:

~~~text
run-8421/
├── summary/
│   ├── test-summary.md
│   └── run-metadata.json
├── reports/
│   ├── surefire/
│   │   └── TEST-OrderServiceTest.xml
│   └── failsafe/
│       └── TEST-PaymentFlowTest.xml
├── logs/
│   ├── test-runner.log
│   ├── order-service.log
│   └── postgres.log
└── traces/
    └── req-7f31.json
~~~

Suppose `PaymentFlowTest.retriesAfterGatewayTimeout` fails. The summary names the test case and duration. Failsafe XML captures the exception and stack trace. The test runner log shows the test waited 15 seconds. Application logs carry correlation ID `req-7f31`; the trace shows the request stalled inside the payment sandbox. Metadata pinpoints the exact commit, JDK, service images, and seed.

From that evidence, the team can determine whether the slowdown sits inside the backing service or inside the application's retry logic. With only a red status badge, the team would have to re-run the test and guess when the failure occurred.

## 16. Test Reporting Design Checklist

Before rolling out a reporting strategy in a pipeline, verify:

- [ ] Every test job emits a human-readable summary and structured reports.
- [ ] Reports display total, passed, failed, errored, skipped, and duration.
- [ ] Failed test cases include name, assertion or exception, and stack trace.
- [ ] Commit SHA, run ID, job ID, and attempt number are recorded.
- [ ] OS, architecture, runtime, toolchain, and necessary test configurations are captured.
- [ ] Dependency and backing service versions are identifiable.
- [ ] Randomized tests save seeds; distributed tests capture correlation/trace IDs where needed.
- [ ] Reports and logs upload even when tests fail.
- [ ] Missing mandatory reports trigger clear warnings.
- [ ] Retries preserve evidence from every attempt and never mask flaky tests.
- [ ] Screenshots, traces, dumps, or service logs are collected per test type.
- [ ] Secrets and sensitive data are redacted before storage.
- [ ] Artifacts have appropriate access controls and retention policies.
- [ ] Reports can be downloaded and traced back to the exact commit, job, and artifact.
- [ ] Investigation workflows include root-cause classification and outcome recording.

A mature test pipeline explains its final status with verifiable evidence. When summaries, reports, logs, and metadata are archived alongside commit and run identifiers, teams can locate the exact failing test, reproduce conditions, separate product defects from environment issues, and resolve regressions faster.
