# R2DBC SPI Batch vs. Parameterized Statement

The R2DBC SPI provides two mechanisms commonly referenced when writing multiple statements or multiple records: `Batch` and a `Statement` with multiple bound value sets. Both can reduce database call overhead compared to creating and executing a separate operation for every row, but they solve two different problems.

`Batch` is created via `Connection.createBatch()` and accepts SQL strings through `Batch.add(String)`. It fits multiple static SQL statements and has no parameter binding API. `Statement` is created via `Connection.createStatement(sql)`; the application binds values to placeholders and calls `Statement.add()` to append the current binding set to the batch for that same SQL query. The latter fits when repeating a parameterized statement across multiple data sets.

Distinguishing the two APIs properly helps you choose a safe, controllable, and driver-appropriate write path. Keep in mind that SPI-level batching does not automatically guarantee a transaction, atomicity, a single network round-trip, or better performance in every scenario. Those properties also depend on the driver, database, batch size, and how the application manages connections.

## 1. What is Batch in the R2DBC SPI?

`io.r2dbc.spi.Batch` represents a group of SQL statements added as strings. The application obtains a batch from a `Connection`, appends statements with `add(String)`, and calls `execute()`.

```java
Batch batch = connection.createBatch();

batch.add("DELETE FROM expired_token WHERE expires_at < CURRENT_TIMESTAMP");
batch.add("UPDATE maintenance_job SET last_run = CURRENT_TIMESTAMP " +
          "WHERE job_name = 'token-cleanup'");

Publisher<? extends Result> results = batch.execute();
```

Key characteristics:

- Each `Batch.add(sql)` appends a SQL string to the batch.
- `Batch` has no `bind(...)` or `bindNull(...)` methods.
- Varying values would have to appear inline in the SQL if using `Batch`; therefore, never concatenate user input into SQL strings.
- `Batch.execute()` returns a publisher of `Result` items; the application must subscribe to and consume the results.
- How the driver sends and executes the statements is a driver implementation detail.

`Batch` fits static statements such as maintenance commands, metadata updates, or independent SQL operations requiring no bind values. It is not a suitable choice for inserting hundreds of records with varying data by string-concatenating SQL per row.

## 2. What is a parameterized `Statement`?

`io.r2dbc.spi.Statement` represents a single SQL statement. The application creates a statement via `Connection.createStatement(sql)`, binds values to placeholders, and calls `execute()`.

```java
Statement statement = connection.createStatement(
        "INSERT INTO customer (id, name) VALUES ($1, $2)");

statement.bind(0, 101L)
        .bind(1, "An Nguyen");

Publisher<? extends Result> result = statement.execute();
```

In this PostgreSQL example, the SQL uses `$1`, `$2` placeholders. The index passed to `bind` is the R2DBC API parameter index, starting at `0`; hence `$1` maps to `bind(0, ...)`, and `$2` maps to `bind(1, ...)`.

For other drivers, placeholder syntax may differ. For instance, some drivers use `?`. Use the parameter syntax supported by your database engine's R2DBC driver rather than copying PostgreSQL syntax verbatim to MySQL or another engine.

Benefits of bind parameters:

- Separates the SQL query from input data.
- Avoids string concatenation of values and mitigates SQL injection risk.
- Gives the driver the Java type of each parameter for conversion using the appropriate codec.
- Allows reusing the same SQL structure across multiple value sets.

## 3. Key difference between `Batch.add` and `Statement.add`

Both methods share the name `add`, but their meanings differ:

| API | Invocation | What gets added | Supports parameter binding? |
| --- | --- | --- | --- |
| `Batch.add(String sql)` | `batch.add("UPDATE ...")` | A new SQL string | No |
| `Statement.add()` | `statement.bind(...).add()` | The current bound value set for the same SQL query | Yes, via `bind`/`bindNull` |

Mental model:

```text
Batch
  add(SQL statement 1)
  add(SQL statement 2)
  add(SQL statement 3)
  execute()

Statement
  create one SQL with placeholders
  bind value set A
  add()       -> enqueue set A into the batch
  bind value set B
  add()       -> enqueue set B into the batch
  bind value set C
  execute()   -> execute previously added sets and the final set
```

`Batch` collects multiple potentially different SQL strings. `Statement.add()` collects multiple binding sets for the same SQL query. Do not mistake `Statement.add()` for a way to add a new SQL statement to a statement.

## 4. Using `Batch` for multiple static SQL statements

Suppose you need to run two maintenance operations with fixed SQL:

```java
Batch batch = connection.createBatch()
        .add("DELETE FROM expired_token " +
             "WHERE expires_at < CURRENT_TIMESTAMP")
        .add("UPDATE maintenance_job " +
             "SET last_run = CURRENT_TIMESTAMP " +
             "WHERE job_name = 'token-cleanup'");

Flux.from(batch.execute())
        .concatMap(result -> Flux.from(result.getRowsUpdated()))
        .then();
```

`Batch.execute()` emits `Result` items. For DML statements, `Result.getRowsUpdated()` provides a publisher of affected row counts if the driver supports it for that operation. `concatMap` consumes results in emission order; `.then()` cares only about completion and returns `Mono<Void>`.

In real code, return this publisher from the method so the caller manages the subscription. The snippet above does not run simply because a `Publisher` or `Flux` variable is created.

### Managing connection lifecycle

An R2DBC connection must be closed upon completion. `Mono.usingWhen` can manage the reactive resource:

```java
public Mono<Void> runCleanup(ConnectionFactory connectionFactory) {
    return Mono.usingWhen(
            Mono.from(connectionFactory.create()),
            connection -> {
                Batch batch = connection.createBatch()
                        .add("DELETE FROM expired_token " +
                             "WHERE expires_at < CURRENT_TIMESTAMP")
                        .add("UPDATE maintenance_job " +
                             "SET last_run = CURRENT_TIMESTAMP " +
                             "WHERE job_name = 'token-cleanup'");

                return Flux.from(batch.execute())
                        .concatMap(result -> Flux.from(result.getRowsUpdated()))
                        .then();
            },
            connection -> Mono.from(connection.close()),
            (connection, error) -> Mono.from(connection.close()),
            connection -> Mono.from(connection.close())
    );
}
```

`usingWhen` closes the connection when the publisher completes, errors, or is canceled. This example only illustrates resource management; it does not open a transaction. If the batch requires atomicity, it must run within an appropriate transaction.

## 5. Why `Batch` is unsuitable for inserting dynamic data

`Batch` provides no parameter binding API. The following snippet may look simple, but it is unsafe:

```java
String sql = "INSERT INTO customer(name) VALUES ('" + userInput + "')";
batch.add(sql);
```

If `userInput` contains quotes or malicious SQL, the statement can be altered. Manual string escaping is error-prone and depends on the database and encoding.

Never use `Batch.add` to interpolate user values into SQL. When writing multiple rows with varying data, use `Statement` with bindings and `Statement.add()` or an appropriate higher-level API.

`Batch` can still be used for statements with fixed application-controlled literals, but should not become a substitute for prepared statements.

## 6. Using `Statement.add()` to write multiple rows of the same shape

Suppose you need to insert multiple customers. All rows share the same `INSERT` structure and differ only in values:

```sql
INSERT INTO customer (id, name, email)
VALUES ($1, $2, $3)
```

Create one `Statement`, bind each value set, and call `add()` between sets:

```java
Statement statement = connection.createStatement(
        "INSERT INTO customer (id, name, email) VALUES ($1, $2, $3)");

statement.bind(0, 101L)
        .bind(1, "An Nguyen")
        .bind(2, "an@example.com")
        .add();

statement.bind(0, 102L)
        .bind(1, "Binh Tran")
        .bind(2, "binh@example.com");

Publisher<? extends Result> results = statement.execute();
```

In this example:

1. The first binding set is assigned to the placeholders.
2. `add()` puts the first value set into the statement's batch.
3. Subsequent bind calls build the second value set for the same SQL query.
4. `execute()` runs the statement with all previously added sets and the current final set.

You do not need to create a new `Statement` per row when using multiple binding sets. Nor should you call `add()` after the final set when no next set follows; after the last binding, call `execute()`.

## 7. Complete example with `Statement.add()` and R2DBC SPI

Define the input data:

```java
public record CustomerRow(
        Long id,
        String name,
        String email
) {
}
```

Method to insert multiple rows:

```java
public Mono<Void> insertCustomers(
        ConnectionFactory connectionFactory,
        List<CustomerRow> customers) {

    if (customers.isEmpty()) {
        return Mono.empty();
    }

    return Mono.usingWhen(
            Mono.from(connectionFactory.create()),
            connection -> {
                Statement statement = connection.createStatement(
                        "INSERT INTO customer (id, name, email) " +
                        "VALUES ($1, $2, $3)");

                for (int i = 0; i < customers.size(); i++) {
                    CustomerRow customer = customers.get(i);

                    statement.bind(0, customer.id())
                            .bind(1, customer.name())
                            .bind(2, customer.email());

                    if (i < customers.size() - 1) {
                        statement.add();
                    }
                }

                return Flux.from(statement.execute())
                        .concatMap(result ->
                                Flux.from(result.getRowsUpdated()))
                        .then();
            },
            connection -> Mono.from(connection.close()),
            (connection, error) -> Mono.from(connection.close()),
            connection -> Mono.from(connection.close())
    );
}
```

This example uses PostgreSQL placeholders (`$1`, `$2`, `$3`). For drivers using `?`, change the SQL syntax to match the driver; SPI bind indices are still passed by parameter position on the statement.

Points to note:

- If the list is empty, return `Mono.empty()` without opening a connection.
- One `Statement` is created per execution.
- Each row gets its own binding set.
- `add()` is called only between binding sets; the final set is executed when `execute()` is called.
- The publisher from `execute()` is consumed so the operation actually runs.
- The connection is closed on success, error, and cancellation paths.

The example uses application-supplied IDs to focus on the binding mechanism. If the database generates IDs, check your specific driver's support for returning generated values across multiple binding sets; do not assume every driver returns generated keys identically.

## 8. Binding null values with `bindNull`

`Statement.bind(index, value)` does not accept `null` as an ordinary bind value. When a parameter requires SQL `NULL`, use `bindNull(index, type)` and provide the corresponding Java type:

```java
statement.bind(0, customer.id())
        .bind(1, customer.name());

if (customer.note() == null) {
    statement.bindNull(2, String.class);
} else {
    statement.bind(2, customer.note());
}
```

The type passed to `bindNull` tells the driver the parameter type of the null value. Choose a type compatible with the column and driver, such as `String.class` for string columns, `Long.class` for 64-bit integers, or `LocalDateTime.class` for the corresponding timestamp type.

When using `Statement.add()`, every binding set must populate all required placeholders. If a field is nullable, each set must call `bindNull` for that field rather than omitting the parameter. Otherwise, the driver may fail with an unbound parameter error.

## 9. Example with multiple binding sets and nullable columns

```java
public record CustomerImportRow(
        Long id,
        String name,
        String note
) {
}

public void addCustomerBinding(
        Statement statement,
        CustomerImportRow row) {

    statement.bind(0, row.id())
            .bind(1, row.name());

    if (row.note() == null) {
        statement.bindNull(2, String.class);
    } else {
        statement.bind(2, row.note());
    }
}
```

Then iterate over the data:

```java
Statement statement = connection.createStatement(
        "INSERT INTO customer_import (id, name, note) VALUES ($1, $2, $3)");

for (int i = 0; i < rows.size(); i++) {
    addCustomerBinding(statement, rows.get(i));

    if (i < rows.size() - 1) {
        statement.add();
    }
}
```

Extracting binding logic into a separate helper ensures every value set follows the same order and null rules. With many columns or custom types, write tests verifying each bind position maps to the right column.

## 10. Comparison table of the two mechanisms

| Criterion | `Batch` | `Statement` with `add()` |
| --- | --- | --- |
| Created via | `connection.createBatch()` | `connection.createStatement(sql)` |
| Add method | `add(String sql)` | `add()` |
| Unit added | A SQL query as a string | Current bound parameter set for the same SQL query |
| Parameter binding | No binding API | Has `bind` and `bindNull` |
| SQL shape count | Can add different SQL statements | One SQL structure across binding sets in the statement |
| Typical use case | Multiple static SQL commands | Repeated insert/update with varying data |
| Safety with dynamic data | Unsuitable for interpolating values into SQL | Safe via bind parameters |
| Result | Publisher of `Result` | Publisher of `Result` |
| Transaction | Does not guarantee atomicity | Does not guarantee atomicity |

Quick selection rules:

- Multiple static SQL statements without bindings: consider `Batch`.
- Same SQL query, multiple data sets: use `Statement` with `bind` and `add()`.
- Need entity mapping, converters, callbacks, and repository abstraction: use the appropriate Spring Data API.
- Need complex SQL where each operation is parameterized: use `DatabaseClient` or parameterized `Statement`; never concatenate data into SQL.

## 11. Is `saveAll()` always an SPI batch?

Spring Data R2DBC provides `ReactiveCrudRepository.saveAll(...)` to persist multiple entities:

```java
public Flux<Customer> importCustomers(Publisher<Customer> customers) {
    return customerRepository.saveAll(customers);
}
```

This is a repository-level abstraction. It lets the application work with entities, mapping metadata, conversions, and Spring Data persistence features. However, the `saveAll` signature is not a commitment that the implementation calls `Connection.createBatch()` or creates a `Statement` and calls `Statement.add()` across all drivers and versions.

The execution strategy can depend on Spring Data Relational, the driver, and entity characteristics such as generated IDs, callbacks, or mapping. Do not infer network round-trip counts solely from the name `saveAll`. If performance requires SPI-level batching, measure the actual implementation or explicitly use the appropriate API.

When dropping down to the direct SPI, the application becomes responsible for type binding, domain value conversions, generated keys, mapping, error handling, and connection lifecycle. You do not automatically keep entity mapping conveniences simply because the same `ConnectionFactory` is used.

## 12. `DatabaseClient` and parameter binding

Spring's `DatabaseClient` provides a SQL API with parameter binding:

```java
public Mono<Long> insertCustomer(CustomerCommand command) {
    return databaseClient.sql(
                    "INSERT INTO customer (name, email) " +
                    "VALUES (:name, :email)")
            .bind("name", command.name())
            .bind("email", command.email())
            .fetch()
            .rowsUpdated();
}
```

`DatabaseClient` uses Spring-style named placeholders (`:name`, `:email`) and translates them to the binding format supported by the driver. It is a higher-level API than direct `Statement` usage and avoids manual connection management in standard cases.

A `DatabaseClient.sql(...).bind(...).fetch()` call describes a single execution. Do not assume calling `.bind()` multiple times creates multiple binding sets like `Statement.add()`. When repeating the same SQL across multiple records, you can use `saveAll`, controlled iteration over `DatabaseClient` operations, or SPI `Statement.add()` when explicit batch binding is needed.

For null values, `DatabaseClient` provides null-binding methods such as `bindNull(name, type)`; use the API matching your Spring Framework/Spring Data version.

## 13. Batching does not automatically create a transaction

A common mistake is thinking that statements in a `Batch` or binding sets on a `Statement` always succeed or fail together. Batching and transactions are two separate concepts:

- **Batching** groups multiple statements or binding sets into one API execution.
- **Transactions** define commit/rollback boundaries and database atomicity.

Without a transaction, some statements may already have executed before a later statement raises an error. The exact result and behavior depend on the driver/database. Do not assume a failed batch automatically undoes all earlier changes.

If multiple writes must succeed or roll back together, execute them inside a transaction. In a Spring application, for operations managed through repositories or `DatabaseClient`, you can use `@Transactional` on reactive methods or `TransactionalOperator`.

```java
public Mono<Void> importCustomers(List<CustomerCommand> commands) {
    return transactionalOperator.transactional(
            Flux.fromIterable(commands)
                    .concatMap(command -> databaseClient.sql(
                                    "INSERT INTO customer (name, email) " +
                                    "VALUES (:name, :email)")
                            .bind("name", command.name())
                            .bind("email", command.email())
                            .fetch()
                            .rowsUpdated())
                    .then()
    );
}
```

This example shows a reactive transaction wrapping `DatabaseClient` operations inside the same Spring-managed transaction context. It does not use `Statement.add()`; the inserts remain separate `DatabaseClient` operations. If you call `ConnectionFactory.create()` directly to obtain a connection outside Spring's transaction machinery, do not assume that connection automatically joins `TransactionalOperator`'s transaction. When working directly at the SPI level, manage the transaction on that connection itself or use an appropriate transaction-aware connection lookup.

## 14. Transactions when using the SPI directly

When obtaining a `Connection` directly from `ConnectionFactory`, you can control transactions through SPI methods such as `beginTransaction()`, `commitTransaction()`, and `rollbackTransaction()`.

Conceptual flow:

```text
create connection
begin transaction
create Batch or Statement
bind/add and execute
consume all Results
    if success: commit
    if error: rollback
close connection
```

Begin, commit, and rollback operations are all reactive publishers; wire them into the pipeline and handle both errors and cancellation. Do not call `subscribe()` piecemeal on individual steps, as doing so can break ordering, resource management, and error propagation.

In Spring applications, prefer Spring's transaction manager when all operations use the same transaction-aware connection infrastructure. When managing the SPI manually, ensure a single connection is used throughout the transaction and closed across completion, error, and cancel branches.

## 15. Execution results and `rowsUpdated`

`Batch.execute()` and `Statement.execute()` return a publisher of `Result`. For write operations, `Result.getRowsUpdated()` can provide the affected row count:

```java
Flux<Long> affectedRows = Flux.from(statement.execute())
        .concatMap(result -> Flux.from(result.getRowsUpdated()));
```

Do not always assume there is only one `Result`, or read just `Mono.from(execute())` if the driver can emit multiple results. Consume the publisher according to the API contract and application requirements.

If you only need to know that execution completed, you can ignore the counts using `.then()`. If you need to total the rows written, sum the values in a controlled way:

```java
Mono<Long> totalRowsUpdated = Flux.from(statement.execute())
        .concatMap(result -> Flux.from(result.getRowsUpdated()))
        .reduce(0L, Long::sum);
```

Whether affected row counts are reported and how results are represented depend on the statement type and driver. If the application needs exact counts for business logic, verify against the target driver and database.

## 16. The driver determines the batching strategy

The R2DBC SPI standardizes the API contract, but does not require every driver to implement batching with the same physical strategy. Depending on the driver, a batch may be sent via a native protocol, executed sequentially, split into multiple transmissions, or handled through another internal mechanism.

Therefore:

- Do not assume `Statement.add()` always maps to one network round-trip.
- Do not assume `Batch` is faster than individual statements.
- Do not assume every driver supports the same batch size limits or the same generated values behavior.
- Do not infer execution order, parallelism, or atomicity beyond what the SPI/database guarantees.
- Benchmark against the real driver and database using production-like dataset sizes.

Batching can reduce application-side overhead and give the driver an opportunity to optimize, though ultimate performance also depends on indexes, constraints, triggers, write logging, locks, transactions, and concurrent load.

## 17. Splitting batches into smaller chunks

Do not accumulate an unbounded number of rows in one statement batch. An oversized batch can consume excessive memory, hold connections too long, exceed driver/database limits, or prolong transactions.

You can split data into fixed-size chunks:

```java
Flux.fromIterable(customers)
        .buffer(500)
        .concatMap(this::insertCustomerChunk);
```

`buffer(500)` creates lists of up to 500 elements; `concatMap` processes each chunk sequentially, avoiding many large batches running at once. `insertCustomerChunk` can use a `Statement` and `Statement.add()` for items within that chunk.

The size 500 is only an example. Measure execution time, memory, parameter counts, packet limits, and transaction duration under your actual workload. Smaller chunks may be better if each row has many columns or complex triggers.

If processing multiple chunks concurrently with `flatMap`, cap concurrency. Each chunk may acquire a connection and increase database load; do not let concurrent batches grow unbounded.

## 18. Errors and retries during batch execution

A batch can fail due to unique/foreign key violations, invalid data, timeouts, dropped connections, or driver errors. Errors propagate through the reactive publisher when the operation runs.

Considerations:

- If the batch is not inside a transaction, part of the operations may already have succeeded before the error occurred.
- If inside a transaction and the error properly reaches the transaction manager, the transaction can roll back all changes participating in that transaction.
- Do not blindly retry a non-idempotent write batch. The prior attempt may have written partially or completely before the connection dropped.
- For rerunnable imports, use business keys/unique constraints, upserts with clear rules, or staging tables to identify processed records.
- Classify transient errors vs. data errors. Constraint violations are usually not resolved by immediate retries.

If per-record error reporting is required, a combined batch can make identifying the failing item harder depending on the driver. In such cases, consider smaller chunks, persisting import status, or controlled per-record processing.

## 19. Connection management and concurrency

`Connection` and `Statement` are objects tied to a single execution. Do not share the same mutable `Statement` across multiple requests or concurrent reactive flows. `bind`, `add`, and `execute` calls must happen in the proper order on a single pipeline.

Avoid creating a statement outside a publisher and reusing it across subscriptions. Instead, create the connection and statement inside the execution flow per invocation. `Mono.usingWhen` or equivalent resource management helps close the connection on completion, error, or cancellation.

When importing many chunks, balance:

- Number of concurrently executing chunks.
- Number of connections in the pool.
- Connection and transaction hold duration.
- Database write capacity.
- Memory used to hold unexecuted rows.

Non-blocking R2DBC does not mean you can open an unlimited number of connections or run unlimited batches. Cap concurrency and monitor the pool and database.

## 20. Data types and conversions when using the SPI directly

When using Spring Data repositories/templates, Spring Data helps with entity mapping and custom conversions. When using the R2DBC SPI directly, the application binds Java values to the statement; the driver must support a codec for each type.

Common type examples:

| Java type | Typical SQL type | Notes |
| --- | --- | --- |
| `String` | `VARCHAR`, `TEXT` | Check length and encoding |
| `Long` | `BIGINT` | Check nulls and value ranges |
| `Integer` | `INTEGER` | Do not bind `Long` if driver/schema expects another type without verifying |
| `BigDecimal` | `DECIMAL`, `NUMERIC` | Control precision and scale |
| `Boolean` | `BOOLEAN` | Support depends on the database |
| `LocalDate` | `DATE` | Date without time |
| `LocalDateTime` | `TIMESTAMP` | Does not carry time zone |
| `Instant`/`OffsetDateTime` | Timestamp types with instant/offset semantics | Verify driver and schema |
| `UUID` | `UUID` or equivalent type | Support depends on engine and driver |

For null values, use `bindNull(index, type)`. For custom domain types, convert them to store types understood by the driver or configure an appropriate codec. Do not assume `R2dbcConverter` custom converters are automatically applied when binding directly via the SPI.

## 21. Comparison with looping multiple writes

A straightforward alternative is creating one statement per row:

```java
Flux.fromIterable(customers)
        .concatMap(customer -> databaseClient.sql(
                        "INSERT INTO customer (id, name) VALUES (:id, :name)")
                .bind("id", customer.id())
                .bind("name", customer.name())
                .fetch()
                .rowsUpdated());
```

The advantages are readability, straightforward per-row error handling, and using the higher-level `DatabaseClient` API. The downside is that each row is a separate SQL operation at the API level; the driver may not combine those operations into a batch.

With `Statement.add()`, the same statement accepts multiple binding sets and executes once at the API level. This can reduce overhead, though per-row error handling and statistics can depend on the driver. Choose based on performance, error observability, and mapping needs, then measure rather than assuming batching is always better.

## 22. Choosing an API by scenario

| Need | Approach | Reason |
| --- | --- | --- |
| Save one entity | Repository `save` or template | Preserves entity mapping and Spring Data abstractions |
| Save a publisher of entities | `ReactiveCrudRepository.saveAll` | High-level API suited for CRUD; not an SPI batch by default |
| Multiple static SQL queries without dynamic data | R2DBC `Batch` | Appends SQL strings via `Batch.add` |
| One SQL query with multiple value sets | R2DBC `Statement` + `bind` + `add()` | Reuses the same SQL query across multiple binding sets |
| Single parameterized SQL operation | `DatabaseClient` | Convenient binding and Spring-managed connections |
| Large import needing business conversions/validation | Chunked processing via service/repository or SPI as needed | Controls memory, errors, and transactions |
| Atomicity across multiple operations | Reactive transaction or transaction on the same SPI connection | Batching does not replace transactions |

## 23. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Thinking `Batch.add` and `Statement.add` are the same | Using the wrong API or unable to bind data | Remember `Batch.add(sql)` adds SQL; `Statement.add()` adds a binding set |
| Using `Batch` with user data via string concatenation | SQL injection and escaping bugs | Use `Statement` bindings or `DatabaseClient` |
| Using the wrong driver placeholder syntax | Parse or parameter binding error | Use driver-specific markers; check bind index order |
| Forgetting `Statement.add()` between binding sets | Only the last set or one set executes | Call `add` after every set except the last |
| Calling `add()` after the last set without binding a new one | May create an empty/incomplete binding set | Call `add` only when preparing a subsequent set |
| Leaving a parameter unbound in a set | Driver reports missing parameter or execution fails | Bind every placeholder, using `bindNull` when needed |
| Passing null to `bind` | Error because API does not accept null | Use `bindNull(index, type)` |
| Failing to consume the `execute()` publisher | SQL never executes | Return/subscribe to the publisher properly |
| Reading only one Result | Ignoring remaining results | Consume the entire `Result` publisher |
| Assuming a batch is automatically atomic | Partial writes may happen on error | Use a transaction when all-or-nothing is needed |
| Sharing a Statement across requests | Mixed bindings or unsafe mutable state | Create a dedicated statement per execution |
| Building an oversized batch | Higher memory, connection hold time, and timeout risk | Split into chunks and cap concurrency |
| Assuming `saveAll` always calls SPI batching | Performance expectations mismatched with implementation | Measure driver/framework or use SPI intentionally |
| Retrying an entire non-idempotent batch | May create duplicates or reprocess rows | Use transactions, unique keys, and idempotency mechanisms |

## 24. Workflow for implementing a batch write flow

When writing multiple records, you can follow this sequence:

1. Determine whether records share the same SQL structure or require different SQL statements.
2. If multiple static SQL statements, consider `Batch`; if the same SQL with multiple value sets, choose parameterized `Statement`.
3. Check placeholder syntax and bind types on the target driver.
4. Define null handling and data type conversions.
5. Choose chunk size and concurrency suited to your pool and database.
6. Manage connections and statements within the reactive lifecycle; close connections on all branches.
7. Decide whether operations need an all-or-nothing transaction.
8. Consume all `Result` items and capture affected row counts if needed.
9. Design error handling, retries, and idempotency before running repeatable imports.
10. Benchmark against the real driver/database and monitor pool, latency, throughput, locks, and errors.

## 25. Practical guidelines

- Use `Batch` for multiple application-controlled SQL string statements; never use it to interpolate dynamic values.
- Use `Statement` when executing the same SQL query with multiple bound value sets.
- Understand that `Batch.add(String)` adds a SQL query, while `Statement.add()` adds the current binding set.
- Use driver-appropriate placeholders and bind parameters in the right order.
- Call `bindNull(index, type)` for null parameters; never pass null to `bind`.
- Call `Statement.add()` between binding sets and call `execute()` after the last set.
- Create a dedicated `Statement` per execution; never share mutable objects across concurrent pipelines.
- Consume all `Result` items from the execute publisher.
- Use an explicit transaction when multiple operations must succeed or roll back together.
- For Spring Data's `saveAll`, do not assume the implementation always uses SPI batching.
- Split data into chunks and cap concurrency to protect the pool and database.
- Measure performance on the real driver; the SPI does not guarantee a single network round-trip or a fixed execution strategy.
- When using the SPI directly, take responsibility for mapping, conversions, generated values, errors, and connection lifecycle.

## 26. Conclusion

The R2DBC SPI has two batching mechanisms with distinct purposes. `Batch` groups multiple SQL strings through `Batch.add(String)` and has no parameter binding API. `Statement` holds a single SQL query with placeholders; the application binds a set of values, calls `Statement.add()` to add that set to the batch, and then binds the next set before calling `execute()`.

For multiple static SQL statements, `Batch` can be a good fit. For multiple records sharing the same structure with varying data, a parameterized `Statement` is the better choice and safer than SQL string concatenation. In Spring Data R2DBC, `saveAll` is a multi-entity persistence abstraction rather than a commitment to use `Statement.add()`. Choose the right API layer, manage transactions and connections explicitly, chunk responsibly, consume reactive results, and test against your target driver and database.
