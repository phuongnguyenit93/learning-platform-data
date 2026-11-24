# TransactionStatus, Rollback-Only, and Status Information in Spring

In Spring Framework, `TransactionStatus` is the object describing **the status of a transaction scope currently being coordinated by Spring**. When a service wants to inspect the current transaction, proactively request rollback, or when `TransactionTemplate` passes status into a callback, this is the core API. To use it properly, you must distinguish **logical transaction scope** from **physical/resource transaction** and understand that a status flag does not automatically turn into a `commit()`/`rollback()` action at that exact line of code.

This lesson belongs to the **Spring Model** group in **Spring Framework – transaction-management**. It focuses on `TransactionStatus`, the meaning of `rollback-only`, transaction completion timing, and how to read status information in imperative transactions. The reactive counterpart is briefly contrasted at the end to avoid misusing the API.

## 1. Where Does TransactionStatus Sit in Spring's Transaction Model?

For imperative transactions (typically JDBC/JPA), Spring divides responsibilities as follows:

- **`TransactionDefinition`** describes the request *before starting/joining*: propagation, isolation, timeout, read-only, transaction name.
- **`PlatformTransactionManager`** obtains or creates a transaction via `getTransaction(definition)` and coordinates completion via `commit(status)` or `rollback(status)`.
- **`TransactionStatus`** is the handle returned by the manager for **a specific scope**, indicating whether the scope is new or participating, has a savepoint, is marked rollback-only, or is completed; it also allows marking rollback-only.
- **`TransactionInterceptor`** of AOP applies `@Transactional`: obtains status, invokes the business method, and lets the manager handle completion.
- **`TransactionTemplate`** uses the same abstraction but passes `TransactionStatus` directly into the callback; the template handles lifecycle and exceptions itself.
- **`TransactionSynchronizationManager`** provides information about the transaction and resource synchronization **bound to the current thread** (for imperative transactions).

Programmatic flow using `TransactionTemplate`:

```text
Caller
  |
  v
TransactionTemplate.execute(status -> ...)
  |-- PlatformTransactionManager.getTransaction(definition)
  |       \-- create/join transaction; return TransactionStatus
  |
  |-- run callback, allowing reading status or setRollbackOnly()
  |
  |-- callback returns / throws exception
  |       \-- template asks manager to commit / rollback
  |
  \-- resource cleanup, return result or rethrow exception
```

Declarative flow using AOP:

```text
Caller --> Spring proxy --> TransactionInterceptor
                                  |
                                  +--> TransactionManager.getTransaction(...)
                                  +--> invoke @Transactional service method
                                  +--> commit/rollback based on outcome and status flags
```

**`TransactionStatus` is neither a `Connection`, an `EntityManager`, nor a transaction history record in the database.** It describes a scope controlled by the manager. Whether SQL executes on the same connection depends on how the data-access API participates in the transaction; whether writes are actually committed or rolled back depends on the corresponding resource.

## 2. The TransactionStatus API: Reading Each Signal Correctly

In Spring Framework 6.1+, `TransactionStatus` extends `TransactionExecution` and `SavepointManager`, and provides `hasSavepoint()` and `flush()`. These are the methods to understand:

| Method | What question does it answer? | Proper interpretation |
| --- | --- | --- |
| `hasTransaction()` | Does this scope have an actual transaction? | Includes a new scope **or** a scope joining an existing transaction; available since Spring 6.1. |
| `isNewTransaction()` | Does the manager treat this scope as a new transaction? | `false` usually means joining an outer scope, though it could also mean no actual transaction exists; do not use alone to conclude. |
| `isNested()` | Is the scope running nested inside another scope? | Additional signal in Spring 6.1+; inspect the manager and propagation in use. |
| `hasSavepoint()` | Does the scope carry an internal savepoint? | Useful when `NESTED` is implemented with savepoints; not every transaction has a savepoint. |
| `isReadOnly()` | Is the scope declared read-only? | Reflects transaction characteristics; **does not** prove the DB forbids all write statements. |
| `getTransactionName()` | What name is declared for the scope? | Can be empty; for declarative transactions it is usually the fully qualified class and method name; not a DB transaction ID. |
| `isRollbackOnly()` | Has the scope/resource been marked rollback-only? | May be set by code calling `setRollbackOnly()` or by infrastructure. `true` does not mean the transaction has already finished rolling back. |
| `setRollbackOnly()` | Proactively request that the scope not commit successfully? | Sets a flag; **does not** immediately halt the method, undo changes, or call `rollback()` on that line. |
| `isCompleted()` | Has this scope finished? | Only `true` after the manager has finished processing the scope; does not tell whether it ended by commit or rollback. |
| `flush()` | Request flushing the session to the data store? | Only a hint, may be a no-op; **flush is not commit**. |
| `createSavepoint()`, `rollbackToSavepoint(...)`, `releaseSavepoint(...)` | Manual savepoint management? | Methods from `SavepointManager`; use only when supported by the transaction manager/resource. |

### Read Flags as a Group, Not in Isolation

Suppose method A starts `@Transactional(REQUIRED)` when no transaction existed, then calls bean B which also uses `REQUIRED`:

```text
A @Transactional(REQUIRED)         B @Transactional(REQUIRED)
  hasTransaction() = true           hasTransaction() = true
  isNewTransaction() = true         isNewTransaction() = false
                 \                 /
                    one physical DB transaction
```

Both A and B can hold **two `TransactionStatus` objects belonging to two logical scopes**, even though they share one physical transaction. Therefore `isNewTransaction() == false` in B **does not** mean B is outside a transaction.

Conversely, with `PROPAGATION_SUPPORTS` when no transaction is active, a logical scope can execute **without a physical transaction**. In that case `isNewTransaction()` is also `false`; on supported versions, `hasTransaction()` distinguishes this scenario.

Do not infer connection IDs, DB transaction counts, or isolation levels from a single boolean status.

## 3. Lifecycle: Active, Rollback-Only, and Completed

Imagine a `TransactionTemplate` scope creating a new transaction:

```text
T0  getTransaction()       -> new status, completed=false
T1  execute UPDATE         -> changes not necessarily committed yet
T2  status.setRollbackOnly()-> rollbackOnly=true, completed=false
T3  callback returns       -> template ends scope
T4  manager runs rollback  -> changes are rolled back
T5  cleanup                -> completed=true, resources released
```

At T2, the next line of code **keeps running** if there is no exception or other control-flow statement. Data is not immediately rolled back just because you called the setter. Common misunderstandings:

- `isRollbackOnly() == true` **is a decision/constraint on the outcome**, not proof that rollback has finished.
- `isCompleted() == false` while inside the callback/method is normal; it does not tell whether the final outcome will be commit or rollback.
- `isCompleted() == true` after the scope finishes only means the scope **is done**; it provides no commit/rollback outcome. Do not use it in place of an audit log or post-commit data read.
- After a scope completes, do not reuse the status to start a new transaction or call `commit()` again. Each `getTransaction()` or `TransactionTemplate.execute()` creates/selects a status for that run.

An easy way to categorize them:

```text
Transaction definition = what am I requesting?
Transaction status     = what is Spring doing with this scope?
Transaction outcome    = did the transaction actually commit or roll back?
```

Status provides useful signals for reasoning about execution, not a full history-query API for outcomes.

## 4. Rollback-Only: A Flag with Strong Consequences, Not an Immediate Rollback Command

`status.setRollbackOnly()` is the way to tell infrastructure: *the work managed by this scope cannot finish with a normal successful commit*. When a new transaction is owned by `TransactionTemplate`/interceptor, the manager detects the flag at completion and performs a rollback.

Crucial point: **Spring handles rollback-only depending on scope and propagation**. Not every scope sharing a physical transaction can commit independently.

### 4.1. New Transaction: Marking Rollback and Returning Normally

```java
transactionTemplate.execute(status -> {
    jdbcTemplate.update("UPDATE wallet SET balance = balance - 10 WHERE id = 1");
    status.setRollbackOnly();
    return "callback completed";
});
```

This is an **illustrative snippet** requiring `transactionTemplate`, `jdbcTemplate`, and a `wallet` table. If the template started a new local JDBC transaction, the `UPDATE` will be rolled back when the template finishes even though the callback returns normally. The returned string is **not** proof that data committed. Normally, calling `setRollbackOnly()` directly on a new scope's status is an intentional rollback decision and does not automatically raise `UnexpectedRollbackException`.

From an API design standpoint, express business outcomes clearly: if an operation was not persisted due to a condition, return a result type carrying failure state or throw an appropriate exception. Do not let callers mistake "method returned normally" for "written to DB".

### 4.2. Inner REQUIRED Scope Marking Rollback-Only

Consider two **different Spring beans**; the caller enters `OuterService` via proxy, and `OuterService` calls `InnerService` via proxy:

```java
@Service
class InnerService {
    @Transactional(propagation = Propagation.REQUIRED)
    public void markFailure() {
        TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
    }
}

@Service
class OuterService {
    private final InnerService inner;

    OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void process() {
        // DB operations
        inner.markFailure();
        // method can still continue running
    }
}
```

This is an **illustrative snippet, not standalone-compilable**; it needs Spring imports, bean wiring, and application-specific DB operations. With a manager using standard `REQUIRED` semantics:

1. `process()` opens a physical transaction and an outer logical scope.
2. `markFailure()` creates a logical scope **joining** the same physical transaction.
3. `setRollbackOnly()` in the inner scope prevents the shared transaction from committing normally.
4. The inner scope may return without immediately throwing an exception; at the outer boundary, when the caller expects a commit but the actual outcome must be rollback, Spring can throw **`UnexpectedRollbackException`**.

This is not an "accidental" rollback: it protects the caller from mistakenly believing a commit succeeded. Even if an exception is caught in the outer transaction and the method returns, there is no simple way to "clear" the rollback-only flag to force the shared physical transaction to commit.

**Distinguish the cause:** calling `setRollbackOnly()` in the outer scope that owns the transaction and knowingly decides to roll back differs from the outer scope being unexpectedly marked rollback-only by an inner scope. `UnexpectedRollbackException` typically occurs in the second case; exact details depend on the transaction manager and configuration.

### 4.3. Comparing REQUIRED, REQUIRES_NEW, and NESTED

| Inner scope propagation | Relationship to outer transaction | How does inner rollback-only usually affect things? |
| --- | --- | --- |
| `REQUIRED` | Same physical transaction | Can cause the entire shared transaction to roll back; outer commit may throw `UnexpectedRollbackException`. |
| `REQUIRES_NEW` | **Independent** physical transaction, outer scope suspended | Rolling back the inner transaction does not automatically roll back the outer transaction; exception and outcome handling remain up to code. |
| `NESTED` | Usually uses a savepoint in the **same** physical transaction if supported | Can roll back to the savepoint and let outer continue; not equivalent to `REQUIRES_NEW`. |

`REQUIRES_NEW` may need to acquire an additional connection while outer's connection is still held; account for pool capacity. `NESTED` depends on savepoint support in the transaction manager and database, commonly used with JDBC. Do not assume every `JpaTransactionManager` or resource supports nested/savepoints identically.

`status.hasSavepoint()` reflects whether the scope *was created with an internal savepoint*. That differs from arbitrary code calling `status.createSavepoint()` on the same status. Verify actual support before using manual savepoint APIs.

### 4.4. Local and Global Flags in Spring

In common Spring implementations, there is a distinction between:

- **Local rollback-only:** a logical scope marks rollback-only on its own `TransactionStatus`.
- **Global rollback-only:** the participating transaction/resource is marked unable to commit by the manager or underlying resource.

`AbstractTransactionStatus.isRollbackOnly()` can check both states. Hence a scope may see rollback-only even if that scope's own code never called the setter. This is one reason `isRollbackOnly()` must be interpreted within **manager and propagation context**, not treated as a service's private boolean variable.

Application code is discouraged from trying to manipulate implementation-internal flags directly; use the `setRollbackOnly()` API and let Spring manage scope completion.

## 5. How to Obtain TransactionStatus?

### 5.1. TransactionTemplate: The Most Readable Programmatic Approach

```java
TransactionTemplate template = new TransactionTemplate(transactionManager);

String result = template.execute(status -> {
    // Runs inside the transaction scope coordinated by template
    if (status.isRollbackOnly()) {
        return "rollback has been requested";
    }
    // ... business processing ...
    return "completed";
});
```

This is an **illustrative snippet**; `transactionManager` must be an appropriate bean, and real DB operations must use a transaction-aware data-access API. The callback receives `TransactionStatus` directly, with no AOP lookup needed. When the callback returns, the template handles commit/rollback and resource cleanup.

If you need to cancel the transaction without throwing an exception:

```java
template.executeWithoutResult(status -> {
    if (businessRuleFailed()) {
        status.setRollbackOnly();
        return;
    }
    writeBusinessData();
});
```

This is an **illustrative snippet**; `businessRuleFailed()` and `writeBusinessData()` are hypothetical methods. `return;` exits the callback, while the template still must complete the scope. `setRollbackOnly()` is the signal requesting rollback. The callback returning void does not prove the transaction committed.

When using `TransactionTemplate`, do not call `transactionManager.commit(status)`/`rollback(status)` yourself inside the callback: the template already owns the lifecycle.

### 5.2. Declarative @Transactional: Accessing Status of the Current AOP Invocation

Inside a method managed by `TransactionInterceptor`, Spring provides:

```java
@Transactional
public void updateAccount(long id) {
    // ... update DB ...
    TransactionStatus status =
            TransactionAspectSupport.currentTransactionStatus();

    if (mustRejectOperation(id)) {
        status.setRollbackOnly();
    }
}
```

This is an **illustrative snippet**; `mustRejectOperation` must be defined. `TransactionAspectSupport.currentTransactionStatus()` retrieves the status of the **current AOP transaction boundary**, even when that boundary is joining an outer transaction.

Do not use this API as a safe status probe in arbitrary code. Without an active AOP invocation context, it throws `NoTransactionException`. A self-invocation like `this.innerMethod()` does not create a new AOP boundary for the inner method's annotation; `currentTransactionStatus()` may still return the status **of the outer boundary** if inside an outer invocation, rather than turning the inner method into an independent scope.

In typical design, prefer `@Transactional` and exception/`rollbackFor` rules. Manual rollback marking is useful when **you need to cancel proactively while still handling or transforming the result**, though it couples business code directly to Spring's API.

### 5.3. PlatformTransactionManager: Proactively Owning the Entire Lifecycle

```java
DefaultTransactionDefinition definition = new DefaultTransactionDefinition();
TransactionStatus status = manager.getTransaction(definition);

try {
    performBusinessOperations();
    manager.commit(status);
} catch (RuntimeException ex) {
    if (!status.isCompleted()) {
        manager.rollback(status);
    }
    throw ex;
}
```

This is an **illustrative snippet** requiring `manager`, `performBusinessOperations()`, and imports. `getTransaction()` creates or joins according to `definition`; code must ensure the scope completes exactly once. Checking `isCompleted()` avoids trying to roll back an already-completed scope, e.g., after an error raised inside `commit()` itself. This direct coding style is error-prone and harder to maintain than `TransactionTemplate`; use it only when genuinely needing infrastructure-level sequence control.

**Do not mix ownership:** If AOP/template already manages the transaction, do not call `commit()` or `rollback()` on a status obtained via its API. Conversely, if you use the manager directly, you must handle all exception paths and cleanup yourself.

## 6. How Does "Status Information" from TransactionStatus Differ from TransactionSynchronizationManager?

For **imperative transactions**, `TransactionSynchronizationManager` stores synchronization and resource information related to execution **per thread**. Typical methods:

```java
boolean actual =
        TransactionSynchronizationManager.isActualTransactionActive();
boolean synchronization =
        TransactionSynchronizationManager.isSynchronizationActive();
String name =
        TransactionSynchronizationManager.getCurrentTransactionName();
boolean readOnly =
        TransactionSynchronizationManager.isCurrentTransactionReadOnly();
Integer isolation =
        TransactionSynchronizationManager.getCurrentTransactionIsolationLevel();
```

This is an **illustrative snippet**; it requires importing `org.springframework.transaction.support.TransactionSynchronizationManager` and an appropriate Spring context.

| Question | Appropriate API |
| --- | --- |
| Did this callback/template or AOP scope mark rollback-only? | `TransactionStatus.isRollbackOnly()` |
| Does the manager treat the scope as new or joined? | `TransactionStatus.isNewTransaction()`, see also `hasTransaction()` |
| Has the scope completed? | `TransactionStatus.isCompleted()` |
| Does the current thread have an active Spring physical/resource transaction? | `TransactionSynchronizationManager.isActualTransactionActive()` |
| Is Spring transaction synchronization active? | `TransactionSynchronizationManager.isSynchronizationActive()` |
| Current name/read-only/isolation bound to the thread? | The corresponding getters on `TransactionSynchronizationManager` |

A crucial difference: **`isSynchronizationActive()` can be `true` while `isActualTransactionActive()` is `false`**, for example a scope that activates transaction synchronization without a physical transaction. Therefore, active synchronization cannot be used to conclude that DB operations will definitely be rolled back.

`TransactionAspectSupport.currentTransactionStatus()` reflects the **local AOP boundary**. `TransactionSynchronizationManager` describes execution-context metadata bound to the thread, which may reflect an outer resource transaction that the local scope joined. These APIs serve different purposes; do not substitute one mechanically for the other.

For reactive transactions, Spring uses **Reactor Context**, not the thread-bound imperative `TransactionSynchronizationManager`. With R2DBC, the corresponding APIs are typically `ReactiveTransactionManager`, `TransactionalOperator`, `ReactiveTransaction`, and the reactive transaction synchronization API. Thread switching does not automatically carry imperative transactions to a new thread; nor can you infer the state of a reactive chain from `ThreadLocal`.

## 7. How Do `isRollbackOnly`, Exceptions, and Flush Interact?

### 7.1. An Exception Does Not Mean a Flag Was Already Set Immediately

With Spring's default `@Transactional`, unchecked `RuntimeException` and `Error` normally trigger rollback when **the exception escapes the transactional invocation**. Checked exceptions do not trigger rollback by default unless an appropriate rule like `rollbackFor` is present.

```java
@Transactional(rollbackFor = IOException.class)
public void importFile() throws IOException {
    // IOException escaping the method also triggers transaction rollback
}
```

This is an **illustrative snippet**; it requires importing `java.io.IOException`. If code catches and swallows the exception and returns normally, the interceptor may take the commit branch if no rollback-only flag is set. You cannot look solely at a stack trace or a `catch` block to conclude the DB rolled back.

`setRollbackOnly()` is an **explicit choice** when you want rollback even though no exception escapes. It does not replace informing the caller of the business outcome. Whether `status.isRollbackOnly()` reflects true before or after an exception is handled depends on what the transaction manager/resource marked; do not rely on the flag flipping at a fixed instant.

### 7.2. Flush Is Not Commit

`status.flush()` may ask a JPA/Hibernate session to push pending SQL to the database, or be a no-op depending on the manager. Even after SQL has been flushed:

1. the transaction may still not be committed;
2. `status.setRollbackOnly()` can still cause changes to be rolled back;
3. data visibility from another connection depends on isolation and the DB;
4. an error during flush can cause the transaction to be marked rollback-only.

Do not use `flush()` to "test commit" or make the rollback-only flag disappear. To verify actual commit, observe **after the boundary ends** using an appropriate resource/transaction.

### 7.3. `isCompleted()` Does Not Mean "Success"

A status that completed by rolling back also returns `isCompleted() == true`. Inside a callback/template, before the template finishes, `isCompleted()` is typically `false` even if business logic has already run all statements. To know whether operations took effect, you need clear result/exception policies and post-transaction verification; `isCompleted()` alone is not enough.

## 8. Standalone Java 17 Example: Three Ways Rollback-Only Appears

This example uses **Java 17**, **Spring Boot 3.3.5**, **Spring JDBC**, and **in-memory H2**. It demonstrates:

1. `TransactionTemplate` creating a new transaction, callback receiving `TransactionStatus`, calling `setRollbackOnly()`, and returning normally.
2. A `@Transactional` bean obtaining `TransactionStatus` via AOP and explicitly marking rollback-only.
3. An inner `REQUIRED` bean joining the outer transaction and marking rollback-only, causing the outer commit to throw `UnexpectedRollbackException`.

Prerequisites: **JDK 17+**, **Maven 3.9+**, able to download Maven dependencies. The service classes are declared `public static` inside the application class so the example fits in a single Java file; they remain Spring-managed beans thanks to `@Service`.

Structure:

```text
tx-status-demo/
├── pom.xml
└── src/main/java/demo/TxStatusDemoApplication.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>tx-status-demo</artifactId>
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

File `src/main/java/demo/TxStatusDemoApplication.java`:

```java
package demo;

import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.UnexpectedRollbackException;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootApplication
public class TxStatusDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(TxStatusDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner run(
            JdbcTemplate jdbc,
            PlatformTransactionManager manager,
            FlaggingService flagging,
            OuterService outer) {

        return args -> {
            jdbc.execute("""
                    CREATE TABLE wallet (
                        id INT PRIMARY KEY,
                        balance INT NOT NULL
                    )
                    """);
            jdbc.update("INSERT INTO wallet (id, balance) VALUES (1, 100)");

            System.out.println("START=" + balance(jdbc));

            // Case 1: callback owns the new status.
            TransactionTemplate template = new TransactionTemplate(manager);
            AtomicReference<TransactionStatus> saved = new AtomicReference<>();

            template.execute(status -> {
                saved.set(status);
                jdbc.update("UPDATE wallet SET balance = balance - 10 WHERE id = 1");

                System.out.println("TEMPLATE before: new=" + status.isNewTransaction()
                        + ", rollback=" + status.isRollbackOnly()
                        + ", completed=" + status.isCompleted());

                status.setRollbackOnly();
                System.out.println("TEMPLATE after mark: rollback="
                        + status.isRollbackOnly());
                return null;
            });

            System.out.println("TEMPLATE after scope: completed="
                    + saved.get().isCompleted()
                    + ", balance=" + balance(jdbc));

            // Case 2: status from AOP invocation.
            flagging.debitAndMarkRollback();
            System.out.println("AOP after scope: balance=" + balance(jdbc));

            // Case 3: inner REQUIRED scope joins outer transaction.
            try {
                outer.updateThenCallInner();
            } catch (UnexpectedRollbackException expected) {
                System.out.println("OUTER: UnexpectedRollbackException");
            }

            System.out.println("END=" + balance(jdbc));
        };
    }

    private static int balance(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
                "SELECT balance FROM wallet WHERE id = 1",
                Integer.class);
    }

    @Service
    public static class FlaggingService {
        private final JdbcTemplate jdbc;

        public FlaggingService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void debitAndMarkRollback() {
            jdbc.update("UPDATE wallet SET balance = balance - 10 WHERE id = 1");
            TransactionStatus status =
                    TransactionAspectSupport.currentTransactionStatus();

            System.out.println("AOP inside: active=" + status.hasTransaction()
                    + ", new=" + status.isNewTransaction());

            status.setRollbackOnly();
        }
    }

    @Service
    public static class InnerService {
        @Transactional
        public void markRollback() {
            TransactionStatus status =
                    TransactionAspectSupport.currentTransactionStatus();

            System.out.println("INNER: new=" + status.isNewTransaction());
            status.setRollbackOnly();
        }
    }

    @Service
    public static class OuterService {
        private final JdbcTemplate jdbc;
        private final InnerService inner;

        public OuterService(JdbcTemplate jdbc, InnerService inner) {
            this.jdbc = jdbc;
            this.inner = inner;
        }

        @Transactional
        public void updateThenCallInner() {
            jdbc.update("UPDATE wallet SET balance = balance - 20 WHERE id = 1");
            inner.markRollback();
            // Outer method returns normally, but the transaction is already marked.
        }
    }
}
```

Run in the `tx-status-demo` directory:

```bash
mvn -q spring-boot:run
```

The lines **printed by the program itself** (excluding Maven/Spring Boot startup logs) are:

```text
START=100
TEMPLATE before: new=true, rollback=false, completed=false
TEMPLATE after mark: rollback=true
TEMPLATE after scope: completed=true, balance=100
AOP inside: active=true, new=true
AOP after scope: balance=100
INNER: new=false
OUTER: UnexpectedRollbackException
END=100
```

Step-by-step analysis:

- **TEMPLATE:** `TransactionTemplate` creates a new transaction, so `new=true`; before marking, `rollback=false`, `completed=false`. After the setter, `rollback=true` immediately inside the callback, yet the callback still returns normally. The template completes the scope by rolling back; `isCompleted()` on the saved status is `true` and the balance remains 100.
- **AOP:** `FlaggingService` is a Spring bean invoked from the runner through a proxy, so `currentTransactionStatus()` obtains the status of the active transactional invocation. Calling the setter prevents the -10 debit from committing; the balance outside the scope remains 100.
- **INNER/OUTER:** `OuterService` opened a physical transaction, `InnerService` is called through a separate proxy and joins it (`new=false`). Inner marks rollback-only. Outer returns normally, but the commit attempt at the outer boundary cannot succeed; Spring throws `UnexpectedRollbackException`. Ultimately the balance remains 100.

The demo intentionally uses **one** H2 datasource and manager, with no thread switching and no `REQUIRES_NEW`, to observe each state deterministically. Real applications require clear business error models, transaction bounds, and proper concurrency controls; this example only illustrates status and lifecycle.

## 9. Confusing Situations and How to Handle Them

### Error 1 — Reading `isNewTransaction() == false` and Concluding No Transaction Exists

**Wrong because:** an inner `REQUIRED` joining an outer transaction also returns `false`. In Spring 6.1+, also check `hasTransaction()`. When diagnosing imperative runtime behavior, you can cross-check `TransactionSynchronizationManager.isActualTransactionActive()`.

### Error 2 — Assuming Calling `setRollbackOnly()` Immediately Undoes Data

**Wrong because:** the setter only requests a rollback outcome. Subsequent code may still run, and resources and DB locks can remain held until the boundary actually ends. If a business branch should not proceed, control execution explicitly (`return`, exception, result type).

### Error 3 — Catching an Exception Inside `@Transactional` and Assuming Spring Rolls Back Automatically

**Wrong because:** the interceptor relies on exceptions escaping the method and rollback rules; a swallowed exception can cause the method to return normally. Change the policy with `rollbackFor`, let the exception propagate out, or proactively mark rollback-only when truly required.

### Error 4 — Inner REQUIRED Cancels, Outer Tries to Commit and Hits `UnexpectedRollbackException`

This is usually the expected consequence of multiple logical scopes sharing one physical transaction. Clearly define which scope decides the business outcome; do not catch and try to "reset" rollback-only. If an independent transaction is mandatory, consider `REQUIRES_NEW` along with resource and consistency impacts.

### Error 5 — Calling `currentTransactionStatus()` in Arbitrary Methods

This API depends on an **AOP transaction invocation context**. A helper called outside a matching invocation can throw `NoTransactionException`; self-invoked methods via `this.method()` do not create an extra proxy boundary as many expect. For programmatic flows, `TransactionTemplate` callbacks already receive status directly without looking it up via AOP.

### Error 6 — Confusing `flush()` or `isCompleted()` with Commit

`flush()` may only push operations to the DB before commit or do nothing. `isCompleted()` carries no success/failure outcome. To prove commit, check postconditions after the boundary using appropriate testing mechanisms.

### Error 7 — Passing `TransactionStatus` to Another Thread or Storing It in a Singleton

Status belongs to one invocation/scope, not shared service-wide state. In imperative Spring transactions, resources are typically bound to a thread; `@Async`, `CompletableFuture`, or `new Thread` do not automatically inherit active DB transactions. Do not cache status in a singleton field for another request to read.

### Error 8 — Assuming One Transaction Manager Covers Every Kind of Resource

`isRollbackOnly() == true` only reflects the scope coordinated by that manager. It **does not** make HTTP requests, emails, file writes, or an independent datasource automatically roll back alongside the database transaction. When multiple resources must coordinate, specific transaction or compensation strategies are needed.

## 10. Testing and Practical Observation

To verify instead of merely reading logs:

1. Set up a test DB with committed initial data, e.g., `wallet.balance=100`.
2. Call the public transactional service method **through the Spring proxy**.
3. Inside the method, update data and call `setRollbackOnly()` or throw an unchecked exception.
4. Let the scope finish. Query data from a caller outside the scope; compare the balance with the initial value.
5. With two `REQUIRED` beans, verify inner has `isNewTransaction()==false` and outer can receive `UnexpectedRollbackException`.
6. When testing with Spring Test's `@Transactional` placed on a test method, note that the test framework normally rolls back automatically at the end of the test. Do not take the **test method's** rollback as proof that the service itself rolls back properly at runtime.

You can enable selective logging in development environments:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
```

Logs help observe begin/join/rollback/commit and binding. Nevertheless, **transaction logs do not replace verifying data after the transaction**. Do not enable overly verbose logging in production without reason due to overhead and data potentially appearing in logs.

A small and useful test matrix:

| Case | End-of-scope expectation |
| --- | --- |
| `TransactionTemplate`: callback returns normally, no flag set | Commits if no other errors/rollback-only state occurred. |
| `TransactionTemplate`: callback calls `setRollbackOnly()` | Rolls back changes in the same transaction. |
| `@Transactional`: unchecked exception escapes method | Rolls back per default rules. |
| `@Transactional`: exception caught and normal return | May commit if the transaction was not already marked rollback-only. |
| Inner `REQUIRED` marks rollback-only, outer still tries to commit | Entire physical transaction rolls back; outer may receive `UnexpectedRollbackException`. |
| Inner `REQUIRES_NEW` rolls back, outer does not request rollback | Outer transaction can commit independently, depending on caller logic/exceptions. |

## 11. Self-Check Knowledge Questions

**Question 1.** A method with `@Transactional(REQUIRED)` is joining the caller's transaction. `status.isNewTransaction()` is `false`. Does that mean there is definitely no DB transaction?

**Explanation:** no. This is the normal case when joining an existing physical transaction; `hasTransaction()` helps identify whether an actual transaction exists in Spring 6.1+.

**Question 2.** Inside a callback, `status.setRollbackOnly()` then `return 42`. Does the callback finish executing, and can the caller receive `42` even though the update rolls back?

**Explanation:** yes. The setter does not throw an exception or halt the method; the template finishes the scope by rolling back, while the callback's return value can still be returned. Therefore the business contract must be able to express non-commit.

**Question 3.** `status.isCompleted()` became `true`. Can you conclude the transaction committed?

**Explanation:** no. `isCompleted()` is also `true` after a rollback; it is a scope lifecycle flag.

**Question 4.** `isSynchronizationActive()` is `true` while `isActualTransactionActive()` is `false`. Is this a contradiction?

**Explanation:** no. Spring may manage synchronization without a physical transaction, such as in certain `SUPPORTS` cases. The two APIs answer two different questions.

**Question 5.** An inner `REQUIRED` sets rollback-only, and the outer method throws no exception. Is outer guaranteed to commit?

**Explanation:** no. Two logical scopes can share a physical transaction; outer's commit may encounter `UnexpectedRollbackException` when the transaction is forced to roll back.

**Question 6.** Call `status.flush()` then `status.setRollbackOnly()`. Are the flushed SQL statements guaranteed to be persisted?

**Explanation:** no. Flush and commit are two different actions; flushed but uncommitted changes can still be rolled back.

## 12. Quick Takeaways

- `TransactionDefinition` = *transaction request*.
- `TransactionStatus` = *status/control of the current transaction scope*.
- `hasTransaction()` = *is there an actual transaction?*; `isNewTransaction()` = *is this scope considered new by the manager?*
- `setRollbackOnly()` = *request not to commit successfully*; `isRollbackOnly()` = *is rollback-only already flagged?*
- `isCompleted()` = *has the scope finished?*, **not** synonymous with *committed*.
- `TransactionTemplate` or the AOP interceptor owns scope completion; business code does not commit a status managed by them.
- With `REQUIRED`, multiple logical scopes can share one physical transaction; inner marking rollback-only can cause outer commit to fail.
- `TransactionSynchronizationManager` holds **per-thread** transaction/resource info for the imperative model; reactive transactions require Reactor Context APIs.

When debugging, ask yourself in order: **Which scope's status is this? Is the scope actually participating in a transaction? Who marked rollback-only? Who owns completion? What was committed/rolled back on the real resource?**

## Official Spring Documentation

- [Transaction Management — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Transaction Management — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Transaction Management — Declarative Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [API — TransactionStatus, Spring Framework 6.2](https://www.springframework.org/spring/docs/6.2.18/javadoc-api/org/springframework/transaction/TransactionStatus.html)
- [API — TransactionExecution, Spring Framework 6.2](https://www.springframework.org/spring/docs/6.2.18/javadoc-api/org/springframework/transaction/TransactionExecution.html)
- [API — TransactionAspectSupport, Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/transaction/interceptor/TransactionAspectSupport.html)