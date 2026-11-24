# Publishing Events After Commit in Spring Framework Application Events

## 1. The Problem: Why Wait for Transaction Commit?

In a Spring application, a service may update the database and then emit an event to send an email, update a search index, refresh a cache, enqueue a job, or call an external system. If that activity executes too early, **the database transaction may roll back while the external side effect has already happened**.

~~~java
@Transactional
public void placeOrder(long id) {
    orderRepository.insert(id);
    publisher.publishEvent(new OrderPlaced(id));
    // An exception here can roll back the INSERT.
}
~~~

This is integration code, requiring definitions for `orderRepository`, `publisher`, the `OrderPlaced` event, and a Spring transaction manager. Under the default multicaster configuration, an `@EventListener` method is normally called **synchronously right at `publishEvent`**, meaning when the transaction may not have committed yet.

~~~text
BEGIN T1
  INSERT orders(id=328)
  publishEvent(OrderPlaced)
      |
      +-- @EventListener -> email sent successfully
  throw RuntimeException
ROLLBACK T1

Email was sent, yet order 328 is no longer in the database.
~~~

A **post-commit event publishing pattern** ensures downstream work is triggered only after the data-creating transaction has committed successfully. However, this phrase often refers to **two different mechanisms** in Spring:

- **Pattern A — publish inside the transaction, listener handles after commit.** The service calls `ApplicationEventPublisher.publishEvent(event)` while T1 is still open, and the consumer uses `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`. The **publication happens before commit**; only the transaction-bound listener is deferred.
- **Pattern B — publish the event only after actual commit.** The service registers `TransactionSynchronization.afterCommit()` inside T1, then calls `publisher.publishEvent(event)` inside the callback. Here **publication itself happens after commit**, so even a plain `@EventListener` sees that event only after the transaction succeeds.

Both approaches achieve the same business goal in many cases, but they differ in semantics, when other listeners observe the event, exception handling, and code structure.

**Important:** both are **in-process** mechanisms and do not automatically become a durable event queue. If the JVM crashes after commit before post-processing finishes, the event/task can still be lost. To avoid losing events in that scenario, use a transactional outbox or an equivalent durable solution.

## 2. Spring Application Events and Transaction Phases

Spring Framework supports:

~~~java
ApplicationEventPublisher publisher;
publisher.publishEvent(new OrderPlaced(328L));
~~~

This is illustrative code; the `OrderPlaced` record is application-defined. Events can be `ApplicationEvent` subclasses or POJO/record payloads. With `@EventListener`, Spring selects methods by event type and dispatches via `ApplicationEventMulticaster`.

### Plain @EventListener

~~~java
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    notificationGateway.send(event.orderId());
}
~~~

This method normally runs as soon as the event is published if the default synchronous multicaster is active. If the listener has `@Async` or the multicaster uses another executor, it may run on a different thread; however, that **does not** make it wait for commit automatically.

### @TransactionalEventListener

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderPlaced event) {
    notificationGateway.send(event.orderId());
}
~~~

When an event is published inside an eligible transaction, Spring **registers a transaction synchronization** to invoke the listener at the corresponding phase. `AFTER_COMMIT` is the default phase:

~~~java
@TransactionalEventListener
public void on(OrderPlaced event) {
    // Defaults to AFTER_COMMIT.
}
~~~

Phases:

| Phase | When It Runs | Suitable When |
|---|---|---|
| `BEFORE_COMMIT` | Right before commit | Validating constraints before the transaction commits |
| `AFTER_COMMIT` | After successful commit | Sending notifications or triggering post-commit work |
| `AFTER_ROLLBACK` | After rollback | Recording failures or explicitly designed compensation |
| `AFTER_COMPLETION` | After commit or rollback | Outcome-independent cleanup/metrics |

When there is **no active transaction** at publication time, `@TransactionalEventListener` by default **ignores the event**. You can enable `fallbackExecution = true` to run immediately on non-transactional paths, though **there is no commit to wait for**.

## 3. Pattern A: Publish Inside Transaction and Handle with @TransactionalEventListener

This is usually the simplest declarative approach when an application has subscribers that should run after commit.

~~~java
public record OrderPlaced(long orderId) {}

@Service
public class OrderService {
    private final OrderRepository repository;
    private final ApplicationEventPublisher events;

    public OrderService(OrderRepository repository,
                        ApplicationEventPublisher events) {
        this.repository = repository;
        this.events = events;
    }

    @Transactional
    public void create(long id) {
        repository.insert(id);
        events.publishEvent(new OrderPlaced(id));
    }
}

@Component
public class ReceiptListener {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void sendReceipt(OrderPlaced event) {
        emailService.send(event.orderId());
    }
}
~~~

This is **integration code**, requiring `OrderRepository`, `emailService` beans, and imports. Spring processes it as:

~~~text
HTTP / command
   |
   v
OrderService.create()
   |
   +-- BEGIN T1
   +-- INSERT orders
   +-- publishEvent(OrderPlaced)
   |      |
   |      +-- plain @EventListener may run immediately
   |      +-- @TransactionalEventListener AFTER_COMMIT registers callback
   |
   +-- RETURN from service body
   +-- COMMIT T1
          |
          +-- success -> sendReceipt()
          |
          +-- rollback -> DO NOT call sendReceipt()
~~~

**Do not say `OrderPlaced` is "only published after commit" in this pattern.** The event was published inside T1; only `sendReceipt` runs after commit. If there is another listener:

~~~java
@EventListener
public void auditImmediately(OrderPlaced event) {
    // Can still run BEFORE commit.
}
~~~

it can observe the event before commit. If all listeners must observe the event only after commit, use **Pattern B**, a distinct post-commit event, or a durable solution.

### Publication Must Occur Inside T1

Mistake:

~~~java
public void checkout(long id) {
    orderService.saveWithinTransaction(id); // T1 commits before returning.
    publisher.publishEvent(new OrderPlaced(id)); // May be outside T1.
}
~~~

If the publisher is called after the transactional service has exited, the transactional listener by default ignores the event because no active transaction remains to register the callback. **Place the publish call inside a method truly running inside T1**, not in a controller calling a transactional service beforehand.

## 4. Pattern B: Register TransactionSynchronization.afterCommit to Publish Later

If an event name explicitly means "the change has been committed," the publisher can defer the entire publication.

~~~java
@Transactional
public void create(long id) {
    orderRepository.insert(id);

    if (!TransactionSynchronizationManager.isActualTransactionActive()
            || !TransactionSynchronizationManager.isSynchronizationActive()) {
        throw new IllegalStateException("Expected an active transaction");
    }

    TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                publisher.publishEvent(new OrderCommitted(id));
            }
        }
    );
}
~~~

This is **integration code**, requiring imports:

~~~java
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
~~~

as well as `OrderCommitted` and a Spring-managed service/repository. `afterCommit()` is a callback triggered **only when commit actually succeeds**.

A plain listener consumes the new event:

~~~java
@EventListener
public void onCommitted(OrderCommitted event) {
    notificationGateway.send(event.id());
}
~~~

In Pattern B, the `publishEvent(new OrderCommitted(id))` call itself has not happened prior to commit, so any listener receiving **this event** can only be triggered after the post-commit callback executes.

### Direct Comparison

| Feature | Pattern A: `@TransactionalEventListener` | Pattern B: `afterCommit()` Publish |
|---|---|---|
| Event publication | Before commit, inside T1 | After commit, inside callback |
| Who chooses the phase? | Each listener | Publisher |
| Plain `@EventListener` for same event | May run before commit | Runs only when event is published post-commit |
| T1 rolls back | `AFTER_COMMIT` listener does not run | Callback does not publish |
| No T1 | Transactional listener skips by default | Cannot register a valid callback |
| Coupling | Publisher is independent of transaction phase | Publisher is aware of transaction synchronization |
| Durability across JVM crash | Not guaranteed | Not guaranteed |

If an application needs both an internal in-T1 "OrderPlaced" fact and a post-T1 "OrderCommitted" notification, use **two distinct event types** with clear meanings rather than overloading one event class.

### Do Not Treat afterCommit() as a New Transaction

When `TransactionSynchronization.afterCommit()` runs, T1 has already committed. This callback **does not open T2**. A new repository write requires an explicit transaction if you want to ensure it commits; see Section 7.

## 5. Runnable Java 17 Example: Both Patterns, Commit, Rollback, and No Transaction

The following example uses **Spring Framework 6.2.8**, Java 17+, Maven, `spring-jdbc`, and in-memory H2. Its goal is to prove:

1. On commit, `OrderCreated` is handled immediately by a plain listener and later by `@TransactionalEventListener(AFTER_COMMIT)`; meanwhile, `afterCommit()` emits `OrderCommittedSignal` to another plain listener.
2. On rollback, the plain listener for `OrderCreated` has already run, but **neither** post-commit path executes.
3. When published outside a transaction, the plain listener still receives `OrderCreated`, while the transactional listener skips by default.

### 5.1. Structure

~~~text
after-commit-demo/
├── pom.xml
└── src/main/java/demo/AfterCommitDemo.java
~~~

### 5.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>after-commit-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.8</version>
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
                <version>3.13.0</version>
                <artifactId>maven-compiler-plugin</artifactId>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.3. src/main/java/demo/AfterCommitDemo.java

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public final class AfterCommitDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            OrderService service = context.getBean(OrderService.class);
            Counters counters = context.getBean(Counters.class);

            jdbc.execute(
                "CREATE TABLE orders(" +
                "id BIGINT PRIMARY KEY, state VARCHAR(20) NOT NULL)"
            );

            // Success: commit triggers both post-commit mechanisms.
            service.create(1L, false);
            counters.print("commit", jdbc);

            // Failure: rollback, no post-commit execution.
            try {
                service.create(2L, true);
            } catch (IllegalStateException expected) {
                System.out.println("caught=" + expected.getMessage());
            }
            counters.print("rollback", jdbc);

            // Outside transaction: only plain listener receives the event.
            context.publishEvent(new OrderCreated(3L));
            counters.print("no transaction", jdbc);
        }
    }

    public record OrderCreated(long id) {}
    public record OrderCommittedSignal(long id) {}

    // Non-final so Spring can create a class-based proxy.
    public static class OrderService {
        private final JdbcTemplate jdbc;
        private final ApplicationEventPublisher publisher;

        public OrderService(JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.publisher = publisher;
        }

        @Transactional
        public void create(long id, boolean fail) {
            if (!TransactionSynchronizationManager
                    .isActualTransactionActive()
                    || !TransactionSynchronizationManager
                    .isSynchronizationActive()) {
                throw new IllegalStateException("no active transaction");
            }

            jdbc.update(
                "INSERT INTO orders(id, state) VALUES (?, ?)",
                id, "CREATED"
            );

            // Pattern A: event is published INSIDE the transaction.
            publisher.publishEvent(new OrderCreated(id));

            // Pattern B: another event is published ONLY AFTER commit.
            TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void afterCommit() {
                        publisher.publishEvent(
                            new OrderCommittedSignal(id));
                    }
                }
            );

            if (fail) {
                throw new IllegalStateException("force rollback");
            }
        }
    }

    public static class Counters {
        private final AtomicInteger immediate = new AtomicInteger();
        private final AtomicInteger transactionalCommitted =
            new AtomicInteger();
        private final AtomicInteger transactionalRollback =
            new AtomicInteger();
        private final AtomicInteger explicitPublication =
            new AtomicInteger();

        @EventListener
        public void immediate(OrderCreated event) {
            immediate.incrementAndGet();
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void afterCommit(OrderCreated event) {
            transactionalCommitted.incrementAndGet();
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
        public void afterRollback(OrderCreated event) {
            transactionalRollback.incrementAndGet();
        }

        @EventListener
        public void onCommittedSignal(OrderCommittedSignal event) {
            explicitPublication.incrementAndGet();
        }

        public void print(String label, JdbcTemplate jdbc) {
            Integer rows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM orders", Integer.class);

            System.out.println(label +
                ": rows=" + rows +
                " immediate=" + immediate.get() +
                " afterCommit=" + transactionalCommitted.get() +
                " afterRollback=" + transactionalRollback.get() +
                " publishedAfterCommit=" + explicitPublication.get());
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {

        @Bean
        public DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:after_commit328;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        public OrderService orderService(
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            return new OrderService(jdbc, publisher);
        }

        @Bean
        public Counters counters() {
            return new Counters();
        }
    }
}
~~~

### 5.4. Running

Inside `after-commit-demo`, using JDK 17+:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.AfterCommitDemo
~~~

Lines **printed by the program**, with the default synchronous multicaster (auxiliary Maven logs may vary):

~~~text
commit: rows=1 immediate=1 afterCommit=1 afterRollback=0 publishedAfterCommit=1
caught=force rollback
rollback: rows=1 immediate=2 afterCommit=1 afterRollback=1 publishedAfterCommit=1
no transaction: rows=1 immediate=3 afterCommit=1 afterRollback=1 publishedAfterCommit=1
~~~

### 5.5. Detailed Walkthrough of Each Branch

**Commit branch (ID 1):**

- `context.getBean(OrderService.class)` retrieves the **Spring-managed bean proxy**.
- `@Transactional` starts T1; `INSERT orders(id=1)` runs inside T1.
- `publisher.publishEvent(new OrderCreated(1))` is called before commit. The plain listener increments `immediate` to 1 right away.
- The `AFTER_COMMIT` and `AFTER_ROLLBACK` transactional listeners register callbacks for T1.
- The service registers a `TransactionSynchronization.afterCommit` callback to emit `OrderCommittedSignal` after commit.
- T1 commits successfully: the `afterCommit` callback publishes the signal and the signal's plain listener increments `publishedAfterCommit`; the `AFTER_COMMIT` transactional listener increments its counter. `AFTER_ROLLBACK` does not run.
- `main` calls `counters.print(...)` after `service.create` returns; `rows = 1`.

**Rollback branch (ID 2):**

- T2 inserts ID 2 and publishes `OrderCreated(2)`. The plain listener already received the event; `immediate=2`.
- The service method registers the post-commit callback and then throws `IllegalStateException("force rollback")`.
- The Spring transaction interceptor rolls back T2. `AFTER_COMMIT` does not run; `afterCommit()` is never invoked either.
- `AFTER_ROLLBACK` increments to 1, and the DB still contains only ID 1. `publishedAfterCommit` remains 1.

**No-transaction branch (ID 3):**

- `main` calls `context.publishEvent(new OrderCreated(3))` outside the transactional service.
- The plain listener increments `immediate=3`.
- Because `@TransactionalEventListener` defaults to `fallbackExecution=false`, the transaction-bound listener does not run.
- `main` did not register `afterCommit()` for this event; there is no post-commit signal and no new DB row.

The example intentionally avoids printing inside each `AFTER_COMMIT` and `afterCommit()` callback so that workflows do not rely on implementation ordering between those two callback types.

## 6. Where Does @Transactional Actually Take Effect?

A common bug is seeing `@Transactional` on a method while events are still processed outside a transaction.

~~~java
@Service
class CheckoutService {
    public void checkout(long id) {
        this.createInTransaction(id);
    }

    @Transactional
    public void createInTransaction(long id) {
        repository.insert(id);
        publisher.publishEvent(new OrderCreated(id));
    }
}
~~~

This is a **counter-example** demonstrating *self-invocation*. In Spring AOP's default proxy mode, `this.createInTransaction(id)` does not go through the transactional proxy, so it may **not start T1**. In that case, `@TransactionalEventListener` skips the event by default, even though the code looks fine.

How to fix:

- Place the transactional method on another Spring-managed bean and invoke it **through the proxy**.
- Or structure the external entry point so callers invoke the `public` transactional method directly on the Spring bean.
- Or use `TransactionTemplate` for an explicit programmatic transaction boundary.

Other pitfalls: object created via `new`; non-interceptable method; `final` class/method incompatible with class-based proxies; wrong transaction manager; config missing `@EnableTransactionManagement` in plain Spring; `SUPPORTS` propagation when the caller has no T1.

### Debugging at the Exact Event Publication Point

~~~java
boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();
boolean sync =
    TransactionSynchronizationManager.isSynchronizationActive();

log.debug("before publish: txActive={}, txSync={}", active, sync);
publisher.publishEvent(new OrderCreated(id));
~~~

This is integration code using your application's logger. With an imperative `PlatformTransactionManager`, checking at the **exact publish point** is usually more informative than checking in the controller. Do not infer from `sync=true` alone that a real business transaction is active; inspect both `active` and the transaction manager.

## 7. A New Transaction Is Required When a Post-Commit Listener Writes to the DB

An important technical nuance: after commit, **transaction resources may remain bound to the thread while the callback runs**, even though the database has already committed and **no subsequent commit will happen** for T1.

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderCreated event) {
    auditRepository.insertAudit(event.id());
}
~~~

This illustrative snippet **does not qualify as proof that the audit data will be committed**. Per the Spring Javadoc, data access operations in post-completion callbacks may join the old transaction's resources without another commit.

Extract to a bean with an independent transaction:

~~~java
@Component
public class AuditObserver {
    private final AuditWriter auditWriter;

    public AuditObserver(AuditWriter auditWriter) {
        this.auditWriter = auditWriter;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderCreated event) {
        auditWriter.write(event.id());
    }
}

@Service
public class AuditWriter {
    private final AuditRepository repository;

    public AuditWriter(AuditRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void write(long id) {
        repository.insertAudit(id);
    }
}
~~~

This is **integration code**, requiring `AuditRepository` and imports, and the call to `AuditWriter` must go through a Spring proxy. `REQUIRES_NEW` opens a separate transaction T2. T2 can commit or roll back independently, though it is no longer atomic with the already-committed T1.

If the audit and the order **must always commit or roll back together**, write both inside T1; do not defer the audit write to `AFTER_COMMIT`.

## 8. Post-Commit Exceptions Do Not Roll Back T1

Consider a manual callback:

~~~java
TransactionSynchronizationManager.registerSynchronization(
    new TransactionSynchronization() {
        @Override
        public void afterCommit() {
            remoteService.notifyOrder(id);
            // An exception here occurs after T1 has already COMMITTED.
        }
    }
);
~~~

Per the `TransactionSynchronization.afterCommit()` contract, runtime exceptions from the callback **can propagate back to the caller** of the transactional operation. Even so, the database **has already committed**, so the caller must not conclude that the order was not created.

Meanwhile, `@TransactionalEventListener(AFTER_COMMIT)` is processed via transaction completion synchronization; Spring distinguishes `afterCompletion` callbacks from direct `afterCommit` methods. Exceptions in `afterCompletion` are typically **logged rather than propagated**. Do not apply a blanket rule like "all post-commit exceptions propagate to the HTTP request" or "all post-commit exceptions are swallowed."

| Where Did It Fail? | Can It Roll Back T1? | Notes |
|---|---|---|
| Plain sync listener throws inside T1 | Possibly, per rollback rules | Exception must exit the transaction boundary properly |
| `BEFORE_COMMIT` listener throws unchecked exception | Yes | T1 has not committed yet |
| `TransactionSynchronization.afterCommit()` throws | **No** | Caller may receive exception even though DB committed |
| `@TransactionalEventListener(AFTER_COMMIT)` fails | **No** | Completion callback; separate logging/error policy |
| `@Async` worker fails after commit | **No** | Observe failures via executor/future/retries |

Therefore, order-creation commands need an idempotency key if clients may retry after timeouts/exceptions. Post-processing needs its own status and metrics to surface failures rather than inferring everything from HTTP status codes.

## 9. Publishing After Commit Does Not Guarantee Durability

Crash-gap diagram:

~~~text
T1 COMMITs order successfully
     |
     +-- JVM crashes before AFTER_COMMIT listener finishes
     |
     +-- Email/API/broker not called or no ACK received
     |
     +-- No durable record for automatic replay
~~~

With both Pattern A and Pattern B, the callback lives in-process. If a business task must complete even across restarts, a **transactional outbox** is more appropriate:

~~~text
BEGIN T1
  INSERT orders(id=328)
  INSERT outbox_events(event_id=E328, type='OrderCreated', status='PENDING')
COMMIT T1
      |
      +-- Outbox relay reads committed rows
      +-- Dispatches to broker / API
      +-- Retries on failure
      +-- Idempotent consumer keyed by eventId
~~~

If T1 rolls back, both business data and outbox roll back together. If it commits and the JVM crashes, the outbox remains available to send. However, if the relay sends successfully and crashes before marking `SENT`, the message may be redelivered. **At-least-once delivery requires consumer idempotency**; an outbox does not automatically create end-to-end exactly-once semantics.

A design mistake:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void saveOutbox(OrderCreated event) {
    outboxRepository.insert(event);
}
~~~

If the goal is an **atomic outbox**, this is the wrong place: T1 already committed before the outbox insert, so the outbox is not in the same business transaction. Opening T2 with `REQUIRES_NEW` persists the outbox after commit, yet a crash gap still exists between T1 and T2. Write the initial outbox record **inside T1**.

If you only need reliable publication **across modules within the same application**, look at the Spring Modulith Event Publication Registry and incomplete-publication resubmission, matching your exact version. Do not assume it automatically acts as a Kafka outbox or broker delivery mechanism.

## 10. Async Listeners: They Wait for Commit, But Do Not Inherit T1

A common pattern:

~~~java
@Async("eventExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCreated(OrderCreated event) {
    emailGateway.send(event.id());
}
~~~

This is integration code requiring `@EnableAsync`, an `eventExecutor` bean, and a Spring-managed listener. Spring registers the transactional synchronization at publication time; once T1 commits, the listener work can be dispatched to the executor via `@Async`.

Key things to understand:

- JDBC transaction T1 is managed on the publisher thread and **is not automatically copied to the worker thread**.
- `@Async` does not make events durable; a process crash can still lose tasks.
- Exceptions in the worker cannot roll back the already-committed T1.
- Tracing/MDC context propagation is not equivalent to transaction propagation.
- If the worker needs DB writes, open an appropriate separate transaction T2.
- Task submission can be rejected by the executor; monitor rejections and queue saturation.
- Tests for async listeners must **await completion with a timeout**, never asserting immediately after `publishEvent`.

### Publishing from an Async Worker Is a Different Story

If a service holds T1 on thread A but calls an `@Async` publisher on thread B, the `publishEvent` call itself may run **without transaction T1**. `@TransactionalEventListener` will then skip the event by default. Design **publication inside T1** or open an appropriate transaction on the worker rather than relying on `ThreadLocal` propagation.

## 11. Reactive Transactions and Post-Commit Events

The examples above use imperative JDBC (`PlatformTransactionManager`), where transactions are thread-bound. Spring Framework 6.1+ also supports `@TransactionalEventListener` with `ReactiveTransactionManager`, where reactive transactions live in the **Reactor Context**.

For transaction-bound listeners to recognize a reactive transaction, Spring requires `TransactionContext` as the **event source**. `TransactionalEventPublisher` provides a helper API:

~~~java
return databaseClient.sql("INSERT INTO orders(id) VALUES (:id)")
    .bind("id", id)
    .fetch()
    .rowsUpdated()
    .then(transactionalEventPublisher.publishEvent(context ->
        new PayloadApplicationEvent<>(
            context,
            new OrderCreated(id)
        )))
    .as(transactionalOperator::transactional);
~~~

This is **reactive integration code**, requiring `DatabaseClient`, `TransactionalEventPublisher`, `TransactionalOperator`, and the event type. It demonstrates publishing inside a reactive transaction so `@TransactionalEventListener(AFTER_COMMIT)` binds to the commit phase. It is **not** an example of publishing genuinely after commit.

In reactive pipelines:

- Creating a `Mono` does not execute the SQL/event by itself; a subscription is required.
- Use `StepVerifier` or subscriber-aware integration tests.
- Do not rely on imperative `TransactionSynchronizationManager.isActualTransactionActive()` as the sole proof of a reactive transaction.
- Avoid calling `subscribe()` detached from the transaction pipeline.
- To publish events strictly after a reactive commit, use an appropriate transaction-completion boundary/callback; writing an outbox inside the same reactive DB transaction remains preferable if durability is the goal.

## 12. Avoid Publish Loops and Too-Late Callbacks

A counter-example:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public OrderCreated afterCommit(OrderCreated event) {
    return event; // May cause an event chain/loop or hard-to-control registration.
}
~~~

This is a **counter-example**; do not use it in production. `@EventListener` can publish a returned object as a new event; however, during completion phases, emitting further events can hit transaction lifecycle issues or infinite loops. Define a **distinct event type** with clear meaning, and if post-commit publication is needed, call `publisher.publishEvent(new EventType(...))` at the right boundary.

Specifically, when calling `publishEvent(...)` **directly inside `TransactionSynchronization.afterCommit()`**, do not assume another `@TransactionalEventListener(AFTER_COMMIT)` will have a fresh transaction to register a callback. T1 is already completing; registering a new synchronization that late can behave unexpectedly. For events published after commit, use a plain `@EventListener` or start a real T2 when a new transaction is needed.

**Do not use `@Order` as a workflow engine.** Listener invocation order is not the same as side-effect completion order in async/broker systems. When B depends on A completing, use an orchestrator, a state machine, or an `"ACompleted"` event with an explicit contract.

## 13. Testing Commit, Rollback, Callbacks, and Side Effects Properly

A solid test suite verifies at least:

| Case | Setup | Expectation |
|---|---|---|
| Commit | `@Transactional` service INSERT + publish | DB commits and `AFTER_COMMIT` callback runs |
| Rollback | INSERT + publish then throw `RuntimeException` | DB rolls back; `AFTER_COMMIT` callback does not run |
| Publish outside transaction | Context publishes directly | Plain `@EventListener` receives; transactional listener skips by default |
| Publish from `afterCommit()` | Service commits | New event is published only when commit succeeds |
| `fallbackExecution=true` | Publish outside T1 | Fallback listener runs immediately; no commit involved |
| Post-commit failure | Callback throws exception | DB remains committed; error is observed separately |
| Async | `@Async` listener | Assert after awaiting completion signal |
| Outbox | Write business/outbox inside T1 | Both rows commit or roll back together |

### The @Transactional Test Trap

In Spring TestContext, a `@Transactional` test method normally **rolls back at the end of the test**. Calling the service and immediately asserting that `AFTER_COMMIT` ran is wrong if the transaction never committed:

~~~java
@Test
@Transactional
void shouldInvokeAfterCommit() {
    service.create(328L);

    TestTransaction.flagForCommit();
    TestTransaction.end();

    // Only now assert the synchronous AFTER_COMMIT callback.
}
~~~

This is **illustrative test code**, requiring `spring-test`, JUnit Jupiter, a test transaction manager, imports, and a Spring-managed service. An easier alternative: leave `@Transactional` off the test method itself so the transactional service commits before assertions run.

### Event Recorders Only Verify Publication

`@RecordApplicationEvents`/`ApplicationEvents.stream(EventType.class)` is useful for checking which events were **published** in a test. With **Pattern A**, the recorder sees `OrderCreated` before commit; that does not prove the `AFTER_COMMIT` listener ran. Verify callbacks through a fake collaborator/counter or DB side effects after a real commit.

In **Pattern B**, tests can assert that the post-commit event appears after the service returns and commits, and does not appear after rollback. If the callback is async, await completion.

### Do Not Rely on Exact Timing

Execution timings, thread scheduling, and database connections vary on CI; never assert "after exactly 10ms." Use latches or await conditions with bounded timeouts and assert counts, payloads, commit outcomes, and idempotency keys.

## 14. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Treating every `@EventListener` as post-commit | Side effects execute before rollback | Use `@TransactionalEventListener(AFTER_COMMIT)` |
| Thinking `@TransactionalEventListener` defers `publishEvent` until after commit | Other listeners still see the event pre-commit | Distinguish delayed handling from delayed publication |
| Calling publish after the transactional service returns | No T1 left to register callback | Publish inside T1 or register `afterCommit` |
| Enabling `fallbackExecution=true` casually | Listener runs immediately outside T1 | Use only if business rules accept fallback |
| Proxy/self-invocation oversight | `@Transactional` never activates | Invoke through a Spring bean proxy |
| `@Async` publisher before commit | T1 does not propagate to worker | Publish inside T1 or open an explicit transaction |
| `REQUIRED` DB write post-commit | May join stale resource without committing | `REQUIRES_NEW` via separate bean proxy |
| Treating post-commit exception as rollback | Command retry creates duplicate records | Distinguish transaction outcome from post-commit work |
| Expecting `@Async` to be a durable queue | JVM crash loses tasks | Transactional outbox/queue |
| Writing initial outbox inside `AFTER_COMMIT` | Not atomic with business row | Write outbox inside T1 |
| Asserting only the event recorder | Does not prove side effects completed | Assert DB/adapter state after real commit |
| Using `@Order` as orchestration | Async/broker tasks finish out of order | Workflow/state machine |
| Publishing new event during completion and binding to T1 phase | Synchronization registered too late | Plain listener or real T2 |
| Not controlling duplicates | Retries duplicate side effects | `eventId` and idempotent consumer |
| Not monitoring callback errors | DB committed while post-processing silently fails | Metrics, logs, retries, and alerts |

## 15. Implementation Checklist

1. **What is the event's meaning?** "Changing now" or "committed successfully"?
2. Should the event become visible after commit to **all listeners** or only specific listeners?
3. Is there an active transaction at the callback registration point?
4. Does the call to `@Transactional` pass through a proxy?
5. If the transaction rolls back, can any callback still cause a side effect?
6. When no transaction is active, is the policy to skip, reject, or fallback?
7. If a post-commit callback fails, will the HTTP/service layer return an error that triggers command retries?
8. If the listener performs extra DB writes, does the new transaction genuinely use `REQUIRES_NEW`?
9. If using async, do you await/observe the worker without confusing `ThreadLocal` transactions?
10. If using reactive pipelines, does the event source carry the proper `TransactionContext`?
11. If work must survive crashes, do you have an outbox/queue and idempotency?
12. Do tests cover commit, rollback, publishing outside T1, exceptions, and async?
13. Are there dedicated metrics for callback completion, errors, retries, and backlog?
14. Does the event carry IDs, version, and minimal data without leaking unnecessary PII/secrets?

## 16. Summary

**Post-commit event publishing** in Spring has two main patterns. **Pattern A** emits the event while T1 is open, using `@TransactionalEventListener(AFTER_COMMIT)` to process it **after the transaction commits**. **Pattern B** registers `TransactionSynchronization.afterCommit()` and **only then calls `publishEvent`**, ensuring a post-commit semantic event is never seen earlier by any plain `@EventListener`.

Both patterns avoid side effects on transaction rollback along proper boundaries, yet **neither solves crash durability or retry duplicates by itself**. If the task must reliably execute, use a transactional outbox with a relay and idempotency. If a post-commit callback writes to the DB, remember that old resources may remain thread-bound without further commits: create a proper new transaction such as `REQUIRES_NEW` through a proxy.

### Official References

- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html): `@TransactionalEventListener`, phases, fallback, and reactive support.
- [Spring Framework 6.2.8 Javadoc — TransactionalEventListener](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html): contract and warnings on post-completion DB resources.
- [Spring Framework 6.2.8 Javadoc — TransactionSynchronization](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html): `afterCommit()`, `afterCompletion()`, and exceptions.
- [Spring Framework 6.2.8 Javadoc — TransactionSynchronizationManager](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html): registering synchronizations in imperative transactions.
- [Spring Framework 6.2 — Declarative Transactions](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html): proxies, `@Transactional`, and self-invocation.
- [Spring Framework 6.2 — Transaction Propagation](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-propagation.html): `REQUIRED`, `REQUIRES_NEW`.
- [Spring Framework 6.2.8 — TransactionalEventPublisher](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html): reactive `TransactionContext` event source.
