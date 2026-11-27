# Fetch Size, useCursorFetch, and Streaming Large Result Sets

When a query returns hundreds of thousands or millions of rows, how the result is read can decide whether the application uses a few megabytes or exhausts the entire heap. By default, MySQL Connector/J receives and buffers the entire query result on the client side before the application iterates through the `ResultSet`. This approach is simple, but memory usage scales with result size.

Connector/J provides two mechanisms for handling large result sets: the legacy streaming mode via `setFetchSize(Integer.MIN_VALUE)`, and server-side cursors via `useCursorFetch=true` combined with `Statement.setFetchSize(n)` or `PreparedStatement.setFetchSize(n)` with a positive value. The two mechanisms operate differently; choose based on workload, driver version, and processing requirements.

This lesson uses MySQL Connector/J 8.x/9.x with MySQL Server 8.0/8.4. Consult the documentation for your exact deployed Connector/J version, as certain properties and behaviors can vary across releases.

## Objectives

After this lesson, you will be able to:

- Explain why large ResultSets can fill the application heap.
- Distinguish fetch size, SQL row limits, and SQL pagination.
- Enable server-side cursors using `useCursorFetch` and server-side prepared statements.
- Use `setFetchSize()` with a positive value to retrieve data in batches.
- Use legacy streaming mode with `Integer.MIN_VALUE` when appropriate.
- Choose batch sizes, close resources properly, and avoid holding connections/transactions too long.
- Monitor memory, network round trips, processing time, and server impact.

## 1. Why Reading Large ResultSets Requires Memory Care

Example query retrieving all customers:

```sql
SELECT customer_id, full_name, email
FROM customers;
```

If the table holds several million rows, the application can receive a very large result set. With Connector/J's default behavior, the driver reads results from the server and buffers them on the client; only after receiving everything does the application iterate over rows in the `ResultSet`. Required heap depends on row count, column count, string sizes, objects allocated by the driver, and objects retained by the application.

A common mistake is loading every row into a `List<Customer>`:

```java
List<Customer> customers = new ArrayList<>();

try (PreparedStatement ps = connection.prepareStatement(
        "SELECT customer_id, full_name, email FROM customers");
     ResultSet rs = ps.executeQuery()) {
    while (rs.next()) {
        customers.add(new Customer(
            rs.getLong("customer_id"),
            rs.getString("full_name"),
            rs.getString("email")
        ));
    }
}
```

Even when the driver reads in batches, storing all objects in a list still grows memory linearly with total row count. Streaming or cursors only reduce how much `ResultSet` data the driver buffers in memory; the application must also process row by row or flush to a destination in batches rather than accumulating every object in a collection.

## 2. Distinguishing Fetch Size, LIMIT, and Pagination

These three mechanisms solve three different problems:

| Mechanism | Role | Reduces total rows returned by the query? |
|---|---|---|
| `setFetchSize(n)` | Hints or controls how many rows the driver fetches per round trip in supported modes | No |
| `LIMIT n` | Caps how many rows SQL returns | Yes |
| Pagination/keyset pagination | Splits a dataset into multiple smaller queries by page or key | Yes, each query returns only a slice |

`fetchSize=500` does not mean the query returns at most 500 rows. It means the driver can fetch results in batches of roughly 500 rows when a matching fetch mechanism is enabled. If the query returns 2 million rows, the application can still iterate through all 2 million rows.

Example limiting results with SQL:

```sql
SELECT customer_id, full_name
FROM customers
ORDER BY customer_id
LIMIT 500;
```

Example keyset pagination:

```sql
SELECT customer_id, full_name
FROM customers
WHERE customer_id > ?
ORDER BY customer_id
LIMIT 500;
```

Keyset pagination is useful when you want to process page by page, persist checkpoints, and resume after failures. It differs from cursor fetch: each page is a fresh SQL query, whereas cursor fetch keeps a single `ResultSet` open and fetches additional rows from the same result.

## 3. Two Mechanisms for Reading Large Results in Connector/J

### 3.1. Default Mode: Buffered ResultSet

When no special fetch mode is enabled, Connector/J normally buffers the entire result on the client. The advantage is simplicity: results can be read after the query finishes, the driver can support navigation operations per `ResultSet` type, and the connection becomes ready for the next statement once results arrive.

The drawback is heap consumption growing with result size. A query returning many columns or large `TEXT`/`BLOB` fields can trigger `OutOfMemoryError`, frequent GC pauses, or elevated latency.

For small and medium result sets, buffered `ResultSet` is usually the right choice. Do not enable cursors for every query because cursors carry server-side overhead and extra network round trips.

### 3.2. Server-Side Cursor: useCursorFetch

`useCursorFetch=true` asks Connector/J to use a server-side cursor to retrieve results in batches. Cursors are only available via server-side prepared statements, so enabling `useCursorFetch` automatically enables `useServerPrepStmts` in Connector/J.

Configure both properties explicitly in the JDBC URL:

```text
jdbc:mysql://db.example.internal:3306/sales?useServerPrepStmts=true&useCursorFetch=true
```

When cursor fetch is enabled, set a positive integer fetch size before calling `executeQuery()`. You can use `PreparedStatement` for parameterized SQL:

```java
String sql =
    "SELECT customer_id, full_name, email " +
    "FROM customers WHERE customer_id > ? " +
    "ORDER BY customer_id";

try (PreparedStatement ps = connection.prepareStatement(
        sql,
        ResultSet.TYPE_FORWARD_ONLY,
        ResultSet.CONCUR_READ_ONLY)) {

    ps.setLong(1, lastCustomerId);
    ps.setFetchSize(500);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("customer_id");
            String name = rs.getString("full_name");
            String email = rs.getString("email");
            processCustomer(id, name, email);
        }
    }
}
```

In this example, `setFetchSize(500)` is called before `executeQuery()`. The driver retrieves data in batches, reducing the amount of `ResultSet` data held on the client at any one time. The application must still iterate to the end if it wants to process every row.

Connector/J documentation also illustrates cursor fetch with a plain `Statement`:

```java
try (Statement st = connection.createStatement()) {
    st.setFetchSize(500);
    try (ResultSet rs = st.executeQuery(
            "SELECT customer_id, full_name FROM customers")) {
        while (rs.next()) {
            processCustomer(
                rs.getLong("customer_id"),
                rs.getString("full_name")
            );
        }
    }
}
```

For parameterized queries, prefer `PreparedStatement` for safe parameter binding. With either statement type, use forward-only/read-only ResultSets and a positive fetch size when using cursor fetch. Never call `last()`, `absolute()`, or backward-scrolling methods on forward-only results.

### 3.3. Legacy Streaming Mode: Integer.MIN_VALUE

Connector/J also supports a legacy streaming mode. With this mechanism, create a forward-only/read-only statement and call `setFetchSize(Integer.MIN_VALUE)` before execution:

```java
String sql =
    "SELECT customer_id, full_name, email " +
    "FROM customers ORDER BY customer_id";

try (Statement st = connection.createStatement(
        ResultSet.TYPE_FORWARD_ONLY,
        ResultSet.CONCUR_READ_ONLY)) {

    st.setFetchSize(Integer.MIN_VALUE);

    try (ResultSet rs = st.executeQuery(sql)) {
        while (rs.next()) {
            processCustomer(
                rs.getLong("customer_id"),
                rs.getString("full_name"),
                rs.getString("email")
            );
        }
    }
}
```

`Integer.MIN_VALUE` is Connector/J's sentinel value to trigger row-by-row ResultSet streaming; it is not an ordinary negative batch size. This mode reads rows sequentially from the connection rather than using batched server-side cursor fetches.

While a streaming ResultSet remains open, do not execute another statement on the same connection. Consume all rows or close the ResultSet before reusing the connection for another query. Connector/J also notes that the statement is not complete until pending rows are read or the ResultSet is closed; locks held by the statement may only be released when the statement/transaction completes. Therefore, process rows quickly and never hold a streaming ResultSet open while waiting on external work.

Do not combine `Integer.MIN_VALUE` mode with expectations of batched cursor fetches. If positive batch size control is required, use `useCursorFetch=true` with a positive fetch size.

## 4. Configuring useCursorFetch

### 4.1. JDBC URL

Example application configuration:

```properties
db.url=jdbc:mysql://db.example.internal:3306/sales?useServerPrepStmts=true&useCursorFetch=true
db.username=app_reader
```

Never place passwords in URLs or configuration files committed to source control. Retrieve credentials from a secret manager or your deployment environment's secure configuration mechanism.

When using a connection pool, configure the URL/driver properties on the `DataSource` or pool. Every connection created by the pool must receive the intended properties. Avoid enabling `useCursorFetch` in one place while accidentally overriding `useServerPrepStmts` elsewhere.

### 4.2. Default Setting for All Statements

Connector/J provides the `defaultFetchSize` property. Its default value is `0`. When set to a positive integer, the driver calls `setFetchSize(n)` with that value on newly created statements:

```text
jdbc:mysql://db.example.internal:3306/sales?useCursorFetch=true&defaultFetchSize=500
```

`defaultFetchSize` has broad scope because it applies to new statements on the connection. Use it only when most queries need this fetch behavior. In applications with mixed query profiles, calling `setFetchSize()` specifically on large-result queries is usually easier to control.

### 4.3. Verifying Effective Configuration

Do not assume cursors are active solely because the URL contains `useCursorFetch=true`. Verify driver version, DataSource/pool properties, statement fetch size, and ResultSet type. If the server or driver does not support the intended settings, inspect exceptions, warnings, and JDBC logs.

Test a small query with the exact statement configuration in a test environment before deploying large export or batch jobs. Ensure fetch size is set before the statement executes.

## 5. How Do Server-Side Cursors Work?

With server-side prepared statements and cursor fetch, Connector/J sends an execute request in cursor mode. MySQL opens a cursor for the result, and the driver requests batches of rows via the fetch protocol. Instead of transferring the entire result set to the client at once, rows travel across multiple fetches.

This reduces client-side buffering in the driver, but it does not mean the server avoids storing the result. MySQL implements server-side cursors by materializing results into an internal temporary table. That temporary table may start in memory and spill to disk once it exceeds configured thresholds. Consequently, the query can consume server-side memory or disk, incur cursor creation overhead, and perform multiple network round trips.

MySQL server-side cursors are read-only, non-scrollable, and non-holdable: you cannot update rows through the cursor, scroll arbitrarily, or keep using the cursor after a transaction commits. Do not use cursor fetch if the application needs updatable ResultSets or random navigation. When scrolling or random access is required, consider buffered ResultSets for moderate sizes or design paginated queries.

## 6. Choosing the Right Fetch Size

Fetch size is a trade-off between client memory, network round trips, and processing overhead:

| Fetch size | Pros | Cons |
|---|---|---|
| Small (e.g., 50–100) | Each batch uses very little client memory | Many fetch round trips, potentially raising latency and network overhead |
| Moderate (e.g., 500–1,000) | Balances memory and round trips across many workloads | Still needs measurement against actual row sizes |
| Large (e.g., 5,000–10,000) | Fewer fetch round trips, can improve throughput | Larger batches consume more heap and increase per-batch processing time |

These numbers are starting points for benchmarking, not universal optimal defaults. A row with a few small integers differs dramatically from a row containing multi-megabyte JSON or BLOBs. With wide rows, the same fetch size can produce vastly different byte sizes per batch.

Selection process:

1. Measure average row size and row size distribution.
2. Run the same query with several fetch sizes, such as 100, 500, and 1,000.
3. Monitor heap, GC pauses, query time, total iteration time, network round trips, and server CPU/I/O.
4. Verify processed row counts and output data.
5. Choose a value meeting memory budgets and SLAs; re-benchmark when schemas or data change.

If the application processes each row very slowly, shrinking fetch size will not necessarily make the query finish faster. The cursor still holds resources and the connection for as long as the ResultSet stays open.

## 7. Managing ResultSet, Connection, and Transaction Lifecycles

### 7.1. Always Close Resources

Use try-with-resources to close ResultSets and statements even when processing throws an exception:

```java
try (PreparedStatement ps = connection.prepareStatement(
        sql,
        ResultSet.TYPE_FORWARD_ONLY,
        ResultSet.CONCUR_READ_ONLY)) {

    ps.setFetchSize(500);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            processRow(rs);
        }
    }
}
```

If the connection came from a pool, return it to the pool after the ResultSet and statement are closed. An unclosed ResultSet can hold cursors, memory, sockets, and a connection slot. If a job stops midway, close statements/connections in `finally` or try-with-resources to free resources.

### 7.2. Connection Pools and Long Processing

Streaming holds a connection for the entire duration the application reads rows. If each job holds a connection for minutes, the pool can run out of connections for regular requests. Isolate export/reporting workloads from transactional pools if needed, set sensible timeouts, and cap concurrent jobs.

Never keep a ResultSet open while waiting on external network calls, slow APIs, or user input. When long processing is required, consider reading one batch, closing resources, saving a checkpoint, and continuing with keyset pagination in the next query.

### 7.3. Transactions and Snapshots

Server-side cursors are not held open across commits. If a ResultSet is read inside an explicit transaction, do not commit or roll back before finishing reads and closing the cursor; ending the transaction can close the cursor or render the ResultSet unusable. In InnoDB, a long-running consistent read can also retain old snapshots, delaying undo history purge and increasing storage pressure.

Do not default to `autoCommit=false` merely to use fetch size. Choose transaction boundaries based on business consistency requirements. For long reports, consider snapshot consistency, read duration, purge impact, and splitting queries by key ranges.

## 8. Streaming vs. Keyset Pagination

Streaming/cursor fetch fits when scanning a result continuously in a single run, such as data exports, application-side aggregations, or streaming data to another system.

Keyset pagination fits when you need to:

- Persist checkpoints and resume after a job stops.
- Release connections between batches.
- Bound transaction duration and snapshot retention.
- Run multiple workers across non-overlapping key ranges.

Example keyset pagination loop:

```java
long lastId = 0L;
int pageSize = 500;
long upperBound = readMaxCustomerId(dataSource);

while (lastId < upperBound) {
    String sql =
        "SELECT customer_id, full_name, email " +
        "FROM customers " +
        "WHERE customer_id > ? AND customer_id <= ? " +
        "ORDER BY customer_id LIMIT ?";

    int rows = 0;
    try (Connection conn = dataSource.getConnection();
         PreparedStatement ps = conn.prepareStatement(sql)) {
        ps.setLong(1, lastId);
        ps.setLong(2, upperBound);
        ps.setInt(3, pageSize);

        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                long id = rs.getLong("customer_id");
                processCustomer(
                    id,
                    rs.getString("full_name"),
                    rs.getString("email")
                );
                lastId = id;
                rows++;
            }
        }
    }

    if (rows == 0) {
        break;
    }

    saveCheckpoint(lastId);
}
```

This code is an illustrative skeleton; production code needs idempotent error handling and should persist checkpoints only after batch output has been durably written. A fixed `upperBound` prevents the job from endlessly chasing newly inserted rows while running. If source data can be deleted or updated mid-job, define snapshot and cutoff semantics explicitly before starting.

Keyset pagination requires a deterministic sort order and an index on the pagination column. If the sort key is not unique, add a unique tie-breaker column such as `(created_at, customer_id)` to avoid skipping or duplicating rows across pages. Avoid large `OFFSET` values because the server still has to scan and discard prior rows before returning the next page.

## 9. Common Errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| `OutOfMemoryError` on large queries | ResultSet buffered entirely or application collects all rows into a collection | Use cursor/streaming or pagination; process row by row without accumulating all objects. |
| `setFetchSize(500)` does not reduce memory | `useCursorFetch` disabled, non-positive fetch size, or incompatible statement config | Check URL properties, server-side prepared statements, ResultSet type, and driver version. |
| Streaming ResultSet still active | Executed another statement on the same connection while streaming ResultSet was open | Finish reading or close the ResultSet before reusing the connection. |
| Cursor closed mid-stream | Statement/connection closed or transaction ended before reading finished | Keep resources open until iteration completes; do not commit early. |
| Connection pool exhausted | Streaming jobs hold connections too long or too many run concurrently | Separate pools, cap concurrency, use batch pagination, and set timeouts. |
| Low throughput with small fetch size | Excessive fetch calls and network round trips | Benchmark larger batches, balancing against heap and row size. |
| Server uses temp disk or heavy I/O | Cursor materializes results into an internal temporary table | Narrow columns/rows, optimize the query, consider pagination, and monitor server resources. |
| Duplicate or missing rows across batches | Non-unique pagination order or faulty checkpointing | Use keyset pagination with a unique key and save checkpoints after safe batch processing. |

## 10. Procedure for Testing a Large Query

1. Record the driver version and active JDBC URL properties.
2. Run the query with a buffered ResultSet for a timing and heap baseline.
3. Rerun with `useCursorFetch=true`, server-side prepared statements, and a positive fetch size.
4. If appropriate, compare against `Integer.MIN_VALUE` streaming.
5. Verify row counts, first/last values, ordering, and nulls to confirm no lost or duplicated rows.
6. Measure heap, GC, network round trips, total processing time, and server-side temp resources.
7. Test exception handling mid-stream, ensuring resources close cleanly and jobs can resume from checkpoints if required by design.

Never benchmark solely by `executeQuery()` duration. With cursors/streaming, most data transfer time occurs inside the `ResultSet.next()` loop. Measure total time from query submission through reading all rows and closing resources.

## 11. Implementation Checklist

- [ ] Query selects only needed columns and uses appropriate filters.
- [ ] Selected buffered, cursor fetch, legacy streaming, or keyset pagination per workload.
- [ ] If using cursor fetch, `useCursorFetch=true` and server-side prepared statements are enabled.
- [ ] Used appropriate `PreparedStatement` or `Statement`, forward-only/read-only ResultSet, and positive fetch size.
- [ ] If using legacy streaming, `Integer.MIN_VALUE` is configured intentionally.
- [ ] Application does not accumulate the entire result set in a collection.
- [ ] ResultSet, Statement, and Connection are closed properly.
- [ ] Connection pool has sufficient capacity for long jobs and concurrency is bounded.
- [ ] Transaction/snapshot lifetimes have been evaluated.
- [ ] Fetch size was benchmarked with realistic row sizes.
- [ ] Monitoring covers heap, GC, round trips, server temp tables, and I/O.
- [ ] Exception handling, checkpointing, and resume capability exist for long-running jobs.

## 12. Self-Check Exercises

1. Why does a fetch size of 500 not limit the total number of rows a query returns?
2. Why does Connector/J need server-side prepared statements to use `useCursorFetch`?
3. What is the main difference between `setFetchSize(500)` with cursor fetch and `setFetchSize(Integer.MIN_VALUE)`?
4. Why can a server-side cursor lower client heap while still increasing server-side I/O?
5. Why should you not call `executeQuery()` again on the same connection while a legacy streaming ResultSet is still open?
6. When is keyset pagination preferable to cursor fetch?
7. Why is a larger fetch size not always faster?
8. Inside an explicit transaction, what can happen if you commit before finishing reading the ResultSet?

**Answer hints:** (1) Fetch size controls how many rows are fetched per batch; `LIMIT` restricts total SQL rows. (2) MySQL cursor fetch relies on the server-side prepared statement protocol. (3) A positive value with `useCursorFetch` fetches batches via a server cursor; `Integer.MIN_VALUE` activates legacy streaming, reading sequentially from the connection. (4) MySQL materializes cursor results into an internal temporary table, which may use memory or disk. (5) The connection has an unconsumed streaming result; the driver cannot start another statement on that connection. (6) When you need checkpoints, releasing connections between batches, bounding transactions, or resuming after failures. (7) Large batches increase memory and per-batch processing time; row sizes and network behavior affect outcomes. (8) Committing the transaction closes the cursor; the ResultSet can no longer be read.

## References

- [MySQL Connector/J Developer Guide: JDBC API Implementation Notes](https://dev.mysql.com/doc/connector-j/en/connector-j-reference-implementation-notes.html)
- [MySQL Connector/J Developer Guide: Performance Extensions](https://dev.mysql.com/doc/connector-j/en/connector-j-connp-props-performance-extensions.html)
- [MySQL Connector/J Developer Guide: Configuration Properties](https://dev.mysql.com/doc/connector-j/en/connector-j-reference-configuration-properties.html)
- [MySQL 8.4 Reference Manual: Restrictions on Server-Side Cursors](https://dev.mysql.com/doc/refman/8.4/en/cursor-restrictions.html)
- [MySQL 8.4 Reference Manual: Prepared Statements](https://dev.mysql.com/doc/refman/8.4/en/sql-prepared-statements.html)
