# Customizing Statement and Driver-Supported Options

The R2DBC SPI provides `Connection.createStatement(sql)` to create a `Statement` for executing a SQL statement. Before calling `execute()`, the application can bind parameters, add multiple value sets for a batch, and request optional behaviors such as returning database-generated values or hinting at a fetch size.

These options belong to the R2DBC driver layer. The SPI defines several common extension points, yet does not guarantee that every driver supports every option or behaves identically. When using features specific to PostgreSQL, MySQL, SQL Server, or another database, consult the documentation and version of the actual driver in use.

## 1. Statement Lifecycle

An operation at the SPI layer typically follows this sequence:

1. Acquire a `Connection` from a `ConnectionFactory` or an active managed transaction.
2. Call `connection.createStatement(sql)` to create a statement.
3. Bind values by name or by position.
4. Apply driver-supported options.
5. Call `execute()` to obtain a publisher of `Result`.
6. Subscribe and consume each `Result` appropriately: read rows with `map(...)` or obtain affected row counts with `getRowsUpdated()`.
7. Close the connection according to its lifecycle; if using a transaction or a Spring-managed connection, let the transaction manager handle the resource.

Example reading data with the R2DBC SPI:

```java
Mono<Customer> findCustomer(ConnectionFactory factory, Long id) {
    return Mono.usingWhen(
        factory.create(),
        connection -> {
            Statement statement = connection.createStatement(
                "SELECT id, email FROM customer WHERE id = $1");
            statement.bind(0, id);

            return Flux.from(statement.execute())
                .flatMap(result -> result.map((row, metadata) ->
                    new Customer(
                        row.get("id", Long.class),
                        row.get("email", String.class))))
                .singleOrEmpty();
        },
        Connection::close,
        (connection, error) -> connection.close(),
        Connection::close
    );
}
```

This example uses the `$1` marker for the PostgreSQL R2DBC driver. With other drivers, markers may differ. `bind(0, id)` uses a zero-based index in the SPI API. `usingWhen` ensures the connection is closed when the publisher completes, errors, or is cancelled.

In Spring Data R2DBC applications, you should normally use `DatabaseClient` or `R2dbcEntityTemplate` instead of acquiring connections manually for each operation. Those abstractions integrate better with Spring's mapping, exception translation, and transaction context. Working directly with `Statement` is suitable when a specific SPI capability or low-level SQL control is required.

## 2. Binding Parameters Before Execution

`Statement` supports positional or named binding depending on the markers accepted by the driver:

```java
Statement statement = connection.createStatement(
    "UPDATE customer SET email = $1 WHERE id = $2");

statement.bind(0, newEmail);
statement.bind(1, customerId);
```

For named binding, the driver must support named markers:

```java
Statement statement = connection.createStatement(
    "SELECT id FROM customer WHERE email = :email");

statement.bind("email", email);
```

Not every driver accepts named markers directly at the SPI layer. The `:email` syntax is commonly provided as an abstraction in Spring `DatabaseClient`, where the framework translates parameter names into native markers. When calling `Connection.createStatement` directly, follow the exact syntax of your driver.

Null values must be bound with `bindNull` and an explicit Java type:

```java
statement.bindNull(0, String.class);
```

Do not call `bind(index, null)` because the driver lacks sufficient information to determine the parameter type. Likewise, do not concatenate input data into SQL. Binding applies only to values, never to table names, column names, or SQL keywords.

## 3. Adding Multiple Parameter Sets with Statement.add()

`Statement.add()` lets you execute the same SQL statement with multiple parameter sets. After binding one set of values, call `add()` to add that set to the batch; then bind the next set. When `execute()` is called, the driver processes the added sets along with the final current set.

Example inserting multiple customers:

```java
Statement statement = connection.createStatement(
    "INSERT INTO customer (email, display_name) VALUES ($1, $2)");

statement.bind(0, "an@example.com")
    .bind(1, "An")
    .add()
    .bind(0, "binh@example.com")
    .bind(1, "Binh");

Flux.from(statement.execute())
    .flatMap(Result::getRowsUpdated)
    .reduce(0L, Long::sum);
```

In this example, `add()` commits the first parameter set and resets binding state for the next set. The last set is executed when `execute()` is called—there is no need to call `add()` again after the final set.

Batching with `Statement.add()` uses one SQL statement and multiple value sets. It differs from joining multiple distinct SQL statements with semicolons. If operations have different SQL or different logic, execute separate statements or use a batching mechanism supported by the database/driver.

### 3.1 When Is Batching Beneficial?

Batching is often beneficial when importing many identically structured rows, updating a set of records using the same statement, or reducing round trips between the application and database. However, large batches can consume memory, hold connections longer, and increase the amount of work inside a single transaction.

Split data into reasonably sized batches. Optimal batch size depends on row width, network, database, bind marker limits, and driver. Avoid blindly loading an entire file or input list into a single batch.

### 3.2 Batch Results

`execute()` returns `Publisher<? extends Result>`. Depending on the driver and execution mode, the application may receive multiple `Result`s. For update statements, affected row counts can be summed:

```java
Mono<Long> totalUpdated = Flux.from(statement.execute())
    .flatMap(Result::getRowsUpdated)
    .reduce(0L, Long::sum);
```

Do not assume every driver returns a single `Result` for the whole batch or always reports counts identically. Check driver semantics, especially if you need per-item row counts or mid-batch error handling.

## 4. Requesting Database-Generated Values

Some databases can generate values on insert, such as auto-increment primary keys, sequence values, or defaults. `Statement.returnGeneratedValues(...)` lets you ask the driver to return database-generated columns if supported by the driver.

Example:

```java
Statement statement = connection.createStatement(
    "INSERT INTO customer (email) VALUES ($1)");

statement.bind(0, email);
statement.returnGeneratedValues("id");

Mono<Long> generatedId = Flux.from(statement.execute())
    .flatMap(result -> result.map((row, metadata) ->
        row.get("id", Long.class)))
    .single();
```

`returnGeneratedValues("id")` is a request to the driver; it does not guarantee every driver or statement type supports it. If unsupported, the driver may throw `UnsupportedOperationException` or an execution error depending on implementation and version. Verify support before relying on it.

With PostgreSQL, an alternative is using the `RETURNING id` SQL clause:

```sql
INSERT INTO customer (email)
VALUES ($1)
RETURNING id;
```

`RETURNING` is PostgreSQL SQL syntax, not portable across all databases. Choose `returnGeneratedValues` or native SQL based on driver/database capabilities; avoid requesting the same value via both mechanisms without understanding how the driver handles them.

When using Spring `DatabaseClient`, you can apply a statement filter if your API version supports it to configure `returnGeneratedValues` before execution. Illustrative example:

```java
databaseClient.sql("INSERT INTO customer (email) VALUES (:email)")
    .bind("email", email)
    .filter((statement, next) ->
        next.execute(statement.returnGeneratedValues("id")))
    .map((row, metadata) -> row.get("id", Long.class))
    .one();
```

Check the `filter` signature and placement against your project's Spring Framework/Spring R2DBC version. If the driver does not support generated values, use a database-provided approach or generate IDs in the application before inserting.

## 5. Fetch Size Hints

`Statement.fetchSize(int)` lets the application provide a hint for how many rows should be fetched per batch when reading results. Depending on the driver, this hint can enable incremental fetching instead of loading the entire result at once.

Example:

```java
Statement statement = connection.createStatement("""
    SELECT id, email
    FROM customer
    ORDER BY id
    """);

statement.fetchSize(200);

Flux<Customer> customers = Flux.from(statement.execute())
    .flatMap(result -> result.map((row, metadata) ->
        new Customer(
            row.get("id", Long.class),
            row.get("email", String.class))));
```

`200` is a hint to the driver, not a cap on total returned rows and not equivalent to `LIMIT 200`. The query can still return the full result set; fetch size only influences how the driver retrieves or transfers data if implemented by the driver.

Some drivers ignore fetch size or only honor it in certain modes. Cursor-based or server-side fetching can also depend on transactions, autocommit, connection settings, and subscription behavior. Consult the driver documentation for exact requirements.

Do not set fetch size excessively large solely to reduce round trips. Too large a size increases memory usage; too small increases database chatter. Measure with realistic data and load before selecting a value.

## 6. Standard Statement Options and Support Levels

Several `Statement` methods are optional extension points in the SPI:

| Method | Purpose | What to Verify |
|---|---|---|
| `bind(index, value)` | Bind value by position | Native markers, Java types, and driver codecs. |
| `bind(name, value)` | Bind value by name | Whether the driver supports named bind markers at the SPI layer. |
| `bindNull(index/name, type)` | Bind typed SQL `NULL` | Java type must be compatible with codec/column. |
| `add()` | Add current parameter set to batch | How the driver executes batches and returns `Result`s. |
| `returnGeneratedValues(columns...)` | Request returned generated columns | Whether the driver/database supports generated values for that statement. |
| `fetchSize(rows)` | Hint rows per fetch | Whether the driver supports streaming/cursors and under what conditions. |
| `execute()` | Execute statement and return reactive results | How to consume each `Result` exactly once. |

The SPI can define a shared method without requiring every driver to implement every optional feature. For unsupported options, handle behavior per the API contract and driver version docs; never extrapolate one driver's behavior as portable.

## 7. ConnectionFactory Options vs. Statement Options

Not all database-related settings belong on `Statement`. `ConnectionFactoryOptions` configures creating connections/factories, such as driver, host, port, database, username, password, SSL, or driver-specific options. Pools have their own settings such as max size, acquire timeout, and connection lifetime.

Meanwhile, `Statement` governs a single execution: data binding, batching, fetch size, and generated values. For example:

| Scope | Configuration Examples |
|---|---|
| Driver/ConnectionFactory | URL, host, port, database, SSL, authentication, default schema depending on driver. |
| Connection pool | `maxSize`, `initialSize`, acquire timeout, idle/lifetime timeouts depending on pool. |
| Statement | bind markers, `add()`, `fetchSize`, `returnGeneratedValues`. |
| Reactive flow | Subscription, cancellation, backpressure, and how `Flux`/`Mono` is consumed. |
| Transaction | Transaction manager, isolation, read-only, and transaction boundaries. |

Some options such as statement timeout or query timeout have no uniform standard API on R2DBC `Statement`. They are typically configured via the driver/database, session, or vendor-specific mechanisms. When timeouts are needed, place them at the right layer: pool acquire wait time, database query execution time, and publisher timeout are not the same concept.

## 8. Driver-Specific Options

Drivers may expose proprietary configurations beyond the standard `Statement` methods. For instance, a driver might allow enabling cursor mode, adjusting how generated values are returned, selecting specialized data types, tuning fetch behavior, or configuring session settings. Option names and activation vary by vendor.

When using driver-specific options:

1. Identify the exact driver and version from your dependency tree or runtime.
2. Read the official documentation for that exact version rather than examples from another driver.
3. Check whether the option belongs to `ConnectionFactoryOptions`, pool configuration, connection API, or `Statement`.
4. Verify valid values, time units, defaults, and behavior when unsupported.
5. Write integration tests against the exact target database/driver.
6. Document non-portable configuration clearly so it can be replaced cleanly if switching databases.

Do not pass an arbitrary option name expecting every driver to understand it. When the SPI provides no standard extension point for an option, use the driver's documented API or configuration; avoid unsafe casts or relying on unstable internal implementations.

## 9. Consuming Result Properly

After `execute()`, each `Result` must be consumed in one of the appropriate ways. For row-returning queries, use `Result.map(...)`. For data-modifying statements, use `Result.getRowsUpdated()`.

Example reading rows:

```java
Flux<Customer> rows = Flux.from(statement.execute())
    .flatMap(result -> result.map((row, metadata) ->
        new Customer(
            row.get("id", Long.class),
            row.get("email", String.class))));
```

Example reading updated row count:

```java
Mono<Long> updated = Flux.from(statement.execute())
    .flatMap(Result::getRowsUpdated)
    .reduce(0L, Long::sum);
```

Do not consume the same `Result` through multiple paths such as calling both `map` and `getRowsUpdated()` unless the driver/API contract explicitly permits it. Results are normally designed for single consumption. If you need both returned data and row counts, use the result representation provided by the database/driver and design reading accordingly.

For multi-row queries, keep the publisher as a `Flux` where possible to avoid collecting everything into memory. Backpressure and driver fetching affect how data flows through the pipeline, yet do not replace SQL limits or pagination on very large result sets.

## 10. Combining Statement with Transactions

A statement uses a connection during execution. If the operation belongs to a transaction, it must use the connection participating in that transaction. When Spring manages reactive transactions, operations through a properly configured `DatabaseClient`/`R2dbcEntityTemplate` can share the same transaction context.

Acquiring a connection manually from `ConnectionFactory` while a Spring transaction is active risks creating a separate connection whose operations fall outside the intended transaction. When direct SPI access is required inside a transactional service, use Spring's transaction-bound connection retrieval or consider a custom integration. Never call `block()` to obtain a connection or result inside a reactive chain.

Batching also does not automatically imply a transaction. If a batch of multiple operations must succeed or fail together, run it inside an appropriate transaction and understand the driver's error behavior. Some databases may apply part of a batch before failing; a transaction is what rolls back partial work when atomicity is required.

## 11. Query Cancellation and Resource Management

R2DBC follows Reactive Streams. Subscribing starts publisher execution; cancelling can stop result reading. Drivers may support cancelling statements or sending cancel signals to the database, though timing and completeness depend on both driver and database.

Do not assume cancellation always rolls back changes or guarantees the server halts immediately. For write operations, transactions and commit state must be managed explicitly. When using the SPI directly, ensure connections close on completion, error, and cancellation; use `usingWhen` or equivalent resource management.

## 12. Choosing Between Direct SPI and Spring Abstractions

| Need | Approach |
|---|---|
| Standard entity CRUD and mapping | Repository or `R2dbcEntityTemplate`. |
| Custom SQL while keeping named parameters, exception translation, and Spring integration | `DatabaseClient`. |
| Requiring `fetchSize` or `returnGeneratedValues` via statement filter | `DatabaseClient` filter if version supports it, or direct SPI. |
| Batching with identical SQL and multiple bind sets | `Statement.add()` or an appropriate batch API. |
| Driver-specific features not exposed by Spring abstractions | Documented driver API or custom integration. |
| Low-level connection/transaction management | R2DBC SPI with explicit resource and transaction management. |

Do not drop down to the direct SPI just to tweak one option if Spring `DatabaseClient` already offers a suitable filter. Staying at a higher abstraction reduces connection-management responsibility and usually makes code easier to maintain. Use vendor-specific APIs only when genuinely needed and accept the vendor coupling.

## 13. Workflow for Applying and Verifying a Statement Option

When customizing a statement, follow this sequence:

1. Identify the goal: batching, generated values, fetch size, or a driver-specific option.
2. Check whether the SPI defines a standard method for it.
3. Check whether the target driver supports that method and what limitations exist.
4. Determine whether it can be configured via a `DatabaseClient` filter or requires direct SPI.
5. Bind all parameters, including explicit types for null values.
6. Consume `Result` exactly once and process returned rows or counts.
7. Manage connection and transaction through the reactive flow, including errors and cancellation.
8. Test against the real database/driver, large datasets, and unsupported-feature scenarios.

`Statement` is R2DBC's execution-level control point. The SPI provides binding, batching, fetch size hints, and generated-value requests, while optional features remain driver-dependent. Separating factory, pool, statement, transaction, and reactive-flow configuration helps place settings in the right layer and avoids accidental reliance on one driver's proprietary behavior when supporting multiple environments.
