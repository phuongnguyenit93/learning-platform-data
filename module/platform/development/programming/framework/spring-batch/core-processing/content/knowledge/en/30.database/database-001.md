# JdbcCursorItemReader

In Spring Batch, `JdbcCursorItemReader<T>` reads data from a database using a JDBC cursor. The reader opens an SQL statement, executes the query, and holds the `ResultSet` to fetch each row sequentially. Each time the framework calls `read()`, the reader moves to the next row and uses a `RowMapper<T>` to convert that row into a Java object.

`JdbcCursorItemReader` is suitable when you need to sequentially read a large SQL result set without loading all data into memory. It is typically used in a chunk-oriented Step to read each record, process it through an `ItemProcessor`, and then write it using an `ItemWriter`.

An important characteristic of a cursor reader is that it holds the cursor and JDBC connection for as long as the Step is reading data. This differs from `JdbcPagingItemReader`, which splits the query into multiple pages. Choosing between the two requires considering connection hold time, database transaction behavior, restart requirements, and the likelihood of source data changing while the Job is running.

## 1. How does a cursor reader work?

A JDBC cursor is a `ResultSet` that allows an application to iterate over query results. With `JdbcCursorItemReader`, Spring Batch manages the cursor lifecycle and provides one item per call to `read()`.

Basic flow:

1. The Step starts and calls `open()` on the reader.
2. The reader acquires a connection, creates a statement, and executes the SQL.
3. JDBC returns a `ResultSet`.
4. On each `read()`, the reader moves to the next row.
5. `RowMapper` converts the current row into an object.
6. Spring Batch groups items into a chunk, invokes the processor/writer, and commits the transaction according to the commit interval.
7. The reader updates the checkpoint via `update()` when the framework persists state.
8. When the Step finishes, the reader closes the `ResultSet`, statement, and connection via `close()`.

```text
Job / Step starts
       |
       v
reader.open(ExecutionContext)
       |
       v
Open JDBC connection + PreparedStatement
       |
       v
Execute SQL -> ResultSet cursor
       |
       v
reader.read()
       |
       +--> ResultSet.next()
       |       |
       |       +--> RowMapper.mapRow(...)
       |       |
       |       +--> return an item
       |
       +--> loop until EOF (return null)
       |
       v
reader.update(ExecutionContext)
       |
       v
reader.close()
```

`JdbcCursorItemReader` implements the required contracts to function as an `ItemStreamReader`. The application does not need to manually open and close the cursor on each `read()` call.

## 2. Basic JdbcCursorItemReader configuration

A cursor reader requires at minimum a `DataSource`, SQL, a reader name, and a `RowMapper`:

```java
@Bean
public JdbcCursorItemReader<Order> orderCursorReader(DataSource dataSource) {
    JdbcCursorItemReader<Order> reader = new JdbcCursorItemReader<>();
    reader.setName("orderCursorReader");
    reader.setDataSource(dataSource);
    reader.setSql("""
            SELECT order_id, customer_id, amount, order_date
            FROM orders
            ORDER BY order_id
            """);
    reader.setRowMapper((rs, rowNum) -> {
        Order order = new Order();
        order.setOrderId(rs.getLong("order_id"));
        order.setCustomerId(rs.getLong("customer_id"));
        order.setAmount(rs.getBigDecimal("amount"));
        order.setOrderDate(rs.getDate("order_date").toLocalDate());
        return order;
    });
    reader.setFetchSize(500);
    reader.setSaveState(true);
    return reader;
}
```

In this example:

- `setName(...)` assigns a stable name to the reader, used when saving state.
- `setDataSource(...)` provides the JDBC connection.
- `setSql(...)` defines the query returning the columns to be read.
- `setRowMapper(...)` maps each `ResultSet` row into an `Order`.
- `setFetchSize(500)` hints to the JDBC driver to fetch data in appropriate batches.
- `setSaveState(true)` enables saving checkpoints to support restart.

The SQL should only select the required columns. Avoid `SELECT *` if the table has many columns or the schema may change, because the reader should only depend on the data the model needs.

## 3. Integrating the reader into a chunk-oriented Step

The reader can be registered as a standard reading component of a chunk Step:

```java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JdbcCursorItemReader<Order> orderCursorReader,
        ItemProcessor<Order, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(orderCursorReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

With `chunk(100, transactionManager)`, the Step processes up to 100 items in a chunk before committing following the normal flow. The cursor is not reopened for each chunk; the reader keeps the ResultSet and continues reading the next row throughout the Step's lifecycle.

Chunk size and JDBC fetch size are two different configurations:

| Configuration | What does it control? |
|---|---|
| `chunk(100, transactionManager)` | Number of items processed in a single chunk transaction |
| `fetchSize(500)` | Hint to the JDBC driver about how many rows to prefetch from the database per fetch |

There is no need to set both values equal. Chunk size affects transactions and commits; fetch size affects how the driver transfers data from the database to the application.

## 4. RowMapper converts ResultSet to object

`RowMapper<T>` receives the `ResultSet` positioned at the current row and returns the corresponding object:

```java
public interface RowMapper<T> {
    T mapRow(ResultSet rs, int rowNum) throws SQLException;
}
```

Example:

```java
public class OrderRowMapper implements RowMapper<Order> {

    @Override
    public Order mapRow(ResultSet rs, int rowNum) throws SQLException {
        Order order = new Order();
        order.setOrderId(rs.getLong("order_id"));
        order.setCustomerId(rs.getLong("customer_id"));
        order.setAmount(rs.getBigDecimal("amount"));

        Date orderDate = rs.getDate("order_date");
        order.setOrderDate(orderDate == null ? null : orderDate.toLocalDate());

        return order;
    }
}
```

`rowNum` is the row sequence number in the mapper context. If you need to store a business ID, retrieve it from a key column such as `order_id`, and do not use `rowNum` as the record identifier.

A `RowMapper` should map a single row and must not move the cursor itself using `next()`, `previous()`, or `absolute()`. The reader manages the ResultSet position. If the mapper moves the cursor, the reader may skip rows or detect an invalid cursor position when cursor position verification is enabled.

## 5. Parameterized SQL and PreparedStatementSetter

Jobs often need to read data by business date, status, or tenant. Do not concatenate parameters directly into the SQL string. Use the `?` placeholder and `PreparedStatementSetter` to bind values.

```java
@Bean
@StepScope
public JdbcCursorItemReader<Order> orderCursorReader(
        DataSource dataSource,
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    JdbcCursorItemReader<Order> reader = new JdbcCursorItemReader<>();
    reader.setName("orderCursorReader");
    reader.setDataSource(dataSource);
    reader.setSql("""
            SELECT order_id, customer_id, amount, order_date
            FROM orders
            WHERE business_date = ?
            ORDER BY order_id
            """);
    reader.setPreparedStatementSetter(ps ->
            ps.setDate(1, Date.valueOf(LocalDate.parse(businessDate)))
    );
    reader.setRowMapper(new OrderRowMapper());
    reader.setFetchSize(500);
    reader.setSaveState(true);
    return reader;
}
```

`@StepScope` allows reading `businessDate` when the StepExecution runs. A prepared statement binds values separately from the SQL statement, helping prevent SQL injection and handling data types more accurately than string concatenation.

If there are multiple parameters, bind them in the exact order of the placeholders:

```java
reader.setSql("""
        SELECT order_id, customer_id, amount
        FROM orders
        WHERE tenant_id = ?
          AND business_date >= ?
        ORDER BY order_id
        """);

reader.setPreparedStatementSetter(ps -> {
    ps.setLong(1, tenantId);
    ps.setDate(2, Date.valueOf(businessDate));
});
```

Column names, table names, or `ORDER BY` direction cannot be bound with `?` like values. If you need to dynamically select SQL structure, use a whitelist for allowed choices and validate the input before constructing the query.

## 6. Using JdbcCursorItemReaderBuilder

Spring Batch provides a builder to configure the reader more concisely:

```java
@Bean
public JdbcCursorItemReader<Order> orderCursorReader(DataSource dataSource) {
    return new JdbcCursorItemReaderBuilder<Order>()
            .name("orderCursorReader")
            .dataSource(dataSource)
            .sql("""
                    SELECT order_id, customer_id, amount
                    FROM orders
                    ORDER BY order_id
                    """)
            .rowMapper(new OrderRowMapper())
            .fetchSize(500)
            .saveState(true)
            .verifyCursorPosition(true)
            .build();
}
```

The builder typically helps configure core properties such as name, data source, SQL, row mapper, fetch size, and save state. Advanced options can be configured via the builder or the reader's setters depending on the Spring Batch version.

If the project uses a different API version, check the available methods in the dependency. Using setters directly as in the previous example clearly shows the core properties and is easy to adjust when the builder changes.

## 7. Fetch size and read performance

`fetchSize` is a hint to the JDBC driver on how many rows to prefetch from the database in a single fetch. It can reduce the number of round trips between the application and the database, especially when reading many rows.

Example:

```java
reader.setFetchSize(1000);
```

Fetch size is not chunk size and does not guarantee the driver will always fetch that exact number of rows. Some drivers treat it as a hint; some drivers have specific handling or require additional configuration to stream results instead of loading the entire result set.

When choosing fetch size, consider:

- Number of columns and average size per row.
- Available heap memory for driver buffers.
- Network latency between the application and the database.
- Fetch behavior of the JDBC driver.
- Number of concurrent readers/partitions.
- Connection and cursor hold duration.

A fetch size that is too small can increase round trips; one that is too large can increase memory used for buffers. Measure with the actual driver and database instead of choosing a value based solely on items per chunk.

## 8. Query timeout, max rows, and cursor options

`JdbcCursorItemReader` supports useful JDBC properties to control queries and cursors. Setter names may vary by version, but common concepts include:

| Property | Effect |
|---|---|
| `fetchSize` | Hint for the number of rows fetched per round trip |
| `queryTimeout` | Limits statement execution time in seconds if supported by the driver |
| `maxRows` | Limits the maximum number of rows the statement returns when configured |
| `verifyCursorPosition` | Checks that the mapper does not alter the cursor position itself |
| `driverSupportsAbsolute` | Tells the reader the driver supports `ResultSet.absolute()` to reposition the cursor |
| `saveState` | Enables/disables saving checkpoints in ExecutionContext |

Example of configuring the reader directly:

```java
reader.setFetchSize(500);
reader.setQueryTimeout(60);
reader.setVerifyCursorPosition(true);
reader.setDriverSupportsAbsolute(false);
reader.setSaveState(true);
```

`queryTimeout` is the JDBC statement timeout, not necessarily the total timeout for the entire Step. A query might execute quickly while the cursor remains open for a long time because the Step reads and processes chunks over an extended period.

`maxRows` is suitable for intentional limits such as testing or processing a subset. Do not use it in place of business conditions in SQL when you need to accurately determine the dataset.

## 9. verifyCursorPosition

`verifyCursorPosition` helps detect whether a `RowMapper` or related code has moved the cursor itself. When enabled, the reader checks the cursor position before/after calling the mapper according to the implementation's mechanism.

Example:

```java
reader.setVerifyCursorPosition(true);
```

This is generally a safe choice during development because a `RowMapper` should only read columns from the current row and return an object. If the mapper calls `rs.next()` to look for another row, the reader may skip items or throw a position check error.

Do not disable the check to hide a bug where the mapper moves the cursor. If you need to read related data, use a separate query/join, query an appropriate repository, or handle it in the processor; do not manipulate the cursor reader's ResultSet from the mapper.

## 10. driverSupportsAbsolute

When restarting, a cursor reader needs to reopen the query and position itself at the saved location. If the JDBC driver supports `ResultSet.absolute(row)`, the reader can use this operation to jump to the required position. Otherwise, the reader must iterate through the preceding rows to reach the checkpoint.

`driverSupportsAbsolute` tells the reader whether the driver supports this positioning method:

```java
reader.setDriverSupportsAbsolute(true);
```

Set it to `true` only when the driver and ResultSet mode actually support `absolute()` for the cursor in use. If unsure, keep the safe default for your version or check the JDBC driver documentation.

The ability to jump quickly to a row does not replace the requirement for stably ordered data. Upon restart, a row position is only meaningful if the query returns the same order and a compatible dataset as the previous run.

## 11. Connection and transaction behavior

One key point to understand when using `JdbcCursorItemReader` is that the cursor must remain alive while the Step reads multiple chunks. In the default configuration, the reader typically opens a separate connection for the cursor rather than using the transaction connection of each chunk. This prevents the cursor from being closed when a chunk transaction commits or rolls back.

Consequences:

- The cursor connection may be held for the entire duration of the Step run.
- Each chunk still uses the Step's transaction manager to commit written data.
- The cursor connection and the chunk transaction may be two different connections/transactions.
- Rolling back a write transaction does not necessarily rewind the JDBC cursor.
- Read data consistency depends on the isolation level and database/driver behavior.

Do not assume the reader and writer share the same transaction just because they use the same `DataSource`. You need to understand how the reader opens connections and how the transaction manager manages connections.

## 12. useSharedExtendedConnection

In some cases, you may want the cursor to share an extended connection with the Step's transaction. `JdbcCursorItemReader` has a `useSharedExtendedConnection` option. This approach requires the `DataSource` to be wrapped with `ExtendedConnectionDataSourceProxy` and the JDBC driver/database to support holding cursors over commit.

Conceptual configuration example:

```java
@Bean
public DataSource extendedDataSource(DataSource targetDataSource) {
    return new ExtendedConnectionDataSourceProxy(targetDataSource);
}

@Bean
public JdbcCursorItemReader<Order> orderCursorReader(
        @Qualifier("extendedDataSource") DataSource dataSource) {

    JdbcCursorItemReader<Order> reader = new JdbcCursorItemReader<>();
    reader.setName("orderCursorReader");
    reader.setDataSource(dataSource);
    reader.setSql("SELECT order_id, amount FROM orders ORDER BY order_id");
    reader.setRowMapper(new OrderRowMapper());
    reader.setUseSharedExtendedConnection(true);
    reader.setSaveState(true);
    return reader;
}
```

This is an advanced configuration. Not every database or JDBC driver supports cursors surviving across commits. If the driver closes the ResultSet after commit, a shared extended connection may not work properly.

Enable this option only after confirming database/driver support and testing actual transaction behavior. For most cases, the default configuration using a separate cursor connection is easier to operate.

## 13. Checkpoint and restart

`JdbcCursorItemReader` supports saving state so a Step can restart. The reader stores reading progress in the Step `ExecutionContext`, typically via the current item count and a key tied to the reader's name.

Example enabling state:

```java
reader.setName("orderCursorReader");
reader.setSaveState(true);
```

When a Job restarts with the same JobInstance:

1. Spring Batch creates a new StepExecution for the rerun.
2. The reader reopens the SQL and creates a new cursor.
3. The reader reads the saved checkpoint from the ExecutionContext.
4. The reader repositions the cursor to the next item to process.
5. The Step continues from the uncommitted portion according to the saved metadata.

The reader cannot preserve the old JDBC `ResultSet` across a process restart. It re-executes the query and repositions based on saved state. Therefore, `saveState` only solves the read position; correctness still depends on the query returning the same dataset and the same order.

Keep the reader name stable across deployments if old executions need to be restarted. Changing the name may change the state storage key, preventing the reader from finding the previous checkpoint.

## 14. Stable ORDER BY is a critical requirement

If the query has no `ORDER BY`, the database does not guarantee the order of returned rows. The reader might read items in one order on the first run and a different order upon restart.

Example to avoid:

```sql
SELECT order_id, amount
FROM orders
WHERE business_date = ?
```

You should define an explicit order using a stable key:

```sql
SELECT order_id, amount
FROM orders
WHERE business_date = ?
ORDER BY order_id
```

If `order_id` is not unique in the result set, add secondary keys to make the order deterministic:

```sql
ORDER BY customer_id, order_date, order_id
```

The order must be stable and unique for the rows being read. When a query has a one-to-many join, ensure the sort keys distinguish each result row, not just each parent entity.

## 15. Data changing between initial run and restart

A cursor reader saves position by item sequence, not as an independent data snapshot. If the source data changes between the initial run and restart, the old row position may point to different data.

For example, the first query returns 1,000 rows ordered by `order_id`. The reader commits up to row 500 and then the Job fails. Before restart, some old rows are deleted or new rows are inserted at the beginning of the order. When the query runs again, position 501 may no longer correspond to the next item from the first run.

Measures to stabilize the data source:

- Select the dataset using `businessDate`, batch ID, or a fixed source status.
- Use a snapshot or appropriate isolation if the business logic requires a consistent point-in-time view.
- Use a watermark/high-water mark to fix the ID range.
- Avoid updating/deleting source data while the Job is processing if restart relies on row position.
- Store a manifest or key list if the dataset must be reproduced identically.
- For highly volatile data, consider key-based paging or partitioning by business range.

`ORDER BY` is necessary, but not sufficient if the dataset can change. Both the result set and the ordering must be stabilized.

## 16. Cursor reader and connection pool

Because a cursor reader holds a connection for the duration of the Step run, it can occupy a connection from the pool for many minutes or longer. If multiple Jobs/Steps run concurrently, the pool can exhaust its connections.

Example:

- 8 cursor Steps running concurrently.
- Each Step holds one connection for its cursor.
- Writers and other services also need connections from the same pool.
- If the pool only has 8 connections, write operations or other services may have to wait.

During deployment, calculate the connections needed for cursor readers, writer transactions, and other applications. Do not simply increase the pool size without checking database connection limits.

Points to monitor:

- Active/idle connection count in the pool.
- Duration a cursor holds a connection.
- Number of open cursors.
- Query time to open the cursor.
- Wait time when acquiring a connection.
- Locks or long-running transactions on the database.

If a Step runs for a very long time, consider `JdbcPagingItemReader` or splitting the range with partitioning to limit cursor hold time and distribute load.

## 17. When should you use JdbcCursorItemReader?

A cursor reader is suitable when:

- You need to read a result set sequentially from a single query.
- The database/driver supports stable cursors for the data volume being processed.
- Holding the connection/cursor for the duration of the Step run is acceptable.
- Ordering and dataset are controlled to support restart.
- You want to reduce repeated queries compared to running a query for each page.

Consider other options when:

- The Step is long-running and you do not want to hold connections for long periods.
- The database/driver does not stream cursors as expected.
- The source data changes frequently, making row-position restart unsafe.
- You need to split data into multiple partitions by key/range.
- You need to re-query page by page for clearer load management and checkpointing.

## 18. Comparing JdbcCursorItemReader and JdbcPagingItemReader

| Criterion | `JdbcCursorItemReader` | `JdbcPagingItemReader` |
|---|---|---|
| Reading approach | Opens one query and iterates a ResultSet cursor | Executes multiple queries by page |
| Connection | Typically holds the cursor connection throughout the Step | Executes queries per page; connection does not need to hold a single cursor for the whole Step |
| Read position | Based on cursor position/item count | Based on sort key and page state |
| ORDER BY | Needs deterministic order for safe restart | Needs stable sort key, typically a unique key |
| Database load | One long query may hold cursors/transactions/resources | Multiple smaller queries, with repeated query overhead |
| Best suited for | Sequential reading of a stable result set | Large datasets needing paging and avoiding long-lived cursors |
| Restart | Reopens query then repositions by item count | Reopens page based on state and sort key |

Neither option is universally faster. Performance depends on the database, driver, query plan, fetch size, page size, connection count, and data size. Measure on a production-like workload.

## 19. Combining cursor reader with partitioning

You can use a cursor reader in a worker Step of a partitioned Job. Each partition receives its own data range and creates its own cursor query.

Example worker SQL:

```sql
SELECT order_id, customer_id, amount
FROM orders
WHERE order_id BETWEEN ? AND ?
ORDER BY order_id
```

The step-scoped reader receives `minId` and `maxId` from `StepExecutionContext` and binds them to the PreparedStatement. Each worker has its own cursor and connection.

This can increase throughput, but also increases the number of concurrent cursors and connections. Grid size needs to fit the connection pool and database limits. Partition names, ID ranges, and JobParameters must be stable to restart the correct partition.

Do not use a singleton `JdbcCursorItemReader` instance shared across multiple worker StepExecutions. The reader holds mutable cursor state and is not designed for multiple partitions to control a single ResultSet simultaneously.

## 20. Common pitfalls when using JdbcCursorItemReader

### Missing ORDER BY

The database returns results in an unspecified order. Upon restart, the reader may position to the wrong item. Always use a stable, unique ordering.

### Holding the cursor too long

Long-running Steps hold connections and cursors, putting pressure on the connection pool or database. Review fetch size, query plan, paging reader, or partitioning.

### RowMapper calling ResultSet.next()

The mapper moves the cursor and causes the reader to skip rows or violate cursor position checks. A mapper should only read columns of the current row.

### Using the wrong fetch size

Too small a fetch size increases round trips; too large can increase memory usage. Verify actual JDBC driver behavior.

### Assuming chunk commit commits the cursor position

The cursor connection by default can be separate from the chunk transaction connection. Rolling back a write transaction does not automatically rewind the cursor. Spring Batch manages replay/checkpointing via reader state.

### Source data changing between restarts

An item-count checkpoint may point to a different row if the result set changes. Use snapshots, batch IDs, watermarks, or an immutable source.

### Disabling saveState while expecting restart

If `saveState(false)` is set, the reader does not save checkpoints via the standard mechanism. Upon restart, it may read from the beginning again or fail to recover expected progress.

### Using shared extended connection when the driver does not support it

The cursor may be closed after commit. Enable this option only when the database/driver supports holding cursors over commit and the proxy is properly configured.

## 21. Error handling and fault tolerance

Exceptions can arise when opening connections, executing SQL, reading the ResultSet, or mapping rows. Transient infrastructure errors can be retried if the reader and database can safely re-execute. Specific data errors can be skipped if business rules allow.

Example retry configuration for transient data access errors:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderCursorReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
```

Do not retry every `Exception`. SQL syntax errors, missing columns, or schema mismatches will not resolve themselves on retry. Similarly, do not skip database outage errors as that can cause data loss.

When an error occurs, inspect the root exception, transaction rollback, cursor state, and checkpoint. The reader may be reopened or repositioned via the retry/restart mechanism; do not hold onto `ResultSet` references in code outside the reader.

## 22. Testing JdbcCursorItemReader

Use an appropriate test database to verify actual JDBC behavior, especially if production uses a specific driver. Key scenarios to test:

1. Read an empty result set and verify `read()` returns `null`.
2. Read multiple rows and verify `RowMapper` maps data types correctly.
3. Bind date/tenant parameters and verify the query returns only the expected dataset.
4. Verify `ORDER BY` produces a deterministic order.
5. Check fetch size and query timeout against the actual driver.
6. Force the writer to fail once and then retry successfully; verify items are neither lost nor duplicated.
7. Stop the Job after several committed chunks and restart with the same JobInstance; verify the reader resumes at the exact checkpoint.
8. Modify source data between two runs to test the risks of item-count restart.
9. Measure connections held throughout the Step and the impact on the pool.
10. If using `useSharedExtendedConnection`, confirm the cursor remains open across commits with the production driver/database.

Unit testing `RowMapper` in isolation verifies single-row conversion, but does not prove the reader opens/closes the cursor, restarts, or coordinates transactions properly. Integration tests with `JobRepository`, a transaction manager, and a real database are required for those behaviors.

## 23. JdbcCursorItemReader design rules

Choose `JdbcCursorItemReader` when you need to iterate sequentially over a result set and can hold the cursor/connection for the duration of the Step run. Configure SQL explicitly, select only necessary columns, use `PreparedStatementSetter` for runtime values, and keep `RowMapper` focused strictly on mapping the current row. Set fetch size based on measurements with the actual JDBC driver.

For reliable restarts, assign a stable reader name, enable `saveState`, preserve JobParameters, and ensure the query has a deterministic `ORDER BY` on a unique key. The dataset must also remain stable between the initial run and restart. Understand clearly that the cursor connection is separate from the chunk transaction by default; use a shared extended connection only when supported by the database/driver and thoroughly tested.

If you do not want to hold cursors for long periods, need pagination, or need key-based load distribution, consider `JdbcPagingItemReader` or partitioning. When investigating incidents, inspect the checkpoint, transaction, Step status, and committed data together. Properly designing these elements enables a cursor reader to process database data sequentially, efficiently, and restart in a controlled manner.
