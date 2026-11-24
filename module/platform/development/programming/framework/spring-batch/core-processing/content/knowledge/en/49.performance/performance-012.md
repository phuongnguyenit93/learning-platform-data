# Representative Data Benchmarking in Spring Batch

A Spring Batch Job may process 10,000 test records very quickly yet slow down dramatically on millions of real-world records—especially if the data contains duplicates, skewed key distributions, oversized records, high error rates, or hot records updated repeatedly. Therefore, when evaluating **Spring Batch Core Processing** performance, choosing **representative data** is just as important as measuring execution time.

**Representative data benchmarking** is the process of building a test workload reflecting the characteristics that drive real processing costs, executing the Job in a controlled environment and procedure, and measuring outcomes with consistent metrics. The goal is not merely to learn "how many seconds the Job took," but to understand **why speed changes, where the system bottlenecks, and which configuration satisfies operational requirements**.

This lesson belongs to the **Performance** section. It covers defining representative workloads, preparing fixtures, structuring end-to-end measurements, analyzing Job/Step and infrastructure metrics, and testing chunk, transaction, and parallelism configurations.

## 1. How Benchmarking Differs from Functional Tests and Stress Tests

| Test Type | Primary Question | Data and Outcome |
| --- | --- | --- |
| **Functional test** | Does the Job read, process, and write accurately? | Small fixtures focused on business rules and assertions. |
| **Representative benchmark** | With production-like data, how fast does the Job run and what resources does it consume? | Volume, error rates, key skew, record sizes, and infrastructure mirror target load. |
| **Load test** | Does the system sustain normal or expected peak load? | Tests operationally meaningful load levels and Job frequencies. |
| **Stress test** | Where is the saturation point and how does the system fail? | Pushes load beyond design limits while watching errors, timeouts, and rollbacks. |
| **Soak test** | Do repeated continuous cycles leak memory or degrade speed? | Long-running executions tracking heap, GC, connections, metadata, and disk. |
| **Regression benchmark** | Is the new release significantly slower than the baseline? | Same procedure and dataset, comparing time and resource distributions. |

Benchmarking focuses on **reproducible comparisons**. One unusually fast run proves nothing about a better configuration; one slow run caused by a concurrent database backup does not prove worse code.

In Batch, correctness remains non-negotiable. If an "optimization" skips 20% of records, apparent throughput rises while the benchmark result is invalid.

## 2. What Makes Data Representative?

"Having one million records" does not guarantee representativeness. Two one-million-row datasets can impose completely different loads.

Consider a Job `importPaymentsJob` that reads transactions, validates formats, looks up account details, computes statuses, and writes to PostgreSQL. Each of the following factors alters performance:

| Data Characteristic | Questions to Answer | Typical Impact |
| --- | --- | --- |
| Row count | How many on a normal day vs. peak day? | Read, process, write times, and commit costs. |
| Record size | What are average and P95/P99 payload lengths? | I/O, memory, serialization, and network traffic. |
| Key distribution | Do transactions cluster on a few accounts/merchants? | Hot partitions, cache misses, lock contention. |
| Uniqueness and duplicates | What fraction of business keys are duplicates? | Index lookups, deduplication, upserts, unique constraints. |
| Null / invalid rate | How many records miss fields or fail format checks? | Validation, skips/retries, logging, and error paths. |
| Filter rate | How many records does `ItemProcessor` filter out? | `readCount` diverges from `writeCount`; processing cost shifts. |
| Cardinality | How many distinct customers/products/accounts exist? | Cache hit rates, joins/indexes, lookup memory. |
| Value distribution | Are there hot keys, extreme values, long strings, or huge groups? | Contention, partition skew, worst-case latency. |
| Input ordering | Is the input pre-sorted or shuffled? | Page cache locality, index lookups, chunk distribution. |
| Data relationships | Are there parent-child links, foreign keys, or reference data? | Joins, validation, transactions, and deadlocks. |
| Pre-existing data | Is the target table empty or holding tens of millions of rows? | B-tree/index depth, locks, inserts vs. updates. |
| Temporal variance | Do month-end or year-end peaks differ from normal days? | Ability to meet SLAs under worst-case conditions. |

A solid fixture is defined by a **workload profile** spanning these parameters, not merely a CSV filename.

### Avoid Benchmarking on Overly "Clean" Data

If data is uniformly random, every ID is unique, every payload has identical length, and zero records fail validation, a benchmark skips production's costliest work: hot-key lookups, validation, retries, skips, batch updates, and unique constraint checks.

Conversely, a dataset with 80% errors is also unrepresentative if normal production sees only 0.2% errors. Separate **baseline scenarios** from **boundary/edge scenarios** instead of mixing everything into one measurement.

## 3. Building a Workload Profile Before Generating Data

Suppose a system processes daily payment transactions. A benchmark data specification might describe:

| Parameter | Normal Day (Example) | Peak Day (Example) | Anomaly Scenario (Example) |
| --- | ---: | ---: | ---: |
| Transaction count | 500,000 | 3,000,000 | 1,000,000 |
| Input size | 250 MB | 1.5 GB | 650 MB |
| Invalid data rate | 0.2% | 0.4% | 5% |
| Duplicate business key rate | 0.5% | 1% | 10% |
| Share of hot-account traffic | 50% | 70% | 90% |
| P95 description field length | 200 chars | 400 chars | 1,000 chars |
| Existing target-table rows | 5 million rows | 30 million rows | 30 million rows |
| Completion target | Under 10 minutes | Under 40 minutes | No standard SLA |

**All figures in this table are illustrative**, not statistics from a real system. On real projects, derive them from approved operational telemetry.

Every profile should specify:

1. **Schema versions** for input and output.
2. **Telemetry source**: observation window, sampling method, peak dates, confidence level.
3. **Volume and distributions**: total rows, sizes, skew, duplicates, nulls, and invalids.
4. **Seed** or dataset ID to regenerate exact inputs.
5. **Target system state**: empty, partially populated, heavily indexed, cold/warm cache.
6. **Job parameters**: business mode, window, insert/update mode, chunk size.
7. **Output invariants**: expected row counts, unique ID set, allowed skip/filter counts.

Maintain separate profiles for real workloads such as "normal day," "month-end," and "high-error batch"; avoid averaging every scenario into a single synthetic shape that matches no real day.

## 4. Data Sources: Snapshots, Anonymized Data, or Synthetic Data?

Three common approaches exist.

### 4.1. Approved Snapshots

A snapshot from a representative environment preserves real distributions, relationships, and payload sizes. However, it requires explicit approval and data protection; never copy raw production data containing customer PII into a benchmark environment.

When using real data, apply proper anonymization/masking and verify that masking **does not distort** benchmark properties. Replacing every customer ID with the same constant string destroys cardinality, skew, and unique-index behavior.

### 4.2. Synthetic Data

Generating data programmatically with a fixed seed is popular for sharing fixtures, reproducing results, and testing edge cases. Preserve not just row counts, but cross-column correlations.

For instance, an account's transaction volume may correlate with region, product type, and transaction amount. Generating every column independently at random presents query planners and caches with an unrealistic workload.

### 4.3. Hybrid Fixtures

A practical strategy uses a safely processed snapshot to extract statistical distributions, then generates synthetic data matching those distributions. Add targeted fixtures for rare edge cases: huge payloads, encoding quirks, hot keys, or prolonged retries.

Store data generation parameters in version control alongside generator code. You do not need to commit multi-gigabyte files to Git if they can be regenerated deterministically.

## 5. Generating Deterministic Synthetic Data with a Fixed Seed

The Java example below writes a CSV with skewed account IDs where most transactions hit a small set of accounts. Values and ratios merely illustrate generation technique.

```java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.SplittableRandom;

public final class PaymentCsvFixtureGenerator {

    public static void generate(
            Path destination, long numberOfRows, long seed)
            throws IOException {

        SplittableRandom random = new SplittableRandom(seed);

        try (BufferedWriter writer =
                Files.newBufferedWriter(
                        destination, StandardCharsets.UTF_8)) {

            writer.write("payment_id,account_id,amount_cents,status,note");
            writer.newLine();

            for (long i = 1; i <= numberOfRows; i++) {
                // 65% of transactions concentrate on 1,000 accounts.
                long accountId = random.nextDouble() < 0.65
                        ? random.nextLong(1, 1_001)
                        : random.nextLong(1_001, 100_001);

                long amountCents = random.nextLong(100, 500_001);

                // 1% of records require processing down the INVALID branch.
                String status = random.nextDouble() < 0.01
                        ? "INVALID" : "VALID";

                // Short/long description following a controlled distribution.
                int descriptionLength = random.nextDouble() < 0.95
                        ? 20 : 500;

                String note = "x".repeat(descriptionLength);

                writer.write(i + "," + accountId + ","
                        + amountCents + "," + status + "," + note);
                writer.newLine();
            }
        }
    }
}
```

Invocation:

```java
PaymentCsvFixtureGenerator.generate(
        Path.of("build/benchmark/payments.csv"),
        1_000_000,
        20261116L
);
```

This requires Java 17 or newer. The output file contains a header plus one million rows. A fixed seed and parameters reproduce the **exact same record sequence** whenever the same generator code runs.

In real projects, extend the generator to produce:

- Controlled rates of duplicate business keys.
- Missing fields, nulls, out-of-range values, and special encodings.
- Valid parent-child rows and foreign-key references.
- Heavy-tailed distributions for payload sizes or records per merchant.
- Business dates with seasonal or event spikes.
- Compressed files or JSON/Avro/Parquet formats if the Job consumes them.

If benchmarking a Job reading from cloud object storage, generating a local CSV and reading from the same SSD misses network latency, object-storage APIs, and download mechanics. Source data must traverse an **I/O path matching your measurement target**.

### Verify the Fixture Before Timing

Verify exact generated row count, invalid rate, unique key count, and file size. For important workloads, save a **manifest** alongside the dataset recording seed, schema version, checksums, row counts, distribution stats, and generation timestamp.

Run fixture verification **outside the Job timing window** so input validation never skews benchmark timings.

## 6. Preparing a Comparable Runtime Environment

Two runs on different environments cannot be compared fairly even with the exact same CSV.

Record at minimum:

| Component | Details to Lock Down or Record |
| --- | --- |
| Java / JVM | JDK vendor/version, heap size, GC collector, key JVM flags. |
| Spring Boot / Spring Batch | Framework versions, Job config, reader/processor/writer beans. |
| Database | Engine/version, CPU/RAM/storage specs, isolation level, indexes, and table stats. |
| JDBC / pool | Driver, pool size, timeouts, fetch size, batch writer settings. |
| Job host | vCPU count, memory, container limits, node placement. |
| File and network | Local SSD, network share, object storage, bandwidth, and latency. |
| Workload | Dataset ID/checksum, row count, distributions, target table state. |
| Job | Chunk size, commit interval, thread count, partitioning, retry/skip policies. |
| Background load | Other jobs, DB maintenance, backups, autoscaling, antivirus, monitoring. |
| Measurement | Warm-up runs, iteration count, timer boundaries, percentile method. |

Shared CI benchmarks can catch major regressions, but cannot reliably judge single-digit percentage changes when hosts and databases experience fluctuating load. For high-impact tuning decisions, use an isolated stable environment or run enough iterations and inspect variance.

### Cold Cache vs. Warm Cache Are Different Scenarios

- **Cold run:** data and OS page caches are unpopulated; I/O costs can be substantially higher.
- **Warm run:** data, connections, and JIT-compiled code are already warmed by prior executions.

Never mix cold runs and warm runs into a single "average time." Measure "first run after deployment" and "steady-state daily run" separately depending on operational goals.

Dropping OS page caches on a shared host is generally inappropriate and disrupts other workloads. If true cold-cache testing is needed, provision an isolated test environment rather than touching production hosts.

## 7. Defining Timing Boundaries

A Job involves multiple cost phases:

```text
Prepare fixture ── Launch Job ── Read ── Process ── Write/Commit ── End
      |               |                                      |        |
      A               B                                      C        D
```

Depending on your goal, measure distinct intervals:

- **End-to-end latency (B → D):** from when the app initiates launch until the Job reaches terminal completion and results are observable.
- **Job processing duration:** from when the Job enters its pipeline until processing finishes.
- **Step duration:** elapsed time per Step.
- **Chunk latency:** time to process and commit a single chunk.
- **Preparation time (A → B):** generating/loading fixtures, truncating tables, running migrations; report separately unless part of production SLA.

Always **document measurement boundaries**. If one team times only `ItemProcessor` while another times full DB writes, their throughput numbers are not comparable.

### Watch Out for Asynchronous Launchers

In Spring Batch, launchers/operators may use an asynchronous `TaskExecutor`. Calling launch then returns immediately with `STARTING` or `STARTED`. Timing right before and after the launch call measures only **submission time**, not actual Job execution duration.

To benchmark end-to-end duration:

1. Capture `System.nanoTime()` before invoking the launcher.
2. Launch the Job and obtain its `jobExecutionId`.
3. If the launcher is asynchronous, poll/wait for a terminal status with a timeout via `JobExplorer` or a controlled completion barrier.
4. Capture the end timestamp once status is truly terminal.
5. Assert `BatchStatus` and business outputs before accepting the timing sample.

`System.nanoTime()` is suited for elapsed durations within a single JVM. Never subtract timestamps from two unsynchronized hosts to measure millisecond latency.

## 8. A Reproducible Spring Batch Benchmark Procedure

Recommended workflow:

```text
Select workload profile and pass criteria
             |
             v
Generate/initialize fixture + measure size/distribution
             |
             v
Lock environment, Job config, and target table state
             |
             v
Warm-up (excluded from reported metrics)
             |
             v
Repeat N times:
  ├─ Reset/seed input and target data (outside timer)
  ├─ Build JobParameters for the run
  ├─ Start timer
  ├─ Run Job to terminal status
  ├─ Stop timer
  ├─ Assert status + output data
  └─ Record metrics and clean up for next run
             |
             v
Compute p50, p95, min/max, throughput, and variance
             |
             v
Compare against baseline + inspect DB/JVM bottlenecks
```

Run at least one warm-up before recording metrics; with JIT compilation, connection pools, caches, and heavy dependencies, base warm-up count on observed stabilization.

Iteration count also scales with Job runtime: a 40-minute Job permits fewer repetitions than a 20-second Job, in which case explicitly report uncertainty and avoid claiming tiny improvements as proven.

## 9. Integration Benchmark Example with Spring Batch 5.x

This example uses **Spring Batch 5.x**, **Spring Boot 3.x**, JUnit Jupiter, AssertJ, and `spring-batch-test`. Assume the application defines an `importPaymentsJob` bean and a test fixture service `PaymentBenchmarkFixture` with:

- `resetAndLoad(int rowCount, long seed)`: clears prior output and seeds inputs **before timing starts**.
- `assertProcessed(int rowCount)`: verifies business-contract outputs **after stopping the timer**.

`PaymentBenchmarkFixture` is a **project-implemented test helper**, not a built-in Spring Batch class.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class ImportPaymentsBenchmarkIT {

    private static final int ROWS = 100_000;
    private static final long SEED = 20261116L;
    private static final int WARMUP_RUNS = 2;
    private static final int MEASURED_RUNS = 8;

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    @Qualifier("importPaymentsJob")
    private Job job;

    @Autowired
    private PaymentBenchmarkFixture fixture;

    @Test
    void benchmarkWithRepresentativeFixture() throws Exception {
        jobLauncherTestUtils.setJob(job);
        List<Long> durationsMs = new ArrayList<>();

        for (int run = 0;
                run < WARMUP_RUNS + MEASURED_RUNS;
                run++) {

            // Outside the timed window: identical input data each run.
            fixture.resetAndLoad(ROWS, SEED);

            // Each independent run creates a distinct JobInstance.
            JobParameters params = new JobParametersBuilder()
                    .addString(
                            "benchmarkRunId",
                            UUID.randomUUID().toString(),
                            true)
                    .addString("dataset", "payments-100k", false)
                    .toJobParameters();

            long startedNanos = System.nanoTime();
            JobExecution execution =
                    jobLauncherTestUtils.launchJob(params);
            long elapsedNanos = System.nanoTime() - startedNanos;

            assertThat(execution.getStatus())
                    .isEqualTo(BatchStatus.COMPLETED);
            fixture.assertProcessed(ROWS);

            if (run >= WARMUP_RUNS) {
                durationsMs.add(
                        TimeUnit.NANOSECONDS.toMillis(elapsedNanos));
            }
        }

        Collections.sort(durationsMs);

        long p50 = percentileNearestRank(durationsMs, 0.50);
        long p95 = percentileNearestRank(durationsMs, 0.95);

        System.out.printf(
                "rows=%d samples=%d p50Ms=%d p95Ms=%d%n",
                ROWS, durationsMs.size(), p50, p95
        );
    }

    private static long percentileNearestRank(
            List<Long> sortedSamples, double quantile) {
        if (sortedSamples.isEmpty()) {
            throw new IllegalArgumentException("No measurements");
        }

        int rank = (int) Math.ceil(quantile * sortedSamples.size());
        int index = Math.max(0, Math.min(
                rank - 1, sortedSamples.size() - 1));

        return sortedSamples.get(index);
    }
}
```

This test illustrates a **benchmark harness** without database/file-specific fixture code. Ensure `PaymentBenchmarkFixture` genuinely reloads identical inputs, resets target tables, and validates real Job outputs. Never rely on row-count-only assertions if duplicate business keys are possible.

This example assumes a **synchronous** launcher. With an asynchronous launcher, adapt timing per Section 7 to await terminal status with a timeout; otherwise, measurements capture only submission latency.

### Why Require a New `benchmarkRunId`?

A `JobInstance` is identified by Job name plus identifying `JobParameters`. Reusing the exact parameters of a `COMPLETED` Job causes Spring Batch to reject subsequent launches with `JobInstanceAlreadyCompleteException`.

Here `benchmarkRunId` is an identifying parameter keeping each benchmark run independent. For **restart** benchmarks, use a separate scenario that preserves the exact same identifying parameters between the failed run and the restart run.

### Do Not Mix Reset Cost into the Timed Window

`fixture.resetAndLoad(...)` may delete and insert hundreds of thousands of rows; placing it between `startedNanos` and `elapsedNanos` corrupts Spring Batch Job timing. In production, if a Job includes its own staging or ingestion step, include that step deliberately inside the timer scope.

### Do Not Purge Metadata Prematurely

Keep `JobExecution`/`StepExecution` records after the Job finishes long enough to inspect metrics and diagnose anomalies. When cleaning up metadata, use only a dedicated test repository and tools like `JobRepositoryTestUtils`. Never purge metadata while an asynchronous Job is still running.

Reset business tables independently of Spring Batch metadata. Rolling back a test method's transaction does not roll back chunk transactions already committed by the Job.

## 10. Key Metrics for Benchmarks

### 10.1. Throughput

Throughput is typically defined as:

\[
\text{Throughput} = \frac{\text{Processed items}}{\text{Measurement duration (seconds)}}
\]

For example, a Job processing 1,000,000 records in 125 seconds:

\[
\frac{1,000,000}{125} = 8,000\ \text{items/second}
\]

**State explicitly whether "items" means items read, items written, or successful business units.** If 30% of inputs are filtered or skipped, `readCount` throughput differs from `writeCount` throughput. Both can be useful, yet never swap denominators silently.

Additional helpful metrics:

- Bytes processed/second for variable-size payload Jobs.
- Rows written/second for write-heavy database Jobs.
- Business entities completed/second for Jobs aggregating multiple records.
- Scheduled windows/hour when Jobs run on recurring windows.

### 10.2. Latency

- **Job wall-clock duration:** actual time operators wait for results.
- **Step duration:** identifies which Step consumes the most time.
- **Chunk duration:** reveals slow commits or abnormally slow item groups.
- **Per-item latency:** useful when the processor calls external APIs, though it does not directly reflect total chunk/transaction cost.

### 10.3. Reliability and Outcomes

- Final `BatchStatus` and `ExitStatus`.
- `readCount`, `writeCount`, `filterCount`, and `skipCount`.
- `commitCount`, `rollbackCount`, retry counts, and errors by type.
- Unique record counts in target tables, checksums, or business-key checks.
- Restartability and duplicate safety under failure.

A faster configuration that introduces rollbacks, deadlocks, or corrupted data is never a valid performance improvement.

### 10.4. Infrastructure Resources

| Layer | Observed Metrics | Common Signals |
| --- | --- | --- |
| JVM | Heap used, allocation rate, GC pauses, CPU, thread count | Heavy allocations, memory pressure, thread contention. |
| Database | CPU, active sessions, locks, slow queries, buffer hits, WAL/redo | Query/index bottlenecks, expensive commits, lock contention. |
| Connection pool | Active/idle/pending connections, connection wait time | Undersized pool or saturated database. |
| File / storage | Read/write throughput, IOPS, latency, page cache | I/O-bound reader or writer. |
| Network | Latency, throughput, retries, socket timeouts | Remote API/object store/DB over network is the bottleneck. |
| Spring Batch | Step statuses, counters, chunks, commits, rollbacks | Processing overhead, transaction size, per-step failures. |

Telemetry from Micrometer, Java Flight Recorder (JFR), database monitors, connection pool metrics, and Job/Step logs helps explain numbers. You do not need heavy profiling on every benchmark run since profilers add overhead; clearly mark which runs had profiling enabled.

## 11. Instrumentation with `JobExecutionListener`

A Job-level listener measures execution duration **from `beforeJob` to `afterJob`**. This is an internal timing measurement and differs slightly from launcher-level end-to-end duration.

Spring Batch 5.x example:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.stereotype.Component;

@Component
public final class JobTimingListener
        implements JobExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(JobTimingListener.class);

    private final ConcurrentMap<Long, Long> startedAt =
            new ConcurrentHashMap<>();

    @Override
    public void beforeJob(JobExecution execution) {
        startedAt.put(execution.getId(), System.nanoTime());
    }

    @Override
    public void afterJob(JobExecution execution) {
        Long start = startedAt.remove(execution.getId());
        if (start == null) {
            return;
        }

        long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - start
        );

        log.info(
                "batch.job.timing jobName={} jobExecutionId={} "
                    + "jobInstanceId={} status={} durationMs={}",
                execution.getJobInstance().getJobName(),
                execution.getId(),
                execution.getJobInstance().getInstanceId(),
                execution.getStatus(),
                elapsedMs
        );
    }
}
```

Register the listener on the Job builder. `@Component` creates a Spring bean, which does not automatically attach it to every Job.

Because the listener is a singleton, `ConcurrentHashMap` prevents concurrent `JobExecution`s from overwriting each other's timestamps. Calling `remove(...)` in `afterJob` frees state. If the JVM is killed abruptly, `afterJob` will not execute; never rely solely on a listener for audit or retention of every measurement.

If metadata-level timing suffices, read `startTime` and `endTime` from `JobExecution` after completion. However, timestamp resolution and persistence timing depend on framework version and schema; for comparing small changes, a monotonic in-JVM clock is usually better.

### Log Identifiers, Avoid High Cardinality in Metrics

Include `jobExecutionId` in logs to investigate slow runs. However, when exporting metrics via Micrometer/Prometheus, **do not attach `jobExecutionId` as a tag**: every run generates a new value, exploding time-series cardinality.

Good low-cardinality tags include `jobName`, `stepName`, `status`, `environment`, and a bounded set of benchmark profiles. Use logs and distributed traces to inspect individual executions.

## 12. Breaking Down Cost by Step and Chunk

A Job may take 15 minutes without revealing where time went:

```text
Job importPaymentsJob            15 minutes
├── validateInputStep             1 minute
├── loadReferenceDataStep         1 minute
├── transformAndWriteStep        12 minutes
└── finalizeStep                  1 minute
```

Here, the third Step dominates runtime. Drill down further into:

- `read()` time: file reads, DB queries, parsing, deserialization.
- `process()` time: validation, lookups, transformations, service calls.
- `write()` time: JDBC batch inserts/upserts, API calls, serialization.
- Transaction commit time: WAL/redo writes, flushes, locks.
- Wait time: connection pools, thread queues, downstream APIs, filesystems.

Never jump to "the processor is slow" just because a chunk-oriented Step is slow. Step duration covers reader, writer, transactions, retries, skips, and more.

### Listeners for Observability

Spring Batch provides hooks such as `ItemReadListener`, `ItemProcessListener`, `ItemWriteListener`, `ChunkListener`, and `StepExecutionListener` for stage-level telemetry.

However, item callbacks fire at very high frequency. If a million items trigger an INFO log on every read, process, and write, logging overhead can turn your benchmark into a **logging benchmark** rather than measuring real processing cost.

Prefer:

1. Minimal counters/timers for telemetry.
2. Aggregation per Step, chunk, or time window.
3. Sampled logging when per-item debugging is needed.
4. Comparing a run with instrumentation against one with production logging to quantify observer overhead.

When a Step runs multi-threaded or partitioned, instrumentation must be thread-safe and independent of cross-thread callback ordering.

## 13. Benchmarking Chunk Size and Commit Interval

In chunk-oriented processing, Spring Batch executes a loop:

```text
read -> process -> read -> process -> ... [full chunk]
                       |
                       v
                    write(...)
                       |
                       v
                commit transaction
                       |
                       v
                   next chunk
```

Chunk size affects:

| Small Chunks | Large Chunks |
| --- | --- |
| More frequent commits. | Fewer commits for the same record count. |
| Shorter transactions. | Transactions hold resources longer. |
| Lower chunk buffer memory. | Chunk memory footprint grows. |
| Higher transaction overhead. | On rollback, larger chunks may redo more work. |
| May underutilize batch writes. | Better write batching until DB/driver limits hit. |

No single chunk size is optimal for every Job. Common candidate sizes include 100, 500, and 1,000 items/chunk, yet these are only **candidates** to measure against real workloads and memory limits.

Example test matrix:

| Run | Chunk Size | Thread Count | Reader/Writer | Dataset |
| --- | ---: | ---: | --- | --- |
| A | 100 | 1 | Fixed config | Normal-day profile |
| B | 500 | 1 | Fixed config | Same profile, same seed |
| C | 1,000 | 1 | Fixed config | Same profile, same seed |

Hold all other settings constant so differences can be attributed cleanly to chunk size. Only after finding a good chunk size should you test concurrency or writer changes.

Spring Batch 5.x Step example:

```java
@Bean
Step processPaymentsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Payment> reader,
        ItemProcessor<Payment, Payment> processor,
        ItemWriter<Payment> writer) {

    return new StepBuilder("processPaymentsStep", jobRepository)
            .<Payment, Payment>chunk(500, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

`Payment` and the reader/processor/writer beans are application-defined. Never tune chunk size while ignoring retry/skip rules and transaction limits; if retries or rollbacks spike, a configuration with higher average throughput can still degrade operations.

## 14. Benchmarking Parallelism: Thread Count and Partitioning

After establishing a single-threaded baseline, evaluate multi-threaded Steps or partitioning to leverage multiple CPUs or parallel I/O.

Example test matrix:

| Configuration | Chunk Size | Threads | Partitioning | Goal |
| --- | ---: | ---: | --- | --- |
| Baseline | 500 | 1 | None | Sequential baseline runtime. |
| Parallel 2 | 500 | 2 | None | Measure scaling with 2 workers. |
| Parallel 4 | 500 | 4 | None | Separate CPU, DB, and I/O bottlenecks. |
| Partition 4 | 500 | Per executor | 4 partitions | Isolate disjoint data slices. |

**More threads do not guarantee linear throughput scaling.** If the database grants 4 connections and other services hold 3, spawning 16 workers mostly creates connection waits. Similarly, writers updating overlapping hot rows trigger lock contention, retries, and deadlocks.

During parallel benchmarks, observe:

- Job and database CPU utilization.
- Active/pending connection pool counts.
- Transaction counts and lock wait durations.
- Executor queue depth and active worker count.
- Rollback, retry, and skip counts.
- Thread safety of `ItemReader`, `ItemWriter`, and any shared state.
- Unique business keys and target data correctness.

If `ItemReader` is not thread-safe, multi-threaded benchmarks yield corrupted or flaky results. Verify concurrent read/write safety first or switch to partitioning over disjoint ranges.

### Skewed Distributions Cause Partition Imbalance

Suppose 4 partitions split by merchant, yet 70% of transactions belong to merchant 1:

```text
Partition 1: ███████████████████████ 70%
Partition 2: ███                      10%
Partition 3: ███                      10%
Partition 4: ███                      10%
```

Even with 4 workers, 3 finish early and sit idle waiting on the straggler. Benchmarking a uniform 25%-per-partition dataset **overestimates** real speedup.

Keep realistic skew in representative benchmarks, or test both uniform and skewed profiles explicitly to evaluate partitioning strategies.

## 15. Computing Benchmark Statistics

Suppose a Job runs on the same 100,000-record dataset 8 times after warm-up, yielding:

```text
Duration (seconds):
12.1, 11.9, 12.4, 13.0, 12.0, 12.2, 12.5, 13.7
```

**These are hypothetical numbers** to illustrate reporting, not real measurements.

Common summary statistics:

- **Min / Max:** fastest and slowest observed runs.
- **Median (P50):** middle sorted value; far less sensitive to outliers than the mean.
- **P95:** threshold at or below ~95% of samples; highlights slow tail runs.
- **Mean:** total duration divided by runs; useful but easily skewed by outliers.
- **Standard deviation or IQR:** run-to-run variance.
- **Throughput:** processed or committed items divided by each run's duration.

With small sample sizes like 8, **P95 is practically the slowest single run** under nearest-rank calculation. Never base hard P95 SLA guarantees on a handful of trials. Collect larger sample sizes across operational cycles or apply appropriate statistical methods when tail confidence matters.

### Benchmark Report Table

| Metric | Baseline (Example) | Candidate (Example) | Interpretation |
| --- | ---: | ---: | --- |
| Dataset | 1,000,000 records | 1,000,000 records | Identical seed and distribution |
| Chunk size | 100 | 500 | Primary variable changed |
| Threads | 1 | 1 | Held constant |
| Median duration | 150 s | 125 s | Candidate faster at median |
| Throughput from median | ≈6,667 rows/s | 8,000 rows/s | Explicitly define "rows processed" |
| P95 duration | 175 s | 140 s | Candidate has lower tail latency |
| Max heap | 1.1 GB | 1.6 GB | Candidate uses more memory |
| Rollback count | 0 | 0 | No change in transaction failures |
| Data correctness | Valid | Valid | Both satisfy business contract |

All numbers in this table are **illustrative**. Never claim a candidate delivers "20% better performance" from a table lacking iteration counts, environment specs, variance, and clear workload conditions.

### Operationally Meaningful Differences

Shaving median duration from 125 seconds to 123 seconds is likely noise if run-to-run variance is ±10 seconds. Cutting runtime from 40 minutes to 20 minutes across repeated equivalent runs is operationally significant.

Compare **resource cost** too. A configuration running 10% faster while consuming three times as many database connections may hurt overall batch windows when multiple Jobs overlap.

## 16. Identifying Bottlenecks from Telemetry

Do not tune blindly by increasing chunk size or thread count. Tie measurements to concrete system limits.

### 16.1. Reader or File I/O

Symptoms:

- Low CPU while the reader consumes most time.
- High file or object-storage latency.
- Throughput jumps sharply when data is cached.
- Poor `fetchSize` or pagination queries.

What to check: file encoding, compression, I/O buffering, query plans, fetch size, indexes, storage network latency, and reader cursor handling.

### 16.2. CPU-Bound Processor

Symptoms:

- High JVM CPU while database and I/O sit largely idle.
- Rising allocations/GC alongside heavy parsing, regexes, or serialization.
- Per-item time scales predictably with input payload size.

What to check: JFR or CPU profiler traces, unnecessary allocations, lookup algorithms, reference caching, and thread-safe concurrency.

### 16.3. Writer or Database

Symptoms:

- High DB CPU, I/O, or transaction latency.
- Rising connection pool pending counts.
- Increasing lock waits, duplicate checks, or index updates.
- Large chunks causing heavy rollbacks or long transactions.

What to check: JDBC batching, query plans, indexes, constraints, locking, batch upserts, commit interval, and pool sizing. Never disable data integrity constraints just to make benchmarks look faster if production enforces them.

### 16.4. Skewed Data Distribution

Symptoms:

- One partition runs far longer than all siblings.
- Contention around specific hot business keys.
- Scaling thread count fails to improve speed.

What to check: key distribution in the dataset, partitioning strategy, work-sharding boundaries, and hot-updated rows.

### 16.5. Retries, Skips, or External APIs

Symptoms:

- Job runs fast on clean data, collapses as error rate rises.
- High `rollbackCount`, timeouts, and backoffs.
- External API enforces rate limits.

What to check: real error rates, skip/retry policies, exponential backoff, circuit breakers, and downstream quotas. Never push concurrency past downstream rate limits just to make isolated test throughput look good.

## 17. Ensuring Fair Comparisons Between Two Versions

When measuring before and after a change:

1. **Keep the workload profile and seed identical** or use standardized equivalent datasets.
2. **Reset schema and data state identically** before every run, including indexes and pre-existing row counts.
3. **Record application commit hash/build version** along with Java and database versions.
4. **Hold resource limits constant**—container quotas, pools, and executors—except the tested variable.
5. **Apply consistent warm-up**, separating cold vs. warm results.
6. **Run multiple iterations** in controlled order; consider interleaving A/B runs to mitigate environmental drift.
7. **Verify business outputs** of every run before accepting its timing.
8. **Document outliers with context** (DB backups, long GC, pod rescheduling) instead of silently discarding them.
9. **Check `JobRepository` state** so completed `JobInstance`s are never accidentally skipped or reused.
10. **Archive raw per-run measurements**, not just P50 or a headline percentage.

Avoid changing multiple parameters at once if you need to understand causality. Changing chunk size, thread count, and DB indexes together may improve speed without revealing which change mattered.

### Single-Job Benchmarks vs. Production Multi-Job Contention

A Job may fly in test when it owns 100% of database CPU, yet share resources with APIs and sibling Jobs in production. Pair "single-Job" benchmarks with an "overlapping batch window" workload profile whenever production runs concurrently.

## 18. Representative Data for Restarts, Skips, and Failures

Happy-path-only benchmarks fail to represent Batch systems that must restart and handle bad records.

### Skip / Filter Scenarios

If the Job skips invalid records, benchmark a dedicated profile with realistic invalid rates. Assert `skipCount`, `filterCount`, `readCount`, and `writeCount` afterward.

### Retry Scenarios

If the writer calls an API or database prone to transient errors, inject failures at controlled frequencies and durations. Retry/backoff delays can dominate total Job duration. Never let random network hiccups skew A/B comparisons unfairly.

### Restart Scenarios

A restart benchmark must:

1. Launch the Job with fixed identifying parameters for a unit of work.
2. Deliberately inject a failure at a deterministic checkpoint.
3. Record the `FAILED` `JobExecution` and verify restart metadata persisted.
4. Clear the failure condition and relaunch with the **exact same identifying parameters**.
5. Measure restart duration and total recovery time.
6. Verify zero missing or duplicate records after restart.
7. Clean up metadata only after the entire scenario finishes.

Never generate a new `benchmarkRunId` on the restart run, as that creates a separate `JobInstance`. Never wipe metadata tables between the two runs, as that erases the checkpoint.

### Measure Recovery Cost Too

For critical workloads, a fast configuration that must reprocess millions of rows after a crash can be worse operationally than a slightly slower configuration with tight checkpoints. Include **recovery time** and rework volume in your performance criteria.

## 19. Recording Results and Establishing a Baseline

Each run can be stored as a structured JSON record:

```json
{
  "benchmarkId": "payments-normal-v1",
  "dataset": {
    "profile": "normal",
    "rows": 1000000,
    "seed": 20261116,
    "generatorVersion": "v1"
  },
  "environment": {
    "jdk": "17",
    "springBatchLine": "5.x",
    "database": "postgresql-test",
    "cpuLimit": "4 vCPU",
    "heap": "2 GiB"
  },
  "configuration": {
    "chunkSize": 500,
    "threads": 1
  },
  "result": {
    "jobStatus": "COMPLETED",
    "wallTimeMs": 125000,
    "readCount": 1000000,
    "writeCount": 1000000,
    "skipCount": 0,
    "outputValidated": true
  }
}
```

This is a **report format template**, not real measured data. In real projects, also capture commit hash, DB schema version, fixture checksum, timestamps, warm-up policy, CPU/GC/DB metrics, and raw log files.

A per-run summary table might capture:

```text
benchmark_id,run_id,profile,rows,chunk_size,threads,status,
elapsed_ms,read_count,write_count,skip_count,commit_count,
rollback_count,peak_heap_mb,db_p95_ms,build_sha
```

Keep **raw runs** separate from aggregated statistics. When comparing baseline vs. candidate, state sample counts and the percentile method. If the environment uses autoscaling, document scaling state explicitly.

### Threshold-Based Regression Checks

Define automated checks such as:

- Median duration regresses beyond an agreed percentage vs. accepted baseline.
- P95 exceeds the Batch window or operational SLA.
- Throughput drops while row count and payload sizes stay constant.
- Peak heap breaches safe margins risking OOM.
- Rollbacks, skips, or errors exceed contract limits.
- Output data is invalid, regardless of speed.

Never turn tight wall-time thresholds into blocking CI gates on noisy shared runners. Separate lightweight smoke-performance checks (catching massive regressions) from scheduled benchmarks on dedicated performance environments.

## 20. Practice Exercise: Choosing a Configuration for 2 Million Records

Suppose `importOrdersJob` reads 2,000,000 order lines, validates product codes, computes prices, and writes to PostgreSQL. Production includes normal days and month-end peaks when certain product codes appear far more frequently.

**Business requirements:** process all valid orders within a 20-minute window, never write duplicate business keys, and preserve restartability after failures. Never relax data constraints or retry/skip policies solely to improve speed.

### Phase 1: Build Datasets

1. Create `normal` and `month-end` profiles. Each holds 2 million records, varying hot-product ratio, payload sizes, duplicate rates, and invalid rates.
2. Use fixed seeds; store a manifest with schema, generator version, row counts, and checksums.
3. Prepare product and order tables with production-like indexes, foreign keys, and pre-existing row counts.
4. Verify expected valid counts and skip/filter counts per profile.

### Phase 2: Establish Baseline

1. Lock JDK, Spring Batch version, database, pool, CPU/RAM limits, and log level.
2. Run the Job with chunk size 100 and one thread; warm up before measuring.
3. Repeat multiple iterations, resetting data outside the timer.
4. Record end-to-end duration, read/write throughput, peak heap, GC, DB connection/lock waits, and commits/rollbacks.
5. Assert exact target outputs after every run.

### Phase 3: Sweep Configurations

1. Repeat with chunk size 500, keeping one thread.
2. Repeat with chunk size 1,000, keeping one thread.
3. Select a promising chunk size, then test 2 or 4 workers if reader/writer are thread-safe and the DB has capacity.
4. Compare `normal` vs. `month-end` profiles; observe differences caused by hot keys or skew.
5. Check whether an optimization that speeds up normal workloads degrades under peak workloads.

### Phase 4: Test Recovery

1. Deliberately inject a database failure roughly halfway through the Job.
2. Verify the first `JobExecution` ends `FAILED` with metadata and checkpoints persisted.
3. Clear the fault and restart with the exact same identifying parameters.
4. Measure recovery duration and assert zero duplicate records.
5. Evaluate trade-offs across commit interval, steady-state throughput, and failure rework volume.

**Self-check questions:**

- Why can two CSVs with the same 2 million rows yield vastly different throughput?
- Why does raising `thread count` alone not guarantee faster Job duration?
- With an asynchronous launcher, what does timing immediately around `launchJob(...)` actually measure?
- Why does `readCount` not always equal `writeCount`?
- Is a benchmark that is 15% faster yet doubles peak heap always worth adopting?
- If P95 is computed from 5 runs, what limits its statistical reliability?
- Why must metadata never be cleared between two runs in a restart benchmark?

## 21. References

- [Spring Batch Reference – Domain Language of Batch](https://docs.spring.io/spring-batch/reference/domain.html): `JobInstance`, `JobExecution`, `StepExecution`, and core concepts.
- [Spring Batch Reference – Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): chunk-oriented reading/processing/writing and transactions.
- [Spring Batch Reference – Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): observing Batch metrics and executions.
- [Spring Batch Reference – Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded Steps, split flows, and partitioning.
- [Spring Batch Reference – Testing](https://docs.spring.io/spring-batch/reference/testing.html): tools for testing Jobs and Steps.
- [Micrometer Documentation](https://docs.micrometer.io/micrometer/reference/): timers, counters, and metrics systems.
- [OpenJDK – Java Flight Recorder](https://docs.oracle.com/en/java/javase/17/jfapi/): capturing CPU, allocation, GC, and Java profiling telemetry.

