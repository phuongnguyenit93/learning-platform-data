# Initializing/Resetting Session State, SQL Mode, and Timezone on Connection Reuse

A physical connection to MySQL represents a session with its own state. When an application uses a connection pool, multiple requests can sequentially borrow the same physical connection. Settings such as `sql_mode`, `time_zone`, isolation level, user variables, temporary tables, and other session settings can persist after the previous request returns the connection to the pool. Without intentional initialization and reset, a subsequent request may run under an unexpected SQL environment, causing data errors, incorrect timestamps, or state leakage between requests.

This lesson belongs to the **Spring Boot and JPA** chapter of the **DATABASE_MYSQL** module. On the path to mastering MySQL—from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query tuning, access control, backups, and operations—a Java application must properly manage session lifecycles when connections are reused. The focus is distinguishing server configuration, session state, and ORM settings; understanding when HikariCP executes init SQL; and selecting appropriate reset strategies before a connection serves the next request.

## 1. How Does a Connection Pool Reuse Sessions?

When Spring Boot uses HikariCP, the application typically calls `DataSource.getConnection()`. The pool returns a logical connection backed by an open physical connection to MySQL. When the application calls `Connection.close()`, the logical connection is returned to the pool; the TCP connection usually stays open for another request to use.

~~~text
Request A
   |
   | borrow
   v
HikariCP ---- physical connection #12 ---- MySQL session #12
   |                                          |
   | Request A: SET SESSION time_zone ...    |
   | Request A: query / transaction           |
   |                                          |
   | close logical connection                 |
   v                                          |
Pool retains physical connection -------------+
   |
   | borrow same connection again
   v
Request B may receive session #12
   |
   | session variables remain if not reset
   v
Request B
~~~

A pool may track and restore certain JDBC states it manages—such as auto-commit, read-only, isolation level, catalog, or schema depending on the pool. However, never assume the pool automatically understands and reverts every SQL `SET SESSION` statement the application executed.

For example, Request A executes:

~~~sql
SET SESSION time_zone = '+07:00';
SET SESSION sql_mode = '';
SET @tenant_id = 42;
~~~

Then Request A calls `close()`. If the pool retains the physical connection without resetting these SQL variables, Request B may receive that exact session with altered timezone, `sql_mode`, and user variables.

**Principle:** MySQL state belongs to the physical session. Closing a pooled logical connection does not mean the MySQL session was closed or reset.

## 2. Distinguishing GLOBAL, SESSION, and Per-Transaction Settings

MySQL has multiple configuration scopes:

| Scope | Effect | Example |
|---|---|---|
| GLOBAL | Default for new sessions; does not automatically alter existing open sessions | `SET GLOBAL sql_mode = ...` |
| SESSION | Alters only the current session | `SET SESSION time_zone = '+00:00'` |
| Transaction | Certain settings apply only to the next transaction | `SET TRANSACTION ISOLATION LEVEL READ COMMITTED` |
| Server configuration | Settings loaded at server startup; managed via option files or persistence mechanisms | Default `sql_mode`, timezone |

Inspect both global and session values:

~~~sql
SELECT
  @@GLOBAL.sql_mode AS global_sql_mode,
  @@SESSION.sql_mode AS session_sql_mode,
  @@GLOBAL.time_zone AS global_time_zone,
  @@SESSION.time_zone AS session_time_zone,
  @@SESSION.autocommit AS session_autocommit,
  @@SESSION.transaction_isolation AS session_isolation;
~~~

`SET GLOBAL` changes the default for new connections, while existing sessions keep their current session values. Therefore, changing global settings while the application is running does not guarantee the entire connection pool immediately adopts the new configuration.

For systems requiring consistent configuration, define global values in server configuration or use a persistence mechanism supported by your version. For instance, MySQL 8.0 supports `SET PERSIST` for persistable variables. Afterward, sessions must be recreated or updated/reset via an explicit procedure.

Never run `SET GLOBAL` per request. A single request must not alter the default configuration for all new connections in the system.

## 3. Types of Session State to Manage

A MySQL session can hold many kinds of state:

| State | Example | Risk When Connection Is Reused |
|---|---|---|
| SESSION-level system variables | `sql_mode`, `time_zone`, `group_concat_max_len` | Next request's SQL may execute under different rules |
| Transaction settings | `autocommit`, isolation level | Changes commit boundaries or data visibility |
| User variables | `@tenant_id`, `@batch_id` | Next request may read stale values from a prior request |
| Temporary tables | `CREATE TEMPORARY TABLE ...` | Temporary tables may linger in the session |
| Named locks | `GET_LOCK()` | Locks may remain held after the request ends |
| Server-side prepared statements | Statements created with SQL `PREPARE` | Consumes resources or causes name collisions if not deallocated |
| Open transactions | Uncommitted/unrolled-back DML | Holds locks, undo logs, and affects subsequent requests |
| Session charset/collation | `SET NAMES`, `character_set_results` | Comparisons or data encoding may behave unexpectedly |
| Foreign/unique checks | `foreign_key_checks`, `unique_checks` | Can bypass data integrity checks if not re-enabled |

Not every state is cleared by a single simple SQL statement. Know what your application modifies and choose a verifiable management policy.

## 4. SQL Mode: Ensuring Consistent Execution Rules

`sql_mode` governs how MySQL handles cases such as out-of-range values, invalid dates, division by zero, `GROUP BY`, and various compatibility behaviors.

Check current values:

~~~sql
SELECT @@GLOBAL.sql_mode, @@SESSION.sql_mode;
~~~

A session can be altered by:

~~~sql
SET SESSION sql_mode = '';
~~~

This sets the current session to an empty SQL mode set. With a connection pool, if the request does not restore state, the next request may lose strict mode or other rules the application relies on.

To reset the session back to the current global value:

~~~sql
SET SESSION sql_mode = DEFAULT;
~~~

Here `DEFAULT` pulls the default from `GLOBAL` for the session. Ensure global `sql_mode` is configured properly; resetting to a misconfigured global value still yields a misconfigured session.

### Choosing SQL Modes Intentionally

Do not copy a mode string from another environment and overwrite the entire configuration. Before setting values, record the current modes and identify which modes must be preserved, for example:

- `STRICT_TRANS_TABLES`: rejects or raises errors for many invalid data cases instead of silently coercing values.
- `ONLY_FULL_GROUP_BY`: validates selected columns when using `GROUP BY`.
- `ERROR_FOR_DIVISION_BY_ZERO`: controls division-by-zero handling under the configured mode.
- `NO_ENGINE_SUBSTITUTION`: prevents silently substituting storage engines if the requested engine is unavailable.

Available modes and defaults vary by MySQL version. Check the target version's documentation, global configuration, and test the application before changing them. Never disable strict mode just to let a broken batch import keep running; fix invalid data at the source.

### Server-Level or Session-Level Configuration?

If all applications require the same SQL mode, configure it at the server level so every new session shares a unified default. If one application has special needs, you can set `SESSION` at connection initialization or before a transaction, while ensuring other requests never inherit an altered session state.

When global `sql_mode` changes, open sessions in the pool may still retain the old mode. Drain/evict connections or explicitly reset sessions according to your rollout plan.

## 5. Timezone: Distinguishing Server, Session, and JVM

Timezones span at least three independent layers:

1. **MySQL server timezone:** `@@GLOBAL.time_zone`; `SYSTEM` means MySQL uses the host OS timezone.
2. **MySQL session timezone:** `@@SESSION.time_zone`; affects temporal expressions and `TIMESTAMP` conversions within the session.
3. **JVM/Hibernate timezone:** the Java timezone used when converting, binding, and extracting temporal values over JDBC.

Inspect them:

~~~sql
SELECT
  @@GLOBAL.time_zone AS global_time_zone,
  @@SESSION.time_zone AS session_time_zone,
  @@system_time_zone AS system_time_zone,
  NOW() AS session_now,
  UTC_TIMESTAMP() AS utc_now;
~~~

Set the session timezone to UTC using a fixed offset:

~~~sql
SET SESSION time_zone = '+00:00';
~~~

The `+00:00` offset does not depend on MySQL's timezone tables. If you use a named timezone like `Asia/Ho_Chi_Minh`, the server must have timezone tables loaded. If timezone tables are missing, MySQL returns an error when using named zones.

### TIMESTAMP and DATETIME Differ

- **TIMESTAMP:** MySQL converts values from the session timezone to UTC on write, and from UTC to the session timezone on read. The same stored instant can display differently across sessions with different timezones.
- **DATETIME:** stores calendar date/time values literally as supplied, without automatic conversion based on session timezone on read/write.

Consequently, if a `TIMESTAMP` column is written by a `+07:00` session and read by a `+00:00` session, the displayed hour differs while representing the same instant. With `DATETIME`, the wall-clock value is stored verbatim; the application must enforce consistent timezone semantics itself.

`NOW()` and `CURRENT_TIMESTAMP` reflect the session timezone. `UTC_TIMESTAMP()` returns UTC time. Do not swap one for the other without reviewing business semantics.

### Connector/J and Hibernate

With Connector/J 8.0.23 and later, you can configure the connection timezone and instruct the driver to synchronize the session timezone:

~~~text
jdbc:mysql://db.example.internal:3306/appdb?connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true
~~~

- `connectionTimeZone=UTC` sets the timezone Connector/J uses for temporal conversions.
- `forceConnectionTimeZoneToSession=true` instructs the driver to apply that timezone to the MySQL session.
- If you only set `connectionTimeZone` without enabling force, do not assume `@@SESSION.time_zone` has changed.

With Hibernate, you can configure the JDBC timezone:

~~~yaml
spring:
  jpa:
    properties:
      hibernate:
        jdbc:
          time_zone: UTC
~~~

This Hibernate setting controls how Hibernate binds and extracts temporal values via JDBC. It does not replace verifying MySQL's `@@SESSION.time_zone`. Both layers should be configured consistently when the application processes timestamps in UTC.

If using an older Connector/J version, timezone properties and behavior may differ. Check the documentation for your exact driver version; do not apply URL examples from a newer version to an older driver.

## 6. HikariCP: When Does connectionInitSql Run?

Spring Boot typically uses HikariCP when Hikari is on the classpath and selected as the pool. HikariCP exposes `connectionInitSql`, bound in Spring Boot via `spring.datasource.hikari.connection-init-sql`.

This property executes SQL right after Hikari creates a new physical connection, before placing it into the pool. It is **not a callback that runs every time the application borrows a connection**.

Example configuring an initial baseline:

~~~yaml
spring:
  datasource:
    url: jdbc:mysql://db.example.internal:3306/appdb
    username: app_user
    password: ${DB_PASSWORD}
    hikari:
      connection-init-sql: "SET SESSION time_zone = '+00:00', SESSION sql_mode = DEFAULT"
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 30000
  jpa:
    properties:
      hibernate:
        jdbc:
          time_zone: UTC
~~~

This example sets the UTC timezone and pulls session SQL mode from the global default whenever a new physical connection is created. Passwords come from environment variables or a secret manager, never hardcoded in the repository.

If the application only needs one uniform set of session defaults, this initialization is useful. However, if code later runs `SET SESSION sql_mode = ''` or changes timezone on the connection, subsequent borrows may still see the modified value. `connectionInitSql` does not re-run just because a logical connection was returned and borrowed again.

HikariCP tracks and restores certain JDBC properties it manages. Do not extrapolate from that to assume arbitrary SQL commands that alter MySQL session variables are automatically restored.

## 7. Setting Session Defaults Before a Transaction in Spring

If a transaction must guarantee a specific SQL mode and timezone, you can set them on the transaction-bound connection before running repository queries. `JdbcTemplate` must share the same `DataSource` and transaction manager as JPA so operations participate in the same transaction.

Example:

~~~java
@Service
public class OrderService {
    private final JdbcTemplate jdbcTemplate;
    private final OrderRepository orderRepository;

    public OrderService(
            JdbcTemplate jdbcTemplate,
            OrderRepository orderRepository) {
        this.jdbcTemplate = jdbcTemplate;
        this.orderRepository = orderRepository;
    }

    @Transactional
    public Order createOrder(CreateOrderRequest request) {
        jdbcTemplate.execute(
            "SET SESSION time_zone = '+00:00'"
        );
        jdbcTemplate.execute(
            "SET SESSION sql_mode = DEFAULT"
        );

        // Call the repository only after setting session defaults.
        Order order = new Order();
        order.setCustomerId(request.customerId());
        order.setCreatedAt(Instant.now());

        return orderRepository.save(order);
    }
}
~~~

In this setup, `JdbcTemplate` and JPA must share the same `DataSource`, and the transaction manager must allow JDBC access to participate in the JPA transaction. If two different DataSources or transaction managers are used, the `SET` statements may execute on a different connection from the one Hibernate uses.

Setting session defaults at the start of a transaction keeps the request independent of leftover values from previous borrows. However, every database access path must follow the same policy; queries running outside transactions or in background jobs must also be handled.

If different requests require different timezones or SQL modes, design a cleanup mechanism before returning the connection. Never let a request freely mutate session state and rely on the next request to fix it.

## 8. Resetting State Before Returning a Connection to the Pool

Three common strategies exist:

### Strategy A: Keep Session State Immutable

This is the simplest approach. Configure one consistent set of defaults for the entire connection pool and never alter them per request. For example, every session uses UTC and the same SQL mode.

- Set global defaults on the server.
- Use Connector/J or Hikari connection init SQL to establish initial state.
- Do not execute arbitrary `SET SESSION` commands in business code.
- If a different transaction isolation is needed, use Spring's transaction configuration instead of mutating persistent session variables.

### Strategy B: Restore Known Variables

If code modifies a small, known set of session variables, restore them to standard defaults before returning the connection to the pool:

~~~sql
SET SESSION sql_mode = DEFAULT;
SET SESSION time_zone = '+00:00';
SET SESSION foreign_key_checks = DEFAULT;
SET SESSION unique_checks = DEFAULT;
~~~

For user variables, reset them explicitly:

~~~sql
SET @tenant_id = NULL;
SET @request_id = NULL;
~~~

Temporary tables must be dropped if still present; named locks must be released; transactions must be committed or rolled back. Reset commands must run on the exact physical session before the connection returns to the pool.

Do not reset only `sql_mode` and `time_zone` and assume the session is clean. Inventory every kind of state your application creates and write tests to verify cleanup.

### Strategy C: Full Session Reset or Discarding the Physical Connection

The MySQL protocol provides the `COM_RESET_CONNECTION` command to reset session state without closing the TCP connection. This mechanism can roll back open transactions, reset session variables to global defaults, clear user variables and temporary tables, and release session state and server-side prepared statements.

This is a protocol-level command; do not send a SQL string `RESET CONNECTION` as a normal SQL query. Only rely on session reset if your driver/pool version supports it and documentation confirms how it integrates. After a reset, required settings such as timezone or session defaults must be reapplied according to pool policy.

If no reset mechanism is supported, the pool can evict the physical connection and open a fresh one. This incurs connection and authentication overhead, but eliminates old session state. Never close the underlying socket behind the pool's back; use eviction/invalidation APIs provided by the pool.

### When to Reset

Safe sequence:

1. Finish request work.
2. Commit or roll back the transaction.
3. Clear/restore any modified session state.
4. If cleanup fails, mark the connection untrusted and evict it from the pool.
5. Return the connection to the pool after cleanup completes.

Never return a connection to the pool before cleanup finishes. If a transaction is open, roll back first; if the connection is already broken, do not try to use it to reset state—let the pool discard it.

## 9. Transaction Isolation and Autocommit

`autocommit` and transaction isolation strongly affect how requests see data.

Check them:

~~~sql
SELECT
  @@SESSION.autocommit,
  @@SESSION.transaction_isolation;
~~~

If a request executes:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;
~~~

that `SESSION` setting can persist for subsequent transactions on the same session. If another request expects `REPEATABLE READ`, it may accidentally inherit the weaker isolation level.

In Spring, prefer declaring isolation at the transaction boundary:

~~~java
@Transactional(isolation = Isolation.READ_COMMITTED)
public void readReport() {
    // Queries run in a transaction with the declared isolation.
}
~~~

Spring's transaction manager manages JDBC isolation state and restores tracked state when the transaction ends. Do not mix multiple isolation-setting mechanisms without clear justification.

MySQL also has syntax to set isolation for the next transaction only:

~~~sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;
~~~

Do not confuse this syntax with `SET SESSION TRANSACTION ISOLATION LEVEL ...`, which changes the default isolation for all subsequent transactions in the session.

When using a pool, always ensure transactions are committed or rolled back before closing the logical connection. Never assume the pool can automatically fix an open transaction without impacting other requests.

## 10. Testing Session Leakage in a Test Environment

A simple test can detect session state leaking through the pool. Use a pool with a single physical connection so consecutive borrows are likely to receive the same session:

1. Borrow connection A.
2. Read `CONNECTION_ID()`, `@@SESSION.time_zone`, and `@@SESSION.sql_mode`.
3. Change timezone or SQL mode.
4. Set a user variable.
5. Close logical connection A.
6. Borrow connection B.
7. Read the values again and compare.

Verification queries:

~~~sql
SELECT
  CONNECTION_ID() AS connection_id,
  @@SESSION.time_zone AS session_time_zone,
  @@SESSION.sql_mode AS session_sql_mode,
  @tenant_id AS tenant_id;
~~~

If the connection ID is identical and session values still carry changes from the prior request, the pool reused an uncleaned session. If the connection ID differs, the test has not proven state was reset; it merely received a different physical connection. Configure the test pool with `maximumPoolSize=1` and run sequentially for reproducible tests.

Write integration tests with real MySQL or Testcontainers rather than only mocking the `DataSource`. Mocks cannot verify server session behavior, timezone conversions, SQL modes, or protocol resets.

### Scenarios to Include in Tests

- Request A changes `time_zone`; Request B must still see UTC.
- Request A changes `sql_mode`; Request B must still see the standard mode.
- Request A sets a user variable; Request B must not see that value.
- Request A creates a temporary table; Request B must not reuse that table if policy requires cleanup.
- Request A acquires a named lock; Request B must not be blocked by a leftover lock.
- Request A rolls back after an error; Request B must not see an unfinished transaction.
- A server restart or connection timeout occurs; the pool creates a new connection and reapplies init defaults.

## 11. Observability and Operational Troubleshooting

When a request is caught running with the wrong timezone or SQL mode, capture diagnostics right on the offending connection:

~~~sql
SELECT
  CONNECTION_ID(),
  @@GLOBAL.sql_mode,
  @@SESSION.sql_mode,
  @@GLOBAL.time_zone,
  @@SESSION.time_zone,
  @@SESSION.autocommit,
  @@SESSION.transaction_isolation;
~~~

In the application, log the pool name, request correlation ID, transaction boundary, and driver configuration. Never log passwords, access tokens, or sensitive personal data.

Common symptoms:

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Some requests have shifted timestamps | Different session timezones across connections | Log `CONNECTION_ID()`, `@@SESSION.time_zone` |
| Some requests fail to reject invalid data as expected | SQL mode altered or strict mode disabled | Compare `GLOBAL` and `SESSION` `sql_mode` |
| Subsequent requests see old user variables | Session reused without cleanup | Inspect `@variable` on the same connection |
| Queries affected by old temporary tables | Temporary table persists in session | Check session lifecycle and reset |
| Transactions hold locks too long | Connection returned to pool with open transaction | Check `autocommit`, rollbacks, and transaction manager |
| Errors appear only under high load | Requests rotate across connections with divergent states | Run integration tests with a small pool and log connection IDs |
| After deploy, only some connections use new config | Older pooled connections keep pre-deploy session defaults | Drain/evict the pool and establish new connections |

After changing global defaults or URL properties, consider draining the pool so old physical connections are closed and recreated. Roll out via rolling deployments to avoid dropping all application connections simultaneously.

## 12. Spring Boot/JPA Configuration Checklist

**Server and Driver Configuration**

- [ ] Determine global `sql_mode` and timezone on MySQL.
- [ ] Standardize on a single timezone, usually UTC for application sessions.
- [ ] Check Connector/J version before using `connectionTimeZone` and `forceConnectionTimeZoneToSession`.
- [ ] Align timezones between Connector/J and Hibernate.
- [ ] Never run `SET GLOBAL` inside business requests.

**Pool Configuration**

- [ ] Understand that `connectionInitSql` runs only when a new physical connection is created.
- [ ] Do not assume init SQL runs on every borrow.
- [ ] Document required session defaults explicitly.
- [ ] Have a cleanup/reset mechanism if the application mutates session state.
- [ ] Evict connections if cleanup fails or session integrity is uncertain.

**Transactions and Code**

- [ ] Share the same `DataSource`/transaction manager between `JdbcTemplate` and JPA when participating in the same transaction.
- [ ] Apply session defaults before the first repository query.
- [ ] Prefer Spring-managed transaction isolation.
- [ ] Commit/roll back before returning a connection.
- [ ] Do not use user variables or temporary tables without an explicit lifecycle.

**Testing**

- [ ] Test with real MySQL and a connection pool.
- [ ] Simulate sequential requests over the same physical connection.
- [ ] Verify SQL mode, timezone, `autocommit`, and isolation.
- [ ] Test temporary tables, user variables, and named locks if used by the application.
- [ ] Test reconnects, server restarts, and pool draining after configuration changes.

## 13. Key Takeaways

- Closing a pooled logical connection normally only returns it to the pool; the physical MySQL session may remain alive.
- `SESSION` variables, user variables, temporary tables, and named locks are scoped to the session lifecycle.
- `GLOBAL` defaults do not automatically update already-open sessions.
- HikariCP `connectionInitSql` executes on physical connection creation, not on every borrow.
- Connector/J `connectionTimeZone`, `forceConnectionTimeZoneToSession`, and Hibernate `hibernate.jdbc.time_zone` serve distinct timezone layers.
- `TIMESTAMP` converts across session timezones; `DATETIME` stores calendar values without automatic conversion.
- Use `SET SESSION ... = DEFAULT` to restore known variables to global defaults; reset user variables and other session resources according to their lifecycle.
- `COM_RESET_CONNECTION` is a protocol-level mechanism; use it only through driver/pool support, not as a normal SQL string.
- Finish transactions and clean up before returning a connection to the pool.
- Test session leakage with real MySQL, a small pool, and `CONNECTION_ID()`.

Proper session state management ensures every request sees a predictable SQL environment even as connections are reused repeatedly. Define which state is pool-wide default, which belongs to a single transaction, and which must be cleaned up; then verify with integration tests against the exact MySQL version and pool your application deploys.

## References

- [MySQL 8.0 Reference Manual: SET Syntax for Variable Assignment](https://dev.mysql.com/doc/refman/8.0/en/set-variable.html)
- [MySQL 8.0 Reference Manual: Server System Variables — sql_mode and time_zone](https://dev.mysql.com/doc/refman/8.0/en/server-system-variables.html)
- [MySQL 8.0 Reference Manual: TIMESTAMP and DATETIME](https://dev.mysql.com/doc/refman/8.0/en/datetime.html)
- [MySQL 8.0 Reference Manual: COM_RESET_CONNECTION](https://dev.mysql.com/doc/dev/mysql-server/latest/page_protocol_com_reset_connection.html)
- [MySQL Connector/J Developer Guide: Connection Time Zone](https://dev.mysql.com/doc/connector-j/en/connector-j-connp-props-datetime-types-processing.html)
- [HikariCP Configuration: connectionInitSql](https://github.com/brettwooldridge/HikariCP#gear-configuration-knobs-baby)
- [Spring Boot Reference: Configure a DataSource](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Hibernate ORM User Guide: JDBC Time Zone](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#basic-temporal)
