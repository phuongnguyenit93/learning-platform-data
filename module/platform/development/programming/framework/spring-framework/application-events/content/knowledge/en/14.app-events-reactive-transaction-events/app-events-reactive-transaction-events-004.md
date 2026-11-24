# Placing Transaction Context into the Event Source

In **Spring Framework Application Events**, the `@TransactionalEventListener` annotation can bind event handling to the `AFTER_COMMIT`, `AFTER_ROLLBACK`, `BEFORE_COMMIT`, or `AFTER_COMPLETION` phase. However, when an application uses **reactive transactions**, Spring needs to know which transaction an event belongs to, even though a Reactor pipeline can switch threads. Since **Spring Framework 6.1**, the official solution is to place **`TransactionContext` of the current reactive transaction into the `source` of `ApplicationEvent`**.

This lesson explains why, how to use `TransactionalEventPublisher` and `TransactionContextManager`, how to structure a proper Reactor pipeline, and how to test commit/rollback with Java 17+, Spring Test, R2DBC, and JUnit 5.

## 1. Why does ReactiveTransactionManager need a special event source?

Traditional JDBC/JPA transactions bind transaction state to a thread; within synchronous execution boundaries, Spring can look up the transaction in `ThreadLocal`. With `ReactiveTransactionManager`, transaction state resides in the **Reactor subscriber Context**; operators can execute on different threads while remaining within the same subscriber context.

`ApplicationEventPublisher` is only responsible for handing events to the multicaster. The `publishEvent(...)` call itself does not automatically turn an arbitrary object into an event carrying a reactive transaction context. For `@TransactionalEventListener` to register a callback on the right transaction, Spring reads the `TransactionContext` passed via **`ApplicationEvent.getSource()`**.

~~~text
Subscriber
  -> TransactionalOperator / reactive @Transactional
      -> Reactor Context: TransactionContext
      -> R2DBC INSERT/UPDATE
      -> publish ApplicationEvent
           source  = current TransactionContext
           payload = business data, e.g. orderId
      -> transaction ends
           commit   -> AFTER_COMMIT listener
           rollback -> AFTER_ROLLBACK listener
~~~

| Component | Role | Do not misunderstand as |
| --- | --- | --- |
| `TransactionContext` | Context of a reactive transaction, residing in Reactor Context | A business ID or serializable transaction to send over Kafka |
| `ApplicationEvent.source` | Supplies Spring with the context needed to associate the event with a reactive transaction | A place to put an arbitrary `String` or `ApplicationContext` when post-commit processing is wanted |
| Payload/event field | Carries business data such as order ID, task type, correlation ID | A replacement for transaction synchronization |
| `TransactionalEventPublisher` | Obtains context when the publisher is subscribed to, creates an event with the right `source` | A message broker or durable delivery guarantee |

**Distinction:** carrying `TransactionContext` in the source allows Spring to decide **when** to invoke the listener based on the transaction outcome. It does not persist the event to a database, does not guarantee execution if the process crashes after commit, and does not automatically create a new transaction for the listener.

## 2. Preferred approach: TransactionalEventPublisher

The `org.springframework.transaction.reactive.TransactionalEventPublisher` API (Spring Framework 6.1+) is a delegate that accepts an `ApplicationEventPublisher`. Declare a bean in Spring configuration:

~~~java
@Bean
TransactionalEventPublisher transactionalEventPublisher(
        ApplicationEventPublisher publisher) {
    return new TransactionalEventPublisher(publisher);
}
~~~

This is an excerpt inside a `@Configuration` class. The API has two overloads:

1. `Mono<Void> publishEvent(Object payload)`: Spring automatically creates a `PayloadApplicationEvent` using the current `TransactionContext` as source.
2. `Mono<Void> publishEvent(Function<TransactionContext, ApplicationEvent> factory)`: passes the context into the factory so the application constructs a custom `ApplicationEvent`.

### 2.1. Using a payload record

~~~java
record OrderCreated(String orderId) { }

// transactionalEventPublisher is an injected bean:
Mono<Void> send = transactionalEventPublisher.publishEvent(
    new OrderCreated("O-42")
);
~~~

A listener in a Spring bean can accept the payload and run only after commit:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onCreated(OrderCreated event) {
    notificationGateway.send(event.orderId());
}
~~~

The two snippets above are **excerpts**, requiring definitions/imports for the record, bean, gateway, and annotations. `TransactionalEventPublisher` creates a `PayloadApplicationEvent<OrderCreated>` whose **source** is `TransactionContext`, so the phase-bound listener has sufficient information. Do not confuse this with calling `ApplicationEventPublisher.publishEvent(new OrderCreated(...))` directly: the regular publisher does not actively attach `TransactionContext` to the source.

### 2.2. Using a custom ApplicationEvent

When you want a dedicated event class (to distinguish event types, carry business metadata, or inspect the source), define:

~~~java
import org.springframework.context.ApplicationEvent;

final class OrderCreatedEvent extends ApplicationEvent {
    private final String orderId;

    OrderCreatedEvent(Object source, String orderId) {
        super(source);
        this.orderId = orderId;
    }

    String orderId() {
        return orderId;
    }
}
~~~

And publish via the factory:

~~~java
Mono<Void> send = transactionalEventPublisher.publishEvent(
    transactionContext -> new OrderCreatedEvent(
        transactionContext, "O-42"
    )
);
~~~

When the publisher is subscribed to inside a reactive transaction, `event.getSource()` is an instance of `org.springframework.transaction.reactive.TransactionContext`. There is no need to read `ThreadLocal` yourself, set source to `this`, or pass Reactor `ContextView` instead of `TransactionContext`.

**Important:** the returned `Mono<Void>` does not execute simply upon creation. You must attach the `Mono` to a subscribed pipeline. `TransactionalEventPublisher` does not subscribe on the service's behalf.

## 3. Placing publication within the right transaction scope

Suppose an order is saved via a reactive repository and then an event is published. The right way is to compose both steps in the same pipeline and wrap the **entire pipeline** in `TransactionalOperator`:

~~~java
Mono<Void> operation = repository.save(order)
    .then(transactionalEventPublisher.publishEvent(
        ctx -> new OrderCreatedEvent(ctx, order.id())
    ));

return operation.as(transactionalOperator::transactional);
~~~

This is a service excerpt, requiring definitions for `repository`, `order`, the beans, and event classes. Because both `save()` and publication lie **inside** the chain controlled by `TransactionalOperator`, Spring obtains `TransactionContext` right when the publisher is subscribed to. `then` ensures saving completes before publishing; the `AFTER_COMMIT` listener still waits for **commit**, not merely for `save()`.

Contrast with the incorrect case:

~~~java
// Wrong: ends the save transaction before executing publish.
return repository.save(order)
    .as(transactionalOperator::transactional)
    .then(transactionalEventPublisher.publishEvent(
        ctx -> new OrderCreatedEvent(ctx, order.id())
    ));
~~~

Here the publish step lies **outside** the save operation's transaction. Upon subscription, `TransactionContextManager.currentContext()` has no matching transaction; the publisher can fail with `NoTransactionException`.

Another approach is `@Transactional` on a service returning `Mono` or `Flux`, when Spring uses `ReactiveTransactionManager` and the call actually goes through the Spring proxy:

~~~java
@Transactional
public Mono<Void> create(Order order) {
    return repository.save(order)
        .then(transactionalEventPublisher.publishEvent(
            ctx -> new OrderCreatedEvent(ctx, order.id())
        ));
}
~~~

This illustrative snippet is not a standalone Java file. With reactive transactions, the method must return an appropriate reactive type; do not self-invoke a `@Transactional` method via `this.create(...)` in default proxy mode and expect Spring to open a transaction.

### Avoiding nested subscriptions and dropped side effects

~~~java
// Wrong: creates an independent subscription inside doOnNext.
return repository.save(order)
    .doOnNext(saved -> transactionalEventPublisher
        .publishEvent(new OrderCreated(saved.id()))
        .subscribe());
~~~

This approach detaches the event-publishing step from the parent pipeline, making errors and transaction context hard to control. Calling `publishEvent(...)` inside `doOnNext` **without subscribing/composing the result** also prevents the event from being published at all. Use `flatMap`, `then`, or `concatMap` as appropriate to connect publishers and let the outermost subscriber govern the entire flow.

## 4. Manual approach with TransactionContextManager

`TransactionalEventPublisher` is a convenience, not the only way. Spring lets you obtain the current context and put it directly into an event's source:

~~~java
Mono<Void> publication = TransactionContextManager.currentContext()
    .map(ctx -> new OrderCreatedEvent(ctx, orderId))
    .doOnNext(applicationEventPublisher::publishEvent)
    .then();

return publication.as(transactionalOperator::transactional);
~~~

This is an excerpt, with `OrderCreatedEvent`, publisher, and operator provided by the application. Import `org.springframework.transaction.reactive.TransactionContextManager`. `currentContext()` returns `Mono<TransactionContext>` from the Reactor subscriber context/holder; when no context is found, it emits a `NoTransactionException` error.

Use this approach when you must control event construction manually. For most business cases, `TransactionalEventPublisher.publishEvent(...)` is cleaner and reduces the risk of forgetting the source.

### One event needs two distinct pieces of information

~~~text
OrderCreatedEvent
  source = TransactionContext  [used internally by Spring only]
  orderId = "O-42"             [business data]
~~~

Do not serialize `TransactionContext` into HTTP payloads, outboxes, Kafka, or logs. If an event must be pushed externally, create a separate message DTO containing the needed business data (such as eventId, orderId, createdAt). The transaction context is runtime state inside the JVM; it is not a transaction ID that can be "restored" in another process.

## 5. Integration test example with R2DBC and Spring Test

The following test suite uses Java 17+, Spring Framework 6.2, R2DBC H2, `TransactionalOperator`, and JUnit 5. It verifies three things: the event has the right source; callbacks run at the appropriate commit/rollback phase; and without subscribing there are no side effects. The tests are not wrapped in a test-managed JDBC transaction.

### 5.1. `build.gradle`

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation platform('org.springframework:spring-framework-bom:6.2.19')
    testImplementation 'org.springframework:spring-context'
    testImplementation 'org.springframework:spring-r2dbc'
    testImplementation 'org.springframework:spring-tx'
    testImplementation 'org.springframework:spring-test'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'

    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
    testRuntimeOnly 'io.r2dbc:r2dbc-h2:1.0.0.RELEASE'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Projects using Spring Boot should use the compatible versions managed by Boot's BOM. H2 is only the test database, whereas the core requirements for reactive event handling are Spring Context, Spring Transaction, and Reactor.

### 5.2. `src/test/java/example/events/ReactiveEventSourceTest.java`

~~~java
package example.events;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import io.r2dbc.spi.ConnectionFactories;
import io.r2dbc.spi.ConnectionFactory;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.r2dbc.connection.R2dbcTransactionManager;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.reactive.TransactionContext;
import org.springframework.transaction.reactive.TransactionalEventPublisher;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

@SpringJUnitConfig(ReactiveEventSourceTest.Config.class)
class ReactiveEventSourceTest {

    @Autowired DatabaseClient client;
    @Autowired OrderService service;
    @Autowired Trace trace;

    @BeforeEach
    void reset() {
        client.sql("CREATE TABLE IF NOT EXISTS orders (" +
                "id VARCHAR(64) PRIMARY KEY)")
            .fetch().rowsUpdated().block();

        client.sql("DELETE FROM orders")
            .fetch().rowsUpdated().block();
        trace.clear();
    }

    @Test
    void commitInvokesListenerWithTransactionSource() {
        service.create("O-100", false).block();

        assertEquals(
            List.of("published:O-100:true", "commit:O-100"),
            trace.snapshot()
        );
        assertEquals(1, rowCount("O-100"));
    }

    @Test
    void rollbackSkipsAfterCommit() {
        assertThrows(IllegalStateException.class,
            () -> service.create("O-200", true).block());

        assertEquals(
            List.of("published:O-200:true", "rollback:O-200"),
            trace.snapshot()
        );
        assertEquals(0, rowCount("O-200"));
    }

    @Test
    void monoWithoutSubscriptionDoesNothing() {
        Mono<Void> notSubscribed = service.create("O-300", false);

        assertEquals(List.of(), trace.snapshot());
        assertEquals(0, rowCount("O-300"));
    }

    private int rowCount(String id) {
        return client.sql("SELECT COUNT(*) FROM orders WHERE id = :id")
            .bind("id", id)
            .map((row, meta) -> ((Number) row.get(0)).intValue())
            .one()
            .block();
    }

    static final class OrderCreatedEvent extends ApplicationEvent {
        private final String orderId;

        OrderCreatedEvent(Object source, String orderId) {
            super(source);
            this.orderId = orderId;
        }

        String orderId() {
            return orderId;
        }
    }

    static final class Trace {
        private final List<String> values = new CopyOnWriteArrayList<>();

        void add(String value) {
            values.add(value);
        }

        List<String> snapshot() {
            return List.copyOf(values);
        }

        void clear() {
            values.clear();
        }
    }

    static final class OrderService {
        private final DatabaseClient client;
        private final TransactionalEventPublisher events;
        private final TransactionalOperator transaction;

        OrderService(DatabaseClient client,
                     TransactionalEventPublisher events,
                     TransactionalOperator transaction) {
            this.client = client;
            this.events = events;
            this.transaction = transaction;
        }

        Mono<Void> create(String id, boolean forceRollback) {
            Mono<Void> operation = client.sql(
                    "INSERT INTO orders(id) VALUES (:id)")
                .bind("id", id)
                .fetch()
                .rowsUpdated()
                .flatMap(affected -> {
                    if (affected != 1) {
                        return Mono.error(
                            new IllegalStateException("Insert failed"));
                    }
                    return events.publishEvent(
                        source -> new OrderCreatedEvent(source, id)
                    );
                })
                .then();

            if (forceRollback) {
                operation = operation.then(Mono.error(
                    new IllegalStateException("force rollback")));
            }
            return transaction.transactional(operation);
        }
    }

    static final class OrderListener {
        private final Trace trace;

        OrderListener(Trace trace) {
            this.trace = trace;
        }

        @EventListener
        public void onPublication(OrderCreatedEvent event) {
            boolean hasContext =
                event.getSource() instanceof TransactionContext;
            trace.add("published:" + event.orderId() + ":" + hasContext);
        }

        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
        public void onCommit(OrderCreatedEvent event) {
            trace.add("commit:" + event.orderId());
        }

        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_ROLLBACK)
        public void onRollback(OrderCreatedEvent event) {
            trace.add("rollback:" + event.orderId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    static class Config {
        @Bean
        ConnectionFactory connectionFactory() {
            return ConnectionFactories.get(
                "r2dbc:h2:mem:///event_source_test" +
                "?options=DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"
            );
        }

        @Bean
        DatabaseClient databaseClient(ConnectionFactory factory) {
            return DatabaseClient.create(factory);
        }

        @Bean
        ReactiveTransactionManager transactionManager(
                ConnectionFactory factory) {
            return new R2dbcTransactionManager(factory);
        }

        @Bean
        TransactionalOperator transactionalOperator(
                ReactiveTransactionManager manager) {
            return TransactionalOperator.create(manager);
        }

        @Bean
        TransactionalEventPublisher transactionalEventPublisher(
                ApplicationEventPublisher publisher) {
            return new TransactionalEventPublisher(publisher);
        }

        @Bean
        Trace trace() {
            return new Trace();
        }

        @Bean
        OrderListener orderListener(Trace trace) {
            return new OrderListener(trace);
        }

        @Bean
        OrderService orderService(DatabaseClient client,
                TransactionalEventPublisher events,
                TransactionalOperator transaction) {
            return new OrderService(client, events, transaction);
        }
    }
}
~~~

Run from a project with the Gradle wrapper:

~~~bash
./gradlew test --tests "example.events.ReactiveEventSourceTest"
~~~

On Windows PowerShell you can use `./gradlew.bat` instead of `./gradlew`. The tests do not print event records to stdout; the `published`, `commit`, and `rollback` traces are kept in `Trace` and checked with assertions.

**Why are these three tests meaningful?**

- The commit test confirms the regular listener receives an event with a `TransactionContext` source and the `AFTER_COMMIT` listener runs only when the transaction completes successfully. The DB retains one record `O-100`.
- The rollback test confirms publishing an event is not synonymous with committing: the `AFTER_ROLLBACK` listener records the event, `commit:O-200` does not appear, and the database has no record left.
- The unsubscribed test confirms merely *creating* a `Mono` neither executes SQL nor publishes. This matters because many reactive bugs stem from forgetting to compose a publisher.

The example uses the context's default synchronous listener mechanism while the transaction runs on `ReactiveTransactionManager`. If an application switches dispatching to async, you must also test asynchronous completion and errors, rather than inferring from the outer `block()` call that every fire-and-forget task has completed.

## 6. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `new OrderCreatedEvent("myService", id)` | `source` is not a `TransactionContext` | Use the `TransactionalEventPublisher` factory, passing `ctx` to `super(ctx)` |
| Using regular `ApplicationEventPublisher.publishEvent(payload)` | Event does not automatically carry the Reactor transaction context | Use `TransactionalEventPublisher.publishEvent(payload)` |
| Placing publish after `.as(transactionalOperator::transactional)` | The transaction has ended before publish | Wrap both save and publish in a single transaction pipeline |
| Calling `subscribe()` inside `doOnNext` | Creates another subscription with uncontrolled errors/context | Compose using `then` or `flatMap` |
| Creating `Mono<Void>` and leaving it unused | Does not publish the event | Ensure the publisher is subscribed to inside the main pipeline |
| Using `ThreadLocal` to read a reactive transaction | Fragile across thread switches | Use Reactor Context and `TransactionalEventPublisher` |
| `fallbackExecution = true` to "fix" lost context | Listener may run even without a proper transaction | Preserve proper context/source; enable fallback only when business logic allows |
| Writing to DB inside `AFTER_COMMIT` without opening a new transaction | Cannot assume another commit will happen for that change | Start an appropriate new transaction and test readback |
| Sending events to Kafka containing `TransactionContext` | Transfers internal state that has no meaning outside the JVM | Separate a business DTO, use an outbox if durable delivery is needed |

### When there is no reactive transaction

If the subscription has no current `TransactionContext`, `TransactionContextManager.currentContext()` signals `NoTransactionException`. With the default `@TransactionalEventListener`, an event published outside a suitable transaction is not handled by phase. `fallbackExecution = true` lets it run even without a transaction, but that is a change in **business contract** rather than a way to recover lost context.

### When combining with asynchronous methods and other systems

The context in the source helps **register transaction synchronization** at event publication time. It does not guarantee the listener automatically inherits context to continue accessing the DB on an already-completed transaction, does not provide retries, and does not automatically turn a publisher returned by a listener into awaited work.

If durable notifications must be sent after commit, consider a **transactional outbox**: write the business data and an outbox record in the same database transaction; a worker reads committed records and delivers them with retry/idempotency. Spring's internal event source is still not a payload to send to a broker.

## 7. Checklist and self-check exercises

- Confirm you are using Spring Framework **6.1+** and `ReactiveTransactionManager`.
- Confirm `TransactionalEventPublisher.publishEvent` is subscribed to **inside** the transaction pipeline.
- For custom `ApplicationEvent`s, pass the proper context to `super(source)`; keep `orderId` in a business field.
- Test `AFTER_COMMIT` with a real committing transaction; test rollback independently.
- If the code uses `@Transactional`, ensure a reactive return type and that calls go through the Spring proxy.
- If there is async processing, a broker, or post-commit data updates, add tests for transaction boundaries and dedicated delivery mechanisms.

**Question 1:** Why is an `ApplicationEvent` whose `source` is a service bean insufficient for reactive `AFTER_COMMIT`? Because that source does not contain the subscriber's `TransactionContext`, so Spring cannot associate the callback with the current reactive transaction.

**Question 2:** Does `TransactionalEventPublisher.publishEvent(Object payload)` automatically use the right source? Yes: it creates a `PayloadApplicationEvent` carrying the current `TransactionContext` if subscribed inside a reactive transaction.

**Question 3:** Can a `Mono` constructed outside a transaction be subscribed inside one? Yes, provided context lookup and publication execution happen **upon subscription** inside the transaction pipeline; what matters is the actual subscription scope.

**Question 4:** If an event was already published and the transaction then rolls back, is the `AFTER_COMMIT` listener invoked? No. An `AFTER_ROLLBACK` listener will handle it if registered for that phase and the event was transaction-bound.

**Question 5:** Does putting the transaction context in the source imply exactly-once message delivery? No. This is Spring's internal transaction-bound listener dispatch mechanism, not a cross-process reliability mechanism.

**Key takeaway:** `TransactionContext` in `ApplicationEvent.source` is the bridge between Spring events and the **Reactor transaction context**. Use `TransactionalEventPublisher` to supply the right source; keep the publisher inside the same reactive transaction chain so callbacks receive the true commit/rollback outcome.

## References

- [Spring Framework – Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework – TransactionalEventPublisher API](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html)
- [Spring Framework – TransactionContextManager API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/reactive/TransactionContextManager.html)
- [Spring Framework – Reactive TransactionalOperator API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/reactive/TransactionalOperator.html)
- [Spring Framework – R2DBC Data Access](https://docs.spring.io/spring-framework/reference/6.2/data-access/r2dbc.html)
