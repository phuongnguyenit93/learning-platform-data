# getTransaction Can Create a New Transaction or Join an Existing One

## 1. The Most Important Fact: getTransaction Does Not Always Mean a New BEGIN

In Spring Framework, `PlatformTransactionManager` provides a direct programmatic API:

~~~java
TransactionStatus status =
    transactionManager.getTransaction(transactionDefinition);
~~~

`getTransaction(...)` does **not create a new physical transaction on every call by default**. The outcome depends on **`TransactionDefinition`**, especially `propagation`, and the state of any **currently existing transaction** at the time of the call:

- With `PROPAGATION_REQUIRED` and **no compatible transaction existing**, the manager **opens a new transaction**. `status.isNewTransaction()` is usually `true`.
- With `PROPAGATION_REQUIRED` and **a compatible transaction already existing**, the manager lets the inner logical scope **join the current physical transaction**. `status.isNewTransaction()` is usually `false`.
- With `PROPAGATION_REQUIRES_NEW`, the manager requests a new physical transaction; when an outer transaction already exists, the outer resource/transaction is **suspended** according to the manager's capabilities.
- With `PROPAGATION_NESTED`, if an outer transaction exists and the manager supports savepoints, the inner scope usually uses the **same physical transaction and a savepoint**; when no outer exists, it opens a new transaction.
- With `SUPPORTS`/`NOT_SUPPORTED`, `getTransaction` may even return a logical status **without a new physical transaction**.
- With `MANDATORY` or `NEVER`, a configuration incompatible with the presence/absence of an outer transaction may be rejected with `IllegalTransactionStateException`.

The accurate mental model is: **`getTransaction` resolves the propagation requirement**, rather than unconditionally executing a "BEGIN" command.

### Why Does This Lesson Matter?

If code calls `getTransaction` inside an existing transaction while assuming it created an independent transaction, calling `commit(innerStatus)` is easily misunderstood as "the data is already saved", whereas in reality an inner `REQUIRED` only **ends the logical scope** and the physical commit still belongs to the outer transaction. Conversely, `rollback(innerStatus)` on a participant can mark the **entire shared transaction rollback-only**, preventing the outer transaction from committing even after catching the error.

Instead of guessing, we will use `TransactionStatus.isNewTransaction()`, `hasSavepoint()`, `TransactionSynchronizationManager.isActualTransactionActive()`, and H2 database readback tests.

## 2. Three Parts of the Direct Transaction API

### 2.1. TransactionDefinition: The Request You Pass In

`TransactionDefinition` describes the transaction to be created or joined. It can be configured with `DefaultTransactionDefinition`:

~~~java
DefaultTransactionDefinition definition =
    new DefaultTransactionDefinition();
definition.setName("create-order");
definition.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRED
);
definition.setIsolationLevel(
    TransactionDefinition.ISOLATION_READ_COMMITTED
);
definition.setTimeout(15);
definition.setReadOnly(false);

TransactionStatus status =
    transactionManager.getTransaction(definition);
~~~

This is an **illustrative code snippet**, requiring an initialized `PlatformTransactionManager`; complete code is in section 6.

Attributes to recognize:

| Attribute | Meaning | Note when a transaction already exists |
| --- | --- | --- |
| `propagationBehavior` | Open new, join, suspend, savepoint, or require/forbid a transaction | This is the **primary factor** determining the number of physical transactions. |
| `isolationLevel` | Desired isolation level | Usually applied only when **starting a new transaction** and supported by manager/DB; inner REQUIRED does not override outer. |
| `timeout` | Transaction time limit in seconds | An inner participant does not reset the outer physical transaction's deadline. |
| `readOnly` | Hint/attribute regarding read operations | Not an authorization mechanism and does not turn an outer transaction read-only. |
| `name` | Transaction name used for diagnostics | With the programmatic API you can set an explicit name for logs/monitoring. |

If `null` is passed to `getTransaction(null)`, the manager uses the **default transaction definition**; in Spring the default propagation is typically `REQUIRED`. When the goal is learning or explicit configuration, pass a `DefaultTransactionDefinition` with a specific name and propagation.

### 2.2. TransactionStatus: The Result Returned by the Manager

`TransactionStatus` holds the state of the **transaction scope returned from that specific call**, not a "registry of all transactions":

~~~java
boolean newTransaction = status.isNewTransaction();
boolean savepoint = status.hasSavepoint();
boolean completed = status.isCompleted();
boolean rollbackOnly = status.isRollbackOnly();
~~~

This is a **snippet** used within a scope that has already called `getTransaction`.

- `isNewTransaction()`: did the manager create a new physical transaction for this scope? In the JDBC lab, standalone `REQUIRED` returns true, while participating `REQUIRED` returns false.
- `hasSavepoint()`: does the status have a nested savepoint? With `NESTED` joining a JDBC outer transaction this can be true, even though `isNewTransaction()` is false.
- `isRollbackOnly()`: is the status requesting rollback instead of commit for the current scope, or has it received a rollback-only marker where the manager exposes that state?
- `isCompleted()`: has the status **already been completed** via commit/rollback? It must not be committed or rolled back a second time.

In particular, `status.isNewTransaction() == false` does **not always mean** "participating in a physical transaction". With `SUPPORTS` and **no transaction existing**, the status is also not a new transaction, yet `TransactionSynchronizationManager.isActualTransactionActive()` may be false. You must consider both propagation and actual transaction activity.

### 2.3. PlatformTransactionManager: Start/Join and Complete

Three basic methods:

~~~java
TransactionStatus getTransaction(TransactionDefinition definition);
void commit(TransactionStatus status);
void rollback(TransactionStatus status);
~~~

`commit(status)` and `rollback(status)` act **according to the status returned by the manager**. They are not necessarily JDBC `COMMIT`/`ROLLBACK` statements on a new connection:

- `commit` for the owner of a physical transaction: performs a real commit when all conditions allow.
- `commit` for a `REQUIRED` participant: ends the logical scope, **does not prematurely commit the outer physical transaction**.
- `rollback` for the owner: rolls back its own physical transaction.
- `rollback` for a `REQUIRED` participant: in the default Spring JDBC manager this can mark the shared transaction **rollback-only** instead of rolling back independently.
- `rollback` for a nested savepoint scope: can roll back **to the savepoint**, if supported by the manager/driver.

**Do not use `status.isNewTransaction()` as a reason to skip `commit/rollback` for a participant**: when the manager returns a status, the caller must still complete the scope properly. `isNewTransaction` helps you understand the behavior, not replace the completion API.

## 3. Why Can the Same REQUIRED Have Two Outcomes?

### 3.1. No Outer Transaction Exists

~~~text
Caller
    |
    v
manager.getTransaction(REQUIRED)
    |
    +-- Sees no active transaction on the resource
    +-- Opens physical transaction T1
    +-- Returns status: newTransaction=true
    |
    +-- JDBC UPDATE A +10 inside T1
    |
    v
manager.commit(status)
    |
    +-- Actually COMMITs T1
    v
Caller reads DB: A has increased by 10
~~~

The transaction manager must manage the same resource as the JDBC operations, for example `DataSourceTransactionManager` and `JdbcTemplate` sharing the same `DataSource`. If SQL executes on an independent connection, the result will not necessarily be part of T1.

### 3.2. An Outer Transaction Already Exists

~~~text
Caller
    |
    v
manager.getTransaction(REQUIRED)    -> OUTER T1, newTransaction=true
    |
    +-- UPDATE A +10 (not committed yet)
    |
    +-- manager.getTransaction(REQUIRED)
    |           |
    |           +-- INNER joins T1
    |           +-- inner.isNewTransaction() == false
    |           +-- UPDATE B +10 (also in T1)
    |           |
    |           v
    |      manager.commit(inner)
    |           |
    |           +-- Completes logical INNER only
    |           +-- Does NOT commit physical T1 yet
    |
    +-- manager.rollback(outer)
                |
                +-- ROLLBACKs all of T1

Result: neither A nor B increased.
~~~

Someone reading logs who only sees two `getTransaction` calls **must not conclude that both T1 and T2 existed**. With `REQUIRED` and matching manager/resource, there is only **one physical transaction T1**, even though the code holds two distinct `TransactionStatus` objects.

The converse is also important: two consecutive standalone `getTransaction(REQUIRED)` calls, if the first call commits before the second call begins and there is no outer transaction, each call gets **its own physical transaction**. An error in the second transaction cannot roll back the already committed first transaction.

## 4. Propagation Matrix: What Will getTransaction Do?

| Propagation | No existing transaction | Compatible transaction exists | Key takeaway |
| --- | --- | --- | --- |
| `PROPAGATION_REQUIRED` | Opens new T1 | Joins T1 | Default, most commonly used. |
| `PROPAGATION_SUPPORTS` | May return status without physical transaction | Joins T1 | `newTransaction=false` alone does not prove joining. |
| `PROPAGATION_MANDATORY` | **Error**: requires an existing transaction | Joins T1 | Use when inner is only valid in an already-transactional workflow. |
| `PROPAGATION_REQUIRES_NEW` | Opens new T1 | Suspends T1, opens independent T2 | Inner commit can survive when outer rolls back. |
| `PROPAGATION_NOT_SUPPORTED` | Runs without physical transaction | Suspends T1, runs outside physical transaction | Do not use if atomicity with outer is required. |
| `PROPAGATION_NEVER` | Runs without physical transaction | **Error**: forbids an existing transaction | Use to assert an operation is never called inside a transaction. |
| `PROPAGATION_NESTED` | Opens new T1 | Savepoint inside T1 when supported | Not an independent commit like REQUIRES_NEW. |

This table describes Spring imperative transactions with managers supporting each propagation. `DataSourceTransactionManager` handles nested via JDBC savepoints when allowed; JPA/JTA managers may have different support or restrictions. Do not infer that the same annotation or `TransactionDefinition` produces identical results across every manager.

### Different Examples of isNewTransaction

~~~text
getTransaction(REQUIRED), no outer        -> new=true
getTransaction(REQUIRED), with outer      -> new=false
getTransaction(REQUIRES_NEW), with outer  -> new=true
getTransaction(NESTED), outer + savepoint -> new=false; hasSavepoint=true
getTransaction(NESTED), no outer          -> new=true;  hasSavepoint=false
getTransaction(SUPPORTS), no outer        -> new=false; actualActive=false
~~~

**Practical note:** `REQUIRES_NEW` may require a **separate JDBC connection** while outer still holds its own connection. If inner writes to the same row that outer is holding a lock on, there is a risk of lock wait or deadlock. The tests use two separate rows A/B to avoid turning a propagation lesson into a lock-contention lesson.

## 5. Commit, Rollback, and Commonly Misunderstood Failures

### 5.1. Committing a Participant Does Not Commit the Physical Transaction

Calling `manager.commit(innerStatus)` for an inner `REQUIRED` does not release a commit for the outer transaction. If outer subsequently calls `rollback(outerStatus)`, all updates from both inner and outer in the shared transaction are undone. This is the intended behavior of transaction scopes.

### 5.2. Rolling Back a Participant Can Prevent Outer from Committing

With `DataSourceTransactionManager` and `AbstractPlatformTransactionManager` in their default configuration, `globalRollbackOnParticipationFailure=true`. When an inner `REQUIRED` calls `manager.rollback(innerStatus)`, the manager **marks the shared transaction rollback-only**. If outer then tries to `commit(outerStatus)`, Spring usually rolls back and throws `UnexpectedRollbackException`.

~~~text
OUTER T1 starts
  +-- UPDATE A +10
  +-- INNER REQUIRED joins T1
        +-- UPDATE B +10
        +-- rollback(innerStatus)
        +-- shared T1 is marked rollback-only
  +-- OUTER attempts commit(outerStatus)
        +-- T1 ROLLBACKs
        +-- UnexpectedRollbackException
Result: both A and B remain unchanged.
~~~

An inner participant has no separate physical transaction to roll back on its own. **Do not catch `UnexpectedRollbackException` and try calling `commit` again on an already completed status**. You need to examine the root cause and business boundaries.

### 5.3. setRollbackOnly and rollback(status) Are Not Entirely Identical

`status.setRollbackOnly()` requests a rollback when the scope completes. For the owner transaction, a subsequent `commit(status)` call can lead to a rollback due to the local rollback-only marker rather than committing. For a participant, the marker can propagate to the shared transaction. Exact differences between local rollback-only markers and global rollback-only caused by inner `rollback(status)` depend on the manager and scope.

In the lab:

- We use `outer.setRollbackOnly()` to **deliberately roll back outer** after inner `REQUIRED` finishes normally. This is an intentional decision by the owner.
- We use `manager.rollback(innerStatus)` to illustrate an inner participant **marking the shared transaction**, causing outer commit to raise `UnexpectedRollbackException`.

Do not write real applications to "call both rollback and setRollbackOnly on every exception" because that easily corrupts the status lifecycle.

### 5.4. Call commit/rollback Exactly Once

Each status is completed once. A safer pattern than unconditional `finally { rollback(status); }` is:

~~~java
TransactionStatus status = manager.getTransaction(definition);
try {
    doBusinessWork();
    manager.commit(status);
} catch (RuntimeException | Error failure) {
    if (!status.isCompleted()) {
        manager.rollback(status);
    }
    throw failure;
}
~~~

This is a **snippet**, without declarations for `manager`, `definition`, and `doBusinessWork`. `isCompleted()` prevents a second rollback when `commit` already completed the status before throwing an exception, such as `UnexpectedRollbackException` at the outer boundary. Production code should still consider: if rollback itself also fails, the rollback exception can mask the original exception; log the secondary failure and preserve the root cause when needed.

**Specifically:** `getTransaction` itself can throw an exception (for example `MANDATORY` missing an outer transaction) **before a status exists**. Never attempt to roll back a status that was never issued.

### 5.5. Checked Exceptions Must Be Handled with Direct Logic

When using `@Transactional`, the interceptor evaluates rollback rules based on the exception. But when you **call `getTransaction` yourself**, your own code must choose `commit/rollback`. `PlatformTransactionManager` does not inspect Java checked/unchecked exceptions from a method body it does not intercept.

Example with a checked `IOException` from reading a file:

~~~java
TransactionStatus status = manager.getTransaction(definition);
try {
    importFile();
    manager.commit(status);
} catch (IOException ex) {
    if (!status.isCompleted()) {
        manager.rollback(status);
    }
    throw ex;
}
~~~

This is a **business-decision snippet**, requiring a real manager, definition, and `importFile()` method. Handling should clearly reflect whether the transaction is still valid. If a failed import leaves the batch incomplete, rollback is usually the right choice. You do not need to rely on `rollbackFor` when you coordinate the status directly.

### 5.6. TransactionTemplate When Concise Code Is Needed

`TransactionTemplate` wraps calling the manager, commit, rollback, and exception handling inside a template callback. It is useful when you only need simple direct transaction scopes:

~~~java
TransactionTemplate template = new TransactionTemplate(manager);
template.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRED
);
String result = template.execute(status -> {
    // JDBC inside transaction; return business result.
    return "OK";
});
~~~

This is an illustrative snippet; it requires a real `manager` bean. `TransactionTemplate` avoids repeating lifecycle code, yet **does not change propagation semantics**: when the callback joins an outer transaction, the final commit still belongs to outer.

This lesson deliberately uses `PlatformTransactionManager` directly in the lab so `getTransaction`, `commit`, and `rollback` are clearly visible.

## 6. Runnable Lab: Java 17, Spring Boot, JDBC, H2, and JUnit 5

The hands-on lab uses **Java 17+**, **Spring Boot 3.5.0**, Spring JDBC, H2 in-memory, and JUnit 5. It creates a demo balance table with A=100, B=200; methods update +10 inside a transaction. After each call, the test reads the database back to distinguish **inner join** from **independent commit**.

### 6.1. Project Structure

~~~text
direct-get-transaction-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/directtx/
    │   │   ├── DirectTxApplication.java
    │   │   └── DirectTxService.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/
        └── java/com/example/directtx/
            └── DirectTxServiceTest.java
~~~

Here **the service has no `@Transactional`**: we want to prove a transaction can be opened/joined **via the direct API**, without relying on calls passing through a Spring AOP proxy. The service is still a Spring bean for dependency injection and sharing the same transaction manager/DataSource. The tests are not wrapped in a Spring Test transaction.

### 6.2. pom.xml

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
    <artifactId>direct-get-transaction-lab</artifactId>
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

### 6.3. application.properties and schema.sql

File `src/main/resources/application.properties`:

~~~properties
spring.datasource.url=jdbc:h2:mem:direct_get_transaction_lab;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

File `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE demo_account (
    id BIGINT PRIMARY KEY,
    amount BIGINT NOT NULL
);
~~~

H2 is an in-JVM-memory database. The test deletes and inserts two rows A=100/B=200 before each case. Do not use production data or assume this example is safe enough for real money transfers.

### 6.4. DirectTxApplication.java

File `src/main/java/com/example/directtx/DirectTxApplication.java`:

~~~java
package com.example.directtx;

import javax.sql.DataSource;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBootApplication
public class DirectTxApplication {
    public static void main(String[] args) {
        SpringApplication.run(DirectTxApplication.class, args);
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
~~~

We explicitly declare **one** `DataSourceTransactionManager` using the **same DataSource** as `JdbcTemplate`. `setNestedTransactionAllowed(true)` makes the intent to test `NESTED` explicit; H2 supports JDBC savepoints. With JPA/JTA or multiple datasources, check actual capabilities and managers rather than copying assumptions from this JDBC lab.

### 6.5. DirectTxService.java — The Core of the Lesson

File `src/main/java/com/example/directtx/DirectTxService.java`:

~~~java
package com.example.directtx;

import java.util.function.Function;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.DefaultTransactionDefinition;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class DirectTxService {
    public record StatusView(
        boolean newTransaction,
        boolean hasSavepoint,
        boolean active
    ) {}

    public record PairView(StatusView outer, StatusView inner) {}

    private final PlatformTransactionManager manager;
    private final JdbcTemplate jdbc;

    public DirectTxService(
            PlatformTransactionManager manager,
            JdbcTemplate jdbc) {
        this.manager = manager;
        this.jdbc = jdbc;
    }

    private DefaultTransactionDefinition definition(
            int propagation,
            String name) {
        DefaultTransactionDefinition d =
            new DefaultTransactionDefinition();
        d.setPropagationBehavior(propagation);
        d.setName(name);
        return d;
    }

    private StatusView view(TransactionStatus status) {
        return new StatusView(
            status.isNewTransaction(),
            status.hasSavepoint(),
            TransactionSynchronizationManager
                .isActualTransactionActive()
        );
    }

    private void add(long id, long delta) {
        int changed = jdbc.update(
            "UPDATE demo_account SET amount = amount + ? WHERE id = ?",
            delta, id
        );
        if (changed != 1) {
            throw new IllegalStateException("Account not found: " + id);
        }
    }

    // Programmatic transaction boundary:
    // getTransaction may create a new transaction OR join depending on propagation.
    private <T> T within(
            int propagation,
            String name,
            Function<TransactionStatus, T> work) {

        DefaultTransactionDefinition definition =
            definition(propagation, name);

        TransactionStatus status =
            manager.getTransaction(definition);

        try {
            T result = work.apply(status);
            manager.commit(status);
            return result;
        } catch (RuntimeException | Error failure) {
            // commit may have already completed status before throwing.
            if (!status.isCompleted()) {
                manager.rollback(status);
            }
            throw failure;
        }
    }

    // A. REQUIRED: no outer exists, manager opens a new physical transaction.
    public StatusView requiredStandalone() {
        return within(
            TransactionDefinition.PROPAGATION_REQUIRED,
            "required-standalone",
            status -> {
                add(1L, 10L);
                return view(status);
            }
        );
    }

    // B. REQUIRED inner: joins outer; inner commit does NOT physically commit.
    public PairView requiredInnerThenOuterRollsBack() {
        return within(
            TransactionDefinition.PROPAGATION_REQUIRED,
            "outer-required",
            outer -> {
                add(1L, 10L);
                StatusView innerView = within(
                    TransactionDefinition.PROPAGATION_REQUIRED,
                    "inner-required",
                    inner -> {
                        add(2L, 10L);
                        return view(inner);
                    }
                );
                // Inner commit has run; outer still owns T1.
                outer.setRollbackOnly();
                return new PairView(view(outer), innerView);
            }
        );
    }

    // C. REQUIRES_NEW inner: B commits independently, outer rolls back A.
    public PairView requiresNewInnerThenOuterRollsBack() {
        return within(
            TransactionDefinition.PROPAGATION_REQUIRED,
            "outer-for-requires-new",
            outer -> {
                add(1L, 10L);
                StatusView innerView = within(
                    TransactionDefinition.PROPAGATION_REQUIRES_NEW,
                    "inner-requires-new",
                    inner -> {
                        add(2L, 10L);
                        return view(inner);
                    }
                );
                outer.setRollbackOnly();
                return new PairView(view(outer), innerView);
            }
        );
    }

    // D. A REQUIRED participant rolls back: shared T1 becomes rollback-only.
    public void participantRollbackPreventsOuterCommit() {
        within(
            TransactionDefinition.PROPAGATION_REQUIRED,
            "outer-marked-rollback",
            outer -> {
                add(1L, 10L);

                TransactionStatus inner = manager.getTransaction(
                    definition(
                        TransactionDefinition.PROPAGATION_REQUIRED,
                        "inner-explicit-rollback"
                    )
                );
                try {
                    add(2L, 10L);
                    manager.rollback(inner);
                } catch (RuntimeException | Error failure) {
                    if (!inner.isCompleted()) {
                        manager.rollback(inner);
                    }
                    throw failure;
                }

                // Outer tries to commit in within(...), but T1 is already rollback-only.
                return null;
            }
        );
    }

    // E. SUPPORTS with no outer: does not create a new physical transaction.
    public StatusView supportsStandalone() {
        return within(
            TransactionDefinition.PROPAGATION_SUPPORTS,
            "supports-no-outer",
            this::view
        );
    }

    // F. MANDATORY with no outer: getTransaction throws an exception.
    public void mandatoryStandalone() {
        within(
            TransactionDefinition.PROPAGATION_MANDATORY,
            "mandatory-no-outer",
            status -> null
        );
    }

    // G. MANDATORY with outer: joins physical T1.
    public PairView mandatoryJoiningOuter() {
        return within(
            TransactionDefinition.PROPAGATION_REQUIRED,
            "outer-for-mandatory",
            outer -> {
                StatusView innerView = within(
                    TransactionDefinition.PROPAGATION_MANDATORY,
                    "inner-mandatory",
                    this::view
                );
                return new PairView(view(outer), innerView);
            }
        );
    }

    // H. NESTED with no outer: new transaction, NOT a savepoint.
    public StatusView nestedStandalone() {
        return within(
            TransactionDefinition.PROPAGATION_NESTED,
            "nested-no-outer",
            this::view
        );
    }

    // I. NESTED with outer: savepoint within the same physical transaction.
    public PairView nestedJoiningOuter() {
        return within(
            TransactionDefinition.PROPAGATION_REQUIRED,
            "outer-for-nested",
            outer -> {
                StatusView innerView = within(
                    TransactionDefinition.PROPAGATION_NESTED,
                    "inner-nested",
                    this::view
                );
                return new PairView(view(outer), innerView);
            }
        );
    }

    // J. New REQUIRED that encounters an error: rolls back the whole new transaction.
    public void requiredStandaloneFailure() {
        within(
            TransactionDefinition.PROPAGATION_REQUIRED,
            "required-fail",
            status -> {
                add(1L, 10L);
                throw new IllegalStateException("controlled failure");
            }
        );
    }

    // K. Two separate standalone calls: T1 commits, then T2 fails.
    public void twoSeparateRequiredCalls() {
        within(
            TransactionDefinition.PROPAGATION_REQUIRED,
            "first-required",
            status -> {
                add(1L, 10L);
                return null;
            }
        );
        within(
            TransactionDefinition.PROPAGATION_REQUIRED,
            "second-required",
            status -> {
                add(2L, 10L);
                throw new IllegalStateException("second step failed");
            }
        );
    }

    // L. NEVER forbids joining an active outer transaction.
    public void neverInsideOuter() {
        within(
            TransactionDefinition.PROPAGATION_REQUIRED,
            "outer-for-never",
            outer -> within(
                TransactionDefinition.PROPAGATION_NEVER,
                "inner-never",
                status -> null
            )
        );
    }
}
~~~

### 6.6. Why Is This Code Different from @Transactional?

`DirectTxService` does not need the `@Transactional` annotation because it **calls `manager.getTransaction(...)` itself**. The transaction manager still binds the JDBC connection to the thread when opening a transaction; SQL statements from `JdbcTemplate` use the exact right resource.

The `within(...)` helper:

1. Creates a `DefaultTransactionDefinition` with an explicit propagation and name.
2. Calls `manager.getTransaction(definition)` before the body.
3. Runs the work while the status is active/participating.
4. Calls `manager.commit(status)` after success.
5. If code throws a RuntimeException/Error, calls `manager.rollback(status)` if status is not yet completed.
6. **Does not roll back again** when `commit` already completed itself and threw an exception due to rollback-only.

`within(...)` is a **helper for the hands-on lab**, not a complete production transaction library. Because it uses `Function`, it only illustrates unchecked exceptions. For checked exceptions, real code needs a callback interface with appropriate `throws` or an explicit try/catch block. In larger systems, `TransactionTemplate` is usually shorter and safer than repeating boilerplate like the above.

Because the transaction is managed **directly**, calling `within(...)` inside the same bean still goes through the manager: it does not hit the self-invocation pitfall of `@Transactional` on a method called via `this.inner()`. However, the resources must match the manager, thread, and datasource.

### 6.7. DirectTxServiceTest.java: Verifying 12 Scenarios

File `src/test/java/com/example/directtx/DirectTxServiceTest.java`:

~~~java
package com.example.directtx;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.UnexpectedRollbackException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class DirectTxServiceTest {
    @Autowired
    private DirectTxService service;

    @Autowired
    private JdbcTemplate jdbc;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM demo_account");
        jdbc.update(
            "INSERT INTO demo_account (id, amount) VALUES (?, ?)",
            1L, 100L
        );
        jdbc.update(
            "INSERT INTO demo_account (id, amount) VALUES (?, ?)",
            2L, 200L
        );
    }

    private long amount(long id) {
        Long result = jdbc.queryForObject(
            "SELECT amount FROM demo_account WHERE id = ?",
            Long.class, id
        );
        if (result == null) {
            throw new AssertionError("Missing account " + id);
        }
        return result;
    }

    @Test
    void requiredStartsNewWhenNoTransactionExists() {
        DirectTxService.StatusView s = service.requiredStandalone();

        assertTrue(s.newTransaction());
        assertTrue(s.active());
        assertFalse(s.hasSavepoint());
        assertEquals(110L, amount(1L));
        assertEquals(200L, amount(2L));
    }

    @Test
    void requiredParticipantDoesNotCommitBeforeOuter() {
        DirectTxService.PairView p =
            service.requiredInnerThenOuterRollsBack();

        assertTrue(p.outer().newTransaction());
        assertFalse(p.inner().newTransaction());
        assertTrue(p.inner().active());
        assertEquals(100L, amount(1L));
        assertEquals(200L, amount(2L));
    }

    @Test
    void requiresNewParticipantCommitsIndependently() {
        DirectTxService.PairView p =
            service.requiresNewInnerThenOuterRollsBack();

        assertTrue(p.outer().newTransaction());
        assertTrue(p.inner().newTransaction());
        assertEquals(100L, amount(1L));
        assertEquals(210L, amount(2L));
    }

    @Test
    void participatingRollbackMarksSharedTransactionRollbackOnly() {
        assertThrows(
            UnexpectedRollbackException.class,
            service::participantRollbackPreventsOuterCommit
        );
        assertEquals(100L, amount(1L));
        assertEquals(200L, amount(2L));
    }

    @Test
    void supportsWithoutOuterHasNoPhysicalTransaction() {
        DirectTxService.StatusView s = service.supportsStandalone();

        assertFalse(s.newTransaction());
        assertFalse(s.active());
        assertFalse(s.hasSavepoint());
    }

    @Test
    void mandatoryWithoutOuterRejectsCall() {
        assertThrows(
            IllegalTransactionStateException.class,
            service::mandatoryStandalone
        );
    }

    @Test
    void mandatoryWithOuterJoinsExistingTransaction() {
        DirectTxService.PairView p =
            service.mandatoryJoiningOuter();

        assertTrue(p.outer().newTransaction());
        assertFalse(p.inner().newTransaction());
        assertTrue(p.inner().active());
    }

    @Test
    void nestedWithoutOuterStartsNewTransaction() {
        DirectTxService.StatusView s = service.nestedStandalone();

        assertTrue(s.newTransaction());
        assertFalse(s.hasSavepoint());
        assertTrue(s.active());
    }

    @Test
    void nestedWithOuterUsesSavepoint() {
        DirectTxService.PairView p = service.nestedJoiningOuter();

        assertTrue(p.outer().newTransaction());
        assertFalse(p.inner().newTransaction());
        assertTrue(p.inner().hasSavepoint());
        assertTrue(p.inner().active());
    }

    @Test
    void failedStandaloneRequiredRollsBackItsOwnTransaction() {
        assertThrows(
            IllegalStateException.class,
            service::requiredStandaloneFailure
        );
        assertEquals(100L, amount(1L));
        assertEquals(200L, amount(2L));
    }

    @Test
    void separateStandaloneRequiredCallsAreNotAtomicTogether() {
        assertThrows(
            IllegalStateException.class,
            service::twoSeparateRequiredCalls
        );
        assertEquals(110L, amount(1L));
        assertEquals(200L, amount(2L));
    }

    @Test
    void neverCannotBeCalledInsideTransaction() {
        assertThrows(
            IllegalTransactionStateException.class,
            service::neverInsideOuter
        );
        assertEquals(100L, amount(1L));
        assertEquals(200L, amount(2L));
    }
}
~~~

**Do not annotate the test class with `@Transactional`.** If the test framework opens an outer transaction, `requiredStartsNewWhenNoTransactionExists` will no longer have "no outer", and `mandatoryWithoutOuterRejectsCall` may not throw an exception. The lab requires the exact condition of **with/without a transaction before `getTransaction`**.

`@BeforeEach` resets data outside any test transaction before each run. Assertions read back through `JdbcTemplate` after the service method finishes, so the results reflect real commits/rollbacks on H2.

## 7. Running the Lab and Reading Results

Requires Java 17+, Maven, and ability to download dependencies on the first run. From the `direct-get-transaction-lab` directory:

~~~bash
java -version
mvn -version
mvn test
~~~

If the project has a Maven Wrapper, use `./mvnw test` on Linux/macOS or `.\mvnw.cmd test` in Windows PowerShell.

With compatible source and H2 database, the expectation is **12 tests pass, 0 failures, 0 errors**. This is the **expected result** from the code, not a log from an executed run.

| Test | Expected | What it proves |
| --- | --- | --- |
| `requiredStartsNewWhenNoTransactionExists` | new=true; A=110, B=200 | REQUIRED opens new when no outer exists. |
| `requiredParticipantDoesNotCommitBeforeOuter` | inner new=false; A=100, B=200 | Inner participant commit does not physically commit; outer rolls back both. |
| `requiresNewParticipantCommitsIndependently` | inner new=true; A=100, B=210 | REQUIRES_NEW commits independently. |
| `participatingRollbackMarksSharedTransactionRollbackOnly` | UnexpectedRollbackException; A=100, B=200 | Inner REQUIRED rollback can cause outer commit to fail. |
| `supportsWithoutOuterHasNoPhysicalTransaction` | new=false; active=false | getTransaction may not start a physical transaction. |
| `mandatoryWithoutOuterRejectsCall` | IllegalTransactionStateException | MANDATORY requires an existing transaction. |
| `mandatoryWithOuterJoinsExistingTransaction` | inner new=false; active=true | MANDATORY joins outer. |
| `nestedWithoutOuterStartsNewTransaction` | new=true; savepoint=false | NESTED without outer opens a new transaction. |
| `nestedWithOuterUsesSavepoint` | new=false; savepoint=true | NESTED with outer creates a savepoint when supported. |
| `failedStandaloneRequiredRollsBackItsOwnTransaction` | A=100, B=200 | Failed standalone REQUIRED rolls back the physical transaction. |
| `separateStandaloneRequiredCallsAreNotAtomicTogether` | A=110, B=200 | Two consecutive standalone getTransaction calls do not automatically create a wrapping outer transaction. |
| `neverCannotBeCalledInsideTransaction` | IllegalTransactionStateException | NEVER rejects when an outer transaction is active. |

### Two Key Observations

**Observation 1 — `commit(inner)` does not mean committed to the DB.** Test `requiredParticipantDoesNotCommitBeforeOuter` updates A in outer, updates B in inner REQUIRED, and then commits inner. Afterward outer calls `setRollbackOnly` and completes; both A and B return to their initial values. Thus inner `commit` only completes the **logical scope**, not a physical commit.

**Observation 2 — rolling back an inner REQUIRED can strip outer's ability to commit.** In test `participatingRollbackMarksSharedTransactionRollbackOnly`, `rollback(inner)` marks the shared transaction. Although outer does not throw an exception in its own business body, calling `commit(outer)` leads to `UnexpectedRollbackException`. This is why a participant's transaction status still matters, even when `isNewTransaction()` is false.

### Purpose of the 12 Tests

The goal is not merely test count; each test varies **one condition**: propagation or outer state. The `newTransaction`, `hasSavepoint`, and post-completion DB readback values are stronger evidence than just counting how many times `getTransaction` was called.

## 8. Common Mistakes and How to Avoid Them

### 8.1. Equating a Logical Scope with a Physical Transaction

Two `getTransaction(REQUIRED)` calls when an outer transaction exists can return two different statuses while still using **one JDBC transaction**. Do not use the number of `TransactionStatus` objects to count physical transactions.

### 8.2. Relying on isNewTransaction=false to Skip commit/rollback

`isNewTransaction` tells you whether the scope opened a new physical transaction; it does not mean the status can be abandoned. Every status returned by the manager must go through proper completion lifecycle handling, including participants. Never call commit/rollback again on a status that already has `isCompleted=true`.

### 8.3. Using a Different Transaction Manager Than JdbcTemplate

If the manager manages `DataSource A` while JDBC code obtains connections from `DataSource B`, calling getTransaction to create/join for A will not control B. Ensure the right **manager, datasource, thread, and resource**. With multiple managers, choose qualifiers explicitly and write real verification tests.

### 8.4. Treating REQUIRES_NEW as a Universal Fix

`REQUIRES_NEW` changes semantics to an independent transaction; inner's commit can survive after outer rolls back. It may need a second connection and hit lock waits if inner writes to the same row outer has locked. Set propagation according to business invariants, not merely from a desire to "have a new transaction".

### 8.5. Failing to Distinguish Inner vs. Outer rollback-only

An inner `REQUIRED` calling `rollback(innerStatus)` typically marks global rollback-only when participating. Outer catching an error or returning normally from its business body cannot clear the marker that was already set; `UnexpectedRollbackException` on outer commit signals that commit did not occur.

### 8.6. Catching Every Exception and Committing Anyway

When managing directly, you decide the transaction state. If code catches a DB error and still proceeds to `commit`, data can end up inconsistent or the transaction may already be unable to commit. Avoid the "swallow every exception" pattern; roll back according to invariants and understand DB behavior after errors.

### 8.7. Calling getTransaction Without Completing the Status

Forgetting `commit`/`rollback` can hold connections/locks/resource bindings for a long time, affecting later calls and exhausting the pool. Every `getTransaction` returning a valid status needs a clear completion path. If an exception from `getTransaction` occurs before a status is returned, do not pretend a status exists to roll back.

### 8.8. Rolling Back or Committing Twice

After `manager.commit(status)` or `manager.rollback(status)`, the status may have `isCompleted=true`. Calling again can throw `IllegalTransactionStateException` or make error handling confusing. In the sample code, `if (!status.isCompleted())` avoids a second rollback when `commit` already processed rollback-only and threw an exception.

### 8.9. Conflating Programmatic Transactions with @Transactional

`@Transactional` relies on an interceptor/proxy or AspectJ weaving, evaluating rollback rules when a method throws an exception. `manager.getTransaction` is a **direct Java call** requiring no proxy on that method, but the caller must ensure completion. If a programmatic method runs inside an active `@Transactional` scope, it **can join** that transaction when using the same manager/resource and compatible propagation; they are not two isolated worlds.

### 8.10. Failing to Check Manager Capabilities

`PROPAGATION_NESTED` requires savepoint support when an outer transaction exists. `REQUIRES_NEW` requires suspension/resource handling, and `isolation` and `timeout` depend on the manager/driver/database. With JPA/JTA/reactive transaction managers, implementation semantics differ from this JDBC lab; do not copy `DataSourceTransactionManager` assumptions as a universal rule for every infrastructure.

### 8.11. Testing Inside a @Transactional Test

When a test class is annotated with `@Transactional`, the framework opens an outer transaction and `getTransaction(REQUIRED)` calls in the service may **join the test transaction**, altering `newTransaction` and commit/rollback behavior. For tests that need to distinguish standalone vs. join, the test must not accidentally have an outer transaction.

### 8.12. Losing Track of When the Transaction Ends by Returning Status

Never return a live `TransactionStatus` to a controller for the controller to arbitrarily commit after the resource/thread may have changed. If you need to display information, create a `record` or DTO **snapshot before completion**, then complete the status within the same managed scope. That is why the lab returns `StatusView` instead of returning an active status.

## 9. Design Workflow When Using getTransaction Directly

For a feature consisting of multiple SQL statements, proceed step by step:

1. **Identify atomic invariants**: which changes must commit or roll back together?
2. **Identify existing transactions**: might a caller or service already have opened a transaction on the same manager/resource?
3. **Choose propagation**: REQUIRED to join if present; REQUIRES_NEW for independence; NESTED for local rollback via savepoint when supported; MANDATORY to require an outer transaction.
4. **Build TransactionDefinition**: set propagation, isolation, timeout, readOnly, and name when meaningful.
5. **Call getTransaction once per scope** and keep status local.
6. **Execute SQL using a resource managed by the manager**, such as JdbcTemplate sharing the DataSource.
7. **Complete the scope once**: commit on success or roll back on error/invariant violation; do not swallow exceptions.
8. **Account for rollback-only and unexpected rollback** if participating in an outer transaction.
9. **Test standalone and nested/join** separately: observe isNewTransaction, hasSavepoint, actualActive, and persisted state.
10. **Consider TransactionTemplate** if the logic only needs a simple scope to reduce boilerplate and lifecycle errors.

If a system has multiple steps that need shared atomicity, the clearest approach is usually **one transaction at the business facade**, with child steps joining via `REQUIRED`. Only open an independent transaction when business rules genuinely allow inner data to survive an outer failure.

## 10. Self-Assessment Questions

1. **Does `manager.getTransaction(REQUIRED)` always open a new transaction?** — No; it can **join an existing transaction**.
2. **When no outer exists, what does REQUIRED return for `isNewTransaction()`?** — Usually true with the JDBC manager in the lab.
3. **When an outer already exists, what does REQUIRED return?** — Usually false because it joins the same physical transaction.
4. **Does `commit(innerStatus)` on a participant immediately commit to the database?** — No; outer owns the physical commit.
5. **If outer rolls back after an inner participant commits, do inner's changes remain?** — No, if they share the same physical transaction.
6. **What can `rollback(innerStatus)` cause during outer commit?** — It can mark rollback-only and trigger `UnexpectedRollbackException`.
7. **Does `REQUIRES_NEW` ensure inner rolls back together with outer?** — No; it has an independent commit.
8. **How does `NESTED` in JDBC with an outer differ from REQUIRES_NEW?** — NESTED uses a savepoint inside the same physical transaction; REQUIRES_NEW opens an independent physical transaction.
9. **When no outer exists, does `NESTED` require a savepoint?** — No; it can open a new transaction with `hasSavepoint=false`.
10. **What does `MANDATORY` do when no outer exists?** — Throws `IllegalTransactionStateException`.
11. **When no outer exists, can `SUPPORTS` have a status that is not a new transaction?** — Yes; the status exists, while the actual transaction may not be active.
12. **What propagation does `getTransaction(null)` typically carry by default?** — The standard default is REQUIRED.
13. **When using the direct API, does a checked exception automatically trigger rollbackFor?** — There is no interceptor applying rules; the caller decides commit/rollback.
14. **When must you not roll back a status again in a catch block?** — When the status is already completed after commit/rollback or has already been handled by the manager.
15. **Why shouldn't tests be annotated with @Transactional?** — Because the test transaction alters the outer state that this lesson measures.
16. **What should you use for shorter code while keeping programmatic transaction semantics?** — `TransactionTemplate`.

## 11. Extended Exercises

**Exercise A — REQUIRED in a facade:** add an outer method using `getTransaction(REQUIRED)` wrapping two `required...` calls inside. Predict `isNewTransaction` for each scope, roll back one inner scope, and verify at outer commit.

**Exercise B — Independence with REQUIRES_NEW:** change inner from REQUIRED to REQUIRES_NEW on a copy of the test, having outer and inner update **two different rows**. Predict the data after outer rollback and explain why the inner commit survives.

**Exercise C — MANDATORY and NEVER:** across calls with and without an active transaction, use `getTransaction(MANDATORY)` and `getTransaction(NEVER)`. Write a table showing which conditions succeed and which throw exceptions before running the test.

**Exercise D — Nested savepoint:** with `DataSourceTransactionManager` supporting savepoints, call `getTransaction(NESTED)` while outer exists, update B, and then roll back nested. Continue updating A in outer and commit. Compare with `rollback(inner REQUIRED)`, which can mark global rollback-only.

**Exercise E — Exception handling:** modify the `within` helper to support checked exceptions using a callback with `throws Exception`. Ensure proper rollback when a checked exception signals business failure and avoid rolling back twice if `commit` already completed.

**Exercise F — Observing logs:** enable transaction manager logging in a test environment and correlate when physical transaction start, participate, suspend, resume, and commit/rollback occur. Avoid logging sensitive information from business data.

## 12. Summary

`PlatformTransactionManager.getTransaction(TransactionDefinition)` is the API that **evaluates propagation requirements** against the current transaction state. It can **create a new transaction**, **join**, **suspend an outer transaction**, **create a savepoint**, **run outside a transaction**, or **reject the call** depending on configuration and manager capabilities.

**Key takeaway:** one `TransactionStatus` does not equate to one new physical transaction. Check `isNewTransaction()` and actual transaction activity, understand propagation and completion semantics, and verify persisted data.

With `REQUIRED`, **committing a participant does not prematurely commit the physical transaction**, and **rolling back a participant can revoke the outer transaction's ability to commit**. When you want to avoid lifecycle mistakes from manual coding, consider `TransactionTemplate` or `@Transactional` at appropriate service boundaries.

### Official References

- [Spring Framework — Understanding the Transaction Abstraction](https://docs.spring.io/spring-framework/reference/data-access/transaction/strategies.html)
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — AbstractPlatformTransactionManager API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html)
- [Spring Framework — PlatformTransactionManager API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/PlatformTransactionManager.html)
- [Spring Framework — TransactionStatus API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/TransactionStatus.html)
