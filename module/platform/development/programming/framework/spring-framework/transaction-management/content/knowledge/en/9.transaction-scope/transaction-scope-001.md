# Distinguishing Logical Scope from Physical Transaction in Spring Framework

## 1. Why distinguish these two concepts?

When two service methods both have `@Transactional`, we have **two logical transaction scopes**. However, that **does not mean** the database management system is running two physical transactions. With the default `REQUIRED` propagation, nested logical scopes usually **participate in a single physical transaction**. That is why an inner method whose exception was caught can still prevent the outer method from committing.

A mental model:

```text
OuterService.outer()       @Transactional(REQUIRED)
│
├── update data A
│
└── InnerService.inner()   @Transactional(REQUIRED)
    └── update data B

Two calls through a Spring transaction proxy
→ two logical scopes
→ usually only ONE physical database transaction.
```

This lesson focuses on **Spring Framework transaction management in the imperative model**, for example `@Transactional` + `DataSourceTransactionManager` + `JdbcTemplate`. Cases involving JPA, multiple databases, JTA, reactive transactions, or message brokers may differ in mechanism details.

**Learning outcomes:**

1. Define logical transaction and physical transaction, without equating the number of `@Transactional` methods to the number of `Connection.commit()` calls.
2. Map `REQUIRED`, `REQUIRES_NEW`, and `NESTED` from logical scopes to physical transactions.
3. Explain why an inner `REQUIRED` marking rollback-only can cause an `UnexpectedRollbackException` in outer.
4. Distinguish a **new physical transaction** (`REQUIRES_NEW`) from a **savepoint on the current physical transaction** (`NESTED`).
5. Run a Java 17+ project to verify commit/rollback outcomes, scope status, savepoints, and JDBC connections.

## 2. Exact definitions

### 2.1. Logical transaction scope

A **logical transaction scope** is the boundary that Spring's transaction abstraction attaches to an intercepted/managed operation, such as a call to a `@Transactional` method **through a Spring proxy**. A scope can carry configuration for propagation, rollback rules, read-only, isolation, timeout, and rollback-only state at the transaction management level.

Example:

```java
@Transactional
public void outer() {
    innerService.inner();
}

@Transactional
public void inner() {
    // Access the database.
}
```

This is **illustrative code**, assuming the two methods belong to different beans and the call `innerService.inner()` goes through a transaction proxy. Spring can create **one logical scope for `outer()`** and **one logical scope for `inner()`**.

Both scopes can decide to roll back according to their own metadata, but they **do not necessarily own two separate physical transactions**. `inner()` returning normally also **does not necessarily mean the database has committed**: if `inner` merely participates in the physical transaction owned by `outer`, the physical commit usually has to wait for the outermost boundary.

Note: merely counting annotations in source code is not enough. If you directly call an object created with `new`, call `this.inner()` bypassing the proxy, or have not enabled the transaction infrastructure in the right context, a `@Transactional` may **not be intercepted**, so there is no logical scope as described.

### 2.2. Physical transaction

A **physical transaction** is the actual resource transaction, for example a JDBC `Connection` in `autoCommit=false` mode started and then committed/rolled back by the transaction manager, tied to locks, isolation, and uncommitted database state.

With a JDBC local transaction:

```text
DataSourceTransactionManager
   └── JDBC Connection (transaction-bound)
        ├── SQL UPDATE A
        ├── SQL UPDATE B
        └── COMMIT or ROLLBACK
```

Multiple repository/service calls can share that connection. If they all belong to one physical transaction, the database commits/rolls back their operations as a single unit.

Conversely, a logical scope with `REQUIRES_NEW` when an outer transaction is active creates an independent physical transaction. `NESTED` in a standard JDBC savepoint setup only creates **a restore point within the same physical transaction**, without turning it into an independent commit.

### 2.3. A comparison table

| Criterion | Logical transaction scope | Physical transaction |
| --- | --- | --- |
| Managed by whom? | Spring transaction interceptor/transaction abstraction | Transaction manager coordinating with the DB/JDBC resource |
| Observable boundary | Managed method/callback invocation | Begin/join, commit, rollback of the resource transaction |
| Quantity | Can have multiple nested scopes | Can be just one physical transaction for multiple scopes |
| `rollback-only` | A scope can request rollback | The physical transaction cannot be committed at the end once marked rollback-only |
| `REQUIRED` inside an existing transaction | Adds a participating scope | Shares the same physical transaction |
| `REQUIRES_NEW` inside an existing transaction | Adds an independent scope | Creates a new physical transaction, suspending the outer scope/resource |
| `NESTED` inside a JDBC transaction | Nested scope with a savepoint | Still shares one physical transaction |

**Key point to remember:** "logical" does not mean the transaction is fake. It is a **processing boundary at the Spring layer**, mapped to a resource transaction according to propagation. Likewise, "physical" is not as simple as seeing one `Connection` object: with different connection pools, wrappers/proxies, and transaction managers, how a connection is observed can vary. Use commit/rollback outcomes to confirm semantics.

## 3. `PROPAGATION_REQUIRED`: multiple logical scopes, one physical transaction

`REQUIRED` is the default propagation of `@Transactional`.

- If **no** matching transaction exists yet, Spring creates a physical transaction.
- If a transaction **already exists**, the new `REQUIRED` scope **participates in the current physical transaction**, rather than creating an independent physical transaction.
- Each intercepted method still has its own logical scope and can make its own rollback decision.
- Physical commit is usually performed by the boundary that owns the physical transaction, not by each inner `REQUIRED` method committing on its own.

```text
                 One physical transaction T1
     ┌──────────────────────────────────────────┐
     │  Outer logical scope REQUIRED            │
     │  ┌────────────────────────────────────┐  │
     │  │ Inner logical scope REQUIRED       │  │
     │  │ UPDATE B                           │  │
     │  └────────────────────────────────────┘  │
     │  UPDATE A                                │
     └──────────────────────────────────────────┘
                         │
                    COMMIT T1
                  or ROLLBACK T1
```

### 3.1. Success: outer and inner commit together

Suppose `outer()` updates A and `inner()` updates B. No errors occur; inner finishes normally; outer finishes normally. Spring can use the same physical transaction T1 for both scopes. When the outer boundary succeeds, **A and B are committed together**.

Inner returning **does not** create an independent commitment for B. If outer subsequently throws an unchecked exception, **both A and B roll back** because T1 has not committed yet.

### 3.2. Inner fails, outer catches it, yet still cannot commit

Logical example:

```java
@Transactional
public void outer() {
    repository.updateA();

    try {
        innerService.requiredAndFail();
    } catch (IllegalStateException ex) {
        // Outer handled the exception at the Java layer.
    }
    // The outer method completes normally.
}

@Transactional(propagation = Propagation.REQUIRED)
public void requiredAndFail() {
    repository.updateB();
    throw new IllegalStateException("inner failure");
}
```

This is **illustrative code** (requiring appropriate beans, repositories, and imports), with two services calling each other **through a proxy**. When the exception exits through the inner transaction interceptor:

1. Inner `REQUIRED` is **participating in outer's physical transaction T1**.
2. Spring applies the default rollback rule for `IllegalStateException` and **marks T1 rollback-only**. Inner does not have an independent physical transaction to roll back separately.
3. Outer catches the exception, so the outer body can continue/return normally.
4. When the outer interceptor tries to commit T1, the manager detects rollback-only and **rolls back T1**.
5. Because the outer caller expected to commit while T1 was actually rolled back, Spring throws **`UnexpectedRollbackException`** in this standard scenario.

Therefore, **catching the exception in outer does not clear rollback-only**. `UnexpectedRollbackException` **does not mean Spring automatically opened another transaction**; on the contrary, it prevents the caller from mistakenly believing the data was committed successfully.

**Distinguishing two cases:**

- If the **inner exception is handled directly inside the inner method** and does not escape to the transaction interceptor (while not marking rollback-only), the interceptor can treat inner as completing normally, and therefore does not trigger a rollback from the swallowed error.
- If the exception **has already passed through the inner transaction interceptor**, catching it in outer afterward does not clear the physical transaction's rollback-only mark. In the default demo, outer's commit fails with `UnexpectedRollbackException`.

## 4. `PROPAGATION_REQUIRES_NEW`: independent physical transaction

With `REQUIRES_NEW`:

1. If outer T1 is running, Spring **suspends the resources bound to T1** on the current thread.
2. Spring opens a **new physical transaction T2** for the inner scope.
3. Inner commits or rolls back **T2** independently.
4. After inner finishes, Spring resumes T1 so outer can continue.
5. Outer decides to commit/roll back T1 separately.

```text
Outer logical scope                 Inner logical scope
      │                                   │
  Physical T1 ── SUSPEND ────────→ Physical T2 (NEW)
      │                                   │
      │                            COMMIT/ROLLBACK T2
      │                                   │
  Physical T1 ←── RESUME ────────────────┘
      │
  COMMIT/ROLLBACK T1
```

**Important consequences:**

- Inner T2 being rolled back **does not automatically mark T1 rollback-only** under `REQUIRES_NEW` semantics. If outer catches the error and continues, T1 can commit.
- If inner T2 **has already committed**, outer T1 rolling back afterward **cannot undo T2's commit**.
- T2 can have its own independent isolation, timeout, and read-only settings.
- With a JDBC connection pool, outer usually holds one connection while inner needs **another connection**. Indiscriminate use of `REQUIRES_NEW` can cause connection starvation or deadlocks under high load; the pool must have enough capacity for nested/concurrent transactions.

Example: outer payment rolls back while inner audit logging with `REQUIRES_NEW` has committed. This is sometimes desirable for independent auditing, but inappropriate if the inner data **must** roll back together with outer. Do not choose `REQUIRES_NEW` just because you want to "be sure there is a transaction".

## 5. `PROPAGATION_NESTED`: one physical transaction, multiple savepoints

When the **JDBC transaction manager supports savepoints**, `NESTED` can place a **savepoint** on the same connection as the existing physical transaction T1. If inner fails, Spring rolls back to the savepoint; outer can continue without rolling back all prior changes.

```text
One physical transaction T1
  BEGIN T1
    UPDATE A (outer)
    SAVEPOINT S1
      UPDATE B (inner nested)
      on error: ROLLBACK TO S1  ← discards only changes after S1
    outer continues
  COMMIT T1 (if all of T1 remains valid)
```

**Distinguish very carefully from `REQUIRES_NEW`:**

- `NESTED` uses the **same physical transaction**, adding a savepoint, not an independent T2.
- An inner nested scope completing successfully **does not perform a separate physical commit**; if outer rolls back, change B is also rolled back.
- An inner nested scope failing can roll back only the part after the savepoint so outer can proceed to commit A.
- If outer ultimately rolls back, all remaining changes in T1 — both A and any unrolled-back part of B — are discarded.

Support for `NESTED` **depends on the transaction manager and the resource**. For example, `DataSourceTransactionManager` with a JDBC driver supporting savepoints fits this lab. Do not assume identical behavior across all `JpaTransactionManager`, R2DBC, JTA, or distributed transactions. If savepoints/the manager do not support it, the configuration may throw an error instead of silently turning `NESTED` into `REQUIRES_NEW`.

### 5.1. Quick-reference table

| Observation | `REQUIRED` (inner joins outer) | `REQUIRES_NEW` | `NESTED` (JDBC savepoint) |
| --- | --- | --- | --- |
| Physical transaction while inner runs | Same T1 | New T2; T1 suspended | Same T1 |
| JDBC connection in demo | Same connection | Different connection | Same connection |
| Inner `TransactionStatus.isNewTransaction()` | `false` | `true` | `false` |
| Inner `TransactionStatus.hasSavepoint()` | `false` | `false` | `true` |
| Inner unchecked exception, outer catches | T1 may become rollback-only → outer `UnexpectedRollbackException` | T2 rolls back; T1 can still commit | Rolls back to savepoint; T1 can commit |
| Inner succeeds, outer later rolls back | Both A/B roll back | Already-committed T2 keeps B | Both A/B roll back |
| Cost/resources | Shares T1 | Separate physical transaction/connection | Savepoint on T1 |

The `TransactionStatus` values in the table assume inner is actually intercepted by Spring and outer **already has an active transaction**. If `inner` is called directly without a proxy or without an existing outer transaction, the results differ. In particular, `NESTED` when no transaction exists may have to start a new transaction instead of creating a savepoint.

## 6. Verification demo with JDBC: Java 17, Spring Framework, H2

We will have 2 counters, each initially 0:

- `outer` is incremented by the outer service before calling inner.
- `inner` is incremented by the inner service inside the logical scope of each propagation.
- Intentionally throw `IllegalStateException` to test rollback.
- Each case resets the table, so numbers can be compared directly.

The demo consists of **six cases**:

| Case | Inner propagation | Intentional event | Post-transaction result |
| --- | --- | --- | --- |
| 1. `REQUIRED success` | `REQUIRED` | No error | outer=1, inner=1 |
| 2. `REQUIRED inner failure` | `REQUIRED` | Inner fails, outer catches | outer=0, inner=0; outer receives `UnexpectedRollbackException` |
| 3. `REQUIRES_NEW inner failure` | `REQUIRES_NEW` | Inner T2 rolls back, outer T1 continues | outer=1, inner=0 |
| 4. `NESTED inner failure` | `NESTED` | Inner rolls back to savepoint, outer continues | outer=1, inner=0 |
| 5. `REQUIRES_NEW inner commits, outer fails` | `REQUIRES_NEW` | Inner T2 commits, outer T1 rolls back | outer=0, inner=1 |
| 6. `NESTED inner succeeds, outer fails` | `NESTED` | Savepoint scope succeeds, but T1 rolls back | outer=0, inner=0 |

The table shows that looking only at the results of cases 3 and 4 is not enough to distinguish `REQUIRES_NEW` from `NESTED`; we must examine the **physical transaction** and the case where **inner commits and outer rolls back** (case 5 vs. 6).

### 6.1. Project structure

```text
logical-physical-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── LogicalPhysicalDemo.java
```

No Spring Boot, web server, or database server is needed. H2 runs in the same JVM. Fixed dependencies are used to make the example easy to reproduce.

### 6.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>logical-physical-demo</artifactId>
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
                    <mainClass>example.LogicalPhysicalDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**Explanation:** `spring-context` creates and injects beans; `spring-jdbc` provides the JDBC transaction manager/JdbcTemplate; `spring-tx` provides propagation, `@Transactional`, and transaction status; H2 is the JDBC database. `h2` is on the compile classpath because the Java file uses `JdbcDataSource` directly. Versions are pinned for the example; in real systems, use a BOM and centralized dependency/security update management.

### 6.3. `src/main/java/example/LogicalPhysicalDemo.java`

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

public class LogicalPhysicalDemo {

    private enum Mode {
        REQUIRED, REQUIRES_NEW, NESTED
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            OuterService service = context.getBean(OuterService.class);

            runCase("REQUIRED success", jdbc, service::requiredSuccess);
            runCase("REQUIRED inner failure", jdbc, service::requiredInnerFails);
            runCase(
                "REQUIRES_NEW inner failure",
                jdbc,
                service::requiresNewInnerFails
            );
            runCase("NESTED inner failure", jdbc, service::nestedInnerFails);
            runCase(
                "REQUIRES_NEW inner commits, outer fails",
                jdbc,
                service::requiresNewCommitsOuterFails
            );
            runCase(
                "NESTED inner succeeds, outer fails",
                jdbc,
                service::nestedSucceedsOuterFails
            );
        }
    }

    private static void runCase(String label, JdbcTemplate jdbc, Runnable work) {
        reset(jdbc);
        System.out.println("CASE: " + label);

        try {
            work.run(); // Call public @Transactional method through Spring proxy.
            System.out.println("Outcome: COMMITTED");
        } catch (UnexpectedRollbackException ex) {
            System.out.println("Outcome: UnexpectedRollbackException");
        } catch (IllegalStateException ex) {
            System.out.println("Outcome: " + ex.getMessage());
        }

        Integer outer = jdbc.queryForObject(
            "SELECT n FROM counters WHERE counter_key = 'outer'",
            Integer.class
        );
        Integer inner = jdbc.queryForObject(
            "SELECT n FROM counters WHERE counter_key = 'inner'",
            Integer.class
        );
        System.out.println("Values: outer=" + outer + ", inner=" + inner);
    }

    private static void reset(JdbcTemplate jdbc) {
        // Each case runs on independent initial data.
        jdbc.execute("DROP TABLE IF EXISTS counters");
        jdbc.execute(
            "CREATE TABLE counters (" +
            "counter_key VARCHAR(16) PRIMARY KEY, n INT NOT NULL)"
        );
        jdbc.update(
            "INSERT INTO counters (counter_key, n) VALUES ('outer', 0)"
        );
        jdbc.update(
            "INSERT INTO counters (counter_key, n) VALUES ('inner', 0)"
        );
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {

        @Bean
        public DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:logical_physical;DB_CLOSE_DELAY=-1");
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

    // Separate bean so outer calls inner THROUGH PROXY, avoiding self-invocation.
    public static class InnerService {
        private final JdbcTemplate jdbc;
        private final DataSource dataSource;

        public InnerService(JdbcTemplate jdbc, DataSource dataSource) {
            this.jdbc = jdbc;
            this.dataSource = dataSource;
        }

        @Transactional(propagation = Propagation.REQUIRED)
        public void required(Connection outerConnection, boolean fail) {
            updateInner("REQUIRED", outerConnection, fail);
        }

        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public void requiresNew(Connection outerConnection, boolean fail) {
            updateInner("REQUIRES_NEW", outerConnection, fail);
        }

        @Transactional(propagation = Propagation.NESTED)
        public void nested(Connection outerConnection, boolean fail) {
            updateInner("NESTED", outerConnection, fail);
        }

        private void updateInner(
            String mode,
            Connection outerConnection,
            boolean fail
        ) {
            TransactionStatus status =
                TransactionAspectSupport.currentTransactionStatus();

            Connection innerConnection =
                DataSourceUtils.getConnection(dataSource);
            boolean sameConnection;
            try {
                sameConnection = innerConnection == outerConnection;
            } finally {
                DataSourceUtils.releaseConnection(innerConnection, dataSource);
            }

            System.out.println(
                "Inner " + mode
                + ": active="
                + TransactionSynchronizationManager.isActualTransactionActive()
                + ", new=" + status.isNewTransaction()
                + ", savepoint=" + status.hasSavepoint()
                + ", sameConnection=" + sameConnection
            );

            int updated = jdbc.update(
                "UPDATE counters SET n = n + 1 WHERE counter_key = 'inner'"
            );
            if (updated != 1) {
                throw new IllegalStateException("missing inner row");
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
        public void requiredSuccess() {
            execute(Mode.REQUIRED, false, false);
        }

        @Transactional
        public void requiredInnerFails() {
            execute(Mode.REQUIRED, true, false);
        }

        @Transactional
        public void requiresNewInnerFails() {
            execute(Mode.REQUIRES_NEW, true, false);
        }

        @Transactional
        public void nestedInnerFails() {
            execute(Mode.NESTED, true, false);
        }

        @Transactional
        public void requiresNewCommitsOuterFails() {
            execute(Mode.REQUIRES_NEW, false, true);
        }

        @Transactional
        public void nestedSucceedsOuterFails() {
            execute(Mode.NESTED, false, true);
        }

        private void execute(
            Mode mode,
            boolean failInner,
            boolean failOuter
        ) {
            // Write outer within the physical transaction opened by the outer proxy.
            int updated = jdbc.update(
                "UPDATE counters SET n = n + 1 WHERE counter_key = 'outer'"
            );
            if (updated != 1) {
                throw new IllegalStateException("missing outer row");
            }

            // Only for observing the connection in the JDBC demo.
            Connection outerConnection =
                DataSourceUtils.getConnection(dataSource);
            try {
                try {
                    switch (mode) {
                        case REQUIRED ->
                            inner.required(outerConnection, failInner);
                        case REQUIRES_NEW ->
                            inner.requiresNew(outerConnection, failInner);
                        case NESTED ->
                            inner.nested(outerConnection, failInner);
                    }
                } catch (IllegalStateException ex) {
                    // Intentionally handle the inner failure to see whether outer can commit.
                    System.out.println("Outer caught: " + ex.getMessage());
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

**Why does the project use two service beans?** `OuterService` calls `InnerService` injected by Spring; the inner call goes **through the proxy**, so Spring creates the corresponding logical scope. If both methods were placed in the same bean and called via `this.inner()`, standard proxy mode does not intercept self-invocation; the propagation comparison conclusions would be wrong.

**Why use `DataSourceUtils.getConnection`?** This is the resource-aware way to obtain the connection bound to the thread by Spring. In this non-pooled H2 demo, we hold a reference to the outer connection and compare it against the inner connection: `true` when sharing outer's physical connection, `false` when `REQUIRES_NEW` requests a different connection. **Passing `Connection` as a parameter in this lab is solely for observation**; do not design production business logic by passing JDBC connections between service methods. With other proxies/connection pools, `==` comparison may not be a universal measurement; commit/rollback semantics remain the ultimate proof.

`TransactionAspectSupport.currentTransactionStatus()` reads the status of the **currently intercepted inner method**. Because `updateInner` is called from inside the proxy-intercepted inner method, reading the status in this helper is valid. `status.isNewTransaction()` indicates whether that scope initiated a new transaction; `status.hasSavepoint()` indicates whether the scope has a savepoint; neither **should replace** inspecting the data after the transaction.

### 6.4. Running the project

Install **JDK 17+** and **Maven 3.9+**; Maven needs to download dependencies from the repository when not yet cached. In the `logical-physical-demo` directory:

```bash
java -version
mvn -version
mvn -q compile exec:java
```

Lines printed by the **program** in order (excluding Maven/Spring logs if added by the environment):

```text
CASE: REQUIRED success
Inner REQUIRED: active=true, new=false, savepoint=false, sameConnection=true
Outcome: COMMITTED
Values: outer=1, inner=1
CASE: REQUIRED inner failure
Inner REQUIRED: active=true, new=false, savepoint=false, sameConnection=true
Outer caught: inner failure
Outcome: UnexpectedRollbackException
Values: outer=0, inner=0
CASE: REQUIRES_NEW inner failure
Inner REQUIRES_NEW: active=true, new=true, savepoint=false, sameConnection=false
Outer caught: inner failure
Outcome: COMMITTED
Values: outer=1, inner=0
CASE: NESTED inner failure
Inner NESTED: active=true, new=false, savepoint=true, sameConnection=true
Outer caught: inner failure
Outcome: COMMITTED
Values: outer=1, inner=0
CASE: REQUIRES_NEW inner commits, outer fails
Inner REQUIRES_NEW: active=true, new=true, savepoint=false, sameConnection=false
Outcome: outer failure
Values: outer=0, inner=1
CASE: NESTED inner succeeds, outer fails
Inner NESTED: active=true, new=false, savepoint=true, sameConnection=true
Outcome: outer failure
Values: outer=0, inner=0
```

### 6.5. Interpreting each case

**Case 1 — REQUIRED success:** Outer transaction T1 begins; inner `REQUIRED` joins T1, so `new=false` and `sameConnection=true`. Inner returns normally. Outer returns normally; T1 commits both changes, yielding `(outer=1, inner=1)`.

**Case 2 — REQUIRED inner failure:** Inner updated `inner` and then threw an unchecked exception. Inner's transaction interceptor marks **physical T1** rollback-only. Outer catches the exception, but does not clear rollback-only. When the outer boundary attempts to commit, Spring rolls back all of T1 and throws `UnexpectedRollbackException`. Both resulting values are 0.

**Case 3 — REQUIRES_NEW inner failure:** Outer T1 is suspended; new inner T2 uses a different connection, `new=true`. Inner throws an error so T2 rolls back. Outer catches the error, continues, and commits T1. Result is `(outer=1, inner=0)`. T1 is not marked rollback-only by inner T2 by default.

**Case 4 — NESTED inner failure:** Inner uses a savepoint within the **same T1**, so `savepoint=true` and `sameConnection=true`. The error causes Spring to roll back writes after the savepoint; outer catches it and then commits T1. The result is also `(outer=1, inner=0)`, but **there is no T2** as in case 3.

**Case 5 — REQUIRES_NEW inner commits, outer fails:** Inner's T2 finishes normally and **commits before** outer throws. Outer T1 then rolls back, discarding only the outer update. The value inner=1 remains persisted. This is a key sign of an **independent physical transaction**.

**Case 6 — NESTED inner succeeds, outer fails:** Inner finishes, but only resolves the savepoint scope; there is no separate physical commit. Outer throws an error, rolling back all of T1 and discarding both outer and inner changes. This is the clearest sign that `NESTED` **is not the same as** `REQUIRES_NEW`.

## 7. Understanding rollback-only and `UnexpectedRollbackException` properly

### 7.1. Rollback-only does not mean rollback has happened immediately

When a participating `REQUIRED` scope requests a rollback, the transaction manager can **mark the physical transaction as rollback-only**, preventing an erroneous commit at the end. While the outer scope is still running, some earlier SQL statements remain uncommitted changes within the transaction. The actual rollback happens when the manager completes the physical transaction (or when the DBMS forces early termination due to a severe error).

```text
T1 begins
  Outer writes A
  Inner REQUIRED writes B
  Inner throws RuntimeException
  Inner proxy marks T1 rollback-only
  Outer catches error and returns
  Outer proxy attempts to complete T1
  -> ROLLBACK T1
  -> UnexpectedRollbackException reported to caller
```

This example follows the defaults of `DataSourceTransactionManager`/`@Transactional`. Do not generalize that **every exception** or **every catch** produces `UnexpectedRollbackException`. If inner is not intercepted by advice, the exception does not match rollback rules, rollback-only is not set, or outer has already proactively rolled back via another path, the outcome can differ.

### 7.2. Why does the exception notification appear at the outer boundary?

In a participating `REQUIRED` transaction, inner does not own an independent physical commit. Outer has the authority to complete T1. Thus the inner method can exit with the original exception that outer catches; **only when outer attempts to commit** does rollback-only cause Spring to throw `UnexpectedRollbackException`. Spring does this so the caller does not mistake a normal method return for committed data.

### 7.3. Proper ways to handle it

- If an inner failure invalidates the entire use case, usually **let the exception propagate** so outer rolls back instead of catching it and returning success.
- If part of an operation can be discarded locally while outer remains valid, consider **`NESTED` + savepoint** when the resource supports it, or clearly refactor the business logic into multiple steps.
- If inner needs to commit/roll back completely independently, consider **`REQUIRES_NEW`**, while making sure that an inner commit **will not be rolled back by outer**.
- If you want the transaction to roll back even after catching an error in the same scope, you can explicitly mark rollback-only via the appropriate transaction API; you must understand the effect on the caller and outer boundary.
- Do not "fix" it by catching `UnexpectedRollbackException` as well and returning success: **the database has rolled back**, and the business layer must report the status truthfully.

## 8. What propagation does not solve by itself

### 8.1. Changing isolation or timeout in inner `REQUIRED`

When an inner `REQUIRED` participates in the physical transaction opened by outer, it **does not have a new connection transaction** on which to independently apply arbitrary different isolation/read-only/timeout settings. The active physical characteristics typically come from the outer transaction. A Spring transaction manager can be configured with `validateExistingTransaction=true` to detect incompatible isolation/read-only declarations instead of silently joining.

Because `REQUIRES_NEW` has its own T2, it can declare separate isolation, timeout, and read-only settings for T2. `NESTED` shares T1, so a savepoint does not create an independent DB isolation level.

### 8.2. Calls must actually go through the proxy

`@Transactional` in proxy mode only takes effect when the method call goes through a Spring proxy. Common buggy code:

```java
public void outer() {
    inner(); // Self-invocation within the same object: bypasses the transaction proxy for inner.
}

@Transactional(propagation = Propagation.REQUIRES_NEW)
public void inner() {
    // Does not necessarily get an independent T2 if called directly via this.inner().
}
```

The snippet above is **illustrative**, not a standalone application. The clear solution is to place inner transactional methods in **another bean** and call them via the injected bean, like `OuterService` and `InnerService` in the demo. Placing `@Transactional` on a private method, an object manually created with `new`, or the wrong `ApplicationContext` can also prevent the advice from running.

### 8.3. Each thread/reactive context has a different model

**Imperative** Spring transactions typically bind JDBC resources to the current thread. Do not spawn `new Thread`, `@Async`, or `CompletableFuture` and assume T1 automatically transfers to the new thread. With reactive R2DBC, transactions are usually bound to the Reactor Context via `ReactiveTransactionManager`, so the thread-bound JDBC checks in this demo do not apply directly.

### 8.4. Transaction manager and resources must be compatible

`DataSourceTransactionManager` only controls JDBC connections participating in the same datasource. Do not infer that rolling back T1 will undo a sent email, an HTTP request, a non-transactional Kafka event, or an update to another database without proper transaction coordination. `REQUIRES_NEW` does not automatically turn multi-system integration into an atomic distributed transaction.

### 8.5. When multiple transaction managers coexist

A `@Transactional` can be bound to a specific manager via `transactionManager`/`value`. Methods using **different managers or datasources** will not automatically share one physical transaction, even if both use `REQUIRED`. You must identify the actual resource/manager being used; avoid inferring from the annotation in isolation.

## 9. Common errors and how to diagnose them

| Symptom | Diagnostic question | Suggested resolution |
| --- | --- | --- |
| Inner `@Transactional` returns, then outer fails and inner data is lost | Is inner running as `REQUIRED` sharing T1? | This is normal atomic behavior; consider `REQUIRES_NEW` only if independent commit is required. |
| Outer catches inner exception yet still gets `UnexpectedRollbackException` | Did inner mark the shared T1 rollback-only? | Do not assume catching clears rollback-only; adjust transaction boundaries/propagation to match business rules. |
| `REQUIRES_NEW` used, yet inner rollback still causes outer to roll back | Did outer let the exception continue escaping the method? | Independent T2 does not stop outer from rolling back if an unchecked exception goes unhandled at the outer boundary. |
| `NESTED` does not work or reports unsupported | Do the transaction manager/JDBC driver support savepoints? | Verify JDBC savepoint support and configuration; do not replace `NESTED` with `REQUIRES_NEW` without evaluating semantics. |
| `REQUIRES_NEW` added, yet still sharing the same transaction | Does the inner call go through the proxy? | Split into separate beans, inject the proper reference, avoid self-invocation. |
| Application hangs when using many `REQUIRES_NEW` | Does the pool have spare connections while outer holds one? | Limit nested usage, size the pool appropriately, measure concurrency. |
| Inner `REQUIRED` declares its own isolation but has no effect | Is inner joining outer's physical T1? | Configure on outer or enable manager validation; do not expect a new connection. |
| Tests pass, but production rollback behaves differently | Is there a test-managed transaction wrapping the test? | Check boundaries and read back after actual commit/rollback. |

### 9.1. Signals to observe in logs/tests

- Is the **service reference** a Spring-created proxy? In diagnostic code, you can use `AopUtils.isAopProxy(bean)`, though a proxy could be for advice other than transactions.
- Is `TransactionSynchronizationManager.isActualTransactionActive()` true while the method is executing?
- Do `TransactionAspectSupport.currentTransactionStatus().isNewTransaction()` and `hasSavepoint()` match the expected propagation? Only call these when inside an active transaction invocation context.
- What is the **database state after the outer boundary completes**? Do not rely solely on inner having executed SQL or printed logs before commit.
- Is an exception being swallowed, is a checked exception outside the rollback rules, or is a database resource failing to participate in the right manager?
- Are there transaction-level timeouts, locks, isolation mismatches, or connection pool contention?

## 10. Thought exercises and further experiments

1. **Two logical scopes, one physical transaction:** draw a diagram when outer `@Transactional` calls inner `@Transactional(REQUIRED)`. Explain why both methods carry the annotation yet there is only one physical commit.
2. **Catch without rollback:** modify the demo so inner `REQUIRED` catches the exception itself **before the exception escapes the inner method**. Predict the rollback-only state and compare with case 2.
3. **Difference between NESTED and REQUIRES_NEW:** using only cases 3 and 4 shows identical final numbers. Use cases 5/6 to prove the physical independence of `REQUIRES_NEW`.
4. **Outer does not catch:** modify case 3 so outer does not catch inner T2's failure. Even though T2 is independent, outer can also roll back because the unchecked exception continues escaping the outer transaction interceptor. Physical independence does not prevent policy-based rollback at the outer boundary.
5. **Change the exception source:** replace `IllegalStateException` with a checked exception matching the method signature; explore `@Transactional(rollbackFor = ...)` and predict how rollback rules change the behavior.
6. **Change the datasource:** investigate why inner `REQUIRES_NEW` with a small connection pool risks waiting for a connection while outer is already holding one.
7. **Reading status accurately:** try logging `TransactionStatus` in both outer and inner; explain why outer has `isNewTransaction=true` while inner `REQUIRED` has `isNewTransaction=false`, even though both reside in one physical transaction.

### Quick self-check

- Is a `@Transactional(REQUIRED)` method called from inside an active transaction guaranteed to open a new physical transaction?
- Inner `REQUIRED` requests rollback-only, outer catches the exception and returns normally: why can the caller still receive `UnexpectedRollbackException`?
- Inner `REQUIRES_NEW` has committed, outer later rolls back: is inner's result discarded?
- Inner `NESTED` succeeds, outer rolls back: does inner's result remain?
- Is a JDBC savepoint equivalent to an independent physical transaction?

**Core takeaway:** `REQUIRED` creates **logical scopes sharing a physical transaction**; `REQUIRES_NEW` creates a **separate physical transaction**; `NESTED` typically creates a **savepoint within the same JDBC physical transaction**. Do not choose propagation solely by name: decide based on **which data must commit/roll back together** and verify with actual transaction behavior.

## 11. References

- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): directly describes logical/physical scopes, `REQUIRED`, `REQUIRES_NEW`, `NESTED`, rollback-only, and `UnexpectedRollbackException`.
- [Spring Framework — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): propagation/rollback defaults and annotation configuration.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): proxy/interceptor and transaction boundaries.
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): rollback behavior and rollback rules.
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): `TransactionTemplate`/`PlatformTransactionManager` and programmatic management scope.
