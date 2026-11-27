# Completion, Cancellation, and Resource Cleanup

## 1. Why Does Lifecycle Matter in Spring Cloud Function?

A reactive function does more than transform data. It also owns or uses lifecycle-bound resources: HTTP connections, data cursors, transaction sessions, event subscriptions, timers, files, and caches. Without knowing **when a publisher finishes** and **who is responsible for stopping it**, an application can leak resources or mistakenly assume an operation succeeded.

In **Spring Cloud Function**, logic is packaged into `Supplier`, `Function`, and `Consumer`. `FunctionCatalog` supports lookup and composition; adapters can expose the same function over HTTP, events via Spring Cloud Stream, or serverless environments. When a function returns `Mono<T>` or `Flux<T>`, lifecycle questions become critical:

- Who calls `get()`, `apply()`, or `accept()`?
- Who **subscribes** to the returned publisher?
- When does the source emit `onComplete` or `onError`?
- When a client disconnects or the application shuts down, who calls `cancel()`?
- Are connections, sessions, and resources opened **per subscription** or shared application-wide?
- Does canceling a subscription actually abort an in-flight network request or running transaction?

Consider a heartbeat source:

~~~java
Supplier<Flux<Long>> heartbeats =
    () -> Flux.interval(Duration.ofSeconds(1));
~~~

This publisher can emit continuously without **ever emitting `onComplete`**. If the adapter or application code fails to cancel the subscription when no longer needed, the stream can keep timers and related work alive.

Conversely, a finite source:

~~~java
Supplier<Flux<String>> exportOnce =
    () -> Flux.just("ORD-101", "ORD-102");
~~~

emits two elements and then `onComplete` during a normal subscription. **Completing the publisher does not mean the Spring Boot application stops automatically**, nor does it guarantee emitted messages were acknowledged or durably saved by a broker.

This lesson in the **Reactive Streams** chapter focuses on three distinct outcomes—**normal completion, error termination, and cancellation**—along with Reactor tools for safe resource cleanup.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish `onComplete`, `onError`, and `cancel` under the Reactive Streams contract.
2. Know when to use `doOnComplete`, `doOnError`, `doOnCancel`, `doOnTerminate`, and `doFinally`.
3. Manage subscriptions manually with `Disposable` and shut down long-lived streams on application close.
4. Tie resource lifecycles to subscriptions using `Flux.using` and `Flux.usingWhen`.
5. Distinguish **synchronous cleanup** from **asynchronous cleanup** that must be awaited.
6. Handle timeouts, retries, blocking tasks that cannot cancel immediately, and unconfirmed transactions.
7. Understand lifecycle boundaries when combining `FunctionCatalog`, HTTP, brokers, and serverless.
8. Write `StepVerifier` tests for completion, errors, cancellation, and closing resources.

## 2. Lifecycle Contract of a Publisher

Reactive Streams defines the fundamental signal flow:

~~~mermaid
flowchart TD
    S["Subscriber subscribes"] --> O["onSubscribe(Subscription)"]
    O --> N["request(n) and onNext(T)"]
    N --> Q{"Does stream continue?"}
    Q -->|Data available| N
    Q -->|Normal completion| C["onComplete"]
    Q -->|Error occurred| E["onError"]
    O -->|No more demand| X["cancel"]
    N -->|Downstream cancels| X
~~~

**`onComplete` and `onError` are the two terminal signals a publisher emits to a subscriber.** They are mutually exclusive in a compliant subscription. After a terminal signal, the publisher must not emit further `onNext` signals to that subscriber.

**`cancel()` differs from both.** It is an action the subscriber invokes on `Subscription` to signal it no longer wants data. It is neither an `onComplete` emitted by the publisher nor an `onError`. Normally downstream **receives no extra terminal callback** merely for canceling itself.

| Outcome | Initiator | What the subscriber sees | Meaning |
| --- | --- | --- | --- |
| `onComplete` | Publisher | Completion callback | Source finished normally in this subscription |
| `onError(e)` | Publisher | Error callback | Source terminated abnormally with an exception |
| `cancel()` | Subscriber or downstream operator | Does not receive `onComplete`/`onError` just from canceling | No longer wants signals; upstream should stop work as supported |

All three can lead to **cleanup**, yet **none automatically guarantees business success**.

### 2.1. Three Lifecycle Scopes to Keep Separate

1. **Bean/function lifecycle:** Spring manages `Supplier`, `Function`, and `Consumer` beans and their dependencies from startup until context shutdown.
2. **Subscription lifecycle:** each subscription to a publisher can create a distinct execution run. A cold source may replay the same data on another subscription.
3. **External resource lifecycle:** connections, transactions, files, or broker sessions may be opened upon subscription, yet when they actually close or commit depends on the API in use.

A bean living for days does not mean a subscription must live for days; conversely, a long-lived subscription may remain active until application shutdown. Cleanup must match **the exact owning scope**.

## 3. Normal Completion with onComplete

A finite `Flux` typically emits `onNext` one or more times and then `onComplete`:

~~~java
Flux<String> orders = Flux.just("A", "B", "C");

orders.subscribe(
    order -> System.out.println("received " + order),
    error -> System.err.println("failed: " + error),
    () -> System.out.println("completed")
);
~~~

With this synchronous source, the subscriber sees A, B, C and then the `completed` callback. An empty source also completes normally:

~~~java
Flux<String> nothingToSend = Flux.empty();
// No onNext; emits onComplete.
~~~

`Mono<Void>` typically expresses **completion or error only, with no payload**:

~~~java
Function<Flux<OrderEvent>, Mono<Void>> persist = events ->
    events.concatMap(repository::append).then();
~~~

`repository.append` is a hypothetical API returning `Mono<Void>`. When the caller subscribes to the resulting publisher, `then()` emits `onComplete` only after the finite upstream and inner tasks succeed **according to each inner publisher's contract**.

If upstream is infinite, `then()` likewise may never complete normally while the stream remains active.

### 3.1. Completion Does Not Mean “Committed Across All Systems”

Suppose a publisher emits `onComplete` right after **enqueuing** a job without waiting for database commit. The subscriber sees completion while the actual transaction is still running. Reactor signals reflect only the contract of the source and composed publishers; they cannot upgrade the guarantees of external drivers or brokers.

Therefore:

- For database writes, check whether the publisher completes **after** commit or merely after enqueueing.
- For brokers, distinguish publish requests, broker acknowledgments, and consumer acknowledgments.
- For HTTP, distinguish completing the body/response from durable downstream processing.
- When exactly-once or at-least-once semantics are required, design transactions, checkpoints, and idempotency explicitly.

### 3.2. Why Doesn't the Completion Callback Run After cancel?

~~~java
Flux<Long> source = Flux.interval(Duration.ofSeconds(1));

Disposable handle = source.subscribe(
    tick -> System.out.println(tick),
    error -> System.err.println(error),
    () -> System.out.println("completed")
);

handle.dispose();
~~~

If the subscription had not emitted a terminal signal before being canceled, the `completed` callback **is not invoked just because `dispose()` ran**. To observe cancellation as well, place `doFinally` in the right spot.

## 4. Error Termination with onError

A publisher can terminate with an error:

~~~java
Flux<String> failing = Flux.concat(
    Flux.just("A", "B"),
    Flux.error(new IllegalStateException("source unavailable"))
);
~~~

A normal subscriber receives A, B, and then `onError`. No `onComplete` follows.

~~~java
failing.subscribe(
    value -> System.out.println(value),
    error -> System.err.println("failed: " + error.getMessage()),
    () -> System.out.println("completed")
);
~~~

Exceptions thrown **inside operator callbacks** such as `map` or `flatMap` are also converted into `onError` per Reactor semantics.

### 4.1. doOnError Is Observation, Not Recovery

~~~java
Flux<String> observed = failing
    .doOnError(error -> logger.error("Failure", error));
~~~

`doOnError` attaches an error-observation side effect while letting the error pass through. To replace a failed publisher with a fallback, use a recovery operator:

~~~java
Flux<String> fallback = failing
    .onErrorResume(error -> Flux.just("FALLBACK"));
~~~

With a source that already emitted A and B, fallback causes downstream to receive A, B, FALLBACK, and then complete. **It does not resume the old publisher from the next element** after the error; the old publisher has already terminated.

### 4.2. Per-Element Error Handling

If you want to continue processing other orders when an API call fails and business rules permit:

~~~java
Function<Flux<OrderEvent>, Flux<Decision>> check = orders ->
    orders.concatMap(order ->
        riskClient.check(order)
            .onErrorResume(error ->
                Mono.just(Decision.unavailable(order.orderId()))
            )
    );
~~~

`OrderEvent`, `Decision`, and `riskClient` are illustrative APIs/DTOs. `onErrorResume` sits **inside** each task, so a failure in `riskClient.check` is turned into an explicit result before `concatMap` proceeds to the next element.

Whether you choose fail-fast or recovery, any opened resources must still be closed; that is why `using`/`usingWhen` are essential for exclusively owned resources.

## 5. Cancellation: cancel Is Neither Success Nor Failure

A user closes a browser tab, a request times out, the application shuts down, downstream only needs the first few elements, or a subscriber stops wanting a feed. All of these can lead to cancellation.

### 5.1. Direct Cancellation with Disposable

~~~java
import reactor.core.Disposable;

Disposable subscription = Flux.interval(Duration.ofSeconds(1))
    .subscribe(
        tick -> System.out.println("tick=" + tick),
        error -> System.err.println(error)
    );

// When you want to stop receiving:
subscription.dispose();
~~~

Reactor's `subscribe(...)` returns a `Disposable` representing the handle to stop the subscription. `dispose()` requests cancellation. In a normal pipeline, this propagates a cancel request upstream and releases resources **if sources and operators support it properly**.

Never infer that:

- An external HTTP request is guaranteed to abort immediately.
- A running JDBC query halts instantaneously.
- An already-committed transaction rolls back.
- A message already sent to a broker is recalled.
- Downstream receives `onComplete` just because you canceled.

### 5.2. take(n) Causes Cancel Upstream, Yet Completes Downstream

~~~java
Flux<Long> upstream = Flux.interval(Duration.ofMillis(100))
    .doFinally(signal -> System.out.println("upstream: " + signal));

Flux<Long> firstThree = upstream.take(3)
    .doFinally(signal -> System.out.println("downstream: " + signal));
~~~

When subscribing to `firstThree` and receiving three ticks:

- `take(3)` **cancels** the subscription to the `interval` source because no further ticks are needed.
- `firstThree` emits `onComplete` to its subscriber.
- The `doFinally` hook **upstream** of `take` observes `CANCEL`.
- The hook **downstream** of `take` observes `ON_COMPLETE`.

These two outcomes do not contradict each other: **operator placement determines which lifecycle scope is observed**.

~~~mermaid
flowchart LR
    INT["Flux.interval"] --> U["doFinally: upstream"]
    U --> TAKE["take(3)"]
    TAKE --> D["doFinally: downstream"]
    D --> SUB["Subscriber"]
    TAKE -.->|"cancel upstream after 3 ticks"| U
    TAKE -->|"onComplete"| SUB
~~~

### 5.3. Timeouts Can Also Cancel Upstream

~~~java
Mono<Decision> bounded = riskClient.check(order)
    .timeout(Duration.ofSeconds(2));
~~~

If the source fails to deliver the expected signal within the deadline, `timeout` cancels the source subscription and emits a timeout error downstream. **Timeout error at the output** and **cancellation at the input** are two views of the same operator boundary.

For blocking operations that do not support cancellation, external work may continue running after downstream gets a timeout. Configure timeouts **on the HTTP client/JDBC driver** alongside a side-effect reconciliation policy.

### 5.4. Common Cancellation Scenarios

| Scenario | Where cancel originates | Consequences to handle |
| --- | --- | --- |
| `take(n)`, `next()` | Downstream operator | Upstream does not need to emit more |
| HTTP client disconnect | Web adapter if it propagates cancellation | Stop streaming, close per-request resources |
| `timeout` | Time-limiting operator | Upstream is canceled; downstream may receive a timeout error |
| App shutdown / binding stop | Adapter or lifecycle management code | Close long-lived streams, release connections |
| Retry/resubscribe | Operators and source per recovery policy | May open new resources/subscriptions and replay side effects |
| User clicks stop feed | Caller holding `Disposable` | Cancel the current subscription |

These scenarios also depend on the connector, framework version, and data source. Verify with a real adapter when cancellation has business impact.

## 6. Choosing the Right Hook to Observe Terminal Signals

Reactor offers several hooks with different scopes. Their names look similar yet are not interchangeable.

| Hook | Normal completion | Error | Cancellation | Purpose |
| --- | --- | --- | --- | --- |
| `doOnComplete(Runnable)` (Flux) | Yes | No | No | Observe successful completion |
| `doOnError(Consumer)` | No | Yes | No | Log/record error metrics |
| `doOnTerminate(Runnable)` | Yes | Yes | **No** | Observe both terminal signals |
| `doAfterTerminate(Runnable)` | Yes | Yes | **No** | Side effect after terminal signal propagation |
| `doOnCancel(Runnable)` | No | No | Yes | Observe cancel requests |
| `doFinally(Consumer<SignalType>)` | Yes | Yes | **Yes** | General metric cleanup / termination tracking |

`doOnComplete` applies only to `Flux`; for `Mono`, use equivalents like `doOnSuccess` (note the callback can receive `null` when `Mono` completes empty), `doOnError`, or `doFinally`. When you need to cover **all** outcomes, `doFinally` is the convenient observation tool.

### 6.1. Observing and Recording Metrics with doFinally

~~~java
Flux<OrderEvent> observed = source
    .doOnSubscribe(subscription -> metrics.streamStarted())
    .doOnError(error -> logger.error("Stream failed", error))
    .doFinally(signal -> {
        metrics.streamStopped(signal.name());

        if (signal == reactor.core.publisher.SignalType.CANCEL) {
            metrics.streamCancelled();
        }
    });
~~~

`doFinally` receives a `SignalType` such as `ON_COMPLETE`, `ON_ERROR`, or `CANCEL`. The hook runs **after the terminal signal has been forwarded downstream**, so an assertion or metric check running *immediately after* `verifyComplete()` can occasionally execute before the corresponding `doFinally` hook.

Never treat `doFinally` as proof that a transaction durably committed. It is a publisher lifecycle hook, normally suitable for lightweight synchronous cleanup and metrics.

### 6.2. Do Not Use doOnTerminate to Handle Cancel

~~~java
source
    .doOnTerminate(() -> logger.info("terminated"))
    .subscribe();
~~~

If the subscriber cancels before the source emits `onComplete` or `onError`, `doOnTerminate` may not run. When resources must close on cancellation too, use `using`, `usingWhen`, or a resource owner that cleans up across all three branches.

### 6.3. Why Can doFinally Order Surprise You?

~~~java
Flux<String> stream = Flux.just("A")
    .doFinally(a -> logger.info("first: {}", a))
    .doFinally(b -> logger.info("second: {}", b));
~~~

When `doFinally` hooks are chained, they can execute in **reverse declaration order** as the terminal signal travels through the pipeline. Never put order-sensitive commit logic into a chain of hooks; use resource operators or transaction APIs that define order explicitly.

### 6.4. doOnDiscard Targets a Different Case

When operators like `filter`, `take`, `buffer`, or prefetching drop objects that need cleanup, `doOnDiscard` can help release *discarded elements* in operators that support the discard hook:

~~~java
Flux<ReferenceCountedBuffer> buffers = source
    .filter(ReferenceCountedBuffer::isRelevant)
    .doOnDiscard(
        ReferenceCountedBuffer.class,
        ReferenceCountedBuffer::release
    );
~~~

This is a conceptual example: `ReferenceCountedBuffer` is a type with `release()` and `isRelevant()`. **`doOnDiscard` is not a hook that runs for every element or every operator**, nor does it replace closing an owned connection/session. Read each operator's discard-support documentation and guard against double releases.

## 7. Binding Synchronous Resources to Subscriptions with Flux.using

When a publisher is backed by a resource such as a file, cursor, or handle, the safe equivalent of `try-with-resources` for lazy subscriptions is `Flux.using`.

### 7.1. Self-Contained Example with AutoCloseable

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

import reactor.core.publisher.Flux;

public class UsingExample {

    static final class OrderCursor implements AutoCloseable {
        private final AtomicBoolean closed;

        OrderCursor(AtomicBoolean closed) {
            this.closed = closed;
        }

        Flux<String> read() {
            return Flux.fromIterable(List.of("ORD-101", "ORD-102"));
        }

        @Override
        public void close() {
            closed.set(true);
        }
    }

    static Flux<String> readOrders(AtomicBoolean closed) {
        return Flux.using(
            () -> new OrderCursor(closed),
            OrderCursor::read
        );
    }
}
~~~

A single subscription to `readOrders(closed)`:

1. Invokes the supplier to create a **new `OrderCursor`**.
2. Obtains a publisher from the resource via `OrderCursor::read`.
3. Subscribes and consumes the source.
4. Closes the resource when the source finishes or the subscription is canceled per the `using` contract.

Calling `readOrders(...)` does not open the resource immediately: with `Flux.using`, the resource supplier runs **upon subscription**.

### 7.2. Errors or Cancellation Must Still Close

If `OrderCursor.read()` returns a publisher that emits `onError`, `using` still performs cleanup. If downstream takes only the first element and cancels, that subscription's resource is still released.

**Distinguishing eager and non-eager:** the `using` overload with an `eager` flag controls whether cleanup runs before or after the terminal signal is forwarded downstream. An exception during cleanup can affect the terminal signal depending on this choice. When cleanup exceptions have business significance, check the exact contract of the overload in use and test `close()` failure scenarios.

### 7.3. Never Open an AutoCloseable Outside Flux Before Passing to using

~~~java
// Dubious: opens the resource before any subscription exists.
OrderCursor cursor = new OrderCursor(closed);

Flux<String> stream = Flux.using(
    () -> cursor,
    OrderCursor::read
);
~~~

Here multiple subscriptions **share a single instance that was already closed** after the first run, leading to errors or races. If a resource is scoped per subscription, the supplier must **create/acquire a fresh resource per subscription**.

When a resource is shared application-wide, such as an HTTP connection pool, do not close the pool on each subscription; let the bean/container lifecycle close it.

### 7.4. using Is Synchronous Cleanup and Does Not Await Async Cleanup

`AutoCloseable.close()` is synchronous. If an API returns a `Mono<Void>` publisher to close a connection, never do this:

~~~java
// Wrong intent: closeAsync() returns a Mono with no subscription.
.doFinally(signal -> connection.closeAsync());
~~~

Nothing subscribes to the `Mono<Void>` returned by `closeAsync()`. Thus, cleanup may **never run**. To have Reactor manage and await an asynchronous cleanup step, use `usingWhen`.

## 8. Asynchronous Cleanup with usingWhen

A reactive connection/session can open, read, commit, rollback, and close entirely through publishers. Reactor provides `Flux.usingWhen` and `Mono.usingWhen` to bind those steps to a resource scope.

### 8.1. Hypothetical API of a Reactive Session

~~~java
interface ReactiveOrderSession {
    Flux<OrderEvent> readPending();

    Mono<Void> commitAndClose();
    Mono<Void> rollbackAndClose(Throwable cause);
    Mono<Void> cancelAndClose();
}

interface ReactiveSessionFactory {
    Mono<ReactiveOrderSession> open();
}
~~~

Here each method completes once its corresponding operation finishes under the client's contract. These are illustrative interfaces, not built-in APIs of Spring Cloud Function or a specific driver.

### 8.2. usingWhen with Three Distinct Cleanup Paths

~~~java
Flux<OrderEvent> pending = Flux.usingWhen(
    sessionFactory.open(),

    // Resource used to construct the source publisher:
    session -> session.readPending(),

    // Source completes normally:
    session -> session.commitAndClose(),

    // Source emits an error:
    (session, error) -> session.rollbackAndClose(error),

    // Subscriber cancels:
    session -> session.cancelAndClose()
);
~~~

The arguments represent:

1. `resourceSupplier`: publisher supplying a resource for the subscription.
2. `resourceClosure`: constructs the publisher using that resource.
3. `asyncComplete`: cleanup when the source ends normally.
4. `asyncError`: cleanup when the source fails.
5. `asyncCancel`: cleanup when canceled.

~~~mermaid
flowchart TD
    ACQ["Acquire resource (Mono<Resource>)"] --> USE["Publisher uses resource"]
    USE --> END{"How did it end?"}
    END -->|onComplete| COMMIT["asyncComplete: commit/close"]
    END -->|onError| ROLLBACK["asyncError: rollback/close"]
    END -->|cancel| CANCEL["asyncCancel: cancel/close"]
    COMMIT --> NEXT["Terminal to downstream"]
    ROLLBACK --> ERROR["Error to downstream"]
    CANCEL --> STOP["No automatic completion emitted"]
~~~

**Difference from `doFinally`:** `usingWhen` **subscribes to and awaits the cleanup publisher** on termination branches per operator semantics, rather than running a side-effect callback and discarding any returned publisher. On completion/error branches, the terminal signal may be delayed until cleanup finishes.

### 8.3. Watch Out for Items Emitted Before Cleanup

With `Flux.usingWhen`, `onNext` elements may already have reached downstream **before** final cleanup runs. If the commit step fails, the subscriber may already have seen some items even though the transaction ultimately failed.

Therefore, never use `Flux.usingWhen` as proof that “every emitted item was definitely committed.” If downstream must **only see results after commit**, you may need a **finite batch** that emits results only after the transaction succeeds, or a suitable transactional API.

### 8.4. What If Cleanup Itself Fails?

If asynchronous cleanup emits an error, the observed terminal signal may be replaced by the cleanup error; a cleanup failure may suppress or attach the original error per the Reactor overload's semantics. The critical rule is **never silently swallow cleanup failures**.

On cancellation, the subscriber is no longer listening, so cleanup errors cannot simply be delivered to the canceled subscriber. Maintain logging, metrics, and separate monitoring/reconciliation mechanisms.

If a resource only needs one uniform close path across all branches, the three-argument overload `Flux.usingWhen(resourcePublisher, resourceClosure, asyncCleanup)` is shorter; when commit/rollback/cancel differ, the five-argument overload is clearer.

### 8.5. Keep All Operations Needing the Resource Inside the Closure

Do not acquire a resource and then use it in operators after the resource operator has already finished:

~~~java
// Error-prone pattern: the resource may already be closed before dependent work runs.
// Flux.usingWhen(...).flatMap(event -> session.fetchMore(event))
~~~

Instead, the entire pipeline needing the same session must live inside `resourceClosure` or within the corresponding transaction scope:

~~~java
Flux<Decision> decisions = Flux.usingWhen(
    sessionFactory.open(),
    session -> session.readPending()
        .concatMap(event -> decisionService.decide(session, event)),
    ReactiveOrderSession::commitAndClose,
    (session, error) -> session.rollbackAndClose(error),
    ReactiveOrderSession::cancelAndClose
);
~~~

`decisionService.decide(session, event)` is a hypothetical API returning `Mono<Decision>`. Keeping it inside the closure prevents the resource from closing just because the source-reading operator finished while later work still needs the session.

## 9. Who Owns the Resource? Do Not Blindly Close in doFinally

Determine **where a resource is opened, how long it lives, and who is responsible for closing it**.

| Resource | Typical scope | Management approach to consider |
| --- | --- | --- |
| Dedicated file/cursor per read | One subscription | `Flux.using`, `try-with-resources` inside an offloaded blocking unit |
| Dedicated reactive connection/session | One subscription or transaction | `usingWhen` / driver transaction API |
| Shared HTTP client and connection pool | Whole application | Managed by bean/container, closed on shutdown |
| `Flux.interval` timer | One subscription | Cancel upstream when unneeded; adapter manages handle |
| Dedicated client WebSocket connection | One session/request | Cleanup on client disconnect and on error |
| Long-lived subscription created by consumer | Bean/binding lifecycle | Retain `Disposable` and cancel on shutdown |
| Message broker consumer | Binder/container lifecycle | Close binding via framework, never close the whole broker per message |
| Broker transaction/offset | Per batch/message per config | Commit/ack via binder, not solely via terminal hooks |

### 9.1. “Closing Too Early” Is Also a Bug

Example of a function using a shared HTTP client for lookups:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<Decision>> checkOrders(
        ReactiveRiskClient client) {
    return events -> events.flatMap(client::check, 8);
}
~~~

`client` is a Spring-managed dependency. Never add:

~~~java
// Wrong if this client is shared across the whole application:
events.doFinally(signal -> client.close());
~~~

Every ending subscription would close the shared client, breaking other requests. Close shared clients/pools **at application shutdown** according to the bean contract.

### 9.2. “Closing Too Late” Is Also a Bug

If a source opens a separate file per subscription yet only cleans up on context shutdown, thousands of completed subscriptions can leave thousands of unclosed file handles behind. Per-subscription resources must be cleaned up per subscription rather than waiting for JVM shutdown.

## 10. Managing Long-Lived Subscriptions in Consumer<Flux<T>>

`Consumer<Flux<T>>` is a special case in Spring Cloud Function: `accept` returns `void`, so the framework receives no resulting publisher to subscribe to. With an explicit reactive consumer, the consumer itself typically has to subscribe to the input and manage the subscription handle.

### 10.1. Example of a Consumer Keeping Only One Active Stream

~~~java
package demo.lifecycle;

import java.util.function.Consumer;

import reactor.core.Disposable;
import reactor.core.Disposables;
import reactor.core.publisher.Flux;

public final class LiveAuditConsumer
        implements Consumer<Flux<String>>, Disposable {

    private final Disposable.Swap current = Disposables.swap();

    @Override
    public void accept(Flux<String> source) {
        Disposable next = source.subscribe(
            event -> System.out.println("audit " + event),
            error -> System.err.println("audit failed " + error),
            () -> System.out.println("audit completed")
        );

        // Policy: the new subscription replaces the old subscription.
        current.update(next);
    }

    @Override
    public void dispose() {
        current.dispose();
    }

    @Override
    public boolean isDisposed() {
        return current.isDisposed();
    }
}
~~~

To have Spring invoke cleanup when the context closes:

~~~java
@Configuration
class AuditConsumerConfiguration {

    @Bean(destroyMethod = "dispose")
    LiveAuditConsumer liveAuditConsumer() {
        return new LiveAuditConsumer();
    }
}
~~~

`Disposable.Swap` atomically replaces the handle and disposes of the old one; `dispose()` terminates the holder's ownership. This policy fits when the application **only wants one active subscription at a time**.

**Do not copy this pattern verbatim when each `accept` call must keep an independent stream alive.** In that case, use `Disposable.Composite` or a multi-subscription registry with bounds and removal of finished subscriptions. Clarify who has authority to cancel each stream.

### 10.2. Why Not Subscribe and Drop the Handle?

~~~java
@Bean
Consumer<Flux<String>> leakingStyle() {
    return source -> source.subscribe(System.out::println);
}
~~~

With an infinite source, this provides no explicit way for the bean itself to stop it and includes no error callback. If the framework calls `accept` multiple times, active subscriptions can accumulate. Not every subscription necessarily causes a real leak, yet this design makes it **hard to prove zero leaks** during shutdown, rebalance, or reconnects.

For most asynchronous work that needs outcome reporting, consider `Function<Flux<T>, Mono<Void>>` instead of `Consumer<Flux<T>>`, letting the caller/adapter manage the returned publisher.

### 10.3. Owning a Handle Differs from Owning the Whole System

Even when a bean disposes of its own handle, the binder may maintain its own subscriptions, event loops, and connections. Never shut down shared Schedulers or brokers from a consumer unless that bean **genuinely owns** those resources. The system needs a unified shutdown plan across source, adapter, and business logic.

## 11. Function<Flux<T>, Mono<Void>> and Completion Responsibility

A reactive function returning a result lets the caller observe terminal signals:

~~~java
@Bean
Function<Flux<OrderEvent>, Mono<Void>> persistOrders(
        ReactiveOrderRepository repository) {

    return incoming -> incoming
        .concatMap(repository::save)
        .then();
}
~~~

`repository.save` is a hypothetical API returning `Mono<Void>`. Once a finite source finishes and all write tasks complete per publisher contracts, the resulting `Mono<Void>` emits `onComplete`.

**Never call `subscribe()` inside the function and return `Mono.empty()`:**

~~~java
// Broken contract: reports success before external operations finish.
Function<Flux<OrderEvent>, Mono<Void>> wrong = source -> {
    source.concatMap(repository::save).subscribe();
    return Mono.empty();
};
~~~

This is *fire-and-forget* with errors and cancellation severed from the returned publisher. On shutdown or timeout, the caller has no handle to await the spawned work.

### 11.1. Infinite Streams Do Not Emit Per-Message Completion

If the input is a continuous `Flux`, `then()` waits for the **entire** input to finish. Individual event saves may succeed, yet the overall `Mono<Void>` may never emit normal completion while the stream stays alive.

Hence, the terminal signal of `Function<Flux<T>, Mono<Void>>` **cannot itself serve as per-message acknowledgment** in an infinite event stream. That requires per-message/batch mechanisms in the adapter and repository depending on the protocol.

### 11.2. When Should You Return Flux<R> Instead of Mono<Void>?

If downstream needs a result per event:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<Decision>> decideOrders(
        RiskClient riskClient) {

    return incoming -> incoming.flatMap(riskClient::decide, 8);
}
~~~

The `Flux<Decision>` output carries per-element results. The adapter can subscribe and dispatch each result outward. End-of-stream `onComplete` and broker per-message acknowledgment remain two distinct concerns.

## 12. Integrating with FunctionCatalog, Composition, and Adapters

`FunctionCatalog` registers and looks up functional beans. Example of a pipeline that filters data and then calls a service:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderEvent>> validOrders() {
    return orders -> orders.filter(o -> o.amountCents() > 0);
}

@Bean
Function<Flux<OrderEvent>, Flux<Decision>> evaluate(
        RiskClient riskClient) {
    return orders -> orders.concatMap(riskClient::decide);
}
~~~

You can select the composition:

~~~properties
spring.cloud.function.definition=validOrders|evaluate
~~~

Here `validOrders` and `evaluate` participate in **one logical publisher chain**. When downstream cancels, cancellation propagates through supporting Reactor operators back upstream. However, if any step manually subscribes on its own, that chain of cancellation responsibility can break.

### 12.1. HTTP Adapter

When a client aborts a request or closes a streaming response, the HTTP adapter can cancel the output subscription. If resources are opened per request, clean them up promptly. Still:

- Never claim every client disconnect is detected instantaneously.
- An HTTP call already dispatched to an external service may continue executing.
- A committed action is not automatically rolled back by cancellation.
- HTTP status codes and error response bodies depend on the adapter; do not infer them directly from `SignalType`.

### 12.2. Spring Cloud Stream and Event Binders

In Spring Cloud Stream, a `Function<Flux<T>, Flux<R>>` may be applied once to a **long-lived publisher**, rather than invoking Java `apply` once per message. When a binding stops, rebalances, or the context closes, the adapter must manage subscriptions and transport connections per its actual contract.

Do not assume:

- `doFinally(ON_COMPLETE)` equals the broker acknowledging every event.
- `doFinally(CANCEL)` automatically rolls back offsets or transactions.
- `Flux.usingWhen` automatically makes the broker commit exactly once.
- A reactive error is handled by a binder identically to a per-message imperative exception.

Check documentation and run integration tests for your specific Spring Cloud Stream and binder versions.

### 12.3. Serverless Adapter

A serverless invocation enforces execution timeouts and runtime limits. An infinite `Flux` may be unsuitable when the invocation must await results. On timeout, the runtime may cancel the subscription or terminate the environment, yet **there is no promise Java cleanup always gets to run** if the process is killed abruptly.

For critical workloads, design finite sources, durable checkpoints/brokers, and idempotency; never rely solely on JVM shutdown hooks in serverless processes.

### 12.4. Supplier and Polling

A finite `Supplier<Flux<T>>` can complete after one batch, yet **it is not automatically re-invoked** merely because it emitted `onComplete`. In Spring Cloud Stream, `@PollableBean` marks a reactive supplier that needs repeated polling; the schedule belongs to the poller/adapter, not Spring Cloud Function Core.

A continuous `Supplier<Flux<T>>` must be canceled when its binding stops. Clarify who creates the subscription and who holds authority to stop it, rather than expecting `Supplier.get()` to manage the entire lifecycle itself.

## 13. Timeouts, Retries, and Why Cancellation Does Not Guarantee Rollback

### 13.1. Publisher Timeout vs. Driver Timeout

~~~java
Mono<Decision> result = Mono
    .fromCallable(() -> legacyClient.check(order))
    .subscribeOn(Schedulers.boundedElastic())
    .timeout(Duration.ofSeconds(2));
~~~

This publisher emits a timeout error after two seconds and requests upstream cancellation. Yet `legacyClient.check` is a blocking API: the background thread or driver **may continue running** until the call returns. Configure timeouts directly on the JDBC/HTTP client and release connections per driver contracts.

`Schedulers.boundedElastic()` avoids blocking the event loop; **it does not create stronger cancellation guarantees than the underlying SDK supports**.

### 13.2. Retries and New Resource Boundaries

~~~java
Flux<OrderEvent> retried = Flux.usingWhen(
    sessionFactory.open(),
    ReactiveOrderSession::readPending,
    ReactiveOrderSession::commitAndClose,
    (session, error) -> session.rollbackAndClose(error),
    ReactiveOrderSession::cancelAndClose
).retry(2);
~~~

This sketch can open **a new resource/session on every re-subscription** triggered by retry. If the previous attempt already emitted some events before failing, they may be emitted again. Idempotency and proper transaction/checkpoint designs are required.

Never interpret retry as merely “resuming from the element after the error.” With cold sources, retry typically re-subscribes upstream; with hot sources, lost data may not be recovered.

### 13.3. Forced Shutdowns and Already-Started Side Effects

There is no absolute guarantee that Java callbacks will run during a forced process kill, power loss, or abrupt external disconnect. Thus, Reactor resource cleanup is part of resilient design **when the JVM has a chance to execute**, not a replacement for:

- Database transactions and commits/rollbacks.
- Outboxes or durable message queues.
- Idempotency keys for retried operations.
- Leases/heartbeats and expiration rules when clients vanish.
- Post-incident reconciliation workflows.

## 14. Discarded Elements, Canceled Resources, and Backpressure Limits

An event stream can drop elements due to `filter`, `take`, buffer overflows, sampling, or cancellation. If an element holds a reference-counted resource, it may need releasing when discarded. That is separate from closing the connection/session that created the publisher.

| Need | Tool to consider |
| --- | --- |
| Stop receiving the entire stream | `cancel` / `Disposable.dispose()` |
| Synchronous cleanup per subscription | `Flux.using` / `Mono.using` |
| Asynchronous cleanup distinguishing complete/error/cancel | `Flux.usingWhen` / `Mono.usingWhen` |
| Record metrics for every outcome | `doFinally` |
| Release elements discarded by supporting operators | `doOnDiscard` |
| Limit element demand | `request(n)` / backpressure operators |
| Limit in-flight I/O | `flatMap(mapper, concurrency)` / `concatMap` |
| Close shared client/pool | Bean/container lifecycle |

A backpressure-compliant `Flux` does not automatically close a resource the application opened outside the publisher. Likewise, calling `dispose()` does not make all buffers and object references disappear instantaneously. Manage both ownership and discard semantics thoroughly when working with resource-sensitive objects.

## 15. Testing Lifecycle with StepVerifier

Unit tests should verify **signals** and **cleanup**, not just `onNext` values. `reactor-test` provides `StepVerifier` to subscribe, request cancellation, and assert completions or errors.

### 15.1. Testing Successful Completion

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class LifecycleTest {

    @Test
    void finiteSourceCompletes() {
        StepVerifier.create(Flux.just("A", "B"))
            .expectNext("A", "B")
            .verifyComplete();
    }
}
~~~

This tests `onComplete` on a finite publisher; it does not verify external resource cleanup.

### 15.2. Testing That onError Does Not Become onComplete

~~~java
@Test
void errorTerminatesTheSequence() {
    Flux<String> source = Flux.concat(
        Flux.just("A"),
        Flux.error(new IllegalStateException("read failed"))
    );

    StepVerifier.create(source)
        .expectNext("A")
        .expectErrorMessage("read failed")
        .verify();
}
~~~

This is a standalone test method that can be placed inside `LifecycleTest` with the imports above.

### 15.3. Testing That cancel Triggers doOnCancel

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.atomic.AtomicBoolean;

@Test
void cancelIsNotCompleteButNotifiesUpstream() {
    AtomicBoolean cancelled = new AtomicBoolean();

    Flux<String> source = Flux.<String>never()
        .doOnCancel(() -> cancelled.set(true));

    StepVerifier.create(source)
        .expectSubscription()
        .thenCancel()
        .verify();

    assertTrue(cancelled.get());
}
~~~

`Flux.never()` emits neither elements nor terminal signals. The test cancels explicitly so it does not hang waiting for completion.

### 15.4. Testing That Flux.using Closes Resources Even on Cancel

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.atomic.AtomicBoolean;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@Test
void usingClosesResourceOnCancel() {
    AtomicBoolean closed = new AtomicBoolean();

    class Lease implements AutoCloseable {
        @Override
        public void close() {
            closed.set(true);
        }
    }

    Flux<String> source = Flux.using(
        Lease::new,
        lease -> Flux.concat(
            Flux.just("A"),
            Flux.<String>never()
        )
    );

    StepVerifier.create(source)
        .expectNext("A")
        .thenCancel()
        .verify();

    assertTrue(closed.get());
}
~~~

**Note:** This illustrates the `Flux.using(Callable, Function)` overload for an `AutoCloseable` resource; the resource is closed per operator semantics. The `Lease` object itself does not need to be emitted downstream.

### 15.5. Testing Asynchronous Cleanup with usingWhen

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@Test
void usingWhenWaitsForAsyncCleanupBeforeCompleting() {
    AtomicInteger cleanupCount = new AtomicInteger();

    Flux<String> source = Flux.usingWhen(
        Mono.just("resource"),
        resource -> Flux.just("A", "B"),
        resource -> Mono.fromRunnable(
            cleanupCount::incrementAndGet
        )
    );

    StepVerifier.create(source)
        .expectNext("A", "B")
        .verifyComplete();

    assertEquals(1, cleanupCount.get());
}
~~~

Here cleanup is a `Mono.fromRunnable` subscribed to by the operator as a contracted async termination step; even though the test runs synchronously, it proves the cleanup publisher **is actually executed and awaited before completion**. In real systems, cleanup might be `connection.close()` returning an I/O publisher.

### 15.6. Testing Timed-Source Cancellation with Virtual Time

~~~java
import java.time.Duration;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@Test
void takeThreeCompletesDownstream() {
    StepVerifier.withVirtualTime(
            () -> Flux.interval(Duration.ofSeconds(1)).take(3)
        )
        .thenAwait(Duration.ofSeconds(3))
        .expectNext(0L, 1L, 2L)
        .verifyComplete();
}
~~~

The `take(3)` publisher completes normally even though it canceled upstream `interval`. **Virtual time only controls Reactor schedulers participating in sources created inside the factory**; it does not simulate real-world databases, sockets, or brokers.

### 15.7. Be Careful Asserting Immediately After doFinally

Because `doFinally` usually runs **after** the terminal signal is forwarded downstream, writing:

~~~java
AtomicBoolean finalHookCalled = new AtomicBoolean();

Flux.just("A")
    .doFinally(signal -> finalHookCalled.set(true));
~~~

and asserting the flag right after a verify call can depend on callback timing. When testing `doFinally` side effects, use appropriate test synchronization (e.g., `CountDownLatch` with a finite timeout) or an awaitable observer. **Never build transactional logic assuming a hook always finishes before the terminal signal's observer.**

## 16. Observing Runtime Behavior and Detecting Resource Leaks

When operating long-lived streams, counting received messages alone is insufficient. Track **subscriptions** and **resources** as well.

| Metric / signal | Question to answer |
| --- | --- |
| Active subscriptions | Are any feeds left uncanceled when clients disconnect? |
| `doFinally` split by `ON_COMPLETE`/`ON_ERROR`/`CANCEL` | Are there excessive cancellations or abnormal errors? |
| Open connections/cursors/file handles | Do resource counts drop after each batch or request? |
| Cleanup duration | Is session closing hanging or slow? |
| Cleanup error count | Do failed closes leak resources or leave data locked? |
| HTTP connection pool active/pending | Is the pool leaking or saturated? |
| Active event loops/timers/tasks | Are unintended infinite sources still running? |
| Broker lag, acks, redeliveries | Is data stuck, duplicated, or lost across shutdowns? |
| Memory/heap and reference counts | Are discarded items being released properly? |

An instrumentation wrapper can track:

~~~java
Flux<String> monitored = source
    .doOnSubscribe(s -> metrics.incrementActive())
    .doFinally(signal -> {
        metrics.decrementActive();
        metrics.recordTermination(signal.name());
    });
~~~

Only use this counting approach when every subscription crosses both hooks strictly once by design, and metric callbacks do not block sensitive threads. `doFinally` does not provide a business “commit”; it serves lifecycle observability.

### 16.1. Common Warning Signs

- Active subscriptions rise without dropping after clients disconnect.
- Open connections/cursors grow with every request.
- `onComplete` callbacks never fire due to infinite sources; shutdown lacks cancellation.
- Many tasks wait in `boundedElastic` after timeouts because blocking drivers fail to abort promptly.
- Retaining `Disposable` handles in collections without pruning on completion, leaking object references.
- A `usingWhen` cleanup failure gets logged and ignored, leaving resources pinned.
- Retries or resubscriptions re-read records already processed before an error.

Distinguish **current subscriber count** from **open resource count**: one subscription can hold multiple resources, and one pool can be shared across many subscriptions.

## 17. Controlled Shutdown Procedure

When an application must shut down for deployment or scale-down, the goal is normally **stop accepting new work**, finish or record in-flight work, and close resources within the allowed window.

A reference workflow:

1. **Stop new intake:** instruct adapters/binders to stop pulling new messages or accepting new requests.
2. **Decide drain vs. cancel:** for long-lived streams, you cannot wait forever for `onComplete`; enforce a timeout on draining in-flight work.
3. **Await accepted work** per policy: commit/ack once completion criteria are met, or persist replayable state.
4. **Cancel remaining live subscriptions** via framework mechanisms or retained handles; cleanup must handle the cancel branch.
5. **Close shared resources** such as HTTP clients, connection pools, and custom schedulers via bean lifecycles.
6. **Persist incomplete work** for recovery on restart: offsets/checkpoints, idempotency, job state, or dead-letter stores.

The exact sequence depends on Spring Boot, the HTTP adapter, the binder, and the deployment platform. **Never write a custom shutdown hook that closes all resources before the binder stops receiving/acking**, as that causes mid-flight failures.

### 17.1. Graceful Shutdown Does Not Replace Crash Recovery

Even with graceful shutdown, a process can still be killed when platform timeouts expire. Therefore, critical events need a recoverable path (broker/outbox/checkpoints) and idempotent consumption. Resource cleanup optimizes **stability when normal shutdown time is available**, rather than guaranteeing durability across all crashes.

## 18. Common Misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| “`cancel` is the same as `onComplete`.” | Cancel is a subscriber request; it does not emit completion downstream. |
| “`doOnTerminate` runs on cancellation.” | That hook covers `onComplete`/`onError`, not cancellation. |
| “`doFinally` is only for errors.” | It observes complete, error, and cancel. |
| “`doFinally` guarantees a transaction committed.” | It is a publisher lifecycle hook, not a durable commit mechanism. |
| “Calling `closeAsync()` inside `doFinally` is enough.” | If the API returns a cold `Mono`, nobody subscribes to that cleanup; consider `usingWhen`. |
| “A resource opened outside a publisher can be reused across all subscriptions.” | A resource closed after the first run may become invalid; define ownership carefully. |
| “`Flux.usingWhen` only needs to close on `onComplete`.” | You must handle errors and cancellation as well, especially with transactions. |
| “Canceling `Mono.fromCallable` definitely stops JDBC.” | Blocking drivers can keep running; timeouts/cancellation do not guarantee rollback. |
| “`take(3)` makes upstream emit `onComplete` too.” | Downstream completes while upstream can receive cancel. |
| “A `Consumer<Flux<T>>` just calls `subscribe()` without keeping the handle.” | Long-lived streams need error handling, lifecycle tracking, and cancellation control. |
| “`Mono<Void>` completes for every event in an infinite stream.” | It completes when the whole finite pipeline ends, and does not auto-ack each message. |
| “When Spring Boot shuts down, all Java callbacks definitely run.” | Process kills/crashes can skip cleanup; durable recovery is required. |
| “Closing a shared client at the end of every request is good practice.” | Shared resources must close via bean lifecycles, not per subscription. |
| “A Reactor unit test proves the binder acks properly.” | Integration tests with real brokers and delivery configs are required. |
| “Retries do not affect cleanup or data.” | Retries can open new resources, replay items, and repeat side effects. |

## 19. Lifecycle-Managed Source Design Checklist

~~~mermaid
flowchart TD
    START["Create Flux/Mono for task"] --> OWNER{"What is the resource scope?"}
    OWNER -->|Per subscription| PER["using / usingWhen"]
    OWNER -->|Shared bean| BEAN["Container lifecycle"]
    OWNER -->|No dedicated resource| NONE["Standard pipeline"]
    PER --> CLEAN{"Is cleanup asynchronous?"}
    CLEAN -->|Yes| WHEN["usingWhen: complete/error/cancel"]
    CLEAN -->|No| USING["using: AutoCloseable"]
    USING --> OBS["Observe with doFinally"]
    WHEN --> OBS
    BEAN --> OBS
    NONE --> OBS
    OBS --> LONG{"Can the stream run long-term?"}
    LONG -->|Yes| CANCEL["Manage Disposable, shutdown/cancel"]
    LONG -->|No| FINITE["Verify onComplete/onError"]
    CANCEL --> VERIFY["Test cleanup and adapter"]
    FINITE --> VERIFY
~~~

Before promoting a function to production, answer thoroughly:

1. **Who creates the resource** and when? At bean creation, `apply`, or subscription?
2. **Who owns the resource?** One request, one subscription, one transaction, or the whole application?
3. **Are all three termination paths covered?** What cleanup runs on completion, error, and cancel?
4. **Does cleanup return a publisher?** If so, who subscribes to and awaits it?
5. **Are all operations needing the resource** kept inside `usingWhen`'s closure?
6. **Is cancellation truly supported** by the HTTP/JDBC client, or does it merely stop signal delivery?
7. **Does the completion signal** mean the whole batch succeeded or merely that work was enqueued?
8. **Do retries reopen resources and re-run side effects?**
9. **Can the stream run indefinitely**, and who retains/cancels the handle?
10. **Does the adapter handle errors/acks/transactions** as expected?
11. **How are mid-flight crashes recovered** if cleanup callbacks never execute?
12. **Do tests cover** completion, errors, cancellation, timeouts, retries, and shutdown?

## 20. Self-Assessment Questions

1. How do `onComplete`, `onError`, and `cancel()` differ in signal direction and callbacks?
2. Why are `doOnComplete` and `doOnTerminate` insufficient for releasing resources on the cancel path?
3. When `Flux.interval(...).take(3)` ends, why does upstream observe `CANCEL` while downstream observes `ON_COMPLETE`?
4. Does `Disposable.dispose()` guarantee a JDBC query stopped and rolled back?
5. Why does `Flux.using` fit per-subscription `AutoCloseable` resources?
6. What can go wrong if a resource is created outside `Flux.using` and the same instance is reused across multiple subscriptions?
7. Why might `doFinally(signal -> connection.closeAsync())` fail to actually close the connection?
8. Which cleanup callbacks does `Flux.usingWhen` accept for completion, error, and cancellation?
9. If the commit step of `Flux.usingWhen` fails, is it guaranteed that previously emitted items never reached downstream?
10. Why should you not close a shared HTTP connection pool at the end of every subscription?
11. With a self-subscribing `Consumer<Flux<T>>`, why must you manage `Disposable` handles or a subscription registry?
12. Does `Function<Flux<T>, Mono<Void>>` automatically acknowledge each message on an infinite source?
13. How can `retry(2)` recreate resources and emit duplicate data?
14. Why does a graceful shutdown procedure not replace idempotency and crash recovery?
15. How would you write a `StepVerifier` test to verify a resource is closed on the cancel path?
16. Which metrics help distinguish a subscription leak from a connection pool leak?

## 21. References

- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/) — subscription lifecycles, cancellation, `doFinally`, and `using`.
- [Project Reactor — Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html) — exact specifications of `using`, `usingWhen`, `doOnCancel`, `doOnTerminate`, and `doFinally`.
- [Project Reactor — Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html) — `Mono.usingWhen`, terminal hooks, and cleanup.
- [Project Reactor — Testing](https://projectreactor.io/docs/test/release/reference/) — `StepVerifier`, cancellation, and virtual time.
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html) — `Supplier`, `Function`, `Consumer`, and reactive signatures.
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html) — reactive Consumers, subscriptions, and binder boundaries.

Exact cleanup, session, cancellation, and acknowledgment semantics also depend on the specific versions of Reactor, Spring Cloud Function/Stream, and drivers/binders in use. Cross-check your project's dependencies/BOM and run integration tests against real adapters.

**Key takeaway:** `onComplete` signals normal publisher completion; `onError` signals termination due to an error; `cancel` is a subscriber request to stop receiving, **not itself a terminal signal sent downstream**. `doFinally` observes all three paths, while `Flux.using` and `Flux.usingWhen` tie resource cleanup to the subscription lifecycle. Identify clearly whether resources belong to each subscription or the whole application, manage `Disposable` handles for long-lived streams, and treat cancellation as a request to stop work—**not a guarantee of rollback or exactly-once delivery**. When deploying Spring Cloud Function across HTTP, brokers, or serverless, verify adapter lifecycles, timeouts, acknowledgments, retries, and crash recovery as well.
