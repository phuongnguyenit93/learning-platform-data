# Commit Interval Tuning in Spring Batch

## 1. What Is the Commit Interval?

In **Spring Batch Core Processing**, a *chunk-oriented* Step typically executes a cycle: read items, process items, group multiple items into a chunk, write the chunk, and commit the transaction. The **commit interval** (commonly called **chunk size**) is the number of items accumulated under the chunk completion policy before the framework performs the corresponding write and commit.

Example with **Spring Batch 5.2.x**:

~~~java
new StepBuilder("importOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
~~~

In the configuration above, the Step normally reads/processes up to 100 input items per chunk, passes the processed items to the writer, updates checkpoints if applicable, and commits the transaction. The final chunk may contain fewer than 100 items.

Adjusting the commit interval simultaneously affects **throughput**, transaction count, memory consumption, database lock hold duration, rollback cost, and restartability. The goal is to select a range that delivers stable performance while satisfying data integrity and recovery requirements. There is no single optimal commit interval for every Job.

### Lesson Objectives

- Understand how the commit interval impacts transaction boundaries and checkpoints.
- Distinguish commit interval from JDBC fetch size, page size, JDBC batch size, and concurrency.
- Analyze the trade-offs of small, medium, and large chunks.
- Configure a chunk-oriented Step using the appropriate Spring Batch API.
- Design benchmarks and collect metrics for evidence-based tuning.
- Test rollbacks, restarts, and idempotency when changing the commit interval.
- Formulate a selection strategy and safely roll out changes to production.

## 2. Visualizing Chunks and Commit Boundaries

Suppose the source contains 10 items and the commit interval is 3:

~~~text
Step starts
    |
    +-- Transaction #1
    |     read/process 1, 2, 3
    |     writer([1, 2, 3])
    |     COMMIT
    |
    +-- Transaction #2
    |     read/process 4, 5, 6
    |     writer([4, 5, 6])
    |     COMMIT
    |
    +-- Transaction #3
    |     read/process 7, 8, 9
    |     writer([7, 8, 9])
    |     COMMIT
    |
    +-- Transaction #4
          read/process 10
          writer([10])
          COMMIT
~~~

In the simple case, the number of **non-empty data chunks** is approximately:

~~~text
data_chunks ≈ ceil(input_item_count / commit_interval)

10 items, interval 3 -> 4 data chunks
100,000 items, interval 100 -> 1,000 data chunks
~~~

Distinguish data-bearing chunks from `StepExecution.getCommitCount()`. Some execution paths perform additional commits when checking end-of-stream, handling skips/retries, or updating metadata. Therefore, do not use the formula above to assert the exact value of the `COMMIT_COUNT` column in all scenarios.

### Items Read and Items Written Can Differ

The processor can return `null` to **filter** an item. For example, if a chunk reads 100 items and filters 15, the writer receives only 85 items. Skips and retries can also cause rollbacks or reprocessing.

Accordingly:

- `READ_COUNT` measures items read under Step semantics.
- `FILTER_COUNT` measures items filtered out by the processor.
- `WRITE_COUNT` measures items written under Step semantics.
- `READ_SKIP_COUNT`, `PROCESS_SKIP_COUNT`, and `WRITE_SKIP_COUNT` measure items skipped due to errors permitted by policy.
- `COMMIT_COUNT` and `ROLLBACK_COUNT` measure transactions as recorded by `StepExecution`.

Do not infer exact writer call counts or transaction counts solely by dividing `WRITE_COUNT / chunkSize` when filtering, retrying, or skipping occurs.

## 3. Chunks Too Small: Benefits and Costs

With `chunk(1, transactionManager)`:

~~~text
read A -> process A -> write A -> COMMIT
read B -> process B -> write B -> COMMIT
read C -> process C -> write C -> COMMIT
...
~~~

A 100,000-item Job may require roughly 100,000 data commits. Every commit carries overhead: transaction coordination, database logging, network round-trips, and metadata/checkpoint updates at relevant points.

**Advantages of small chunks:**

- Smaller in-memory item lists.
- Shorter transactions, reducing lock hold times.
- Rolling back a chunk forces fewer items to be reprocessed.
- Frequent checkpoints, which is helpful when restarting after a failure.
- The Step has more frequent opportunities to respond to stop signals at nearby chunk boundaries.

**Disadvantages:**

- High transaction count and more frequent metadata updates.
- Less opportunity for the writer to leverage large SQL batches.
- Fixed commit costs can dominate total runtime.
- When the database is remote, many round-trips can reduce throughput.

If each item takes 300 ms of CPU processing, commit cost may be a minor fraction. Increasing chunk size from 10 to 100 may barely help in that case. Conversely, with small items and a JDBC writer, reducing commits can make a dramatic difference.

## 4. Chunks Too Large: Why Can Throughput Drop?

With `chunk(5_000, transactionManager)`, the Step may hold thousands of items and processed results inside a single transaction. Fewer commits occur, but new risks emerge:

| Impact | Mechanism |
| --- | --- |
| Higher memory usage | One chunk holds many objects, collections, and buffers until the writer finishes. |
| Long transactions | Locks, transaction logs, and database sessions stay open longer. |
| Costlier rollbacks | An error near the end of a chunk can force reprocessing of many uncommitted items. |
| Sparse checkpoints | On restart, the reader may have to re-read most of an uncommitted chunk. |
| Slow stop response | Tasklets/Steps generally process stop requests only when control returns to the framework. |
| Writer overload risk | The writer must handle many SQL parameters, messages, or requests at once. |
| Higher tail latency | A single slow item can delay completion of the entire chunk. |

MVCC databases can suffer from long transactions and retained row versions. Row-lock-heavy systems can experience increased lock waits and deadlocks. If the transaction timeout is shorter than the chunk processing duration, the Job may fail repeatedly.

Consequently, performance curves usually exhibit an **optimal balance zone**: initially increasing chunk size reduces commit overhead; beyond a threshold, rising memory pressure, contention, and recovery cost can erase the gains.

## 5. Commit Interval Differs from Fetch Size, Page Size, and Batch Size

These parameters are frequently conflated:

| Parameter | What It Controls | Relationship to Commit |
| --- | --- | --- |
| **Commit interval** | Number of items to complete a chunk and Step transaction boundary. | This is the parameter being tuned. |
| **JDBC fetch size** | Hints how the driver fetches rows from a `ResultSet` in batches. | Does not govern the transaction boundary. |
| **Paging page size** | Number of rows a paging reader fetches per query/page. | Does not need to equal chunk size. |
| **JDBC batch size** | Number of SQL statements/parameters grouped into a JDBC batch. | May be influenced by chunk, but depends on writer/driver. |
| **Partition/grid size** | Number of data partitions/parallel execution units. | Affects how many chunks/transactions run concurrently. |
| **Connection pool size** | Number of available JDBC connections. | Caps concurrency; does not determine chunk size. |
| **Retry limit** | Retry budget upon failure. | Alters reprocessing cost; does not define commit interval. |

For example, a `JdbcCursorItemReader` configured with `fetchSize(500)` in a Step with `chunk(100, tx)`: the driver can fetch rows in batches of 500 while Spring Batch completes chunks every 100 items. Conversely, setting chunk to 500 does not guarantee the driver sends a single SQL command for all 500 items.

For JPA, reader page size, `EntityManager` persistence context, and provider-level JDBC batching are also distinct layers. Never assume increasing chunk size automatically optimizes all of them.

## 6. Cost Model to Reason About Before Experimenting

This can be approximated as:

~~~text
T_total ≈ T_read
        + T_process
        + T_write
        + T_commit
        + T_lock_or_contention
        + T_retry_and_rollback

T_commit ≈ number_of_commits * fixed_commit_overhead
number_of_data_chunks ≈ ceil(total_input_items / commit_interval)
~~~

As commit interval increases, `number_of_data_chunks` decreases. However, `T_lock_or_contention` and `T_retry_and_rollback` may rise; `T_write` also depends on whether the writer batches SQL.

Theoretical calculation example for 100,000 items, ignoring filtering/skipping/retries:

| Commit Interval | Estimated Data Chunks |
| ---: | ---: |
| 1 | 100,000 |
| 10 | 10,000 |
| 50 | 2,000 |
| 100 | 1,000 |
| 250 | 400 |
| 500 | 200 |
| 1,000 | 100 |
| 5,000 | 20 |

This table is **not a benchmark** and does not prove that chunk 5,000 is faster than chunk 100. It only helps estimate the scale of fixed transaction overhead along a simple execution path.

## 7. Practical Configuration with Spring Batch 5.2.x

This example uses Java 17, Spring Boot 3, and Spring Batch 5.2.x with a **JDBC JobRepository**. The Job reads a source table and writes to a target table via a JDBC writer.

### 7.1. Database Tables

~~~sql
CREATE TABLE source_orders (
    id BIGINT PRIMARY KEY,
    amount DECIMAL(18, 2) NOT NULL
);

CREATE TABLE imported_orders (
    id BIGINT PRIMARY KEY,
    amount DECIMAL(18, 2) NOT NULL
);
~~~

The primary key on the target table helps catch duplicate writes during restart tests. In production, design appropriate business keys and idempotency/upsert strategies.

### 7.2. Model

~~~java
import java.math.BigDecimal;

public class OrderRecord {
    private final Long id;
    private final BigDecimal amount;

    public OrderRecord(Long id, BigDecimal amount) {
        this.id = id;
        this.amount = amount;
    }

    public Long getId() {
        return id;
    }

    public BigDecimal getAmount() {
        return amount;
    }
}
~~~

### 7.3. Reader and Writer

~~~java
import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class OrderIoConfiguration {

    @Bean
    @StepScope
    JdbcCursorItemReader<OrderRecord> ordersReader(DataSource dataSource) {
        return new JdbcCursorItemReaderBuilder<OrderRecord>()
                .name("ordersReader")
                .dataSource(dataSource)
                .sql("SELECT id, amount FROM source_orders ORDER BY id")
                .rowMapper((rs, rowNum) -> new OrderRecord(
                        rs.getLong("id"),
                        rs.getBigDecimal("amount")))
                .fetchSize(300)
                .saveState(true)
                .build();
    }

    @Bean
    JdbcBatchItemWriter<OrderRecord> ordersWriter(DataSource dataSource) {
        return new JdbcBatchItemWriterBuilder<OrderRecord>()
                .dataSource(dataSource)
                .sql("INSERT INTO imported_orders(id, amount) " +
                     "VALUES (:id, :amount)")
                .beanMapped()
                .build();
    }
}
~~~

`ORDER BY id` establishes a deterministic read order **provided the source does not mutate**. If rows can be inserted or deleted before the checkpoint position, a row-offset saved by the reader may not be safe enough; use a data snapshot or a business-key checkpointing strategy.

`saveState(true)` lets the reader store its read position in `ExecutionContext` to support restarts. `@StepScope` creates a fresh reader per `StepExecution`; avoid sharing a stateful cursor across executions.

### 7.4. Step with Commit Interval 100

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration(proxyBeanMethods = false)
class OrderJobConfiguration {

    @Bean
    Step importOrdersStep(
            JobRepository repository,
            PlatformTransactionManager tx,
            JdbcCursorItemReader<OrderRecord> ordersReader,
            JdbcBatchItemWriter<OrderRecord> ordersWriter) {

        final int commitInterval = 100;

        return new StepBuilder("importOrdersStep", repository)
                .<OrderRecord, OrderRecord>chunk(commitInterval, tx)
                .reader(ordersReader)
                .processor(order -> order)
                .writer(ordersWriter)
                .build();
    }

    @Bean
    Job importOrdersJob(
            JobRepository repository,
            Step importOrdersStep) {

        return new JobBuilder("importOrdersJob", repository)
                .start(importOrdersStep)
                .build();
    }
}
~~~

In production, externalize `commitInterval` as an application property such as `batch.tuning.commit-interval=100` and bind it via `@ConfigurationProperties`. This is a **custom-defined property**, not one Spring Batch reads automatically. When parsing configuration, enforce positive values and set sensible bounds for your workload.

The reader, writer, and Step should use compatible transaction managers and DataSources. If metadata and the writer use separate resources or transaction managers, verify commit, checkpoint, and recovery consistency behavior.

## 8. `CompletionPolicy` for Flexible Chunks

If you do not want a fixed item count, Spring Batch supports **`CompletionPolicy`** to decide when a chunk ends according to a policy.

Example in Spring Batch 5.2:

~~~java
import org.springframework.batch.repeat.CompletionPolicy;
import org.springframework.batch.repeat.policy.SimpleCompletionPolicy;

@Bean
CompletionPolicy simplePolicy() {
    return new SimpleCompletionPolicy(100);
}
~~~

The builder accepts a `CompletionPolicy` instead of a fixed chunk size:

~~~java
new StepBuilder("policyStep", repository)
        .<OrderRecord, OrderRecord>chunk(simplePolicy, transactionManager)
        .reader(reader)
        .writer(writer)
        .build();
~~~

`SimpleCompletionPolicy(100)` still bounds chunks by item count. Other policies can be based on elapsed time or custom termination conditions. For workloads with wide variance in per-item processing time, a suitable policy helps bound transaction length. However, understand the exact semantics of the policy in your Spring Batch version and test chunk boundary conditions; do not assume a time-based policy can immediately interrupt a blocked JDBC or HTTP call.

## 9. How Does the Commit Interval Affect Restart?

When a Step fails, previously committed chunks generally remain persisted; the in-flight chunk may roll back depending on transaction behavior. A reader supporting restart via `ExecutionContext` resumes from its saved checkpoint.

Example with 1,000 items, commit interval 100, where the processor intentionally fails at item 231:

~~~text
Execution 1:
  items 1..100   -> COMMIT
  items 101..200 -> COMMIT
  items 201..231 -> processor fails -> ROLLBACK chunk
  Job            -> FAILED

Execution 2 (restart same JobInstance):
  restore from checkpoint after item 200
  items 201..300 -> COMMIT
  ...
  items 901..1000 -> COMMIT
  Job             -> COMPLETED
~~~

If interval = 10, the uncommitted work lost upon failure at 231 is smaller. If interval = 500, failing at 231 can force re-reading and reprocessing all items in the first chunk upon restart.

Conditions for this example to hold:

- The reader saves state and reads in a deterministic order.
- The writer's JDBC operations participate in the same transaction by design.
- `BATCH_*` metadata is preserved between the two executions.
- No non-transactional side effects are re-invoked without idempotency.
- No new identifying `JobParameters` are supplied when intending to restart.

**Restarting does not automatically guarantee exactly-once delivery** for HTTP APIs, emails, files, or message brokers. If an external API already received 80 requests before the chunk failed prior to metadata commit, restarting may re-send them. Use stable idempotency keys tied to business keys, unique constraints, outbox patterns, or reconciliation.

To tune safely, measure **recovery cost after failure**, not just happy-path duration.

## 10. Interaction with Databases and Writers

| Writer Type | What to Measure When Increasing the Interval |
| --- | --- |
| `JdbcBatchItemWriter` | Round-trips, effective JDBC batching, transaction logs, index updates, lock waits, and write throughput. |
| `JpaItemWriter` | `EntityManager` flush/clear behavior, persistence context size, dirty checking, JDBC batching, and heap usage. |
| File writer | Flushes, buffering, checkpoints, and truncate/rollback safety upon restart. |
| HTTP/API writer | Timeouts, rate limits, idempotency, request count, and latency; chunking does not automatically create bulk APIs. |
| Message writer | Broker ACK/transactions, duplicate messages, and recovery mechanics. |
| Secondary-DB writer | Multi-resource consistency and compensation/reconciliation strategies. |

### JDBC Batching Is Not the Same as Commit Interval

`JdbcBatchItemWriter` leverages JDBC batching. Even so, the driver may split SQL batches, rewrite/optimize statements per dialect, or enforce driver-specific limits. Increasing chunk size does not guarantee a proportional drop in network round-trips.

If a writer simply calls `JdbcTemplate.update(...)` once per item, increasing chunk size mostly reduces a portion of transaction overhead; it does not automatically turn individual calls into a JDBC batch. Optimize at the layer actually causing the bottleneck.

### Locks, Isolation, and Transaction Timeouts

Long transactions hold locks longer and raise contention. On workloads concurrently updating contended tables, chunk 1,000 may lengthen database wait queues compared to chunk 100. If the transaction timeout is short or an item triggers a multi-second API call, an overly large interval can cause recurring Step failures.

Measure p95/p99 transaction duration, not just the mean. A handful of outlier items can abruptly stretch a single chunk's duration.

## 11. Memory and Concurrency

A chunk's memory footprint can be approximated as:

~~~text
memory ≈ items_in_chunk * average_item_footprint
       + processed_output_buffers
       + reader/writer_buffers
       + framework_and_application_state
~~~

If each item consumes about 50 KiB once instantiated:

| Chunk Size | Estimated Item Footprint (Excluding Overhead) |
| ---: | ---: |
| 10 | approx. 0.49 MiB |
| 100 | approx. 4.88 MiB |
| 1,000 | approx. 48.83 MiB |
| 10,000 | approx. 488.28 MiB |

This is an illustrative calculation, not actual heap telemetry. Large payloads, deep object graphs, or JPA caches can make real memory usage far higher.

With partitioning or multi-threaded Steps, the number of concurrently active chunks also multiplies memory usage:

~~~text
Partition A -> chunk(100) -> transaction A
Partition B -> chunk(100) -> transaction B
Partition C -> chunk(100) -> transaction C
Partition D -> chunk(100) -> transaction D
~~~

Four partitions may hold four chunks simultaneously, plus connections, reader buffers, writer buffers, and metadata transactions. Increasing both chunk size and concurrency in the same benchmark makes it very difficult to isolate what caused a performance gain or failure.

Tune commit interval and concurrency in **separate experiments** first, then evaluate the combined configuration.

## 12. Designing Benchmarks to Choose an Interval

A reliable benchmark plan covers happy-path runs, failure-path runs, and runs under concurrent load.

### Step 1: Define Criteria

Common metrics include:

- **Throughput**: business items completed per second.
- **End-to-end duration**: total Job completion time.
- **Heap/GC**: peak heap, allocation rate, and GC pauses.
- **Database**: CPU, transaction latency, lock waits, deadlocks, and log I/O.
- **Step metadata**: read/write/filter/skip/commit/rollback counts.
- **Recovery cost**: items reprocessed and restart time after a failure.
- **SLA**: does the Job finish on time without degrading other workloads?

For example, if 100,000 items are written accurately in 250 seconds:

~~~text
throughput = 100000 / 250 = 400 items/second
~~~

This is an illustrative calculation. For Jobs with filtering or skipping, define clearly whether "completed items" means items read, items written, or successful business units.

### Step 2: Hold Other Variables Constant

Within a single experiment sweep, vary only chunk size; keep fixed:

- Item count, size distribution, and ordering.
- Reader, processor, writer, SQL queries, and indexes.
- JDBC driver, fetch size, page size, and transaction isolation.
- JVM heap/GC settings, CPU, database instance, and connection pool.
- Concurrency/partition count and competing workload level.
- Retry/skip policies, timeouts, and logging level.
- Data seeding/resetting and `JobRepository` cleanup between **independent benchmark runs**.

Run warm-up iterations, repeat each configuration multiple times, and alternate run order across rounds to avoid warm-cache bias. Report median and p95 rather than taking a single fastest run.

### Step 3: Sweep a Range of Values

An initial sweep might test:

~~~text
10 -> 50 -> 100 -> 250 -> 500 -> 1000
~~~

This is an **experimental sweep**, not a default recommendation. Large payloads or slow HTTP calls may require testing 1, 5, 10, 20. For a JDBC writer inserting tiny rows, you can explore larger values after confirming memory and locks remain stable.

Experiment recording table:

| Chunk Size | Duration (s) | Throughput | Peak Heap | DB Lock Wait | Rollbacks | Notes |
| ---: | --- | --- | --- | --- | --- | --- |
| 10 | Measure | Measure | Measure | Measure | Measure | Fill after run |
| 50 | Measure | Measure | Measure | Measure | Measure | Fill after run |
| 100 | Measure | Measure | Measure | Measure | Measure | Fill after run |
| 250 | Measure | Measure | Measure | Measure | Measure | Fill after run |
| 500 | Measure | Measure | Measure | Measure | Measure | Fill after run |
| 1000 | Measure | Measure | Measure | Measure | Measure | Fill after run |

Never fill in hypothetical numbers to pick a winner. Conclusions must come from your real system and dataset.

### Step 4: Fault Injection

Test failure scenarios separately, such as failing at item 231 or near the end of a chunk. Verify:

- Data committed prior to failure.
- Rollback of the incomplete chunk.
- Ability to restart from checkpoint.
- Final target data completeness with zero duplicates.
- Restart duration and number of reprocessed items.
- External side effects protected by idempotency.

A chunk size with top happy-path throughput may sharply inflate restart cost, so inspect both sets of numbers.

### Step 5: Test Under Contention

Run the Job alongside real traffic or a simulated competing database workload. Observe transaction timeouts, lock waits, latency impact on other jobs/services, and connection pool saturation. The best setting on an idle benchmark machine may cause bottlenecks in production.

## 13. Monitoring via `StepExecution` and Micrometer

Spring Batch persists key metadata in `StepExecution`. Example listener in Spring Batch 5.2.x:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public class StepPerformanceListener implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(StepPerformanceListener.class);

    @Override
    public void afterStep(StepExecution step) {
        log.info(
            "step={} read={} write={} filter={} " +
            "commits={} rollbacks={} status={}",
            step.getStepName(),
            step.getReadCount(),
            step.getWriteCount(),
            step.getFilterCount(),
            step.getCommitCount(),
            step.getRollbackCount(),
            step.getStatus()
        );
    }
}
~~~

Register the listener on the Step builder:

~~~java
.listener(new StepPerformanceListener())
~~~

These counts aid in evaluating transactions and business outcomes. However:

- `COMMIT_COUNT` may not equal exactly `ceil(READ_COUNT / chunkSize)`.
- `ROLLBACK_COUNT` is distinct from retry count.
- `READ_COUNT` and `WRITE_COUNT` diverge when filtering or skipping occurs.
- Metadata does not natively include per-chunk p95 duration or lock hold times.

Combine **Micrometer** (Job/Step timers and version-appropriate item/chunk metrics) with JVM and database metrics. If you need per-chunk durations, instrument an appropriate listener while avoiding excessive logging on the hot path.

Examples of questions a dashboard should answer:

| Signal | Question |
| --- | --- |
| Step duration | Did the new chunk size make the Step faster? |
| Throughput items/s | How many real items are successfully written per second? |
| Commit/rollback count | How did transaction cadence and failures change? |
| Heap/GC | Did larger chunks cause memory pressure? |
| DB lock wait, deadlock | Are longer transactions hurting other workloads? |
| Connection pool wait | Does concurrency exceed DataSource capacity? |
| Recovery time | How long does a Job restart take after a failure? |

Do not attach `jobExecutionId` or item IDs as Prometheus labels because they create high cardinality. Keep those IDs in structured logs or traces, and use low-cardinality labels like Job, Step, and environment on metrics.

## 14. Testing Commit Intervals and Rollbacks

An integration test should use a **real JDBC JobRepository** to verify checkpointing and restarts. Do not wipe `BATCH_*` metadata between the failed run and the restart run within the same test.

### Boundary Cases to Test

| Total Items | Chunk Size | Purpose |
| ---: | ---: | --- |
| 0 | 10 | Empty source; Step completes safely. |
| 1 | 10 | Single partial final chunk. |
| 9 | 10 | Fewer items than the interval. |
| 10 | 10 | Exact match with the interval. |
| 11 | 10 | One full chunk plus one small final chunk. |
| 100 | 1 | High-transaction-count path. |
| 100 | 100 | Single-data-chunk path. |
| 101 | 100 | Remainder crossing a chunk boundary. |

With a non-retryable failure at item 231, chunk size 100, and a deterministically ordered 1,000-item dataset, the simple expectation is 200 committed rows in the target table. After restarting the same `JobInstance`, there should be 1,000 rows with no duplicates.

### Spring Batch 5.2.x Integration Test Skeleton

Assume a Job named `importOrdersJob`, JDBC reader/writer, and a processor using a `FailureSwitch` that throws a deterministic exception at item 231:

~~~java
@SpringBatchTest
@SpringBootTest
class CommitIntervalIT {

    @Autowired
    JobLauncherTestUtils launcher;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    FailureSwitch failureSwitch;

    @Test
    void failedChunkRollsBackAndRestartResumes() throws Exception {
        // Before test: seed 1,000 source rows, clear output
        // and clear metadata from other tests on a dedicated test database.
        failureSwitch.failOnId(231L);

        JobParameters params = new JobParametersBuilder()
                .addString("caseKey", "chunk100-failure")
                .toJobParameters();

        JobExecution first = launcher.launchJob(params);
        assertEquals(BatchStatus.FAILED, first.getStatus());

        Integer beforeRestart = jdbc.queryForObject(
                "SELECT COUNT(*) FROM imported_orders", Integer.class);
        assertEquals(200, beforeRestart);

        failureSwitch.disable();
        JobExecution second = launcher.launchJob(params);

        assertEquals(BatchStatus.COMPLETED, second.getStatus());
        assertEquals(first.getJobInstance().getInstanceId(),
                     second.getJobInstance().getInstanceId());

        Integer finalCount = jdbc.queryForObject(
                "SELECT COUNT(*) FROM imported_orders", Integer.class);
        assertEquals(1000, finalCount);
    }
}
~~~

This is an **illustrative skeleton**; implement `FailureSwitch`, test data setup, imports, and bean wiring yourself. For the 200-row expectation to hold, the processor must throw **before the writer runs** on item 231, the Step must not skip or retry that exception, and the writer must participate in the appropriate JDBC transaction. If the framework runs asynchronously, wait for terminal status before asserting.

Do not place `@Transactional` over the entire integration test if it masks the Step's real commits and rollbacks. Data-correctness tests must observe the transactions actually committed by Spring Batch.

### Post-Tuning Checks by Chunk Size

For each candidate chunk size, verify:

- Job reaches `COMPLETED` on valid data.
- Business results are complete with no duplicates.
- Proper rollback and restart on mid-chunk failures.
- No transaction timeout violations.
- No out-of-memory issues on large datasets.
- No deadlocks under concurrent load.

## 15. Tuning by Workload Type

**CPU-bound:** if `ItemProcessor` performs heavy computation, commit overhead may not be the bottleneck. Profile CPU usage; consider partitioning or concurrency separately if reader/writer thread safety permits.

**JDBC write-heavy:** if rows are small and the writer batches well, a moderate chunk size usually yields major gains over chunk 1. Measure actual JDBC batching, log I/O, locks, and indexes; increasing chunk size past a threshold may stop helping.

**JPA:** pay attention to the persistence context, `flush`/`clear` calls, and lazy associations. A large chunk can retain many entities and increase dirty-checking and GC overhead. Do not look only at commit count.

**Large payloads:** items several MB in size call for small chunks. Memory footprint of objects and buffers outweighs saving a few commits.

**API-bound:** larger chunks do not automatically parallelize sequential HTTP calls. Prioritize timeouts, bulk endpoints, API invocation patterns, rate limits, and idempotency.

**Mixed latency:** if most items take 1 ms while a few take several seconds, chunk 100 can exhibit highly variable durations. Measure tail latency and consider an appropriate completion policy.

## 16. Rolling Out Configuration Changes to Production

Changing from 100 to 1,000 may improve throughput while also increasing transaction duration and restart cost. Recommended workflow:

1. Record baseline: throughput, duration, GC, DB contention, and rollback/recovery metrics.
2. Select a few candidates and benchmark on a representative dataset.
3. Test deliberate failures, restarts, and side-effect idempotency.
4. Separate chunk-size effects from fetch-size and concurrency changes.
5. Roll out via deployment and apply cleanly when new Step instances are created.
6. Monitor metrics closely post-deployment against the baseline.
7. Revert to the previous setting if SLA or stability degrades.

Changing `application.yml` does not guarantee an already-running Step changes its commit interval immediately; configuration is bound when the Step is constructed/configured. For a `FAILED` `JobInstance` awaiting restart, changing the interval alters future transaction boundaries. Test that carefully with checkpoints, writers, and final data, especially if code, schema, or serializers also changed.

If a Job has failed and is awaiting restart, **do not delete metadata** just to retry by creating a new `JobInstance`. Preserve execution history, pass the proper `JobParameters`, and verify change compatibility.

## 17. API Differences Between Spring Batch 5.2 and 6.x

The examples in this guide use Spring Batch 5.2.x syntax:

~~~java
new StepBuilder("loadStep", jobRepository)
        .<Input, Output>chunk(100, transactionManager)
        .reader(reader)
        .writer(writer)
        .build();
~~~

In Spring Batch 6.x, transaction manager configuration is expressed via the corresponding builder API:

~~~java
new StepBuilder("loadStep", jobRepository)
        .<Input, Output>chunk(100)
        .transactionManager(transactionManager)
        .reader(reader)
        .writer(writer)
        .build();
~~~

In the 6.x line, readers/writers and item interfaces were reorganized into infrastructure modules/packages, so imports and dependencies must be adjusted for your version. JDBC `JobRepository` setup must also match your Spring Batch/Boot release.

**Tuning principles remain unchanged:** chunk size impacts transactions, memory, writer throughput, rollbacks, and restarts. However, never compare performance across two versions using commit count alone if the DataSource, transaction manager, JDBC driver, metadata schema, or writer configuration differs.

## 18. Common Mistakes

**Assuming bigger chunks are always better.** Large chunks can raise memory usage, lock waits, transaction timeouts, and recovery times.

**Equating fetch size with chunk size.** These operate at two separate layers: the reader and the Step.

**Looking only at theoretical commit counts.** Measure real wall time, throughput, heap, and database load.

**Skipping mid-chunk failure tests.** A happy-path run does not prove rollback, checkpointing, and idempotency work.

**Changing partitions and chunk size simultaneously.** You cannot tell which variable drove the performance change.

**Ignoring filters, skips, and retries.** Read and written item counts no longer map 1:1; interpret metadata carefully.

**Assuming JDBC rollback undoes HTTP calls or emails.** External side effects may already have succeeded and repeat upon restart.

**Changing the interval on restart without checking state compatibility.** Readers, writers, and `ExecutionContext` may depend on the prior version's behavior.

**Ignoring other applications sharing the database.** Single-tenant benchmark winners can harm overall production SLAs.

**Overlooking outlier large payloads.** Oversized items can cause the same chunk size to consume many times the average memory.

## 19. Practice Exercises

### Exercise 1 — Baseline Comparison

Use a JDBC Job importing 100,000 rows. Run with chunk sizes 10, 50, 100, 250, and 500 while holding all other parameters constant. Record duration, throughput, commits/rollbacks, peak heap, and lock waits. Pick a setting balancing performance and stability.

### Exercise 2 — Failure at Item 231

Inject a failure in the processor and run the Job with chunk sizes 10, 100, and 500. Observe committed row counts before failure and how much data is reprocessed on restart. Verify final data has no gaps or duplicates.

### Exercise 3 — Independent Fetch Size

Keep chunk at 100 and test `fetchSize` 50, 300, and 1,000 with `JdbcCursorItemReader`. Measure latency and memory at the JDBC driver level. Explain why changing fetch size does not necessarily change chunk count.

### Exercise 4 — Filtering and Skipping

Have the processor return `null` for 10% of items and skip a skippable exception. Inspect read/write/filter/skip counts; explain why the writer does not always receive the full commit interval's worth of items.

### Exercise 5 — Large Items and Multi-Partitioning

Simulate large payloads and run with one partition, then four partitions. Keep concurrency constant within each chunk-size sweep; measure peak heap, GC pauses, DB contention, and throughput.

### Exercise 6 — Out-of-Transaction API

Have a writer call an API with a stable idempotency key derived from the business key; mock the API to time out after persisting successfully. Restart the same `JobInstance` and verify no duplicate business side effects occur.

### Exercise 7 — Deployment Decision

From experimental data, build a decision matrix covering minimum throughput, maximum memory, p95 transaction duration, lock waits, and recovery time. Select a commit interval in the stable performance zone and outline a configuration rollback plan if production conditions degrade.

## 20. Official References

- [Spring Batch — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html)
- [Spring Batch — Commit Interval](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/commit-interval.html)
- [Spring Batch — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html)
- [Spring Batch — Readers and Writers](https://docs.spring.io/spring-batch/reference/readers-and-writers.html)
- [Spring Batch — Database Readers and Writers](https://docs.spring.io/spring-batch/reference/readers-and-writers/database.html)
- [Spring Batch — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html)
- [Spring Batch 5.2 — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing.html)
- [Spring Batch 5.2 — StepBuilder API](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/step/builder/StepBuilder.html)

