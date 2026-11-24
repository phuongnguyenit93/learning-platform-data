# `subscribeOn` Controls the Source Subscription Process in Project Reactor

## 1. Goal and Problem to Solve

In Project Reactor, a `Mono` or `Flux` pipeline describes processing steps, yet mostly does nothing until there is a **subscription**. When subscription begins, Reactor must walk back up the operator chain toward the original publisher, establish the `Publisher–Subscriber–Subscription` relationship, and emit data signals when demand exists. `subscribeOn(Scheduler)` is the tool to **move the source subscription process onto a `Scheduler.Worker`**, thereby influencing the source's signal-emitting context in synchronous pipelines.

This is the meaning of the topic "`subscribeOn` controls the source subscription process" under **Execution Threading**. Distinguish it from `publishOn`, from spawning threads automatically, and from an asynchronous source that already decides where to emit events.

After this lesson, you will be able to:

- Explain what happens at **assembly**, **subscription**, **request**, and **signal delivery**.
- Trace the flow direction of `subscribe()`, `onSubscribe`, `request(n)`, and `onNext` across an operator chain.
- Predict which segment runs on the `subscribeOn` worker; understand why placing it close to the source is easier to read.
- Compare `subscribeOn` with `publishOn` and know how to combine them.
- Use `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` when integrating synchronous I/O in Spring WebFlux.
- Avoid misconceptions such as "calling `subscribeOn` makes the whole pipeline run on that thread," "calling `subscribeOn` already subscribes," or "switching threads automatically makes code non-blocking."
- Write a Java 17+ example and test that verify behavior without relying on timing guesswork.

## 2. Four Distinct Phases

**Assembly**: Java code executes to **create** publishers and chain operators:

~~~java
Mono<Integer> pipeline = Mono.fromSupplier(() -> 21)
    .map(value -> value * 2)
    .subscribeOn(Schedulers.boundedElastic());
~~~

The snippet above only **assembles** the publisher. `fromSupplier` has not called the supplier yet; `map` has not transformed any value. Nor does `subscribeOn` initiate a subscription by itself. It only configures how subscription will be carried out later.

**Subscription**: downstream calls `subscribe(...)`, `block()`, `StepVerifier.verify()`, or a framework (like Spring WebFlux) subscribes to the publisher. At that point, the internal subscriber chain is established, typically traveling from the end of the pipeline back toward the source.

**Request**: the subscriber requests a number of elements via `Subscription.request(n)`. For some sources, this request triggers data emission. By default, `subscribeOn` also schedules request signaling upstream on the scheduler's worker, per Reactor semantics and the involved operators.

**Signal delivery**: `onNext`, `onError`, and `onComplete` are emitted from the source downstream. With a synchronous source like `Flux.range` or `Mono.fromCallable`, subscribing on a worker typically causes source signals to be produced on that worker; a subsequent `publishOn` can then further switch the downstream signal-emitting context.

**Do not confuse with Java argument evaluation:** calling `Mono.just(blockingRead())` already executes `blockingRead()` **before `Mono` construction finishes**, so `subscribeOn` written after `just` cannot move an already-completed blocking call to another scheduler. To defer it, place the call inside a supplier/callable.

## 3. Subscription Flows Backward, Data Flows Forward

Consider the pipeline:

~~~java
Flux<Integer> pipeline = Flux.range(1, 3)
    .map(i -> i * 10)
    .subscribeOn(Schedulers.boundedElastic())
    .filter(i -> i >= 20);
~~~

This is a snippet assuming `Flux` and `Schedulers` are imported.

~~~text
Assembly (written order):
Flux.range -> map -> subscribeOn -> filter -> final subscriber

Subscription:
final subscriber
    -> filter
    -> subscribeOn: schedules work on a Scheduler.Worker
    -> map
    -> Flux.range (actual source subscribed to)

Data (example with a synchronous source):
Flux.range: onNext(1), onNext(2), onNext(3)
    -> map: 10, 20, 30
    -> subscribeOn
    -> filter: 20, 30
    -> final subscriber
~~~

`subscribeOn` **is not a value-transformation operator**. It intervenes in registration and request scheduling toward the source. When the source emits synchronously on the scheduled worker, consecutive synchronous operators also typically receive signals on that worker unless another async boundary exists.

**Key point:** writing `subscribeOn` after `map` does not mean `map` will run before the scheduler. Subscription is established backward toward the source, so `map` still belongs to the source portion subscribed to on the worker.

At the same time, do not apply that conclusion blindly to every publisher: `Flux.interval`, callback APIs, sinks/hot sources, network clients, and operators with their own schedulers can have their own signal-emitting mechanisms.

## 4. What Does `subscribeOn` Actually Control?

With the common overload:

~~~java
source.subscribeOn(scheduler)
~~~

Reactor uses a `Scheduler.Worker` to **subscribe to the upstream segment**, including setting up the subscription and typically scheduling `request(n)` calls upstream on that worker. In a synchronous source section, data creation and synchronous callbacks can execute on the chosen worker.

There are three consequences:

1. **The thread initiating subscription externally and the thread running the source can differ.** For instance, `main` calls `block()`, while `Callable` executes on a scheduler worker. `block()` itself still makes `main` wait for the result.
2. **The unit of control is source subscription, not one thread per element.** `subscribeOn` by itself does not create per-element parallelism; a synchronous `map` chain does not split three items onto three threads.
3. **It cannot change the thread an external asynchronous source already chose for callbacks.** For example, an SDK firing callbacks from its own thread, or a sink receiving `tryEmitNext` from another thread. `subscribeOn` still governs subscription of the relevant Reactor segment, yet signals from that source may arrive on its own thread.

When debugging, separate three questions: who called `subscribe()`, on which worker was the source subscribed to, and on which thread did each `onNext` actually run. They often coincide for simple synchronous sources, but that is not a law for all sources.

## 5. Position of `subscribeOn` in the Chain

Reactor documentation recommends placing `subscribeOn` **immediately after the source** so readers see the intent clearly and intermediate operators do not obscure the execution context.

The following two forms typically produce the same result for the source's thread in a simple synchronous pipeline:

~~~java
// Approach 1: close to source, easy to read
Flux<Integer> a = Flux.range(1, 3)
    .subscribeOn(Schedulers.parallel())
    .map(i -> i * 2);

// Approach 2: placed after map; subscription still travels backward to source
Flux<Integer> b = Flux.range(1, 3)
    .map(i -> i * 2)
    .subscribeOn(Schedulers.parallel());
~~~

This is a snippet: it only **constructs** two publishers, with no output before subscribing. On subscription, `subscribeOn` schedules subscription to `Flux.range` on the specified scheduler. For synchronous operators like `map`, data typically continues flowing on the thread selected from the scheduler.

`subscribeOn` placement is not like `publishOn` placement: `publishOn` switches signals **from its position downward downstream**, so moving it noticeably alters which operators run on the new scheduler.

### Should You Write Multiple `subscribeOn` Calls?

Example:

~~~java
Flux<Integer> stream = Flux.range(1, 3)
    .subscribeOn(Schedulers.single())
    .map(i -> i * 2)
    .subscribeOn(Schedulers.boundedElastic());
~~~

Do not view each `subscribeOn` as a "thread-switching step" for `map`. Per the Reactor Reference, **the `subscribeOn` closer to the source in the downstream chain** is the one that actually schedules subscribe/request for the source or intercepting operators (like `doFirst`, `doOnRequest`); additional `subscribeOn` calls can introduce unnecessary worker hops. Most pipelines only need **one appropriate `subscribeOn` for the source that needs isolation**.

Nor should you rely solely on the ordering of multiple `doOnSubscribe` hooks to measure where a source subscribed: a hook downstream of a `subscribeOn` boundary may run on the thread calling subscribe. Observe directly inside `Flux.defer`, `Mono.fromCallable`, or close to the source when verifying.

## 6. Runnable Java 17+ Example: Seeing Which Scheduler the Source Subscribes On

The program below keeps output deterministic by printing only **the result of checking the thread name prefix**, rather than relying on exact thread names or timing. It also proves that assembly does not trigger the source.

Create a Gradle project with `build.gradle`:

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

application {
    mainClass = 'SubscribeOnDemo'
}
~~~

Create `src/main/java/SubscribeOnDemo.java`:

~~~java
import java.util.List;
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

public final class SubscribeOnDemo {
    public static void main(String[] args) {
        Scheduler sourceScheduler = Schedulers.newSingle("source-worker");

        try {
            Flux<Integer> pipeline = Flux.defer(() -> {
                System.out.println("source subscribed");
                boolean onWorker = Thread.currentThread()
                    .getName().startsWith("source-worker-");
                System.out.println("source on worker: " + onWorker);
                return Flux.range(1, 3);
            })
            .map(value -> {
                boolean onWorker = Thread.currentThread()
                    .getName().startsWith("source-worker-");
                System.out.println("map " + value
                    + " on worker: " + onWorker);
                return value * 10;
            })
            .subscribeOn(sourceScheduler);

            System.out.println("after assembly");
            List<Integer> values = pipeline.collectList().block();
            System.out.println("result=" + values);
        } finally {
            sourceScheduler.dispose();
        }
    }
}
~~~

Run with `gradle run --quiet`, or `./gradlew run --quiet` if Gradle Wrapper is present.

With `Flux.range` and the dedicated single scheduler, stdout:

~~~text
after assembly
source subscribed
source on worker: true
map 1 on worker: true
map 2 on worker: true
map 3 on worker: true
result=[10, 20, 30]
~~~

Explaining the results:

1. `Flux.defer` takes a publisher **factory**. The factory does not run at assembly, so the first line is `after assembly`.
2. `collectList().block()` creates a new subscription. `subscribeOn(sourceScheduler)` switches upstream subscription to a worker whose name starts with `source-worker-`.
3. The `defer` factory prints `source subscribed` and confirms it is on the worker.
4. `Flux.range(1,3)` emits synchronously; `map` also receives the three elements on the worker and multiplies them by 10.
5. `collectList()` puts the three values into a list; `block()` makes **main wait** until the result is ready. Do not use `block()` in WebFlux handlers/reactive threads.
6. `Schedulers.newSingle(...)` creates a dedicated scheduler for the demo; `dispose()` frees resources afterward. For Reactor-provided shared schedulers like `Schedulers.boundedElastic()`, applications should not arbitrarily dispose them just because one request finished.

Experiment: move `.subscribeOn(sourceScheduler)` right after `Flux.defer(...)`. In this synchronous example, the source still runs on the worker and the observed output matches above. If replaced with `publishOn(sourceScheduler)` placed after `map`, the source thread differs: `publishOn` only changes the signal-emitting context **after its position**.

## 7. Comparison with `publishOn`

Both operators take a `Scheduler`, but solve different problems:

| Criterion | `subscribeOn(scheduler)` | `publishOn(scheduler)` |
| --- | --- | --- |
| Primary point of effect | Subscription/request flow going upstream | `onNext`/terminal signals going downstream |
| Position in chain | Affects source subscription from its position upstream; place near source for clarity | Affects from its position downstream until another thread-switching boundary |
| Typical use | Selecting thread for synchronous sources, legacy blocking operations | Switching processing context for subsequent operators |
| Runs pipeline before subscribing? | No | No |
| Automatically parallelizes elements? | No | No |
| Turns blocking I/O into non-blocking? | No | No |
| Scheduling overhead? | May schedule subscribe/request | Adds an asynchronous boundary, queue/prefetch depending on overload |

Combined example (snippet with `Flux` and `Schedulers` imports):

~~~java
Flux<String> output = Flux.range(1, 4)
    .doOnNext(i -> log("source-stage", i))
    .subscribeOn(Schedulers.boundedElastic())
    .map(i -> i * 10)
    .publishOn(Schedulers.parallel())
    .map(i -> "value-" + i)
    .doOnNext(s -> log("downstream-stage", s));
~~~

Here `log(...)` is an application-provided illustration helper; the snippet is **not a self-compiling Java class**. The synchronous source and `map(i -> i * 10)` before `publishOn` typically run on a `boundedElastic` worker. `map(i -> "value-" + i)` and `doOnNext` after `publishOn` receive signals on a worker selected from `parallel`.

Do not conclude that all `source-stage` logs are guaranteed to print completely before all `downstream-stage` logs. `publishOn` introduces an async boundary so worker scheduling can interleave logs; preserving `onNext` order within a subscription does not mean **all logs across threads** appear in strict lockstep.

**Case where `publishOn` sits after a blocking source:**

~~~java
Mono<String> p = Mono.fromCallable(() -> legacy.readBlocking())
    .publishOn(Schedulers.boundedElastic());
~~~

`publishOn` is placed **after** the Callable, so it is not the standard solution to move the blocking call itself off the subscribing thread. For a synchronous blocking source, choose `fromCallable(...).subscribeOn(Schedulers.boundedElastic())`.

## 8. Why Does `subscribeOn` Often Pair with `fromCallable` and `boundedElastic`?

Some existing libraries offer only synchronous APIs, such as traditional JDBC, file-reading SDKs, synchronous REST clients, or heavy encryption/decompression. They can block the calling thread. If placed directly on a WebFlux event loop, a slow request can tie up the thread serving many other requests.

**Wrong timing:**

~~~java
// readBlocking() runs immediately when the Mono creation line is evaluated:
Mono<String> bad = Mono.just(legacy.readBlocking())
    .subscribeOn(Schedulers.boundedElastic());
~~~

Writing `subscribeOn` after `just` cannot relocate a blocking call that already completed during Java argument evaluation.

**Right timing and thread:**

~~~java
Mono<String> good = Mono
    .fromCallable(() -> legacy.readBlocking())
    .subscribeOn(Schedulers.boundedElastic());
~~~

- `fromCallable` **defers** the synchronous call until subscription.
- `subscribeOn(boundedElastic)` moves subscription and the callable onto a worker suitable for tasks that may wait on I/O.
- When the callable returns a value, it is emitted via `onNext`. When the callable returns `null`, Reactor completes empty; when it throws an exception, the error becomes an `onError` signal per contract.
- `boundedElastic` is a scheduler with **bounded** resources/queues; the synchronous operation still blocks one worker while running. This is a compatibility bridge for legacy libraries, not true non-blocking I/O.
- With non-blocking sources such as Reactor Netty reactive WebClient or reactive R2DBC database drivers, adding `boundedElastic` indiscriminately can introduce overhead with no benefit.

To distinguish: **`fromCallable` determines when the work runs**, whereas **`subscribeOn` determines which worker runs subscription/source**. Missing either can break the deferral or isolation goal.

## 9. Applying in a Spring WebFlux Controller

Suppose you must use a legacy DAO returning synchronous results:

~~~java
// Do NOT do this in a WebFlux handler:
@GetMapping("/users/{id}")
public Mono<UserDto> find(@PathVariable long id) {
    return Mono.just(legacyDao.findByIdBlocking(id));
}
~~~

When the handler is invoked, `findByIdBlocking(id)` executes **before the Mono even exists**. Changing the return type to `Mono<UserDto>` does not automatically make the DAO's I/O reactive/non-blocking.

A suitable way to wrap a legacy source:

~~~java
@GetMapping("/users/{id}")
public Mono<UserDto> find(@PathVariable long id) {
    return Mono.fromCallable(() -> legacyDao.findByIdBlocking(id))
        .subscribeOn(Schedulers.boundedElastic())
        .switchIfEmpty(Mono.error(
            new ResponseStatusException(HttpStatus.NOT_FOUND, "Not found")
        ));
}
~~~

This is a controller **snippet**: `@RestController`, `legacyDao`, `UserDto`, and Spring Web/Reactor imports are required; it is not a complete standalone Java file. In a real application:

1. The handler returns a quickly assembled `Mono`, without calling the DAO while creating the `Mono`.
2. Spring WebFlux performs subscription when handling the response.
3. `subscribeOn` switches subscription/source callable to `boundedElastic` to run the blocking DAO.
4. The value flows downstream for WebFlux to encode the response; if the DAO returns `null`, `Mono.fromCallable` completes empty and `switchIfEmpty` produces HTTP 404.
5. Exceptions from the DAO travel along `onError`; they do **not automatically** become 404 unless mapped explicitly.

You must still control timeouts, concurrent request limits, connection pool size, and connection hold times. Even though the event loop is not held by the DAO, too many blocking calls can overload the scheduler or the database.

**Do not use `block()` in a reactive controller**:

~~~java
// Wrong intent in a reactive request handler:
UserDto result = Mono.fromCallable(() -> legacyDao.findByIdBlocking(id))
    .subscribeOn(Schedulers.boundedElastic())
    .block();
~~~

`block()` blocks the **calling thread** waiting for the response; on a thread marked NonBlocking by Reactor, it can throw `IllegalStateException`. Keep composing with `map`, `flatMap`, `switchIfEmpty` and return the publisher.

## 10. Choosing the Right `Scheduler`

| Scheduler | Characteristics | When to use for subscription |
| --- | --- | --- |
| `Schedulers.boundedElastic()` | Suited for blocking-work compatibility, with bounded workers and queues | Legacy blocking sources like JDBC/synchronous HTTP |
| `Schedulers.parallel()` | Worker pool for short CPU work, should not block long | Pure CPU operators when context switching is desired |
| `Schedulers.single()` | Shared single worker for tasks needing serialization | Non-blocking work needing ordering on a single thread |
| `Schedulers.newSingle("name")` | Independent single-thread scheduler; application manages lifecycle | Demos, components needing a dedicated lifecycle |
| `Schedulers.immediate()` | Runs immediately on calling thread, no actual worker switch | When deliberately not switching threads; unsuitable for isolating blocking I/O |

**`subscribeOn(Schedulers.parallel())` does not turn every `map` into parallel computation.** It chooses the worker where subscription/source runs. To process independent items in parallel, consider `flatMap(item -> Mono.fromCallable(() -> compute(item)).subscribeOn(...), concurrency)`, while explicitly sizing concurrency, ordering, and resource cost; that is a separate design concern.

For example, sharing a single `Schedulers.newSingle(...)` does not mean "one distinct thread per subscription": subscriptions can share the worker belonging to that single-thread scheduler. Manage the scheduler object's lifecycle if you create it yourself, and avoid creating a new scheduler **for every HTTP request** just to call a blocking DAO.

Some operators have their own schedulers (for example timer/interval defaults to an appropriate scheduler), and reactive I/O libraries control their own event loops. `subscribeOn` should not be viewed as a tool that unconditionally overrides every thread chosen downstream or by third parties.

## 11. Request/Backpressure Also Relates to `subscribeOn`

The Reactive Streams specification uses `Subscription.request(long n)` so a subscriber grants permission to emit data. Per the Reactor API, the `subscribeOn(Scheduler)` overload executes `subscribe`, `onSubscribe`, and normally dispatches `request` on the scheduler's worker. Thus it can affect not only when the source initializes, but also how requests travel to the source.

**However:** do not read a single `doOnRequest(n)` log and infer the whole pipeline always lives on that worker. Operators such as `publishOn`, `buffer`, `flatMap`, and `limitRate` can hold queues, prefetch, and reshape request sizes/paths. When debugging, place `doOnRequest` near the source, log both thread name and `n`, and correlate with actual boundaries.

There is an advanced overload:

~~~java
Flux<T> sourceOnWorker = source.subscribeOn(scheduler, false);
~~~

This is a **generic snippet**, assuming `T`, `source`, and `scheduler` are defined. The parameter `requestOnSeparateThread=false` instructs Reactor **not to force request signals to be scheduled on that worker** as the default overload does. The Reactor API notes a specific scenario: an eager/blocking `Flux.create` source can hold the scheduler thread in an emission loop while requests queue up on that same worker, causing a progress deadlock; this overload can resolve that kind of source.

**Do not add `false` by default for every source.** That decision depends on how the source executes, whether it is blocking/eager, and backpressure requirements; most code should simply use `subscribeOn(scheduler)`.

## 12. Debugging Execution Flow: Observing at the Right Places

Useful hooks:

- `doFirst(() -> ...)`: runs before the source is subscribed to; multiple `doFirst` hooks in a chain execute in **reverse order** of declaration because subscription travels from downstream to upstream.
- `doOnSubscribe(subscription -> ...)`: observes when subscription passes through a point in the chain; placement before/after `subscribeOn` determines which thread is observed.
- `doOnRequest(n -> ...)`: observes request batches passing through the stage under inspection.
- `doOnNext(value -> ...)`: observes data signals emitted through the stage; which thread this callback runs on depends on the source and async boundaries.
- `doOnError`, `doFinally`, `doOnCancel`: observe termination/cancellation.

Example logging near the source (snippet; requires `Flux` and `Schedulers` imports):

~~~java
Flux<Integer> p = Flux.defer(() -> {
        System.out.println("source subscribed on "
            + Thread.currentThread().getName());
        return Flux.range(1, 3);
    })
    .doOnRequest(n -> System.out.println(
        "source-side request " + n
        + " on " + Thread.currentThread().getName()))
    .subscribeOn(Schedulers.boundedElastic())
    .doOnNext(i -> System.out.println(
        "next " + i
        + " on " + Thread.currentThread().getName()));
~~~

The snippet only **assembles** `p` and prints nothing until subscribed to. On subscription, logs show where source initialization and source-side requests occur; do not rely on the exact order/count of every `request` line in a complex pipeline if prefetch-shaping operators exist. `subscribe()` often returns early for async pipelines: a console program can exit before logs appear unless completion is awaited properly.

When reading a thread report, do not merely log `Thread.currentThread().getName()` in a final `map` and conclude the source ran on that thread. Observe **right at the source**, before and after any `publishOn` or async boundary, and note the log's position in the chain.

## 13. Does Subscription Always Re-Run the Source?

For cold sources built with `Mono.fromCallable` or `Flux.defer`, **each subscription** typically re-executes the source:

~~~java
Mono<String> p = Mono.fromCallable(() -> legacy.load())
    .subscribeOn(Schedulers.boundedElastic());

p.subscribe();
p.subscribe();
~~~

The snippet assumes `legacy.load()` is valid. Two subscriptions can invoke `load()` **twice**. `subscribeOn` does not cache results, does not turn a source into a singleton, and does not prevent duplicate side effects. With `retry`, resubscribing can also re-run the source.

Conversely:

~~~java
String value = legacy.load(); // runs before the Mono is created
Mono<String> p = Mono.just(value)
    .subscribeOn(Schedulers.boundedElastic());
~~~

No matter how many subscribers exist, the expression `legacy.load()` in this line already ran once **at assembly**. `subscribeOn` only affects subscriptions to the publisher holding the already-captured value. If you need "execute once and share" semantics, choose an appropriate cache/share policy and data lifecycle rather than expecting that from a scheduler.

With hot/broadcast sources, subscriptions may observe signals from an emission process that started independently of them. `subscribeOn` does not shift the thread of an external producer invoking a callback or `Sinks.Many.tryEmitNext(...)`. Publishers with their own async sources may also emit signals from the source's own thread, even if subscription occurred on another worker.

## 14. Automated Testing: Proving Assembly Did Not Run It and Worker Did

Verify using controlled state and thread names, rather than using `Thread.sleep` to guess at the scheduler. Continuing the Gradle project from section 6: replace the **dependencies block** with:

~~~groovy
dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.8'
    testImplementation 'io.projectreactor:reactor-test:3.8.8'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.2'
}

test {
    useJUnitPlatform()
}
~~~

Create `src/test/java/SubscribeOnTest.java`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class SubscribeOnTest {
    @Test
    void sourceRunsOnChosenWorkerOnlyAfterSubscribe() {
        Scheduler scheduler = Schedulers.newSingle("test-source");
        AtomicInteger calls = new AtomicInteger();
        AtomicReference<String> sourceThread = new AtomicReference<>();

        try {
            Mono<Integer> source = Mono.fromCallable(() -> {
                sourceThread.set(Thread.currentThread().getName());
                return calls.incrementAndGet();
            }).subscribeOn(scheduler);

            assertEquals(0, calls.get()); // assembly has not executed the source yet

            StepVerifier.create(source)
                .expectNext(1)
                .verifyComplete();

            assertEquals(1, calls.get());
            assertTrue(sourceThread.get().startsWith("test-source-"));

            StepVerifier.create(source)
                .expectNext(2)
                .verifyComplete();

            assertEquals(2, calls.get()); // new subscription
        } finally {
            scheduler.dispose();
        }
    }

    @Test
    void justEvaluatesArgumentBeforeSubscription() {
        AtomicInteger calls = new AtomicInteger();
        Mono<Integer> source = Mono.just(calls.incrementAndGet());

        assertEquals(1, calls.get());

        StepVerifier.create(source)
            .expectNext(1)
            .verifyComplete();

        StepVerifier.create(source)
            .expectNext(1)
            .verifyComplete();

        assertEquals(1, calls.get()); // already captured value 1
    }
}
~~~

Run `gradle test`. Both tests should PASS:

- The first test verifies the source did not run at assembly, executed on a worker named `test-source-...`, and each independent subscription re-invokes the source.
- The second test verifies `Mono.just(calls.incrementAndGet())` evaluated its value at assembly and does not re-evaluate the expression on subscribe.

Because `StepVerifier.verifyComplete()` awaits the completion signal, the test checks post-execution state without sleeping an arbitrary duration. This test does not try to measure "how much faster"; that is a separate benchmark/performance concern.

## 15. Common Misconceptions

| Wrong claim | What actually happens | Correct usage |
| --- | --- | --- |
| "Adding `subscribeOn` runs the source immediately" | It only configures how subscription will occur | An actual subscription is required |
| "Position of `subscribeOn` means only operators after it run on the worker" | Subscription flows backward to the source, so for synchronous sources emissions from the source are governed by `subscribeOn` even if written after `map` | Place near the source for clarity; do not interpret it like `publishOn` |
| "`subscribeOn` splits each element across different threads" | It selects the worker for subscription/source, without creating per-element parallelism | Use a suitable concurrency model if parallelism is needed |
| "`Mono.just(jdbc.call()).subscribeOn(boundedElastic)` is safe" | `jdbc.call()` runs before `just` | `Mono.fromCallable(() -> jdbc.call()).subscribeOn(boundedElastic)` |
| "`publishOn` after `fromCallable` stops the source from blocking the event loop" | `publishOn` switches downstream signals; the upstream Callable can still block the subscribing thread | Use `subscribeOn` for blocking sources |
| "`subscribeOn` re-runs a `just` value for each subscriber" | `just` holds an already-computed value | To re-invoke on subscribe: `fromCallable`/`defer` |
| "Chaining multiple `subscribeOn` switches threads repeatedly" | Usually just adds switching/overhead, unlike multiple `publishOn` calls | One clear `subscribeOn` for the source |
| "Using `parallel()` scheduler processes every item in parallel" | A scheduler pool differs from splitting work across multiple rails/tasks | Configure concurrency deliberately |
| "`subscribeOn` overrides the thread of every hot/async source" | External sources/callbacks have their own emission contexts | Identify the producer's thread; use `publishOn` when switching downstream |
| "`boundedElastic` makes JDBC non-blocking" | JDBC still blocks a worker, and queues/resources are bounded | Limit load, set timeouts, prefer reactive drivers when appropriate |
| "Since `subscribeOn` is used, `block()` is fine in a controller" | `block()` still blocks the calling thread and may be rejected by Reactor on NonBlocking threads | Return the publisher and compose with operators |
| "`subscribeOn` guarantees cancel stops I/O immediately" | Cancellation does not guarantee interrupting every blocking API | Configure timeout/cancel in the underlying API and manage resources |

## 16. Practice Exercises with Solutions

**Exercise 1.** In `Flux.range(1,3).map(x -> x+1).subscribeOn(scheduler)`, does `map` always run before `subscribeOn` executes?

**Answer:** No. `map` is assembled first, but its callback only processes elements once the source is subscribed to and emits data. With a synchronous `Flux.range` source, emission/`map` typically happens on the worker selected by `subscribeOn`.

**Exercise 2.** Does moving `subscribeOn` from right after `Flux.range` to after two synchronous `map` operators move the source back to the thread calling `subscribe()`?

**Answer:** Not in this simple pipeline. `subscribeOn` intervenes in the subscription traveling backward to the source. However, placing it near the source is easier to read, and asynchronous operators may follow their own thread rules.

**Exercise 3.** When does `Mono.just(service.loadBlocking()).subscribeOn(boundedElastic)` run `loadBlocking`?

**Answer:** When Java evaluates the argument to `Mono.just` at assembly, before subscription. To defer and schedule it on a worker, use `Mono.fromCallable(service::loadBlocking).subscribeOn(Schedulers.boundedElastic())`.

**Exercise 4.** A pipeline has `subscribeOn(boundedElastic)` followed by `publishOn(parallel)`. Where does a synchronous `map` **after** `publishOn` usually run?

**Answer:** On a `parallel` worker because `publishOn` switches signals downstream. `subscribeOn` still governs upstream subscription/source.

**Exercise 5.** You use `Mono.fromCallable(call).subscribeOn(scheduler)` and call `subscribe()` twice. Can you assume `call` runs once and is cached?

**Answer:** No. With this cold source, each subscription can re-invoke the Callable. Design idempotency or a cache/share policy if side effects exist and different semantics are desired.

**Exercise 6.** Why is a log at the end of a pipeline showing thread `parallel-1` insufficient to claim the source also ran on `parallel-1`?

**Answer:** Between the source and the log there could be `publishOn`, timers, network drivers, or asynchronous publishers. To know which thread subscribed to the source, log directly inside `defer`/`fromCallable` or a hook near the source.

**Exercise 7.** Does `subscribeOn(Schedulers.boundedElastic())` make a 3-second JDBC call run in 3 milliseconds?

**Answer:** No. The call remains synchronous I/O blocking a worker while waiting. The scheduler isolates the event loop from the blocking call; it does not shorten the driver's I/O execution time.

## 17. Takeaways and References

- **`subscribeOn` schedules subscription toward the source**, usually affecting both the thread running a synchronous source and upstream requests.
- **`publishOn` is a thread-switching boundary for downstream data** at the point where it appears in the chain.
- **Assembly does not mean subscription.** `Mono.just(blockingCall())` already ran the blocking call beforehand; `fromCallable` or `defer` is needed to defer.
- **One `subscribeOn` near the source is usually enough**; multiple `subscribeOn` calls are not equivalent to multiple `publishOn` calls.
- **`boundedElastic` is for blocking compatibility**, not turning I/O into non-blocking and not automatically solving load limits.
- **The source thread is not always the thread of every `onNext`**; hot/async sources and other boundaries can actively change context.

Official documentation for further reading:

1. [Project Reactor Reference — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): how `subscribeOn`, `publishOn`, multiple scheduler switches, and recommended placement work.
2. [Project Reactor FAQ — How Do I Wrap a Synchronous, Blocking Call?](https://projectreactor.io/docs/core/release/reference/faq.html): the `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` pattern.
3. [Flux API — subscribeOn](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): contracts for `subscribeOn(scheduler)` and `subscribeOn(scheduler, requestOnSeparateThread)`, special scenario with `Flux.create` sources.
4. [Project Reactor — Backpressure and Ways to Reshape Requests](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html): `request(n)`, prefetch, and requests across operators.
5. [Spring Framework — WebFlux Reference](https://docs.spring.io/spring-framework/reference/web/webflux.html): how Spring WebFlux uses publishers and non-blocking I/O.
