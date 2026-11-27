# Consumer<Flux<T>> and Subscription Responsibility

## 1. The Problem: Consumer Receives a Flux but Processes Zero Elements

In **Spring Cloud Function**, `Supplier` produces data, `Function` transforms data, and `Consumer` receives data to perform side effects such as logging, persisting orders, or updating external systems. Functions can be looked up via `FunctionCatalog`, composed, and share the same business logic across HTTP, message brokers, or serverless environments.

In the **Reactive Streams** chapter, a consumer can accept `Flux<T>` instead of just a single `T`:

~~~java
Consumer<Flux<String>> audit = events ->
    events.doOnNext(event -> System.out.println(event));
~~~

This snippet has a bug. `doOnNext` creates **a new publisher** with an added observation hook, yet nobody subscribes to that publisher. Because `Consumer.accept` returns `void`, the newly constructed publisher is simply discarded. With a cold Reactor source, the print statement will never run.

Someone might try to “fix” it like this:

~~~java
Consumer<Flux<String>> audit = events ->
    events.doOnNext(System.out::println).subscribe();
~~~

This second version **actually subscribes to receive data**. However, it opens up new questions: who handles `onError`, who cancels the subscription on application shutdown, who knows when persistence finishes, and at what moment does the message broker acknowledge the message?

**This is the central theme of the lesson:** When choosing `Consumer<Flux<T>>`, you must understand precisely who owns the subscription and the consequences of returning `void`. In many cases, `Function<Flux<T>, Mono<Void>>` expresses the asynchronous contract much better.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish `Consumer<T>` from `Consumer<Flux<T>>` and their `accept` invocation counts.
2. Explain why `subscribe()` is necessary when writing a reactive consumer that returns `void`.
3. Separate **constructing a pipeline**, **subscribing**, **processing `onNext`**, **completing**, and **canceling**.
4. Spot bugs caused by self-subscribing and losing visibility into results or lifecycle.
5. Write consumers with error handling, and recognize when to return `Mono<Void>` instead.
6. Test Reactor behavior and verify responsibility boundaries with Spring Cloud Function adapters.

## 2. Java's Consumer Contract Does Not Change in Reactive Environments

Java defines:

~~~java
@FunctionalInterface
public interface Consumer<T> {
    void accept(T value);
}
~~~

`Consumer` simply states that the caller hands the consumer **one argument**, and `accept` **returns no result**. If the argument is a publisher, `accept` is still just a synchronous Java call receiving **one `Flux<T>`**; it does not automatically become a subscriber.

| Signature | Argument per call | Return value of `accept` | How elements run |
| --- | --- | --- | --- |
| `Consumer<OrderEvent>` | One `OrderEvent` | `void` | Logic in `accept` runs on the passed order |
| `Consumer<Mono<OrderEvent>>` | A publisher emitting 0–1 order | `void` | Requires a subscription to receive the order |
| `Consumer<Flux<OrderEvent>>` | A publisher emitting 0–N orders | `void` | Requires a subscription to receive `onNext` signals |
| `Function<Flux<OrderEvent>, Mono<Void>>` | A publisher emitting 0–N orders | Publisher describing completion/error | Caller can subscribe and observe the outcome |

**`Mono<Void>` emits no `Void` value.** It represents an operation that completes successfully or terminates with an error. That is why a `Function` returning `Mono<Void>` is often well suited for an “asynchronous consumer that needs to signal completion.”

### 2.1. Three Distinct Events

Suppose we have a source:

~~~java
Flux<String> source = Flux.just("A", "B", "C");
~~~

The logical sequence is:

~~~mermaid
sequenceDiagram
    participant Adapter as Caller / adapter
    participant Consumer as Consumer<Flux<T>>
    participant Pipeline as Reactor pipeline
    participant Source as Source Flux

    Adapter->>Consumer: accept(source)
    Consumer->>Pipeline: Build operator chain
    Note over Consumer,Pipeline: No subscribe yet = cold source not processed
    Consumer-->>Adapter: void
    Consumer->>Pipeline: subscribe() if consumer manages it
    Pipeline->>Source: onSubscribe + request(n)
    Source-->>Pipeline: onNext(A), onNext(B), onNext(C)
    Source-->>Pipeline: onComplete
~~~

Notably, `accept` can return before asynchronous data is processed. Without a subscription, a cold source may never execute.

**One `accept(flux)` call does not equate to one execution per `T`.** A framework may pass a long-lived stream to a reactive consumer; callbacks inside the pipeline are what run per element.

## 3. Why Doesn't Spring Automatically Subscribe for Consumer<Flux<T>>?

Spring Cloud Function and Spring Cloud Stream documentation explicitly note that a reactive `Consumer` is a special case: because it returns `void`, the framework **has no reference to a resulting publisher** to subscribe to and track for completion. If you explicitly write `Consumer<Flux<?>>`, the developer must subscribe to the input Flux.

This differs from `Function<Flux<T>, Flux<R>>`:

~~~java
Function<Flux<String>, Flux<String>> normalize =
    input -> input.map(String::trim);
~~~

The caller receives a `Flux<String>` from `apply`, so it can control subscription, demand, cancellation, and `onError` handling. By contrast, with:

~~~java
Consumer<Flux<String>> audit =
    input -> input.doOnNext(System.out::println);
~~~

the caller only knows that `accept` returned `void`. The pipeline constructed by the consumer is not handed back for the framework to manage. There is no automatic contract that “hunts down a publisher inside the lambda.”

### 3.1. Distinguishing “Framework Passes a Flux” from “Framework Subscribes to the Flux”

In an event integration supporting reactive functions, the framework can construct a `Flux<Message<T>>` source and pass it into `Consumer<Flux<Message<T>>>`. The fact that the framework **creates and passes a publisher** does not mean code inside the consumer has **subscribed** to it.

If the consumer only calls `map`, `filter`, or `doOnNext` and discards the return value, those operators normally never run. If the consumer calls `subscribe()`, it becomes the party performing the subscription and from that point on must have a strategy for observability, errors, cancellation, and resources.

Exact invocation details, binders, and acknowledgments depend on the adapter version; never infer from the Java type that the broker will automatically know when side effects have finished.

## 4. From Broken Examples to Correct Examples

### 4.1. Broken: Creating a Publisher Without Subscribing

~~~java
@Bean
Consumer<Flux<String>> silentConsumer() {
    return incoming -> incoming
        .map(String::trim)
        .doOnNext(value -> System.out.println("received " + value));
}
~~~

This code **processes none** of the cold source's values: the return value of `doOnNext` is ignored. Some IDEs may warn “result of method call ignored,” though not every environment catches it.

### 4.2. Subscription-Correct: Handling All Three Signal Types

~~~java
@Bean
Consumer<Flux<String>> loggingConsumer() {
    return incoming -> incoming
        .map(String::trim)
        .subscribe(
            value -> System.out.println("received " + value),
            error -> System.err.println("stream failed: " + error),
            () -> System.out.println("stream completed")
        );
}
~~~

Calling `subscribe(onNext, onError, onComplete)` starts the pipeline. With a finite cold source like `Flux.just(" A ", " B ")`, it emits two values and completes. With a long-lived source, the completion callback may never be invoked if the source never emits `onComplete`.

This example is helpful for understanding the mechanism. In production, `System.out` should be replaced with proper logging/metrics, and a long-lived consumer must also **hold and dispose of the `Disposable`** on shutdown.

### 4.3. Why Must an Error Callback Be Provided?

An overly terse snippet:

~~~java
incoming.subscribe(value -> sendToExternalSystem(value));
~~~

If the pipeline emits `onError` without an error handler, the error may be routed to Reactor's global/drop error hook, making it hard to tie back to business outcomes. Moreover, if `sendToExternalSystem` calls a blocking API here, it can block the emitting thread.

A more responsible version separates pipeline errors from external system errors and decides whether they terminate the subscription or are handled per element.

## 5. Why Does .subscribe() Inside Consumer Still Have Limitations?

Inside `Consumer<Flux<T>>`, self-subscribing may be required so data is actually consumed, yet **it does not turn `void` into an asynchronous completion signal**. You can picture it like this:

~~~mermaid
flowchart LR
    IN["Input Flux<Order>"] --> CON["Consumer.accept(flux)"]
    CON -->|self-subscribes| TASK["Async processing"]
    CON -->|returns void| CALLER["Framework / caller"]
    TASK -->|completes or errors later| LOG["Internal handler"]
    CALLER -.->|no result Mono| TASK
~~~

Scenarios to consider:

- **Caller returns early:** `accept` can return immediately while internal I/O operations are still in flight.
- **Errors do not travel through the return value:** `onError` is handled by an internal callback/subscription; the caller has no `Mono` to observe.
- **Canceling the subscription:** without saving the `Disposable` or an equivalent handle, it is hard to cancel cleanly when a binding closes or the application shuts down.
- **Retries and at-least-once:** if the source is re-subscribed, data may be re-emitted; side effects require idempotency.
- **Ack/offset/transaction:** never assume the binder waits to acknowledge a message until asynchronous work inside a custom `subscribe()` finishes.

Also, do not subscribe twice just to both log and write to a database:

~~~java
Consumer<Flux<String>> wrong = flux -> {
    flux.subscribe(value -> System.out.println(value));
    flux.subscribe(value -> externalWrite(value));
};
~~~

With a cold source, two subscriptions can **read the source twice**. With a hot source, the two subscribers may receive different elements depending on timing. Chain operations inside **one pipeline**, explicitly choosing ordering and error policies.

## 6. The Preferred Approach: Function<Flux<T>, Mono<Void>>

Spring Cloud Stream documentation recommends in most cases using:

~~~java
Function<Flux<T>, Mono<Void>>
~~~

and ending the pipeline with `then()`. This preserves an output describing **completion or failure**, giving the framework/caller a publisher to manage the subscription under the adapter contract.

Example processing orders with a reactive repository. Suppose we have a record and an interface:

~~~java
public record OrderEvent(String orderId, long amountCents) {}

public interface OrderAuditRepository {
    // Write succeeds: onComplete; fails: onError.
    Mono<Void> append(OrderEvent event);
}
~~~

Function configuration:

~~~java
package demo.functions;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Configuration
public class OrderAuditFunctions {

    public record OrderEvent(String orderId, long amountCents) {}

    public interface OrderAuditRepository {
        Mono<Void> append(OrderEvent event);
    }

    @Bean
    public Function<Flux<OrderEvent>, Mono<Void>> auditOrders(
            OrderAuditRepository repository) {

        return incoming -> incoming
            .concatMap(repository::append)
            .then();
    }
}
~~~

Here:

1. `auditOrders.apply(incoming)` **returns `Mono<Void>`**, which is not yet proof that data writes have finished.
2. When the caller/adapter subscribes to the result, `concatMap` invokes `repository.append` for elements and awaits each operation's publisher in order.
3. `then()` ignores all `onNext` signals in the pipeline, emitting `onComplete` only if the entire upstream completes normally; errors propagate via `onError`.
4. If the input source is a non-terminating `Flux`, `Mono<Void>` will also **not complete successfully** while the stream remains active. Write tasks still execute as the source emits data.

**Key point:** Returning `Mono<Void>` improves observability only when the caller/adapter **actually subscribes to and manages the returned publisher**. Never promise that merely changing the signature causes a binder to provide per-message acknowledgment automatically. Always run integration tests in your active Spring Cloud Stream environment.

### 6.1. Direct Comparison of Both Approaches

| Criterion | Self-subscribing `Consumer<Flux<T>>` | `Function<Flux<T>, Mono<Void>>` |
| --- | --- | --- |
| Return type | `void` | `Mono<Void>` |
| Who subscribes to the processing pipeline? | Consumer code must do it explicitly | Caller/adapter can subscribe to the result |
| Tracking completion/error | Callback or internal mechanism inside consumer | Via `onComplete` / `onError` signals of returned publisher |
| Canceling the pipeline | Consumer must retain/manage the subscription | Caller/adapter can cancel its subscription to the publisher |
| Composition suitability | Limited because it ends in `void` | Exposes a result publisher for reactive contracts |
| With infinite streams | Subscription usually lives long-term | `Mono<Void>` usually has no end-of-stream `onComplete` |
| Automatic broker delivery guarantee | No | No |

`Function<Flux<T>, Mono<Void>>` is not universally superior in every adapter. Its distinction is that it **explicitly expresses an asynchronous task that can complete or fail**.

### 6.2. Why Not Write map(repository::append)?

This is a frequent mistake when a repository operation returns `Mono<Void>`:

~~~java
// Wrong intent: creates Flux<Mono<Void>>,
// without ensuring the inner Monos are subscribed to.
Flux<Mono<Void>> nested = incoming.map(repository::append);
~~~

`map` only constructs the inner publisher and emits it as a value; it does not subscribe to each `Mono`. Use:

~~~java
Mono<Void> completed = incoming
    .concatMap(repository::append)
    .then();
~~~

or when concurrent operations are allowed, consider:

~~~java
Mono<Void> completed = incoming
    .flatMap(repository::append, 8)
    .then();
~~~

`flatMap(..., 8)` caps concurrency at eight simultaneous inner publishers and **does not guarantee completion order**. When order persistence sequence matters, `concatMap` is usually easier to reason about.

## 7. When Consumer<Flux<T>> Is Mandatory: Managing Disposable

Some adapters or designs strictly require a true `Consumer<Flux<T>>`. In that case, do not just call `subscribe()` and discard the handle. Reactor returns a `Disposable` representing the subscription, which can be used to cancel it.

Simple example with **one active stream at a time**:

~~~java
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Consumer;

import reactor.core.Disposable;
import reactor.core.publisher.Flux;

public final class ControlledLoggingConsumer
        implements Consumer<Flux<String>>, AutoCloseable {

    private final AtomicReference<Disposable> current =
        new AtomicReference<>();

    @Override
    public void accept(Flux<String> source) {
        Disposable subscription = source.subscribe(
            value -> System.out.println("received: " + value),
            error -> System.err.println("failed: " + error),
            () -> System.out.println("completed")
        );

        Disposable previous = current.getAndSet(subscription);
        if (previous != null) {
            previous.dispose();
        }
    }

    @Override
    public void close() {
        Disposable active = current.getAndSet(null);
        if (active != null) {
            active.dispose();
        }
    }
}
~~~

In this pattern, each time `accept` is called, the previous subscription is canceled. **This is a single-subscription policy**, not a general management pattern for consumers receiving multiple independent sources. If an adapter can supply multiple concurrent `Flux` streams, you need a mechanism to track multiple `Disposable` handles, bound source counts, and synchronize lifecycles properly.

Another point: the code above implements `AutoCloseable`, yet **Spring automatically invokes lifecycle methods only under Spring-managed bean contracts**. If you instantiate `new ControlledLoggingConsumer()` manually and discard the reference, nothing calls `close()`. When registering a bean, you can write:

~~~java
@Bean
ControlledLoggingConsumer controlledLoggingConsumer() {
    return new ControlledLoggingConsumer();
}
~~~

With a bean implementing `AutoCloseable`, verify Spring's destroy-method/lifecycle behavior in your application setup; you can also declare it explicitly:

~~~java
@Bean(destroyMethod = "close")
ControlledLoggingConsumer controlledLoggingConsumer() {
    return new ControlledLoggingConsumer();
}
~~~

This is **an alternative** to the bean declaration above—do not declare both at once. In applications with delivery constraints, you also need to decide how to let in-flight tasks finish before canceling, rather than abruptly calling `dispose()`.

### 7.1. Limitations of Disposable

- `dispose()` requests subscription cancellation; whether an external I/O operation cancels immediately depends on the client and its cancellation support.
- `dispose()` does not automatically roll back committed transactions or unsend already-dispatched messages.
- Cancellation does not mean success; distinguish `CANCEL`, `ON_COMPLETE`, and `ON_ERROR`.
- A cold stream that finishes right before assignment to `current` may still be stored as a completed handle. Under rapid, complex invocations, manage handle lists and cleanup carefully.

You can use `doFinally(signal -> ...)` to record how termination happened; do not confuse `doOnComplete` with cancellation, since cancellation does not emit normal `onComplete`.

## 8. Error Handling Per Element vs. for the Entire Subscription

In Reactive Streams, `onError` is a **terminal signal**. If an asynchronous write operation fails and is not recovered, the entire active pipeline can terminate. Where you place error handling determines whether subsequent elements get a chance to be processed.

Suppose `repository.append(order)` returns `Mono<Void>`. If you want to **attempt each order independently** and business policy permits skipping per-order errors, place `onErrorResume` inside:

~~~java
Function<Flux<OrderEvent>, Mono<Void>> keepProcessing = incoming ->
    incoming
        .concatMap(order ->
            repository.append(order)
                .onErrorResume(error -> {
                    logger.error("Cannot persist order {}", order.orderId(), error);
                    return Mono.empty();
                })
        )
        .then();
~~~

This **does not** guarantee every order is saved successfully. It only ensures each operation's error is handled before escaping outward. You must have alerting or a retry/dead-letter queue if business rules forbid dropping events.

Conversely:

~~~java
Mono<Void> stoppedOnFirstError = incoming
    .concatMap(repository::append)
    .then();
~~~

When `append` fails, `Mono<Void>` emits `onError` and upstream may be canceled. This suits a fail-fast strategy; however, on a continuous source, it can halt processing of subsequent messages unless the adapter has a recovery mechanism.

### 8.1. An Outermost onErrorResume Does Not Resume the Old Source

~~~java
Mono<Void> maskedError = incoming
    .concatMap(repository::append)
    .then()
    .onErrorResume(error -> Mono.empty());
~~~

This **converts an error into completion**; it is not a way to “skip one failed element and continue processing subsequent elements” on the already-terminated subscription. Place error handling at the scope required by business rules.

### 8.2. Retries Can Re-Process Data

~~~java
Mono<Void> retried = incoming
    .concatMap(repository::append)
    .then()
    .retry(2);
~~~

`retry` re-subscribes to upstream on failure. If a cold publisher re-emits earlier elements, orders saved before the error may be written again. Only retry side effects if you have idempotency, event keys, transactions, or checkpoints in place. With hot sources, a new subscription does not necessarily replay missed elements.

## 9. Backpressure, subscribe(), and Blocking Operations

A subscriber needs to communicate how many elements downstream can accept. When using convenience overloads of `Flux.subscribe(...)`, the default subscriber typically requests data with **unbounded demand**. That does not mean infinite data exists at once, but a fast source can push too much work.

If a consumer does:

~~~java
Consumer<Flux<OrderEvent>> naive = source ->
    source.subscribe(order -> blockingRepository.save(order));
~~~

then `blockingRepository.save` can run directly on the emitting thread and block it. Especially on an event loop, this is a dangerous design.

### 9.1. Integrating Blocking APIs in a Controlled Way

If you cannot replace the repository yet, wrap the blocking API in `Mono.fromRunnable` and isolate it onto the bounded elastic scheduler:

~~~java
Function<Flux<OrderEvent>, Mono<Void>> storeBlocking =
    incoming -> incoming
        .concatMap(order ->
            Mono.fromRunnable(
                    () -> blockingRepository.save(order)
                )
                .subscribeOn(
                    reactor.core.scheduler.Schedulers.boundedElastic()
                )
        )
        .then();
~~~

`blockingRepository` is a hypothetical dependency, and `save` is a blocking method returning `void`. This approach only **moves blocking work** onto an appropriate scheduler; it does not turn it into non-blocking I/O. You still need timeouts, connection pool bounds, and concurrency limits.

### 9.2. Using BaseSubscriber When Explicit Demand Control Is Needed

For a pipeline with **very fast synchronous processing**, you can illustrate requesting one element at a time:

~~~java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;

BaseSubscriber<String> subscriber = new BaseSubscriber<>() {
    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        request(1);
    }

    @Override
    protected void hookOnNext(String value) {
        System.out.println("received " + value);
        request(1);
    }

    @Override
    protected void hookOnError(Throwable throwable) {
        System.err.println("stream failed: " + throwable);
    }
};

Flux.just("A", "B", "C").subscribe(subscriber);
~~~

This example clarifies Reactive Streams `request(n)`. However, if each element requires **asynchronous** I/O, calling `request(1)` immediately inside `hookOnNext` **does not wait for the write operation to finish**. In that situation, compose `concatMap`/`flatMap` with the I/O operation's publisher, specifying concurrency and error policies explicitly.

Reactor's internal backpressure also does not automatically slow down a broker or external system; the binder and connector must support matching flow control.

## 10. Consumer with Finite vs. Long-Lived Flux Sources

| Characteristic | Finite Flux | Long-lived Flux |
| --- | --- | --- |
| Examples | `Flux.just(a,b,c)` | `Flux.interval(...)`, event streams |
| Normal `onComplete`? | Yes | Usually not until the source closes |
| Self-subscribing `Consumer<Flux<T>>` | Receives elements and completion callback | Subscription continues until error/cancellation |
| `Function<Flux<T>,Mono<Void>>` | `then()` completes when source and inner tasks finish | Can run indefinitely while `Mono<Void>` has not emitted `onComplete` |
| Application shutdown | Subscription may already be finished | Must actively cancel/close resources |
| Testing | `StepVerifier.verifyComplete()` | Bounded tests with `take(n)` or cancellation |

It is wrong to think “every time a message arrives, the reactive consumer is called again.” In many stream-oriented integrations, a consumer can receive **a single long-lived `Flux<T>`**; values arrive via `onNext` inside that subscription. With an HTTP adapter or direct Java caller, there may be a new invocation per request. Measure and verify in integration tests rather than guessing from the signature.

## 11. Consumer<Message<T>> and Consumer<Flux<Message<T>>>

For event processing, the payload alone may be insufficient: you may need correlation IDs, routing keys, event IDs, or message headers. In that case, use Spring Messaging's `Message<T>`.

### 11.1. Imperative Consumer Accepting One Message at a Time

~~~java
@Bean
Consumer<Message<String>> auditOneMessage() {
    return message -> {
        String eventId = (String) message
            .getHeaders()
            .get("eventId");

        System.out.println(
            "received eventId=" + eventId
                + ", payload=" + message.getPayload()
        );
    };
}
~~~

An adapter can invoke this consumer per message with its corresponding headers. Type conversion rules, retries, and acknowledgments are decided by the adapter/binder.

### 11.2. Reactive Consumer Accepting the Message Stream

~~~java
@Bean
Consumer<Flux<Message<String>>> auditMessageStream() {
    return messages -> messages.subscribe(
        message -> {
            Object eventId = message.getHeaders().get("eventId");
            System.out.println(
                eventId + ": " + message.getPayload()
            );
        },
        error -> System.err.println("stream failed: " + error)
    );
}
~~~

Here headers are read **per `Message<String>`**, not as a single shared header for the entire `Flux`. The input stream can contain messages with many different correlation IDs.

**Warning:** If headers carry a binder-provided acknowledgment object, manually acknowledging inside a subscription must follow the exact binder documentation and active delivery mode. Never assume that finishing `onNext` makes committing safe, especially when the core work is asynchronous.

## 12. FunctionCatalog, Composition, and Reactive Consumer

Spring Cloud Function can chain compatible function beans into a pipeline. Example of a reactive filtering function and an imperative consumer:

~~~java
@Bean
Function<Flux<String>, Flux<String>> trimStream() {
    return source -> source.map(String::trim);
}

@Bean
Consumer<String> printOne() {
    return System.out::println;
}
~~~

A composition can be selected by name, for example:

~~~properties
spring.cloud.function.definition=trimStream|printOne
~~~

However, **composing a reactive function with an imperative consumer has a limitation** highlighted in Spring Cloud Stream documentation: the composition ends in a reactive `Consumer`. Because the final result is `void`, the framework has no resulting publisher to subscribe to; without appropriate subscription handling, the pipeline may not run as expected.

Therefore, do not assume every type-compatible composition automatically has a valid subscription lifecycle.

### 12.1. Options to Handle This

- **When processing each message independently:** consider keeping both steps imperative—`Function<T,R>` followed by `Consumer<R>`—so the adapter invokes them per message.
- **When processing the whole stream:** consider making the final reactive step a function returning a publisher, such as `Function<Flux<T>, Mono<Void>>`, and letting the caller/adapter subscribe to the result under a supported contract.
- **When a reactive Consumer is genuinely required:** implement subscription, errors, and lifecycle explicitly following your adapter's guidance.

A publisher-returning version can look like:

~~~java
@Bean
Function<Flux<String>, Mono<Void>> printStream() {
    return source -> source
        .doOnNext(System.out::println)
        .then();
}
~~~

`doOnNext` in this example is a **small synchronous side effect** for illustration. If you need to write to a database or send asynchronous HTTP requests, use `concatMap`/`flatMap` to bring the inner task publisher into the pipeline and propagate errors properly.

## 13. HTTP, Brokers, and Serverless: Which Responsibilities Change?

Spring Cloud Function separates Java logic from protocols, yet **subscription and completion contracts** still depend on the adapter.

| Environment | What must be clarified |
| --- | --- |
| Direct Java call | Caller invokes `accept` with a publisher, receiving no result to know completion; unit tests must manage signals explicitly |
| `FunctionCatalog` | Catalog looks up/wraps functions; it does not turn `Consumer<Flux<T>>` into an observable publisher by name alone |
| Spring Cloud Stream binder | How `Flux` is supplied, subscription, retries/acks, partitions, and shutdown; a reactive Consumer must self-subscribe when declared explicitly |
| HTTP adapter | Request may complete right after `accept` returns `void`; must verify whether and when async I/O actually finishes |
| Serverless adapter | Invocations have timeouts; do not assume a fire-and-forget subscription keeps running after the invocation ends |

For critical tasks such as payments, invoicing, or writing to an outbox, avoid picking `Consumer<Flux<T>>` solely for concise syntax. You need a mechanism for the caller/binder to know when acknowledgment is safe, plus handling for mid-flight shutdowns.

### 13.1. Subscription Is Not Acknowledgment

**A successful subscribe** only indicates that the pipeline was registered. It does not prove:

- The message was written to the database.
- The outcome was durably committed.
- The broker received an acknowledgment.
- An event cannot be processed again.
- A subscription will not be canceled mid-flight.

Those guarantees come from transaction design, idempotency, offset/acknowledgment strategies, and concrete binder contracts.

## 14. Testing: Is There a Subscription or Just a Pipeline?

### 14.1. Unit Test Catching a Consumer That Forgot to Subscribe

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;

class ReactiveConsumerTest {

    @Test
    void aPipelineWithoutSubscriptionDoesNotConsumeColdFlux() {
        AtomicInteger processed = new AtomicInteger();

        Consumer<Flux<Integer>> wrong = source -> {
            source.doOnNext(value -> processed.incrementAndGet());
        };

        wrong.accept(Flux.just(1, 2, 3));

        assertEquals(0, processed.get());
    }

    @Test
    void explicitSubscriptionConsumesColdFlux() {
        AtomicInteger processed = new AtomicInteger();

        Consumer<Flux<Integer>> correct = source ->
            source.subscribe(
                value -> processed.incrementAndGet(),
                error -> { throw new AssertionError(error); }
            );

        correct.accept(Flux.just(1, 2, 3));

        // Flux.just emits synchronously in this simple case.
        assertEquals(3, processed.get());
    }
}
~~~

The second test works for the synchronous `Flux.just` source. With asynchronous HTTP/databases or `Flux.interval`, **do not assert immediately after `accept` expecting work to be done**. Wait for an explicit signal, use test synchronization with a finite timeout, or test a function that returns a publisher.

### 14.2. Testing a Function Returning Mono<Void> with StepVerifier

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveFunctionCompletionTest {

    @Test
    void completionMeansAllItemsWereProcessed() {
        AtomicInteger saved = new AtomicInteger();

        Function<Flux<Integer>, Mono<Void>> process = numbers ->
            numbers
                .concatMap(number ->
                    Mono.fromRunnable(saved::incrementAndGet)
                )
                .then();

        Mono<Void> completion = process.apply(
            Flux.just(10, 20, 30)
        );

        // Not subscribed yet: no side effects yet.
        assertEquals(0, saved.get());

        StepVerifier.create(completion)
            .verifyComplete();

        assertEquals(3, saved.get());
    }

    @Test
    void anErrorIsObservable() {
        Function<Flux<Integer>, Mono<Void>> process = numbers ->
            numbers
                .concatMap(number -> number == 2
                    ? Mono.<Void>error(
                        new IllegalStateException("invalid item")
                      )
                    : Mono.<Void>empty()
                )
                .then();

        StepVerifier.create(process.apply(Flux.just(1, 2, 3)))
            .expectErrorMessage("invalid item")
            .verify();
    }
}
~~~

`StepVerifier` verifies both completion and error signals. That is the benefit of returning a publisher instead of `void`.

### 14.3. What Should Integration Tests Verify?

When exposing a consumer through Spring Cloud Stream or another adapter, verify in practice:

1. `spring.cloud.function.definition` selects the right bean.
2. The bean receives the expected payloads/headers per contract.
3. The reactive consumer actually holds a subscription and processes multiple consecutive messages.
4. Repository/API errors are detected and handled according to the intended policy.
5. Shutdown/rebalance stops the subscription or exits cleanly.
6. If ordering is required, `flatMap`/`concatMap` maintains the expected constraint.
7. Whether retries or restarts can duplicate messages and whether idempotency protects against them.
8. At what exact point ack/offset/transaction occurs relative to successful persistence.

Reactor unit tests **cannot replace** testing actual interactions with the binder and broker.

## 15. Common Pitfalls and Remedies

| Symptom | Possible cause | Remedy |
| --- | --- | --- |
| Consumer is called but no data logs appear | Only calling `map`/`doOnNext` without subscribing | If `Consumer<Flux<T>>` is required, subscribe explicitly; or return a publisher from `Function` |
| Function returns `Mono<Void>` but writes nothing | Caller did not subscribe to the returned publisher | Check the adapter/caller contract and subscription |
| One error stops the entire event stream | Unhandled `onError` in a long-lived pipeline | Scope per-element recovery or fail and restart cleanly |
| Error occurred but caller thinks it succeeded | `Consumer.accept` returned `void` before async work finished | Use a publisher-returning function when completion must be observed |
| Duplicate processing after retry | New subscription replays a cold source | Use idempotency, checkpoints, and appropriate retry policies |
| Slow tasks stall the source | Blocking I/O inside `subscribe(onNext)` | Use a reactive repository or isolate blocking work and limit concurrency |
| Out-of-order results | Using parallel `flatMap` | Use `concatMap` or `flatMapSequential` as appropriate |
| Same element processed multiple times | Subscribing multiple times to a cold publisher | Build a single pipeline and manage one subscription at the right scope |
| Sources keep running on app shutdown | `Disposable` not retained/disposed | Manage lifecycle and cancellation via bean/container |
| Composed consumer does not run | Composition ends with a `void`-returning reactive Consumer | Choose a composition with a resulting publisher or configure the consumer properly |
| Broker gets messages but DB has no writes | Confusing subscription time with side-effect completion time | Verify binder ack/transaction behavior with integration tests |
| Tests with `Flux.just` PASS but runtime fails | Synchronous tests miss cancellation, I/O, and transport behavior | Add tests with asynchronous sources and a real broker |

## 16. Choosing a Signature by Responsibility

~~~mermaid
flowchart TD
    START["Need to process input data"] --> Q1{"Process each T independently?"}
    Q1 -->|Yes| SINGLE["Consumer<T> / Function<T,R>"]
    Q1 -->|No, process a Flux| Q2{"Does caller need to know when\nprocessing completes or fails?"}
    Q2 -->|Yes| FUNCTION["Function<Flux<T>,Mono<Void>>"]
    Q2 -->|No, adapter mandates\nConsumer<Flux<T>>| CONSUMER["Consumer<Flux<T>>"]
    CONSUMER --> SUB["Explicitly call subscribe()\n+ onError + lifecycle"]
    FUNCTION --> DELEGATE["Return publisher;\ncaller/adapter subscribes"]
    SINGLE --> VERIFY["Verify delivery,\nretry, ack, and idempotency"]
    SUB --> VERIFY
    DELEGATE --> VERIFY
~~~

To choose accurately, answer five questions:

- **Who calls `accept` or `apply`?** Once per message, or once to provide a long-lived publisher?
- **Who subscribes?** Does the framework have a returned publisher to manage, or must the consumer subscribe itself?
- **Who receives `onError` and `onComplete`?** Should an error stop the whole pipeline or only one inner task?
- **Who cancels the source?** How must shutdown, rebalance, timeouts, and network disconnects be handled?
- **When is a message considered processed?** After subscribing, after the task finishes, or after the transaction/ack succeeds?

A maintainable design must answer these clearly before connecting to a broker or external system.

## 17. Self-Assessment Questions

1. Why will a `Consumer<Flux<String>>` that calls `flux.map(...)` without subscribing fail to process a cold source?
2. Why does `Consumer<Flux<T>>` leave the framework with no resulting publisher reference to subscribe to automatically?
3. What is the difference between a `Consumer<T>` invoked by an adapter per message and a `Consumer<Flux<T>>` receiving a long-lived stream?
4. If a consumer calls `subscribe()` itself and `accept` returns `void`, does the caller know whether the database write succeeded?
5. How does `Function<Flux<T>, Mono<Void>>` propagate completion and error signals? Does it automatically guarantee timely broker acks?
6. Why can `map(repository::save)` produce a `Flux<Mono<Void>>` without saving any data? Which operators should you use instead?
7. Will a subscription that encounters `onError` continue receiving subsequent elements in the same subscription?
8. Why should you retain the `Disposable` if a consumer receives a long-lived `Flux`?
9. If the same cold source is subscribed to twice, how many times can the data write occur?
10. When combining a reactive `Function` with an imperative `Consumer` in a composition, what limitation must you check?
11. Why does the convenience `subscribe(onNext)` overload not replace a backpressure and error-handling strategy?
12. Why does `StepVerifier.verifyComplete()` verify something different from proving that a broker acknowledged a message?

## 18. References

- [Spring Cloud Function — Programming model, Consumer](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Stream — Producing and Consuming Messages, Consumer (Reactive)](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/test/release/reference/)

Invocation/subscription mechanics, acknowledgments, and lifecycles depend on the versions of Spring Cloud Function, Spring Cloud Stream, and the binder in use. Official documentation is the authoritative reference for each real stack; pure Reactor unit tests are not proof of production adapter behavior.

**Key takeaway:** `Consumer<Flux<T>>` **does not automatically run Reactor operators** just because it receives a `Flux`. Because `accept` returns `void`, if you write a reactive consumer explicitly, you must **subscribe** proactively and manage errors, cancellation, and in-flight tasks. When the caller or adapter needs to observe completion, consider `Function<Flux<T>, Mono<Void>>` with `then()` so termination and error signals are carried by the returned publisher. In either case, reliable event processing still depends on retries, idempotency, acknowledgments, and adapter lifecycle management.
