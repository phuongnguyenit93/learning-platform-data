# Creating, Rolling Back, and Releasing Savepoints with `TransactionStatus` in Spring

## Objectives

A **savepoint** is a marker inside an **open physical transaction**. When a group of operations fails, you can revert database state back to that marker instead of rolling back the entire transaction. Spring Framework provides three APIs through `TransactionStatus` (which extends `SavepointManager`):

- `Object createSavepoint()` — creates a marker.
- `void rollbackToSavepoint(Object savepoint)` — undoes work after the marker.
- `void releaseSavepoint(Object savepoint)` — releases a marker that is no longer needed.

This lesson focuses on **manually managing savepoints with `TransactionStatus`**, within the context of `NESTED and savepoints` in Spring transaction management. It uses Java 17, Spring JDBC, and a database supporting JDBC savepoints. Afterward, you will understand the three calls accurately, know when to invoke each one, distinguish savepoints from whole-transaction commit/rollback and `@Transactional(propagation = NESTED)`, handle errors safely, and verify results directly in the database.

## 1. What Problem Do Savepoints Solve?

Suppose a batch-import transaction consists of three parts:

1. Write batch header info (mandatory).
2. Import a group of optional records (can be skipped if constraints fail).
3. Write batch summary (mandatory).

If the optional records group fails, you want to **undo only the optional part** and let the transaction continue. That is an appropriate case for placing a savepoint before the optional part.

```text
BEGIN TRANSACTION T
   |
   +-- INSERT "batch-start"          (kept)
   |
   +-- SAVEPOINT S
   |      |
   |      +-- INSERT "optional-1"    (will be undone)
   |      +-- INSERT "optional-2"    (will be undone)
   |      +-- error detected
   |      |
   |      +-- ROLLBACK TO S
   |      +-- RELEASE S
   |
   +-- INSERT "batch-end"            (kept)
   |
COMMIT TRANSACTION T
```

After commit, only `batch-start` and `batch-end` exist. Transaction T **remains a single physical transaction**; the savepoint creates no new connection, does not commit INSERTs before it, and does not make the kept work independent of the outer transaction.

If T ultimately rolls back entirely, even both `batch-start` and `batch-end` INSERTs are lost. This is the fundamental difference from `REQUIRES_NEW`: an independent child physical transaction can commit even if outer rolls back, whereas a savepoint **cannot commit independently**.

## 2. `TransactionStatus` and the `SavepointManager` Contract

`org.springframework.transaction.TransactionStatus` represents the status of a managed transaction. It extends `SavepointManager`, so the three savepoint operations are available. However, **having these methods on the interface does not guarantee the current manager/driver supports savepoints**.

| API | Meaning | What does NOT happen |
|---|---|---|
| `Object sp = status.createSavepoint()` | Creates a new savepoint in the current transaction; returns a handle for later use | Does **not** open a separate physical transaction; does **not** commit |
| `status.rollbackToSavepoint(sp)` | Reverts the database to its state at marker `sp`, discarding eligible SQL changes after the marker | Does **not** roll back the whole transaction; does **not** auto-release the marker |
| `status.releaseSavepoint(sp)` | Drops an unneeded marker so resources/database handles can be freed appropriately | Does **not** commit data; does **not** preserve data against an outer rollback |

**`Object` return type:** `createSavepoint()` returns an opaque handle (for JDBC, typically related to `java.sql.Savepoint`). Pass the **exact handle** back to `rollbackToSavepoint` / `releaseSavepoint`. Do not forge handles, cast them arbitrarily, or store a handle to reuse in another transaction/connection.

**Short savepoint lifetime:** it is valid only within the transaction and resource where it was created. After `releaseSavepoint(sp)`, you no longer have the right to roll back to that marker. After transaction completion, never reuse any handle.

### 2.1. `createSavepoint()`

```java
Object savepoint = status.createSavepoint();
```

Requests the transaction manager to create a new marker on the active transaction. JDBC drivers typically implement this via `Connection.setSavepoint()`. When the DB/driver/transaction manager lacks support, Spring may throw `NestedTransactionNotSupportedException` or `TransactionException`.

Critical requirement: there must be an **actually active transaction** and savepoint support. Do not call it on an already-committed/rolled-back transaction, or assume savepoint support solely from the interface's existence.

### 2.2. `rollbackToSavepoint(sp)`

```java
status.rollbackToSavepoint(savepoint);
```

Reverts database state back to **when the savepoint was created**, not back to the start of the transaction. Changes after the marker are undone; changes before the marker stay in the active transaction and can still roll back if the overall transaction fails.

Per the `SavepointManager` contract, **rolling back to a savepoint does not automatically release the savepoint**. If the database/driver allows, you can keep issuing operations after rollback; effects outside the DB (emails, HTTP calls, files, sent messages) are not rolled back by a JDBC savepoint.

When multiple savepoints exist, rolling back to an earlier marker can invalidate markers created after it depending on DB/driver semantics. Avoid using a handle belonging to a rolled-back branch.

### 2.3. `releaseSavepoint(sp)`

```java
status.releaseSavepoint(savepoint);
```

Release frees **the marker**, not "committing a child transaction." All data before/after the marker still belongs to the main physical transaction and can roll back when that transaction ends.

Spring documentation notes that most transaction managers automatically release savepoints upon transaction completion. Even so, when **creating savepoints manually to handle individual segments**, releasing once no longer needed is explicit and helps reduce resource retention. Some DBs/drivers have limits or special semantics for release; if release fails, Spring may throw `TransactionException`, though the contract encourages implementations to clean up flexibly when resources are ultimately freed at transaction completion.

### 2.4. Two Especially Important Confusions

- `status.setRollbackOnly()` is a request to **roll back the transaction**, not equivalent to `rollbackToSavepoint(sp)`. It can prevent the entire transaction from committing. **Do not call `setRollbackOnly()` when the goal is only discarding an optional group of operations**.
- `status.hasSavepoint()` primarily indicates **whether the TransactionStatus itself holds a savepoint created for a nested transaction**. It is **not** a general check of whether you called `createSavepoint()` manually, and `false` does not prove the manager lacks savepoint support. To use the manual API, retain the returned handle and handle exceptions if creation fails.

## 3. Where Do You Get `TransactionStatus`?

There are two typical ways.

### 3.1. Using `TransactionTemplate` — Clearer Approach for Manual Savepoints

```java
TransactionTemplate template = new TransactionTemplate(transactionManager);
template.executeWithoutResult(status -> {
    // status is the TransactionStatus of the template-managed transaction.
    Object sp = status.createSavepoint();
    try {
        // A group of database operations that can be partially rolled back.
        status.releaseSavepoint(sp);
    } catch (RuntimeException ex) {
        status.rollbackToSavepoint(sp);
        status.releaseSavepoint(sp);
        // Only swallow the exception if business rules permit it.
    }
});
```

This is **pattern-illustrating code**, not a standalone program: it requires `transactionManager`, a datasource, and real SQL. `TransactionTemplate.executeWithoutResult` supplies `TransactionStatus` directly. If a transaction already exists per the template's propagation (default `REQUIRED`), the template can join it; otherwise it opens a new transaction.

Strength: does not depend on AOP proxies to *obtain* the status. However, the transaction manager and transaction resource must still be configured properly; creating savepoints is only supported when the underlying transaction/driver supports them.

### 3.2. Inside a Method Managed by `@Transactional`

```java
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Transactional
public void importBatch() {
    TransactionStatus status =
        TransactionAspectSupport.currentTransactionStatus();
    Object sp = status.createSavepoint();
    // SQL and rollbackToSavepoint()/releaseSavepoint() as appropriate.
}
```

This is a **snippet inside a Spring service class**, not a standalone compilable file. `currentTransactionStatus()` requires the current call to be managed by the Spring Transaction AOP aspect/interceptor; without an invocation context, it throws `NoTransactionException`.

Notably, `this.importBatch()` from another method in the same bean can **bypass the proxy**, preventing `@Transactional` from activating. A connection having an actual transaction does not mean `TransactionAspectSupport.currentTransactionStatus()` is available in every context. Use a Spring bean invoked via proxy or explicitly use `TransactionTemplate`.

**Watch status scope:** use the exact status of the transaction in which you want to create a savepoint. Do not store `TransactionStatus` in a singleton field, cache, or another thread, or pass it to an async task for use after the transaction completes.

## 4. Technical Prerequisites to Satisfy

For JDBC in Spring Framework:

1. Use a database and JDBC driver supporting savepoints, usually checkable via `DatabaseMetaData.supportsSavepoints()`; this check is advisory and still requires testing with real transactions.
2. Use a savepoint-compatible transaction manager: `DataSourceTransactionManager` or `JdbcTransactionManager` is the standard choice for a single JDBC `DataSource`. On these managers, `PROPAGATION_NESTED` support is enabled by default, **yet the driver must support JDBC savepoints**.
3. Use the same `DataSource` for `JdbcTemplate` and the transaction manager. `JdbcTemplate` uses `DataSourceUtils` to obtain the transaction-bound connection.
4. Have an **open physical transaction**, not code running outside a transaction or on an autocommit connection without an appropriate transaction manager.
5. Run JDBC operations synchronously within the same transaction/thread; never pass a savepoint handle across threads, connections, or transactions.
6. With ORM/JPA, caches/persistence contexts may not revert to old state on a JDBC savepoint rollback. Therefore, do not extrapolate plain JDBC examples directly to JPA/Hibernate or JTA/reactive transaction managers.

**Failure modes to anticipate:**

| Situation | Consequence |
|---|---|
| Database/driver does not support savepoints | `NestedTransactionNotSupportedException` or corresponding transaction exception |
| Transaction is inactive/already completed | Create/rollback/release can fail due to invalid state |
| Misusing a handle from another connection | `SQLException`/`TransactionException` or driver-dependent undefined lifecycle |
| Releasing then rolling back the same marker | Handle is no longer valid |
| JDBC error puts transaction in rollback-needed state | Must roll back to a valid marker before continuing; if savepoint rollback fails, end transaction with full rollback |
| `setRollbackOnly()` already called | Release cannot "clear" a whole-transaction rollback request |
| Inner `@Transactional(REQUIRED)` marks rollback-only | Catching in outer does not necessarily allow commit; may throw `UnexpectedRollbackException` |

## 5. Proper Lifecycle: Create → Attempt Work → Roll Back or Release → Finish Transaction

Success case:

```text
BEGIN T
INSERT before marker
sp = createSavepoint()
INSERT optional part
releaseSavepoint(sp)
INSERT after marker
COMMIT T
```

Failure case where dropping just the optional part is acceptable:

```text
BEGIN T
INSERT before marker
sp = createSavepoint()
INSERT optional part A
INSERT optional part B -> anticipated error
rollbackToSavepoint(sp)
releaseSavepoint(sp)        (if supported; frees unneeded marker)
INSERT after marker
COMMIT T
```

Error case that **cannot be safely handled**:

```text
BEGIN T
sp = createSavepoint()
SQL -> severe error / unknown connection state
rollbackToSavepoint(sp) -> also fails
DO NOT keep writing as if transaction were clean
LET ERROR ESCAPE transaction boundary
ROLLBACK T (if transaction manager can still execute it)
```

An important pattern when swallowing **only anticipated errors**:

```java
Object sp = status.createSavepoint();
try {
    importOptionalRecords();      // SQL in the same transaction
    status.releaseSavepoint(sp);   // Success: release marker
} catch (KnownRecoverableDatabaseException ex) {
    status.rollbackToSavepoint(sp);
    status.releaseSavepoint(sp);
    // Record/report optional failure per business policy.
}
```

This is **Java pseudocode inside a transaction**, as `importOptionalRecords` and `KnownRecoverableDatabaseException` represent undeclared application logic. In production, catch only genuinely recoverable errors instead of swallowing every `Exception`. If creating the savepoint succeeds yet some statement throws an unexpected exception, let the transaction manager roll back the whole transaction as the exception escapes; do not force release in every branch since calling release on a broken connection can mask the root cause.

**Ordering must be designed carefully:** if you call `releaseSavepoint(sp)` too early, you can no longer roll back to that marker afterward. If `rollbackToSavepoint(sp)` succeeds, you should still release the finished marker per driver capability; Spring's contract explicitly notes rollback does **not** auto-release. Also do not call `rollbackToSavepoint` twice on the same handle after it has been released.

## 6. Runnable Java 17 Example: Verifying All Three APIs on H2

To avoid confusion with `@Transactional` self-invocation, the example uses `TransactionTemplate`, receives `TransactionStatus` directly, and runs on in-memory H2.

Scenarios:

1. Create savepoint, insert a temporary record, **roll back to savepoint**, **release**, then continue writing. The transaction still commits records before/after the marker.
2. Create savepoint, write valid data, only **release** without rolling back; when the transaction commits at the end, the data persists.
3. Release savepoint then throw an unchecked exception out of the transaction callback: **the entire transaction rolls back**, proving release is not a commit.
4. Create savepoint, execute a valid INSERT then intentionally violate the primary key, catch `DuplicateKeyException`, roll back to savepoint, release, and continue with another record.
5. Use **two savepoints** to demonstrate that rolling back to the outer marker erases changes since that marker; do not try reusing an inner marker already rolled back/invalidated.

### 6.1. Project Structure

```text
spring-savepoint-demo/
├── pom.xml
└── src/main/java/com/example/savepoint/Main.java
```

### 6.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-savepoint-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
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

`spring-jdbc` pulls in Spring transaction infrastructure and JDBC helpers; `h2` is the test database. No Spring Boot application or application context is needed here because `TransactionTemplate` is configured directly with the transaction manager. Spring 6.2 requires Java 17+; versions are pinned for reproducibility. Real applications should manage dependencies and security updates via supported BOMs/releases.

### 6.3. `src/main/java/com/example/savepoint/Main.java`

```java
package com.example.savepoint;

import java.util.List;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public class Main {
    private static void add(JdbcTemplate jdbc, int id, String label) {
        jdbc.update(
            "INSERT INTO work_items(id, label) VALUES (?, ?)",
            id, label
        );
    }

    private static List<String> labels(JdbcTemplate jdbc) {
        return jdbc.queryForList(
            "SELECT label FROM work_items ORDER BY id",
            String.class
        );
    }

    private static void clear(JdbcTemplate jdbc) {
        jdbc.update("DELETE FROM work_items");
    }

    public static void main(String[] args) {
        var dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl("jdbc:h2:mem:savepoint_demo;DB_CLOSE_DELAY=-1");
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        var jdbc = new JdbcTemplate(dataSource);
        jdbc.execute(
            "CREATE TABLE work_items (" +
            "id INT PRIMARY KEY, label VARCHAR(80) NOT NULL)"
        );

        var txManager = new JdbcTransactionManager(dataSource);
        var tx = new TransactionTemplate(txManager);

        // 1. Partial rollback, then release and continue writing.
        tx.executeWithoutResult(status -> {
            add(jdbc, 1, "before");
            Object sp = status.createSavepoint();
            add(jdbc, 2, "temporary");
            status.rollbackToSavepoint(sp);
            status.releaseSavepoint(sp);
            add(jdbc, 3, "after");
        });
        System.out.println("partial=" + labels(jdbc));
        clear(jdbc);

        // 2. Release without rollback, so data is kept until commit.
        tx.executeWithoutResult(status -> {
            add(jdbc, 1, "before");
            Object sp = status.createSavepoint();
            add(jdbc, 2, "kept");
            status.releaseSavepoint(sp);
            add(jdbc, 3, "after");
        });
        System.out.println("release=" + labels(jdbc));
        clear(jdbc);

        // 3. Even after release, if outer throws an exception, all changes roll back.
        try {
            tx.executeWithoutResult(status -> {
                add(jdbc, 1, "before");
                Object sp = status.createSavepoint();
                add(jdbc, 2, "not-committed");
                status.releaseSavepoint(sp);
                throw new IllegalStateException("rollback-all");
            });
        } catch (IllegalStateException ex) {
            System.out.println("full rollback=" + ex.getMessage());
        }
        System.out.println("after failure=" + labels(jdbc));
        clear(jdbc);

        // 4. Expected SQL error: roll back to marker and continue transaction.
        tx.executeWithoutResult(status -> {
            add(jdbc, 1, "before");
            Object sp = status.createSavepoint();
            try {
                add(jdbc, 2, "discarded");
                add(jdbc, 1, "duplicate-key"); // id=1 already exists
            } catch (DuplicateKeyException ex) {
                status.rollbackToSavepoint(sp);
                System.out.println("constraint recovered=true");
            }
            status.releaseSavepoint(sp);
            add(jdbc, 3, "after");
        });
        System.out.println("constraint=" + labels(jdbc));
        clear(jdbc);

        // 5. Two savepoints, roll back to outer marker.
        tx.executeWithoutResult(status -> {
            add(jdbc, 1, "root");
            Object outerSp = status.createSavepoint();
            add(jdbc, 2, "first");
            Object innerSp = status.createSavepoint();
            add(jdbc, 3, "second");

            status.rollbackToSavepoint(innerSp);
            status.releaseSavepoint(innerSp);
            add(jdbc, 4, "third");

            status.rollbackToSavepoint(outerSp);
            status.releaseSavepoint(outerSp);
            add(jdbc, 5, "tail");
        });
        System.out.println("two savepoints=" + labels(jdbc));
    }
}
```

**Java syntax notes:**

- The file named `Main.java` resides in package `com.example.savepoint`; the public class is `Main`.
- `TransactionTemplate.executeWithoutResult(status -> {...})` is supported in Spring 6.2; the callback parameter is `TransactionStatus`.
- Savepoint handles are stored in `Object` variables matching the contract.
- Each `clear(jdbc)` executes **after** the previous scenario's transaction has completed, separating each scenario's outcome.
- H2 with JDBC and `JdbcTransactionManager` supports savepoints; `DriverManagerDataSource` is only suitable for demos, not as a replacement for a connection pool in production.

### 6.4. Run Command and Results

In the `spring-savepoint-demo` directory, with JDK 17+ and Maven installed, run:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.savepoint.Main
```

Lines **printed by the program**, excluding environment-dependent Maven/SLF4J messages:

```text
partial=[before, after]
release=[before, kept, after]
full rollback=rollback-all
after failure=[]
constraint recovered=true
constraint=[before, after]
two savepoints=[root, tail]
```

**Analysis by database state:**

- `partial=[before, after]`: `temporary` was created after the savepoint and rolled back; the remaining two records belonged to the main transaction and committed.
- `release=[before, kept, after]`: when there is no rollback, release only drops the marker; all three INSERTs are committed by the main transaction.
- `after failure=[]`: releasing the savepoint did not save either INSERT from rolling back when the callback threw an unchecked exception out of `TransactionTemplate`.
- `constraint=[before, after]`: the INSERT `discarded` after the savepoint was also rolled back alongside handling the duplicate key error; afterward the transaction continued and wrote `after`. With databases like PostgreSQL, rolling back to a valid marker is also especially helpful when a failed SQL statement requires returning the transaction to a usable state.
- `two savepoints=[root, tail]`: rolling back to `innerSp` removed `second`; later rolling back to `outerSp` removed both `first` and `third`. `root` preceded both markers and `tail` was created after the last rollback, so both remain.

**Reproducibility limits:** the example tests standard Spring JDBC and H2 behavior; savepoint APIs, releasing, and SQL error handling can differ on other DBs. Run integration tests on your real driver/database before designing error-recovery logic.

## 7. Safe Error Management and Releasing

### 7.1. Do Not Swallow Errors Without Being Sure They Are Recoverable

A duplicate key error when importing *optional data* can be handled by rolling back to a savepoint. Yet lost connections, broken transaction managers, schema migration failures, or external resource errors can leave the transaction unsafe to continue. In those cases, let the exception escape the callback so the transaction manager rolls back everything and reports the true failure.

Do not wrap arbitrary SQL in `catch (Exception ignored)` and try to commit. A transaction still reporting `isActualTransactionActive() == true` does not guarantee that committing is safe.

### 7.2. Do Not Release Before Deciding to Roll Back

Wrong order:

```java
Object sp = status.createSavepoint();
doSomething();
status.releaseSavepoint(sp);
// Too late: cannot roll back to an already-released handle.
status.rollbackToSavepoint(sp);
```

This is an **intentionally wrong snippet**; do not use it in real code. After release, the handle is no longer a valid marker to roll back to.

Better:

```java
Object sp = status.createSavepoint();
try {
    doOptionalWork();
    status.releaseSavepoint(sp);
} catch (ExpectedRecoverableException ex) {
    status.rollbackToSavepoint(sp);
    status.releaseSavepoint(sp);
}
```

The second snippet is also only illustrative with placeholder methods/types; production code must explicitly handle the case where rollback or release **itself throws an error**. If rollback fails, do not try to continue business work; usually let the error propagate out so the transaction manager handles a full rollback. If release fails due to the driver, follow the API contract and resource manager reality rather than blindly ignoring every exception.

### 7.3. Do Not Use `setRollbackOnly()` for Partial Rollback

```java
Object sp = status.createSavepoint();
performOptionalInserts();
status.setRollbackOnly(); // Marks the ENTIRE transaction for rollback.
status.releaseSavepoint(sp);
```

This is an **example of wrong intent**, not a recommendation. `setRollbackOnly()` does not replace `rollbackToSavepoint(sp)`; releasing does not clear rollback-only. Choose clearly between **partial rollback** and **full rollback**.

### 7.4. Savepoints Do Not Make External Side Effects Atomic

For example, sending an email or calling a REST API between `createSavepoint()` and `rollbackToSavepoint()`. Those actions are not rolled back by the database. If events should only be sent when the transaction commits successfully, consider a transactional outbox or appropriate after-commit mechanism and understand its limits. Savepoints only affect operations supported by the transactional resource/database.

### 7.5. When Nested `@Transactional` Easily Triggers Unintended Rollback-Only

An inner service with `@Transactional(propagation = REQUIRED)` joins the outer physical transaction and throws an unchecked exception **through the transaction interceptor**. The inner interceptor can mark the entire transaction rollback-only before outer catches the exception. At that point, outer holding a manual savepoint will not automatically "clear" the interceptor's rollback-only flag; eventually `UnexpectedRollbackException` may occur.

If you want to use `TransactionStatus.createSavepoint()` manually to discard an optional part, design a clear transaction boundary and catch the error **inside the managed scope before it exits another `REQUIRED` interceptor**. Or use `@Transactional(propagation = NESTED)` on a separate bean if supported by the JDBC transaction manager/driver.

## 8. Comparing Manual Savepoints with `@Transactional(propagation = NESTED)`

| Criterion | Manual `TransactionStatus.createSavepoint()` | `Propagation.NESTED` via proxy |
|---|---|---|
| Who creates the marker? | Business code calls explicitly | Transaction manager when starting a logical nested scope with an outer transaction |
| Who rolls back to the marker? | Business code calls `rollbackToSavepoint` | Transaction manager when the nested scope decides to roll back |
| Who releases the marker? | Business code calls `releaseSavepoint` (or cleaned up at transaction end) | Infrastructure manages the nested scope's marker |
| Scope | Arbitrary placement inside a method/callback | Bound to an intercepted method boundary |
| Proxy requirement | Not required if using `TransactionTemplate` | Yes in Spring AOP proxy mode |
| Physical transaction | Still one running transaction | Still one physical transaction when NESTED joins outer |
| Error rollback mechanism | Manual catch/rollback per policy | Based on method and transaction manager rollback rules |
| Support | Requires resource/manager savepoint support | Requires resource/manager nested transaction/savepoint support |
| Best fit | One method with multiple small rollback decision points | Inner business unit with independent error handling yet no separate physical commit |

Short declarative example:

```java
@Service
class OptionalPartService {
    @Transactional(propagation = Propagation.NESTED)
    public void insertOptional() {
        // JDBC access via JdbcTemplate on the same datasource.
        // An unchecked error exiting the method causes Spring to roll back
        // to the savepoint created by the manager for the logical nested scope.
    }
}

@Service
class BatchService {
    private final OptionalPartService optional;

    BatchService(OptionalPartService optional) {
        this.optional = optional;
    }

    @Transactional
    public void importBatch() {
        // Mandatory part inside the outer transaction.
        try {
            optional.insertOptional(); // Called THROUGH ANOTHER BEAN'S PROXY.
        } catch (RuntimeException ex) {
            // Continue only if this error type is allowed to be skipped.
        }
        // Another mandatory part in the same physical transaction.
    }
}
```

These are **two illustrative classes**, not a standalone program: they need imports, component scanning, transaction manager configuration, and real SQL. `Propagation.NESTED` depends on savepoint support from the transaction manager and database, and **does not create an independent transaction B**. `@Transactional(REQUIRES_NEW)`, by contrast, opens a separate physical transaction and can commit regardless of outer rollback.

When `NESTED` is used on a call with no outer transaction, the transaction manager typically creates a new physical transaction like `REQUIRED`; no child savepoint is created merely from the propagation name. To ensure an outer transaction exists, check the call architecture and access policies.

## 9. Advanced Nuances to Know

### 9.1. Ordering and Validity Scope of Two Savepoints

A single transaction can have multiple savepoints:

```text
BEGIN
INSERT A
SP1 = createSavepoint()
INSERT B
SP2 = createSavepoint()
INSERT C
rollbackToSavepoint(SP2)     -- C is lost
releaseSavepoint(SP2)
INSERT D
rollbackToSavepoint(SP1)     -- B and D are lost
releaseSavepoint(SP1)
INSERT E
COMMIT                       -- A and E remain
```

Do not arbitrarily roll back an older marker and then reuse the handle of a marker created after it, because the database may have invalidated subsequent markers. Each savepoint should have a clear owning branch; LIFO management reduces errors, though you still need to understand DB semantics.

### 9.2. `status.hasSavepoint()` Does Not Count Manual Savepoints

`hasSavepoint()` reflects **whether the transaction status itself holds a savepoint for a nested scope**, not a list of handles you created via `createSavepoint()`. If you need to know whether a manual savepoint exists, the application must track the handle and its lifecycle. Do not use `hasSavepoint() == false` to decide to automatically create a savepoint if you may have already created one earlier.

### 9.3. Savepoint Synchronization Callbacks Since Spring 6.2

In Spring Framework 6.2+, `TransactionSynchronization` adds two callbacks:

- `savepoint(Object savepoint)`: invoked **right after** the resource savepoint is created.
- `savepointRollback(Object savepoint)`: invoked **right before** rolling back to the savepoint.

They can be used in infrastructure that must coordinate internal state with savepoints, yet they do not replace the three methods on `TransactionStatus`. Do not confuse `savepointRollback()` with `afterCompletion(STATUS_ROLLED_BACK)`: rolling back to a savepoint does not complete the physical transaction. Callbacks do not automatically undo external side effects unless you write corresponding handling logic.

### 9.4. JPA Persistence Context Does Not Necessarily Revert

When JDBC rolls back to a savepoint, entity objects already mutated in `EntityManager`/Hibernate session may still retain post-savepoint state. Some SQL may be deferred until flush. Therefore, **do not mechanically apply** plain JDBC examples using `JdbcTransactionManager` to `JpaTransactionManager` and JPA code without additionally testing flushing, persistence context, and savepoint support.

### 9.5. Savepoint Transaction Scope Does Not Propagate Across Threads/Reactive Pipelines

Spring's imperative JDBC model uses thread-bound resources. Spawning `@Async` or a new thread between create and rollback can cause the new thread's SQL to run outside the active transaction, and rolling back to the savepoint on the original thread will not undo those effects. With R2DBC/reactive, transactions use Reactor context and separate managers; the `TransactionStatus`/`JdbcTemplate` examples here are **not** how reactive transactions are implemented.

## 10. Common Errors and Remedies

| Symptom | Cause | Remedy |
|---|---|---|
| `createSavepoint()` throws `NestedTransactionNotSupportedException` | Driver/transaction manager or current resource does not support savepoints | Check DB driver, transaction manager, and active transaction; fall back safely |
| Rolled back to savepoint yet data still remains | SQL did not use the same physical transaction/connection; off-DB code; marker created at wrong moment | Use `JdbcTemplate` with the same datasource/manager; test DB state after commit |
| `releaseSavepoint()` then rollback throws error | Handle was already released or invalidated | Do not reuse; manage handle lifecycle |
| After partial rollback, outer still rolls back | Code called `setRollbackOnly()`; error escaped a `REQUIRED` interceptor; another unhandled error occurred | Verify transaction boundaries and rollback policies |
| After a JDBC error, subsequent SQL cannot run | Database requires recovery to a savepoint/errored transaction state | Create savepoint **before** fallible operation; roll back to it or roll back whole transaction |
| `hasSavepoint()` is false even though code called create | API only reports internal savepoint held by a nested status | Track manual savepoint handles explicitly |
| Rolled back to outer marker then reused inner marker | Later marker may have been invalidated | Do not keep/reuse handles from a rolled-back branch |
| Works on H2 yet fails on real database | Differences in DDL transactions, isolation, driver, and release semantics | Run integration tests on real DB, verify `supportsSavepoints()` |
| Rollback does not undo sending email/HTTP | Savepoints only cover transaction-supporting resources | Use outbox/after-commit/compensation for side effects |
| Using savepoints with no actual transaction | Running outside transaction or wrong context | Use `TransactionTemplate`/proper AOP boundary and the same manager |
| Business code holds handle too long | Transaction already completed or thread/connection changed | Keep handle in local transaction scope; do not cache |
| `NESTED` does not run via proxy | Self-invocation or transaction advice not enabled | Call separate bean via proxy or use explicit template |

## 11. Summary and Self-Check Questions

**Rules to remember:**

1. `createSavepoint()` creates a **marker inside a physical transaction**.
2. `rollbackToSavepoint(sp)` undoes **the part after the marker**, does not roll back the whole transaction, and **does not auto-release**.
3. `releaseSavepoint(sp)` cleans up the marker, **does not commit**, and does not protect the released part from an outer rollback.
4. `status.setRollbackOnly()` decides to roll back the **entire transaction**, not a partial rollback.
5. `TransactionTemplate` supplies `TransactionStatus` directly; `TransactionAspectSupport.currentTransactionStatus()` requires an invocation inside a Spring transaction interceptor.
6. Spring JDBC savepoints fit when the transaction manager, driver, and database support them; you must test SQL failures/cleanup and continued committability.
7. `Propagation.NESTED` uses the same physical transaction/savepoint, whereas `REQUIRES_NEW` uses an independent physical transaction.

**Self-check:**

- **Q1.** After `rollbackToSavepoint(sp)`, is the marker automatically released? — **No**, you can call `releaseSavepoint(sp)` when no longer needed.
- **Q2.** Does releasing a savepoint guarantee earlier INSERTs survive even if the outer transaction rolls back? — **No**, release does not commit.
- **Q3.** Does `status.hasSavepoint() == false` mean you cannot call `createSavepoint()`? — **No**, that API mainly reflects a savepoint held by a nested status.
- **Q4.** Once `setRollbackOnly()` has been called, can releasing a savepoint rescue the transaction to commit? — **No**.
- **Q5.** Two savepoints SP1 then SP2; after rolling back to SP1, can SP2 be reused? — **Should not be**; SP2 may have been invalidated.
- **Q6.** Why is a savepoint needed before an INSERT that might fail on PostgreSQL? — **To have a valid marker to roll back the failed part, restore transaction state, and continue subsequent SQL if the error is genuinely recoverable**.
- **Q7.** When you need a transaction to commit independently even if outer rolls back, choose savepoints or `REQUIRES_NEW`? — **`REQUIRES_NEW`**, while considering connections, locks, and business consistency.

## Official References

- Spring Framework — `TransactionStatus` API and `hasSavepoint()`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/TransactionStatus.html
- Spring Framework — `SavepointManager`: `createSavepoint`, `rollbackToSavepoint`, `releaseSavepoint`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/SavepointManager.html
- Spring Framework — `AbstractTransactionStatus`: distinguishing custom savepoints and nested held savepoints: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/AbstractTransactionStatus.html
- Spring Framework — `TransactionTemplate`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html
- Spring Framework — `TransactionSynchronization` callbacks since Spring 6.2: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html
- Spring Framework — Transaction Propagation, `PROPAGATION_NESTED`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — `DataSourceTransactionManager` and JDBC savepoint support: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html
- Spring Framework — Controlling Database Connections: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
