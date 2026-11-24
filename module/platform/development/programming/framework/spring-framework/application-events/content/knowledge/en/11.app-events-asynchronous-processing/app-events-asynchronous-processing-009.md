# Transaction Limitations of Async Listeners in Spring Application Events

## 1. Problem Statement and Mental Model

An order-creation use case typically saves an `orders` record inside a transaction and then publishes `OrderCreated`. To reduce HTTP response time, the team adds an `@Async` listener to send notifications, update a search index, or write a projection. The critical question is: **does the asynchronous listener belong to the transaction creating the order, can it see uncommitted data, and if the listener fails, does the use case's transaction roll back?**

For Spring Framework using imperative transactions via `PlatformTransactionManager`, the answers are:

- **It does not automatically join the same transaction.** Spring JDBC/JPA transactions typically bind resources to the current thread; work running on an executor thread does not automatically inherit those resources.
- **It is not guaranteed to run after commit.** The task can be scheduled while the publisher's transaction is still open and run before, during, or after commit/rollback.
- **It does not automatically propagate business errors back to the publisher.** An exception thrown in the listener body after the task has started does not alter a source transaction that has already finished or is running on another thread.

These three points are easy to confuse. `@Async` is about **executing on another thread**; `@Transactional` is about **transaction boundaries of a properly proxied call**; `@TransactionalEventListener` is about **the transaction phase at which a callback is triggered**. Each annotation solves a separate problem.

~~~text
Request thread (publisher)           Worker thread (listener)
--------------------------------     --------------------------------
BEGIN transaction T1
INSERT orders
publishEvent(OrderCreated)
  \-- schedule async task ---------> @Async listener runs on its own thread
continue processing                    does not automatically have transaction T1
COMMIT / ROLLBACK T1                   read DB / call API / update projection
return HTTP response                   completes or fails independently
~~~

With default synchronous listeners, `publishEvent` usually waits for the listener to complete. With an async listener, it only needs to schedule execution successfully before returning; listener completion is not guaranteed to coincide with the use case.

## 2. Why Doesn't Spring Carry Transactions Across to a New Thread?

By default, `SimpleApplicationEventMulticaster` invokes standard listeners on the same thread as `ApplicationEventPublisher.publishEvent(...)`. If the use case has an active transaction, a synchronous listener using the same transaction manager and `DataSource` can participate in that transaction. Unhandled runtime exceptions can propagate through `publishEvent(...)`.

Example of a synchronous listener, illustrated in a Spring bean with `OrderCreated` defined:

~~~java
@EventListener
public void reserveInventory(OrderCreated event) {
    inventoryRepository.reserve(event.orderId());
}
~~~

Whereas with async:

~~~java
@Async("eventExecutor")
@EventListener
public void buildSearchIndex(OrderCreated event) {
    projectionRepository.update(event.orderId());
}
~~~

The second method call is dispatched by Spring's async infrastructure to the executor when `@Async` is enabled and the proxy is working properly. In an imperative transaction system, `TransactionSynchronizationManager` holds thread-bound transaction/resource state. The executor thread does not automatically inherit that transaction. If the listener uses `JdbcTemplate`, it will typically open/acquire another connection when no matching transaction exists on the current thread.

This leads to the following scenarios:

| When the async listener reads data | What can happen |
| --- | --- |
| Before the source transaction commits | Uncommitted data may not be visible under isolation like `READ_COMMITTED`, or queries may block on locks |
| After commit | Can read committed data if queries, caches, and isolation align |
| After rollback | Rolled-back data does not exist in committed storage |
| While other requests are updating | May encounter newer data or concurrent state changes; requires proper versioning/isolation |

Do not use `Thread.sleep(...)` expecting the listener will reliably see the row. Scheduling timing varies with executor load, machine load, DB locks, and transaction configuration.

### Annotation-Driven Async vs. Multicaster-Driven Async

There are two common approaches:

1. Annotate a specific listener with `@Async` and enable `@EnableAsync`. A Spring proxy offloads the call to an executor.
2. Configure an `applicationEventMulticaster` bean with `SimpleApplicationEventMulticaster.setTaskExecutor(...)` to multicast via an executor for listeners that **support** async execution.

Both approaches can coexist, but they are not fully equivalent. Specifically in Spring 6.2, a transaction-phase-bound synchronous listener does not support having the multicaster move its synchronization-registration step to another thread; it needs to catch the event on the transaction thread. When the target method also carries `@Async`, **the post-processing work body** can still be scheduled on another thread after the transaction phase.

## 3. Do Async Failures Roll Back the Source Transaction?

Separate **task scheduling failures** from **task execution failures**.

- If the executor rejects the task due to overload or shutdown, scheduling can throw an exception directly inside the `publishEvent` call. Depending on configuration, the publisher may receive that error.
- Once the task has been scheduled successfully, an exception thrown **later** inside the async listener body does not automatically travel back up the publisher's call stack. With `@Async` on a `void` method, Spring provides `AsyncUncaughtExceptionHandler`; with async APIs returning a suitable future, the corresponding caller can observe results via the future, but an async `@EventListener` does not turn publishing into a listener-result-awaiting API.

Illustrative snippet (requires corresponding beans and imports):

~~~java
@Async("eventExecutor")
@EventListener
public void notifyCustomer(OrderCreated event) {
    throw new IllegalStateException("Mail server unavailable");
}
~~~

If the order-creation transaction commits successfully, an email-sending failure does not automatically roll back `orders`. If the transaction has not committed yet when the task runs and throws an error, the publisher also does not automatically receive that exception to abort the transaction.

Conversely, a **synchronous** listener throwing an unhandled `RuntimeException` can fail `publishEvent`; when wrapped by a source transaction and rollback rules apply, the use case can roll back. Therefore, do not convert a listener that **enforces mandatory invariants** (such as reserving inventory or computing totals determining order validity) to async without changing the business contract.

In Spring, an async `@EventListener` also **cannot publish a follow-up event by returning a method value** the way a synchronous listener can. If a follow-up event is needed, inject `ApplicationEventPublisher` and call `publishEvent(...)` explicitly.

## 4. Runnable Java 17+ Example: Comparing Events After Commit and Rollback

This example uses Spring Framework 6.2.8, Spring JDBC, and in-memory H2, **without Spring Boot**. The use case inserts into `orders` and publishes a regular event. The first run commits; the second intentionally rolls back. The async listener still receives its scheduled notification in both cases.

To make `stdout` ordering predictable, the example passes two `CountDownLatch` instances to the listener: it waits until the source transaction finishes before reading the DB, and signals main when done. This is a demonstration/testing technique, **not a production event payload design**.

### 4.1. Structure

~~~text
async-event-transaction/
├── pom.xml
└── src/main/java/AsyncTransactionDemo.java
~~~

Create `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>async-event-transaction</artifactId>
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
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>AsyncTransactionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 4.2. Source Code `src/main/java/AsyncTransactionDemo.java`

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

public final class AsyncTransactionDemo {

    // Two latches solely to demonstrate deterministic ordering in this example.
    public record OrderSubmitted(
            long id,
            CountDownLatch releaseListener,
            CountDownLatch listenerDone
    ) { }

    private static void await(CountDownLatch latch) {
        try {
            if (!latch.await(15, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timeout waiting for listener");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", ex);
        }
    }

    public static final class OrderUseCase {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate transactions;
        private final ApplicationEventPublisher events;

        public OrderUseCase(
                JdbcTemplate jdbc,
                TransactionTemplate transactions,
                ApplicationEventPublisher events
        ) {
            this.jdbc = jdbc;
            this.transactions = transactions;
            this.events = events;
        }

        public void execute(long id, boolean rollback) {
            CountDownLatch release = new CountDownLatch(1);
            CountDownLatch done = new CountDownLatch(1);
            try {
                try {
                    transactions.executeWithoutResult(status -> {
                        jdbc.update(
                            "INSERT INTO orders (id) VALUES (?)", id
                        );
                        events.publishEvent(
                            new OrderSubmitted(id, release, done)
                        );
                        if (rollback) {
                            throw new IllegalStateException("force rollback");
                        }
                    });
                    System.out.println("USE_CASE id=" + id + " COMMIT");
                } catch (IllegalStateException ex) {
                    if (!"force rollback".equals(ex.getMessage())) {
                        throw ex;
                    }
                    System.out.println("USE_CASE id=" + id + " ROLLBACK");
                }
            } finally {
                // TransactionTemplate has already committed/rolled back before reaching here.
                release.countDown();
                await(done);
            }
        }
    }

    // DO NOT mark final: Spring needs to create a proxy for @Async.
    public static class AsyncOrderObserver {
        private final JdbcTemplate jdbc;

        public AsyncOrderObserver(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Async("eventExecutor")
        @EventListener
        public void onOrderSubmitted(OrderSubmitted event) {
            try {
                await(event.releaseListener());
                boolean active =
                    TransactionSynchronizationManager
                        .isActualTransactionActive();
                int rows = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM orders WHERE id = ?",
                    Integer.class, event.id()
                );
                System.out.println(
                    "ASYNC id=" + event.id()
                    + " tx=" + active
                    + " rows=" + rows
                );
            } finally {
                event.listenerDone().countDown();
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config {
        @Bean("eventExecutor")
        ThreadPoolTaskExecutor eventExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("event-");
            executor.initialize();
            return executor;
        }

        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:async_tx_demo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        JdbcTemplate jdbc(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        TransactionTemplate transactions(PlatformTransactionManager manager) {
            return new TransactionTemplate(manager);
        }

        @Bean
        OrderUseCase orderUseCase(
                JdbcTemplate jdbc,
                TransactionTemplate transactions,
                ApplicationEventPublisher events
        ) {
            return new OrderUseCase(jdbc, transactions, events);
        }

        @Bean
        AsyncOrderObserver asyncOrderObserver(JdbcTemplate jdbc) {
            return new AsyncOrderObserver(jdbc);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute("CREATE TABLE orders (id BIGINT PRIMARY KEY)");

            OrderUseCase useCase = context.getBean(OrderUseCase.class);
            useCase.execute(1L, false);
            useCase.execute(2L, true);

            System.out.println(
                "FINAL rows=" + jdbc.queryForObject(
                    "SELECT COUNT(*) FROM orders", Integer.class
                )
            );
        }
    }
}
~~~

Run with JDK 17+ and Maven from the project directory:

~~~bash
mvn -q compile exec:java
~~~

Lines printed to `stdout`, excluding Maven auxiliary logs:

~~~text
USE_CASE id=1 COMMIT
ASYNC id=1 tx=false rows=1
USE_CASE id=2 ROLLBACK
ASYNC id=2 tx=false rows=0
FINAL rows=1
~~~

### 4.3. Result Explanation

- **Order 1:** `TransactionTemplate` inserts `orders(id=1)`, schedules the event, and commits. The use case prints `COMMIT` and releases the latch; only then does the listener query the DB and see one record. `tx=false` shows the listener thread has no active transaction at the check point.
- **Order 2:** `TransactionTemplate` inserts `orders(id=2)` and schedules the event, then throws `IllegalStateException("force rollback")`. The transaction rolls back. The use case prints `ROLLBACK` and releases the latch. The already-scheduled listener still executes, but its query does not see the rolled-back order `2`.
- **Conclusion from the experiment:** `@Async @EventListener` has no built-in mechanism to revoke a task when the publisher rolls back; the listener being invoked is not proof that the source data committed. `FINAL rows=1` confirms the final outcome of the two transactions.

Latches are used here to produce **deterministic observation order**. Without latches, the listener could query before commit; whether rows are visible depends on isolation/database and execution timing. This is not an event design for production: payloads should carry only necessary business data and identifiers, without embedding thread-synchronization primitives into domain contracts.

Note that the Maven/Java example needs to download dependencies if they are not cached locally. This demo uses an executor with one worker and waits for each event to finish before continuing; it does not depict guaranteed completion order across applications using multi-threaded pools.

## 5. What Transaction Does `@Transactional` on an Async Listener Create?

A common fix attempt is adding `@Transactional` to the async listener:

~~~java
@Async("eventExecutor")
@Transactional
@EventListener
public void updateProjection(OrderCreated event) {
    // If the transaction proxy is applied, a transaction runs on the executor thread.
}
~~~

This is an illustrative snippet inside a Spring bean with an existing event type. The transaction annotation can open a **new transaction for work on the worker thread** if the proxy operates and beans are properly configured. It **does not reuse the publisher use case's transaction T1**. If T1 rolls back, T2 does not automatically roll back; if T2 fails, T1 is not automatically reverted.

Keep these distinctions in mind:

- `Propagation.REQUIRED` means joining a transaction **already present on the invoked thread**, or starting a new one if none exists. The worker thread does not automatically have transaction T1.
- `Propagation.REQUIRES_NEW` explicitly starts an independent transaction; on an async worker already on a separate thread, it still does not attach T2 to T1.
- `@Transactional` and `@Async` normally rely on proxies; self-invocation or `final` classes/methods prevent class-based proxies from working as expected. With Spring AOP class-based proxies, do not place `final` on a class without interfaces that needs `@Async`.
- The worker's transaction manager only manages resources within the worker's transaction scope. Sending emails, HTTP calls, or message broker operations do not automatically become rollbackable by a JDBC transaction.

For a **mandatory step** that must fail the use case if unsuccessful (e.g., checking inventory to decide whether to create an order), calling a synchronous service inside the use case's transaction gives a clearer contract. Async listeners fit post-processing that can be retried, run slowly, or accept eventual consistency.

## 6. Running Only After Commit: `@TransactionalEventListener`

When a listener may only process **committed orders**, the straightforward solution is listening by transaction phase:

~~~java
@Component
public class ProjectionListener {
    @Async("eventExecutor")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCommitted(OrderCreated event) {
        // Access committed data and update a separate projection.
    }
}
~~~

This is an **illustrative snippet** (requiring `OrderCreated`, an executor, and imports for `Component`, `Async`, `TransactionalEventListener`, `TransactionPhase`). When the use case publishes an event **inside an active transaction**, Spring registers a callback. With `AFTER_COMMIT`, the callback is only triggered when the transaction commits successfully. If the transaction rolls back, the `AFTER_COMMIT` listener is not triggered for that event.

Phase table:

| Phase | When it runs | Suited for |
| --- | --- | --- |
| `BEFORE_COMMIT` | Before commit | Checks/work that must happen right before commit, with clear awareness of boundaries |
| `AFTER_COMMIT` (default) | After successful commit | Notifications, projections, post-processing relying solely on committed data |
| `AFTER_ROLLBACK` | After rollback | Failure tracking or scheduling compensation |
| `AFTER_COMPLETION` | After the transaction finishes, commit or rollback | Tracking final completion outcome |

**Key points:**

1. If an event is published **outside a transaction**, `@TransactionalEventListener` does not invoke the handler by default; `fallbackExecution=true` can be used when running without a transaction is genuinely acceptable.
2. `@TransactionalEventListener` selects **when to trigger**, while `@Async` selects **how to execute the method body**. A callback bound to a transaction phase can dispatch the async task to an executor after commit.
3. In Spring Framework 6.2, transaction-synchronized listeners need the multicaster to invoke them on the transaction thread to register synchronization. Therefore, do not infer that configuring an async executor at the multicaster level pushes every transactional listener onto another thread.
4. `AFTER_COMMIT` does not move transaction T1 onto the worker thread. If the listener needs DB writes, intentionally open a new transaction for those updates.
5. Once a transaction has committed, exceptions thrown in a post-commit listener **do not roll back committed data**.
6. After commit, some transactional resources may temporarily remain bound to the callback thread even though the transaction has completed; do not mistake DB operations at that moment as having another commit coming. Explicitly establish a new transaction for post-processing DB writes.

For **reactive transactions**, Spring 6.1+ also supports Reactor transaction-bound listeners, though Reactor context differs from imperative JDBC/JPA `ThreadLocal`; events must carry transaction info via supported mechanisms such as `TransactionalEventPublisher`. Do not copy thread-bound examples verbatim into reactive flows.

## 7. Remaining Challenges: Durability and Retries

`@TransactionalEventListener(AFTER_COMMIT)` avoids processing events from rolled-back transactions, yet **it is not a durable queue**. Event loss can still occur:

~~~text
Order COMMIT succeeds
    |
    +-- application crashes before the callback is scheduled
    |
    +-- executor rejects the task due to overload
    |
    +-- task is accepted but fails with no durable retry
~~~

If search indexing can be rebuilt or auxiliary emails may fail occasionally, post-commit processing with monitoring may be sufficient. However, if integration messages **must never be lost** after commit, you need durable intent recording, such as a **transactional outbox**.

Outbox flow:

1. In the same transaction creating the order, write `orders` and an `outbox` record describing the event, including an event ID.
2. If the transaction rolls back, both the order and the outbox record roll back; on commit, both exist.
3. A separate dispatcher reads committed outbox entries, publishes messages, and tracks processing/retry state.
4. Consumers handle messages idempotently by event ID because messages may be delivered repeatedly during retries.

An outbox typically targets **at-least-once delivery**, not automatic system-wide "exactly once." Monitor retry counts, dead letters, latency, idempotency, record cleanup, and concurrent dispatchers competing for the same record.

## 8. Payloads and Context Across Thread Boundaries

For async listeners, prefer passing **identifiers or immutable DTOs**:

~~~java
public record OrderCreated(long orderId, String customerId) { }
~~~

Avoid passing managed JPA entities assuming the worker shares the same persistence context. Entities with lazy associations can trigger `LazyInitializationException` once the original transaction/session closes, or data state may change between publication and execution. After `AFTER_COMMIT`, the worker can open a new transaction to re-query data by ID. If a **publish-time snapshot** is needed, include the required fields in the event or outbox record.

Beyond transactions, other contexts such as logging MDC, security context, request scope, tracing, and custom `ThreadLocal` values do not automatically follow every executor. A `TaskDecorator` or context propagation library can carry **safe context data** to the worker; that is **not** a way to pass JDBC connections, `EntityManager` instances, or the source transaction across threads. Manually copying `TransactionSynchronizationManager` across threads can violate connection/session lifecycles and thread safety.

**Ordering:** when an executor has multiple workers, event completion order does not match publish order. If a projection requires ordering, use sequences/versions, partition by business key, or use a processor with an explicit ordering contract; add idempotency to guard against stale overwrites.

## 9. Choosing the Right Mechanism for Requirements

| Business Requirement | Mechanism to Consider |
| --- | --- |
| Order must not be created unless inventory is reserved | Call synchronous service inside the same transaction |
| Send notification only when order commits; losing task on process crash is acceptable | `@TransactionalEventListener(AFTER_COMMIT)`, optionally combined with `@Async` |
| Update an independent projection, retriable | After commit, dedicated transaction on worker, monitoring, and idempotency |
| Send messages to external systems with zero loss allowed | Transactional outbox + dispatcher + retries + idempotent consumer |
| Observe rollback reasons | `@TransactionalEventListener(AFTER_ROLLBACK)` or observability at transaction boundary |
| Perform a mandatory calculation affecting transaction outcome | Synchronous processing; do not rely on async listeners to roll back publisher |

When combining multiple listeners, do not assume `@Order` across listeners turns an async pipeline into an all-or-nothing rollback chain. `@Order` only partially controls listener invocation order in supported setups; it does not create cross-thread transactions, undo side effects already performed, or guarantee delivery.

## 10. Testing and Troubleshooting

A test suite should cover **commit, rollback, task failures, and process restarts**. Observe state after the transaction finishes, rather than only counting listener invocations.

| Case | What to Verify |
| --- | --- |
| Publish in committed transaction, regular async listener | Task does not inherit T1; data is only reliably readable after commit |
| Publish then roll back, `@Async @EventListener` | Task may still run even though data rolled back |
| Publish then roll back, `@TransactionalEventListener(AFTER_COMMIT)` | Listener is not invoked after commit for rolled-back transactions |
| Async listener throws `RuntimeException` | Publisher does not automatically roll back from task body exceptions |
| Executor rejects task | Separate scheduling failure from execution failure; verify backpressure policy |
| `@Transactional` listener on worker | Worker transaction is independent of publisher transaction |
| System crashes after commit before sending notification | Verify replay/outbox if delivery is mandatory |
| Multiple events update the same entity | Check ordering, sequence/version, and idempotency |
| Listener reads lazy JPA entity after request | Does not depend on publisher's session |

To inspect whether an imperative transaction is active on a thread, you can log `TransactionSynchronizationManager.isActualTransactionActive()` at the publish site and inside the listener. However, `true` does not prove every resource belongs to the same physical transaction: check the transaction manager, `DataSource`, propagation, and actual commit/rollback outcomes.

In integration tests, avoid wrapping the entire test in an uncommitted transaction and expecting an async worker to see that data; that differs from production behavior and masks bugs. Use latches/futures or timed waiting utilities to synchronize checkpoints instead of fixed sleeps. Post-processing tests should verify failed tasks, retries, and executor shutdown.

## 11. Common Mistakes

1. **Assuming `@Async` inherits the source transaction:** imperative transactions do not follow `ThreadLocal` across to workers.
2. **Assuming publishing inside `@Transactional` means the event runs after commit:** async listeners can often be scheduled before commit.
3. **Using async to enforce mandatory invariants:** worker exceptions are not a rollback contract for the use case.
4. **Adding `@Transactional` to the worker thinking it is T1:** the worker starts an independent T2.
5. **Using `sleep` to guess commit timing:** causes flakiness; use transaction phases or proper synchronization.
6. **Forgetting `@EnableAsync`/proxy config or using unproxiable `final` beans:** `@Async` may silently not take effect.
7. **Passing mutable entities/persistence contexts:** data and session lifecycles may differ when the worker runs.
8. **Ignoring task failures:** proper handlers, metrics, retries, and alerting are required.
9. **Confusing after-commit with zero event loss:** crashes between commit and scheduling can still lose work.
10. **Arbitrarily propagating transaction context:** connections/`EntityManager` are not designed as cross-thread shared objects.
11. **Ignoring event ordering and idempotency:** worker pools can reorder execution, and retries can cause duplicate effects.

## 12. Self-Check Exercises

1. `@Transactional` creates an order, publishes an event, and then explicitly rolls back. Is `@Async @EventListener` automatically canceled? Why or why not?
2. In the demo, if both latches were removed, why might the async listener's `SELECT` miss the row even for an order that eventually commits?
3. Does placing `@Transactional` on an async listener make the listener's transaction the publisher's transaction?
4. When should you use `@TransactionalEventListener(AFTER_COMMIT)`, and why is an outbox still needed for critical messages?
5. Why can't `@TransactionalEventListener(BEFORE_COMMIT)` combined with `@Async` be treated as "wait for the async task to finish before committing"?
6. If an async listener throws an exception, what mechanisms are needed so work is not silently lost?
7. Why should you pass `orderId` or an immutable DTO instead of a managed entity, and what should the worker do if it needs to re-read data?
8. If two events update the same order projection, how do you prevent stale state overwrites?

**Guidance:** (1) No; the task may already have been scheduled before rollback; (2) the worker thread is not in the same transaction, so uncommitted data may not be visible; (3) no, it normally starts a new transaction on the worker; (4) only after commit, yet not durable across crashes, so outbox/retries are needed; (5) callback registration phase and async task body execution are two separate steps; (6) monitoring, retries, idempotency/dead-letter handling; (7) open a new transaction on the worker and query by ID or carry a snapshot; (8) sequence/version checks, per-key ordering, and idempotency.

## References

- Spring Framework Reference, *Application Events / Asynchronous Listeners*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework Reference, *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework Reference, *Using @Transactional*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework 6.2.8 Javadoc, *SimpleApplicationEventMulticaster*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework 6.2.8 Javadoc, *TransactionalEventListener*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html