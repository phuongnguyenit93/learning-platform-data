# doOnCancel, doOnTerminate, and doFinally

**Module:** Spring Framework – reactive  
**Parent topic:** Cancellation and resources

## Learning Objectives

After this lesson, you can:

1. Distinguish the three outcomes of a subscription in Reactor: **successful completion**, **termination with an error**, and **cancellation**.
2. Explain accurately when `doOnCancel`, `doOnTerminate`, and `doFinally` run on `Mono`/`Flux`, along with the relative ordering between callbacks and signals passing through the operator.
3. Use `SignalType.ON_COMPLETE`, `SignalType.ON_ERROR`, and `SignalType.CANCEL` to collect metrics or perform consistent cleanup by outcome.
4. Understand the difference when placing hooks **before or after** `take`, `timeout`, `onErrorResume`, and other boundaries.
5. Distinguish side-effect hooks used for **observation** from mechanisms that **own and close resources** such as `using`, `usingWhen`, and `doOnDiscard`.
6. Apply these in Spring WebFlux without manually calling `subscribe()` in a controller; understand practical limits when a client disconnects.

## 1. Why Care About Cancellation, Completion, and Errors Alike?

Reactive applications do not only process `onNext` values. When an HTTP connection closes, a user stops watching a stream, a timeout occurs, or all data has finished sending, the subscription lifecycle can end along different paths. If you only clean up resources on `onComplete`, you can miss cancellation. If you only handle `onError`, you also miss cases where downstream no longer wants to receive more even though the source did not fail.

A Reactor pipeline is built from publishers such as `Mono<T>` (at most one value) and `Flux<T>` (0 to many values). Under Reactive Streams, a subscriber receives `onSubscribe` and valid `onNext` calls, and may then receive one of two terminal signals:

- **`onComplete`:** the source finished successfully; no more elements.
- **`onError(Throwable)`:** the source terminated with an error; no further `onNext` or `onComplete`.
- **`Subscription.cancel()`:** control direction **from downstream back upstream**, expressing that the subscriber has no more demand. This is not an `onComplete` or `onError` emitted down to the subscriber.

Therefore, when saying “terminate”, you must ask **terminate in what way**. Reactor provides three related hooks, but **they cannot be treated as synonymous**.

```text
                        Active subscription
                                   |
           +-----------------------+----------------------+
           |                       |                      |
        onComplete               onError                 cancel()
           |                       |                      |
    doOnTerminate runs      doOnTerminate runs       doOnCancel runs
           |                       |                      |
       downstream               downstream              upstream
       completes              receives error         receives cancel
           |                       |                      |
   doFinally(ON_COMPLETE)  doFinally(ON_ERROR)     doFinally(CANCEL)
```

The diagram is a conceptual model for **a single hook position** in a pipeline; exact execution order also depends on operator placement, synchronous/asynchronous sources, and the segment of the pipeline being observed. The core idea is:

- `doOnCancel` observes **only cancel**.
- `doOnTerminate` observes **only complete or error**, not cancel.
- `doFinally` observes **all three: complete, error, and cancel**, and knows the termination type.

## 2. Quick Comparison of the Three Operators

| Operator | Callback | On successful completion | On error | On cancel | Receives reason? |
| --- | --- | --- | --- | --- | --- |
| `doOnCancel(Runnable)` | `() -> ...` | No | No | **Yes** | No; knows it is the cancel branch. |
| `doOnTerminate(Runnable)` | `() -> ...` | **Yes** | **Yes** | No | No; use another hook to tell error vs complete. |
| `doFinally(Consumer<SignalType>)` | `signal -> ...` | **Yes** | **Yes** | **Yes** | **Yes**, via `SignalType`. |

All of these are **side-effect operators**: they return a new publisher, preserving the data type of the pipeline; callbacks do not transform one value into another and do not “recover” errors by themselves. Example:

```java
Flux<String> observed = source
        .doOnCancel(() -> metrics.incrementCancelled())
        .doOnTerminate(() -> metrics.incrementTerminated())
        .doFinally(signal -> metrics.recordFinalSignal(signal));
```

This is an **illustrative snippet**, requiring an application-defined `Flux<String> source` and `metrics`. Writing the operator chain does not yet run callbacks for lazy subscriptions; callbacks run when a subscription reaches the corresponding signal. If there is no subscriber or the pipeline never reaches a matching outcome, the callback may never run.

### 2.1. doOnCancel: Observing a Cancellation Request

Common signatures:

```java
Flux<T> doOnCancel(Runnable onCancel)
Mono<T> doOnCancel(Runnable onCancel)
```

When cancellation propagates upstream through this operator, Reactor runs the `onCancel` callback **first**, and then forwards `cancel` upstream at that position. This is a good hook for logging, incrementing cancellation counters, or notifying a resource owner that downstream does not want further data.

```java
Flux<Long> ticks = Flux.interval(Duration.ofSeconds(1))
        .doOnCancel(() -> System.out.println("subscriber cancelled"));
```

This is an **illustrative snippet**, requiring imports for `java.time.Duration` and `Flux`. This statement does not start the timer by itself; there must be a subscription. When the subscriber cancels, the hook observes cancellation. Do not infer from the hook that all in-flight I/O operations have stopped immediately or that prior side effects were rolled back.

**Do not use `doOnCancel` to detect errors.** If upstream emits `onError`, there is no reason for the cancel callback to run just because of an error. Likewise, a normally completing source does not turn completion into cancellation.

### 2.2. doOnTerminate: Observing Complete or Error

Signatures:

```java
Flux<T> doOnTerminate(Runnable onTerminate)
Mono<T> doOnTerminate(Runnable onTerminate)
```

`doOnTerminate` runs when the publisher at that position completes successfully or signals an error. The callback executes **before** the terminal signal is forwarded downstream. It does **not** run merely because a subscriber cancels.

```java
Flux<Integer> observed = Flux.range(1, 3)
        .doOnTerminate(() -> System.out.println("source terminated"));
```

The snippet above is **illustrative**: when a subscriber consumes all three elements, the callback runs once due to completion. When the source errors, the callback also runs, though from a `Runnable` you receive neither the `Throwable` nor a flag distinguishing the two cases.

If you need to distinguish them:

```java
Flux<Integer> observed = source
        .doOnComplete(() -> metrics.completed())
        .doOnError(error -> metrics.failed(error))
        .doOnTerminate(() -> metrics.terminated());
```

This is an **illustrative snippet**, with `source` and `metrics` defined by the application. `doOnComplete` is `Flux`'s hook for successful completion, `doOnError` receives the exception; `doOnTerminate` can count total terminations excluding cancel. Avoid double-counting the same event if your dashboard sums metrics that represent different meanings.

**Specific note for Mono:** when a `Mono` emits an element successfully, semantically it is already known that it will complete, so `Mono.doOnTerminate` is invoked **before the `onNext` element is forwarded** downstream, unlike `Flux.doOnTerminate` which only runs on `onComplete` or `onError`. With `Mono.empty()`, the hook runs before `onComplete`; with `Mono.error(...)`, the hook runs before `onError`. This is an important difference when checking log ordering.

### 2.3. doFinally: Unified Handling of Every Outcome

Signatures:

```java
Flux<T> doFinally(Consumer<SignalType> onFinally)
Mono<T> doFinally(Consumer<SignalType> onFinally)
```

`doFinally` receives the outcome kind:

| `SignalType` | Meaning |
| --- | --- |
| `ON_COMPLETE` | The subscription at the operator's position completed successfully. |
| `ON_ERROR` | The subscription at the operator's position terminated with an error. |
| `CANCEL` | Downstream cancelled via the subscription at the operator's position. |

Example:

```java
Flux<String> traced = source.doFinally(signal -> {
    switch (signal) {
        case ON_COMPLETE -> metrics.record("completed");
        case ON_ERROR -> metrics.record("failed");
        case CANCEL -> metrics.record("cancelled");
        default -> metrics.record("other");
    }
});
```

This is a **Java 17 illustrative snippet**, requiring an application-defined `Flux<String> source` and `metrics`. Reactor invokes the callback **after forwarding the termination signal in the appropriate direction** (complete/error downstream; cancel upstream). Thus, `doFinally` is useful for outcome-based cleanup/metrics; however, do not use this callback to “convert” an error into a different response.

If multiple `doFinally` operators are chained consecutively, their callbacks are typically invoked in **reverse declaration order** when a terminal event passes through the chain:

```java
Flux.just("x")
    .doFinally(signal -> System.out.println("first " + signal))
    .doFinally(signal -> System.out.println("second " + signal));
```

This is an **unsubscribed illustrative snippet**; when subscribed to and completed, the `second` hook runs before the `first` hook. Do not rely on a `doFinally` callback having already updated a counter immediately after a `block()` or `blockLast()` call returns in other scenarios: the terminal signal can reach downstream **before** `doFinally` finishes, especially in asynchronous pipelines. For tests that need to verify cleanup, wait on a dedicated cleanup signal or use properly synchronized test constructs.

## 3. Runnable Java 17+ Program: Four Observable Outcomes

The example uses **Java 17+**, **Maven**, and **Project Reactor Core 3.8.8**. To keep output ordering easy to inspect, we use synchronous sources (`Flux.just`, `Flux.range`, `Flux.error`, and `Mono.just`) instead of HTTP/timers. Each scenario has its own subscriber.

Create the structure:

```text
termination-hooks-demo/
├── pom.xml
└── src/main/java/demo/
    └── TerminationHooksDemo.java
```

### pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>termination-hooks-demo</artifactId>
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
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### src/main/java/demo/TerminationHooksDemo.java

```java
package demo;

import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class TerminationHooksDemo {
    private static void successfulFlux() {
        System.out.println("=== COMPLETE ===");
        Flux.range(1, 2)
                .doOnCancel(() ->
                        System.out.println("source: cancel"))
                .doOnTerminate(() ->
                        System.out.println("source: terminate"))
                .doFinally(signal ->
                        System.out.println("source: finally " + signal.name()))
                .subscribe(
                        value -> System.out.println("downstream: " + value),
                        error -> System.out.println("downstream error"),
                        () -> System.out.println("downstream: complete"));
    }

    private static void failingFlux() {
        System.out.println("=== ERROR ===");
        Flux.concat(
                    Flux.just(7),
                    Flux.<Integer>error(
                            new IllegalStateException("broken")))
                .doOnCancel(() ->
                        System.out.println("source: cancel"))
                .doOnTerminate(() ->
                        System.out.println("source: terminate"))
                .doFinally(signal ->
                        System.out.println("source: finally " + signal.name()))
                .subscribe(
                        value -> System.out.println("downstream: " + value),
                        error -> System.out.println("downstream: error " +
                                error.getClass().getSimpleName()),
                        () -> System.out.println("downstream: complete"));
    }

    private static void cancelledFlux() {
        System.out.println("=== CANCEL ===");
        Flux.range(1, 5)
                .doOnCancel(() ->
                        System.out.println("source: cancel"))
                .doOnTerminate(() ->
                        System.out.println("source: terminate"))
                .doFinally(signal ->
                        System.out.println("source: finally " + signal.name()))
                .subscribe(new BaseSubscriber<Integer>() {
                    @Override
                    protected void hookOnSubscribe(Subscription subscription) {
                        request(1);
                    }

                    @Override
                    protected void hookOnNext(Integer value) {
                        System.out.println("downstream: " + value);
                        cancel();
                    }

                    @Override
                    protected void hookOnError(Throwable error) {
                        System.out.println("downstream: error");
                    }
                });
    }

    private static void successfulMono() {
        System.out.println("=== MONO ===");
        Mono.just("OK")
                .doOnTerminate(() ->
                        System.out.println("mono: terminate"))
                .doOnNext(value ->
                        System.out.println("mono: doOnNext " + value))
                .doFinally(signal ->
                        System.out.println("mono: finally " + signal.name()))
                .subscribe(
                        value -> System.out.println("mono subscriber: " + value),
                        error -> System.out.println("mono subscriber error"),
                        () -> System.out.println("mono subscriber complete"));
    }

    public static void main(String[] args) {
        successfulFlux();
        failingFlux();
        cancelledFlux();
        successfulMono();
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.TerminationHooksDemo
```

**Stdout of the program itself** (excluding Maven logs or warnings):

```text
=== COMPLETE ===
downstream: 1
downstream: 2
source: terminate
downstream: complete
source: finally ON_COMPLETE
=== ERROR ===
downstream: 7
source: terminate
downstream: error IllegalStateException
source: finally ON_ERROR
=== CANCEL ===
downstream: 1
source: cancel
source: finally CANCEL
=== MONO ===
mono: terminate
mono: doOnNext OK
mono subscriber: OK
mono subscriber complete
mono: finally ON_COMPLETE
```

**Why does the program print this?**

- **COMPLETE:** `Flux.range(1, 2)` emits 1, 2 and then signals completion. `doOnTerminate` runs before `onComplete` reaches the subscriber, while `doFinally` runs after. There is no `source: cancel`.
- **ERROR:** `Flux.concat` emits 7 and then switches to `Flux.error`. `doOnTerminate` runs before the error reaches the subscriber, and `doFinally` receives `ON_ERROR`. There is no `downstream: complete`.
- **CANCEL:** `BaseSubscriber` initially requests only 1, receives 1, and calls `cancel()`. `doOnCancel` runs; `doFinally` receives `CANCEL`. `doOnTerminate` **does not run**, because there was no complete/error at the observed source segment.
- **MONO:** `Mono.just("OK")` already knows it will succeed with one element. For `Mono`, `doOnTerminate` runs **before** `onNext("OK")` is forwarded, so `mono: terminate` precedes `mono: doOnNext OK`. This is a key difference compared to `Flux`.
- In the last three cases alike, `doFinally` knows the **kind** of termination via `signal.name()`. The fact that this synchronous example yields predictable ordering does not mean callbacks on async publishers will execute on the same thread.

**Note:** The `subscribe(...)` calls in `main` are only for the standalone CLI lesson. In a Spring WebFlux handler, you normally return the publisher to the HTTP framework instead of subscribing yourself.

## 4. Reading the Signal Table: Which Hook Runs When?

Assume each publisher is subscribed to exactly once, hooks are placed on the same pipeline segment, and no downstream operator alters the termination semantics:

| Scenario | doOnCancel | doOnTerminate | doFinally |
| --- | --- | --- | --- |
| `Flux.just(1, 2).subscribe(...)` receives all | No | Yes, once | `ON_COMPLETE` |
| `Mono.empty()` completes | No | Yes, once | `ON_COMPLETE` |
| `Mono.just("ok")` emits one element successfully | No | Yes, once, before `onNext` | `ON_COMPLETE` |
| `Flux.error(new RuntimeException(...))` | No | Yes, once | `ON_ERROR` |
| `Flux.never()` is cancelled by subscriber | Yes | No | `CANCEL` |
| `Flux.range(1, 10)` is cancelled after two values | Yes | No | `CANCEL` |
| Publisher never emits a terminal and is not cancelled | No | No | No |
| Publisher created but not yet subscribed | No | No | No |

The table assumes a simple single-subscription model. **Operator placement matters greatly**: a pipeline can complete normally downstream due to `take` or `onErrorResume` while the upstream segment terminates via cancel or error. You must answer the question: “Which segment did I attach the hook to?” before interpreting logs.

## 5. Easily Confused Case: take(n) and Cancellation

`take(n)` can complete the **resulting publisher** after `n` elements, yet to avoid receiving more data from the source, it usually **cancels upstream**. Therefore, two hooks on either side of `take` can observe two different outcomes.

```java
Flux<Integer> observed = Flux.range(1, 10)
        .doOnCancel(() ->
                System.out.println("UPSTREAM cancelled"))
        .doOnTerminate(() ->
                System.out.println("UPSTREAM terminated"))
        .doFinally(signal ->
                System.out.println("UPSTREAM finally: " + signal))
        .take(2)
        .doOnTerminate(() ->
                System.out.println("DOWNSTREAM terminated"))
        .doFinally(signal ->
                System.out.println("DOWNSTREAM finally: " + signal));
```

This is an **illustrative snippet**, requiring a `Flux` import and a subscription to trigger. With a cold `range` source that is not exhausted after two elements:

- **Before `take(2)`**, the source receives cancellation: `doOnCancel` and `doFinally(CANCEL)` may be recorded. Upstream `doOnTerminate` does not run merely from cancellation.
- **After `take(2)`**, the result emits two elements and **completes successfully**: downstream `doOnTerminate` and the corresponding `doFinally(ON_COMPLETE)` run.
- There is no contradiction: **the exact same action** can be “cancel upstream” while being “complete downstream”.

Do not take an upstream `doFinally(CANCEL)` as proof that an HTTP request failed. Cancellation is sometimes a **normal optimization mechanism** of operators such as `take`, `next`, `timeout`, or single-result selection strategies. Distinguish client-initiated cancellation, element-limiting operator cancellation, and cancellation caused by an error in another branch using proper context and tracing.

### 5.1. Mono from first/next Can Also Cancel the Source

If a `Flux` has multiple elements and you call `next()`, the result is a `Mono` taking the first element. Once a value is obtained, the operator can cancel the upstream subscription because the rest is unnecessary. The same holds for `take(1)`. Upstream `doOnCancel` can run even though the external subscriber receives a completely normal result.

### 5.2. doFinally Does Not Have Just One “Answer” for the Entire Pipeline

```java
source
    .doFinally(signal -> log("source-side", signal))
    .take(1)
    .doFinally(signal -> log("response-side", signal));
```

This is an **illustrative snippet**, requiring `source` and an application-defined `log` function. The two callbacks describe **two different subscription segments**. For a source with more values remaining, the source side can see `CANCEL`, while the response side sees `ON_COMPLETE`. Place the hook right next to the component you want to measure.

## 6. Easily Confused Case: Errors Recovered by onErrorResume

`onErrorResume` can intercept an upstream error and switch to a fallback publisher. From a viewpoint before recovery, the source failed; from a viewpoint after recovery, the overall output can complete successfully.

```java
Mono<String> result = remoteCall()
        .doOnTerminate(() -> metrics.rawTerminated())
        .doFinally(signal -> metrics.rawFinally(signal))
        .onErrorResume(error -> Mono.just("fallback"))
        .doOnTerminate(() -> metrics.responseTerminated())
        .doFinally(signal -> metrics.responseFinally(signal));
```

This is an **illustrative snippet**; `remoteCall()` returns `Mono<String>`, and `metrics` is application-defined. If `remoteCall` errors and the fallback succeeds:

1. `doOnTerminate` before recovery runs because upstream failed.
2. `doFinally` on the source segment receives `ON_ERROR`.
3. `onErrorResume` replaces the error with `Mono.just("fallback")`.
4. Downstream `doOnTerminate` runs because the resulting publisher succeeded.
5. Downstream `doFinally` receives `ON_COMPLETE`.

**Exact log ordering among callbacks** still depends on placement and synchronicity, but the classification at each position is the key point to remember. If a dashboard wants to measure **raw upstream error counts**, place `doOnError` before recovery. If it wants to measure **final successful response rate**, place `doFinally`/`doOnTerminate` after recovery. Avoid treating these two sets as measurements with the same meaning.

### 6.1. timeout Can Produce Error Downstream and Cancel Upstream

When `timeout(Duration.ofSeconds(...))` expires, it can cancel the pending source subscription and emit a `TimeoutException` downstream. A `doFinally` **before** `timeout` can see `CANCEL`; a `doFinally` **after** `timeout` can see `ON_ERROR`, unless another recovery changes the outcome. This is why you should not interpret every `CANCEL` as a user disconnecting.

### 6.2. retry Increases Subscription Counts and Hook Invocations

`retry(2)` can re-subscribe upstream on error, up to two retry attempts beyond the initial try. Hooks **before** `retry` sit inside each subscription attempt and may run multiple times, whereas hooks **after** `retry` observe the final outcome of the entire pipeline at that position. When tracking errors, distinguish `attempts`, `retries`, and `requests`; otherwise event counts will easily be miscounted.

## 7. doFinally and Releasing Resources

`doFinally` is convenient for releasing resources owned by a subscriber or instrumentation; however, it is a **side-effect callback**, not a transaction manager or automatic resource scope.

Example counting active subscriptions:

```java
AtomicInteger active = new AtomicInteger();

Flux<String> tracked = source
        .doOnSubscribe(subscription ->
                active.incrementAndGet())
        .doFinally(signal ->
                active.decrementAndGet());
```

This is an **illustrative snippet**, requiring `java.util.concurrent.atomic.AtomicInteger` and an application-defined `Flux<String> source`. Each subscription entering the tracked segment increments once and decrements once upon termination. For production metrics logic, check whether the hook is in the right place, whether the source has retry/share, how late the metric may be observed, and whether the callback could throw. If `doFinally` has not finished running at the moment a test reads `active`, temporary readings can be misleading.

### 7.1. Which Hook to Choose for Cleanup?

- **Only on cancel:** `doOnCancel` fits logging/metrics or releasing something specific to the cancellation path.
- **Only complete/error:** `doOnTerminate` fits when cancel does not matter, but is **insufficient** for cleaning up resources that must be closed in every case.
- **Every outcome:** `doFinally` fits finalizing metrics, releasing a callback-managed handle, or observing `SignalType`.
- **Source that actually opens a resource:** usually prefer `Flux.using`/`Mono.using` (sync resource) or `usingWhen` (reactive/async resource cleanup) to ensure cleanup scope and ordering are bound to the publisher.

**Do not put slow blocking cleanup operations inside `doFinally`** running on the WebFlux event-loop signal path. The callback may execute on an I/O thread and stall the entire application. If you need to close a connection, transaction, or session via an async operation, use an appropriate abstraction instead of nesting a `subscribe()` call inside `doFinally`.

### 7.2. using for Synchronously Closed Resources

```java
Flux<String> lines = Flux.using(
        () -> openReader(),                  // create resource per subscription
        reader -> readLinesReactive(reader),  // return Flux<String>
        reader -> closeReader(reader));       // close resource per scope
```

This is a **structural illustrative snippet**: `openReader`, `readLinesReactive`, and `closeReader` are application-defined; if `readLinesReactive` directly performs blocking file reads, do not assume it is non-blocking just because it returns a `Flux`. `using` has overloads for eager cleanup; read the API and choose appropriately if closing the resource before vs after emitting the terminal signal matters.

Main point: the publisher **owns the resource** and is responsible for closing it per subscription scope, rather than relying on an external subscriber remembering to attach the right hook.

### 7.3. usingWhen for Asynchronous Cleanup

```java
Flux<Result> queryResults = Flux.usingWhen(
        pool.acquire(),                     // Mono<Resource>
        resource -> query(resource),        // Flux<Result>
        resource -> resource.release(),     // Publisher<?> on complete
        (resource, error) -> resource.release(), // cleanup on error
        resource -> resource.release());    // cleanup on cancel
```

This is an **illustrative snippet**, requiring definitions for `Result`, `pool`, `Resource`, `query`, and `release()` returning a reactive publisher. The API has an overload passing separate cleanup for complete/error/cancel. Real policies might commit on success, roll back on error, and roll back on cancel; do not assume all three branches should just “release” if transactions require different handling.

`usingWhen` has specific rules for waiting on the cleanup publisher to complete as well as propagating cleanup errors; use it when **cleanup timing and asynchronicity** matter to the result, instead of spawning an independent subscription inside `doFinally`.

### 7.4. Resources Dropped by filter/prefetch: doOnDiscard

When a `filter` operator drops an object, or buffered/prefetched items are discarded due to cancel/error, certain resources such as pooled buffers may need to be released even though they **never reached the subscriber**. `doFinally` reports that the subscription ended, but does not automatically provide a list of every discarded item.

```java
Flux<Buffer> values = source
        .filter(this::shouldKeep)
        .doOnDiscard(Buffer.class, Buffer::release);
```

This is an **illustrative snippet**, assuming `Buffer`, `source`, and `shouldKeep` are application-defined; use only if `Buffer` is indeed a releasable resource type and the operator supports discard. `doOnDiscard` is not guaranteed to be supported by all operators; the callback must be safe when invoked repeatedly or for items needing cleanup, and must never release a buffer still owned by downstream.

## 8. In Spring WebFlux, What Happens When a Client Disconnects?

A streaming endpoint can produce a long-lived `Flux`:

```java
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<String> events() {
    return Flux.interval(Duration.ofSeconds(1))
            .map(index -> "event-" + index)
            .doOnCancel(() -> logger.info("stream cancelled"))
            .doOnTerminate(() -> logger.info("stream terminated"))
            .doFinally(signal ->
                    logger.info("stream finally: {}", signal));
}
```

This is an **illustrative snippet inside a `@RestController`**, requiring imports for `Flux`, `Duration`, `GetMapping`, `MediaType`, and a logger. WebFlux and the HTTP runtime typically own the response subscriber. When a client ends the stream by closing the connection, cancellation **can** propagate back to the `Flux` and trigger `doOnCancel`/`doFinally(CANCEL)`. However:

- Disconnect detection depends on the reactive HTTP server, buffers, transport, and write timing. There is no guarantee the hook runs in the exact millisecond the client closes the tab.
- If the stream finishes normally on its own, `doOnTerminate` and `doFinally(ON_COMPLETE)` may run, not cancel.
- If the source errors, `doOnTerminate` and `doFinally(ON_ERROR)` run, though the HTTP response may already have sent headers/body and cannot arbitrarily change its status to 500.
- A `CANCEL` **does not prove** only that the client disconnected. Operators such as `take`, `next`, or `timeout` can also cancel upstream intentionally.
- Do not call `.subscribe()` inside the handler to “activate” callbacks. Doing so creates a separate subscription detached from the response, so HTTP cancel/error does not automatically flow to that new branch.

If you need to record metrics when an HTTP request finishes, you can attach `doFinally` on the returned publisher after the main processing steps. If resources opened in a service need cleanup, keep the resource-closing mechanism **at the source/service itself**, rather than relying entirely on whether the controller attached a hook.

### 8.1. doFinally Does Not Turn Side Effects into Reliable Background Tasks

If inside `doFinally` you call:

```java
.doFinally(signal -> auditService.writeEvent(signal).subscribe())
```

This is an **illustrative snippet of an anti-pattern** in business pipelines. It opens a detached subscription, does not guarantee the audit was saved when the response ends, does not manage retries or shutdown, and can lose data if the application stops. For audits required before confirming success, compose the audit publisher into the result flow. For genuine background auditing, use a queue/outbox or a consumer with managed lifecycle, errors, and retries.

### 8.2. Never Block the Event-Loop During Cleanup

`doOnCancel`/`doOnTerminate`/`doFinally` may be invoked on the signal-emitting thread or the cancelling thread. Therefore, never write `Thread.sleep`, synchronous JDBC, or `block()` inside WebFlux callbacks. Use reactive resource APIs or a properly designed scheduler strategy if blocking work must be handled. **Do not assume `doFinally` runs on a background thread.**

## 9. Callback Ordering and Result Visibility

Hooks are not a “Java try/finally invoked in the exact same stack frame” in every situation. A subscription can span multiple operators and schedulers:

1. `doOnCancel` runs **before** forwarding `cancel` upstream at that operator's position.
2. `doOnTerminate` runs **before** forwarding `onComplete`/`onError` downstream; for a valued `Mono`, it can run before `onNext`.
3. `doFinally` runs **after** the termination signal has been propagated. With multiple consecutive `doFinally` calls, callbacks execute in reverse declaration order.
4. `doAfterTerminate` (if used) observes only complete/error **after** the terminal signal has been passed downstream; it still does not handle cancel like `doFinally`.
5. `doOnSuccess` is `Mono`'s success hook: it receives value `T` when the Mono completes with data, and receives `null` **in the callback** if the Mono completes empty. This **does not mean** Reactor emits `null` via `onNext`.

If testing a counter inside `doFinally`, do not assume checking immediately after `block()` will always see the increment/decrement. Because `doFinally` runs after the terminal signal is delivered downstream, tests with async publishers may need a `CountDownLatch`, `StepVerifier` combined with a waiting mechanism, or a dedicated cleanup signal. Do not “fix” this with arbitrary `Thread.sleep`.

### 9.1. One Subscription Is Not the Whole Application Lifecycle

With `retry`, each attempt can create a new subscription to the source and callbacks there run multiple times. With `share`, `publish`, `cache`, or hot sources, how subscribers share upstream can change callback invocation counts at each position. Always measure the right scope: one subscriber, one connection, one request, or one shared source. If you want to count HTTP requests, do not naively infer it from `doFinally` counts across all nested publishers.

## 10. Testing Complete, Error, and Cancel

The `reactor-test` library provides `StepVerifier`, useful for verifying outcomes. Add the dependency matching your `reactor-core` version branch:

```xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <version>3.8.8</version>
    <scope>test</scope>
</dependency>
```

The following are **code snippets inside test methods**, not standalone Java programs; import `StepVerifier`, `Flux`, and `Mono`.

### 10.1. Verifying Complete

```java
StepVerifier.create(
        Flux.just(1, 2).doOnTerminate(() -> record("terminated")))
    .expectNext(1, 2)
    .verifyComplete();
```

Define `record` in the test. When the source completes, the `doOnTerminate` callback runs. `verifyComplete()` confirms the terminal signal is indeed `onComplete`.

### 10.2. Verifying Error

```java
StepVerifier.create(
        Flux.<Integer>error(new IllegalStateException("bad"))
            .doOnTerminate(() -> record("terminated")))
    .expectError(IllegalStateException.class)
    .verify();
```

`doOnTerminate` still runs even though the source did not succeed, because it observes both complete/error. If you need to inspect exception details, use `doOnError` or dedicated assertions.

### 10.3. Verifying Cancel

```java
StepVerifier.create(
        Flux.range(1, 10)
            .doOnCancel(() -> record("cancelled"))
            .doFinally(signal -> record(signal.name())),
        0)
    .thenRequest(2)
    .expectNext(1, 2)
    .thenCancel()
    .verify();
```

This scenario creates a subscriber with **initial request = 0**, then requests 2 elements and cancels. Since all 10 elements were not requested, the source segment is cancelled; `doOnCancel` observes cancellation, and `doFinally` receives `CANCEL`. The `record` function is simply a test-defined helper. If you want to assert the exact **moment** a record is stored, synchronize with the final callback; `verify()` checks that the subscription executed the scenario, and does not replace synchronization design when testing async resources.

In Spring WebFlux, you can use `WebTestClient` to test status/body of completing/failing endpoints; for real SSE client disconnects, an integration test capable of controlling the subscription/connection is needed, not just a unit test with `Flux.range`.

## 11. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `doOnTerminate` to “catch all termination kinds” | Misses cancel, risks resource leaks | Use `doFinally` if you want to include cancel. |
| Using `doOnCancel` to catch service errors | Callback does not run when upstream emits `onError` | Use `doOnError`, `doOnTerminate`, or `doFinally` as appropriate. |
| Treating `cancel` as `onComplete` | Incorrect “success” metrics; wrong cleanup branch | Distinguish `CANCEL` from `ON_COMPLETE`. |
| Assuming upstream `doFinally(CANCEL)` always means client disconnect | `take`/`next`/`timeout` can legitimately cancel upstream | Attach hooks near the HTTP boundary and use tracing/context. |
| Placing hooks after `onErrorResume` and expecting upstream errors | Recovery can turn the output into complete | Attach `doOnError`/`doFinally` before recovery to observe source errors. |
| Using `doFinally`, reading a counter right after `block()`, and assuming it updated | Callback may arrive after terminal/downstream unblocks | Synchronize waiting for callbacks in tests. |
| Thinking `Mono.doOnTerminate` has the same order relative to `onNext` as `Flux.doOnTerminate` | Unexpected log ordering | Remember a valued Mono triggers `doOnTerminate` before `onNext`. |
| Calling `subscribe()` inside `doFinally` to write mandatory audits | Creates an unmanaged branch, no guarantee the audit finishes | Compose the publisher or use a dedicated outbox/consumer. |
| Calling JDBC/blocking I/O inside a WebFlux `doFinally` callback | Blocks I/O threads and hurts throughput | Use reactive/async cleanup scoped to the resource. |
| Attaching `doFinally` in many places and treating every callback as one request | One request can have multiple subscriptions and inner publishers | Measure the exact scope, avoid double-counting. |
| Using `doFinally` to clean up individual buffers dropped by `filter` | Callback does not know every discarded item | Use `doOnDiscard` and proper buffer ownership mechanisms. |
| Using `doOnTerminate` as a transaction rollback mechanism | Misses cancel and does not manage real rollbacks | Use transaction/resource APIs with cleanup for complete/error/cancel. |
| Letting a callback throw an exception and assuming it is “handled gracefully” | Can disrupt terminal handling or create extra errors | Keep hooks short, reliable, non-throwing; log side-effect errors properly. |

## 12. Self-Check Questions

**Question 1.** `Flux.just(1, 2).doOnCancel(...).doOnTerminate(...).doFinally(...)` is subscribed to and receives both elements. Which hooks run?  
**Answer:** `doOnTerminate` and `doFinally(ON_COMPLETE)`; `doOnCancel` does not run on normal completion.

**Question 2.** What does `Flux.error(new RuntimeException("boom"))` pass to `doFinally`? Does `doOnTerminate` run?  
**Answer:** `doFinally` receives `SignalType.ON_ERROR`, and `doOnTerminate` does run because the source terminated with an error. `doOnCancel` does not run just because of an error.

**Question 3.** `Flux.never()` is `cancel()`ed by its subscriber. Which hooks can run?  
**Answer:** `doOnCancel` and `doFinally(CANCEL)` at the point where cancel passes through; `doOnTerminate` does not run because the source did not complete/error.

**Question 4.** A `Flux.range(1, 10).take(2)` has `doFinally` before and after `take`. Must both hooks receive the same type?  
**Answer:** No. Upstream may receive `CANCEL` after two elements suffice, while downstream receives `ON_COMPLETE` because `take(2)` completes its output successfully.

**Question 5.** Why might `Mono.just("ok").doOnTerminate(...).doOnNext(...)` log terminate before next?  
**Answer:** For `Mono`, emitting a value already implies completion. `Mono.doOnTerminate` runs before the value is pushed downstream, unlike regular `Flux`.

**Question 6.** An error is turned into `Mono.just("fallback")` by `onErrorResume`. What will `doFinally` placed before and after recovery observe?  
**Answer:** The hook before recovery observes `ON_ERROR` from the source; the hook after recovery observes `ON_COMPLETE` if the fallback publisher succeeds.

**Question 7.** Is using `doFinally` to close a resource via `Mono<Void> release()` by manually calling `subscribe()` inside the callback acceptable for mandatory cleanup?  
**Answer:** Not recommended. That creates a detached subscription with no guarantee cleanup completes before the main result is observed; use `usingWhen` or an appropriate reactive resource scope.

**Question 8.** Why shouldn't you rely on `doOnCancel` running the instant a user closes their browser?  
**Answer:** The HTTP server may detect disconnect late, data may be in buffers, and cancellation is not a synchronous notification across all layers. Verify with integration tests and observe actual transport behavior.

## Key Takeaways

- **`doOnCancel`:** observes **cancellation**; callback runs before forwarding cancellation upstream at the hook's position.
- **`doOnTerminate`:** observes **completion or error**, excluding cancel; callback runs before the terminal signal is forwarded downstream. For a valued `Mono`, the hook can run before `onNext`.
- **`doFinally`:** observes **all three outcomes** and receives `SignalType.ON_COMPLETE`, `ON_ERROR`, or `CANCEL`; runs after the signal has been forwarded, suited for outcome classification/lightweight cleanup.
- **Place hooks in the right place.** `take`, `timeout`, `retry`, and `onErrorResume` can cause upstream and downstream to see different termination types.
- For real resources, prefer `using`/`usingWhen` and API-compliant discard handling; do not turn `doFinally` into a place for blocking I/O or launching unmanaged background subscriptions.
- In Spring WebFlux controllers, **return the publisher** so the framework handles HTTP subscription and cancellation; do not call `subscribe` manually to drive the pipeline.

### References

1. [Project Reactor – Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): `doOnCancel`, `doOnTerminate`, `doFinally`, `doAfterTerminate`, and `doOnDiscard`.
2. [Project Reactor – Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): differences between `Mono.doOnTerminate` and `Mono.doOnSuccess`.
3. [Project Reactor – Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): `doFinally`, `onErrorResume`, and the terminal signal model.
4. [Project Reactor – Using a Resource](https://projectreactor.io/docs/core/release/reference/advancedFeatures/using.html): reactive resource management approaches, `using`, and `usingWhen`.
5. [Reactive Streams Specification for the JVM](https://github.com/reactive-streams/reactive-streams-jvm): `Publisher`/`Subscriber`/`Subscription` contracts.
6. [Spring Framework – WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): reactive HTTP response handling, streaming, and cancellation.
