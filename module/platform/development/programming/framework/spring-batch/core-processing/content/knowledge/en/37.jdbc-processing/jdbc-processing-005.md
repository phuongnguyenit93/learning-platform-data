# Immutable RowMapper in Spring Batch

In Spring Batch, JDBC readers typically use Spring JDBC to transform each row of a `ResultSet` into a Java object. The component performing this mapping is **RowMapper**. A well-designed `RowMapper` usually holds no state between invocations, does not mutate the read data structures, and produces an object whose values remain stable after leaving the `ResultSet`.

In batch processing, those characteristics are especially important. A `RowMapper` with mutable state can accidentally carry over data from a previous row, causing bugs when reused or when multiple Steps run concurrently. A mutable output object can be modified after reading, causing the processor, writer, or retry pass to see different values. Designing an immutable `RowMapper` makes data reading predictable, easier to test, and safer to reuse.

Two concepts should be distinguished:

- **Immutable/stateless RowMapper:** the mapper itself does not mutate state during mapping and does not store the `ResultSet` or current row's data in fields.
- **Immutable output object:** the object created from a data row does not allow state modification after instantiation, or protects mutable data via defensive copies.

These two complement each other. A mapper can be stateless yet return a mutable object; conversely, an object can be immutable yet the mapper remains unsafe if it holds a shared field. In batch processing, design both sides explicitly.

This lesson focuses on `RowMapper` in Spring JDBC and how to use it with `JdbcCursorItemReader` and `JdbcPagingItemReader`. Topics include mapping with Java records or final classes, handling SQL `NULL` and data types, mapping `JOIN` queries, restarts, concurrency, and testing mappers.

## 1. What Does RowMapper Do?

Spring JDBC defines `RowMapper` to map the current row of a `ResultSet` into an object:

~~~java
public interface RowMapper<T> {
    T mapRow(ResultSet rs, int rowNum) throws SQLException;
}
~~~

The two parameters:

- `rs` is the `ResultSet` positioned at the row to be mapped.
- `rowNum` is the row index provided by the framework for the current mapping call.
- The return value is the object representing that row.
- `SQLException` may be thrown so the framework handles it via JDBC/Spring mechanisms.

Simple example:

~~~java
public class CustomerRowMapper implements RowMapper<Customer> {

    @Override
    public Customer mapRow(ResultSet rs, int rowNum)
            throws SQLException {

        return new Customer(
            rs.getLong("customer_id"),
            rs.getString("full_name"),
            rs.getString("email")
        );
    }
}
~~~

For each `ResultSet` row, the mapper creates a new `Customer`. The mapper does not call `rs.next()`; cursor movement is managed by `JdbcTemplate` or the reader.

### One mapRow Call Corresponds to One Row

`RowMapper` is not the place to drive the `ResultSet` loop. Do not write:

~~~java
@Override
public Customer mapRow(ResultSet rs, int rowNum)
        throws SQLException {

    while (rs.next()) {
        // Do not do this inside RowMapper.
    }

    return null;
}
~~~

If it calls `rs.next()` itself, the mapper advances the cursor by an extra row and causes the framework to skip data or hit cursor state errors.

Also do not store `ResultSet` in a field for use after `mapRow` completes. A `ResultSet`'s lifecycle is tied to its statement/connection; once the query finishes, it may already be closed.

## 2. Why Should RowMapper Be Stateless?

`RowMapper` is often registered as a singleton Spring bean and reused across many queries. A stateless implementation can process multiple `ResultSet`s without carrying data from one call to the next.

Unsafe example:

~~~java
public class UnsafeCustomerRowMapper
        implements RowMapper<Customer> {

    private long currentCustomerId;
    private String currentName;

    @Override
    public Customer mapRow(ResultSet rs, int rowNum)
            throws SQLException {

        currentCustomerId = rs.getLong("customer_id");
        currentName = rs.getString("full_name");

        return new Customer(currentCustomerId, currentName);
    }
}
~~~

The fields `currentCustomerId` and `currentName` have no reason to exist. They create shared mutable state and can cause race conditions if the mapper is called concurrently.

Safe approach:

~~~java
public final class CustomerRowMapper
        implements RowMapper<Customer> {

    @Override
    public Customer mapRow(ResultSet rs, int rowNum)
            throws SQLException {

        long customerId = rs.getLong("customer_id");
        String name = rs.getString("full_name");

        return new Customer(customerId, name);
    }
}
~~~

Local variables exist only within a single `mapRow` invocation. Each row creates a new object without writing data to shared fields.

### Stateless Enables Reuse

A stateless mapper can be:

- Declared as a singleton bean.
- Used by multiple queries sharing the same projection.
- Shared across Steps if the mapping contract is identical.
- Invoked concurrently without race conditions from internal state.
- Unit tested independently of a Spring context.

Being stateless does not automatically guarantee all dependencies are thread-safe. If a mapper uses a formatter or converter that holds mutable state, that dependency must also be designed safely.

## 3. What Is an Immutable Output Object?

An immutable object is an object whose state cannot change after it is created. Instead of creating an empty object and calling setters, the constructor takes all required values.

Mutable example:

~~~java
public class Customer {
    private long id;
    private String name;
    private String email;

    public void setId(long id) {
        this.id = id;
    }

    public void setName(String name) {
        this.name = name;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
~~~

This object can be constructed in an incomplete state and populated field by field later. Another component can mutate `name` or `email` after the reader has returned the object.

An immutable model using a Java record:

~~~java
public record Customer(
    long id,
    String name,
    String email
) {
}
~~~

A record generates a constructor, accessors, and value-based methods. A record's fields are final. If its internal components are also immutable, `Customer` is a suitable value object for the pipeline.

Another option is a `final` class with `final` fields:

~~~java
public final class Customer {

    private final long id;
    private final String name;
    private final String email;

    public Customer(long id, String name, String email) {
        this.id = id;
        this.name = name;
        this.email = email;
    }

    public long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Provide no setters or field-mutating methods. The constructor validates invariants and initializes a complete object.

## 4. Records Are a Good Fit for JDBC Projections

On Java 16 and later, records are often well suited for objects that simply hold data queried from a database.

Example:

~~~java
public record OrderRow(
    long orderId,
    String orderNumber,
    String status,
    BigDecimal total,
    LocalDate createdDate
) {
}
~~~

RowMapper:

~~~java
public final class OrderRowMapper
        implements RowMapper<OrderRow> {

    @Override
    public OrderRow mapRow(ResultSet rs, int rowNum)
            throws SQLException {

        Date createdDate = rs.getDate("created_date");

        return new OrderRow(
            rs.getLong("order_id"),
            rs.getString("order_number"),
            rs.getString("status"),
            rs.getBigDecimal("total"),
            createdDate == null ? null : createdDate.toLocalDate()
        );
    }
}
~~~

The mapper holds no fields, and `OrderRow` has no setters. Each call to `mapRow` produces a snapshot of the current row's values.

Records can be used directly with `ItemProcessor`:

~~~java
@Bean
ItemProcessor<OrderRow, OrderSummary> orderProcessor() {
    return row -> new OrderSummary(
        row.orderId(),
        row.orderNumber(),
        row.total()
    );
}
~~~

Not every object in a pipeline has to be a record. If a project uses an older Java version or requires specific framework binding, a `final` class with a constructor remains a solid choice.

## 5. Deep Immutability and Defensive Copies

Having `final` fields does not automatically make an object deeply immutable. If a record contains a mutable `List`, `Map`, array, or `Date`, its internal data can still be mutated.

Insufficiently safe example:

~~~java
public record CustomerWithTags(
    long id,
    List<String> tags
) {
}
~~~

The `tags` reference is final, yet callers can still modify the list if the list is mutable.

Use a defensive copy:

~~~java
public record CustomerWithTags(
    long id,
    List<String> tags
) {
    public CustomerWithTags {
        tags = List.copyOf(tags);
    }
}
~~~

`List.copyOf` creates an unmodifiable list through the returned reference. If input can be null, specify the rule clearly: reject null, replace with `List.of()`, or preserve null per contract.

With `Map`:

~~~java
public record CustomerAttributes(
    long id,
    Map<String, String> attributes
) {
    public CustomerAttributes {
        attributes = Map.copyOf(attributes);
    }
}
~~~

With arrays, clone both on input and on output:

~~~java
public final class BinaryPayload {

    private final byte[] content;

    public BinaryPayload(byte[] content) {
        this.content = content.clone();
    }

    public byte[] content() {
        return content.clone();
    }
}
~~~

If elements inside a collection are also mutable, copying the collection is not enough. Create immutable copies of each element or use immutable value types.

## 6. Mapping SQL NULL Properly

JDBC has a well-known pitfall: primitive getters such as `getLong()`, `getInt()`, and `getBoolean()` do not return null. When the SQL column is `NULL`, they return a default value; you must call `wasNull()` immediately after the getter to determine whether the value just read was null.

Example:

~~~java
long parentIdValue = rs.getLong("parent_id");
Long parentId = rs.wasNull() ? null : parentIdValue;
~~~

`wasNull()` must be called right after the corresponding getter. If you call another getter first and then `wasNull()`, the result reflects the most recent getter rather than `parent_id`.

If the driver supports JDBC 4.1 and compatible types, you can fetch wrapper types directly:

~~~java
Long parentId = rs.getObject("parent_id", Long.class);
Integer retryCount = rs.getObject("retry_count", Integer.class);
Boolean enabled = rs.getObject("enabled", Boolean.class);
~~~

This represents null clearly and avoids pairing primitive getters with `wasNull`. Still, verify behavior against your actual driver and column types.

### Distinguishing Zero from NULL

These two states can carry different business meanings:

| SQL value | getLong() | Meaningful value |
|---|---:|---|
| 0 | 0 | Actual number 0 |
| NULL | 0 | No value present |

If you omit `wasNull()`, the mapper turns `NULL` into `0` and loses information. This can cause the processor to miscalculate or misclassify records.

For required fields, you can fail explicitly if the database returns `NULL`:

~~~java
Long quantity = rs.getObject("quantity", Long.class);

if (quantity == null) {
    throw new SQLException(
        "Column quantity must not be NULL"
    );
}
~~~

If null is a valid state, keep the wrapper type in the DTO instead of coercing it to a primitive.

## 7. Numeric Types and BigDecimal

For currency, rates, or decimal numbers requiring exact precision, use `BigDecimal`:

~~~java
BigDecimal amount = rs.getBigDecimal("amount");
~~~

Do not convert `DECIMAL` to `double` and reconstruct `BigDecimal`:

~~~java
// Avoid converting through double:
BigDecimal amount = BigDecimal.valueOf(
    rs.getDouble("amount")
);
~~~

Going through `double` can lose decimal precision. Reading directly with `getBigDecimal` preserves the exact decimal representation from the JDBC driver.

If the column can be `NULL`, `getBigDecimal` returns null. Keep null or apply a default according to a clearly defined business rule.

### Scale and Rounding

The database might store `DECIMAL(18, 2)`, while an object or business rule requires a different scale. Do not arbitrarily call `setScale` inside `RowMapper` if that represents a business calculation rule.

The mapper should reflect the stored value. Rounding, currency conversion, or precision policies belong in the processor or domain service.

## 8. Mapping Enums and Status Values

If the database stores status as `VARCHAR`:

~~~text
status
------
ACTIVE
SUSPENDED
CLOSED
~~~

It can be mapped to an enum:

~~~java
public enum CustomerStatus {
    ACTIVE,
    SUSPENDED,
    CLOSED
}
~~~

Mapper:

~~~java
private CustomerStatus mapStatus(String value) {
    if (value == null) {
        return null;
    }

    try {
        return CustomerStatus.valueOf(
            value.trim().toUpperCase(Locale.ROOT)
        );
    } catch (IllegalArgumentException ex) {
        throw new IllegalArgumentException(
            "Unsupported customer status: " + value,
            ex
        );
    }
}
~~~

In `mapRow`:

~~~java
CustomerStatus status = mapStatus(
    rs.getString("status")
);
~~~

If the database contains legacy values such as `ENABLED`, `DISABLED`, or abbreviated codes, use an explicit mapping:

~~~java
private CustomerStatus mapStatus(String value) {
    if (value == null) {
        return null;
    }

    return switch (value) {
        case "A", "ACTIVE" -> CustomerStatus.ACTIVE;
        case "S", "SUSPENDED" -> CustomerStatus.SUSPENDED;
        case "C", "CLOSED" -> CustomerStatus.CLOSED;
        default -> throw new IllegalArgumentException(
            "Unknown status code: " + value
        );
    };
}
~~~

Do not silently map unrecognized values to `ACTIVE` or a default status that alters data meaning. If legacy compatibility is needed, document the mapping explicitly and test each code.

## 9. Mapping Dates and Times

JDBC has SQL `DATE`, `TIME`, and `TIMESTAMP` types. Convert them to `java.time` types rather than putting mutable `java.sql.Date` or `java.sql.Timestamp` into domain objects.

SQL `DATE` example:

~~~java
Date sqlDate = rs.getDate("business_date");
LocalDate businessDate =
    sqlDate == null ? null : sqlDate.toLocalDate();
~~~

`TIMESTAMP` to `LocalDateTime` example:

~~~java
Timestamp timestamp = rs.getTimestamp("created_at");
LocalDateTime createdAt =
    timestamp == null ? null : timestamp.toLocalDateTime();
~~~

If the column represents an absolute point in time:

~~~java
Timestamp timestamp = rs.getTimestamp("created_at");
Instant createdAt =
    timestamp == null ? null : timestamp.toInstant();
~~~

Understand the column type, database timezone, JDBC driver, and session configuration. A `TIMESTAMP` without timezone may be interpreted using the session/driver timezone; do not assume every timestamp is UTC.

For SQL types with timezone, you can use JDBC 4.2 `getObject` with `OffsetDateTime` if the driver supports it:

~~~java
OffsetDateTime createdAt =
    rs.getObject("created_at", OffsetDateTime.class);
~~~

Test with the real database and driver. Never use `java.util.Date` as an immutable field since it can be mutated through `setTime`.

## 10. Mapping Columns with Clear Aliases

`JOIN` queries can contain multiple columns sharing names such as `id`, `status`, or `created_at`. If the mapper reads by an ambiguous label, the driver may return the wrong column or throw an error.

Use descriptive aliases for the projection:

~~~sql
SELECT
    c.customer_id AS customer_id,
    c.status AS customer_status,
    a.account_id AS account_id,
    a.status AS account_status
FROM customer c
LEFT JOIN account a
    ON a.customer_id = c.customer_id
~~~

Mapper reads the exact labels:

~~~java
return new CustomerAccountRow(
    rs.getLong("customer_id"),
    rs.getString("customer_status"),
    rs.getObject("account_id", Long.class),
    rs.getString("account_status")
);
~~~

Alias names are part of the contract between SQL and `RowMapper`. When changing an alias, update the query and mapper together.

Avoid `SELECT *` in queries with `JOIN`. `SELECT *` ties the projection to schema layout and can produce duplicate column names, making mapping fragile when tables evolve.

## 11. Mapping a JOIN Row to an Immutable Projection

A one-to-one or many-to-one `JOIN` can be mapped into a combined object:

~~~java
public record CustomerAccountRow(
    long customerId,
    String customerName,
    Long accountId,
    String accountStatus
) {
}
~~~

RowMapper:

~~~java
public final class CustomerAccountRowMapper
        implements RowMapper<CustomerAccountRow> {

    @Override
    public CustomerAccountRow mapRow(
            ResultSet rs,
            int rowNum) throws SQLException {

        return new CustomerAccountRow(
            rs.getLong("customer_id"),
            rs.getString("customer_name"),
            rs.getObject("account_id", Long.class),
            rs.getString("account_status")
        );
    }
}
~~~

A `LEFT JOIN` may find no matching account. In that case, `account_id` and `account_status` are null. The mapper should preserve that semantics rather than turning them into ID `0` or an empty string.

This is a single-row `JOIN` projection. It works when each SQL row corresponds to one output object.

## 12. One-to-Many JOINs Need Different Handling

Suppose one customer has multiple addresses. A `JOIN` query may return:

~~~text
customer_id | customer_name | address_id | city
------------+---------------+------------+----------
10          | An            | 101        | Hanoi
10          | An            | 102        | Da Nang
11          | Binh          | 103        | HCMC
~~~

A regular `RowMapper` creates one object per row. If mapped to `CustomerWithAddresses`, the first two rows will produce two separate `Customer` objects with ID 10, each holding one address.

Do not put a `Map` field inside a singleton `RowMapper` to accumulate addresses across `mapRow` calls. That retains state across queries, cannot tell when a customer is finished, and is unsafe under concurrent execution.

Better options include:

- Using `ResultSetExtractor` to iterate the entire `ResultSet` and group parent-child rows.
- Querying parents separately and loading collections via another query.
- Returning a flat per-row projection and grouping inside a well-scoped processor/service.
- Using SQL aggregation such as JSON aggregation if the database and contract fit.

### When to Use ResultSetExtractor

`RowMapper` fits mapping one row to one object. `ResultSetExtractor` fits reading multiple rows to produce an aggregated result.

Conceptual example:

~~~java
Map<Long, CustomerBuilder> customers = new LinkedHashMap<>();

while (rs.next()) {
    long customerId = rs.getLong("customer_id");

    CustomerBuilder customer = customers.computeIfAbsent(
        customerId,
        id -> new CustomerBuilder(
            id,
            readCustomerName(rs)
        )
    );

    Long addressId = rs.getObject("address_id", Long.class);

    if (addressId != null) {
        customer.addAddress(readAddress(rs));
    }
}

return customers.values().stream()
    .map(CustomerBuilder::build)
    .toList();
~~~

This snippet illustrates grouping only. `ResultSetExtractor` controls iterating the `ResultSet`; `RowMapper` does not. A mutable builder can be used locally within one extraction pass and then converted into immutable objects when returning results.

## 13. RowMapper in JdbcTemplate

`JdbcTemplate.query` accepts SQL and a `RowMapper`:

~~~java
List<CustomerRow> customers = jdbcTemplate.query(
    """
    SELECT customer_id, full_name, email
    FROM customer
    WHERE status = ?
    ORDER BY customer_id
    """,
    customerRowMapper,
    "ACTIVE"
);
~~~

Spring JDBC manages creating the statement, executing the query, iterating the `ResultSet`, and calling `mapRow` for each row.

The mapper must not:

- Call `rs.next()`.
- Close the `ResultSet` or `Statement`.
- Close the `Connection` managed by `JdbcTemplate`.
- Store the `ResultSet` in a field.
- Issue other queries using the same `ResultSet` being mapped.
- Alter the cursor or transaction boundaries.

If you need to query additional data for every row, that is an N+1 pattern that can hurt performance. Consider a `JOIN`, batch query, or post-projection enrichment.

## 14. Using RowMapper with JdbcCursorItemReader

In Spring Batch, `JdbcCursorItemReader` uses `RowMapper` to turn each cursor row into an item:

~~~java
@Bean
@StepScope
JdbcCursorItemReader<CustomerRow> customerReader(
        DataSource dataSource,
        CustomerRowMapper customerRowMapper,
        @Value("#{jobParameters['status']}") String status) {

    return new JdbcCursorItemReaderBuilder<CustomerRow>()
        .name("customerReader")
        .dataSource(dataSource)
        .sql("""
            SELECT customer_id, full_name, email, status
            FROM customer
            WHERE status = ?
            ORDER BY customer_id
            """)
        .preparedStatementSetter(ps ->
            ps.setString(1, status)
        )
        .rowMapper(customerRowMapper)
        .fetchSize(500)
        .saveState(true)
        .build();
}
~~~

The reader opens the cursor and controls movement through the `ResultSet`. `RowMapper` only transforms the current row into a `CustomerRow`.

With a cursor reader:

- Do not call `rs.next()` inside `mapRow`.
- Do not close the cursor or connection inside the mapper.
- Do not store state in mapper fields.
- The reader manages resources and checkpoints.
- The mapper should return an object independent of `ResultSet` so the item remains usable after the cursor advances.

### Why Must the Object Be Independent of ResultSet?

`ResultSet` is valid only within the query's lifecycle. If a DTO retains a `Blob`, `Clob`, `SQLXML`, or connection-backed stream, data may become unreadable after the reader moves to the next row or closes the cursor.

If LOB data is needed, read it into a `byte[]`, `String`, or standalone representation during `mapRow`, keeping memory limits and payload size in mind.

## 15. Using RowMapper with JdbcPagingItemReader

`JdbcPagingItemReader` also uses `RowMapper` to convert each row of each page into an item:

~~~java
@Bean
@StepScope
JdbcPagingItemReader<CustomerRow> customerPagingReader(
        DataSource dataSource,
        PagingQueryProvider queryProvider,
        CustomerRowMapper customerRowMapper) {

    return new JdbcPagingItemReaderBuilder<CustomerRow>()
        .name("customerPagingReader")
        .dataSource(dataSource)
        .queryProvider(queryProvider)
        .pageSize(500)
        .rowMapper(customerRowMapper)
        .saveState(true)
        .build();
}
~~~

`RowMapper` does not need to know which page the data belongs to. It simply receives the current row and maps it.

A paging reader requires a stable sort key for pagination and restart. If the sort key is not unique, rows with equal values can be duplicated or skipped depending on the query provider and database. Usually you should use the primary key or combine secondary keys to form a total order.

### Mapper Does Not Store Page State

Do not put page number, current offset, or last ID in fields of a singleton `RowMapper`. That state belongs to the reader or `ExecutionContext`.

Separation of responsibilities:

| Component | Owned state |
|---|---|
| `RowMapper` | No per-row or per-page state |
| `JdbcPagingItemReader` | Page, sort key, and checkpoint |
| `ItemProcessor` | Business state if any, clearly scoped |
| `JobRepository` | Persistent metadata and `ExecutionContext` |

## 16. RowMapper and Restart

`RowMapper` is not a checkpointing component. It does not need to implement `ItemStream` just because it is used by a restartable reader.

The Spring Batch reader is responsible for:

- Tracking the current position.
- Updating `ExecutionContext`.
- Restoring state on restart.
- Managing the cursor or pages.
- Opening and closing resources.

`RowMapper` is responsible for:

- Reading columns of the current row.
- Converting data types.
- Creating the output object.
- Holding no state across rows.

Because the mapper should be deterministic, the same data row and mapping contract should yield the same object value. If mapping depends on current wall-clock time or a mutable service, a restart can produce a different object for the same row. If a snapshot value is needed, pass it via `JobParameters` or persisted data before processing.

### Avoid Side Effects in mapRow

Do not send emails, update tables, write files, or call APIs with side effects inside `mapRow`. The reader can re-read items after rollback/restart or retry; side effects inside a mapper are hard to control and can repeat.

Mapping should be a pure data transformation.

## 17. Mapping Complex Data Types

A `RowMapper` can convert multiple types:

~~~java
public record InvoiceRow(
    long id,
    String invoiceNumber,
    BigDecimal amount,
    LocalDate invoiceDate,
    Instant createdAt,
    InvoiceStatus status,
    Boolean approved
) {
}
~~~

Mapper:

~~~java
public final class InvoiceRowMapper
        implements RowMapper<InvoiceRow> {

    @Override
    public InvoiceRow mapRow(ResultSet rs, int rowNum)
            throws SQLException {

        Date invoiceDate = rs.getDate("invoice_date");
        Timestamp createdAt = rs.getTimestamp("created_at");
        String statusValue = rs.getString("status");

        return new InvoiceRow(
            rs.getLong("invoice_id"),
            rs.getString("invoice_number"),
            rs.getBigDecimal("amount"),
            invoiceDate == null
                ? null
                : invoiceDate.toLocalDate(),
            createdAt == null
                ? null
                : createdAt.toInstant(),
            statusValue == null
                ? null
                : InvoiceStatus.valueOf(statusValue),
            rs.getObject("approved", Boolean.class)
        );
    }
}
~~~

In production, enum parsing must handle legacy or invalid values according to contract. If data is invalid, throw a meaningful exception instead of silently picking a default enum constant.

### UUID

If the database stores `UUID` and the JDBC driver supports the type, you can use `getObject` with `UUID.class`. If the driver or database stores `UUID` as `VARCHAR`/`BINARY`, map it to match the schema:

~~~java
String rawId = rs.getString("external_id");
UUID externalId =
    rawId == null ? null : UUID.fromString(rawId);
~~~

Do not assume every database stores UUIDs identically.

### JSON Columns

If a column contains JSON, `RowMapper` can read the `String` and parse it using `ObjectMapper`:

~~~java
String rawMetadata = rs.getString("metadata_json");

Metadata metadata = rawMetadata == null
    ? null
    : objectMapper.readValue(rawMetadata, Metadata.class);
~~~

A configured `ObjectMapper` can be shared if used in a thread-safe manner. Do not instantiate a new JSON mapper for every row unnecessarily, and never reconfigure a shared `ObjectMapper` while a batch is running.

## 18. Mapping Null Data and Domain Invariants

Not every SQL `NULL` should simply be preserved as null. The decision depends on domain meaning:

- Optional fields: preserve null using wrappers or `Optional` at the appropriate layer.
- Required fields: fail if the database violates the invariant.
- Fields with business defaults: apply defaults deliberately, with tests and auditability.
- Legacy fields: convert through an explicit mapping.

Example constructor validating invariants:

~~~java
public record ProductRow(
    long id,
    String sku,
    String name,
    BigDecimal price
) {
    public ProductRow {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException(
                "sku must not be blank"
            );
        }

        if (price == null || price.signum() < 0) {
            throw new IllegalArgumentException(
                "price is invalid"
            );
        }
    }
}
~~~

If the constructor throws an exception, the failure happens immediately when `mapRow` constructs the object. This keeps invalid data from traveling deeper into the processor/writer.

Still, distinguish skippable data errors from schema/infrastructure errors. If an entire required column is `NULL` due to a bad migration, skipping row by row can mask a system-wide failure.

## 19. Do Not Return Objects Tied to JDBC Resources

An output object should stand on its own once `mapRow` finishes. Avoid returning directly:

- `ResultSet`.
- Connection-bound `Blob` or `Clob`.
- Unread `SQLXML`.
- An `InputStream` obtained from a LOB without materializing it.
- Unconverted JDBC `Array`.
- Proxies or wrappers tied to a finished transaction.

Example reading a `Clob` into a `String`:

~~~java
Clob clob = rs.getClob("description");

String description = null;

if (clob != null) {
    long length = clob.length();

    if (length > MAX_DESCRIPTION_LENGTH) {
        throw new SQLException(
            "Description exceeds allowed limit"
        );
    }

    description = clob.getSubString(1, (int) length);
}
~~~

This code enforces a size limit so unbounded payloads are not loaded onto the heap. For very large LOBs, design a dedicated streaming workflow instead of attaching a `ResultSet`-backed stream to an item and using it after the cursor closes.

## 20. Should RowMapper Take Dependencies?

A `RowMapper` can accept dependencies such as `ObjectMapper`, converters, or mapping configuration. To preserve immutability:

- Inject dependencies via the constructor.
- Store them in `final` fields.
- Never mutate dependencies after construction.
- Shared dependencies must be thread-safe.
- Do not store current row data in fields.

Example:

~~~java
public final class EventRowMapper
        implements RowMapper<EventRow> {

    private final ObjectMapper objectMapper;

    public EventRowMapper(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public EventRow mapRow(ResultSet rs, int rowNum)
            throws SQLException {

        String payload = rs.getString("payload");

        try {
            EventPayload parsed =
                objectMapper.readValue(payload, EventPayload.class);

            return new EventRow(
                rs.getLong("event_id"),
                rs.getString("event_type"),
                parsed
            );
        } catch (JsonProcessingException ex) {
            throw new SQLException(
                "Unable to parse event payload",
                ex
            );
        }
    }
}
~~~

Once configured, `ObjectMapper` is typically reused. Never call `registerModule` or modify settings on a shared `ObjectMapper` while a batch is running.

### Constructor Injection in Spring

You can declare the mapper bean as:

~~~java
@Bean
EventRowMapper eventRowMapper(ObjectMapper objectMapper) {
    return new EventRowMapper(objectMapper);
}
~~~

Spring beans are singletons by default. This is safe when the mapper holds no mutable per-request/per-row state and shared dependencies are thread-safe.

## 21. Immutable RowMapper Does Not Mean Immutable SQL

A mapper can be stateless yet results can still change if the query reads database data that changes between runs. Separate two concerns:

- Whether the mapper is deterministic for a given `ResultSet` row.
- Whether the query and data source provide suitable snapshot/ordering semantics for batch processing.

If the batch must process an exact dataset as of a point in time, use a business date, cutoff timestamp, batch ID, snapshot isolation, or a materialized ID set. Do not rely on the mapper to solve source consistency.

With `JdbcPagingItemReader`, a stable sort key and cutoff filter prevent new data from creeping into the read set.

## 22. Exception Handling in RowMapper

`RowMapper` declares `throws SQLException`. When reading columns or converting data, several errors can occur:

- `SQLException` from missing columns or driver errors.
- `IllegalArgumentException` when parsing enums or UUIDs.
- `JsonProcessingException` when parsing JSON.
- Domain validation exceptions when the constructor rejects invalid data.

Do not catch all `Exception`s and return an empty object. That turns corrupt data into seemingly valid items and delays failure until later.

Example exception translation:

~~~java
try {
    return mapDomainObject(rs);
} catch (IllegalArgumentException ex) {
    throw new SQLException(
        "Database data does not match projection",
        ex
    );
}
~~~

Depending on the application, you can define a dedicated exception mapping. When used in Spring Batch, check the cause chain and configure retry/skip against the actual exceptions thrown by the reader in your Spring Batch version.

### Do Not Log Entire Rows by Default

Rows may contain emails, account numbers, tokens, or personal data. If mapping fails, log the primary key, query context, or correlation ID needed for investigation rather than dumping all column values.

## 23. ColumnMapRowMapper vs. Custom RowMapper

Spring JDBC can return a map keyed by column names via `ColumnMapRowMapper`. This is convenient for dynamic queries or generic tooling, but a map lacks the strong domain typing of a DTO.

| Approach | Best suited when |
|---|---|
| Custom `RowMapper` | Stable projection, explicit types, custom conversion logic |
| `BeanPropertyRowMapper` | Column names map cleanly by property conventions and object fits |
| `DataClassRowMapper` | Constructor/record mapping supported by your Spring version |
| `ColumnMapRowMapper` | Dynamic queries or data needed in `Map` form |
| `ResultSetExtractor` | Aggregating multiple rows into a single result |

`BeanPropertyRowMapper` or `DataClassRowMapper` can reduce boilerplate, though you still need to verify null handling, constructors, alias names, and type conversions. Do not pick an automatic mapper solely for shorter code when the projection has important conversion rules.

A custom `RowMapper` is a clear choice when enum mapping, SQL `NULL` semantics, JSON, timezones, or domain invariants are involved.

## 24. Testing RowMapper in Isolation

Unit tests should verify mapping from a `ResultSet` row into an object.

You can use Mockito to mock `ResultSet`:

~~~java
@Test
void mapsCustomerColumns() throws SQLException {
    ResultSet rs = mock(ResultSet.class);

    when(rs.getLong("customer_id")).thenReturn(42L);
    when(rs.getString("full_name")).thenReturn("An Nguyen");
    when(rs.getString("email")).thenReturn("an@example.test");

    CustomerRowMapper mapper = new CustomerRowMapper();

    Customer customer = mapper.mapRow(rs, 0);

    assertEquals(42L, customer.id());
    assertEquals("An Nguyen", customer.name());
    assertEquals("an@example.test", customer.email());
}
~~~

This test focuses on the mapper contract without opening a database. It is useful for checking every field, alias, type conversion, and null handling.

Using Mockito requires adding the corresponding test dependency to the project. Mocking is not mandatory; you can also use a real `ResultSet` from an embedded database in integration tests.

## 25. Testing SQL NULL

With primitive getters, tests must simulate both the default primitive return value and `wasNull`:

~~~java
@Test
void preservesNullForNullableLong() throws SQLException {
    ResultSet rs = mock(ResultSet.class);

    when(rs.getLong("parent_id")).thenReturn(0L);
    when(rs.wasNull()).thenReturn(true);

    NullableCustomerRowMapper mapper =
        new NullableCustomerRowMapper();

    CustomerRelation relation = mapper.mapRow(rs, 0);

    assertNull(relation.parentId());
}
~~~

If the mapper uses `getObject("parent_id", Long.class)`, the test is simpler:

~~~java
when(rs.getObject("parent_id", Long.class)).thenReturn(null);
~~~

Include a separate test for an actual `0` value to ensure the mapper does not confuse zero with `NULL`.

## 26. Testing Immutable Output Objects

If the output is a record containing only `String`, `Long`, and `BigDecimal`, those fields are already immutable. If there are collections or arrays, test defensive copying.

~~~java
@Test
void copiesTagsAndPreventsMutation() {
    List<String> source = new ArrayList<>();
    source.add("vip");

    CustomerWithTags customer =
        new CustomerWithTags(10L, source);

    source.add("internal");

    assertEquals(List.of("vip"), customer.tags());

    assertThrows(
        UnsupportedOperationException.class,
        () -> customer.tags().add("new-tag")
    );
}
~~~

This test confirms the object is unaffected when the caller mutates the input list and that the returned list cannot be modified.

If the model contains other mutable objects, tests must also check nested objects. Immutability must be evaluated across the entire object graph, not just `final` modifiers on top-level fields.

## 27. Testing RowMapper Against a Real Database

A mocked `ResultSet` does not test:

- Whether SQL returns the expected aliases.
- How the database driver converts types.
- How `NULL` columns are represented.
- How timestamps and timezones are interpreted.
- Whether `JOIN` queries create duplicate rows.
- Whether mapping is compatible with the real schema.

Use an embedded database or Testcontainers to test the query and mapper together.

Example workflow:

1. Create a test schema with columns matching real data types.
2. Insert valid, `NULL`, zero, and boundary-value records.
3. Execute a `JdbcTemplate` query with the `RowMapper`.
4. Assert each field and data type.
5. Run `JOIN` queries to verify aliases.
6. Verify row order and counts.
7. Test behavior against a production-like driver/database where type semantics differ.

H2 is helpful for fast tests, though it cannot fully replace a production database if SQL, JSON, UUID, timestamp, or numeric semantics differ. For driver-dependent mappings, Testcontainers lets tests run closer to the real environment.

## 28. Testing RowMapper in Spring Batch

When the mapper is used by `JdbcCursorItemReader`, test the reader as well:

~~~java
@Bean
JdbcCursorItemReader<CustomerRow> customerReader(
        DataSource dataSource,
        CustomerRowMapper customerRowMapper) {

    return new JdbcCursorItemReaderBuilder<CustomerRow>()
        .name("customerReader")
        .dataSource(dataSource)
        .sql("""
            SELECT customer_id, full_name, email
            FROM customer
            ORDER BY customer_id
            """)
        .rowMapper(customerRowMapper)
        .saveState(true)
        .build();
}
~~~

A Step integration test can verify:

- The reader opens the query.
- `RowMapper` builds the expected items.
- The processor receives the mapped objects.
- The writer persists the expected data.
- `StepExecution` `readCount` and `writeCount` match expectations.
- The cursor is closed when the Step ends.

Use `spring-batch-test` and `JobLauncherTestUtils` to run the real Step when verifying `JobRepository`, transactions, and lifecycle.

### Testing Restart as Well

`RowMapper` does not hold checkpoints, yet mapping must still behave deterministically when the reader restarts. Tests should run the Step partially, force a failure after a committed chunk, restart the same `JobInstance`, and confirm subsequent items have accurate values.

If the query or schema changes between two runs, the same row can be mapped differently. Manage query/schema versions and source data consistently with restartability.

## 29. RowMapper in Partitioning and Parallel Execution

In partitioning, multiple workers can share the same singleton `RowMapper` if the mapper is stateless and its dependencies are thread-safe. Each worker has its own reader and `ExecutionContext`.

A mapper with a `currentRow` field or shared buffer can cause race conditions:

~~~java
public class UnsafeMapper implements RowMapper<Customer> {
    private Customer lastCustomer;

    @Override
    public Customer mapRow(ResultSet rs, int rowNum)
            throws SQLException {
        lastCustomer = new Customer(
            rs.getLong("id"),
            rs.getString("name")
        );
        return lastCustomer;
    }
}
~~~

The `lastCustomer` field is unnecessary. Return a new object directly:

~~~java
@Override
public Customer mapRow(ResultSet rs, int rowNum)
        throws SQLException {
    return new Customer(
        rs.getLong("id"),
        rs.getString("name")
    );
}
~~~

If the mapper uses a `DateTimeFormatter`, `ObjectMapper`, or converter, use an immutable/thread-safe instance or create local per-call state. Never share a mutable `SimpleDateFormat` across threads.

### Singleton Mapper and StepScope Reader

A common pattern:

- `RowMapper` is a stateless singleton.
- `JdbcCursorItemReader` is `@StepScope` when it needs `JobParameters`.
- Each partition gets its own reader.
- `DataSource` and the connection pool are managed at application scope.
- An immutable DTO is created per row.

This separation minimizes mutable state in the pipeline and clarifies ownership.

## 30. Do Not Use RowMapper to Accumulate Data

A common mistake is storing a list of items inside a `RowMapper` field to aggregate multiple rows:

~~~java
public class BadOrderMapper implements RowMapper<Order> {

    private final List<OrderLine> lines = new ArrayList<>();

    @Override
    public Order mapRow(ResultSet rs, int rowNum)
            throws SQLException {
        // Add line to field and return Order when the last row is seen.
        return null;
    }
}
~~~

This design violates the `RowMapper` contract. The mapper is invoked once per row and must return the object for the current row. It cannot know where a `JOIN` group ends unless it drives the cursor itself or keeps out-of-contract state.

When you need to combine multiple rows:

- Use `ResultSetExtractor` in Spring JDBC.
- Use SQL aggregation.
- Use a flat row DTO and group in a query-scoped component.
- Use an aggregating processor or service if data is chunked with clear grouping rules.

Never keep group state inside a singleton `RowMapper`.

## 31. Mapping Projections vs. Domain Entities

`RowMapper` usually pairs well with read DTOs/projections. You do not need to create a JPA entity for every query.

A projection can contain only the columns needed for the batch:

~~~java
public record PaymentExportRow(
    long paymentId,
    String accountNumberMasked,
    BigDecimal amount,
    LocalDate settlementDate
) {
}
~~~

Advantages:

- No lazy-loading behavior dragged along.
- No persistence context required.
- Queries only the columns needed.
- Objects can be immutable.
- Mapping is easy to test and stable against the SQL contract.

If an entity must be updated, convert the projection into a command/domain object inside the processor or service. Do not use `RowMapper` to manage entity lifecycles like an ORM.

## 32. Versioning the Mapping Contract

A Job may restart after a new application version has been deployed. If SQL aliases, enum mappings, or data types change, the same `JobInstance` might interpret data under different rules between the initial run and restart.

Considerations:

- Query version.
- Schema version.
- Enum code compatibility.
- Timezone conversion.
- Decimal scale.
- Nullability.
- Sort key and paging order.
- Projection changes.

If a change affects business results, you can store a mapping version or batch version in `JobParameters`/`ExecutionContext`. On restart, verify version compatibility or fail with a clear error message.

Never silently change how a column is interpreted while older Jobs can still restart.

## 33. RowMapper Performance

`RowMapper` is called once per row, so operations inside it should be lean and have predictable cost.

Recommended practices:

- Read only required columns.
- Use an explicit SQL projection instead of `SELECT *`.
- Use stable aliases.
- Reuse immutable converters.
- Avoid instantiating heavy formatters or parsers per row if they can be safely reused.
- Avoid issuing extra queries per row.
- Bound LOB and JSON sizes.
- Use appropriate fetch size/page size.
- Measure performance on representative data.

Do not optimize by keeping a shared mutable object to avoid allocations. Creating a new object per row is the natural semantics of a mapper; the JVM optimizes short-lived allocations very well. Prioritize correctness and clarity first, then profile real bottlenecks.

### Avoiding N+1 Queries in the Mapper

If every `mapRow` calls a repository to fetch extra information, a 100,000-row query triggers 100,000 additional queries. This is typically slow and difficult to manage transactionally.

Instead, use a `JOIN`, batch key queries, or a batch enrichment step. If supplemental data can change, snapshot it or define a clear consistency policy.

## 34. Immutable RowMapper Design Checklist

Before using a mapper in a batch job, check:

1. **Projection:** which columns and aliases does the query return?
2. **One row:** which single object corresponds to one SQL row?
3. **State:** does the mapper have mutable fields? If so, are they truly needed?
4. **Output:** is the object deeply immutable or does it require defensive copies?
5. **SQL NULL:** are wrappers, `wasNull`, or invariants used appropriately?
6. **Types:** how are `BigDecimal`, enums, dates/times, UUIDs, JSON, and LOBs converted?
7. **JOIN:** does one row map to one object, or do multiple rows need grouping?
8. **Resources:** does the returned object depend on `ResultSet`/`Connection`?
9. **Errors:** is invalid data failed, skipped, or routed to rejects?
10. **Concurrency:** are the mapper and its dependencies safe for concurrent use?
11. **Restart:** is the mapping contract stable across initial runs and restarts?
12. **Tests:** are unit tests, SQL integration tests, and Step tests in place?

## 35. Common Pitfalls

### Storing Current Row Data in Fields

A singleton mapper can leak data from previous calls or race across threads. Use local variables and return new objects.

### Returning Mutable Objects Modified by Multiple Components

A processor might mutate an item and affect other components. Use immutable records/classes or make explicit copies.

### Using final Alone on Collections

A `final` field only locks the reference. Use `List.copyOf`, `Map.copyOf`, or defensive copies for arrays and nested objects.

### Forgetting wasNull with Primitive Getters

SQL `NULL` silently becomes `0` or `false`. Use wrapper types via `getObject` or call `wasNull` immediately after the getter.

### Converting Money Through double

Can lose decimal precision. Use `getBigDecimal`.

### Using Duplicate Column Names in JOINs

The mapper may read the wrong column label. Use distinct aliases and explicit `SELECT` projections.

### Calling rs.next Inside mapRow

The framework manages the cursor. The mapper must never advance the `ResultSet`.

### Closing ResultSet or Connection Inside the Mapper

Resources belong to `JdbcTemplate` or the reader. Let the framework manage their lifecycle.

### Keeping Blob/Clob/Streams in Items

The object may depend on a closed connection. Materialize the data safely or use a dedicated streaming workflow.

### Aggregating Parent-Child Rows Using RowMapper Fields

The mapper does not know group boundaries and is not thread-safe. Use `ResultSetExtractor` or an aggregation component.

### Calling Databases or APIs Inside mapRow

Causes N+1 queries and repeatable side effects on retry. Enrich in the query or in a batched processor step.

### Using Automatic Mappers Without Testing Nulls/Types

Matching property names do not guarantee SQL `NULL`, enum, or timestamp semantics. Test with the real driver and database.

## 36. Process for Implementing an Immutable RowMapper

You can follow this sequence:

1. **Design the SQL projection:** list needed columns, clear aliases, and a stable order.
2. **Create an immutable DTO:** use a record or `final` class with a complete constructor.
3. **Write a stateless mapper:** hold no row state, `ResultSet`, or cursor in fields.
4. **Map nulls deliberately:** use wrappers/`getObject` or `wasNull` immediately after getters.
5. **Convert types explicitly:** `BigDecimal`, `java.time`, enums, UUIDs, JSON, and LOBs matching the schema.
6. **Handle JOINs with the right abstraction:** `RowMapper` for one row; `ResultSetExtractor` for combining multiple rows into one result.
7. **Register the mapper:** can be a singleton if the mapper and dependencies are thread-safe.
8. **Connect to the Batch reader:** the reader owns checkpoints and resources; the mapper only maps.
9. **Test:** mock `ResultSet` for mapping logic, database tests for driver/SQL, and Step tests for lifecycle.
10. **Keep the contract stable:** manage schema/query changes while older Jobs can still restart.

## 37. Key Takeaways

- `RowMapper.mapRow` receives the current `ResultSet` row and returns one object.
- `RowMapper` must not call `rs.next()`, close `ResultSet`, or retain the cursor.
- Mappers should be stateless and never store current row data in fields.
- Output objects should be immutable using records or `final` classes with `final` fields.
- Collections and arrays require defensive copies for deep immutability.
- SQL `NULL` must be distinguished from zero/false using wrappers or `wasNull`.
- Use `BigDecimal` for `DECIMAL` and `java.time` types for dates and times.
- Enums, UUIDs, and JSON need explicit mapping; do not silently default unrecognized codes.
- One-row-per-object `JOIN`s fit `RowMapper`; multi-row parent-child aggregation should use `ResultSetExtractor` or an aggregation step.
- `JdbcCursorItemReader` and `JdbcPagingItemReader` manage cursors/pages/checkpoints; `RowMapper` does not own restart state.
- A stateless mapper can be a shared singleton if dependencies are thread-safe.
- Never call APIs/databases, write files, or produce side effects inside `mapRow`.
- Never return objects tied to a `ResultSet` or closed connection.
- Test the mapper standalone, against real SQL/drivers, and in Step integration tests as needed.
- Keep the mapping contract stable across the lifetime of restartable `JobInstance`s.

An immutable `RowMapper` ensures each database row is turned into an independent, predictable, and safely reusable data snapshot. When the mapper holds no state, output objects protect their data, and the reader owns checkpoints and resources, JDBC processing in Spring Batch becomes easier to test, easier to scale, and more reliable.

