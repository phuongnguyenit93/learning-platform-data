# Distinguishing Creating a Publisher from Wrapping an Already-Executed Blocking Call

## 1. The Core Problem

In Reactor and Spring WebFlux, **creating a `Mono`/`Flux` object does not mean the work inside it has not already run**. Java always evaluates method arguments before calling the method itself. Therefore:

~~~java
Mono<String> wrong = Mono.just(legacyClient.loadBlocking());
~~~

`legacyClient.loadBlocking()` runs **right when this Java line is executed**, before `Mono.just(...)` receives the result. If the call blocks I/O for 500 ms, the current thread has already waited 500 ms; the publisher merely wraps **an already-obtained value**. Even if nobody has called `subscribe()`, the blocking task has already happened.

A better way to create a deferred-execution source:

~~~java
Mono<String> source = Mono.fromCallable(() -> legacyClient.loadBlocking())
    .subscribeOn(Schedulers.boundedElastic());
~~~

Here the lambda holds **the work to be done**. When creating `source`, the blocking call has not run yet. Only when there is a subscriber does Reactor execute the `Callable`; `subscribeOn(Schedulers.boundedElastic())` schedules subscription/the blocking source onto a scheduler suited for I/O-waiting tasks.

**Three questions that must be separated:**

1. **When** does the work actually start: immediately when building the publisher or upon subscribe?
2. **On which thread** does it run: the current method's calling thread, the subscribing thread, or a scheduler worker?
3. **Is it blocking**: a synchronous JDBC/SDK operation still blocks a thread, even when placed on `boundedElastic`; only genuinely non-blocking I/O APIs have non-blocking characteristics at the I/O layer.

This lesson belongs to the topic **Creating Data Sources**: the goal is to choose the right factory/source for the work to be performed, not just change return types to `Mono` or `Flux`.

## 2. Three Points in Time: Method Execution, Assembly, Subscription

**Assembly** is when the program constructs the chain of publishers/operators. **Subscription** is when a subscriber subscribes and triggers work for a cold source. Both must be distinguished from **argument evaluation** time in Java.

~~~text
Code line                           Assembly          Subscription
    |
    |-- legacy.loadBlocking() ------> RUNS, BLOCKS
    |-- Mono.just(result) ----------> creates Mono wrapping result
    |                                         |
    |                                         +----> emits existing result
    |
    |-- Mono.fromCallable(() -> ...) -> creates Mono, does NOT call legacy yet
                                              |
                                              +----> CALLS legacy, may BLOCK
~~~

Two code sequences differ in execution order:

~~~java
// A: execute first, then wrap the result
String value = legacyClient.loadBlocking();
Mono<String> a = Mono.just(value);

// B: hold the action to execute when subscription happens
Mono<String> b = Mono.fromCallable(() -> legacyClient.loadBlocking());
~~~

Before subscribing:

- `a`: the blocking call has already run once; the result sits inside the publisher.
- `b`: the blocking call has not run yet; it will run when subscribed.
- **However, `b` does not automatically run on a separate thread.** If subscribe happens on an event-loop and no scheduler is configured, the `Callable` can block that event-loop itself.

Therefore you must control both **when** and **where** execution takes place.

## 3. Why Wrapping a Value with `Mono.just` Is Wrong When You Want to Defer Blocking

Java evaluates arguments before the function call:

~~~java
Mono.just(legacyClient.loadBlocking())
~~~

is equivalent in timing to:

~~~java
String result = legacyClient.loadBlocking(); // executes, may wait here
Mono<String> mono = Mono.just(result);       // merely wraps result
~~~

We cannot “fix” timing that has already happened by adding a scheduler after `just`:

~~~java
// WRONG if expecting loadBlocking to move to boundedElastic:
Mono<String> mono = Mono.just(legacyClient.loadBlocking())
    .subscribeOn(Schedulers.boundedElastic());
~~~

`subscribeOn` affects **the publisher's subscription**, while `loadBlocking()` already ran while **evaluating the argument to build `Mono.just`**. That I/O call cannot be moved retroactively to another point in time.

A subtler-looking mistake:

~~~java
String value = legacyClient.loadBlocking(); // already blocked before creating publisher

Mono<String> mono = Mono.fromCallable(() -> value)
    .subscribeOn(Schedulers.boundedElastic());
~~~

`fromCallable` in this case only defers **returning the already-computed variable**, not `loadBlocking()`. Rule to remember: **put the blocking call itself inside the lambda/callable**, not its result inside the lambda.

Using `Mono.just(value)` is completely right when `value` is an existing value or cheap constant, such as `Mono.just("ok")` or `Mono.just(configValue)`. The problem is not with the `just` API; the problem lies in calling a thread-blocking I/O operation to produce its argument.

## 4. Publisher Creation Methods and Execution Semantics

| Source Creation | Work Execution Timing | Characteristics |
| --- | --- | --- |
| `Mono.just(value)` | `value` was computed before calling `just` | Suits pre-existing values, replays that value to subscribers |
| `Mono.just(blockingCall())` | `blockingCall()` runs when building the publisher | Does not defer blocking, can block the event-loop |
| `Mono.fromCallable(() -> blockingCall())` | Calls `Callable` on subscribe | Defers operation, each subscription can re-invoke |
| `Mono.fromSupplier(() -> calculate())` | Calls `Supplier` on subscribe | Defers computation; `Supplier` does not declare checked exceptions |
| `Mono.defer(() -> createMono())` | Calls factory returning a `Mono` per subscription | Defers even the decision of choosing/creating the publisher |
| `Mono.fromRunnable(() -> sideEffect())` | Runs `Runnable` on subscribe then completes without value | For `void`-returning operations |
| `Flux.fromIterable(legacy.findAllBlocking())` | `findAllBlocking()` runs immediately to build the argument | Wraps an already-fetched list; creating `Flux` does not defer the query |
| `Flux.defer(() -> Flux.fromIterable(legacy.findAllBlocking()))` | Calls `findAllBlocking()` on subscribe | Defers the query, but needs a scheduler if the query blocks |

**`Mono.fromCallable`** fits synchronous APIs best when they return **one** result (or `null`) and may throw checked exceptions. If Callable returns `null`, Reactor completes `Mono.empty()`; if it throws an exception, the subscriber receives `onError`.

**`Mono.defer`** is used when you need to defer creating another publisher; for example, reading info at subscription time and deciding to return `Mono.empty()`, `Mono.error(...)`, or another source:

~~~java
Mono<String> dynamic = Mono.defer(() -> {
    if (featureEnabled()) {
        return Mono.just("enabled");
    }
    return Mono.empty();
});
~~~

The example is a snippet, assuming `featureEnabled()` exists. If the factory inside `defer` calls blocking I/O, deferring timing alone is not enough: you still must route the subscription to `boundedElastic` or switch to a non-blocking I/O API. For a single-value blocking source, `fromCallable` is usually easier to read than `defer(() -> Mono.just(blockingCall()))`.

**Note on cold/hot terminology:** `fromCallable` and `defer` are sources that generate data per subscription. `Mono.just` captures a value when creating the publisher, which Reactor often uses to illustrate a “hot/captured” nuance at assembly time; however, `just` can still deliver the same value to multiple subscribers and does not mean it emits in the background on its own or acts as a running broadcast stream.

## 5. Complete Java 17+ Example: Seeing Exactly When Calls Run

Use the following program to verify execution counts. `Thread.sleep(30)` merely simulates a blocking API; in a real app this could be JDBC, a synchronous HTTP client, or a file-reading SDK.

Create `build.gradle`:

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
    mainClass = 'PublisherTimingDemo'
}
~~~

Create `src/main/java/PublisherTimingDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public final class PublisherTimingDemo {
    private static final AtomicInteger CALLS = new AtomicInteger();

    private static String blockingRead() throws InterruptedException {
        int invocation = CALLS.incrementAndGet();
        System.out.println("blockingRead call " + invocation);
        Thread.sleep(30); // simulate synchronous I/O
        return "data-" + invocation;
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("assemble eager");
        Mono<String> eager = Mono.just(blockingRead());

        System.out.println("assemble deferred");
        Mono<String> deferred = Mono
            .fromCallable(PublisherTimingDemo::blockingRead)
            .subscribeOn(Schedulers.boundedElastic());

        System.out.println("calls after assembly=" + CALLS.get());

        System.out.println("eager first=" + eager.block());
        System.out.println("eager second=" + eager.block());

        System.out.println("deferred first=" + deferred.block());
        System.out.println("deferred second=" + deferred.block());

        System.out.println("calls at end=" + CALLS.get());
    }
}
~~~

Run with `gradle run --quiet` or `./gradlew run --quiet` when a Gradle Wrapper is present. With this program, stdout is:

~~~text
assemble eager
blockingRead call 1
assemble deferred
calls after assembly=1
eager first=data-1
eager second=data-1
blockingRead call 2
deferred first=data-2
blockingRead call 3
deferred second=data-3
calls at end=3
~~~

Explaining each milestone:

1. Right after `assemble eager`, the argument to `Mono.just` is evaluated. `blockingRead()` runs call 1 **before the `eager` publisher exists**.
2. `Mono.fromCallable` stores only an action. After building both publishers, `CALLS` is still 1.
3. Both `eager.block()` calls subscribe to a publisher containing the same `data-1` value. They do not re-run `blockingRead`.
4. Each `deferred.block()` creates a new subscription. The Callable runs call 2 and then call 3, returning `data-2` and `data-3`. `subscribeOn(boundedElastic)` moves Callable execution onto an appropriate worker.
5. `block()` still makes the **main thread wait for the result** in this console demo. That is normal for observing sequentially, but **you must never call `block()` on a reactive processing thread on the WebFlux event-loop**.

Avoid using thread names or measured durations as “invariant” output of the example: the scheduler can vary the chosen thread and runtime; the invocation counts and printed order here are what should be verified.

## 6. Which Part Does `subscribeOn` Solve? Which Part Does `publishOn` Solve?

Two independent aspects:

- `fromCallable` / `defer`: defers **when** the work starts.
- `subscribeOn(Schedulers.boundedElastic())`: selects the **execution context for subscription and the upstream source**, preventing a synchronous blocking call from holding the event-loop serving other reactive tasks.

Pattern recommended by Reactor when integrating a blocking synchronous API is needed:

~~~java
Mono<Result> publisher = Mono
    .fromCallable(() -> blockingApi.read())
    .subscribeOn(Schedulers.boundedElastic());
~~~

`Result` and `blockingApi` are application types/variables, so this is an illustrative snippet. Place `subscribeOn` right after the source for readability and so other operators do not confuse readers about the thread-switching point. `subscribeOn` itself **does not trigger subscribe**; work only starts when there is an actual subscription.

Compare three situations:

~~~java
// RIGHT: both defers the blocking call and picks an appropriate scheduler.
Mono<String> a = Mono.fromCallable(() -> legacy.readBlocking())
    .subscribeOn(Schedulers.boundedElastic());

// WRONG for deferring: legacy.readBlocking() already ran earlier.
Mono<String> b = Mono.just(legacy.readBlocking())
    .subscribeOn(Schedulers.boundedElastic());

// WRONG for offloading the blocking source itself:
// publishOn afterward only switches context for downstream signals/operators.
Mono<String> c = Mono.fromCallable(() -> legacy.readBlocking())
    .publishOn(Schedulers.boundedElastic());
~~~

The three snippets above assume `legacy` already exists, and `readBlocking` returns String. With `c`, on normal subscription, the Callable before `publishOn` can still run on the subscribing thread, causing blocking. There are ways to place `publishOn` before a blocking operator, but **the clearest pattern for a synchronous source is `fromCallable(...).subscribeOn(...)`**.

`Schedulers.boundedElastic()` has bounded worker/task queue limits, used to isolate unavoidable blocking calls. It **does not turn JDBC or a synchronous HTTP client into non-blocking**. Each operation still occupies a worker while waiting; too many tasks can fill the queue and increase latency. `Schedulers.parallel()` and `Schedulers.single()` serve different workloads and are unsuitable for running long blocking I/O calls on those threads.

## 7. Real-World Mistake in a Spring WebFlux Controller

Suppose a controller is invoked on a reactive HTTP processing thread and uses a legacy DAO with a synchronous API:

~~~java
// Should not be used in a WebFlux controller:
@GetMapping("/users/{id}")
public Mono<UserDto> findUser(@PathVariable long id) {
    return Mono.just(legacyDao.findByIdBlocking(id));
}
~~~

When HTTP handling enters `findUser`, `legacyDao.findByIdBlocking(id)` is called **before the controller returns a publisher**. If this is a Netty event-loop thread, it can block serving other requests. Changing the return type from `UserDto` to `Mono<UserDto>` does not make the DAO call automatically asynchronous.

A more reasonable way to integrate the legacy API:

~~~java
@GetMapping("/users/{id}")
public Mono<UserDto> findUser(@PathVariable long id) {
    return Mono.fromCallable(() -> legacyDao.findByIdBlocking(id))
        .subscribeOn(Schedulers.boundedElastic())
        .switchIfEmpty(Mono.error(
            new ResponseStatusException(HttpStatus.NOT_FOUND, "User not found")
        ));
}
~~~

**This is a controller snippet**, which must be placed in a Spring WebFlux `@RestController`, with `legacyDao` and `UserDto` declared, and `Mono`, `Schedulers`, `GetMapping`, `PathVariable`, `ResponseStatusException`, `HttpStatus` imported. The snippet is not a self-compiling console program if taken alone.

Processing flow:

~~~text
HTTP enters controller
  -> quickly creates Mono.fromCallable(...).subscribeOn(...)
  -> returns publisher
  -> WebFlux subscribes
  -> boundedElastic executes synchronous DAO
  -> value or error propagates through Mono
  -> WebFlux completes HTTP response
~~~

If the DAO returns `null`, `Mono.fromCallable` completes empty; `switchIfEmpty` turns this case into HTTP 404. If the DAO throws an exception, the signal follows the `onError` branch for WebFlux/error handlers to process; that case is **not automatically** treated as 404.

**Do not call `mono.block()` in a controller** to “conveniently grab the value”. `block()` still blocks the calling thread; on threads marked non-blocking by Reactor, it can throw `IllegalStateException`. Keep composing with `map`, `flatMap`, `switchIfEmpty` and return the publisher to the framework.

## 8. The `Flux` Case: From an Existing List to a Source Needing a Query

When you have a list already prepared in RAM, `Flux.fromIterable(items)` makes sense. But if `items` is produced by a blocking call right inside the argument, creating the Flux still blocks:

~~~java
// legacyRepository.fetchAllBlocking() runs right here.
Flux<Item> eager = Flux.fromIterable(
    legacyRepository.fetchAllBlocking()
);
~~~

To defer the entire query and Flux initialization per subscriber:

~~~java
Flux<Item> deferred = Flux
    .defer(() -> Flux.fromIterable(
        legacyRepository.fetchAllBlocking()
    ))
    .subscribeOn(Schedulers.boundedElastic());
~~~

This is a **snippet** assuming `legacyRepository` has a synchronous method returning `Iterable<Item>`. Using `defer` is necessary to defer the call returning the list itself. Adding `subscribeOn` avoids executing this call on the event-loop. Do not confuse `Flux.fromIterable` with true paginated/streaming queries: if `fetchAllBlocking()` loads millions of records into RAM before returning the list, a lazily created publisher still **does not** turn loading the whole dataset into low-memory streaming.

A `Flux.create` / callback adapter source also does not automatically make a legacy API non-blocking; how callbacks are invoked and the actual execution thread must be examined separately.

## 9. Once Work Has Started, a Wrapper Cannot Make It “Not Started Yet”

This rule also applies to `CompletableFuture`:

~~~java
// startRequestAsync() starts the work here.
CompletableFuture<String> future = startRequestAsync();

// The publisher may not be subscribed yet, but the future is already running.
Mono<String> wrapped = Mono.fromFuture(future);

// If each subscriber needs to launch its own future on subscribe:
Mono<String> deferred = Mono.defer(
    () -> Mono.fromFuture(startRequestAsync())
);
~~~

This is a snippet, assuming `startRequestAsync()` returns a `CompletableFuture<String>` already scheduled by an async API. Unlike a blocking call, a started Future may not block the current thread, but it is still a **side effect that has already occurred** before subscription. `fromFuture` taking an existing Future cannot reverse that Future's creation history.

Difference between **true async** and **offloading blocking to a worker**:

| Mechanism | Blocks a Thread Waiting for I/O? | Start Timing |
| --- | --- | --- |
| `Mono.just(blockingRead())` | Yes, immediately on the assembly thread | Before finishing building the Mono |
| `Mono.fromCallable(blockingRead)` without scheduler | Yes, typically on the subscribing thread | On subscribe |
| `Mono.fromCallable(blockingRead).subscribeOn(boundedElastic)` | Yes, but on an appropriate worker | On subscribe when the worker runs the task |
| `Mono.fromFuture(existingFuture)` | Depends on how the Future is created and executed | The Future may have already started |
| Publisher from a true reactive I/O driver (e.g., an appropriate reactive database driver) | Does not occupy a thread to block waiting for I/O | Per the driver's specific contract and mechanism |

Moving blocking work onto `boundedElastic` is a **compatibility workaround** when you cannot yet replace legacy APIs, not a way to turn a synchronous library into a true reactive driver.

## 10. Errors, `null`, and Repeated Subscriptions

### When Do Errors Appear?

~~~java
// If legacy.readBlocking() throws RuntimeException,
// the exception escapes when creating Mono, before any subscriber exists.
Mono<String> eager = Mono.just(legacy.readBlocking());

// If callable throws an exception, Reactor sends onError at subscription.
Mono<String> lazy = Mono.fromCallable(() -> legacy.readBlocking());
~~~

When the source is built with `fromCallable`, errors can be handled with `onErrorResume`, `onErrorMap`, or left to WebFlux's error handler. With `Mono.just(blockingCall())`, the exception already occurred before the publisher existed, so an `onErrorResume` operator attached after `just` cannot catch an error from evaluating the argument.

### What About Returning `null`?

- `Mono.just(null)` is invalid, throwing `NullPointerException` when creating the publisher.
- `Mono.justOrEmpty(value)` can emit a value or complete empty, but if `value` is produced by a blocking call, that call **still runs immediately**.
- `Mono.fromCallable(() -> legacy.lookup())` returning `null` will complete as `Mono.empty()`; use `switchIfEmpty` if a “not found” policy is needed.

### Each Subscription Can Re-run Side Effects

~~~java
Mono<String> lookup = Mono.fromCallable(() -> legacy.readBlocking())
    .subscribeOn(Schedulers.boundedElastic());

// Two subscriptions => in principle two calls to legacy.
lookup.subscribe();
lookup.subscribe();
~~~

If `retry` is used, a single subscription can execute the source multiple times on failure; if `repeat` or multiple subscribers exist, the source can also be called again. For operations with side effects such as **charging payments, sending emails, or writing data**, design idempotency and explicit retry semantics; do not assume “creating one Mono” means “executing once and only once”.

`cache()` can be used to share/retain results after the first subscription per operator semantics, but it alters data lifecycle and can cache error/empty signals as well; do not add `cache` merely to avoid duplicate execution without understanding business requirements and data freshness.

### Cancel/Timeout Does Not Automatically Interrupt All I/O

Cancelling a subscription or `timeout` stops waiting for results at the reactive layer, but **does not guarantee** that an already-launched synchronous I/O library will stop immediately. It still depends on interrupts, driver/client timeouts, library cancellation support, and task state. With legacy APIs, configuring connection/read timeouts, managing connection pools, and properly opening/closing resources remain essential.

## 11. Automated Testing of Execution Timing

You can test the difference without depending on machine speed or thread schedulers. Keep the main example in section 5, and replace the `dependencies` block in `build.gradle` with the following (keeping `plugins`, `repositories`, `application` unchanged):

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

Create `src/test/java/LazySourceTest.java`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class LazySourceTest {
    @Test
    void fromCallableExecutesOnEachSubscription() {
        AtomicInteger calls = new AtomicInteger();
        Mono<Integer> source = Mono.fromCallable(calls::incrementAndGet);

        assertEquals(0, calls.get());

        StepVerifier.create(source).expectNext(1).verifyComplete();
        assertEquals(1, calls.get());

        StepVerifier.create(source).expectNext(2).verifyComplete();
        assertEquals(2, calls.get());
    }

    @Test
    void justCapturesAlreadyComputedValue() {
        AtomicInteger calls = new AtomicInteger();
        Mono<Integer> source = Mono.just(calls.incrementAndGet());

        assertEquals(1, calls.get());

        StepVerifier.create(source).expectNext(1).verifyComplete();
        StepVerifier.create(source).expectNext(1).verifyComplete();

        assertEquals(1, calls.get());
    }
}
~~~

Run `gradle test`. Two passing tests demonstrate:

- `fromCallable` did not invoke the Supplier/Callable at assembly; after two subscriptions, the counter reached 2.
- `just` received the expression result evaluated at assembly; two subscriptions still emit the same value; the counter does not increase further.

This tests timing/semantics. It does not need real blocking calls, avoiding timed waits or random scheduler dependencies. To verify a WebFlux app avoids blocking the event-loop, you also need to observe actual threads, latency under load, BlockHound (if applicable), and the drivers/clients in use.

## 12. Choosing a Design by Scenario

| Scenario | Approach |
| --- | --- |
| Cheap value, already in RAM, no need to recompute | `Mono.just(value)` or `Mono.justOrEmpty(value)` |
| A pure computation, needs to run on subscribe | `Mono.fromSupplier(() -> compute())` |
| A synchronous blocking call returning a result, may throw exceptions | `Mono.fromCallable(() -> legacy.call()).subscribeOn(Schedulers.boundedElastic())` |
| Need to decide/create another publisher at subscribe time | `Mono.defer(() -> choosePublisher())`, plus scheduler if blocking inside |
| Source returns `void` and must be triggered on subscribe | `Mono.fromRunnable(() -> legacy.doWork())`, plus scheduler if blocking |
| List already in RAM | `Flux.fromIterable(items)` |
| Must call legacy to load list before emitting | `Flux.defer(() -> Flux.fromIterable(legacy.fetchAll())).subscribeOn(Schedulers.boundedElastic())`; consider pagination to avoid loading everything |
| Native async/non-blocking API available | Use an appropriate async publisher/adapter to avoid holding threads waiting on I/O |
| Already have a running Future | `Mono.fromFuture(existingFuture)` only wraps the Future; use `defer` if you want to defer launching the Future |

For blocking APIs that cannot yet be eliminated in production, also consider concurrency rates, database connection pool limits, timeouts, backpressure, retry/idempotency, and task queuing capacity. Using `boundedElastic` protects the event-loop but still incurs resource costs and can saturate if upstream exceeds capacity.

## 13. Common Mistakes and Fixes

| Mistake | Why It Is Wrong | Fix |
| --- | --- | --- |
| “Returning `Mono` makes it non-blocking” | Return type does not change the I/O mechanism already run | Identify exact blocking calls and execution threads |
| `Mono.just(dao.readBlocking())` in WebFlux | `dao.readBlocking()` runs immediately inside the handler | `Mono.fromCallable(() -> dao.readBlocking()).subscribeOn(boundedElastic)` |
| `fromCallable(() -> cachedValue)` after already calling DAO | Only defers reading the variable, not the DAO | Put **the DAO call** inside the callable |
| Adding `subscribeOn` after `Mono.just(blockingCall())` | The blocking task already finished before the publisher existed | Defer the work first, then pick a scheduler |
| Using `publishOn` after a blocking source | The upstream source can still run on the subscribing thread | Use `subscribeOn` for the source |
| Using `Mono.defer` without choosing a scheduler | Deferred timing, did not handle blocking thread | `defer(...).subscribeOn(boundedElastic)` or `fromCallable` |
| Calling `block()` in a reactive controller | Can block event-loop/throw on NonBlocking threads | Compose with operators and return Mono/Flux |
| Thinking `fromCallable` runs only once | It is a cold source, usually re-running per subscription | Consider idempotency, retry, and intentional caching |
| Thinking `timeout` always aborts blocking JDBC | Reactive cancellation does not guarantee stopping the driver | Configure timeouts/cancellation at the I/O layer |
| Thinking `boundedElastic` scales serving capacity infinitely | Workers and queues are bounded | Set concurrency limits, protect pools, and measure latency |

## 14. Self-Check Questions

**Question 1.** A WebFlux controller returns `Mono.just(jdbcDao.find(id))`. If `find` waits on the database for 2 seconds, can the controller return the publisher immediately?

**Answer:** No. Java must run `jdbcDao.find(id)` first to evaluate the argument to `Mono.just`, so the method blocks for about 2 seconds (assuming no error). A scheduler attached after `just` does not reverse this timing.

**Question 2.** Using `Mono.fromCallable(() -> jdbcDao.find(id))` without `subscribeOn`. Is it non-blocking yet?

**Answer:** No. The call is deferred until subscription, but when it runs it is still synchronous blocking I/O on the subscribing thread (unless another scheduling mechanism is applied externally).

**Question 3.** `Mono.just(service.load())` has been created; then three subscribers arrive. How many times does `service.load()` run due to that publisher creation statement?

**Answer:** Once while creating the publisher. All three subscribers typically receive the captured value; not three loads.

**Question 4.** With `Mono.fromCallable(service::load)`, three independent subscriptions, and no `cache`, how many times does `load` run?

**Answer:** Three times if the subscriptions execute normally (not cancelled before Callable runs). Each subscription triggers the cold source's Callable.

**Question 5.** `Mono.fromCallable(() -> legacy.lookup())` returns `null`. What signal reaches downstream?

**Answer:** `onComplete` with no `onNext`; in Reactor, `Mono.fromCallable` treats `null` as empty. You can use `switchIfEmpty` to provide a default value or appropriate error.

**Question 6.** Does `Mono.fromFuture(startAsync())` guarantee work starts only after subscription?

**Answer:** No. `startAsync()` executes when evaluating the argument for `fromFuture`. If it needs to start on subscription, use a deferred factory such as `Mono.defer(() -> Mono.fromFuture(startAsync()))`.

## 15. Takeaways and Standard References

**Decision rules:**

- **Value already available:** use `just`.
- **Need to defer an action producing a value:** use `fromCallable` / `fromSupplier`.
- **Need to defer choosing or building an entire publisher:** use `defer`.
- **Deferred action is still blocking:** add `subscribeOn(Schedulers.boundedElastic())` for blocking sources, or prefer truly non-blocking reactive APIs.
- **Action already executed before assembly:** wrapping the result in `Mono`/`Flux` cannot turn it into deferred work.

References:

1. [Project Reactor FAQ — How Do I Wrap a Synchronous, Blocking Call?](https://projectreactor.io/docs/core/release/reference/faq.html) — the `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` pattern.
2. [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html) — difference between `subscribeOn` / `publishOn`, `boundedElastic`, and resource limits.
3. [Project Reactor — Hot Versus Cold](https://projectreactor.io/docs/core/3.7.0/reference/advancedFeatures/reactor-hotCold.html) — `Mono.just` captures data at assembly, `defer` runs per subscription.
4. [Reactor Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html) — contract of `just`, `fromCallable`, `defer`, `fromFuture`.
5. [Spring WebFlux Reference](https://docs.spring.io/spring-framework/reference/web/webflux.html) — reactive programming in Spring's HTTP stack.
