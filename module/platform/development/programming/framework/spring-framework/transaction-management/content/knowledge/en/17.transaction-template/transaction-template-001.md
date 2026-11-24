# When Visible Transaction Boundaries in Code Are Needed

## 1. Why Must a Transaction Boundary Sometimes Be Visible Directly in Java?

In most standard Spring services, `@Transactional` is the most readable choice:

```java
@Transactional
public void createOrder(CreateOrderCommand command) {
    validate(command);
    orderRepository.save(toOrder(command));
    inventoryRepository.reserve(command.items());
}
```

This is an illustrative snippet, not a standalone class: `validate`, `toOrder`, and the two repositories are defined by the application. The annotation places a **transaction boundary around the entire method called through a Spring AOP proxy**. If the entire method is genuinely **a single unit of work** that must commit/rollback together, that is a good design.

However, if the method includes **multiple phases with different transaction requirements**, for example:

1. Calling an external API to fetch information (which can be slow).
2. Writing two related records in **a short transaction**.
3. Only after the transaction has completed, calling a subsequent step, sending a notification, or reading a report.
4. If the subsequent step fails, **not** wanting to pretend the database write in step 2 never committed.

Then placing `@Transactional` on the **entire method** can keep the transaction open too long or place the wrong semantic boundary. In that case, `TransactionTemplate` lets you express it very clearly:

```java
ExternalData source = fetchExternalData(); // outside DB transaction

String id = transactionTemplate.execute(status -> {
    persistSource(source);
    updateRelatedRows(source);
    return source.id();
}); // execute has completed the completion path of this scope

notifyAbout(id); // outside the callback, not in the scope the template just created
```

This snippet **illustrates the structure** and assumes the methods/variables are declared. The main point to learn is that **the callback block is the exact part of the code required to run within the template's transaction scope**. If the template creates a new transaction and there is no outer transaction, when `execute(...)` returns normally, the transaction manager has already executed the completion path, usually a successful commit. If the callback throws a runtime exception, the template handles the rollback and propagates the exception.

**Important distinction:** a callback `return` is not synonymous with a database commit; the **`transactionTemplate.execute(...)` call returning to the caller** only occurs after the manager completion step. Moreover, if the template uses `PROPAGATION_REQUIRED` and is **joining an outer transaction**, `execute` returning only means the logical inner scope has completed; the **physical commit still waits for the outer owner**.

The topic of this article is **TransactionTemplate → When Visible Transaction Boundaries in Code Are Needed**. Not every problem needs programmatic transactions. The goal is to know **when you should**, **when you should not**, **how to use the API**, **which promises must not be inferred**, and **how to prove it with integration tests**.

## 2. Definition: What Is TransactionTemplate?

`org.springframework.transaction.support.TransactionTemplate` is Spring's abstraction for **imperative programmatic transaction management**. It extends `DefaultTransactionDefinition` and implements `TransactionOperations`, using an actual `PlatformTransactionManager` to perform:

- `getTransaction(definition)` before the callback;
- running the callback with a `TransactionStatus`;
- if the callback throws a `RuntimeException` or `Error`, handling the appropriate rollback and rethrowing the error;
- if the callback returns normally, completing the scope via the `commit(status)` path, in which the manager still must respect rollback-only;
- cleaning up transaction resources appropriate to the manager.

Developers **do not need** to manually write `try/catch/commit/rollback/finally` against `PlatformTransactionManager` for the common case.

```java
TransactionTemplate tx = new TransactionTemplate(transactionManager);

String result = tx.execute(status -> {
    repository.insert("alpha");
    return "alpha";
});
```

This snippet requires `PlatformTransactionManager transactionManager` and `repository` to exist. The return type of `execute(...)` is generic; `null` is a valid result if the callback returns `null`. `TransactionStatus` has `setRollbackOnly()` and `isNewTransaction()` methods, which are useful when you need to make explicit decisions in code.

If the callback does not need to return a value, use:

```java
tx.executeWithoutResult(status -> {
    repository.insert("alpha");
    repository.insert("beta");
});
```

`executeWithoutResult` is an API on `TransactionOperations`, provided by `TransactionTemplate`. In the standalone example later, all imports and dependencies are explicitly declared.

### 2.1. Comparison with `@Transactional`

| Criterion | `@Transactional` declarative | `TransactionTemplate` programmatic |
| --- | --- | --- |
| Boundary location | Around the method call intercepted by AOP | The exact **callback scope** passed into `execute` |
| Needs to go through a proxy for that boundary? | **Yes** in the default proxy mode | **No**: the template call is direct Java code |
| Separating a short DB section between long steps | Requires splitting beans/methods and calling through proxy | Easy to express directly inside the orchestration method |
| Multiple independent transactions in one workflow | Can be created using multiple beans/methods with different propagation | Can invoke multiple separate `execute` calls |
| Rollback on runtime exception | According to `@Transactional` rollback rules | Template handles runtime exception/Error escaping the callback |
| Checked exception | Controlled via `rollbackFor/noRollbackFor` | Callback does not declare checked exceptions; wrap or explicitly call `setRollbackOnly` |
| Deciding to rollback without throwing an exception | `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()` | `status.setRollbackOnly()` directly |
| Does business code know the Spring transaction API? | Little or none | Yes: depends on `TransactionTemplate` |
| Configuring propagation, isolation, timeout | Belongs to the annotation, manager, and configuration | Belongs to the `TransactionTemplate` instance |
| Reactive transactions | Use appropriate reactive transaction support | **Do not** use imperative template; consider `TransactionalOperator` |

**Selection rule:** if there are many ordinary service methods, declarative transactions help separate infrastructure from business code. If there are only a few places needing an explicit boundary or workflows orchestrating clear phases, `TransactionTemplate` is worth considering. This is also the recommendation in Spring's documentation on **Choosing Between Programmatic and Declarative Transaction Management**.

### 2.2. TransactionTemplate Is Not a Type of Transaction Manager

`TransactionTemplate` does not directly open a database connection with its own mechanism. It **delegates** to a `PlatformTransactionManager`:

```text
Service method
  |
  +-- tx.execute(callback)
         |
         +-- manager.getTransaction(definition)
         |      -> new physical transaction / join existing transaction
         |
         +-- callback.doInTransaction(status)
         |      -> JDBC/JPA repository operations
         |
         +-- manager.commit(status) or rollback(status)
         |      -> rollback-only, synchronization, cleanup
         |
         +-- return result or propagate exception
```

It does not replace choosing the right `DataSourceTransactionManager`, `JdbcTransactionManager`, `JpaTransactionManager`, JTA, or an appropriate resource manager. Each manager has its own semantics and resources.

## 3. Scenarios Where You SHOULD Use an Explicit Boundary

### 3.1. Only the DB Update Section Needs a Transaction, the Rest of the Workflow Does Not

Example of a batch item:

```text
parse input file
  -> validate syntax
  -> fetch remote metadata
  -> BEGIN DB TRANSACTION
       INSERT detail rows
       UPDATE aggregate
     COMMIT DB TRANSACTION
  -> format result
  -> notify downstream
```

Placing `@Transactional` on the entire method can cause the transaction to hold connections/locks while reading files, making HTTP calls, or waiting for user input. Using `TransactionTemplate` helps wrap the transaction only around the DB section that needs atomicity.

Do not interpret "short transaction" as skipping atomicity: SQL statements belonging to the same invariant must still reside **within the same callback** and the same manager.

### 3.2. Needing Multiple Independent Units of Work in a Loop

For example, importing 100,000 rows in chunks:

```java
for (Chunk chunk : chunks) {
    tx.executeWithoutResult(status -> {
        validateChunk(chunk);
        persistChunk(chunk);
    });
}
```

This is an illustrative snippet; `Chunk`, `chunks`, `validateChunk`, and `persistChunk` are supplied by the application. Each call to `executeWithoutResult` has its own **logical transaction scope**. If there is no outer transaction and propagation is `REQUIRED`, each chunk usually has its own physical transaction, allowing checkpoint/progress tracking and retrying failed chunks. If the loop is inside an outer `@Transactional`, all `REQUIRED` callbacks can participate in the same physical transaction — **no longer committing per chunk**.

Chunking changes atomicity: once chunk 1 has committed, a failure in chunk 2 **does not automatically** roll back chunk 1. Only use this when the business requirements allow partial success, with idempotency keys and safe resumption.

### 3.3. Needing to Handle a Failure from a Previous Step and Then Start a New Transaction

```java
try {
    tx.executeWithoutResult(status -> persistOneOperation());
} catch (IllegalStateException ex) {
    recordFailure(ex);
}

tx.executeWithoutResult(status -> persistIndependentOperation());
```

These snippets are not standalone. The key point is that `catch` is **outside the first `execute`**: the transaction manager has already gone through the rollback path for the failed scope before code reaches the second step. If you catch the exception **inside the callback** and keep executing SQL, the DB/JPA resource may already be in an aborted/rollback-only state. Do not "swallow the error" inside a broken physical transaction and expect to commit.

At the same time, calling two callbacks only truly separates **physical commit/rollback** when they are not placed inside an outer `REQUIRED` transaction. To guarantee independence when an outer transaction exists, you must control propagation and accept consequences such as `REQUIRES_NEW`.

### 3.4. Needing Intentional Rollback When a Business Operation Returns a Result Instead of Throwing an Error

A step might receive a response indicating "ineligible, discard all changes":

```java
Outcome result = tx.execute(status -> {
    repository.insertDraft();
    if (!eligibilityPolicy.accepted()) {
        status.setRollbackOnly();
        return Outcome.rejected("Not eligible");
    }
    return Outcome.accepted();
});
```

`Outcome`, `repository`, and `eligibilityPolicy` are illustrative classes/variables. When a callback marks rollback-only on a status that **owns a new transaction**, `execute` can **return normally** even though the manager performs a rollback. That is intentional semantics, not a Spring bug. Therefore, the **return value must clearly indicate "accepted" or "rejected"**, and a result must never be labeled `CREATED` before completion actually succeeds.

If the template is only participating in an outer transaction, `setRollbackOnly` can mark the shared physical transaction rollback-only and the outer owner will later encounter `UnexpectedRollbackException`. Do not treat `setRollbackOnly` as a local boolean that does not affect the caller.

### 3.5. Wanting to Avoid Annotation Self-Invocation Issues at a Small Point

In proxy mode, `this.someTransactionalMethod()` usually does not go through the Spring proxy, so the annotation on the inner method does not create a separate boundary. Conversely, a direct call:

```java
public void outer() {
    helper();
}

private void helper() {
    tx.executeWithoutResult(status -> repository.insert("ok"));
}
```

still uses the template, even though `helper` is private and called via `this`. Because **the boundary is an API call**, not advice intercepting a method. That is a valid technical reason to use the template in a small orchestration method.

However, you should not convert all code to templates just to work around an unreasonable bean design. If there are multiple domain services, the declarative approach on separate service beans can be easier to maintain.

### 3.6. Wanting to Attach a Transaction Name or Custom Policy to a Section

`TransactionTemplate` extends `DefaultTransactionDefinition`, allowing configuration of:

```java
TransactionTemplate tx = new TransactionTemplate(manager);
tx.setName("settle-invoice");
tx.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
tx.setIsolationLevel(TransactionDefinition.ISOLATION_READ_COMMITTED);
tx.setTimeout(15);
tx.setReadOnly(false);
```

This snippet requires imports/manager. These settings are **requests** to the manager, not a guarantee that every database/driver implements them identically. `REQUIRES_NEW` creates an independent transaction and may require an extra connection. Isolation, timeout, and readOnly are especially meaningful when **creating a new transaction**; if `REQUIRED` joins an existing transaction, the outer scope usually determines the physical transaction characteristics.

Create **one template instance per static configuration**, such as `readOnlyTemplate` and `writeTemplate`. `TransactionTemplate` is thread-safe when the instance's configuration is not continuously mutated while multiple threads use it; do not call `setPropagationBehavior`/`setTimeout` before every request on a shared singleton object and cause races.

## 4. Scenarios Where You Should NOT Choose TransactionTemplate

1. **A pure DB service method with one obvious boundary.** `@Transactional` is more readable; there is no need for nested callbacks just to "look explicit".
2. **Wanting to lock a database row or prevent duplicates.** `TransactionTemplate` does not automatically add `SELECT FOR UPDATE`, `UNIQUE`, optimistic versioning, or proper isolation; DB constraints/locking are needed.
3. **Wanting to make an email/HTTP/Kafka call part of a JDBC rollback.** The template manages resources participating in the manager, not rolling back an email already sent. See transactional outbox/idempotency.
4. **Wanting to avoid checking transaction isolation or concurrent races.** An explicit boundary does not fix TOCTOU bugs or lost updates.
5. **Using reactive `Mono`/`Flux`.** `TransactionTemplate` is imperative and typically relies on thread-bound resources; use `TransactionalOperator` with `ReactiveTransactionManager` to wrap reactive publisher lifecycles.
6. **Trying to make one transaction span arbitrary multiple threads.** Imperative transaction ThreadLocals are not automatically propagated across `CompletableFuture`, `@Async`, or executors.
7. **Needing a distributed transaction across two databases/external systems.** A local `PlatformTransactionManager` does not automatically solve multi-resource coordination.
8. **Just wanting to catch an exception inside the callback and continue.** The database/ORM may already have a broken transaction; split the boundary properly or let rollback complete before handling.
9. **Wanting to retry SQL without idempotency.** A callback with a new transaction does not guarantee safe retries if the previous commit outcome is uncertain.
10. **Using it inside a shared domain model and creating deep Spring coupling.** You can extract an infrastructure/application service that wraps the template and keep the domain model framework-agnostic.

**Architectural principle:** place boundaries **at the application/orchestration layer**, which knows which unit of work needs to be atomic. Do not scatter templates across every repository and lose business boundaries.

## 5. `execute`, `executeWithoutResult`, `TransactionStatus`

### 5.1. `execute(TransactionCallback<T>)`

```java
Long id = tx.execute(status -> {
    long createdId = insertOrder();
    insertLineItems(createdId);
    return createdId;
});
```

This is an illustrative pattern assuming `insertOrder`/`insertLineItems` methods. If there is a new physical transaction, both operations are enclosed in the same DB transaction. `id` is returned to the caller **after the transaction manager completes the scope**. However, when the callback only joins an outer `REQUIRED`, the physical commit still waits for the outer transaction.

Do not take the callback's return value as proof that the database has durably committed when an outer transaction or a later commit error is still possible.

### 5.2. `executeWithoutResult(Consumer<TransactionStatus>)`

```java
tx.executeWithoutResult(status -> {
    jdbc.update("UPDATE account SET active = ? WHERE id = ?", true, 10L);
});
```

This pattern is concise when no value needs to be returned from the callback. It does not require manually implementing the `TransactionCallbackWithoutResult` class. `status` is still usable if `setRollbackOnly()` is needed.

### 5.3. `status.setRollbackOnly()` Differs from Throwing an Exception

```java
Decision decision = tx.execute(status -> {
    insertDraft();
    if (businessCheckFails()) {
        status.setRollbackOnly();
        return Decision.REJECTED;
    }
    return Decision.ACCEPTED;
});
```

The callback returns `REJECTED` while the transaction can roll back normally; no `RuntimeException` has to be thrown. A transaction owner that marks local rollback-only can roll back **silently in terms of exceptions**. Therefore, the result type must accurately describe the business semantics.

For checked exceptions not permitted to be thrown directly from the callback signature, there are two paths:

**A. Catch and return a business result after marking rollback-only:**

```java
return tx.execute(status -> {
    try {
        callCodeThatThrowsIOException();
        saveData();
        return Result.ok();
    } catch (IOException ex) {
        status.setRollbackOnly();
        return Result.failed(ex.getMessage());
    }
});
```

**B. Wrap into an unchecked exception so the template rolls back and propagates:**

```java
tx.executeWithoutResult(status -> {
    try {
        callCodeThatThrowsIOException();
        saveData();
    } catch (IOException ex) {
        throw new UncheckedIOException(ex);
    }
});
```

These are illustrative snippets without concrete `Result`, `saveData`, or `callCodeThatThrowsIOException`; `java.io.IOException` and `java.io.UncheckedIOException` are needed. In the complete example in section 8, corresponding classes/methods are provided. **Do not** force every checked exception to roll back if the business contract actually wants to keep the data; decide from the invariant first.

### 5.4. What the Callback Can and Cannot Catch

```text
Caller -> tx.execute(...)
              |
              +-- manager.getTransaction(...)
              +-- callback START
              |     JDBC INSERT
              |     callback return
              +-- manager.commit(status)  <-- can fail here
              +-- callback scope finished
        <- execute returns or throws exception
```

`try/catch` **inside the callback** cannot catch an exception thrown by the transaction manager **after the callback returns**, such as a commit failure. Only `try/catch` **outside `execute(...)`** covers the entire corresponding begin/callback/commit/rollback path.

In a workflow that needs to report a "saved" status, place the decision **after `execute` returns** and outside any outer transaction that might own the physical transaction. If it fails right at commit and the connection is lost, the outcome may be indeterminate; do not assume rollback succeeded and retry blindly.

## 6. Do Not Confuse an Explicit Boundary with an Independent Physical Transaction

### 6.1. Default `PROPAGATION_REQUIRED` Can JOIN

`TransactionTemplate` uses `REQUIRED` propagation by default. Example:

```java
@Transactional
public void outer() {
    tx.executeWithoutResult(status -> {
        jdbc.update("INSERT INTO events(code) VALUES (?)", "inner");
    });
    throw new IllegalStateException("outer failure");
}
```

This snippet has assumed `tx`/`jdbc` fields, and the `outer` method must be called through a proxy. When the template participates in an existing outer transaction, `executeWithoutResult` returning **does not mean the inner INSERT committed independently**. `outer` throws an exception and the transaction owner rolls back -> the inner INSERT is also discarded.

```text
outer @Transactional(REQUIRED): physical transaction T
   +-- tx.execute(REQUIRED) -> JOIN T
       +-- INSERT 'inner'
       +-- execute returns (no physical commit)
   +-- outer throws
   +-- ROLLBACK T (discards 'inner')
```

This is why the statement "every `execute` creates its own transaction" is **false**.

### 6.2. When True Independence Is Needed, Use `REQUIRES_NEW`

```java
TransactionTemplate isolated = new TransactionTemplate(manager);
isolated.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRES_NEW);

outerTemplate.executeWithoutResult(outer -> {
    writeMainData();
    isolated.executeWithoutResult(inner -> writeIndependentAudit());
    outer.setRollbackOnly();
});
```

This is an illustrative pattern. If the manager/resource supports `REQUIRES_NEW`, the inner part uses physical transaction T2 and can commit independently, while outer T1 rolls back. However, T1 and T2 are **no longer atomic together**. Moreover, outer can still hold one connection while T2 needs another connection; the pool must be large enough to avoid deadlock/starvation when many threads do this concurrently.

**`REQUIRES_NEW` does not automatically mean "makes retry safe" or "persists audit permanently"**. The audit can still encounter errors, DB outages, or an uncertain commit outcome. If the audit/event must stay tightly coupled to the main transaction, transactional outbox is an important option to consider.

### 6.3. `NESTED` Is Not the Same as `REQUIRES_NEW`

If using `PROPAGATION_NESTED` with a JDBC manager/driver that supports savepoints, an inner rollback is usually a rollback **to a savepoint within the same physical transaction**, with no independent T2. When outer later rolls back, all changes in T, including the inner part that previously succeeded, can be discarded. With JPA, `JpaTransactionManager` does not support nested JPA semantics by default; a JDBC savepoint does not snapshot the JPA persistence context.

### 6.4. Template Can Be Called from a Private Method

Unlike `@Transactional` proxies, `TransactionTemplate` does not require the method containing the callback to be public or called through a Spring AOP proxy. However, this **does not** magically make arbitrary resources transaction-aware. `JdbcTemplate` still must use the same `DataSource`/transaction manager; `EntityManager`/JPA still needs an appropriate manager; async calls to another thread still require their own mechanism.

## 7. Designing Boundaries to Reduce Lock Time and Keep Outcomes Accurate

### 7.1. A Workflow with External I/O

**How not to do it when HTTP is slow and not part of the DB transaction:**

```java
@Transactional
public void importFromPartner() {
    PartnerResponse response = remoteClient.fetch(); // long network I/O
    repository.insert(response);
    remoteClient.acknowledge(response);              // cannot DB rollback
}
```

This is a hypothetical snippet, not a standalone program. The transaction can hold a connection/locks while waiting on the network, while the `acknowledge` response cannot be rolled back by the DB manager.

**Shorter explicit boundary approach:**

```java
public void importFromPartner() {
    PartnerResponse response = remoteClient.fetch(); // outside DB transaction

    tx.executeWithoutResult(status -> {
        repository.insert(response);
        repository.updateRelatedRows(response);
    });

    remoteClient.acknowledge(response);  // outside callback
}
```

Here the callback contains only DB work. If the template created a new transaction and `execute` returns normally, the DB transaction completes before sending `acknowledge`. **However, if `acknowledge` fails**, the committed DB records **do not automatically roll back**. If reliable post-commit event/notification delivery must be guaranteed, consider outbox + a retrying/idempotent dispatcher; do not send a message directly and call it "atomic".

### 7.2. Why Outbox Is Often Better Than Calling Email Sending Right After Commit?

```text
DB transaction:
    INSERT order
    INSERT outbox_event
    COMMIT
          |
          v
outbox dispatcher:
    read committed event
    send message (retry with idempotency)
    mark delivered
```

Saving the order and outbox record in the **same transaction** ensures both rows commit/rollback together. The dispatcher is a separate component with safe retries for effects outside the DB. While `TransactionTemplate` helps expose the DB boundary, it **does not replace outbox** when at-least-once delivery or an exactly-once business effect across systems is needed.

### 7.3. TransactionTemplate Is Not a Stopwatch

`setTimeout(10)` does not guarantee aborting every CPU-bound Java code block or `Thread.sleep(...)` after 10 seconds. Timeout can be honored differently by the manager, resource, or JDBC statement. For external I/O, use independent network client timeouts and do not hold a DB transaction across network calls unnecessarily.

### 7.4. A Callback Should Be Small, but Do Not Split an Invariant

Do not split every SQL statement into a separate `execute`:

```java
tx.executeWithoutResult(s -> insertOrder());
tx.executeWithoutResult(s -> reserveInventory());
```

If the business requires order and inventory to **succeed together or fail together**, the split above can commit the order before reserve fails. Better:

```java
tx.executeWithoutResult(s -> {
    insertOrder();
    reserveInventory();
});
```

These are illustrative snippets; the condition is sharing the same resource manager and appropriate propagation. "Short transaction" is not synonymous with "small transaction regardless of invariants".

## 8. Complete Java 17 + Spring Boot/JDBC/H2 Project

The following example uses **Spring Boot 3.3.5**, Spring JDBC, H2, and JUnit 5. It clearly demonstrates each point where `TransactionTemplate` adds value:

- returning the callback result after completion;
- `void` callback;
- runtime exception causing rollback;
- `setRollbackOnly()` for business rejection without throwing an exception;
- checked exception converted to a business result or wrapped unchecked;
- two separate transactions, retry/continue **after** rollback;
- `REQUIRES_NEW` committing audit independently of outer rollback;
- failure outside the callback **not** rolling back an already committed DB transaction;
- self-call still executing the template because it is a direct call, not proxy-based;
- reading transaction status inside and outside the callback;
- read-only template with dedicated settings.

### 8.1. File Structure

```text
visible-transaction-boundaries/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/boundary/
    │   │   ├── VisibleBoundaryApplication.java
    │   │   ├── EventStore.java
    │   │   └── BoundaryService.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/java/com/example/boundary/
        └── BoundaryServiceIntegrationTest.java
```

If generating the project from Spring Initializr, the Gradle Wrapper may already be included; if you create the exact files above manually, install Gradle or generate the wrapper first. The Java code consistently uses the `com.example.boundary` package.

`settings.gradle`:

```groovy
rootProject.name = 'visible-transaction-boundaries'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Use JDK 17+ with a Gradle version compatible with the Spring Boot plugin. `spring-boot-starter-jdbc` provides `JdbcTemplate`/transaction support; H2 is the in-memory database; JUnit 5 is provided by the Spring Boot test starter. Specific dependency versions are managed by Spring Boot dependency management.

### 8.2. Schema and Datasource

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:boundaries;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=5
spring.sql.init.mode=always
```

`src/main/resources/schema.sql`:

```sql
CREATE TABLE tx_events (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    event_key VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE audit_entries (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    audit_key VARCHAR(80) NOT NULL UNIQUE
);
```

Separating `tx_events` and `audit_entries` keeps the `REQUIRES_NEW` test from competing on the same row/unique key with outer T, avoiding unnecessary lock conflicts in the lesson. In a real application, committing audit independently may **not** match business requirements; see the earlier note.

### 8.3. Application with One Transaction Manager

`src/main/java/com/example/boundary/VisibleBoundaryApplication.java`:

```java
package com.example.boundary;

import javax.sql.DataSource;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBootApplication
public class VisibleBoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(VisibleBoundaryApplication.class, args);
    }

    @Bean("transactionManager")
    public PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
```

This sample **does not need `@EnableTransactionManagement` just to use TransactionTemplate**, because the boundary is invoked via direct API calls. There is one `PlatformTransactionManager` bound to one `DataSource`. Spring Boot auto-configures the datasource and `JdbcTemplate`; we provide an explicit transaction manager bean so we know exactly what the template uses.

If the application has multiple managers, you must inject the right manager/qualifier; do not pick a manager for JPA and then use `JdbcTemplate` on an unrelated datasource expecting the SQL to commit together.

### 8.4. Simple JDBC Repository

`src/main/java/com/example/boundary/EventStore.java`:

```java
package com.example.boundary;

import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class EventStore {
    private final JdbcTemplate jdbc;

    public EventStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void saveEvent(String key) {
        jdbc.update(
                "INSERT INTO tx_events(event_key) VALUES (?)", key);
    }

    public void saveAudit(String key) {
        jdbc.update(
                "INSERT INTO audit_entries(audit_key) VALUES (?)", key);
    }

    public List<String> eventKeys() {
        return jdbc.queryForList(
                "SELECT event_key FROM tx_events ORDER BY event_key",
                String.class);
    }

    public List<String> auditKeys() {
        return jdbc.queryForList(
                "SELECT audit_key FROM audit_entries ORDER BY audit_key",
                String.class);
    }

    public long eventCount() {
        Long result = jdbc.queryForObject(
                "SELECT COUNT(*) FROM tx_events", Long.class);
        return result;
    }

    public void clearAll() {
        jdbc.update("DELETE FROM audit_entries");
        jdbc.update("DELETE FROM tx_events");
    }
}
```

`EventStore` does not create transactions itself. When called inside a template callback, `JdbcTemplate` participates in the Spring-managed JDBC transaction on the same datasource. When tests call `clearAll()` outside a callback, each SQL statement uses an autocommit connection per the H2 fixture, letting tests prepare data independently of the service's transactions.

### 8.5. TransactionTemplate Configured Once in the Service

`src/main/java/com/example/boundary/BoundaryService.java`:

```java
package com.example.boundary;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class BoundaryService {
    private final EventStore store;
    private final TransactionTemplate required;
    private final TransactionTemplate independent;
    private final TransactionTemplate readOnly;

    public BoundaryService(
            PlatformTransactionManager transactionManager,
            EventStore store) {

        this.store = store;

        this.required = new TransactionTemplate(transactionManager);
        this.required.setName("visible-event-write");

        this.independent = new TransactionTemplate(transactionManager);
        this.independent.setName("independent-audit");
        this.independent.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW);

        this.readOnly = new TransactionTemplate(transactionManager);
        this.readOnly.setReadOnly(true);
        this.readOnly.setName("read-events");
    }

    public record Outcome(boolean accepted, String message) {
    }

    public record ScopeObservation(
            boolean activeInside,
            boolean activeAfter) {
    }

    public String saveAndReturn(String key) {
        return required.execute(status -> {
            store.saveEvent(key);
            return key;
        });
    }

    public void saveWithoutResult(String key) {
        required.executeWithoutResult(status -> {
            store.saveEvent(key);
        });
    }

    public void throwRuntimeAndRollback(String key) {
        required.executeWithoutResult(status -> {
            store.saveEvent(key);
            throw new IllegalStateException("Simulated business failure");
        });
    }

    public void markRollbackOnlyWithoutThrowing(String key) {
        required.executeWithoutResult(status -> {
            store.saveEvent(key);
            status.setRollbackOnly();
        });
    }

    public Outcome checkedFailureAsBusinessResult(String key) {
        return required.execute(status -> {
            store.saveEvent(key);
            try {
                checkedOperation();
                return new Outcome(true, "ACCEPTED");
            } catch (IOException ex) {
                status.setRollbackOnly();
                return new Outcome(false, "INPUT_ERROR");
            }
        });
    }

    public void wrapCheckedFailureAndRollback(String key) {
        required.executeWithoutResult(status -> {
            store.saveEvent(key);
            try {
                checkedOperation();
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        });
    }

    private static void checkedOperation() throws IOException {
        throw new IOException("Simulated checked I/O failure");
    }

    public void recoverAfterSeparateFailedTransaction() {
        try {
            required.executeWithoutResult(status -> {
                store.saveEvent("failed-step");
                throw new IllegalStateException("Step failed");
            });
        } catch (IllegalStateException expected) {
            // First transaction has already completed its rollback path.
        }

        required.executeWithoutResult(status -> {
            store.saveEvent("recovered");
        });
    }

    public void rollbackOuterButKeepIndependentAudit() {
        required.executeWithoutResult(outerStatus -> {
            store.saveEvent("outer");

            independent.executeWithoutResult(innerStatus -> {
                store.saveAudit("inner-audit");
            });

            outerStatus.setRollbackOnly();
        });
    }

    public void commitThenFailOutsideBoundary(String key) {
        required.executeWithoutResult(status -> {
            store.saveEvent(key);
        });

        // Runs AFTER the transaction callback has completed.
        // Simulates an external notification failure.
        throw new IllegalStateException("Notification failed after DB commit");
    }

    public boolean directThisCallStillRunsExplicitTemplate(String key) {
        return this.privateHelper(key);
    }

    private boolean privateHelper(String key) {
        return required.execute(status -> {
            store.saveEvent(key);
            return TransactionSynchronizationManager
                    .isActualTransactionActive();
        });
    }

    public long countWithReadOnlyTemplate() {
        return readOnly.execute(status -> store.eventCount());
    }

    public ScopeObservation observeBoundary(String key) {
        boolean activeInside = required.execute(status -> {
            store.saveEvent(key);
            return TransactionSynchronizationManager
                    .isActualTransactionActive();
        });

        boolean activeAfter = TransactionSynchronizationManager
                .isActualTransactionActive();

        return new ScopeObservation(activeInside, activeAfter);
    }

    public void processChunksWithIndependentCommits(List<String> keys) {
        for (String key : keys) {
            try {
                required.executeWithoutResult(status -> {
                    store.saveEvent(key);
                    if ("reject".equals(key)) {
                        throw new IllegalStateException("Bad chunk");
                    }
                });
            } catch (IllegalStateException expected) {
                // Example only of a policy allowing partial success.
                // Production needs error recording and idempotency keys.
            }
        }
    }
}
```

**Important points in this class:**

- `required` uses default `REQUIRED` propagation, with the injected manager; the transaction name is configured once in the constructor.
- `independent` is a **different template instance** with `REQUIRES_NEW`. Do not change propagation on a shared template between calls because of races if multiple requests use the same singleton service.
- `readOnly` is a separate template with the `readOnly=true` hint. This is a manager-dependent hint/setting, not a security permission strictly blocking every SQL write.
- `saveAndReturn` and `saveWithoutResult` can be used directly in ordinary code without needing a transaction proxy to intercept the method.
- `checkedOperation` intentionally throws checked `IOException`, so the callback catches it and **marks rollback-only** or wraps into `UncheckedIOException` so the template rolls back.
- `rollbackOuterButKeepIndependentAudit` demonstrates an **independent transaction**; do not use this if audit must roll back together with the order.
- `commitThenFailOutsideBoundary` illustrates an external side effect happening **after DB commit**, so the exception reaching the caller cannot undo the earlier DB transaction.
- `directThisCallStillRunsExplicitTemplate` proves that self-invocation is an issue of **annotation proxies**, not of direct `TransactionTemplate` calls.
- `processChunksWithIndependentCommits` is appropriate **only when** business rules allow partial results; a new transaction per chunk only happens when there is no outer enclosing transaction.

### 8.6. JUnit Integration Test: Observing the DB After the Boundary

`src/test/java/com/example/boundary/BoundaryServiceIntegrationTest.java`:

```java
package com.example.boundary;

import java.io.UncheckedIOException;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class BoundaryServiceIntegrationTest {
    @Autowired
    private BoundaryService service;

    @Autowired
    private EventStore store;

    @BeforeEach
    void reset() {
        store.clearAll();
    }

    @Test
    void executeReturnsAValueAfterItsTransactionScopeCompletes() {
        assertEquals("alpha", service.saveAndReturn("alpha"));
        assertEquals(List.of("alpha"), store.eventKeys());
        assertFalse(TransactionSynchronizationManager
                .isActualTransactionActive());
    }

    @Test
    void executeWithoutResultCommits() {
        service.saveWithoutResult("beta");

        assertEquals(List.of("beta"), store.eventKeys());
    }

    @Test
    void runtimeExceptionRollsBackAndReachesCaller() {
        assertThrows(IllegalStateException.class,
                () -> service.throwRuntimeAndRollback("runtime"));

        assertEquals(List.of(), store.eventKeys());
    }

    @Test
    void rollbackOnlyCanReturnWithoutThrowing() {
        service.markRollbackOnlyWithoutThrowing("rejected");

        assertEquals(List.of(), store.eventKeys());
    }

    @Test
    void checkedFailureCanReturnARejectedBusinessResult() {
        var outcome = service.checkedFailureAsBusinessResult("checked");

        assertFalse(outcome.accepted());
        assertEquals("INPUT_ERROR", outcome.message());
        assertEquals(List.of(), store.eventKeys());
    }

    @Test
    void wrappedCheckedExceptionTriggersRollback() {
        assertThrows(UncheckedIOException.class,
                () -> service.wrapCheckedFailureAndRollback("wrapped"));

        assertEquals(List.of(), store.eventKeys());
    }

    @Test
    void secondTransactionCanCommitAfterFirstRolledBack() {
        service.recoverAfterSeparateFailedTransaction();

        assertEquals(List.of("recovered"), store.eventKeys());
    }

    @Test
    void requiresNewAuditCanSurviveOuterRollback() {
        service.rollbackOuterButKeepIndependentAudit();

        assertEquals(List.of(), store.eventKeys());
        assertEquals(List.of("inner-audit"), store.auditKeys());
    }

    @Test
    void exceptionAfterExecuteDoesNotUndoEarlierCommit() {
        assertThrows(IllegalStateException.class,
                () -> service.commitThenFailOutsideBoundary("notified"));

        assertEquals(List.of("notified"), store.eventKeys());
    }

    @Test
    void callingPrivateHelperStillUsesTemplateBoundary() {
        assertTrue(service.directThisCallStillRunsExplicitTemplate("direct"));

        assertEquals(List.of("direct"), store.eventKeys());
    }

    @Test
    void readOnlyTemplateCanRead() {
        service.saveWithoutResult("a");
        service.saveWithoutResult("b");

        assertEquals(2L, service.countWithReadOnlyTemplate());
        assertEquals(List.of("a", "b"), store.eventKeys());
    }

    @Test
    void transactionContextIsActiveOnlyInsideCallbackInThisFixture() {
        var observation = service.observeBoundary("seen");

        assertTrue(observation.activeInside());
        assertFalse(observation.activeAfter());
        assertEquals(List.of("seen"), store.eventKeys());
    }

    @Test
    void chunkFailureDoesNotUndoPreviousOrLaterCommittedChunk() {
        service.processChunksWithIndependentCommits(
                List.of("first", "reject", "third"));

        assertEquals(List.of("first", "third"), store.eventKeys());
    }
}
```

**There are 13 integration tests**, each with a `@BeforeEach` clearing both tables. Do not place `@Transactional` on the test class itself; if you do, `REQUIRED` callbacks can join the test-managed transaction and not physically commit right at `execute`, causing the test to read data inside the same transaction and misinterpret the outcome.

### 8.7. How to Run?

In the `visible-transaction-boundaries` directory, with the Gradle Wrapper:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

If you created the files yourself without a wrapper yet, use an installed compatible Gradle to generate the wrapper or run `gradle test`. Do not run `javac` directly without adding Spring/JUnit/H2 to the classpath.

**Expected result:** 13 tests pass in the Spring Boot 3.3.5 + JDBC/H2 fixture. This is the expected outcome predicted from the code and transaction semantics; there is no claim that the tests were executed here. JUnit does not guarantee method order or fixed stdout. Read the report at `build/reports/tests/test/index.html` when running it for real.

| Scenario | Caller outcome | Data after service returns/throws |
| --- | --- | --- |
| `saveAndReturn("alpha")` | Returns `alpha` | Event `alpha` exists |
| `saveWithoutResult("beta")` | Returns normally | Event `beta` exists |
| `throwRuntimeAndRollback` | `IllegalStateException` | No events |
| `markRollbackOnlyWithoutThrowing` | Returns normally | No events |
| Checked failure → business result | `Outcome(false,"INPUT_ERROR")` | No events |
| Checked failure → wrapped unchecked | `UncheckedIOException` | No events |
| Step 1 rollback, step 2 new transaction | Returns normally | Only `recovered` |
| Outer rollback; `REQUIRES_NEW` audit commit | Returns normally | Events empty, audit `inner-audit` exists |
| DB commit then notification fails | `IllegalStateException` | Event `notified` **still exists** |
| Direct private-helper call | Returns `true` for active transaction | Event `direct` exists |
| Read-only template | Returns count `2` | Events `a`, `b` |
| Observe inside/after | `activeInside=true`, `activeAfter=false` | Event `seen` exists |
| Middle chunk fails | Returns normally per sample policy | Only `first`, `third` |

**Why is this result meaningful?** The test calls the service **through the Spring bean** and only queries the DB via the repository after the service method returns/throws. The methods are not inside an outer `@Transactional`, so `REQUIRED` callbacks create separate actual physical transactions, while the `REQUIRES_NEW` audit is truly independent of the outer template. From there, the test distinguishes method-body return, callback return, manager completion, and external failure.

## 9. Handling Exceptions Properly at Boundaries

### 9.1. Catching Outside `execute` When Converting Transaction Failure to a Domain Result

```java
public BookingResult tryBook(BookingCommand command) {
    try {
        return tx.execute(status -> {
            insertBooking(command);
            return BookingResult.confirmed();
        });
    } catch (DuplicateKeyException ex) {
        return BookingResult.seatAlreadyTaken();
    }
}
```

This is an illustrative snippet, requiring corresponding classes/vars and imports. It places the catch **after the `execute` scope**: if the JDBC INSERT throws `DuplicateKeyException`, Spring puts the transaction through the rollback path before the caller catches. **However**, only map a genuine duplicate of the right business constraint to `seatAlreadyTaken`; do not catch every `DataIntegrityViolationException` and conclude a seat conflict.

If the method calls the snippet above **inside an active outer transaction**, `tx.execute(REQUIRED)` only joins the outer physical transaction. Catching the exception outside the inner `execute` does not mean the outer transaction owner has rolled back; if the inner side marked rollback-only, the outer side can encounter `UnexpectedRollbackException`. Check the actual transaction scope.

### 9.2. Rollback-Only Return Is a Different Outcome from an Exception

```java
Decision decision = tx.execute(status -> {
    if (!policyAllows()) {
        status.setRollbackOnly();
        return Decision.REJECTED;
    }
    insertAcceptedRecord();
    return Decision.ACCEPTED;
});
```

This is an illustrative snippet. If the business contract uses a result type instead of an exception, the caller must check `Decision`. A successful Java return from `execute` **does not prove a write happened**, because the callback may have proactively marked rollback-only. Only a clear result avoids "returning success while the transaction rolled back".

### 9.3. Checked Exceptions from Callbacks

`TransactionCallback<T>.doInTransaction` does not declare `throws IOException`. Therefore, you cannot throw a checked `IOException` directly from a Java lambda unless you catch/wrap/convert it into an unchecked exception type. `UncheckedIOException` is the standard choice for `IOException`; for other checked business exceptions, consider a domain-specific runtime wrapper, a business result, or a dedicated adapter.

If you want to use declarative `rollbackFor=SomeCheckedException.class` because the public API already declares checked exceptions, `@Transactional` can express that contract more naturally.

### 9.4. Do Not Perform Side Effects Inside a Callback Expecting Them to Roll Back

```java
tx.executeWithoutResult(status -> {
    repository.saveOrder();
    emailSender.sendConfirmation(); // NOT inside the DB transaction
});
```

Hypothetical snippet. If the email is sent and then `commit` fails, the database has no order while the recipient already received the email. Even if the email was called "before the callback returns", the DB manager still does not control email. Outbox/saga/compensation/idempotency are needed as required.

### 9.5. Be Careful with Errors at Commit

If the connection drops at the exact moment of commit, the DB may have received the commit while the application receives an exception. Do not manually call rollback again on an already completed status or retry non-idempotent payment creation. For multi-step transactions, record a business key and use a reconciliation mechanism before retrying.

## 10. How to Test and Debug Boundaries

### 10.1. Checking Active Transactions at the Right Phase

Inside an imperative callback:

```java
boolean inside = tx.execute(status ->
        TransactionSynchronizationManager.isActualTransactionActive());
```

Outside the callback:

```java
boolean after =
        TransactionSynchronizationManager.isActualTransactionActive();
```

These are snippets when `tx` is available. In a fixture **with no outer transaction**, `inside` is usually `true` and `after` is `false`. If there is an outer `REQUIRED`, `after` may still be `true`; do not use a single observation to declare that the DB has committed.

### 10.2. Distinguishing Three Points in Time

```text
A — Callback returns
B — TransactionTemplate.execute returns to caller
C — Owner's physical transaction commits

If the template creates the physical transaction:
    A -> commit/cleanup -> B; C occurs along the path between A and B.

If the template JOINs an outer REQUIRED:
    A -> inner logical scope completion -> B -> ... -> C (later)
```

In practice, if the manager reports an error at `commit`, B will not be a successful return and may throw an exception. If the callback marks rollback-only, B may return normally after rollback depending on status/manager. Therefore, do not confuse **A, B, and C**.

### 10.3. Observation Checklist

1. Which transaction manager bean is injected into the template?
2. Is the `execute` call inside an outer `@Transactional`?
3. Is propagation `REQUIRED` or `REQUIRES_NEW`?
4. Measure scope using `status.isNewTransaction()` and appropriate logs/resources, not just method names.
5. Is the SQL using the exact datasource/connection managed by the manager?
6. Does an exception escape the callback or get caught inside? Is `setRollbackOnly` called?
7. Was a shared transaction marked global rollback-only by another participant?
8. Did the commit/rollback path actually complete before the caller used the result?
9. Are data measurements performed **after the boundary**, rather than only from the persistence context/test transaction?
10. Are there side effects outside the database requiring outbox/idempotency?

In test/development, you can enable:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
```

Logs are helpful for diagnostic direction, though wording/ordering varies by framework/manager. Do not rely on a single log line like "Committing" to assert database durability; readback after the boundary is more important. Avoid logging parameters containing sensitive information.

## 11. Common Mistakes When Using TransactionTemplate

1. **Assuming callback return means commit.** The transaction manager still has to run completion after the callback; if there is an outer transaction, the physical commit may come later.
2. **Assuming every `execute` creates a new transaction.** `REQUIRED` will join an existing transaction.
3. **Assuming `setRollbackOnly()` always throws an exception.** With an owner transaction, it can roll back and return normally.
4. **Assuming catching an exception inside the callback recovers the transaction.** The DB/ORM may already be in an aborted/rollback-only state.
5. **Wrapping a template around remote API/network calls.** It cannot roll back external side effects and increases lock/connection hold time.
6. **Splitting two SQL operations belonging to the same invariant into two template calls.** Loses atomicity if the two calls commit independently.
7. **Changing propagation of a singleton template per request.** Shared mutable configuration causes races; create fixed instances for different policies.
8. **Using `TransactionTemplate` in a Reactor pipeline in place of reactive transactions.** Imperative ThreadLocal does not cover publisher lifecycles; use `TransactionalOperator`.
9. **Thinking `readOnly=true` forbids writes like an ACL.** It is a hint that managers/drivers/DBs may optimize or enforce differently.
10. **Thinking `timeout=5` aborts any CPU computation/HTTP call at exactly 5 seconds.** Timeout depends on the resource and manager; separate network timeouts are needed.
11. **Thinking the template solves self-invocation for annotations on other methods.** It only creates a boundary for the invoked **callback**; other `@Transactional` methods still need a proxy.
12. **Catching any integrity exception and returning success.** You must distinguish constraint/tenant/idempotency cases and not ignore unexpected infrastructure errors.
13. **Using `REQUIRES_NEW` for audit without checking the pool.** Outer holds a resource while inner needs another connection; starvation can happen.
14. **Thinking a callback can throw a checked exception without catching it.** The Java signature of `TransactionCallback` does not allow that.
15. **Calling `new TransactionTemplate()` and forgetting the manager.** The template needs a `PlatformTransactionManager` configured before `execute`.
16. **Enabling transactions at the repository level without a business-level boundary.** Multiple repository calls can commit piecemeal, breaking invariants.
17. **Reading state inside a `@Transactional` test and calling it committed.** A test-managed transaction may roll back at the end of the test.
18. **Assuming that if calling execute succeeds then external notification is guaranteed to succeed.** That is a separate step; design an appropriate outbox/delivery mechanism.

## 12. Quick Decision Table

| Flow requirement | Approach to consider | Reason |
| --- | --- | --- |
| A service method doing a single atomic DB unit | `@Transactional` | Clear, minimal framework coupling in the body |
| Long method with network/file work, only a DB block needs atomicity | `TransactionTemplate` | Short and explicit boundary |
| A few update points needing transactions in a low-transaction app | `TransactionTemplate` | Less proxy/annotation structural overhead |
| Thousands of items processed in chunks, partial success is valid | Multiple `execute` calls with checkpoint/idempotency | Separates units of work |
| Independent step inside an outer transaction | `REQUIRES_NEW` with a clearly designed template/annotation | Different physical transaction, suitable pool |
| Need a savepoint for partial rollback in JDBC | `NESTED` on a supporting manager/DB | Not identical to `REQUIRES_NEW` |
| Need rollback due to a business result without throwing an error | `TransactionStatus.setRollbackOnly()` | Explicit decision, clear outcome type |
| Need atomic DB + message delivery | DB transaction + transactional outbox | Cannot roll back HTTP/email/Kafka via JDBC |
| Need transaction management with reactive resources | `TransactionalOperator` | Reactive/Context lifecycle |
| Many services needing uniform semantics | `@Transactional` and transaction infrastructure | Separates boilerplate from business code |
| Need different config per request | Create dedicated templates per policy, do not mutate shared singleton | Avoids races |
| Multiple databases needing global atomicity | Appropriate transaction coordination or workflow/saga | Not an inherent capability of the template |

## 13. Self-Check Questions

**1. When should you use TransactionTemplate instead of placing `@Transactional` on the entire method?**

When only a small section of a workflow needs a transaction, there is non-DB I/O that should not hold connections/locks, or multiple boundaries with explicit policies are needed. If the method is already a single atomic unit, the annotation is usually easier to read.

**2. Does `tx.execute(...)` always commit the DB when it returns?**

No. If `REQUIRED` joins an outer transaction, the physical commit still waits for the outer owner. If the callback calls `setRollbackOnly()`, the template can return normally after rollback. If a commit error occurs, `execute` may throw an exception.

**3. Does TransactionTemplate solve self-invocation?**

It does not use a proxy for the callback call itself, so calling `tx.execute` from a private/helper method still creates a transaction scope. However, it does not make other `@Transactional` methods automatically intercepted when called via `this`.

**4. Why should you catch exceptions outside `execute` when wanting to try a new transaction after a failure?**

Because the manager has already had the chance to roll back/clean up the failed scope before code handles it and starts a new scope. Catching a SQL error right inside the callback and continuing can leave the resource aborted or rollback-only.

**5. Can a Java `TransactionCallback` lambda throw a checked IOException directly?**

Not under the standard callback signature. You must catch it and decide on rollback-only/result or wrap it into an unchecked exception such as `UncheckedIOException`.

**6. Is `status.setRollbackOnly()` the same as throwing `RuntimeException`?**

Not in terms of API and control flow: both can lead to rollback, but `setRollbackOnly` can return normally and the caller must inspect an explicit business result.

**7. If `REQUIRES_NEW` is used to write an audit and the outer transaction rolls back, what happens to the audit?**

If the independent inner transaction commits successfully, the audit can remain even when the outer rolls back. This changes atomicity and is unsuitable if the audit must belong to the same business unit.

**8. Why is `remoteClient.send` after `tx.execute` not guaranteed by the DB transaction?**

Because a network call does not participate in a local JDBC transaction. If sending fails, the DB may already have committed; if reliable delivery is needed, an outbox/idempotent dispatcher or suitable integration mechanism is required.

**9. Why shouldn't you use a single template instance and set readOnly/propagation per request?**

The template holds mutable configuration in a shared singleton object; multiple threads can race to change the config. Use instances configured once.

**10. Are read-only and timeout on the template hard guarantees?**

No. They depend on the resource manager/DB, propagation, and statement processing. Read-only is not authorization, and timeout is not a general CPU/HTTP circuit breaker.

**11. An import has 3 chunks; chunk 1 commits, chunk 2 fails, chunk 3 commits. Is that an atomicity bug?**

It depends on the invariant. If the business allows partial success and retry/checkpoint, it can be a valid design. If all-or-nothing is required, all three must be placed in one transaction; splitting into multiple `execute` calls is wrong.

**12. What technique verifies a boundary more strongly than looking at a 'commit' log?**

An integration test calling the service outside a test-managed transaction and querying the DB after `execute` completes, while also checking exceptions/outcomes/rollback-only against the contract.

## 14. Official References

- [Spring Framework — Programmatic Transaction Management (TransactionTemplate and TransactionalOperator)](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring Framework — Choosing Between Programmatic and Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-decl-vs-prog.html)
- [Spring Framework — TransactionTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html)
- [Spring Framework — TransactionOperations Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/TransactionOperations.html)
- [Spring Framework — DefaultTransactionDefinition Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/DefaultTransactionDefinition.html)
- [Spring Framework — TransactionStatus Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/TransactionStatus.html)
- [Spring Framework — Transaction Propagation: REQUIRED, REQUIRES_NEW, NESTED](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — Test-managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
