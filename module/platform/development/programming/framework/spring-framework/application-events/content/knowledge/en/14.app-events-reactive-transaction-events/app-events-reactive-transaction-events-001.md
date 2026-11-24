# Reactive Transactions in Spring 6.1: TransactionalEventPublisher and Transaction-Bound Events

## 1. Context: reactive transaction events in Spring Framework Application Events

When a WebFlux application using R2DBC writes data, a business event such as `OrderCreated` often needs to be processed **after the transaction commits**. For example, if creating an order succeeds, record a notification; if the database operation rolls back, do not notify that the order was created.

In Spring Framework prior to 6.1, `@TransactionalEventListener` was primarily bound to transactions managed by `PlatformTransactionManager`, relying on thread-bound state. **Since Spring Framework 6.1**, the transactional listener mechanism also supports transactions managed by `ReactiveTransactionManager`. The key requirement is that **`ApplicationEvent.source` must carry the reactive `TransactionContext`**. The new class `org.springframework.transaction.reactive.TransactionalEventPublisher` helps create the right event and publish it inside a reactive pipeline.

Lesson objectives:
- Distinguish reactive transactions from imperative transactions; understand Reactor `Context` and subscription-based lifecycle.
- Use `TransactionalOperator` or `@Transactional` for reactive pipelines.
- Publish events via `TransactionalEventPublisher` and compose `Mono<Void>` into the pipeline.
- Use `@TransactionalEventListener` with `AFTER_COMMIT`, `AFTER_ROLLBACK`, and other phases.
- Test commit, rollback, missing context, missing subscription, post-commit error handling, and event durability.

**Limitation:** transactional events only help invoke listeners according to the transaction phase. They are not a durable message queue, do not guarantee exactly-once delivery, and do not turn external side effects into an atomic part of the DB transaction.

## 2. Where is the transaction held?

| Aspect | Imperative transaction | Reactive transaction |
| --- | --- | --- |
| Transaction manager | `PlatformTransactionManager` | `ReactiveTransactionManager` |
| Database example | JDBC via `DataSourceTransactionManager` | R2DBC via `R2dbcTransactionManager` |
| Where transaction state is held | `ThreadLocal` of the current thread | Reactor `Context` attached to the reactive chain/subscription |
| Scoping API | `TransactionTemplate`, synchronous `@Transactional` | `TransactionalOperator`, `@Transactional` with a reactive return type |
| How listeners find context | Spring looks up the thread-bound transaction | The event must carry `TransactionContext` as its source |
| Execution timing | Typically when calling the method | The `Publisher` must be subscribed to |

In reactive programming, code may switch threads due to schedulers while the Reactor Context can still follow the chain. Conversely, two operations running sequentially on the same thread are **not guaranteed** to belong to the same transaction if they are in two different subscriptions/contexts.

Conceptual model:

```text
Subscription
   |
TransactionalOperator opens reactive transaction
   |
R2DBC saves order
   |
TransactionalEventPublisher.publishEvent(OrderCreated)
   | creates PayloadApplicationEvent
   | source = current TransactionContext
   | payload = OrderCreated
   | registers transactional listener with this transaction
   |
   +---- pipeline completes -> COMMIT
   |                         -> AFTER_COMMIT
   |
   +---- pipeline errors    -> ROLLBACK
                             -> AFTER_ROLLBACK
```

An event can be published while the transaction has **not yet committed** to register the callback; meanwhile, a side effect requested at `AFTER_COMMIT` is only executed after the commit. That is the difference between **the time the event is published** and **the time the listener handles it**.

## 3. New API in Spring 6.1

`TransactionalEventPublisher` takes an `ApplicationEventPublisher` (typically the Spring application context itself):

```java
TransactionalEventPublisher publisher =
    new TransactionalEventPublisher(applicationEventPublisher);
```

This is an integration snippet; `applicationEventPublisher` is injected or obtained from the application context.

### 3.1. Publishing a payload

```java
Mono<Void> publish = publisher.publishEvent(
    new OrderCreated(101L)
);
```

The `publishEvent(Object payload)` overload creates an event with the `TransactionContext` from the Reactor Context as its **source**, while keeping `OrderCreated` as the payload. A listener can declare a method accepting `OrderCreated`.

### 3.2. Explicitly constructing an ApplicationEvent

If you need to customize the event, use the `publishEvent(Function<TransactionContext, ApplicationEvent>)` overload:

```java
Mono<Void> publish = publisher.publishEvent(
    transactionContext -> new PayloadApplicationEvent<>(
        transactionContext,
        new OrderCreated(101L)
    )
);
```

This snippet requires `org.springframework.context.PayloadApplicationEvent` and compatible types. You can also use a custom `ApplicationEvent` class, as long as the event source is the reactive `TransactionContext`.

Both overloads return `Mono<Void>`. You must compose the `Mono` into the chain that currently holds the transaction. Writing:

```java
publisher.publishEvent(new OrderCreated(101L)); // Publisher IGNORED
```

does not cause the event to be published automatically. `Mono` is lazy by default: without an enclosing subscription, it does not execute.

### 3.3. Manually creating an event from TransactionContext

To understand the mechanism, the manual equivalent is:

```java
Mono<Void> publication = TransactionContextManager.currentContext()
    .map(source -> new PayloadApplicationEvent<>(
        source,
        new OrderCreated(101L)
    ))
    .doOnNext(applicationEventPublisher::publishEvent)
    .then();
```

This is an integration snippet, with `TransactionContextManager` in package `org.springframework.transaction.reactive`. Usually, `TransactionalEventPublisher` is preferred because it encapsulates retrieving the context and creating the event, reducing configuration mistakes.

## 4. Why isn't ApplicationEventPublisher.publishEvent(payload) enough?

In a reactive method, the following code looks as if it publishes an event inside a transaction:

```java
return database.sql("INSERT INTO orders (id) VALUES (:id)")
    .bind("id", orderId)
    .fetch()
    .rowsUpdated()
    .doOnNext(count ->
        applicationEventPublisher.publishEvent(
            new OrderCreated(orderId)
        )
    )
    .then();
```

This is an **illustrative pattern with a semantic bug**. `ApplicationEventPublisher.publishEvent(Object)` can wrap the payload into a `PayloadApplicationEvent`, but it does not automatically set the reactive `TransactionContext` as the event source. Because `@TransactionalEventListener` receives the context via the event source in the reactive model, the listener may fail to register for the right phase and be skipped by default when there is no compatible transaction.

The correct pattern to persist and register an event in a single chain:

```java
Mono<Void> workflow = database
    .sql("INSERT INTO orders (id) VALUES (:id)")
    .bind("id", orderId)
    .fetch()
    .rowsUpdated()
    .then()
    .then(transactionalEventPublisher.publishEvent(
        new OrderCreated(orderId)
    ));
```

This is an integration snippet that requires a reactive transaction wrapping the workflow. `then(publisherMono)` ensures publication executes **after** the R2DBC operation and within the same subscription/context. Do not call `subscribe()` separately on the publication; doing so can create a different subscription without the appropriate transaction.

## 5. Runnable Java 17+ example with Spring Context, R2DBC, and H2

The program below uses a real DB transaction and two listeners:
- `AFTER_COMMIT` for committed orders.
- `AFTER_ROLLBACK` for rolled-back orders.

The example uses **Spring Framework 6.1.21**, in-memory H2, and `TransactionalOperator`. It does not require Spring Boot or an external database. `block()` is only used in `main` so the console application waits for the result; do not use `block()` like this on production WebFlux processing threads.

Structure:

```text
reactive-transaction-events/
├── build.gradle
└── src/main/java/demo/ReactiveTransactionEventsDemo.java
```

Contents of `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.21'
    implementation 'org.springframework:spring-r2dbc:6.1.21'
    runtimeOnly 'io.r2dbc:r2dbc-h2:1.0.0.RELEASE'
}

application {
    mainClass = 'demo.ReactiveTransactionEventsDemo'
}
```

Contents of `src/main/java/demo/ReactiveTransactionEventsDemo.java`:

```java
package demo;

import io.r2dbc.spi.ConnectionFactories;
import io.r2dbc.spi.ConnectionFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.r2dbc.connection.R2dbcTransactionManager;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.reactive.TransactionalEventPublisher;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

public final class ReactiveTransactionEventsDemo {

    public record OrderCreated(long orderId) {}

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public OrderEventListener orderEventListener() {
            return new OrderEventListener();
        }
    }

    public static final class OrderEventListener {
        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void whenCommitted(OrderCreated event) {
            System.out.println("AFTER_COMMIT order=" + event.orderId());
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
        public void whenRolledBack(OrderCreated event) {
            System.out.println("AFTER_ROLLBACK order=" + event.orderId());
        }
    }

    public static void main(String[] args) {
        ConnectionFactory factory = ConnectionFactories.get(
            "r2dbc:h2:mem:///reactive_events" +
            "?options=DB_CLOSE_DELAY=-1"
        );

        DatabaseClient database = DatabaseClient.create(factory);
        database.sql(
            "CREATE TABLE orders (id BIGINT PRIMARY KEY)"
        ).fetch().rowsUpdated().then().block();

        R2dbcTransactionManager manager =
            new R2dbcTransactionManager(factory);
        TransactionalOperator transactions =
            TransactionalOperator.create(manager);

        try (var context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            TransactionalEventPublisher events =
                new TransactionalEventPublisher(context);

            Mono<Void> successFlow = database
                .sql("INSERT INTO orders (id) VALUES (1)")
                .fetch()
                .rowsUpdated()
                .then()
                .then(events.publishEvent(new OrderCreated(1L)));

            transactions.transactional(successFlow).block();

            Mono<Void> rollbackFlow = database
                .sql("INSERT INTO orders (id) VALUES (2)")
                .fetch()
                .rowsUpdated()
                .then()
                .then(events.publishEvent(new OrderCreated(2L)))
                .then(Mono.<Void>error(
                    new IllegalStateException("rollback requested")
                ));

            try {
                transactions.transactional(rollbackFlow).block();
            } catch (IllegalStateException expected) {
                System.out.println("rollback requested");
            }

            Long persistedRows = database
                .sql("SELECT COUNT(*) FROM orders")
                .map((row, metadata) ->
                    ((Number) row.get(0)).longValue()
                )
                .one()
                .block();

            System.out.println("rows persisted=" + persistedRows);
        }
    }
}
```

Run command (with JDK 17+ and Gradle available):

```bash
gradle run --quiet
```

**Expected business stdout lines:**

```text
AFTER_COMMIT order=1
AFTER_ROLLBACK order=2
rollback requested
rows persisted=1
```

Explanation:
1. Table creation occurs before the two demo transactions. `DB_CLOSE_DELAY=-1` keeps the in-memory H2 database alive across connections in the same process.
2. `transactions.transactional(successFlow).block()` subscribes to the workflow, opens a reactive transaction, and puts the connection into the Reactor Context. `INSERT 1` runs, then `events.publishEvent(OrderCreated(1))` registers the event with the right transaction.
3. The workflow completes, so the transaction commits. The `AFTER_COMMIT` listener prints the message for id 1.
4. The second workflow publishes the event after `INSERT 2`, then throws `IllegalStateException` **inside** the transaction scope. The transaction manager rolls back; the `AFTER_ROLLBACK` listener prints the message for id 2.
5. `catch` is placed **outside** the operator; it only handles the exception after the transaction has already rolled back. Using `onErrorResume` to swallow the error before the transaction manager sees it can lead to an unintended commit.
6. The `COUNT(*)` query executes after both transactions, so it only finds id 1.

Each subscription can re-execute side effects. In production, if you retry the entire workflow or re-subscribe to a Publisher, you must control idempotency, unique keys, and DB state.

## 6. Phases of @TransactionalEventListener

`@TransactionalEventListener` has the same phases for both imperative and reactive transactions:

| Phase | Meaning | Notes |
| --- | --- | --- |
| `BEFORE_COMMIT` | Invoked before commit | The transaction can still fail/roll back after the callback |
| `AFTER_COMMIT` | Invoked after a successful commit; **default** | Post-commit errors cannot roll back the original transaction |
| `AFTER_ROLLBACK` | Invoked after rollback | Used for cleanup, logging, or handling the failure branch |
| `AFTER_COMPLETION` | Invoked when the transaction has finished (commit/rollback) | Must not assume it always means success |

Example as methods in a Spring bean:

```java
@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
public void beforeCommit(OrderCreated event) {
    // Logic that needs to run before commit.
}

@TransactionalEventListener
public void afterSuccess(OrderCreated event) {
    // Default AFTER_COMMIT.
}

@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
public void afterFailure(OrderCreated event) {
    // Runs only on rollback.
}
```

The methods above are illustrative, not a standalone program. A listener does not automatically get a new transaction just because it is called "after commit". At completion time, some old transaction resources may still be available, but new DB write operations require their own transaction if they need to commit further changes.

If no suitable transaction exists, `@TransactionalEventListener` by default **does not process the event** because `fallbackExecution=false`. Setting `fallbackExecution=true` allows the listener to run even when there is no transaction, but in that case there is no actual commit to wait for. Only enable it when the business logic accepts fallback semantics.

## 7. @Transactional with a reactive return type

A reactive service can use `@Transactional` instead of `TransactionalOperator`, provided the transaction manager bean and transaction advice are configured properly.

Integration example (requires `@Service`, `@Transactional`, Spring bean `DatabaseClient`, and `TransactionalEventPublisher`):

```java
@Service
public class OrderService {
    private final DatabaseClient database;
    private final TransactionalEventPublisher events;

    public OrderService(DatabaseClient database,
                        TransactionalEventPublisher events) {
        this.database = database;
        this.events = events;
    }

    @Transactional
    public Mono<Void> createOrder(long id) {
        return database
            .sql("INSERT INTO orders (id) VALUES (:id)")
            .bind("id", id)
            .fetch()
            .rowsUpdated()
            .then()
            .then(events.publishEvent(new OrderCreated(id)));
    }
}
```

This snippet is **not a standalone runnable file**; the application must declare `OrderCreated`, the reactive transaction manager, and its listeners. Under default proxy configuration, service calls must go through the Spring proxy; internal self-invocation within the same bean typically does not apply `@Transactional`.

With `ReactiveTransactionManager`, the transaction binds when the returned publisher is **subscribed** to, not when the Java method merely constructs a `Mono`. Methods returning normal types or `void` do not carry the reactive transaction contract like `Mono`/`Flux`. Inside the same reactive chain, data access operations must use reactive-aware resources like `DatabaseClient` to participate in the transaction.

**Do not mix up `TransactionTemplate` and `TransactionalOperator`** just because their names are similar: `TransactionTemplate` is for imperative `PlatformTransactionManager`, while `TransactionalOperator` is for reactive `ReactiveTransactionManager`.

## 8. Reactor Context and easily overlooked mistakes

### 8.1. Calling the publisher outside a transaction

`TransactionalEventPublisher` uses the current transaction context. When subscribed outside a reactive transaction, it cannot retrieve a missing transaction context to put into the event source, so publishing may fail. Having `fallbackExecution=true` on the listener does not create a context for this publisher.

If the event does **not** need to depend on commit/rollback, use `ApplicationEventPublisher` or another pipeline with a clear contract.

### 8.2. Missing subscription

```java
Mono<Void> neverRuns =
    transactionalEventPublisher.publishEvent(new OrderCreated(1L));
```

This snippet only initializes a Mono; without a subscription, the event has not been published. In a WebFlux application, the framework normally subscribes to the publisher returned by the handler. In CLI/tests, `block()` or `StepVerifier` can be an appropriate subscription boundary.

### 8.3. Calling subscribe separately

```java
database.sql("INSERT ...").fetch().rowsUpdated().then().subscribe();
events.publishEvent(new OrderCreated(1L)).subscribe();
```

This is an **incorrect pattern for transactional business logic**: two subscriptions do not automatically share the same Reactor Context/transaction. Beyond losing the phase binding, errors are also hard to aggregate and retry. Compose a single publisher and wrap the transaction at the outer layer.

### 8.4. Using ThreadLocal to check a reactive transaction

There are two classes with the same name but different models:
- `org.springframework.transaction.support.TransactionSynchronizationManager`: supports imperative, thread-bound.
- `org.springframework.transaction.reactive.TransactionSynchronizationManager`: supports reactive, subscriber-context-bound.

Do not call the imperative ThreadLocal API to decide that a reactive pipeline has "no transaction". If you need to read the reactive context directly, use the reactive APIs designed for Reactor Context.

### 8.5. Confusing execution order

Creating a `Mono` does not guarantee a transaction already exists. The right sequence is **subscribe -> transaction begins -> R2DBC operation -> publish event -> commit/rollback -> listener phase**. `flatMap` can cause work to overlap; if the order of write-then-publish is a strict requirement, use `then(...)` or a composition method that guarantees the desired completion order.

`map(...)` on a `Mono<Void>` does not invoke a side effect upon completion because `Mono<Void>` emits no `onNext` item. Use `then(...)` for sequential follow-up tasks.

## 9. Should reactive I/O be handled inside an after-commit listener?

`@TransactionalEventListener` helps **choose when to invoke the handler**, not automatically manage an arbitrary reactive chain created inside the handler. For example:

```java
@TransactionalEventListener
public void onCreated(OrderCreated event) {
    remoteClient.sendNotification(event.orderId()).subscribe();
}
```

This is an **illustrative anti-pattern**: `remoteClient` is assumed to be injected. Calling `subscribe()` spawns an unmanaged task with no reliable completion tracking, retry, backpressure, or shutdown handling. Errors may never reach where the caller expects, while the original transaction has already committed.

If it is only a best-effort side task that can be lost, log errors and bound resources. If reliability is required, consider:
- Storing an **outbox record** in the same reactive DB transaction as the business record; an independent worker reads and sends it after commit.
- Making consumers idempotent by business key or stable `eventId`, with retry and monitoring.
- When you must create new records after commit, open a **new reactive transaction** in an appropriate service (via `TransactionalOperator`/`@Transactional`) and coordinate an explicit error policy.

**There is no default exactly-once guarantee:** an `AFTER_COMMIT` listener might not finish running if the process stops right after the DB commit. Internal Spring events are not durable across restarts. A transactional outbox helps narrow the event-loss gap by persisting the intent to send within the same transaction.

## 10. Testing commit, rollback, and context errors

Do not just test that a listener is registered. Integration tests need to verify both **DB state** and **callback phase**.

| Scenario | Test design | Expectation |
| --- | --- | --- |
| Real commit | Insert + publish inside the same TransactionalOperator and subscribe to completion | DB contains data; `AFTER_COMMIT` called once |
| Rollback | Insert + publish then emit `Mono.error` before commit | DB has no record; `AFTER_ROLLBACK` called |
| No subscribe | Create Mono without subscribing | No DB operation or event executed |
| Publisher without context | Subscribe `TransactionalEventPublisher` outside a transaction | Cannot obtain reactive transaction context to publish properly |
| Wrong source | Use normal publisher inside a reactive transaction | Transactional listener lacks a valid reactive source to bind phase |
| Swallowing error in transaction | `onErrorResume` inside operator turns error into completion | Must check risk of unintended commit |
| Replay/retry | Re-subscribe pipeline or retry on error | Side effects are not invalidly duplicated |
| Post-commit failure | Simulate API or job failure in after-commit | Original DB transaction remains committed; error needs separate observability/recovery |

If using `reactor-test`, you can verify pipeline signals:

```java
StepVerifier.create(transactions.transactional(successFlow))
    .verifyComplete();

StepVerifier.create(transactions.transactional(rollbackFlow))
    .expectError(IllegalStateException.class)
    .verify();
```

This is an **illustrative test snippet**, assuming the variables from the example already exist and the `io.projectreactor:reactor-test` dependency is added. Each `StepVerifier` creates a real subscription, so the pipeline can perform DB operations. Avoid reusing the same ID or shared test state when you want tests to run independently.

Also test the actual callback count, event ID, payload immutability, transaction manager name, and error paths when context is missing. Do not use `Thread.sleep` to "wait for commit"; use publisher completion results or appropriate test signals.

## 11. Distinguishing three easily confused event types

| Type | Usage | Consequence |
| --- | --- | --- |
| Regular event | `@EventListener` + `ApplicationEventPublisher` | Handled on dispatch; not tied by default to commit/rollback |
| Imperative transactional event | `@TransactionalEventListener` in `PlatformTransactionManager` | Relies on thread-bound transaction state |
| Spring 6.1 reactive transactional event | `@TransactionalEventListener` + event source is `TransactionContext`, usually created by `TransactionalEventPublisher` | Registers callbacks along the reactive transaction lifecycle |

In Spring 6.1, a transactional listener may run on the publishing thread to register synchronization even when the multicaster is configured as async. Do not assume `@Async` preserves the reactive transaction context or makes post-commit side effects durable. If a listener must invoke a long-running reactive workflow, decouple and manage that pipeline according to delivery requirements.

## 12. Common mistakes

1. **Calling the regular publisher and expecting a transactional listener to find Reactor Context automatically.** You must put `TransactionContext` into the event source.
2. **Ignoring the `Mono<Void>` returned by `TransactionalEventPublisher`.** Without a subscription, nothing is published.
3. **Calling subscribe multiple times inside a service.** Easily detaches from the transaction and causes duplicate side effects.
4. **Assuming switching threads necessarily loses Reactor Context or staying on the same thread always has context.** What determines it is the subscription/context.
5. **Using imperative `TransactionSynchronizationManager` to query reactive transaction state.** The two APIs have different state mechanisms.
6. **Calling `block()` inside a reactive WebFlux handler/worker.** Risks blocking the event-loop and reducing throughput.
7. **Using `onErrorResume` before the point where the manager decides rollback.** Turning an error into success can lead to a commit.
8. **Enabling `fallbackExecution=true` to mask missing source errors.** Can process events even when there was no actual commit.
9. **Performing new DB writes after commit without creating a new transaction.** Old transaction resources may still be bound, with no guarantee of committing again.
10. **Treating `AFTER_COMMIT` as a durable queue.** A crash after commit can still lose unprocessed tasks.
11. **Failing to design idempotency for retried events.** Another subscribe/retry can re-emit the event.
12. **Relying on logs or listener ordering as proof of commit.** Must verify actual DB outcome and phase.

## 13. Implementation checklist

- [ ] Actual data persistence is coordinated by `ReactiveTransactionManager` and uses an appropriate R2DBC/reactive driver.
- [ ] Service has a reactive return type; the transaction starts on subscribe rather than merely when constructing the Mono.
- [ ] `TransactionalEventPublisher` is created from an `ApplicationEventPublisher` and publication runs within the right transaction context.
- [ ] `publishEvent(...)` is in the same chain as data operations, without a separate subscribe.
- [ ] Listener has `@TransactionalEventListener` with the right phase; defaults `AFTER_COMMIT` and `fallbackExecution=false` are understood.
- [ ] Reactor Context is not confused with ThreadLocal, and async is not assumed to inherit transactions.
- [ ] Tests cover commit, rollback, no transaction, no subscribe, retry, and post-commit failure.
- [ ] Critical side effects have a retry/idempotency plan, and an outbox when durability is required.
- [ ] You can distinguish "DB committed", "event registered callback", "listener ran", and "external system task completed".

**Takeaway:** since Spring Framework 6.1, transactional listeners support reactive transactions when the event carries the proper `TransactionContext`. Publish events with `TransactionalEventPublisher` **inside** the reactive transaction pipeline and verify the actual phase, rather than relying on thread state.

## References

- [Spring 6.1.21 Javadoc — TransactionalEventPublisher](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html)
- [Spring 6.1.21 Javadoc — TransactionalEventListener](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework Reference — Data Access with R2DBC](https://docs.spring.io/spring-framework/reference/6.2/data-access/r2dbc.html)
- [R2DBC H2 — Connection Factory and URL](https://github.com/r2dbc/r2dbc-h2)
