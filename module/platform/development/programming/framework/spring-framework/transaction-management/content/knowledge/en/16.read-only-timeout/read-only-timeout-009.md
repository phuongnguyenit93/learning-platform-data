# Consistently Choosing Transaction, Query, and Connection Timeouts

## 1. Practical Problem: Why Do Requests Still Hang After Setting Timeouts?

A Spring request typically passes through several phases: waiting to acquire a JDBC connection from the pool, starting a transaction, waiting for database locks, executing one or more SQL statements, calling external services, committing/rolling back, and sending the response. Each phase has one or more timeout mechanisms, each with its **own unit, starting point, scope, and error handling**.

For example: a service sets `@Transactional(timeout = 5)` while the connection pool allows waiting up to 30 seconds. If a request already spent significant time **before the physical transaction was initialized**, the transaction timeout attribute is not an end-to-end deadline starting the moment the HTTP request arrived. One timeout type does not automatically substitute for another.

Another example: `JdbcTemplate.setQueryTimeout(2)` is configured, yet the method runs inside a transaction with its own timeout. Spring JDBC has logic that **applies remaining transaction time to the JDBC statement and can override the query timeout configured on `JdbcTemplate`**. You cannot assume by default that the two values always resolve to `min(2, transactionRemaining)` across every code path.

This lesson explains how to **design a consistent time budget** across transactions, SQL queries, lock waits, pool connection acquisition, TCP connect, socket reads, request/HTTP deadlines, and retries. The focus is **Spring Framework 6.x, imperative JDBC/JPA, Java 17+**, with attention to Spring Boot/HikariCP and PostgreSQL. There is no single number "right for every application": it must be based on SLOs, real latency, database/provider, and retry safety.

### Objectives

After this lesson, you will be able to:

1. State accurately what is measured by `@Transactional(timeout)`, `Statement.setQueryTimeout`, and HikariCP `connectionTimeout`.
2. Distinguish connection-pool wait timeout from TCP connection establishment timeout and socket read wait.
3. Design a time budget from the outer request down to individual SQL without omitting pool/lock waits.
4. Understand why Spring JDBC can **prioritize remaining transaction timeout** over `JdbcTemplate`'s local timeout.
5. Choose database timeout settings as a proper safeguard rather than relying solely on client-side query cancellation.
6. Avoid relying on an inner `REQUIRED` annotation to "reset" a timeout already started in an outer transaction.
7. Handle timeout/rollback/retry at the proper transaction boundary.
8. Verify with integration tests and metrics to identify **which layer actually timed out**.

## 2. Six Timeouts Easily Mislabeled as "Database Timeout"

| Timeout Type | When Does Measurement Start? | What Is Bounded? | Common Unit | Does Not Cover |
| --- | --- | --- | --- | --- |
| **Request/application deadline** | When the application receives or starts processing the request | Total time serving a business request | ms | Automatically stopping running SQL without cancellation |
| **Pool acquisition timeout** | When thread calls `DataSource.getConnection()` and pool cannot yet provide a connection | Time **waiting for a connection from the pool** | ms, e.g. Hikari `connectionTimeout` | Not TCP connect timeout; does not limit SQL after borrowing a connection |
| **TCP connect/login timeout** | When driver establishes physical connection to database | Connection setup/handshake per driver | s or ms depending on driver | Does not limit queries on an already open connection |
| **Transaction timeout** | When Spring transaction manager begins/guards a new transaction | Transaction budget (and how it is checked/applied to resources) | s, `@Transactional(timeout = 5)` | Not a Java watchdog interrupting every line of code at exact 5s |
| **SQL/statement timeout** | When a statement executes, per JDBC/DB semantics | SQL statement/query duration or DB processing wait | JDBC seconds, PostgreSQL `statement_timeout` ms | Does not limit the whole HTTP request, nor necessarily connection acquisition |
| **Lock wait timeout** | When SQL requests a lock and encounters contention | Time waiting to be granted the lock | ms/s depending on database | Does not limit execution that is not waiting for locks |

Two very different limits also need to be distinguished:

- **Network/socket read timeout**: the driver limits time waiting for data from the socket; can cause **the connection to close**, rather than a clean business-level query cancellation.
- **Idle-in-transaction timeout**: some databases terminate a session to prevent transactions left idle with no SQL commands; it is not equivalent to total transaction timeout.

### 2.1. Phase Timeline Diagram

```mermaid
flowchart LR
    A["HTTP request starts"] --> B["Pre-processing"]
    B --> C["Pool: wait for connection"]
    C --> D["Start / join DB transaction"]
    D --> E["Wait for row lock"]
    E --> F["Execute SQL"]
    F --> G["Subsequent business logic"]
    G --> H["Commit / rollback"]
    H --> I["HTTP response"]
```

- Request deadline covers or coordinates overall **A → I**.
- Pool acquisition timeout primarily constrains **C**.
- Transaction timeout attaches to the transaction resource created/managed by the manager, typically covering work from transaction begin to completion.
- Statement timeout covers each SQL execution; lock wait can be part of statement time.
- TCP connect/socket timeouts are **driver/network limits**, not business transaction policies.

**Do not mechanically add** every timeout together and treat that as maximum request latency: some layers are **nested inside** others, some start counting at different moments, and some are not enforced by a strict wall-clock timer.

## 3. `@Transactional(timeout = N)`: Exact Scope and Limits

### 3.1. The Unit Is Seconds

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class LedgerService {
    @Transactional(timeout = 5)
    public void postEntry() {
        // Transaction timeout set to 5 seconds.
    }
}
```

This is a snippet of a Spring bean. `timeout = 5` is in **seconds**, not milliseconds; `timeoutString`, if using config expressions, is also interpreted per the API attribute. The timeout value belongs to `TransactionDefinition` and is applied by the transaction manager when actually **creating a new transaction**.

For the annotation call to work in proxy mode, the caller must go through the Spring-managed proxy; `this.postEntry()` from the same bean normally creates no separate boundary. You cannot look at the annotation in source and conclude the timeout is applied.

### 3.2. `REQUIRED` Joining an Existing Transaction Does Not Create a New Budget

```java
@Service
public class OrderService {
    private final AuditService audit;

    public OrderService(AuditService audit) {
        this.audit = audit;
    }

    @Transactional(timeout = 8)
    public void place() {
        audit.save();  // Default Propagation.REQUIRED.
    }
}

@Service
public class AuditService {
    @Transactional(timeout = 2)
    public void save() {
        // Typically joins place()'s physical transaction.
    }
}
```

These snippets lack specific imports/repositories; they illustrate two beans. If `place()` owns physical T1 and `save()` is intercepted with `REQUIRED` and joins T1, **the 2-second timeout on inner does not automatically replace the physical timeout established by outer with 2 seconds**. T1's budget remains the outer's actual budget per the manager; inner creates a logical scope without opening a new physical transaction.

In particular, calling inner after T1 has already run for 6 seconds **does not** grant outer another 8 seconds or reset the clock; remaining transaction time must be accounted for.

### 3.3. `REQUIRES_NEW`, `NESTED`, `NOT_SUPPORTED`

| Inner Propagation | When Outer Already Has a Transaction | Inner's Annotation Timeout |
| --- | --- | --- |
| `REQUIRED` | Joins physical T1 | Does not create a new independent physical timeout; normally uses T1's remaining budget |
| `SUPPORTS` | Joins T1 | No new transaction to reset |
| `REQUIRES_NEW` | Suspends outer T1, opens physical T2 | Can apply T2's own timeout if supported by manager/resource |
| `NESTED` with JDBC | Creates a savepoint inside T1, no T2 | Savepoint does not automatically create a new physical transaction deadline |
| `NOT_SUPPORTED` | Suspends T1, runs without an actual transaction from manager | No transaction T2 opened by this propagation |
| No outer + `REQUIRED` or `NESTED` | Creates a new physical transaction | Can apply the top-level scope's timeout |

Do not use `REQUIRES_NEW` merely to "get a separate timeout" if business logic requires rolling back everything together with T1: T2 has independent commit/rollback, may require an extra JDBC connection, and can create lock contention.

### 3.4. Not a Java Thread-Interrupt Watchdog

Example:

```java
@Transactional(timeout = 1)
public void expensiveWork() {
    Thread.sleep(3000); // Snippet: Java must handle InterruptedException.
}
```

This is a **pseudo-snippet**, not a standalone compilable method. It conveys that transaction timeout **is not a guarantee Spring will interrupt a Java sleep/computation at the first second**. In Spring JDBC, remaining time is applied to JDBC statements; when the next statement prepares to run, Spring can detect expiration and throw `TransactionTimedOutException`. Depending on manager/provider, failure may be detected at another step.

Because the transaction may still hold connections/locks while code sleeps, keep critical sections short and design request deadlines with real cancellation mechanisms rather than relying solely on the annotation.

## 4. `JdbcTemplate` `queryTimeout` and Remaining Transaction Time Precedence

`JdbcTemplate` has a query timeout configuration in **seconds**:

```java
@Bean
public JdbcTemplate jdbcTemplate(DataSource dataSource) {
    JdbcTemplate jdbc = new JdbcTemplate(dataSource);
    jdbc.setQueryTimeout(2);
    return jdbc;
}
```

This is a Spring bean method fragment. `2` here means 2 seconds for JDBC statements created by `JdbcTemplate`, **when not overridden by a transaction-level timeout**. Spring's `JdbcTemplate.setQueryTimeout` Javadoc notes that the template's timeout **will be overridden by the remaining transaction time** when the statement executes inside a transaction with a transaction-level timeout.

Thus, suppose:

- `JdbcTemplate.setQueryTimeout(2)`.
- Outer `@Transactional(timeout = 5)` started T1 and has ~4 seconds left.
- Query runs through `JdbcTemplate` on the same datasource/connection.

In normal Spring JDBC code paths, `DataSourceUtils.applyTimeout` applies **remaining transaction timeout** to JDBC `Statement.setQueryTimeout` instead of assuming the template enforces an independent 2-second cap. Actual values depend on call timing and how the driver handles second-level granularity; **you must not assert an exact millisecond number**.

This is a trap in budget design:

> **If business rules strictly require each SQL statement not to exceed 1.8 seconds when a transaction has 5 seconds, do not just set `JdbcTemplate` `queryTimeout=2` and assume both are enforced as `min`.** Consider database-side `statement_timeout`/dialect-specific timeouts or statement override mechanisms verified for your exact Spring/driver.

### 4.1. `DataSourceUtils.applyTransactionTimeout`

Spring JDBC provides an API so lower-level JDBC code still respects transaction timeout:

```java
DataSourceUtils.applyTransactionTimeout(statement, dataSource);
```

This is a fragment inside JDBC code that already has `Statement` and `DataSource`, requiring `import org.springframework.jdbc.datasource.DataSourceUtils`. `JdbcTemplate` handles applying transaction-related timeouts to statements via Spring's mechanism. If you create a JDBC `Statement` manually, consider `DataSourceUtils.applyTransactionTimeout(...)` or `applyTimeout(...)`; merely calling `connection.prepareStatement(...)` on a self-managed connection does not automatically inherit all Spring settings.

The Spring transaction manager must manage the exact same `DataSource`. A connection acquired outside the Spring transaction context, or from another datasource, may not be subject to the deadline you thought was applied.

### 4.2. Drivers and Databases May Apply Timeouts Differently

`java.sql.Statement.setQueryTimeout(int seconds)` is the JDBC API to request a statement timeout. Drivers typically attempt to cancel when the limit is exceeded, yet **precision and cancellation mechanics depend on the driver**. JDBC cancellation does not guarantee the backend has finished cleanup or that the network responds instantaneously at that mark.

Some databases offer server-side `statement_timeout`; that is a separate layer of protection, especially useful when ensuring the server bounds query processing time. However, a server timeout does not interrupt Java application logic outside SQL and does not limit time spent waiting to acquire a connection from the pool.

### 4.3. Query Timeout Is Not Transaction Timeout

A transaction executing **three SQL statements**, each taking 1.5 seconds, can consume nearly 4.5 seconds even when each statement's timeout is 2 seconds. If business logic requires total transaction time under 4 seconds, a 2-second statement timeout alone is insufficient.

Conversely, setting transaction timeout to 5s lets a query wait on a lock for nearly 5s, burning the entire budget. If there is a separate lock-wait SLO, set a smaller threshold at the database.

## 5. Pool Acquisition, TCP Connect, and Socket Read Are Different

### 5.1. HikariCP `connectionTimeout` Measures Only Waiting for a Connection from the Pool

HikariCP:

```properties
spring.datasource.hikari.connection-timeout=800
spring.datasource.hikari.validation-timeout=500
spring.datasource.hikari.maximum-pool-size=20
```

This is an **example `application.properties` for Spring Boot + HikariCP**, not the configuration of the plain Spring demo below. `connection-timeout` and `validation-timeout` are in **milliseconds**. Hikari requires validation timeout to be smaller than connection timeout and enforces a minimum threshold per version (current common HikariCP releases have a 250 ms minimum).

Meaning:

- `connection-timeout=800`: the thread waits **to borrow a connection from the pool** for at most ~800 ms per Hikari semantics; if no connection is available, an acquisition error is raised.
- `validation-timeout=500`: limits checking whether a connection is alive when validation needs to run; **not** an SQL query timeout.
- `maximum-pool-size=20`: maximum connections in the pool, which must be sized per concurrent load/DB capacity rather than copied blindly.

**Do not equate Hikari's `connectionTimeout` with a JDBC driver's `connectTimeout`.** Nearly identical names, yet two different layers. A new connection created by the pool can also incur the driver's TCP connect/login timeout, as well as specific pool lifecycle behavior.

### 5.2. Driver TCP Connect Timeout

With the PostgreSQL JDBC driver (pgJDBC), illustrative URL:

```properties
spring.datasource.url=jdbc:postgresql://db.example.internal:5432/orders?connectTimeout=2&socketTimeout=6
```

This is an example configuration with an illustrative hostname, not a ready-to-use URL. Per pgJDBC:

- `connectTimeout=2`: time limit for the **socket connection** operation to the server, in **seconds**.
- `socketTimeout=6`: **socket read** timeout, in **seconds**; if waiting for a server response exceeds the allowed time, the driver can close the connection.
- `loginTimeout`, if configured, has a different meaning and also uses **seconds** per pgJDBC; it does not simply replace Hikari's pool acquisition timeout.

Socket read timeout is a network safety net, **not an exact 6-second total SQL execution deadline** across every interaction. It can drop the connection and an active transaction, requiring proper failure/cleanup handling. For long transactions or streaming queries, evaluate timeouts according to protocol/driver.

### 5.3. Pool `idleTimeout`/`maxLifetime`/`leakDetectionThreshold` Do Not Limit Queries

Other Hikari properties are frequently misused:

| HikariCP Property | Actual Purpose | Should Not Be Interpreted As |
| --- | --- | --- |
| `connectionTimeout` | Waiting to borrow a connection from the pool | SQL timeout, TCP connect timeout |
| `validationTimeout` | Time to validate whether a connection is still usable | Transaction timeout |
| `idleTimeout` | When the pool can retire an **idle connection** (per pool conditions) | Automatically closing active SQL running too long |
| `maxLifetime` | Lifetime limit of a connection in the pool; active connections are normally only retired after being returned | Max transaction duration/query duration |
| `leakDetectionThreshold` | Logs a warning for long-held connections, for diagnostics | Automatically rolling back the transaction at the warning threshold |

Setting `maxLifetime = 5000` does not create a "5-second transaction timeout". A connection actively in use by the application is normally not yanked mid-transaction by Hikari just because `maxLifetime` is reached; retirement happens per pool lifecycle.

### 5.4. Clues to Distinguish Connection Wait Types

- Pool wait: Hikari pending threads rising, active connections near maximum, error `"connection is not available, request timed out"`.
- Network connect: driver stack in socket connect/handshake, DNS/TLS/network, physical connection not yet established.
- DB query wait: connection granted and statement is executing/waiting for locks.
- Socket read wait: request sent, client waiting for bytes from server.
- Transaction logic wait: Java code/remote HTTP/synchronization running inside the transaction.

Metrics must separate these; simply seeing `"database call took 7s"` does not tell whether time was lost in the pool, TCP, locks, or execution.

## 6. Consistent Time Budget: Designing from Outer Deadline Inward

Suppose an endpoint targets **returning a result or a controlled error within 8 seconds**. This is an **illustrative exercise**, not a general SLA recommendation.

An initial configuration could be:

| Layer | Illustrative Threshold | Purpose |
| --- | ---: | --- |
| Upstream/gateway timeout | 8,000 ms | Avoid gateway dropping the request before the service has a chance to return a meaningful error |
| Application/handler deadline | 7,000 ms | Leave ~1,000 ms for network, serialization, middleware cleanup |
| Pool acquisition budget | 800 ms | Bound waiting for a connection before DB work |
| Physical transaction budget | 5,000 ms | Prevent a unit-of-work from holding DB resources too long per manager mechanism |
| Per-SQL server statement timeout | 1,800 ms | Bound each statement even while transaction still has time |
| Lock wait timeout | 700 ms | Fail before waiting for a lock consumes the statement's entire budget |
| Socket read timeout (pgJDBC) | 6,000 ms | Network safety net; not treated as a query/transaction stopwatch |
| TCP connect timeout (pgJDBC) | 2,000 ms | Avoid hanging too long when establishing a new DB connection |

Why the values are structured this way:

- `700 ms < 1,800 ms < 5,000 ms < 7,000 ms < 8,000 ms`: a lock wait fails early, a statement has its own cap, the transaction has a total budget, and the service has headroom for other steps/cleanup.
- Pool wait 800 ms and transaction 5,000 ms can happen sequentially: 5,800 ms stays under the 7,000 ms handler budget, leaving margin for non-DB logic in typical cases.
- `socketTimeout=6s` is a **network safety net** when the backend stops responding; it does not replace the 1.8-second server statement timeout and does not guarantee terminating every query at exact 6 seconds.
- If the pool creates a new physical connection under load, the 2s TCP connect timeout can complicate the path relative to the 800 ms borrow wait; do not assume layers automatically intersect via a `min` formula.
- Timeouts have different resolutions and starting points, plus queueing, GC pauses, scheduling, and rollback costs; **the table is an engineering budget to be measured**, not an SLA proven by configuration alone.

### 6.1. Deadline Precedence Model

```text
HTTP gateway budget:          8,000 ms
  Application handling:       7,000 ms
    Connection pool borrow:     800 ms
    Transaction total:        5,000 ms
      SQL statement server:   1,800 ms/stmt
        Lock wait:              700 ms/lock request
    Serialization/cleanup/retry reserve: remaining
  Transport/headroom:         1,000 ms

TCP connect:                  2 seconds when creating a new connection
Socket read safety net:       6 seconds per driver read
```

Only use **retries when enough remaining request deadline exists**. If a request already spent 6.7 seconds of a 7-second budget, retrying a 5-second transaction can both breach gateway timeout and worsen lock contention.

### 6.2. Distinguishing a Configured Threshold from a Propagated Deadline

A better architectural design is keeping an **absolute deadline** for the request (target completion timestamp), then before starting a new step computing remaining budget:

```java
long remainingNanos = deadlineNanos - System.nanoTime();
if (remainingNanos <= 0) {
    throw new RequestDeadlineExceededException();
}
```

This is a **design fragment**, requiring prior declaration of `deadlineNanos` and exception definition; not standalone Java. `System.nanoTime()` is suitable for measuring durations within the same process, not Unix timestamps sent over the network. For deadlines propagated over HTTP, use an absolute wall-clock mark or protocol deadline and safely convert it to a local monotonic budget.

Main idea: never unconditionally grant "a fresh 5 seconds" to every step in a request that has nearly exhausted 7 seconds. Use **remaining budget** to decide whether to begin a DB transaction, remote call, or retry.

## 7. PostgreSQL: Adding Server-Side Statement and Lock Timeouts

When using PostgreSQL inside a physical transaction:

```sql
BEGIN;
SET LOCAL statement_timeout = '1800ms';
SET LOCAL lock_timeout = '700ms';

SELECT quantity
FROM inventory
WHERE id = 101
FOR UPDATE;

UPDATE inventory
SET quantity = quantity - 1
WHERE id = 101;

COMMIT;
```

This is **illustrative PostgreSQL SQL** for a session transaction; do not send extra `BEGIN/COMMIT` via JDBC if Spring `@Transactional` is managing the same connection.

- `statement_timeout`: server limits statement duration, typically including execution/wait per PostgreSQL protocol semantics.
- `lock_timeout`: limits lock-wait duration; applies per lock acquisition attempt, and is set smaller than `statement_timeout` so lock issues are reported first.
- `SET LOCAL`: applies the setting only for the current transaction; after COMMIT/ROLLBACK it does not persist like session-level `SET`.
- If a statement exceeds the timeout, PostgreSQL can put the transaction into an **aborted** state; you must roll back the transaction or roll back to an appropriate savepoint before continuing SQL. Do not catch the exception and assume the connection/transaction is still usable.

PostgreSQL docs also note that setting `lock_timeout` equal to or greater than `statement_timeout` usually makes little sense because `statement_timeout` triggers first. Do not copy these SQL commands verbatim to H2, MySQL, Oracle, or SQL Server; parameter names and semantics differ.

### 7.1. Idle-in-Transaction Is Not Total Transaction Timeout

PostgreSQL has `idle_in_transaction_session_timeout` to close a session sitting in a transaction **with no SQL activity** longer than the threshold. This protects against abandoned connections holding locks, unlike statement timeout or total transaction timeout.

If Java code holds a transaction while waiting 20 seconds on a remote call without querying, a server idle-in-transaction timeout may intervene, yet that can break the connection and cause unpredictable side effects; do not treat this as the primary fix for poorly designed critical sections.

### 7.2. Spring Transaction Timeout and Server Timeouts Can Coexist

You can combine:

- Spring `@Transactional(timeout = 5)` for a new physical transaction.
- PostgreSQL `SET LOCAL statement_timeout = '1800ms'` to limit each SQL.
- PostgreSQL `SET LOCAL lock_timeout = '700ms'` to avoid long lock waits.
- Driver socket read timeout as a safety net.
- A 7-second application deadline for the whole request.

Yet once the server cancels a statement due to timeout, **Spring's transaction rollback policy** and database session state must be handled consistently. One layer must not "compensate" for another by trying to resume the same failed T1.

## 8. Spring Data JPA and Query Hints

JPA has different APIs from raw JDBC. Spring Data JPA example:

```java
public interface InventoryRepository
        extends JpaRepository<Inventory, Long> {

    @QueryHints(@QueryHint(
            name = "jakarta.persistence.query.timeout",
            value = "1800"))
    @Query("select i from Inventory i where i.id = :id")
    Optional<Inventory> findWithQueryBudget(@Param("id") Long id);
}
```

This is a **snippet**, requiring Spring Data JPA, the entity, `Optional`, and corresponding imports. The Jakarta Persistence query timeout hint is expressed in **milliseconds**, yet how the provider translates it into SQL/JDBC statement timeout can differ. A JPA provider may not support all hints across every dialect, or may round values due to JDBC's second-level granularity.

When using pessimistic locking:

```java
entityManager.find(
        Inventory.class,
        101L,
        LockModeType.PESSIMISTIC_WRITE,
        Map.of("jakarta.persistence.lock.timeout", 700));
```

This is a fragment with `EntityManager`, entity, `LockModeType`, and `Map`. Lock timeout hints are usually in milliseconds and support varies unevenly across providers/databases. Do not infer that setting the hint alone makes the database enforce exact 700 ms; verify with two genuinely contending connections.

### 8.1. Transaction Timeout and Query Hints: Precedence Is Up to the Provider

Hibernate/JPA may set its own query timeout, transaction timeout, and the database/server may have other caps. Inspect actual SQL, JDBC statement timeouts, provider logs, and PostgreSQL settings when exceptions occur. Do not mechanically apply **`JdbcTemplate`**'s timeout-override rule to every JPA provider.

### 8.2. A Spring Data Repository Method Is Not an End-to-End Deadline

A repository method with a 1.8-second query hint does not bound time spent on:

- Waiting to acquire a connection before the query is created.
- Java logic calling the repository before/after.
- Multiple other queries within the same service method.
- Remote calls/serialization outside the DB.

Only service-level/application deadlines and transaction design can cover all these intervals under a proactive policy.

## 9. Runnable Java 17 Example: Transaction Timeout Wins Over a Configured Query Timeout

The demo uses **Java 17+, Spring Framework 6.2.19, H2 2.3.232, Maven**. It verifies an easily overlooked point: with `DataSourceTransactionManager` and `JdbcTemplate`, **an expired transaction budget can be detected at the next SQL statement and lead to rolling back all uncommitted changes**.

Design:

- `JdbcTemplate` has a default query timeout of **2 seconds**.
- `quickWrite()` is called through the Spring proxy with `@Transactional(timeout = 4)`; updates quickly, commits.
- `expireAfterWork()` has `@Transactional(timeout = 1)`; updates first, Java sleeps 1.5 seconds, then runs a JDBC query. When `JdbcTemplate` prepares to apply remaining transaction timeout to the statement, Spring detects the expired deadline and throws `TransactionTimedOutException`, so the update in T2 rolls back.
- Final database state: only the committed update from the fast call remains.

Do not use `Thread.sleep` inside real transactions; it merely helps the demo reproduce an expired deadline cleanly. The code uses `DriverManagerDataSource` for H2, so it **does not demonstrate pool acquisition timeout**; that belongs to HikariCP configuration outside this example.

### 9.1. Project Structure

```text
timeout-budget-demo/
├── pom.xml
└── src/main/java/demo/tx/TimeoutBudgetDemo.java
```

### 9.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>timeout-budget-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 9.3. `src/main/java/demo/tx/TimeoutBudgetDemo.java`

```java
package demo.tx;

import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionTimedOutException;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;

public final class TimeoutBudgetDemo {

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = ctx.getBean(JdbcTemplate.class);
            BudgetService service = ctx.getBean(BudgetService.class);

            jdbc.execute(
                    "CREATE TABLE wallet (id INT PRIMARY KEY, balance INT)");
            jdbc.update(
                    "INSERT INTO wallet (id, balance) VALUES (1, 100)");

            System.out.println("initial=" + balance(jdbc));
            System.out.println("configuredJdbcQueryTimeoutSeconds="
                    + jdbc.getQueryTimeout());

            service.quickWrite();
            System.out.println("after quick=" + balance(jdbc));

            try {
                service.expireAfterWork();
                throw new AssertionError("Expected transaction timeout");
            } catch (TransactionTimedOutException ex) {
                System.out.println("caught=TransactionTimedOutException");
            }
            System.out.println("after timeout=" + balance(jdbc));
        }
    }

    private static int balance(JdbcTemplate jdbc) {
        Integer number = jdbc.queryForObject(
                "SELECT balance FROM wallet WHERE id = 1",
                Integer.class);
        return number;
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement(proxyTargetClass = true)
    public static class Config {

        @Bean
        public DataSource dataSource() {
            return new DriverManagerDataSource(
                    "jdbc:h2:mem:timeout_budget;DB_CLOSE_DELAY=-1",
                    "sa", "");
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            JdbcTemplate template = new JdbcTemplate(ds);
            template.setQueryTimeout(2);
            return template;
        }

        @Bean
        public BudgetService budgetService(JdbcTemplate jdbc) {
            return new BudgetService(jdbc);
        }
    }

    public static class BudgetService {
        private final JdbcTemplate jdbc;

        public BudgetService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(timeout = 4)
        public void quickWrite() {
            jdbc.update(
                    "UPDATE wallet SET balance = balance + 5 WHERE id = 1");
        }

        @Transactional(timeout = 1)
        public void expireAfterWork() {
            jdbc.update(
                    "UPDATE wallet SET balance = balance + 20 WHERE id = 1");

            // Demo only: let the transaction deadline elapse.
            try {
                Thread.sleep(1500L);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("Interrupted", ex);
            }

            // JdbcTemplate checks remaining transaction timeout
            // before executing the next statement.
            jdbc.queryForObject(
                    "SELECT balance FROM wallet WHERE id = 1",
                    Integer.class);
        }
    }
}
```

### 9.4. Run Command

With Maven and JDK 17+, from the `timeout-budget-demo` directory:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.tx.TimeoutBudgetDemo
```

Lines printed by the program, excluding Maven/Spring logs:

```text
initial=100
configuredJdbcQueryTimeoutSeconds=2
after quick=105
caught=TransactionTimedOutException
after timeout=105
```

### 9.5. Why Does the Output Make Sense?

1. Initially the wallet has balance `100`.
2. `jdbc.getQueryTimeout()` prints the **template's configured** 2 seconds. It **does not** tell you the `Statement.setQueryTimeout` value applied to a statement while inside a transaction with a deadline.
3. `quickWrite()` runs quickly and returns, transaction T1 commits the +5 update; balance `105`.
4. `expireAfterWork()` starts T2 with a 1-second timeout, updates +20 (uncommitted); then the method runs `Thread.sleep(1500L)`, during which the Java thread **is not automatically interrupted** by the Spring transaction annotation.
5. When the next JDBC query is prepared, Spring JDBC checks remaining transaction time. T2's deadline has expired, raising `TransactionTimedOutException`; the unchecked exception escapes the transaction interceptor so T2 rolls back.
6. After rollback, balance remains `105`. No 125 is committed.

**Demo limitations:** it checks transaction timeout being applied at a JDBC statement after the deadline elapsed, without measuring database-side query cancellation time or connection borrow time. `Thread.sleep`/scheduling can drift on heavily loaded machines or if the thread is interrupted, so confirming production behavior requires integration tests and metrics on the actual driver/database. The code is designed to compile with the dependencies in the POM; if running on different Spring/H2 versions, verify API/exception behavior before drawing conclusions.

### 9.6. Extended Experiments

- Change `@Transactional(timeout = 1)` to `timeout = 5`: Java sleeps 1.5 seconds then the query typically completes; T2 commits and balance rises by 20.
- Remove `Thread.sleep` and run fast: T2 finishes before the deadline.
- Set `Thread.sleep` to 3 seconds yet **run no JDBC statement after sleeping**: do not treat that as proof that "Spring transaction timeout will abort Java code on time" because enforcement varies by manager/resource.
- Replace `DriverManagerDataSource` with a Hikari pool with `maximumPoolSize=1` and test two concurrent requests; the second thread may hit **pool acquisition timeout** before getting a chance to run SQL. That is a different failure category, not SQL-phase `TransactionTimedOutException`.
- With PostgreSQL, add `SET LOCAL statement_timeout`/`lock_timeout` and run a real blocking query; test timing and the SQLState returned by the server.

## 10. Transaction Timeout Cannot Rescue an Overly Long Critical Section

A method:

```java
@Transactional(timeout = 5)
public void reserve(long productId) {
    inventoryRepository.lockRow(productId);
    paymentGateway.authorize();
    inventoryRepository.decrease(productId);
}
```

is an illustrative snippet. If `lockRow` acquires a database row lock and `paymentGateway.authorize` waits 9 seconds, the row lock may still be held **until the physical transaction completes or the connection/transaction is killed by the DB via its own mechanism**. Setting a 5-second timeout **does not guarantee the lock is released right at 5 seconds** if the application has not ended the transaction or the resource is hanging outside SQL.

A better design usually separates:

1. Validation unrelated to changing state upfront.
2. Preparing payment intent/reservation state per the business contract.
3. Opening a **short transaction**.
4. Locking the right row, re-checking invariants, and performing minimal updates.
5. Committing/rolling back.
6. Communicating externally via an appropriate workflow/idempotency/outbox.

Do not blindly move payment calls outside the transaction if the system lacks a consistency strategy; redesign business states so you do not trade correctness for latency.

## 11. Retries Must Share the Same Deadline Budget

Suppose a request has 800 ms left; an SQL error is classified as transient. Immediately retrying an entire transaction with a 5-second timeout can cause the request to exceed the outer deadline. Never automatically grant a full fresh timeout as if the request just started.

Checklist before each retry:

1. Check the error type: lock timeout/deadlock/connection failure can be transient; unique constraint violations from business rules usually should not be retried indefinitely.
2. Check **remaining request deadline**, attempt count, backoff, and time available for a new transaction.
3. Ensure **the previous transaction rolled back/cleaned up completely**; never retry SQL on an aborted PostgreSQL transaction.
4. Use a fresh Spring proxy invocation/`TransactionTemplate` on each attempt when a new physical transaction is needed.
5. Ensure idempotency if the action can cause side effects (payments, broker publishing, sending emails).
6. Emit metrics for retry counts, reasons, and final outcomes; do not log only the final error.

```java
public void performWithRetry(long id, long deadlineNanos) {
    for (int attempt = 1; attempt <= 3; attempt++) {
        long remaining = deadlineNanos - System.nanoTime();
        if (remaining <= 0) {
            throw new DeadlineExceededException();
        }
        try {
            transactionalWorker.update(id);
            return;
        } catch (TransientDataAccessException ex) {
            if (attempt == 3) {
                throw ex;
            }
            backoffWithinBudget(attempt, remaining);
        }
    }
}
```

This is **Java pseudocode with undefined methods/exceptions**, not a standalone runnable file. Crucially, the retry loop sits **outside** the transactional method `transactionalWorker.update` so each attempt can create a valid transaction through the proxy; budget and backoff must not exceed the final deadline.

### 11.1. Does Timeout Mean Rollback Is Definitely Confirmed?

**Not always.** If the client loses connectivity right while sending `COMMIT` or waiting for the commit acknowledgment, the client may not know whether the DB committed. Receiving a network timeout does not prove the entire operation rolled back.

For operations that may be retried after an "unknown outcome", you need idempotency keys, natural unique keys, or status lookups to avoid creating two payment/order transactions. This is why timeout handling must go hand in hand with **transaction outcome certainty**, not merely exception classification.

## 12. Diagnosing Failures by Layer

| Symptom | Likely Layer | Distinguishing Clues |
| --- | --- | --- |
| `SQLTransientConnectionException` or pool reports "Connection is not available" | Pool acquisition | Hikari pending connections, active=max, no statement running |
| TCP connect refused/timed out | Driver network setup | DNS, socket connect/SSL, pgJDBC `connectTimeout` |
| Query runs too long then gets canceled | Statement/client query timeout or server `statement_timeout` | SQLState, DB logs, JDBC cancellation |
| SQL waiting on row lock then times out | DB lock timeout | Blocking PID/lock wait metrics, PostgreSQL `lock_timeout` |
| `TransactionTimedOutException` before statement | Spring transaction remaining timeout | Spring transaction logs, physical transaction state, JDBC statement setup |
| JDBC socket read timeout closes connection | Driver `socketTimeout` | Network exceptions, connection invalidation |
| Request returns 504 Gateway Timeout yet DB keeps running | Gateway/app deadline lacking cancellation | Upstream request logs and DB active queries |
| Transaction holds locks while running no SQL | Java/remote call inside transaction or idle-in-transaction | DB transaction age, backend state, traces |
| Inner `@Transactional(timeout=1)` does not alter outer 10s | `REQUIRED` joins outer | Transaction join logs, owner is outer |
| JPA query hint has no effect | Provider/dialect does not enforce as expected | Provider logs, actual statement timeout, integration tests |
| Very short Hikari `maxLifetime` yet queries still run long | Wrong setting type | Pool retirement policy differs from transaction/query timeout |

When catching a timeout exception, log **SQLState/vendor code, layer, elapsed time, attempt number, and transaction outcome**; avoid logging passwords, personal data, or sensitive query parameters.

### 12.1. Metrics to Track

- End-to-end HTTP request latency by percentiles (p50/p95/p99).
- Pool active/idle/pending, acquisition latency, and acquisition timeouts.
- JDBC connect failures; TCP connect latency; socket read timeout counts.
- DB statement latency, cancellation count, slow queries, and query timeout codes.
- DB lock wait time, deadlock count, and blocking transaction age.
- Transaction duration from start to commit/rollback; rollback/unknown-outcome counts.
- Retry counts, backoff, and requests finishing near deadline.
- SQL queries still active **after** the client-side request was canceled.

With PostgreSQL you can use `pg_stat_activity`/`pg_locks`/`pg_blocking_pids` and server logs to separate slow queries from lock waits. With Hikari there are Micrometer metrics and logs depending on version. Do not diagnose from a single overall stopwatch.

## 13. Safe Configuration Sequence

### Step 1 — Define Business Boundaries and Latency SLOs

Set SLOs for endpoints and dependency calls, separating synchronous requests from long batch jobs. A 20-minute batch job must not share the same budget as an 8-second HTTP request.

### Step 2 — Measure Where Time Is Spent

Measure pool wait, connection creation, lock wait, SQL execution, Java work, remote calls, and commit time. If 90% of latency comes from pool exhaustion, dropping `@Transactional(timeout)` to 1 second will not fix the root cause.

### Step 3 — Place Application Deadline Highest Inside the App with Upstream Headroom

If the gateway caps at 8 seconds, the app needs a shorter budget leaving enough time for error responses/cleanup. Stop starting new work when remaining budget is insufficient. Use cancellation on each dependency per its supported API, without expecting Spring annotations to automatically propagate HTTP deadlines.

### Step 4 — Configure Pool and Driver Using Exact Units

- Hikari `connectionTimeout`/`validationTimeout` are **ms**.
- pgJDBC `connectTimeout`/`socketTimeout` are **s**.
- JDBC `Statement.setQueryTimeout` is **s**.
- Spring `@Transactional(timeout)` is **s**.
- Jakarta Persistence query/lock timeout hints use **ms** (subject to provider support).
- PostgreSQL `statement_timeout`/`lock_timeout` can be declared `'1800ms'`, `'700ms'` to avoid confusion.

Use unit-explicit config names: `poolAcquisitionTimeoutMs`, `transactionTimeoutSeconds`, `postgresStatementTimeoutMs`. Never copy `2000` from an ms field into a seconds field.

### Step 5 — Set Transaction Timeout at the Physical Owner

Choose timeouts per unit-of-work, rather than arbitrarily placing different numbers on every `REQUIRED` helper. When inner joins T1, it does not open T2; if one SQL statement needs its own timeout, consider appropriate database/driver timeouts instead of changing propagation and breaking atomicity.

### Step 6 — Test Timeouts Both Independently and Together

At minimum:

1. Pool with 1 connection, request A holds it; request B borrows → must observe pool timeout separately.
2. Driver connects to an unresponsive endpoint → verify connect timeout in a controlled test environment.
3. Slow PostgreSQL query → server statement timeout triggers.
4. Two transactions contend for a lock → lock timeout triggers before statement timeout.
5. Spring transaction exhausts budget then sends next SQL → observe `TransactionTimedOutException` or manager-appropriate behavior.
6. Outer T1 with inner `REQUIRED` → confirm inner timeout annotation does not reset T1.
7. Inner `REQUIRES_NEW` if truly needed → confirm independent T2 timeout and resources without exhausting the pool.
8. Query timeout and network timeout occurring close together → inspect exception precedence and cleanup.
9. Cancel HTTP request while SQL is running → verify whether the query is canceled / connection released.
10. Timeout when COMMIT acknowledgment is lost → verify idempotency/unknown-outcome handling.

## 14. Common Mistakes

**Mistake 1 — "Hikari `connectionTimeout=1000` means SQL runs at most 1 second."** No. That is the time waiting to borrow a connection from the pool, not execution timeout.

**Mistake 2 — "JDBC driver `connectTimeout=2` caps queries at 2 seconds max."** No. It bounds socket connection establishment; queries/socket reads are separate.

**Mistake 3 — "`@Transactional(timeout=5)` will interrupt `Thread.sleep` at second 5."** There is no such watchdog guarantee. Enforcement depends on the manager/resource and subsequent operations.

**Mistake 4 — "`JdbcTemplate.queryTimeout=2` always takes min with transaction `timeout=5`."** Do not guess: Spring JDBC Javadoc states remaining transaction timeout **overrides** the template timeout. If a lower per-statement cap is required, enforce it via a tested mechanism such as server `statement_timeout`.

**Mistake 5 — "Setting inner `REQUIRED(timeout=1)` gives outer T1 only 1 second left."** Not by default. Joining physical T1 does not create a new transaction or set a new deadline.

**Mistake 6 — "A 2s statement timeout is enough to bound a transaction with 10 SQL queries."** No. Ten SQL queries taking 1 second each already spend 10 seconds, excluding pool/Java/commit.

**Mistake 7 — "Socket timeout and statement timeout are the same."** No. Socket read timeout can close the connection; server-side query cancellation and transaction state differ.

**Mistake 8 — "JDBC timeout means the database definitely rolled back everything."** Not always. You must examine server transaction state, Spring rollback rules, lost commit acknowledgments, and out-of-DB side effects.

**Mistake 9 — "Higher timeouts reduce errors at zero cost."** Excessively high timeouts hold locks/pools/threads longer, increasing backlogs and causing cascades. Too-low timeouts fail valid workloads. Tune based on SLOs and percentiles.

**Mistake 10 — "Connection leak detector automatically closes long-running transactions."** No. Hikari leak detection primarily **logs warnings** to diagnose long-held connections, not kill transactions.

**Mistake 11 — "PostgreSQL `lock_timeout=2s` with `statement_timeout=1s` allows waiting 2s for locks."** When statement timeout triggers first, the 2s lock timeout does nothing for that statement.

**Mistake 12 — "When timeout happens, just retry inside a catch in the same `@Transactional` method."** The transaction may already be rollback-only/aborted; retries usually need a new transaction boundary, sufficient remaining deadline, and idempotency.

## 15. Self-Check Questions

**Question 1.** In Spring JDBC, you set `JdbcTemplate.setQueryTimeout(2)` and `@Transactional(timeout=5)`. Can you assume by default every JDBC statement is capped at 2 seconds max?

*Answer:* No. Spring JDBC has a mechanism applying remaining transaction timeout, and Javadoc explicitly states it overrides the template timeout. To cap per-statement at 2 seconds, verify the code path/driver or add an appropriate server-side cap.

**Question 2.** What does HikariCP `connectionTimeout=800` measure, and in what unit?

*Answer:* Maximum time a thread waits to borrow a connection from the pool; milliseconds. Not TCP connect or SQL timeout.

**Question 3.** Are pgJDBC `connectTimeout=2` and `socketTimeout=6` the same?

*Answer:* No. Both use seconds, yet relate respectively to socket connection establishment and socket read wait.

**Question 4.** Outer `@Transactional(timeout=8)`, inner `@Transactional(timeout=2)` with `REQUIRED`. Does it reset the transaction deadline?

*Answer:* Not by default when inner simply joins T1. It does not create a new physical T2.

**Question 5.** Why should PostgreSQL `lock_timeout` be smaller than `statement_timeout` if you want to distinguish lock-wait errors?

*Answer:* Because statement timeout will trigger first if it is less than or equal to lock timeout, rendering the lock-specific limit ineffective.

**Question 6.** A service transaction slept past its deadline and performs no further JDBC operations. Is Spring guaranteed to proactively interrupt it at the exact time?

*Answer:* No. Transaction timeout is not an interrupt watchdog for arbitrary Java code. Inspect actual manager/resource enforcement.

**Question 7.** Does a query timeout when a COMMIT acknowledgment is lost prove the transaction rolled back?

*Answer:* No. The outcome may be unknown; lookups/idempotency are needed to prevent double-application.

**Question 8.** If the app has 300ms left before the request deadline yet retries a 5s-timeout transaction, is the policy consistent?

*Answer:* No. Retries must be bounded by remaining deadline and backoff/cleanup costs.

**Question 9.** What is the maximum transaction duration HikariCP `maxLifetime` limits?

*Answer:* It manages connection lifetime in the pool, not a watchdog aborting long-running transactions or SQL.

**Question 10.** Why is `SET LOCAL statement_timeout` preferred when limiting SQL on the PostgreSQL side within a transaction?

*Answer:* It applies a server-side cap for the current transaction without leaving a session-level setting active after the transaction; you must still verify SQLState and rollback when the server cancels.

## 16. Summary and Action Checklist

- Choose timeouts **from the business/end-to-end deadline**, then allocate budgets to pool, transaction, lock wait, SQL, and network; never pick numbers independently.
- Know **the exact units**: Spring `@Transactional(timeout)`/JDBC `setQueryTimeout` (seconds); Hikari `connectionTimeout` (ms); pgJDBC `connectTimeout`/`socketTimeout` (seconds); JPA query hints (ms).
- `@Transactional(timeout)` applies primarily when **a new physical transaction is created**; an inner `REQUIRED` joining outer does not reset the deadline.
- In **Spring JDBC**, configured `JdbcTemplate.setQueryTimeout` can be **overridden by remaining transaction timeout**. Need an individual per-SQL cap? Verify the driver and use server-side `statement_timeout` where appropriate.
- **Pool borrow, TCP connect, socket read, lock wait, and statement execution are distinct phases**; each phase needs its own metrics and timeouts.
- **Transaction timeout is not a watchdog interrupting Java code**; keep transaction critical sections short, and do not let network calls/sleeps extend lock lifetimes.
- **Timeout does not always mean rollback is confirmed**; lost commit acknowledgments in particular require idempotency design.
- **Retries must have remaining budget, a new transaction boundary, and an attempt cap**; never retry blindly inside an errored transaction.
- Verify with tests **against real databases/drivers/providers**, adding metrics and logs to distinguish which layer timed out.

## Official Documentation Sources

- [Spring Framework — Transaction Management Reference](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework API — JdbcTemplate.setQueryTimeout](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html)
- [Spring Framework API — DataSourceUtils.applyTransactionTimeout](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html)
- [Spring Framework API — TransactionTimedOutException](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/TransactionTimedOutException.html)
- [HikariCP — Configuration reference](https://github.com/brettwooldridge/HikariCP#frequently-used)
- [pgJDBC — Connection and socket timeouts](https://jdbc.postgresql.org/documentation/use/)
- [PostgreSQL — Client connection defaults, statement_timeout, lock_timeout](https://www.postgresql.org/docs/current/runtime-config-client.html)
- [Jakarta Persistence — Query and lock timeout hints](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2)
