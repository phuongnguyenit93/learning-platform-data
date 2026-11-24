# Isolation only takes effect when supported by the manager

## 1. Main point: annotations state a request; the manager applies it

In Spring Framework, configuring:

~~~java
@Transactional(isolation = Isolation.SERIALIZABLE)
public void placeOrder() {
    // SQL statements running inside the business transaction.
}
~~~

does not mean Spring can always force every database to execute `SERIALIZABLE`. This is only **an isolation request** in the transaction definition. Whether it takes effect depends on the **transaction manager**, resource type, JDBC/ORM/reactive driver, database, and when the transaction starts.

For the requested isolation level to actually take effect, all of the following must hold:

1. **The call is handled by the transaction interceptor**: the method is called through a Spring-managed proxy or equivalent transaction mechanism, not merely annotated in source code.
2. **A new physical transaction is started**: custom isolation is designed primarily for `Propagation.REQUIRED`/`REQUIRES_NEW` when opening a new transaction, not for changing a running transaction's level upon entering an inner method.
3. **The manager supports custom isolation**: e.g., `DataSourceTransactionManager`/`JdbcTransactionManager` have mechanisms using JDBC connections; JPA/JTA managers have different restrictions.
4. **The driver and database support the request**: they may reject it, normalize it per engine capabilities, or implement different semantics.
5. **SQL statements actually use the resource participating in the transaction**: if code grabs a separate connection or another datasource, the Spring-managed transaction's isolation level does not necessarily cover them.

The Java snippet at the top is a **snippet**, not standalone runnable because it lacks imports, class, and infrastructure. Section 6 provides a complete Maven/Spring Boot/JDBC/H2/JUnit example.

### Chain from declaration to execution

~~~text
@Transactional(isolation = SERIALIZABLE)
                  |
                  v
Is transaction interceptor called through proxy?
                  |
                  v
PlatformTransactionManager
                  |
             Does T1 already exist?
                  |
          +-------+---------+
          |                 |
       T1 exists          No T1 yet
          |                 |
       REQUIRED          Create new T1
       joins T1             |
          |                 v
       Keeps T1's        Manager prepares resource
       level             and requests isolation
          |                 |
          +----------+------+
                     |
             JDBC / JPA / JTA / R2DBC
                     |
             Driver and DB engine
                     |
          Level supported or error
                     |
         SQL executes on actual resource
~~~

If the manager does not support custom isolation, the request may be **rejected with an exception**. Never assert that Spring always silently downgrades isolation. On the other hand, the driver may accept the configuration call while the DB interprets each level under its own semantics: **an accepted level does not guarantee every anomaly follows a single simplified table across all engines**.

## 2. What does isolation protect against in concurrent transactions?

Isolation describes data visibility relationships between transactions. Commonly cited phenomena:

- **Dirty read**: reading uncommitted data from another transaction.
- **Non-repeatable read**: re-reading the same row in one transaction and seeing a different value because another transaction committed in between.
- **Phantom read**: re-executing a predicate query and seeing the result set change due to concurrent writes.
- **Serialization anomaly**: the outcome of concurrently executing transactions is not equivalent to any valid serial execution order. Patterns such as write skew require examining both business constraints and engine semantics.

Spring provides the `org.springframework.transaction.annotation.Isolation` enum with common levels:

| Level | Theoretical meaning | Important caveat |
| --- | --- | --- |
| `DEFAULT` | Use the default level from the transaction infrastructure/database | **Does not mean READ_COMMITTED on every system**. |
| `READ_UNCOMMITTED` | Weakest requested level in common SQL classification | Some engines disallow dirty reads and map it to another level. |
| `READ_COMMITTED` | Does not read uncommitted data in the common model | Does not automatically eliminate all races or non-repeatable reads. |
| `REPEATABLE_READ` | Aims for consistent re-reads of the same row | Snapshot/locking and phantom behavior depend on the DB. |
| `SERIALIZABLE` | Committed transaction outcomes equivalent to a serial schedule | May have to wait, abort, or retry due to conflicts. |

**Do not apply the SQL isolation table as an identical implementation guarantee across every RDBMS.** For instance, PostgreSQL handles `READ_UNCOMMITTED` equivalently to `READ_COMMITTED`. MySQL/InnoDB, PostgreSQL, and H2 have different snapshot/locking strategies. Nor does an isolation level replace constraints, conditional updates, idempotency, or authorization checks.

### Business example

Two transactions concurrently check inventory and place orders. Merely writing:

~~~java
@Transactional(isolation = Isolation.SERIALIZABLE)
public void reserve() {
    // SELECT stock; if enough -> UPDATE stock.
}
~~~

does not prove the application prevents overselling. You must also verify that the manager actually applies isolation, code accesses the right DB, how the engine handles conflicts, whether rollback/retry work properly, and whether there is a conditional update `WHERE stock >= ?` or an appropriate constraint.

## 3. Capabilities of each transaction manager

`PlatformTransactionManager` is a general abstraction, **not a promise that every implementation supports all isolation levels**.

### 3.1. JDBC: DataSourceTransactionManager and JdbcTransactionManager

With a JDBC `DataSource`, `DataSourceTransactionManager` can request custom isolation when starting a new transaction by preparing the JDBC `Connection`. `JdbcTransactionManager` is an extended variant that preserves this JDBC capability and adds transaction exception translation tailored for `JdbcTemplate`.

At the JDBC layer, the corresponding operation is essentially:

~~~java
connection.setTransactionIsolation(
    java.sql.Connection.TRANSACTION_SERIALIZABLE
);
~~~

This is a **low-level snippet** that should not be called directly inside a Spring-managed method. The Spring transaction manager also coordinates auto-commit, connection binding, rollback/commit, and restoring connection state on completion.

`JdbcTemplate` uses `DataSourceUtils` to obtain the connection participating in the current transaction. If you manually call `dataSource.getConnection()` to grab a separate connection and write with it, you can bypass the Spring-managed resource.

### 3.2. JPA: JpaTransactionManager and JpaDialect

When using JPA, the transaction manager must coordinate with the JPA `EntityManager`, provider, and `JpaDialect`. Per Spring documentation, an appropriate `JpaDialect` can support advanced capabilities such as **custom isolation**, timeouts, and JDBC connection access. `DefaultJpaDialect` does not provide all of those advanced capabilities.

Consequently:

- Do not conclude that **every JpaTransactionManager can apply every isolation level**.
- Nor conclude that **every JpaTransactionManager is completely incapable of applying them**; having `HibernateJpaDialect`/vendor adapters and underlying JDBC infrastructure changes what is supported.
- When moving from plain JDBC to JPA, verify the actual configuration and write integration tests on the target provider rather than simply keeping the `@Transactional` annotation.

### 3.3. JTA: coordinator with its own limitations

`JtaTransactionManager` coordinates a JTA environment, typically involving a transaction coordinator/container. Spring documentation notes that JTA **does not support JDBC custom isolation levels through the same mechanism as DataSourceTransactionManager**. Transactions still commit/roll back, yet custom isolation requests through Spring are not automatically applied.

If a transaction manager does not support a custom level, opening the transaction may throw an exception rather than silently falling back to the default level. Inspect the root cause; do not swallow configuration errors and let code proceed under a false assumption of safety.

### 3.4. R2DBC/reactive

`R2dbcTransactionManager` coordinates reactive transactions using the reactive abstraction rather than thread-bound JDBC `Connection`s as in the lab. Applying isolation depends on the reactive manager, R2DBC driver, and database. The `JdbcTemplate` snippets below do **not** apply to reactive code.

### Comparison table

| Infrastructure | Isolation application path | What to verify |
| --- | --- | --- |
| JDBC + `DataSourceTransactionManager`/`JdbcTransactionManager` | JDBC Connection when creating physical transaction | Driver/DB support, same DataSource, right proxy |
| JPA + `JpaTransactionManager` | JPA provider / `JpaDialect` / JDBC when supported | Dialect, vendor, transaction configuration |
| JTA + `JtaTransactionManager` | Transaction coordinator, differs from local JDBC | Whether custom isolation is actually supported or rejected |
| R2DBC + reactive manager | R2DBC transaction definition/driver | Reactive resource and driver/DB capabilities |
| Custom manager or wrapper | Depends on implementation code | Never assume support just because it implements `PlatformTransactionManager` |

## 4. Why can an inner @Transactional not override an outer one?

Suppose there are two Spring beans:

~~~java
@Service
class OuterService {
    private final InnerService inner;

    OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional(isolation = Isolation.SERIALIZABLE)
    public void outer() {
        inner.work();
    }
}

@Service
class InnerService {
    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.READ_COMMITTED
    )
    public void work() {
        // Participating in outer's physical transaction.
    }
}
~~~

This is **illustrative code without imports**, not a standalone project. If outer opens transaction T1 with `SERIALIZABLE` isolation, when inner `REQUIRED` is invoked through the proxy, it joins **T1** rather than asking the connection mid-flight to switch isolation to `READ_COMMITTED`.

Distinguish:

- **Metadata resolution:** an annotation directly on a method can take precedence over a class-level annotation for that specific invocation.
- **Physical transaction lifetime:** an already-open T1 has a real isolation level; inner `REQUIRED` by default uses T1's settings.
- **Logical scope:** inner still has its own transaction advice scope and can have rollback rules, yet does not create a new physical transaction.

### Default mode and strict validation

For managers extending `AbstractPlatformTransactionManager`, `setValidateExistingTransaction(false)` is typically the default: **lenient participation** — inner declares a different isolation yet still joins outer, keeping outer's level.

If `setValidateExistingTransaction(true)` is enabled, the manager can **reject** inner `READ_COMMITTED` trying to join outer `SERIALIZABLE` and throw `IllegalTransactionStateException`. The goal is detecting mismatches, **not forcing outer to switch to inner's level**.

If inner uses `REQUIRES_NEW`, Spring suspends outer and opens a separate transaction T2; the manager can apply T2's isolation when the infrastructure supports it. However, T2 commits independently, incurs a separate connection cost, and can break business atomicity. Do not use `REQUIRES_NEW` as a default isolation workaround when operations truly need to commit together.

| Call pattern | Physical transaction | Isolation outcome in example |
| --- | --- | --- |
| Call inner `REQUIRED(READ_COMMITTED)` with **no outer** | New T1 | JDBC manager can apply READ_COMMITTED |
| Outer `SERIALIZABLE` calls inner `REQUIRED(READ_COMMITTED)` | Shared T1 | Inner usually uses T1's SERIALIZABLE |
| Outer `SERIALIZABLE` calls inner `REQUIRES_NEW(READ_COMMITTED)` | T1 suspended; new T2 | Inner T2 can use READ_COMMITTED; outer T1 remains SERIALIZABLE |
| Strict validation, inner `REQUIRED` differs from T1 isolation | Existing T1; join rejected | Exception, **does not change T1's isolation** |

## 5. What should you inspect to prove isolation was applied?

Do not merely log the annotation attribute. There are three distinct levels of information:

1. **Requested value in `@Transactional`:** the application's intent.
2. **Transaction metadata stored by Spring:** `TransactionSynchronizationManager.getCurrentTransactionIsolationLevel()` can reflect what Spring recorded. For `DEFAULT`, metadata may be `null`.
3. **Level reported by the real JDBC connection:** `Connection.getTransactionIsolation()` read on **the connection participating in the transaction** via `JdbcTemplate.execute(ConnectionCallback)` or `DataSourceUtils`.

Level 3 reflects the JDBC setting closer to the database, yet is still not enough to prove a specific anomaly is prevented. To be sure of semantics, run **two concurrent transactions against the target database** and inspect outcomes/exceptions.

Example code querying the connection inside `JdbcTemplate`:

~~~java
Integer level = jdbcTemplate.execute(
    (ConnectionCallback<Integer>) connection ->
        connection.getTransactionIsolation()
);
~~~

This is a snippet (requires importing `ConnectionCallback` and having a `JdbcTemplate` bean). Do not grab a brand-new connection externally from the datasource and assume its level represents the running transaction.

The JDBC driver also provides:

~~~java
boolean supports = connection.getMetaData()
    .supportsTransactionIsolationLevel(
        java.sql.Connection.TRANSACTION_SERIALIZABLE
    );
~~~

This queries **whether the driver advertises support for that level**, not a test of which anomalies occur in practice. In the lab, combine these two checks with Spring's transaction status.

## 6. Runnable project: Spring Boot 3.5 / Java 17 / H2

This lab clearly separates **new transaction**, **joining outer**, and **strict manager**. It uses Java 17+, Spring Boot 3.5.0, Spring JDBC, in-memory H2, and JUnit 5. No separate database server installation is needed.

### 6.1. Directory structure

~~~text
isolation-manager-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/isolationlab/
    │   │   ├── IsolationLabApplication.java
    │   │   ├── IsolationView.java
    │   │   ├── InnerIsolationService.java
    │   │   └── OuterIsolationService.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/isolationlab/
            ├── NormalIsolationTest.java
            └── StrictIsolationTest.java
~~~

There is no `schema.sql` because this lab only reads isolation levels from the connection; the tests measure transaction configuration and **do not pretend to run a concurrency load test**.

### 6.2. File pom.xml

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
    <artifactId>isolation-manager-lab</artifactId>
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

### 6.3. File application.properties

~~~properties
spring.datasource.url=jdbc:h2:mem:isolation_manager_lab;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
lab.strict=false
~~~

H2 is only an in-memory JVM database, not production storage.

### 6.4. File IsolationLabApplication.java

~~~java
package com.example.isolationlab;

import javax.sql.DataSource;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBootApplication
public class IsolationLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(IsolationLabApplication.class, args);
    }

    @Bean
    public PlatformTransactionManager transactionManager(
            DataSource dataSource,
            Environment environment) {
        boolean strict =
            environment.getProperty("lab.strict", Boolean.class, false);

        DataSourceTransactionManager manager =
            new DataSourceTransactionManager(dataSource);
        manager.setValidateExistingTransaction(strict);
        return manager;
    }
}
~~~

We explicitly declare **a single `DataSourceTransactionManager`** for the exact `DataSource` used by `JdbcTemplate`. It is a JDBC manager supporting custom isolation. The two test classes run with two different `lab.strict` property values, so Spring creates two corresponding application contexts.

`setValidateExistingTransaction(true)` does not force inner's custom isolation onto outer; it causes mismatches against an existing transaction to be **rejected**. Never flip this flag on a singleton manager serving real traffic solely for experimentation.

### 6.5. File IsolationView.java

~~~java
package com.example.isolationlab;

import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.interceptor.TransactionAspectSupport;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public record IsolationView(
    boolean active,
    boolean newTransaction,
    int jdbcLevel
) {
    public static IsolationView capture(JdbcTemplate jdbc) {
        Integer level = jdbc.execute(
            (ConnectionCallback<Integer>) connection ->
                connection.getTransactionIsolation()
        );
        if (level == null) {
            throw new IllegalStateException("No JDBC level returned");
        }

        return new IsolationView(
            TransactionSynchronizationManager.isActualTransactionActive(),
            TransactionAspectSupport.currentTransactionStatus()
                .isNewTransaction(),
            level
        );
    }
}
~~~

`TransactionAspectSupport.currentTransactionStatus()` is called **inside a method wrapped by the transaction interceptor**, not outside the proxy. Using `JdbcTemplate` reads the transaction-bound connection. The `IsolationView` record is Java 17 and is not an MVCC snapshot.

### 6.6. File InnerIsolationService.java

~~~java
package com.example.isolationlab;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InnerIsolationService {
    private final JdbcTemplate jdbc;

    public InnerIsolationService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.READ_COMMITTED
    )
    public IsolationView requiredReadCommitted() {
        return IsolationView.capture(jdbc);
    }

    @Transactional(
        propagation = Propagation.REQUIRES_NEW,
        isolation = Isolation.READ_COMMITTED
    )
    public IsolationView requiresNewReadCommitted() {
        return IsolationView.capture(jdbc);
    }

    @Transactional(isolation = Isolation.DEFAULT)
    public IsolationView usingDefault() {
        return IsolationView.capture(jdbc);
    }
}
~~~

When `requiredReadCommitted()` is called directly from a test without an active transaction, it opens a new transaction and JDBC isolation is set to `READ_COMMITTED`. When it joins an outer `SERIALIZABLE` transaction, the connection still reports `SERIALIZABLE`. `requiresNewReadCommitted()` can start an independent transaction when needed.

### 6.7. File OuterIsolationService.java

~~~java
package com.example.isolationlab;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterIsolationService {
    public record Comparison(
        IsolationView before,
        IsolationView inner,
        IsolationView after
    ) {}

    private final InnerIsolationService inner;
    private final JdbcTemplate jdbc;

    public OuterIsolationService(
            InnerIsolationService inner,
            JdbcTemplate jdbc) {
        this.inner = inner;
        this.jdbc = jdbc;
    }

    @Transactional(isolation = Isolation.SERIALIZABLE)
    public Comparison callRequired() {
        IsolationView before = IsolationView.capture(jdbc);
        IsolationView inside = inner.requiredReadCommitted();
        IsolationView after = IsolationView.capture(jdbc);
        return new Comparison(before, inside, after);
    }

    @Transactional(isolation = Isolation.SERIALIZABLE)
    public Comparison callRequiresNew() {
        IsolationView before = IsolationView.capture(jdbc);
        IsolationView inside = inner.requiresNewReadCommitted();
        IsolationView after = IsolationView.capture(jdbc);
        return new Comparison(before, inside, after);
    }
}
~~~

Outer and inner reside in **two separate Spring beans**, ensuring calls go through the proxy and avoiding the `this.method()` self-invocation trap. The `before/inner/after` triple shows isolation before, during, and after the inner call **while the outer transaction remains active**.

### 6.8. File NormalIsolationTest.java

~~~java
package com.example.isolationlab;

import java.sql.Connection;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(properties = "lab.strict=false")
class NormalIsolationTest {
    @Autowired
    private InnerIsolationService inner;

    @Autowired
    private OuterIsolationService outer;

    @Autowired
    private JdbcTemplate jdbc;

    @Test
    void standaloneRequiredAppliesReadCommitted() {
        IsolationView v = inner.requiredReadCommitted();

        assertTrue(v.active());
        assertTrue(v.newTransaction());
        assertEquals(Connection.TRANSACTION_READ_COMMITTED,
                     v.jdbcLevel());
    }

    @Test
    void innerRequiredCannotOverrideSerializableOuter() {
        OuterIsolationService.Comparison r = outer.callRequired();

        assertTrue(r.before().active());
        assertTrue(r.inner().active());
        assertTrue(r.after().active());

        assertTrue(r.before().newTransaction());
        assertFalse(r.inner().newTransaction());

        assertEquals(Connection.TRANSACTION_SERIALIZABLE,
                     r.before().jdbcLevel());
        assertEquals(Connection.TRANSACTION_SERIALIZABLE,
                     r.inner().jdbcLevel());
        assertEquals(Connection.TRANSACTION_SERIALIZABLE,
                     r.after().jdbcLevel());
    }

    @Test
    void requiresNewGetsItsOwnIsolationAndOuterResumes() {
        OuterIsolationService.Comparison r = outer.callRequiresNew();

        assertTrue(r.inner().active());
        assertTrue(r.inner().newTransaction());

        assertEquals(Connection.TRANSACTION_SERIALIZABLE,
                     r.before().jdbcLevel());
        assertEquals(Connection.TRANSACTION_READ_COMMITTED,
                     r.inner().jdbcLevel());
        assertEquals(Connection.TRANSACTION_SERIALIZABLE,
                     r.after().jdbcLevel());
    }

    @Test
    void defaultUsesDataSourceConnectionSetting() {
        Integer outside = jdbc.execute(
            (ConnectionCallback<Integer>) connection ->
                connection.getTransactionIsolation()
        );

        IsolationView inTransaction = inner.usingDefault();

        assertTrue(inTransaction.active());
        assertTrue(inTransaction.newTransaction());
        assertEquals(outside.intValue(), inTransaction.jdbcLevel());
    }

    @Test
    void h2DriverReportsSerializableSupport() {
        Boolean supported = jdbc.execute(
            (ConnectionCallback<Boolean>) connection ->
                connection.getMetaData().supportsTransactionIsolationLevel(
                    Connection.TRANSACTION_SERIALIZABLE
                )
        );
        assertEquals(Boolean.TRUE, supported);
    }
}
~~~

These five tests demonstrate:

- A **new transaction** with the JDBC manager can apply `READ_COMMITTED`.
- Inner `REQUIRED` joining outer `SERIALIZABLE` does not alter outer's isolation.
- `REQUIRES_NEW` creates a new physical transaction with its own isolation, and outer resumes with its own isolation.
- `DEFAULT` does not enforce a fixed isolation value independent of the datasource.
- The H2 JDBC driver **advertises** support for `SERIALIZABLE`.

None of these tests run two competing transactions against a table, so do **not** treat them as proof of all anomaly/isolation behavior in a production system.

### 6.9. File StrictIsolationTest.java

~~~java
package com.example.isolationlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.IllegalTransactionStateException;

import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(properties = "lab.strict=true")
class StrictIsolationTest {
    @Autowired
    private OuterIsolationService outer;

    @Test
    void strictManagerRejectsJoiningWithDifferentIsolation() {
        assertThrows(
            IllegalTransactionStateException.class,
            outer::callRequired
        );
    }
}
~~~

In strict mode, outer opens `SERIALIZABLE` and inner `REQUIRED` requests `READ_COMMITTED`. The manager refuses **joining** with a different isolation rather than altering T1 to READ_COMMITTED.

**Do not confuse the strict test with testing a manager that does not support custom isolation:** strict validation checks **a participant's mismatch**; unsupported custom isolation is when the manager cannot apply a request to **a new transaction**. Those are two different failure causes.

Both test classes run in two separate Spring application contexts with their own properties; they do not write to tables, so no `schema.sql` is needed. If a real application has multiple transaction managers, ensure the test exercises the right manager.

### 6.10. Run and expected results

In the `isolation-manager-lab` directory, using JDK 17+ and Maven:

~~~bash
java -version
mvn -version
mvn test
~~~

If dependencies resolve and the environment is valid, Maven Surefire is expected to report **6 tests pass, 0 failures, 0 errors**. Test order, Spring logs, and execution duration can vary. This is **the expected result from the source code**, not an actual run log executed in this lesson.

| Test | Asserted value/phenomenon |
| --- | --- |
| `standaloneRequiredAppliesReadCommitted` | active=true, newTransaction=true, JDBC level=READ_COMMITTED |
| `innerRequiredCannotOverrideSerializableOuter` | SERIALIZABLE → SERIALIZABLE → SERIALIZABLE |
| `requiresNewGetsItsOwnIsolationAndOuterResumes` | SERIALIZABLE → READ_COMMITTED → SERIALIZABLE |
| `defaultUsesDataSourceConnectionSetting` | DEFAULT matches the datasource connection setting in the lab |
| `h2DriverReportsSerializableSupport` | JDBC metadata returns true |
| `strictManagerRejectsJoiningWithDifferentIsolation` | `IllegalTransactionStateException` |

## 7. When a manager does not support it: distinguishing failure modes

### 7.1. Transaction manager rejects custom isolation

A manager may support `commit/rollback` yet **not support custom isolation**. In that case, a request like `Isolation.SERIALIZABLE` can fail transaction startup, for example via `InvalidIsolationLevelException`; never assume Spring will silently apply a weaker level.

With JPA, inspect `JpaDialect`/provider; with JTA, check coordinator limits. Read the actual exception and root-cause logs from the running system.

### 7.2. JDBC driver does not support the requested level

A `DataSourceTransactionManager` may attempt to call `Connection.setTransactionIsolation(level)`, yet the driver/database rejects that `level`. Then the `SQLException` may be wrapped into a Spring transaction infrastructure exception. There is no single exception class name valid across every engine/driver/manager.

Check the driver via `DatabaseMetaData.supportsTransactionIsolationLevel(level)`, inspect the connection's actual level, and test the real database. Advertised metadata is a signal, not absolute proof of all concurrency semantics.

### 7.3. Database maps or implements isolation uniquely

Even when the request succeeds without error, database behavior may differ from a simple theoretical assumption. For example, PostgreSQL `READ_UNCOMMITTED` behaves like `READ_COMMITTED`. An engine may use snapshot isolation or locking rules affecting whether phantoms or write skew are observed.

Therefore, **do not translate an enum value into a universal concurrency promise across all databases**. For critical invariants, run multi-session/multi-transaction tests on the production engine and observe final results, exceptions, and retry paths.

## 8. Common mistakes

### 8.1. Putting SERIALIZABLE on an inner method while outer already opened a transaction

If inner is `REQUIRED`, it joins the existing physical transaction and does not change the level. A better fix is usually placing isolation on **the service facade opening the transaction**. When a new transaction is genuinely needed, consider `REQUIRES_NEW`, keeping in mind that independent commits can break overall atomicity.

### 8.2. Reading the wrong JDBC connection

Do not grab an arbitrary connection via `DataSource.getConnection()` and treat it as the connection in the Spring transaction. Use `JdbcTemplate` or `DataSourceUtils` to access the bound connection.

### 8.3. Confusing `Isolation.DEFAULT` with `READ_COMMITTED`

DEFAULT depends on the database, driver, pool configuration, and transaction infrastructure; it is not a single fixed constant. When targeting multiple databases, avoid hardcoding assumptions about the default level.

### 8.4. Instantiating a service with `new` or self-invocation

`@Transactional` requires the Spring interceptor. In proxy mode, `new SomeService(...)` or `this.someTransactionalMethod()` usually skips advice. You cannot rely on an isolation annotation to protect code if no transaction was opened.

### 8.5. Using the wrong transaction manager

Multiple datasources/managers can result in isolation being applied to resource A while SQL runs against resource B. Verify the default/qualified manager and connection path.

### 8.6. Thinking JDBC manager support means every DB supports it

Spring can call `setTransactionIsolation`, yet the driver/engine decides whether to accept that level. Never promise `READ_UNCOMMITTED` or `SERIALIZABLE` behaves identically across all DBs.

### 8.7. Enabling strict validation and thinking it upgrades isolation

`setValidateExistingTransaction(true)` **rejects** mismatches from an inner `REQUIRED` call; it does not alter the already-open transaction's isolation. Test strict mode separately in a lab to avoid accidentally altering production policy.

### 8.8. Assuming a JDBC-level test proves race protection

`Connection.getTransactionIsolation()` measures the setting reported by the connection. It does not prove whether transactions A and B in practice exhibit dirty reads, write skew, or serialization failures. Write independent concurrency tests when business correctness requires guarantees.

### 8.9. Raising isolation instead of implementing transaction retries

SERIALIZABLE can trigger waits, aborts, and retries. Production designs need **full-transaction** retries where appropriate, idempotency for repeatable requests, and constraints/validation protecting invariants.

### 8.10. Confusing isolation with rollback rules

`isolation` governs the concurrent read/write visibility environment; `rollbackFor`/`noRollbackFor` determine when Spring triggers rollback on exceptions. Stronger isolation does not automatically turn checked exceptions into rollbacks; the two sets of attributes are independent.

## 9. Decision and testing workflow

1. Identify the **business invariant** to protect and the anomalies to prevent.
2. Identify the **DB engine/version**, default isolation, driver, and connection pool.
3. Identify the **actual PlatformTransactionManager**; do not rely solely on the annotation name.
4. Place isolation on the method that **actually creates the physical transaction**.
5. Verify calls flow through the **Spring proxy** and SQL statements use the right resource.
6. Check whether the manager/driver/DB accept custom isolation.
7. Measure isolation on the JDBC connection **inside the transaction**, not on a random connection.
8. When an inner method declares a different level from outer, consider strict validation to catch conflicting configuration.
9. Write concurrent tests on the target engine, recording outcomes and serialization/deadlock errors.
10. Design appropriate rollback/retry/idempotency mechanisms rather than expecting an enum to guarantee everything.

## 10. Self-check questions

1. **Does `@Transactional(isolation=SERIALIZABLE)` automatically change the DB's isolation?** — No; there must be a new transaction, plus support from the manager and driver/DB.
2. **Where does `DataSourceTransactionManager` apply custom isolation?** — On the JDBC connection, e.g., `setTransactionIsolation` when starting the transaction.
3. **Can JPA always apply custom isolation?** — Not guaranteed; depends on `JpaDialect` and the provider.
4. **Does JTA support custom JDBC isolation the same way a JDBC manager does?** — Do not assume so by default; Spring documentation notes JTA's limitations.
5. **What happens when inner REQUIRED READ_COMMITTED joins outer SERIALIZABLE?** — Usually uses outer's SERIALIZABLE without lowering the level.
6. **What happens with inner REQUIRES_NEW READ_COMMITTED?** — The new transaction can use READ_COMMITTED if supported.
7. **Does enabling strict validation cause inner to override outer?** — No; the manager can throw `IllegalTransactionStateException`.
8. **Does Isolation.DEFAULT default to READ_COMMITTED?** — No, it depends on the underlying infrastructure.
9. **Is `getCurrentTransactionIsolationLevel()` the same as `getTransactionIsolation()`?** — Not necessarily; one is Spring metadata, the other is the setting reported by the JDBC connection.
10. **Does driver support for SERIALIZABLE prove no anomalies can happen?** — No; you must test concurrency on the exact DB engine.
11. **Can `@Transactional` work without passing through the Spring proxy?** — In proxy mode, calls bypassing the interceptor do not automatically apply transaction annotations.
12. **Will a manager that does not support custom isolation always silently ignore the request?** — No; it may throw an error and prevent the transaction from starting.
13. **Does strong isolation replace unique constraints and business validation?** — No; they complement each other.

## 11. Conclusion

**"Isolation only takes effect when supported by the manager"** is the boundary between **configuration intent in Java** and **actual runtime execution**. Spring merely coordinates via the chosen manager; the manager can only use capabilities provided by the resource/driver/database; and new isolation must be applied to **the right physical transaction being opened**.

To avoid a false sense of security, verify **the manager, transaction start point, proxy boundary, participating connection, driver support, and the real DB's concurrency semantics**.

### Official references

- [Spring Framework — @Transactional Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html)
- [Spring Framework — JDBC Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — AbstractPlatformTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html)
- [Spring Framework — JPA and JpaDialect](https://docs.spring.io/spring-framework/reference/data-access/orm/jpa.html)
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
