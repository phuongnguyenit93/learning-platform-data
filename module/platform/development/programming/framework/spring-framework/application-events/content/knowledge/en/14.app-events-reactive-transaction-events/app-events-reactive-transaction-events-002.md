# Reactor Context and Transaction Context in Spring Reactive Transaction Events

## 1. Why does this lesson matter?

In imperative Java applications, Spring typically binds transaction state to the execution thread using `ThreadLocal`. However, in reactive applications using Project Reactor, a pipeline can cross multiple threads, suspend, and resume when data is ready. Therefore, **reactive transactions do not rely on ThreadLocal to identify the active transaction**. Spring binds the transaction to the **subscription's Reactor Context**.

That difference directly impacts application events: a `@TransactionalEventListener` can only register phase handling such as `AFTER_COMMIT` or `AFTER_ROLLBACK` for a reactive transaction when it knows the **TransactionContext** of the transaction that published the event. Since Spring Framework 6.1, Spring supports this by **setting `TransactionContext` as the `source` of `ApplicationEvent`**, typically via `TransactionalEventPublisher`.

Lesson objectives:

- Understand `Context`/`ContextView` in Reactor, Spring's `TransactionContext`, and the relationship between them.
- Know how `ReactiveTransactionManager` and `TransactionalOperator` attach transaction state to the subscriber context.
- Distinguish regular event publishing from events whose source contains a transaction context.
- Write and verify `@TransactionalEventListener` for both commit and rollback in R2DBC.
- Understand why switching threads, creating separate subscriptions, using `block()`, or uncontrolled `@Async` can break transaction assumptions.
- Distinguish JVM-internal event scope from durable delivery mechanisms of a message broker.

## 2. Three easily confused concepts

| Concept | Definition | Scope |
|---|---|---|
| `ThreadLocal` | A value bound to a Java thread | Current thread; does not automatically follow logic across thread switches |
| Reactor `Context` / `ContextView` | Key-value data attached to a **subscriber**, propagated through Reactor operators | A subscription chain, depending on `contextWrite` placement and subscribe boundaries |
| Spring `TransactionContext` | An object storing reactive transaction resources and synchronization info managed by Spring | A specific reactive transaction within the Reactor Context |

**Reactor Context is not synonymous with TransactionContext.** Reactor `Context` is a general mechanism: it can hold trace IDs, tenant IDs, security info, or framework-managed keys. Spring `TransactionContext` is specialized data that the transaction infrastructure places into this context stream.

Do not treat `Reactor Context` like a global variable. Another subscription does not share the same context by default, even if both subscriptions run on the same thread.

### Data flows by subscription rather than by thread

An illustrative pipeline:

~~~text
HTTP/WebFlux handler
   |
   | creates Mono/Flux (assembly, not yet executed)
   v
Subscriber subscribes (subscription)
   |
   | Reactor Context holds subscriber keys
   v
TransactionalOperator / reactive @Transactional
   |
   | TransactionContext is attached to the subscription by Spring
   v
DatabaseClient / R2DBC
   |
   | looks up transaction state via Reactor Context
   | uses the connection matching the transaction
   v
Commit / Rollback when the publisher terminates
~~~

Threads may change during execution, while the context of the same subscription is propagated through operators that follow the Reactor contract. This **does not mean** every library, non-Reactor callback, or manually spawned task automatically receives the context.

## 3. How does Reactor Context work?

`reactor.util.context.Context` is a key-value structure with immutable semantics (*immutable API*): `put`/`delete` operations produce a new context. `ContextView` is the read-only interface for retrieving data.

- `contextWrite(...)` creates an effective context for **upstream** operators at subscription time.
- `Mono.deferContextual(...)` or `Flux.deferContextual(...)` reads the context at subscribe time, when there is an actual subscriber.
- Context is propagated through the Reactor chain in the **downstream -> upstream** direction during subscription; the placement of `contextWrite` therefore matters.
- `publishOn(...)` may switch the thread processing signals, while Reactor Context remains the subscriber context; that differs from `ThreadLocal`.
- Each `subscribe()`/`block()` call can create a new subscription. If you detach a publisher from the current transaction chain, you must not assume it inherits the transaction context.

A pure Reactor example that can be placed in a Java 17 class:

~~~java
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

public class ReactorContextExample {
    public static void main(String[] args) {
        String result = Mono.deferContextual(view ->
                Mono.just("trace=" + view.get("traceId")))
            .contextWrite(Context.of("traceId", "REQ-123"))
            .block();

        System.out.println(result);
    }
}
~~~

With the `io.projectreactor:reactor-core` dependency, the output is:

~~~text
trace=REQ-123
~~~

**Explanation:** `deferContextual` retrieves `traceId` when the Mono is subscribed to by `block()`. `contextWrite` supplies data for the upstream segment. Placing `contextWrite` on a different branch does not make every publisher across the entire application see that key.

To see the converse, consider:

~~~java
Mono<String> source = Mono.deferContextual(view ->
        Mono.just(view.getOrDefault("traceId", "missing").toString()));

Mono<String> first = source.contextWrite(Context.of("traceId", "A"));
Mono<String> second = source.contextWrite(Context.of("traceId", "B"));
// first and second are two differently configured publishers.
// When subscribed separately, they receive A and B respectively.
~~~

This snippet is illustrative; use the Reactor classes/imports in a real project. It helps avoid thinking that `Context` is a global variable stored on `source`.

## 4. Spring manages reactive transactions using Reactor Context

In the imperative model:

~~~text
PlatformTransactionManager
    -> ThreadLocal / TransactionSynchronizationManager (imperative)
    -> same thread usually means same transaction
~~~

In the reactive model:

~~~text
ReactiveTransactionManager
    -> Reactor subscriber Context
    -> Spring TransactionContext / TransactionSynchronizationManager (reactive)
    -> operations in the same reactive chain can share the same transaction
~~~

Two different types of transaction managers:

- `PlatformTransactionManager` is used for JDBC/JPA and traditional thread-bound transactions.
- `ReactiveTransactionManager` is used for reactive drivers such as R2DBC, with transaction state in Reactor Context.
- `R2dbcTransactionManager` is an implementation of `ReactiveTransactionManager` for an R2DBC `ConnectionFactory`.
- `TransactionalOperator` provides a *per-publisher* API to declare transaction boundaries. When a subscriber subscribes, Spring starts the transaction, sets the appropriate context, then commits on successful completion or rolls back on error/cancellation per the specific contract.

Configuration example:

~~~java
@Bean
ReactiveTransactionManager reactiveTransactionManager(ConnectionFactory factory) {
    return new R2dbcTransactionManager(factory);
}

@Bean
TransactionalOperator transactionalOperator(
        ReactiveTransactionManager transactionManager) {
    return TransactionalOperator.create(transactionManager);
}
~~~

This is a **configuration snippet**; it requires importing the Spring and R2DBC classes along with a `ConnectionFactory` bean. For the transaction to actually occur, you must **subscribe** to the publisher to which the operator was applied:

~~~java
Mono<Void> operation = repository.save(order)
    .then()
    .as(transactionalOperator::transactional);

// Creating the Mono alone neither executes DB work nor commits.
return operation; // WebFlux will subscribe to process the request.
~~~

The snippet above illustrates with a hypothetical reactive repository having a `save` method. In a real WebFlux application, prefer **returning `Mono`/`Flux` to the framework**; in command-line examples or tests you can use `block()` at the boundary. Do not use `block()` in the middle of logic running on the WebFlux event loop.

### TransactionContextManager.currentContext()

Spring provides `org.springframework.transaction.reactive.TransactionContextManager.currentContext()` to obtain `Mono<TransactionContext>` for the current subscription. This API reads the Spring-managed context, including cases where the transaction is held via a context holder, so it is preferable to guessing the key stored in `ContextView`.

Illustrative example inside a reactive transaction:

~~~java
Mono<Boolean> hasReactiveContext =
    TransactionContextManager.currentContext()
        .map(context -> context != null);
~~~

This is an unsubscribed publisher. When placed inside the same pipeline with a reactive transaction, the result can be `true`; if there is no transaction context, Spring signals a missing-context error instead of implicitly creating a transaction. Having a `TransactionContext` does not mean an *active* transaction exists at every moment; when you need to check a specific status, use the contract of the reactive transaction manager/synchronization manager.

**Do not use** `org.springframework.transaction.support.TransactionSynchronizationManager` (the thread-bound version) to conclude whether a reactive transaction exists. Spring has a similarly named class in package `org.springframework.transaction.reactive` with its own Mono/Context contract.

## 5. Why does @TransactionalEventListener need the transaction context in the event source?

`ApplicationEventPublisher.publishEvent(...)` itself is not a transaction-creating API and does not automatically pass the entire Reactor Context to a synchronous Java callback. A transactional listener needs to know **which transaction** to bind its callback to.

With a regular JDBC transaction, the listener can obtain the transaction state through ThreadLocal while `publishEvent` is executing. In a reactive pipeline, however, the listener might be invoked on any thread and the transaction state belongs to the **subscriber Context**. Therefore, for reactive transactions, Spring requires `TransactionContext` to be in the **`source`** of `ApplicationEvent`.

Conceptual correct flow:

~~~text
Mono/Flux inside reactive transaction T1
       |
       | TransactionalEventPublisher.publishEvent(payload)
       v
TransactionContextManager.currentContext()
       |
       | obtains TransactionContext of T1
       v
PayloadApplicationEvent(source=TransactionContext, payload)
       |
       | delegates to ApplicationEventPublisher.publishEvent
       v
@TransactionalEventListener
       |
       | uses source to register transaction synchronization on T1
       v
T1 COMMIT   ---> AFTER_COMMIT listener invoked
T1 ROLLBACK ---> AFTER_ROLLBACK listener invoked
~~~

If you publish a POJO event directly with `applicationEventPublisher.publishEvent(payload)` from a reactive pipeline without attaching the transaction source, `@TransactionalEventListener` may fail to find the right reactive transaction and not execute as expected. With `fallbackExecution=false` (the default), an event without a matching transaction is skipped by the transactional listener.

Spring Framework 6.1+ provides:

~~~java
import org.springframework.transaction.reactive.TransactionalEventPublisher;

// Typically declared as a bean:
@Bean
TransactionalEventPublisher transactionalEventPublisher(
        ApplicationEventPublisher publisher) {
    return new TransactionalEventPublisher(publisher);
}
~~~

Two main overloads:

| API | When to use |
|---|---|
| `publishEvent(Object payload)` | You have a POJO/record payload; Spring automatically creates a `PayloadApplicationEvent` with `TransactionContext` as source |
| `publishEvent(Function<TransactionContext, ApplicationEvent>)` | You need to instantiate a custom event class extending `ApplicationEvent` and set its source to `TransactionContext` |

Note: `publishEvent(Object payload)` **does not accept an existing `ApplicationEvent`** to arbitrarily replace its source; for a custom `ApplicationEvent`, use the function overload and construct a new event with the provided transaction context.

## 6. Publishing events properly inside a transactional publisher

Payload record example:

~~~java
public record OrderPlaced(long orderId) {}
~~~

Reactive service:

~~~java
public Mono<Void> createOrder(long id) {
    return database.sql("INSERT INTO orders(id) VALUES (:id)")
        .bind("id", id)
        .fetch()
        .rowsUpdated()
        .then(transactionalEvents.publishEvent(new OrderPlaced(id)))
        .as(transactionalOperator::transactional);
}
~~~

This code is an **integration snippet**: it requires a `database` bean of type `DatabaseClient`, `transactionalEvents` of type `TransactionalEventPublisher`, and `transactionalOperator`. Using `then(...)` is crucial: it ensures the event-publishing publisher sits in the **same reactive chain** governed by the transaction operator, after the INSERT statement has completed at the publisher level. The INSERT has not yet committed at the moment the event is published; the `AFTER_COMMIT` listener waits for a successful commit.

Do not call manually:

~~~java
@Transactional // Assuming this is a reactive transaction.
public Mono<Void> incorrect(long id) {
    database.sql("INSERT INTO orders(id) VALUES (:id)")
        .bind("id", id)
        .fetch()
        .rowsUpdated()
        .subscribe(); // Creates a separate subscription, losing the desired boundary.

    return Mono.empty();
}
~~~

This is an **intentionally incorrect example**: an internal subscription via `subscribe()` creates an execution flow detached from the transaction returned by `incorrect`. A similar bug happens when calling `block()` inside a pipeline, using a manually created `CompletableFuture`, or offloading work to a thread pool without propagating the required context. Do not fix it by manually copying the transaction context like a ThreadLocal; structure a single unified publisher and let Spring subscribe.

### Custom ApplicationEvent and source

If the system needs a dedicated `ApplicationEvent` type instead of a payload record:

~~~java
public final class OrderPlacedEvent extends ApplicationEvent {

    private final long orderId;

    public OrderPlacedEvent(Object source, long orderId) {
        super(source);
        this.orderId = orderId;
    }

    public long orderId() {
        return orderId;
    }
}
~~~

Publish using the function overload to preserve the transaction source:

~~~java
return transactionalEvents.publishEvent(
    transactionContext -> new OrderPlacedEvent(transactionContext, orderId)
);
~~~

The snippets above require importing `org.springframework.context.ApplicationEvent` and running **inside a reactive transaction**. Do not replace `transactionContext` with `this`, `null`, or an arbitrary string: a reactive transactional listener requires a source of type `TransactionContext`.

## 7. Complete Java 17 + R2DBC H2 example: listener runs on commit, not on rollback

This example uses Spring Framework **6.2.8**, Reactor, and H2 with R2DBC; no Spring Boot or external database server is needed. The program:

1. Creates the `orders` table in in-memory H2.
2. Enables reactive transactions using `R2dbcTransactionManager` and `TransactionalOperator`.
3. Inserts a row then publishes an event via `TransactionalEventPublisher`.
4. Verifies the `AFTER_COMMIT` listener runs after the transaction succeeds.
5. Attempts to insert a second row and throws an error to roll back; the `AFTER_COMMIT` listener does not run again.
6. Reads the actual row count in the database and prints deterministic results.

Structure:

~~~text
reactive-event-demo/
├── pom.xml
└── src/main/java/demo/ReactiveEventDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>reactive-event-demo</artifactId>
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
            <artifactId>spring-r2dbc</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.7.8</version>
        </dependency>
        <dependency>
            <groupId>io.r2dbc</groupId>
            <artifactId>r2dbc-h2</artifactId>
            <version>1.0.0.RELEASE</version>
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

### src/main/java/demo/ReactiveEventDemo.java

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

import io.r2dbc.spi.ConnectionFactories;
import io.r2dbc.spi.ConnectionFactory;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.r2dbc.connection.R2dbcTransactionManager;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.reactive.TransactionalEventPublisher;
import org.springframework.transaction.reactive.TransactionalOperator;

import reactor.core.publisher.Mono;

public final class ReactiveEventDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            DatabaseClient database = context.getBean(DatabaseClient.class);
            OrderCommands orders = context.getBean(OrderCommands.class);
            CommitListener listener = context.getBean(CommitListener.class);

            database.sql(
                "CREATE TABLE orders (id BIGINT PRIMARY KEY, status VARCHAR(20))"
            ).fetch().rowsUpdated().block();

            orders.saveAndPublish(1L, false).block();
            System.out.println("after success listener calls: "
                    + listener.handledCount());

            try {
                orders.saveAndPublish(2L, true).block();
            } catch (IllegalStateException expected) {
                System.out.println("rollback: " + expected.getMessage());
            }

            Long rows = database.sql("SELECT COUNT(*) AS total FROM orders")
                .map((r, meta) -> ((Number) r.get("total")).longValue())
                .one()
                .block();

            System.out.println("after rollback listener calls: "
                    + listener.handledCount());
            System.out.println("database rows: " + rows);
        }
    }

    public record OrderPlaced(long orderId) {}

    @Configuration
    public static class Config {

        @Bean
        ConnectionFactory connectionFactory() {
            return ConnectionFactories.get(
                "r2dbc:h2:mem:///rxevents?options=DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"
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
                ReactiveTransactionManager transactionManager) {
            return TransactionalOperator.create(transactionManager);
        }

        @Bean
        TransactionalEventPublisher transactionalEventPublisher(
                ApplicationEventPublisher publisher) {
            return new TransactionalEventPublisher(publisher);
        }

        @Bean
        OrderCommands orderCommands(
                DatabaseClient database,
                TransactionalEventPublisher publisher,
                TransactionalOperator operator) {
            return new OrderCommands(database, publisher, operator);
        }

        @Bean
        CommitListener commitListener() {
            return new CommitListener();
        }
    }

    public static final class OrderCommands {

        private final DatabaseClient database;
        private final TransactionalEventPublisher publisher;
        private final TransactionalOperator operator;

        OrderCommands(DatabaseClient database,
                TransactionalEventPublisher publisher,
                TransactionalOperator operator) {
            this.database = database;
            this.publisher = publisher;
            this.operator = operator;
        }

        public Mono<Void> saveAndPublish(long id, boolean fail) {
            Mono<Void> flow = database.sql(
                    "INSERT INTO orders (id, status) VALUES (:id, :status)")
                .bind("id", id)
                .bind("status", "NEW")
                .fetch()
                .rowsUpdated()
                .then(publisher.publishEvent(new OrderPlaced(id)));

            if (fail) {
                flow = flow.then(Mono.error(
                    new IllegalStateException("simulated failure")));
            }

            return operator.transactional(flow);
        }
    }

    public static final class CommitListener {

        private final AtomicInteger handled = new AtomicInteger();

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void afterCommit(OrderPlaced event) {
            handled.incrementAndGet();
            System.out.println("committed event: " + event.orderId());
        }

        int handledCount() {
            return handled.get();
        }
    }
}
~~~

Run inside the `reactive-event-demo` directory using Java 17 and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ReactiveEventDemo
~~~

Output printed by **the program itself** (ignoring auxiliary Maven logs, if any):

~~~text
committed event: 1
after success listener calls: 1
rollback: simulated failure
after rollback listener calls: 1
database rows: 1
~~~

### Analyzing the output

- `AnnotationConfigApplicationContext` registers the listener bean and the reactive transaction components.
- The INSERT into H2 executes when `saveAndPublish(...).block()` subscribes. `TransactionalOperator` starts the transaction and sets up the subscription's context.
- `TransactionalEventPublisher.publishEvent(new OrderPlaced(id))` retrieves TransactionContext within the same chain, creates a `PayloadApplicationEvent` with TransactionContext as source, and forwards it to `ApplicationEventPublisher`.
- `@TransactionalEventListener(AFTER_COMMIT)` registers synchronization with that transaction. Because the listener does not have `@Async`, incrementing the counter and printing the message happen during transaction completion before the Mono successfully emits its final signal.
- The `fail = true` branch publishes the event before returning `Mono.error(...)`, yet the transaction rolls back so the `AFTER_COMMIT` callback does not run.
- H2 uses `DB_CLOSE_DELAY=-1` to keep the in-memory database alive when connections close; the COUNT query confirms only row ID 1 was committed.

The example deliberately uses `TransactionalOperator`, so `@EnableTransactionManagement` is unnecessary. If you replace it with `@Transactional` on a method returning `Mono`, you must configure a reactive transaction manager and invoke it through the Spring proxy.

**Illustrative limitation:** the listener only increments an in-memory counter. In a real application, sending messages or performing I/O in a post-commit callback requires dedicated design for publishers, retries, async execution, and error observability; you must not claim that the callback guarantees durable delivery.

## 8. How does reactive @Transactional differ from imperative @Transactional?

Suppose a method returns `Mono<Void>` and is managed by `ReactiveTransactionManager`:

~~~java
@Transactional
public Mono<Void> createOrder(long id) {
    return database.sql("INSERT INTO orders(id) VALUES (:id)")
        .bind("id", id)
        .fetch()
        .rowsUpdated()
        .then(transactionalEvents.publishEvent(new OrderPlaced(id)));
}
~~~

This is integration code; it must be invoked through the transaction proxy and use `DatabaseClient` and the matching publisher. The Spring transaction interceptor applies the transaction when the reactive publisher is **subscribed** to, not merely when the Java method returns a `Mono`.

Imperative method:

~~~java
@Transactional
public void createOrderImperative(long id) {
    jdbcTemplate.update("INSERT INTO orders(id) VALUES (?)", id);
    applicationEventPublisher.publishEvent(new OrderPlaced(id));
}
~~~

is managed via `PlatformTransactionManager`/ThreadLocal. Both snippets use the same annotation, yet differ in resource types and where transaction context is stored. For an application that uses both JDBC/JPA and R2DBC, you must choose the right transaction manager for each operation and never assume one transaction spans both technologies.

Key distinctions:

| Characteristic | Imperative transaction | Reactive transaction |
|---|---|---|
| Manager | `PlatformTransactionManager` | `ReactiveTransactionManager` |
| Context | Thread-bound state | Reactor subscriber Context |
| Starting boundary | Usually when the proxy invokes the method | When the publisher is subscribed to |
| Thread switching | ThreadLocal does not follow automatically | Context follows the subscription through Reactor operators |
| Data access | JDBC / JPA | R2DBC or reactive APIs with transaction integration |
| Publishing events for transactional listeners | Regular events can use ThreadLocal | Requires a source carrying `TransactionContext` |
| Correct synchronization API reference | `org.springframework.transaction.support` | `org.springframework.transaction.reactive` |

Note that in Spring's transaction abstraction, a `@Transactional` method using a reactive manager typically needs to return a reactive publisher (or a corresponding supported type). A `void` method or one returning a regular object does not automatically become a reactive transaction just because it is called from a reactive controller.

## 9. Transaction phase timing and reactive events

The four main phases of `@TransactionalEventListener`:

| Phase | When the listener is invoked | Meaning |
|---|---|---|
| `BEFORE_COMMIT` | Before commit | Data is not yet guaranteed to be committed |
| `AFTER_COMMIT` | Transaction committed successfully | Suitable for triggering post-commit processing |
| `AFTER_ROLLBACK` | Transaction rolled back | Suitable for reacting to transaction cancellation |
| `AFTER_COMPLETION` | After commit or rollback | Behavior does not distinguish the two outcomes unless checked explicitly |

`AFTER_COMMIT` is the annotation's default value. If there is no matching transaction, the listener does not run by default; enable `fallbackExecution = true` only when you intend to handle the no-transaction case as well. **`fallbackExecution` does not cause `TransactionalEventPublisher` to create a transaction:** that helper still needs a current `TransactionContext` to build the proper event source.

Even after `AFTER_COMMIT`, resources bound to the old transaction may still be accessible when the callback runs; performing I/O or database updates inside the callback does not mean it automatically gets a new transaction. For post-commit operations that require durable writes, open an appropriate new transaction boundary or use an outbox. This applies to both imperative and reactive models, though how a new pipeline/transaction is created differs.

### Should @Async be used with @TransactionalEventListener?

You may aim to offload heavy work to an executor, but you need to distinguish **registering transaction synchronization** (which must occur within the event's transaction context) from **executing work after the transaction finishes**.

Key points to remember:

- Since Spring 6.1, transactional application listeners require the registration step to execute within the original context rather than being arbitrarily dispatched to the multicaster's executor.
- If the post-commit listener body has `@Async`, the work may run on another thread that lacks the publisher's ThreadLocal; do not assume it can access the old transaction.
- With Reactor, a synchronous callback does not automatically become a subscriber with a transaction context just because the event source contains `TransactionContext`.
- If you must run reactive I/O after commit, design an independent subscription with error and state management or a queue/outbox; **do not nest `subscribe()` arbitrarily** inside the business pipeline.

Keep transactional listeners lean, and reserve critical side effects for mechanisms that can be monitored and recovered on failure.

## 10. Common mistakes when moving from ThreadLocal to Reactor Context

### Mistake 1: Relying on Thread.currentThread() to identify a transaction

A reactive publisher can start on thread A and continue on thread B after `publishOn` or when R2DBC emits signals. Thread names or querying imperative ThreadLocals do not prove which reactive transaction is active.

**Correct approach:** keep work within the same reactive chain, and use `TransactionalOperator`/reactive `@Transactional` and Spring's reactive transaction context APIs.

### Mistake 2: Calling publishEvent(Object) directly and expecting AFTER_COMMIT

~~~java
Mono<Void> wrong = database.sql("INSERT INTO orders(id) VALUES (123)")
    .fetch().rowsUpdated()
    .doOnSuccess(ignored -> applicationEventPublisher.publishEvent(
        new OrderPlaced(123)))
    .then()
    .as(transactionalOperator::transactional);
~~~

Even though the publish callback runs inside the pipeline, a regular `ApplicationEventPublisher` does not automatically wrap the source into a `TransactionContext`. For reactive transactions, `@TransactionalEventListener` lacks the required source.

**Correct approach:** use `TransactionalEventPublisher.publishEvent(new OrderPlaced(123))` as a step in the chain instead of calling the regular publisher inside `doOnSuccess`.

### Mistake 3: Calling subscribe() inside a transaction

~~~java
Mono<Void> wrong = database.sql("UPDATE orders SET status='READY'")
    .fetch().rowsUpdated()
    .doOnNext(count -> otherMono.subscribe())
    .then()
    .as(transactionalOperator::transactional);
~~~

`otherMono.subscribe()` creates a separate subscription. It does not inherit the transaction context the way the main chain is governed. If you need execution ordering and a shared transaction, compose publishers with `flatMap`/`then`/`concatMap` before applying the transaction operator.

### Mistake 4: Creating a Mono without subscribing

~~~java
Mono<Void> eventMono = transactionalEvents.publishEvent(new OrderPlaced(1));
// Assembly only; without subscribe, no publication occurs.
~~~

Unlike `ApplicationEventPublisher.publishEvent` which returns `void` and executes directly, `TransactionalEventPublisher.publishEvent` returns `Mono<Void>`. It is a reactive operation that must be subscribed to as part of a chain. In server applications, let the framework subscribe; in tests, use `StepVerifier` or `block()` at a safe boundary.

### Mistake 5: Ignoring rollback, cancellation, and timeout

A reactive transaction can roll back due to an error or subscription cancellation. If an event was registered but the transaction rolls back, the `AFTER_COMMIT` listener does not run. Do not rely on "the publisher was called" to conclude "the event was processed".

### Mistake 6: Abusing Context as a business data store

`Context` is designed for per-subscription metadata, not to replace a database, event payload, or durable delivery mechanism. For a listener to handle work properly, put the necessary business data in the payload (e.g., order ID, version), while `TransactionContext` in the source serves to bind to the transaction.

### Mistake 7: Placing contextWrite in the wrong spot

~~~java
Mono<String> flow = Mono.deferContextual(ctx ->
        Mono.just(ctx.get("traceId").toString()));

Mono<String> correct = flow.contextWrite(Context.of("traceId", "X"));
~~~

This example makes the key visible to `flow`. If `contextWrite` is on a branch that is not the source the listener subscribes to, or added after a subscription has completed, it will not supply data as expected. For Spring transactions, **do not manually insert `TransactionContext` arbitrarily via `contextWrite`**; let the transaction infrastructure manage lifecycle and resources.

## 11. Testing and observing behavior

A good integration test should have at least two branches:

1. **Commit:** inside a reactive transaction, INSERT/update, call `TransactionalEventPublisher`, then complete normally. Verify `@TransactionalEventListener(AFTER_COMMIT)` runs and the database contains the data.
2. **Rollback:** same chain, but emit an error before commit. Verify the `AFTER_COMMIT` listener does not run and the database rolls back the changes.

Use `StepVerifier` to subscribe and verify completion/error in Reactor tests:

~~~java
StepVerifier.create(orderCommands.saveAndPublish(1L, false))
    .verifyComplete();

StepVerifier.create(orderCommands.saveAndPublish(2L, true))
    .expectError(IllegalStateException.class)
    .verify();
~~~

This is an **integration test snippet**; it requires the `io.projectreactor:reactor-test` dependency and JUnit/test data setup. Do not add this snippet into the example's main class because it requires test-scoped dependencies and separate test data.

For proper observability, you can record:

- Application transaction ID or correlation ID (Spring does not provide a durable ID by default).
- Event type, payload ID/version, transaction phase, selected listener.
- Timestamps of INSERT/update, publication, commit/rollback, callback start/end.
- Executor/thread name for diagnostic purposes, but do not use it in place of a transaction identifier.
- Number of published events, successful callbacks, errors, and queue/outbox depth if any.

In multi-subscriber applications, inspect context boundaries across `flatMap`, `publishOn`, `retry`, non-Reactor callbacks, and places that call `subscribe()` directly. In particular, `retry` can trigger a **new subscription** and re-execute database operations; if the event-publishing pipeline and business logic are not idempotent, duplicate side effects can occur.

## 12. Event lifecycle is not durable delivery

`TransactionalEventPublisher` only provides the means to publish an event carrying a reactive transaction context so `@TransactionalEventListener` can register for the right phase. It is **not** a message broker:

| Need | In-JVM event | What to add when strict |
|---|---|---|
| Wait for commit before processing | `@TransactionalEventListener(AFTER_COMMIT)` | Ensure publication is in the same subscription |
| Do not process on rollback | Supported by transaction phase | Test rollback/cancellation |
| Event survives a crash | No default guarantee | Transactional outbox, broker, and recovery |
| Retry when listener fails | Not automatic | Retry policy, DLQ, or job queue |
| Propagate context across services | Not automatic | Explicit headers/payload; tracing propagation |
| System-wide exactly-once | Not provided by default | Idempotency design, deduplication, related transactions |

If post-commit tasks are critical, write an outbox record within the same business transaction, then have a worker read the outbox, send messages, and mark the result. With an R2DBC database, the outbox write needs to be verified in the same reactive transaction; if combining multiple data sources, define atomicity boundaries clearly.

## 13. Review questions

**1. Is Reactor Context the same as TransactionContext?** No. Reactor Context is a per-subscriber key-value mechanism; TransactionContext is specialized transaction state managed by Spring inside it.

**2. Does a reactive transaction automatically follow ThreadLocal?** No. Spring binds reactive transaction state to the Reactor subscriber Context.

**3. Why is TransactionalEventPublisher needed?** Because a transactional listener needs `TransactionContext` in the **event source** to bind to a reactive transaction. This publisher constructs the right event and returns a Mono that composes into the pipeline.

**4. Can `publishEvent(Object payload)` be called with an already-created `ApplicationEvent`?** Not with that overload; if you want to create a custom ApplicationEvent, use the function overload that receives TransactionContext and returns an event with the proper source.

**5. When is the event published?** When the Mono returned by `TransactionalEventPublisher.publishEvent` is subscribed to within the chain; merely calling the method to obtain the Mono does not publish it.

**6. If the transaction rolls back, does the AFTER_COMMIT listener run?** No. Choose `AFTER_ROLLBACK` if you need dedicated handling on rollback.

**7. Does switching threads with publishOn always lose Reactor Context?** No; Reactor Context is bound to the subscription. However, ThreadLocals and manually spawned callbacks outside the chain are not preserved automatically.

**8. Should raw `subscribe()` be used in the middle of a business flow?** Usually no: it detaches the subscription, making transaction boundaries and error handling hard to control.

**9. Should you manually put `TransactionContext` into Reactor Context to simulate a transaction?** No: the transaction manager also manages connections, synchronization, commit/rollback, and cleanup.

**10. After AFTER_COMMIT, is a message guaranteed to have reached the broker?** No. The transaction phase only reflects the local transaction outcome; delivery and retries must be designed separately.

## 14. Core takeaways

**Reactor Context holds per-subscription context. Spring TransactionContext holds reactive transaction state and is managed by the transaction manager via Reactor Context.** When publishing transaction-bound application events, the event must carry TransactionContext in its `source`. The convenient way is to use `TransactionalEventPublisher.publishEvent(...)` and compose the returned Mono into the same pipeline governed by `ReactiveTransactionManager` or `TransactionalOperator`.

Do not use ThreadLocal or thread names to infer reactive transactions; do not let a publisher call `subscribe()` detached from the chain. Test commit, rollback, handling phases, and error handling; use an outbox/broker when durability or cross-process delivery is required.

### Reference materials

- [Spring Framework 6.2 Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework 6.2 Reference — Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework Javadoc — TransactionalEventPublisher](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html)
- [Spring Framework Javadoc — TransactionContextManager](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/reactive/TransactionContextManager.html)
- [Spring Framework Reference — Data Access with R2DBC](https://docs.spring.io/spring-framework/reference/6.2/data-access/r2dbc.html)
- [Project Reactor Reference — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
