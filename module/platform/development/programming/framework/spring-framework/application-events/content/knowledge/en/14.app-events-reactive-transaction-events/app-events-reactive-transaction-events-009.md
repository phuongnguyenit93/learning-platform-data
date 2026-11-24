# Limitations When Mixing Imperative and Reactive in Spring Transaction Events

Spring Framework supports two distinct transaction models:

- **Imperative transactions** are typically managed by `PlatformTransactionManager`, such as `DataSourceTransactionManager` or `JpaTransactionManager`; transaction context is bound to the **current thread** via `ThreadLocal`.
- **Reactive transactions** are managed by `ReactiveTransactionManager`, such as `R2dbcTransactionManager`; transaction context resides in the **subscription's Reactor Context** and follows an appropriate reactive pipeline.

Both can use `@TransactionalEventListener` since **Spring Framework 6.1**, yet they **do not share the same transaction context**. Consequently, when mixing JDBC/JPA with R2DBC/Project Reactor or calling imperative event-publishing APIs from a reactive flow, it is easy to misjudge when events are processed, miss `AFTER_COMMIT` listeners, or perform operations outside the intended transaction.

The scope of this lesson is **boundaries and limitations when combining both models in Spring Application Events**, not benchmarking speed or recommending rewriting an entire application as reactive.

## 1. Where do the two transaction models differ?

| Aspect | Imperative | Reactive |
| --- | --- | --- |
| Transaction manager | `PlatformTransactionManager` | `ReactiveTransactionManager` |
| Where transaction context is held | `ThreadLocal` of the executing thread | `Reactor Context` attached to the subscription |
| Common data APIs | JDBC, JPA/Hibernate | R2DBC |
| Unit of work | Method executes directly, returns a normal result | `Mono`/`Flux` describing work that runs only on subscription |
| Explicit transaction tool | `TransactionTemplate` | `TransactionalOperator` |
| Typical transactional event publication | `ApplicationEventPublisher.publishEvent(...)` directly inside transaction | `TransactionalEventPublisher.publishEvent(...)` inside the reactive pipeline |
| How listeners recognize the source transaction | Spring sees the thread-bound transaction when publishing | Event must carry `TransactionContext` as **`source`** for Spring to bind to the reactive transaction |

For imperative:

```text
Current thread
  +-- TransactionTemplate / @Transactional (JDBC, JPA)
        +-- transaction context in ThreadLocal
        +-- publishEvent(OrderCreated)
              +-- registers AFTER_COMMIT callback
        +-- COMMIT
              +-- AFTER_COMMIT listener invoked
```

For reactive:

```text
Mono/Flux subscription
  +-- TransactionalOperator / @Transactional (R2DBC)
        +-- transaction context in Reactor Context
        +-- TransactionalEventPublisher.publishEvent(OrderCreated)
              +-- puts TransactionContext into event.source
              +-- registers AFTER_COMMIT callback for reactive transaction
        +-- COMMIT when publisher completes successfully
              +-- AFTER_COMMIT listener invoked
```

**There is no automatic conversion** that turns a `ThreadLocal`-bound JDBC transaction into an R2DBC transaction in `Reactor Context`, or vice versa. Placing a JDBC call inside `Mono.fromCallable(...)` also does not make JDBC participate in an R2DBC transaction.

## 2. Why does `@TransactionalEventListener` behave differently in reactive?

By Spring's contract, `@TransactionalEventListener` supports these phases:

- `BEFORE_COMMIT`: before the source transaction commits.
- `AFTER_COMMIT`: after the source transaction commits successfully; **default**.
- `AFTER_ROLLBACK`: after the source rolls back.
- `AFTER_COMPLETION`: after the source finishes, regardless of outcome.

If no suitable transaction exists, the listener **does not run by default** (`fallbackExecution = false`).

### 2.1. Imperative path: can publish directly

In a JDBC/JPA service running on a thread holding an imperative transaction, calling:

```java
eventPublisher.publishEvent(new OrderCreated(42L));
```

allows Spring to recognize the thread-bound transaction at the time the event is published. A `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` listener will be bound to that transaction's commit.

### 2.2. Reactive path: the event must carry transaction context properly

Inside a reactive transaction, simply calling:

```java
Mono.fromRunnable(() ->
    eventPublisher.publishEvent(new OrderCreated(42L))
);
```

is **not** a reliable way to bind a transactional listener to a reactive transaction. When the publish callback executes, the reactive transaction sits in `Reactor Context`, whereas the imperative lookup mechanism via `ThreadLocal` cannot see it. Regular payload events published by `ApplicationEventPublisher` also do not automatically carry the required `TransactionContext`.

Spring provides `org.springframework.transaction.reactive.TransactionalEventPublisher`:

```java
TransactionalEventPublisher publisher =
        new TransactionalEventPublisher(applicationEventPublisher);

Mono<Void> publish = publisher.publishEvent(new OrderCreated(42L));
```

Here `publishEvent(...)` returns **`Mono<Void>`**, responsible for retrieving the running pipeline's `TransactionContext` and using that context as the event's **`source`**. To actually publish and bind the callback to the transaction, you must **compose this Mono into the same reactive chain** and subscribe from a flow holding a valid transaction.

Core conceptual example:

```java
Mono<Void> businessFlow =
        repository.save(order)
                  .then(transactionalEventPublisher.publishEvent(
                          new OrderCreated(order.id())));

return businessFlow.as(transactionalOperator::transactional);
```

This is an **illustrative integration snippet**, assuming `repository.save(...)` returns an appropriate reactive publisher, `transactionalOperator` uses the right `ReactiveTransactionManager`, and `order` is a business object. `then(...)` ensures the publish step follows the save step **in the same pipeline**. The transaction opens only when the returned chain is subscribed to.

### 2.3. Do not confuse `event.source` with the business payload

In the reactive publishing approach, `TransactionContext` is used as the **`source`** of `ApplicationEvent`, without needing to replace the entire business payload with a transaction object. With `TransactionalEventPublisher.publishEvent(Object)`, Spring can wrap the payload into a `PayloadApplicationEvent` carrying the transaction context as source, so listener methods continue receiving the business type:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderCreated event) {
    // Invoked when the source reactive transaction commits successfully.
}
```

Do not manually create an `ApplicationEvent` with `source = this` or an arbitrary source and assume Spring knows which reactive transaction it belongs to. If you need to build an event with its source yourself, the `publishEvent(Function<TransactionContext, ApplicationEvent>)` API lets you attach the proper context.

## 3. Runnable Java 17+ example: same reactive transaction, two different ways of publishing events

The following example uses **Spring Framework 6.2**, H2 via R2DBC, and `TransactionalOperator`. We create three reactive transactions:

1. **T1:** saves order `42` and publishes an event via `TransactionalEventPublisher` — the `AFTER_COMMIT` listener runs.
2. **T2:** saves order `43` yet calls `ApplicationEventPublisher` directly from `Mono.fromRunnable` — does not pass transaction context in the event, so the transaction-bound listener **skips** that event by default.
3. **T3:** saves order `44` and publishes properly, yet throws an error before commit — the transaction rolls back, so the `AFTER_COMMIT` listener **does not run**.

The example uses an in-memory database to compare committed data; this is not production deployment code.

Project structure:

```text
mixed-transaction-events/
├── pom.xml
└── src/main/java/MixedTransactionEventsDemo.java
```

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>mixed-transaction-events</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-r2dbc</artifactId>
            <version>6.2.9</version>
        </dependency>
        <dependency>
            <groupId>io.r2dbc</groupId>
            <artifactId>r2dbc-h2</artifactId>
            <version>1.0.0.RELEASE</version>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.7.9</version>
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
                <configuration>
                    <mainClass>MixedTransactionEventsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Create `src/main/java/MixedTransactionEventsDemo.java`:

```java
import io.r2dbc.spi.ConnectionFactories;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.r2dbc.connection.R2dbcTransactionManager;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.reactive.TransactionalEventPublisher;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

public class MixedTransactionEventsDemo {

    public record OrderCreated(long id) {}

    public static class OrderListeners {
        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void afterCommit(OrderCreated event) {
            System.out.println("AFTER_COMMIT listener: " + event.id());
        }
    }

    private static long count(DatabaseClient db, long orderId) {
        Long result = db.sql("SELECT COUNT(*) FROM orders WHERE id = :id")
                .bind("id", orderId)
                .map((row, meta) -> row.get(0, Long.class))
                .one()
                .block();

        return result == null ? 0L : result;
    }

    public static void main(String[] args) {
        var connectionFactory = ConnectionFactories.get(
                "r2dbc:h2:mem:///mixed?options=DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"
        );

        var db = DatabaseClient.create(connectionFactory);
        db.sql("CREATE TABLE orders (id BIGINT PRIMARY KEY)")
                .fetch().rowsUpdated().block();

        var txManager = new R2dbcTransactionManager(connectionFactory);
        var txOperator = TransactionalOperator.create(txManager);

        try (var context = new AnnotationConfigApplicationContext()) {
            context.registerBean(OrderListeners.class);
            context.refresh();

            var reactivePublisher = new TransactionalEventPublisher(context);

            // T1: publish event properly, bound to the R2DBC transaction.
            Mono<Void> t1 =
                    db.sql("INSERT INTO orders (id) VALUES (42)")
                            .fetch().rowsUpdated()
                            .then(reactivePublisher.publishEvent(
                                    new OrderCreated(42)));

            t1.as(txOperator::transactional).block();
            System.out.println("T1 committed rows: " + count(db, 42));

            // T2: call imperative publisher; event does not carry
            // the reactive transaction's TransactionContext.
            Mono<Void> t2 =
                    db.sql("INSERT INTO orders (id) VALUES (43)")
                            .fetch().rowsUpdated()
                            .then(Mono.fromRunnable(() -> {
                                context.publishEvent(new OrderCreated(43));
                                System.out.println("T2 raw publish: 43");
                            }));

            t2.as(txOperator::transactional).block();
            System.out.println("T2 committed rows: " + count(db, 43));

            // T3: registered AFTER_COMMIT, but transaction rolls back.
            Mono<Void> t3 =
                    db.sql("INSERT INTO orders (id) VALUES (44)")
                            .fetch().rowsUpdated()
                            .then(reactivePublisher.publishEvent(
                                    new OrderCreated(44)))
                            .then(Mono.<Void>error(
                                    new IllegalStateException("reject order 44")));

            try {
                t3.as(txOperator::transactional).block();
            } catch (IllegalStateException ex) {
                System.out.println("T3 rolled back: 44");
            }
            System.out.println("T3 committed rows: " + count(db, 44));
        }
    }
}
```

Run in the directory containing `pom.xml` (requires JDK 17+, Maven; on first run Maven needs to download dependencies):

```bash
mvn -q compile exec:java
```

Main lines printed by the application, in order (excluding library logs):

```text
AFTER_COMMIT listener: 42
T1 committed rows: 1
T2 raw publish: 43
T2 committed rows: 1
T3 rolled back: 44
T3 committed rows: 0
```

Explanation:

- In **T1**, `TransactionalEventPublisher` creates an event with `TransactionContext` as source; Spring registers the listener with the R2DBC transaction and invokes it after T1 commits.
- In **T2**, the database write committed, yet `context.publishEvent(...)` created a payload event without carrying the reactive transaction's context. `@TransactionalEventListener` finds no matching transaction from this event, so it does not print `AFTER_COMMIT listener: 43`. This is a **skipped event listener**, not a database transaction rollback.
- In **T3**, publication was done properly, but the transaction rolled back before commit, so the `AFTER_COMMIT` listener does not run. Record `44` does not exist after rollback.

Using `.block()` here **is only inside a command-line program** to wait for each scenario to finish and print ordered results. **Do not copy `.block()` onto non-blocking WebFlux/Netty processing threads**. In real reactive applications, return `Mono`/`Flux` for upper layers to subscribe and complete.

Important note: `@TransactionalEventListener` does not automatically guarantee durable event delivery to a broker, exactly-once accuracy, or automatic retries when a listener fails. It only binds callbacks to the outcome of a transaction that Spring can identify.

## 4. Practical limitations when mixing the two models

### 4.1. `ThreadLocal` and `Reactor Context` do not replace each other

Imperative transactions are bound to the current **thread**. When calling `subscribeOn` or running tasks on another thread, you cannot assume the imperative `ThreadLocal` transaction is present on the new thread.

Conversely, **Reactor Context is not synonymous with ThreadLocal**. Standard Reactor operators can preserve Reactor Context across a valid thread switch within **the same subscription**, yet a regular Java call that only looks up transactions via `ThreadLocal` still cannot see a reactive transaction.

Example:

```java
Mono<Void> flow = reactiveService.saveOrder(order)
        .publishOn(Schedulers.boundedElastic())
        .then(Mono.fromRunnable(() -> {
            // Cannot infer an active JDBC transaction
            // merely because this flow has a reactive transaction.
            jdbcAuditService.writeAudit(order.id());
        }));
```

This is an **illustrative integration snippet**, requiring the application to supply `reactiveService`, `jdbcAuditService`, `order`, and Reactor scheduler imports. Even when JDBC runs on a scheduler meant for blocking I/O, it does not automatically join the preceding R2DBC transaction.

### 4.2. Calling `subscribe()` separately breaks required completion relationships

Common mistake:

```java
public Mono<Void> saveAndPublish(Order order) {
    reactiveRepository.save(order).subscribe(); // Separate subscription.
    return transactionalEventPublisher.publishEvent(
            new OrderCreated(order.id()));
}
```

This is **illustrative bad code**, assuming `reactiveRepository.save(...)` is a reactive publisher. `subscribe()` in the middle makes the save task run independently; the returned chain no longer guarantees saving completes before publishing, and the transaction context is not automatically shared with the new subscription.

The right pattern is to **compose** publishers:

```java
public Mono<Void> saveAndPublish(Order order) {
    return reactiveRepository.save(order)
            .then(transactionalEventPublisher.publishEvent(
                    new OrderCreated(order.id())));
}
```

The method above is an **illustrative integration snippet**. It still must execute inside a real reactive transaction, e.g., via `@Transactional("r2dbcTransactionManager")` on a Spring-proxied method or via `TransactionalOperator`. Composing the chain alone is not enough to create a transaction automatically.

### 4.3. Returning `Mono` from a method bound to a JDBC transaction

Code like the following easily misleads readers:

```java
@Transactional("jdbcTransactionManager")
public Mono<Void> saveLater() {
    return Mono.fromRunnable(() ->
            jdbcTemplate.update("INSERT INTO audit(message) VALUES (?)", "ok"));
}
```

This is **code illustrating a flawed design**, not a standalone program. If `jdbcTransactionManager` is a `PlatformTransactionManager`, the imperative transaction wraps the **method call**, while `Mono.fromRunnable` only runs upon a subsequent subscription. Therefore, the actual JDBC work can execute **after the method's transaction has already closed**. Do not treat a `Mono` return signature as proof that a JDBC transaction will stay open until the publisher completes.

To handle JDBC, let the imperative transaction wrap the actual JDBC call, for example inside a separate Spring service with `@Transactional("jdbcTransactionManager")` and a method returning a regular type. If you need to call that blocking service from reactive code, switch to an appropriate executor/scheduler and accept that it is a **separate transaction boundary**.

### 4.4. `.block()` does not transfer transactions back and forth

Calling `.block()` on a `Mono` can trigger a subscription to wait for the result. It **does not move** `TransactionContext` from a reactive pipeline into a JDBC/JPA `ThreadLocal`, nor does it turn an existing JDBC transaction into a reactive transaction.

Besides losing non-blocking benefits, `.block()` on a thread marked non-blocking by Reactor (common in WebFlux threads) can throw `IllegalStateException`. On other threads, blocking can still exhaust resources and reduce throughput.

If you have no choice but to call a blocking imperative library from a reactive pipeline, isolate that task with an explicitly coordinated adapter such as `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`, and manage the JDBC transaction inside the invoked imperative service itself. **`boundedElastic` only isolates blocking I/O; it does not combine two transactions into one**.

### 4.5. Two transaction managers do not create a single shared transaction

An application may simultaneously have:

```java
@Transactional("jdbcTransactionManager")
public void writeLegacyTable() {
    // JDBC/JPA transaction.
}

@Transactional("r2dbcTransactionManager")
public Mono<Void> writeReactiveTable() {
    // R2DBC transaction.
    return reactiveRepository.save(...).then();
}
```

This is **illustrative skeleton code**; repositories and manager configuration are application components. Each manager has its own connection, commit boundary, and rollback boundary. Calling both methods within the same request **does not guarantee atomicity** across the two data sources.

Possible scenario:

```text
JDBC transaction:  COMMIT succeeded
R2DBC transaction: error -> ROLLBACK

Result: JDBC data persisted, R2DBC data not persisted.
```

If business rules require all changes to share the same outcome, design appropriate transaction boundaries or a coordination protocol with clear commitments. Common patterns across multiple data sources/services include **Transactional Outbox**, idempotent message retries, or **Saga/compensating actions**. `@TransactionalEventListener` alone cannot create atomicity between JDBC and R2DBC.

### 4.6. Listener phases are local to the source transaction

An `AFTER_COMMIT` listener bound to an R2DBC transaction only means the **source R2DBC transaction** committed. It does not certify that another JDBC transaction committed, nor does it guarantee an event reached Kafka/RabbitMQ. Likewise, a JDBC `AFTER_COMMIT` says nothing about the progress of an independent reactive pipeline.

If a listener executes a new database operation after commit, create an **explicit new transaction** in the matching model. During post-commit callbacks, old transaction resources might still be accessible for a while, yet new write operations are not automatically committed again. In an imperative flow, a `@Transactional(propagation = REQUIRES_NEW)` service through a Spring proxy can open a separate transaction; in a reactive flow, use the corresponding reactive operator/manager and keep the publisher within its proper lifecycle.

## 5. Choosing the event-publishing API by which transaction owns the business operation

An application rule:

1. If the operation is managed by **`PlatformTransactionManager`** and work runs inside an imperative method that opened a transaction, use `ApplicationEventPublisher.publishEvent(...)` and `@TransactionalEventListener`.
2. If the operation is managed by **`ReactiveTransactionManager`**, use `TransactionalEventPublisher`, **compose the publish `Mono` into the pipeline itself**, and let the subscription manage the entire transaction.
3. If you are at a **transition boundary** between imperative and reactive, identify which source transaction determines whether the event is valid. Do not rely on schedulers, current threads, or the mere presence of `@Transactional` to guess.
4. If an event must be sent reliably to an external system, write an **outbox record inside the source data's transaction** and let an independent worker deliver and retry it. In-memory events should only act as an auxiliary signal so the worker wakes up sooner.

Additional notes:

- **Do not enable `fallbackExecution = true` just to mask lost transaction context bugs.** That flag allows callbacks to run even without a suitable transaction, which can violate the "handle only after successful commit" requirement.
- **Do not use `@Async` or `@Order` to fix transaction context problems.** They relate to execution and listener ordering, not transferring transaction context from Reactor to `ThreadLocal`.
- **Do not put critical work into a `Mono` and forget the subscription.** An unsubscribed publisher normally does nothing.
- **Do not assume switching threads always loses Reactor Context.** Context is tied to the subscription; the issue is leaving the subscription or accessing it via an API that only knows `ThreadLocal`.
- **Do not treat an HTTP 500 as proof of rollback.** The source transaction may already have committed while the error occurred in a post-commit callback; client retries must be idempotent.

## 6. Testing the intersection points

Test using a **real database or appropriate H2/R2DBC**, with the right transaction manager type. Checking logs from listeners alone is insufficient to conclude a transaction committed.

| Case | What to verify |
| --- | --- |
| Reactive transaction + `TransactionalEventPublisher` + commit | `AFTER_COMMIT` listener runs, R2DBC data exists |
| Reactive transaction + direct imperative publisher + payload lacking `TransactionContext` | Transaction-bound listener does not run by default, even though data may have committed |
| Reactive transaction + proper publish + rollback | `AFTER_COMMIT` listener does not run, data rolled back |
| Unsubscribed reactive transaction | Cannot claim a transaction or event was processed; lazy work typically has not run |
| Publishing event outside transaction with `fallbackExecution = false` | Transaction-bound listener is skipped |
| Calling JDBC from reactive flow | JDBC and R2DBC transactions are tested separately; do not assume atomicity |
| Two managers with diverging commit/rollback outcomes | Observe state of both sources and recovery/outbox logic |

With Reactor, use `StepVerifier` to verify pipeline completion, errors, and cancellation. When checking `AFTER_COMMIT`, ensure the transaction has **truly finished**, then query the database from an independent connection/transaction. Merely receiving an `onNext` value does not prove the transaction committed: a reactive publisher can emit items while the transaction is still open.

Do not write tests relying on `Thread.sleep(...)` to "wait for events" because it introduces nondeterminism; for asynchronous tasks use synchronization utilities or durably stored state. Tests with blocking JDBC called through a scheduler should verify real threads/resources and transactions, not just mocked repository methods.

## 7. Self-assessment questions

**1. Why might `@TransactionalEventListener` not run when calling `applicationEventPublisher.publishEvent(...)` inside a reactive transaction?**

Because the R2DBC transaction resides in `Reactor Context`, whereas regular events do not carry `TransactionContext` as source and there is no matching imperative transaction in `ThreadLocal`. Spring cannot bind the callback to the source transaction.

**2. Is switching from `Mono.fromRunnable(...publishEvent...)` to `TransactionalEventPublisher.publishEvent(...)` enough?**

No. The publish `Mono` must sit inside a **reactive pipeline with an actual transaction**, be subscribed to, and complete. Calling it and discarding the result still publishes nothing.

**3. Does using `publishOn(Schedulers.boundedElastic())` turn an R2DBC transaction into a JDBC transaction?**

No. A scheduler can switch where execution runs, but it creates no new transaction manager and does not convert `Reactor Context` into `ThreadLocal`.

**4. If a JDBC transaction committed while a reactive transaction errored, does `@TransactionalEventListener` roll back both?**

No. Two independent transactions can reach different outcomes. Consistency must be designed via proper transaction boundaries, an outbox, idempotency, or compensating actions.

**5. If `@TransactionalEventListener(AFTER_COMMIT)` runs and fails to send a webhook, does the source transaction roll back?**

No: an error in a post-commit task cannot reverse an already-completed commit decision. Handle webhook delivery errors independently and apply retry/idempotency if required by business logic.

## Official documentation and technical references

- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework 6.2 — Programmatic Transaction Management and `TransactionalOperator`](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html)
- [Spring Framework 6.2 — `@Transactional`, choosing a transaction manager](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)
- [Spring Framework 6.2.9 — Javadoc `TransactionalEventListener`](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Framework 6.2.9 — Javadoc `TransactionalEventPublisher`](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html)
- [R2DBC H2 — README on ConnectionFactory and in-memory database](https://github.com/r2dbc/r2dbc-h2)
