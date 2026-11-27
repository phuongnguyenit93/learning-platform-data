# Named Parameters, Positional Parameters, and Driver Bind Markers

When writing queries in Spring Data R2DBC, an application needs to pass values into SQL statements without concatenating raw input directly into strings. Bind parameters ensure the database treats values as data, reducing the risk of SQL injection and allowing the driver to prepare statements according to its protocol.

It is important to distinguish three concepts that are often confused:

- **Named parameter:** uses readable names such as `:email` or `:status`. This is a convenience provided by Spring Data/Spring DatabaseClient; the framework translates it into a bind marker that the driver understands.
- **Positional parameter:** values are associated with the first, second, third... position in the statement. The placeholder syntax depends on the API and driver, commonly `?` or native markers.
- **Driver bind marker:** the actual symbol that the R2DBC driver accepts in SQL—for example, PostgreSQL uses `$1`, `$2`, while many drivers use `?`. The syntax is not standardized to be identical across all databases.

Understanding this boundary helps you write queries that are readable, maintainable, and compatible with your target database.

## 1. Why bind parameters?

You should not construct SQL by concatenating user-supplied values:

```java
String sql = "SELECT * FROM customer WHERE email = '" + email + "'";
```

If `email` contains quotes or malicious SQL fragments, the statement's meaning can be altered. String concatenation also makes escaping and type handling the application's responsibility.

Instead, write the SQL statement with placeholders and pass values through a bind API:

```java
databaseClient.sql("SELECT * FROM customer WHERE email = :email")
    .bind("email", email)
    .map((row, metadata) -> row.get("id", Long.class))
    .one();
```

Here, `:email` is a parameter name recognized by Spring. The `email` value is passed separately via `.bind(...)`, so its contents never become part of the SQL syntax.

Bind parameters also help the driver handle data types, value conversions, and statement execution over the database protocol. However, binding applies only to **values**. Table names, column names, SQL keywords, sort directions, and operators are not bindable values.

## 2. Named parameters in @Query

With repositories, Spring Data R2DBC allows using named parameters inside `@Query`. This lets the SQL directly describe the meaning of each parameter.

```java
import java.util.UUID;
import org.springframework.data.r2dbc.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    @Query("""
        SELECT *
        FROM customer
        WHERE tenant_id = :tenantId
          AND email = :email
        """)
    Mono<Customer> findByTenantAndEmail(
        @Param("tenantId") UUID tenantId,
        @Param("email") String email
    );
}
```

The name after `:` must match the name declared in `@Param`. When using `@Param`, parameter names do not depend on whether the compiler preserves parameter name metadata in bytecode.

In certain configurations, Spring Data can extract parameter names directly from Java metadata if the build enables retaining parameter names (such as `-parameters`). Even so, for queries with multiple parameters or when you want code to stay explicit across build environments, explicit `@Param` annotations are usually clearer and less dependent on configuration.

### 2.1 Named parameters in DatabaseClient

`DatabaseClient` also supports named parameter syntax:

```java
Mono<Integer> updateEmail(Long id, String newEmail) {
    return databaseClient.sql("""
            UPDATE customer
            SET email = :email
            WHERE id = :id
            """)
        .bind("email", newEmail)
        .bind("id", id)
        .fetch()
        .rowsUpdated();
}
```

Parameter names in SQL are linked to the names passed into `.bind(String, value)`. You can call bind in a different order than they appear in the SQL because the framework matches by name. This makes it easier to adjust query formatting without recalculating positional indices.

Named parameters are a Spring abstraction. The framework parses the SQL, generates bind markers appropriate for the dialect/driver, and attaches values to the right markers. Do not assume the database natively understands `:email` as standard SQL.

## 3. Positional parameters

Positional parameters bind values according to placeholder order. This approach is concise for small SQL statements, but readers must carefully track the exact position of each value.

Example with the `DatabaseClient` API using placeholders supported by the target driver:

```java
Mono<Integer> updateCustomer(Long id, String email) {
    return databaseClient.sql(
            "UPDATE customer SET email = $1 WHERE id = $2")
        .bind(0, email)
        .bind(1, id)
        .fetch()
        .rowsUpdated();
}
```

This example uses PostgreSQL's native markers: `$1` is the first parameter, `$2` is the second parameter. In the R2DBC API, indices passed to `.bind(int, value)` are 0-based, so `$1` corresponds to `.bind(0, ...)` and `$2` corresponds to `.bind(1, ...)`.

For drivers that use `?`, the SQL can take the form:

```java
databaseClient.sql("UPDATE customer SET email = ? WHERE id = ?")
    .bind(0, email)
    .bind(1, id)
    .fetch()
    .rowsUpdated();
```

Do not copy a PostgreSQL example directly to a driver that uses `?` or vice versa. When using positional markers at the `DatabaseClient`/R2DBC layer, write the exact syntax supported by your application's dialect and driver.

## 4. Native R2DBC driver bind markers

The R2DBC SPI does not enforce a single placeholder symbol across all drivers. Each driver parses SQL and provides a binding mechanism appropriate for its database. Some common forms:

| Common database/driver | Marker in SQL | Positional example |
|---|---|---|
| PostgreSQL R2DBC | `$1`, `$2`, `$3` | `WHERE id = $1 AND status = $2` |
| Some other drivers | `?` or driver-specific marker | Check supported marker syntax in driver/dialect documentation |

Example using the R2DBC SPI directly with PostgreSQL:

```java
ConnectionFactory connectionFactory = ...;

Mono<Integer> update = Mono.usingWhen(
    connectionFactory.create(),
    connection -> {
        Statement statement = connection.createStatement(
            "UPDATE customer SET email = $1 WHERE id = $2");

        statement.bind(0, newEmail);
        statement.bind(1, customerId);

        return Flux.from(statement.execute())
            .flatMap(result -> result.getRowsUpdated())
            .reduce(0L, Long::sum)
            .map(Long::intValue);
    },
    Connection::close,
    (connection, error) -> connection.close(),
    Connection::close
);
```

This snippet demonstrates direct SPI usage: `createStatement` accepts SQL with native markers and `bind` takes a 0-based index. In production code, you must ensure connections are safely closed even when the publisher errors or is cancelled; prefer connection-management helpers or Spring's `DatabaseClient`/`R2dbcEntityTemplate` to avoid managing connection lifecycles manually on every query.

When using Spring Data R2DBC at the repository or `DatabaseClient` layer, prefer named parameters to reduce coupling to driver-specific marker syntax. When working directly with `Connection.createStatement`, you must follow the driver's native markers.

## 5. How do named parameters and positional parameters differ?

| Criterion | Named parameter | Positional parameter |
|---|---|---|
| Syntax | `:tenantId`, `:status` | `?`, `$1`, `$2`, or other native markers |
| Value association | By name | By order/index |
| Readability | Name conveys meaning | Requires matching positions against bind calls |
| Reordering conditions | Usually requires no change to name-based bind calls | May require updating indices or bind order |
| Driver coupling | Spring can translate named markers to appropriate driver markers | Placeholder syntax depends on driver/dialect |
| Best fit | Repository queries, multi-condition SQL, maintainable queries | Short SQL, direct SPI usage, or when explicit marker control is needed |

Both approaches pass values separately from the SQL statement and are safe when bound properly. The main differences lie in how parameters are identified and the degree of coupling to the driver.

## 6. Binding NULL values

You cannot bind `null` like an ordinary object because the framework/driver needs to know the expected SQL type of the parameter. With `DatabaseClient`, use `bindNull` and specify the Java class:

```java
databaseClient.sql("""
        UPDATE customer
        SET nickname = :nickname
        WHERE id = :id
        """)
    .bindNull("nickname", String.class)
    .bind("id", customerId)
    .fetch()
    .rowsUpdated();
```

With positional binding:

```java
databaseClient.sql("UPDATE customer SET nickname = ? WHERE id = ?")
    .bindNull(0, String.class)
    .bind(1, customerId)
    .fetch()
    .rowsUpdated();
```

The class passed to `bindNull` must match the Java type the driver uses to encode the column value. For example, a string column can use `String.class`, while numeric columns can use `Integer.class` or `BigDecimal.class`. If a column uses a specialized native type, check the driver's codec requirements.

Do not use `column = NULL` to compare against null. In SQL, you must use `IS NULL` or `IS NOT NULL`:

```sql
SELECT * FROM customer WHERE nickname IS NULL;
```

If you want an optional condition that is skipped when a parameter is null, explicitly design that logic in code or use an intentional SQL expression. The expression `(:nickname IS NULL OR nickname = :nickname)` skips filtering on that column when `nickname` is null; this can be desirable for search queries, though you must be especially cautious when using it in `UPDATE` or `DELETE`.

## 7. Binding collections and IN conditions

A query may need to find rows matching a list of IDs. With named parameters in Spring, certain APIs support expanding a collection into multiple bind markers in an `IN` clause:

```java
databaseClient.sql("SELECT * FROM customer WHERE id IN (:ids)")
    .bind("ids", ids)
    .map((row, metadata) -> mapCustomer(row))
    .all();
```

Collection expansion support and handling depend on the Spring API/version, dialect, and driver. Check the documentation for your version. Expanding a list into multiple markers differs from binding a single SQL ARRAY; the two approaches have different codec and syntax requirements.

If the list is empty, do not generate an `IN ()` query assuming every database accepts it. Handle it beforehand:

```java
if (ids == null || ids.isEmpty()) {
    return Flux.empty();
}
```

For write or delete operations, do not let an empty list accidentally turn into a broader operation like `deleteAll()`. Define the semantics of an empty list explicitly based on business rules.

## 8. Value binding cannot bind table or column names

Placeholders represent values only. The following snippets do not work as intended:

```sql
SELECT * FROM :tableName WHERE :columnName = :value
ORDER BY :sortColumn
```

The database treats placeholders as expression values, not SQL identifiers. If you need to choose a sort column or table based on a request, use an allowlist in code:

```java
String orderBy = switch (sortField) {
    case "createdAt" -> "created_at";
    case "email" -> "email";
    default -> throw new IllegalArgumentException("Unsupported sort field");
};

String direction = descending ? "DESC" : "ASC";

String sql = "SELECT id, email FROM customer ORDER BY "
    + orderBy + " " + direction;
```

In this example, the dynamic SQL parts come from controlled choices in code. The user's `sortField` is never concatenated directly. Whenever possible, use a query builder API or Spring Data's `Sort` to avoid assembling identifiers manually.

## 9. Avoiding common binding errors

### 9.1 Wrong parameter name

SQL using `:customerId` while code calls `.bind("id", value)` will fail to match. With `@Query`, the name in `@Param` must match the placeholder name. Standardize on camelCase or clear names and check errors during query execution.

### 9.2 Wrong positional binding order

With SQL `SET email = ? WHERE id = ?`, bind index 0 is email and index 1 is ID. If reversed, the database may raise a type error or update the wrong data if both types happen to be compatible. Name variables clearly and place bind calls right next to placeholder positions for easy verification.

### 9.3 Mixing marker syntax from multiple drivers

SQL using PostgreSQL's `$1` will not run on a driver that only accepts `?`. If the application must support multiple databases, prefer named parameters with a dialect-aware abstraction or separate queries by dialect. Never replace markers with naive string find-and-replace because SQL may contain marker symbols inside string literals or comments.

### 9.4 Missing type for null

Calling `.bind("note", null)` does not give the driver enough type information. Use `.bindNull("note", String.class)` or the corresponding index-and-type overload.

### 9.5 Using the wrong Java type

A `Long` bound to a UUID column or a `String` bound to a native enum column may be rejected by the driver. Choose Java types compatible with codecs and schema, or register converters.

### 9.6 Mismatched placeholder count

Every marker must have a bound value. Missing a bind or binding an out-of-range index typically causes statement failure before execution. When generating dynamic SQL, construct the placeholder list and corresponding bind calls within the same logic branch.

## 10. Repository example combining multiple named parameters

Queries with many conditions are usually easier to maintain when named:

```java
public interface OrderRepository
        extends ReactiveCrudRepository<PurchaseOrder, Long> {

    @Query("""
        SELECT *
        FROM purchase_order
        WHERE tenant_id = :tenantId
          AND status = :status
          AND created_at >= :fromTime
          AND created_at < :toTime
        ORDER BY created_at DESC
        """)
    Flux<PurchaseOrder> findOrders(
        @Param("tenantId") UUID tenantId,
        @Param("status") String status,
        @Param("fromTime") Instant fromTime,
        @Param("toTime") Instant toTime
    );
}
```

Each parameter is named according to its meaning, and the time range condition uses an inclusive lower bound (`>=`) and an exclusive upper bound (`<`). This style is convenient for time-based pagination or partitioning data intervals without boundary overlaps.

If pagination is required, you can use a repository-supported pagination API or write SQL with limit/offset according to your dialect. Limit/offset parameters are also values and should be bound, while column names in `ORDER BY` must be controlled via an allowlist or the `Sort` API.

## 11. Choosing a binding approach by data access layer

| Layer used | Approach to consider |
|---|---|
| Spring Data repository with `@Query` | Named parameters `:name` and `@Param` for explicit association. |
| `DatabaseClient` | Named parameters and `.bind("name", value)` to reduce native marker coupling. |
| `DatabaseClient` requiring positional binding | Use 0-based indices and markers supported by the dialect/driver. |
| Direct R2DBC SPI | Use the driver's native markers in `createStatement`, bind by index or name if supported by the driver. |
| Multi-database applications | Prefer dialect-based abstractions; test queries against each target driver. |

For most business queries, named parameters make code easier to read and less prone to ordering mistakes. Positional binding remains useful at lower layers or for short SQL, provided it is tightly coupled to the driver's syntax.

## 12. Checklist for parameterized queries

When adding a new query, check the following steps:

1. Identify the actual database and R2DBC driver the application uses.
2. Choose Spring named parameters or the driver's native positional markers.
3. Ensure bind names or indices match placeholders exactly.
4. Pick Java types compatible with column types and driver codecs.
5. Handle `NULL` via `bindNull` with explicit types.
6. Handle empty collections and large element counts.
7. Never bind identifiers; use allowlists for dynamic column names, table names, and sort directions.
8. Run the query against the target database/driver with normal values, nulls, special characters, and boundary data.

Named parameters, positional parameters, and native bind markers all serve to pass values safely into SQL statements. Spring Data R2DBC and `DatabaseClient` provide abstractions to reduce dependence on driver-specific markers, whereas direct R2DBC SPI requires following the syntax implemented by the driver. Choosing the right abstraction layer, binding the right types, and controlling dynamic SQL keeps queries stable, maintainable, and secure.
