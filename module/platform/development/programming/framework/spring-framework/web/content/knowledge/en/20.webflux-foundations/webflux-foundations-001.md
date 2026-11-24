# Reactive Streams: Publisher, Subscriber, and Subscription in Spring WebFlux

## 1. Objectives and Scope

A WebFlux application can receive, process, and return asynchronous data streams without having to dedicate a separate thread just to wait for I/O. Behind `Mono`, `Flux`, and most reactive pipelines in WebFlux lies **Reactive Streams**, a small protocol enabling a data producer and a data consumer to exchange signals with **backpressure** — the ability of the receiver to control demand for elements.

This lesson accurately explains the nature of the three interfaces `Publisher<T>`, `Subscriber<T>`, and `Subscription`; progressing from signal sequencing, `request(n)`, and `cancel()` to examples in Java 17, Project Reactor, and Spring WebFlux. The content is conceptually compatible with **Spring Framework 6.x, Spring Boot 3.x, Java 17+**, focusing on JVM Reactive Streams foundations and the reactive HTTP stack.

After studying this lesson, you will be able to:

- State precisely the roles of Publisher, Subscriber, and Subscription and distinguish them from HTTP requests/controllers.
- Diagram the sequence `onSubscribe → onNext* → (onError | onComplete)?`; know when a stream terminates or is cancelled.
- Analyze positive `request(n)`, cumulative demand, `Long.MAX_VALUE`, and the invariant of never emitting beyond demand.
- Explain why `request(0)`/`request(-1)` violate the contract, and why `cancel` does not guarantee immediate stopping.
- Understand that backpressure **is not synonymous with** non-blocking, async, automatic thread creation, unbounded queues, or pausing hot sources.
- Use Reactor `Flux`/`Mono`, `BaseSubscriber`, `StepVerifier`, and operators `map`/`filter`/`flatMap`/`publishOn`/`subscribeOn` with accurate expectations.
- Write a concise WebFlux application with `Flux`/`Mono` and HTTP streaming; know not to manually call `subscribe()` inside a controller to produce a response.
- Test signals, demand, cancellation, errors, terminal signals, and the HTTP boundary using `curl`/`WebTestClient`.

**Do not confuse WebFlux with Spring MVC async.** MVC can also return certain reactive types, but it handles HTTP through the Servlet stack; WebFlux is built on the reactive contract and non-blocking I/O. Not every dependency inside a pipeline automatically becomes non-blocking: calling JDBC or `Thread.sleep` on an event loop can still block.

## 2. Why Were Reactive Streams Created?

In the synchronous pull model, the consumer calls `iterator.next()` when ready; the producer does not push infinitely. With asynchronous push, a producer can be faster than a consumer:

```text
Publisher:  100,000 events/second
       |
       v
Unbounded buffer: grow -> GC pressure -> OOM
       |
       v
Subscriber: 100 events/second
```

Reactive Streams defines a **contract point** so the subscriber sends demand `request(n)` and the publisher does not emit `onNext` beyond the total demand received. A slow consumer can request a few elements first and only request more after finishing processing.

```text
Subscriber                            Publisher
    |                                     |
    |  subscribe(...)                     |
    |------------------------------------>|
    |  onSubscribe(subscription)          |
    |<------------------------------------|
    |  subscription.request(2)            |
    |------------------------------------>|
    |  onNext(A)                          |
    |<------------------------------------|
    |  onNext(B)                          |
    |<------------------------------------|
    |  [no demand yet for C]              |
    |  subscription.request(1)            |
    |------------------------------------>|
    |  onNext(C)                          |
    |<------------------------------------|
    |  onComplete()                       |
    |<------------------------------------|
```

The model above is a **logical protocol**; it does not guarantee that each request corresponds to one network packet, that each element runs on a separate thread, or that each `request(n)` must emit all n elements. A Publisher may emit fewer and complete, error, or wait for I/O. Conversely, `onError`/`onComplete` can arrive **without requiring demand**.

Reactive Streams focuses on four principles: handling potentially asynchronous data, propagating demand upstream from the consumer, delivering signals in order, and not forcing the consumer to maintain an unbounded queue. The specification does not automatically create CPU scheduling, quotas, or database backpressure mechanisms for you.

## 3. Four Core Interfaces in the JVM Specification

Reactive Streams JVM defines the `org.reactivestreams` interfaces:

```java
public interface Publisher<T> {
    void subscribe(Subscriber<? super T> subscriber);
}

public interface Subscriber<T> {
    void onSubscribe(Subscription subscription);
    void onNext(T element);
    void onError(Throwable error);
    void onComplete();
}

public interface Subscription {
    void request(long n);
    void cancel();
}

public interface Processor<T, R>
        extends Subscriber<T>, Publisher<R> {
}
```

This is a **transcript of the API signatures for learning**, not a source file to add to a project: `org.reactivestreams` is already provided by the library. Do not redefine duplicate packages/interfaces in your project.

| Component | Primary Responsibility | Example |
| --- | --- | --- |
| `Publisher<T>` | Supplies elements of type T to a subscriber following the protocol | Reactor `Flux`/`Mono` |
| `Subscriber<T>` | Receives signals, decides demand, and processes data/errors | `BaseSubscriber<T>` |
| `Subscription` | Binds **one Publisher–Subscriber relationship**, controls `request`/`cancel` | Object passed via `onSubscribe` |
| `Processor<T,R>` | Simultaneously receives from upstream and emits downstream; can transform T into R | Foundation for some operators, though not every operator is an exposed Processor object |

**Key point:** `Publisher.subscribe(...)` returns `void` per the spec; `Subscription` arrives at the subscriber via `onSubscribe(subscription)`. In Reactor, several convenience overloads of `Flux.subscribe(...)` return `Disposable` for easy cancellation; do not confuse Reactor convenience APIs with the standard Reactive Streams signature.

`Publisher` is not where you specify how many elements you want *before subscribing*. Demand is communicated through the corresponding `Subscription` after `onSubscribe`.

## 4. Publisher: Demand-Driven Signal Source

`Publisher<T>` is responsible for accepting a subscriber via `subscribe(Subscriber<? super T>)`, providing a `Subscription`, and emitting signals according to the protocol.

Important rules:

1. The number of `onNext` signals emitted **must never exceed** the total demand accepted on the subscription.
2. A Publisher **may emit fewer** than requested and terminate with `onComplete` or `onError`.
3. Signals to a subscriber must be **serialized**; never concurrently invoke two `onNext`/terminal callbacks out of order.
4. `onSubscribe` is always sent **before** `onNext`, `onError`, or `onComplete` (for a non-null subscriber).
5. After a terminal signal `onComplete` or `onError`, no further `onNext` or second terminal signal may be emitted.
6. After `cancel`, the Publisher must **eventually stop** sending signals; stopping may be delayed due to signals already in flight in the pipeline.
7. A Publisher may support multiple subscribers, multicast, or unicast; the spec **does not require** every publisher to be cold/replayable.

Reactor example:

```java
Flux<Integer> numbers = Flux.range(1, 3);
```

`Flux.range` is a finite source. **Creating the `numbers` variable does not mean a consumption pipeline has run**; signals are typically triggered when a subscriber subscribes. However, do not assume “every piece of code in a Flux-creation expression is lazy,” because computations in arguments to `just(...)` can execute immediately when creating the object.

### Publishers and Unbounded Data

`Flux.interval`, event buses, log tailing, WebSocket, or SSE can emit data long-term. Bounded subscriber demand does not automatically throttle a real-world source (devices, message brokers) if the source does not support pausing. In that case, an adapter must choose a bounded buffer policy, drop/sampling, failing, or limiting upstream via a separate mechanism. You cannot turn an infinitely pushing device into a backpressure-aware source merely by wrapping it in the word `Flux`.

## 5. Subscriber: Receiver and Demand Decision-Maker

A `Subscriber<T>` implements four callbacks:

| Callback | When Called | Responsibility |
| --- | --- | --- |
| `onSubscribe(Subscription)` | Once when establishing the subscription | Store the subscription, decide `request(n)` or `cancel()` |
| `onNext(T)` | When an element is delivered according to demand | Consume the element, optionally request more |
| `onError(Throwable)` | Stream terminates with an error | Cleanup, report error; **terminal** |
| `onComplete()` | Finite stream finishes successfully | Cleanup/completion; **terminal** |

A subscriber **must send demand** via `request(n)` to receive `onNext`. However, `onError` and `onComplete` can occur even before any request is made. Signals must always follow a valid order.

**Do not arbitrarily reuse the same subscriber instance across multiple subscriptions by default**: Reactive Streams requires that a Publisher can be subscribed to multiple times with **different Subscriber instances**, while a publisher is entitled to decide unicast/multicast behavior and may reject unsupported subscriptions per the protocol. Do not call `subscribe` again with the same active Subscriber instance and expect the framework to make it safe automatically.

In a manual implementation, receiving another `onSubscribe` when a subscription already exists must cancel the subsequent subscription per spec rules. For most WebFlux business code, use Reactor operators and `BaseSubscriber` when custom demand is needed instead of writing a raw Subscriber yourself.

## 6. Subscription: Bridge and Control Handle

A `Subscription` is bound exclusively to one Publisher–Subscriber relationship:

```java
subscription.request(5);
subscription.request(2);
subscription.cancel();
```

- `request(5)` grants permission to emit **at most 5 elements**.
- `request(2)` adds **2 more elements**, rather than resetting demand to 2.
- Each `onNext` emitted consumes one unit of demand.
- `cancel()` requests stopping emissions and releasing resources when possible.
- After cancel, subsequent `request`/`cancel` calls on the subscription must be no-ops per the spec.
- `request` and `cancel` must be handled thread-safely/serialized per the contract; a subscriber must not arbitrarily invoke these two methods concurrently without coordination.
- Request/cancel is not a promise that data will be produced or I/O will cease immediately.

Suppose:

```text
Initial outstanding demand = 0
request(3) -> outstanding = 3
onNext(A)  -> outstanding = 2
onNext(B)  -> outstanding = 1
request(2) -> outstanding = 3
onNext(C)  -> outstanding = 2
onNext(D)  -> outstanding = 1
onNext(E)  -> outstanding = 0
```

At every point `emitted <= total requested`. A finite source can call `onComplete` when data is exhausted; the completion signal does not consume a “data element” the way `onNext` consumes demand.

### request(0) and request(-1) Are Invalid

Per Subscription rule 3.9: on an uncancelled subscription, `request(n)` with `n <= 0` is a protocol violation and **must signal `onError` with `IllegalArgumentException`**, rather than being treated as a normal “pause”. Do not use `request(0)` to wait; simply **do not request more yet**, or proactively cancel if you no longer need the stream.

### Long.MAX_VALUE and Accumulating Demand

`request(Long.MAX_VALUE)` may be treated as **effectively unbounded demand**. Implementations must withstand multiple requests without overflowing the `long` counter into negative numbers; Reactor typically uses demand addition capped at `Long.MAX_VALUE`. This does not mean “the publisher will generate infinite data”: a finite source can still complete, error, or emit no data.

Reactor convenience `subscribe()` overloads typically request unbounded demand. If your goal is to study backpressure, use `BaseSubscriber`/`StepVerifier` with controlled demand instead of just writing `flux.subscribe(System.out::println)` and claiming you tested requesting one element at a time.

## 7. Protocol Signals: Valid and Invalid Sequences

Abstract form:

```text
onSubscribe → onNext* → (onError | onComplete)?
```

The `*` = 0 or more `onNext`; `?` = 0 or 1 terminal signal. Having no terminal signal is possible when a stream is infinite, the source has not finished, or the subscription is cancelled.

| Sequence | Valid? | Why |
| --- | --- | --- |
| `onSubscribe → onNext(A) → onComplete` | Yes, if demand ≥1 | Finite stream |
| `onSubscribe → onComplete` | Yes | Empty stream can complete without a request |
| `onSubscribe → onError(ex)` | Yes | Error can arrive before onNext, without a request |
| `onSubscribe → onNext(A) → onNext(B)` | Yes if sufficient demand and not terminated | Stream still active |
| `onNext(A) → onSubscribe` | No | Missing onSubscribe before data |
| `onSubscribe → onNext(A)` when demand=0 | No | Exceeded demand |
| `onSubscribe → onComplete → onNext(A)` | No | Signal after terminal |
| `onSubscribe → onError(x) → onComplete` | No | Two terminal signals |
| Two concurrent `onNext` calls to one Subscriber | No | Signals must be serialized |

“Serialized” **does not require all callbacks to run on the same Thread**. They can arrive from different threads if synchronized to establish a happens-before relationship and avoid overlap. Do not casually share mutable state across callbacks without considering thread handoff, even though the protocol preserves signal ordering to the subscriber.

### Why Is null Not a Valid Element?

Reactive Streams forbids `onNext(null)`; null breaks the contract and could ambiguously represent “no data”. Use `Mono.empty()` to represent completion without a value, emit `Optional<T>` as a non-null object if the API contract fits, or design an explicit domain type.

In Reactor, `Mono.just(null)` is invalid, while `Mono.justOrEmpty(nullable)` can create an empty Mono when the value is null. A source with no elements can still complete with `onComplete`.

## 8. Backpressure Is Pull-Controlled Delivery, Not Backpressure Everywhere

The subscriber controls demand, but three levels must be distinguished:

1. **Reactive Streams demand:** the number of `onNext` signals the Publisher is allowed to send to the Subscriber.
2. **Operator demand:** operators may request **more** from upstream to implement `buffer`, `flatMap`, or prefetching.
3. **Transport/storage backpressure:** TCP flow control, file/network buffering, database drivers, and message brokers have their own mechanisms.

A final subscriber calling `request(1)` does not guarantee that **only one database row is read**, or only one network packet is received. `flatMap` may subscribe to multiple inner publishers and prefetch; `buffer(10)` may request 10 upstream items to produce one `List<T>` downstream. That does not violate the spec as long as each boundary sends no more than the demand on its boundary.

Example:

```text
Final Subscriber: request(1) List
          |
          v
Flux.buffer(10): request(10) items upstream
          |
          v
Source: emits 10 items -> buffer returns one List
```

Memory control is not solved just by “using Flux”. Choose appropriate `prefetch`, concurrency, bounded buffers, rate/size limits, timeouts, and resource ownership.

### When the Source Cannot Slow Down

With a hot event bus that does not support pausing, the adapter must define:

- Bounded buffers and full-buffer handling.
- Drop/sampling with clear observability.
- Failing/closing the connection when the consumer is too slow.
- Using a broker with ack/credits/pause-consumer if supported.

Reactor options such as `onBackpressureBuffer`, `onBackpressureDrop`, and `onBackpressureLatest` must be used intentionally, understanding data loss and memory footprint. **An unbounded buffer is not a safe backpressure solution.**

## 9. Cold Publisher and Hot Publisher

The Reactive Streams specification **does not mandate** whether a Publisher is cold or hot. This is a property of how the source is designed:

**Cold:** each subscription can start its own independent sequence; `Flux.range(1,3)` is an example. If a cold source makes an HTTP/DB call on subscribe, two subscriptions can trigger the work twice.

**Hot:** data is emitted over time and can be shared across subscribers. A late subscriber may miss earlier events; the backpressure policy depends on the source. Reactor `Sinks.Many` is a tool for creating a hot signal source (with variants and overflow policies).

```text
Cold source A:  subscribe1 -> 1 2 3 (separate)
                subscribe2 -> 1 2 3 (separate)

Hot broadcast:  time ------  A B C D E F --->
                sub1          ^ B C D E F
                sub2              ^ D E F
```

Illustrative diagram: a replaying hot source can replay history based on configuration; not every hot publisher drops old data. WebFlux does not automatically guarantee that a browser reconnecting to SSE will receive all missed events; you need replay IDs, broker retention, and an explicit reconnect policy.

### Creating a Flux Does Not Mean Everything Is Lazy

```java
String value = compute();       // Runs IMMEDIATELY.
Mono<String> eager = Mono.just(value);

Mono<String> lazy = Mono.defer(
        () -> Mono.just(compute())); // Runs on subscribe.
```

This is a snippet inside a class that has a `compute()` method. If you call `Mono.just(expensiveServiceCall())`, the argument call runs immediately when constructing the pipeline. Use `Mono.defer(...)` or `Mono.fromCallable(...)` when you need to defer data creation, and you must evaluate whether the work is blocking vs. non-blocking.

## 10. Reactor: Flux, Mono, and Utility Subscribers

Project Reactor is the reactive library used by Spring WebFlux:

| Type | Valid Element Count | Some Factories |
| --- | --- | --- |
| `Mono<T>` | 0 or 1 then terminal | `just`, `empty`, `error`, `fromCallable`, `defer` |
| `Flux<T>` | 0..N then terminal or unending stream | `just`, `range`, `fromIterable`, `interval`, `defer` |
| `BaseSubscriber<T>` | Helper for writing a Subscriber with `request/cancel` control | Hooks `hookOnSubscribe`, `hookOnNext` |
| `StepVerifier` | Test signals and demand by scenario | `expectNext`, `thenRequest`, `verifyComplete` |

`Flux<T>` and `Mono<T>` implement the required reactive contracts; when returned from a WebFlux handler, the framework subscribes and manages the response lifecycle for you.

Several `Flux.subscribe(...)` overloads are convenience terminal operations: **by default they usually request unbounded demand**, especially `subscribe()` and standard lambda overloads. Do not confuse them with implementing a custom `Subscriber` that receives a `Subscription`.

**Important point:** `Mono` has at most one `onNext`, but that does not mean Mono has no demand or is always synchronous. `Mono.error(...)`/`Mono.empty()` can send a terminal signal without emitting a value. A Mono can also perform asynchronous network I/O.

## 11. Standalone Java 17: Flow API Closely Matches Reactive Streams

Java 9+ provides `java.util.concurrent.Flow` with `Publisher`, `Subscriber`, `Subscription`, and `Processor` **similar in design** to `org.reactivestreams`. These are **two distinct sets of Java interfaces in different packages**, not the same object to cast directly. When integrating them, you need an appropriate adapter, such as `reactor.adapter.JdkFlowAdapter` (`reactor-adapter` dependency depending on the project).

To observe callbacks in **standard Java 17 without Maven**, use `SubmissionPublisher`:

File `FlowDemandDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;

public class FlowDemandDemo {

    public static void main(String[] args) throws Exception {
        CountDownLatch finished = new CountDownLatch(1);

        try (SubmissionPublisher<String> publisher =
                     new SubmissionPublisher<>()) {

            publisher.subscribe(new Flow.Subscriber<String>() {
                private Flow.Subscription subscription;

                @Override
                public void onSubscribe(Flow.Subscription s) {
                    this.subscription = s;
                    System.out.println("onSubscribe");
                    s.request(1);
                }

                @Override
                public void onNext(String item) {
                    System.out.println("onNext=" + item);
                    subscription.request(1);
                }

                @Override
                public void onError(Throwable throwable) {
                    System.out.println("onError=" +
                            throwable.getClass().getSimpleName());
                    finished.countDown();
                }

                @Override
                public void onComplete() {
                    System.out.println("onComplete");
                    finished.countDown();
                }
            });

            publisher.submit("A");
            publisher.submit("B");
            publisher.close();

            if (!finished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "No terminal signal before timeout");
            }
        }
    }
}
```

Commands:

```bash
javac FlowDemandDemo.java
java FlowDemandDemo
```

Stdout when the program completes normally:

```text
onSubscribe
onNext=A
onNext=B
onComplete
```

`CountDownLatch` waits for the terminal signal so the main thread does not exit before the callback. `SubmissionPublisher` can **buffer** data and run callbacks asynchronously via an executor; the two `submit` calls do not have to wait for each `request(1)`. It is the `Subscription` that limits **delivering `onNext` to the subscriber**, not necessarily blocking the producer from creating/buffering data immediately. Real projects need to choose bounded buffers and overload policies.

Technical note: This example uses `Flow` to illustrate the protocol on plain JDK. With WebFlux, continue using Reactor `Flux`/`Mono`; do not cast `Flow.Publisher` to `org.reactivestreams.Publisher` without an adapter.

## 12. Reactor Demo: Controlling Element-by-Element with BaseSubscriber

In a Maven project with Reactor Core (provided by the Spring Boot WebFlux starter), create:

File `src/main/java/com/example/demo/DemandDemo.java`:

```java
package com.example.demo;

import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public class DemandDemo {

    public static void main(String[] args) {
        Flux.range(1, 5)
            .subscribe(new BaseSubscriber<Integer>() {
                private int received;

                @Override
                protected void hookOnSubscribe(
                        Subscription subscription) {
                    System.out.println("subscribed");
                    request(1);
                }

                @Override
                protected void hookOnNext(Integer value) {
                    System.out.println("next=" + value);
                    received++;

                    if (received == 3) {
                        System.out.println("cancel");
                        cancel();
                    } else {
                        request(1);
                    }
                }

                @Override
                protected void hookOnComplete() {
                    System.out.println("complete");
                }
            });
    }
}
```

To run this class on the Maven dependencies classpath, use the IDE “Run main” or configure an appropriate Maven exec plugin. Running `javac` directly without Reactor jars **will not compile** the code. This code is a complete Java class meant to run inside a Spring WebFlux Maven project with the Reactor dependency.

Stdout for the synchronous `Flux.range` in the example:

```text
subscribed
next=1
next=2
next=3
cancel
```

There is no `complete` because the subscriber proactively cancels after the third element. `BaseSubscriber` manages reentrant requests in accordance with the Reactor contract. If changed so the subscriber requests all five elements without cancelling, `Flux.range` can emit `onComplete` after the last element.

**Observation:** `request(1)` is called right inside the hook, and data can arrive synchronously on the current thread. Reactive Streams does not force asynchronous execution; “reactive” describes the signal and demand protocol, and does not spawn threads on its own.

## 13. StepVerifier: Controlling Demand in Tests

Reactor provides `reactor-test` and `StepVerifier`. Add the test-scope dependency `io.projectreactor:reactor-test` if the project does not already pull it in. Example testing a finite source:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class ReactiveDemandTest {

    @Test
    void doesNotEmitMoreThanInitialDemand() {
        StepVerifier.create(Flux.range(1, 3), 0)
            .expectSubscription()
            .thenRequest(2)
            .expectNext(1, 2)
            .thenRequest(1)
            .expectNext(3)
            .verifyComplete();
    }

    @Test
    void aFluxCanBeCancelledBeforeCompletion() {
        StepVerifier.create(Flux.range(1, 10), 0)
            .expectSubscription()
            .thenRequest(1)
            .expectNext(1)
            .thenCancel()
            .verify();
    }

    @Test
    void emptyMonoCompletesWithoutOnNext() {
        StepVerifier.create(
                reactor.core.publisher.Mono.empty(), 0)
            .expectSubscription()
            .verifyComplete();
    }

    @Test
    void errorIsTerminal() {
        StepVerifier.create(
                Flux.error(new IllegalStateException("boom")))
            .expectErrorMessage("boom")
            .verify();
    }
}
```

This is a JUnit 5 class that can run in a Spring Boot project when `spring-boot-starter-test`/`reactor-test` is on the test classpath. The tests above do not assume scheduler timing or real time; `Flux.range` emits elements synchronously matching demand, while `Mono.empty` can complete even with request=0.

**Do not write** `StepVerifier.create(Flux.range(1,3), 0).expectNext(1)` right after subscription without `thenRequest(...)`: a spec-compliant source will not emit a value, and the test may hang/timeout. Do not confuse checking for “no value” with `expectNoEvent(...)` when waiting without appropriate scheduling.

For timer-based sources, `StepVerifier.withVirtualTime` can be used where appropriate to avoid slow or timing-flaky tests. However, when the primary test target is the request/cancel protocol, a `range` source and explicit demand are usually clearer.

## 14. Is Writing a Compliant Publisher Hard?

Yes. A compliant `Publisher` must handle:

- `subscribe(null)` and the proper error reporting path.
- `onSubscribe` exactly once, before any other signal.
- Valid `request(n)`, safe accumulation, and `Long.MAX_VALUE` saturation.
- `request(n<=0)` signaling `onError(IllegalArgumentException)` per the spec; not merely throwing from `request`.
- Serializing signals and avoiding infinite recursion/stack overflow from reentrant `onNext → request → onNext`.
- Respecting eventual cancellation and cleaning up references.
- Never emitting null, never emitting after terminal, and never sending two terminal signals.
- Races among `request`, `cancel`, emitting values, errors, and completion across multiple threads.
- If there is no data, being able to complete/error immediately; if the source is slow, never spin-waiting on an event loop.

Do not write a Publisher simply by doing:

```java
subscriber.onSubscribe(subscription);
for (T item : items) {
    subscriber.onNext(item); // WRONG: does not check request(n).
}
subscriber.onComplete();
```

This is a **counterexample**, not a compilable file; variables `subscriber`/`subscription`/`items` are illustrative only. It violates demand rules when the subscriber has not yet requested.

Instead of implementing the protocol yourself, use `Flux.fromIterable`, `Flux.generate` (when synchronous stateful generation fits), or `Flux.create`/`Sinks.Many` following Reactor guidelines, and read overflow/backpressure semantics carefully. When building a new integration Publisher yourself, use the **Reactive Streams Technology Compatibility Kit (TCK)** to verify protocol compliance.

## 15. Operators Can Reshape Demand

Example:

```java
Flux.range(1, 100)
    .filter(n -> n % 2 == 0)
    .buffer(5)
    .take(2);
```

Operators do not merely transform values; they also form Publisher–Subscriber relationships inside the pipeline.

- `map` typically maintains a one-in/one-out ratio for each successfully emitted item.
- `filter` may need more upstream items than downstream demand because some items are dropped.
- `buffer(5)` needs up to 5 input elements to produce one output list.
- `flatMap` can subscribe to multiple publishers concurrently, prefetch, and interleave results; `concurrency`/`prefetch` should be bounded.
- `concatMap` preserves the order of multiple inner streams differently, with its own throughput/queue cost.
- `publishOn` shifts processing to another scheduler and introduces a queue/prefetch boundary.
- `limitRate` helps shape how upstream requests are batched, and **does not** automatically limit CPU/memory of every downstream stage.
- `take(n)` typically cancels upstream once n elements have been taken, though cancellation can arrive with a delay.

**Do not expect every `request(1)` on the terminal subscriber to match exactly one `doOnRequest(1)` at the source** when intermediate operators reshape requests. Place `doOnRequest` at appropriate points to observe actual demand at each boundary.

```java
Flux.range(1, 20)
    .doOnRequest(n -> System.out.println("source demand=" + n))
    .buffer(5)
    .doOnRequest(n -> System.out.println("list demand=" + n))
    .take(2);
```

This is an illustrative pipeline; since it is not subscribed to, there is no stdout. When subscribed, the exact sequence/count of requests depends on each operator and Reactor version. Do not hardcode a log sequence in documentation without appropriate tests.

## 16. Schedulers and Threads: subscribeOn, publishOn

Reactive Streams **does not mandate a specific thread model**. Sources like `Flux.range` are typically synchronous, whereas `WebClient`/Reactor Netty produce signals from asynchronous I/O event loops. Reactor provides `Scheduler` to switch execution contexts when needed.

| Operator | General Meaning |
| --- | --- |
| `subscribeOn(scheduler)` | Affects where subscription/request/upstream work starts; relative placement has specific rules |
| `publishOn(scheduler)` | Switches downstream stages after it to a worker from the scheduler, until another boundary |
| `Schedulers.parallel()` | Pool optimized for short CPU-bound work, not for long blocking tasks |
| `Schedulers.boundedElastic()` | Bounded pool intended for legacy blocking tasks when integration is unavoidable |
| `delayElements(...)` | Introduces an asynchronous time boundary and scheduling for each emitted item |

Legacy blocking call example:

```java
Mono<String> value = Mono.fromCallable(
        () -> legacyJdbcService.fetchText())
    .subscribeOn(Schedulers.boundedElastic());
```

This is a snippet inside a class with `legacyJdbcService` and imports `reactor.core.publisher.Mono`, `reactor.core.scheduler.Schedulers`. It helps **offload the blocking call from the event loop**, yet JDBC remains blocking and still uses connections and boundedElastic workers. Do not interpret “wrapping JDBC in a Mono” as turning it into a reactive database driver.

**Do not call `block()` inside a WebFlux handler/event-loop thread**; it can stall the pipeline, and Reactor can throw an error when blocking on a non-blocking thread. At synchronous application boundaries (CLI, tests), `block()` can be reasonable in a controlled way, but do not use it to break an end-to-end reactive chain inside a handler.

## 17. How Does the WebFlux HTTP Boundary Relate to Publisher?

In a WebFlux annotated controller:

```java
@GetMapping("/api/numbers")
public Flux<NumberDto> numbers() {
    return Flux.range(1, 3).map(NumberDto::new);
}
```

**The controller returns a Publisher** and does not call `subscribe()` itself. The WebFlux HTTP infrastructure becomes the downstream consumer, subscribing, applying codecs, and writing the response as network I/O permits.

```text
Reactive DB / Flux.range / WebClient       HTTP response writer
                Publisher                      Subscriber
                  |                               |
                  | <------ subscribe ------------|
                  | ------ onSubscribe ---------->|
                  | <------ request(n) ------------|
                  | ------ onNext(record) -------->|
                  |                         JSON encoding/network
                  | ------ onComplete ------------>|
```

Simplified diagram: WebFlux has multiple intermediate operators, codecs, and internal subscribers; one `request(n)` does not necessarily correspond to one JSON document or one network packet. Reactor Netty/WebFlux is built on non-blocking I/O and backpressure. A slow-reading HTTP client can exert backpressure through response writing, but memory usage also depends on codecs, buffering, the data source, and application limits.

### Mono/Flux and HTTP Response Behavior

- `Mono<Dto>`: 0 or 1 object; typically suits GET for a single resource.
- `Flux<Dto>`: stream of multiple values; an HTTP JSON array is serialized in a way that may require appropriate buffering/formatting; with `text/event-stream`, each event can be sent over time.
- `Mono<Void>`: represents completion handling with no value, typically paired with an appropriate status.
- `Flux<DataBuffer>`: raw bytes; memory/ref-counting and cleanup must be managed per the `DataBuffer` API.
- Errors before the response is committed can be mapped to an HTTP status/body; errors after the stream is committed **cannot always be changed** into a new JSON error or HTTP 500.

Do not manually run `flux.subscribe(value -> response.getWriter().write(...))` inside a handler and then return `Mono.empty()`, because the framework can no longer properly manage response completion, cancellation, and backpressure.

## 18. Runnable Spring Boot WebFlux Application

Create a Maven project via Spring Initializr with **Java 17+, Spring Boot 3.x**, dependencies:

- `spring-boot-starter-webflux` (do not add `spring-boot-starter-web` if you want Boot to clearly select the reactive WebFlux app type).
- `spring-boot-starter-test` (test scope).
- `reactor-test` (test scope, if not already included by starter-test).

This example requires no database. Files:

```text
src/main/java/com/example/demo/
  DemoApplication.java
  NumbersController.java
src/test/java/com/example/demo/
  NumbersControllerTest.java
  ReactiveDemandTest.java
```

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

### 18.2. NumbersController.java

```java
package com.example.demo;

import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class NumbersController {

    @GetMapping(path = "/numbers",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<NumberDto> numbers(
            @RequestParam(defaultValue = "3") int count) {

        if (count < 1 || count > 20) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "count must be between 1 and 20");
        }

        return Flux.range(1, count)
                .map(NumberDto::new)
                .delayElements(Duration.ofMillis(80));
    }

    @GetMapping(path = "/numbers/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<NumberDto> one(@PathVariable int id) {
        if (id < 1 || id > 20) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "number not found"));
        }
        return Mono.just(new NumberDto(id));
    }

    @PostMapping(path = "/echo",
                 consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<EchoResponse> echo(@RequestBody Mono<EchoInput> input) {
        // Do not subscribe manually: WebFlux manages the subscription.
        return input.map(v -> new EchoResponse(v.message()));
    }

    public record NumberDto(int value) {}
    public record EchoInput(String message) {}
    public record EchoResponse(String message) {}
}
```

**Explanation:**

- `numbers` returns a finite `Flux`, rendered as Server-Sent Events thanks to `produces=text/event-stream`. `delayElements` introduces an illustrative delay; an exact 80ms interval is not guaranteed on every system.
- `one` returns `Mono<NumberDto>` or `Mono.error(...)`; an error before response commit can become a 404.
- `echo` receives the request body as `Mono<EchoInput>` to illustrate a WebFlux reactive request-body argument; the response completes once the input is decoded and mapped.
- The controller **never calls `subscribe()` or `block()`**. The HTTP infrastructure owns demand/cancel/completion.
- The count endpoint is bounded to 1..20 so the demo does not emit an infinite stream or consume unbounded resources.
- If you want to use R2DBC/a real reactive repository, choose a driver that provides a reactive contract rather than wrapping JDBC and claiming it is non-blocking.

### 18.3. Startup

In a Maven project with the Wrapper:

```bash
./mvnw spring-boot:run
```

On PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

By default the app listens on port `8080` if `server.port` is unchanged. This is a Spring Boot source requiring Spring WebFlux/Reactor/Jackson on the classpath; `javac NumbersController.java` alone lacks dependencies.

## 19. curl: Observing WebFlux HTTP Responses

### Server-Sent Events

```bash
curl -N -i 'http://localhost:8080/api/numbers?count=3'
```

With an appropriate default `Accept` header, the response typically has `Content-Type: text/event-stream` and three events emitted in order; the data portion looks like:

```text
data:{"value":1}

data:{"value":2}

data:{"value":3}

```

Headers, timing intervals, and formatting details can depend on the codec/server, but the `value` numbers and order 1–3 are the contract of `Flux.range`. `curl -N` disables output buffering in curl so each event can be observed.

Do not assume “request count=3 → client calls Subscription.request(3) exactly once”. The WebFlux writer and codecs perform internal buffering/prefetching; only assert that the response contains three events in the expected order.

### Fetching a Single Element

```bash
curl -i 'http://localhost:8080/api/numbers/2'
```

Expected HTTP 200:

```json
{"value":2}
```

`GET /api/numbers/99` returns 404 if the error is handled before the response is committed. The app has no database; the 1..20 rule simply illustrates `Mono.error`.

### Reading a JSON Body as Mono

```bash
curl -i -X POST 'http://localhost:8080/api/echo' \
  -H 'Content-Type: application/json' \
  -d '{"message":"Hello WebFlux"}'
```

Expected HTTP 200 and JSON:

```json
{"message":"Hello WebFlux"}
```

No code subscribes manually once to “trigger echo” and then returns another Mono; doing so would create side effects or duplicate subscriptions outside the HTTP lifecycle.

### Testing Invalid Input

```bash
curl -i 'http://localhost:8080/api/numbers?count=1000'
```

Expected HTTP 400 before sending a streaming body because the controller validates immediately. In real applications, the error body depends on Spring Boot error handling and Problem Details configuration; do not hardcode a specific error JSON payload unless configured.

## 20. WebTestClient: Testing Reactive HTTP

File `src/test/java/com/example/demo/NumbersControllerTest.java`:

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

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class NumbersControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void oneNumberReturnsMonoValueAsJson() {
        client.get()
            .uri("/api/numbers/2")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.value").isEqualTo(2);
    }

    @Test
    void rejectsInvalidCount() {
        client.get()
            .uri("/api/numbers?count=1000")
            .exchange()
            .expectStatus().isBadRequest();
    }

    @Test
    void echoJsonBody() {
        client.post()
            .uri("/api/echo")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"message\":\"hello\"}")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("hello");
    }

    @Test
    void receivesThreeSseItemsThenCompletes() {
        Flux<String> body = client.get()
            .uri("/api/numbers?count=3")
            .accept(MediaType.TEXT_EVENT_STREAM)
            .exchange()
            .expectStatus().isOk()
            .returnResult(String.class)
            .getResponseBody();

        StepVerifier.create(body)
            .expectNextMatches(s -> s.contains("\"value\":1"))
            .expectNextMatches(s -> s.contains("\"value\":2"))
            .expectNextMatches(s -> s.contains("\"value\":3"))
            .verifyComplete();
    }
}
```

**Note on SSE testing:** decoding `String.class` under `text/event-stream` can depend on codecs and how events are split across Spring/client versions. If a project's codec maps the body to another object or you need to inspect event metadata, replace `String.class` with `ServerSentEvent<NumberDto>`/DTO using an appropriate `ParameterizedTypeReference` and assert values. Do not assume each TCP chunk is a separate event.

Run:

```bash
./mvnw test
```

Or PowerShell:

```powershell
.\mvnw.cmd test
```

This is a **runnable test example for a Boot 3 project with matching dependencies**, not output already executed in a user's repository. For endpoints protected by Spring Security, you must supply valid identity/CSRF per policy or requests may receive 401/403 before reaching the controller.

## 21. Errors, Cancellation, Resource Cleanup, and HTTP Disconnect

When a Publisher emits `onError(error)`, it is a **terminal** signal: neither `onComplete` nor `onNext` may follow. Reactor operators like `onErrorResume` can switch an errored stream to a new fallback Publisher, but recognize this as **pipeline redirection**, not continuing to emit signals after termination on the original subscription.

Example:

```java
Mono<String> result = remoteCall()
    .timeout(Duration.ofSeconds(2))
    .onErrorResume(java.util.concurrent.TimeoutException.class,
                   e -> Mono.just("fallback"));
```

The snippet above requires a `remoteCall()` method and imports; it is not a standalone runnable file. `timeout` terminates/cancels the upstream portion, yet there is **no guarantee** that the physical network/database operation stopped instantaneously or that side effects rolled back. Fallbacks can mask critical errors if used indiscriminately.

With HTTP streaming, when a client disconnects, downstream WebFlux can cancel the subscription. Ensure the source releases database cursors, file handles, broker consumers, and references in `doFinally`/resource-managed operators according to the signal type.

```java
Flux<Integer> source = Flux.range(1, 100)
    .doFinally(signal ->
        System.out.println("terminated=" + signal));
```

The snippet above only observes events when the source actually has a subscription; termination/cancellation depends on how it is subscribed and consumed. `doFinally` can receive `ON_COMPLETE`, `ON_ERROR`, or `CANCEL`; do not treat cancellation as success in domain logic.

`Subscription.cancel()` must be thread-safe/idempotent and eventually stop emitting; the subscriber must still be prepared for some `onNext` signals already in flight right after requesting cancellation. Do not rely on cancel as a thread-killing mechanism or transaction rollback.

## 22. How Reactive Streams Differ from Java Stream, Future, and Iterator

| Concept | Consumption Model | Difference from Reactive Streams |
| --- | --- | --- |
| `java.util.Iterator` | Consumer synchronously calls `next()` | Direct pull, typically blocking if fetching data is slow |
| `java.util.stream.Stream` | Typically synchronous pipeline over a collection/spliterator | Not a Reactive Streams Publisher, no `Subscription.request(n)` |
| `CompletableFuture<T>` | Single eventual result/error | Does not naturally represent 0..N signals/backpressure |
| `Flow.Publisher<T>` | Similar JDK reactive protocol | Different interface package from `org.reactivestreams.Publisher` |
| `Mono<T>` | 0..1 asynchronous/synchronous publisher | Reactor type rich in operators |
| `Flux<T>` | 0..N signals, supports demand | Reactor type rich in operators, not always infinite data |

`parallelStream()` is not a shortcut to non-blocking WebFlux. `CompletableFuture.supplyAsync` has its own executor semantics and does not inherently receive backpressure from an HTTP subscriber. Reactor does not replace Java Stream for every small CPU-bound collection task.

**Reactor does not guarantee optimal throughput for everything**: event-driven non-blocking sources help use fewer threads when waiting on heavy I/O, yet reactive code is harder to debug, incurs scheduler/operator overhead, and still faces data bottlenecks.

## 23. Common Mistakes

1. **Thinking `subscribe()` returns a Subscription in the spec:** it returns `void`; Subscription is passed via `onSubscribe`.
2. **Not calling `request(n)`:** a spec-compliant source does not send `onNext` without demand.
3. **Using `request(0)` to pause:** invalid per rule 3.9; must error while active.
4. **Thinking `request(2)` must emit exactly two values:** the source may emit fewer or complete/error.
5. **Emitting `onNext` before `onSubscribe`:** protocol violation.
6. **Emitting after `onError`/`onComplete`:** violates the terminal contract.
7. **Emitting `onNext(null)` to signify no data:** invalid; use empty/completion.
8. **Two threads calling `onNext` concurrently on the same subscriber:** violates serialized signals.
9. **Not cancelling unused subscriptions:** wastes resources and can leak.
10. **Thinking `cancel` immediately halts all network I/O:** semantics are eventual, with no rollback guarantee.
11. **Thinking `Flux` means non-blocking:** the underlying source might still call JDBC or `Thread.sleep`.
12. **Calling `block()` directly inside a WebFlux event-loop handler:** blocks the event loop or throws an error.
13. **Manually calling `subscribe()` in a controller and returning `Mono.empty()`:** detaches the producer from the HTTP lifecycle.
14. **Thinking a `subscribe(...)` lambda demo verifies per-element backpressure:** it typically requests unbounded demand.
15. **Thinking `Mono` always has one value so terminal/error handling isn't needed:** a Mono can be empty or error.
16. **Assuming every `Flux` is cold and every subscriber gets all data:** hot/unicast/replay behaviors differ.
17. **Thinking `map`/`filter`/`flatMap` operators preserve `request(1)` upstream:** they can reshape or prefetch demand.
18. **Creating an unbounded buffer for a hot source:** can cause OOM when consumers are slow.
19. **Thinking a slow-reading HTTP client merely slows the Publisher without buffering:** networks and codecs have their own buffers/limits.
20. **Using `onErrorResume` to swallow every error:** can mask outages and return incorrect business data.
21. **Using `Mono.just(blockingCall())` thinking the call is lazy:** the argument is already evaluated when creating the Mono.
22. **Wrapping JDBC in a Mono without selecting an appropriate scheduler:** blocking work can end up on the event loop.
23. **Implementing a custom Publisher without running the TCK:** easy to get demand, cancellation, and concurrency wrong.
24. **Using `StepVerifier` with `initialRequest=0` and immediately calling `expectNext`:** the source has no permission to emit, so the test may stall.
25. **Thinking WebFlux and Servlet MVC always share the same request context/thread-local:** their stacks and contexts differ.
26. **Not managing resource cleanup on cancel/disconnect:** leaks cursors, subscriptions, and handles.
27. **Equating backpressure with rate limiting/quotas:** demand is per-subscription data flow, distinct from API quotas.
28. **Failing to distinguish the Flow API from the `org.reactivestreams` package:** an adapter is required if combining them directly.
29. **Ignoring operator prefetch/concurrency:** small downstream requests can still trigger heavy upstream work.
30. **Thinking one streaming HTTP event equals one TCP packet:** transport framing and codecs differ from object signals.

## 24. Practice and Production Checklist

### Protocol

- [ ] Does the Publisher emit `onSubscribe` before other signals and at most once?
- [ ] Is `onNext` always non-null and never exceeding total requested?
- [ ] Are signals serialized, with no second terminal signal or signal after terminal?
- [ ] Is `request(n)` positive, is demand additive, and are `Long.MAX_VALUE`/overflow handled?
- [ ] Does `request(0)`/negative emit a terminal `IllegalArgumentException` per the spec?
- [ ] Is `cancel` safe, idempotent, and performing eventual cleanup?
- [ ] Have Reactor built-ins/TCK been used instead of hand-rolling a Publisher unnecessarily?

### WebFlux/Reactor

- [ ] Do controllers return `Flux`/`Mono` for the framework to subscribe, without subscribing manually?
- [ ] Is blocking I/O kept off the Netty event loop, using `boundedElastic` or a proper reactive driver?
- [ ] Are cold/hot assumptions avoided when multiple subscribers or reconnects exist?
- [ ] Are operator prefetch/concurrency/buffers bounded?
- [ ] Do hot sources have a policy when downstream is slow?
- [ ] Is resource cleanup verified on complete/error/cancel?
- [ ] Are timeouts understood not to automatically roll back side effects?
- [ ] Are security/authentication/authorization and per-user quotas independent of backpressure?

### Testing and Operations

- [ ] Are `request(1)`, batched requests, cancellation, empty, error, and completion tested?
- [ ] Is `StepVerifier` used with explicit initial request when verifying demand?
- [ ] Are HTTP SSE/JSON endpoints tested with `WebTestClient` and `curl -N`?
- [ ] Are buffers/queues, memory, event-loop blocking, dropped events, and timeouts monitored?
- [ ] Is TCP chunk order avoided as a proxy for business message order?
- [ ] Are max events/request, idle timeouts, and reconnect/replay policies documented for streaming?
- [ ] Is sensitive data prevented from leaking via event streams, logs, traces, or error messages?

## 25. Self-Check Questions

**1.** Who decides how many elements a Publisher is allowed to deliver to a Subscriber?

**Answer:** The Subscriber by calling `Subscription.request(n)`; the Publisher must not emit `onNext` beyond the accepted demand.

**2.** What type does `Publisher.subscribe(s)` return according to the Reactive Streams JVM specification?

**Answer:** `void`. The Subscription is delivered via `Subscriber.onSubscribe(subscription)`.

**3.** Why is `onSubscribe` needed before `onNext`?

**Answer:** The Subscriber needs to receive the Subscription so it can proactively request/cancel, establishing a consistent initialization point.

**4.** What do `request(2)` followed by `request(3)` mean?

**Answer:** Demand is cumulative, allowing up to five more elements to be emitted minus any already consumed; it does not reset to three.

**5.** Can `onComplete` be called before any `request`?

**Answer:** Yes. Terminal signals do not require demand like `onNext`.

**6.** Is `request(0)` a pause?

**Answer:** No; when the Subscription is still active, it is an invalid request and must signal `onError(IllegalArgumentException)`.

**7.** Can both `onError` and `onComplete` occur on the same subscription?

**Answer:** No. Both are terminal signals and are mutually exclusive.

**8.** Do Reactive Streams always execute asynchronously on another thread?

**Answer:** No. `Flux.range` can emit synchronously right inside the `request` call; a `Scheduler` is a separate choice.

**9.** Why does `subscribe(System.out::println)` not demonstrate custom backpressure?

**Answer:** Simple Reactor overloads usually request unbounded demand; you need `BaseSubscriber` or `StepVerifier` to control demand.

**10.** Does `cancel()` always immediately abort a network call or roll back a transaction?

**Answer:** No. It requests eventual stopping and cleanup; downstream I/O and transactions have their own semantics.

**11.** Does a final subscriber requesting only `request(1)` guarantee the upstream source computes only one item?

**Answer:** No. `buffer`, `flatMap`, and prefetching can reshape demand; each boundary has its own rules.

**12.** Should a WebFlux controller return a `Flux` or call `subscribe` itself?

**Answer:** Return `Flux`/`Mono`. The WebFlux infrastructure will subscribe, manage demand, handle the response, and propagate cancellation.

**13.** Is `Mono.just(service.get())` always lazy?

**Answer:** No. `service.get()` is evaluated before being passed into `just`; use `defer`/`fromCallable` and an appropriate scheduler if needed.

**14.** Can Java `Flow.Publisher` be cast directly to `org.reactivestreams.Publisher`?

**Answer:** No. They are interfaces in different packages and require an intentional adapter.

## 26. References

- Reactive Streams JVM specification, API, and Publisher/Subscriber/Subscription rules: https://github.com/reactive-streams/reactive-streams-jvm
- Reactive Streams official website: https://www.reactive-streams.org/
- Spring Framework — Spring WebFlux overview: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Spring Framework — Reactive Core and HTTP backpressure: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Framework — WebFlux annotated controllers: https://docs.spring.io/spring-framework/reference/web/webflux/controller.html
- Project Reactor Core reference, `subscribe`, `BaseSubscriber`, and demand: https://projectreactor.io/docs/core/release/reference/
- Project Reactor Core reference — backpressure and request reshaping: https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html
- Project Reactor — testing `StepVerifier`: https://projectreactor.io/docs/core/release/reference/testing.html
- Project Reactor — schedulers and threading: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
- Java 17 `java.util.concurrent.Flow`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.html
- Java 17 `SubmissionPublisher`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html
