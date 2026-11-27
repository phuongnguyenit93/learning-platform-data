# JdbcTemplate, Named Parameters, and Oracle Data Type Handling

Spring JDBC provides a lighter database access layer than raw JDBC while keeping full SQL control in the application's hands. With Oracle Database, the two most frequently used components are `JdbcTemplate` and `NamedParameterJdbcTemplate`. `JdbcTemplate` handles JDBC resource lifecycles, parameter binding, result iteration, and translating JDBC errors into Spring's exception hierarchy. `NamedParameterJdbcTemplate` adds named parameters such as `:customerId` instead of `?` placeholders, making SQL easier to read and less prone to parameter-order mistakes.

When working with Oracle, the quality of the JDBC layer depends heavily on how data types are mapped. Oracle includes types such as `NUMBER`, `DATE`, `TIMESTAMP`, `TIMESTAMP WITH TIME ZONE`, `VARCHAR2`, `CHAR`, `CLOB`, `BLOB`, `RAW`, and other specialized types. Binding or reading data with the wrong type can cause conversion errors, lost time components, precision errors, NULL bugs, or poor performance.

This document covers configuring Spring JDBC in Spring Boot, writing queries with `JdbcTemplate` and named parameters, mapping results, handling transactions and batches, and practical considerations when working with Oracle data types.

## 1. Role of Spring JDBC

JDBC is Java's standard API for connecting to and interacting with databases. At a low level, a query operation typically requires:

1. Acquiring a `Connection` from a `DataSource`.
2. Creating a `PreparedStatement` or `CallableStatement`.
3. Binding parameters.
4. Executing SQL.
5. Reading the `ResultSet`.
6. Closing the `ResultSet`, statement, and connection on every success and error path.
7. Translating `SQLException` and handling transactions.

Repeating these steps in every repository produces verbose code and risks leaking resources. Spring JDBC encapsulates that boilerplate in template classes while the application provides the SQL, parameters, and mapping logic.

### 1.1. What Does JdbcTemplate Do?

`JdbcTemplate` is the core class of Spring JDBC. It provides common operations:

- `query(...)`: runs SELECT and maps each row.
- `queryForObject(...)`: queries a single value or single row.
- `queryForList(...)`: returns a list of results as maps or simple types.
- `update(...)`: executes INSERT, UPDATE, DELETE, or other DML.
- `batchUpdate(...)`: executes a group of DML statements with multiple parameter sets.
- `execute(...)`: runs callbacks or SQL requiring lower-level control.
- `call(...)`: invokes stored procedures/functions where explicit parameter declarations are needed.

The template manages acquiring and releasing JDBC resources. When a Spring-managed transaction is active, the template participates in the current transaction via `DataSourceUtils`.

### 1.2. What Does NamedParameterJdbcTemplate Do?

JDBC `PreparedStatement` uses positional `?` placeholders:

```sql
SELECT order_id, total_amount
FROM orders
WHERE customer_id = ?
  AND order_status = ?
```

The application must pass values in exact positional order. In long SQL statements, queries with many placeholders, or queries reusing the same value multiple times, counting positions is error-prone.

`NamedParameterJdbcTemplate` lets you assign names:

```sql
SELECT order_id, total_amount
FROM orders
WHERE customer_id = :customerId
  AND order_status = :status
```

Values are passed by matching names. Spring translates named parameters into JDBC placeholders at execution time. These are still bind variables, not SQL string concatenation.

### 1.3. When to Use JDBC Instead of JPA?

Spring JDBC fits well when:

- SQL requires precise control, especially for complex Oracle queries.
- The application uses analytic functions, CTEs, hints, or Oracle-specific SQL features.
- Reporting queries, bulk DML, or large-volume batch processing are needed.
- You want to avoid ORM overhead for specific data-access paths.
- You need direct interaction with stored procedures or specialized data types.

JPA fits when the object model and entity relationships are central, whereas JDBC fits when SQL and database execution plans are central. A Spring Boot application can use JPA for routine CRUD and Spring JDBC for reporting or specialized queries; align the transaction manager and `DataSource` when combining both approaches.

## 2. Configuring Spring Boot with Oracle JDBC

### 2.1. Dependencies

With Maven, Spring JDBC dependencies are usually provided via the starter:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
</dependency>

<dependency>
    <groupId>com.oracle.database.jdbc</groupId>
    <artifactId>ojdbc11</artifactId>
    <scope>runtime</scope>
</dependency>
```

Choose the JDBC artifact matching your Java runtime and Oracle Database version. For instance, `ojdbc11` targets the Java versions supported by that driver; do not pick the latest driver arbitrarily without checking the compatibility matrix across database, JDK, and Spring Boot. In real projects, manage versions via Spring Boot dependency management or an internal BOM to avoid conflicts.

If the project already uses `spring-boot-starter-data-jpa`, the JPA starter pulls in the needed Spring JDBC infrastructure. However, declaring the JDBC starter explicitly can make the intent to use `JdbcTemplate` clearer.

### 2.2. Configuring the DataSource

Example `application.yml`:

```yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@//db-host.example.com:1521/SALES_PDB
    username: app_user
    password: ${DB_PASSWORD}
    driver-class-name: oracle.jdbc.OracleDriver
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 30000
      validation-timeout: 5000
```

The `url` above uses a service name in Easy Connect format. With RAC, applications normally connect via a DBA-published SCAN/service name rather than hardcoding a specific instance. Passwords should come from a secret manager or environment variables, never committed to Git.

Spring Boot typically auto-configures `DataSource` and `JdbcTemplate` when the JDBC starter and an appropriate driver are present. HikariCP is the common default connection pool in Spring Boot. Do not guess a huge `maximum-pool-size`; total connections across all application instances must stay within database limits and workload capacity.

### 2.3. Injecting JdbcTemplate

When auto-configuration is active, you can inject it directly:

```java
@Repository
public class OrderRepository {

    private final JdbcTemplate jdbcTemplate;

    public OrderRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }
}
```

Spring Boot can also create a `NamedParameterJdbcTemplate` backed by `JdbcTemplate`/`DataSource`:

```java
@Repository
public class OrderSearchRepository {

    private final NamedParameterJdbcTemplate namedJdbc;

    public OrderSearchRepository(NamedParameterJdbcTemplate namedJdbc) {
        this.namedJdbc = namedJdbc;
    }
}
```

If the application has multiple `DataSource` beans, explicitly declare which bean is `@Primary`, which `JdbcTemplate` binds to which DataSource, and which transaction manager governs each database. Never inject a default template and assume it points to the right database.

### 2.4. Explicit Configuration with Multiple DataSources

Example configuring a dedicated Oracle DataSource:

```java
@Configuration
public class OracleJdbcConfig {

    @Bean
    @ConfigurationProperties("app.oracle.datasource")
    public DataSource oracleDataSource() {
        return DataSourceBuilder.create().build();
    }

    @Bean
    public JdbcTemplate oracleJdbcTemplate(
            @Qualifier("oracleDataSource") DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    public NamedParameterJdbcTemplate oracleNamedJdbcTemplate(
            @Qualifier("oracleDataSource") DataSource dataSource) {
        return new NamedParameterJdbcTemplate(dataSource);
    }
}
```

In production setups, configure the pool implementation and pool properties explicitly instead of relying solely on default `DataSourceBuilder`. If the Oracle DataSource has its own transactions, declare an appropriate `DataSourceTransactionManager` or `JdbcTransactionManager` and apply the right bean qualifiers in repositories/services.

## 3. Basic Queries with JdbcTemplate

### 3.1. Query Returning a List of Objects

`RowMapper<T>` maps a single `ResultSet` row to a Java object. DTO example:

```java
public record OrderSummary(
        long orderId,
        long customerId,
        BigDecimal totalAmount,
        String status) {
}
```

Repository:

```java
@Repository
public class OrderRepository {

    private final JdbcTemplate jdbcTemplate;

    public OrderRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<OrderSummary> findPaidOrders(long customerId) {
        String sql = """
            SELECT order_id,
                   customer_id,
                   total_amount,
                   order_status
            FROM app.orders
            WHERE customer_id = ?
              AND order_status = 'PAID'
            ORDER BY order_date DESC, order_id DESC
            """;

        return jdbcTemplate.query(sql, (rs, rowNum) ->
                new OrderSummary(
                        rs.getLong("ORDER_ID"),
                        rs.getLong("CUSTOMER_ID"),
                        rs.getBigDecimal("TOTAL_AMOUNT"),
                        rs.getString("ORDER_STATUS")
                ), customerId);
    }
}
```

`JdbcTemplate` accepts SQL, a `RowMapper`, and bind parameters. The template prepares the statement, binds values, iterates over the `ResultSet`, and closes resources.

If a numeric column can be NULL, `ResultSet.getLong()` returns 0 for SQL NULL. Call `rs.wasNull()` immediately after reading the column, or use `getObject(..., Long.class)` where supported by the driver, to distinguish NULL from 0. For DTOs with nullable fields, never silently turn NULL into zero.

### 3.2. Querying a Single Value

Example counting orders:

```java
public long countOrders(long customerId) {
    String sql = """
        SELECT COUNT(*)
        FROM app.orders
        WHERE customer_id = ?
        """;

    Long count = jdbcTemplate.queryForObject(sql, Long.class, customerId);
    return count == null ? 0L : count;
}
```

`COUNT(*)` returns one row. `queryForObject` is suitable when SQL is expected to return exactly one row. If the query returns zero rows or multiple rows where one result is expected, Spring throws the corresponding exception. Aggregates like `COUNT` normally always return one row, whereas other aggregates can return NULL when given empty input.

### 3.3. Querying a Single Row into an Object

```java
public OrderSummary findById(long orderId) {
    String sql = """
        SELECT order_id,
               customer_id,
               total_amount,
               order_status
        FROM app.orders
        WHERE order_id = ?
        """;

    return jdbcTemplate.queryForObject(sql, (rs, rowNum) ->
            new OrderSummary(
                    rs.getLong("ORDER_ID"),
                    rs.getLong("CUSTOMER_ID"),
                    rs.getBigDecimal("TOTAL_AMOUNT"),
                    rs.getString("ORDER_STATUS")
            ), orderId);
}
```

If `ORDER_ID` does not exist, `queryForObject` throws `EmptyResultDataAccessException`. To represent not-found with `Optional`, catch that specific exception or call `query(...)` and take the first element if present. Never catch broad `DataAccessException` and return `null`, as that can swallow connectivity or SQL errors.

### 3.4. Insert, Update, and Delete

`update(...)` returns the number of affected rows:

```java
public int updateOrderStatus(long orderId, String status) {
    String sql = """
        UPDATE app.orders
        SET order_status = ?,
            updated_at = SYSTIMESTAMP
        WHERE order_id = ?
        """;

    return jdbcTemplate.update(sql, status, orderId);
}
```

For `INSERT`, use `update` if you do not need a generated key. If you need a sequence or database-generated key, use `GeneratedKeyHolder` with proper configuration, or query a sequence/`RETURNING` depending on Oracle JDBC and version support. With Oracle, sequence `NEXTVAL` is common:

```java
public long nextOrderId() {
    Long value = jdbcTemplate.queryForObject(
            "SELECT app.order_id_seq.NEXTVAL FROM dual",
            Long.class);
    return value;
}
```

Sequences can have gaps and do not guarantee commit order. Do not use sequences as gap-free sequential counters.

## 4. NamedParameterJdbcTemplate

### 4.1. Using MapSqlParameterSource

Example query with named parameters:

```java
public List<OrderSummary> searchOrders(
        long customerId,
        String status,
        LocalDateTime fromTime) {

    String sql = """
        SELECT order_id,
               customer_id,
               total_amount,
               order_status
        FROM app.orders
        WHERE customer_id = :customerId
          AND order_status = :status
          AND order_date >= :fromTime
        ORDER BY order_date DESC, order_id DESC
        """;

    MapSqlParameterSource params = new MapSqlParameterSource()
            .addValue("customerId", customerId, Types.NUMERIC)
            .addValue("status", status, Types.VARCHAR)
            .addValue("fromTime", Timestamp.valueOf(fromTime), Types.TIMESTAMP);

    return namedJdbc.query(sql, params, (rs, rowNum) ->
            new OrderSummary(
                    rs.getLong("ORDER_ID"),
                    rs.getLong("CUSTOMER_ID"),
                    rs.getBigDecimal("TOTAL_AMOUNT"),
                    rs.getString("ORDER_STATUS")
            ));
}
```

`MapSqlParameterSource` lets you specify parameter name, value, and JDBC type. Declaring the type is especially helpful for NULLs or Oracle types that the driver cannot infer reliably from the Java value.

### 4.2. Using Map.of for Simple Parameters

```java
String sql = """
    SELECT order_id, order_status
    FROM app.orders
    WHERE customer_id = :customerId
    """;

List<Map<String, Object>> rows = namedJdbc.queryForList(
        sql,
        Map.of("customerId", 501L));
```

`Map.of` does not allow `null` keys or values. If a parameter can be NULL, use `MapSqlParameterSource` or an appropriate mutable `Map`.

### 4.3. Reusing the Same Named Parameter

```sql
SELECT order_id,
       customer_id
FROM app.orders
WHERE customer_id = :customerId
   OR referred_by_customer_id = :customerId
```

A named parameter can appear multiple times; the application only supplies one `customerId` value. Spring expands the parameter name into the corresponding JDBC placeholders.

### 4.4. Named Parameters with IN Lists

A notable benefit of `NamedParameterJdbcTemplate` is collection support:

```java
String sql = """
    SELECT order_id,
           customer_id,
           order_status
    FROM app.orders
    WHERE order_id IN (:orderIds)
    """;

MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("orderIds", List.of(1001L, 1002L, 1003L));

List<OrderSummary> orders = namedJdbc.query(sql, params, orderRowMapper);
```

Spring expands the collection into the matching number of placeholders. There is no need to concatenate IDs into SQL strings.

However, handle empty lists before executing. `IN ()` is invalid syntax in Oracle. Depending on semantics, return an empty list immediately in Java or substitute an always-false predicate. Example:

```java
public List<OrderSummary> findByIds(Collection<Long> ids) {
    if (ids == null || ids.isEmpty()) {
        return List.of();
    }

    String sql = """
        SELECT order_id, customer_id, total_amount, order_status
        FROM app.orders
        WHERE order_id IN (:ids)
        """;

    return namedJdbc.query(
            sql,
            new MapSqlParameterSource("ids", ids),
            orderRowMapper);
}
```

Oracle enforces a limit on expressions inside an `IN` list in many versions (commonly 1,000 expressions prior to Oracle Database 23ai; verify for your exact version). For large ID sets, batch the queries, load IDs into a staging/global temporary table, or use an appropriate collection/table type instead of generating a massive `IN` list.

### 4.5. Named Parameters Cannot Replace Identifiers

Bind parameters are strictly for data values. You cannot bind table names, column names, `ASC`/`DESC` keywords, or SQL fragments:

```sql
-- Does not work like value binding:
SELECT * FROM :tableName
```

If a table or column name must vary based on user selection, use a Java allowlist:

```java
private static final Map<String, String> SORT_COLUMNS = Map.of(
        "date", "ORDER_DATE",
        "amount", "TOTAL_AMOUNT",
        "id", "ORDER_ID"
);

String sortColumn = SORT_COLUMNS.get(requestedSort);
if (sortColumn == null) {
    throw new IllegalArgumentException("Unsupported sort field");
}

String direction = descending ? "DESC" : "ASC";
String sql = "SELECT order_id, order_date, total_amount " +
        "FROM app.orders ORDER BY " + sortColumn + " " + direction;
```

Only allowlisted identifiers and tokens may be interpolated into SQL. Data values such as customer ID, status, or dates must still be bound. Never concatenate arbitrary HTTP request input into SQL.

## 5. RowMapper, ResultSetExtractor, and Result Mapping

### 5.1. RowMapper

`RowMapper<T>` maps a single row to a single object. Spring invokes the mapper per row and manages `ResultSet` iteration.

```java
private final RowMapper<OrderSummary> orderRowMapper = (rs, rowNum) ->
        new OrderSummary(
                rs.getLong("ORDER_ID"),
                rs.getLong("CUSTOMER_ID"),
                rs.getBigDecimal("TOTAL_AMOUNT"),
                rs.getString("ORDER_STATUS")
        );
```

Reuse mappers when the same projection appears across multiple queries. Never let a mapper issue extra queries per row, which creates N+1 queries. When related data is needed, join or batch-load it.

### 5.2. BeanPropertyRowMapper

Spring provides `BeanPropertyRowMapper` to map column names to Java properties using standard naming conventions:

```java
public class CustomerRow {
    private Long customerId;
    private String customerName;
    private BigDecimal creditLimit;

    // getters/setters
}
```

```java
List<CustomerRow> customers = jdbcTemplate.query(
        "SELECT customer_id, customer_name, credit_limit FROM app.customers",
        new BeanPropertyRowMapper<>(CustomerRow.class));
```

`CUSTOMER_ID` typically maps to `customerId`. However, automatic mapping may not suit complex column names, nullable primitives, custom conversions, or immutable DTOs. For critical queries, an explicit `RowMapper` is usually easier to control.

### 5.3. ResultSetExtractor

`ResultSetExtractor<T>` receives the entire `ResultSet` and controls how results are aggregated. It is useful when a query returns repeated parent rows across a parent-child join and you want to assemble an object graph in one pass.

Example of one customer with multiple orders:

```java
Map<Long, CustomerWithOrders> result = jdbcTemplate.query(sql, rs -> {
    Map<Long, CustomerWithOrders> customers = new LinkedHashMap<>();

    while (rs.next()) {
        long customerId = rs.getLong("CUSTOMER_ID");
        CustomerWithOrders customer = customers.computeIfAbsent(
                customerId,
                id -> new CustomerWithOrders(
                        id,
                        rsString(rs, "CUSTOMER_NAME")));

        long orderId = rs.getLong("ORDER_ID");
        if (!rs.wasNull()) {
            customer.addOrder(new OrderItem(
                    orderId,
                    rs.getBigDecimal("TOTAL_AMOUNT")));
        }
    }

    return customers;
});
```

This snippet illustrates the concept; in production code, avoid reading `ResultSet` inside a `computeIfAbsent` lambda if variable capture hurts readability or complicates checked exception handling. Read the customer name beforehand, check the map, and construct the object explicitly.

### 5.4. Column Aliases for Stable Mapping

For expressions or complex column names, use explicit aliases:

```sql
SELECT o.order_id AS order_id,
       o.total_amount * :taxRate AS amount_with_tax
FROM app.orders o
```

Then read by alias:

```java
rs.getBigDecimal("AMOUNT_WITH_TAX");
```

Oracle normally returns unquoted aliases as uppercase column labels. Avoid mixed-case quoted aliases unless necessary, as quoted labels become case-sensitive.

## 6. Mapping Oracle NUMBER to Java

`NUMBER` is Oracle's primary numeric type, supporting precision and scale. In Java, `BigDecimal` is generally the safest choice for monetary data or values requiring exact decimal precision.

| Oracle | Common Java type | Notes |
|---|---|---|
| `NUMBER(p, s)` | `BigDecimal` | Preserves precision/scale; suitable for money |
| `NUMBER(10,0)` | `Long` or `BigDecimal` | Only use `Long` if value range definitely fits |
| `NUMBER(1)` | `Integer`, `Short`, or boolean convention | Do not automatically treat every NUMBER(1) as boolean |
| `BINARY_FLOAT` | `Float` | Binary floating point |
| `BINARY_DOUBLE` | `Double` | Binary floating point |

### 6.1. Use BigDecimal for Money

```java
BigDecimal amount = rs.getBigDecimal("TOTAL_AMOUNT");
```

Do not use `double` for money if business logic requires decimal accuracy. `double` uses binary floating point, so many decimal fractions cannot be represented exactly.

When binding:

```java
jdbcTemplate.update(
        "UPDATE app.orders SET total_amount = ? WHERE order_id = ?",
        new BigDecimal("1250.50"),
        1001L);
```

Construct `BigDecimal` from decimal strings to avoid precision artifacts introduced by `double`:

```java
new BigDecimal("0.10");
```

Avoid:

```java
new BigDecimal(0.10);
```

### 6.2. Precision and Scale

For `NUMBER(12,2)`, total precision is 12 digits and scale is 2 digits after the decimal point. The application should validate values before binding to prevent exceeding precision or supplying an unexpected scale.

```java
BigDecimal normalized = amount.setScale(2, RoundingMode.HALF_UP);
```

Choose the rounding mode per business rules. Do not let the database silently round if the application needs explicit control over rounding policy.

### 6.3. Nullable NUMBER

`getBigDecimal()` returns `null` for SQL NULL, fitting nullable columns naturally. With primitive numeric getters like `getLong()` or `getInt()`, check `wasNull()`:

```java
long value = rs.getLong("OPTIONAL_COUNT");
Long optionalCount = rs.wasNull() ? null : value;
```

`wasNull()` must be called immediately after the corresponding getter because it reflects the most recently read column.

## 7. Mapping DATE, TIMESTAMP, and Time Zones

Oracle has a notorious pitfall: Oracle's `DATE` type stores both date and time down to seconds, unlike `java.sql.Date` which represents date-only under JDBC semantics. If an application maps Oracle `DATE` to `LocalDate`, hours, minutes, and seconds can be lost.

### 7.1. Oracle DATE

Oracle `DATE` stores year, month, day, hour, minute, and second; it does not store fractional seconds or time zones.

Common Java mappings:

- `LocalDateTime` when both date and time must be preserved.
- `java.sql.Timestamp` as the intermediate JDBC type.
- `LocalDate` only when the column is guaranteed by convention to represent midnight or the application intentionally discards time.

Reading Oracle DATE:

```java
LocalDateTime orderTime = rs.getTimestamp("ORDER_DATE").toLocalDateTime();
```

Binding:

```java
Timestamp timestamp = Timestamp.valueOf(orderTime);
jdbcTemplate.update(
        "INSERT INTO app.orders(order_id, order_date) VALUES (?, ?)",
        orderId,
        timestamp);
```

With JDBC drivers supporting JDBC 4.2 and corresponding types, you can use `getObject`/`setObject` with `LocalDateTime`, though verify behavior on the exact Oracle JDBC version deployed.

### 7.2. Oracle TIMESTAMP

`TIMESTAMP(p)` stores date, time, and fractional seconds with precision `p` (up to Oracle's limits). Java `LocalDateTime` fits when the column does not store a time zone.

```java
LocalDateTime createdAt = rs.getTimestamp("CREATED_AT").toLocalDateTime();
```

If using `Timestamp`, remember `Timestamp` carries no time zone. Do not attach an arbitrary time zone if the schema does not define time zone semantics.

### 7.3. TIMESTAMP WITH TIME ZONE

`TIMESTAMP WITH TIME ZONE` stores an instant along with time zone/offset metadata per Oracle semantics. Java `OffsetDateTime` is typically a better representation than `LocalDateTime` when offset preservation is needed.

With Oracle JDBC supporting JDBC 4.2:

```java
OffsetDateTime eventTime = rs.getObject("EVENT_TIME", OffsetDateTime.class);
```

Binding:

```java
namedJdbc.update(
        "INSERT INTO app.events(event_id, event_time) " +
        "VALUES (:eventId, :eventTime)",
        new MapSqlParameterSource()
                .addValue("eventId", eventId)
                .addValue("eventTime", eventTime));
```

Exact mapping behavior also depends on the Oracle JDBC driver version and actual column type. Write integration tests against a production-like database/driver, especially when preserving region IDs such as `Europe/Paris` rather than just fixed offsets like `+01:00`.

### 7.4. TIMESTAMP WITH LOCAL TIME ZONE

`TIMESTAMP WITH LOCAL TIME ZONE` is normalized to the database time zone on storage and displayed in the session time zone on read. It does not preserve the original client time zone the way `TIMESTAMP WITH TIME ZONE` does.

When mapping to Java, verify the session time zone and application conventions. It can be read as `Timestamp`/`LocalDateTime` in the session time zone, but if business logic needs the user's original time zone, store the time zone/region separately or choose the appropriate data type.

### 7.5. Avoid Implicit Conversions and Session-Dependent NLS

Never pass dates/times as strings dependent on `NLS_DATE_FORMAT`:

```java
// Avoid: result depends on session/database format.
jdbcTemplate.query(sql, rowMapper, "14/11/2026");
```

Bind `Timestamp`, `LocalDateTime`, or `java.sql.Date` appropriately instead of letting Oracle parse strings. If string parsing in SQL is unavoidable, use an explicit format mask:

```sql
TO_DATE(:orderDateText, 'YYYY-MM-DD')
```

Even better, parse into a Java temporal type first and bind the corresponding JDBC type.

## 8. VARCHAR2, CHAR, NVARCHAR2, and Unicode Strings

### 8.1. VARCHAR2

`VARCHAR2` stores variable-length strings. In Java, use `String`:

```java
String customerName = rs.getString("CUSTOMER_NAME");
```

Bind with `String` and `Types.VARCHAR` when an explicit type is needed:

```java
params.addValue("customerName", customerName, Types.VARCHAR);
```

Maximum `VARCHAR2` length depends on `MAX_STRING_SIZE`, byte/char semantics, and database version. Do not assume a single universal limit across all databases.

### 8.2. CHAR Padding

`CHAR(n)` is fixed-length and may be space-padded. When read via `getString`, the application may receive trailing spaces depending on driver/mapping. If the column holds fixed-width status codes, consider `trim()` at the mapping boundary or normalizing values by contract.

Do not trim every string blindly. Trailing whitespace can be meaningful in free-form text; trim only columns with an explicit convention.

### 8.3. NVARCHAR2 and National Character Set

`NVARCHAR2` uses Oracle's national character set. Java `String` represents Unicode, but the right JDBC type and driver mapping must be selected when binding. Use `Types.NVARCHAR` or `setNString` on `PreparedStatement` when needed.

Example with `SqlParameterValue`:

```java
MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("displayName",
                new SqlParameterValue(Types.NVARCHAR, displayName));
```

Most modern applications use a Unicode database character set such as AL32UTF8 for `VARCHAR2`; use `NCHAR`/`NVARCHAR2` only when the schema deliberately requires it. Check database and column character sets to avoid conversions or replacement characters.

### 8.4. Empty Strings and NULL

In Oracle SQL, an empty string `''` for standard character types is treated as `NULL`. This differs from databases that treat empty strings as distinct non-null values.

Therefore:

- Binding Java `""` into `VARCHAR2` may be stored/treated as NULL.
- `IS NULL` is the Oracle-semantic check for an absent string value.
- Never use `= ''` to search for empty strings in Oracle.
- If business logic must distinguish "not provided" from "intentionally blank", model it explicitly, such as via a status flag or an agreed sentinel value.

## 9. CLOB, NCLOB, BLOB, and Large Data

### 9.1. CLOB and NCLOB

`CLOB` stores large character data; `NCLOB` stores large character data in the national character set. Java can read small payloads via `getString()`, while large LOBs should be streamed to avoid loading everything onto the heap.

Example streaming a CLOB read:

```java
String sql = "SELECT document_body FROM app.documents WHERE document_id = ?";

String document = jdbcTemplate.queryForObject(sql, (rs, rowNum) -> {
    try (Reader reader = rs.getCharacterStream("DOCUMENT_BODY")) {
        if (reader == null) {
            return null;
        }
        StringBuilder content = new StringBuilder();
        char[] buffer = new char[8192];
        int count;
        while ((count = reader.read(buffer)) != -1) {
            content.append(buffer, 0, count);
        }
        return content.toString();
    }
}, documentId);
```

This example still materializes the full content into a final `String`; the benefit is controlled reading. For very large documents, stream directly to a file or output consumer rather than building a large `String`.

### 9.2. BLOB

`BLOB` stores binary data. Java can use `byte[]` for small payloads or `InputStream` for large ones.

```java
byte[] payload = rs.getBytes("FILE_CONTENT");
```

For large files, `getBinaryStream()` enables chunked processing. Note that the `ResultSet`, statement, and connection must remain open while the stream is being read. Never return a `ResultSet`-backed `InputStream` out of a `JdbcTemplate` callback and let the template close the connection before the caller finishes reading.

If streaming to the web layer, structure the callback/streaming response so the transaction and connection stay valid throughout reading while bounding connection hold time. Another option is copying the LOB to a file/temp storage inside the callback and returning an independent file stream.

### 9.3. Binding LOBs

For small CLOBs, `String` is usually enough. For large payloads, use `SqlLobValue` and `LobHandler` in a `PreparedStatementCreator`/`SqlParameterSource` per the corresponding Spring API. For BLOBs, pass an `InputStream` and length where required by the API.

Conceptual example using `PreparedStatement` directly in a callback:

```java
jdbcTemplate.update(connection -> {
    PreparedStatement ps = connection.prepareStatement(
            "INSERT INTO app.documents(document_id, document_body) VALUES (?, ?)");
    ps.setLong(1, documentId);
    ps.setCharacterStream(2, new StringReader(documentText), documentText.length());
    return ps;
});
```

The template manages the statement/connection. For application-created streams, ensure streams are closed per application ownership and aligned with how the driver consumes data.

## 10. RAW, UUID, and Binary Types

Oracle `RAW(n)` stores raw bytes. JDBC typically maps it to `byte[]`:

```java
byte[] token = rs.getBytes("TOKEN_RAW");
```

Binding:

```java
jdbcTemplate.update(
        "INSERT INTO app.api_tokens(token_id, token_raw) VALUES (?, ?)",
        tokenId,
        token);
```

If storing UUIDs, standardize the encoding. Storing UUIDs as `RAW(16)` is more compact than 36-character strings, but Java must convert consistently in both directions between `UUID` and 16 bytes. Never call `UUID.toString()` and parse it as if it were the raw byte representation.

Conversion helper:

```java
public static byte[] uuidToBytes(UUID uuid) {
    ByteBuffer buffer = ByteBuffer.allocate(16);
    buffer.putLong(uuid.getMostSignificantBits());
    buffer.putLong(uuid.getLeastSignificantBits());
    return buffer.array();
}

public static UUID bytesToUuid(byte[] bytes) {
    if (bytes == null || bytes.length != 16) {
        throw new IllegalArgumentException("UUID RAW value must contain 16 bytes");
    }
    ByteBuffer buffer = ByteBuffer.wrap(bytes);
    return new UUID(buffer.getLong(), buffer.getLong());
}
```

If the database already uses a different byte-order convention, follow that convention rather than applying sample functions blindly.

## 11. Booleans and Oracle-Specific Types

### 11.1. Booleans in Oracle SQL Depend on Version

In Oracle Database releases prior to table-column SQL `BOOLEAN` support (such as many 19c/21c systems), table columns cannot be declared as SQL `BOOLEAN` like in Java. Applications typically adopt conventions:

- `NUMBER(1)` with `0`/`1`.
- `CHAR(1)` with `Y`/`N`.
- An explicit status code if there are more than two states.

Example `NUMBER(1)` mapping:

```java
Boolean active = rs.getObject("IS_ACTIVE") == null
        ? null
        : rs.getInt("IS_ACTIVE") == 1;
```

When binding, convert explicitly:

```java
Integer activeValue = active == null ? null : (active ? 1 : 0);
```

Oracle Database 23ai/23c adds the SQL `BOOLEAN` type for SQL tables/columns. JDBC mapping support depends on driver and version; verify your specific driver before using `Boolean` directly against SQL BOOLEAN columns. PL/SQL `BOOLEAN` and SQL `BOOLEAN` are distinct contexts depending on release.

### 11.2. ROWID and UROWID

`ROWID` identifies a row's physical location in the database. JDBC provides `java.sql.RowId` and the Oracle driver provides specific support. Never use ROWID as a durable business key because row movement, table reorganization, or structural changes can alter physical locations. Use primary keys for business references.

### 11.3. XMLTYPE, JSON, and Object Types

Oracle offers types/capabilities such as `XMLTYPE`, JSON, and user-defined object types. JDBC mapping depends on the Oracle JDBC driver and specific APIs. For JSON, applications may store data in `CLOB`, `BLOB`, or native JSON depending on database version. If querying JSON in SQL, check version capabilities and limits; do not assume every driver maps native JSON directly to `String` without conversion.

For Oracle object or collection types, `Struct`, `Array`, or Oracle-specific JDBC classes may be needed. Isolate those mappings inside dedicated repositories/adapters so service layers do not depend on driver-specific APIs.

## 12. Binding NULL and Specifying JDBC Types

NULL is error-prone because Java `null` carries no SQL type metadata. For `NUMBER`, `DATE`, `TIMESTAMP`, `CLOB`, or `NVARCHAR2` columns, the driver may require an explicit JDBC type.

### 12.1. Named Parameters with Explicit Types

```java
MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("customerId", customerId, Types.NUMERIC)
        .addValue("comment", comment, Types.VARCHAR)
        .addValue("cancelledAt", cancelledAt, Types.TIMESTAMP);
```

Even if `comment` or `cancelledAt` is null, Spring knows which JDBC type to bind.

### 12.2. SqlParameterValue

With `JdbcTemplate`, wrap the value and type:

```java
jdbcTemplate.update(
        "UPDATE app.orders SET cancelled_at = ? WHERE order_id = ?",
        new SqlParameterValue(Types.TIMESTAMP, cancelledAt),
        orderId);
```

### 12.3. setNull in PreparedStatement

When direct JDBC control is needed:

```java
jdbcTemplate.update(connection -> {
    PreparedStatement ps = connection.prepareStatement(
            "UPDATE app.orders SET cancelled_at = ? WHERE order_id = ?");
    if (cancelledAt == null) {
        ps.setNull(1, Types.TIMESTAMP);
    } else {
        ps.setTimestamp(1, Timestamp.valueOf(cancelledAt));
    }
    ps.setLong(2, orderId);
    return ps;
});
```

Never use the string `'NULL'` to represent SQL NULL. `'NULL'` is four literal characters; SQL NULL is an absent/unknown value.

## 13. Oracle REF CURSOR and Stored Procedures

Oracle stored procedures can return result sets via `SYS_REFCURSOR`. Spring JDBC supports calling procedures through `SimpleJdbcCall` or `CallableStatement` depending on needs.

Procedure example:

```sql
CREATE OR REPLACE PROCEDURE app.get_orders_by_customer (
    p_customer_id IN NUMBER,
    p_result      OUT SYS_REFCURSOR
)
AS
BEGIN
    OPEN p_result FOR
        SELECT order_id,
               order_date,
               total_amount
        FROM app.orders
        WHERE customer_id = p_customer_id;
END;
/
```

Example using `SimpleJdbcCall`:

```java
SimpleJdbcCall getOrdersCall = new SimpleJdbcCall(jdbcTemplate)
        .withSchemaName("APP")
        .withProcedureName("GET_ORDERS_BY_CUSTOMER")
        .declareParameters(
                new SqlParameter("P_CUSTOMER_ID", Types.NUMERIC),
                new SqlOutParameter(
                        "P_RESULT",
                        OracleTypes.CURSOR,
                        orderRowMapper));

Map<String, Object> out = getOrdersCall.execute(
        new MapSqlParameterSource("P_CUSTOMER_ID", customerId));

@SuppressWarnings("unchecked")
List<OrderSummary> orders = (List<OrderSummary>) out.get("P_RESULT");
```

`OracleTypes.CURSOR` comes from the Oracle JDBC driver. Import it from the package matching your driver version. You may need to configure metadata lookup or declare parameters explicitly to avoid name/metadata differences across releases.

For complex procedures/functions, test parameter names, directions, types, schema names, and cursor mappings. Do not rely on positional parameter order when the API allows explicit named declarations.

## 14. Batch Updates with JdbcTemplate

When writing many rows, calling `update` inside a Java loop causes many network round trips. `batchUpdate` groups multiple parameter sets into JDBC batches.

```java
public int[][] insertOrders(List<OrderSummary> orders) {
    String sql = """
        INSERT INTO app.orders (
            order_id,
            customer_id,
            total_amount,
            order_status
        ) VALUES (?, ?, ?, ?)
        """;

    return jdbcTemplate.batchUpdate(sql, orders, 500,
            (ps, order) -> {
                ps.setLong(1, order.orderId());
                ps.setLong(2, order.customerId());
                ps.setBigDecimal(3, order.totalAmount());
                ps.setString(4, order.status());
            });
}
```

Batch size `500` is an example only. Choose it based on row size, driver, memory, redo/undo generation, transaction duration, and application limits. Batching does not automatically commit each batch; transaction boundaries remain governed by the transaction manager or connection.

### 14.1. Batching with Named Parameters

```java
SqlParameterSource[] batch = orders.stream()
        .map(order -> new MapSqlParameterSource()
                .addValue("orderId", order.orderId(), Types.NUMERIC)
                .addValue("customerId", order.customerId(), Types.NUMERIC)
                .addValue("amount", order.totalAmount(), Types.NUMERIC)
                .addValue("status", order.status(), Types.VARCHAR))
        .toArray(SqlParameterSource[]::new);

int[] counts = namedJdbc.batchUpdate("""
        INSERT INTO app.orders (
            order_id, customer_id, total_amount, order_status
        ) VALUES (
            :orderId, :customerId, :amount, :status
        )
        """, batch);
```

For very large volumes, consider chunked batch commits if business semantics allow. If an entire import must be atomic, holding one transaction for the whole batch generates heavy undo and long transactions; evaluate consistency requirements before splitting commits.

### 14.2. Generated Keys and Sequences in Batches

With Oracle, the simplest approach is generating IDs from a sequence or letting the database populate an identity column depending on version. If you need generated keys back for every row in a batch, verify Oracle JDBC driver and Spring version support. Do not assume `GeneratedKeyHolder` behaves identically across all databases and drivers.

## 15. Transactions with Spring JDBC

`JdbcTemplate` joins Spring-managed transactions whenever it shares the same `DataSource` as the transaction manager.

### 15.1. Using @Transactional

```java
@Service
public class OrderService {

    private final JdbcTemplate jdbcTemplate;

    public OrderService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public void cancelOrder(long orderId) {
        int updated = jdbcTemplate.update("""
            UPDATE app.orders
            SET order_status = 'CANCELLED'
            WHERE order_id = ?
            """, orderId);

        if (updated != 1) {
            throw new IllegalStateException("Order was not found or not unique");
        }

        jdbcTemplate.update("""
            INSERT INTO app.order_audit(order_id, action, created_at)
            VALUES (?, 'CANCEL', SYSTIMESTAMP)
            """, orderId);
    }
}
```

If the audit insert fails and the exception triggers transaction rollback per policy, the order status update rolls back as well. By default, Spring rolls back on unchecked exceptions and `Error`; checked exceptions do not trigger automatic rollback unless configured via `rollbackFor` or another policy.

### 15.2. Do Not Manually Commit Inside Repositories

Never call `connection.commit()` inside a repository while Spring manages transactions. Doing so breaks transaction boundaries and prevents other operations from rolling back as expected.

Let the transaction manager handle commits and rollbacks. Repositories should only execute SQL and throw exceptions on failure.

### 15.3. Multiple DataSources

If a service uses two databases, `@Transactional` by default manages only one transaction manager. Two databases do not automatically form a distributed transaction just because they are called in the same method. JTA/XA or a saga/outbox design is required depending on requirements; never assume two DataSources commit atomically together.

## 16. Exception Translation and Oracle Error Handling

Spring JDBC translates `SQLException` into the `DataAccessException` hierarchy. This decouples the service layer from raw JDBC vendor error codes.

Common exceptions:

| Spring exception | Common meaning |
|---|---|
| `DuplicateKeyException` | Unique/primary key violation |
| `DataIntegrityViolationException` | Constraint or data integrity violation |
| `BadSqlGrammarException` | Invalid SQL syntax or missing/invalid database object |
| `EmptyResultDataAccessException` | Zero rows returned when expecting one result |
| `IncorrectResultSizeDataAccessException` | Row count differs from expectation |
| `CannotGetJdbcConnectionException` | Failed to acquire a connection |
| `QueryTimeoutException` | Query exceeded configured query timeout |

Oracle error codes can still be inspected via the root-cause `SQLException` when detailed classification is needed. For example, `ORA-00001` indicates a unique constraint violation, `ORA-02291` indicates a missing parent foreign key, and `ORA-00060` indicates a deadlock detected.

Never catch every `DataAccessException` and return success or `null`. Classify recoverable errors, data errors, and system errors; log contextual fields like SQL operation, batch ID, and business keys without logging passwords or sensitive data.

## 17. Query Timeout, Fetch Size, and Handling Large Result Sets

### 17.1. Query Timeout

You can configure a timeout on `JdbcTemplate`:

```java
@Bean
JdbcTemplate jdbcTemplate(DataSource dataSource) {
    JdbcTemplate template = new JdbcTemplate(dataSource);
    template.setQueryTimeout(30);
    return template;
}
```

The timeout is in seconds and depends on JDBC driver/database support. Timeouts do not replace SQL tuning. For some operations, a timeout cancels the statement while the transaction still needs proper error handling/rollback.

### 17.2. Fetch Size

Fetch size hints how many rows the driver fetches per round trip when reading a `ResultSet`:

```java
JdbcTemplate template = new JdbcTemplate(dataSource);
template.setFetchSize(500);
```

The optimal value depends on row width, network latency, heap, and driver behavior. Larger fetch sizes reduce round trips at the cost of memory/buffers; smaller fetch sizes increase database round trips.

### 17.3. Streaming and Connection Lifetime

`JdbcTemplate.query(...)` with a `RowCallbackHandler` processes rows one by one without holding the entire result set in a `List`:

```java
jdbcTemplate.query(
        "SELECT order_id, total_amount FROM app.orders",
        (RowCallbackHandler) rs -> {
            long orderId = rs.getLong("ORDER_ID");
            BigDecimal amount = rs.getBigDecimal("TOTAL_AMOUNT");
            processOrder(orderId, amount);
        });
```

The template still holds the connection and ResultSet open while the callback executes. Avoid slow work such as HTTP calls or waiting on user input inside the callback, as the connection remains checked out. For large exports, stream data to files/object storage in chunks while controlling transactions and timeouts.

### 17.4. Oracle Cursors and Fetch Behavior

The Oracle JDBC driver uses cursors and fetch round trips to read results. `fetchSize` controls rows fetched per trip. For large queries, measure fetch size alongside row width, network, and heap. Never raise fetch size blindly, as rows containing CLOBs/BLOBs or large objects can spike memory usage quickly.

## 18. SQL Injection and Parameter Binding Safety

Always use bind parameters for data values:

```java
String sql = "SELECT order_id FROM app.orders WHERE customer_id = ?";
jdbcTemplate.query(sql, rowMapper, customerId);
```

Never concatenate strings:

```java
// Unsafe if customerId comes from external input.
String sql = "SELECT order_id FROM app.orders WHERE customer_id = " + customerId;
```

Named parameters also bind values and provide the same SQL injection protection:

```java
namedJdbc.query(
        "SELECT order_id FROM app.orders WHERE customer_id = :id",
        Map.of("id", customerId),
        rowMapper);
```

Bind parameters cannot replace identifiers. For sort columns, table names, or SQL fragments, use fixed allowlists. Never pass user input into `String.format` or concatenate it into `ORDER BY`.

## 19. Oracle Pagination and SQL Limits

Oracle Database 12c and later support `OFFSET ... FETCH`:

```sql
SELECT order_id,
       order_date,
       total_amount
FROM app.orders
WHERE customer_id = :customerId
ORDER BY order_date DESC, order_id DESC
OFFSET :offset ROWS FETCH NEXT :pageSize ROWS ONLY
```

You can bind offset/page size values, but validate they are non-negative and bounded by a maximum limit. A deterministic `ORDER BY` is required for stable pagination.

For very deep pages, OFFSET forces the database to scan past many rows before returning the page. Consider keyset pagination using the last key from the previous page:

```sql
SELECT order_id,
       order_date,
       total_amount
FROM app.orders
WHERE customer_id = :customerId
  AND (order_date, order_id) < (:lastOrderDate, :lastOrderId)
ORDER BY order_date DESC, order_id DESC
FETCH FIRST :pageSize ROWS ONLY
```

Verify row-value comparison semantics and Oracle data types in your target version; an equivalent condition can be written explicitly using `OR`. Keyset pagination requires suitable indexes and explicit handling of NULLs or duplicate sort keys per contract.

## 20. Oracle and JDBC Data Types: Reference Table

| Oracle SQL type | Common JDBC type | Common Java type | Notes |
|---|---|---|---|
| `NUMBER` | `NUMERIC` / `DECIMAL` | `BigDecimal` | Use for exact precision |
| `NUMBER(p,0)` | `NUMERIC` | `Long`/`Integer` if range fits | Check for overflow and NULL |
| `FLOAT` | `FLOAT`/`NUMERIC` depending on mapping | `BigDecimal` or `Double` per requirements | Oracle FLOAT is a numeric type with binary precision per Oracle definition |
| `BINARY_FLOAT` | `REAL` | `Float` | IEEE floating point |
| `BINARY_DOUBLE` | `DOUBLE` | `Double` | IEEE floating point |
| `VARCHAR2` | `VARCHAR` | `String` | Database character set |
| `CHAR` | `CHAR` | `String` | Space-padded |
| `NVARCHAR2` | `NVARCHAR` | `String` | National character set |
| `NCHAR` | `NCHAR` | `String` | Fixed-width national character |
| `DATE` | `DATE`/`TIMESTAMP` per driver | `Timestamp`/`LocalDateTime` | Oracle DATE includes time down to seconds |
| `TIMESTAMP` | `TIMESTAMP` | `LocalDateTime`/`Timestamp` | Includes fractional seconds |
| `TIMESTAMP WITH TIME ZONE` | `TIMESTAMP_WITH_TIMEZONE` or Oracle-specific mapping | `OffsetDateTime` | Verify driver/version |
| `TIMESTAMP WITH LOCAL TIME ZONE` | Driver/session-dependent mapping | `Timestamp`/`LocalDateTime` | Displayed in session time zone |
| `CLOB` | `CLOB` | `Clob`, `Reader`, `String` | Stream if large |
| `NCLOB` | `NCLOB` | `NClob`, `Reader`, `String` | National character data |
| `BLOB` | `BLOB` | `Blob`, `InputStream`, `byte[]` | Stream if large |
| `RAW` | `VARBINARY`/Oracle-specific | `byte[]` | Binary data |
| `LONG` | `LONGVARCHAR` | `String`/stream | Legacy type; consider migrating to CLOB |
| `LONG RAW` | `LONGVARBINARY` | `byte[]`/stream | Legacy type; consider BLOB |
| `ROWID` | `ROWID` | `RowId`/Oracle-specific | Never use as a business key |
| SQL `BOOLEAN` (23ai/23c+) | Driver/version dependent | `Boolean` | Not applicable to older DBs without SQL BOOLEAN |

Exact mappings can vary by Oracle JDBC driver version, `ResultSetMetaData`, column definition, and API call. This table is a type-selection guide, not a replacement for integration tests on the production driver.

## 21. Comprehensive Repository Example

A repository using named parameters, `BigDecimal`, `LocalDateTime`, and `RowMapper`:

```java
@Repository
public class OrderSearchRepository {

    private static final RowMapper<OrderSummary> ROW_MAPPER = (rs, rowNum) ->
            new OrderSummary(
                    rs.getLong("ORDER_ID"),
                    rs.getLong("CUSTOMER_ID"),
                    rs.getBigDecimal("TOTAL_AMOUNT"),
                    rs.getString("ORDER_STATUS")
            );

    private final NamedParameterJdbcTemplate jdbc;

    public OrderSearchRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<OrderSummary> search(
            Long customerId,
            String status,
            LocalDateTime from,
            LocalDateTime to) {

        String sql = """
            SELECT order_id,
                   customer_id,
                   total_amount,
                   order_status
            FROM app.orders
            WHERE (:customerId IS NULL OR customer_id = :customerId)
              AND (:status IS NULL OR order_status = :status)
              AND order_date >= :fromTime
              AND order_date < :toTime
            ORDER BY order_date DESC, order_id DESC
            """;

        MapSqlParameterSource params = new MapSqlParameterSource()
                .addValue("customerId", customerId, Types.NUMERIC)
                .addValue("status", status, Types.VARCHAR)
                .addValue("fromTime", Timestamp.valueOf(from), Types.TIMESTAMP)
                .addValue("toTime", Timestamp.valueOf(to), Types.TIMESTAMP);

        return jdbc.query(sql, params, ROW_MAPPER);
    }
}
```

The `(:param IS NULL OR column = :param)` pattern is convenient for optional filters, but does not always yield optimal execution plans, especially when bind peeking and selectivity vary widely. For critical queries, build SQL branches for the filters actually present (interpolating only fixed fragments from code) so the optimizer sees clear predicates. Never concatenate input values into SQL.

## 22. Testing Repositories with Oracle

### 22.1. Unit Tests vs. Integration Tests

Unit tests can verify service or mapper logic with mocks, but mocked JDBC does not prove Oracle type conversions work properly. For types like `DATE`, `TIMESTAMP WITH TIME ZONE`, `NUMBER`, `CLOB`, and `RAW`, integration tests against a compatible Oracle database/driver are essential.

### 22.2. Testing Critical Data Types

Include tests for:

- Large `NUMBER` values near maximum precision and various scales.
- Monetary values with decimals and rounding rules.
- SQL NULL in nullable columns.
- Oracle `DATE` with non-zero hours/minutes/seconds (`!= 00:00:00`).
- `TIMESTAMP` with fractional seconds.
- `TIMESTAMP WITH TIME ZONE` across different offsets.
- `CHAR` with trailing spaces.
- `NVARCHAR2` with multi-byte Unicode (e.g., Vietnamese) and non-BMP characters if needed.
- Empty strings versus NULL.
- Large CLOB/BLOB payloads and streaming lifecycles.
- Empty collection parameters and large lists.

### 22.3. Testing Transaction Rollbacks

Test a service method with multiple DML statements and verify that when a later step fails, earlier steps roll back per policy. Tests must run through the real Spring transaction manager, not just invoke repositories outside a transaction.

### 22.4. Performance Testing

For large queries, measure:

- Round trips and fetch size.
- Row counts and row widths.
- Heap usage during result mapping.
- Connection hold duration.
- Execution plans and logical/physical reads.
- Batch sizes, redo/undo volume, and transaction duration.

Never use H2 as proof of Oracle SQL compatibility. H2 can help test simple logic, but differences in data types, functions, sequences, locking, and SQL semantics require Oracle-specific tests to run against Oracle.

## 23. Common Errors When Using JdbcTemplate with Oracle

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `ORA-01722: invalid number` | String cannot convert to NUMBER or implicit conversion | Bind `BigDecimal`/numeric type, validate data, avoid implicit conversions |
| `ORA-01861: literal does not match format string` | Date string does not match format mask/NLS | Bind temporal types or use explicit format masks |
| `ORA-00932: inconsistent datatypes` | JDBC type incompatible with column/expression | Declare types explicitly; check Oracle type and driver mapping |
| `ORA-01008: not all variables bound` | Missing bind value or mismatched parameter name | Cross-check placeholders against parameter source |
| `ORA-01036: illegal variable name/number` | Wrong bind name/position or attempt to bind identifier | Bind data values only; verify named parameters |
| `ORA-00001: unique constraint violated` | Duplicate key data | Check keys, idempotency, and handle duplicates per business rules |
| `ORA-02291: integrity constraint violated - parent key not found` | Foreign key references nonexistent parent | Load parent first or validate foreign keys |
| `EmptyResultDataAccessException` | `queryForObject` returned zero rows | Use Optional pattern or query a list when empty is valid |
| Oracle DATE loses time portion | Mapped through `java.sql.Date`/`LocalDate` | Use `Timestamp`/`LocalDateTime` when time must be preserved |
| Monetary rounding errors | Used `double` instead of `BigDecimal` | Use `BigDecimal` and explicit rounding rules |
| NULL becomes 0 | Used primitive getter without `wasNull()` | Use wrapper/object mapping or check `wasNull()` |
| Empty IN list error | SQL becomes `IN ()` | Handle empty lists before executing query |
| Oversized list error | Too many placeholders/expressions | Chunk, use staging tables, or use SQL collections |
| OutOfMemoryError reading LOB | Loaded entire CLOB/BLOB onto heap | Stream and enforce size limits |
| Connection pool exhaustion | Long-held ResultSet/LOB streams or slow queries | Close resources promptly, set timeouts, tune SQL |

## 24. Process for Building a Reliable JDBC Layer

When adding a Spring JDBC repository for Oracle, follow this sequence:

1. **Define the SQL contract:** tables, columns, predicates, joins, ordering, and expected cardinality.
2. **Choose the template:** `JdbcTemplate` for positional placeholders; `NamedParameterJdbcTemplate` for SQL with many parameters or collections.
3. **Choose Java types:** `BigDecimal` for exact numbers, `LocalDateTime` for Oracle DATE/TIMESTAMP with time, `OffsetDateTime` for time-zoned timestamps when driver-supported.
4. **Bind explicitly:** use `MapSqlParameterSource`/`SqlParameterValue` with JDBC types for NULLs and specialized types.
5. **Map explicitly:** use `RowMapper` for DTOs; avoid N+1 queries and uncontrolled implicit mappings.
6. **Handle LOBs:** stream large payloads and manage connection/resource lifecycles properly.
7. **Define transactions:** place `@Transactional` at service boundaries; never commit manually in repositories.
8. **Control batches:** size batches and transaction chunks to fit the workload.
9. **Protect SQL:** bind values, allowlist identifiers, and never concatenate arbitrary input.
10. **Test on Oracle:** verify data types, NULLs, time zones, precision, transactions, and execution plans.

## 25. Pre-Production Repository Checklist

| Item | Question to Confirm |
|---|---|
| Driver | Is the Oracle JDBC driver compatible with the JDK, database, and Spring Boot versions? |
| DataSource | Does the URL use the right service name; is pool size within database capacity? |
| SQL | Are all external values bound? Do dynamic identifiers use allowlists? |
| Named parameters | Do parameter names match, and are empty/large collections handled? |
| NUMBER | Do monetary and high-precision numbers use `BigDecimal`? |
| DATE | Is the time component of Oracle DATE preserved where business logic needs it? |
| TIME ZONE | Do session time zone and Java time types match semantics? |
| Character | Are CHAR padding, Unicode, and empty-string/NULL semantics handled properly? |
| LOB | Are large LOBs streamed and connection lifetimes bounded? |
| NULL | Are JDBC types declared when binding null; do primitive getters check `wasNull()`? |
| Transaction | Does the repository share the DataSource/transaction manager; is rollback policy clear? |
| Batch | Are batch size, transaction duration, redo/undo, and retries controlled? |
| Error handling | Are exceptions classified; are errors never swallowed? |
| Performance | Have fetch size, execution plans, round trips, and heap usage been measured? |
| Integration tests | Have Oracle-specific types been tested against real Oracle JDBC? |

`JdbcTemplate` and `NamedParameterJdbcTemplate` help keep Oracle data-access layers concise while retaining SQL control. What matters most is binding values with the right types, mapping results deliberately, and understanding Oracle-specific semantics: `DATE` includes time, `NUMBER` needs exact precision, `CHAR` is space-padded, empty strings behave as NULL, LOBs require stream lifecycle management, and time-zoned timestamps depend on driver and session configuration. Combining these practices with proper transaction boundaries, batch sizing, timeouts, fetch sizes, and Oracle integration tests yields a JDBC layer that is stable and operable in Spring Boot.
