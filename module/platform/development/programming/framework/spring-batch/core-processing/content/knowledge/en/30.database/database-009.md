# SqlParameterSourceProvider

When writing data with JDBC in Spring Batch, `JdbcBatchItemWriter` needs to convert each Java item into SQL parameters to execute `INSERT`, `UPDATE`, or `MERGE` statements. For SQL using named parameters like `:orderId`, the writer needs an `SqlParameterSource` object holding the corresponding value for each parameter name.

In the Spring Batch API, the extension point commonly used for this is officially named **`ItemSqlParameterSourceProvider<T>`**. The provider takes an item and creates an `SqlParameterSource` for it. The lesson title "SqlParameterSourceProvider" is commonly used to refer to this mechanism in the context of batch writers.

The provider is responsible for mapping item data to named SQL parameters. It does not open connections, execute SQL itself, manage transactions, or determine chunk size. Those responsibilities belong to `JdbcBatchItemWriter`, `NamedParameterJdbcTemplate`, and the step's transaction manager.

## 1. What is SqlParameterSource?

`SqlParameterSource` is a Spring JDBC abstraction used to supply parameter values for named SQL. Instead of passing values positionally with `?`, the SQL statement can assign a name to each value:

```sql
insert into orders(order_id, customer_id, amount)
values (:orderId, :customerId, :amount)
```

An `SqlParameterSource` provides values for the names `orderId`, `customerId`, and `amount`. Spring JDBC uses these names to bind values into the SQL statement before invoking a JDBC `PreparedStatement`.

Common implementations:

- `BeanPropertySqlParameterSource`: retrieves values from JavaBean properties.
- `MapSqlParameterSource`: retrieves values from an explicitly configured map while allowing SQL types to be declared.
- `EmptySqlParameterSource`: represents an empty parameter source for statements needing no dynamic values.

In Spring Batch, `ItemSqlParameterSourceProvider<T>` connects pipeline items to this `SqlParameterSource` abstraction.

## 2. What does ItemSqlParameterSourceProvider<T> do?

The Spring Batch interface has a core method:

```java
public interface ItemSqlParameterSourceProvider<T> {

    SqlParameterSource createSqlParameterSource(T item);
}
```

The provider receives an item of type `T` and returns the SQL parameter source for that item. `JdbcBatchItemWriter` invokes the provider when preparing a batch update to obtain parameters for each item.

Example:

```text
Order item
  orderId = 1001
  customerId = C001
  amount = 250.00
       |
       v
ItemSqlParameterSourceProvider
       |
       v
SqlParameterSource
  orderId    -> 1001
  customerId -> C001
  amount     -> 250.00
       |
       v
NamedParameterJdbcTemplate
       |
       v
PreparedStatement parameters
```

The provider only builds the parameter mapping. The writer remains responsible for executing the batch update with the configured SQL.

## 3. Where is the provider used in Spring Batch?

The typical use case is `JdbcBatchItemWriter<T>`. The writer receives each item read by the reader and processed by the processor, then converts the item into named parameters to write to the database.

```mermaid
flowchart LR
    A[ItemReader] --> B[ItemProcessor]
    B --> C[JdbcBatchItemWriter]
    C --> D[ItemSqlParameterSourceProvider]
    D --> E[SqlParameterSource]
    E --> F[NamedParameterJdbcTemplate]
    F --> G[Database]
```

The provider is usually configured when building the writer via the `itemSqlParameterSourceProvider(...)` builder method. The builder also lets you supply a `DataSource` or `NamedParameterJdbcTemplate`, SQL, and update-count assertion options.

In many Spring Batch versions, the API uses the name `ItemSqlParameterSourceProvider<T>`, rather than a standalone Spring JDBC interface named `SqlParameterSourceProvider`. `SqlParameterSource` is a Spring JDBC type; `ItemSqlParameterSourceProvider` is the Spring Batch adapter extension point that accepts an item.

## 4. Using BeanPropertyItemSqlParameterSourceProvider

If the item is a JavaBean with getters matching the named parameter names in SQL, the simplest option is `BeanPropertyItemSqlParameterSourceProvider<T>`.

Example model:

```java
public class OrderRecord {

    private Long orderId;
    private String customerId;
    private BigDecimal amount;

    public Long getOrderId() {
        return orderId;
    }

    public String getCustomerId() {
        return customerId;
    }

    public BigDecimal getAmount() {
        return amount;
    }
}
```

Creating the provider:

```java
ItemSqlParameterSourceProvider<OrderRecord> provider =
        new BeanPropertyItemSqlParameterSourceProvider<>();

SqlParameterSource parameters =
        provider.createSqlParameterSource(orderRecord);
```

This implementation constructs a `BeanPropertySqlParameterSource` around the item. Spring JDBC looks up properties by name, typically through JavaBean getters. For the item above, SQL names `:orderId`, `:customerId`, and `:amount` can be mapped to `getOrderId()`, `getCustomerId()`, and `getAmount()`.

Advantages:

- Less manual mapping code.
- Model property names can directly match SQL parameter names.
- Readable when the item is a DTO dedicated to the database writer.
- Can leverage property type metadata to help determine SQL types.

Limitations:

- SQL depends on model property names.
- If the database schema and model use different names, you must adjust aliases in SQL or write a custom provider.
- The item must expose properties accessible to Spring JDBC.
- Avoid using an entity with many unrelated properties when the writer only needs a subset of data.

## 5. Configuring JdbcBatchItemWriter with bean property provider

Example of a writer writing `OrderRecord` into the `orders` table:

```java
@Bean
public JdbcBatchItemWriter<OrderRecord> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<OrderRecord>()
            .dataSource(dataSource)
            .sql("""
                    insert into orders(order_id, customer_id, amount)
                    values (:orderId, :customerId, :amount)
                    """)
            .itemSqlParameterSourceProvider(
                    new BeanPropertyItemSqlParameterSourceProvider<>())
            .assertUpdates(true)
            .build();
}
```

In this example:

- `.dataSource(dataSource)` provides the datasource to the writer.
- `.sql(...)` declares the SQL statement using named parameters.
- `.itemSqlParameterSourceProvider(...)` converts each item into an `SqlParameterSource`.
- `.assertUpdates(true)` instructs the writer to verify update counts per writer behavior.
- `.build()` creates the configured writer.

Placeholder names in SQL must match readable properties on the item. `:orderId` differs from `:id`; the provider does not automatically infer that those two names mean the same thing.

If using a Java version without text block support, write the SQL as concatenated strings or regular string literals.

## 6. Using MapItemSqlParameterSourceProvider

If items are already `Map<String, Object>`, you can use `MapItemSqlParameterSourceProvider` to turn the map into an SQL parameter source.

Example item:

```java
Map<String, Object> item = new HashMap<>();
item.put("orderId", 1001L);
item.put("customerId", "C001");
item.put("amount", new BigDecimal("250.00"));
```

Provider:

```java
ItemSqlParameterSourceProvider<Map<String, Object>> provider =
        new MapItemSqlParameterSourceProvider<>();

SqlParameterSource parameters = provider.createSqlParameterSource(item);
```

Key names in the map must match named parameters in SQL. If the SQL has `:customerId` while the map only contains key `customer_id`, Spring JDBC will not find the matching value.

The map provider fits when data is already shaped as key/value pairs, such as output from a normalization step, schema-dynamic data, or items assembled from multiple sources. However, maps reduce compile-time type checking and misspelled key errors often surface only when the writer executes.

## 7. Using MapSqlParameterSource directly

You do not have to use `MapItemSqlParameterSourceProvider`. For mappings that need explicit SQL types, default values, or property names differing from SQL names, you can write a provider that returns `MapSqlParameterSource` directly.

Example:

```java
ItemSqlParameterSourceProvider<OrderRecord> provider = item ->
        new MapSqlParameterSource()
                .addValue("orderId", item.getOrderId(), Types.BIGINT)
                .addValue("customerId", item.getCustomerId(), Types.VARCHAR)
                .addValue("amount", item.getAmount(), Types.DECIMAL);
```

This provider creates a new `MapSqlParameterSource` per item. You can specify SQL types explicitly, which is especially helpful when values are `null` or the driver needs explicit type metadata.

Example with a null value:

```java
return new MapSqlParameterSource()
        .addValue("orderId", item.getOrderId(), Types.BIGINT)
        .addValue("note", null, Types.VARCHAR);
```

Without type metadata and with a null value, some drivers or column types may require Spring JDBC to infer or use special binding. Specifying `Types.VARCHAR`, `Types.DECIMAL`, `Types.TIMESTAMP`, etc., reduces ambiguity.

## 8. Writing a custom ItemSqlParameterSourceProvider

When the item model does not directly match SQL names or values need transformation before binding, you can implement the interface.

For example, the item has property `id`, while SQL uses `:orderId`; status enum must be written as a code:

```java
public class OrderSqlParameterSourceProvider
        implements ItemSqlParameterSourceProvider<OrderRecord> {

    @Override
    public SqlParameterSource createSqlParameterSource(OrderRecord item) {
        return new MapSqlParameterSource()
                .addValue("orderId", item.getId(), Types.BIGINT)
                .addValue("customerId", item.getCustomerId(), Types.VARCHAR)
                .addValue("amount", item.getAmount(), Types.DECIMAL)
                .addValue("status", item.getStatus().getCode(), Types.VARCHAR);
    }
}
```

Wiring the provider into the writer:

```java
@Bean
public JdbcBatchItemWriter<OrderRecord> orderWriter(
        DataSource dataSource,
        OrderSqlParameterSourceProvider provider) {

    return new JdbcBatchItemWriterBuilder<OrderRecord>()
            .dataSource(dataSource)
            .sql("""
                    insert into orders(order_id, customer_id, amount, status)
                    values (:orderId, :customerId, :amount, :status)
                    """)
            .itemSqlParameterSourceProvider(provider)
            .build();
}
```

A custom provider is useful when:

- Java property names differ from SQL placeholder names.
- Data from multiple properties needs to be combined.
- Enums must be converted to database codes or strings.
- SQL types need to be declared explicitly.
- Null/default values require business-rule handling.
- Computed parameters must be derived from the item.

Keep mappings focused and easy to test. Avoid putting database queries or API calls inside the provider; the provider should translate items into parameters, not execute infrastructure-dependent business logic.

## 9. Named parameter names must match exactly

Named parameters make SQL easier to read, but names must match between the statement and `SqlParameterSource`.

Correct example:

```sql
update orders
set amount = :amount,
    status = :status
where order_id = :orderId
```

The provider must supply:

```java
new MapSqlParameterSource()
        .addValue("amount", item.getAmount())
        .addValue("status", item.getStatus())
        .addValue("orderId", item.getId());
```

Do not include the `:` prefix in the key name when calling `addValue`. The `:` only appears in SQL; the key in the parameter source is `orderId`, not `:orderId`.

Common mistakes:

| SQL placeholder | Provider key | Result |
|---|---|---|
| `:orderId` | `orderId` | Matches |
| `:orderId` | `order_id` | Mismatch without extra mapping |
| `:customerId` | `:customerId` | Invalid key naming |
| `:amount` | Missing `amount` | Missing parameter error at execution |

Adopt a consistent naming convention, such as camelCase in Java and named placeholders, while database column names can remain snake_case.

## 10. Mapping properties whose names differ from database columns

Database column names do not have to match Java property names. The SQL statement bridges the two sides:

```sql
insert into order_line(order_id, customer_code, net_amount)
values (:id, :customerCode, :amount)
```

If the item provides `getId()`, `getCustomerCode()`, and `getAmount()`, `BeanPropertyItemSqlParameterSourceProvider` can supply those properties. SQL placeholders use Java property names, while the column list on the left uses database column names.

If a property needs transformation or lacks a matching getter, a custom provider can construct custom keys. There is no need to alter the database schema merely so column names match Java field names.

## 11. SQL and Java data types

Spring JDBC can infer many SQL types from Java types, but applications should understand how key types are bound.

| Common Java type | Common SQL type | Notes |
|---|---|---|
| `Long` / `long` | `BIGINT` | IDs or counters |
| `Integer` / `int` | `INTEGER` | Integers |
| `String` | `VARCHAR` or `CHAR` | Length and encoding per schema |
| `BigDecimal` | `DECIMAL` / `NUMERIC` | Suitable for currency; control precision/scale |
| `Boolean` | `BOOLEAN` or DB equivalent | Some databases represent as number/bit |
| `LocalDate` | `DATE` | Support depends on Spring/driver |
| `LocalDateTime` | `TIMESTAMP` | Does not carry timezone itself |
| `Instant` / `OffsetDateTime` | `TIMESTAMP`/`TIMESTAMP WITH TIME ZONE` per DB | Agree on timezone convention |
| `byte[]` | `VARBINARY`/`BLOB` | Consider payload size |

SQL type names and exact binding support depend on the database and JDBC driver. For sensitive types like timestamps, JSON, UUIDs, enums, or nulls, verify actual mapping with integration tests.

## 12. Handling null

Nulls require attention because the database has typed columns while Java references may have no value.

With the bean property provider, `BeanPropertySqlParameterSource` can read the property type from bean metadata even when the current value is null. However, with maps or custom sources, specify the SQL type if the driver cannot infer it.

Example:

```java
return new MapSqlParameterSource()
        .addValue("orderId", item.getOrderId(), Types.BIGINT)
        .addValue("comment", item.getComment(), Types.VARCHAR)
        .addValue("shippedAt", item.getShippedAt(), Types.TIMESTAMP);
```

Do not blindly convert null to an empty string or 0 if business rules distinguish "no value" from empty/zero. Decide explicitly whether columns allow null and handle validation in the processor or database constraints.

## 13. Enums, date/time, and value conversion

The provider is an appropriate place to convert representations before binding when database conventions differ from model types.

Enum example:

```java
enum OrderStatus {
    NEW("N"), PAID("P"), CANCELLED("C");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    public String getCode() {
        return code;
    }
}
```

The provider can bind `item.getStatus().getCode()` instead of the enum object. This lets the database store stable codes rather than depending on Java enum names.

For date/time values, decide explicitly whether a column stores a calendar date, local timestamp, or absolute instant. Never convert `Instant` to `LocalDateTime` using the machine's default timezone because runtime environments can differ. Standardize on UTC or use timezone-aware SQL types per system convention.

The provider should not perform complex unvalidated conversions. If data is invalid, the processor should catch it and raise a business error before the writer is invoked.

## 14. Nested properties and item DTOs

In some cases, an item contains nested objects:

```java
public class OrderRecord {
    private Long id;
    private Customer customer;
    private BigDecimal amount;

    public Long getId() { return id; }
    public Customer getCustomer() { return customer; }
    public BigDecimal getAmount() { return amount; }
}
```

SQL may need `customerId`, obtained from `item.getCustomer().getId()`. A custom provider can handle this explicitly:

```java
return new MapSqlParameterSource()
        .addValue("orderId", item.getId(), Types.BIGINT)
        .addValue("customerId", item.getCustomer().getId(), Types.BIGINT)
        .addValue("amount", item.getAmount(), Types.DECIMAL);
```

This also lets you handle a null `customer` with an appropriate message or value. Do not assume nested paths always exist if the model has optional relationships.

For simple writers, flat DTOs are usually easier to control than entities with many lazy associations. Accessing lazy associations inside a provider can trigger extra queries or fail if the persistence context is closed.

## 15. Provider and dynamic SQL

`SqlParameterSource` binds expression values in SQL, not table names, column names, or SQL keywords.

Valid example:

```sql
select * from orders where tenant_id = :tenantId
```

`tenantId` is a value and can be bound via a parameter source.

You cannot use:

```sql
select * from :tableName
```

to bind a table name with `SqlParameterSource`. JDBC parameter markers do not represent SQL identifiers. If dynamic table or column selection is needed, use an application-controlled identifier allowlist and build SQL from validated choices.

Parameter binding avoids concatenating user data directly into SQL values and reduces SQL injection risk. However, it does not protect identifiers or fragments concatenated into the statement.

## 16. ItemSqlParameterSourceProvider vs. ItemPreparedStatementSetter

`JdbcBatchItemWriter` supports two common data-binding approaches:

- `ItemSqlParameterSourceProvider<T>`: uses named parameters with `SqlParameterSource`.
- `ItemPreparedStatementSetter<T>`: binds values positionally on `PreparedStatement`.

Positional setter example:

```java
public class OrderPreparedStatementSetter
        implements ItemPreparedStatementSetter<OrderRecord> {

    @Override
    public void setValues(
            OrderRecord item,
            PreparedStatement ps) throws SQLException {

        ps.setLong(1, item.getId());
        ps.setString(2, item.getCustomerId());
        ps.setBigDecimal(3, item.getAmount());
    }
}
```

Comparison:

| Criterion | ItemSqlParameterSourceProvider | ItemPreparedStatementSetter |
|---|---|---|
| Parameter style | Named parameters like `:orderId` | Positional `?` like 1, 2, 3 |
| Mapping | Returns `SqlParameterSource` | Calls setters directly on `PreparedStatement` |
| Readability | Parameter names clear in SQL | Must preserve exact bind order |
| SQL type declaration | Possible via `MapSqlParameterSource` | Via `PreparedStatement` setters or `setNull` |
| Best suited for | SQL with many parameters, name-based mapping | Simple SQL or needing direct JDBC binding control |

Do not configure both approaches simultaneously on a single writer. The builder expects a single binding strategy matching the supplied SQL.

## 17. Provider is invoked per item in the batch

`JdbcBatchItemWriter` receives a chunk containing multiple items. For each item, the writer needs a matching parameter source to construct the batch update. Consequently, the provider can be called many times during a single `write()` call.

For instance, a chunk size of 500 can invoke the provider around 500 times in one chunk write, depending on writer processing and any retries/skips that occur.

Because the provider can be re-invoked when a chunk rolls back/retries or when the writer isolates a failing item, the implementation should:

- Produce deterministic results for the same item.
- Never send messages, emails, or call external APIs.
- Never write business data to the database.
- Never hold a shared mutable `MapSqlParameterSource` across multiple items.
- Never store the current item in a field of a singleton provider.
- Avoid heavy computations or per-item secondary queries if they can be prepared in the processor.

Typically, the provider should be a stateless mapper. Each call returns a new `SqlParameterSource` or an independent source unaffected by the next call.

## 18. Thread safety when the writer runs in parallel

In some architectures, a writer may be used across multiple threads or multiple step executions. In that case, the provider can also be invoked concurrently.

A stateless provider that only reads item properties and creates a new parameter source is generally safer to use. A provider with mutable fields, counters, or unsynchronized caches can introduce race conditions.

Avoid:

```java
public class UnsafeProvider
        implements ItemSqlParameterSourceProvider<OrderRecord> {

    private final MapSqlParameterSource shared =
            new MapSqlParameterSource();

    @Override
    public SqlParameterSource createSqlParameterSource(OrderRecord item) {
        shared.addValue("orderId", item.getId());
        return shared;
    }
}
```

Concurrent calls can overwrite each other's values. Create a fresh source per item:

```java
public class SafeProvider
        implements ItemSqlParameterSourceProvider<OrderRecord> {

    @Override
    public SqlParameterSource createSqlParameterSource(OrderRecord item) {
        return new MapSqlParameterSource()
                .addValue("orderId", item.getId(), Types.BIGINT);
    }
}
```

A stateless provider does not automatically make items thread-safe. If an item is mutable and modified by multiple threads concurrently, mapping can still read inconsistent data. Each item should have clear ownership in the pipeline.

## 19. Writer transactions and rollbacks

The provider does not manage transactions. When `JdbcBatchItemWriter` runs in a chunk-oriented step, JDBC commands typically participate in the transaction managed by the step's transaction manager if the writer uses the matching datasource/resource.

If a batch update fails before commit, the transaction can roll back the chunk's database changes. On retry, the writer can be called again and the provider recreates parameter sources for items.

Because the provider only maps values, it must not have non-transactional side effects. If a provider calls APIs or writes files, those actions are not rolled back automatically with the database and may repeat when the writer retries.

Keep pure transformation logic inside the provider, while business side effects belong in mechanisms with proper transaction/idempotency support such as outbox or separate processing steps.

## 20. assertUpdates and the meaning of update counts

`JdbcBatchItemWriterBuilder` has an `assertUpdates` option. When enabled, the writer checks update results per the writer contract; if a statement updates zero rows, the writer may throw an exception.

This is useful when every item must create or update a record. However, some valid SQL statements can return an update count of 0 per database or statement semantics, such as an idempotent no-op update or a specialized upsert.

Clarify what update count means for the SQL in use. If 0 rows is a business error, keep `assertUpdates(true)`. If 0 rows can be valid, consider appropriate configuration and verify results yourself against business rules. Never disable the assertion merely to mask a mapping bug or a wrong `WHERE` condition.

## 21. Handling missing parameters or wrong property names

If SQL expects `:orderId` yet the provider does not supply that key, `NamedParameterJdbcTemplate` typically raises an error when preparing to execute the statement. The error may surface at the writer step rather than when the application context starts.

Common causes:

- Placeholder name does not match getter/property name.
- Map is missing a key.
- Property lacks a getter or is inaccessible.
- SQL changed while the provider was not updated.
- Item has a null value and the SQL type is unclear to the driver.
- Custom provider returns the wrong source or reuses a source.

Test mappings independently and have integration tests for real SQL statements. Error logs should note the missing parameter name and item type, while avoiding logging full payloads containing sensitive data.

## 22. Do not query the database inside the provider

The provider is invoked per item. If each invocation queries the database for extra data, a 1,000-item chunk can generate 1,000 extra queries, causing N+1 queries and degrading throughput.

Avoid:

```java
@Override
public SqlParameterSource createSqlParameterSource(OrderRecord item) {
    Customer customer = customerRepository.findById(item.getCustomerId())
            .orElseThrow();

    return new MapSqlParameterSource()
            .addValue("orderId", item.getId())
            .addValue("customerName", customer.getName());
}
```

If customer data is needed, enrich the item in the processor, use a join in the reader, or load data in controlled batches/caches. The provider should only map a ready item into SQL parameters.

## 23. Provider with stored procedures or special SQL

`SqlParameterSource` can supply parameters to named SQL statements, but `JdbcBatchItemWriter` is primarily designed for standard batch updates/inserts. If you need to invoke stored procedures, output parameters, cursors, or complex logic, evaluate `StoredProcedureItemWriter`, `SimpleJdbcCall`, or a custom writer suited to Spring Batch/Spring JDBC APIs.

Do not force a standard `JdbcBatchItemWriter` to handle output parameters or multiple result sets when the batch update abstraction does not support those semantics.

## 24. Unit testing the provider independently

A provider is a small mapper that can be unit tested directly without a database.

Example:

```java
class OrderSqlParameterSourceProviderTest {

    private final OrderSqlParameterSourceProvider provider =
            new OrderSqlParameterSourceProvider();

    @Test
    void mapsOrderFieldsToNamedParameters() {
        OrderRecord item = new OrderRecord(
                1001L,
                "C001",
                new BigDecimal("250.00"),
                OrderStatus.PAID);

        SqlParameterSource source =
                provider.createSqlParameterSource(item);

        assertEquals(1001L, source.getValue("orderId"));
        assertEquals("C001", source.getValue("customerId"));
        assertEquals(new BigDecimal("250.00"), source.getValue("amount"));
        assertEquals("P", source.getValue("status"));
    }
}
```

Tests should verify:

- All required named parameters have values.
- Properties map to exact names and types.
- Enums/dates/decimals convert per convention.
- Nulls are handled properly and carry SQL types when needed.
- Every item receives an independent source.
- Items missing required data are handled per explicit policy.

## 25. Integration testing with JdbcBatchItemWriter

Unit testing the provider does not prove SQL placeholders, database schemas, and JDBC drivers behave properly. Write integration tests for the writer against a suitable test database.

Skeleton example:

```java
@SpringBatchTest
@SpringJUnitConfig(JdbcWriterTestConfiguration.class)
class JdbcBatchWriterIntegrationTest {

    @Autowired
    private JdbcBatchItemWriter<OrderRecord> orderWriter;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void writesItemsUsingNamedParameters() throws Exception {
        Chunk<OrderRecord> items = new Chunk<>();
        items.add(new OrderRecord(
                1001L, "C001", new BigDecimal("250.00"), OrderStatus.PAID));

        orderWriter.write(items);

        Integer count = jdbcTemplate.queryForObject(
                "select count(*) from orders where order_id = ?",
                Integer.class,
                1001L);

        assertEquals(1, count);
    }
}
```

This is an illustrative skeleton; the test configuration must set up the schema, datasource, and transaction appropriately. Depending on the Spring Batch version, how `Chunk` is created and how the writer is called may need adjustments for your API.

Integration tests should also cover rollback scenarios: the writer writes partially then fails, the transaction rolls back, and subsequent retries or restarts create no duplicate data.

## 26. Common errors

| Situation | Cause | Resolution |
|---|---|---|
| Named parameter not found | Placeholder name does not match key/property | Synchronize SQL names and provider |
| Value bound to wrong column | Wrong property or mapping used | Unit test each key and integration test SQL |
| Null causes JDBC error | Driver cannot infer SQL type | Use `MapSqlParameterSource.addValue` with `Types.*` |
| Enum fails to write | JDBC driver does not know how to bind Java enum | Convert explicitly to code/string/int |
| Provider returns previous item's data | Reused mutable `SqlParameterSource` | Create a new source per item |
| Writer unexpectedly slow | Provider queries DB or calls API per item | Move enrichment to reader/processor or batch lookup |
| Retry causes duplicate side effects | Provider performs I/O outside mapping | Keep provider pure; use outbox/idempotency for side effects |
| Two threads overwrite parameters | Provider holds shared mutable state | Use stateless provider and separate sources |
| SQL injection via identifier | Trying to bind table/column name as parameter | Whitelist and validate SQL identifiers separately |
| Writer reports zero update count | `assertUpdates` mismatches SQL semantics or `WHERE` misses | Clarify expected update count and inspect SQL |
| Missing map key caught only at runtime | Dynamic mapping not checked upfront | Unit test provider and validate items before writer |

## 27. Workflow for choosing a provider

1. **Inspect the item model:** does the item have JavaBean getters matching the named parameters?
2. **If yes:** use `BeanPropertyItemSqlParameterSourceProvider` to minimize manual mapping.
3. **If the item is a map:** consider `MapItemSqlParameterSourceProvider`.
4. **If renaming/conversion/types/nulls are needed:** write a custom `ItemSqlParameterSourceProvider<T>` returning `MapSqlParameterSource`.
5. **Declare SQL:** use clear named placeholders and verify each key.
6. **Check types:** specify SQL types, especially for nulls, enums, dates/times, and database-specific types.
7. **Keep the provider stateless:** do not store a shared mutable source and avoid side effects.
8. **Configure the writer:** pass the provider via `itemSqlParameterSourceProvider(...)` and configure datasource/SQL.
9. **Test mapping:** unit test the source for each item variation.
10. **Test real writes:** integration test with a database, transactions, update counts, and rollbacks.

## 28. Key principles to remember

- In Spring Batch, the commonly used extension point is named `ItemSqlParameterSourceProvider<T>`; it builds an `SqlParameterSource` from each item.
- `SqlParameterSource` belongs to Spring JDBC and supplies named values for named SQL parameters.
- `JdbcBatchItemWriter` uses the provider to bind parameters for each item in a batch.
- `BeanPropertyItemSqlParameterSourceProvider` fits items with JavaBean properties matching placeholder names.
- `MapItemSqlParameterSourceProvider` fits map-shaped items; `MapSqlParameterSource` is useful when SQL types must be declared.
- A custom provider fits when renaming, enum/date conversion, null handling, or multi-property mapping is needed.
- Key names in the source must match placeholder names; keys do not include the `:` prefix.
- Parameter binding cannot bind table/column names or SQL fragments; dynamic identifiers must be whitelisted.
- Providers should be stateless, create an independent source per item, and never call APIs/databases.
- Providers can be re-invoked when the writer retries; mappings must be deterministic and side-effect-free.
- Providers do not manage transactions, chunk size, retries, or connections; those are the writer's and step's responsibility.
- Use `ItemPreparedStatementSetter` when direct positional parameter binding is needed.
- Test providers independently and integration-test against real SQL/drivers.

`ItemSqlParameterSourceProvider` is the bridge between Spring Batch item objects and Spring JDBC named parameters. By choosing the right implementation, keeping placeholder names consistent, handling types/nulls explicitly, and keeping the provider pure, `JdbcBatchItemWriter` can write data batches that are readable, testable, and safer during retries or parallel execution.
