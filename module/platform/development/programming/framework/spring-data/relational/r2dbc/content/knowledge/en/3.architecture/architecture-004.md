# Role of DatabaseClient in Spring R2DBC

`DatabaseClient` is Spring Framework's lower-level SQL access API for R2DBC. It provides a unified way to create statements, bind parameters, execute SQL asynchronously, and read results as reactive publishers. In the Spring Data R2DBC architecture, `DatabaseClient` is a foundational component: `R2dbcEntityTemplate` uses it to perform entity-mapped operations, while repositories provide a higher-level abstraction for CRUD workflows.

When working directly with `DatabaseClient`, developers explicitly write SQL and decide how to map each result row into application data types. In return, the application gains explicit control over column projections, joins, database-specific queries, bulk updates, and statements that are awkward to express with repository methods.

## 1. Where Does DatabaseClient Sit in the Architecture?

Spring R2DBC organizes data access layers from a low-level SQL API up to entity-oriented abstractions. A typical flow can be pictured as follows:

```text
Application service
        |
        +-----------------------------+
        |                             |
        v                             v
Spring Data repository          DatabaseClient
        |                             |
        v                             |
R2dbcEntityTemplate                  |
        |                             |
        +-------------+---------------+
                      |
                      v
               R2DBC SPI
                      |
                      v
                R2DBC driver
                      |
                      v
                 Database
```

The diagram highlights two approaches at the application layer:

- **Repository / `R2dbcEntityTemplate`:** works with entities, mapping metadata, and operations following the Spring Data model.
- **`DatabaseClient`:** works directly with SQL, parameters, rows, and result metadata. The application defines how rows are transformed into DTOs or desired data types.

`DatabaseClient` uses R2DBC's `ConnectionFactory` to access the database. It handles the repetitive mechanics of SQL execution and integrates with Spring's connection management, transactions, and error handling. It is not a JDBC `JdbcTemplate` running on blocking threads: the API returns `Mono` or `Flux`, matching R2DBC's reactive model.

### Core Responsibilities

`DatabaseClient` focuses on the following responsibilities:

1. Accepting a SQL statement and creating an execution operation through R2DBC.
2. Binding parameter values to bind markers supported by the driver.
3. Executing the statement reactively.
4. Reading `Row` and `RowMetadata`, then allowing the application to map them to result types.
5. Returning results as `Mono<T>`, `Flux<T>`, or affected row counts.
6. Integrating with Spring infrastructure such as exception translation and reactive transaction management.

`DatabaseClient` does not decide business logic, infer SQL from method names, or design schemas. Queries, filter criteria, sort orders, and mapping strategies remain the application's responsibility when using this API.

## 2. When Should You Use DatabaseClient?

Use `DatabaseClient` when you need direct control over SQL while keeping a reactive programming model and Spring integration.

Common use cases:

- Multi-table join queries mapping results to a custom DTO.
- Using CTEs, window functions, subqueries, expressions, or database-specific syntax.
- Projection queries selecting only required columns instead of loading an entire entity.
- Executing update or delete statements with complex conditions.
- Running analytical, reporting, or data aggregation queries.
- Requiring explicit SQL to control execution plans and optimize performance.
- Statements that repository query derivation or entity operations APIs cannot express conveniently.

If business logic only needs standard CRUD on an aggregate, repositories are usually easier to read and maintain. If you need entity-based operations with flexible query construction, `R2dbcEntityTemplate` is the middle ground. Avoid rewriting all CRUD operations in manual SQL just because `DatabaseClient` can execute them.

## 3. Initializing and Configuring DatabaseClient

`DatabaseClient` requires a `ConnectionFactory`. In a Spring application, `ConnectionFactory` is usually configured from an R2DBC driver and database connection details.

You can create the client directly:

```java
import io.r2dbc.spi.ConnectionFactory;
import org.springframework.r2dbc.core.DatabaseClient;

DatabaseClient databaseClient = DatabaseClient.create(connectionFactory);
```

Or declare it as a bean in Spring configuration when the application needs to manage this bean itself:

```java
@Configuration
public class R2dbcConfiguration {

    @Bean
    DatabaseClient databaseClient(ConnectionFactory connectionFactory) {
        return DatabaseClient.create(connectionFactory);
    }
}
```

In a Spring Boot application with the R2DBC starter, take advantage of the `ConnectionFactory` configuration and auto-configured beans if already provided. Avoid creating multiple independent `ConnectionFactory` or `DatabaseClient` instances for the same database without a clear architectural reason. In particular, a client used inside a transaction must be tied to the same `ConnectionFactory` managed by the reactive transaction manager.

A builder can also be used when customization is needed:

```java
DatabaseClient databaseClient = DatabaseClient.builder()
    .connectionFactory(connectionFactory)
    .build();
```

Builder details and options may vary across Spring Framework versions. Verify the API of the version your project uses before adding custom configuration.

## 4. Executing SELECT Queries

An operation typically starts with `databaseClient.sql(...)`. Next, the application binds parameters, defines row mapping, and selects how to retrieve results.

Suppose the application has a data type:

```java
public record Customer(Long id, String name, String email) {}
```

You can query and map as follows:

```java
public Flux<Customer> findActiveCustomers(DatabaseClient databaseClient) {
    return databaseClient.sql("""
            SELECT id, name, email
            FROM customer
            WHERE active = :active
            ORDER BY id
            """)
        .bind("active", true)
        .map((row, metadata) -> new Customer(
            row.get("id", Long.class),
            row.get("name", String.class),
            row.get("email", String.class)))
        .all();
}
```

In this example:

- `sql(...)` accepts the SQL statement to execute.
- `bind("active", true)` binds a value to the named parameter `active`.
- `map((row, metadata) -> ...)` receives a `Row` along with `RowMetadata` and transforms it into `Customer`.
- `all()` returns `Flux<Customer>` containing the result rows.

The mapping function receives metadata so column info can be inspected when needed. In simple examples, the application reads columns by name. Use clear aliases in SQL to avoid ambiguity, especially when joining multiple tables with overlapping column names like `id`, `name`, or `created_at`.

### 4.1. Choosing the Right Result Retrieval Method

After mapping, `DatabaseClient` offers methods to retrieve results based on expected cardinality:

```java
// Retrieve the first row if present; ignore subsequent rows.
Mono<Customer> first = databaseClient.sql("""
        SELECT id, name, email
        FROM customer
        WHERE active = true
        ORDER BY id
        """)
    .map((row, metadata) -> new Customer(
        row.get("id", Long.class),
        row.get("name", String.class),
        row.get("email", String.class)))
    .first();
```

Key options:

| Method | Return Type | Meaning |
|---|---|---|
| `first()` | `Mono<T>` | Retrieves the first row if present; does not enforce a single-row result |
| `one()` | `Mono<T>` | Expects at most one row; multiple rows trigger a result-size error |
| `all()` | `Flux<T>` | Emits all result rows |

Choose based on the business contract. If querying by primary key and expecting at most one row, `one()` expresses that expectation more clearly. If only the first row under a defined ordering is needed, `first()` fits. If processing a collection of results, use `all()`.

Do not use `first()` to hide data integrity bugs with duplicate rows when business logic requires uniqueness. In that case, `one()` surfaces expectation violations earlier.

## 5. Safe Parameter Binding

Parameterizing queries separates input data from SQL structure. With named parameters, SQL remains readable:

```java
Mono<Customer> findById(Long id) {
    return databaseClient.sql("""
            SELECT id, name, email
            FROM customer
            WHERE id = :id
            """)
        .bind("id", id)
        .map((row, metadata) -> new Customer(
            row.get("id", Long.class),
            row.get("name", String.class),
            row.get("email", String.class)))
        .one();
}
```

Spring translates named parameters into bind markers compatible with the R2DBC driver. Marker syntax at the driver layer can differ across databases, so use `DatabaseClient`'s binding mechanism rather than concatenating values into SQL strings.

### 5.1. Null Values

You cannot bind `null` as an ordinary value in R2DBC because the driver needs to know the data type of the null parameter. Use `bindNull` and specify the type explicitly:

```java
DatabaseClient.GenericExecuteSpec spec = databaseClient.sql("""
        SELECT id, name, email
        FROM customer
        WHERE email = :email
        """);

spec = spec.bindNull("email", String.class);

Flux<Customer> result = spec
    .map((row, metadata) -> new Customer(
        row.get("id", Long.class),
        row.get("name", String.class),
        row.get("email", String.class)))
    .all();
```

If a parameter has a non-null value, use `bind("email", value)`. If the value is null, use `bindNull("email", String.class)` or the type matching the database column.

### 5.2. Never Concatenate Input Data into SQL

Do not construct queries by directly concatenating user-supplied values:

```java
// Unsafe: input data becomes part of the SQL syntax.
String sql = "SELECT * FROM customer WHERE name = '" + name + "'";
```

Bind the value instead:

```java
databaseClient.sql("SELECT id, name FROM customer WHERE name = :name")
    .bind("name", name)
    .map((row, metadata) -> new Customer(
        row.get("id", Long.class),
        row.get("name", String.class),
        null))
    .all();
```

Bind parameters are for **values**, not for replacing table names, column names, `ORDER BY` keywords, or SQL syntax fragments. If you need to pick a sort column from user input, map that choice through an allowlist:

```java
String orderColumn = switch (sortField) {
    case "name" -> "name";
    case "createdAt" -> "created_at";
    default -> "id";
};

String sql = "SELECT id, name FROM customer ORDER BY "
    + orderColumn + " LIMIT :limit";

Flux<Customer> customers = databaseClient.sql(sql)
    .bind("limit", 100)
    .map((row, metadata) -> new Customer(
        row.get("id", Long.class),
        row.get("name", String.class),
        null))
    .all();
```

In this example, `orderColumn` can only evaluate to one of the column names defined in code. Never inject arbitrary strings from a request directly into SQL structure.

## 6. Executing INSERT, UPDATE, and DELETE

Not every SQL statement returns a row set. For statements that modify data, applications are often interested in the affected row count. `fetch().rowsUpdated()` returns a `Mono<Long>` result.

Example updating status:

```java
Mono<Long> deactivateCustomer(Long customerId) {
    return databaseClient.sql("""
            UPDATE customer
            SET active = false
            WHERE id = :id
            """)
        .bind("id", customerId)
        .fetch()
        .rowsUpdated();
}
```

The emitted value indicates the number of updated rows reported by the driver. The application can use this value to determine whether a record existed or was modified:

```java
Mono<Void> deactivateOrFail(Long customerId) {
    return deactivateCustomer(customerId)
        .flatMap(rows -> rows == 1
            ? Mono.empty()
            : Mono.error(new IllegalStateException(
                "Customer does not exist or was not updated")))
        .then();
}
```

For a simple INSERT:

```java
Mono<Long> insertCustomer(String name, String email) {
    return databaseClient.sql("""
            INSERT INTO customer(name, email, active)
            VALUES (:name, :email, true)
            """)
        .bind("name", name)
        .bind("email", email)
        .fetch()
        .rowsUpdated();
}
```

If you need to retrieve an auto-generated key, the syntax depends on the database and driver. For example, PostgreSQL supports `RETURNING`:

```java
Mono<Long> insertAndReturnId(String name, String email) {
    return databaseClient.sql("""
            INSERT INTO customer(name, email, active)
            VALUES (:name, :email, true)
            RETURNING id
            """)
        .bind("name", name)
        .bind("email", email)
        .map((row, metadata) -> row.get("id", Long.class))
        .one();
}
```

`RETURNING` is a PostgreSQL-specific example, not universal SQL syntax. With other databases, use the generated-key retrieval mechanism supported by the driver and database engine.

## 7. Mapping Row to DTO and JOIN Results

A major strength of `DatabaseClient` is mapping results to the exact shape a use case needs, without having to hydrate a full entity.

Suppose you need to display orders together with customer names:

```sql
SELECT
    o.id AS order_id,
    o.total_amount AS order_total,
    c.id AS customer_id,
    c.name AS customer_name
FROM orders o
JOIN customer c ON c.id = o.customer_id
WHERE o.status = :status
ORDER BY o.id
```

Declare the DTO:

```java
public record OrderSummary(
    Long orderId,
    BigDecimal total,
    Long customerId,
    String customerName
) {}
```

Map the result:

```java
Flux<OrderSummary> findOrderSummaries(String status) {
    return databaseClient.sql("""
            SELECT
                o.id AS order_id,
                o.total_amount AS order_total,
                c.id AS customer_id,
                c.name AS customer_name
            FROM orders o
            JOIN customer c ON c.id = o.customer_id
            WHERE o.status = :status
            ORDER BY o.id
            """)
        .bind("status", status)
        .map((row, metadata) -> new OrderSummary(
            row.get("order_id", Long.class),
            row.get("order_total", BigDecimal.class),
            row.get("customer_id", Long.class),
            row.get("customer_name", String.class)))
        .all();
}
```

Aliases prevent column name collisions and clarify the meaning of each field. Pay attention to the Java types returned by the driver for each SQL type. For numeric, date/time, JSON, or custom types, verify the driver's mapping and perform explicit conversions when needed.

`Row` may only be used within the scope of the mapping callback according to the R2DBC contract. Extract required values into a DTO or application object inside the callback, rather than holding the `Row` object for use after the result has been consumed.

## 8. DatabaseClient and Spring Data Entity Mapping

An important distinction is that `DatabaseClient` focuses on SQL and result rows. When calling `map(...)`, the application reads columns and constructs objects manually. It does not automatically apply full entity metadata as the Spring Data mapping layer does.

For example, when using `DatabaseClient` directly, the application must decide:

- Which columns are selected and mapped to which properties.
- Which aliases correspond to DTO fields.
- How database types convert to Java types.
- How null values and missing columns are handled.
- How business/persistence rules like version, auditing, or timestamp updates are applied.

For entity operations, `R2dbcEntityTemplate` provides a higher abstraction. It uses Spring Data R2DBC's mapping infrastructure, including mapping metadata and converters, to convert between entities and relational data. Repositories in turn build a repository-style API on top of the entity operations layer.

| Criterion | `DatabaseClient` | `R2dbcEntityTemplate` | Repository |
|---|---|---|---|
| Abstraction level | SQL-centric, lower | Entity-centric, intermediate | Repository-centric, higher |
| Writing SQL | Direct | Can use query/update APIs or SQL via client | Can use derived queries, `@Query`, and supported APIs |
| Entity mapping | Usually write mapper manually | Integrates Spring Data converters and metadata | Built on Spring Data's entity layer |
| Custom DTO/projection | Very flexible via `map` | Has suitable query APIs, depending on use case | Supports projections per repository capabilities |
| Best suited for | Complex SQL, reporting, specialized queries | Entity operations requiring flexible control | CRUD and queries following a repository contract |

Not every Spring Data feature runs automatically when using raw `DatabaseClient`. For instance, do not assume auditing, entity callbacks, optimistic locking rules, or annotation-based mapping will automatically apply to application-written SQL. If you need those features, consider `R2dbcEntityTemplate` or repositories, or explicitly implement the corresponding rules in your statements and services.

## 9. Integrating with Reactive Transactions

`DatabaseClient` can participate in Spring-managed transactions. With R2DBC, the common transaction manager is `R2dbcTransactionManager`. Connections are managed via the reactive context so operations within the same transaction share that transaction's connection.

Example service performing an update and then reading back the record:

```java
@Service
public class CustomerService {

    private final DatabaseClient databaseClient;

    public CustomerService(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    @Transactional
    public Mono<Customer> rename(Long id, String newName) {
        Mono<Long> update = databaseClient.sql("""
                UPDATE customer
                SET name = :name
                WHERE id = :id
                """)
            .bind("name", newName)
            .bind("id", id)
            .fetch()
            .rowsUpdated();

        Mono<Customer> readBack = databaseClient.sql("""
                SELECT id, name, email
                FROM customer
                WHERE id = :id
                """)
            .bind("id", id)
            .map((row, metadata) -> new Customer(
                row.get("id", Long.class),
                row.get("name", String.class),
                row.get("email", String.class)))
            .one();

        return update.then(readBack);
    }
}
```

When a reactive method is called within an appropriate Spring transaction context, operations in the publisher execute inside that transaction. If an operation emits an error, the transaction manager can roll back according to transaction rules.

Key principles:

- `DatabaseClient` and `R2dbcTransactionManager` must use the same corresponding `ConnectionFactory`.
- Reactive transactional methods should return a publisher (`Mono` or `Flux`) so Spring can manage execution boundaries.
- Never call `block()` inside a reactive flow to wait for database operations.
- Do not manually create separate connections via `ConnectionFactory.create()` per statement if you want operations to join a Spring-managed transaction.
- Keep transactions short enough to avoid holding connections and locks for too long.

If programmatic transaction control is needed, `TransactionalOperator` can wrap a publisher. This is useful when transaction boundaries are defined within a pipeline rather than via method-level annotations.

## 10. Reactive Lifecycle: Subscribe, Demand, and Cancellation

`DatabaseClient` operations are lazy under the reactive model. Creating a `Mono` or `Flux` describes the work; the query typically starts when the publisher is subscribed to.

```java
Flux<Customer> customers = databaseClient.sql("""
        SELECT id, name, email
        FROM customer
        WHERE active = true
        """)
    .map((row, metadata) -> new Customer(
        row.get("id", Long.class),
        row.get("name", String.class),
        row.get("email", String.class)))
    .all();
```

At the time of assigning to the `customers` variable, the application has only described the publisher. Execution is triggered when a subscriber consumes that publisher. If the same publisher is subscribed to multiple times, the SQL operation may execute again for each subscription; do not assume results are cached.

Because the result is a reactive publisher:

- Downstream regulates how many elements to receive via Reactive Streams demand.
- When downstream processes slowly, item emission can be throttled across backpressure-supporting layers.
- When a subscription is canceled, the client and driver have an opportunity to stop consuming results and release resources within their capabilities.
- Details regarding prefetching, buffering, cursors, and cancellation handling depend on the driver and database.

Backpressure does not replace SQL limits. If business logic needs at most 100 rows, add `LIMIT 100` in the query. If processing large datasets in passes, use pagination or keyset pagination instead of keeping an unbounded query open for a long time.

Avoid collecting an entire large result into a single collection:

```java
// May hold all rows in memory.
Mono<List<Customer>> allCustomers = customers.collectList();
```

For large datasets, process items individually or in bounded batches. In WebFlux, return the publisher to the web layer so the framework manages subscription; do not block threads with `.block()` on the request path.

## 11. Error Handling and Exception Translation

R2DBC drivers raise exceptions from the R2DBC ecosystem, such as connection errors, SQL syntax errors, constraint violations, or timeouts. Spring `DatabaseClient` integrates exception translation to convert many R2DBC errors into Spring's `DataAccessException` hierarchy.

This allows the service layer to handle errors using Spring's abstraction groups rather than depending entirely on each driver's specific exceptions. For example, a unique key violation can be represented by a corresponding data access exception in the `DataAccessException` hierarchy.

Example error handling in a reactive pipeline:

```java
Mono<Long> updateEmail(Long id, String email) {
    return databaseClient.sql("""
            UPDATE customer
            SET email = :email
            WHERE id = :id
            """)
        .bind("email", email)
        .bind("id", id)
        .fetch()
        .rowsUpdated()
        .onErrorMap(DataAccessException.class, ex ->
            new CustomerPersistenceException(
                "Unable to update customer email", ex));
}
```

Only translate the exceptions that the service layer genuinely wants to abstract. Never catch all exceptions and return a fake success value, as that hides data errors and prevents transactions from handling failures correctly.

Timeouts, connection resets, or network errors may be transient, yet not every statement is safe to retry. Specifically, for INSERTs or operations with side effects, determine whether the database committed before retrying to avoid executing a business action twice. Retries must have an explicit policy and consider idempotency.

## 12. Pagination and Query Limits

Because `DatabaseClient` lets you write SQL directly, the application can explicitly control returned row counts and pagination strategies.

Offset pagination example:

```java
Flux<Customer> findPage(int page, int size) {
    int safePage = Math.max(0, page);
    int safeSize = Math.max(1, Math.min(size, 200));
    long offset = (long) safePage * safeSize;

    return databaseClient.sql("""
            SELECT id, name, email
            FROM customer
            ORDER BY id
            LIMIT :size OFFSET :offset
            """)
        .bind("size", safeSize)
        .bind("offset", offset)
        .map((row, metadata) -> new Customer(
            row.get("id", Long.class),
            row.get("name", String.class),
            row.get("email", String.class)))
        .all();
}
```

Bounding `safeSize` protects the database from requests asking for excessively large pages. A deterministic `ORDER BY` ensures page ordering is consistent. For very deep pages or sequential data scans, keyset pagination is often more efficient than offset:

```sql
SELECT id, name, email
FROM customer
WHERE id > :afterId
ORDER BY id
LIMIT :size
```

The application passes the last `id` of the previous page as `afterId`. The cursor column needs deterministic ordering and an appropriate index. If sorting by multiple columns, the cursor predicate must reflect that full ordering.

`DatabaseClient` does not automatically make a query fast just because results are returned as a `Flux`. Inspect execution plans, indexes, selected columns, filter predicates, and data sizes. For large reporting queries, consider time limits, access permissions, and database load according to operational policies.

## 13. Testing DatabaseClient

Tests should verify both application behavior and actual SQL on a compatible database.

### 13.1. Integration Testing

For SQL statements with specific dialects, integration testing against the same database management system or a compatible version is a reliable way to verify:

- SQL syntax is accepted by the database.
- Bind markers and data types are handled properly by the driver.
- `Row`-to-DTO mapping works with actual data types.
- Transaction commit and rollback behave as expected.
- Constraints, generated keys, and affected row counts behave accurately.

Embedded databases or containers can be used depending on the project's test infrastructure. Do not rely solely on mocking `DatabaseClient` to conclude SQL is valid, since mocks do not execute statements on a database.

### 13.2. Verifying Reactive Publishers

Reactor's `StepVerifier` can be used to assert emitted counts, values, and terminal signals:

```java
StepVerifier.create(customerService.findActiveCustomers())
    .expectNextMatches(customer -> customer.id() != null)
    .expectNextCount(1)
    .verifyComplete();
```

The example above shows how to assert that a publisher emits items and completes. Real tests should prepare deterministic data, verify all important fields, and cover both empty-result and error cases.

### 13.3. Runtime Observability

Useful metrics when operating `DatabaseClient` include:

- Execution duration by query type and endpoint.
- Returned row counts, updated row counts, and batch sizes.
- Query error rates, timeouts, and connection errors.
- Active/idle connection counts, acquisition wait time, and connection hold time.
- Heap memory, GC, and downstream latency when processing large results.
- Execution plans and CPU, I/O, and lock utilization on the database.

Do not log sensitive query parameter values such as passwords, tokens, emails, or personal data unless security policy permits it. When tracing is needed, prefer logging operation types, durations, correlation IDs, and masked or redacted details.

## 14. Common Mistakes When Using DatabaseClient

| Mistake | Why Is It a Problem? | Solution |
|---|---|---|
| Concatenating input data directly into SQL | Can introduce SQL injection and syntax errors | Use `bind` / `bindNull` for values |
| Binding column or table names as parameters | Bind markers only represent values | Use an allowlist of permitted identifiers |
| Using `first()` when uniqueness is required | Multiple rows can be silently ignored without flagging size errors | Use `one()` when the contract expects at most one row |
| Not aliasing joined columns | Duplicate column names cause mapping mistakes | Define unique aliases and map by alias |
| Assuming entity mapping happens automatically | Raw `DatabaseClient.map` does not apply full mapping metadata | Write an explicit mapper or use `R2dbcEntityTemplate` |
| Calling `.block()` in a reactive request | Blocks threads and breaks non-blocking benefits | Return `Mono` / `Flux` and compose with Reactor operators |
| Calling `collectList()` on unbounded results | Can grow heap until out of memory | Limit in SQL and process in batches |
| Creating a publisher without subscribing | Lazy queries may never execute | Compose the publisher into the framework-subscribed flow |
| Subscribing multiple times unintentionally | The same publisher may execute SQL multiple times | Manage subscriptions explicitly; cache only intentionally |
| Using a different `ConnectionFactory` from the transaction manager | Operations may not join the same transaction | Use the same managed `ConnectionFactory` |
| Retrying all database errors | Can repeat side effects or mask persistent errors | Retry only suitable errors, with timeouts and idempotency |

## 15. Choosing DatabaseClient, Template, or Repository

The decision should be based on the level of SQL control and entity support required by the use case.

| Need | Commonly Suitable Choice | Reason |
|---|---|---|
| Simple CRUD on an aggregate | Spring Data repository | Concise API, clear business intent, and reduced boilerplate |
| Flexible entity operations with Spring Data mapping | `R2dbcEntityTemplate` | Retains entity metadata and converters while being more flexible than repository methods |
| Complex SQL, joins, and custom projections | `DatabaseClient` | Direct control over SQL statements and mappers |
| Reporting, analytics, or database-specific queries | `DatabaseClient` | Easy to leverage database expressions and SQL features |
| Full manual control over each returned column | `DatabaseClient` | Mapper only reads selected columns |
| Leveraging Spring Data lifecycle, auditing, and entity mapping | Repository or `R2dbcEntityTemplate` | Integrates with Spring Data's mapping layer and callbacks |

These options can coexist within a single application. A service can use repositories for common CRUD operations, `R2dbcEntityTemplate` for flexible entity queries, and `DatabaseClient` for reporting queries or specialized SQL. Establish team conventions so each use case uses an abstraction that is clear and easy to test.

## 16. Design Principles When Introducing DatabaseClient to a Project

1. **Place SQL where it is easy to find and test.** Group queries in repository adapters or persistence classes matching the architecture, avoiding scattering raw SQL strings in controllers.
2. **Use bind for all input values.** Guard dynamic identifiers separately with allowlists.
3. **Choose the right publisher type.** Use `Mono` for single results or affected row counts; use `Flux` for result sets.
4. **Define cardinality clearly.** Use `one()` when expecting at most one row, `first()` when only the first row is needed, and `all()` when all results are required.
5. **Enforce limits in SQL.** Use filters, `LIMIT`, pagination, and proper indexes; do not treat reactive streams as a row-count limit.
6. **Map intentionally.** Use clear aliases, check driver data types, and select only needed columns.
7. **Keep transactions short and consistent.** Ensure the same `ConnectionFactory` and avoid blocking publishers.
8. **Make errors observable.** Do not swallow exceptions; establish clear policies for retries, timeouts, and business error handling.
9. **Measure on a real database.** Use integration tests, execution plans, and metrics to verify performance.
10. **Pick just enough abstraction.** Use repositories or templates when entity mapping adds value; use `DatabaseClient` when direct SQL delivers clear benefits.

`DatabaseClient` acts as a bridge between a reactive Spring application and database SQL statements. It provides a non-blocking execution API, safe parameter binding, flexible result mapping, and integration with Spring transactions. By understanding its boundaries relative to `R2dbcEntityTemplate` and repositories, development teams can select the right abstraction layer for each query, keep SQL transparent, and build a maintainable data access layer in Spring R2DBC.
