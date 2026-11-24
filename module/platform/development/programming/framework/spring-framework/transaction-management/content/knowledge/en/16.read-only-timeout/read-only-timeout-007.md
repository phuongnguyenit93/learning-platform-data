# JDBC Statement Timeout and Data-Access Tool Support

## 1. The Issue: Does `@Transactional(timeout=...)` Automatically Abort Every JDBC Query?

Suppose a report-search feature in the Spring Framework has:

~~~java
@Transactional(readOnly = true, timeout = 20)
public Report loadReport() {
    // Queries data using JDBC, ORM, or raw SQL.
}
~~~

This is an illustrative snippet, **not a standalone compilable program**. Seeing `timeout = 20` alone is not enough to assert that *any* SQL statement in the method is guaranteed to be canceled right after 20 seconds. Spring needs a **transaction manager**, a **DataSource/Connection participating in the transaction**, and a **data-access tool that knows how to apply the timeout to each JDBC Statement**. The driver/database must also enforce statement cancellation to the extent of its capability.

In a JDBC application using `DataSourceTransactionManager` or `JdbcTransactionManager`, Spring supports this via:

- `@Transactional(timeout = N)`: declares a **time budget for a new transaction**, in seconds, not an automatic interrupt across arbitrary Java threads.
- `JdbcTemplate`: when creating a `Statement`/`PreparedStatement`/`CallableStatement`, it can apply the **remaining transaction time** to the JDBC statement.
- `DataSourceUtils.applyTransactionTimeout(statement, dataSource)`: helps **manual JDBC code** attach the current transaction timeout to a created statement.
- `Statement.setQueryTimeout(seconds)`: the JDBC API allowing the driver to receive a maximum statement execution time, while how the driver/DB stops the statement depends on the implementation.

**Takeaway:** transaction timeout is a **policy within the transaction**, whereas query timeout is a **setting on each JDBC statement**. There is a link between them when the data-access tool **actively converts and applies it**. A single annotation does not automatically alter every JDBC statement created by arbitrary libraries.

### Flow Diagram

~~~text
Caller invokes Spring bean through transaction proxy
                      |
                      v
@Transactional(timeout = 20)
                      |
                      v
DataSourceTransactionManager starts JDBC transaction
and stores transaction deadline on participating resource
                      |
                      v
Service calls JDBC:
    |
    +-- JdbcTemplate / NamedParameterJdbcTemplate
    |       |
    |       +-- creates Statement via Spring-managed connection
    |       +-- applies remaining transaction timeout
    |       +-- driver receives setQueryTimeout(seconds)
    |
    +-- Manual JDBC using DataSourceUtils
    |       |
    |       +-- getConnection(dataSource)
    |       +-- connection.prepareStatement(...)
    |       +-- applyTransactionTimeout(statement, dataSource)
    |       +-- driver receives query timeout
    |
    +-- Manual JDBC bypassing helpers
            |
            +-- not guaranteed to automatically receive transaction timeout
                      |
                      v
Database/driver enforces cancellation, lock waits, retries?
                      |
                      v
Spring receives success/SQLException then applies completion/rollback rules
~~~

The practical question is not merely "does the transaction have a timeout?", but also **"through which API is this SQL issued, on which connection, does the statement receive a query timeout, and does the DB enforce it?"**

## 2. Distinguishing Types of Timeouts So You Fix the Right Layer

The word "timeout" appears at many layers. They are **not synonymous**:

| Concept | Unit / Target | Main Effect | Does Not Guarantee |
| --- | --- | --- | --- |
| `@Transactional(timeout = 20)` | Seconds; **new transaction** | Spring sets a transaction deadline when supported by the manager | Automatically interrupting arbitrary Java code, HTTP, file I/O, or statements of any library. |
| `JdbcTemplate.setQueryTimeout(7)` | Seconds; JDBC statements created by the template | Sends the configured query timeout to the driver when running outside a budgeted transaction | Replacing transaction timeout; may be **overridden** by remaining transaction time. |
| `Statement.setQueryTimeout(3)` | Seconds; **specific statement** | Asks the JDBC driver to limit statement execution time | Exact cancellation behavior and exception type depend on the JDBC driver/DB. |
| JDBC `Connection.setNetworkTimeout(...)` | Milliseconds; connection network operations | Configures network timeout when supported by the driver | Equivalent to business runtime or full transaction duration. |
| Connection-pool acquisition timeout | Usually milliseconds; **waiting for a connection** | Limits waiting for a resource from the pool | Limiting SQL duration once a connection is acquired. |
| Database statement/lock timeout | Per DB; statement or lock wait | Engine directly enforces its own limit | Automatically replacing Spring/JDBC transaction policies. |
| HTTP client timeout | Per client; network call | Limits HTTP connection/reading | Rolling back an already completed external effect. |

Example: the connection pool is exhausted, causing a request to wait 5 seconds. `Statement.setQueryTimeout(3)` **has no effect** while the request has not yet obtained a connection to create a statement. Conversely, if the pool is fast yet SQL waits long on locks, you must inspect DB-side query timeout/lock timeout.

In JDBC, `Statement.setQueryTimeout(int seconds)` accepts seconds; a value of `0` in JDBC typically means **no query timeout limit**. By contrast, `JdbcTemplate`'s default is `queryTimeout = -1`, indicating the template does not proactively set a fixed timeout outside a transaction; these values **must not be used interchangeably**.

### Reading "Timeout Inside a Transaction" Properly

`@Transactional(timeout=20)` does not arm a Java timer that kills the thread right after 20 seconds. With `DataSourceTransactionManager`, Spring holds the transaction deadline on the resource and helps SQL run via transaction-aware tooling receive the **remaining time**. Some activities may not check the time budget until preparing/executing the next JDBC statement. Effectiveness on a JDBC statement still depends on the driver.

This also explains why `Thread.sleep(25000)` in a transactional method is not a valid test for "the driver automatically cancels SQL": during sleep there is no statement for the driver to cancel. Instead, inspect the **statement setting** and, if needed, run a controlled slow SQL statement on the **exact target database** to test cancellation.

## 3. How Does Transaction Timeout Reach a JDBC Statement?

### 3.1. `DataSourceTransactionManager` Manages the Connection and Deadline

In Spring JDBC, `DataSourceTransactionManager` manages a JDBC connection for a specific `DataSource`; in imperative transactions it typically binds the connection to the thread. Calls via `JdbcTemplate` retrieve connections through `DataSourceUtils` and thus use the connection participating in the transaction.

When a transaction is created with a timeout, Spring stores deadline information so subsequent data operations can query the **remaining transaction timeout**. This differs from calling `Connection.setNetworkTimeout`: the transaction deadline is a time policy on the Spring resource holder, not merely a network timeout value.

If the application uses **two different DataSources**, or a service uses one manager while the JDBC query connects to another resource, deadline propagation is not guaranteed. Method names and annotations cannot substitute for actual resource coordination.

### 3.2. `JdbcTemplate` Applies Statement Settings Automatically

For standard `JdbcTemplate` operations, Spring creates the JDBC statement and invokes code applying statement settings before running the callback/executing SQL. Timeout logic uses `DataSourceUtils.applyTimeout(statement, dataSource, configuredQueryTimeout)`.

Key policy rules:

1. **No active transaction timeout:** if the template has `queryTimeout = 7`, statements from that template receive a **7-second** timeout request.
2. **Active transaction deadline:** **remaining transaction time overrides** the query timeout configured on the template; it does not necessarily take `min(7, remaining)`. For example, a fresh transaction with nearly 20 seconds left can give the statement a query timeout near 20, even if the template is configured with 7.
3. **Transaction nearly expired:** the time budget shrinks; statements created late receive lower remaining values or may hit a timeout error once the deadline has passed.
4. **Do not compare values to the exact millisecond:** the JDBC `setQueryTimeout` API takes **whole seconds**; the "remaining" value is affected by elapsed wall-clock time, rounding, and system scheduling jitter.

~~~java
// Illustrates bean-level configuration; not a standalone project.
JdbcTemplate jdbc = new JdbcTemplate(dataSource);
jdbc.setQueryTimeout(7);
~~~

The lab below checks directly inside `PreparedStatementCallback` that a statement created **outside a transaction** receives 7, while a statement created **inside a `timeout=20` transaction** reflects the transaction's remaining time.

**Do not equate "transaction overrides template query timeout" with "the transaction is guaranteed to cancel right at 20 seconds".** It proves Spring code forwards the request down to the JDBC statement; actual driver cancellation and DB response must still be tested separately.

### 3.3. `NamedParameterJdbcTemplate`, `JdbcClient`, and Higher-Level Libraries

`NamedParameterJdbcTemplate` uses `JdbcTemplate` underneath for many JDBC operations, so when configured properly with the same datasource and template, statements it creates inherit the corresponding Spring JDBC mechanism. `JdbcClient` in Spring JDBC also uses these templates for fluent calls.

Example:

~~~java
// Illustrative: executing through a Spring template.
namedParameterJdbcTemplate.queryForObject(
    "SELECT COUNT(*) FROM orders WHERE status = :status",
    Map.of("status", "NEW"),
    Long.class
);
~~~

This is a non-standalone snippet requiring a bean and an actual `orders` table. The point to remember: **whichever library creates the statement is the one responsible for handling timeouts**. When wrapping `JdbcTemplate` in another API, verify the final wrapper still uses the right Spring-managed template/connection rather than creating JDBC statements down a separate code path.

### 3.4. Manual JDBC: `DataSourceUtils.applyTransactionTimeout`

If code must create `PreparedStatement`/`Statement` manually, Spring provides a helper:

~~~java
Connection connection = DataSourceUtils.getConnection(dataSource);
try (PreparedStatement statement =
         connection.prepareStatement("SELECT 1")) {
    DataSourceUtils.applyTransactionTimeout(statement, dataSource);
    try (ResultSet rs = statement.executeQuery()) {
        // Process ResultSet.
    }
} finally {
    DataSourceUtils.releaseConnection(connection, dataSource);
}
~~~

This is a **condensed illustrative snippet**, requiring imports/SQLException handling and context; runnable code is in `StatementProbe.java` in section 6. Use `DataSourceUtils.getConnection` instead of acquiring connections arbitrarily; do not call `connection.close()` directly on a connection bound by Spring to a transaction. `DataSourceUtils.releaseConnection` handles transaction-managed connections properly.

**Very easy pitfall:** `DataSourceUtils.applyTransactionTimeout` needs **the exact same DataSource resource** that the transaction manager manages. Do not pass an arbitrary different `DataSource` wrapper or a datasource pointing to another database and expect the helper to find the active deadline.

With manual JDBC, **each newly created statement** needs the timeout applied to it. `applyTransactionTimeout` is not a **permanent configuration across the whole connection**.

### 3.5. The `TransactionAwareDataSourceProxy` Mechanism

`TransactionAwareDataSourceProxy` is an adapter for legacy JDBC code that only knows how to call the standard `DataSource` API, giving it connection access with Spring transaction awareness. Spring documentation recommends **preferring `JdbcTemplate`/`DataSourceUtils`** in new code. Do not stack extra datasource proxies to fix timeouts when code can move straight to a template.

Having a proxy present is not a guarantee that every JDBC library uses statement timeouts as desired in all cases; check the statement creation path and the specific wrapper's behavior.

## 4. `@Transactional(timeout)` Is Not a Global Setting for Inner Methods

Another key point is that **timeout only applies when starting a new transaction** per transaction propagation.

~~~java
@Service
class OuterService {
    private final InnerService inner;

    OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional(timeout = 60)
    public void outer() {
        inner.inner();
    }
}

@Service
class InnerService {
    @Transactional(
        propagation = Propagation.REQUIRED,
        timeout = 5
    )
    public void inner() {
        // Joins the outer transaction, does not reset deadline to 5 seconds.
    }
}
~~~

This is **illustrative code**, missing full imports. When two Spring beans are called through proxies, `inner` uses `REQUIRED` and thus joins the outer's physical transaction. **The outer's deadline is preserved**, instead of inner resetting it to 5 seconds.

Comparison:

| Inner Method Call | Transaction State Before Call | Which Timeout Has a Chance to Apply? |
| --- | --- | --- |
| `REQUIRED(timeout=5)` called standalone | No transaction yet | Inner opens a new transaction and requests 5 seconds |
| `REQUIRED(timeout=5)` called from `outer(timeout=60)` | Physical transaction already exists | Uses remaining time of outer's 60-second budget, does not reset to 5 |
| `REQUIRES_NEW(timeout=5)` called from outer | Outer transaction already exists | Inner opens an independent transaction with its own 5-second deadline |
| `this.inner()` within same target | May have outer's transaction or none | Inner annotation normally **bypasses proxy** so it creates no timeout scope as expected |

`REQUIRES_NEW` is not merely a way to "force a faster query": it opens an independent transaction, can commit even if outer rolls back, requires another connection, and risks lock contention/pool exhaustion. When a specific query needs a shorter timeout, consider configuring an appropriate **statement/query timeout** instead of altering propagation and business commit semantics.

### Inner Time Budget vs. Physical Transaction Deadline

There can be multiple `@Transactional` logical scopes yet only one `REQUIRED` physical transaction. The transaction manager keeps the deadline of the physical transaction; it does not create a new clock for every inner method called. Thus, judging deadlines by reading annotations on inner methods is insufficient.

If an inner exception escapes through the proxy, rollback rules can still affect the shared transaction; timeout and rollback policy are two separate dimensions. A query timeout can throw `SQLException` translated into a Spring exception, while whether the transaction rolls back depends on rules, transaction state, and whether the DB allows continuing after an error.

## 5. Actual Driver/Database Support and Error Types

### 5.1. JDBC Query Timeout Is a *Cancel Request*

Per JDBC, `Statement.setQueryTimeout(int seconds)` provides a time limit for statement execution. When supported by the driver/DB, exceeding it may raise `SQLTimeoutException` or a corresponding driver `SQLException`. However:

- Drivers can check timeouts at different points and do not promise millisecond precision.
- Different engines account for lock-wait time, server statement execution, or network differently.
- Sending a cancel request does not mean the server stops instantaneously.
- If the statement already made partial changes or the transaction entered an error state, you must know the database's rollback/cancel semantics.
- `Statement.cancel()` is likewise only a cancellation request API; outcome depends on the driver/engine.

Do not hardcode "timeout always returns exact `SQLTimeoutException`" across every DB. Spring JDBC can translate `SQLException` into a `DataAccessException` subclass (such as `QueryTimeoutException` in recognized cases); the exact exception class depends on SQL state, error code, and driver.

### 5.2. Statement Timeout Cannot Replace the Entire Business Time Budget

Suppose a service:

~~~text
BEGIN TRANSACTION timeout=20s
  |
  +-- Fast SELECT: 1s
  +-- External HTTP call outside database: 15s
  +-- Java data assembly: 3s
  +-- Second SELECT: starts with only ~1s left
  |
  +-- Transaction deadline may already be near/expired when creating new statement
  +-- Driver only cancels SQL if applied/supported by tools
COMMIT or ROLLBACK per actual state
~~~

For HTTP, file I/O, CPU, thread pools, queues, or connection acquisition waits, place limits at the **appropriate layer** instead of expecting `@Transactional(timeout=20)` to apply to them. Keeping a transaction open across network calls can also hold locks/connections unnecessarily long.

### 5.3. Database Timeout, Lock Timeout, Network Timeout

For example, PostgreSQL has server parameters `statement_timeout` and `lock_timeout`; these are managed by the database and act independently of JDBC `Statement.setQueryTimeout`. MySQL, SQL Server, Oracle, and H2 do not necessarily provide identical parameter names or semantics. This is given only as an illustration; do not copy `SET statement_timeout` verbatim to every DB.

`Connection.setNetworkTimeout(executor, millis)` belongs to the connection/network API, in milliseconds, with a different contract from query timeout. Meanwhile, HikariCP `connectionTimeout` is the maximum time waiting to borrow a connection from the pool. These are three separate layers; do not use the same value to mask errors at another layer.

## 6. Complete Lab: Java 17, Spring Boot, JDBC, and H2

This lab uses **Spring Boot 3.5.0**, Java 17+, Spring JDBC, in-memory H2, and JUnit 5. It **does not** run sleeping/lock-waiting SQL to force a real timeout; instead, it inspects the `Statement.getQueryTimeout()` value reported by the H2 driver **right before executing a `SELECT 1`**. This approach is less timing-sensitive and clearly shows which setting the JDBC tooling applied.

Specifically, the lab covers six scenarios:

1. Fixed template query timeout of 7 seconds when there is no transaction deadline.
2. A 20-second transaction timeout **overrides the template's query timeout** with remaining time.
3. Manual JDBC explicitly sets 3 seconds; without calling the helper it keeps 3 seconds even inside a transaction.
4. Manual JDBC calling `DataSourceUtils.applyTransactionTimeout` is synchronized with the transaction's time budget by Spring.
5. Standalone inner `REQUIRED(timeout=5)` creates a 5-second deadline.
6. Inner `REQUIRED(timeout=5)` joining outer `timeout=60` does not replace the deadline with 5 seconds.

### 6.1. Project Structure

~~~text
jdbc-statement-timeout-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/timeoutlab/
    │   │   ├── TimeoutLabApplication.java
    │   │   ├── StatementProbe.java
    │   │   ├── TimeoutCasesService.java
    │   │   ├── ShortTimeoutService.java
    │   │   └── OuterTimeoutService.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/timeoutlab/
            └── StatementTimeoutTest.java
~~~

The lab only needs `SELECT 1`, so **no `schema.sql`** or seed data is required. Java code belongs to package `com.example.timeoutlab` in all files.

### 6.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>jdbc-statement-timeout-lab</artifactId>
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
</project>
~~~

### 6.3. `application.properties`

~~~properties
spring.datasource.url=jdbc:h2:mem:timeout_lab;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
~~~

H2 is the test database. `DB_CLOSE_DELAY=-1` keeps the DB alive until the JVM exits; this exercise does not rely on persistent data. JDBC settings are tested with H2, without claiming every driver responds identically.

### 6.4. `TimeoutLabApplication.java`: Same `DataSource` and Transaction Manager

~~~java
package com.example.timeoutlab;

import javax.sql.DataSource;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBootApplication
public class TimeoutLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(TimeoutLabApplication.class, args);
    }

    @Bean
    public PlatformTransactionManager transactionManager(
            DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    public JdbcTemplate jdbcTemplate(DataSource dataSource) {
        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.setQueryTimeout(7);
        return jdbc;
    }
}
~~~

Here we declare **one transaction manager** for the H2 `DataSource` and one `JdbcTemplate` using that **same DataSource**. `JdbcTemplate.setQueryTimeout(7)` configures the template for statements outside a transaction deadline. Inside a transaction with a timeout, Spring's `DataSourceUtils.applyTimeout` uses remaining transaction time and can override 7.

Note: if using Spring Boot's auto-configured `JdbcTemplate` instead of a manually declared bean, you can configure query timeout via properties as supported by that Boot version; this lab uses a Java bean for clarity.

### 6.5. `StatementProbe.java`: Observing the Executing Statement

~~~java
package com.example.timeoutlab;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.Objects;

import javax.sql.DataSource;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.PreparedStatementCallback;
import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.stereotype.Component;

@Component
public class StatementProbe {
    private final JdbcTemplate jdbc;
    private final DataSource dataSource;

    public StatementProbe(JdbcTemplate jdbc, DataSource dataSource) {
        this.jdbc = jdbc;
        this.dataSource = dataSource;
    }

    // JdbcTemplate applies statement settings before calling this callback.
    public int templateQueryTimeout() {
        Integer seconds = jdbc.execute(
            "SELECT 1",
            (PreparedStatementCallback<Integer>) statement -> {
                int configured = statement.getQueryTimeout();
                try (ResultSet rs = statement.executeQuery()) {
                    if (!rs.next()) {
                        throw new SQLException("SELECT 1 returned no row");
                    }
                }
                return configured;
            }
        );
        return Objects.requireNonNull(seconds, "No timeout returned");
    }

    // Manual JDBC code: can choose whether to call the helper.
    public int manualStatement(boolean applySpringTimeout) {
        Connection connection = DataSourceUtils.getConnection(dataSource);
        try (Statement statement = connection.createStatement()) {
            statement.setQueryTimeout(3);

            if (applySpringTimeout) {
                DataSourceUtils.applyTransactionTimeout(
                    statement, dataSource
                );
            }

            int configured = statement.getQueryTimeout();

            try (ResultSet rs = statement.executeQuery("SELECT 1")) {
                if (!rs.next()) {
                    throw new SQLException("SELECT 1 returned no row");
                }
            }
            return configured;
        } catch (SQLException ex) {
            throw new IllegalStateException(
                "JDBC statement inspection failed", ex
            );
        } finally {
            DataSourceUtils.releaseConnection(connection, dataSource);
        }
    }
}
~~~

This is a complete Java 17 class; the `PreparedStatement` import could be removed since the callback already receives the typed statement, though an unused import causes no compilation error. `templateQueryTimeout()` reads `getQueryTimeout()` **inside `JdbcTemplate`'s callback**, after `applyStatementSettings` and before executing `SELECT 1`.

`manualStatement(...)` uses `DataSourceUtils.getConnection`/`releaseConnection` to acquire a transaction-aware connection. It creates a JDBC `Statement` and sets 3 seconds via standard JDBC, then **only when requested** calls Spring's `applyTransactionTimeout`. That way you can compare the same raw JDBC code with vs. without Spring's bridge, rather than mistakenly assuming "once using Spring's connection, statements automatically have the timeout".

**Important:** applying timeout must be done **each time a new statement is created**. Calling `DataSourceUtils.getConnection` on the right resource solves **joining the transaction**, yet does not mean every statement created with `connection.createStatement` automatically receives the deadline unless a helper or supporting wrapper is used.

### 6.6. `TimeoutCasesService.java`: Standard Transaction Checks

~~~java
package com.example.timeoutlab;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TimeoutCasesService {
    private final StatementProbe probe;

    public TimeoutCasesService(StatementProbe probe) {
        this.probe = probe;
    }

    // No service transaction. Template uses 7 seconds.
    public int templateOutsideTransaction() {
        return probe.templateQueryTimeout();
    }

    @Transactional(timeout = 20, readOnly = true)
    public int templateInsideTransaction() {
        return probe.templateQueryTimeout();
    }

    // Same 20-second transaction, yet raw Statement keeps 3 seconds.
    @Transactional(timeout = 20)
    public int manualWithoutSpringHelper() {
        return probe.manualStatement(false);
    }

    // Same transaction, helper passes remaining time to Statement.
    @Transactional(timeout = 20)
    public int manualWithSpringHelper() {
        return probe.manualStatement(true);
    }
}
~~~

`StatementProbe` does not put `@Transactional` on itself; its methods run inside the scope opened by `TimeoutCasesService`. Because the caller (the test) invokes `TimeoutCasesService`'s public methods through the Spring bean proxy, `@Transactional` on the service takes effect. Do not instantiate `new TimeoutCasesService(...)` in tests.

### 6.7. `ShortTimeoutService.java` and `OuterTimeoutService.java`: Demonstrating Transaction Joining

File `src/main/java/com/example/timeoutlab/ShortTimeoutService.java`:

~~~java
package com.example.timeoutlab;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Service
public class ShortTimeoutService {
    public record TimeoutView(
        boolean newTransaction,
        int queryTimeoutSeconds
    ) {}

    private final StatementProbe probe;

    public ShortTimeoutService(StatementProbe probe) {
        this.probe = probe;
    }

    @Transactional(
        propagation = Propagation.REQUIRED,
        timeout = 5
    )
    public TimeoutView inspect() {
        boolean newTransaction = TransactionAspectSupport
            .currentTransactionStatus()
            .isNewTransaction();

        return new TimeoutView(
            newTransaction,
            probe.templateQueryTimeout()
        );
    }
}
~~~

File `src/main/java/com/example/timeoutlab/OuterTimeoutService.java`:

~~~java
package com.example.timeoutlab;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterTimeoutService {
    private final ShortTimeoutService inner;

    public OuterTimeoutService(ShortTimeoutService inner) {
        this.inner = inner;
    }

    @Transactional(timeout = 60)
    public ShortTimeoutService.TimeoutView callInnerRequired() {
        return inner.inspect();
    }
}
~~~

When the test calls `ShortTimeoutService.inspect()` **standalone**, `REQUIRED(timeout=5)` must start a new transaction, `newTransaction=true`, and the statement via `JdbcTemplate` receives the remaining portion of 5 seconds (typically 1 to 5 if SQL starts promptly).

When the test calls `OuterTimeoutService.callInnerRequired()`, outer opens a **60-second** deadline, then calls inner `REQUIRED(timeout=5)`. Because inner **joins** the outer transaction, `newTransaction=false`, and the statement's query timeout follows outer's **remaining time**, typically greater than 5 seconds absent unusual delays. This tests the difference between **annotation declared on inner** and **actual physical timeout managed by Spring**.

These tests do not call `Thread.sleep`; they verify the timeout applied to the statement rather than artificially creating a slow SQL command.

### 6.8. `StatementTimeoutTest.java`: Six Integration Tests

~~~java
package com.example.timeoutlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class StatementTimeoutTest {
    @Autowired
    private TimeoutCasesService cases;

    @Autowired
    private ShortTimeoutService shortService;

    @Autowired
    private OuterTimeoutService outer;

    private static void between(int value, int min, int max) {
        assertTrue(
            value >= min && value <= max,
            "Expected timeout in [" + min + ", " + max
                + "], actual=" + value
        );
    }

    @Test
    void templateWithoutTransactionUsesSevenSeconds() {
        assertEquals(7, cases.templateOutsideTransaction());
    }

    @Test
    void transactionBudgetOverridesConfiguredTemplateTimeout() {
        int observed = cases.templateInsideTransaction();
        between(observed, 1, 20);
    }

    @Test
    void manuallyConfiguredStatementStaysAtThreeWithoutBridge() {
        assertEquals(3, cases.manualWithoutSpringHelper());
    }

    @Test
    void manualStatementWithSpringBridgeReceivesTransactionTime() {
        int observed = cases.manualWithSpringHelper();
        between(observed, 1, 20);
    }

    @Test
    void standaloneRequiredUsesItsOwnFiveSecondDeadline() {
        ShortTimeoutService.TimeoutView result =
            shortService.inspect();

        assertTrue(result.newTransaction());
        between(result.queryTimeoutSeconds(), 1, 5);
    }

    @Test
    void innerRequiredDoesNotReplaceOuterSixtySecondDeadline() {
        ShortTimeoutService.TimeoutView result =
            outer.callInnerRequired();

        assertFalse(result.newTransaction());
        between(result.queryTimeoutSeconds(), 1, 60);
        // On a normally running machine, since outer just opened 60 seconds,
        // the observed value is usually greater than 5 seconds.
    }
}
~~~

Note a measurement detail: `queryTimeoutSeconds` is the **remaining value when the statement is created**, not a constant always strictly equal to 20, 5, or 60. Thus tests assert a range rather than forcing equality to the full deadline. If an unusually slow environment causes the time budget to expire before the query runs, Spring may throw a timeout error; that is why real lifetime tests need dedicated design rather than treating sleep results as absolute truth.

In the last test, `newTransaction=false` directly confirms inner is joining outer. Combined with Spring's explanation of propagation and `getQueryTimeout()`, when execution is not delayed, the statement receives the **remaining outer deadline** rather than inner's 5 seconds. If you want to test exact seconds with strict assertions, you must carefully control the scheduler and test clock mechanism.

**Do not annotate the test class with `@Transactional`.** If Spring Test opens an outer transaction automatically, `templateOutsideTransaction()` and `shortService.inspect()` will no longer be standalone scenarios as intended; that is one of the most common traps when testing propagation/timeouts.

### 6.9. Running the Project

Requires JDK 17+, Maven 3.9+, and ability to download dependencies:

~~~bash
java -version
mvn -version
mvn test
~~~

With compatible Spring/H2 drivers as chosen in the code, expect **6 tests pass, 0 failures, 0 errors**. This is an **expected result from the code**, not a log from a live run executed in this lesson. The assertions test passing the **setting** down to JDBC, without attempting to trigger SQL cancellation. On the target database, if you must verify an overdue statement is canceled, write a separate integration test with controlled slow SQL/lock waits.

### 6.10. What Is Proven and Not Proven

| Test | Proven in the H2 Environment | Not Yet Proven |
| --- | --- | --- |
| Template without transaction | Statement created by template has `getQueryTimeout=7` | Every SQL is canceled by the driver right at second 7. |
| Template inside `transaction=20` | Statement receives a time budget in range 1–20 from the transaction | Java thread is automatically interrupted at second 20. |
| Raw JDBC without bridge | Statement keeps its manual 3-second setting | Spring applied the 20-second deadline to that statement. |
| Raw JDBC with bridge | Spring helper replaces setting with remaining transaction timeout | Another DB's timeout behaves identically to H2. |
| Standalone inner `REQUIRED=5` | New physical transaction exists and statement receives up to 5 seconds timeout | Timeout 5 applies to all other network calls. |
| Inner `REQUIRED` joining `outer=60` | Inner opens no new physical transaction | Inner `timeout=5` can change outer's deadline (it cannot). |

The goal of the lab **is not to prove how fast `SELECT 1` runs**, but to prove **the bridge from Spring transaction timeout → JDBC statement setting**.

## 7. When Does Spring Not Apply Query Timeout Automatically?

### 7.1. Using a Library That Manages JDBC Statements Itself

Some libraries create statements using their own connections or bypass Spring helpers. Even when the outer method has `@Transactional(timeout=...)`, that library may **fail to join the right connection** or omit calling `setQueryTimeout`. To be sure, inspect how the library integrates transactions and statement configuration rather than guessing from the library name.

### 7.2. Calling `DataSource.getConnection` Directly, Not Transaction-Aware

In Spring-managed imperative JDBC code, prefer `JdbcTemplate` or `DataSourceUtils.getConnection`. Calling `dataSource.getConnection()` directly on a raw pool may borrow **a different connection** not bound to the current Spring transaction; query timeouts/commits/rollbacks can become detached from the business transaction.

If you must pass a `DataSource` to legacy code, `TransactionAwareDataSourceProxy` can be an integration adapter, though verify the API capabilities and timing applied by the wrapper. Do not close a Spring-bound connection manually with `connection.close()`.

### 7.3. Creating Statements Manually Yet Forgetting to Apply Timeout

`DataSourceUtils.getConnection` gets the right connection; it does not automatically set timeouts on every `Statement` you invoke on that connection. After `prepareStatement(...)` or `createStatement()`, call `DataSourceUtils.applyTransactionTimeout` if you want Spring to transfer the deadline to the statement via this mechanism.

### 7.4. Using JPA/Hibernate or R2DBC

In JPA/Hibernate, Spring `@Transactional(timeout=...)` may be forwarded via provider/dialect or query timeout APIs through another mechanism; outcomes also depend on `JpaTransactionManager`, `EntityManager`, query hints/provider settings, and the database. Do not use `JdbcTemplate` code as proof that a native/JPQL JPA query is guaranteed the exact same query timeout.

Reactive `R2dbcTransactionManager` uses different resources and contexts from thread-bound JDBC. It does not create `java.sql.Statement`, so `DataSourceUtils.applyTransactionTimeout` is not the API for managing query timeouts in reactive drivers.

### 7.5. Inner Transaction Is Not a New Transaction

`@Transactional(timeout=2)` in a `REQUIRED` method normally does not apply if an outer transaction already exists. Put timeouts on the **transaction owner** or configure statement-level timeouts in the appropriate scope. Turning on `REQUIRES_NEW` solely for a shorter SQL timeout can cause unintended independent commits.

## 8. When a Query Timeout Actually Happens: How Should You Respond?

Suppose the JDBC driver canceled a query, or the server returned a timeout error. Steps to take:

1. **Record the error and root cause**: distinguish JDBC `SQLTimeoutException`, Spring JDBC translated exceptions, lock wait timeouts, serialization failures, server connection loss, or pool timeouts.
2. **Determine if the transaction is still usable**: some databases place the transaction in an error state after statement failure; do not keep issuing SQL and committing as if nothing happened.
3. **Decide rollback per business logic**: `@Transactional` rolls back by default on `RuntimeException` and `Error`; Spring's `DataAccessException` is a runtime exception. If code catches/swallows the error and returns normally, the interceptor may not roll back automatically unless the transaction is already rollback-only.
4. **Do not retry blindly forever**: slow SQL due to missing indexes, deadlocks, or contention can repeat. Retrying the whole operation requires idempotency, proper backoff, and observing committed state.
5. **Place timeouts at the right layer**: slow queries from execution plans need indexes/SQL tuning; pool exhaustion needs pool sizing/tuning; lock contention needs transaction/locking strategy.

For example, an error in a controller may turn into HTTP 504 when upstream takes too long, yet **HTTP 504 does not mean the database transaction definitely rolled back**. If a request is aborted after the DB already committed, clients must handle duplicate-retry risks with request IDs/idempotency.

### Why Shouldn't You Expect `Thread.interrupt()`?

JDBC drivers usually perform query cancellation via DB/driver-specific mechanisms. `@Transactional(timeout)` does not issue `Thread.interrupt` across arbitrary Java segments of a method. Running CPU-heavy work or sleeping does not mean the statement deadline is actively checked. Measure timeouts at the statement and test with real queries/locks if needed.

## 9. Implementation Checklist for Real Projects

Before relying on timeouts as a production safeguard:

1. **Identify the transaction owner**: which method opens the physical transaction, and what timeout is declared there?
2. **Verify the interceptor/proxy**: are there self-invocations, manually `new`-ed beans, or cross-thread calls?
3. **Identify manager and resource**: `DataSourceTransactionManager` or another manager, sharing the same `DataSource` with JDBC code?
4. **Classify the JDBC API**: `JdbcTemplate`/`NamedParameterJdbcTemplate`, ORM, raw JDBC, or third-party library?
5. **Check what was applied to the statement**: `JdbcTemplate.getQueryTimeout` is template config; `Statement.getQueryTimeout` on the executing statement shows the final JDBC setting.
6. **Distinguish transaction override**: with a transaction deadline, `JdbcTemplate.setQueryTimeout(7)` can be overridden by **remaining transaction timeout**.
7. **If using raw JDBC**: acquire connections via `DataSourceUtils` and apply timeout per required statement.
8. **Test the target driver/database**: try controlled slow statements and lock waits; record exception types/SQLStates, rollback, and cancellation latency.
9. **Check other timeouts**: pool acquisition, network, DB statement/lock timeout, HTTP timeout; do not mix seconds and milliseconds.
10. **Design retries and observability**: duration/timeout count metrics, logs with correlation IDs, rollback verification, indexes/SQL plans, and idempotency.

Keep operational costs in mind: too short a timeout causes false errors under high DB load; too long holds locks/connections too long. Numbers should reflect latency SLOs, system capacity, and business goals, not an arbitrary constant across all query types.

## 10. Self-Check Questions

1. **Does `@Transactional(timeout=20)` automatically interrupt the Java thread after 20 seconds?** — No; it is a transaction time budget enforced by the manager/resource to the extent possible, commonly translated into a JDBC statement query timeout when using compatible tools.
2. **Is `JdbcTemplate.setQueryTimeout(7)` overridden by a transaction `timeout=20`?** — Yes; Spring documentation notes remaining transaction timeout overrides template query timeout when the transaction has a deadline.
3. **Which API sets a JDBC statement timeout?** — `Statement.setQueryTimeout(int seconds)`, depending on driver support.
4. **Does raw JDBC calling `DataSourceUtils.getConnection` automatically receive statement timeouts?** — Not guaranteed; you need `DataSourceUtils.applyTransactionTimeout` on each statement if you want Spring's mechanism to apply the deadline.
5. **What is the unit of `Statement.setQueryTimeout`?** — Whole seconds; JDBC `0` usually means no separate limit from this API.
6. **Does `@Transactional(timeout=5)` on an inner `REQUIRED` reset the deadline when outer has `timeout=60`?** — Usually no; inner joins the already opened outer physical transaction.
7. **Is a 7-second query timeout the same as a 7-second connection-pool timeout?** — No: one bounds statement execution, the other bounds waiting to borrow a connection.
8. **If the driver cancels SQL after timeout, do all databases return exact `SQLTimeoutException`?** — No; drivers/engines and Spring exception translation can differ.
9. **Why didn't the test in this lesson use `Thread.sleep(25000)`?** — Because sleep measures Java time, without proving the statement received `setQueryTimeout` or that the server actually cancels SQL.
10. **Is H2 returning `getQueryTimeout=20` enough to guarantee PostgreSQL cancels SQL the same way?** — No; you must test against the production database/driver and real queries.
11. **How does `readOnly` relate?** — `readOnly=true` can help optimize, yet does not automatically apply statement timeouts or replace database permissions.
12. **If code swallows the timeout exception and returns normally, is Spring guaranteed to roll back?** — No; you must check rollback-only state, exception propagation, and rollback rules.
13. **Can `JdbcClient` using underlying JDBC templates benefit from timeouts?** — Yes, when actually using the same Spring-managed templates/resources; still verify the path and settings.
14. **Why must the manager and helper use the exact same `DataSource`?** — To locate the right resource holder/deadline of the running transaction.

## 11. Summary

**JDBC statement timeout does not automatically appear on every SQL query simply because a method has `@Transactional(timeout=...)`.** In Spring JDBC, the proper mechanism is:

~~~text
@Transactional(timeout = N) on a method opening a new transaction
              |
              v
Transaction manager / DataSource sharing the same resource
              |
              v
Statement created by JdbcTemplate
OR raw JDBC code calling DataSourceUtils.applyTransactionTimeout
              |
              v
JDBC Statement.setQueryTimeout(remaining seconds)
              |
              v
Driver/DB executes per capability, returning result or exception
~~~

A sound design **separates transaction deadlines from query timeouts**, **places limits at the right layer**, **ensures SQL uses transaction-aware tooling**, and **verifies behavior on the target driver/database**.

### Official References

- [Spring Framework — Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)
- [Spring Framework — JDBC Core Classes](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html)
- [Spring Framework — DataSourceUtils API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html)
- [Spring Framework — JdbcTemplate API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html)
- [Spring Framework — @Transactional API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html)
- [Java SE 17 — Statement.setQueryTimeout](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Statement.html#setQueryTimeout(int))
