# Connector/J

## Closing ResultSet/Statement, Returning Connections to the Pool, and Cleaning Up Session State

In Java applications using MySQL Connector/J, a query typically opens multiple resources in sequence: acquiring a connection, creating a statement, executing SQL, and reading a ResultSet. When processing finishes, these resources must be closed in the right order to release cursors, memory, server-side statements, and finally the connection. When the connection comes from a connection pool, calling close on the Connection object usually returns the logical connection to the pool for reuse; it does not necessarily close the physical socket.

Returning a connection to the pool is also a session-state handoff boundary. An open transaction, session variable, temporary table, named lock, or SQL mode change can leak into the next request if the pool does not reset that state. Therefore, applications must close ResultSets/Statements, end transactions explicitly, and restore any session mutations they introduced.

In the **DATABASE_MYSQL** module, you learn to master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, and concurrency control. You also practice reading execution plans, optimizing queries, authorization, backups, and handling relational database operational issues. This lesson connects those skills to the JDBC lifecycle: resource management, transactions, session state, query performance, and pool reliability.

### 1. JDBC Resource Lifecycle

A query operation typically involves these resources:

1. **DataSource/Connection:** provides the database session. With a pool, the application borrows a logical connection.
2. **Statement/PreparedStatement/CallableStatement:** represents an SQL statement or stored procedure call.
3. **ResultSet:** holds the cursor for reading query results.
4. **Stream/LOB:** large data may be read through InputStream, Reader, Blob, or Clob.

Resources have an ownership hierarchy. ResultSets are created from Statements; Statements are created from Connections. Close child resources before parent resources:

~~~java
try (Connection conn = dataSource.getConnection();
     PreparedStatement ps = conn.prepareStatement(
         "SELECT order_id, total_amount FROM orders WHERE status = ?")) {

    ps.setString(1, "PAID");

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long orderId = rs.getLong("order_id");
            BigDecimal total = rs.getBigDecimal("total_amount");
            // Process current row.
        }
    }
}
~~~

Try-with-resources automatically calls close when exiting the block, even on exceptions. Within a resource declaration list, Java closes resources in reverse order of declaration: ResultSet closes before PreparedStatement, then Connection. Nesting ResultSet in its own block clarifies when result consumption ends and avoids holding cursors longer than needed.

JDBC also specifies that closing a Statement closes the current ResultSet produced by that Statement. Still, manage ResultSets explicitly with try-with-resources, especially when handling multiple result sets, generated keys, or streams. Never keep a ResultSet alive after its Statement/Connection has closed.

### 2. Why Must ResultSet and Statement Be Closed?

Closing a ResultSet releases result-reading state. Depending on execution mode and Connector/J settings, rows may already be buffered on the client or still streaming incrementally from the server. For large results, an unclosed ResultSet can hold cursors, protocol state, memory, and keep the connection busy for a long time.

Closing a Statement frees resources bound to that statement. For server-side prepared statements, the server may be holding a statement handle. Connector/J may cache prepared statements if caching is enabled; calling close is still required because the driver manages returning internal objects to the cache.

Failing to close resources causes:

- Connections cannot return to the pool promptly.
- Pools can run out of available connections even without increased request volume.
- The server may retain cursors or prepared statements longer than needed.
- Streaming queries may leave the protocol in an unconsumed state.
- Application memory can grow from retained ResultSets and mapped objects.
- Exceptions can easily leak resources if closing happens only on the success path.

Never store a Statement/ResultSet in a global variable shared across requests. JDBC Connection, Statement, and ResultSet are not thread-safe shared objects. Each unit of work should borrow its own connection and own its resources.

### 3. Closing Multiple Result and Statement Types

#### 3.1. PreparedStatement and ResultSet

This is the most common case. Declare both Connection and PreparedStatement in try-with-resources, then close ResultSet in a nested block:

~~~java
String sql = """
    SELECT order_id, created_at
    FROM orders
    WHERE customer_id = ?
    ORDER BY created_at DESC
    """;

try (Connection conn = dataSource.getConnection();
     PreparedStatement ps = conn.prepareStatement(sql)) {

    ps.setLong(1, customerId);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("order_id");
            Timestamp createdAt = rs.getTimestamp("created_at");
            // Map to DTO or run business logic.
        }
    }
}
~~~

Using PreparedStatement for parameters prevents concatenating user input into SQL strings and lets the driver/server handle typed parameters properly. Table names, column names, and SQL keywords cannot be passed via ? placeholders; if dynamic selection is required, use an allowlist and quote identifiers per rules.

#### 3.2. Generated Keys

When inserting and needing auto-generated keys, also close the ResultSet returned by getGeneratedKeys:

~~~java
String sql = "INSERT INTO orders(customer_id, status) VALUES (?, ?)";

try (Connection conn = dataSource.getConnection();
     PreparedStatement ps = conn.prepareStatement(
         sql, Statement.RETURN_GENERATED_KEYS)) {

    ps.setLong(1, customerId);
    ps.setString(2, "NEW");
    ps.executeUpdate();

    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (keys.next()) {
            long orderId = keys.getLong(1);
        }
    }
}
~~~

Do not assume every driver or statement returns generated keys identically. Check Connector/J documentation and test multi-row inserts, batches, and tables with triggers.

#### 3.3. Stored Procedures and Multiple ResultSets

CallableStatement can return multiple ResultSets, update counts, or output parameters. Read and close each ResultSet before advancing to the next result:

~~~java
try (Connection conn = dataSource.getConnection();
     CallableStatement cs = conn.prepareCall("{call get_order_report(?)}")) {

    cs.setLong(1, customerId);
    boolean hasResultSet = cs.execute();

    while (true) {
        if (hasResultSet) {
            try (ResultSet rs = cs.getResultSet()) {
                while (rs.next()) {
                    // Read current result.
                }
            }
        } else if (cs.getUpdateCount() == -1) {
            break;
        }

        hasResultSet = cs.getMoreResults(Statement.CLOSE_CURRENT_RESULT);
    }
}
~~~

This pattern illustrates the result consumption loop; a specific stored procedure may return output parameters or multiple update counts. When a procedure produces multiple results, verify result order and counts against the procedure contract. Never leave unread results behind while keeping the connection open.

### 4. Large ResultSets, Streaming, and Connection Hold Time

Connector/J can buffer entire query results on the client depending on execution mode. For large datasets, this increases heap usage. Row-by-row streaming or cursor fetch modes reduce client memory, yet keep the connection busy until reading completes or the ResultSet closes.

When processing large results:

- SELECT only needed columns; avoid fetching unused LOBs.
- Split work by key or key ranges whenever possible.
- Use fetch size and cursor/streaming modes suitable for Connector/J.
- Read ResultSets sequentially without retaining read rows in collections unless necessary.
- Close ResultSet immediately upon completion or cancellation.
- Set query timeouts and monitor connection hold duration.

Connector/J offers options such as useCursorFetch and useServerPrepStmts for cursor-based fetching. Forward-only streaming also follows version-specific fetch size rules. Never copy a fetch size from an old example without verifying your active driver configuration.

If an application reads slowly from a ResultSet while trying to run another query on the same connection, watch out for streaming and protocol limits. Many modes require fully consuming or closing the current result before executing the next statement on that connection.

For Blobs/Clobs or streams returned from a ResultSet, finish reading and close the stream before closing the ResultSet. Never pass a stream to another layer to use after the connection has returned to the pool.

### 5. Returning Connections to the Pool

#### 5.1. Logical Connections vs. Physical Connections

DataSource is the JDBC interface providing connections. A DataSource itself does not necessarily perform pooling. With a pool such as HikariCP or an application-server-managed pool, getConnection() normally returns a proxy/logical connection.

In the pooled model:

1. The application calls dataSource.getConnection() to borrow a connection.
2. The application runs queries/transactions.
3. The application calls conn.close().
4. The pool reclaims the logical connection and returns the physical connection to the idle pool if healthy and eligible for reuse.

Without a pool, close() normally closes the physical connection and frees server sockets/sessions. Knowing how your DataSource is configured is essential to understanding what close actually does.

Example using HikariCP:

~~~java
HikariConfig config = new HikariConfig();
config.setJdbcUrl("jdbc:mysql://db.example.net:3306/appdb");
config.setUsername("app_user");
config.setPassword(secret);
config.setMaximumPoolSize(20);
config.setAutoCommit(true);

HikariDataSource dataSource = new HikariDataSource(config);
~~~

The HikariDataSource object lives for the application's lifetime; close it at shutdown to release the pool. Never instantiate a new pool per request.

#### 5.2. close Does Not Mean Skipping Cleanup

Pools typically track standard JDBC attributes modified by the application—such as autoCommit, readOnly, transaction isolation, catalog/schema, or network timeout depending on implementation. When the logical connection closes, the pool may roll back unfinished transactions and restore tracked attributes.

However, never assume every pool resets all SQL-created session state. Commands such as SET @user_var, SET SESSION sql_mode, SET time_zone, USE schema, creating temporary tables, or acquiring named locks can leave lingering state if the pool does not physically reset the session or track those mutations.

Some pools/drivers can issue a MySQL protocol connection-reset command; whether it is used depends on version, settings, and implementation. Check your pool and Connector/J documentation, then test by re-borrowing the same physical connection if you need proof of behavior. Never rely on close returning cleanly as proof that every session variable was wiped.

### 6. Ending Transactions Before Closing

When autoCommit=true, each statement normally commits independently upon succeeding. When autoCommit=false, modifications remain part of the transaction until the application calls commit or rollback.

Always finish transactions explicitly before returning a connection:

~~~java
try (Connection conn = dataSource.getConnection()) {
    conn.setAutoCommit(false);

    try (PreparedStatement debit = conn.prepareStatement(
             "UPDATE accounts SET balance = balance - ? WHERE account_id = ?");
         PreparedStatement credit = conn.prepareStatement(
             "UPDATE accounts SET balance = balance + ? WHERE account_id = ?")) {

        debit.setBigDecimal(1, amount);
        debit.setLong(2, fromAccount);
        debit.executeUpdate();

        credit.setBigDecimal(1, amount);
        credit.setLong(2, toAccount);
        credit.executeUpdate();

        conn.commit();
    } catch (SQLException | RuntimeException ex) {
        try {
            conn.rollback();
        } catch (SQLException rollbackError) {
            ex.addSuppressed(rollbackError);
        }
        throw ex;
    }
}
~~~

This example illustrates a fund-transfer transaction. In production code, verify affected row counts, account existence, sufficient balance, deadlocks, and retry rules. If commit() fails due to connection loss, the transaction outcome may be uncertain on the client side; never blindly retry a non-idempotent transaction. Reconcile business state or use transaction IDs/idempotency keys.

JDBC recommends applications commit or roll back before calling close. Behavior when closing a connection with an active transaction depends on implementation; pools often perform a defensive rollback on reclamation, but that is a safety net, not primary transaction management.

If you changed autoCommit or isolation, restore the baseline before returning the connection. Order matters: roll back any active transaction first, then restore other attributes, and finally re-enable autoCommit if baseline requires it. Flipping autoCommit from false to true can implicitly commit an active transaction.

### 7. Session State That Needs Cleanup

A MySQL session persists alongside the physical connection. The following mutations can leak into the next request if the connection is reused:

| State | Example | How to handle |
|---|---|---|
| Transaction/autocommit | SET autocommit = 0, uncommitted transaction | Explicit commit/rollback; restore baseline autoCommit |
| Isolation/read-only | SET SESSION TRANSACTION ISOLATION LEVEL ..., SET SESSION transaction_read_only=... | Save prior state or use JDBC APIs; restore before returning connection |
| Session variables | SET @tenant_id = ... | Avoid if possible; if used, save and restore or ensure session reset |
| System/session variables | SET SESSION sql_mode, time_zone, foreign_key_checks, unique_checks | Save old values and restore accurately |
| Default schema | USE appdb, Connection.setCatalog()/setSchema() | Restore baseline catalog/schema |
| Temporary tables | CREATE TEMPORARY TABLE | Explicit DROP in finally; do not assume commit drops it |
| Named locks | GET_LOCK() | Call RELEASE_LOCK(); check acquire/release return values |
| Table locks | LOCK TABLES | UNLOCK TABLES before returning connection |
| Prepared statements/cursors | Open Statement or ResultSet | Close all ResultSets, Statements, and streams |
| Warnings | JDBC warning chain | Read if needed, then clearWarnings(); this does not reset session variables |
| Client info/network timeout | JDBC setClientInfo, setNetworkTimeout | Restore baseline per pool contract |

SET SESSION affects only the current session; SET GLOBAL affects server-wide config and normally requires administrative privileges. Business applications should never mutate GLOBAL variables to serve a single request.

#### 7.1. Session Variables and SQL Mode

Example code modifying SQL mode:

~~~sql
SELECT @@SESSION.sql_mode;
SET SESSION sql_mode = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';
~~~

If the connection returns to the pool without restoring it, subsequent queries can execute under an unexpected SQL mode. Save the original value and restore it in finally, or use a verified session reset mechanism. When saving/restoring via SQL strings, handle the complete value and never concatenate user input.

Similarly, altering time_zone can shift TIMESTAMP reads/writes. Set a standard timezone in pool/connection initialization config if it is an application-wide policy; avoid ad-hoc per-request mutations that might be left uncleaned.

#### 7.2. Temporary Tables and Named Locks

Temporary tables are session-scoped and survive COMMIT. If a request creates a temporary table and returns the connection to the pool without running DROP, a later request borrowing the same session may see the stale table or fail trying to create a table with the same name.

Named locks acquired via GET_LOCK() are also session-scoped. Transaction rollbacks do not release named locks. Always call RELEASE_LOCK() in finally and check the return value. Closing the physical session releases the lock, but a connection pool keeps the physical session alive after logical connection close.

### 8. Cleanup Pattern for Custom State

When code must temporarily alter connection attributes, save old state and restore it. The following example assumes an application temporarily changes the isolation level:

~~~java
try (Connection conn = dataSource.getConnection()) {
    // Example assumes the pool supplies a clean connection with autoCommit=true.
    int originalIsolation = conn.getTransactionIsolation();
    boolean originalAutoCommit = conn.getAutoCommit();
    boolean transactionActive = false;
    boolean safeToReturn = true;
    Throwable primaryFailure = null;
    SQLException cleanupFailure = null;

    try {
        conn.setTransactionIsolation(Connection.TRANSACTION_READ_COMMITTED);
        conn.setAutoCommit(false);
        transactionActive = true;

        // Perform work inside the transaction.

        conn.commit();
        transactionActive = false;
    } catch (SQLException | RuntimeException ex) {
        primaryFailure = ex;
        if (transactionActive) {
            try {
                conn.rollback();
                transactionActive = false;
            } catch (SQLException rollbackError) {
                safeToReturn = false;
                ex.addSuppressed(rollbackError);
            }
        }
        throw ex;
    } finally {
        if (safeToReturn) {
            try {
                if (transactionActive) {
                    conn.rollback();
                }
                conn.setTransactionIsolation(originalIsolation);
                if (conn.getAutoCommit() != originalAutoCommit) {
                    conn.setAutoCommit(originalAutoCommit);
                }
            } catch (SQLException resetError) {
                safeToReturn = false;
                cleanupFailure = resetError;
                if (primaryFailure != null) {
                    primaryFailure.addSuppressed(resetError);
                }
            }
        }

        if (!safeToReturn) {
            // Invoke the active pool's eviction API before the connection can be reused.
        }
        if (cleanupFailure != null && primaryFailure == null) {
            throw cleanupFailure;
        }
    }
}
~~~

This is an illustrative skeleton; wire the eviction step to your specific pool's API before production use. If commit throws due to connection loss, the transaction outcome may be uncertain even if a subsequent rollback appears to succeed; reconcile business state via a transaction key/idempotency key. Never let an exception in finally mask the original exception. JDBC provides no single portable API across all pools to evict a logical connection.

For session state mutated via SQL, follow a similar pattern:

1. Read and save the previous value of the variable/session setting.
2. Mutate for the shortest scope possible.
3. Execute the work.
4. Restore in finally, even if SQL fails.
5. If restoration fails, never return a dirty connection to the pool.

If a setting can be configured uniformly for the entire pool, place it in DataSource config or connection initialization instead of toggling it per request.

### 9. Pool Reset Settings and Behavior

Different pools have different reclamation rules. When choosing and configuring a pool, verify:

- Does it roll back uncommitted transactions when a logical connection closes?
- Does it restore autoCommit, readOnly, isolation, catalog/schema, and network timeout?
- Does it reset server-side session state, or only JDBC attributes tracked by the pool?
- Does it validate connections on borrow or return, and how does it handle broken connections?
- Does it evict connections on fatal errors?
- Are leak detection, maximum lifetime, idle timeout, and validation timeout configured?

MySQL supports a connection-reset protocol command to return a physical session to its initial state without opening a new socket. Still, applications should never assume JDBC's Connection.close() always sends this reset command. Verify whether your specific pool and driver use it, and test states such as user variables, temporary tables, prepared statements, and locks.

Connector/J properties such as cachePrepStmts, useServerPrepStmts, or session-state tracking options affect how the driver manages statements and internal state. They do not replace application-level resource closing or cleanup rules. Toggle them only after measuring and testing with your deployed Connector/J version.

### 10. Handling Exceptions and Unhealthy Connections

When Statement/ResultSet throws SQLException, classify the failure:

- Business SQL errors such as duplicate keys, constraint violations, or syntax errors.
- Transaction errors such as deadlocks or lock wait timeouts.
- Connection errors such as communications link failures, socket timeouts, or server-closed sessions.
- Cleanup errors such as failed rollback/close.

For deadlocks, MySQL normally rolls back the victim transaction; applications can retry the entire transaction if idempotent and bounded by retry/backoff limits. For connection loss during commit, outcomes may be uncertain; reconcile by transaction key before rerunning.

Pools normally detect certain connection-fatal errors and evict physical connections. However, not every SQLException means the connection is broken. Never tear down the entire pool over a single SQL error.

Connection.isClosed() only reports JDBC closed state; it does not prove the socket is alive. Use pool-provided validation or Connection.isValid(timeout) when checking health. Avoid running a validation query on every request if the pool already performs proper validation.

If rollback or cleanup fails, log both the primary exception and the secondary exception. With try-with-resources, exceptions thrown while closing resources are attached as suppressed exceptions if a primary exception already exists; preserve those suppressed details in logs for investigation.

### 11. Monitoring Connection Pools and Detecting Leaks

Key metrics:

| Metric | Meaning | Signal to investigate |
|---|---|---|
| Active connections | Connections currently borrowed by the application | Constantly near maximum pool size |
| Idle connections | Connections ready for requests | Stuck at 0 while requests wait |
| Pending/waiting threads | Requests waiting to borrow a connection | Sustained growth, rising latency |
| Connection acquisition time | Wait time to obtain a connection | Sudden spike in P95/P99 |
| Usage/hold time | How long a request holds a connection | Slow queries or non-DB work performed while holding connection |
| Leak detection | Connections borrowed too long without closing | Stack trace pointing to code failing to return connections |
| Validation failures | Connections failing health checks | Network, server, or pool lifetime issues |

Never increase maximum pool size just to hide long connection hold times. An oversized pool exposes MySQL to too many concurrent sessions, raising contention and lowering throughput. Optimize queries, shorten hold times, and fix resource leaks before adjusting pool size.

Never hold a connection while calling HTTP services, sending emails, waiting on user input, or processing files. Borrow a connection right before database work and return it immediately after the transaction/statement finishes.

### 12. Troubleshooting

| Symptom | Possible cause | Resolution |
|---|---|---|
| Pool runs out of connections | ResultSet/Statement/Connection not closed or queries held too long | Use try-with-resources, enable leak detection, and inspect stack traces |
| Next request sees another session's data/state | Session variable, SQL mode, timezone, or schema not restored | Audit cleanup and pool reset behavior |
| Commands out of sync or next query fails to run | ResultSet/multiple results not fully read or closed | Consume/close results before reusing Statement/Connection |
| Server holds many prepared statements | Unclosed statements or misconfigured cache | Close PreparedStatements, inspect cache and server statement counts |
| Java heap grows during large queries | Driver buffered entire ResultSet or app retained objects | Use streaming/cursor fetch appropriately, narrow columns, and process in batches |
| Temporary table already exists on new request | Stale temporary table from prior session in pool | Explicit DROP or verified session reset |
| Named lock still held after request completes | RELEASE_LOCK not called and physical session stayed alive | Release in finally, monitor lock owner and cleanup |
| Transaction committed unexpectedly | Re-enabled autoCommit before rollback or faulty pool state | Finish transaction first, restore autoCommit in safe order |
| Connection close throws error | Connection already broken or error during pool reclamation/reset | Log suppressed exceptions, check eviction and health metrics |
| Recurring deadlocks | Inconsistent lock acquisition order or overly long transactions | Standardize update ordering, shorten transactions, and use bounded retries |

### 13. Pre-Return Connection Checklist

- [ ] All ResultSets have been fully consumed or closed.
- [ ] All Statements, PreparedStatements, and CallableStatements are closed.
- [ ] All InputStreams/Readers/Blobs/Clobs opened from results are processed and closed.
- [ ] Transaction is explicitly committed or rolled back.
- [ ] No active transaction remains open before close.
- [ ] autoCommit, isolation, readOnly, and catalog/schema are restored to baseline.
- [ ] Session variables, SQL mode, timezone, and custom session settings are cleaned up.
- [ ] Temporary tables are dropped or session reset is verified.
- [ ] Named locks are released; table locks are unlocked.
- [ ] No pending cursors, multiple results, or batches remain unconsumed.
- [ ] If cleanup fails, connection is evicted from the pool via the appropriate mechanism.
- [ ] Pool metrics and logs show no sustained connection leaks.

### 14. Hands-On Exercise

A Java application uses Connector/J and HikariCP. A request borrows a connection, sets autoCommit=false, creates a temporary table, sets @tenant_id, calls a procedure returning two ResultSets, and hits an exception while processing the first result. The request catches the exception and calls conn.close(). The next request borrows a connection from the pool and sees the old temporary table.

1. Which JDBC resources must be closed and in what order?
2. Why might Connection.close() not close the physical MySQL session?
3. Where must rollback happen, and how should you handle rollback itself throwing SQLException?
4. What state could remain besides autoCommit?
5. How do you ensure temporary tables and named locks are cleaned up even when the procedure fails?
6. Rewrite the code using try-with-resources and finally to close every ResultSet, Statement, and Connection.
7. What should you configure or test in HikariCP/Connector/J to verify whether sessions are reset upon pool return?
8. Which metrics would you use to distinguish a connection leak from a slow query holding a connection for a long time?

### 15. Operational Principles

Every ResultSet and Statement must have a clear owner and be closed as soon as work finishes. Every transaction must be explicitly committed or rolled back. With a connection pool, close returns the logical connection to the pool; the physical session can remain alive, so any session mutations must be restored or reset through a verified mechanism. Use try-with-resources, keep transactions short, clean up temporary tables/locks/session variables, monitor pool metrics, and evict connections whenever clean state cannot be confirmed. This ensures the next request receives a clean session and prevents pool exhaustion under load.
