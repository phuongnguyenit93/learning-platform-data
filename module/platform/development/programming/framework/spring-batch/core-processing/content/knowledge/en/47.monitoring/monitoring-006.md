# Monitoring Job Duration in Spring Batch

## 1. What Is Job Duration and Why Monitor It?

In batch processing systems, **job duration** is the time a job execution actually spends running, typically calculated from **JobExecution.startTime** to **JobExecution.endTime**. This metric helps answer operational questions:

- How long does the order import job run in each period?
- Did the job start later than its scheduled time?
- Did completion time increase because of larger data volume, a slow Step, or external service timeouts?
- Is a currently running job at risk of breaching its completion deadline (SLA/SLO)?
- After tuning chunk size, queries, or worker count, did processing time actually improve?

For example, a job scheduled at 01:00 starts running at 01:04 and finishes at 01:19:

~~~text
01:00          01:04                          01:19
  |              |                              |
  v              v                              v
Scheduled     STARTED                       COMPLETED
  |-- 4 min ---|----------- 15 min ------------|
    Start       Job duration = 15 minutes
    delay

Time from scheduled start to completion = 19 minutes
~~~

**Job duration = 15 minutes** in this example; **start delay = 4 minutes** is a separate metric. If you measure only one of the two, the system may miss why output reached downstream late.

In Spring Batch, distinguish **JobInstance** (the logical work, identified by job name and identifying job parameters) from **JobExecution** (a specific execution attempt of that JobInstance). When a job fails and restarts, multiple JobExecutions can belong to the same JobInstance. The duration of each execution differs from the total time elapsed until the logical work completes.

## 2. Types of Time to Distinguish

| Metric | Start point | End point | Purpose |
|---|---|---|---|
| **Job execution duration** | JobExecution.startTime | JobExecution.endTime | Measure duration of a finished run |
| **Running elapsed time** | startTime of a running execution | Current observation time | Detect abnormally long-running jobs |
| **Step duration** | StepExecution.startTime | StepExecution.endTime | Isolate the Step causing slowdowns |
| **Start delay** | Scheduled time / trigger event | startTime | Detect slow schedulers, queues, or startup resources |
| **Queue/infrastructure delay** | Request / JobExecution creation time | startTime, depending on launch mechanism | Observe time spent waiting for capacity or scheduling |
| **End-to-end latency** | Time when data becomes eligible for processing | Time when output is READY | Evaluate actual data delivery deadlines |
| **Total elapsed across restarts** | First execution starts | Final execution completes | Includes pauses/wait time between attempts |
| **Active processing time across attempts** | Sum of start→end intervals of each execution | Aggregated per JobInstance | Estimate total active runtime, distinct from total elapsed |

**Do not use a single "duration" name for all of the quantities above.** For example, if a job pauses for two hours waiting for upstream to fix data and then restarts: total wall-clock time until complete output can be huge, while each execution only ran for a few minutes.

Duration is also distinct from **throughput**. A job processing 100,000 items in 10 minutes and a job processing 1,000,000 items in 12 minutes have similar durations yet completely different throughput. Pair duration with metrics for processed items and bytes.

### How Status Affects Duration Meaning

| BatchStatus | How to interpret timing metrics |
|---|---|
| COMPLETED | Duration is the time of a completed run according to the job flow; output quality still needs separate reconciliation |
| FAILED | Duration is the time until failure, not the time needed to process all data |
| STOPPED | Duration of a controlled stop; output may be incomplete |
| STARTED / STARTING / STOPPING | No final duration yet; calculate provisional elapsed time only |
| UNKNOWN / ABANDONED | Review metadata and operational procedures before drawing conclusions |

When computing **p95 duration of successful jobs**, filter specifically for status **COMPLETED**. Short `FAILED` durations from failing immediately at startup must not be included to make success latency look artificially better; track failures in a separate chart.

## 3. How Does JobRepository Record Time?

Spring Batch stores execution metadata in **JobRepository** and provides an API to read it via **JobExplorer**. In modern versions, JobExecution and StepExecution carry start and end timestamps; while a job is running or if metadata updates are interrupted, `endTime` may be absent.

Common metadata tables:

~~~text
BATCH_JOB_INSTANCE
    JOB_INSTANCE_ID
    JOB_NAME
       |
       v
BATCH_JOB_EXECUTION
    JOB_EXECUTION_ID
    JOB_INSTANCE_ID
    CREATE_TIME
    START_TIME
    END_TIME
    STATUS
       |
       v
BATCH_STEP_EXECUTION
    STEP_EXECUTION_ID
    JOB_EXECUTION_ID
    STEP_NAME
    START_TIME
    END_TIME
    READ_COUNT / WRITE_COUNT / ...
~~~

**CREATE_TIME** shows when the JobExecution was created in the repository; it is not automatically the scheduled run time. **START_TIME** is the primary timestamp for measuring execution duration. **END_TIME** is meaningful only once the execution has actually finished and metadata has been updated.

If the application is killed, loses connection to the repository, or the host crashes, the database may still show status **STARTED** with an empty `END_TIME`. Do not treat such executions as "infinite jobs"; combine heartbeats/worker liveness with recovery runbooks.

### Reading a JobExecution's Duration in Java

Spring Batch 5+ example using **LocalDateTime**:

~~~java
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.Optional;

import org.springframework.batch.core.JobExecution;

public final class BatchDurationCalculator {

    private BatchDurationCalculator() {
    }

    public static Optional<Duration> completedExecutionDuration(
            JobExecution execution) {

        LocalDateTime started = execution.getStartTime();
        LocalDateTime ended = execution.getEndTime();

        if (started == null || ended == null) {
            return Optional.empty();
        }
        return Optional.of(Duration.between(started, ended));
    }
}
~~~

Usage example:

~~~java
Optional<Duration> duration =
        BatchDurationCalculator.completedExecutionDuration(execution);

duration.ifPresent(value ->
        System.out.println("durationSeconds=" + value.toMillis() / 1000.0));
~~~

In older Spring Batch versions, timestamp APIs may use `Date`, so adapt conversions for your project version. When designing deployment environments, standardize timezone rules and synchronize host clocks; `LocalDateTime` timestamps carry no timezone for environment-independent interpretation.

The calculation above applies to **executions with valid start and end times**. For still-running executions, never substitute the current time for `endTime` and store it as a completed duration; emit it as a separate **running elapsed seconds** metric instead.

## 4. Measuring Elapsed Time of a Running Job

For a running execution:

\[
\text{runningElapsed}(t) = t - \text{startTime}
\]

For example, a job that started at 02:00 and is still STARTED at 02:17 has **elapsed = 17 minutes** and no final duration yet.

A monitoring application can read the execution via JobExplorer:

~~~java
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.Optional;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.explore.JobExplorer;

public class RunningJobInspector {

    private final JobExplorer jobExplorer;

    public RunningJobInspector(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public Optional<Duration> elapsed(long executionId) {
        JobExecution execution = jobExplorer.getJobExecution(executionId);
        if (execution == null || execution.getStartTime() == null) {
            return Optional.empty();
        }
        BatchStatus status = execution.getStatus();
        if (status != BatchStatus.STARTED
                && status != BatchStatus.STARTING
                && status != BatchStatus.STOPPING) {
            return Optional.empty();
        }
        return Optional.of(Duration.between(
                execution.getStartTime(), LocalDateTime.now()));
    }
}
~~~

The code above illustrates measuring from metadata. In multi-node systems, clock skew can produce negative or inaccurate elapsed values; keep NTP synchronized, standardize timezones, and never treat elapsed time computed from an old `STARTED` record as proof that the process is still alive.

If you need high-precision duration **within the same running process**, a monotonic clock such as `System.nanoTime()` is more suitable because it avoids system clock jumps. However, that result lives only in RAM; the metadata repository remains the historical source for completed executions.

### Detecting a "Hung" Job Requires Multiple Signals

Long job duration does not automatically mean a hung job. A Step may legitimately take longer when processing a large dataset. To tell them apart, monitor additionally:

- **Last progress** timestamp: the last time `readCount`/`writeCount` increased or a chunk committed.
- Thread/process state, worker heartbeats, and `JobRepository` health.
- DB lock wait times, API latencies, retries, and backoffs.
- Input volume of the current execution compared to history.
- Remaining backlog count, if a reliable way to measure it exists.

For instance, a job running for 30 minutes whose `readCount` steadily climbs may still be healthy, whereas a job running for only 5 minutes with zero progress and a thread blocked on an untimeouted network call may require intervention.

## 5. Querying Historical Duration from Spring Batch Tables

When analyzing multiple runs, read metadata via JobExplorer or read-only reporting SQL. The following example uses **PostgreSQL** syntax and assumes Spring Batch's default metadata schema.

~~~sql
SELECT
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.START_TIME,
    je.END_TIME,
    EXTRACT(EPOCH FROM (je.END_TIME - je.START_TIME))
        AS duration_seconds
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_JOB_INSTANCE ji
  ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE je.START_TIME IS NOT NULL
  AND je.END_TIME IS NOT NULL
  AND je.END_TIME >= :fromTime
ORDER BY je.END_TIME DESC;
~~~

Results might look like:

| JOB_NAME | EXECUTION_ID | STATUS | Duration (s) |
|---|---:|---|---:|
| importOrdersJob | 1001 | COMPLETED | 380 |
| importOrdersJob | 1002 | COMPLETED | 420 |
| importOrdersJob | 1003 | FAILED | 45 |
| importOrdersJob | 1004 | COMPLETED | 610 |

To calculate successful execution times on the set above, use **380, 420, and 610 seconds**. The 45-second `FAILED` execution must be analyzed as a failure, not mixed into the completion distribution when the metric is defined as successful job duration.

Querying individual Step durations:

~~~sql
SELECT
    se.JOB_EXECUTION_ID,
    se.STEP_NAME,
    se.STATUS,
    se.READ_COUNT,
    se.WRITE_COUNT,
    se.START_TIME,
    se.END_TIME,
    EXTRACT(EPOCH FROM (se.END_TIME - se.START_TIME))
        AS step_duration_seconds
FROM BATCH_STEP_EXECUTION se
WHERE se.JOB_EXECUTION_ID = :executionId
  AND se.START_TIME IS NOT NULL
  AND se.END_TIME IS NOT NULL
ORDER BY se.START_TIME, se.STEP_EXECUTION_ID;
~~~

When a job has Steps running in parallel, **do not sum all Step durations and call that total the job duration**. If two Steps each run for 10 minutes while completely overlapping, the sum of Step durations is 20 minutes whereas the job's wall-clock time is roughly 10 minutes.

### Querying Executions Running Beyond a Threshold

~~~sql
SELECT
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.START_TIME,
    EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - je.START_TIME))
        AS elapsed_seconds
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_JOB_INSTANCE ji
  ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE je.STATUS IN ('STARTING', 'STARTED', 'STOPPING')
  AND je.START_TIME IS NOT NULL
  AND je.START_TIME < CURRENT_TIMESTAMP - INTERVAL '30 minutes'
ORDER BY elapsed_seconds DESC;
~~~

This is a **list of candidates to investigate**, not proof that all of them are still actively running. If stale metadata was left behind after a crash, cross-check process/worker heartbeats.

For Oracle, SQL Server, MySQL, or other databases, adapt the time-difference expression to the SQL dialect. Avoid running unbounded historical queries without time filters or proper indexes on large metadata tables; `JobRepository` tables serve job execution, so reporting workload must be kept under control.

## 6. Measuring with Micrometer and Spring Boot Actuator

In Spring Boot applications, **Micrometer** and **Actuator** are standard foundations for publishing metrics to Prometheus, an OpenTelemetry collector, or an observability backend. Spring Batch also ships built-in instrumentation across many versions; meter names and tags can vary across Spring Batch, Spring Boot, Micrometer versions, and configuration.

Therefore, before adding custom metrics:

1. Verify whether Spring Batch metrics are already enabled in the application.
2. Inspect the actual meters via Actuator or MeterRegistry at runtime.
3. Check whether timers already exist for Jobs and Steps with tags like job name, step name, and status.
4. Add a new metric only when you need a duration definition or tag set not already covered.

Do not assume a specific Prometheus metric name will appear simply by adding Spring Batch to the classpath.

### Configuring Actuator and the Prometheus Endpoint

Gradle example for a Spring Boot application:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Example `application.yml`:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    distribution:
      percentiles-histogram:
        application.batch.job.duration: true
~~~

The `percentiles-histogram` configuration here applies to **the custom timer named `application.batch.job.duration`** in the next section, and is only needed if you query histograms/quantiles that way. Bucket counts and storage cost should be controlled in production.

The `/actuator/metrics` and `/actuator/prometheus` endpoints require security configuration and access restrictions; do not expose metrics containing internal system names and operational details to the public internet.

### What Does a Micrometer Timer Measure?

A **Timer** records multiple duration measurements, typically exposing **count**, **total time**, and **max** depending on the registry; histograms/percentiles can be exported when configured. Timers fit the durations of **finished executions**.

A timer alone does not tell you how many jobs are currently `STARTED` or how long a specific job has been running. For active work, use a dedicated metric such as an active execution count or an elapsed gauge backed by an appropriate monitoring source.

## 7. Creating a Custom Timer via JobExecutionListener

When you need metrics following application conventions, you can record one measurement when a job ends. The example below uses **Micrometer Timer.Sample**, tracking samples by `JobExecutionId` to support multiple concurrent runs in one JVM.

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.stereotype.Component;

@Component
public class JobDurationMetricsListener implements JobExecutionListener {

    private final MeterRegistry meterRegistry;
    private final ConcurrentMap<Long, Timer.Sample> runningSamples =
            new ConcurrentHashMap<>();

    public JobDurationMetricsListener(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    @Override
    public void beforeJob(JobExecution jobExecution) {
        Long executionId = jobExecution.getId();
        if (executionId != null) {
            runningSamples.put(executionId, Timer.start(meterRegistry));
        }
    }

    @Override
    public void afterJob(JobExecution jobExecution) {
        Long executionId = jobExecution.getId();
        if (executionId == null) {
            return;
        }

        Timer.Sample sample = runningSamples.remove(executionId);
        if (sample == null) {
            return;
        }

        sample.stop(Timer.builder("application.batch.job.duration")
                .description("Elapsed time of an in-process job execution")
                .tag("job", jobExecution.getJobInstance().getJobName())
                .tag("status", jobExecution.getStatus().name())
                .register(meterRegistry));
    }
}
~~~

Register the listener when building the Job:

~~~java
@Bean
public Job importOrdersJob(
        JobRepository jobRepository,
        Step importOrdersStep,
        JobDurationMetricsListener durationListener) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(importOrdersStep)
            .listener(durationListener)
            .build();
}
~~~

This example uses the Spring Batch 5+ builder style and assumes an **importOrdersStep** bean exists. If there are multiple Jobs to monitor, attach the listener to each Job or use appropriate instrumentation registration.

**Measurement scope:** the Timer sample uses a monotonic clock from the **beforeJob** callback to **afterJob** within **the same process**. It covers execution inside callbacks and Steps along the job flow, though it may not match repository `endTime - startTime` identically because listener invocation timing differs from metadata update timing.

Limitations to know:

- If the process is killed or crashes, **afterJob does not run**, the in-memory sample is lost, and no completed duration observation is recorded for that execution.
- If an execution runs on another JVM, the old listener's map cannot hold the sample for the new JVM. A job restart creates a new JobExecution with a new sample.
- Do not add **executionId**, **batchId**, **customerId**, filenames, or timestamps as metric labels; these cause **high cardinality**, increasing memory and storage cost.
- Low-variance tags like **job** and **status** work better for aggregation; keep the number of dynamically generated job names bounded.
- If built-in instrumentation already exports the same kind of timer, avoid adding a redundant custom metric with the same semantics under a different name that causes dashboards to double-count.

When you need a historical duration source resilient to process crashes, rely on **JobRepository** or a durable audit store with matching semantics; in-memory timers do not replace metadata.

## 8. Designing Metrics and Labels for Monitoring

A practical metric suite combines timing, execution outcomes, and progress:

| Conceptual metric | Type | Recommended labels | Goal |
|---|---|---|---|
| job duration | Timer/histogram | job, status | Duration distribution of finished executions |
| step duration | Timer/histogram | job, step, status | Identify slow Steps |
| job executions total | Counter | job, status | Completion/failure/stop frequency |
| running jobs | Gauge | job or job group | Number of currently active jobs |
| running elapsed | Gauge or metadata query | job; execution ID in logs/traces | Alert on long-running jobs |
| processed items | Counter | job, step, outcome | Throughput and progress |
| skip/retry/rollback | Counter | job, step, reason category | Diagnose slow processing scenarios |
| last successful completion | Timestamp Gauge | job | Detect batch periods missing timely output |
| input volume | Histogram/Gauge per execution | job | Explain duration increases when data grows |

For **running elapsed per execution**, a table dashboard querying JobRepository or a monitoring service is often preferable to stuffing `executionId` into Prometheus labels. Using a Gauge partitioned by `executionId` continually creates new time series; it requires cleanup policies and special handling for short-lived jobs.

In structured logs, by contrast, **executionId and batchId are very valuable** because logs and traces are designed to trace specific runs:

~~~text
event=JOB_FINISHED
jobName=importOrdersJob
jobExecutionId=2048
batchId=B20261116
status=COMPLETED
durationMs=428350
readCount=100000
writeCount=99320
filterCount=600
skipCount=80
~~~

This is an example log, not real numbers. If read/write totals do not match, inspect filter, skip, and output transformation logic first; never label it a "data error" from counter differences alone.

## 9. Duration Dashboards: Averages Are Not Enough

Suppose there are 10 `COMPLETED` executions with durations:

~~~text
8, 9, 9, 10, 10, 10, 11, 12, 13, 45 minutes
~~~

The average is **13.7 minutes**, yet the first nine runs clustered around 8–13 minutes. The 45-minute execution is an outlier requiring investigation. Showing only the average hides the slow tail.

Dashboards should display:

1. **p50, p95, p99 duration** for jobs with enough executions for percentiles to be meaningful.
2. **Max duration** and a list of the slowest runs, drillable via `executionId` in logs/traces.
3. **Execution counts by status**: COMPLETED, FAILED, STOPPED.
4. **Step durations** to pinpoint where latency increased.
5. **Input volume and throughput** over the same period.
6. **Elapsed time of running jobs** alongside completion deadlines.
7. **Time since last successful completion** for scheduled jobs.

For a job running only once per day, p99 across a few days of data is not a statistically stable measure. In that case, comparing each execution against a day-of-week baseline, volume, and business schedule limits is often more helpful.

### Example Dashboard Layout

~~~text
Batch processing / Import orders

Last run:
  status                 COMPLETED
  execution duration     12m 35s
  input records          150,000
  throughput             198 items/s
  completed at           02:18 local time

24-hour history:
  successful executions  12
  failed executions       1
  p50 duration          11m
  p95 duration          17m
  slowest step          enrichCustomer

Running executions:
  executionId 2081       STARTED  elapsed 8m

SLO:
  99% daily outputs READY before 03:00
~~~

Each metric above needs a clear source and definition. For example, **throughput = items written / duration** may omit processor filtering/skipping work; sometimes **readCount / duration** is used for input rate while reporting write throughput separately.

## 10. Prometheus/PromQL Examples

Assume the **custom Timer** from Section 7 is exported to Prometheus with histograms enabled. Converted metric names typically appear as:

~~~text
application_batch_job_duration_seconds_count
application_batch_job_duration_seconds_sum
application_batch_job_duration_seconds_bucket
~~~

These are **illustrative names to verify on your actual Prometheus endpoint**; bucket export depends on registry and distribution config. If the project uses Spring Batch's built-in metrics, replace the metric name with the one actually exported.

### 10.1. Average Duration of Successful Jobs Over 24 Hours

~~~promql
sum by (job) (
  increase(application_batch_job_duration_seconds_sum{
    status="COMPLETED"
  }[24h])
)
/
sum by (job) (
  increase(application_batch_job_duration_seconds_count{
    status="COMPLETED"
  }[24h])
)
~~~

The result unit is **seconds**. Dashboards should handle a zero denominator when no jobs completed in the window rather than displaying a fabricated figure.

### 10.2. p95 Duration from Histograms

~~~promql
histogram_quantile(
  0.95,
  sum by (le, job) (
    rate(application_batch_job_duration_seconds_bucket{
      status="COMPLETED"
    }[7d])
  )
)
~~~

The example uses a seven-day window to gather enough executions for infrequently run jobs. This syntax applies to **classic histograms** with an **le** label; if your backend uses native histograms or another distribution type, adapt the syntax.

### 10.3. Counting FAILED Jobs Over 24 Hours

~~~promql
sum by (job) (
  increase(application_batch_job_duration_seconds_count{
    status="FAILED"
  }[24h])
)
~~~

This metric only counts FAILED executions that passed through the listener and recorded a Timer sample. **Seeing zero FAILED does not mean no crashes occurred**, because a dead process may not run `afterJob`. Supplement it with metadata/heartbeat checks or scheduler monitoring events.

### Distinguishing Histogram Quantiles from Averages

Histograms represent duration distributions once intervals have completed; **p95 cannot be derived from the average**. For long-running jobs with few executions, configure suitable buckets (e.g., minutes or hours) so histograms are not overly coarse.

## 11. Alerting Based on Duration and Deadlines

Two alert groups can be defined:

**Long-running job alert:** an execution remains `STARTED` and its elapsed time exceeds the job's threshold. The goal is catching potential timeouts, deadlocks, slow APIs, or abnormal input volume.

**Missed-deadline output alert:** by a mandatory business cutoff, no `READY` output exists—whether because the job FAILED, STOPPED, was never triggered by the scheduler, or finished yet failed data reconciliation.

Example:

| Job | Reference duration threshold | Business deadline | Action when breached |
|---|---|---|---|
| importOrdersJob | 20 minutes under standard volume | READY before 03:00 | Check slow steps, record counts, and API latency |
| billingSettlementJob | 60 minutes | READY before 06:00 | Escalate due to impact on settlement data |
| nightlyExportJob | 90 minutes | File/manifest READY before 07:00 | Inspect writer, storage, and publish step |

These thresholds are examples only. In practice, calibrate by run schedule, volume, day-type baselines, partition count, and recovery buffer needed before the deadline.

### Dynamic Alerting by Input Volume

A job processing 5 million rows can legitimately run many times longer than one processing 50 thousand rows. You can model a baseline like:

\[
T_{\text{expected}} = T_{\text{setup}} +
\frac{N_{\text{items}}}{R_{\text{expected}}}
\]

Where:

- \(T_{\text{setup}}\): fixed overhead to initialize connections/Steps.
- \(N_{\text{items}}\): actual or expected input item count.
- \(R_{\text{expected}}\): expected processing rate (items/second).

For example, 30 seconds setup, 120,000 items, expected throughput 200 items/second:

\[
T_{\text{expected}} = 30 + \frac{120000}{200}
= 630 \text{ seconds} = 10.5 \text{ minutes}
\]

If an execution takes 25 minutes for the same volume, that is a signal to investigate. However, this formula is only a reference model: uneven transform costs, partition contention, API rate limits, and skips/retries can make speed nonlinear.

### Avoiding Alert Noise

Do not alert every time duration rises slightly above average. Base thresholds on historical baselines, volume conditions, and absolute duration, combined with a confirmation window to avoid spamming alerts once a job is already being handled.

For jobs running once per day, alerting on **no new COMPLETED run before the deadline** is usually more important than a p95 alert. For jobs running continuously many times per hour, p95/p99 and failure rates show trends more clearly.

## 12. Root-Cause Investigation When Duration Increases

A slow job alone does not identify which Step caused the problem. Investigation workflow:

~~~text
Job duration increases
        |
        v
Did input volume increase proportionally?
   | Yes                         | No / insufficient explanation
   v                              v
Compare throughput              Check Step durations
   |                              |
   v                              v
Throughput stable?              Which Step spiked?
   |                              |
   v                              v
If stable: expected longer      DB / API / Writer / CPU
If dropped: deep diagnosis      locks / retries / GC / I/O
~~~

Analysis can be divided by layer:

| Layer | Diagnostic signals |
|---|---|
| Reader | Slow queries, paging, locks, file size, network storage |
| Processor | CPU, GC, heavy transforms, cache hits, API calls |
| Writer | Batch inserts, commit latency, row locks, unique constraints, flushes |
| Transaction | Rollbacks, retries, deadlocks, and transaction timeouts |
| Infrastructure | CPU throttling, memory pressure, disk/network I/O |
| Coordination | Competing jobs, thread pools, partition imbalance |
| Downstream | HTTP 429/503, rate limits, queue backlogs |

If a job has multiple Steps, checking Step durations is the starting point. If a chunk-oriented Step combines reader, processor, and writer, add instrumentation for **chunk duration**, DB timing, and API timing to pinpoint which phase consumes the time.

### Do Not Equate Retry Counts with Throughput

An item may be processed multiple times due to retries or rollbacks; final read/write counts do not always reflect total API call volume. When duration climbs, combine:

- `readCount`, `writeCount`, `filterCount`, `readSkipCount`, `processSkipCount`, `writeSkipCount`.
- `rollbackCount`, exception histograms, and application-level retry attempts.
- Request counts, latencies, and error rates of external services.
- Durations of chunks, DB transactions, and API requests.

Do not immediately add more workers when a job slows down if the bottleneck is database locks or API rate limits: adding parallelism can make the job even slower.

## 13. Monitoring Duration in Multi-Step and Partitioned Jobs

Consider a job with these Steps:

~~~text
importOrdersJob
  |
  +-- loadStaging          3 min
  |
  +-- enrichRisk           8 min
  |
  +-- writeOutput          4 min
  |
  +-- verifyAndPublish     2 min
~~~

When run sequentially ignoring overhead, duration is close to **17 minutes**. However, when one Step runs in parallel with another or partitions process concurrently:

~~~text
partition-1: 00:00 ------- 00:08
partition-2: 00:00 ------------- 00:12
partition-3: 00:00 ---------- 00:10
~~~

Total partitioned Step duration is dominated by the slowest partition plus coordination overhead; **do not sum 8 + 12 + 10 = 30 minutes** as the Step's wall-clock duration. Monitor both median and max partition durations to spot **stragglers** (slow partitions).

When a job has asynchronous flows, never treat the sum of Step durations as total job duration. The sum of Step durations remains useful as a measure of total work, but label it explicitly as **sum of step durations** to prevent misunderstandings.

### Attaching Correlation IDs

Logs, traces, and audits should use `jobExecutionId`, `stepExecutionId`, and `batchId` to link events:

~~~text
jobExecutionId=3051 step=readAndEnrich chunk=12
chunkDurationMs=820
readerDurationMs=85
externalApiDurationMs=670
writerDurationMs=40
commitDurationMs=25
~~~

The numbers above are illustrative. When multiple API calls occur in a chunk, measure each layer consistently to avoid overlapping intervals (for example, async API calls can overlap). Keep dynamic IDs in traces/logs for troubleshooting; avoid putting them in aggregated metric labels.

## 14. Measuring Duration When a Job Restarts

Consider a JobInstance processing batch `B20261116`:

~~~text
JobExecution #41
  STARTED 01:00
  FAILED  01:08         duration = 8 min

Fixing data source:
  01:08 -> 01:30        wait = 22 min

JobExecution #42 (restart of same JobInstance)
  STARTED 01:30
  COMPLETED 01:40      duration = 10 min
~~~

We have three distinct numbers:

- **Execution duration #41:** 8 minutes, FAILED status.
- **Execution duration #42:** 10 minutes, COMPLETED status.
- **End-to-end elapsed time of the JobInstance from first start to completion:** 40 minutes, including the 22-minute wait between runs.

The total active execution time across both attempts is **18 minutes**, distinct from 40 minutes end-to-end. Never collapse both executions into a single duration without stating the aggregation rule.

Dashboards can separate:

| Scope | Metric | Meaning |
|---|---|---|
| JobExecution | execution duration | Compare performance of each attempt |
| JobInstance | attempts count | See how many restarts occurred |
| JobInstance | time to final completion | Evaluate SLA of the logical job |
| JobInstance | total active attempt time | Evaluate resource time spent executing |

If there are STOPPED/FAILED executions that have never reached COMPLETED, **time to final completion does not exist yet**. Never use the current time as a "completed duration"; instead report **time since first attempt** or **age of unresolved batch**.

## 15. Testing Duration Monitoring

A monitoring layer should be tested at both the calculation and integration levels, with expectations matched to the clock type:

| Scenario | Expectation |
|---|---|
| Job COMPLETED with start/end | Non-negative duration in the right unit |
| Job FAILED but finished | Duration recorded with status FAILED |
| Job still STARTED, endTime null | No final duration emitted; separate running elapsed available |
| Job finishes nearly instantaneously | Duration can be very small; not rounded into "non-existent" |
| Job STOPPED | Duration recorded for the stopped run with proper status label |
| Job restarted | Two executions tracked separately |
| Job with parallel Steps | Job duration is not computed as sum of Step durations |
| Process crashes before afterJob | In-memory timer may be missing; metadata/heartbeat monitoring detects anomalous execution |
| Different jobs running concurrently | Timer samples are not mixed up |
| Metrics with execution-varying labels | No unbounded time-series/cardinality growth |

### Unit Testing Time Calculations

You can construct a mock JobExecution or use test doubles with fixed timestamps. The goal is verifying **Duration.between** on two known instants and null handling without `Thread.sleep`.

Example with a pure function:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.time.LocalDateTime;
import java.util.Optional;

import org.junit.jupiter.api.Test;

class DurationCalculationTest {

    private static Optional<Duration> calculate(
            LocalDateTime start,
            LocalDateTime end) {
        if (start == null || end == null) {
            return Optional.empty();
        }
        return Optional.of(Duration.between(start, end));
    }

    @Test
    void calculatesNinetyFiveSeconds() {
        LocalDateTime start =
                LocalDateTime.of(2026, 11, 16, 1, 0, 0);
        LocalDateTime end =
                LocalDateTime.of(2026, 11, 16, 1, 1, 35);

        assertEquals(Duration.ofSeconds(95),
                calculate(start, end).orElseThrow());
    }

    @Test
    void runningExecutionHasNoFinalDuration() {
        assertTrue(calculate(LocalDateTime.now(), null).isEmpty());
    }
}
~~~

This sample function assumes start/end timestamps are normalized and `end` is not before `start`. In real applications, detect negative durations to alert on clock/metadata anomalies rather than feeding negative numbers into a Timer.

### Integration Testing with `SimpleMeterRegistry`

To test the listener from Section 7, you can use Micrometer's `SimpleMeterRegistry` in tests (no Prometheus server needed). For a small job executed in the test, verify that the Timer has **count = 1** after completion and the **status** tag is correct.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

// After wiring the listener with registry and running the job in test:
Timer timer = registry.find("application.batch.job.duration")
        .tag("job", "importOrdersJob")
        .tag("status", "COMPLETED")
        .timer();

assertEquals(1L, timer.count());
~~~

This snippet illustrates the assertion needed after a JobExecution completes, **not a complete test class**. Avoid asserting overly tight absolute duration values, as CI machine speeds vary. If exact clock testing is needed, inject a clock abstraction or test pure logic separately.

Using `SimpleMeterRegistry` does not prove that a Prometheus histogram is exported under the expected name. That requires a dedicated exporter/adapter test or checking the application endpoint under deployment configuration.

### Testing the Entire Monitoring Pipeline

A full integration test can:

1. Launch a job with a small fixture and wait for JobExecution to finish.
2. Read JobExplorer and confirm start/end times were persisted properly.
3. Query StepExecution to verify per-Step durations.
4. Read the Timer by job/status and confirm at least one sample was recorded.
5. For Prometheus exporters, verify metric names and tags appear if the feature is enabled.
6. Confirm dashboards/queries filter strictly on `COMPLETED` when computing successful duration.
7. Simulate `FAILED`/`STOPPED` runs to ensure durations are not conflated across statuses.

For systems where monitoring must never obstruct batch processing, also test when the metrics backend is unavailable or registry export fails: the job must preserve business behavior per policy, and metrics/logs must handle failures gracefully.

## 16. Common Mistakes

**Using CREATE_TIME instead of START_TIME to measure execution duration.** CREATE_TIME can include time before the job began running. If you need to measure start delay, track it as a separate metric.

**Computing completed duration with NOW() when END_TIME is absent.** This turns provisional runtime into a final result. Use running elapsed time and distinguish statuses.

**Mixing FAILED/STOPPED with COMPLETED when calculating successful p95.** Jobs failing early can make average duration look artificially faster and mask SLA risks.

**Summing Step durations to get Job duration in parallel flows.** Steps/partitions can overlap, so use JobExecution start/end for wall-clock time.

**Assuming COMPLETED means output is READY.** A job may need separate reconciliation and publishing steps; business deadlines must check explicit output-readiness signals per contract.

**Putting executionId or batchId into Prometheus labels.** Every run generates new time series, increasing cost and hurting backend stability. Use logs, traces, and audit tables for dynamic IDs.

**Using a post-Job Timer to detect hung jobs.** Timers record samples only when executions finish; use running elapsed time, progress checks, and heartbeats.

**Looking only at duration while ignoring volume.** Larger jobs naturally take longer; compare throughput and workload structure to recognize regressions.

**Ignoring retries, rollbacks, API latency, and lock contention.** Slow JobExecution is only a symptom; add Step/chunk/dependency timing to find the cause.

**Relying solely on in-memory metrics.** Process crashes lose the final observation; a metadata repository and independent monitoring detect stalled or dead executions.

**Inconsistent units.** One report using milliseconds and another using seconds/minutes easily causes 1,000x alerting mistakes. Add explicit unit suffixes, display units on dashboards, and convert carefully.

**Setting percentile alerts with too few samples.** Daily jobs only run a few times a week, so pair them with deadline alerts and per-run analysis.

**Ignoring timezones and clock skew.** With a shared JobRepository and workers on different hosts, clock skew produces negative or inflated durations. Synchronize clocks, standardize storage/display, and distinguish local time from UTC.

## 17. Practical Implementation Workflow

To introduce duration monitoring into a running Spring Batch system:

1. **Define durations in business terms:** execution time, end-to-end time to READY, start delay, and running elapsed are distinct metrics.
2. **Choose data sources:** JobRepository/JobExplorer for durable history; Micrometer for duration distributions and live dashboards; scheduler/manifests for deadlines.
3. **Standardize comparison dimensions:** stable jobName, status, Step, environment, and volume along needed axes.
4. **Configure instrumentation:** prefer built-in Spring Batch metrics; add custom Timers only where gaps exist and avoid high-cardinality labels.
5. **Build dashboards:** completed p50/p95/max, failures, running elapsed, slowest Step, read/write throughput, last READY.
6. **Set alert thresholds:** duration breaches, missing successful runs, missed output deadlines, stalled progress, abnormally long `STARTED` runs.
7. **Connect investigation paths:** link alerts to `executionId` in logs/traces and `StepExecution` in JobRepository, then to DB/API/I/O.
8. **Test special states:** `FAILED`, `STOPPED`, restarts, parallel execution, and process crashes.
9. **Monitor overhead:** histogram storage, time series count, metadata query frequency, and dashboard retention.
10. **Update baselines:** after changes to volume, chunk size, partition count, DB schema, or external service capacity.

A good monitoring system does not stop at "how long did the job take." It reveals **which run was slow, where it slowed down, whether deadlines are threatened, whether progress continues, and whether data is ready**. By distinguishing timing milestones, persisting durable metadata, and pairing duration with status, progress, and output contracts, Spring Batch can be operated and tuned on verifiable evidence.
