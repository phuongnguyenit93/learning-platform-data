# Unicast, Multicast, and Replay by Use Case in Reactor

## 1. The Problem: One Event Source, Multiple Distribution Patterns

In Spring WebFlux and Project Reactor, a data source can be sensor events, library callbacks, internal notifications, status updates, or data from external services. When there are one or more subscribers, you must determine:

- Is there **a single subscriber** or do you need to emit to **multiple subscribers**?
- Should late subscribers receive only new events, or receive part/all of the history?
- If a subscriber processes slowly, should the producer wait, buffer, report an error, or drop events?
- Does data restart for each subscriber, or does the producer emit independently of subscribers?
- When no subscribers remain, does the source stop? When the source has completed, what will later subscribers see?

Within `Sinks.Many`, the three core choices are:

- **Unicast:** a sink for at most one subscriber; data can be buffered before the first subscriber subscribes.
- **Multicast:** a sink emitting new events to multiple active subscribers; late subscribers typically only see events emitted after they subscribe.
- **Replay:** a multicast sink that retains history; late subscribers receive the retained history and then continue receiving new events.

**Replay is a history-retention policy for multicast.** These three concepts are related yet not interchangeable. Choosing wrongly can cause subscribers to miss events, hold memory too long, or stall the producer due to backpressure.

After this lesson, you will be able to explain unicast/multicast/replay, distinguish them from cold/hot publishers, choose an appropriate `Sinks.Many`, manage buffers and emission failures, use `publish`, `share`, `replay`, and `cache`, write Java 17+ examples, and test with StepVerifier.

## 2. Two Independent Axes: cold/hot and unicast/multicast/replay

Before choosing a sink, separate two questions.

**Cold or hot** describes the relationship between data production and subscription:

- **Cold publisher:** each new subscriber typically triggers a new source execution, starting over from the beginning. For example, `Flux.range(1, 3)` or `Mono.fromCallable(...)`.
- **Hot publisher:** the producer can emit data independently of any specific subscriber. Late subscribers typically receive only signals emitted after they subscribe, unless the source has a replay/cache policy.

**Unicast, multicast, or replay** describes how a source distributes data to subscribers:

- **Unicast:** only one subscriber is allowed to subscribe.
- **Multicast:** multiple subscribers receive new events together.
- **Replay:** multiple subscribers receive new events and late subscribers also receive retained history replayed.

The two axes are not synonymous:

| Source | Cold/Hot | Subscribers and History |
| --- | --- | --- |
| `Flux.range(1, 3)` | Cold | Each subscriber gets a fresh emission run; no shared history |
| `Sinks.many().unicast().onBackpressureBuffer()` | Active producer sink, typically used as a hot source | One subscriber; buffers data before the first subscriber |
| `Sinks.many().multicast().onBackpressureBuffer()` | Hot | Multiple subscribers; emits new events, does not replay history to latecomers |
| `Sinks.many().replay().limit(10)` | Hot | Multiple subscribers; replays up to the 10 most recent elements |
| `source.cache(10)` | Shares and caches results from the first subscribe | Later subscribers can receive cached history |

A cold publisher can be shared via `share()` or `publish()`. A hot source may or may not have replay. Therefore, do not use the word “hot” as if it always meant “multicast with replay”.

## 3. Unicast: One Producer Sink, One Subscriber

### 3.1. Characteristics

Creating a unicast sink:

~~~java
Sinks.Many<Integer> sink =
    Sinks.many().unicast().onBackpressureBuffer();

Flux<Integer> view = sink.asFlux();
~~~

- `Sinks.Many` is the producer object; the application emits data via `tryEmitNext`, `emitNext`, `tryEmitComplete`, or `tryEmitError`.
- `asFlux()` provides the Publisher view for consumers to subscribe to.
- Only **one subscriber** is accepted. A second subscriber to the same unicast view is rejected and receives an error.
- `onBackpressureBuffer()` retains elements when the subscriber has not requested enough yet.
- If the producer emits before the first subscriber subscribes, those elements are buffered and delivered to the first subscriber when it arrives.
- This is a buffer waiting for the **single subscriber**, not replay for multiple late subscribers.

Example:

~~~java
Sinks.Many<Integer> sink =
    Sinks.many().unicast().onBackpressureBuffer();

sink.tryEmitNext(10);
sink.tryEmitNext(20);

sink.asFlux().subscribe(System.out::println);

sink.tryEmitNext(30);
sink.tryEmitComplete();
~~~

Output:

~~~text
10
20
30
~~~

The first two elements were emitted before a subscriber existed, yet they were buffered. When the first subscriber subscribed, they were forwarded downstream; element 30 was emitted directly afterward.

### 3.2. Backpressure and Memory Bounds

A unicast sink honors the single subscriber's demand. However, default `onBackpressureBuffer()` can use an unbounded queue. If the producer emits faster than the consumer over a long period, the queue grows and can cause memory pressure.

You can supply your own queue via the `onBackpressureBuffer(Queue<T>)` overload. That queue must satisfy the API's single-producer/single-consumer requirement. If the queue is bounded and full, the producer can receive `FAIL_OVERFLOW`. A concrete policy is needed:

- Use a bounded queue if backlogged data must be capped.
- Handle `FAIL_OVERFLOW` by rejecting, retrying under control, or reporting a business error.
- If buffering is not acceptable and the subscriber should receive an error when there is no demand, consider `Sinks.many().unicast().onBackpressureError()`.

Do not treat a buffer as infinite memory to “prevent data loss”. A buffer only shifts a slowdown problem from the present moment into memory usage and wait latency; if the producer rate persistently exceeds the consumer rate, backlog still grows.

### 3.3. When to Use Unicast?

Fits when one component produces data and a single component is responsible for consuming it, such as an adapter turning callbacks from an imperative library into a `Flux` for one consumer, an internal queue with a single worker consumer, or a processing session where one subscriber owns the stream.

Do not use unicast if multiple services need to independently receive the same event. In that case, multicast or a message broker/queue with suitable semantics is required.

## 4. Multicast: One Source Emitting to Multiple Subscribers

### 4.1. Live-Only Multicast

Creating a multicast sink:

~~~java
Sinks.Many<String> sink =
    Sinks.many().multicast().onBackpressureBuffer();

Flux<String> events = sink.asFlux();
~~~

Every currently subscribed subscriber can receive new events. A subscriber subscribing **after** an event has been emitted does not automatically receive past events.

Example:

~~~java
Sinks.Many<String> sink =
    Sinks.many().multicast().onBackpressureBuffer();

Flux<String> events = sink.asFlux();

events.subscribe(value -> System.out.println("A: " + value));
sink.tryEmitNext("one");
sink.tryEmitNext("two");

events.subscribe(value -> System.out.println("B: " + value));
sink.tryEmitNext("three");
sink.tryEmitComplete();
~~~

Output:

~~~text
A: one
A: two
A: three
B: three
~~~

Subscriber A subscribed before `one` and `two` were emitted, so it receives both. Subscriber B arrived later, so it only receives `three`.

**Warm-up note:** some multicast buffer overloads can retain a few elements emitted **before the first subscriber** to warm up the sink. This does not turn multicast into replay for all late subscribers. Distinguish warm-up data before the first subscriber from history already emitted to earlier subscribers.

### 4.2. Multi-Subscriber Backpressure

With `multicast().onBackpressureBuffer(...)`, Reactor regulates according to subscribers' demand. When one subscriber is slow or has not requested yet, that subscriber can force the source to hold data in the buffer. If demand divergence exceeds buffer capacity, `tryEmitNext` can return `FAIL_OVERFLOW`; if using `emitNext` with a failure handler, error behavior depends on the chosen handler.

An overload lets you configure the buffer and `autoCancel`:

~~~java
Sinks.Many<Event> sink =
    Sinks.many().multicast().onBackpressureBuffer(
        256,
        true
    );
~~~

This is a snippet: `Event` is the application's data type. Argument 256 is the buffer limit; `true` enables `autoCancel`. By default, when all subscribers cancel, a multicast sink cancels its active state, clears its buffer, and stops accepting new subscribers. This behavior can be adjusted with the `autoCancel` parameter when there is a clear lifecycle reason.

### 4.3. Two Unbuffered Multicast Modes

Reactor provides two direct modes to choose how slow subscribers are handled:

| Sink | When One Subscriber Has No Demand | Other Subscribers |
| --- | --- | --- |
| `directAllOrNothing()` | The current event is dropped for everyone if at least one subscriber is not ready | Nobody receives that event |
| `directBestEffort()` | Only the slow subscriber misses the current event | Subscribers with demand still receive it |

Neither direct mode replays history or buffers like `onBackpressureBuffer`. Slow subscribers are not terminated solely for missing events; once they request again, they continue receiving new events.

Use `directBestEffort()` for status update notifications where a subscriber can fetch a fresh snapshot itself, such as current position or dashboard metrics. Use `directAllOrNothing()` when all subscribers must observe the exact same set of events and if one subscriber is unready, the event should not be emitted to anyone. For transactional or audit data requiring guaranteed processing, dropping may be inappropriate; a reliable storage/queue mechanism is needed.

### 4.4. When to Use Multicast?

- Broadcasting state to multiple active screens or WebSocket sessions.
- Sending internal updates to multiple components interested in new events.
- Data fan-out where late subscribers do not need history.
- One producer emitting the same events to multiple consumers in the same process.

If subscribers must be able to go offline for a while and then read all missed events, live-only multicast does not meet the requirement; use bounded replay or a message broker with retention/offsets.

## 5. Replay: Multicast Retaining History for Late Subscribers

### 5.1. Replay by Element Count

Creating a replay sink:

~~~java
Sinks.Many<Integer> sink =
    Sinks.many().replay().limit(3);

Flux<Integer> events = sink.asFlux();
~~~

`limit(3)` keeps at most the three most recent elements. New subscribers receive the historical elements within the limit and then continue receiving new events.

Example:

~~~java
Sinks.Many<Integer> sink =
    Sinks.many().replay().limit(3);

Flux<Integer> events = sink.asFlux();

sink.tryEmitNext(1);
sink.tryEmitNext(2);
sink.tryEmitNext(3);
sink.tryEmitNext(4);

events.subscribe(value -> System.out.println("late: " + value));

sink.tryEmitNext(5);
sink.tryEmitComplete();
~~~

Output:

~~~text
late: 2
late: 3
late: 4
late: 5
~~~

When the subscriber subscribed, the retained history was `[2, 3, 4]`; afterward, event 5 was emitted live. Replay does not recreate the source from the start; it sends the elements stored by the sink.

### 5.2. Replay Configurations

| Configuration | Retained History | Suitable For |
| --- | --- | --- |
| `replay().all()` | All emitted elements | Finite streams, small and clearly bounded history |
| `replay().limit(n)` | At most the n most recent elements | Recent snapshots/events, bounding memory by count |
| `replay().limit(Duration)` | Elements still within the max age window | Events valid only within a time window |
| `replay().limit(n, Duration)` | Combines both count and age limits | Controlling both memory and data staleness |
| `replay().latest()` | Most recent value | Current state, when subscribers only need the latest snapshot |
| `replay().latestOrDefault(value)` | Most recent value or an initial default | Subscribers always need an initial value |

`replay().all()` can retain the entire history in memory; on an infinite source, this risks unbounded memory growth. Prefer `limit(n)` or time-based limits if business requirements do not need full history.

With time-based replay, Reactor checks element age on signals; do not treat it as a background task running down to the exact millisecond to evict every item immediately upon expiry. If strict retention/auditing is required, use a store with explicit retention policies.

### 5.3. Replay Does Not Mean a Durable Event Store

A replay sink keeps history in process memory. When the application restarts, retained data does not automatically recover from disk. Nor does it provide durable offsets/checkpoints like Kafka or an event log system.

Use replay for late subscribers within the same application lifecycle, short-term caching, or recent snapshots. If requirements include recovery after restart, reprocessing from offsets, auditing, or guaranteed zero event loss, a durable storage source is required.

## 6. Comparing Unicast, Multicast, and Replay

| Criterion | Unicast | Multicast | Replay |
| --- | --- | --- | --- |
| Subscriber count | At most 1 | Multiple | Multiple |
| Late subscribers | First subscriber receives previously buffered data | Only receive new events after subscribing, aside from warm-up before the first subscriber | Receive retained history then new events |
| Buffer/history | Queue for one subscriber | Buffer serving current subscribers' demand | Bounded or unbounded replay history |
| Backpressure | Follows single subscriber's demand | Multi-subscriber demand; slow subscribers can affect the buffer | Each subscriber reads history/live per its own demand |
| Main risk | Single consumer only; queue growth | Slow subscribers fill buffer or data dropped in direct modes | Retaining oversized history, replaying stale data |
| Use case | One consumer owns the stream | Live broadcast | Broadcast with history for new subscribers |

Choose based on **the data delivery contract**, not familiar operator names. A helpful question is: “If a subscriber arrives 10 seconds late, what must it receive?” The answer usually settles live-only vs. replay.

## 7. Other Publisher-Sharing Operators

You do not always need to create a sink manually. If you already have a source `Flux`, Reactor has sharing/connection/caching operators.

### 7.1. publish and ConnectableFlux

`publish()` creates a `ConnectableFlux`. Subscribers can register first, and then the application calls `connect()` to start subscribing to the source:

~~~java
ConnectableFlux<Integer> shared =
    Flux.range(1, 3).publish();

shared.subscribe(value -> System.out.println("A " + value));
shared.subscribe(value -> System.out.println("B " + value));

shared.connect();
~~~

Both subscribers are gathered before the source starts, so both receive the source's elements. `connect()` returns a `Disposable` that can be used to disconnect.

Common variants:

- `publish().autoConnect(n)`: auto-connects when n subscribers arrive; after connecting, the source does not auto-disconnect just because subscribers drop.
- `publish().refCount(n)`: auto-connects when n subscribers arrive and tracks cancellations; when subscriber count drops below the threshold, the source may disconnect.
- `publish().refCount(n, gracePeriod)`: adds a wait window before disconnecting so new subscribers have a chance to join.

`publish()` coordinates demand among active subscribers and can pause requesting from the source when one subscriber has no demand.

### 7.2. share

`share()` is a concise choice for sharing a source among concurrent subscribers:

~~~java
Flux<Event> live = eventSource.share();
~~~

Multiple concurrently active subscribers can share one upstream subscription. Late subscribers do not receive previously emitted history; they receive events from the time they join. `share()` is not replay/cache.

Because `share()` has subscriber-based connection semantics, understand the lifecycle when all subscribers cancel and when the source completes/errors. If you need explicit control over subscriber threshold and grace period, use `publish().refCount(...)`.

### 7.3. replay and cache

If you want to retain history from an existing `Flux`:

~~~java
Flux<Event> recent = eventSource.replay(100).autoConnect(1);
~~~

This is a `ConnectableFlux` replaying at most 100 elements; `autoConnect(1)` starts the source when the first subscriber subscribes.

If you want automatic caching when the first subscriber arrives:

~~~java
Flux<Event> cached = eventSource.cache(100);
~~~

`cache()` options can retain all signals; `cache(n)` bounds element count, `cache(Duration)` bounds time, and `cache(n, Duration)` combines both. Cache changes the source's lifecycle: later subscribers can receive cached results instead of triggering a new upstream execution.

**Caution:** do not cache publishers containing personal/request-specific data or results that vary by user permissions in a shared cache without proper partitioning keys/lifecycle. Sharing a result across subscribers can leak data or return stale snapshots.

### 7.4. When to Use Sinks Instead of Operators?

- Use `Sinks.Many` when **the application needs to actively emit events** from callbacks, listeners, or an imperative source.
- Use `share`, `publish`, `replay`, and `cache` when you already have a publisher and only need to change how that publisher is subscribed to, shared, or cached.
- Use a broker/event log when durable retention, independent consumers, cross-restart replay, or cross-process communication is needed.

Do not create a `Sinks.Many` just to share a `Flux.range` that could use `share()` or `publish()`.

## 8. Emitting Safely: tryEmitNext and emitNext

`Sinks` was designed to replace calling `onNext` directly on legacy Processors. Default sinks detect unserialized concurrent emit operations to prevent Reactive Streams violations.

There are two API families:

- `tryEmitNext(value)`, `tryEmitComplete()`, `tryEmitError(error)`: return `Sinks.EmitResult`, letting the caller inspect whether emission succeeded or failed.
- `emitNext(value, failureHandler)`, `emitComplete(failureHandler)`, `emitError(error, ...)`: use an `EmitFailureHandler` to decide how to handle certain failures.

Example:

~~~java
Sinks.EmitResult result = sink.tryEmitNext(event);

if (result != Sinks.EmitResult.OK) {
    // Choose a concrete policy: bounded retry,
    // log/metric, reject, or transition to error.
}
~~~

Do not ignore the result of `tryEmitNext`. An emission can fail because the sink is terminated, cancelled, buffer full, lacks matching subscribers, or encountered unserialized concurrent emission. Handle based on the sink type and returned result.

`emitNext(value, Sinks.EmitFailureHandler.FAIL_FAST)` is fail-fast emission; on failure, it can throw an exception per contract. `EmitFailureHandler.busyLooping(timeout)` can retry for a bounded time upon contention, but should not be used as a general fix for an overloaded producer. If producers continuously outrun consumer capacity, spin-retrying only burns CPU.

### 8.1. Multiple Producer Threads

Suppose two threads call `tryEmitNext` at the same time. A default sink detects unserialized concurrent signals and may return `FAIL_NON_SERIALIZED`. That means producers must decide how to serialize/queue emissions; do not assume the sink automatically turns every concurrent call into an unbounded queue.

Ways to handle this:

1. Put events into a bounded queue and use a single producer/dispatcher to emit sequentially into the sink.
2. Use `emitNext` with a bounded-retry failure handler if contention is brief and acceptable.
3. If business ordering matters, attach sequence numbers or serialize at the source layer before emitting.
4. Consider `Sinks.unsafe()` only when the application itself guarantees all signals are serialized per spec. Do not expose an unsafe sink on public APIs where callers cannot guarantee that.

Thread-safe here means the sink detects/handles contention per contract; it does not mean every concurrent producer is always accepted, every event always succeeds, or business ordering is automatically preserved.

## 9. Backpressure and Slow Subscribers: Choosing a Policy

Suppose a producer emits 1,000 events/second, subscriber A processes 1,000 events/second, and subscriber B only processes 100 events/second. With buffered multicast, elements waiting for B can grow the buffer up to its limit. There are four common decisions:

| Policy | Behavior | When Suitable |
| --- | --- | --- |
| Buffer | Holds events waiting for demand | Slowdown is temporary and backlog is bounded |
| Fail/overflow | Reports failure when buffer is full | Data loss is unacceptable; producer must handle pressure |
| Drop slow subscriber | Drops events on subscribers without demand | Subscribers can fetch a fresh snapshot themselves |
| Drop all | If any subscriber is slow, drops that event for everyone | Every subscriber must observe the exact same set of events |

In Reactor multicast:

- `onBackpressureBuffer` uses a buffer and can overflow.
- `directBestEffort` drops only for slow subscribers.
- `directAllOrNothing` drops for everyone if any subscriber lacks demand.

**There is no single right choice for every business domain.** For audit events, payment commands, or events requiring exact processing per contract, do not choose drop just so the system “never stalls”. For a dashboard displaying the latest state, dropping intermediate states can be acceptable.

Backpressure does not automatically throttle an external callback if that callback keeps firing regardless of demand. In that case, you need bounded queues, rate limits, drop policies, or a demand-aware upstream protocol.

## 10. Runnable Java 17+ Program: Comparing the Three Sink Types

The example below uses Reactor Core 3.8.6. It emits data synchronously in order so output is easy to verify.

Create `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.6'
}

application {
    mainClass = 'BroadcastModesDemo'
}
~~~

Create `src/main/java/BroadcastModesDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

public final class BroadcastModesDemo {
    private static void emit(Sinks.Many<Integer> sink, int value) {
        Sinks.EmitResult result = sink.tryEmitNext(value);
        if (result != Sinks.EmitResult.OK) {
            throw new IllegalStateException("emit failed: " + result);
        }
    }

    private static void complete(Sinks.Many<Integer> sink) {
        Sinks.EmitResult result = sink.tryEmitComplete();
        if (result != Sinks.EmitResult.OK) {
            throw new IllegalStateException("complete failed: " + result);
        }
    }

    public static void main(String[] args) {
        // 1. UNICAST: buffers before the first subscriber, only one subscriber.
        Sinks.Many<Integer> unicast =
            Sinks.many().unicast().onBackpressureBuffer();
        List<Integer> unicastValues = new ArrayList<>();

        emit(unicast, 1);
        emit(unicast, 2);
        unicast.asFlux().subscribe(unicastValues::add);
        emit(unicast, 3);
        complete(unicast);

        System.out.println("unicast=" + unicastValues);

        // 2. MULTICAST: late subscriber does not receive already-emitted history.
        Sinks.Many<Integer> multicast =
            Sinks.many().multicast().onBackpressureBuffer();
        Flux<Integer> live = multicast.asFlux();

        List<Integer> early = new ArrayList<>();
        List<Integer> late = new ArrayList<>();

        live.subscribe(early::add);
        emit(multicast, 1);
        emit(multicast, 2);

        live.subscribe(late::add);
        emit(multicast, 3);
        complete(multicast);

        System.out.println("multicast early=" + early);
        System.out.println("multicast late=" + late);

        // 3. REPLAY: late subscriber receives the last two elements.
        Sinks.Many<Integer> replay =
            Sinks.many().replay().limit(2);
        Flux<Integer> history = replay.asFlux();

        List<Integer> replayEarly = new ArrayList<>();
        List<Integer> replayLate = new ArrayList<>();

        history.subscribe(replayEarly::add);
        emit(replay, 1);
        emit(replay, 2);
        emit(replay, 3);

        history.subscribe(replayLate::add);
        emit(replay, 4);
        complete(replay);

        System.out.println("replay early=" + replayEarly);
        System.out.println("replay late=" + replayLate);
    }
}
~~~

Run with `gradle run --quiet`, or `./gradlew run --quiet` if the project has a Gradle Wrapper.

Stdout:

~~~text
unicast=[1, 2, 3]
multicast early=[1, 2, 3]
multicast late=[3]
replay early=[1, 2, 3, 4]
replay late=[2, 3, 4]
~~~

Explanation:

1. **Unicast:** 1 and 2 were emitted before any subscriber existed; the buffer kept them for the single subscriber. The subscriber receives 1, 2, then live event 3.
2. **Multicast:** A subscribed before events 1 and 2, so it receives all three. B subscribed after event 2, so it receives only event 3.
3. **Replay:** the sink caps history at two elements. When B arrives, history holds 2 and 3; afterward B receives live event 4. A joined from the start and receives 1, 2, 3, 4.

The example uses `subscribe(Consumer)` so subscribers request unbounded by default; it illustrates history and subscriber count, not slow-subscriber testing. Every emission checks `EmitResult`, never ignoring emit failures.

`block()` is not used in this demo; the sink emits synchronously and the lists are updated directly as `onNext` runs.

## 11. Testing with JUnit 5 and StepVerifier

You can test semantics without opening sockets, sleeping threads, or relying on timing. Replace the `dependencies` block in `build.gradle` with:

~~~groovy
dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.6'
    testImplementation 'io.projectreactor:reactor-test:3.8.6'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.2'
}

test {
    useJUnitPlatform()
}
~~~

Create `src/test/java/BroadcastModesTest.java`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;
import reactor.test.StepVerifier;

class BroadcastModesTest {
    @Test
    void unicastBuffersUntilItsOnlySubscriberArrives() {
        Sinks.Many<Integer> sink =
            Sinks.many().unicast().onBackpressureBuffer();

        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(1));
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(2));
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitComplete());

        StepVerifier.create(sink.asFlux())
            .expectNext(1, 2)
            .verifyComplete();
    }

    @Test
    void multicastLateSubscriberReceivesOnlyNewSignals() {
        Sinks.Many<Integer> sink =
            Sinks.many().multicast().onBackpressureBuffer();

        Flux<Integer> view = sink.asFlux();
        List<Integer> first = new ArrayList<>();
        List<Integer> late = new ArrayList<>();

        view.subscribe(first::add);
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(1));
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(2));

        view.subscribe(late::add);
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(3));
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitComplete());

        assertEquals(List.of(1, 2, 3), first);
        assertEquals(List.of(3), late);
    }

    @Test
    void replaySinkKeepsOnlyConfiguredHistory() {
        Sinks.Many<Integer> sink =
            Sinks.many().replay().limit(2);

        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(1));
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(2));
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(3));
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitComplete());

        StepVerifier.create(sink.asFlux())
            .expectNext(2, 3)
            .verifyComplete();
    }
}
~~~

Run `gradle test` or `./gradlew test`.

The three tests verify three different contracts:

- Unicast retains elements before the first subscriber and delivers them to the one subscriber.
- Multicast does not send previously emitted history to late subscribers.
- Replay retains and replays only historical elements within the configured limit.

The tests use synchronous sinks and lambda subscribers with default demand; if you need to test partial-request subscribers or overflow, use `StepVerifier.create(publisher, initialRequest)` and drive `thenRequest(n)` to create explicit demand.

## 12. Applications in Spring WebFlux

### 12.1. Broadcasting the Latest State to Multiple Clients

Suppose a service receives status-update callbacks from a device. If screens only need **the current value**, every intermediate state is not necessarily needed:

~~~java
@Service
public class DeviceStatusService {
    private final Sinks.Many<DeviceStatus> sink =
        Sinks.many().replay().limit(1);

    public Flux<DeviceStatus> statusStream() {
        return sink.asFlux();
    }

    public Sinks.EmitResult publish(DeviceStatus status) {
        return sink.tryEmitNext(status);
    }
}
~~~

This is a service snippet; `DeviceStatus` and callback handling are defined by the application. `replay().limit(1)` gives new subscribers the most recent status value and then keeps delivering updates. Callers must check the result of `publish`; the service can record metrics/logs or apply its own policy when emit fails.

### 12.2. Server-Sent Events Endpoint

The controller can return the `Flux` directly:

~~~java
@RestController
class DeviceController {
    private final DeviceStatusService service;

    DeviceController(DeviceStatusService service) {
        this.service = service;
    }

    @GetMapping(
        value = "/devices/status",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    Flux<DeviceStatus> status() {
        return service.statusStream();
    }
}
~~~

This is a WebFlux snippet; `MediaType`, `GetMapping`, `RestController`, `Flux`, and the service/DTO definitions must be imported/defined. Each HTTP subscriber joins the stream under the chosen sink policy. With replay limit 1, new clients receive the latest snapshot before new updates.

**Lifecycle consideration:** a singleton sink in a Spring service can live for the lifetime of the application context. Decide when to complete/error, how to release callback resources, and behavior when no clients remain. Do not create a new sink on every controller call if the goal is to share one status stream.

### 12.3. When Do WebSocket/SSE Need Replay?

- Status dashboards: replay 1 or latest may suffice.
- Clients needing the last few updates to render UI: replay bounded by count or time.
- Chat/event history that must be complete: use a database/event store; a replay sink is only process memory.
- Transactional events: use durable storage, consumer offsets, and deduplication rather than relying on multicast/drop.

## 13. Lifecycle, Termination, and Cancellation

A sink does not emit only `onNext`. The producer can also emit terminal signals:

- `tryEmitComplete()` / `emitComplete(...)`: normal termination; no further elements emitted afterward.
- `tryEmitError(error)` / `emitError(error, ...)`: error termination.
- Subscriber calls `cancel` / disposes `Disposable`: no longer wants to receive data.
- With multicast using `autoCancel`, when all subscribers cancel, the sink can clear its buffer and stop accepting new subscribers per configuration.

A subscriber arriving after a sink has terminated can receive the terminal signal immediately; a replay sink can also emit retained history before the terminal signal. This differs from an active source where late subscribers receive only new data.

**Do not use `complete` to simulate pausing.** Terminal means finished; that sink cannot be reopened to emit more data. If a new session is needed, create a new publisher/sink per business lifecycle.

When an HTTP client disconnects, the endpoint's subscriber may be cancelled. That does not mean a singleton producer should complete the entire sink, because other clients may still be listening. Distinguish cancellation of one subscriber from shutdown of the shared source.

## 14. Common Pitfalls and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using unicast for multiple listening services | Second subscriber is rejected | Use multicast or replay |
| Thinking multicast automatically resends history to new clients | Late clients miss prior events | Use replay/cache or load a separate snapshot |
| Using replay `all` for infinite streams | History kept in RAM grows without bound | Use `limit(n)`, TTL, or a durable store |
| Thinking unicast pre-subscriber buffering is multi-consumer replay | Only the single subscriber receives that queue | Distinguish unicast queue from replay history |
| Ignoring `Sinks.EmitResult` | Events may not be emitted without the app knowing | Check every emit result and have an explicit policy |
| Using `directBestEffort` for audits needing complete data | Slow subscribers lose events | Use durable queues/logs and acks/offsets |
| Using `directAllOrNothing` without knowing about slow subscribers | One subscriber without demand can drop events for everyone | Evaluate group-wide semantics before choosing |
| Unbounded or oversized multicast buffers | Backlog consumes RAM and raises latency | Choose capacity, overflow policy, and metrics |
| Assuming Sinks serialize all producer threads automatically | Concurrent emits can return `FAIL_NON_SERIALIZED` | Serialize producers or use a bounded failure handler |
| Using `Sinks.unsafe()` from multiple callers | Can violate Reactive Streams | Use only when serialization is guaranteed yourself |
| Using `share()` and expecting new subscribers to get history | `share` is live sharing, not replay | Use `replay()` or `cache()` if history is needed |
| Using `cache()` for per-user data in a shared cache | Can share wrong results/risk data exposure | Partition cache by key/permissions/lifecycle |
| Completing the sink when one client disconnects | Remaining clients lose the stream | Cancel individual subscriber; manage producer lifecycle independently |
| Creating a new sink in every controller call | No shared source to broadcast from | Manage the sink at an appropriate service/scope |
| Treating in-RAM replay as an event store | App restarts lose history | Use a DB/broker with retention and offsets |

## 15. Self-Check Exercises with Answers

**Question 1.** A unicast sink emitted 1, 2 before any subscriber existed. Does the first subscriber arriving afterward receive these two elements?

**Answer:** Yes, if using `unicast().onBackpressureBuffer()`. They are buffered for the single subscriber. A second subscriber is not accepted.

**Question 2.** A multicast sink emitted A and B to the first subscriber. A second subscriber subscribes after B. What does it receive?

**Answer:** It only receives new events after subscribing, such as C. Live-only multicast does not replay previously emitted A/B to late subscribers.

**Question 3.** `replay().limit(2)` emitted 10, 20, 30. What does a new subscriber receive before the next event arrives?

**Answer:** 20 and 30. The two most recent elements remaining in history are retained.

**Question 4.** Is a `replay().all()` sink suitable for a sensor stream running for months?

**Answer:** Usually not, because the entire history can be held in memory. Choose a count/time limit or a durable event store.

**Question 5.** `directBestEffort()` encounters a subscriber with no demand while another subscriber has demand. What happens?

**Answer:** The slow subscriber misses that event; the subscriber with demand still receives it. The slow subscriber is not terminated merely due to this drop.

**Question 6.** `directAllOrNothing()` has one subscriber without demand. Is the current event emitted to the fast subscriber?

**Answer:** No. The event is dropped for everyone because this mode requires all subscribers to have demand.

**Question 7.** `tryEmitNext` returns `FAIL_OVERFLOW`. Should you ignore the result because the sink is thread-safe?

**Answer:** No. Thread-safe does not mean every emission succeeds. Apply an overflow policy: bounded backoff, rejection, log/metrics, or routing to a bounded queue.

**Question 8.** How do `share()` and `replay(10)` differ?

**Answer:** `share()` shares live signals among active subscribers without replaying history. `replay(10)` retains up to the 10 most recent elements for late subscribers to receive.

**Question 9.** A WebSocket client cancels its subscription. Should you call `tryEmitComplete()` on the singleton sink?

**Answer:** Not automatically. Cancel only says that client is no longer receiving; other clients may still be using the sink. Complete only when the source's lifecycle truly ends.

**Question 10.** Full event recovery is required after an application restart. Is a replay sink enough?

**Answer:** No. A replay sink stores data in process memory. A broker/event log/database with retention and offset/checkpoint mechanisms is needed.

## 16. Solution Selection Checklist

Before implementing, answer in order:

1. **Subscriber count:** strictly one, or multiple independent subscribers?
2. **Late subscribers:** receive only new events, the N most recent elements, or full history?
3. **Source:** cold recreated per subscriber, or hot producer emitting independently?
4. **Slow subscribers:** buffer, fail, drop per subscriber, or drop for the whole group?
5. **Resource bounds:** maximum elements or duration for buffer/replay history?
6. **Producers:** single thread or multiple threads; are emissions serialized?
7. **Lifecycle:** who completes/errors/cancels the sink and when?
8. **Data durability:** is losing data on process restart acceptable?
9. **Correctness:** are exactly-once delivery, deduplication, ordering, or acks needed?
10. **Observability:** have subscriber count, backlog, overflow, emission failures, and consumption rate been measured?

| Need | Initial Choice |
| --- | --- |
| One consumer; producer may emit before subscriber | `Sinks.many().unicast().onBackpressureBuffer()` |
| Multiple consumers; live events only | `Sinks.many().multicast().onBackpressureBuffer()` |
| Multiple consumers; drop events for slow subscribers | `directBestEffort()` |
| Every subscriber must be ready to receive an event | `directAllOrNothing()` |
| New subscribers need the N most recent events | `Sinks.many().replay().limit(N)` |
| New subscribers only need the latest state | `Sinks.many().replay().limit(1)` |
| Share a cold publisher among active subscribers | `share()` or `publish()` |
| Subscribers must rendezvous before source runs | `publish()` + `connect()`/`autoConnect(n)` |
| Retain publisher history for later subscribers | `replay()` or `cache(...)` |
| Need durable replay across restarts | Message broker/event store, not just an in-RAM sink |

## 17. Key Takeaways and References

- **Unicast = one subscriber; Multicast = multiple subscribers receiving live events; Replay = multiple subscribers receiving retained history and new events.**
- **Cold/hot is a different axis:** cold typically reruns the source per subscription; a hot producer can emit independently of subscribers.
- `unicast().onBackpressureBuffer()` retains data before the first subscriber but does not support multiple subscribers.
- `multicast().onBackpressureBuffer()` regulates subscriber demand; direct modes can drop by policy.
- `replay().limit(n)` bounds history by element count; `replay().all()` risks RAM growth on infinite sources.
- Check `Sinks.EmitResult`; a thread-safe sink can still reject emissions due to overflow or concurrent emission.
- A replay sink is in-process memory and does not replace a durable event store/broker.

Official documentation:

1. [Project Reactor Reference — Sinks](https://projectreactor.io/docs/core/release/reference/coreFeatures/sinks.html): creating sinks, unicast/multicast/replay, emitting events, and thread safety.
2. [Project Reactor Reference — Hot Versus Cold](https://projectreactor.io/docs/core/release/reference/advancedFeatures/reactor-hotCold.html): source lifecycle per subscription.
3. [Project Reactor Reference — Broadcasting with ConnectableFlux](https://projectreactor.io/docs/core/release/reference/advancedFeatures/advanced-broadcast-multiple-subscribers-connectableflux.html): `publish`, `replay`, `connect`, `autoConnect`, `refCount`.
4. [Sinks API 3.8.6](https://javadoc.io/static/io.projectreactor/reactor-core/3.8.6/reactor/core/publisher/Sinks.html): builders and contracts.
5. [Sinks.UnicastSpec API](https://javadoc.io/static/io.projectreactor/reactor-core/3.8.6/reactor/core/publisher/Sinks.UnicastSpec.html): single subscriber, queue, and backpressure.
6. [Sinks.MulticastSpec API](https://javadoc.io/static/io.projectreactor/reactor-core/3.8.6/reactor/core/publisher/Sinks.MulticastSpec.html): buffer, autoCancel, directAllOrNothing, directBestEffort.
7. [Sinks.MulticastReplaySpec API](https://javadoc.io/static/io.projectreactor/reactor-core/3.8.6/reactor/core/publisher/Sinks.MulticastReplaySpec.html): all, latest, limit by count/time.
8. [Spring WebFlux Reference](https://docs.spring.io/spring-framework/reference/web/webflux.html): integrating publishers in Spring's reactive HTTP stack.
