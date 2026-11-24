# Distinguishing Method Completion from Commit Completion in Spring Framework

## 1. Two different points in time

In Spring Transaction Management, the statement "the `@Transactional` method has finished running" may only mean that **the Java method body (target method) has reached `return`**. That **does not yet confirm that data has been `COMMIT`ted successfully**.

You must distinguish at least three milestones:

1. **Method body finishes:** the statements inside the method have run to the end or `return`; the provisional result is returned to the transaction interceptor/proxy. SQL may already have been sent to the database, yet the transaction is still open.
2. **Physical transaction completes:** the transaction manager has asked the database to `COMMIT` and received a successful result, or has executed `ROLLBACK`. Before commit, there may still be flushes, callbacks, constraint checks, connection errors, `rollback-only` markers, and so on.
3. **Spring proxy call finishes:** the caller receives the return value or exception after the interceptor handles the transaction. If the proxy **owns the physical transaction** in a normal synchronous call, the caller only receives a successful result after the commit succeeds and the relevant synchronous callbacks have run. If the method merely **joins the caller's transaction**, its return is not the final commit milestone.

That is why `return orderId;` in a service does not mean "the order is durably saved" at the `return` line, and a `"save completed"` log placed before `return` is not proof of a successful commit.

| Observation | Valid conclusion |
| --- | --- |
| Reached `return` inside a `@Transactional` service | The method body completed; commit may not have started yet. |
| `repository.save(...)` returned | The save call was accepted per repository semantics; commit is not yet confirmed. |
| `entityManager.flush()` or `saveAndFlush(...)` succeeded | Pending changes were synchronized to the DB; **flush is not commit**. |
| `TransactionSynchronization.afterCommit()` was invoked | The commit of the corresponding transaction succeeded. |
| Caller received a successful result from a proxy that **creates and finishes** the physical transaction | Normally the commit succeeded before the proxy returned the result. |
| A `REQUIRED` method inside an outer transaction returned | The outer transaction can still roll back afterward. |
| An exception appears at the caller | You must determine whether the exception occurred before or after commit; do not assume every exception means rollback. |

## 2. Execution mechanism of `@Transactional`

For a **synchronous, imperative Spring transaction using an AOP proxy** (the common case with JDBC/JPA), the typical flow is:

```text
Caller
  |
  v
Spring transactional proxy / interceptor
  |-- Start a new transaction or join an existing transaction
  |-- Invoke the service method body
  |     |-- Repository / JDBC / JPA operations
  |     |-- Log, build result, and return
  |     '-- [Method body ends here]
  |
  |-- If the proxy is responsible for completing the transaction:
  |     |-- beforeCommit / flush and beforeCompletion (if any)
  |     |-- COMMIT or ROLLBACK at transaction manager / DB
  |     |-- afterCommit (only when commit succeeds)
  |     |-- afterCompletion and cleanup
  |
  '-- Return result or throw exception to caller
```

Crucially, **Spring does not execute `COMMIT` at the `return` statement inside the service body**. For a new transaction, the interceptor acts after the method body exits. If the method body throws an exception, the interceptor applies the appropriate rollback/commit rules before propagating the exception to the caller. If the method is called without going through the proxy or merely joins an existing transaction, the handling milestone differs.

### Why can a method body return normally yet commit still fail?

- SQL flush occurs near commit and hits a foreign key violation, unique constraint violation, optimistic locking error, or another error.
- `TransactionSynchronization.beforeCommit(...)` or a commit-preparation task throws an exception.
- An earlier execution branch marked the transaction as `rollback-only`. At the commit boundary, Spring may report `UnexpectedRollbackException`.
- The DB or transaction management system fails during the commit step.

For instance, `return "OK";` inside the service body only constructs the intended return value. If commit fails, the caller may receive an exception instead of `"OK"`.

## 3. Runnable example: method finishes before commit

This example uses **Java 17+, Spring Boot 3.5.16, Spring JDBC, and H2**. Two calls show: one successful commit and one case where the method body finishes yet a `beforeCommit` callback triggers a rollback. This mechanism is used here to demonstrate ordering; in real applications you should not intentionally throw exceptions inside callbacks solely to control business logic.

Structure:

```text
tx-boundary-demo/
  pom.xml
  src/main/java/com/example/tx/TransactionDemoApplication.java
```

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>tx-boundary-demo</artifactId>
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

**`src/main/java/com/example/tx/TransactionDemoApplication.java`**

```java
package com.example.tx;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@SpringBootApplication
public class TransactionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(TransactionDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner demo(JdbcTemplate jdbc, TxWriter writer) {
        return args -> {
            jdbc.execute("CREATE TABLE IF NOT EXISTS tx_demo "
                    + "(id INT PRIMARY KEY, label VARCHAR(40))");
            jdbc.update("DELETE FROM tx_demo");

            System.out.println("caller: before, rows=" + count(jdbc));
            writer.write(1, false);
            System.out.println("caller: after success, rows=" + count(jdbc));

            try {
                writer.write(2, true);
            } catch (IllegalStateException ex) {
                System.out.println("caller: caught " + ex.getMessage());
            }
            System.out.println("caller: after failure, rows=" + count(jdbc));
        };
    }

    private static int count(JdbcTemplate jdbc) {
        return jdbc.queryForObject("SELECT COUNT(*) FROM tx_demo", Integer.class);
    }
}

@Service
class TxWriter {
    private final JdbcTemplate jdbc;

    TxWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void write(int id, boolean rejectBeforeCommit) {
        jdbc.update(
                "INSERT INTO tx_demo (id, label) VALUES (?, ?)",
                id, "row-" + id);
        System.out.println("target: inserted id=" + id);

        TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void beforeCommit(boolean readOnly) {
                        if (rejectBeforeCommit) {
                            throw new IllegalStateException("commit blocked");
                        }
                    }

                    @Override
                    public void afterCommit() {
                        System.out.println("callback: committed id=" + id);
                    }
                });

        System.out.println("target: about to return id=" + id);
    }
}
```

Run in the `tx-boundary-demo` directory:

```bash
mvn spring-boot:run
```

Main `System.out` lines, **omitting Spring's banner and startup logs**:

```text
caller: before, rows=0
target: inserted id=1
target: about to return id=1
callback: committed id=1
caller: after success, rows=1
target: inserted id=2
target: about to return id=2
caller: caught commit blocked
caller: after failure, rows=1
```

**Analysis:**

- Call `write(1, false)`: `target: about to return` is printed **inside the method body**, before the `afterCommit` callback. The proxy starts the transaction, the target finishes, Spring commits, `afterCommit` prints, and only then does the caller print `after success`. The DB has one row.
- Call `write(2, true)`: the method body still reaches its final line; however, `beforeCommit` throws `IllegalStateException` while the proxy processes the transaction. Spring rolls back, there is no `callback: committed id=2` line, and the row count stays `1`. The caller does not observe a successful call.
- The experiment proves that the milestone "target reaches the end" and the milestone "transaction commits successfully" **differ in timing and outcome**. In real code, failure can also come from flush, DB constraints, or rollback-only, not solely from callbacks.

## 4. Returning from a child method does not guarantee the transaction has ended

`@Transactional` defaults to `propagation = REQUIRED`. When no transaction exists, a call through the proxy can create a new transaction. When an outer transaction already exists, the child method **joins the same physical transaction**, and only the owner of the outer boundary decides the final commit.

```java
@Service
class CheckoutService {
    private final StockService stockService;

    CheckoutService(StockService stockService) {
        this.stockService = stockService;
    }

    @Transactional
    public void checkout() {
        stockService.reserveStock(); // Completing this call is not a commit yet
        // If subsequent steps fail and the transaction rolls back,
        // changes made inside reserveStock() can also be rolled back.
    }
}

@Service
class StockService {
    @Transactional // REQUIRED by default
    public void reserveStock() {
        // Modify data within the same physical transaction as checkout().
    }
}
```

This snippet **illustrates service structure**; it is not a standalone program because it omits DB operations and application startup. Both services must be Spring beans and the call must go through the proxy.

| Propagation | When the child method returns |
| --- | --- |
| `REQUIRED` (default), outer transaction active | Not committed independently; outcome depends on the outer transaction. |
| `REQUIRES_NEW` | Creates an independent physical transaction and suspends the outer one; when the proxy call completes successfully, the new transaction has committed on its own. The outer transaction can still roll back afterward. |
| `NESTED` (when supported by tx manager/DB) | Typically uses a savepoint within the same physical transaction; exiting the child scope is not equivalent to an independent physical commit. |

**Easily missed case:** an inner `REQUIRED` scope marks `rollback-only` and returns, or its exception is caught by the outer scope. If the outer scope still tries to commit, it may receive `UnexpectedRollbackException` and the whole transaction rolls back. A child method having "finished with no exception at the caller line" does not clear the rollback-only state.

## 5. Exceptions, rollback, and what the caller-visible result means

Under Spring `@Transactional` defaults, `RuntimeException` and `Error` trigger rollback; checked exceptions normally **do not automatically** trigger rollback. This can be customized via `rollbackFor` or `noRollbackFor`. Therefore, you cannot deduce solely from "presence/absence of an exception in the method body" whether the transaction committed or rolled back.

```java
@Transactional(rollbackFor = java.io.IOException.class)
public void importData() throws java.io.IOException {
    // If IOException escapes, the transaction is also marked for rollback.
}
```

This is **configuration illustrative code**, not a standalone program. Also remember:

- **Catching and swallowing an exception** inside a transaction can let the method finish normally and cause Spring to proceed with attempting a commit, unless the transaction was already marked rollback-only or another error occurs. Do not `catch` and log as if all changes were guaranteed to have rolled back.
- **Errors in `afterCommit`** happen **after the DB commit has already succeeded**; a synchronous callback can propagate an exception to the caller yet cannot undo the commit that already happened. When handling errors, do not blindly retry writing data simply because the caller received an exception.
- **A DB commit does not guarantee that emails, HTTP calls, or outbound messages succeeded.** Those are outcomes of external systems and require their own consistency mechanisms.

## 6. Placing side tasks at the right point in time

Suppose you create an order and then send a notification. If you send an email/message right before `return` inside `@Transactional`, the recipient might see an order that **is later rolled back**. If business logic requires notifying only about committed records, you can bind a listener to the commit phase:

```java
public record OrderCreated(long orderId) {}

@Component
class OrderNotificationListener {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCreated(OrderCreated event) {
        // Runs only after successful commit of the transaction bound to the event.
        // Send signal to notification channel / downstream processing.
    }
}
```

This is a **design illustration**; it requires importing `@Component`, `@TransactionalEventListener`, `TransactionPhase`, and publishing the event inside the transaction. `AFTER_COMMIT` is the default phase of `@TransactionalEventListener`; `BEFORE_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION` serve other purposes. If there is no active transaction, the listener is not invoked by default unless `fallbackExecution = true` is configured.

You can use `TransactionSynchronization.afterCommit()` when you need a callback attached directly to the current transaction. If a post-commit callback must **write new data in its own transaction**, call a service through a proxy with `Propagation.REQUIRES_NEW`; old transaction resources can sometimes remain bound to the thread during the callback phase, so do not assume new writes will automatically commit.

**Reliability limit:** an `AFTER_COMMIT` callback does not automatically make sending messages/emails atomic with the DB. If the process crashes right after DB commit and before sending the notification, the signal can be lost. When delivery guarantees are required, use a **transactional outbox**: write the business record and the outbox record in the same transaction; a worker/relay delivers after commit with retries and deduplication.

## 7. When observing and testing, verify the right milestone

1. **Distinguish log locations.** A log inside the target before `return` only confirms the method body ran up to that line. A log in `afterCommit` or an actual transaction callback confirms commit of that transaction. A log outside the proxy call implies commit only when that proxy owns the physical transaction.
2. **Verify using a separate transaction/connection after the outer boundary finishes.** Do not use the same persistence context or open transaction and conclude data is committed just because you can read back what you wrote.
3. **Test failures occurring at commit time.** Test optimistic locking, unique constraints, rollback-only, and callback failures; assert the final DB state, not just log lines inside the method.
4. **Watch out for `@Transactional` on tests.** Spring TestContext usually rolls back the test transaction after each test; `save()` finishing in a test does not prove the transaction committed. You can use `TestTransaction` to explicitly end a test transaction when verifying commit.
5. **Confirm the proxy actually applies.** In proxy mode, calling `this.innerMethod()` within the same object normally **is not intercepted**; placing `@Transactional` on `innerMethod` does not automatically start a new transaction. Call via a Spring bean/proxy or redesign service boundaries.
6. **Recognize asynchronous/reactive programming.** `@Async` runs on another thread and reactive transactions use the Reactor context; completion of the work or stream is not necessarily when the Java method returns a publisher/future. Do not mechanically apply the synchronous diagram above to every kind of API.

## 8. Self-check scenarios

**Scenario A.** A `@Transactional` service calls `repository.save`, prints `"DONE"`, and `return`s. Afterward the DB reports a unique constraint error during flush/commit. Can the record be considered committed because `"DONE"` was printed?

**Answer:** No. `"DONE"` was printed before the transaction manager completed; the caller may receive an exception and the transaction rolls back.

**Scenario B.** `outer()` has `@Transactional`; `inner()` uses `REQUIRED` and returns normally. `outer()` then throws a `RuntimeException`. Is the data from `inner()` guaranteed to persist?

**Answer:** No. `inner()` participates in `outer()`'s physical transaction; if outer rolls back, inner's changes are rolled back too.

**Scenario C.** An `afterCommit` callback prints `"COMMITTED"`, and then an email-sending task throws an exception. Can you conclude the DB rolled back?

**Answer:** No. The DB commit already succeeded before `afterCommit` ran. Email failure must be handled separately, avoiding non-idempotent write retries.

**Scenario D.** `entityManager.flush()` completed before `return`. The outer transaction is still open. Is another client guaranteed to see the new data?

**Answer:** No. Flush is not commit; data visibility depends on the isolation level, transaction state, and DB mechanism.

## Takeaways

- **Method body completion ≠ successful commit.**
- **Commit belongs to the physical transaction boundary**, not mechanically tied to every `return` of every annotated method.
- Distinguish `target return`, `proxy return`, and the **outer transaction**; relying solely on in-method logs, `save`, or `flush` is insufficient.
- When post-commit actions are needed, use appropriate hooks/transaction events; when durable cross-system delivery is needed, consider an outbox.

## Official references

- Spring Framework — [Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- Spring Framework — [Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- Spring Framework — [Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- Spring Framework — [`TransactionSynchronization` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
- Spring Boot — [Java and Maven requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
