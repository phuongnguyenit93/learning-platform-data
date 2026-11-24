# Rollback and Transaction-Bound Events in Spring Framework

## 1. What are transaction-bound events?

When a Spring application publishes an event using `ApplicationEventPublisher.publishEvent(...)` inside a `@Transactional` method, there are usually two very different requirements:

1. **React immediately when the event is published:** for example, updating another table in the same transaction. The default synchronous `@EventListener` runs right when the multicaster dispatches the event, even if the original transaction later rolls back.
2. **React based on the transaction outcome:** send confirmation only upon **successful commit**, or record an incident only when the transaction **rolls back**. `@TransactionalEventListener` binds listener invocation to an appropriate transaction phase (`TransactionPhase`).

An event being published **does not mean data changes have committed**. The event may have been created and regular listeners may have run, yet the transaction still rolls back afterward. Similarly, rollback does not automatically generate a new event: `@TransactionalEventListener(AFTER_ROLLBACK)` is called only if the corresponding event was published and registered with the transaction before the transaction finished.

This article focuses on **imperative** transactions managed by `PlatformTransactionManager`, such as `DataSourceTransactionManager` or `JpaTransactionManager`. In reactive Spring, transactions are managed via the Reactor Context and event-to-transaction binding differs.

## 2. Mechanism for binding listeners to commit/rollback outcomes

Spring supports four `TransactionPhase` values:

| Phase | When is the listener executed? | Typical scenario |
| --- | --- | --- |
| `BEFORE_COMMIT` | In the callback before attempting commit, while the transaction can still roll back | Validation, flush, or data updates that must belong to the main transaction |
| `AFTER_COMMIT` | After the transaction commits successfully | Sending confirmation notifications, triggering post-commit processing |
| `AFTER_ROLLBACK` | After the transaction has rolled back | Cleaning up temporary resources, recording a failed processing attempt |
| `AFTER_COMPLETION` | After the transaction completes, whether commit or rollback | General cleanup, statistics, or completion monitoring |

`@TransactionalEventListener` **defaults to `AFTER_COMMIT`**, rather than running immediately like `@EventListener`.

Illustrative flow:

```text
@Transactional service
    |
    +-- start transaction T1
    +-- modify data
    +-- publishEvent(OrderAttempted)
    |      |
    |      +-- @EventListener: handles immediately (if synchronous)
    |      |
    |      +-- @TransactionalEventListener:
    |             registers callback corresponding to T1
    |
    +-- service ends
           |
           +-- T1 commits successfully
           |      +-- AFTER_COMMIT
           |      +-- AFTER_COMPLETION
           |
           +-- T1 rolls back
                  +-- AFTER_ROLLBACK
                  +-- AFTER_COMPLETION
```

`BEFORE_COMMIT` occurs before the commit step and **is not proof that commit will succeed**; errors in this phase itself can still lead to rollback. `AFTER_COMPLETION` means the callback runs on both outcomes, yet a regular event-receiving listener method **is not directly passed the commit/rollback result code**. If you need to clearly distinguish the two branches, use two phase-specific listeners; if you need the lower-level status code, use `TransactionSynchronization.afterCompletion(int status)`.

### Listener syntax example

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
public void onRollback(OrderAttempted event) {
    // Invoked only after rollback of the transaction that registered the event.
}

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onCommit(OrderAttempted event) {
    // Invoked only after successful commit.
}

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
public void onCompleted(OrderAttempted event) {
    // Runs after the transaction completes with either outcome.
}
```

These are **illustrative methods**, which must reside in a Spring-managed bean; `OrderAttempted` is an application-defined event type. Import `TransactionalEventListener` and `TransactionPhase` from Spring Transaction.

## 3. What causes a transaction to roll back?

Do not equate **"an exception occurred"** with **"definitely rolled back"**. The outcome depends on the transaction manager, proxy boundaries, propagation, and rollback policy.

### 3.1. Default rules of `@Transactional`

With standard declarative transaction setup:

- Exceptions extending `RuntimeException` or `Error` that **escape across the `@Transactional` boundary** normally trigger rollback.
- Checked exceptions (such as `IOException`) **do not** trigger rollback by default, unless `rollbackFor` is declared, an appropriate rollback rule is used, or different default rollback rules are configured.
- If an exception **is caught and handled completely inside the transactional method**, the interceptor may see normal completion and attempt to commit.
- A transaction can be explicitly marked **rollback-only**, regardless of whether the method returns normally.

For example, with a checked exception in a service method:

```java
@Transactional(rollbackFor = IOException.class)
public void importOrders() throws IOException {
    // If IOException escapes the method,
    // the transaction will roll back per rollbackFor.
}
```

This is an illustrative snippet; import `java.io.IOException` and `org.springframework.transaction.annotation.Transactional`. Avoid choosing `rollbackFor = Exception.class` application-wide without reviewing the business meaning of each exception.

Marking rollback-only inside a Spring-managed transaction context:

```java
TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
```

This statement is appropriate only when executing inside a transaction context managed by the Spring transaction aspect; import `org.springframework.transaction.interceptor.TransactionAspectSupport`. It does not publish an event itself. A transaction marked rollback-only can roll back at the completion boundary even if the Java method throws no exception.

### 3.2. `REQUIRED` and `UnexpectedRollbackException`

In nested call structures, a `@Transactional(propagation = REQUIRED)` method participates in the outer physical transaction. If the inner scope marks the shared transaction rollback-only yet the outer caller catches the exception and still tries to commit, Spring can throw `UnexpectedRollbackException` at the outer commit boundary: the caller needs to know that commit was requested yet rollback actually occurred.

**Key takeaway:** An `AFTER_ROLLBACK` listener relies on the **actual transaction completion outcome**, regardless of whether the caller sees a specific exception. `AFTER_ROLLBACK` can run for rollback-only, timeout, commit errors leading to rollback, or other transaction manager rollback decisions.

### 3.3. Nested transactions and savepoints

`Propagation.NESTED` may use a savepoint inside the **same physical transaction**, depending on transaction manager support. Rolling back to a savepoint **is not necessarily** a full rollback of the outer transaction.

For instance, a small operation rolls back to a savepoint while the outer transaction T1 still commits. If an event was registered with T1's completion, do not assume T1's `AFTER_ROLLBACK` listener will run just because a savepoint rolled back. When savepoint observation is needed, Spring 6.2 provides `TransactionSynchronization.savepoint(...)` and `savepointRollback(...)` for appropriate cases; that is a different mechanism from `@TransactionalEventListener(AFTER_ROLLBACK)`.

Conversely, `Propagation.REQUIRES_NEW` opens a separate physical transaction: rollback of the new child transaction **does not automatically roll back the outer transaction**. Which transaction an event attaches to must be evaluated by the active context at `publishEvent()` time.

## 4. Runnable Java 17+ example: post-commit and post-rollback events

A plain Spring Framework example using `Spring JDBC` and in-memory H2, with no Spring Boot required. It demonstrates:

1. Creating order `ok-1` succeeds: only the `AFTER_COMMIT` listener runs.
2. Creating order `bad-1` then throwing `IllegalStateException`: the order-creation transaction rolls back, and only the `AFTER_ROLLBACK` listener runs.
3. The rollback listener writes a row to the `rollback_audit` table through a **new transaction** with `Propagation.REQUIRES_NEW`. The audit record persists even though the failed order record rolled back.

Project structure:

```text
transaction-rollback-events/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/RollbackEventDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'transaction-rollback-events'
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
    mainClass = 'demo.RollbackEventDemo'
}
```

`src/main/java/demo/RollbackEventDemo.java`:

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

public class RollbackEventDemo {

    public record OrderAttempted(String orderId) {}

    public static class OrderService {
        private final JdbcTemplate jdbc;
        private final ApplicationEventPublisher publisher;

        public OrderService(
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.publisher = publisher;
        }

        @Transactional
        public void place(String orderId, boolean reject) {
            jdbc.update("insert into orders (id) values (?)", orderId);
            System.out.println("publisher: inserted " + orderId);

            publisher.publishEvent(new OrderAttempted(orderId));
            System.out.println("publisher: after publish " + orderId);

            if (reject) {
                throw new IllegalStateException("rejected " + orderId);
            }
        }
    }

    public static class RollbackAuditWriter {
        private final JdbcTemplate jdbc;

        public RollbackAuditWriter(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public void recordFailure(String orderId) {
            jdbc.update(
                    "insert into rollback_audit (order_id) values (?)",
                    orderId);
            System.out.println("audit writer: recorded " + orderId);
        }
    }

    public static class LifecycleListener {
        private final RollbackAuditWriter writer;

        public LifecycleListener(RollbackAuditWriter writer) {
            this.writer = writer;
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void committed(OrderAttempted event) {
            System.out.println("commit listener: " + event.orderId());
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
        public void rolledBack(OrderAttempted event) {
            System.out.println("rollback listener: " + event.orderId());
            writer.recordFailure(event.orderId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class AppConfig {

        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:rollback_events;DB_CLOSE_DELAY=-1");
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
        OrderService orderService(
                JdbcTemplate jdbc, ApplicationEventPublisher publisher) {
            return new OrderService(jdbc, publisher);
        }

        @Bean
        RollbackAuditWriter rollbackAuditWriter(JdbcTemplate jdbc) {
            return new RollbackAuditWriter(jdbc);
        }

        @Bean
        LifecycleListener lifecycleListener(RollbackAuditWriter writer) {
            return new LifecycleListener(writer);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            OrderService service = context.getBean(OrderService.class);

            jdbc.execute("create table orders (id varchar(40) primary key)");
            jdbc.execute(
                    "create table rollback_audit (order_id varchar(40) primary key)");

            service.place("ok-1", false);
            System.out.println("success: orders=" + count(jdbc, "orders")
                    + ", rollback_audit=" + count(jdbc, "rollback_audit"));

            try {
                service.place("bad-1", true);
            } catch (IllegalStateException ex) {
                System.out.println("caught: " + ex.getMessage());
            }

            System.out.println("failure: orders=" + count(jdbc, "orders")
                    + ", rollback_audit=" + count(jdbc, "rollback_audit"));
        }
    }

    private static int count(JdbcTemplate jdbc, String tableName) {
        // tableName is only the constants "orders"/"rollback_audit" in the demo.
        return jdbc.queryForObject(
                "select count(*) from " + tableName, Integer.class);
    }
}
```

Run with JDK 17+ and Gradle installed:

```bash
gradle -q run
```

`System.out.println` lines of the program, in exact order:

```text
publisher: inserted ok-1
publisher: after publish ok-1
commit listener: ok-1
success: orders=1, rollback_audit=0
publisher: inserted bad-1
publisher: after publish bad-1
rollback listener: bad-1
audit writer: recorded bad-1
caught: rejected bad-1
failure: orders=1, rollback_audit=1
```

### Result analysis

**Success branch (`ok-1`):**

- `OrderService.place(...)` is called through the bean from the Spring context, so the transaction proxy starts T1.
- The order row is inserted and the event is published in T1. The transaction-bound listener only registers a callback, so `publisher: after publish ok-1` appears before the listener.
- T1 commits. `committed(...)` for `AFTER_COMMIT` runs, while `rolledBack(...)` does not run.
- The database has one order and no rollback audit row.

**Failure branch (`bad-1`):**

- The order row is inserted in T2 and the event is published while T2 is active.
- `IllegalStateException` escapes through the `@Transactional` method's proxy, so T2 rolls back under the default rule.
- After rollback, `rolledBack(...)` is invoked. `writer.recordFailure(...)` goes through another Spring bean with `@Transactional(REQUIRES_NEW)`, creating an independent transaction T3 to insert `rollback_audit` and commit.
- Order `bad-1` does not exist after rollback; audit row `bad-1` remains because it was committed by T3.
- The original exception is caught outside the service method, after the transaction interceptor has completed rollback and callbacks. Therefore, `caught: ...` appears after the listener and writer lines.

**Important note:** The log line `audit writer: recorded ...` prints inside transaction T3, before the writer's proxy commits T3. The proof that the audit was actually persisted is the `rollback_audit=1` query result after the method returns.

The example uses `DriverManagerDataSource` for ease of learning, with no connection pool. Production applications should use a bounded connection pool and monitor usage, especially when `REQUIRES_NEW` needs a second connection while the previous transaction's resource is still bound to the thread.

## 5. Why must writing data in an `AFTER_ROLLBACK` listener open a new transaction?

This is a critical pitfall in transaction synchronization:

> The transaction has already finished rolling back/committing, yet transaction resources may still be accessible during the completion callback. A DB call can attach to the old context even though **there is no subsequent commit**.

Hence code like the following is unreliable for persisting a post-rollback audit:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
public void onRollback(OrderAttempted event) {
    jdbc.update(
            "insert into rollback_audit (order_id) values (?)",
            event.orderId());
}
```

This is an illustrative snippet, not a standalone program. `JdbcTemplate` may find the resource bound to the just-rolled-back transaction and have no new transaction to commit the write operation. In a JPA environment, an `EntityManager` still linked to the old context can also cause confusion about whether the entity was persisted.

**The right way when a separate commit is needed:** move the write operation to a bean with a method:

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordFailure(String id) {
    // Insert into audit with an independent transaction.
}
```

Then invoke it **through a Spring bean proxy** from the listener. In the full example, that is `RollbackAuditWriter`.

Default `@Transactional` with `REQUIRED` propagation **does not substitute** for opening an independent transaction in a post-completion callback; old resources may still be bound to the thread. `REQUIRES_NEW` suspends/detaches the existing binding and creates another physical transaction. If T3 fails, the audit may be lost, yet T2's rollback state is never "undone" or turned into a commit.

You can use `TransactionTemplate` with `PROPAGATION_REQUIRES_NEW` to create a transaction programmatically:

```java
TransactionTemplate template = new TransactionTemplate(transactionManager);
template.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW);

template.executeWithoutResult(status ->
        jdbc.update("insert into rollback_audit(order_id) values (?)", id));
```

This is an illustrative snippet requiring `transactionManager`, `jdbc`, and `id` variables along with `TransactionTemplate` and `TransactionDefinition` imports. Its advantage is not depending on calling another bean to apply transactional advice. With `@Transactional` on a method, avoid self-invocation like `this.recordFailure(...)`, as the transaction proxy can be bypassed.

## 6. Is a regular `@EventListener` "retracted" on rollback?

**No.** A regular `@EventListener` is invoked synchronously when `publishEvent()` occurs. Spring does not "go back in time" to undo side effects the listener already performed.

Example:

```java
@EventListener
public void onOrderAttempted(OrderAttempted event) {
    emailClient.sendMessage(event.orderId());
}
```

This is illustrative code: `emailClient` is application-defined. If the email is sent **before** the DB rolls back, rollback cannot recall the email. Similarly, an HTTP call or message already sent to a broker is not automatically rolled back by a JDBC transaction. Therefore, a regular synchronous listener should perform external pre-commit actions only when that consequence is truly acceptable.

Conversely, if a synchronous `@EventListener` uses the **same JDBC transaction** to write an internal table, that write can roll back together with the publisher. That is the difference between **side effects participating in the same transaction** and **side effects outside the transaction**.

| Scenario | Event/listener | Effect when T1 rolls back |
| --- | --- | --- |
| Synchronous listener using the same JDBC transaction | `@EventListener` | DB writes belonging to T1 roll back with T1 |
| Synchronous listener calling an external service | `@EventListener` | HTTP/email already sent is not automatically undone |
| Listener registered for after commit | `@TransactionalEventListener(AFTER_COMMIT)` | Does not run when T1 rolls back |
| Listener registered for after rollback | `@TransactionalEventListener(AFTER_ROLLBACK)` | Runs when the event's bound transaction rolls back |
| Listener running on both outcomes | `@TransactionalEventListener(AFTER_COMPLETION)` | Runs after T1 completes |
| Post-rollback listener writing DB via T3 | `@Transactional(REQUIRES_NEW)` in another bean | T3 commits/rolls back independently of T1 |

## 7. Registration condition: the event must be published inside a suitable transaction

`@TransactionalEventListener` is meaningful only when the event is published within a suitable active transaction context. Without a transaction, the listener **does not run** by default.

For example, this call outside a transaction:

```java
publisher.publishEvent(new OrderAttempted("no-tx"));
```

If there is no transaction and the listener uses default configuration, neither `AFTER_COMMIT` nor `AFTER_ROLLBACK` is invoked. To allow fallback:

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_ROLLBACK,
        fallbackExecution = true)
public void handle(OrderAttempted event) {
    // Can run even when there is no transaction; in that case
    // there is no actual rollback to wait for or guarantee.
}
```

This is only illustrative code: `OrderAttempted` is application-defined. `fallbackExecution = true` changes business semantics: when there is no transaction, the callback may execute via the fallback path, **with no proof of rollback**. For tasks that must run only on a real rollback, usually keep the default `false` and ensure the publisher actually runs inside a transaction.

Situations where you think you are publishing inside a transaction when no expected transaction actually exists:

- A `@Transactional` method is called via `this.method()` on the same bean, bypassing the proxy.
- The bean was created with `new` rather than managed by Spring.
- The transaction exists only on **another thread**, e.g., the event is published from an `@Async` method or another `Executor`. Thread-bound imperative transactions do not automatically propagate to a new thread.
- The method has no actual transaction due to misconfigured transaction manager/proxy or executing outside transaction boundaries.

Since Spring 6.1, `@TransactionalEventListener` also supports reactive transactions, yet reactive transactions live in the **Reactor Context**. When using `ReactiveTransactionManager`, the transaction context must be passed in the event's source via a Spring-supported API, such as `TransactionalEventPublisher`, rather than relying on thread-bound `TransactionSynchronizationManager`. The JDBC example in section 4 **does not use reactive transactions**.

## 8. Callback errors, rollback-only, and processing order

### 8.1. Exceptions in `BEFORE_COMMIT`

A `BEFORE_COMMIT` listener runs before commit; an appropriate runtime exception can propagate to the commit caller and lead to rollback. If logic needs to prevent the transaction from committing, this may be a place to consider, while still designing errors per transaction rules and callback timing.

An exception in `AFTER_ROLLBACK` or `AFTER_COMPLETION` happens **after** the transaction's outcome has been decided. In the `TransactionSynchronization.afterCompletion(...)` mechanism, runtime exceptions are logged by Spring and **are not guaranteed to propagate back to the caller**. Therefore, do not use whether an exception reaches the caller to infer that the post-rollback listener finished successfully.

### 8.2. A post-rollback callback does not roll back a second time

Once T1 has rolled back, an error in an `AFTER_ROLLBACK` listener **cannot roll back T1 again**. If the listener creates transaction T3 to write an audit and T3 fails, only T3 rolls back; T1 remains rolled back from the earlier outcome.

Thus, if rollback audits are critical data, monitoring, retries, and durable persistence of work requests are necessary. In-memory callbacks do not guarantee successful execution if the application crashes or the process is killed at that moment.

### 8.3. `@Order` and multiple listeners

`@Order` can adjust the order of corresponding callbacks/listeners in Spring, but it does not turn multiple listeners into one atomic transaction. One failing listener can affect others differently depending on phase and invocation mechanism; do not rely on implicit ordering or "all succeed together" assumptions. If steps must commit together, write them in **one explicit transaction** or an orchestrated flow with error control.

### 8.4. Transaction rollback is not every nested rollback

If an operation runs in `REQUIRES_NEW`, callbacks bound to the new transaction are handled according to that new transaction's outcome. If business logic in the outer transaction rolls back while the inner transaction already committed independently, the `AFTER_COMMIT` callback for the inner transaction may already have run. With `NESTED`, rolling back to a savepoint does not necessarily complete the outer transaction. To ensure clear semantics, explicitly track *which transaction owns the event* and *which scope starts/ends the transaction*.

## 9. Distinguishing `@Async` from transaction-phase listeners

`@Async` addresses the **execution thread**, while `@TransactionalEventListener` addresses **timing relative to the transaction outcome**.

Illustrative example:

```java
@Async("eventExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void notifyAfterCommit(OrderAttempted event) {
    // Once the post-commit callback is triggered, @Async can
    // dispatch the handling to the named executor.
}
```

Requires `@EnableAsync`, an `eventExecutor` bean, and the listener being a Spring-managed bean. This snippet does not automatically guarantee durable delivery: if the process dies before the task runs, the work can be lost.

For `AFTER_ROLLBACK`, if asynchronous handling is needed yet an audit must be saved:

```java
@Async("eventExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
public void onRollbackAsync(OrderAttempted event) {
    auditWriter.recordFailure(event.orderId());
}
```

This is an illustrative snippet, assuming `auditWriter` is a separate bean with a `@Transactional(REQUIRES_NEW)` method. `@Async` does not automatically create a transaction; the worker thread does not inherit the publisher thread's JDBC transaction. When handling post-rollback on another thread, the new transaction should still be declared on the service interacting with the database.

**Warning:** If `publishEvent()` itself happens on another thread before the original transaction completes, the transaction-bound listener may not be registered because the new thread lacks the original transaction's context. Clearly distinguish "moving the listener to async after callback registration" from "moving the publisher to another thread".

## 10. Reliable design when reacting to rollback

Not all post-rollback work belongs in `@TransactionalEventListener`.

**Suitable for in-memory callbacks:**

- Best-effort cleanup of memory or temporary resources.
- Recording debug metrics or logs; accepting that events may be lost if the process dies.
- Updating test state or telemetry that does not affect business correctness.
- Simple audit writes via a new transaction when error policies/monitoring and callback limitations are acceptable.

**Requires a more durable mechanism:**

- Mandatory emails/notifications that must not be lost.
- Recording critical payment/failure events for reconciliation.
- Syncing with external systems requiring retries, backoff, and idempotency.
- Long-running work, SLA requirements, or recovery across restarts.

A `transactional outbox` typically writes records to send in the **same transaction as the business change**. If the transaction rolls back, **the outbox record also rolls back**, so an outbox does not automatically capture every failure/rollback that occurred. To record an important rollback, design an independent transaction, an external durable event source, or a business state model that reflects pre-/post-transaction failures as required. Do not use an outbox as the default answer for "saving the rolled-back transaction itself".

If you need to log a failed transaction to the DB without relying on callbacks, catch the error at an orchestration layer **outside transaction T1** and call an audit service with a new transaction. Ensure transaction T1 has actually finished before writing the audit, and clearly define handling if the audit also fails.

## 11. Testing `AFTER_ROLLBACK` properly

Tests should focus on **actual post-transaction state**, not only checking whether the listener method was called.

1. **Successful commit:** publish event inside T1, complete commit; `AFTER_COMMIT` runs and `AFTER_ROLLBACK` does not.
2. **Rollback via unchecked exception:** publish event, throw `RuntimeException` out of `@Transactional`; verify original DB changes disappear and the rollback listener is invoked.
3. **Rollback-only:** mark transaction rollback-only via Spring API, end transaction; verify rollback callback without relying on an escaping exception.
4. **Checked exception:** compare with/without `rollbackFor`; verify actual commit/rollback outcome instead of assuming checked exceptions always roll back.
5. **No transaction:** publish event outside T1; listener with `fallbackExecution=false` does not run.
6. **Audit via `REQUIRES_NEW`:** rollback listener writes audit independently; when audit succeeds, its row commits despite T1 rolling back.
7. **Error in audit T3:** verify T3 rolls back and T1's outcome is unchanged; check logs, metrics, and recovery mechanisms.
8. **Multiple/nested transactions:** test `REQUIRES_NEW` and `NESTED` separately per transaction manager, especially savepoint rollbacks.

### Be careful with `@Transactional` on tests

In Spring Test, a test method annotated with `@Transactional` is normally rolled back automatically when the test finishes. If you simply publish an event and assert right inside the test, the `AFTER_ROLLBACK` callback **may not have run yet**, because the transaction has not completed. Likewise, `AFTER_COMMIT` will not run if the test rolls back instead of committing.

You can use `TestTransaction.flagForRollback()` followed by `TestTransaction.end()` to actively complete the transaction in a properly configured test:

```java
TestTransaction.flagForRollback();
TestTransaction.end();

// After the test transaction finishes, verify the rollback outcome.
```

This is illustrative code requiring Spring Test to manage the test transaction and importing `org.springframework.test.context.transaction.TestTransaction`; `spring-test` must be on the test classpath. Avoid relying solely on `Thread.sleep()` to wait for async callbacks. If a listener is asynchronous, use a latch/future/Awaitility with a timeout for controlled waiting.

## 12. Common errors

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| `AFTER_ROLLBACK` is not invoked | No transaction when publishing, event not published, or T1 committed | Verify proxy invocation, `publishEvent()` timing, and T1 status |
| Listener runs immediately even though outcome should be awaited | Used `@EventListener` instead of `@TransactionalEventListener` | Choose `AFTER_COMMIT`, `AFTER_ROLLBACK`, or `AFTER_COMPLETION` |
| Post-rollback audit fails to persist | DB operation uses ended old transaction resources | Open a new `REQUIRES_NEW` transaction in another bean |
| `REQUIRES_NEW` annotation present yet ineffective | Self-invocation `this.recordFailure()` bypassed proxy | Inject service/bean and call via Spring proxy or use `TransactionTemplate` |
| External data sent even though T1 rolled back | Regular `@EventListener` or external I/O occurred before commit | Execute only after commit, or use a suitable durable mechanism |
| Callback errors yet caller receives no exception | Post-completion callback may log error without propagating | Observe errors separately; do not infer from caller outcome |
| Savepoint rolled back yet rollback listener did not run | Outer transaction has not rolled back/completed | Distinguish `NESTED` savepoint from transaction completion |
| `@Transactional` test does not see callback | Test transaction still open or auto-completes after assertion | End the test transaction explicitly before asserting |
| Listener sees data "still there" yet write does not commit | Old resources still accessible in callback | Use `REQUIRES_NEW` for new DB operations |
| Process crash loses callback | Spring events live in memory only | Design persisted work/audit or another recovery model |

## 13. Choosing a solution by business requirement

- **Need DB updates atomic with business operation:** use synchronous `@EventListener` inside the current transaction or call a service directly inside T1. Avoid non-rollbackable external I/O.
- **Work only if commit succeeds:** use `@TransactionalEventListener(AFTER_COMMIT)` and open a new transaction if DB writes are needed after commit.
- **Work only if transaction rolls back:** use `@TransactionalEventListener(AFTER_ROLLBACK)`; if saving an audit, use a new transaction and have an error-handling plan.
- **Need to know transaction ended regardless of outcome:** use `AFTER_COMPLETION`; when status must be distinguished, choose two separate phases or use `TransactionSynchronization`.
- **Must guarantee no data/work loss:** use an independent transaction for error records, an outbox inside the appropriate transaction, a message broker, or a persistent queue matching business semantics; add retry/idempotency/monitoring.

Principle to remember: **An event can be published before a transaction succeeds; rollback only undoes changes that actually belong to the transaction.** Choose the listener phase for the desired outcome, clearly identify which transaction owns the event, and create a new transaction whenever a post-completion callback needs to write durable data.

## Official references

- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework — `@TransactionalEventListener` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Framework — `TransactionSynchronization` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
- [Spring Framework — Declarative transaction rollback rules](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — Transaction propagation](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Proxying and self-invocation](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
