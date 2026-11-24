# Sinks.One and Sinks.Many in Project Reactor

> **Module:** Spring Framework – reactive · **Parent topic:** Hot and cold sources. This lesson teaches how to use **Project Reactor Sinks** to actively emit signals from imperative code, callbacks, or multiple data-producing components. Topics include `Sinks.One`, `Sinks.Empty`, `Sinks.Many`, unicast/multicast/replay variants, backpressure, handling concurrent producers, testing, and Spring WebFlux integration.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain that **a Sink is an active signal-emission point** and why it typically represents a hot source.
2. Choose `Sinks.One` for a single result, `Sinks.Empty` for a data-less terminal signal, and `Sinks.Many` for multi-element streams.
3. Distinguish `unicast`, `multicast`, `replay`, `directAllOrNothing`, and `directBestEffort` by subscriber count, history retention, and backpressure.
4. Use `tryEmit...`/`emit...` properly, read `Sinks.EmitResult`, and handle `FAIL_NON_SERIALIZED`, `FAIL_OVERFLOW`, and `FAIL_TERMINATED`.
5. Understand why default thread-safe Sinks can still reject two producers emitting concurrently; know when to serialize producers or use `EmitFailureHandler`.
6. Design buffer bounds, sink lifecycle, terminal signals, and behavior when there are no subscribers or late subscribers.
7. Write a runnable Java 17+ program, test with `StepVerifier`, and wire an event hub into a Spring WebFlux SSE endpoint.

**Core idea:** `Mono` and `Flux` describe a processing sequence; `Sinks` provide a port to **push signals into** that sequence from the outside. You control when values, errors, or completion are emitted. Consequently, you must decide explicitly who receives them, whether data is retained, what happens when consumers are slow, and how multiple producers are handled.

## 2. What Is a Sink? When Should You Use It?

`Sinks` resides in `reactor.core.publisher`. A Sink is a construct allowing code to **actively emit** Reactive Streams signals:
- `tryEmitNext(value)` / `emitNext(...)`: emits a value.
- `tryEmitValue(value)` / `emitValue(...)`: emits a value and completes, for `Sinks.One`.
- `tryEmitEmpty()` / `emitEmpty(...)`: completes with no value.
- `tryEmitError(error)` / `emitError(...)`: terminates with an error.
- `tryEmitComplete()` / `emitComplete(...)`: completes a `Sinks.Many`.

A Sink is commonly used to bridge an imperative data source into the reactive world: SDK callbacks, event listeners, notifications from another thread, job completion, or an in-application event hub. A Sink can be exposed downstream via **`asMono()`** or **`asFlux()`**.

~~~text
Producer / callback / listener / thread
                |
                | tryEmitNext / tryEmitValue / tryEmitError
                v
             Sinks
                |
                | asFlux() or asMono()
                v
       Reactor operators (map/filter/flatMap)
                |
                v
         WebFlux / Subscriber
~~~

**Sinks are hot sources:** producers can emit when there are no subscribers, depending on the sink type and buffer/replay policy. Late subscribers receive only what that sink type retains or replayed terminal signals. This is a major difference from a cold Publisher like `Flux.defer(...)`, which typically executes a new source per subscription.

### 2.1. Do Not Use a Sink Just to Make Every Flux Hot

If data is already a `Publisher`, usually compose it directly with `map`, `flatMap`, `merge`, `share`, `cache`, `publish`, or `defer`. If you only need to create a Flux from a callback tied individually to each subscription, `Flux.create`/`Mono.create` may fit better because callback lifecycles are tied to the subscriber. Use `Sinks` when you genuinely need an **independent emission point** called by multiple components.

A Sink often outlives a single subscription. Therefore, consider:
- who owns and completes the sink;
- which subscribers are allowed to subscribe;
- whether data before the first subscriber is retained;
- whether new subscribers receive history;
- if nobody is listening, whether the producer continues, buffers, or fails;
- how the sink terminates when the application shuts down.

### 2.2. Sinks Replace Legacy Processors

Legacy `Processor` types such as `MonoProcessor`, `UnicastProcessor`, `EmitterProcessor`, and `ReplayProcessor` have been deprecated in modern Reactor; the modern approach is `Sinks.One`, `Sinks.Empty`, and `Sinks.many()` variants. Sinks have a clearer emission API and detect unserialized concurrent access. Do not start new projects with legacy Processors.

## 3. Sinks.One: One Result, One Completion

`Sinks.one()` creates a **`Sinks.One<T>`**, with Mono semantics: at most one value followed by completion, or empty completion, or error. It acts like a reactive promise/future that a producer can complete later. The terminal outcome is retained so late subscribers still receive the same result.

~~~java
Sinks.One<String> sink = Sinks.one();
Mono<String> result = sink.asMono();

// Producer decides to complete later:
Sinks.EmitResult emitted = sink.tryEmitValue("ready");
~~~

`asMono()` returns a Mono view for consumers to subscribe to. `tryEmitValue("ready")` emits `onNext("ready")` then `onComplete`; it is **not** a multi-value stream. If the sink has already terminated before a subscriber subscribes, late subscribers still see the outcome.

### 3.1. Three Ways to Complete

~~~java
Sinks.One<String> valueSink = Sinks.one();
valueSink.tryEmitValue("found");       // onNext("found"), onComplete

Sinks.One<String> emptySink = Sinks.one();
emptySink.tryEmitEmpty();              // onComplete, no onNext

Sinks.One<String> errorSink = Sinks.one();
errorSink.tryEmitError(new IllegalStateException("failed")); // onError
~~~

These fragments use the same `Sinks.One<String>` type yet are **three independent sinks**. Each sink can terminate only once; after termination, subsequent emissions typically return `FAIL_TERMINATED`. Do not use `null` as data: Reactive Streams forbids `onNext(null)`. The Javadoc of `Sinks.One.tryEmitValue(null)` specifies that `null` only produces an empty completion; in business code, use `tryEmitEmpty()` for clear intent.

### 3.2. When to Use One?

- An HTTP/SDK callback returning a single result.
- A job finishing and exposing its outcome to multiple consumers.
- A component announcing that initialization has completed.
- A shared promise between an imperative producer and reactive consumers.

**Note:** `Sinks.One` is a shared source, not something that spawns new work per subscriber. If one subscriber cancels before the producer emits, that does not mean the sink cancels itself or the producer stops; the sink can still be completed for other or late subscribers. Define who owns the sink and when it times out/disposes according to the job's lifecycle.

## 4. Sinks.Empty: Terminal Signal Only

`Sinks.empty()` creates a `Sinks.Empty<T>`, exposed as a `Mono<T>` that emits no data. It emits only **onComplete** or **onError**. This represents an operation that needs to signal “finished” without a value.

~~~java
Sinks.Empty<Void> completed = Sinks.empty();
Mono<Void> done = completed.asMono();

// When the external operation completes:
Sinks.EmitResult result = completed.tryEmitEmpty();
~~~

Use `Sinks.Empty<Void>` for “completed” callbacks, or another generic type if the API's Mono view signature requires it. `tryEmitError(...)` terminates with an error. Late subscribers still receive the terminal signal per sink semantics.

**Distinction:** `Sinks.Empty<T>` is not an empty `Sinks.Many<T>`; it emits no `onNext` at all and has only one terminal event. `Sinks.One<T>` extends these semantics with the ability to emit one value as well.

## 5. Sinks.Many: Multiple Elements and Multiple Subscribers

`Sinks.many()` is the builder for `Sinks.Many<T>`. This sink can emit multiple `onNext` signals before completing or erroring; the consumer view is `Flux<T>` via `asFlux()`.

~~~java
Sinks.Many<String> events =
    Sinks.many().multicast().onBackpressureBuffer();

Flux<String> stream = events.asFlux();

events.tryEmitNext("created");
events.tryEmitNext("updated");
events.tryEmitComplete();
~~~

`Sinks.Many` has three major families: **unicast**, **multicast**, and **replay**. Choose a family by subscriber count and history policy, not by which name sounds “faster”.

| Variant | Subscribers | Data Before First Subscriber | Late Subscribers |
| --- | --- | --- | --- |
| `many().unicast().onBackpressureBuffer()` | One subscriber only | Buffers and delivers when the first subscriber subscribes | Second subscriber is rejected |
| `many().multicast().onBackpressureBuffer()` | Multiple subscribers | Has bounded warm-up buffer | Receive only new events from subscription time onward; no old history replay |
| `many().multicast().directAllOrNothing()` | Multiple subscribers | No buffer | No replay; one slow subscriber causes the event to be rejected for everyone |
| `many().multicast().directBestEffort()` | Multiple subscribers | No buffer | No replay; slow subscribers can individually miss events |
| `many().replay().all()` | Multiple subscribers | Retains all data | New subscribers receive all retained history |
| `many().replay().limit(n)` | Multiple subscribers | Retains at most the n most recent elements | New subscribers receive up to n elements of history |

All `Many` variants accept `tryEmitNext`, `tryEmitError`, and `tryEmitComplete`, but **what happens when there are no subscribers, slow subscribers, or full buffers depends on the sink type**.

## 6. Unicast: One Producer Channel for One Subscriber

`Sinks.many().unicast().onBackpressureBuffer()` allows **a single subscriber**. A useful feature is that the producer can emit before the subscriber subscribes; values are buffered and forwarded when the first subscriber arrives. The sink honors that subscriber's demand.

~~~java
Sinks.Many<Integer> queue = Sinks.many()
    .unicast()
    .onBackpressureBuffer();

queue.tryEmitNext(1);
queue.tryEmitNext(2);
queue.tryEmitNext(3);

// First subscriber arrives later:
Flux<Integer> values = queue.asFlux();
~~~

By default, unicast's internal buffer can be **unbounded**. If the producer outpaces the subscriber or no subscriber arrives for a long time, the heap can grow unchecked. You can pass a bounded queue:

~~~java
Queue<Integer> boundedQueue = new ArrayBlockingQueue<>(128);

Sinks.Many<Integer> queue = Sinks.many()
    .unicast()
    .onBackpressureBuffer(boundedQueue);
~~~

This fragment requires importing `java.util.Queue` and `java.util.concurrent.ArrayBlockingQueue`. The provided queue must at minimum satisfy **Single Producer / Single Consumer (SPSC)** semantics per the API contract. When the queue is full, emissions can fail with `FAIL_OVERFLOW`; the producer must have a handling policy rather than ignoring the result.

**Choose Unicast when:** one consumer owns the channel, such as a worker receiving tasks from a callback producer/bridge. Do not use unicast if you need to broadcast to multiple HTTP clients; a second subscriber is unsupported.

## 7. Multicast: One Source Emitting to Multiple Subscribers

### 7.1. onBackpressureBuffer

`Sinks.many().multicast().onBackpressureBuffer()` lets multiple subscribers receive new events. Subscribers only receive data emitted **after they subscribe**, except for certain warm-up values retained before the first subscriber. The sink coordinates backpressure across subscribers; if one subscriber is too slow, the buffer can fill and emissions can fail.

~~~java
Sinks.Many<String> broadcast = Sinks.many()
    .multicast()
    .onBackpressureBuffer(256, false);
~~~

In this overload:
- `256` is the configured maximum buffer size.
- `false` is the `autoCancel` option: do not automatically close the sink just because the last subscriber cancels. Choose according to real lifecycle; an application-level event hub may need to stay alive while temporarily having no clients.
- With multiple subscribers, the slowest demand can affect shared emission. If demand divergence exceeds the buffer, `tryEmitNext` can return `FAIL_OVERFLOW`; `emitNext` with default handling can terminate the sink with an overflow error.

`onBackpressureBuffer()` is not history replay. A subscriber subscribing after other subscribers have already received earlier events **does not receive history**. If history is needed, pick replay; if buffering is unwanted, pick a direct variant.

### 7.2. directAllOrNothing

~~~java
Sinks.Many<Event> sink =
    Sinks.many().multicast().directAllOrNothing();
~~~

There is no buffer. If **any subscriber** lacks demand at emission time, the sink reports `FAIL_OVERFLOW` and drops the event for **all** subscribers; subscribers are not terminated solely because of that emission. Fits when all subscribers must see the exact same set of events or all drop an event; unsuitable if data must not be lost.

### 7.3. directBestEffort

~~~java
Sinks.Many<Event> sink =
    Sinks.many().multicast().directBestEffort();
~~~

Also has no buffer. The sink delivers the event to subscribers that currently have demand; slow subscribers can individually miss that event. If **no subscriber** has demand, emission fails. This suits heartbeats, UI state, or transient notifications where a slow client may skip an update.

**Do not confuse `directBestEffort` with replay or reliable delivery.** It retains no history and does not guarantee reconnecting clients receive missed events. For financial, order, or lossless business notifications, use a message broker/persistence and proper event IDs/acks.

## 8. Replay: Retaining History for Late Subscribers

`Sinks.many().replay()` retains emitted elements and sends appropriate history to new subscribers.

~~~java
Sinks.Many<String> history = Sinks.many()
    .replay()
    .limit(100);

history.tryEmitNext("event-1");
history.tryEmitNext("event-2");
history.tryEmitNext("event-3");

Flux<String> lateSubscriber = history.asFlux();
~~~

Common options:

| Factory | Retained History | When to Use |
| --- | --- | --- |
| `replay().all()` | All elements | Small history, explicit lifecycle and count bounds |
| `replay().limit(n)` | At most the n newest elements | Count-bounded history window |
| `replay().latest()` | Only the latest value | Current snapshot/state |
| `replay().latestOrDefault(value)` | Latest value or default | Subscribers need a snapshot even before any event occurs |
| `replay().limit(Duration)` | Elements still within the age window | Time-bounded history |
| `replay().limit(n, Duration)` | Combines both count and age limits | More controlled history window |

**Be careful with `all()` and `limit(Duration)`**: they can retain a lot of data over a long or unbounded period if the source emits continuously. Use `limit(n)` or `limit(n, Duration)` when you need to bound RAM by both count and time. With time-based variants, the API checks age on signals; do not treat it as a background sweeper pruning continuously down to the exact millisecond.

Replay also replays terminal signals to late subscribers: if the sink has completed/errored, new subscribers receive the retained history followed by the corresponding terminal signal. A replay sink is a cache in **process memory**, not a durable event log; restarting the application loses the history.

## 9. Emit API: How Do tryEmit and emit Differ?

### 9.1. `tryEmit...`: Deciding Error Handling Yourself

`tryEmitNext`, `tryEmitValue`, `tryEmitEmpty`, `tryEmitError`, and `tryEmitComplete` return `Sinks.EmitResult`. This is usually the best choice when the application wants to **handle each case explicitly**.

~~~java
Sinks.Many<String> sink = Sinks.many().replay().limit(10);

Sinks.EmitResult result = sink.tryEmitNext("hello");

if (result == Sinks.EmitResult.OK) {
    // Sink accepted the emission.
} else {
    // Must decide explicitly how to handle result.
}
~~~

`OK` means the emission succeeded given the sink's state at call time; **it is not proof that every subscriber has finished processing the value**. Emitting and subscriber consumption are two asynchronous steps. Also do not use `currentSubscriberCount()` as a hard pre-emit check: it is only a best-effort snapshot, and subscribers can change immediately afterward.

### 9.2. Common EmitResult Values

| Result | Meaning | Action to Consider |
| --- | --- | --- |
| `OK` | Emission succeeded | Record success metrics if needed; does not mean downstream finished processing |
| `FAIL_NON_SERIALIZED` | Overlapping, unserialized emit access occurred | Serialize producers, route events through a single-consumer queue, or bounded retry |
| `FAIL_OVERFLOW` | Buffer has no remaining capacity/suitable demand | Backpressure, drop, retry once capacity frees up, or report error |
| `FAIL_ZERO_SUBSCRIBER` | No subscribers and sink has no buffer space | Accept drop, persist event, or wait for subscribers depending on domain |
| `FAIL_CANCELLED` | Sink was cancelled/disconnected by consumers | Stop producer or end lifecycle per policy |
| `FAIL_TERMINATED` | Sink already completed or errored previously | Do not emit further; review lifecycle or create a new sink |

Some results depend on the sink type. For example, `unicast` can buffer before subscribers; `multicast().directBestEffort()` does not buffer; `replay()` retains history. Do not write one generic handler assuming every sink can return every result kind.

### 9.3. `emit...`: Providing a FailureHandler

`emitNext(value, handler)` is a convenience method calling `tryEmitNext` and letting `EmitFailureHandler` decide whether to retry. `Sinks.EmitFailureHandler.FAIL_FAST` does not retry. `busyLooping(Duration)` retries for a finite time upon `FAIL_NON_SERIALIZED` contention.

~~~java
sink.emitNext(
    value,
    Sinks.EmitFailureHandler.busyLooping(Duration.ofMillis(200))
);
~~~

**Mandatory notes for `busyLooping`:**
- This handler can **busy-loop on the producer thread** until the deadline; it is not a non-blocking queue.
- Create a **new handler per emit call**; do not cache/reuse instances.
- Reactor documentation recommends a timeout larger than roughly 100ms; values that are too small are usually unhelpful.
- Use only when contention is brief and the caller can afford retry cost; do not place it on Netty event-loop or latency-sensitive threads.
- Do not treat `FAIL_OVERFLOW` or `FAIL_TERMINATED` as if they were `FAIL_NON_SERIALIZED`; they have different causes and blind retrying usually will not solve them.

For systems with continuous multiple producers, a better approach is usually **serializing inputs** via a queue/actor or a single sequential emitting consumer, rather than having multiple threads contend and spin on emit.

## 10. Thread Safety: Safe Does Not Mean Every Concurrent Emit Succeeds

Reactor's default Sinks are **thread-safe in the sense of detecting concurrent access and avoiding Reactive Streams violations**. If two threads try to emit simultaneously, one may fail with `FAIL_NON_SERIALIZED`; the sink does not silently turn all producers into an unbounded queue. This improves on legacy Processors where callers had to synchronize manually to avoid undefined behavior.

Concurrent producer example:

~~~java
Sinks.Many<Integer> sink = Sinks.many().replay().all();

// Thread A:
Sinks.EmitResult a = sink.tryEmitNext(1);

// Thread B, if colliding right while A is emitting:
Sinks.EmitResult b = sink.tryEmitNext(2);
~~~

Do not expect `b` to always be `FAIL_NON_SERIALIZED`, because the two operations might not actually overlap; results depend on timing. If `b` receives this result, decide to retry/serialize rather than ignoring it.

### 10.1. How to Manage Multiple Producers

- **Single producer:** call `tryEmit...` and handle the result.
- **Multiple producers needing ordering:** pass messages through a single-threaded queue or dispatcher, then have only one consumer emit into the sink.
- **Multiple producers, brief contention:** you may use `emit...` with a bounded handler, understanding the blocking/busy-loop cost.
- **Multiple producers and high throughput:** design per-key partitioning/actors/single-writers or use an appropriate broker; do not turn `Sinks` into an unbounded message delivery system.

### 10.2. Why You Should Not Use `Sinks.unsafe()`

`Sinks.unsafe()` creates variants that do not detect/synchronize concurrent access. It has lower overhead, yet **the caller must guarantee external synchronization** to obey Reactive Streams. Use it only inside internal operators/frameworks where serialized calling is proven. Regular Spring applications should use default safe sinks; do not pick unsafe merely because of a microbenchmark on a single emit.

## 11. Terminal Signals and Sink Lifecycle

A Sink can terminate only once:
- `tryEmitComplete()` or `tryEmitEmpty()` terminates successfully.
- `tryEmitError(error)` terminates with an error.
- With `Sinks.One`, `tryEmitValue(value)` both emits the value and completes.
- After termination, subsequent data emissions typically return `FAIL_TERMINATED`; new values/errors are not appended to the same stream.

**Who calls complete/error?** The component owning the sink's lifecycle should decide when the stream stops: service shutdown, job completion, listener unregistration, or external source failure. Without a clear owner, a sink can live forever, retaining subscribers, queues, or history on the heap.

For application-level sinks:
1. Create the sink in a component with a clear lifecycle (e.g., a singleton service).
2. Expose `asFlux()`/`asMono()` instead of letting every caller mutate internals.
3. Expose only `publish`, `complete`, and `fail` methods per business contract.
4. On shutdown, stop accepting new producers, emit the terminal signal, and clean up listeners/timers.
5. Monitor subscriber count, buffer/overflow, emit failures, and sink age.
6. If restarts or cross-instance replay are needed, use persistence/a message broker instead of in-memory state.

**Do not share one singleton Sink across all requests if each request needs an independent source.** That mixes subscribers, data, and lifecycles of multiple users into a single channel.

## 12. Runnable Java 17+ Program

The following example demonstrates `Sinks.One`, `Sinks.Empty`, unicast, multicast, and replay. It uses Reactor Core 3.8.8 and Maven. The CLI program calls `block()` **only at the final boundary to collect results and print stdout**; do not copy this pattern into WebFlux controllers.

### 12.1. Directory Structure

~~~text
reactor-sinks-demo/
├── pom.xml
├── src/main/java/com/example/sinks/SinksDemo.java
└── src/test/java/com/example/sinks/SinksDemoTest.java
~~~

### 12.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>reactor-sinks-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <version>3.8.8</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
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

### 12.3. Program `SinksDemo.java`

**src/main/java/com/example/sinks/SinksDemo.java**

~~~java
package com.example.sinks;

import java.util.ArrayList;
import java.util.List;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;

public final class SinksDemo {
    private SinksDemo() {}

    private static void requireOk(Sinks.EmitResult result) {
        if (result != Sinks.EmitResult.OK) {
            throw new IllegalStateException("Emit failed: " + result);
        }
    }

    public static void main(String[] args) {
        // One: single result replayed to late subscribers.
        Sinks.One<String> one = Sinks.one();
        Mono<String> oneView = one.asMono();
        requireOk(one.tryEmitValue("ready"));
        System.out.println("one=" + oneView.block());
        System.out.println("oneLate=" + oneView.block());

        // Empty: completes only, no onNext.
        Sinks.Empty<Void> empty = Sinks.empty();
        Mono<Void> completion = empty.asMono();
        requireOk(empty.tryEmitEmpty());
        completion.block();
        System.out.println("empty=complete");

        // Unicast: retains elements before the first subscriber.
        Sinks.Many<Integer> unicast = Sinks.many()
            .unicast()
            .onBackpressureBuffer();
        requireOk(unicast.tryEmitNext(1));
        requireOk(unicast.tryEmitNext(2));
        requireOk(unicast.tryEmitComplete());
        List<Integer> queued = unicast.asFlux().collectList().block();
        System.out.println("unicast=" + queued);

        // Multicast: both subscribers subscribe before emitting.
        Sinks.Many<Integer> multicast = Sinks.many()
            .multicast()
            .onBackpressureBuffer(8, false);
        List<Integer> first = new ArrayList<>();
        List<Integer> second = new ArrayList<>();
        Flux<Integer> live = multicast.asFlux();
        live.subscribe(first::add);
        live.subscribe(second::add);

        requireOk(multicast.tryEmitNext(10));
        requireOk(multicast.tryEmitNext(20));
        requireOk(multicast.tryEmitComplete());
        System.out.println("multicastA=" + first);
        System.out.println("multicastB=" + second);

        // Replay: late subscriber receives only the last two elements.
        Sinks.Many<Integer> replay = Sinks.many()
            .replay()
            .limit(2);
        requireOk(replay.tryEmitNext(1));
        requireOk(replay.tryEmitNext(2));
        requireOk(replay.tryEmitNext(3));
        requireOk(replay.tryEmitComplete());
        List<Integer> history = replay.asFlux().collectList().block();
        System.out.println("replayLate=" + history);

        System.out.println("afterComplete=" + replay.tryEmitNext(4));
    }
}
~~~

### 12.4. Running and Stdout

In the directory containing `pom.xml`, JDK 17+ and Maven are required:

~~~bash
java -version
mvn -version
mvn test
mvn -q exec:java -Dexec.mainClass=com.example.sinks.SinksDemo
~~~

**Stdout from `System.out.println` statements in main** (excluding Maven logs):

~~~text
one=ready
oneLate=ready
empty=complete
unicast=[1, 2]
multicastA=[10, 20]
multicastB=[10, 20]
replayLate=[2, 3]
afterComplete=FAIL_TERMINATED
~~~

Result explanation:
- `Sinks.One` stores the result and late subscribers still receive `"ready"`.
- `Sinks.Empty` completes without emitting elements.
- Unicast buffers `1,2` before the first subscriber.
- Both multicast subscribers subscribed before emission, so both receive `10,20`.
- Replay limits to two elements, so the late subscriber receives `2,3`.
- After the replay sink completes, emitting `4` returns `FAIL_TERMINATED`.

This is a small example to understand semantics; in production you must decide buffer size, subscriber lifecycle, and how every `EmitResult` is handled.

## 13. Testing with StepVerifier

Do not test only lists of values; verify **late-subscriber behavior, subscriber limits, terminal signals, and EmitResult**.

**src/test/java/com/example/sinks/SinksDemoTest.java**

~~~java
package com.example.sinks;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class SinksDemoTest {

    @Test
    void oneReplaysItsSingleValueToLateSubscribers() {
        Sinks.One<String> sink = Sinks.one();
        Flux<String> notUsed = Flux.empty();

        assertEquals(Sinks.EmitResult.OK, sink.tryEmitValue("done"));

        StepVerifier.create(sink.asMono())
            .expectNext("done")
            .verifyComplete();

        StepVerifier.create(sink.asMono())
            .expectNext("done")
            .verifyComplete();

        assertEquals(Sinks.EmitResult.FAIL_TERMINATED,
            sink.tryEmitValue("late"));
    }

    @Test
    void oneCanCompleteEmpty() {
        Sinks.One<String> sink = Sinks.one();
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitEmpty());

        StepVerifier.create(sink.asMono())
            .verifyComplete();
    }

    @Test
    void unicastBuffersBeforeFirstSubscriber() {
        Sinks.Many<Integer> sink = Sinks.many()
            .unicast()
            .onBackpressureBuffer();

        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(1));
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(2));
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitComplete());

        StepVerifier.create(sink.asFlux())
            .expectNext(1, 2)
            .verifyComplete();

        StepVerifier.create(sink.asFlux())
            .expectError(IllegalStateException.class)
            .verify();
    }

    @Test
    void replayLimitKeepsOnlyRecentValuesForLateSubscriber() {
        Sinks.Many<Integer> sink = Sinks.many().replay().limit(2);
        sink.tryEmitNext(1);
        sink.tryEmitNext(2);
        sink.tryEmitNext(3);
        sink.tryEmitComplete();

        StepVerifier.create(sink.asFlux())
            .expectNext(2, 3)
            .verifyComplete();
    }

    @Test
    void multicastLateSubscriberReceivesOnlyNewSignals() {
        Sinks.Many<Integer> sink = Sinks.many()
            .multicast()
            .onBackpressureBuffer(8, false);

        List<Integer> early = new ArrayList<>();
        List<Integer> late = new ArrayList<>();
        Flux<Integer> view = sink.asFlux();

        view.subscribe(early::add);
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(1));

        view.subscribe(late::add);
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(2));
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitComplete());

        assertEquals(List.of(1, 2), early);
        assertEquals(List.of(2), late);
    }

    @Test
    void emissionAfterTerminationReturnsFailure() {
        Sinks.Many<Integer> sink = Sinks.many().replay().all();
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(1));
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitComplete());

        assertEquals(Sinks.EmitResult.FAIL_TERMINATED,
            sink.tryEmitNext(2));
    }
}
~~~

The tests above use `StepVerifier` to assert signals and JUnit assertions to check emit results. In real code, add tests for overflow with bounded buffers, slow subscribers, autoCancel, direct variants, and producer races if those are active paths in the system. Do not write concurrency tests requiring one fixed thread to win; race tests must verify invariants and handle all possible results.

## 14. Spring WebFlux Integration: Event Hub and SSE

An application can use `Sinks.Many` as an **in-process** event hub. The service exposes a Flux to the controller, and producers call `tryEmitNext`. The example picks `directBestEffort()` for transient updates: slow subscribers can lose individual events; there is no buffering and no replay.

### 14.1. EventHub

~~~java
package com.example.web;

import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

@Component
public class EventHub {
    public record AppEvent(long id, String type, String message) {}

    private final AtomicLong ids = new AtomicLong();
    private final Sinks.Many<AppEvent> sink =
        Sinks.many().multicast().directBestEffort();

    public Flux<AppEvent> events() {
        return sink.asFlux();
    }

    public void publish(String type, String message) {
        AppEvent event = new AppEvent(
            ids.incrementAndGet(), type, message);

        Sinks.EmitResult result = sink.tryEmitNext(event);

        switch (result) {
            case OK -> { }
            case FAIL_ZERO_SUBSCRIBER, FAIL_OVERFLOW -> {
                // For transient events, having no listeners or slow consumers
                // may be an acceptable scenario.
            }
            default -> throw new IllegalStateException(
                "Cannot publish event: " + result);
        }
    }

    public void close() {
        Sinks.EmitResult result = sink.tryEmitComplete();
        if (result != Sinks.EmitResult.OK &&
                result != Sinks.EmitResult.FAIL_TERMINATED) {
            throw new IllegalStateException(
                "Cannot close event hub: " + result);
        }
    }
}
~~~

This class integrates into Spring Boot WebFlux via component scanning. `close()` should be called by the lifecycle owner on application shutdown; if the event hub is a singleton, do not close it after each HTTP request. If there are multiple producers, serialize `publish` calls or handle `FAIL_NON_SERIALIZED` properly; the example intentionally surfaces failures rather than silently dropping them.

**`directBestEffort` policy:**
- Clients without demand can have an event skipped.
- If some subscribers have demand, they still receive the event; slow subscribers miss that event.
- If no subscriber can receive, emit returns the corresponding failure.
- The sink retains no history for reconnections.

### 14.2. SSE Controller

~~~java
package com.example.web;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
public class EventController {
    private final EventHub hub;

    public EventController(EventHub hub) {
        this.hub = hub;
    }

    @GetMapping(path = "/api/events",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<EventHub.AppEvent>> events() {
        return hub.events().map(event ->
            ServerSentEvent.<EventHub.AppEvent>builder()
                .id(Long.toString(event.id()))
                .event(event.type())
                .data(event)
                .build());
    }
}
~~~

The controller returns `Flux<ServerSentEvent<...>>`; WebFlux manages subscription and response streaming. When a client disconnects, its response subscription may be cancelled, yet that does not automatically destroy the shared event hub. Other subscribers can keep receiving data. Do not call `subscribe()` manually inside a controller.

**If events must not be lost:** switch the policy to bounded replay or use a queue/broker/persistence with acknowledgments, event IDs, and reconnect replay. `Sinks.Many.replay().limit(n)` only retains history in one process's memory; it does not replace Kafka, RabbitMQ, or transactional outbox and does not share history across multiple instances.

## 15. Choosing a Sink Type by Problem

| Need | Suggestion | What to Decide |
| --- | --- | --- |
| A callback returning one result to multiple consumers | `Sinks.one()` | Timeout, complete/error, and who owns the promise |
| Only need to signal completion or error | `Sinks.empty()` | When the terminal signal is emitted |
| One worker receiving one command stream | `many().unicast().onBackpressureBuffer(queue)` | Bounded queue, single subscriber |
| Broadcast new events to multiple clients, with buffering | `many().multicast().onBackpressureBuffer(size, autoCancel)` | Slowest subscriber, overflow, autoCancel |
| Transient broadcast, drop events for slow clients | `many().multicast().directBestEffort()` | Whether event loss is acceptable |
| All subscribers must see together or drop together | `many().multicast().directAllOrNothing()` | One slow subscriber affects the whole group |
| Late subscribers need a few recent events | `many().replay().limit(n)` | History size and retention |
| Subscribers only need the latest state | `many().replay().latest()` | Older values are discarded |
| Producer is a separate callback per subscriber | `Flux.create` / `Mono.create` | Cleanup and cancellation of each subscription |
| Multiple instances, durability and distribution needed | Message broker / database outbox | Delivery semantics, acks, partitions, replay |

**First decision question:** can events be lost? If yes, direct variants can make sense. If no, a bounded buffer or storage system is required; in-memory replay alone does not guarantee data across restarts.

## 16. Common Pitfalls and How to Handle Them

| Mistake | Consequence | Right Approach |
| --- | --- | --- |
| Using `Sinks.One` as a multi-value Flux | Second emit fails after termination | Choose `Sinks.Many` for multiple elements |
| Using `Sinks.Many.unicast` with multiple subscribers | Later subscribers are rejected | Choose multicast or replay |
| Thinking multicast replays old history | Late subscribers miss events | Use a replay sink if history is needed |
| Using unbounded replay `.all()` | Heap grows with total history | `limit(n)` or `limit(n, Duration)` |
| Ignoring `EmitResult` | Silent event loss/overflow/concurrency failures | Check every result and define an explicit policy |
| Thinking a safe sink serializes all producers automatically | Hits `FAIL_NON_SERIALIZED` on overlapping emits | Serialize producers or bounded retry |
| Busy-looping forever to emit | CPU pinned and system stalls | Single-threaded queue/dispatcher or short, reasonable deadline |
| Using `unsafe()` without locking | Violates Reactive Streams, corrupted signals | Default safe sink or provable external synchronization |
| Default unbounded unicast buffer | RAM grows when consumer is slow/absent | Bounded queue, overflow policy, and metrics |
| Using direct sinks for lossless events | Slow subscribers miss events | Durable buffer/replay or message broker |
| Calling complete multiple times/emitting after terminal | `FAIL_TERMINATED` or dropped signals | Single lifecycle owner, terminate exactly once |
| Calling `subscribe()` inside a WebFlux controller | Detaches work from HTTP lifecycle, prone to leaks | Return `Mono`/`Flux` to the framework |
| Using a singleton sink for independent per-request streams | Mixes data and subscribers across users | Scope sink per job/session or use an intentional event bus |
| Treating `OK` as meaning subscribers finished processing | Wrong metrics and delivery confirmation | Separate accepted, delivered, processed/acknowledged |
| Using Sinks instead of a distributed broker | Events lost on process restart, not shared across instances | Broker/outbox/persistence for durability and distribution |

## 17. Production Readiness Checklist

- [ ] Chose the right `One`, `Empty`, or `Many` based on value cardinality.
- [ ] For `Many`, chose unicast/multicast/replay/direct based on subscriber count and history needs.
- [ ] Decided whether data before the first subscriber is buffered or dropped.
- [ ] Buffer is bounded with an overflow policy; not relying on default unbounded queues.
- [ ] Decided whether slow subscribers affect only themselves or all subscribers.
- [ ] Every `tryEmit...` checks `EmitResult`.
- [ ] Concurrent producers are serialized or explicitly handle `FAIL_NON_SERIALIZED`.
- [ ] `busyLooping` is not used on event-loops or latency-sensitive threads; handlers are created fresh per call.
- [ ] `Sinks.unsafe()` is used only with proven external synchronization.
- [ ] The sink has a lifecycle owner and terminal signals are emitted only once.
- [ ] `OK` is understood as emit accepted, not completed business processing.
- [ ] Tests cover subscribers before/after emit, overflow, terminal, unicast rejection, and replay.
- [ ] WebFlux controllers return Flux/Mono, without manual subscribe.
- [ ] If durable delivery, cross-restart replay, or multi-instance fan-out is needed, chose a broker/persistence instead of an in-memory sink.

## 18. Practice Exercises

**Exercise 1 – One or Many?** Write a `Sinks.One<String>` and try emitting two values. Confirm the first returns `OK` and the second returns `FAIL_TERMINATED`; switch to `Sinks.Many` and observe both elements emitted.

**Exercise 2 – Unicast buffer:** Emit three values before the first subscriber, then subscribe. Verify all three values are forwarded. Try a second subscriber and confirm it is rejected.

**Exercise 3 – Multicast:** Subscribe subscriber A, emit event 1, subscribe subscriber B, emit event 2, then complete. Result: A sees 1,2; B sees only 2. Switch to replay limit(10) and observe B receiving bounded history.

**Exercise 4 – Direct backpressure:** Use `StepVerifier.create(sink.asFlux(), 0)` to create a subscriber that has not requested yet. Compare `directAllOrNothing` vs. `directBestEffort` when another subscriber is requesting; record `EmitResult` and elements received by each subscriber.

**Exercise 5 – Overflow:** Create a very small multicast buffer and a slow subscriber. Emit beyond capacity, check `FAIL_OVERFLOW`; decide whether to retry, drop, write to a broker, or error the producer.

**Exercise 6 – Concurrent producers:** Have two producers emit to the same sink using a latch to create controlled contention. Observe `FAIL_NON_SERIALIZED`; then route messages through a single-writer queue and compare results. Do not require a specific thread to always win.

**Exercise 7 – SSE:** Create EventHub with directBestEffort, open two SSE clients, emit an event, and observe both. Close one client and emit again; verify the remaining client continues receiving. Explain why events emitted before a new client connects are not replayed.

## 19. Official References

1. Reactor Core 3.8.8 – `Sinks`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.html
2. Reactor Core – `Sinks.One`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.One.html
3. Reactor Core – `Sinks.Many`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.Many.html
4. Reactor Core – `Sinks.EmitResult`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.EmitResult.html
5. Reactor Core – `Sinks.EmitFailureHandler`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.EmitFailureHandler.html
6. Reactor Core – `Sinks.UnicastSpec`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.UnicastSpec.html
7. Reactor Core – `Sinks.MulticastSpec` and `MulticastReplaySpec`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.MulticastSpec.html
8. Project Reactor Reference Guide – Sinks and backpressure: https://projectreactor.io/docs/core/release/reference/
9. Spring Framework – WebFlux streaming: https://docs.spring.io/spring-framework/reference/web/webflux.html

**Final self-check:** Why is `Sinks.One` suitable for a callback result yet unsuitable for an event stream? Why can `multicast().onBackpressureBuffer()` be affected by a slow subscriber? When should you choose `directBestEffort` instead of replay? Why must `tryEmitNext()` be checked even when a sink is thread-safe? If you can explain these points along with late-subscriber and overflow tests, you understand how to use Sinks properly in Reactor.
