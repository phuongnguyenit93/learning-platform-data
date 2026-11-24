# Transaction-Bound Listeners in Reactive Flows

## 1. Problem: events must only be handled when a reactive transaction reaches the right state

In a Spring application using Reactor and R2DBC, a flow can persist an order, publish `OrderCreated`, and then commit. A listener should only send a notification or update secondary state **after a successful commit**; if the write operation rolls back, the `AFTER_COMMIT` listener must not execute.

Spring's tool is `@TransactionalEventListener`, yet registering a listener in a reactive transaction has an important difference from traditional JDBC/JPA: **a reactive transaction lives in the subscriber's Reactor `Context`, not in the thread's `ThreadLocal`**. Thus, the event must carry the proper transaction context so Spring can associate the callback with the commit/rollback of the right subscription.

Since **Spring Framework 6.1**, `@TransactionalEventListener` supports both traditional transactions managed by `PlatformTransactionManager` and reactive transactions managed by `ReactiveTransactionManager`. For reactive transactions, Spring requires **`TransactionContext` to be in the `source` of `ApplicationEvent`**. `TransactionalEventPublisher` is the utility that handles this.

### Desired flow

~~~text
Client subscribes
    |
    v
TransactionalOperator / @Transactional on Mono or Flux
    |
    +-- BEGIN reactive transaction T1
    |
    +-- INSERT orders via R2DBC (same Reactor Context)
    |
    +-- TransactionalEventPublisher.publishEvent(orderCreated)
    |      |
    |      +-- retrieves TransactionContext of current subscription
    |      +-- creates ApplicationEvent with source = TransactionContext
    |      +-- multicaster notifies listener to register synchronization
    |
    +-- pipeline completes ----------------------------> COMMIT T1
    |                                                     |
    |                                                     +-- AFTER_COMMIT listener
    |
    +-- pipeline errors -------------------------------> ROLLBACK T1
                                                          |
                                                          +-- AFTER_ROLLBACK listener
~~~

**Model limitation:** publishing events via `ApplicationEventPublisher` only delivers events to the internal listener system. It does not create a message broker, does not guarantee replay after a crash, and does not guarantee exactly-once processing.

## 2. How do reactive transactions differ from thread-bound transactions?

| Aspect | Imperative transaction | Reactive transaction |
| --- | --- | --- |
| Transaction manager | `PlatformTransactionManager`, e.g. `DataSourceTransactionManager` | `ReactiveTransactionManager`, e.g. `R2dbcTransactionManager` |
| Where context is held | Primarily `ThreadLocal` of the current thread | Reactor `Context` attached to subscriber/reactive chain |
| Data access code | Synchronous JDBC/JPA | R2DBC/reactive repository returning `Mono` or `Flux` |
| Transaction boundary | Transaction interceptor around synchronous call | Transaction interceptor/operator around **subscribing and emitting signals** |
| Binding event to transaction | Spring can inspect thread-bound transaction | Event must contain `TransactionContext` as `source` for listener to register synchronization |
| Common mistake | Switching to another thread loses thread context | Splitting the chain or manual `subscribe()` runs logic outside expected subscription |

`publishOn` or `subscribeOn` **does not inherently lose Reactor Context** if the Reactor chain is composed properly: context follows the subscription rather than a fixed thread. The risk lies in creating a **separate subscription**, offloading work to systems that do not carry context, or assembling pipelines outside the transaction scope.

When using Spring `@Transactional` with `ReactiveTransactionManager`, the transactional method must return a suitable reactive type such as `Mono<T>` or `Flux<T>`; a `void` method cannot act as a reactive transactional method in the usual way.

## 3. How does TransactionalEventPublisher place context into an event?

`org.springframework.transaction.reactive.TransactionalEventPublisher` was introduced by Spring in version 6.1. It takes an `ApplicationEventPublisher` and provides two main usage patterns:

~~~java
// Publisher returns Mono<Void>; must be composed into the reactive chain.
Mono<Void> published = transactionalEventPublisher.publishEvent(
    new OrderCreated(101L)
);
~~~

In the example above, `OrderCreated` is a regular payload. Spring creates a `PayloadApplicationEvent<OrderCreated>` whose **source is the active `TransactionContext`**. The listener can still declare the business parameter `OrderCreated`.

If you want an event class extending `ApplicationEvent`, use a factory receiving the context:

~~~java
// Illustrative snippet requiring appropriate variables and classes.
Mono<Void> published = transactionalEventPublisher.publishEvent(
    transactionContext -> new OrderCreatedApplicationEvent(
        transactionContext, 101L
    )
);
~~~

With an illustrative constructor:

~~~java
final class OrderCreatedApplicationEvent
        extends org.springframework.context.ApplicationEvent {
    private final long orderId;

    OrderCreatedApplicationEvent(Object source, long orderId) {
        super(source);
        this.orderId = orderId;
    }

    long orderId() {
        return orderId;
    }
}
~~~

Both approaches ensure the **event source** is the transaction context when invoked inside a valid reactive transaction. Depending on how the event is modeled, the listener accepts either the payload or the specific `ApplicationEvent` class.

**Special notes:**

- `TransactionalEventPublisher` **does not open a transaction**. It retrieves the current context; event publication must be invoked within a chain that already has a transaction.
- The method returning `Mono<Void>` is **lazy**: merely assigning a `Mono` variable without putting it into a subscribed chain means the event is not published yet.
- Do not create a `Mono` and call `subscribe()` independently inside a service; the new subscription does not automatically inherit the enclosing transactional subscription's context.
- Only put `TransactionContext` into **`source`**; there is no need to put the entire transaction object or DB connection into the business payload. The payload should hold the necessary data, such as `orderId`.
- Do not fabricate a fake `TransactionContext` to trick the listener. The context must belong to a real Spring-managed transaction.

Calling `ApplicationEventPublisher.publishEvent(new OrderCreated(...))` directly in a reactive flow can lack the special source. Without the context source and without a matching thread-bound transaction, the transaction-bound listener **cannot register synchronization** and does not run by default.

## 4. Listener phases and their meaning in reactive flows

`@TransactionalEventListener` still uses the same phases as in imperative programming:

| Phase | When is the callback invoked? | Business example |
| --- | --- | --- |
| `BEFORE_COMMIT` | Before the transaction commits, when synchronization runs | Synchronous checks or finalizing work in the same transaction, if suited to the callback mechanism |
| `AFTER_COMMIT` (**default**) | After a successful commit | Business notifications sent only after the order exists |
| `AFTER_ROLLBACK` | After the transaction rolls back | Recording failures into an independent system |
| `AFTER_COMPLETION` | After the transaction finishes, whether commit or rollback | Resource cleanup/logging independent of outcome |

When **there is no transaction**, a `@TransactionalEventListener` is skipped by default. Enable `fallbackExecution = true` to also handle events outside a transaction if business logic allows, though fallback behavior **no longer guarantees after-commit semantics**.

Furthermore, the listener callback is part of the synchronization mechanism. Do not interpret "listener runs after commit" as "any publisher returned by the listener will automatically be subscribed to in a new transaction". If the callback needs new R2DBC operations, you must organize an independent reactive pipeline with explicit transaction and subscription boundaries.

## 5. Runnable example: H2 R2DBC + TransactionalOperator + commit/rollback listeners

The demo uses **Java 17+**, Spring Framework **6.2.19**, Reactor Core **3.7.19**, and H2 R2DBC. No Spring Boot is needed. It opens a reactive transaction T1, saves an order, and publishes an event in the same pipeline; then it tests commit and intentional rollback in sequence.

Project structure:

~~~text
reactive-transaction-events/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/ReactiveTxEventsDemo.java
~~~

Create `settings.gradle`:

~~~groovy
rootProject.name = 'reactive-transaction-events'
~~~

Create `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
    implementation 'org.springframework:spring-tx:6.2.19'
    implementation 'org.springframework:spring-r2dbc:6.2.19'
    implementation 'io.projectreactor:reactor-core:3.7.19'
    implementation 'io.r2dbc:r2dbc-h2:1.0.0.RELEASE'
}

application {
    mainClass = 'demo.ReactiveTxEventsDemo'
}
~~~

Create `src/main/java/demo/ReactiveTxEventsDemo.java`:

~~~java
package demo;

import io.r2dbc.spi.ConnectionFactories;
import io.r2dbc.spi.ConnectionFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.r2dbc.connection.R2dbcTransactionManager;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Component;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.reactive.TransactionalEventPublisher;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

@Configuration
@EnableTransactionManagement
@ComponentScan(basePackageClasses = ReactiveTxEventsDemo.class)
public class ReactiveTxEventsDemo {

    @Bean
    ConnectionFactory connectionFactory() {
        return ConnectionFactories.get(
            "r2dbc:h2:mem:///reactive_events" +
            "?options=DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"
        );
    }

    @Bean
    DatabaseClient databaseClient(ConnectionFactory factory) {
        return DatabaseClient.create(factory);
    }

    @Bean
    ReactiveTransactionManager transactionManager(ConnectionFactory factory) {
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

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                ReactiveTxEventsDemo.class)) {

            var db = context.getBean(DatabaseClient.class);
            db.sql("CREATE TABLE orders (id BIGINT PRIMARY KEY)")
                .then()
                .block();

            var service = context.getBean(OrderService.class);

            // T1 commit -> AFTER_COMMIT listener handles order 101.
            service.createOrder(101L, false).block();

            // T2 rollback -> AFTER_ROLLBACK listener handles order 102.
            try {
                service.createOrder(102L, true).block();
            } catch (IllegalStateException ex) {
                System.out.println("caught rollback: 102");
            }

            Long total = db.sql("SELECT COUNT(*) FROM orders")
                .map((row, metadata) ->
                    ((Number) row.get(0)).longValue())
                .one()
                .block();

            System.out.println("rows in DB: " + total);
        }
    }
}

// Pure data payload. TransactionContext is in the source
// of the PayloadApplicationEvent created by TransactionalEventPublisher.
record OrderCreated(long orderId) {}

@Component
class OrderService {
    private final DatabaseClient db;
    private final TransactionalEventPublisher events;
    private final TransactionalOperator transaction;

    OrderService(DatabaseClient db,
                 TransactionalEventPublisher events,
                 TransactionalOperator transaction) {
        this.db = db;
        this.events = events;
        this.transaction = transaction;
    }

    Mono<Void> createOrder(long id, boolean forceRollback) {
        Mono<Void> work = db.sql(
                    "INSERT INTO orders (id) VALUES (:id)")
                .bind("id", id)
                .fetch()
                .rowsUpdated()
                .then(events.publishEvent(new OrderCreated(id)))
                .then(Mono.defer(() -> forceRollback
                    ? Mono.<Void>error(
                        new IllegalStateException("forced rollback"))
                    : Mono.<Void>empty()));

        // Reactive transaction wraps both INSERT and publishEvent.
        // All steps execute when the caller subscribes/blocks.
        return transaction.transactional(work);
    }
}

@Component
class OrderEventListener {

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
    public void onCommit(OrderCreated event) {
        System.out.println("after commit: " + event.orderId());
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_ROLLBACK)
    public void onRollback(OrderCreated event) {
        System.out.println("after rollback: " + event.orderId());
    }
}
~~~

Run in the project directory using JDK 17+ and Gradle (or Gradle Wrapper if the project already has one):

~~~bash
gradle run --quiet
# If wrapper is present: ./gradlew run --quiet
# Windows: gradlew.bat run --quiet
~~~

Lines emitted to `System.out` by the program, in order:

~~~text
after commit: 101
after rollback: 102
caught rollback: 102
rows in DB: 1
~~~

Explanation:

1. `createOrder(101, false)` builds reactive pipeline T1. When `block()` subscribes, R2DBC inserts order 101, then `TransactionalEventPublisher.publishEvent(...)` sends `OrderCreated(101)` to the multicaster with T1's `TransactionContext` as source.
2. Listeners register the appropriate transaction synchronizations. The pipeline completes without error -> T1 commits; the `AFTER_COMMIT` callback prints `after commit: 101`. The `AFTER_ROLLBACK` callback does not run for this event.
3. `createOrder(102, true)` also inserts and publishes an event in T2, but emits an error at the end. T2 rolls back -> the `AFTER_ROLLBACK` callback prints `after rollback: 102`. The error propagates to `block()` and is caught by `catch` in `main`; `AFTER_COMMIT` does not run for order 102.
4. The final query gives `rows in DB: 1`: only order 101 exists. Order 102's event was published in the flow, yet the post-commit listener did not execute.

**Key learning point:** calling `publishEvent(...)` **in the chain** via `.then(events.publishEvent(...))` ensures it executes after INSERT and before the transactional operator finishes. If you only create a `Mono` without composing it into the chain, the event is not published. If you call `events.publishEvent(...).subscribe()` inside the service, it easily splits off into a subscription lacking the current transaction context.

`block()` in the demo is only used in `main` to wait for the console program to finish. In WebFlux/reactive handlers or non-blocking processing threads, **return `Mono`/`Flux`** for the runtime to subscribe; never call `block()` inside handlers or listeners.

## 6. Why can regular publishEvent cause the listener not to run?

Compare the two approaches inside a reactive transaction:

~~~java
// INSUFFICIENT FOR REACTIVE TRANSACTION-BOUND LISTENERS:
// Regular ApplicationEventPublisher does not automatically put
// Reactor TransactionContext into the event source.
return db.sql("INSERT INTO orders (id) VALUES (:id)")
    .bind("id", id)
    .fetch()
    .rowsUpdated()
    .doOnSuccess(count ->
        applicationEventPublisher.publishEvent(new OrderCreated(id)))
    .then();
~~~

~~~java
// CORRECT: the event carries TransactionContext in its source,
// and the publishing Mono<Void> is composed into the same reactive chain.
return db.sql("INSERT INTO orders (id) VALUES (:id)")
    .bind("id", id)
    .fetch()
    .rowsUpdated()
    .then(transactionalEventPublisher.publishEvent(new OrderCreated(id)));
~~~

These two snippets illustrate only **the body of a pipeline**: to truly be transaction-bound, you still need to wrap the whole thing with `TransactionalOperator` or a reactive `@Transactional` method using `ReactiveTransactionManager`. Do not paste snippets into a demo while forgetting the transaction boundary.

Calling `ApplicationEventPublisher.publishEvent(...)` directly is **not always wrong**: it is valid for regular events or when using thread-bound transactions. However, **for reactive transaction-bound listeners**, it does not automatically carry `TransactionContext` as required by Spring 6.1+.

Another explicit alternative is to retrieve `TransactionContextManager.currentContext()`, create `PayloadApplicationEvent<>(transactionContext, payload)`, and pass it through `ApplicationEventPublisher`. However, `TransactionalEventPublisher` already encapsulates this exact operation, reducing the risk of mistakes.

## 7. Reactive context, threads, and subscriptions: easily confused scenarios

### Scenario A — Creating a publisher without subscribing

~~~java
Mono<Void> pending = transactionalEventPublisher.publishEvent(
    new OrderCreated(5L)
);
// Neither returns pending, nor composes into flow, nor subscribes.
// No event is published from this snippet.
~~~

Reactor is lazy. This is why `then(...)`, `flatMap(...)`, or an appropriate reactive composition structure is required.

### Scenario B — Independent subscribe right inside a transaction

~~~java
// Anti-pattern: opens a separate subscription and drops lifecycle management.
transactionalEventPublisher.publishEvent(new OrderCreated(5L))
    .subscribe();
~~~

The new subscription may lack the outer publisher's `TransactionContext`; errors can appear as "no transaction in context", or observed behavior may diverge from expectations. Return the publisher and compose it with Reactor operators.

### Scenario C — Switching schedulers

~~~java
Mono<Void> work = transactionalEventPublisher
    .publishEvent(new OrderCreated(5L))
    .publishOn(reactor.core.scheduler.Schedulers.parallel());
~~~

If `work` is subscribed to **inside the corresponding transaction chain**, `publishOn` preserves the subscriber context by Reactor convention. There is no need to force everything onto the same thread. However, callbacks dispatched to APIs running outside Reactor, interacting with external ThreadLocals, or secretly calling `subscribe()` still require dedicated context/lifecycle propagation handling.

### Scenario D — Event without an active transaction

With the default `fallbackExecution = false`, the listener is not invoked if an event is published outside a transaction capable of registering synchronization. If the publisher requires `TransactionContext` but no valid context exists, retrieving the context can emit a reactive error; this **differs** from using a regular event publisher where the listener is simply skipped. Do not enable `fallbackExecution = true` just to mask transaction-creation or reactive-chain-composition bugs.

## 8. What if a listener needs R2DBC operations after commit?

The `AFTER_COMMIT` callback indicates that **T1 has committed**. It **does not provide a new T2 transaction** for subsequent write operations. Similar to the imperative mechanism, some resources from the original transaction may still be in cleanup. With reactive transactions, you definitely should not assume a `void` callback is a place where you can safely run a DB-writing `Mono` by creating it and walking away.

If you genuinely need to write another record **after** commit:

- Design a dedicated write pipeline with an appropriate `ReactiveTransactionManager`/`TransactionalOperator`, an explicit **T2 transaction** boundary, and ensure that pipeline has its lifecycle, errors, and retries managed per application requirements.
- If `REQUIRES_NEW` is needed, you can create a `TransactionalOperator` with `DefaultTransactionDefinition` and `PROPAGATION_REQUIRES_NEW`. It opens a new transaction when the pipeline is subscribed to; configuring propagation **does not subscribe automatically**.
- Do not call `block()` inside an event listener running on a non-blocking thread; do not use "fire and forget" `subscribe()` without managing completion/errors.
- If the secondary operation must survive process crashes, consider a **transactional outbox**: write `orders` and `outbox` in the same T1, then have an independent worker process the outbox with retry/idempotency.

Example configuring a separate operator—an **embedded illustrative snippet**, not a standalone program:

~~~java
var definition = new org.springframework.transaction.support
    .DefaultTransactionDefinition();
definition.setPropagationBehavior(
    org.springframework.transaction.TransactionDefinition.PROPAGATION_REQUIRES_NEW
);

var newTransaction = TransactionalOperator.create(
    reactiveTransactionManager, definition
);

// Return this Mono to the appropriate lifecycle/subscription management layer.
Mono<Void> saveAudit = newTransaction.transactional(
    databaseClient.sql(
        "INSERT INTO audit_log (order_id) VALUES (:orderId)")
        .bind("orderId", orderId)
        .then()
);
~~~

The snippet above assumes `reactiveTransactionManager`, `databaseClient`, `orderId`, and the `audit_log` table already exist. It illustrates the **T2 boundary**, not just how to wire that publisher into a specific callback. Mistakenly calling a `@Transactional` method with a `void` return type does not create a proper reactive transaction either.

A business note: **an already-committed T1 cannot be rolled back by an error in T2**. Therefore, for audit entries that must atomically coexist with the order, write them inside T1; for reliable integration across external systems, an outbox is usually more appropriate.

## 9. Testing transaction-bound listeners and troubleshooting

A useful test suite should distinguish at least four scenarios:

| Test case | Outcome to verify |
| --- | --- |
| Transaction commits successfully | `AFTER_COMMIT` runs exactly once for the event published in the test; `AFTER_ROLLBACK` does not run |
| Transaction rolls back | `AFTER_ROLLBACK` runs; `AFTER_COMMIT` does not run; DB changes in T1 are rolled back |
| Event published outside transaction | Listener is skipped by default, or `TransactionalEventPublisher` reports missing context on subscribe |
| Subscription split via `subscribe()` | Must not assume same transaction; replace with a single verified chain |

Diagnose in order:

1. **Check the transaction manager type**: are you using `ReactiveTransactionManager` or accidentally using `PlatformTransactionManager`? For R2DBC, use `R2dbcTransactionManager` matching the connection factory.
2. **Verify the event was actually published**: was the publisher subscribed to? Is `Mono<Void>` properly chained after the DB statement?
3. **Check the source**: does the event intended for reactive listeners have `TransactionContext`? Using `TransactionalEventPublisher` is the standard way.
4. **Check timing**: `AFTER_COMMIT` runs only after a successful commit; if the transaction rolls back or is cancelled, there is no after-commit callback. Cancellation in reactive transactions must be handled carefully; do not treat it as a commit.
5. **Look for detached subscriptions**: manual `subscribe()`, callbacks handed off to systems outside Reactor, or code creating publishers without returning them.
6. **Check listener execution errors**: the event was registered, yet the listener might throw an exception or async side work might fail; use appropriate logging, metrics, and retry mechanisms. Do not confuse "dispatched event" with "side work succeeded".
7. **Re-read data from an independent connection after the transaction completes** to verify commit/rollback, rather than relying on a "called INSERT" log.

### Key takeaways

~~~text
ReactiveTransactionManager -> transaction in Reactor Context
TransactionalEventPublisher -> event.source = TransactionContext
@TransactionalEventListener -> handles according to registered phase
Mono/Flux -> must be in a subscribed reactive chain
AFTER_COMMIT -> T1 has committed; further writes need an explicit T2
~~~

## Official references

- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework 6.2 — TransactionalEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html)
- [Spring Framework 6.2 — TransactionalEventListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Framework — TransactionalOperator Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/reactive/TransactionalOperator.html)
- [Spring Framework — R2DBC transaction management](https://docs.spring.io/spring-framework/reference/6.2/data-access/r2dbc.html)
- [R2DBC H2 project documentation](https://github.com/r2dbc/r2dbc-h2)
