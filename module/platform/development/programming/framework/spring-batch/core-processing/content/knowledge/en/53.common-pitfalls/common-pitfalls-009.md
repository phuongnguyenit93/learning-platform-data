# Chunk Too Small Causing Low Throughput in Spring Batch

## 1. Symptom: The Job Processes Correctly, Yet Runs Too Slowly

Suppose a Spring Batch job needs to move one million order records from a staging table to a target table. The reader fetches items, the processor normalizes data, and the writer writes to the database. The job finishes successfully with no exceptions, and CPU is not always high, yet total runtime drags on for hours.

Inspecting the configuration reveals:

```java
. <Order, ProcessedOrder>chunk(1, transactionManager)
```

In valid Java syntax, the generic type argument must attach directly to the dot:

```java
.<Order, ProcessedOrder>chunk(1, transactionManager)
```

With a **chunk size of 1**, each item typically drives the framework through nearly the full chunk lifecycle: read, process, write, state update, and transaction commit. When the job processes millions of items, transaction overhead, database round-trips, flushes, and framework infrastructure repeat millions of times.

However, **small chunks are not always wrong**. For very heavy records, writers calling external services, strict low-latency-per-item requirements, or minimal rollback scopes, chunk sizes of 1–10 can fit. The pitfall is choosing a value far too small **relative to the workload and fixed per-transaction cost**, dragging throughput down unnecessarily.

This lesson aims to identify the root cause, measure costs accurately, and choose an appropriate **commit interval** without blindly sacrificing stability, memory, or restartability.

## 2. How Does Chunk-Oriented Processing Work?

Spring Batch distinguishes *tasklet-oriented steps* from *chunk-oriented steps*. In a chunk-oriented step, the framework typically reads items until a chunk completes per the `completion policy`/commit interval, then processes/writes and commits inside the corresponding transaction.

```text
                Chunk-oriented step
                         |
           Begin transaction / chunk
                         |
                    ItemReader
                         |
                    ItemProcessor
                         |
             Collect items for a chunk
                         |
                    ItemWriter
                         |
              ItemStream.update(...)
                         |
             Commit transaction/chunk
                         |
                    Next chunk
```

This is a conceptual diagram. Actual callback order, listeners, retries, skips, buffering, and metadata updates depend on step configuration. Do not assume every `read()` call immediately opens and closes a separate transaction when chunk size exceeds 1.

Example of a step with `chunk(100, transactionManager)`:

```text
Chunk 1: items 1 ... 100    -> write -> commit
Chunk 2: items 101 ... 200  -> write -> commit
Chunk 3: items 201 ... 300  -> write -> commit
...
```

With the same 1,000 items and no retries/skips:

| Chunk size | Approximate chunks containing data | Meaning |
|---|---:|---|
| 1 | 1,000 | Many tiny transactions. |
| 10 | 100 | Significantly fewer commits. |
| 100 | 10 | Writer can handle a larger batch. |
| 500 | 2 | Fewer commits, though each transaction is larger. |
| 1,000 | 1 | One very large chunk for this dataset. |

The number of data-bearing chunks is mathematically approximated as `ceil(totalItems / chunkSize)`. However, **`StepExecution.getCommitCount()` does not necessarily equal that exact formula**: the trailing chunk, end-of-stream detection, rollbacks/retries, and framework mechanics can add extra commits or alter statistics. Use actual counts and traces to evaluate rather than hardcoding that estimate as an assertion for every reader.

## 3. Why Do Tiny Chunks Drag Throughput Down?

### 3.1. Transaction Overhead Repeats Too Frequently

Each chunk can incur fixed work:

1. Starting or joining a transaction managed by `PlatformTransactionManager`.
2. Acquiring a connection from the pool or preparing the transaction context.
3. Executing the writer, flushing, JDBC batching, or running SQL.
4. Updating `ExecutionContext` and step metadata per the Batch lifecycle.
5. Committing the transaction; the database may write transaction logs and sync durability per configuration.
6. Invoking listeners, updating metrics, and releasing related resources.

When chunk size is 1, this overhead can repeat **on every single item**. When chunk size is 500, part of that cost is amortized across 500 items. Not all costs shrink equally: per-item processor CPU still runs, and SQL statements still process all data.

### 3.2. Writer Cannot Leverage Batch I/O

`JdbcBatchItemWriter` or writers supporting multi-item writes can group SQL statements into a single JDBC batch execution per `Chunk`. If each chunk holds only one item, statement batching is severely constrained. Depending on driver/database and implementation, larger chunks can cut round-trips, improve network efficiency, and boost throughput.

**Increasing chunk size does not automatically optimize SQL.** If a custom writer loops and makes a separate HTTP call per item, total requests stay identical. If a writer opens a fresh connection per item, the real bottleneck is the writer implementation. Distinguish:

- Chunk transaction: group of items committed under one transaction boundary.
- JDBC batch: group of statements sent to the database via `PreparedStatement.addBatch/executeBatch` or an equivalent abstraction.
- Bulk SQL: a single statement updating/inserting many rows using database syntax.
- Reader fetch/page size: rows fetched from the source in a single round-trip.

They are related, yet **not a single parameter**.

### 3.3. Higher Framework and Metadata Overhead

Frequent commits mean frequent `StepExecution` status updates, checkpoints, transaction boundaries, and listener callbacks. This cost becomes especially noticeable when `JobRepository` sits on a separate database with appreciable network latency or uses a constrained transaction manager/connection pool.

Still, do not conclude that seeing many `Executing step` log lines automatically means commit interval is to blame: that may just be step-level logging while the bottleneck lies in SQL or a remote API. Measure at every layer.

### 3.4. Overly Verbose Logs and Metrics Slow Things Down Too

If `ChunkListener.afterChunk(...)` logs at `INFO` on every chunk, chunk size 1 scales log volume with item count. One million items means roughly one million chunk-level listener calls and potentially one million progress log lines. With synchronous appenders or slow stdout/log collectors, logging overhead worsens the slowdown.

Log summaries in `StepExecutionListener`, emit sparse milestone progress logs, and use metrics for latency/throughput. Avoid enabling `DEBUG`/`TRACE` on JDBC or Spring Batch during benchmarks unless investigating a targeted issue.

## 4. Simple Throughput Estimation Model

We can use an approximate model to understand costs:

\[
T(N,C) \approx N \cdot t_{item}
  + \left\lceil\frac{N}{C}\right\rceil \cdot t_{fixed}
  + T_{other}
\]

Where:

- `N`: total items to process.
- `C`: chunk size or commit interval.
- `t_item`: average cost to read/process/write one item excluding fixed per-chunk overhead.
- `t_fixed`: fixed cost of one chunk (transaction, commit, callbacks, round-trip, etc.) under measured conditions.
- `T_other`: startup, connection setup, reader preparation, I/O, and unmodeled costs.

Hypothetical example with **1,000,000 items**, assuming in a specific environment each chunk has 3 ms fixed overhead and per-item cost stays constant:

| Chunk size | Approximate data chunks | Estimated fixed overhead |
|---|---:|---:|
| 1 | 1,000,000 | 3,000 seconds (50 minutes) |
| 10 | 100,000 | 300 seconds (5 minutes) |
| 100 | 10,000 | 30 seconds |
| 500 | 2,000 | 6 seconds |
| 1,000 | 1,000 | 3 seconds |

This is a **mathematical illustration**, not a general benchmark for Spring Batch. Fixed cost does not always remain constant as chunk size grows: longer transactions, larger SQL batches, memory pressure, lock contention, or DB log flushes can shift both `t_fixed` and `t_item`. The model also omits concurrency, retries, and heterogeneous data effects.

Throughput can be measured as:

\[
\text{Throughput} = \frac{\text{items confirmed per target definition}}{\text{actual elapsed runtime (seconds)}}
\]

When using Spring Batch counters, clearly define numerator and denominator: items `read`, items `written`, committed rows, or completed business records. Processors can filter items, writers can bulk-update, and retries can reprocess. **Do not grab an arbitrary counter and label it "records per second" if its semantics do not match.**

## 5. Signs of an Undersized Chunk

Common signals when commit interval is the main culprit:

| Signal | Interpretation to verify |
|---|---|
| Tiny chunk size (1, 5, 10) on a large dataset | Likely high per-transaction overhead. |
| Huge `commitCount` relative to actual work | Many tiny transactions; inspect end-of-stream/retries. |
| High share of time in commits/JDBC round-trips | Larger batch size can cut commit trips. |
| Heavy DB transaction log/fsync activity | Frequent commits may be driving load. |
| Low processor CPU yet low throughput | Likely waiting on DB/network/transactions, not slow Java code. |
| Writer runs `executeBatch()` with batch size 1 | Not utilizing JDBC batching benefits. |
| Per-chunk logs dominate log output | Logging overhead multiplies by chunk count. |
| Raising size 10→100 helps sharply, 500→1,000 does not | Suggests approaching the optimal plateau; measure further. |

Signals that are **insufficient on their own**:

- Job is slow with chunk size already at 500: could be unindexed queries, external APIs, locks, or GC.
- CPU at 100%: processor may be heavy and commit interval is not the bottleneck.
- High `readCount`: only reflects items read per Batch semantics, not where time is spent.
- Many DB connections: does not prove small chunks; could be partitioning, multiple jobs, or connection leaks.

## 6. Configuring Chunk Size in Spring Batch 5.x

The examples below use **Java 17+, Spring Boot 3.x, Spring Batch 5.x** and corresponding builder APIs. Spring Batch 6.x reorganizes some packages/APIs; consult reference docs matching your project dependencies.

### 6.1. Step with Fixed Commit Interval

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class ImportOrdersStepConfiguration {

    @Bean
    Step importOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<Order> orderReader,
            ItemProcessor<Order, ProcessedOrder> orderProcessor,
            ItemWriter<ProcessedOrder> orderWriter) {

        return new StepBuilder("importOrdersStep", jobRepository)
                .<Order, ProcessedOrder>chunk(500, transactionManager)
                .reader(orderReader)
                .processor(orderProcessor)
                .writer(orderWriter)
                .build();
    }
}
```

`Order`, `ProcessedOrder`, and the reader/processor/writer beans are application domain classes, not auto-generated by Spring Batch. In Spring Batch 5.x, `.chunk(500, transactionManager)` sets a commit interval of 500 for a step with the corresponding transaction manager.

Do not bump a production job to 500 solely because of this example. It is an **initial candidate value** that must be benchmarked against real workloads and databases.

### 6.2. Externalizing Chunk Size to Configuration

In `application.yml`:

```yaml
app:
  batch:
    import-orders:
      chunk-size: 500
```

In step configuration:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, ProcessedOrder> orderProcessor,
        ItemWriter<ProcessedOrder> orderWriter,
        @Value("${app.batch.import-orders.chunk-size:500}") int chunkSize) {

    if (chunkSize <= 0) {
        throw new IllegalArgumentException("chunkSize must be positive");
    }

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, ProcessedOrder>chunk(chunkSize, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

Add `import org.springframework.beans.factory.annotation.Value` along with the imports from the previous example. The key `app.batch.import-orders.chunk-size` is an **application-defined property**, not a built-in Spring Batch property. Externalizing configuration makes it easy to test values across profiles, though you should record the value used by each execution for reproducible benchmarks and change tracking.

For applications requiring different chunk sizes per job execution, you can use step-scoped configuration or a controlled completion policy; however, do not alter a completion policy arbitrarily mid-run of an active `StepExecution`. On restart, understand how changes affect checkpoints, memory, and processing time.

### 6.3. Chunk Size Is Not Page Size, Fetch Size, or Grid Size

```text
chunkSize              = items grouped into one transaction/chunk
JdbcCursor.fetchSize   = hint for rows the JDBC driver fetches per round-trip
JdbcPaging.pageSize    = query page size in a paging reader
partition grid size    = how data is split across workers/partitions
thread pool size       = number of parallel threads
```

For example, a `JdbcPagingItemReader` with `pageSize=1,000` and a step with `chunkSize=250`: one fetched page can feed multiple chunks. This is valid when reader, sort key, and transactions are designed properly. Changing one parameter does not automatically adjust the others.

## 7. JDBC Writers: Large Chunks Help Only When Using Batch I/O

If a writer must write millions of rows to a database, an implementation supporting JDBC batching is usually a good starting point. Spring Batch provides `JdbcBatchItemWriter` to group a `Chunk` of items into JDBC batch operations.

Example with an application record:

```java
import java.math.BigDecimal;

public record ProcessedOrder(long id, BigDecimal amount) {
}
```

And writer:

```java
import javax.sql.DataSource;

import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.context.annotation.Bean;

@Bean
JdbcBatchItemWriter<ProcessedOrder> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<ProcessedOrder>()
            .dataSource(dataSource)
            .sql("""
                INSERT INTO imported_order (id, amount)
                VALUES (:id, :amount)
                """)
            .itemSqlParameterSourceProvider(item ->
                    new MapSqlParameterSource()
                            .addValue("id", item.id())
                            .addValue("amount", item.amount()))
            .build();
}
```

Why use `itemSqlParameterSourceProvider`: `ProcessedOrder` is a Java record with `id()`/`amount()` accessors, so we map SQL parameters explicitly without relying on JavaBeans getter names. With your target JDBC driver/database, observe **actual batch sizes and execution times**, because the framework calling JDBC batching does not guarantee the database turns every command into a single network round-trip.

Example DDL for testing:

```sql
CREATE TABLE imported_order (
    id BIGINT PRIMARY KEY,
    amount DECIMAL(14, 2) NOT NULL
);
```

When comparing `chunkSize=10` vs. `chunkSize=500`, hold reader, writer, indexes, database server, concurrency, and input dataset constant. If you add JDBC batching, new indexes, or a larger connection pool at the same time, you cannot attribute the improvement to commit interval alone.

### 7.1. When the Writer Still Calls an API Per Item

A writer that loops over `Chunk` and makes an HTTP call for every item:

```java
@Override
public void write(Chunk<? extends ProcessedOrder> chunk) {
    for (ProcessedOrder item : chunk) {
        externalApi.sendOrder(item);
    }
}
```

This snippet illustrates **a writer bounded by request count**; `externalApi` is an application dependency. Raising chunk size will not cut HTTP requests if one call still fires per item. Moreover, HTTP calls do not automatically roll back when the database transaction rolls back. For such writers, examine API-supported batching, timeouts, rate limits, idempotency, and outbox options. Do not raise chunk size endlessly expecting the API to speed up on its own.

## 8. Measuring Throughput and Transaction Overhead Properly

### 8.1. Capture a Baseline Before Changing Anything

Before tuning, record at minimum:

| Metric | How to use |
|---|---|
| Total elapsed time of job and each step | Identify which step needs optimization. |
| `readCount`, `writeCount`, `filterCount`, `skipCount` | Verify work volume and before/after counts. |
| `commitCount`, `rollbackCount` | Observe transaction/chunk counts and errors/retries. |
| Throughput in items/s or committed rows/s | Compare configurations with matching semantics. |
| JVM CPU/heap/GC | Detect CPU-bound processors or memory pressure. |
| Connection pool metrics | Check connection wait times and saturation. |
| SQL query latency/batch execution time | Assess whether DB/driver is the bottleneck. |
| Database locks/log I/O/wait events | Identify commit and transaction contention. |
| Log volume and listener latency | Quantify observability overhead. |

Spring Batch exposes `StepExecution` for reading post-run statistics. Once you have `JobExecution`, you can summarize:

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;

for (StepExecution step : jobExecution.getStepExecutions()) {
    System.out.printf(
            "step=%s read=%d written=%d commits=%d rollbacks=%d status=%s%n",
            step.getStepName(),
            step.getReadCount(),
            step.getWriteCount(),
            step.getCommitCount(),
            step.getRollbackCount(),
            step.getStatus());
}
```

Print this summary **only after reaching a terminal status** and when code has metadata access. If `JobLauncher` runs asynchronously, the returned `JobExecution` may still be running; wait for a terminal status or re-read via `JobExplorer`.

### 8.2. Measuring Bounded Per-Chunk Duration

With Spring Batch 5.x, `ChunkListener` lets you observe callbacks around chunks. A rough measurement in test environments records start time via `System.nanoTime()` and computes elapsed time when `afterChunk` or `afterChunkError` runs.

```java
import java.util.concurrent.atomic.LongAdder;

import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.scope.context.ChunkContext;

public final class ChunkTimingListener implements ChunkListener {

    private static final String START_KEY = "chunkStartNanos";

    private final LongAdder successfulChunkCount = new LongAdder();
    private final LongAdder totalSuccessfulNanos = new LongAdder();

    @Override
    public void beforeChunk(ChunkContext context) {
        context.setAttribute(START_KEY, System.nanoTime());
    }

    @Override
    public void afterChunk(ChunkContext context) {
        Object started = context.getAttribute(START_KEY);
        if (started instanceof Long startNanos) {
            long elapsed = System.nanoTime() - startNanos;
            successfulChunkCount.increment();
            totalSuccessfulNanos.add(elapsed);
        }
    }

    public long getSuccessfulChunkCount() {
        return successfulChunkCount.sum();
    }

    public long getTotalSuccessfulNanos() {
        return totalSuccessfulNanos.sum();
    }
}
```

This is **illustrative instrumentation**: counters belong to the listener instance; if a singleton bean is shared across multiple steps/jobs, measurements are combined. In production, separate metrics by step name or execution scope using Micrometer/Observation and avoid unbounded state storage. `ChunkContext` holds chunk-callback attributes; storing/reading keys this way serves normal execution paths, not durable checkpointing.

Time measured from `beforeChunk` to `afterChunk` spans multiple parts of the chunk lifecycle, **not database commit time alone**. To quantify commit cost, use dedicated instrumentation/DB metrics or transaction-manager tracing. If raising chunk size increases chunk duration, throughput has not necessarily dropped: each chunk simply carries more items.

### 8.3. Use Micrometer/Actuator Instead of Logging Every Chunk

Spring Batch supports Micrometer metrics covering job, step, item read/process, and chunk write durations. When a Spring Boot app has Actuator and a registry configured, you can compare sizes via latency dashboards without emitting millions of `INFO` lines.

Keep metric tags bounded (`jobName`, `stepName`, status, etc.). **Do not put `orderId`, `jobExecutionId`, or arbitrary file paths on every metric tag**, because high cardinality can overload the metrics backend. Execution IDs belong in logs/traces when investigating an individual run.

## 9. Benchmarking Chunk Size Under a Controlled Plan

A structured test workflow beats jumping straight from 1 to 10,000:

1. Pick a representative input set: large enough, with realistic valid/filtered ratios, record sizes, and data distribution near production.
2. Hold database engine, schema/indexes, JVM memory, CPU quota, connection pool, reader/writer, and concurrency fixed.
3. Run a warm-up if JIT, connection pools, or caches matter noticeably; exclude warm-up results from primary numbers.
4. Test sensible sizes such as `10`, `50`, `100`, `250`, `500`, `1,000` instead of only two distant extremes.
5. Run multiple trials per size, resetting data/metadata properly and alternating test order to minimize bias from caches or background load.
6. Measure elapsed time, throughput, p95/p99 chunk duration, heap/GC, commit counts, rollbacks, DB waits, and errors.
7. Pick a **stable performance plateau** rather than merely the single fastest lucky trial.
8. Re-verify under near-production load with concurrency and dirty data before changing deployment configuration.

Example **hypothetical** results table—not actual benchmark numbers:

| Chunk size | Throughput (items/s) | Relative throughput | Observation |
|---|---:|---:|---|
| 1 | 230 | 1.0× | Heavy commit overhead. |
| 10 | 1,500 | 6.5× | Rapid improvement. |
| 100 | 4,700 | 20.4× | Writer begins utilizing batching. |
| 250 | 5,100 | 22.2× | Near saturation point. |
| 500 | 5,250 | 22.8× | Slight gain, larger transactions. |
| 1,000 | 5,200 | 22.6× | No extra benefit, higher heap usage. |

In this hypothetical dataset, `250` or `500` are good candidates for further testing. Do not assume `500` is always best: `250` may prove steadier under data errors or concurrent jobs.

### 9.1. Do Not Benchmark on Fewer Items Than the Chunk Size

If a test has 50 items and chunk size is 500, everything runs in a single chunk. You fail to measure multi-commit effects, GC interactions, or DB transaction logs. Use a dataset large enough to span **many chunks** at every tested size and run long enough to dampen measurement noise.

### 9.2. Do Not Benchmark with Per-Item DEBUG Logging Enabled

When one run emits per-item logs and another does not, results reflect logger/appender costs rather than commit overhead. Keep logging levels consistent, enable extra logs/timing only while pinpointing bottlenecks, and re-measure in a near-production configuration.

## 10. Trade-Offs When Increasing Chunk Size

### 10.1. RAM and Size of a Single Chunk

Spring Batch may retain a batch of input/output items in memory during processing. With large items, `chunkSize=5,000` can trigger memory pressure, frequent GC, or `OutOfMemoryError`. Actual object footprints are usually much larger than raw file/row byte sizes due to object headers, strings, collections, buffers, and intermediate representations.

**Simple illustrative estimate:** if live objects per chunk item average ~10 KiB, a 1,000-item chunk can need at least ~10 MiB for those payloads alone, **excluding** reader buffers, output objects, retry state, connection pools, JVM overhead, and other threads. This is not an exact allocation formula; measure real heap usage.

### 10.2. Long Transactions, Locks, and Contention

Larger chunks mean longer transactions. The database may hold row locks longer, forcing other jobs/services to wait and raising deadlock or timeout probability. In systems with multiple writers contending on the same table, overall throughput can degrade even if one isolated job runs faster in a test environment.

Measure lock waits, deadlocks, transaction durations, and latencies of co-located services sharing the database—not just items/s of a single step.

### 10.3. Costlier Rollbacks and Retries

When a 1,000-item chunk rolls back near the end, reading/processing/writing for many items may have to re-run. With chunk size 10, the replay scope is far smaller. Fault-tolerant steps may retry/skip per configuration, so actual processor/writer calls and external effects do not scale simply by multiplying by chunk size.

Writers calling external services without idempotency are especially hazardous: HTTP requests that already succeeded **do not roll back** with the database transaction. Never raise chunk size substantially without understanding transaction boundaries and duplicate side effects.

### 10.4. Sparser Checkpoints and Restart

`ItemStream` can update checkpoints in `ExecutionContext` per transaction/chunk. Larger chunks widen the gap between commit marks. If the process is killed mid-chunk, uncommitted work may need reprocessing on restart, and non-transactional side effects must be guarded.

**Increasing chunk size must not break reader/writer restartability.** Keep inputs immutable, stabilize sort keys when paging, and apply `saveState`/stream registration properly per the implementation.

### 10.5. Per-Item Latency

For overnight batch imports, aggregate throughput usually matters more than individual items appearing immediately in the target table. However, if downstream requires data within a few seconds, large chunks delay visibility until commit. Consider **end-to-end latency** SLAs alongside throughput.

### 10.6. Writer Batch Limits

Database drivers, APIs, or target systems may cap parameters/batch rows, request sizes, transaction logs, or payload lengths. For example, a bulk API may accept at most 200 records per request. In that case, raising chunk size to 1,000 does not allow sending a single 1,000-record request; the writer may have to split it. Design chunk size and remote batch size separately, with rollback/retry controls.

## 11. Tuning Reader, Processor, and Writer Together

Chunk size is only **one tuning knob** in the pipeline. Once transaction overhead drops, the next bottleneck may shift to another component.

### 11.1. JDBC Cursor Readers

`JdbcCursorItemReader` reads rows from a JDBC cursor. `fetchSize` lets the driver optimize how many rows it fetches per round-trip. It is a **JDBC driver hint**, not a guarantee of identical row batching per network trip across all databases.

```java
JdbcCursorItemReader<Order> reader = new JdbcCursorItemReader<>();
reader.setDataSource(dataSource);
reader.setSql("SELECT id, amount FROM staging_order ORDER BY id");
reader.setFetchSize(500);
reader.setRowMapper(orderRowMapper);
reader.setName("stagingOrderCursor");
reader.setSaveState(true);
```

This is an illustrative setup assuming `dataSource` and `orderRowMapper` already exist. Tune `fetchSize` for your driver. In some DBs, autocommit or connection settings also affect cursor streaming.

### 11.2. Paging Readers

`JdbcPagingItemReader` uses `pageSize` and sort keys to paginate. Sort keys must be **unique and deterministic** to avoid missed/duplicated rows across pages, especially if source rows can update. A page size of 1,000 does not require chunk size to also equal 1,000.

### 11.3. CPU-Bound Processors

If the processor performs heavy math, XML parsing, or encryption, per-item CPU time may dominate. Then increasing chunk size removes only a small fraction of transaction overhead. Profile CPU to spot hot methods, allocations, and serialization; optimize algorithms or apply controlled concurrency if readers/writers are thread-safe.

### 11.4. Writers and Indexes/SQL

Check:

- Does the writer use JDBC batching, or still `executeUpdate` per item?
- Are indexes present for reader queries and required target constraints?
- Are heavy triggers, foreign key checks, or unique checks becoming bottlenecks?
- Does the driver actually batch efficiently? Some databases support driver options to rewrite batches.
- Is anything opening a separate connection/transaction per item even though the step already manages transactions?
- Is the database contending with other services or starved of I/O?

Do not strip constraints/indexes that protect correctness just to make benchmarks look prettier. To optimize bulk loads, design a controlled staging/load/merge workflow and measure both correctness and speed.

## 12. Chunk Size, Concurrency, and Partitioning

Increasing `chunkSize` and increasing workers/threads are **two distinct optimizations**:

| Technique | Primary effect | Risks |
|---|---|---|
| Increase chunk size | Cuts transaction/commit count; increases work per chunk | Heap, lock duration, rollback/restart scope. |
| Multi-threaded step | Processes multiple chunks concurrently | Non-thread-safe reader/writer, connection contention, ordering. |
| Partitioning | Splits dataset into independent processing partitions | Overlapping/missing partitions, result aggregation, state management. |
| Remote chunking | Distributes processing/writing over messaging | Network, delivery semantics, duplicates, multi-component ops. |

Under parallel execution, active connections and transactions multiply. If chunk size is also large, lock contention and memory can surge rapidly. Never raise `chunkSize`, `gridSize`, and thread pools simultaneously and guess what caused a gain or regression.

A measurable approach is optimizing chunk size on a single worker at fixed concurrency first, then varying concurrency in a separate benchmark pass while checking consistency, DB health, and restartability.

## 13. Impact of Skip, Retry, and Fault Tolerance

Small chunks add transactions, yet oversized chunks can become costly when data contains errors.

Suppose 100,000 items have 1% legitimately skippable errors. Depending on failure points and `.faultTolerant().skip(...)`, the framework may have to roll back and retry, or split/locate failing items. You cannot use `ceil(100000 / chunkSize)` as actual commit count when retries/skips occur.

Things to measure separately:

| Situation | Why it affects tuning |
|---|---|
| High `skipCount` | Rework and repeated listener callbacks can make large chunks expensive. |
| High `rollbackCount` | Reprocessing and DB contention wipe out commit-reduction gains. |
| Long retry backoffs | Bottleneck is waiting on transient faults, not commit interval. |
| Processor with side effects | Retries can re-invoke processor; requires idempotent design. |
| Non-transactional writer | Rollbacks do not undo already-succeeded HTTP/file calls. |

With error-prone datasets, benchmark at least two sets: a clean set and a set reflecting realistic error rates. A size that looks fast on spotless data can become unstable under random errors or deadlocks.

### 13.1. Skip Limit Is Not a Throughput Knob

Raising `skipLimit` merely to stop a job from failing while testing large chunks can mask severe data errors. Similarly, slashing retries/backoffs for speed can increase real failures and hammer external services. Tuning commit interval must never alter the business rules for accepting or rejecting records.

## 14. Testing and Verifying Correctness When Changing Chunk Size

Changing the commit interval must still preserve business outcomes and restartability.

### 14.1. Integration Test with Identical Input

With Spring Boot 3.x and Spring Batch 5.x, use `@SpringBatchTest`, `@SpringBootTest`, `@ActiveProfiles("test")`, `JobLauncherTestUtils`, and a test-dedicated JDBC `JobRepository`.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

@SpringBatchTest
@SpringBootTest(properties = "app.batch.import-orders.chunk-size=100")
@ActiveProfiles("test")
class ImportOrdersChunkIntegrationTest {

    @Autowired
    JobLauncherTestUtils launcherTestUtils;

    @Autowired
    JobRepositoryTestUtils repositoryTestUtils;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Autowired
    @Qualifier("importOrdersJob")
    Job importOrdersJob;

    @BeforeEach
    void setUp() {
        repositoryTestUtils.removeJobExecutions();
        launcherTestUtils.setJob(importOrdersJob);
        jdbcTemplate.update("DELETE FROM imported_order");
        // Load fixed staging_order fixture here, e.g., via @Sql.
    }

    @Test
    void completesAndWritesExpectedRows() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("inputId", "chunk-benchmark-fixture-1")
                .toJobParameters();

        JobExecution execution = launcherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        Integer actual = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM imported_order", Integer.class);
        assertEquals(1000, actual);
    }
}
```

This is an **illustrative integration test skeleton**: it assumes the application defines an `importOrdersJob` bean, Batch configuration, test tables, a 1,000-record fixture, and the proper transaction manager. `@SpringBootTest` does not auto-generate these domain components. When implementing, load fixtures explicitly via `@Sql` or a test-data factory; `@BeforeEach` cleanup is suitable only on an isolated test database, never a shared environment.

`JobRepositoryTestUtils.removeJobExecutions()` wipes metadata in the repository it points to; never call it while another test runs concurrently on the same repository. Set `spring.batch.job.enabled=false` in the test profile so jobs do not auto-run at context startup.

### 14.2. Comparing Multiple Sizes via Dedicated Tests/Benchmarks

To measure `10`, `100`, `500`, each value can use a matching profile/test context or a benchmark harness building the step at the target size. Ensure:

- Identical input/expected output.
- Target data reset before each trial.
- Fresh metadata/distinct `JobParameters` to avoid `JobInstanceAlreadyCompleteException`.
- Stable warm-up and trial runs—never benchmark on a test with just a handful of items.
- Do not wrap the whole job-launching test in `@Transactional` expecting all step commits to roll back with the test method.
- Verify data, status, and counts before trusting throughput figures.

### 14.3. Testing Rollback and Restart at Larger Chunk Sizes

An essential test: intentionally inject a failure mid-chunk, keep `JobRepository`/`ExecutionContext` intact, then re-run with the exact same **identifying JobParameters**. Verify:

1. Chunks committed before the error are not double-written.
2. The rolled-back chunk replays safely.
3. Input/output streams restore checkpoints accurately.
4. No non-transactional side effects execute twice improperly.
5. The job ultimately reaches the right status and data reconciles.

If changing chunk size breaks a restart test, never drop the test just to keep high throughput; diagnose the reader/writer or transaction design.

## 15. Misleading Optimization Assumptions

### 15.1. "Bigger Is Always Faster"

False, because overhead savings plateau while heap, lock duration, rollback cost, and commit wait times rise. When moving from `500` to `1,000` barely helps or lowers throughput, evaluate the optimal plateau rather than scaling exponentially.

### 15.2. "Larger Chunk Size Means Fewer SQL Statements"

Not necessarily. A writer may still issue one SQL statement per item. JDBC batching can cut round-trips, yet database execution still depends on driver and SQL. Measure actual batch execution and network traffic.

### 15.3. "Just Increase the Connection Pool"

If a job runs a single sequential step using one connection per transaction, growing the pool from 10 to 100 will not run multiple chunks in parallel. Pool sizing must reflect real concurrency and total workload, not substitute for commit-interval tuning.

### 15.4. "Fewer Commits Always Cut Database Time"

Fewer commits save commit overhead, yet larger transactions can make DB buffer/log activity and locking costlier. If the bottleneck is an unindexed query or lock wait, changing commit interval may yield little gain.

### 15.5. "Fast Reading Means a Fast Job"

A reader can read 100,000 items/s while the writer writes only 500 items/s due to API rate limits. Increasing reader fetch size or chunk size will not remove writer constraints. Profile time per stage.

### 15.6. "Higher Throughput Means the Change Is Right"

A job may run faster while committing wrong totals, failing crash recovery, skipping bad items, or increasing locks that slow other systems down. Selection criteria include **correctness, throughput, stability, and operational fit**, not a single number.

## 16. Troubleshooting Reference Table

| Symptom | Possible cause | Direction to take |
|---|---|---|
| Huge `commitCount`, chunk size = 1 | Every item runs in its own transaction | Try sizes 50/100/500 and measure DB/throughput. |
| High `writeCount` yet low throughput | Too many writer round-trips or DB waits | Check `JdbcBatchItemWriter`, SQL, and driver batching. |
| Chunk size 500 yet writer still sends 1 HTTP request/item | No bulk API or writer does not batch | Design batched requests/outbox/idempotency separately. |
| Raising 100→1,000 gives no speedup | Hit plateau or bottleneck lies elsewhere | Profile processor, SQL, network, and locks. |
| Large chunks grow heap and lengthen GC | Large item/intermediate state in memory | Shrink size, cut allocations, monitor heap/GC. |
| Large chunks cause deadlocks or timeouts | Transactions hold locks longer | Shrink size, optimize update order/indexes, measure contention. |
| Job fails and restart reprocesses many items | Commit/checkpoint points too sparse | Pick a balanced size; keep reader/writer restartable. |
| Flood of `afterChunk` log lines | Listener logs progress on every chunk | Log by milestones or use Micrometer. |
| `readCount` differs from `writeCount` | Processor filters or skips | Inspect `filterCount`, skip counts, and business rules. |
| 50-item benchmark at chunk size 1,000 looks super fast | Too few chunks; dataset too small | Use a large dataset, multiple trials, and warm-up. |
| Outcomes change when retry/skip enabled | Rollback/reprocessing alters work | Test representative dirty data; measure rollback/skip/retry. |
| Multiple partitions run slower than one worker | DB/network saturation and lock contention | Tune concurrency; avoid raising all knobs at once. |
| Changing size has no effect | Step ignored property, cached bean, or writer bottleneck | Verify active config loaded and measure the right stage. |
| Job hits `JobInstanceAlreadyCompleteException` on re-benchmark | Reusing same identifying params on old repository | Use isolated test repo/reset metadata or valid new instances. |

## 17. Practical Optimization Workflow for a Large Job

When receiving a report that "the job runs slowly because chunk size is too small", a sound runbook follows:

1. **Confirm scope:** which job/step is slow, how many items, which environment, and what is the SLA?
2. **Inspect configuration:** actual chunk size, transaction manager, reader fetch/page size, writer implementation, and retry/skip policies.
3. **Capture baseline:** elapsed time, throughput, commit/rollback counts, memory/GC, and DB waits.
4. **Pinpoint primary bottleneck:** transaction overhead, network/SQL, reader, processor CPU, or external service.
5. **Step up sizes gradually:** test sensible milestones, hold other variables constant, and reset test data.
6. **Measure on representative real data:** include large items, dirty data, retries/skips, and near-production concurrency.
7. **Verify correctness:** output counts, values, constraints, transactions, idempotency, and restart.
8. **Pick the balanced plateau:** strong throughput without overly long transactions, keeping heap/DB locks bounded.
9. **Roll out under control:** record chosen chunk size, timestamp/version, and config rollback plan.
10. **Monitor post-rollout:** job duration, p95/p99, error rates, locks/GC, queue backlog, and impact on co-located workloads.

### Exercise 1 — Overhead Model

Assume `N=2,000,000`, fixed cost 4 ms per chunk, and constant item cost. Compute estimated fixed overhead for chunk sizes 1, 20, 200, and 1,000. Explain why this calculation cannot replace benchmarking when larger sizes lengthen transactions.

### Exercise 2 — Measuring Commit Interval

Create a chunk-oriented step reading 100,000 records from a staging table and writing to a target table via `JdbcBatchItemWriter`. Test sizes 10, 100, 500, and 1,000 on identical input. Record `readCount`, `writeCount`, `commitCount`, elapsed time, heap, and DB round-trips. Explain which size hits the best throughput plateau on your test machine and why.

### Exercise 3 — Injecting Mid-Chunk Failure

With chunk size 500, inject a write failure near the end of the third chunk, then restart using the exact same identifying parameters. Inspect committed results and replayed data. Compare how many items must be reprocessed against chunk size 50, without bypassing idempotency requirements.

### Exercise 4 — Spotting a False Bottleneck

Create two writers: writer A uses JDBC batching, writer B makes one HTTP call per item. Raise chunk size from 10 to 500. Observe how dramatically the gains can differ; design a measurement plan so you do not mistake an API/network bottleneck for chunk tuning.

### Exercise 5 — Tuning Under Parallel Execution

Run two independent partitions writing concurrently to one database table; inspect contention while varying chunk size and worker counts. Measure system-wide throughput and lock waits, not just one partition's runtime. Recommend safe bounds for concurrency and commit interval.

## 18. Key Principles to Remember

- **An undersized chunk size** repeats transaction/commit, metadata, and writer I/O overhead far too often on large jobs.
- **Increasing chunk size can improve throughput**, especially when the writer supports JDBC batching or bulk I/O; actual gains depend on the workload.
- **Chunk size is not fetch size, page size, SQL batch size, or concurrency.** Measure the actual bottleneck component.
- **There is no single optimal number** for every Spring Batch job. Benchmark on representative datasets and databases.
- **Never optimize by sacrificing restartability and correctness.** Longer transactions raise rollback/retry costs, memory usage, and lock durations.
- **Watch the whole picture:** CPU, GC, DB waits, commit counts, throughput, and business outcomes—never conclude from a single log line.
- **Choose a stable operating plateau**, easy to run and re-test, rather than simply picking the largest size.

## 19. References

- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): reading, processing, writing by chunk, and commit intervals.
- [Spring Batch Reference — Configuring a Step](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/commit-interval.html): configuring step commit intervals.
- [Spring Batch Reference — JDBC Batch Item Writer](https://docs.spring.io/spring-batch/reference/readers-and-writers/database.html): database readers/writers and JDBC batching.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): checkpoints, start limits, and `allowStartIfComplete`.
- [Spring Batch Reference — Fault Tolerance](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html): skip/retry policies and impact on chunk transactions.
- [Spring Batch Reference — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): job, step, item, and chunk metrics/timings.
- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction boundaries and propagation.

