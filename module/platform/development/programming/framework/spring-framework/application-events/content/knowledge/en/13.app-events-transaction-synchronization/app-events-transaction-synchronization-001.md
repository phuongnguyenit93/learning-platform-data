# Mechanism for Binding Listeners to Transactions in Spring Application Events

## 1. The problem that transaction-bound listeners solve

When a business operation updates the database and publishes an event, the event may be sent **before the transaction commits**. For example: a service saves an order, publishes `OrderCreated`, and then throws an exception that causes the transaction to roll back. If a regular `@EventListener` sends an email immediately upon receiving the event, the customer may receive a notification about an order that was never successfully persisted.

Spring Framework's `@TransactionalEventListener` allows **binding event processing timing to a phase in the transaction lifecycle**. By default, the listener processes the event only **after the transaction commits successfully**. This mechanism relies on *transaction synchronization*: Spring registers a callback with the active transaction and invokes the callback at the appropriate time.

Three statements must be distinguished:

1. **The event has been published**: the service has called `ApplicationEventPublisher.publishEvent(...)`.
2. **The event has been registered with the transaction**: Spring has bound the corresponding callback to the current transaction.
3. **The listener has executed successfully**: the callback has run and its side effects have completed; this cannot be inferred automatically from the previous two statements.

This article explains the registration mechanism, the phases, a runnable Java 17+ example verifying commit/rollback, and the limitations when using `@Async`, reactive transactions, or external side effects.

## 2. How `@EventListener` and `@TransactionalEventListener` differ

Regular listener:

~~~java
// Illustrates a method inside a Spring bean.
@EventListener
public void handle(OrderCreated event) {
    sendEmail(event.orderId());
}
~~~

With the default synchronous multicaster, `handle` is called immediately during `publishEvent` (even while the publisher's transaction is still open). A rollback that occurs afterward **does not undo the email**.

Transaction-bound listener:

~~~java
// Illustrates a method inside a Spring bean.
@TransactionalEventListener
public void handleAfterCommit(OrderCreated event) {
    sendEmail(event.orderId());
}
~~~

When published within a valid transaction, Spring **defers** calling `handleAfterCommit` until the `AFTER_COMMIT` phase. If the transaction rolls back, this listener does not run. `@TransactionalEventListener` does not create a transaction itself; it observes the lifecycle of the transaction in which the publisher is participating.

The two snippets above are illustrative; `OrderCreated`, `sendEmail`, and the imports must be defined when integrated into an application.

| Aspect | Regular `@EventListener` | `@TransactionalEventListener` |
| --- | --- | --- |
| Invocation timing | When the event is published, according to the multicaster mode | When the chosen `TransactionPhase` is reached |
| Requires active transaction | No | Yes by default |
| On rollback | Listener may have already run before rollback | Only listeners choosing `AFTER_ROLLBACK`/`AFTER_COMPLETION` are invoked on the rollback path |
| When published outside a transaction | Handled normally | Ignored unless `fallbackExecution=true` |
| Guarantees replay after crash | No | No |

## 3. How Spring binds events to transactions

In the thread-bound synchronous transaction model (typically managed by `PlatformTransactionManager`), the main components are:

- **`ApplicationEventPublisher`**: the event publishing point, typically implemented by `ApplicationContext`.
- **`TransactionalApplicationListenerMethodAdapter`**: the adapter Spring creates for a `@TransactionalEventListener` method; it receives the event and knows which phase the listener wants to run in.
- **`TransactionSynchronizationManager`**: holds resources and synchronization callbacks bound to the current transaction/thread.
- **`TransactionSynchronization`**: the callback interface such as `beforeCommit`, `afterCommit`, `afterCompletion`.
- **`PlatformTransactionManager`**: executes commit/rollback and coordinates the callbacks.

### 3.1. Processing flow with `AFTER_COMMIT`

1. Spring starts or participates in a transaction, for example when a service runs through a `@Transactional` proxy or `TransactionTemplate`.
2. Business logic writes data and calls `publishEvent(new OrderCreated(id))` **within that transaction context**.
3. The multicaster dispatches the event to the `@TransactionalEventListener` adapter. The adapter receives the event and registers a synchronization instead of immediately executing the listener method body.
4. When the business code finishes, the transaction manager executes the commit preparation, commit/rollback, and completion callback steps.
5. If the transaction **commits successfully**, the callback corresponding to `AFTER_COMMIT` runs. If the transaction **rolls back**, the `AFTER_COMMIT` callback does not run; the `AFTER_ROLLBACK` or `AFTER_COMPLETION` callback is selected according to configuration.

~~~text
@Transactional service
    |
    +-- INSERT data
    |
    +-- publishEvent(OrderCreated)
    |       |
    |       +-- Transactional listener adapter
    |               |
    |               +-- register synchronization with the current transaction
    |
    +-- business method ends
            |
      Transaction manager
            |
            +-- beforeCommit / beforeCompletion
            +-- COMMIT or ROLLBACK
            +-- completion callback
                    |
                    +-- invoke listeners matching the phase and status
~~~

**Hook distinction:** In Spring, `TransactionPhase.AFTER_COMMIT` of `@TransactionalEventListener` is handled as a special case of the **`TransactionSynchronization.afterCompletion(STATUS_COMMITTED)`** sequence, not directly equivalent to the `TransactionSynchronization.afterCommit()` method. Therefore, do not infer the execution order of different listeners and callbacks solely based on the wording "after commit".

This is an **in-memory registration** mechanism tied to the current transaction. It does not automatically persist the event as a durable message to replay after a process crash.

### 3.2. Conditions for registering synchronization

With thread-bound transactions, Spring needs active synchronization **and an actual running transaction** in the event publishing context. Calling `publishEvent` does not open a transaction; running code on another thread does not automatically inherit the original thread's transaction either.

If no suitable transaction exists, the listener **does not run** by default. There is no mechanism to "wait for the next transaction".

## 4. The four `TransactionPhase` values and their trigger points

| Phase | Timing | Appropriate use cases | What must not be inferred |
| --- | --- | --- | --- |
| `BEFORE_COMMIT` | Before the transaction actually commits | Consistency checks, finalizing data within the transaction | Does not guarantee the subsequent commit will succeed |
| `AFTER_COMMIT` (default) | Once the transaction has committed successfully | Reacting to confirmed data, updating cache, or triggering other tasks | Does not guarantee side effects are saved/retried if the process crashes |
| `AFTER_ROLLBACK` | Once the transaction has rolled back | Observing failures, cleaning up temporary resources | There is no old transaction left to continue writing and committing |
| `AFTER_COMPLETION` | After the transaction ends via commit or rollback | General cleanup, metrics for both branches | Does not convey status through the event parameter itself; additional logic is needed to distinguish |

Syntax of the four phases:

~~~java
@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
public void before(OrderCreated event) { /* ... */ }

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void committed(OrderCreated event) { /* ... */ }

@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
public void rolledBack(OrderCreated event) { /* ... */ }

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
public void completed(OrderCreated event) { /* ... */ }
~~~

These are illustrative snippets for methods belonging to a Spring bean. To use them in real code, you need to define the event type, imports, and the bean owning the methods.

### `BEFORE_COMMIT` and errors

`BEFORE_COMMIT` is triggered before the actual commit operation. The listener can throw an exception causing the transaction to roll back; even if the listener succeeds, the database commit can still fail. Therefore, sending an email or calling a payment API that cannot be undone in this phase is dangerous: the side effect may occur even though the data is rolled back.

### `AFTER_COMMIT` and data access

By Spring's contract, when running a callback in `AFTER_COMMIT`, `AFTER_ROLLBACK`, or `AFTER_COMPLETION`, the transaction has already committed/rolled back, **but resources may still be bound and accessible**. A repository/JDBC call inside the callback may still participate in the old transaction resource, while **there is no subsequent commit**. Therefore, do not assume a data modification performed in `AFTER_COMMIT` will be persisted.

If you need to write data after commit, use an **independent transaction**, for example calling another Spring service annotated with `@Transactional(propagation = Propagation.REQUIRES_NEW)` **through a proxy**, or configuring `TransactionTemplate` with `PROPAGATION_REQUIRES_NEW`.

## 5. Runnable Java 17+ example: commit, rollback, and outside transaction

The example uses Spring Framework 6.2.12, H2, and `DataSourceTransactionManager`. Spring Boot is not required. `TransactionTemplate` opens transactions explicitly, and four listeners increment counters by phase. We print **after the transaction ends** so we do not depend on callback ordering within the same stage.

Structure:

~~~text
transaction-event-demo/
├── pom.xml
└── src/main/java/demo/TransactionEventDemo.java
~~~

### 5.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>transaction-event-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
            <scope>runtime</scope>
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
~~~

### 5.2. `src/main/java/demo/TransactionEventDemo.java`

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

public class TransactionEventDemo {
    public record TicketCreated(long ticketId) {}

    public static class Observations {
        final AtomicInteger before = new AtomicInteger();
        final AtomicInteger committed = new AtomicInteger();
        final AtomicInteger rolledBack = new AtomicInteger();
        final AtomicInteger completed = new AtomicInteger();
    }

    @Configuration
    public static class Config {
        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:txevents;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        public TransactionTemplate transactionTemplate(PlatformTransactionManager tm) {
            return new TransactionTemplate(tm);
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        public Observations observations() {
            return new Observations();
        }

        @Bean
        public PhaseListeners phaseListeners(Observations obs) {
            return new PhaseListeners(obs);
        }
    }

    public static class PhaseListeners {
        private final Observations obs;

        public PhaseListeners(Observations obs) {
            this.obs = obs;
        }

        @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
        public void before(TicketCreated event) {
            obs.before.incrementAndGet();
        }

        // AFTER_COMMIT is the default phase.
        @TransactionalEventListener
        public void afterCommit(TicketCreated event) {
            obs.committed.incrementAndGet();
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
        public void afterRollback(TicketCreated event) {
            obs.rolledBack.incrementAndGet();
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
        public void afterCompletion(TicketCreated event) {
            obs.completed.incrementAndGet();
        }
    }

    private static void show(String label, Observations o) {
        System.out.printf(
            "%s: before=%d commit=%d rollback=%d completion=%d%n",
            label, o.before.get(), o.committed.get(),
            o.rolledBack.get(), o.completed.get());
    }

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = ctx.getBean(JdbcTemplate.class);
            TransactionTemplate tx = ctx.getBean(TransactionTemplate.class);
            Observations obs = ctx.getBean(Observations.class);

            jdbc.execute("CREATE TABLE tickets (id BIGINT PRIMARY KEY, title VARCHAR(60))");

            tx.executeWithoutResult(status -> {
                jdbc.update("INSERT INTO tickets (id, title) VALUES (?, ?)",
                        101L, "created");
                ctx.publishEvent(new TicketCreated(101L));
                show("inside-commit", obs);
            });
            show("after-commit", obs);
            System.out.println("ticket-101=" + jdbc.queryForObject(
                "SELECT COUNT(*) FROM tickets WHERE id = 101", Integer.class));

            tx.executeWithoutResult(status -> {
                jdbc.update("INSERT INTO tickets (id, title) VALUES (?, ?)",
                        102L, "will-rollback");
                ctx.publishEvent(new TicketCreated(102L));
                status.setRollbackOnly();
                show("inside-rollback", obs);
            });
            show("after-rollback", obs);
            System.out.println("ticket-102=" + jdbc.queryForObject(
                "SELECT COUNT(*) FROM tickets WHERE id = 102", Integer.class));

            // Event outside transaction: fallbackExecution=false by default.
            ctx.publishEvent(new TicketCreated(103L));
            show("outside-tx", obs);
        }
    }
}
~~~

Run in the directory containing `pom.xml` (JDK 17+ and Maven):

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.TransactionEventDemo
~~~

Program `stdout` lines:

~~~text
inside-commit: before=0 commit=0 rollback=0 completion=0
after-commit: before=1 commit=1 rollback=0 completion=1
ticket-101=1
inside-rollback: before=1 commit=1 rollback=0 completion=1
after-rollback: before=1 commit=1 rollback=1 completion=2
ticket-102=0
outside-tx: before=1 commit=1 rollback=1 completion=2
~~~

**Detailed explanation:**

- **`inside-commit`**: the event is published while in the middle of the transaction, but the transactional listener has only been registered; no phase has been reached yet so all counters remain 0.
- **`after-commit`**: `BEFORE_COMMIT`, `AFTER_COMMIT`, and `AFTER_COMPLETION` have run; `AFTER_ROLLBACK` did not run. The record `ticket-101=1` persists after commit.
- **`inside-rollback`**: callbacks for the second event are still waiting for the transaction to finish.
- **`after-rollback`**: because of `status.setRollbackOnly()`, the `AFTER_ROLLBACK` and `AFTER_COMPLETION` counters increment; `BEFORE_COMMIT` does not increment. The record `ticket-102=0` was rolled back.
- **`outside-tx`**: the third event is published outside a transaction; none of the four listeners run because `fallbackExecution` defaults to `false`.

The example does not need `@EnableTransactionManagement` because it uses `TransactionTemplate` directly rather than relying on AOP `@Transactional` on a service. In a real application using `@Transactional`, transaction management must be enabled according to framework/Spring Boot configuration and called through a Spring proxy.

## 6. What does the listener do when there is no transaction?

By default, `@TransactionalEventListener` ignores events published outside a transaction. To allow running even when there is no transaction, use `fallbackExecution=true`:

~~~java
// Illustrative snippet for a Spring bean.
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = true)
public void onCreated(OrderCreated event) {
    process(event);
}
~~~

When there is a transaction, the listener still waits for commit. When **there is no transaction**, it runs during the event publication via the fallback path: at that point there is no commit to wait for. That is a **change in business semantics**, not merely a setting "to avoid losing events".

If a listener unexpectedly does not run, check the transaction boundary, AOP proxy, propagation, and thread before enabling fallback.

## 7. When data needs to be written after commit: open a new transaction

After commit, old resources may still be bound while the callback runs. To reliably write an audit record or update another table after commit, call a separate service with `REQUIRES_NEW` propagation:

~~~java
// Illustrates the idea across two separate Spring beans (not standalone).
@Service
public class AuditWriter {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void persist(String orderId) {
        // auditRepository.save(new Audit(...));
    }
}

@Component
public class AuditListener {
    private final AuditWriter auditWriter;

    public AuditListener(AuditWriter auditWriter) {
        this.auditWriter = auditWriter;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onCreated(OrderCreated event) {
        auditWriter.persist(event.orderId());
    }
}
~~~

It must be separated into a distinct bean so that the call to `persist` goes through a Spring AOP proxy. Calling `this.persist()` within the same bean under standard proxy mode bypasses the advice. The example above uses `OrderCreated` and the repository as conceptual names; the actual classes and imports must be declared in an application.

Note: a successful `REQUIRES_NEW` transaction **does not guarantee atomicity** with the previously committed business transaction. If the audit record must be written atomically with the order change, write the audit **inside the main transaction**, or use an outbox record within the same transaction.

## 8. `@Async`, transaction context, and reactive transactions

### 8.1. With `@Async`

With `PlatformTransactionManager`, the transaction context is typically thread-bound. Offloading `publishEvent` to another executor does not automatically carry the transaction from the original thread. If an event is published from a thread without a transaction, transactional listeners may be skipped.

For `@TransactionalEventListener` combined with `@Async`, the listener body may be scheduled to run after the phase is triggered. However, the thread executing the asynchronous callback **does not automatically inherit the old transaction**. Therefore, do not infer that the listener has finished running when `TransactionTemplate.execute` returns, and do not use `@Order` as a completion order guarantee for async tasks.

Configuring the event multicaster with an executor is also not a valid way to automatically transfer a thread-bound transaction to another thread. Transactional listeners have a synchronization registration mechanism suited to the transaction context; you must understand how executor configuration interacts with each type of listener.

### 8.2. Reactive transactions

Since Spring Framework 6.1, `@TransactionalEventListener` also supports transactions managed by `ReactiveTransactionManager`. Reactive transactions live in the **Reactor Context** instead of `ThreadLocal`. When publishing a reactive event, the transaction context must be carried in the event's `source` according to the API contract.

Spring provides `org.springframework.transaction.reactive.TransactionalEventPublisher` to help carry the `TransactionContext` into the appropriate event. Do not apply thread-bound `TransactionSynchronizationManager` access patterns verbatim to a reactive pipeline. Ensure the pipeline is actually subscribed within the reactive transaction boundary and that the event has the correct context source.

### 8.3. Propagation, nested transactions, multiple publishers

- `PROPAGATION_REQUIRED` normally joins the existing transaction; the event waits for completion of the shared **physical transaction**, not for a sub-method return if the outer transaction remains open.
- `PROPAGATION_REQUIRES_NEW` opens an independent transaction; events bound to the inner transaction may be processed after the inner commit even if the outer transaction later rolls back.
- With savepoint/`NESTED`, do not assume registered events are automatically discarded when rolling back to a savepoint; verify your transaction manager's semantics and design explicit callbacks if business logic depends on it.
- With multiple publishers/threads, publication timing and completion order are not automatically synchronized globally. `@Order` only helps prioritize listeners within the scope of the corresponding dispatch/synchronization mechanism.

## 9. Reliability: after commit does not mean successfully sent

Suppose the transaction saving an order commits successfully, but the process crashes **before the callback sending a message to the broker completes**. The database still has the order, whereas the message may not exist. `@TransactionalEventListener(AFTER_COMMIT)` has no built-in durable replay mechanism.

For integrations that must retry across crashes, consider the **transactional outbox**:

1. Within the **same transaction**, save the business data and an outbox record representing the event to be sent.
2. After commit, a worker/relay reads the outbox and sends it to the broker or external system.
3. If sending fails, the worker retries; once sent successfully, it marks the record processed according to idempotency rules.
4. Consumers also need idempotency/deduplication, because retries can cause a message to be processed multiple times.

The outbox does not automatically guarantee end-to-end exactly-once delivery; it improves durability and recoverability with proper retry, locking, and idempotency design.

## 10. Exceptions, ordering, and testing

- If `BEFORE_COMMIT` throws an exception, the transaction may roll back; do not perform unrecoverable external side effects in this phase.
- If a post-commit/post-rollback callback fails, the transaction has already finished and cannot be "undone" due to the callback error. Exact error-throwing/logging behavior depends on the transaction manager and callback hook; separate logging, metrics, and retry paths are needed.
- `@Order` can prioritize transactional listeners, but does not establish completion order when the author explicitly uses `@Async` or multiple different transactions.
- Do not use post-commit listeners to persist data that **must be atomic** with the main transaction; write it inside the transaction or in an outbox.
- In testing, verify event publication before commit, successful commit, rollback, publication outside a transaction, `BEFORE_COMMIT` errors, `fallbackExecution`, `REQUIRES_NEW` propagation, and crashes/retries when there are out-of-process side effects.

### Common mistakes

| Mistake | Result | How to handle |
| --- | --- | --- |
| Treating regular `@EventListener` as after-commit | Side effects occur even if DB rolls back | Choose `@TransactionalEventListener(AFTER_COMMIT)` |
| Publishing outside a transaction without checking `fallbackExecution` | Event is not received by transactional listener | Check the boundary or enable fallback intentionally |
| Using `BEFORE_COMMIT` to confirm business persistence | Commit afterward can still fail | Distinguish "about to commit" from "committed" |
| Writing to DB in `AFTER_COMMIT` without a new transaction | Operation may not be committed | Use `REQUIRES_NEW` via proxy when appropriate |
| Using `@Async` and assuming the transaction follows the new thread | Context loss or wrong execution timing | Redesign thread and transaction boundaries |
| Treating after-commit callbacks as a reliable message queue | Events can be lost after a crash | Outbox, retry, idempotency |
| Expecting `@Order` to order async completion | Callbacks can run in parallel | Use a controlled workflow/queue |

## 11. Design selection checklist

1. Does the listener need to run **before commit**, **after commit**, **only on rollback**, or **on every outcome**?
2. Is the event published inside an **actual transaction**, and in the right thread/context?
3. Should events outside a transaction be ignored or handled via `fallbackExecution`?
4. Does the listener need to persist data after commit? If so, there must be a new transaction or a design change.
5. Must any side effects survive crashes/retries? In that case, consider a transactional outbox.
6. Are there `@Async`, reactive pipelines, `REQUIRES_NEW` propagation, or savepoints? These boundaries must be tested specifically.
7. Are callback errors logged/metered and paired with an appropriate recovery mechanism?

**Remember:** `@TransactionalEventListener` does not "bring the transaction into the listener"; it **registers an action to run at a specific phase of the current transaction**. The default `AFTER_COMMIT` helps process after a successful commit, but does not guarantee a new transaction for data writes inside the callback and does not automatically provide durability for external event delivery.

## Official references

- Spring Framework 6.2 — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework — `@TransactionalEventListener` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html
- Spring Framework — `TransactionPhase` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/event/TransactionPhase.html
- Spring Framework — `TransactionSynchronization` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html
- Spring Framework — `TransactionalEventPublisher` (reactive): https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html
