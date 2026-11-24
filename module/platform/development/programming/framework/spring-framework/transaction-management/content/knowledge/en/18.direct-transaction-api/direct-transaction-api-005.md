# Never Complete the Same TransactionStatus Twice

> **Module:** Spring Framework — Transaction Management. **Group:** Direct Transaction API. **Focus:** `TransactionStatus` lifecycle in the imperative `PlatformTransactionManager` API. Each status returned by `getTransaction(...)` may go through **only one completion path** — `commit(status)` **or** `rollback(status)`. Never "commit and then roll back to be safe", never roll back again when commit throws an error, and never reuse a completed status for another transaction. This lesson covers rules, state diagram, exception pitfalls, statuses joining an outer transaction, savepoints, `TransactionTemplate`, and a runnable Java 17/Spring Boot/H2 project.

## 1. The Most Important Rule

With Spring's imperative transaction management:

```java
TransactionStatus status = transactionManager.getTransaction(definition);

try {
    doBusinessWork();
} catch (RuntimeException | Error error) {
    transactionManager.rollback(status);
    throw error;
}

transactionManager.commit(status);
```

This is an **illustrative excerpt**, assuming `transactionManager` is a `PlatformTransactionManager`, `definition` is a `TransactionDefinition`, and `doBusinessWork()` is synchronous business work. It places **`commit` outside the `try` block that wraps only the business work**, avoiding catching an error thrown by `commit` itself and subsequently calling `rollback` on the same status.

**A `TransactionStatus` has only one completion:** if execution enters `commit(status)`, do **not** subsequently call `rollback(status)`; if `rollback(status)` has already been called, do **not** call `commit(status)`. The `PlatformTransactionManager` API is designed to complete and clean up the transaction when the commit call finishes, **even if commit throws an exception**. The Javadoc explicitly emphasizes never rolling back after a commit failure, because that rollback call would encounter an already completed transaction.

Common sources of misunderstanding:

- `commit(status)` **does not guarantee the database committed successfully**: it may roll back due to rollback-only, or throw an exception from the transaction manager/resource.
- `rollback(status)` **is not an "undo commit" operation**. If commit actually finished, a subsequent rollback is rejected; compensating for already committed data requires **a new transaction** and appropriate business compensation.
- `status.setRollbackOnly()` **does not complete the status**. It marks a rollback request, while the template/interceptor/manager performs the completion step at the right time.
- `status.isCompleted()` indicates **the scope/status has been completed**, not an oracle guaranteeing the business operation committed or definitively determining the outcome of a commit that failed over the network.
- "One status" does not mean "the entire call stack has only one status". Two `getTransaction(...)` calls can yield **two distinct logical statuses** both participating in **one physical transaction**. Each status must still be completed **once**.

**Takeaway before diving deeper:** `TransactionStatus` is an object holding the state of **a single transaction start/participation under the manager contract**, not a reusable multi-use ticket.

## 2. Three Objects in the Direct Transaction API

### 2.1. `PlatformTransactionManager`

Primary interface for imperative transactions:

```java
public interface PlatformTransactionManager extends TransactionManager {
    TransactionStatus getTransaction(TransactionDefinition definition)
        throws TransactionException;

    void commit(TransactionStatus status) throws TransactionException;

    void rollback(TransactionStatus status) throws TransactionException;
}
```

This is an **illustrative API signature sketch**, not Spring's full source. Concrete implementations may be `JdbcTransactionManager`, `DataSourceTransactionManager`, `JpaTransactionManager`, or other managers.

- `getTransaction(definition)`: applies propagation; creates a new transaction, joins an existing transaction, uses a savepoint, or creates an empty scope depending on definition and manager; returns a `TransactionStatus` for that call.
- `commit(status)`: completes the scope along the commit path, yet **automatically rolls back if the status is marked rollback-only** per the manager's rules. When merely joining an outer transaction, committing the inner scope **must not prematurely commit the outer physical transaction**.
- `rollback(status)`: completes the scope along the rollback path; for a new transaction it can actually roll back, for a participating scope it can mark the outer physical transaction rollback-only, and for a nested savepoint it can roll back to the savepoint.

### 2.2. `TransactionDefinition`

The definition describes **the request when acquiring a transaction**:

```java
DefaultTransactionDefinition definition =
    new DefaultTransactionDefinition();

definition.setName("register-payment");
definition.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRED
);
definition.setIsolationLevel(
    TransactionDefinition.ISOLATION_READ_COMMITTED
);
definition.setTimeout(15);
definition.setReadOnly(false);
```

This is an excerpt requiring imports `org.springframework.transaction.TransactionDefinition` and `org.springframework.transaction.support.DefaultTransactionDefinition`. You do not call `commit` on `TransactionDefinition`: it is only **configuration**. Each `getTransaction(definition)` returns the **status for a specific scope**.

### 2.3. `TransactionStatus`

Several particularly useful APIs:

| Method | Meaning | Does it complete the transaction? |
| --- | --- | --- |
| `isNewTransaction()` | Did the status open a new physical transaction per the manager | No |
| `hasTransaction()` | Is there an underlying transaction per the runtime interface | No |
| `hasSavepoint()` | Does the scope have a savepoint for nested behavior | No |
| `setRollbackOnly()` | Instructs the manager to allow only rollback when the scope completes | **No** |
| `isRollbackOnly()` | Rollback-only state per the status/manager | No |
| `isCompleted()` | Whether the scope has already been completed | Observation only |
| `flush()` | Hints to flush resources if supported by the manager | **Does not replace commit/rollback** |

**Note:** `TransactionStatus` extends `TransactionExecution` and `SavepointManager` in Spring Framework 6.x. Not every manager supports savepoints. `isNewTransaction() == false` does **not** mean you are allowed to skip completing the status: a participating logical scope must also be closed properly under the contract.

## 3. State Machine: Not Completed vs. Completed

Basic lifecycle of **one status**:

```text
                getTransaction(definition)
                           |
                           v
                  TransactionStatus S
                      completed=false
                           |
                +----------+-----------+
                |                      |
           business OK             business FAIL
                |                      |
           commit(S)               rollback(S)
                |                      |
                +----------+-----------+
                           |
                           v
                     S COMPLETED
                   completed=true
                           |
              +------------+-------------+
              |                          |
           commit(S)                  rollback(S)
              |                          |
              +------------+-------------+
                           |
                           v
                IllegalTransactionStateException
                    (standard Spring manager)
```

The `commit(S)` path may end in a **physical commit**, a **rollback due to rollback-only**, or an **exception**. Even so, under the `PlatformTransactionManager.commit` contract, once the call has finished (normally or via exception), the scope must be completed and cleaned up. **There is no valid path from "COMPLETED" back to "ACTIVE" for the same status**.

### Action Table

| Status state | Call | Expected outcome |
| --- | --- | --- |
| Not completed, owns new transaction | `commit(S)` | Commits or rolls back per flags/manager, then completed |
| Not completed, owns new transaction | `rollback(S)` | Rolls back, then completed |
| Not completed, participating scope | `commit(S)` | Completes scope; normally **does not commit the outer physical transaction** |
| Not completed, participating scope | `rollback(S)` | Completes scope; may mark outer rollback-only |
| Not completed, savepoint scope | `rollback(S)` | Rolls back to savepoint, then scope status is completed |
| **Already completed** | **`commit(S)`** | **Invalid; typically `IllegalTransactionStateException`** |
| **Already completed** | **`rollback(S)`** | **Invalid; typically `IllegalTransactionStateException`** |

Never "fix" a double-completion error by forging a `TransactionStatus` or directly mutating `completed` fields on an implementation. If you need a new transaction, call **`getTransaction` again** with an appropriate definition to receive a **different status**.

## 4. Double-Completion Errors: All Four Combinations

### 4.1. Commit Twice

```java
TransactionStatus status = tx.getTransaction(def);
jdbc.update("INSERT INTO events(id) VALUES (1)");

tx.commit(status);
tx.commit(status); // WRONG: status is already completed.
```

This is an excerpt where `tx`, `def`, and `jdbc` are already available. After the first commit, the status no longer represents an open scope. The second commit does **not** provide "higher commit certainty"; it can throw `IllegalTransactionStateException` reporting that the status is already completed.

### 4.2. Rollback Twice

```java
TransactionStatus status = tx.getTransaction(def);
jdbc.update("INSERT INTO events(id) VALUES (2)");

tx.rollback(status);
tx.rollback(status); // WRONG.
```

The first rollback already completed the scope. The second rollback does **not** make the data "roll back one extra time"; it is simply misusing a status past its lifecycle.

### 4.3. Commit Then Rollback

```java
TransactionStatus status = tx.getTransaction(def);
jdbc.update("INSERT INTO events(id) VALUES (3)");

tx.commit(status);
tx.rollback(status); // WRONG: cannot undo an already completed commit.
```

If the business needs to offset an already committed transaction (for example creating a reversal entry), design a **compensating action in a brand-new transaction**, without reusing the status. A compensating action also does not guarantee "the system returns as if nothing happened" if external side effects have already occurred.

### 4.4. Rollback Then Commit

```java
TransactionStatus status = tx.getTransaction(def);
jdbc.update("INSERT INTO events(id) VALUES (4)");

tx.rollback(status);
tx.commit(status); // WRONG: already completed along the rollback path.
```

Likewise, calling `commit` after rollback does not "recover" the rolled-back operation. If you want to retry, you must start a **new transaction** and re-run the business logic, with an appropriate retry policy and idempotency.

### Do Not Treat the Exception as Proof the DB Changed

Each `IllegalTransactionStateException` in the examples above reflects **calling the API with a completed status**, not necessarily an SQL failure in the first transaction. To verify whether the row exists or is gone, inspect the committed database state after a **valid** completion.

## 5. Critical Mistake: Catching Commit Exceptions and Rolling Back Again

A very common snippet among newcomers to `PlatformTransactionManager`:

```java
TransactionStatus status = tx.getTransaction(def);

try {
    repository.save(...);  // Excerpt: repository is an application dependency.
    tx.commit(status);
} catch (Exception ex) {
    tx.rollback(status); // WRONG if commit itself threw the exception.
    throw ex;
}
```

The problem: `catch` wraps both the **business work** and **`tx.commit(status)`**. If `commit(status)` throws `UnexpectedRollbackException`, `TransactionSystemException`, a pre-commit flush error, or a resource exception, the transaction has already been completed/cleaned up by the manager under the contract. The rollback call in the catch block is then **a second completion call**, which can throw `IllegalTransactionStateException` and mask the important original exception.

The `PlatformTransactionManager` documentation states explicitly: **do not call rollback after commit throws an exception**.

### 5.1. Right Pattern: Commit Outside the Business Catch

```java
TransactionStatus status = tx.getTransaction(def);

try {
    repository.save(...);
    validateBusinessRules();
} catch (RuntimeException | Error ex) {
    tx.rollback(status);
    throw ex;
}

tx.commit(status);  // Lies OUTSIDE the catch block above.
```

This is an **excerpt**, with `repository` and `validateBusinessRules()` belonging to the application. Distinguish two cases:

1. **Business work throws before commit is called:** roll back the status **once**, then propagate the error to the caller.
2. **Business work completes normally:** call commit **once**. If commit throws an error, **do not roll back on the same status**; handle/record the error outside the boundary.

Never put `tx.commit(status)` inside `finally`: `finally` also runs when business work fails, which could commit partial writes if no appropriate rollback-only marker was set.

### 5.2. What If Rollback Itself Fails?

If `tx.rollback(status)` throws a `TransactionSystemException`, we have **two errors**: the original business error and the rollback error. In production code, preserve the original error information, for example by adding a suppressed exception or using an exception mapper/logger capable of recording both, while **never calling rollback again on the old status**.

```java
try {
    doWork();
} catch (RuntimeException | Error original) {
    try {
        tx.rollback(status);
    } catch (RuntimeException rollbackFailure) {
        rollbackFailure.addSuppressed(original);
        throw rollbackFailure;
    }
    throw original;
}
tx.commit(status);
```

This is an **excerpt**. It keeps the rollback exception as primary when rollback fails and attaches the business failure to the suppressed list. Choosing which error is primary depends on system conventions. Never write a retry loop "rollback until it succeeds" on the same status.

### 5.3. Commit Errors Can Leave the Database Outcome Uncertain

Before commit, flush/constraint errors usually lead to rollback; in some failure modes involving distributed resources or connection loss at the exact moment of commit, the caller lacks sufficient evidence to know whether the commit was applied. **A cleaned-up status does not mean the caller knows for sure whether the business commit succeeded or failed**.

For critical operations, verify the outcome via an idempotency key/operation ID, transaction log, a database read on a new connection, or proper reconciliation. Never automatically repeat a non-idempotent payment solely because `commit` threw an exception.

## 6. `isCompleted()` and `isRollbackOnly()` Are Two Distinct States

`TransactionStatus` exposes two pieces of information that are easily confused:

```java
boolean rollbackOnly = status.isRollbackOnly();
boolean completed = status.isCompleted();
```

- `isRollbackOnly() == true`: the scope has been marked such that **it cannot commit normally**; it has not necessarily finished yet.
- `isCompleted() == true`: the scope **has already been completed** through a commit/rollback path. No further completion call can be made.

### 6.1. `setRollbackOnly()` Does Not Roll Back Immediately by Itself

```java
TransactionStatus status = tx.getTransaction(def);
jdbc.update("INSERT INTO events(id) VALUES (10)");

status.setRollbackOnly();

System.out.println(status.isRollbackOnly()); // true
System.out.println(status.isCompleted());    // false

tx.commit(status);  // Spring handles rollback-only, usually ROLLBACK.
System.out.println(status.isCompleted());    // true
```

This is an excerpt. In standard Spring managers, `commit(status)` may be called **once** even after local rollback-only has been set. The commit call processes the decision to **actually roll back**, without violating the single-completion rule. With direct local rollback-only on a new transaction, the manager normally performs the rollback without throwing `UnexpectedRollbackException` because the caller itself requested rollback.

You may also call `tx.rollback(status)` **instead of** `tx.commit(status)` after marking rollback-only, if that is the completion path you choose. But **never call both**.

### 6.2. `UnexpectedRollbackException` Differs from Duplicate Completion

`UnexpectedRollbackException` can occur when an outer transaction tries to commit while the physical transaction was already **marked rollback-only** by a participating scope without outer actively knowing. In that case `commit(outerStatus)` completed the transaction via rollback and threw the exception so the caller does not receive a false success.

**After `UnexpectedRollbackException`, do not roll back `outerStatus` again.** This was still a commit call that traversed the completion path. That error is about an **unexpected rollback decision**, whereas `IllegalTransactionStateException` after a second call is about **using an already completed status**.

## 7. One Physical Transaction Can Have Multiple Statuses

A common misconception: thinking each status corresponds to a separate physical JDBC transaction.

Direct example:

```java
TransactionStatus outer = tx.getTransaction(requiredDefinition);
TransactionStatus inner = tx.getTransaction(requiredDefinition);

System.out.println(outer.isNewTransaction()); // true if T1 did not exist.
System.out.println(inner.isNewTransaction()); // false: joins T1.

tx.commit(inner); // Completes INNER scope, does not commit T1.
tx.commit(outer); // Completes OUTER scope, commits T1 if valid.
```

This is an **excerpt**, where `requiredDefinition` is a `TransactionDefinition` with `PROPAGATION_REQUIRED`. Both statuses are **two distinct logical scope objects**, even though both participate in physical transaction T1.

Key points:

- Do not call `tx.commit(inner)` twice.
- Do not use `inner` in place of `outer`; each status belongs to its own scope.
- `tx.commit(inner)` does **not** automatically commit outer T1.
- `tx.rollback(inner)` on a participating scope **can** mark T1 rollback-only; outer's `commit(outer)` may then raise `UnexpectedRollbackException`.
- `inner.isCompleted()` can be `true` while `outer.isCompleted()` is still `false` and **physical T1 has not ended yet**.

### 7.1. `isNewTransaction() == false` Does Not Mean "Skip Completion"

A participating status may not create a new physical transaction, yet the manager still tracks the **logical scope**, rollback-only, and transaction synchronizations. Whenever you explicitly call `getTransaction`, the code owning that status must complete it **exactly once** via the appropriate commit/rollback path, never abandoning it because `isNewTransaction()` is false.

### 7.2. `PROPAGATION_NESTED` and Savepoints

```java
TransactionStatus outer = tx.getTransaction(requiredDef);
TransactionStatus nested = tx.getTransaction(nestedDef);
// nestedDef has PROPAGATION_NESTED; manager/JDBC supports savepoints.

tx.rollback(nested); // Rolls back to SAVEPOINT; nested status completed.
tx.commit(outer);    // Outer T1 can still commit its valid work.
```

This is an excerpt. `rollback(nested)` ends the **nested scope**, typically via rollback-to-savepoint, which is **not** the same as rolling back all of physical T1. `commit(nested)` likewise does not mean physical outer T1 has committed. Even so, **the nested status cannot be rolled back or committed again** once completed.

### 7.3. `PROPAGATION_REQUIRES_NEW`

```java
TransactionStatus outer = tx.getTransaction(requiredDef);
TransactionStatus innerNew = tx.getTransaction(requiresNewDef);

tx.commit(innerNew); // Separate T2 completes.
tx.rollback(outer);  // T1 rolls back, does not undo committed T2.
```

This is an excerpt, assuming the manager supports suspend/resume and `requiresNewDef` configures `PROPAGATION_REQUIRES_NEW`. T1 and T2 can be **two physical transactions**, and each status must be completed **once**. Never reuse `innerNew` to finish `outer`.

### 7.4. `PROPAGATION_SUPPORTS` Without a Physical Transaction

Even when a `getTransaction` call creates a scope with no physical transaction (for example `SUPPORTS` with no active transaction depending on manager config), the returned status still has a completion lifecycle; do not call `commit` multiple times just because there is no JDBC transaction. Whenever your code manages the API directly, follow the status contract strictly.

## 8. Who Owns Completing a TransactionStatus?

There must be **a single clear owner** for the completion decision.

| Management approach | Who receives the status? | Who calls commit/rollback? | What should the application do? |
| --- | --- | --- | --- |
| Direct `PlatformTransactionManager` | Code calling `getTransaction(def)` | **That exact code** | Call exactly one terminal operation based on business outcome. |
| `TransactionTemplate` | Callback receives status | **Template** | Execute business work, return/throw; call `setRollbackOnly()` if intentional rollback is needed. |
| `@Transactional` via proxy | Spring transaction interceptor | **Interceptor** | Return/throw per rollback rules; use `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()` when needed. |
| Reactive `TransactionalOperator` | Callback/operator receives reactive transaction context | **Reactive operator** | Build pipeline and appropriate signals; do not use imperative `PlatformTransactionManager` status to control reactive flows. |

**Never complete a status owned by a higher-level abstraction.** For example, `TransactionTemplate.executeWithoutResult(status -> ...)` already decides commit/rollback when the callback ends. Never call `transactionManager.commit(status)` inside the callback, because the template will also need to complete the status afterward and will hit double completion.

## 9. `TransactionTemplate`: How to Reduce Lifecycle Management Bugs

Spring recommends `TransactionTemplate` for imperative programmatic transactions in many scenarios because it automatically handles acquiring the transaction, exception handling, and scope completion.

```java
TransactionTemplate template = new TransactionTemplate(tx);

template.executeWithoutResult(status -> {
    jdbc.update("INSERT INTO audit_rows(id) VALUES (1)");
    // Normal return: template decides to commit.
});
```

Do **not** call `tx.commit(status)` inside the callback. If business logic wants a rollback without throwing an exception:

```java
template.executeWithoutResult(status -> {
    jdbc.update("INSERT INTO audit_rows(id) VALUES (2)");
    status.setRollbackOnly();
    // Template automatically completes with rollback when callback finishes.
});
```

The callback only **requests rollback**, without calling terminal APIs itself. If the callback throws an unchecked exception, the template usually rolls back and propagates the error to the caller. `TransactionTemplate` eliminates manual try/catch branches that easily double-complete.

### 9.1. TransactionTemplate Can Be Reused; Status Cannot

A `TransactionTemplate` can be stored as a field and used across many calls; each `execute(...)` creates and manages its **own** status. The template does not hold a global `TransactionStatus` to reuse. Propagation/isolation/timeout can be configured on the template; if different workflows need different definitions, use templates with matching configurations.

### 9.2. `@Transactional` Needs No Manual Status Retrieval

```java
@Transactional
public void submit() {
    repository.save(...);
    // Interceptor will commit on normal return,
    // or roll back per rules if an exception escapes.
}
```

This is an excerpt where `repository` is defined by the application. If you want rollback-only on a branch without throwing:

```java
TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
```

This is a Spring API requiring import `org.springframework.transaction.interceptor.TransactionAspectSupport` and must only be used when the corresponding transaction advice is active. It **does not call commit/rollback directly**, because the interceptor owns the lifecycle.

## 10. Runnable Project: Observing `isCompleted` and H2 Data Precisely

The project uses **Java 17, Spring Boot 3.5.7, Maven, Spring JDBC, and H2**. The program deliberately performs several **invalid API calls** to prove the exceptions; all expected errors are caught individually so the program continues, without accidentally rolling back other transactions.

Cases covered:

1. Commit once and check `isCompleted`.
2. Commit a second time and roll back after commit on the old status → `IllegalTransactionStateException`.
3. Roll back once, then roll back a second time and commit after rollback → same exception.
4. Mark rollback-only, verify **not yet completed**, call commit exactly once so Spring rolls back.
5. Business logic throws before commit: roll back exactly once; commit is not called.
6. Two `REQUIRED` scopes sharing T1: inner rollback marks T1 rollback-only; outer attempting commit receives `UnexpectedRollbackException`.
7. `NESTED` scope using a JDBC savepoint: roll back nested then commit outer, each status completed once.
8. `TransactionTemplate` automatically completes a rollback-only callback.

### 10.1. Project Structure

```text
transaction-status-once-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── vn/example/txonce/
        │       └── TransactionStatusOnceApplication.java
        └── resources/
            └── application.properties
```

### 10.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>vn.example</groupId>
    <artifactId>transaction-status-once-demo</artifactId>
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

### 10.3. `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:status_once;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
```

`DB_CLOSE_DELAY=-1` keeps the H2 in-memory database alive in the same JVM when JDBC connections return to the pool. No external database server is needed.

### 10.4. `src/main/java/vn/example/txonce/TransactionStatusOnceApplication.java`

```java
package vn.example.txonce;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.UnexpectedRollbackException;
import org.springframework.transaction.support.DefaultTransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootApplication
public class TransactionStatusOnceApplication {

    public static void main(String[] args) {
        SpringApplication.run(TransactionStatusOnceApplication.class, args);
    }

    @Bean
    JdbcTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean
    CommandLineRunner demo(
            PlatformTransactionManager manager,
            JdbcTemplate jdbc
    ) {
        return args -> {
            jdbc.execute(
                "CREATE TABLE tx_events (" +
                "id INT PRIMARY KEY, label VARCHAR(60) NOT NULL)"
            );

            demoCommitOnce(manager, jdbc);
            demoRollbackOnce(manager, jdbc);
            demoRollbackOnly(manager, jdbc);
            demoBusinessFailure(manager, jdbc);
            demoParticipatingScopes(manager, jdbc);
            demoNestedSavepoint(manager, jdbc);
            demoTemplate(manager, jdbc);
        };
    }

    private static DefaultTransactionDefinition required(String name) {
        DefaultTransactionDefinition def =
            new DefaultTransactionDefinition();
        def.setName(name);
        def.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRED
        );
        return def;
    }

    private static DefaultTransactionDefinition nested(String name) {
        DefaultTransactionDefinition def = required(name);
        def.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_NESTED
        );
        return def;
    }

    private static void insert(
            JdbcTemplate jdbc, int id, String label
    ) {
        jdbc.update(
            "INSERT INTO tx_events(id, label) VALUES (?, ?)",
            id, label
        );
    }

    private static int count(JdbcTemplate jdbc, int id) {
        return jdbc.queryForObject(
            "SELECT COUNT(*) FROM tx_events WHERE id = ?",
            Integer.class, id
        );
    }

    private static void expectCompletedFailure(
            Runnable operation, String label
    ) {
        try {
            operation.run();
            throw new AssertionError(
                "Expected completed-status rejection: " + label
            );
        } catch (IllegalTransactionStateException expected) {
            System.out.println(
                label + "=IllegalTransactionStateException"
            );
        }
    }

    private static void demoCommitOnce(
            PlatformTransactionManager manager, JdbcTemplate jdbc
    ) {
        TransactionStatus s =
            manager.getTransaction(required("commit-once"));

        System.out.println(
            "commit.beforeCompleted=" + s.isCompleted()
        );
        insert(jdbc, 1, "committed");
        manager.commit(s);

        System.out.println(
            "commit.afterCompleted=" + s.isCompleted()
        );
        System.out.println("commit.rows=" + count(jdbc, 1));

        expectCompletedFailure(
            () -> manager.commit(s), "commit.twice"
        );
        expectCompletedFailure(
            () -> manager.rollback(s), "commit.thenRollback"
        );
    }

    private static void demoRollbackOnce(
            PlatformTransactionManager manager, JdbcTemplate jdbc
    ) {
        TransactionStatus s =
            manager.getTransaction(required("rollback-once"));

        insert(jdbc, 2, "rolled-back");
        manager.rollback(s);

        System.out.println(
            "rollback.afterCompleted=" + s.isCompleted()
        );
        System.out.println("rollback.rows=" + count(jdbc, 2));

        expectCompletedFailure(
            () -> manager.rollback(s), "rollback.twice"
        );
        expectCompletedFailure(
            () -> manager.commit(s), "rollback.thenCommit"
        );
    }

    private static void demoRollbackOnly(
            PlatformTransactionManager manager, JdbcTemplate jdbc
    ) {
        TransactionStatus s =
            manager.getTransaction(required("rollback-only"));

        insert(jdbc, 3, "marked");
        s.setRollbackOnly();

        System.out.println(
            "marked.rollbackOnly=" + s.isRollbackOnly()
        );
        System.out.println(
            "marked.beforeCompleted=" + s.isCompleted()
        );

        manager.commit(s); // Single completion; handles rollback-only.

        System.out.println(
            "marked.afterCompleted=" + s.isCompleted()
        );
        System.out.println("marked.rows=" + count(jdbc, 3));
    }

    private static void demoBusinessFailure(
            PlatformTransactionManager manager, JdbcTemplate jdbc
    ) {
        try {
            executeBusinessThatFails(manager, jdbc);
            throw new AssertionError("Expected simulated failure");
        } catch (IllegalArgumentException expected) {
            System.out.println(
                "business.error=IllegalArgumentException"
            );
        }
        System.out.println("business.rows=" + count(jdbc, 4));
    }

    private static void executeBusinessThatFails(
            PlatformTransactionManager manager, JdbcTemplate jdbc
    ) {
        TransactionStatus s =
            manager.getTransaction(required("business-work"));

        try {
            insert(jdbc, 4, "business-error");
            throw new IllegalArgumentException("Simulated failure");
        } catch (RuntimeException | Error failure) {
            manager.rollback(s);
            throw failure;
        }

        // No commit because this business operation intentionally always fails.
    }

    private static void demoParticipatingScopes(
            PlatformTransactionManager manager, JdbcTemplate jdbc
    ) {
        TransactionStatus outer =
            manager.getTransaction(required("outer"));

        insert(jdbc, 5, "outer");
        TransactionStatus inner =
            manager.getTransaction(required("inner"));

        System.out.println(
            "participant.innerIsNew=" + inner.isNewTransaction()
        );

        insert(jdbc, 6, "inner");
        manager.rollback(inner); // Marks T1 rollback-only.

        System.out.println(
            "participant.innerCompleted=" + inner.isCompleted()
        );
        System.out.println(
            "participant.outerBeforeCompleted=" +
                outer.isCompleted()
        );

        try {
            manager.commit(outer);
            throw new AssertionError(
                "Expected UnexpectedRollbackException"
            );
        } catch (UnexpectedRollbackException expected) {
            System.out.println(
                "participant.outerCommit=UnexpectedRollbackException"
            );
        }

        System.out.println(
            "participant.outerAfterCompleted=" +
                outer.isCompleted()
        );
        System.out.printf(
            "participant.rows=%d,%d%n",
            count(jdbc, 5), count(jdbc, 6)
        );
    }

    private static void demoNestedSavepoint(
            PlatformTransactionManager manager, JdbcTemplate jdbc
    ) {
        TransactionStatus outer =
            manager.getTransaction(required("nested-outer"));
        insert(jdbc, 7, "outer-before-savepoint");

        TransactionStatus nested =
            manager.getTransaction(nested("nested-inner"));

        System.out.println(
            "nested.hasSavepoint=" + nested.hasSavepoint()
        );
        insert(jdbc, 8, "nested-to-rollback");
        manager.rollback(nested); // Rolls back to savepoint.

        insert(jdbc, 9, "outer-after-savepoint");
        manager.commit(outer);

        System.out.printf(
            "nested.rows=%d,%d,%d%n",
            count(jdbc, 7), count(jdbc, 8), count(jdbc, 9)
        );
    }

    private static void demoTemplate(
            PlatformTransactionManager manager, JdbcTemplate jdbc
    ) {
        TransactionTemplate template =
            new TransactionTemplate(manager);

        template.executeWithoutResult(status -> {
            insert(jdbc, 10, "template-rollback");
            status.setRollbackOnly();
            // Template owns commit/rollback: do not call manager directly.
        });

        System.out.println("template.rows=" + count(jdbc, 10));
    }
}
```

**Demo characteristics:**

- `JdbcTransactionManager` receives the exact `DataSource` that `JdbcTemplate` uses, so JDBC operations join the same thread-bound transaction.
- Each `demo...` method holds only the status of the scope it created; `insert` and `count` do not open separate transactions.
- Every `INSERT` in the example uses distinct IDs to verify commit/rollback cleanly.
- In `demoCommitOnce` and `demoRollbackOnce`, invalid API calls are attempted only **after the status has completed**, and are caught inside `expectCompletedFailure`.
- `demoRollbackOnly` shows `setRollbackOnly()` sets `isRollbackOnly=true` while `isCompleted=false` until the manager processes `commit`.
- `demoBusinessFailure` rolls back once on the business error; **there is no commit call** after rollback.
- `demoParticipatingScopes` intentionally creates two distinct statuses joining T1, illustrating inner completed while outer is not yet completed. `UnexpectedRollbackException` means outer's commit ended with a rollback.
- `demoNestedSavepoint` uses H2's JDBC savepoint via a manager supporting `PROPAGATION_NESTED`. Rolling back nested does not roll back outer.
- `demoTemplate` lets the template manage the transaction, without secretly calling the manager from inside the callback.

**Scope:** this demo uses one JVM, one JDBC datasource, and one transaction manager; it does not cover all behaviors of JTA/XA, JPA flushing, or reactive transaction managers.

### 10.5. Build and Run

In the `transaction-status-once-demo` directory:

```bash
java -version
mvn -version
mvn -q package
java -jar target/transaction-status-once-demo-1.0.0.jar
```

Lines **explicitly printed by the demo code** with the Spring Boot 3.5.7 / JDBC / H2 configuration above:

```text
commit.beforeCompleted=false
commit.afterCompleted=true
commit.rows=1
commit.twice=IllegalTransactionStateException
commit.thenRollback=IllegalTransactionStateException
rollback.afterCompleted=true
rollback.rows=0
rollback.twice=IllegalTransactionStateException
rollback.thenCommit=IllegalTransactionStateException
marked.rollbackOnly=true
marked.beforeCompleted=false
marked.afterCompleted=true
marked.rows=0
business.error=IllegalArgumentException
business.rows=0
participant.innerIsNew=false
participant.innerCompleted=true
participant.outerBeforeCompleted=false
participant.outerCommit=UnexpectedRollbackException
participant.outerAfterCompleted=true
participant.rows=0,0
nested.hasSavepoint=true
nested.rows=1,0,1
template.rows=0
```

Spring Boot/HikariCP may print additional startup/shutdown logs. The lines above are the expected application stdout, **excluding** framework logs. This example uses the specific defaults of `JdbcTransactionManager` and H2; with other transaction managers, re-test rollback-only, nested support, and specific exception types.

### 10.6. Explaining Results via Committed State

| Group | Status completed? | Record remains in DB? | Explanation |
| --- | --- | --- | --- |
| Valid commit | `true` after commit | ID 1: **1** | Commit finished; second call on status rejected |
| Valid rollback | `true` after rollback | ID 2: **0** | Rollback finished; second call rejected |
| Mark rollback-only | `false` right when marked; `true` after commit call | ID 3: **0** | Single completion handles rollback-only |
| Business error | `true` after rollback | ID 4: **0** | Error before commit; rolled back once |
| Participating REQUIRED | Inner completed before outer | ID 5/6: **0/0** | Inner rollback marks T1 rollback-only; outer commit rejected with UnexpectedRollbackException |
| Nested savepoint | Nested completed first, outer completed later | ID 7/8/9: **1/0/1** | Inner savepoint rolled back, outer still commits |
| TransactionTemplate | Template completes automatically | ID 10: **0** | Callback marks rollback-only; template rolls back |

Never rely solely on `isCompleted()` to infer "data committed"; always consider **which path completed the status**, rollback-only, manager type, exceptions, and database state.

## 11. A Transaction Status Is Not a Connection to Reuse

A JDBC connection in a pool can be reused many times over an application's lifetime, yet **that does not mean a `TransactionStatus` can be used multiple times**. The transaction manager creates and cleans up a dedicated scope on every `getTransaction` call.

After commit/rollback:

- Resource bindings and transaction synchronizations for the scope may be cleaned up.
- The connection may be returned to the pool, with auto-commit/isolation/read-only state restored per manager/driver.
- `afterCompletion` callbacks may have fired.
- If an outer transaction was previously suspended due to `REQUIRES_NEW`, the manager may resume outer.
- The old `TransactionStatus` is already completed; keeping it in a field/cache does not allow completing it again.

**Never store a status in a mutable singleton field** shared across HTTP requests or jobs; a status belongs to a single execution and transaction context. Imperative transactions are normally thread-bound. Sharing a status across threads or letting multiple callbacks complete it easily causes races and lifecycle bugs.

## 12. Handling Commit Failures Properly

A commit failure can occur at several stages:

| Stage | Example | What code must do |
| --- | --- | --- |
| Before-commit flush/validation | JPA flush detects unique violation or serialization conflict | Catch exception **outside** commit call; do not roll back that status again |
| JDBC/DB commit | Connection lost, deadlock/transaction abort, resource error | Do not reuse status; evaluate outcome via idempotency/reconciliation |
| Transaction coordinator | Unexpected global rollback-only, heuristic outcome | Classify exception, retain correlation ID, do not call rollback again |
| Cleanup/synchronization | Error releasing/restoring resource | Do not treat status as still alive merely because an exception occurred |

This is a **list of scenarios**; exact exception types and outcomes depend on manager/driver/DB. Under the `PlatformTransactionManager.commit` contract, the transaction must be completed and cleaned up when the commit call finishes, whether normally or by throwing. Therefore code like:

```java
try {
    tx.commit(status);
} catch (TransactionException ex) {
    tx.rollback(status); // WRONG: do not roll back status again.
    throw ex;
}
```

is an **anti-pattern**. When handling the error, only log/propagate, look up the outcome, or start **another transaction** for compensation — never use the old status.

### 12.1. Is `isCompleted()` Enough to Do "If Not Completed, Roll Back"?

Do not rely on `isCompleted` as the **sole safeguard** for deciding whether to retry a terminal call after a commit error. In standard Spring implementations, the commit call handles cleanup even when throwing; the contract already states never to call rollback after a commit failure. `isCompleted` is useful for observation/troubleshooting and catching programming errors, not for replacing ownership/state-machine discipline or proving commit outcomes.

If you write:

```java
try {
    doWork();
    tx.commit(status);
} finally {
    if (!status.isCompleted()) {
        tx.rollback(status);
    }
}
```

then logic depends entirely on the transaction manager's internal state and exception handling, blurring the boundary of "has commit started yet?". The simpler, recommended approach is to **limit try/catch strictly to the business work and call commit outside**, or use `TransactionTemplate`.

## 13. TransactionTemplate When the Callback Throws an Error

A clear callback pattern:

```java
TransactionTemplate template = new TransactionTemplate(tx);

try {
    template.executeWithoutResult(status -> {
        jdbc.update("INSERT INTO events(id) VALUES (99)");
        throw new IllegalStateException("Business rejected");
    });
} catch (IllegalStateException expected) {
    // Template has already handled rollback for the corresponding scope.
}
```

If the callback throws an unchecked exception before completion, the template handles rollback. Callers outside the template **must not retain the callback status and call `rollback` again**. If the callback has no exception yet wants a rollback, call `status.setRollbackOnly()` and return.

With `TransactionTemplate`, transaction lifecycle management logic is generally more reliable and concise than hand-writing `getTransaction/try/catch/commit/rollback`. When an outer transaction exists, the template's propagation decides whether to join or open a new transaction; do not assume every template always creates a new physical transaction.

## 14. Mistakes in Nested Transaction Scopes

### 14.1. An Inner Status Completed Does Not Mean Outer Completed

If inner `REQUIRED` joins outer:

```java
TransactionStatus outer = tx.getTransaction(required);
TransactionStatus inner = tx.getTransaction(required);
tx.commit(inner); // inner completed = true
// outer is still active, JDBC changes are not committed yet if outer owns T1.
tx.rollback(outer); // ultimately all of T1 rolls back.
```

This is an excerpt. Do not evaluate outcomes after `tx.commit(inner)` as if the physical transaction has already committed.

### 14.2. Inner Rollback Does Not Mean Mechanically "Immediately Roll Back Outer Status Too"

`tx.rollback(inner)` on a participating scope can mark outer T1 rollback-only. Afterward outer code must still finish **outer status** per business error rules: either roll back outer if aborting is decided, or outer attempts commit and receives UnexpectedRollbackException. What is wrong is rolling back **inner status a second time**; completing a **different** outer status once is valid.

### 14.3. `REQUIRES_NEW` Has Two Physical Transactions, Yet Still Once per Status

```java
TransactionStatus outer = tx.getTransaction(requiredDef);
TransactionStatus innerNew = tx.getTransaction(requiresNewDef);

tx.commit(innerNew);
tx.rollback(outer);
```

These two terminal operations do **not** violate the "never complete twice" rule, because they apply to **two distinct statuses**. Outer's rollback does not undo inner's committed T2. However, if inner commit throws an exception, do not roll back `innerNew` again; handle the exception per contract and decide what outer will do via the separate **outer status**.

### 14.4. A Nested Savepoint Is Not a Reusable Token

After `tx.rollback(nestedStatus)`, the savepoint scope is completed. To make another savepoint/nested attempt, call `getTransaction(nestedDefinition)` **again** inside a living outer transaction to receive a **new status**. Never call `rollback(nestedStatus)` a second time.

## 15. What Should Automated Tests Cover?

- **Commit once:** start a new transaction, INSERT, commit, assert `isCompleted=true`, row persists.
- **Double commit:** call commit a second time on the same status and assert `IllegalTransactionStateException` (with the Spring manager in use).
- **Rollback once:** INSERT, roll back, assert completed, row is gone.
- **Double rollback:** call rollback a second time and assert exception.
- **Commit→rollback / rollback→commit:** must be rejected; must not alter the already established committed state.
- **setRollbackOnly:** right when marked, `isRollbackOnly=true` and `isCompleted=false`; after one completion, row is gone.
- **Business failure:** exception before commit triggers only one rollback; no commit after catch.
- **Commit failure:** test with an appropriate manager/fake resource to confirm no rollback call occurs after the commit attempt; do **not** force a real commit network failure by breaking a production DB.
- **Participating statuses:** inner `REQUIRED` rollback marks outer rollback-only, inner is completed, outer stays active until its own completion.
- **Nested savepoint:** if supported by the manager, roll back nested and then commit outer for the remaining work.
- **Template ownership:** callback calls setRollbackOnly or throws; template cleans up automatically, callback code never calls manager terminal APIs.
- **Context:** ensure tests are not inadvertently wrapped in Spring TestContext `@Transactional`, altering the behavior under measurement.

### 15.1. Why Looking Only at Exceptions in a Test Is Not Enough

An `IllegalTransactionStateException` on the second call proves the API blocks double completion, yet does not prove the first transaction actually committed or rolled back as intended. You must have **database assertions** after the terminal operation to observe whether data persists or disappears.

### 15.2. Especially for Indeterminate Commit Outcomes

Production-grade tests should include operation IDs/idempotency keys, transaction manager/DB logs, state checks via a new connection, and reconciliation workflows. If commit loses connectivity after the DB already committed, non-idempotent retries can create duplicate business operations. The goal is **never re-completing an old status and never repeating uncontrolled business side effects**.

## 16. Reference Matrix: Should You Call the Manager Again?

| What did you just do? | `isCompleted()` afterward? | May you call `commit/rollback` again on the **same status**? |
| --- | --- | --- |
| Only `getTransaction` | Usually false | Yes, **one** valid completion in the future |
| Called `status.setRollbackOnly()` | Still false | Yes, choose **one** completion; manager handles rollback-only |
| `manager.commit(status)` succeeded | True | **No** |
| `manager.rollback(status)` succeeded | True | **No** |
| `manager.commit(status)` threw an exception | Completed/cleaned up per contract | **No**, even if wanting a "compensating rollback" |
| `manager.rollback(status)` threw a system error | May be in error/cleanup state per manager | **Do not automatically call rollback again**; investigate manager/resource, avoid double completion |
| Inner `REQUIRED` commit/rollback on inner status | Inner completed; outer status independent | Do not repeat on **inner**, but must complete **outer status** separately |
| `TransactionTemplate` callback returns/throws | Template completes callback status | **No** — template is the owner |

## 17. Code Review Checklist

- [ ] Each `getTransaction` returns a status managed within a clear scope.
- [ ] Status is never stored in a singleton or shared across requests/threads.
- [ ] `commit(status)` is called **at most once** per status.
- [ ] `rollback(status)` is called **at most once** per status.
- [ ] No code path can both commit and roll back the **same status**.
- [ ] `commit` lies **outside** the catch block handling only business-work errors.
- [ ] There is no `catch(commitFailure) -> rollback(sameStatus)`.
- [ ] There is no `finally` blindly committing/rolling back regardless of whether a terminal operation already occurred.
- [ ] `setRollbackOnly` is understood as **marking**, not already completed.
- [ ] `isCompleted()` is never used as a substitute for business/DB commit outcome.
- [ ] Participating `REQUIRED`, `NESTED`, and `REQUIRES_NEW` have clearly distinguished statuses/physical scopes.
- [ ] Inner completed is never mistaken for outer physical transaction committed.
- [ ] When a callback belongs to `TransactionTemplate`, the template owns the terminal call.
- [ ] When a method belongs to a `@Transactional` interceptor, application code does not manually complete the interceptor's status.
- [ ] Commit failures/rollback failures are logged and classified without masking the original exception.
- [ ] Retrying business work uses a **new transaction**, with idempotency/correlation IDs and retry limits.
- [ ] Tests cover both duplicate terminal operations and database state after valid completion.

## 18. Self-Check Questions

**Question 1.** After `tx.commit(status)` succeeds, does calling `tx.rollback(status)` undo the data?

**Answer:** No. The status is already completed; an additional rollback is rejected. Offsetting an already committed transaction requires a **compensating business action in a new transaction**.

**Question 2.** If `commit(status)` throws `UnexpectedRollbackException`, should you call `rollback(status)` in the catch block?

**Answer:** **No.** Commit already traversed the completion path and the transaction was cleaned up; rolling back the same status afterward is double completion.

**Question 3.** Does `status.setRollbackOnly()` make `isCompleted()` immediately become true?

**Answer:** No. It only marks rollback-only; the template/interceptor/manager must still execute completion for the scope.

**Question 4.** An inner `REQUIRED` status has been rolled back, while the outer status is not yet completed. Is it valid for outer to subsequently roll back the outer status?

**Answer:** Yes. Those are **two distinct statuses**. What is wrong is rolling back **inner status twice**.

**Question 5.** Should a `TransactionTemplate.executeWithoutResult(status -> ...)` callback call `manager.commit(status)` itself?

**Answer:** No. The template owns the transaction lifecycle. The callback only performs business logic, returns/throws, or calls `setRollbackOnly()`.

**Question 6.** Why shouldn't you put `tx.commit(status)` inside `try` and `catch(Exception e){tx.rollback(status);}`?

**Answer:** If commit throws an exception, the catch block will roll back **the same completed status**, usually raising `IllegalTransactionStateException` and hiding the original commit error. Restrict the catch to business work and call commit outside.

**Question 7.** Does `status.isCompleted() == true` prove the transaction committed successfully?

**Answer:** No. A status can be completed by rollback, rollback-only, unexpected rollback, or a commit path that threw an error. You must verify the confirmed outcome and database state.

**Question 8.** Need to retry after a transaction failure? Should you reuse the status?

**Answer:** No. Start a **new transaction** via `getTransaction(newDefinition)` or a new `TransactionTemplate.execute` call; re-read state, revalidate invariants, and use idempotency when external side effects exist.

## Official Spring Documentation

1. [Spring Framework 6.2 — PlatformTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/PlatformTransactionManager.html): `getTransaction`, `commit`, `rollback`, `IllegalTransactionStateException` on completed status; contract **never to roll back after a commit failure**.
2. [Spring Framework 6.2 — TransactionStatus Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/TransactionStatus.html): status, savepoints, rollback-only, completion.
3. [Spring Framework 6.2 — TransactionExecution Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/TransactionExecution.html): `isCompleted`, `isNewTransaction`, `isRollbackOnly`.
4. [Spring Framework 6.2 — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html): `try business / catch rollback / commit outside` pattern and `TransactionTemplate`.
5. [Spring Framework 6.2 — AbstractPlatformTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html): rules for handling rollback-only, participating transactions, and completion lifecycle.
6. [Spring Framework 6.2 — Transaction Propagation](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-propagation.html): `REQUIRED`, `REQUIRES_NEW`, `NESTED`, physical vs. logical scopes.
7. [Spring Framework 6.2 — JdbcTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/support/JdbcTransactionManager.html): manager used in the hands-on project.

**Final takeaway:** **Each `TransactionStatus` has only one terminal operation — `commit` or `rollback` — and never a second operation on that same status, even when `commit` fails.** `setRollbackOnly` is not completion; inner and outer can have **different statuses** even within the same physical transaction; `TransactionTemplate` is a strong choice to avoid manually managing complex completion branches.
