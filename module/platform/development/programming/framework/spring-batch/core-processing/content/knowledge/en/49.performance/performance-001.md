# Chunk-Oriented Throughput in Spring Batch

## 1. What Is Chunk-Oriented Throughput?

In Spring Batch Core Processing, **chunk-oriented** Steps process data in groups of items: read, process, write, and commit a transaction. When optimizing performance, a common question is: **How long does each chunk take, and how many items per second does the entire Step process?**

**Throughput** is the rate at which a unit of work is completed over a period of time. For Spring Batch, throughput can be observed at multiple levels:

- **Input throughput:** the number of items successfully read per second.
- **Output throughput:** the number of items recorded by the Step as written per second.
- **Chunk throughput:** the number of chunk processing cycles completed per second.
- **Commit throughput:** the number of transaction commits recorded by the Step per second.
- **End-to-end throughput:** the total number of completed business items divided by the end-to-end runtime of the Job or Step.

These metrics are related, yet **not identical**. One chunk may read 500 items, filter out 30 items, and write 470 items. Another chunk may retry, roll back, or have no items to write. Measuring chunk count alone does not tell you the total output volume; measuring item count alone does not tell you the transaction cost.

For example, consider a Step that finishes importing 120,000 items in 40 seconds:

~~~text
Job: importOrdersJob
Step: importOrdersStep
Chunk size: 500

Read:  120,000 items
Write: 117,000 items
Filter:  3,000 items
Wall-clock duration: 40 seconds

Input throughput : 120,000 / 40 = 3,000 items/second
Output throughput: 117,000 / 40 = 2,925 items/second
~~~

This is the average throughput of the entire Step execution. To understand why speed is low or fluctuates, you also need to measure **per-chunk duration**, **transaction commit count**, **rollbacks**, **read/write time**, and **resource utilization**.

This guide explains how to define, measure, analyze, and improve chunk throughput using the built-in tools in Spring Batch 5.x, Spring Boot 3.x, and Micrometer, and highlights common benchmarking pitfalls.

## 2. Chunk Lifecycle and Measurement Points

Consider the following Step:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, OrderOutput> processor,
        ItemWriter<OrderOutput> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, OrderOutput>chunk(500, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

With **chunk size = 500**, Spring Batch attempts to collect a group of up to 500 input items per chunk cycle, process them, and write the results within a transaction boundary managed by the Step. The final chunk may be smaller if the reader runs out of data.

~~~text
             Start chunk
                  |
           Open transaction
                  |
       +----------v----------+
       | ItemReader          |  File / database / API read cost
       +----------+----------+
                  |
       +----------v----------+
       | ItemProcessor       |  Compute / validate / map cost
       +----------+----------+
                  |
       +----------v----------+
       | ItemWriter          |  SQL batch / file write / network cost
       +----------+----------+
                  |
       +----------v----------+
       | Checkpoint, metadata|  Save ExecutionContext / StepExecution
       +----------+----------+
                  |
                Commit
                  |
              End chunk
                  |
              Next chunk
~~~

There are at least three layers of timing:

1. **Per-operation time:** reader, processor, writer, and specific I/O calls.
2. **Chunk time:** the elapsed time from before a chunk begins processing until the chunk completes. With **ChunkListener** callbacks, you can measure from **beforeChunk** to **afterChunk** for the success case.
3. **Step/Job time:** the wall-clock time from start to finish, including initialization, opening/closing resources, transactions, chunks, listeners, and other overhead.

A Step whose processor is very fast but whose commit is slow will still have low throughput. Conversely, increasing the chunk size can reduce commit frequency, but causes each chunk to hold transactions and memory longer.

### Why Can't Commit Count Replace Chunk Count?

**StepExecution.getCommitCount()** records the number of transaction commits managed by the Step. In a simple configuration it is closely tied to chunk processing, but it can also include end-of-data cycles or Step-specific behavior. Moreover, rollbacks, retries, Tasklets, and restarts make simplistic assumptions unreliable.

When you need the **number of successful chunks**, count the **afterChunk** callbacks for the chunks within your scope of interest. When you need the **framework commit count**, use **getCommitCount()**. Do not name these two metrics as if they were always equal.

## 3. Throughput Formulas and Choosing the Denominator

### 3.1. Item Throughput

Over an observation window of length **Δt** seconds:

~~~text
readThroughput  = ΔreadCount  / Δt   (items/second)
writeThroughput = ΔwriteCount / Δt   (items/second)
~~~

The **Δ** symbol represents the difference between the value at the end and the beginning of the observation window for the **same StepExecution**.

Example:

| Time | readCount | writeCount | commitCount |
| --- | ---: | ---: | ---: |
| 10:00:00 | 2,000 | 1,900 | 10 |
| 10:00:20 | 6,000 | 5,700 | 30 |

Over 20 seconds:

~~~text
readThroughput  = (6,000 - 2,000) / 20 = 200 items/second
writeThroughput = (5,700 - 1,900) / 20 = 190 items/second
commitRate      = (30 - 10) / 20 = 1 commit/second
~~~

**Read throughput** indicates the rate of successful reads. **Write throughput** indicates the number of written items recorded by the framework. Differences may arise from filtering, skipping, or how the Step is configured. Do not conclude data loss merely because read throughput exceeds write throughput.

### 3.2. Chunk Throughput

If **C** chunks complete successfully in **Δt** seconds:

~~~text
chunkThroughput = C / Δt                   (chunks/second)
averageChunkRate = Δt / C                (seconds/chunk)
~~~

For example, 40 chunks completed in 20 seconds equals **2 chunks/second**.

Note that **chunk units differ from item units**. When one chunk contains 100 items while another contains only 20 items, each chunk contributes one unit to chunk throughput, even though the amount of work differs.

### 3.3. Per-Chunk Duration

For each completed chunk, measure its execution duration:

~~~text
chunkDuration = timeAfterChunk - timeBeforeChunk
~~~

After collecting many samples, examine:

- **p50:** median chunk duration.
- **p95:** the duration threshold that roughly 95% of chunks in the observed sample do not exceed.
- **p99:** identifies the slowest group of chunks.
- **max:** the slowest chunk recorded during the measurement interval.
- **count:** the number of chunk samples collected.

A Step with good average throughput but a sharp spike in p99 may be experiencing database locks, GC pauses, or erratic I/O latency.

### 3.4. End-to-End Throughput

If a Step completes **W** valid output items in **T** seconds from start to finish:

~~~text
endToEndWriteThroughput = W / T
~~~

Use **wall-clock** time, not total CPU time. This metric reflects the actual productivity experienced by users, including reading, processing, writing, committing, and runtime overhead.

In a multi-Step Job, you must define the scope: the duration of a single Step differs from the duration of the entire Job. For a Job with multiple Steps running in parallel, **summing individual Step durations** does not equal wall-clock elapsed time because Steps can overlap.

### 3.5. Comparing the Metrics

| Metric | Formula or Source | Best Used When |
| --- | --- | --- |
| **Read items/s** | ΔreadCount / Δt | Diagnosing data retrieval capacity |
| **Written items/s** | ΔwriteCount / Δt | Measuring Step write productivity |
| **Completed chunks/s** | Successful afterChunk count / Δt | Observing chunk completion cadence |
| **Commits/s** | ΔcommitCount / Δt | Observing transaction cadence |
| **Chunk duration** | afterChunk - beforeChunk | Finding slow chunks and p95/p99 latency |
| **End-to-end items/s** | Total output items / Job or Step wall-clock | Comparing benchmark runs |
| **Rollback count** | StepExecution.getRollbackCount() | Explaining throughput drops due to transaction failures |

Do not rely on a single metric to determine the optimal chunk size.

## 4. Fixed Per-Chunk Cost vs. Per-Item Cost

A simple model helps illustrate the trade-off:

~~~text
T_total ≈ N × t_item + ceil(N / K) × t_chunk_fixed
~~~

Where:

- **N:** number of input items.
- **K:** chunk size.
- **t_item:** average cost to read, process, and write one item.
- **t_chunk_fixed:** average fixed cost per chunk, such as starting a transaction, writing metadata, and committing.

According to this model, a **larger K** reduces how many times the fixed cost is paid. For example, with N = 1,000,000 and an assumed overhead of 10 ms per chunk:

~~~text
K = 100:
  ~10,000 chunks × 10 ms = ~100 seconds of fixed overhead

K = 500:
  ~2,000 chunks × 10 ms = ~20 seconds of fixed overhead

Model savings: about 80 seconds of overhead
~~~

However, this is only a **mental model**. Real-world execution time is non-linear because:

- Batch inserts/updates can become more efficient when the writer receives more items.
- Large chunks consume more memory and hold transactions open longer.
- Database locks may be held longer.
- On rollback/retry, a large chunk may have to redo much more work.
- Garbage collection pressure can increase as more objects stay alive longer.
- Query paging/cursors, caches, and network round-trips have their own performance characteristics.
- Read/write costs can shift once the database reaches a load threshold.

Therefore, do not choose K from the formula alone. **Measure on a representative workload**, compare multiple chunk sizes, and verify failure recovery behavior.

## 5. Measuring Actual Duration with ChunkListener

**ChunkListener** provides useful callbacks:

- **beforeChunk:** before starting to process a chunk within the Step's transaction scope.
- **afterChunk:** after the chunk completes successfully and the associated transaction finishes according to the Spring Batch lifecycle.
- **afterChunkError:** when the chunk encounters an error; this callback is useful for measuring and diagnosing failed attempts.

The code below uses **System.nanoTime()** to measure elapsed time. This monotonic clock is better suited for durations than **System.currentTimeMillis()**, which can shift due to system clock synchronization.

### 5.1. Listener Recording Timer and Counter with Micrometer

Spring Batch 5.x, Spring Boot 3.x, Micrometer example:

~~~java
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.stereotype.Component;

@Component
public class ChunkThroughputListener implements ChunkListener {

    private final MeterRegistry registry;

    // Each chunk-processing thread keeps its own timestamp.
    private final ThreadLocal<Long> startedAt = new ThreadLocal<>();

    public ChunkThroughputListener(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void beforeChunk(ChunkContext context) {
        startedAt.set(System.nanoTime());
    }

    @Override
    public void afterChunk(ChunkContext context) {
        record(context, "success");
    }

    @Override
    public void afterChunkError(ChunkContext context) {
        record(context, "error");
    }

    private void record(ChunkContext context, String outcome) {
        Long start = startedAt.get();
        startedAt.remove();

        if (start == null) {
            return;
        }

        StepExecution step =
                context.getStepContext().getStepExecution();

        String jobName = step.getJobExecution()
                .getJobInstance()
                .getJobName();

        long elapsedNanos = System.nanoTime() - start;

        Timer.builder("app.batch.chunk.duration")
                .description("Elapsed time of chunk attempts")
                .tags(
                        "job", jobName,
                        "step", step.getStepName(),
                        "outcome", outcome)
                .publishPercentileHistogram()
                .register(registry)
                .record(elapsedNanos, TimeUnit.NANOSECONDS);

        registry.counter(
                "app.batch.chunk.events",
                "job", jobName,
                "step", step.getStepName(),
                "outcome", outcome
        ).increment();
    }
}
~~~

Registering the listener:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, OrderOutput> processor,
        ItemWriter<OrderOutput> writer,
        ChunkThroughputListener throughputListener) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, OrderOutput>chunk(500, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .listener(throughputListener)
            .build();
}
~~~

Each successful callback records an **app.batch.chunk.duration** sample with **outcome=success**. An error callback records a sample with **outcome=error**. The **app.batch.chunk.events** counter tracks callback counts by outcome; for successful chunk throughput, filter on **outcome=success**.

Key points to understand about this listener:

1. **The Timer measures time around the chunk**, encompassing everything within the callback span. It is not an isolated timer for the reader, processor, or writer.
2. **Error samples measure the duration of a failed chunk attempt**, not a successfully committed data chunk.
3. **ThreadLocal** isolates timestamps across different chunk-processing threads under normal synchronous callback execution; call **remove()** to avoid retaining stale data when threads are reused.
4. In architectures where start and end callbacks do not run on the same thread, replace ThreadLocal with a correlation mechanism keyed by an appropriate **chunk attempt ID**. Do not assume this listener works unchanged for every remote orchestration topology.
5. If the process is killed mid-chunk, the completion callback may not execute, so the timing sample for that chunk may be missing.
6. **publishPercentileHistogram()** increases time-series count and metric memory usage. Enable histograms only for metrics where you actually need p95/p99.
7. Do not attach **jobExecutionId**, UUIDs, input filenames, or customer IDs as long-lived metric tags, as they cause cardinality to explode rapidly.

### 5.2. Why Not Measure Only ItemWriter Duration?

If the writer takes 30 ms while the reader + processor take 400 ms, measuring only the writer makes chunks appear very fast even though total duration is around 430 ms or more. **Chunk duration** pinpoints overall slowness. When deeper diagnosis is needed, add timers for the reader, processor, and writer to break down which component dominates execution time.

**ItemReadListener**, **ItemProcessListener**, and **ItemWriteListener** can help instrument individual phases. However, under retry or rollback, an item may be invoked multiple times. Phase metrics generally reflect **invocation counts and processing time**, which do not automatically equal the final number of committed items.

## 6. Measuring Items per Chunk

A chunk configured with size 500 does not necessarily write 500 items:

- The final chunk may have only 80 items remaining.
- The processor may filter out items by returning **null**.
- The Step may skip faulty items.
- Retries/rollbacks may alter actual processing attempts.
- The writer may update existing records rather than inserting new ones.

In a **single-threaded Step**, you can take the difference in **writeCount** before and after a chunk to estimate how many items the Step recorded as written in that chunk. However, you must understand the limitation of this approach: in a **multi-threaded** Step, concurrent chunks update the Step-wide count simultaneously, so the difference in the global count between two callbacks may include work from other threads.

Therefore:

- **Chunk duration** can be measured via per-chunk callbacks.
- **Written items/s** should be derived from **StepExecution.writeCount** snapshots over a time window, or from custom instrumentation designed with proper transaction/concurrency semantics.
- Do not assume that **current getWriteCount() - previous getWriteCount()** always equals the item count of a single chunk when parallel processing is active.
- Do not use the **number of ItemWriter.write(...) calls** as the written item count; each call receives a **Chunk** that can contain multiple items.

To calculate real business throughput, prefer **StepExecution writeCount over a consistent time window** and reconcile against the actual data at the destination. If the writer triggers side effects outside the transaction, also add acknowledgment or target-system outcome metrics.

## 7. Tracking Progress via StepExecution and JobExplorer

Spring Batch stores counts and status in **StepExecution**. For example:

~~~java
StepExecution step = ...;

long reads = step.getReadCount();
long writes = step.getWriteCount();
int commits = step.getCommitCount();
int rollbacks = step.getRollbackCount();
int filters = step.getFilterCount();
int skips = step.getSkipCount();
~~~

To monitor from another service, **JobExplorer** can query persisted JobExecution and StepExecution records:

~~~java
import java.util.List;

import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.stereotype.Service;

@Service
public class BatchThroughputQueryService {

    private final JobExplorer jobExplorer;

    public BatchThroughputQueryService(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public List<StepSnapshot> getSteps(long jobExecutionId) {
        JobExecution execution =
                jobExplorer.getJobExecution(jobExecutionId);

        if (execution == null) {
            throw new IllegalArgumentException(
                    "Unknown jobExecutionId=" + jobExecutionId);
        }

        return execution.getStepExecutions().stream()
                .map(step -> new StepSnapshot(
                        step.getId(),
                        step.getStepName(),
                        step.getStatus().name(),
                        step.getReadCount(),
                        step.getWriteCount(),
                        step.getCommitCount(),
                        step.getRollbackCount()))
                .toList();
    }

    public record StepSnapshot(
            Long stepExecutionId,
            String stepName,
            String status,
            long reads,
            long writes,
            int commits,
            int rollbacks) {}
}
~~~

A dashboard can poll every 15 or 30 seconds, retain the previous snapshot, and compute rates as **delta counts / delta time**.

Keep in mind:

- **JobExplorer returns the state persisted in JobRepository**. While a chunk has not yet committed, the snapshot may remain unchanged.
- A StepExecution object fetched in a previous query does not update automatically. The dashboard must re-query.
- Compute deltas only within the **same StepExecution ID**. If the Job restarts and creates a new StepExecution, do not subtract an old execution's count from the new count.
- Once a Job is **COMPLETED**, end-to-end throughput can be computed from total items and execution duration; at that point there is no uncommitted-chunk lag.
- If JobLauncher is asynchronous, **run(...)** returning does not mean the Job has finished; you must wait for a terminal status before computing total duration.

### SQL Against Metadata Tables

In a typical Spring Batch 5.x schema, you can query:

~~~sql
SELECT
    STEP_EXECUTION_ID,
    JOB_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    READ_COUNT,
    WRITE_COUNT,
    FILTER_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT,
    LAST_UPDATED
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = ?
ORDER BY STEP_EXECUTION_ID;
~~~

This information is useful for per-StepExecution snapshots. Use appropriate read-only permissions, target the correct JobRepository database, and never edit metadata to "adjust" throughput.

**LAST_UPDATED** marks when metadata was updated; it is not an accurate timer for individual chunk processing time. For p50/p95 duration distributions, use a ChunkListener timer.

## 8. Observing with Prometheus and Grafana

With Micrometer and a Prometheus registry, metric names are typically mapped from dots to underscores with unit suffixes appended. Assuming the success Counter from section 5 is exported as **app_batch_chunk_events_total** with label **outcome=success**:

### Completed Chunks per Second

~~~promql
sum by (job, step) (
  rate(app_batch_chunk_events_total{outcome="success"}[5m])
)
~~~

This expression represents the average number of **successful afterChunk events per second** over five minutes. By itself, it does not indicate how many items were in each chunk.

### Average Chunk Duration

Assuming Timer **app.batch.chunk.duration** is exported as **app_batch_chunk_duration_seconds_sum** and **app_batch_chunk_duration_seconds_count**:

~~~promql
sum by (job, step) (
  rate(app_batch_chunk_duration_seconds_sum{outcome="success"}[5m])
)
/
sum by (job, step) (
  rate(app_batch_chunk_duration_seconds_count{outcome="success"}[5m])
)
~~~

The resulting unit is **seconds/chunk**, since total duration is divided by the number of chunk events.

### p95 Duration

If histograms are enabled and the backend provides appropriate buckets:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, job, step) (
    rate(app_batch_chunk_duration_seconds_bucket{outcome="success"}[5m])
  )
)
~~~

The result helps detect tail latency. Exact series names may vary depending on registry configuration and version; inspect the actually exposed metrics endpoint before using these expressions.

### Recommended Panels

| Panel | Source | Purpose |
| --- | --- | --- |
| **Written items/s** | StepExecution writeCount delta or appropriate item metric | Output productivity |
| **Successful chunks/s** | ChunkListener Counter | Chunk completion cadence |
| **Chunk duration p50/p95/p99** | ChunkListener Timer histogram | Detecting tail latency and variance |
| **Read/write/filter/skip** | StepExecution or instrumentation | Explaining data flow through the pipeline |
| **Commit/rollback trend** | StepExecution | Detecting transaction errors and slow commits |
| **CPU, memory, GC** | JVM metrics | Identifying compute/memory limits |
| **JDBC pool, query latency, locks** | DataSource/database metrics | Identifying writer/reader bottlenecks |
| **Job completion time** | Job metadata | Measuring end-to-end performance |

Do not compare **chunk duration p95** in isolation between two Jobs with different chunk sizes and conclude which Job is faster. A larger chunk size normally increases single-chunk duration while potentially boosting **items/second** by reducing overhead. Look at both together.

## 9. How to Benchmark Chunk Size

To select a chunk size, use the same dataset, the same business logic, and a sufficiently stable measurement environment. An experiment might vary K across: **50, 200, 500, 2,000**.

Example **simulated** results with one million input items and no filtering/skipping:

| Chunk size | Total Step Duration | Output Throughput | Observation |
| ---: | ---: | ---: | --- |
| 50 | 240 seconds | ~4,167 items/second | Many transactions, high overhead |
| 200 | 155 seconds | ~6,452 items/second | Significant overhead reduction |
| 500 | 148 seconds | ~6,757 items/second | Highest speed in this experiment |
| 2,000 | 182 seconds | ~5,495 items/second | Large chunks; memory/lock/rollback cost can be high |

This is illustrative data to demonstrate comparison methodology, not default Spring Batch benchmark results. Chunk size **500** is only the best choice **in this hypothetical table**. With different data sources and databases, the optimal chunk size may be completely different.

### Repeatable Benchmark Procedure

1. **Fix the dataset:** item count, item size, filter/skip rate, processor complexity, value distribution, and output size must represent production.
2. **Select the environment:** identical database engine, hardware/CPU quota, connection pool, and JDBC writer configuration. Prevent background tasks from interfering with a benchmark run.
3. **Hold other variables constant:** vary only chunk size within an experiment set; keep the reader query, processor logic, writer, retry policy, and thread count unchanged.
4. **Warm up appropriately:** if JVM/JIT, caches, or connection pools have a significant effect, run warm-up executions before recording numbers. Document the warm-up procedure.
5. **Run multiple iterations:** capture median and percentiles of total Step duration; a single run can be skewed by GC, locks, or network jitter.
6. **Record comprehensive metrics:** wall time, output items/s, chunk duration p95, CPU, heap, GC pauses, JDBC latency, rollbacks, and error rates.
7. **Verify business results:** output matches expected counts and contents, with no lost or duplicate items.
8. **Test failure paths:** happy-path benchmarking is not enough; an overly large chunk can make recovery after rollback/restart very expensive.

Do not set overly tight timing thresholds for integration tests running on shared-resource CI runners. Separate correctness testing from **performance benchmarking** in a more controlled environment.

## 10. Causes of Low Chunk Throughput

### 10.1. Slow Reader

Symptoms: high reader latency, low processor CPU usage, writer mostly idle.

Root causes:

- Queries lacking appropriate indexes or inefficient SQL execution plans.
- Paging queries executing repeatedly with large offsets.
- High network latency when every read performs I/O.
- Input data requiring complex parsing or files stored on remote storage.
- Resource contention on cursor/paging readers.

Remediation:

- Inspect query plans and indexes.
- Choose the right reader among cursor, paging, file, or streaming readers.
- Tune fetch size / page size appropriately while preserving deterministic ordering to support restart.
- Minimize unnecessary round-trips and decouple heavy data transformations from the read path where appropriate.

**JDBC fetch size is not chunk size.** Fetch size hints to the driver how many rows to retrieve from the database per round-trip, whereas chunk size defines the item-processing transaction boundary in Spring Batch. Both parameters can be tuned independently.

### 10.2. Slow Processor

Symptoms: high CPU usage, processor dominates execution time; increasing chunk size yields little improvement in items/s.

Possible causes:

- CPU-intensive regex, mapping, validation, or calculations.
- Calling external APIs or querying the database per item.
- Allocating excessive objects/JSON, increasing garbage collection overhead.
- N + 1 queries when processing individual items.

Remediation:

- Profile CPU and memory allocations.
- Cache reference data appropriately with bounded memory.
- Batch queries or preload reference data when business rules allow.
- Avoid unnecessary side effects inside the processor.
- Consider multi-threading or partitioning only after ensuring the reader/processor/writer coordinate safely and output is idempotent.

If the processor accounts for 95% of per-item duration, increasing chunk size alone rarely makes a meaningful difference because transaction overhead is only a small fraction.

### 10.3. Slow Writer

Symptoms: chunk duration increases mainly in the writer, high database CPU/locks, or saturated network throughput.

Causes:

- Writing item-by-item with many SQL round-trips.
- Missing JDBC batching or driver configuration that does not enable batch optimization.
- Inserts/updates requiring expensive index updates or constraint checks.
- Database lock contention or multiple transactions competing on the same table.
- Writer calling a high-latency remote API.
- File writer flushing or syncing to disk too frequently.

Remediation:

- Use **JdbcBatchItemWriter** or an appropriate batch writing mechanism to reduce round-trips.
- Check indexes, execution plans, lock waits, and transaction duration.
- Separate data loading from transformation steps if architecture permits.
- For API writers, consider batch endpoints and concurrency limits.
- Design for idempotency/retry so faster writes do not compromise consistency.

Do not increase chunk size indefinitely to compensate for a writer performing slow individual operations. Identify the true source of latency.

### 10.4. Slow Commit or Checkpoint

Symptoms: reader, processor, and writer are all relatively fast, yet chunk duration remains high; database log/transaction commit or metadata updates consume significant time.

Possible causes:

- fsync or transaction log overhead.
- Long-held database locks.
- JobRepository hosted on a slow or overloaded database.
- ExecutionContext storing excessive data that must be serialized.
- Multiple listeners running queries on every chunk.

Remediation:

- Measure writer duration separately from total chunk duration to isolate remaining overhead.
- Keep **ExecutionContext** lean, storing only the state required for restart.
- Inspect database infrastructure, transaction logs, locks, and connection counts.
- Test a larger chunk size in a controlled benchmark.
- Avoid placing heavy logic inside synchronous listeners.

## 11. Side Effects of Setting Chunk Size Too Large

Increasing chunk size typically reduces transaction count for the same data volume, but incurs several costs:

| Risk | Why Larger Chunks Increase Risk |
| --- | --- |
| **Memory pressure** | More input/output objects reside in the chunk simultaneously |
| **GC pause** | Higher allocation volume and longer-lived objects |
| **Lock contention** | Transactions hold locks for longer intervals |
| **Rollback cost** | More uncommitted items in the chunk may need reprocessing |
| **Restart granularity** | Coarser checkpoints; after a crash, more work may be repeated |
| **Slow chunk p99** | A single slow item can stall the entire transaction |
| **Large SQL batch** | Drivers or databases impose limits on statement/batch size |
| **Timeout** | Transactions or APIs may exceed allowed timeouts |

Example:

~~~text
Chunk size = 100
  Commit after each small group.
  Crash after 9,950 items -> at most about one uncheckpointed chunk.

Chunk size = 10,000
  Commit less frequently.
  Crash after 9,950 items -> may have to reprocess most of the first chunk.
~~~

This example only illustrates checkpointing in a sequential execution; the actual number of items reprocessed depends on ItemStream, reader, transaction behavior, and crash location. For writers issuing out-of-band side effects outside the transaction, reprocessing can also cause duplicate deliveries without idempotency.

An appropriate chunk size balances **throughput**, **latency**, **memory**, **rollback duration**, and **restart safety**.

## 12. Multi-Threaded Steps, Partitioning, and Throughput

### 12.1. Multi-Threaded Step

When a Step executes multiple chunks concurrently, end-to-end throughput can increase if the bottleneck is relieved by parallelism. However:

- **The sum of chunk durations** can exceed wall-clock time because multiple chunks overlap.
- **writeCount/readCount** on StepExecution are Step-wide counts; do not subtract counts across two callbacks to infer the exact item count of a single concurrent chunk.
- Reader, writer, and processor must be concurrency-safe; many stateful ItemReaders are not inherently thread-safe.
- Commit order and output order may differ from input order.
- Each thread may require a database connection; an undersized pool becomes a bottleneck.

For example, four chunks running concurrently, each taking one second:

~~~text
Thread 1: [ chunk A 1s ]
Thread 2: [ chunk B 1s ]
Thread 3: [ chunk C 1s ]
Thread 4: [ chunk D 1s ]

Total chunk durations: 4 seconds
Wall-clock elapsed  : about 1 second (excluding overhead)
~~~

Do not compute **chunk throughput = 4 / total durations 4s = 1 chunk/s** here. Actual wall-clock throughput is roughly **4 chunks/s**, while average per-chunk duration remains near 1 second.

### 12.2. Partitioned Step

With partitioning, multiple **worker StepExecutions** process distinct data partitions. You can measure:

- Overall Job throughput as valid output divided by wall-clock time.
- Per-partition throughput to spot slow workers.
- Per-partition p95 chunk duration.
- Item count skew across partitions.

Avoid **double counting**: the manager StepExecution may hold aggregated counts rolled up by an aggregator. Do not sum both manager and worker counts if the manager already aggregates worker metrics.

### 12.3. Remote Chunking

When reader, processor, and writer run in separate processes, throughput depends on the message broker, network, serialization, acknowledgments, and worker count. **Manager-side chunk duration** may include waiting on remote workers; add queue latency and worker processing metrics to pinpoint bottlenecks.

Do not assume adding more workers guarantees linear throughput scaling. The target database, connection pool, or network bandwidth can become the next bottleneck.

## 13. Retry, Rollback, and Interpreting Throughput

A "happy path" benchmark with clean data usually achieves higher speed than production workloads. When a Step is configured with **faultTolerant()**, transient errors can trigger rollbacks and retries.

Example:

~~~text
Chunk 1: 500 items -> commit
Chunk 2: 500 items -> writer error -> rollback
Chunk 2: retry -> commit
Chunk 3: 500 items -> commit
~~~

The failed attempt on chunk 2 still consumes CPU, I/O, and time, yet produces zero additional successful business items. Measuring only **read attempts or writer invocations** can inflate apparent throughput. **Wall-clock output throughput** and **final destination records** reflect real results more accurately.

Distinguish clearly between:

- **Attempt throughput:** number of processing/write attempts made, including retries.
- **Successful chunk throughput:** number of chunks completed successfully.
- **Committed output throughput:** number of items recorded as successfully written according to Step semantics over wall-clock time.
- **Business throughput:** number of unique records/orders persisted at the destination system over wall-clock time.

When retries spike, successful chunks/s can drop sharply while attempt counts rise. Monitor **rollbackCount**, skip counts, and exceptions to explain why.

## 14. How Restarts Affect Measurement

A JobInstance that fails and then restarts has multiple JobExecutions and StepExecutions:

~~~text
JobInstance importOrdersJob(businessDate=2026-11-15)
  |
  +-- JobExecution #1: FAILED
  |     StepExecution #10
  |       writeCount = 8,000
  |
  +-- JobExecution #2: COMPLETED
        StepExecution #11
          writeCount = 4,000
~~~

This is an illustrative example. When calculating throughput:

- **For the initial run**, use the counts and duration of StepExecution #10.
- **For the restart run**, use the counts and duration of StepExecution #11.
- **For end-to-end business-cycle throughput**, decide whether downtime waiting for restart is included; you often need both active processing time and total elapsed time until final data completeness.
- **Final item counts** should be verified against destination data or business keys; never treat commitCount as item count.

Never compute a delta between writeCount of StepExecution #10 and #11 as though they belonged to a single continuous counter.

A chunk reprocessed after rollback can consume extra CPU and I/O without increasing the final output count. That is why you should monitor **successful throughput**, **retry/rollback overhead**, and **checkpoint behavior** together.

## 15. Testing Throughput Measurements

Testing serves two distinct goals:

1. **Correctness tests:** verify that the Step reads/writes the expected items, statuses, and counters; independent of CI CPU speed.
2. **Performance benchmarks:** measure duration and throughput in a stable environment across repeated runs to compare versions/configurations.

### 15.1. Correctness Integration Test

Example using **spring-batch-test**, **JUnit 5**, and **AssertJ**:

~~~java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class ImportOrdersThroughputTest {

    @Autowired
    private JobLauncherTestUtils testUtils;

    @Test
    void shouldProcessAllItemsAndRecordCommits() throws Exception {
        // The test fixture contains exactly 1,000 valid items.
        JobParameters parameters = new JobParametersBuilder()
                .addString("caseId", UUID.randomUUID().toString(), true)
                .toJobParameters();

        long startNanos = System.nanoTime();
        JobExecution jobExecution =
                testUtils.launchStep("importOrdersStep", parameters);
        double elapsedSeconds =
                (System.nanoTime() - startNanos) / 1_000_000_000.0;

        StepExecution step = jobExecution.getStepExecutions().stream()
                .filter(s -> "importOrdersStep".equals(s.getStepName()))
                .findFirst()
                .orElseThrow();

        assertThat(jobExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
        assertThat(step.getReadCount()).isEqualTo(1_000);
        assertThat(step.getWriteCount()).isEqualTo(1_000);
        assertThat(step.getRollbackCount()).isZero();

        // Example only prints the metric for observation; do not set pass/fail
        // based on a throughput threshold that fluctuates across CI machines.
        double throughput = step.getWriteCount() / elapsedSeconds;
        System.out.printf("write throughput = %.1f item/s%n", throughput);
    }
}
~~~

This assumes a **synchronous JobLauncher** and an isolated test fixture not modified by other tests. If the launcher is asynchronous, wait for Job completion before capturing elapsed time.

Test data should produce deterministic output; beyond read/write counts, tests should verify the target table/file by business key, especially when the writer causes side effects outside the transaction.

### 15.2. Benchmarking Multiple Chunk Sizes

Do not modify the production-deployed Step directly just to benchmark. You can inject **chunk size** via dedicated benchmark configuration when building the Step, or define Steps corresponding to fixed K values in a test environment.

A result recording table should capture:

~~~text
datasetVersion, chunkSize, threads, readCount, writeCount,
durationSeconds, itemsPerSecond, chunkP95Ms,
rollbackCount, peakHeapMb, gcPauseMs, dbLockWaitMs
~~~

When comparing runs, keep the dataset version and related settings constant. Run multiple iterations to obtain reliable median/p95 numbers. On shared CI machines, treat performance numbers as informational only—do not hardcode assertions such as "must exceed 20,000 items/s" on uncontrolled infrastructure.

### 15.3. Testing the Timing Listener

You can unit-test **ChunkThroughputListener** with a test MeterRegistry and a mocked ChunkContext containing a StepExecution. The goal of a unit test is to prove that the listener emits Timers/Counters with the expected names and tags, not to verify exact physical CPU speed.

Do not sleep for a fixed duration and assert an exact millisecond value. Runtime, scheduler, and CI jitter can make such assertions flaky. For throughput calculation logic over snapshots, extract a pure function accepting **deltaCount** and **elapsedSeconds** so you can test the formula with deterministic inputs.

## 16. Common Throughput Measurement Mistakes

| Mistake | Why It Is Wrong | How to Fix It |
| --- | --- | --- |
| Using **chunk size × commitCount** as exact written items | Commits can involve EOF, filtering, skipping, or special Steps | Use writeCount and actual target output |
| Using **sum of chunk durations** as wall-clock time in parallel runs | Chunks overlap across threads | Measure real wall-clock time from start to end |
| Viewing throughput over a 1-second window only | Large chunks update metrics in bursts | Use a wider window and compare p50/p95 |
| Measuring only the writer | Ignores reader, processor, and commit overhead | Measure whole-chunk duration and instrument each phase |
| Putting UUID/jobExecutionId into metric tags | Cardinality grows unboundedly with every run | Tag only job, step, and low-cardinality outcomes |
| Setting speed pass/fail thresholds on shared CI | CPU, database, and network vary | Benchmark in a stable environment |
| Comparing different datasets | Small/large/complex items have different costs | Fix the fixture and dataset version |
| Assuming rollback/retry does not affect speed | Reprocessing still consumes resources | Track attempts, rollbacks, and output |
| Increasing chunk size indefinitely | Memory, transaction duration, and retry cost grow | Measure multiple K values and check limits |
| Watching items/s while ignoring correctness | Can write fast while dropping or duplicating data | Assert final business outcomes |
| Mixing restart executions | Counts get confused across StepExecutions | Use the exact ID or aggregate intentionally |
| Summing manager and worker partitions | Counts get double-aggregated | Pick the single authoritative metric source |

## 17. Practical Workflow for Optimizing Chunk Throughput

You can apply an iterative cycle as follows:

**Step 1 — Set the target.** For example, process 10 million items before 06:00 while keeping error rate and memory below thresholds. Clarify whether input throughput or output throughput is the primary KPI.

**Step 2 — Establish a baseline.** Record elapsed time, read/write items/s, chunk duration p50/p95, commits/rollbacks, CPU, heap, GC, database latency, and target counts.

**Step 3 — Identify the bottleneck.** If the writer dominates duration, optimize SQL batching or the database; if the processor dominates, profile CPU; if commit overhead is high, test a controlled increase in chunk size.

**Step 4 — Change one variable.** Sweep a range of chunk sizes instead of changing K, reader, writer, and thread count all at once.

**Step 5 — Measure multiple runs.** Record median and tail latency. A single run can be skewed by warm-up, caches, or GC.

**Step 6 — Evaluate trade-offs.** The new chunk size must deliver better throughput without excessively increasing rollback cost, memory, lock time, or restart correctness risks.

**Step 7 — Verify failure paths.** Inject a controlled mid-chunk failure and verify that rollback and restart produce accurate output with no missing or duplicate items.

**Step 8 — Monitor post-deployment.** Save the baseline, build dashboards, and alert if throughput drops, chunk p95 spikes, or rollbacks increase abnormally.

### Example Step Monitoring Report

~~~text
Job: importOrdersJob                  Status: STARTED
Step: importOrdersStep                Chunk size: 500
JobExecution: 1824                    StepExecution: 2941

Read count                120,000
Write count               117,000
Filter count                3,000
Commit count                  240
Rollback count                  0

Read throughput            3,000 items/s
Write throughput           2,925 items/s
Successful chunks/sec      6.0 chunks/s
Chunk duration p50         145 ms
Chunk duration p95         230 ms
Heap usage                 52%
Database lock waits        low
~~~

The values above are illustrative examples; chunk duration and chunks/s can be affected by parallelism and measurement methodology. Always specify the rate time window alongside the measurement source.

**Chunk-oriented throughput** is most meaningful when viewed as a combination of **item output**, **chunk completion cadence**, **chunk duration**, **transaction cost**, and **result correctness**. The best chunk size is the value that enables your Job to meet its throughput and SLA targets while preserving rollback safety, restartability, and stable operation on real data.

