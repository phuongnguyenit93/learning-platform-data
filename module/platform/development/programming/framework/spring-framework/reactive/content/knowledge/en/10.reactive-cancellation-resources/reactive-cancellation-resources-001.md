# Propagating Cancel When the Receiver Needs No More Data

**Context:** Spring Framework – Reactive, chapter **Cancellation and Resources**. This lesson focuses on the **cancellation** mechanism in Project Reactor: when a subscriber or a downstream operator no longer wants to receive further data, how the `cancel()` signal propagates upstream, why cancelling a subscription must not be equated with immediately stopping all work, and how to properly release resources in Spring WebFlux.

## 1. Why Is Cancel Needed?

In a reactive pipeline, downstream may no longer need data before the source finishes naturally. For example:

- A user closes a page viewing Server-Sent Events (SSE), WebSocket, or a stream.
- A processor only needs the first three elements of a `Flux` containing thousands of elements.
- A new search query arrives, making the results of the previous query no longer useful.
- A request times out, or the subscriber decides to cancel because the user aborts the operation.
- A stream holds a connection to a long-lived event source and needs to stop when the client is no longer listening.

If it continues loading data, creating timers, holding connections, or running work nobody needs, the system will waste CPU, memory, network, threads, and upstream resources. **Cancellation** allows downstream to announce: “I no longer need the remaining data of this subscription; please try to stop the related work.”

In Reactive Streams, the cancellation signal is sent using the **`Subscription.cancel()`** method. In Reactor, many convenience APIs ultimately lead to the same thing, for example `Disposable.dispose()` on a subscription returned by some `subscribe(...)` overloads, `BaseSubscriber.cancel()`, or an operator cancelling the source itself once its goal is reached.

**Key point:** cancel is a **control signal on the subscription**, not a confirmed business rollback request, not a way to force an HTTP server or database to stop immediately, and it does not automatically emit `onComplete()` for a cancelled source.

## 2. Two Directions in a Pipeline: Data Goes Down, Cancel Goes Up

A Reactor pipeline can be visualized as:

```text
                       DATA SIGNAL DIRECTION
Publisher A --> map --> filter --> take(3) --> Final Subscriber
      |         |          |          |               |
      |       onNext ---- onNext ---- onNext -------> receives 1, 2, 3
      |                                              |
      +---------------- cancel() <-------------------+
                       CONTROL DIRECTION
```

The source emits `onNext(value)`, `onComplete()`, or `onError(error)` downstream. Conversely, downstream uses `Subscription.request(n)` to request the number of elements permitted to be emitted, or `Subscription.cancel()` to state that it does not need to continue.

Each operator can play two roles:

1. **Subscriber to upstream:** receives `onSubscribe`, `onNext` signals, and terminal signals from the preceding operator.
2. **Publisher to downstream:** provides a subscription to the following operator and receives `request(n)`/`cancel()` from downstream.

When receiving `cancel()`, an operator typically forwards the cancellation notification to its upstream subscription and performs the necessary cleanup steps. In a composed chain, an operator may simultaneously cancel **multiple inner subscriptions** or scheduled tasks. The details depend on the operator type and runtime state.

### 2.1. Cancel Is Different from Running Out of Demand

| State | Meaning | Can it continue receiving data later? |
| --- | --- | --- |
| Called `request(2)` and received two elements, outstanding demand is 0 | No further `onNext` is currently permitted | Yes, if the subscription is still active and more `request(n)` calls are made |
| Subscriber calls `cancel()` | No longer wants to continue that subscription | Must not rely on a cancelled subscription to request more |
| Publisher emits `onComplete()` | Source finished successfully | No, the subscription has terminated |
| Publisher emits `onError(error)` | Source terminated with an error | No, the subscription has terminated |
| A `take(3)` operator receives three elements | Operator sends complete downstream and cancels the upstream source if still active | Downstream completes; upstream may observe cancel |

**Do not call `request(0)` as a cancel or pause command.** `request(n)` requires a positive value; a non-positive request is a Reactive Streams protocol violation. If you are only temporarily not ready, simply do not request more elements. If you decide to terminate completely, use `cancel()`.

### 2.2. Cancel Is Per-Subscription

A cold `Flux` can be subscribed to multiple times:

```java
Flux<Long> ticks = Flux.interval(Duration.ofSeconds(1));
Disposable first = ticks.subscribe(System.out::println);
Disposable second = ticks.subscribe(System.out::println);

// When the first subscriber is no longer needed:
first.dispose();
```

This is **illustrative code**, requiring imports for `Duration`, `Disposable`, and `Flux`; it is not a standalone runnable class. With a standard `Flux.interval`, each subscription creates its own subscription/emission schedule. Cancelling `first` does not mean `second` is cancelled.

If a publisher has been **shared or cached** (for example with `share()`, `publish().refCount(...)`, `cache()`, or a hot sink), cancelling one downstream subscription may not stop the shared source while other subscribers still need data. You need to understand the contract of the sharing operator; **cancel does not mean “close all subscribers and all global resources”**.

## 3. How Does Cancel Propagate When `take(n)` Receives Enough Data?

Suppose a source has ten elements, but downstream only needs three:

```java
Flux<Integer> firstThree = Flux.range(1, 10)
        .take(3);
```

Once the subscriber actually requests and receives three elements, `take(3)` needs no more elements from upstream:

1. Upstream emits 1, 2, 3 according to valid demand.
2. `take(3)` forwards those three elements downstream.
3. It notifies upstream to cancel the subscription because 4..10 are no longer needed.
4. Downstream sees a **normal completion** via `onComplete()` after three elements.

Conceptual progression:

```text
Source                    take(3)                  Subscriber
  | onNext(1) -------------->| onNext(1) ------------->|
  | onNext(2) -------------->| onNext(2) ------------->|
  | onNext(3) -------------->| onNext(3) ------------->|
  |<------------- cancel() ---|                         |
  |                           | onComplete() ---------->|
```

**A single pipeline can simultaneously have two different termination kinds at two different positions:**

- **Before `take(3)`:** upstream receives `cancel()`, so a hook placed before `take` may observe `SignalType.CANCEL`.
- **After `take(3)`:** downstream receives `onComplete()`, so a hook placed after `take` may observe `SignalType.ON_COMPLETE`.

This is not a contradiction: `take` proactively completes its own output after reaching the required count and no longer needing input.

**Note:** limiting results with `take(n)` does not necessarily cause every upstream operator to request strictly `n` elements in all configurations. Prefetching, queues, and intermediate operators can alter requests; cancellation is still intended to stop work that does not need to continue. If the source has already emitted some signals into a buffer, they may be discarded upon cancellation.

### 3.1. Operators That Can Trigger Source Cancellation

| Cause | Typical mechanism | What does downstream see? |
| --- | --- | --- |
| `take(n)` has received `n` elements | Cancels the active upstream | Receives `n` elements then completes normally |
| `next()` applied to `Flux<T>` | Takes the first element and skips the rest by cancelling upstream | `Mono<T>` with at most one element, then completes |
| `switchMap(...)` receives a new outer item | Cancels the old inner publisher, subscribes to the new inner | The main stream continues, only the new inner is observed |
| Downstream calls `cancel()` or `dispose()` | Propagates cancel upstream through the operator chain | Upstream is not required to send `onComplete`/`onError` after cancellation |
| `timeout(...)` expires | Cancels the pending source; may switch to error or fallback | Usually a timeout `onError` or fallback data, depending on configuration |
| HTTP/SSE client disconnect | WebFlux/adapter may cancel the response publisher | Source tries to stop per subscription lifecycle; timing depends on transport |
| An outer `flatMap` is cancelled | Operator usually cancels still-active inner subscriptions | No further results from cancelled work are used |

When an operator completes normally before the source has finished, the signal observed by the **source** may differ from the signal seen by the **final consumer**. Place logs on both sides of important operators instead of guessing.

## 4. Standalone Runnable Java 17+ Example: Downstream Cancels and Resources Are Closed

The example has two parts:

- **Explicit cancellation:** `BaseSubscriber` requests elements one by one from `Flux.range(1,10)`, and after receiving 3 values calls `cancel()`.
- **Operator-triggered cancellation:** `take(2)` receives two values from a resource-backed source; `Flux.using(...)` closes the resource when it is no longer needed.

The program has no scheduler, HTTP, or network, so the output does not depend on execution timing.

Create the file `src/main/java/demo/CancellationPropagationDemo.java`:

```java
package demo;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public final class CancellationPropagationDemo {

    static final class FakeCursor implements AutoCloseable {
        private final AtomicInteger closeCount;

        FakeCursor(AtomicInteger closeCount) {
            this.closeCount = closeCount;
        }

        @Override
        public void close() {
            closeCount.incrementAndGet();
        }
    }

    public static void main(String[] args) {
        AtomicInteger cancelCalls = new AtomicInteger();
        AtomicInteger sourceCompletes = new AtomicInteger();
        List<Integer> received = new ArrayList<>();

        Flux<Integer> source = Flux.range(1, 10)
                .doOnCancel(() -> cancelCalls.incrementAndGet())
                .doOnComplete(() -> sourceCompletes.incrementAndGet());

        BaseSubscriber<Integer> subscriber = new BaseSubscriber<>() {
            @Override
            protected void hookOnSubscribe(Subscription subscription) {
                request(1);
            }

            @Override
            protected void hookOnNext(Integer value) {
                received.add(value);
                if (received.size() == 3) {
                    cancel();
                } else {
                    request(1);
                }
            }
        };

        source.subscribe(subscriber);

        System.out.println("received = " + received);
        System.out.println("source cancel calls = " + cancelCalls.get());
        System.out.println("source completes = " + sourceCompletes.get());

        AtomicInteger closeCount = new AtomicInteger();

        List<Integer> firstTwo = Flux.using(
                    () -> new FakeCursor(closeCount),
                    resource -> Flux.range(10, 5),
                    FakeCursor::close
                )
                .take(2)
                .collectList()
                .block(Duration.ofSeconds(3));

        System.out.println("take values = " + firstTwo);
        System.out.println("cursor closes = " + closeCount.get());
    }
}
```

**Prerequisites:** Java 17+, `io.projectreactor:reactor-core` along with compatible `org.reactivestreams:reactive-streams`. Spring Boot projects with `spring-boot-starter-webflux` typically already include the relevant dependencies. If you already have a project, run the `main` method directly from your IDE.

To compile manually, place the two required libraries in `lib/` and run from the directory containing `src/`:

```bash
# Linux/macOS
mkdir -p out
javac -cp "lib/*" -d out src/main/java/demo/CancellationPropagationDemo.java
java -cp "out:lib/*" demo.CancellationPropagationDemo
```

```powershell
# Windows PowerShell
New-Item -ItemType Directory -Force out
javac -cp "lib/*" -d out src/main/java/demo/CancellationPropagationDemo.java
java -cp "out;lib/*" demo.CancellationPropagationDemo
```

**Exact stdout of this synchronous example:**

```text
received = [1, 2, 3]
source cancel calls = 1
source completes = 0
take values = [10, 11]
cursor closes = 1
```

Analysis:

1. Upon subscribing, `BaseSubscriber` sends `request(1)`. After each initial element, it requests one more. After the third element, it calls `cancel()` instead of requesting further.
2. `doOnCancel(...)` placed **before the subscriber, near the source** receives exactly one cancel signal; `doOnComplete(...)` does not run because the source did not finish naturally.
3. Once subscribing to the synchronous source finishes, the list contains only 1, 2, 3. With no further demand, the source does not continue emitting 4..10.
4. `Flux.using(...)` creates a `FakeCursor` **per subscription** and registers the `FakeCursor::close` cleanup. `take(2)` receives 10 and 11 and cancels upstream, so the resource is closed.
5. `collectList().block(...)` is used only at the **command-line program boundary** to wait for data and print results. In a WebFlux controller/event-loop, do not use `block()` to obtain data synchronously.

The example above demonstrates **subscription-level cancellation** and cleanup when a source is cut short. It does not prove that a remote HTTP request, JDBC query, or running CPU task can be forced to stop immediately.

## 5. Paying Attention to When Cancellation Actually Occurs

### 5.1. Cancellation Is a Request to Stop, Not Confirmation of Immediate Halt

Reactive Streams specifies that `cancel()` is a signal to stop the subscription, but execution may be happening on another thread. Depending on the source, an element may already have been computed or be in flight toward downstream at the exact moment of cancellation. Some synchronous sources may also complete very quickly before the caller gets a chance to cancel.

Typical cases:

- A synchronous `Flux.range(...)` source can easily stop early when receiving cancel during its emission loop.
- `Flux.interval(...)` can cancel the schedule/timer of an active subscription.
- `WebClient` can cancel waiting for the response and help release client resources depending on the HTTP connector.
- Blocking JDBC/SDK calls may not respond to cancellation immediately, or may be unable to stop code currently waiting.
- An HTTP server that already received the request may have finished writing even though the client is no longer waiting for the response.
- A hot source or `Sinks.Many` may continue producing events for other subscribers; cancelling one consumer does not force the global source to stop.

Therefore, distinguish between **having emitted the cancel signal**, **having received cancel at the upstream subscription**, **having released local resources**, and **external system work actually stopping**. Those are four events that can happen at different times.

### 5.2. Cancel Does Not Automatically Generate `onError` or `onComplete` Upstream

A cancelled subscription is not required to emit a terminal signal as confirmation. `onErrorResume(...)` is also not a default hook for cancellation, because cancel **is not an `onError`**.

Example of observation placement:

```java
Flux<Integer> output = Flux.range(1, 10)
        .doFinally(signal ->
                System.out.println("upstream: " + signal))
        .take(3)
        .doFinally(signal ->
                System.out.println("downstream: " + signal));
```

This is an **illustrative snippet**, meaningful only after a subscriber requests enough elements. Before `take`, `SignalType.CANCEL` is typically seen, whereas after `take`, `SignalType.ON_COMPLETE` is seen. **The order in which `doFinally` logs appear is not fixed**: Reactor may execute the final callback after the terminal signal has gone downstream, and with multi-threaded scheduling the logs can interleave.

If a source naturally emits all ten elements before being cancelled, it will follow the completion path instead of cancellation. If an error occurs before the cancellation point, the pipeline may receive an error. Actual state depends on event ordering.

## 6. Choosing the Right Hook to Observe Cancellation

Reactor provides several lifecycle observation operators. They serve different purposes:

| Hook | Observation timing | Runs on cancel? | Notes |
| --- | --- | --- | --- |
| `doOnSubscribe(...)` | New subscription is attached | Not a termination hook | For recording lifecycle start |
| `doOnRequest(...)` | Downstream sends demand | Does not replace cancel | Tracks requested counts at the exact placement point |
| `doOnNext(...)` | An element is emitted past the probe | Not necessarily | Does not run if no element has been emitted |
| `doOnCancel(...)` | Subscription at that point is cancelled | Yes | Does not mean upstream has closed remote resources |
| `doFinally(signal -> ...)` | After complete/error/cancel of the subscription | Yes, with `SignalType.CANCEL` | Suitable for metrics, logging, and classifying termination |
| `doOnComplete(...)` | Upstream completes normally | No for pure cancel | May run downstream after `take` but not at a cancelled source |
| `doOnError(...)` | Upstream emits error | No for pure cancel | Do not use to catch a user leaving the page |
| `doOnTerminate(...)` | Complete or error | No | Different from `doFinally` |
| `doOnDiscard(...)` | Operator supports dropping elements from a buffer | Useful in certain cancellation paths | Only effective on operators with discard support, not a general hook for all elements |

**Hook placement matters as much as hook type.** If you want to know whether an HTTP, database, or timer source **was requested to cancel**, place `doOnCancel` near the source publisher; if you want to know for what reason a WebFlux request ended, place `doFinally` at the response boundary.

Logging example in a service:

```java
return source
        .doOnSubscribe(s -> metrics.streamStarted())
        .doOnCancel(() -> metrics.sourceCancelled())
        .doFinally(signal -> metrics.streamFinished(signal));
```

This is **illustrative code**; `source` and `metrics` are application-defined. `doFinally` can execute **after downstream has already received the terminal signal**. If you measure via a counter, call `block()`, and check immediately afterward, the `doFinally` callback might not have been observed yet; use proper synchronization/testing rather than asserting unguaranteed ordering.

### 6.1. `doOnCancel` and `doFinally` Are Not Full Resource Management Mechanisms

Using `doFinally` to close a resource can make cleanup logic depend on callback ordering, errors inside callbacks, or access to a resource shared by multiple subscribers. If a resource is **opened at assembly time** and shared across multiple subscriptions, cancelling one subscriber can mistakenly close the resource others are using.

For resources whose lifecycle is bound **per subscription**, prefer `Flux.using(...)` or `Mono.using(...)` for synchronous cleanup, and `usingWhen(...)` for asynchronous cleanup. These operators clearly express “open resource → create publisher using resource → close on complete, error, or cancel”.

## 7. Releasing Resources with `using` and `usingWhen`

### 7.1. Why `try/finally` Around Returning a Publisher Can Be Wrong

The following snippet has a **wrong lifecycle** when the pipeline executes lazily:

```java
Reader reader = openReader();
try {
    return Flux.fromStream(reader.lines());
} finally {
    reader.close();
}
```

This is illustrative code: `openReader()` and checked exception handling are undefined. The problem is that the Java code builds the publisher and **closes the reader right when returning**, whereas the subscriber usually only reads data **later**. The publisher may be subscribed to when the resource is already closed.

Instead, let the resource be created **per subscription** and bind cleanup to that exact subscription:

```java
return Flux.using(
        () -> openReader(),
        reader -> Flux.fromStream(reader.lines()),
        reader -> closeReader(reader));
```

This is also illustrative code, requiring definitions for `openReader`/`closeReader`, `IOException` handling, and appropriate scheduler selection. With a blocking reader, use it only when you have accounted for isolating I/O off the Netty event-loop, for example at a legacy boundary using `Schedulers.boundedElastic()`. **The presence of `Flux.using` does not automatically make File I/O/JDBC non-blocking.**

When a subscriber cancels partway through, `using` runs the disposer per contract so readers/cursors/sockets are not held forever. In the complete example in section 4, `FakeCursor` is closed exactly once even though the original `Flux.range` did not finish emitting.

### 7.2. `usingWhen` for Asynchronous Cleanup

When a resource is opened/closed via an asynchronous publisher (such as a reactive connection), `Flux.usingWhen(...)`/`Mono.usingWhen(...)` helps manage the resource per termination path:

```java
Flux<Result> stream = Flux.usingWhen(
        acquireResource(),
        resource -> readResults(resource),
        resource -> asyncClose(resource),                  // complete
        (resource, error) -> asyncCleanupOnError(resource), // error
        resource -> asyncCleanupOnCancel(resource)          // cancel
);
```

This is **illustrative code with hypothetical types and methods**, not a standalone Java class. Cleanup functions must return `Publisher<?>`, and each path must decide the behavior for the actual resource.

Meaning:

- **Complete:** normal work finished, clean up via the completion branch.
- **Error:** source failed, clean up via the error branch (may need to roll back a transaction or close the connection depending on contract).
- **Cancel:** downstream no longer needs data, a **dedicated cleanup branch** can return a publisher to release the resource or abort the transaction per supported API.

Design cleanup to be idempotent, bound it with timeouts, and add logging/metrics for cleanup failures. In process crash or complete network partition scenarios, no cleanup publisher can be guaranteed to always run to completion. For transactional data, recovery, server-side timeouts, transaction semantics, and additional guarantees are required.

**Do not equate cancel with rollback.** Cancel at the Reactor layer cannot automatically undo a committed database write or an HTTP command creating a resource that the server has already received and executed.

### 7.3. Callback-Based Sources with `Flux.create`

A callback-driven push source may know nothing about Reactive Streams. An adapter written with `Flux.create(sink -> ...)` should consider:

- Use `sink.onCancel(...)` to request unregistering a listener or stopping callbacks when downstream cancels.
- Use `sink.onDispose(...)` for cleanup on complete/error/cancel; when using both, avoid cleaning up resources twice and ensure cleanup is safe.
- Control a fast producer with an overflow strategy, bounded buffer, drop/error, or a mechanism to actually stop the producer if the API allows.
- Do not keep pushing events indefinitely into a cancelled sink, and do not retain closure references to expired requests and resources.

In Reactor, a sink's `onCancel` runs specifically for cancellation; `onDispose` applies to multiple termination types. If both are used, the cancel callback runs before dispose. When the source cannot pause, cleanup only stops delivery to the subscriber, while the external producer must still be managed separately.

## 8. Cancel in Spring WebFlux: Client Closes an SSE/HTTP Stream

Spring WebFlux typically receives a `Mono`/`Flux` **returned from a handler**, and the framework subscribes to the publisher according to the HTTP lifecycle. An SSE example:

File `src/main/java/demo/HeartbeatController.java`, using Java 17+ in a Spring Boot application with `spring-boot-starter-webflux`:

```java
package demo;

import java.time.Duration;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.SignalType;

@RestController
public class HeartbeatController {

    @GetMapping(value = "/heartbeat",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> heartbeat() {
        return Flux.interval(Duration.ofSeconds(1))
                .map(n -> ServerSentEvent.<String>builder()
                        .id(Long.toString(n))
                        .event("heartbeat")
                        .data("tick-" + n)
                        .build())
                .doFinally(signal -> {
                    if (signal == SignalType.CANCEL) {
                        System.out.println("SSE subscription cancelled");
                    }
                });
    }
}
```

**Usage:** place the controller in a package scanned by Spring Boot, run the server, and call `curl -N http://localhost:8080/heartbeat` (assuming port 8080). Each second, the publisher can emit an event with the corresponding data. Press Ctrl+C to disconnect the client.

**There is no guaranteed cancellation stdout at a precise moment**: disconnect detection also depends on the server, Netty, TCP, flushing, and schedulers. When WebFlux detects that the response subscription is no longer in use, it usually cancels the subscription; `doFinally(SignalType.CANCEL)` can log it. Closing a browser tab is not an immediate synchronous call into the controller's Java method.

Several important details:

1. **Each HTTP request has one subscription:** `Flux.interval(...)` creates a corresponding timer; cancelling one response usually cleans up that subscription's timer without cancelling other users' responses.
2. **Controllers return publishers:** do not manually call `.subscribe()` here and return `Mono.just("ok")`, because that breaks the binding between the HTTP lifecycle and the task.
3. **Transport-level cancel is not business cancel:** if the event stream has triggered data writes in an external system, client disconnect does not guarantee those writes are stopped.
4. **Buffering and flushing:** events may already be serialized/queued even if the subscriber cancels; do not claim that every byte still on the network will vanish instantaneously.
5. **Errors and completion differ from cancel:** on an unbounded SSE stream, user disconnection is typically related to cancellation; however, timeouts, exceptions, or server policies can produce other termination types.

### 8.1. Why Don't Independent HTTP Endpoints Auto-Cancel Each Other?

If a frontend sequentially calls `GET /search?q=a` and `GET /search?q=ab`, they are typically **two HTTP requests with two independent subscriptions**. The server does not automatically know the previous result is stale, so the second request does not automatically send a cancel to the first.

To achieve **latest-wins** behavior, the orchestrating layer must explicitly cancel the old request/subscription or use a shared event stream with an operator such as `switchMap`. When `switchMap` receives a new item, it cancels the **previous inner subscription**, though that is not a guaranteed rollback for a backend that already received the request. Distinguish between cancelling client processing, cancelling an HTTP subscription, and cancelling work on the server.

## 9. Cancel Involving `flatMap`, `switchMap`, and Child Publishers

A pipeline can contain multiple concurrently active publishers. Downstream cancellation does not just stop the outer source; publisher-composing operators must typically propagate cancel to **still-active inner subscriptions**.

### 9.1. `flatMap`

With `ids.flatMap(id -> remoteClient.fetch(id), concurrency)`, multiple inner requests can run concurrently within the allowed limit. When the final subscriber cancels, `flatMap` no longer needs results, so it requests cancellation of still-active inners and stops accepting further data.

However, a request that already reached the server can continue consuming CPU/database; therefore timeouts, connection pools, concurrency limits, and idempotency mechanisms are still needed. Do not use cancellation as a substitute for capacity planning.

### 9.2. `switchMap`

When `switchMap` receives a new outer value, it cancels the **old inner** in favor of the new inner. This is cancellation by **new intent**, distinct from downstream cancelling the entire stream. The outer subscription can still continue receiving subsequent updates.

Live search example: a new keyword makes the old HTTP request no longer worth waiting for. However, any results **already emitted downstream before the switch point** cannot be retracted; and the remote server may still process the old query even though the client stopped waiting.

### 9.3. `timeout`

If a source waits too long, `timeout(Duration)` can cancel the original source subscription. Downstream of the operator, the receiver typically sees a timeout error, or a fallback publisher if configured. In other words:

- **Source before timeout:** receives cancel because it is no longer waited on.
- **Downstream after timeout:** may receive `onError(TimeoutException)` or fallback results.

Do not infer “timeout is always equivalent to the client explicitly cancelling”; it is an **operator policy** and the downstream signal can differ.

### 9.4. `retry` and `repeat`

Retry typically re-subscribes to a cold publisher after an error; repeat typically re-subscribes after completion per contract. Cancellation prevents the pipeline from continuing unnecessary work, but does not undo previous subscriptions that already sent HTTP/DB requests. For side effects, you must have idempotency, auditing, and bounded retry counts.

## 10. How Does Backpressure Differ from Cancellation?

Both `request(n)` and `cancel()` flow from downstream to upstream, but they answer two different questions:

- `request(n)`: **“I still want data; I am currently able to receive n more elements.”**
- `cancel()`: **“I do not want any more data from this subscription.”**

If a subscriber merely runs out of outstanding demand, a Reactive Streams-compliant source stops emitting further `onNext` until a new request arrives. However, **the subscription stays alive**, resources or timers may continue to exist, and a remote operation may still be pending. Only cancel expresses the decision to terminate consumption of the subscription.

For example, if a consumer only needs the first avatar from `Flux<Image>`: use `next()` or `take(1)` to cancel the rest once a matching image is obtained. If a consumer needs to read the entire list but works slowly to process in batches, use demand/backpressure; do not cancel after every batch and re-subscribe if re-subscribing is expensive or loses position.

**Do not use `onBackpressureDrop()` instead of cancel.** Drop is a policy for discarding elements when demand cannot keep up; cancel is stopping the subscription. In transaction processing, dropping can lose business events whereas cancelling a request might simply mean stopping waiting for a response.

## 11. Special Resources: Buffers, I/O, Transactions, and External Work

### 11.1. Reference-Counted Buffers

Spring WebFlux/Netty can work with `DataBuffer` instances allocated from reference-counted memory pools. When cancellation causes elements already produced but not yet delivered downstream to be dropped, ensure buffers are released per the operator/adapter contract. In custom pipelines, you can consider `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` at discard-supporting positions, but **you must never manually release a buffer that is still owned or already released**.

Important rule: do not assume every operator automatically releases every application-created buffer, nor attach `release` arbitrarily causing double-release. Check the contracts of `DataBufferUtils`, Reactor discard support, and HTTP codecs for the version in use.

### 11.2. Blocking I/O and Virtual Threads

If a pipeline contains `Mono.fromCallable(() -> legacyJdbcCall())` running on `Schedulers.boundedElastic()`, a cancel signal to the subscription does not guarantee a blocking JDBC/driver call will stop immediately. Running on virtual threads does not change that operational characteristic either: threads are lighter in many I/O waiting scenarios, but SQL already sent to the DB still has the lifecycle of the DB and connection pool.

You need timeouts at the proper layer, driver cancellation if available, connection lifetimes, and concurrency limits. If a blocking API does not support interruption, cleanup must account for the case where the task still finishes after downstream leaves.

### 11.3. Transactions and Data Writes

Dangerous example:

1. Client sends an order-creation command.
2. Backend starts a transaction, writes records, or publishes events.
3. Client closes the tab or network drops, subscription is cancelled.
4. Backend may already have committed or continues processing; the client receives no response.

Do not deduce “cancel means the order was not created”. Retries from the client can create duplicates without an **idempotency key**, unique constraint, or status-verification rules. With reactive transactions, cancellation and rollback/cleanup require checking the contract of the transaction manager and publisher, especially when using `usingWhen` to manage resource lifecycles.

### 11.4. Shared Resources and Multiple Subscribers

If a `Flux` uses `share()`, `cache()`, or a hot sink serving multiple receivers, cancelling one subscriber may only remove that subscriber. The source keeps running because others need it or because of the hot source design. Closing a shared socket when one subscriber leaves can break the streams for the remaining subscribers.

Resources need **clear ownership**: per-subscription, per-request, per-user-session, or shared application-wide. Only cancel/close resources belonging to the exact lifecycle that needs to stop.

## 12. Testing Cancellation with StepVerifier

Checking only the result of `Flux.range(1,10).take(3)` is not enough to prove upstream actually received cancel. You can attach a counter near the source and use `StepVerifier` to control demand and cancellation timing.

Create `src/test/java/demo/CancellationPropagationTest.java` in a Java project with JUnit Jupiter and `reactor-test`:

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CancellationPropagationTest {

    @Test
    void downstreamCancelReachesSource() {
        AtomicInteger cancellations = new AtomicInteger();

        Flux<Integer> source = Flux.range(1, 10)
                .doOnCancel(() -> cancellations.incrementAndGet());

        StepVerifier.create(source, 0L)
                .expectSubscription()
                .thenRequest(2)
                .expectNext(1, 2)
                .thenCancel()
                .verify();

        assertEquals(1, cancellations.get());
    }

    @Test
    void takeCancelsUpstreamAfterEnoughItems() {
        AtomicInteger cancellations = new AtomicInteger();

        Flux<Integer> source = Flux.range(1, 10)
                .doOnCancel(() -> cancellations.incrementAndGet());

        StepVerifier.create(source.take(3))
                .expectNext(1, 2, 3)
                .verifyComplete();

        assertEquals(1, cancellations.get());
    }
}
```

**Dependencies:** `io.projectreactor:reactor-test` and JUnit Jupiter compatible with the Reactor/Spring Boot BOM. Use `./gradlew test` or `mvn test` depending on the project. With synchronous examples, assertions do not need to rely on `Thread.sleep(...)`.

Test explanation:

1. `StepVerifier.create(source, 0L)` uses an **initial demand of 0 on the test subscriber**, which is completely different from calling `Subscription.request(0)` (illegal).
2. `thenRequest(2)` requests exactly two elements and then `thenCancel()` sends cancel.
3. The `doOnCancel` callback placed right after the source receives this signal and increments the counter.
4. The second test shows `take(3)` **completes downstream**, while cancelling the source before it finishes emitting.
5. The counter reflects Reactor subscription cancellation, **not** that an external HTTP server or database has completely stopped.

For async or hot sources, extend tests with virtual time, publishers that record requests/cancellations, mock HTTP servers, and resource/callback checks after the subscriber leaves. Do not use a single “cancel” log line as proof that an external transaction rolled back.

### 12.1. Test Cases to Include in Production

- Downstream cancels **before receiving any element**: the source must clean up opened resources.
- Downstream cancels **after a few elements**: stop sending further useful data into the cancelled subscription, handle discarded buffered elements.
- Cancel **concurrently with complete/error**: cleanup does not execute twice or get skipped; code must be idempotent.
- Cancel while **an HTTP/DB request is in flight**: measure client and server resources; check whether the SDK/driver supports cancellation.
- Multiple subscribers sharing a publisher: cancelling one subscriber does not mistakenly close shared resources.
- Async cleanup error or timeout: proper observability, valid retry/compensation, and no resource leaks.
- Request **times out or client disconnects**: identify signal types at each point and what side effects already occurred.
- Very fast callback source: test overflow, buffering, and cancellation races rather than only using synchronous sources.

## 13. Common Reasoning Mistakes

| Misconception | What is true | How to handle it |
| --- | --- | --- |
| “Running out of demand means cancelled” | Outstanding demand of 0 only means no more has been requested yet | Use `cancel()` if the subscription is no longer needed |
| “Calling `cancel()` makes upstream emit `onComplete()`” | Cancel is a control signal; not a required terminal signal from the source | Observe `doOnCancel` or `doFinally(CANCEL)` near the source |
| “`take(3)` only emits three items so the source also completes normally” | The output of `take` completes, while a source with remaining data usually receives cancel | Place hooks both before and after `take` |
| “Cancel guarantees stopping HTTP server/JDBC immediately” | Local cancel may not stop work already dispatched externally | Timeouts, driver support, idempotency, and telemetry |
| “`onErrorResume` will catch cancel” | Cancel is not an error | Track via `doOnCancel`/`doFinally` |
| “`doOnTerminate` handles all termination paths” | It handles complete/error, not pure cancel | Use `doFinally` or `using/usingWhen` |
| “Just `doFinally(resource::close)` is enough in every case” | Cleanup may need to be per-subscription or async; callback order matters | Prefer `using/usingWhen` and clear ownership |
| “Client closed the tab so the DB write definitely hasn't committed” | Server-side side effects may have already completed | Check status/idempotency, do not assume rollback |
| “Cancelling one subscriber will stop a shared hot source” | The source may still serve other subscribers | Manage resources according to their true ownership scope |
| “Bypassing controller return with `subscribe()` and disposing at will is still safe” | Manual subscribing can detach the task from the HTTP lifecycle | Return the publisher to the framework |
| “Cancel is instantaneous so there can be no race” | In-flight work/signals can occur around cancellation time | Write idempotent cleanup, test concurrent races |
| “Retrying after cancel is always safe” | The old task may have already written data even though the client stopped waiting | Design idempotency and limit retries |

## 14. Process for Reading and Debugging a Pipeline with Cancel

When suspecting cancellation does not release resources, follow this analysis sequence:

1. **Identify who the final subscriber is.** Spring WebFlux, WebClient, a message consumer, a CLI app, or a custom `BaseSubscriber`?
2. **Identify the cause of cancellation.** Client disconnect, `take`, `next`, `switchMap`, `timeout`, explicit `dispose`, or shutdown?
3. **Map subscription boundaries.** Mark each `flatMap` inner, upstream source, `share/cache`, and shared resources.
4. **Place hooks in the right positions.** `doOnSubscribe`, `doOnCancel`, `doFinally` before/after operators that can cut off the source; add a request correlation ID.
5. **Observe cleanup.** Count active timers, open connections, queued tasks, buffered bytes, resource close counts, and transaction state.
6. **Distinguish the cancellation signal from outcomes outside the JVM.** If calling HTTP or DB, ask the server/driver whether the task actually stopped, finished, or committed.
7. **Test race scenarios.** Cancel right before a result arrives, after one element, during fallback/error, and concurrently with completion.
8. **Use controlled tests.** `StepVerifier` to verify Reactor signals; integration tests for networking and persistence.
9. **Apply lifecycle-accurate cleanup.** `using` for synchronous resources; `usingWhen` for async resources; `sink.onCancel/onDispose` for callback bridges; verify idempotency.
10. **Measure operational impact.** Under the same load, counts of subscriptions, connections, tasks, and heap after cancel should return to baseline; if not, locate where resources are retained.

There is no need to spawn a new thread per cancel, nor to use `block()` to wait for cleanup inside a WebFlux controller. Waiting for or coordinating cleanup must be expressed according to the publisher's lifecycle, especially when cleanup is asynchronous.

## 15. References

- [Reactive Streams Specification for the JVM](https://github.com/reactive-streams/reactive-streams-jvm): contracts of `Publisher`, `Subscriber`, `Subscription.request`, and `Subscription.cancel`.
- [Project Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/): sections on subscription, cancellation, `doFinally`, `using`, and resource lifecycle.
- [Project Reactor API – Flux](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): `doOnCancel`, `take`, `using`, and `usingWhen`.
- [Project Reactor API – Mono](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): `doFinally` and cleanup for Mono.
- [Project Reactor Testing](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): `StepVerifier` and signal testing.
- [Spring Framework – WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): response publishers, streaming, and HTTP lifecycle.
- [Spring Framework – Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html): managing `DataBuffer`, reference counting, and releasing resources.

## 16. Takeaways

**When downstream no longer needs data, it sends `cancel()` via the subscription; operators propagate this signal upstream so upstream can stop emitting and clean up resources when possible.** An operator like `take(3)` can cause downstream to complete normally while upstream receives cancel; this is intentional behavior.

Keep four things in mind:

1. **Cancel is different from running out of demand:** simply not requesting more does not mean the subscription is closed.
2. **Cancel is best-effort regarding actual work:** HTTP, JDBC, hot callbacks, and external transactions may keep running or have already finished.
3. **Put lifecycle management in the right place:** `doOnCancel`/`doFinally` to observe, `using`/`usingWhen` to manage resources, and return publishers to Spring WebFlux.
4. **Test both signals and resources:** confirm upstream receives cancel, cleanup runs once, and do not wrongly infer that side effects rolled back.

By understanding this propagation direction, you can build resource-efficient data streams, stop unnecessary tasks, and maintain correct behavior when clients disconnect midway.
