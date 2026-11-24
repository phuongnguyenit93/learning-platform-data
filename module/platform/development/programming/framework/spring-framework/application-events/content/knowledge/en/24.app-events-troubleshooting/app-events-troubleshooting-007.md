# No Transaction for Transactional Listener in Spring Framework

## 1. Symptoms and Root Nature of the Error

A service calls `ApplicationEventPublisher.publishEvent(...)` successfully, yet the `@TransactionalEventListener` method does not execute; switching the annotation to `@EventListener` makes it receive the event. This is a very common symptom of **no compatible transaction existing at the exact moment the event is published**.

~~~java
@Component
class PaymentObserver {
    @TransactionalEventListener
    public void onPaymentCompleted(PaymentCompleted event) {
        System.out.println("Payment committed: " + event.paymentId());
    }
}
~~~

This is an integration snippet requiring `PaymentCompleted`, imports, and corresponding bean registration. The default `@TransactionalEventListener` annotation is equivalent to:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT,
    fallbackExecution = false
)
~~~

Spring requires an active transaction to bind phase callbacks. **If an event is published outside a transaction, the transactional listener is skipped** (under default settings), because there is no commit or rollback to track. Spring is not required to throw an exception just for skipping this callback.

This lesson focuses on diagnosing six causes:

1. Calling `publishEvent` outside a transaction or after the transactional service has already returned.
2. `@Transactional` is present in code yet ineffective due to self-invocation, proxying, bean setup, or manager configuration.
3. Transaction propagation does not create a transaction, e.g. `SUPPORTS` or `NOT_SUPPORTED`.
4. The event is published on another thread or inside a scheduler/`@Async`.
5. A reactive transaction exists in Reactor Context yet was not attached to the event source.
6. A transaction exists yet rolled back, or the listener specifies the wrong phase, producing a symptom identical to "no transaction".

Do not fix this by immediately enabling fallback. First determine whether **the business contract** genuinely requires the event to be processed only upon successful commit.

## 2. Why Does @EventListener Still Run?

The two annotations serve different roles.

| Property | Standard `@EventListener` | `@TransactionalEventListener` |
|---|---|---|
| Without a transaction | Usually called when event is published | By default **not** called |
| Inside a transaction | Usually runs immediately at publish time | Registers callback for a `TransactionPhase` |
| Default phase | No transaction phase | `AFTER_COMMIT` |
| Additional requirements | Matching bean/type/condition | Compatible transaction or fallback |
| Creates a transaction itself? | No | No |
| Provides durable delivery? | No | No |
| Suitable for post-commit-only processing? | Requires external coordination | Yes, when the event is registered inside a transaction |

Diagram:

~~~text
publisher.publishEvent(OrderPlaced)
    |
    v
ApplicationContext / EventMulticaster
    |
    +-- @EventListener
    |      +-- runs immediately per dispatch policy (synchronous by default)
    |
    +-- @TransactionalEventListener
           |
           +-- Compatible transaction present?
                  |
                  +-- Yes: register synchronization by phase
                  |        +-- BEFORE_COMMIT
                  |        +-- AFTER_COMMIT
                  |        +-- AFTER_ROLLBACK
                  |        +-- AFTER_COMPLETION
                  |
                  +-- No: fallbackExecution?
                            +-- false: drop event
                            +-- true: invoke listener via fallback path
~~~

`publishEvent(...)` returning **does not prove all listeners ran**, nor does it prove the transaction committed, an email was sent, or a message was accepted by a broker.

### Three Distinct Timestamps

- **Publication:** `publishEvent` is called in code.
- **Transaction completion:** the transaction commits or rolls back.
- **Listener execution:** the callback actually runs at its phase, or via fallback when no transaction exists.

Therefore, when an event is published inside a transaction and an `AFTER_COMMIT` listener has not run yet, the transaction may simply still be open. Conversely, when published outside a transaction with `fallbackExecution=false`, waiting longer **will not** cause the dropped event to be invoked later.

## 3. What Does fallbackExecution=true Change?

Spring allows:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT,
    fallbackExecution = true
)
public void onOrderPlaced(OrderPlaced event) {
    notification.send(event.orderId());
}
~~~

This illustrative snippet requires the application's beans, events, and notification service.

- **With a transaction:** the listener honors the phase; for `AFTER_COMMIT`, it runs after successful commit.
- **Without a transaction:** the listener is allowed to run via the fallback path **immediately when the event is published**; there is no commit to wait for.
- **Does not start a transaction:** fallback does not replace `@Transactional` or a transaction manager.
- **Does not guarantee exactly-once:** no durable store, retry, or idempotency is added automatically.

| Phase | With transaction | Without transaction, fallback=false | Without transaction, fallback=true |
|---|---|---|---|
| `BEFORE_COMMIT` | Before commit | Skipped | Runs fallback immediately |
| `AFTER_COMMIT` | After successful commit | Skipped | Runs fallback immediately |
| `AFTER_ROLLBACK` | After rollback | Skipped | Runs fallback immediately, **even without rollback** |
| `AFTER_COMPLETION` | After commit or rollback | Skipped | Runs fallback immediately |

The `AFTER_ROLLBACK` case is especially important: enabling fallback can trigger a listener named `onRollback` **without any transaction having rolled back**. If the listener performs compensation or records business failures, that can violate business logic.

### When Should Fallback Be Enabled?

Better suited for logging, metrics, or events whose meaning is independent of a transaction. Explicitly document the contract: "after commit when a transaction exists, immediately when none exists".

Do not enable fallback merely to make payment emails, order notifications, or external updates fire when the true requirement is "run only after DB changes commit". In that case, **fix the publication boundary**.

## 4. Runnable Java 17 Demo: Outside Transaction, Commit, and Rollback

This example uses Spring Framework **6.2.8**, Java 17+, Maven, `spring-context`, `spring-jdbc`, and an in-memory H2 database. It distinguishes all three cases in **the same program** and reads back actual database row counts instead of mocking transactions with booleans.

Project structure:

~~~text
no-transaction-event-demo/
├── pom.xml
└── src/main/java/demo/NoTransactionEventDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>no-transaction-event-demo</artifactId>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### src/main/java/demo/NoTransactionEventDemo.java

~~~java
package demo;

import javax.sql.DataSource;
import java.util.concurrent.atomic.AtomicInteger;

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
import org.springframework.transaction.support.TransactionSynchronizationManager;

public final class NoTransactionEventDemo {

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = ctx.getBean(JdbcTemplate.class);
            OrderService service = ctx.getBean(OrderService.class);
            Counters counts = ctx.getBean(Counters.class);

            jdbc.execute(
                "CREATE TABLE demo_orders (" +
                "id BIGINT PRIMARY KEY, status VARCHAR(30) NOT NULL)"
            );

            // 1. Publication outside a Spring transaction.
            if (TransactionSynchronizationManager.isActualTransactionActive()) {
                throw new AssertionError("main should have no transaction");
            }
            ctx.publishEvent(new OrderCreated(100L));
            counts.print("outside", jdbc);

            // 2. Transaction commits when the service proxy returns.
            service.createAndCommit(200L);
            counts.print("commit", jdbc);

            // 3. RuntimeException forces transaction rollback.
            try {
                service.createAndRollback(300L);
            } catch (IllegalStateException ex) {
                System.out.println("rollback cause=" + ex.getMessage());
            }
            counts.print("rollback", jdbc);
        }
    }

    public record OrderCreated(long orderId) {}

    // Non-final class so Spring can create a class-based transaction proxy.
    public static class OrderService {
        private final JdbcTemplate jdbc;
        private final ApplicationEventPublisher events;

        public OrderService(JdbcTemplate jdbc,
                ApplicationEventPublisher events) {
            this.jdbc = jdbc;
            this.events = events;
        }

        @Transactional
        public void createAndCommit(long id) {
            assertTransaction();
            jdbc.update(
                "INSERT INTO demo_orders (id, status) VALUES (?, ?)",
                id, "CREATED"
            );
            events.publishEvent(new OrderCreated(id));
        }

        @Transactional
        public void createAndRollback(long id) {
            assertTransaction();
            jdbc.update(
                "INSERT INTO demo_orders (id, status) VALUES (?, ?)",
                id, "CREATED"
            );
            events.publishEvent(new OrderCreated(id));
            throw new IllegalStateException("force rollback");
        }

        private void assertTransaction() {
            if (!TransactionSynchronizationManager
                    .isActualTransactionActive()) {
                throw new AssertionError("transaction proxy not active");
            }
        }
    }

    public static final class Counters {
        private final AtomicInteger ordinary = new AtomicInteger();
        private final AtomicInteger afterCommit = new AtomicInteger();
        private final AtomicInteger fallback = new AtomicInteger();
        private final AtomicInteger afterRollback = new AtomicInteger();

        @EventListener
        public void regular(OrderCreated event) {
            ordinary.incrementAndGet();
        }

        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT
        )
        public void committed(OrderCreated event) {
            afterCommit.incrementAndGet();
        }

        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT,
            fallbackExecution = true
        )
        public void committedOrFallback(OrderCreated event) {
            fallback.incrementAndGet();
        }

        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_ROLLBACK
        )
        public void rolledBack(OrderCreated event) {
            afterRollback.incrementAndGet();
        }

        public void print(String label, JdbcTemplate jdbc) {
            Long rows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM demo_orders", Long.class
            );
            System.out.println(
                label +
                ": ordinary=" + ordinary.get() +
                " afterCommit=" + afterCommit.get() +
                " fallback=" + fallback.get() +
                " afterRollback=" + afterRollback.get() +
                " rows=" + rows
            );
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {
        @Bean
        public DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:event273;DB_CLOSE_DELAY=-1");
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
                JdbcTemplate jdbc, ApplicationEventPublisher events) {
            return new OrderService(jdbc, events);
        }

        @Bean
        public Counters counters() {
            return new Counters();
        }
    }
}
~~~

### How to Run

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.NoTransactionEventDemo
~~~

Lines printed by the program in order, under default synchronous configuration:

~~~text
outside: ordinary=1 afterCommit=0 fallback=1 afterRollback=0 rows=0
commit: ordinary=2 afterCommit=1 fallback=2 afterRollback=0 rows=1
rollback cause=force rollback
rollback: ordinary=3 afterCommit=1 fallback=2 afterRollback=1 rows=1
~~~

Maven and Spring may print other technical logs. The four lines above are the output intentionally printed by application code.

### Explaining Each Branch

**Outside branch:** `ctx.publishEvent(new OrderCreated(100L))` is in `main`, not going through the transactional service. The standard listener is called and the fallback listener is called, yet default `AFTER_COMMIT` and `AFTER_ROLLBACK` are not called. The DB still has no rows.

**Commit branch:** `service.createAndCommit(200L)` is invoked via the **Spring bean proxy**. A JDBC transaction starts, inserts ID 200, and publishes the event inside the transaction; the standard listener increments immediately. Both `AFTER_COMMIT` listeners register callbacks; after commit, both increment. In this branch, the fallback-enabled listener still uses the **transactional path**, not fallback, because a transaction exists.

**Rollback branch:** `service.createAndRollback(300L)` inserts ID 300, publishes the event, and throws an unchecked exception. The standard listener has already been called; `AFTER_COMMIT` does not run due to rollback; `AFTER_ROLLBACK` runs. Row 300 is rolled back, so after all three branches only one committed row remains.

The example creates real transactions via `DataSourceTransactionManager`; when the demo completes successfully, the implicit assertions about commit/rollback timing are proven by the DB row count. The example does **not** verify durable delivery across process crashes, message brokers, or reactive transactions.

## 5. Diagnose at the Publish Site, Not Only by Reading Annotations

More reliable than asking "Does the method have `@Transactional`?" is checking **the transaction state right before `publishEvent`**.

~~~java
boolean actual =
    TransactionSynchronizationManager.isActualTransactionActive();
boolean sync =
    TransactionSynchronizationManager.isSynchronizationActive();

log.info("Publishing OrderPlaced: txActive={}, sync={}",
    actual, sync);

publisher.publishEvent(new OrderPlaced(orderId));
~~~

This is illustrative imperative code with the application's logger, `OrderPlaced`, and publisher. Results distinguish:

- `actual=true` and `sync=true`: a transaction and synchronization suitable for callback registration usually exist, though **successful commit is not yet guaranteed**.
- `actual=false`: no real transaction may exist; inspect call graph/propagation.
- `sync=true`, `actual=false`: synchronization scope alone does not prove a real transaction that the listener needs exists.
- `actual=true`, `sync=false`: special configuration; inspect transaction manager/synchronization activation.

**Warning:** `TransactionSynchronizationManager` in this snippet is an imperative ThreadLocal-based API. In reactive transactions, `ReactiveTransactionManager` stores state in **Reactor Context**; an imperative ThreadLocal check returning false is **not sufficient proof that a reactive transaction is absent**.

## 6. Common Cause: Self-Invocation Causes @Transactional to Be Bypassed

~~~java
@Service
public class CheckoutService {

    public void checkout(long id) {
        this.saveAndPublish(id);
    }

    @Transactional
    public void saveAndPublish(long id) {
        repository.insert(id);
        publisher.publishEvent(new OrderCreated(id));
    }
}
~~~

This is illustrative code (requiring repository, publisher, imports, and bean). Under default **Spring AOP proxy mode**, calling `this.saveAndPublish(id)` does not go through the Spring transactional proxy. The method bears the annotation, yet **the intended transaction may never start**. When the event is published, default transactional listeners are skipped.

The clearest fix is usually separating the boundary into another bean:

~~~java
@Service
public class CheckoutWorkflow {
    private final TransactionalOrderService orders;

    public CheckoutWorkflow(TransactionalOrderService orders) {
        this.orders = orders;
    }

    public void checkout(long id) {
        orders.saveAndPublish(id); // Goes through the other bean's proxy.
    }
}

@Service
public class TransactionalOrderService {
    @Transactional
    public void saveAndPublish(long id) {
        repository.insert(id);
        publisher.publishEvent(new OrderCreated(id));
    }
}
~~~

These are integration classes requiring matching collaborators. Do not do `new TransactionalOrderService()` and call it directly: manually instantiated objects do not get a Spring transaction proxy. When using AspectJ weaving or programmatic transactions, interception differs from default proxying; this article focuses on typical Spring AOP behavior.

Other signs that `@Transactional` is not being applied:

- Calls to `private`/uninterceptable methods via proxy, or `final` classes/methods incompatible with class-based proxies.
- Object is not a Spring-managed bean.
- `@EnableTransactionManagement` not enabled in plain Spring Framework, or misconfigured transaction infrastructure.
- Multiple transaction managers exist and the method picks the wrong manager or resource.
- An init/lifecycle method is invoked before the proxy is ready.
- The transactional method already returned before `publishEvent` actually occurred.

Do not use `fallbackExecution=true` to "fix" self-invocation; it may make the event run yet **does not ensure DB writes occur inside a transaction**.

## 7. Propagation: @Transactional Does Not Always Open a Transaction

Propagation modes directly affect whether an active transaction exists at publish time.

| Propagation | When caller has no transaction | Impact on listener |
|---|---|---|
| `REQUIRED` (default) | Starts a new transaction | Can register callback |
| `REQUIRES_NEW` | Starts an independent transaction | Callback binds to the new transaction |
| `SUPPORTS` | Continues without a transaction | Default listener may be skipped |
| `NOT_SUPPORTED` | Runs without a transaction, suspending outer tx if any | Default listener may be skipped |
| `MANDATORY` | Throws exception if no transaction exists | Does not publish event on success path |
| `NEVER` | Runs without a transaction, throws if one exists | Default listener may be skipped |

Example:

~~~java
@Transactional(propagation = Propagation.SUPPORTS)
public void emit(String orderId) {
    publisher.publishEvent(new OrderCreated(orderId));
}
~~~

This is an illustrative pattern with an event type carrying a `String` `orderId`. `SUPPORTS` does not start a new physical transaction when the caller has no T1. Therefore, **having the annotation is still not enough** to guarantee `@TransactionalEventListener` is called.

`@Transactional(readOnly=true)` with `REQUIRED` can still create a transaction; `readOnly` is an attribute/hint and **does not mean absence of a transaction**. Choose propagation based on real business needs, not merely to "make callbacks run".

## 8. Publication Placed After the Transaction Boundary

Another trap:

~~~java
public void checkout(String id) {
    OrderSaved saved = orderService.save(id);
    publisher.publishEvent(new OrderCreated(saved.id()));
}

@Service
class OrderService {
    @Transactional
    public OrderSaved save(String id) {
        // Saves data; transaction commits when the proxied call returns.
    }
}
~~~

This is illustrative architecture code requiring `OrderSaved`, `OrderCreated`, beans, and persistence components. The publish statement occurs **after `orderService.save(id)` returns**, typically after the service's transaction has already committed. Thus inside `checkout`, **no transaction may remain**.

If the contract requires binding the event to that exact DB commit, move publication inside the transactional method:

~~~java
@Transactional
public void saveAndPublish(String id) {
    repository.save(...);
    publisher.publishEvent(new OrderCreated(id));
}
~~~

This is an integration snippet. If the transaction commits successfully, `AFTER_COMMIT` listeners run at the proper phase. If the transaction rolls back, `AFTER_COMMIT` listeners do not run.

**Do not open an empty transaction after the DB has already committed just to fabricate an "AFTER_COMMIT phase".** That new transaction is not the original transaction of the change. When reliable post-commit event emission is required, consider a transactional outbox.

## 9. Async, Schedulers, and ThreadLocal Transactions

In imperative Spring transactions (JDBC/JPA), transaction state is bound to the thread. An `@Async` worker does not automatically inherit transaction T1 from the calling thread:

~~~java
@Service
public class AsyncPublisher {
    private final ApplicationEventPublisher events;

    public AsyncPublisher(ApplicationEventPublisher events) {
        this.events = events;
    }

    @Async("taskExecutor")
    public void publishLater(OrderCreated event) {
        events.publishEvent(event);
    }
}
~~~

This is integration code: requires `@EnableAsync`, executor bean, proxy, and imports. If an HTTP request holds transaction T1 on thread A and dispatches `publishLater` to worker B, worker B **does not share the same ThreadLocal transaction** merely because it was spawned during that call. Events published on B may be skipped by transactional listeners.

Distinguish:

1. **Publisher runs async:** the event is emitted from a thread lacking the caller's transaction, so registration can fail.
2. **Listener is marked `@Async`:** `@TransactionalEventListener` registration binds to publication inside the transaction; at phase time, the body can execute on an executor, yet the worker does not inherit the original JDBC transaction.

Spring Framework 6.1+ enables transactional listeners to require synchronization registration on the original thread rather than arbitrary executor handoff. Still, that **does not** make a transaction context freely shareable across threads.

If work in the worker needs DB reads/writes, open a **separate transaction inside the worker** (via proxy or `TransactionTemplate`) with clear boundaries; avoid manually copying ThreadLocal transactions. Propagating tracing context/MDC is also not equivalent to propagating a transaction.

## 10. Reactive Transactions Live in Reactor Context, Not ThreadLocal

Since Spring Framework **6.1**, `@TransactionalEventListener` supports both imperative transactions (via `PlatformTransactionManager`) and reactive transactions (via `ReactiveTransactionManager`), but reactive binding works differently.

| Imperative | Reactive |
|---|---|
| Thread-bound transaction | Transaction in Reactor subscriber Context |
| Inspectable via imperative `TransactionSynchronizationManager` | Do not use imperative ThreadLocal as sole proof |
| Publisher typically runs synchronously on same thread | Publisher runs inside pipeline/subscription |
| Listener can see thread-bound transaction | Event needs `TransactionContext` as its **source** |

If publishing with standard `ApplicationEventPublisher` inside a reactive flow:

~~~java
publisher.publishEvent(new OrderCreated(orderId));
~~~

this **does not automatically place `TransactionContext` into the event source**, so transactional listeners may fail to bind to the reactive transaction.

Spring provides `TransactionalEventPublisher`:

~~~java
// Integration pattern: runs inside a reactive transaction pipeline.
return transactionalEventPublisher.publishEvent(context ->
    new PayloadApplicationEvent<>(
        context,
        new OrderCreated(orderId)
    )
);
~~~

This snippet requires `TransactionalEventPublisher`, `PayloadApplicationEvent`, event payload, and `TransactionalOperator` or an appropriate reactive transaction boundary. The `publishEvent(Function<TransactionContext, ApplicationEvent>)` API lets you **set `TransactionContext` as the source**. This is not a standalone program; do not expect a reactive transaction to appear automatically if the pipeline is never subscribed or has no transaction.

Avoid:

~~~java
// Anti-pattern: detached subscription outside the managed flow.
someReactivePublisher.subscribe();
~~~

Manual `subscribe()` calls can create a separate subscription chain without retaining the expected transaction context. Prefer composing with `flatMap` and `then` within the same pipeline and testing with `StepVerifier`. `fallbackExecution=true` **does not replace** attaching the reactive transaction context to the event source.

## 11. No Transaction vs. Transaction Rollback Are Two Different Causes

The same silent `AFTER_COMMIT` listener can result from two distinct scenarios:

~~~text
A. Publish outside a transaction
   -> Cannot register callback
   -> fallback=false: event is skipped for this listener

B. Publish inside T1
   -> AFTER_COMMIT callback is registered
   -> T1 rolls back
   -> AFTER_COMMIT does not run because there was no successful commit
~~~

To detect path B, use another phase:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
public void onRollback(OrderCreated event) {
    metrics.recordRollback(event.orderId());
}
~~~

This runs only when the transaction rolls back and the callback was successfully registered. If a regular listener throws an exception before the transactional adapter registers synchronization, behavior can differ; during investigation check `@Order`/`ErrorHandler` and dispatch ordering.

**Missing AFTER_COMMIT logs do not always indicate a transaction manager bug**. It may be a valid rollback, an event type mismatch, a non-matching `condition` filter, or a callback failing during execution.

## 12. Check Spring Beans and ApplicationContext Before Concluding

Several non-transactional issues produce identical symptoms:

- Listener is not scanned/registered by Spring as a bean.
- Publisher and listener reside in different `ApplicationContext` instances without the expected propagation link.
- Listener method parameter does not match the event type.
- A SpEL `condition` causes the listener to be skipped.
- Spring Test slice does not load the observer bean.
- Custom multicaster or proxy alters dispatch policy.
- Event fires before the listener is registered, e.g., during early bootstrap.

Isolation strategy:

~~~java
@EventListener
public void verifyDelivery(OrderCreated event) {
    log.debug("OrderCreated reached this context");
}
~~~

If the standard listener **also does not** receive the event, check wiring/context/type first. If the standard listener receives it while the transactional listener does not, move on to checking transaction state at the publish site.

Do not rewrite or edit the entire application configuration over one silent listener; start from a single reproducible publication.

## 13. Why Putting @Transactional on the Listener Is Not Enough

A fix that misses the root cause:

~~~java
@TransactionalEventListener
@Transactional
public void onOrderCreated(OrderCreated event) {
    repository.saveAudit(event.orderId());
}
~~~

Problem: if publication happens outside a transaction with `fallbackExecution=false`, Spring skips the event **before invoking the listener method**. The transaction interceptor on that method **never gets a chance to start a transaction** to rescue a dropped event.

When a listener genuinely runs post-commit and needs to write to the database, there is another caveat: Spring Javadoc warns that original transaction resources may still be bound to the thread during completion callbacks, causing DB operations to join old resources that **will not commit again**. Delegate DB writes to another bean:

~~~java
@Component
public class OrderObserver {
    private final AuditWriter writer;

    public OrderObserver(AuditWriter writer) {
        this.writer = writer;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderCreated event) {
        writer.persist(event.orderId());
    }
}

@Service
public class AuditWriter {
    private final AuditRepository repository;

    public AuditWriter(AuditRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void persist(long orderId) {
        repository.insertAudit(orderId);
    }
}
~~~

These are two illustrative classes integrating with the application's `AuditRepository` and matching imports. Calling `AuditWriter` goes through a Spring proxy, so `REQUIRES_NEW` opens an independent transaction for DB work. **It does not rescue dropped events**; it only solves the DB persistence boundary once the listener has actually been invoked.

## 14. Debug Logs for Transactions and Event Routing

In a Spring Boot application with a configured logging backend, you can temporarily raise log levels:

~~~properties
logging.level.org.springframework.transaction=DEBUG
logging.level.org.springframework.transaction.event=TRACE
logging.level.org.springframework.context.event=DEBUG
~~~

This is reference configuration, with no guarantee every version prints an identical log string. Checklist of things to inspect:

1. Did the service entry point go through a Spring proxy?
2. Which transaction manager started the transaction?
3. Which thread ran `publishEvent`?
4. Right before publish, what were `actualTx`/`sync`?
5. Did the right `ApplicationContext` dispatch the event?
6. Does the transactional listener have the right `phase`/`fallbackExecution`?
7. Did the transaction ultimately commit or roll back?
8. If the callback ran yet side effects are missing, did the DB write or external API call truly succeed?

Do not log credentials, tokens, emails, full sensitive event payloads, or financial info to debug logs. Lower log levels after identifying the root cause.

## 15. Testing Properly: Outside Transaction, Commit, Rollback

With `spring-test` and JUnit Jupiter, maintain at least three integration tests.

**Outside-transaction test:** a test method without `@Transactional` calls publish directly. Assert the regular listener receives it, default `AFTER_COMMIT` does not, and fallback receives it. If the test inherits a transaction from a base class or meta-annotation, results will differ.

~~~java
@Test
void outsideTransactionDropsDefaultListener() {
    publisher.publishEvent(new OrderCreated(273L));
    assertEquals(0, counters.afterCommit());
    assertEquals(1, counters.fallback());
}
~~~

**Commit test:** call a `@Transactional` Spring service bean that publishes inside the method and returns/commits; assert `AFTER_COMMIT` ran and the DB row exists.

~~~java
@Test
void commitRunsAfterCommitListener() {
    transactionalService.saveAndPublish(273L);
    assertEquals(1, counters.afterCommit());
    assertEquals(1, repository.countCommittedRows());
}
~~~

**Rollback test:** the service publishes and throws an unchecked exception causing rollback; assert `AFTER_COMMIT` did not run, `AFTER_ROLLBACK` ran, and the DB contains no new row.

~~~java
@Test
void rollbackSkipsAfterCommit() {
    assertThrows(IllegalStateException.class,
        () -> transactionalService.saveAndFail(273L));
    assertEquals(0, counters.afterCommit());
    assertEquals(1, counters.afterRollback());
}
~~~

The three snippets above are **illustrative test code**, requiring JUnit, fake counters or fresh contexts per test, and matching service/repository beans. Reset counters and data between tests; do not share mutable state that causes flakiness.

### Trap of @Transactional on Test Methods

Spring TestContext typically rolls back test-managed transactions at the end of a test:

~~~java
@Test
@Transactional
void thisTestUsuallyRollsBack() {
    transactionalService.saveAndPublish(273L);
    // AFTER_COMMIT has not run here; the test transaction is still open.
}
~~~

To test post-commit behavior, omit `@Transactional` from the test method, or use:

~~~java
TestTransaction.flagForCommit();
TestTransaction.end();
// Only after ending the test transaction, assert AFTER_COMMIT callbacks.
~~~

This is an integration test snippet requiring `org.springframework.test.context.transaction.TestTransaction` and an active test-managed transaction. Do not call `TestTransaction` when no TestContext transaction exists.

### Can @RecordApplicationEvents Be Used?

Yes, but distinguish **event was published** from **listener ran**. `ApplicationEvents.stream(OrderCreated.class).count()` can be > 0 even when the transaction rolled back or `AFTER_COMMIT` was never invoked. To prove the callback executed, assert a test collaborator, DB state, or a dedicated completion signal; to prove publication, inspect `ApplicationEvents`.

## 16. Fallback Does Not Replace Durability

Having a transaction and an `AFTER_COMMIT` listener running at the right phase still does not mean messages are durable. There is a failure window:

~~~text
T1: COMMIT Order
      |
      +-- JVM crash / service killed
      |
      +-- AFTER_COMMIT callback may not have executed yet
      |
      +-- No durable record to replay
~~~

For critical tasks (invoice emails, payment notifications, mandatory document generation, cross-service sync), consider a **transactional outbox**:

~~~text
BEGIN T1
  INSERT / UPDATE orders(...)
  INSERT outbox_events(event_id, aggregate_id, payload, status='PENDING')
COMMIT T1
        |
        +-- Worker polls outbox
        +-- Publish message / call external API
        +-- Retry with backoff and record status
        +-- Consumer deduplicates by eventId
~~~

Both the business change and the outbox row live in the same local transaction, so rolling back T1 rolls back both. A process dying after commit still leaves the outbox record intact. However, the relay may redeliver a message if it crashes between sending and marking completion; hence idempotency is required. `@TransactionalEventListener`, `fallbackExecution`, and `@Async` **do not automatically provide exactly-once delivery**.

If an event is completely unrelated to any DB transaction (e.g., an application lifecycle signal or in-memory update), a standard `@EventListener` may be the more semantically honest choice.

## 17. Symptom – Cause – Action Table

| Symptom | Likely cause | Remediation |
|---|---|---|
| `@EventListener` runs yet transactional listener is silent | Missing transaction at publish time | Log `txActive` at publish site; fix boundary |
| Enabling fallback makes listener run | Non-transactional publish path | Decide if immediate execution is allowed or true `AFTER_COMMIT` is needed |
| `@Transactional` present yet `txActive=false` | Self-invocation or unproxied object | Invoke Spring-managed bean through proxy |
| `@Transactional(SUPPORTS)` without outer T1 | `SUPPORTS` does not open a physical transaction | Use `REQUIRED` if business logic demands it |
| Published after `service.save()` | T1 already committed | Publish inside transactional service or use outbox |
| `@Async` worker publishes event | ThreadLocal transaction does not cross threads | Create worker transaction boundary or move publish site |
| R2DBC transaction active yet listener silent | Missing `TransactionContext` in event source | Use `TransactionalEventPublisher` in same subscription |
| Default `AFTER_COMMIT` skips, `AFTER_ROLLBACK` runs | Transaction rolled back, not missing transaction | Investigate exceptions and rollback-only flags |
| `AFTER_COMMIT` runs yet audit is not committed | Stale resource during completion | Call `REQUIRES_NEW` via another proxied bean |
| `@Transactional` test method misses callback | Test usually rolls back at end | Commit explicitly or avoid wrapping test transaction |
| No listeners receive anything | Wrong event type/bean/context | Check wiring and `ApplicationContext` |
| Need to avoid losing events on crash | In-JVM events are non-durable | Use outbox, queue, retries, and idempotency |

## 18. Checklist Before Concluding the Bug Is Fixed

1. Know the exact **event type** and publishing bean.
2. Confirm the listener bean resides in the right context.
3. Confirm a control `@EventListener` can receive the event.
4. Log transaction status **right at publication**, not only at request entry.
5. Verify the call path goes through the transactional proxy, avoiding self-invocation.
6. Check propagation, transaction manager, and datasource/resource.
7. Confirm the event is published **inside** rather than **after** the transactional method.
8. Identify thread, executor, scheduler, and Reactor subscription.
9. For reactive transactions, verify the event source carries `TransactionContext`.
10. Distinguish callbacks awaiting commit, skipped callbacks, and post-rollback callbacks.
11. Choose fallback based on semantics, not a desire to "just make it run".
12. Separate a new transaction for post-completion DB writes if needed.
13. Test all three paths (outside/commit/rollback) using a real transaction manager.
14. For critical processing, add a durable outbox/queue.
15. Record callback outcome metrics/logs and turn off verbose debug logging afterward.

## 19. Self-Check Questions

**1. Why is `@TransactionalEventListener` silent by default when published in `main`?** Because there is no transaction to register phase callbacks against, and `fallbackExecution` defaults to false.

**2. Does enabling `fallbackExecution=true` create a transaction?** No. It permits immediate execution outside a transaction; there is no corresponding commit or rollback.

**3. Can `@TransactionalEventListener(AFTER_ROLLBACK, fallbackExecution=true)` run even without a rollback?** Yes, via the fallback path when there is no transaction.

**4. Does `@Transactional(propagation=SUPPORTS)` guarantee a transaction exists?** No. If the caller has no transaction, `SUPPORTS` runs non-transactionally.

**5. Does placing `@Transactional` on the listener rescue a dropped event?** No, because the listener method may never be invoked at all.

**6. Why does imperative `isActualTransactionActive()` return false when a reactive transaction exists?** Because reactive transactions live in Reactor Context, not an imperative ThreadLocal.

**7. When published inside T1 and T1 rolls back, does `AFTER_COMMIT` run?** No. That is expected behavior, distinct from having no T1.

**8. Why does an `@Transactional` test miss `AFTER_COMMIT` callbacks?** Test-managed transactions are typically uncommitted at assertion time and roll back when the test ends.

**9. When should a regular `@EventListener` be used?** When event handling does not depend on transaction outcome and does not require phase-bound semantics.

**10. How does an outbox differ from fallback?** An outbox durably persists events alongside DB changes; fallback only controls whether a listener executes when no transaction exists.

## 20. Conclusion and Official Sources

**Lacking a transaction at publish time is the direct reason default `@TransactionalEventListener` handlers drop events.** Enabling `fallbackExecution=true` lets the listener run outside a transaction, yet creates no commit, carries no ThreadLocal across workers, and provides no durability. The most effective diagnosis pinpoints the publication boundary, transaction proxy/propagation, phase, and thread/reactive context; then decides whether to fix the transaction boundary, switch to a regular `@EventListener`, or adopt an outbox per business contract.

Reference documentation:

- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html): phases, fallbackExecution, reactive transactions.
- [Spring Framework 6.2.8 Javadoc — TransactionalEventListener](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html): default phase, discarded events, post-completion warning.
- [Spring Framework 6.2.8 Javadoc — TransactionPhase](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/event/TransactionPhase.html): BEFORE_COMMIT, AFTER_COMMIT, AFTER_ROLLBACK, AFTER_COMPLETION.
- [Spring Framework 6.2 — Declarative Transactions](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html): proxies, @Transactional, and propagation.
- [Spring Framework 6.2.8 Javadoc — TransactionSynchronizationManager](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html): checking imperative transactions/synchronization.
- [Spring Framework 6.2.8 Javadoc — TransactionalEventPublisher](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html): event source holding TransactionContext.