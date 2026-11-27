# SQLState, Vendor Code, CommunicationsException, and Retry Error Classification

When a Java application interacts with MySQL through Connector/J, an SQL failure is typically represented as an **SQLException**. To decide whether to retry, the application needs at least three pieces of information: SQLState, vendor error code, and the root cause in the exception chain. For network failures such as **CommunicationsException**, it must also know whether the failure happened before sending the statement, during execution, or right at **COMMIT**, because transaction state may be uncertain.

This lesson belongs to the **DATABASE_MYSQL** module and focuses on handling connection and SQL errors in Java applications: distinguishing data errors from transient errors, identifying communications failures, managing connection pools, and designing bounded retries that avoid creating duplicate transactions.

## 1. What Information Does SQLException Contain?

JDBC APIs typically throw **SQLException** when queries, connections, or transaction operations fail. This class exposes several informational fields:

| API | Meaning | How to use |
|---|---|---|
| **getSQLState()** | Five-character status code per SQLState convention | Classifies error groups at a relatively standardized level |
| **getErrorCode()** | Driver/database-specific error code (vendor code) | Identifies specific MySQL errors such as 1062, 1205, or 1213 |
| **getMessage()** | Operator-readable error description | Aids diagnosis; never use message text as the primary classification key |
| **getNextException()** | Next exception in the JDBC error chain | Reads additional errors supplied by the driver or batch operations |
| **getCause()** | Root cause per Java's exception chaining mechanism | Locates underlying network, timeout, or lower-level errors |

Not every error populates every field. A client-side driver-generated exception may have a vendor code of 0 or a generic SQLState. Conversely, errors returned by MySQL Server normally carry the corresponding MySQL error number and SQLState.

Never log only getMessage() and discard error codes. Messages can vary across driver versions, locales, or context. Log SQLState, vendor code, exception class, root cause, and transaction stage.

## 2. What Is SQLState?

SQLState is a five-character code classifying statuses or errors according to SQL conventions. The first two characters identify the error class; the remaining three identify the specific condition within that class.

Examples:

| SQLState | Class | Common meaning |
|---|---|---|
| **08xxx** | Connection exception | Connection or communications failure |
| **22xxx** | Data exception | Incompatible data, conversion error, or out-of-range value |
| **23xxx** | Integrity constraint violation | Key or data constraint violation |
| **28xxx** | Invalid authorization | Authentication or access privilege failure |
| **40xxx** | Transaction rollback | Transaction rolled back, possibly due to deadlock or serialization conflict |
| **42xxx** | Syntax error or access rule violation | SQL syntax error or object access violation |
| **HYT00**, **HYT01** | Timeout in some drivers | Convention-based timeout codes used by certain drivers |

SQLState is more standardized than vendor codes, though not every driver maps every error identically. MySQL may return a general SQLState such as **HY000** for some errors. Therefore, combine SQLState with the MySQL error number and operation context.

### Classifying by the First Two Characters

In Java code, you can extract the error class with:

~~~java
String sqlState = exception.getSQLState();
String sqlStateClass =
        sqlState != null && sqlState.length() >= 2
                ? sqlState.substring(0, 2)
                : null;
~~~

For example, **08S01** belongs to class 08 and usually indicates a communications link failure. **23000** belongs to class 23 and typically indicates a constraint violation.

Do not assume every class 08 error can be retried immediately. A connection may drop after the server already committed the transaction; resending the entire request could then create duplicate data.

### Standard JDBC Exception Subclasses

Alongside SQLState, JDBC defines several subclasses describing error semantics:

- **SQLTransientException:** error that may succeed if retried without changing external causes.
- **SQLNonTransientException:** retrying verbatim will normally fail; data, SQL, privileges, or config must be fixed.
- **SQLRecoverableException:** the application can recover by closing the current connection, acquiring a new one, and retrying an appropriate operation.
- **SQLTransientConnectionException** and **SQLNonTransientConnectionException:** describe transient and non-transient connection errors.
- **SQLTransactionRollbackException:** transaction rolled back, typically due to serialization failure or deadlock.
- **SQLIntegrityConstraintViolationException:** data integrity constraint violation.
- **SQLSyntaxErrorException:** SQL syntax or object access error.
- **SQLTimeoutException:** operation exceeded a configured timeout.

These subclasses help write less vendor-coupled code, though drivers can map specific errors differently. Still inspect SQLState, vendor code, and transaction context. An SQLTimeoutException does not prove the server never ran the statement; nor does SQLRecoverableException mean you can resend a non-idempotent write.

## 3. Vendor Codes and MySQL Error Numbers

**SQLException.getErrorCode()** returns the vendor-defined error code. With Connector/J, when MySQL Server returns an error, this value normally matches the MySQL error number.

Key codes:

| MySQL error code | Common name | Meaning | Handling approach |
|---:|---|---|---|
| 1062 | ER_DUP_ENTRY | Duplicate PRIMARY/UNIQUE key | Check business rules or idempotency; never retry blindly |
| 1045 | ER_ACCESS_DENIED_ERROR | Authentication denied | Check user, host, password, and authentication plugin |
| 1142 | ER_TABLEACCESS_DENIED_ERROR | Missing table privileges | Fix grants following least privilege |
| 1054 | ER_BAD_FIELD_ERROR | Referenced column does not exist | Fix SQL or align schema |
| 1064 | ER_PARSE_ERROR | SQL syntax error | Fix statement or generated SQL |
| 1205 | ER_LOCK_WAIT_TIMEOUT | Lock wait timeout expired | Roll back transaction, inspect blocking transaction, then consider retry |
| 1213 | ER_LOCK_DEADLOCK | InnoDB detected a deadlock | Retry entire transaction if business logic permits |
| 2002 | CR_CONNECTION_ERROR | Cannot connect to local socket/endpoint | Check endpoint, socket, service, and network |
| 2003 | CR_CONN_HOST_ERROR | Cannot connect to MySQL host | Check DNS, routing, firewall, port, and server |
| 2006 | CR_SERVER_GONE_ERROR | Server closed or connection unusable | Evict connection from pool; determine whether operation may have run |
| 2013 | CR_SERVER_LOST | Lost connection during operation | Inspect failure stage; commit outcome may be unknown |

Codes 2002, 2003, 2006, and 2013 are MySQL client error codes. Depending on where they originate, the driver may wrap them in an SQLException or a specialized exception. Do not assume every network failure yields one exact vendor code.

Vendor code is an integer, so compare using **getErrorCode()**, never by parsing numbers from the message string. If a proxy or gateway sits between the application and MySQL, errors may originate from the proxy rather than MySQL Server, producing different vendor codes and SQLStates.

## 4. What Is CommunicationsException?

**CommunicationsException** is Connector/J's specialized exception representing communication failures between the Java application and MySQL Server. It typically occurs when a socket closes, a connection resets, the server fails to respond within a timeout, or the driver cannot send/receive data over the connection.

Common class name in modern Connector/J:

~~~java
com.mysql.cj.jdbc.exceptions.CommunicationsException
~~~

This is a Connector/J-specific detail. Applications can catch **SQLException** to remain JDBC-portable, then inspect SQLState, the cause chain, and the concrete exception name for diagnostics.

Common causes:

- MySQL Server restart, crash, or failover.
- Firewall, NAT, load balancer, or proxy closing an idle connection.
- Network interruption or packet loss between application and database.
- DNS pointing to an invalid address.
- Server overload failing to answer within client-configured timeouts.
- Long-running query or result set exceeding a network component's timeout.
- Application reusing a connection already closed by the server or pool.

### SQLState and Vendor Code for Communications Failures

Communications link failures are commonly mapped to SQLState class 08, frequently **08S01**. However, the driver may raise the exception before receiving any server response, in which case the vendor code may be 0 or not a server error code.

Therefore:

1. Read SQLState if present.
2. Read vendor code if present.
3. Inspect exception type and the entire cause chain.
4. Record the timestamp and operation stage.
5. Correlate application logs, MySQL logs, proxy logs, and network infrastructure.

Never classify solely on whether the message contains the phrase communications link failure. Similar errors can arise across multiple network layers.

## 5. Classifying Connection Failures by Timing

The most critical question when handling communications failures is whether the server might have already executed the operation.

| Time of disconnection | What can be concluded | Action |
|---|---|---|
| Before sending statement | Usually no operation reached the server | Open a fresh connection and retry if the request still has budget |
| While sending statement | Unknown whether the server received the complete statement | Check state; do not assume the operation did not run |
| While server is executing | Server may have done partial or full work | For explicit transactions, clean up connection and transaction state; never reuse failed connection |
| After sending COMMIT but before receiving response | Commit may have succeeded even though client missed the ACK | Treat outcome as unknown; query by idempotency key or business ID |
| While reading ResultSet | Statement may have completed while response rows were truncated | Close/evict failed connection; rerun read query only if safe and within deadline |

### Why Failures at COMMIT Are Dangerous

Suppose the application sends:

~~~sql
START TRANSACTION;
INSERT INTO orders(order_id, customer_id, total_amount)
VALUES (90001, 42, 125000);
COMMIT;
~~~

The server may have written and committed the transaction, yet the network drops before the response reaches Java. The client receives CommunicationsException and does not know whether the order was created.

If the application retries the INSERT with a different order ID, the customer could end up with two orders. If it retries the same order_id guarded by a unique key, MySQL may return a duplicate key error; that is a signal to look up the previous result, not a reason to generate a new ID.

The solution is attaching a stable request ID/idempotency key to the business request, persisting it in the same transaction as the order, and checking status before deciding to resend.

## 6. Error Categories and Retry Decisions

Retry decisions should depend on error category, transaction state, operation idempotency, and remaining request deadline. The table below guides JDBC applications with MySQL:

| Error category | Examples | Auto retry? | Conditions |
|---|---|---|---|
| Deadlock | SQLState 40001, MySQL 1213 | Possible | Roll back entire transaction and rerun from the start |
| Lock wait timeout | MySQL 1205, often SQLState HY000 | Conditionally possible | Proactively roll back entire transaction, check load, and bound attempts |
| Communications failure | SQLState class 08, CommunicationsException, 2006/2013 | Not by default | Needs a fresh connection; determine operation type and whether commit may have happened |
| Query timeout | SQLTimeoutException or driver timeout | Conditional | Cancel/roll back transaction, verify state, and retry only when safe |
| Constraint violation | SQLState class 23, MySQL 1062 | Normally no | Handle per business rules or idempotency |
| Syntax/schema error | SQLState class 42, MySQL 1064/1054 | No | Fix SQL or schema |
| Authentication/authorization | SQLState class 28, MySQL 1045/1142 | No | Fix config or grants |
| Data conversion | SQLState class 22 | No | Fix input data or mapping |

### Retrying Deadlock 1213

InnoDB already selected the transaction as a victim and rolled it back to break the deadlock. The application can retry the entire transaction after a brief wait. Never rerun only the single SQL statement that hit the deadlock, because prior statements in that same transaction were already rolled back.

### Retrying Lock Wait Timeout 1205

By default, when a lock wait timeout occurs, MySQL normally rolls back only the timed-out statement; the transaction may remain open. The **innodb_rollback_on_timeout** variable can change this to roll back the entire transaction. Therefore, the application should explicitly call **rollback()** on the entire transaction before retrying, avoiding continuing on a partially rolled-back transaction.

### Communications Failure

Do not retry merely because SQLState starts with 08. First evict the failed connection from the pool and borrow a new connection. If the operation is a repeatable read query, retrying is usually straightforward. For writes or failures during COMMIT, require idempotency or outcome verification.

### Constraint Violation

Error 1062 may mean the request was already processed earlier, or that input violates a uniqueness rule. The application must inspect business keys and return an appropriate response. Never retry the same statement infinitely.

## 7. Traversing the SQLException Chain and Cause Chain

A single failure can wrap multiple linked exceptions. For instance, **BatchUpdateException** can carry update counts and a chained exception; a communications failure can wrap an underlying socket or timeout cause.

The following code traverses both getNextException() and getCause():

~~~java
import java.sql.SQLException;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

public final class SqlExceptionLogger {
    private SqlExceptionLogger() {}

    public static void logChain(SQLException root) {
        Set<Throwable> seen =
                Collections.newSetFromMap(new IdentityHashMap<>());

        for (SQLException sql = root;
             sql != null && seen.add(sql);
             sql = sql.getNextException()) {
            System.err.printf(
                    "SQLState=%s vendorCode=%d type=%s message=%s%n",
                    sql.getSQLState(),
                    sql.getErrorCode(),
                    sql.getClass().getName(),
                    sql.getMessage()
            );

            Throwable cause = sql.getCause();
            while (cause != null && seen.add(cause)) {
                System.err.printf(
                        "Cause type=%s message=%s%n",
                        cause.getClass().getName(),
                        cause.getMessage()
                );
                cause = cause.getCause();
            }
        }
    }
}
~~~

The **seen** set prevents infinite loops if exceptions contain cyclic references. In production, use a structured logger instead of System.err and redact sensitive information. Never log passwords, URLs with credentials, personal data, or query contents carrying secrets.

## 8. Error Classification in Java

A classifier should return an action category, not merely a retryable boolean. Example:

~~~java
import java.sql.SQLException;
import java.util.ArrayDeque;
import java.util.Collections;
import java.util.Deque;
import java.util.IdentityHashMap;
import java.util.Set;

enum SqlFailureKind {
    RETRY_TRANSACTION,
    CONNECTION_FAILURE,
    CONSTRAINT_VIOLATION,
    AUTH_OR_PERMISSION,
    SQL_OR_SCHEMA,
    DATA_ERROR,
    OTHER
}

final class MySqlErrorClassifier {
    static SqlFailureKind classify(SQLException root) {
        if (root == null) {
            return SqlFailureKind.OTHER;
        }

        Deque<Throwable> pending = new ArrayDeque<>();
        Set<Throwable> seen =
                Collections.newSetFromMap(new IdentityHashMap<>());
        pending.add(root);

        while (!pending.isEmpty()) {
            Throwable current = pending.removeFirst();
            if (current == null || !seen.add(current)) {
                continue;
            }

            if (current instanceof SQLException) {
                SQLException e = (SQLException) current;
                int code = e.getErrorCode();
                String state = e.getSQLState();

                if (code == 1213 || "40001".equals(state) || code == 1205) {
                    return SqlFailureKind.RETRY_TRANSACTION;
                }

                if (code == 2002 || code == 2003 ||
                    code == 2006 || code == 2013 ||
                    (state != null && state.startsWith("08"))) {
                    return SqlFailureKind.CONNECTION_FAILURE;
                }

                if (code == 1062 ||
                    (state != null && state.startsWith("23"))) {
                    return SqlFailureKind.CONSTRAINT_VIOLATION;
                }

                if (code == 1045 || code == 1142 ||
                    (state != null && state.startsWith("28"))) {
                    return SqlFailureKind.AUTH_OR_PERMISSION;
                }

                if (code == 1064 || code == 1054 ||
                    (state != null && state.startsWith("42"))) {
                    return SqlFailureKind.SQL_OR_SCHEMA;
                }

                if (state != null && state.startsWith("22")) {
                    return SqlFailureKind.DATA_ERROR;
                }

                SQLException next = e.getNextException();
                if (next != null) {
                    pending.addLast(next);
                }
            }

            Throwable cause = current.getCause();
            if (cause != null) {
                pending.addLast(cause);
            }
        }

        return SqlFailureKind.OTHER;
    }
}
~~~

This is a starter example, not an exhaustive MySQL error catalog. In real applications, also:

- Traverse both the cause chain and SQLException chain.
- Inspect **BatchUpdateException** and update counts when running batches.
- Classify communications failures by operation stage.
- Do not treat every timeout error as retryable.
- Add error codes and SQLStates suited to your workload and driver version.

Do not merge CONNECTION_FAILURE and RETRY_TRANSACTION into a single action. Connection errors require replacing the connection and potentially verifying business outcomes; deadlocks require rerunning a fresh transaction.

## 9. Retrying Transactions Properly

For deadlocks or retryable serialization/transaction rollback errors, start a fresh transaction, re-read data, and re-evaluate business preconditions. A bounded retry loop:

~~~java
int maxAttempts = 4;

for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);

        try {
            reserveInventory(connection, sku, quantity);
            createOrder(connection, requestId, sku, quantity);
            connection.commit();
            return;
        } catch (SQLException error) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                error.addSuppressed(rollbackError);
            }

            SqlFailureKind kind = MySqlErrorClassifier.classify(error);
            boolean retry =
                    kind == SqlFailureKind.RETRY_TRANSACTION;

            if (!retry || attempt == maxAttempts) {
                throw error;
            }
        }
    }

    backoffWithJitter(attempt);
}
~~~

**reserveInventory**, **createOrder**, and **backoffWithJitter** are illustrative domain methods. This loop only retries classified transaction errors. Communications failures need a separate branch because commit outcomes may be uncertain.

A backoff policy should include:

- Maximum attempt count.
- Increasing wait delays.
- Random jitter to prevent synchronized client retry storms.
- Overall request deadline.
- Metrics for retry counts, error codes, and exhausted failures.

Never retry infinitely or keep a transaction open while sleeping during backoff. Roll back and release the connection before waiting.

## 10. Handling CommunicationsException and Connection Pools

When a communications failure occurs, the current connection may be broken or out of sync with server state. Never return that connection to the pool as healthy.

Handling procedure:

1. Log SQLState, vendor code, exception class, cause chain, and operation stage.
2. Mark the connection unusable; close it and let the pool evict it.
3. If a transaction was open, attempt rollback while communication is still possible. If rollback fails, close the connection so the server cleans up the lost session.
4. Acquire a fresh connection for the next attempt.
5. If failure happened during commit, look up business state by idempotency key before resending.
6. Track failures by host, pool, timestamp, and topology to identify infrastructure causes.

### Checking the Pool

With HikariCP or similar pools, verify:

- Validation and how the pool detects closed connections.
- **maxLifetime** relative to connection limits on MySQL, proxies, firewalls, or load balancers.
- **keepaliveTime** if supported by your pool and version.
- **connectionTimeout** and connection acquisition wait times.
- **socketTimeout** and proxy/network timeouts.
- Active, idle, pending counts, and new connection creation rates.

Setting maxLifetime shorter than infrastructure idle/max connection limits reduces the chance of borrowing stale expired connections. Never pick timeouts arbitrarily; measure latency, query durations, and network policies before tuning.

### Distinguishing Timeouts

| Timeout | Layer | Meaning |
|---|---|---|
| Connection timeout | Connection open | Failed to establish a connection within the deadline |
| Socket timeout | Socket read/write | Failed to receive data within the wait limit |
| Query timeout | JDBC Statement | Query exceeded client-specified execution limit |
| Lock wait timeout | InnoDB | Lock wait exceeded server limit |
| Transaction timeout | Framework/application | Transaction exceeded business time budget |

Timeouts can overlap, yet they are not equivalent. For example, socketTimeout does not substitute for innodb_lock_wait_timeout, and Statement.setQueryTimeout() does not guarantee the transaction completely rolled back when the client catches the exception.

## 11. Idempotency When Commit Outcome Is Uncertain

When the network drops right at commit, the application cannot know for sure whether the transaction completed. A standard solution is attaching a stable idempotency key to each business request.

Example table tracking processed requests:

~~~sql
CREATE TABLE processed_requests (
  request_id VARCHAR(64) PRIMARY KEY,
  result_code VARCHAR(32) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
~~~

Inside the same transaction:

1. Insert request_id into the idempotency table.
2. Execute the business changes, such as creating an order or deducting inventory.
3. Store the business outcome associated with the request ID.
4. Commit.

If the client loses connection after commit, the retry uses the exact same request ID. The application queries the processed record and returns the original result. The unique key prevents the same request from executing twice.

Recording the idempotency key must occur inside the same transaction as the business changes. If written in a separate transaction, you can end up with the key persisted while business work failed, or business work committed without the key recorded.

For external side effects outside the database—such as sending emails, calling payment APIs, or publishing messages—consider a transactional outbox. Write the outbox event in the same transaction and have a worker dispatch it post-commit; the worker also needs idempotency to handle redelivery.

## 12. BatchUpdateException and Batch Errors

When executing a JDBC batch, the driver may throw **BatchUpdateException**. In addition to SQLState and vendor code, this exception exposes **getUpdateCounts()** to inspect the execution status of commands in the batch.

~~~java
try {
    statement.executeBatch();
} catch (BatchUpdateException error) {
    int[] counts = error.getUpdateCounts();
    for (int i = 0; i < counts.length; i++) {
        System.err.printf("batch[%d] updateCount=%d%n", i, counts[i]);
    }
    throw error;
}
~~~

The meaning of update counts depends on the driver and whether processing stops or continues on error. **Statement.EXECUTE_FAILED** marks a failed command; **Statement.SUCCESS_NO_INFO** indicates success without an exact affected row count from the driver.

If the batch ran in an explicit transaction and the application rolled back everything on error, you can evaluate retrying the whole batch after confirming the error is transient. If auto-commit was enabled, part of the batch may have already committed before failure. Never rerun an entire batch without verifying each item's status or enforcing idempotency.

## 13. Logging and Observing Errors Effectively

A useful connection/SQL error log should include:

- Timestamp and correlation ID/request ID.
- Service name, instance, and pool name.
- Database endpoint or logical datasource name, without credentials.
- SQLState, vendor code, exception class, and cause chain.
- Operation stage: connection acquisition, execute, result reading, commit, or rollback.
- Whether the transaction had auto-commit enabled.
- Retry attempt count and backoff delay.
- Idempotency verification outcome when commit status was uncertain.

Metrics to track:

- SQL error rate by SQLState class and vendor code.
- Communications failures by endpoint.
- Connections evicted from pools.
- Connection recreation rate.
- Query timeouts, lock wait timeouts, and deadlocks.
- Retry attempts, retry exhaustion, and overall latency.
- Requests encountering ambiguous commit states.

Never log raw SQL with bound values containing sensitive data. Log query fingerprints, operation names, or business table names alongside correlation IDs.

## 14. Scenario-Based Diagnostic Workflow

### Scenario A: SQLState 23000, vendor code 1062

This is normally a duplicate key error. Check which unique key was violated, whether the request ID matches an earlier call, and whether a prior attempt succeeded. If this is a redelivery of the same request, look up and return the prior result. If input genuinely violates business rules, return an error instead of retrying.

### Scenario B: SQLState 40001, vendor code 1213

InnoDB detected a deadlock. Record the transaction and queries involved, roll back the entire transaction, wait a brief backoff, and retry from the beginning with fresh data. If frequent, review row update ordering and lock hold durations.

### Scenario C: SQLState HY000, vendor code 1205

This is normally a lock wait timeout. Inspect the transaction holding the lock, runtimes, and **innodb_lock_wait_timeout**. Roll back the entire transaction in the application before retrying; if the system is overloaded, adding retries may worsen contention.

### Scenario D: SQLState 08S01 or CommunicationsException

Check error timing, server status, proxies, firewalls, DNS, and timeouts. Evict the connection from the pool. If the error occurred before sending the operation, retrying on a new connection may be safe. If it happened during commit, verify outcome via request ID before resending.

### Scenario E: No suitable driver or datasource initialization error

This is usually a dependency/classpath or URL issue, not a retryable SQL error. Check Connector/J in the runtime artifact, dependency tree, jdbc:mysql: prefix, and DataSource configuration.

## 15. Error Handling Design Checklist

- [ ] Read SQLState and vendor code rather than message strings alone.
- [ ] Traverse getNextException() and the cause chain.
- [ ] Record exception class and transaction stage.
- [ ] Distinguish deadlock, lock timeout, communications, and constraint errors.
- [ ] Retry deadlocks with a fresh transaction and rerun the entire unit of work.
- [ ] For lock timeouts, roll back the entire transaction before retrying.
- [ ] Never retry blindly when an error occurs during COMMIT.
- [ ] Use idempotency keys for write requests that may be resent.
- [ ] Evict broken connections from pools and acquire fresh connections.
- [ ] Enforce maximum retries, backoff, jitter, and deadlines.
- [ ] Inspect BatchUpdateException and update counts during batch runs.
- [ ] Maintain metrics and logs to spot recurring failures.

## References

- [Java SE — SQLException](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/SQLException.html)
- [Java SE — SQLState](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/package-summary.html)
- [MySQL Connector/J Developer Guide — Exception Handling](https://dev.mysql.com/doc/connector-j/en/connector-j-exceptions.html)
- [MySQL Reference Manual — Server Error Message Reference](https://dev.mysql.com/doc/mysql-errors/8.0/en/server-error-reference.html)
- [MySQL Reference Manual — Client Error Message Reference](https://dev.mysql.com/doc/mysql-errors/8.0/en/client-error-reference.html)
- [MySQL Reference Manual — InnoDB Error Handling](https://dev.mysql.com/doc/refman/8.0/en/innodb-error-handling.html)

## Conclusion

SQLState identifies the error group, vendor code pinpoints the specific MySQL error, and the cause chain plus failure timing reveal the actual root cause. Deadlock 1213 can usually be retried as a whole transaction; lock timeout 1205 requires an explicit rollback before retrying; communications failures require a fresh connection and outcome verification if the drop occurred during commit. Build a classifier driven by SQLState, error codes, and transaction context, paired with bounded retries, idempotency keys, and pool monitoring so applications recover safely.
