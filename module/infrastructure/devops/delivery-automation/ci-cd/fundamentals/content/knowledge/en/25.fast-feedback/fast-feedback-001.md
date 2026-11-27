# Measuring Runner Wait Time and Individual Job Durations

The time a CI/CD pipeline takes from receiving a change to returning results depends on multiple components. A job may sit in a queue because no runner slot is available; a runner may take additional time to be provisioned and started; and only then does the job check out source code, download dependencies, build, run tests, and upload artifacts. If a team only looks at total pipeline duration, it is difficult to tell whether time is spent waiting for a runner or actually executing work.

Measuring runner wait time and individual job durations helps pinpoint exactly where feedback is slow. **Runner queue time** shows how long a job must wait before getting an execution machine; **runner provisioning time** shows how long the machine takes to become ready; **job execution time** shows how long the work itself takes; and **end-to-end feedback time** shows how long a developer must wait to receive the required results.

This lesson explains how to define time intervals, collect timestamps, calculate durations, break down metrics by job and runner pool, build dashboards, interpret percentiles, and identify bottlenecks. The goal is to turn the vague perception of a "slow pipeline" into actionable data: knowing which jobs wait too long, which steps run slowly, which runner pools lack capacity, and which changes genuinely improve feedback time.

## 1. Breaking Down Time Instead of Measuring Only Total Pipeline Duration

A pipeline typically consists of multiple jobs connected by dependencies. Some jobs run in parallel, while others only start after an upstream job completes. Each job goes through stages such as waiting for a runner, provisioning the machine, setup, and executing steps.

If you only measure from trigger time to pipeline completion, you know the total duration but not which part causes the delay. You should separate at least the following intervals:

| Time Interval | Start Point | End Point | Meaning |
|---|---|---|---|
| Dependency wait | Job is created or workflow starts | Job becomes eligible to run after dependencies complete | Time spent waiting for upstream jobs |
| Runner queue time | Job becomes eligible to run | Runner is assigned by the scheduler | Time spent waiting for execution capacity |
| Runner provisioning time | Runner is assigned/provisioning is requested | Runner is ready to accept the job | Time to create the VM/container or boot the machine |
| Job startup time | Runner is ready | First job command begins | Checkout/bootstrap or initial setup |
| Job execution time | Job starts | Job completes | Job execution time, including steps and in-job overhead |
| Step duration | A step starts | Step completes | Duration of each individual command or operation group |
| End-to-end feedback time | Pipeline trigger event | Required results are published | Time the developer must wait for feedback |

The key point is that **queue time and provisioning time are two different things**. A job may be picked up by the scheduler immediately, yet a new machine takes 40 seconds to provision. Conversely, runners may always be ready, yet a job has to queue for 5 minutes because all machines are busy.

Some platforms only provide two timestamps: queued and started. In that case, the interval from queued to started may combine queue, provisioning, and startup. Name it **wait_to_start** or **queue_plus_startup**, and do not call it pure queue time if you lack timestamps to separate those stages.

~~~mermaid
flowchart LR
    A["Workflow triggered"] --> B["Job eligible"]
    B --> C["Runner queue"]
    C --> D["Runner assigned"]
    D --> E["Runner provisioning"]
    E --> F["Runner ready"]
    F --> G["Job startup"]
    G --> H["Job execution"]
    H --> I["Job completed"]
    I --> J["Feedback published"]
~~~

## 2. Defining Standard Timestamps

Accurate duration measurement starts with agreeing on the meaning of each timestamp. Field names may differ across GitHub Actions, GitLab CI, Jenkins, or internal CI systems, but the concepts should stay consistent.

A reference event model:

| Timestamp | Meaning |
|---|---|
| workflow_triggered_at | Git event or manual action that triggers the workflow |
| job_created_at | System creates the job |
| job_eligible_at | All dependency conditions are met, and the scheduler can place the job in the queue |
| runner_requested_at | Runner request is sent |
| runner_assigned_at | Scheduler selects or assigns a runner |
| runner_ready_at | Runner finishes provisioning and is ready to execute |
| job_started_at | Job execution commands begin |
| step_started_at | A step begins |
| step_completed_at | A step finishes |
| job_completed_at | Job ends, regardless of success or failure |
| feedback_published_at | Results are displayed or sent to where developers receive feedback |

Not every platform emits all of these events. You can add instrumentation in the runner controller, a plugin, or a pipeline wrapper to collect the missing pieces.

### 2.1. Choosing the Right Queue Start Timestamp

For jobs with dependencies, a job may be created at the start of the workflow but not allowed to run because an upstream job has not finished. That waiting period is **dependency wait**, not runner queue time.

For example, integration tests only run after the build completes. If the build takes 4 minutes, the integration job is not eligible for the scheduler to allocate a runner during that period. Recording all 4 minutes as queue time would mislead the team into thinking the runner pool lacks machines when the job was actually waiting on a dependency.

To measure pure queue time, use **job_eligible_at** as the start timestamp if the system provides it. If this timestamp is unavailable, clearly document that the metric includes dependency wait.

### 2.2. Measuring Duration with the Right Clock

Timestamps used for correlation across multiple systems should be stored in UTC, with clocks synchronized across controllers, runners, and services. When measuring an interval within the same process or on the same machine, prefer a monotonic clock because wall-clock time can be adjusted while a job is running.

Do not take timestamps from logs on two unsynchronized machines and subtract them directly without accounting for clock skew. A negative or anomalous result is usually a sign of out-of-order events, clock drift, or missing data.

## 3. Formulas for Calculating Time Intervals

Once standard timestamps are available, durations are calculated as follows:

\[
T_{\text{dependency}} =
t_{\text{eligible}} - t_{\text{created}}
\]

\[
T_{\text{queue}} =
t_{\text{runner-assigned}} - t_{\text{eligible}}
\]

\[
T_{\text{provision}} =
t_{\text{runner-ready}} - t_{\text{runner-assigned}}
\]

\[
T_{\text{startup}} =
t_{\text{job-started}} - t_{\text{runner-ready}}
\]

\[
T_{\text{job}} =
t_{\text{job-completed}} - t_{\text{job-started}}
\]

\[
T_{\text{feedback}} =
t_{\text{feedback-published}} - t_{\text{workflow-triggered}}
\]

If only queued and started timestamps are available, you can calculate:

\[
T_{\text{wait-to-start}} =
t_{\text{started}} - t_{\text{queued}}
\]

However, note that this metric combines stages that the platform cannot separate.

### 3.1. Duration Calculation Example

Suppose a workflow has three jobs:

- lint and unit-test are eligible to run immediately when the workflow starts.
- integration-test becomes eligible only after unit-test completes.
- Runners are provisioned at different times.

| Job | Eligible | Runner assigned | Runner ready | Job started | Job completed |
|---|---:|---:|---:|---:|---:|
| lint | 09:00:00 | 09:00:20 | 09:00:25 | 09:00:25 | 09:00:55 |
| unit-test | 09:00:00 | 09:00:50 | 09:01:00 | 09:01:00 | 09:03:00 |
| integration-test | 09:03:00 | 09:03:10 | 09:03:20 | 09:03:20 | 09:07:20 |

From the data above:

| Job | Queue | Provisioning | Startup | Execution |
|---|---:|---:|---:|---:|
| lint | 20 seconds | 5 seconds | 0 seconds | 30 seconds |
| unit-test | 50 seconds | 10 seconds | 0 seconds | 120 seconds |
| integration-test | 10 seconds | 10 seconds | 0 seconds | 240 seconds |

The integration test has a dependency wait of 180 seconds from when the workflow started until unit-test finished. Its queue time is only 10 seconds from becoming eligible until a runner was assigned.

If the workflow was triggered at 09:00 and the final result was published at 09:07:20, the end-to-end feedback time is 7 minutes 20 seconds. You must not sum the queue times and durations of all three jobs to derive the pipeline duration, because lint and unit-test run in parallel. End-to-end time depends on the critical path of the job graph and the associated wait intervals.

## 4. Distinguishing Job, Step, and Pipeline Duration

These three levels answer three different questions:

- **Pipeline duration:** how long a developer waits from trigger to result.
- **Job duration:** how long a specific job runs after starting.
- **Step duration:** how long a specific operation inside a job takes.

For example, a build-and-test job runs for 12 minutes 40 seconds. Within it:

| Step | Duration |
|---|---:|
| Checkout | 20 seconds |
| Restore dependency cache | 15 seconds |
| Resolve dependencies | 70 seconds |
| Compile | 90 seconds |
| Unit tests | 420 seconds |
| Package artifact | 45 seconds |
| Upload artifact | 60 seconds |
| Other setup/teardown steps | 40 seconds |

The sum of the listed step durations is 760 seconds (12 minutes 40 seconds), matching the job duration in the example. In practice, the sum of step durations can differ from the job duration due to setup/teardown, platform overhead, overlapping steps, or inconsistent timestamp conventions. Check how the platform calculates time and which intervals are not recorded as steps.

In a pipeline with many parallel jobs, the sum of all job durations can be much larger than the pipeline duration. That is normal: total job duration measures the amount of compute work consumed, while pipeline duration measures the actual wall-clock time until results are available.

### 4.1. Critical Path

The critical path is the chain of jobs and dependencies that determines when the pipeline can finish. Speeding up a job that is not on the critical path may not reduce final feedback time.

For example:

~~~mermaid
flowchart TD
    A["Trigger"] --> B["Lint 30s"]
    A --> C["Unit test 120s"]
    B --> D["Package"]
    C --> D
    D --> E["Integration test 240s"]
    E --> F["Publish result"]
~~~

In this example, lint finishes before unit test. If package requires both lint and unit test, it must wait for the unit test branch. Optimizing lint from 30 seconds down to 10 seconds does not change the critical path if unit test still takes 120 seconds. Optimizing unit test can reduce end-to-end time more directly.

### 4.2. First Feedback and Final Feedback

A developer might receive lint results after 30 seconds, yet wait several more minutes for integration tests. You should measure all of the following:

- **time_to_first_feedback:** time until the first useful result arrives.
- **time_to_required_checks:** time until all required checks complete.
- **time_to_pipeline_completion:** time until the entire workflow finishes.

These milestones help evaluate whether the pipeline surfaces errors early or forces developers to wait for every task just to learn about a simple error.

## 5. Collecting Timing Data from Pipelines

To enable analysis, each run must emit events with consistent identifiers and timestamps.

An event might contain:

~~~json
{
  "workflow_run_id": "run-84721",
  "job_id": "job-compile-02",
  "job_name": "unit-test",
  "stage": "test",
  "repository": "orders-service",
  "commit_sha": "a91c...72ef",
  "runner_pool": "linux-large",
  "runner_image": "ubuntu-22.04-v17",
  "job_eligible_at": "2026-11-18T09:00:00Z",
  "runner_assigned_at": "2026-11-18T09:00:50Z",
  "runner_ready_at": "2026-11-18T09:01:00Z",
  "job_started_at": "2026-11-18T09:01:00Z",
  "job_completed_at": "2026-11-18T09:03:00Z",
  "result": "success"
}
~~~

This is an illustrative event schema. Field names can be adjusted to match your CI provider or internal telemetry system.

### 5.1. Metadata to Store

For meaningful analysis, associate durations with:

- Workflow name and run ID.
- Job name, job ID, and stage.
- Repository, branch, commit SHA, and trigger type.
- Runner pool, machine type, CPU/memory class, and image version.
- Operating system, architecture, and toolchain.
- Job result: success, failure, cancelled, or skipped.
- Cache hit/miss and artifact size if available.
- Start/end timestamps and retry attempt.

Do not put run ID, commit SHA, or user ID as labels on every time series if your metrics system incurs high cardinality costs. Store them in events/logs or traces; metrics should only use bounded-value labels such as job_name, stage, runner_pool, os, and result.

### 5.2. Ensuring Events Are Not Lost

Record successful jobs as well as failed, cancelled, and timed-out jobs. If you only store normally completed jobs, dashboards will miss hung jobs or lost runners.

You can use CI provider event hooks, runner telemetry, plugins, or wrappers to emit events when:

- A job is created and becomes eligible to run.
- A runner is assigned and becomes ready.
- A job starts and finishes.
- A step starts and finishes.
- A job is cancelled or times out.
- Feedback is published.

If an event is missing, explicitly mark the data as incomplete instead of setting duration to 0. Track the missing-event rate as a quality indicator for the measurement system.

## 6. Measuring Runner Queue Time

High queue time usually means jobs are eligible to run, but no suitable runner is available or the scheduler has not assigned one yet.

Common causes include:

- Insufficient runners for the number of concurrent jobs.
- Many pipelines starting simultaneously after a burst of pushes or merges.
- Runner pools restricted by repository, team, or environment.
- Jobs requesting rare labels, OSes, or specialized architectures.
- Runner autoscaling taking too long to spin up or hitting capacity limits.
- Long-running jobs occupying all persistent runners.
- Hitting platform concurrency limits or quotas.
- Low-priority jobs waiting behind high-priority jobs.

### 6.1. Analyzing Queue Time by Runner Pool

Do not look only at organization-wide average queue time. Break it down by runner pool, machine type, repository, job class, and time of day.

For example:

| Runner pool | p50 queue | p95 queue | Job count | Assessment |
|---|---:|---:|---:|---|
| linux-small | 8 seconds | 35 seconds | 4,200 | Capacity is relatively stable |
| linux-large | 25 seconds | 210 seconds | 1,100 | May lack large machines during peak hours |
| windows | 40 seconds | 300 seconds | 420 | Need to check capacity and startup |
| macos | 75 seconds | 480 seconds | 160 | Small pool, concentrated demand |

These numbers are illustrative examples. A high p95 in a pool with few jobs can fluctuate sharply; always check sample count and multi-day trends.

### 6.2. Queue Time vs. Provisioning Time

If queue time is low but the time from runner assigned to runner ready is high, increasing the number of always-on runners may help more than increasing queue quotas. If both queue and provisioning times are high, check both capacity and the autoscaler.

For ephemeral runners, provisioning may include VM allocation, image pulling, agent installation, credential fetching, and controller registration. For warm-pool runners, machines are pre-initialized so per-job provisioning time can be very small, though maintaining the pool carries ongoing cost.

### 6.3. Jobs Waiting on Dependencies Are Not Runner Capacity Shortages

If a job is not yet eligible because `needs` or upstream dependencies have not finished, it should not be counted as queue time. Analyze dependency wait separately to tell whether the pipeline is slow due to DAG structure or runner capacity.

## 7. Measuring Individual Job and Step Execution Time

Job duration helps identify which tasks consume the most time after a runner is ready.

You should track:

- Duration of each job across multiple runs.
- Duration of each step within a job.
- p50, p90, p95, and max instead of only averages.
- Job failure, retry, and timeout rates.
- Duration by runner image and machine type.
- Duration by cache hit/miss.
- Artifact download/upload time.
- Checkout and dependency resolution time.

### 7.1. Comparing the Same Type of Job

Do not compare an integration-test job directly against lint and conclude one is anomalous. Compare the same job name, same runner type, and same workload across runs.

When job duration increases, check:

- Did the commit add tests or workload?
- Did dependencies change?
- Was the cache missed or invalidated?
- Is the runner experiencing CPU throttling or memory pressure?
- Is an artifact or package download step slow?
- Did the number of tests, shards, or matrix entries change?
- Is the job retrying internally without showing up as a separate job?

### 7.2. Step Duration for Pinpointing Root Causes

Job duration points to a slow job; step duration points to the slow step. For example, a build job increases from 4 to 9 minutes. If checkout stays at 15 seconds and compile increases by 20 seconds, but dependency resolution jumps from 30 seconds to 4 minutes, the team should investigate the package repository, lockfile, cache, or network.

Give steps clear and stable names. If every commit renames steps, historical comparison becomes harder. For long commands, create sub-steps or instrumentation to measure dependency downloads, compilation, testing, and uploads separately.

### 7.3. Matrix Jobs

A matrix job creates multiple executions corresponding to OS, runtime, or version combinations. Store matrix dimensions while limiting label cardinality. When analyzing, check:

- Which job in the matrix is the slowest?
- Which runner pool has high queue times?
- Is one OS/version consistently slower?
- Can fail-fast be enabled where appropriate?
- Are unnecessary combinations running on every pull request?

Do not look only at the duration of a single representative matrix job if instances vary significantly in runtime.

## 8. Analyzing End-to-End Feedback and the Critical Path

End-to-end pipeline time does not equal the sum of all job durations. With parallel jobs, most work can happen concurrently. To understand slow feedback, examine the dependency graph and critical path.

An analysis approach:

1. Identify the workflow trigger timestamp.
2. Determine when each job becomes eligible to run.
3. Calculate dependency wait and queue/provisioning separately.
4. Calculate the duration of each job and step.
5. Identify the dependency chain that finishes last.
6. Compare against when required checks and feedback are published.

### 8.1. The Longest-Running Job Is Not Always the Bottleneck

A 10-minute job running in parallel with another 10-minute branch may sit on the critical path. An 8-minute job that does not block required results might not affect pull request feedback time.

Identify which jobs are holding back downstream dependencies. Optimizing a job on the critical path typically has a greater impact than optimizing a non-blocking job.

### 8.2. Optimizing First Feedback

You can arrange fast, high-signal checks to run early:

- Syntax, formatting, and lint.
- Fast unit tests.
- Configuration and schema validation.
- Compile/build checks.
- Integration tests and resource-intensive checks.

Ordering should be based on dependencies and reliability. Never skip required checks just to make the first result appear earlier. The goal is to catch simple mistakes early while keeping full gates intact before merge/release.

## 9. Metrics and Percentiles for Pipeline Timing

Durations typically have a skewed distribution: most jobs run quickly, while a few wait long or hit cache misses. Averages are easily distorted by outliers and fail to reflect the experience of most runs.

You should track:

- **p50:** typical duration for half of the jobs.
- **p90:** 90% of jobs complete within this time.
- **p95:** useful for detecting slow tail experiences.
- **p99:** shows very slow runs, though it requires sufficient sample size.
- **Max:** useful for finding extreme incidents, not as a standalone target.
- **Count:** number of runs used to compute the percentiles.

### 9.1. Histogram for Queue Time

If your instrumentation emits the histogram `ci_job_queue_duration_seconds`, you can query p95 by runner pool:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, runner_pool) (
    rate(ci_job_queue_duration_seconds_bucket[1h])
  )
)
~~~

This is an illustrative metric; you need to create the corresponding histogram and labels in your telemetry system. To view p95 by job:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, job_name) (
    rate(ci_job_queue_duration_seconds_bucket[1h])
  )
)
~~~

### 9.2. Histogram for Job Duration

~~~promql
histogram_quantile(
  0.95,
  sum by (le, job_name) (
    rate(ci_job_duration_seconds_bucket[1h])
  )
)
~~~

You can build similar metrics for runner provisioning, step duration, and end-to-end feedback. Choose bucket boundaries suited to real timescales: queue times may be measured in seconds, while integration tests can span tens of minutes.

### 9.3. Do Not Combine Fundamentally Different Groups

A single histogram aggregating all jobs can be misleading. A 5-second lint job and a 15-minute integration test have very different distributions. Group by job class or stage while keeping labels low-cardinality and stable.

When viewing p95, always display the sample count. A p95 from 20 samples is far less reliable than a p95 from thousands of samples. For infrequently run groups, inspect raw runs or use a longer time window.

## 10. Dashboards for Monitoring Wait Time and Job Duration

A useful dashboard should quickly answer:

- How long are jobs waiting for runners?
- Which pool has rising queue times?
- Is runner provisioning slow?
- Which jobs or steps consume the most time?
- Which critical path governs end-to-end pipeline duration?
- How is feedback time changing day over day or week over week?
- Are job failure, timeout, and retry rates rising alongside runtimes?

A reference dashboard layout:

| Panel | Content | Grouping |
|---|---|---|
| Queue time | p50/p95 queue duration | Runner pool, job class |
| Provisioning | p50/p95 runner startup | Runner image, machine type |
| Job duration | p50/p95 duration | Job name, stage |
| Step duration | Top slowest steps | Job name, step |
| Feedback time | Trigger to first/required feedback | Workflow, branch type |
| Queue depth | Number of eligible jobs waiting | Runner pool |
| Runner capacity | Busy/idle/starting/available | Pool, machine type |
| Reliability | Fail, timeout, retry rate | Job class, runner pool |
| Data quality | Rate of missing events or anomalous durations | Provider, runner image |

### 10.1. Release and Change Markers

When runner images, concurrency limits, cache policies, or workflows change, annotate the dashboard with markers. This makes it easy to compare before and after the change and see whether queue or job duration improvements coincide with a specific update.

### 10.2. Data Protection and Cardinality

Do not use email addresses, usernames, commit SHAs, or run IDs as labels on every metric time series. Those fields belong in logs/events for drill-down. Metrics should use bounded dimensions such as repository group, workflow, job name, runner pool, OS, and result.

Dashboards displaying repository names or internal pipeline details need appropriate access controls. Do not expose secrets or command lines containing tokens in logs just to improve diagnostics.

## 11. Reading Data to Find Bottlenecks

Combining queue, provisioning, job, and step durations helps isolate the category of root cause.

| Observed Pattern | Likely Cause | What to Check |
|---|---|---|
| Queue p95 rises, job duration stable | Insufficient runners or scheduler throttling | Capacity, concurrency, quotas, and labels |
| Queue low, provisioning high | Slow autoscaler or runner startup | Warm pool, image pull, bootstrap, and cloud API |
| Queue and provisioning low, job duration rises | Work inside the job is slow | Step timings, CPU/memory, dependencies, and cache |
| One step spikes suddenly | Localized bottleneck | Logs, network, artifacts, tests, or commands |
| Pipeline duration high, individual job durations normal | Dependency wait or critical path | DAG, `needs`, and stage ordering |
| p50 stable, p95/p99 rises | Outliers, uneven pool, or burst traffic | Runner breakdown, time of day, and job class |
| Job duration low, feedback time high | Slow feedback publishing or downstream gate | Required checks, report upload, and notifications |
| Queue rises during peak hours | Capacity cannot keep up with demand | Autoscaling, scheduled runs, and concurrency |
| One runner image is consistently slow | Problematic image or toolchain | Startup scripts, image size, package installation |
| Duration drops while failure rate rises | Steps may have been skipped or timeouts too aggressive | Compare gates, retries, and quality results |

Never optimize based on a single anomalous run. Check trends, sample counts, concurrent changes, and the stability of the measurement system.

## 12. Using Measurements to Improve Feedback Time

Once the bottleneck is identified, choose actions tailored to the dominant time interval.

### 12.1. When Queue Time Is High

- Scale up or autoscale runner pools based on actual demand.
- Create warm pools for machine types that take long to initialize.
- Separate pools by workload and trust level.
- Adjust concurrency limits or quotas when justified.
- Avoid requesting overly specialized labels or machine types unless needed.
- Use larger runners when small jobs queue due to lack of matching machines, while measuring cost and throughput.
- Prioritize jobs appropriately.

Adding more runners does not always solve queuing. If the bottleneck is cloud quotas, the package registry, or a shared test database, adding runners can overload those dependencies further.

### 12.2. When Provisioning Time Is High

- Build runner images with required toolchains pre-installed.
- Reduce package downloads during startup scripts.
- Use image caching or warm runners where appropriate.
- Measure VM creation, image pull, bootstrap, and agent registration separately.
- Inspect cloud APIs, networking, and registries during initialization.
- Remove duplicate installation steps present in both the image and the job.

### 12.3. When Job/Step Duration Is High

- Use dependency caching with proper keys and controlled invalidation.
- Run independent tests in parallel.
- Split test suites into balanced shards.
- Reduce redundant artifact or dependency downloads.
- Avoid rebuilding the same artifact across stages just to swap environment config.
- Optimize high-duration steps on the critical path.
- Use incremental builds when supported by tools and correctness can be guaranteed.
- Narrow data or scope for fast pull-request tests while keeping full gates for releases.

### 12.4. When Dependency Wait or Critical Path Is High

- Verify whether job dependencies are truly necessary.
- Allow independent lint and unit tests to run early.
- Separate artifact preparation jobs from tests that do not depend on those artifacts where appropriate.
- Avoid unnecessary sequential dependency chains.
- Combine steps into a single job only when startup overhead exceeds the benefit of parallelism.
- Avoid creating too many tiny jobs if each must provision a runner and re-checkout the code.

Parallelism carries overhead. Splitting a 2-minute job into 20 tiny jobs can add more queue and provisioning time than it saves. Measure before and after on the same workload.

## 13. Setting Objectives and Evaluating Changes

No single queue time or job duration threshold fits every organization. Objectives should reflect developer experience, workflow type, job count, and how critical the feedback is.

You can set internal SLIs/SLOs, for example:

- Runner pool p95 queue time below an agreed threshold.
- Pull request p95 time to first feedback below a target.
- Unit test p95 job duration not exceeding an acceptable growth limit.
- Missing-telemetry job rate below a small threshold.
- Retry or timeout rates not increasing after optimization.

Illustrative policy example:

~~~yaml
pipeline_timing:
  measurements:
    - dependency_wait
    - runner_queue
    - runner_provisioning
    - job_duration
    - step_duration
    - time_to_first_feedback
    - time_to_required_checks

  reporting:
    percentiles:
      - p50
      - p90
      - p95
    include_sample_count: true
    group_by:
      - workflow
      - job_name
      - runner_pool
      - result

  objectives:
    pull_request:
      queue_p95_seconds: 60
      first_feedback_p95_seconds: 180
    data_quality:
      missing_timestamps: 0
      negative_durations: 0
~~~

The numbers in this example are only meant to illustrate how to express objectives, not a universal standard. Base your targets on baselines, team expectations, and platform capacity. Do not optimize duration by dropping required checks or reducing test coverage without evaluating risk.

### 13.1. Comparing Before and After Optimization

When evaluating a change:

1. Select representative workflows and jobs.
2. Collect a baseline with a sufficient number of runs.
3. Keep workload, runner type, and time of day constant or record them.
4. Change one group of factors at a time if possible.
5. Compare p50/p95, sample count, queue, provisioning, job, and feedback times.
6. Check failure rate, retry rate, and gate quality.
7. Document the results and decide whether to keep, adjust, or revert the change.

A good optimization reduces wait or execution time without increasing errors, degrading check quality, or overloading dependencies.

## 14. Troubleshooting Anomalous Timing Data

| Symptom | Possible Cause | What to Check |
|---|---|---|
| Negative queue duration | Clock skew or out-of-order timestamps | Synchronize clocks, inspect event sources |
| Job duration equals 0 | Missing timestamps, rounding, or skipped job | Check result and event completeness |
| Queue time suddenly drops to 0 for all jobs | Metric instrumentation stopped emitting events | Check exporter and pipeline telemetry |
| Job duration rises while step durations stay flat | Startup/teardown or gaps inside the job | Measure checkout, setup, artifacts, and cleanup |
| p95 rises while average stays stable | A subset of jobs or runners is slow | Break down by pool, job name, and time of day |
| Total job duration exceeds pipeline duration | Multiple jobs running in parallel | Inspect DAG and critical path |
| Feedback time exceeds last job completion time | Slow report upload, check publishing, or notification | Measure publishing time separately |
| A runner pool has high queue despite idle machines | Label mismatch or scheduler not selecting runners | Check labels, eligibility, and policies |
| Job starts late despite runner being ready | Agent registration, workspace, or setup | Measure the startup gap |
| Duration fluctuates wildly between runs | Workload, cache, runner contention, or test data | Group by cache hit, machine type, and workload |

If data is incomplete, do not replace missing values with 0. Record unknown, missing, or exclude the sample from calculations with a separate metric for missing-data rate. Otherwise, percentiles will look artificially good.

## 15. Sample Scenario: Identifying Why Pull Request Feedback Is Slow

A team notices that pull requests typically take around 12 minutes to complete all required checks, without knowing why.

1. The team adds event timestamps for workflow trigger, job eligible, runner assigned, runner ready, job start, and job completion.
2. The dashboard shows `linux-large` p95 queue time rising to 3 minutes during peak hours.
3. Provisioning time for that pool is only around 12 seconds, so machine startup is not the main bottleneck.
4. The `unit-test` job has an execution duration p95 of about 6 minutes, up from 4 minutes as test count grew.
5. Step breakdown reveals that most of the time is spent on integration-style tests running inside the `unit-test` job.
6. The team splits fast tests and database-backed tests into two jobs while keeping the corresponding required checks.
7. Lint and fast unit tests run in parallel to deliver early first feedback; database-backed tests continue running and remain a required gate.
8. The team increases `linux-large` capacity in a controlled way during peak hours, then re-measures p95 queue time.
9. After one week, p95 queue drops, first feedback is shorter, and required checks complete faster. Failure rates and test coverage do not degrade.
10. The team documents the baseline, runner pool changes, DAG adjustments, and measurement results so other teams can learn from them.

This scenario shows that a single 12-minute total is not enough to decide whether to add runners or optimize tests. Only by separating queue, provisioning, execution, and critical path can the team choose the right action.

## 16. Practice Roadmap

You can practice on a sample CI workflow following these steps:

1. **List jobs and dependencies:** draw the DAG, identifying parallel jobs and jobs that block results.
2. **Standardize timestamps:** record workflow trigger, job eligible, runner assignment, runner ready, job start, and job completion.
3. **Calculate durations:** dependency wait, queue, provisioning, startup, job, and end-to-end feedback.
4. **Measure step durations:** add stable step names and record start/end times.
5. **Build a dashboard:** display p50/p90/p95, sample count, queue depth, and runner capacity.
6. **Group data:** slice by runner pool, job name, stage, OS, and result.
7. **Find the critical path:** identify the dependency chain governing required feedback.
8. **Simulate high queue time:** limit runners in a test environment and observe queue duration.
9. **Simulate a slow job:** increase workload or disable cache in a test run to observe step duration changes.
10. **Propose optimizations:** choose capacity, provisioning, caching, parallelism, or DAG changes based on evidence.
11. **Measure before/after:** compare equivalent workloads while tracking sample count and failure rate.
12. **Verify telemetry quality:** confirm there are no negative durations, missing events, or uncontrolled label cardinality.

### Completion Criteria

Learners can consider the practice complete when they can demonstrate:

- Distinguishing dependency wait, runner queue, provisioning, startup, job duration, and step duration.
- Selecting the right `job_eligible_at` timestamp to measure pure queue time for jobs with dependencies.
- Explaining the limitations when a platform only provides queued and started timestamps.
- Calculating durations from timestamps and detecting clock skew.
- Distinguishing job duration from pipeline duration and critical path.
- Measuring first feedback and time to required checks.
- Analyzing p50/p90/p95/p99 alongside sample count.
- Grouping queue/job durations by runner pool and job class.
- Identifying bottlenecks from dashboards and step breakdowns.
- Proposing optimizations backed by before/after measurements without degrading gate quality.

## Conclusion

To improve CI/CD feedback speed, separately measure the time a job waits for a runner, the time the runner takes to provision, the execution time of each job and step, and the end-to-end time from trigger to result. Timestamps must have unified definitions; dependency wait must not be mistaken for queue time; and provisioning must not be lumped into queue time when the system can separate them.

Dashboards should show percentiles, sample counts, queue depth, runner capacity, and durations by job and step. Combined with the dependency graph and critical path, teams can determine whether to add capacity, shorten startup, optimize steps, or change execution order. Every improvement should be compared before and after on equivalent workloads while preserving check quality. That way, a "slow pipeline" becomes a measurable, explainable, and evidence-driven engineering problem.
