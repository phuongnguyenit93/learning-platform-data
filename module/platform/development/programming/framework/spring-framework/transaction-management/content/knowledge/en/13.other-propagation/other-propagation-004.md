# NEVER and Errors When Encountering an Active Transaction in Spring Framework

## 1. The essence of `Propagation.NEVER`

In Spring Framework, `Propagation.NEVER` is a policy requiring **the method to run outside an active transaction**. For a method handled by the Spring transaction interceptor:

```java
@Transactional(propagation = Propagation.NEVER)
public void runOutsideTransaction() {
    // Logic allowed to run ONLY when NO current transaction exists.
}
```

Spring applies two behavioral branches:

- **No active transaction recognized by the transaction manager in use:** lets the method body run **without opening a new physical transaction** for this call.
- **An active transaction exists:** Spring **throws `IllegalTransactionStateException`** from the transaction infrastructure **before the method body executes**.

**NEVER does not suspend an outer transaction, does not create a new transaction, does not establish a savepoint, and does not commit/roll back an existing transaction.** If you want to temporarily suspend the outer transaction while still letting the inner code run, that is `Propagation.NOT_SUPPORTED`, not `NEVER`.

Spring exception class name:

```java
org.springframework.transaction.IllegalTransactionStateException
```

This is a **class name for reference**, not a standalone Java file or statement. It is an unchecked transaction exception. The typical message in `AbstractPlatformTransactionManager` is:

```text
Existing transaction found for transaction marked with propagation 'never'
```

When handling errors, check the **exception type** and avoid relying on the exact wording of the message because versions/implementations may vary.

### Learning objectives

1. Distinguish "not creating a transaction" from "rejecting an active transaction".
2. Understand that the `NEVER` exception happens in the **proxy/transaction manager**, before the method body.
3. Analyze outcomes when outer `@Transactional` calls inner `NEVER` and either **catches** or **does not catch** the exception.
4. Clearly compare `NEVER`, `NOT_SUPPORTED`, `MANDATORY`, `SUPPORTS`, and `REQUIRED`.
5. Verify independently using Spring JDBC, H2, Java 17, and Maven; observe both logs and database state after commit/rollback.
6. Identify limitations around proxies, contexts, transaction managers, test transactions, and resource participation.

## 2. Two different call paths

### 2.1. Calling `NEVER` when no transaction exists

```text
Application caller without a transaction
         |
         v
Spring proxy @Transactional(NEVER)
         |
         +--> Transaction manager sees no active transaction
         |
         +--> Allows method body to run
                   |
                   v
             No new physical transaction opened
```

In the Spring JDBC example, `TransactionSynchronizationManager.isActualTransactionActive()` inside the method is `false`. Distinguish this from "no database activity": code can still call JDBC, read data, or execute SQL. With JDBC connections typically in `autoCommit=true` when not participating in a transaction, **each UPDATE can commit individually**. `NEVER` does not guarantee atomicity across multiple write operations.

A `@Transactional(NEVER)` method called from a normal `main()`, when there is no enclosing transaction, passes the check and runs successfully **if there are no other application errors**.

### 2.2. Calling `NEVER` when a transaction already exists

```text
OuterService.process()  @Transactional(REQUIRED)
         |
         +--> Starts transaction T1
         +--> UPDATE outer_row in T1 (uncommitted)
         |
         +--> InnerService.runOutsideTransaction()
                   @Transactional(NEVER)
                       |
                       v
                Spring transaction interceptor:
                Detects active T1
                       |
                       +--> IllegalTransactionStateException
                             (before method body)
         |
         +--> Outer receives exception and decides how to handle
```

Spring **does not execute the inner body** once it detects a propagation violation. Log statements, SQL, or side effects placed **inside the inner body** will not run. This is a useful "fail-fast" property when an API has a clear contract that it must not run inside a caller's transaction.

However, the exception thrown by the inner interceptor **does not by itself prove** that transaction T1 was rolled back. Whether T1 commits or rolls back still depends on the caller and the outermost transaction interceptor.

## 3. Same error, yet outer may commit or roll back

Consider two separate Spring beans:

```java
@Service
class OuterService {
    private final StrictService strict;

    OuterService(StrictService strict) {
        this.strict = strict;
    }

    @Transactional
    public void process() {
        repository.updateA();
        strict.mustRunWithoutTransaction();
    }
}

@Service
class StrictService {
    @Transactional(propagation = Propagation.NEVER)
    public void mustRunWithoutTransaction() {
        repository.updateB();
    }
}
```

This is **illustrative code**; `repository` variables and imports are not declared, so it cannot compile standalone. The call between **two Spring beans** is crucial: if the `NEVER` method is called via `this.inner()` on the same target, default AOP proxy mode may bypass the transaction interceptor.

Suppose outer `process()` has opened transaction T1 and written `A`:

- The inner proxy receives the `NEVER` call, detects T1, and throws `IllegalTransactionStateException`.
- The body of `mustRunWithoutTransaction()` **has not run**, so `updateB()` is not executed.
- **If outer does not catch the exception:** the unchecked error continues through the outer transaction interceptor; under default rollback rules, outer T1 is rolled back and `updateA()` is not committed.
- **If outer catches that exact exception and returns normally:** inner `NEVER` never joined T1 to mark it rollback-only, so T1 can commit `updateA()`, provided nothing else causes the transaction to roll back.

Illustrating conditional catching:

```java
@Transactional
public void processAndOptionallySkip() {
    repository.updateA();
    try {
        strict.mustRunWithoutTransaction();
    } catch (IllegalTransactionStateException ex) {
        // Ignore only if the business contract ALLOWS skipping the strict step.
        auditLogger.warn("Wrong transaction context", ex);
    }
}
```

The snippet above **is not standalone**, because `repository`, `strict`, and `auditLogger` are assumed dependencies. If the strict operation is a mandatory step of the use case, "swallowing the error to commit outer" is a bad design. The proper approach may be **adjusting transaction boundaries** to call strict before/after the transaction, or intentionally letting the exception fail the entire use case.

**Do not confuse with `UnexpectedRollbackException`:** that exception typically occurs when a participating `REQUIRED` scope marks the shared physical transaction rollback-only, yet outer still attempts to commit. With `NEVER`, Spring rejects **before inner ever joins the transaction**; the direct error type is `IllegalTransactionStateException`. If uncaught, outer can roll back because the exception propagated out, not because inner participated in T1.

## 4. Why is `NEVER` different from `NOT_SUPPORTED`?

Both propagations aim for **the method body not running inside the current transaction**, yet they handle a caller with an active transaction in two completely different ways.

```text
When T1 already exists:

NEVER:
T1 is active
  └── Call inner proxy
         └── THROW IllegalTransactionStateException
                └── Method body does NOT run

NOT_SUPPORTED:
T1 is active
  └── Call inner proxy
         ├── SUSPEND T1
         ├── Run body WITHOUT transaction T1
         ├── RESUME T1
         └── Return to outer
```

**`NEVER` is a declaration: "the caller must not bring a transaction in here."** If the caller violates this, the application must fix the call site or accept the failure.

**`NOT_SUPPORTED` is a declaration: "even if the caller has a transaction, run this block outside any transaction."** Spring attempts to suspend T1 temporarily and resume it afterward (depending on transaction manager support). JDBC updates inside the `NOT_SUPPORTED` block may auto-commit per statement. If T1 rolls back, they **do not automatically roll back with it**.

Choose `NEVER` when you need **early detection of contract violations**. Choose `NOT_SUPPORTED` when the intent is to **execute code outside a transaction even when the caller holds T1**. Neither replaces a real transaction when multiple SQL statements must commit/roll back together.

## 5. Comparison across the full propagation table

| Inner propagation | No existing transaction | Active transaction T1 |
| --- | --- | --- |
| `REQUIRED` | Creates a new transaction | Joins T1 |
| `SUPPORTS` | Runs without a new physical transaction | Joins T1 |
| `MANDATORY` | Throws error for missing transaction | Joins T1 |
| `REQUIRES_NEW` | Creates a new transaction | Suspends T1 and creates independent T2 |
| `NOT_SUPPORTED` | Runs without a transaction | Suspends T1 then runs without a transaction |
| **`NEVER`** | **Runs without a transaction** | **Throws `IllegalTransactionStateException`** |
| `NESTED` (if manager supports) | Behaves much like `REQUIRED` | Can create a savepoint inside T1 |

A few counterexamples:

- `NEVER` is **not** a "read-only transaction": `readOnly=true` only affects transaction attributes when applicable; `NEVER` forbids an active transaction.
- `NEVER` is **not** a "new transaction" like `REQUIRES_NEW`.
- `NEVER` is **not** a "savepoint" like `NESTED`.
- `NEVER` and `MANDATORY` are opposite preconditions: `MANDATORY` **requires** a transaction, while `NEVER` **forbids** a transaction.
- `NEVER` and `SUPPORTS` are similar when the caller has no transaction, but `SUPPORTS` agrees to join T1 whereas `NEVER` rejects T1.

## 6. Standalone runnable lab: Java 17+, Spring Framework, and H2

The lab's goal is not only to observe the exception, but also to prove **whether the method body ran** and **whether the outer transaction ultimately committed or rolled back**. The example uses:

- Java 17+, Maven 3.9+.
- Spring Framework **6.2.8**, Spring JDBC/transaction infrastructure.
- H2 **2.3.232** running in-memory; no Spring Boot or web server needed.
- A `counters` table with three rows: `outer`, `never`, `not_supported`. Each case resets all three to 0.

There are four cases:

1. **Without T1 → NEVER runs:** increments `never` to 1.
2. **With T1, outer catches NEVER error:** increments `outer` to 1; inner body does not run; T1 commits.
3. **With T1, NEVER error propagates:** inner body does not run; outer T1 rolls back.
4. **With T1, inner NOT_SUPPORTED then outer fails:** inner runs outside T1 and writes data; outer T1 rolls back, inner write persists.

### 6.1. Project structure

```text
never-tx-demo/
├── pom.xml
└── src/main/java/example/NeverDemo.java
```

### 6.2. `pom.xml`

The file begins **immediately** with the XML declaration; copy the code fence directly into `pom.xml`, without adding comments before it.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>never-tx-demo</artifactId>
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
                    <mainClass>example.NeverDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` provides `ApplicationContext` and bean lifecycle support; `spring-jdbc` provides `JdbcTemplate` and `DataSourceTransactionManager`; `spring-tx` contains propagation/transaction annotations. H2 must be on the compile classpath because the code imports `org.h2.jdbcx.JdbcDataSource`.

### 6.3. `src/main/java/example/NeverDemo.java`

```java
package example;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class NeverDemo {

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = ctx.getBean(JdbcTemplate.class);
            StrictService strict = ctx.getBean(StrictService.class);
            OuterService outer = ctx.getBean(OuterService.class);

            runCase("NEVER without T1", jdbc, strict::mustRunOutside);
            runCase("Outer catches NEVER error", jdbc, outer::catchesNever);
            runCase("Outer propagates NEVER error", jdbc, outer::propagatesNever);
            runCase(
                "NOT_SUPPORTED then outer fails",
                jdbc,
                outer::notSupportedThenFails
            );
        }
    }

    private static void runCase(String title, JdbcTemplate jdbc, Runnable work) {
        reset(jdbc);
        System.out.println("CASE: " + title);
        try {
            work.run();
            System.out.println("Outcome: returned");
        } catch (IllegalTransactionStateException ex) {
            System.out.println("Outcome: IllegalTransactionStateException");
        } catch (IllegalStateException ex) {
            System.out.println("Outcome: " + ex.getMessage());
        }

        Integer outer = jdbc.queryForObject(
            "SELECT n FROM counters WHERE k = ?", Integer.class, "outer"
        );
        Integer never = jdbc.queryForObject(
            "SELECT n FROM counters WHERE k = ?", Integer.class, "never"
        );
        Integer other = jdbc.queryForObject(
            "SELECT n FROM counters WHERE k = ?", Integer.class, "not_supported"
        );
        System.out.println(
            "Values: outer=" + outer + ", never=" + never
                + ", not_supported=" + other
        );
    }

    private static void reset(JdbcTemplate jdbc) {
        jdbc.execute("DROP TABLE IF EXISTS counters");
        jdbc.execute(
            "CREATE TABLE counters (k VARCHAR(30) PRIMARY KEY, n INT NOT NULL)"
        );
        jdbc.update("INSERT INTO counters(k, n) VALUES (?, ?)", "outer", 0);
        jdbc.update("INSERT INTO counters(k, n) VALUES (?, ?)", "never", 0);
        jdbc.update(
            "INSERT INTO counters(k, n) VALUES (?, ?)", "not_supported", 0
        );
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {
        @Bean
        public DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:never_tx;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        public StrictService strictService(JdbcTemplate jdbc) {
            return new StrictService(jdbc);
        }

        @Bean
        public OuterService outerService(
            JdbcTemplate jdbc, StrictService strict
        ) {
            return new OuterService(jdbc, strict);
        }
    }

    public static class StrictService {
        private final JdbcTemplate jdbc;

        public StrictService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(propagation = Propagation.NEVER)
        public void mustRunOutside() {
            System.out.println(
                "NEVER body active="
                    + TransactionSynchronizationManager.isActualTransactionActive()
            );
            jdbc.update("UPDATE counters SET n=n+1 WHERE k=?", "never");
        }

        @Transactional(propagation = Propagation.NOT_SUPPORTED)
        public void runWithoutT1() {
            System.out.println(
                "NOT_SUPPORTED body active="
                    + TransactionSynchronizationManager.isActualTransactionActive()
            );
            jdbc.update("UPDATE counters SET n=n+1 WHERE k=?", "not_supported");
        }
    }

    public static class OuterService {
        private final JdbcTemplate jdbc;
        private final StrictService strict;

        public OuterService(JdbcTemplate jdbc, StrictService strict) {
            this.jdbc = jdbc;
            this.strict = strict;
        }

        private void incrementOuter() {
            jdbc.update("UPDATE counters SET n=n+1 WHERE k=?", "outer");
        }

        private void showActive() {
            System.out.println(
                "Outer active="
                    + TransactionSynchronizationManager.isActualTransactionActive()
            );
        }

        @Transactional
        public void catchesNever() {
            showActive();
            incrementOuter();
            try {
                strict.mustRunOutside();
            } catch (IllegalTransactionStateException expected) {
                System.out.println("Caught in outer: IllegalTransactionStateException");
            }
        }

        @Transactional
        public void propagatesNever() {
            showActive();
            incrementOuter();
            strict.mustRunOutside();
        }

        @Transactional
        public void notSupportedThenFails() {
            showActive();
            incrementOuter();
            strict.runWithoutT1();
            throw new IllegalStateException("forced outer failure");
        }
    }
}
```

**Why does this example clarify the mechanism?**

- `Config` creates exactly one datasource and one JDBC transaction manager; `JdbcTemplate` uses that same datasource.
- `@EnableTransactionManagement` enables annotation processing. `OuterService` and `StrictService` are **two Spring beans** obtained via `ctx.getBean`, not manually instantiated targets in `main()`; outer's calls to strict go through the proxy.
- The `@Transactional` methods are public and classes are non-final, suitable for class-based Spring AOP proxies. Self-calls using `this` would yield different results.
- `reset()` runs outside any transaction before each case; thus every case starts with identical data and post-case queries observe the committed/rolled-back state.
- `mustRunOutside()` prints a line right at **the start of the method body**. When this line does not appear while T1 is active, we clearly see the interceptor prevented the body from running.
- `runWithoutT1()` demonstrates `NOT_SUPPORTED`: it enters the body even while outer T1 exists; writing to a different row avoids waiting on T1's row lock.
- The program deliberately catches the exception **outside the transactional boundary** in `runCase()` so it can still inspect the database; in the outer-catches case, the exception is caught **right inside** the outer boundary. The two catch locations produce different transaction outcomes.

### 6.4. Compile and run

In the `never-tx-demo` directory, using JDK 17+ and Maven 3.9+:

```bash
java -version
mvn -version
mvn -q compile exec:java
```

The following lines are the output **printed by the application** in exact order (ignoring extra Maven/Spring logs):

```text
CASE: NEVER without T1
NEVER body active=false
Outcome: returned
Values: outer=0, never=1, not_supported=0
CASE: Outer catches NEVER error
Outer active=true
Caught in outer: IllegalTransactionStateException
Outcome: returned
Values: outer=1, never=0, not_supported=0
CASE: Outer propagates NEVER error
Outer active=true
Outcome: IllegalTransactionStateException
Values: outer=0, never=0, not_supported=0
CASE: NOT_SUPPORTED then outer fails
Outer active=true
NOT_SUPPORTED body active=false
Outcome: forced outer failure
Values: outer=0, never=0, not_supported=1
```

### 6.5. Analysis of each case

**Case 1 — Without T1.** `strict.mustRunOutside()` is called from `main()` through the proxy, and the caller has not opened a transaction. `NEVER` allows the body to run. `TransactionSynchronizationManager.isActualTransactionActive()` returns `false`; the JDBC update increments `never=1` and auto-commits in the H2 demo environment. No new transaction is opened by `NEVER`.

**Case 2 — Outer catches error.** `OuterService.catchesNever()` opens T1 and increments `outer`. The call to `StrictService.mustRunOutside()` is rejected because the manager sees T1; **there is no `NEVER body` log**, and `never` does not increment. Outer catches `IllegalTransactionStateException` and completes normally, so T1 commits `outer=1`. Inner failing fast does not mean T1 is automatically marked rollback-only.

**Case 3 — Outer lets error propagate.** After incrementing `outer` in T1, outer calls strict and receives the exception. With no catch in outer, the unchecked error passes through the outer interceptor so T1 rolls back. In `runCase()`, the caller catches the exception outside the boundary; data returns to `outer=0, never=0`. No update ran inside the `NEVER` inner body.

**Case 4 — NOT_SUPPORTED comparison.** Outer opens T1, updates `outer`, and calls `StrictService.runWithoutT1()`. Spring suspends T1 and lets the inner code run outside the transaction, producing `NOT_SUPPORTED body active=false`; updating the `not_supported` row auto-commits separately. After resuming T1, outer throws `IllegalStateException` and T1 rolls back. `not_supported=1` persists, showing `NOT_SUPPORTED` is "suspend then execute", not "error and skip body" like `NEVER`.

## 7. When to use `NEVER` instead of another mechanism?

`NEVER` is an **architectural guard**, useful when an operation **must not run inside a caller's transaction**. For example, a very slow operation or an API that must be called outside a database transaction boundary to avoid holding JDBC connections/row locks while waiting. Placing `NEVER` on the bean's entry point rejects callers that accidentally wrap it in T1 early.

Illustrative orchestration pattern:

```java
public void orchestrate() {
    preflightService.checkOutsideTransaction(); // NEVER
    orderService.writeOrder();                  // REQUIRED
    notificationService.scheduleAfterCommit(); // Per outbox/event design
}
```

This is **illustrative code**; dependencies and transaction semantics of the notification step are not implemented. Do not infer that because three methods run sequentially, the transaction guarantees the notification only happens after commit. If you need to tie events to committed data, look into transactional outbox or after-commit hooks.

`NEVER` **does not guarantee atomicity** across multiple write operations in its method body. If the body runs two `UPDATE` statements outside a transaction in JDBC auto-commit mode, the first update may have already committed even if the second update fails. If they must roll back together, choose a real transaction boundary.

### 7.1. NEVER as a contract, not a security barrier

`NEVER` checks for an active transaction **according to the selected transaction manager** once the call is intercepted. It does not scan every resource/driver or every manually opened database transaction in the JVM. If an application uses multiple `PlatformTransactionManager`s or datasources, identify which manager handles the method via `@Transactional(transactionManager = "...")` and the actual resource.

Also do not treat `NEVER` as an authorization control. Code can still access the database outside a transaction, and a call bypassing the proxy will not execute the propagation check. Data security belongs to application/database permissions; transaction propagation is an execution coordination policy.

## 8. Technical pitfalls that produce unexpected results

### 8.1. Self-invocation bypasses the proxy

```java
public void outer() {
    inner(); // this.inner(), bypasses the proxy for @Transactional(NEVER).
}

@Transactional(propagation = Propagation.NEVER)
public void inner() {
    // In default proxy mode, the interceptor does not see self-invocation.
}
```

This is an **illustrative snippet**, not a complete Java class. When the outer method is on the same target bean, `this.inner()` invokes internally without going through the Spring proxy. The `NEVER` constraint **is not applied separately** to this call; if outer has T1, the inner code can run inside T1 without throwing a propagation exception. The clear fix is moving inner to another Spring bean and injecting the proxy, as in the lab.

### 8.2. Objects created with `new` outside the container

Writing `new StrictService(jdbc)` creates a plain Java target; `@Transactional` annotations on the class do not run the transaction interceptor automatically. If the caller holds a raw instance, `NEVER` may not check for T1 at all. Use `ApplicationContext.getBean(...)` or Spring constructor injection so the caller receives the proper bean/proxy. A caller created manually with `new` can still get the right semantics if **the callee reference is a proxy**.

### 8.3. Transaction infrastructure in the wrong ApplicationContext

In proxy mode, `@EnableTransactionManagement` registers transaction advice in the `ApplicationContext` containing that configuration. If a service bean is managed by the root context while transaction infrastructure is only enabled in a `DispatcherServlet` child context, the child will not re-proxy the root bean automatically. Verify which context actually **creates the bean**, not just where a controller sees it.

### 8.4. Private/final methods and JDK proxies

Class-based proxies do not intercept private methods in the usual way and cannot override final methods; JDK dynamic proxies only apply to eligible interface methods. Choose public Spring service methods called **through a proxy** for clear transaction boundaries. With `AdviceMode.ASPECTJ` weaving, constraints differ, but this article covers the **common Spring AOP proxy mode**.

### 8.5. Tests that already open a transaction

Spring Test may automatically open a test-managed transaction if a test method carries `@Transactional`. Calling a `NEVER` bean inside such a test throws an exception—which is the **correct behavior** because a transaction exists, even though the same call from `main` without T1 runs normally. Write two tests—with and without an outer transaction—checking both exception type and post-boundary DB state. Avoid removing the `NEVER` annotation just to silence a failing test when the contract truly forbids a transaction.

### 8.6. Catching an error does not mean automatic rollback-only

An `IllegalTransactionStateException` comes from `NEVER`'s interceptor **before joining T1**. If outer catches it and returns normally, outer's transaction can commit. If outer does not catch it, the unchecked exception passes through the outer interceptor and causes T1 to roll back under default policy. Both outcomes were demonstrated in the demo. Do not confuse this with `UnexpectedRollbackException`, which arises when outer tries to commit a transaction already marked rollback-only by a participating `REQUIRED` scope.

### 8.7. Transaction flags and thread context

`TransactionSynchronizationManager.isActualTransactionActive()` is a useful diagnostic tool for thread-bound JDBC transactions, but not a substitute for choosing the right manager and testing outcomes. With reactive R2DBC, Spring transactions typically rely on the Reactor Context; with `@Async`/`CompletableFuture`, thread-bound imperative transactions do not propagate automatically to new threads. Do not use a single thread-local flag to determine propagation across every transaction system.

## 9. Applying via `TransactionTemplate`

Besides declarative annotations, you can enforce the same policy using the programmatic transaction API:

```java
TransactionTemplate template = new TransactionTemplate(transactionManager);
template.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_NEVER
);

template.executeWithoutResult(status -> {
    performNonTransactionalWork();
});
```

This is **illustrative code**, assuming `transactionManager` and `performNonTransactionalWork()` already exist, and requiring imports for `TransactionTemplate` and `TransactionDefinition`. If the manager sees no active transaction, the callback runs without a new physical transaction. If T1 exists, `IllegalTransactionStateException` occurs **before the callback**, with no "suspend T1 then run callback" step.

The template is useful when the boundary needs to sit right around a block of code rather than a public Spring bean method. However, it still cannot detect every database transaction outside the manager, and does not give non-transactional SQL statements atomicity.

## 10. Experiments and self-check questions

| Scenario | Does `NEVER` body run? | Can outer T1 commit? | Observed result |
| --- | --- | --- | --- |
| Call `NEVER` directly via proxy, no T1 | Yes | No T1 exists | `never=1` |
| Outer T1 calls `NEVER` then catches | No | Possible, if business/rollback rules allow | `outer=1, never=0` |
| Outer T1 calls `NEVER` and lets error propagate | No | Rolls back by default | `outer=0, never=0` |
| Outer T1 calls `NOT_SUPPORTED` then outer rolls back | `NEVER` body irrelevant; `NOT_SUPPORTED` body runs | T1 rolls back | `not_supported` write outside T1 persists |

Exercises:

1. Change `Propagation.NEVER` on `StrictService.mustRunOutside()` to `NOT_SUPPORTED`. Predict whether the method body runs when outer T1 exists, and what happens to `never` if outer rolls back.
2. Change it to `MANDATORY` and call from `main` without T1. Explain why the exception occurs in the opposite situation from `NEVER`.
3. Remove `@EnableTransactionManagement` from a copy of the demo. Predict why the annotations may stop taking effect even though they remain in the source code.
4. Move the `NEVER` method into `OuterService` itself and call `this.mustRunOutside()`. Compare its behavior to calling through another bean's proxy.
5. Annotate a test with `@Transactional` and call `NEVER`. Explain why the test throws an error while calling from `main` without a transaction succeeds.
6. Build a test case with two datasources/transaction managers; determine which manager handles `NEVER` and why you should not generalize that it catches every transaction in the system.

**Core answer to remember:** `Propagation.NEVER` **allows the method to run only when no active transaction visible to the Spring transaction manager exists**. If a transaction exists, it **throws `IllegalTransactionStateException` before running the method body**. When you need to **suspend the transaction and still execute inner**, use `NOT_SUPPORTED`; when you need to **create a new independent physical transaction**, use `REQUIRES_NEW`. Do not confuse these three mechanisms.

## 11. Official references

- [Spring Framework — `Propagation` API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Propagation.html): definitions of `NEVER`, `NOT_SUPPORTED`, `MANDATORY`, and other propagations.
- [Spring Framework — `TransactionDefinition` API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/TransactionDefinition.html): active transaction conditions and propagation constants.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): interceptors and transaction boundaries.
- [Spring Framework — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): annotation configuration and proxy interception.
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): using `TransactionTemplate`.
