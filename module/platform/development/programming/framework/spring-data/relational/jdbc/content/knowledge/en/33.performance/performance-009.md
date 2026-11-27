# Memory, Fetch Size, and Connection Hold Time When Streaming

When a query returns a large number of rows, how the results are read directly affects JVM heap memory, connection hold time, and the application's ability to serve other requests. In **Spring Data Relational JDBC**, an application can use `Stream<T>` as a query method return type if supported by the Spring Data JDBC version in use, or use Spring JDBC's streaming APIs to process rows one by one.

Streaming lets the application consume results incrementally instead of always allocating a list holding the entire result set. However, `Stream<T>` does not by itself guarantee that the JDBC driver fetches rows in batches. Actual behavior also depends on `fetch size`, the driver, the database, transactions, and how code consumes the stream.

A stream reading from a database typically holds a `ResultSet`, `Statement`, and connection until the stream is closed. Thus, streaming can reduce memory pressure while lengthening connection occupancy. This lesson explains how to balance those two factors, how to set fetch size, how to close streams properly, and when to use keyset pagination instead of a long-lived stream.

## 1. How Full Result Materialization and Streaming Differ

With standard reading, a repository returns a collection:

~~~java
List<PurchaseOrder> orders =
    repository.findByStatus(OrderStatus.SUBMITTED);
~~~

The application receives a materialized list. Every object in the result must remain on the heap as long as the list is referenced.

With a streaming query:

~~~java
try (Stream<PurchaseOrder> orders =
         repository.streamByStatus(OrderStatus.SUBMITTED)) {
    orders.forEach(this::process);
}
~~~

The application can process each element while reading results. When supported by Spring Data JDBC and the JDBC driver, this avoids keeping the entire list in memory.

| Read approach | Application memory | Resource lifecycle |
|---|---|---|
| `List<T>` | Typically proportional to row count and object size | Connection can be released once the query finishes materializing |
| `Stream<T>` | Can retain fewer objects if consumed sequentially | Typically holds `ResultSet`, `Statement`, and connection until stream closes |
| Batch keyset pagination | Bounds objects per batch | Query/connection can close after each batch |

Streaming does not mean data never enters the heap. The driver may buffer part or all of the result set; processed objects may also be retained by application code in collections, caches, or closures.

## 2. Streaming from Spring Data JDBC Query Methods

If your project's Spring Data JDBC version supports repository query methods returning `Stream<T>`, you can declare a stream method:

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    @Query("""
        SELECT *
        FROM purchase_orders
        WHERE status = :status
        ORDER BY id
        """)
    Stream<PurchaseOrder> streamByStatus(
        @Param("status") String status
    );
}
~~~

This illustrates an aggregate whose mapping matches the `SELECT` statement. If a query retrieves only a subset of columns or reporting data, use a projection/DTO compatible with your Spring Data JDBC version's mapping capabilities rather than assuming a partial row can construct a complete aggregate.

### 2.1. Always Close the Stream

A database stream can hold JDBC resources. Always close it even if processing throws an exception:

~~~java
try (Stream<PurchaseOrder> orders =
         repository.streamByStatus("SUBMITTED")) {
    orders.forEach(this::process);
}
~~~

Do not rely on the garbage collector to close `ResultSet` or connections. Terminal operations such as `forEach`, `count`, or `collect` do not replace calling `close()` on the stream.

Try-with-resources invokes `close()` when the block exits, even if processing throws an exception.

### 2.2. Do Not Return a Stream Outside Its Transaction Boundary

A common bug is opening a stream in a repository or service method and returning that stream to a caller after the method exits. If the transaction has already ended or the connection has been released before the caller consumes elements, the stream can fail.

Wrap both opening and consuming the stream within the transaction boundary:

~~~java
@Service
public class OrderExportService {

    private final PurchaseOrderRepository orders;

    public OrderExportService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(readOnly = true)
    public long processSubmittedOrders() {
        try (Stream<PurchaseOrder> stream =
                 orders.streamByStatus("SUBMITTED")) {
            return stream
                .peek(this::process)
                .count();
        }
    }

    private void process(PurchaseOrder order) {
        // Quickly process one aggregate's data.
    }
}
~~~

In this example, the service transaction remains active while the stream is consumed. When the method finishes, try-with-resources closes the stream before the transaction ends.

If the application has multiple transaction managers, specify the transaction manager bound to that repository/`DataSource` in `@Transactional`.

### 2.3. Do Not Assume Every Query Method Automatically Has a Suitable Transaction

Inherited CRUD repository methods follow Spring Data's default transaction rules. Custom-declared query methods may require explicit transaction configuration. Even if a query method has its own transaction, that transaction may end as soon as the method returns the stream, before the caller finishes reading results.

A service-level transaction enclosing both reading and processing usually clarifies resource lifetimes. Verify the semantics of your Spring Data JDBC version and test against the real driver.

## 3. How Long Is a Connection Held?

With streams backed by a JDBC cursor/result set, the connection must stay open while the application keeps fetching rows. The typical lifecycle is:

~~~mermaid
sequenceDiagram
    participant Service
    participant Repository
    participant JDBC as JDBC Driver
    participant DB as Database
    Service->>Repository: open query stream
    Repository->>JDBC: create Statement and execute query
    JDBC->>DB: send SELECT
    DB-->>JDBC: return ResultSet/cursor
    JDBC-->>Repository: Stream<T>
    Repository-->>Service: Stream<T>
    loop Consume each row
        Service->>JDBC: request next row
        JDBC->>DB: fetch batch if needed
        DB-->>JDBC: next data
        JDBC-->>Service: mapped object
    end
    Service->>Repository: close stream
    Repository->>JDBC: close ResultSet/Statement
    JDBC->>DB: release cursor/connection
~~~

Fetch details vary by driver, but the resource-management principle holds: failing to close the stream can keep the connection held indefinitely.

### 3.1. Streaming Reduces Heap Usage at the Cost of Connection Occupancy

Suppose a query returns 500,000 rows. Materializing them into a `List` may require holding hundreds of thousands of objects simultaneously. A stream lets you process one row at a time and drop references afterward.

However, if processing takes 15 minutes, the connection can remain occupied for 15 minutes. During that time, that connection cannot serve other requests.

Balance two separate resources:

- **Heap:** number of objects and data held concurrently in the application.
- **Connection pool:** number of connections occupied and duration each connection is unavailable for other work.

Streaming optimizes one dimension while potentially turning the other into a bottleneck.

### 3.2. Avoid Slow Service Calls While Holding a Stream When Possible

The following can hold a connection for a very long time:

~~~java
try (Stream<PurchaseOrder> orders = repository.streamAll()) {
    orders.forEach(order -> {
        remoteClient.send(order); // May block on network for a long time.
    });
}
~~~

If each HTTP call takes hundreds of milliseconds or retries, connection hold time scales with row count. One slow export flow can exhaust the connection pool and stall ordinary requests.

Better options depending on requirements:

- Read in small batches, close the query, and then call external services.
- Push items to process into a queue or staging table.
- Use dedicated workers with bounded concurrency.
- Decouple database reading from external service calls.

Do not hold an open database cursor while waiting on users, networks, or external systems.

## 4. What Is Fetch Size?

Fetch size is a hint the application can set on a JDBC `Statement` via:

~~~java
statement.setFetchSize(500);
~~~

It hints to the JDBC driver how many rows to retrieve per fetch round trip from the database. For drivers supporting cursors or incremental fetching, fetch size can help cap how much data is pulled over the wire at once.

Fetch size is **not**:

- A limit on total rows returned by the `SELECT`.
- Equivalent to `LIMIT` or `TOP`.
- The page size returned by a repository.
- A hard guarantee on maximum heap objects.
- A guarantee that every driver uses server-side cursors.

Drivers may treat fetch size as an advisory hint, interpret it differently, or ignore it. Actual behavior also depends on autocommit, transactions, URL properties, and driver version.

### 4.1. Fetch Size Differs from Page Size

| Concept | Effect |
|---|---|
| Fetch size | Suggested number of rows the driver retrieves per fetch from a result set |
| Page size | Number of rows the application requests in one page |
| SQL limit | Maximum rows the database returns for a query |
| Batch size | Number of records the application groups into a processing/writing batch |

For instance, a query with `LIMIT 10000` and fetch size 500 still returns up to 10,000 rows, potentially retrieved in multiple fetches. Conversely, an unlimited query with fetch size 500 can still return millions of rows across many fetches.

### 4.2. Fetch Size Does Not Guarantee Fixed Memory

Even with fetch size set to 500:

- The driver may buffer more rows or the entire result set.
- Mappers may allocate large objects.
- Application code may retain processed objects in a collection.
- Application caches/contexts may retain extra data.
- An aggregate may pull in many child objects or related data.

Measure heap usage and inspect driver/database behavior in your target environment. Do not treat fetch size as a strict memory ceiling.

## 5. Setting Fetch Size with JdbcTemplate

Spring JDBC allows setting a default fetch size on `JdbcTemplate`. If `NamedParameterJdbcTemplate` wraps that `JdbcTemplate`, it shares the underlying JDBC operations.

Example configuration:

~~~java
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcOperations;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

@Configuration
public class JdbcReadConfiguration {

    @Bean
    NamedParameterJdbcOperations namedParameterJdbcOperations(
            DataSource dataSource) {
        JdbcTemplate jdbcTemplate = new JdbcTemplate(dataSource);
        jdbcTemplate.setFetchSize(500);

        return new NamedParameterJdbcTemplate(jdbcTemplate);
    }
}
~~~

This sets the default fetch size for statements created through that template. A global configuration affects many queries, not only streaming queries. Check other queries and driver behavior before applying globally.

With Spring Data JDBC, repository infrastructure commonly uses `NamedParameterJdbcOperations`. If you configure this bean manually to adjust fetch size, verify that your repository configuration actually uses that operations bean.

Do not assume `@Query` in every Spring Data JDBC version exposes a `fetchSize` attribute. Check the annotation signature in your project's version. If unavailable, configure the underlying JDBC operations or use a dedicated query path with direct statement control.

## 6. Setting Fetch Size Per Query with queryForStream

When per-query fetch size control is needed, Spring JDBC provides `JdbcTemplate.queryForStream` in Spring Framework versions that include this API.

Example:

~~~java
public record OrderExportRow(
        Long id,
        String orderNumber,
        String status
) {
}
~~~

~~~java
public class OrderExportReader {

    private static final String SQL = """
        SELECT id, order_number, status
        FROM purchase_orders
        WHERE status = ?
        ORDER BY id
        """;

    private final JdbcTemplate jdbcTemplate;

    public OrderExportReader(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public Stream<OrderExportRow> streamSubmittedOrders() {
        return jdbcTemplate.queryForStream(
            connection -> {
                PreparedStatement statement =
                    connection.prepareStatement(SQL);
                statement.setString(1, "SUBMITTED");
                statement.setFetchSize(500);
                statement.setFetchDirection(ResultSet.FETCH_FORWARD);
                return statement;
            },
            (resultSet, rowNumber) -> new OrderExportRow(
                resultSet.getLong("id"),
                resultSet.getString("order_number"),
                resultSet.getString("status")
            )
        );
    }
}
~~~

The caller must close the stream:

~~~java
try (Stream<OrderExportRow> rows = reader.streamSubmittedOrders()) {
    rows.forEach(exportWriter::write);
}
~~~

This snippet demonstrates setting fetch size on a `PreparedStatement` for a single query. `queryForStream` returns a stream tied to JDBC resources; closing the stream releases the `ResultSet`, `Statement`, and connection. Confirm the API exists in your project's Spring Framework version before using it.

If the query needs an active transaction for the driver to use a cursor, wrap both stream creation and consumption with that DataSource's transaction manager:

~~~java
@Transactional(readOnly = true)
public void exportSubmittedOrders() {
    try (Stream<OrderExportRow> rows = reader.streamSubmittedOrders()) {
        rows.forEach(exportWriter::write);
    }
}
~~~

If `exportWriter` performs slow I/O, consider reading in batches so connections are not held throughout file writes or external calls.

## 7. Drivers and Databases Dictate Fetch Behavior

Standard JDBC defines `Statement.setFetchSize`, while drivers decide how to implement it. The same fetch size can produce very different behavior across databases.

### 7.1. PostgreSQL

With the PostgreSQL JDBC driver, cursor-based fetching typically requires:

- An active transaction, meaning the connection is not in autocommit mode.
- A positive fetch size set on the statement.
- Consuming the `ResultSet` while the transaction remains active.

If a query runs in autocommit mode, the driver may fetch the entire result set instead of using a batched cursor. A service-level `@Transactional(readOnly = true)` helps establish an appropriate transaction, though you should verify actual configuration and driver version.

### 7.2. MySQL Connector/J

With MySQL Connector/J, cursor-based fetching may require enabling the `useCursorFetch=true` property alongside a positive fetch size. Otherwise, the driver may buffer results differently.

Check the documentation for your exact Connector/J version; never copy connection URL properties from another version without verifying.

### 7.3. Other Drivers

Oracle, SQL Server, and other JDBC drivers have their own defaults, limits, and prefetch mechanisms. Some drivers use fetch size to tune prefetch row counts; others require transactions or extra settings for cursor-based reads.

When documentation does not cover a specific driver, treat fetch size as a JDBC hint and verify per driver. Never claim one fetch size is optimal across all DBMSs.

## 8. How to Choose a Fetch Size

Too small a fetch size increases network round trips between the application and database. Too large a fetch size inflates buffer memory and erodes streaming benefits.

A practical selection process:

1. Start with a moderate value, such as 200 or 500.
2. Use the same query and a representative dataset.
3. Measure completion time, heap, fetch counts, and connection hold time.
4. Test raising and lowering fetch size.
5. Test across varying row widths and network latencies.
6. Pick a value suited to your driver, workload, and connection pool.

Do not rely on local benchmarks with a few hundred rows to size production exports of millions of records.

### 8.1. Estimating Buffer Memory

Suppose the driver retains roughly one batch of `F` rows and each row occupies roughly `R` bytes in buffer representation. The buffer footprint scales roughly as:

`F × R`

This is a conceptual estimate only. Actual heap also includes Java objects, `String`s, collections, mappers, driver buffers, and objects retained by application code. You cannot derive a strict memory ceiling from fetch size alone.

### 8.2. Watch Row Width

500 narrow rows with a few numeric columns are far lighter than 500 rows containing large CLOBs, large JSON payloads, or binary data. For export queries, `SELECT` only needed columns rather than loading full aggregates if the use case does not require them.

Flat projection/DTO models usually suit report streaming better than materializing full aggregates with many child objects.

## 9. Connection Pools and Connection Hold Time

A connection pool has a finite number of connections. While a stream stays open, its connection cannot be lent to other requests.

Example with a 20-connection pool:

- 5 export requests open streams concurrently.
- 4 batch jobs also hold streams.
- Only 11 connections remain for ordinary online requests.

If each stream holds a connection for a long duration, other requests may block waiting for a connection even when their own queries are fast.

### 9.1. Hold Time Matters More Than Raw Row Count

A query returning 1 million rows that is consumed rapidly can hold a connection for less time than a query returning 5,000 rows where each row triggers a multi-second external API call.

Monitor at least:

- Duration from query open to stream close.
- Active and idle connection counts.
- Threads pending a connection.
- Connection acquisition timeouts.
- Query execution time vs. per-row processing time.
- Row counts and payload sizes.

Distinguish query execution time from total connection hold time. The query may largely finish on the database early, yet the connection remains held while the application drains the rest of the stream.

### 9.2. Do Not Open Unbounded Concurrent Streams

Each stream can occupy a connection. Launching a stream per task in an unbounded executor can starve the pool and stall tasks waiting on each other.

Bound batch/export concurrency based on:

- Connection pool size.
- Connections reserved for online traffic.
- Database load.
- Connection hold duration.
- Per-worker memory footprint.

Do not set concurrency equal to CPU thread count and assume the database can sustain that many concurrent streams.

## 10. Transactions and Locks During Streaming

A stream running inside a transaction can keep that transaction open throughout consumption. This affects:

- Connection hold duration.
- Snapshot or MVCC state lifetime depending on database/isolation.
- Locks if the query or transaction performs writes.
- Vacuum/cleanup or version retention on some databases.
- Rollback cost and recovery time on failure.

Streaming reads should use read-only transactions when aligned with application semantics. However, `readOnly = true` is a hint to the transaction manager/database, not a guarantee that all writes are blocked.

Avoid updating multiple tables inside a long transaction merely because inputs were read via a stream. When writes are needed, consider splitting work into short batch transactions.

## 11. Do Not Run Arbitrary Nested Queries on the Same Stream

While a `ResultSet` is open, issuing extra repository queries on the same connection can cause problems depending on the driver:

- Drivers may not support multiple concurrent `ResultSet`/`Statement`s on one connection.
- A new query may close or alter the state of the open `ResultSet`.
- Transactions and locks last longer than expected.
- N+1 queries multiply round trips and connection occupancy.

Pattern to avoid:

~~~java
try (Stream<PurchaseOrder> orders = repository.streamAll()) {
    orders.forEach(order -> {
        Customer customer = customerRepository.findById(
            order.getCustomerId()
        ).orElseThrow();
        process(order, customer);
    });
}
~~~

Instead, use JOINs/projections where appropriate, or batch-load customers by ID list. For large lists, keyset pagination lets you control each chunk cleanly.

## 12. When to Use Keyset Pagination Instead of Streaming?

Streaming fits when:

- You need to read a large result sequentially.
- Each row processes quickly.
- The driver supports batched fetching.
- Holding one connection for the consumption duration is acceptable.

Keyset pagination usually fits better when:

- Work is long-running or calls external systems.
- You want to release connections between batches.
- You want to resume from the last processed key.
- You want to retry a batch or resume after worker restarts.

Example ID-based query:

~~~sql
SELECT id, order_number, status
FROM purchase_orders
WHERE id > :lastSeenId
ORDER BY id
LIMIT :batchSize;
~~~

The application processes a batch, records the last ID, and queries the next batch:

~~~java
long lastSeenId = 0L;
int batchSize = 500;

while (true) {
    List<OrderExportRow> batch =
        reader.findNextBatch(lastSeenId, batchSize);

    if (batch.isEmpty()) {
        break;
    }

    processBatch(batch);
    lastSeenId = batch.get(batch.size() - 1).id();
}
~~~

Each query materializes at most one small batch. When transaction boundaries sit around each batch and end after the batch completes, connections return to the pool between batches.

### 12.1. Conditions for Safe Keyset Pagination

- The cursor column must have a deterministic order, typically a primary key or unique sort key.
- The `WHERE` predicate must match the `ORDER BY` direction and columns.
- Handle rows inserted or modified while batches run.
- When sorting by multiple columns, the cursor must include enough columns to form a unique total order.
- Decide whether snapshot consistency is required or mutations during export are acceptable.

Keyset pagination does not automatically provide a consistent snapshot for the entire job. If business logic demands a snapshot, design isolation or a dedicated data strategy.

## 13. Error Handling and Closing Resources

Always use try-with-resources for streams:

~~~java
try (Stream<OrderExportRow> rows = reader.streamSubmittedOrders()) {
    rows.forEach(this::process);
} catch (DataAccessException ex) {
    // Log and handle failure per job contract.
}
~~~

If processing throws an exception:

1. Try-with-resources closes the stream.
2. JDBC `ResultSet` and `Statement` are released.
3. The connection returns to the transaction manager or pool per transaction lifecycle.
4. The transaction interceptor decides commit/rollback based on the exception and rollback rules.

Never catch an exception and keep reading a stream that may now be in a broken state. When retrying, open a fresh query/transaction and resume from a saved checkpoint.

### 13.1. Do Not Close Too Early

Avoid doing this:

~~~java
Stream<OrderExportRow> stream = reader.streamSubmittedOrders();
stream.close();
stream.forEach(this::process);
~~~

A closed stream cannot be consumed. Keep it inside try-with-resources and consume it within that block.

### 13.2. Do Not Hand Off a Stream Across Threads

JDBC connections and `ResultSet`s are not designed for arbitrary multi-threaded sharing. Avoid:

~~~java
stream.parallel().forEach(this::process);
~~~

Running parallel streams over a JDBC stream risks unsafe concurrent cursor/connection access and blurs transaction boundaries.

If parallel processing is needed, split data into independent batches, close each batch query, and dispatch materialized data to concurrency-bounded workers. Each worker opens its own transaction/connection if it needs database access.

## 14. Verifying Streaming in a Real Environment

A unit test confirming code processes items one by one does not prove the driver fetches in batches. Verify against the real database and driver.

Metrics to observe:

| Metric | What to check |
|---|---|
| Heap usage | Does it grow with total row count or stay steady per batch? |
| GC activity | Are there excessive allocations or long pauses? |
| Fetch size | Does the `Statement` actually receive the configured value? |
| Driver behavior | Is cursor/incremental fetch genuinely active? |
| Connection hold time | How long from query open until stream close? |
| Pool pending threads | Do requests block waiting for connections? |
| Database sessions | Are cursors/transactions closed after processing? |
| Throughput | How does rows-per-second throughput behave? |

### 14.1. Testing That Streams Close on Both Success and Failure

Use integration tests with sufficiently large queries to verify streaming consumption. In addition, use pool metrics or JDBC instrumentation to confirm connections return once try-with-resources exits.

Test all of:

- Consuming the entire stream.
- Early termination after a few rows.
- Mapper or processor throwing an exception.
- Caller with no outer transaction.
- Caller with a service-level transaction.
- Canceling an export mid-run.

### 14.2. Measuring on the Target Database and Driver

Run tests with the exact driver version and connection string settings planned for deployment. An H2 test can verify basic mapping, yet does not prove PostgreSQL or MySQL uses cursors the same way.

Record database version, driver version, fetch size, autocommit/transaction mode, and tested row counts. Never issue a universal fetch size recommendation without suitable benchmarks.

## 15. Common Mistakes

| Symptom | Cause | Remedy |
|---|---|---|
| Heap still grows despite using `Stream` | Driver buffers results or code retains processed objects | Inspect driver, fetch size, and application references |
| Connection pool exhausted | Stream unclosed or held too long | Use try-with-resources and shorten processing time |
| Stream fails after service returns | Transaction/connection closed before caller consumes | Consume stream inside the transaction boundary |
| Fetch size makes no difference | Driver ignores it or needs extra config | Read exact driver docs and measure in practice |
| Query returns more rows than expected | Confusing fetch size with `LIMIT`/page size | Use SQL limit or pagination to cap total rows |
| Export crawls when calling external APIs | Connection held open during network waits | Read in batches and call external APIs outside transactions |
| Nested query breaks stream | Driver forbids multiple statements on one connection | Use JOINs or batch lookups |
| Using parallel stream causes errors | `ResultSet`/connection unsafe for concurrent sharing | Process sequentially or dispatch independent batches |
| Cursors inactive on PostgreSQL | Autocommit or transaction/fetch size misconfigured | Check transaction boundaries and driver settings |
| MySQL still buffers results | Cursor fetch or driver property not enabled | Check `useCursorFetch` and fetch size |
| Query method fails to compile with `Stream` | Spring Data JDBC version lacks that return signature | Check supported return types for your exact version |
| Batches skip or duplicate rows | Keyset lacks unique order or data mutates | Use deterministic cursors and define consistency model |

## 16. Workflow for Choosing a Large-Read Strategy

When handling large result sets, proceed in order:

1. **Estimate scale:** row count, row width, and total payload.
2. **Pick result shape:** DTO/projection for reports; aggregate when full domain mapping is required.
3. **Verify Stream support:** check the resolved Spring Data JDBC version.
4. **Design transactions:** enclose stream consumption if the driver requires a transaction for cursors.
5. **Configure fetch size:** set it on the JDBC `Statement` or appropriate template.
6. **Verify driver behavior:** confirm cursor/incremental fetching and autocommit constraints.
7. **Close resources:** always use try-with-resources, even on early exit or error.
8. **Measure connection occupancy:** monitor connection hold duration and pool pressure.
9. **Limit slow work:** avoid network calls or user waits while holding a stream.
10. **Consider keyset pagination:** when short batch transactions, retries, and checkpoints are needed.
11. **Load test:** use production-like database, driver, and row counts.

## 17. Practice Exercises

### Exercise 1 — Comparing List and Stream

1. Write a query returning `List<PurchaseOrder>`.
2. Write an equivalent query returning `Stream<PurchaseOrder>` if supported by your version.
3. Read a sufficiently large dataset.
4. Observe heap usage and completion time.
5. Verify the stream closes after processing.

### Exercise 2 — Fetch Size

1. Use `JdbcTemplate` and `PreparedStatement.setFetchSize`.
2. Try values 100, 500, and 1,000.
3. Keep the query and dataset identical.
4. Measure heap, throughput, and connection hold time.
5. Compare results on the target driver.

### Exercise 3 — Transaction Boundaries

1. Open a stream inside a service method.
2. Consume the stream inside a read-only transaction.
3. Try returning the stream out of the method.
4. Observe errors or behavior when the transaction closes early.
5. Move consumption back inside the transaction.

### Exercise 4 — Connection Pool Pressure

1. Open multiple streams concurrently.
2. Intentionally slow down the processor.
3. Monitor active, idle, and pending connections.
4. Bound worker concurrency.
5. Compare against batch processing.

### Exercise 5 — Keyset Pagination

1. Write the query `id > :lastSeenId ORDER BY id LIMIT :batchSize`.
2. Process a batch and close the query.
3. Save the last ID checkpoint.
4. Resume from the checkpoint after restarting the job.
5. Test behavior when new rows are inserted during export.

## 18. Conclusion

Streaming enables processing large result sets without always materializing a full `List`, yet memory savings depend on Spring Data JDBC, the JDBC driver, and how code consumes results. `fetch size` is a driver hint for rows fetched per round trip; it does not limit total results and does not guarantee a fixed heap ceiling.

A JDBC stream can hold a `ResultSet`, `Statement`, connection, and transaction for the entire consumption duration. Use try-with-resources, wrap reads within transaction boundaries, keep per-row processing fast, and monitor the connection pool. Avoid slow API calls or parallelizing over a single JDBC stream.

When jobs are long-running, require retries, or need to return connections between chunks, keyset pagination in batches is usually easier to control. Whether choosing streaming or batching, measure on the target database and driver, document tested fetch sizes and settings, and never generalize one driver's behavior as a guarantee across all DBMSs.
