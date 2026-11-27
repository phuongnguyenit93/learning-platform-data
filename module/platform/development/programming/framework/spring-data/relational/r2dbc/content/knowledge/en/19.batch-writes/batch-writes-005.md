# Splitting Data into Groups by Row Count or Parameter Count

## 1. Why split data into groups?

When writing many records with Spring Data Relational R2DBC, sending each small operation individually can cause numerous round-trips between the application and the database. On a large dataset, the overhead of creating statements, sending requests, awaiting responses, and managing transactions can account for a significant share of processing time.

Splitting data into groups (chunking) bounds the amount of data placed into each write unit. A group can be bounded by:

- **Maximum row count:** each group contains at most N records.
- **Maximum parameter count:** total bind parameters in a statement do not exceed a chosen limit.
- **Both criteria:** a group closes when either the row limit or parameter limit is reached, whichever comes first.

For example, an import has 12,000 rows. If you choose 400 rows per group, the pipeline creates 30 groups. If each row requires 8 parameters and the SQL has 2 fixed parameters, a single 400-row multi-row INSERT needs 3,202 parameters. If the driver or database has a lower limit, you must reduce the number of rows per statement.

The goal is not to build the largest possible group. Oversized groups can exceed bind parameter limits, increase memory usage, produce huge statements, hold transactions open too long, or cause a single failure to discard more work. Undersized groups increase round-trips and coordination overhead.

Distinguish three concepts:

1. **Application-layer chunking:** splitting a Flux or collection into groups.
2. **R2DBC-layer batching:** sending multiple value sets for the same prepared statement via Statement.add().
3. **Multi-row SQL:** generating a single statement with multiple VALUES tuples inside one statement.

These three techniques can be combined, but they are not synonymous.

## 2. Where chunking sits in the write pipeline

A write pipeline can be structured as follows:

~~~text
Input stream
    |
    v
Validate / normalize
    |
    v
Buffer into chunks
(max rows / max parameters)
    |
    v
Write one chunk
    |
    v
R2DBC Statement / SQL
    |
    v
Database
    |
    v
Commit chunk or transaction
    |
    v
Process next chunk
~~~

Chunking controls how much data is held in memory and how many rows go into one write step. It does not automatically guarantee that one chunk corresponds to one SQL statement or one transaction.

For instance, buffer(500) creates groups of up to 500 objects in Reactor. If you then call saveAll(batch), the repository implementation may still emit separate insert/update operations. If you want true batch statements, use an API/driver supporting batching and verify the emitted SQL behaves as expected.

Likewise, splitting into 500-row chunks does not mean each chunk commits independently. Wrapping the entire pipeline in one transaction keeps all chunks inside a single long transaction.

## 3. Choosing row-count criteria

Limiting by row count is the easiest approach to understand and operate when every record has a fairly uniform structure.

Example:

~~~java
Flux.fromIterable(customers)
        .buffer(500)
        .concatMap(batch -> writeBatch(batch));
~~~

buffer(500) emits a List<Customer> once 500 items accumulate, and emits a smaller final chunk if fewer than 500 items remain when the source completes.

If the source is an unbounded or non-completing Flux, a partial chunk under 500 items might never be emitted. In that case, consider time-based flushing:

~~~java
Flux.fromIterable(customers)
        .bufferTimeout(500, Duration.ofSeconds(2))
        .concatMap(batch -> writeBatch(batch));
~~~

bufferTimeout emits a chunk when either the item count or the timeout is reached, whichever happens first. This is useful for consumers receiving continuous streams. Verify your Reactor version and API.

### 3.1. When is row-count limiting appropriate?

Row-count limiting fits well when:

- Every row has a nearly fixed number of written columns.
- Row sizes are relatively uniform.
- The database/driver can handle the planned chunk row count.
- Business rules need checkpoints by record count.
- You want straightforward import/export progress tracking.

For example, a product_prices table has 5 columns written per row. A 200-row chunk has predictable parameter sizing. If rows contain large JSON or BLOBs, a row count limit alone may be insufficient because payload sizes vary dramatically.

### 3.2. Choosing an initial batch size

There is no universally right batch size for all databases. You can start testing with groups such as 50, 100, 250, or 500 rows, then measure:

- Write duration per chunk.
- Rows per second.
- Payload size.
- Connection hold duration.
- Transaction duration.
- Application memory.
- Lock waits and query latency.
- Timeout/error rates.

These numbers are only starting points for experimentation. A table with small rows and few indexes can handle larger chunks than a table with many indexes, triggers, or large values.

Increase batch size incrementally while keeping the workload constant when comparing. When throughput plateaus while latency, memory, or lock waits climb, the chunk size may already have passed the sweet spot.

## 4. Choosing bind-parameter-count criteria

Databases and drivers typically impose a limit on the number of parameters in a single statement or execution. Exact limits depend on the engine, protocol, driver, and version.

A multi-row INSERT looks like:

~~~sql
INSERT INTO inventory (sku, quantity, warehouse_id)
VALUES
    (:sku0, :quantity0, :warehouse0),
    (:sku1, :quantity1, :warehouse1),
    (:sku2, :quantity2, :warehouse2);
~~~

Each row needs 3 parameters. With N rows, the statement needs roughly 3 × N parameters, excluding any other fixed parameters.

If a statement has:

- P parameters per row.
- F shared fixed parameters.
- M as the safe parameter limit per statement.

Then the maximum row count by parameters is:

\[
N_{max} = \left\lfloor \frac{M-F}{P} \right\rfloor
\]

The practical limit should take the minimum of the row configuration and the parameter limit:

\[
N_{chunk} = \min(N_{configured}, N_{max})
\]

Illustrative example: each row needs 7 parameters, the statement has 2 fixed parameters, and the safe statement limit is configured at 2,000 parameters:

\[
N_{max} = \left\lfloor \frac{2000-2}{7} \right\rfloor = 285
\]

If the row-based batch configuration is 500, the multi-row INSERT chunk must drop to at most 285 rows under this parameter budget.

This is a limit calculation, not a guarantee that 285 rows is the optimal batch size. A lower limit may still be required due to payload size, execution time, or transaction duration.

## 5. Determining actual parameters per row

Not every row has the same parameter count. A write operation may require:

- Business column values.
- Tenant ID or owner ID.
- Audit actor and timestamp if bound in SQL.
- Version for optimistic locking.
- Filter values or additional conditions.
- Shared parameters in a WHERE clause.

If SQL has 6 parameters per row and 3 shared parameters, the total parameter count of the multi-row statement is:

~~~text
parameter_count = row_count × 6 + 3
~~~

For data with optional columns, parameter counts can vary with row shape. Two options exist:

1. Use one uniform SQL shape and bind NULL for absent fields, if schema and semantics permit.
2. Group rows of identical shape so each statement shares the same parameter structure.

Never omit a parameter just because its value is null. When binding null, use the null-binding API with the proper Java/SQL type, such as bindNull(index, String.class), matching your driver and Spring Data APIs.

For multi-row SQL, count total parameters across all rows in the statement. For R2DBC batches using Statement.add(), each binding set uses the parameter count of one execution; parameter count does not simply multiply by row count like a single multi-row SQL query. Calculate these two strategies separately.

## 6. Distinguishing R2DBC Statement batching from multi-row INSERT

Two techniques are frequently both called batch inserts, yet transmit data differently.

### 6.1. Statement.add(): multiple value sets for the same SQL

The R2DBC SPI provides Statement.add() to append the current binding set to the same statement's batch. Each execution uses the same SQL with a different parameter set.

Conceptual example with PostgreSQL:

~~~java
Statement statement = connection.createStatement(
        "INSERT INTO inventory (sku, quantity) VALUES ($1, $2)"
);

statement.bind(0, "SKU-001")
        .bind(1, 10)
        .add();

statement.bind(0, "SKU-002")
        .bind(1, 20);

Publisher<? extends Result> results = statement.execute();
~~~

In this example:

- The SQL has only two placeholders.
- Each binding set has two parameters.
- add() appends the current value set to the batch.
- The final binding set is kept to execute with the batch.
- Bind indices in the R2DBC SPI are zero-based; SQL placeholder syntax depends on the driver.

Statement.add() fits when the same INSERT/UPDATE runs across many rows. The driver can optimize batch transmission, though you should not assume it always becomes a single multi-row SQL query or a single network round-trip. Verify exact behavior with your driver.

### 6.2. Multi-row INSERT: multiple VALUES in one SQL

Multi-row INSERT constructs one SQL query containing multiple tuples:

~~~sql
INSERT INTO inventory (sku, quantity)
VALUES
    ($1, $2),
    ($3, $4),
    ($5, $6);
~~~

With 3 rows and 2 columns, the statement has 6 parameters. As row count grows, placeholder count grows with the number of rows.

The advantage is one statement expressing multiple rows in a single SQL command. The downside is longer SQL text and total parameters growing linearly with row count.

Placeholder syntax, statement limits, and generated value support depend on the database/driver. Never copy PostgreSQL's $1 to H2, SQL Server, or another driver without adapting it.

### 6.3. Comparison

| Criterion | Statement.add() batch | Multi-row INSERT |
|---|---|---|
| SQL | One fixed SQL template | SQL with multiple VALUES |
| Parameter count | Per binding set | Scales with row count |
| SQL text size | Typically fixed | Scales with row count |
| Rows per send | Multiple binding sets | Multiple tuples in one statement |
| Generated values | Depends on driver and individual Results | Depends on RETURNING/generated-value support |
| Driver capability | Must support batch add() | Must support multi-row syntax |
| Use when | Repeating the same operation across many rows | Wanting one multi-tuple INSERT statement |

Neither technique is universally faster. Benchmark against your actual driver/database, schema, and row size.

## 7. saveAll() does not mean one bulk SQL statement

Spring Data R2DBC repositories provide saveAll() to accept multiple entities as a Publisher or Iterable. This API is convenient for reactive multi-entity processing, but do not assume it always emits a multi-VALUES INSERT or a Statement.add() batch.

Depending on the implementation and version, persistence may still occur via save operations per entity. In some cases, each row can generate a separate statement. Inspect actual SQL or check the Spring Data version/documentation before drawing conclusions about batching.

Example:

~~~java
Flux<Customer> saved =
        customerRepository.saveAll(
                Flux.fromIterable(batch)
        );
~~~

This snippet expresses a flow saving multiple entities. By itself it does not state whether the database receives one multi-row INSERT, one batch statement, or multiple separate statements.

If a specific transmission strategy is required, use the appropriate explicit batch/SQL API and verify with the real driver. Never use the number of entities passed to saveAll() as proof of how many statements are sent.

## 8. Grouping by both row count and parameter count

In real systems, apply both row and parameter limits together. For fixed-shape rows, pre-calculate the maximum row count:

~~~java
int rowsByParameters =
        (maxParameters - fixedParameters) / parametersPerRow;

int effectiveBatchSize =
        Math.min(configuredMaxRows, rowsByParameters);
~~~

Verify rowsByParameters is greater than 0. If a single row already exceeds the parameter budget, lowering the row count cannot solve it; change the SQL shape or write strategy.

For rows with varying parameter counts, build chunks dynamically against a cumulative budget:

~~~text
current_batch = []
current_parameters = fixed_parameters

for each row:
    row_parameters = count_parameters(row)

    if row_parameters + fixed_parameters > max_parameters:
        reject row or use another SQL shape

    if current_batch is not empty and
       (row_count + 1 > max_rows or
        current_parameters + row_parameters > max_parameters):
        flush current_batch
        start a new batch

    append row
    increase current_parameters

flush the final non-empty batch
~~~

This pseudocode describes the algorithm. When implementing it, re-account for fixed parameters per statement and handle failing rows according to your import policy.

### 8.1. Dynamic batch calculation example

Suppose:

- Maximum 300 rows by configuration.
- Budget of 1,800 bind parameters per statement.
- Normal rows have 5 parameters each.
- 3 fixed parameters.

Then:

\[
N_{max} = \left\lfloor \frac{1800-3}{5} \right\rfloor = 359
\]

The row-based limit is 300, so the effective batch size is 300.

If each row has 8 parameters:

\[
N_{max} = \left\lfloor \frac{1800-3}{8} \right\rfloor = 224
\]

The effective batch size drops to 224.

For a Statement.add() batch, each binding set still has only 8 parameters in this example. You must respect the per-execution parameter limit and driver batch/payload limits, rather than multiplying 8 by row count to assume one statement with 8 × N bind parameters.

## 9. Chunking with Reactor buffer

A simple row-count pipeline:

~~~java
public Mono<Void> importCustomers(Flux<CustomerInput> input) {
    return input
            .map(this::toCustomer)
            .buffer(250)
            .concatMap(batch -> writeBatch(batch))
            .then();
}
~~~

buffer(250) emits a group of up to 250 rows. concatMap processes each batch sequentially, waiting for the current batch to complete before moving to the next. This caps concurrent running batches within the subscription at one and preserves group order.

If flushing by count or time is needed:

~~~java
public Mono<Void> importCustomers(Flux<CustomerInput> input) {
    return input
            .map(this::toCustomer)
            .bufferTimeout(250, Duration.ofSeconds(1))
            .concatMap(this::writeBatch)
            .then();
}
~~~

Keep in mind bufferTimeout suits long-lived or continuous streams. For an existing finite collection, buffer(maxRows) is usually sufficient.

### 9.1. Avoid collectList on large inputs

Avoid:

~~~java
return input.collectList()
        .flatMap(this::writeAll);
~~~

This retains the entire input in memory before writing. If the dataset has millions of rows, heap usage can spike or run out of memory.

Use buffer to hold only active chunks. However, if downstream runs multiple chunks concurrently, each active chunk still occupies memory simultaneously. Concurrency must therefore also be bounded.

### 9.2. Bounding concurrent batches

If batches are independent and the database tolerates concurrency, you can use flatMap with bounded concurrency:

~~~java
return input
        .map(this::toCustomer)
        .buffer(200)
        .flatMap(batch -> writeBatch(batch), 2)
        .then();
~~~

In this example, at most two inner batch-writing publishers are subscribed concurrently within this subscription. This is not an application-wide limit; multiple concurrent requests or import jobs multiply total concurrency.

Use concatMap when ordering and simple control matter. Use bounded flatMap when batches are independent, safe to run in parallel, and database capacity has been measured. Avoid unbounded flatMap on large sources.

## 10. Decoupling batch size from transaction size

Chunk size and transaction boundaries are two separate decisions.

### 10.1. One transaction for the whole import

~~~java
Mono<Void> work =
        input.buffer(250)
                .concatMap(this::writeBatch)
                .then();

return transactionalOperator.transactional(work);
~~~

Here each chunk is processed sequentially, yet all sit inside one transaction. If the last chunk fails, the entire import can roll back.

Pros:

- Atomicity across the entire import.
- No partially committed state if the transaction rolls back cleanly.

Cons:

- Transaction can be very long.
- A connection is held throughout the entire process.
- Locks/snapshots may persist for a long time.
- Rollback can be expensive.
- A late failure discards earlier work.
- Transaction logs/WAL and database resource usage can grow.

Use this only when business rules genuinely require all data to commit or roll back together.

### 10.2. One transaction per chunk

~~~java
Flux<Void> chunks =
        input.buffer(250)
                .concatMap(batch ->
                        writeBatch(batch)
                                .as(transactionalOperator::transactional)
                                .then()
                );

return chunks.then();
~~~

Each chunk runs inside its own transaction. When a chunk succeeds, it commits before moving to the next chunk.

Pros:

- Shorter transactions.
- Connections released after each chunk.
- Smaller rollback blast radius.
- Easy to checkpoint and resume from incomplete chunks.

Cons:

- Import can partially commit.
- Requires progress tracking or idempotency design.
- If a later chunk fails, earlier chunks remain persisted.
- Requires a defined retry policy for failed chunks.

This is often the practical option for large imports if business rules accept partial progress.

### 10.3. Parallel chunks with separate transactions

~~~java
return input.buffer(200)
        .flatMap(
                batch -> writeBatch(batch)
                        .as(transactionalOperator::transactional),
                2
        )
        .then();
~~~

Each inner publisher gets its own transaction. Up to two chunks can be processing in this subscription. Completion order does not necessarily match input order.

Use this only when chunks are data-independent or the database handles conflicts appropriately. If two chunks update the same row, races, lock waits, or deadlocks can occur.

Never put parallel flatMap inside a single shared transaction assuming each branch gets its own connection. Operations in the same transaction typically share the connection bound to that transaction; many drivers do not support multiple concurrent statements on one connection.

## 11. Sizing chunks by payload, not just row count

Two chunks can both have 100 rows yet differ drastically in data size:

- Group A: each row has 4 short columns.
- Group B: each row has large JSON or long text.
- Group C: some rows have binary payloads.

Beyond row count and parameter count, consider:

- Total payload bytes.
- Generated SQL size.
- Driver and database message/packet limits.
- Memory needed to hold the chunk.
- Serialization/binding time.
- Transaction duration.
- Limits of upstream request or message broker payloads.

If row sizes vary widely, add maxBytes to the chunking algorithm. This prevents a chunk with few rows from carrying an oversized payload.

Do not pick an arbitrary byte limit without checking driver/protocol and database behavior. Measure actual sizes using representative data and leave a safety margin.

## 12. Batch insert with R2DBC SPI

When repeating the same SQL, Statement.add() can be used directly. The example below illustrates using Spring's ConnectionFactoryUtils to obtain a connection that participates in the current reactive transaction:

~~~java
public Flux<Integer> insertBatch(List<InventoryRow> rows) {
    String sql = """
            INSERT INTO inventory (sku, quantity)
            VALUES ($1, $2)
            """;

    return Flux.usingWhen(
            ConnectionFactoryUtils.getConnection(connectionFactory),
            connection -> {
                Statement statement = connection.createStatement(sql);

                for (int i = 0; i < rows.size(); i++) {
                    InventoryRow row = rows.get(i);

                    statement.bind(0, row.sku())
                            .bind(1, row.quantity());

                    if (i < rows.size() - 1) {
                        statement.add();
                    }
                }

                return Flux.from(statement.execute())
                        .concatMap(result ->
                                Mono.from(result.getRowsUpdated())
                        );
            },
            connection ->
                    ConnectionFactoryUtils.releaseConnection(
                            connection, connectionFactory),
            (connection, error) ->
                    ConnectionFactoryUtils.releaseConnection(
                            connection, connectionFactory),
            connection ->
                    ConnectionFactoryUtils.releaseConnection(
                            connection, connectionFactory)
    );
}
~~~

This example uses PostgreSQL placeholders. Other drivers may use different placeholders; R2DBC bind indices remain zero-based. Import ConnectionFactoryUtils, ConnectionFactory, Statement, Mono, Flux, and the relevant data types.

Points to note:

- ConnectionFactoryUtils.getConnection can retrieve the connection already bound in the current reactive transaction.
- releaseConnection respects connections managed by the transaction manager and avoids closing a connection still active in a transaction.
- Calling raw connectionFactory.create() inside a Spring transaction risks acquiring an independent connection outside the transaction-bound resource.
- Statement.add() is the R2DBC SPI batch API, though the driver must properly support it.
- getRowsUpdated() is reactive; result count and affected row reporting depend on the driver.
- Generated IDs are not automatically returned just by calling getRowsUpdated().

For production code, verify driver behavior and error/cleanup handling for your exact Spring Framework and R2DBC SPI versions. Do not copy examples while omitting transaction resource management.

### 12.1. Batching with null bindings

If a row contains null values, use bindNull with the proper Java type:

~~~java
statement.bind(0, row.sku());

if (row.description() == null) {
    statement.bindNull(1, String.class);
} else {
    statement.bind(1, row.description());
}
~~~

Do not bind null as a normal Java value when the API requires an explicit type. The type must be compatible with the column and driver.

### 12.2. Batch update

The same mechanism works for repeated UPDATEs:

~~~sql
UPDATE inventory
SET quantity = $1
WHERE sku = $2
~~~

Each binding set supplies a different quantity and sku. Inspect rows-updated results to detect missing rows or version conflicts if required by business rules.

## 13. Multi-row INSERT and parameter limits

If using one multi-row INSERT, generate placeholders for the row count. Three rows with two columns each:

~~~sql
INSERT INTO inventory (sku, quantity)
VALUES
    ($1, $2),
    ($3, $4),
    ($5, $6)
~~~

Total parameters: 6. With 300 rows and 8 columns, parameter count reaches 2,400, before fixed parameters.

Construct the SQL from fixed structure and bind all values. Never put input values directly into SQL strings. Table and column names must be code-defined identifiers, never taken directly from users.

General placeholder generation pattern:

~~~text
for each row i:
    create one tuple with P placeholders
    bind row[i] values to the corresponding parameter indexes

join all tuples with commas
execute the statement
~~~

Exact placeholder syntax is dialect/driver-specific. Use a tested SQL builder or helper instead of scattering placeholder string concatenation across services.

### 13.1. Is the parameter limit per statement or per batch?

This distinction is critical:

- With multi-row INSERT, all tuples sit in the same statement. Parameter count grows with row count.
- With Statement.add(), each binding set has its own parameter count; multiple sets are added to the batch. The per-execution parameter limit does not necessarily equal the sum of parameters across the entire batch.

Even though Statement.add() does not multiply parameter count by row count like multi-row SQL, batches still face limits on binding set count, payload size, memory, execution duration, and driver capabilities. Measure and verify actual limits.

Do not take a database limit meant for one statement form and apply it blindly to a different batching mechanism.

## 14. Database and driver limits

Parameter limits vary by engine and version. For example, SQL Server typically caps parameters per stored procedure/batch, SQLite has version/build-dependent host parameter limits, and PostgreSQL is constrained by protocol and driver limits. Limits can change across versions and driver dispatch strategies.

When evaluating, check:

- Database engine/version.
- R2DBC driver/version.
- Driver placeholder limits.
- Statement bind parameter limits.
- Packet/message limits.
- SQL length limits.
- Row or batch item limits.
- Generated value return capabilities.
- Timeout and transaction behavior.

Do not hard-code one universal maximum for all environments. Configure safe limits below verified thresholds and re-check after upgrading databases or drivers.

## 15. Error handling and partial success

A chunk can fail due to:

- Unique constraints.
- Foreign keys.
- Not-null/check constraints.
- Wrong data types or length overflows.
- Deadlocks or lock timeouts.
- Connection resets.
- Query/statement timeouts.
- Parameter limits.
- Database unavailability.

Define policies by error category:

| Error category | Common handling |
|---|---|
| Single-row validation error | Filter out the row or write to an error report |
| Duplicate key | Skip, update/upsert, or reject per business rules |
| Missing foreign key | Retry after dependency is written or reject |
| Deadlock/serialization failure | Bounded retry if transaction is idempotent |
| Parameter limit | Split into smaller chunks |
| Payload too large | Lower max bytes or process separately |
| Database unavailable | Backoff/retry within deadline |
| Schema/type mismatch | Stop batch and fix mapping/schema |

If a batch statement runs outside a transaction and the driver/database does not guarantee whole-batch atomicity, partial success can occur. Never assume either all rows were written or all rows failed.

If a chunk must be atomic, wrap writeBatch in a reactive transaction. On failure, let errors propagate past the transaction boundary to roll back. If an error is swallowed via onErrorResume into completion inside the transaction, the transaction may commit prior changes.

### 15.1. Do not blindly retry the whole import

If the first 20 chunks committed and chunk 21 failed, retrying the whole import can create duplicates or re-apply updates. Design for idempotency:

- Unique business keys.
- Upserts with clear semantics.
- Import job ID and chunk sequence.
- Checkpointing committed chunks.
- Deduplication keys.
- Retrying only the failed chunk when data allows.

For non-idempotent creation operations, use duplicate-prevention keys or check state before retrying.

### 15.2. Per-row error reporting

When a chunk holds hundreds of rows and only one row is invalid, decide whether to roll back the whole chunk or accept valid rows.

Two strategies:

- **Atomic chunk:** one bad row rolls back the entire chunk. Simple and consistent.
- **Per-row isolation:** isolate bad rows and persist valid ones. Requires more executions and clear rules.

You can validate data before hitting the database to catch formatting errors early. However, application validation does not replace database constraints since concurrent writes can still conflict.

## 16. Data ordering and foreign key relationships

Chunking can alter processing order if parallel flatMap is used.

If a child table references a parent table, ensure parent rows are created before child rows, or that the database has appropriate deferred constraints and transaction design.

Example:

~~~text
Chunk 1: Orders 1..200
Chunk 2: Order lines 1..800
~~~

Do not run both chunk types concurrently if order lines could be written before their parent orders exist.

Organize in phases:

1. Write parent rows.
2. Collect/map generated IDs.
3. Write child rows in batches.
4. Commit according to the chosen transaction boundary.

If data is partitioned by key, ensure rows belonging to the same aggregate land in the same chunk to avoid concurrent updates to one aggregate.

With flatMapSequential, emission order is preserved while inner publishers still execute concurrently. It does not guarantee SQL execution order at the database.

## 17. Generated IDs and batch results

A batch insert may need to return generated IDs per row for creating child rows or building a response.

Do not assume Statement.add() with getRowsUpdated() returns generated keys for every binding set. Retrieving generated values depends on the driver, SQL dialect, and RETURNING/generated-value capabilities.

Options:

- Use application-generated IDs up front, such as UUIDs.
- Use multi-row INSERT with RETURNING if supported by database/driver.
- Insert parent rows and re-query by a unique business key.
- Use per-row inserts when generated keys are needed through explicitly supported driver behavior.
- Design batch APIs to return a business key → generated ID mapping.

Do not re-query solely by name or non-unique fields. Use a constrained business key to map results accurately.

When generated IDs and batch ordering matter, write integration tests against the exact database/driver to confirm Result order and per-row mapping. Never infer ordering from a different driver.

## 18. Choosing transaction boundaries for large imports

A large import can span tens of thousands of chunks. Consider:

| Strategy | Atomicity | Transaction duration | Resumability |
|---|---|---|---|
| One transaction for whole import | Entire import commits/rolls back together | Long | Hard on late failures |
| One transaction per chunk | Atomic per chunk | Shorter | Easy to checkpoint |
| One transaction per row | Atomic per row | Many transactions | Easy error isolation, high round-trip cost |
| No explicit transaction | Depends on driver/database/autocommit | Unpredictable | Partial success possible |

For multi-million-row imports, whole-import transactions usually place heavy pressure on the database. One transaction per chunk is usually easier to operate if business rules accept incremental progress.

If business rules require users to see the entire import only after completion, write rows into a staging table keyed by job ID, then validate and promote in a controlled transaction or via publication status. This is an explicit business design rather than holding one massive transaction open solely to hide in-progress data.

## 19. Backpressure and memory during chunking

buffer(maxRows) builds a collection per chunk. It avoids holding the entire source, though memory still depends on:

- Rows per chunk.
- Object sizes.
- Concurrently executing chunks.
- Prefetch in upstream/downstream operators.
- Retry queues and backlogs.
- Driver and connection pool buffers.

With concurrency C and B rows per chunk, the application may hold roughly C × B rows in active chunks, excluding other buffers. This is a simple estimate to spot memory pressure.

For example, 500-row chunks at concurrency 4 can hold around 2,000 rows in flight. If each row contains 100 KB of JSON, memory usage becomes substantial.

Bound both batch size and concurrency. For unbounded sources, use bufferTimeout or appropriate windowing so groups are not held indefinitely. When downstream is slow, Reactor backpressure regulates demand within a chain, though multiple independent subscriptions can still create high aggregate load.

## 20. Chunk-level timeouts and retries

Configure timeouts for chunk characteristics. A 500-row batch needs more time than a single-row insert.

Example:

~~~java
Mono<Integer> writeChunk(List<Customer> batch) {
    return writeBatch(batch)
            .timeout(Duration.ofSeconds(10));
}
~~~

This timeout is illustrative; actual values must reflect latency distributions and import deadlines. When a timeout triggers inside a transaction, verify cancellation/rollback behavior on your driver and database.

Chunk-level retry:

~~~java
Retry retryPolicy = Retry.backoff(3, Duration.ofMillis(200))
        .maxBackoff(Duration.ofSeconds(3));

return writeBatch(batch)
        .retryWhen(retryPolicy);
~~~

Retry only transient errors and operations safe to repeat. If a batch may have committed before the client received a response, retrying can create duplicates. Use idempotency keys or upserts with clear semantics.

Do not retry validation errors, non-recoverable constraint violations, or SQL syntax errors. Parameter limit errors require shrinking batch size, not retrying the same group.

## 21. Metrics for choosing batch size

Track group-level metrics:

| Metric | Meaning |
|---|---|
| Rows per chunk | Actual rows per group |
| Parameters per statement | Total bind parameters per statement |
| Chunk duration | Time to write one chunk |
| Rows per second | Throughput |
| Chunks per second | Group completion rate |
| Batch error count | Failed chunk count |
| Retry count | Retry attempts |
| Pool acquire duration | Connection wait time |
| Transaction duration | Time spent in transaction |
| Heap / allocation | Memory pressure |
| DB lock wait / CPU / I/O | Impact on the database |

Record batch_size as a histogram/distribution or bucketed metric. Do not create dynamic tags per batch ID or import ID, as cardinality will explode uncontrollably.

Compare batch sizes like 50, 100, 250, and 500 on the same dataset and concurrency. Inspect p95/p99, throughput, DB resources, and error rates. Choose a balanced operating point rather than chasing peak throughput from a single run.

## 22. Testing chunking and batch behavior

Write dedicated tests:

### 22.1. Testing the chunking algorithm

With 1,001 input rows and maxRows 250, expect chunks of:

~~~text
250, 250, 250, 250, 1
~~~

Verify:

- No dropped rows.
- No duplicated rows.
- Order preserved if required.
- No empty trailing chunk.
- Empty input produces no statements.
- High-parameter-count rows handled correctly.

### 22.2. Testing parameter limits

With P parameters per row and limit M, verify:

- No statement exceeds M.
- Fixed parameters are accounted for.
- Variable-shape rows are counted accurately.
- A single row exceeding the limit is rejected or routed to a different SQL shape.
- Null bindings specify the right type.

### 22.3. Integration tests with the R2DBC driver

Use the real database/driver to verify:

- Statement.add() is supported.
- Multi-row SQL syntax is valid.
- Rows updated are reported accurately.
- Generated values return properly if needed.
- Constraint errors yield expected batch/transaction results.
- Transactions roll back properly when one row fails.
- Timeouts/cancellations release connections.
- Large batch sizes stay within driver limits.

H2 can validate basic standard relational SQL, but production-specific batching tests should run on your real engine and driver.

### 22.4. Testing partial progress and resume

If each chunk commits separately, test:

1. Create multi-chunk input.
2. Let the first chunk succeed.
3. Force the next chunk to fail.
4. Confirm the earlier chunk remains persisted.
5. Retry the job with the same import ID.
6. Confirm no duplicates are created and processing resumes at the proper checkpoint.

Do not rely on mocks to claim database batch atomicity. Integration tests are needed for transaction behavior.

## 23. Common pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| Large batch fails parameter limit | Multi-row statement has too many placeholders | Calculate rows × paramsPerRow + fixedParams |
| saveAll is slow despite passing a large List | Repository still executes per-entity saves | Inspect actual SQL; use a batch API when needed |
| Memory spikes with 500-row batches | Large row payloads or parallel chunks | Reduce batch size/concurrency, add max bytes |
| Final chunk never gets written | Non-completing source using count-only buffer | Use bufferTimeout or a flush policy |
| Single error discards whole import | All chunks wrapped in one transaction | Consider per-chunk transactions and checkpoints |
| Partially committed import hard to resume | Missing idempotency/checkpoints | Add job ID, chunk state, and unique keys |
| Duplicates on retry | Non-idempotent writes or lost response after commit | Use idempotency keys/upserts |
| Generated IDs map incorrectly | Driver does not return generated values as assumed | Test RETURNING or re-query by business key |
| Batch update affects wrong rows | Wrong parameter binding or bind order | Test bindings and use explicit helpers |
| Related rows fail FK constraints | Chunks processed out of parent/child order | Separate phases or group by aggregate |
| Pool pending grows | High chunk concurrency or long transactions | Reduce concurrency, measure acquire/hold times |
| Very long SQL parses slowly | Oversized multi-row statement | Reduce row count or use Statement.add |
| One bad row rolls back whole chunk | Atomic chunk is active policy | Decide whether to reject chunk or isolate rows |
| Driver lacks add() support | Varying batch capabilities | Use multi-row SQL or controlled fallback |

## 24. Process for selecting chunk size

A practical process:

1. Determine columns/parameters per row.
2. Determine fixed parameters on the statement.
3. Check database and R2DBC driver limits.
4. Pick initial maxRows based on row size and workload.
5. Compute maxRows from parameter budget.
6. Take the minimum of both limits.
7. If row shape varies, accumulate parameter count while building chunks.
8. If row size varies, add a payload byte limit.
9. Choose transaction boundary: whole import or per chunk.
10. Choose chunk concurrency within connection/database budgets.
11. Run load tests against the exact database/driver.
12. Compare throughput, p95/p99, memory, pool waits, and locks.
13. Test mid-batch failures and resumability.
14. Externalize configuration so it can be tuned per environment.
15. Re-measure after upgrading driver or database versions.

Do not hard-code one batch size if multiple data types have different profiles. Use separate settings for customer imports, event inserts, inventory updates, and batch reporting.

## 25. Implementation checklist

- [ ] Decide whether chunking uses row count, parameter count, or both.
- [ ] Distinguish Reactor chunking from driver batch statements.
- [ ] Do not assume saveAll() is a single bulk SQL statement.
- [ ] Calculate parameters per row plus fixed parameters.
- [ ] Use verified safe limits for your database/driver.
- [ ] Handle rows with varying parameter shapes.
- [ ] Bind nulls with appropriate types.
- [ ] Use Statement.add() only when supported by the driver.
- [ ] Use dialect/driver-specific placeholders.
- [ ] Bound payload bytes when row sizes vary.
- [ ] Cap concurrently running chunks.
- [ ] Define clear transaction boundaries.
- [ ] Add checkpoints/idempotency if committing per chunk.
- [ ] Handle generated IDs per driver capabilities.
- [ ] Preserve parent/child and aggregate ordering.
- [ ] Configure safe timeouts and retry policies.
- [ ] Measure rows/sec, chunk duration, pool wait, and transaction duration.
- [ ] Test parameter limits, partial success, and resumability.
- [ ] Run integration tests against the production database engine.

## 26. Conclusion

Splitting data into groups by row count or parameter count is how you bound write unit sizes in Spring Data Relational R2DBC. Row-count limiting is simple to implement with Reactor buffer, while parameter limiting requires accounting for bind values per row and fixed parameters. With multi-row INSERTs, parameters scale with row count; with R2DBC Statement.add(), each binding set carries its own parameters, though batches remain bounded by payload, memory, and driver limits.

Distinguish application-layer chunking, batch statements, and multi-row SQL. saveAll() is a multi-entity persistence API, not a promise of a bulk SQL statement. Pick batch sizes using the lower bound of max rows and parameter budget, add payload limits when needed, and benchmark against the real database and driver.

Finally, decouple chunk size from transaction size. One transaction for the entire import guarantees atomicity but can grow very long; per-chunk transactions simplify resumption while allowing partial progress. Combine backpressure, bounded concurrency, idempotency, checkpoints, metrics, and integration tests to achieve fast batch writes while keeping memory, connections, errors, and data consistency under control.
