# cache, replay, and Data Retention Bounds

In **Spring WebFlux** and **Project Reactor**, a reactive data source can be *cold* or *hot*. When multiple subscribers need the same data stream, an application may want to **share a single execution**, **replay already-emitted data to late subscribers**, or **retain only a portion of history for a limited time**.

Three concepts often appear together yet are not synonymous:

- **`cache`** turns a publisher into a shared source that retains emitted signals so later subscribers can receive them. Overloads allow bounding element count and/or retention time.
- **`replay`** creates a stream capable of replaying history to late subscribers; in Reactor, `ConnectableFlux.replay(...)` lets you control when the source connects and bound history.
- **Data retention bounds** determine how many elements are kept, for how long, and at what memory cost. Bounding element count alone does not necessarily bound exact byte size.

This lesson explains cold/hot, sharing and replaying, Reactor operators, using `Sinks.Many`, and choosing safe retention policies in real applications.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish cold and hot sources; explain what a late subscriber receives from each.
2. Distinguish `share`, `publish`, `replay`, and `cache` in terms of subscription sharing, retained history, and how the source starts.
3. Use `Flux.cache(history)`, `cache(ttl)`, or combined overloads to control history.
4. Use `ConnectableFlux.replay(history)`, `connect`, `autoConnect`, and `refCount` with the right lifecycle.
5. Use `Sinks.many().replay().limit(n)` when you need to actively emit events and retain a number of recent elements.
6. Understand that cache retains terminal signals such as completion/errors, and know the impact of caching errors or empty sources.
7. Evaluate memory retention, TTL, payload size, emission rate, slow subscribers, cancellation, and backpressure.
8. Test first-subscriber and late-subscriber behavior using `StepVerifier`.

## 2. Cold and Hot Sources

### 2.1. Cold Publisher: Each Subscriber Gets Its Own Execution

A cold publisher typically starts work when a subscriber arrives. Each new subscribe can receive a fresh sequence from the beginning:

~~~java
Flux<Integer> cold = Flux.defer(() -> Flux.just(1, 2, 3));
~~~

Two independent subscribers typically receive:

~~~text
Subscriber A: 1 -> 2 -> 3 -> complete
Subscriber B: 1 -> 2 -> 3 -> complete
~~~

Familiar examples are `Flux.range`, `Flux.fromIterable`, `Mono.fromCallable`, and `WebClient` requests created per subscribe. `defer` makes source creation at subscribe time explicit. However, cold **does not mean** every source creates a completely new resource: exact behavior is still defined by the underlying publisher.

If a cold publisher represents an HTTP GET, two subscriptions can make two HTTP requests. If it represents `Mono.fromCallable(() -> readFile())`, the file can be read twice. This may be right, but if multiple subscribers need the same result, the cost is duplicated.

### 2.2. Hot Publisher: A Source Emitting Independently of Individual Subscribers

A hot publisher can emit events over time or driven by system activity, even when no subscriber is currently present. Late subscribers can **miss elements emitted before they subscribed**.

~~~text
Hot source:       A ---- B ---- C ---- D ---- E
Subscriber 1:          B ---- C ---- D ---- E
Subscriber 2:                         D ---- E
~~~

Typical examples are device event streams, market prices, connection states, a shared message source, or a `Sinks.Many` actively emitted by the application.

**Do not infer the source type merely from the name `Flux` or `Mono`.** Those two types describe element cardinality, not cold/hot. A `Flux` can be cold, hot, or become a shared/replaying source after applying appropriate operators.

### 2.3. Comparison Table

| Property | Cold | Hot |
| --- | --- | --- |
| When does the source start? | Usually when each subscriber subscribes | Can start independently of subscribers |
| New subscription | Usually creates a separate execution | Can join an already-running stream |
| Data emitted before subscribe | Usually new subscribers receive from the start | May be missed if there is no replay |
| Sharing upstream work | Not by default | Can share the same emission run |
| Examples | `Flux.range`, `Mono.fromCallable` | `Sinks.Many`, shared event publishers |

## 3. Why Use share, cache, or replay?

Suppose multiple requests all need application configuration or reference data:

~~~text
Request A ----\
Request B -----+----> Load data from service/database
Request C ----/
~~~

If each request subscribes to a cold publisher, the system may call the source three times. This can cause:

- Repeated identical I/O and higher database/API load.
- Inconsistent results if the source changes between calls.
- Higher latency because each subscriber must wait for a separate load.

Sharing the source can turn the flow into:

~~~text
                   +--> Subscriber A
One upstream ------+--> Subscriber B
                   +--> Subscriber C
~~~

However, sharing one subscription **does not mean** every subscriber receives the same history. A late-subscribing subscriber may only receive elements from the time it joins; receiving past data requires replay/cache.

Questions to answer up front:

1. Should the source run exactly once for multiple subscribers?
2. Do late subscribers need **full history**, **the last N elements**, or **only new data**?
3. When no subscribers remain, should the source keep running or be cancelled?
4. When the source errors or completes, should subsequent subscribers receive the old signal or trigger a new execution?
5. How much data can be held in RAM and for how long?

No single operator fits every case.

## 4. `share` and `publish`: Sharing a Stream Without Replaying History

### 4.1. `publish()` Creates a ConnectableFlux

`publish()` turns a `Flux` into a `ConnectableFlux`. Subscribers can register first, and then the application calls `connect()` to start upstream:

~~~java
ConnectableFlux<Integer> shared = Flux.range(1, 3).publish();

shared.subscribe(value -> System.out.println("A=" + value));
shared.subscribe(value -> System.out.println("B=" + value));

shared.connect();
~~~

Both subscribers registered before connecting, so they receive the same values. `publish()` **does not retain history to replay to late subscribers**; it multicasts signals while the stream is active.

`ConnectableFlux` is useful when the application wants precise control over when the source starts. If you subscribe again after the source has emitted some values, the new subscriber does not automatically receive those earlier values.

### 4.2. `share()` for Overlapping Subscribers

`share()` is a convenient way to share a source among concurrent subscribers, equivalent to the `publish().refCount(1)` model in current Reactor versions:

~~~java
Flux<Event> events = source.share();
~~~

It is useful when multiple subscribers watch a running source together. `share()` **is not a history cache**; late subscribers are not guaranteed to receive elements emitted before they joined.

Reconnect lifecycle after subscribers cancel or the source ends can depend on state and the specific version/operator. Do not treat `share()` as a completed-result storage contract; if result replay is needed, pick `cache` or `replay` with explicit bounds.

### 4.3. `refCount` and `autoConnect`

Two common connection-control methods:

~~~java
Flux<Event> waitForTwo = source.publish().refCount(2);
Flux<Event> startAfterOne = source.publish().autoConnect(1);
~~~

- `refCount(2)` connects upstream only when two subscribers exist. When subscriber count drops below the threshold, it can disconnect per ref-count policy.
- `autoConnect(1)` connects after the first subscriber; after connecting, it does not auto-disconnect upstream just because subscribers drop to 0.
- No-arg `refCount()` typically uses a threshold of one subscriber.
- `share()` is an automatic sharing form for the threshold-one case.

**Choose by lifecycle:** a source that should stop when no listeners remain usually fits ref-count; a source that should keep running after the first subscriber can use auto-connect. Read the overload's contract and test reconnect/terminal behavior for the exact Reactor version in use.

## 5. `replay`: Replaying History to Late Subscribers

`replay` creates a `ConnectableFlux` capable of retaining a portion of history so late-subscribing subscribers can receive it:

~~~java
ConnectableFlux<Integer> replayLastTwo =
    Flux.range(1, 5).replay(2);
~~~

If the first subscriber receives 1, 2, 3, 4, 5, a later subscriber can receive the last two elements, 4 and 5 (after the source has finished emitting). Common overloads:

| Creation Method | History Policy |
| --- | --- |
| `source.replay()` | Replays all retained history |
| `source.replay(n)` | Retains at most the n most recent elements |
| `source.replay(ttl)` | Retains elements for a TTL time window |
| `source.replay(n, ttl)` | Combines count and time limits when the corresponding overload is available |

`replay` returns a `ConnectableFlux`; the source starts only when connected via `connect()`, or via `autoConnect`/`refCount`:

~~~java
Flux<Integer> lateSubscribers = Flux.range(1, 5)
    .replay(2)
    .autoConnect(1);
~~~

This creates a replay source that auto-connects when the first subscriber arrives. A late subscriber can receive the portion of history remaining in the buffer.

**Bounded replay is not durable storage.** If the process restarts, in-memory data disappears. If the source emits fast and payloads are large, even replaying a short time window can consume a lot of RAM.

## 6. `cache`: Sharing Execution and Retaining Emitted Signals

### 6.1. `Flux.cache()`

`cache()` turns a cold Flux into a shared and replaying source. The first subscriber triggers upstream; subsequent subscribers receive retained elements and the terminal signal:

~~~java
Flux<String> cached = remoteService.loadAll().cache();
~~~

In its unbounded form, `Flux.cache()` can retain the entire history. For small finite sources, that can be convenient. For long or never-ending sources, **memory can grow continuously**.

### 6.2. Bounding by Element Count

~~~java
Flux<Event> lastHundred = source.cache(100);
~~~

`cache(100)` retains at most the 100 most recent elements for late subscribers. The first subscriber still receives the live stream per the source's contract; the history limit governs what is kept for replay.

For a never-ending Flux, bounding history by element count is especially important. However, 100 elements could be 100 small objects or 100 very large payloads; count is not an exact byte limit.

### 6.3. Bounding by Time (TTL)

~~~java
Flux<Event> recent = source.cache(
    java.time.Duration.ofMinutes(2)
);
~~~

TTL bounds the retention age of signals. A combined history-and-TTL overload lets you set both boundaries:

~~~java
Flux<Event> bounded = source.cache(
    500, java.time.Duration.ofMinutes(2)
);
~~~

Here history is capped at 500 elements and a two-minute TTL. Reactor APIs provide corresponding TTL overloads for `Flux`/`Mono`; check the Javadoc for your project's exact dependency version when selecting a specific signature.

**TTL does not replace an element-count limit.** If a source emits hundreds of thousands of events per second, two minutes of history can still be huge. Combine TTL with a history limit when a more predictable memory budget is needed.

### 6.4. `Mono.cache()`

With `Mono`, cache typically stores a single result or terminal signal:

~~~java
Mono<Config> cachedConfig = configService.load().cache();
~~~

Subscribers sharing this instance can share a single execution and receive the cached result. `Mono.cache()` can cache all of:

- A successfully emitted value.
- An empty completion (`Mono.empty()`).
- An error (`Mono.error(...)`).

Therefore, if the first config load fails and the error is cached, later subscribers may receive that same error instead of automatically calling the source again. A TTL or signal-type caching policy may be needed to avoid holding errors too long.

### 6.5. How Does `cache` Differ from `replay`?

| Criterion | `cache` | `replay` |
| --- | --- | --- |
| Typical API | `Flux.cache(...)` / `Mono.cache(...)` | `ConnectableFlux.replay(...)` |
| Starting upstream | Auto-triggers on the first subscriber | Explicitly call `connect` or use `autoConnect`/`refCount` |
| Late subscribers | Receive cached history per limits | Receive history remaining in the replay buffer |
| Connection control | Simple, self-managed | More explicit via ConnectableFlux |
| History bounds | History and/or TTL via overloads | History and/or TTL via overloads |
| Suitable use case | Sharing loaded results/streams | Lifecycle-controlled multicast and replay |

For the common need of “load once and share the result across multiple subscribers”, `cache` is usually simpler. For long-lived event streams needing control over connect/disconnect timing, `replay` or `publish` may be more appropriate.

## 7. `Sinks.Many`: Actively Emitting and Choosing a Replay Policy

`Sinks` is the API for an application to actively emit signals into Reactor. It is useful when bridging imperative callbacks, event producers, or internal components into a `Flux`.

Example of replay retaining the last three elements:

~~~java
Sinks.Many<Event> sink = Sinks.many()
    .replay()
    .limit(3);

Flux<Event> events = sink.asFlux();
~~~

- `sink.tryEmitNext(event)` sends an element.
- `sink.tryEmitComplete()` sends a completion signal.
- `sink.tryEmitError(error)` sends an error.
- `sink.asFlux()` provides a publisher for subscribers to observe.

An unbounded replay sink can retain all history; `replay().limit(3)` keeps only the three most recent elements. When using `tryEmit...`, check `EmitResult`; do not ignore emission failures such as overflow, an already-terminated sink, or unserialized concurrent producers.

Sink variants have different meanings:

| Sink | Overview Behavior |
| --- | --- |
| `many().unicast()` | Single subscriber, with configurable queuing for waiting data |
| `many().multicast()` | Shares signals to current subscribers; backpressure policy depends on variant |
| `many().replay().all()` | Replays entire history; consider RAM usage |
| `many().replay().limit(n)` | Replays the n most recent elements |

**Do not confuse a replay sink with a durable message broker.** A sink lives in-process and provides no persistence, replication, or consumer offsets across restarts.

## 8. Runnable Java 17 Example: cold, cache, and replay

The example below illustrates three behaviors with deterministic output:

1. The cold source is subscribed to twice, so the factory runs twice.
2. Cache subscribes upstream only once and the later subscriber receives the last two elements.
3. The replay buffer keeps the last two elements for the late subscriber.

Create file `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.6.8'
    testImplementation 'io.projectreactor:reactor-test:3.6.8'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.3'
}

application {
    mainClass = 'CacheReplayDemo'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Create file `src/main/java/CacheReplayDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.ConnectableFlux;
import reactor.core.publisher.Flux;

public class CacheReplayDemo {
    public static void main(String[] args) {
        AtomicInteger subscriptions = new AtomicInteger();

        Flux<Integer> cold = Flux.defer(() -> {
            int run = subscriptions.incrementAndGet();
            System.out.println("cold source subscription #" + run);
            return Flux.just(1, 2, 3);
        });

        System.out.println(
            "cold first = " + cold.collectList().block()
        );
        System.out.println(
            "cold second = " + cold.collectList().block()
        );

        Flux<Integer> cached = cold.cache(2);
        System.out.println(
            "cache first = " + cached.collectList().block()
        );
        System.out.println(
            "cache late = " + cached.collectList().block()
        );

        ConnectableFlux<Integer> replay =
            Flux.range(1, 3).replay(2);

        replay.subscribe(value ->
            System.out.println("replay first = " + value)
        );
        replay.connect();
        replay.subscribe(value ->
            System.out.println("replay late = " + value)
        );
    }
}
~~~

Run `gradle run` or the Gradle Wrapper: `./gradlew run` (Windows: `gradlew.bat run`). Program stdout, excluding Gradle logs:

~~~text
cold source subscription #1
cold first = [1, 2, 3]
cold source subscription #2
cold second = [1, 2, 3]
cold source subscription #3
cache first = [1, 2, 3]
cache late = [2, 3]
replay first = 1
replay first = 2
replay first = 3
replay late = 2
replay late = 3
~~~

**Explanation:**

- `Flux.defer` increments the counter for each new subscriber, proving the cold source ran twice separately.
- `cold.cache(2)` is a new publisher. The first subscriber to cache causes the cold upstream to be subscribed to a third time and receives all of 1, 2, 3.
- Cache retains the last two elements. The next subscriber does not trigger a fourth subscription; it receives 2, 3 from cache.
- `replay(2)` has its first subscriber registered before `connect()`. When the synchronous source emits 1, 2, 3, the first subscriber receives all of them. The late subscriber receives 2, 3.
- `block()` here is only used in a console program to collect results. In WebFlux controllers/services, return the publisher for the framework to subscribe; do not use `block()` on the event loop.

This is a standalone example using Java 17+ and Reactor Core. In a Spring Boot project, let the Spring Boot BOM manage compatible Reactor versions instead of pinning a separate version.

## 9. `Sinks.replay().limit` Example for Late Subscribers

The snippet below is a standalone example of a replay sink, which can be placed in `main` after importing `reactor.core.publisher.Sinks`:

~~~java
Sinks.Many<Integer> sink = Sinks.many().replay().limit(2);

sink.tryEmitNext(10).orThrow();
sink.tryEmitNext(20).orThrow();
sink.tryEmitNext(30).orThrow();
sink.tryEmitComplete().orThrow();

System.out.println(
    "sink late = " + sink.asFlux().collectList().block()
);
~~~

Output:

~~~text
sink late = [20, 30]
~~~

The sink emitted 10, 20, 30 and completed before the subscriber subscribed. Because the replay limit is 2, the late subscriber receives only 20 and 30 followed by completion.

In a real application, do not ignore the result of `tryEmit...`. `orThrow()` throws an exception if emission fails; with multi-producer event streams, decide on serialization and how to handle `EmitResult`. Do not emit concurrently at will into a sink that does not support concurrent emission.

## 10. Retention Policies: What to Bound and Why?

A cache/replay buffer consumes memory according to element count, payload size, and retention duration. When designing, separate the types of bounds:

### 10.1. Bounding by Element Count

For example, `cache(100)` or `replay(100)` retains at most the 100 most recent elements. This is a predictable count-based limit, yet **not a byte limit**.

100 small objects can be lightweight; 100 objects containing images, large JSON, or nested lists can be very heavy. Estimate memory by actual object-graph size, not just JSON string length.

### 10.2. Bounding by Time

A TTL such as two minutes fits when late subscribers only need recent history. However, with a fast-emitting source, the element count within two minutes can grow huge. TTL does not guarantee a fixed RAM budget.

### 10.3. Combining Count and TTL

When both freshness and history bounds are needed, choose a combined history/TTL overload matching your Reactor version. Example:

~~~java
Flux<Event> recent = eventSource.cache(
    1_000, java.time.Duration.ofMinutes(1)
);
~~~

Late subscribers only need to receive history still within the count and TTL limits. Verify the exact policy of the overload used in your project version; if strict byte limits are required, use a dedicated cache with weight/size eviction instead of relying solely on Reactor history counts.

### 10.4. Lifecycle Bounds

Explicitly ask how long the cache retains data:

- Until the source completes?
- Until TTL expires?
- While subscribers remain?
- Until a configuration or data version changes?
- Until a tenant/session/user is deleted?

Reactor's `cache` is not a key-value cache with per-key eviction or tenant-partitioning policies. If you need multi-ID caching, TTL, maximum size, refresh, metrics, and invalidation, consider Caffeine or a dedicated caching system.

### 10.5. Bounding Capacity by Bytes

Reactor cache/replay by history count and/or time does not directly guarantee an exact byte bound. For large payloads, consider:

- Caching only small DTOs or IDs, not entire blobs.
- Using a dedicated cache with a weight function and maximum weight.
- Limiting payload size before putting it into a buffer.
- Moving long-term history to a database/object storage/message broker.

## 11. Terminal Signals Can Also Be Cached

Cache does not only retain `onNext`. It can also retain the source's terminal signal:

| Initial Source | Later Subscribers Receive |
| --- | --- |
| Completed `Flux.just(1, 2).cache()` | Retained values, then `onComplete` |
| `Mono.empty().cache()` | Cached empty completion |
| `Mono.error(ex).cache()` | Error cached/replayed per API TTL/policy |
| Incomplete `Flux` | Retained history; subscribers can continue receiving new signals if the source stays active |

This matters when caching an HTTP request or database query. If the first attempt hits a transient error, `Mono.cache()` does not automatically know it was transient; later subscribers may receive the old error again. If retries are needed before caching, place retry upstream:

~~~java
Mono<Config> resilient = configService.load()
    .retryWhen(reactor.util.retry.Retry.max(2))
    .cache();
~~~

Here cache stores the signal after the retry policy finishes. If retries still fail, the final error can still be cached. Do not use infinite retries before cache; the first subscriber may wait forever and resources stay held.

Conversely:

~~~java
Mono<Config> perSubscriberRetry = configService.load()
    .cache()
    .retryWhen(reactor.util.retry.Retry.max(2));
~~~

Retry placed after cache can re-subscribe to **the same cached result**; if an error is cached, retrying does not necessarily call the source again. To actually call the source again, design TTL/invalidation or create a new publisher/cache instance per lifecycle.

### Empty Results Must Also Be Considered

If a `Mono<User>` is empty because the user was not found and is cached for a long time, a newly created record afterward may remain “invisible” to later subscribers until TTL/invalidation allows reloading. This is a stale negative-cache scenario.

When caching lookup results, define separate TTLs for values and empties if the API supports it; or use a dedicated cache with explicit negative-caching policies. Do not retain “not found” for too long if data can appear shortly after.

## 12. Cache/Replay, Backpressure, and Slow Subscribers

Backpressure (`request(n)`) regulates subscriber demand, but **does not replace a retention policy**. A hot source can emit independently; cache/replay keeps history in memory for late subscribers to receive.

When subscribers are slow:

- Non-replaying multicast may have to coordinate demand across active subscribers; exact behavior depends on the operator/sink.
- Replay/cache can retain data for late subscribers, with bounded or unbounded buffers depending on configuration.
- Sinks have their own overflow/backpressure policies; emission can fail if the buffer cannot accept more.
- No operator automatically guarantees an external source slows down if that source does not support demand.

Do not use unbounded `cache()` to “keep from losing events” on an infinite stream. If emission rate exceeds consumption capacity over time, retained data grows and eventually causes heap/GC/OOM pressure.

### Choosing a Policy per Data Type

| Data | Recommended Approach | Reason |
| --- | --- | --- |
| Small configuration loaded once at startup | `Mono.cache()` with appropriate invalidation/TTL | Shares a small result |
| Finite catalog, rarely changing | `Flux.cache(history)` if total size is controlled | Avoids repeated queries |
| Dashboard needing the last few events | `replay(n)` or `Sinks.replay().limit(n)` | New subscribers get a recent snapshot |
| High-volume telemetry stream, only latest samples needed | Bounded buffer or appropriate drop/latest strategy | Avoids retaining every event |
| Audit/events requiring durable storage | Database or message broker with persistence | Does not rely on one process's RAM |
| HTTP GET results needing short-term sharing | `Mono.cache(TTL)` or dedicated keyed cache | Avoids duplicate calls within TTL |
| User/tenant-sensitive results | Keyed cache with explicit security scope | Prevents cross-user data leaks |

## 13. Caching by Request/Key: Avoiding Accidental Data Sharing

A publisher on which `cache()` has been called is a specific instance. If held in a singleton field, every subscriber using that field can receive the same result. This is useful for global configuration, yet **dangerous if results depend on user, tenant, or request parameters**.

Risky example:

~~~java
@Service
class UserService {
    private final Mono<User> cachedUser =
        repository.findById("some-user").cache();
}
~~~

This example illustrates a singleton field. Every caller gets the same user; if the identifier actually needs to vary per request, this design is wrong.

Also be careful when writing:

~~~java
Mono<User> find(String id) {
    return repository.findById(id).cache();
}
~~~

Each call to `find(id)` creates a new cache instance, so it only shares among subscribers using **that exact returned instance**. Two independent calls to `find("u1")` do not automatically share a cache. To cache by key across requests, use a keyed cache (e.g., Caffeine) or a map/cache service with explicit eviction, TTL, concurrency, and invalidation.

In multi-tenant applications, keys must include the appropriate tenant/authorization scope. Do not cache personal data under an overly generic key like `"profile"` if multiple users could receive different results.

## 14. Invalidation, Refresh, and Stale Data

Reactor's `cache` is not a full cache service with arbitrary key deletion. When data changes, decide how to create a new publisher/cache or use an external caching layer supporting invalidation.

Several strategies:

1. **TTL:** data expires over time; simple, though it has a staleness window.
2. **Versioned key:** cache key includes a version/config revision; bumping version creates a new cache entry.
3. **Event invalidation:** when data changes, delete/mark the cache entry by key in a cache service.
4. **Refresh-ahead:** load fresh data before expiration; requires managing a refresh publisher and separate error handling.
5. **No caching:** when correctness outweighs query cost.

Do not keep a `cache()` publisher in a field and expect to call `invalidate()` like Caffeine. If complex invalidation is needed, use a dedicated cache and wrap value retrieval in a publisher only when fetching.

**Stale-while-revalidate** is a product/application policy: serve the old value while loading a fresh one. `cache` alone does not fully define this policy; you must design old/new value state, refresh, refresh errors, and update synchronization.

## 15. Testing with StepVerifier

Add file `src/test/java/CacheReplayTest.java` to the Gradle project in section 8. Dependencies `reactor-test` and JUnit are already in `build.gradle`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.ConnectableFlux;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CacheReplayTest {

    @Test
    void coldSourceRunsForEachSubscription() {
        AtomicInteger calls = new AtomicInteger();

        Flux<Integer> cold = Flux.defer(() -> {
            calls.incrementAndGet();
            return Flux.just(1, 2, 3);
        });

        StepVerifier.create(cold)
            .expectNext(1, 2, 3)
            .verifyComplete();

        StepVerifier.create(cold)
            .expectNext(1, 2, 3)
            .verifyComplete();

        assertEquals(2, calls.get());
    }

    @Test
    void cacheSharesUpstreamAndReplaysLimitedHistory() {
        AtomicInteger calls = new AtomicInteger();

        Flux<Integer> cached = Flux.defer(() -> {
            calls.incrementAndGet();
            return Flux.just(1, 2, 3, 4);
        }).cache(2);

        StepVerifier.create(cached)
            .expectNext(1, 2, 3, 4)
            .verifyComplete();

        StepVerifier.create(cached)
            .expectNext(3, 4)
            .verifyComplete();

        assertEquals(1, calls.get());
    }

    @Test
    void replayConnectableSendsHistoryToLateSubscriber() {
        ConnectableFlux<Integer> replay =
            Flux.range(1, 4).replay(2);

        StepVerifier.create(replay)
            .then(replay::connect)
            .expectNext(1, 2, 3, 4)
            .verifyComplete();

        StepVerifier.create(replay)
            .expectNext(3, 4)
            .verifyComplete();
    }

    @Test
    void monoCacheAlsoCachesAnErrorSignal() {
        AtomicInteger calls = new AtomicInteger();

        Mono<String> cachedError = Mono.defer(() -> {
            calls.incrementAndGet();
            return Mono.error(
                new IllegalStateException("source failed")
            );
        }).cache();

        StepVerifier.create(cachedError)
            .expectErrorMessage("source failed")
            .verify();

        StepVerifier.create(cachedError)
            .expectErrorMessage("source failed")
            .verify();

        assertEquals(1, calls.get());
    }
}
~~~

Run `gradle test` or the corresponding Gradle Wrapper. Four tests are expected to **PASS**:

- The cold source is subscribed to twice and the factory runs twice.
- The cached source runs only once; the later subscriber receives only the last two elements.
- The replay connectable retains the last two elements for a subscriber registering after source completion.
- `Mono.cache()` also shares error signals; the later subscription receives the cached error without calling the supplier again.

Replay tests use finite synchronous sources. With infinite or asynchronous sources, test connect timing, late subscribers, cancellation, TTL, and overflow separately. Do not use `Thread.sleep` to guess when data appears.

## 16. Common Pitfalls and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using default `cache()` on an infinite Flux | History can grow without bound | Choose `cache(history)` or TTL and account for payload size |
| Thinking `share()` replays old data | Late subscribers can miss earlier elements | Use `replay`/`cache` with explicit retention |
| Using unbounded `replay()` on a long-lived stream | Heap grows with entire history | Bound count/TTL or store outside the process |
| Assuming cache is distributed/durable | Process restarts lose history; other instances do not share it | Database, broker, or distributed cache |
| Caching errors indefinitely | Transient errors are replayed to later subscribers | TTL/explicit error policy, retry before cache if appropriate |
| Failing to intentionally cache negative results | Cache misses can cause repeated query load | Short-TTL negative caching if contract permits |
| Holding per-user cache in a singleton field | May return another user's data | Cache by key/tenant and auth scope |
| Thinking history=100 limits memory to 100 KB | Large payloads can consume significant RAM | Cache with maximum weight or payload limits |
| Confusing connect, autoConnect, refCount | Source may start too early or fail to stop as expected | Design and test subscriber lifecycle |
| Ignoring tryEmit... results | Emissions can fail without the app noticing | Check tryEmit... and handle each failure kind |
| Using cache instead of backpressure | Buffers can still fill and upstream can still emit fast | Manage demand, queues, concurrency, and retention separately |
| Using cache instead of transactions | Multiple subscribers see the same result, yet side effects are not atomic | Use transactions/idempotency and appropriate persistence |

## 17. Strategy Selection Checklist

Before putting `cache` or `replay` into a pipeline, answer:

1. **Is the source cold or hot?** Does each subscriber need a new call or share one execution?
2. **What do late subscribers need?** No history, latest value, last N events, or full history?
3. **Which retention bounds apply?** Count, TTL, bytes/weight, or a combination? If the source never ends, bounds must be finite.
4. **Should terminal signals be retained?** Caching errors/empty can keep stale state around; define TTL/invalidation.
5. **Who manages connections?** `cache` auto-triggers; `ConnectableFlux` needs connect/autoConnect/refCount.
6. **What happens when no subscribers remain?** Should the source keep running or be allowed to stop?
7. **Is data per-user/tenant?** Keys and access permissions must be isolated; avoid caching sensitive data globally.
8. **Does data need to survive restarts or span multiple instances?** If so, use appropriate persistence/distributed cache/broker.
9. **Have memory and load been measured?** Check element count, payload size, emission rate, subscriber count, GC, and p95/p99.
10. **Have late subscribers and errors been tested?** Verify replay history, TTL, terminal errors, cancellation, and reconnection.

**Key takeaway:** cold publishers typically run separately per subscriber; hot publishers can emit before subscribers subscribe. `share/publish` share the current stream, while `replay` and `cache` retain partial history for replay. Choose explicit limits on **element count, duration, and real memory capacity** before caching a long-lived source. Reactor cache/replay is an in-process memory mechanism and does not replace persistence or a key-evicting cache service.

## References

- Project Reactor Reference — Hot Versus Cold: https://projectreactor.io/docs/core/release/reference/advancedFeatures/reactor-hotCold.html
- Project Reactor Reference — Broadcasting to Multiple Subscribers with ConnectableFlux: https://projectreactor.io/docs/core/release/reference/advancedFeatures/advanced-broadcast-multiple-subscribers-connectableflux.html
- Reactor `Flux` API — `cache`, `replay`, `publish`, `share`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Reactor `Mono` API — `cache` and TTL variants: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Reactor `Sinks` API: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.html
- Spring Framework — WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Reactive Streams specification: https://www.reactive-streams.org/
