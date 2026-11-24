# Distinguishing Cold Sources from Hot Sources in Project Reactor

## 1. Why Does the Distinction Matter?

In Spring WebFlux, `Mono<T>` and `Flux<T>` describe a sequence of reactive signals. However, when multiple Subscribers subscribe to the same Publisher, an important question arises: **does each Subscriber trigger a new data processing run, or do they all observe one running data source?**

Project Reactor calls these two common models **cold publisher** and **hot publisher**:

- A **cold** source starts work for each subscription. Each Subscriber typically gets an independent emission run; without a subscription, the work has not started.
- A **hot** source has a data-emission lifecycle that is more independent of individual Subscribers. A late Subscriber typically only receives signals emitted after the time they subscribe; some hot sources can store and replay history.

This is a difference in **when data is created/emitted and how the signal sequence is shared**. It does not mean cold = synchronous, hot = asynchronous, cold = single-threaded, or hot = multi-threaded. A cold Publisher can make asynchronous HTTP calls; a hot sink can be emitted to synchronously right on the calling thread.

After this lesson, you will be able to identify cold/hot sources, explain the effects of `just` and `defer`, convert a cold source to multicast using `publish`/`share`, choose replay/cache when historical data is needed, emit events with `Sinks.Many`, apply these in WebFlux, and test the behavior of early/late Subscribers.

## 2. Cold Publisher: Each Subscription Starts a New Run

A cold sequence produces fresh data for each Subscriber. When two Subscribers subscribe to the same cold source, each Subscriber has its own separate subscription to upstream. With a finite source, both typically see the entire sequence from the beginning.

Example:

~~~java
Flux<String> source = Flux.just("blue", "green", "orange")
        .map(String::toUpperCase);

source.subscribe(value -> System.out.println("S1: " + value));
source.subscribe(value -> System.out.println("S2: " + value));
~~~

Stdout:

~~~text
S1: BLUE
S1: GREEN
S1: ORANGE
S2: BLUE
S2: GREEN
S2: ORANGE
~~~

Each `subscribe` runs the cold pipeline again. This is very useful when the source represents an operation that must be executed per user: making an HTTP call, querying a reactive repository, reading a file, computing per request, or creating a new sequence.

### 2.1. Common Cold Sources

- `Flux.range(start, count)`: each subscription re-emits the range of numbers.
- `Flux.fromIterable(iterable)`: each subscription creates an iterator and traverses the source.
- `Mono.fromCallable(callable)` / `Flux.fromIterable` combined with `defer`: executes the value-producing part upon subscribe.
- `Mono.defer(supplier)` / `Flux.defer(supplier)`: invokes the supplier for each subscription to obtain a new Publisher.
- `WebClient` request pipeline: when constructed and returned as a Publisher without subscribing, the request is not sent yet; each subscription normally initiates a new request.

Do not assume that **every cold source always creates a deep copy of the data**. For example, `Flux.fromIterable(sharedList)` may iterate over the same List object across multiple subscriptions; if the List is modified concurrently, thread-safety issues still exist. Cold is about per-subscription sequence creation/emission, not a mechanism for cloning arbitrary Java objects.

### 2.2. Using defer When Values Need to Be Recomputed per Subscription

`Flux.just(value)` takes a value that Java has already evaluated at assembly time. If the inner expression is a method call, that method runs before `just` is created:

~~~java
Mono<String> captured = Mono.just(loadCurrentValue());
~~~

`loadCurrentValue()` runs immediately at assembly. Subsequent Subscribers receive that captured value.

If you want each subscription to invoke the operation again:

~~~java
Mono<String> fresh = Mono.defer(
        () -> Mono.just(loadCurrentValue())
);
~~~

Now `loadCurrentValue()` runs inside the supplier for each subscription. If the method can return `null`, use `Mono.justOrEmpty(loadCurrentValue())` inside `defer`; `Mono.just(null)` is invalid.

**A Reactor nuance:** Reactor documentation classifies `just` among the few operators with hot characteristics because it captures the value at assembly and replays that captured value to later Subscribers. That does not mean `just` calls `onNext` before a subscription exists; signals are still delivered during subscription. The key point to remember is that the value is **not recomputed** for each Subscriber. `defer` is the way to delay source creation so that this operation becomes per-subscription.

### 2.3. HTTP and Repository Examples

In a service:

~~~java
Mono<User> findUser(String id) {
    return webClient.get()
            .uri("/users/{id}", id)
            .retrieve()
            .bodyToMono(User.class);
}
~~~

This is a lazy pipeline: when the caller subscribes, WebClient executes the request. If the same Mono is subscribed to twice, there will normally be two requests. If you want multiple downstreams to share a single in-flight request, you must explicitly use a sharing or caching mechanism; do not assume Mono automatically memoizes results.

With a blocking API that returns an object immediately when called:

~~~java
// Blocking operation occurs right at assembly:
Mono<User> wrong = Mono.just(legacyDao.findUser(id));

// Defer operation to subscription and move blocking work off the event-loop:
Mono<User> adapted = Mono.fromCallable(() -> legacyDao.findUser(id))
        .subscribeOn(Schedulers.boundedElastic());
~~~

The snippet above illustrates a blocking source; in real systems, prefer reactive drivers/clients. `fromCallable` defers and executes the work per subscription, while `subscribeOn` selects an appropriate scheduler. Cold does not automatically mean non-blocking.

## 3. Hot Publisher: A Source with Its Own Emission Pace

A hot sequence does not restart its entire history for each Subscriber. The source can continue emitting as Subscribers arrive or leave; new Subscribers typically only receive data emitted after they subscribe.

Typical examples:

- Events from a running device, sensor, or message broker.
- Continuously updated price tickers or exchange rates.
- In-application notifications broadcast to WebSocket/SSE sessions.
- A `Sinks.Many` receiving events actively pushed by the application.
- A cold source converted to hot via `share()` or `replay()` after subscription begins.

~~~text
Time ────────────────────────────────────────────────►

Source emits:     E1       E2       E3       E4
Subscriber A:     ├────────────── receives E1,E2,E3,E4
Subscriber B:                       ├────── receives E3,E4
Subscriber C:                                  ├── receives E4

B and C do not automatically receive E1,E2 if the source does not replay history.
~~~

A hot publisher can run when there are no Subscribers, though not every type of hot source retains data during periods with no listeners. A multicast sink typically forwards only new elements to current Subscribers; a replay sink stores history according to its configuration.

### 3.1. Hot Does Not Mean Multi-Threaded

`Sinks.Many` can be called synchronously:

~~~java
sink.tryEmitNext("event");
~~~

The event is delivered to listening Subscribers right on the calling path, if demand/overflow conditions allow. Another hot source might be emitted from an I/O callback or a scheduler. Hotness/coldness and thread selection are two independent axes.

### 3.2. Late Subscribers and History

With a non-replaying hot multicast source:

- A Subscriber that subscribed before E1 was emitted can receive E1.
- A Subscriber that subscribes after E1 typically only receives E2 onward.
- If the source has already completed before a Subscriber arrives, the new Subscriber typically receives the terminal signal per the source's contract; it does not automatically receive already-lost data.

If the business logic requires new Subscribers to see history, choose replay/cache or persist events durably. Do not treat a regular hot stream as a replayable event log.

## 4. Comparing Cold and Hot

| Criterion | Cold | Hot |
| --- | --- | --- |
| When work starts | Upon subscription | Can be independent of subscription |
| Second Subscriber | Typically triggers a new run | Typically joins the running source |
| History before subscribe | Cold source replays sequence from the start | Typically does not receive history unless replayed |
| Typical sources | HTTP requests, reactive queries, range, iterable, defer | Multicast sink, event bus, shared live feed |
| Upstream resources | Can multiply per Subscriber | Can share a single upstream source |
| Cancelling one Subscriber | Typically cancels that separate upstream run if unshared | Typically just leaves the group; source may keep serving other Subscribers |
| Design question | Does each request need to run again? | Who owns the source, who receives events, and is there replay? |

This table describes general tendencies. Operators such as `share`, `cache`, `replay`, `publish`, and the underlying hot/cold source can alter behavior; you must inspect operator placement across the entire pipeline.

## 5. Converting Cold to Hot: share and cache

Reactor can turn a cold source into a source shared among multiple Subscribers. Two common options are `share()` and `cache()`; they do not have the same semantics.

### 5.1. share: Multicast New Data to the Current Group of Subscribers

~~~java
Flux<Long> shared = Flux.interval(Duration.ofMillis(500))
        .share();
~~~

`share()` starts connecting upstream when the first Subscriber arrives. Participating Subscribers share the same emission run. A late Subscriber typically only receives ticks emitted after they subscribe, not all prior ticks. When the Subscriber group leaves, `share` can disconnect upstream according to ref-count semantics; reset/reconnect behaviors depend on the version and source state.

Suitable when multiple clients watch a live feed and running multiple identical upstream sources would be wasteful. Do not use it if each client needs an independent result, or must be guaranteed to receive all past events.

### 5.2. cache: Store and Replay Signals to Later Subscribers

~~~java
Mono<Config> cachedConfig = loadConfig()
        .cache();
~~~

`cache()` stores signals from upstream so later Subscribers can receive the cached values and terminal signal. With `Flux`, `cache` can retain many elements; look at the overloads that limit count and TTL to avoid retaining data indefinitely. For sensitive data or data that must always be fresh, an unbounded cache without expiration can cause logic bugs.

`cache` is useful for a shared result, such as loading configuration or metadata that only needs to be computed once during the cache's lifetime. It does not replace a dedicated cache with invalidation, memory bounds, key partitioning, and application-level expiration policies.

### 5.3. Quick Selection

| Need | Choice |
| --- | --- |
| Multiple Subscribers receive new events from the same source | `share()` |
| Late Subscribers receive stored data again | `cache()` or `replay()` |
| Each Subscriber reruns the entire source | Keep cold; use `defer` if fresh creation is needed |
| Share only after N Subscribers have subscribed | `publish().autoConnect(N)` or `refCount(N)` |
| Need manual control over when to start | `publish()` / `replay()` combined with `connect()` |

## 6. ConnectableFlux: Controlling When Broadcast Starts

`publish()` and `replay()` can return a `ConnectableFlux<T>`. Unlike a regular Flux, ConnectableFlux lets you attach Subscribers first and then explicitly call `connect()` to start upstream.

~~~java
ConnectableFlux<Integer> shared = Flux.range(1, 3).publish();

shared.subscribe(value -> System.out.println("A:" + value));
shared.subscribe(value -> System.out.println("B:" + value));

shared.connect();
~~~

Stdout:

~~~text
A:1
B:1
A:2
B:2
A:3
B:3
~~~

With a synchronous source and two Subscribers registered before `connect()`, both receive the same emission run. `publish` coordinates demand across multiple Subscribers; if one Subscriber has no demand, it can pause the source to ensure backpressure for the group.

### 6.1. autoConnect and refCount

- `publish().autoConnect(n)` automatically calls connect once `n` Subscribers arrive. After connecting, it does not use the current Subscriber count as an auto-disconnect condition like refCount.
- `publish().refCount(n)` connects once `n` Subscribers arrive and manages cancelling upstream when the Subscriber count drops below the threshold per contract.
- `share()` is a concise choice for sharing that starts with the first Subscriber; check the specific semantics of the Reactor version in use.

If you need a group of two Subscribers to start the source together, `autoConnect(2)` or `refCount(2)` is useful. With a very fast synchronous source, subscribing a second Subscriber after the first Subscriber has already triggered the source may be too late; pick a threshold or connect manually to avoid timing races.

### 6.2. replay: ConnectableFlux with History

`replay()` retains seen elements and replays them to late Subscribers according to the configured limit. For example, `replay(2)` keeps at most the last two elements:

~~~java
ConnectableFlux<Integer> replayed = Flux.range(1, 5).replay(2);

replayed.connect(); // synchronous source finishes emitting, history keeps 4 and 5
replayed.subscribe(value -> System.out.println("late:" + value));
~~~

Stdout:

~~~text
late:4
late:5
~~~

In a live application, you can use an element-count or time limit so new Subscribers get a recent snapshot. Replay consumes memory; unbounded replay on an infinite source will accumulate data forever. If you need long-term event history and recovery across restarts, use a durable broker/log/database rather than relying solely on the Publisher's RAM.

## 7. Sinks.Many: Creating Application-Driven Hot Sources

`Sinks.Many<T>` lets an application actively push data into a source and expose a `Flux<T>` view to Subscribers. Three common families:

| Sink | Behavior for New Subscribers | Number of Subscribers |
| --- | --- | --- |
| `Sinks.many().multicast()` | Emits only new elements from subscription time onward; no history replay | Multiple |
| `Sinks.many().unicast()` | Allows only one Subscriber; can buffer elements before the first Subscriber arrives | One |
| `Sinks.many().replay()` | Replays history per configured limit then continues live | Multiple |

Example of creating a multicast sink:

~~~java
Sinks.Many<Event> sink = Sinks.many()
        .multicast()
        .onBackpressureBuffer();

Flux<Event> events = sink.asFlux();
~~~

The application can hold `sink` in a singleton service to receive events from multiple places and expose `events` to clients. Because the sink is a shared resource, you must define policies for backpressure, buffering, emit failures, and terminal lifecycle.

### 7.1. Checking Emit Results

~~~java
Sinks.EmitResult result = sink.tryEmitNext(event);

if (result.isFailure()) {
    // Handle failure according to result type and application policy.
}
~~~

Failures can include `FAIL_NON_SERIALIZED` when multiple producers contend to emit concurrently, `FAIL_OVERFLOW` when buffer capacity is exceeded, `FAIL_TERMINATED` when the sink has already completed/errored, or `FAIL_ZERO_SUBSCRIBER` in configurations that reject emissions when there are no Subscribers. Specific results depend on the sink type.

Do not ignore `EmitResult` and assume the event was broadcast. With multiple producers, use a safe sink and handle contention with bounded retries or serialize through a single-writer queue. `Sinks.unsafe()` is only suitable when the caller guarantees serialized emissions.

### 7.2. Multicast and Replay Sinks

~~~java
Sinks.Many<Event> live = Sinks.many()
        .multicast()
        .onBackpressureBuffer();

Sinks.Many<Event> history = Sinks.many()
        .replay()
        .limit(100);
~~~

`live` forwards only new events to current Subscribers; `history` retains up to 100 events to replay to late Subscribers. Choose the sink based on business requirements: live telemetry may not need history; dashboards may need the latest snapshot; transactional systems need durable logs/acks rather than an in-RAM replay buffer.

## 8. Spring WebFlux Applications: Per-Request or Broadcast?

### 8.1. Endpoint Returning Data per Request

A controller can return a cold Publisher:

~~~java
@GetMapping("/users/{id}")
Mono<User> getUser(@PathVariable String id) {
    return userRepository.findById(id);
}
~~~

This is a snippet in a Spring WebFlux application with a reactive repository. Each request is subscribed to by WebFlux; the reactive repository typically executes a query for that subscription. If the same Mono is subscribed to again, do not assume the result is cached.

### 8.2. Server-Sent Events Endpoint from a Shared Event Source

Suppose a service emits application-wide events:

~~~java
@Service
class EventHub {
    private final Sinks.Many<ServerEvent> sink =
            Sinks.many().multicast().onBackpressureBuffer();

    Flux<ServerEvent> stream() {
        return sink.asFlux();
    }

    void publish(ServerEvent event) {
        Sinks.EmitResult result = sink.tryEmitNext(event);
        if (result.isFailure()) {
            throw new IllegalStateException("Event publish failed: " + result);
        }
    }
}
~~~

Controller:

~~~java
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<ServerEvent> events() {
    return eventHub.stream();
}
~~~

These are two illustrative snippets requiring the Spring WebFlux dependency and application types `ServerEvent` and `eventHub`. Each SSE client creates a Subscriber to the same multicast sink. A late-connecting client only receives new events from the moment it subscribes; if a client disconnects, its Subscriber leaves the stream, while the sink can continue serving other clients.

If a client that loses connection needs to reconnect and receive missed events, you need event IDs, bounded replay, or a broker with offsets/acks. An in-memory multicast sink does not guarantee durable delivery.

### 8.3. Do Not Manually Subscribe in a Controller

Return `Mono`/`Flux` so WebFlux manages subscription, cancellation, and backpressure. Do not call `subscribe()` manually inside a controller just to “start the stream”, as that detaches the lifecycle from the HTTP request and makes error handling, connection cancellation, and resource cleanup difficult.

## 9. Standalone Java 17+ Example: Cold Replay vs. Non-Replaying Hot Multicast

The example below uses Reactor Core and synchronous sources so stdout is deterministic. The cold source uses `Flux.defer` to record each subscription creation. The hot source uses a multicast sink: Subscriber A subscribes before the first event; B subscribes after the first event and therefore only receives the second event.

Project structure:

~~~text
cold-hot-demo/
├── build.gradle
└── src/main/java/ColdHotDemo.java
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.8'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'ColdHotDemo'
}
~~~

`src/main/java/ColdHotDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;

public class ColdHotDemo {

    private static void emit(Sinks.Many<String> sink, String value) {
        Sinks.EmitResult result = sink.tryEmitNext(value);
        if (result.isFailure()) {
            throw new IllegalStateException("Emit failed: " + result);
        }
    }

    private static void complete(Sinks.Many<String> sink) {
        Sinks.EmitResult result = sink.tryEmitComplete();
        if (result.isFailure()) {
            throw new IllegalStateException("Complete failed: " + result);
        }
    }

    public static void main(String[] args) {
        AtomicInteger runs = new AtomicInteger();

        Flux<String> cold = Flux.defer(() -> {
            int run = runs.incrementAndGet();
            System.out.println("cold run #" + run);
            return Flux.just("A", "B");
        });

        System.out.println("[cold]");
        cold.subscribe(value -> System.out.println("S1:" + value));
        cold.subscribe(value -> System.out.println("S2:" + value));

        System.out.println("[hot multicast]");
        Sinks.Many<String> sink =
                Sinks.many().multicast().onBackpressureBuffer();
        Flux<String> hot = sink.asFlux();

        hot.subscribe(value -> System.out.println("A:" + value));
        emit(sink, "one");

        hot.subscribe(value -> System.out.println("B:" + value));
        emit(sink, "two");
        complete(sink);

        System.out.println("[assembly capture]");
        AtomicInteger version = new AtomicInteger(1);
        Mono<Integer> captured = Mono.just(version.get());
        Mono<Integer> deferred =
                Mono.defer(() -> Mono.just(version.get()));

        version.set(2);
        captured.subscribe(value -> System.out.println("just:" + value));
        deferred.subscribe(value -> System.out.println("defer:" + value));
    }
}
~~~

From the directory containing `build.gradle`, run with an installed Gradle:

~~~bash
gradle -q run
~~~

If the project has a wrapper, use `./gradlew -q run` on Linux/macOS or `gradlew.bat -q run` on Windows. Exact stdout of this synchronous program:

~~~text
[cold]
cold run #1
S1:A
S1:B
cold run #2
S2:A
S2:B
[hot multicast]
A:one
A:two
B:two
[assembly capture]
just:1
defer:2
~~~

Analysis:

1. The first `cold.subscribe` invokes the supplier for the first time, emitting A and B to S1.
2. The second subscription invokes the supplier again, creating a new run for S2.
3. A subscribes to the sink before the `one` event is emitted, so it receives that event.
4. B subscribes after `one`, so the multicast sink does not replay the old event to B. Both A and B receive the `two` event.
5. `Mono.just(version.get())` captures 1 at assembly. `Mono.defer(...)` reads version on subscribe, so it emits 2 after the variable has changed.

The example uses no scheduler or asynchronous I/O, so output ordering is deterministic. With a real live source, events can be emitted concurrently while clients subscribe; clear subscription boundaries and replay policies must be defined.

## 10. Testing with StepVerifier

In a project with JUnit 5, add `reactor-test` matching the Reactor version to test scope:

~~~groovy
dependencies {
    testImplementation 'io.projectreactor:reactor-test:3.8.8'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

File `src/test/java/ColdHotTest.java`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;
import reactor.test.StepVerifier;

class ColdHotTest {

    @Test
    void coldSourceRunsAgainForEachSubscription() {
        AtomicInteger runs = new AtomicInteger();

        Flux<Integer> cold = Flux.defer(() ->
                Flux.just(runs.incrementAndGet()));

        StepVerifier.create(cold)
                .expectNext(1)
                .verifyComplete();

        StepVerifier.create(cold)
                .expectNext(2)
                .verifyComplete();

        assertEquals(2, runs.get());
    }

    @Test
    void replaySinkReplaysHistoryToLateSubscriber() {
        Sinks.Many<Integer> sink = Sinks.many().replay().all();

        sink.tryEmitNext(10).orThrow();
        sink.tryEmitNext(20).orThrow();
        sink.tryEmitComplete().orThrow();

        StepVerifier.create(sink.asFlux())
                .expectNext(10, 20)
                .verifyComplete();

        StepVerifier.create(sink.asFlux())
                .expectNext(10, 20)
                .verifyComplete();
    }

    @Test
    void multicastSinkDoesNotReplayEarlierEvents() {
        Sinks.Many<Integer> sink =
                Sinks.many().multicast().onBackpressureBuffer();
        Flux<Integer> hot = sink.asFlux();

        StepVerifier.create(hot)
                .then(() -> sink.tryEmitNext(1).orThrow())
                .expectNext(1)
                .thenCancel()
                .verify();

        StepVerifier.create(hot)
                .then(() -> sink.tryEmitNext(2).orThrow())
                .expectNext(2)
                .then(() -> sink.tryEmitComplete().orThrow())
                .verifyComplete();
    }
}
~~~

These tests verify three different contracts: a cold source creates a new run for each subscription; a replay sink stores history and replays it; a multicast sink only forwards new events while the Subscriber is subscribed. The sink tests use `tryEmit...` and check results with `orThrow`, avoiding silently ignoring emit failures.

When testing sources with schedulers or time, use `StepVerifier.withVirtualTime` when the operators support a virtual scheduler; do not rely on `Thread.sleep`. For sinks with backpressure, add tests for subscriber demand of 0 and overflow policy.

## 11. Choosing a Model by Business Requirement

| Question | Recommended Choice |
| --- | --- |
| Must each request execute a separate query/HTTP call? | Cold Publisher; use `defer` if source creation must run at subscribe time |
| Do multiple clients watch one live feed? | Hot multicast via `share` or `Sinks.Many.multicast` |
| Must late clients receive the most recent few events? | `replay(limit)`, `cache(history)`, or a bounded replay sink |
| Must all Subscribers be ready before the source starts? | `ConnectableFlux.publish()` and `connect()` after subscribing, or `autoConnect(n)` |
| Need auto-connect at enough Subscribers and disconnect when the group leaves? | `refCount(n)` |
| Need a single shared result replayed later? | `Mono.cache()` or a cache with TTL when appropriate |
| Must events survive restarts/network loss? | Durable broker/event log/database; an in-RAM hot sink is insufficient |
| Multiple producers pushing to the same sink? | Safe sink, handle `EmitResult` and serialize/retry with bounds |
| Must each Subscriber have its own state? | Cold source/`defer`; avoid capturing mutable variables outside assembly |

Deciding between cold and hot requires weighing both cost and semantics: cold can multiply requests or work by the number of Subscribers; hot can save upstream work but couples Subscribers to the same emission pace and data loss/replay policy.

## 12. Common Pitfalls

1. **Assuming every Flux is cold:** `Mono.just`/`Flux.just` capture values at assembly in a way Reactor describes as one of the special hot operators. If you need to read fresh values per subscription, use `defer`.
2. **Assuming hot always replays history:** multicast sources typically do not replay. Use replay/cache or an event store when history is needed.
3. **Assuming cold always copies objects:** `fromIterable(sharedList)` can still share a collection. Cold does not guarantee deep copies.
4. **Calling `share()` while expecting each Subscriber to call upstream separately:** share intentionally shares a single upstream run across a group of Subscribers.
5. **Using unbounded `cache()` on an infinite source:** history retention memory grows continuously. Pick bounded history/TTL or a bounded sink.
6. **Subscribing a Subscriber after a synchronous source has finished running:** a late Subscriber cannot receive data if the source does not replay. Subscribe enough Subscribers before `connect` or use replay.
7. **Assuming cancelling one Subscriber always cancels a hot source:** if other Subscribers remain, a multicast source can keep running. With `refCount`, check the threshold and disconnect behavior.
8. **Ignoring `tryEmitNext` failures:** an event may not be delivered due to overflow, a terminated sink, or producer contention.
9. **Using a sink in a singleton with an unbounded buffer:** a source faster than consumers can grow backlog or overflow.
10. **Using an in-memory hot stream as a durable event log:** process restarts can lose history. A broker or persistent storage is needed.
11. **Calling `subscribe()` manually in a controller/service just to start a stream:** detaches lifecycle from the caller, making cancellation and error handling difficult. Return the Publisher for the framework/caller to manage.
12. **Equating cold/hot with synchronous/asynchronous:** inspect subscription timing, schedulers, data sources, and broadcast policies separately.

## 13. Self-Check

1. What will two Subscribers subscribing to the same `Flux.defer(() -> Flux.range(1, 3))` receive? **Each Subscriber gets an independent run of 1, 2, 3.**
2. When does `Mono.just(loadConfig())` invoke `loadConfig`? **When Java assembles the expression, before subscription.**
3. How do you invoke `loadConfig` on every subscribe? **`Mono.defer(() -> Mono.just(loadConfig()))` or `fromCallable` if the operation can throw.**
4. Subscriber B subscribes after a multicast sink has already emitted event E1; does B receive E1? **No, unless the source replays.**
5. At most how many historical elements does `replay(2)` keep? **The two most recent elements.**
6. How does `publish()` differ from `share()`? **publish returns a ConnectableFlux allowing manual connect; share auto-connects based on Subscribers and shares the emission run.**
7. Is `cache()` unconditionally suitable for an infinite Flux? **No, history/TTL must be bounded and memory considered.**
8. Is a cold source guaranteed to be thread-safe? **No; it can capture shared mutable objects or access non-thread-safe resources.**
9. Must a hot source run on a background thread? **No; a hot source can emit synchronously or asynchronously.**
10. An SSE endpoint must resend missed events when a client reconnects. Is a simple multicast sink enough? **No; replay/event IDs or an appropriate durable storage source is needed.**

**Key takeaway:** Cold creates an emission run per subscription; hot shares a single emission pace and late Subscribers typically see only new data. `defer` controls source creation timing, `share` multicasts live data, `cache`/`replay` store history, and `Sinks.Many` lets the application actively emit events. Choose based on whether each client needs dedicated data, live data, or replayable history.

## References

- [Project Reactor Reference Guide — Hot Versus Cold](https://projectreactor.io/docs/core/release/reference/advancedFeatures/reactor-hotCold.html).
- [Project Reactor Reference Guide — Broadcasting to Multiple Subscribers with ConnectableFlux](https://projectreactor.io/docs/core/release/reference/advancedFeatures/advanced-broadcast-multiple-subscribers-connectableflux.html).
- [Project Reactor Reference Guide — Sinks](https://projectreactor.io/docs/core/release/reference/coreFeatures/sinks.html).
- [Project Reactor Flux Javadoc — publish, replay, share, cache, refCount](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- [Spring Framework Reference — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html).
