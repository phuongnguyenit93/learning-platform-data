# Why TransactionTemplate Is Usually Chosen Over Manual Management Code

## 1. Short Answer: Keep Transaction Control, Eliminate Error-Prone Code

When you need direct transaction control in an **imperative** Spring application, you have at least two choices:

1. **Use `PlatformTransactionManager` directly**: call `getTransaction(...)` to obtain `TransactionStatus`, choose where to call `commit(...)` or `rollback(...)` yourself, and handle errors occurring in business code, during rollback, and at the commit boundary.
2. **Use `TransactionTemplate`**: provide a callback describing the work to wrap in a transaction; the template takes care of calling the transaction manager along the proper lifecycle, rolling back on runtime exceptions/`Error`, and committing when the callback finishes normally.

Spring Framework **generally recommends `TransactionTemplate` for programmatic transaction management in imperative code**. For reactive code, Spring recommends `TransactionalOperator`; additionally, when an entire service method already forms a clear unit of work, declarative `@Transactional` is often even more suitable than either programmatic approach.

Example of both styles achieving the same goal of "write two records and commit together":

**Manual management:**

```java
DefaultTransactionDefinition definition =
        new DefaultTransactionDefinition();
TransactionStatus status = manager.getTransaction(definition);

try {
    repository.insertOrder(order);
    repository.insertOrderLines(order);
} catch (RuntimeException | Error failure) {
    manager.rollback(status);
    throw failure;
}

manager.commit(status);
```

The snippet above is **illustrative only**: `manager`, `repository`, and `order` must be declared. It omits preserving the original exception if `rollback` also fails, and does not yet show a policy for checked exceptions. It illustrates the length and number of control-flow branches you must take responsibility for.

**Using TransactionTemplate:**

```java
TransactionTemplate template = new TransactionTemplate(manager);

template.executeWithoutResult(status -> {
    repository.insertOrder(order);
    repository.insertOrderLines(order);
});
```

This still needs `manager`/`repository`/`order` and runs inside a real Spring application. Yet the transaction code focuses on the **business unit of work**, without repeating acquire/rollback/commit calls everywhere.

The answer is not that "TransactionTemplate has safer transactions because of some new transaction type". Both can use the **exact same `PlatformTransactionManager`, `DataSource`, propagation, isolation, read-only, timeout**, and ultimately the same database transaction mechanism. The value of the template lies in **encapsulating a procedure that is notoriously error-prone on exception paths**, keeping boundaries clear, code concise, policies consistent, and testing straightforward.

This lesson covers **Direct Transaction API → Why `TransactionTemplate` Is Usually Chosen Over Manual Management Code**. We will start from the low-level API, compare step by step, analyze common bugs, practice with Java 17+/Spring Boot/JDBC/H2, and identify cases where the template should not be used.

## 2. Three Core Components of Programmatic Transactions

### 2.1. `PlatformTransactionManager`

`PlatformTransactionManager` is the interface coordinating imperative transactions in Spring:

```java
TransactionStatus getTransaction(TransactionDefinition definition);
void commit(TransactionStatus status);
void rollback(TransactionStatus status);
```

These three signatures are **API shape excerpts for learning**, not a new Java interface to declare. Common implementations:

- `DataSourceTransactionManager`/`JdbcTransactionManager`: local transaction for a JDBC `DataSource`.
- `JpaTransactionManager`: transaction for an `EntityManagerFactory`, handling JPA resources/lifecycle.
- `JtaTransactionManager`: transactions managed by JTA infrastructure.
- Custom manager: can add behavior for dedicated resources.

`getTransaction` does not mean "always create a new physical transaction". With `PROPAGATION_REQUIRED`, if a compatible transaction already exists, the manager can return a **participating logical status**. Calling `commit(status)` on a participating scope does not necessarily commit the physical transaction either; the outer owner decides final completion.

### 2.2. `TransactionDefinition`

`TransactionDefinition` is the contract describing propagation, isolation, timeout, read-only, and name. `DefaultTransactionDefinition` is a mutable implementation for configuring the request:

```java
DefaultTransactionDefinition definition =
        new DefaultTransactionDefinition();

definition.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRED);
definition.setIsolationLevel(
        TransactionDefinition.ISOLATION_DEFAULT);
definition.setTimeout(TransactionDefinition.TIMEOUT_DEFAULT);
definition.setReadOnly(false);
definition.setName("create-order");
```

The values in the snippet represent common default behavior. **Name is metadata** for the manager/monitoring; it does not guarantee naming the database transaction across all engines. Timeout/isolation/read-only also depend on the manager and resources. When joining an outer transaction, physical characteristics are usually governed by the outer owner.

### 2.3. `TransactionStatus`

`TransactionStatus` represents the status of **one transaction manager call**:

```java
TransactionStatus status = manager.getTransaction(definition);

boolean isNew = status.isNewTransaction();
boolean rollbackOnly = status.isRollbackOnly();
boolean completed = status.isCompleted();

status.setRollbackOnly();
```

This snippet uses the variables configured above. `status.setRollbackOnly()` requests that the transaction not commit under manager semantics; it does **not** immediately execute a physical `rollback` at that line in all cases. `isCompleted()` is not a way to recover or reuse a status. After `commit`/`rollback`, never "reuse" a status to commit a second time.

### 2.4. Where Does `TransactionTemplate` Fit?

`TransactionTemplate` is an **execution wrapper** built on these three concepts, not a replacement for the manager:

```text
Business service
     |
     +--- TransactionTemplate.execute(callback)
             |
             +--- manager.getTransaction(definition)
             |       -> TransactionStatus
             |
             +--- callback.doInTransaction(status)
             |       -> JDBC / JPA application code
             |
             +--- manager.commit(status) OR manager.rollback(status)
             |       -> manager handles resources and completion
             |
             +--- return value OR propagate failure
```

The template extends `DefaultTransactionDefinition`, so the template instance itself holds propagation/isolation/timeout/readOnly/name settings. You can configure it once in a constructor or as a Spring bean and reuse it.

## 3. Why Is Manual Management Error-Prone?

A transaction is not merely "try then commit, catch then rollback". There are multiple exit paths and multiple kinds of failures.

### 3.1. Forgetting Rollback on a RuntimeException

Incorrect example:

```java
TransactionStatus status = manager.getTransaction(definition);
repository.insertA();
repository.insertB();    // throws RuntimeException here
manager.commit(status);
```

If business code throws before `commit`, the thread exits the method without properly completing the status. Depending on the manager, resources may remain held/bound to the thread or leave the transaction lifecycle in a broken state. Do not use this pattern.

**`TransactionTemplate` automatically takes the rollback path when the callback throws a RuntimeException or Error**, keeping application code focused on the transactional work.

### 3.2. Catching Only `Exception` and Forgetting `Error`

Incomplete example:

```java
try {
    performWork();
} catch (Exception ex) {
    manager.rollback(status);
    throw ex;
}
```

`Error` does not inherit from `Exception`. The template handles `RuntimeException | Error` escaping the callback to request rollback. In manual code, catching `Exception` misses `OutOfMemoryError`, `AssertionError`, and other `Error`s. Even though not every `Error` is recoverable, omitting the cleanup/rollback path is a lifecycle gap.

Do not write `catch (Throwable)` and blindly swallow all errors; if you handle `Error`, propagate it and let the infrastructure preserve proper semantics.

### 3.3. Calling Rollback Twice or Calling Rollback After Commit

An easily confused pattern:

```java
try {
    doBusinessWork();
    manager.commit(status);
} catch (RuntimeException failure) {
    manager.rollback(status);
    throw failure;
}
```

This snippet is **not a proper pattern**. If `commit(status)` throws an exception **after the manager has already completed/cleaned up the transaction**, the catch block may go on to call `rollback` on an already completed status, throwing a second exception that masks the real failure. "Commit threw" is not proof the transaction did not commit; the outcome may be indeterminate if the connection dropped right at commit time.

A less error-prone manual approach separates **exceptions from the business body** and **exceptions from commit**:

```java
TransactionStatus status = manager.getTransaction(definition);
Result result;

try {
    result = performBusinessWork();
} catch (RuntimeException | Error businessFailure) {
    manager.rollback(status);
    throw businessFailure;
}

// Commit sits outside the catch handling business errors.
manager.commit(status);
return result;
```

Still an illustrative snippet. It lacks a checked-exception policy and preservation of the original failure if rollback also fails. `TransactionTemplate` already solves most of that boilerplate so call sites do not have to repeat it.

### 3.4. Rollback Can Fail Too

Suppose business logic throws `IllegalStateException`, yet during rollback the connection drops and the transaction manager throws `TransactionSystemException`. Which one gets propagated? How do you preserve context of the business failure?

In `TransactionTemplate`'s implementation, Spring handles rollback failures and has a mechanism to record the original exception on `TransactionSystemException`; another rollback failure may replace the original exception while logging it. Manual code frequently overlooks this.

If writing a helper yourself, at minimum avoid needlessly losing context:

```java
try {
    manager.rollback(status);
} catch (RuntimeException | Error rollbackFailure) {
    if (rollbackFailure != businessFailure) {
        rollbackFailure.addSuppressed(businessFailure);
    }
    throw rollbackFailure;
}
throw businessFailure;
```

This snippet belongs to the **catch branch of a manual transaction**, not standalone; it requires `businessFailure` and `status` in scope. It is not a full replica of every Spring edge case, only illustrating the duty to preserve exceptions when rollback encounters a further error.

### 3.5. Misconfiguring and Confusing Logical vs. Physical Transactions

Manual code can misuse `TransactionDefinition`, for example leaving default `REQUIRED` while a developer assumes every `getTransaction` creates an independent transaction. The template does not change that underlying behavior, yet when the policy is declared once on a template instance, call sites are far more likely to share the same configuration and are easier to review.

### 3.6. Writing Inconsistent Versions of Boilerplate

A team with 20 services hand-writing `getTransaction`/`commit`/`rollback` can end up with 20 different exception-handling styles:

- Some services catch RuntimeException yet miss Error.
- Some services roll back in `finally` even when commit succeeded.
- Some services swallow DataAccessException.
- Some services acquire JDBC connections outside the manager.
- Some services forget to handle checked exceptions.
- Some services retry an already completed transaction.
- Some services commit and return results before ensuring callbacks finished.

Using a template for use cases needing programmatic transactions establishes a shared control model, cutting copy/paste bugs and making business code easier to read and test.

## 4. How TransactionTemplate Handles Callbacks and Errors

### 4.1. Normal Return

```java
String code = template.execute(status -> {
    store.insert("E-01");
    return "E-01";
});
```

This is an illustrative snippet with `template` and `store` available. Flow:

1. Template calls manager to obtain `TransactionStatus`.
2. Callback runs and returns `"E-01"`.
3. Template invokes the completion path `manager.commit(status)`.
4. If manager completion succeeds, `execute` returns the result to the caller.

**Warning:** with `PROPAGATION_REQUIRED` participating in an outer transaction, `commit(status)` may complete only the **logical scope**, while physical commit is performed later by the outer owner. There is also the case where the callback calls `status.setRollbackOnly()` and returns normally: the manager rolls back, yet `execute` can still return a normal value. Therefore, a return value from the callback does not mean "the DB definitely has the data" in every situation.

### 4.2. RuntimeException or Error Escaping the Callback

```java
template.executeWithoutResult(status -> {
    store.insert("E-02");
    throw new IllegalStateException("Cannot finish");
});
```

The template requests rollback per manager semantics and propagates the exception, unless rollback itself fails and raises a corresponding transaction-system exception. `AssertionError` and other `Error`s escaping the callback also trigger rollback handling.

Do not equate "rollback was requested" with "rollback definitely succeeded across every outage"; distinguish Spring's decision from the DB outcome.

### 4.3. Checked Exceptions from `TransactionCallback`

`TransactionCallback<T>.doInTransaction(TransactionStatus)` **does not declare checked exceptions**. A standard Java lambda cannot directly `throw new IOException(...)` from that callback. Two proper approaches:

**Convert to unchecked so the template rolls back and propagates:**

```java
template.executeWithoutResult(status -> {
    store.insert("E-03");
    try {
        readExternalFile();
    } catch (IOException ex) {
        throw new UncheckedIOException(ex);
    }
});
```

**Or catch the checked exception, mark rollback-only, and return a business result:**

```java
Result outcome = template.execute(status -> {
    store.insert("E-03");
    try {
        readExternalFile();
        return Result.success();
    } catch (IOException ex) {
        status.setRollbackOnly();
        return Result.failed("INPUT_UNAVAILABLE");
    }
});
```

These two snippets are illustrative only: `Result`, `store`, and `readExternalFile` are hypothetical APIs requiring appropriate Java imports. If the business wants to commit despite a checked exception, express that decision clearly via result/policy; do not assume "commit on checked exceptions" as with traditional `@Transactional`.

With a manual manager, code using `Callable<T>.call() throws Exception` can let real checked exceptions escape. In that case, however, **the author of the manual code must decide the rollback/commit policy** for each type, rather than having an automatic fallback rollback rule for `Callable`.

### 4.4. Actively Rolling Back Without Throwing an Exception

```java
Decision decision = template.execute(status -> {
    store.insert("draft");
    if (!canAccept()) {
        status.setRollbackOnly();
        return Decision.REJECTED;
    }
    return Decision.ACCEPTED;
});
```

If the template owns the transaction, calling `setRollbackOnly` on the status can trigger a rollback while `execute` returns normally, especially when rollback is an intentional decision by the owner. This works well with domain result types, provided it is crystal clear that `Decision.REJECTED` does **not** mean "saved and committed".

If the template is only joining an outer `REQUIRED`, marking rollback-only can cause the outer physical transaction to roll back later; the outer owner may receive `UnexpectedRollbackException`. Even when using a template, rollback-only **is not a flag that can be cleared** by catching or returning normally.

### 4.5. Commit Failure Occurring After the Callback

A point often missed in code reviews:

```text
caller -> template.execute(...)
          ├── getTransaction()
          ├── callback -> return Result
          ├── manager.commit(status)   <-- can still fail
          └── execute returns Result   <-- only when completion path succeeds
```

A `try/catch` **inside the callback** cannot catch errors occurring **after the callback returns** during manager commit. If you want to map commit errors to an API error or perform reconciliation, wrap `try/catch` around **`template.execute(...)` at the caller**. Yet do not treat every exception from `commit` as proof the database rolled back; with certain network/connection errors, the outcome may be indeterminate.

## 5. Side-by-Side Comparison: Correct Manual Code vs. Equivalent Template

Suppose a use case inserts both an order and an audit row in the same transaction; the invariant is **both succeed together or both roll back together**.

### 5.1. Minimal Manual Approach Handling RuntimeException/Error

```java
public String createManually(String key) {
    DefaultTransactionDefinition def = new DefaultTransactionDefinition();
    def.setName("create-manual");
    def.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);

    TransactionStatus status = manager.getTransaction(def);
    String result;
    try {
        store.insertEvent(key);
        store.insertAudit("AUDIT-" + key);
        result = key;
    } catch (RuntimeException | Error businessFailure) {
        manager.rollback(status);
        throw businessFailure;
    }

    manager.commit(status);
    return result;
}
```

The code here is an **illustrative method**, needing fields `manager`, `store`, and imports. If rollback also fails, exception handling still needs to preserve context. To support checked exceptions, catch the appropriate exceptions and declare `throws`. If commit fails, handle it outside the boundary without unconditionally rolling back an already completed status.

### 5.2. Template Approach

```java
public String createWithTemplate(String key) {
    return template.execute(status -> {
        store.insertEvent(key);
        store.insertAudit("AUDIT-" + key);
        return key;
    });
}
```

This eliminates transaction boilerplate while keeping business-related DB operations inside the same callback. If a custom policy is needed, configure the template once in a constructor/bean and share it. When there are many similar methods, the cumulative benefit is substantial.

### 5.3. Responsibility Matrix

| Responsibility | Manual manager usage | TransactionTemplate |
| --- | --- | --- |
| Choose manager & propagation | Developer | Developer configures template |
| Create/get `TransactionStatus` | Call directly everywhere | Template calls |
| Run business code | Call directly | Callback |
| Commit on normal business return | Call manually in the right place | Template calls |
| Roll back on runtime exception | Catch and call manually | Template handles |
| Roll back on `Error` | Remember to catch appropriately | Template handles |
| Checked exceptions | Choose policy/catch/rethrow yourself | Callback must catch/wrap/mark rollback-only |
| Rollback failure handling | Handle precedence/context yourself | Template has standard mechanism |
| Manager completion and cleanup | Call manager exactly once yourself | Template coordinates manager |
| Physical commit when joining outer `REQUIRED` | Waits for outer owner | **Still** waits for outer owner |
| Business invariants, SQL locking, idempotency | Developer | **Still** developer's responsibility |

**Important point:** `TransactionTemplate` does not guarantee that **every kind of failure** or every resource is rolled back. It simply wraps interactions with the transaction manager and callback within the corresponding context; DB semantics, deadlocks, networking, external I/O, propagation, and resource state still matter.

## 6. Comparison with `@Transactional`: Do Not Misread Spring's Advice

Spring generally recommends `TransactionTemplate` **once you have chosen programmatic transaction management**, not as a claim that templates are always better than `@Transactional`.

| Need | Common fit | Reason |
| --- | --- | --- |
| One public service method = one atomic unit | `@Transactional` | Less API coupling in the body, easy to declare |
| A short DB segment amid long file/HTTP work | `TransactionTemplate` | Callback boundary highlights the exact segment |
| Multiple chunked transactions, partial success valid | Template or multiple service boundaries | Explicitly separates each unit |
| Need to roll back based on result without throwing | Template + `status.setRollbackOnly()` or explicit domain design | Decide directly in code |
| Need a new transaction from a private/helper method | Template or refactor service proxy | Template does not depend on self-invocation |
| Fully reactive code with Reactor | `TransactionalOperator` | Different reactive context/lifecycle |
| Many business methods sharing the same policy | `@Transactional` | Reduces boilerplate and coupling |
| Ultra-low-level control over the manager | Direct `PlatformTransactionManager` | Use only when abstractions fall short |

### 6.1. No Self-Invocation Issue for the Template Call Itself

In Spring proxy mode, `this.innerTransactionalMethod()` can bypass advice on an annotation placed on the inner method. By contrast:

```java
private void persistOne(String key) {
    template.executeWithoutResult(status -> store.insertEvent(key));
}
```

still runs the template normally, even when called via `this.persistOne(...)`. `execute` is a direct Java API call; it does not require intercepting the enclosing method. However, that does not make other `@Transactional` annotations run during self-invocation.

### 6.2. Template Increases Coupling to Spring

`TransactionTemplate` is a class in `org.springframework.transaction.support`. Injecting it into every domain entity couples the domain model tightly to Spring. Keep templates in the **application service/orchestrator/infrastructure adapter**, where units of work are defined, and call plain-Java domain logic from the callback. That balances lifecycle-management benefits with a testable architecture.

## 7. Propagation, Timeout, Isolation, and Thread Safety

### 7.1. `REQUIRED` Still Joins an Outer Transaction

`TransactionTemplate` defaults to `REQUIRED` propagation. If no outer transaction exists, it usually opens a new physical transaction; if an outer exists, it joins:

```text
outer @Transactional(REQUIRED) opens physical T
  -> template.execute(REQUIRED)
       -> joins T
       -> writes row
       -> template's logical scope returns
  -> outer throws IllegalStateException
  -> physical T rolls back, including row written by template
```

Thus the statement "after `execute` finishes, the DB has committed" **holds only when the template actually owns the physical transaction and the manager completed successfully**. Manual manager calls with `PROPAGATION_REQUIRED` have the exact same limitation.

### 7.2. `REQUIRES_NEW` for Truly Independent Boundaries

```java
TransactionTemplate isolated = new TransactionTemplate(manager);
isolated.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW);
```

With a supporting manager, when an outer transaction is active, inner `REQUIRES_NEW` suspends outer and opens another physical transaction. Inner can commit even if outer rolls back, changing business atomicity. It may require a second connection because outer still holds its connection. Under high load, pool exhaustion can cause starvation.

Do not switch every callback to `REQUIRES_NEW` just to "guarantee commit": business invariants may forbid it, and distributed resources or commit failures still exist.

### 7.3. `NESTED` Differs from `REQUIRES_NEW`

`NESTED` typically uses a JDBC savepoint inside the same physical transaction and rolls back to the savepoint when supported by manager/driver. `REQUIRES_NEW` creates another physical transaction. `JpaTransactionManager` does not provide portable nested JPA persistence-context semantics; savepoints do not revert managed entities.

Both `TransactionTemplate` and the manual manager API rely on the same propagation implementation; the template does not magically add savepoint capabilities to a DB or JPA.

### 7.4. Configure Once, Reuse Many Times

`TransactionTemplate` instances can be shared across threads as long as **configuration is not mutated between calls**. They do not store per-transaction conversational state, yet they do hold mutable settings such as propagation/isolation/timeout.

**Avoid:**

```java
// Wrong if this is a singleton template used across concurrent requests:
template.setPropagationBehavior(requestWantsNew
        ? TransactionDefinition.PROPAGATION_REQUIRES_NEW
        : TransactionDefinition.PROPAGATION_REQUIRED);
template.executeWithoutResult(status -> doWork());
```

Threads race when mutating the same instance. Create two separate templates:

```java
TransactionTemplate required = new TransactionTemplate(manager);

TransactionTemplate newTransaction = new TransactionTemplate(manager);
newTransaction.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW);
```

The runnable project below uses this pattern.

### 7.5. Read-Only, Timeout, and Isolation Are Not Magic

`template.setReadOnly(true)` is a hint to the manager/resource and may be enforced by some databases/drivers, yet it is not a security ACL guaranteed to block every write. `setTimeout(10)` is not a watchdog killing arbitrary Java CPU work or HTTP requests after 10 seconds. Isolation is not automatically changed on an already active transaction if the manager does not apply transaction characteristics to participating scopes.

If a transaction includes an external HTTP call, configure a dedicated network timeout; better yet, avoid holding a JDBC transaction open across long I/O when business rules do not require it.

## 8. Runnable Project: Java 17 + Spring Boot 3.3.5 + JDBC/H2

Let us build a small Spring Boot project to **compare in practice**, rather than just reading pseudocode. Both the manual helper and the template use the **same `DataSourceTransactionManager`** and the same `EventStore`, differing solely in how they coordinate the transaction lifecycle.

Tests observe:

- both template and manual commit when the body succeeds;
- both template and manual roll back when a runtime exception or Error escapes;
- manual helper defines its own rollback for checked `IOException`, while template wraps as unchecked;
- template allows `status.setRollbackOnly()` without throwing an exception;
- rollback of an earlier transaction finishes before the next transaction begins;
- `REQUIRES_NEW` can commit an audit record independently of outer rollback;
- transaction activity appears only inside the callback/low-level action in a fixture without an outer transaction;
- direct call through a private helper still runs the template without depending on a transactional proxy.

### 8.1. Directory Tree

```text
transaction-template-vs-manual/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/txcompare/
    │   │   ├── TxCompareApplication.java
    │   │   ├── EventStore.java
    │   │   ├── ManualTransactions.java
    │   │   └── ComparisonService.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/java/com/example/txcompare/
        └── ComparisonServiceIntegrationTest.java
```

Requirements: **JDK 17+**, Gradle compatible with Spring Boot 3.3.5, and Maven Central for initial dependency download. If creating the project manually, you need Gradle or a Gradle Wrapper. The project uses an in-memory H2 DB with no web server.

`settings.gradle`:

```groovy
rootProject.name = 'transaction-template-vs-manual'
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

Spring Boot's dependency management aligns compatible versions of Spring JDBC, Spring TX, JUnit, and H2. There is no need to add Hibernate/JPA because this lesson uses JDBC so transaction statuses and SQL timing remain clear.

### 8.2. DataSource, Schema, and Spring Boot Bootstrap

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:txcompare;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=5
spring.sql.init.mode=always
```

`src/main/resources/schema.sql`:

```sql
CREATE TABLE events (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    event_key VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE audit_events (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    audit_key VARCHAR(80) NOT NULL UNIQUE
);
```

Two separate tables ensure the `REQUIRES_NEW` test does not have to UPDATE a row currently locked by the outer transaction. Never infer that external I/O outside the database is also inside the JDBC transaction.

`src/main/java/com/example/txcompare/TxCompareApplication.java`:

```java
package com.example.txcompare;

import javax.sql.DataSource;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBootApplication
public class TxCompareApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxCompareApplication.class, args);
    }

    @Bean("transactionManager")
    public PlatformTransactionManager transactionManager(
            DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
```

There is only one `PlatformTransactionManager` for one datasource. Spring Boot provides `JdbcTemplate` and the datasource; the JDBC manager binds the connection to the thread's transaction context per imperative transaction semantics.

### 8.3. EventStore: SQL Layer That Needs No Knowledge of Transaction Ownership

`src/main/java/com/example/txcompare/EventStore.java`:

```java
package com.example.txcompare;

import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class EventStore {
    private final JdbcTemplate jdbc;

    public EventStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void addEvent(String key) {
        jdbc.update(
                "INSERT INTO events(event_key) VALUES (?)", key);
    }

    public void addAudit(String key) {
        jdbc.update(
                "INSERT INTO audit_events(audit_key) VALUES (?)", key);
    }

    public List<String> events() {
        return jdbc.queryForList(
                "SELECT event_key FROM events ORDER BY event_key",
                String.class);
    }

    public List<String> audits() {
        return jdbc.queryForList(
                "SELECT audit_key FROM audit_events ORDER BY audit_key",
                String.class);
    }

    public void reset() {
        jdbc.update("DELETE FROM audit_events");
        jdbc.update("DELETE FROM events");
    }
}
```

The repository only knows `JdbcTemplate`. It joins any active transaction via Spring's connection-binding mechanism; there is no need to insert `commit`/`rollback` or manually call `Connection.setAutoCommit(false)`. When tests call `reset()` outside a transaction, SQL cleanup runs on a connection following the fixture's autocommit behavior.

### 8.4. ManualTransactions: Carefully Written Low-Level Code

`src/main/java/com/example/txcompare/ManualTransactions.java`:

```java
package com.example.txcompare;

import java.util.concurrent.Callable;

import org.springframework.stereotype.Component;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.DefaultTransactionDefinition;

@Component
public class ManualTransactions {
    private final PlatformTransactionManager manager;
    private final DefaultTransactionDefinition definition;

    public ManualTransactions(PlatformTransactionManager manager) {
        this.manager = manager;
        this.definition = new DefaultTransactionDefinition();
        this.definition.setName("manual-unit-of-work");
        this.definition.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRED);
    }

    public <T> T run(Callable<T> action) throws Exception {
        // May throw here; no status exists to roll back
        // if getTransaction fails before returning.
        TransactionStatus status = manager.getTransaction(definition);
        T result;

        try {
            result = action.call();
        } catch (Exception | Error businessFailure) {
            // Do not place commit in this try: if commit throws
            // after completion, never try rolling back a completed status.
            try {
                manager.rollback(status);
            } catch (RuntimeException | Error rollbackFailure) {
                // Preserve original error context if rollback also fails.
                if (rollbackFailure != businessFailure) {
                    rollbackFailure.addSuppressed(businessFailure);
                }
                throw rollbackFailure;
            }
            throw businessFailure;
        }

        manager.commit(status);
        return result;
    }
}
```

This is a **compilable helper** for the demo, though not intended to replicate all capabilities/edge cases of `TransactionTemplate`. Because it uses `Callable<T>`, it allows checked `Exception`s to escape the body and **deliberately rolls back checked exceptions too**. That is a **policy chosen by the helper**, differing from declarative `@Transactional`'s fallback rollback rule.

**Read the exception handling carefully:**

- A failure in `getTransaction` leaves no `TransactionStatus` for the application to roll back.
- If the body throws `Exception` or `Error`, the helper requests rollback and then propagates.
- If rollback also fails, the rollback error is propagated and the original failure is attached via `addSuppressed`.
- `manager.commit(status)` sits **outside the body's catch block**, avoiding blind rollback after a commit error.
- The helper still does not replace all logic in Spring's template; any custom helper must be thoroughly tested against real managers/resources.

### 8.5. ComparisonService: Same Work, Two Invocation Styles

`src/main/java/com/example/txcompare/ComparisonService.java`:

```java
package com.example.txcompare;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class ComparisonService {
    private final EventStore store;
    private final ManualTransactions manual;
    private final TransactionTemplate required;
    private final TransactionTemplate independent;

    public ComparisonService(
            EventStore store,
            ManualTransactions manual,
            PlatformTransactionManager manager) {

        this.store = store;
        this.manual = manual;

        this.required = new TransactionTemplate(manager);
        this.required.setName("template-required");

        this.independent = new TransactionTemplate(manager);
        this.independent.setName("template-new");
        this.independent.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW);
    }

    public record Observation(boolean inside, boolean after) {
    }

    public String templateSuccess(String key) {
        return required.execute(status -> {
            store.addEvent(key);
            return key;
        });
    }

    public String manualSuccess(String key) throws Exception {
        return manual.run(() -> {
            store.addEvent(key);
            return key;
        });
    }

    public void templateRuntimeFailure(String key) {
        required.executeWithoutResult(status -> {
            store.addEvent(key);
            throw new IllegalStateException("template runtime failure");
        });
    }

    public void manualRuntimeFailure(String key) throws Exception {
        manual.run(() -> {
            store.addEvent(key);
            throw new IllegalStateException("manual runtime failure");
        });
    }

    public void templateErrorFailure(String key) {
        required.executeWithoutResult(status -> {
            store.addEvent(key);
            throw new AssertionError("template error");
        });
    }

    public void manualErrorFailure(String key) throws Exception {
        manual.run(() -> {
            store.addEvent(key);
            throw new AssertionError("manual error");
        });
    }

    public void manualCheckedFailure(String key) throws Exception {
        manual.run(() -> {
            store.addEvent(key);
            throw new IOException("checked IO");
        });
    }

    public void templateWrappedCheckedFailure(String key) {
        required.executeWithoutResult(status -> {
            store.addEvent(key);
            try {
                checkedOperation();
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        });
    }

    private static void checkedOperation() throws IOException {
        throw new IOException("checked IO");
    }

    public boolean templateBusinessRejects(String key) {
        return required.execute(status -> {
            store.addEvent(key);
            status.setRollbackOnly();
            return false;
        });
    }

    public void templateSecondTransactionAfterFailure() {
        try {
            required.executeWithoutResult(status -> {
                store.addEvent("should-rollback");
                throw new IllegalStateException("first failed");
            });
        } catch (IllegalStateException expected) {
            // First transaction has gone through the rollback path.
        }

        required.executeWithoutResult(status -> {
            store.addEvent("second-committed");
        });
    }

    public void templateNewAuditSurvivesOuterRollback() {
        required.executeWithoutResult(outerStatus -> {
            store.addEvent("outer");

            independent.executeWithoutResult(innerStatus -> {
                store.addAudit("inner-audit");
            });

            outerStatus.setRollbackOnly();
        });
    }

    public Observation templateBoundaryVisibility(String key) {
        boolean inside = required.execute(status -> {
            store.addEvent(key);
            return TransactionSynchronizationManager
                    .isActualTransactionActive();
        });

        boolean after = TransactionSynchronizationManager
                .isActualTransactionActive();

        return new Observation(inside, after);
    }

    public boolean manualBodyHasActiveTransaction(String key)
            throws Exception {
        return manual.run(() -> {
            store.addEvent(key);
            return TransactionSynchronizationManager
                    .isActualTransactionActive();
        });
    }

    public void directCallToPrivateHelper(String key) {
        privateTemplateHelper(key);
    }

    private void privateTemplateHelper(String key) {
        required.executeWithoutResult(status -> {
            store.addEvent(key);
        });
    }

    public void templateThenExternalFailure(String key) {
        required.executeWithoutResult(status -> {
            store.addEvent(key);
        });

        // Failure occurs AFTER execute has already completed the DB scope.
        throw new IllegalStateException("external notification failed");
    }

    public void templateInChunks(List<String> keys) {
        for (String key : keys) {
            try {
                required.executeWithoutResult(status -> {
                    store.addEvent(key);
                    if ("reject".equals(key)) {
                        throw new IllegalStateException("rejected chunk");
                    }
                });
            } catch (IllegalStateException expected) {
                // Partial-success demo policy. Do not swallow other errors.
            }
        }
    }
}
```

Four details to inspect closely:

1. `templateSuccess` and `manualSuccess` use the same `EventStore`, the same `PlatformTransactionManager`, and default `REQUIRED`. When run outside an outer transaction, both create a new physical transaction.
2. `manualCheckedFailure` lets `IOException` escape from `Callable`; the helper rolls back. `templateWrappedCheckedFailure` converts `IOException` to unchecked so the template rolls back.
3. `templateBusinessRejects` marks rollback-only and returns `false`: do not interpret a normal return as meaning the insert committed.
4. `templateNewAuditSurvivesOuterRollback` demonstrates `REQUIRES_NEW` is distinct from the outer transaction. The audit can commit despite outer rollback, an **architectural decision the business must approve**.

Templates are created/configured **once in the constructor**, never mutating propagation/read-only per request on a singleton. The private helper still calls the template directly without relying on a proxy intercepting private methods.

### 8.6. JUnit Integration Test: Comparing Identical DB Outcomes

`src/test/java/com/example/txcompare/ComparisonServiceIntegrationTest.java`:

```java
package com.example.txcompare;

import java.io.IOException;
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
class ComparisonServiceIntegrationTest {
    @Autowired
    private ComparisonService service;

    @Autowired
    private EventStore store;

    @BeforeEach
    void reset() {
        store.reset();
    }

    @Test
    void templateCommitAndReturnValue() {
        assertEquals("template-ok", service.templateSuccess("template-ok"));
        assertEquals(List.of("template-ok"), store.events());
    }

    @Test
    void manualCommitAndReturnValue() throws Exception {
        assertEquals("manual-ok", service.manualSuccess("manual-ok"));
        assertEquals(List.of("manual-ok"), store.events());
    }

    @Test
    void templateRollsBackRuntimeFailure() {
        assertThrows(IllegalStateException.class,
                () -> service.templateRuntimeFailure("template-failed"));
        assertEquals(List.of(), store.events());
    }

    @Test
    void manualRollsBackRuntimeFailure() {
        assertThrows(IllegalStateException.class,
                () -> service.manualRuntimeFailure("manual-failed"));
        assertEquals(List.of(), store.events());
    }

    @Test
    void templateRollsBackError() {
        assertThrows(AssertionError.class,
                () -> service.templateErrorFailure("template-error"));
        assertEquals(List.of(), store.events());
    }

    @Test
    void manualHelperRollsBackError() {
        assertThrows(AssertionError.class,
                () -> service.manualErrorFailure("manual-error"));
        assertEquals(List.of(), store.events());
    }

    @Test
    void manualHelperRollsBackCheckedIOExceptionByItsPolicy() {
        assertThrows(IOException.class,
                () -> service.manualCheckedFailure("manual-io"));
        assertEquals(List.of(), store.events());
    }

    @Test
    void templateRollsBackWrappedCheckedException() {
        assertThrows(UncheckedIOException.class,
                () -> service.templateWrappedCheckedFailure("template-io"));
        assertEquals(List.of(), store.events());
    }

    @Test
    void templateRollbackOnlyCanReturnNormally() {
        assertFalse(service.templateBusinessRejects("rejected"));
        assertEquals(List.of(), store.events());
    }

    @Test
    void separateTransactionCanCommitAfterEarlierRollback() {
        service.templateSecondTransactionAfterFailure();
        assertEquals(List.of("second-committed"), store.events());
    }

    @Test
    void requiresNewAuditCanSurviveOuterRollback() {
        service.templateNewAuditSurvivesOuterRollback();
        assertEquals(List.of(), store.events());
        assertEquals(List.of("inner-audit"), store.audits());
    }

    @Test
    void transactionIsVisibleInsideTemplateScopeNotAfterIt() {
        var observation = service.templateBoundaryVisibility("observed");
        assertTrue(observation.inside());
        assertFalse(observation.after());
        assertEquals(List.of("observed"), store.events());
        assertFalse(TransactionSynchronizationManager
                .isActualTransactionActive());
    }

    @Test
    void manualTransactionAlsoBindsActiveContext() throws Exception {
        assertTrue(service.manualBodyHasActiveTransaction("manual-visible"));
        assertEquals(List.of("manual-visible"), store.events());
        assertFalse(TransactionSynchronizationManager
                .isActualTransactionActive());
    }

    @Test
    void directPrivateHelperCallStillUsesTemplate() {
        service.directCallToPrivateHelper("private");
        assertEquals(List.of("private"), store.events());
    }

    @Test
    void externalFailureAfterTemplateCompletionDoesNotUndoCommit() {
        assertThrows(IllegalStateException.class,
                () -> service.templateThenExternalFailure("committed"));
        assertEquals(List.of("committed"), store.events());
    }

    @Test
    void failedChunkDoesNotUndoEarlierAndLaterCommittedChunks() {
        service.templateInChunks(
                List.of("first", "reject", "third"));
        assertEquals(List.of("first", "third"), store.events());
    }
}
```

**There are 16 integration tests**, covering commit, runtime rollback, Error rollback, checked-exception policy, explicit rollback-only, multiple independent scopes, `REQUIRES_NEW`, scope activity, private method call, post-commit external failure, and chunked partial success.

**Why not put `@Transactional` on the test class?** If the test opens its own transaction, both the manual helper and `REQUIRED` template can **join** the test's transaction; SQL visible inside the test would not prove the service physically committed. Here the tests run outside a test-managed transaction: they invoke the service, let transaction scope completion occur, and then read the DB from the repository.

### 8.7. Running Tests and Understanding Results

With Gradle Wrapper:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

If you created the project manually without a wrapper, install a compatible Gradle version, run `gradle test`, or generate the Gradle Wrapper first. Do not run plain `javac` for Spring code because Spring/JUnit/H2 are required on the classpath.

**Expected result:** 16 tests pass when dependencies/environment match the fixture. This is the expectation from the code and Spring JDBC transaction semantics; **it is not a claim that the test suite was executed while authoring this lesson**. JUnit does not guarantee a fixed test order or stdout order. The report generated on an actual run is at `build/reports/tests/test/index.html`.

| Scenario | Caller / result | DB after boundary |
| --- | --- | --- |
| Template commit | Returns `template-ok` | One event `template-ok` |
| Manual commit | Returns `manual-ok` | One event `manual-ok` |
| Template RuntimeException | `IllegalStateException` | Events empty |
| Manual RuntimeException | `IllegalStateException` | Events empty |
| Template Error | `AssertionError` | Events empty |
| Manual Error | `AssertionError` | Events empty |
| Manual checked exception | `IOException` | Events empty |
| Template wrapped checked | `UncheckedIOException` | Events empty |
| Template `setRollbackOnly` | Returns `false` | Events empty |
| Callback 1 fails, callback 2 succeeds | Normal return | Only `second-committed` |
| `REQUIRES_NEW` audit inside outer rollback | Normal return | Events empty; audit `inner-audit` |
| Template scope activity | `true` inside, `false` after | Event `observed` |
| Manual scope activity | `true` inside action | Event `manual-visible` |
| Private helper calls template | Normal return | Event `private` |
| External failure after execute | `IllegalStateException` | Event `committed` **remains** |
| Middle chunk fails | Returns per demo policy | Events `first`, `third` |

**Do not infer from a single exception that the DB rolled back cleanly.** Tests verify both exception/transaction state and real data after the boundary. If using JPA, flush/commit timing can differ from JDBC; if using a production DB, verify against that system's exact driver, isolation, and locking behavior.

## 9. When Is Manual Management with PlatformTransactionManager Still Reasonable?

TransactionTemplate is **usually** better if the work fits a normal `execute callback` shape. Still, the low-level API has its place, especially when writing infrastructure code:

### 9.1. Building a Specialized Transaction Abstraction

An internal framework may need to interact directly with `getTransaction`/`commit`/`rollback`, manage multiple phases, or coordinate lifecycle states that cannot be expressed cleanly as a single callback. In those cases, knowing exact owner/status and error precedence is mandatory. However, this is typically **thoroughly tested infrastructure code**, not everyday service logic.

### 9.2. Controlling Checked-Exception Policies Outside a Callback

An API accepting `Callable<T>` declaring `throws Exception` can choose to roll back on checked exceptions and rethrow the exact same exception type, like `ManualTransactions` in the demo. A template callback cannot throw checked exceptions directly through standard Java signatures. Yet before building a complex custom helper, consider `@Transactional(rollbackFor=...)` or designing an adapter that converts checked exceptions into domain outcomes or unchecked wrappers.

### 9.3. Code Whose Transaction Lifecycle Intentionally Spans Beyond One Callback

Some places start a transaction in one step and end it in another step within the same request/thread. The direct manager API can express this, yet **it is very easy for resources to be held too long, drift across threads, or leak**. An imperative manager's `TransactionStatus` is usually tied to thread/resources; never pass it arbitrarily across executors/`@Async`/HTTP requests. Use only when no safer abstraction fits and you have tests for cancellation, timeouts, errors, and cleanup.

### 9.4. Writing Tests for a Custom Transaction Manager

If the goal is to test a `PlatformTransactionManager` implementation directly, you naturally need to call the direct API. That is infrastructure testing, distinct from a business service merely wanting an atomic unit of work.

**Tradeoff:** manual code grants control yet increases error-handling obligations, and does not make resources/DBs magically support features they lack.

## 10. Limitations of TransactionTemplate You Must Also Understand

### 10.1. Does Not Automatically Solve Concurrency Invariants

`TransactionTemplate` wraps a database transaction, yet does not automatically prevent duplicate bookings, lost updates, or quota overruns if SQL/schema lack protection. You still need `UNIQUE`, `CHECK`, locking, optimistic locking `@Version`, or appropriate atomic guarded UPDATEs.

### 10.2. Does Not Roll Back HTTP, Email, or Object Storage

An already sent email cannot be recalled by a JDBC transaction manager merely because the callback threw an exception. Avoid placing slow network I/O inside callbacks when unnecessary. When DB events must stay in sync with message delivery, consider a transactional outbox and an idempotent dispatcher.

### 10.3. Does Not Guarantee Every Commit Error Means Rollback

After a commit failure caused by network or connection drop, the outcome can be uncertain. Never retry a payment/booking operation without an idempotency key or reconciliation mechanism.

### 10.4. Does Not Automatically Carry Transactions to Other Threads

Imperative Spring transactions typically rely on thread-bound resources via `TransactionSynchronizationManager`. If a callback spawns a `CompletableFuture` or `@Async` task, that task does not automatically join the caller thread's transaction. Use separate transaction boundaries, queues/workflows, or appropriate reactive infrastructure.

### 10.5. Not Equivalent to Reactive Transactions

With R2DBC/Reactor, use `ReactiveTransactionManager` and `TransactionalOperator` to wrap the publisher lifecycle/reactor context, rather than using imperative `TransactionTemplate` thinking it holds a transaction open across an entire `Mono`/`Flux`.

### 10.6. Cannot Cure a Transaction Already Marked Rollback-Only

If an inner `REQUIRED` participant marks the shared transaction rollback-only, an outer catch and normal `template.execute` return does not reset the marker. When the physical owner tries to commit, `UnexpectedRollbackException` can occur. TransactionTemplate reduces boilerplate; it does not disable propagation or rollback-only semantics.

## 11. Code Review Checklist: Template or Manual?

When reviewing a PR containing `getTransaction`/`commit`/`rollback` in a business service, ask:

1. What is the unit of work? Which statements **must commit or roll back together**?
2. Can the boundary be declared with `@Transactional` on a service method via Spring proxy?
3. If programmatic is needed, does the business body fit a callback shape? If so, why not use `TransactionTemplate`?
4. Does the injected manager match the datasource/entity manager in use?
5. Might `PROPAGATION_REQUIRED` join an active outer transaction? Did the author confuse "scope finished" with "physical commit finished"?
6. Do transaction definition name/isolation/timeout/readOnly need configuration? Is a shared template being mutated per request?
7. Which checked exceptions require rollback? Is there an explicit policy instead of relying on an assumption from `@Transactional`?
8. Are both `Error` and runtime exceptions caught and rolled back properly before propagating?
9. If rollback fails, is the original business exception preserved via cause/suppressed/log?
10. Is `commit` inside a catch block where it could be rolled back a second time on a commit error?
11. Is `TransactionStatus` reused after completion or rolled back twice?
12. If no status exists because `getTransaction` failed, how does the code handle it?
13. Are there outer/inner transactions with `REQUIRES_NEW`, connection pool sizing, or lock contention?
14. Are there external side effects outside the database that the callback cannot roll back?
15. Do tests read the DB **after the transaction boundary** and avoid test-managed transactions when proving commits?
16. Are there integration tests for success, runtime failure, checked policy, Error, rollback-only, major commit failures, and rollback failures (if writing a custom helper)?
17. Is there an idempotency/retry plan when commit outcome is unclear?
18. Is the template kept at the orchestration/application layer rather than coupling the domain model to Spring APIs?

For most business services, the more of these questions you must handle yourself in manual code, the clearer **the boilerplate-avoidance benefit of `TransactionTemplate`** becomes.

## 12. Common Misconceptions

**Misconception 1: "TransactionTemplate differs from PlatformTransactionManager in atomicity guarantees."**  
False. The template calls the corresponding manager; atomicity comes from the transaction manager and participating resources.

**Misconception 2: "Only manual code truly controls commit."**  
False. The template also configures propagation/isolation/timeout and accesses status; it only delegates lifecycle boilerplate to Spring.

**Misconception 3: "With a template, you do not need to understand propagation."**  
False. `REQUIRED` can join outer; `REQUIRES_NEW` is an independent transaction; `NESTED` is a savepoint when supported.

**Misconception 4: "Callback returning means the data has committed."**  
False. The manager still runs completion; if joining outer, physical commit happens later, and if rollback-only is set, it can roll back.

**Misconception 5: "Template rolls back on all checked Exceptions just like @Transactional with rollbackFor."**  
False at the Java API level: the callback signature declares no checked exceptions. You must catch/wrap/mark rollback-only, or choose an appropriate declarative policy.

**Misconception 6: "Manual getTransaction always creates a new transaction."**  
False. It depends on `TransactionDefinition` and existing transactions just like the template.

**Misconception 7: "Catching a RuntimeException inside the callback and returning normally still rolls back by default."**  
Not automatically. If the interceptor/template sees only a normal return and neither status nor resource is rollback-only, the manager may commit. To roll back, propagate the exception or call `setRollbackOnly`.

**Misconception 8: "Putting rollback in finally is the safest pattern."**  
False if `finally` always rolls back even when commit/rollback has already completed; that causes double completion and hides errors.

**Misconception 9: "Catching Exception is enough."**  
That excludes `Error`. The template handles rollback when `Error` escapes the callback.

**Misconception 10: "A rollback exception does not need to preserve the business failure."**  
False for observability. When rollback also fails, preserving context of the application failure is essential for finding root causes.

**Misconception 11: "The template automatically manages all external resources."**  
False. Email, HTTP, messages, and file systems are not rolled back by a JDBC transaction manager.

**Misconception 12: "Creating a singleton template and changing propagation per call is fine."**  
Unsafe when mutable configuration is shared across threads. Create separate template instances per policy.

**Misconception 13: "Using a template inside a private method has no transaction."**  
False. A direct `execute` call needs no Spring AOP proxy on the enclosing method, though it still needs the right manager/resources.

**Misconception 14: "A manual manager is always better because it is flexible."**  
It may be necessary in infrastructure code, yet flexibility brings many error branches you must test yourself; for standard callback flows, the template usually lowers risk.

**Misconception 15: "If an exception is returned to the caller, the DB definitely rolled back."**  
False for indeterminate commit outcomes or exceptions **after** the transaction completed (for example an external notification failing).

## 13. Self-Check Questions

**Question 1.** Why does Spring generally recommend `TransactionTemplate` for imperative programmatic transaction management?  
**Answer:** It uses a callback to encapsulate acquiring status, commit/rollback, exception handling, and completion paths; developers stay focused on the unit of work, reducing boilerplate and failure-path bugs.

**Question 2.** Does the template create a different "transaction engine" than `PlatformTransactionManager`?  
**Answer:** No. It uses the exact manager provided and the exact same propagation/resource semantics.

**Question 3.** Why is the manual snippet `try { work(); commit(); } catch(RuntimeException e) { rollback(); }` dangerous?  
**Answer:** `commit` can throw an error after the status is already completed; the catch block tries to roll back a second time and masks the error. Separate exceptions from work from completion, or let the template manage it.

**Question 4.** If the body throws `AssertionError`, does `catch (Exception)` run?  
**Answer:** No. `Error` does not inherit from `Exception`. The template includes a rollback branch whenever `RuntimeException` or `Error` escapes the callback.

**Question 5.** Can you directly throw checked `IOException` from a `TransactionCallback` lambda?  
**Answer:** Not under normal Java signatures. Catch/wrap it as unchecked, return a business result and mark rollback-only, or use another suitable API/declarative option.

**Question 6.** Can a manual manager choose to roll back for checked exceptions?  
**Answer:** Yes. The application sets the policy in its catch block, like `ManualTransactions` accepting `Callable<T>` and rolling back when `Exception` escapes. That is an application decision, not a fixed manager default.

**Question 7.** Does `status.setRollbackOnly()` always throw an exception to the caller?  
**Answer:** No. When the owner transaction intentionally rolls back, the template can return normally. When merely joining an outer transaction, the marker can later cause the outer owner to encounter `UnexpectedRollbackException`.

**Question 8.** Does `template.execute` returning normally mean the physical transaction committed?  
**Answer:** Only when the template actually owns the physical transaction and the manager finished committing successfully; `REQUIRED` can join an outer transaction and therefore not physically commit yet.

**Question 9.** Why shouldn't a singleton template change isolation/propagation before each request?  
**Answer:** The instance holds mutable configuration, so concurrent threads can race. Use separate instances configured once.

**Question 10.** If atomicity is needed between a DB insert and sending an email, is TransactionTemplate enough?  
**Answer:** No. Email does not automatically roll back with a JDBC manager. Use a transactional outbox/idempotent dispatcher or another suitable design.

**Question 11.** Why don't the example tests put `@Transactional` on the test class?  
**Answer:** A test-managed transaction can cause `REQUIRED` callbacks to join the test's transaction and not physically commit at the boundary under test. You need to read the DB after completion.

**Question 12.** If partial rollback inside the same JDBC transaction is needed, is `REQUIRES_NEW` the same as `NESTED`?  
**Answer:** No. `NESTED` usually uses a savepoint; `REQUIRES_NEW` opens an independent physical transaction. Both require manager/resource support and have different semantics.

**Question 13.** When is the manual manager API still worth considering?  
**Answer:** Infrastructure code needing very special lifecycle control or custom transaction-manager tests, where callback abstractions do not fit and the team can thoroughly test begin/commit/rollback/failure paths.

**Question 14.** Can you test how the template handles a rollback error merely by asserting event counts?  
**Answer:** No. To test error precedence and exception preservation, you need tests that simulate or control the manager failure path. Normal H2 integration tests verify business rollback, not connection-outage/rollback-exception edge cases.

**Question 15.** For a pure database service method with a clear boundary, should you use the template or `@Transactional`?  
**Answer:** Usually prefer `@Transactional` to keep business code concise with low coupling. Advice to use the template applies once you have decided programmatic transaction control is needed.

## 14. Official References

- [Spring Framework — Programmatic Transaction Management: TransactionTemplate vs PlatformTransactionManager](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html)
- [Spring Framework — TransactionTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html)
- [Spring Framework — TransactionCallback Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/TransactionCallback.html)
- [Spring Framework — TransactionOperations Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/TransactionOperations.html)
- [Spring Framework — PlatformTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/PlatformTransactionManager.html)
- [Spring Framework — TransactionStatus Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/TransactionStatus.html)
- [Spring Framework — DefaultTransactionDefinition Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/DefaultTransactionDefinition.html)
- [Spring Framework — Rollback Rules](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Test-managed Transactions](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html)
