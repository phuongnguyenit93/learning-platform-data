# Roles of Publisher, Subscriber, Subscription, and Processor

## 1. Context: What Problem Does Reactive Streams Solve?

**Reactive Streams** is a specification for how components exchange **asynchronous** streams of data with **backpressure** (the receiver controls the number of items permitted to be sent). It is a *communication contract* between components, not a stream-processing library or a mechanism that automatically spawns threads for parallel execution.

In the Java/Spring WebFlux ecosystem, the core interfaces live in the `org.reactivestreams` package: `Publisher<T>`, `Subscriber<T>`, `Subscription`, and `Processor<T, R>`. Project Reactor implements this model through `Flux` (0..N items) and `Mono` (0..1 item). Java also has similar interfaces in `java.util.concurrent.Flow`; the names are the same, but they are **different Java types/packages** and cannot be interchanged directly without an appropriate adapter.

The goal of the contract: a fast-producing source must not overwhelm a slow receiver by sending more `onNext` signals than the receiver has requested. Backpressure is coordination of **demand for receiving data**; it does not mean every operation across the entire system is non-blocking or automatically memory-efficient.

## 2. Responsibilities of the Four Interfaces

| Component | Role | Core Methods | Key Takeaway |
|---|---|---|---|
| `Publisher<T>` | **Source/producer** that generates a stream of `T` items; accepts subscribers. | `subscribe(Subscriber<? super T> s)` | Commits to emitting signals according to the contract; each subscription has its own lifecycle and demand. |
| `Subscriber<T>` | **Receiver** that processes items, errors, and completion signals. | `onSubscribe`, `onNext`, `onError`, `onComplete` | Receives the `Subscription` first, then decides when to request data. |
| `Subscription` | **Control channel** bound to one Publisher–Subscriber relationship. | `request(long n)`, `cancel()` | Represents the right to request `n` more items or cancel; not the data itself. |
| `Processor<T,R>` | **Bidirectional intermediary**: receives `T` from upstream and emits `R` to downstream. | Extends `Subscriber<T>` and `Publisher<R>` | Complies with both the receiving contract and the emitting contract; can transform types, filter, or coordinate streams. |

Abbreviated signatures to show the type relationships (this is an **API illustration**, not a standalone file to compile):

```java
interface Publisher<T> {
    void subscribe(Subscriber<? super T> subscriber);
}

interface Subscriber<T> {
    void onSubscribe(Subscription subscription);
    void onNext(T item);
    void onError(Throwable error);
    void onComplete();
}

interface Subscription {
    void request(long n);
    void cancel();
}

interface Processor<T, R> extends Subscriber<T>, Publisher<R> {}
```

**Distinguishing responsibilities:** `Publisher` decides *what data is emitted* and obeys the requested count; `Subscriber` decides *how to receive and process it*; `Subscription` decides *when/how many more items are allowed to be transferred*; `Processor` acts as an intermediary and must therefore manage both sides.

## 3. Subscription Lifecycle and Signals

A valid stream has the following signal shape:

```text
onSubscribe(subscription)
    ├─ onNext(item)  [0 or more times, within demand limit]
    ├─ onNext(item)
    └─ onComplete()  OR  onError(throwable)
```

Example sequence when the source has three items:

```text
Subscriber ── subscribe(subscriber) ──> Publisher
Subscriber <── onSubscribe(s) ──────── Publisher
Subscriber ── s.request(2) ──────────> Subscription
Subscriber <── onNext(1) ──────────── Publisher
Subscriber <── onNext(2) ──────────── Publisher
Subscriber ── s.request(1) ──────────> Subscription
Subscriber <── onNext(3) ──────────── Publisher
Subscriber <── onComplete() ───────── Publisher
```

The arrows describe **logical relationships**; they do not assert that each signal runs on a separate thread or happens asynchronously. For example, Reactor's `Flux.range(...)` can emit synchronously right inside the `request` call.

Important invariants:

1. `onSubscribe` provides exactly one `Subscription` per subscription and must arrive before `onNext`, `onError`, and `onComplete`.
2. `onNext` delivers one **non-null** item at a time; the number of `onNext` calls without a terminal signal must not exceed the total active demand.
3. `onComplete` signals normal source completion; `onError` signals failure. **Only one kind of terminal signal** is sent for a subscription, and no `onNext` may follow it.
4. Signals to the **same Subscriber** must be serialized according to the contract; do not arbitrarily call `onNext` concurrently from multiple threads.
5. `onComplete`/`onError` are terminal signals and **do not consume demand** like `onNext`; `onError` may arrive even before any items are requested.
6. After `cancel()`, the source must stop sending as soon as possible; due to asynchrony, some signals already in flight may still arrive. Cancelling is **not equivalent** to emitting `onComplete`.

A `Publisher` may be a **cold** source (each subscriber triggers its own stream) or a **hot** source (sharing an active source); the `Publisher` interface itself does not guarantee cold/hot behavior, lazy evaluation, which thread runs, or replay capability.

## 4. Subscription and the Backpressure Mechanism

- Inside `onSubscribe(s)`, the Subscriber typically stores `s` and calls `s.request(n)` with **`n > 0`**. `request(0)` and `request(n < 0)` are invalid requests that, per the specification, lead to an `onError` signal.
- Demand is **cumulative**: `request(2)` followed by `request(3)` grants a total of five `onNext` permissions (minus those already received); each `onNext` decrements remaining demand by one.
- `request(Long.MAX_VALUE)` is commonly used as an **unbounded** request. The specification requires demand addition to handle overflow safely, effectively saturating at the unbounded level.
- `cancel()` is used when results are no longer needed, for example when a user disconnects or business logic stops processing. Calling cancel multiple times must be safe.
- Backpressure controls **items delivered to the Subscriber**. A chain containing `filter`, `buffer`, `flatMap`, prefetch, or a hot source may manage, batch, or request an upstream item count different from downstream demand. Therefore, do not assume `request(1)` always equals exactly one I/O read or exactly one item generated at every layer.

For example, suppose a source has 100 items and the Subscriber only calls `request(2)`: without additional requests, a spec-compliant source must not send a third item via `onNext` to that Subscriber. Upstream data may be held back, bounded-buffered, or handled by the operator's/source's own strategy; this must not be assumed to mean an infinite buffer exists automatically.

## 5. Runnable Java 17+ Example with Project Reactor

The following example uses **the `org.reactivestreams` interfaces directly**. `Flux` is the concrete Publisher; a `Subscriber` manages its `Subscription` itself, receiving one item before requesting the next. No Spring Boot startup is needed.

Create the structure:

```text
reactive-roles/
├── pom.xml
└── src/main/java/demo/Main.java
```

Contents of `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>reactive-roles</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Contents of `src/main/java/demo/Main.java`:

```java
package demo;

import org.reactivestreams.Publisher;
import org.reactivestreams.Subscriber;
import org.reactivestreams.Subscription;
import reactor.core.publisher.Flux;

public class Main {
    public static void main(String[] args) {
        Publisher<Integer> publisher =
                Flux.range(1, 3).map(n -> n * 10);

        publisher.subscribe(new Subscriber<Integer>() {
            private Subscription subscription;

            @Override
            public void onSubscribe(Subscription s) {
                this.subscription = s;
                System.out.println("onSubscribe -> request(1)");
                s.request(1);
            }

            @Override
            public void onNext(Integer item) {
                System.out.println("onNext: " + item);
                subscription.request(1);
            }

            @Override
            public void onError(Throwable error) {
                System.out.println("onError: " + error.getMessage());
            }

            @Override
            public void onComplete() {
                System.out.println("onComplete");
            }
        });
    }
}
```

From the directory containing `pom.xml`, run with **JDK 17+** and Maven:

```bash
mvn -q compile exec:java
```

Program stdout output:

```text
onSubscribe -> request(1)
onNext: 10
onNext: 20
onNext: 30
onComplete
```

Role-by-role explanation:

1. `Flux.range(1, 3).map(n -> n * 10)` is a **Publisher<Integer>** pipeline that emits `10`, `20`, `30` in sequence when requested; `map` transforms each item.
2. `publisher.subscribe(...)` connects the Subscriber to the Publisher. Before emitting data, the source calls `onSubscribe(s)`.
3. The Subscriber holds `s` and calls `request(1)`: only **one** `onNext` is allowed to be transferred at that point. After each item, `onNext` calls `request(1)` to continue.
4. Once all three items have been emitted, the Publisher calls `onComplete`; `onError` is not called. In this example the source is synchronous and finite, so the stdout order is deterministic.

**Trying cancellation:** inside `onNext`, after printing `item`, replace `subscription.request(1)` with:

```java
if (item == 20) {
    subscription.cancel();
    System.out.println("cancel");
} else {
    subscription.request(1);
}
```

With this synchronous source, stdout will stop after `onNext: 20` and the `cancel` line, with no `onNext: 30` or `onComplete`. This is a change **inside the `onNext` method of the example**, not a second standalone program. With an asynchronous source, `cancel()` may not retract every signal already dispatched earlier.

## 6. Processor: When Is It Needed and When Is It Not?

`Processor<T, R>` is simultaneously a **Subscriber<T>** receiving input from upstream and a **Publisher<R>** providing an output stream to downstream:

```text
Publisher<Order>
    ──(upstream Subscription / Order)──>
Processor<Order, Receipt>
    ──(downstream Subscription / Receipt)──>
Subscriber<Receipt>
```

A Processor must behave properly on **both sides**: receiving `onSubscribe` from upstream; deciding upstream `request` calls; managing downstream demand; transforming data; forwarding completion/errors and handling cancellation appropriately. The demand relationship does not have to be 1:1 (for example, when filtering out some inputs). Writing a Processor by hand that obeys every rule for concurrency, backpressure, and cancellation is difficult.

**Not every Reactor operator is a `Processor` object.** In applications, transformations are normally expressed using operators:

```java
Flux<Integer> result = Flux.range(1, 5)
        .filter(n -> n % 2 == 1)
        .map(n -> n * 10); // logic: 10, 30, 50
```

The snippet above creates a Publisher pipeline and does not emit to any Subscriber until subscribed to. The operators handle demand coordination and transformation inside Reactor's implementation; there is no reason to create a `Processor<Integer,Integer>` manually just to perform filtering or mapping.

When you need to push external events programmatically into a Reactor stream, look into **`Sinks.Many<T>`** and an appropriate emission/buffering strategy instead of defaulting to building a manual Processor. `Sinks.Many` is Reactor's event-source API, **not** the `org.reactivestreams.Processor` interface itself. Do not assume every `tryEmitNext` call succeeds by default: check the `EmitResult` and understand the subscriber/demand rules of the chosen sink.

## 7. Practical Connection with Spring WebFlux

In Spring WebFlux, a controller method can **return `Flux`/`Mono`**. The framework and HTTP infrastructure participate in subscribing, consuming, regulating flow, and cancelling according to the request/response lifecycle.

Example **illustrative snippet inside an existing Spring WebFlux application** (not a standalone runnable file):

```java
@RestController
class NumberController {
    @GetMapping(value = "/numbers",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<Integer> numbers() {
        return Flux.range(1, 3);
    }
}
```

You need to import `org.springframework.web.bind.annotation.GetMapping`, `RestController`, `org.springframework.http.MediaType`, and `reactor.core.publisher.Flux`. When a client accesses `/numbers`, the server can emit the numbers as Server-Sent Events. Do not call `.subscribe()` inside the controller just to "start" the chain and return `void`: returning the Publisher to the framework preserves connection to error handling, cancellation on client disconnect, and runtime backpressure mechanisms. Actual flow control also depends on the network, codecs, buffering, and source type; you cannot assert that one `request(1)` at the HTTP layer corresponds to exactly one database read.

## 8. Common Misconceptions

| Misconception | Correct Understanding |
|---|---|
| "A Publisher always pushes data as soon as it is created." | Emission depends on the source type and demand; cold sources usually start only when subscribed to. |
| "`subscribe()` means running in parallel / spawning a thread." | Reactive Streams does not mandate threading; schedulers and sources/operators determine the execution context. |
| "A Subscriber only needs `onNext`." | It must receive `onSubscribe`, manage the `Subscription` lifecycle, and handle errors and completion. |
| "`request(1)` always yields an item immediately." | A request is a **maximum receiving allowance**; the source may be slow, have no items yet, or terminate without emitting anything. |
| "`onNext(null)` can be called." | Null items violate the contract; use an appropriate type representing absence, such as `Mono.empty()`. |
| "`cancel()` will emit `onComplete()`." | Cancellation ends interest/consumption; it is not a normal terminal signal. |
| "Every `map`/`filter` operation needs a Processor." | Use `Flux`/`Mono` operators; only consider a Processor when you genuinely need a combined Publisher + Subscriber intermediary. |
| "Backpressure guarantees there is no buffering or blocking." | It only defines the demand protocol; upstream handling, buffering, and I/O strategies are implementation responsibilities. |

## 9. Quick Self-Check

**Scenario:** A Publisher has five items ready; the Subscriber calls `request(2)`, receives two `onNext` signals, and then makes no further `request` calls. Question: may the third item be sent via `onNext`? What happens if the Subscriber later calls `request(3)`? And who provides the `cancel()` method?

**Answer:** The third item must not be sent once demand is exhausted. `request(3)` adds permission to receive up to three more `onNext` signals, so the source can send all three remaining items and then `onComplete()`. `cancel()` belongs to the `Subscription` that the Publisher gives the Subscriber via `onSubscribe`.

**Key takeaway:** `Publisher` **emits**, `Subscriber` **receives**, `Subscription` **controls demand/cancellation**, and `Processor` **receives and re-emits** under both contracts. Keeping these boundaries clear helps you read `Flux`/`Mono` pipelines accurately and reason about backpressure in Spring WebFlux.
