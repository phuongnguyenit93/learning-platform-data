# JdbcTemplate, Named Parameters, and Result Mapping

Spring Boot provides `JdbcTemplate` to execute SQL directly against MySQL without manually managing `Connection`, `PreparedStatement`, and `ResultSet`. When a SQL statement has multiple parameters, `NamedParameterJdbcTemplate` lets you name parameters such as `:customerId` or `:status`, making statements readable and avoiding concatenating input data into SQL strings. Query results are converted into Java objects using `RowMapper`, `ResultSetExtractor`, or appropriate callbacks.

These tools are especially useful when you need fine-grained SQL control, MySQL-specific features, query tuning, or aggregated reads. They still rely on JDBC and Spring's transaction manager, so you must understand parameter binding, `NULL` handling, numeric/date-time type mapping, and proper connection management.

## 1. Configuring JdbcTemplate in Spring Boot

If an application uses `spring-boot-starter-jdbc` or `spring-boot-starter-data-jpa`, Spring Boot typically auto-configures `DataSource`, `JdbcTemplate`, and `NamedParameterJdbcTemplate` when a JDBC driver is on the classpath.

Example Maven dependencies for a Spring Boot application using JDBC directly:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
</dependency>

<dependency>
    <groupId>com.mysql</groupId>
    <artifactId>mysql-connector-j</artifactId>
    <scope>runtime</scope>
</dependency>
```

Declare connection settings in `application.yml`:

```yaml
spring:
  datasource:
    url: jdbc:mysql://localhost:3306/appdb
    username: app_runtime
    password: ${DB_PASSWORD}
    driver-class-name: com.mysql.cj.jdbc.Driver
    hikari:
      maximum-pool-size: 15
      minimum-idle: 3
      connection-timeout: 30000
```

Pool values are illustrative only; tune them based on application instance count, MySQL connection limits, and measured load. Never commit passwords to the repository. In new applications, verify Connector/J charset/timezone properties against your system data standards and use TLS when connecting over untrusted networks.

Inject templates via constructor:

```java
@Repository
public class CustomerJdbcRepository {
    private final JdbcTemplate jdbcTemplate;
    private final NamedParameterJdbcTemplate namedJdbc;

    public CustomerJdbcRepository(
            JdbcTemplate jdbcTemplate,
            NamedParameterJdbcTemplate namedJdbc) {
        this.jdbcTemplate = jdbcTemplate;
        this.namedJdbc = namedJdbc;
    }
}
```

`JdbcTemplate` and `NamedParameterJdbcTemplate` are thread-safe once configured. Do not create a new template per request; use Spring-managed beans so they share the `DataSource` and connection pool.

## 2. JdbcTemplate Handles JDBC Boilerplate

With plain JDBC, the application must acquire a connection, create a statement, bind parameters, read the result set, and close resources across every branch. `JdbcTemplate` handles that lifecycle management while translating `SQLException` into Spring's unchecked exception hierarchy (`DataAccessException`).

Simple query example:

```java
String sql = "SELECT COUNT(*) FROM customers WHERE status = ?";

Long count = jdbcTemplate.queryForObject(
        sql,
        Long.class,
        "ACTIVE"
);
```

Commonly used methods:

| Method | Purpose | Return Value |
|---|---|---|
| `query(...)` | Query multiple rows | `List<T>` or per-row callback processing. |
| `queryForObject(...)` | Query a single value or single row | One object; throws an exception if row count is not exactly one for the overload used. |
| `queryForList(...)` | Query multiple rows as maps | `List<Map<String, Object>>`. |
| `queryForMap(...)` | Single row as a map | `Map<String, Object>`. |
| `update(...)` | `INSERT`, `UPDATE`, `DELETE` | Number of affected rows. |
| `batchUpdate(...)` | Execute multiple DML operations in a batch | Array of affected row counts or batch results. |
| `execute(...)` | Low-level SQL/callback execution | Depends on overload. |

`queryForObject()` suits queries returning exactly one result, such as counts or unique-key lookups. If no row exists, Spring throws `EmptyResultDataAccessException`; if more than one row is returned for single-row overloads, it throws `IncorrectResultSizeDataAccessException`. When a result may be absent, use `query()` returning a list and convert to `Optional` per repository conventions.

Example:

```java
public Optional<CustomerSummary> findById(long customerId) {
    String sql = """
        SELECT customer_id, email, status, credit_limit
        FROM customers
        WHERE customer_id = ?
        """;

    List<CustomerSummary> rows = jdbcTemplate.query(
            sql,
            CUSTOMER_ROW_MAPPER,
            customerId
    );

    return rows.stream().findFirst();
}
```

If `customer_id` is the primary key, the query returns at most one row. For non-unique queries, `findFirst()` merely picks the first element in whatever order SQL returns; add `ORDER BY` if ordering matters.

## 3. NamedParameterJdbcTemplate and Named Parameters

In `JdbcTemplate`, positional parameters use `?`; the order of `setXxx()` calls must match positions in SQL. When a statement has many conditions, named parameters make it clear which value binds to which condition:

```java
String sql = """
    SELECT customer_id, email, status
    FROM customers
    WHERE status = :status
      AND created_at >= :fromTime
      AND created_at < :toTime
    ORDER BY created_at DESC
    """;

MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("status", "ACTIVE", Types.VARCHAR)
        .addValue("fromTime", fromTime, Types.TIMESTAMP)
        .addValue("toTime", toTime, Types.TIMESTAMP);

List<CustomerRow> customers = namedJdbc.query(
        sql,
        params,
        CUSTOMER_ROW_MAPPER
);
```

Spring translates named parameters into JDBC `?` placeholders before sending them to the driver. Values are still bound via prepared statements; this is not direct string substitution.

You can use a `Map` when parameters are simple:

```java
Map<String, Object> params = Map.of(
        "status", "ACTIVE",
        "minTotal", new BigDecimal("100.00")
);

List<CustomerRow> rows = namedJdbc.query(
        "SELECT customer_id, email, status, credit_limit " +
        "FROM customers " +
        "WHERE status = :status AND credit_limit >= :minTotal",
        params,
        CUSTOMER_ROW_MAPPER
);
```

`Map.of()` rejects `null` keys or values. When a parameter may be null or requires an explicit JDBC type, use `MapSqlParameterSource`:

```java
MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("email", nullableEmail, Types.VARCHAR)
        .addValue("status", status, Types.VARCHAR);
```

When binding `null`, declaring the SQL type helps the driver handle it consistently, especially for `DECIMAL`, date/time, binary, and specialized types.

### Named Parameters with IN Clauses

`NamedParameterJdbcTemplate` can expand a collection into multiple placeholders:

```java
String sql = """
    SELECT customer_id, email, status
    FROM customers
    WHERE customer_id IN (:ids)
    """;

MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("ids", List.of(10L, 20L, 30L));

List<CustomerRow> rows = namedJdbc.query(sql, params, CUSTOMER_ROW_MAPPER);
```

When the collection is empty, do not pass `IN (:ids)` as-is with an empty list because the generated SQL may be invalid or behave inconsistently across drivers/databases. Handle it explicitly in the application layer: return an empty list immediately if business logic expects zero matches, or omit the filter if business semantics mean no list filtering.

### Values Can Be Bound, Identifiers Cannot

Prepared statements can only bind values. You cannot use `:columnName`, `:tableName`, or `:sortDirection` to bind column names, table names, or SQL keywords. If dynamic sorting is needed, map input through an allowlist:

```java
String orderColumn = switch (sortBy) {
    case "email" -> "email";
    case "createdAt" -> "created_at";
    case "status" -> "status";
    default -> throw new IllegalArgumentException("Unsupported sort field");
};

String direction = descending ? "DESC" : "ASC";
String sql = "SELECT customer_id, email, status FROM customers "
        + "ORDER BY " + orderColumn + " " + direction;
```

Here `orderColumn` and `direction` are chosen strictly from fixed server-controlled values. Never concatenate client-supplied sort/table/column strings directly. All data values such as email, status, timestamps, and IDs must still use bind parameters.

## 4. Mapping Rows with RowMapper

`RowMapper<T>` converts the current row of a `ResultSet` into a Java object. Spring invokes `mapRow()` for each row; implementations must not call `rs.next()` themselves and must not close the `ResultSet`.

Define a DTO/record:

```java
public record CustomerRow(
        long customerId,
        String email,
        String status,
        BigDecimal creditLimit,
        LocalDateTime createdAt) {
}
```

Create an explicit mapper:

```java
private static final RowMapper<CustomerRow> CUSTOMER_ROW_MAPPER =
        (rs, rowNum) -> new CustomerRow(
                rs.getLong("customer_id"),
                rs.getString("email"),
                rs.getString("status"),
                rs.getBigDecimal("credit_limit"),
                rs.getObject("created_at", LocalDateTime.class)
        );
```

SQL should select columns explicitly and use stable aliases. The mapper relies on column labels (`customer_id`) rather than positional indices, so projection order can change without breaking mapping.

If `created_at` is MySQL `DATETIME`, `LocalDateTime` fits because `DATETIME` carries no timezone. If the column is `TIMESTAMP`, align session timezone and conversion rules; you can read via `Timestamp` and call `toInstant()` if the domain expects an absolute instant. Do not attach a timezone to `DATETIME` if the data represents only a local date-time.

### BeanPropertyRowMapper

Spring includes `BeanPropertyRowMapper` to map column names to JavaBean properties, typically converting `customer_id` to `customerId`:

```java
RowMapper<CustomerBean> mapper =
        new BeanPropertyRowMapper<>(CustomerBean.class);
```

This mapper is convenient for DTOs with a no-arg constructor and setters, but it relies on reflection and naming conventions. It can mask type mismatches or nullability issues on complex domain objects. For critical queries, unsigned types, bitmasks, or custom conversions, an explicit mapper is easier to review and test.

## 5. MySQL Type Mapping Pitfalls

Certain MySQL types should not be read carelessly as Java primitives:

| MySQL Type | Recommended Java Type | RowMapper Guidance |
|---|---|---|
| `DECIMAL(p,s)` | `BigDecimal` | `rs.getBigDecimal("amount")` |
| Signed `BIGINT` | `long`/`Long` | `rs.getLong(...)`; call `wasNull()` if nullable, or `getObject(..., Long.class)`. |
| `BIGINT UNSIGNED` | `BigInteger` when full range is needed | `rs.getBigDecimal(...).toBigIntegerExact()` or `getObject()` with class check. |
| `BIT(1)` / boolean | `Boolean` | `getBoolean()` followed by `wasNull()` if nullable. |
| `BIT(M)` with M > 1 | `byte[]` | `rs.getBytes(...)`, decode bits per application convention. |
| `DATE` | `LocalDate` | `rs.getObject("birth_date", LocalDate.class)`. |
| `DATETIME` | `LocalDateTime` | `rs.getObject("created_at", LocalDateTime.class)`. |
| `TIMESTAMP` | `Instant` or `Timestamp` per domain | Align session timezone; read `Timestamp` and call `toInstant()` when an instant is needed. |

Example mapper handling unsigned, decimal, and nullable boolean:

```java
public record PaymentRow(
        BigInteger paymentId,
        BigDecimal amount,
        Boolean confirmed) {
}

private static final RowMapper<PaymentRow> PAYMENT_ROW_MAPPER = (rs, rowNum) -> {
    BigDecimal rawId = rs.getBigDecimal("payment_id");
    BigInteger paymentId = rawId == null ? null : rawId.toBigIntegerExact();

    boolean confirmedValue = rs.getBoolean("confirmed");
    Boolean confirmed = rs.wasNull() ? null : confirmedValue;

    return new PaymentRow(
            paymentId,
            rs.getBigDecimal("amount"),
            confirmed
    );
};
```

`getLong()`, `getInt()`, and `getBoolean()` return default primitive values when the SQL value is `NULL`. Call `rs.wasNull()` immediately after the primitive getter being checked; any intervening getter overwrites the flag. For nullable columns, you can use `getObject(column, Long.class)` or the corresponding wrapper if the driver supports that target class.

For `BIGINT UNSIGNED`, never call `getLong()` for the full range because values above `Long.MAX_VALUE` cannot be represented. If the application intentionally caps IDs below `Long.MAX_VALUE`, enforce that bound via constraints/data rules and validate on write.

## 6. Mapping One-to-Many JOIN Queries

A join between parent and child returns multiple rows per parent. Using `RowMapper<OrderRow>` would produce a duplicate order object for every row. When aggregating multiple children into one parent, use `ResultSetExtractor` to read the entire result set and group by key.

Example DTOs:

```java
public record OrderLine(long lineId, String productCode, int quantity) {}

public record OrderWithLines(long orderId, String orderNumber, List<OrderLine> lines) {}
```

SQL should use `LEFT JOIN` if orders with zero lines must still be returned:

```sql
SELECT
    o.order_id,
    o.order_number,
    l.line_id,
    l.product_code,
    l.quantity
FROM orders AS o
LEFT JOIN order_lines AS l ON l.order_id = o.order_id
WHERE o.order_id IN (:orderIds)
ORDER BY o.order_id, l.line_id;
```

Extractor:

```java
private static final ResultSetExtractor<List<OrderWithLines>> ORDER_EXTRACTOR = rs -> {
    Map<Long, OrderAccumulator> orders = new LinkedHashMap<>();

    while (rs.next()) {
        long orderId = rs.getLong("order_id");

        OrderAccumulator order = orders.computeIfAbsent(
                orderId,
                id -> new OrderAccumulator(
                        id,
                        getString(rs, "order_number"))
        );

        long lineId = rs.getLong("line_id");
        if (!rs.wasNull()) {
            order.lines.add(new OrderLine(
                    lineId,
                    rs.getString("product_code"),
                    rs.getInt("quantity")
            ));
        }
    }

    return orders.values().stream()
            .map(OrderAccumulator::toResult)
            .toList();
};
```

In the example above, `getString(rs, "order_number")` is a column-reading helper defined as follows:

```java
private static String getString(ResultSet rs, String column) {
    try {
        return rs.getString(column);
    } catch (SQLException ex) {
        throw new DataRetrievalFailureException("Cannot read " + column, ex);
    }
}

private static final class OrderAccumulator {
    final long orderId;
    final String orderNumber;
    final List<OrderLine> lines = new ArrayList<>();

    OrderAccumulator(long orderId, String orderNumber) {
        this.orderId = orderId;
        this.orderNumber = orderNumber;
    }

    OrderWithLines toResult() {
        return new OrderWithLines(orderId, orderNumber, List.copyOf(lines));
    }
}
```

In a production implementation, you can write a mapper helper to avoid catching `SQLException` inside a `computeIfAbsent` lambda, or use an explicit `get`/`put` loop. The core idea is that `ResultSetExtractor` owns the `rs.next()` loop and groups rows by parent key. Use `LinkedHashMap` to preserve parent order as returned by the query; the SQL still needs `ORDER BY` to guarantee deterministic ordering.

## 7. Choosing the Right Callback: RowMapper, ResultSetExtractor, or RowCallbackHandler

| Callback | When to Use | Characteristics |
|---|---|---|
| `RowMapper<T>` | Each independent row becomes one object. | Spring manages the loop; the mapper only reads the current row. |
| `ResultSetExtractor<T>` | Need to see the full result to group, build nested structures, or compute aggregates. | Application iterates `ResultSet` manually. |
| `RowCallbackHandler` | Process each row without holding the entire result in a list. | Suited for streaming/writing rows out to a sink. |

Example `RowCallbackHandler`:

```java
jdbcTemplate.query(
        "SELECT customer_id, email FROM customers ORDER BY customer_id",
        (RowCallbackHandler) rs -> {
            long id = rs.getLong("customer_id");
            String email = rs.getString("email");
            exportCustomer(id, email);
        }
);
```

Using a callback does not automatically enable streaming in every driver. For large datasets, check fetch size, cursor fetching, transaction settings, and Connector/J behavior; otherwise, the driver may buffer all rows in memory.

## 8. Safe Pagination, Filtering, and Sorting

For potentially large lists, paginate in SQL rather than fetching everything and slicing in Java:

```java
String sql = """
    SELECT customer_id, email, status, created_at
    FROM customers
    WHERE status = :status
    ORDER BY created_at DESC, customer_id DESC
    LIMIT :limit OFFSET :offset
    """;

MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("status", status, Types.VARCHAR)
        .addValue("limit", pageSize, Types.INTEGER)
        .addValue("offset", offset, Types.INTEGER);

List<CustomerRow> page = namedJdbc.query(sql, params, CUSTOMER_ROW_MAPPER);
```

`ORDER BY` needs a deterministic tie-breaker column, such as the primary key, so rows sharing the same `created_at` do not shift arbitrarily between pages. Validate `pageSize` and `offset` in the application layer; never allow clients to request unbounded page sizes.

On large tables, high `OFFSET` values force MySQL to scan and discard many rows. Keyset pagination is generally more efficient:

```sql
SELECT customer_id, email, created_at
FROM customers
WHERE status = :status
  AND (created_at, customer_id) < (:lastCreatedAt, :lastCustomerId)
ORDER BY created_at DESC, customer_id DESC
LIMIT :limit;
```

The tuple predicate above illustrates descending order; ensure an appropriate index exists—such as `(status, created_at, customer_id)`—and extract the cursor token from the last row of the previous page. If sort direction or filter columns change, design the keyset condition and index accordingly.

## 9. Batch Updates and Generated Keys

When writing many rows, `batchUpdate()` cuts network round-trips compared to calling `update()` in a loop:

```java
String sql = """
    UPDATE inventory
    SET reserved_quantity = reserved_quantity + :quantity
    WHERE product_id = :productId
    """;

SqlParameterSource[] batch = reservations.stream()
        .map(item -> new MapSqlParameterSource()
                .addValue("quantity", item.quantity(), Types.INTEGER)
                .addValue("productId", item.productId(), Types.BIGINT))
        .toArray(SqlParameterSource[]::new);

int[] results = namedJdbc.batchUpdate(sql, batch);
```

Choose batch size based on workload and packet/driver limits. If a batch must be atomic, run it inside a transaction and define how partial failures are handled. Never assume every JDBC driver returns exact row counts for each command; JDBC may report `SUCCESS_NO_INFO` or `EXECUTE_FAILED` in batch results.

To retrieve auto-increment keys:

```java
String sql = "INSERT INTO customers (email, status) VALUES (?, ?)";
KeyHolder keyHolder = new GeneratedKeyHolder();

jdbcTemplate.update(connection -> {
    PreparedStatement ps = connection.prepareStatement(
            sql,
            Statement.RETURN_GENERATED_KEYS
    );
    ps.setString(1, email);
    ps.setString(2, "ACTIVE");
    return ps;
}, keyHolder);

Number generatedId = keyHolder.getKey();
if (generatedId == null) {
    throw new DataRetrievalFailureException("MySQL did not return a generated key");
}
long customerId = generatedId.longValue();
```

For unsigned keys that may exceed `Long.MAX_VALUE`, do not cast `Number` blindly to `long`; pick an appropriate domain key type and test how the driver returns generated keys. In most applications, auto-increment signed `BIGINT` IDs are kept within the `long` range for Java compatibility.

## 10. Transactions with JdbcTemplate

In Spring Boot, `@Transactional` manages transactions for `JdbcTemplate` calls when the template shares the same `DataSource` with the transaction manager:

```java
@Service
public class TransferService {
    private final JdbcTemplate jdbc;

    public TransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(long fromAccount, long toAccount, BigDecimal amount) {
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("Transfer amount must be positive");
        }

        int debited = jdbc.update("""
            UPDATE accounts
            SET balance = balance - ?
            WHERE account_id = ? AND balance >= ?
            """, amount, fromAccount, amount);

        if (debited != 1) {
            throw new IllegalStateException("Insufficient balance or account missing");
        }

        int credited = jdbc.update("""
            UPDATE accounts
            SET balance = balance + ?
            WHERE account_id = ?
            """, amount, toAccount);

        if (credited != 1) {
            throw new IllegalStateException("Destination account missing");
        }
    }
}
```

If any step throws a runtime exception, Spring rolls back the transaction by default. Checked exceptions do not trigger rollback by default; specify `@Transactional(rollbackFor = ...)` if business rules require it. Both updates must run on the same transaction-bound connection. `JdbcTemplate` uses Spring's connection synchronization mechanism and automatically participates in the active transaction when configured properly.

Do not call `dataSource.getConnection()` and close it manually inside a `@Transactional` method unless you know how to obtain the transaction-bound connection. Use `JdbcTemplate` or `DataSourceUtils` to ensure the same connection is used.

### Combining JdbcTemplate and JPA

An application can use JPA for entity CRUD and `JdbcTemplate` for specialized queries. The two technologies participate in the same transaction only when configured with the same `DataSource` and a compatible transaction manager—typically `JpaTransactionManager` configured for that persistence unit.

If JPA modified an entity without flushing yet, a `JdbcTemplate` query will not see the change because the SQL has not been sent to the database. Call `entityManager.flush()` when JDBC needs to read changes made by JPA within the same transaction. Conversely, if `JdbcTemplate` directly updates a row currently managed in the persistence context, the entity cached in `EntityManager` becomes stale; consider calling `refresh()` or `clear()` appropriately. Avoid writing to the same data from both layers without a clear source of state ownership.

## 11. Reading Large Datasets and Memory Management

`query()` returns a `List<T>`, keeping all result objects in memory. For large reports or exports, consider `RowCallbackHandler`, keyset pagination, or `queryForStream()`.

Example `queryForStream()`:

```java
try (Stream<CustomerRow> stream = jdbcTemplate.queryForStream(
        "SELECT customer_id, email, status, credit_limit FROM customers",
        CUSTOMER_ROW_MAPPER)) {
    stream.forEach(this::writeToExport);
}
```

Always close the stream with try-with-resources because the stream holds open JDBC resources until closed. Never return the stream out of the repository layer for callers to consume after the transaction/connection has closed.

With MySQL Connector/J, cursor-based fetching requires proper configuration, usually including `useCursorFetch=true` and a positive fetch size on the statement. Merely calling `setFetchSize()` does not guarantee every driver streams rows via a cursor. Test against your exact Connector/J version, transaction mode, and pool configuration; monitor memory, connection hold duration, and server impact.

Do not hold one connection open for long durations if an export job runs for minutes on a small pool. Chunk into batches, write to the sink incrementally, and enforce timeouts and cancellation.

## 12. Error Handling and Logging

`JdbcTemplate` translates `SQLException` into `DataAccessException` subclasses such as `DuplicateKeyException`, `DataIntegrityViolationException`, `CannotAcquireLockException`, `PessimisticLockingFailureException`, or `DataAccessResourceFailureException`. Exact exception types depend on SQLState/vendor codes and the configured translator. Catch domain-relevant exceptions where meaningful rather than catching generic `Exception` and swallowing it.

Example handling a unique constraint conflict:

```java
try {
    jdbcTemplate.update(
            "INSERT INTO customers (email, status) VALUES (?, ?)",
            email,
            "ACTIVE"
    );
} catch (DuplicateKeyException ex) {
    throw new CustomerAlreadyExistsException(email, ex);
}
```

Never log passwords, tokens, personal data, or raw sensitive parameter payloads. For SQL errors, record a query identifier, repository method name, SQLState/vendor code, and correlation ID; log sanitized parameter values only when genuinely necessary.

For deadlocks or lock timeouts, retry the transaction only if the operation is safe to re-execute, and retry the entire transaction across a consistent boundary. Never retry a single statement mid-transaction after MySQL has already rolled back the transaction due to a deadlock.

## 13. Testing Repositories with MySQL

Spring Boot provides `@JdbcTest` for slice testing JDBC components, configuring `JdbcTemplate`, and transactional tests. If tests run against H2, MySQL syntax, collations, unsigned types, `BIT(M)`, JSON, SQL modes, and locking behaviors will differ. For repositories relying on MySQL behavior, run integration tests against real MySQL using Testcontainers or a dedicated test database.

Cases to test:

- Queries returning one row, zero rows, and unexpectedly multiple rows.
- Nullable named parameters, empty collections, and large `IN` lists.
- `DECIMAL` with scale, `BIGINT UNSIGNED` boundaries, `BIT(M)`, and nullable booleans.
- One-to-many JOINs without duplicating parents or dropping childless parents.
- Batches where one row violates a constraint.
- Transaction rollback when the second statement fails.
- Deterministic pagination when multiple rows share the same timestamp.
- Dynamic SQL accepting identifiers only from an allowlist.

Unit testing mappers with a mocked `ResultSet` validates small mapping logic, but cannot replace integration tests because Java types and metadata depend on Connector/J.

## 14. Common Pitfalls

| Symptom | Common Cause | Resolution |
|---|---|---|
| `queryForObject()` throws when no row exists | API called expecting exactly one row | Use `query()` and return `Optional`, or handle `EmptyResultDataAccessException`. |
| JOIN results contain duplicate parent objects | Each joined row mapped to a new parent object | Use `ResultSetExtractor` grouped by key, or intentionally return flat DTOs. |
| Nullable column becomes `0`/`false` | Primitive getters cannot distinguish SQL `NULL` | Use wrapper types or call `wasNull()` immediately after the getter. |
| SQL injection in `ORDER BY` | Concatenating user input into identifiers/direction | Use an allowlist for identifiers; bind all data values. |
| `IN` clause errors on empty list | Named parameter collection expands to empty placeholder list | Handle empty collections before running SQL. |
| Overflow reading `BIGINT UNSIGNED` | Using `getLong()` across the full unsigned range | Use `BigInteger`/`BigDecimal` and validate bounds. |
| Export fills the JVM heap | `query()` buffers the full list or driver buffers all rows | Use pagination, callbacks, or verified cursor fetching. |
| JPA update invisible to JDBC query | `EntityManager` has not flushed | Call `flush()` when JPA SQL must be sent before a JDBC query. |
| JDBC update leaves JPA entity stale | Persistence context holds cached entity | Refresh/clear appropriately or avoid mixing writes on the same entity. |
| Transaction fails to roll back as expected | Different `DataSource`/transaction manager or checked exception not covered by rollback rules | Share the same transaction manager and configure `rollbackFor` as needed. |
| Retries create duplicate data | Non-idempotent operation or retrying mid-transaction | Use idempotency keys and retry the full transaction under clear rules. |

## 15. Repository Design Checklist

- [ ] Use Spring-managed `JdbcTemplate`/`NamedParameterJdbcTemplate` via constructor injection.
- [ ] Use bind parameters in SQL for all data values.
- [ ] Select dynamic identifiers exclusively from a server-side allowlist.
- [ ] Use `MapSqlParameterSource` with explicit SQL types when binding `null` or specialized types.
- [ ] Keep `RowMapper` focused on the current row; use `ResultSetExtractor` for grouping.
- [ ] Preserve full domain ranges when mapping `DECIMAL`, unsigned integers, `BIT`, booleans, and date/time types.
- [ ] Never confuse SQL `NULL` with primitive defaults.
- [ ] Enforce deterministic ordering and bounded page sizes in pagination.
- [ ] Bound batch sizes and define clear transaction/error policies.
- [ ] Align `@Transactional` with the right `DataSource`/transaction manager and verify JPA interaction.
- [ ] Prevent large result sets from unexpectedly loading into heap memory.
- [ ] Translate exceptions into appropriate business errors; keep secrets and sensitive data out of logs.
- [ ] Test repositories against real MySQL and your exact Connector/J version when relying on MySQL behavior.

`JdbcTemplate` gives you direct SQL control while preserving Spring's consistent JDBC lifecycle and exception handling. `NamedParameterJdbcTemplate` improves readability for multi-condition queries, while `RowMapper` and `ResultSetExtractor` shape results to match your Java data structures. Combining bind parameters, accurate type mapping, shared-DataSource transactions, and real MySQL integration tests lets JDBC repositories operate cleanly and reliably alongside Spring Data JPA.
