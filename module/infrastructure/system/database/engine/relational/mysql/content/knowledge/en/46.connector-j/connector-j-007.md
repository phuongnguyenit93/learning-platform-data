# cachePrepStmts, Prepared Statement Limits, and Resource Lifecycle

## Objectives

MySQL Connector/J is the JDBC driver for Java. When an application creates many `PreparedStatement` instances with the same SQL statement, repeated parsing and preparation can add overhead. Connector/J has a prepared statement cache mechanism to reuse preparation state, and it can reuse server-side prepared statements when configured appropriately. However, the cache is maintained per physical connection, while server-side prepared statements consume resources across the entire MySQL instance. Configuring an oversized cache alongside a large connection pool can push the server up against `max_prepared_stmt_count`.

This lesson belongs to the **DATABASE_MYSQL** module, which covers table design, data types, keys, SQL queries, indexes, transactions, concurrency control, query optimization, and relational database operations. This lesson focuses on configuring `cachePrepStmts`, understanding prepared statement limits, managing JDBC lifecycles, and sizing the cache based on actual connection counts.

After this lesson, you will be able to:

- Distinguish client-side emulated prepared statements from MySQL server-side prepared statements.
- Configure `cachePrepStmts`, `prepStmtCacheSize`, `prepStmtCacheSqlLimit`, and `useServerPrepStmts`.
- Estimate the impact of per-connection caching on server-wide limits.
- Properly close `Connection`, `PreparedStatement`, and `ResultSet` in Java.
- Monitor prepared statement counts, detect leaks, and choose an appropriate cache size.

## 1. PreparedStatement in JDBC

`PreparedStatement` represents a parameterized SQL statement. The application constructs SQL with `?` placeholders, binds values via setters, and executes it. This separates SQL structure from input data, promotes reuse, and avoids concatenating user values directly into SQL strings.

```java
String sql = "SELECT order_id, status FROM orders WHERE customer_id = ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, customerId);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long orderId = resultSet.getLong("order_id");
            String status = resultSet.getString("status");
            // Process results while ResultSet remains open.
        }
    }
}
```

Placeholders are only for values—never for substituting table names, column names, keywords, or sort directions. If dynamic column or sort direction selection is needed, use an application-controlled allowlist and interpolate only the validated identifier into SQL. Never put request strings directly into the structural part of a statement.

A prepared statement is not a query result cache. It does not store query results to return stale data on subsequent calls; MySQL still executes the statement and reads data according to the current transaction, isolation level, and database state.

## 2. Client-Side and Server-Side Prepared Statements

Connector/J can handle prepared statements in two ways:

- **Client-side emulation:** the driver retains the statement structure and sends parameter-substituted SQL to the server. The server does not create a dedicated server prepared statement for each statement via the prepare/execute protocol.
- **Server-side prepared statement:** the driver sends a prepare request to MySQL. The server creates a statement bound to the connection session, then receives parameter values during execute calls.

The `useServerPrepStmts=true` property instructs Connector/J to use server-side prepared statements when the statement and version support them. Certain statements or features may not support server-side prepare, and the driver may handle them using a compatibility mechanism depending on configuration and version.

Server-side prepare can reduce repeated SQL transmission and parsing in some workloads, and it changes how data types and metadata are transmitted. It also allocates statement objects on the server, so the count is bounded by `max_prepared_stmt_count`. Do not enable it just because the name sounds faster; benchmark with your actual SQL and driver.

## 3. `cachePrepStmts` and Related Properties

Connector/J provides several core properties:

| Property | Role |
|---|---|
| `cachePrepStmts` | Enables/disables prepared statement caching in Connector/J |
| `prepStmtCacheSize` | Maximum number of cache entries per physical connection |
| `prepStmtCacheSqlLimit` | Maximum SQL length eligible for caching |
| `useServerPrepStmts` | Requests server-side prepared statements when supported |

Example connection URL:

```text
jdbc:mysql://db.example.net:3306/app?cachePrepStmts=true&prepStmtCacheSize=250&prepStmtCacheSqlLimit=2048&useServerPrepStmts=true
```

This configuration is a starting point for experimentation, not an optimal value for every application. Property names and defaults can vary across Connector/J versions; check the documentation for the exact driver version deployed.

`cachePrepStmts=true` allows the driver to retain eligible prepared statements for reuse. `prepStmtCacheSize` sets the entry limit per physical connection, not a global application-wide cache. `prepStmtCacheSqlLimit` excludes overly long SQL strings from caching; those statements still run, but are not retained as cache entries.

When server-side prepare is enabled, the cache can retain server prepared statements even after the application calls `close()` on the JDBC object. The driver can then reuse that statement on a later call over the same physical connection. When an entry is evicted from the cache or the physical connection closes, the corresponding server-side statement is released according to driver mechanics.

## 4. Caching Is Scoped to Physical Connections

Server-side prepared statements belong to the MySQL session that created them. A statement on connection A cannot be used directly from connection B. Consequently, Connector/J's cache is organized per physical connection, usually connections managed by a connection pool.

This has an important consequence: the potential total number of prepared statements scales with active physical connections and cache size per connection. For instance, 80 physical connections with a cache limit of 200 entries per connection yields a theoretical capacity of up to 16,000 entries if all entries are populated and are server-side statements. This is only a capacity estimate; caches do not fill immediately when connections open, and actual counts depend on workload, eviction, active connections, and the driver.

If multiple application instances exist, include physical connections from every instance in the calculation. Connection pools can keep idle connections alive for long periods, meaning caches on those connections persist and server-side prepared statements may continue consuming quota.

Do not divide `prepStmtCacheSize` across the entire application as if it were a global setting. Calculate per pool, number of application replicas, maximum connections, and server limits.

## 5. The `max_prepared_stmt_count` Limit on MySQL

MySQL sets a server-wide limit on concurrent prepared statements via the `max_prepared_stmt_count` variable. This limit includes server-side prepared statements across all sessions and applications. A common default is `16382`, though you must check the instance's actual value because configuration may vary by environment or version.

```sql
SHOW GLOBAL VARIABLES LIKE 'max_prepared_stmt_count';
SHOW GLOBAL STATUS LIKE 'Prepared_stmt_count';
```

`Prepared_stmt_count` shows how many prepared statements the server currently tracks. If the limit is reached, new prepare requests can fail with MySQL error `ER_MAX_PREPARED_STMT_COUNT_REACHED` (typically error 1461). At that point, applications can fail even though individual connections remain healthy.

You can inspect statements currently tracked by Performance Schema:

```sql
SELECT OWNER_THREAD_ID, STATEMENT_ID, SQL_TEXT
FROM performance_schema.prepared_statements_instances;
```

Querying `performance_schema.prepared_statements_instances` requires Performance Schema enabled and appropriate read privileges. SQL text may contain sensitive details; restrict access and avoid writing queries with private data into unprotected logs.

If statement counts grow steadily over time and do not drop when workload subsides, check for statement leaks, unclosed connections, pools holding too many connections, or oversized per-connection caches. Raising `max_prepared_stmt_count` should only follow memory and load estimation, never serve as a band-aid for a lifecycle leak.

## 6. How to Calculate the Cache Budget

Initial estimate for cached server-side statements:

```text
Potential cached statements
  ~= total physical connections across all app pools
     x prepStmtCacheSize per connection
```

For example, a service with 3 application instances, each allowing up to 40 physical connections, and a cache size of 100:

```text
3 x 40 x 100 = 12,000 potential cache entries
```

This number does not yet include open prepared statements not yet returned to the cache, statements from batches/jobs/monitoring, other services sharing MySQL, and necessary headroom. Nor does it mean the server immediately allocates 12,000 statements; entries are created only as workloads execute the corresponding SQL statements.

Leave ample headroom below `max_prepared_stmt_count` for traffic spikes, rolling deployments, background jobs, and admin sessions. In particular, during a deploy, connections from both old and new application versions can coexist simultaneously.

## 7. Stable SQL Makes Caching Effective

Caching works best when the exact same SQL statement is reused. Pass parameter values via setters instead of concatenating them into SQL:

```java
String sql = "SELECT order_id FROM orders WHERE customer_id = ? AND status = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, customerId);
    statement.setString(2, status);
    try (ResultSet resultSet = statement.executeQuery()) {
        // Read results.
    }
}
```

Concatenating values directly into SQL creates a distinct SQL string per value and defeats caching. Inconsistent whitespace, comments, or statement construction patterns can likewise generate separate cache keys.

Statements exceeding `prepStmtCacheSqlLimit` are excluded from caching per that threshold. Dynamic SQL such as `IN (?, ?, ?)` with varying placeholder counts also creates distinct statement forms. If hundreds of variants rarely repeat, increasing cache size may only increase memory and quota usage without raising the hit rate.

Do not force unrelated SQL into one giant query just to boost reuse. Keep queries readable, parameterize values, and standardize only SQL templates that truly repeat.

## 8. Lifecycle of `Connection`, `PreparedStatement`, and `ResultSet`

JDBC requires applications to close resources after use. The simplest and most reliable pattern in Java is `try-with-resources`:

```java
String sql = "UPDATE inventory SET quantity = quantity - ? WHERE sku = ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setInt(1, amount);
    statement.setString(2, sku);

    int updatedRows = statement.executeUpdate();
    if (updatedRows != 1) {
        throw new IllegalStateException("Unexpected inventory row count");
    }
}
```

For queries returning data, close `ResultSet` within the `PreparedStatement` scope:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
         "SELECT sku, quantity FROM inventory WHERE sku = ?")) {
    statement.setString(1, sku);

    try (ResultSet resultSet = statement.executeQuery()) {
        if (resultSet.next()) {
            int quantity = resultSet.getInt("quantity");
            // Transfer needed data to an application object.
        }
    }
}
```

Closing `ResultSet` releases cursors and related resources. Closing `PreparedStatement` lets Connector/J return the statement to the cache if eligible, or free it. Closing `Connection` returns the logical connection to the pool or closes the physical session if no pool is used. Never skip `close()` just because caching is enabled.

Do not hold `ResultSet` or `PreparedStatement` in global fields to share across requests. Statements are bound to a connection and are not designed for arbitrary concurrent use across threads. Each unit of work should borrow a connection, create statements, consume results, close statements, and return the connection.

With a connection pool, calling `Connection.close()` usually returns the logical connection to the pool rather than closing the socket immediately. The pool can keep the physical session and its statement cache alive for reuse. When the pool evicts the physical connection, the driver releases all session resources on the server.

## 9. Transactions and the Statement Cache

The prepared statement cache does not alter transaction boundaries. Statements still execute inside the current connection's transaction, obeying `autocommit`, isolation level, and InnoDB locks.

Transaction example:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        try (PreparedStatement debit = connection.prepareStatement(
                 "UPDATE accounts SET balance = balance - ? WHERE account_id = ?");
             PreparedStatement credit = connection.prepareStatement(
                 "UPDATE accounts SET balance = balance + ? WHERE account_id = ?")) {
            debit.setBigDecimal(1, amount);
            debit.setLong(2, fromAccount);
            debit.executeUpdate();

            credit.setBigDecimal(1, amount);
            credit.setLong(2, toAccount);
            credit.executeUpdate();
        }
        connection.commit();
    } catch (SQLException exception) {
        try {
            connection.rollback();
        } catch (SQLException rollbackException) {
            exception.addSuppressed(rollbackException);
        }
        throw exception;
    }
}
```

This structure is illustrative; production code must verify affected row counts, validate balances, and handle uncertain commit errors. Never blindly call `setAutoCommit(true)` inside `finally`: JDBC can implicitly commit an open transaction when re-enabling auto-commit. Pools usually reset connection state on return; if rollback or session reset fails, mark and evict the physical connection using your pool's mechanism.

## 10. Coordinating Pool and Cache Configuration

The connection pool dictates how many physical sessions open to MySQL. The statement cache multiplies resource consumption per session. Therefore, pool and cache settings must be tuned together.

| Increasing value | Potential benefit | Cost/risk |
|---|---|---|
| `maximumPoolSize` | More requests can borrow connections concurrently | Increases sessions, memory, threads, and total cache entries |
| `prepStmtCacheSize` | Retains more SQL templates per connection | Increases potential server-side statements and cache memory |
| `prepStmtCacheSqlLimit` | Caches longer SQL statements | Increases memory storing SQL text and total cached entries |
| `useServerPrepStmts` | Uses server-side prepare/execute for supported statements | Allocates server statements, subject to global limits and potential driver behavior differences |

Do not size maximum pool size solely from application thread counts. Determine actual concurrent queries, connection hold times, MySQL capacity, and total connection limits. Adding connections when the database is already CPU- or I/O-saturated may fail to raise throughput and simply worsen contention.

## 11. Monitoring the Cache and Detecting Leaks

Measure before and after enabling the cache using a representative workload. Monitor:

- `Prepared_stmt_count` relative to `max_prepared_stmt_count`.
- Open, active, idle, and pending connections in each pool.
- Prepare errors, error 1461 occurrences, and connection close errors.
- Prepare/execute latency, throughput, and MySQL CPU.
- Cache hit/miss or cache metrics exposed by your Connector/J version, if available.
- Open statements in `performance_schema.prepared_statements_instances`.

Basic monitoring queries:

```sql
SHOW GLOBAL STATUS LIKE 'Prepared_stmt_count';
SHOW GLOBAL VARIABLES LIKE 'max_prepared_stmt_count';

SELECT COUNT(*) AS server_prepared_statements
FROM performance_schema.prepared_statements_instances;
```

To investigate a specific session, join `OWNER_THREAD_ID` from `prepared_statements_instances` with threads in Performance Schema. Access privileges and columns may vary by MySQL version; grant only the necessary monitoring privileges.

Common leak indicators:

- `Prepared_stmt_count` grows steadily under stable load and does not return to baseline after requests finish.
- The connection pool continually opens new connections because old ones error out or are never returned.
- Code creates statements inside loops without closing them.
- Query results are held open for a long time, preventing statements and connections from being released.
- Many nearly identical SQL templates differing only in literals, comments, or whitespace fragment the cache.

Cache eviction is part of management, not a replacement for closing statements. Use your pool's connection leak detection, log connection borrow durations, and audit code paths for `try-with-resources`.

## 12. Practical Tuning Workflow

1. Record Connector/J, MySQL, pool type, application instance count, and max connection settings.
2. Check `max_prepared_stmt_count` and `Prepared_stmt_count` during peak hours.
3. Identify repeating SQL templates, SQL lengths, and execution frequencies; exclude rarely reused templates from caching scope if needed.
4. Start with a moderate per-connection cache size; calculate total potential capacity across all pools.
5. Benchmark `cachePrepStmts` and `useServerPrepStmts` separately on the same workload, avoiding changing multiple variables at once.
6. Compare latency, throughput, CPU, prepared statement count, errors, and memory.
7. Test traffic spikes and rolling deployments to verify total connections/cache stay within quota.
8. Adjust cache size, SQL limit, or pool size; maintain safe headroom below server limits.
9. Document the selected configuration, rationale, and alert thresholds for operations.

Never optimize based on a single query or a short run. Caching helps workloads with high SQL repetition, but offers little for dynamic SQL or one-off queries. Always measure under production-like conditions.

## 13. Common Mistakes

- **Enabling caching without closing statements:** the cache cannot reuse statements that are never returned. Use `try-with-resources`.
- **Confusing a per-connection cache with a global cache:** total entries scale by the connection count across all instances. Calculate budgets server-wide.
- **Setting cache size too high:** connection pools retain thousands of server-side statements. Start small and measure `Prepared_stmt_count`.
- **SQL strings constantly differ:** concatenated literals cause cache misses. Use placeholders for values and keep SQL templates stable.
- **Long SQL exceeds cache limit:** statements execute but are never cached. Check `prepStmtCacheSqlLimit` and increase only when measurable benefit exists.
- **Assuming server-side prepare is always faster:** overhead and workload patterns can produce different outcomes. Benchmark `useServerPrepStmts`.
- **Sharing statements across threads or connections:** statements are session-bound and unsafe for arbitrary sharing. Create statements within the unit of work.
- **Raising `max_prepared_stmt_count` to hide leaks:** a higher quota does not fix broken lifecycles. Find the root cause and recalculate limits.
- **Ignoring rolling deployments:** overlapping old and new pools can temporarily spike connection/statement counts. Include deployment phases in load tests.

## 14. Hands-On Exercise

In a Java application using MySQL Connector/J and a connection pool:

1. Record the Connector/J version, pool type, maximum pool size, and MySQL's `max_prepared_stmt_count`.
2. Create an endpoint that repeatedly executes the same `SELECT ... WHERE id = ?` and a parameterized `UPDATE`.
3. Run a benchmark with caching disabled, then enable `cachePrepStmts=true` with a small cache size.
4. Next, test adding `useServerPrepStmts=true`; compare latency, throughput, and `Prepared_stmt_count`.
5. Increase connection pool size and observe potential prepared statement counts when more connections are utilized.
6. Temporarily introduce a code branch that omits closing statements in a test environment to observe leak symptoms, then fix it with `try-with-resources`.
7. Test SQL longer than `prepStmtCacheSqlLimit` and SQL with varying placeholder variants; observe cache impact.
8. Inspect state after connections return to the pool and after the pool closes physical connections.

**Completion criteria:** explain which connection scope the cache lives at, calculate server-wide prepared statement budgets, close all JDBC resources properly, and base configuration choices on measured data.

## Conclusion

`cachePrepStmts` can reduce repetitive overhead when applications frequently run the same SQL templates, but the cache is tied to each physical connection and server-side prepared statements share a global limit across the MySQL instance. Coordinate cache size with connection pooling, SQL length limits, and `max_prepared_stmt_count`; close `ResultSet`, `PreparedStatement`, and `Connection` via `try-with-resources`; and measure hit/miss behavior, statement counts, and performance before rolling out to production.
