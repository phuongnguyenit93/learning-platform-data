# Measuring Feedback Time, Test Stability, and Wait Time

A CI/CD pipeline can pass successfully yet still waste a lot of the development team's time. Pull requests wait for runners; test jobs run fast but produce erratic results; pipelines fail after tens of minutes even though a simple check could have caught the error at the start. Looking only at pass/fail status or total duration makes it hard for a team to know where to improve.

To improve CI/CD, measure at least three dimensions:

- **Feedback time:** from the triggering event until the developer receives actionable feedback, plus the time to final outcome.
- **Test stability:** how repeatable test results are under identical conditions, intermittent failure rates, retries, and skipped tests.
- **Wait time:** time when pipelines/jobs are not doing real work because they are waiting for runners, environments, dependencies, approvals, or shared resources.

This is part of the **DEVOPS_CI_CD_FUNDAMENTALS** competency: building CI/CD discipline from Git events, pipelines as code, and automated build/test to artifact management, environments, quality gates, and traceable releases. Measurement helps identify bottlenecks, prioritize improvements, and verify whether changes genuinely improve the release flow.

## 1. What decisions should measurement inform?

A metric is only useful when tied to a specific operational or improvement question:

| Question | Metric to inspect | Decision it enables |
| --- | --- | --- |
| How long must developers wait to know a PR has an error? | Time to first feedback | Move lint, compile, and fast tests to the front of the pipeline |
| How long does a pipeline take to complete? | End-to-end pipeline duration | Analyze critical path, slow jobs, and dependencies |
| Are tests frequently inconsistent? | First-pass pass rate, flaky failures, retry-rescue rate | Fix tests, fixtures, environments, or test data |
| Where are jobs losing time waiting? | Queue wait, runner provisioning, approval wait, environment wait | Increase runner capacity, improve scheduling, or automate environment provisioning |
| Are releases faster while staying safe? | Pipeline metrics combined with quality, failure, and recovery metrics | Evaluate trade-offs and keep or revert improvements |

Do not optimize a single metric in isolation. Shortening a pipeline by dropping tests can make green runs arrive faster while increasing post-deployment failures. Increasing retries can raise the green pipeline rate while hiding unstable tests. Improvements must consider speed, reliability, and quality together.

## 2. Distinguishing pipeline time milestones

A pipeline has several distinct time intervals. Define start and end milestones before computing metrics.

| Interval | Start | End | Meaning |
| --- | --- | --- | --- |
| Trigger-to-first-feedback | Push/PR event received by CI | First actionable result | Developer wait for initial feedback |
| Pipeline duration | Pipeline created/triggered | Pipeline completed | Wall-clock time of the entire pipeline |
| Job queue wait | Job eligible to run and queued | Runner/executor picks up job | Waiting for execution capacity |
| Runner provisioning | Runner allocated or selected | Executor ready to run commands | Runtime environment startup time |
| Job execution | Commands/job start | Job finishes | Actual execution time, including in-job setup |
| Approval wait | Approval request created | Authorized person decides | Waiting for manual decision |
| Environment wait | Environment request submitted | Environment/lock acquired | Waiting for environment or shared resource |
| Pipeline completion feedback | Pipeline starts | Final result published | Time to final decision |

**Trigger-to-first-feedback** is not necessarily when the pipeline finishes. If lint and compile return results in three minutes while integration tests take twenty minutes, initial feedback can arrive much earlier than the final verdict.

### 2.1. Wall-clock time vs. sum of job durations

With parallel jobs, the sum of individual job durations can exceed the actual time a user waits for the pipeline. For example, two jobs taking 8 and 10 minutes run in parallel; the pipeline might take roughly 10 minutes plus orchestration overhead.

Therefore, distinguish:

- **Wall-clock duration:** elapsed time from when the pipeline starts until it finishes.
- **Sum of job durations:** total execution time across all jobs.
- **Critical path:** the chain of jobs/dependencies determining the earliest time the pipeline can complete.

To shorten wall-clock duration, look for jobs or dependencies on the critical path. Optimizing a job off the critical path can lower runner cost without getting results to developers any sooner.

## 3. Measuring feedback time (pipeline responsiveness)

Feedback time reflects how quickly CI delivers information after a change. Two primary metrics can be tracked:

**Time to first actionable feedback**

\[
T_{first} = t_{first\_feedback} - t_{trigger}
\]

Actionable feedback is a result that helps a developer decide to fix code, inspect logs, or continue waiting for remaining checks. Examples: lint failure, compile failure, or fast unit test results.

**End-to-end pipeline duration**

\[
T_{pipeline} = t_{completed} - t_{trigger}
\]

This metric measures the time from trigger to final state, including queuing, job execution, approvals, and any wait intervals inside the pipeline as defined by the system.

Do not measure from when the runner starts running and call that pipeline response time, because that omits the time developers spend waiting for a runner.

### 3.1. Choosing a consistent first-feedback milestone

Clearly define which feedback counts:

- Lint/static checks capable of catching errors quickly.
- Compile/build validation.
- Core unit tests.
- Policy checks or secret scans.
- First aggregated result of required checks.

Do not count a “job started” log line as feedback; it does not tell whether the change is valid. Nor should you count an optional job that finishes before required checks without providing useful signal.

You can measure time-to-first-failure and time-to-first-success separately. Early failures enable faster fixes; the first pass shows when review or merge can proceed under policy.

### 3.2. Using percentiles instead of averages alone

Pipeline durations typically have a skewed distribution: most runs finish quickly, while a few hit long queues or runner failures. Averages can obscure either the typical experience or the worst delays teams suffer.

| Metric | Interpretation |
| --- | --- |
| p50 | Half of runs complete within this time or faster |
| p90 | 90% of runs complete within this time or faster |
| p95 | 95% of runs complete within this time or faster |
| Maximum | Slowest run in the data window; sensitive to outliers |

Track p50 to understand the typical experience and p90/p95 to spot runs suffering prolonged wait or execution times. Always display sample count and measurement window; p95 from 10 runs is nowhere near as stable as p95 from thousands of runs.

## 4. Measuring test stability

Tests are stable when the same code version, conditions, and equivalent test data yield consistent results. A test that fails and then passes on rerun without relevant code changes might be a flaky test, or it might result from unstable dependencies or infrastructure.

Do not treat every successful retry as definitive proof of a flaky test. Categorize the root cause and preserve first-attempt results.

### 4.1. Test reliability metrics

| Metric | Formula/definition | What to watch for |
| --- | --- | --- |
| First-pass pass rate | Tests passing on first run / total tests executed on first run | Do not count skipped tests as passes |
| First-pass failure rate | Tests failing on first run / total tests executed on first run | Classify product failures, test defects, and infrastructure failures |
| Retry-rescue rate | Tests failing first run but passing on retry / failed tests retried | A signal of suspected flakiness, not a final conclusion |
| Confirmed flaky-test rate | Test IDs with inconsistent outcomes across repeated identical runs / eligible repeated test IDs | Requires defining window and comparison conditions |
| Retry rate | Tests/jobs with retries / eligible tests/jobs | High retry rates can mask instability |
| Skip rate | Skipped/disabled tests / total expected tests | Helps detect shrinking coverage |

For example: in one day 1,000 test cases execute on the first run; 970 pass, 30 fail. Suppose all 30 failed tests are retried and 18 pass on retry. First-pass pass rate is 97%; retry-rescue rate is 60% among the 30 retried tests. That 60% signals an investigation target, not that 60% of the entire test suite is flaky.

### 4.2. Distinguishing product defects, test defects, and infrastructure failures

A test failure can stem from:

- **Product defect:** the application returns wrong results or behavior fails requirements.
- **Test defect:** wrong assertions, brittle UI selectors, broken fixture data, or order-dependent tests.
- **Infrastructure failure:** runner disconnects, DNS errors, test database unavailable, or resource exhaustion.
- **External dependency:** external sandbox/API slow or disrupted.
- **Flaky behavior:** race conditions, timing, shared state, or non-determinism causing the same test to intermittently pass and fail.

Proper classification drives the right fix. Adding runner capacity does not fix a race condition inside a test; rewriting assertions does not fix a test database running out of connections.

### 4.3. Tracking test stability by test ID

Every test should have a stable identifier across runs. Reports should store:

- Test ID and suite/module.
- Commit SHA or artifact version tested.
- Environment, runner image, and dependency versions.
- First attempt and all retries.
- Outcome, duration, and failure category.
- Skipped/disabled status and reason.

If test names change continuously, systems struggle to recognize chronically flaky tests. Use stable test IDs or metadata to track history.

Do not pool test results across different commits, environments, or configurations without segmentation. A test might pass on Linux yet fail on Windows due to environment differences; that is vital signal to preserve.

## 5. Measuring wait time

Pipelines can be slow even when command execution is short. Common wait intervals:

| Wait type | Example | Improvement direction |
| --- | --- | --- |
| Runner queue wait | Job waiting for an available runner | Tune concurrency, autoscaling, and pool allocation |
| Runner provisioning | Booting VM/container, installing toolchain | Use pre-baked images, optimized ephemeral runners |
| Environment wait | Waiting for namespace, test environment, or lock | On-demand environments, cleanup, and lease management |
| Approval wait | Waiting for release approver | Risk-based approvals, on-call rotation, clear notifications |
| Dependency wait | Waiting for upstream pipeline/artifact | Caching, versioning, and trimming unnecessary dependencies |
| Resource contention | Waiting for test database, device farm, or license | Pool splitting, quotas, and concurrency limits |
| Manual handoff | Waiting for manual artifact copy or variable updates | Controlled handoff automation |

### 5.1. Formulas for wait intervals

Examples:

\[
T_{queue} = t_{runner\_assigned} - t_{job\_queued}
\]

\[
T_{provision} = t_{executor\_ready} - t_{runner\_assigned}
\]

\[
T_{approval} = t_{decision} - t_{approval\_requested}
\]

\[
T_{environment} = t_{lease\_acquired} - t_{environment\_requested}
\]

Milestones must be defined according to what the CI platform supports. Some platforms only expose job queued and started timestamps, not runner assigned or executor ready. In such cases, state clearly which intervals are directly measured and which are estimates; avoid metric names that mislead readers.

### 5.2. Waiting for a runner vs. job execution

Suppose a job is queued at 09:00, a runner is assigned at 09:04, the executor is ready at 09:05, and the test command finishes at 09:12:

- Queue wait: 4 minutes.
- Runner provisioning: 1 minute.
- Execution: 7 minutes.
- Time from queue to finish: 12 minutes.

If the team only looks at the 7-minute job duration, they overlook the 5 minutes developers waited before tests even started. If a pipeline has many parallel jobs, inspect each job on a timeline to determine which sits on the critical path.

## 6. Instrumentation: recording events and timestamps

To measure accurately, emit events at key milestones. Each event should carry pipeline/job identifiers and UTC timestamps.

Example event for a job:

~~~json
{
  "event_id": "evt-job-1842-test-01",
  "event_type": "ci.job.started",
  "occurred_at": "2026-11-18T09:05:00Z",
  "pipeline_id": "pipeline-1842",
  "job_id": "integration-test",
  "repository": "commerce/orders-api",
  "commit_sha": "4f9a1c2d7b...",
  "runner_pool": "linux-medium",
  "environment": "ci-test",
  "attempt": 1
}
~~~

Useful events:

- pipeline.triggered
- pipeline.first_feedback
- pipeline.completed
- job.queued
- job.runner_assigned
- job.started
- job.completed
- test.case.started
- test.case.completed
- approval.requested
- approval.decided
- environment.requested
- environment.acquired

These are illustrative event names. In production systems, define the schema, required fields, unique event IDs, producers, timestamps, and duplicate-event handling rules.

### 6.1. Clocks and timestamps

Runners, CI controllers, and external services can have clock drift. Synchronize time using standard infrastructure mechanisms and store timestamps in UTC. Whenever possible, use a monotonic clock to measure durations within a single process; use wall-clock timestamps to correlate events across systems.

Do not compute negative durations or join timestamps from unsynchronized machines without alerting. If the platform provides pre-computed durations, understand the platform's exact definition before comparing them with custom metrics.

### 6.2. Keeping correlation keys consistent

Events should carry appropriate fields:

- repository, commit SHA, and branch/ref.
- pipeline ID, job ID, and attempt number.
- test suite/test ID.
- runner pool and environment.
- event type, timestamp, and result.
- release/deployment ID if the job is part of a release flow.

Never put tokens, secrets, sensitive payload contents, or personal data into metrics/events. Use pseudonymous IDs or sanitized metadata when needed for investigation.

## 7. Analyzing pipelines via timelines and critical paths

A dashboard showing only “pipeline took 18 minutes” is not enough to find the cause. Inspect the job timeline and dependencies:

~~~mermaid
gantt
    title Example pipeline timeline
    dateFormat HH:mm
    axisFormat %H:%M
    section Trigger
    Trigger to first feedback :a1, 09:00, 4m
    section Jobs
    Lint and compile :a2, 09:01, 3m
    Unit tests :a3, 09:04, 5m
    Integration tests :a4, 09:05, 7m
    section Release
    Approval wait :a5, 09:12, 5m
    Deploy and smoke :a6, 09:17, 4m
~~~

This timeline is illustrative, not a literal sum to deduce exact pipeline wall-clock time. Jobs can run in parallel; approvals might start before all jobs finish depending on design. Always derive actual milestones from events.

To identify the critical path:

1. Build the job dependency graph.
2. Record queued, started, and completed timestamps.
3. Find the longest dependency chain governing pipeline completion.
4. Separate queue/provisioning from execution along that chain.
5. Prioritize improving steps that are both slow and on the critical path.

A slow job running in parallel that finishes before the critical path needs it may not affect wall-clock duration. However, it can still consume runners and lengthen queues for other pipelines.

## 8. Segmenting data to pinpoint affected groups

Do not look at just one organization-wide average. Break down along meaningful dimensions:

- Repository or service.
- Event type: pull request, push, tag, scheduled, manual.
- Branch class: feature, main, release.
- Runner pool or executor type.
- Job class: lint, unit, integration, e2e, deploy.
- Environment or region.
- Change size or pipeline type if suitable data is available.

For example, high p95 queue wait on a Linux runner pool may indicate insufficient concurrency; high p95 execution specifically on the integration suite may stem from tests or dependencies. A set of tests flaky on Windows should not be masked by clean results on Linux.

Keep cardinality reasonable. Avoid putting commit SHA, test run ID, or user ID into metric labels if doing so creates thousands or millions of time series. Use log/event stores for detailed queries; metrics should use dimensions with bounded value sets.

## 9. Designing dashboards and measurement targets

Dashboards should answer three questions: how fast is feedback, how reliable are test results, and where is wait time occurring.

A basic dashboard can include:

| Group | Panel | Display |
| --- | --- | --- |
| Response | Trigger-to-first-feedback | p50/p90/p95 by repository |
| Response | End-to-end pipeline duration | p50/p90/p95 and pipeline count |
| Test stability | First-pass pass rate | By suite and branch class |
| Test stability | Retry-rescue / confirmed flaky rate | Top test IDs to investigate |
| Test stability | Skip rate | By suite and reason |
| Waiting | Queue wait | p50/p90/p95 by runner pool |
| Waiting | Provisioning time | By executor/image |
| Waiting | Approval/environment wait | By stage and owner |
| Outcome | Pipeline success and change failure | By service/release window |

Set targets from real baselines, such as p90 time-to-first-feedback, p95 queue wait, or first-pass pass rate. Do not copy thresholds from other organizations when runner scale, test suites, and products differ.

A solid target needs:

- Measurement scope and applicable entities.
- Formula and start/end timestamps.
- Time window.
- Target threshold and alert threshold.
- Accountable owner.
- Guardrails to prevent trading away quality.

## 10. Calculation example from a pipeline

Suppose a pipeline has the following timestamps:

| Event | Timestamp |
| --- | --- |
| PR trigger received by CI | 09:00 |
| Lint/compile returns first feedback | 09:04 |
| Integration job queued | 09:05 |
| Runner assigned | 09:09 |
| Executor ready | 09:10 |
| Integration test finishes | 09:17 |
| Approval requested | 09:17 |
| Approval decided | 09:22 |
| Deploy and smoke complete | 09:28 |

From these timestamps:

- Time to first feedback = 4 minutes.
- Integration job queue wait = 4 minutes.
- Provisioning time = 1 minute.
- Integration execution = 7 minutes.
- Approval wait = 5 minutes.
- End-to-end duration = 28 minutes.

If the team cuts integration execution from 7 to 5 minutes while queue stays 4 minutes and approval stays 5 minutes, total time drops by only about 2 minutes if that is the critical path. If queue wait drops from 4 to 1 minute, users receive final results sooner without touching tests.

If first-pass pass rate is only 92% and many tests pass on retry, optimizing speed before fixing stability can make pipelines pass faster without becoming more trustworthy. Examine all three metric groups together.

## 11. Improving feedback time

When time-to-first-feedback is high:

- Put linting, formatting, compilation, and fast unit tests at the start of the pipeline.
- Run independent checks in parallel.
- Run change-scoped tests only when the dependency graph is reliable enough.
- Use dependency caching with proper keys and invalidation.
- Avoid repeatedly downloading toolchains or container images in every job.
- Fail fast when a required check is guaranteed to fail.
- Keep slower tests in later stages while keeping them mandatory before release if policy requires.

Do not run an unstable test suite at the start of the pipeline just to get fast feedback. False positives erode developer trust in CI and create extra investigation overhead.

When end-to-end duration is high but first feedback is low, keep the fast feedback pipeline and optimize the critical path in later stages. Never look solely at total time and serialize all tests.

## 12. Improving test stability

When retry-rescue rate or confirmed flaky rate is high, investigate by root-cause category:

**Time-dependent tests**

- Use mocked or fixed clocks for time-based logic.
- Avoid fixed sleeps; wait on conditions with timeouts.
- Check runner timezone and locale settings.

**Tests sharing state**

- Create isolated data per test/run.
- Clean up data using clearly scoped fixtures.
- Avoid test order dependencies or shared resources.
- Isolate accounts, tenants, database schemas, and queues when needed.

**Race conditions and concurrency**

- Wait for actual completion states.
- Use proper synchronization rather than timing assumptions.
- Check for resource contention and concurrency limits.

**Environments and dependencies**

- Pin browser, driver, container, and toolchain versions.
- Health-check dependencies before running suites.
- Capture logs, traces, and runner metadata on failure.
- Use sandboxes/mocks for unstable external dependencies where appropriate.

Keep retries as a bounded recovery mechanism or diagnostic tool. Do not automatically turn a retry pass into a clean pass by erasing the initial failure. Reports must preserve both the first attempt, retries, and failure classification.

## 13. Reducing wait time by root cause

### 13.1. High queue wait

- Measure queues by runner pool, time of day, and job class.
- Increase concurrency or autoscaling when sustained demand proves a capacity shortage.
- Separate pools for heavy or sensitive workloads.
- Curb unnecessary jobs and duplicate pipelines.
- Set concurrency limits to avoid saturating downstream infrastructure.

### 13.2. High provisioning time

- Use runner images preloaded with common toolchains.
- Reduce runtime installation steps per job.
- Pin images by digest and update in a controlled manner.
- Optimize container/VM startup.
- Collect bootstrap timings separately to identify which step is slow.

### 13.3. High approval wait

- Determine which approvals are mandatory based on risk.
- Use environment protections and clear approver groups.
- Send notifications with context and deadlines.
- Maintain on-call rotations or backup approvers.
- Automate checks verifiable via policy, reserving human approval for accountable decisions.

Do not remove approvals merely to shrink a metric if the change still requires production risk control.

### 13.4. High environment wait

- Use ephemeral environments for PRs when suitable.
- Automatically provision and tear down namespaces/test environments.
- Manage locks/leases with timeouts and cleanup.
- Separate environments for parallel test runs.
- Reduce reliance on a single shared integration environment.

### 13.5. High dependency wait

- Publish artifacts promptly after upstream builds succeed.
- Pin versions and digests so consumers fetch exact contents.
- Safely cache artifacts/dependencies.
- Trigger only affected consumers.
- Avoid system-wide release trains when contracts permit independent releases.

## 14. Preventing metrics from driving wrong behaviors

When metrics become targets, teams may accidentally optimize numbers instead of outcomes:

- Dropping slow tests to cut pipeline duration.
- Moving tests to optional jobs so they do not count toward pass rates.
- Retrying repeatedly until green and reporting only the final run.
- Splitting a pipeline into pieces to shrink displayed duration while raising total cost.
- Skipping approvals or security checks to cut wait time.
- Measuring from runner start instead of trigger to exclude queue wait from reports.

Guardrails:

- Keep executed, skipped, and disabled test counts visible on dashboards.
- Store the first attempt and every retry.
- Measure both wall-clock duration and wait times.
- Track post-deploy failures, rollbacks, and incidents alongside CI speed.
- Change metric definitions only through versioned reviews.
- Never rank individuals by pipeline duration or commit counts.

The goal is to reduce feedback and wait times while preserving test coverage, reliability, and release quality.

## 15. Connection to DORA and release outcomes

Feedback, test stability, and wait-time metrics primarily improve internal CI/CD flow. They complement service/team-level delivery metrics such as:

- Lead time for changes: time from committed change to running in production, per the organization's measurable definition.
- Deployment frequency: cadence of deployments.
- Change failure rate: percentage of deployments causing service degradation or requiring remediation per agreed definition.
- Failed deployment recovery time: recovery time after a failed deployment.

Do not equate pipeline duration with lead time for changes. A pipeline may take 20 minutes while code waited two days for review; conversely, a fast pipeline's release might wait for a long deployment window.

When optimizing CI/CD, examine both delivery speed and delivery stability. If pipelines get faster while change failure rate rises or recovery time lengthens, the change is not necessarily an improvement.

## 16. Data-driven improvement loop

A practical improvement process:

1. **Define:** agree on metrics, formulas, timestamps, and scope.
2. **Baseline:** collect data long enough to see peak days, pipeline types, and variance.
3. **Segment:** pinpoint problematic repositories, runner pools, test suites, or stages.
4. **Identify root cause:** use timelines, logs, and owners to isolate bottlenecks.
5. **Propose change:** modify only one or a small related group of factors.
6. **Check guardrails:** inspect test coverage, failures, security, and release outcomes.
7. **Compare:** compare p50/p90/p95 and sample counts before/after across equivalent cohorts.
8. **Standardize:** document effective practices and keep watching for drift.

For example, if p95 queue wait rises after adding an integration suite, inspect runner pools and concurrency before trimming tests. If first-pass pass rate drops right after a runner image update, compare test failures by image version to isolate the impact.

Do not change many components simultaneously without a baseline; when metrics shift, the team will not know which change caused the effect.

## 17. Example metric definitions for dashboards

A definition set can live in a repository so every team shares the same understanding:

~~~yaml
metrics:
  pipeline_first_feedback_seconds:
    start_event: pipeline.triggered
    end_event: pipeline.first_actionable_feedback
    aggregation: p50_p90_p95
    dimensions:
      - repository
      - event_type
      - runner_pool

  pipeline_wall_clock_seconds:
    start_event: pipeline.triggered
    end_event: pipeline.completed
    aggregation: p50_p90_p95
    dimensions:
      - repository
      - branch_class

  job_queue_wait_seconds:
    start_event: job.queued
    end_event: job.runner_assigned
    aggregation: p50_p90_p95
    dimensions:
      - runner_pool
      - job_class

  test_first_pass_pass_rate:
    numerator: test_cases_passed_on_first_attempt
    denominator: test_cases_executed_on_first_attempt
    aggregation: ratio
    exclude:
      - skipped

  test_retry_rescue_rate:
    numerator: failed_tests_that_passed_on_retry
    denominator: failed_tests_retried
    aggregation: ratio

  approval_wait_seconds:
    start_event: approval.requested
    end_event: approval.decided
    aggregation: p50_p90_p95
    dimensions:
      - environment
      - approval_type
~~~

This is an illustrative schema. Metric owners must define how to handle missing events, canceled jobs, pipeline retries, confirmed flaky tests, revoked approvals, and re-created pipelines. If the denominator is 0, ratio metrics must show no data instead of defaulting to 100%.

## 18. Common pitfalls

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Measuring only pipeline duration | Unknown whether time is spent in queue, execution, or approval | Measure each interval and critical path |
| Measuring from runner start | Ignores developer wait time | Measure from trigger/queue per definition |
| Using averages only | Outliers skew or mask p95 | Track p50/p90/p95 and sample size |
| Treating retry passes as stable tests | Masks intermittent failures | Store first attempts and classify failures |
| Counting skipped tests as passes | Inflates rates while cutting test coverage | Report skip rate separately |
| Lumping infra errors into product failures | Fixes the wrong cause | Classify test, product, infra, and external dependencies |
| Optimizing off-critical-path jobs | Does not reduce user wait time | Analyze dependency graphs and timelines |
| Scaling runners without limits | Drives up cost and saturates dependencies | Data-driven concurrency/capacity limits |
| Removing approvals to cut wait | Increases release risk | Risk-based approvals and automated checks |
| Infinite retries | Lengthens pipelines and hides bugs | Bounded retries, backoff, and clear reporting |
| Not versioning metric definitions | Teams measure differently and cannot compare | Version schemas and formulas |
| Watching CI speed alone | Misses post-deploy failures | Combine DORA and quality guardrails |

## 19. CI/CD measurement and improvement checklist

**Definition and collection**

- [ ] Definitions exist for trigger, first feedback, and pipeline completion.
- [ ] Wall-clock duration, job execution, and wait intervals are measured separately.
- [ ] UTC events/timestamps are recorded with pipeline ID, job ID, and attempt.
- [ ] Releases, deployments, repositories, and runner pools are distinguished.
- [ ] Clear metric definitions and owners exist.

**Test stability**

- [ ] First-pass pass/failure rates are reported.
- [ ] Every retry and first-attempt outcome is preserved.
- [ ] Retry-rescue, confirmed flaky, and skip rates are measured.
- [ ] Product, test, infrastructure, and external failures are classified.
- [ ] History is tracked by test ID and environment.

**Wait and feedback times**

- [ ] p50/p90/p95 and sample sizes are tracked.
- [ ] Queue, provisioning, approval, environment, and dependency waits are separated.
- [ ] Pipeline critical paths are identified.
- [ ] Data is segmented by repository, event type, runner pool, and job class.
- [ ] Dashboards show where action is needed and who owns it.

**Improvement with guardrails**

- [ ] A baseline exists before making changes.
- [ ] Bottlenecks are prioritized using data.
- [ ] Tests or approvals are not dropped merely to look good on metrics.
- [ ] Coverage, release failures, and recovery are tracked alongside speed.
- [ ] Before/after comparisons use equivalent cohorts and outcomes are recorded.

## Conclusion

Measuring feedback time, test stability, and wait time helps teams understand where CI/CD is costing developers time and whether test results can be trusted. Measure from trigger time, separate first feedback from pipeline completion, analyze queue/provisioning/approval waits individually, and keep first-attempt results alongside all retries to expose unstable tests.

Percentiles, timelines, and dependency graphs reveal real bottlenecks. Improvements should start from baselines, target root causes on the critical path, and always include guardrails for test coverage, security, change failures, and recovery. When metrics are clearly defined, properly segmented, and never weaponized into number-chasing targets, they become a durable tool for CI/CD improvement.
