# `tryEmit`, `emit`, Concurrent Emission, and Buffer Overflow in Project Reactor Sinks

## 1. Objectives and Real-World Scenarios

In Spring WebFlux, most applications should produce data using Publishers such as `Mono<T>` and `Flux<T>` and return them for the framework to handle. However, sometimes data comes from an **imperative** API: a legacy library listener, an SDK callback, events from a socket connection, or a thread outside Reactor. In that case, we need an integration point for external code to **push signals into** a reactive sequence.

Project Reactor provides `Sinks` for this scenario. A `Sink` can be thought of as an active entry point for emitting `onNext`, `onError`, and `onComplete`. Two key API families:

- `tryEmitNext(value)`: attempts to emit and returns a `Sinks.EmitResult` so the application decides how to handle the outcome.
- `emitNext(value, failureHandler)`: attempts to emit using a handler mechanism; the handler can tell Reactor to retry certain emission failures, or let the sink apply its default failure behavior.

This lesson focuses on three questions asked in this module:

1. **How do `tryEmit` and `emit` differ?**
2. **How are multiple concurrent producers** handled?
3. **When the buffer is full or subscribers cannot keep up**, what is the outcome and how should it be handled?

After this lesson, you will know how to read each `EmitResult` status, choose a Sink variant based on subscriber count/history needs, bound buffers, handle contention among producers, and bridge external callbacks into Spring WebFlux.

## 2. A Sink as a Bridge Between Imperative Code and Reactive Streams

A `Sinks.Many<T>` can be exposed to the reading side as a `Flux<T>` via `asFlux()`:

~~~java
Sinks.Many<String> sink = Sinks.many().multicast().onBackpressureBuffer();

Flux<String> events = sink.asFlux();

sink.tryEmitNext("created");
sink.tryEmitNext("updated");
sink.tryEmitComplete();
~~~

`events` is the stream consumers subscribe to. Producer code actively calls `tryEmitNext` to push signals into the Sink. When done, the sink emits `onComplete`; calling `tryEmitError(error)` emits `onError`.

Differences from `Flux.just(...)`:

| Regular Reactive Source | `Sinks.Many` |
| --- | --- |
| Publisher-creating operators describe how data is generated/composed | External producers actively emit individual signals |
| Sources are typically subscribed to per Publisher lifecycle | A Sink can be retained as an event entry point outliving a single subscription |
| Subscribers drive demand via Reactive Streams | A Sink must handle producers emitting when subscribers have no demand yet |
| Fits end-to-end reactive processing | Fits bridging from callbacks/threads/imperative APIs |

Do not use a Sink merely to replace `Flux.just`, `Flux.fromIterable`, or `Mono.fromCallable`. If the source already has a reactive API, keeping that Publisher directly is usually simpler and easier to manage backpressure with.

### 2.1. `Sinks.Many`, `Sinks.One`, and `Sinks.Empty`

- `Sinks.Many<T>` has semantics close to `Flux<T>`: can emit multiple elements.
- `Sinks.One<T>` has semantics close to `Mono<T>`: emits at most one value and completes, or completes empty/with error.
- `Sinks.Empty<T>` emits only terminal signals (`onComplete` or `onError`), emitting no values.

Example when a callback only finishes one task:

~~~java
Sinks.One<String> resultSink = Sinks.one();

Mono<String> result = resultSink.asMono();

resultSink.tryEmitValue("done");
~~~

For continuous event streams, `Sinks.Many` is typically used. The main examples in this lesson focus on `Many` because it clearly exposes concurrency, demand, and overflow issues.

## 3. `tryEmitNext`: Explicitly Inspecting Emit Results

### 3.1. Signature and Meaning

~~~java
Sinks.EmitResult result = sink.tryEmitNext(value);
~~~

`tryEmitNext` attempts to emit a **non-null** value as `onNext(value)`. Rather than returning a simple `boolean`, it returns the `Sinks.EmitResult` enum. Producers must therefore read the result and decide:

- Was the value accepted by the sink?
- Are there no subscribers to receive it?
- Did subscribers cancel?
- Has the sink already terminated?
- Is the buffer full?
- Is another producer emitting concurrently?

**`OK` means the sink accepted the signal at call time.** It is not a business receipt proving all subscribers finished processing the data. Subscribers may process asynchronously, lack demand, or cancel while the producer is emitting.

Simple handling pattern:

~~~java
Sinks.EmitResult result = sink.tryEmitNext(event);

if (result.isSuccess()) {
    // Sink accepted the signal.
} else {
    // Classify result and apply an appropriate policy.
}
~~~

Do not ignore the result just because the program “seems to work”. If a value is rejected and the producer continues as if it succeeded, the application can silently lose events.

### 3.2. `EmitResult` Values

| Result | Cause | Common Handling Direction |
| --- | --- | --- |
| `OK` | Sink accepted the signal | Continue; do not infer consumers finished processing |
| `FAIL_NON_SERIALIZED` | Overlapping, unserialized emit calls occurred | Serialize producers or bounded retry on contention |
| `FAIL_OVERFLOW` | No buffer capacity left or subscribers lack sufficient demand per Sink policy | Throttle, bound queue, intentional drop, or persist durably |
| `FAIL_ZERO_SUBSCRIBER` | Sink has no subscribers and cannot buffer/warm-up that signal | Subscribe consumers first, pick a buffered Sink type, or accept drop |
| `FAIL_CANCELLED` | Sink was cancelled or disconnected by subscribers/consumers | Stop producer or start a new lifecycle per business logic |
| `FAIL_TERMINATED` | Sink already received a terminal signal earlier | Do not emit further; check lifecycle or duplicate-call bug |

Not every Sink type can produce every status in all scenarios. For example, a replay Sink can store data before subscribers subscribe, while a direct multicast sink can return `FAIL_ZERO_SUBSCRIBER` immediately when nobody is listening. Understand the policy of the chosen factory.

### 3.3. Distinguishing `tryEmitNext` from Terminal Methods

Corresponding methods:

~~~java
Sinks.EmitResult next = sink.tryEmitNext(value);
Sinks.EmitResult complete = sink.tryEmitComplete();
Sinks.EmitResult error = sink.tryEmitError(new IllegalStateException("failed"));
~~~

- `tryEmitNext` is affected by backpressure and buffer capacity.
- `tryEmitComplete` is not a data element, so it does not require a `request(1)` unit of demand to emit.
- `tryEmitError` is also a terminal signal, not an `onNext` element.
- After `onComplete` or `onError`, the sink is terminated; a subsequent `tryEmitNext` typically returns `FAIL_TERMINATED`.
- Do not emit `null`. Reactive Streams and Sinks require valid elements/Throwables, not null to represent “no data”.

### 3.4. Checking Specific Statuses Instead of Treating All Failures Alike

~~~java
switch (sink.tryEmitNext(event)) {
    case OK -> recordAccepted(event);
    case FAIL_NON_SERIALIZED -> enqueueForSingleWriter(event);
    case FAIL_OVERFLOW -> applyOverflowPolicy(event);
    case FAIL_ZERO_SUBSCRIBER -> handleNoConsumer(event);
    case FAIL_CANCELLED -> stopProducing();
    case FAIL_TERMINATED -> reportLateEvent(event);
}
~~~

This is an **illustrative snippet**: `recordAccepted`, `enqueueForSingleWriter`, `applyOverflowPolicy`, `handleNoConsumer`, `stopProducing`, and `reportLateEvent` are application-defined policies. This snippet shows that you must decide based on cause, not copy it verbatim as a standalone program.

## 4. `emitNext`: Using EmitFailureHandler to Handle Failures

### 4.1. Signature

~~~java
sink.emitNext(value, Sinks.EmitFailureHandler.FAIL_FAST);
~~~

`emitNext` is a convenience API built on top of `tryEmitNext`. When an attempt does not succeed, Reactor asks `EmitFailureHandler` whether to **retry the emission**:

- Handler returns `true`: the implementation is instructed to retry `tryEmitNext`.
- Handler returns `false`: the sink applies the implementation's default failure behavior.

`Sinks.EmitFailureHandler.FAIL_FAST` is a built-in handler that does not request retries. With Reactor's safe sinks, if the failure is `FAIL_NON_SERIALIZED`, `emitNext` may throw `Sinks.EmissionException`. If the failure is overflow, default `emitNext` behavior may push the sink onto the `onError` path with an overflow error. Thus `emitNext` is **not** a way to “just call it and guarantee emission succeeds”.

### 4.2. Why `tryEmitNext` Is Often Better When Control Is Needed

`tryEmitNext` returns the cause so the producer chooses the action itself. It fits when:

- There are no subscribers and the application wants to save the event to a database.
- The buffer is full and the application wants to return an error to the caller.
- Contention occurs and the application wants to route the event into a sequential queue.
- An event is expired or the sink is terminated and logs/metrics must be recorded.

`emitNext` fits when the application wants an explicit handler policy and accepts the sink's default behavior for non-retried failures. For critical business logic, checking `EmitResult` is usually more transparent.

### 4.3. `busyLooping(Duration)` Only Solves Concurrent Emission Contention

Reactor provides:

~~~java
sink.emitNext(
    event,
    Sinks.EmitFailureHandler.busyLooping(Duration.ofSeconds(2))
);
~~~

The `busyLooping` handler can wait briefly and retry when the sink reports `FAIL_NON_SERIALIZED`, meaning producers are accessing the sink concurrently. Remember:

1. This is a **busy loop with a deadline**, not a durable queue.
2. Use a practical duration; Reactor documentation recommends over 100 ms because too short a duration is usually meaningless.
3. **Create a new handler per emit call**; do not cache and reuse a `busyLooping` handler because the deadline is measured from when the handler was created.
4. This handler does not turn `FAIL_OVERFLOW` into success; a full buffer is a capacity/backpressure problem, not brief contention.
5. Do not use unbounded busy loops on event-loops or threads serving other requests. If contention persists, serialize producers with a queue/lock or design a single writer stream.

### 4.4. Do Not Confuse the Handler with Business Retries

`EmitFailureHandler` only decides whether to retry **pushing a signal into the Sink** after a failed `EmitResult`. It does not re-call HTTP APIs, re-run transactions, or recover dropped data. If a producer retries an event itself, ensure no duplicate delivery or repeated side effects occur.

## 5. Concurrent Emission: Why Does `FAIL_NON_SERIALIZED` Happen?

### 5.1. Reactive Streams Requires Serialized Signals

For the same Subscriber, signals must obey the protocol and must not be emitted concurrently in an overlapping manner. If two threads simultaneously call:

~~~java
// Thread A
sink.tryEmitNext("A");

// Thread B, at the same time
sink.tryEmitNext("B");
~~~

then one of the emits can receive `FAIL_NON_SERIALIZED`. Reactor's default safe sinks detect concurrent access and reject unserialized operations; they **do not automatically put every producer into an unbounded queue**.

Do not interpret “thread-safe Sink” as meaning every concurrent call always succeeds. Safety here means the sink protects the signal contract and tells you when producers violate serialization; producers still must handle the result.

### 5.2. Three Handling Strategies

**Strategy A — Single writer (often easiest to control)**

Multiple threads put events into a thread-safe queue. Only one consumer reads the queue and calls `tryEmitNext`. Thus emissions to the Sink are serialized at a single point.

~~~text
Producer A ----\
Producer B -----+--> bounded queue --> single writer --> Sink.asFlux()
Producer C ----/
~~~

Pros: easy control of ordering, backpressure, and overflow. Cons: requires managing the queue, worker thread, lifecycle, and full-queue policy.

**Strategy B — Producer-side synchronization**

~~~java
private final Object emitLock = new Object();

public Sinks.EmitResult publish(Event event) {
    synchronized (emitLock) {
        return sink.tryEmitNext(event);
    }
}
~~~

This serializes emit calls on the same lock. Use only when the critical section is short, with no slow or blocking callbacks inside the lock. With multiple producer instances or multiple processes, a Java lock on one object only protects threads sharing that object, not distributed locking.

**Strategy C — Bounded contention retry**

~~~java
sink.emitNext(
    event,
    Sinks.EmitFailureHandler.busyLooping(Duration.ofSeconds(1))
);
~~~

This can fit when contention is very brief and producer count/load is controlled. If contention is frequent or prolonged, a single-writer queue is usually more predictable. Do not use unbounded retries, which tie up producer threads and can cause stalls.

### 5.3. When to Use `Sinks.unsafe()`?

`Sinks.unsafe().many()` omits some thread-safety/serialization checks compared to safe sinks. It is only for advanced use cases when **the application already guarantees all emit calls are serialized by another mechanism**. If multiple producers emit without external protection, skipping checks can break the protocol and cause invalid downstream behavior.

By default, use safe factories such as `Sinks.many()`. Do not pick unsafe just to make `FAIL_NON_SERIALIZED` disappear; fix the concurrency source first.

## 6. Buffer Overflow: Understand the Cause Before Picking a Policy

### 6.1. Buffers Exist Because Producers Can Outpace Consumers

Suppose a producer pushes 10,000 events/second while subscribers only process 1,000 events/second. The difference must be handled in one of these ways:

- Temporarily hold in a buffer.
- Reject emissions when the buffer is full.
- Drop some or all events according to a policy.
- Throttle/control the producer.
- Persist durably outside memory and read later.

A buffer only delays having to resolve a rate mismatch; it does not make consumers process faster. An unbounded buffer can turn overload into heap growth, GC pressure, or `OutOfMemoryError`.

### 6.2. What Does `FAIL_OVERFLOW` Mean?

`FAIL_OVERFLOW` indicates the Sink lacks capacity to accept a new element under the current backpressure/buffering policy. It can occur when:

- A unicast sink with a bounded queue is full.
- A multicast sink buffering for slow subscribers hits its limit.
- A direct sink has no subscribers with demand to receive the element under direct policy.
- Demand divergence across subscribers exceeds the configured buffer.

This is not a signal to continuously busy-loop. If subscribers are not consuming, retrying immediately only adds load and will likely fail again. The application must decide to drop, retry once consumers have capacity, throttle, or persist durably.

### 6.3. Differences Between `tryEmitNext` and `emitNext` on Overflow

- `tryEmitNext` returns `FAIL_OVERFLOW` for the producer to handle. The Sink does not necessarily terminate itself merely because this attempt was rejected.
- With Reactor's default behavior, `emitNext` encountering `FAIL_OVERFLOW` can transition the Sink to a terminal error with an overflow exception. Active subscribers will receive `onError`.
- If using `emitNext` with a handler that carelessly returns `true` for overflow, the producer may spin even though capacity is not freed. Retry only when a mechanism genuinely increases the chance of success.

For critical data, prefer `tryEmitNext`, handle `FAIL_OVERFLOW` explicitly, and never pretend the event was received.

## 7. Choosing the Right Sink Type: unicast, multicast, replay, and direct

### 7.1. Unicast: One Subscriber, Buffers for Later Consumer Registration

~~~java
Sinks.Many<Event> sink =
    Sinks.many().unicast().onBackpressureBuffer();
~~~

- Accepts **only one Subscriber** on the Flux view.
- Events emitted before the subscriber subscribes can be buffered and delivered when the subscriber arrives.
- The no-queue factory uses an unbounded queue by default; if the producer can emit heavily before the consumer is ready, consider bounding it.
- You can supply a custom queue, such as a fixed-capacity `ArrayBlockingQueue`, for explicit overflow behavior.

~~~java
Sinks.Many<Event> bounded =
    Sinks.many().unicast()
        .onBackpressureBuffer(new ArrayBlockingQueue<>(256));
~~~

### 7.2. Multicast with Backpressure Buffer: Multiple Subscribers Receiving New Events

~~~java
Sinks.Many<Event> sink =
    Sinks.many().multicast().onBackpressureBuffer();
~~~

- Allows multiple subscribers.
- Subscribers receive only events emitted after subscribing (plus whatever is buffered per backpressure/warm-up).
- Policy honors subscribers' demand; slow subscribers can cause the buffer to accumulate.
- Capacity and `autoCancel` can be specified via the appropriate overload.
- By default when all subscribers cancel, the sink can clear its buffer and stop accepting new subscribers; understand its lifecycle before using it as a long-lived event bus.

Bounded capacity example:

~~~java
Sinks.Many<Event> sink =
    Sinks.many().multicast().onBackpressureBuffer(
        512,  // bufferSize
        true  // autoCancel
    );
~~~

When demand divergence among subscribers exceeds capacity, `tryEmitNext` can return `FAIL_OVERFLOW`. Pick buffer size based on bursts and how long consumers may lag, not an arbitrary large number.

### 7.3. Direct Multicast: Choosing a Drop Policy Instead of Buffering

`directAllOrNothing()` and `directBestEffort()` do not attempt to buffer for slow subscribers like `onBackpressureBuffer`:

| Factory | When a Subscriber Has No Demand | Consequence |
| --- | --- | --- |
| `directAllOrNothing()` | Even one slow subscriber | Drops event for all subscribers on that emission; producer may receive `FAIL_OVERFLOW` |
| `directBestEffort()` | Some subscribers are slow while others have demand | Delivers to ready subscribers; drops individually for slow subscribers |
| `directBestEffort()` when nobody has demand | No subscriber can receive | Producer receives overflow failure |
| Both when there are no subscribers | No listeners/warm-up buffer | `tryEmitNext` may return `FAIL_ZERO_SUBSCRIBER` |

Choose direct sinks when **dropping is part of an acceptable contract**, such as latest-state updates, optional telemetry, or droppable signals. Do not use direct sinks for orders, transactions, or lossless events.

### 7.4. Replay: Late Subscribers Still Receive History

~~~java
Sinks.Many<Event> replayAll =
    Sinks.many().replay().all();

Sinks.Many<Event> last100 =
    Sinks.many().replay().limit(100);
~~~

Replay sinks cache events and replay them to late subscribers:

- `all()` retains full history, risking unbounded memory growth.
- `limit(n)` retains only a bounded number of historical elements.
- Time limits or combined count-and-time limits can be used.

Replay fits state/streams where late subscribers need history. It does not replace a durable database/event log: data in a Sink lives in process memory and is lost when the process stops.

### 7.5. Quick Selection

| Need | Suitable Variant |
| --- | --- |
| Single consumer; events arriving before subscriber must be kept | `unicast().onBackpressureBuffer(...)` |
| Multiple consumers receiving new events, demand-buffered | `multicast().onBackpressureBuffer(...)` |
| Multiple consumers; drop for all if one consumer is slow | `multicast().directAllOrNothing()` |
| Multiple consumers; drop individually for slow consumers | `multicast().directBestEffort()` |
| New consumers need to see bounded history | `replay().limit(n)` |
| Only need to keep history within a time window | `replay().limit(Duration)` or combined overload |
| Single value or async outcome only | `Sinks.one()` |
| Only completion/error with no data | `Sinks.empty()` |

## 8. Reading and Handling Each Emit Failure

### 8.1. `FAIL_NON_SERIALIZED` — Multiple Producers Emitting Concurrently

Appropriate actions:

- Switch to a single-writer queue.
- Use a lock if the critical section is short and all producers share the same lock.
- Use `emitNext` with `busyLooping` if contention is brief, with a deadline.
- Do not switch to `unsafe()` to hide the error.

Do not retry by spawning a new thread on every failure; that can worsen contention.

### 8.2. `FAIL_OVERFLOW` — Buffer Has No Room Left

Appropriate actions:

- Throttle the producer or apply backpressure at the callback source if the API allows.
- Reduce concurrency, speed up consumers, or partition load appropriately.
- Drop per business-allowed policy and count dropped events.
- Put events into a durable queue/database and re-emit when downstream is ready.
- Return an error to the producer so upstream decides on delayed retry.

Do not use `busyLooping` as an overflow fix: a buffer does not magically gain capacity just because the producer spins.

### 8.3. `FAIL_ZERO_SUBSCRIBER` — No Consumers Yet

Question to answer: must events emitted before subscribers arrive be retained?

- If yes, pick a suitable unicast buffer or replay.
- If no, a direct sink can return failure; the producer can ignore it while recording metrics.
- If consumers must exist before producers run, manage startup order and only start producers after subscriptions are established.

`currentSubscriberCount()` is only a best-effort point-in-time observation; do not use it as a guaranteed pre-emit check because state can change immediately afterward.

### 8.4. `FAIL_CANCELLED` — Consumers Cancelled

When subscribers leave, producers need to know whether to stop the external source. For example, if a Sink represents a per-client socket subscription, cancellation may be the moment to unregister the listener/close the socket. If the Sink is a shared event bus for multiple consumers, one subscriber cancelling is not necessarily a reason to stop the producer.

Do not ignore cancellation and keep generating events forever into a sink nobody is reading.

### 8.5. `FAIL_TERMINATED` — Emitting After Terminal

A Sink terminates only once. After a successful `tryEmitComplete` or `tryEmitError`, any subsequent `onNext` is a late event or a lifecycle bug. Check:

- Is the producer still running after application shutdown?
- Are two places calling complete/error?
- Is an old callback continuing to emit after the request/session ended?
- Should a new Sink be created for a new lifecycle instead of reusing a terminated Sink?

### 8.6. `FAIL_ZERO_SUBSCRIBER` and Terminal Signals Can Differ

Some Sinks can store terminal signals so later subscribers receive `onComplete`/`onError`; exact behavior depends on the Sink type. Therefore, do not apply a conclusion from `tryEmitNext` directly to `tryEmitComplete` or `tryEmitError`. Read the Javadoc of the factory in use and handle each result separately.

## 9. Complete Java 17+ Example: Overflow and Concurrent Producers

This example uses Project Reactor Core **3.8.8**, Java 17+, and Maven. The program demonstrates:

1. `tryEmitNext` with a one-element bounded unicast queue, showing `FAIL_OVERFLOW`.
2. Concurrent emission from two producers into a safe sink using `emitNext` and the `busyLooping` handler.
3. Closing the sink with `tryEmitComplete` after all producers finish.

Project structure:

~~~text
reactor-sinks-demo/
├── pom.xml
└── src/main/java/example/SinksEmissionDemo.java
~~~

### 9.1. File `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
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
                    <mainClass>example.SinksEmissionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 9.2. File `src/main/java/example/SinksEmissionDemo.java`

~~~java
package example;

import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import reactor.core.publisher.Sinks;

public final class SinksEmissionDemo {

    private static void demonstrateOverflow() {
        System.out.println("== bounded buffer ==");

        Sinks.Many<Integer> bounded = Sinks.many()
            .unicast()
            .onBackpressureBuffer(new ArrayBlockingQueue<>(1));

        System.out.println("first=" + bounded.tryEmitNext(1));
        System.out.println("second=" + bounded.tryEmitNext(2));
        System.out.println("complete=" + bounded.tryEmitComplete());

        bounded.asFlux().subscribe(
            value -> System.out.println("received=" + value),
            error -> System.out.println("error=" + error.getClass().getSimpleName()),
            () -> System.out.println("downstream complete")
        );
    }

    private static void demonstrateConcurrentProducers() throws Exception {
        System.out.println("== concurrent producers ==");

        Sinks.Many<Integer> sink = Sinks.many()
            .unicast()
            .onBackpressureBuffer();

        List<Integer> received =
            Collections.synchronizedList(new ArrayList<>());
        AtomicReference<Throwable> failure = new AtomicReference<>();
        CountDownLatch completed = new CountDownLatch(1);

        sink.asFlux().subscribe(
            received::add,
            failure::set,
            completed::countDown
        );

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<?>> tasks = new ArrayList<>();

        for (int producer = 0; producer < 2; producer++) {
            final int base = producer * 10;

            tasks.add(pool.submit(() -> {
                ready.countDown();

                if (!start.await(2, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("start timeout");
                }

                for (int i = 0; i < 10; i++) {
                    // Create a new handler for each emit.
                    sink.emitNext(
                        base + i,
                        Sinks.EmitFailureHandler.busyLooping(
                            Duration.ofSeconds(2))
                    );
                }
                return null;
            }));
        }

        if (!ready.await(2, TimeUnit.SECONDS)) {
            throw new IllegalStateException("producer not ready");
        }
        start.countDown();

        for (Future<?> task : tasks) {
            task.get();
        }

        pool.shutdown();
        if (!pool.awaitTermination(2, TimeUnit.SECONDS)) {
            throw new IllegalStateException("producer pool did not stop");
        }

        System.out.println("complete=" + sink.tryEmitComplete());

        if (!completed.await(2, TimeUnit.SECONDS)) {
            throw new IllegalStateException("sink did not complete");
        }
        if (failure.get() != null) {
            throw new IllegalStateException("downstream failed", failure.get());
        }

        List<Integer> sorted = new ArrayList<>(received);
        Collections.sort(sorted);

        System.out.println("received count=" + sorted.size());
        System.out.println("values=" + sorted);
    }

    public static void main(String[] args) throws Exception {
        demonstrateOverflow();
        demonstrateConcurrentProducers();
    }
}
~~~

Run from the `reactor-sinks-demo` directory (with JDK 17+ and Maven installed):

~~~bash
mvn -q compile exec:java
~~~

**Expected stdout:**

~~~text
== bounded buffer ==
first=OK
second=FAIL_OVERFLOW
complete=OK
received=1
downstream complete
== concurrent producers ==
complete=OK
received count=20
values=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
~~~

Explanation:

- The first queue has capacity 1 and no subscriber yet. `tryEmitNext(1)` takes the slot; `tryEmitNext(2)` is rejected with `FAIL_OVERFLOW`. Retrying the second emit with `tryEmitNext` does not free space in the queue.
- `tryEmitComplete` can still send the terminal signal while one element sits in the queue; when a subscriber subscribes, the buffered element is emitted and then completed.
- The concurrent example has one subscriber and two producers calling the Sink concurrently. `busyLooping` only handles `FAIL_NON_SERIALIZED` contention within a bounded time window; each emit creates a new handler.
- Actual interleaving between the two producers can vary. The program sorts a copy of the list before printing so stdout is stable; a Sink does not promise ordering by producer start time.
- `received count=20` proves the example received all 20 values; it does not prove busy-looping is optimal for every load. For large systems, consider a single writer and a bounded queue.
- `Collections.synchronizedList` protects the receiving list when callbacks may run on different producer threads. In production code, use concurrent structures or consumers matching actual requirements.

## 10. `tryEmitNext` Status Inspection: Examples for Each Result

Some statuses depend on the Sink type and timing. Example:

~~~java
// FAIL_ZERO_SUBSCRIBER: direct sink does not buffer when there are no listeners.
Sinks.Many<Integer> direct =
    Sinks.many().multicast().directAllOrNothing();

Sinks.EmitResult noSubscriber = direct.tryEmitNext(1);

// FAIL_TERMINATED: emitting after the sink has completed.
Sinks.Many<Integer> finished =
    Sinks.many().replay().all();

finished.tryEmitComplete();
Sinks.EmitResult afterComplete = finished.tryEmitNext(2);
~~~

`FAIL_CANCELLED` occurs when the sink has been cancelled by consumers/lifecycle. `FAIL_NON_SERIALIZED` occurs when a safe sink detects two overlapping emit operations. `FAIL_OVERFLOW` was demonstrated in section 9. Do not try to trigger race states in unit tests by relying on random timing; test handling policies per result by extracting decision logic into standalone functions.

### 10.1. Result-Handling Pattern with Explicit Actions

~~~java
void publish(Event event) {
    Sinks.EmitResult result = sink.tryEmitNext(event);

    switch (result) {
        case OK -> metrics.accepted();
        case FAIL_NON_SERIALIZED -> retryViaSingleWriter(event);
        case FAIL_OVERFLOW -> persistOrReject(event);
        case FAIL_ZERO_SUBSCRIBER -> metrics.noConsumer();
        case FAIL_CANCELLED -> stopSource();
        case FAIL_TERMINATED -> metrics.lateEvent();
    }
}
~~~

This is a **design pattern**; metric/queue/persistence methods are defined by the application. Merely incrementing counters without a policy for critical events can still lose data.

## 11. Connecting a Sink to Spring WebFlux

### 11.1. Bridging from a Callback API

Suppose a legacy SDK registers a callback to notify device status. A Sink can serve as the bridge:

~~~java
@Component
public class DeviceEventBridge {

    private final Sinks.Many<DeviceEvent> sink =
        Sinks.many().multicast().onBackpressureBuffer(256, true);

    public Flux<DeviceEvent> events() {
        return sink.asFlux();
    }

    public void onSdkEvent(DeviceEvent event) {
        Sinks.EmitResult result = sink.tryEmitNext(event);

        if (result != Sinks.EmitResult.OK) {
            // Apply a specific policy: metric, persist, reject, or stop source.
            handleRejectedEvent(event, result);
        }
    }

    public void close() {
        Sinks.EmitResult result = sink.tryEmitComplete();
        if (result != Sinks.EmitResult.OK) {
            recordCloseResult(result);
        }
    }

    private void handleRejectedEvent(
        DeviceEvent event,
        Sinks.EmitResult result
    ) {
        // Implementation depends on business requirements.
    }

    private void recordCloseResult(Sinks.EmitResult result) {
        // Record metrics/logs if needed.
    }
}
~~~

This is **Spring illustrative code**; imports, bean configuration, the `DeviceEvent` class, and real SDK callbacks are needed. Key points:

- The SDK callback is an imperative producer; it calls `onSdkEvent`.
- Reactive controllers/services receive `Flux<DeviceEvent>` via `events()`.
- `handleRejectedEvent` must make an explicit decision when an event is not accepted by the sink; do not ignore failures.
- `close()` should be called at the right lifecycle point (e.g., bean/application shutdown) and after the SDK producer has stopped, avoiding callbacks continuing to emit after terminal.
- With multiple subscribers, pick an appropriate multicast buffer and capacity. If events have only one consumer, unicast may fit better.

### 11.2. Controller Returning Publisher to the Framework

~~~java
@RestController
@RequestMapping("/devices")
public class DeviceController {

    private final DeviceEventBridge bridge;

    public DeviceController(DeviceEventBridge bridge) {
        this.bridge = bridge;
    }

    @GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<DeviceEvent> events() {
        return bridge.events();
    }
}
~~~

Spring WebFlux manages the response subscription. If a client disconnects, its subscriber can cancel; the bridge must understand how that affects the Sink and SDK. With a shared multicast, one client cancelling does not necessarily mean stopping the entire producer. With a single-client unicast, cancellation may be the moment to cancel the source callback.

Do not call `subscribe()` manually inside a controller and return an independent response. Let the framework manage HTTP lifecycle, errors, and cancellation.

### 11.3. Do Not Use a Sink When a Reactive Publisher Already Exists

If WebClient, R2DBC, or a library already returns `Flux`/`Mono`, prefer using it directly:

~~~java
public Flux<Product> products() {
    return webClient.get()
        .uri("/products")
        .retrieve()
        .bodyToFlux(Product.class);
}
~~~

Creating a Sink adds an imperative boundary, forcing the application to manage concurrency, overflow, terminal signals, and cleanup itself. Add one only when you genuinely need to bridge from a non-Reactive-Streams API.

## 12. Managing Lifecycle, Terminal Signals, and Cancellation

A Sink is not a permanent queue. It has a lifecycle:

1. Factory initialization.
2. Producer emits zero or more elements.
3. Consumers subscribe and process according to demand.
4. Producer finishes with `tryEmitComplete` or `tryEmitError`.
5. Producer stops; emissions after terminal are rejected.

Several rules:

- Only one terminal signal takes effect; do not send complete and then error.
- Stop the imperative source first or synchronize shutdown to avoid callbacks emitting after terminal.
- If subscribers cancel, check whether to stop the upstream SDK, unregister listeners, or close resources.
- Do not keep a Sink alive longer than the data/lifecycle it represents; a singleton event bus and a per-request stream have different cleanup requirements.
- If a Sink pattern is reused for a new session, usually create a new Sink for the new lifecycle instead of trying to reset a terminated Sink.
- For critical data, do not rely on an in-memory Sink as a durable event log. Persistence, acknowledgments, or an appropriate message broker are required.

## 13. Common Pitfalls and How to Avoid Them

**Pitfall 1 — Calling `tryEmitNext` and ignoring the result.** Producers can lose events due to overflow, cancellation, or zero subscribers. Classify `EmitResult`.

**Pitfall 2 — Thinking `OK` means all subscribers finished processing.** It only indicates the emission was accepted by the sink; it is not a business acknowledgment.

**Pitfall 3 — Using `emitNext` and assuming it always succeeds.** If the handler does not retry, the sink applies default failure behavior; some failures may throw or terminate the sink.

**Pitfall 4 — Multiple producers calling a Sink simultaneously without handling `FAIL_NON_SERIALIZED`.** Use a single writer, controlled lock, or deadline-bounded retry handler.

**Pitfall 5 — Using `busyLooping` for overflow.** Busy looping handles unserialized contention; it does not create new capacity in a full buffer.

**Pitfall 6 — Using unbounded `busyLooping`.** Ties up producer threads and stalls the system. Always use a reasonable deadline; if contention is common, redesign producers.

**Pitfall 7 — Reusing the same `busyLooping` handler.** The deadline is measured from when the handler was created. Create a fresh handler per emit call.

**Pitfall 8 — Using the default unbounded unicast queue for a source that can emit long before a subscriber arrives.** Memory can grow continuously. Consider a bounded queue and handling `FAIL_OVERFLOW`.

**Pitfall 9 — Using `replay().all()` on an infinite stream.** History grows over time. Use count or time bounds if retaining everything is unnecessary.

**Pitfall 10 — Choosing direct sinks when event loss is unacceptable.** directAllOrNothing/directBestEffort can drop based on demand. Choose buffering or persistence when preservation is required.

**Pitfall 11 — Thinking unicast can have multiple subscribers.** Its Flux view accepts only one subscriber. If fan-out is needed, use multicast/replay.

**Pitfall 12 — Assuming a multicast buffer has infinite capacity.** Capacity is bounded by factory/configuration. When full, producers must have an overflow policy.

**Pitfall 13 — Using a Sink as a replacement for every Flux.** If the source is already reactive, a Sink only adds management complexity.

**Pitfall 14 — Using `Sinks.unsafe()` to hide concurrency errors.** Unsafe drops protective checks; use only when external serialization is proven.

**Pitfall 15 — Calling complete/error multiple times or emitting after terminal.** Check lifecycle and stop producers at the right time.

**Pitfall 16 — Using null to represent empty events.** Sinks do not emit null. Use an explicit data type or appropriate terminal signal.

**Pitfall 17 — Thinking a full buffer automatically errors the subscriber immediately.** With `tryEmitNext`, the producer receives the overflow result and must act; with `emitNext`, default behavior can transition to a terminal error. Distinguish the API in use.

**Pitfall 18 — Not monitoring drops and overflows.** Record metrics for `FAIL_OVERFLOW`, `FAIL_NON_SERIALIZED`, rejected events, queue depth, and consumer rate to detect issues early.

## 14. Self-Check Exercises

1. What does `tryEmitNext(value)` return? **`Sinks.EmitResult`**, not a boolean.
2. Does `OK` guarantee consumers finished processing the event? **No**, only that the sink accepted the signal at emit time.
3. What does `FAIL_NON_SERIALIZED` indicate? **Overlapping, unserialized emit operations**.
4. Should `busyLooping` be used when `FAIL_OVERFLOW` occurs? **No**, capacity/demand must be addressed.
5. What can `emitNext(value, FAIL_FAST)` do on concurrent emits to a safe sink? **It can throw `Sinks.EmissionException` due to `FAIL_NON_SERIALIZED`**.
6. Can a `unicast().onBackpressureBuffer()` have two subscribers? **No**, only one subscriber.
7. How does `multicast().directBestEffort()` handle slow subscribers? **Drops for slow subscribers, continues emitting to subscribers with demand**.
8. How does `multicast().directAllOrNothing()` handle a subscriber with no demand? **Drops the event for all subscribers on that emission**.
9. When a bounded buffer is full, what does `tryEmitNext` typically return? **`FAIL_OVERFLOW`**.
10. Does `tryEmitComplete` require demand like `onNext`? **No**, terminal signals are not data elements.
11. Why should a `busyLooping` handler not be cached? **The deadline is measured from handler creation**, so later uses may already be expired.
12. What risk does `replay().all()` carry? **Retains all history in memory**, which can grow without bound.
13. When an SDK callback emits after the sink has completed, what result can appear? **`FAIL_TERMINATED`**.
14. When WebClient already returns a `Flux`, should you wrap it in a Sink? **Usually not needed**; keep the reactive Publisher directly.
15. Why can a safe Sink still return `FAIL_NON_SERIALIZED`? Because it detects concurrent access and rejects unserialized signals, protecting the Reactive Streams contract.

## 15. Official References

- [Project Reactor Reference — Sinks](https://projectreactor.io/docs/core/release/reference/coreFeatures/sinks.html): Sink types, unicast/multicast/replay, concurrent emission, and converting to `Flux`/`Mono`.
- [Project Reactor API — Sinks.Many](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.Many.html): `tryEmitNext`, `emitNext`, `tryEmitComplete`, `tryEmitError`, and failure behavior.
- [Project Reactor API — Sinks.EmitResult](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.EmitResult.html): meanings of `OK`, `FAIL_NON_SERIALIZED`, `FAIL_OVERFLOW`, `FAIL_ZERO_SUBSCRIBER`, `FAIL_CANCELLED`, and `FAIL_TERMINATED`.
- [Project Reactor API — Sinks.EmitFailureHandler](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.EmitFailureHandler.html): `FAIL_FAST`, `busyLooping(Duration)`, deadline, and retry conditions.
- [Project Reactor API — Sinks.MulticastSpec](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.MulticastSpec.html): buffer capacity, `autoCancel`, directAllOrNothing, and directBestEffort.
- [Project Reactor API — Sinks.UnicastSpec](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.UnicastSpec.html): single subscriber and custom queue.
- [Reactive Streams JVM Specification](https://github.com/reactive-streams/reactive-streams-jvm#specification): rules for signal serialization, demand, terminal signals, and cancellation.