# Closing Streams, Fetch Size, and Connection Hold Time in Spring Data JPA

Spring Data JPA can return query results as a Java `Stream<T>` to process a large dataset element by element. This is useful for exports, reconciliation, and bulk processing, but requires properly managing three related resources: the Java Stream, the JDBC ResultSet/Statement, and the transaction/persistence context.

There are three critical rules:

1. **Always close the Stream**, even on early termination or when processing throws an exception.
2. **Consume the Stream within an open transaction** because the ResultSet and Statement are typically tied to the transaction and connection.
3. **Setting fetch size alone does not guarantee streaming**. The JPA provider and JDBC driver must support batched fetching; verify on a real database.

A forgotten Stream can hold a connection from the pool. A properly closed Stream whose driver still buffers the entire ResultSet can still consume excessive heap. Fetch size, transaction boundaries, and per-row processing time must be designed together.

## 1. Which Layers Participate in a Spring Data JPA Stream Query?

When calling a repository method returning `Stream<T>`, several layers are involved:

- **Java Stream:** provides operations such as `filter`, `map`, `forEach`, `findFirst`, and `count`.
- **Spring Data JPA:** creates the query and returns a Stream from the JPA provider.
- **JPA provider:** typically Hibernate, managing the EntityManager, persistence context, and result retrieval.
- **JDBC driver:** manages the Statement, ResultSet, fetch size, and communication with the database.
- **Database:** executes the query; depending on driver and configuration, data may be read via a cursor or sent to the client differently.

Thus, `Stream<T>` is a result-consumption interface in Java. It does not by itself guarantee the database sends one row at a time, nor does it guarantee constant memory usage.

### 1.1. How Does Stream Differ from List?

| Aspect | `List<T>` | `Stream<T>` |
|---|---|---|
| Usage | Receives a materialized collection | Consumes results through a pipeline |
| Resource lifecycle | Usually ends after the query builds the result | May hold ResultSet/Statement/connection open while reading |
| Closing resources | List does not need closing | Stream must be closed when attached to resources |
| Batched retrieval | Usually depends on how provider materializes collections | Can use cursors/fetch size if provider and driver support it |
| Memory | Can grow with total row count | Can be lower, though not guaranteed solely by the Stream type |
| Multiple passes | Collection can be iterated multiple times | Stream can only be consumed once |

A Stream is consumed by a terminal operation such as `forEach`, `count`, or `findFirst`. Once a terminal operation runs, the Stream cannot be reused. If a Stream owns off-heap/external resources, close it with try-with-resources.

### 1.2. A Stream Query Is Not a Reactive Stream

`java.util.stream.Stream` is a sequential or parallel processing API on the JVM. It does not provide backpressure or a non-blocking I/O model like Reactor `Flux`.

Spring Data JPA still uses JDBC and typically occupies a connection while reading. Do not choose `Stream<T>` expecting it to turn JPA into reactive database access.

## 2. Declaring a Repository Method Returning Stream

The example below reads orders from a given timestamp, sorted by ID, and returns DTOs for export.

### 2.1. A DTO Containing Only Needed Data

Create `OrderExportRow.java`:

~~~java
package com.example.orders;

import java.math.BigDecimal;
import java.time.Instant;

public record OrderExportRow(
        Long id,
        Instant createdAt,
        BigDecimal total) {
}
~~~

Using a DTO avoids holding unnecessary managed entities and lazy associations in the persistence context. For exports, usually only ID, creation time, and total amount are needed; there is no need to load the entire entity graph.

### 2.2. Repository Stream Query

Create the method in `OrderRepository.java`:

~~~java
package com.example.orders;

import java.time.Instant;
import java.util.stream.Stream;
import jakarta.persistence.QueryHint;
import org.hibernate.jpa.HibernateHints;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.jpa.repository.QueryHints;
import org.springframework.data.repository.query.Param;

public interface OrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query("""
           select new com.example.orders.OrderExportRow(
               o.id,
               o.createdAt,
               o.total
           )
           from PurchaseOrder o
           where o.createdAt >= :from
           order by o.id
           """)
    @QueryHints(
        value = @QueryHint(
            name = HibernateHints.HINT_FETCH_SIZE,
            value = "200"
        )
    )
    Stream<OrderExportRow> streamForExport(
            @Param("from") Instant from);
}
~~~

This example uses Hibernate. `HibernateHints.HINT_FETCH_SIZE` is a Hibernate-specific hint, not a portable Jakarta Persistence fetch-size hint. The value `200` is merely a starting point for benchmarking, not an optimal figure for every query or driver.

The query uses a constructor expression to fetch only the fields needed for export. `order by o.id` provides a stable order; it is also useful if migrating to keyset batching later.

If not using Hibernate, consult your provider's documentation to configure JDBC fetch size. Do not assume another provider understands the `org.hibernate.fetchSize` hint.

### 2.3. Global Hibernate Fetch Size Configuration

You can set a default fetch size:

~~~properties
spring.jpa.properties.hibernate.jdbc.fetch_size=200
~~~

This setting applies at the Hibernate/JDBC level to eligible statements. If only one query needs streaming, a per-query hint limits the scope of impact.

Avoid setting multiple different values simultaneously and guessing which wins. Pick one configuration approach, inspect the actual Statement, and verify the driver uses it.

## 3. Always Close Streams with try-with-resources

`Stream` implements `AutoCloseable` via `BaseStream`. Use try-with-resources to ensure `close()` is invoked when:

- All results have been read.
- Stopping early via `findFirst`, `limit`, or business logic.
- An exception occurs during processing.
- The caller exits the block via return.

Example:

~~~java
try (Stream<OrderExportRow> rows =
             orderRepository.streamForExport(from)) {
    rows.forEach(this::writeRow);
}
~~~

This is the proper resource-lifecycle pattern. Do not simply call `rows.count()` or `rows.forEach(...)` and leave the Stream unclosed.

### 3.1. Failing to Close a Stream Can Leak Resources

If a Stream is attached to a JDBC ResultSet and Statement, failing to close it can keep:

- An open ResultSet.
- A Statement actively executing or holding results.
- A Connection borrowed from the connection pool.
- The transaction and persistence context enclosing the query.

When multiple requests leave Streams open, the connection pool can become exhausted even if the database is not overloaded. Other requests must wait for connections or time out.

### 3.2. Early Stopping Still Requires Closing

Example fetching only the first row:

~~~java
try (Stream<OrderExportRow> rows =
             orderRepository.streamForExport(from)) {
    return rows.findFirst();
}
~~~

`findFirst()` is a terminal operation that can stop before reading the entire ResultSet. Try-with-resources still closes the Stream and releases resources.

Do not assume operations like `limit(100)` automatically close the Stream. They only limit elements emitted by the pipeline; resource-closing responsibility remains with the caller.

### 3.3. Do Not Return a Stream from a Service Transaction

Dangerous pattern:

~~~java
@Transactional(readOnly = true)
public Stream<OrderExportRow> openExport(Instant from) {
    return repository.streamForExport(from);
}
~~~

When the method returns, the Spring-managed transaction may end. The external caller only starts consuming the Stream afterward, while the ResultSet's required transaction/connection is no longer valid.

Consume and close the Stream inside the transactional service method. Do not return a Stream from a service to a controller or another thread for later processing.

## 4. The Transaction Must Enclose Stream Consumption

Spring Data JPA notes that Stream queries are tied to resources like JDBC ResultSets or Statements and typically depend on an enclosing transaction. Therefore, the transaction must stay open for the entire duration of Stream reading.

Service example:

~~~java
package com.example.orders;

import java.io.BufferedWriter;
import java.io.IOException;
import java.time.Instant;
import java.util.stream.Stream;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderExportService {

    private final OrderRepository orders;

    public OrderExportService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(readOnly = true)
    public void exportSince(
            Instant from,
            BufferedWriter writer) throws IOException {

        try (Stream<OrderExportRow> rows =
                     orders.streamForExport(from)) {

            var iterator = rows.iterator();

            while (iterator.hasNext()) {
                OrderExportRow row = iterator.next();

                writer.write(row.id() + ","
                        + row.createdAt() + ","
                        + row.total());
                writer.newLine();
            }
        }
    }
}
~~~

The service method opens a transaction before calling the repository, consumes the Stream inside that transaction, and closes the Stream before the method exits. When the method returns, Spring completes the transaction.

The example assumes the caller created `BufferedWriter` and is responsible for closing the writer. In real applications, write to a temporary file, complete the export successfully, and then rename the file to avoid publishing an incomplete file if the query or write fails.

### 4.1. readOnly Does Not Mean the Connection Is Released Early

`@Transactional(readOnly = true)` can help the transaction manager/provider optimize read paths. It does not shorten the transaction lifecycle and does not close the ResultSet while the Stream remains open.

The connection must still be held for as long as the query consumes results. An export taking 20 minutes can hold a connection for roughly that duration, even though the transaction is read-only.

### 4.2. Note on Spring Proxies

`@Transactional` is typically applied via a Spring AOP proxy. If a method inside the same class directly calls another method with `@Transactional`, the internal call (self-invocation) normally bypasses the proxy under default proxy mode.

Place transaction boundaries on public service methods called from another bean or extract Stream reading into a separate service. Do not assume annotations automatically open transactions for internal calls.

## 5. What Is Fetch Size?

Fetch size is a hint to the JDBC driver indicating how many rows to retrieve from the database in one round trip when more results are needed.

Example:

~~~java
query.setHint(HibernateHints.HINT_FETCH_SIZE, 200);
~~~

Or using Hibernate configuration:

~~~properties
spring.jpa.properties.hibernate.jdbc.fetch_size=200
~~~

If the driver supports cursor fetching, a fetch size of 200 can cause the driver to retrieve roughly 200 rows per trip instead of buffering the entire result set upfront.

Fetch size is a **JDBC hint**. Under the JDBC contract, a driver may ignore the hint or handle it differently depending on the database, driver, ResultSet type, and connection configuration. Verify real behavior rather than relying solely on annotations.

### 5.1. Fetch Size Is Not Page Size

| Concept | Meaning |
|---|---|
| Fetch size | Number of rows the driver is hinted to retrieve per database trip |
| Page size | Number of rows the application requests in one query page |
| SQL LIMIT/FETCH FIRST | Limits the total number of rows a query returns |
| JDBC batch size | Number of write statements grouped in one batch |
| Hibernate batch fetch size | Number of associations/proxies that can be batch-loaded |

Fetch size does not limit the total number of rows a query returns. If a query matches 2 million rows and fetch size is 200, the application can still read all 2 million rows across multiple trips.

Fetch size is also not `hibernate.jdbc.batch_size`, which relates to batching write statements.

### 5.2. How to Choose Fetch Size?

Small fetch size:

- Smaller client-side buffer.
- May require more round trips.
- Suitable when each row is large or memory budget is tight.

Large fetch size:

- Can reduce round-trip count.
- Larger per-trip buffer.
- Can increase heap or driver-side memory.

There is no universal optimal value. Test values like 50, 100, 200, 500, or 1000 with production-like row sizes and network conditions. Measure time to first row, total time, heap, fetch trip count, and connection hold duration.

## 6. Fetch Size Depends on the JDBC Driver

A query hint can be translated into `Statement.setFetchSize()`, but the driver decides how to apply cursors or buffering.

### 6.1. PostgreSQL JDBC (pgJDBC)

Per pgJDBC, by default the driver collects all query results at once. Cursor-based fetching has important prerequisites:

- The connection is not in auto-commit mode.
- The ResultSet is `TYPE_FORWARD_ONLY`.
- The query is a single statement.
- Fetch size is greater than 0.

If these conditions are not met, the driver may silently fall back to fetching the entire ResultSet. Spring transactions normally disable auto-commit within active transactions, yet you should still verify actual connection and statement settings.

Example Hibernate fetch size configuration:

~~~properties
spring.jpa.properties.hibernate.jdbc.fetch_size=200
~~~

With PostgreSQL, do not merely verify that a Stream can iterate through all results. Verify that cursor mode is actually activated on your driver/version.

### 6.2. MySQL Connector/J

MySQL Connector/J by default can fetch the entire ResultSet into client memory. For cursor-based fetching, the driver supports:

- `useCursorFetch=true`.
- `defaultFetchSize` greater than 0 or `setFetchSize()` called on the Statement with a positive value.
- The driver automatically enables server-side prepared statements when cursor fetching is used because the cursor mechanism depends on server-side prepared statements.

JDBC URL example:

~~~properties
spring.datasource.url=jdbc:mysql://localhost:3306/shop?useCursorFetch=true&defaultFetchSize=200
~~~

There is an older row-by-row streaming mechanism using the special fetch size `Integer.MIN_VALUE` with a forward-only/read-only ResultSet. That mechanism has specific constraints, such as requiring the ResultSet to be completely read or closed before using the connection for another query. In JPA applications, prefer driver-supported cursor fetch configuration and test with your actual Connector/J version.

### 6.3. Do Not Apply One Driver's Settings to Every Database

PostgreSQL, MySQL, MariaDB, Oracle, and SQL Server handle ResultSets and fetch sizes differently. There is no single JDBC URL or hint value guaranteeing identical streaming across all databases.

When switching drivers or upgrading databases, re-run integration tests with large datasets and inspect heap/connection metrics.

## 7. Streaming Entities Can Still Increase Memory Usage

A common misconception is that Streams always have low memory usage. With JPA, entities consumed from a Stream can still be attached to the persistence context (first-level cache), just like entities fetched from a collection query.

If processing hundreds of thousands of entities, the persistence context can grow continuously even if the driver only fetches 200 rows per trip.

### 7.1. Prefer DTO Projections for Read-Only Work

The DTO query example from earlier:

~~~java
select new com.example.orders.OrderExportRow(
    o.id,
    o.createdAt,
    o.total
)
from PurchaseOrder o
where o.createdAt >= :from
order by o.id
~~~

DTOs are not managed entities and do not require dirty-checking tracking. This is usually well suited for exports, reporting, and read-only processing.

### 7.2. If Entities Must Be Streamed

If business logic genuinely requires entities:

- Use a read-only transaction when appropriate.
- Do not load unnecessary relationships.
- Avoid mutating entities in a read-only job.
- You can detach entities after processing if lazy associations are no longer needed.
- If using `EntityManager.clear()` periodically, understand that it detaches all managed entities in the persistence context; do not call it while those entities or their lazy relationships are still needed.
- Test how your provider handles the cursor when the persistence context is cleared/detached.

Do not call `clear()` arbitrarily. DTO projections are generally more predictable for large read flows.

### 7.3. Avoid Terminal Operations That Materialize All Results

Approaches like the following can load the entire result set into memory:

~~~java
List<OrderExportRow> all = rows.toList();
~~~

~~~java
Object[] array = rows.toArray();
~~~

If the goal is incremental processing, write/transform each row and drop references afterward. Operations like `sorted()` may need to buffer all data before emitting the first element; avoid them on large Streams unless you have evaluated the cost.

### 7.4. Do Not Use Parallel Streams on a JPA Cursor

Do not call `parallel()` on a Stream tied to a persistence context/JDBC cursor. EntityManager and Hibernate Session are not designed for concurrent manipulation from multiple threads on the same context. JDBC ResultSets are also typically sequential read streams.

If parallel processing is required, read DTO batches in short transactions, close the transaction/connection, and then dispatch batches detached from the persistence context to workers for parallel processing.

## 8. Connection Hold Time and Impact on the Connection Pool

A Stream query typically holds a connection while the ResultSet remains open and the transaction has not completed. This duration includes:

- Time for the database to execute the query.
- Time for the driver to fetch subsequent batches.
- Time for Java to process each row.
- Time to write files, send data, or wait on external systems.
- Time until the transaction completes and the connection returns to the pool.

For example, a query reading 500,000 rows takes only 20 seconds for the database to prepare results, but the application writes to a slow file for 15 minutes. The connection may be held for nearly 15 minutes, even though the database is not computing for most of that time.

### 8.1. The Connection Pool Can Exhaust Even When the Database Is Healthy

Suppose the pool has 20 connections and 20 export jobs each hold a Stream open. Web requests needing other queries will wait for connections. Consequences can include:

- Connection acquisition timeouts.
- Increased request latency.
- HikariCP reporting pending threads.
- One export task degrading interactive request availability.

Increasing pool size is not the default cure. If each export holds a connection too long, a larger pool can overwhelm the database with too many concurrent queries.

### 8.2. Avoid Slow Unrelated Work Inside the Transaction

Do not call HTTP APIs, send emails, wait on message brokers, or perform user-facing I/O while iterating a Stream. These operations extend transactions and connection borrow times.

If sending data to another system is needed, consider reading DTO batches, closing the transaction after each batch, and processing the batch outside. If a consistent snapshot must be guaranteed, explicitly define the isolation/snapshot strategy before splitting transactions.

### 8.3. Long Transactions Can Retain Snapshots and Database Resources

Long-running read transactions can hold snapshots open longer than expected. Exact impacts depend on the database and isolation level; on some engines, old snapshots can delay reclaiming old row versions or increase storage pressure.

Long write transactions can also hold locks longer. Therefore, avoid running a job reading/writing millions of records in a single transaction if it can be processed in chunks with appropriate semantics.

## 9. When to Use Stream vs. Keyset Batch?

Stream fits when:

- A large query needs to be traversed in order.
- The provider and driver genuinely support incremental/cursor fetching.
- Transaction/connection hold time is acceptable.
- Per-row work is lightweight and needs no other queries on the same connection.
- Stream closing can be guaranteed.

Keyset batching is usually a better fit when:

- Exports take a long time or per-row processing is slow.
- Connections must be returned to the pool between chunks.
- Per-batch retries are desired.
- Memory bounds must be strictly explicit.
- A single transaction/snapshot for the entire job is unnecessary, or consistency has been designed separately.

### 9.1. Keyset Pagination by ID Example

Repository:

~~~java
@Query("""
       select new com.example.orders.OrderExportRow(
           o.id,
           o.createdAt,
           o.total
       )
       from PurchaseOrder o
       where o.id > :afterId
       order by o.id
       """)
List<OrderExportRow> readNextBatch(
        @Param("afterId") Long afterId,
        Pageable pageable);
~~~

A reader service loads one batch inside a short transaction:

~~~java
@Service
public class OrderBatchReader {

    private static final int BATCH_SIZE = 500;

    private final OrderRepository orders;

    public OrderBatchReader(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(readOnly = true)
    public List<OrderExportRow> loadAfter(Long lastId) {
        return orders.readNextBatch(
                lastId,
                PageRequest.of(0, BATCH_SIZE)
        );
    }
}
~~~

The orchestrator does not hold a transaction across the whole loop:

~~~java
public void exportAll(OrderBatchReader reader) {
    long lastId = 0L; // Example assumes generated IDs are always positive.

    while (true) {
        List<OrderExportRow> batch = reader.loadAfter(lastId);

        if (batch.isEmpty()) {
            break;
        }

        for (OrderExportRow row : batch) {
            writeRow(row);
            lastId = row.id();
        }
    }
}
~~~

Each `loadAfter` call passes through the Spring proxy, opens a read transaction, loads up to 500 DTOs, and closes the transaction. The orchestrator processes the batch after the reader returns, so the previous batch's connection is released before writing or calling external services.

This is an illustrative example. In real projects, use an initial ID matching your schema, handle errors/retries, persist checkpoints, and ensure the reader is invoked via a bean proxy. If per-batch transactions are desired, do not place a single `@Transactional` wrapping the entire orchestrator.

### 9.2. Keyset Avoids Growing OFFSET Costs

With offset pagination, later pages can force the database to skip more and more rows. Keyset uses `id > lastId` combined with `ORDER BY id`, typically suiting sequential scans of large datasets when indexed by ID.

If ordering uses multiple columns, the keyset predicate must compare the full sort key, such as `(createdAt, id)`, and the order must be uniquely deterministic.

### 9.3. Keyset Does Not Automatically Create a Fixed Snapshot

While the job runs, data may be inserted or updated. Keyset reduces offset-shift issues but does not automatically guarantee an export reflects a single point in time.

If a fixed dataset is required:

- Record a high-water mark, such as the maximum ID at start time, and read only up to that mark.
- Define a policy for rows updated while the job runs.
- If a strictly consistent snapshot is required, pick an appropriate transaction/isolation or database snapshot mechanism and weigh the cost of holding long snapshots.

## 10. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Connection pool does not reclaim connections | Stream was not closed | Use try-with-resources |
| Stream fails after service returns | Transaction ended before caller consumed it | Consume Stream inside the service transaction |
| Heap still grows despite using Stream | Driver buffers everything or entities accumulate in persistence context | Verify cursor fetch, use DTOs, and measure heap |
| Fetch size has no effect | Driver ignores hint or cursor prerequisites missing | Check driver docs, autocommit, and ResultSet mode |
| PostgreSQL still loads everything | Autocommit enabled, fetch size 0, or cursor prerequisites unmet | Use a transaction and positive fetch size; verify pgJDBC |
| MySQL still buffers ResultSet | Cursor fetch disabled or non-positive fetch size | Check `useCursorFetch` and `defaultFetchSize`/query hint |
| Other requests wait for connections | Stream processes too slowly and holds connection | Shorten in-transaction processing or use keyset batching |
| Error running another query while streaming | Driver may disallow another statement on a connection with an active result | Avoid nested queries in loops; fetch needed data via projection/batch |
| LazyInitializationException | Entity/association accessed after context closed or detached | Load required fields inside the query/transaction |
| Duplicate or missing data when paginating | Non-unique order or offset on changing data | Use unique order and suitable keyset |
| Partial export left after exception | Target file written directly before job finishes | Write to a temporary file then publish/rename after success |

## 11. Testing and Observing in Real Environments

A small unit test confirming the repository returns the right rows does not prove the driver is streaming. Integration tests with the real database and JDBC driver are required.

### 11.1. Testing Stream Closing

Example verifying query contents and ensuring callers use try-with-resources:

~~~java
@DataJpaTest
class OrderStreamRepositoryTest {

    @Autowired
    private OrderRepository orders;

    @Test
    void streamReturnsExpectedRows() {
        try (Stream<OrderExportRow> rows =
                     orders.streamForExport(Instant.parse("2026-01-01T00:00:00Z"))) {

            assertThat(rows.map(OrderExportRow::id).toList())
                    .containsExactly(1L, 2L, 3L);
        }
    }
}
~~~

The test assumes fixture data contains three orders with matching IDs and dates. This test verifies content and proper Stream closing; it does not yet prove cursor fetching or memory usage.

### 11.2. Testing Cursor/Fetch Size

With integration tests on a real database:

1. Create a dataset many times larger than the fetch size.
2. Wrap the entire consumption duration in a read-only transaction.
3. Verify the JDBC Statement receives the intended fetch size via datasource/driver instrumentation or a JDBC proxy.
4. Check driver cursor settings, such as autocommit and ResultSet type for PostgreSQL.
5. Observe time to first row and subsequent fetch trips.
6. Measure heap as row counts scale from thousands to hundreds of thousands.
7. Measure active connection hold duration and confirm the connection returns after Stream close/transaction completion.
8. Test exceptions and short-circuiting to confirm resources are released.

Do not rely solely on SQL logs. SQL logs show the query executed, not necessarily whether the driver buffered everything or fetched via a cursor.

### 11.3. Monitoring the Connection Pool

With HikariCP, monitor metrics:

- Active connections.
- Idle connections.
- Pending threads waiting for connections.
- Connection acquisition time.
- Connection usage/hold time.
- Transaction duration.

You can enable leak detection threshold in development/testing environments to detect connections held too long. This is a diagnostic tool; it does not replace closing Streams and should not be set too low in production because it can emit noisy warnings.

### 11.4. Benchmarking Multiple Fetch Sizes

Run the same query and dataset across different fetch size values, such as 50, 100, 200, 500, and 1000. Hold all other factors constant to compare:

- Total read time.
- Time to first row.
- Peak heap and garbage collection.
- Number of fetch trips/round trips if the driver exposes metrics.
- Connection hold duration.
- Impact on other requests when the pool is under concurrent load.

Choose values based on real workloads and drivers. Do not optimize based solely on a single run or an overly small dataset.

## 12. Implementation Checklist

- [ ] Repository methods returning `Stream<T>` are used only for large-dataset reading use cases.
- [ ] Streams are consumed inside a service transaction.
- [ ] Streams are always enclosed in try-with-resources.
- [ ] Streams are never returned across transaction boundaries, controllers, or other threads.
- [ ] DTOs/projections are used when only certain fields are needed.
- [ ] Verified that the persistence context does not accumulate excessive entities.
- [ ] Fetch size is configured per provider/driver and measured.
- [ ] Confirmed the driver actually uses cursor/incremental fetching.
- [ ] For PostgreSQL, verified autocommit, forward-only ResultSet, and positive fetch size.
- [ ] For MySQL Connector/J, verified `useCursorFetch` and positive fetch size.
- [ ] No remote API calls or slow waiting tasks while holding a Stream open.
- [ ] No parallel streams executed on the same persistence context/cursor.
- [ ] Keyset batching fallback available when reducing connection hold time is required.
- [ ] Consistent snapshot requirements defined when data changes during export.
- [ ] Integration tests use the exact production database and JDBC driver.
- [ ] Active/idle/pending connections and connection hold times are monitored.

## 13. References

- [Spring Data JPA — Repository Query Return Types](https://docs.spring.io/spring-data/jpa/reference/repositories/query-return-types-reference.html) — Stream is a resource that can be tied to a ResultSet/Statement; requires an enclosing transaction and must be closed after use.
- [Spring Data Commons — Streaming Query Results](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html) — Stream query examples, try-with-resources, and notes on non-guaranteed incremental fetching.
- [Hibernate JDBC Settings](https://docs.hibernate.org/stable/core/javadocs/org/hibernate/cfg/JdbcSettings.html) — `hibernate.jdbc.fetch_size` and the meaning of the JDBC fetch-size hint.
- [pgJDBC — Getting Results Based on a Cursor](https://jdbc.postgresql.org/documentation/query/) — conditions for cursor-based ResultSets and fetch size.
- [MySQL Connector/J — Performance Extensions](https://dev.mysql.com/doc/connector-j/en/connector-j-connp-props-performance-extensions.html) — `useCursorFetch`, `defaultFetchSize`, and server-side prepared statements.
- [MySQL Connector/J — JDBC API Implementation Notes](https://dev.mysql.com/doc/connector-j/en/connector-j-reference-implementation-notes.html) — streaming ResultSet, cursor fetch, and restrictions while a connection has an active result.

`Stream<T>` helps structure sequential reads, but memory efficiency and connection lifecycles depend on the provider, driver, and transaction. Closing Streams properly, configuring verified fetch sizes, and keeping processing inside the shortest feasible transaction will keep exports more stable. For long-running jobs or tasks calling external services, keyset batching usually provides clearer control over memory, retries, and connection hold time.
