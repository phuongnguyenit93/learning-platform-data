# Choosing Cursor vs. Paging in Spring Batch

## 1. The Problem and Decision Goal

A Spring Batch job might read a table containing millions of orders and process each record through an `ItemProcessor` and `ItemWriter`. When designing an `ItemReader` for a JDBC source, the two common choices are **cursor** and **paging**. Both avoid loading the entire dataset into a Java list up front, but they differ in how they interact with the database, resource usage, stability when data mutates, performance, and restartability.

If the wrong choice is made, the job can exhibit symptoms such as:

- The cursor closes due to a timeout or the JDBC connection dropping after a long duration.
- Paging queries degrade progressively, the database repeats heavy work, or records are skipped/duplicated when source data changes.
- Heap grows because `fetchSize`/`pageSize` is set too high, or because the writer retains every item.
- Restarting from a checkpoint reads the wrong records because query ordering shifted.
- Adding more workers does not increase throughput due to source contention or a non-thread-safe reader.

This lesson belongs to the **Design Decisions** section of **Spring Batch Core Processing**. The goal is not to claim that cursor or paging is always faster, but to **know the evidence-based criteria for choosing** based on data source traits, transactions, volume, restart requirements, and infrastructure.

After this lesson, you will be able to:

1. Explain the mechanics of `JdbcCursorItemReader` and `JdbcPagingItemReader`.
2. Distinguish a JDBC cursor from SQL `OFFSET/LIMIT` pagination, keyset pagination, and API cursor tokens.
3. Evaluate memory, connections, query count, transactions, and source data mutations.
4. Configure each reader with Spring Batch 5.x, using business date parameters and stable read ordering.
5. Protect restarts from mutating data, plan partitioning, and design idempotency.
6. Measure performance with Batch metadata, database metrics, and controlled experiments.
7. Use a decision matrix to pick the right reader for each scenario.

Examples use Java 17+, Spring Boot 3.x, Spring Batch 5.x, JDBC, and PostgreSQL. SQL, cursor mechanisms, and transactions can vary across drivers and databases; verify against your real target system before going to production.

## 2. How Do Cursor and Paging Actually Read Data?

### 2.1. Cursor: One Query, Sequential Reads Over a ResultSet

A cursor-based reader opens a single query, obtains a `ResultSet`, and calls `next()` to pull one record at a time. The driver may fetch rows from the server in batches depending on fetch size, connection settings, and database cursor support.

```text
                   Database
                      |
      SELECT ... WHERE ... ORDER BY ...
                      |
                      v
               JDBC ResultSet
               cursor stays open
                      |
           fetch in batches from DB
                      |
                      v
              JdbcCursorItemReader
                   read()
                      |
                      v
             Processor -> Writer
                   chunk N
                      |
                 COMMIT chunk
                      |
                      v
        Continue reading existing ResultSet
```

Key trait: typically **one primary query** serves the entire scan, with the cursor/result set remaining active across multiple chunks. Rows already received over JDBC may still be buffered depending on the driver.

**Using a class named CursorItemReader does not guarantee the database streams row by row.** The driver can buffer most or all of the `ResultSet` if fetch size, auto-commit, or cursor mode is not configured properly. Measure heap, network traffic, and actual driver behavior.

### 2.2. Paging: Multiple Queries, Fetching One Page at a Time

A paging reader executes queries that fetch a batch of records and map them into items; once the current page is consumed, it executes the next query.

```text
Database: sales_order
         |
         +-- Page 1: 500 rows ----+
         |                        |
         +-- Page 2: 500 rows ----+--> JdbcPagingItemReader
         |                        |            |
         +-- Page 3: 500 rows ----+            v
         |                               read() each item
         +-- ...                               |
                                            Chunk -> Writer
```

Key trait: a long-lived database cursor is not the primary mechanism; instead, there are **multiple per-page queries**. Spring Batch uses `PagingQueryProvider` to generate database-specific SQL and requires a **stable, unique sort key**.

Paging does not automatically guarantee consistency when data is changing. If the table mutates between page queries, each query's results may observe a different slice of data depending on isolation, sort keys, and filter predicates.

### 2.3. Brief Comparison

| Aspect | Cursor | Paging |
| --- | --- | --- |
| Access pattern | One result set read sequentially | Multiple queries fetching page by page |
| DB connection | Usually holds connection/result set until step end | Connection used per page fetch; can return to pool between queries |
| Query round-trips | Usually fewer | More, roughly equal to number of pages |
| Buffering mechanism | JDBC fetch/driver buffer | Page buffer plus items in chunk |
| Ordering | `ORDER BY` helps stabilize order and restarts | Sort key is essential for accurate paging |
| Resilience to connection timeouts | Vulnerable when cursors run long and connections drop | Each page query is fairly independent, though overall run can still fail |
| Data changing during reads | Depends on transaction/isolation/cursor semantics | Pages may observe different snapshots |
| Restart | Typically reopens query and restores position via saved state | Restores position/page via state and sort key |
| Parallelism | A single cursor is inherently sequential | Pairs well with key-range partitioning; a single reader is still not thread-safe by default |

**Do not decide based on slogans like "cursor is always faster" or "paging is always safer."** Concrete behavior depends on the driver, query, indexes, transactions, and data churn.

## 3. JDBC Cursor vs. API Cursor and SQL OFFSET

The word "cursor" can refer to several distinct concepts:

- **JDBC cursor:** an open `ResultSet` through which rows are streamed over a database connection.
- **API cursor token:** a server-returned token for the next request, e.g., `nextCursor=abc123`. This is API pagination and does not necessarily hold a long-lived JDBC `ResultSet`.
- **Keyset pagination:** querying the next page based on the previous page's last key value, e.g., `WHERE order_id > :lastId`.
- **Offset pagination:** skipping N rows and fetching the next page, e.g., `OFFSET 500000 LIMIT 500`.

The two SQL pagination approaches behave differently:

```sql
-- OFFSET: rows prior to the offset position may still
-- incur heavy scan/sort/skip cost.
SELECT order_id, amount
FROM sales_order
WHERE business_date = DATE '2026-11-15'
ORDER BY order_id
LIMIT 500 OFFSET 100000;
```

```sql
-- Keyset: continue after the last processed key.
SELECT order_id, amount
FROM sales_order
WHERE business_date = DATE '2026-11-15'
  AND order_id > 100500
ORDER BY order_id
LIMIT 500;
```

With an appropriate index, keyset pagination usually avoids the cost of scanning and discarding hundreds of thousands of rows incurred by offset. Yet keyset still does not guarantee an immutable snapshot if records are inserted, deleted, or updated in ways that alter filter matches during reading.

**With `JdbcPagingItemReader`**, to let the framework generate queries and manage state per database dialect, you configure sort keys via `sortKeys`. The generated SQL and page-reading mechanics depend on the `PagingQueryProvider`/dialect; do not reduce every implementation to a single hand-written `LIMIT OFFSET` template. Spring Batch uses the sort key to determine the resume point for paging/restart.

## 4. Primary Selection Criteria

Before writing code, answer these questions:

| Question | If the answer is... | Direction to consider |
| --- | --- | --- |
| Can data be read sequentially via one stable query? | Yes, low churn | Cursor is worth considering |
| Can a connection stay open for minutes/hours? | No; proxy/pool has timeouts | Prefer considering paging |
| Does the table have a unique key for sorting? | Yes, with matching index | Paging has a solid foundation |
| Is the query complex with expensive joins/sorts per page? | Yes | Cursor can avoid repeating query cost |
| Need independent partitions by key range? | Yes | Key-range paging is usually convenient |
| Is data undergoing continuous INSERT/UPDATE/DELETE? | Yes | Snapshot/watermark matters more than reader choice |
| Must restart be exact with zero lost/duplicate items? | Yes | Requires stable source, checkpoints, and idempotent writer for both |
| Does the driver genuinely stream the ResultSet? | Unclear | Test before committing to cursor |
| Is the result set small? | A few thousand rows | Both work well; prioritize simplicity and maintainability |
| Is container memory tightly constrained? | Yes | Cap fetch/page/chunk sizes and measure retained heap for both |

A practical decision always covers **reader + configuration + data consistency policy + restart plan**, not just a class name.

## 5. Shared Data Example

Suppose we need to process orders by `businessDate`:

```sql
CREATE TABLE sales_order (
    order_id BIGINT PRIMARY KEY,
    business_date DATE NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    status VARCHAR(30) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_sales_order_date_id
    ON sales_order (business_date, order_id);
```

We need to read records for November 15, 2026 in ascending `order_id` order, then write aggregated output to a target system.

Use the item model:

```java
import java.math.BigDecimal;
import java.time.LocalDate;

public record OrderRow(
        long orderId,
        LocalDate businessDate,
        BigDecimal amount) {
}
```

Both cursor and paging will map to the same item type. The table has `order_id` as its primary key, giving a unique sort key within the target business date.

In practice, filter predicates may involve multiple columns such as `status='READY'` and `tenant_id`. If those columns can mutate while the job runs, you need a snapshot rule or state-transition strategy so items are never missed.

## 6. Configuring JdbcCursorItemReader in Spring Batch 5.x

Example cursor reader configuration using the builder and `@StepScope`:

```java
import java.sql.Date;
import java.time.LocalDate;

import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CursorReaderConfiguration {

    @Bean("ordersCursorReader")
    @StepScope
    JdbcCursorItemReader<OrderRow> ordersCursorReader(
            DataSource dataSource,
            @Value("#{jobParameters['businessDate']}")
                String businessDate) {

        LocalDate date = LocalDate.parse(businessDate);

        return new JdbcCursorItemReaderBuilder<OrderRow>()
            .name("ordersCursorReader")
            .dataSource(dataSource)
            .sql("""
                 SELECT order_id, business_date, amount
                 FROM sales_order
                 WHERE business_date = ?
                 ORDER BY order_id
                 """)
            .preparedStatementSetter(
                ps -> ps.setDate(1, Date.valueOf(date))
            )
            .rowMapper((rs, rowNum) -> new OrderRow(
                rs.getLong("order_id"),
                rs.getDate("business_date").toLocalDate(),
                rs.getBigDecimal("amount")
            ))
            .fetchSize(500)
            .saveState(true)
            .build();
    }
}
```

Meaning of the options:

- `name("ordersCursorReader")` establishes a stable name for state management in `ExecutionContext`.
- `@StepScope` resolves `businessDate` when the step executes, avoiding fixing the processing date at application startup.
- `preparedStatementSetter` binds SQL parameters via JDBC rather than concatenating user strings into SQL.
- `ORDER BY order_id` keeps result ordering predictable within a given data snapshot.
- `fetchSize(500)` hints the driver to fetch rows in batches; it does **not** guarantee the entire result set occupies only 500 objects.
- `saveState(true)` allows the reader to persist read progress for restarts via Spring Batch's mechanism.

### Cursor and Transactions

`JdbcCursorItemReader` typically uses a separate connection for the cursor, distinct from the connection the step uses to commit chunks. This lets the cursor keep reading across multiple step transactions. However, it also means **writer transaction commits do not automatically govern the cursor's snapshot or lifetime**.

In specialized cases, Spring Batch offers `useSharedExtendedConnection` with `ExtendedConnectionDataSourceProxy` and drivers supporting holdable cursors across commits. This is an advanced setting; never enable it purely as an "optimization" without thoroughly understanding your driver and transaction manager.

**Point to verify in your real environment:** The PostgreSQL driver has specific auto-commit and `fetchSize` requirements to switch to batched fetching. Other JDBC drivers have their own conditions. Never claim a reader is streaming just because `fetchSize(500)` is set.

## 7. Configuring JdbcPagingItemReader in Spring Batch 5.x

A paging reader uses `selectClause`, `fromClause`, `whereClause`, `sortKeys`, and `parameterValues`. Spring Batch picks database-appropriate SQL generation:

```java
import java.sql.Date;
import java.time.LocalDate;
import java.util.LinkedHashMap;
import java.util.Map;

import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcPagingItemReader;
import org.springframework.batch.item.database.Order;
import org.springframework.batch.item.database.builder.JdbcPagingItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PagingReaderConfiguration {

    @Bean("ordersPagingReader")
    @StepScope
    JdbcPagingItemReader<OrderRow> ordersPagingReader(
            DataSource dataSource,
            @Value("#{jobParameters['businessDate']}")
                String businessDate) {

        LocalDate date = LocalDate.parse(businessDate);

        Map<String, Order> sortKeys = new LinkedHashMap<>();
        sortKeys.put("order_id", Order.ASCENDING);

        return new JdbcPagingItemReaderBuilder<OrderRow>()
            .name("ordersPagingReader")
            .dataSource(dataSource)
            .selectClause("""
                SELECT order_id, business_date, amount
                """)
            .fromClause("FROM sales_order")
            .whereClause("WHERE business_date = :businessDate")
            .parameterValues(
                Map.of("businessDate", Date.valueOf(date))
            )
            .sortKeys(sortKeys)
            .rowMapper((rs, rowNum) -> new OrderRow(
                rs.getLong("order_id"),
                rs.getDate("business_date").toLocalDate(),
                rs.getBigDecimal("amount")
            ))
            .pageSize(500)
            .saveState(true)
            .build();
    }
}
```

Key takeaways:

- `sortKeys` is a critical requirement. In this example, `order_id` is unique so it works as the sort key.
- `pageSize(500)` sets the query page size; it is **not the step's chunk size**.
- `parameterValues` passes `businessDate` to the query as a named parameter.
- `saveState(true)` allows the reader to save its position for restart.
- The final SQL is generated by the dialect-specific paging query provider; the example does not hand-write an incrementing `OFFSET`.

To support indexing:

```sql
CREATE INDEX idx_sales_order_date_id
    ON sales_order (business_date, order_id);
```

An index on `(business_date, order_id)` can support filtering by date and scanning by order ID, though actual benefit depends on selectivity, data volume, query planner choices, table partitioning, and database statistics. Run `EXPLAIN (ANALYZE, BUFFERS)` in a test environment with representative data.

## 8. Configuring a Chunk Step with the Chosen Reader

Both readers implement `ItemStreamReader<OrderRow>` and fit a chunk-oriented step. You can use separate profiles or a configuration property to pick the reader, but **do not inject both into the same step without disambiguation**.

Example step using the cursor reader:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean("processOrdersCursorStep")
Step processOrdersCursorStep(
        JobRepository repository,
        PlatformTransactionManager transactionManager,
        @Qualifier("ordersCursorReader")
            JdbcCursorItemReader<OrderRow> reader,
        ItemProcessor<OrderRow, OrderRow> processor,
        ItemWriter<OrderRow> writer) {

    return new StepBuilder("processOrdersCursorStep", repository)
        .<OrderRow, OrderRow>chunk(200, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
}
```

For paging, swap in `JdbcPagingItemReader<OrderRow>` and give the step an appropriate name. Your project's configuration structure must ensure scoped proxies are injected properly; the snippet above only shows wiring and assumes processor and writer beans are already declared.

**Chunk size 200** and **fetch/page size 500** do not have to match. The ideal ratio depends on:

- Rows/result sets fetched from the database in one I/O round-trip.
- Items accumulated in a chunk before invoking the writer.
- Rollback scope and commit cost.
- Item memory footprint and writer-side buffering.
- Database latency and batch write efficiency.

Only controlled experiments reveal the best combination; there is no rule that "`pageSize` must always equal `chunkSize`."

## 9. When Is Cursor Usually the Reasonable Choice?

Cursor is worth considering when:

1. The job is a long sequential scan over a stable source.
2. The database/driver supports ResultSet streaming effectively without buffering the entire dataset.
3. Holding a cursor/connection for the job duration is acceptable.
4. The query is complex or compute-heavy, making re-execution per page expensive.
5. Multiple workers do not need to contend over a single cursor.
6. Restartability is verified against stable snapshot data.

### Example: End-of-Day Reporting on a Snapshot

The `daily_sales_snapshot` table finishes building at 01:00 and is locked, then the job scans sequentially at 01:15. The snapshot has 3 million rows indexed by a unique key. If the driver supports batched fetching, a cursor avoids repeated query overhead and keeps processing simple.

Still, "snapshot" here must be an actual data guarantee, not merely a table name. If rows can still be modified while the job runs, both the cursor and restart mechanism must be re-evaluated.

### Risks of Long-Lived Cursors

- Database connection remains occupied for an extended period.
- Connection pool runs low on slots for other workloads.
- Proxies, load balancers, or firewalls impose idle or lifetime timeouts.
- ResultSet closes if transactions or connections reset.
- Query holds DB resources or snapshots longer than expected.
- If the connection drops, the job must fail and restart; an old `ResultSet` cannot be reused on a new connection.

If the job runs for several hours or the database enforces strict timeouts, paging can be easier to operate.

## 10. When Is Paging Usually the Reasonable Choice?

Paging is worth considering when:

1. A unique sort key and efficient pagination index exist.
2. You do not want a single cursor/result set open across a long-running job.
3. You need to split data by ID/time/tenant ranges for partitioning.
4. Executing multiple page queries is acceptable to the source system.
5. You can pin a snapshot/watermark or enforce clear consistency rules.
6. You want to tune page size and measure database load in discrete bursts.

### Example: Reading from an Operational Table

A job processes orders within a fixed `order_id` range, fetching pages of 500 rows along a unique key. Each page is indexed and connections do not stay pinned to one cursor for the entire job. This manages resources better on long workloads with multiple independent partitions.

**This does not mean paging is automatically safe when data mutates.** If records are sorted by business key while a row's `READY` status changes mid-read, subsequent page queries can observe a shifted dataset. You still need snapshots or work-claiming design.

### Is Paging Always Faster?

No. Each page query may repeat JOINs, filters, sorts, index lookups, and network round-trips. If `pageSize` is small relative to the dataset, query count explodes. If the query provider or driver yields a poor execution plan, paging can be substantially slower than a cursor.

Conversely, a "single query" cursor can still suffer driver-side buffering, hold server resources too long, and hit timeouts, yielding poor real-world throughput. Always measure.

## 11. Mutating Source Data: More Important Than Raw Speed

Suppose a table is read in `order_id` order while another transaction inserts, deletes, or updates records concurrently.

### 11.1. Offset Pagination Can Skip or Duplicate

Initially:

```text
order_id: 10 20 30 40 50 60
pageSize=3

Page 1: 10 20 30
```

After Page 1, record `15` is inserted. If Page 2 uses `OFFSET 3`:

```text
order_id: 10 15 20 30 40 50 60
Page 2 OFFSET 3: 30 40 50
```

Record `30` is read twice. If a record before the offset is deleted, a record can be skipped entirely.

### 11.2. Keyset Avoids Offset Drift but Does Not Guarantee a Snapshot

If the next page uses:

```sql
WHERE order_id > :lastOrderId
ORDER BY order_id
```

with `lastOrderId=30`, inserting record `15` does not cause Page 2 to re-read `30`. That is keyset's advantage.

However, if a new record with ID `35` is inserted after Page 1, it may appear in the next page; if the job was supposed to process **the exact snapshot at job start**, that record is out of scope. If an unread record is deleted or changes status, it can vanish from subsequent queries.

Hence keyset eliminates one class of offset-shift bugs, **but does not replace snapshot isolation or an immutable source**.

### 11.3. Cursor Also Requires Examining Transaction Isolation

An open cursor may observe different row sets depending on the database and isolation level; some setups provide relatively stable query snapshots, but you should never assume a cursor on every driver captures an immutable point-in-time snapshot at job start.

Also distinguish:

- **Intra-execution consistency:** what concurrent changes can a query/cursor see?
- **Cross-restart consistency:** will a new query on a new connection see the exact same rows and order?

Even if the initial run enjoyed a stable snapshot transaction, **a restart after a crash opens a new query and transaction**. If the source changed in the meantime, position checkpoints may no longer align with the same rows.

## 12. Strategies to Ensure a Stable Dataset

Common design patterns:

### 12.1. Snapshot Table or File Before Processing

Build a snapshot table keyed by `snapshot_id` or export immutable source files. The job uses identifying parameters such as `snapshotId` and reads exclusively from that dataset.

```text
Operational tables
       |
       v
Create snapshot S123
       |
       +--> Snapshot sealed / immutable
       |
       v
Spring Batch job (snapshotId=S123)
       |
       +--> cursor or paging
       |
       v
Output / audit
```

Pros: deterministic restarts and testing, operational source unaffected during processing. Cost: extra snapshot step, disk storage, and preparation time.

### 12.2. High-Water Mark

Lock an upper bound before the job starts:

```sql
SELECT MAX(order_id)
FROM sales_order
WHERE business_date = DATE '2026-11-15';
```

Then add `order_id <= :highWaterMark` to all queries. Persist the high-water mark in `JobParameters` or durable metadata so **restarts reuse the exact initial value**.

This prevents picking up rows with newly generated IDs above the watermark. However, it does not guard against UPDATEs/DELETEs on rows below the watermark, or INSERTs with IDs below it. Thus it only works when business rules guarantee monotonic IDs/data and stable filter columns.

### 12.3. Claiming and Processing Status

For database-backed work queues, **claiming** is often better: transition rows from `READY` to `IN_PROGRESS` via transaction/locking, or assign by partition. The system must define leases, timeouts, retries, and abandonment recovery.

This is no longer purely a cursor-vs-paging question; it is a work-distribution problem. If a job reads and updates the very column it filters on—such as `WHERE status='READY'`—be careful with paging. Processed rows drop out of the result set and can break position-based logic.

### 12.4. Locking the Source by Version

Record `sourceVersion`, `sourceChecksum`, or snapshot code alongside `businessDate`. Before restarting, verify the source still matches that version. For files, ensure paths point to immutable content; keeping a single path that can be overwritten is not enough.

## 13. Restart: How Does a Cursor Restore Its Position?

With `JdbcCursorItemReader` and `saveState(true)`, Spring Batch writes read progress to `ExecutionContext` when chunks commit. When an execution fails and restarts, the reader reopens the query and advances to the saved position using the reader/driver mechanism.

Conceptual example:

```text
Execution 1:
  read order_id 1..200   -> commit
  read order_id 201..400 -> commit
  read order_id 401..500 -> fail, rollback

Restart:
  reopen query
  restore from committed checkpoint
  reprocess uncommitted portion
```

This **does not mean the old database cursor stayed alive while the JVM was down**. The reader opens a new cursor and uses saved state to fast-forward to the position.

### Danger When Row Set or Order Changes

If the first execution read 400 rows, and then 5 rows before them were inserted or deleted, repositioning by row count/position in the new query result can land on the wrong record. A stable `ORDER BY` only guarantees **deterministic ordering when the row set is identical**—it does not make a mutating row set immutable.

For accurate restarts, use a source snapshot or guarantee that rows and ordering do not change between executions.

### driverSupportsAbsolute

Some drivers support jumping directly to a specific row position via JDBC APIs instead of scanning sequentially from the start on restart. Reader options related to `absolute()` positioning can affect repositioning cost. Verify driver behavior; never assume every `ResultSet` supports efficient random jumps.

## 14. Restart: Paging Uses Sort Keys and State

`JdbcPagingItemReader` persists progress state to resume from the proper point. A **unique sort key** is crucial so the reader never confuses two records sharing the same sort value.

For example, do not sort solely by `created_at` when multiple rows share a timestamp:

```sql
ORDER BY created_at
```

If multiple rows have identical `created_at`, page boundaries become non-deterministic. Use a unique composite key:

```sql
ORDER BY created_at, order_id
```

In the builder:

```java
Map<String, Order> sortKeys = new LinkedHashMap<>();
sortKeys.put("created_at", Order.ASCENDING);
sortKeys.put("order_id", Order.ASCENDING);
```

This example applies to time-ordered data. If `created_at` can be updated, even a unique composite sort key is unsafe if the source mutates between pages. Choose **immutable** keys whenever possible.

### Risk of Non-Unique Sort Keys

Suppose `pageSize=2` and three records share `created_at`:

```text
(created_at=10:00, id=A)
(created_at=10:00, id=B)
(created_at=10:00, id=C)
```

If pagination relies solely on `created_at` to fetch the next page, there is no way to express "after B but before C" using that timestamp alone. Items can be lost or duplicated. Adding `id` to `sortKeys` uniquely identifies the boundary via the pair.

**Rule:** the sort key must define a strict total order over all selected records, not just "most rows have distinct values."

## 15. Cursor, Paging, and Chunk Transactions

A chunk step performs multiple commits during execution. This creates three distinct lifecycles:

1. **Chunk processing transaction:** read, process, and write a batch of items, then commit/rollback.
2. **Source connection/query:** cursor or page queries.
3. **JobExecution/StepExecution:** status and restart checkpoints.

Do not infer that because a chunk commits every 200 items, the database cursor closes and reopens every 200 items. `JdbcCursorItemReader` typically keeps a `ResultSet` open longer than a single chunk transaction. With paging, the reader may fetch a 500-item page and feed several chunks from that buffer.

### 15.1. Consistency and Read-Only

If the reader uses a separate connection/transaction, row visibility depends on how the database handles MVCC/isolation and the reader's configuration. Putting `@Transactional(readOnly=true)` on another method in the application does not automatically put all cursor/page queries into the same snapshot.

If you need a consistent snapshot across the entire job, design it at the **immutable source/snapshot** level or via appropriate database/transaction semantics. Holding a single snapshot transaction for hours can trigger MVCC/vacuum/lock overhead or hit resource limits, so coordinate with your DBA.

### 15.2. Writer Mutating Data the Reader Is Scanning

Suppose the read query is:

```sql
SELECT order_id
FROM sales_order
WHERE status = 'READY'
ORDER BY order_id;
```

The writer updates `status='PROCESSED'` after each chunk. With paging, the `READY` set shrinks dynamically. If re-queried with incompatible ordering/offsetting, later pages risk skipping rows. With a cursor, behavior also depends on snapshot/cursor semantics and update visibility.

A better solution is capturing the target key list up front or designing a claiming/work-queue pattern with dedicated transactions, rather than mutating the filter predicate mid-scan and expecting every paging reader to cope.

## 16. Memory and JDBC Resources

A common misconception is "cursor uses zero memory, paging uses memory." Both maintain buffers:

```text
Cursor:
  JDBC driver buffers / fetch window
       + mapped current item
       + chunk items
       + writer buffers

Paging:
  pageSize mapped items
       + chunk items
       + writer buffers
       + query infrastructure
```

**The working set** can grow when:

- `fetchSize` or `pageSize` is too large.
- Items contain large text/JSON/blob fields or collections.
- Large `chunkSize` retains many items until the writer finishes.
- The writer buffers all output into a list before commit.
- Multiple partitions/threads each allocate their own reader, chunk, and connection.
- Logging retains payloads/exceptions or async queues are unbounded.

Illustrative calculation:

```text
pageSize = 1,000
average retained item ≈ 4 KB

1 paging reader may hold ≈ 4 MB just for page items
8 partition readers may hold ≈ 32 MB for pages

Not counting chunk/writer, JDBC buffers, JVM overhead,
object graphs, and other tasks/queues.
```

These numbers only illustrate scaling trends, not exact heap measurements. Use JFR/heap profiling and JVM metrics to measure actual allocations and retained memory.

### Connection Pool

A cursor generally holds a connection for the duration of the active step. If you run 10 parallel partitions, budget connections for all readers alongside writer transactions, monitoring, and other workloads. Paging can be more flexible with connection hold time, yet each query still borrows a connection and generates frequent DB requests.

Never scale partition counts past your connection pool capacity or database throughput ceiling while assuming linear speedup per worker.

## 17. Query Performance: One Long Query vs. Many Page Queries?

Suppose there are 5 million records, 1,000 items per page:

- Cursor executes one query and fetches in batches from the result set.
- Paging issues roughly 5,000 page queries (exact count depends on filters, restarts, and SQL generation).
- Individual page queries can leverage indexes to pull a narrow slice quickly.
- If the query contains expensive JOINs, GROUP BYs, or sorts, paging may repeat that execution cost thousands of times.
- If a cursor query holds server resources too long or runs over an unstable connection, recovery cost may outweigh the benefit of fewer queries.

Measure:

| Metric | Cursor | Paging |
| --- | --- | --- |
| Total job duration | Measure | Measure |
| Items/second | Measure | Measure |
| SQL execution count | Measure | Measure |
| Average/p95 query time | Measure | Measure |
| Open connections and hold duration | Measure | Measure |
| DB CPU/IO/buffer reads | Measure | Measure |
| Peak heap and GC time | Measure | Measure |
| Timeouts/failures | Measure | Measure |
| Restart time after failure | Measure | Measure |

Never draw conclusions from a single "rows per second" metric if the reader looks fast while saturating the writer or database.

### EXPLAIN and Indexes

For paging:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, business_date, amount
FROM sales_order
WHERE business_date = DATE '2026-11-15'
  AND order_id > 100000
ORDER BY order_id
LIMIT 500;
```

This is an illustrative keyset query, not necessarily the exact SQL generated by every `PagingQueryProvider`. To analyze real Spring Batch queries, enable SQL logging or capture actual queries at the datasource/proxy, and inspect the execution plan of that exact SQL.

Index design should consider:

- Equality and range filter predicates.
- Sort key order.
- Cardinality and data distribution.
- Selectivity by date/tenant.
- Number of projected columns and potential index-only scans.
- Table write workload, since extra indexes add write overhead.

## 18. Parallel Processing and Partitioning

Neither `JdbcCursorItemReader` nor `JdbcPagingItemReader` is **thread-safe by default** when a single reader instance is invoked concurrently by multiple threads.

For parallel processing, a clean pattern is **partitioning data** by key range, giving each `StepExecution` its own reader:

```text
                         Manager Step
                              |
             +----------------+----------------+
             |                |                |
          Partition A      Partition B      Partition C
          ID 1..100k       ID 100k..200k    ID 200k..300k
             |                |                |
          Reader A         Reader B         Reader C
             |                |                |
          Chunks            Chunks           Chunks
             |                |                |
             +----------------+----------------+
                              |
                       Output / Aggregation
```

Each partition receives identifying/range parameters in its step execution context and maintains isolated reader state. Avoid overlaps or gaps, verify matching `WHERE` predicates, and keep writers idempotent.

### If a Multi-Threaded Step Is Needed

You can wrap a reader with synchronization in some designs, but synchronization can bottleneck throughput, and state/restart semantics in a multi-threaded step require careful analysis. Never simply point multiple threads at one JDBC `ResultSet` or stateful reader.

One reason paging is often chosen for partitioning is that each key range can be queried independently without sharing a single cursor. Cursors can also run per partition; just budget concurrent cursors and DB connections accordingly.

## 19. Transaction Isolation and Consistency: Three Pattern Choices

### Option A — Period-Immutable Source

**Data:** an end-of-day finalized snapshot table.

**Choice:** either cursor or paging can fit. If reading sequentially and driver streaming works well, cursor is simple. If many partitions are needed or connections cannot stay open long, paging makes sense.

**Restart:** safer because data and ordering do not change, though the writer still needs idempotency.

### Option B — Live Operational Source Still Mutating

**Data:** an active orders table receiving continuous inserts/updates/deletes.

**Choice:** do not pick cursor or paging before solving consistency. You need a snapshot, conditional watermark, claiming, or an appropriate CDC/work-queue model.

**Restart:** checkpoints are only valid if the underlying dataset has not changed; verify source version.

### Option C — High Volume and Long Job Duration

**Data:** tens of millions of records, multi-hour runtime, database enforces finite connection lifetimes.

**Choice:** key-based paging/partitioning is usually more practical to avoid a single long-lived cursor. Still verify query count, indexes, and DB load.

**Restart:** per-partition checkpoints on a stable source; prevent duplicate target rows after partial failures.

## 20. Example: Selecting Reader via Configuration Property

To benchmark both readers over the exact same business logic, you can use two profiles or conditional configuration. Spring Boot example:

```yaml
app:
  batch:
    reader: paging
    page-size: 500
    chunk-size: 200
```

During benchmark runs:

```yaml
app:
  batch:
    reader: cursor
    fetch-size: 500
    chunk-size: 200
```

In the implementation, each reader configuration is registered conditionally with `@ConditionalOnProperty` or separate profiles; the step injects the active reader. Ensure **Job/Step/Reader names and restart metadata** are managed intentionally when switching strategies.

Crucial warning: **Do not switch from cursor to paging mid-flight on a `FAILED` `JobInstance` and assume the old reader's checkpoint is compatible.** The two readers store different state formats and may use different ordering/queries. When changing strategy for an incomplete period, use a verified migration/restart procedure or run a controlled reprocess after reconciling target data.

## 21. A Practical Decision Matrix

Evaluate traits against system needs instead of following a rigid formula:

| Workload Characteristic | Cursor | Paging |
| --- | --- | --- |
| Single sequential scan over a snapshot | **Strong candidate** | Also suitable |
| Heavy query that is expensive to re-run | **Potential advantage** | Check per-page execution cost |
| Long connections prone to timeout | Risky | **Usually more practical** |
| Many independent partitions | Each partition holds a cursor/connection | **Easy to organize by key range** |
| Table has good unique key/index | Helps ordering/restart | **Essential for `sortKeys` and performance** |
| No unique sort key | Cursor reads in one order, though restart remains risky | **Hard to guarantee accurate paging** |
| Source mutates continuously | Needs snapshot/isolation | Needs snapshot/keyset/work claiming |
| Separate tuning of queries and chunks | `fetchSize` and `chunkSize` | `pageSize` and `chunkSize` |
| Small problem, few records | Pick for simplicity | Pick for simplicity |
| Poor JDBC ResultSet streaming support | May over-buffer or time out | **May be more suitable** |
| Needs exact restarts | Stable source and state | Stable source, unique sort key, and state |

### Quick Rule of Thumb

- **Prototype cursor first** when you have an immutable snapshot source, sequential processing, a relatively heavy query, and verified JDBC streaming.
- **Prototype paging first** when you have a unique sort key/index, long-running jobs, constrained connection lifetimes, or independent partitions.
- **Hold off choosing a reader** when the source mutates continuously without a defined snapshot/consistency contract. First solve: "Which exact rows must each period process?"

These are starting points for benchmarking, not guarantees that one option always wins.

## 22. Testing Reader Behavior

A meaningful comparison must verify **data correctness** before measuring speed.

### 22.1. Controlled Dataset

Prepare data for day D:

```text
order_id: 1, 2, 3, ..., 1,005
businessDate: D
```

Configuration:

```text
chunkSize = 200
cursorFetchSize = 500
pagingPageSize = 500
```

Requirements:

- Both readers read all 1,005 orders.
- Every order ID appears exactly once in the business output.
- Ordering ascends by key or meets business rules.
- The final partial batch (< 200 items) is still processed.
- Read/write counts and `StepExecution` status match expectations.

### 22.2. Test Scenarios

| Scenario | Expectation |
| --- | --- |
| Empty source | Reader returns `null` immediately; job completes per policy |
| Single record | Exactly one item; no page boundary bugs |
| 499, 500, 501 records | No drops or duplicates around page size 500 |
| 999, 1,000, 1,001 records | Accurate across multiple page boundaries |
| Query with NULLs or duplicate keys in sort columns | Detect or prevent non-unique sort designs |
| Chunk commit while cursor remains open | Cursor continues reading normally on target driver |
| Writer fails on third chunk | Restarts from checkpoint with zero duplicate output |
| Insert row before already-read position | Demonstrate behavior and consistency risks |
| Delete/update rows between pages | Verify snapshot/watermark policy |
| Database/proxy drops connection mid-job | Exceptions and recovery are handled cleanly |
| 4–8 partitions | No overlapping or skipped ranges; total output matches |
| Records with large text/JSON payloads | Heap and GC remain within bounds |
| One day has 0 rows, another has huge volume | No parameter calculation or sorting bugs |

For concurrent update tests, use synchronization primitives like `CountDownLatch` to coordinate exact timing while reading pages/chunks; avoid `Thread.sleep` and hoping events align.

### 22.3. Integration Testing Against a Real Database

For paging SQL, behavior can depend on database dialect. Test against PostgreSQL if production uses PostgreSQL (e.g., via Testcontainers or a dedicated test instance), rather than assuming H2 SQL and isolation match production.

Assertions should check both **actual rows in the target table** and **the list of business keys**, not just `readCount`. Under retries/rollbacks, a reader may re-fetch parts of data, so verify the final committed output.

## 23. Reliable Performance Benchmarking

Benchmark cursor and paging on the same dataset, processor/writer, and infrastructure conditions.

### Suggested Procedure

1. Prepare a snapshot with representative row counts, sizes, and distributions.
2. Initialize matching database statistics/indexes and fix connection pool settings.
3. Run warm-ups and multiple timed iterations for each option.
4. Hold `chunkSize` constant initially while varying `fetchSize` or `pageSize`.
5. Measure overall throughput and total SQL queries.
6. Measure DB CPU, I/O, lock waits, and connection usage.
7. Measure JVM peak heap, allocation rate, GC pauses, and thread counts.
8. Repeat at target concurrency and under failure-restart conditions.
9. Compare output counts, keys, and values to verify both options processed identical data.
10. Document configurations, environment, JVM, Spring Batch, driver, and database versions.

### Illustrative Results Table

| Metric | Cursor (simulated) | Paging (simulated) |
| --- | ---: | ---: |
| Dataset | 2,000,000 items | 2,000,000 items |
| Total duration | 420 seconds | 450 seconds |
| Throughput | ~4,762 items/s | ~4,444 items/s |
| JDBC query executions | 1 main query | ~4,000 page queries |
| Reader connection hold time | Long | Per query/page |
| Peak heap | 1.1 GB | 1.0 GB |
| Errors/timeouts | 0 | 0 |
| Correct output | Yes | Yes |

**All numbers in this table are simulated to illustrate reporting format**, not a real benchmark or claim that cursor beats paging. On another workload, paging can be markedly faster—especially with partitioning or when a cursor has to restart due to connection timeouts.

Never draw conclusions from a single run: JIT warm-up, DB caching, network variance, background load, and query plan changes can skew results heavily.

## 24. Common Design Mistakes

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Cursor consumes excessive heap | Driver buffers entire ResultSet; `fetchSize` ignored | Verify driver/autocommit/fetch behavior; profile memory |
| Cursor times out on long jobs | Connection/result set stays open too long | Tune timeouts appropriately or switch to paging |
| Cursor restart skips/duplicates rows | Query/dataset mutated after checkpoint | Snapshot source; enforce stable sort/order |
| Paging drops rows at page boundaries | Non-unique sort key | Use a unique composite sort key |
| Paging slows down over time | Deep `OFFSET`, costly sort, or missing index | Inspect actual SQL, query plan, and keyset/indexes |
| Paging re-reads the same record | Mutation before next page or sort key changed | Snapshot or immutable sort key |
| Reading `WHERE status='READY'` while writer updates status | Filter set shrinks during read | Snapshot, claiming, or decoupled source pipeline |
| Small table with overly complex config | Premature optimization | Pick the maintainable option |
| Large page size causes OOM | Page buffer, chunk, and writer all retain items | Lower sizes; profile retained heap |
| Raising concurrency slows the job down | DB or connection pool saturated | Cap partitions and measure DB metrics |
| Reader misbehaves when multi-threaded | Sharing a non-thread-safe reader | Dedicated reader per partition |
| Restart after swapping reader fails | Incompatible old `ExecutionContext` | Controlled migration/reprocess procedure |
| Duplicates in target table after restart | Non-idempotent writer, insufficient checkpoints | Unique keys, upserts, outbox |
| Passes on H2 tests, fails in production | Dialect, isolation, or cursor behavior differences | Test against a production-compatible database |
| Confusing `pageSize` and `chunkSize` | Tuning the wrong knob | Separate read I/O buffering from write transaction chunking |
| Confusing API cursor token with JDBC cursor | Wrong state/lifetime design | Identify the true source protocol |
| No errors logged, yet 1% data missing | Checking only `BatchStatus.COMPLETED` | Reconcile keys/counts against snapshot |
| Non-deterministic query order | Missing `ORDER BY` / unique sort | Define a deterministic total order |

## 25. Practice Exercises

Build `importOrdersJob` to read 100,000 orders from `sales_order` for a finalized `businessDate`:

1. Write one version using `JdbcCursorItemReader` configured with `fetchSize=500`, a reader name, and `saveState(true)`.
2. Write another version using `JdbcPagingItemReader` with `pageSize=500` and a unique sort key.
3. Share a processor that adds a simple processing fee; write to `order_summary` with a unique constraint on business date and order ID.
4. Test chunk sizes 100, 200, and 500; measure runtime, read/write counts, peak heap, GC, and query count.
5. Force the writer to fail after two chunks commit; restart and reconcile target data to verify zero duplicates.
6. Insert a record into the source between two pages, then delete a record ahead of the read position. Compare both readers' behavior and explain why a snapshot is required for accuracy.
7. Experiment with a non-unique sort key and fix it using a composite key.
8. Partition by ID range with a dedicated reader per partition; check total processed orders and concurrent connection counts.
9. Write a selection report choosing cursor or paging for an environment with a 30-minute connection lifetime limit and an expected 2-hour job runtime. State what must be verified by benchmarks.

Your report should include **correctness**, **resources**, **throughput**, **restartability**, **source-mutation risk**, and a **final decision backed by evidence**. Do not decide solely because one run finished a few seconds faster in a single test.

## 26. Summary

Choosing **cursor vs. paging** in Spring Batch is a trade-off among query count, connection lifetime, memory buffering, transaction strategy, scalability, and restart reliability.

- **Cursor** is worth considering for long sequential scans over a stable source, especially when queries are expensive and the JDBC driver genuinely supports batched fetching. In return, cursors/result sets hold resources for a long time.
- **Paging** fits when you have a unique sort key and good indexes, need key-range partitioning, or want to avoid long-lived cursors. In return, it issues many queries and requires care if the source mutates between pages.
- **Both require stable source design, proper checkpoints, idempotent writers, and restart testing.** Neither reader automatically ensures exactly-once semantics when source data mutates or targets have external side effects.

A reliable decision workflow is: define the business record set and consistency requirement → check indexes, drivers, and connection policies → implement the fitting reader config → measure throughput and resources on realistic data → verify restarts and outputs. The ultimate goal is not merely reading fast, but **processing accurately, recovering cleanly, and operating reliably**.
