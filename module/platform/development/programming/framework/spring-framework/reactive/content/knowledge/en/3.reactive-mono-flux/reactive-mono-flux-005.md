# Distinguishing Pipeline Assembly from Execution at Subscription (Mono and Flux)

## 1. Goal and Core Intuition

When reading **Project Reactor** code in Spring WebFlux, you must separate two distinct points in time:

1. **Assembly (pipeline construction):** the program calls methods such as `Mono.just(...)`, `map(...)`, `flatMap(...)`, `filter(...)`, and `doOnNext(...)` to create objects describing a processing chain. Calling **Java methods to construct the chain** happens immediately when that line of code runs.
2. **Subscription:** a subscriber attaches to the publisher via `subscribe(...)`, or the framework does the equivalent. Subscribing initiates interaction under the Reactive Streams protocol; the publisher can begin emitting signals and performing deferred work when it receives demand for data.

For common **cold publishers** such as `Mono.fromSupplier(...)` or `Flux.range(...)`, signal generation work is typically tied to **each subscription**. Therefore, *declaring a processing chain* does not mean *the chain has finished running*.

However, **"everything in `Mono`/`Flux` waits until `subscribe()`" is a false conclusion**. Java expressions evaluated during assembly can still compute values, call blocking APIs, print logs, or throw exceptions immediately. A hot publisher may already be emitting data before a new subscriber arrives; schedulers can also cause processing to happen asynchronously after `subscribe()` returns.

Keep three questions in mind when reading code:

- **Is this line merely creating a publisher, or is it calling a Java function immediately at assembly time?**
- **Is the data source created fresh for each subscription, or is it sharing/caching a single source?**
- **When subscription occurs, do signals run synchronously or get scheduled onto another thread?**

## 2. Three Timing Layers: Assembly, Subscribe, and Signal

| Phase | What Can Happen? | Example |
| --- | --- | --- |
| **Assembly time** | Executes Java expressions to build the pipeline, creates operator wrappers, validates arguments; arguments not inside deferred lambdas are evaluated immediately | `Mono.just(load())` calls `load()` immediately; `source.map(fn)` creates a new publisher |
| **Subscription time** | Subscriber subscribes, `onSubscribe` fires, cold sources may start; many source factories run when the source receives demand | `source.subscribe(...)`; `doOnSubscribe` callback |
| **Signal-processing time** | Source sends `onNext`, `onError`, `onComplete`; operators process and forward signals | Lambdas inside `map`/`flatMap`, `doOnNext` callback, `onErrorResume` on error |

Reactive Streams also includes **`request(n)`** after `onSubscribe`: the subscriber requests the number of elements it is ready to receive. Thus, saying "executes on subscription" is an introductory simplification; more accurately, **subscription establishes the pipeline, and then demand and source signals drive the actual work**. Some tasks run during `subscribe()`; others wait for `request(n)` or asynchronous signals.

Conceptual flow with a cold publisher:

```text
Create Mono/Flux -> attach map/filter/flatMap -> hold publisher (assembly)
                                                       |
                                                       | subscribe()
                                                       v
                                         onSubscribe -> request(n)
                                                       |
                                                       v
                                         source emits onNext/onError/onComplete
                                                       |
                                                       v
                                         operators process and forward signals
                                                       |
                                                       v
                                              subscriber receives result
```

In Reactor, `Mono<T>` represents at most one element, while `Flux<T>` represents 0..N elements. Both describe pipelines and follow subscription rules; a `Mono` does not automatically execute immediately upon creation just because it has at most one value.

## 3. Runnable Java 17+ Example: One Pipeline, Two Subscriptions

This is a standalone **class-level** Java program requiring the `reactor-core` dependency on the classpath. You can place `src/main/java/demo/AssemblyVsSubscriptionDemo.java` in a Spring Boot/WebFlux project (which already includes Project Reactor) and run `main` from your IDE. In a Spring Boot project using Gradle with dependency management via the Spring Boot BOM, `spring-boot-starter-webflux` already brings Reactor onto the classpath; there is no need to add a separate Reactor version.

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Mono;

public class AssemblyVsSubscriptionDemo {
    public static void main(String[] args) {
        AtomicInteger sourceRuns = new AtomicInteger();

        System.out.println("A: before assembly");

        Mono<Integer> pipeline = Mono.fromSupplier(() -> {
                    int run = sourceRuns.incrementAndGet();
                    System.out.println("source run #" + run);
                    return run;
                })
                .map(value -> {
                    System.out.println("map " + value);
                    return value * 10;
                })
                .doOnSubscribe(subscription ->
                        System.out.println("doOnSubscribe"));

        System.out.println("B: after assembly, runs=" + sourceRuns.get());

        pipeline.subscribe(value ->
                System.out.println("first subscriber: " + value));

        System.out.println("C: after first subscribe, runs=" + sourceRuns.get());

        pipeline.subscribe(value ->
                System.out.println("second subscriber: " + value));

        System.out.println("D: after second subscribe, runs=" + sourceRuns.get());
    }
}
```

**Exact stdout for this example** (synchronous source, no scheduler or external I/O):

```text
A: before assembly
B: after assembly, runs=0
doOnSubscribe
source run #1
map 1
first subscriber: 10
C: after first subscribe, runs=1
doOnSubscribe
source run #2
map 2
second subscriber: 20
D: after second subscribe, runs=2
```

Milestone-by-milestone explanation:

1. The `Mono.fromSupplier(...)` line and the `.map(...)` and `.doOnSubscribe(...)` calls **create the processing description**. They have not yet invoked the lambdas inside `fromSupplier` or `map`. Hence after assembly, `sourceRuns` is still 0.
2. The first `subscribe` establishes a subscription; `doOnSubscribe` is notified before the synchronous source emits a value; the supplier runs, returns 1, and `map` turns 1 into 10.
3. The second `subscribe` **re-subscribes to the same cold publisher**. The supplier runs again, returning 2, and `map` produces 20. The two subscribers do not share "the result of the first run".
4. In **this exact synchronous example**, `subscribe(...)` finishes processing before the next print line executes. Do not generalize that behavior to `WebClient`, `Mono.delay`, scheduled sources, or any asynchronous source.

A subtle point that causes confusion: even though the lambda inside `map` does not run during assembly, the function/lambda object and the `map` operator wrapper **have already been instantiated**. "Lazy" refers to signal emission and processing, **not denying every allocation cost or side effect of the Java code building the pipeline**.

## 4. How Does `Mono.just(...)` Differ from `fromSupplier(...)`, `fromCallable(...)`, and `defer(...)`?

### 4.1. `Mono.just(expression)`: Argument Expression Runs Immediately

Java must evaluate `expression` before invoking `Mono.just(...)`. Therefore:

```java
Mono<String> result = Mono.just(expensiveCall());
```

`expensiveCall()` runs **immediately at assembly time**, before any subscription, whether that call hits the network, JDBC, file I/O, or expensive computation. The `Mono.just` publisher holds the received value; each subscriber typically receives **that same value**. If `expensiveCall()` throws an exception, the error can occur **right while building the chain**, before there is a publisher to attach `onErrorResume` to. Passing `null` to `Mono.just` also throws at construction time instead of emitting `null`.

Conversely, `Mono.just("ready")` is completely reasonable: a pre-existing constant/value is reused across multiple subscriptions, with no expensive work needing deferral.

### 4.2. `Mono.fromSupplier(...)` and `Mono.fromCallable(...)`: Deferring the Call

```java
Mono<String> fromSupplier = Mono.fromSupplier(() -> expensiveCall());

Mono<String> fromCallable = Mono.fromCallable(() -> mayThrowCheckedException());
```

Both lambdas are passed in at assembly time, but **their bodies only execute when the source is triggered during subscription/data demand**. Each subscription to a cold publisher can perform a fresh invocation. `fromCallable` is convenient when the work may throw checked exceptions: Reactor turns execution-time exceptions into `onError` signals so downstream can handle them with `onErrorResume`/`onErrorMap`.

If the supplier/callable returns `null`, these factories complete **empty** (emitting no value) instead of emitting `null`. If a value is strictly required, check and convert an empty result into a business error, for example with `switchIfEmpty(...)`.

**Warning:** deferred ≠ non-blocking. `Mono.fromCallable(() -> jdbcRepository.findById(id))` still performs blocking JDBC when executed. If this source runs on the WebFlux event loop, it can block the event loop. When temporarily integrating blocking code, offload execution to an appropriate scheduler such as `subscribeOn(Schedulers.boundedElastic())`, while limiting concurrency and resources. This approach **does not turn JDBC into non-blocking I/O**.

### 4.3. `Mono.defer(...)`: Deferring Even Selecting and Creating the Publisher

`Mono.defer(Supplier<Mono<T>>)` invokes the publisher factory **for every subscription**. Difference from `fromSupplier`: `fromSupplier` defers producing **a value**; `defer` defers creating **a publisher** (which may be `Mono.empty()`, `Mono.error(...)`, or another publisher).

```java
Mono<String> chosenAtSubscription = Mono.defer(() -> {
    boolean enabled = featureFlagIsEnabled();
    return enabled ? Mono.just("new-path") : Mono.just("old-path");
});
```

In the **illustrative** snippet above, `featureFlagIsEnabled()` is only queried upon subscription. This is not a standalone program: the flag-checking method is provided by the application.

If you wrote `Mono.just(featureFlagIsEnabled() ? "new-path" : "old-path")`, the flag would be read **at publisher construction time**, so later subscriptions would keep emitting the already-chosen value. If you want selection based on current configuration per request, `defer` is more appropriate.

### 4.4. Isolated Timing Comparison Example

The snippet below can be placed in `main` of a Java class with Reactor, assuming the static `load()` method as defined:

```java
static int load() {
    System.out.println("load called");
    return 7;
}

// Placed inside main:
Mono<Integer> eager = Mono.just(load());
Mono<Integer> lazy = Mono.fromSupplier(() -> load());
System.out.println("assembled");

eager.subscribe(value -> System.out.println("eager: " + value));
lazy.subscribe(value -> System.out.println("lazy #1: " + value));
lazy.subscribe(value -> System.out.println("lazy #2: " + value));
```

Stdout for **this snippet**:

```text
load called
assembled
eager: 7
load called
lazy #1: 7
load called
lazy #2: 7
```

Note that getting 7 every time does not prove the work ran the same number of times. The number of `load()` calls reveals once at assembly for `just`, and twice at subscription for `fromSupplier`.

## 5. Assembly Builds a Description; It Does Not Mean "Nothing Runs at All"

Consider the example:

```java
System.out.println("before");
Mono<String> mono = Mono.just("hello")
        .map(value -> {
            System.out.println("inside map");
            return value.toUpperCase();
        });
System.out.println("after");
```

With no subscriber yet, stdout only contains:

```text
before
after
```

If `mono.subscribe(System.out::println)` is called afterward, the subsequent synchronous processing prints:

```text
inside map
HELLO
```

But when you write:

```java
Mono<String> mono = Mono.just(fetchBlocking());
```

`fetchBlocking()` still runs immediately, because it is **a Java expression evaluated to compute the argument**. The difference lies in where the work is placed: **outside a lambda** versus **inside a lambda/operator executed per signal**.

A similar confusion appears in:

```java
Mono<String> pipeline = source.map(value -> transform(value));
pipeline.map(value -> decorate(value));  // Result is discarded, does not modify pipeline
return pipeline;                          // Only the transform step runs on execution
```

Reactor operators generally return a **new publisher** without mutating the original publisher in place. To add an operation, you must reassign or return the result:

```java
return source
        .map(value -> transform(value))
        .map(value -> decorate(value));
```

These two snippets are illustrative only since `source`, `transform`, and `decorate` are not defined. The key is that the chain returned by each operator must be preserved.

## 6. Does Calling `subscribe()` Always Complete Immediately?

**No.** Subscribing and completing are two separate events.

- Synchronous sources, such as `Mono.just(1)`, `Flux.range(1, 3)`, and ordinary synchronous operators, can emit all signals while `subscribe()` is still on the call stack.
- Asynchronous sources, such as `WebClient`, `Mono.delay(...)`, polling/schedulers, or a source backed by a message broker, can complete **after `subscribe()` has already returned**. Data arrives via callbacks/schedulers when results become ready.
- `subscribeOn(...)` affects where subscription and source work are scheduled (depending on the source); `publishOn(...)` affects where downstream signals continue. Neither alters the Java rule that the argument to `Mono.just(expensiveCall())` was already evaluated beforehand.
- A subscriber can cancel the subscription before a result arrives; there is no guarantee that every `doOnNext` or `map` will run. An empty publisher can emit only `onComplete` with no `onNext`.

For example, `Mono.delay(Duration.ofMillis(100))` can continue on a scheduler thread after `subscribe()` returns. Therefore, writing:

```java
Mono.delay(java.time.Duration.ofMillis(100))
        .subscribe(value -> System.out.println("done"));
System.out.println("after subscribe");
```

must not be used as **proof that the callback has completed when execution passes the `subscribe()` line**. With async sources, a standalone program must keep the process alive long enough for the callback to run, whereas a WebFlux application has server lifecycle management. Do not rely on interleaved log order across threads to misjudge assembly order.

### 6.1. `block()` Also Creates a Subscription

In a command-line application or test, `mono.block()` can be convenient for waiting on a result. It **subscribes** to the publisher, waits for the final outcome, and returns the value; with a cold publisher, calling `block()` twice can run the source twice. `Flux.blockLast()` likewise triggers a subscription and waits for the last element.

**Do not use `block()` to grab values inside a WebFlux event-loop processing path.** It forfeits non-blocking benefits and can throw errors on threads that disallow blocking. To pass results between services/controllers, return `Mono` or `Flux`; at imperative boundaries, deliberately evaluate how waiting is isolated.

## 7. Cold vs. Hot Determines the Effect of Each Subscription

### 7.1. Cold Publishers: Each Subscriber Can Start Its Own Work

`Mono.fromSupplier(...)`, `Mono.defer(...)`, and `Flux.range(...)` are normally cold. Each subscription gets its own signal emission process. If a cold source wraps an HTTP request or DB query, **re-subscribing** can cause **another HTTP call/query**.

Example:

```java
Mono<Integer> cold = Mono.fromSupplier(counter::incrementAndGet);
```

This is an illustrative snippet (requiring an `AtomicInteger` variable `counter`). Two separate subscriptions can receive 1 and 2 respectively. If a publisher is re-subscribed by `retry(...)` or `repeat(...)`, upstream side effects can happen again. This is especially dangerous for money transfers, payments, sending emails, or creating resources without idempotency.

### 7.2. Hot Publishers: The Source May Already Be Running, and New Subscribers May Not See History

A `Sinks.Many` emitting events into a hot stream can have signals occurring **independently of when a particular subscriber arrives**. Late subscribers may miss earlier signals, or receive only replayed elements per sink configuration. You cannot mechanically apply the rule "every subscribe runs the source from the start".

Operators that introduce **sharing/caching** also change behavior:

- `share()` can share a single upstream subscription among active downstream subscribers; behavior when subscribers leave or arrive late depends on the publisher/operator type.
- `cache()` stores signals for later subscribers to reuse; subsequent subscriptions may skip re-executing the cached source portion.
- `publish().refCount(...)`, `replay(...)`, and similar operators alter when the source connects, start conditions, and how data is replayed.

A subtle point: `Mono.just(value)` captures the **value** at assembly time, yet is still typically a cold publisher in the sense that **each subscriber is re-emitted that value upon subscribing**. Eager value evaluation does not automatically make a source "hot". Similarly, `Flux.interval(...)` is not implicitly a globally shared hot stream: each subscription normally sets up its own tick schedule unless converted into a shared source.

**Distinguish three things:** (1) when values are computed / the source starts; (2) whether each subscriber gets its own subscription or shares upstream; (3) whether past data is replayed.

## 8. In Spring WebFlux, Who Calls `subscribe()`?

A WebFlux controller typically **returns the publisher** to the framework:

```java
@GetMapping("/products/{id}")
public Mono<ProductDto> get(@PathVariable String id) {
    System.out.println("controller: build pipeline");
    return webClient.get()
            .uri("http://catalog-service/products/{id}", id)
            .retrieve()
            .bodyToMono(ProductDto.class)
            .map(this::toDto);
}
```

This is an **illustrative controller snippet**, requiring application-defined `webClient`, `ProductDto`, and `toDto`, not a standalone Java class. When the handler is invoked, `controller: build pipeline` logs when the controller **constructs and returns the publisher**. The non-blocking HTTP call via `WebClient` normally starts when subscription occurs; the `map` callback only runs after incoming data arrives.

**Spring WebFlux is the one that subscribes** to the returned publisher to build the response and manage completion/error/cancellation across the request lifecycle. Do not call `subscribe()` yourself in a controller/service merely to "kick off" a pipeline that should be returned to the framework:

```java
// WRONG for HTTP lifecycle: publisher is triggered on the side,
// while the framework cannot wait for the result/cannot manage errors.
service.save(item).subscribe();
return Mono.just("accepted");
```

The snippet above **illustrates a bug** (`service` and `item` are hypothetical). If the save operation is required before returning the result, compose it into the returned publisher:

```java
return service.save(item)
        .thenReturn("saved");
```

`thenReturn` emits `"saved"` only after `save(item)` completes normally; if `save(item)` errors, the result also signals an error instead of returning a false success. **Note:** *calling* `service.save(item)` to obtain the publisher still happens during the assembly phase; inside the service, avoid eager/blocking work outside the publisher if you want all work deferred.

If business logic genuinely requires a background task independent of the HTTP response, design its lifecycle, error handling, observability, retries, and durability explicitly (e.g., message queue/outbox). Calling `subscribe()` casually to spawn unmanaged work is hard to control.

## 9. Logging and Debugging: Which Logs Indicate Assembly vs. Execution?

Example:

```java
System.out.println("assembly start");
Mono<Integer> pipeline = Mono.just(3)
        .doOnSubscribe(s -> System.out.println("subscription attached"))
        .map(i -> i * 2)
        .doOnNext(i -> System.out.println("next: " + i))
        .doFinally(signal -> System.out.println("finally: " + signal));
System.out.println("assembly end");
pipeline.subscribe(i -> System.out.println("subscriber: " + i));
```

Since the source is synchronous and completes normally, the output order is:

```text
assembly start
assembly end
subscription attached
next: 6
subscriber: 6
finally: onComplete
```

How to interpret this:

- Logs outside lambdas in the chain-building method print **when that method runs**, even before any subscription exists.
- `doOnSubscribe` shows the source received a subscription; it **does not confirm** that I/O finished or data arrived.
- `doOnNext` only runs if an element is emitted; it does not run for `Mono.empty()`.
- `doOnError` only runs on an error signal; `doFinally` sees completion, error, or cancellation, making it useful for inspecting how a subscription ended.
- Reactor's `log()` helps observe subscription, request, onNext, onComplete, and cancel, though it can generate heavy log volume under high load. Enable it selectively during debugging and avoid logging sensitive data.

For async chains, logs from different threads can interleave; adding **request/correlation IDs** and tracing compatible with Reactor Context helps identify which request a signal belongs to. Do not assume a single subscription always runs on a single thread.

## 10. Common Mistakes and Fixes

| Common Misconception / Buggy Pattern | Problem | Right Approach |
| --- | --- | --- |
| `Mono.just(blockingCall())` to defer I/O | `blockingCall()` runs immediately at assembly; can also block the event loop | Use non-blocking APIs; if bridging is unavoidable, bounded `fromCallable(...).subscribeOn(boundedElastic())` |
| "Creating a `Mono` means the data was already queried" | The publisher is built, but subscription/demand may not have happened yet | Identify where the publisher is returned and who subscribes |
| Calling `subscribe()` inside a controller and returning `Mono.just("ok")` | Detaches the task from the response and loses error/cancel propagation | Return the chain, e.g., `service.save(...).thenReturn(...)` |
| Calling `subscribe()` twice on a cold HTTP source for one result | Can trigger two real requests | Use intentional sharing/caching or compose within one pipeline |
| Assuming `map` and `flatMap` run when attached to the chain | Lambdas only process when matching signals arrive | Use logs at assembly and at signal time to tell them apart |
| Calling `pipeline.map(...)` and discarding the result | The original pipeline is unchanged | Return or reassign the new publisher |
| Calling `block()` on the event loop | Blocking, defeats WebFlux benefits, and may be rejected | Keep `Mono`/`Flux` return types across layers |
| Thinking `subscribeOn` makes `Mono.just(blockingCall())` safe | The Java argument is evaluated before the publisher even exists | Wrap the call inside a deferred lambda and choose the right scheduler |
| Equating `subscribe()` with instant completion | Async sources may run after `subscribe` returns | Track `onNext`/`onError`/`onComplete` and write async tests |
| Using `retry` on a source with non-idempotent side effects | Can repeat writes/HTTP calls upon resubscription | Design idempotency, retry predicates, backoff, and attempt limits |
| Assuming every publisher is cold | Hot/cached/shared publishers may already be emitting or share upstream | Inspect sinks, `share`, `cache`, `publish`, and replay policies |

### 10.1. Special Note on `flatMap`

`flatMap(value -> asyncCall(value))` only invokes its lambda to create an inner publisher when upstream **emits a matching value**. Reactor then subscribes to that inner publisher to merge results; it is not equivalent to calling `asyncCall(...)` at assembly time of the outer pipeline.

If `asyncCall` itself performs blocking side effects before returning its publisher, those side effects still execute **when the lambda is invoked**, typically during the signal-processing phase. Even inside `flatMap`, blocking can still occur on the event loop. Therefore, inspect **the method body**, not just the `Mono<T>` return type.

`flatMap` can also open multiple inner publishers concurrently, whereas `concatMap` preserves the sequential order of inner subscriptions. For a large `Flux`, consider concurrency limits, memory, and backpressure before executing.

### 10.2. `switchIfEmpty` Arguments Can Also Trigger Early Publisher Construction

For example, `source.switchIfEmpty(fallbackPublisher())` **calls the Java method `fallbackPublisher()` immediately at assembly time** to evaluate the publisher argument, even if the primary source later emits a value. If that method merely *creates a lazy publisher*, the fallback's signals will not run when the source is non-empty; however, any side effect happening while *constructing* the fallback still occurs early.

To defer even invoking the fallback-selection method, write:

```java
return source.switchIfEmpty(Mono.defer(() -> fallbackPublisher()));
```

This is an illustrative snippet with hypothetical `source` and `fallbackPublisher()`. General rule: placing a deferred lambda right at **the boundary where work happens** is what guarantees that work is not triggered early.

## 11. Testing Execution Timing Accurately

An important test is proving that code does no work before subscription and only executes when the publisher is triggered. With `reactor-test`, you can use `StepVerifier` to verify signals while measuring side effects with a counter.

Illustrative example inside a JUnit 5 test with `reactor-test`:

```java
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import static org.junit.jupiter.api.Assertions.assertEquals;

class SubscriptionTimingTest {
    @Test
    void coldSourceRunsForEachSubscription() {
        AtomicInteger counter = new AtomicInteger();
        Mono<Integer> source = Mono.fromSupplier(counter::incrementAndGet);

        assertEquals(0, counter.get()); // Assembly has not run the source yet

        StepVerifier.create(source)
                .expectNext(1)
                .verifyComplete();

        assertEquals(1, counter.get());

        StepVerifier.create(source)
                .expectNext(2)
                .verifyComplete();

        assertEquals(2, counter.get());
    }
}
```

Requires `org.junit.jupiter:junit-jupiter` and `io.projectreactor:reactor-test` in test dependencies (versions managed by the Spring Boot BOM if using Spring Boot); run with the project's JUnit/Gradle test runner. This test needs no `Thread.sleep(...)` and does not rely on flaky timing.

You can extend tests with `Mono.defer` to prove a flag variable is evaluated on each subscription; use `StepVerifier.withVirtualTime(...)` for time-based publishers like `delay`/`interval`; and use `PublisherProbe` to verify that a fallback branch was actually subscribed to. For errors/cancellation, tests should assert the corresponding `onError` and `doFinally(CANCEL)` paths rather than merely counting log lines.

## 12. Practical Checklist When Reading Production Code

For a method returning `Mono`/`Flux`, check each item in order:

1. **Construction point:** what Java calls execute before returning the publisher? Can they block or mutate state?
2. **Source:** `just`, `fromSupplier`, `defer`, `WebClient`, R2DBC, hot sink, or cached publisher? Could events already have been emitted beforehand?
3. **Subscription point:** WebFlux controller, `StepVerifier` test, CLI `block()`, or a consumer with its own lifecycle? Are there unintended `subscribe()` calls?
4. **Emission point:** which operators run per `onNext`, which branches run only on empty/error, and which sources only start upon receiving demand?
5. **Re-subscription:** will `retry`, `repeat`, multiple subscribers, or replay/cache cause extra I/O or reuse results? Are side effects idempotent?
6. **Threading and cancellation:** are there async sources or schedulers; is any blocking code running on the event loop; do timeouts/cancellations release resources and stop work cleanly?

## 13. Key Takeaway

**Assembly creates and wires publishers; subscription establishes consumption, from which sources and operators process data according to demand and signals.** With cold publishers, each subscription typically starts its own source chain; with hot/shared/cached publishers, behavior also depends on sharing and replay semantics.

Remember the three contrasting examples: `Mono.just(call())` invokes `call()` immediately; `Mono.fromSupplier(() -> call())` invokes it when the source is triggered; `Mono.defer(() -> buildPublisher())` defers creating the publisher itself. In Spring WebFlux, **return the publisher for the framework to manage subscription**, place side effects at the proper boundaries, and observe actual signals rather than guessing from where `map` or `subscribe()` appears in code.
