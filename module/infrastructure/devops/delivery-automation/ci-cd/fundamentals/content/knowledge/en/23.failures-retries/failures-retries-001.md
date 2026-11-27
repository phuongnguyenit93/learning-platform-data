# Classifying Source, Test, Infrastructure, and Configuration Failures

A failed CI/CD pipeline does not always mean the new source code has a bug. A build may stop because the compiler detected an error; tests may fail due to a regression or unstable test data; a runner may run out of disk space; a registry may be temporarily unreachable; or environment configuration may be missing a required variable or pointing to the wrong service. If the team simply looks at the red X on the pipeline and retries the entire job, it can waste time, obscure the root cause, and increase load on an already struggling system.

To handle failures effectively, you must first **classify failures by their domain of origin and observable evidence**. This lesson focuses on four main categories: source failures, test failures, infrastructure failures, and configuration failures. It then connects that classification to the decision to fix code, fix tests, recover runners, adjust configuration, or apply bounded retries.

The goal is not to slap a label on every failure as fast as possible. The goal is to determine what broke, whether the failure is reproducible, whether it can be retried safely, who owns the resolution, and what evidence needs to be preserved to prevent the same incident from recurring.

## 1. Why classify failures before retrying?

A retry re-runs a step or job after a failure. It is useful when the cause is transient, such as a network reset or a temporarily overloaded registry service. However, retrying cannot fix logic bugs, wrong assertions, missing configuration, or denied permissions.

If the wrong type of failure is retried, several problems can occur:

- A code bug gets masked by a lucky run that happens not to hit the failing branch.
- A flaky test keeps flipping the pipeline between green and red, eroding the team's trust in results.
- A runner with low disk space continues picking up jobs and causes many other pipelines to fail.
- An invalid secret or endpoint gets retried repeatedly without any chance of fixing itself.
- An overloaded dependent service receives extra requests from multiple jobs retrying simultaneously.
- Evidence from the first run gets overwritten by logs from subsequent runs.

A sound handling workflow typically follows this order:

1. Collect the error, exit code, logs, test reports, and runner status.
2. Identify the failing step and when it started.
3. Classify the domain of origin: source, test, infrastructure, or configuration.
4. Check reproducibility and correlate with the most recent changes.
5. Decide whether to fix the cause, apply a conditional retry, or escalate to an owner.
6. Re-run only the scope needed for verification and record the outcome.

~~~mermaid
flowchart TD
    A["Pipeline fails"] --> B["Collect logs, exit code, report"]
    B --> C["Identify failing job and step"]
    C --> D{"Evidence of transient infrastructure failure?"}
    D -- "Yes" --> E["Bounded retry / check runner"]
    D -- "No" --> F{"Failure consistently reproducible?"}
    F -- "Yes" --> G{"Domain of origin"}
    G -- "Source" --> H["Fix code or dependency"]
    G -- "Test" --> I["Fix product or test"]
    G -- "Configuration" --> J["Fix config / permissions / secret"]
    F -- "Unclear" --> K["Collect more evidence"]
    K --> G
    E --> L["Verify result after remediation"]
    H --> L
    I --> L
    J --> L
    L --> M["Record cause and outcome"]
~~~

Do not conclude the cause from just the last log line. The last line may be where the process stopped, not where the failure began. Look for the first meaningful error in the event chain and inspect cascading causes.

## 2. The four primary failure domains

The four categories in this lesson provide a practical classification model for CI/CD. A single incident can span multiple domains. For example, a misconfiguration prevents the application from connecting to the database, which then causes an integration test to fail. In that case, the observed failure is in tests, while the root cause belongs to configuration.

| Failure domain | Nature | Common symptoms | Primary action |
|---|---|---|---|
| Source | Code, dependency, or build logic fails to meet requirements | Compile error, static analysis, assertion, consistently reproducible exception | Fix code, dependency, or build definition |
| Test | Test, fixture, data, or test environment has an issue | Flaky, random timeout, test order dependency, broken fixture | Verify test, fix fixture, or fix product |
| Infrastructure | Runner, network, storage, registry, or platform service is unavailable | Runner offline, disk full, 5xx from service, DNS/network error | Restore infrastructure or retry transient failure |
| Configuration | Environment values, permissions, secrets, or parameters are wrong/missing | Missing variable, invalid URL, permission denied, wrong endpoint | Fix configuration source and re-validate |

Distinguish between **symptom** and **root cause**:

- A test timing out is a symptom. The cause could be slow code, an overloaded runner, an unresponsive test database, or a timeout configured too low.
- A deployment reporting unauthorized is a symptom. The cause could be an expired token, a role lacking permissions, or a job using the wrong identity.
- A build failing to download a dependency is a symptom. The cause could be a broken registry, wrong proxy, expired credential, or a non-existent dependency version.

When classifying, record both the observed failure domain and the root cause once identified. If evidence is insufficient, mark it as unknown rather than guessing.

## 3. Source failures

Source failures occur when application code, dependencies, or build logic are invalid or fail to satisfy application requirements.

### 3.1. Identifying signs

Common signs include:

- The compiler reports syntax, type, or missing symbol errors.
- A linter or static analyzer detects rule violations.
- Unit tests fail consistently after a code change.
- A build task cannot produce output due to incompatible build configuration or source code.
- The application throws an exception when executing a specific code path.
- A new dependency introduces a version conflict or breaking API change.
- A security scanner flags an issue traceable to code or a dependency.

A source failure is usually reproducible given the same commit, toolchain, and inputs. However, race conditions, concurrency bugs, or time-dependent logic can cause intermittent failures. Do not assume a failure that does not reproduce immediately is an infrastructure issue.

### 3.2. Investigation approach

1. Identify the commit SHA and associated changes.
2. Read the first error from the compiler, analyzer, or runtime stack trace.
3. Re-run the exact build/test command in an equivalent environment.
4. Compare against the previous commit or the last known good run.
5. Inspect dependency lockfiles, compiler versions, and build tool versions.
6. Narrow down to the failing module, file, or task.
7. Fix the root cause and re-run targeted checks, then run the required test suite.

Example compile error:

~~~text
src/main/java/example/OrderService.java:42: error: cannot find symbol
    paymentClient.authorize(order);
                 ^
  symbol:   method authorize(Order)
  location: variable paymentClient of type PaymentClient
~~~

This message indicates the code calls a method that does not exist on the `PaymentClient` type used by the compiler. Retrying the build will not change the outcome. Check the dependency API, library version, or renamed method.

### 3.3. Dependencies and build definitions

Not all build failures live inside application source files. Changes to dependencies, plugins, compiler options, or build scripts are also code changes that can break builds.

Check the following:

- Are dependencies declared and version-pinned?
- Did the lockfile or dependency constraints change?
- Does the repository provide the expected package/version?
- Is the plugin compatible with the runtime/build tool version?
- Does the build rely on undeclared files or environment variables?
- Was the artifact built from the right commit and toolchain?

If a package does not exist or versions are incompatible, retrying will not help. If the registry is temporarily unreachable, that may be an infrastructure failure where a bounded retry is appropriate.

### 3.4. When not to retry source failures

Do not retry to work around:

- Consistently reproducible compile errors.
- Static analysis violations with clear evidence.
- Unit test assertion failures caused by wrong actual results.
- Non-existent or incompatible dependency versions.
- Logic bugs in build scripts.
- Security gate findings that require remediation or review.

You may re-run after code or dependencies have changed. That is verifying a fix, not retrying the exact same input.

## 4. Test failures

Test failures require the most careful analysis because tests may catch real product defects, yet the test itself or the test environment can also be unstable.

### 4.1. Distinguishing test failures from test infrastructure failures

A **test failure** occurs when the test executes properly but the actual outcome does not match expectations. For example, an order total is calculated incorrectly, or an unauthorized user can still read data.

A **test infrastructure failure** occurs when tests cannot execute reliably because the test database fails to start, the container registry is unreachable, the runner runs out of resources, or a mock service crashes.

Some indicators:

| Symptom | Likely cause | Check |
|---|---|---|
| Assertion fails with the same value | Regression or outdated test expectation | Verify requirements and code changes |
| Same test passes sometimes and fails other times | Flaky test, race condition, or fluctuating environment | Run controlled repetitions; inspect ordering and resources |
| Multiple tests time out together | Runner or test dependency overloaded | Check CPU, memory, network, and service health |
| Fails only when running in parallel | Shared state, port, or shared data | Check isolation and cleanup |
| Test cannot find fixture | Wrong path, test artifact, or setup | Check working directory and setup steps |
| Snapshot changes unexpectedly | Output changed or snapshot outdated | Review diff; do not update snapshots blindly |

### 4.2. Flaky tests

A flaky test is a test that produces different results across runs with the same input and no corresponding change in the product or expectations.

Common causes:

- Dependency on wall-clock time or timezone.
- Using fixed sleeps instead of waiting for conditions.
- Race conditions and concurrency bugs.
- Shared test data across tests.
- Execution order affecting outcomes.
- Contention over ports or temporary files.
- Calls to unstable external services.
- Tests failing to clean up resources after running.

Do not simply increase test retry counts to force the pipeline green. Retries may help confirm instability, but they do not eliminate the cause. Flaky tests must be tracked, assigned an owner, and scheduled for fixing.

### 4.3. Flaky test verification workflow

1. Record the test name, seed, timestamp, runner, and commit.
2. Run the test in isolation to check reproducibility.
3. Run it multiple times with the same configuration and seed if the framework supports it.
4. Run the full suite to detect order dependencies.
5. Run in parallel and sequentially to compare behavior.
6. Inspect clock, timezone, network, fixtures, and shared state.
7. Fix the test or product code if a real race condition is uncovered.
8. If temporarily quarantined, record the owner, reason, expiration date, and compensating checks.

Quarantining does not mean removing the test from release quality standards. If a test protects critical functionality, alternative verification must be in place while it is being resolved.

### 4.4. Distinguishing test timeouts from test assertions

A timeout can be a product, test, or infrastructure issue. Identify what the test is waiting on:

- Waiting on HTTP response: inspect the server, dependencies, and network.
- Waiting on database lock: inspect transactions, connection pools, and shared data.
- Waiting on message: inspect producer, consumer, queue, and test setup.
- Waiting on UI element: inspect application behavior, selectors, and UI synchronization.
- Waiting on job: inspect workers, queue lag, and deadlines.

An assertion failure typically means a condition was evaluated and found false. A timeout typically means a condition was not reached within the allowed time. These two require different investigation paths.

## 5. Infrastructure failures

Infrastructure failures originate from the pipeline execution environment or underlying platform services that a job depends on.

### 5.1. Common failure modes

- Runner offline, terminated, or disconnected.
- Disk full, inode exhaustion, or workspace out of space.
- CPU/memory exhaustion, processes killed by OOM.
- DNS, proxy, firewall, or network routing errors.
- Package registry, artifact store, or container registry unavailable.
- Cloud provider or CI platform APIs returning 5xx or rate limits.
- Test database, message broker, or backing service failing to start.
- Expired certificates or clock skew on the runner.
- Container image pull failures due to registry or network issues.

### 5.2. Identifying signs

| Symptom | Likely infrastructure domain | Evidence to collect |
|---|---|---|
| Job disappears mid-run with no test report | Runner/host terminated | Runner events, host status, termination reason |
| No space left on device | Storage | Disk usage, inode count, workspace size |
| Exit 137 or OOMKilled | Memory/container limit | Memory metrics, kernel/container events |
| DNS lookup timeout | DNS/network | Resolver logs, DNS queries, network traces |
| HTTP 429 or 503 from registry | Rate limit/service availability | Response headers, status codes, service status |
| Multiple repositories fail simultaneously | Shared infrastructure/dependency | Blast radius across runners/regions/services |
| Only one runner pool fails | Runner image or pool config | Image version, pool health, node events |

Simultaneous failures across multiple repositories may suggest a shared incident, but still verify. A broadly rolled-out library update or credential change can also cause multiple pipelines to fail at the same time.

### 5.3. Verification before retrying

Before retrying an infrastructure failure, check:

- Has the dependent service recovered?
- Is the new runner healthy and sufficiently provisioned?
- Could the previous request have already been processed by the server even though the client lost the response?
- Will retrying add load to an already overloaded service?
- Are there rate limits or `Retry-After` headers to honor?
- Should the job move to a different runner pool or region?

If a runner is unhealthy, re-running on the same runner may reproduce the failure. Provision a clean runner or restore the pool first.

## 6. Configuration failures

Configuration failures occur when values or rules supplied to a job or application do not match what the environment requires.

### 6.1. Types of configuration failures

- Missing required environment variables.
- Misspelled variable names or wrong data types.
- Incorrect URL, hostname, port, or namespace.
- Configuration accidentally pointing staging to production or vice versa.
- Expired, revoked, or mis-scoped secrets.
- Token with the right identity but insufficient permissions.
- Invalid combinations of feature flags or build profiles.
- Config file not mounted or malformed.
- Precedence order causing defaults to override environment values.
- Direct configuration edits introducing configuration drift.

### 6.2. Symptoms and inspection steps

| Symptom | Possible cause | Inspection step |
|---|---|---|
| Missing required variable | Not declared in pipeline/environment | Check variable name and scope |
| Invalid URL/port | Malformed value or wrong environment | Validate against schema and allowlist |
| Unauthorized/forbidden | Token missing scope or role | Verify identity, permissions, and audience |
| Secret not found | Wrong secret reference or environment | Check secret name/version and read permissions |
| Certificate verify failed | Wrong/expired CA bundle, hostname, or certificate | Check trust chain and system clock |
| Connected to wrong service | Wrong precedence or endpoint | Log the source of the effective value without printing secrets |
| Passes locally but fails in CI | Different runtime, env vars, filesystem, or permissions | Compare redacted configuration and toolchain |

### 6.3. Safely verifying configuration and secrets

Do not dump the entire environment or raw secrets for debugging. You may log:

- The name of the missing property.
- Which configuration source was selected.
- The configuration version or revision.
- The secret reference and access status, without logging the value.
- The identity, role, or scope used.
- Validation results.

If secret exposure is suspected, revoke or rotate it immediately and assess the blast radius. Retrying with an expired secret cannot resolve the issue.

## 7. Classifying by retryability

Once the failure domain is identified, evaluate retryability. The domain alone is not absolute: an infrastructure error can be permanent due to a wrong network configuration; a test error can be transient because a test database is still starting up.

| Failure type | Retry same input? | Recommended action |
|---|---|---|
| Compile error | No | Fix source or dependency |
| Consistent assertion failure | No | Investigate regression or test expectation |
| Flaky test | Controlled verification only | Track as flaky, find race, fix test/product |
| Runner terminated | Yes, after using a healthy runner | Collect runner events, provision new runner |
| Transient network reset | Bounded | Backoff, jitter, and timeout |
| Registry returns 429 | Policy-based | Honor `Retry-After` and retry budget |
| Permission denied | No | Fix identity, role, or policy |
| Missing configuration | No | Add and validate configuration |
| Expired secret | No with old secret | Rotate or issue new credential |
| Artifact digest mismatch | No | Stop pipeline, verify source and integrity |
| Dependency service 5xx | Conditional | Bounded retry, circuit breaker if appropriate |
| Quota or capacity exhausted | Do not retry aggressively | Wait for capacity, lower concurrency, or increase quota |

Distinguish three decisions:

- **Retry:** re-run the same operation because the failure is assessed as transient and the operation is safe to repeat.
- **Fix and rerun:** fix the root cause and re-run to verify.
- **Escalate/hold:** stop the pipeline, preserve evidence, and hand off to the owner when information is insufficient or risk is high.

## 8. Designing bounded retries

Retries should only be applied to operations likely to succeed on a subsequent attempt. Every retry policy needs a maximum attempt count, overall timeout, wait interval, and explicit list of retryable failure types.

### 8.1. Exponential backoff

Exponential backoff increases wait intervals with each attempt. A simple form is:

\[
d_n = \min(d_{\max}, d_0 \times 2^n)
\]

Where:

- \(d_0\): initial wait interval.
- \(n\): number of retries already performed.
- \(d_{\max}\): maximum wait cap.

For example, wait intervals can grow from 1 second to 2, 4, and 8 seconds before capping at the maximum. Actual values depend on service latency and rate limits.

### 8.2. Jitter

If many jobs retry on the exact same schedule, they can create synchronized request spikes and overload the service further. Jitter adds randomness to the wait interval to spread out requests.

A common approach is full jitter:

\[
d_n = U(0,\min(d_{\max},d_0 \times 2^n))
\]

Where \(U(0,x)\) is a random value between 0 and \(x\).

For HTTP 429 or 503 responses, if the server returns `Retry-After`, the client should honor that guidance within its configured timeout and policy limits.

### 8.3. Retry budget

A retry budget limits total retries over a time window or as a ratio of original requests. If every request retries multiple times, a minor incident can escalate into a retry storm.

You can cap:

- Maximum N retries per request/job.
- Maximum retry ratio over total requests.
- Total retry duration for a job.
- Number of concurrent jobs retrying against one dependency.
- Number of manual reruns within a time window.

Retry budgets help systems fail gracefully and protect dependent services.

### 8.4. Do not retry unrecoverable errors

Errors such as syntax errors, missing variables, permission denied, invalid artifacts, or wrong assertions do not disappear on their own. Retrying them only generates noise and extra load.

Classify error codes or response statuses according to the tool's documentation. Do not retry all HTTP 4xx/5xx codes uniformly: 429 may be retried after waiting; 401 may require fresh credentials; 403 usually requires permissions; 404 may indicate a wrong resource or eventual consistency depending on the API.

## 9. Timeouts, idempotency, and safe retry operations

A timeout limits how long the client waits, but it does not prove the server stopped executing the operation. A deploy API might have applied the change right before the response was lost. If the client retries a non-idempotent command, the system may create duplicate resources or releases.

Before retrying a mutating operation:

1. Determine whether the request reached the server.
2. Query the current state.
3. Use an idempotency key or stable release ID if supported by the API.
4. Resubmit only if you can prove the operation has not completed or the API guarantees idempotency.
5. Enforce an overall timeout across all attempts.

Example:

~~~text
request_id = release-2026-11-18-01
attempt 1: apply request_id
response: connection reset
query status by request_id
if status == SUCCEEDED:
    do not submit again
if status == RUNNING:
    continue polling
if status == NOT_FOUND and API guarantees idempotency:
    retry with the same request_id
otherwise:
    stop and investigate
~~~

Do not generate a new idempotency key for every retry attempt if the goal is to identify the same logical operation. If each attempt carries a different key, the server may treat them as separate operations.

## 10. Circuit breakers and limiting dependency pressure

A circuit breaker temporarily pauses calls to a dependency when failure rates or timeouts exceed a defined threshold. It is useful when a dependent service is experiencing a prolonged outage and repeated retries would worsen the situation.

Three common states:

- **Closed:** requests are allowed through; the system tracks failures.
- **Open:** requests to the dependency are blocked temporarily for a cooldown period.
- **Half-open:** a limited number of probe requests are allowed to determine whether the dependency has recovered.

~~~mermaid
stateDiagram-v2
    [*] --> Closed
    Closed --> Open: Errors exceed threshold
    Open --> HalfOpen: Wait timeout expired
    HalfOpen --> Closed: Probe succeeded
    HalfOpen --> Open: Probe failed
~~~

Circuit breakers typically live inside applications or service clients, while retry policies may sit at the client, job, or pipeline layer. Both mechanisms must coordinate. If the circuit is open, continuous retries from multiple jobs are usually counterproductive.

Do not use circuit breakers to hide broken dependencies. Emit metrics for breaker state, rejected request count, open duration, and probe outcomes.

## 11. Handling test and infrastructure failures in CI

Pipelines should separate test results from the health of runners and test services.

Recommended practices:

- Preserve JUnit/XML reports, coverage, and logs even when tests fail.
- Record test name, seed, timestamp, runner image, runtime, and commit SHA.
- Collect container/backing service status when integration tests fail.
- Separate fast test suites from suites requiring heavy infrastructure.
- Use service containers or isolated test environments where appropriate.
- Clean up databases, queues, files, and containers after test runs.
- Limit concurrency to avoid overloading runners or test dependencies.
- Re-run only failed tests by policy rather than defaulting to re-running the entire suite.

### 11.1. Re-running failed tests

Some platforms support re-running failed jobs or test retries. Always preserve both the initial result and the retry results. If the first run fails and the retry passes, the overall record must not erase history; mark it as flaky or intermittent and generate data for investigation.

For tests protecting security, authorization, or data integrity, do not allow a passing retry to automatically clear the first failure alert without review.

### 11.2. Checking runners before blaming code

When multiple unrelated tests time out together, inspect the runner:

- CPU throttling and memory pressure.
- Disk space, inodes, and workspace usage.
- Leftover processes from previous jobs.
- DNS, proxy, and connectivity to test services.
- Runner image and toolchain versions.
- Failure timing relative to other jobs on the same pool.

If a persistent runner is polluted with state from a previous job, clean it up or recreate the runner. Do not keep retrying on the same machine without verifying its health.

## 12. Recording failures and evidence for traceability

Every failure should have a record complete enough for someone else to continue investigating without re-running the job just to capture logs.

Fields to store:

- Pipeline run ID and job ID.
- Repository, branch, commit SHA, and pull request.
- Failing stage, job, step, and command.
- Exit code, signal, or HTTP status.
- Error class or failure category.
- Runner ID/image, OS, runtime, and toolchain version.
- Relevant environment/config revision.
- Start time, end time, and duration.
- Sanitized test reports, logs, and trace IDs.
- Retry count and outcome of each attempt.
- Root cause, owner, and remediation action once identified.

### 12.1. Usable classification labels

You can standardize a set of labels:

| Label | Meaning |
|---|---|
| **SOURCE_FAILURE** | Source code, dependency, or build definition error |
| **TEST_FAILURE** | Assertion or product behavior failed |
| **FLAKY_TEST** | Unstable test outcome requiring investigation |
| **INFRA_FAILURE** | Runner or underlying platform service error |
| **CONFIG_FAILURE** | Missing/wrong value, permission, secret, or endpoint |
| **UNKNOWN** | Insufficient evidence to classify |
| **RECOVERED_RETRY** | Retried after transient failure and succeeded |
| **FIXED_AND_VERIFIED** | Root cause fixed and re-verified |

Labels should describe observed evidence and must not replace root cause notes. A failure may carry `TEST_FAILURE` at the observation layer and `CONFIG_FAILURE` as its root cause. Store both fields if the system supports it.

### 12.2. Never include secrets in reports

Before uploading logs or reports, redact tokens, passwords, private keys, cookies, connection strings, and sensitive payloads. Keeping variable names or secret references is usually sufficient for investigation. Restrict read access to log artifacts and apply appropriate retention policies.

## 13. Example classification and retry policy

The following YAML example is a conceptual configuration, not a schema for any specific CI/CD platform:

~~~yaml
failure_policy:
  source_failure:
    retry: false
    action: fix_source_or_dependency
    owner: code_owner

  test_failure:
    assertion:
      retry: false
      action: investigate_product_or_expectation
    flaky:
      diagnostic_reruns: 2
      preserve_first_result: true
      action: create_flaky_test_record

  infrastructure_failure:
    retryable:
      - network_reset
      - service_503
      - rate_limited
      - runner_terminated
    max_attempts: 3
    backoff: exponential
    jitter: full
    action_after_exhaustion: escalate_infrastructure

  configuration_failure:
    retry: false
    action: validate_config_identity_and_permissions

  common:
    total_timeout: 20m
    preserve_logs: true
    redact_secrets: true
    require_failure_category: true
~~~

In practice, map categories to tool exit codes, error signatures, or response statuses. Avoid classifying solely via substring matching in logs when structured error codes or statuses are available.

## 14. Sample scenario: integration tests fail due to test database

Suppose an order service pipeline runs integration tests. Several database-related tests time out together, while unit tests and compilation pass.

1. Identify that the failing tests share a database dependency.
2. Read the logs showing tests could not obtain a connection within the deadline.
3. Inspect the runner: CPU and memory are normal, disk space is sufficient.
4. Inspect the service container: the database took longer to initialize and health checks were not yet passing.
5. Determine the root cause is an overly short test database setup timeout on a slower runner, not an application assertion failure.
6. Adjust readiness wait logic to match real conditions, with an overall timeout and status logging.
7. Re-run the integration suite on an equivalent runner.
8. Confirm the database reports healthy before tests start and all tests pass.
9. Record the failure category as `INFRA_FAILURE` or `TEST_ENVIRONMENT_FAILURE` per team taxonomy; record the specific cause as service readiness timeout.
10. Monitor subsequent runs to confirm the incident does not recur.

If the database is ready and data assertions still fail, shift the investigation to source/test. Classification must be based on evidence, not on the fact that the suite is named integration tests.

## 15. Practice roadmap

You can practice on a sample repository with these steps:

1. **Collect a baseline:** take a passing pipeline and save logs, test reports, runner image, commit, and execution duration.
2. **Create a controlled source failure:** introduce a compile error or failing unit assertion; confirm the pipeline does not auto-retry.
3. **Create a test failure:** break a test assertion and confirm the report shows the test along with expected/actual values.
4. **Create a flaky test:** introduce a race or order dependency in a test sandbox; run repeatedly and log each outcome.
5. **Create an infrastructure failure:** make a test service unavailable or simulate a network reset; confirm retries only apply to allowed errors.
6. **Create a configuration failure:** omit a required variable or supply a wrong endpoint; confirm validation fails fast without exposing secrets.
7. **Configure a retry policy:** set max attempts, backoff, jitter, and overall timeout.
8. **Test idempotency:** simulate a lost response after a mutating operation and verify the script queries state before resubmitting.
9. **Verify evidence:** confirm logs, reports, category, and retry history are preserved and secrets are redacted.
10. **Write a runbook:** document symptoms, evidence, owners, and actions for each failure category.

### Completion criteria

Learners can consider the lab complete when they can demonstrate:

- Distinguishing source, test, infrastructure, and configuration failures.
- Separating symptoms from root causes.
- Recognizing flaky tests and verifying them in a controlled manner.
- Determining which failures are retryable and which must be fixed first.
- Configuring bounded retries with exponential backoff, jitter, and timeouts.
- Using idempotency to avoid unintended duplicate mutations.
- Knowing when to use a circuit breaker or stop retrying.
- Collecting logs, reports, runner metadata, and retry history.
- Redacting secrets before storing evidence.
- Recording failure category, owner, root cause, and remediation outcome.

## Conclusion

Failure classification is the first step toward handling pipeline failures systematically. Source failures usually require fixing code or dependencies; test failures require distinguishing regressions from flaky behavior; infrastructure failures require recovering runners or dependencies; configuration failures require fixing values, identities, permissions, or secrets. The same symptom can stem from multiple domains, so decisions must rely on evidence.

Retries are only suitable for transient failures and operations that are safe to repeat. Exponential backoff, jitter, retry budgets, timeouts, and idempotency help bound blast radius. For unrecoverable errors, pipelines must stop, preserve evidence, and route to the right owner. When every failure carries a category, retry history, and resolution outcome, teams can cut down false-red pipelines, shorten investigation time, and maintain trust in the CI/CD flow.
