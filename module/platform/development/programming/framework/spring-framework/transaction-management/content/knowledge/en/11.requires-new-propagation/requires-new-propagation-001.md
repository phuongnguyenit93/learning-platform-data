# Suspending the Outer Transaction and Creating an Independent Physical Transaction with `REQUIRES_NEW`

## 1. The Problem and What You Need to Understand

In Spring Framework, `@Transactional(propagation = Propagation.REQUIRES_NEW)` means: **every time the method is handled by the transaction interceptor, it runs in a new physical transaction that is independent of any existing outer transaction**. If an outer transaction exists, Spring **suspends** it while the new transaction runs; after the inner transaction finishes (commits or rolls back), Spring **resumes** the outer transaction for execution to continue.

Let us call the outer transaction **T1** and the inner transaction **T2**.

```text
Caller -> OuterService.outer() [@Transactional(REQUIRED)]
          |
          | BEGIN physical T1 (JDBC Connection C1)
          | UPDATE business_row ... (uncommitted)
          |
          +---> InnerService.inner() [@Transactional(REQUIRES_NEW)]
          |       |
          |       | Suspend T1, retain T1's resource C1
          |       | BEGIN physical T2 (JDBC Connection C2)
          |       | UPDATE audit_row ...
          |       | COMMIT / ROLLBACK T2
          |       | Resume T1 (C1)
          |       v
          |
          | Continue in T1
          | COMMIT / ROLLBACK T1
          v
Caller
```

Business example: an order-creation service needs to write an independent operation log. If the order ultimately fails, a log record of the **execution attempt** may still need to exist. If the inner method writes the log in T2 and commits successfully before the outer T1 rolls back, **T2 is not rolled back along with it**. However, not every audit or outbox record fits `REQUIRES_NEW`: if an event must only be published when the order commits, separating transactions so the event exists even when the order rolls back can create inconsistent data.

After this lesson, you should be able to answer:

1. How does "Suspend T1" happen at the Spring/JDBC layer, and why is it not `Thread.suspend()`?
2. Why can T2 commit before T1, and why does rolling back T1 not erase the data T2 committed?
3. When T2 rolls back, must T1 roll back? How do Java exceptions still affect it?
4. Why does `REQUIRES_NEW` require an extra JDBC connection and risk exhausting the connection pool?
5. What causes the annotation to be present without creating T2: self-invocation, objects created with `new`, wrong `ApplicationContext`, or bypassing the Spring proxy?

## 2. Logical Scope, Physical Transaction, and Suspend

A **logical transaction scope** is the boundary Spring manages when a call is intercepted. A **physical transaction** is the actual resource-level transaction, such as a JDBC connection in transaction mode that is committed or rolled back by the database.

With the default `Propagation.REQUIRED`, if T1 already exists, an inner `@Transactional(REQUIRED)` method **joins T1**: the two methods may have **two logical scopes but only one physical transaction**. When the inner method finishes normally, it does not perform an independent physical commit.

With `Propagation.REQUIRES_NEW`, the inner method does not join T1. Spring creates a **new physical transaction T2**, temporarily moves T1's resources and synchronizations out of the active transaction context, and restores them when T2 finishes. With `DataSourceTransactionManager` in standard Spring JDBC, T1 retains connection C1, while T2 acquires a different connection C2.

### 2.1. Suspend Is Not Commit, Rollback, or Thread Suspension

- **Does not commit T1:** T1's updates remain uncommitted. Do not treat the start of the inner method as a safe checkpoint for the outer transaction.
- **Does not roll back T1:** T1 still exists; once the inner method finishes, the outer method resumes its work as before.
- **Does not release T1's locks:** connection C1 and T1's row locks may remain held; if inner T2 touches the same row locked by T1, it may have to wait.
- **Does not suspend the Java thread:** in the standard imperative model, the same Java thread enters the inner proxy, executes the inner method, and returns to the outer method. The thread is not paused via `Thread.suspend()`; Spring suspends the **transaction resource context**, not the execution thread.
- **Does not automatically return C1 to the pool:** the outer transaction can keep holding connection C1 while the inner transaction must acquire an additional C2.
- **Does not isolate every side effect:** T1/T2 only control resources enlisted with the matching transaction manager. Sent emails or HTTP requests do not automatically roll back with JDBC.

### 2.2. Concrete Timeline

```text
t0  Outer proxy creates T1, binds Connection C1 to the thread
t1  Outer executes UPDATE orders; changes are uncommitted
t2  Inner REQUIRES_NEW proxy is invoked
t3  Suspend T1: unbind T1's resources/synchronizations from the active context
t4  Create T2 and bind Connection C2 (different from C1)
t5  Inner executes UPDATE audit
t6  End T2: COMMIT or ROLLBACK T2, clean up T2 resources
t7  Resume T1: restore T1's connection/synchronizations
t8  Outer continues using C1
t9  Outer executes COMMIT or ROLLBACK T1
```

This happens at the transaction infrastructure layer; application code should not manually call `TransactionSynchronizationManager.unbindResource(...)` to simulate `REQUIRES_NEW`. With non-JDBC managers or resources, suspension details may differ, so do not assume the exact sequence above applies identically to every transaction manager.

## 3. Declaring `REQUIRES_NEW` Properly in Spring

Separate-bean service model:

```java
@Service
public class OrderService {
    private final AuditService auditService;

    public OrderService(AuditService auditService) {
        this.auditService = auditService;
    }

    @Transactional // Default REQUIRED -> creates T1 if none exists
    public void placeOrder() {
        // Write order in T1.
        auditService.recordAttempt(); // Goes through AuditService proxy.
        // Continue processing in T1.
    }
}

@Service
public class AuditService {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordAttempt() {
        // Write audit log in new T2.
    }
}
```

This is **illustrative code**, omitting repositories, imports, and full bean configuration. `AuditService` must be a Spring-managed bean in a context with transaction annotation infrastructure enabled. `OrderService` must receive the actual proxy of `AuditService`; Spring needs a transaction manager matching the datasource/ORM in use.

**Why split into two services?** In default Spring AOP proxy mode, if both methods are in the same class and `placeOrder()` calls `this.recordAttempt()`, the inner call bypasses the proxy, so `REQUIRES_NEW` **is not applied** to that invocation. Placing the annotation does not automatically weave an interceptor into an internal Java method call.

### 3.1. Two Entry Scenarios

| State before calling inner | What does Spring do with `REQUIRES_NEW`? |
| --- | --- |
| No current transaction | Starts a new physical transaction. There is no T1 to suspend. |
| T1 already opened by outer | Suspends T1, creates a new T2, finishes T2, resumes T1. |

If T2 in turn calls another `REQUIRES_NEW` method, Spring can suspend T2 as well to open T3. Deep nesting consumes more resources and increases the risk of connection pool exhaustion.

## 4. Independent Commit and Rollback — But Exceptions Do Not Disappear

Suppose two database rows start at `outer=0`, `inner=0`. Outer increments the `outer` row in T1, and inner increments the `inner` row in T2. The following outcomes demonstrate physical independence:

| T2 (inner) | How does outer handle it? | T1 (outer) | Final data |
| --- | --- | --- | --- |
| Succeeds, commits T2 | Outer completes | Commits | `outer=1, inner=1` |
| Succeeds, commits T2 | Outer later throws an unchecked exception | Rolls back | `outer=0, inner=1` |
| Fails, rolls back T2 | Outer catches the error and decides to continue | Commits | `outer=1, inner=0` |
| Fails, rolls back T2 | Exception propagates out of the outer method | Rolls back due to T1's rollback rule | `outer=0, inner=0` |

**Distinguish transaction independence from control-flow independence.** Rolling back inner T2 **does not automatically mark T1 rollback-only** merely because the two transactions have a caller-callee relationship. However, if inner throws a `RuntimeException` and outer does not catch it, the exception continues through the outer transaction interceptor: Spring may roll back T1 according to **T1's own rollback policy**. Therefore, the claim "`REQUIRES_NEW` guarantees outer always commits even if inner fails" is false.

Similarly, if inner T2 commits and outer T1 later rolls back, **T2 does not lose its commit**. If the application requires updates to live or die together, `REQUIRES_NEW` does not provide shared atomicity; use the same `REQUIRED` transaction or a more appropriate design.

## 5. Comparing Propagations to Choose Correctly

| Inner propagation | When T1 is active | Meaning |
| --- | --- | --- |
| `REQUIRED` | Joins T1 | Inner has no separate physical commit; a participating scope can mark T1 rollback-only. |
| `REQUIRES_NEW` | Suspends T1; creates independent T2 | Inner commits/rolls back independently; once inner T2 completes, T1 resumes. |
| `NESTED` (when supported) | Savepoint within the same T1 | Inner rollback can roll back to the savepoint; inner has no independent physical commit. |
| `NOT_SUPPORTED` | Suspends T1 and runs without a transaction | Does not create T2; SQL may auto-commit per statement. |
| `MANDATORY` | Requires an active transaction | Does not open T2; missing transaction throws an exception. |

Two points worth remembering: (1) `NOT_SUPPORTED` can also suspend T1, but it has **no** new transaction; (2) `NESTED` allows partial rollback via savepoints in some JDBC managers, yet if outer rolls back, nested inner changes are lost too. Only `REQUIRES_NEW` in the group above creates an **independent physical transaction** while outer has T1.

## 6. Complete Demo: Java 17+, Spring JDBC, and H2

We build a plain Java application using **Spring Framework 6.2.8**, **H2 2.3.232**, and Maven. No Spring Boot, HTTP server, or external database server is needed. The demo uses two distinct rows so T2 avoids waiting on a lock held by T1.

### 6.1. Project Files

```text
requires-new-demo/
├── pom.xml
└── src/main/java/example/RequiresNewDemo.java
```

```xml
<!-- pom.xml -->
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>requires-new-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-tx</artifactId>
            <version>6.2.8</version>
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
                <version>3.4.1</version>
                <configuration>
                    <mainClass>example.RequiresNewDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` provides ApplicationContext/configuration; `spring-jdbc` provides `JdbcTemplate` and the JDBC transaction manager; `spring-tx` provides `@Transactional` and `TransactionStatus`; H2 supplies an in-memory JDBC datasource. Since `org.h2.jdbcx.JdbcDataSource` is referenced directly, the H2 dependency must be on the compile classpath.

### 6.2. The `RequiresNewDemo.java` File

```java
package example;

import java.sql.Connection;
import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.UnexpectedRollbackException;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class RequiresNewDemo {

    private enum Mode { NEW, REQUIRED }

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = ctx.getBean(JdbcTemplate.class);
            OuterService outer = ctx.getBean(OuterService.class);
            InnerService inner = ctx.getBean(InnerService.class);

            test("both commit", jdbc, outer::bothCommit);
            test(
                "inner commits; outer fails",
                jdbc,
                outer::innerCommitsOuterFails
            );
            test(
                "inner fails; outer catches",
                jdbc,
                outer::innerFailsOuterCatches
            );
            test(
                "inner fails; exception reaches outer",
                jdbc,
                outer::innerFailsOuterPropagates
            );
            test(
                "REQUIRED comparison; outer catches",
                jdbc,
                outer::requiredFailsCaught
            );
            test(
                "REQUIRES_NEW without outer transaction",
                jdbc,
                () -> inner.requiresNew(null, false)
            );
        }
    }

    private static void test(String label, JdbcTemplate jdbc, Runnable action) {
        reset(jdbc);
        System.out.println("CASE: " + label);
        try {
            action.run(); // Caller invokes public @Transactional method through proxy.
            System.out.println("Outcome: COMMITTED");
        } catch (UnexpectedRollbackException ex) {
            System.out.println("Outcome: UnexpectedRollbackException");
        } catch (IllegalStateException ex) {
            System.out.println("Outcome: " + ex.getMessage());
        }
        Integer a = jdbc.queryForObject(
            "SELECT n FROM counters WHERE counter_key='outer'",
            Integer.class
        );
        Integer b = jdbc.queryForObject(
            "SELECT n FROM counters WHERE counter_key='inner'",
            Integer.class
        );
        System.out.println("Values: outer=" + a + ", inner=" + b);
    }

    private static void reset(JdbcTemplate jdbc) {
        jdbc.execute("DROP TABLE IF EXISTS counters");
        jdbc.execute(
            "CREATE TABLE counters (" +
            "counter_key VARCHAR(20) PRIMARY KEY, n INT NOT NULL)"
        );
        jdbc.update(
            "INSERT INTO counters(counter_key,n) VALUES (?,?)", "outer", 0
        );
        jdbc.update(
            "INSERT INTO counters(counter_key,n) VALUES (?,?)", "inner", 0
        );
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {
        @Bean
        public DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:requires_new;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(
            DataSource dataSource
        ) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        public InnerService innerService(JdbcTemplate jdbc, DataSource ds) {
            return new InnerService(jdbc, ds);
        }

        @Bean
        public OuterService outerService(
            JdbcTemplate jdbc,
            DataSource ds,
            InnerService inner
        ) {
            return new OuterService(jdbc, ds, inner);
        }
    }

    public static class InnerService {
        private final JdbcTemplate jdbc;
        private final DataSource dataSource;

        public InnerService(JdbcTemplate jdbc, DataSource dataSource) {
            this.jdbc = jdbc;
            this.dataSource = dataSource;
        }

        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public void requiresNew(Connection outerConnection, boolean fail) {
            updateInner("REQUIRES_NEW", outerConnection, fail);
        }

        @Transactional(propagation = Propagation.REQUIRED)
        public void required(Connection outerConnection, boolean fail) {
            updateInner("REQUIRED", outerConnection, fail);
        }

        private void updateInner(
            String label,
            Connection outerConnection,
            boolean fail
        ) {
            TransactionStatus status =
                TransactionAspectSupport.currentTransactionStatus();

            Connection current = DataSourceUtils.getConnection(dataSource);
            String sameConnection;
            try {
                sameConnection = outerConnection == null
                    ? "n/a"
                    : String.valueOf(current == outerConnection);
            } finally {
                DataSourceUtils.releaseConnection(current, dataSource);
            }

            System.out.println(
                "Inner " + label
                + ": active="
                + TransactionSynchronizationManager.isActualTransactionActive()
                + ", new=" + status.isNewTransaction()
                + ", savepoint=" + status.hasSavepoint()
                + ", sameConnection=" + sameConnection
            );

            int updated = jdbc.update(
                "UPDATE counters SET n=n+1 WHERE counter_key=?", "inner"
            );
            if (updated != 1) {
                throw new IllegalStateException("inner row missing");
            }
            if (fail) {
                throw new IllegalStateException("inner failure");
            }
        }
    }

    public static class OuterService {
        private final JdbcTemplate jdbc;
        private final DataSource dataSource;
        private final InnerService inner;

        public OuterService(
            JdbcTemplate jdbc,
            DataSource dataSource,
            InnerService inner
        ) {
            this.jdbc = jdbc;
            this.dataSource = dataSource;
            this.inner = inner;
        }

        @Transactional
        public void bothCommit() {
            execute(Mode.NEW, false, true, false);
        }

        @Transactional
        public void innerCommitsOuterFails() {
            execute(Mode.NEW, false, true, true);
        }

        @Transactional
        public void innerFailsOuterCatches() {
            execute(Mode.NEW, true, true, false);
        }

        @Transactional
        public void innerFailsOuterPropagates() {
            execute(Mode.NEW, true, false, false);
        }

        @Transactional
        public void requiredFailsCaught() {
            execute(Mode.REQUIRED, true, true, false);
        }

        private void execute(
            Mode mode,
            boolean failInner,
            boolean catchInner,
            boolean failOuter
        ) {
            TransactionStatus status =
                TransactionAspectSupport.currentTransactionStatus();
            System.out.println(
                "Outer before: active="
                + TransactionSynchronizationManager.isActualTransactionActive()
                + ", new=" + status.isNewTransaction()
            );

            int updated = jdbc.update(
                "UPDATE counters SET n=n+1 WHERE counter_key=?", "outer"
            );
            if (updated != 1) {
                throw new IllegalStateException("outer row missing");
            }

            Connection outerConnection =
                DataSourceUtils.getConnection(dataSource);
            try {
                try {
                    if (mode == Mode.NEW) {
                        inner.requiresNew(outerConnection, failInner);
                    } else {
                        inner.required(outerConnection, failInner);
                    }
                } catch (IllegalStateException ex) {
                    if (!catchInner) {
                        throw ex;
                    }
                    System.out.println("Outer caught: " + ex.getMessage());
                } finally {
                    Connection resumed =
                        DataSourceUtils.getConnection(dataSource);
                    try {
                        System.out.println(
                            "Outer after inner: active="
                            + TransactionSynchronizationManager
                                .isActualTransactionActive()
                            + ", sameConnection="
                            + (resumed == outerConnection)
                        );
                    } finally {
                        DataSourceUtils.releaseConnection(resumed, dataSource);
                    }
                }
            } finally {
                DataSourceUtils.releaseConnection(outerConnection, dataSource);
            }

            if (failOuter) {
                throw new IllegalStateException("outer failure");
            }
        }
    }
}
```

**Why does this structure matter?** `OuterService` and `InnerService` are two Spring beans, so the inner call is intercepted by the proxy; they share the **same datasource/transaction manager**, rather than two managers that merely happen to share a name. Outer already acquired the transaction-bound connection C1 before calling inner. Inside inner, `DataSourceUtils` acquires connection C2 for T2; after inner completes, outer retrieves C1 again. This observation works with H2 `JdbcDataSource` **without pooled/proxied connections**; in production, do not rely solely on `Connection == Connection` reference equality.

`TransactionAspectSupport.currentTransactionStatus()` must be called while inside a method managed by transaction advice; the private helper `updateInner` is called from inside the annotated inner method, so the status there still belongs to the inner interceptor. `@EnableTransactionManagement` enables transaction advice; `DataSourceTransactionManager` manages local JDBC transactions. In this complete example, returning `new` from `@Bean` methods is valid because Spring receives and post-processes those objects into beans/proxies before callers retrieve them from the context.

### 6.3. Run Command and stdout

In the `requires-new-demo` directory, JDK 17+ and Maven 3.9+ are required:

```bash
java -version
mvn -version
mvn -q compile exec:java
```

The lines printed by the program itself (excluding external Maven/Spring logs):

```text
CASE: both commit
Outer before: active=true, new=true
Inner REQUIRES_NEW: active=true, new=true, savepoint=false, sameConnection=false
Outer after inner: active=true, sameConnection=true
Outcome: COMMITTED
Values: outer=1, inner=1
CASE: inner commits; outer fails
Outer before: active=true, new=true
Inner REQUIRES_NEW: active=true, new=true, savepoint=false, sameConnection=false
Outer after inner: active=true, sameConnection=true
Outcome: outer failure
Values: outer=0, inner=1
CASE: inner fails; outer catches
Outer before: active=true, new=true
Inner REQUIRES_NEW: active=true, new=true, savepoint=false, sameConnection=false
Outer caught: inner failure
Outer after inner: active=true, sameConnection=true
Outcome: COMMITTED
Values: outer=1, inner=0
CASE: inner fails; exception reaches outer
Outer before: active=true, new=true
Inner REQUIRES_NEW: active=true, new=true, savepoint=false, sameConnection=false
Outer after inner: active=true, sameConnection=true
Outcome: inner failure
Values: outer=0, inner=0
CASE: REQUIRED comparison; outer catches
Outer before: active=true, new=true
Inner REQUIRED: active=true, new=false, savepoint=false, sameConnection=true
Outer caught: inner failure
Outer after inner: active=true, sameConnection=true
Outcome: UnexpectedRollbackException
Values: outer=0, inner=0
CASE: REQUIRES_NEW without outer transaction
Inner REQUIRES_NEW: active=true, new=true, savepoint=false, sameConnection=n/a
Outcome: COMMITTED
Values: outer=0, inner=1
```

### 6.4. Reading the Results by Scenario

**1. Both commit:** T1 writes `outer` and suspends; T2 writes `inner` and commits; T1 resumes and commits. Both rows end up with value 1.

**2. Inner commits, outer fails:** Inner T2 already committed `inner=1` before outer threw `outer failure`. Outer T1 rolls back, reverting only `outer`; the `(0,1)` result is clear proof of **two independent physical transactions**.

**3. Inner fails, outer catches:** T2 rolls back on its own due to `IllegalStateException`. Outer catches the error **after the inner proxy has finished T2**, continues T1, and commits. The `(1,0)` result proves T2 rollback does not implicitly mark T1 rollback-only.

**4. Inner fails, exception reaches outer:** T2 rolls back, and the exception continues through the outer proxy, so T1 also rolls back under T1's rollback rule. `(0,0)` does not mean T1/T2 shared a physical transaction; the reason is that **the same Java exception crossed two independent boundaries**.

**5. Comparison with REQUIRED:** Inner `REQUIRED` joins T1, with `new=false` and the same connection as outer. Inner throws an unchecked exception, and the inner proxy marks T1 rollback-only. Outer catches it and returns normally, but when the outer proxy attempts to commit T1, Spring rolls back and throws `UnexpectedRollbackException`. That is the key difference from `REQUIRES_NEW`.

**6. Without outer:** Calling inner through the Spring proxy when no outer transaction exists. `REQUIRES_NEW` still creates a new transaction, with no T1 to suspend; result `(0,1)`.

## 7. Practical Limits of Suspension

### 7.1. Connection Pool and Blocking Risk

T1 can hold C1 while T2 needs C2. If N requests concurrently open T1 and occupy all N connections in a pool of size N, **no thread can acquire a new connection for T2**. Requests can wait until timeout; this resource-wait pattern can cause pool starvation or a deadlock-like failure. Spring documentation advises that when using `REQUIRES_NEW`, the pool should be larger than the number of concurrent outer threads by **at least one connection** in simple scenarios; deeper nesting and other workloads may require more. Always measure active/idle/pending connections, connection hold times, and actual concurrency.

Do not claim that "every request always needs exactly two connections" in every setup: it depends on when the datasource acquires connections, the connection pool, the transaction manager, and the depth of nested calls. However, once T1 **already holds a connection**, an independent T2 requires its own transaction resource in standard JDBC scenarios.

### 7.2. T1 May Hold Locks While T2 Runs

Suspending T1 in Spring does not release database row locks held by T1. If T2 attempts to update the **same row** as T1 (or a row with dependent constraints), T2 can block. In that situation, outer T1 is waiting for inner T2 to finish, while inner is waiting on the lock held by T1: the risk of lock waits and timeouts is obvious.

That is why the demo updates two separate rows and does not force inner to read a row that outer just inserted uncommitted. Because T2 uses a separate transaction, under common isolation levels such as `READ_COMMITTED` it **does not see** T1's uncommitted changes. With foreign keys, unique constraints, or row locks, the outcome depends on the database and isolation level.

### 7.3. Isolation, Timeout, and Read-Only Attributes

Because T2 is its own physical transaction, inner can declare its own isolation/timeout/read-only settings:

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    isolation = Isolation.READ_COMMITTED,
    timeout = 10,
    readOnly = false
)
public void recordAudit() {
    // JDBC / repository work
}
```

This is **illustrative code**, requiring the `Isolation` import and a compatible manager/database. Attributes are applied depending on the transaction manager and driver. `readOnly` is generally a hint or setting whose enforcement level depends on the infrastructure; it is not a substitute for database write privileges.

### 7.4. Only Manages Resources Enlisted with the Matching Manager

`DataSourceTransactionManager` cannot roll back emails, HTTP requests, already-sent messages, or transactions on another database if those operations do not participate in the same transaction mechanism. If outer and inner use **different managers**, "suspend" must be understood with respect to the actual manager and resource. With JTA, suspension support depends on the runtime and the corresponding `JtaTransactionManager` integration.

### 7.5. Do Not Use REQUIRES_NEW Indiscriminately for Outbox

To send an event **only when the main business operation commits**, the outbox record normally must be inserted in the **same transaction as the main business data**. If the outbox record is inserted in a `REQUIRES_NEW` T2 and T1 later rolls back, the event can exist even though the order does not. An audit of an "execution attempt" may intentionally use T2, provided its data semantics, idempotency, and retention are clearly defined.

## 8. Conditions for the Annotation to Actually Take Effect

### 8.1. The Call Must Go Through the Proxy

Incorrect in common Spring AOP proxy mode:

```java
@Service
class OrderService {
    @Transactional
    public void outer() {
        saveAudit(); // this.saveAudit(): self-invocation, bypasses proxy.
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveAudit() {
        // T2 is not guaranteed because the call does not pass through this method's interceptor.
    }
}
```

This is an **illustrative class**. When the inner method is called via `this` on the same target, the inner transaction interceptor does not run. The inner SQL may still run under T1 opened by outer. Fix this by moving inner to another bean and injecting/calling the proxy as shown in the demo, or by using `TransactionTemplate` for a new transaction block within the same execution flow.

Similarly, `new AuditService(...)` in application code does not automatically get wrapped in a transaction proxy. Having `@Service` or `@Transactional` on a class does not turn every instance into a Spring bean. Obtain objects via `ApplicationContext`/constructor injection, and check proxyability requirements for classes/methods (`final`/`private`/JDK interface proxies).

### 8.2. Correct ApplicationContext and Transaction Manager

`@EnableTransactionManagement` in proxy mode applies to the `ApplicationContext` where it is configured. A service bean in a root context is not automatically proxied by a child `DispatcherServlet` context just because the child has annotation infrastructure. When multiple managers/datasources coexist, verify which manager handles outer, which handles inner, and which JDBC/JPA resources are actually enlisted. A proxied call that acquires connections improperly can still produce confusing behavior.

### 8.3. Exceptions and Rollback Rules

By common default, `@Transactional` rolls back when a `RuntimeException` or `Error` escapes the advised method; checked exceptions may require `rollbackFor` or an appropriate default rollback policy configuration. If inner **catches** the exception itself and returns normally, the proxy may commit T2 if it is not marked rollback-only. If outer **catches after T2 has rolled back** and decides to continue, T1 can still commit. Distinguishing where the catch occurs is critical.

Do not swallow critical errors just to keep T1 alive. Outer must make a clear business decision: can an inner audit failure be ignored, or must it fail the entire request?

## 9. Programmatically Opening T2 with `TransactionTemplate`

If you need a very specific transaction boundary without relying on avoiding self-invocation, you can use the programmatic transaction API:

```java
TransactionTemplate template =
    new TransactionTemplate(transactionManager);

template.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRES_NEW
);

template.executeWithoutResult(status -> {
    auditRepository.saveAttempt(...);
});
```

This is **illustrative code**, assuming `transactionManager` and `auditRepository` are already available. When the callback runs inside T1 managed by the **same manager**, the template creates an independent T2 and suspends/resumes T1 according to the transaction manager's mechanism. For checked/unchecked exceptions and callbacks, verify the corresponding rollback semantics. Do not use the template as a way to magically make HTTP calls or an unmanaged datasource transactional.

Choose `@Transactional(REQUIRES_NEW)` when the inner method is a clear service boundary invoked through a proxy. Choose the template when the scope is a small block, requires programmatic control, or when the class design does not suit proxy interception. There is no need to combine both mechanisms on the same piece of code without a clear reason.

## 10. Diagnostic Checklist and Exercises

| Observation | Questions to check |
| --- | --- |
| `Inner REQUIRES_NEW` yet no T2 observed | Did the caller invoke the bean proxy; is there self-invocation or a `new`-created object? |
| Inner rolls back and outer also rolls back | Did the exception escape outer, or did outer have its own rollback-only condition? |
| Inner commits yet data appears lost | Did T2 actually commit, or is inner using `REQUIRED`/same manager/misconfigured setup? |
| Inner does not see the row outer just wrote | The row in T1 is still uncommitted; what are the isolation/foreign key/lock rules? |
| Connection pool stalls | T1 holds C1 while T2 needs C2; does the pool have enough connections and an appropriate timeout? |
| Spring AOP proxy exists yet no rollback happens | Inspect transaction advice, manager, datasource, exception rules, and transaction boundaries. |
| Tests behave differently from production | Does the test have its own outer transaction managed by Spring Test? |

**Exercises:** (1) Change inner from `REQUIRES_NEW` to `REQUIRED` and compare the outer-catch case. (2) Replace inner with `NESTED` where JDBC supports savepoints, then test inner commit followed by outer rollback. (3) Have outer and inner attempt to update the same row in a test database with a short lock timeout to observe the wait risk; do not run on real data. (4) Use a small connection pool and run several outer transactions concurrently to observe pending connections. (5) Call inner directly with no outer transaction to verify `REQUIRES_NEW` still starts a transaction.

**Summary:** `REQUIRES_NEW` **suspends the outer transaction if present, creates a new physical transaction for inner, commits or rolls back inner independently, and then resumes outer**. Database-level independence does not separate the call stack, does not release T1's locks, does not prevent exceptions from affecting T1, and carries a real connection cost. Choose it based on the **business semantics of data that must commit independently**, not on the assumption that "adding a transaction is safer".

## 11. References

- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html) — `REQUIRED`, `REQUIRES_NEW`, `NESTED`, independent physical transactions, and pool notes.
- [Spring Framework — `Propagation` API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Propagation.html) — definition of "create a new transaction, suspend current if exists".
- [Spring Framework — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html) — attributes, rollback, and proxy mode.
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html) — `TransactionTemplate`.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html) — self-invocation and calling through proxies.
