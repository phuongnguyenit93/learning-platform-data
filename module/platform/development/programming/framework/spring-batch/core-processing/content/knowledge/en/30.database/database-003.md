# RowMapper and Domain Mappers in Spring Batch

In Spring Batch, a reader typically fetches data from a database and converts each result row into an object for the processor and writer to handle. For readers built on Spring JDBC, RowMapper handles the step of converting a row in a ResultSet into a Java object. After the read step, the application sometimes also needs to transform that persistence object into a domain model with business meaning. This second task is commonly called domain mapping.

These two types of mappers are related but have distinct responsibilities. RowMapper understands JDBC row structure; the domain mapper understands the business model and rules. Separating responsibilities properly makes the reader easier to test, prevents the processor from depending on database column structures, and allows the batch job to evolve schema or domain models with less impact.

## 1. What is RowMapper?

RowMapper is a Spring JDBC interface used to map a single row in a ResultSet into a Java object. The interface has one method:

~~~java
public interface RowMapper<T> {
    T mapRow(ResultSet rs, int rowNum) throws SQLException;
}
~~~

Spring calls mapRow for each row returned by the query. Parameters:

- rs is the ResultSet pointing to the current row.
- rowNum is the row sequence number in the result, starting from 0.
- The return value is the object representing that row.

RowMapper does not call rs.next(). ResultSet iteration is managed by JdbcTemplate or the reader. The mapper only reads columns from the current row and constructs the object. Nor is it responsible for closing the ResultSet, Statement, or Connection; resource lifecycle belongs to the component executing the query.

For example, a row in the orders table can be mapped into OrderRow:

~~~java
public record OrderRow(
    long id,
    String customerId,
    BigDecimal total,
    LocalDate businessDate
) {}
~~~

Corresponding RowMapper:

~~~java
public class OrderRowMapper implements RowMapper<OrderRow> {

    @Override
    public OrderRow mapRow(ResultSet rs, int rowNum) throws SQLException {
        return new OrderRow(
            rs.getLong("id"),
            rs.getString("customer_id"),
            rs.getBigDecimal("total"),
            rs.getObject("business_date", LocalDate.class)
        );
    }
}
~~~

Each row creates a new object. The reader can pass that object to the processor for validation, enrichment, or further transformation.

## 2. Where is RowMapper used in Spring Batch?

Readers based on Spring JDBC typically accept a RowMapper to convert query data into items:

- JdbcCursorItemReader reads through a JDBC cursor.
- JdbcPagingItemReader reads page by page using paginated queries.
- JdbcTemplate also uses RowMapper when querying data outside Spring Batch readers.

Example JdbcCursorItemReader configuration:

~~~java
@Bean
@StepScope
JdbcCursorItemReader<OrderRow> orderReader(DataSource dataSource) {
    return new JdbcCursorItemReaderBuilder<OrderRow>()
        .name("orderReader")
        .dataSource(dataSource)
        .sql("""
            select id, customer_id, total, business_date
            from orders
            where status = ?
            order by id
            """)
        .preparedStatementSetter(ps -> ps.setString(1, "READY"))
        .rowMapper(new OrderRowMapper())
        .fetchSize(500)
        .saveState(true)
        .build();
}
~~~

In this configuration, the reader manages query execution and fetching each row; OrderRowMapper only converts the current row into OrderRow. The reader does not need to know how the domain model is built downstream.

With JdbcPagingItemReader, RowMapper plays the same role. The difference lies in how the reader retrieves data by page, not how a single row is mapped:

~~~java
@Bean
@StepScope
JdbcPagingItemReader<OrderRow> pagingOrderReader(
        DataSource dataSource,
        PagingQueryProvider queryProvider) {

    return new JdbcPagingItemReaderBuilder<OrderRow>()
        .name("pagingOrderReader")
        .dataSource(dataSource)
        .queryProvider(queryProvider)
        .pageSize(500)
        .rowMapper(new OrderRowMapper())
        .saveState(true)
        .build();
}
~~~

RowMapper does not determine page size, sort keys, or checkpoints. Those parts belong to the paging reader's configuration and lifecycle.

## 3. Writing a custom RowMapper

A custom RowMapper is suitable when mapping has explicit rules, needs special data type handling, or column names do not match Java property names.

For example, the orders table stores snake_case columns while the Java model uses camelCase:

~~~sql
select
    order_id,
    customer_code,
    gross_amount,
    created_at
from orders
~~~

Mapper:

~~~java
public class OrderRowMapper implements RowMapper<OrderRow> {

    @Override
    public OrderRow mapRow(ResultSet rs, int rowNum) throws SQLException {
        return new OrderRow(
            rs.getLong("order_id"),
            rs.getString("customer_code"),
            rs.getBigDecimal("gross_amount"),
            rs.getTimestamp("created_at").toInstant()
        );
    }
}
~~~

Reading columns by name makes mapping easy to understand and less dependent on column order in SELECT. If the query changes aliases, the mapper and query must be updated together.

Column aliases can be used to clarify data meaning:

~~~sql
select
    o.id as order_id,
    o.customer_code as customer_id,
    o.gross_amount as total_amount
from orders o
~~~

Then the mapper reads the exact aliases:

~~~java
return new OrderRow(
    rs.getLong("order_id"),
    rs.getString("customer_id"),
    rs.getBigDecimal("total_amount")
);
~~~

Aliases are especially useful when joining multiple tables that share column names like id, status, or created_at.

## 4. BeanPropertyRowMapper and limitations of automatic mapping

Spring JDBC provides BeanPropertyRowMapper to map columns by name to Java properties. By default, the mapper can convert underscore-separated column names to camelCase, such as customer_id to customerId.

~~~java
RowMapper<OrderBean> mapper =
    new BeanPropertyRowMapper<>(OrderBean.class);
~~~

The Java model needs compatible properties and an instantiation mechanism supported by the mapper:

~~~java
public class OrderBean {

    private long id;
    private String customerId;
    private BigDecimal total;

    public OrderBean() {
    }

    public long getId() {
        return id;
    }

    public void setId(long id) {
        this.id = id;
    }

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public void setTotal(BigDecimal total) {
        this.total = total;
    }
}
~~~

Automatic mapping reduces boilerplate code, but does not replace schema/model design. Limitations to consider:

- Column and property names must match according to the mapping convention.
- The model must support the instantiation mechanism required by the mapper.
- Automatic mapping does not express business rules well.
- Join queries may return duplicate column names or ambiguous aliases.
- Special data types and nulls may need explicit handling.
- Column/property name mismatches may only surface when the query executes.

For immutable objects, constructor-based mapping, or records, consider DataClassRowMapper in supported Spring Framework versions. When mapping involves many rules or requires high clarity, a custom RowMapper is usually easier to read and control.

## 5. Handling SQL NULL properly

A common mistake is using primitive getters without checking for SQL NULL. For example, ResultSet.getLong() returns 0 if the column is SQL NULL. If 0 is also a valid value, the application cannot distinguish between the two cases without calling wasNull().

Example:

~~~java
long customerNumber = rs.getLong("customer_number");
Long nullableCustomerNumber =
    rs.wasNull() ? null : customerNumber;
~~~

With JDBC drivers supporting JDBC 4.1 or higher, you can use getObject with a wrapper type:

~~~java
Long customerNumber = rs.getObject("customer_number", Long.class);
Integer retryCount = rs.getObject("retry_count", Integer.class);
~~~

For reference types such as String, BigDecimal, and Timestamp, getters typically return null if the SQL column is NULL. However, clearly define whether the domain model allows null. If a required field is null, you can create a persistence row holding nullable values and let the domain mapper detect it and throw a meaningful validation error.

Do not blindly replace every null with 0, an empty string, or a default date if doing so alters business meaning. Some fields may need defaults, but defaults should be expressed in explicit domain rules.

## 6. Converting date/time and numeric data types

JDBC supports many SQL and Java types. Use Java types that accurately reflect the data semantics:

| SQL type | Commonly used Java type | Notes |
| --- | --- | --- |
| DATE | LocalDate | Date only, without time or timezone |
| TIME | LocalTime | Time of day only |
| TIMESTAMP | LocalDateTime or Instant | Must define the data's timezone convention |
| DECIMAL/NUMERIC | BigDecimal | Avoid converting to double for monetary amounts |
| BIGINT | Long or long | Choose nullable or non-null per schema |
| BOOLEAN | Boolean or boolean | Check null if the column allows it |

Example:

~~~java
LocalDate businessDate =
    rs.getObject("business_date", LocalDate.class);

LocalDateTime createdAt =
    rs.getObject("created_at", LocalDateTime.class);

BigDecimal amount = rs.getBigDecimal("amount");
~~~

Do not assume all drivers handle TIMESTAMP, timezones, or vendor-specific types identically. For Oracle, PostgreSQL, or SQL Server, verify the JDBC driver and actual mapping in integration tests.

For currency, use BigDecimal and define scale/rounding in the domain layer. RowMapper should preserve the exact JDBC value; do not round prematurely just because the column is displayed with a fixed number of decimal places.

## 7. Mapping enums and statuses

Databases often store enums as VARCHAR or numeric codes. Do not use Enum.valueOf directly if the data may contain legacy values, aliases, or business codes that differ from enum names.

If the DB stores exact enum names:

~~~java
OrderStatus status =
    OrderStatus.valueOf(rs.getString("status"));
~~~

If the DB stores custom codes:

~~~java
public enum OrderStatus {
    READY("R"),
    PROCESSING("P"),
    COMPLETED("C");

    private final String databaseCode;

    OrderStatus(String databaseCode) {
        this.databaseCode = databaseCode;
    }

    public static OrderStatus fromDatabaseCode(String code) {
        return Arrays.stream(values())
            .filter(value -> value.databaseCode.equals(code))
            .findFirst()
            .orElseThrow(() ->
                new IllegalArgumentException("Unknown order status: " + code)
            );
    }
}
~~~

RowMapper calls the code conversion method:

~~~java
OrderStatus status =
    OrderStatus.fromDatabaseCode(rs.getString("status"));
~~~

Unknown code errors should be categorized intentionally. If invalid data belongs to a single record and business rules allow discarding it, domain mapping can throw a dedicated validation exception for the step to handle via a skip policy. If an unknown code indicates an incompatible schema or deployment, the step may need to fail to avoid skipping records en masse.

## 8. Mapping joined data and relationships

A join query can return columns from multiple tables. Alias columns to clearly distinguish their source:

~~~sql
select
    o.id as order_id,
    o.total as order_total,
    c.id as customer_id,
    c.name as customer_name
from orders o
join customers c on c.id = o.customer_id
~~~

RowMapper can produce a flat read model:

~~~java
public record OrderWithCustomerRow(
    long orderId,
    BigDecimal orderTotal,
    String customerId,
    String customerName
) {}
~~~

~~~java
public class OrderWithCustomerRowMapper
        implements RowMapper<OrderWithCustomerRow> {

    @Override
    public OrderWithCustomerRow mapRow(ResultSet rs, int rowNum)
            throws SQLException {
        return new OrderWithCustomerRow(
            rs.getLong("order_id"),
            rs.getBigDecimal("order_total"),
            rs.getString("customer_id"),
            rs.getString("customer_name")
        );
    }
}
~~~

Do not run an additional query per row inside mapRow to fetch customer or related collections. That creates N+1 queries: one query reading orders followed by an extra query for each order. Consider joins, batch lookups, or a separate controlled enrichment step.

If a join produces multiple rows for the same parent aggregate, a simple RowMapper will not automatically group those rows into an aggregate with child collections. You can use ResultSetExtractor to process the entire ResultSet, or let the query return a flat read model and group it in a separate step. Choose the tool based on the shape of the data.

## 9. How RowMapper and ResultSetExtractor differ

RowMapper is suitable when each row corresponds to an independent item. ResultSetExtractor is suitable when you need to inspect the entire ResultSet to build a single object or composite structure:

| Component | Processing unit | Example |
| --- | --- | --- |
| RowMapper | One row | One OrderRow |
| ResultSetExtractor | Entire ResultSet | One Order with a list of multiple order item lines |
| RowCallbackHandler | One row, no object returned | Reading and writing each row directly to a sink |

In Spring Batch, a reader normally wants to return one item per read() call, so RowMapper fits naturally with cursor/paging readers. If each item needs to aggregate multiple rows, define the aggregate boundary in the query or use a reader/custom component that explicitly groups data.

Do not use RowMapper to call rs.next() yourself to aggregate multiple rows. Doing so breaks the contract because the reader/JdbcTemplate manages the ResultSet cursor position.

## 10. What is a domain mapper?

A domain mapper transforms data from a technical representation or persistence model into a domain model used by the business logic. It is generally not a Spring JDBC interface; it is an application-defined component dictated by architecture.

For example, RowMapper creates a DTO reflecting database data:

~~~java
public record OrderRow(
    long id,
    String customerCode,
    BigDecimal total,
    String statusCode
) {}
~~~

The domain mapper converts that DTO into a domain object:

~~~java
public class OrderDomainMapper {

    public Order toDomain(OrderRow row) {
        CustomerId customerId = CustomerId.of(row.customerCode());
        Money total = Money.of(row.total(), Currency.getInstance("VND"));
        OrderStatus status = OrderStatus.fromDatabaseCode(row.statusCode());

        return Order.rehydrate(
            OrderId.of(row.id()),
            customerId,
            total,
            status
        );
    }
}
~~~

In this example:

- RowMapper understands column names and JDBC types.
- OrderRow reflects the read data.
- The domain mapper converts codes and values into value objects.
- The domain model protects invariants and expresses business meaning.

Separating the domain mapper keeps the domain model unaware of SQL column names or ResultSet.

## 11. Should you map ResultSet directly into a domain object?

There is no strict rule that RowMapper must always produce an intermediate DTO. If the query is simple and the domain object has an appropriate constructor/factory, RowMapper can create the domain object directly:

~~~java
public class OrderDomainRowMapper implements RowMapper<Order> {

    @Override
    public Order mapRow(ResultSet rs, int rowNum) throws SQLException {
        return Order.rehydrate(
            OrderId.of(rs.getLong("id")),
            CustomerId.of(rs.getString("customer_id")),
            Money.of(
                rs.getBigDecimal("total"),
                Currency.getInstance("VND")
            ),
            OrderStatus.fromDatabaseCode(rs.getString("status"))
        );
    }
}
~~~

This approach eliminates one mapping layer and works well when the domain object itself is the item the batch needs to process. However, RowMapper then depends on the domain API and must handle both JDBC conversion and domain instantiation.

Separate persistence DTO and domain mapper when:

- One query/read model may be used by multiple use cases.
- Database schema and domain model evolve at different cadences.
- The domain model has complex invariants or factories.
- Data mapping and business rules need to be tested separately.
- Multiple data sources produce the same domain object.

Direct mapping is fine when the data is simple, the mapping is clear, and it does not create hard-to-manage coupling. The goal is clear separation of responsibilities, not adding extra layers for every case.

## 12. Where do RowMapper and domain mapper sit in a batch pipeline?

A common pipeline:

~~~text
Database
   |
   v
JdbcCursorItemReader / JdbcPagingItemReader
   |
   v
RowMapper
   |
   v
Persistence row / read DTO
   |
   v
Domain mapper
   |
   v
Domain object
   |
   v
ItemProcessor
   |
   v
ItemWriter
~~~

The domain mapper can be placed inside the processor if transformation is part of item processing:

~~~java
public class OrderProcessor
        implements ItemProcessor<OrderRow, EnrichedOrder> {

    private final OrderDomainMapper domainMapper;
    private final OrderEnrichmentService enrichmentService;

    public OrderProcessor(
            OrderDomainMapper domainMapper,
            OrderEnrichmentService enrichmentService) {
        this.domainMapper = domainMapper;
        this.enrichmentService = enrichmentService;
    }

    @Override
    public EnrichedOrder process(OrderRow row) {
        Order order = domainMapper.toDomain(row);
        return enrichmentService.enrich(order);
    }
}
~~~

If the reader can return the domain object directly, the processor only needs to handle enrichment. If mapping can fail due to invalid record data, classify exceptions clearly to retry, skip, or fail according to business rules.

## 13. Do not put heavy business logic in RowMapper

RowMapper is invoked while reading each row. It should focus on reading columns and basic data conversion. Avoid doing the following inside mapRow:

- Calling HTTP services or message brokers.
- Running additional queries per row to load relationships.
- Writing to the database or causing side effects.
- Executing multi-step business workflows.
- Holding ResultSet, Connection, or Statement in fields for later use.
- Accumulating all items in a global collection.

If the mapper calls an API for every row, the reader becomes an integration orchestrator and can cause N+1 network calls. Retries/re-reads could also duplicate side effects. Move enrichment to a processor or dedicated service where retry and transaction behavior can be intentionally configured.

RowMapper should be fast enough and stateless. Create a new object for the current row, return it, and let the reader continue.

## 14. RowMapper must be stateless and thread-safe

RowMapper is typically configured as a reusable object in a reader or JdbcTemplate. If multiple threads invoke the mapper concurrently, mutable fields can be shared and cause one row's data to bleed into another.

Avoid:

~~~java
public class UnsafeOrderRowMapper implements RowMapper<OrderRow> {

    private String currentCustomer;

    @Override
    public OrderRow mapRow(ResultSet rs, int rowNum) throws SQLException {
        currentCustomer = rs.getString("customer_id");
        return new OrderRow(
            rs.getLong("id"),
            currentCustomer,
            rs.getBigDecimal("total"),
            rs.getObject("business_date", LocalDate.class)
        );
    }
}
~~~

Use local variables instead:

~~~java
public class SafeOrderRowMapper implements RowMapper<OrderRow> {

    @Override
    public OrderRow mapRow(ResultSet rs, int rowNum) throws SQLException {
        String customerId = rs.getString("customer_id");
        BigDecimal total = rs.getBigDecimal("total");
        LocalDate date = rs.getObject("business_date", LocalDate.class);

        return new OrderRow(
            rs.getLong("id"),
            customerId,
            total,
            date
        );
    }
}
~~~

A stateless mapper is also easier to test because its output depends solely on the input row. If reference data caching is needed, put the cache in a separate service with clear concurrency control and lifecycle; never use RowMapper fields to hold the current item.

## 15. Handling mapping errors and classifying exceptions

Mapping errors can stem from several causes:

- The query does not return a column the mapper expects.
- A column has SQL NULL while the domain requires non-null.
- An enum/status code value is unrecognized.
- The driver does not support type conversion as assumed.
- Data is malformed or out of bounds.
- Schema and application are incompatible after a deployment.

Do not catch all SQLExceptions and return an empty object. Doing so turns corrupted data into seemingly valid data and makes it hard for processors/writers to detect issues.

Record validation errors can be wrapped in a meaningful exception:

~~~java
public class InvalidOrderRowException extends RuntimeException {
    public InvalidOrderRowException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

However, missing column errors due to a bad query are usually programming/schema bugs and should fail the step. An invalid value in a single record can be skipped if business rules permit. Distinguish these two categories instead of configuring a broad skip for all mapping exceptions.

For checked exceptions like SQLException, Spring JDBC typically passes them through its exception translation mechanism or the reader wraps them into an appropriate exception. Verify the actual exception type the step receives when configuring retry/skip.

## 16. Mapping in JdbcCursorItemReader and restart

RowMapper does not store checkpoints. JdbcCursorItemReader manages the cursor and read state according to the reader's lifecycle. When saveState is enabled, the reader can persist the state needed to restart as configured.

Example:

~~~java
new JdbcCursorItemReaderBuilder<OrderRow>()
    .name("orderReader")
    .dataSource(dataSource)
    .sql("select id, customer_id, total from orders order by id")
    .rowMapper(orderRowMapper)
    .saveState(true)
    .build();
~~~

A good mapper does not rely on rowNum as business identity. rowNum is merely the position in the current result set; changing queries, changing ordering, or restarting the reader can cause that position to cease being a stable record identifier.

If the processor or writer needs to identify records for idempotency, use the primary key/business key from the data row. Do not store the ResultSet object or depend on rowNum for business recovery.

For a cursor reader, database resources are held for the step's lifecycle. RowMapper must not close the connection or ResultSet; doing so can prevent the reader from reading the next row.

## 17. Mapping in JdbcPagingItemReader and sort keys

JdbcPagingItemReader executes multiple queries by page. RowMapper still maps only one row at a time, but the paging reader requires a stable sort key for accurate pagination and restart.

Example query with id as sort key:

~~~sql
select id, customer_id, total
from orders
where status = :status
order by id
~~~

The sort key should be unique or combine multiple columns to create a stable ordering. If sorting by created_at where multiple rows share the same timestamp, add id as a tie-breaker. If source data can change while the job runs, understand the impact of inserts/updates on pages.

RowMapper does not solve paging order issues. It only maps the id, customer_id, and total columns. The reader/query provider manages sort keys, page boundaries, and checkpoints.

Do not use rowNum as a paging key because rowNum can reset on each page and is unstable across restarts.

## 18. Domain mapper and domain model invariants

The domain mapper is where technical data becomes business concepts. It can construct value objects, validate invariants, or call a factory to reconstruct an aggregate from persisted state.

Example Money:

~~~java
public record Money(BigDecimal amount, Currency currency) {

    public Money {
        Objects.requireNonNull(amount);
        Objects.requireNonNull(currency);
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("Amount cannot be negative");
        }
    }
}
~~~

Domain mapper:

~~~java
public class PaymentRowMapper {

    public Payment toDomain(PaymentRow row) {
        Money amount = new Money(
            row.amount(),
            Currency.getInstance(row.currencyCode())
        );

        return Payment.rehydrate(
            PaymentId.of(row.paymentId()),
            amount,
            PaymentStatus.fromCode(row.statusCode())
        );
    }
}
~~~

If the domain constructor/factory rejects the data, the mapper must let the exception clearly indicate an invalid record. Do not bypass invariants to construct an inconsistent object just to avoid a batch error.

Some domain models distinguish factories for creating new entities from rehydrate methods for restoring persisted state. The domain mapper should use the API meant for that purpose rather than calling setters field by field and bypassing invariants.

## 19. Mapping one-to-many relationships

An order can have multiple order lines. A join query returns one row per line, so the same order ID appears multiple times:

~~~sql
select
    o.id as order_id,
    o.customer_id,
    l.id as line_id,
    l.product_id,
    l.quantity
from orders o
join order_line l on l.order_id = o.id
order by o.id, l.id
~~~

RowMapper can produce an OrderLineRow for each row. But if the item needs to be the entire Order with its list of lines, rows must be grouped by order ID.

ResultSetExtractor can be used when the query returns the full group needed:

~~~java
Map<Long, OrderAggregateRow> orders =
    jdbcTemplate.query(sql, rs -> {
        Map<Long, OrderAggregateRow> result = new LinkedHashMap<>();
        while (rs.next()) {
            long orderId = rs.getLong("order_id");
            OrderAggregateRow order = result.computeIfAbsent(
                orderId,
                id -> new OrderAggregateRow(
                    id,
                    rsString(rs, "customer_id")
                )
            );
            order.addLine(
                rs.getLong("line_id"),
                rs.getString("product_id"),
                rs.getInt("quantity")
            );
        }
        return result;
    });
~~~

This is a conceptual example; the rsString helper must handle SQLException properly in real code. For large batches, do not load the entire table into a Map at once. You can query by order groups, use a custom reader that aggregates one aggregate at a time, or use an appropriate staging step.

The batch item boundary should be decided upfront: one row, one order, or a group of records. That boundary affects commit interval, retry, skip, and memory usage.

## 20. Unit testing RowMapper independently

RowMapper can be unit tested without launching the entire job. You can use a Mock ResultSet or a real ResultSet from a test database. Testing with a real database is often more useful when verifying data types and JDBC driver behavior.

Cases to verify:

- Required columns are mapped accurately.
- SQL NULL is preserved as null or handled per defined rules.
- Decimals do not lose precision.
- Date/time converts to the right Java types.
- Valid enums/codes are mapped correctly.
- Unknown enums/codes produce a meaningful exception.
- Query aliases match the column names the mapper reads.
- Each invocation returns a new object, without reusing a mutable object from the previous row.

Example mapping logic test:

~~~java
@Test
void mapsOrderColumns() throws SQLException {
    ResultSet rs = mock(ResultSet.class);
    when(rs.getLong("id")).thenReturn(42L);
    when(rs.getString("customer_id")).thenReturn("C-100");
    when(rs.getBigDecimal("total"))
        .thenReturn(new BigDecimal("125.50"));
    when(rs.getObject("business_date", LocalDate.class))
        .thenReturn(LocalDate.of(2026, 11, 15));

    OrderRow row = new OrderRowMapper().mapRow(rs, 0);

    assertThat(row.id()).isEqualTo(42L);
    assertThat(row.customerId()).isEqualTo("C-100");
    assertThat(row.total()).isEqualByComparingTo("125.50");
    assertThat(row.businessDate())
        .isEqualTo(LocalDate.of(2026, 11, 15));
}
~~~

Mock tests verify that the mapper calls the expected columns and converts according to assumptions. They do not verify that the real driver returns the expected data types; supplement with integration tests for important queries and schemas.

## 21. Testing the domain mapper

The domain mapper should be tested independently of JDBC. The input is a persistence DTO or row object; the output is a domain object. This lets you verify invariants and transformation rules without mocking ResultSet.

Example:

~~~java
@Test
void mapsPersistenceRowToOrderDomain() {
    OrderRow row = new OrderRow(
        42L,
        "C-100",
        new BigDecimal("125.50"),
        "READY"
    );

    Order order = new OrderDomainMapper().toDomain(row);

    assertThat(order.id()).isEqualTo(OrderId.of(42L));
    assertThat(order.customerId()).isEqualTo(CustomerId.of("C-100"));
    assertThat(order.total().amount())
        .isEqualByComparingTo("125.50");
    assertThat(order.status()).isEqualTo(OrderStatus.READY);
}
~~~

Additional tests should verify:

- Invalid currency codes are rejected.
- Unsupported status codes produce a clear error.
- Null required values are handled according to domain rules.
- Domain factories do not allow creating aggregates that violate invariants.
- Mapping does not mutate the input persistence object.

## 22. Integration testing the reader with RowMapper

Unit testing RowMapper does not verify that the reader queries the right data. An integration test with a test database can create tables and fixture data, run the step, and inspect the items read and written.

Example test:

1. Insert two valid orders and one order with a status not selected.
2. Configure JdbcPagingItemReader or JdbcCursorItemReader with the query.
3. Use the custom RowMapper.
4. Run the step with a test writer that collects items or writes to a target table.
5. Verify exactly two orders are read and values are mapped accurately.
6. Verify the reader closes resources after the step.

For JdbcPagingItemReader, test across more than one page to verify the query provider and sort keys. Use data with sequential IDs as well as duplicate primary sort key cases if the query uses composite sorting.

For JdbcCursorItemReader, verify cursor behavior and transaction configuration against the database/driver in use. Do not rely solely on a mock ResultSet to conclude a reader can restart.

## 23. Mapping and performance in large batches

RowMapper is invoked for every row, so small costs in the mapper can multiply millions of times. Do:

- Avoid unnecessary repeated reflection or introspection in custom mappers.
- Avoid extra queries inside mapRow.
- Do not parse large payloads multiple times if they can be converted once.
- Select only the columns needed.
- Tune fetch size/page size to database and memory capabilities.
- Do not hold every row object in a global collection.
- Use intentional BigDecimal/Date conversions, avoiding unnecessary string formatting/parsing.

BeanPropertyRowMapper is convenient but may carry overhead compared to a simple custom mapper. Do not optimize before measuring; for actual bottlenecks, benchmark query and mapping separately to identify whether the cost lies in the database, network, conversion, or processor.

The domain mapper may also allocate many value objects. That is usually worthwhile to preserve invariants and type safety. If mapping becomes a bottleneck, profile allocation and time before reducing abstractions.

## 24. Common pitfalls when using RowMapper and domain mappers

**Calling rs.next() inside mapRow:** JdbcTemplate/reader already controls the ResultSet cursor. Calling it again skips rows or breaks the read flow.

**Closing ResultSet/Connection inside the mapper:** the mapper does not own the resource. Closing it can prevent the reader from reading the next row.

**Using rowNum as business ID:** rowNum is only the position in the current result set, not a stable record identifier.

**Ignoring SQL NULL:** primitive getters may return 0/false. Use wrapper getObject or wasNull() to distinguish null.

**Using double for money:** can lose precision. Keep BigDecimal and apply rounding within domain rules.

**Using Enum.valueOf for custom DB codes:** enum names may differ from codes stored in the database. Use an explicit code conversion function.

**Putting secondary queries in RowMapper:** causes N+1 queries and prolongs read time. Use joins or separate batch enrichment.

**Keeping mutable fields in the mapper:** multiple rows/threads can corrupt each other's data. Use stateless mappers and local variables.

**Making the domain model depend on ResultSet:** couples the domain layer to JDBC. Use row DTOs and domain mappers when layer separation is needed.

**Mapping all errors to a default object:** hides bad data and can write corrupted records. Classify exceptions into record validation vs. schema/code bugs.

**Using RowMapper to group multiple rows into an aggregate:** RowMapper maps only one row. Use ResultSetExtractor or a reader with explicit aggregate boundaries.

**Assuming the mapper handles checkpoints:** RowMapper does not save reader state. The reader and ExecutionContext are responsible for restart.

## 25. Mapping design workflow for production batches

First, determine whether the item the batch needs to process is a database row, a read DTO, or a domain aggregate. Design the SELECT with clear aliases and fetch only required columns. Write a custom RowMapper when you need control over nulls, data types, enums, or join mapping; use BeanPropertyRowMapper for simple models matching naming conventions.

Next, decide whether a domain mapper is needed. If the batch only performs simple data transfers, RowMapper can construct the domain object directly. If the persistence shape differs from the domain model or the domain has invariants/value objects, create an intermediate DTO and use a domain mapper. Keep RowMapper stateless, with no extra queries and no side effects.

Finally, test both mapping layers independently and integration-test the reader against a real database/driver. Cover SQL NULL, date/time types, decimals, enums, aliases, joins, paging, and restarts. Measure performance on representative data before optimizing the mapper.

RowMapper converts a JDBC row into an object; the domain mapper converts a data object into a business concept. In Spring Batch, these two steps let the reader focus on fetching data, the processor on business processing, and the writer on output. With clear boundaries, mapping is easy to test, queries are easy to evolve, and batch jobs depend less on database schema details.
