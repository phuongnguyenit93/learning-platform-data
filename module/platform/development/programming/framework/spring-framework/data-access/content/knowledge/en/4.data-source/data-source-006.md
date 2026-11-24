# Checking Connections and Handling Broken Connections

## 1. The Problem: A Connection That Once Worked Can Still Die

In a Spring application, `DataSource` provides JDBC connections to the database. A `Connection` may work fine when created, and later break due to a DB restart, a firewall or load balancer closing idle connections, network interruptions, timeouts, or server-side failures. As a result, queries fail, transactions do not complete, and requests return errors.

Three separate questions need answers:

1. **Before use:** how do we reduce the chance of borrowing a connection that is already dead?
2. **During use:** when SQL or `COMMIT` hits a connection error, how should resources and transactions be handled?
3. **After an incident:** how do new requests obtain a healthy connection, and when can an operation be retried without causing side effects?

Think of a connection like a phone call. Hearing a tone at this moment does not guarantee the line will still be open one second later. Likewise, **a successful check only confirms a single instant; every SQL statement must still have an error-handling path**.

Examples in this lesson use JDBC 4+, Java 17, Spring JDBC, and HikariCP. HikariCP is one kind of connection pool; its specific properties do not automatically apply to every `DataSource` implementation. With Spring Boot, HikariCP is typically auto-configured when the appropriate library is present, but always verify the actual `DataSource` type in use.

## 2. Understanding the Lifecycle of `DataSource` and Connection Pool

`DataSource` is the `javax.sql.DataSource` contract, typically invoked by the application or Spring via `getConnection()`. `Connection` is the `java.sql.Connection` contract used to prepare and execute SQL, control transactions, and release resources.

With HikariCP, distinguish:

- **Physical connection:** the actual session with the DB server, normally over a socket and driver.
- **Connection lease (handle):** the `Connection` object the application receives from the pool, usually a lifecycle-managing proxy.
- **Idle connection:** a physical connection returned to the pool that remains available for reuse.
- **Broken connection:** a connection the pool/driver determines is no longer usable, or where an actual operation fails due to a dropped session.

```text
Application / JdbcTemplate
         |
         | acquire connection
         v
DataSource / connection pool
         |               \
         |                \ broken connection via check or JDBC exception
         |                 -> evict/replace when possible
         v
Borrowed Connection
         |
         v
SQL / COMMIT / ROLLBACK
         |
         v
close() -> return lease to pool
```

Calling `connection.close()` on a connection borrowed from HikariCP usually **returns the connection to the pool**, rather than physically closing the socket on every call. The pool may decide to evict a physical connection that is broken or expired. Conversely, holding a `Connection` in a `static` field, cache, singleton, or sharing it across requests breaks how the pool controls leases and makes bugs hard to diagnose.

Spring's `DriverManagerDataSource` creates a new JDBC connection every time one is requested and **provides no reusable pool**. `SingleConnectionDataSource` intentionally uses one continuous connection, mainly suited for testing, not a pooling mechanism for multithreaded applications. Therefore, pool-based connection validation details apply only when an actual pool is in use.

## 3. Distinguishing Three Commonly Conflated Checks

| Mechanism | What It Checks | What It Does Not Guarantee |
| --- | --- | --- |
| `Connection.isClosed()` | Whether the connection object has been closed according to driver-known state | `false` does not prove the network and DB are still working |
| `Connection.isValid(int timeout)` | Driver verifies liveness via a query or reliable JDBC-compliant mechanism | Does not guarantee the next statement will succeed |
| Test query, e.g. `SELECT 1` | Whether a simple SQL statement can execute and return a result | Does not guarantee business queries, permissions, or transactions will succeed |

### 3.1. Why Is `isClosed() == false` Not Enough?

A socket can be silently cut by network equipment while idle. Because the driver has not performed new I/O yet, it may not have detected the problem. `isClosed()` can still return `false` while the very next SQL statement throws `SQLException`. Do not use `isClosed()` as a network "ping".

### 3.2. How Does `Connection.isValid(timeout)` Work?

JDBC specifies that the driver must use a query or genuine verification mechanism. The `timeout` for `isValid` is in **seconds**:

- `connection.isValid(2)`: asks the driver to limit verification to two seconds.
- Returns `true`: the connection is currently valid according to the driver's check.
- Returns `false`: invalid or verification did not complete before the limit.
- May throw `SQLException` in error cases; `timeout < 0` is an invalid argument.
- Value `0` means no time limit on verification; should not be used by default in health checks needing a bounded wait.

A check can still succeed and the connection break right before `UPDATE`; this is the gap between check and use (*time-of-check/time-of-use*). Therefore, always handle errors on the actual statement too.

### 3.3. Test Query `SELECT 1`

With PostgreSQL, MySQL, and H2, `SELECT 1` is typically a lightweight test query. Not every DBMS uses the same syntax; check your database type. A test query is still an extra round trip to the DB, so do not invoke it manually before every SQL statement in the application.

If the driver supports JDBC 4 `Connection.isValid()`, HikariCP recommends normally **leaving `connectionTestQuery` unconfigured**. Only consider a test query when the driver lacks support or driver-based verification has a verified issue. Layering multiple pings at once does not eliminate mid-operation disconnects.

### 3.4. Spring Example: Checking Connectivity with `DataSource`

This is an example class **inside a Spring application with a `DataSource` bean and `spring-context`**, not a standalone program needing only `javac`:

```java
import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

import org.springframework.stereotype.Component;

@Component
public final class JdbcConnectivityProbe {
    private final DataSource dataSource;

    public JdbcConnectivityProbe(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean available() {
        try (Connection connection = dataSource.getConnection()) {
            return connection.isValid(2); // 2 SECONDS
        } catch (SQLException ex) {
            return false;
        }
    }
}
```

`try-with-resources` closes the `Connection` object even when an error occurs. If this is a pooled connection, it is usually returned to the pool; the pool decides whether the physical connection can be reused. The method also returns `false` if a connection cannot be borrowed because the pool is busy, so **do not interpret every false result as "the DB is dead"**.

This example is suitable for learning the API or performing a dedicated probe, not for embedding in every repository method. In Spring Boot with Actuator, prefer the built-in health indicator mechanism instead of repeatedly calling `available()` from controllers.

## 4. When Does Checking Actually Have Value?

There are four distinct moments:

1. **At pool or application startup:** detects wrong DB address, credentials, connection privileges, or TLS. Successful startup does not prove the DB will remain available forever.
2. **When borrowing a connection:** the pool can validate an idle connection and pick another if it detects a broken one. No pool can prevent a failure occurring right after issuing a connection.
3. **While a connection is idle or due for rotation:** the pool can ping, evict old connections, or create new ones per lifetime, idle time, and keepalive settings.
4. **During SQL execution and commit:** failures must be handled via exceptions and transaction rules; you cannot rely solely on an earlier ping.

In particular, a DB health check and pool connection validation are not the same as a business guarantee. `isValid()` can return true while a query still has bad SQL, missing privileges, deadlocks, or unexpected data.

## 5. Proper HikariCP Configuration

Each timeout addresses a different stage. The following properties all belong to **HikariCP**, and time units in the configuration below are in **milliseconds**, unless individual method documentation states otherwise.

| Property | Role | Notes |
| --- | --- | --- |
| `connectionTimeout` | Maximum time the application waits to borrow a connection from the pool | Not an SQL timeout; expiration may be due to pool saturation or inability to create connections |
| `validationTimeout` | Maximum time the pool spends validating connection liveness | Must be smaller than `connectionTimeout` |
| `maxLifetime` | Maximum lifetime of a connection in the pool | Currently borrowed connections are not forcibly closed solely for hitting this mark; should be lower than infra/DB limits |
| `keepaliveTime` | Interval at which the pool attempts to ping idle connections to prevent inactivity disconnects | Applies only to idle connections; must be smaller than `maxLifetime` |
| `idleTimeout` | Duration after which idle connections may be retired when the pool holds more than the minimum | Does not necessarily evict all connections after this exact duration |
| `maximumPoolSize` | Limit on how many connections the pool can hold | Too low causes queuing; too high can overload the DB |
| `connectionTestQuery` | Liveness SQL replacing JDBC `isValid()` | Usually left blank with full JDBC 4 drivers |
| `leakDetectionThreshold` | Logs a warning when a connection is held beyond the threshold | Diagnostic tool; does not safely reclaim connections or fix the DB |

An example `application.yml` for a Spring Boot application using HikariCP (**illustrative** values, must be tuned to DB, infrastructure, load, and operational requirements):

```yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      pool-name: app-db
      maximum-pool-size: 10
      connection-timeout: 30000
      validation-timeout: 3000
      max-lifetime: 1500000
      keepalive-time: 300000
      # Leave connection-test-query unset when the driver supports isValid().
```

Interpretation: borrowing a connection can wait up to 30 seconds; validation is capped at 3 seconds; max lifetime is 25 minutes; the pool attempts keepalive on idle connections around every 5 minutes. These values **do not guarantee fixing every issue automatically** and are not a default recommendation for all environments.

For example, if infrastructure enforces a **strict 30-minute connection lifetime**: choosing a shorter `maxLifetime` (say 25 minutes) helps avoid using expired connections. Yet if a firewall closes sockets after only **3 minutes of idleness**, a 5-minute `keepaliveTime` is insufficient to proactively prevent idle drops; adjust to match real limits.

Do not reflexively increase `maximumPoolSize` when encountering `connectionTimeout` errors. Check slow queries, overly long transactions, DB connection limits, and concurrent requests. Also avoid pinging aggressively at very low intervals because that creates unnecessary traffic.

If the actual `DataSource` is a pool other than HikariCP or a custom bean, property names and connection management behavior must be checked against that pool type. The `spring.datasource.hikari.*` prefix does not turn `DriverManagerDataSource` into HikariCP.

## 6. Spring JDBC and Transactions: Who Is Responsible for Releasing Connections?

### 6.1. Using `JdbcTemplate` for Everyday Data Operations

`JdbcTemplate` uses Spring's mechanisms to borrow/release connections, prepare and execute SQL, process `ResultSet`s, and translate many `SQLException`s into the `DataAccessException` hierarchy. In many cases, the best way to reduce resource bugs is **not holding connections manually**.

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public final class CustomerLookup {
    private final JdbcTemplate jdbc;

    public CustomerLookup(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Customer findById(long id) {
        return jdbc.queryForObject(
            "SELECT id, name FROM customer WHERE id = ?",
            (rs, row) -> new Customer(
                rs.getLong("id"),
                rs.getString("name")
            ),
            id
        );
    }

    public record Customer(long id, String name) {}
}
```

The class above requires Spring JDBC setup, a DB, and a `customer` table, so **it does not run standalone with just the JDK**. If no customer exists with that ID, `queryForObject` can throw `EmptyResultDataAccessException`; that is a query-result error, not a sign of a lost connection.

Do not call `Connection.isValid()` before every `queryForObject`, because an extra ping adds overhead and errors can still happen when the subsequent SQL executes. Let the pool validate as designed, use `JdbcTemplate`, and handle business exceptions appropriately.

### 6.2. Plain JDBC Outside a Spring Transaction

If you must call `DataSource.getConnection()` directly outside a Spring transaction, close resources explicitly:

```java
try (Connection connection = dataSource.getConnection();
     var statement = connection.prepareStatement(
         "SELECT name FROM customer WHERE id = ?"
     )) {
    statement.setLong(1, 42L);

    try (var result = statement.executeQuery()) {
        if (result.next()) {
            System.out.println(result.getString("name"));
        }
    }
}
```

This is an illustrative snippet needing a `dataSource` variable, database, and JDBC imports. Each borrow must be returned promptly even if the SQL fails.

When inside a Spring-managed transaction, calling `dataSource.getConnection()` directly may create a connection not bound to the current transaction. When forced to write low-level JDBC, use `DataSourceUtils.getConnection(dataSource)` and `DataSourceUtils.releaseConnection(connection, dataSource)` to respect the thread/transaction-bound connection, or prefer `JdbcTemplate` which already uses this mechanism. Do not arbitrarily call `close()` directly on a connection obtained via `DataSourceUtils` while Spring is managing its transaction.

### 6.3. A Broken Connection Inside `@Transactional` Cannot "Resume" the Same Transaction

Suppose a money transfer transaction consists of:

```text
BEGIN
  UPDATE account A: debit
  UPDATE account B: credit
COMMIT
```

If the connection breaks between the two `UPDATE` statements, you must not grab another connection and continue the remaining statement as if keeping the same transaction. The session and prior transaction context belonged to the broken connection. Spring normally attempts to roll back/complete the transaction upon exception, but if the link is dead, the `ROLLBACK` command itself may also fail or receive no acknowledgment.

Especially if the application sends `COMMIT` and loses the connection while awaiting the response, **it is uncertain whether the DB committed or not**. You cannot deduce "client got an error = data definitely was not written". Money transfers, order creation, and event emission require idempotency keys or an independent reconciliation mechanism.

Example read service using a Spring transaction:

```java
import java.math.BigDecimal;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public final class AccountReader {
    private final JdbcTemplate jdbc;

    public AccountReader(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(readOnly = true)
    public BigDecimal balance(long accountId) {
        return jdbc.queryForObject(
            "SELECT balance FROM account WHERE id = ?",
            BigDecimal.class,
            accountId
        );
    }
}
```

The example requires a Spring application with a transaction manager, `JdbcTemplate`, and an `account` table. When a connection error occurs, let the exception propagate across the appropriate transaction boundary so Spring cleans up resources. Do not catch the exception and try to reuse the broken connection, nor manually start a new transaction from the middle of an unfinished one.

## 7. Recognizing Connection Errors vs. Query Errors Properly

Not every `SQLException` means a broken connection. Errors can also come from unique constraint violations, bad SQL, held locks, long waits, missing privileges, or an exhausted pool.

Several common indicators:

- `CannotGetJdbcConnectionException`: Spring could not obtain a JDBC connection; may be due to an unavailable DB, misconfiguration, or pool wait timeout.
- Exceptions in the `DataAccessException` family: Spring translates from JDBC by case; inspect the specific subtype and root cause.
- `SQLException` with `SQLState` in class `08`: typically indicates a connection exception per SQLState convention.
- `SQLTransientConnectionException`, `SQLNonTransientConnectionException`, or `SQLRecoverableException`: provide signals from the JDBC driver, though handling decisions still depend on timing and business semantics.
- Pool errors like "connection is not available" or "failed to validate": distinguish failing to borrow because the pool is exhausted from a physical connection having broken.

### 7.1. SQLState: Classify for Investigation, Do Not Auto-Retry

| SQLState Prefix | Common Error Group | Line of Thinking |
| --- | --- | --- |
| `08`, e.g. `08006` | Connection exception | Inspect DB, network, connection session, driver, and pool |
| `40`, e.g. `40001` | Transaction rollback/serialization | May need to retry the **entire transaction** under safe conditions |
| `23`, e.g. `23505` | Data integrity constraint violation | Look for duplicate keys or business bugs; borrowing a new connection will not fix it |
| `42` | Syntax/access privilege per SQLState convention | Check SQL, schema, and privileges, distinct from network incidents |
| `null` or vendor code | Driver omits standard code or uses custom convention | Check vendor code, cause chain, `getNextException()`, and DB/pool logs |

Do not jump to "whenever `DataAccessException` is caught, retry" or "whenever prefix is `08`, re-run the write statement". SQLState is useful for diagnosing the **error category**, not answering whether the business operation partially executed or already committed.

### 7.2. Standalone Java 17 Program Testing Classification

The example needs no Spring or real DB. It constructs four hypothetical `SQLException`s to practice reading SQLState—**not** a production retry decider.

Create file `SqlStateDiagnosticDemo.java`:

```java
import java.sql.SQLException;
import java.util.List;

public class SqlStateDiagnosticDemo {
    static String classify(SQLException error) {
        String state = error.getSQLState();
        if (state != null && state.startsWith("08")) {
            return "connection-failure";
        }
        if (state != null && state.startsWith("40")) {
            return "transaction-rollback";
        }
        if (state != null && state.startsWith("23")) {
            return "integrity-constraint";
        }
        return "unknown";
    }

    public static void main(String[] args) {
        List<SQLException> errors = List.of(
            new SQLException("Network lost", "08006"),
            new SQLException("Serialization conflict", "40001"),
            new SQLException("Duplicate key", "23505"),
            new SQLException("Unclassified")
        );

        for (SQLException error : errors) {
            System.out.println(
                error.getSQLState() + " -> " + classify(error)
            );
        }
    }
}
```

Run commands:

```bash
javac SqlStateDiagnosticDemo.java
java SqlStateDiagnosticDemo
```

Exact output:

```text
08006 -> connection-failure
40001 -> transaction-rollback
23505 -> integrity-constraint
null -> unknown
```

When investigating real incidents, pinpoint whether the failure happened during **acquiring the connection, executing SQL, committing, or rolling back**, along with SQLState, driver error code, original message, and pool state. The same "connection closed" phrase at different stages can lead to very different business decisions.

## 8. Process for Handling a Broken Connection

**Step 1 – Stop using the current connection.** When the driver/pool reports a connection error, do not reuse that `Connection` for the next SQL statement. `isClosed() == false` is not proof that continuing is safe. If inside a transaction, let the transaction reach an appropriate ending boundary.

**Step 2 – Clean up resources.** With plain JDBC, ensure `ResultSet`, `Statement`, and connection are closed via `try-with-resources` or `finally`. With `JdbcTemplate`/Spring transaction manager, let the framework manage cleanup per its contract. The pool handles broken physical connections once it detects an unusable state; the application does not need to hold a connection and ping infinitely.

**Step 3 – Locate where the failure happened.** If a connection could not be acquired, inspect pool saturation, DB, TLS, network, and authentication. If during SQL execution, check query timeout, DB restart, transaction, and network. If it failed right at `COMMIT`, data state may be indeterminate.

**Step 4 – Only let a new request/transaction obtain a new connection.** After finishing the old operation, the pool can issue another connection once the DB is ready. Never continue the second half of a broken transaction on a new connection.

**Step 5 – Decide on retries based on business semantics.** Independent, safely repeatable reads can be retried finitely; monetary/order writes require deduplication controls and reconciliation. Never use unbounded loops, especially when the DB is overloaded.

**Step 6 – Log and respond clearly.** Log SQLState, error type, failure stage, pool name, duration, correlation ID, and connection-wait state. Do not log passwords or sensitive information. If unrecoverable, return an appropriate infrastructure error; never return "success" when write results are unconfirmed.

## 9. When Can You Retry, and Where Should You Retry?

| Situation | Handling Approach |
| --- | --- |
| Independent, read-only `SELECT`, safely repeatable | Can retry finitely on a **new connection/transaction**, with total timeout and backoff |
| Pool exhausted because many requests hold connections | Diagnose load, concurrency limits, connection hold time; aggressive retries can worsen it |
| Connection lost mid-write transaction | Terminate old transaction, do not continue it on a new connection; evaluate safety before re-running the whole operation |
| Response lost during `COMMIT` | Reconcile state; do not assume the transaction failed |
| Write command with `idempotency_key` and deduplication constraint | Can design a **whole-operation** retry under an explicit contract |
| Wrong password, missing table, syntax error, duplicate key | Do not retry as a connection error; fix the root cause |

A controlled retry needs a maximum attempt count, exponentially increasing wait with randomness (*backoff + jitter*), total timeout budget, and error-rate monitoring. If using `@Retryable` with `@Transactional`, verify **advice/proxy ordering**: it is critical that each retry attempt is wrapped in a fresh transaction, not re-executed inside an already broken transaction.

For instance, a create-payment command is sent, the DB commits, but the `COMMIT` response is lost in transit. If the application retries `INSERT payment` without a unique business identifier, it may create **two payments**. The real fix is a unique request key enforced by a DB `UNIQUE` constraint, returning the prior result, and reconciliation; "healing" the connection cannot solve commit uncertainty.

**Retrying cannot resume a disconnected transaction.** It can only execute **a fresh business attempt** once safety conditions are established.

## 10. Distinguishing Common Timeouts

| Scope | Example | Controls |
| --- | --- | --- |
| Pool borrow wait | HikariCP `connectionTimeout` | How long a request may wait for the pool to issue a connection |
| Liveness check | `validationTimeout`, `Connection.isValid(seconds)` | How long a connection validation check may wait |
| Opening connection | JDBC driver connect timeout | Network setup and DB handshake duration; name and unit depend on driver |
| SQL execution | `Statement.setQueryTimeout(seconds)`, DB timeouts | Query run duration when supported by driver/DB |
| Network I/O wait | Socket timeout or `Connection.setNetworkTimeout(...)` when driver supports | Prevents hanging too long on network calls |
| Transaction | `@Transactional(timeout = ...)` with manager/driver/DB support | Bounds transaction within supported scope; not a hard clock across every driver |

Do not use `connectionTimeout` to cure a slow SQL query: once a connection is borrowed, SQL execution time is governed by another layer. Conversely, a query timeout does not fix a pool out of idle connections.

For `Connection.isValid(2)`, the unit is **seconds**; for `spring.datasource.hikari.validation-timeout: 3000`, the unit is **milliseconds**. Mixing up the two units can produce timeouts far too short or far too long.

## 11. Monitoring Database and Connection Pool Health

In Spring Boot with `spring-boot-starter-actuator`, Spring Boot can auto-register `DataSourceHealthIndicator` to report data source health (typically under the `db` component of `/actuator/health`). The health indicator checks `DataSource` via `Connection.isValid()` or a configured test query. Endpoint access permissions and returned detail level must be controlled appropriately.

Distinguish three concepts:

- **Liveness:** has the application process failed to the point that it must be restarted?
- **Readiness:** is the application ready to accept requests that depend on the DB?
- **Database health:** did acquiring/validating a connection succeed at the moment of observation?

Do not configure liveness so that all application replicas restart simultaneously just because a shared DB has a blip. Including DB in readiness requires architectural judgment: some applications can still serve non-DB features while the DB is temporarily down. A passing health check does not guarantee the next query will succeed; conversely, a health check can fail when the pool is saturated even though the DB server is still running.

If using Micrometer with HikariCP, monitor:

- `hikaricp.connections.active`: number of connections currently borrowed.
- `hikaricp.connections.idle`: number of idle connections.
- `hikaricp.connections.pending`: number of requests waiting for a connection.
- Connection borrow wait time, timeout counts, frequency of failed liveness warnings, and driver error logs.

For example, `active` persistently near `maximumPoolSize` alongside rising `pending` suggests pool saturation, slow queries, or long-held connections. It **does not directly prove DB sockets are dead**. Conversely, clusters of connection validation failures after idle periods point toward checking infrastructure timeouts/keepalive.

## 12. Scenario-Based Diagnosis

### Scenario A: First Request After an Idle Period Reports "connection reset"

An idle connection may have been closed earlier by the DB, proxy, or firewall. Check validation logs, idle duration, connection age, `keepaliveTime`, and `maxLifetime`. When the pool detects a dead connection, it can evict it and open a new one when the DB is ready. The first failed request must still be handled per the business contract; there is no guarantee every case is intercepted by the pool beforehand.

### Scenario B: DB Restarts Between Two SQL Statements Inside `@Transactional`

The active connection may drop; SQL/commit/rollback throws an exception. Do not continue the second half on another connection. Finish the old transaction, clean up resources, and clarify write status before deciding to re-run the whole operation. For idempotent reads, finite retries outside the old transaction are usually easier to control.

### Scenario C: `getConnection()` Times Out Yet Pinging the DB from Another Machine Still Works

The pool may be exhausted due to slow queries, long transactions, the app holding connections too long, or excessive request volume. Check `active`/`idle`/`pending`, DB connection limits, and leak warnings. Before increasing pool size, determine transaction length and DB load capacity.

### Scenario D: `isValid()` Returns `true` Yet `UPDATE` Still Fails

A ping only checks connectivity at a single instant; the statement can still fail due to network drop after the ping, locks, permissions, constraints, or timeouts. Read SQLState/vendor error codes and the failure location; do not conclude `isValid` was "wrong" when the two calls occurred at different moments.

### Scenario E: Timeouts Reported Yet Raising `connectionTimeout` Still Does Not Fix It

If the DB is stuck or the pool is leaking connections, waiting longer only prolongs hung requests. Inspect metrics and where connections are held. A reasonably short timeout can limit user impact, but must be chosen based on load and business needs, not guesswork.

## 13. Controlled Practice

In a test environment with a dedicated DB:

1. Start the application and run a simple read query; record health results and pool `active/idle/pending`.
2. Stop the test DB **between two reads**. Record the exception, SQLState, and failure point: when acquiring the connection or when executing SQL?
3. Restore the DB. Send a new request and confirm the pool can issue a working fresh connection.
4. Repeat with the DB stopped **while** a test query is executing; observe timeouts and resource cleanup. Do not use production data/DB for experiments.
5. Generate a bounded number of read requests to make the pool wait; compare pool-saturation errors against DB-disconnect errors.
6. With a simulated write operation, test a failure during commit and practice reconciliation based on a unique business key; do not infer commit status from network errors.

Each test result should record: **where the error occurred, evidenced cause, transaction state, application response, and recovery method**. Merely noting "connection closed" without knowing at which step makes choosing the right fix very difficult.

## 14. Questions and Answers

**1. Why can `connection.isClosed() == false` still encounter a "connection reset" error?**  
Because the closed state known to the driver may not yet reflect that the network dropped the connection; you must check proactively or accept detecting the error when SQL executes.

**2. Does `connection.isValid(2)` guarantee the `INSERT` right after it will succeed?**  
No. The DB/network can fail after the ping, and `INSERT` has other failure causes as well.

**3. Does `connectionTimeout: 30000` limit an SQL query to a maximum of 30 seconds?**  
No. It limits how long to wait to **borrow a connection from HikariCP**; queries need separate timeouts at the statement/driver/DB layer.

**4. With a Hikari pool, should `connectionTestQuery: SELECT 1` be added by default?**  
Usually no if the JDBC 4 driver supports `isValid()` properly. Only configure a test query when there is a specific reason.

**5. If a connection breaks between two update statements in the same transaction, can a new connection be used to continue the second statement?**  
No. The old transaction is no longer guaranteed; it must be terminated and re-executing the entire business operation evaluated under safe policies.

**6. Why shouldn't every failure at `COMMIT` be automatically retried?**  
Because the DB may have already committed before the client lost the response; retrying a write can create duplicate data/payments without idempotency and reconciliation mechanisms.

**7. Does `getConnection()` timing out prove the DB is down?**  
No. The pool may be saturated from connections held too long, too many requests, or slow queries.

## 15. Principles to Remember

- `DataSource` provides connections; the pool manages reuse and replacement of physical connections. **Closing resources on time** is foundational.
- `isClosed()` is not a network check. `isValid(timeout)` and pool validation reduce borrowing dead connections, yet cannot guarantee the next SQL succeeds.
- Configure `connectionTimeout`, `validationTimeout`, `maxLifetime`, and `keepaliveTime` to real DB/network limits; with JDBC 4, usually leave `connectionTestQuery` unset.
- `JdbcTemplate` and the transaction manager help manage connection lifecycle properly; **do not reuse a broken connection or transaction**.
- SQLState along with driver/pool info points the direction for diagnosis. An exception alone cannot decide whether a write operation is safe to retry.
- Retrying independent reads can be appropriate; retrying writes requires a new transaction boundary, bounded attempts, **idempotency, and reconciliation** when commit status is uncertain.
- Observe both DB state and pool `active`, `idle`, and `pending` to distinguish dead connections from an exhausted pool.

### References

- [JDK 17: `java.sql.Connection`](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html)
- [Spring Framework: Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)
- [Spring Framework: Data Access with JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html)
- [HikariCP: Configuration README](https://github.com/brettwooldridge/HikariCP/blob/dev/README.md)
- [Spring Boot 3.3: `DataSourceHealthIndicator`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/jdbc/DataSourceHealthIndicator.html)
