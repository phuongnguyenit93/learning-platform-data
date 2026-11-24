# Per-Job Failure Rate in Spring Batch

## 1. What Does Per-Job Failure Rate Tell You?

In a Spring Batch system, a job may run hundreds of times per day, once per night, or only on events. Seeing a `JobExecution` with status `FAILED` is useful for investigating a specific incident. However, to assess **the stability of each job over time**, we need an aggregate indicator: **per-job failure rate**.

For example, in the last 24 hours:

| Job | Successful completed runs | Failed runs | Failure rate |
| --- | ---: | ---: | ---: |
| `importOrdersJob` | 90 | 10 | 10% |
| `settlePaymentsJob` | 19 | 1 | 5% |
| `exportReportsJob` | 1 | 0 | 0% |
| `monthEndClosingJob` | 0 | 0 | Insufficient data |

Even though `exportReportsJob` has a 0% rate, the data contains only a single run. You cannot conclude it is more reliable than a job running 100 times. For `monthEndClosingJob`, there were no runs in the 24-hour window; display **N/A**, never convert it to 0%.

Within **Spring Batch Core Processing → Monitoring**, this lesson focuses on:

1. Defining the denominator and what constitutes a "failed run."
2. Retrieving execution outcomes from `JobRepository` or Micrometer.
3. Calculating, visualizing, and alerting on failure rate **per job**.
4. Avoiding distortions caused by restarts, retries, unfinished states, missing data, or overly short observation windows.
5. Testing the measurement so charts genuinely reflect batch job behavior.

A clearly defined rate is a prerequisite for setting SLO thresholds, comparing deployment versions, and deciding when an incident requires intervention.

## 2. Understanding JobInstance, JobExecution, and Statuses Correctly

### 2.1. One Logical Job Can Have Multiple Executions

In Spring Batch:

- `Job` is the job definition, e.g., `importOrdersJob`.
- `JobInstance` is a logical unit of work, identified by job name plus **identifying `JobParameters`**.
- `JobExecution` is a single attempt to run that `JobInstance`. An instance can have multiple executions if the first attempt fails and is restarted.
- `StepExecution` stores each step's status; a multi-step job can fail at any step.

```text
Job: importOrdersJob
 |
 +-- JobInstance: businessDate=2026-11-15
 |      |
 |      +-- JobExecution #101 -> FAILED
 |      +-- JobExecution #102 -> COMPLETED (restart succeeded)
 |
 +-- JobInstance: businessDate=2026-11-16
        |
        +-- JobExecution #103 -> COMPLETED
```

If counted by **execution**, there are 3 attempts and 1 failure: the rate is **33.33%**. If evaluated by **final outcome of each instance**, 2 instances ultimately succeeded: the final rate is **0%**. Both calculations are useful, but they answer **two different questions**:

| Measure | Core question | How to interpret |
| --- | --- | --- |
| *Execution failure rate* | How many run attempts ended in failure? | Operational health, frequency of interventions/restarts |
| *Final instance failure rate* | How many logical jobs ultimately failed to complete? | Ability to finish work after allowing recovery |
| *First-attempt failure rate* | How many jobs failed on their initial run? | Initial reliability, degree of reliance on retries/restarts |
| *Consecutive failures* | How many times in a row has the job failed? | Detects outage trends even with small sample sizes |

Saying "per-job failure rate" without specifying the counting unit allows two teams to report different numbers while reading the same `JobRepository`. This article uses **execution failure rate** as the primary metric and presents the other metrics where needed.

### 2.2. Distinguishing BatchStatus and ExitStatus

Spring Batch has two status types to keep distinct:

- `BatchStatus` describes execution lifecycle: `STARTING`, `STARTED`, `STOPPING`, `STOPPED`, `FAILED`, `COMPLETED`, `ABANDONED`, `UNKNOWN`.
- `ExitStatus` represents the result/exit code used by job flow routing, which can be customized by the application, such as `COMPLETED WITH SKIPS`.

The `STARTING`, `STARTED`, and `STOPPING` statuses indicate the execution is running or preparing to run. They are **not terminal outcomes** and must not be included in the denominator of a completed success/failure rate.

`STOPPED` usually means the job was stopped intentionally or by an orchestration mechanism; do not equate it with `FAILED` by default. `ABANDONED` and `UNKNOWN` should also not be automatically bucketed into either group without an explicit operational policy.

| `BatchStatus` | Included in standard failure rate denominator? | How to monitor |
| --- | --- | --- |
| `COMPLETED` | Yes, success group | Counts as one successful execution |
| `FAILED` | Yes, failure group | Counts as one failed execution |
| `STOPPED` | No, under this article's default definition | Track stop rate separately |
| `ABANDONED` | No | Track manual interventions / abandoned runs |
| `UNKNOWN` | No | Alert on unknown status; requires investigation |
| `STARTED`, `STARTING`, `STOPPING` | No | Monitor active jobs, long-running, or hung runs |

A job with `BatchStatus.COMPLETED` that skipped items under a policy can still be a **technical success**. If business rules require "no invoice missed," add a **processing quality metric**; do not treat every case with `skipCount > 0` as `FAILED`.

## 3. Standard Formula and Choosing the Denominator

Let:

- `F(J, W)`: number of `JobExecution`s of job `J` with `BatchStatus.FAILED` ending within time window `W`.
- `C(J, W)`: number of `JobExecution`s of job `J` with `BatchStatus.COMPLETED` ending within time window `W`.
- `N(J, W) = F(J, W) + C(J, W)`: number of executions with terminal outcomes eligible for the calculation.

When `N > 0`:

\[
\text{FailureRate}(J,W)=\frac{F(J,W)}{F(J,W)+C(J,W)}
\]

As a percentage:

\[
\text{FailureRatePct}(J,W)=100\times\text{FailureRate}(J,W)
\]

If `N = 0`, the result is **undefined** (`NULL`/`N/A`). The metric is not 0%.

**Example:** `importOrdersJob` has 16 `COMPLETED` and 4 `FAILED` in one day: `F=4`, `C=16`, `N=20`, so failure rate = `4/20 = 0.20 = 20%`.

Do not compute:

- `FAILED / all JobExecution records` while many executions are `STARTED`.
- `FAILED / lines read by ItemReader`: that is an item count, not a job run count.
- `FAILED / number of JobInstances` while the numerator still counts JobExecutions: numerator and denominator use different units.
- Unweighted average of per-job failure rates called a system-wide failure rate; each job runs at a different frequency.

### 3.1. When Should STOPPED Count as Failure?

Some organizations treat an unplanned `STOPPED` as an incident counted against SLO. If so, give it a distinct name, for example:

\[
\text{UnsuccessfulRate}=\frac{FAILED+UNEXPECTED\_STOPPED}{COMPLETED+FAILED+UNEXPECTED\_STOPPED}
\]

Do not change classification rules on a dashboard without clear annotations, as numbers before and after the change will no longer be directly comparable. A planned maintenance stop and a system-error stop may need different reason labels.

### 3.2. Stability by Sample Size

If a job runs once and fails, the failure rate is 100%. If another job runs 100 times and fails once, the rate is 1%. The first job's rate may reflect a severe incident, but a single run cannot estimate long-term reliability.

Therefore, dashboards should show **F / N** alongside the percentage. When alerting on percentages, require a minimum run count in the window; for infrequent jobs, use **per-failure or consecutive-failure alerts** instead of waiting for enough samples.

## 4. Choosing the Time Window for the Rate

A failure rate without a time window is hard to interpret. Common windows include:

| Window | Purpose | Notes |
| --- | --- | --- |
| 15 minutes / 1 hour | Detect newly emerging errors in high-frequency jobs | Unsuitable for daily-only jobs |
| 24 hours | Daily operational monitoring | Once-daily jobs have a very small sample |
| 7 days | Observe trends for daily jobs | Can mask newly introduced incidents |
| 30 days | Track long-term targets / SLOs | Requires sufficient metadata and metrics retention |
| By `businessDate` | Reconcile business cycles | May differ from the calendar date the job actually ended |

Assign executions to windows by **`END_TIME`** when measuring outcomes recorded during that window. For instance, a job starting at 23:58 and finishing at 00:03 falls into the new day by `END_TIME`, even though its input belongs to the prior day's `businessDate`.

In the database, use a half-open interval `[startInclusive, endExclusive)`:

```text
END_TIME >= 2026-11-15T00:00:00Z
END_TIME <  2026-11-16T00:00:00Z
```

If a dashboard uses dates in a business timezone, convert day boundaries from an agreed `ZoneId` into timestamps compatible with the database; never assume the SQL server, JVM, dashboard, and scheduler share the same timezone.

**Windows with zero runs** require a separate *freshness/missing run* metric. No jobs running may mean the scheduler broke; a standalone failure-rate chart will not catch this.

## 5. Data Source 1: JobRepository and Metadata Tables

`JobRepository` is the durable metadata store for Spring Batch executions. In common JDBC repositories, two key tables are:

- `BATCH_JOB_INSTANCE`: holds `JOB_INSTANCE_ID` and `JOB_NAME`.
- `BATCH_JOB_EXECUTION`: holds `JOB_EXECUTION_ID`, `JOB_INSTANCE_ID`, `STATUS`, `CREATE_TIME`, `START_TIME`, `END_TIME`, and exit details.

To compute rates **by job name**, join execution to instance via `JOB_INSTANCE_ID`. Avoid querying the step table and counting `FAILED` steps because one job can have many steps; the unit to count here is **JobExecution**.

### 5.1. SQL for Per-Job Failure Rate

The example below uses standard SQL compatible with PostgreSQL, H2, and many other RDBMSs; `:fromTime` and `:toTime` are placeholders bound by your query tool or `NamedParameterJdbcTemplate`:

```sql
SELECT
    ji.JOB_NAME AS job_name,
    SUM(CASE WHEN je.STATUS = 'FAILED' THEN 1 ELSE 0 END) AS failed_runs,
    SUM(CASE WHEN je.STATUS = 'COMPLETED' THEN 1 ELSE 0 END) AS completed_runs,
    COUNT(*) AS terminal_runs,
    100.0 * SUM(CASE WHEN je.STATUS = 'FAILED' THEN 1 ELSE 0 END)
        / NULLIF(COUNT(*), 0) AS failure_pct
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_JOB_INSTANCE ji
    ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE je.END_TIME >= :fromTime
  AND je.END_TIME < :toTime
  AND je.STATUS IN ('FAILED', 'COMPLETED')
GROUP BY ji.JOB_NAME
ORDER BY failure_pct DESC, terminal_runs DESC;
```

How it works:

1. `WHERE ... END_TIME` selects only executions **that finished within the measurement window**.
2. `STATUS IN ('FAILED', 'COMPLETED')` establishes a clean denominator; `STOPPED` and non-terminal states are tracked by separate metrics.
3. `COUNT(*)` counts executions with outcomes included in the metric.
4. `NULLIF(COUNT(*),0)` guards the division if the query structure is modified later; within grouped rows, count is already greater than 0.
5. `ORDER BY` puts jobs with higher failure rates first, then orders by sample size.

The query only returns jobs **with at least one qualifying execution** in the window. To display jobs with zero runs as **N/A**, join results against a managed job list (job catalog or scheduler config) rather than defaulting them to 0%.

**Watch out for database schema/version differences:** timestamp column types, table prefixes, migration patterns, and read permissions vary by Spring Batch setup. Use your deployment's actual schema. Metadata queries should run with appropriate read permissions or against a read replica if monitoring query volume is high.

### 5.2. Reading via JobExplorer

When a Java API is preferred over querying tables directly, Spring Batch provides `JobExplorer` to look up `JobInstance` and `JobExecution`.

Illustrative Java example for Spring Batch 5.x:

```java
import java.time.Instant;
import java.util.List;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.explore.JobExplorer;

public record FailureSummary(
        long failed, long completed, Double failureRate) {}

public final class JobFailureRateService {
    private final JobExplorer jobExplorer;

    public JobFailureRateService(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public FailureSummary summarize(
            String jobName, Instant from, Instant to) {

        long failed = 0;
        long completed = 0;

        int offset = 0;
        int pageSize = 100;

        while (true) {
            List<JobInstance> instances =
                    jobExplorer.getJobInstances(jobName, offset, pageSize);
            if (instances.isEmpty()) {
                break;
            }

            for (JobInstance instance : instances) {
                for (JobExecution execution :
                        jobExplorer.getJobExecutions(instance)) {
                    if (execution.getEndTime() == null) {
                        continue;
                    }

                    Instant endedAt =
                            execution.getEndTime().toInstant(
                                    java.time.ZoneOffset.UTC);
                    // Note: see timezone explanation below.
                    if (endedAt.isBefore(from) || !endedAt.isBefore(to)) {
                        continue;
                    }

                    if (execution.getStatus() == BatchStatus.FAILED) {
                        failed++;
                    } else if (execution.getStatus() == BatchStatus.COMPLETED) {
                        completed++;
                    }
                }
            }
            offset += instances.size();
            if (instances.size() < pageSize) {
                break;
            }
        }

        long total = failed + completed;
        Double rate = total == 0 ? null : (double) failed / total;
        return new FailureSummary(failed, completed, rate);
    }
}
```

In Spring Batch 5.x, `JobExecution.getEndTime()` returns `LocalDateTime`, meaning it **does not carry a timezone**. The `toInstant(ZoneOffset.UTC)` call in the example is only valid if the system consistently stores and reads metadata in UTC. If the repository uses a different timezone, convert according to that convention. For operational dashboards, prefer SQL queries using database-consistent timestamps and controlled parameter binding.

**Performance note:** scanning all instances from the beginning and filtering by time is only suitable for API demonstrations or small datasets. With large execution counts, it becomes very expensive; a time-filtered SQL query in the database or an aggregated metrics system is far more appropriate.

> **Version note:** `JobExecution`/`JobInstance` imports and some package organizations changed between Spring Batch 5 and 6. The code example above uses the Spring Batch 5.x structure; when using 6.x, check the API for your project version.

## 6. Data Source 2: Micrometer and the Metrics System

In Spring Batch applications using Micrometer/Spring Boot Actuator, metrics can be collected via listeners or built-in framework instrumentation. Spring Batch provides timers/observations measuring job execution, step execution, and related activities; **metric names, tags, and export behavior depend on the Spring Batch/Micrometer version, registry, and configuration**.

For example, a framework-recorded timer metric may provide sample counts after exporter conversion to Prometheus as a series with a `_count` suffix. Before writing PromQL, inspect `/actuator/prometheus` or scraped data directly to verify the **actual metric names and labels**. Do not assemble names from memory assuming every version produces the exact same string.

If the system wants an explicit, stable metric aligned with operations team contracts, you can create a **counter per terminal outcome** using `JobExecutionListener`.

### 6.1. Defining a Custom Metric

Convention:

```text
Logical metric name: batch.job.executions
Metric type: Counter
Tags:
    job.name = importOrdersJob
    status   = COMPLETED | FAILED | STOPPED
```

After exporting to Prometheus, the metric and label names may be normalized to:

```text
batch_job_executions_total{
  job_name="importOrdersJob",
  status="FAILED"
}
```

The name above is an **illustrative application-defined convention**, not a guaranteed default metric name across all Spring Batch versions.

### 6.2. Installing a Listener to Record Outcomes

Spring Batch 5.x example with Micrometer:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.stereotype.Component;

@Component
public class JobOutcomeMetricsListener implements JobExecutionListener {

    private final MeterRegistry registry;

    public JobOutcomeMetricsListener(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void afterJob(JobExecution execution) {
        BatchStatus status = execution.getStatus();
        if (status != BatchStatus.COMPLETED
                && status != BatchStatus.FAILED
                && status != BatchStatus.STOPPED) {
            return;
        }

        String jobName = execution.getJobInstance().getJobName();

        Counter.builder("batch.job.executions")
                .description("Finished Spring Batch job executions")
                .tag("job.name", jobName)
                .tag("status", status.name())
                .register(registry)
                .increment();
    }
}
```

The listener must actually be attached to the **Job**:

```java
@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        Step importOrdersStep,
        JobOutcomeMetricsListener metricsListener) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .listener(metricsListener)
            .start(importOrdersStep)
            .build();
}
```

In Spring Batch 5.x, `JobBuilder` is in `org.springframework.batch.core.job.builder`. With annotation-based or custom builder configurations, ensure the listener is not omitted. The metric should appear after the execution **finishes** and the listener runs.

### 6.3. Limitations of `afterJob` and Counters

`afterJob(...)` is useful for near real-time monitoring, but **it is not an immutable transactional record**:

- If the JVM is killed, loses power, or crashes before the listener runs or metrics are scraped, the failure event may never be emitted as a metric.
- In-process counters reset when a pod restarts; Prometheus typically handles resets in `increase(...)`, yet sufficient scrape samples are still required.
- If an outcome is replayed or recorded twice by another instrumentation mechanism, the counter may double-count. Ensure a clear single instrumentation contract per `JobExecution`.
- When jobs run across multiple JVMs, aggregate by job and status across all instances; do not count per pod as separate jobs when the goal is an overall rate.
- `JobRepository` metadata is the right source for **reconciling** gaps caused by restarts, crashes, or missing metrics scrapes.

Never stuff `jobExecutionId`, `runId`, customer IDs, transaction IDs, or exception messages into **metric labels**: cardinality will explode rapidly. Those details belong in structured logs, traces, or audit databases; metrics need only bounded-value labels such as `job.name` and `status`.

## 7. Calculating Rates with PromQL

Assume the exporter actually exposes the counter:

```text
batch_job_executions_total{job_name="importOrdersJob",status="COMPLETED"}
batch_job_executions_total{job_name="importOrdersJob",status="FAILED"}
```

### 7.1. Failures in 24 Hours

```promql
sum by (job_name) (
  increase(batch_job_executions_total{status="FAILED"}[24h])
)
```

`increase(...)` calculates counter growth over the window while handling counter resets per Prometheus semantics. If the metric carries additional labels like `instance`, `pod`, or `application`, `sum by(job_name)` aggregates series for the same job. In multi-environment setups, include `environment`, `service`, or namespace labels so production is never mixed with staging.

### 7.2. Failure Rate Per Job

```promql
100 *
sum by (job_name) (
  increase(batch_job_executions_total{status="FAILED"}[24h])
)
/
sum by (job_name) (
  increase(
    batch_job_executions_total{status=~"COMPLETED|FAILED"}[24h]
  )
)
```

This implements `100 * F / (F+C)`. When the denominator has no executions, dashboards should display **N/A** or "No runs"; configure empty/absent handling rather than turning it into 0%.

In Prometheus, a series appears only after it has been created and scraped; for example, a job that has never failed may **lack a `status="FAILED"` series**. In that case, the numerator becomes an empty vector, causing the chart to drop the job even though it succeeded. Consider **pre-initializing counters for each status of known jobs** or handling zero-fill from the completed/failed set carefully. For critical SLO metrics, reconcile against `JobRepository` to catch missing data regions.

Additionally, `increase` extrapolates from scrape samples and can return fractional values even though actual execution counts are integers. With low traffic and newly created metrics, numbers may differ slightly from metadata queries; this is inherent to windowed counter estimation, not necessarily a bug in the job.

### 7.3. Alerting with Minimum Sample Size

Suppose operations defines: **alert if failure rate exceeds 10% in one hour and at least 10 executions completed in that hour**.

```promql
(
  sum by (job_name) (
    increase(batch_job_executions_total{status="FAILED"}[1h])
  )
  /
  sum by (job_name) (
    increase(
      batch_job_executions_total{status=~"FAILED|COMPLETED"}[1h]
    )
  )
) > 0.10
and on (job_name)
sum by (job_name) (
  increase(
    batch_job_executions_total{status=~"FAILED|COMPLETED"}[1h]
  )
) >= 10
```

These are **illustrative thresholds only**. Choose real thresholds according to run frequency, job criticality, SLOs, and recoverability. A critical payment job may require immediate alerting on a single `FAILED`; a high-frequency experimental job can be evaluated over 1-hour/24-hour trends.

For infrequent jobs, percentage-based rules may never meet the minimum sample requirement. Supplement them with alerts on **latest failure**, **consecutive failures**, and **overdue without a successful run**.

## 8. JobExecution Failure Rate vs. JobInstance Final Failure Rate

Execution-level failure rate can be high while the job still self-recovers through restarts. For example:

| JobInstance | Execution 1 | Execution 2 | Final outcome |
| --- | --- | --- | --- |
| Day D1 | FAILED | COMPLETED | Succeeded |
| Day D2 | COMPLETED | — | Succeeded |
| Day D3 | FAILED | FAILED | Not yet succeeded |

Counted by execution: `F=3`, `C=2`, rate **60%**. Counted by the latest status of each instance: 1 failed instance out of 3, rate **33.33%**. This is not a contradiction; each calculation uses a different counting unit.

### 8.1. SQL to Fetch the Latest Status of Each Instance

Example using a window function:

```sql
WITH ranked_executions AS (
    SELECT
        ji.JOB_NAME,
        je.JOB_INSTANCE_ID,
        je.JOB_EXECUTION_ID,
        je.STATUS,
        je.END_TIME,
        ROW_NUMBER() OVER (
            PARTITION BY je.JOB_INSTANCE_ID
            ORDER BY je.CREATE_TIME DESC, je.JOB_EXECUTION_ID DESC
        ) AS rn
    FROM BATCH_JOB_EXECUTION je
    JOIN BATCH_JOB_INSTANCE ji
      ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
),
latest AS (
    SELECT JOB_NAME, JOB_INSTANCE_ID, STATUS, END_TIME
    FROM ranked_executions
    WHERE rn = 1
)
SELECT
    JOB_NAME,
    SUM(CASE WHEN STATUS = 'FAILED' THEN 1 ELSE 0 END)
        AS failed_instances,
    SUM(CASE WHEN STATUS = 'COMPLETED' THEN 1 ELSE 0 END)
        AS completed_instances,
    COUNT(*) AS terminal_instances,
    100.0 * SUM(CASE WHEN STATUS = 'FAILED' THEN 1 ELSE 0 END)
        / NULLIF(COUNT(*), 0) AS final_failure_pct
FROM latest
WHERE END_TIME >= :fromTime
  AND END_TIME < :toTime
  AND STATUS IN ('FAILED', 'COMPLETED')
GROUP BY JOB_NAME;
```

The query fetches **the currently latest execution** for each instance and checks that execution's end time. It serves as a snapshot of current state, but **does not accurately reconstruct history at a past date** if that instance was later restarted: for example, if Monday failed and Tuesday succeeded, running the query on Wednesday sees the latest status as succeeded.

If you need an immutable historical chart of final instance outcomes, define a cutoff time (such as end of business deadline), store outcome snapshots, or record state-transition events over time. Never silently rewrite historical charts using current-state queries.

### 8.2. When Do You Need Both Rates?

For a billing job, a cycle that failed twice and recovered on restart may still meet its business deadline on time, yet still needs monitoring because it wastes resources and increases risk. An ideal dashboard provides two perspectives:

- **Execution failure rate:** stability of each run attempt.
- **On-time completion rate per business period:** percentage of business cycles completed before deadline.

Measuring only execution failure rate misses situations where a job is slow, stalled, or never launched by the scheduler. Measuring only final completion can mask chronic fail-and-recover behavior.

## 9. Per-Job Monitoring Dashboard

A readable dashboard should display at least:

| Field | Meaning |
| --- | --- |
| Job name | A stable name, e.g., `importOrdersJob` |
| Execution failures | Number of `FAILED` runs in the window |
| Completed executions | Number of `COMPLETED` runs in the window |
| Failure rate | `FAILED / (FAILED + COMPLETED)` |
| Last execution status | Status of the newest run, even if not yet finished |
| Last successful completion | Most recent `COMPLETED` outcome |
| Time since last success | Detect jobs that have gone too long without a successful run |
| Duration / p95 | Identify jobs growing slower before they fail |
| Runbook / log link | Support incident investigation by `jobExecutionId` |

Example table:

| Job | Failed / Terminal (24h) | Failure rate | Last success | Assessment |
| --- | ---: | ---: | --- | --- |
| `importOrdersJob` | 6 / 120 | 5% | 5 minutes ago | Recurring errors to watch |
| `settlePaymentsJob` | 1 / 1 | 100% | Yesterday | Incident needing priority check |
| `monthlyCloseJob` | 0 / 0 | N/A | End of last month | Not due yet; verify schedule |
| `syncCustomersJob` | 0 / 80 | 0% | 2 minutes ago | Operating normally |

Do not use a **single percentage-based color scale** to classify every job. For a critical nightly financial job, one failure can be far more severe than a 5% error rate on an auxiliary reporting job running hundreds of times per hour.

### Recommended Charts

1. **Bar chart:** 24-hour per-job failure rate, annotated with `failed/total`.
2. **Time series:** hourly `FAILED` and `COMPLETED` counts; helps spot regressions after deploys.
3. **Last-success age:** elapsed time since the latest `COMPLETED` run.
4. **Job duration:** p50/p95, especially for jobs with deadlines.
5. **Error breakdown:** failing step, structured error codes, application version, or environment. Avoid using exception messages as metric labels.

## 10. Alerting on Failure Rate Without Noise

### 10.1. Based on Job Run Frequency

| Job type | Useful alert | Why |
| --- | --- | --- |
| Runs every few seconds/minutes | 15-min/1-hour failure rate + minimum sample gate | Enough runs to evaluate trends |
| Runs hourly | A few consecutive failures; 24-hour rate | Short windows have too few samples |
| Runs daily | Single `FAILED` or not `COMPLETED` before deadline | Cannot wait for 10 runs in 1 hour |
| Runs at month-end | Closing cycle not completed on time | Daily rates are usually N/A |
| Self-restarting jobs | Execution failure rate + restart count + completion before deadline | Avoids missing recurring yet self-healing incidents |

### 10.2. Combining Rate, Freshness, and Duration

A batch monitoring system needs at least three signal groups:

- **Outcome:** how many runs ended in `FAILED`?
- **Freshness:** did the job run and finish on schedule?
- **Latency:** is the job running unusually long or breaching its deadline?

For example, `importOrdersJob` is not launched for 12 hours. Its failure rate is N/A because there are no executions in the window, yet that condition can be far worse than a 2% failure rate. You need a "missing expected run" alert based on schedule or time since last successful completion.

A job stuck in `STARTED` for 8 hours also has not produced a `FAILED` yet. Monitor active executions exceeding time thresholds rather than waiting for them to turn `FAILED`.

### 10.3. Illustrative Alert Policy Proposal

Suppose a frequent order-processing system has a weekly failure-rate SLO below 1%. You might use:

1. **Fast alert:** failure rate rises above a short-term threshold, given enough samples.
2. **Sustained alert:** 24-hour failure rate breaches threshold; avoids reacting solely to a few-minute spike.
3. **Schedule alert:** critical job lacks a `COMPLETED` run before its deadline.
4. **State alert:** execution stuck in `STARTED` too long, or unexpected `UNKNOWN`/`ABANDONED` status.

Numerical thresholds in examples are starting points to tune against run schedules, business impact weights, and acceptable noise levels. When multiple jobs share a dashboard, each job tier may need a different policy.

## 11. Tracking Failure Causes so Alerts Are Actionable

Failure rate tells you **there is a problem**; it does not explain **why**. When a job's failure rate rises, drill down from the metric to specific `JobExecution`s.

Investigation flow:

```text
Dashboard: importOrdersJob failure rate rises
                 |
                 v
Find FAILED JobExecutions during the spike
                 |
                 v
Read JOB_EXECUTION_ID, JobParameters, timestamps, ExitStatus
                 |
                 v
Locate FAILED StepExecution and exception/stacktrace
                 |
                 +-- Input error: invalid data, missing file
                 +-- Database error: connection, deadlock, unique constraint
                 +-- Dependency error: API timeout, queue unavailable
                 +-- Logic error: processor/writer exception
                 +-- Resource error: memory, disk, thread pool
                 |
                 v
Remediate -> rerun/restart per contract -> verify recovery
```

In Spring Batch Java, `JobExecution` provides failure exceptions, and each `StepExecution` holds status, exit status, and read/write/skip counters. Together these link failure rates to concrete root causes.

Useful fields in structured logs:

```text
jobName
jobInstanceId
jobExecutionId
stepName
stepExecutionId
businessDate
batchStatus
exitCode
durationMs
errorCategory
deploymentVersion
```

`errorCategory` should be a normalized, bounded value such as `INPUT_VALIDATION`, `DATABASE`, or `DEPENDENCY_TIMEOUT`. Exception details and stack traces belong in logs/traces rather than metric labels.

### Is a Step-Level Error Always a Job Failure?

Not every skipped item or handled exception produces `JobExecution.FAILED`. Conversely, a step may fail while the job flow is configured to handle it and still finish `COMPLETED` intentionally. Therefore:

- Compute **job failure rate** strictly from job-level outcomes as defined.
- Track **step failures, skip rates, and retry counts** with complementary metrics.
- If you need a "business failure rate" (e.g., invalid invoices), define it separately by item count or business cycle.

A `COMPLETED` job does not guarantee 100% of business records succeeded; SLOs should reflect data quality as well.

## 12. How to Test Failure-Rate Metric Accuracy

Monitoring tests have two levels: **calculation functions** and **integration with the batch lifecycle**.

### 12.1. Unit Testing the Formula

Write a function taking failed and completed counts:

```java
public final class FailureRate {
    private FailureRate() {}

    /**
     * Returns null when there are no completed or failed executions.
     * Otherwise returns a value in [0, 1].
     */
    public static Double calculate(long failed, long completed) {
        if (failed < 0 || completed < 0) {
            throw new IllegalArgumentException("Counts must be non-negative");
        }
        long total = Math.addExact(failed, completed);
        return total == 0 ? null : (double) failed / total;
    }
}
```

JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class FailureRateTest {

    @Test
    void allCompletedMeansZeroFailureRate() {
        assertEquals(0.0, FailureRate.calculate(0, 20));
    }

    @Test
    void fourFailuresInTwentyRunsMeansTwentyPercent() {
        assertEquals(0.20, FailureRate.calculate(4, 16));
    }

    @Test
    void allFailedMeansOneHundredPercent() {
        assertEquals(1.0, FailureRate.calculate(5, 0));
    }

    @Test
    void noRunsMeansUnknownRate() {
        assertNull(FailureRate.calculate(0, 0));
    }

    @Test
    void negativeCountsAreInvalid() {
        assertThrows(IllegalArgumentException.class,
                () -> FailureRate.calculate(-1, 4));
    }
}
```

This function uses `null` to represent "no data" for simplicity. In production code, you can use `OptionalDouble` or a DTO carrying `failed`, `completed`, `total`, and a nullable `rate`; pick one clear contract for the API/dashboard.

### 12.2. Unit Testing the Micrometer Listener

Example verifying that a `JobExecution.FAILED` increments the matching counter:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;

class JobOutcomeMetricsListenerTest {

    @Test
    void failedExecutionIncrementsFailureCounter() {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            JobOutcomeMetricsListener listener =
                    new JobOutcomeMetricsListener(registry);
            JobExecution execution = mock(JobExecution.class);
            JobInstance instance = mock(JobInstance.class);

            when(execution.getStatus()).thenReturn(BatchStatus.FAILED);
            when(execution.getJobInstance()).thenReturn(instance);
            when(instance.getJobName()).thenReturn("importOrdersJob");

            listener.afterJob(execution);

            assertEquals(1.0,
                    registry.get("batch.job.executions")
                            .tag("job.name", "importOrdersJob")
                            .tag("status", "FAILED")
                            .counter()
                            .count());
        }
    }
}
```

Test `COMPLETED` and `STOPPED` similarly, and verify `STARTED` does not increment any outcome counter. Unit tests need no Prometheus server and verify the exact metric contract registered by the application.

### 12.3. Integration Testing with JobRepository

A straightforward test scenario:

1. Create a test database containing Spring Batch metadata tables.
2. Run job A successfully 3 times with distinct identifying parameters.
3. Use a controlled failing job/step to produce 1 `FAILED` execution for job A.
4. Query `JobRepository` using the aggregation SQL over a window covering those runs.
5. Verify `C=3`, `F=1`, rate `25%`.
6. Create an additional `STOPPED` execution and verify it does not alter the standard failure rate numerator/denominator.
7. Restart a failed `JobInstance` to completion; verify **execution rate** and **instance-final rate** return different results as defined.

When an integration test must verify `JobExecution` statuses and timestamps, avoid merely inserting fake SQL rows manually: running Spring Batch against `JobRepository` catches mismatches between end times, statuses, and metadata.

To create test failures, use a step that intentionally throws an exception (such as `IllegalStateException`) in a dedicated test configuration. Do not use production dependencies or live data-sending APIs in tests.

### 12.4. Testing Historical and Missing-Data Edge Cases

Create fixtures or verification queries for:

| Scenario | Expectation |
| --- | --- |
| `COMPLETED=8`, `FAILED=2` | Rate 20% |
| `COMPLETED=0`, `FAILED=4` | Rate 100% |
| `COMPLETED=0`, `FAILED=0` | N/A |
| Plus 5 `STARTED` | Rate unchanged; separate running metric |
| Plus 1 `STOPPED` | Unchanged under standard definition |
| Failure at 23:59:59 | Assigned to previous day's window |
| Failure at exactly 00:00:00 | Assigned to next day's window |
| One failed execution then restarted to completed | Counts 2 executions, 1 JobInstance |
| Metric counter resets on JVM restart | Dashboard does not interpret as negative |
| Job misses its schedule | Freshness alert fires even though failure rate is N/A |

## 13. Common Mistakes When Implementing Monitoring

### Wrong Denominator from Including All Executions

Suppose there are 10 `COMPLETED`, 2 `FAILED`, and 8 `STARTED`:

- Wrong: `2/(10+2+8) = 10%`.
- Right under the lesson's formula: `2/(10+2) = 16.67%`.

Running executions belong in **running/long-running** metrics, not in the denominator to dilute failure rates.

### Counting Every FAILED Step as a FAILED Job

One job can have multiple steps, and one step can retry multiple times. Counting `BATCH_STEP_EXECUTION` rows or exception counts is not equivalent to `JobExecution.FAILED`. Query the job execution table and job-level status.

### Successful Restart "Erasing" Failure History

Looking only at the latest status per `JobInstance` lets a successful restart hide prior failures. Keep two separate views: attempt failure rate and final outcome rate.

### Displaying Zero Runs as 0%

An hourly job whose scheduler died may have zero new executions. Displaying 0% makes the dashboard falsely look "healthy." Display `N/A` and alert on **missing runs**.

### Querying by START_TIME While Describing Hourly Outcomes

A job crossing a window boundary can be assigned to the wrong day. If the definition tracks **completed outcomes**, use `END_TIME`. If reporting by business date is desired, use an explicit field or JobParameter.

### Counting STOPPED Without Documenting Policy

Intentionally stopping a job for maintenance differs from failure. Track `STOPPED` separately or define an explicit "unsuccessful rate" metric with documentation.

### Missing Listener Counters When JVM Dies

The process may die before `afterJob` runs or before Prometheus scrapes. Reconcile with `JobRepository` and monitor scrape gaps. Never treat missing series as healthy.

### Mixing Metrics Across Environments

If both staging and production emit job name `importOrdersJob`, aggregating without an environment label yields wrong numbers. Always scope dashboards before `sum by(job_name)`.

### High-Cardinality Metric Labels

Putting execution ID, business date, or exception messages into labels can create hundreds of thousands of series. Keep details in logs and use bounded metric labels.

### Failure Rate Drops While Data Is Still Wrong

A job can reach `COMPLETED` even if items were wrongly filtered/skipped or the writer wrote bad data. Pair failure rate with freshness, record counts, error/quarantine counts, financial checksums, and output validation.

## 14. Practice Exercise: Building a Failure-Rate Tracking Table

Assume a system with three jobs:

- `importOrdersJob` running every 10 minutes.
- `settlePaymentsJob` running nightly.
- `monthlyCloseJob` running once a month.

### Exercise 1: Designing the Data Source

In a test database, create `JobExecution` records with explicit `END_TIME`, `STATUS`, and `JOB_NAME`. Write a query grouped by job name counting `COMPLETED`/`FAILED` over 24 hours. Display both run counts and percentages.

Expected: `importOrdersJob` with `FAILED=3` and `COMPLETED=27` yields `10%`. `monthlyCloseJob` with no runs today yields N/A.

### Exercise 2: Distinguishing Execution vs. Instance

Create a `JobInstance` of `settlePaymentsJob` that fails once and then restarts to succeed. Show that execution failure rate is `50%` across two attempts, while final instance failure rate is `0%`.

### Exercise 3: Adding Metrics

Register `JobOutcomeMetricsListener`. Using `SimpleMeterRegistry`, assert that a failed run increments the counter once with tag `status=FAILED`. Then expose metrics through your project's Prometheus setup and verify the actual metric name and tags.

### Exercise 4: Defining Alerts

Pick an appropriate threshold for the 10-minute job. For the nightly job, design an alert when the job is `FAILED` or lacks a `COMPLETED` run past its deadline. Explain why one percentage threshold does not fit both.

### Exercise 5: Simulating Operational Failures

Abruptly terminate a running process. Verify how the system detects a `STARTED` state lasting too long or missing completions instead of relying solely on failure counters from `afterJob`. Add alerting or reconciliation backed by `JobRepository`.

## 15. Conclusion

**Per-job failure rate** is the ratio of `JobExecution.FAILED` to total `FAILED + COMPLETED` executions of a job within a well-defined window. It is a valuable metric for tracking stability and spotting regressions, but is meaningful only alongside its **denominator, time window, and status classification rules**.

In Spring Batch, distinguish a single run attempt (`JobExecution`) from a restartable logical job (`JobInstance`). Use `JobRepository` for queryable, reconcilable execution history; use Micrometer/Prometheus for near real-time dashboards and alerts. Pair it with **last-success freshness**, **duration**, **running status**, **deadline completion**, and **output data quality** so you never miss jobs that failed to start, ran too slowly, or "succeeded" without meeting business requirements.

### References

- [Spring Batch Reference – Domain: Job, JobInstance and JobExecution](https://docs.spring.io/spring-batch/reference/domain.html)
- [Spring Batch Reference – Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html)
- [Spring Batch Reference – Testing](https://docs.spring.io/spring-batch/reference/testing.html)
- [Micrometer – Concepts](https://docs.micrometer.io/micrometer/reference/concepts.html)
- [Prometheus – increase() and Query Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/)
