# Tracking Demand from Downstream to Upstream in Project Reactor

**Context:** Spring Framework – Reactive, topic **Backpressure**. This article explains how a subscriber expresses its capacity to receive data via `Subscription.request(n)`, how demand travels upstream through Reactor operators, and how to inspect the actual request flow. The concepts apply to `Flux`, `Mono`, and pipelines used by Spring WebFlux.

## 1. Why Track Demand?

Suppose a source emits 50,000 events per second, while the final processor can only handle 1,000 events per second. If the source keeps sending without limit, unprocessed data will accumulate in queues or memory. When buffers are exhausted, the application can suffer increased latency, excessive RAM consumption, buffer overflow errors, or crashes.

**Backpressure** is the mechanism that allows the consumer (*downstream*) to express how many more elements it is ready to receive from the producer (*upstream*). In Reactive Streams, this signal is primarily transmitted via the `request(long n)` method on `Subscription`.

Two directions of travel must be distinguished:

- **Data and terminal signals**: from upstream to downstream, consisting of `onNext(item)`, `onError(error)`, `onComplete()`.
- **Control**: from downstream to upstream, most importantly `request(n)` and `cancel()`.

```text
  Data direction:
  Source  ----onNext/onError/onComplete----> Operator ----> Subscriber
    ^                                         ^                |
    |                                         |                |
    +------------ request(n) / cancel --------+----------------+
                Upstream control direction
```

**Demand** is the number of additional elements permitted to be emitted at a subscription boundary—not the number of elements currently stored in memory, the requests-per-second rate, the thread count, the byte size, or the size of an HTTP request. `request(10)` means "I allow receiving up to 10 more elements under the Reactive Streams contract"; it does not mean "send exactly 10 elements immediately".

A valid source may emit **fewer** than the requested count if no more data remains, an error occurs, it is cancelled, or it is not ready yet. A finite source can complete normally even if excess demand remains.

## 2. Components That Make Up the Request Mechanism

Reactive Streams defines the following roles:

| Component | Role | Main API |
| --- | --- | --- |
| `Publisher<T>` | Provides signals to subscribers according to registered demand | `subscribe(Subscriber<? super T>)` |
| `Subscriber<T>` | Receives the subscription and signals from the publisher | `onSubscribe`, `onNext`, `onError`, `onComplete` |
| `Subscription` | Links a specific subscriber with a publisher; controls requested element count and cancellation | `request(long n)`, `cancel()` |
| Reactor `Flux<T>` | Publisher emitting 0 to many elements | Operators such as `map`, `buffer`, `flatMap` |
| Reactor `Mono<T>` | Publisher emitting at most one element then completing or erroring | `map`, `flatMap`, `then`, ... |
| Intermediate operator | Consumes data from upstream while providing data to downstream | Forwards or transforms `request` and signals |

Typical lifecycle:

1. Downstream subscribes to the publisher.
2. Downstream receives `onSubscribe(subscription)` to gain the ability to `request` or `cancel`.
3. Downstream calls `subscription.request(n)` with a **positive** number when ready.
4. Upstream only emits `onNext` within the valid demand on that subscription; operators forward signals and may transform sizes/requests.
5. Downstream can call `request(n)` again; when the source runs out of data, it emits `onComplete`; on error, it emits `onError`; when no longer needed, it calls `cancel()`.

Within a subscription, the sequence of data callbacks has the general form `onSubscribe → onNext* → (onComplete | onError)?`. After a terminal signal, the subscription stops emitting data. `cancel()` requests stopping, though the cancellation effect may not be immediate and does not undo side effects that have already occurred.

**Key point:** an operator can be a subscriber to the immediately preceding source and a publisher to the immediately following stage. Therefore, "downstream" and "upstream" are **relative relationships based on position in the pipeline**; the same operator can receive `request` from behind and generate a different `request` for the stage ahead.

## 3. Tracking Outstanding Demand: Add `request`, Subtract `onNext`

Suppose a subscriber has not requested any elements yet. It calls:

```text
request(2)       outstanding demand = 2
onNext(A)        outstanding demand = 1
onNext(B)        outstanding demand = 0
request(3)       outstanding demand = 3
onNext(C)        outstanding demand = 2
onNext(D)        outstanding demand = 1
```

At the exact **subscription boundary under consideration**, the intuitive formula is:

```text
outstanding = total elements requested - total valid onNext received
```

Calls to `request(n)` **accumulate** with unused demand. Calling `request(2)` and `request(3)` before receiving data allows up to 5 `onNext` signals at that boundary. They do not replace each other and do not limit the source to only 3.

A Reactive Streams–compliant publisher must not send `onNext` exceeding outstanding demand. However, it may send fewer if there is no data; `onComplete` or `onError` is not an `onNext` element and does not "consume" a unit of demand to terminate.

### 3.1. `request(n)` Must Be Positive

- `request(1)`: ask for one more element.
- `request(64)`: allow emitting up to 64 more elements.
- `request(Long.MAX_VALUE)`: treated as **effectively unbounded demand** (*unbounded demand*) in Reactor.
- `request(0)` or `request(-1)`: **invalid** according to Reactive Streams. When the subscription has not been cancelled, this is a violation and is reported via `onError` with `IllegalArgumentException`; do not use `request(0)` as a "pause" command.

If you do not want to receive elements yet, hold the subscription and **do not send a request yet**. If you no longer need data, use `cancel()`. If you want to slow the pace, request in sufficiently small batches, finish processing, and then ask for more. Do not request a "negative number" to return granted demand.

For very large numbers, demand is handled with saturation at `Long.MAX_VALUE` to prevent integer overflow in compliant implementations. Once treated as unbounded, upstream may emit as fast as remaining constraints allow; the risk of overload on non-backpressure-aware sources still exists.

### 3.2. `request` Can Trigger Synchronous or Asynchronous Emission

In `Flux.range(...)`, a single `request(2)` can cause two `onNext` callbacks to run **immediately within the request call**. With an asynchronous I/O source like `WebClient`, the request expresses readiness to receive, but data only arrives after the connection/source actually emits.

Therefore, do not assume that:

- `request(5)` will block until 5 elements are received;
- each `request` creates exactly one network batch;
- all `request`/`onNext` signals occur on the same thread;
- the `request` count measured near the source equals the `request` count of the final subscriber.

## 4. Runnable Java 17+ Example: Batch Requests and Observing the Upstream Direction

The following standalone example uses `Flux.range(...)`, `BaseSubscriber`, and `doOnRequest(...)` to clearly show when downstream asks for more elements and what quantities upstream receives.

Create the file `src/main/java/demo/DemandFlowDemo.java`:

```java
package demo;

import java.util.List;
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public final class DemandFlowDemo {

    public static void main(String[] args) {
        System.out.println("=== Batch demand ===");

        Flux<Integer> numbers = Flux.range(1, 5)
                .doOnRequest(n ->
                        System.out.println("source request(" + n + ")"));

        BaseSubscriber<Integer> subscriber = new BaseSubscriber<>() {
            @Override
            protected void hookOnSubscribe(Subscription subscription) {
                System.out.println("onSubscribe, no data requested yet");
            }

            @Override
            protected void hookOnNext(Integer value) {
                System.out.println("onNext " + value);
            }

            @Override
            protected void hookOnComplete() {
                System.out.println("onComplete");
            }
        };

        numbers.subscribe(subscriber);
        System.out.println("after subscribe");

        System.out.println("subscriber request(2)");
        subscriber.request(2);

        System.out.println("subscriber request(1)");
        subscriber.request(1);

        System.out.println("subscriber request(2)");
        subscriber.request(2);

        System.out.println("=== Three-element buffer ===");

        Flux.range(1, 6)
                .doOnRequest(n ->
                        System.out.println("source-stage request(" + n + ")"))
                .buffer(3)
                .doOnRequest(n ->
                        System.out.println("buffer-stage request(" + n + ")"))
                .subscribe(new BaseSubscriber<List<Integer>>() {
                    @Override
                    protected void hookOnSubscribe(Subscription subscription) {
                        System.out.println("subscriber requests 2 buffers");
                        request(2);
                    }

                    @Override
                    protected void hookOnNext(List<Integer> values) {
                        System.out.println("onNext buffer " + values);
                    }

                    @Override
                    protected void hookOnComplete() {
                        System.out.println("onComplete buffer");
                    }
                });
    }
}
```

**How to run:** requires Java 17+, the `reactor-core` library, and a compatible `reactive-streams` dependency. In a Spring Boot project with `spring-boot-starter-webflux`, the required libraries are usually already present and you can run `main` from your IDE. If compiling manually, place the required JARs into the `lib/` directory and create the output directory:

```bash
# Linux / macOS; run from the project root directory
mkdir -p out
javac -cp "lib/*" -d out src/main/java/demo/DemandFlowDemo.java
java -cp "out:lib/*" demo.DemandFlowDemo
```

```powershell
# Windows PowerShell; run from the project root directory
New-Item -ItemType Directory -Force out
javac -cp "lib/*" -d out src/main/java/demo/DemandFlowDemo.java
java -cp "out;lib/*" demo.DemandFlowDemo
```

**Exact stdout** with the synchronous publisher in the example:

```text
=== Batch demand ===
onSubscribe, no data requested yet
after subscribe
subscriber request(2)
source request(2)
onNext 1
onNext 2
subscriber request(1)
source request(1)
onNext 3
subscriber request(2)
source request(2)
onNext 4
onNext 5
onComplete
=== Three-element buffer ===
subscriber requests 2 buffers
buffer-stage request(2)
source-stage request(6)
onNext buffer [1, 2, 3]
onNext buffer [4, 5, 6]
onComplete buffer
```

Explanation:

1. `BaseSubscriber` lets you decide demand yourself. Overriding `hookOnSubscribe` in the example **does not call request**, so after `numbers.subscribe(subscriber)`, the source has not emitted `onNext` yet; the `after subscribe` line is printed first.
2. `subscriber.request(2)` sends two units of demand to the `Flux.range` source. `doOnRequest` logs near the source, and then the source emits 1 and 2. After that, demand is exhausted, so it pauses.
3. When asking for 1 more, the source only emits 3. When asking for 2 more, the source emits 4 and 5, then completes.
4. The `buffer(3)` part turns **3 integers into one list**. The final subscriber requests 2 **lists**, so the `buffer` stage needs to pull **6 integers** from the source. Therefore, the logs at the two locations show different request counts: `2` downstream of `buffer`, `6` upstream of it.
5. The code does not create a scheduler or asynchronous I/O; since the source is synchronous, the log order above is deterministic. With `publishOn`/`flatMap` or a network source, logs from multiple threads can interleave, and you should not deduce ordering from this synchronous example.

**Warning when writing your own subscriber:** `BaseSubscriber` requests unbounded by default if you do not override `hookOnSubscribe`. Overriding it while forgetting to call request or forgetting to arrange a mechanism to request more can leave a `Flux` waiting forever. The example intentionally requests from `main` to make the demand quantities clear, and does not represent a subscriber lifecycle in production WebFlux.

## 5. Why Can Demand Change When Passing Through an Operator?

Downstream demand does not necessarily travel straight upstream with the same number. Each operator knows how it transforms elements and can adjust requests to supply enough output data, perform prefetching, or manage buffers.

Consider the pipeline:

```java
Flux<List<Integer>> batches = Flux.range(1, 100)
        .doOnRequest(n -> System.out.println("near source: " + n))
        .buffer(5)
        .doOnRequest(n -> System.out.println("near subscriber: " + n));
```

If downstream wants **2 elements of type `List<Integer>`**, `buffer(5)` needs up to **10 `Integer` elements** upstream. The result of this example is `request(2)` near the subscriber but `request(10)` near the source. This is a contract conversion of **element units across each boundary**.

| Operator | Downstream demand meaning | What can happen upstream |
| --- | --- | --- |
| `map` | One output element corresponds to one input element | Usually keeps a 1:1 quantity relationship; asynchronicity may still exist elsewhere |
| `filter` | Only elements matching the predicate pass through | May request more to compensate for dropped elements |
| `buffer(k)` | One downstream `onNext` contains up to `k` upstream elements | Can multiply demand; e.g., 2 buffers x 5 elements = 10 inputs |
| `flatMap` | One outer element creates an inner publisher that can emit many elements | Can have multiple inner subscriptions and prefetch; request counts are not necessarily 1:1 |
| `concatMap` | Tracks inner publishers sequentially | Has requesting and buffering mechanisms depending on the operator/version |
| `publishOn` | Shifts downstream processing to another scheduler | Uses a queue and prefetch to decouple when upstream emits and downstream processes |
| `take(k)` | Needs at most `k` downstream elements | Can cap emission and cancel upstream once enough elements are received |
| `limitRate(highTide, lowTide)` | Splits a large request into smaller batches upstream | Requests in batches and replenishes gradually, which can reshape request logs |

Do not memorize "each subscriber request corresponds to one upstream request". You need to **place measurement points around each operator** to see exactly where demand is transformed.

### 5.1. `buffer`: Changing Element Units

`buffer(5)` does not create additional business data, but turns five individual elements into one list. Downstream asking for 2 units means **2 lists**, corresponding to a demand for more original elements.

Meanwhile, `window(5)` creates inner publishers, causing both window subscriptions and inner consumption to affect behavior; it should not be assumed to always be equivalent to `buffer(5)` in timing and memory. `groupBy` also creates group publishers, requiring consumption management for each group to avoid buildup.

### 5.2. `filter`: Compensating for Dropped Elements

If the source is `Flux.range(1, 10).filter(n -> n % 2 == 0)` and downstream requests three even values, the source may have to read more than three integers because odd numbers are not forwarded downstream. Reactor can adjust demand to compensate for discarded data. Therefore, request counts logged before and after `filter` are not necessarily identical, especially when combining operators or under fusion modes.

### 5.3. `flatMap`, `concatMap`, and Prefetch

Operators that merge inner publishers can pre-request a batch of data from the inner or outer publisher to keep the pipeline running efficiently. The **prefetch** parameter is the expected number of elements requested ahead at the corresponding boundary, and many operators have a **replenishment** strategy: once part of the batch is consumed, more is requested before the batch runs completely dry.

Example:

```java
Flux<String> result = ids.flatMap(
        id -> remoteClient.fetchOne(id),
        8   // Limit the number of concurrent inner publishers
);
```

The snippet above is **illustrative code only**; `ids` and `remoteClient` must be provided by the application. The `concurrency=8` limit helps control the number of active inner publishers within `flatMap`, but does not automatically mean there are at most eight HTTP connections for the entire application. Inner request counts, connection pool sizes, scheduler queues, and load on other services still need to be measured separately.

With some overloads of `flatMap`, `concatMap`, and `publishOn`, `prefetch` can be configured. **Do not try to guess a fixed default value for every operator or every Reactor version**. Check the API of the version actually in use, set values according to memory/throughput goals, and re-measure under real load.

## 6. Tools for Observing Demand in Reactor

### 6.1. `doOnRequest`: Measuring Requests at a Boundary

`doOnRequest(LongConsumer)` is the most useful observation point for this problem. The callback runs when the operator **receives** a request from downstream, before forwarding that request upstream. This logs the **demand arriving at the boundary where the operator is placed**, not the number of elements guaranteed to be emitted and not necessarily the initial demand of the final subscriber.

```java
Flux<Integer> pipeline = Flux.range(1, 50)
        .doOnRequest(n -> System.out.println("A near source: " + n))
        .buffer(5)
        .flatMapIterable(list -> list)
        .doOnRequest(n -> System.out.println("B near consumer: " + n));
```

This is an illustrative example of where to place logs. `flatMapIterable` can alter how upstream requests are made, so **do not predict the exact log sequence in advance** for this pipeline; use it to observe actual request counts when running with a subscriber that has known demand.

A placement diagram:

```text
Flux source
   |
doOnRequest("A")   <- request right before source
   |
buffer(5)
   |
flatMapIterable(...)
   |
doOnRequest("B")   <- request at output
   |
Subscriber
```

When the subscriber calls `request(2)`, `B` observes the demand at the output. `A` may receive a different number because of the intermediate operators. In signal direction, **onNext flows A → B** while **request flows B → A**.

### 6.2. `doOnNext`, `doOnCancel`, `doFinally`, and `log()`

To understand *how much was requested* and *how much was received*, you can place an observation pair:

```java
return source
        .doOnRequest(n -> metrics.recordRequest(n))
        .doOnNext(value -> metrics.recordReceived())
        .doOnCancel(metrics::recordCancel)
        .doFinally(signal -> metrics.recordEnd(signal));
```

This is an **illustrative snippet inside a service**, where `source` and `metrics` are defined by the system. `doOnRequest` is a callback for each request, `doOnNext` runs for each element, `doOnCancel` observes cancellation, and `doFinally` indicates termination via completion/error/cancel.

Note carefully:

- The sum of numbers received via `doOnRequest` is **signal demand** at the log point, not an actual queue, and cannot directly measure internal buffer occupancy.
- `doOnNext` indicates an element has passed the measurement point, not that final business logic has committed.
- A source may be requested for many elements yet emit few due to early completion. Conversely, a hot source that ignores demand may require a separate drop/buffer policy.
- `doFinally` can run after the terminal signal has moved downstream to the subscriber; do not use log ordering across threads as sole evidence.
- Reactor's `log()` can help inspect `request`, `onNext`, `cancel`, and terminal signals in development environments. Under heavy load, per-element logging is expensive and risks exposing data; choose an appropriate scope and log level.

For production metrics, measure **queue/buffer depth**, active publisher/subscription counts, elements emitted/received/dropped, overflows, pool wait time, heap, GC, p95/p99 latency, and error rates. These numbers answer whether backpressure keeps resources under control, rather than looking at a single `request(n)` in isolation.

### 6.3. Why Does `subscribe(value -> ...)` Often Log Very Large Demand?

Many lambda-based `subscribe()` overloads and blocking calls like `block()`/`blockLast()` **request unbounded** by default (equivalent to `Long.MAX_VALUE` in Reactor). This is convenient for consuming simple sequences, but is not suitable when the goal is to control individual request batches yourself.

If you want to see small batches, use `BaseSubscriber` and explicitly call `request(n)`, or use the test tool `StepVerifier.create(publisher, initialRequest)`. The fact that `Mono` holds at most one value does not itself prove the source has end-to-end backpressure; how subscriptions and underlying I/O behave still matters.

## 7. Throttling Upstream Requests with `limitRate`

Reactor provides `limitRate(...)` to split a large downstream request into smaller batches when pushing upstream. Example:

```java
Flux<Integer> boundedRequests = Flux.range(1, 1000)
        .doOnRequest(n -> System.out.println("near source: " + n))
        .limitRate(10, 0);
```

If the final subscriber requests a very large number of elements, `limitRate(10, 0)` lets the operator request from upstream in **batches of at most 10**. `lowTide=0` selects strict batching mode (*strict batching*): after consuming a batch, it requests the next batch according to remaining demand; it does not use the early replenishment strategy of the default mode.

With `limitRate(10)`, the operator can replenish part of the demand ahead of time once enough of the batch has been consumed, rather than strictly waiting until empty before requesting a new round. The `limitRate(highTide, lowTide)` overload lets you tune the initial batch threshold and replenishment threshold; you must verify the semantics for the Reactor version in use.

**Do not confuse `limitRate(10)` with "10 elements/second".** It splits request quantities by **batch size**; it does not add a clock to throttle throughput over time. A very fast synchronous publisher can still emit thousands of elements per second via batches of 10.

Nor should you deduce a heap limit of exactly 10 elements: other operators, HTTP/Netty buffers, internal data, inner publishers, and serialization can require additional memory. When using `limitRate`, you also need to measure the actual data flow.

For stopping after a certain number of elements, `take(n)` has a different contract: it **caps the number of output elements and can cancel upstream once satisfied**. `limitRate` does not itself shorten the total number of elements from the source.

## 8. Sources That Do Not Slow Down on Request: When Backpressure Can Only Buffer, Drop, or Error

Reactive Streams requires publishers to honor demand at the subscriber boundary, but not every external data source can actually **slow down its emission rate**. Examples: measurement devices, hot callback streams, continuous UI events, eager message brokers, UDP, or an HTTP service that has already started computing. Cancelling or not requesting more on the receiving end does not guarantee the actual source stops producing data.

In this case, the adapter can choose a policy:

| Policy | Meaning | What Must Be Accepted |
| --- | --- | --- |
| **Source throttling** | Pause the producer, limit concurrency, or control the source via demand if the protocol allows | Requires real API support; may reduce throughput |
| **Bounded buffer** | Temporarily hold a number of elements for downstream to process later | Uses memory; must have an overflow policy when full |
| **Drop** | Discard elements that cannot be received | Data loss; only suitable for droppable telemetry/previews |
| **Latest** | Keep the newest element when the receiver is slow | Intermediate values lost; unsuitable for transaction recording |
| **Error/Reject** | Signal an error when unable to keep up | Downstream must handle failure and recover |
| **Durable queue** | Decouple ingestion and processing via a broker/persistent queue | Has limits, operational cost, requires ack/retry/idempotency |

Some related Reactor operators:

- `onBackpressureBuffer(...)`: buffers elements when downstream has not caught up; prefer configuring a **bounded capacity** and an appropriate overflow policy; an unbounded buffer can lead to out-of-memory errors.
- `onBackpressureDrop(...)`: can drop elements when no demand remains.
- `onBackpressureLatest()`: keeps the latest value in certain slow-downstream situations; **does not preserve every event**.
- `onBackpressureError()`: signals an error when the data stream exceeds demand capacity.
- `Flux.create(...)` and `Sinks.Many`: must check the overflow/backpressure strategy of the adapter or sink, especially when a hot source pushes data regardless of request.

These policies **do not unconditionally make the data contract right**. If the business domain requires that no payment/order/audit event ever be lost, do not choose drop/latest just to make overload warnings disappear; you need a reliable queue, source control, and idempotent processing.

### 8.1. An Example of a Wrong Decision

A `Flux<PaymentCommand>` emits 500 commands/second while downstream can process 100 commands/second. Attaching `onBackpressureLatest()` might make the system "stable" in memory while **dropping payment commands**. That is a serious business bug.

Conversely, a `Flux<MousePosition>` used to draw a cursor on screen can discard intermediate positions and keep only the latest position, if that is the desired UX. It is the same throttling technique, yet correctness depends on the **meaning of each element**.

## 9. Direct Connection to Spring WebFlux

In Spring WebFlux, a handler typically **returns a `Mono` or `Flux`**. The framework subscribes to the publisher according to the HTTP lifecycle to write the response and handle completion/error/cancellation. Services/controllers generally should not manually call `subscribe()` to push the response via out-of-band side effects.

The following Server-Sent Events (SSE) endpoint illustrates where to place a demand measurement point at the controller layer:

File `src/main/java/demo/ItemStreamController.java`, in a Spring Boot project with `spring-boot-starter-webflux`:

```java
package demo;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
public class ItemStreamController {

    @GetMapping(value = "/stream/items",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<Integer>> stream() {
        return Flux.range(1, 20)
                .doOnRequest(n ->
                        System.out.println("source sees request(" + n + ")"))
                .map(i -> ServerSentEvent.<Integer>builder()
                        .data(i)
                        .build());
    }
}
```

This is a **complete controller inside a running application**, not a standalone application with a `main` method. Start Spring Boot and call `curl -N http://localhost:8080/stream/items` while the server is running on port 8080 to view the event stream. Data may be sent as SSE `data:1`, `data:2`, ...; there is no fixed console stdout for the `request(...)` lines because request quantities depend on the HTTP adapter, runtime, and connection state.

Key takeaways:

1. WebFlux subscribes to the returned publisher to write the response; the publisher does not need to be manually subscribed to inside the controller.
2. `doOnRequest` observes the demand sent upward by **the chain downstream of it**, after passing through the HTTP bridge and downstream operators.
3. A slow-reading HTTP client does not mean the application will receive exact sequential `request(1)` calls for each event. The framework, Netty, TCP, decoder, scheduler, and buffers at each layer have their own mechanisms.
4. On a real system, the source may be data from a reactive repository, broker, or device. Only when the layers along the path can cooperate does demand actually help **reduce the amount of work generated** rather than merely shifting buffering to another layer.
5. If the client closes the connection, the system normally needs to cancel the subscription and release resources, though you must check the specific adapter; a blocking task or remote operation may not stop immediately.

**Do not claim "WebFlux automatically guarantees end-to-end backpressure for every HTTP API".** Reactive Streams manages **protocol-compliant publishers/subscribers within the pipeline**; propagating pressure across the network, HTTP bodies, database clients, brokers, and devices is an integration concern. A JSON endpoint using `collectList()` can even gather the entire result into memory before serialization, eliminating the expected streaming benefits.

### 9.1. How Can `WebClient` and Reactive Databases Be Affected?

When using `WebClient.bodyToFlux(...)`, downstream requests can influence the pace of body reading/decoding depending on the HTTP connector, codec, and buffering. However, `request(n)` counts cannot be equated to the number of TCP packets or database rows returned by the server. Some servers have already generated the data, some drivers read in batches, and some protocols do not support a corresponding pause.

With R2DBC or reactive messaging, you must read the specific driver and adapter contract: implementations may use fetch sizes, cursors, prefetching, or internal buffers. Tracking demand helps evaluate the Reactor pipeline, but you need additional metrics at the **connection pool, driver, broker, and upstream service** to know whether pressure is propagating across system boundaries.

## 10. Testing Controlled Demand with `StepVerifier`

Why is just running `subscribe(System.out::println)` not enough? Because lambda-based `subscribe` calls usually **request unbounded**. They do not prove that a publisher respects small requests or that an operator transforms demand as expected.

`reactor-test` provides `StepVerifier.create(publisher, initialRequest)` to initialize demand and request more step by step. The following test verifies that `buffer(3)` requires six input elements to emit two output lists.

File `src/test/java/demo/DemandFlowTest.java`:

```java
package demo;

import java.util.List;
import java.util.concurrent.atomic.AtomicLong;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class DemandFlowTest {

    @Test
    void requestsTravelUpstreamInBufferUnits() {
        AtomicLong upstreamRequested = new AtomicLong();

        Flux<List<Integer>> batches = Flux.range(1, 6)
                .doOnRequest(upstreamRequested::addAndGet)
                .buffer(3);

        StepVerifier.create(batches, 0L)
                .expectSubscription()
                .thenRequest(1)
                .expectNext(List.of(1, 2, 3))
                .thenRequest(1)
                .expectNext(List.of(4, 5, 6))
                .verifyComplete();

        assertEquals(6L, upstreamRequested.get());
    }
}
```

The test requires the `io.projectreactor:reactor-test` dependency and JUnit Jupiter. For a Gradle project using the Spring Boot BOM, let the BOM manage the appropriate versions; run `./gradlew test` (Linux/macOS), `.\gradlew.bat test` (Windows), or run from your IDE. If using Maven, configure the corresponding test dependencies and run `mvn test`.

Test explanation:

1. `initialRequest=0L` is an **internal `StepVerifier` parameter to refrain from automatically requesting elements upon subscription**, **not** a call to `Subscription.request(0)` (which is forbidden).
2. The first `thenRequest(1)` asks for one **list**; `buffer(3)` requests three numbers from the source to form the first list.
3. The second `thenRequest(1)` asks for the remaining list; the total requested at the source is six.
4. `verifyComplete()` confirms that the publisher completes normally without over-emitting. `assertEquals` verifies the demand observed near the source.

With asynchronous sources, you can add `expectNoEvent(...)` to verify no emission before a request, use virtual time for timers, and use a test publisher that records request/cancel signals. Do not write tests relying solely on `Thread.sleep(...)` to time the event loop.

### 10.1. Assumptions That Need Separate Tests

Depending on the use case, add tests for the following requirements:

- **No initial demand:** the publisher emits no `onNext` when the subscriber has not requested elements yet.
- **Cumulative demand:** two consecutive requests of `2` and `3` allow up to five additional elements.
- **Post-operator bounds:** `buffer`, `filter`, `flatMap`, or `publishOn` can make upstream requests differ from downstream requests.
- **Cancellation:** when the subscriber cancels, the source receives the cancel signal; whether external work actually stops must be tested in separate integration tests.
- **Hot sources:** when the producer is faster than the consumer, the right overflow/drop/latest/error policy is applied without violating data-loss expectations outside the contract.
- **Payload size:** even when element count is bounded, a single element that is a large list/image can still exhaust memory; check both bytes and heap.

## 11. Real-World Scenario Analysis

### Scenario A: Processing Database Records

A service reads records one by one and validates data. Downstream can only process a small group at a time. If the driver and adapter support it, limiting demand/prefetch can reduce the number of records waiting in the JVM. However, if the database query always materializes the entire result before returning, Reactor only reduces pressure **after materialization**, without eliminating memory cost in the driver or database.

What to observe: rows read and buffered, fetch size/cursor, query time, active connections, processing queue, commit rate, and transaction hold time.

### Scenario B: Streaming Events for a Dashboard

A dashboard only needs the most recent sensor value. The source emits faster than the browser can render. `onBackpressureLatest()` or a sampling strategy can be appropriate if **losing intermediate points is acceptable**. If the dashboard displays audit data requiring every single event, drop/latest strategies are wrong; use durable storage/queues with replay and controlled consumption.

What to observe: lag between source timestamp and display, dropped event count, buffer memory, disconnect duration, and ability to resynchronize after reconnect.

### Scenario C: Batching Before Calling an API

A service must batch 50 items into one request. Downstream asking for 2 batches may require up to 100 items upstream; the number "2" in downstream logs does not mean production has been limited to two original records. If the backend only tolerates 10 concurrent requests, you also need to control concurrency and pools, rather than merely reducing the number of requested buffers.

What to observe: items per batch, wait time for a full batch, in-flight batches, HTTP call count, timeouts, and the distinction between **batch** demand and **item** demand.

### Scenario D: Suddenly Slow Subscriber

A properly implemented source can stop emitting `onNext` at the boundary where demand is lacking. However, a producer that cannot pause may continue emitting into an intermediate buffer; the queue will fill up. You need an explicit decision: stall the producer, buffer boundedly then error, or drop elements that are safe to lose. Configuring automatic retries after overflow can amplify pressure even further without backoff and limits.

## 12. Common Misconceptions

| Misconception | Fact to Remember |
| --- | --- |
| "`subscribe()` always limits the amount of data automatically" | Many Reactor lambda `subscribe` overloads request `Long.MAX_VALUE`; for bounded requests you must control demand yourself |
| "`request(0)` pauses the stream" | `request(0)` is invalid; simply **do not call request** to keep demand at 0 |
| "`request(5)` guarantees exactly 5 items" | A publisher may emit fewer if it completes/errors; `request` is the maximum allowed to be emitted |
| "Once requested, `onNext` must arrive immediately" | Async sources may still be waiting on I/O or new data |
| "Every subscriber request is an identical request to the source" | `buffer`, `filter`, `flatMap`, `publishOn`, and prefetch can transform requests |
| "`doOnRequest` shows how many elements are sitting in the queue" | It only logs the demand signal at that operator's position |
| "`Long.MAX_VALUE` means the JVM has enough memory for infinite elements" | It is unbounded demand, not a resource guarantee |
| "`limitRate(10)` limits to 10 elements/second" | It splits request batch sizes; it does not install a rate-limiting clock |
| "Having backpressure in Flux means TCP/DB/broker stops immediately too" | Backpressure only propagates where the adapter/protocol supports it; other layers have buffers or keep running |
| "`onBackpressureBuffer()` is always safe" | Unbounded buffers can run out of memory; configure capacity and an overflow policy |
| "You can drop events to shed load without affecting results" | Only true for data types allowed to be lost; wrong for transactions/records requiring completeness |
| "Cancelling a subscription rolls back business work" | Cancellation does not automatically undo external work or side effects that already occurred |

## 13. Checklist for Tracking Demand in a Real Pipeline

1. **Identify the final subscriber boundary.** Who subscribes: WebFlux framework, Reactor Test, a message consumer, or custom code? Does it automatically request unbounded?
2. **Trace the path of `request`.** Place `doOnRequest` downstream and near upstream, noting the element type at each point: item, list, window, inner publisher.
3. **Find demand-altering operators.** Inspect `buffer`, `filter`, `flatMap`, `concatMap`, `publishOn`, `take`, `limitRate`, and prefetch settings.
4. **Inspect the source.** Is it a cold demand-aware source like `Flux.range`, a reactive driver, a hot callback, a shared sink, or a blocking SDK wrapped as a publisher? Can it stop emitting?
5. **Set resource bounds.** Active inner count, queue/buffer size, connection pool, heap, timeouts, and overload strategy.
6. **Observe outcomes.** Compare requested, emitted, processed, dropped, and errored counts; do not draw conclusions from a single `request(n)` number alone.
7. **Test with small demand.** Use `StepVerifier.create(source, 0L)`, `thenRequest(n)`, verify counts are not exceeded, and verify proper cancellation.
8. **Load test realistically.** Increase concurrency and artificially slow down downstream; measure p95/p99, heap, GC, queue length, and recovery time.
9. **Preserve business correctness.** If every event must be processed, use durable ingestion/buffering and proper idempotency; do not choose drop/latest out of convenience.

## 14. Authoritative References

- [Reactive Streams Specification for the JVM](https://github.com/reactive-streams/reactive-streams-jvm): defines `Publisher`, `Subscriber`, `Subscription.request(n)`, cancellation, and demand limits.
- [Project Reactor Reference – On Backpressure and Ways to Reshape Requests](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html): how demand travels upstream, `BaseSubscriber`, `buffer`, prefetch, and `limitRate`.
- [Project Reactor API – Flux](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): look up signatures/operators `doOnRequest`, `limitRate`, and the backpressure operator family for your version.
- [Spring Framework – WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): reactive HTTP runtime, request/response publishers, and non-blocking integration.

## 15. Conclusion

In Project Reactor, **backpressure starts with downstream demand**. The subscriber receives a `Subscription` and requests a number of elements via `request(n)`; the demand signal travels **upstream** through operators and may be adjusted before reaching the source. `onNext` data travels in the opposite direction and must respect demand on each subscription.

The two most important practical lessons are:

1. **Observe at multiple points:** `doOnRequest` next to the subscriber and next to the source can report different numbers because `buffer`, `filter`, prefetch, and merging operators reshape demand.
2. **Do not confuse a request signal with system-wide flow control:** Reactor can manage demand for compatible publishers, while hot sources, HTTP, databases, brokers, and blocking work still depend on their own adapters, buffers, and limits.

When facing an overloaded pipeline, measure **demand → emission → processed → queued → errors/drops**, and then choose where to bound concurrency, queues, or the emitting source. That is how backpressure keeps a system stable while upholding business obligations.
