# Laziness, Subscription, and the Lifecycle of a Reactive Sequence in Spring WebFlux

## 1. The Problem: Does Declaring a Pipeline Mean Running It?

In imperative programming, calling `service.findById(id)` usually executes immediately when control passes through that statement. In Project Reactor, an expression like `Mono.defer(() -> service.findReactive(id))` usually only **describes how to create the data source when subscribed**. Assembling a pipeline, subscribing a subscriber, requesting elements, emitting signals, and cleaning up resources are distinct phases.

This is foundational knowledge for **Spring WebFlux**, where controllers typically return `Mono<T>` or `Flux<T>` so the HTTP infrastructure subscribes and handles the response. Failing to distinguish these phases leads to bugs: calling APIs too early, sending emails/payments twice during retries, thinking a source executed even though nobody subscribed, calling `subscribe()` yourself and losing error/cancellation management, or forgetting to close resources when the client disconnects.

Objectives:

- Distinguish **assembly time** (building the chain), **subscription time** (subscribing), **request/demand**, **signal processing**, **termination/cancellation**, and **resource cleanup**.
- Know how `Mono.just(...)` differs from `Mono.defer(...)`, `Mono.fromSupplier(...)`, and `Mono.fromCallable(...)`; never say “everything in Mono is lazy”.
- Understand that `subscribe` propagates from downstream to upstream, whereas `onNext/onError/onComplete` flow from upstream to downstream.
- Explain why subscribing to a cold chain twice can trigger queries/side effects twice; compare with hot/shared/cached publishers.
- Observe `doFirst`, `doOnSubscribe`, `doOnRequest`, `doOnNext`, `doOnError`, `doOnComplete`, and `doFinally`.
- Manage `Disposable`, `cancel()`, timeouts, retries, resource acquisition/release, and client disconnects.
- Integrate cleanly with WebFlux annotated controllers, WebClient, and Reactive Repositories; do not manually subscribe inside controllers.
- Practice **Java 17+, Spring Framework 6.x, Spring Boot 3.x, Reactor Core** with runnable code and `StepVerifier`/`WebTestClient` tests.

**Scope:** Spring WebFlux/Reactor, not just Spring MVC `Callable`/Servlet async. Reactor is built on Reactive Streams; a source can emit **synchronously right inside `subscribe`/`request`**, so reactive does not automatically spawn a new thread. Examples do not require a more specific Reactor version beyond what Spring Boot 3.x manages compatibly.

## 2. Lifecycle Diagram of a Sequence

```text
T0: ASSEMBLY — create Flux/Mono, chain operators
    Flux.range(1, 3).map(...).filter(...)
             |
             | (no terminal consumer yet)
             v
T1: SUBSCRIBE — downstream Subscriber subscribes
    subscriber -> filter -> map -> source
             |
             v
T2: onSubscribe(Subscription), demand request(n)
    downstream -------------> upstream
             |
             v
T3: SIGNALS
    upstream -> onNext(value)* -> downstream
    upstream -> onComplete()/onError() -> downstream
             |
             v
T4: FINALLY/CLEANUP
    complete | error | cancel
    release file/connection/registration
```

These milestones are not necessarily separated in time: with `Flux.range(1,3)`, subscribe/request/onNext/complete can occur **on the same thread and same call stack**. With `WebClient` or a reactive database driver, signal emission may arrive later from network I/O callbacks. An infinite publisher may never emit `onComplete`; it requires cancellation or a dedicated termination policy.

**Responsibility rule:** Assembling a pipeline does not mean the HTTP response has been sent. Subscribing also does not mean elements have been received: `request(n)` demand and how the source emits signals determine that. Completion/error/cancel require resource control; do not treat the controller method returning as the completion of the operation.

## 3. Reactive Streams: Publisher, Subscriber, Subscription

The three main interfaces in `org.reactivestreams`:

```java
public interface Publisher<T> {
    void subscribe(Subscriber<? super T> subscriber);
}

public interface Subscriber<T> {
    void onSubscribe(Subscription subscription);
    void onNext(T item);
    void onError(Throwable failure);
    void onComplete();
}

public interface Subscription {
    void request(long n);
    void cancel();
}
```

These are **illustrative API signatures**, not source files to recreate since the library already provides them.

- **Publisher:** a source capable of supplying 0..N elements; `Mono` represents 0..1, `Flux` represents 0..N.
- **Subscriber:** receiver of callbacks and decider of demand; most WebFlux code does not need to implement Subscriber manually.
- **Subscription:** contract binding one upstream–downstream relationship, accepting `request(n)` and `cancel()`.
- **Processor:** both a Subscriber and a Publisher; many operators inside Reactor create equivalent boundaries.
- **Disposable:** Reactor convenience type returned by `subscribe` overloads for unsubscribing, **not identical to the standard `Subscription` API**.

The protocol has the form:

```text
onSubscribe → onNext* → (onError | onComplete)?
```

`onError` and `onComplete` are mutually exclusive terminal signals; they do not require demand to be emitted. `onNext` must not exceed accepted `request(n)`, must not send null, and must not be sent after a terminal signal. `cancel()` causes the publisher to eventually stop emitting, though it does not necessarily halt in-flight work immediately or roll back transactions.

## 4. Assembly Time: When Has Java Already Run Code?

Example:

```java
System.out.println("A");
Mono<String> mono = Mono.just(expensiveCall());
System.out.println("B");
```

Here **`expensiveCall()` is evaluated immediately** when the program builds the argument passed to `Mono.just`, before `mono` is assigned. `Mono.just` holds an already-computed value. If `expensiveCall()` makes a blocking network or JDBC call, wrapping its result in Mono does not “turn it lazy”.

By contrast:

```java
Mono<String> mono = Mono.fromSupplier(() -> expensiveCall());
```

The lambda describing the work will be called on subscription (and the source logic runs according to the operator's semantics). Creating the `mono` variable has not invoked `expensiveCall` yet.

**Second pitfall:**

```java
Mono<String> mono = Mono.just("hello")
    .map(value -> value.toUpperCase());
```

The `map` lambda has not run at assembly; however, the `Mono.just("hello")` expression and operator object creation have already executed. You must not say every line inside a reactive expression is deferred. **Building the pipeline is normal Java execution; what is deferred is the work placed inside publishers/operators to run upon subscription.**

### Differences Between Mono.just, fromSupplier, fromCallable, defer

| Creation Method | When Is Value/Source Computed? | Notes |
| --- | --- | --- |
| `Mono.just(value)` | `value` is computed **before** the call | From a non-null value, replays this value to subscribers |
| `Mono.justOrEmpty(nullable)` | `nullable` is computed beforehand | Null → completes empty, no onNext(null) |
| `Mono.fromSupplier(supplier)` | Supplier invoked on subscription | Supplier returning null → empty per Reactor contract |
| `Mono.fromCallable(callable)` | Callable invoked on subscription | Checked exceptions become onError; null → empty |
| `Mono.defer(supplierOfMono)` | Factory creates **a new Publisher per subscription** | Useful when reading state/building pipeline at subscribe time |
| `Flux.defer(supplierOfFlux)` | Similar, for 0..N | Does not change the thread model on its own |
| `Mono.empty()` | Source with no onNext | Still has subscription/completion |
| `Mono.error(exception)` | Source emitting onError on subscribe | Exception object may be created at assembly |
| `Mono.error(exceptionSupplier)` | Creates exception via factory on subscribe | Suits exceptions carrying subscription-local details |

`Mono.defer` does not merely “delay a calculation”: it defers **creating the entire Publisher** based on fresh state at each subscription. `fromSupplier`/`fromCallable` are typically suited for computing exactly **one value**. If the source must be reconfigured per subscriber's Reactor Context, use `Mono.deferContextual(...)`.

## 5. Clear Example: Eager vs. Lazy Values When Subscribing Twice

The complete Java file below requires Reactor Core (e.g., in a Spring Boot WebFlux Maven project). Class `LazinessDemo.java`:

```java
package com.example.demo;

import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Mono;

public class LazinessDemo {

    public static void main(String[] args) {
        AtomicInteger counter = new AtomicInteger();

        int eagerValue = counter.incrementAndGet();
        Mono<Integer> eager = Mono.just(eagerValue);

        Mono<Integer> lazy = Mono.fromSupplier(
                counter::incrementAndGet);

        System.out.println("assembled=" + counter.get());
        System.out.println("eager1=" + eager.block());
        System.out.println("eager2=" + eager.block());
        System.out.println("lazy1=" + lazy.block());
        System.out.println("lazy2=" + lazy.block());
        System.out.println("final=" + counter.get());
    }
}
```

In a Maven project that already has `spring-boot-starter-webflux`, run main from your IDE or `mvn exec:java` when the exec plugin is configured; **do not** run bare `javac LazinessDemo.java` without Reactor jars. `block()` is used only at the **synchronous demo main boundary**, never inside a WebFlux handler/event loop.

Exact stdout with the synchronous source:

```text
assembled=1
eager1=1
eager2=1
lazy1=2
lazy2=3
final=3
```

Explanation:
1. `counter.incrementAndGet()` before `just` runs immediately, even with no subscriber: counter=1.
2. Two `block()` calls on `Mono.just(1)` create two subscriptions yet emit the **same captured value** of 1.
3. Two `block()` calls on `Mono.fromSupplier(counter::incrementAndGet)` create two distinct subscriptions, invoking the supplier twice more → 2 then 3.
4. `block()` itself is **a terminal operation initiating a new subscription** to the Mono each time it is called.

This leads to an important question: if the supplier **writes to a database/sends email/charges payment**, re-subscribing can execute the side effect again. Therefore, never place non-idempotent side effects in a cold source and allow arbitrary `retry`/multiple subscriptions without business-level safeguards.

## 6. Subscribing: What Does subscribe() Actually Do?

Calling `publisher.subscribe(subscriber)` establishes a link between Subscriber and Publisher, wires the operator chain, and passes a `Subscription` downstream.

Given a pipeline:

```java
Flux<Integer> stream = Flux.range(1, 3)
    .map(n -> n * 10)
    .filter(n -> n >= 20);

stream.subscribe(System.out::println);
```

Creating `stream` does not consume any elements. `subscribe(...)` starts the process; with synchronous `Flux.range` you may see:

```text
20
30
```

However, this is the synchronous case: `subscribe()` may return without waiting for network I/O to finish in an async source, and code after `subscribe()` is not guaranteed to run after `onComplete`.

### Subscription Flows from Downstream to Upstream

```text
downstream subscribe
     |
     v
filter.subscribe -> map.subscribe -> source.subscribe
                                        |
onSubscribe(subscription) <-------------|
      |
request(n) -----------------------------> upstream
                                        |
onNext / onComplete --------------------> downstream
```

Operators can wrap the Subscription and reshape demand internally. A terminal Subscriber calling `request(1)` does not guarantee upstream receives exactly one `request(1)` when `buffer`/`flatMap`/prefetch are present.

Common Reactor overloads `subscribe()`/`subscribe(Consumer)` typically request unbounded demand; if you want to **observe per-element requests**, use `BaseSubscriber` or `StepVerifier.create(publisher, 0)` with `thenRequest(n)`.

## 7. Demand: Subscribing Does Not Guarantee Receiving onNext

Reactive Streams requires the Publisher **never to send more `onNext` signals than requested**. Right after subscribing with demand 0, a protocol-compliant source must not emit `onNext` data. However, it may still send terminal `onComplete`/`onError` without demand.

Reactor Test example:

```java
StepVerifier.create(Flux.range(1, 3), 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNext(1)
    .thenRequest(2)
    .expectNext(2, 3)
    .verifyComplete();
```

This snippet goes inside a Java test method with imports present. Demand accumulates rather than resetting: `request(1)` followed by `request(2)` grants a total of 3 `onNext` permissions.

Notes:

- `request(0)` and negative values are not “pause”; they violate the spec, and an active Subscription must signal `IllegalArgumentException` via `onError`.
- `request(Long.MAX_VALUE)` is treated as unbounded demand, which does not mean the source is guaranteed to emit infinitely.
- `cancel()` requests stopping the subscription; some in-flight signals may arrive right after cancel.
- Hot data transports that cannot slow down on their own may have to buffer/drop/fail by policy; `Flux` does not make every upstream backpressure-capable.
- When using `publishOn`, `flatMap`, `buffer`, or `limitRate`, upstream demand and final subscriber demand may differ.

## 8. Lifecycle Hooks: doFirst, doOnSubscribe, doOnRequest, doOnNext

Reactor provides several operators that only observe lifecycle events without transforming data.

| Hook | Observed Milestone | Notes |
| --- | --- | --- |
| `doFirst(Runnable)` | Before subscription begins propagating into the source | Invoked from the subscribing flow; chained `doFirst` hooks run in reverse declaration order |
| `doOnSubscribe(Consumer<Subscription>)` | Subscription has been created/passed through the operator | Useful for metrics; do not use to hijack Subscription management arbitrarily |
| `doOnRequest(LongConsumer)` | A `request(n)` crosses the boundary | Observes demand at the operator's position, not HTTP requests |
| `doOnNext(Consumer<T>)` | Source emits a value through the operator | Can repeat per subscription, not inherently limited to once |
| `doOnComplete(Runnable)` | Flux completes successfully | Flux only; not called on error/cancel |
| `doOnSuccess(Consumer<T>)` | Mono completes successfully | Receives **null** when Mono completes empty |
| `doOnError(Consumer<Throwable>)` | Error passes through the operator | Does not recover from error; use `onErrorResume` for fallback |
| `doOnCancel(Runnable)` | Downstream cancels the operator | Not necessarily the exact instant physical I/O finishes |
| `doFinally(Consumer<SignalType>)` | After complete, error, **or cancel** | Essential for final release/logging |
| `doOnDiscard(Class, Consumer)` | Cleanup for elements discarded by certain operators | Applies only to discard-supporting operators; not a catch-all object hook |

**Hook ordering** also depends on operator placement, whether the source is synchronous/async, and reentrant requests. Do not assume a `doOnNext` log always appears before every `doOnSubscribe` in a pipeline; however, the protocol still guarantees a subscriber receives `onSubscribe` before `onNext`.

### doFirst Follows Subscription Direction (Reverse Declaration Order)

```java
Mono.just("x")
    .doFirst(() -> System.out.println("one"))
    .doFirst(() -> System.out.println("two"))
    .subscribe();
```

Synchronous stdout:

```text
two
one
```

Because `doFirst` means “run before subscribing to upstream”, the hook chained later executes first. Do not use `doFirst` for non-idempotent mutations relying on a single subscription, since re-subscribing/`retry` can run the hook again.

### doFinally Runs After Downstream Signal

Snippet:

```java
Mono.just("x")
    .doFinally(signal -> cleanup())
    .subscribe(System.out::println);
```

This snippet requires a `cleanup()` method. `doFinally` is called when the sequence ends via complete/error/cancel, yet this callback may **run after the signal has already propagated downstream**. Thus a test checking a cleanup variable right after `block()` or `verifyComplete()` can occasionally race depending on scheduling; synchronize properly or use signal-observing test tools.

**Distinguishing `doFinally` and `doOnTerminate`:** `doOnTerminate` only observes complete/error and is not guaranteed to run on cancel; `doFinally` covers cancellation as well. For resources with their own lifecycle, `using`/`usingWhen` is usually safer and expresses ownership better than wiring manual cleanup into every branch.

## 9. Empty Mono, onSuccess(null), Errors, and Cancel

`Mono<T>` has these basic completion patterns:

```text
success with value: onSubscribe -> onNext(value) -> onComplete
success empty:      onSubscribe -> onComplete
error:              onSubscribe -> onError(ex)
cancel:             onSubscribe -> ...cancel (not necessarily onComplete)
```

`Mono#doOnSuccess(Consumer<T>)` differs from `doOnNext`: `doOnSuccess` is invoked even when the Mono completes empty, with argument `null`; `doOnNext` is **not** called for empty.

Example:

```java
Mono<String> noValue = Mono.<String>empty()
    .doOnNext(v -> System.out.println("next=" + v))
    .doOnSuccess(v -> System.out.println("success=" + v));

noValue.subscribe();
```

Output:

```text
success=null
```

This is a **null argument to the hook**, not `onNext(null)`. Reactive Streams **forbids** a publisher from emitting a null value via `onNext`. To represent a missing record, use `Mono.empty()` and map to an appropriate 404/204 response status rather than `Mono.just(null)`.

An `onError` is terminal: the upstream pipeline does not continue `onNext` after an error. Operators like `onErrorResume` can switch to a **fallback publisher**, not “continue emitting after terminal” on the old subscription. `retry(n)` **re-subscribes** to the upstream source, which can repeat side effects.

## 10. Cold and Hot: Re-subscribing May Re-run or Share

### Cold Publisher

`Flux.range(1,3)` is cold: each subscription typically creates its own process emitting 1, 2, 3.

`Mono.defer(() -> repository.findById(id))` is a lazy factory; if each subscription triggers a new reactive repository query, subscribing twice can execute the query twice.

```java
Mono<String> cold = Mono.fromSupplier(
        () -> expensiveOperation());

cold.subscribe(v -> useFirst(v));
cold.subscribe(v -> useSecond(v));
```

This is a **snippet** assuming three application-provided methods. Two subscriptions mean two consumptions, and the supplier normally runs twice. Do not call `subscribe()` once to “warm up” and assume the second call simply reads a cached response.

### Hot/Shared Publisher

Hot sources such as a `Sinks.Many` receive events even when subscribers differ or subscribe late. Various share/replay operators provide different forms of multicasting/caching:

| Operator/Usage | Purpose | Warning |
| --- | --- | --- |
| `Flux.share()` | Shares one upstream subscription while subscribers are active | Late subscribers may miss earlier data |
| `publish().refCount(n)` | Connects upstream when n subscribers join, can disconnect when count drops | Thresholds/scheduling/reconnection need testing |
| `Mono.cache()` | Caches terminal signal/value for future subscriptions | Retains errors or results long-term; consider TTL and resources |
| `Flux.cache(history)` | Replays a stored number of items | History/memory limits are critical |
| `Sinks.Many` | Emits events from a manual producer | Buffer/overflow/backpressure policy must be explicit |

**Do not assume caching is safe by default:** caching a per-user/tenant response on a singleton bean can leak data across requests; you need cache keys, TTL, invalidation, and authorization. `Mono.cache()` by default can hold results/errors indefinitely for the Mono instance's lifetime; do not use casually for mutable data or secrets.

### Hotness Is Not a Property of the Flux Type

Two variables both typed `Flux<String>` can have one be cold and the other hot. Hot/cold behavior comes from the **source and sharing strategy**, not the class name.

## 11. retry and repeat Are Both Re-subscriptions

`retry` does not “resume the failed step within an ongoing subscription”. Typically it **re-subscribes to upstream** after `onError`, governed by `retry(n)`, backoff, error type, and source state.

```java
AtomicInteger attempts = new AtomicInteger();

Mono<String> result = Mono.fromCallable(() -> {
    int attempt = attempts.incrementAndGet();
    if (attempt < 3) {
        throw new IllegalStateException("temporary");
    }
    return "ok";
}).retry(2);
```

This snippet sits inside a method with `import java.util.concurrent.atomic.AtomicInteger`. On one subscription to this synchronous source, attempts #1 and #2 fail, #3 succeeds; `retry(2)` allows two retries after the initial try. Calling `result.block()` a second time creates yet another subscription, and since `attempts` is external state, the outcome may differ.

`repeat` re-subscribes after completion (per specific operator semantics), not only after error. `retryWhen` can apply a retry budget/backoff, yet you must classify retryable errors; do not retry all HTTP 4xx or non-idempotent writes.

**Production:** For payment/order creation, use idempotency keys and DB uniqueness/transactions to prevent duplicate side effects if clients retry or Reactor retries; relying on operators alone is insufficient.

## 12. Threads and Schedulers Are Not Spawned Automatically by subscribe

Reactive Streams does not require callbacks to run on a separate thread. `Flux.range`/`Mono.just` can emit signals synchronously right inside the subscription call stack. Reactor `Schedulers` let you switch execution contexts:

- `subscribeOn(scheduler)`: affects where subscription/upstream work executes; commonly used to offload blocking legacy sources onto workers.
- `publishOn(scheduler)`: switches downstream processing from that point onward to a scheduler worker.
- `Schedulers.parallel()`: suited for short CPU-bound tasks, not long blocking I/O.
- `Schedulers.boundedElastic()`: bounded scheduler for bridging to blocking legacy code, still consumes threads/queues.
- `WebClient` and reactive database drivers: typically perform non-blocking I/O, so do not wrap them in `fromCallable` when the client already returns Mono/Flux.

Legacy API integration example:

```java
Mono<String> callLegacy() {
    return Mono.fromCallable(
            () -> legacyJdbcService.queryOne())
        .subscribeOn(Schedulers.boundedElastic());
}
```

This is a **snippet** requiring the `legacyJdbcService` bean. The source is deferred until subscription and runs on a `boundedElastic` worker; **JDBC is still blocking**. Do not call `Mono.just(legacyJdbcService.queryOne())` in a WebFlux controller, because `queryOne()` runs **immediately on the thread invoking the method**, which may be a Netty event loop.

### block() Also Creates a Subscription

`mono.block()` is a terminal consumer that creates a **new** subscription and waits; never use it inside a WebFlux handler or reactor-netty event loop. In Java console demos/tests on threads where blocking is permitted, `block()` can serve as an illustration tool, not a production solution for reactive pipelines.

`blockOptional()`/`block(Duration)` also trigger subscriptions; a blocking caller timing out does not mean the underlying I/O source rolled back side effects.

## 13. doOnNext and Side Effects: Observation vs. Business Processing

`doOnNext` is designed for logging, metrics, tracing, or controlled side effects:

```java
Flux<Order> monitored = orders
    .doOnSubscribe(s -> metrics.started())
    .doOnNext(order -> metrics.itemReceived())
    .doOnError(e -> metrics.failed())
    .doFinally(signal -> metrics.finished(signal));
```

This snippet depends on `orders` and `metrics`. If subscribed twice, the hooks can run twice. If `metrics.finished` throws or blocks, it complicates the lifecycle; hooks should be fast and avoid altering business semantics.

**Do not use `doOnNext(order -> paymentService.charge(order))` to guarantee charging exactly once**. Retry/repeat/multiple subscriptions can invoke it again. If a side effect is part of business logic, express it via a reactive operator returning a Publisher (`flatMap`/`then`) with proper idempotency and transactions; do not spawn fire-and-forget `subscribe()` calls inside a hook.

### Wrong Anti-Pattern

```java
// Wrong: runs a background subscription outside the caller's management.
return repository.save(order)
    .doOnNext(saved -> sendEmail(saved).subscribe());
```

This is a **counterexample snippet**, not a standalone method. If the WebFlux HTTP caller cancels after `repository.save` emits a value, the email has been subscribed separately and may continue independently; email errors can also be lost. A more sound option:

```java
return repository.save(order)
    .flatMap(saved ->
        sendEmail(saved).thenReturn(saved));
```

Here `sendEmail(saved)` returns `Mono<Void>`; the parent chain manages the email's completion/error/cancel. This still does not provide exactly-once transactional email, so production systems may use an outbox/message broker/idempotency.

## 14. Resource Management Across Complete, Error, and Cancel

A source may open a file, database cursor, websocket session, or lease. Cleaning up only in `doOnComplete` misses `onError` and `cancel`.

### Using Resource Scopes

Reactor provides `Flux.using`/`Mono.using` and `usingWhen`:

- `using(resourceSupplier, sourceFactory, resourceCleanup)`: suited for synchronous/`AutoCloseable` resources, tying the resource lifecycle to the subscription.
- `usingWhen(resourcePublisher, resourceClosure, asyncCompleteCleanup, asyncErrorCleanup, asyncCancelCleanup)`: suited for **asynchronous** resource acquisition/cleanup (e.g., reactive connections/transactions), with separate callbacks for terminal paths.

Illustrative file-resource source example:

```java
Flux<String> lines = Flux.using(
    () -> java.nio.file.Files.lines(path),
    stream -> Flux.fromStream(stream),
    java.util.stream.Stream::close);
```

This snippet assumes `java.nio.file.Path path`, Reactor dependency, and `Flux` import. `Files.lines` is blocking file I/O; in WebFlux it should not run directly on a Netty event loop. If reading a file this way is required, consider `subscribeOn(Schedulers.boundedElastic())` or appropriate I/O APIs while bounding file count, size, and resources.

Do not assume `doFinally` always finishes cleanup **before** downstream receives completion. With `usingWhen`, cleanup ordering and terminal signal propagation have specific semantics that require checking docs/versions. When transactions are involved, use Reactor-aware transaction management rather than mixing a ThreadLocal JDBC transaction manager.

### Cleanup on Cancel and HTTP Disconnect

When a WebFlux HTTP subscriber is cancelled (client disconnect/downstream timeout), upstream can receive `cancel`. `doFinally(SignalType.CANCEL)` and `usingWhen`'s `asyncCancel` handler help clean up resources. Still, `cancel` **does not guarantee** physical network/database requests stop immediately or committed side effects roll back.

If the pipeline holds a message broker consumer or event listener, cleanup must unsubscribe/remove the listener; never retain references in an unbounded static map. Cancellation can also come from downstream operators like `take`/`timeout`, not only a browser closing a tab.

## 15. onErrorResume, timeout, take, and doFinally

Various operators terminate subscriptions via different paths:

| Operator/Situation | What Can Happen |
| --- | --- |
| `take(3)` on a source with more data | Takes three elements, cancels upstream, downstream can complete |
| `timeout(Duration)` | When no signal arrives on time, cancels upstream and emits `TimeoutException` downstream |
| `onErrorResume(e -> fallback)` | Switches to a fallback publisher when upstream errors |
| `switchIfEmpty(fallback)` | When upstream completes empty, subscribes to fallback |
| `retry(2)` | After `onError`, re-subscribes upstream up to two times |
| HTTP client disconnect | Downstream HTTP subscriber may cancel |
| `doFinally` | Receives `ON_COMPLETE`/`ON_ERROR`/`CANCEL` at its corresponding boundary |

**Important:** A pipeline can contain **multiple `doFinally` operators at different positions**. For instance, the source before `take(3)` receives cancel, while downstream after `take(3)` receives complete. Therefore, do not claim “the entire chain has a single signal type” when operators transform terminal behavior.

A `Flux` completing empty (no values) still has subscription/completion; `switchIfEmpty` can trigger another publisher. If the fallback is `Mono.just(expensiveCall())`, the expensive call **already ran** when creating the fallback at assembly; use `Mono.defer(...)` if it should only run when truly empty.

## 16. Reactor Context: Per-Subscription Data, Not ThreadLocal

In WebFlux, request processing and signals can hop across multiple threads/schedulers. Consequently, do not rely on a plain `ThreadLocal` to hold request IDs, locales, user context, or tracing data across the pipeline. Reactor provides `Context`/`ContextView` attached to the **Subscriber chain**, suited for immutable subscription-scoped metadata.

Example:

```java
Mono<String> message = Mono.deferContextual(ctx ->
    Mono.just("request=" + ctx.get("requestId")));

String result = message
    .contextWrite(ctx -> ctx.put("requestId", "r-42"))
    .block();
```

This snippet is for a main/test thread with the Reactor dependency. The value of `result` is:

```text
request=r-42
```

Note that `block()` is used at the demo boundary, not in a WebFlux event loop. Reactor Context is not a full copy of a Servlet request; it does not automatically hold user/token data unless the application/framework places it into the context properly. Reactive security context has dedicated Spring Security APIs.

### Context and Subscription Boundaries

Each subscription creates its own subscription context. `contextWrite` affects upstream operators according to Reactor rules; it is not a global ThreadLocal updated for all tasks. If you manually call `subscribe()` inside a controller/service, you may create **a new subscription without the HTTP request's Context**, losing trace/security metadata.

To pass metadata into services, use explicit method parameters or intentional `Mono.deferContextual`; do not hide business inputs in context when they should be explicit arguments.

## 17. WebFlux: The Framework Subscribes at the HTTP Boundary

In a WebFlux controller:

```java
@GetMapping("/products/{id}")
public Mono<ProductDto> one(@PathVariable String id) {
    return productService.find(id);
}
```

The controller merely returns a Publisher. **Spring WebFlux HTTP infrastructure is the downstream subscriber**, subscribing to read results and write the response. It owns critical parts of the lifecycle: demand, response encoding, cancellation, and error handling before the response commits.

You do not need (and usually must not) do:

```java
@GetMapping("/bad")
public Mono<Void> bad() {
    productService.saveSomething().subscribe();
    return Mono.empty();
}
```

This is an **illustrative anti-pattern**, not an existing file. The server may send HTTP success before `saveSomething` finishes, errors are detached from HTTP, cancellation does not propagate, and context can be lost.

Instead use:

```java
@GetMapping("/good")
public Mono<Void> good() {
    return productService.saveSomething();
}
```

This is also a snippet requiring a bean. When the method returns the Publisher, the framework manages the subscription. If an operation is genuinely an independent background workflow, use a monitored queue/broker/task manager rather than hiding it inside `subscribe()` in a request handler.

### When Is the Controller Method Called?

**Invoking the controller method to build the Mono/Flux is part of HTTP request handling; it can run before the publisher is subscribed.** If code runs a blocking call before returning, such as `Mono.just(repository.find())`, that call executes immediately when the handler is invoked. **What is lazy is the logic deferred inside the Publisher, not the entire controller method.**

## 18. Runnable Spring Boot WebFlux Example: Eager, Lazy, Request Lifecycle

Create a Maven project from Spring Initializr:

- Java 17+ and Spring Boot 3.x.
- `spring-boot-starter-webflux`.
- `spring-boot-starter-test` (test scope) and `io.projectreactor:reactor-test` (test scope if not already included).
- **Do not add `spring-boot-starter-web`** if you want Boot to select the WebFlux reactive application type automatically when both starters exist.

Structure:

```text
src/main/java/com/example/demo/
  DemoApplication.java
  SequenceService.java
  SequenceController.java
src/test/java/com/example/demo/
  SequenceControllerTest.java
  LifecycleTest.java
```

The app requires no database. `AtomicInteger` generates a counter per singleton service to help observe behavior across HTTP requests; this is a teaching demo, not a safe distributed sequence/version generator.

### 18.1. DemoApplication.java

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 18.2. SequenceService.java

```java
package com.example.demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class SequenceService {

    private final AtomicInteger sequence = new AtomicInteger();

    public Mono<ValueResponse> nextValue() {
        // Creates a publisher at invocation time; counter not incremented yet.
        return Mono.fromSupplier(() ->
            new ValueResponse(sequence.incrementAndGet()));
    }

    public Mono<ValueResponse> echoLazy(String value) {
        // Mono.defer creates the Publisher at subscription time.
        return Mono.defer(() -> Mono.just(
            new ValueResponse(value.length())));
    }

    public record ValueResponse(int value) {}
}
```

`sequence.incrementAndGet()` only runs when a subscription occurs to `nextValue()`, not when the service method returns the Mono. `echoLazy` uses `defer` to illustrate a per-subscription factory; for a known immutable string, `value.length()` is trivial, so in production `defer` is unnecessary for something that small.

### 18.3. SequenceController.java

```java
package com.example.demo;

import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/lifecycle")
public class SequenceController {

    private final SequenceService service;

    public SequenceController(SequenceService service) {
        this.service = service;
    }

    @GetMapping(path = "/next",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<SequenceService.ValueResponse> next() {
        // WebFlux subscribes; controller NEVER calls subscribe/block.
        return service.nextValue();
    }

    @GetMapping(path = "/double",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<SequenceService.ValueResponse> doubleNext() {
        // zip of two distinct Monos creates two subscriptions to the source.
        return Mono.zip(service.nextValue(), service.nextValue())
            .map(tuple -> new SequenceService.ValueResponse(
                tuple.getT1().value() + tuple.getT2().value()));
    }

    @GetMapping(path = "/stream/{count}",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<SequenceService.ValueResponse> stream(
            @PathVariable int count) {

        if (count < 1 || count > 5) {
            return Flux.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "count must be 1..5"));
        }

        return Flux.range(1, count)
            .delayElements(Duration.ofMillis(80))
            .map(SequenceService.ValueResponse::new);
    }

    @GetMapping(path = "/empty",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<SequenceService.ValueResponse> empty() {
        return Mono.empty();
    }
}
```

**Endpoint explanation:**

- `GET /next` returns a `Mono.fromSupplier`; each normal HTTP request gets its own subscription, incrementing the counter once. If a proxy/client retries HTTP, the counter can increment again; do not use GET with significant side effects like this demo in production.
- `GET /double` creates **two distinct Monos** and `zip` subscribes to both; on a single subscription to zip, the counter usually increments twice and output is the sum of two consecutive values, though concurrency/scheduling across multiple HTTP requests makes the sum non-deterministic. Use isolated tests to verify.
- `GET /stream/{count}` emits a finite `Flux` as server-sent events; `delayElements` uses a time-based scheduler without guaranteeing exact millisecond timing.
- `GET /empty` completes with no item; WebFlux may produce an empty response with a default status depending on handling. If you want an explicit **404** when data is absent, use `switchIfEmpty(Mono.error(new ResponseStatusException(HttpStatus.NOT_FOUND)))` or an appropriate `ResponseEntity`.
- The controller does not call `subscribe()` itself. If the client stops reading the stream, WebFlux can cancel the subscription and Reactor cleans up timers/operators per its semantics.

**API design note:** The `GET /next` demo intentionally has a counter-increment side effect so subscriptions are easy to observe, **which does not fit HTTP safe-method semantics in a real service**. For state mutations, use POST/PUT with proper business contracts, authorization/idempotency, and transactions. If you do not want client caching/prefetching to alter counters, do not use GET for side effects outside demos.

### 18.4. Running the Demo

With the project's Maven wrapper:

```bash
./mvnw spring-boot:run
```

Windows PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

By default the server listens on port 8080 if `server.port` is uncustomized. The code above requires Spring Boot/Reactor/Jackson on the classpath; `javac SequenceController.java` alone **lacks** dependencies.

## 19. curl: Observing Subscriptions and Responses

### Each GET /next Produces a Result

```bash
curl -i 'http://localhost:8080/api/lifecycle/next'
curl -i 'http://localhost:8080/api/lifecycle/next'
```

If the app was just started and no competing requests hit `/next` or `/double`, JSON responses are respectively:

```json
{"value":1}
```

and:

```json
{"value":2}
```

The counter lives in a singleton service and resets on restart; **do not** conclude every environment or concurrent requests will always yield the exact 1, 2 sequence. If an HTTP client retries automatically, one user request can trigger multiple server-side subscriptions.

### Two Subscriptions in One /double Request

```bash
curl -i 'http://localhost:8080/api/lifecycle/double'
```

If the counter is currently 2 with no concurrent calls, the two `nextValue()` suppliers return 3 and 4; response:

```json
{"value":7}
```

`Mono.zip` only completes with a tuple when both sources emit a value; if one source is `Mono.empty()`, zip can complete empty and the other source may be cancelled. Do not use zip when you need to guarantee both side effects run even if one source is empty.

### Streaming Events

```bash
curl -N -i 'http://localhost:8080/api/lifecycle/stream/3'
```

SSE data (illustrative body):

```text
data:{"value":1}

data:{"value":2}

data:{"value":3}

```

The `-N` flag reduces curl buffering. Event timing depends on scheduler/network; do not treat the 80ms interval as a hard guarantee. One event does not necessarily correspond to one TCP packet.

### Empty Mono and Validation Errors

```bash
curl -i 'http://localhost:8080/api/lifecycle/empty'
curl -i 'http://localhost:8080/api/lifecycle/stream/100'
```

`/empty` returns an HTTP response with no JSON value; `/stream/100` emits a 400 error if the response has not yet committed. Error body formatting depends on Spring Boot/Problem Details configuration; do not hardcode JSON unless a custom error handler is defined.

## 20. StepVerifier: Accurately Testing Lifecycle in Reactor

With `reactor-test`, test subscription is triggered at `verify...()`, not when constructing the StepVerifier variable. File `src/test/java/com/example/demo/LifecycleTest.java`:

```java
package com.example.demo;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

class LifecycleTest {

    @Test
    void justCapturesBeforeSubscription() {
        AtomicInteger counter = new AtomicInteger();

        Mono<Integer> eager = Mono.just(counter.incrementAndGet());

        assertEquals(1, counter.get());
        StepVerifier.create(eager)
            .expectNext(1)
            .verifyComplete();
        StepVerifier.create(eager)
            .expectNext(1)
            .verifyComplete();
        assertEquals(1, counter.get());
    }

    @Test
    void deferFactoryRunsOnEverySubscription() {
        AtomicInteger counter = new AtomicInteger();

        Mono<Integer> lazy = Mono.defer(() ->
            Mono.just(counter.incrementAndGet()));

        assertEquals(0, counter.get());

        StepVerifier.create(lazy)
            .expectNext(1)
            .verifyComplete();
        StepVerifier.create(lazy)
            .expectNext(2)
            .verifyComplete();

        assertEquals(2, counter.get());
    }

    @Test
    void backpressureRequiresRequestForOnNext() {
        StepVerifier.create(Flux.range(1, 3), 0)
            .expectSubscription()
            .thenRequest(1)
            .expectNext(1)
            .thenRequest(2)
            .expectNext(2, 3)
            .verifyComplete();
    }

    @Test
    void emptyMonoCompletesWithoutValue() {
        StepVerifier.create(Mono.empty(), 0)
            .expectSubscription()
            .verifyComplete();
    }

    @Test
    void retryTriggersNewSourceSubscriptions() {
        AtomicInteger count = new AtomicInteger();

        Mono<String> eventual = Mono.defer(() -> {
            int attempt = count.incrementAndGet();
            if (attempt < 3) {
                return Mono.error(
                    new IllegalStateException("temporary"));
            }
            return Mono.just("ok");
        }).retry(2);

        StepVerifier.create(eventual)
            .expectNext("ok")
            .verifyComplete();

        assertEquals(3, count.get());
    }

    @Test
    void cancellationStopsFiniteSequence() {
        StepVerifier.create(Flux.range(1, 100), 0)
            .expectSubscription()
            .thenRequest(2)
            .expectNext(1, 2)
            .thenCancel()
            .verify();
    }

    @Test
    void timeoutPropagatesErrorWithVirtualTime() {
        StepVerifier.withVirtualTime(() ->
                Mono.never().timeout(Duration.ofSeconds(5)))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(5))
            .expectError(java.util.concurrent.TimeoutException.class)
            .verify();
    }
}
```

**These tests use no network** and assume no specific executor. `StepVerifier.withVirtualTime` requires publishers with time operators to be created **inside the supplier lambda** as shown; creating `Mono.delay` outside the lambda can break virtual-time tests. When verifying `doFinally` ran, remember the callback may execute after downstream termination, so synchronize tests properly instead of reading a boolean at an unguaranteed moment.

Calling `StepVerifier.create(publisher, 0)` followed immediately by `expectNext(...)` **without** `thenRequest(...)` causes a protocol-compliant source not to emit items; the test does not prove the source is broken. You need `expectSubscription` or an appropriate request step.

## 21. WebTestClient: Testing WebFlux HTTP from the Controller

File `src/test/java/com/example/demo/SequenceControllerTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class SequenceControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void nextProducesOneValue() {
        client.get().uri("/api/lifecycle/next")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.value").isNumber();
    }

    @Test
    void invalidStreamingCountReturns400() {
        client.get().uri("/api/lifecycle/stream/100")
            .exchange()
            .expectStatus().isBadRequest();
    }

    @Test
    void streamCompletesAfterThreeEvents() {
        Flux<String> response = client.get()
            .uri("/api/lifecycle/stream/3")
            .accept(MediaType.TEXT_EVENT_STREAM)
            .exchange()
            .expectStatus().isOk()
            .returnResult(String.class)
            .getResponseBody();

        StepVerifier.create(response)
            .expectNextMatches(s -> s.contains("\"value\":1"))
            .expectNextMatches(s -> s.contains("\"value\":2"))
            .expectNextMatches(s -> s.contains("\"value\":3"))
            .verifyComplete();
    }
}
```

**SSE codec caveat:** String decoding with `text/event-stream` depends on message readers and WebTestClient/Reactor Netty configuration; in real projects you can decode into `ServerSentEvent<ValueResponse>` or a DTO using an appropriate `ParameterizedTypeReference` if the codec does not return each event as a single String. Do not treat each TCP chunk as a Reactor element, and do not claim streaming always flushes at exact intervals.

**Test stability:** Do not assert exact counter values across multiple HTTP tests because singleton state can be shared across tests and JUnit runs in non-deterministic order. With Spring Security, tests require user/authorization/CSRF matching the endpoint. Mock WebTestClient and a real HTTP server differ on transport/disconnect behavior, so add integration tests to verify client cancellation.

Run:

```bash
./mvnw test
```

PowerShell:

```powershell
.\mvnw.cmd test
```

This is a runnable example in a Boot 3 project with matching dependencies; it is not a claim of having been executed in a user's workspace.

## 22. Side Effects, HTTP, WebClient, and Retries at the Right Boundary

### WebClient Mono Usually Does Not Send HTTP When Merely Constructed

Example:

```java
Mono<ProductDto> product = webClient.get()
    .uri("/products/{id}", id)
    .retrieve()
    .bodyToMono(ProductDto.class);
```

This is a snippet inside a class with `webClient`, `id`, and `ProductDto`. Constructing the `Mono` **typically has not sent the HTTP request yet**; the network exchange occurs when a subscriber subscribes. Calling `product.block()` twice or having two independent subscribers on a cold source can trigger **two outbound HTTP requests**, unless the source has different sharing/caching semantics.

In a WebFlux controller, **return this Mono to the framework**; do not `subscribe()` to “send the request early” and then return a different Mono.

### When Side Effects Must Run Exactly Once

Reactive Streams does not provide exactly-once mutation semantics. If a `POST`/payment pipeline involves:
- HTTP client retries,
- `retryWhen`,
- duplicate subscriptions,
- network timeouts after server commit,

then side effects can run again. You must have idempotency keys, transactions/outbox, uniqueness constraints, authorized ownership, and a retry policy. Caching a Mono in memory **does not replace** durable storage mechanisms for exactly-once behavior across pods/restarts.

### Do Not Mix Blocking Service Calls into Assembly

Wrong:

```java
@GetMapping("/bad")
public Mono<String> bad() {
    return Mono.just(jdbcService.fetch());
}
```

Here `jdbcService.fetch()` blocks immediately when the handler method runs. If integrating legacy JDBC is unavoidable:

```java
@GetMapping("/bridge")
public Mono<String> bridge() {
    return Mono.fromCallable(() -> jdbcService.fetch())
        .subscribeOn(Schedulers.boundedElastic());
}
```

These are **snippets** requiring the `jdbcService` bean and imports; to compile in a sample controller, add the corresponding dependencies and data service. `boundedElastic` only **moves** blocking work to bounded workers; it does not turn JDBC into a reactive driver or automatically solve connection pooling, timeouts, and cancellation.

## 23. Mistakes to Avoid

1. **“Declaring a Flux means running data”**: for cold sources, without subscribing no data is emitted yet.
2. **“Everything in Mono is lazy”**: the argument `Mono.just(expensiveCall())` already ran at assembly.
3. **“Subscribe always runs on another thread”**: synchronous sources like `Flux.range` can emit immediately on the same thread.
4. **“Subscribe without requesting still gets onNext”**: protocol-compliant publishers must wait for demand.
5. **“block() has no impact”**: it creates a new subscription, blocks the thread, and can repeat side effects.
6. **Manually subscribing inside a WebFlux controller**: loses response lifecycle/error/cancellation control.
7. **Reading resources in the controller before returning Mono**: can block the event loop.
8. **Using `Mono.just(null)`**: `onNext(null)` is invalid; use `Mono.empty`/`justOrEmpty`.
9. **Using `doOnNext` to send emails/payments**: can execute multiple times on retry or multi-subscribe.
10. **Assuming cold sources are automatically cached**: every subscription can re-run queries.
11. **Assuming `Mono.cache()` is safe for sensitive user data**: requires keys, TTL, auth, and invalidation.
12. **Using `retry` with non-idempotent POSTs**: can create duplicate records/charges.
13. **Assuming `onErrorResume` resumes upstream after `onError`**: it actually switches to a fallback publisher.
14. **Assuming `take(3)` always sends complete upstream**: it typically cancels upstream after taking enough items.
15. **Cleaning up only in `doOnComplete`**: misses errors and cancellation.
16. **Assuming `doFinally` already ran before downstream sees completion**: callbacks often run after terminal propagation.
17. **Calling `Subscription.request(0)` to pause**: violates the protocol.
18. **Expecting `request(1)` at pipeline end = `request(1)` at the database**: operators prefetch/reshape demand.
19. **Using `ThreadLocal` as request context across any scheduler**: Reactor Context has its own semantics.
20. **Assuming cancel rolls back side effects**: resources/tasks may already be committed.
21. **Putting a hot source in a pipeline and assuming every subscriber sees history**: replay must be configured.
22. **Leaving hot-source buffers unbounded**: risks OOM.
23. **Using `StepVerifier` with `initialRequest=0` and immediately calling `expectNext`**: the test stalls due to zero demand.
24. **Creating timed sources outside the `withVirtualTime` lambda**: prevents proper virtual scheduler control.
25. **Hardcoding thread order/names when `publishOn` is used**: scheduler semantics need controlled testing.
26. **Calling `block` in the WebFlux event loop**: causes thread starvation or Reactor `NonBlockingThread` exceptions.
27. **Not releasing files/connections on client disconnect**: causes leaks.
28. **Testing only the happy path without no-value/error/cancel**: misses terminal lifecycle behavior.
29. **Using GET with mutating side effects to model real APIs**: violates safe-method/retry/cache expectations.
30. **Thinking the HTTP response is finished as soon as the controller returns Mono**: it finishes when the publisher terminates and the writer flushes.
31. **Taking a Reactive Repository Mono and calling subscribe in a service**: breaks transaction/retry/error tracing from the caller.
32. **Collapsing all errors into `Mono.empty`**: loses failure reasons; keep 404/no-value distinct from outages.
33. **Ignoring cancellation on long-lived SSE connections**: holds timers/broker subscriptions unnecessarily.
34. **Believing `Mono.fromCallable` is non-blocking**: the Callable can still block the thread it runs on.
35. **Assuming every subscription to a hot publisher creates a new HTTP request**: hot/shared semantics depend on the implementation.

## 24. Checklist for Code Review and Production

### Building Pipelines and Subscribing

- [ ] Are all calls with side effects at assembly time clearly identified?
- [ ] Does `Mono.just(...)` only receive already-computed values without accidentally wrapping a blocking call?
- [ ] When per-subscription evaluation is needed, are `defer`/`fromSupplier`/`fromCallable` used properly?
- [ ] Do you know whether a publisher is cold/hot/shared/cached before creating multiple subscriptions?
- [ ] Are sources with per-subscription mutable state created in the right place (`defer` if needed)?
- [ ] Do WebFlux controllers return Mono/Flux without calling `subscribe`/`block`?
- [ ] Do genuinely independent background jobs have dedicated executors/queues/monitoring?

### Signals, Errors, Cancel, Cleanup

- [ ] Are terminal callbacks prevented from firing twice?
- [ ] Is `request(n)` positive and demand never exceeded?
- [ ] Do `flatMap`/`buffer`/`publishOn` operators have resource/concurrency/prefetch budgets?
- [ ] Do `retry`/`repeat` have error classification, backoff, and idempotency?
- [ ] Does cleanup cover completion, error, **and cancellation** paths?
- [ ] Are `using`/`usingWhen` used when owning connection/file resources?
- [ ] Are event/broker subscriptions cleaned up on client disconnect?
- [ ] Is cancellation never mistaken for transaction rollback?
- [ ] Are Reactor Context/security/tracing preserved across the publisher chain?

### Testing

- [ ] Do tests distinguish eager `just` from lazy `fromSupplier`/`defer`?
- [ ] Do tests verify how many times two subscriptions invoke a supplier?
- [ ] Are initial demand 0, `thenRequest`, and `thenCancel` tested?
- [ ] Are `Mono.empty`, `onError`, fallbacks, and retry resubscriptions tested?
- [ ] Are timeouts tested with `withVirtualTime` and a lazy publisher supplier?
- [ ] Are SSE/JSON HTTP endpoints tested via `WebTestClient`/`curl` matching their lifecycle?
- [ ] Are tests free of fragile assertions on timers or hardcoded scheduler thread names?
- [ ] Is HTTP client disconnect integration-tested for long-lived streaming APIs?
- [ ] Is private data prevented from being cached/replayed across users/tenants?

## 25. Self-Check Questions

**1.** When `Mono.just(service.load())` is created, when does `service.load()` run?

**Answer:** Immediately at assembly when evaluating the argument before calling `just`; it does not wait for subscribe.

**2.** When `Mono.fromSupplier(service::load)` is created, when does the method run?

**Answer:** When subscribed and the source is executed; each subscription normally invokes the supplier again.

**3.** How does `Mono.defer(...)` differ from `fromSupplier(...)`?

**Answer:** `defer` takes a factory creating a new Publisher per subscription; `fromSupplier` takes a factory producing one value.

**4.** What type does `publisher.subscribe(subscriber)` return per the Reactive Streams JVM spec?

**Answer:** `void`; the Subscription arrives via `subscriber.onSubscribe(subscription)`. Some Reactor `subscribe` overloads return `Disposable`.

**5.** Does merely subscribing without requesting guarantee receiving `onNext`?

**Answer:** No; a publisher may only emit `onNext` when demand exists, though it can emit `onComplete`/`onError` without demand.

**6.** Why can calling `mono.block()` twice send two outbound HTTP requests?

**Answer:** Each `block` creates a new subscription. If a cold source like a WebClient body Mono is not cached/shared, each subscription can trigger a new exchange.

**7.** Is `doOnSuccess(null)` Reactor emitting `onNext(null)`?

**Answer:** No; the hook uses null to indicate the Mono completed empty. `onNext(null)` is forbidden.

**8.** When `Flux.take(3)` receives three items, what does upstream usually receive?

**Answer:** Upstream cancellation; downstream receives completion, and the two boundaries can observe different `doFinally` signal types.

**9.** Which termination paths does `doFinally` handle?

**Answer:** Complete, error, and cancel. Cleanup may run after the terminal signal has reached downstream; for resource ownership consider `using`/`usingWhen`.

**10.** Should you run `repository.save(...).subscribe()` in a controller and return `Mono.empty()`?

**Answer:** No. That creates fire-and-forget work outside the HTTP lifecycle, losing propagated errors/cancellations/tracing. Return the publisher for the framework to manage.

**11.** Does `retry(2)` merely “resume” a failed Subscription?

**Answer:** No; it typically re-subscribes upstream up to two more times, which can re-run side effects.

**12.** Is a `Flux` guaranteed to be cold and replay everything for a late subscriber?

**Answer:** No. Hot/shared sources may not replay; cache/replay have separate policies.

**13.** Does `subscribeOn(boundedElastic)` turn JDBC into a non-blocking driver?

**Answer:** No. It moves blocking calls to a worker pool; JDBC itself remains blocking.

**14.** When a WebFlux handler returns a Mono without subscribing itself, who subscribes?

**Answer:** Spring WebFlux HTTP infrastructure, to manage response writing and cancellation.

**15.** Is Reactor Context a global `ThreadLocal`?

**Answer:** No. It is attached to the Subscriber chain and propagated by protocol/scheduling rules, unlike ordinary thread-local variables.

## 26. References

- Project Reactor reference — Reactor Core, building and subscribing: https://projectreactor.io/docs/core/release/reference/
- Reactor — Simple ways to create a Flux/Mono and subscribe: https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html
- Reactor — Which operator do I need? `defer`, `fromCallable`, `just`: https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html
- Reactor Core API — `Mono`, `doFirst`/`doFinally`/`doOnSuccess`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Reactor Core API — `Flux`, `using`/`usingWhen` and lifecycle: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Reactor — Testing with `StepVerifier`: https://projectreactor.io/docs/core/release/reference/testing.html
- Reactor Test API — `StepVerifier.withVirtualTime`: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html
- Reactor — Schedulers and threading: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
- Reactor — Adding a Context: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Spring Framework — WebFlux overview/non-blocking principles: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Spring Framework — WebFlux annotated controllers: https://docs.spring.io/spring-framework/reference/web/webflux/controller.html
- Spring Framework — WebFlux return values: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html
- Spring Framework — WebTestClient: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Reactive Streams JVM specification and TCK: https://github.com/reactive-streams/reactive-streams-jvm
- Java 17 — Flow API and reactive streams: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.html
