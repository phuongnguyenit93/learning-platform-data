# ItemPreparedStatementSetter

In Spring Batch, `ItemPreparedStatementSetter<T>` is a callback used to bind an item's values to the `?` placeholders of a JDBC `PreparedStatement`. It is commonly used with `JdbcBatchItemWriter` when you want explicit control over how each object attribute is bound into the SQL statement.

For example, an `Order` has `orderId`, `customerId`, and `amount`. The writer executes the statement:

```sql
INSERT INTO orders (order_id, customer_id, amount)
VALUES (?, ?, ?)
```

`ItemPreparedStatementSetter` receives an `Order` and a `PreparedStatement`, then calls `setString`, `setBigDecimal`, or the corresponding JDBC methods to bind the three values at positions 1, 2, and 3. `JdbcBatchItemWriter` is responsible for grouping items into a batch and executing the batch; the setter only maps data for a single item.

This is positional binding, suitable when SQL uses `?` placeholders, requires explicit JDBC type control, explicit `null` handling, or complex data mapping. If you prefer named binding such as `:orderId`, you can use `ItemSqlParameterSourceProvider` or the builder's `beanMapped()`/`columnMapped()` options instead of `ItemPreparedStatementSetter`.

## What is ItemPreparedStatementSetter?

The interface resides in package `org.springframework.batch.item.database` and has a simple contract:

```java
public interface ItemPreparedStatementSetter<T> {

    void setValues(T item, PreparedStatement ps) throws SQLException;
}
```

The two parameters mean:

- `item`: the current item received by the writer, typically the output of `ItemProcessor` or an item directly from the reader if no processor is used.
- `ps`: the `PreparedStatement` used by the writer to execute the configured SQL.

The `setValues` method is called for each item in the batch to bind that item's parameters. The setter does not open connections, execute SQL itself, or commit transactions. Those responsibilities belong to `JdbcBatchItemWriter` and Spring's JDBC infrastructure.

### Position in chunk processing

```text
ItemReader<OrderInput>
        |
        v
ItemProcessor<OrderInput, Order>
        |
        v
Chunk<Order>
        |
        v
JdbcBatchItemWriter<Order>
        |
        +--> SQL: INSERT ... VALUES (?, ?, ?)
        |
        +--> ItemPreparedStatementSetter<Order>
                 |
                 +--> setString(1, orderId)
                 +--> setString(2, customerId)
                 +--> setBigDecimal(3, amount)
        |
        v
JdbcTemplate batchUpdate
        |
        v
Database
```

The reader/processor produces items. The writer takes each item, calls the setter to bind parameters, and then executes the batch. When the step runs in chunks, the writer normally operates within the chunk transaction if configured with the appropriate datasource/transaction manager.

## Configuring JdbcBatchItemWriter with a setter

The example below uses Spring Batch 5 and a Java record:

```java
public record Order(
        String orderId,
        String customerId,
        BigDecimal amount) {
}
```

Writer declaration:

```java
@Bean
JdbcBatchItemWriter<Order> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO orders (order_id, customer_id, amount)
                    VALUES (?, ?, ?)
                    """)
            .itemPreparedStatementSetter((order, ps) -> {
                ps.setString(1, order.orderId());
                ps.setString(2, order.customerId());
                ps.setBigDecimal(3, order.amount());
            })
            .build();
}
```

Main parts:

1. `.dataSource(dataSource)` provides the datasource used by the writer.
2. `.sql(...)` declares the SQL statement containing JDBC `?` placeholders.
3. `.itemPreparedStatementSetter(...)` defines how parameters are bound for each item.
4. `.build()` constructs the configured `JdbcBatchItemWriter`.

The builder can also accept a setter instance declared as a bean:

```java
@Bean
ItemPreparedStatementSetter<Order> orderParameterSetter() {
    return (order, ps) -> {
        ps.setString(1, order.orderId());
        ps.setString(2, order.customerId());
        ps.setBigDecimal(3, order.amount());
    };
}

@Bean
JdbcBatchItemWriter<Order> orderWriter(
        DataSource dataSource,
        ItemPreparedStatementSetter<Order> orderParameterSetter) {

    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("INSERT INTO orders(order_id, customer_id, amount) VALUES (?, ?, ?)")
            .itemPreparedStatementSetter(orderParameterSetter)
            .build();
}
```

Extracting the setter into a bean facilitates reuse and independent unit testing. If the application has multiple setters with the same generic type, use `@Qualifier` so Spring injects the right bean.

## Placeholder order and JDBC parameter index

JDBC numbers parameters starting from **1**, not 0. Positions in the setter must match the placeholder order in the SQL statement.

```sql
UPDATE orders
SET customer_id = ?, amount = ?, updated_at = ?
WHERE order_id = ?
```

Corresponding setter:

```java
ItemPreparedStatementSetter<Order> setter = (order, ps) -> {
    ps.setString(1, order.customerId());
    ps.setBigDecimal(2, order.amount());
    ps.setTimestamp(3, Timestamp.valueOf(order.updatedAt()));
    ps.setString(4, order.orderId());
};
```

| Position | SQL placeholder | Bound value |
| ---: | --- | --- |
| 1 | `customer_id = ?` | `order.customerId()` |
| 2 | `amount = ?` | `order.amount()` |
| 3 | `updated_at = ?` | `order.updatedAt()` as a timestamp |
| 4 | `WHERE order_id = ?` | `order.orderId()` |

If bound in the wrong order, the SQL might still run without throwing an exception while writing into the wrong columns. This is a dangerous bug because it may not surface as an exception. Keep the SQL and setter close together, use clear variable names, and write tests verifying every position.

### Every placeholder must be set on every invocation

`JdbcBatchItemWriter` reuses the prepared statement for multiple items in a batch. The setter must assign all parameters required by the SQL on every call. Never rely on values from a previous item remaining in the statement.

Incomplete example:

```java
// Avoid: when note is null, parameter 3 might retain the value from the previous bind
if (order.note() != null) {
    ps.setString(3, order.note());
}
```

Explicitly bind the null case too:

```java
if (order.note() == null) {
    ps.setNull(3, Types.VARCHAR);
} else {
    ps.setString(3, order.note());
}
```

This guarantees every item gets an independent, complete set of parameters with no value leakage from prior items.

## Choosing setter methods by data type

Prefer JDBC methods matching the SQL type so the driver receives the right data type.

| Java type | Common JDBC method | Common SQL types |
| --- | --- | --- |
| `String` | `setString(index, value)` | `VARCHAR`, `CHAR`, `TEXT` depending on driver |
| `Integer` / `int` | `setInt(index, value)` | `INTEGER` |
| `Long` / `long` | `setLong(index, value)` | `BIGINT` |
| `BigDecimal` | `setBigDecimal(index, value)` | `DECIMAL`, `NUMERIC` |
| `Boolean` / `boolean` | `setBoolean(index, value)` | `BOOLEAN` or database equivalent |
| `LocalDate` | `setDate(index, Date.valueOf(value))` | `DATE` |
| `LocalDateTime` | `setTimestamp(index, Timestamp.valueOf(value))` | `TIMESTAMP` |
| `Instant` | `setTimestamp(index, Timestamp.from(value))` | `TIMESTAMP` per application timezone convention |
| `byte[]` | `setBytes(index, value)` | `BINARY`, `VARBINARY`, `BLOB` depending on size/driver |

Example with date/time types:

```java
ps.setDate(1, Date.valueOf(order.businessDate()));
ps.setTimestamp(2, Timestamp.valueOf(order.createdAt()));
ps.setTimestamp(3, Timestamp.from(order.createdInstant()));
```

`LocalDate` carries no timezone. `LocalDateTime` also carries no timezone/offset. `Instant` represents an absolute point in time; standardize whether to store UTC or the database/driver's timezone. Never perform implicit timezone conversions between processor and setter.

### Typed null handling

When a value can be null, use `setNull(index, sqlType)` to specify the SQL type explicitly:

```java
if (order.discount() == null) {
    ps.setNull(4, Types.DECIMAL);
} else {
    ps.setBigDecimal(4, order.discount());
}
```

`setObject(index, null)` may leave the driver unable to infer the SQL type, especially with databases or columns having specialized types. `setNull` is clearer and makes code less driver-dependent.

If a column has a specialized database type, use the matching `Types` constant or an `setObject` overload with SQL type if supported by the driver. Verify against the production schema and driver, not solely on H2 or a test database.

### Enums and domain types

Enums are commonly stored as strings or numeric codes. Mapping decisions must remain consistent with the schema:

```java
ps.setString(1, order.status().name());
```

If the database stores codes like `P`, `C`, `X`, use an explicit mapper instead of `name()`:

```java
ps.setString(1, statusCodeMapper.toCode(order.status()));
```

Do not rely on `ordinal()` to persist enums if enum ordering could change across versions; inserting a new enum value in the middle can misinterpret old data.

## Setter for INSERT

For `INSERT`, the number of placeholders typically matches the number of supplied columns:

```sql
INSERT INTO orders (
    order_id,
    customer_id,
    amount,
    status,
    created_at
)
VALUES (?, ?, ?, ?, ?)
```

Setter:

```java
ItemPreparedStatementSetter<Order> insertOrderSetter = (order, ps) -> {
    ps.setString(1, order.orderId());
    ps.setString(2, order.customerId());
    ps.setBigDecimal(3, order.amount());
    ps.setString(4, order.status().name());
    ps.setTimestamp(5, Timestamp.from(order.createdAt()));
};
```

If the database auto-generates the primary key, omit the placeholder for that column if SQL uses identity/default. `ItemPreparedStatementSetter` is not a callback for retrieving generated keys and writing them back onto items. If generated keys are needed, use JDBC generated keys, appropriate sequence/returning mechanisms, or a dedicated step/service.

## Setter for UPDATE

For `UPDATE`, remember to bind parameters in both the `SET` clause and the `WHERE` clause:

```sql
UPDATE orders
SET status = ?, updated_at = ?
WHERE order_id = ?
```

```java
ItemPreparedStatementSetter<Order> updateOrderSetter = (order, ps) -> {
    ps.setString(1, order.status().name());
    ps.setTimestamp(2, Timestamp.from(order.updatedAt()));
    ps.setString(3, order.orderId());
};
```

If `WHERE` matches no records, the update count can be 0. `JdbcBatchItemWriter` checks update counts by default and can raise an error when an item updates zero rows. This is helpful when the application expects every item to affect at least one row.

If valid SQL can legitimately update 0 rows, consider `assertUpdates(false)` or adjusting the business contract. Do not disable checks merely to hide missing key errors or dropped data.

## Setter for SQL with many parameters

An SQL statement may have many parameters, such as inserting into a transaction table:

```sql
INSERT INTO payment_transaction (
    transaction_id,
    order_id,
    amount,
    currency,
    approved,
    processed_at,
    reference_code
)
VALUES (?, ?, ?, ?, ?, ?, ?)
```

```java
ItemPreparedStatementSetter<PaymentTransaction> paymentSetter =
        (payment, ps) -> {
            ps.setString(1, payment.transactionId());
            ps.setString(2, payment.orderId());
            ps.setBigDecimal(3, payment.amount());
            ps.setString(4, payment.currency());
            ps.setBoolean(5, payment.approved());
            ps.setTimestamp(6, Timestamp.from(payment.processedAt()));

            if (payment.referenceCode() == null) {
                ps.setNull(7, Types.VARCHAR);
            } else {
                ps.setString(7, payment.referenceCode());
            }
        };
```

When SQL is long, align the column list, placeholders, and setter in the exact same order. Comments in the setter linking positions to columns can help, though keeping code readable and backed by tests is best.

## Using a setter in a chunk-oriented step

The writer is attached to a step just like any other `ItemWriter`:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        JdbcBatchItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

With a chunk size of 100, the writer receives up to 100 output items per write call (the actual count may be lower at end of input or due to filtering). `JdbcBatchItemWriter` invokes the setter for each item and executes the batch update. The setter neither dictates chunk size nor manages transactions itself.

If the processor returns `null` to filter an item, that item does not reach the writer and the setter is not called for it. If the processor throws an exception, the step handles it according to configured rollback/retry/skip policies; the setter only runs for items passed to the writer.

## ItemPreparedStatementSetter vs. ItemSqlParameterSourceProvider

Spring Batch provides two common binding approaches for `JdbcBatchItemWriter`:

| Binding approach | SQL placeholder | Mechanism |
| --- | --- | --- |
| `ItemPreparedStatementSetter<T>` | Positional `?` | Calls `PreparedStatement.setX(index, value)` |
| `ItemSqlParameterSourceProvider<T>` | Named parameters like `:orderId` | Creates an `SqlParameterSource` for the item |

### Named parameters with beanMapped

If the object's property names match SQL parameter names, you can use `beanMapped()`:

```java
@Bean
JdbcBatchItemWriter<Order> namedOrderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO orders(order_id, customer_id, amount)
                    VALUES (:orderId, :customerId, :amount)
                    """)
            .beanMapped()
            .build();
}
```

The builder uses the item's properties to supply named parameters. This is concise when objects have matching bean properties and the SQL needs no special mapping.

### Named parameters with a custom provider

When named binding is needed without default property mapping, you can provide a custom `ItemSqlParameterSourceProvider`. The provider creates an `SqlParameterSource` for each item.

`ItemPreparedStatementSetter` fits better when:

- SQL already uses positional `?` placeholders.
- Specific JDBC setters must be called for each type.
- Mapping has custom logic or requires explicit `Types` control for nulls.
- You want code to explicitly display parameter order.

Named parameters fit better when:

- SQL has many columns and parameter names aid readability.
- Object property names match SQL placeholders.
- You want to reduce the risk of swapping placeholder positions.
- The team standardizes on `SqlParameterSource`.

Do not mix `ItemPreparedStatementSetter` and a parameter source provider on the same writer. Pick one binding mechanism consistent with the SQL.

## ItemPreparedStatementSetter vs. PreparedStatementSetter

The two interfaces share similar names but serve different scopes:

| Interface | Package | Data bound |
| --- | --- | --- |
| `ItemPreparedStatementSetter<T>` | `org.springframework.batch.item.database` | One Spring Batch item per callback |
| `PreparedStatementSetter` | `org.springframework.jdbc.core` | Parameters for one JDBC statement execution in Spring JDBC |

`ItemPreparedStatementSetter` additionally accepts `item`, allowing it to be called repeatedly for every element in a batch. It is a Spring Batch layer adapter enabling `JdbcBatchItemWriter` to convert each item into a parameter set.

Do not confuse this interface with `RowMapper`. `RowMapper` maps a query result row into an object; `ItemPreparedStatementSetter` maps an object into input parameters for write SQL.

## What should a setter do and avoid?

A setter should perform simple, deterministic, side-effect-free work:

- Read item attributes.
- Perform simple type conversions if needed.
- Bind all parameters onto the statement.
- Use appropriate SQL types for null values.
- Throw `SQLException` if JDBC binding fails.

A setter must avoid:

- Calling `executeUpdate()`, `executeBatch()`, or `commit()` itself.
- Closing the `PreparedStatement` or connection managed by the writer.
- Opening a new connection per item.
- Logging full payloads or calling external APIs.
- Executing other database queries in each callback if they can be handled earlier.
- Retaining a reference to `PreparedStatement` for use after the callback.
- Using mutable fields to remember a previous item.

`JdbcBatchItemWriter` manages batch execution. If a setter executes or commits itself, it can break the batch lifecycle and chunk transaction boundaries.

## Where should validation live?

`ItemPreparedStatementSetter` is the JDBC binding layer, not the ideal place for complex business validation.

For example, if `amount` must be greater than 0, validate it in the processor or a validator:

```java
public Order process(OrderInput input) {
    if (input.amount() == null || input.amount().signum() <= 0) {
        throw new InvalidOrderException("Amount must be positive");
    }

    return new Order(input.orderId(), input.customerId(), input.amount());
}
```

The setter then simply binds:

```java
ps.setBigDecimal(3, order.amount());
```

This separation lets skip/retry policies classify business errors at the processor layer, while JDBC binding errors are recognized as write failures. If a setter detects an invalid null or type, it can throw an exception, but remember that this happens during the writer phase and affects retry/skip semantics differently from processor validation.

## SQLException and exception handling

`setValues` declares `throws SQLException`. If a `PreparedStatement.setX(...)` call fails, the exception propagates to the JDBC writer/JdbcTemplate and is typically translated into a `DataAccessException` via Spring JDBC exception translation.

Possible errors include:

- Parameter type incompatible with column.
- Value exceeding `DECIMAL` precision/scale.
- String exceeding column length.
- Invalid SQL parameter index.
- Driver not supporting the requested type.
- Connection closed or JDBC error during batch execution.

Do not catch `SQLException` and ignore it inside the setter. If data cannot be bound properly, let the error propagate so Spring Batch can apply rollback/retry/skip policies. If wrapping into a business exception, preserve the cause and classify clearly.

### Retry and skip at the writer

Exceptions thrown in the setter occur during writer binding. If the step configures fault tolerance, choose appropriate exception types:

```java
.faultTolerant()
.skip(InvalidColumnValueException.class)
.skipLimit(20)
```

However, do not broadly skip SQL configuration errors or database connection failures. Infrastructure errors typically need bounded retries or failure for operator intervention. Data errors can be validated in the processor before reaching the writer.

With a batch writer, an item may sit inside a chunk alongside many others. When the writer fails, the chunk transaction may roll back; a fault-tolerant writer may need to scan to isolate the failing item. The setter can be re-invoked for items during that scan, so it must be stateless and safe to repeat.

## Batch update counts and assertUpdates

`JdbcBatchItemWriter` executes the batch and receives update counts from the JDBC driver. The builder enables `assertUpdates` by default. Its purpose is to catch cases where an item affects zero rows when the writer expects every item to update/insert at least one row.

With `UPDATE ... WHERE order_id = ?`, if an order does not exist, the update count can be 0. When `assertUpdates` is enabled, the writer throws an exception instead of silently accepting an un-updated item.

```java
new JdbcBatchItemWriterBuilder<Order>()
        .dataSource(dataSource)
        .sql("UPDATE orders SET status = ? WHERE order_id = ?")
        .itemPreparedStatementSetter((order, ps) -> {
            ps.setString(1, order.status().name());
            ps.setString(2, order.orderId());
        })
        .assertUpdates(true)
        .build();
```

If an update count of 0 is valid per business rules, you can configure `.assertUpdates(false)`, though you should inspect separate outputs/metrics to detect no-op items when needed. JDBC drivers may return special values such as `SUCCESS_NO_INFO` for batch updates; do not assume every driver always returns exact row counts.

For `INSERT`, unique constraint or foreign key violations normally raise exceptions. Do not use `assertUpdates(false)` to mask such errors; it is no substitute for handling constraints or duplicates.

## Transactions and datasources

`ItemPreparedStatementSetter` does not manage transactions. `JdbcBatchItemWriter` executes inside the transaction coordinated by the step if the writer uses the matching datasource/transaction manager.

```java
@Bean
Step writeOrdersStep(
        JobRepository jobRepository,
        @Qualifier("ordersTransactionManager") PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        JdbcBatchItemWriter<Order> writer) {

    return new StepBuilder("writeOrdersStep", jobRepository)
            .<Order, Order>chunk(200, transactionManager)
            .reader(reader)
            .writer(writer)
            .build();
}
```

In multi-datasource setups, ensure the writer uses a datasource managed by the step's transaction manager if inserts/updates must roll back with the chunk. If the writer uses a different datasource, the step's local transaction will not automatically roll back that resource.

| Configuration | Consequence |
| --- | --- |
| Writer and step share datasource/transaction manager | Batch writes join chunk transaction; exceptions roll back uncommitted changes |
| Writer uses a different datasource | May run in an independent transaction; requires coordination or idempotency |
| Setter opens its own connection | Bypasses step-managed transaction; avoid doing this |
| Setter commits manually | Breaks chunk atomicity; avoid doing this |

When the writer shares the transaction resource, if an item in the batch fails and the transaction rolls back, current chunk changes are rolled back per database semantics. Previously committed chunks persist.

## Thread safety and reusing setters

`JdbcBatchItemWriter` is designed for batch processing and can be shared once configured. However, a custom `ItemPreparedStatementSetter` must also be safe for how the writer is used.

A stateless setter is generally safe:

```java
ItemPreparedStatementSetter<Order> setter = (order, ps) -> {
    ps.setString(1, order.orderId());
    ps.setBigDecimal(2, order.amount());
};
```

A setter with mutable fields holding the current item can suffer race conditions if called concurrently by multiple threads:

```java
// Avoid: shared state across invocations
private String currentOrderId;

public void setValues(Order order, PreparedStatement ps) throws SQLException {
    currentOrderId = order.orderId();
    ps.setString(1, currentOrderId);
}
```

Use local variables and read only the item passed in. Never store `PreparedStatement` in a field. If the setter needs a mapper driven by configuration, that mapper should be immutable or thread-safe.

With multi-threaded steps or multiple flows sharing a writer, evaluate both the JDBC connection/transaction model and the thread safety of custom collaborators. Do not assume a stateful setter is safe merely because Spring manages the writer as a singleton.

## Testing ItemPreparedStatementSetter

Write unit tests to verify per-parameter mapping and integration tests to verify batch writes and transactions against a database.

### Unit testing with a mock PreparedStatement

Isolated tests can verify that exact positions and JDBC types are called:

```java
@Test
void bindsOrderFieldsToExpectedPositions() throws SQLException {
    PreparedStatement ps = mock(PreparedStatement.class);
    ItemPreparedStatementSetter<Order> setter = (order, statement) -> {
        statement.setString(1, order.orderId());
        statement.setString(2, order.customerId());
        statement.setBigDecimal(3, order.amount());
    };

    Order order = new Order(
            "O-1001",
            "C-20",
            new BigDecimal("125.50"));

    setter.setValues(order, ps);

    verify(ps).setString(1, "O-1001");
    verify(ps).setString(2, "C-20");
    verify(ps).setBigDecimal(3, new BigDecimal("125.50"));
}
```

This unit test proves the setter calls the right JDBC methods and parameter indexes. It does not prove SQL schemas, drivers, or transactions work properly.

### Unit testing null binding

```java
@Test
void bindsNullWithExplicitSqlType() throws SQLException {
    PreparedStatement ps = mock(PreparedStatement.class);
    OrderWithNote order = new OrderWithNote("O-1", null);

    setter.setValues(order, ps);

    verify(ps).setNull(2, Types.VARCHAR);
}
```

Tests should cover both present and absent values to verify every invocation binds all parameters.

### Integration testing with JdbcBatchItemWriter

Use a test database with the matching schema. Launch the step containing the writer and verify:

- The exact number of rows inserted/updated.
- Each column value matches the input item.
- Decimal scale, date/time, and nulls are persisted properly.
- Parameter order in SQL is not swapped.
- Multi-item batches do not leak values from previous items.
- Unique/foreign key violations are handled per desired policy.

For example, a test can launch the job via `JobLauncherTestUtils`, then query using `JdbcTemplate`:

```java
List<OrderRow> rows = jdbcTemplate.query(
        "SELECT order_id, customer_id, amount FROM orders ORDER BY order_id",
        (rs, rowNum) -> new OrderRow(
                rs.getString("order_id"),
                rs.getString("customer_id"),
                rs.getBigDecimal("amount")));

assertEquals(2, rows.size());
assertEquals("O-1001", rows.get(0).orderId());
assertEquals(new BigDecimal("125.50"), rows.get(0).amount());
```

`OrderRow` is a test record defined by the application. For realistic tests, use distinct identifying `JobParameters` to avoid old execution metadata affecting the run.

### Testing chunk rollback

Create a batch with multiple items where one item causes a failure during binding or database execution. Verify the chunk transaction rolls back when the writer and `JobRepository`/business datasource use matching transaction resources. Confirm previously committed chunks remain intact.

Do not merely assert the job is `FAILED`; query the target table to verify actual persisted data. If drivers differ in batch update behavior, run tests on a database/driver equivalent to production.

### Testing assertUpdates

With an SQL update that finds no rows, verify behavior when `assertUpdates(true)` and when `false`. If zero updates is valid, tests must confirm the application has metrics or other logic to notice items with no effect.

## Batch and setter performance

`ItemPreparedStatementSetter` is called per item, while SQL executes in batches coordinated by the writer. To preserve throughput:

- Avoid allocating unnecessary objects or formatting large strings inside the setter.
- Never query the database or make HTTP calls per item inside the setter.
- Use exact JDBC setters to avoid unnecessary conversions.
- Keep binding logic short and deterministic.
- Choose chunk size based on throughput, transaction duration, and database limits.
- Verify the JDBC driver supports efficient batch updates and is configured properly.
- Benchmark with representative data, including nulls and large data types.

Do not use an excessively large chunk size just to reduce writer calls. Overly large batches can increase memory, lock duration, and rollback time. Choose sizes using real benchmarks and metrics.

## Common mistakes

### Using 0-based indexing

JDBC parameter indexes start at 1. Index 0 causes `SQLException` or binding errors.

### Setter order not matching SQL

SQL may run while putting values into the wrong columns. Cross-check placeholders and setter positions; add unit tests for mapping.

### Omitting parameter binding when value is null

The prepared statement may retain an old value or the driver may fail. Call `setNull` with the appropriate SQL type.

### Using `setObject` for every type

Drivers may infer types differently. Prefer `setString`, `setBigDecimal`, `setTimestamp`, or an overload with explicit SQL type.

### Concatenating item strings into SQL

Direct string concatenation introduces quoting bugs and SQL injection risks. Use `?` placeholders and bind via `PreparedStatement`.

### Executing or committing inside the setter

The setter only binds parameters. `JdbcBatchItemWriter` manages batch execution; the step's transaction manager handles commits/rollbacks.

### Catching and ignoring SQLException

The writer may proceed as if parameters were valid. Let exceptions propagate for the framework to handle properly.

### Putting business validation inside the setter

Errors surface during the write phase and are hard to separate from JDBC failures. Validate data in the processor/domain layer; keep the setter focused on binding.

### Using a mutable setter in a multi-threaded step

Shared state can be overwritten across items. Keep setters stateless and use local variables.

### Confusing ItemPreparedStatementSetter with PreparedStatementSetter or RowMapper

`ItemPreparedStatementSetter` binds a Spring Batch item; `PreparedStatementSetter` belongs to Spring JDBC; `RowMapper` maps a result row into an object.

### Ignoring update counts

An `UPDATE` may affect zero rows. Keep `assertUpdates` configured appropriately and test zero-update outcomes per business contract.

## Implementation principles

When using `ItemPreparedStatementSetter`, verify:

1. Does the SQL use `?` placeholders and does their count match the setter?
2. Is every JDBC position bound to the right column in exact order?
3. Does every callback invocation bind all parameters completely?
4. Are nulls bound with appropriate SQL types?
5. Are date/time, decimal, enum, and binary mappings consistent with the schema?
6. Is the setter stateless, retaining no `PreparedStatement` and causing no side effects?
7. Do the writer and step use compatible datasources/transaction managers?
8. Does `assertUpdates` reflect expected update counts?
9. Are exceptions classified properly for retry/skip/fail?
10. Have tests verified parameter mapping, batch output, rollback, and the database driver?

For positional SQL, `ItemPreparedStatementSetter` offers direct and explicit binding. Keep the setter small, use properly typed JDBC methods, always bind all parameters, and let `JdbcBatchItemWriter` execute batches inside the step's transaction. If SQL has many columns and parameter names aid readability, consider a named parameter provider. In either case, test against a production-equivalent database/driver and verify actual business data after commits/rollbacks.

## Key takeaways

`ItemPreparedStatementSetter<T>` maps an item onto `?` placeholders of a `PreparedStatement` via `setValues(item, ps)`. JDBC parameter indexes start at 1 and must match the exact placeholder order in SQL. The setter only binds values; `JdbcBatchItemWriter` executes the batch while the step's transaction manager controls commit/rollback. Bind every parameter on each invocation, use typed JDBC methods and `setNull(index, Types.X)` for nulls. Keep the setter stateless, never execute/commit/close statements manually, and never concatenate data into SQL. Use `ItemSqlParameterSourceProvider`/`beanMapped()` if named parameters are preferred. Unit test mapping separately with a mock `PreparedStatement`, then integration-test against a database to confirm batch output, update counts, null/type mapping, and rollbacks.
