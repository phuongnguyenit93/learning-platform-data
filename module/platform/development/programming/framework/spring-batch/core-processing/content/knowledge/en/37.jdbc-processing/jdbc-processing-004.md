# Query Parameters

In Spring Batch, a reader or processor often queries the database using a set of conditions: business date, status, ID range, tenant, partition range, or watermark. These values must be passed into SQL safely and consistently.

**Query parameters** are values bound to a SQL statement at execution time. Instead of concatenating data into the SQL string, the application uses `PreparedStatement` placeholders or named parameters. Spring Batch can obtain values from `JobParameters`, `StepExecutionContext`, or runtime configuration and pass them to the JDBC reader.

Proper parameter design helps:

- Prevent SQL injection when values come from external sources.
- Ensure JDBC data types match the table columns.
- Reuse the SQL statement across multiple sets of values.
- Partition data across workers.
- Keep the query scope unchanged when a Job restarts.
- Make filter conditions clear and easy to test.

## 1. Why Not Concatenate Parameters Directly into SQL?

Unsafe approach:

~~~java
String sql = "SELECT id, amount FROM orders WHERE status = '"
        + status + "'";

return jdbcTemplate.query(sql, rowMapper);
~~~

If `status` comes from `JobParameters` or an external source, the value may contain quotes or unintended SQL fragments. String concatenation also forces the database to parse a different SQL string for each value.

Using placeholders:

~~~java
String sql =
        "SELECT id, amount FROM orders WHERE status = ?";

return jdbcTemplate.query(sql, rowMapper, status);
~~~

JDBC sends the SQL statement and parameter values separately. The driver binds each value according to its data type without interpreting parameter contents as SQL syntax.

`PreparedStatement` does not only improve security. It also makes SQL easier to read, easier to reuse, and avoids manual escaping bugs.

## 2. Positional Parameters with Question Marks

JDBC `PreparedStatement` uses question marks as placeholders:

~~~sql
SELECT id, customer_id, amount
FROM orders
WHERE status = ?
  AND created_at >= ?
  AND created_at < ?
ORDER BY id
~~~

Parameters are bound by 1-based position:

~~~java
PreparedStatement statement = connection.prepareStatement(sql);

statement.setString(1, status);
statement.setTimestamp(2, startTimestamp);
statement.setTimestamp(3, endTimestamp);
~~~

Binding order must match the exact placeholder order in the SQL. If two parameters with compatible types are swapped, the query may execute yet return wrong data without raising an obvious error.

When there are many conditions, keep the SQL and binding logic close together, or use `NamedParameterJdbcTemplate` to reduce positional mistakes.

## 3. Using JdbcTemplate in a Processor or Service

`JdbcTemplate` fits well when a processor or service needs to query supporting data for each item.

Example checking customer status:

~~~java
public class CustomerLookupService {

    private final JdbcTemplate jdbcTemplate;

    public CustomerLookupService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public CustomerStatus findStatus(Long customerId) {
        String sql = """
                SELECT status
                FROM customer
                WHERE id = ?
                """;

        return jdbcTemplate.queryForObject(
                sql,
                (rs, rowNum) ->
                        CustomerStatus.valueOf(rs.getString("status")),
                customerId);
    }
}
~~~

The `customerId` parameter is bound to the placeholder. There is no need to convert the ID to a string or add quotes in SQL.

If a processor calls this service for every item, evaluate N+1 queries. With large chunks, you can batch-lookup by a set of customer IDs or join the data directly in the reader to reduce round trips to the database.

## 4. NamedParameterJdbcTemplate

When SQL has many parameters, named parameters make the query easier to read.

~~~java
String sql = """
        SELECT id, customer_id, amount
        FROM orders
        WHERE status = :status
          AND created_at >= :startTime
          AND created_at < :endTime
        ORDER BY id
        """;

MapSqlParameterSource parameters = new MapSqlParameterSource()
        .addValue("status", status)
        .addValue("startTime", startTime)
        .addValue("endTime", endTime);

List<Order> orders = namedParameterJdbcTemplate.query(
        sql,
        parameters,
        orderRowMapper);
~~~

Names in the SQL must match the keys in the parameter source. `NamedParameterJdbcTemplate` converts named parameters into the appropriate JDBC placeholders before execution.

Named parameters help avoid positional mistakes when adding or changing conditions. However, they still bind **values**; they do not allow passing table names, column names, or SQL keywords as parameters.

## 5. Reading Parameters from JobParameters

A Job typically receives values such as business date, tenant ID, input mode, or ID bounds when launched.

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addLong("minOrderId", 1000L, true)
        .addString("status", "READY", false)
        .toJobParameters();
~~~

These parameters can be injected into a `@StepScope` bean using SpEL:

~~~java
@Bean
@StepScope
public ItemReader<Order> orderReader(
        @Value("#{jobParameters['businessDate']}") String dateText,
        @Value("#{jobParameters['minOrderId']}") Long minOrderId,
        @Value("#{jobParameters['status']}") String status) {
    // Build reader with resolved values.
}
~~~

`StepScope` defers target bean creation until `StepExecution` is active. At that point, the `JobParameters` for the current run are available.

If a parameter is required, validate it before the Step runs using `JobParametersValidator`. Do not let a null value travel deep into a query and fail later due to conversion or SQL semantics.

## 6. Parameters from StepExecutionContext

With partitioning, each worker usually queries its own data range. The `Partitioner` can place `fromId` and `toId` into each partition's `StepExecutionContext`.

The reader receives those values via `StepScope`:

~~~java
@Bean
@StepScope
public JdbcCursorItemReader<Order> partitionOrderReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['fromId']}") Long fromId,
        @Value("#{stepExecutionContext['toId']}") Long toId) {

    // Configure query for the partition's ID range.
}
~~~

For example, each worker receives a range:

| Partition | fromId | toId |
|---|---:|---:|
| worker-0 | 1 | 10000 |
| worker-1 | 10001 | 20000 |
| worker-2 | 20001 | 30000 |

The query can use:

~~~sql
SELECT id, amount
FROM orders
WHERE id >= ?
  AND id <= ?
ORDER BY id
~~~

Each `StepExecution` has its own context, so the partition reader should be created with `StepScope`. Do not share a single singleton reader with mutable parameter fields across multiple workers.

## 7. Using PreparedStatementSetter with JdbcCursorItemReader

`JdbcCursorItemReader` uses a JDBC cursor to read results sequentially. When the SQL has positional parameters, you can pass a `PreparedStatementSetter` to bind values.

Example:

~~~java
@Bean
@StepScope
public JdbcCursorItemReader<Order> orderCursorReader(
        DataSource dataSource,
        @Value("#{jobParameters['status']}") String status,
        @Value("#{jobParameters['minOrderId']}") Long minOrderId) {

    String sql = """
            SELECT id, customer_id, amount, status
            FROM orders
            WHERE status = ?
              AND id > ?
            ORDER BY id
            """;

    return new JdbcCursorItemReaderBuilder<Order>()
            .name("orderCursorReader")
            .dataSource(dataSource)
            .sql(sql)
            .preparedStatementSetter(statement -> {
                statement.setString(1, status);
                statement.setLong(2, minOrderId);
            })
            .rowMapper(orderRowMapper())
            .fetchSize(500)
            .saveState(true)
            .build();
}
~~~

`PreparedStatementSetter` is invoked when the reader prepares the query. Values are bound in placeholder order.

If a parameter can be null, decide the JDBC type and SQL semantics before binding. Do not call `setLong` with a null `Long` because Java will unbox null and throw a `NullPointerException`. Use `setNull` with the corresponding `java.sql.Types` constant or design an appropriate predicate.

## 8. Binding Dates and Times with Proper JDBC Types

Business dates and timestamps must be bound using appropriate types. Avoid concatenating date strings into SQL because formats and locales can differ across environments.

Example filtering by a single date:

~~~java
LocalDate businessDate = LocalDate.parse(dateText);

statement.setDate(
        1,
        java.sql.Date.valueOf(businessDate));
~~~

For a time range:

~~~java
LocalDateTime start = businessDate.atStartOfDay();
LocalDateTime end = businessDate.plusDays(1).atStartOfDay();

statement.setTimestamp(
        1,
        Timestamp.valueOf(start));

statement.setTimestamp(
        2,
        Timestamp.valueOf(end));
~~~

The query uses a half-open interval (closed at the start, open at the end):

~~~sql
WHERE created_at >= ?
  AND created_at < ?
~~~

This avoids constructing a `23:59:59.999...` boundary and works better when timestamp precisions differ.

If the column stores UTC instants or has specific timezone semantics, convert using the defined business `ZoneId`. Do not rely on the JVM's default timezone to construct timestamps.

## 9. Parameters in JdbcPagingItemReader

`JdbcPagingItemReader` reads data page by page. The query provider generates SQL appropriate for the database and sort keys. Named parameter values are passed via `parameterValues`.

Example using `PostgresPagingQueryProvider`:

~~~java
@Bean
@StepScope
public JdbcPagingItemReader<Order> orderPagingReader(
        DataSource dataSource,
        @Value("#{jobParameters['businessDate']}") String dateText,
        @Value("#{jobParameters['minOrderId']}") Long minOrderId) {

    LocalDate businessDate = LocalDate.parse(dateText);

    PostgresPagingQueryProvider queryProvider =
            new PostgresPagingQueryProvider();

    queryProvider.setSelectClause(
            "SELECT id, customer_id, amount, status");
    queryProvider.setFromClause("FROM orders");
    queryProvider.setWhereClause(
            "WHERE business_date = :businessDate AND id > :minOrderId");
    queryProvider.setSortKeys(
            Map.of("id", Order.ASCENDING));

    return new JdbcPagingItemReaderBuilder<Order>()
            .name("orderPagingReader")
            .dataSource(dataSource)
            .queryProvider(queryProvider)
            .parameterValues(Map.of(
                    "businessDate",
                    java.sql.Date.valueOf(businessDate),
                    "minOrderId",
                    minOrderId))
            .pageSize(500)
            .fetchSize(500)
            .rowMapper(orderRowMapper())
            .saveState(true)
            .build();
}
~~~

Keys in `parameterValues` must match placeholder names in `whereClause`. For example, `:businessDate` needs the key `businessDate`, not `:business_date` or `business_date`.

The query provider is responsible for generating next-page queries based on sort keys. Query provider configuration and parameter types must fit the actual database.

## 10. Sort Keys Must Be Stable and Unique

A paging reader needs deterministic ordering to move from one page to the next. If a sort key is not unique, multiple records sharing the same value can fall on a page boundary and cause duplicates or misses during paging/restart.

Do not sort solely by `status` when many orders share the same status:

~~~sql
ORDER BY status
~~~

Use a unique key as a tie-breaker:

~~~sql
ORDER BY status, id
~~~

With `JdbcPagingItemReader`, the `sortKeys` configuration must reflect this stable ordering. When using multiple columns, all columns together must yield a deterministic order and the query provider's condition must continue accurately.

If sort keys can change while the Job runs, paging still risks skipping or double-reading rows. Use snapshot data, watermarks, or immutable ranges.

## 11. Parameter Values and Null

Named parameters can accept null values, provided the SQL statement has the right semantics.

Example:

~~~sql
WHERE customer_id = :customerId
~~~

If `customerId` is null, comparing equality with NULL does not return true in SQL. It evaluates to `UNKNOWN`. The same predicate cannot be used to find rows where `customer_id IS NULL`.

If you want an optional parameter, you can write:

~~~sql
WHERE (:customerId IS NULL OR customer_id = :customerId)
~~~

This can be convenient, but sometimes makes it harder for the query planner to use an optimal index. For performance-critical queries, consider building two separate queries with explicit predicates based on whether the parameter is present.

Do not use `Map.of` when values might be null because `Map.of` rejects null keys/values. Validate upfront or use `MapSqlParameterSource`/`HashMap` with deliberate null handling.

## 12. Optional Parameters and Dynamic Filters

A query may have multiple optional filters: status, customer ID, start date, end date. Do not concatenate values into SQL.

You can assemble a list of predicates from validated conditions, concatenating only fixed SQL fragments controlled by the application:

~~~java
List<String> predicates = new ArrayList<>();
MapSqlParameterSource params = new MapSqlParameterSource();

if (status != null) {
    predicates.add("status = :status");
    params.addValue("status", status);
}

if (customerId != null) {
    predicates.add("customer_id = :customerId");
    params.addValue("customerId", customerId);
}

String where = predicates.isEmpty()
        ? ""
        : " WHERE " + String.join(" AND ", predicates);

String sql = """
        SELECT id, customer_id, amount
        FROM orders
        """ + where + " ORDER BY id";
~~~

Values are still bound through `params`. Only fixed predicate fragments selected by the application are concatenated into the SQL.

With `JdbcPagingItemReader`, the query provider is typically configured before the reader runs. If filters vary with `JobParameters`, build the query provider inside a `@StepScope` bean with the corresponding predicate structure and `parameterValues`.

## 13. Table Names or Column Names Cannot Be Bound with Placeholders

Placeholders represent **values**, not SQL identifiers.

This statement will not work as expected:

~~~sql
SELECT * FROM ? WHERE status = ?
~~~

The first parameter cannot substitute a table name. JDBC treats it as a value expression, not an identifier.

If a user needs to select a table or column, use a whitelist:

~~~java
Map<String, String> allowedTables = Map.of(
        "orders", "orders",
        "returns", "returns");

String table = allowedTables.get(requestedTable);

if (table == null) {
    throw new IllegalArgumentException("Unsupported table");
}

String sql = "SELECT id, status FROM " + table
        + " WHERE status = ?";
~~~

`requestedTable` is checked against an allowlist. Only application-controlled table names enter the SQL. The `status` value still uses a placeholder.

Apply the same rule to `ORDER BY`, column names, schemas, operators, and other dynamic SQL clauses. Never interpolate external input directly into identifiers or keywords.

## 14. Parameters for IN Clauses

When filtering by a list of IDs, `NamedParameterJdbcTemplate` supports expanding collection parameters in an `IN` clause:

~~~sql
SELECT id, amount
FROM orders
WHERE id IN (:orderIds)
~~~

Example:

~~~java
MapSqlParameterSource parameters = new MapSqlParameterSource()
        .addValue("orderIds", orderIds);

List<Order> orders = namedParameterJdbcTemplate.query(
        sql,
        parameters,
        orderRowMapper);
~~~

`NamedParameterJdbcTemplate` expands the collection into the corresponding number of placeholders and binds each element.

Empty lists must be handled before running the query. An `IN` clause with zero elements can produce invalid SQL or different behavior depending on the framework/database. Decide explicitly: does an empty list mean return no records, apply no filter, or treat as invalid input?

For very large lists, avoid generating tens of thousands of placeholders. You can use a temporary table, table-valued parameter, staging table, or join against a preloaded data source depending on the database.

## 15. LIKE Parameters and Wildcards

You can bind patterns for `LIKE`:

~~~sql
WHERE customer_name LIKE ?
~~~

Example finding names starting with a prefix string:

~~~java
statement.setString(1, prefix + "%");
~~~

`%` and `_` are wildcards in `LIKE`. If a user enters them as literal characters, escape them according to database rules and declare an `ESCAPE` character:

~~~sql
WHERE customer_name LIKE :pattern ESCAPE '\'
~~~

Escape the escape character first, then escape `%` and `_`. Do not assume parameterization automatically turns wildcards into literal characters; parameterization prevents SQL injection, but does not alter `LIKE` semantics.

## 16. Parameter Types Must Match Column Types

Binding the wrong type can force the database to implicitly cast, skip indexes, or reject the query.

Examples:

- `BIGINT`: `setLong` or `Long`.
- `INTEGER`: `setInt` or `Integer`.
- `DECIMAL/NUMERIC`: `setBigDecimal` or `BigDecimal`.
- `DATE`: `setDate` or `java.sql.Date`.
- `TIMESTAMP`: `setTimestamp` or an appropriate JDBC type.
- `VARCHAR`: `setString`.
- `BOOLEAN`: `setBoolean`.

Do not convert all parameters into `String` just for configuration convenience. The database may have to cast strings to column types, leading to format errors or poor query plans.

For enums, decide whether to store name, code, or ordinal. If storing name or code, bind a `String` matching the defined code. Do not use `enum.ordinal()` as a business value because reordering enum constants can corrupt data.

## 17. Parameters and Query Plans

Databases can often reuse prepared statements or query plans for SQL statements with stable structures. This can reduce parse and planning overhead.

However, parameterization does not guarantee every query gets an optimal plan. Some databases exhibit parameter sniffing or choose plans dependent on data distribution.

When a query is slow:

- Check the execution plan.
- Check indexes on filter and sort columns.
- Check whether parameter types match column types.
- Check filter selectivity.
- Avoid `OR`-style optional predicates if they cause the planner to skip indexes.
- Benchmark with representative values, not just a single parameter set.

Do not add hints or force casts purely on guesswork. Use execution plans and real data.

## 18. Parameters in JdbcCursorItemReader and JdbcPagingItemReader

The two readers support different reading approaches:

| Criterion | JdbcCursorItemReader | JdbcPagingItemReader |
|---|---|---|
| Reading approach | Sequential cursor | Page-by-page queries |
| Common parameter binding | `PreparedStatementSetter` | Map of named `parameterValues` |
| Sort key | `ORDER BY` for stable order | Required for stable paging |
| Connection | May hold cursor/connection for Step duration | Opens queries per page |
| Restart | Restores position via reader state | Resumes based on paging state/sort keys |
| Best suited for | Sequential reading over a cursor | Large datasets needing pagination or where holding a cursor is impractical |

Both require a stable reader name and `saveState` when restart support is desired. Choose based on database driver, transactions, concurrency, dataset size, and continuation query capabilities.

Parameter values must remain identical across restarts. If business date or partition ranges change between the initial run and restart, the reader may resume on a different dataset.

## 19. Parameters and Restart Identity

`JobParameters` serves two distinct roles:

- Passing runtime values to queries.
- Identifying the `JobInstance` when parameters are marked identifying.

If `businessDate` defines the dataset, it should usually be marked as an identifying parameter. If `businessDate` is changed while reusing the same `JobInstance`, a restart could query a different record set than the saved checkpoint.

Example:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addLong("minOrderId", 1000L, true)
        .addString("traceLabel", "night-run", false)
        .toJobParameters();
~~~

`traceLabel` is only for observability, so it can be non-identifying. `businessDate` and `minOrderId` affect query scope and therefore belong in identity.

If parameters come from a partition's `StepExecutionContext`, that context is persisted per `StepExecution`. When restarting a partition, restore the originally assigned range; do not recompute a new range from changed data if the goal is resuming the same work.

## 20. Snapshots and Data Changing During Paging

Even when parameters do not change, source data can change while the Job runs.

Suppose a reader uses:

~~~sql
WHERE id > :lastId
ORDER BY id
~~~

If new records are inserted with IDs greater than `lastId` while the Step is running, the reader may pick up those records. If updates or deletes affect predicate columns, results across pages can change.

Strategies:

- Fix an upper bound at start time: `id <= :maxId`.
- Use an immutable business date or batch ID.
- Use snapshot isolation if the database and workload support it.
- Read from a fixed staging table.
- Store the watermark and query range in `JobParameters` or `ExecutionContext`.

Example:

~~~sql
WHERE id > :lastId
  AND id <= :upperBound
ORDER BY id
~~~

`upperBound` must remain unchanged across restarts. Recomputing `max(id)` on every restart can expand the dataset and cause the Job to process more records than intended.

## 21. Query Parameters for Tenant Isolation

If data is isolated by tenant, `tenantId` must be included in every relevant query:

~~~sql
SELECT id, amount
FROM orders
WHERE tenant_id = :tenantId
  AND business_date = :businessDate
ORDER BY id
~~~

Do not pull `tenantId` from item data and bypass verified tenant scoping. Validate the tenant at launch time or from a trusted security context.

With partitioning, every partition must still preserve the right `tenantId` and its own range. Do not allow `JobParameters` or input files to freely choose a tenant if the caller is not authorized.

Tenant parameters directly determine data scope, so they should be treated as part of the contract and restart identity appropriately.

## 22. Parameters for Processor Queries and Avoiding N+1

A processor can use query parameters to look up data per item:

~~~java
public OrderEnrichment process(OrderInput input) {
    Customer customer = namedParameterJdbcTemplate.queryForObject(
            """
            SELECT id, tier
            FROM customer
            WHERE id = :customerId
            """,
            Map.of("customerId", input.customerId()),
            customerRowMapper);

    return enrich(input, customer);
}
~~~

This is safe, but it can issue one query per item. For 1 million items, the processor could execute 1 million lookup queries.

Improvements include:

- Joining `customer` in the reader query if appropriate.
- Bounded caching for immutable lookups.
- Batching IDs by chunk and looking them up once.
- Using a bulk query with an `IN` clause or staging table.
- Using a processor with preloaded reference data if the set is small.

If cached data varies by tenant or business date, the cache key must include those parameters. Do not use a global cache keyed only by customer ID if the same ID can exist across multiple tenants.

## 23. Parameters for Stored Procedures

Stored procedures also accept positional or named parameters depending on the database/driver. With Spring JDBC, you can use `SimpleJdbcCall` or `CallableStatementCreator`.

`CallableStatement` example:

~~~java
CallableStatement statement =
        connection.prepareCall("{call refresh_order_status(?, ?)}");

statement.setDate(1, java.sql.Date.valueOf(businessDate));
statement.setString(2, tenantId);

statement.execute();
~~~

Determine `IN`, `OUT`, and `INOUT` parameters, JDBC types, transaction participation, and retry behavior. A stored procedure may perform internal commits or other side effects; check its implementation before assuming chunk rollback will undo everything.

Do not concatenate parameters into the procedure call string. Use the corresponding bind API.

## 24. Query Timeout, Fetch Size, and Parameters

Query parameters are one aspect of performance, alongside reader operational settings:

- `fetchSize`: hint for how many rows the driver fetches at a time.
- `queryTimeout`: query execution timeout in seconds if supported by the driver.
- `maxRows`: limit on the number of returned rows.
- `pageSize`: items per page in a paging reader.
- `chunk size`: items per chunk transaction.

Example:

~~~java
return new JdbcCursorItemReaderBuilder<Order>()
        .name("orderCursorReader")
        .dataSource(dataSource)
        .sql(sql)
        .preparedStatementSetter(setter)
        .rowMapper(orderRowMapper())
        .fetchSize(500)
        .queryTimeout(60)
        .saveState(true)
        .build();
~~~

`fetchSize` is not `chunkSize`. Drivers may interpret `fetchSize` differently; some drivers require specific cursor or transaction settings to actually stream rows.

Query timeout is not a retry policy. When a timeout occurs, identify the exception and decide whether it is retryable.

## 25. SQL Parameters and Injection

Parameterization protects values, but it does not automatically protect every dynamically constructed SQL part.

Safe:

~~~java
String sql = "SELECT id FROM orders WHERE status = ?";
jdbcTemplate.query(sql, rowMapper, status);
~~~

Unsafe:

~~~java
String sql = "SELECT id FROM orders ORDER BY " + sortColumn;
~~~

If `sortColumn` comes from outside, an attacker can inject SQL expressions. Use a whitelist:

~~~java
Map<String, String> sortColumns = Map.of(
        "created", "created_at",
        "amount", "amount",
        "id", "id");

String column = sortColumns.get(requestedSort);

if (column == null) {
    throw new IllegalArgumentException("Unsupported sort field");
}

String sql = "SELECT id FROM orders ORDER BY " + column;
~~~

Filter values should still be bound via placeholders. Identifiers must only be selected from a fixed list managed by the application.

## 26. Testing Parameter Binding

Unit tests or integration tests should verify that values are bound properly and query results are accurate.

Example with `JdbcTemplate` against a test database:

~~~java
@Test
void filtersOrdersByStatusAndDate() {
    insertOrder(1L, "READY", LocalDate.of(2026, 11, 15));
    insertOrder(2L, "DONE", LocalDate.of(2026, 11, 15));
    insertOrder(3L, "READY", LocalDate.of(2026, 11, 14));

    List<Order> result = repository.findReadyOrders(
            "READY",
            LocalDate.of(2026, 11, 15));

    assertEquals(List.of(1L), result.stream()
            .map(Order::id)
            .toList());
}
~~~

Tests should cover:

- Normal values.
- Null or optional parameters.
- Strings with quotes and SQL special characters.
- Start/end boundary dates.
- Large numeric types and overflow.
- Empty list for `IN`.
- Mismatched parameter name in named queries.
- Wrong parameter order in `PreparedStatementSetter`.
- Non-overlapping and gap-free partition ranges.

Use an appropriate test database when SQL relies on database-specific syntax. H2 may not fully emulate PostgreSQL, Oracle, or SQL Server.

## 27. Testing Restart with Query Parameters

A restart integration test should prove the reader resumes on the same dataset:

1. Launch the Job with `businessDate` and `minOrderId`.
2. Allow one chunk to commit.
3. Force a later chunk to fail.
4. Restart the same `JobInstance` with identical identifying parameters.
5. Verify the reader resumes from the checkpoint.
6. Verify the query still uses the same `businessDate`, `minOrderId`, and partition range.
7. Verify already-committed items are not written twice.
8. Verify uncommitted items are reprocessed.

Do not check only Step status. Compare business keys in the target table against the expected source dataset.

If parameters come from a partition's `StepExecutionContext`, verify the context is persisted and restored properly on partition restart.

## 28. Common Pitfalls

### Concatenating Values into SQL Strings

Creates SQL injection risk and escaping bugs. Use `PreparedStatement` or `NamedParameterJdbcTemplate`.

### Using Placeholders for Table or Column Names

Placeholders only bind values. Use a whitelist for dynamic identifiers.

### Wrong Positional Parameter Order

The query runs but filters incorrectly. Keep SQL and `PreparedStatementSetter` close together and test binding order.

### Named Parameter Not Matching Map Key

SQL uses `:businessDate` while the map has `business_date`. Names must match exactly.

### Binding Dates and Times as Strings

Forces the database to cast based on locale/format. Use appropriate JDBC Date/Timestamp types.

### Using Equality Comparison with NULL

`column = NULL` never finds null rows. Use `IS NULL` or a dedicated predicate.

### Using Map.of with Nullable Values

`Map.of` rejects null. Validate upfront or use `MapSqlParameterSource` deliberately.

### Optional Parameters Causing Index Loss

`OR`-style predicates can lead to poor query plans. Inspect execution plans and consider separate query shapes.

### Non-Unique Paging Sort Key

Can duplicate or miss records at page boundaries. Use a unique sort key or stable composite key.

### Changing Parameters Between Restarts

Old checkpoints can get applied to a new dataset. Keep identifying parameters and query context consistent.

### Processor Generating N+1 Queries

Performance degrades linearly with item count. Use joins, bulk lookups, or bounded caches.

### Query Reading Mutating Data

Paging may see different record sets across pages or restarts. Use upper bounds, snapshots, or staging.

## 29. Process for Designing Query Parameters

Before implementing queries in Spring Batch, determine:

1. Do parameters come from `JobParameters`, `StepExecutionContext`, or another configuration source?
2. Are parameters required or optional?
3. Are values bound with `PreparedStatementSetter` or named parameters?
4. Do Java/JDBC types match column types?
5. Are there nullable parameters and corresponding SQL semantics?
6. Does the query have dynamic filters or identifiers requiring whitelisting?
7. Does paging have a stable and unique sort key?
8. Do parameters define data scope or tenant isolation?
9. Do parameters need to be identifying for restarting the same `JobInstance`?
10. Can the data source change while the Step is running?
11. Have query plans, indexes, fetch size, and timeouts been measured?
12. Do tests verify bound values, injection strings, boundaries, partitions, and restarts?

Query parameters bridge a Job's execution configuration and database data. Pull values from `JobParameters` or `ExecutionContext` under the right scope, bind via `PreparedStatement` or named parameters, keep dynamic identifiers inside whitelists, and choose matching JDBC types. With paging or partitioning, sort keys and query ranges must stay stable; on restart, parameters defining the dataset must remain unchanged. Designing this way keeps queries safe, testable, and consistent across multiple executions.
