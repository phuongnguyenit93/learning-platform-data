# Multiple Parameter Sets on a Statement and Driver Limits

When writing multiple records in Spring Data Relational R2DBC, an application can execute the same SQL statement with multiple sets of parameter values. The R2DBC SPI provides `Statement.add()` to append a new parameter set to the same `Statement`. This is useful when many rows share the same INSERT or UPDATE structure and differ only in their values.

However, multiple parameter sets on a `Statement` do not equate to a SQL statement with multiple `VALUES` tuples, nor do they guarantee that the driver sends a single packet or that the database processes everything in one transaction. Support, execution strategy, limits on the number of parameter sets, and buffering behavior depend on the driver, database, and protocol. To write large datasets reliably, you need to explicitly control batch size, bind marker count, concurrency, transactions, and error handling.

## 1. One statement, multiple parameter sets

Suppose you need to insert multiple customers into the same table:

```sql
INSERT INTO customer(name, email)
VALUES ($1, $2)
```

Each row has the same structure with `name` and `email`, differing only in values. Instead of creating a new SQL statement for each row, the R2DBC SPI lets you create one `Statement`, bind the first set of values, call `add()`, and then bind the next set of values.

```java
Statement statement = connection.createStatement("""
    INSERT INTO customer(name, email)
    VALUES ($1, $2)
    """);

statement.bind(0, "An")
    .bind(1, "an@example.com")
    .add()
    .bind(0, "Binh")
    .bind(1, "binh@example.com");
```

This example uses PostgreSQL's `$1`, `$2` bind marker syntax. SQL markers depend on the driver; other databases may use `?` or another syntax. The index passed to R2DBC SPI's `bind(int, value)` starts at 0, even when SQL markers are 1-based.

Meaning of the call chain:

1. `createStatement(...)` creates a statement with a fixed SQL query.
2. `bind(0, ...).bind(1, ...)` attaches the first parameter set.
3. `add()` finalizes the current parameter set and starts a new one.
4. Subsequent `bind` calls assign values for the new parameter set.
5. `execute()` runs the statement with the declared parameter sets.

Each set must bind all required parameters before moving to the next set. Do not leave a parameter missing or accidentally reuse a stale value.

## 2. How Statement.add() differs from multi-row SQL INSERT

Two approaches are commonly referred to as "inserting multiple rows," but they have different shapes.

### 2.1. Multiple parameter sets with Statement.add()

One SQL statement has a single group of placeholders reused across multiple value sets:

```sql
INSERT INTO customer(name, email) VALUES ($1, $2)
```

Parameter sets are added via the API:

```text
Set 1: name = An,   email = an@example.com
Set 2: name = Binh, email = binh@example.com
Set 3: name = Chi,  email = chi@example.com
```

This is the R2DBC SPI's `Statement.add()` feature. The driver decides how to transmit the parameter sets to the database.

### 2.2. One SQL statement with multiple VALUES tuples

Another SQL query can contain multiple value groups in the same statement:

```sql
INSERT INTO customer(name, email)
VALUES
    ($1, $2),
    ($3, $4),
    ($5, $6);
```

Here the SQL query has six distinct bind markers for three rows. This is a multi-row SQL INSERT. The application or framework must generate the corresponding number of `VALUES` groups and markers.

### 2.3. Comparing the two approaches

| Criterion | `Statement.add()` | Multi-row `VALUES` |
|---|---|---|
| SQL statement | One placeholder group reused | Multiple placeholder groups in SQL |
| Number of value sets | Multiple sets on the same Statement | One large parameter set for the entire SQL statement |
| Bind markers in SQL template | Fixed by the number of columns/placeholders per row | Scales with the number of rows generated in SQL |
| Support | Depends on driver support for `Statement.add()` | Depends on dialect and SQL/parameter limits |
| SQL text size | Typically does not grow with parameter set count | Grows with the number of `VALUES` tuples |
| Execution | Driver decides how to execute the sets | Database receives a single multi-row statement |
| Atomicity | Does not automatically create a transaction; verify driver/database semantics | One statement, though transaction and database semantics still apply |

Neither approach is always faster. `Statement.add()` avoids building SQL strings with thousands of placeholder groups, though the driver may buffer multiple parameter sets or execute them in its own way. Multi-row `VALUES` can reduce statement overhead but increases bind marker count and SQL size. Benchmark on your actual database and driver.

## 3. Executing a Statement with multiple parameter sets

After adding parameter sets, call `execute()` to obtain the reactive result:

```java
Publisher<? extends Result> results = statement.execute();
```

For INSERT/UPDATE/DELETE statements, you typically need to read the affected row count from `Result.getRowsUpdated()`:

```java
Flux.from(statement.execute())
    .concatMap(result -> Flux.from(result.getRowsUpdated()))
    .reduce(0L, Long::sum);
```

`execute()` is lazy under the Reactive Streams model: the statement runs when the Publisher is subscribed to. If you do not attach the Publisher to a pipeline or subscribe to it, you cannot assume data has been written.

The observed number of `Result` items and `rowsUpdated` values can depend on how the driver represents execution results. Do not assume there is always one `Result` for the whole batch or one update count per parameter set. Verify with your driver and integration tests.

### 3.1. Complete example with R2DBC SPI

The following example writes a list of customers. It uses PostgreSQL bind markers for illustration; adjust the SQL for your driver.

```java
import io.r2dbc.spi.Connection;
import io.r2dbc.spi.ConnectionFactory;
import io.r2dbc.spi.Statement;
import java.util.List;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

record CustomerInput(String name, String email) {}

Mono<Long> insertBatch(
        ConnectionFactory connectionFactory,
        List<CustomerInput> customers) {

    if (customers.isEmpty()) {
        return Mono.just(0L);
    }

    return Mono.usingWhen(
        Mono.from(connectionFactory.create()),
        connection -> {
            Statement statement = connection.createStatement("""
                INSERT INTO customer(name, email)
                VALUES ($1, $2)
                """);

            for (int i = 0; i < customers.size(); i++) {
                if (i > 0) {
                    statement.add();
                }

                CustomerInput customer = customers.get(i);
                statement.bind(0, customer.name());

                if (customer.email() == null) {
                    statement.bindNull(1, String.class);
                } else {
                    statement.bind(1, customer.email());
                }
            }

            return Flux.from(statement.execute())
                .concatMap(result -> Flux.from(result.getRowsUpdated()))
                .reduce(0L, Long::sum);
        },
        connection -> Mono.from(connection.close()),
        (connection, error) -> Mono.from(connection.close()),
        connection -> Mono.from(connection.close())
    );
}
```

In this example:

- An empty list returns 0 without acquiring a connection or building SQL.
- `Statement.add()` is called before binding each parameter set from the second set onward.
- `bindNull(1, String.class)` is used when email can be null; R2DBC requires a Java type for null values.
- `Mono.usingWhen` manages the connection on pipeline completion, error, or cancellation.
- Affected row counts are summed from the results emitted by the driver.

This example uses the R2DBC SPI directly. If the application needs to participate in a Spring-managed reactive transaction, do not assume calling `connectionFactory.create()` directly will obtain the connection bound by Spring to the transaction context. Use `DatabaseClient`, Spring's connection retrieval mechanism, or `ConnectionFactoryUtils` appropriately, and ensure the same `ConnectionFactory` is shared with the transaction manager.

### 3.2. Binding null values

Do not pass null directly to `bind`:

```java
// Do not use this for null values.
statement.bind(1, null);
```

Use `bindNull` and specify the type:

```java
statement.bindNull(1, String.class);
```

The declared type must be compatible with the column type and driver mapping. If the column does not allow NULL, the database will raise an error on execution; `bindNull` does not bypass schema constraints.

## 4. Is Statement.add() supported by every driver?

The R2DBC SPI defines `Statement.add()` for multiple parameter sets, but execution capability depends on the driver. Some drivers may not support this operation or may have specific limitations. Therefore, do not assume that simply compiling the code means every database executes batches identically.

Before using it, verify:

- Whether the driver supports `Statement.add()` in your deployed version.
- Which statement types are supported: INSERT, UPDATE, DELETE, or others.
- Whether the driver supports parameter binding for all required data types.
- Whether `execute()` emits results per parameter set or aggregated.
- What happens when a parameter set fails mid-batch.
- Whether there are limits on parameter set count or batch size.
- Whether statements work as expected within transactions and connection pools.

If the driver throws `UnsupportedOperationException` or a similar error when calling `add()`/`execute()`, choose another strategy such as sequential execution, multi-row INSERT if supported by the dialect, or a database/driver-specific bulk API.

## 5. Distinguishing Statement from Batch in the R2DBC SPI

The R2DBC SPI also has a `Batch` API, which differs from `Statement`.

- `Statement` uses one SQL query that may contain bind markers, binds values, and can add multiple parameter sets using `add()`.
- `Batch` groups multiple SQL statements into a batch using `add(String sql)`; this API does not provide the same parameter binding model as `Statement`.

Conceptual example of `Batch`:

```java
Batch batch = connection.createBatch();
batch.add("UPDATE customer SET active = false WHERE id = 10");
batch.add("UPDATE customer SET active = false WHERE id = 20");

Publisher<? extends Result> results = batch.execute();
```

The example above illustrates the API and uses fixed literals to highlight the difference. Do not concatenate user input into SQL strings passed to `Batch.add()`: doing so risks SQL injection and quoting bugs. When dynamic data must be passed, prefer `Statement` with bind parameters.

`Batch` is also driver-dependent. Not every driver supports every form of SQL batching, and `Batch` should not be treated as a safe substitute for a prepared statement with bindings.

## 6. Driver and database limits

Batch size is not just the number of rows the application wants to write. It is constrained by limits at multiple layers.

| Limit | Impact |
|---|---|
| Bind markers in a statement | Caps total parameters in one SQL query, especially for multi-row `VALUES` |
| Parameter sets in a Statement | The driver may cap or need to buffer sets added via `add()` |
| SQL length | A multi-row SQL query can exceed parser or protocol limits |
| Request/packet size | Total bound data can exceed driver, protocol, or server limits |
| Single value size | A large text/binary column can exceed SQL type or driver limits |
| Driver/client memory | The driver may buffer many values before sending or while processing the batch |
| Statement duration | An overly large batch can run slowly, time out, or hold a connection too long |
| Transaction limits | A large batch can create long transactions, heavy locking, or large WAL/undo growth |
| Database limits | Constraints, triggers, logging, locks, replication, and server resources affect write capacity |

Exact numbers depend on the database engine, database version, driver, and configuration. For instance, SQL Server's parameter limit, Oracle's expression limit in `IN` lists, and SQLite's host parameter variable limit are distinct constraints; none can be treated as a universal number for R2DBC.

Beyond hard limits, there are practical performance limits. A batch may be protocol-valid yet still hold connections too long, increase latency for other requests, or overload the database.

## 7. Calculating bind markers in multi-row INSERT

For multi-row INSERT, the number of bind markers grows with both row count and bound columns.

Suppose each row has `C` bound columns and the statement contains `N` rows:

\[
P = N \times C
\]

If there are `F` additional fixed parameters outside the row tuples:

\[
P = N \times C + F
\]

For example, if each row has 4 columns and you want to insert 300 rows:

\[
P = 300 \times 4 = 1200
\]

If the statement also has 2 shared parameters, the total marker count is 1,202. Compare this total against the database/driver's actual parameter limit.

With `Statement.add()`, the SQL template still has `C` markers for one row, while the number of parameter sets is `N`. This can avoid marker limits scaling with `N`, but does not eliminate driver limits on set count, data size, memory, and execution duration.

This is a key distinction: multi-row `VALUES` primarily increases the number of placeholders in the SQL query; `Statement.add()` primarily increases the number of parameter sets on the same statement.

## 8. Choosing batch size

There is no single optimal batch size for all systems. Batches that are too small create many round-trips and statement overhead; batches that are too large increase memory, locks, processing time, and latency.

When choosing batch size, consider:

- Number of columns and data types per row.
- Average and maximum size of individual values, especially `VARCHAR`, JSON, and binary.
- The driver's `Statement.add()` capabilities.
- Maximum parameter sets supported by the driver/database.
- Target execution time for a single batch.
- Connection pool size and concurrent write requests.
- Transaction timeouts, lock contention, and rollback requirements.
- Retry strategy and handling of partially failed batches.

A value like 100 or 500 rows per batch is only a starting point for benchmarking, not a universal rule. Use measured metrics to tune.

## 9. Splitting large datasets into bounded batches

Do not feed hundreds of thousands or millions of parameter sets into a single `Statement`. Split the source into bounded batches.

Sequential processing example:

```java
Flux<Long> insertAll(
        ConnectionFactory connectionFactory,
        Flux<CustomerInput> source) {

    int batchSize = 200;

    return source
        .buffer(batchSize)
        .concatMap(batch -> insertBatch(connectionFactory, batch));
}
```

`buffer(batchSize)` collects up to 200 elements into a list. `concatMap` waits for the current batch to finish before executing the next one. This bounds the number of concurrent batches and generally makes connection usage easier to control.

If the workload and database allow multiple batches in parallel, set a bounded concurrency:

```java
Flux<Long> insertAll(
        ConnectionFactory connectionFactory,
        Flux<CustomerInput> source) {

    int batchSize = 200;
    int concurrency = 2;

    return source
        .buffer(batchSize)
        .flatMap(batch -> insertBatch(connectionFactory, batch), concurrency);
}
```

A concurrency of 2 allows at most two batches to be processed simultaneously in that operator. Balance this against the pool's `maxSize`, other application operations, and the database's connection budget.

### 9.1. Do not collect the entire source before batching

For large sources, avoid:

```java
source.collectList()
    .flatMapMany(all -> Flux.fromIterable(all).buffer(200));
```

This materializes the entire source before batching, negating memory bounding. Call `buffer(batchSize)` directly on the Flux to retain only one batch at a time, unless the source is already a list of controlled size.

### 9.2. The final batch can be smaller

If the total element count is not divisible by batch size, the final batch contains fewer rows. For example, 450 rows with batch size 200 yield three batches of sizes 200, 200, and 50. Do not pad with dummy rows or unused placeholders for the last batch.

### 9.3. Handling an empty source

`buffer` on an empty Flux emits no batches, so `insertAll` completes without calling `insertBatch`. If the method must return the total row count written, sum the per-batch counts:

```java
Mono<Long> insertAllAndCount(
        ConnectionFactory connectionFactory,
        Flux<CustomerInput> source) {

    return source
        .buffer(200)
        .concatMap(batch -> insertBatch(connectionFactory, batch))
        .reduce(0L, Long::sum);
}
```

## 10. Combining batching with transactions

`Statement.add()` does not create a transaction by itself. It describes multiple parameter sets for one statement; operation atomicity still depends on the database, driver, and transaction boundary.

If business rules require all batches to succeed or roll back together, place the batches inside an appropriate reactive transaction. Service-level example:

```java
@Transactional
public Mono<Long> importCustomers(Flux<CustomerInput> source) {
    return source
        .buffer(200)
        .concatMap(this::insertBatchUsingSpringManagedConnection)
        .reduce(0L, Long::sum);
}
```

`insertBatchUsingSpringManagedConnection` must use the Spring-managed connection inside that transaction, not open an independent connection outside the transaction context. All repositories/templates/clients must also share the same `ConnectionFactory` as `R2dbcTransactionManager`.

### 10.1. One transaction for the entire import

Pros:

- Can roll back everything if one batch fails.
- All operations sit within the same transaction boundary.
- Fits when atomicity across the whole dataset is a business requirement.

Cons:

- Long-running transaction that can hold a connection for a long time.
- More locks or older data snapshots may be retained longer.
- Transaction log/WAL/undo can grow significantly.
- For very large imports, rollback can take considerable time and resources.

### 10.2. One transaction per batch

Each batch gets its own transaction:

- Shortens transaction duration and limits rollback scope.
- Allows saving checkpoints after each batch.
- When a later batch fails, earlier batches may already be committed.
- Requires resume logic, idempotency, or status tracking to avoid duplicates on rerun.

Choose transaction boundaries based on business requirements, not performance alone. If an import must resume after failure, design batch status and idempotency keys from the start.

## 11. Mid-batch errors and partial results

When a batch has multiple parameter sets, one set may violate a constraint or encounter an error during execution. How the driver reports errors and how far prior sets progressed depend on the implementation and transaction.

The application needs to determine:

- Does one error stop the entire `execute()` call?
- Might sets before the error already have been written?
- How many `Result` items does the driver emit before signaling the error?
- Does the transaction roll back everything?
- Can you pinpoint exactly which row failed?
- Could retrying the entire batch create duplicate records?

Without a surrounding transaction, if the driver/database partially executes and then errors, the application may not know for certain which rows committed. Do not assume "batch threw an error means zero rows were written."

### 11.1. Idempotency when retrying

For imported data, you can use a unique business key or idempotency key to identify whether a row was already processed. Example:

```sql
CREATE TABLE imported_customer (
    external_id VARCHAR(100) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    email VARCHAR(250)
);
```

`external_id` is a unique key supplied by the data source. On retry, the database can reject duplicates or the application can use a dialect-appropriate upsert to reprocess safely. Upsert syntax differs across databases; use a supported mechanism and define clearly how existing records are updated.

Do not blindly retry a non-idempotent batch INSERT after losing a connection during commit. The commit outcome can be ambiguous: the server may have written the data while the client never received the acknowledgment.

## 12. Generated IDs and batch results

When inserting individual entities through a repository/template, the application may need the database-generated ID back. With `Statement.add()` at the SPI level, how the driver returns generated values depends on the API, database, and implementation. Do not assume `getRowsUpdated()` provides a list of IDs.

If generated IDs are needed per row:

- Check whether the driver supports generated values for statements with multiple parameter sets.
- Check how generated columns or `RETURNING` are retrieved for your database.
- Verify whether result order matches input order.
- If unsupported by the driver, consider multi-row `INSERT ... RETURNING`, per-row inserts, or application-generated keys.

For example, PostgreSQL supports `RETURNING` for multiple rows:

```sql
INSERT INTO customer(name, email)
VALUES ($1, $2), ($3, $4)
RETURNING id, name;
```

This is PostgreSQL syntax and is not portable. Check how binding and mapping generated rows work with your R2DBC driver.

## 13. DatabaseClient, repositories, and Statement.add()

Spring Data abstractions offer different levels of control:

| API | Purpose | Multi-row writes |
|---|---|---|
| `ReactiveCrudRepository.save(...)` | Save a single entity | One save operation for the entity |
| `ReactiveCrudRepository.saveAll(...)` | Save a publisher/collection of entities | Do not assume it always produces a `Statement.add()` batch; behavior depends on implementation/version |
| `R2dbcEntityTemplate` | Entity operations and mapping | Convenient for entity-based insert/update; verify version-specific execution behavior |
| `DatabaseClient` | Execute SQL and bind values | Standard fluent API describes one binding set per execution; callback/connection-level APIs or direct SPI can be used when multiple sets are needed |
| R2DBC SPI `Statement.add()` | Control multiple parameter sets on one Statement | Direct, but depends on driver support |

Do not infer that the method name `saveAll` equates to a database protocol batch. If batch performance is a requirement, verify SQL counts, binding behavior, and round-trips with logging/metrics or tests against the real driver.

### 13.1. When to use repositories/templates?

Use a repository or `R2dbcEntityTemplate` when:

- You need Spring Data entity mapping, lifecycle, and converters.
- Write volume is moderate.
- Existing save APIs meet SLAs.
- Direct control over how the driver sends multiple parameter sets is not required.

### 13.2. When to use Statement.add()?

Consider direct SPI when:

- You have high write volume sharing the same SQL structure.
- The driver confirms support for multiple parameter sets.
- You need control over batch size and connection lifecycle.
- The application is willing to manage mapping, generated values, and transaction integration manually.
- You have tested behavior on batch failure and cancellation.

If using the SPI directly in Spring, pay attention to connections managed by the transaction manager. Calling `ConnectionFactory.create()` directly can obtain a connection outside the transaction context unless the appropriate Spring mechanism is used.

## 14. Backpressure and bounding concurrent batches

Reactive does not mean an application can push millions of records into a driver simultaneously with zero memory cost. Operators and drivers can buffer data.

Points to control:

- A source `Flux` can emit faster than writes complete; use demand and appropriate batching operators.
- `buffer(batchSize)` caps elements per batch, but active batches still occupy memory.
- `concatMap` processes only one batch at a time.
- `flatMap(..., concurrency)` allows multiple concurrent batches; total retained data grows with concurrency.
- The driver may buffer all parameter sets of a `Statement.add()` before sending.
- The connection pool bounds connections, not the number of elements held on the heap.

Concurrency limiting example:

```java
source.buffer(200)
    .flatMap(this::writeBatch, 2);
```

If each batch has 200 items and concurrency is 2, the application may hold data for multiple batches at once. That is only a pipeline-level estimate; the driver may also maintain internal buffers. Measure heap and pool metrics under realistic load.

## 15. Timeouts and time limits

Large batches can take longer than single operations. Distinguish between:

| Timeout type | Meaning |
|---|---|
| Connection acquire timeout | Time spent waiting to borrow a connection from the pool |
| Connection creation timeout | Time allowed to open a new connection |
| Statement/query timeout | Time the database/driver permits a statement to run |
| Transaction timeout | Time a transaction is allowed to remain open |
| Application deadline | Overall time budget for the use case |

A request timeout does not automatically cancel database work in the same way across all drivers. On timeout or cancellation, verify that the statement is canceled, the connection returns to the pool, and the transaction rolls back or closes as expected.

Do not set timeouts so short that valid batches frequently get canceled; nor allow batches to hold connections indefinitely. Base settings on batch size, observed latency, and actual SLAs.

## 16. Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Forgetting to call `add()` between sets | Values overwrite the previous set or only one set runs | Call `add()` after binding a full set and before the next |
| Calling `add()` before binding all parameters | Current parameter set is missing bindings | Bind all placeholders completely before calling add |
| Using wrong bind index | Values land in wrong columns or fail at runtime | Remember R2DBC SPI indices are 0-based |
| Passing null to `bind` | Error because the driver does not know the null type | Use `bindNull(index, type)` |
| Assuming all drivers support `Statement.add()` | Unsupported errors or differing behavior | Check driver docs and run integration tests |
| Thinking `add()` equals multi-row VALUES | Misunderstanding parameter limits and execution | Distinguish multiple parameter sets from multiple SQL placeholders |
| Assuming a batch is a transaction | Partial writes possible on failure | Use a reactive transaction when atomicity is needed |
| Putting too many rows in one batch | Higher memory, latency, locks, and risk of hitting limits | Split into measured batch sizes |
| Using unbounded `flatMap` | Too many concurrent batches/connections | Set concurrency or use `concatMap` |
| Collecting the entire source via `collectList()` | Materializes large data on the heap | Use `buffer(batchSize)` directly |
| Retrying non-idempotent batch writes | Can create duplicate records | Use unique keys, upserts, or idempotency keys |
| Using raw connections outside transaction context | Operations may not join the Spring transaction | Use Spring-managed connection utilities/clients |
| Assuming `saveAll` is always a driver batch | Misjudging round-trips and performance | Measure SQL and verify implementation/version |
| Not checking generated IDs | Failing to retrieve IDs as expected | Verify driver generated values support |

## 17. Implementation workflow for multiple parameter sets

When building bulk write functionality, follow this sequence:

1. Define the SQL structure and parameter count per row.
2. Choose the API: repository/template for normal entity operations, `Statement.add()` when multiple parameter sets are needed and driver-supported.
3. Verify bind marker syntax and `add()` support on the exact driver version.
4. Determine batch size based on set count, value sizes, and driver/database limits.
5. Handle empty lists, null values, data types, and generated values.
6. Split large sources with `buffer(batchSize)`; use `concatMap` or bounded concurrency.
7. Choose transaction boundaries based on atomicity and resume needs.
8. Define error handling, partial results, and idempotency before enabling retries.
9. Test cancellation, timeouts, and connection cleanup.
10. Benchmark and observe written row counts, batch duration, errors, heap, connection pool, and database load.

## 18. Testing and observability

Tests must run against the same database and R2DBC driver used in deployment. Mocking `Statement` does not prove the driver actually supports `add()` or handles batch failures properly.

Cases to verify:

- Empty input.
- Single parameter set and multiple parameter sets.
- Configured maximum batch size and a smaller final batch.
- Null values bound via `bindNull`.
- Unique constraint violations in the first, middle, and last set of a batch.
- Connection failures during execution.
- Cancellation during writes.
- Transaction rolling back the whole batch or committing per batch as designed.
- Generated IDs if the use case expects keys back.
- Concurrent batches at configured concurrency.
- Large payload sizes and statement durations.

Useful metrics:

| Metric | Purpose |
|---|---|
| Rows per batch | Verify actual batch size |
| Batch execution duration | Track latency and detect oversized batches |
| Total rows written | Reconcile against source dataset |
| Errors by category | Distinguish constraint, timeout, and connection errors |
| Batch retries | Detect transient faults or retry storms |
| Connection acquire/pending | Detect pool saturation |
| Heap and GC | Detect excessive buffering |
| Database CPU, I/O, locks, and transaction logs | Assess server-side load |

Do not log full bound contents if they include emails, tokens, personal data, or sensitive payloads. Log correlation IDs, batch row counts, durations, operation types, and sanitized error details.

## 19. Key principles to remember

- `Statement.add()` adds a new parameter set for the same SQL query in the R2DBC SPI.
- Bind the current set completely before calling `add()`; `bind(int, ...)` indices start at 0.
- Use `bindNull(index, type)` for null values.
- Distinguish multiple parameter sets on one Statement from a multi-row `VALUES` SQL query with multiple bind markers.
- `Statement.add()` depends on driver support; check documentation and test against the real database.
- `Batch` is a different API that groups multiple SQL statements and does not replace prepared statements with bind parameters.
- Driver/database limits include parameter count, set count, SQL length, packet size, value size, memory, and duration.
- Include fixed parameters when estimating limits for multi-row INSERTs.
- Split large sources using `buffer(batchSize)`; use `concatMap` or bounded concurrency.
- Do not materialize the entire source before batching when data is large.
- `Statement.add()` does not create a transaction; pick transaction boundaries based on business requirements.
- Handle mid-batch failures, partial results, and retries via idempotency.
- Verify generated values and `saveAll` behavior rather than assuming every driver/framework batches identically.
- Measure batch latency, heap, connection pool, and database load to select an appropriate size.

Multiple parameter sets on a `Statement` are a useful low-level tool when repeatedly executing the same SQL query in R2DBC. They can reduce statement creation overhead and allow the driver to optimize transmission, though actual efficiency and limits depend on the implementation. By combining `Statement.add()` with bounded batch sizes, intentional transactions, controlled concurrency, and testing on the real driver, an application can write many records reliably while staying responsive to errors and resource pressure.
