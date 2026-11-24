# Batch Update Size in Spring Batch: Choosing Batch Sizes for Efficient Writes

## 1. What Is Batch Update Size?

In Spring Batch systems, updating tens of thousands or millions of records takes far longer when the application sends **one SQL statement per item**. JDBC batching groups multiple parameter sets for **the same structurally identical SQL statement** so the driver executes them in bulk, reducing repeated statement-preparation overhead and database communication costs.

**Batch update size** usually refers to the number of update/write statements grouped into **a single JDBC `executeBatch()` call** or a batch group processed together by the framework/driver.

Suppose we need to transition 100,000 orders from `NEW` to `READY`. When executed sequentially:

```text
UPDATE orders SET status = 'READY' WHERE id = 1;
UPDATE orders SET status = 'READY' WHERE id = 2;
UPDATE orders SET status = 'READY' WHERE id = 3;
...
UPDATE orders SET status = 'READY' WHERE id = 100000;
```

The application may issue 100,000 independent executions. With JDBC batching, the application prepares one parameterized SQL template and binds multiple parameter sets:

```sql
UPDATE orders
SET status = ?
WHERE id = ?
```

```text
JDBC PreparedStatement
  addBatch("READY", 1)
  addBatch("READY", 2)
  addBatch("READY", 3)
  ...
  addBatch("READY", 200)
  executeBatch()

Repeat for subsequent batches.
```

If each group holds 200 items, 100,000 items produce roughly **500 batch groups** at the application layer. This does not strictly mean 500 network round-trips: how the driver and database pack, transmit, and execute batches depends on versions, protocols, and settings. Benchmark to know actual speed.

In Spring Batch, this topic sits at the intersection of **chunk processing**, **JDBC/JPA writers**, and **transaction management**. Never crank up a single parameter assuming performance will always improve.

## 2. Distinguishing Three Commonly Confused Sizes

In documentation or project configurations, "batch size" can refer to three distinct concepts:

| Concept | Configuration / Example | What It Controls |
|---|---|---|
| **Chunk size / commit interval** | `.chunk(500, transactionManager)` | Number of items Spring Batch processes in one chunk before a normal commit boundary |
| **JDBC batch update size** | `JdbcTemplate.batchUpdate(..., batchSize=100, ...)` | Maximum number of JDBC parameter sets per batch group created by this API |
| **Hibernate JDBC batch size** | `hibernate.jdbc.batch_size=50` | Number of compatible SQL operations Hibernate may group when flushing the persistence context |

The first two sizes **are not the same parameter**. For example:

```text
One Spring Batch chunk: 500 items
       |
       v
ItemWriter receives Chunk(500)
       |
       +--> JDBC executeBatch: 100 items
       +--> JDBC executeBatch: 100 items
       +--> JDBC executeBatch: 100 items
       +--> JDBC executeBatch: 100 items
       +--> JDBC executeBatch: 100 items
       |
       v
Commit chunk transaction
```

In this illustrative setup, **5 JDBC batch groups** execute within **the same single chunk transaction**. Having the driver execute five groups does not create five separate transactions.

If you use the standard `JdbcBatchItemWriter` and it receives a 500-item chunk directly, the writer invokes Spring JDBC's batch update mechanism for the chunk's items. `JdbcBatchItemWriter`'s builder API does not expose a separate `batchSize` option akin to `JdbcTemplate`'s chunking overload. To cap JDBC batches below the chunk size, implement a custom writer or choose an appropriate commit interval.

### Example Relationship Between Sizes

| Chunk Size | JDBC Update Size | JDBC Groups for a Full Chunk | Chunk Transactions* |
|---:|---:|---:|---:|
| 100 | 100 | 1 | 1 |
| 500 | 100 | 5 | 1 |
| 1,000 | 200 | 5 | 1 |
| 1,000 | 1,000 | 1 | 1 |
| 10 | 100 | 1 group of up to 10 items | 1 |

\* Assumes a chunk-oriented step with a proper transaction manager and a writer participating in the step's transaction. Retries, rollbacks, filtering, skips, or partial final chunks make actual behavior more complex.

This leads to a key question: are you trying to reduce **transaction count**, **SQL transmission overhead**, or **memory/lock pressure**? Each goal points toward a different size configuration.

## 3. Batch Updates in the Spring Batch Processing Flow

A typical chunk-oriented step:

```text
ItemReader
    |
    v
ItemProcessor       (can filter items by returning null)
    |
    v
[Retained chunk items]
    |
    v
ItemWriter          (batch UPDATE / INSERT / UPSERT)
    |
    v
Transaction commit
    |
    v
Checkpoint saves progress in JobRepository
```

Example:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step updateOrderStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderStatusChange> reader,
        ItemProcessor<OrderStatusChange, OrderStatusChange> processor,
        ItemWriter<OrderStatusChange> writer) {

    return new StepBuilder("updateOrderStep", jobRepository)
            .<OrderStatusChange, OrderStatusChange>chunk(
                    500, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

The snippet above uses the **Spring Batch 5.x** builder style with Java 17+. `OrderStatusChange` is an illustrative DTO defined in the next section.

Here, `chunk(500, transactionManager)` controls the commit interval. It does **not** set the JDBC batch size for every driver or Hibernate. If the writer does not batch, 500 sequential update calls can still occur inside the transaction.

Furthermore, if `ItemProcessor` filters out items or the step undergoes retries/skips, the writer may receive fewer than 500 items. Never assume every `write` call contains exactly the commit interval's worth of items.

## 4. Using `JdbcBatchItemWriter` for UPDATE Statements

`JdbcBatchItemWriter<T>` is Spring Batch's built-in writer for running batch SQL over input items. It fits well when all items share the same SQL template and each item supplies a different parameter set.

### 4.1. Input DTO

```java
public record OrderStatusChange(
        long id,
        String newStatus
) {
}
```

Sample data:

```text
OrderStatusChange(101, "READY")
OrderStatusChange(102, "READY")
OrderStatusChange(103, "CANCELLED")
```

### 4.2. Configuring the Writer

```java
import javax.sql.DataSource;

import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

@Bean
JdbcBatchItemWriter<OrderStatusChange> orderUpdateWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<OrderStatusChange>()
            .dataSource(dataSource)
            .sql("""
                UPDATE orders
                   SET status = :newStatus
                 WHERE id = :id
                """)
            .itemSqlParameterSourceProvider(item ->
                    new MapSqlParameterSource()
                            .addValue("newStatus", item.newStatus())
                            .addValue("id", item.id()))
            .assertUpdates(true)
            .build();
}
```

The writer receives a `Chunk` and uses Spring JDBC to execute the SQL with item parameters. `assertUpdates(true)` checks update results, catching cases where an item updated zero rows when the driver returns per-statement affected-row counts.

In business workflows where missing records are permissible, define an explicit policy instead of enabling assertions blindly. For example, "update if present" may treat 0 affected rows as acceptable. Conversely, if every item **must** match an existing order, 0 affected rows signals a data error that must be caught.

**Note:** Affected-row counts returned by JDBC may include `Statement.SUCCESS_NO_INFO`, meaning the driver reports success without knowing the exact row count per element. Do not write tests assuming every driver returns exact positive update counts.

### 4.3. What to Understand About Sizing with This Writer

With the writer above, the item group size seen by the writer is typically bounded by **chunk size**. For instance, a step with `chunk(500)` passes at most 500 post-filter items per normal `write` call. PreparedStatement SQL statements are batched across the items in the chunk.

If database constraints require sending groups of at most 100 items while still committing every 500-item chunk, implement a custom `ItemWriter` using the `JdbcTemplate.batchUpdate` overload with a `batchSize` parameter.

## 5. Limiting JDBC Batch Size Explicitly with `JdbcTemplate`

Spring JDBC provides this overload:

```java
int[][] batchUpdate(
    String sql,
    Collection<T> batchArgs,
    int batchSize,
    ParameterizedPreparedStatementSetter<T> pss
)
```

It splits a large collection into smaller batch groups. For example, a writer processing 500 items per chunk while capping each JDBC batch update at 100 items:

```java
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriter;
import org.springframework.jdbc.core.JdbcTemplate;

public final class SizedOrderUpdateWriter
        implements ItemWriter<OrderStatusChange> {

    private static final String UPDATE_SQL = """
            UPDATE orders
               SET status = ?
             WHERE id = ?
            """;

    private final JdbcTemplate jdbcTemplate;
    private final int jdbcBatchSize;

    public SizedOrderUpdateWriter(
            JdbcTemplate jdbcTemplate,
            int jdbcBatchSize) {

        if (jdbcBatchSize <= 0) {
            throw new IllegalArgumentException(
                    "jdbcBatchSize must be positive");
        }

        this.jdbcTemplate = jdbcTemplate;
        this.jdbcBatchSize = jdbcBatchSize;
    }

    @Override
    public void write(Chunk<? extends OrderStatusChange> chunk) {
        if (chunk.isEmpty()) {
            return;
        }

        List<OrderStatusChange> items =
                new ArrayList<>(chunk.getItems());

        jdbcTemplate.batchUpdate(
                UPDATE_SQL,
                items,
                jdbcBatchSize,
                (PreparedStatement statement,
                 OrderStatusChange item) -> {
                    statement.setString(1, item.newStatus());
                    statement.setLong(2, item.id());
                }
        );
    }
}
```

Bean declaration:

```java
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@Bean
ItemWriter<OrderStatusChange> sizedOrderUpdateWriter(
        JdbcTemplate jdbcTemplate) {

    return new SizedOrderUpdateWriter(
            jdbcTemplate,
            100 // JDBC batch update size
    );
}
```

When the step uses `chunk(500)`, a single writer invocation of 500 items produces five batches of up to 100 items each. As long as the JDBC writer shares the DataSource and transaction manager bound to the step's transaction, all batches still participate in the **chunk's transaction** rather than committing individually.

**Caveat for this example:** The writer executes SQL and lets Spring JDBC throw exceptions on batch failures. It does not handle 0-row update policies, optimistic locking, or auditing. If business rules require verifying that every item updated exactly one row, inspect the returned `int[][]` according to your JDBC driver's contract (including `SUCCESS_NO_INFO` and `EXECUTE_FAILED`), or use a writer with built-in verification.

### 5.1. Batch Update Does Not Mean a Single SQL Statement

`batchUpdate` processes multiple parameter sets for one SQL template. The driver may send multiple prepared commands or optimize the wire payload in driver-specific ways. This differs from a set-based SQL statement:

```sql
UPDATE orders
SET status = 'READY'
WHERE processing_date = :businessDate
  AND status = 'NEW';
```

Set-based SQL can update thousands of rows in a single statement, sometimes far faster than thousands of per-ID updates. However, it only fits when all matching rows follow one uniform condition; if each order has a different target status or per-item business validation, item-level batching is easier to control.

Benchmark both approaches against a real workload instead of assuming item batching is always optimal.

## 6. Choosing a Large vs. Small Batch Update Size

There is no universal optimal number across all databases, drivers, and datasets.

### 6.1. Small Batches

For example, `jdbcBatchSize=10`:

Advantages:

- Keeps parameter arrays, buffers, and memory low.
- Easier to isolate problematic groups when diagnosing failures.
- Bounds the size of each payload sent to the driver.
- Well suited for heavy SQL statements, wide rows, or resource-constrained systems.

Disadvantages:

- Requires more `executeBatch()` calls and repeated per-batch overhead.
- With high latency between app and database, throughput may suffer.
- CPU/driver overhead from managing many tiny batches.

### 6.2. Large Batches

For example, `jdbcBatchSize=1,000`:

Advantages:

- Reduces invocations across the JDBC layer.
- Improves parameter transmission and driver/database optimizations.
- Effective for repetitive, identical SQL templates with moderate payload sizes.

Disadvantages:

- Parameter buffers grow large, consuming more memory.
- On failure, pinpointing the offending item inside a large batch can be harder.
- The database may hold more locks and resources during execution.
- Some drivers impose limits on packet size, bind parameters, or batch length.
- An oversized batch increases single-call `executeBatch()` latency and can delay graceful job stops.

**Large chunk sizes** also lengthen transactions and increase rollback cost on error. **Large JDBC batch sizes** primarily affect batching at the JDBC layer; the two often correlate when a writer processes the whole chunk, yet they do not always scale identically.

### 6.3. Qualitative Comparison Table

| Size | Batch Calls | Parameter Memory | Responsiveness | When to Consider |
|---|---|---|---|---|
| 1 | Highest | Low | Short per statement | Comparison baseline |
| 20–50 | High | Low–moderate | Usually good | Large items, heavy SQL |
| 100–200 | Moderate | Moderate | Balanced | Common starting point for tuning |
| 500–1,000 | Low | Higher | Batches may take longer | Lightweight SQL, well-tuned DB/driver |
| Over 1,000 | Very low | Potentially very high | Risk of very long batches | Select only after benchmarking |

These ranges are **experimental starting points**, not mandatory limits or best practices. Test several sizes under representative load to find your sweet spot.

## 7. Impact of Transactions and Commit Intervals

This is the most critical aspect when increasing batch sizes in Spring Batch.

Suppose:

```text
Chunk size:       500 items
JDBC batch size:  100 items
Transaction:      JDBC transaction wrapping the chunk
```

The step executes:

```text
BEGIN TRANSACTION

  executeBatch(items 1..100)
  executeBatch(items 101..200)
  executeBatch(items 201..300)
  executeBatch(items 301..400)
  executeBatch(items 401..500)

COMMIT
```

If the fifth batch fails and the writer throws an exception, **the chunk transaction can roll back all updates in the chunk**, including the earlier `executeBatch` groups, provided they share the same transaction and the database supports rollback properly.

Conversely, if custom writer code opens a standalone connection with `autoCommit=true`, each batch commits before later errors are detected. Spring Batch's rollback and restart guarantees then break down.

### 7.1. Choosing the Right Transaction Manager

With Spring JDBC, ensure `JdbcTemplate` uses a DataSource enlisted in the transaction managed by the step's `PlatformTransactionManager`. In standard JDBC applications, this is `DataSourceTransactionManager` or the transaction manager auto-configured by Spring Boot.

Never pair a writer's DataSource with an unrelated transaction manager that does not manage its connections and expect JDBC rollbacks to work.

### 7.2. Increasing Chunk Size vs. Increasing JDBC Batch Size Yield Different Gains

| Change | Potential Reduction | Trade-Off to Evaluate |
|---|---|---|
| Chunk 100 → 1,000 | Fewer transactions, commits, and checkpoints | Longer transactions, locks, and larger rollbacks |
| JDBC batch 20 → 200 | Fewer JDBC batch submissions/round-trips | Larger buffers and longer batch calls |
| Increasing both together | Both transaction and batch overhead | Hard to tell which change helped or hurt |
| Increasing concurrency alone | Higher aggregate throughput | Connection/lock contention and deadlocks |

When tuning, change **one primary variable at a time** while holding the workload fixed so you know what actually drove the result.

## 8. Retries, Skips, and Batch Failures

A key risk of oversized batches is that when a single UPDATE fails, the entire group can report errors differently depending on the JDBC driver.

For example, a batch of three items:

```text
id=101 -> updated successfully
id=102 -> constraint / business rule violation
id=103 -> unclear whether driver continues or stops
```

JDBC may throw `BatchUpdateException` with `updateCounts`. However:

- Some drivers halt on the first failing item; others continue executing the remaining statements.
- Counts may report affected rows, `Statement.SUCCESS_NO_INFO`, or `EXECUTE_FAILED`.
- Statements reported as "executed" are not necessarily **committed**: the transaction may still roll back.
- After rollback, Spring Batch may retry the chunk or invoke item-level skipping per the fault-tolerant configuration.
- You cannot always map an exact index in `updateCounts` back to a specific input item if the driver reorders or batches statements.

Therefore, prioritize:

1. **Validating inputs before the writer** for errors detectable up front.
2. **Enforcing proper transaction boundaries** so partial batch failures never leave dirty partial writes behind.
3. **Idempotency** so retries and restarts never apply wrong updates or duplicate side effects.
4. **Sensible retry/skip limits** tested against your actual driver and database.
5. **Logging business identifiers for the group** or correlation IDs on error, without dumping sensitive payloads in bulk.

### 8.1. Illustrative Fault-Tolerance Configuration

```java
@Bean
Step updateOrderStepWithRetry(
        JobRepository repository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderStatusChange> reader,
        ItemWriter<OrderStatusChange> writer) {

    return new StepBuilder("updateOrderStepWithRetry", repository)
            .<OrderStatusChange, OrderStatusChange>chunk(
                    200, transactionManager)
            .reader(reader)
            .writer(writer)
            .faultTolerant()
            .retry(org.springframework.dao.DeadlockLoserDataAccessException.class)
            .retryLimit(3)
            .build();
}
```

This merely illustrates retrying a transient database access exception. Exception names/hierarchies may vary across Spring Framework versions, so pick exceptions actually observed from your driver and aligned with application policy. Never enable retries for all `Exception` types, as SQL syntax errors or invalid data will not resolve themselves on retry.

If you want to skip individual items when an update fails, verify carefully whether the writer can isolate the failing item and whether the driver reports accurate error positions. `faultTolerant()` does not magically turn every bulk SQL batch into safe item-level skipping.

### 8.2. Duplicate Item Updates Within a Chunk

A chunk might contain the same `id` multiple times:

```text
(id=101, status=READY)
(id=101, status=CANCELLED)
```

With `UPDATE ... WHERE id = ?`, the final persisted state depends on processing order. When the reader lacks deterministic ordering or execution is multi-threaded, outcomes can become non-deterministic.

Options depending on business rules:

- Ensure at most one update per entity ID within an execution.
- Use version columns / optimistic locking to detect concurrent updates.
- Deduplicate/order items before writing if order matters.
- Use explicit upsert or set-based operations with well-defined semantics.

Increasing batch size **does not solve update contention**; sometimes it prolongs lock duration instead.

## 9. Hibernate/JPA Batch Update Size

When a step uses JPA instead of `JdbcTemplate`, SQL batching depends on the ORM and persistence context.

Hibernate provides JDBC batching properties such as:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        jdbc:
          batch_size: 50
        order_updates: true
```

In this configuration:

- `hibernate.jdbc.batch_size=50` sets the batch threshold Hibernate uses for compatible statements.
- `hibernate.order_updates=true` lets Hibernate sort updates by entity type and primary key, which can improve batching and reduce certain deadlocks at the cost of sorting overhead.
- Actual batching depends on dirty checking, `flush` timing, entity mappings, generated SQL, and the JDBC driver.

**Spring Batch chunk size remains independent** of `hibernate.jdbc.batch_size`. For instance, `chunk(500)` paired with Hibernate JDBC batch 50 can emit multiple SQL groups upon flush.

### 9.1. `JpaItemWriter` and the Persistence Context

`JpaItemWriter` persists entities through the step's `EntityManager`, typically flushing on write with options for managing the persistence context. Keep in mind:

- Entity updates only emit SQL if Hibernate detects changes per its mappings and entity state.
- The persistence context retains entities and tracking metadata, so oversized chunks can consume heavy memory.
- Hibernate groups identical SQL templates; interleaved updates or varied statement shapes can break batching.
- Flushing too often defeats batching; retaining tens of thousands of entities in the persistence context is also suboptimal.
- Configuring JDBC batching does not replace inspecting SQL logs, slow queries, and actual statement counts.

When using `JpaPagingItemReader`, `JpaItemWriter`, or custom repositories, verify exact transaction and flush/clear mechanics for your framework version. Do not assume setting `hibernate.jdbc.batch_size` automatically optimizes every repository `save(...)` call.

### 9.2. Comparing JDBC and JPA

| Criterion | `JdbcBatchItemWriter` | `JpaItemWriter` / Hibernate |
|---|---|---|
| SQL generation | Hand-written SQL | ORM-generated SQL |
| Batch size | Primarily chunk-driven; customizable in JDBC | `hibernate.jdbc.batch_size` |
| Entity management | No JPA persistence context | Dirty checking, flushing, entity lifecycle |
| Update count control | Closer to raw JDBC | Depends on ORM and mappings |
| Best suited for | High-volume ETL/updates with clear SQL | Jobs needing domain entities and JPA logic |
| What to watch | Driver batching/round-trips, update counts | Flushes, memory, SQL grouping, N+1 queries |

For simple high-volume bulk updates, raw JDBC or a set-based `UPDATE` is worth benchmarking. For domains requiring cascades, versioning, and entity relationships, JPA can be a better fit provided SQL count and memory are kept under control.

## 10. Why Increasing Batch Size May Fail to Speed Things Up

### 10.1. Slow UPDATE SQL Due to Missing Indexes

Example:

```sql
UPDATE orders
   SET status = :status
 WHERE external_code = :externalCode;
```

If `external_code` lacks a proper index, every UPDATE may scan many rows. Batching 1,000 unindexed UPDATEs is no substitute for proper indexing and query plans.

Check:

- Is the lookup column properly indexed?
- Is the predicate selective and sargable?
- Are triggers, cascades, foreign keys, or audit hooks slowing updates?
- Are many rows locked or awaiting commit?
- Are large columns being touched unnecessarily?

### 10.2. Batches Containing Heterogeneous SQL

JDBC batching works best with a single statement template. If items generate varying SQL dynamically, drivers and ORMs struggle to group them.

Example:

```text
UPDATE orders SET status = ? WHERE id = ?
UPDATE orders SET status = ?, note = ? WHERE id = ?
UPDATE orders SET ship_date = ? WHERE id = ?
```

These are three distinct SQL shapes. If you can unify the SQL or group by mutation type while preserving exact semantics, batching efficiency improves.

### 10.3. Network and Driver Behavior

Some drivers offer batch optimization or SQL rewrite options, though effects vary by database and statement type. Settings that accelerate `INSERT` may not apply equally to `UPDATE`.

Never apply a driver flag from a blog post and claim speedup without measuring executed SQL counts, network traffic, latency, and throughput.

### 10.4. Database Locks and Transaction Logs

When multiple threads or partitions update overlapping ranges, large batches hold locks longer, raising deadlock and lock-wait risk. The database must also write redo/WAL/transaction logs; giant batches can turn log I/O into the bottleneck.

In these scenarios, shrinking batch/chunk sizes or refining partitioning can outperform enlarging them.

### 10.5. Connection Pools and Worker Counts

Suppose 16 workers share a connection pool capped at 8 active connections. Raising JDBC batch size from 100 to 1,000 will not eliminate pool wait contention. Instead, longer transactions per worker may increase pool wait times.

End-to-end tuning must look across the full stack:

```text
CPU / memory
    |
Spring Batch concurrency
    |
Connection pool
    |
JDBC driver
    |
Database connections / locks / WAL
    |
Storage I/O
```

## 11. Designing Benchmarks to Choose Batch Update Size

Tuning should rely on **a repeatable workload**. Build a sample dataset matching production in row width, key distribution, indexes, valid update ratio, and error rate.

Hold other factors constant within each benchmark sweep:

- Same database engine and driver version.
- Identical dataset, reset to an equivalent initial state before every run.
- Same chunk size while sweeping JDBC batch size.
- Same concurrency, connection pool, and transaction isolation.
- Same indexes, triggers, and database settings.
- Warm up and run multiple iterations to smooth out cache/JIT variance.
- Record throughput, latency, and error counts—not just total duration.

### 11.1. Illustrative Test Matrix

Suppose `chunkSize=500` is fixed; you might test:

| Run | JDBC Batch Size | Duration | Throughput | Notes |
|---|---:|---:|---:|---|
| A | 1 | Measure | Measure | Baseline |
| B | 20 | Measure | Measure | Test gains from small batching |
| C | 50 | Measure | Measure | Test intermediate size |
| D | 100 | Measure | Measure | Test 5 batches/chunk |
| E | 250 | Measure | Measure | Test 2 batches/chunk |
| F | 500 | Measure | Measure | Test 1 batch/chunk |

After identifying a promising JDBC batch size region, sweep chunk sizes `100`, `500`, and `1,000` using that batch size. Avoid changing both variables at once from the start, as it obscures cause and effect.

### 11.2. Metrics to Collect

| Metric | Meaning |
|---|---|
| `step duration` | Total elapsed time from step start to end |
| `items/sec` | Items completed per second |
| `writeCount` | Items recorded by the step's framework counter |
| `commitCount` | Commits during the step |
| `rollbackCount` | Rollback count |
| `executeBatch()` call count | Confirms whether JDBC groups actually decreased |
| Total / update SQL latency | Separates SQL bottlenecks from Java overhead |
| Lock waits / deadlocks | Checks if larger batches cause contention |
| CPU, heap, GC | Checks for memory pressure |
| DB transaction log / WAL | Checks for commit I/O bottlenecks |
| Connection wait / pool usage | Checks for connection pool bottlenecks |

**Note:** `StepExecution.getWriteCount()` reflects items processed by the writer according to the framework, **not necessarily total database rows UPDATED**. One SQL statement may affect 0, 1, or many rows; one item may emit multiple statements. If auditing actual modified rows, capture affected-row counts or run verification queries.

### 11.3. Example of Reading Results

Suppose a benchmark for **one specific application** produces hypothetical results:

| JDBC Batch Size | Time for 100,000 Updates | Updates/Second |
|---:|---:|---:|
| 1 | 180 s | ~556 |
| 50 | 70 s | ~1,429 |
| 100 | 58 s | ~1,724 |
| 250 | 55 s | ~1,818 |
| 500 | 61 s | ~1,639 |
| 1,000 | 83 s | ~1,205 |

These figures are **illustrative only** to demonstrate curve analysis, not real benchmark measurements. If this curve appeared in your system, `250` is a stronger candidate than `1,000`. Beyond a threshold, oversized batches make memory, locking, or per-batch latency counterproductive.

Never choose a size purely on throughput. If 250 is three seconds faster than 100 yet spikes `rollbackCount` or p95 latency, 100 may be safer operationally.

## 12. Measuring Performance in Spring Batch

Spring Batch 5.x integrates with Micrometer for job/step and stage metrics. Combine Spring Boot Actuator + an appropriate registry with `JobExplorer` to inspect specific executions.

Example Maven configuration:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-batch</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

The project also needs a JDBC driver and compatible DataSource; dependency versions are usually managed by the Spring Boot BOM.

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
```

Meters of interest once instrumentation is enabled include:

- `spring.batch.step`: Timer for step duration.
- `spring.batch.chunk.write`: writer duration for a chunk.
- `spring.batch.item.read`: item read duration.
- `spring.batch.item.process`: item process duration.
- `spring.batch.step.active`: tracks active steps if your version provides the corresponding `LongTaskTimer`.

Actual meter and tag names depend on framework version. Check `/actuator/metrics` or `/actuator/prometheus` before hardcoding queries. **Micrometer step/chunk timers alone do not report exact JDBC `executeBatch()` counts**; to count JDBC batches, add writer instrumentation or observe at the JDBC/driver layer.

### 12.1. Timing Individual Write Calls

Example creating a custom Timer specifically for writer invocations:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriter;

public final class TimedWriter<T> implements ItemWriter<T> {

    private final ItemWriter<T> delegate;
    private final MeterRegistry registry;

    public TimedWriter(ItemWriter<T> delegate, MeterRegistry registry) {
        this.delegate = delegate;
        this.registry = registry;
    }

    @Override
    public void write(Chunk<? extends T> chunk) throws Exception {
        Timer.Sample sample = Timer.start(registry);

        try {
            delegate.write(chunk);
        } finally {
            sample.stop(
                    Timer.builder("custom.batch.writer.duration")
                            .tag("writer", "orderUpdate")
                            .register(registry)
            );
        }
    }
}
```

This metric captures **writer invocation duration**, encompassing both Java and JDBC execution—not solely network or database SQL time. Combine it with JDBC/DB telemetry for finer SQL breakdown.

Do not use `orderId`, `jobExecutionId`, or `chunkIndex` as metric tags: they cause unbounded cardinality growth. Keep those in structured logs or traces when tracing specific runs.

## 13. Testing Writers and Transactions

### 13.1. Unit Tests Without a Database

For a custom writer, unit tests can verify that it passes the expected `batchSize`, SQL, and parameters to `JdbcTemplate`. However, mocking `JdbcTemplate` **does not prove the database batches or rolls back properly**.

For example, validating that the constructor rejects invalid batch sizes:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;

import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

class SizedOrderUpdateWriterTest {

    @Test
    void rejectsZeroBatchSize() {
        JdbcTemplate template = mock(JdbcTemplate.class);

        assertThrows(
                IllegalArgumentException.class,
                () -> new SizedOrderUpdateWriter(template, 0)
        );
    }
}
```

This test is useful for guarding input validation; actual write/commit behavior requires integration tests.

### 13.2. Database Integration Tests

Depending on project setup, use `@SpringJdbcTest` or `@JdbcTest`; in Spring Boot, `@JdbcTest` provides a lean JDBC context for running SQL against a test database.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.item.Chunk;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;

@JdbcTest
class SizedOrderUpdateWriterJdbcTest {

    @Autowired
    JdbcTemplate jdbcTemplate;

    @BeforeEach
    void setUp() {
        jdbcTemplate.execute("DROP TABLE IF EXISTS orders");
        jdbcTemplate.execute("""
            CREATE TABLE orders (
                id BIGINT PRIMARY KEY,
                status VARCHAR(32) NOT NULL
            )
            """);
        jdbcTemplate.update(
                "INSERT INTO orders(id, status) VALUES (?, ?)",
                101L, "NEW"
        );
        jdbcTemplate.update(
                "INSERT INTO orders(id, status) VALUES (?, ?)",
                102L, "NEW"
        );
        jdbcTemplate.update(
                "INSERT INTO orders(id, status) VALUES (?, ?)",
                103L, "NEW"
        );
    }

    @Test
    void updatesItemsAcrossMultipleJdbcBatches() {
        SizedOrderUpdateWriter writer =
                new SizedOrderUpdateWriter(jdbcTemplate, 2);

        writer.write(new Chunk<>(List.of(
                new OrderStatusChange(101L, "READY"),
                new OrderStatusChange(102L, "READY"),
                new OrderStatusChange(103L, "CANCELLED")
        )));

        assertEquals("READY", jdbcTemplate.queryForObject(
                "SELECT status FROM orders WHERE id = 101",
                String.class
        ));
        assertEquals("READY", jdbcTemplate.queryForObject(
                "SELECT status FROM orders WHERE id = 102",
                String.class
        ));
        assertEquals("CANCELLED", jdbcTemplate.queryForObject(
                "SELECT status FROM orders WHERE id = 103",
                String.class
        ));
    }
}
```

This test proves the writer updates rows correctly across multiple JDBC batches, **not the exact number of network round-trips**. To verify rollback when a later batch fails, inject an error inside a transactional test and inspect database state after rollback using your production transaction manager and DB engine.

Real databases such as PostgreSQL, SQL Server, and MySQL differ from H2 in batching limits and update counts. Deadlocks, packet limits, and query plans should be tested on at least a production-equivalent environment.

### 13.3. Testing Inside a Real Step

Using `spring-batch-test`, `JobLauncherTestUtils.launchStep("updateOrderStep")`, and a test DataSource, verify:

- The Step ends `COMPLETED` on valid input.
- `StepExecution` read/write counts match expectations.
- Database rows reach the expected final state.
- When the writer fails mid-chunk, uncommitted changes are rolled back cleanly.
- Restarting from the saved checkpoint causes no bad updates or duplicate external side effects.

If you only care about SQL parameter mapping, a focused writer integration test suffices. To verify commit intervals, retries, skips, and restarts in Spring Batch, run the real Step rather than calling `writer.write(...)` directly.

## 14. Batch Size in Concurrent Environments

When a step uses multiple threads or partitions, batch size impacts are multiplied by concurrency.

Suppose:

```text
4 worker threads
each worker processes chunk 500
each chunk split into JDBC batch 100
```

Multiple transactions and batch groups compete for database resources simultaneously. If workers update the same `orders` table, watch indexes, locks, ID ordering, and connection pool capacity.

A sound tuning sequence:

1. Establish baseline throughput with **1 worker**.
2. Pick a stable chunk and JDBC batch size region.
3. Scale workers from 1 to 2, 4, 8, etc., within infrastructure limits.
4. Track connection waits, lock waits, deadlocks, CPU, and throughput.
5. Stop raising concurrency once contention costs outweigh gains.

Never treat `8 workers × batch 500` as a single "batch size 4,000" transaction. They are separate threads and transactions, each with its own lifecycle and failure modes.

### Key-Range Partitioning

If partitioning by ID range or business date, workers should operate on **disjoint** datasets. This prevents two transactions from fighting over the same row. However, skewed partitions can leave one worker handling 90% of the work while others sit idle.

Batch update size tuning must go hand-in-hand with balanced partitioning and locking; enlarging batches inside an overloaded partition will not fix data skew.

## 15. Practical Tuning Workflow

Scenario: a nightly job updating 2 million records takes 80 minutes, whereas the SLA allows 45 minutes.

**Step 1 — Measure baseline.** Record `stepDuration`, `readCount`, `writeCount`, chunk size, actual statement/batch counts, update latency, and database CPU/locks.

**Step 2 — Locate the bottleneck.** If the reader is slowest, changing the writer's JDBC batch update size will barely help. If the writer is slowed by network latency and tiny updates, batching holds high potential.

**Step 3 — Sweep JDBC batch size.** Hold chunk size, concurrency, and dataset constant. Compare 20, 50, 100, 200, and 500; do not jump straight to 10,000.

**Step 4 — Sweep chunk size.** If transaction/commit count is excessive, test larger commit intervals while watching locks, rollback cost, and memory.

**Step 5 — Inspect SQL.** If individual updates are slow due to missing indexes or triggers, fixing SQL/schema often beats raising batch size.

**Step 6 — Test failures.** Intentionally trigger a constraint violation, and verify rollback, restart, and idempotency under the target configuration.

**Step 7 — Re-benchmark under real concurrency.** Single-worker gains may not transfer to 8 workers, especially on a shared hot table.

**Step 8 — Monitor in production.** Compare duration, throughput, `rollbackCount`, DB lock waits, CPU, memory, and errors against baseline; keep tuning knobs configurable as workloads evolve.

### Common Anti-Patterns

| Anti-Pattern | Why It Is Problematic | Remediation |
|---|---|---|
| Assuming `chunk(1000)` sets every JDBC driver's batch size to 1000 | Chunk only defines the processing/commit boundary | Verify actual writer and batching behavior |
| Always cranking size as high as possible | Memory, locks, packet limits, and rollbacks can worsen | Benchmark against your real workload |
| Calling `JdbcTemplate.update` in a loop expecting batching | Each `update` is an independent call | Use `batchUpdate` / `JdbcBatchItemWriter` |
| Manually committing per JDBC batch inside the writer | Breaks the step's transaction boundary | Let the step's transaction manager govern commits |
| Mocking everything and claiming DB batching works | Mocks do not exercise SQL, drivers, or transactions | Run real integration tests and benchmarks |
| Using `writeCount` to count affected DB rows | It counts items, not SQL `UPDATE` row counts | Inspect update counts or query target data |
| Ignoring drivers returning `SUCCESS_NO_INFO` | Causes misinterpretation of update counts | Handle results per the JDBC contract |
| Skipping rollback tests when the last batch fails | Risks leaving partially applied data behind | Test transactions and restarts |
| Batching duplicate IDs without deterministic ordering | Final row state becomes non-deterministic | Deduplicate or enforce versioning |
| Increasing chunk, batch, and thread counts together | Obscures which change helped or broke things | Adjust one primary variable at a time |
| Raising batch size when SQL lacks an index | Database remains the bottleneck | Inspect query plans and indexes |
| Using a tiny toy benchmark | Misses GC, cache, lock, and WAL behavior | Use a realistic dataset and multiple runs |

## 16. Practice Exercises

You have a job `syncCustomerStatus` reading 500,000 customer status changes from a file and updating the `customer` table in PostgreSQL. Business rules require each change to be applied accurately by `customer_id` and the job to be safely restartable.

Complete the following tasks:

1. Implement an `ItemReader<CustomerChange>` and a writer using `JdbcBatchItemWriter`. Set chunk size = 500.
2. Create an alternative writer using `JdbcTemplate.batchUpdate(..., batchSize=100, ...)` to split a chunk into JDBC batches of at most 100 items.
3. Prepare a fixed 500,000-item dataset with 99% valid updates and 1% non-existent IDs. Define an explicit policy for 0 affected rows.
4. Compare batch sizes 1, 20, 50, 100, 250, and 500 on the same dataset; record duration, throughput, memory, lock waits, and batch call counts.
5. Hold JDBC batch size = 100 and compare chunk sizes 100, 500, and 1,000. Explain why transaction/commit counts change.
6. Simulate a constraint violation inside the third batch; inspect the entire chunk's data after rollback.
7. Intentionally stop the job and then restart it; verify no wrong updates or duplicate non-DB side effects occur.
8. Run two workers updating disjoint customer ID sets, then overlapping ID sets. Observe lock waits/deadlocks and explain the cause.
9. Identify a scenario where thousands of per-item updates can be replaced with a single set-based `UPDATE ... WHERE ...`. Compare semantics and performance.
10. Based on your measurements, recommend `chunkSize` and `jdbcBatchSize` for your environment with evidence justifying why they outperform alternatives.

**Review question:** If a step uses `chunk(500)` and the writer splits into `jdbcBatchSize = 100`, when the fifth batch fails, are the first four batches already committed?

**Answer:** No. With a proper JDBC transaction wrapping the chunk, those batches were only **executed inside the transaction**; upon rollback, all uncommitted changes in the chunk are undone. This relies on the writer actually participating in the same transaction and the database supporting rollback for those operations.

## 17. References

- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): how chunks, commit intervals, and step transactions work.
- [Spring Batch Reference — Database Item Readers and Writers](https://docs.spring.io/spring-batch/reference/readers-and-writers/database.html): `JdbcBatchItemWriter` and database writer options.
- [Spring Framework JDBC — Batch Operations](https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html#jdbc-batch): `JdbcTemplate.batchUpdate` and sized batching.
- [Spring Batch Reference — Retry and Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html): chunk error-handling policies.
- [Hibernate User Guide — JDBC Batching](https://docs.jboss.org/hibernate/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#batch): `hibernate.jdbc.batch_size` and ordered updates.
- [Spring Batch Reference — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): tracking step and chunk durations.
- [JDBC API — BatchUpdateException](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/BatchUpdateException.html): handling JDBC batch errors and `updateCounts`.
