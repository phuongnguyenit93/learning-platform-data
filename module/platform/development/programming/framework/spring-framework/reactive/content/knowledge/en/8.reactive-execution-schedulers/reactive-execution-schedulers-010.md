# Shared State and Thread Safety Across Multiple Subscriptions

## 1. The Problem to Understand

In Spring WebFlux and Project Reactor, the same `Flux<T>` or `Mono<T>` can be subscribed to by multiple Subscribers: two HTTP requests, two consuming branches, a retry, or multiple clients of an event stream. An application can also switch threads when using `subscribeOn`, `publishOn`, schedulers, asynchronous I/O, and concurrent operators.

Two separate questions must be answered:

1. **Who owns this state?** Does each subscription need its own instance, or do all subscriptions intentionally share one?
2. **Who can access that state concurrently?** If multiple threads exist, how must reads/writes guarantee atomicity, visibility, and business invariants?

If you ignore the first question, one subscription can inherit another subscription's counter, collection, or temporary result even when running sequentially. If you ignore the second question, concurrent updates can be lost or leave data structures inconsistent. An `AtomicInteger` can solve races on a single counter, yet **does not** isolate data per Subscriber.

This lesson covers Publisher–Subscription boundaries, lambda-captured variables, the Java Memory Model, using `Flux.defer`, `generate`, `transformDeferred`, stateful operators, Reactor `Context`, shared/hot publishers, Spring singletons, concurrency-safe sinks, Java 17+ examples, and testing.

## 2. One Publisher Can Be Subscribed To Multiple Times

A Publisher describes a data-emission process. A Subscriber calls `subscribe` to establish a `Subscription`, then uses `request(n)` or `cancel()` to coordinate flow. With *cold* sources like `Flux.range` and `Flux.just`, each subscription typically receives a fresh emission run; however, **already-created Java closures are not automatically cloned**.

~~~text
                    Assembled Flux
                           |
                  +--------+--------+
                  |                 |
              subscribe A       subscribe B
                  |                 |
            Subscription A    Subscription B
              demand A          demand B
              cancel A          cancel B
                  |                 |
                  +------ same reference? -----+
                                               |
                                  shared mutable object
~~~

Reactive Streams Publisher rule 1.3 requires `onSubscribe`, `onNext`, `onError`, and `onComplete` to be signaled **sequentially within each subscription**, meaning no two callbacks may concurrently enter a Subscriber for the same subscription; across thread switches, *happens-before* must hold between signals. **This rule does not synchronize different subscriptions.**

~~~text
Subscription A: onNext(1) ── onNext(2) ── onComplete
Subscription B:      onNext(X) ── onNext(Y) ── onComplete

Both streams can run concurrently on different threads.
~~~

Moreover, even though signals to a downstream Subscriber are serialized, side effects caused by two inner publishers inside `flatMap` can still execute concurrently. Do not treat downstream callback ordering as a shared lock protecting fields in a singleton service or external resources.

## 3. Types of State and Ownership Scope

| State kind | Example | Typical scope | Rule |
| --- | --- | --- | --- |
| Variable created at assembly and captured by lambda | `AtomicInteger counter` declared before `map` | Same reference may be used by multiple subscriptions | Share only intentionally |
| Variable created in per-subscription factory | Variable inside `Flux.defer` or `transformDeferred` | Private to each subscription if factory creates a new object | Use for progress, sequence numbering, request handling |
| State managed by Reactor operators | `distinct`, `scan`, `buffer`, `collectList` | Generally per subscription per operator contract | Prefer standard operators over external collections |
| Field on a Spring singleton bean | Cache, counter, `Map`, mutable helper | Visible across multiple requests/subscriptions | Immutable or properly synchronized |
| Hot/multicast publisher, sink, cache | `Sinks.Many`, `share`, `cache` | Can share source, signals, or payloads | Check lifecycle and ownership rules |

**Distinguish variable from object.** A `final` reference variable only prevents reassignment; if it points to an `ArrayList` or `AtomicInteger`, the object's contents can still mutate. A local variable inside `map(value -> { ... })` is created each time the lambda runs, whereas a local variable declared **outside** the lambda and captured can outlive multiple subscriptions.

Example:

~~~java
AtomicInteger counter = new AtomicInteger();

Flux<Integer> counts = Flux.just(10, 20)
        .map(value -> counter.incrementAndGet());
~~~

Each `subscribe` on `counts` re-runs `onNext`, yet `counter` was created only once when building `counts`. If subscribed twice sequentially, the first run receives 1, 2; the second receives 3, 4. The counter is thread-safe, yet **shared**. That may be right for a global metric, and wrong for a per-request index.

## 4. Data Races and the Java Memory Model

Consider a bean holding a mutable counter:

~~~java
class UnsafeCounter {
    private int count;

    void increment() {
        count++;   // read → add → write, non-atomic
    }

    int get() {
        return count;
    }
}
~~~

Two threads can both read `count = 7`, both compute 8, and both write 8. Two increments collapse into one (*lost update*). Lack of proper synchronization also causes *visibility* issues: one thread is not guaranteed to observe updates written by another.

Marking `volatile int count` aids visibility and ordering for field accesses, yet **does not make `count++` atomic**. For an intentionally shared total counter:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

class SafeCounter {
    private final AtomicInteger count = new AtomicInteger();

    void increment() {
        count.incrementAndGet();
    }

    int get() {
        return count.get();
    }
}
~~~

If updates are very frequent and only an aggregate metric is needed, `LongAdder` can reduce contention, though `sum()` running concurrently with updates is not a linearizable snapshot of the whole system. If two fields must change as **one invariant** (such as balance and version), two separate `AtomicInteger`s are not enough; you need CAS over an immutable snapshot, a state-protecting lock, a sequential actor/queue, or a proper transaction.

`ConcurrentHashMap` supports concurrent access, yet a `get → compute → put` sequence is not automatically atomic for the same key. When conditional per-key updates are required, use `compute`/`merge` or another consistency mechanism per application contract. For business operations spanning multiple databases/services, in-JVM locks do not replace cross-process transactions and concurrency control.

## 5. Proper Isolation with Flux.defer

`Flux.defer(Supplier<? extends Publisher<T>>)` invokes the Supplier **each time** the resulting Flux is subscribed to. This is the right place to allocate a per-run counter or state object:

~~~java
Flux<String> local = Flux.defer(() -> {
    AtomicInteger index = new AtomicInteger();
    return Flux.just("A", "B")
            .map(s -> index.incrementAndGet() + ":" + s);
});
~~~

Subscribers S1 and S2 both receive `1:A`, `2:B` (with this cold source). The state is created inside the supplier and captured only by lambdas belonging to the Publisher built for that run.

Compare with a case that is still wrong:

~~~java
AtomicInteger shared = new AtomicInteger();

Flux<String> stillShared = Flux.defer(() ->
        Flux.just("A", "B")
            .map(s -> shared.incrementAndGet() + ":" + s)
);
~~~

`defer` calls the Supplier multiple times, yet `shared` sits **outside the Supplier**, so it remains a single object. `defer` does not clone objects captured by closures.

When you want to reuse a processing segment over an existing source per subscription, use `transformDeferred`:

~~~java
Flux<String> numbered = Flux.just("A", "B")
        .transformDeferred(source -> {
            AtomicInteger index = new AtomicInteger();
            return source.map(s -> index.incrementAndGet() + ":" + s);
        });
~~~

`transformDeferred` applies the transformer per subscription, allowing state initialization inside the transformer body. By contrast, `transform` applies the transformer right at pipeline assembly, causing state created inside the transformer to be shared across repeated subscribes. `defer` defers **creating a source or pipeline**, while `transformDeferred` defers **attaching an operator segment** to an existing source. You do not necessarily need both everywhere.

Note that `retry` and `repeat` can re-subscribe upstream. The phrase "per subscription" must specify **subscription at which operator**. If a `defer` result passes through `cache()` or `share()`, upstream subscription counts can differ from downstream Subscriber counts.

## 6. Prefer Standard Stateful Operators

### 6.1. scan Instead of an External Accumulator Variable

~~~java
Flux<Integer> sums = Flux.just(1, 2, 3)
        .scan(0, Integer::sum);

sums.subscribe(System.out::println);
~~~

Stdout:

~~~text
0
1
3
6
~~~

`scan` emits seed 0 first, then cumulative sums 1, 3, 6. With immutable `Integer` values, accumulated state is managed per subscription. That eliminates data mixing across subscriptions compared to `doOnNext(n -> sharedTotal += n)`.

If the seed is a **pre-created mutable object that gets captured**, you still must analyze reference sharing; prefer an immutable accumulator or an overload supplying initial state via a supplier if the API requires it.

### 6.2. distinct and collectList

~~~java
Flux<String> unique =
        Flux.just("A", "A", "B").distinct();

Mono<java.util.List<String>> list =
        Flux.just("A", "B").collectList();
~~~

Per Reactor Javadoc, `distinct` tracks seen elements **per Subscriber**, and `collectList` collects items for that subscription. Do not replace them with an `ArrayList` declared outside the pipeline plus `doOnNext(list::add)`: subscriptions can mix contents and perform unsafe concurrent writes.

### 6.3. Flux.generate for Private State

When building a synchronous stateful stream yourself, the `Flux.generate(stateSupplier, generator)` overload invokes `stateSupplier` **per Subscriber**:

~~~java
Flux<Integer> generated = Flux.generate(
        () -> 1,
        (state, sink) -> {
            if (state <= 3) {
                sink.next(state);
                return state + 1;
            }
            sink.complete();
            return state;
        }
);
~~~

Each Subscriber receives 1, 2, 3 and then completes. `Flux.generate` uses `SynchronousSink`, emitting at most one data signal per generator invocation. Do not emit multiple `onNext` signals concurrently from different threads inside the generator. Overloads with a state-cleanup consumer exist; subscription-scoped resources can also be managed via `Flux.using` / `usingWhen`.

**There is no rule that every Reactor operator creates private state:** `share`, `cache`, `replay`, and multicast mechanisms intentionally alter how a source is shared.

## 7. Standalone Java 17+ Example: Shared vs. Per-Subscription

This example intentionally uses two **sequential** subscriptions to demonstrate state leakage without relying on races or random timing.

Create the project:

~~~text
reactor-state-demo/
├── build.gradle
└── src/main/java/SubscriptionStateDemo.java
~~~

File `build.gradle`:

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
    mainClass = 'SubscriptionStateDemo'
}
~~~

File `src/main/java/SubscriptionStateDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Flux;

public class SubscriptionStateDemo {

    private static void show(String label, Flux<String> source) {
        System.out.print(label + ": ");
        source.collectList().subscribe(System.out::println);
    }

    public static void main(String[] args) {
        AtomicInteger sharedCounter = new AtomicInteger();

        Flux<String> shared = Flux.just("A", "B")
                .map(value ->
                        sharedCounter.incrementAndGet() + ":" + value);

        Flux<String> isolated = Flux.defer(() -> {
            AtomicInteger localCounter = new AtomicInteger();
            return Flux.just("A", "B")
                    .map(value ->
                            localCounter.incrementAndGet() + ":" + value);
        });

        show("shared S1", shared);
        show("shared S2", shared);
        show("isolated S1", isolated);
        show("isolated S2", isolated);

        System.out.println("shared total: " + sharedCounter.get());
    }
}
~~~

In the directory containing `build.gradle`, run with Gradle installed:

~~~bash
gradle -q run
~~~

Or use the wrapper `./gradlew -q run` if the project has a wrapper on Linux/macOS, `gradlew.bat -q run` on Windows. Stdout emitted by the **program**:

~~~text
shared S1: [1:A, 2:B]
shared S2: [3:A, 4:B]
isolated S1: [1:A, 2:B]
isolated S2: [1:A, 2:B]
shared total: 4
~~~

`Flux.just`/`collectList` in the program have no asynchronous scheduler, so `subscribe` processes immediately and output order is deterministic. `sharedCounter` is the same object across S1 and S2; the counter inside `defer` is allocated separately. Using `AtomicInteger` on the shared branch makes increments atomic under concurrency, but does not turn the shared branch into a per-subscription branch.

Do not prove thread safety merely because stdout "looks right" in a single run. Testing isolation and global metrics in section 11 uses deterministic invariants.

## 8. Schedulers, ThreadLocal, and Reactor Context

`Flux`/`Mono` does not imply a dedicated thread. Many operators run on the upstream emitting thread. `subscribeOn` changes the subscription/source context; `publishOn` switches downstream to a chosen scheduler. One subscription may switch threads over its lifetime, and the same worker thread may serve multiple different subscriptions.

~~~text
Request A: event-loop-1 → publishOn → parallel-2 → Subscriber A
Request B: event-loop-1 → publishOn → parallel-1 → Subscriber B
~~~

This is an **illustrative diagram**; actual threads depend on schedulers and the application. Signals of the same subscription still obey serialization rules, yet two subscriptions can run concurrently and both read/write an object handed to them.

**ThreadLocal is not subscription-local state.** When switching threads, ThreadLocal values do not follow the subscription automatically; when a thread pool reuses threads, stale request info can linger if mismanaged. In Reactor code, use `Context` to carry metadata such as trace ID/correlation ID per subscription.

~~~java
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

Mono<String> source = Mono.deferContextual(context ->
        Mono.just("trace=" + context.get("traceId")));

source.contextWrite(Context.of("traceId", "req-100"))
      .subscribe(System.out::println);
~~~

With this synchronous source, stdout:

~~~text
trace=req-100
~~~

`contextWrite` adds entries to the Context visible upstream; `deferContextual` reads it per subscription. Context is an immutable key/value structure with respect to adding/removing keys, **yet an object stored as a value can still be mutable and shared** if multiple subscriptions receive the same reference. Do not place a shared `ArrayList` in Context and assume it is isolated.

MDC/ThreadLocal integrations with specific propagation mechanisms can work when properly configured; never assume ThreadLocal remains accurate after `publishOn` without an explicit propagation mechanism.

## 9. Cold, Hot, share, and cache Sources

A cold source such as `Flux.range` typically creates a fresh emission per Subscriber, yet does not clone application objects captured at assembly. A hot source like `Sinks.Many` can emit the same events to multiple currently listening Subscribers. If payloads are mutable objects, Subscribers can mutate **the same object** on different threads.

`share()` connects multiple downstream Subscribers to one active upstream; late subscribers can miss already-emitted events. `cache()` can retain data/terminal signals to replay to later Subscribers, and may subscribe upstream only once. A source with per-subscription state **before `cache`** will not automatically re-run for each downstream Subscriber.

~~~java
Flux<String> upstream = Flux.defer(() -> {
    AtomicInteger n = new AtomicInteger();
    return Flux.just("x", "y")
            .map(s -> n.incrementAndGet() + ":" + s);
});

Flux<String> cached = upstream.cache();
~~~

This is an illustrative snippet requiring `Flux`/`AtomicInteger` imports in the app. Once `cached` has been subscribed to and cached data, subsequent Subscribers can receive the cached results without creating a new counter in `upstream`. Therefore verify **operator placement and connection lifecycle** before assuming independent state.

If a payload contains a mutable List/Map, prefer emitting immutable instances or necessary defensive copies (e.g., `List.copyOf` in Java 17) so two Subscribers cannot mutate the same reference. A Java `record` only freezes field references; a record holding a mutable List may still need defensive copying.

## 10. Multiple Producers and Sinks.Many

When bridging multiple producer callbacks into one Flux, both **serial signaling** and **shared-data correctness** must be addressed. Reactor's `Sinks.Many` provides an API to control emission and report failures:

~~~java
import reactor.core.publisher.Sinks;

Sinks.Many<String> sink = Sinks.many()
        .multicast()
        .onBackpressureBuffer();

Sinks.EmitResult result = sink.tryEmitNext("event");
if (result.isFailure()) {
    // Handle emission failure per application policy.
}
~~~

This is an API illustration snippet without a standalone `main`. With safe sinks, when multiple threads contend emitting at once, `tryEmitNext` can return `FAIL_NON_SERIALIZED`. Results like `FAIL_OVERFLOW`, `FAIL_TERMINATED`, and `FAIL_ZERO_SUBSCRIBER` report other failure cases depending on sink configuration. **Do not ignore `EmitResult`** and assume the event was delivered.

When needed, use a single-producer queue/actor feeding the sink, or `emitNext` with a bounded retry handler tailored to the failure type. Avoid infinite spin loops or unchecked resends that can burn CPU or emit duplicates. `Sinks.unsafe()` does not guard concurrent emissions like safe sinks, and is meant only where the caller guarantees serialization.

A sink that serializes signals does not automatically solve **backpressure**: a producer faster than consumers can still trigger overflow, dropped data, or buffer buildup. Plan demand, memory limits, and business policies separately.

## 11. Testing Isolation and Concurrent Shared Metrics

In a project with `reactor-test` and JUnit 5 in test scope, Gradle can include:

~~~groovy
dependencies {
    testImplementation 'io.projectreactor:reactor-test:3.8.8'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

File `src/test/java/SubscriptionStateTest.java`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class SubscriptionStateTest {
    @Test
    void freshStatePerSubscribe() {
        Flux<Integer> isolated = Flux.defer(() -> {
            AtomicInteger n = new AtomicInteger();
            return Flux.just("A", "B")
                    .map(value -> n.incrementAndGet());
        });

        StepVerifier.create(isolated)
                .expectNext(1, 2)
                .verifyComplete();
        StepVerifier.create(isolated)
                .expectNext(1, 2)
                .verifyComplete();
    }

    @Test
    void capturedStateRemainsShared() {
        AtomicInteger count = new AtomicInteger();
        Flux<Integer> shared = Flux.just("A", "B")
                .map(value -> count.incrementAndGet());

        StepVerifier.create(shared)
                .expectNext(1, 2)
                .verifyComplete();
        StepVerifier.create(shared)
                .expectNext(3, 4)
                .verifyComplete();
    }

    @Test
    void atomicMetricCountsUpdatesFromTwoPipelines() {
        AtomicInteger total = new AtomicInteger();

        Mono<Void> a = Flux.range(1, 1_000)
                .publishOn(Schedulers.parallel())
                .doOnNext(value -> total.incrementAndGet())
                .then();

        Mono<Void> b = Flux.range(1, 1_000)
                .publishOn(Schedulers.parallel())
                .doOnNext(value -> total.incrementAndGet())
                .then();

        StepVerifier.create(Mono.when(a, b)).verifyComplete();
        assertEquals(2_000, total.get());
    }
}
~~~

Test 1 proves state inside `defer` resets per run. Test 2 proves a captured counter is shared, even without concurrent execution. Test 3 verifies total atomic updates once two pipelines that can run on different workers have completed. Depending on the machine, the scheduler may use few threads; **a passing test does not prove every shared access in the app is thread-safe**.

Do not write a test expecting `int count++` to always lose updates: races depend on scheduling and may not reproduce on a given run. Test invariants and use proper stress/concurrency tools when real race risk exists.

## 12. Spring WebFlux and Singleton Services

Spring services by default are singletons in the application context, so multiple HTTP requests can invoke the same instance. Mutable fields in a service are shared state across requests; **per-subscription** state should be allocated separately.

Example in a Spring Boot WebFlux project:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.LongAdder;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public final class EventLabelService {

    // App-wide metric: intentionally shared.
    private final LongAdder totalProcessed = new LongAdder();

    public Flux<String> label(Flux<String> events) {
        return Flux.defer(() -> {
            // Per-subscription index.
            AtomicInteger perSubscription = new AtomicInteger();

            return events.map(event -> {
                totalProcessed.increment();
                return perSubscription.incrementAndGet() + ":" + event;
            });
        });
    }

    public long approximateTotal() {
        return totalProcessed.sum();
    }
}
~~~

This is an illustrative service class, **not a program with `main`**. `totalProcessed` is an intentionally shared metric; `LongAdder` supports concurrent updates. `sum()` is not a strictly consistent snapshot during updates, so do not use it as a transaction balance. `perSubscription` sits inside `Flux.defer`, so each subscription to `label`'s result gets its own counter.

When a controller returns `Mono` or `Flux`, Spring WebFlux manages subscription/cancellation. Do not call `subscribe()` manually in a handler just to update a field and return a response; side effects belong properly in the pipeline or a separate workflow with a clear contract. If state is a lifecycle resource (connection, cursor, session), use `using`/`usingWhen` to clean up on complete, error, **and cancel**, instead of holding it in a singleton field.

With retry, repeat, or a request actually subscribed multiple times, side effects in `doOnNext` can execute repeatedly. `doOnNext` gives no exactly-once guarantee. If the side effect is a payment/DB write, use idempotency keys, transactions, message acknowledgements, or suitable storage design.

## 13. Technical Decision Table

| Goal | Approach | Limitations |
| --- | --- | --- |
| Per-subscription counter / state | `defer`, `generate(stateSupplier)`, `transformDeferred`, `scan`/`distinct` operators | Allocate state inside the factory; watch `cache/share` |
| Passing objects across threads/subscribers | Immutable values, defensive copy if needed | A record holding a mutable collection can still be mutated |
| Global metric counter | `AtomicLong`, `LongAdder` | Does not replace business transactions |
| Shared cache map | `ConcurrentHashMap`, updates via `compute/merge` | Related multi-step invariants still require synchronization |
| Updating multiple fields consistently | Immutable snapshot/CAS, lock, actor, or transaction | Separate atomics do not form a transaction |
| Per-subscription trace ID across schedulers | Reactor `Context` and contextual APIs | A Context value can still be shared if it is a mutable object |
| Multiple producers emitting events | Safe `Sinks.Many`, handle `EmitResult`, single-writer queue | Still needs backpressure policy |
| Resource-managing state | `using`/`usingWhen` | Cleans up on error, cancel, and retry |

Do not treat everything as shared state needing locks. When a problem can be solved with **immutable data + pure functions + per-subscription state**, code is usually easier to reason about and test. When sharing is required, pinpoint the exact invariants to protect, synchronization scope, and behavior under load.

## 14. Common Mistakes and Fixes

1. **Using an `ArrayList` as a Spring singleton field with `doOnNext(list::add)`:** subscriptions mix data and can perform concurrent writes. Choose `collectList` per subscription or concurrent storage with clear ownership.
2. **Assuming per-subscription serialized signals protect shared fields:** two subscriptions can run concurrently. Separate state or proper synchronization is needed.
3. **Using `volatile` to make `count++` atomic:** volatile does not prevent lost updates. Use atomic increments or locks.
4. **Putting `AtomicInteger` outside `Flux.defer` and thinking it resets:** the object is still lambda-captured. Allocate inside the Supplier.
5. **Using `ThreadLocal` as request state with `publishOn`:** data may not follow the subscription. Use Reactor `Context` or properly configured propagation.
6. **Using `share` or `cache` and expecting upstream to run separately per Subscriber:** upstream may already be shared or cached. Check where operators are placed.
7. **Assuming an immutable record makes the whole object graph immutable:** mutable collection fields still need defensive copying.
8. **Using `ConcurrentHashMap` yet `get-then-put` still has business races:** use atomic map methods or an overarching consistency mechanism.
9. **Ignoring `FAIL_NON_SERIALIZED` when emitting from multiple producers:** events can be dropped/rejected. Handle results and serialize emissions when needed.
10. **Writing to DB in `doOnNext` and retrying without bounds:** side effects can repeat, causing duplicate data. Design idempotency, bound retries, and control commits.
11. **Testing with only one Subscriber:** state leakage may stay hidden. Test subscribing twice to the same Publisher, plus concurrency for genuinely shared resources.
12. **Thinking `subscribeOn`/`publishOn` automatically makes mutable objects thread-safe:** schedulers only control where code runs; they add neither atomicity nor isolation.

Observe production with metrics, logs tagged with Context correlation IDs, and tests with at least two subscriptions. To find state leaks, inspect **where variables are created and references are captured**, not only thread numbers appearing in logs.

## 15. Self-Check

1. A Flux with a counter created outside `map` is subscribed to twice sequentially: does the counter reset automatically? **No; both runs share the reference.**
2. Does a shared `AtomicInteger` counter solve "each request starts at 1"? **No; it only makes increments atomic.**
3. Does `Flux.defer` automatically copy objects declared outside the Supplier? **No.**
4. Why do `onNext` callbacks serialize within a subscription yet a singleton field still races? **Because two different subscriptions can run concurrently against that field.**
5. Does `volatile int count` make `count++` atomic? **No.**
6. When does `Flux.generate(stateSupplier, generator)` create state? **Once per Subscriber registration.**
7. Whose seen values does `distinct` track in a cold Flux? **Per Subscriber.**
8. When `cache` is added after `defer`, is every downstream Subscriber guaranteed to trigger a new Supplier call? **No.**
9. What should you use to pass a correlation ID across thread hops per subscription? **Reactor `Context`.**
10. What does `FAIL_NON_SERIALIZED` on `Sinks.EmitResult` indicate? **Non-serialized concurrent emission into the sink.**
11. Are two atomic counters for `balance` and `version` enough to update both atomically as one transaction? **No.**
12. Why does `doOnNext` not guarantee an exactly-once side effect? **Retry/repeat or re-subscription can invoke the callback multiple times.**

**Takeaway:** A Subscription is the scope of signal-protocol guarantees, not an automatic isolator for all Java objects. Use per-subscription factories or standard stateful operators when state belongs to one Subscriber; for intentionally shared resources, deliberately choose immutable designs, atomics, synchronization, and business consistency mechanisms.

## References

- [Reactive Streams JVM specification — rule 1.3, serial signaling and happens-before](https://github.com/reactive-streams/reactive-streams-jvm).
- [Project Reactor Flux Javadoc — defer, generate, distinct, share, cache, using](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- [Project Reactor Reference Guide — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html).
- [Project Reactor Reference Guide — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html).
- [Project Reactor Sinks.EmitResult — FAIL_NON_SERIALIZED and emission failures](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.EmitResult.html).
- [Project Reactor Reference Guide — Testing](https://projectreactor.io/docs/core/release/reference/testing.html).
- [Spring Framework — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html).
