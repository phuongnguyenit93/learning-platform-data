# Using inConnection and inConnectionMany When Connection Access Is Needed

## 1. When Is Direct Connection Access Needed?

In Spring Data Relational R2DBC, most data operations can be handled with repositories, R2dbcEntityTemplate, or DatabaseClient. These abstractions let you write queries, bind parameters, and map results without managing Connection directly.

However, there are situations where you need access to `io.r2dbc.spi.Connection`:

- Using the R2DBC SPI directly to create Statements, read Results, or execute a sequence of low-level operations.
- Reading connection or database metadata.
- Setting a session-level option provided by the driver or DBMS.
- Using a driver- or database-specific feature not exposed by higher-level abstractions.
- Executing multiple statements on the same connection within a controlled scope.

DatabaseClient provides two methods for this:

- **inConnection(...):** executes a callback with a Connection and returns a Mono for a single result.
- **inConnectionMany(...):** executes a callback with a Connection and returns a Flux for a stream of results.

Both methods let you use the R2DBC SPI while still letting Spring manage acquiring and releasing the connection. You gain direct connection access without reimplementing the full resource lifecycle.

## 2. Connection and Resource Lifecycle in R2DBC

### 2.1. Connection Is a Stateful Resource

`io.r2dbc.spi.Connection` represents a database session. From a connection, you can create statements, inspect metadata, manage transactions, or invoke driver-supported session operations.

A connection is not an ordinary Java object to hold long-term in a service. It may come from a connection pool, carries session state, and must be released once the publisher finishes.

Normally, applications should not call ConnectionFactory.create() manually for every business operation when already using DatabaseClient. Let DatabaseClient acquire connections through Spring-managed infrastructure.

### 2.2. DatabaseClient Manages Acquiring and Releasing Connections

For standard operations:

~~~java
Mono<Customer> customer =
    databaseClient.sql("""
        SELECT id, full_name
        FROM customers
        WHERE id = :id
        """)
        .bind("id", customerId)
        .map((row, metadata) -> new Customer(
            row.get("id", Long.class),
            row.get("full_name", String.class)
        ))
        .one();
~~~

DatabaseClient is responsible for acquiring the connection, executing the statement, reading results, and releasing the connection when the operation finishes or is cancelled. When using a connection pool, releasing typically returns the connection to the pool for reuse.

When SPI access is needed, inConnection and inConnectionMany pass the connection acquired by DatabaseClient into your callback. Once the publisher returned by the callback completes, errors, or is cancelled, Spring concludes the connection lifecycle according to the ConnectionFactory and active transaction context.

Therefore, inside the callback:

- Do not call connection.close() yourself as if you had acquired the connection directly from the factory.
- Do not store the Connection in a field, singleton, or shared variable across requests.
- Do not return the Connection outside the callback for later use.
- Do not call subscribe() or block() inside the callback.
- Return a publisher representing the entire work to be performed on the connection.

### 2.3. inConnection Does Not Automatically Start a Transaction

A very common misconception: using the same Connection does not mean statements automatically run inside a transaction.

inConnection and inConnectionMany scope connection usage for the callback. Without an active reactive transaction, statements still follow the connection and database's transaction/autocommit mode. Do not assume multiple SQL statements inside a callback automatically commit or roll back as an atomic unit.

If multiple operations must succeed or fail together, configure an R2DBC transaction manager and use @Transactional or TransactionalOperator. When a reactive transaction is active on the same ConnectionFactory, DatabaseClient can reuse the connection bound to that transaction context.

## 3. Distinguishing inConnection and inConnectionMany

Both methods serve similar purposes but differ in result type:

| Method | Return Type | When to Use |
|---|---|---|
| inConnection | Mono<T> | Callback produces a single result or only signals completion |
| inConnectionMany | Flux<T> | Callback emits zero, one, or many elements |

Conceptually:

~~~text
DatabaseClient
     |
     +-- inConnection(connection -> Mono<T>)
     |          |
     |          +-- single result or empty completion
     |
     +-- inConnectionMany(connection -> Publisher<T>)
                |
                +-- stream of 0..N elements
~~~

Both pass a Connection to the callback. The difference lies in the cardinality of the publisher returned by the callback and the reactive type emitted by the outer method.

Do not pick the method based on the number of SQL statements. An inConnection callback may run several statements and ultimately return a single Mono result. An inConnectionMany callback may read one multi-row query and emit rows via Flux.

## 4. Using inConnection for a Single Result

### 4.1. Basic Structure

Example finding a customer by ID via the R2DBC SPI:

~~~java
public Mono<CustomerView> findCustomer(Long customerId) {
    return databaseClient.inConnection(connection ->
        Flux.from(
            connection.createStatement("""
                SELECT id, full_name
                FROM customers
                WHERE id = $1
                """)
                .bind(0, customerId)
                .execute()
        )
        .concatMap(result ->
            Flux.from(result.map((row, metadata) ->
                new CustomerView(
                    row.get("id", Long.class),
                    row.get("full_name", String.class)
                )
            ))
        )
        .singleOrEmpty()
    );
}
~~~

This example uses PostgreSQL's `$1` bind marker syntax. Marker syntax in Connection.createStatement() depends on the driver; adjust for the database in use.

Execution flow:

1. inConnection obtains a DatabaseClient-managed Connection.
2. createStatement(...) creates a statement directly via the R2DBC SPI.
3. bind(0, customerId) binds the value to the first marker.
4. execute() returns a publisher of Result.
5. result.map(...) converts each Row into a CustomerView.
6. singleOrEmpty() turns the result stream into a Mono, fitting a primary-key lookup.
7. When the publisher completes, errors, or is cancelled, connection lifecycle is handled by DatabaseClient.

If no customer is found, singleOrEmpty() emits Mono.empty(). If the query returns more than one row, singleOrEmpty() emits a cardinality error. For primary-key lookups, this helps detect unexpected schemas or queries.

### 4.2. When the Callback Only Needs to Return a Count or Status

Not every callback returns an entity. For example, running an UPDATE and returning the affected row count:

~~~java
public Mono<Long> updateCustomerName(
        Long customerId,
        String newName) {

    return databaseClient.inConnection(connection ->
        Flux.from(
            connection.createStatement("""
                UPDATE customers
                SET full_name = $1
                WHERE id = $2
                """)
                .bind(0, newName)
                .bind(1, customerId)
                .execute()
        )
        .concatMap(result -> Flux.from(result.getRowsUpdated()))
        .singleOrEmpty()
        .defaultIfEmpty(0L)
    );
}
~~~

Result.getRowsUpdated() emits the updated row count as reported by the driver. singleOrEmpty() reduces the result into a Mono; defaultIfEmpty(0L) represents the absence of an update count as 0 in this example.

The type and number of values emitted by getRowsUpdated() can depend on the driver, especially for batches or multiple results. For a single UPDATE, the pattern above illustrates the typical case.

### 4.3. When Multiple Operations Must Run Yet Return One Value

An inConnection callback can chain multiple sequential operations and return the final result:

~~~java
public Mono<String> updateAndReadStatus(Long orderId) {
    return databaseClient.inConnection(connection -> {
        Mono<Long> updated = executeUpdate(connection, orderId);

        Mono<String> status = updated.then(
            readStatus(connection, orderId)
        );

        return status;
    });
}
~~~

executeUpdate and readStatus here are helper methods returning publishers and using the supplied connection. then(...) ensures the read step runs only after the update step finishes.

Sharing a connection callback does not mean a transaction is automatically started. If the update and read must be protected by an atomic transaction, wrap this publisher in a properly configured reactive transaction.

## 5. Using inConnectionMany for Multiple Results

### 5.1. Basic Structure

When a query can return multiple rows, use inConnectionMany:

~~~java
public Flux<CustomerView> findCustomersByStatus(String status) {
    return databaseClient.inConnectionMany(connection ->
        Flux.from(
            connection.createStatement("""
                SELECT id, full_name
                FROM customers
                WHERE status = $1
                ORDER BY id
                """)
                .bind(0, status)
                .execute()
        )
        .concatMap(result ->
            Flux.from(result.map((row, metadata) ->
                new CustomerView(
                    row.get("id", Long.class),
                    row.get("full_name", String.class)
                )
            ))
        )
    );
}
~~~

The callback returns Publisher<CustomerView>. DatabaseClient emits results through Flux<CustomerView>. Each Row is mapped into a CustomerView instance.

Avoid calling collectList() if the caller can process items individually. Flux enables streaming processing and supports backpressure. Collecting into a List keeps all elements in memory until the publisher completes.

### 5.2. One Connection Is Held While the Flux Is Active

With inConnectionMany, the callback returns a publisher that may emit many elements. The connection must remain available for as long as that publisher is being consumed.

This means:

- When the Flux completes, the connection is released by DatabaseClient's management mechanism.
- When the Flux emits an error, processing terminates and the connection is released.
- When the subscriber cancels, cleanup happens via the reactive mechanism.
- If the subscriber reads slowly or fails to consume the stream, the connection can be held longer.

Therefore, do not use inConnectionMany to produce an infinite Flux or wait on external non-database events while holding a connection. Connections are a finite pool resource; holding one too long can starve other requests.

### 5.3. When Emitting Multiple Results from Multiple Result Objects

Statement.execute() returns Publisher<Result>. A typical statement returns one Result, though the API allows representing multiple results in some scenarios. Multiple Results can be processed sequentially with concatMap:

~~~java
return databaseClient.inConnectionMany(connection ->
    Flux.from(connection.createStatement(sql).execute())
        .concatMap(result ->
            Flux.from(result.map((row, metadata) ->
                mapCustomer(row)
            ))
        )
);
~~~

concatMap preserves the processing order of each Result and child publisher. This is easy to reason about when results share the same connection.

## 6. Binding Parameters Directly via R2DBC Statement

When using databaseClient.sql(...), you can use named bindings:

~~~java
databaseClient.sql("""
    SELECT id
    FROM customers
    WHERE email = :email
    """)
    .bind("email", email);
~~~

However, when creating statements directly from Connection, you are working with the R2DBC SPI. Placeholder syntax and binding behavior are determined by the driver. The standard SPI API provides bind(int index, Object value) and bindNull(int index, Class<?> type).

### 6.1. Positional Binding

PostgreSQL example:

~~~java
connection.createStatement("""
    SELECT id, full_name
    FROM customers
    WHERE email = $1
      AND status = $2
    """)
    .bind(0, email)
    .bind(1, status);
~~~

Indexes in R2DBC SPI bind(index, value) start at 0. In this example:

- $1 receives the value from bind(0, email).
- $2 receives the value from bind(1, status).

Exact marker syntax varies across drivers. Consult the R2DBC driver documentation for your database and do not copy `$1` to a DBMS expecting different markers.

### 6.2. Binding NULL Values

Do not call bind(index, null) because the R2DBC SPI requires bindNull to specify the Java type of the null value.

~~~java
Statement statement = connection.createStatement("""
    INSERT INTO customers (id, full_name, email)
    VALUES ($1, $2, $3)
    """)
    .bind(0, customerId)
    .bind(1, fullName)
    .bindNull(2, String.class);
~~~

The type in bindNull tells the driver what data type to bind. That type must be compatible with the SQL column.

If the value is non-null, use bind(index, value). If null, use bindNull(index, type).

### 6.3. Multiple Bindings or Statement.add()

The R2DBC SPI includes a Statement API for adding parameter sets to execute multiple times with the same statement structure, subject to driver capabilities. However, support and effectiveness of batching/bind sets depend on the driver.

If batch inserts/updates are needed, consult your driver documentation and consider DatabaseClient or repository APIs first. Do not assume all drivers share the same batching behavior or optimizations.

### 6.4. Parameter Binding Does Not Replace Dynamic Identifiers

Bind markers are for values, not table names, column names, or SQL keywords.

You cannot write:

~~~sql
SELECT * FROM $1
~~~

expecting `$1` to be replaced by a table name. If dynamic table or column selection is needed, whitelist allowed identifiers and build the SQL structure from trusted code. Never interpolate raw client-sent strings into SQL.

## 7. Accessing Connection Metadata

Some operations require session or database info. R2DBC Connection exposes getMetadata() to inspect connection metadata.

Example:

~~~java
public Mono<String> getDatabaseProductName() {
    return databaseClient.inConnection(connection ->
        Mono.just(
            connection.getMetadata().getDatabaseProductName()
        )
    );
}
~~~

Metadata can provide the database product name and related info per the driver API. Most metadata calls read directly from the Connection object and do not necessarily execute a SQL query.

Do not use metadata as a substitute for application configuration or to guess full SQL capabilities. When specialized features are required, consult the corresponding driver and database documentation.

## 8. Using Connection for Session-Level Operations

Some databases provide commands to set session-level state, such as configuring the current schema, timezone, or a session variable. You may need to run a command on a specific connection and then execute queries relying on that state within the same callback.

Illustrative PostgreSQL example setting search_path:

~~~java
public Mono<CustomerView> findCustomerInSchema(
        String schema,
        Long customerId) {

    if (!ALLOWED_SCHEMAS.contains(schema)) {
        return Mono.error(
            new IllegalArgumentException("Schema is not allowed")
        );
    }

    return databaseClient.inConnection(connection ->
        Flux.from(connection.createStatement(
                "SET search_path TO " + schema
            ).execute())
            .concatMap(result -> Flux.from(result.getRowsUpdated()))
            .then(Mono.defer(() ->
                Flux.from(connection.createStatement("""
                        SELECT id, full_name
                        FROM customers
                        WHERE id = $1
                        """)
                    .bind(0, customerId)
                    .execute())
                    .concatMap(result -> Flux.from(result.map((row, metadata) ->
                        new CustomerView(
                            row.get("id", Long.class),
                            row.get("full_name", String.class)
                        )
                    )))
                    .singleOrEmpty()
            ))
    );
}
~~~

This example only illustrates keeping two operations in the same connection callback. Because a schema name is a SQL identifier, it cannot be bound as a value; hence it must be validated against a fixed whitelist before interpolating into SQL. SET syntax and schema management vary by database.

A major risk is that a connection pool can reuse the physical connection after the callback ends. If session state is not reset, that state can leak into subsequent requests. Prefer driver-supported connection-pool/initialization settings, or ensure state is restored before the callback completes. Do not rely on the pool automatically resetting arbitrary session settings.

If using @Transactional, verify how session settings and state resets interact with transactions. A SET command can carry DBMS-specific semantics across isolation/transaction modes.

## 9. Combining inConnection with Reactive Transactions

### 9.1. Spring-Managed Transactions

Spring R2DBC can manage reactive transactions using R2dbcTransactionManager and TransactionalOperator or @Transactional.

When a transaction is active, the connection is bound to Reactor Context. Data-access operations using the same ConnectionFactory and Spring's connection management can share that transaction's connection.

Example:

~~~java
@Transactional
public Mono<CustomerView> updateCustomer(Long id, String name) {
    return databaseClient.inConnection(connection ->
        Mono.from(connection.createStatement("""
                UPDATE customers
                SET full_name = $1
                WHERE id = $2
                """)
            .bind(0, name)
            .bind(1, id)
            .execute())
            .flatMap(updateResult ->
                Mono.from(updateResult.getRowsUpdated())
            )
            .then(
                Mono.from(connection.createStatement("""
                        SELECT id, full_name
                        FROM customers
                        WHERE id = $1
                        """)
                    .bind(0, id)
                    .execute())
                    .flatMap(result ->
                        Mono.from(result.map((row, metadata) ->
                            new CustomerView(
                                row.get("id", Long.class),
                                row.get("full_name", String.class)
                            )
                        ))
                    )
            )
    );
}
~~~

This example shows two statements using the same Connection passed to the callback. With a properly configured reactive transaction, the update and read belong to the same transaction.

For this to work as expected:

1. The transaction manager must be an R2DBC reactive transaction manager.
2. The transaction manager and DatabaseClient must use the same ConnectionFactory.
3. The method must return the reactive publisher so transaction context propagates throughout.
4. Do not call subscribe or block inside the callback.
5. Do not manually close the connection, commit, or roll back a Spring-managed transaction.

### 9.2. Do Not Manually Begin/Commit When Spring Manages the Transaction

When using @Transactional or TransactionalOperator, never call beginTransaction(), commitTransaction(), or rollbackTransaction() on a connection inside Spring's transaction context.

Spring's transaction manager is responsible for starting, committing, and rolling back. If code manually manipulates transactions at the Connection level, transaction state can conflict with the manager and break business atomicity.

If no transaction manager is used and you must manage transactions manually at the SPI level, you take full responsibility for begin, commit, rollback, errors, and cancellation. In typical Spring applications, prefer Spring's transaction abstraction to avoid manual management.

### 9.3. inConnectionMany Inside a Transaction

inConnectionMany can return a Flux participating in a reactive transaction. The transaction normally finishes only when the publisher completes. If a subscriber consumes slowly, the transaction and connection can remain open longer.

Do not stream millions of rows inside a long-running transaction without an explicit requirement. Consider pagination, batching, or separating long reads from write transactions.

## 10. Serializing Operations on the Same Connection

A connection is a stateful resource. Do not assume the driver supports concurrent execution of multiple independent statements on the same connection.

Problematic example:

~~~java
return databaseClient.inConnection(connection ->
    Mono.when(
        updateCustomer(connection, customerId),
        insertAudit(connection, customerId)
    ).then()
);
~~~

Mono.when subscribes to child publishers simultaneously. If both share one connection, commands can contend on the same session. Exact behavior depends on driver and protocol; never assume concurrent execution on a single connection is supported.

When order matters or the driver requires sequential usage, chain publishers with then():

~~~java
return databaseClient.inConnection(connection ->
    updateCustomer(connection, customerId)
        .then(insertAudit(connection, customerId))
);
~~~

For a collection of items, use concatMap when sequential execution is needed:

~~~java
return databaseClient.inConnection(connection ->
    Flux.fromIterable(customerIds)
        .concatMap(id -> updateCustomer(connection, id))
        .then()
);
~~~

concatMap preserves execution order. flatMap can introduce concurrency. Only run concurrently after confirming the driver and connection management support it. When truly independent operations need concurrency, usually let each pipeline acquire its own connection through managed abstractions rather than multiplexing commands onto one connection.

## 11. Backpressure, Cancellation, and Connection Hold Time

Because inConnectionMany returns a Flux, consumption can be throttled by backpressure. The connection must remain live while the publisher is still working.

Situations to watch out for:

- Slow clients cause results to drain slowly and hold connections longer.
- Non-completing publishers prevent connections from being released under normal lifecycles.
- Subscriber cancellation requires cleanup to run through the reactive mechanism.
- Blocking calls inside a callback can hold both the connection and reactive thread longer than expected.
- Waiting on HTTP services, message brokers, or user input inside a callback increases connection hold duration.

Keep callbacks focused on database work. Perform external data processing after exiting the connection-holding scope, unless business logic explicitly requires a transaction spanning those steps.

Do not use publishOn or subscribeOn as a workaround for connection management bugs. Schedulers do not make a connection thread-safe and do not replace transaction context.

## 12. When to Use Regular DatabaseClient Instead of inConnection?

inConnection and inConnectionMany are lower-level APIs. When you only need SQL, parameter binding, and result mapping, DatabaseClient.sql(...) is usually clearer.

| Need | Recommended Approach |
|---|---|
| Simple SELECT and entity/DTO mapping | DatabaseClient.sql(...).map(...).one()/all() |
| Standard INSERT/UPDATE/DELETE | DatabaseClient.sql(...).fetch().rowsUpdated() |
| Entity-oriented CRUD | Repository or R2dbcEntityTemplate |
| Direct R2DBC Connection/Statement usage | inConnection or inConnectionMany |
| Reading Connection metadata | inConnection |
| Multiple commands needing the same connection in one callback | inConnection/inConnectionMany, combined with a transaction if atomicity is required |
| Transactions across multiple repositories or abstractions | @Transactional or TransactionalOperator |

Do not use inConnection merely to replace .bind() or .map() on DatabaseClient. Direct SPI access increases coupling to drivers, bind markers, Row types, and Result details. Use it only when that extra control adds real value.

## 13. Error Handling and Resource Release

When the callback returns a publisher, DatabaseClient tracks that publisher's lifecycle. If the publisher completes, errors, or is cancelled, Spring releases the connection using the active connection-management mechanism.

Example handling errors outside the connection scope:

~~~java
public Mono<CustomerView> loadCustomer(Long id) {
    return databaseClient.inConnection(connection ->
        executeCustomerQuery(connection, id)
    )
    .onErrorMap(error ->
        new CustomerReadException("Unable to read customer", error)
    );
}
~~~

This translates errors into domain exceptions at the right layer. Do not swallow errors inside the callback and emit a fake success result, as that hides database failures.

If fallback handling is needed:

~~~java
return databaseClient.inConnection(connection ->
        executeCustomerQuery(connection, id)
    )
    .onErrorResume(DatabaseException.class, error ->
        Mono.error(new CustomerReadException("Query error", error))
    );
~~~

Exact exception names depend on the driver and Spring's error wrapping. Distinguish SQL errors, connection failures, conversion errors, and business errors in your handling design.

Do not manually close the connection in doFinally, doOnTerminate, or cleanup callbacks when DatabaseClient manages it. Closing manually can break a connection still tracked by the transaction manager or pool.

## 14. Comparison with Using ConnectionFactory Directly

You can acquire a connection directly from ConnectionFactory:

~~~java
Mono.usingWhen(
    Mono.from(connectionFactory.create()),
    connection -> executeQuery(connection),
    connection -> Mono.from(connection.close()),
    (connection, error) -> Mono.from(connection.close()),
    connection -> Mono.from(connection.close())
);
~~~

usingWhen manages asynchronous cleanup on completion, error, and cancellation. This example assumes executeQuery returns a Mono and does not participate in a Spring-managed transaction connection. Acquiring connections manually still requires coordinating properly with transaction context and releasing resources along every path.

In Spring applications, when you want the connection currently managed by a Spring transaction, use ConnectionFactoryUtils or corresponding Spring abstractions instead of calling ConnectionFactory.create() directly.

When you simply need connection access within a callback scope, DatabaseClient.inConnection or inConnectionMany is usually simpler. They keep code in the reactive model and let DatabaseClient manage connection lifecycle.

## 15. Common Mistakes

| Mistake or Misconception | Consequence | Fix |
|---|---|---|
| Thinking inConnection starts a transaction | Multiple statements may still run under autocommit | Use a transaction manager when atomicity is needed |
| Calling connection.close() inside callback | May close a connection still managed by Spring/pool/transaction | Let DatabaseClient release it |
| Storing Connection in a service field | Concurrent misuse, post-release access, or pool exhaustion | Only use inside the callback and its publisher |
| Using inConnection for multi-row results | Mono cannot represent a multi-element stream | Use inConnectionMany |
| Using inConnectionMany for a single result | Not wrong, but weakens API clarity | Use inConnection when the result is a Mono |
| Calling subscribe() inside callback | Creates an unlinked subscription outside callback/transaction lifecycle | Return the publisher from the callback |
| Calling block() to retrieve results | Blocks reactive threads and risks deadlocks | Compose Mono/Flux |
| Using SQL markers from another driver | Statement cannot bind parameters | Verify marker syntax for your driver |
| Calling bind(index, null) | R2DBC SPI does not accept null via bind | Use bindNull(index, type) |
| Assuming bind markers replace table names | Database treats marker as a value, not an identifier | Whitelist and build trusted identifiers |
| Running statements concurrently on one connection | Driver may not support it or ordering becomes unpredictable | Use then()/concatMap when sequential order is needed |
| Holding an infinite Flux in inConnectionMany | Connection held indefinitely; pool can be exhausted | Bound publishers and resource hold times |
| Changing session state without resetting | Later requests may receive a connection with stale state | Restore state or configure pool properly |
| Manually committing/rolling back in @Transactional | Conflicts with transaction manager | Let Spring manage the transaction |

## 16. Workflow for Using inConnection or inConnectionMany

When direct Connection access is needed, follow this sequence:

1. Verify why repositories, R2dbcEntityTemplate, or standard DatabaseClient SQL cannot satisfy the requirement.
2. Choose inConnection if the callback returns a single Mono result; choose inConnectionMany if it returns a multi-element Publisher.
3. Write a callback receiving Connection and returning a publisher covering the full work.
4. Create a Statement using SQL syntax and bind markers matching the driver.
5. Use bind(index, value) for non-null values and bindNull(index, type) for nulls.
6. Map Result/Row into DTOs or target types.
7. Chain multiple operations with then() or concatMap when ordering is required.
8. Never manually subscribe, block, close, commit, or roll back a DatabaseClient-managed connection.
9. If atomicity is needed, wrap the pipeline in a reactive transaction using the same ConnectionFactory.
10. Bound connection hold duration and avoid non-database work inside the callback.
11. Test completion, error, and cancellation against a real driver and database.
12. Monitor pool metrics for long-running queries or large Flux streams.

## 17. Self-Check Exercises

### Exercise 1: Choosing the API

A query finds a customer by ID and returns at most one row. Should you use inConnection or inConnectionMany?

Hint: inConnection, because the result fits Mono. If the query can emit multiple rows, use inConnectionMany.

### Exercise 2: Reading a List

You need to read all orders for a customer using an R2DBC Statement and emit OrderView items. Describe the callback structure.

Hint: Use inConnectionMany, create a Statement, bind the ID, call execute(), transform each Result into a publisher of Rows via map(), and emit OrderView items in the Flux.

### Exercise 3: Binding NULL

You need to insert a NULL email via Statement. Which API should you use?

Hint: Use bindNull(index, String.class) with the proper positional index and column-compatible type.

### Exercise 4: Transactions

A callback updates an order and then writes an audit log. If writing the audit fails, both operations must roll back. Is using inConnection alone enough?

Hint: No. inConnection shares the same connection inside the callback but does not open a transaction. Use a reactive transaction manager and wrap the publisher with @Transactional or TransactionalOperator.

### Exercise 5: Session State

A callback sets the session schema and then queries a table. Why should you be careful after the callback finishes?

Hint: The physical connection may be returned to the pool and reused. Session state can affect subsequent requests if not reset.

### Exercise 6: Multiple Operations

You have three statements that must run sequentially on the same Connection. Should you use Mono.when or then?

Hint: Use then() to chain sequentially. Mono.when subscribes to publishers concurrently and can create contention on the same connection.

### Exercise 7: Cancelling a Subscription

A client stops reading a Flux returned from inConnectionMany. What needs to happen?

Hint: The subscription is cancelled; the publisher must terminate and DatabaseClient's management mechanism releases the connection. Do not retain the connection or launch detached subscriptions.

## 18. Key Takeaways

- inConnection provides a Connection to a callback and returns a Mono.
- inConnectionMany provides a Connection to a callback and returns a Flux.
- Both methods manage connection lifecycle within the publisher's scope; do not manually close the connection.
- Sharing a Connection does not automatically create a transaction. Use a reactive transaction manager when atomic commit/rollback is required.
- When using the R2DBC SPI directly, bind marker syntax depends on the driver; bind indexes start at 0.
- Use bindNull(index, type) for null values.
- Use Result.map() to convert Rows into DTOs or result types.
- Never store Connection in a field, nor call subscribe or block inside the callback.
- Chain operations sequentially with then() or concatMap to avoid concurrent execution on a single connection.
- inConnectionMany can hold a connection for as long as the Flux is consumed; pay attention to backpressure, cancellation, and hold times.
- If changing session-level state, have a plan to restore it before the connection is reused.
- Drop to low-level APIs only when Connection capabilities are truly needed; for typical SQL, prefer DatabaseClient, repositories, or R2dbcEntityTemplate.

When direct Connection access is needed in Spring Data Relational R2DBC, let DatabaseClient scope the connection via inConnection or inConnectionMany and return a publisher encompassing all operations. This lets you use the R2DBC SPI while cooperating cleanly with Spring's connection lifecycle, connection pool, and reactive transactions.
