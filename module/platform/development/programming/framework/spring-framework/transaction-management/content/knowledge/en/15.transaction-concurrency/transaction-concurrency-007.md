# Lock Timeout, Transaction Timeout, and Canceled Statements in Spring Framework

## 1. The problem: all called "timeout," yet different impacts

In a Spring Framework application where multiple requests update the same record, transaction A holds a lock to modify data; transaction B waits for the lock and eventually receives a timeout error. In another scenario, a transaction is not waiting on a lock at all, yet runs Java logic for too long; when it executes the next JDBC statement, Spring detects that the **transaction deadline** has expired. A third scenario is a SQL statement being canceled due to `Statement.setQueryTimeout(...)`, a server-side timeout, or a `Statement.cancel()` call.

The three issues are related, yet they **do not share the same timer, do not use the same mechanism, and do not guarantee the same rollback outcome**.

This lesson belongs to the **Locking and Concurrency** section of Spring transaction management. After this lesson, you can:

- Distinguish **lock wait timeout**, **transaction timeout**, **statement/query timeout**, **statement cancellation**, and **connection-pool acquisition timeout**.
- Understand which transaction holds the lock, which statement is waiting, who configures the timeout, and who enforces it.
- Configure `@Transactional(timeout = ...)`, `TransactionTemplate.setTimeout(...)`, and XML `<tx:method timeout="...">` with the right units and transaction boundary.
- Explain how `DataSourceTransactionManager` propagates the remaining deadline down to JDBC `Statement` via `JdbcTemplate` / `DataSourceUtils`.
- Understand the limitations: a transaction timeout is **not** a timer that interrupts arbitrary Java work, and `Future.cancel(true)` does not mean the SQL command has been canceled.
- Distinguish a statement-only rollback from rolling back the entire physical transaction, even when an exception is caught.
- Run a Java 17+ demo with two concurrent JDBC transactions on H2: a lock timeout due to a locked record; a Spring deadline expiring before the next SQL statement; and verifying data after rollback.
- Read the root cause (`SQLException`, SQLState/error code), design retries at the right transaction boundary, and avoid holding locks too long.

**Running example:** The `locked_account` table has `id=1, balance=100`. Transaction W acquires a lock to update `balance=200` without committing yet. Transaction C wants to update `balance=300`, cannot acquire the lock in time, and has its statement canceled. Eventually W rolls back, so the committed value remains 100. In a separate flow, a transaction with `timeout=1` second inserts a row, waits in Java, and then uses `JdbcTemplate` to run another SQL statement: Spring checks the deadline and prevents the transaction from continuing.

## 2. Classifying timeouts: which layer controls what?

| Mechanism | Measured from? | Set by | Target bounded | Typical unit |
| --- | --- | --- | --- | --- |
| **Lock wait timeout** | Wait duration to acquire a lock for one operation | DB/session/engine; configured per DB | Statement waiting for lock | H2/PostgreSQL/SQL Server: ms; MySQL InnoDB: seconds |
| **Spring transaction timeout** | Lifetime of a new Spring-managed transaction | `@Transactional`, `TransactionTemplate`, manager | Transaction scope/deadline; passed to JDBC statements when supported | Seconds |
| **JDBC statement/query timeout** | Execution time of one SQL statement | `Statement.setQueryTimeout` / `JdbcTemplate.setQueryTimeout` | Executing statement | Seconds |
| **DB statement timeout** | Server processing time for a statement | E.g., PostgreSQL `statement_timeout` | Session/server statement | Usually ms or unit-suffixed string |
| **Statement cancellation** | Active cancellation request | `Statement.cancel()` or server/client | Running statement, driver/backend dependent | Does not necessarily have a deadline |
| **Pool acquisition timeout** | Time waiting to borrow a connection from pool | E.g., HikariCP `connectionTimeout` | Waiting for a connection, **not** waiting for a row lock | Milliseconds |
| **Network/socket timeout** | Waiting on network/driver I/O | Driver, network layer, `Connection.setNetworkTimeout` | Connection communication | Usually milliseconds |
| **HTTP/request timeout** | Request budget at application/gateway | API framework/client/gateway | HTTP request | System-dependent |

### Three questions to ask before handling errors

1. **Waiting on a lock or running slow SQL?** Lock waiting is one part of time inside a statement; statement/query timeout may include lock wait time depending on DB/driver.
2. **Did the error come from the DB, JDBC driver, or Spring transaction manager?** The Java exception class is only a wrapper; inspect the underlying `SQLException` and SQLState/error code.
3. **Which transactions can still commit?** Some DBs abort only the failed statement; some put the whole transaction into an aborted state. Furthermore, if a `RuntimeException` escapes through a Spring `@Transactional` proxy, **Spring rolls back the entire transaction owned by that proxy by default**, even if the backend only canceled one statement.

**Rule:** Never infer "statement was canceled" = "all changes rolled back"; nor infer "exception was caught" = "transaction is still safe to commit."

## 3. Lock wait timeout: one transaction waiting for a resource held by another

### 3.1. Timeline

```text
Connection W / transaction T1         Connection C / transaction T2
----------------------------------    -----------------------------------
BEGIN
SELECT ... FOR UPDATE (id=1)
UPDATE id=1 SET balance=200
(lock remains held)
                                     BEGIN
                                     UPDATE id=1 SET balance=300
                                     -> WAITS for T1's lock
... continues holding lock ...
                                     exceeds lock wait limit
                                     -> statement errors
                                     -> interceptor may roll back T2
ROLLBACK T1
                                     fresh query -> balance is still 100
```

Here T1 and T2 are **two transactions on two separate physical connections**. A transaction can read/write rows it already locked itself, so if you test "UPDATE then UPDATE" on the **same connection**, you have not verified contention.

### 3.2. Lock timeout is not transaction timeout

- Lock wait timeout concerns **a single lock wait**, not necessarily bounding all work in the transaction.
- Spring's `@Transactional(timeout = 30)` does not mean DB `lock_timeout=30s`.
- One SQL statement can hit a lock timeout while plenty of Spring transaction budget remains.
- Conversely, a Spring transaction deadline can expire while code is computing, calling another API, or waiting on a thread — without waiting for any database lock.
- When both limits are configured, which triggers first depends on the situation, driver, and how the backend accounts for timeouts.

### 3.3. When a lock timeout happens, whose lock is released?

The transaction **holding the lock** is not automatically rolled back just because another transaction timed out waiting. Transaction W can keep holding the lock until W commits/rolls back or its session ends per DB rules.

Meanwhile, the **waiting** transaction may:

- Lose only the waiting statement and still be able to continue the transaction, depending on DB/error state.
- Be placed into a failed/aborted state by the database until rollback.
- Be completely rolled back by the Spring transaction interceptor if the exception exits the `@Transactional` method and matches rollback rules.

Therefore, distinguish **DB state** from **Spring's rollback policy**; both can lead to rollback, yet operate at different layers.

## 4. Spring transaction timeout: a deadline, not a thread killer

### 4.1. @Transactional(timeout = ...)

```java
@Transactional(timeout = 5)
public void processBatch() {
    jdbcTemplate.update(
            "UPDATE locked_account SET balance = ? WHERE id = ?",
            110, 1L);
    // Subsequent JDBC statements are subject to the remaining budget
    // of the new Spring-managed transaction.
}
```

This snippet is a fragment assuming `jdbcTemplate` exists. `timeout = 5` is in **seconds**. With a supporting JDBC transaction manager, Spring sets a deadline when **starting a new physical transaction** and passes the remaining time down to each statement created through Spring JDBC.

Key characteristics:

- `@Transactional(timeout = 5)` is not a timer that automatically calls `Thread.interrupt()` after 5 seconds.
- If a method executes `Thread.sleep(10_000)` and **runs no further JDBC statements**, the annotation alone does not guarantee thread cancellation or a `TransactionTimedOutException` right at 5 seconds. Understand the manager/driver lifecycle.
- With `JdbcTemplate`, when creating a statement, Spring uses `DataSourceUtils.applyTransactionTimeout(...)` and `Statement.setQueryTimeout(...)`. If the deadline has already expired, computing the remaining time can throw `TransactionTimedOutException` **before the statement executes**.
- A running SQL statement may be canceled by the driver/server when query timeout is applied; whether cancellation happens promptly depends on the driver and database.
- Commit itself can take time, and a soft timeout does not guarantee an absolute hard end-to-end bound for every operation.

### 4.2. Where is the deadline applied?

```text
@Transactional(timeout = 5) proxy begins transaction
    |
    +-- t=0s: INSERT A        -> statement budget ~5s remaining
    |
    +-- t=2s: UPDATE B        -> statement budget ~3s remaining
    |
    +-- t=4s: SELECT C        -> statement budget ~1s remaining
    |
    +-- t=6s: UPDATE D        -> deadline already expired
              |
              +-- JdbcTemplate/DataSourceUtils may throw
                  TransactionTimedOutException before execute
    |
    +-- transaction interceptor rolls back if exception escapes
```

The timeout clock belongs to the **newly started transaction**, not 5 fresh seconds per query. `Statement#setQueryTimeout` is the JDBC capability Spring leverages to bound statements by the **remaining time**.

Spring JDBC `JdbcTemplate` automatically handles transaction-bound `Connection` and statement settings. If code manually creates raw `Statement`s, it does not inherit every `JdbcTemplate` timeout automatically; when using raw JDBC inside a Spring-managed transaction, obtain the connection via `DataSourceUtils` and call `DataSourceUtils.applyTransactionTimeout(statement, dataSource)` on manually created statements (or use an appropriate connection proxy). Never manually call `commit/rollback` on a Spring-managed connection.

### 4.3. Propagation decides who sets the deadline

| Propagation | When an outer transaction exists | New deadline? |
| --- | --- | --- |
| `REQUIRED` | Joins outer transaction | Does **not** automatically alter the existing physical transaction's deadline |
| `REQUIRES_NEW` | Suspends outer, opens new physical transaction | Can set its own deadline |
| `NESTED` | Uses savepoint in shared physical transaction | Does not open a physical transaction with an independent deadline |
| No outer + `REQUIRED` | Opens new transaction | Applies `timeout` if manager supports it |
| Self-invocation `this.method()` in same bean | May bypass proxy method | Timeout metadata on the called method may not apply |

Example:

```java
@Transactional(timeout = 20)
public void outer() {
    otherService.inner(); // another bean, inner REQUIRED timeout=2
}

// In bean otherService:
@Transactional(propagation = Propagation.REQUIRED, timeout = 2)
public void inner() {
    // Joins outer physical transaction: does not get its own 2s deadline.
}
```

Both snippets are illustrative fragments. You cannot use an inner `@Transactional(timeout=2)` to "shorten" an outer `timeout=20` deadline when inner merely joins that transaction. If you genuinely need a bound for a specific SQL statement, use a suitable query/statement timeout; if you need an independent transaction, consider `REQUIRES_NEW` with its own connection and commit implications.

### 4.4. TransactionTemplate and XML

Programmatic transaction:

```java
TransactionTemplate template = new TransactionTemplate(transactionManager);
template.setTimeout(5);

template.executeWithoutResult(status -> {
    jdbcTemplate.update(
            "UPDATE locked_account SET balance = ? WHERE id = ?",
            120, 1L);
});
```

Illustrative snippet assuming `PlatformTransactionManager transactionManager` and `JdbcTemplate jdbcTemplate`. `TransactionTemplate` defaults to `REQUIRED`, so it gets its own deadline only when creating a new physical transaction.

XML transaction advice:

```xml
<tx:advice id="txAdvice" transaction-manager="transactionManager">
    <tx:attributes>
        <tx:method name="update*" propagation="REQUIRED" timeout="5"/>
        <tx:method name="find*" read-only="true"/>
        <tx:method name="*"/>
    </tx:attributes>
</tx:advice>
```

Configuration fragment requiring namespaces, manager bean, and AOP advisor/pointcut. `timeout="5"` is **5 seconds**. Do not confuse it with H2 `LOCK_TIMEOUT=500`, which is **500 milliseconds**.

## 5. Query timeout and statement cancellation: canceling an executing command

### 5.1. JDBC Statement#setQueryTimeout

`Statement#setQueryTimeout(int seconds)` asks the driver to limit how many seconds a statement is allowed to execute:

```java
JdbcTemplate template = new JdbcTemplate(dataSource);
template.setQueryTimeout(2);

template.queryForObject(
        "SELECT COUNT(*) FROM locked_account", Integer.class);
```

Fragment requiring `DataSource`. `JdbcTemplate.setQueryTimeout(2)` applies the timeout to statements created by the template, unless overridden by an active transaction deadline. **Spring's remaining transaction time typically takes precedence** when `JdbcTemplate` runs inside a transaction that has a timeout.

Notes:

- Drivers may round durations and use server-side or client-side cancellation; enforcement accuracy and error timing vary.
- `Statement.setQueryTimeout(0)` per JDBC typically means no JDBC-level query timeout limit, though it can still be bounded by a **server-side timeout** or **transaction deadline**.
- Statement/query timeout is not synonymous with lock timeout: a statement can hit query timeout because the query runs slowly (including lock waiting), whereas lock timeout counts only lock acquisition.
- If the database throws an error leaving the transaction aborted, you cannot simply catch it and keep querying normally.

### 5.2. Statement.cancel() is a cancellation request

JDBC has the API:

```java
// Fragment: controller thread holding a reference to a running Statement.
// Driver and database determine actual cancellation support.
statement.cancel();
```

This is a **non-standalone fragment**. Meaning:

- `cancel()` requests canceling an executing statement; there is no cross-driver guarantee that execution stops instantaneously.
- Some drivers send a cancel request to the DB server. Network latency and backend cleanup time may still occur.
- `statement.close()` and `connection.close()` must also not be treated as safe substitutes for transaction rollback without checking driver/pool behavior.
- After cancel, you may need to roll back the transaction and discard a broken connection; decisions depend on DB error state.

### 5.3. Future.cancel(true) / Thread.interrupt() does not reliably cancel JDBC

`Future.cancel(true)` attempts to interrupt the running thread if permitted, but **JDBC drivers are under no obligation to turn every thread interrupt into a SQL cancel**. The thread may remain blocked on a network read, or the DB may keep executing the query. If an HTTP request is closed by the client, the JDBC transaction does not necessarily stop on its own either.

When canceling running SQL is needed, configure multi-layer bounds and test with the real driver:

1. Appropriate DB-side statement/lock timeout.
2. JDBC `Statement.setQueryTimeout(...)` per statement.
3. Spring transaction timeout for the whole scope when starting a new transaction.
4. Connection/socket/network timeouts and circuit breaker/request timeouts in separate layers.
5. For active cancellation, use supported APIs and verify the backend actually ended the statement; then clean up the transaction/connection.

**Do not** automatically treat a Java Future's `CancellationException` as proof that SQL rolled back on the database.

### 5.4. JDBC and Spring exception taxonomy

| Phenomenon | Possible exception/diagnostic | Note |
| --- | --- | --- |
| Spring detects transaction deadline expired | `TransactionTimedOutException` | Can occur **before** the new SQL runs |
| JDBC statement timed out/canceled | `SQLTimeoutException` or `SQLException` | Error from driver; SQLState/error code varies by DB |
| Spring translates JDBC timeout | `QueryTimeoutException` or another `DataAccessException` subtype | Do not assert a fixed subtype across all DBs/drivers |
| Lock could not be acquired | `CannotAcquireLockException`, `PessimisticLockingFailureException`, other `DataAccessException` | Inspect root `SQLException` to see if lock error or other query error |
| Transaction marked rollback-only unexpectedly | `UnexpectedRollbackException` | Usually surfaces at outer commit, not the original lock timeout |
| Pool failed to lend a connection in time | Pool/driver exception | Does not mean SQL was waiting on a row lock |
| DB deadlock chose one transaction as victim | SQLState/vendor-specific exception | Different from merely waiting too long for a lock |

Spring does not guarantee a **single** exception class maps to a **single** SQL error across all backends. Use `SQLException.getSQLState()`, `getErrorCode()`, the exception chain, and logs to classify. Avoid logging raw SQL containing secrets/PII.

## 6. DBMS differences: where only the statement cancels vs. where the whole transaction aborts

### 6.1. H2: LOCK_TIMEOUT in milliseconds

H2 allows:

```sql
SET LOCK_TIMEOUT 500;
```

This sets a maximum lock wait of **500 ms** for the **current session**. It does not commit the transaction, and rollback does not automatically restore the session setting. It can be declared in the example's JDBC URL:

```properties
spring.datasource.url=jdbc:h2:mem:lock_lab;DB_CLOSE_DELAY=-1;LOCK_TIMEOUT=350
```

New connections in the demo are thus configured with a 350 ms lock-wait limit. When a statement cannot acquire a lock in time, H2 typically raises a `SQLException` with code `50200` (`LOCK_TIMEOUT_1`). Spring may translate it to a `DataAccessException` subtype; do not hardcode a Spring exception subtype.

**Caution:** manually changing session `SET LOCK_TIMEOUT` on a pooled connection can affect the next request if the setting is not reset. The example uses the URL to avoid per-session temporary changes inside business methods.

Docs: https://h2database.com/html/commands.html and https://h2database.com/javadoc/org/h2/api/ErrorCode.html

### 6.2. PostgreSQL: separate lock_timeout and statement_timeout

PostgreSQL has two important server-side settings:

```sql
-- Example while inside a PostgreSQL transaction.
SET LOCAL lock_timeout = '300ms';
SET LOCAL statement_timeout = '2s';
```

- `lock_timeout`: aborts a statement if **waiting to acquire one lock** takes too long; does not apply to CPU/IO time of other query phases.
- `statement_timeout`: bounds total server processing time for a statement, including lock waiting.
- `SET LOCAL` affects only the current transaction; avoids leaking session settings when using connection pools.
- When both are enabled, if `statement_timeout` is less than or equal to `lock_timeout`, statement timeout usually fires first; design thresholds sensibly.
- A SQL error in PostgreSQL normally leaves the current transaction in a **failed** state until rollback, unless a savepoint was used and handled properly. Catching `DataAccessException` and executing more SQL without rolling back usually keeps failing.
- Example SQLStates: `55P03` relates to `lock_not_available`, `57014` relates to `query_canceled`. Do not treat error codes as universal JDBC definitions across all DBs.

PostgreSQL also has `idle_in_transaction_session_timeout` to terminate sessions holding open idle transactions too long; modern versions also have server-side `transaction_timeout`. These settings **differ** from Spring `@Transactional(timeout=...)` and require checking docs for the exact deployed version.

Docs: https://www.postgresql.org/docs/current/runtime-config-client.html and https://www.postgresql.org/docs/current/errcodes-appendix.html

### 6.3. MySQL InnoDB: lock wait timeout usually rolls back only the statement

MySQL InnoDB has:

```sql
-- Example when using MySQL InnoDB:
SET SESSION innodb_lock_wait_timeout = 3;
```

`innodb_lock_wait_timeout` is in **seconds** and applies mainly to InnoDB row lock waits; defaults vary by application configuration. Typical error: `ERROR 1205 (HY000)`.

According to MySQL 8.4 docs, on a lock wait timeout:

- **By default**, InnoDB rolls back the **waiting statement**, not necessarily the **entire transaction**.
- If server setting `innodb_rollback_on_timeout` is enabled, the database can roll back the whole transaction.
- **Deadlocks** differ from lock wait timeouts: InnoDB typically detects deadlocks and rolls back the chosen victim transaction.
- Even if InnoDB only cancels the statement, if a `RuntimeException` **escapes through the Spring `@Transactional` proxy**, Spring rolls back the method's transaction by default. If the exception is caught **inside** the transactional method, the transaction might continue per InnoDB rules, though you must evaluate state and business invariants carefully.

Common mistake: reading "statement-only rollback" in the docs and concluding a Spring transactional method will commit all INSERTs prior to the lock timeout. That is **false by default** if the database error is translated by Spring into `DataAccessException` (unchecked) and escapes through the proxy.

Docs: https://dev.mysql.com/doc/refman/8.4/en/innodb-parameters.html and https://dev.mysql.com/doc/refman/8.4/en/innodb-error-handling.html

### 6.4. SQL Server: SET LOCK_TIMEOUT in session

SQL Server supports:

```sql
SET LOCK_TIMEOUT 500; -- 500 milliseconds
```

- `500` means wait for a lock for at most 500 **ms**.
- `0` means do not wait; `-1` is typically the default infinite wait.
- The setting is **session-scoped**, persisting until the session ends or is changed; pooled connections require reset handling.
- Lock timeout errors typically have code `1222`; check SQL Server docs/driver for exact exception types.
- Post-error transaction state must be checked appropriately with `XACT_STATE()`, `XACT_ABORT`, and code context; never assume you can continue and commit.

Docs: https://learn.microsoft.com/en-us/sql/t-sql/statements/set-lock-timeout-transact-sql

### 6.5. Practical comparison table

| Backend/mechanism | Config example | Unit | What to verify |
| --- | --- | --- | --- |
| H2 session lock wait | `SET LOCK_TIMEOUT 350` | ms | Error `50200`; is lock-holding transaction/connection still open? |
| PostgreSQL | `SET LOCAL lock_timeout='350ms'` | ms | Does transaction enter failed state? Which SQLState? |
| PostgreSQL statement | `SET LOCAL statement_timeout='2s'` | s/ms | Is statement canceled even when not waiting on a lock? |
| MySQL InnoDB | `innodb_lock_wait_timeout=3` | seconds | Default statement-only rollback and Spring interceptor effect |
| SQL Server | `SET LOCK_TIMEOUT 350` | ms | Session setting, transaction state, error 1222 |
| Spring `@Transactional(timeout=3)` | Annotation/manager | seconds | Does it open a new transaction? Do JDBC statements receive deadline? |
| Spring `JdbcTemplate.setQueryTimeout(3)` | JDBC statement | seconds | Does driver honor it? Does transaction deadline override it? |

Do not use this table as a copy/paste config sheet for all DBMSs. Even with the same numeric timeout value, **units and behavior can differ**; consult vendor/version documentation before deploying to production.

## 7. Runnable Java 17+ project: H2 lock timeout and Spring transaction timeout

This lab uses Spring Boot **3.5.6**, Java 17+, Spring JDBC, HikariCP, and a named in-memory H2 database. The test uses **two concurrent connections/transactions** rather than simulating on a single JDBC connection.

**Outcomes to prove:**

1. Writer acquires a row lock without committing; contender waits past 350 ms and fails with H2 code `50200`.
2. Writer rolls back; contender's UPDATE was canceled and the committed balance remains `100`.
3. A separate transaction with `@Transactional(timeout=1)` INSERTs a row and then sleeps over one second in Java. On the next `JdbcTemplate` call, Spring detects the expired deadline and throws `TransactionTimedOutException`; the prior INSERT rolls back.
4. No need to measure exact OS timing or assert a fixed `DataAccessException` subtype; verify **H2's root SQL code**, transaction outcome, and final data.

### 7.1. Project structure

```text
lock-timeout-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── TimeoutApplication.java
    │   │   ├── LockOwnerService.java
    │   │   ├── LockContenderService.java
    │   │   ├── LockExperiment.java
    │   │   └── DeadlineService.java
    │   └── resources/
    │       ├── application.properties
    │       ├── schema.sql
    │       └── data.sql
    └── test/
        └── java/demo/
            └── TimeoutIntegrationTest.java
```

### 7.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>lock-timeout-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Spring Boot manages compatible dependencies and auto-configures `DataSource`, `JdbcTemplate`, and the JDBC transaction manager. `spring-boot-starter-test` enables JUnit 5/Spring Boot Test.

### 7.3. application.properties and schema/data

**`src/main/resources/application.properties`**

```properties
spring.datasource.url=jdbc:h2:mem:lock_lab;DB_CLOSE_DELAY=-1;LOCK_TIMEOUT=350
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=5
spring.main.banner-mode=off
app.demo.enabled=true
```

`LOCK_TIMEOUT=350` is H2's **350 ms**, not a Spring transaction deadline. Pool max size 5 ensures that while writer holds one connection locking the row, contender gets a second connection to truly experience lock contention. A named H2 URL allows multiple connections to access **one** shared in-memory database.

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE IF NOT EXISTS locked_account (
    id BIGINT PRIMARY KEY,
    balance INT NOT NULL
);
```

**`src/main/resources/data.sql`**

```sql
INSERT INTO locked_account (id, balance) VALUES (1, 100);
```

Spring Boot initializes schema/data in embedded H2 before `CommandLineRunner` executes. Here there is only one initial row `id=1`. The transaction timeout case uses `id=2`, which rolls back, leaving no permanent extra row.

### 7.4. LockOwnerService.java — hold lock then roll back

**`src/main/java/demo/LockOwnerService.java`**

```java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class LockOwnerService {
    private final JdbcTemplate jdbc;

    public LockOwnerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void holdAndRollback(
            CountDownLatch locked,
            CountDownLatch release) {

        // FOR UPDATE acquires lock before notifying contender.
        jdbc.queryForObject(
                "SELECT balance FROM locked_account WHERE id = 1 FOR UPDATE",
                Integer.class);

        jdbc.update(
                "UPDATE locked_account SET balance = 200 WHERE id = 1");

        // Transaction is still open, not yet committed/rolled back.
        locked.countDown();

        try {
            if (!release.await(15, TimeUnit.SECONDS)) {
                throw new IllegalStateException("owner wait expired");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("owner interrupted", ex);
        }

        // Throw exception out through proxy => rolls back update 200.
        throw new IllegalStateException("owner rollback");
    }
}
```

`holdAndRollback` runs on a **worker thread**, yet still passes through the Spring proxy because `LockOwnerService` is injected from the Spring container. The transaction is created on the worker thread, holding its connection and row lock until `release` is signaled.

`CountDownLatch` guarantees contender starts **only after writer acquired the lock**. Using unsynchronized `Thread.sleep(...)` could let the test run before writer locks the row, causing flaky results.

### 7.5. LockContenderService.java — attempt to update the locked row

**`src/main/java/demo/LockContenderService.java`**

```java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class LockContenderService {
    private final JdbcTemplate jdbc;

    public LockContenderService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void updateLockedRow() {
        // On another connection, row id=1 is still locked by owner transaction.
        jdbc.update(
                "UPDATE locked_account SET balance = 300 WHERE id = 1");
    }
}
```

Contender is called from the main thread with no outer transaction. It opens its own transaction/connection. When H2 cannot acquire the lock within 350 ms, JDBC throws an error. `JdbcTemplate` translates `SQLException` to `DataAccessException`; because it is unchecked and escapes the transactional interceptor, Spring rolls back contender's transaction.

Note: verification in `LockExperiment` checks for **H2 error code 50200 in the SQLException cause chain**, without pinning a specific Spring exception subtype since translators can vary by driver or version.

### 7.6. LockExperiment.java — coordinate two independent transactions

**`src/main/java/demo/LockExperiment.java`**

```java
package demo;

import java.sql.SQLException;
import java.util.Objects;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
public class LockExperiment {
    private final LockOwnerService owner;
    private final LockContenderService contender;
    private final JdbcTemplate jdbc;

    public LockExperiment(
            LockOwnerService owner,
            LockContenderService contender,
            JdbcTemplate jdbc) {
        this.owner = owner;
        this.contender = contender;
        this.jdbc = jdbc;
    }

    public record Result(boolean lockTimedOut, int committedBalance) {}

    public Result run() throws Exception {
        CountDownLatch locked = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            Future<?> ownerTask = executor.submit(
                    () -> owner.holdAndRollback(locked, release));

            if (!locked.await(6, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "owner did not acquire lock");
            }

            boolean timedOut = false;

            try {
                contender.updateLockedRow();
            } catch (DataAccessException ex) {
                // H2 LOCK_TIMEOUT_1: error code 50200.
                // Do not swallow unrelated SQL errors.
                if (!hasH2LockTimeoutCode(ex)) {
                    throw ex;
                }
                timedOut = true;
            } finally {
                // Release owner even if contender errored to avoid hanging worker.
                release.countDown();
            }

            try {
                ownerTask.get(8, TimeUnit.SECONDS);
                throw new IllegalStateException(
                        "owner completed without rollback");
            } catch (ExecutionException ex) {
                Throwable cause = ex.getCause();
                if (!(cause instanceof IllegalStateException)
                        || !"owner rollback".equals(cause.getMessage())) {
                    throw ex;
                }
            }

            Integer balance = jdbc.queryForObject(
                    "SELECT balance FROM locked_account WHERE id = 1",
                    Integer.class);

            return new Result(
                    timedOut,
                    Objects.requireNonNull(balance));
        } finally {
            release.countDown();
            executor.shutdownNow();
        }
    }

    private static boolean hasH2LockTimeoutCode(Throwable error) {
        for (Throwable current = error;
                current != null;
                current = current.getCause()) {
            if (current instanceof SQLException sql
                    && sql.getErrorCode() == 50200) {
                return true;
            }
        }
        return false;
    }
}
```

Logic notes:

1. `executor` starts thread W. Bean `owner` runs in transaction W and locks `id=1`.
2. `locked.await(...)` waits until the lock is acquired, preventing a race between writer and contender.
3. Main thread calls `contender.updateLockedRow()`, so contender's `JdbcTemplate` must borrow another connection from the Hikari pool.
4. After waiting past 350 ms, H2 throws `SQLException` error `50200`, which Spring translates to `DataAccessException`.
5. `catch` checks the real cause; if it is any other SQL error, it **is rethrown** and the demo fails rather than reporting a false pass.
6. `release.countDown()` always runs so owner proceeds and throws its intentional exception. `Future.get` confirms the exact `owner rollback` exception, meaning owner's transaction finished through the proxy.
7. Only **after both transactions finish** is `balance` queried. By then owner rolled back 200 and contender failed to write 300, so committed balance is 100.
8. `shutdownNow()` in `finally` cleans up the executor. Both latches and timeouts prevent the lab from hanging indefinitely on failure.

**Experiment limitation:** never hold a database transaction open with a latch in real business code; that is a **concurrency-verification technique**, deliberately keeping the transaction holding its lock long enough for contender to wait.

### 7.7. DeadlineService.java — Spring transaction timeout before next SQL

**`src/main/java/demo/DeadlineService.java`**

```java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DeadlineService {
    private final JdbcTemplate jdbc;

    public DeadlineService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(timeout = 1)
    public void expireBeforeNextStatement(long id) {
        jdbc.update(
                "INSERT INTO locked_account (id, balance) VALUES (?, ?)",
                id, 800);

        try {
            // Demo holds Java code longer than the 1-second transaction deadline.
            // Spring does not auto-interrupt Thread.sleep just from the annotation.
            Thread.sleep(1800);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("deadline demo interrupted", ex);
        }

        // JdbcTemplate creates a new statement and checks remaining deadline.
        // Deadline expired -> typically TransactionTimedOutException.
        jdbc.update(
                "UPDATE locked_account SET balance = ? WHERE id = ?",
                801, id);
    }
}
```

In this method:

- Spring `@Transactional(timeout=1)` creates a new transaction because the caller has no outer transaction.
- The first `INSERT` runs before the deadline, yet **has not committed**.
- `Thread.sleep(1800)` is not SQL; it simply lets wall-clock time pass. No "timeout daemon" wakes the thread right at 1 second.
- When `JdbcTemplate` creates the next UPDATE statement, `DataSourceUtils` sees the deadline has passed and throws `TransactionTimedOutException`.
- The exception exits through the transaction interceptor, causing rollback, so `INSERT id=2` **is no longer** in the database.

This demo deliberately triggers timeout **before executing the next statement** to distinguish Spring's transaction deadline from database lock wait timeouts. It does not prove drivers can interrupt every running SQL command precisely on time.

### 7.8. TimeoutApplication.java — run and read committed results

**`src/main/java/demo/TimeoutApplication.java`**

```java
package demo;

import java.util.Objects;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.TransactionTimedOutException;

@SpringBootApplication
public class TimeoutApplication {
    public static void main(String[] args) {
        SpringApplication.run(TimeoutApplication.class, args);
    }

    @Bean
    @ConditionalOnProperty(
            name = "app.demo.enabled",
            havingValue = "true",
            matchIfMissing = true)
    CommandLineRunner demo(
            LockExperiment experiment,
            DeadlineService deadlines,
            JdbcTemplate jdbc) {

        return args -> {
            LockExperiment.Result result = experiment.run();

            System.out.println(
                    "H2 lock timeout observed: " + result.lockTimedOut());
            System.out.println(
                    "balance after owner rollback: "
                            + result.committedBalance());

            boolean transactionTimedOut = false;

            try {
                deadlines.expireBeforeNextStatement(2L);
            } catch (TransactionTimedOutException ex) {
                transactionTimedOut = true;
            }

            System.out.println(
                    "Spring tx timeout observed: " + transactionTimedOut);

            Integer count = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM locked_account WHERE id = 2",
                    Integer.class);

            System.out.println(
                    "row 2 after timeout: "
                            + (Objects.requireNonNull(count) == 0
                                    ? "absent" : "present"));
        };
    }
}
```

In the demo, `CommandLineRunner` has no `@Transactional`. Thus:

- `LockOwnerService` and `LockContenderService` each own their own transaction across two threads.
- `DeadlineService.expireBeforeNextStatement` owns a transaction with a 1-second deadline.
- The SELECT queries in `LockExperiment`/`TimeoutApplication` run **after the transactions have ended**, not reading uncommitted data on the same connection.

`@ConditionalOnProperty` disables the runner during integration tests so tests do not trigger concurrency experiments automatically on application context startup.

### 7.9. Run command and expected stdout

Requires JDK 17+, Maven 3.6.3+, and dependencies available locally or downloadable. In the directory containing `pom.xml`:

```bash
mvn spring-boot:run
```

Lines printed by the application itself, excluding Spring/Maven logs:

```text
H2 lock timeout observed: true
balance after owner rollback: 100
Spring tx timeout observed: true
row 2 after timeout: absent
```

Comparison table:

| Observation | Why? |
| --- | --- |
| `H2 lock timeout observed: true` | Contender could not acquire row lock within 350 ms; root SQL has H2 code `50200` |
| `balance after owner rollback: 100` | Owner rolled back temporary value 200; contender never succeeded on UPDATE 300 |
| `Spring tx timeout observed: true` | 1-second transaction deadline expired before the next JDBC UPDATE; Spring threw `TransactionTimedOutException` |
| `row 2 after timeout: absent` | INSERT id=2 belonged to the rolled-back transaction |

**Limitation:** the output above is the **expected design behavior with the stated H2/Spring/JDK**, not an empirically captured stdout log at the time of writing. Differences in OS scheduling, overloaded CPUs, driver versions, and pools may require adjusting latch timeouts or reducing test environment load. However, the demo does not rely on contender "just barely" racing for the lock: the latch guarantees owner locked the row before contender starts.

## 8. Integration test verifying transaction and SQL errors

**`src/test/java/demo/TimeoutIntegrationTest.java`**

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.TransactionTimedOutException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(properties = "app.demo.enabled=false")
class TimeoutIntegrationTest {
    @Autowired
    private LockExperiment experiment;

    @Autowired
    private DeadlineService deadlines;

    @Autowired
    private JdbcTemplate jdbc;

    @Test
    void lockWaitTimesOutAndBothTransactionsLeaveOriginalValue()
            throws Exception {

        LockExperiment.Result result = experiment.run();

        assertTrue(result.lockTimedOut());
        assertEquals(100, result.committedBalance());
    }

    @Test
    void springTransactionDeadlineRollsBackPreviousInsert() {
        assertThrows(
                TransactionTimedOutException.class,
                () -> deadlines.expireBeforeNextStatement(20L));

        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM locked_account WHERE id = 20",
                Integer.class);
        assertEquals(0, count);
    }
}
```

Run:

```bash
mvn test
```

**Expectation:** both tests pass on H2 with this configuration. The test uses ID=20 to avoid colliding with the runner's ID=2 (even though the runner is disabled via `app.demo.enabled=false`).

**Why not put `@Transactional` on the test class?** If Spring TestContext opens a test-managed transaction, `REQUIRED` services can **join the test transaction**, changing deadlines and rollback boundaries. Worse, the lock contention test could accidentally share the lock-holding transaction/connection. Tests are therefore invoked from a caller **without an outer transaction**, matching the demo design.

### Verifying lock errors are not confused with other SQL errors

Instead of merely:

```java
assertThrows(DataAccessException.class, () -> contender.updateLockedRow());
```

the lesson uses `hasH2LockTimeoutCode` to find `SQLException.getErrorCode()==50200` in the cause chain. Because `DataAccessException` can represent many SQL errors (syntax, constraints, connections), asserting a broad subtype alone creates **false positives**.

This does not mean production code should hardcode H2 codes. In real systems, inspect vendor error codes/SQLState, build backend-specific classification strategies, and log root causes safely.

### Testing after rollback matters more than merely asserting timeout

If a method throws `TransactionTimedOutException` and you never SELECT afterward, the test only proved an exception occurred, not that prior mutations rolled back. Here we assert `id=20` **is absent** after the proxy invocation to prove the transaction completed according to rollback policy.

## 9. Retry: retry in a new transaction, never mask an existing failure

When a lock wait timeout or deadlock occurs, certain idempotent tasks can retry. However, retries must **not** be placed carelessly inside an already-errored transaction or one marked rollback-only.

### 9.1. Sound retry flow

```text
Request
   |
   +-- Attempt 1: create new transaction
   |      UPDATE ... -> lock timeout
   |      roll back transaction
   |
   +-- short backoff + jitter
   |
   +-- Attempt 2: create new transaction
   |      UPDATE ... -> succeeds
   |      commit
   |
   +-- return result
```

Conditions:

- Each attempt should cross a **separate transaction proxy**, or use `TransactionTemplate` to start a new transaction per attempt.
- With DBs that abort transactions (such as PostgreSQL after a SQL error), **never retry SQL inside the same aborted transaction**.
- Retry only errors classified as transient (appropriate lock timeout/deadlock), never syntax errors or business errors unfixable by waiting.
- Set a **maximum attempt count**, backoff/jitter, and overall request budget; never retry infinitely.
- Require **idempotency**: do not send duplicate emails, money transfers, or events if a prior attempt had external side effects outside the DB.
- If a transaction commit actually succeeded while the response was lost, do not blindly retry from scratch without checking an idempotency key.

### 9.2. Boundary-correct pseudocode example

```java
// Pseudocode: not a standalone Java class.
for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
        // worker is another Spring bean with a @Transactional method.
        worker.performOneTransaction();
        break;
    } catch (TransientDataAccessException ex) {
        if (attempt == maxAttempts) {
            throw ex;
        }
        backoffWithJitter(attempt);
    }
}
```

This illustrates placing retries **outside the transactional method**. `TransientDataAccessException` is a useful Spring exception family to consider, though **not every** subtype is retryable and vendor translators do not always classify consistently. `maxAttempts`, `backoffWithJitter`, and `worker` must be implemented per application.

If using `@Retryable`, you must install/enable Spring Retry and ensure AOP advice ordering so each retry attempt genuinely starts a new transaction. The lab does not include the Spring Retry dependency, so do not assume that annotation works just by copying code.

## 10. Multi-layer timeout strategy in practice

A configuration set should make **time budgets and their relationships** explicit. For example, an API with roughly a 5-second total budget:

| Layer | Budget example | Meaning |
| --- | --- | --- |
| Pool acquisition | 0.5 seconds | Do not wait too long for a connection |
| DB lock wait | 0.7 seconds | Fail fast if a row is locked too long |
| DB/JDBC statement | 2 seconds | Bound slow statements in general |
| Spring transaction | 4 seconds | Overall deadline for a new transaction |
| HTTP request | 5 seconds | Caller/client budget |

This is only a **design example**, not a universal standard. What matters is keeping timeouts coherent and understanding **how time is measured**: a DB-side deadline can control actual execution better than a timeout checked only when Java creates a new statement; network timeouts concern sockets, not rollback rules.

Never simply add up thresholds into a hard SLA if the driver does not support timely cancellation. Measure p95/p99 latency, blocked time, lock graphs, pool wait, and commit latency in real environments.

### Principles to reduce lock contention before raising timeouts

1. Keep transactions **short**; do not wait for HTTP/network/user input while holding row locks.
2. Ensure UPDATE/`SELECT FOR UPDATE` use appropriate indexes; queries scanning many rows can hold more locks than expected.
3. Keep consistent lock ordering across flows to reduce deadlocks.
4. For long jobs, split into sensible batches and document atomicity rules.
5. Use appropriate isolation; never downgrade isolation just to reduce blocking without checking correctness.
6. Use optimistic locking/versioning when business semantics allow, instead of always holding pessimistic locks.
7. For queue workers, consider `SKIP LOCKED`/`NOWAIT` if supported by the vendor and skipping work fits semantics.
8. Monitor slow-query logs, deadlock logs, lock wait metrics, and transaction hold times.

## 11. Common failure scenarios

### 11.1. @Transactional(timeout=1) does not interrupt Thread.sleep(10s)

**Cause:** Spring transaction timeout is a deadline/resource timeout, not a Java watchdog interrupting code. `JdbcTemplate` detects expiration at the next statement. If a method just sleeps and returns, do not infer a hard timeout canceled it.

**How to verify:** In tests, invoke a JDBC statement after the deadline expired; verify both the exception and database rollback, as in `DeadlineService`.

### 11.2. Query timeout configured yet SQL keeps running long

**Possible causes:** Driver/backend lacks proper cancellation support, the statement is stuck on network/commit, or application logic runs outside SQL. Some timeouts are rounded to whole seconds.

**How to handle:** Inspect driver/server logs, JDBC `Statement#setQueryTimeout`, DB-side `statement_timeout`, network timeouts, and test realistic cases. Never promise SQL always halts at the exact timer mark.

### 11.3. Lock timeout caught inside a transactional method and still committed

**Cause:** InnoDB by default may roll back only the timed-out statement. If the exception is caught before reaching the transaction interceptor and the backend lets work continue, Spring sees a normal return and may commit earlier work.

**How to handle:** For lock errors on atomic write paths, usually let the exception escape the boundary or explicitly mark rollback-only and handle in the caller. PostgreSQL in particular enters a failed transaction state after an error and cannot continue without proper rollback/savepoint.

### 11.4. Inner REQUIRED has a short timeout that never takes effect

**Cause:** Inner joins the physical transaction opened by outer. Inner's timeout does not automatically alter outer's deadline.

**How to handle:** Put the timeout on the boundary owning the transaction, or set a query timeout for the operation; consider a new transaction only when business rules genuinely allow it.

### 11.5. Two tests do not actually use two connections

If reader/contender run inside the same transaction or on the same JDBC connection as writer, they may not wait on their own lock. Use two threads, two Spring proxy invocations, and a pool of at least two connections, as in the demo; verify transaction boundaries and data.

### 11.6. Right number, wrong unit

`@Transactional(timeout=3)` is **3 seconds**; H2 `SET LOCK_TIMEOUT 300` is **300 ms**; MySQL `innodb_lock_wait_timeout=3` is **3 seconds**; SQL Server `SET LOCK_TIMEOUT 300` is **300 ms**. Wrong units make requests wait far too long or fail prematurely.

### 11.7. Catching all DataAccessException and retrying every error

Syntax, constraint, permission, and schema errors are not solved by waiting. Classify by SQLState/vendor code and assess retryability; retry in a new transaction, bounded and idempotent.

### 11.8. Suspecting deadlock when it is only a lock wait timeout

Deadlocks require a wait cycle between transactions; a lock wait timeout may just be transaction A holding a lock too long while B waits in one direction. Inspect lock graphs/deadlock logs and root SQL error codes; do not change algorithms merely because a message contains the word "lock."

### 11.9. Looking only at the exception without inspecting final data

A statement timeout might cancel only the statement on the DB; a new transaction might be rolled back by Spring if an unchecked exception escapes; or an errored transaction might be marked rollback-only. Wait for the outermost transaction to finish and SELECT from a fresh connection/transaction.

### 11.10. Misinterpreting a canceled future as rolled back

`Future.cancel(true)` or client disconnect does not guarantee SQL/the database stopped executing. Real JDBC/DB cancellation/timeouts, completion tracking, and rollback boundaries are required.

### 11.11. Logging every timeout as QueryTimeoutException

Spring JDBC exception translators depend on driver/SQLState/errorCode; H2 lock timeouts may translate differently from PostgreSQL or MySQL. Log the root cause and which timeout applied. `TransactionTimedOutException` is also **not** a generic JDBC `DataAccessException` for query errors.

### 11.12. Changing session timeouts on pooled connections without resetting

PostgreSQL `SET`, SQL Server `SET LOCK_TIMEOUT`, and H2 `SET LOCK_TIMEOUT` can stick to the session/connection. Reusing a pooled connection can leak old settings to subsequent requests. Use `SET LOCAL` inside transactions when supported, or pool initialization/reset hooks.

### 11.13. Using test @Transactional creating an unintended outer transaction

Spring TestContext opens a test-managed transaction when `@Transactional` is placed on a test. `REQUIRED` services join that test transaction, shifting timeouts and commit boundaries. The demo and tests here **do not** annotate the test class with `@Transactional`.

### 11.14. Lock held even after contender times out

The **owner** transaction's lock can persist even after contender times out. If owner fails to commit/roll back, subsequent requests keep getting blocked. Monitor and resolve the **lock-holding transaction**, not just waiting transactions.

## 12. Production diagnostic workflow

When receiving a timeout/cancel exception:

1. **Record timestamp and request correlation ID.** Avoid logging credentials, sensitive info, or full bind parameters unless necessary.
2. **Classify the layer:** pool connection exhaustion, lock wait timeout, statement/query timeout, Spring transaction deadline, network failure, or deadlock?
3. **Extract root SQLException:** `getSQLState()`, `getErrorCode()`, original message; match against SQLState/vendor error mappings.
4. **Check actual transaction manager:** `DataSourceTransactionManager`/`JpaTransactionManager`/JTA? How many DataSources and managers exist?
5. **Confirm proxy boundary/propagation:** did `@Transactional` actually go through the proxy? Did inner `REQUIRED` join outer? Was timeout set on the owning scope?
6. **Check server/session settings:** PostgreSQL `lock_timeout`/`statement_timeout`, MySQL InnoDB timeout, SQL Server session `LOCK_TIMEOUT`, H2 `LOCK_TIMEOUT`.
7. **Check statement settings:** `JdbcTemplate.setQueryTimeout`, JDBC `Statement.setQueryTimeout`, and remaining time propagated by Spring.
8. **Inspect lock hold times:** which transaction holds locks, which statements are waiting, query plans/indexes, and idle transactions.
9. **Determine post-error state:** DB transaction failed/aborted? Spring transaction rollback-only? Can a statement retry or must the whole transaction roll back?
10. **Read committed state after boundary:** check the exact database/tenant/schema, not stale JPA cache or lagging read replicas.
11. **Design recovery:** bounded retry in a new transaction, backoff, idempotency, or returning an appropriate business error.
12. **Add regression tests** on the exact production DB/driver version, not just H2.

For Spring Boot, diagnostic logging can be enabled in test environments:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
logging.level.org.springframework.jdbc.core=DEBUG
```

Spring logs help verify scope and SQL execution, yet actual lock waits usually require **DB-side lock views / slow query logs / deadlock diagnostics**. Do not leave DEBUG/TRACE enabled indefinitely in production if it logs SQL/bind values or adds overhead.

## 13. Questions and exercises

**Exercise 1 — Which timeout?** A holds `SELECT ... FOR UPDATE` on id=1 for 10 seconds. B tries to UPDATE id=1 with DB lock timeout 500 ms. B errors after ~0.5 seconds. Did Spring `@Transactional(timeout=...)` expire?

**Answer:** You cannot conclude that. This is a DB **lock wait timeout**; Spring's transaction timeout may be larger or unconfigured.

**Exercise 2 — Does canceling a statement roll back the whole transaction?** MySQL InnoDB times out waiting on a row lock; the exception is caught inside `@Transactional` and the method returns normally.

**Answer:** InnoDB defaults to rolling back only the timed-out statement; if the transaction can continue and the Spring interceptor sees a normal return, prior successful SQL may commit. You must check `innodb_rollback_on_timeout`, transaction state, and business intent.

**Exercise 3 — Exception escaping proxy:** The same InnoDB error is translated by Spring to `DataAccessException` and exits the transactional method uncaught. What does Spring typically do?

**Answer:** Per default rollback rules for unchecked exceptions, Spring rolls back the method's transaction when it owns the transaction. Spring's behavior is not limited to the DB's statement-only rollback.

**Exercise 4 — Long sleep:** Method `@Transactional(timeout=1)` only calls `Thread.sleep(5000)` and returns, executing no JDBC statements. Will Spring definitely interrupt the thread at second 1?

**Answer:** No. `@Transactional(timeout)` is not a Java thread watchdog; deadlines are typically checked/applied when resource operations execute.

**Exercise 5 — JDBC query timeout:** Does `JdbcTemplate.setQueryTimeout(2)` mean the same as `@Transactional(timeout=2)`?

**Answer:** No. Query timeout limits each individual SQL statement at the JDBC driver; transaction timeout is the deadline of a new scope and can be propagated as query timeout **for the remaining time**.

**Exercise 6 — Statement.cancel():** Is `Future.cancel(true)` guaranteed to make the database roll back running SQL?

**Answer:** No. Java interrupts and JDBC/backend cancel requests differ. Supported SQL cancellation and proper rollback/cleanup management are needed.

**Exercise 7 — REQUIRED:** Outer transaction has a 20-second deadline; inner `REQUIRED` declares `timeout=2`. Does inner automatically apply 2 seconds?

**Answer:** Not when inner merely joins the outer physical transaction. Timeout metadata primarily takes effect when starting a new transaction.

**Exercise 8 — H2 50200:** In the lab, what error does catching `DataAccessException` and checking root `SQLException.getErrorCode()==50200` avoid?

**Answer:** It avoids confusing arbitrary SQL errors (syntax, constraints, connections) with lock timeouts. When deploying to another DB, use dedicated mappings rather than hardcoding H2 codes globally.

**Exercise 9 — Deadlock:** T1 holds row A waiting for B; T2 holds B waiting for A. Is this just a one-way lock wait?

**Answer:** No, this is a deadlock cycle. The engine usually picks one transaction as victim; a dedicated deadlock retry strategy is required rather than reasoning purely from wait duration.

**Exercise 10 — Client request ends:** An HTTP client closes the connection at second 2 while a JDBC statement is still running. Will the SQL command definitely cancel?

**Answer:** No. Request timeout/disconnect does not guarantee SQL cancellation. Explicit JDBC/DB timeout/cancel boundaries and transaction cleanup are required.

**Exercise 11 — Session settings:** Why does `SET LOCK_TIMEOUT 500` on SQL Server/H2 require care in a connection pool?

**Answer:** It is a session-scoped setting that can affect subsequent uses of the pooled connection if not reset. Prefer pool-safe config or DB transaction-scoped mechanisms when supported.

**Exercise 12 — Proof of rollback:** Why must the demo case SELECT after `ownerTask.get(...)` instead of SELECTing while owner still holds the transaction?

**Answer:** Only after owner's proxy finishes rolling back do we know the committed state. Reading inside an open transaction or on the same connection can see uncommitted temporary changes.

## 14. Official References

- Spring Framework — **Using @Transactional**, `timeout` and propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — **Controlling Database Connections**, transaction timeout applied to JDBC statements: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
- Spring Framework — `DataSourceUtils` Javadoc, `applyTransactionTimeout` and `applyTimeout`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html
- Spring Framework — `TransactionTimedOutException` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/TransactionTimedOutException.html
- Spring Framework — `JdbcTemplate` Javadoc (`setQueryTimeout`): https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Java 17 JDBC — `Statement` (`setQueryTimeout`, `cancel`): https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Statement.html
- H2 — SQL `SET LOCK_TIMEOUT` and millisecond scope: https://h2database.com/html/commands.html
- H2 — `ErrorCode.LOCK_TIMEOUT_1` (50200): https://h2database.com/javadoc/org/h2/api/ErrorCode.html
- PostgreSQL — runtime `lock_timeout` and `statement_timeout`: https://www.postgresql.org/docs/current/runtime-config-client.html
- PostgreSQL — SQLSTATE error codes: https://www.postgresql.org/docs/current/errcodes-appendix.html
- MySQL 8.4 — InnoDB error handling: https://dev.mysql.com/doc/refman/8.4/en/innodb-error-handling.html
- MySQL 8.4 — `innodb_lock_wait_timeout` / `innodb_rollback_on_timeout`: https://dev.mysql.com/doc/refman/8.4/en/innodb-parameters.html
- Microsoft SQL Server — `SET LOCK_TIMEOUT`: https://learn.microsoft.com/en-us/sql/t-sql/statements/set-lock-timeout-transact-sql

**Remember:** **Lock timeout** is a database-enforced lock-wait limit; **Spring transaction timeout** is a deadline set when Spring creates a new transaction and integrated down to JDBC statements per supported mechanisms; **statement timeout/cancel** attempts to stop a SQL statement without automatically guaranteeing every part of the transaction rolled back. Always check **transaction boundaries**, **root causes**, **DB state after errors**, and **committed data after transactions finish**.