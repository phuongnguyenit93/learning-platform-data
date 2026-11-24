# Optimizing Spring Batch Without Breaking Restarts

A batch job that runs fine on 10,000 test records does not necessarily scale cleanly to millions of real-world records. Common speedup levers include increasing chunk size, reading larger pages, batching writes, adding threads, or partitioning. Yet if optimization focuses solely on records per second, you can accidentally break **restartability**: after a job fails, data gets skipped, duplicated, or re-read from the very beginning.

In **Spring Batch Core Processing**, **Performance – Optimizing Without Breaking Restarts** requires satisfying two goals at once:

1. **Increase performance:** cut total runtime, database round-trips, I/O wait times, memory usage, and transaction overhead.
2. **Preserve recoverability:** when a job fails or is stopped, restarting the same `JobInstance` must resume from its saved state without corrupting already-committed data or skipping unprocessed work.

Key principle: *an optimization succeeds only if both the happy path **and** the post-failure recovery path produce accurate business results*. Finishing faster alone is never enough to prove an optimization is safe.

## 1. Understand Restart Mechanics Before Optimizing

Spring Batch tracks state via `JobRepository`. Key entities to distinguish:

| Component | Purpose | Relationship to Restart |
| --- | --- | --- |
| `JobInstance` | A logical job run identified by job name + identifying `JobParameters` | A restart must target the same instance, not spawn a new one unintentionally |
| `JobExecution` | A single execution attempt of an instance | The initial failed run and the restart run have distinct executions |
| `StepExecution` | A single execution of a step, holding status, counters, and context | A failed step can receive a new execution upon job restart |
| `ExecutionContext` | State map persisted by the framework to the repository | Readers/writers can store position state for recovery |
| `ItemStream` | `open`, `update`, and `close` contract | `open` restores state, `update` prepares checkpoints, `close` frees resources |
| Chunk transaction | Commit/rollback boundary for a group of items | Determines which work was committed before failure |

Example with chunk size 200:

```text
Read/write 1..200       → commit #1; checkpoint after item 200
Read/write 201..400     → commit #2; checkpoint after item 400
Read/write 401..600     → error before commit #3
                                      |
                                      v
                         rollback uncommitted work
                                      |
                                      v
Restart: open reader using durable checkpoint after item 400
         (when the reader supports saving/restoring properly)
```

Items 401..600 may have been read and passed through the processor, but if the transaction did not commit, they are not complete. Upon restart, those items may be read again. That is normal under checkpointed processing; external side effects outside the transaction must enforce idempotency or separate reconciliation.

**Never treat `readCount`, `writeCount`, or the last log line as the default restart position.** Recovery position is governed by what the reader/writer implementation stores in `ExecutionContext`. Some readers are stateless, or track a key/last sort key rather than an item index.

### `JobParameters` Are Part of the Recovery Contract

For a batch job processing by business date:

```java
JobParameters params = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16")
    .addString("sourceVersion", "file-v12")
    .toJobParameters();
```

Both parameters above are *identifying* by default. With the same job name and identifying parameters, Spring Batch resolves the same `JobInstance`. When the prior execution is `FAILED`/`STOPPED` and configuration permits, Spring Batch restarts that instance using its persisted metadata.

Conversely:

```java
JobParameters differentInstance = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16")
    .addString("sourceVersion", "file-v12")
    .addString("attemptId", UUID.randomUUID().toString())
    .toJobParameters();
```

Adding a new identifying `attemptId` creates a **different `JobInstance`**. That may be intentional for rerunning from scratch, yet it is **not a checkpointed restart**. Never tack on `RunIdIncrementer` or a UUID merely to bypass `JobInstanceAlreadyCompleteException` and assume Batch will pick up where it left off.

## 2. Measure Performance and Define Correctness

Before optimizing, identify where time is actually spent. A batch job slowed by a missing SQL index will barely benefit from adding threads; one slowed by overly frequent commits may gain significantly from tuning chunk size.

Collect metrics by **job execution, step, and data cycle**:

| Metric Group | Indicators | Interpretation |
| --- | --- | --- |
| Overall performance | Duration, records/second, output throughput | Actual processing speed |
| Chunk / transaction | `commitCount`, `rollbackCount`, chunk duration, items/chunk | Commit overhead and failure rework risk |
| Reader | Query latency, query counts, DB fetches, file read time | Data retrieval bottlenecks |
| Processor | CPU, allocations, GC pauses, per-item processing time | Computation cost |
| Writer | Rows per batch, round-trips, lock waits, flush time | Write and transaction costs |
| Infrastructure | CPU, heap, connection pool, disk I/O, network | Resource ceilings |
| Recovery | Restart duration, reprocessed item count, duplicates/gaps | Cost of failure after optimization |

`StepExecution.getReadCount()` and `getWriteCount()` are **per-execution** counters, not necessarily total unique business records across restarts. When reconciling after a restart, rely on business keys and committed destination outputs.

Example comparison between baseline and optimized runs on **the same input dataset**:

| Metric | Baseline (Example) | Optimized (Example) |
| --- | ---: | ---: |
| Input | 1,000,000 | 1,000,000 |
| Chunk size | 50 | 500 |
| Approx. commits for full data | 20,000 | 2,000 |
| Runtime | 28 minutes | 13 minutes |
| Final valid outputs | 999,200 | 999,200 |
| Result after mid-run failure & restart | Correct, zero duplicates | Must be verified by testing |

These are **hypothetical numbers illustrating comparison**, not Spring Batch benchmarks or guarantees. Actual commit counts depend on step setup, transactions, end-of-stream checks, retries, and skips. The goal is cutting runtime while keeping final output accurate after deliberate failure injection.

## 3. Tuning Chunk Size While Preserving Checkpoints

A chunk-oriented step reads, processes, and writes a group of items and then commits the transaction. Spring Batch 5.x setup:

```java
@Bean
Step importOrdersStep(JobRepository repository,
                      PlatformTransactionManager transactionManager,
                      ItemReader<OrderRow> reader,
                      ItemProcessor<OrderRow, OrderResult> processor,
                      ItemWriter<OrderResult> writer) {
    return new StepBuilder("importOrdersStep", repository)
        .<OrderRow, OrderResult>chunk(250, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
}
```

`OrderRow` and `OrderResult` are illustrative application types, not Spring Batch classes. `chunk(250, transactionManager)` sets a 250-item commit interval under the standard chunk model.

### Chunks Too Small

- Many transactions and commits, plus frequent metadata/checkpoint updates.
- More database round-trips if the writer cannot batch enough items.
- Can still be appropriate when items consume heavy memory, transactions are slow, or tiny rollback windows are required.

### Chunks Too Large

- Long-lived transactions, raising lock waits, undo/WAL pressure, and memory usage.
- On a late-chunk error, large amounts of uncommitted work must be redone.
- Some writers buffer many items, inflating heap and slowing GC.
- Reduced visibility into committed progress when a single chunk takes very long.

### Safe Tuning Workflow

1. Measure a baseline with fixed inputs and reconciled outputs.
2. Sweep sizes such as 100, 250, and 500 on representative data instead of assuming "bigger is always faster."
3. Compare throughput, transaction duration, memory, lock waits, and rollback counts.
4. Inject a failure after several committed chunks; restart **the same instance** and verify zero gaps or duplicates.
5. Adopt the new setting only when both performance and recovery behavior meet requirements.

Changing chunk size alters commit boundaries for **new** runs. For an in-progress restart, changing chunk size, reader code, and context schema simultaneously complicates checkpoint interpretation; test upgrade/restart paths against realistic metadata snapshots before production rollout. Never change multiple factors at once if you want to isolate the cause of any discrepancy.

## 4. Optimizing Readers Without Dropping or Duplicating Records

The reader is often the hardest piece of restartability because it connects "how far we read" with "whether the dataset is still the same." A checkpoint is safe only when item ordering and identity remain stable.

### 4.1. Paging Requires Deterministic Sort Keys

When using `JdbcPagingItemReader`, **the sort key must be stable and uniquely distinguish rows**. Sorting solely by a non-unique field like `created_at` lets rows with identical timestamps shift positions across pages or restarts.

```sql
-- Non-deterministic ordering for rows sharing created_at:
SELECT id, created_at, amount
FROM orders_source
WHERE business_date = :businessDate
ORDER BY created_at;

-- Unique id key enforces deterministic ordering:
SELECT id, created_at, amount
FROM orders_source
WHERE business_date = :businessDate
ORDER BY id;
```

At scale, add indexes matching the filter and sort key—for instance, `(business_date, id)` on the source table depending on database and query plans. `JdbcPagingItemReader` tracks the last sort key value to support restarts; this **does not permit arbitrary source mutations**. If rows can be inserted, deleted, or have sort keys modified, establish a clear data contract for whether new items belong to the current cycle.

### 4.2. Restart-Capable Paging Reader Example

Spring Batch 5.x example on PostgreSQL with source table `orders_source(id BIGINT PRIMARY KEY, business_date VARCHAR(10), amount NUMERIC)`:

```java
import java.math.BigDecimal;
import java.util.Map;
import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcPagingItemReader;
import org.springframework.batch.item.database.Order;
import org.springframework.batch.item.database.builder.JdbcPagingItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

record OrderRow(long id, BigDecimal amount) {}

@Bean
@StepScope
JdbcPagingItemReader<OrderRow> ordersReader(
        DataSource dataSource,
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    return new JdbcPagingItemReaderBuilder<OrderRow>()
        .name("ordersReader")
        .dataSource(dataSource)
        .selectClause("SELECT id, amount")
        .fromClause("FROM orders_source")
        .whereClause("WHERE business_date = :businessDate")
        .parameterValues(Map.of("businessDate", businessDate))
        .sortKeys(Map.of("id", Order.ASCENDING))
        .rowMapper((rs, rowNum) -> new OrderRow(
            rs.getLong("id"), rs.getBigDecimal("amount")))
        .pageSize(250)
        .fetchSize(250)
        .saveState(true)
        .build();
}
```

`@StepScope` instantiates a fresh reader per step execution, avoiding reusing a prior run's cursor on a singleton. `name("ordersReader")` namespaces state keys; when multiple readers share an execution context, each needs a distinct name so they never overwrite each other's state. `saveState(true)` enables checkpointing; do not disable it merely to trim metadata updates.

`pageSize(250)` sets the reader's page size, whereas `fetchSize(250)` only hints row fetch size to the JDBC driver. Actual effect depends on driver and database. `pageSize` and `chunk size` need not match, though choosing them together should be validated on representative data.

This example assumes **the input is a stable business snapshot** throughout the job and any restarts. One way to enforce stability is passing `sourceVersion`/`snapshotId` in `JobParameters` and querying only that version. For dynamic sources, consider staging/snapshots or a fixed watermark instead of calling `now()` repeatedly inside the reader.

### 4.3. Cursor Readers and Fetch Size

`JdbcCursorItemReader` streams a result set instead of issuing paging queries. Tuning `fetchSize`, indexes, and SQL can sharply reduce I/O. However, cursors can hold database connections open long-term, and fetch behavior depends on driver and transaction settings. Upon restart, the reader reopens the query and repositions via saved state; source mutations between runs remain a hazard.

Never treat `fetchSize` as a commit boundary or checkpoint mechanism. It is a JDBC retrieval setting, independent of `chunk()` and `ExecutionContext`.

### 4.4. Avoid Offsets on Mutating Datasets

Paginated APIs like `?page=5&size=100` or SQL `OFFSET 500` break easily when items on earlier pages are inserted or deleted mid-job. If the source exposes cursor/token pagination or a monotonically increasing key over a stable snapshot, use that instead. When building a custom `ItemStreamReader`, save the token or last committed key **at proper checkpoint boundaries**, not just when logging the last seen key.

## 5. Optimizing Writers: Batch Writes and Idempotency

Writing one JDBC statement per item multiplies round-trips. Within a single transaction, `JdbcBatchItemWriter` groups statements per chunk and normally lowers database call overhead. Yet faster writes alone are not enough: the writer must behave deterministically when items are retried.

### 5.1. JDBC Batch Writer Example with Business-Key Upsert

Assume a PostgreSQL target table:

```sql
CREATE TABLE order_result (
    order_id BIGINT PRIMARY KEY,
    amount NUMERIC NOT NULL
);
```

Sample writer:

```java
import java.math.BigDecimal;
import javax.sql.DataSource;

import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;

record OrderResult(long orderId, BigDecimal amount) {}

@Bean
JdbcBatchItemWriter<OrderResult> resultWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<OrderResult>()
        .dataSource(dataSource)
        .sql("""
            INSERT INTO order_result(order_id, amount)
            VALUES (?, ?)
            ON CONFLICT (order_id)
            DO UPDATE SET amount = EXCLUDED.amount
            """)
        .itemPreparedStatementSetter((item, statement) -> {
            statement.setLong(1, item.orderId());
            statement.setBigDecimal(2, item.amount());
        })
        .build();
}
```

`ON CONFLICT` is **PostgreSQL syntax**, not portable standard SQL. On Oracle, MySQL, or SQL Server, use the appropriate merge/upsert syntax and evaluate locking, indexing, and concurrency. The unique key on `order_id` enforces a single business record per order: if an item is reprocessed, the writer will not duplicate output rows.

**Upserts do not solve every consistency problem.** If calculations depend on wall time or mutated source rows, overwriting the same key with a different `amount` can still be wrong. Make processors deterministic for a given input/version, or tag outputs with `sourceVersion` and clear update policies. If business rules require retaining calculation history, use versioned keys and explicit version activation.

### 5.2. Writer Optimization Pitfalls

| Optimization | Expected Benefit | Restart Risk to Address |
| --- | --- | --- |
| JDBC batching instead of per-item inserts | Fewer round-trips | Mid-batch failures, transactions, and idempotency |
| Combining many items into one large file | Fewer open/close operations | Restoring file position; avoiding corrupted appends on restart |
| Calling an external API directly | Removes intermediate staging | API does not roll back with DB; requires idempotency keys |
| Async writing behind the writer | Hides network latency | Step may commit before writes finish if unawaited/uncoordinated |
| Dedicated bulk loaders | Very high throughput | Needs checkpoints/correlation between Batch and loader state |
| Dropping unique constraints to write faster | Cuts index/check overhead | Loses duplicate protection during retries/restarts |

With `JpaItemWriter`, batching/flushing and persistence context retention affect memory. When adjusting flush/clear behavior for throughput, preserve transaction integrity and avoid retaining entities across chunks—never let ORM buffers grow unboundedly across the job.

## 6. Optimizing File Outputs While Preserving Recovery

`FlatFileItemWriter` and file-based writers can store state in `ExecutionContext` to support restarts. When tuning buffering or altering file writing strategies, understand options like `saveState`, appending, overwriting, and restart detection.

```text
Initial run:
  input.csv → processing → result.csv (new)
  chunk #1/#2 commit; writer saves valid state
  chunk #3 fails

Restart same JobInstance:
  reader reads from saved checkpoint
  writer reopens result.csv and restores state

Rerun as a new JobInstance:
  must use a new output policy, controlled replacement,
  or versioning to avoid overwriting published results
```

Do not enable `appendAllowed(true)` merely to skip file initialization overhead: if a new `JobInstance` appends onto a previous run's file, outputs duplicate even while status reports `COMPLETED`. Conversely, unconditionally deleting the target file at the start of **every** run destroys committed data from a prior execution upon restart.

A safe workflow for critical output files is writing to a temporary path keyed by **business key + execution/version**, validating results, and only publishing/renaming to the final path after verification. If restarting directly into an in-progress staging file, keep the staging filename and state consistent for that `JobInstance`. On object storage or cross-filesystem targets, renames may not be atomic—use manifests and proper publish markers.

Test mid-chunk failures, pre-existing files, writer flush/close behavior, and restarts on the same file. `BatchStatus.COMPLETED` alone does not prove a file has no duplicate lines or truncated tails.

## 7. Do Not Disable `saveState` in Exchange for Speed

A dangerous "optimization" is setting `.saveState(false)` on readers/writers to skip persisting `ExecutionContext`. This may trim minor metadata overhead while forcing readers to restart from record 1 whenever a step restarts.

```java
// If the reader needs to restore its position:
reader.setSaveState(true);

// Choose false only when there is a reprocess-from-start contract or complete partitioning
// that needs no prior position and final outputs remain protected.
```

Not every processor or reader needs state: pure-function processors rarely touch `ExecutionContext`, and a reader generating a tiny immutable list for an idempotent re-runnable step may need no checkpoint. Yet choosing statelessness **must stem from your restart model**, never from blindly stripping "overhead" without data.

### Implementing the `ItemStream` Lifecycle Properly

For a custom reader:

```java
public final class KeysetOrderReader implements ItemStreamReader<OrderRow> {
    private static final String LAST_KEY = "orders.reader.lastCommittedId";
    private Long nextAfterId;

    @Override
    public void open(ExecutionContext context) {
        nextAfterId = context.containsKey(LAST_KEY)
            ? context.getLong(LAST_KEY)
            : null;
        // Prepare query: id > nextAfterId, ORDER BY id.
    }

    @Override
    public OrderRow read() {
        // Read the next row ordered by id; return null at EOF.
        // In a real implementation, invoke JDBC/resources here.
        throw new UnsupportedOperationException("Illustrative skeleton");
    }

    @Override
    public void update(ExecutionContext context) {
        if (nextAfterId != null) {
            context.putLong(LAST_KEY, nextAfterId);
        }
    }

    @Override
    public void close() {
        // Close ResultSet/Statement/Connection owned by the reader, if any.
    }
}
```

This is an **illustrative skeleton**, not a production-ready reader: `read()` is intentionally unimplemented, and a real implementation must update `nextAfterId` strictly according to items handed off under the framework's checkpoint contract. Moreover, saving the last key before commit is only a *checkpoint candidate*; the framework persists it at the appropriate transaction point. For standard paging/cursors, prefer Spring Batch's battle-tested readers over custom ones written just to shave a few SQL calls.

If wrapping an `ItemStreamReader` inside a delegate hidden from Spring Batch, ensure the wrapper forwards `open`/`update`/`close` or registers the stream explicitly with the step. Otherwise, the job may read and write fine yet fail to persist restart checkpoints.

## 8. Parallelism: Boosting Throughput While Isolating Restart Boundaries

Increasing concurrency significantly alters execution order. When a chunk step runs multi-threaded, items are not necessarily read, processed, written, and committed in strict linear order. A shared stateful reader may not be thread-safe; simply attaching a `TaskExecutor` without auditing the reader breaks correctness and restartability.

### 8.1. Multi-Threaded Steps

Spring Batch can use a task executor to run chunks across multiple threads (exact APIs vary by major version). Speed can improve when waiting on I/O or parallelizing CPU-bound processors. However, check:

- Is the reader safe under concurrent calls from multiple threads?
- Can a single `ExecutionContext` offset remain valid when chunks complete out of order?
- Does the writer share buffers, file handles, or transaction state across threads?
- If a later chunk commits before an earlier chunk and the process crashes, can restart miss or re-read items?

`SynchronizedItemStreamReader` synchronizes reader access to prevent certain read races, yet **does not make a multi-threaded step safely restartable**; chunks still process and commit out of order. Synchronizing `read()` on a stateful reader does not serialize the full multi-threaded chunk transactions.

### 8.2. Partitioning with Disjoint Data Ranges

For large jobs needing controllable restarts, partitioning is usually cleaner because each worker owns an independent slice and its own `StepExecution`/context:

```text
masterStep
   |
   +-- partition-00: order_id 1..100000
   |      dedicated reader + dedicated writer + dedicated checkpoint
   |
   +-- partition-01: order_id 100001..200000
   |      dedicated reader + dedicated writer + dedicated checkpoint
   |
   +-- partition-02: order_id 200001..300000
          dedicated reader + dedicated writer + dedicated checkpoint
```

A `Partitioner` produces an `ExecutionContext` per range:

```java
Map<String, ExecutionContext> partitions = new LinkedHashMap<>();

ExecutionContext first = new ExecutionContext();
first.putLong("minId", 1L);
first.putLong("maxId", 100_000L);
partitions.put("range-000", first);

ExecutionContext second = new ExecutionContext();
second.putLong("minId", 100_001L);
second.putLong("maxId", 200_000L);
partitions.put("range-001", second);
```

This illustrates the map returned from `Partitioner.partition(int gridSize)`; import `Map`, `LinkedHashMap`, and `ExecutionContext` accordingly. In the worker step, the reader injects `minId`/`maxId` via `@StepScope`—e.g., `@Value("#{stepExecutionContext['minId']}")`—to bound its query. Ranges must be **non-overlapping and cover the entire input**. Give each partition a stable name/identity so it can be tracked and restarted.

If the partitioner recomputes different boundaries on every launch (due to newly inserted rows or changing `gridSize`), partition names or ranges can drift. On restarts, preserve the committed partition plan or derive deterministic ranges from an input snapshot/version. Never change partition count between a failed run and its restart without verifying metadata and already-processed ranges.

### 8.3. Remote Chunking and Async Processing

Remote chunking dispatches work to workers over messaging. Retries and redeliveries can reprocess chunks; require message/chunk IDs, idempotent processing, and clear rules for when the manager treats results as committed. If workers call APIs or write outside a shared transaction, add reconciliation. Choose remote chunking only when operational complexity is justified by real scaling needs, not merely because a job "seems slow."

## 9. Optimizing Processors and Memory with Minimal Checkpoint Impact

Pure-function processors rarely touch metadata:

- Avoid re-parsing config or recompiling regexes per item when they can be prepared once.
- Trim unnecessary intermediate allocations without introducing thread-unsafe mutable shared caches.
- Cache small, explicitly versioned reference datasets per run.
- Batch reference lookups when business semantics remain identical.
- For CPU-heavy work, profile before adding threads; exceeding core counts often just raises contention and GC.

Even so, processor logic changes can break restart **determinism**. Suppose the initial run converts currencies using November 16 rates, and next day's restart queries "latest rates": identical inputs yield inconsistent outputs. Lock `rateVersion`/`rulesetVersion` inside identifying parameters or source snapshots so every execution of an instance uses consistent rules.

In multi-step pipelines, keep state shared via `JobExecutionContext`/`StepExecutionContext` small and semantically stable. Never use `ExecutionContext` as a cache for millions of rows: serialized metadata bloats, checkpoints slow down, and restarts spend heavy time deserializing.

## 10. Keeping Source Inputs Stable Across Restarts

An optimization that looks safe performance-wise can be dangerous against a mutating source. Define the **dataset contract** before reading:

| Source | Mutation Hazard | Common Solution |
| --- | --- | --- |
| CSV on shared folder | File overwritten under same path | Copy to immutable staging; track checksum/object version |
| Live transaction table | Inserts/deletes/updates shift query results | Read snapshot, fix watermark, or filter by immutable status |
| Paginated API | Responses shift across calls; offset drift | Use stable cursor tokens / snapshot APIs or staging |
| Reference data | Rates/rules edited mid-run | Pin data/ruleset version for the `JobInstance` |
| Queue / message | Redeliveries after failure; no shared tx | Idempotency keys and processed-message tracking |

In databases, `ORDER BY id` on a unique key yields deterministic ordering **within a snapshot**, but does not freeze dataset membership. If new rows with higher IDs keep arriving, a restart reader may pull extra out-of-scope rows. Fixing a `maxId` at job creation alongside `businessDate` and `sourceVersion` bounds the dataset in some designs, though updates/deletes below `maxId` still call for snapshots or staging tables.

## 11. Failure Testing Is Mandatory for Safe Optimization

Integration tests that only run to `COMPLETED` miss many checkpoint bugs. After any substantial change to chunks, paging, writers, or concurrency, run a **fail-then-restart** scenario verifying committed outputs.

### 11.1. Illustrative Scenario

Immutable input: `A001, A002, A003, A004, A005`. Chunk size 2.

```text
Run #1:
  chunk 1 [A001,A002] -> COMMIT
  chunk 2 [A003,A004] -> inject writer error, ROLLBACK
  JobExecution #100 = FAILED
  Final output of Run #1 = A001,A002

Restart with same identifying JobParameters:
  reader opens saved context
  read/write remaining items
  JobExecution #101 = COMPLETED
  Final output = A001,A002,A003,A004,A005
```

Tests should verify all three layers:

1. **Framework:** first execution ends `FAILED`, second ends `COMPLETED`, both sharing the same `JobInstance.id` with distinct `JobExecution.id`s.
2. **Checkpoint:** the step resumes from committed state; if logging checkpoints, logs match repository state—never substitute logs for actual results.
3. **Business output:** exact key set, zero duplicates, expected counts, and row payloads matching input/rules.

### 11.2. Java Assertions After a Two-Phase Run

Assuming `first`, `restarted`, and `jdbcTemplate` come from a Spring Batch 5.x integration test using `JobLauncherTestUtils`/`JobLauncher` and a real metadata repository:

```java
assertThat(first.getStatus()).isEqualTo(BatchStatus.FAILED);
assertThat(restarted.getStatus()).isEqualTo(BatchStatus.COMPLETED);

assertThat(restarted.getJobInstance().getId())
    .isEqualTo(first.getJobInstance().getId());

assertThat(restarted.getId()).isNotEqualTo(first.getId());

List<String> codes = jdbcTemplate.queryForList(
    "SELECT order_code FROM order_result ORDER BY order_code",
    String.class
);
assertThat(codes)
    .containsExactly("A001", "A002", "A003", "A004", "A005");

Integer duplicateKeys = jdbcTemplate.queryForObject("""
    SELECT COUNT(*) FROM (
      SELECT order_code
      FROM order_result
      GROUP BY order_code
      HAVING COUNT(*) > 1
    ) t
    """, Integer.class);
assertThat(duplicateKeys).isZero();
```

This is an **assertion pattern**, not a complete runnable test: prepare the `order_result(order_code, ...)` table and failure injection yourself. Note that if the target table already enforces a unique constraint, the duplicate check returns 0 by schema design—still verify output counts, payloads, and external side effects to prove true correctness.

### 11.3. Testing Across Multiple Chunk Sizes

Run the same fixture with chunk sizes 1, 10, and 250 while injecting failures before and after checkpoints. Final business outcomes must stay identical, even though `commitCount`, per-execution read/write counts, and rework volume differ. Also test restarting old metadata from prior deployed versions before changing config or reader keys.

### 11.4. Testing Multiple Partitions

Inject a failure in just one partition after sibling partitions reached `COMPLETED`. Upon restart, verify completed partitions are not re-run unintentionally, the failed partition resumes its exact range, and overall job outputs contain no duplicates. Changing worker/grid counts across failures also requires stable partition rules before claiming parallelism is safe.

## 12. Observing Restart Cost and Correctness in Production

Beyond normal runtimes, monitor:

- `jobName`, `businessDate`, `jobInstanceId`, `jobExecutionId`, and `stepExecutionId` to correlate related runs.
- Per-step-execution read, write, filter, skip, commit, and rollback counts.
- Chunk or chunk-group durations, input rates, and output rates.
- Active source ID/version, checkpoints persisted at key milestones, and post-failure re-read counts where measurable.
- Duplicate/upsert conflict counts, retries, backend latency, and destination-confirmed record counts.
- Recovery duration from detecting `FAILED` until the cycle's output is certified complete.

Never log the entire `ExecutionContext`: it may hold sensitive fields and large state. Log selected fields only, and never rely on logs to drive restart decisions; durable `JobRepository` metadata and committed business data are the source of truth.

Structured log example:

```text
event=batch.chunk.completed
jobName=importOrdersJob
businessDate=2026-11-16
jobExecutionId=512
stepExecutionId=841
partition=orders-range-00
readCount=100000
writeCount=99900
commitCount=400
checkpoint=lastId:100000
```

When logging checkpoints, reference only fields with a clear application reader contract. A `lastId` observed in memory during reading is not guaranteed to be the persisted post-commit value. In chunk processing, post-commit listeners emit more reliable progress signals; final reconciliation still belongs against the repository and target outputs.

## 13. Changes That Easily Break Restarts

| Seeming Optimization | Why It Is Dangerous | Safe Alternative |
| --- | --- | --- |
| Disabling `saveState` to cut metadata writes | Reader loses its saved offset | Disable only if step is designed to rerun from start idempotently |
| Setting chunk size huge | Long transactions/locks; failures redo massive work | Benchmark on representative data with fail/restart tests |
| Switching sort key from `id` to non-unique column | Paging and restarts drift / become non-deterministic | Use a stable, unique sort key |
| Renaming `reader.name` or context keys between runs | Reader cannot find prior saved state | Preserve checkpoint contracts, migrate, or drain old instances first |
| Sharing a stateful singleton reader across threads/steps | Shared cursor is not thread-safe | Use `@StepScope` per step and isolate per partition |
| Adding `TaskExecutor` to chunk step blindly | Out-of-order commits, ambiguous checkpoints | Partition disjoint ranges or prove safety via failure tests |
| Rerunning with a fresh identifying UUID | Spawns a new `JobInstance` and re-reads everything | Use cycle identifying parameters; restart via metadata |
| Appending to old output files | Duplicates data or resumes at wrong offset | Use stateful writers, explicit versioned paths, and restart tests |
| Switching writers to fire-and-forget async | Chunks commit before writes finish | Await acks/results or use outbox/idempotent workers |
| Changing partition counts/ranges every run | Restarts fail to match completed partitions | Keep partition names, ranges, and snapshots deterministic |
| Caching unversioned reference data | Restarts apply different rules than initial run | Pin dataset and ruleset versions |
| Deleting `BATCH_*` rows on job failure | Destroys metadata/`ExecutionContext` needed to recover | Preserve repository history and follow official restart flows |

## 14. Step-by-Step Controlled Optimization Workflow

A practical workflow for production jobs:

1. **Lock down input/output contracts:** business keys, source versions, ordering/snapshots, output counts/checksums, and what `COMPLETED` means operationally.
2. **Measure the baseline:** on a representative dataset, record throughput, DB query/flush times, locks, memory, and post-failure restart time.
3. **Apply low-risk optimizations first:** indexes, SQL queries, batch writers, eliminating redundant work, and reasonable fetch sizes while leaving processing boundaries intact.
4. **Tune chunk/page sizes:** adjust one parameter at a time, measuring speed, transaction length, rollbacks, and restarts.
5. **Introduce parallelism carefully:** favor clean data partitioning, isolated reader/step state, deterministic ordering, and idempotent outputs.
6. **Test failure paths:** inject mid-chunk errors, kill processes or drop connections in test environments, restart the exact instance, and verify final outputs.
7. **Deploy with observability:** monitor throughput, duration, retries/skips, duplicate conflicts, and incomplete cycles; keep a quick rollback path for config changes.

Never declare an optimization safe from a benchmark that only runs from start to `COMPLETED`. Explicitly test mid-run interruptions and resuming from persisted metadata. If `ExecutionContext` schemas or partitioning schemes change, test restarting in-flight instances created by the prior release.

## 15. Spring Batch Versions and APIs

Code snippets using `StepBuilder(...).chunk(size, transactionManager)`, `JdbcPagingItemReaderBuilder`, and `JdbcBatchItemWriterBuilder` follow **Spring Batch 5.x** syntax. Spring Batch 6 changes packages and APIs on core types. When upgrading major versions, check official docs and imports carefully—especially if incomplete `JobExecution`s remain in flight. **Framework upgrades and resuming in-flight data are coupled problems** that must be tested on cloned metadata/schemas and safe datasets before production upgrades.

The core concepts remain unchanged: `JobInstance` identified by parameters, `ExecutionContext` persisting state, `ItemStream` driving checkpoints, transactions bounding commits, and writers tolerating bounded reprocessing.

## Conclusion

Sustainable Spring Batch optimization is not just cranking up chunk sizes or thread counts. It is optimizing **within explainable transaction and checkpoint boundaries**: readers see consistent inputs, writers guarantee duplicate-safe effects, each partition owns isolated state, and `JobRepository` retains the metadata needed to restart. Benchmark the happy path, then deliberately break and recover the job to prove your optimization keeps data intact.

## References

- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): chunk boundaries, commits, and transactions.
- [Spring Batch Reference — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): `open`, `update`, `close`, `ExecutionContext`, and restarts.
- [Spring Batch Reference — Database Readers and Writers](https://docs.spring.io/spring-batch/reference/readers-and-writers/database.html): cursor/paging readers and JDBC batch writers.
- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded steps, partitioning, and remote chunking.
- [Spring Batch Reference — Configuring a Job](https://docs.spring.io/spring-batch/reference/job/configuring.html): job instance identity, status, and restarts.
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): testing steps/jobs and restart scenarios.
