# Fetch Size, Row Prefetch, and Reducing Network Round Trips

## 1. Why do JDBC queries need fetch size?

When Java runs a `SELECT` query through Oracle JDBC, the database does not necessarily send the entire result set to the application at once. The driver retrieves results in groups of rows (fetch batches). Each time the next batch is needed, the driver may have to exchange more data with the database over the network.

If a query returns many rows and each batch contains only a few rows, the application incurs many fetches. When network latency (round-trip time, RTT) is significant, network wait time can dominate even when the SQL query and database data reads are relatively inexpensive in CPU.

**Fetch size** is a hint for the number of rows the JDBC driver should retrieve in a single fetch. With Oracle JDBC, the related concept is **row prefetch**: the driver asks Oracle to pre-return a batch of rows to reduce network round trips.

Fetch size affects how results are transferred from the database to the client. It does not change SQL conditions, does not limit the total number of rows a query can return, and does not replace pagination. A query returning 100,000 rows still returns all 100,000 rows even if fetch size is 100; the driver simply divides receiving the results into multiple batches.

## 2. Fetch size and Oracle row prefetch

### 2.1. Fetch size in JDBC

JDBC defines `Statement.setFetchSize(int)` and `ResultSet.setFetchSize(int)` so applications can suggest how many rows to fetch each time the driver needs more data.

Example:

```java
try (PreparedStatement statement = connection.prepareStatement(
        "SELECT order_id, order_date, amount FROM orders WHERE status = ?")) {
    statement.setString(1, "SHIPPED");
    statement.setFetchSize(200);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long orderId = resultSet.getLong("order_id");
            Date orderDate = resultSet.getDate("order_date");
            BigDecimal amount = resultSet.getBigDecimal("amount");
            process(orderId, orderDate, amount);
        }
    }
}
```

Here, `200` is the suggested number of rows for the driver to fetch per batch. JDBC defines this as a hint; the driver may apply it in its own way and impose limits depending on result set type or returned data types.

The default value of `Statement.getFetchSize()` in JDBC may be `0`, meaning the application has not provided a custom hint. In that case, the driver uses its own default. Do not interpret `0` as Oracle fetching no rows or fetching the entire result set at once.

### 2.2. Oracle row prefetch

Oracle JDBC refers to batched fetching as row prefetch. In Oracle JDBC, the default row prefetch is typically 10 rows if not configured otherwise. The driver fetches the first batch upon query execution and fetches subsequent batches when the application reads past already-buffered rows.

JDBC `setFetchSize` is the standard, portable approach across JDBC drivers. Oracle JDBC maps fetch size onto the driver's row prefetch mechanism. Oracle also provides dedicated APIs such as `OracleStatement.setRowPrefetch(int)` and connection-level defaults via corresponding Oracle APIs in some driver versions.

When developing new applications, prefer JDBC `setFetchSize` to avoid coupling to Oracle-specific APIs unless specialized capabilities are required. If an application uses Oracle's row prefetch API, consult the documentation for the exact `ojdbc` version and avoid configuring both mechanisms with conflicting values.

### 2.3. Configuring at statement or connection level?

Fetch size can be configured at multiple scopes:

| Scope | How to configure | When appropriate |
|---|---|---|
| Single SQL statement | `PreparedStatement.setFetchSize(n)` | Specific queries with distinct data volume/row width |
| Single ResultSet | `ResultSet.setFetchSize(n)` | Changing the fetch hint for an open result set, if supported by driver |
| Oracle statement API | `OracleStatement.setRowPrefetch(n)` | Application intentionally uses Oracle-specific APIs |
| Connection/driver default | Oracle connection/driver default row prefetch configuration | Setting a general baseline for statements using that connection |

Statement-level fetch size is usually easier to control because different queries return different column counts and row sizes. An overly large connection-wide default can inflate memory across many concurrent result sets, including small queries that do not need large batches.

## 3. How fetch batches reduce network round trips

### 3.1. Row count and fetch size example

Suppose a query returns 10,000 rows and each fetch retrieves up to one batch per fetch size. The approximate theoretical number of fetch batches is:

\[
Number\ of\ batches \approx \left\lceil \frac{N}{F} \right\rceil
\]

Where:

- (N): total result rows.
- (F): fetch size/row prefetch.

| Total rows | Fetch size | Approximate fetch batches |
|---:|---:|---:|
| 10,000 | 10 | 1,000 |
| 10,000 | 100 | 100 |
| 10,000 | 200 | 50 |
| 10,000 | 500 | 20 |
| 10,000 | 1,000 | 10 |

This is an estimate of batch count, not the exact round-trip count for every SQL statement. Execution, parsing, metadata, LOB access, protocol overhead, and driver-specific behavior can add extra network exchanges. In many cases, the first batch is returned with the execution response, so do not mechanically add one round trip per batch.

### 3.2. Impact of network latency

Suppose RTT between application and database is 8 ms. If a query requires 1,000 fetch batches and each batch needs a network exchange, theoretical network wait time alone can reach roughly:

\[
1,000 \times 8\ ms = 8,000\ ms
\]

Increasing fetch size to reduce batches to 100 cuts theoretical RTT wait down to roughly 800 ms. Actual elapsed time still depends on database processing, data transfer, deserialization, application row processing, and pipelining overlap between stages.

This explains why increasing fetch size noticeably improves queries over WANs or high-RTT networks, whereas the impact may be smaller on low-latency LANs.

### 3.3. Fetch size does not make SQL run faster in the database

Fetch size primarily reduces round trips for transferring results. It does not automatically improve:

- Access paths or indexes chosen by the optimizer.
- Join order and join methods.
- Number of database blocks read.
- Predicates or cardinality estimates.
- SQL expression computation time.

If SQL is full-scanning billions of rows when only a small subset is needed, increasing fetch size does not replace SQL tuning. Distinguish database execution time from client fetch and result-processing wait time.

## 4. Choosing an appropriate fetch size

### 4.1. There is no single optimal number for every query

A larger fetch size generally means fewer batches and round trips, but the driver must hold more data in memory per batch. A batch of 500 rows with three short numeric columns differs completely from 500 rows containing large `VARCHAR2`, `RAW`, or LOB columns.

Factors influencing selection:

- RTT between JVM and database.
- Expected total rows and how fast the application consumes the result set.
- Number of selected columns and average row size.
- Number of concurrently open result sets and request concurrency.
- JVM heap memory and allocation/GC pressure.
- Data types, especially LOBs and streaming types.
- Driver version, statement type, and scrollability.

### 4.2. Start with a moderate value

You can test values such as 50, 100, 200, 500, and 1,000 on a representative workload. These are test points, not fixed recommended values. Compare throughput, p95/p99 latency, fetch/round-trip count, heap usage, and GC.

Example:

```java
int[] fetchSizes = {50, 100, 200, 500, 1000};

for (int fetchSize : fetchSizes) {
    try (PreparedStatement statement = connection.prepareStatement(SQL)) {
        statement.setFetchSize(fetchSize);
        // Execute and consume the complete ResultSet.
    }
}
```

When benchmarking, run with identical data, bind values, concurrency, and result consumption. Do not measure `executeQuery()` alone: many drivers return the first batch during execution while fetching the bulk of rows inside the `ResultSet.next()` loop.

### 4.3. Estimating batch memory

Rough estimate of data per batch:

\[
Batch\ memory \approx F \times Average\ row\ size
\]

For example, if one row after conversion and storage in the driver/application averages 2 KB, a fetch size of 500 equals roughly 1 MB of raw data per batch. Actual memory can be higher due to object overhead, encoding, driver buffers, and temporary objects.

If 40 concurrent result sets run with fetch size 500, total data/buffers can grow substantially. Therefore, evaluate concurrency rather than a single isolated query.

### 4.4. Queries returning few rows

If a query typically returns only 5–20 rows, raising fetch size to 500 may bring no benefit. The first batch already holds the entire result, and the driver may allocate larger buffers than necessary. Tailor fetch size to query characteristics instead of setting an excessively large application-wide value.

## 5. Configuration in Oracle JDBC

### 5.1. Using JDBC setFetchSize

This is the generally recommended approach:

```java
String sql = """
    SELECT order_id, customer_id, order_date, amount
    FROM orders
    WHERE order_date >= ?
    ORDER BY order_date, order_id
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setDate(1, Date.valueOf("2026-01-01"));
    statement.setFetchSize(200);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long orderId = resultSet.getLong(1);
            long customerId = resultSet.getLong(2);
            LocalDate orderDate = resultSet.getDate(3).toLocalDate();
            BigDecimal amount = resultSet.getBigDecimal(4);

            processOrder(orderId, customerId, orderDate, amount);
        }
    }
}
```

Setting fetch size before `executeQuery()` ensures the setting applies to the result set from the start. `try-with-resources` closes the result set, statement, and connection properly. In applications using connection pools, `close()` normally returns the connection to the pool rather than closing the physical connection.

### 5.2. Setting fetch size on ResultSet

JDBC also permits:

```java
try (PreparedStatement statement = connection.prepareStatement(SQL);
     ResultSet resultSet = statement.executeQuery()) {

    resultSet.setFetchSize(300);

    while (resultSet.next()) {
        process(resultSet);
    }
}
```

Changing fetch size after the result set is created may affect only subsequent fetches and depends on the driver. For predictable behavior, configure it on the statement before execution. If mid-stream adjustment is needed, verify behavior on your exact Oracle JDBC version.

### 5.3. Oracle-specific row prefetch API

Oracle JDBC provides specialized APIs to set row prefetch, for example:

```java
import oracle.jdbc.OracleStatement;

try (PreparedStatement statement = connection.prepareStatement(SQL)) {
    OracleStatement oracleStatement = statement.unwrap(OracleStatement.class);
    oracleStatement.setRowPrefetch(200);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            process(resultSet);
        }
    }
}
```

`unwrap` is the standard JDBC way to access vendor-specific interfaces when supported by the driver. APIs and classes must be verified against the exact `ojdbc` version; in portable code, prefer `Statement.setFetchSize`.

Do not call both `setFetchSize(100)` and `setRowPrefetch(500)` and assume which value will take effect. Oracle JDBC maps between JDBC fetch size and row prefetch; precedence rules can depend on call order and driver version. Pick one API, configure one clear value, and verify through measurement.

### 5.4. Connection/driver-level default configuration

Oracle JDBC provides mechanisms to set a default row prefetch for a connection/driver. Exact configuration depends on version; for example, the Oracle connection API may expose `setDefaultRowPrefetch(int)` or a corresponding connection property.

Only set a connection-wide default when most queries in the workload share similar characteristics. If an application mixes small queries, large queries, and queries with LOBs, let each DAO/repository set custom fetch sizes for queries needing optimization.

Avoid copying property names from old driver examples into a newer `ojdbc` without checking documentation. Oracle may change property/API names or behavior across versions.

## 6. Relationship between fetch size, pagination, and streaming

### 6.1. Fetch size is not pagination

Fetch size governs how many rows the driver retrieves per batch; pagination limits or slices the result set at the SQL/application level.

Example pagination using `OFFSET/FETCH`:

```sql
SELECT order_id, order_date, amount
FROM orders
ORDER BY order_date, order_id
OFFSET :offset ROWS FETCH NEXT :page_size ROWS ONLY;
```

A fetch size of 200 with `page_size=50` still yields at most 50 rows on the page. Conversely, a fetch size of 200 on an unbounded SQL query can still read millions of rows across many batches.

Pagination is useful when limiting data per request, supporting UIs, or avoiding long-lived result sets. Fetch size is useful when streaming a large result set without fetching only a few rows per network trip.

### 6.2. Keyset pagination for large datasets

For deep pages, large `OFFSET` values force the database to skip many rows before returning the page. Keyset pagination uses the last sort key of the previous page to fetch the next page:

```sql
SELECT order_id, order_date, amount
FROM orders
WHERE (order_date, order_id) > (:last_order_date, :last_order_id)
ORDER BY order_date, order_id
FETCH FIRST :page_size ROWS ONLY;
```

Row-value comparison examples require checking syntax and semantics support per Oracle release; equivalent conditions can be written with `OR` predicates if needed. Sort keys must define a deterministic order, typically including the primary key as a tie-breaker.

### 6.3. Streaming result sets

To process large results, read row by row and process/write to the destination rather than collecting the entire result into a `List`:

```java
try (PreparedStatement statement = connection.prepareStatement(SQL)) {
    statement.setFetchSize(500);

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            exportRow(rs);
        }
    }
}
```

Fetch size bounds how many rows the driver buffers per batch, yet the application can still exhaust heap if `exportRow` retains every object in memory. Process each row and release references once done.

An open ResultSet typically holds the statement and connection until finished/closed. Do not stream while performing long-running non-database work, as holding connections long can exhaust the pool. When streaming very large datasets for extended periods, consider paging or writing to staging files/batches with appropriate transaction boundaries.

## 7. Special cases: LOB, LONG, and scrollable ResultSets

### 7.1. LOBs and streaming data types

`BLOB`, `CLOB`, `NCLOB`, `LONG`, or `LONG RAW` columns may be handled by the driver via streaming or locators, unlike short numeric/text columns. Oracle JDBC applies row prefetch restrictions/adjustments for some of these types; in certain cases, the driver lowers prefetch to 1 for safe handling.

If a query includes LOBs, do not assume a fetch size of 500 will always batch 500 rows like a NUMBER/VARCHAR2-only query. Reading LOB content can also trigger extra network round trips depending on size and stream consumption.

For large LOBs:

- Select LOBs only when genuinely needed; avoid `SELECT *` if LOB contents are unused.
- Read LOBs via streams/chunks rather than materializing everything into huge byte arrays or Strings.
- Close streams/LOB locators and result sets properly.
- Measure metadata queries separately from LOB content downloads.
- Consult Oracle JDBC documentation for your exact driver version regarding specific prefetch limits.

### 7.2. Scrollable ResultSets

Scrollable result sets allow moving the cursor forward/backward or to arbitrary positions, unlike forward-only result sets used for sequential reading. Scrollability can increase memory/caching and affect how the driver fetches rows.

If the application only iterates in one direction:

```java
connection.prepareStatement(
    SQL,
    ResultSet.TYPE_FORWARD_ONLY,
    ResultSet.CONCUR_READ_ONLY
);
```

Forward-only/read-only generally suits exports and batch processing. Only use scrollable result sets when business logic truly requires cursor navigation.

### 7.3. ResultSet holdability

Holdability determines whether a ResultSet remains open or closes when a transaction commits. This attribute is separate from fetch size. Do not use holdability to optimize network fetching; choose a lifecycle that avoids holding cursors/connections longer than needed.

## 8. Fetch size and related JDBC settings

### 8.1. Fetch size is not setMaxRows

`Statement.setMaxRows(n)` limits the maximum total rows returned by a ResultSet under JDBC. `setFetchSize(n)` is strictly a batch fetch hint. The two APIs serve different purposes:

```java
statement.setMaxRows(1000);   // limits total visible rows
statement.setFetchSize(200);  // hints fetching ~200 rows per batch
```

If `maxRows=1000` is set, the application cannot read row 1001 from the ResultSet, even if the database has more matching rows. Setting only fetch size 200 still lets the application read every matching row.

### 8.2. Fetch size is not batch update size

`setFetchSize` applies to reading ResultSets. Batch updates use `addBatch()` and `executeBatch()` to group DML; that is a separate mechanism not controlled by fetch size.

```java
try (PreparedStatement statement = connection.prepareStatement(
        "INSERT INTO audit_log(id, message) VALUES (?, ?)")) {
    for (AuditRecord record : records) {
        statement.setLong(1, record.id());
        statement.setString(2, record.message());
        statement.addBatch();
    }
    statement.executeBatch();
}
```

Batch updates reduce DML round trips, whereas fetch size reduces round trips when retrieving query results. Do not confuse the two mechanisms just because both group data into batches.

### 8.3. Fetch direction

`Statement.setFetchDirection()` is a separate hint from fetch size. For example, `FETCH_FORWARD` describes the direction the application intends to traverse the result set. It does not set the number of rows per batch and does not replace `setFetchSize`.

## 9. Measuring effectiveness

### 9.1. Measure the entire ResultSet consumption process

Do not measure `executeQuery()` alone. Measure from before execution until the entire result set is consumed:

```java
long start = System.nanoTime();
long rows = 0;

try (PreparedStatement statement = connection.prepareStatement(SQL)) {
    statement.setFetchSize(fetchSize);

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            consume(rs);
            rows++;
        }
    }
}

long elapsedNanos = System.nanoTime() - start;
double elapsedMillis = elapsedNanos / 1_000_000.0;
System.out.printf("fetchSize=%d rows=%d elapsed=%.2f ms%n",
        fetchSize, rows, elapsedMillis);
```

Ensure `consume(rs)` performs identical work across benchmark runs. If one benchmark only calls `next()` while another parses JSON or writes files, the results are incomparable.

### 9.2. Metrics to observe

- Total elapsed time from execution through the last row.
- Separate execute time and fetch/consume time if instrumentation permits.
- Rows received and fetch/batch round-trip counts from driver metrics or tracing.
- Throughput (rows/sec) and p50/p95/p99 latency.
- Heap usage, allocation rate, GC pauses, and peak memory.
- Active connections, connection hold time, and pool wait time.
- Network bytes/packets and RTT when network tooling is available.
- Database CPU, logical reads, physical reads, and wait events to see whether the bottleneck lies in the DB.

### 9.3. Designing a fair benchmark

1. Use identical SQL, bind values, and data.
2. Keep fetch direction, result set type, and row processing identical.
3. Run multiple iterations to separate cache/warm-up effects.
4. Test several fetch sizes, from small to large.
5. Run both single-client and production-like concurrency levels.
6. Record heap/GC and tail latency, not just averages.
7. Benchmark queries with LOBs and wide rows separately.
8. Select values for representative workloads, then monitor post-deployment.

If raising fetch size cuts round trips yet spikes heap/GC or reduces concurrency, it may be a poor trade-off. The goal is optimizing overall throughput/latency within resource bounds.

## 10. Common configuration mistakes

### 10.1. Setting an overly large fetch size for every query

A very large value can inflate buffer memory, especially when many queries run concurrently or rows are wide. Use per-query values or a modest default, then benchmark.

### 10.2. Assuming fetch size caps total results

An application sets fetch size 100 yet still reads 1 million rows, because 100 is rows per batch. To cap total rows, use SQL predicates, pagination, or `setMaxRows` as appropriate.

### 10.3. Measuring only executeQuery

If the driver returns the first batch during execution, measuring `executeQuery()` alone misses most fetch time. Measure until the `ResultSet.next()` loop completes.

### 10.4. Holding the entire dataset in a List

Increasing fetch size does not stop an application from accumulating every object on the heap. For large results, process row by row or page by page and write incrementally to the destination.

### 10.5. LOB query results do not improve as expected

The driver may adjust row prefetch when queries include LOB/streaming types. Furthermore, reading LOB contents can require separate round trips. Benchmark LOB queries separately and check API/driver documentation.

### 10.6. Setting fetch size after the statement has executed

Setting fetch size before execution avoids relying on how the driver handles changing fetch size on an already-open ResultSet. If changing it on ResultSet, verify whether it takes effect on the next fetch in your driver.

### 10.7. Confusing fetch size with array fetch in other APIs

OCI, ODP.NET, PL/SQL bulk collect, and Oracle JDBC use similar buffer concepts, but their APIs and semantics differ. Never copy values or formulas from another driver into JDBC without checking the matching docs.

## 11. Adoption workflow in Java applications

1. Identify queries returning many rows and showing signs of network fetch wait.
2. Measure elapsed time from execution through full ResultSet consumption, alongside RTT and actual row counts.
3. Inspect data types and row sizes; watch for LOBs, LONGs, and scrollable result sets.
4. Set `PreparedStatement.setFetchSize()` before `executeQuery()` for that query.
5. Test reasonable values such as 50, 100, 200, 500, and 1,000.
6. Measure round trips/batches, throughput, p95/p99 latency, heap, GC, and connection hold time.
7. Keep forward-only/read-only if sequential reading suffices.
8. Never hold connections during lengthy non-database processing; close ResultSets/Statements and return connections promptly.
9. If total results are huge, use pagination/keyset pagination or streaming; never expect fetch size to cap total rows.
10. Document fetch sizes per query and monitor post-deployment when load, drivers, or network conditions change.

## 12. Principles to remember

- JDBC fetch size is a hint for rows per fetch batch; Oracle JDBC implements it via row prefetch.
- Oracle JDBC typically defaults row prefetch to 10 rows unless configured otherwise; verify your exact driver version.
- Increasing fetch size usually reduces fetch round trips while increasing client memory/buffering.
- Fetch size does not alter SQL, cap total results, or replace pagination.
- Set fetch size on the statement before execution for predictable behavior; prefer standard JDBC APIs unless Oracle-specific APIs are needed.
- Queries with LOB/LONG/streaming data may have special prefetch rules and extra round trips when reading contents.
- Measure the full ResultSet reading lifecycle, not `executeQuery()` alone.
- Benchmark under realistic concurrency and observe heap, GC, network, DB waits, and connection pools.
- For very large results, process row by row or page by page; never retain entire result sets in heap.

## Oracle reference documentation

- [Oracle Database 19c JDBC Developer's Guide — Row Prefetching](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/performance-extensions.html)
- [Oracle Database 19c JDBC Developer's Guide — Performance Extensions](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/)
- [Oracle Database 19c JDBC Java API Reference — OracleStatement](https://docs.oracle.com/en/database/oracle/oracle-database/19/jajdb/)
- [Java SE API — Statement.setFetchSize](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Statement.html#setFetchSize(int))
- [Java SE API — ResultSet.setFetchSize](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/ResultSet.html#setFetchSize(int))
