# Checking `isNewTransaction`, `isRollbackOnly`, and `isCompleted` with Spring TransactionStatus

## 1. Why Must Transaction Status Flags Be Read Accurately?

In Spring Framework, when managing transactions **programmatically** through `PlatformTransactionManager` or `TransactionTemplate`, the application can obtain a `TransactionStatus` object. Three methods are commonly used to inspect the lifecycle:

- `isNewTransaction()` — did the current scope **start a new transaction** or join another transaction?
- `isRollbackOnly()` — has the scope/transaction been **marked rollback-only**?
- `isCompleted()` — has **the scope represented by this status object** been finished by the transaction manager?

These three flags answer three **distinct** questions. In particular:

- `isNewTransaction() == false` does **not** automatically mean "no transaction": a `REQUIRED` scope may be joining an outer method's transaction.
- `isRollbackOnly() == true` does **not** mean physical rollback **has already happened immediately**. It indicates a state requesting or forbidding a normal commit.
- `isCompleted() == true` does **not** prove commit succeeded. A status can be completed **after commit, rollback, or an error-ending completion**. For a participating inner scope, its status can be completed while the **outer physical transaction is still running**.

This lesson belongs to **Direct Transaction API**. The focus is how to read the three flags to debug and control `getTransaction(...)`, `commit(...)`, and `rollback(...)`; propagation modes are included only to clarify differences across statuses.

### Learning Objectives

After studying this lesson, you will be able to:

1. Call `PlatformTransactionManager.getTransaction(TransactionDefinition)` to obtain `TransactionStatus`.
2. Understand the status lifecycle before/after `commit` or `rollback`.
3. Distinguish `setRollbackOnly()` from `rollback(status)`.
4. Explain why an inner `REQUIRED` has `isNewTransaction=false`, yet when marked rollback-only causes outer to fail with `UnexpectedRollbackException`.
5. Explain why `isCompleted=true` on an inner scope does not mean the outer transaction has ended.
6. Compare `REQUIRES_NEW` and `NESTED` with `hasSavepoint()` so you do not misread `isNewTransaction`.
7. Write and run a Java 17+ program verifying all three flags with Spring JDBC/H2.

## 2. From `PlatformTransactionManager` to `TransactionStatus`

Spring provides a direct transaction control API:

```java
PlatformTransactionManager txManager = /* injected bean */;
TransactionDefinition definition = new DefaultTransactionDefinition();

TransactionStatus status = txManager.getTransaction(definition);
try {
    performBusinessWork();
} catch (RuntimeException | Error ex) {
    txManager.rollback(status);
    throw ex;
}
txManager.commit(status);
```

This is **illustrative code**, without defining `txManager` or `performBusinessWork()`. The structure intentionally places `commit(status)` **outside the catch block**, because under the `PlatformTransactionManager` contract, once `commit` has returned **or thrown an error**, the status has already been completed/cleaned up; **do not call `rollback(status)` a second time just because `commit` failed**.

### 2.1. Three Objects with Distinct Roles

| API | Role |
| --- | --- |
| `TransactionDefinition` | Defines propagation, isolation, timeout, read-only, and transaction name if any. |
| `PlatformTransactionManager` | Starts/joins the transaction, decides commit/rollback, and cleans up resources. |
| `TransactionStatus` | Represents **one specific transaction request**, holding info to inspect state and request rollback. |

One transaction manager can return multiple statuses within the same call stack. For example:

```text
TransactionStatus outer = txManager.getTransaction(REQUIRED);
    -> outer.isNewTransaction() == true

    TransactionStatus inner = txManager.getTransaction(REQUIRED);
        -> inner.isNewTransaction() == false
        -> inner joins the physical transaction created by outer

    txManager.commit(inner);
        -> inner.isCompleted() == true
        -> outer's physical transaction does NOT necessarily commit yet

txManager.commit(outer);
    -> outer.isCompleted() == true
    -> if all conditions are valid, the physical transaction now commits
```

**Do not treat two statuses as two connections or two physical transactions.** `TransactionStatus` is an object for one **managed scope**, whereas physical transactions depend on propagation and the transaction manager.

### 2.2. Status vs. `TransactionSynchronizationManager`

Sometimes learners use:

```java
boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();
```

This is an **illustrative snippet**, requiring import `org.springframework.transaction.support.TransactionSynchronizationManager`. It tells you whether Spring considers an actual transaction active on the **current thread** in the imperative model. However, `active=true` does not distinguish outer T1 from inner T2 and does not replace reading a specific scope's `TransactionStatus`; `active=false` also does not replace checking every individual database resource.

`TransactionStatus` answers **who owns a new scope, who marked rollback-only, and which scope has completed**. `TransactionSynchronizationManager` helps diagnose the **thread's resource context**. Both must be interpreted in the context of the appropriate transaction manager.

## 3. `isNewTransaction()` — Did This Scope Start a New Transaction?

Signature:

```java
boolean isNewTransaction();
```

A `true` value means: in a typical Spring transaction manager environment, the corresponding `getTransaction(...)` call **started a new transaction** rather than merely joining an existing one.

### 3.1. Example of `REQUIRED` in Two Positions

```text
No active transaction:
  getTransaction(REQUIRED) -> outer status
    isNewTransaction = true

T1 is running:
  getTransaction(REQUIRED) -> inner status
    isNewTransaction = false
    inner is joining physical T1
```

This is crucial when debugging: if an inner `REQUIRED` reports `false`, **nothing is wrong**; that is the expected behavior because inner uses the transaction opened by outer.

However, `isNewTransaction() == false` **does not prove there is an active physical transaction**. With `PROPAGATION_SUPPORTS` or `PROPAGATION_NOT_SUPPORTED` when no transaction exists, Spring can also return a status with `false` without any physical transaction to commit. In Spring 6.2, APIs like `hasTransaction()` on `TransactionExecution` and observing the resource context help diagnose deeper. With other database managers, do not infer from a single boolean alone.

### 3.2. `REQUIRES_NEW` and `NESTED`

While outer T1 is running:

- Inner `REQUIRES_NEW` requests an **independent** physical transaction T2, suspending T1: inner `isNewTransaction()` is usually `true`.
- Inner `NESTED` with JDBC savepoint support **shares T1**, yet has a savepoint: inner `isNewTransaction()` is usually `false` and `hasSavepoint()` is `true`.
- Inner `REQUIRED` also usually has `isNewTransaction=false`, yet `hasSavepoint=false`.

Also check `hasSavepoint()` to avoid confusing a nested scope with a participating `REQUIRED`. When no outer transaction exists, `NESTED` can behave like starting a new transaction; the result depends on context and manager.

### 3.3. Mistakes to Avoid

Do **not** infer from `isNewTransaction=true` that the transaction has committed; an active status can still roll back. Do **not** infer from `false` that every database operation runs in autocommit mode. And do **not** take an already completed status and call manager commit a second time just because `isNewTransaction` still reflects that status's origin.

## 4. `isRollbackOnly()` — Rollback Requested, Not Necessarily Rolled Back Yet

Signatures:

```java
boolean isRollbackOnly();
void setRollbackOnly();
```

`isRollbackOnly()` checks the **rollback-only marked state**. In common implementations like `DefaultTransactionStatus`, it reflects the scope's local marker **or** the underlying transaction's rollback-only marker.

### 4.1. `setRollbackOnly` Differs from `rollback(status)`

```java
TransactionStatus status = txManager.getTransaction(definition);
status.setRollbackOnly();

// Right at this moment:
// status.isRollbackOnly() == true
// status.isCompleted() is usually still false

txManager.commit(status);
// Manager performs a rollback because the status was marked.
```

This is **illustrative code**, needing `txManager` and `definition`. Calling `setRollbackOnly()` **only sets a marker**; it does not clean up the scope on its own and is not equivalent to executing completion via `rollback(status)`. For a **new transaction owned by the scope itself**, `commit(status)` when **local rollback-only** is set usually performs an intentional rollback and **does not throw `UnexpectedRollbackException` merely because the caller itself requested rollback**.

Conversely, `txManager.rollback(status)` is the operation that **ends** the scope via the rollback path. Once the manager completes it successfully, `status.isCompleted()` is typically `true`.

### 4.2. Participating Scope Marking Rollback-Only

The trickiest scenario is two `REQUIRED` scopes sharing T1:

```text
outer = getTransaction(REQUIRED)  [new = true]     -> T1
  UPDATE A
  inner = getTransaction(REQUIRED) [new = false]   -> joins T1
    UPDATE B
    inner.setRollbackOnly()                       -> inner local marker
    inner.isRollbackOnly() = true
  commit(inner)                                   -> closes inner logical scope,
                                                     marks T1 rollback-only
  inner.isCompleted() = true
  outer.isRollbackOnly() = true (in the JDBC demo)
commit(outer)                                     -> ROLLBACK T1
                                                   -> UnexpectedRollbackException
```

**Why does outer receive `UnexpectedRollbackException`?** Outer code thinks it is completing normally and calls commit, yet physical transaction T1 was already marked for rollback by a participating scope. Spring must report that **commit did not happen**. This differs from **outer status itself** calling `setRollbackOnly()` and intentionally requesting rollback at commit.

Note: inner's local marker and the underlying transaction's global marker are distinct concepts. Right after `inner.setRollbackOnly()`, before ending the participating scope, do not assume every other status immediately sees the same value; check after the manager has processed `commit(inner)`/`rollback(inner)`. Manager settings such as `globalRollbackOnParticipationFailure` can affect certain exception rollback paths; the lab uses `DataSourceTransactionManager` defaults.

### 4.3. Why Is `isRollbackOnly=false` Not a Commit Guarantee?

A running status may currently be `false`, yet:

- Subsequent SQL fails, and the transaction manager may mark rollback-only.
- The outer method may throw an unchecked exception causing the transaction to roll back.
- The database may fail at commit due to constraints, connection drop, deadlock, or timeout.
- The caller may decide to call `rollback(status)` without ever having called `setRollbackOnly()`.

Therefore treat `isRollbackOnly()` as **a current-state signal**, not a final guarantee that commit is certain to succeed.

## 5. `isCompleted()` — Scope Has Ended, Not Commit Outcome

Signature:

```java
boolean isCompleted();
```

In the standard `PlatformTransactionManager` lifecycle:

- Immediately after `getTransaction(...)`, a newly received status typically has `isCompleted() == false`.
- After a successful `commit(status)`, the status has `isCompleted() == true`.
- After a successful `rollback(status)`, the status also has `isCompleted() == true`.
- Even when `commit(status)` throws a transaction exception, the manager contract specifies that the transaction/status has been completed and resources cleaned up; **do not call `rollback(status)` to "try fixing" a commit failure**.

Common confusion: `isCompleted()` refers to **this status's scope**, **not necessarily** the entire physical transaction that an outer scope may still hold.

```text
Outer T1 is open:
  outer.isCompleted() = false

Inner REQUIRED joins T1:
  inner.isCompleted() = false

manager.commit(inner):
  inner.isCompleted() = true       <-- inner logical scope has ended
  outer.isCompleted() = false      <-- T1 is still open
  physical T1 has not committed yet

manager.commit(outer):
  outer.isCompleted() = true       <-- T1 ends
```

**Never use `isCompleted()==true` to infer "committed successfully".** A scope that just rolled back is also completed. If you need the business outcome, inspect the **manager outcome, exceptions, transaction synchronization callbacks, or post-boundary data**. `isCompleted()` is a **lifecycle** flag, not a `COMMITTED/ROLLED_BACK` enum.

### 5.1. Do Not Reuse a Completed Status

Wrong:

```java
txManager.commit(status);
txManager.rollback(status); // Wrong: status is already completed.
```

This is an **illustrative error snippet**. With `AbstractPlatformTransactionManager`, calling `commit` or `rollback` on an already completed status throws `IllegalTransactionStateException`. Do not retain `TransactionStatus` across requests or cache it as a reusable object. **Each `getTransaction(...)` call creates its own scope/status, and each scope must be ended exactly once.**

## 6. Summary Table of the Three Flags Across Scenarios

This table assumes **Spring JDBC `DataSourceTransactionManager`**, propagation applied via `PlatformTransactionManager.getTransaction(...)`, and outer already holding a physical transaction where "inner" is described.

| Scope/Moment | `isNewTransaction()` | `isRollbackOnly()` | `isCompleted()` | Explanation |
| --- | --- | --- | --- | --- |
| Outer `REQUIRED`, no existing transaction, just started | `true` | `false` | `false` | Outer opens T1, currently active. |
| Inner `REQUIRED` joins T1 | `false` | `false` initially | `false` | Adds logical scope, does not open T2. |
| Inner after `setRollbackOnly()`, before ending | `false` | `true` | `false` | Inner is marked, scope not cleaned up yet. |
| Inner after `commit(inner)` processed rollback-only | Do not use new flag for further decisions | Do not use for further decisions | `true` | Inner scope completed; T1 may still be open and marked rollback-only. |
| Outer T1 after inner marked global rollback-only | `true` | `true` | `false` | Outer is still active but cannot commit normally. |
| Outer T1 after commit triggered unexpected rollback | Do not reuse status | Do not reuse status | `true` | Caller receives `UnexpectedRollbackException`. |
| Inner `REQUIRES_NEW` inside T1 | `true` | `false` initially | `false` | Opens independent T2, suspends T1. |
| Inner `NESTED` with JDBC savepoint | `false` | `false` initially | `false` | Same T1, usually `hasSavepoint=true`. |
| Outer explicit `rollback(status)` completed | Status origin does not matter | No need to inspect flag | `true` | Scope rolled back; do not call commit again. |

The table shows **typical semantics** in the illustrative configuration; exact behavior may vary across JTA, JPA, reactive transactions, and different managers/settings. Never conclude physical outcomes from a boolean tuple without context.

## 7. Runnable Java 17+ Project: Measuring All Three Flags

The project uses Spring Framework **6.2.8**, Spring JDBC, and H2 **2.3.232**. We call **`PlatformTransactionManager` directly**, **without `@Transactional` on a service**, to see exactly when a status appears and completes.

### 7.1. Directory Structure

```text
transaction-status-flags/
├── pom.xml
└── src/main/java/example/StatusFlagsDemo.java
```

### 7.2. `pom.xml`

Save this XML **verbatim** into `pom.xml`. The first line is the XML declaration; **do not place any comment before `<?xml ... ?>`**.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>transaction-status-flags</artifactId>
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
                    <mainClass>example.StatusFlagsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` creates the `ApplicationContext`/beans; `spring-jdbc` provides `JdbcTemplate` and `DataSourceTransactionManager`; `spring-tx` provides the transaction contracts; H2 is the in-memory JDBC database. We **do not need `@EnableTransactionManagement`** because all transactions in the lab are started **manually** via `PlatformTransactionManager` — this differs from declarative proxy mode.

### 7.3. `src/main/java/example/StatusFlagsDemo.java`

```java
package example;

import java.util.List;
import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.UnexpectedRollbackException;
import org.springframework.transaction.support.DefaultTransactionDefinition;

public class StatusFlagsDemo {

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            PlatformTransactionManager manager =
                context.getBean(PlatformTransactionManager.class);
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);

            commitNewTransaction(manager, jdbc);
            markNewTransactionRollbackOnly(manager, jdbc);
            participatingRequiredRollback(manager, jdbc);
            independentRequiresNew(manager, jdbc);
            nestedSavepointRollback(manager, jdbc);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        public DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:flags_demo;DB_CLOSE_DELAY=-1");
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
                DataSource dataSource) {
            DataSourceTransactionManager manager =
                new DataSourceTransactionManager(dataSource);
            manager.setNestedTransactionAllowed(true);
            return manager;
        }
    }

    private static DefaultTransactionDefinition definition(int propagation) {
        DefaultTransactionDefinition definition =
            new DefaultTransactionDefinition();
        definition.setPropagationBehavior(propagation);
        return definition;
    }

    private static void show(String label, TransactionStatus status) {
        System.out.println(
            label
                + ": new=" + status.isNewTransaction()
                + ", rollbackOnly=" + status.isRollbackOnly()
                + ", completed=" + status.isCompleted()
                + ", savepoint=" + status.hasSavepoint()
        );
    }

    private static void reset(JdbcTemplate jdbc) {
        // Run outside any transaction before each case.
        jdbc.execute("DROP TABLE IF EXISTS events");
        jdbc.execute(
            "CREATE TABLE events (" +
            "id INT PRIMARY KEY, label VARCHAR(40) NOT NULL)"
        );
    }

    private static List<String> rows(JdbcTemplate jdbc) {
        return jdbc.queryForList(
            "SELECT label FROM events ORDER BY id",
            String.class
        );
    }

    private static void insert(JdbcTemplate jdbc, int id, String label) {
        jdbc.update(
            "INSERT INTO events(id, label) VALUES (?, ?)",
            id,
            label
        );
    }

    private static void commitNewTransaction(
            PlatformTransactionManager manager,
            JdbcTemplate jdbc) {
        reset(jdbc);
        System.out.println("CASE 1: new transaction commits");

        TransactionStatus status = manager.getTransaction(
            definition(TransactionDefinition.PROPAGATION_REQUIRED)
        );
        show("start", status);
        insert(jdbc, 1, "committed");
        manager.commit(status);

        System.out.println("after commit: completed=" + status.isCompleted());
        System.out.println("rows=" + rows(jdbc));
    }

    private static void markNewTransactionRollbackOnly(
            PlatformTransactionManager manager,
            JdbcTemplate jdbc) {
        reset(jdbc);
        System.out.println("CASE 2: local rollback-only on new transaction");

        TransactionStatus status = manager.getTransaction(
            definition(TransactionDefinition.PROPAGATION_REQUIRED)
        );
        insert(jdbc, 1, "discard");
        status.setRollbackOnly();
        show("marked", status);

        // Even though commit is called, the manager intentionally switches to rollback.
        manager.commit(status);
        System.out.println("after commit request: completed="
                           + status.isCompleted());
        System.out.println("rows=" + rows(jdbc));
    }

    private static void participatingRequiredRollback(
            PlatformTransactionManager manager,
            JdbcTemplate jdbc) {
        reset(jdbc);
        System.out.println("CASE 3: inner REQUIRED marks shared transaction");

        TransactionStatus outer = manager.getTransaction(
            definition(TransactionDefinition.PROPAGATION_REQUIRED)
        );
        insert(jdbc, 1, "outer");
        show("outer start", outer);

        TransactionStatus inner = manager.getTransaction(
            definition(TransactionDefinition.PROPAGATION_REQUIRED)
        );
        insert(jdbc, 2, "inner");
        show("inner start", inner);
        inner.setRollbackOnly();
        show("inner marked", inner);

        // End participating scope; does not commit T1.
        manager.commit(inner);
        System.out.println("inner after end: completed=" + inner.isCompleted());
        show("outer after inner", outer);

        try {
            manager.commit(outer);
        } catch (UnexpectedRollbackException expected) {
            System.out.println(
                "outer commit outcome: UnexpectedRollbackException"
            );
        }
        System.out.println("outer after attempt: completed="
                           + outer.isCompleted());
        System.out.println("rows=" + rows(jdbc));
    }

    private static void independentRequiresNew(
            PlatformTransactionManager manager,
            JdbcTemplate jdbc) {
        reset(jdbc);
        System.out.println("CASE 4: REQUIRES_NEW commits independently");

        TransactionStatus outer = manager.getTransaction(
            definition(TransactionDefinition.PROPAGATION_REQUIRED)
        );
        insert(jdbc, 1, "outer");

        TransactionStatus inner = manager.getTransaction(
            definition(TransactionDefinition.PROPAGATION_REQUIRES_NEW)
        );
        show("inner REQUIRES_NEW", inner);
        insert(jdbc, 2, "inner");
        manager.commit(inner);
        System.out.println("inner after commit: completed="
                           + inner.isCompleted());
        show("outer resumed", outer);

        manager.rollback(outer);
        System.out.println("outer after rollback: completed="
                           + outer.isCompleted());
        System.out.println("rows=" + rows(jdbc));
    }

    private static void nestedSavepointRollback(
            PlatformTransactionManager manager,
            JdbcTemplate jdbc) {
        reset(jdbc);
        System.out.println("CASE 5: NESTED rolls back to savepoint");

        TransactionStatus outer = manager.getTransaction(
            definition(TransactionDefinition.PROPAGATION_REQUIRED)
        );
        insert(jdbc, 1, "outer");

        TransactionStatus nested = manager.getTransaction(
            definition(TransactionDefinition.PROPAGATION_NESTED)
        );
        show("inner NESTED", nested);
        insert(jdbc, 2, "nested");

        // Roll back the part after the savepoint without aborting T1.
        manager.rollback(nested);
        System.out.println("nested after rollback: completed="
                           + nested.isCompleted());
        show("outer after nested", outer);
        manager.commit(outer);

        System.out.println("outer after commit: completed="
                           + outer.isCompleted());
        System.out.println("rows=" + rows(jdbc));
    }
}
```

### 7.4. How to Run

Create both files according to the project structure. Inside the `transaction-status-flags` directory, using JDK 17 or higher and Maven 3.9+:

```bash
java -version
mvn -version
mvn -q compile exec:java
```

### 7.5. Expected Output

With Spring JDBC `DataSourceTransactionManager` and H2 as in the project, the lines printed by the program in order are:

```text
CASE 1: new transaction commits
start: new=true, rollbackOnly=false, completed=false, savepoint=false
after commit: completed=true
rows=[committed]
CASE 2: local rollback-only on new transaction
marked: new=true, rollbackOnly=true, completed=false, savepoint=false
after commit request: completed=true
rows=[]
CASE 3: inner REQUIRED marks shared transaction
outer start: new=true, rollbackOnly=false, completed=false, savepoint=false
inner start: new=false, rollbackOnly=false, completed=false, savepoint=false
inner marked: new=false, rollbackOnly=true, completed=false, savepoint=false
inner after end: completed=true
outer after inner: new=true, rollbackOnly=true, completed=false, savepoint=false
outer commit outcome: UnexpectedRollbackException
outer after attempt: completed=true
rows=[]
CASE 4: REQUIRES_NEW commits independently
inner REQUIRES_NEW: new=true, rollbackOnly=false, completed=false, savepoint=false
inner after commit: completed=true
outer resumed: new=true, rollbackOnly=false, completed=false, savepoint=false
outer after rollback: completed=true
rows=[inner]
CASE 5: NESTED rolls back to savepoint
inner NESTED: new=false, rollbackOnly=false, completed=false, savepoint=true
nested after rollback: completed=true
outer after nested: new=true, rollbackOnly=false, completed=false, savepoint=false
outer after commit: completed=true
rows=[outer]
```

This is the output **according to the semantics of this specific configuration**. Maven/Spring may print additional logs; when using another manager (JTA, Hibernate/JPA, reactive), verify the implementation details instead of assuming all flags/logs are identical.

### 7.6. Case-by-Case Analysis

**CASE 1 — New transaction commits successfully**

`getTransaction(REQUIRED)` runs when no other transaction exists, so the status has `new=true`, `rollbackOnly=false`, `completed=false`. `insert` runs inside JDBC T1. When `manager.commit(status)` completes, the scope is marked `completed=true` and the `committed` row appears after the boundary. This is the easiest case to read, yet you should not infer that every status with `completed=true` committed successfully — cases 2 and 3 prove the opposite.

**CASE 2 — Marking rollback-only in a new transaction**

The new status also has `isNewTransaction=true`. The code runs `insert` and then `status.setRollbackOnly()`; at that point `rollbackOnly=true` and `completed=false`. When the application calls `manager.commit(status)`, Spring sees the local marker and **intentionally rolls back**. The call finishes with `completed=true`, yet the database **no longer has** the `discard` row. This is crucial proof that `completed` does not mean `committed`, and `setRollbackOnly` is only a marker rather than immediately ending the transaction.

**CASE 3 — Inner REQUIRED marks the shared physical transaction**

Outer T1 opens first, `outer.isNewTransaction=true`. Inner `REQUIRED` joins T1, so `inner.isNewTransaction=false`. Inner writes a row and calls `setRollbackOnly()`; initially the marker belongs to the inner scope. When `manager.commit(inner)` is called, Spring does not physically commit T1; instead it processes the participating scope and marks **T1 rollback-only**. Therefore `inner.isCompleted=true` while `outer.isCompleted=false` and `outer.isRollbackOnly=true`. When outer subsequently requests commit, Spring rolls back T1 and throws `UnexpectedRollbackException`. Neither row exists after the boundary. Never confuse `inner.isCompleted=true` with "T1 has committed".

**CASE 4 — Independent inner REQUIRES_NEW**

Outer T1 has an uncommitted record. When inner is requested with `REQUIRES_NEW`, the manager suspends T1 and creates T2: inner status `new=true`. Inner writes and commits T2, and inner status `completed=true`. Then T1 resumes; `outer.isRollbackOnly=false` and is still incomplete. When the application rolls back T1, only the `outer` row is undone; the `inner` row committed in T2 remains. This is why inner's `isNewTransaction=true` has a different physical meaning from a participating inner `REQUIRED`.

**CASE 5 — Inner NESTED based on savepoints**

In Spring JDBC with savepoint support, inner `NESTED` has `new=false` and `hasSavepoint=true`. Inner writes data and then `rollback(nested)` reverts to the savepoint, undoing only inner's change. The nested status is now `completed=true`; outer T1 remains open with `rollbackOnly=false`, so it can commit the `outer` row. If the database/transaction manager does not support savepoints, `NESTED` may be rejected; the lab explicitly enables `setNestedTransactionAllowed(true)`.

## 8. Reading Status Inside `TransactionTemplate`

For common use cases, Spring recommends **`TransactionTemplate`** to avoid manual `getTransaction`/`commit`/`rollback` boilerplate.

```java
TransactionTemplate template = new TransactionTemplate(txManager);

template.executeWithoutResult(status -> {
    System.out.println(status.isNewTransaction());
    System.out.println(status.isRollbackOnly());
    System.out.println(status.isCompleted());

    doSomeJDBCWork();
    if (businessRuleFailed()) {
        status.setRollbackOnly();
    }
});
```

This is **illustrative code**, requiring declarations of `txManager`, `doSomeJDBCWork`, and `businessRuleFailed`. The callback receives a `TransactionStatus`; you can read the three flags and mark rollback-only inside the callback. **Never call `txManager.commit(status)` or `rollback(status)` yourself inside the callback**; `TransactionTemplate` is responsible for finishing the scope when the callback returns or throws. Inside the callback itself, `isCompleted()` is normally still `false` because the template has not finished the transaction yet.

### 8.1. If the Callback Calls `setRollbackOnly()`

```text
template.execute(callback)
    ├── Template opens/joins transaction
    ├── Callback receives status
    ├── Callback calls status.setRollbackOnly()
    └── Template handles scope completion
        └── New scope: roll back instead of commit
```

When the template is **joining an outer `REQUIRED` transaction**, the inner marker can make outer rollback-only. Do not interpret `setRollbackOnly` as "undo only the SQL statements inside the callback" if the callback is sharing T1. For a local savepoint, look at `NESTED` when supported; for an independent physical transaction, look at `REQUIRES_NEW`.

### 8.2. Status from `@Transactional` Proxy

Inside a method currently managed by the Spring `@Transactional` interceptor, you can access the current status using:

```java
TransactionStatus status =
    TransactionAspectSupport.currentTransactionStatus();
```

This is an **illustrative snippet**, requiring import `org.springframework.transaction.interceptor.TransactionAspectSupport` and running in a context with an active transaction aspect. If called outside a transactional AOP invocation, the API may throw `NoTransactionException`. Never assume every request with a `@Transactional` annotation in source creates a status — self-invocation, objects instantiated with `new`, and misconfigured context/proxies can bypass interception.

`TransactionAspectSupport.currentTransactionStatus()` differs from `PlatformTransactionManager.getTransaction(...)` in that the former retrieves the **status of the currently running AOP invocation**, whereas the latter **requests a transaction scope** programmatically. Do not mix statuses from multiple managers or close a status not owned by the current code.

## 9. Common Mistakes

### 9.1. "`isNewTransaction=false` means SQL runs outside a transaction"

False. An inner `REQUIRED` joining T1 has `false`, yet `JdbcTemplate` still uses T1's transaction-bound connection. Check propagation and the physical transaction before concluding.

### 9.2. "`isRollbackOnly=true` means the database has already rolled back"

False. The marker can be set while the transaction is still active and changes are uncommitted. Rollback finishes at a manager-handled boundary, not the instant the boolean becomes true.

### 9.3. "`isCompleted=true` means commit succeeded"

False. After an explicit rollback or after a commit attempt converted into a rollback, the status is still completed. If you need the outcome, inspect exceptions, transaction synchronization status, or verify data after the boundary ends.

### 9.4. "If the inner scope is completed, the outer transaction is also completed"

False. With `REQUIRED`, a participating inner scope can finish while outer still holds physical T1. Case 3 shows inner `completed=true` simultaneously with outer `completed=false`.

### 9.5. "Call `commit(status)`, catch errors, and call `rollback(status)`"

False. The `PlatformTransactionManager.commit` contract specifies that the status is already completed/cleaned up even when commit throws an exception. Calling `rollback` again easily throws `IllegalTransactionStateException` and hides the original error. Separate business work and commit in the direct-management pattern, or use `TransactionTemplate`.

### 9.6. "Just call `setRollbackOnly` and return normally, and the caller will know it rolled back"

Not necessarily. In a new transaction, the manager can complete an intentional rollback without throwing an exception; if the code returns a fake "success" result, the caller may not realize the operation was aborted. Design domain return values or exceptions appropriately. For a participating scope marking outer rollback-only, the outer caller may receive `UnexpectedRollbackException` when attempting to commit.

### 9.7. "Having `new=true` means every SQL call is automatically enlisted"

No. The status must match the right transaction manager and resources. A JDBC connection acquired outside Spring-aware mechanisms may not participate in the transaction. With `DataSourceTransactionManager`, use `JdbcTemplate`/`DataSourceUtils` on the right datasource; external HTTP/email/message brokers do not automatically roll back with a JDBC status.

### 9.8. "Read flags on an old status in a new request"

False. A status belongs to **one specific transaction scope**, not a global singleton or session state to cache. Never store `TransactionStatus` in a field shared across threads or reuse it after completion.

### 9.9. "Check `isCompleted` to decide whether to commit again"

False. Once completed, the scope is over. Do not call `commit`/`rollback` again. Checking `isCompleted()` is useful diagnostically in cleanup paths, not to turn a status into a reusable object.

### 9.10. "Manual API and declarative API always share the exact same status object"

Not necessarily. With a declarative method, AOP creates/holds a status for the invocation; manual `getTransaction` creates another scope with the chosen propagation. They may share the same physical transaction, yet they are not the same status object. Never manually `rollback` a status obtained from AOP if you do not manage that boundary.

### 9.11. "`isRollbackOnly=false` means commit will succeed 100%"

False. Constraint validation, flush, network/DB disconnect, deadlock, or subsequent logic can cause rollback or a commit exception. The flag is an observation **at a point in time**, not a prophecy of the final outcome.

### 9.12. "`NESTED` always creates a new physical transaction"

False in the JDBC savepoint model: `isNewTransaction=false`, `hasSavepoint=true`. Unlike `REQUIRES_NEW`, a nested scope cannot commit a physical transaction independently, and an outer rollback still undoes all changes of T1.

## 10. Writing Unit/Integration Tests for the Three Flags

A valuable test must check **both the status and the database outcome**. Never assert booleans alone and claim the system guarantees commits.

| Test | Recommended assertions |
| --- | --- |
| New `REQUIRED` | `new=true`, `completed=false` while active; `completed=true` after commit; data exists |
| New transaction calling `setRollbackOnly` | `rollbackOnly=true` before ending; `completed=true` after commit request; data does not exist |
| Participating `REQUIRED` | Inner `new=false`, after inner ends `completed=true` while outer `completed=false` |
| Inner rollback-only affecting outer | Outer receives `UnexpectedRollbackException` on commit; both outer/inner writes roll back |
| `REQUIRES_NEW` | Inner `new=true`; inner commits before outer rolls back; inner data remains |
| JDBC `NESTED` | Inner `new=false` and `hasSavepoint=true`; rolling back nested does not force outer rollback |
| Calling manager a second time with completed status | Verify `IllegalTransactionStateException` in a dedicated test; do not use as business flow |
| Exception on commit | Do not call `rollback` again on an already completed status; log root cause |

### 10.1. Testing with Multiple Transaction Managers

If using `DataSourceTransactionManager` for datasource A and a JPA/JTA manager for datasource B, verify **which manager** produced the status. `isNewTransaction()` from one manager does not confirm every resource on the JVM shares one physical transaction. Name managers clearly and test the actual participating resources.

### 10.2. Testing Under Spring Test `@Transactional`

When a test method has Spring Test automatically open an outer transaction, a `REQUIRED` call in your code can have `isNewTransaction=false` even though the exact same call in `main()` without an outer transaction has `true`. That is a **transaction context difference**, not a status bug. The lab tests deliberately use `main()` and reset outside transactions to prevent the test harness transaction from masking the results.

### 10.3. Reactive Transactions Do Not Use the JDBC Thread-Bound Model Verbatim

For reactive data access, use `ReactiveTransactionManager`/`TransactionalOperator` and the corresponding `ReactiveTransaction` object. A reactive transaction context can attach to the Reactor Context instead of the current Java thread. This lesson intentionally uses **imperative `PlatformTransactionManager` + Spring JDBC** to demonstrate observable state, without assuming thread-bound management primitives are identical for every reactive pipeline.

## 11. Exercises

**Exercise 1 — Predict state:** No transaction exists; call `getTransaction(REQUIRED)`. Before `commit`, predict the three flags. After commit, can you rely on `completed=true` to know commit definitely succeeded? Also check the database.

**Exercise 2 — Local rollback-only:** In CASE 2, replace `status.setRollbackOnly(); manager.commit(status);` with `manager.rollback(status);`. How do the two paths differ in the API? Is the database outcome the same or different? When does `completed` become true?

**Exercise 3 — Inner participation:** In CASE 3, remove `inner.setRollbackOnly()` and run. Predict whether outer receives `UnexpectedRollbackException`. Explain why `manager.commit(inner)` does not actually commit physical T1.

**Exercise 4 — When global rollback-only becomes visible:** In CASE 3, try printing `outer.isRollbackOnly()` before and after `manager.commit(inner)`. Distinguish inner's local marker from the physical transaction's marker after the participating scope ends.

**Exercise 5 — Two physical transactions:** In CASE 4, change `REQUIRES_NEW` to `REQUIRED`. If outer rolls back, does the inner row still exist? Does inner's `isNewTransaction` change?

**Exercise 6 — Savepoint:** In CASE 5, replace `manager.rollback(nested)` with `manager.commit(nested)`, and then have outer roll back. Predict whether the inner row remains; explain why nested commit is not a physical commit.

**Exercise 7 — Double finish:** In a test copy, after `manager.commit(status)` try calling `manager.commit(status)` again and catch `IllegalTransactionStateException`. Do not put this logic in a production service.

**Exercise 8 — Refactor to template:** Rewrite CASE 2 using `TransactionTemplate.executeWithoutResult(status -> ...)`. Call `status.setRollbackOnly()` inside the callback; do not manually call `manager.commit(status)`. Compare the database output.

**Exercise 9 — Domain policy:** Design a function returning `SUCCESS`/`REJECTED` instead of only printing status. If `rollbackOnly=true` due to a rule failure, what must the function do so it does not report a false success? Discuss domain exceptions versus return values.

**Exercise 10 — Cleanup on commit failure:** Write pseudocode handling exceptions per Spring's recommended pattern: `rollback` when business work throws an error **before commit**, yet **never** roll back a second time when `commit` throws an exception. Explain why.

### Self-Check Questions

- When `inner.isNewTransaction()==false`, is inner guaranteed to be running outside a transaction?
- Has `setRollbackOnly()` already performed a physical rollback immediately?
- Why can inner's `isCompleted()==true` coexist with `outer.isCompleted()==false`?
- Why can an outer scope that never called `setRollbackOnly` itself still see `isRollbackOnly()==true`?
- When `commit(status)` throws `UnexpectedRollbackException`, should you follow up with `rollback(status)`?
- Do two statuses that both have `new=true` necessarily share the same physical transaction?
- What does `hasSavepoint()==true` tell you that `isNewTransaction()` alone does not?

**Conclusion:** the three flags must be interpreted per **specific `TransactionStatus` scope**: `isNewTransaction` tells you the origin of the scope's transaction, `isRollbackOnly` tells you the **rollback intent/requirement**, and `isCompleted` tells you **the scope has been finished**. No single flag is a complete report on actual commit; combine propagation, transaction manager, exceptions, and post-boundary data outcomes.

## 12. Official References

- [Spring Framework 6.2 — `TransactionStatus` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/TransactionStatus.html): transaction status, `hasSavepoint()`, and inheritance from `TransactionExecution`.
- [Spring Framework 6.2 — `TransactionExecution` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/TransactionExecution.html): `isNewTransaction`, `isRollbackOnly`, `isCompleted`, `setRollbackOnly`.
- [Spring Framework 6.2 — `PlatformTransactionManager` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/PlatformTransactionManager.html): `getTransaction`, `commit`, `rollback`, and the contract not to roll back after a commit failure.
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): using `TransactionTemplate` or the transaction manager directly.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): logical/physical scopes, `REQUIRED`, `REQUIRES_NEW`, `NESTED`, rollback-only, and `UnexpectedRollbackException`.
- [Spring Framework — `AbstractPlatformTransactionManager` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html): coordinating participating transactions and rollback-only.
