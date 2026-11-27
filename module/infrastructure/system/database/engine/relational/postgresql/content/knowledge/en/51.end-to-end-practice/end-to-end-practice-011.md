# Integrating JDBC, Connection Pools, and Transaction Error Handling

A Java application working with PostgreSQL must coordinate three tightly coupled layers: JDBC to send statements and receive results, a connection pool to reuse connections efficiently, and transactions to ensure data mutations stay consistent. Mishandling connection lifecycles or transaction errors can lead to pool exhaustion, long query waits, partially applied updates, or recurring deadlocks.

This lesson covers connecting Java to PostgreSQL with JDBC, configuring a connection pool, structuring transaction boundaries, handling `SQLSTATE` errors, implementing safe retries, and monitoring runtime behavior in production.

## 1. Java and PostgreSQL Integration Architecture

JDBC (Java Database Connectivity) is Java's standard API for relational databases. PostgreSQL ships its own JDBC driver, commonly known as pgJDBC. The application invokes JDBC APIs; the driver translates those calls into the PostgreSQL wire protocol, sends them to the server, and maps returned rows into Java types.

In server applications, place a connection pool between business code and the driver:

```text
Java service / repository
        |
        v
    DataSource
        |
        v
  Connection pool
        |
        v
 PostgreSQL JDBC driver
        |
        v
 PostgreSQL server
```

Each layer has a distinct role:

- **`DataSource`:** the JDBC interface that supplies connections. Application code depends on `DataSource` instead of manually opening raw connections per request.
- **Connection pool:** manages a pool of open physical connections to PostgreSQL. When code requests a connection, the pool lends an open connection; calling `close()` returns it to the pool for reuse.
- **JDBC driver:** implements the PostgreSQL network protocol, handling parameters, data types, result sets, and server errors.
- **`Connection`:** represents a single database session. Transactions, isolation levels, and several JDBC settings are bound to this connection.
- **`PreparedStatement`:** represents a parameterized SQL statement. Using parameters transmits values safely and lets the driver/server reuse appropriate plans.
- **`ResultSet`:** the query result cursor. Always close `ResultSet` and `Statement` once reading completes.

A connection actively serving one request must never be shared concurrently across multiple threads. Transactions and connection state are session-scoped; if two threads mutate state or run statements on the same connection simultaneously, outcomes become unpredictable.

## 2. Adding the PostgreSQL JDBC Driver and Pool to Your Application

In Maven, applications typically declare the PostgreSQL JDBC driver alongside a pooling library like HikariCP. Exact versions should be centrally governed via your project's dependency management.

```xml
<dependencies>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <version>YOUR_APPROVED_PGJDBC_VERSION</version>
    </dependency>

    <dependency>
        <groupId>com.zaxxer</groupId>
        <artifactId>HikariCP</artifactId>
        <version>YOUR_APPROVED_HIKARICP_VERSION</version>
    </dependency>
</dependencies>
```

In modern Java applications, JDBC drivers auto-register via the service provider mechanism. Calling `Class.forName` manually is usually unnecessary. Opening direct connections with `DriverManager` remains handy for tiny CLI scripts or tests, but server applications should rely on a long-lived managed `DataSource`.

A basic JDBC URL has the form:

```text
jdbc:postgresql://db-host:5432/orders
```

Where:

- `jdbc:postgresql` selects the PostgreSQL driver.
- `db-host` is the server hostname or IP address.
- `5432` is PostgreSQL's default port.
- `orders` is the database name.

Additional connection parameters can be passed in the URL or as properties on the `DataSource`. For example, `ApplicationName` identifies the service in `pg_stat_activity`. Credentials should be pulled from a secret manager or deployment-managed environment variables—never hardcode passwords in source code or repositories.

Example creating a `DataSource` with HikariCP:

```java
HikariConfig config = new HikariConfig();
config.setJdbcUrl(System.getenv("DB_JDBC_URL"));
config.setUsername(System.getenv("DB_USERNAME"));
config.setPassword(System.getenv("DB_PASSWORD"));
config.setPoolName("orders-pool");
config.setMaximumPoolSize(12);

config.addDataSourceProperty("ApplicationName", "orders-api");

HikariDataSource dataSource = new HikariDataSource(config);
```

Instantiate `DataSource` once for the application's lifetime and inject it into repositories or services. Never create a new pool per HTTP request or repository call. When the application shuts down, close the `DataSource` so the pool releases physical connections and background threads.

## 3. How Connection Pools Work

Opening a TCP socket, authenticating, and initializing a PostgreSQL backend session carries overhead. Opening and closing physical connections for every single query becomes prohibitively expensive under load. A pool maintains pre-established connections for requests to borrow sequentially.

Typical lifecycle:

1. Application calls `dataSource.getConnection()`.
2. The pool hands out an idle connection or waits until one is returned.
3. Application executes statements and transactions.
4. Application closes `ResultSet`, `Statement`, and `Connection`.
5. The pool reclaims the connection, validates it, and resets required JDBC state before lending it to the next request.

With a pooled `DataSource`, `Connection.close()` normally returns the connection to the pool rather than closing the underlying socket to PostgreSQL. Therefore, closing connections inside `finally` or `try-with-resources` remains mandatory; otherwise, the pool leaks available connections until exhausted.

### 3.1 Why You Should Not Arbitrarily Increase Pool Size

Each PostgreSQL connection consumes server resources: memory, a backend process, and scheduling overhead. If multiple application instances each spin up oversized pools, total connections can hit server limits or overwhelm the database with excessive concurrent queries.

Calculate your total connection budget:

```text
Total app connections
  = app instance count × maximumPoolSize per instance

Projected total connections
  = app connections
  + background jobs
  + admin tools
  + other services
```

This total must stay comfortably within `max_connections`, leaving headroom for administrative work and maintenance connections. Also account for external proxies or poolers if deployed.

A larger pool does not automatically yield higher throughput. Once PostgreSQL saturates CPU, I/O, or locks, adding concurrent queries only lengthens queues and worsens tail latency. Start with a reasoned pool size, measure pool wait times and database load, and tune empirically.

### 3.2 Common HikariCP Configuration

Configuration example:

```java
HikariConfig config = new HikariConfig();

config.setJdbcUrl(System.getenv("DB_JDBC_URL"));
config.setUsername(System.getenv("DB_USERNAME"));
config.setPassword(System.getenv("DB_PASSWORD"));

config.setPoolName("orders-api-pool");
config.setMaximumPoolSize(12);
config.setMinimumIdle(2);

config.setConnectionTimeout(3000);
config.setValidationTimeout(1000);

config.setMaxLifetime(1500000);
config.setIdleTimeout(300000);

config.setLeakDetectionThreshold(20000);

config.addDataSourceProperty("ApplicationName", "orders-api");

HikariDataSource dataSource = new HikariDataSource(config);
```

Key properties:

| Property | Meaning | How to Choose |
|---|---|---|
| `maximumPoolSize` | Maximum connections in the pool | Balance against total connection budget and PostgreSQL capacity |
| `minimumIdle` | Minimum idle connections the pool tries to retain | Set based on baseline traffic and connection-creation cost |
| `connectionTimeout` | Max wait time to borrow a connection from the pool | Align with request SLA; this is pool wait timeout, not query timeout |
| `validationTimeout` | Max time allowed for connection liveness check | Must be shorter than `connectionTimeout` |
| `maxLifetime` | Maximum lifetime of a connection in the pool | Set shorter than any proxy, firewall, or network idle/lifetime cap |
| `idleTimeout` | Time before idle connections may be retired | Applies when pool shrinks below `maximumPoolSize` |
| `leakDetectionThreshold` | Threshold to log warnings when a connection stays checked out too long | Helps spot missing `close()` calls; emits warnings without forcibly closing |

HikariCP uses JDBC4 `Connection.isValid()` by default to validate connections. Avoid configuring a manual test query when the driver supports `isValid()` properly. Only configure a validation query for explicit compatibility needs after understanding its overhead.

`maxLifetime` does not abruptly terminate an in-use connection. The pool retires expired connections after they are returned. Setting `maxLifetime` slightly below proxy, load-balancer, or firewall timeouts reduces the chance of handing an application a connection silently severed by infrastructure.

`leakDetectionThreshold` is valuable for tracking leaks, though setting it too low triggers false alarms on legitimate long-running transactions. Inspect the logged stack trace and checkout duration before concluding a leak exists.

### 3.3 Distinguishing Pool Timeouts from Database Timeouts

Each timeout governs a distinct layer:

- HikariCP `connectionTimeout` bounds how long the app waits to borrow a connection from the pool.
- pgJDBC `connectTimeout` bounds TCP connection establishment to PostgreSQL.
- pgJDBC `socketTimeout` bounds socket read waits; once triggered, the connection may be unusable.
- `Statement.setQueryTimeout()` caps statement execution time via the JDBC driver.
- PostgreSQL `lock_timeout` caps how long a statement waits to acquire a lock.
- PostgreSQL `statement_timeout` caps total statement execution time on the server.

Do not set every timeout to the exact same value. Pick each threshold based on the responsible layer and recovery behavior. In particular, `socketTimeout` is not a substitute for `statement_timeout`: a socket timeout drops the connection client-side while leaving the application uncertain whether the server finished committing.

## 4. Borrowing and Returning Connections Properly

Use `try-with-resources` to ensure JDBC resources close even when exceptions occur:

```java
String sql = """
    SELECT id, customer_name, total
    FROM orders
    WHERE id = ?
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setLong(1, orderId);

    try (ResultSet resultSet = statement.executeQuery()) {
        if (resultSet.next()) {
            long id = resultSet.getLong("id");
            String customerName = resultSet.getString("customer_name");
            BigDecimal total = resultSet.getBigDecimal("total");

            // Map rows to application objects.
        }
    }
}
```

When the `try` block exits, `ResultSet`, `PreparedStatement`, and `Connection` close in reverse order. With a pooled `DataSource`, closing the connection returns it to the pool.

Core practices to uphold:

- Borrow connections strictly for the duration of the unit of work and close immediately when done.
- Never store `Connection`, `Statement`, or `ResultSet` in `static` fields or shared service singletons.
- Never pass a single `Connection` across parallel threads.
- Never keep a `ResultSet` open across HTTP calls or user pauses.
- Never return a connection to the pool with an open or aborted transaction.
- Explicitly close `ResultSet` and `Statement`, even though `Connection` will also close afterward.

When a request executes multiple statements that belong to the same transaction, borrow one connection and pass it across the participating repository methods. Do not let each repository borrow its own connection if operations must commit or roll back atomically.

## 5. Managing Transactions in JDBC

By default, JDBC connections start in auto-commit mode. With `autoCommit = true`, every single statement runs as its own independent transaction and commits immediately. This suits standalone reads or single statements, but fails when a business operation requires multiple updates to succeed or fail together.

To manage transactions explicitly:

1. Obtain a connection.
2. Call `setAutoCommit(false)`.
3. Execute all statements belonging to the business unit of work.
4. Call `commit()` when all steps succeed.
5. Call `rollback()` on any error.
6. Close the connection to return it to the pool.

Example transferring funds between two accounts:

```java
public void transfer(
        DataSource dataSource,
        long fromAccountId,
        long toAccountId,
        BigDecimal amount
) throws SQLException {

    if (amount.signum() <= 0) {
        throw new IllegalArgumentException("Amount must be positive");
    }

    String lockSql = """
        SELECT id, balance
        FROM accounts
        WHERE id IN (?, ?)
        ORDER BY id
        FOR UPDATE
        """;

    String debitSql = """
        UPDATE accounts
        SET balance = balance - ?
        WHERE id = ? AND balance >= ?
        """;

    String creditSql = """
        UPDATE accounts
        SET balance = balance + ?
        WHERE id = ?
        """;

    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);

        try {
            Map<Long, BigDecimal> balances = new HashMap<>();

            try (PreparedStatement lockStatement =
                         connection.prepareStatement(lockSql)) {
                lockStatement.setLong(1, fromAccountId);
                lockStatement.setLong(2, toAccountId);

                try (ResultSet resultSet = lockStatement.executeQuery()) {
                    while (resultSet.next()) {
                        balances.put(
                            resultSet.getLong("id"),
                            resultSet.getBigDecimal("balance")
                        );
                    }
                }
            }

            if (!balances.containsKey(fromAccountId)
                    || !balances.containsKey(toAccountId)) {
                throw new SQLException("Account not found");
            }

            try (PreparedStatement debit =
                         connection.prepareStatement(debitSql)) {
                debit.setBigDecimal(1, amount);
                debit.setLong(2, fromAccountId);
                debit.setBigDecimal(3, amount);

                if (debit.executeUpdate() != 1) {
                    throw new SQLException("Insufficient balance");
                }
            }

            try (PreparedStatement credit =
                         connection.prepareStatement(creditSql)) {
                credit.setBigDecimal(1, amount);
                credit.setLong(2, toAccountId);

                if (credit.executeUpdate() != 1) {
                    throw new SQLException("Destination account not found");
                }
            }

            connection.commit();
        } catch (SQLException | RuntimeException | Error failure) {
            try {
                connection.rollback();
            } catch (SQLException rollbackFailure) {
                failure.addSuppressed(rollbackFailure);
            }
            throw failure;
        }
    }
}
```

Principles illustrated above:

- Both rows are locked inside a single transaction.
- Rows are locked in a consistent `id` order to reduce deadlocks under concurrent transfers.
- The source debit includes `balance >= amount`, preventing negative balances under concurrency.
- Updated row counts are verified to catch missing accounts or insufficient funds.
- If any step fails, the entire transaction rolls back.

This snippet assumes `fromAccountId` and `toAccountId` are distinct accounts. Production code should validate that precondition before opening a transaction, and enforce currencies, transfer limits, and accounting rules per business requirements.

With pools like HikariCP, closing a connection resets supported JDBC states to defaults. Nevertheless, application code must explicitly call `commit()` or `rollback()` before closing. Never rely on connection-close cleanup as a substitute for explicit transaction termination.

### 5.1 Do Not Hold Transactions Open While Calling External Services

Suppose a workflow updates an order and then calls an HTTP payment gateway while keeping the database transaction open. If the payment API takes 10 seconds, the connection and all held locks remain pinned for the entire 10 seconds.

Split the workflow into crisp boundaries:

1. Open a short transaction, persist the order in `PENDING` state and an outbound message record.
2. Commit the transaction.
3. A worker reads from the outbox or queue and invokes the payment service.
4. Open a fresh transaction to record the payment outcome.
5. Use business keys or idempotency keys so worker retries remain safe.

The outbox pattern writes business state and outbound events inside one atomic transaction. Workers dispatch events post-commit without pinning database connections during network I/O.

## 6. Transaction Error Handling and `SQLException`

JDBC surfaces database errors via `SQLException` and its subclasses. When catching an error, do not read only the message text. Inspect `SQLSTATE`, vendor error codes, chained exceptions, and transaction state.

Useful methods:

- `getSQLState()`: standard or driver-provided `SQLSTATE` code.
- `getErrorCode()`: database-specific error code.
- `getNextException()`: subsequent exception in a chain, especially relevant for batches.
- `getCause()`: underlying cause if wrapped.
- `getMessage()`: descriptive text helpful for internal logs—never expose verbatim to end users.

Example logging error details:

```java
catch (SQLException exception) {
    logger.error(
        "Database operation failed: sqlState={}, vendorCode={}",
        exception.getSQLState(),
        exception.getErrorCode(),
        exception
    );
    throw exception;
}
```

Never log passwords, tokens, personal data, or raw sensitive payloads. Handle query text and bound parameters according to your system's data protection policy.

### 6.1 Common PostgreSQL `SQLSTATE` Codes

| `SQLSTATE` | Error Name | Common Scenario | Handling |
|---|---|---|---|
| `23505` | `unique_violation` | Duplicate unique key | Check business rules; return conflict or use upsert if appropriate |
| `23503` | `foreign_key_violation` | Referencing missing row or deleting referenced parent | Fix operation ordering and relationship integrity |
| `23502` | `not_null_violation` | Inserting `NULL` into mandatory column | Fix input validation or defaults |
| `23514` | `check_violation` | Value violates a `CHECK` constraint | Verify business preconditions and input values |
| `40001` | `serialization_failure` | Transaction cannot complete at requested isolation level | Roll back and consider retrying full transaction |
| `40P01` | `deadlock_detected` | Two or more transactions formed a lock cycle | Roll back, retry with cap, and fix lock ordering |
| `55P03` | `lock_not_available` | Lock unavailable under `NOWAIT` or lock timeout | Review wait policy, timeouts, and contention |
| `57014` | `query_canceled` | Statement cancelled via `statement_timeout` or external cancel | Identify cancellation source and tune query or timeout |
| `25P02` | `in_failed_sql_transaction` | App sent another statement after transaction entered failed state | Roll back transaction or roll back to savepoint |
| `08003` | `connection_does_not_exist` | Connection no longer exists | Discard broken connection and obtain a new one |
| `08006` | `connection_failure` | Connection dropped during communication | Investigate network/server; determine whether commit succeeded |

`SQLSTATE` codes consist of a two-character class followed by a three-character condition. For example, class `23` covers integrity constraint violations; class `40` covers transaction rollback errors; class `08` covers connection exceptions.

Never classify errors solely by parsing message text, which varies across PostgreSQL versions and locales. Branch on `SQLSTATE`, and use messages and logs for diagnostics.

### 6.2 Aborted Transaction State in PostgreSQL

Inside an explicit transaction, if a statement fails—for example, violating a unique constraint—PostgreSQL marks the transaction as aborted. All subsequent statements fail with `25P02` until the transaction rolls back.

Example:

```sql
BEGIN;

INSERT INTO customers(id, email)
VALUES (10, 'a@example.com');

-- Assume email already exists and INSERT raises 23505.

SELECT count(*) FROM customers;
-- Error 25P02: transaction is now in failed state.

ROLLBACK;
```

The application must roll back before starting a new transaction. Catching the exception in Java and continuing to issue SQL on the same aborted transaction is invalid.

### 6.3 Using Savepoints for Localized Error Recovery

Savepoints let you roll back part of a transaction. This helps when an optional step may fail while business rules permit the remainder of the transaction to proceed.

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        insertOrderHeader(connection);

        Savepoint beforeOptionalItem = connection.setSavepoint();

        try {
            insertOptionalItem(connection);
            connection.releaseSavepoint(beforeOptionalItem);
        } catch (SQLException itemFailure) {
            if ("23505".equals(itemFailure.getSQLState())) {
                connection.rollback(beforeOptionalItem);
                connection.releaseSavepoint(beforeOptionalItem);
                logger.info("Optional item already exists; skipped");
            } else {
                throw itemFailure;
            }
        }

        connection.commit();
    } catch (SQLException | RuntimeException | Error failure) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
        throw failure;
    }
}
```

Rolling back to a savepoint discards changes made after the savepoint and restores the transaction to a healthy state. Only swallow `SQLSTATE` codes explicitly allowed by business logic; never catch and ignore arbitrary `SQLException`s that might indicate dropped connections, schema errors, or severe failures.

Some constraints may be declared `DEFERRABLE` and checked only at commit time. Consequently, every statement may succeed individually while `commit()` still fails. Always wrap `commit()` inside the transaction's error-handling block.

## 7. Isolation Levels and Consistency

Isolation levels govern how a transaction observes changes made by concurrent transactions. JDBC exposes constants such as `TRANSACTION_READ_COMMITTED`, `TRANSACTION_REPEATABLE_READ`, and `TRANSACTION_SERIALIZABLE`.

PostgreSQL defaults to `READ COMMITTED`. Each statement receives a fresh snapshot as of when that statement begins. Thus, two `SELECT` statements inside the same transaction can observe rows committed in between them.

| Isolation Level | General Behavior in PostgreSQL | Notes |
|---|---|---|
| `READ COMMITTED` | Each statement sees the latest committed snapshot at statement start | Default; fits most CRUD workloads |
| `REPEATABLE READ` | All statements in the transaction share one snapshot | Can raise serialization failures on concurrent update conflicts |
| `SERIALIZABLE` | PostgreSQL tracks dependencies to guarantee serial-equivalent execution | May abort transactions with `SQLSTATE` `40001`; app must retry |

Set isolation level before executing statements in a transaction:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setTransactionIsolation(
        Connection.TRANSACTION_SERIALIZABLE
    );
    connection.setAutoCommit(false);

    try {
        performBusinessOperation(connection);
        connection.commit();
    } catch (SQLException | RuntimeException | Error failure) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
        throw failure;
    }
}
```

Never bump the isolation level just to "feel safer" without understanding your workload. `SERIALIZABLE` can raise retry rates; the application must implement full-transaction retries and ensure idempotent execution. For many workflows, explicit locking or conditional updates are simpler and faster.

Isolation level is a connection/transaction attribute. With pools, ensure it is consistently reset or managed so settings never leak to subsequent requests.

## 8. `PreparedStatement`, Data Types, and Query Safety

Use `PreparedStatement` to bind values:

```java
String sql = """
    SELECT id, status
    FROM orders
    WHERE customer_id = ?
      AND created_at >= ?
    ORDER BY created_at DESC
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setLong(1, customerId);
    statement.setTimestamp(2, Timestamp.from(startInstant));

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            // Read each result row.
        }
    }
}
```

Never concatenate user input directly into SQL strings. The following is vulnerable to SQL injection:

```java
String sql = "SELECT * FROM users WHERE email = '" + email + "'";
```

Use placeholders and typed setters. `?` placeholders bind values only; they cannot substitute table names, column names, SQL keywords, or sort directions. When dynamic identifiers are needed, pick strictly from an explicit allowlist defined in application code.

Map Java types cleanly to PostgreSQL types:

| Java Type | Common PostgreSQL Type | Notes |
|---|---|---|
| `long` / `Long` | `bigint` | Use `setLong()` and `getLong()` |
| `int` / `Integer` | `integer` | Use `setInt()` and `getInt()` |
| `BigDecimal` | `numeric` / `decimal` | Avoid `double` for currency |
| `String` | `text` / `varchar` | Use `setString()` |
| `boolean` | `boolean` | Handle `NULL` explicitly for nullable columns |
| `LocalDate` | `date` | Use `java.time` JDBC support or explicit conversion |
| `LocalDateTime` | `timestamp without time zone` | Carries no time-zone offset |
| `OffsetDateTime` | `timestamp with time zone` (`timestamptz`) | PostgreSQL stores instants in UTC; original offset is not preserved separately |
| `UUID` | `uuid` | pgJDBC maps `UUID` natively |
| `byte[]` | `bytea` | Used for binary payloads |

Standardize timestamp semantics across your system. `timestamp without time zone` represents an unzoned local date-time; `timestamptz` represents a specific instant normalized internally by PostgreSQL. Never mix the two types without explicit conversion rules.

For SQL `NULL` values, primitive getters such as `getLong()` return `0` when the column is `NULL`. Call `wasNull()` immediately after the getter or use boxed object types (`getObject(..., Long.class)`) to distinguish `NULL` from zero.

## 9. Batching and Streaming Large Datasets

### 9.1 Batch Inserts and Updates

When writing many rows using the same SQL template, batching reduces network round-trips between the application and database:

```java
String sql = """
    INSERT INTO inventory(product_id, quantity)
    VALUES (?, ?)
    ON CONFLICT (product_id)
    DO UPDATE SET quantity = EXCLUDED.quantity
    """;

try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        for (InventoryItem item : items) {
            statement.setLong(1, item.productId());
            statement.setInt(2, item.quantity());
            statement.addBatch();
        }

        int[] counts = statement.executeBatch();
        connection.commit();
    } catch (SQLException | RuntimeException | Error failure) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
        throw failure;
    }
}
```

`executeBatch()` returns update counts or special codes like `SUCCESS_NO_INFO`; drivers may throw `BatchUpdateException` with partial update counts. If the batch forms an atomic transaction, roll back on error and inspect the chained exceptions to identify which statement failed.

Overly huge batches increase memory consumption, transaction duration, and lock hold times. Size batches to fit your dataset, network, and operational limits.

### 9.2 Streaming Large Reads via Fetch Size

By default, pgJDBC buffers the entire query result into client memory. Reading hundreds of thousands or millions of rows this way can exhaust heap memory.

Instruct the driver to stream rows in chunks using fetch size:

```java
String sql = "SELECT id, payload FROM event_log ORDER BY id";

try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setFetchSize(500);

        try (ResultSet resultSet = statement.executeQuery()) {
            while (resultSet.next()) {
                processEvent(resultSet.getLong("id"),
                             resultSet.getString("payload"));
            }
        }

        connection.commit();
    } catch (SQLException | RuntimeException | Error failure) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
        throw failure;
    }
}
```

pgJDBC's cursor-based fetching requires an explicit transaction—specifically `autoCommit = false` before executing the query. That means the transaction and connection stay open for the entire iteration. Avoid calling external services or processing rows slowly while the cursor remains open. For long-running jobs, prefer keyset pagination so each page runs in its own short transaction.

## 10. Safe Retries on Concurrency Errors

Certain PostgreSQL errors are transient concurrency failures:

- `40P01`: deadlock detected.
- `40001`: serialization failure.

You can retry these errors if you follow strict rules:

1. Roll back the current transaction.
2. Start a fresh transaction on a healthy connection.
3. Replay the entire business unit of work from the start.
4. Cap maximum retry attempts.
5. Apply exponential backoff with jitter so clients do not retry in lockstep.
6. Log `SQLSTATE`, attempt count, and business correlation ID for observability.

Example retryable-error predicate:

```java
private boolean isRetryableTransactionError(SQLException exception) {
    String sqlState = exception.getSQLState();

    return "40P01".equals(sqlState)
        || "40001".equals(sqlState);
}
```

Each retry attempt must run inside a brand-new transaction. Never retry directly inside an aborted transaction.

```java
public <T> T executeWithRetry(
        int maxAttempts,
        SqlWork<T> work
) throws SQLException {

    SQLException lastFailure = null;

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                T result = work.execute(connection);
                connection.commit();
                return result;
            } catch (SQLException | RuntimeException | Error failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }

                if (failure instanceof SQLException sqlException
                        && isRetryableTransactionError(sqlException)) {
                    lastFailure = sqlException;
                } else {
                    throw failure;
                }
            }
        }

        if (attempt < maxAttempts) {
            sleepWithBackoffAndJitter(attempt);
        }
    }

    throw lastFailure;
}
```

This is an illustrative skeleton; `SqlWork`, `sleepWithBackoffAndJitter`, and thread-interruption handling must match your application architecture. Production code must ensure retries respect request deadlines and preserve thread interrupt flags.

**Never retry arbitrary `SQLException`s.** Unique constraint violations, type errors, missing tables, or permission denials do not fix themselves after a backoff sleep. Retry only explicitly classified transient errors.

### 10.1 Risk of Dropping the Connection During Commit

A dangerous edge case occurs when the application sends `COMMIT` and loses the network connection before receiving acknowledgment. The client cannot tell whether the server committed or rolled back. Re-running the entire operation blindly risks duplicate writes or double-executing business effects.

Blind retries cannot solve this. Design operations with an idempotency key or unique request identifier persisted inside the same transaction as the business state. When a client retries, the server checks that key and returns the recorded outcome instead of re-applying changes.

For workflows emitting events, a transactional outbox writes the event in the same transaction. Delivery workers can safely retry dispatching, while downstream consumers remain idempotent to handle duplicates.

## 11. Managing Session State with Connection Pools

Connection pools reuse the same PostgreSQL backend session across many requests. Any unreset session state leaks into subsequent requests.

Settings to watch carefully:

- `autoCommit`
- Transaction isolation level
- Read-only mode
- Schema/catalog if altered by application code
- Network timeout
- Session variables or PostgreSQL `SET` commands
- Role, `search_path`, and other session parameters

HikariCP tracks and restores standard JDBC connection properties upon return. However, raw SQL statements like `SET search_path`, `SET statement_timeout`, or `SET application_name` mutate server-side session state in ways a pool may not fully track or revert.

When a setting applies only to a single transaction, prefer `SET LOCAL` after the transaction starts:

```sql
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '15s';

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 42;

COMMIT;
```

`SET LOCAL` reverts automatically when the transaction ends. If you must use session-level `SET`, enforce explicit reset logic before returning connections to the pool, or configure defaults at the role/database level so every session inherits the same baseline.

Never let a request mutate `search_path` or `ROLE` and return the connection to the pool unrestored. That creates both cross-request isolation bugs and security vulnerabilities.

## 12. Monitoring Pools and Database State in Production

When an application slows down, inspect both the Java connection pool and PostgreSQL backend sessions. Looking at only one side leads to false conclusions.

### 12.1 Pool Metrics

With HikariCP, monitor equivalent metrics for:

- **Active connections:** connections currently checked out.
- **Idle connections:** connections ready to be borrowed.
- **Total connections:** total open connections in the pool.
- **Threads awaiting connection:** threads currently blocked waiting for the pool.
- **Acquisition time:** latency between calling `getConnection()` and receiving a connection.
- **Usage time:** duration connections remain checked out before returning.
- **Timeout count:** requests failing to acquire a connection within `connectionTimeout`.

If active connections stay pegged at maximum, idle hits zero, and awaiting threads climb, the pool is either undersized or connections are held too long. Hunt down long-held connections, unclosed transactions, slow queries, or slow `ResultSet` processing.

If the pool still has idle connections while requests stall, look elsewhere: slow SQL, network latency, application thread pools, or downstream services.

### 12.2 Identifying Connections in PostgreSQL

Set `ApplicationName` in pgJDBC configuration to track sessions cleanly:

```sql
SELECT
    pid,
    application_name,
    usename,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query_start,
    left(query, 500) AS query
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
```

You can filter by application:

```sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    clock_timestamp() - xact_start AS transaction_age,
    left(query, 500) AS query
FROM pg_stat_activity
WHERE application_name = 'orders-api'
ORDER BY xact_start NULLS LAST;
```

Key session states to watch:

- `active`: backend is currently executing a statement; inspect `wait_event` to see if it is blocked.
- `idle`: connection is free with no open transaction.
- `idle in transaction`: transaction remains open while the backend sits idle; can hold locks and pin old snapshots.
- `idle in transaction (aborted)`: transaction failed and has not rolled back yet.

A healthy pool naturally keeps idle sessions open in PostgreSQL; `idle` sessions do not indicate a leak. Cross-reference session counts against pool settings and pool metrics.

### 12.3 Detecting Connection Leaks

Typical symptoms:

- Active connection count climbs steadily without dropping.
- Pool exhausts even though request throughput did not spike proportionally.
- Threads waiting for connections climb.
- HikariCP logs long-held connection warnings.
- Logged stack traces point to code paths missing resource cleanup.

Common root causes include missing `try-with-resources`, exception paths skipping `close()`, `ResultSet` stored in long-lived objects, or tasks holding connections open during external service calls.

Leak detection only pinpoints where a connection was borrowed; it does not automatically close leaked connections. Once you trace the culprit, fix resource lifecycle management and verify via post-deploy metrics.

## 13. Integration Testing Transactions and Pools

Testing against a real PostgreSQL instance is essential because transaction semantics, locking, `SQLSTATE` codes, and data types differ from embedded mock databases like H2.

Scenarios to test:

1. **Successful commit:** changes become visible from another connection after commit.
2. **Rollback:** when a second statement fails, changes from the first statement disappear.
3. **Constraint violation:** application receives expected `SQLSTATE` and rolls back cleanly.
4. **Aborted transaction:** after an error, subsequent statements fail until full rollback or savepoint rollback.
5. **Deadlock:** two transactions lock two rows in opposite orders; application catches `40P01` and retries the full unit of work.
6. **Serialization failure:** transactions under strict isolation receive `40001` and retry with a bounded cap.
7. **Pool reuse:** `autoCommit`, isolation level, and session settings do not leak across pooled requests.
8. **Connection leaks:** both success and failure paths return connections to the pool.
9. **Network failure:** application handles dropped connections and uncertain commits via idempotency.
10. **Shutdown:** `DataSource` closes cleanly and releases pool resources on app shutdown.

Concurrency tests should coordinate execution order with latches, barriers, or synchronization primitives. Never rely on `Thread.sleep()` to reproduce deadlocks reliably.

## 14. Common Integration Pitfalls

| Symptom | Possible Cause | Investigation Direction |
|---|---|---|
| `Connection is not available, request timed out` | Pool exhausted, connections held too long, or DB refusing connections | Inspect active/idle/pending metrics, acquisition time, and `pg_stat_activity` |
| `current transaction is aborted` | Prior statement failed without rollback | Find the initial `SQLSTATE` error; roll back or use savepoints properly |
| `duplicate key value violates unique constraint` | Concurrent requests inserted the same unique key or duplicate input | Check `SQLSTATE` `23505`; use upsert or handle conflict per business rules |
| `deadlock detected` | Transactions locked resources in conflicting orders | Inspect deadlock logs, standardize lock ordering, and retry whole transaction |
| `canceling statement due to statement timeout` | Statement exceeded `statement_timeout` | Check query plan, load, lock waits, and timeout threshold |
| `Connection reset` or socket timeout | Network drop, proxy timeout, server restart, or driver timeout | Determine whether connection is reusable; acquire fresh connection and handle commit uncertainty |
| Many `idle in transaction` sessions | App forgot to commit/rollback or holds transaction during external work | Locate code opening transactions and configure `idle_in_transaction_session_timeout` |
| Slow queries despite idle pool capacity | Slow SQL, missing index, locks, or server bottleneck | Check `pg_stat_activity`, wait events, `EXPLAIN`, and PostgreSQL metrics |

Do not treat every error by blindly enlarging the pool or raising timeouts. Identify which layer caused the failure before tuning.

## 15. Step-by-Step Workflow for a Safe JDBC Flow

A practical checklist for Java services:

**Step 1 — Initialize `DataSource`.** Create one shared application-wide pool. Load URL, username, and password from secure configuration; set `ApplicationName`.

**Step 2 — Define transaction boundaries.** Decide which mutations must commit together. Borrow one connection for the entire business unit of work.

**Step 3 — Use `PreparedStatement`.** Bind values via placeholders, and close `Statement` and `ResultSet` with `try-with-resources`.

**Step 4 — Terminate transactions explicitly.** Commit on success, roll back on failure, and never return an open transaction to the pool.

**Step 5 — Classify errors.** Use `SQLSTATE` to separate data errors, concurrency conflicts, connection drops, and timeouts. Never retry non-transient errors.

**Step 6 — Retry with bounds.** Retry only transient transaction errors such as deadlocks or serialization failures; run each attempt in a fresh transaction and guarantee idempotency.

**Step 7 — Measure.** Track pool metrics, acquisition latency, checkout duration, transaction age, and PostgreSQL wait events.

**Step 8 — Test failures.** Test rollbacks, deadlocks, constraints, connection drops, pool reuse, and shutdown against a real PostgreSQL instance.

## 16. Key Takeaways

- Use `DataSource` and a shared connection pool in server applications; never create pools per request.
- Always close `Connection`, `Statement`, and `ResultSet` via `try-with-resources`. On pooled connections, `close()` returns the connection to the pool.
- A transaction requires a single connection throughout; explicitly `commit()` or `rollback()` before returning it.
- PostgreSQL puts a transaction into an aborted state after any failed statement; roll back or roll back to a savepoint before continuing.
- Use `SQLSTATE` to classify errors. `40P01` and `40001` can be retried across the whole transaction with bounded attempts.
- Dropping a connection during `COMMIT` leaves the outcome uncertain; use idempotency keys and reconciliation to prevent duplicate processing.
- Size pools based on the total system connection budget and measured telemetry.
- Distinguish pool wait timeouts, network connect timeouts, statement timeouts, and lock timeouts.
- Monitor pool metrics alongside `pg_stat_activity` to catch connection leaks, long transactions, and lock waits.
- Run integration tests against real PostgreSQL to verify transaction, locking, and driver behavior.
