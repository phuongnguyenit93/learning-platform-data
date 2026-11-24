# Joining, Suspending, and Resuming an Existing Transaction in Spring Transaction Management

## Learning Objectives

When a `@Transactional` service method calls another service that also has `@Transactional`, Spring must decide whether to **join the existing transaction**, **suspend it to run an independent transaction**, or **suspend it to run without a transaction**. After the inner call, Spring must also accurately restore the outer transaction context, even when the inner call throws an exception.

After this lesson, you will be able to:

1. Distinguish a **logical transaction scope** (the transaction scope created by each interceptor) from a **physical transaction** (the actual transaction on the connection/resource).
2. Use `REQUIRED`, `SUPPORTS`, and `MANDATORY` to join transactions appropriately; understand when a method does not create a transaction.
3. Explain how `REQUIRES_NEW` and `NOT_SUPPORTED` suspend the current transaction, and how the previous transaction is **resumed** afterward.
4. Distinguish `NESTED` using savepoints from `REQUIRES_NEW` creating an independent physical transaction.
5. Predict rollbacks, `UnexpectedRollbackException`, commit timing, connection/lock retention, and consequences for the connection pool.
6. Run a Java 17 + Spring JDBC/H2 program to verify each case rather than guessing from annotations alone.

**Scope:** synchronous (imperative) transaction management via Spring AOP proxies with `PlatformTransactionManager` and a single JDBC `DataSource`. The final sections highlight differences when using reactive transactions or multiple data sources.

## 1. What is an existing transaction?

A transaction can be opened at an outer service layer, for example:

```java
@Transactional
public void placeOrder() {
    inventoryService.reserve();
    paymentService.recordPayment();
}
```

The statements above are **illustrative only**, not a standalone program; each service must be a Spring-managed bean and called through an appropriate proxy. If both `reserve()` and `recordPayment()` have `@Transactional(propagation = REQUIRED)`, in the common case they **join** the transaction started by `placeOrder()`. If one step needs to roll back the whole operation, all DB changes in the shared physical transaction are rolled back.

In the standard JDBC model, Spring binds a `ConnectionHolder` and transaction metadata to the executing thread via `TransactionSynchronizationManager`. `JdbcTemplate` and Spring-compatible data access mechanisms obtain that bound connection instead of opening an independent transaction for each statement.

**Two concepts to keep separate:**

- **Logical transaction scope:** each call with a transaction interceptor can have its own scope, propagation attributes, and rollback intent. With `REQUIRED`, the inner method gets a new logical scope even though it does not create a new physical transaction.
- **Physical transaction:** the real transaction on the database connection (or corresponding resource transaction), where commit/rollback affects data. Multiple `REQUIRED` logical scopes can share one physical transaction.

Example with `REQUIRED`:

```text
outerService.outer()     [logical scope A] ──────────┐
    innerService.inner() [logical scope B] ───┐       │
                                              │       │
             Same physical transaction ───────┴───────┘
                              │
                        commit/rollback
```

Because they share the same physical transaction, **inner cannot commit its part independently**. If inner marks rollback-only, outer cannot turn the shared transaction into a successful commit simply by catching the exception and ignoring it.

## 2. The seven propagation types in one table

The `propagation` attribute of `@Transactional` or XML `tx:method` determines the relationship between the method's transaction and the transaction active at call time.

| Propagation | When a transaction already exists | When no transaction exists |
|---|---|---|
| `REQUIRED` (default) | **Joins** the existing physical transaction | Creates a new transaction |
| `SUPPORTS` | Joins if one exists | Runs without an actual transaction |
| `MANDATORY` | Must join | Throws `IllegalTransactionStateException` |
| `REQUIRES_NEW` | **Suspends** the outer transaction, creates an independent physical transaction; then **resumes** the outer transaction | Creates a new physical transaction |
| `NOT_SUPPORTED` | **Suspends** the outer transaction, executes the inner block without an actual transaction; then **resumes** the outer transaction | Runs without an actual transaction |
| `NEVER` | Throws `IllegalTransactionStateException` | Runs without an actual transaction |
| `NESTED` | If supported, creates a savepoint within the same physical transaction | Usually creates a new one like `REQUIRED` |

In particular, **`NESTED` is not synonymous with `REQUIRES_NEW`**. It typically creates a savepoint on the same JDBC connection; an inner rollback can roll back to the savepoint, while the physical commit is still decided by the outer scope. Availability depends on the transaction manager/driver—common with JDBC, and cannot be assumed across all JPA, JTA, or reactive managers.

**Key terms:** "join" means sharing a transaction; "suspend" means keeping the outer transaction open while detaching it from the current context; "resume" means restoring the outer transaction's resources/synchronizations and metadata so outer can continue.

## 3. Joining an existing transaction with `REQUIRED`, `SUPPORTS`, `MANDATORY`

### 3.1. `REQUIRED`: join if present, create new if not

```java
@Service
class OrderService {
    private final StockService stock;

    OrderService(StockService stock) { this.stock = stock; }

    @Transactional
    public void placeOrder() {
        // Write order to the database.
        stock.reserve();
        // Write additional related data.
    }
}

@Service
class StockService {
    @Transactional(propagation = Propagation.REQUIRED)
    public void reserve() {
        // Uses the same physical transaction as placeOrder(), if present.
    }
}
```

The example above consists of **two illustrative classes**: it requires Spring imports, transaction manager configuration, and real database operations. Assuming the call from `OrderService` to `StockService` goes through a proxy and both beans use the same transaction manager/resource:

- If no transaction exists before `placeOrder()`, outer opens a physical transaction; inner creates a `REQUIRED` logical scope joining that physical transaction.
- `reserve()` completing normally **is not the physical commit point**; only when outer completes successfully does the whole commit occur.
- If inner throws an unchecked exception out of the interceptor, inner can cause the shared transaction to be marked rollback-only. Outer catching the exception and returning normally can still receive `UnexpectedRollbackException` at commit time because Spring cannot silently report "committed" when the transaction actually rolled back.

**Attributes when joining:** `isolation`, `timeout`, and `readOnly` declared by inner generally do not alter the properties of an already existing physical transaction. With `AbstractPlatformTransactionManager`, you can configure `validateExistingTransaction=true` to reject incompatible isolation/read-only declarations; do not assume inner rules automatically override outer.

### 3.2. `SUPPORTS`: join if present, do not create one if absent

```java
@Transactional(propagation = Propagation.SUPPORTS)
public AccountDetails loadDetails(long id) {
    // If caller has a compatible transaction: join it.
    // Otherwise: do not create an actual transaction solely because of SUPPORTS.
    return repository.findById(id).orElseThrow();
}
```

This is a snippet inside a service with an appropriate `repository`, not a standalone Java file. `SUPPORTS` is often used for queries that can run inside or outside an existing transaction. It can create a transaction **synchronization scope** even when no actual transaction exists, depending on the transaction manager; therefore `TransactionSynchronizationManager.isSynchronizationActive()` and `isActualTransactionActive()` **are not the same check**.

Do not use `SUPPORTS` when business logic requires a physical transaction across multiple write operations. When called outside a transaction, each change may use its own commit behavior depending on the API/driver.

### 3.3. `MANDATORY`: caller must always provide a transaction

```java
@Transactional(propagation = Propagation.MANDATORY)
public void recordInExistingTransaction() {
    // Valid only if an active transaction already exists.
}
```

If no transaction exists when the interceptor processes the call, Spring throws `IllegalTransactionStateException`. This is a way to express an architectural constraint: a helper must belong to the outer business transaction. Note that self-invocation can skip the interceptor, bypassing even the `MANDATORY` check.

## 4. `REQUIRES_NEW`: suspend outer, run independent transaction, then resume

`Propagation.REQUIRES_NEW` requests a **new physical transaction** even when the caller is already in a transaction. With a manager that supports suspension, Spring generally performs:

```text
Outer @Transactional(REQUIRED)
  ├─ Open transaction A; bind connection/resource A
  ├─ Write A's data
  │
  ├─ Call inner @Transactional(REQUIRES_NEW) through proxy
  │    ├─ Suspend transaction A:
  │    │    unbind A's resource/synchronization from thread
  │    ├─ Open transaction B with independent resource/connection B
  │    ├─ Run inner
  │    ├─ Commit or roll back B
  │    └─ Resume transaction A:
  │         re-bind A's resource and synchronization
  │
  ├─ Outer continues in transaction A
  └─ Commit or roll back A
```

**Suspension is neither committing nor rolling back transaction A.** A remains an open transaction and can hold database locks and a connection for the entire duration of B. `REQUIRES_NEW` does not "extract" previously written code out of A; it only starts a separate transaction for the code inside inner.

Important consequences:

- **Commit/rollback independence:** B committing successfully remains persisted if A rolls back later. Conversely, B rolling back does not necessarily force A to roll back if outer handles the exception and continues validly.
- **Separate connection:** with JDBC `DataSourceTransactionManager`/`JdbcTransactionManager`, A typically keeps its bound connection while B needs another connection. If every request/thread holds connection A and simultaneously waits to obtain connection B when the pool has none left, the application can suffer pool exhaustion or deadlock. Spring's guide recommends sizing the pool larger than the number of concurrent threads by **at least one connection** in typical `REQUIRES_NEW` cases; actual sizing also depends on nesting depth and load.
- **Independent attributes:** B can set its own isolation/timeout/read-only because it is a new physical transaction.
- **Resumes even when inner fails:** after B finishes/rolls back, Spring typically resumes A before propagating the exception back to outer. If outer catches the error and decides to proceed, subsequent operations still belong to A.
- **Not a distributed transaction solution:** two datasources, a message broker, or HTTP calls do not automatically share one physical transaction.

### Application example: independent audit logging

```java
@Service
class AuditService {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordAttempt(String event) {
        // INSERT audit in a new independent transaction.
    }
}

@Service
class CheckoutService {
    private final AuditService audit;

    CheckoutService(AuditService audit) { this.audit = audit; }

    @Transactional
    public void checkout() {
        // Main operations live in transaction A.
        audit.recordAttempt("CHECKOUT_ATTEMPT"); // Transaction B.
        // If RuntimeException is thrown afterward, A rolls back,
        // yet the audit record committed in B can still exist.
    }
}
```

This is non-standalone illustrative code; it requires a database, imports, and real implementations. Ensuring an audit log "always saves" across all failure types still requires accounting for B itself failing, DB unavailability, or outer holding locks that conflict with B. Do not call `this.recordAttempt()` from within `AuditService` itself: self-invocation can bypass the proxy and lose `REQUIRES_NEW`.

## 5. `NOT_SUPPORTED`: suspend outer and run without an actual transaction

`Propagation.NOT_SUPPORTED` also suspends the current transaction (if one exists), but differs from `REQUIRES_NEW` in that it **does not start a physical transaction B**.

```text
A: outer transaction open ──┐                               ┌── A is resumed ── commit/rollback
                            │                               │
                            └── suspend A ──> inner runs ───┘
                                              no actual transaction
```

When outer has an active transaction, Spring temporarily detaches the relevant resource/synchronization from the thread context, then invokes inner outside an actual transaction. After inner returns or throws an exception, Spring restores the outer context to continue. `NOT_SUPPORTED` differs from `NEVER`: `NEVER` **throws an exception** if it encounters an outer transaction instead of suspending it.

**JDBC consequences:** if inner uses another connection with `autoCommit=true`, a single INSERT/UPDATE statement may be committed immediately while outer is suspended. If outer rolls back afterward, statements already committed in inner **are not undone by the outer transaction**. This is an important consequence—do not use `NOT_SUPPORTED` to "dodge rollbacks" without a clear business reason.

It is better suited for operations that genuinely do not need a database transaction: independent reads, computations, or long-running tasks, while keeping in mind that transaction A remains open and A's resources remain held. Running slow work mid-transaction risks holding locks/connections for too long.

**When inner throws an exception:** Spring attempts to resume A before propagating the error to outer. If the exception continues escaping the outer `@Transactional(REQUIRED)` method, by default transaction A also rolls back due to the unchecked error, even though the error originated in the `NOT_SUPPORTED` block. If outer catches the error, A can commit, while any non-transactional changes in inner may already have committed earlier.

## 6. How do `REQUIRES_NEW`, `NOT_SUPPORTED`, and `NESTED` differ?

| Criterion | `REQUIRES_NEW` | `NOT_SUPPORTED` | `NESTED` |
|---|---|---|---|
| Outer transaction present? | Suspends A | Suspends A | Keeps A, creates savepoint if supported |
| Inner has an actual transaction? | Yes: independent transaction B | No | Yes: same physical transaction A |
| Needs a different connection/resource? | Usually yes with JDBC | May use another connection outside A | Usually same connection A |
| Does inner commit survive if outer rolls back? | Yes, if B committed | Committed non-tx statements can survive | No; outer rollback discards everything after the savepoint |
| Does inner rollback affect outer? | Not automatically | No local transaction to roll back | Can roll back to savepoint and outer continues |
| When outer finishes | A commits/rolls back independently | A commits/rolls back independently of inner side effects | Commits/rolls back the entire physical transaction A |
| Main risk | Connection pool exhaustion, lock conflicts, partial business consistency | Non-rolled-back side effects, keeping outer open | Driver/manager does not support savepoints |

Example of `NESTED`: outer creates 2 rows, inner insert fails and rolls back to the savepoint, outer can continue and commit the valid portion. This **is not** an independently committed transaction B, because if outer rolls back entirely, even the inner data that had "succeeded" no longer exists.

Common choices: `REQUIRED` for unified atomic business logic; `REQUIRES_NEW` for work that must commit separately while accepting independence consequences; `NOT_SUPPORTED` for blocks that truly need no transaction; `NESTED` for intentional savepoints where support has been verified.

## 7. Runnable example: observing join, suspend, resume, and rollback-only

This demo uses Java 17, Spring Framework 6.2.19, H2, and Spring JDBC. `OuterService` calls `InnerService` which is a **separate bean**, so the call goes through a proxy. The program compares 5 scenarios:

1. `REQUIRED` joins A, outer fails → all INSERTs roll back together.
2. `REQUIRES_NEW` commits B, outer rolls back A → B's data remains.
3. `NOT_SUPPORTED` runs outside A, outer rolls back → inner's auto-committed INSERT remains.
4. B `REQUIRES_NEW` fails and rolls back, outer catches the exception → Spring resumes A and outer commits.
5. Inside `REQUIRED` throws an unchecked exception, outer catches the error → transaction A is marked rollback-only; when outer commits it receives `UnexpectedRollbackException`.

This example **runs inside a Spring application context**; it does not use `@SpringBootApplication` and requires no web server.

### 7.1. Project structure

```text
spring-propagation-demo/
├── pom.xml
└── src/main/java/com/example/tx/Main.java
```

### 7.2. File `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-propagation-demo</artifactId>
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

The `spring-context` dependency provides the application context/AOP; `spring-jdbc` provides `JdbcTemplate` and `JdbcTransactionManager`; H2 is an in-memory DB. Version 6.2.19 has been released, though real projects should use a supported BOM and an appropriate update policy.

### 7.3. File `src/main/java/com/example/tx/Main.java`

```java
package com.example.tx;

import javax.sql.DataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.UnexpectedRollbackException;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class Main {
    private static boolean active() {
        return TransactionSynchronizationManager.isActualTransactionActive();
    }

    // Only call this helper from a method currently intercepted by a transaction interceptor.
    private static boolean isNew() {
        return TransactionAspectSupport.currentTransactionStatus()
            .isNewTransaction();
    }

    @Configuration
    @EnableTransactionManagement(proxyTargetClass = true)
    public static class Config {
        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:propagation_demo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            return new JdbcTransactionManager(ds);
        }

        @Bean
        public InnerService innerService(JdbcTemplate jdbc) {
            return new InnerService(jdbc);
        }

        @Bean
        public OuterService outerService(
                JdbcTemplate jdbc, DataSource ds, InnerService inner) {
            return new OuterService(jdbc, ds, inner);
        }
    }

    public static class InnerService {
        private final JdbcTemplate jdbc;

        public InnerService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        private void insert(String label) {
            jdbc.update("INSERT INTO tx_events(label) VALUES (?)", label);
        }

        @Transactional(propagation = Propagation.REQUIRED)
        public void requiredInsert() {
            System.out.println("inner REQUIRED active=" + active()
                + " new=" + isNew());
            insert("inner-required");
        }

        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public void requiresNewInsert() {
            System.out.println("inner REQUIRES_NEW active=" + active()
                + " new=" + isNew());
            insert("inner-new");
        }

        @Transactional(propagation = Propagation.NOT_SUPPORTED)
        public void outsideTransactionInsert() {
            System.out.println("inner NOT_SUPPORTED active=" + active());
            insert("outside-tx");
        }

        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public void requiresNewThenFail() {
            System.out.println("inner REQUIRES_NEW fails active=" + active());
            insert("inner-new-failed");
            throw new IllegalStateException("inner failed");
        }

        @Transactional(propagation = Propagation.REQUIRED)
        public void requiredThenFail() {
            System.out.println("inner REQUIRED fails active=" + active()
                + " new=" + isNew());
            insert("inner-required-failed");
            throw new IllegalStateException("inner failed");
        }
    }

    public static class OuterService {
        private final JdbcTemplate jdbc;
        private final DataSource dataSource;
        private final InnerService inner;

        public OuterService(
                JdbcTemplate jdbc, DataSource dataSource, InnerService inner) {
            this.jdbc = jdbc;
            this.dataSource = dataSource;
            this.inner = inner;
        }

        private void insert(String label) {
            jdbc.update("INSERT INTO tx_events(label) VALUES (?)", label);
        }

        // TransactionSynchronizationManager binds outer's resource by ds.
        private Object boundResource() {
            return TransactionSynchronizationManager.getResource(dataSource);
        }

        @Transactional
        public void requiredThenOuterFail() {
            System.out.println("outer REQUIRED active=" + active());
            insert("outer-required");
            inner.requiredInsert();
            throw new IllegalStateException("outer failed");
        }

        @Transactional
        public void requiresNewThenOuterFail() {
            Object outerResource = boundResource();
            // Avoid writing to the same table in outer before inner writes,
            // so the demo does not depend on DB lock contention.
            inner.requiresNewInsert();
            System.out.println("outer restored="
                + (outerResource == boundResource()) + " active=" + active());
            insert("outer-rolled-back");
            throw new IllegalStateException("outer failed");
        }

        @Transactional
        public void notSupportedThenOuterFail() {
            Object outerResource = boundResource();
            inner.outsideTransactionInsert();
            System.out.println("outer restored="
                + (outerResource == boundResource()) + " active=" + active());
            insert("outer-rolled-back");
            throw new IllegalStateException("outer failed");
        }

        @Transactional
        public void resumeAfterInnerFailure() {
            Object outerResource = boundResource();
            insert("outer-start");
            try {
                inner.requiresNewThenFail();
            } catch (IllegalStateException ex) {
                System.out.println("outer catches inner error");
            }
            System.out.println("outer restored="
                + (outerResource == boundResource()) + " active=" + active());
            insert("outer-end");
        }

        @Transactional
        public void catchRequiredFailure() {
            insert("outer-start");
            try {
                inner.requiredThenFail();
            } catch (IllegalStateException ex) {
                System.out.println("outer catches inner error");
            }
            System.out.println("outer still active=" + active());
            insert("outer-end");
            // On return, the outer proxy attempts to commit, but the transaction
            // was already marked rollback-only by inner REQUIRED.
        }
    }

    private static void run(
            String label, Runnable scenario, JdbcTemplate jdbc) {
        System.out.println("=== " + label + " ===");
        try {
            scenario.run();
        } catch (UnexpectedRollbackException ex) {
            System.out.println("result=UnexpectedRollbackException");
        } catch (IllegalStateException ex) {
            System.out.println("result=IllegalStateException");
        }
        System.out.println("rows=" + jdbc.queryForList(
            "SELECT label FROM tx_events ORDER BY id", String.class));
        jdbc.update("DELETE FROM tx_events");
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute(
                "CREATE TABLE tx_events ("
                + "id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, "
                + "label VARCHAR(60) NOT NULL)"
            );
            OuterService outer = context.getBean(OuterService.class);
            run("REQUIRED", outer::requiredThenOuterFail, jdbc);
            run("REQUIRES_NEW", outer::requiresNewThenOuterFail, jdbc);
            run("NOT_SUPPORTED", outer::notSupportedThenOuterFail, jdbc);
            run("RESUME_AFTER_INNER_ERROR", outer::resumeAfterInnerFailure, jdbc);
            run("ROLLBACK_ONLY", outer::catchRequiredFailure, jdbc);
        }
    }
}
```

**Design and check explanations:**

- `InnerService` and `OuterService` are two separate Spring beans; outer receives the Spring-proxied inner bean once the application is ready. `proxyTargetClass=true` selects class-based proxies so the example needs no interfaces.
- Each outer scenario has default `@Transactional` (`REQUIRED`). `InnerService` changes only the policy via `propagation`.
- `TransactionSynchronizationManager.isActualTransactionActive()` indicates whether an **actual transaction** is active on the thread. `TransactionAspectSupport.currentTransactionStatus().isNewTransaction()` measures whether the current logical scope opened a new physical transaction or merely joined one. The `isNew()` helper must only be called from a method passing through a transaction interceptor; calling it outside can throw `NoTransactionException`.
- `boundResource()` returns the `ConnectionHolder` (viewed as an `Object`) bound by the manager to `DataSource`. Comparing `==` before/after the inner call illustrates **the same outer resource being re-bound**; this is an internal observation technique for the demo, not an API for business code to depend on connection holder identity.
- `DriverManagerDataSource` is used solely for the demo; Spring manages connection transactions via `JdbcTransactionManager`. In real environments, use a connection pool; `REQUIRES_NEW` requires accounting for multiple connections.
- The outer record is inserted after inner `REQUIRES_NEW`/`NOT_SUPPORTED` runs in those two respective cases to avoid lock contention on a single table. The demo does not attempt to simulate database isolation across every driver.
- Exceptions are thrown intentionally to test rollback; do not copy that behavior into real business logic.

### 7.4. Run command and expected output

Install JDK 17+ and Maven, and from the `spring-propagation-demo` directory run:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.tx.Main
```

Lines **printed by the example code** (excluding Maven/JDBC logs that may vary by environment):

```text
=== REQUIRED ===
outer REQUIRED active=true
inner REQUIRED active=true new=false
result=IllegalStateException
rows=[]
=== REQUIRES_NEW ===
inner REQUIRES_NEW active=true new=true
outer restored=true active=true
result=IllegalStateException
rows=[inner-new]
=== NOT_SUPPORTED ===
inner NOT_SUPPORTED active=false
outer restored=true active=true
result=IllegalStateException
rows=[outside-tx]
=== RESUME_AFTER_INNER_ERROR ===
inner REQUIRES_NEW fails active=true
outer catches inner error
outer restored=true active=true
rows=[outer-start, outer-end]
=== ROLLBACK_ONLY ===
inner REQUIRED fails active=true new=false
outer catches inner error
outer still active=true
result=UnexpectedRollbackException
rows=[]
```

**Reading the results:**

1. **REQUIRED:** outer and inner share one physical transaction. Inner returns normally, yet outer throws an exception → both INSERTs roll back → `rows=[]`.
2. **REQUIRES_NEW:** inner creates a separate transaction B and commits `inner-new`; Spring resumes resource A (`restored=true`). Outer then rolls back A, while B's row remains.
3. **NOT_SUPPORTED:** inner has no actual transaction (`active=false`). H2 on an auto-commit connection commits `outside-tx`; Spring resumes A, outer rolls back, and the inner row remains.
4. **RESUME_AFTER_INNER_ERROR:** B rolls back the `inner-new-failed` row, and Spring resumes A **before the exception reaches outer's catch block**. Outer continues and commits `outer-start` and `outer-end`.
5. **ROLLBACK_ONLY:** inner `REQUIRED` throws an unchecked exception; the interceptor marks physical transaction A as rollback-only. Outer catches the exception and sees an active transaction, yet "active" **does not mean it can still be committed**. When outer finishes normally and attempts to commit, Spring rolls back A and throws `UnexpectedRollbackException` so the caller knows the commit failed.

## 8. Important nuances of suspend/resume

### 8.1. What does Spring preserve during suspension?

In implementations based on `AbstractPlatformTransactionManager`, suspension typically involves: suspending transaction synchronizations, invoking the suspend operation provided by the specific transaction manager, unbinding outer's resources from the thread, and retaining the transaction name, read-only status, isolation, and actual-transaction flag. After inner completes, Spring resumes outer's resources and restores its synchronizations/metadata.

Actual suspension capability **depends on the transaction manager**. It is common for JDBC local transactions managed by `DataSourceTransactionManager`/`JdbcTransactionManager`; with `JtaTransactionManager`, suspending a JTA transaction may require a JTA `TransactionManager` supplied by the server/container. If the manager or resource does not support it, do not assume every propagation behaves like the JDBC example.

### 8.2. "Resume" does not restart the suspended transaction

Transaction A **remains open** while inner runs; on resume, Spring reattaches the context so outer can continue. Therefore:

- A is not automatically committed, rolled back, or given a reset timeout due to suspension.
- A's locks may still be held, causing inner B to wait; especially if B needs to update the exact row A has locked, B can block/time out and A will not "release locks" merely because it was suspended.
- A's connection may still be held; B also needs another connection. Connection hold time and pool limits must be evaluated.
- Do not treat `REQUIRES_NEW` as a "lock avoidance" or automatic "parallel execution" technique.

### 8.3. What if `NOT_SUPPORTED` throws an exception?

Spring resumes A before returning the exception to the caller, yet A's final outcome is determined by **outer's transaction boundary**:

- If outer does not catch the unchecked exception: the exception escapes A's interceptor → A rolls back by default.
- If outer catches and handles the exception without marking rollback-only: A can commit.
- Any non-transactional statements committed in inner are not automatically rolled back with A in either case above.

### 8.4. In `REQUIRED`, "catching the exception" does not guarantee commit

When inner is participating in A and the transaction interceptor marks rollback-only, catching in outer can handle error presentation but cannot clear rollback-only. This is the scenario that leads to `UnexpectedRollbackException`. If one part must be able to fail while transaction A still commits, you must revisit the consistency goal: use a savepoint (`NESTED` with a supporting manager/driver), separate an independent physical transaction with `REQUIRES_NEW`, or redesign the business flow; you cannot simply swallow the exception to simulate success.

### 8.5. Joining does not inherit independent "commit authority"

An inner `REQUIRED` with `readOnly=false` still cannot upgrade an outer `readOnly=true` transaction into a true read-write transaction. Inner's isolation and timeout also do not replace outer's configuration. If you need to guarantee compatibility, check `validateExistingTransaction` and the manager's policy instead of expecting Spring to silently override attributes.

## 9. Common implementation mistakes

| Mistake | Consequence | How to avoid |
|---|---|---|
| `this.innerMethod()` instead of calling the inner bean through proxy | New propagation is ignored; does not suspend/join as expected | Separate services, inject the bean, and call through the Spring proxy |
| Using `REQUIRES_NEW` for too many small calls | Opens many connections/transactions, wastes resources, pool exhaustion | Use only when independent commit is needed; size the pool and load test |
| Thinking suspension releases outer's locks | Inner waits on outer's own locks or times out | Shrink outer scope, order SQL carefully, do not let B touch data A locked |
| Thinking `NOT_SUPPORTED` rolls back with outer | Inner committed side effects remain even if outer rolls back | Avoid writes needing atomicity outside a transaction |
| Outer swallows exception from inner `REQUIRED` | May receive `UnexpectedRollbackException` when outer commits | Understand rollback-only; test error paths |
| Confusing `NESTED` with a separate transaction | Outer rollback still loses inner data | Distinguish savepoint from physical transaction |
| Neglecting to handle inner `REQUIRES_NEW` failures | Unchecked exception escapes outer and rolls back A as well | Catch / define a clear business policy if outer must continue |
| Assuming `@Transactional` crosses new threads | JDBC transactions rely on thread-bound context, do not auto-propagate | Keep within valid call stack; design separate transactions for async tasks |
| Using raw JDBC connections without Spring-aware APIs | Writes outside the transaction-bound connection | Use `JdbcTemplate`/`DataSourceUtils` or Spring-managed repositories |
| Multiple `PlatformTransactionManager`s but picking the wrong one | Joining/suspending on manager A does not ensure operations on datasource B participate | Specify `@Transactional("managerName")` and write integration tests |
| Using `SUPPORTS` and treating active synchronization as an active transaction | Misjudges commit/rollback scope | Check actual transaction, test against DB |
| Testing rollback only with mocked unit tests | Cannot observe physical transactions or real connections | Write integration tests with a real database |

## 10. Choosing propagation by consistency goal

- **All operations must commit/roll back together:** outer `REQUIRED`, inner `REQUIRED` (or `MANDATORY` if inner must never run standalone).
- **A read service can leverage the caller's transaction, without needing one itself:** consider `SUPPORTS`, understanding actual transaction vs. synchronization constraints.
- **An audit/notification state record committed independently of the main transaction:** `REQUIRES_NEW` may be used, weighing pool, locks, and cross-transaction data consistency.
- **A code block genuinely needs no database transaction:** consider `NOT_SUPPORTED`; if it performs writes, accept that they may commit outside A.
- **Need partial rollback and continuation of the main physical transaction:** `NESTED` with supported JDBC/savepoints, verified against a real DB.
- **Must reject calls without a transaction / when a transaction already exists:** `MANDATORY` / `NEVER` respectively.

**Self-check exercises:**

1. Outer `REQUIRED` opens transaction A, inner `REQUIRED` succeeds. Has inner committed independently? **No**, physical commit of A belongs to the outer boundary.
2. Outer A rolls back after inner `REQUIRES_NEW` commits B. Does B automatically roll back with A? **No**, they are independent.
3. Does `NOT_SUPPORTED` create a new transaction in place of A? **No**, it runs without an actual transaction and resumes A afterward.
4. Does `REQUIRES_NEW` make outer A release its locks when suspended? **No**, A remains open and locks may remain held.
5. Inner `REQUIRED` throws an unchecked exception, outer catches it and returns normally. Is committing A guaranteed? **No**, rollback-only and `UnexpectedRollbackException` may occur.
6. How do `NESTED` and `REQUIRES_NEW` differ? **NESTED typically uses a savepoint within the same physical A; REQUIRES_NEW creates an independent B**.
7. Does a local JDBC transaction automatically follow `@Async` / new thread calls? **No**; a separate transaction boundary is needed on that thread.

## References

- Spring Framework — Transaction Propagation, `REQUIRED` / `REQUIRES_NEW` / `NESTED`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — Using `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — `Propagation` enum Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/annotation/Propagation.html
- Spring Framework — Programmatic Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring Framework — `TransactionSynchronizationManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html
- Spring Framework — `AbstractPlatformTransactionManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html
