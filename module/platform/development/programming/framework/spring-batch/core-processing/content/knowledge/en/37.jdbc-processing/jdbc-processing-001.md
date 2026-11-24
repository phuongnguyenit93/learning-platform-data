# Cursor Reading and Transactions

In Spring Batch, `JdbcCursorItemReader<T>` reads database data using a JDBC cursor. The reader opens a query, keeps the `ResultSet` open, and advances row by row with `ResultSet.next()`. This reading approach is suitable when you need to iterate sequentially over a large result set without loading all data into memory.

When using a cursor in a chunk-oriented step, you need to clearly understand two lifecycles running concurrently:

- **Cursor lifecycle:** open the connection/statement/result set, read rows, save the checkpoint position, and close resources.
- **Chunk transaction lifecycle:** start a transaction, read and process a group of items, write the results, and then commit or roll back per chunk.

By default, `JdbcCursorItemReader` opens the cursor on a separate connection, isolated from the connection that the step uses for chunk processing transactions. This allows the cursor to remain open across chunk commits. If you want to share the connection with the step, you must enable the extended connection mechanism and use `ExtendedConnectionDataSourceProxy`; the database driver must also support cursors that survive across commits.

Reading via a cursor should not be treated as a single transaction spanning the entire job. The cursor can live for the duration of the step, whereas write transactions usually end after each chunk. This separation affects isolation, dataset consistency, rollback, restart, and holding connections for long periods.

## What Is a Cursor?

In JDBC, a `SELECT` statement can return a `ResultSet`. A cursor represents the current position in that result set. The application calls `next()` to move to the next row and read the columns of the current row.

```text
SQL query
   |
   v
PreparedStatement.executeQuery()
   |
   v
ResultSet / cursor
   |
   +--> next() -> row 1
   +--> next() -> row 2
   +--> next() -> row 3
   +--> ...
   +--> next() -> false (EOF)
```

A cursor is typically used in a forward-only direction (*forward-only*). The driver can fetch data from the database in batches via fetch size, though the details depend on the driver and database configuration.

`JdbcCursorItemReader` wraps a JDBC cursor into Spring Batch's `ItemReader<T>` contract. Each call to `read()` returns one object mapped from the next row; when there are no more results, the reader returns `null`.

### How a Cursor Differs from Reading All Rows into a List

With a standard query approach, an application might call `queryForList` or `query` to materialize the entire result into a collection. With a cursor reader, rows are consumed sequentially:

| Reading Approach | Characteristics |
| --- | --- |
| Query returning `List` | Results are usually materialized in memory before further processing |
| `JdbcCursorItemReader` | Keeps the cursor open and maps each row as the step calls `read()` |
| `JdbcPagingItemReader` | Runs multiple queries page by page, typically using a sort key to continue to the next page |

A cursor reduces the need to keep all objects in memory, but it holds a connection and database cursor open for as long as the step is active. It is not automatically faster than paging across every database or workload.

## How Does JdbcCursorItemReader Work?

`JdbcCursorItemReader<T>` resides in the `org.springframework.batch.item.database` package. It executes the SQL when the reader opens and holds the necessary JDBC resources until the step closes the reader.

General lifecycle:

```text
Step starts
    |
    v
reader.open(ExecutionContext)
    |
    +--> acquire connection
    +--> create PreparedStatement
    +--> executeQuery()
    +--> hold ResultSet/cursor
    |
    v
reader.read() repeats per item
    |
    +--> ResultSet.next()
    +--> RowMapper maps row to item
    +--> return item to chunk
    |
    v
Chunk transaction commits/rolls back per step configuration
    |
    +--> reader.update(ExecutionContext) at checkpoint
    |
    v
Step ends
    |
    v
reader.close()
    |
    +--> close ResultSet
    +--> close Statement
    +--> release connection per ownership
```

This is a conceptual lifecycle model. Spring Batch manages invoking the `ItemStream` callbacks; do not manually call `open`, `update`, or `close` in the reader's business code.

## Basic JdbcCursorItemReader Configuration

Suppose the database has a `customer` table:

```sql
CREATE TABLE customer (
    customer_id BIGINT PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL,
    balance DECIMAL(18, 2),
    created_at TIMESTAMP NOT NULL
);
```

Java model:

```java
public record Customer(
        long customerId,
        String fullName,
        BigDecimal balance,
        LocalDateTime createdAt) {
}
```

Reader using the builder:

```java
@Bean
@StepScope
JdbcCursorItemReader<Customer> customerCursorReader(
        DataSource dataSource,
        @Value("#{jobParameters['cutoffTime']}") String cutoffTime) {

    Timestamp cutoff = Timestamp.valueOf(
            LocalDateTime.parse(cutoffTime));

    return new JdbcCursorItemReaderBuilder<Customer>()
            .name("customerCursorReader")
            .dataSource(dataSource)
            .sql("""
                    SELECT customer_id, full_name, balance, created_at
                    FROM customer
                    WHERE created_at < ?
                    ORDER BY customer_id
                    """)
            .preparedStatementSetter(ps -> ps.setTimestamp(1, cutoff))
            .rowMapper((rs, rowNum) -> new Customer(
                    rs.getLong("customer_id"),
                    rs.getString("full_name"),
                    rs.getBigDecimal("balance"),
                    rs.getTimestamp("created_at").toLocalDateTime()))
            .fetchSize(500)
            .saveState(true)
            .build();
}
```

Main components:

- `dataSource`: datasource used to open the cursor connection.
- `sql`: query to fetch the data.
- `preparedStatementSetter`: binds values for `?` placeholders.
- `rowMapper`: converts each row in the `ResultSet` into an object.
- `fetchSize`: hint to the JDBC driver for how many rows to fetch per batch.
- `saveState(true)`: allows the reader to save its position to support restart.
- `name`: stable name used for state in the `ExecutionContext`.

The example assumes `cutoffTime` is in ISO local date-time format, such as `2026-11-15T00:00:00`. If temporal data carries a timezone, use a type/format with an offset and convert consistently with the database; do not parse an instant with a timezone into `LocalDateTime` and drop the offset.

## RowMapper and Cursor Position

`RowMapper<T>` receives the `ResultSet` positioned at the current row and maps that row to an object. It must not call `ResultSet.next()` itself.

```java
RowMapper<Customer> customerMapper = (rs, rowNum) ->
        new Customer(
                rs.getLong("customer_id"),
                rs.getString("full_name"),
                rs.getBigDecimal("balance"),
                rs.getTimestamp("created_at").toLocalDateTime());
```

Spring Batch has already moved the cursor to the row to be read before invoking the mapper. If the mapper calls `next()` itself, it will skip rows or alter the cursor position unexpectedly.

`JdbcCursorItemReader` has a `verifyCursorPosition` option to check whether the mapper changed the cursor position. Keep this check enabled in normal cases. Only disable it if you have a specific reason and full control over the mapper.

Do not retain `ResultSet` or `PreparedStatement` inside business objects after the mapper returns. JDBC resources belong to the reader and will be closed when the step ends.

## Cursor Connection and Chunk Transaction

This is the most important aspect when reading via a cursor. A chunk-oriented step has its own transaction manager and transaction boundaries. `JdbcCursorItemReader` opens the cursor using a separate connection by default; the chunk transaction usually uses a different connection to write data or update metadata.

### Default: Cursor Uses a Separate Connection

By default, the reader opens a separate connection for the cursor. This connection is held for the entire reading duration and is not the connection that the chunk's transaction manager uses to execute the writer.

```text
                Step execution
                     |
          +----------+----------+
          |                     |
          v                     v
  Cursor connection       Chunk transaction
          |                     |
  SELECT ...               BEGIN
          |                     |
  ResultSet.next()         Processor
          |                     |
  RowMapper                JDBC writer
          |                     |
  next item                COMMIT / ROLLBACK
          |                     |
  cursor stays open        next chunk
          |                     |
          +----------+----------+
                     |
                 Step ends
                     |
                close cursor
```

The advantage of a separate connection is that chunk commit/rollback does not automatically close the cursor connection. The reader can continue reading subsequent rows across multiple chunk transactions.

The consequence is that the cursor's `SELECT` statement does not inherently execute in the same transaction as the writer's `INSERT`/`UPDATE` statements. The two connections may observe data according to their own isolation levels and snapshots. If the writer updates the very rows the cursor is reading, you must understand the database semantics and avoid assuming the reader will immediately see committed changes from the writer.

### Chunk Transactions Do Not Roll Back Cursor Movement

When `ResultSet.next()` advances to the next row, that is the state of the cursor on the reader connection. Rolling back the chunk write transaction does not automatically rewind the database cursor to a previous row.

Spring Batch manages item buffering, checkpoints, and reader state through the step mechanism. Do not call `ResultSet.previous()` or manually rewind the cursor inside a processor or writer to try to recover on rollback. The reader should properly implement the `ItemStream` contract and let the framework manage restart/retry.

When a chunk fails, distinguish between:

- The chunk's database transaction can roll back uncommitted changes.
- The physical cursor has already advanced when the reader fetched the items.
- Spring Batch has mechanisms for handling items already read in the chunk and checkpoint state according to the step/fault-tolerance configuration.
- When the process/job restarts, the reader reopens the query and restores its position from saved state.

Therefore, do not infer that a database rollback will make `JdbcCursorItemReader` re-read from the start of the chunk by rolling back the cursor. Test retry/skip with the actual step configuration and database driver.

## Shared Extended Connection

In some cases, an application wants the cursor to use a connection shared with the step's processing operations. `JdbcCursorItemReader` supports the `useSharedExtendedConnection` option.

To use this mechanism, the datasource must be wrapped with `ExtendedConnectionDataSourceProxy`, and the JDBC driver/database must support cursors that can survive across commits (*holdable cursor*). The reader requests appropriate holdability so the cursor is not closed when the chunk transaction commits.

Example datasource proxy configuration:

```java
@Bean
ExtendedConnectionDataSourceProxy extendedDataSource(DataSource dataSource) {
    return new ExtendedConnectionDataSourceProxy(dataSource);
}
```

Then configure the reader to use the datasource proxy and enable shared connection:

```java
@Bean
@StepScope
JdbcCursorItemReader<Customer> sharedCustomerReader(
        ExtendedConnectionDataSourceProxy extendedDataSource) {

    return new JdbcCursorItemReaderBuilder<Customer>()
            .name("sharedCustomerReader")
            .dataSource(extendedDataSource)
            .sql("SELECT customer_id, full_name FROM customer ORDER BY customer_id")
            .rowMapper((rs, rowNum) -> new Customer(
                    rs.getLong("customer_id"),
                    rs.getString("full_name"),
                    null,
                    null))
            .useSharedExtendedConnection(true)
            .saveState(true)
            .build();
}
```

The example only illustrates the reader. In a real configuration, the transaction manager and components sharing the datasource must be configured consistently so the proxy can share the extended connection properly. Do not create separate proxies for the reader and the transaction manager and expect them to automatically share the same connection; they need the same proxy/target resource mechanism per Spring's guidance.

### Conditions and Limitations

Before enabling `useSharedExtendedConnection`, verify:

- The database driver supports holdable cursors across commits.
- The connection can request `ResultSet.HOLD_CURSORS_OVER_COMMIT`.
- `ExtendedConnectionDataSourceProxy` is used correctly in the datasource/transaction manager configuration.
- No other component closes or modifies the connection outside the managed lifecycle.
- Behavior on rollback, commit, and restart has been tested on the production driver.

If the driver does not support holdable cursors, sharing the connection can cause the cursor to be closed after commit or prevent the reader from working as expected. In that case, keeping the default configuration with a separate connection is usually the safer choice.

### When Is a Shared Connection Needed?

Enable it only when there is a clear requirement for transaction/connection sharing. For example, a workflow needs to read and write on the same connection/resource to achieve specific database semantics. However, a shared connection can increase coupling between the cursor lifecycle and the transaction lifecycle, while also holding the connection for a long time.

Do not enable it merely out of a belief that reader and writer must always use the same connection. For most standard batch read/write workloads, the default separate connection is a sound design.

## Isolation Level and Data Consistency

A cursor reads a result set while other transactions may insert, update, or delete rows. How the reader observes changing data depends on the database, isolation level, cursor implementation, and when the query is executed.

Several concepts to distinguish:

- **Read committed:** each read may only see committed data; the snapshot may differ per statement or per transaction depending on the database.
- **Repeatable read:** restricts certain changes to already-read rows, though exact semantics depend on the database.
- **Snapshot isolation/MVCC:** a query can read a consistent snapshot at a point in time, depending on the engine and transaction scope.
- **Serializable:** a higher isolation level, which can increase locking/contention and reduce concurrency.

You cannot assume every JDBC cursor always sees a fixed snapshot until EOF. Some databases create a snapshot for a SELECT statement at the time the cursor opens; some behaviors depend on transaction isolation and server configuration. Check your actual database/driver documentation.

### Data Changing While the Job Runs

Suppose a cursor reads from the `orders` table while another application inserts new rows or updates `status`:

```text
T0: batch opens cursor and runs SELECT
T1: batch reads orders 1..100
T2: another application runs INSERT order 101 and COMMIT
T3: batch continues reading
```

Whether order 101 appears depends on the database's cursor/snapshot semantics. Likewise, an already-read or upcoming row may reflect values at query open time or fetch time depending on the engine.

If business logic requires a fixed input set, you can:

- Choose a cutoff/watermark and only read rows with `created_at` earlier than the cutoff.
- Use a batch/staging status to freeze the dataset.
- Use appropriate snapshot isolation if the database supports it and the transaction duration is acceptable.
- Persist a manifest of keys to process.
- Read from a staging table or immutable source.

Use `ORDER BY` only to stabilize ordering, not to freeze the dataset. Stable ordering and a stable snapshot are two distinct requirements.

## ORDER BY Is Crucial for Restart

On restart, `JdbcCursorItemReader` typically re-executes the SQL and restores position by advancing to the row corresponding to the checkpointed item count. If the query result does not have a deterministic order, the same position may point to a different row on a subsequent run.

You should include an `ORDER BY` on a unique key or a unique combination of keys:

```sql
SELECT order_id, customer_id, amount
FROM orders
WHERE batch_status = 'READY'
ORDER BY created_at, order_id
```

`created_at` may have duplicates across multiple rows; `order_id` adds a unique tie-breaker. If you only use `ORDER BY created_at`, the database may return rows with the same timestamp in a different order on the next query.

Do not rely on physical table order, indexes, or execution plans. The query must specify the ordering explicitly.

## Checkpoint and Restart of JdbcCursorItemReader

`JdbcCursorItemReader` implements `ItemStream`, so it can store state in the `ExecutionContext`. When `saveState(true)` is set, the reader records the count of items read according to the `AbstractCursorItemReader` mechanism and uses that state when reopening.

On restart, the reader typically:

1. Reopens the SQL query.
2. Restores the number of processed/read items from the committed checkpoint.
3. Advances the cursor to the position to resume from.
4. Continues returning the next item.

Depending on the driver and configuration, the reader can use `ResultSet.absolute()` to jump quickly if `driverSupportsAbsolute` is enabled and the driver supports it; otherwise, the reader may advance the cursor sequentially to the checkpoint position. Do not enable the absolute option based on guesswork; confirm driver support.

### Reader Name Must Be Stable

The reader name is used to construct state keys in the `ExecutionContext`. Keep `.name("customerCursorReader")` stable across restarts. Changing the name can prevent the reader from finding the old checkpoint.

### SQL and Parameters Must Be Stable

When restarting the same `JobInstance`, the query needs to return the same logical dataset and the same order. If you change the cutoff, filter, join, or identifying parameters, the old checkpoint may no longer be valid.

If the query depends on the current time (`CURRENT_TIMESTAMP`) or mutable data without a cutoff, the restart run may receive a different result set. Compute cutoff values before launching, pass them via `JobParameters`, and keep them unchanged on restart.

### saveState false

If `saveState` is disabled, the reader does not store its position for restart. The job may not resume from a checkpoint as expected. Only disable state when the step does not need restart or the application has another mechanism to reposition on the data.

Do not manually edit keys in the `ExecutionContext` or replace `currentItemCount` with SQL metadata without understanding the reader state contract. Let the reader and `JobRepository` manage checkpoints.

## Cursor and Rollback in a Fault-Tolerant Step

When a step has retry or skip configured, the reader may be invoked within a more complex execution flow than a normal chunk. Spring Batch can buffer already-read items for reprocessing without re-reading the cursor, depending on the processing mode and reader semantics.

Key points to remember:

- A cursor generally moves forward; database rollback does not rewind the `ResultSet`.
- Items already read in a chunk may be held in a buffer by the framework during retry/rollback.
- Checkpoints should only represent progress committed according to the step lifecycle.
- The reader should have no business side effects inside `read()`.
- If the read source is a transactional queue or a resource with different semantics, configure buffering accordingly.

Do not blindly add retry for every cursor read error. SQL syntax errors, schema mismatches, or mapping bugs usually do not recover on retry. Transient connection errors can be retried per policy, but the cursor/connection may already be lost and the step may need to fail and restart from the checkpoint.

If the writer writes to the same table the reader is querying, consider the risk of rows being re-read, skipped, or having their status changed while the cursor is open. You can separate source and target, use a staging table, or mark batches with a dedicated claim/lease process.

## Connection Pool and Database Resources

A cursor holds a connection open for the entire time the reader is active. For a long-running step, a connection may be held for minutes or hours. This directly affects the connection pool and the ability to serve other jobs.

For example, suppose a pool has 10 connections and 8 concurrent jobs hold cursor connections. Only 2 connections remain for writer transactions, the metadata repository, and other requests. If writers need connections from the same pool, waiting or pool deadlock can occur if the pool is undersized.

Operational principles:

- Calculate the number of connections needed for cursors, chunk transactions, the repository, and other workers.
- Size the pool based on actual concurrency, not just the number of launcher threads.
- Set appropriate query timeouts and connection/network timeouts.
- Close the reader on all step termination paths; let Spring Batch manage the lifecycle.
- Monitor active connections, borrowed duration, and cursor counts.
- Avoid holding a cursor in a step while waiting on an external operation without a timeout.
- Check database cursor/open statement limits.

If using multiple datasources, distinguish the pool dedicated to cursors from the pool dedicated to transaction processing. Separating pools can reduce contention, though it increases the total connections the database must handle.

## Fetch Size and Performance

`fetchSize` is a hint to the JDBC driver for how many rows to retrieve from the database in a single round trip batch. For example, `.fetchSize(500)` suggests the driver fetch around 500 rows per round trip.

Fetch size is not chunk size:

| Setting | Meaning |
| --- | --- |
| JDBC fetch size | Hint for how many rows the driver fetches at a time from the server |
| Spring Batch chunk size | Number of items processed in a single chunk transaction |
| Page size | Number of rows per query/page for a paging reader |

For example, a fetch size of 500 and a chunk size of 100 may cause the driver to fetch data in batches of 500 rows while Spring Batch commits after every 100 items. How the driver actually buffers rows depends on the driver and database.

A fetch size that is too small can increase round trips; one that is too large can increase memory usage in the driver/client. Some drivers only stream data when fetch size is combined with specific auto-commit/isolation settings or special options. Read your JDBC driver documentation and benchmark in a production-like environment.

Beyond fetch size, performance also depends on:

- Indexes supporting `WHERE` and `ORDER BY` clauses.
- Number of columns returned and row size.
- `RowMapper` and conversion overhead.
- Processor/writer execution time.
- Cursor holdability and isolation level.
- Network latency between the batch node and the database.

Select only the columns you need; avoid `SELECT *` if the table has BLOB/CLOB columns or many large unnecessary columns.

## Query Timeout, Max Rows, and Warnings

`JdbcCursorItemReader` supports JDBC query-related settings, depending on the builder/version:

- `queryTimeout`: limits statement execution time as supported by the driver.
- `maxRows`: caps the number of returned rows if business logic needs to limit the read set.
- `fetchSize`: hint for rows fetched per batch.
- `ignoreWarnings`: determines how SQL warnings are handled per reader configuration.
- `verifyCursorPosition`: checks that the mapper does not move the cursor itself.

These limits do not replace timeouts at the connection pool, socket, or database server layer. If a query hangs due to a lock or network issue, timeouts are needed at the appropriate layer.

Do not set `maxRows` just to make a job run faster if it causes data loss. If batching is needed, use a cutoff, partitioning, or a business limit recorded in `JobParameters`.

## Reading and Writing the Same Database

A common pattern is a cursor reading from a source table, a processor transforming items, and a writer writing to a target table:

```text
JdbcCursorItemReader
        |
        v
ItemProcessor
        |
        v
JdbcBatchItemWriter
        |
        v
Target table
```

If the reader and writer use the same datasource but the reader uses a separate connection by default, the writer transaction does not necessarily govern the cursor query. You should consider:

- Do the two connections have different isolation levels?
- Does the query read rows that the writer is updating?
- Does the writer modify columns used in the cursor's `WHERE` clause?
- Can deadlocks or lock contention occur?
- On restart, will the query still return the original set of rows?

Risk example: the cursor queries `WHERE status = 'READY' ORDER BY id`, while the writer updates `status = 'DONE'` on the same table. If the cursor is reopened after a restart, rows already updated to `DONE` may no longer appear in the query result; the checkpointed row count may no longer map to the right position. Use a more stable input set, such as claiming a `batch_id` before reading or copying keys to be processed into a staging table.

### Do Not Use Positional Offset/Checkpoint on a Mutable Result Set

Restarting by the count of rows read assumes the query result has stable ordering and contents. If rows are deleted or filter conditions change, position N may point to a different item. For mutable sources, use keyset/watermark positioning or a snapshot manifest for stable positioning.

## Cursor Reader vs. Paging Reader

Both `JdbcCursorItemReader` and `JdbcPagingItemReader` read database data item by item, but they manage state and database interaction differently.

| Criterion | Cursor reader | Paging reader |
| --- | --- | --- |
| Query pattern | Single query holding an open cursor/ResultSet | Multiple queries per page |
| Connection | Typically keeps the cursor connection open for the whole step | Typically executes queries per page and releases statement/connection per query lifecycle |
| Restart condition | Reopens query and restores cursor position | Uses sort key/page state to continue |
| Best suited for | Databases/drivers with strong cursor support needing sequential reads | Large datasets needing page-by-page queries or keyset-style continuation |
| Resources | Holds cursor/connection long-term | More query round trips, less reliance on long-lived cursors |
| Changing data | Snapshot/cursor semantics depend on the database | Page boundaries can also be affected if sort keys/dataset change |

There is no single best choice for all databases. A cursor is often efficient when the driver streams well and the query result is stable. Paging fits when you need page-by-page queries and have a reliable sort key. Evaluate against your actual workload, driver, indexes, and isolation.

## Multiple Cursors or Multiple Steps

A job can have multiple steps, each using its own cursor reader. Assign distinct reader names so states do not overwrite each other, and allocate enough connection pool capacity for steps that may run concurrently.

Do not share the same `JdbcCursorItemReader` instance across multiple steps or multiple concurrent `StepExecution`s. The reader holds a cursor, `ResultSet`, and current position; this state belongs to a single execution.

If parallel queries are needed, create a separate reader per partition or step scope. Each reader must have appropriate SQL/parameters/resources and isolated state.

## Registering ItemStream and Scope

`JdbcCursorItemReader` implements `ItemStream`, so when configured directly as a step's reader, Spring Batch manages its lifecycle:

```java
.reader(customerCursorReader)
```

If the reader is hidden inside a wrapper that does not forward `ItemStream`, explicitly register the stream delegate via `.stream(...)` or have the wrapper implement/forward `ItemStreamReader<T>`.

The reader should usually be `@StepScope` when SQL or parameters depend on `JobParameters`/`ExecutionContext`. This defers reader creation until the step execution has its context.

Do not create a mutable singleton reader and use it concurrently across multiple executions. Each step execution needs its own reader state and cursor.

## Transaction Manager and Datasource

A chunk step is configured with a `PlatformTransactionManager`. The database writer should use the datasource corresponding to that transaction manager if you want writes to participate in the chunk transaction.

```java
@Bean
Step readCustomersStep(
        JobRepository jobRepository,
        @Qualifier("businessTransactionManager") PlatformTransactionManager transactionManager,
        JdbcCursorItemReader<Customer> customerCursorReader,
        ItemProcessor<Customer, CustomerSummary> summaryProcessor,
        JdbcBatchItemWriter<CustomerSummary> summaryWriter) {

    return new StepBuilder("readCustomersStep", jobRepository)
            .<Customer, CustomerSummary>chunk(200, transactionManager)
            .reader(customerCursorReader)
            .processor(summaryProcessor)
            .writer(summaryWriter)
            .build();
}
```

If `JobRepository` uses a different datasource/transaction manager than the business writer, understand how metadata transactions and business transactions coordinate. A chunk might commit business output and fail when updating metadata on another resource, or vice versa, depending on transaction manager configuration. Do not assume multiple datasources automatically form a distributed transaction.

With a local transaction manager, a transaction usually protects only a single transactional resource. If atomicity across multiple databases or between a database and files/messages is required, consider outbox, staging, compensation, or an appropriate distributed transaction.

## Testing Cursor and Transactions

Tests should run against a database/driver close to production because cursor holdability, fetch size, isolation, and auto-commit can differ across H2, PostgreSQL, Oracle, SQL Server, and other JDBC drivers.

### Testing Sequential Reading

Create a fixture table with a unique key, open the reader, and verify:

- Rows are returned in `ORDER BY` order.
- Each row is returned only once during a normal run.
- `read()` returns `null` at EOF.
- The mapper does not move the cursor itself.
- The reader closes the connection/statement/result set when the step finishes.

### Testing Chunk Commits

Run the step with a small chunk size, such as 2 or 3. After each chunk, verify the writer committed the expected number of rows and the step continues reading the cursor until EOF. Verify the cursor still works after multiple commits on the actual driver.

### Testing Rollback

Inject a writer test double or constraint violation in one chunk. Verify database changes from the current chunk roll back under the transaction manager, while previously committed chunks remain intact. Observe reader retry/buffering per step configuration; do not assume database rollback rewinds the cursor.

### Testing Restart

Let the job read several chunks and then fail. Restart with the same identifying `JobParameters` and verify the reader:

- Reopens the same SQL and parameters.
- Uses the same reader name.
- Resumes from the committed checkpoint.
- Neither drops nor duplicates rows.
- Produces the same result ordering thanks to a stable `ORDER BY`.

Also test a case where the source table changes between runs to confirm the job detects or prevents restarting on an incompatible dataset.

### Testing Separate Connection vs. Shared Extended Connection

If using the default separate connection, verify the cursor remains open across chunk commits and the connection is released when the step finishes. If shared extended connection is enabled, run tests on the actual production driver to verify holdable cursors survive commits and resources are not closed prematurely.

### Testing the Connection Pool

Run multiple jobs concurrently and monitor active connections. Verify the pool has enough capacity for cursor connections plus transaction connections and repository connections. Tests should include timeouts to detect pool starvation.

### Testing Isolation and Concurrent Updates

In another transaction, insert/update/delete rows while the cursor is reading. Observe results under the database's isolation level. Use this test to prove actual snapshot semantics rather than relying on generic assumptions about JDBC cursors.

## Common Pitfalls

### Assuming the Cursor Participates in the Chunk Transaction

By default, the reader uses a separate connection. The cursor query does not inherently belong to the transaction the writer uses. Understand connection ownership and isolation.

### Assuming Rollback Rewinds the ResultSet

Cursor position is state of the JDBC `ResultSet`, not a row update inside the writer transaction. Let Spring Batch manage buffering/checkpoint/restart; do not manually call `previous()`.

### Using Shared Connection Without the Proxy

`useSharedExtendedConnection(true)` requires `ExtendedConnectionDataSourceProxy` and a driver supporting holdable cursors. Missing either requirement can cause the cursor to close after commit.

### Missing a Stable ORDER BY

Query ordering can change across runs/restarts. Sort by a unique key or a unique combination of keys.

### Query Returning a Mutable Dataset

Rows inserted/deleted or filter condition changes can cause positional checkpoints to mismatch. Use a cutoff, staging, snapshot, or manifest.

### RowMapper Calling next()

The reader has already moved the cursor to the current row. A mapper calling `next()` will skip data and corrupt cursor position. Map only the current row.

### Holding Cursors Too Long and Exhausting the Connection Pool

A cursor connection lives for the duration of the step. Account for pool capacity, timeouts, and concurrency; close readers properly via lifecycle.

### Confusing Fetch Size with Chunk Size

Fetch size is a hint to the driver; chunk size is Spring Batch's transaction unit. Choose them independently based on driver and workload.

### Disabling saveState While Expecting Restart

Without a reader checkpoint, the reader cannot resume at the exact position via its built-in mechanism. Enable state and keep the reader name stable if restart is needed.

### Changing SQL/Parameters on Restart

Changing query results makes checkpoints point to different rows. Keep identifying parameters, cutoffs, and SQL semantics stable.

### Sharing One Reader Instance Across Multiple Executions

The cursor and read position are mutable state. Use `@StepScope` or a separate instance per execution/partition.

## Design Principles

When reading a database via a cursor in Spring Batch, determine:

1. Does the query have an `ORDER BY` on a unique key or unique combination of keys?
2. Is the row set stable throughout the job and across restarts?
3. Does the reader's default separate connection meet requirements?
4. Is `useSharedExtendedConnection` truly necessary?
5. If using a shared connection, are the datasource proxy and holdable cursors supported?
6. Do the chunk transaction and cursor connection have the expected isolation/visibility?
7. Does the writer use the matching transaction manager/datasource?
8. Are `fetchSize`, `queryTimeout`, and pool capacity appropriate for the driver/workload?
9. Are the reader name, SQL parameters, and `saveState` stable on restart?
10. Does the `RowMapper` read only the current row without moving the cursor?
11. Have retry/rollback been tested on the real step?
12. Does monitoring track cursors, connection duration, pool usage, and query time?

For most sequential batch reads, start with `JdbcCursorItemReader` using its default separate connection, a deterministically ordered query, a stateless `RowMapper`, and `saveState(true)`. Only enable shared extended connection when the database/driver supports it and there is a specific need for transaction/connection sharing. Keep the dataset stable via cutoffs or staging, size the connection pool adequately, and test commit, rollback, and restart on the actual production database.

## Key Takeaways

`JdbcCursorItemReader` opens a SQL cursor/`ResultSet` and returns one row at a time via `read()`, usually using a `RowMapper` to map objects. The cursor is a resource that lives for the duration of the step, whereas chunk transactions commit/roll back per group of items. By default, the reader uses a separate connection so the cursor is not closed by chunk commits; consequently, the SELECT is not inherently in the same transaction as the writer. Sharing a connection requires enabling `useSharedExtendedConnection`, using `ExtendedConnectionDataSourceProxy`, and a driver supporting holdable cursors across commits. Rollback does not rewind the `ResultSet`; Spring Batch manages buffering/checkpoints and restart. Keep queries ordered by a unique `ORDER BY`, keep parameters and datasets stable, enable `saveState`, preserve the reader name, choose an appropriate fetch size, and size the connection pool for long-running cursors. Test isolation, commit, rollback, restart, and shared connections on the actual production JDBC driver/database.
