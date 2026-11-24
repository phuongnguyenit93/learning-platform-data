# Opening a New Transaction for Post-Commit Tasks in Spring Framework

## 1. Why does a task running after commit still need a new transaction?

In Spring Framework, a business operation can publish an event inside a transaction and use `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` to perform work **only after the main transaction commits successfully**. However, "committed" **is not synonymous** with all resources and state related to the old transaction being cleaned up immediately.

At the moment a post-commit callback runs, transaction resources such as a JDBC `Connection` or persistence context may still be bound to the thread. A regular data-access call may continue participating in the old transaction context, while **there is no subsequent commit pass** to save new changes. This is especially dangerous when the listener writes additional audit logs, notification records, or processing state that the application expects to be persisted durably.

**The right way when writing to the database after commit:** call a method on **another Spring bean** annotated with `@Transactional(propagation = Propagation.REQUIRES_NEW)`. Spring creates an independent physical transaction for this task; if it succeeds it commits independently, and if it fails it rolls back independently. This approach is explicitly recommended by Spring in the Javadoc of `TransactionSynchronization.afterCommit()` and `afterCompletion()`.

Points to keep separate:

- **`AFTER_COMMIT`** is when the callback is invoked relative to the original transaction.
- **`REQUIRES_NEW`** is the propagation policy when starting a transaction-managed unit of work.
- `AFTER_COMMIT` **does not automatically create a new transaction**.
- `@Transactional` without specifying propagation defaults to `REQUIRED`. In a post-commit context, `REQUIRED` may join resources still bound to the just-finished transaction, resulting in writes that **do not commit as expected**.
- A new transaction **does not make the post-commit task an atomic part of the preceding transaction**. The main transaction has already committed; a post-commit error cannot revert previously committed data.

This article focuses on Spring's **imperative** transaction model with `PlatformTransactionManager`, Spring JDBC/JPA, and event listeners running synchronously in callbacks. For reactive applications, transactions live in the Reactor Context, so design accordingly rather than reasoning from `ThreadLocal`.

## 2. Understanding the `@TransactionalEventListener` lifecycle accurately

Suppose `OrderService.placeOrder()` is called through a Spring transaction proxy:

```text
Caller
  |
  v
@Transactional OrderService.placeOrder()
  |
  +-- BEGIN transaction T1
  |
  +-- INSERT order
  |
  +-- publishEvent(OrderPlaced)
  |     |
  |     +-- @TransactionalEventListener(AFTER_COMMIT)
  |           registers callback for transaction T1
  |
  +-- business method finishes
  |
  +-- COMMIT T1 succeeds
  |
  +-- run AFTER_COMMIT callback
  |     |
  |     +-- AuditService.saveAudit()
  |           @Transactional(REQUIRES_NEW)
  |             |
  |             +-- BEGIN independent transaction T2
  |             +-- INSERT audit
  |             +-- COMMIT T2
  |
  +-- complete callback / cleanup of T1
```

By default, `@TransactionalEventListener` uses the `AFTER_COMMIT` phase. If the event is published when **no transaction is active**, the listener will not run unless `fallbackExecution = true` is configured. With `fallbackExecution = true`, the listener can run immediately when there is no transaction, so the "only after commit" guarantee no longer holds.

Commonly used phases:

| `TransactionPhase` | When the listener runs | Notes |
| --- | --- | --- |
| `BEFORE_COMMIT` | Before the original transaction commits | Can still participate in the original transaction's work; not a post-commit phase. |
| `AFTER_COMMIT` | After the original transaction commits successfully | Use a new transaction for DB operations that must commit separately. |
| `AFTER_ROLLBACK` | After the original transaction rolls back | Can save failure/compensation info in a new transaction. |
| `AFTER_COMPLETION` | After the original transaction finishes, regardless of commit or rollback | Must clarify whether handling should run on both outcomes. |

**Technical detail:** Spring's `@TransactionalEventListener(AFTER_COMMIT)` is handled via transaction synchronization and is normally invoked in the transaction completion branch for the committed status. Therefore, it should not be equated exactly with implementing `TransactionSynchronization.afterCommit()` directly, even though both occur after commit. During post-completion callbacks, old resources may not yet be released, so the `REQUIRES_NEW` rule still applies.

## 3. Why can `@Transactional(REQUIRED)` mislead after commit?

Consider the following illustrative snippet (not a standalone program):

```java
@Component
class OrderListener {
    private final AuditService auditService;

    OrderListener(AuditService auditService) {
        this.auditService = auditService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void afterCommit(OrderPlaced event) {
        auditService.saveAudit(event.orderId());
    }
}

@Service
class AuditService {
    @Transactional // defaults to REQUIRED: not a safe choice here
    public void saveAudit(String orderId) {
        // JDBC/JPA insert audit row
    }
}
```

`REQUIRED` means: join an existing suitable transaction, or open a new one if none exists. In a post-commit callback, the original transaction **has already committed**, yet Spring may still hold resources and synchronization state while invoking the callback. DB access at this time may "join" the old resource and **have no new commit** for the operation just performed. In JPA, entity modifications may be visible in the persistence context without being flushed/committed as expected.

Replace with:

```java
@Service
class AuditService {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveAudit(String orderId) {
        // JDBC/JPA insert audit row
    }
}
```

This is also illustrative code; `OrderPlaced` and data-access operations are application-defined. Annotations require imports from `org.springframework.stereotype`, `org.springframework.transaction.annotation`, and `org.springframework.transaction.event`.

`REQUIRES_NEW` requires an **independent physical transaction**; Spring temporarily suspends/detaches the old transaction's resources if still bound, starts a new transaction for the unit of work, and commits/rolls back that unit when the method exits. With JDBC, the new transaction typically needs another connection. Hence, ensure the connection pool has sufficient capacity under concurrent load; do not treat a new transaction as free.

## 4. Runnable Java 17+ example: order transaction T1 and audit transaction T2

The example uses **Spring Framework 6.2.12**, **Spring JDBC**, and **in-memory H2**, without Spring Boot. It shows:

1. When `OrderService` commits successfully, the `AFTER_COMMIT` listener is invoked and `AuditWriter` creates a new transaction to write the audit.
2. When `OrderService`'s transaction rolls back, the `AFTER_COMMIT` listener does not run and there is no audit record for the failed order.
3. Both outcomes are verified via DB queries after the service completes.

Create the structure:

```text
after-commit-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/AfterCommitDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'after-commit-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'demo.AfterCommitDemo'
}
```

`src/main/java/demo/AfterCommitDemo.java`:

```java
package demo;

import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

public class AfterCommitDemo {

    public record OrderPlaced(String orderId) {}

    public static class OrderService {
        private final JdbcTemplate jdbc;
        private final ApplicationEventPublisher publisher;

        public OrderService(JdbcTemplate jdbc, ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.publisher = publisher;
        }

        @Transactional
        public void place(String orderId, boolean abort) {
            jdbc.update("insert into orders (id) values (?)", orderId);
            System.out.println("publisher: inserted " + orderId);

            publisher.publishEvent(new OrderPlaced(orderId));
            System.out.println("publisher: after publish " + orderId);

            if (abort) {
                throw new IllegalStateException("order aborted");
            }
        }
    }

    public static class AuditWriter {
        private final JdbcTemplate jdbc;

        public AuditWriter(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public void persist(String orderId) {
            jdbc.update("insert into audit_log (order_id) values (?)", orderId);
            System.out.println("writer: inserted audit " + orderId);
        }
    }

    public static class PostCommitListener {
        private final AuditWriter writer;

        public PostCommitListener(AuditWriter writer) {
            this.writer = writer;
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void afterCommit(OrderPlaced event) {
            System.out.println("listener: AFTER_COMMIT " + event.orderId());
            writer.persist(event.orderId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class AppConfig {

        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:after_commit_demo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        OrderService orderService(JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            return new OrderService(jdbc, publisher);
        }

        @Bean
        AuditWriter auditWriter(JdbcTemplate jdbc) {
            return new AuditWriter(jdbc);
        }

        @Bean
        PostCommitListener postCommitListener(AuditWriter writer) {
            return new PostCommitListener(writer);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            OrderService service = context.getBean(OrderService.class);

            jdbc.execute("create table orders (id varchar(40) primary key)");
            jdbc.execute(
                    "create table audit_log (order_id varchar(40) primary key)");

            service.place("A-1", false);
            System.out.println("after success: orders="
                    + jdbc.queryForObject(
                            "select count(*) from orders", Integer.class)
                    + ", audit="
                    + jdbc.queryForObject(
                            "select count(*) from audit_log", Integer.class));

            try {
                service.place("B-2", true);
            } catch (IllegalStateException ex) {
                System.out.println("caught: " + ex.getMessage());
            }

            System.out.println("after rollback: orders="
                    + jdbc.queryForObject(
                            "select count(*) from orders", Integer.class)
                    + ", audit="
                    + jdbc.queryForObject(
                            "select count(*) from audit_log", Integer.class));
        }
    }
}
```

Run with **JDK 17+** and Gradle installed:

```bash
gradle -q run
```

`System.out.println` lines from the application, in order:

```text
publisher: inserted A-1
publisher: after publish A-1
listener: AFTER_COMMIT A-1
writer: inserted audit A-1
after success: orders=1, audit=1
publisher: inserted B-2
publisher: after publish B-2
caught: order aborted
after rollback: orders=1, audit=1
```

Explanation:

1. `context.getBean(OrderService.class)` retrieves the object through Spring, allowing the transaction proxy to apply `@Transactional` on `place`. Do not use `new OrderService(...)` directly in a real program and expect the annotation to create transactions.
2. `publishEvent(...)` happens while the order's transaction T1 is still active. The `AFTER_COMMIT` listener **does not handle immediately at publication time**, so `publisher: after publish ...` appears before the listener line.
3. For `A-1`, T1 commits successfully. Spring triggers the `AFTER_COMMIT` callback, the listener calls `writer.persist(...)` through **another bean** with a transaction proxy, opening a new transaction T2. `audit_log` commits independently when `persist` exits. Thus the DB has `orders=1, audit=1`.
4. For `B-2`, `IllegalStateException` exits the `@Transactional` method. The default rollback rule for unchecked exceptions rolls back T1. The `AFTER_COMMIT` listener does not run for `B-2`; the DB still has one record per table.
5. `writer: inserted audit A-1` appears **inside** transaction T2, before the proxy commits T2. It is the `audit=1` query result after the service call finishes that shows data was durably saved in the demo.
6. `DriverManagerDataSource` is used for a short example; production applications usually use a connection pool like HikariCP with monitoring and proper resource limits.

In this example, the listener runs **synchronously inside the post-commit callback**, because there is no `@Async` or executor on the event multicaster. `REQUIRES_NEW` creates a new transaction, **not a new thread**: the two concepts are independent.

## 5. Why call another bean instead of `this.saveAudit()`?

By default, Spring applies `@Transactional` through proxies (e.g., JDK proxy or CGLIB proxy). An internal call from one method to another on the **same instance**, such as `this.saveAudit()`, usually **bypasses the transaction interceptor**.

Erroneous example:

```java
@Component
class WrongPostCommitListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void afterCommit(OrderPlaced event) {
        this.saveAudit(event.orderId());
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveAudit(String orderId) {
        // Has the annotation, but self-invocation does not trigger the proxy.
    }
}
```

This is only illustrative code with an application-defined `OrderPlaced` and corresponding Spring imports. `this.saveAudit(...)` is a direct Java call on the target, not passing through proxy advice. Therefore **you cannot conclude T2 was opened** even though the `REQUIRES_NEW` annotation appears in code.

The reliable approach is separating the two responsibilities:

```text
OrderService @Transactional(T1)
      |
      +-- publish event
             |
             +-- PostCommitListener.afterCommit(...)
                    |
                    +-- auditWriter.persist(...)
                           Spring proxy of AuditWriter
                               |
                               +-- @Transactional(REQUIRES_NEW) -> T2
```

Inject `AuditWriter` via constructor as in the complete example. Make the transactionally intercepted method `public` on a proxyable Spring-managed bean, and call it **through the bean proxy**. With AspectJ transaction weaving, self-invocation rules may differ; this article uses the common proxy mode.

## 6. How does `REQUIRES_NEW` differ from `REQUIRED`, `NESTED`, and `@Async`?

| Mechanism | Meaning | Suitable for post-commit DB writes? |
| --- | --- | --- |
| `Propagation.REQUIRED` | Joins an existing transaction if present, otherwise opens a new one. | **Do not rely on** in a post-commit callback while old resources are not yet cleaned up. |
| `Propagation.REQUIRES_NEW` | Always creates an independent physical transaction, suspending any existing transaction. | **Yes**, when a separate, explicitly managed commit is needed. |
| `Propagation.NESTED` | Uses a nested scope/savepoint if supported by the transaction manager, still within the outer physical transaction. | Does not replace an independent post-commit physical transaction. |
| `@Async` | Moves execution to an executor/another thread when the async proxy applies. | Does not define a transaction itself; typically paired with a separate transactional service. |
| `@TransactionalEventListener(AFTER_COMMIT)` | Specifies a callback after successful commit. | Determines timing, but by itself creates no new transaction. |

Some consequences:

- `REQUIRES_NEW` has its own transaction status, timeout, isolation, and rollback rules as configured. Once T2 commits, it is not rolled back just because T1 failed or vice versa.
- In a post-commit scenario, T1 has already committed successfully before T2's callback begins. If T2 fails, **T1 remains committed**; business requirements must decide whether to retry, alert, compensate, or record pending work.
- For `REQUIRES_NEW` calls *inside* an already-open T1 transaction, a second connection may be needed while T1 still holds the first. A pool that is too small under concurrent load can exhaust connections or cause deadlocks; connection limits and concurrency must be calculated.
- `@Async` running on another thread does not automatically carry the JDBC transaction, `EntityManager`, security context, or MDC from the event-publishing thread. Do not use thread switching as a "trick" instead of proper propagation design.

## 7. Post-commit failure: why can't the original transaction roll back?

Suppose T1 creates an order and commits. Then the callback calls T2 to write an audit, but the DB reports an error:

```text
T1: INSERT orders('A-1')  -> COMMIT succeeds
                             |
                             v
                  AFTER_COMMIT listener
                             |
                             v
                  T2: INSERT audit_log
                             |
                             x-- error / ROLLBACK T2
```

Order `A-1` still exists because T1 committed before T2 failed. There is no mechanism to automatically merge them into one atomic transaction across commit time. Even if an exception from the callback is thrown and surfaces to the caller, that **cannot undo T1's commit**. Exception routing/reporting depends on the specific callback; for example, `@TransactionalEventListener(AFTER_COMMIT)` is triggered during transaction completion, so listener errors may be logged by Spring without propagating back to the event publisher. Therefore, never use callback exceptions as a guarantee of work replay.

Failure behavior must be designed for post-commit tasks:

- **Idempotency:** use a business key or unique constraint (such as `audit_log.order_id` in the example) so reruns do not create duplicate records; on retry, distinguish "already processed" from other errors.
- **Observability:** log with `eventId`/`orderId`, metrics for failed task counts, processing duration, and alerts.
- **Bounded retries:** handle transient failures with backoff; never retry infinitely on a request thread or inside a transactional callback.
- **Persisted work queue / transactional outbox:** when post-commit work must not be lost, write an outbox record **inside T1 itself**, then an independent worker reads and sends/writes results. The outbox ensures business data and follow-up processing requests commit together. Delivery/completion marking still requires idempotency and retries.
- **Intentional compensation:** if business rules strictly require updating order status when a post-commit step fails, create an explicit new transaction for the compensating action; do not assume rolling back in time.

`REQUIRES_NEW` solves the **new commit boundary**, not crashes, retries, or exactly-once delivery. Spring Application Events are in-memory notifications, not a replacement for a durable message broker.

## 8. When to use `TransactionTemplate` instead of annotations?

In some cases you want a new transaction inside a callback without adding a separate bean; you can use `TransactionTemplate` with `REQUIRES_NEW` propagation. This calls the transaction manager directly, so it does not depend on calls going through an AOP proxy.

**Illustrative snippet** (dependencies and event are application-defined):

```java
@Component
class PostCommitAuditHandler {

    private final JdbcTemplate jdbc;
    private final TransactionTemplate transactionTemplate;

    PostCommitAuditHandler(JdbcTemplate jdbc,
            PlatformTransactionManager transactionManager) {
        this.jdbc = jdbc;
        this.transactionTemplate =
                new TransactionTemplate(transactionManager);
        this.transactionTemplate.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW);
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void handle(OrderPlaced event) {
        transactionTemplate.executeWithoutResult(status ->
                jdbc.update(
                        "insert into audit_log(order_id) values (?)",
                        event.orderId()));
    }
}
```

Import the corresponding types from `org.springframework.stereotype.Component`, `org.springframework.jdbc.core.JdbcTemplate`, `org.springframework.transaction.PlatformTransactionManager`, `org.springframework.transaction.TransactionDefinition`, `org.springframework.transaction.support.TransactionTemplate`, and `org.springframework.transaction.event.*`.

`TransactionTemplate.executeWithoutResult(...)` opens and completes a new transaction as configured; an exception thrown inside the callback can cause the new transaction to roll back. This is a clear option when you want programmatic transaction boundary control. Still, using an `AuditWriter` bean with `@Transactional(REQUIRES_NEW)` is often easier to read, test, and reuse.

## 9. Combining with asynchronous processing

For notifications, emails, or indexing, a post-commit listener can also be `@Async`:

```java
@Async("postCommitExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderPlaced event) {
    auditWriter.persist(event.orderId());
    // Continue handling other tasks if needed.
}
```

This is an **illustrative snippet**, requiring `@EnableAsync`, an executor bean named `postCommitExecutor`, a Spring-managed listener, and corresponding `OrderPlaced`/`auditWriter`. Spring registers the callback with the publisher's transaction first; when the post-commit phase arrives, the async proxy can submit listener execution to the executor. On the worker thread, transaction T1 is not carried over, so `auditWriter.persist(...)` remains the place declaring the needed transaction.

Points not to overlook:

- `@Async` works only if the call goes through Spring's async proxy; self-invocation bypasses the proxy in default mode.
- The thread pool may reject tasks or be shut down; in-memory events do not guarantee successful execution across crashes.
- Exceptions from `void` async methods normally go to `AsyncUncaughtExceptionHandler`/logs, rather than returning to the publisher like synchronous exceptions.
- Async tasks may finish after the request returns; tests must use a latch/future/Awaitility with a timeout rather than arbitrary `Thread.sleep()`.
- With `@TransactionalEventListener` using imperative transactions, callback registration relies on the publisher's transaction. If the *event publishing* step itself is moved to another thread **before commit**, the listener may not see the transaction and be skipped; distinguish async publishing from async post-commit processing.

Thus `AFTER_COMMIT` addresses **timing**, `REQUIRES_NEW` addresses the **transaction for data writes**, and `@Async` addresses the **execution thread**. They complement one another, but are not synonymous.

## 10. Practical testing and signs of bugs

A test suite for a post-commit flow should include:

1. **Successful commit:** start T1, publish event, commit; then verify both the business record and audit record exist. If the callback is synchronous, checking after the service call suffices; if async, await a completion signal with a timeout.
2. **T1 rollback:** induce an error in the original transaction, verify the `AFTER_COMMIT` listener does not write an audit.
3. **T2 rollback:** deliberately cause an error in `AuditWriter`, verify T2's changes are absent while T1's committed record remains.
4. **No-transaction context:** publish event outside a transaction; by default `@TransactionalEventListener` does not run. Test separately if using `fallbackExecution = true`.
5. **Self-invocation:** call a `REQUIRES_NEW` method via `this` to expose proxy bypass; tests should verify real post-commit data rather than merely checking an annotation's presence.
6. **Overload/connections:** measure behavior under concurrency, pool size, timeouts, and callback latency; do not assume `REQUIRES_NEW` reuses T1's connection for free.
7. **Long-lived failures:** test retry/idempotency or outbox if this is a task that must complete.

**Note on `@Transactional` tests:** A test method wrapped in `@Transactional` in Spring Test usually rolls back when the test ends. If you just call `publishEvent()` and assert immediately, the `AFTER_COMMIT` listener may **never have run**. To test the post-commit phase accurately, use a test without a default transaction wrapper, or use `TestTransaction.flagForCommit()` and `TestTransaction.end()` in a properly configured test.

Common errors:

| Symptom | Cause worth checking | Fix |
| --- | --- | --- |
| `AFTER_COMMIT` listener logs but audit does not persist | Written under `REQUIRED` while T1 resources are not yet cleaned up; no new commit | Move write to a `REQUIRES_NEW` bean or `TransactionTemplate`. |
| Has `REQUIRES_NEW` annotation but still does not open T2 | `this.method()` bypassed proxy | Extract `AuditWriter` into a Spring-managed bean and inject it. |
| Event published with no transaction so no callback runs | `@TransactionalEventListener` ignores by default | Publish inside a real transaction; enable `fallbackExecution` only if accepting different semantics. |
| T1 rolls back yet post-commit callback is expected to run | Wrong transaction phase | Use `AFTER_ROLLBACK` if handling on rollback is needed. |
| T2 fails yet T1 still exists | Two transactions commit independently | Design retries/compensation and failure monitoring; do not expect T1 rollback. |
| Load increase causes connection exhaustion | `REQUIRES_NEW` needs an independent connection while old resource is still held | Size connection pool capacity and limit concurrency. |
| Test does not see post-commit execution | Test transaction has not committed, or auto-rolled back | Finish a real transaction before asserting. |
| Duplicate execution after retry | Missing idempotency key | Add business key/unique constraint and retry strategy. |

## 11. Design checklist for post-commit tasks

Before shipping a post-commit listener to production, answer:

- Does the task **truly need to run after commit**, or must it share a transaction with the original change? If atomicity is needed, execute before commit in T1 or write an outbox record with T1.
- If the post-commit task writes to the DB, which **Spring-managed bean/proxy** defines the `REQUIRES_NEW` boundary?
- What happens if T2 fails? Are idempotency, retries, monitoring, and recovery state in place?
- Does the listener run synchronously or asynchronously? Could it slow down requests or exhaust connection/thread pools?
- Must execution survive crashes? If so, in-memory events are only part of the solution; an outbox and durable worker are usually needed.

**Adoption rule:** After T1 commits, to write post-commit data, create an independent T2 with `REQUIRES_NEW` (or an equivalent `TransactionTemplate`) and invoke it across the proper Spring transaction boundary. `AFTER_COMMIT` only picks the timing; T2 has its own commit/rollback outcome and needs its own failure-handling plan.

## References

- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework — `@TransactionalEventListener` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Framework — `TransactionSynchronization.afterCommit()` and `afterCompletion()`](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
- [Spring Framework — Transaction Propagation (`REQUIRED`, `REQUIRES_NEW`, `NESTED`)](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Proxying Mechanisms and self-invocation](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — Declarative transaction rollback rules](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
