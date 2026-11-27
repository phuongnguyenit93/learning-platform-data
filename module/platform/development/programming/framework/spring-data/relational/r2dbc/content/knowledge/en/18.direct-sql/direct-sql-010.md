# Using the R2DBC SPI Directly and Responsibilities for Managing Results and Resources

Spring Data Relational R2DBC provides repositories, mapping metadata, and abstractions that let applications work with databases reactively. In some cases, applications need finer-grained control: using driver-specific APIs, running dynamic SQL commands, reading multiple result segments, retrieving generated keys, or coordinating multiple operations on a single connection. In those cases, you can work directly with the R2DBC SPI.

The R2DBC SPI is the standard set of interfaces for reactive relational database access. Key components include `ConnectionFactory`, `Connection`, `Statement`, `Result`, `Row`, and `RowMetadata`. The SPI exposes publishers to open connections, execute statements, read results, and close resources.

Using the SPI directly means the application must understand and manage the lifecycle of those resources. Connections must be closed or returned to the pool on every termination path; results must be consumed properly; rows may only be read during the mapping callback; transactions must be committed or rolled back; and cancellation must also trigger cleanup.

This lesson covers the R2DBC SPI structure, opening and releasing connections, binding parameters, reading rows and metadata, handling update counts and generated values, managing transactions, batching, errors, and cancellation, as well as when to use the direct SPI instead of repositories.

## 1. Where Does the R2DBC SPI Sit in the Architecture?

A Spring Data R2DBC application typically has these layers:

~~~text
Service
   |
   v
Reactive Repository / DatabaseClient
   |
   v
Spring Data Relational
   |
   v
R2DBC SPI
   |
   v
R2DBC Driver
   |
   v
Database
~~~

Repositories and `DatabaseClient` use the R2DBC SPI underneath. With repositories, Spring Data generates SQL, binds parameters, and maps data from entity metadata. With `DatabaseClient`, the application has greater control over SQL and result mapping while still using Spring's abstraction.

When calling the R2DBC SPI directly, the application works closer to the driver:

- Manually requesting connections from `ConnectionFactory`.
- Creating `Statement` instances on the connection.
- Binding parameters per the driver's rules.
- Calling `execute()` and consuming `Result`s.
- Reading `Row`s or update counts.
- Closing connections on completion, error, or cancellation.
- Managing transactions manually if needed.

The R2DBC SPI is not an asynchronous JDBC wrapper. Operations return Reactive Streams Publishers, so never call `block()` or synchronous APIs to await results inside a reactive flow.

## 2. Core Components of the R2DBC SPI

| Component | Role |
|---|---|
| `ConnectionFactory` | Supplies connections to the database |
| `Connection` | Represents a database session |
| `Statement` | Represents a SQL statement prepared for execution |
| `Result` | Represents the outcome of a statement execution |
| `Row` | Represents a single data row being read |
| `RowMetadata` | Provides metadata for columns in the row |
| `ColumnMetadata` | Describes a column's name, type, and attributes |
| `ConnectionFactoryMetadata` | Provides info about the connection factory/driver |

Basic query flow:

~~~text
ConnectionFactory.create()
        |
        v
     Connection
        |
        v
createStatement(sql)
        |
        v
bind parameters
        |
        v
Statement.execute()
        |
        v
      Result
        |
        +---- map(Row, RowMetadata) ----> data
        |
        +---- getRowsUpdated() ---------> affected row count
        |
        v
Connection.close()
~~~

SPI methods typically return `Publisher` rather than `Mono` or `Flux`. In Reactor applications, use `Mono.from(...)` or `Flux.from(...)` to adapt publishers based on the expected cardinality.

For instance, `ConnectionFactory.create()` returns a publisher that emits a connection. A single `Statement.execute()` call may emit one or more `Result`s depending on the statement and driver.

## 3. Acquiring a Connection from ConnectionFactory

`ConnectionFactory` is the starting point to open a connection:

~~~java
Publisher<? extends Connection> publisher =
        connectionFactory.create();
~~~

In a Reactor application, adapt it to a `Mono`:

~~~java
Mono<Connection> connectionMono =
        Mono.from(connectionFactory.create());
~~~

Never call `block()` to acquire a connection inside a reactive service:

~~~java
// Avoid in reactive applications.
Connection connection = Mono.from(connectionFactory.create()).block();
~~~

This blocks the thread until a connection arrives and forfeits non-blocking benefits. Chain subsequent work with `flatMap`, `map`, `usingWhen`, or appropriate Reactor operators.

### 3.1. ConnectionFactory and Connection Pools

In Spring applications, `ConnectionFactory` is usually configured by starter auto-configuration or declared by the application. A connection pool may be used to reuse physical connections.

When taking a connection from a pool, `Connection.close()` usually returns the connection to the pool for reuse; it does not necessarily close the underlying socket. The application must still call close so the pool knows the connection has been returned.

Never store a connection in a singleton service field to share across requests. A connection is a stateful resource: transactions, auto-commit, isolation, and statements can leak into other operations if lifecycle boundaries are violated.

## 4. The Most Critical Obligation: Closing the Connection on Every Termination Path

When using the SPI directly, the application must guarantee the connection is released when:

- Work completes successfully.
- The query emits an error.
- Data mapping throws an error.
- The subscriber cancels the subscription.
- The request times out or the client disconnects.

Do not close the connection only on the success branch. If an error occurs before close is reached, connections leak and can exhaust the pool.

### 4.1. Using usingWhen to Manage Asynchronous Resources

Reactor provides `usingWhen` for resources whose cleanup returns a publisher. This matches `Connection.close()` because closing is also reactive.

Example reading multiple rows:

~~~java
Flux<Customer> findCustomers(String city) {
    return Flux.usingWhen(
            connectionFactory.create(),
            connection -> {
                Statement statement = connection.createStatement("""
                        SELECT id, customer_name
                        FROM customer
                        WHERE city = ?
                        """);

                statement.bind(0, city);

                return Flux.from(statement.execute())
                        .concatMap(result ->
                                Flux.from(result.map((row, metadata) ->
                                        new Customer(
                                                row.get("id", Long.class),
                                                row.get("customer_name", String.class)))));
            },
            connection -> Mono.from(connection.close()),
            (connection, error) ->
                    Mono.from(connection.close()),
            connection -> Mono.from(connection.close())
    );
}
~~~

The three cleanup callbacks handle, in order:

1. Normal completion of the publisher.
2. Termination with an error.
3. Publisher cancellation.

`usingWhen` awaits completion of the cleanup publisher per Reactor semantics. This matters because `Connection.close()` is asynchronous; merely invoking the method without subscribing to its publisher does not ensure closing finishes.

This example shows simple mapping; constructors and types must match the actual entity. Check vendor docs if your connection factory or driver has special behavior.

### 4.2. Why Not Use doFinally to Close Connections?

`doFinally` receives the termination signal, yet its callback does not return a publisher for Reactor to await. Calling:

~~~java
.doFinally(signal -> connection.close())
~~~

creates the close publisher without subscribing to it as part of the cleanup chain. Thus, there is no guarantee the resource returns to the pool at the right time.

Similarly, avoid calling `close().subscribe()` inside `doOnTerminate`, `doOnError`, or `finally`, which spawns a detached subscription. Use `usingWhen` or a composition pattern with explicit cleanup publishers.

### 4.3. Do Not Use try-with-resources for Reactive Connections

`Connection` should not be managed synchronously as a resource that closes upon exiting a lexical block:

~~~java
// Unsuitable for connections used asynchronously.
try (Connection connection = ...) {
    // execute reactive operation
}
~~~

The publisher may not have finished executing when the Java block exits. The connection would close before the query completes. `usingWhen` is designed to bind cleanup to asynchronous lifecycles.

## 5. Creating Statements and Binding Parameters

Create a statement from a connection:

~~~java
Statement statement = connection.createStatement(
        "SELECT id, customer_name FROM customer WHERE id = ?");
~~~

Then bind values. Bind indexes in the R2DBC SPI start at 0:

~~~java
statement.bind(0, 10L);
~~~

While `DatabaseClient` supports named parameters, the direct SPI relies on the binding capabilities provided by the driver. Placeholder syntax in SQL depends on the driver/dialect: some drivers use `?`, others `$1`, or other formats. Do not assume a single placeholder syntax runs across all drivers.

### 5.1. Binding Null Values with bindNull

Do not call `bind(index, null)` to bind SQL NULL. The R2DBC SPI provides `bindNull` to declare the Java type of the null value:

~~~java
statement.bindNull(0, String.class);
~~~

Example:

~~~java
Statement statement = connection.createStatement("""
        INSERT INTO customer (customer_name, phone_number)
        VALUES (?, ?)
        """);

statement.bind(0, "Nguyen An");
statement.bindNull(1, String.class);
~~~

The supplied Java type helps the driver determine how to bind the null value. Choose a type compatible with the column and driver mapping.

### 5.2. Do Not Concatenate User Data into SQL

Do not construct SQL by directly concatenating input strings:

~~~java
// Unsafe.
String sql = "SELECT * FROM customer WHERE name = '" + name + "'";
~~~

Use parameter binding instead:

~~~java
Statement statement = connection.createStatement(
        "SELECT id, customer_name FROM customer WHERE customer_name = ?");

statement.bind(0, name);
~~~

Parameter binding separates data from SQL structure and prevents value-based injection. However, table names, column names, or sort keywords cannot be bound as ordinary values. Dynamic identifiers must come from an application-controlled whitelist.

## 6. Executing Statements and Consuming Results

`Statement.execute()` returns a publisher of `Result`:

~~~java
Publisher<? extends Result> results = statement.execute();
~~~

Do not assume `execute()` directly emits an entity or a row. The application must consume each `Result` using the proper API:

- `Result.map(...)` to read rows.
- `Result.getRowsUpdated()` to read affected row counts.
- `Result.flatMap(...)` to process result segments when needed.

Example reading rows:

~~~java
Flux<Customer> customers =
        Flux.from(statement.execute())
                .concatMap(result ->
                        Flux.from(result.map((row, metadata) ->
                                new Customer(
                                        row.get("id", Long.class),
                                        row.get("customer_name", String.class)))));
~~~

`concatMap` processes each result in order. With `flatMap`, multiple child publishers could run concurrently; for statements with multiple results or meaningful ordering, `concatMap` is easier to control.

Never ignore results after execution. Consuming results is part of the driver protocol and may be required to free resources or allow the connection to run the next statement.

### 6.1. Each Result Must Be Consumed According to Its Kind

For SELECT, use `map` to read rows. For UPDATE/DELETE, use `getRowsUpdated` to obtain the affected row count. Do not invoke multiple consumption methods simultaneously on the same `Result` unless the driver/SPI permits it; pick the method matching the result kind and consume it once per contract.

If a statement returns multiple results, process every emitted result. For batches or stored procedures, there may be multiple result segments or different output types depending on the driver.

## 7. Reading Row and RowMetadata

`Row` holds the values of a single row. `RowMetadata` describes the columns in the row, such as column names, data types, and other driver-provided metadata.

Reading by label:

~~~java
String customerName =
        row.get("customer_name", String.class);
~~~

Reading by index:

~~~java
Long id = row.get(0, Long.class);
~~~

Labels are usually more readable when SQL defines aliases. Indexes can fit fixed queries where column positions are tightly controlled.

### 7.1. Row Is Meaningful Only Inside the Mapping Callback

Do not store `Row` in a field or return it outside the callback:

~~~java
// Avoid: Row is tied to the result/driver lifecycle.
AtomicReference<Row> savedRow = new AtomicReference<>();

result.map((row, metadata) -> {
    savedRow.set(row);
    return row;
});
~~~

`Row` is a driver-managed view over data. Once the callback completes or the result is consumed, the application must not access the old row. Convert needed values into Java objects immediately inside the callback:

~~~java
result.map((row, metadata) ->
        new Customer(
                row.get("id", Long.class),
                row.get("customer_name", String.class)));
~~~

The `Customer` object created from extracted values can be used afterward according to the application's lifecycle.

### 7.2. Using RowMetadata

You can inspect column metadata:

~~~java
result.map((row, metadata) -> {
    String firstColumnName =
            metadata.getColumnMetadata(0).getName();

    Long id = row.get("id", Long.class);

    return new CustomerIdView(id, firstColumnName);
});
~~~

`RowMetadata` is useful when writing generic mappers, logging result set structure, or handling dynamic SQL. For fixed queries, there is no need to read metadata on every row unnecessarily.

Column names, casing, and data types are supplied by the driver per dialect. With quoted or colliding aliases, choose distinct aliases and inspect actual metadata.

### 7.3. SQL NULL Values

A nullable column can return Java `null`:

~~~java
String phoneNumber = row.get("phone_number", String.class);
~~~

If the column is SQL NULL, `phoneNumber` can be null. Never use Java primitives when a column can be null; use wrapper types such as `Long`, `Integer`, or `Boolean`.

Distinguish:

- No rows: result emits no row.
- Row present with SQL NULL column: mapper is called and the column value can be null.
- Query failure: publisher emits `onError`.

## 8. Reading Multiple Rows and Preserving the Reactive Stream

For multi-row SELECTs, each `Result` can emit many rows. Transform those rows into a `Flux<T>`:

~~~java
Flux<Customer> findAllCustomers(Connection connection) {
    Statement statement = connection.createStatement("""
            SELECT id, customer_name
            FROM customer
            ORDER BY id
            """);

    return Flux.from(statement.execute())
            .concatMap(result ->
                    Flux.from(result.map((row, metadata) ->
                            new Customer(
                                    row.get("id", Long.class),
                                    row.get("customer_name", String.class)))));
}
~~~

This method receives an already-acquired connection; it does not own the connection and must not close it. Resource ownership must be clear: whichever component opens the connection must guarantee it closes after the publisher completes.

If a method returns `Flux` and opens the connection itself, use `Flux.usingWhen` to bind connection lifetime to the entire stream. If the caller passes the connection in, the caller owns cleanup.

Do not collect all rows into a list when the result set is large. `Flux` enables row-by-row processing and supports backpressure; `collectList()` should only be used when result counts are safely bounded.

## 9. Reading Update Counts with getRowsUpdated

For UPDATE or DELETE statements, applications often need the number of affected rows:

~~~java
Mono<Long> updateCustomerName(
        Connection connection,
        Long id,
        String name) {

    Statement statement = connection.createStatement("""
            UPDATE customer
            SET customer_name = ?
            WHERE id = ?
            """);

    statement.bind(0, name);
    statement.bind(1, id);

    return Mono.from(statement.execute())
            .flatMap(result ->
                    Mono.from(result.getRowsUpdated()));
}
~~~

`getRowsUpdated()` returns a publisher of the affected row count. `Long` fits the SPI because counts can exceed `int` range.

Distinguish:

- Emits `0`: statement succeeded, but no rows were affected.
- Emits positive number: rows were affected.
- `onError`: statement failed, such as a SQL or constraint error.
- Publisher completes without emitting a count: depends on statement/driver; do not assume a value is always emitted if the driver omits one.

Do not use `Result.map` to read update counts. Use the dedicated `getRowsUpdated()` API.

## 10. Retrieving Generated Values

Some drivers support requesting database-generated values, such as auto-increment primary keys. The SPI provides `Statement.returnGeneratedValues(...)` where supported by the driver.

Example:

~~~java
Mono<Long> insertCustomer(Connection connection, String name) {
    Statement statement = connection.createStatement("""
            INSERT INTO customer (customer_name)
            VALUES (?)
            """);

    statement.bind(0, name);
    statement.returnGeneratedValues("id");

    return Mono.from(statement.execute())
            .flatMap(result ->
                    Mono.from(result.map((row, metadata) ->
                            row.get("id", Long.class))));
}
~~~

Support for returning generated values and specifying column names depends on the database/driver. Some databases provide `RETURNING` syntax; drivers may use vendor-specific syntax internally. Check driver docs and integration tests.

If the driver does not support `returnGeneratedValues`, use a database-appropriate method to acquire the ID, such as a sequence or a supported query. Never deduce the ID by calling `MAX(id)` after insert because concurrent requests can create other records.

## 11. Binding Multiple Value Sets and Batch Statements

The R2DBC SPI supports adding multiple binding sets to a statement via `Statement.add()`:

~~~java
Statement statement = connection.createStatement("""
        INSERT INTO customer (customer_name, email_address)
        VALUES (?, ?)
        """);

statement.bind(0, "Nguyen An")
        .bind(1, "an@example.com")
        .add();

statement.bind(0, "Tran Binh")
        .bind(1, "binh@example.com");

Publisher<? extends Result> results = statement.execute();
~~~

Each `add()` adds the current binding set to the batch and allows setting up the next binding set per the SPI contract. Values must be bound completely for each set.

Batching can reduce overhead when writing many rows, yet behavior and performance depend on the driver and database. A batch does not automatically place all items in a single transaction; if all items must succeed or roll back together, use an explicit transaction.

If an item in a batch fails, results and the state of remaining items depend on the database, driver, and transaction. Never assume a batch is atomic unless enclosed in a transaction.

## 12. Managing Transactions Directly via Connection

The R2DBC SPI provides transaction operations such as:

- `beginTransaction()`
- `commitTransaction()`
- `rollbackTransaction()`
- `setTransactionIsolationLevel(...)`
- `setAutoCommit(...)`

For instance, with manual transactions, commit only after all required operations finish. On error, roll back.

In Spring, you should usually prefer `R2dbcTransactionManager` and `TransactionalOperator` so transaction context is managed consistently across reactive pipelines. Only drive transactions manually via the SPI when specialized needs require it and connection ownership is crystal clear.

### 12.1. Transaction and Cleanup Example

Conceptual example using `usingWhen` to open a connection, begin a transaction, commit on success, roll back on error or cancellation, and finally close the connection:

~~~java
Mono<Customer> createCustomerAtomically(String name) {
    return Mono.usingWhen(
            connectionFactory.create(),
            connection ->
                    Mono.from(connection.beginTransaction())
                            .then(insertCustomer(connection, name))
                            .flatMap(customer ->
                                    Mono.from(connection.commitTransaction())
                                            .thenReturn(customer)),
            connection ->
                    Mono.from(connection.close()),
            (connection, error) ->
                    Mono.from(connection.rollbackTransaction())
                            .onErrorResume(rollbackError -> Mono.empty())
                            .then(Mono.from(connection.close())),
            connection ->
                    Mono.from(connection.rollbackTransaction())
                            .onErrorResume(rollbackError -> Mono.empty())
                            .then(Mono.from(connection.close()))
    );
}
~~~

This is an illustrative pattern. Production code must also account for errors in `beginTransaction`, rollback errors, and close errors, logging cleanup failures without masking the root cause. Driver, transaction manager, and pool configuration also affect runtime behavior.

Never mix a Spring-managed transaction with manual transaction control on a separate connection. If repositories and direct SPI code do not share the same connection/transaction context, they can execute in two separate transactions.

### 12.2. Isolation Levels and Consistency

Isolation levels can be configured when business logic demands a specific consistency guarantee. Supported levels and semantics depend on the database. Do not raise isolation arbitrarily, as it can increase locking, contention, or versioning overhead.

A transaction should be short-lived and scoped to one use case. Never hold a connection or transaction open while a user interacts or pages through results.

## 13. Errors and Cancellation in Reactive Pipelines

Reactive streams have three primary signals:

- `onNext`: emits data.
- `onComplete`: normal completion.
- `onError`: termination with an error.

Additionally, a subscriber can send a cancellation. Cancellation is not a terminal signal emitted by the publisher; it is a request to stop the subscription.

When using the R2DBC SPI directly, cleanup must handle all three terminal outcomes plus cancellation. `usingWhen` provides separate cleanup callbacks for success, error, and cancel.

Avoid:

- Closing connections only in `doOnSuccess`.
- Rolling back only when catching synchronous exceptions.
- Calling `subscribe()` to run detached cleanup.
- Storing connections in fields and reusing them after cancellation.
- Discarding publishers returned by `close`, `commit`, or `rollback`.

If cleanup itself fails, define a logging policy and preserve the original error. Never silently swallow all cleanup errors in production just to make the pipeline look successful.

## 14. Connection Validation and Connection State

A connection carries state, such as an open transaction, auto-commit mode, isolation level, or savepoints. Do not assume a freshly acquired pooled connection is always in an arbitrary desired state if the pool or driver configures it differently.

The SPI offers driver-dependent validation APIs such as `Connection.validate(...)`. Validation can help in specific cases, though it should not replace a connection pool or standard connection management.

After using a transaction, ensure commit or rollback completes before returning the connection to the pool. If a connection fails or cannot be cleaned up, the pool/driver may evict it depending on implementation. The application must never continue using a connection after closing it.

## 15. When Should You Use the R2DBC SPI Directly?

| Need | Option to Consider |
|---|---|
| Standard entity CRUD | Spring Data repository |
| Custom SQL while keeping Spring abstractions | `DatabaseClient` |
| Complex dynamic SQL, manual mapping | `DatabaseClient` or SPI |
| Driver-specific features or SPI result segments | Direct R2DBC SPI |
| Specialized statement, binding, or generated-values control | Direct R2DBC SPI if higher abstractions fall short |
| Low-level manual connection/transaction control | Direct SPI, with full cleanup responsibility |
| Spring entity mapping, converters, and naming strategies | Repository or Spring Data mapping API |

Using the SPI directly increases application responsibility. Pick it when you need control that repositories or `DatabaseClient` do not conveniently expose. For routine CRUD, repositories keep code shorter, easier to test, and less prone to connection leaks.

## 16. Common Mistakes When Using the R2DBC SPI

| Mistake | Consequence | Fix |
|---|---|---|
| Failing to call `Connection.close()` | Connection leak, pool exhaustion | Use `usingWhen` with success/error/cancel cleanup |
| Calling `close()` without chaining publisher | Cleanup may not finish | Return the close publisher from cleanup callbacks |
| Using `doFinally` for async close | Reactor does not await the close publisher | Use `usingWhen` |
| Calling `block()` to get a connection | Blocks reactive thread | Chain publishers with `flatMap`/`usingWhen` |
| Calling `bind(index, null)` | Invalid null binding | Use `bindNull(index, type)` |
| Using the wrong bind index | Value bound to wrong placeholder | Remember indexes start at 0 |
| Assuming placeholders are identical across drivers | SQL fails on other dialects | Use the placeholder syntax of the target driver |
| Failing to consume `Result` | Result/connection may not be released cleanly | Use `map`, `getRowsUpdated`, or suitable result API |
| Reading `Row` after callback | Data may no longer be valid | Map to Java objects immediately inside callback |
| Confusing update count with row mapping | Fails to receive affected row count | Use `getRowsUpdated()` |
| Failing to roll back on error or cancel | Transaction may remain open | Attach rollback to error/cancel cleanup |
| Mixing SPI connections with another repository transaction | Operations do not share a transaction | Share transaction context or managed connection |
| Using `MAX(id)` to fetch inserted ID | May read ID from another request | Use generated values or an appropriate sequence |
| Using batching assuming automatic atomicity | Partial writes on error | Wrap in a transaction when atomicity is required |
| Sharing one connection across concurrent requests | State and statements can collide | Give each operation a clear connection lifecycle |

## 17. Safe SPI Query Execution Workflow

When writing a direct R2DBC SPI operation, follow this sequence:

1. Identify the driver/dialect and placeholder syntax.
2. Acquire a connection from `ConnectionFactory` inside the reactive pipeline.
3. Create a statement and bind all values, using `bindNull` for SQL NULL.
4. Execute the statement and consume every `Result`.
5. For SELECT, map `Row` to objects inside the callback.
6. For UPDATE/DELETE, read `getRowsUpdated()`.
7. If generated keys are needed, verify driver support for `returnGeneratedValues`.
8. If multiple operations require atomicity, open a transaction and commit/roll back on the right branches.
9. Attach connection cleanup for success, error, and cancellation using `usingWhen`.
10. Return the publisher to the caller; never subscribe or block inside services.
11. Run integration tests on the target database/driver covering SQL errors, cancellation, and cleanup.
12. Monitor pool metrics to catch long-held connections or leaks.

## 18. Testing Resource Lifecycles

Tests should verify not only SQL results, but also that connections are returned when:

- The query succeeds.
- The query returns no rows.
- SQL emits an error.
- Mapping throws an error.
- The subscriber cancels before completion.
- The transaction rolls back.

You can use `StepVerifier` to assert signals:

~~~java
StepVerifier.create(customerService.findCustomers("Hanoi"))
        .expectNextCount(2)
        .verifyComplete();
~~~

For cancellation:

~~~java
StepVerifier.create(customerService.streamCustomers(), 0)
        .thenRequest(1)
        .expectNextCount(1)
        .thenCancel()
        .verify();
~~~

To verify cleanup, use a connection factory/driver test double that records `close` calls, or inspect pool metrics in integration tests. For transactions, verify data rolled back after intentionally failing mid-operation.

Do not test only the happy path. Resource leaks often surface only after many requests or when errors and cancellations occur.

## 19. Key Takeaways

- The R2DBC SPI provides lower-level abstractions such as `ConnectionFactory`, `Connection`, `Statement`, `Result`, `Row`, and `RowMetadata`.
- All operations are reactive; never call `block()` inside a non-blocking chain.
- An application that opens a connection must guarantee closing it on success, error, and cancellation.
- Use `usingWhen` to await asynchronous cleanup; `doFinally` does not replace a cleanup publisher.
- Bind indexes start at 0; use `bindNull` to bind SQL NULL.
- Placeholders and certain features like generated values depend on the driver/database.
- Consume `Result` with the right API: `map` for rows and `getRowsUpdated` for update counts.
- Map `Row` to Java objects inside the callback; do not retain Row for later use.
- Direct transactions must commit on success and roll back on error or cancellation.
- Never assume batches are automatically atomic or that two different connections share a transaction.
- Prefer repositories or `DatabaseClient` for routine operations; use the direct SPI when lower-level control is needed.
- Test results, errors, cancellation, and connection release on the target database and driver.
