# Monitoring Step Duration in Spring Batch

## 1. What Is Step Duration and Why Monitor It?

In Spring Batch, each **step** is a unit of processing with its own status, statistics, and execution history. **Step duration** is the amount of time a `StepExecution` takes from start to finish. It is a foundational metric for spotting abnormally slow data ingestion, verifying optimization results, and predicting when a job will complete.

For example, the `dailyImport` job has three steps:

```text
dailyImport
  |
  +-- downloadFile       00:00:18
  |
  +-- validateRows       00:01:42
  |
  +-- writeToDatabase    00:12:30
                         --------
  Sum of step durations: 00:14:30
```

If steps run sequentially with no significant wait time between them, the total duration is close to the job's runtime. However, with **parallel steps, partitioning, remote processing**, or delays between two steps, summing the durations of all steps does not necessarily equal the total job runtime.

When `writeToDatabase` jumps from 12 minutes to 50 minutes, looking only at `JobExecution=COMPLETED` can cause operators to miss the issue. Duration helps answer: which step grew slower, by how much, and was it caused by larger data volume or lower processing speed?

### Lesson Objectives

After this lesson, you will be able to:

- Read `startTime`, `endTime`, and `BatchStatus` from `StepExecution` to calculate the duration of **a single step execution**.
- Understand the meaning of Micrometer `Timer` and `LongTaskTimer` in Spring Batch.
- Distinguish finished steps from still-running steps, as well as retried/restarted steps and parallel steps.
- Design dashboards and alerts based on duration, record counts, and throughput.
- Write deterministic tests for duration calculation code without using `Thread.sleep(...)`.
- Troubleshoot slow steps using `JobExplorer`, `JobRepository`, metrics, and logs.

**Versions used in examples:** Spring Batch 5.2.x, Spring Boot 3.x, Java 17+, and Micrometer. Spring Batch 6.x introduces package and API changes, so verify signatures against your project's actual version.

## 2. Distinguishing Types of Time in Batch Processing

The term "runtime" can refer to several different measurements.

| Metric | Measurement span | Used to answer |
|---|---|---|
| **Job duration** | From when `JobExecution` starts until it ends | How long did the entire job run take? |
| **Step duration** | From `StepExecution.startTime` to `endTime` | How long did a specific step take? |
| **Active step duration** | From when the step started until the current moment | How long has a still-running step been executing? |
| **Chunk duration** | Processing a single chunk unit | Is a transaction/chunk running slowly? |
| **Item read duration** | Reader invocation | Is reading from DB/API/file slow? |
| **Item process duration** | Processor invocation | Is transformation logic CPU-heavy or calling slow external services? |
| **Chunk write duration** | Writer invocation | Is writing to the database/file/broker slow? |
| **Scheduler delay** | From scheduled time until the job actually starts | Was the job delayed by queues, locks, or resource contention? |

**Do not equate step duration with the sum of individual item processing times.** A step may spend time initializing resources, opening/closing readers, managing transactions, writing checkpoints, retrying/backing off, or waiting on I/O.

Example:

```text
StepExecution importOrders
startTime = 01:00:00
endTime   = 01:05:00
duration  = 5 minutes

Within those 5 minutes:
  item read       40 seconds
  item process    60 seconds
  chunk write    140 seconds
  transaction     35 seconds
  open/close I/O   5 seconds
  other overhead  20 seconds
```

This illustrative breakdown is not a formula that Spring Batch guarantees to add up cleanly in every scenario. Some phases and measurements may overlap, especially with multithreading or callbacks measured inside transactions.

## 3. Primary Data Source: `StepExecution`

Spring Batch stores information for each step run in `StepExecution` and `JobRepository`. In Spring Batch 5.x, the typical time fields have type `LocalDateTime`:

```java
StepExecution stepExecution = ...;

LocalDateTime started = stepExecution.getStartTime();
LocalDateTime ended = stepExecution.getEndTime();

BatchStatus status = stepExecution.getStatus();
String stepName = stepExecution.getStepName();
Long stepExecutionId = stepExecution.getId();
```

Related fields:

| Property / counter | Meaning |
|---|---|
| `getId()` | ID of the step execution |
| `getStepName()` | Name of the step in the job |
| `getJobExecutionId()` | ID of the job execution containing this step |
| `getStartTime()` | Timestamp when the step started |
| `getEndTime()` | Timestamp when the step finished; may be `null` while still running |
| `getStatus()` | `STARTED`, `COMPLETED`, `FAILED`, `STOPPED`, ... |
| `getReadCount()` | Number of items successfully read by the reader |
| `getWriteCount()` | Number of items written by the writer per batch statistics |
| `getFilterCount()` | Number of items filtered by the processor returning `null` |
| `getReadSkipCount()` / `getProcessSkipCount()` / `getWriteSkipCount()` | Number of items actually skipped in each phase |
| `getCommitCount()` / `getRollbackCount()` | Commit/rollback activity in the step |

A `StepExecution` typically corresponds to **one run of a step within one `JobExecution`**. If a job stops or fails and is restarted, the step may receive a new `StepExecution`. Therefore, when analyzing history, store both **`stepName` and `stepExecutionId`**, not just the step name.

### 3.1. Computing Duration After the Step Completes

A simple helper method can handle cases where timestamps are not yet complete:

```java
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.Optional;

import org.springframework.batch.core.StepExecution;

public final class StepDurationCalculator {

    private StepDurationCalculator() {
    }

    public static Optional<Duration> completedDuration(
            StepExecution execution) {

        LocalDateTime start = execution.getStartTime();
        LocalDateTime end = execution.getEndTime();

        if (start == null || end == null) {
            return Optional.empty();
        }

        Duration duration = Duration.between(start, end);

        if (duration.isNegative()) {
            // Do not interpret an anomalous timestamp as a valid duration.
            return Optional.empty();
        }

        return Optional.of(duration);
    }
}
```

Using the helper:

```java
StepDurationCalculator.completedDuration(stepExecution)
        .ifPresent(duration -> {
            long elapsedMillis = duration.toMillis();

            System.out.println(
                    "step=" + stepExecution.getStepName()
                    + ", durationMs=" + elapsedMillis
            );
        });
```

**Calculation example:** A step starting at `2025-05-12T01:00:00` and ending at `2025-05-12T01:02:30` has a duration of **150 seconds**, or **150,000 milliseconds**.

### 3.2. Limitations of Timestamps Read from Metadata

`LocalDateTime` carries no offset or timezone. It suits representing metadata as persisted by Spring Batch 5.x, but when computing **highly accurate elapsed time**, keep in mind:

- The OS clock can be adjusted while a job is running.
- The process default timezone and JDBC/database configuration can affect how timestamps are interpreted.
- Daylight Saving Time (DST) transitions in some regions complicate using `LocalDateTime` as an absolute elapsed measure.
- For multi-day steps, clock adjustments between the two timestamps can make the difference unreliable.

To measure duration **within a running process**, metrics systems like Micrometer typically use a monotonic clock to avoid calendar-clock adjustments. For historical auditing and querying after the process exits, `startTime` and `endTime` in `JobRepository` remain very useful, provided you understand they are computed from system timestamps.

**Do not edit `startTime`/`endTime` just to "make reports look nicer."** Metadata is critical operational data for analysis and restarts.

## 4. Reading Step Duration from `JobExplorer`

`JobExplorer` is the Spring Batch metadata query API. Once you have a `jobExecutionId`, you can retrieve the execution and inspect its steps.

```java
import java.time.Duration;
import java.util.Comparator;
import java.util.List;

import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;

public final class StepDurationQueryService {

    private final JobExplorer explorer;

    public StepDurationQueryService(JobExplorer explorer) {
        this.explorer = explorer;
    }

    public List<StepDurationRow> findByJobExecution(long jobExecutionId) {
        JobExecution job = explorer.getJobExecution(jobExecutionId);

        if (job == null) {
            throw new IllegalArgumentException(
                    "Unknown JobExecution: " + jobExecutionId
            );
        }

        return job.getStepExecutions().stream()
                .map(step -> new StepDurationRow(
                        step.getId(),
                        job.getId(),
                        step.getStepName(),
                        step.getStatus().toString(),
                        StepDurationCalculator
                                .completedDuration(step)
                                .map(Duration::toMillis)
                                .orElse(null),
                        step.getReadCount(),
                        step.getWriteCount()))
                .sorted(Comparator.comparing(
                        StepDurationRow::stepExecutionId))
                .toList();
    }

    public record StepDurationRow(
            Long stepExecutionId,
            Long jobExecutionId,
            String stepName,
            String status,
            Long durationMillis,
            long readCount,
            long writeCount
    ) {
    }
}
```

For `STARTED` or `STOPPING`, `durationMillis` in this example is `null` when `endTime` is not yet set. That represents **no completed duration yet**, rather than returning `0` or pretending the job is finished.

An operations screen might display:

| StepExecution ID | Step | Status | Duration | Read | Write |
|---:|---|---|---:|---:|---:|
| 1001 | `downloadFile` | COMPLETED | 18 s | 1 | 1 |
| 1002 | `validateRows` | COMPLETED | 102 s | 120,000 | 119,800 |
| 1003 | `writeToDatabase` | STARTED | Running | 70,000 | 65,000 |

When a monitoring page shows "running for 8 minutes," that elapsed figure is **the monitoring page's own estimate relative to the current time**, not an `endTime` recorded by Spring Batch. Clearly label **completed duration** separately from **provisional elapsed time**.

### 4.1. Avoiding Confusion Across Restarts

Example:

```text
JobInstance: dailyImport, businessDate=2025-05-12
  ├── JobExecution 501
  │     └── StepExecution 1003, writeToDatabase, FAILED, 9 minutes
  └── JobExecution 515 (restart)
        └── StepExecution 1042, writeToDatabase, COMPLETED, 7 minutes
```

If asked "how long did the step in execution 515 take?", the answer is **7 minutes**. If asked "how much total step processing time was spent across attempts for that day?", you could compute **9 + 7 = 16 minutes** as cumulative time spent, but only when you explicitly want that metric. It is **not the duration of a single execution**, and if attempts overlap, summing does not reflect wall-clock elapsed time.

## 5. Querying Metadata in the Database

Spring Batch stores step history in the `BATCH_STEP_EXECUTION` table; related job tables are `BATCH_JOB_EXECUTION` and `BATCH_JOB_INSTANCE`, with the default prefix `BATCH_`.

A basic query to read execution info:

```sql
SELECT
    i.JOB_NAME,
    s.JOB_EXECUTION_ID,
    s.STEP_EXECUTION_ID,
    s.STEP_NAME,
    s.START_TIME,
    s.END_TIME,
    s.STATUS,
    s.READ_COUNT,
    s.WRITE_COUNT,
    s.COMMIT_COUNT,
    s.ROLLBACK_COUNT
FROM BATCH_STEP_EXECUTION s
JOIN BATCH_JOB_EXECUTION j
    ON s.JOB_EXECUTION_ID = j.JOB_EXECUTION_ID
JOIN BATCH_JOB_INSTANCE i
    ON j.JOB_INSTANCE_ID = i.JOB_INSTANCE_ID
WHERE s.JOB_EXECUTION_ID = :jobExecutionId
ORDER BY s.STEP_EXECUTION_ID;
```

`:jobExecutionId` represents an application bind parameter, not SQL syntax supported directly by every interactive client. You can compute the time difference in Java after reading `START_TIME`/`END_TIME`, or use the database's appropriate timestamp arithmetic.

For a historical dashboard:

```text
BATCH_JOB_INSTANCE
       |
       v
BATCH_JOB_EXECUTION
       |
       v
BATCH_STEP_EXECUTION
       |
       +-- STEP_NAME
       +-- STATUS
       +-- START_TIME / END_TIME
       +-- READ_COUNT / WRITE_COUNT
       +-- COMMIT_COUNT / ROLLBACK_COUNT
```

**Notes when reading tables directly:**

- Metadata is updated by `JobRepository` at lifecycle events and checkpoints; counters for a running step do not necessarily reflect the very latest item processed at this instant.
- If a table prefix other than `BATCH_` is configured, adjust table names to match your configuration.
- Do not write directly to metadata tables just to adjust durations, as that can corrupt restart state.
- When purging metadata under a retention policy, older records may be deleted; for long-term reporting, export metrics to a monitoring system or analytics warehouse.

## 6. Monitoring Duration with Micrometer

Spring Batch integrates with Micrometer to collect metrics at batch processing milestones. In versions with support and when Micrometer is enabled, notable meters include:

| Meter name | Type | Meaning |
|---|---|---|
| `spring.batch.job` | Timer | Duration of completed job executions |
| `spring.batch.job.active` | LongTaskTimer | Currently executing jobs |
| `spring.batch.step` | Timer | Duration of completed step executions |
| `spring.batch.step.active` | LongTaskTimer | Currently executing steps |
| `spring.batch.item.read` | Timer | Item read duration |
| `spring.batch.item.process` | Timer | Item process duration |
| `spring.batch.chunk.write` | Timer | Chunk write duration |

Meter names, tags, and auto-configuration details can vary across Spring Batch/Micrometer versions. Verify which meters **actually appear** in `/actuator/metrics` or `/actuator/prometheus` before building dashboards or alerts.

### 6.1. How `Timer` Differs from `LongTaskTimer`

**Timer** records **completed** operations: invocation count, total time, and optionally buckets/histograms.

For example, a `spring.batch.step` Timer has:

```text
step=writeToDatabase
status=COMPLETED
count=3
totalTime=35 minutes
```

Average = 35 / 3 ≈ 11.67 minutes per run. This is just an illustration, not verbatim output from a specific endpoint.

**LongTaskTimer** tracks operations that are **still running**, exposing active count and current elapsed time. It is useful when a step hangs and you cannot wait until completion for a regular timer to record a sample.

Example:

```text
spring.batch.step          -> finished runs
spring.batch.step.active   -> currently running executions
```

If a step has been hung for 2 hours, the Timer for **completed** runs may look completely normal. Inspect LongTaskTimer or `STARTED` status paired with the active execution's elapsed time.

### 6.2. Configuring Spring Boot Actuator

Gradle example with Spring Boot 3.x:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}
```

These are the dependencies related to Batch and metrics, excluding the application's JDBC driver/datasource for `JobRepository`.

Example configuration in `application.yml`:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    distribution:
      percentiles-histogram:
        spring.batch.step: true
```

With a Prometheus registry and a compatible version, metrics can be inspected at:

```text
GET /actuator/metrics
GET /actuator/metrics/spring.batch.step
GET /actuator/prometheus
```

`/actuator/metrics` lets you inspect which meter names and tags exist in the process. `/actuator/prometheus` exposes the Prometheus format; Timers are typically exported in **seconds** such as `spring_batch_step_seconds_count` and `spring_batch_step_seconds_sum`. If histograms are enabled and supported by the backend, `..._bucket` series also appear.

If `/actuator/metrics/spring.batch.step` is empty, verify that the step actually ran, Micrometer/Batch instrumentation is enabled, a registry is configured, and the endpoint is exposed. Do not assume every Spring Boot project exports all meters in the table above automatically.

**Security:** Metric endpoints can expose job/step names and operational details. Expose them only to the monitoring network or authorized accounts; do not expose all actuator endpoints publicly on the internet by default.

## 7. Reading Duration Charts and Designing Dashboards

For recurring steps, a dashboard should help distinguish **a step slowed by higher load** from **a step slowed by degraded performance**.

Example time series:

| Business date | Step | Duration | Read count | Average read rate |
|---|---|---:|---:|---:|
| May 12 | importOrders | 10 min | 100,000 | 166.7 items/s |
| May 13 | importOrders | 18 min | 180,000 | 166.7 items/s |
| May 14 | importOrders | 22 min | 110,000 | 83.3 items/s |
| May 15 | importOrders | 9 min | 95,000 | 175.9 items/s |

On May 13, duration increased by 80% while throughput stayed virtually flat — higher load is the likely reason. On May 14, load was lower yet duration was longer: throughput dropped sharply, so inspect database locks, retries, I/O errors, and system performance.

Basic throughput calculation:

```text
throughput = readCount / durationSeconds
```

For example, 100,000 items in 600 seconds ⇒ about 166.7 items/s. For jobs with multiple I/O steps unrelated to items, this throughput only reflects **the step-wide average**; do not equate it with pure reader speed.

### 7.1. Recommended Panels

An operational dashboard might include:

1. **Duration by step name**: median/percentiles or per-execution duration.
2. **Success/failure ratio** by step; do not plot only `COMPLETED` durations while hiding `FAILED` runs.
3. **Active step count** and **active elapsed** for currently running steps.
4. **Read/write/filter/skip counts** to compare workload and data quality.
5. **Commit/rollback counts** to spot transactions hitting frequent retries/rollbacks.
6. **Links to logs/traces** via `jobExecutionId` and `stepExecutionId`.

Do not rely on a single duration dashboard to infer root causes. CPU, memory, GC, SQL latency, network, message broker, and retry counts may all need cross-checking when a spike occurs.

### 7.2. Prometheus: Measuring Average Duration

When the Micrometer Timer exports Prometheus series `spring_batch_step_seconds_sum` and `spring_batch_step_seconds_count`, the idea for average duration by step name is:

```promql
sum by (name) (
  rate(spring_batch_step_seconds_sum[24h])
)
/
sum by (name) (
  rate(spring_batch_step_seconds_count[24h])
)
```

The formula yields **seconds per completed execution**, provided enough runs occurred within the window. Actual tag names may differ from `name` depending on version and configuration, so inspect scraped data before applying it.

For jobs running once per day, `[5m]` is usually too short and yields no data; use a 24-hour or multi-day window to compare trends, or rely on per-execution records in `JobRepository`.

### 7.3. P95 and Histograms

If histograms are enabled and Prometheus has `spring_batch_step_seconds_bucket`, an example p95 query by step is:

```promql
histogram_quantile(
  0.95,
  sum by (le, name) (
    rate(spring_batch_step_seconds_bucket[7d])
  )
)
```

This query depends on the `name` label and actual metrics in Prometheus. Percentiles are only meaningful with a sufficiently large sample size; for a step running strictly once a day, a 7-day p95 has very few samples and can be misleading. For infrequent batch jobs, viewing **each execution's duration** or comparing against daily/volume-normalized baselines is often more useful.

## 8. Detecting Overly Long Steps Before They Finish

A practical problem: a dashboard watching only completed-execution Timers will miss a currently hung step.

Suppose `writeToDatabase` normally takes 10–20 minutes, but today it has remained `STARTED` for 90 minutes.

```text
01:00  Step STARTED
01:20  No final result yet
01:45  Still STARTED
02:30  Still STARTED → investigate
```

With `LongTaskTimer` or `StepExecution.startTime` metadata, the system can alert when current elapsed time exceeds a threshold. However, **a `STARTED` metadata row does not guarantee the thread is still alive**: if a worker dies abruptly, `JobRepository` can retain the stale status.

For reliable alerting:

- Check `STARTED`/`STOPPING` status, elapsed time since start, and whether any newer execution exists.
- Cross-check whether the worker/pod/process is still alive, along with the latest checkpoint or application heartbeat.
- Watch for I/O timeouts and error logs from reader/processor/writer.
- Do not automatically flip status to `FAILED`/`STOPPED` solely because a time threshold was exceeded; metadata recovery requires a proper operational procedure.

### 8.1. Load-Appropriate Duration Thresholds

A fixed rule like "every step over 5 minutes is slow" is rarely useful. Thresholds should match each step and its data characteristics:

```text
downloadFile       > 3 minutes     -> alert
validateRows       > 15 minutes    -> alert
writeToDatabase    > 45 minutes    -> alert
```

These are illustrative values. When data volume grows substantially, scale thresholds accordingly—for example, alert if **duration per 10,000 items** exceeds normal levels, or if throughput drops sharply under comparable input volume.

Distinguish two alert types:

- **Completed slow:** the step finished, but its duration breached the SLO; inspect performance and trends.
- **Running too long:** the step has no end time yet and elapsed time breached the SLO; prioritize checking worker health and blocked resources.

## 9. Logging Duration Per Execution

Micrometer fits aggregated metrics well. When looking up a specific execution, structured logs carrying `jobExecutionId` and `stepExecutionId` are much more practical than putting those two IDs into metric labels.

Example of a `JobExecutionListener` that logs every step in a job once the job finishes:

```java
import java.time.Duration;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.batch.core.StepExecution;

public final class StepDurationLoggingListener
        implements JobExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(StepDurationLoggingListener.class);

    @Override
    public void afterJob(JobExecution jobExecution) {
        for (StepExecution step : jobExecution.getStepExecutions()) {
            StepDurationCalculator.completedDuration(step)
                    .ifPresentOrElse(
                            duration -> logCompleted(
                                    jobExecution,
                                    step,
                                    duration),
                            () -> log.warn(
                                    "Missing step duration: jobExecutionId={}, "
                                            + "stepExecutionId={}, stepName={}, status={}",
                                    jobExecution.getId(),
                                    step.getId(),
                                    step.getStepName(),
                                    step.getStatus())
                    );
        }
    }

    private void logCompleted(
            JobExecution job,
            StepExecution step,
            Duration duration) {

        log.info(
                "batch.step.finished jobName={} jobExecutionId={} "
                        + "stepExecutionId={} stepName={} status={} "
                        + "durationMs={} readCount={} writeCount={} "
                        + "filterCount={} rollbackCount={}",
                job.getJobInstance().getJobName(),
                job.getId(),
                step.getId(),
                step.getStepName(),
                step.getStatus(),
                duration.toMillis(),
                step.getReadCount(),
                step.getWriteCount(),
                step.getFilterCount(),
                step.getRollbackCount()
        );
    }
}
```

Register the listener in the job configuration:

```java
@Bean
Job importJob(
        JobRepository repository,
        Step downloadStep,
        Step processStep) {

    return new JobBuilder("importJob", repository)
            .start(downloadStep)
            .next(processStep)
            .listener(new StepDurationLoggingListener())
            .build();
}
```

`afterJob` runs when the job reaches its completion phase and can observe the `StepExecution` instances of **the current job execution**. If the JVM crashes before the callback, logs are not guaranteed to appear; metadata in `JobRepository` can still be queried for later reconciliation.

**Why not put execution IDs into metric tags?** `jobExecutionId` and `stepExecutionId` change on every run; putting them in tags causes **high cardinality**, forcing Prometheus/monitoring backends to consume excessive memory and slowing down queries. Use stable tags such as job name, step name, and status; store specific IDs in logs, traces, or audit stores.

## 10. When to Use `StepExecutionListener` for Custom Timing

To add custom instrumentation for **an individual step**, you can measure from `beforeStep` to `afterStep`:

```java
public class StepTimingListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution execution) {
        // Mark the measurement start point.
    }

    @Override
    public ExitStatus afterStep(StepExecution execution) {
        // Record duration and return null if exit status needs no change.
        return null;
    }
}
```

The snippet above only shows the extension points. In practice, Spring Batch already provides step-level metrics and `StepExecution` records timestamps, so evaluate carefully before writing a redundant custom Timer.

If a specific requirement demands higher-resolution duration, use a **monotonic clock**:

```java
long startNanos = System.nanoTime();

// Unit of work inside the same process.
performWork();

long elapsedNanos = System.nanoTime() - startNanos;
```

`System.nanoTime()` measures **elapsed intervals**, not calendar timestamps or checkpoints persisted across process restarts. This illustrative snippet is not a complete `StepExecutionListener` implementation.

### 10.1. Avoid Turning Singleton Listener State into a Bug

Do not store `startNanos` in a shared field like this:

```java
public class UnsafeTimingListener implements StepExecutionListener {

    private long startNanos;

    @Override
    public void beforeStep(StepExecution execution) {
        startNanos = System.nanoTime();
    }

    @Override
    public ExitStatus afterStep(StepExecution execution) {
        long elapsed = System.nanoTime() - startNanos;
        System.out.println(elapsed);
        return null;
    }
}
```

If a singleton listener bean is registered on multiple steps running in parallel, another `beforeStep` call can overwrite the start time and corrupt measurements.

Safer approaches:

- Prefer Spring Batch/Micrometer's default instrumentation.
- Use `Timer.Sample` tied to each execution inside a safe state-tracking mechanism, releasing state upon completion.
- When historical records are needed, rely on `StepExecution` metadata and `JobRepository`.
- Avoid passing `System.nanoTime()` from one JVM to another or saving it into `ExecutionContext` for use after a restart, because monotonic values are meaningful only within the same process.

## 11. Testing Duration Calculation Logic

A proper test must verify explicit timestamps instead of waiting for a job to sleep for some number of milliseconds. Because `StepExecution` already holds start/end times, unit tests simply construct objects and compute the difference.

### 11.1. Unit Testing with Fixed Timestamps

Example using JUnit Jupiter and `spring-batch-test`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.time.LocalDateTime;
import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.MetaDataInstanceFactory;

class StepDurationCalculatorTest {

    @Test
    void completedStepShouldReturn150Seconds() {
        StepExecution execution =
                MetaDataInstanceFactory.createStepExecution();

        execution.setStartTime(
                LocalDateTime.of(2025, 5, 12, 1, 0, 0)
        );
        execution.setEndTime(
                LocalDateTime.of(2025, 5, 12, 1, 2, 30)
        );

        Optional<Duration> elapsed =
                StepDurationCalculator.completedDuration(execution);

        assertEquals(
                Duration.ofSeconds(150),
                elapsed.orElseThrow()
        );
    }

    @Test
    void runningStepShouldNotHaveCompletedDuration() {
        StepExecution execution =
                MetaDataInstanceFactory.createStepExecution();

        execution.setStartTime(
                LocalDateTime.of(2025, 5, 12, 1, 0)
        );
        execution.setEndTime(null);

        assertTrue(
                StepDurationCalculator.completedDuration(execution)
                        .isEmpty()
        );
    }

    @Test
    void inconsistentTimestampsShouldNotProduceNegativeDuration() {
        StepExecution execution =
                MetaDataInstanceFactory.createStepExecution();

        execution.setStartTime(
                LocalDateTime.of(2025, 5, 12, 2, 0)
        );
        execution.setEndTime(
                LocalDateTime.of(2025, 5, 12, 1, 0)
        );

        assertTrue(
                StepDurationCalculator.completedDuration(execution)
                        .isEmpty()
        );
    }
}
```

The test does not rely on `LocalDateTime.now()` or `Thread.sleep()`. It tests **the calculation rules from metadata**, not that the framework populates start/end times or updates counters properly. Those behaviors belong in integration tests.

### 11.2. Testing a Timer Without Waiting Real Time

If you write custom Micrometer instrumentation, you can use `MockClock` to measure accurately without sleeping:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import org.junit.jupiter.api.Test;

class StepTimerTest {

    @Test
    void timerShouldRecordThreeSecondsWithoutSleeping() {
        MockClock clock = new MockClock();

        try (SimpleMeterRegistry registry =
                     new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock)) {

            Timer timer = Timer.builder("custom.batch.step.duration")
                    .tag("step", "importOrders")
                    .register(registry);

            Timer.Sample sample = Timer.start(registry);

            // Advance Micrometer's measurement clock:
            clock.add(Duration.ofSeconds(3));

            sample.stop(timer);

            assertEquals(1L, timer.count());
            assertEquals(
                    3.0,
                    timer.totalTime(TimeUnit.SECONDS),
                    0.000001
            );
        }
    }
}
```

`MockClock` belongs to Micrometer, distinct from `java.time.Clock.fixed(...)`. It is suitable for testing application-instrumented metrics; this test approach does not imply every built-in framework meter automatically picks up a `MockClock` created in another test.

### 11.3. Integration Testing a Real Step

To verify that `StepExecution.startTime` and `endTime` are populated when the framework executes a step, create a Spring Batch test running a finite tasklet:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBatchTest
@SpringBootTest(
        classes = StepDurationIntegrationTest.TestApplication.class,
        properties = {
                "spring.batch.job.enabled=false",
                "spring.batch.jdbc.initialize-schema=always"
        }
)
class StepDurationIntegrationTest {

    @Autowired
    JobLauncherTestUtils launcherTestUtils;

    @Test
    void completedStepShouldHaveStartAndEndTime() throws Exception {
        JobExecution job = launcherTestUtils.launchStep("measuredStep");

        StepExecution step = job.getStepExecutions()
                .iterator()
                .next();

        assertEquals(BatchStatus.COMPLETED, step.getStatus());
        assertNotNull(step.getStartTime());
        assertNotNull(step.getEndTime());
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {

        @Bean
        Step measuredStep(
                JobRepository repository,
                PlatformTransactionManager transactionManager) {

            return new StepBuilder("measuredStep", repository)
                    .tasklet((contribution, context) ->
                            RepeatStatus.FINISHED, transactionManager)
                    .build();
        }

        @Bean
        Job durationTestJob(
                JobRepository repository,
                Step measuredStep) {

            return new JobBuilder("durationTestJob", repository)
                    .start(measuredStep)
                    .build();
        }
    }
}
```

The test uses `launchStep` to test **a single step** without waiting artificial durations. It does not assume the step must take more than 10 ms, because CI environments, JIT, CPU, and payload sizes vary. To verify metric statistics, separately test that the registry receives samples and check actual meter names/tags on your stack.

To test a job-level duration logging listener, use `launchJob(...)`, because the root job's listener is not necessarily invoked when `launchStep(...)` creates its own wrapper job.

## 12. Systematically Analyzing a Slow Step

When a step's duration spikes suddenly, cross-check the following data.

### 12.1. Volume and Throughput

```text
Baseline:
  duration    = 10 minutes
  readCount   = 100,000
  read/sec    = 166.7

Today:
  duration    = 30 minutes
  readCount   = 100,000
  read/sec    = 55.6
```

Since volume is unchanged while throughput dropped to one-third, inspect I/O, locks, network, GC, CPU resources, and concurrency. If today read three times as much data at the same throughput, consider capacity or scheduling rather than immediately blaming a performance regression.

### 12.2. Retry, Skip, and Rollback

A step can finish `COMPLETED` yet run slowly because many errors were retried successfully:

- Rising `rollbackCount` may indicate repeated transactions.
- `readSkipCount`, `processSkipCount`, and `writeSkipCount` indicate items were skipped.
- Rising `filterCount` does not mean errors; the processor may be intentionally filtering.
- Counters only aggregate framework-recorded behavior; they do not provide per-retry duration histograms.

If you need to know **which retries are slow**, add appropriate metrics/logs in the policy or corresponding component without stuffing every data field into metric tags.

### 12.3. DB and Transactions

Database-writing steps are commonly affected by:

- Lock contention and transaction isolation.
- Chunk/batch insert size.
- Index maintenance, triggers, foreign keys.
- Connection pool exhaustion.
- Query plan changes as data grows.
- Commit or deadlock retries.

Step-level duration tells you **that it is slow**, while SQL monitoring/tracing tells you **where it is slow**.

### 12.4. Remote Services and File I/O

If the reader calls HTTP endpoints or downloads files over SFTP, rising latency usually lies outside application CPU. Enforce finite timeouts, bounded retries, request latency metrics, and traces with correlation IDs. Do not merely raise timeouts indefinitely to mask rising durations.

## 13. Special Cases That Complicate Comparisons

### 13.1. Parallel Steps

With parallel flows, two steps can run concurrently:

```text
Timeline (unit: minutes)

Step A: |=========== 10 ===========|
Step B: |====== 6 ======|

Job wall-clock roughly 10 minutes
Sum of step durations = 10 + 6 = 16 minutes
```

The sum of 16 minutes represents cumulative resource/execution time of both steps, not 16 minutes of elapsed wall-clock time. If the two steps share resources, also analyze concurrency levels and contention.

### 13.2. Partitioned Steps

A manager step distributes data across multiple workers/partitions. Each partition has its own `StepExecution`; manager duration and worker durations can overlap. Summing all of them can help understand total processing cost, but **cannot** be used as end-to-end duration.

A partitioning dashboard should display:

- Manager duration.
- Duration per partition and the slowest partition.
- Distribution of read/write counts across partitions.
- Wait time for distribution, queues, and workers.
- Failed or retried partitions.

Data skew often causes one partition to run far longer than the rest even when aggregate throughput looks healthy.

### 13.3. Restarts

After a job is `FAILED` or `STOPPED`, a restart can create a new `StepExecution`. Comparing durations requires clarifying which question you are asking:

- Duration of the latest execution?
- Cumulative duration across all attempts?
- Elapsed time from first start until completion after restart, including operator wait time?

Those are three distinct metrics. Each answers a different operational question.

### 13.4. Should FAILED/STOPPED Steps Be Included?

Yes, when evaluating processing cost and incidents. A step failing after 60 minutes is crucial information, even though it does not contribute to the average duration of `COMPLETED` runs.

When charting, separate statuses so viewers understand the dataset. Do not exclude all `FAILED` runs and conclude the system got faster; that is a form of **survivorship bias** in metrics.

### 13.5. Clocks and Timestamps

Do not derive duration **from the scheduled cron time**, and do not subtract scheduler dispatch time from the last log line timestamp. Those endpoints can include queue delay, logging delay, network latency, and clock skew across machines. For step-level dashboards, use `StepExecution` execution data or meters measuring the step itself.

## 14. Operational Checklist for Step Duration

| Question | Metric / tool to inspect |
|---|---|
| Has the step finished? | `StepExecution.status` and `endTime` |
| How long did a specific step take? | `startTime`, `endTime`, or `spring.batch.step` Timer |
| Is a step running abnormally long? | `spring.batch.step.active` or `STARTED` + elapsed from metadata |
| Did data volume grow? | `readCount`, `writeCount`, business input count |
| Did processing speed drop? | Duration combined with item count and throughput |
| Are there many rollbacks/retries? | `rollbackCount`, retry logs, error metrics |
| Is the slowdown in reader/processor/writer? | `spring.batch.item.read`, `spring.batch.item.process`, `spring.batch.chunk.write`, and traces |
| Is this a restart or the first attempt? | `jobExecutionId`, `stepExecutionId`, `JobInstance` |
| Is one partition lagging behind? | Per-partition duration and data distribution |
| Is metadata missing `endTime`? | Worker/process health, crashes, recovery procedure |

### Common Anti-Patterns

| Anti-pattern | Problem | Replace with |
|---|---|---|
| Measuring duration via `Thread.sleep` in tests | Tests depend on real time and become flaky | Fixed timestamps or Micrometer `MockClock` |
| Calling `LocalDateTime.now()` twice and asserting exact deltas | Easily drifts as time passes during tests | Inject a clock or use controlled measurements |
| Treating `STARTED` with `endTime=null` as 0 duration | Hides slow or hung steps | Display "Running" and track active elapsed time |
| Summing parallel step durations as job duration | Double-counts overlapping time | Use `JobExecution` for wall-clock job duration |
| Putting `stepExecutionId` into Prometheus tags | Cardinality grows with every run | Store IDs in logs/traces |
| Monitoring only `COMPLETED` steps | Ignores slow failed steps | Separate series by status |
| Assuming every `STARTED` step is still alive | The JVM may have crashed | Cross-check worker heartbeats/processes |
| Comparing durations across days with different volumes | Easy to misdiagnose regressions | Combine volume, throughput, and p95 |
| Manually updating `BATCH_STEP_EXECUTION` | Can corrupt metadata/restart state | Read via `JobExplorer` or read-only queries |
| Watching only completed-run timers | Cannot detect currently hung steps | `LongTaskTimer` and active execution checks |

## 15. Hands-on Exercises

Build a `nightlyInvoiceImport` job with three steps: `downloadInvoices`, `validateInvoices`, and `persistInvoices`. Each night, the job processes data for a fixed `businessDate`.

Requirements:

1. Enable Spring Boot Actuator and Micrometer, and inspect `spring.batch.step` after the job completes.
2. Write a service using `JobExplorer` returning a list of steps containing `stepExecutionId`, `status`, `startTime`, `endTime`, `durationMillis`, `readCount`, and `writeCount`.
3. Write unit tests for the duration calculation function covering three cases: 150 seconds, a running step without `endTime`, and metadata with reversed timestamps.
4. Write an integration test running a real step and verifying that the framework persisted start and end times.
5. Create two fixtures: 100,000 invoices processed in 10 minutes and 180,000 invoices processed in 18 minutes. Explain why duration increased while throughput did not drop.
6. Design a dashboard showing per-step duration, active duration, read/write counts, rollbackCount, and status.
7. Simulate one partition taking 20 minutes while three other partitions take 5 minutes; identify the bottleneck partition and explain why you cannot sum all four to get wall-clock job duration.
8. Simulate `persistInvoices` failing and then being restarted. Record the duration of each `StepExecution` separately as well as an aggregate metric across attempts.
9. Configure an alert when `persistInvoices` runs longer than 45 minutes. List the checks to perform before concluding the worker is hung.

**Review question:** If `spring.batch.step` shows all completed runs of `persistInvoices` finished under 15 minutes yet one execution is currently still `STARTED` after 90 minutes, is the system healthy? **You cannot conclude it is healthy.** Monitor `LongTaskTimer`, inspect the current worker and potential bottlenecks; the Timer for completed runs does not reflect an execution that is currently hung.

## 16. References

- [Spring Batch Reference — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): Micrometer integration, meter names, and how to monitor jobs/steps.
- [Spring Batch 5.2 — StepExecution API](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/StepExecution.html): `getStartTime()`, `getEndTime()`, `getStatus()`, and counters.
- [Spring Batch 5.2 — JobExplorer API](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/explore/JobExplorer.html): querying job/step execution metadata.
- [Spring Batch — Metadata Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): `BATCH_JOB_EXECUTION` and `BATCH_STEP_EXECUTION` tables.
- [Spring Boot Reference — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): metrics endpoint, registry, and duration distributions.
- [Micrometer Reference — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): `Timer`, `LongTaskTimer`, and measuring durations.
- [Prometheus Documentation — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/): reading histograms and percentiles from duration samples.
