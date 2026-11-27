# Step-by-Step Log Reading and Preserving Meaningful Error Messages

When a CI/CD pipeline fails, the first questions are usually: which step failed, where did the error occur, what is the likely cause, and what should be done next? If logs only contain a single line like “Command failed” or thousands of lines of context-free output, responders have to piece information together from multiple places. Investigations drag on, retries can mask the root cause, and subsequent releases become harder to reproduce when incidents occur.

Good logs help reconstruct the progression of a run across each run, job, and step. Every message needs a timestamp, context, severity level, a stable error code, and enough information to take action. When an error appears, the log should explain what failed, which component was affected, whether it can be retried, and where to find detailed evidence. Logs must also be designed so they do not expose secrets, tokens, personal data, or sensitive infrastructure details.

In the CI/CD module, logs are part of observability and release evidence. They help determine the cause of build/test/deploy failures, track retries, reconcile pipeline state, and preserve an audit trail. Logs need to be designed alongside the pipeline, rather than merely turning on console output and hoping the necessary information shows up.

## 1. What Problems Do Logs Solve in CI/CD?

A pipeline has multiple execution layers. A run may contain build, test, scan, publish, deploy, and post-deploy verification jobs; each job in turn consists of multiple steps. When an error occurs, simply knowing that the run failed is not enough.

Step-by-step logs help answer:

- Which run, commit, and artifact are being processed?
- Which job and step started, finished, or failed?
- Which command or operation was executed?
- In which environment, runner, or dependency did the step execute?
- How long did execution take and at what point was the error detected?
- Which exit code, error code, or exception was returned?
- Is this a transient error, configuration error, test failure, or unknown error?
- Which attempt is the current one and how did previous attempts end?
- Should the next step be to retry, fix configuration, reassign to an owner, or halt the release?

Logs also help distinguish application errors from infrastructure errors. For example, an integration test can fail due to a wrong assertion, an unavailable database, a DNS error, or a runner running out of disk space. Recording only “integration tests failed” leaves the recipient with no idea where to start.

## 2. Distinguishing Logs, Metrics, Traces, and Artifacts

Different types of observability evidence complement one another:

| Data type | Question answered | Example |
|---|---|---|
| Log | What happened at a specific point in time? | Dependency download step received HTTP 503 |
| Metric | How frequently or at what level does a phenomenon occur? | Job timeout rate, queue wait, build duration |
| Trace | Which components does a request or operation pass through? | Deploy request travels from pipeline to controller and cluster |
| Artifact/evidence | What detailed output or evidence is stored? | Test report, SBOM, scan report, deployment manifest |
| Event/state history | In what sequence did states transition? | Run transitioned from QUEUED to RUNNING then FAILED |

Logs do not replace metrics. One error line shows a single timeout; metrics show that timeouts are increasing across multiple runs. Logs do not replace traces when you need to follow a request across multiple services. Logs should also not be the sole place storing test reports or large file dumps; store them as separate artifacts and record the link along with the digest/ID in the log.

In CI/CD, different data types should be linked by run ID, job ID, step ID, attempt ID, commit SHA, artifact digest, and trace/correlation ID. That way, responders can navigate from a dashboard to logs, from logs to reports, and from reports to the exact artifact that was verified.

## 3. Run, Job, and Step Lifecycle Structure

A readable way to organize logs is to divide them into clear boundaries:

~~~text
Pipeline run
  ├── Job: build
  │     ├── Step: checkout-source
  │     ├── Step: resolve-dependencies
  │     └── Step: compile-and-package
  ├── Job: test
  │     ├── Step: start-test-services
  │     ├── Step: unit-tests
  │     └── Step: integration-tests
  ├── Job: security
  │     ├── Step: dependency-scan
  │     └── Step: image-scan
  └── Job: deploy
        ├── Step: verify-artifact
        ├── Step: apply-release
        └── Step: post-deploy-check
~~~

Each level needs start and end events. If a step fails, the log must identify its parent job and run. If a job is skipped because a dependency failed, clearly record the skip reason to avoid the false impression that the job ran and passed.

Step names should stay stable across runs. Display names can be human-friendly, but machine-readable IDs should not change arbitrarily because dashboards, alerts, and log queries may rely on those IDs.

## 4. Context Fields That Should Appear in Logs

Structured logs make querying and grouping events more accurate. A CI/CD log record typically needs several of the following fields:

| Field | Purpose |
|---|---|
| timestamp | Event time, preferably UTC in a standard format |
| level | Severity level such as INFO, WARN, or ERROR |
| event | Stable event name, for example step_started |
| message | Short, human-readable description |
| run_id | Pipeline run identifier |
| attempt | Current run or retry attempt |
| job_id | Job identifier |
| step_id | Step identifier |
| repository | Source repository |
| commit_sha | Checked-out/built revision |
| artifact_digest | Content identifier of the artifact if available |
| environment | Target or test environment |
| runner_id | Executing runner, if needed for investigation |
| duration_ms | Duration of the step or operation |
| error_code | Stable error code when an error occurs |
| correlation_id/trace_id | Links logs with other systems or requests |

Not every log line needs to repeat all metadata. Common context can be placed at the start of the run/job and supplemented with step-specific fields as they change. However, logs must retain enough keys so that when isolating a snippet or querying by error code, readers can still identify the source.

Data fields must have a consistent schema. Do not alternate between runId, pipeline, and execution if they all mean the same thing. Log schema changes require versioning or a compatibility plan for parsers/dashboards.

## 5. Structured Logging and Plain-Text Logs

Structured logging writes each event as a record with explicit fields, typically JSON. Free-form plain-text logs remain useful for compiler, test runner, or external tool output, but are hard to query without metadata.

Example of a JSON log record:

~~~json
{
  "timestamp": "2026-11-18T08:30:12.418Z",
  "level": "ERROR",
  "event": "step_failed",
  "message": "Integration test did not complete",
  "run_id": "build-1842",
  "attempt": 2,
  "job_id": "integration-tests",
  "step_id": "run-contract-suite",
  "commit_sha": "9f4c...e81a",
  "environment": "ci-test",
  "duration_ms": 120034,
  "error_code": "TEST_TIMEOUT",
  "retryable": false
}
~~~

The example is abbreviated; the commit value and IDs are placeholders. JSON lets systems filter by event, level, job, or error code without parsing prose sentences. The message still needs to be readable so operators can understand it quickly.

Do not turn every output into JSON by manually concatenating strings if messages may contain quotes, newlines, or special characters. Use a language's JSON encoder or a tool like jq for proper escaping. If a tool only outputs plain text, you can keep the raw output in the step log and emit structured events at the start/end boundaries.

## 6. Logging at Step Start and End Boundaries

A step should emit at least these events:

- step_started: step begins, with ID and context.
- step_progress: checkpoint or progress update for long steps.
- step_succeeded: step finishes successfully, with duration.
- step_failed: step fails, with error code, exit code, and retryability.
- step_skipped: step did not run, with the condition or dependency that caused it to be skipped.
- step_cancelled: step was cancelled, with actor or reason if known.

Example sequence:

~~~text
08:30:00Z INFO  step_started   job=build step=compile
08:30:01Z INFO  compile_progress source_files=412
08:30:18Z INFO  step_succeeded job=build step=compile duration_ms=17420
08:30:18Z INFO  step_started   job=build step=package
08:30:22Z ERROR step_failed    job=build step=package error_code=PACKAGE_OUTPUT_MISSING
~~~

There is no need to log every loop iteration or every individual file if the volume is too large. Choose useful checkpoints: start, end, processed counts, percentage milestones, or state changes. For long jobs, progress markers help distinguish slow activity from a hung job.

If a step is killed abruptly, the completion event may not be written. Dashboards should detect missing terminal events using heartbeats, timeouts, and runner state, rather than assuming the step succeeded.

## 7. Log Levels and Consistent Usage

Log levels help readers filter by importance:

| Level | When to use | Example |
|---|---|---|
| TRACE | Very deep detail for short-term debugging | Internal parser decisions |
| DEBUG | Information for investigation | Dependency cache hit/miss |
| INFO | Meaningful normal events | Build started, artifact published |
| WARN | Abnormal condition, but execution can continue | Used fallback mirror after timeout |
| ERROR | An operation or step failed | Test assertion failed, deploy gate denied |
| FATAL/CRITICAL | Component cannot continue safely | Runner agent lost unrecoverable state |

Do not use ERROR for every message just to make logs stand out. If a test case fails while the overall job still runs cleanup, the test event is ERROR; successful cleanup is INFO. If a dependency times out but a retry succeeds, the first attempt can be WARN depending on policy, while the final operation must record a successful outcome after retry.

Log levels do not replace outcomes. A WARN line does not mean the pipeline passed; an ERROR line does not necessarily mean the entire run has terminated. Dashboards need to aggregate by job state and policy.

## 8. Writing Meaningful Error Messages

A good error message helps the reader quickly answer:

1. What failed?
2. Which run/job/step or component did it happen in?
3. What is the known evidence or cause?
4. How does it impact the pipeline/release?
5. Can it be retried, and under what conditions?
6. What should the responder do next?

Weak message:

~~~text
ERROR: Something went wrong.
~~~

More useful message:

~~~text
ERROR [TEST_TIMEOUT]: Contract test suite exceeded 120 seconds.
Job: integration-tests
Step: run-contract-suite
Attempt: 2 of 2
Impact: staging deployment is blocked.
Retryable: no automatic retry; inspect the slow test and dependency health.
Evidence: test-report artifact contract-tests-1842.
~~~

The example above is a content template. When the cause is undetermined, explicitly state “undetermined” and present the known evidence. Do not write “database down” if the log only proves a single connection timed out; the cause could be network issues, pool exhaustion, DNS, or an overloaded database.

## 9. Stable Error Codes and Error Taxonomy

An error code is a machine-readable identifier for an error category. Messages may be improved over time or translated into other languages, while codes should remain stable for alerts, dashboards, and runbooks to rely on.

A taxonomy can be organized by group:

| Prefix/category | Example code | Meaning |
|---|---|---|
| SOURCE | SOURCE_CHECKOUT_FAILED | Failed to retrieve source revision |
| BUILD | COMPILATION_FAILED | Compiler exited with errors |
| TEST | TEST_ASSERTION_FAILED | Assertion did not pass |
| TEST | TEST_TIMEOUT | Test exceeded allowed duration |
| RUNNER | RUNNER_HEARTBEAT_LOST | Lost heartbeat from runner |
| DEPENDENCY | REGISTRY_RATE_LIMITED | Registry rate-limited requests |
| ARTIFACT | ARTIFACT_DIGEST_MISMATCH | Content does not match expected digest |
| POLICY | DEPLOYMENT_POLICY_DENIED | Policy disallowed the next step |
| ENVIRONMENT | TEST_DATABASE_NOT_READY | Test database is not ready |
| DEPLOY | ROLLOUT_HEALTH_CHECK_FAILED | Health gate did not pass |

This is an example taxonomy, not a mandatory list. Codes should be specific enough to support routing, yet not so granular that every message gets its own code. Do not embed dynamic values such as run ID or branch name inside an error code; put them in context fields.

When changing a code, maintain a mapping or alias during a compatibility period if alert/runbook systems still reference the old code.

## 10. Separating Cause, Symptom, and Action

A log entry should separate three layers of information:

- **Symptom:** what was observed, e.g., HTTP request timed out after 10 seconds.
- **Cause:** verified cause or hypothesis, e.g., connection pool ran out of slots.
- **Action:** what to do, e.g., check pool saturation and dependency latency.

If the cause has not been verified, record it as a suspected cause or hypothesis. Do not present a hypothesis as fact.

Example:

~~~text
Symptom: package download returned HTTP 503.
Known context: registry endpoint was registry.internal.example.
Cause: not confirmed; upstream availability is under investigation.
Action: wait for Retry-After or check registry status before retrying.
Retryable: yes, within the configured retry budget.
~~~

Error messages should not contain conclusions that go beyond the evidence. This is especially important when the pipeline automatically classifies errors and assigns owners; misclassification can route tickets to an unrelated team.

## 11. Exit Codes, Exceptions, and Command Context

When a command fails, the log should record the exit code or exception type along with the step that ran. Exit code 1 usually indicates only a generic program error; do not infer a specific cause if the tool does not provide further information.

Example:

~~~text
Step: run-unit-tests
Command: ./gradlew test
Exit code: 1
Result: test task failed
Report: build/reports/tests/test/index.html
Next action: inspect failed test cases in the report
~~~

It is not always necessary to log the full command line if arguments might contain passwords, tokens, signed URLs, or sensitive data. You can log the executable name, task, sanitized arguments, and tool version. Do not dump all environment variables to troubleshoot; doing so often exposes credentials.

For exceptions, record the error type, redacted message, stack trace when needed, and correlation ID. Avoid logging the same exception at every layer, which causes one failure to produce dozens of duplicates. Choose one layer responsible for detailed logging; other layers should add context or propagate the error.

## 12. Keeping stdout and stderr Meaningful

Many CI tools collect stdout and stderr into a single console stream. Some systems keep the two streams separate. You need to understand how the platform displays and stores them so information is not lost.

- stdout usually contains normal output, progress, and summaries.
- stderr usually contains warnings, errors, or tool diagnostics, though not every tool follows this convention.
- Exit code is the primary signal of command success/failure; do not rely solely on the presence of text on stderr.
- When redirecting or piping output, ensure the original command's exit code is preserved.
- Multi-line output needs step boundaries or prefixes to identify its source.

Example with Bash:

~~~bash
set -Eeuo pipefail

./gradlew test 2>&1 | tee test-output.log
~~~

In Bash, pipefail ensures a piped command returns an error if any command in the pipe fails rather than only taking the exit code of tee. However, verify the runner's actual shell; syntax and semantics can differ across Bash, PowerShell, and cmd.exe.

Do not use grep for the word “ERROR” as the sole criterion to conclude a job failed. A tool may print warning/error text yet exit with code 0, or fail without containing that keyword. Combine exit codes, machine-readable reports, and log context.

## 13. Example Step-Logging Wrapper in Bash

A small wrapper can record start/end events and exit codes without printing all command arguments:

~~~bash
#!/usr/bin/env bash
set -Eeuo pipefail

RUN_ID="$CI_RUN_ID"
JOB_ID="unit-tests"
STEP_ID="gradle-test"

log_event() {
  local level="$1"
  local event="$2"
  local message="$3"
  local exit_code="$4"

  jq -cn \
    --arg timestamp "$(date -u +%FT%TZ)" \
    --arg level "$level" \
    --arg event "$event" \
    --arg message "$message" \
    --arg run_id "$RUN_ID" \
    --arg job_id "$JOB_ID" \
    --arg step_id "$STEP_ID" \
    --arg exit_code "$exit_code" \
    '{
      timestamp: $timestamp,
      level: $level,
      event: $event,
      message: $message,
      run_id: $run_id,
      job_id: $job_id,
      step_id: $step_id,
      exit_code: (if $exit_code == "" then null else ($exit_code | tonumber) end)
    }'
}

log_event "INFO" "step_started" "Gradle test task started" ""

if ./gradlew test; then
  log_event "INFO" "step_succeeded" "Gradle test task passed" ""
else
  rc=$?
  log_event "ERROR" "step_failed" "Gradle test task failed" "$rc" >&2
  exit "$rc"
fi
~~~

The example requires Bash, jq, and the CI_RUN_ID variable provided by the runner. If context variables do not exist, the script should validate them and report a clear configuration error. Do not put secrets into messages or command arguments. In production implementations, you can add attempt, commit SHA, duration, and report references.

## 14. Logging Errors Without Losing the Exit Code

A common mistake is a wrapper that catches an error but then returns exit code 0, causing the pipeline to report success. Dangerous example:

~~~bash
./gradlew test || echo "Tests failed"
~~~

In a shell, a successful echo can make the command list return code 0 if the script does not explicitly return the error code. As a result, an error message appears in the log while the CI gate stays green.

Clearer approach:

~~~bash
if ./gradlew test; then
  echo "INFO: tests passed"
else
  rc=$?
  echo "ERROR: tests failed with exit code $rc" >&2
  exit "$rc"
fi
~~~

Do not use **|| true** on mandatory test/build/deploy gates just to let the pipeline keep running. If you need to collect reports or run cleanup after an error, use the CI platform's **always()**/finally mechanism or an intentional shell trap, and preserve the original failure outcome.

## 15. Logging for Retries and Backoff

When a step is retried, each attempt needs its own log entries linked back to the same operation. At a minimum, log:

- current attempt and max attempts.
- error code and error category.
- retry decision: allowed, denied, or exhausted.
- delay/backoff and Retry-After if present.
- retry start time.
- outcome of each attempt and final outcome.
- idempotency key or operation ID when applicable, without logging secrets.

Example:

~~~text
WARN retry_scheduled operation=download-dependency attempt=1 max_attempts=3
     error_code=REGISTRY_RATE_LIMITED delay_ms=2000
INFO retry_started operation=download-dependency attempt=2
INFO retry_succeeded operation=download-dependency attempt=2 duration_ms=840
~~~

Do not just log “retrying”. Investigators need to know why a retry was permitted and which attempt succeeded. If the error is a compile error or policy denied, retrying usually does not help; the log should state clearly that retry was denied because the error is not transient.

When the retry budget is exhausted, emit a final event such as **retry_exhausted** and preserve the original error code. Do not replace the root cause with a generic “max retries exceeded” message without linking the initial failure.

## 16. Logs for Timeouts and Cancellations

Timeouts must specify which layer timed out:

- Connect timeout.
- Read/response timeout.
- Command/step timeout.
- Job timeout.
- Pipeline deadline.
- External operation deadline.

Saying “operation timed out” is insufficient without knowing the deadline and how long it waited. Record timeout_ms, elapsed_ms, dependency/request ID, and the last verifiable operation state.

Cancellations need to record the actor or policy that requested cancellation, the time the request was sent, and the confirmation result. Cancelling a pipeline does not guarantee that external processes have stopped. If a runner loses connection during deployment, the state may be unknown; the log must clearly state that side effects are unverified and must not recommend blind retries.

## 17. Correlation IDs and Trace Context

A pipeline may call many systems: Git provider, artifact registry, scanner, cloud API, deployment controller, and notification service. To connect logs across them, a correlation ID or trace ID must be propagated across requests.

Identifiers should be kept distinct:

- run_id: a single pipeline run.
- attempt_id: a specific execution or retry attempt.
- job_id/step_id: a component within the pipeline.
- operation_id: a logical operation such as publishing an artifact or deploying a release.
- correlation_id: links related activities across multiple systems.
- trace_id/span_id: tracks a distributed trace according to tracing standards.

Do not use one ID to replace all others when their scopes and lifecycles differ. A run can have multiple attempts; an operation can be called again from multiple jobs; a trace can finish before the entire release completes.

If accepting a correlation ID from an external source, validate its length/format and prevent users from injecting control characters into logs. For systems using W3C Trace Context, propagate traceparent/tracestate per the standard and do not put sensitive values in baggage.

## 18. Timestamps and Durations

Timestamps should use UTC, include timezone, and follow a consistent format such as RFC 3339/ISO 8601. This helps compare logs across runners, registries, and cloud services in different timezones.

Duration should be measured using a monotonic clock within the same process when accurate execution timing is needed. System clocks can be adjusted by NTP or time changes; do not rely solely on subtracting two wall-clock timestamps for short durations.

A step record may include:

- started_at and finished_at.
- duration_ms.
- runner timezone or clock metadata if needed for investigation.
- event timestamp from the emitter and ingest timestamp from the log platform if available.

Distinguishing event time from ingest time helps detect delayed logs or skewed runner clocks. Do not order events solely by the order they appear in the UI when multiple runners write concurrently.

## 19. Keeping Error Messages Safe: Redaction and Data Minimization

Logs often contain data passing through commands, environments, and requests. Before writing or shipping logs to a centralized system, remove:

- Access tokens, API keys, passwords, and private keys.
- Authorization headers, cookies, and session tokens.
- Signed URLs or query parameters containing credentials.
- Secret environment variables and secret manager contents.
- Personal data or customer payloads unnecessary for investigation.
- Private endpoints or internal details beyond the log viewer's scope.

Do not dump the entire environment, request body, or configuration files when debugging. Do not enable shell tracing (**set -x**) in steps with secrets without reliable redaction mechanisms. String-based masking can fail if a secret is encoded, split, transformed, or appears in another URL/header.

The best practice is to avoid putting secrets on command lines or in logs in the first place. Fetch secrets through an appropriate management mechanism, pass them via controlled files/descriptors or environments, and limit their scope and lifetime. Redaction is a supplementary defense, not a reason to log sensitive data.

## 20. Log Injection and Untrusted Data

Branch names, commit messages, test outputs, file names, and responses from dependencies may be controlled by users or external systems. If concatenated directly into log text, the data may contain newlines, control characters, or strings resembling CI platform annotation commands.

Risks include:

- Forging an ERROR or SUCCESS log line.
- Creating unintended annotations/links.
- Breaking JSON or log parsers.
- Injecting sensitive content into dashboards/notifications.
- Misleading operators about the actor or outcome.

Use a structured logger/JSON encoder, enforce field length limits, and escape control characters. When using CI platform-specific annotation commands, properly encode special characters according to the platform documentation. Do not pass untrusted values into control syntax without sanitization.

## 21. Avoid Over-Logging

Logging too little starves investigations of data; logging too much increases cost, buries signals, and risks exposing information. Choose the level of detail based on step type and risk.

Should log:

- Start/end boundaries and outcome of steps.
- Tool versions, environment, and critical dependencies.
- Meaningful counts or summaries.
- Error codes, exit codes, and report references.
- Retry decisions and attempt history.
- State changes or release decisions.

Avoid:

- Printing every loop iteration or every file when it adds no investigative value.
- Dumping the entire environment or configuration.
- Printing full requests/responses containing customer data.
- Repeating the same stack trace across multiple layers.
- Logging sensitive information merely for debugging convenience.

For large outputs such as compiler logs, test reports, or scanner reports, keep the file as an artifact with appropriate retention. Console logs only need a summary, storage location, and ID/digest for retrieval.

## 22. Step Groups, Annotations, and Summaries

Pipeline logs should be easy to scan. Output can be grouped by job/step, warnings/errors can be highlighted, and a summary can be generated at the end of the run.

A good summary should include:

- Total counts of passed, failed, and skipped jobs/steps.
- The first failed step and subsequent failures.
- Error code and brief message.
- Attempt/retry count.
- Links to reports/artifacts.
- Blocked steps or undeployed environments.
- Next action or owner if determined by the system.

Do not just put “Pipeline failed” at the end. A summary should help viewers quickly locate the failing step without reading the entire log from the beginning. However, summaries do not replace raw logs; links to details must be provided.

When using colors or annotations, clear text must still be present to support non-color terminals, screen readers, and archival systems. Do not rely on red/green color as the sole signal.

## 23. Example Workflow Retaining Step-by-Step Logs

The GitHub Actions example below illustrates naming steps, retaining test reports, and generating a summary upon failure:

~~~yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout source
        id: checkout
        uses: actions/checkout@v4

      - name: Record build context
        id: context
        run: |
          echo "run_id=$GITHUB_RUN_ID"
          echo "attempt=$GITHUB_RUN_ATTEMPT"
          echo "commit_sha=$(git rev-parse HEAD)"

      - name: Run unit tests
        id: unit-tests
        run: ./gradlew test

      - name: Upload test report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: unit-test-report
          path: build/reports/tests/test/
          if-no-files-found: warn

      - name: Write failure summary
        if: failure()
        run: |
          {
            echo "## Unit test job failed"
            echo ""
            echo "- Run: $GITHUB_RUN_ID"
            echo "- Attempt: $GITHUB_RUN_ATTEMPT"
            echo "- Commit: $(git rev-parse HEAD)"
            echo "- Report: unit-test-report artifact"
          } >> "$GITHUB_STEP_SUMMARY"
~~~

This is an illustrative example; actions should be pinned by commit SHA if repository policy requires it. Do not write secrets to step outputs or summaries. Step context should record only non-sensitive metadata; test reports are stored separately with access controlled by artifact policy.

The **always()** condition ensures the report is uploaded after tests fail, while **failure()** creates a summary when the job encounters an error. For complex pipelines, pay attention to job dependency, cancellation, and timeout semantics; a cleanup/upload step can still be cancelled if the entire workflow is cancelled or the runner disconnects.

## 24. Analyzing Logs in Investigative Order

When a job fails, read logs in the following order:

1. Identify run ID, attempt, commit SHA, and environment.
2. Check the summary to identify the failing job/step.
3. Open the failing step's log and identify the error code/exit code.
4. Read the events immediately preceding the error for context.
5. Check related dependencies or upstream steps.
6. Cross-reference test reports, scanner reports, or artifact evidence.
7. Check retry history to see if the error repeats in the same pattern.
8. Determine whether the error is transient, deterministic, policy-related, or unknown.
9. Choose the next action and owner based on the evidence.
10. Document investigation findings and link to runbooks/tickets if needed.

Reading backward from the last error line is sometimes helpful, but do not stop at the last line. Root causes often appear earlier: an unavailable dependency, an ignored warning, or a misresolved configuration.

## 25. Example: Dependency Download Failure

Log without sufficient context:

~~~text
Download failed.
~~~

More useful log:

~~~text
timestamp=2026-11-18T08:32:10Z
level=WARN
event=dependency_download_retryable
run_id=build-1842
job_id=build
step_id=resolve-dependencies
dependency=org.example:library:2.4.1
http_status=503
attempt=1
max_attempts=3
retry_after_ms=2000
error_code=REGISTRY_UNAVAILABLE
~~~

If the next attempt succeeds, log a retry succeeded event and the final outcome. If the retry budget is exhausted, log **retry_exhausted**, preserving the dependency coordinates and authorized registry host. Do not log credentials or full URLs containing tokens.

For a 404 error due to a non-existent version, retrying usually will not help. Error classification should indicate this may be a dependency declaration or repository configuration issue, rather than continuing to retry under the same policy.

## 26. Example: Test Failure Due to Assertion

A good message should specify which test failed, what was expected, and what actually occurred, while linking to the report:

~~~text
ERROR [TEST_ASSERTION_FAILED]
Test: OrderPricingTest.appliesDiscountForEligibleCustomer
Expected: total = 90000 VND
Actual: total = 100000 VND
Job: unit-tests
Step: gradle-test
Attempt: 1
Retryable: no automatic retry; deterministic assertion failure
Evidence: unit-test-report artifact
~~~

In production systems, only log business values if they do not contain personal data or sensitive information. If test fixtures contain real customer data, replace them with synthetic identifiers or redacted values.

Do not automatically retry a deterministic assertion multiple times just to wait for the test to pass. If a test is flaky, record its flaky status, reproduction count, and environment separately; do not treat a passing retry as proof that the code is stable.

## 27. Logs for Deployment and Post-Deploy Verification

Deployment logs must link the verified artifact to the target environment:

- service and release ID.
- artifact URI and digest.
- environment, region/cluster/namespace.
- deployment controller request ID.
- rollout strategy and current step/cohort.
- expected replica/instance count.
- health gates and individual probe results.
- expected digest and actual runtime digest.
- start/end timestamps, duration, and actor.

If the deploy API times out, log the request ID and state that the status is unverified. Do not log “deploy failed” if it is unknown whether the controller applied side effects. When the runtime digest differs from the expected digest, log an error code such as **RUNTIME_ARTIFACT_MISMATCH** and block the next promotion step.

Post-deploy logs should separately record smoke tests, readiness, error rate/latency gates, and runtime verification results. A deploy command exit code of 0 does not replace post-deployment verification.

## 28. Log Retention, Access, and Integrity

Logs can contain internal information and serve as investigative evidence. Log policies need to define:

- Retention periods by log type: console, audit, debug, and security events.
- Viewing permissions by repository, service, environment, and incident role.
- Encryption in transit and at rest.
- How to redact or delete sensitive data as required.
- Size limits, chunking, and handling of truncated logs.
- Long-term storage for release evidence needed across rollback/audit windows.
- Auditing access to or exports of sensitive logs when required.

Do not retain debug logs indefinitely just because storage is cheap. Conversely, do not delete release evidence before the period needed for investigation, rollback, or compliance expires. Retention should be based on purpose and sensitivity.

For critical evidence, store the digest of the report/log bundle in the release record to detect file tampering. Digests verify content; access permissions and publishing provenance still need to be controlled separately.

## 29. Handling Missing, Delayed, or Truncated Logs

Logs can be incomplete because a runner disconnected, an agent was killed, output exceeded platform limits, or artifact upload failed. Collection status should be explicitly recorded:

- **complete:** logs were collected completely within defined limits.
- **partial:** some logs exist, but segments or terminal events are missing.
- **truncated:** logs exceeded limits and were cut off.
- **unavailable:** logs could not be retrieved.
- **delayed:** logs arrived late relative to event time.

Do not interpret “no errors seen in logs” as “no errors occurred” if logs are partial or truncated. Dashboards should prominently warn about evidence quality.

For large outputs, split into chunks with sequence numbers, step ID, and timestamp. If report upload fails, log a separate error and preserve the local path if the runner is still alive. If the runner is lost, state must reflect that evidence is incomplete.

## 30. Common Anti-Patterns

| Anti-pattern | Consequence | Improvement |
|---|---|---|
| Logging only “Step failed” | Unknown where it failed or what to do next | Add step ID, error code, exit code, and next action |
| Relying only on console text | Hard to query and group errors | Structured events for boundaries and outcomes |
| Using ERROR for every line | Noisy alerts, hard to find real failures | Enforce log level conventions |
| Logging the entire environment | May expose tokens/passwords | Allowlist only required fields |
| Enabling shell tracing with secrets | Secrets appear in logs | Avoid tracing or use verified protection mechanisms |
| Catching errors then returning exit code 0 | False-green pipeline | Propagate exit code and preserve failure outcome |
| Retrying without logging attempts | Unknown initial error and which attempt succeeded | Log attempt, delay, reason, and outcome |
| Logging hypotheses as confirmed causes | Misleads investigation | Distinguish symptom, known cause, and hypothesis |
| Printing entire reports to console | Huge, unreadable, and costly logs | Store as artifact, log summary and link |
| Missing correlation IDs | Hard to correlate logs across systems | Propagate run/operation/trace context |
| Using timestamps without timezone | Hard to reconcile across multiple runners | Use UTC and standard formatting |
| Logging untrusted data directly | Log injection or broken parsers | Use structured encoders and sanitization |
| Not flagging partial/truncated logs | Readers trust incomplete evidence | Attach collection status |
| Using grep “ERROR” as a gate | False positives/negatives | Rely on exit codes and structured reports |

## 31. Pipeline Log Design Checklist

Before putting a pipeline into production, verify:

- [ ] Runs, jobs, and steps have stable IDs and clear names.
- [ ] Start/end events and skipped/cancelled statuses are emitted as needed.
- [ ] Logs include UTC timestamps and durations.
- [ ] Run ID, attempt, job ID, step ID, and commit SHA are present.
- [ ] Artifact digest and environment are logged during publish/deploy steps.
- [ ] Logs use consistent levels, event names, and schemas.
- [ ] Error codes are stable and contain no dynamic values.
- [ ] Messages distinguish symptoms, verified causes, and next actions.
- [ ] Exit codes/exceptions are preserved and propagated properly.
- [ ] Retry logs include attempt, max attempts, delay, reason, and final outcome.
- [ ] Timeouts/cancellations specify the layer and side-effect status.
- [ ] Correlation/trace IDs link related systems.
- [ ] Secrets, tokens, cookies, and personal data are excluded from logs.
- [ ] Untrusted inputs are escaped before logging or creating annotations.
- [ ] Large outputs are stored as artifacts with links and appropriate retention.
- [ ] Summaries help locate failing steps and detailed evidence.
- [ ] Partial/truncated/unavailable logs are clearly marked.
- [ ] Access permissions, encryption, and retention are configured.
- [ ] Behavior has been tested for runner disconnection or log upload failure.

## 32. Conclusion

Step-by-step log reading enables teams to pinpoint exactly where a pipeline started, progressed, failed, or was interrupted. Structured logs, stable IDs, UTC timestamps, error codes, and correlation context connect a failure to its associated run, job, commit, artifact, and environment. Meaningful error messages must describe what is known, the impact, retryability, and the next action without asserting unverified causes.

Log design must preserve exit codes, record attempts and retry decisions, distinguish timeouts from cancellations, protect secrets, and flag missing or truncated evidence. When logs are linked with metrics, traces, test reports, and deployment records, pipelines become easier to investigate and release decisions can rest on clear evidence.
