# Client/Server Prepared Statements and useServerPrepStmts

This lesson belongs to the **DATABASE_MYSQL** module. When a Java application accesses MySQL through MySQL Connector/J, JDBC PreparedStatement helps separate SQL statements from input values, reuse statements, and bind parameters with proper data types. However, calling Connection.prepareStatement() in the application does not automatically mean MySQL Server holds a prepared statement. Connector/J can handle parameters on the client side or use server-side prepared statements, depending on configuration and statement support.

The useServerPrepStmts property controls this choice. Understanding both modes helps you design safe queries, evaluate performance, manage resources per connection pool, and diagnose differences in production.

## 1. What Is a JDBC PreparedStatement?

PreparedStatement is a JDBC API for executing an SQL statement containing ? parameter placeholders. The application creates the statement once, binds values to each parameter position, and executes it:

~~~java
String sql = "SELECT order_id, total_amount "
           + "FROM orders "
           + "WHERE customer_id = ? AND created_at >= ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId);
    ps.setTimestamp(2, Timestamp.valueOf(startTime));

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long orderId = rs.getLong("order_id");
            BigDecimal total = rs.getBigDecimal("total_amount");
            // Process result
        }
    }
}
~~~

Key points to remember:

- Parameter positions start at **1**, not 0.
- Each ? is a separate parameter. If the same value appears twice, it must be bound at both positions.
- Use setters matching the data type, such as setLong, setString, setBigDecimal, setDate, setTimestamp, or setBytes.
- Standard JDBC PreparedStatement does not provide named parameter syntax. Parameters are bound by positional index.
- Close PreparedStatement and ResultSet after use; try-with-resources conveniently releases resources even when exceptions occur.

A prepared statement can be executed multiple times with different values:

~~~java
String sql = "SELECT order_id FROM orders WHERE customer_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (long customerId : customerIds) {
        ps.setLong(1, customerId);

        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                processOrder(rs.getLong("order_id"));
            }
        }
    }
}
~~~

Reusing the same statement object avoids creating a new JDBC object on every iteration. The degree of reuse on MySQL Server also depends on the configured prepare mode and cache.

## 2. Two Ways Connector/J Handles Prepared Statements

Connector/J can execute PreparedStatements in two ways.

### 2.1. Client-Side Prepared Statements (Client Emulation)

In client-side mode, Connector/J keeps the SQL template and parameter values inside the driver. At execution time, the driver converts values into proper SQL literals, escapes and formats them according to connection metadata, and sends the complete SQL statement to MySQL Server over the text protocol.

For example, the application creates the template:

~~~sql
SELECT order_id FROM orders WHERE customer_id = ?
~~~

When customer_id is 501, the driver sends a constructed SQL string with that value. MySQL Server receives the text SQL, parses it, and executes it like an ordinary statement.

Characteristics:

- No server-side prepared statement handle is needed for each statement.
- Can reduce server-side prepared statement management overhead.
- The substituted SQL must still be parsed by the server on every execution.
- The driver is responsible for type conversion and escaping matching the connection, charset, and SQL mode.

This is still using JDBC PreparedStatement; the API name does not indicate where the statement is prepared.

### 2.2. Server-Side Prepared Statements

In server-side mode, Connector/J uses MySQL's binary prepared statement protocol. The driver sends the SQL template to the server to prepare, then sends parameter values separately on subsequent executions.

General flow:

1. Client sends the SQL template using the prepare protocol command (COM_STMT_PREPARE).
2. Server parses the statement, creates a prepared statement handle, and returns matching parameter/result metadata.
3. Client sends parameter values and an execution request (COM_STMT_EXECUTE).
4. Server executes the prepared statement with the new set of values.
5. When no longer needed, the client closes the handle (COM_STMT_CLOSE) or the driver manages its lifecycle via cache.

The SQL example remains:

~~~sql
SELECT order_id, total_amount
FROM orders
WHERE customer_id = ? AND created_at >= ?
~~~

The customer_id and created_at values are transmitted separately in the execute protocol rather than concatenated into a text SQL string.

Characteristics:

- The server parses the statement during prepare and can reuse the prepared statement across subsequent executions.
- Parameters are transmitted via the binary protocol with type information.
- Each prepared statement belongs to the MySQL session/connection that created it.
- The server must retain resources for open statements; excessive counts can hit the global limit.
- Certain metadata changes can force the server to reprepare the statement.

Server-side prepare does not guarantee faster execution for every query. It is most useful when the same SQL template is executed repeatedly; for statements run only once, the overhead of prepare and handle management may yield no meaningful benefit.

## 3. Enabling useServerPrepStmts

In MySQL Connector/J, useServerPrepStmts defaults to false. To request server-side prepared statements, enable the property in the JDBC URL or DataSource configuration:

~~~text
jdbc:mysql://db.example.net:3306/shop?useServerPrepStmts=true
~~~

Example configuration using MysqlDataSource:

~~~java
import com.mysql.cj.jdbc.MysqlDataSource;
import javax.sql.DataSource;

MysqlDataSource mysql = new MysqlDataSource();
mysql.setURL("jdbc:mysql://db.example.net:3306/shop");
mysql.setUser("shop_app");
mysql.setPassword(readSecret());
mysql.setUseServerPrepStmts(true);

DataSource dataSource = mysql;
~~~

Setter names and packages must match your Connector/J version. When using a connection pool such as HikariCP, configure the property in the JDBC URL or driver properties passed by the pool to Connector/J. Verify the actual configuration on each physical connection.

Example URL combining server-side prepare and caching:

~~~text
jdbc:mysql://db.example.net:3306/shop?useServerPrepStmts=true&cachePrepStmts=true&prepStmtCacheSize=100&prepStmtCacheSqlLimit=2048
~~~

These cache numbers are illustrative starting values for testing, not fixed recommendations for all workloads. Measure SQL template counts, statement lengths, connection counts, and server prepared statement limits before tuning.

### 3.1. useServerPrepStmts Is Not an Absolute Guarantee for Every Statement

This property asks Connector/J to use server-side prepared statements when both the server and the statement support them. Certain statement types or situations unsupported by the server may still be handled by the driver via client-side emulation. Therefore, do not assume every PreparedStatement in the application creates a server-side handle merely because the URL includes useServerPrepStmts=true.

Test the exact SQL statements, MySQL version, and Connector/J version in use; inspect counters or Performance Schema if you need to prove actual behavior.

## 4. Comparing Client-Side and Server-Side

| Criterion | Client-side (emulated) | Server-side (useServerPrepStmts=true) |
|---|---|---|
| Where parameters are processed | Connector/J formats/escapes and builds text SQL | Driver sends parameters separately via binary protocol |
| SQL parsing | Server parses substituted SQL on every execution | Server prepares SQL template and can reuse the statement |
| Server resources | No prepared statement handles needed for emulation | Keeps handles in session while statements remain open/cached |
| Parameter types | Driver converts values into suitable literals | Parameters are sent with protocol-level type information |
| One-off statements | Avoids extra server-side prepare handle overhead | Adds prepare step and handle management |
| Repeated statements | Server still parses text SQL after substitution | Can reduce repeated SQL parsing and template transmission overhead |
| Limitations | Depends on driver escaping/type conversion | Depends on prepared statement support and server limits |

Both modes are usable through JDBC PreparedStatement. Using parameterized APIs properly is what matters; enabling server-side prepare is a choice about protocol and statement lifecycle, not the sole condition for writing safe SQL.

## 5. Preventing SQL Injection

Never concatenate user input directly into SQL:

~~~java
// Unsafe: input can alter the SQL statement structure
String sql = "SELECT * FROM users WHERE email = '" + email + "'";
Statement st = connection.createStatement();
ResultSet rs = st.executeQuery(sql);
~~~

Use parameters:

~~~java
String sql = "SELECT user_id, email FROM users WHERE email = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, email);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Process user appropriately
        }
    }
}
~~~

In server-side mode, values are transmitted separately from the SQL template so the server never interprets parameter contents as SQL syntax. In client-side mode, Connector/J emulates this by escaping and formatting literals. Regardless of mode, applications should always use PreparedStatement and never concatenate untrusted data into SQL.

### 5.1. Parameters Represent Values Only

Question marks cannot replace table names, column names, keywords, operators, or sort directions. The following example does not work as intended:

~~~java
String sql = "SELECT * FROM ? WHERE customer_id = ?";
PreparedStatement ps = connection.prepareStatement(sql);
ps.setString(1, "orders");
ps.setLong(2, customerId);
~~~

MySQL must know the table name when parsing statement structure; a JDBC parameter cannot become an identifier. If choosing a sort column dynamically is required, use a fixed whitelist:

~~~java
Set<String> allowedSortColumns = Set.of("created_at", "total_amount");
String sortColumn = allowedSortColumns.contains(requestedSort)
        ? requestedSort
        : "created_at";

String sql = "SELECT order_id, total_amount FROM orders "
           + "WHERE customer_id = ? ORDER BY " + sortColumn + " DESC";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId);
    // Execute query
}
~~~

Only identifiers validated against a whitelist should enter SQL. Never use user input directly as an identifier.

### 5.2. IN (?) Does Not Automatically Expand Lists

One ? corresponds to one value. Binding the string "1,2,3" to a single placeholder does not turn it into three elements inside an IN clause.

To query a variable-length list, generate the matching number of placeholders and bind each element:

~~~java
List<Long> ids = List.of(101L, 102L, 103L);
String placeholders = String.join(",", Collections.nCopies(ids.size(), "?"));
String sql = "SELECT order_id FROM orders WHERE order_id IN (" + placeholders + ")";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (int i = 0; i < ids.size(); i++) {
        ps.setLong(i + 1, ids.get(i));
    }
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            processOrder(rs.getLong(1));
        }
    }
}
~~~

Here, the SQL string is built solely from the count of ? placeholders; all values remain bound. Handle empty lists separately and cap list size to avoid oversized SQL statements.

## 6. Binding Accurate Data Types

Choosing the right setter avoids unnecessary conversions and preserves data semantics:

| Common MySQL Type | Suggested JDBC Setter |
|---|---|
| TINYINT, INT within Java int range | setInt |
| BIGINT | setLong |
| DECIMAL, NUMERIC | setBigDecimal |
| VARCHAR, TEXT | setString |
| DATE | setDate or java.time APIs supported by Connector/J |
| DATETIME, TIMESTAMP | setTimestamp or appropriate java.time types |
| BINARY, VARBINARY, BLOB | setBytes, setBinaryStream |

Example with DECIMAL and NULL values:

~~~java
String sql = "INSERT INTO invoices (invoice_no, amount, due_date) "
           + "VALUES (?, ?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, invoiceNumber);

    if (amount == null) {
        ps.setNull(2, Types.DECIMAL);
    } else {
        ps.setBigDecimal(2, amount);
    }

    if (dueDate == null) {
        ps.setNull(3, Types.DATE);
    } else {
        ps.setDate(3, java.sql.Date.valueOf(dueDate));
    }

    ps.executeUpdate();
}
~~~

Never pass the string "NULL" to represent SQL NULL; use setNull with the appropriate JDBC type. For dates and times, align the timezones of the JVM, JDBC connection, and MySQL, especially when using TIMESTAMP because it converts based on the session timezone.

## 7. Prepared Statement Reuse and Caching

Server-side prepare is most beneficial when an SQL template executes many times on the same connection. Distinguish two layers of reuse:

- Reusing the same PreparedStatement object in code: keeping the statement open and calling setX()/execute...() multiple times.
- Connector/J caching: the driver retains prepared statements so they can be reused when the application closes a statement and later re-prepares the same SQL on the same physical connection.

The cachePrepStmts property controls driver-side caching; it is disabled by default. When testing caching, you can configure:

~~~text
useServerPrepStmts=true
cachePrepStmts=true
prepStmtCacheSize=100
prepStmtCacheSqlLimit=2048
~~~

Meaning:

- cachePrepStmts: enables prepared statement caching inside Connector/J.
- prepStmtCacheSize: maximum number of cached statements per connection.
- prepStmtCacheSqlLimit: maximum SQL length eligible for caching.

The cache is tied to each physical connection. If a pool has 40 connections and each caches up to 100 statements, total handles can grow substantially when workloads use many SQL templates. Do not set a large cache size without accounting for connection count, SQL template count, and max_prepared_stmt_count on MySQL Server.

### 7.1. Managing Statement Lifecycle

Recommended pattern:

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "UPDATE inventory SET quantity = ? WHERE product_id = ?")) {
    ps.setInt(1, newQuantity);
    ps.setLong(2, productId);
    ps.executeUpdate();
}
~~~

When the statement closes, the driver releases the handle or places it into the cache per configuration. Do not hold thousands of statements open in a single request or retain statements beyond the connection's lifecycle. When a connection pool returns a connection to the pool, open statements must be closed to prevent resource leaks and leaked session state.

Server-side prepared statements belong to a specific connection. You cannot prepare on connection A and execute that handle on connection B. If the application borrows a different connection from the pool on the next call, the statement must be prepared or retrieved from that connection's cache.

### 7.2. MySQL Server Limits

MySQL limits total open prepared statements via the max_prepared_stmt_count variable. You can inspect it:

~~~sql
SHOW VARIABLES LIKE 'max_prepared_stmt_count';
SHOW GLOBAL STATUS LIKE 'Prepared_stmt_count';
SHOW GLOBAL STATUS LIKE 'Com_stmt_prepare';
SHOW GLOBAL STATUS LIKE 'Com_stmt_execute';
SHOW GLOBAL STATUS LIKE 'Com_stmt_close';
~~~

If statement counts grow continuously, check for connection leaks, unclosed statements, oversized caches, or pools with too many physical connections. Never merely raise max_prepared_stmt_count to mask lifecycle management bugs.

## 8. Batching and Prepared Statements

For multiple operations sharing the same SQL template, you can use addBatch() and executeBatch():

~~~java
String sql = "INSERT INTO order_items (order_id, product_id, quantity) "
           + "VALUES (?, ?, ?)";

boolean originalAutoCommit = connection.getAutoCommit();
connection.setAutoCommit(false);
try {
    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        int count = 0;
        for (OrderItem item : items) {
            ps.setLong(1, item.orderId());
            ps.setLong(2, item.productId());
            ps.setInt(3, item.quantity());
            ps.addBatch();

            if (++count % 500 == 0) {
                ps.executeBatch();
            }
        }

        ps.executeBatch();
    }
    connection.commit();
} catch (SQLException e) {
    connection.rollback();
    throw e;
} finally {
    connection.setAutoCommit(originalAutoCommit);
}
~~~

This snippet illustrates batching multiple operations and ending the transaction on success or failure. In production code, handle exceptions thrown during rollback or autoCommit restoration separately so they do not suppress the original error. A batch size of 500 is only an example; tune based on payload, transaction duration, packet size, lock contention, and replication lag.

useServerPrepStmts and batching are independent choices. Enabling server-side prepare does not automatically mean the driver merges every batch into a single SQL statement. Connector/J has separate batching properties, and behavior can depend on statement type and driver version. Benchmark with realistic settings before enabling extra options.

## 9. Fetching Large Data and Server-Side Cursors

For very large result sets, buffering the entire ResultSet in client memory can cause heap pressure. Connector/J supports cursor fetching under specific conditions; useCursorFetch=true requires server-side prepared statements and a non-zero fetch size to use the server-side cursor mechanism.

URL example:

~~~text
jdbc:mysql://db.example.net:3306/shop?useServerPrepStmts=true&useCursorFetch=true&defaultFetchSize=500
~~~

Or set fetch size on the statement:

~~~java
String sql = "SELECT order_id, created_at FROM orders ORDER BY order_id";

try (PreparedStatement ps = connection.prepareStatement(
        sql, ResultSet.TYPE_FORWARD_ONLY, ResultSet.CONCUR_READ_ONLY)) {
    ps.setFetchSize(500);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            processOrder(rs.getLong("order_id"));
        }
    }
}
~~~

Fetch size hints/controls how the driver retrieves results; it does not limit how many rows the SQL query returns. Server-side cursors can hold server resources and connections throughout result traversal. Close ResultSets early, avoid holding cursors across slow external work, and measure both client heap and server resources.

## 10. Verifying Server-Side Prepare Is Actually Active

Do not look solely at the JDBC URL to draw conclusions. You can check several indicators on the server side.

### 10.1. Status Counters

The Com_stmt_* counters report prepared statement activity at the server level:

~~~sql
SHOW GLOBAL STATUS LIKE 'Com_stmt%';
SHOW GLOBAL STATUS LIKE 'Prepared_stmt_count';
~~~

Run a test workload with repeated prepareStatement() and executeQuery() calls on a connection configured with useServerPrepStmts=true, then observe changes in Com_stmt_prepare, Com_stmt_execute, and Com_stmt_close. Global counters can be affected by other applications; measure in an isolated test environment or compare deltas before and after an isolated workload.

### 10.2. Performance Schema

If Performance Schema is enabled and you have sufficient privileges, inspect currently open server-side prepared statements:

~~~sql
SELECT STATEMENT_ID, STATEMENT_NAME, SQL_TEXT,
       OWNER_THREAD_ID, COUNT_EXECUTE, COUNT_REPREPARE
FROM performance_schema.prepared_statements_instances;
~~~

This table shows statements still held on the server at query time. If the application closes statements immediately and the driver does not cache them, handles may disappear before you query. Seeing zero rows in a single check does not prove the driver never used server-side prepare.

You can also inspect reprepare counters to catch metadata changes or situations where the server had to reprepare a statement. Cross-check exact column names and observability details against your running MySQL version.

## 11. Performance and Practical Considerations

### 11.1. When Server-Side Prepare Can Help

- An SQL template executes repeatedly with many parameter sets.
- The application uses long-lived connections and reuses statements effectively.
- Reducing text SQL re-parsing overhead is a significant portion of the workload.
- Binary parameter transmission is desirable, especially for numeric, temporal, or suitable payloads.
- Using cursor fetch for large result sets while accepting server-side cursor lifecycles.

### 11.2. When Benefits May Be Low or Costly

- SQL statements execute only once; prepare/close overhead can outweigh savings.
- The application generates many distinct SQL strings due to literal concatenation or dynamic structures, preventing good cache hit rates.
- The pool holds many physical connections, giving each connection its own cache and increasing total server handles.
- Statements stay open for a long time, consuming server or connection resources.
- Metadata/schema changes force statements to reprepare.
- Certain statements do not support server-side prepare and the driver falls back to emulation.

Server-side prepare does not create indexes, fix poor execution plans, or guarantee MySQL always picks the same optimal plan. You must still tune SQL, indexes, statistics, and transactions independently of your prepare mode choice.

### 11.3. Avoid Generating Unstable SQL Templates

If an application embeds values into SQL strings instead of placeholders, every value produces a different SQL text. That undermines statement reuse and caching. Keep SQL structures stable, bind values via setters, and construct identifiers only from whitelists when genuinely needed.

## 12. Common Errors and Diagnostics

| Symptom | Possible cause | Check/Resolution |
|---|---|---|
| No server-side statements observed | Property not applied to physical connection, unsupported statement, or handles already closed | Check JDBC URL/DataSource, counters, and Performance Schema during execution |
| max_prepared_stmt_count exceeded | Too many handles, unclosed statements, or oversized cache/pool | Measure Prepared_stmt_count, check statement lifecycles, and calculate total cache across connections |
| Queries slower after enabling | Low-reuse workload, prepare overhead, cache misses, or unsuitable parameter types | Benchmark by SQL group, comparing p95/p99 and server resources |
| Parameter type conversion errors | Wrong setter used, NULL lacking explicit JDBC type, or timezone mismatch | Use type-matched setters/setNull and verify session timezone |
| Errors using placeholders for table/column names | Parameter markers represent values only | Use validated identifier whitelists and bind data values |
| IN (?) matches only a single value | One placeholder represents a single scalar value | Generate matching placeholders or use a staging strategy for large lists |
| Statement reprepares | Table metadata changed or server detected reprepare need | Inspect COUNT_REPREPARE, DDL timing, and statement lifecycle |
| Heap grows when reading many rows | Driver/client buffering large results | Evaluate fetch size, cursor fetch, ResultSet mode, and cursor hold duration |

When logging for investigation, prefer recording SQL templates, durations, row counts, and error categories. Avoid logging passwords, tokens, personal data, or sensitive bound parameter values in application logs.

## 13. Benchmark Procedure Before Enabling in Production

Do not enable useServerPrepStmts system-wide based on a single sample query. Compare in a production-like environment:

1. Choose a representative query mix: high-frequency repeated queries, one-off queries, DML, batches, and multi-row queries.
2. Keep SQL templates, parameters, indexes, data, and concurrency identical between test runs.
3. Run pass A in client-side mode and pass B with useServerPrepStmts=true.
4. If evaluating caching, run an additional pass with cachePrepStmts=true and the same pool size.
5. Measure throughput, p50/p95/p99 latency, client/server CPU, network bytes, prepared statement counts, parse/execute counters, heap, and replication lag.
6. Run long enough to warm caches and stabilize load; avoid short single-shot measurements.
7. Test reconnects, connection eviction, failovers, and statement open/close cycles to catch lifecycle bugs.
8. Roll out to a small percentage of traffic, monitor metrics, and keep a way to toggle the property off if results regress.

A change might reduce CPU while increasing handle count or memory usage. Decide based on overall latency, throughput, resource footprint, and system stability.

## 14. Deployment Checklist

- [ ] Verified MySQL Server and Connector/J versions.
- [ ] Identified which queries actually repeat and suit prepared statements.
- [ ] Kept SQL templates stable and bound all values via setters.
- [ ] Avoided misusing placeholders for identifiers or IN lists.
- [ ] Configured useServerPrepStmts on the correct DataSource/physical connection.
- [ ] Checked cachePrepStmts, cache size, and SQL length limit when caching is enabled.
- [ ] Calculated maximum handles across physical connections against max_prepared_stmt_count.
- [ ] Closed statements/result sets per lifecycle and handled transaction errors.
- [ ] Benchmarked client-side vs. server-side on a representative workload.
- [ ] Verified behavior using Com_stmt_* counters or Performance Schema.
- [ ] Evaluated cursor fetch if reading large result sets.
- [ ] Ensured logs do not expose sensitive parameters.
- [ ] Prepared a rollout, monitoring, and rollback/disable plan.

## 15. Self-Check

1. Does JDBC PreparedStatement automatically mean MySQL Server uses server-side prepared statements? Explain.
2. What is the protocol difference between client-side emulation and server-side prepare?
3. Which Connector/J behavior does useServerPrepStmts=true control?
4. Why can server-side prepare help repeated SQL executions yet not always be faster?
5. Why can't ? substitute for a table name or column name?
6. Why can't IN (?) accept a string containing multiple IDs to create a list of elements?
7. How does cachePrepStmts differ from reusing the same PreparedStatement object?
8. Why must you factor in connection pool size when tuning cache size and max_prepared_stmt_count?
9. How does useCursorFetch relate to server-side prepared statements and fetch size?
10. Propose a benchmark to decide whether to enable server-side prepare for a Java service handling high-volume order queries.

When tuning MySQL Connector/J, separate the JDBC API from the underlying protocol mechanism. PreparedStatement is how the application expresses parameterized queries; useServerPrepStmts decides whether the driver asks MySQL to prepare statements on the server. Combine proper type binding, lifecycle management, cache sizing, and realistic workload measurement to choose the right configuration.
