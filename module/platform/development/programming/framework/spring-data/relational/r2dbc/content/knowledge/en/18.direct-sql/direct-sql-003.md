# Reading `Row`, `RowMetadata`, and Manual Result Mapping

When using direct SQL with Spring Data Relational R2DBC, applications often need to convert database results into DTOs, projections, or domain data structures themselves. Two key abstractions at the R2DBC SPI layer are `Row` and `RowMetadata`: `Row` provides the values of a single result row, while `RowMetadata` describes the columns in the result set. Spring `DatabaseClient` passes both objects into the `map((row, metadata) -> ...)` callback, enabling row-by-row mapping directly inside the reactive pipeline.

Manual mapping is appropriate when SQL queries involve joins, aggregates, complex aliases, or results that do not map directly to an entity. You must read the right data types, handle SQL `NULL`, use stable aliases, avoid retaining `Row` beyond the callback, and let the publisher manage the result lifecycle. `RowMetadata` is useful for inspecting column structure and diagnosing mapping issues; it is neither row data nor an automatic value converter.

## 1. What Are `Row` and `RowMetadata`?

The R2DBC SPI represents a query's output as a `Result`. When a result contains data rows, the application can map each row via `Row` along with its corresponding metadata.

| Type | Role | When to Use? |
| --- | --- | --- |
| `Result` | Represents the execution result of a statement | Consuming rows or affected row counts |
| `Row` | Provides values for a specific row | Reading columns by name or position and desired Java type |
| `RowMetadata` | Describes the columns of the result set | Inspecting column names, types, metadata, and column order |
| `ColumnMetadata` | Describes a single column in the result set | Checking name, Java/native type, and precision/scale if provided by driver |

Example query:

```sql
SELECT id, email, display_name
FROM customer
WHERE active = TRUE;
```

Each returned row has a `Row`. Metadata describes the columns `id`, `email`, `display_name`, while `Row` holds concrete values such as `42`, `an@example.com`, `An Nguyen`.

`RowMetadata` is typically identical across rows of the same result set. Do not treat metadata as data belonging to a specific customer; it describes the shape of the result.

## 2. Manual Mapping with `DatabaseClient`

`DatabaseClient` is Spring Framework's API for executing reactive SQL. The `map` method accepts a callback with `Row` and `RowMetadata`, returning a `FetchSpec<T>` that can be consumed via `all()`, `one()`, or `first()`.

Example:

```java
public Flux<CustomerSummary> findActiveCustomers() {
    return databaseClient.sql("""
            SELECT id, email, display_name
            FROM customer
            WHERE active = :active
            ORDER BY id
            """)
            .bind("active", true)
            .map((row, metadata) -> new CustomerSummary(
                    row.get("id", Long.class),
                    row.get("email", String.class),
                    row.get("display_name", String.class)))
            .all();
}
```

In this example, the callback receives each row and constructs a `CustomerSummary`. `all()` returns `Flux<CustomerSummary>`, so data is emitted along the reactive stream. There is no need to call `subscribe()` manually or store `Row` instances in a collection.

Mapping runs directly inside the callback. This is the right place to read the required values, check for null, and construct application-owned DTOs or entities.

## 3. Reading Columns by Name with `Row.get(String, Class<T>)`

`Row` provides a way to read values by column name:

```java
Long id = row.get("id", Long.class);
String email = row.get("email", String.class);
BigDecimal balance = row.get("balance", BigDecimal.class);
```

The first argument is the column name or alias in the result set; the second is the desired Java type. The driver is responsible for providing a value compatible with the requested type.

Reading by name is readable and less coupled to column order in the `SELECT` clause. However, the name must match the result set metadata. In joins with duplicate column names such as `id`, define distinct aliases to avoid ambiguity.

## 4. Reading Columns by Position with `Row.get(int, Class<T>)`

You can read by column index:

```java
Long id = row.get(0, Long.class);
String email = row.get(1, String.class);
String displayName = row.get(2, String.class);
```

`Row` indexes are zero-based and follow the column order in the result set. This approach can be useful in high-performance mapping or when column names are inconvenient, but the code becomes tightly coupled to the `SELECT` order.

For example, if the query changes order:

```sql
SELECT email, id, display_name
FROM customer;
```

index-based mapping with the old indexes will read the wrong columns. If using indexes, keep `SELECT` and mapping adjacent, write tests for column order, and avoid `SELECT *`.

## 5. Choosing Java Types Compatible with SQL Columns

The type passed to `row.get(...)` must be compatible with the data types supported by the driver. Common mappings include:

| Common SQL Type | Common Java Type |
| --- | --- |
| `SMALLINT` | `Short` or a compatible numeric type supported by the driver |
| `INTEGER` | `Integer` |
| `BIGINT` | `Long` |
| `NUMERIC` / `DECIMAL` | `BigDecimal` |
| `BOOLEAN` | `Boolean` |
| `VARCHAR` / `TEXT` | `String` |
| `UUID` | `UUID` if supported by the driver |
| `DATE` | `LocalDate` |
| `TIME` | `LocalTime` |
| `TIMESTAMP` | Usually `LocalDateTime` |
| `TIMESTAMP WITH TIME ZONE` | Offset-aware temporal type matching the driver, commonly `OffsetDateTime` on PostgreSQL R2DBC |
| `BINARY` / `VARBINARY` | `byte[]` or a driver-specific buffer type |

The table above is a general guide, not a guarantee of identical conversions across every database. SQL type, driver, codecs, and R2DBC version determine supported Java types. Check the driver documentation and run integration tests against the actual production database.

Do not request `Long.class` when the driver only provides `Integer` if the driver does not support that conversion. If numeric conversion is needed, read the compatible native type and convert explicitly in Java while checking for overflow.

## 6. SQL `NULL` and Java `null` Values

A SQL column may contain `NULL`. When read via `row.get(...)`, the returned value may be Java `null`. Therefore, use wrapper/reference types rather than primitives for nullable columns.

Example:

```java
Integer age = row.get("age", Integer.class);
Boolean verified = row.get("verified", Boolean.class);
OffsetDateTime deletedAt = row.get("deleted_at", OffsetDateTime.class);
```

If the column contains SQL `NULL`, the corresponding variable can be `null`. Do not use `int`, `boolean`, or `long` directly as target types because primitives cannot represent null.

DTOs can represent nullable fields using wrappers:

```java
public record CustomerProfile(
        Long id,
        String email,
        Integer age,
        Boolean verified,
        OffsetDateTime deletedAt
) {
}
```

If the domain requires a non-null value, validate and throw an explicit mapping error rather than letting a `NullPointerException` surface in code far removed from the callback.

## 7. Writing Helpers for Required and Optional Values

Small helpers can make nullability explicit:

```java
private static <T> T required(
        Row row,
        String column,
        Class<T> type) {

    T value = row.get(column, type);
    if (value == null) {
        throw new IllegalStateException(
                "Required database column is NULL: " + column);
    }
    return value;
}

private static <T> T nullable(
        Row row,
        String column,
        Class<T> type) {

    return row.get(column, type);
}
```

Usage:

```java
CustomerSummary customer = new CustomerSummary(
        required(row, "id", Long.class),
        required(row, "email", String.class),
        nullable(row, "display_name", String.class));
```

The `required` helper prevents schema or data errors from silently turning into null. In real applications, the exception can be a dedicated mapping exception for consistent logging and handling.

Do not include sensitive column values in error messages. The column name is usually sufficient for diagnostics; never log the entire row.

## 8. Using `RowMetadata` to Inspect Result Set Structure

`RowMetadata` provides column information such as the metadata list, lookup by index or name, and checking whether a column exists.

Example logging column names and Java types:

```java
private void logColumns(RowMetadata metadata) {
    metadata.getColumnMetadatas().forEach(column ->
            log.debug("column={}, javaType={}",
                    column.getName(),
                    column.getJavaType().getName()));
}
```

Some metadata also exposes native type, precision, scale, and nullability depending on the driver. Not every database/driver provides all properties with the same level of detail.

`RowMetadata` is useful when:

- Diagnosing wrong aliases or column names.
- Inspecting results of customized queries.
- Building flexible mapping based on known projections.
- Recording column types in a debug environment.
- Verifying a query returns the expected shape.

Avoid logging metadata for every row in production unnecessarily. Metadata usually repeats across a result set; log once or only enable at debug level.

## 9. Looking Up `ColumnMetadata` by Name or Index

You can retrieve metadata for a specific column:

```java
ColumnMetadata idColumn = metadata.getColumnMetadata("id");
ColumnMetadata firstColumn = metadata.getColumnMetadata(0);

String columnName = idColumn.getName();
Class<?> javaType = idColumn.getJavaType();
Type nativeType = idColumn.getType();
```

Method names and metadata types must match the R2DBC SPI version in use. `getType()` describes the type under the SPI abstraction; `getJavaType()` indicates the Java type the driver associates with the column. Native metadata may be a driver-specific type.

To check whether a column exists:

```java
if (!metadata.contains("display_name")) {
    throw new IllegalStateException("Missing display_name column");
}
```

`contains` and name-based lookup have metadata/driver-dependent semantics, especially with quoted identifiers or uppercase column names. Use simple, consistent lowercase aliases to minimize casing issues.

## 10. Using Metadata to Validate Expected Projections

For customizable queries, you can verify required columns before mapping:

```java
private void requireColumns(RowMetadata metadata, String... names) {
    for (String name : names) {
        if (!metadata.contains(name)) {
            throw new IllegalStateException(
                    "Query result is missing column: " + name);
        }
    }
}
```

Then:

```java
return databaseClient.sql("""
        SELECT id, email, display_name
        FROM customer
        WHERE id = :id
        """)
        .bind("id", id)
        .map((row, metadata) -> {
            requireColumns(metadata, "id", "email", "display_name");
            return new CustomerSummary(
                    required(row, "id", Long.class),
                    required(row, "email", String.class),
                    nullable(row, "display_name", String.class));
        })
        .one();
}
```

For static SQL in code, the metadata shape is usually verified by the query itself and integration tests. Runtime validation is more useful for queries built from multiple valid projections or internally configured SQL. Avoid repeating heavy metadata checks on every row once the structure has been verified for the result set.

## 11. Mapping DTOs from Join Results

A join query can return columns from multiple tables. If both tables have `id` or `name`, aliases are needed to avoid collisions:

```sql
SELECT
    c.id AS customer_id,
    c.email AS customer_email,
    c.display_name AS customer_name,
    o.id AS order_id,
    o.order_number AS order_number,
    o.total AS order_total
FROM customer c
LEFT JOIN orders o ON o.customer_id = c.id
WHERE c.id = :customerId
ORDER BY o.id;
```

DTO:

```java
public record CustomerOrderRow(
        Long customerId,
        String customerEmail,
        String customerName,
        Long orderId,
        String orderNumber,
        BigDecimal orderTotal
) {
}
```

Mapping:

```java
return databaseClient.sql(sql)
        .bind("customerId", customerId)
        .map((row, metadata) -> new CustomerOrderRow(
                required(row, "customer_id", Long.class),
                required(row, "customer_email", String.class),
                nullable(row, "customer_name", String.class),
                nullable(row, "order_id", Long.class),
                nullable(row, "order_number", String.class),
                nullable(row, "order_total", BigDecimal.class)))
        .all();
```

Because `LEFT JOIN` is used, columns from `orders` can be null when the customer has no orders. Mapping must use nullable types for `orderId`, `orderNumber`, and `orderTotal`. Do not use primitive `long` or `double` for those columns.

## 12. Aggregating Multiple Join Rows into One Aggregate

A query joining one customer with many orders can emit multiple rows repeating customer details. Each row can be mapped to a row DTO and then grouped into an aggregate:

```java
public record CustomerWithOrderRow(
        Long customerId,
        String customerEmail,
        Long orderId,
        String orderNumber
) {
}

public record CustomerWithOrders(
        Long customerId,
        String email,
        List<OrderSummary> orders
) {
}
```

If the query is ordered by customer ID, `collectMultimap` or a reducer can group the data. Simple example for a bounded dataset:

```java
return findCustomerOrderRows(customerId)
        .collectList()
        .flatMap(rows -> {
            if (rows.isEmpty()) {
                return Mono.empty();
            }

            CustomerWithOrderRow first = rows.get(0);
            List<OrderSummary> orders = rows.stream()
                    .filter(row -> row.orderId() != null)
                    .map(row -> new OrderSummary(
                            row.orderId(), row.orderNumber()))
                    .toList();

            return Mono.just(new CustomerWithOrders(
                    first.customerId(), first.customerEmail(), orders));
        });
```

`collectList()` gathers the entire result into memory. This works when a customer has a bounded number of orders. For very large results, use ordered grouping or bounded batches; never collect unboundedly just to build aggregate objects.

## 13. `RowMetadata` and Aliased Column Names

When using aliases:

```sql
SELECT c.id AS customer_id, o.id AS order_id
FROM customer c
LEFT JOIN orders o ON o.customer_id = c.id;
```

mapping should use the exact alias:

```java
Long customerId = row.get("customer_id", Long.class);
Long orderId = row.get("order_id", Long.class);
```

Do not rely on the original column name when the query specifies an alias. In databases with identifier case-folding rules, unquoted aliases may be converted to lowercase or uppercase. Use simple unquoted aliases and verify metadata in integration tests.

Avoid `SELECT *` in join queries because:

- Multiple columns may share the same name.
- Adding a column to a table can alter the result shape.
- Index-based mapping easily drifts out of alignment.
- The application reads more data than needed.

Explicitly listing columns and aliases makes mapping more stable.

## 14. Mapping Aggregate Results

Aggregate queries typically return one row with numeric types or nullable values:

```sql
SELECT COUNT(*) AS customer_count,
       AVG(age) AS average_age,
       MAX(created_at) AS latest_customer
FROM customer
WHERE active = :active;
```

DTO:

```java
public record CustomerStatistics(
        Long customerCount,
        BigDecimal averageAge,
        OffsetDateTime latestCustomer
) {
}
```

Mapping:

```java
return databaseClient.sql(sql)
        .bind("active", true)
        .map((row, metadata) -> new CustomerStatistics(
                row.get("customer_count", Long.class),
                row.get("average_age", BigDecimal.class),
                row.get("latest_customer", OffsetDateTime.class)))
        .one();
```

`COUNT(*)` normally returns zero when there are no rows, whereas `AVG` and `MAX` can return SQL `NULL`. Use wrapper/reference types for nullable aggregates and verify the type provided by the driver. Do not assume every database returns `COUNT` with the same Java type.

## 15. Choosing `all()`, `one()`, or `first()`

After calling `map`, `DatabaseClient` lets you choose how to consume results:

| API | Return Type | Meaning |
| --- | --- | --- |
| `all()` | `Flux<T>` | Emits all mapped rows |
| `one()` | `Mono<T>` | Expects at most one row; multiple rows cause a cardinality error |
| `first()` | `Mono<T>` | Takes the first row if present without requiring the source to have only one row |

Example:

```java
Mono<CustomerSummary> byId = databaseClient.sql(
                "SELECT id, email FROM customer WHERE id = :id")
        .bind("id", id)
        .map((row, metadata) -> new CustomerSummary(
                row.get("id", Long.class),
                row.get("email", String.class)))
        .one();
```

If a query can return multiple rows but code only needs the first row, use `first()` with an explicit `ORDER BY`. Do not use `one()` for queries that do not guarantee uniqueness. Conversely, if business logic requires a single row, keep `one()` to detect anomalous data rather than silently discarding extra rows.

## 16. Manual Mapping with R2DBC SPI `Result.map`

When working directly with the R2DBC SPI, `Statement.execute()` emits `Result`. Each result can be mapped:

```java
Statement statement = connection.createStatement("""
        SELECT id, email, display_name
        FROM customer
        WHERE active = $1
        ORDER BY id
        """);

statement.bind(0, true);

Flux<CustomerSummary> customers = Flux.from(statement.execute())
        .concatMap(result -> Flux.from(result.map((row, metadata) ->
                new CustomerSummary(
                        row.get("id", Long.class),
                        row.get("email", String.class),
                        row.get("display_name", String.class)))));
```

At the SPI layer, SQL markers and binding depend on the driver. PostgreSQL typically uses `$1` in SQL and index 0 in `Statement.bind(0, value)`. Do not copy PostgreSQL markers to drivers using `?` or other syntax.

`Result.map(...)` returns a publisher of mapped values. Results must be consumed according to the R2DBC SPI contract; do not discard the publisher from `Result.map` and do not retain `Row` after the mapper finishes.

## 17. Managing Connections When Using the SPI Directly

With `DatabaseClient`, Spring manages acquiring and releasing connections. When using `ConnectionFactory` directly, the application must close the connection on all completion, error, and cancellation paths.

Example using `Flux.usingWhen`:

```java
public Flux<CustomerSummary> findActiveCustomersDirect() {
    return Flux.usingWhen(
            Mono.from(connectionFactory.create()),
            connection -> {
                Statement statement = connection.createStatement("""
                        SELECT id, email, display_name
                        FROM customer
                        WHERE active = $1
                        """);
                statement.bind(0, true);

                return Flux.from(statement.execute())
                        .concatMap(result -> Flux.from(result.map(
                                (row, metadata) -> new CustomerSummary(
                                        row.get("id", Long.class),
                                        row.get("email", String.class),
                                        row.get("display_name", String.class)))));
            },
            connection -> Mono.from(connection.close()),
            (connection, error) -> Mono.from(connection.close()),
            connection -> Mono.from(connection.close())
    );
}
```

`usingWhen` ties cleanup to completion, error, and cancellation. This is the responsibility of direct SPI code; do not manually close connections managed by a Spring transaction manager.

If the application needs transactions, connection lifecycle and transaction begin/commit/rollback must be properly managed. For standard code, `DatabaseClient` or Spring Data repositories significantly reduce manual resource-management risk.

## 18. `Row` Should Only Be Read Inside the Mapping Callback

Do not store `Row` in fields, collections, or other publishers to read later:

```java
// Avoid: retaining Row for processing outside the callback.
List<Row> rows = new ArrayList<>();

return databaseClient.sql("SELECT id, email FROM customer")
        .map((row, metadata) -> {
            rows.add(row);
            return row;
        })
        .all();
```

`Row` is a driver-managed view over a result row. Its lifetime and backing memory depend on the driver; after the callback or result is consumed, you cannot assume the object remains valid.

Read the needed values immediately and create an independent object:

```java
return databaseClient.sql("SELECT id, email FROM customer")
        .map((row, metadata) -> new CustomerSummary(
                row.get("id", Long.class),
                row.get("email", String.class)))
        .all();
```

The DTO constructed from the read values can be passed down the pipeline. Do not pass `Row` or `RowMetadata` out of the callback for later asynchronous processing.

## 19. Do Not Keep `RowMetadata` as Part of Business Data

Metadata describes the result set structure, not a long-lived domain schema. Do not store `RowMetadata` inside entities or business caches.

If column info is needed for debugging or building a dynamic projection, extract simple values like column name, Java type, and precision/scale inside the callback and build an application-owned metadata structure. Avoid retaining driver-provided metadata objects after the result finishes unless the driver explicitly documents their lifetime.

## 20. Mapping Timestamps and Timezones

Time handling is a common source of mapping errors because SQL types differ:

- `DATE` represents a calendar date, typically mapped to `LocalDate`.
- `TIME` represents a time of day, typically mapped to `LocalTime`.
- `TIMESTAMP` has no timezone, typically mapped to `LocalDateTime`.
- `TIMESTAMP WITH TIME ZONE` has database-dependent semantics; PostgreSQL R2DBC commonly supports `OffsetDateTime`.

Example:

```java
OffsetDateTime createdAt = row.get("created_at", OffsetDateTime.class);
LocalDateTime scheduledAt = row.get("scheduled_at", LocalDateTime.class);
LocalDate birthDate = row.get("birth_date", LocalDate.class);
```

Do not convert a timezone-less timestamp into `Instant` without defining the business timezone. If the database stores UTC instants, align the types and conversion rules across schema, driver, and domain.

Test offset values, DST, and timestamp precision on the target database. Some drivers truncate fractional seconds according to column precision.

## 21. Mapping Monetary Amounts and Exact Numeric Types

For `NUMERIC`/`DECIMAL`, prefer `BigDecimal`:

```java
BigDecimal total = row.get("total", BigDecimal.class);
```

Do not use `double` for money because floating-point cannot represent decimal numbers accurately. If fixed scale is needed, verify schema precision/scale and apply rounding rules in the domain/service layer.

For `COUNT`, `SUM`, or large numbers, check the Java type returned by the driver. Do not cast `Long` to `Integer` if overflow is possible. When converting types, use checked methods like `Math.toIntExact(...)` or verify the range.

## 22. Mapping Enums

Databases can store enums as `VARCHAR`, numeric codes, or native enum types. A safe approach is to read the stored value and convert via an explicit domain function:

```java
String statusValue = row.get("status", String.class);
OrderStatus status = OrderStatus.valueOf(statusValue);
```

If the database contains legacy or unknown values, `valueOf` throws `IllegalArgumentException`. You can use a controlled parser to raise a clear mapping exception, rather than silently converting unknown values into a valid state without a policy.

If the database uses codes that do not match Java enum names, write an explicit mapping:

```java
private OrderStatus toOrderStatus(String value) {
    return switch (value) {
        case "P" -> OrderStatus.PENDING;
        case "C" -> OrderStatus.COMPLETED;
        case "X" -> OrderStatus.CANCELLED;
        default -> throw new IllegalArgumentException(
                "Unknown order status code");
    };
}
```

## 23. Mapping JSON, Arrays, and Specialized Data Types

Some databases support JSON/JSONB, arrays, spatial, or native types. R2DBC drivers may supply dedicated codecs for these types. The read type may be `String`, `Json`, `List`, `Array`, or a driver-specific type.

For PostgreSQL JSONB, for example, you can read the driver-supported type and parse it into a DTO using the application's JSON library. Do not assume every driver maps JSONB directly to `Map<String, Object>`.

For JSON data:

1. Verify the Java type provided by the driver.
2. Read the value inside the mapping callback.
3. Parse using a configured `ObjectMapper`/codec.
4. Handle JSON null, SQL NULL, and invalid JSON as distinct cases.
5. Bound payload size and avoid logging sensitive data.

For arrays, check how the driver represents them and how resources are released if a specialized buffer type is used. Prefer converting into application-owned Java structures before leaving the callback.

## 24. Distinguishing SQL `NULL`, JSON `null`, and Missing Values

These three cases have different meanings:

- SQL `NULL`: the column has no value in the database; `row.get(...)` normally returns Java `null`.
- JSON `null`: a null value inside a JSON document; the JSON column itself may not be SQL NULL.
- Column absent from the result set: the query did not select that column or used the wrong alias; this is a query shape error, not a null value.

Example:

```sql
SELECT
    NULL::text AS sql_null_value,
    '{"nickname": null}'::jsonb AS json_document;
```

When mapping, `sql_null_value` can be Java null; `json_document` is a JSON value containing a null property. Do not use `row.get(...) == null` to conclude that an inner JSON property is null.

If the API needs to distinguish unselected fields, SQL NULL fields, and JSON null, the DTO should model those states explicitly instead of using a single nullable `String` for all of them.

## 25. Mapping Errors and Result Validation

The mapping callback can raise errors when:

- A column name or alias does not exist.
- The driver does not support the requested Java type.
- A column is SQL NULL while the domain requires non-null.
- A value cannot be converted to an enum/domain type.
- Database data violates an invariant expected by the application.
- JSON or specialized data fails to parse.

Do not catch every exception and return a default DTO:

```java
// Avoid: masking mapping errors.
return databaseClient.sql(sql)
        .map((row, metadata) -> {
            try {
                return mapCustomer(row);
            } catch (Exception error) {
                return CustomerSummary.empty();
            }
        })
        .all();
```

Let mapping errors flow through the reactive pipeline or wrap them in a contextual exception without hiding the cause:

```java
return databaseClient.sql(sql)
        .map((row, metadata) -> {
            try {
                return mapCustomer(row);
            } catch (RuntimeException error) {
                throw new CustomerRowMappingException(
                        "Cannot map customer query result", error);
            }
        })
        .all();
```

Do not include sensitive row data in messages. You can log the query name, alias, and exception class for diagnostics.

## 26. Mapping and `R2dbcCustomConversions`

Spring Data Relational has `MappingR2dbcConverter` and `R2dbcCustomConversions` to convert between domain types and storage types when using Spring Data's mapping infrastructure.

When using repositories or `R2dbcEntityTemplate` with entity mapping, Spring Data can apply configured custom converters. However, a manual callback:

```java
databaseClient.sql(sql)
        .map((row, metadata) -> new DomainObject(
                row.get("custom_value", String.class)))
        .all();
```

reads directly through `Row.get`. Do not assume `R2dbcCustomConversions` is automatically applied to every `Row.get` call. If a domain type requires custom conversion, read the base type supported by the driver and invoke the converter/mapping service explicitly, or use Spring Data's mapping converter through the appropriate API.

Example converting a string code into a value object:

```java
String rawCode = row.get("account_code", String.class);
AccountCode accountCode = AccountCode.of(rawCode);
```

If you need to use `MappingR2dbcConverter` directly, verify the API of your current Spring Data Relational version and configure the converter consistently with the application's mapping context/conversions. Do not create a new converter out of sync with the entity mapping configuration.

## 27. When to Use Automatic Mapping vs. Manual Mapping?

| Need | Appropriate Choice |
| --- | --- |
| CRUD for an aggregate/entity annotated with `@Table` | Repository or `R2dbcEntityTemplate` |
| Query returning a fairly direct entity | Spring Data entity mapping |
| DTO projection of a few columns | `DatabaseClient.map(...)` or suitable projection |
| Multi-table join with dedicated aliases | Manual mapping to row DTO, then group if needed |
| Aggregates, window functions, or specialized SQL | `DatabaseClient`/SPI and manual mapping |
| Native types needing specialized codecs | Driver codec or controlled custom conversion |
| Low-level control over statements/results | R2DBC SPI `Statement` and `Result.map` |

Manual mapping is not always better. For regular entity CRUD, automatic mapping reduces boilerplate and leverages Spring Data metadata/conversions. Use manual callbacks when the query shape genuinely requires it.

## 28. Avoiding `SELECT *` and Unintended Schema-Coupled Mapping

`SELECT *` couples mapping to every existing column. When the schema adds columns, results can change and expose unnecessary data. In joins, `SELECT *` also introduces duplicate column names.

Explicitly list projections instead:

```sql
SELECT
    c.id AS customer_id,
    c.email AS customer_email,
    c.display_name AS customer_name
FROM customer c
WHERE c.id = :id;
```

Benefits:

- Mapping has an explicit contract.
- Reduces data transferred from the database.
- Avoids reading unnecessary sensitive columns.
- Keeps aliases stable across tables.
- Tests can verify exact result shapes.

## 29. Metadata Does Not Replace Schema Migration

`RowMetadata` describes the result set of the current query. It is not a schema management, migration, or database-wide validation tool.

Do not use metadata from one query to conclude that all tables share the same types or that every application instance has been migrated. If a query returns a column with the wrong type, inspect schema migrations, SQL expressions/casts, and driver codecs. Metadata only lets you observe what the query actually returned.

## 30. Mapping Results When Using `DatabaseClient` with Multi-Part `Result`

At the `DatabaseClient` level, the `map` API handles `Result` and supplies `Row` to the callback. When using the SPI directly, a statement may emit multiple `Result`s, such as when running batches or certain multi-part statements. Consume all results with proper semantics and do not discard publishers returned by `Result.map`.

Simple queries usually produce one result containing rows. For batch/update statements, you may need `getRowsUpdated()` instead of mapping rows. Do not try to map an update result with no rows into a DTO.

## 31. Distinguishing Row Results from Affected Row Counts

A `SELECT` typically returns rows; `INSERT`, `UPDATE`, and `DELETE` typically provide an affected row count. `DatabaseClient` supports:

```java
Mono<Long> updated = databaseClient.sql("""
        UPDATE customer
        SET active = :active
        WHERE id = :id
        """)
        .bind("active", false)
        .bind("id", id)
        .fetch()
        .rowsUpdated();
```

Do not use `Row`/`RowMetadata` to read the result of an update if the statement returns no result rows. If the database supports `RETURNING`, the statement can return rows:

```sql
UPDATE customer
SET active = FALSE
WHERE id = :id
RETURNING id, active;
```

In that case, you can map the returned rows like a query. `RETURNING` syntax is database-dependent.

## 32. Reading Metadata to Diagnose Column Types

During debugging, you can print column metadata:

```java
private void describe(RowMetadata metadata) {
    for (ColumnMetadata column : metadata.getColumnMetadatas()) {
        log.debug(
                "name={}, javaType={}, nativeType={}, precision={}, scale={}",
                column.getName(),
                column.getJavaType().getName(),
                column.getNativeTypeMetadata(),
                column.getPrecision(),
                column.getScale());
    }
}
```

Precision/scale or native metadata values may be absent or driver-dependent. Check nullability before dereferencing optional metadata if the API/driver allows missing values. Never use metadata logging to dump row data.

## 33. Flexible Mapping with Index and Metadata

Some internal tools need to convert a result set into a generic structure such as `Map<String, Object>`. You can iterate over metadata to discover column names, then read values by index using the Java type advertised by metadata:

```java
private Map<String, Object> toMap(Row row, RowMetadata metadata) {
    Map<String, Object> values = new LinkedHashMap<>();

    for (int index = 0; index < metadata.getColumnMetadatas().size(); index++) {
        ColumnMetadata column = metadata.getColumnMetadata(index);
        Object value = row.get(index, column.getJavaType());
        values.put(column.getName(), value);
    }

    return values;
}
```

This generic mapping has limitations. Some drivers may return Java types or native metadata that need special handling; `getJavaType()` does not guarantee every type can be serialized directly. Handle types such as `Blob`, `Clob`, buffers, arrays, and JSON separately.

With duplicate column names, `Map<String,Object>` can overwrite earlier values. Use unique aliases or namespaced keys. Do not use this generic mapping as the primary domain DTO when the result shape is known.

## 34. Caution When Using `getColumnMetadatas()` and Dynamic Column Names

If a result set has many columns, retrieve metadata once and use that list to iterate by index. Avoid reflection or dynamic class generation per row in a large result set unless needed.

Column names must come from application-controlled SQL. If a query is built dynamically from input, still allowlist identifiers; metadata does not make unsafe dynamic SQL safe.

## 35. Testing Manual Mapping

Manual mapping should be tested with a real database and driver. Some errors only surface when the driver converts types or returns metadata in a specific dialect.

Cases worth testing:

1. Mapping by alias name and by index.
2. SQL NULL column into a nullable DTO field.
3. Null in a required column throwing a clear mapping error.
4. Joins with duplicate column names given distinct aliases.
5. `LEFT JOIN` with no matching row on the right side.
6. Aggregates returning null or zero per SQL semantics.
7. Timestamps with/without timezone and precision.
8. Large numerics, decimal scale, and overflow.
9. Invalid enum codes.
10. JSON/array/native types under the driver codec.
11. Queries missing an alias or changing column type.
12. Publisher cancelled mid-result with resources cleaned up.

## 36. Integration Test Example for Mapping

Suppose a query returns a customer with a null `display_name`:

```java
@SpringBootTest
class CustomerRowMappingTest {

    @Autowired
    CustomerQueryRepository queryRepository;

    @Test
    void mapsNullableColumn() {
        StepVerifier.create(queryRepository.findSummaryById(10L))
                .assertNext(customer -> {
                    assertThat(customer.id()).isEqualTo(10L);
                    assertThat(customer.displayName()).isNull();
                })
                .verifyComplete();
    }
}
```

This test verifies mapping SQL NULL into a reference type. Fixtures must set up intentional data and the query must select the expected aliases. For production drivers, run tests on Testcontainers or a compatible test database.

## 37. Example Verifying `RowMetadata`

You can test metadata shape via `DatabaseClient`:

```java
Mono<List<String>> columnNames = databaseClient.sql("""
        SELECT id AS customer_id, email AS customer_email
        FROM customer
        WHERE id = :id
        """)
        .bind("id", 10L)
        .map((row, metadata) -> metadata.getColumnMetadatas().stream()
                .map(ColumnMetadata::getName)
                .toList())
        .one();
```

This example illustrates reading the list of column names from metadata; since a query may return no rows, the mapping callback might not execute and the publisher could complete empty. If you want to verify metadata independently of row data, choose a query guaranteed to return at least one row or use test SQL suited to the database.

Do not write tests that depend on column order if mapping uses names and order is not part of the contract. Conversely, if mapping uses indexes, order must be explicitly tested.

## 38. Debugging `Column ... not found` Errors

When `row.get("column_name", ...)` fails because a column cannot be found, check:

- Does the SQL select that column?
- What is the exact alias?
- Does the database fold identifier casing?
- Does a join query have duplicate aliases?
- Was a Java property name used instead of the SQL alias?
- Was the query or projection changed without updating the mapper?

A quick step is printing `metadata.getColumnMetadatas()` in a test/debug environment to inspect actual names. Then fix the alias or mapping; never catch the exception and return null because that hides contract mismatches between SQL and code.

## 39. Debugging Incompatible Type Errors

When `row.get("amount", BigDecimal.class)` or `row.get("created_at", OffsetDateTime.class)` fails, check:

- The actual SQL type of the expression/column.
- The Java type advertised by `ColumnMetadata.getJavaType()`.
- Whether the codec/driver supports the requested type.
- Whether the query casts to another type.
- Whether the column is an expression/aggregate rather than a base column.
- Whether the timestamp type includes a timezone.
- Whether a driver version changed conversion behavior.

Do not force types with unsafe casts or turn every error into null. You can use `CAST(...)` in SQL if conversion should occur in the database, or read a compatible base type and convert explicitly in Java.

## 40. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Wrong column/alias name | Mapping fails or reads wrong column | Use stable aliases and verify metadata |
| Wrong Java type in `row.get` | Driver cannot convert value | Pick a compatible type or convert explicitly |
| Primitives for nullable columns | Cannot represent SQL NULL | Use wrapper/reference types |
| Retaining `Row` outside callback | May read a resource past its lifetime | Map immediately into DTO/domain objects |
| Retaining `RowMetadata` as domain state | Coupled to driver objects and result lifecycle | Extract needed info into application types |
| Using index but changing SELECT order | Mapping shifts across columns | Use names/aliases or test projection order |
| Using `SELECT *` in joins | Duplicate names, fragile mapping | List columns and distinct aliases explicitly |
| Confusing SQL NULL with JSON null | Wrong data semantics | Handle SQL null and JSON null separately |
| Using `one()` for multi-row queries | Cardinality error | Use `all()` or `first()` per business rules |
| Using `first()` without ORDER BY | Non-deterministic result | Add explicit ordering or a unique query |
| Assuming `R2dbcCustomConversions` applies to manual `Row.get` | Conversions do not run as expected | Read base type and convert explicitly or use mapping converter |
| Ignoring `Result.map` publisher | Rows are not consumed | Chain publisher with `concatMap`/proper operators |
| Not closing connection when using SPI | Connection leak | Use `usingWhen` or equivalent lifecycle management |
| Logging the entire row for debugging | May expose sensitive data | Log column names/types and correlation IDs |

## 41. Manual Result Mapping Workflow

When writing a direct SQL query, follow this sequence:

1. Explicitly list the columns to return; avoid `SELECT *`.
2. Assign unique, readable aliases, especially when joining multiple tables.
3. Choose `DatabaseClient.map((row, metadata) -> ...)` for Spring-layer mapping.
4. Read by column name for maintainable mapping; use indexes when justified and order is controlled.
5. Choose Java types compatible with the database/driver.
6. Handle SQL NULL using wrapper/reference types and validate required columns.
7. Use `RowMetadata` to inspect names, types, and shape when needed.
8. Convert `Row` into a DTO/domain object immediately inside the callback.
9. Choose `all()`, `one()`, or `first()` according to business cardinality.
10. When using the SPI directly, consume `Result.map` and close the connection on complete/error/cancel.
11. Verify timestamp, numeric, enum, JSON, and native types per driver.
12. Write integration tests against a schema and R2DBC driver compatible with production.

## 42. Best Practices

- `Row` holds a single row's values; `RowMetadata` describes the columns of the result set.
- Use `DatabaseClient.map((row, metadata) -> ...)` for manual mapping in the reactive pipeline.
- Read by name/alias for maintainable code; use indexes only when `SELECT` order is tightly controlled.
- Choose Java types supported by the driver; test against the real database/driver.
- Use wrapper/reference types for columns that can be SQL NULL.
- Use `RowMetadata` to inspect names, Java/native types, and precision/scale when diagnosing issues.
- Give duplicate columns distinct aliases in joins.
- Avoid `SELECT *`; select only the required columns.
- Never retain `Row` or driver metadata outside the callback/result lifecycle.
- Convert JSON, enums, timestamps, and native types via deliberate codecs/conversions.
- Do not assume `R2dbcCustomConversions` automatically applies to manual `Row.get`.
- Choose `all`, `one`, or `first` for the right cardinality and add `ORDER BY` when deterministic results are needed.
- When using the R2DBC SPI directly, consume `Result` and clean up connections on complete/error/cancel.
- Do not mask mapping errors with default DTOs or silent nulls.
- Test result shapes, nullability, data types, joins, and cancellation on a real driver.

## 43. Conclusion

`Row` and `RowMetadata` are the two core components when mapping direct SQL results in Spring Data Relational R2DBC. `Row` allows reading values by name or index with the desired Java type; `RowMetadata` provides column names, types, and driver-supported metadata attributes. `DatabaseClient.map(...)` turns each row into a DTO directly inside the reactive pipeline, while R2DBC SPI `Result.map(...)` provides the same capability at a lower level.

For stable mapping, list columns explicitly, use unique aliases, select compatible Java types, handle SQL NULL with reference types, and never retain `Row` past the callback. Use metadata to diagnose result shape, not as a substitute for schema migrations or domain validation. In direct SPI code, manage result consumption and close connections on every terminal signal. Integration tests on the actual database and driver will verify type and codec details that mocks cannot simulate.
