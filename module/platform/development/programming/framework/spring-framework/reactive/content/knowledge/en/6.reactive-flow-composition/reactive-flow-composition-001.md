# `concat` and `merge`: Combining Reactor Sources with Different Timing Relationships

## 1. Goal and Problem to Solve

In a Spring WebFlux application, data can come from multiple sources: two HTTP APIs responding at different speeds, data access queries, continuous event streams, or staged processing tasks. When combining those sources, the key questions are **which source is subscribed to at what time, in what order elements are emitted, and what happens when a source completes, is slow, errors, or never ends?**

Project Reactor provides two fundamental ways to combine them:

- **`Flux.concat(a, b)`**: subscribes to source `a`, forwards `a`'s elements downstream, **waits for `a` to complete successfully**, and only then subscribes to `b`. The result keeps each source's elements grouped in source order.
- **`Flux.merge(a, b)`**: subscribes to sources **eagerly** (within the concurrency limit for each overload), forwarding elements as each source emits them. Elements across sources can **interleave** according to when signals are observed; this does not necessarily match the source order in the `merge` call.

This lesson analyzes `concat` and `merge` when sources are **fast/slow, appear earlier/later, are finite/infinite, cold/hot, or error**, along with a Java 17+ test program using **virtual time**. The goal is to choose the right processing semantics rather than relying on assumptions like “merge is always faster” or “concat is always slow”.

## 2. Review of Lifecycle and Timing Concepts

A `Publisher<T>` emits data according to the Reactive Streams contract. When a subscriber subscribes, a source can emit:

```text
onSubscribe(subscription)
    -> onNext(value1)
    -> onNext(value2)
    -> ...
    -> onComplete()

or:
onSubscribe(subscription)
    -> [optional onNext]
    -> onError(exception)
```

`onComplete` and `onError` are **mutually exclusive terminal signals**. After a terminal signal, no new `onNext` is valid within the same subscription. A subscriber can call `cancel()` to cancel; cancellation is different from the source sending `onComplete`.

Three points in time should be distinguished:

1. **Publisher creation time**: Java code calls `Flux.just(...)`, `WebClient...bodyToFlux(...)`, etc., creating an expression that describes a pipeline; a typical *cold* source does not perform work until a subscription occurs.
2. **Subscription time**: the upstream is subscribed to and can start I/O operations or emit data. This is the point where `concat` and `merge` differ most clearly.
3. **Signal reception time**: downstream observes `onNext`, `onError`, or `onComplete`; this may differ from the time the actual event was generated in an external system.

**Different timing relationships** can mean one source starts late, source A emits every 200 ms while B emits every 50 ms, or source B is already *hot* and emits events before we subscribe. `concat` and `merge` handle these situations under two different contracts.

## 3. `concat`: Sequential Processing, Waiting for Completion Before Switching Sources

Basic path when both sources are finite:

```text
Source A:      A1 ---- A2 ---- COMPLETE
                         |
Source B:                 |        B1 -- B2 -- COMPLETE
                          |        ^
Subscribe B:              +--------+ (only after A's COMPLETE)

concat:        A1 ---- A2 --------- B1 -- B2 -- COMPLETE
```

With cold sources, when downstream subscribes to `Flux.concat(A, B)`:

1. Reactor subscribes to A first.
2. When A emits `onNext`, downstream receives A's elements in emission order.
3. If A completes empty (`Flux.empty()`), concat can move to B immediately.
4. If A emits `onComplete`, Reactor subscribes to B; B begins producing elements according to B's own lifecycle.
5. If A emits `onError`, concat terminates with an error by default and does **not** continue to B. If A never completes, B is never subscribed to.

A simple example with no asynchronous work:

```java
Flux<String> a = Flux.just("A1", "A2");
Flux<String> b = Flux.just("B1", "B2");

Flux<String> combined = Flux.concat(a, b);
```

A normal subscriber will see the order `A1`, `A2`, `B1`, `B2`, `onComplete`. This is an illustrative snippet inside an application that already has the Reactor dependency and imports `reactor.core.publisher.Flux`, not a standalone Java file.

Common ways to write it:

```java
Flux<String> usingConcat = Flux.concat(a, b);
Flux<String> usingConcatWith = a.concatWith(b);
```

Both expressions have the same meaning for these two sources. For sources defined as `Publisher<Publisher<T>>`, Reactor also has the `Flux.concat(publishers)` overload to concatenate inner publishers sequentially.

**Concat's order is *source* order, not sorting by every record's timestamp.** If A contains an event with timestamp 10:05 and B contains timestamp 10:02, concat still outputs A's data before B's. To merge by *event time*, you need dedicated time-handling design with watermarks/buffering/sorting; `concat` cannot be treated as a sorting algorithm.

## 4. `merge`: Eager Subscription and Interleaving as Signals Arrive

`Flux.merge(A, B)` typically subscribes to both A and B when downstream subscribes (for these two finite sources). Both sources can be active at the same time. Downstream receives elements depending on emission speed:

```text
Time (ms):         0       50      100      200              400
Source A (200 ms):                          A1               A2
Source B (50 ms):          B1      B2
merge output:              B1      B2       A1               A2
```

Unlike concat, **merge does not wait for A to complete before B starts**. With a fast source B and a slow source A, B can emit first even though A was passed first to the function.

```java
Flux<String> merged = Flux.merge(a, b);
Flux<String> alsoMerged = a.mergeWith(b);
```

When `a` and `b` are just synchronous `Flux.just`, the output can look like concat because the first source emits everything immediately within a single call stack. To see real interleaving, you need sources with asynchronous waiting or emitting on appropriate schedulers. **`merge` does not automatically create a separate thread for each source**; interleaving depends on how the sources emit signals and their scheduler/runtime.

Some constraints:

- `merge` does not guarantee **ordering across sources**; when two signals arrive at nearly the same time, the observed order can vary with scheduling.
- For Reactive Streams-compliant publishers, `onNext` order *within each individual source* is still preserved; merge does not reorder A1/A2 within stream A.
- The merged result only emits `onComplete` when **all involved sources have completed successfully**.
- An error from any source by default can terminate the merge with an error and cancel other sources; you must not assume elements not yet emitted will still arrive.
- Merge is designed to work well for asynchronous or finite sources; if an infinite source emits synchronously without yielding execution, other sources can be starved while merge tries to consume it. Sources and schedulers must be arranged appropriately.

Do not use `merge` if the API contract requires “finish reading page 1 before reading page 2” or “step B only starts after step A succeeds”. Those order-dependent requirements fit `concat` or a sequential operator chain better.

## 5. Timing Example: Slow A 200 ms, Fast B 50 ms

Suppose two **cold, finite** sources each emit two elements and apply a delay to *each element*:

```java
Flux<String> slowA() {
    return Flux.just("A1", "A2")
            .delayElements(Duration.ofMillis(200));
}

Flux<String> fastB() {
    return Flux.just("B1", "B2")
            .delayElements(Duration.ofMillis(50));
}
```

These are two illustrative methods inside a Java class importing `java.time.Duration` and `reactor.core.publisher.Flux`. `delayElements` uses Reactor's scheduling mechanism to delay signals; it is **not `Thread.sleep` blocking an event-loop thread**.

If downstream begins subscribing at relative time `t=0`, with no extra system load on sources A/B or the pipeline:

| Relative time | `Flux.concat(slowA(), fastB())` | `Flux.merge(slowA(), fastB())` |
|---|---|---|
| `t = 0` | Subscribe A; B not subscribed yet | Subscribe A and B |
| `t ≈ 50 ms` | No element yet | B1 |
| `t ≈ 100 ms` | No element yet | B2, B completes |
| `t ≈ 200 ms` | A1 | A1 |
| `t ≈ 400 ms` | A2, A completes; **only now subscribe B** | A2, A completes; merge completes |
| `t ≈ 450 ms` | B1 | Already completed |
| `t ≈ 500 ms` | B2, concat completes | Already completed |

The table above is an **idealized scheduler logic model**. On a real machine, millisecond timestamps have jitter and two close events can swap order. When you need to test ordering reproducibly, use **virtual time** as in section 7.

Important consequences:

1. Concat completes after approximately the **sum** of the sources' durations in the example: 400 + 100 = 500 ms.
2. Merge completes after approximately the **duration of the slowest source**: max(400, 100) = 400 ms, if resources allow the sources to run concurrently.
3. These numbers only reflect **two independent, cold sources with no resource limits**. Concurrency can increase load, reduce efficiency due to connection pool contention, or overload upstream.
4. The biggest difference is not just completion speed: concat creates an **ordering boundary**, while merge creates a **progress-based unified output channel**.

## 6. Determining Which Order Must Be Preserved

| Business requirement | Appropriate approach | Reason |
|---|---|---|
| Read consecutive pages of data where the next page depends on the previous page | `concat`/`concatMap` or sequential chain | Next source only starts when previous completes |
| Combine multiple known lists sequentially by group | `concat` | No interleaving between groups |
| Collect results from multiple independent APIs as soon as each responds | `merge` | Eager start, emit as progress happens |
| Unify notifications from multiple independent event sources | `merge` | Not forced to wait for one source to finish |
| Run multiple sources eagerly but still emit all of A before B | `mergeSequential` | Eager subscription, buffering later sources' results to keep groups |
| Need to *pair* one element from A with one element from B | `zip` | Pairwise combination, distinct from concatenation/interleaving |
| Need elements in globally increasing timestamp order | Build custom event-time processing | `merge` does not globally sort by time |

**Choose based on the data contract.** An API reading logs in file order may need concat; a dashboard showing new events from multiple services may need merge. If ordering affects transactional correctness, do not replace concat with merge merely to reduce latency.

## 7. Runnable Java 17+ Example: Verifying with `StepVerifier` and Virtual Time

The test program below demonstrates the ordering of three combination approaches on **the same two sources with different speeds** without waiting in real time. It uses Maven, Java 17+, and Project Reactor Core. `StepVerifier` comes from `reactor-test`, and `JUnit Jupiter` runs the tests.

Directory structure:

```text
reactor-combination-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── edu/
                └── demo/
                    └── ConcatMergeTest.java
```

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.demo</groupId>
    <artifactId>reactor-combination-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.6</version>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <version>3.6.6</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
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
                <version>3.2.5</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Create `src/test/java/edu/demo/ConcatMergeTest.java`:

```java
package edu.demo;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class ConcatMergeTest {

    private static Flux<String> slowA() {
        return Flux.just("A1", "A2")
                .delayElements(Duration.ofMillis(200));
    }

    private static Flux<String> fastB() {
        return Flux.just("B1", "B2")
                .delayElements(Duration.ofMillis(50));
    }

    @Test
    void concatWaitsForAThenStartsB() {
        StepVerifier.withVirtualTime(
                    () -> Flux.concat(slowA(), fastB()))
                .expectSubscription()
                .thenAwait(Duration.ofMillis(600))
                .expectNext("A1", "A2", "B1", "B2")
                .verifyComplete();
    }

    @Test
    void mergeInterleavesByObservedArrival() {
        StepVerifier.withVirtualTime(
                    () -> Flux.merge(slowA(), fastB()))
                .expectSubscription()
                .thenAwait(Duration.ofMillis(600))
                .expectNext("B1", "B2", "A1", "A2")
                .verifyComplete();
    }

    @Test
    void mergeSequentialStartsEarlyButKeepsSourceOrder() {
        StepVerifier.withVirtualTime(
                    () -> Flux.mergeSequential(slowA(), fastB()))
                .expectSubscription()
                .thenAwait(Duration.ofMillis(600))
                .expectNext("A1", "A2", "B1", "B2")
                .verifyComplete();
    }
}
```

Run in the project directory:

```bash
mvn test
```

Once dependencies are downloaded and the code runs successfully, **all 3 tests PASS** (`Tests run: 3, Failures: 0, Errors: 0, Skipped: 0` in the Surefire summary; other build log lines depend on the environment). The assertions in the code are the exact test results:

```text
concat:          A1, A2, B1, B2 -> complete
merge:           B1, B2, A1, A2 -> complete
mergeSequential: A1, A2, B1, B2 -> complete
```

Why this example is deterministic:

- `StepVerifier.withVirtualTime(...)` activates a virtual scheduler and uses `thenAwait(...)` to advance the clock without waiting in real time.
- **Create the pipeline inside the lambda/supplier** passed to `withVirtualTime`. Do not create a publisher with time operators beforehand and pass it into the lambda, because it may have already captured the real scheduler.
- No two elements from different sources are expected at the exact same timestamp (B1=50, B2=100, A1=200, A2=400), so the merge test does not depend on arbitrary scheduling tie-breaking.
- For concat, B is only subscribed to after A finishes around 400 ms, so B1 and B2 appear around 450/500 ms respectively.
- For mergeSequential, B can finish early and be buffered, but downstream only sees B after all of A has been emitted.

**Limitations of the example:** The delays are simulated data, not a benchmark of CPU, WebFlux HTTP, or real-system latency. Test ordering is guaranteed by virtual scheduler logic; it does not mean independent I/O calls in a real environment will always return in the same order.

## 8. `mergeSequential`: Concurrent Progress While Preserving Source Groups

There are cases where you want to start independent HTTP calls at the same time yet return the response as “all results of A, then all results of B”. Reactor has `Flux.mergeSequential(A, B)`:

```java
Flux<String> ordered = Flux.mergeSequential(
        slowA(),
        fastB()
);
```

- **Like merge:** subscribes to inner sources eagerly, within the concurrency limit; B can do work while A is not yet finished.
- **Like concat in output:** downstream still receives A1, A2, then B1, B2.
- **Different from concat in resources:** if B is fast and A is slow, B's elements may have to be **buffered while waiting**. When later sources emit large amounts of data, the buffer can grow large; you need to bound concurrency/prefetch and check backpressure, timeout, and memory capacity needs.

This is a trade-off between **reducing wait time for later sources** and **buffer demand to preserve order**. `mergeSequential` is not a `sort`: it preserves *source group order*, not element timestamps across multiple sources.

Corresponding operators when sources are created from each upstream element:

```java
Flux<String> ids = Flux.just("A", "B", "C");

// Call fetch(id) one by one; each previous publisher must complete.
Flux<String> sequential = ids.concatMap(id -> fetch(id));

// Can subscribe to publishers created by fetch(id) eagerly, interleaving results.
Flux<String> interleaved = ids.flatMap(id -> fetch(id));

// Can run multiple fetches concurrently while emitting in A, B, C order.
Flux<String> orderedConcurrent =
        ids.flatMapSequential(id -> fetch(id));
```

This is an **illustrative snippet**: `fetch(String id)` must be a defined method returning `Publisher<String>`/`Mono<String>`/`Flux<String>`; it is not a standalone program. For infinite or resource-heavy sources, choose overloads with bounded `concurrency` and `prefetch`, and measure queue capacity.

## 9. Cold and Hot Sources: Subscription Timing Can Lose Data

The difference between concat and merge is not just “printed earlier or later”; it also determines **when a source begins to be observed**.

### Cold publisher

A *cold* source usually starts new work for each subscription. For example, a `Flux.just(...)`, `Flux.range(...)`, or a cold reactive network pipeline can create a separate execution for each subscriber. In the test in section 7, A and B are cold.

- With concat, B is **not subscribed to yet** until A completes. Therefore, B's intrinsic delay only begins counting after A.
- With merge, A and B are subscribed eagerly and can begin waiting on I/O in parallel.

`Flux.interval(...)` is also typically a **cold per-subscription source**: each subscriber gets its own timing cadence. Not every timer-based stream should be called hot.

### Hot publisher

A *hot* source can emit data regardless of whether a specific subscriber arrives: for example, an event bus, a device emitting signals, or an already-active `Sinks.Many`. History retention depends on the sink or replay mechanism.

Suppose `hotB` emits B1 at `t=50 ms` and B2 at `t=100 ms`, while A only completes at `t=400 ms`:

```text
hotB:          B1(t=50)  B2(t=100) -------------------->
A:            -------------------------- complete(t=400)
concat(A,B):   subscribe A                 subscribe hotB(t=400)
```

In a **non-replaying** hot source, concat subscribes to B too late and **can miss B1/B2**. Merge subscribes to B earlier so it has a chance to receive those events. However, merge also cannot recover events emitted before merge itself subscribed.

If the business requirement cannot afford to drop events, explicitly design **replay, history storage, checkpoint/cursor, or a message broker** rather than assuming any stream-combining operator stores data automatically.

## 10. When Sources Are Empty, Error, or Never Complete

### 10.1. Empty sources (`empty`)

```java
Flux<String> result = Flux.concat(
        Flux.<String>empty(),
        Flux.just("B")
);
```

With concat, the first source immediately emits `onComplete`, then the second source is subscribed to; the result is `B`, complete.

With merge, empty contributes no elements; merge still waits for the remaining source to complete:

```java
Flux<String> result = Flux.merge(
        Flux.<String>empty(),
        Flux.just("B")
);
```

The result is also `B`, complete, though the subscription mechanics differ.

### 10.2. Erroring sources (`error`)

```java
Flux<String> later = Flux.just("B");

Flux<String> concatFailed = Flux.concat(
        Flux.<String>error(new IllegalStateException("A failed")),
        later
);
```

`concatFailed` emits `onError`; source B is **not subscribed to** under concat's normal success flow.

```java
Flux<String> mergedFailed = Flux.merge(
        Flux.<String>error(new IllegalStateException("A failed")),
        later
);
```

In merge, an error is terminal; active sources are cancelled/cut off according to execution. **Do not assume a specific number of B's elements will be seen** when there is a race between an error signal and concurrent data. Test the actual code and design explicit error handling.

If you need to **emit the error after other sources have had a chance to run**, Reactor provides variants:

```java
Flux<String> concatDelayedError = Flux.concatDelayError(
        Flux.just("A"),
        Flux.<String>error(new IllegalStateException("failed")),
        Flux.just("B")
);

Flux<String> mergeDelayedError = Flux.mergeDelayError(
        16,
        Flux.just("A"),
        Flux.<String>error(new IllegalStateException("failed")),
        Flux.just("B")
);
```

This snippet assumes `Flux` is imported; `16` in the `mergeDelayError` overload is the inner source `prefetch`, **not a timeout or requests-per-second limit**. With `concatDelayError`, data after the failing source can still be processed before reporting the combined error. With `mergeDelayError`, the error is deferred until the merge backlog finishes processing; delayed errors should not be used in systems that require fail-fast behavior for safety or correctness.

An error at the end is still an error: `DelayError` **does not fix** a broken dependency and does not roll back already-emitted elements. When a fallback is needed, you can use `onErrorResume` in the appropriate place.

### 10.3. Never-completing sources (`never`)

```java
Flux<String> concatNever = Flux.concat(
        Flux.<String>never(),
        Flux.just("B")
);
```

The first source never sends `onComplete`; concat **never subscribes to B** without an external timeout or cancellation mechanism.

```java
Flux<String> mergeNever = Flux.merge(
        Flux.<String>never(),
        Flux.just("B")
);
```

Merge can still emit `B`, but **never emits `onComplete`** because the never source never finishes. This matters when using `.collectList()`: it requires `onComplete` to return the list, so it can wait indefinitely.

You can bound time at an appropriate boundary:

```java
Flux<String> bounded = Flux.merge(
        Flux.<String>never(),
        Flux.just("B")
).timeout(Duration.ofSeconds(2));
```

`timeout(Duration)` applies to the **interval between `onNext` signals**, or the wait from subscription to the first signal; after receiving `B`, it can still time out if no next signal arrives within 2 seconds. The duration must be chosen based on business requirements. Sometimes you need an **overall execution deadline**, different from an idle timeout; apply the deadline at the request/client layer or use an appropriate operator such as `take(Duration)` when early completion is acceptable. Never call `.block()` unboundedly on a never-ending source.

## 11. Backpressure, Concurrency, and Memory Capacity

Both `concat` and `merge` honor downstream demand under the Reactive Streams contract, but they distribute requests and buffer differently.

**Concat**:

- Only one inner source is subscribed to for emitting data at a time (per sequential concatenation semantics).
- Simplifies ordering and reduces the number of I/O sources active simultaneously.
- Downside is high total latency when independent sources are forced to execute sequentially.

**Merge**:

- Multiple sources can be active simultaneously, typically using internal buffers/queues and distributing demand to each source.
- Requires controlling how many sources are subscribed concurrently and `prefetch` when merging a large number of publishers.
- If upstream emits very fast or downstream is slow, queues, memory, connection pools, and source limits must be monitored. Backpressure **does not mean** zero buffering ever happens.
- Merging infinite sources that emit synchronously without yielding the scheduler can starve other sources of progress; emission and scheduling must be designed appropriately.

Example when the list of sources is produced on demand:

```java
// sources is a Flux<Publisher<String>> created elsewhere.
Flux<String> limited = Flux.merge(sources, 4, 16);
```

This is a snippet, not standalone-compilable. `4` is the **maximum concurrency for inner publishers** in the publisher-of-publishers overload; `16` is **prefetch**, i.e. the initial number of elements requested from each inner source, not a byte limit or actual HTTP request count. `Publisher` belongs to `org.reactivestreams.Publisher`.

With multiple network sources, the number of concurrent requests is also affected by the HTTP client's connection pool, timeouts, retries, quotas, and upstream rate limits. Raising concurrency too high does not guarantee higher throughput.

## 12. Applying in a Spring WebFlux Service

Suppose an application needs to unify two separate notification sources: a slower security alert source and a faster-updating task status source. Both reactive clients return `Flux<Notice>`:

```java
// Snippet inside a @Service with two reactive clients injected.
public Flux<Notice> allNotices() {
    Flux<Notice> security = securityClient.streamNotices();
    Flux<Notice> operations = operationsClient.streamNotices();

    return Flux.merge(security, operations);
}
```

This is an **architectural snippet**, not a standalone Spring Boot file: `Notice`, `securityClient`, and `operationsClient` are application types/beans, and `streamNotices()` must actually return a publisher. Use merge if the goal is **to display notices from either source as they arrive**, without waiting for the alert source to finish.

If the API contract states “return all historical data from source A first, then continue with source B's data”, using concat only makes sense when A **will complete** and late subscription to B **will not lose critical events**:

```java
return Flux.concat(
        securityClient.loadHistory(),
        operationsClient.loadRecentBatch()
);
```

Both methods in the snippet must return an appropriate `Publisher<Notice>`. If source B is a non-replaying hot stream, the risk of missing events on late subscription must be solved (e.g., via a cursor/replay mechanism) before using concat.

For an API that needs **to return JSON once after sources complete**, you can combine the `Flux` and call `.collectList()`, though if any source is infinite you will never get a complete list. For **SSE**, a merged `Flux` is useful for streaming elements as they progress:

```java
@GetMapping(value = "/notices",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<Notice> notices() {
    return noticeService.allNotices();
}
```

This is also a snippet to place inside a `@RestController` with `noticeService` injected and importing `org.springframework.http.MediaType`, `org.springframework.web.bind.annotation.GetMapping`, and `reactor.core.publisher.Flux`. HTTP streaming also depends on codecs, timeouts, disconnect handling, and the transport/client's backpressure support.

**Do not call `.block()` or `.subscribe()` inside a WebFlux controller to “force” merge to run.** Return the publisher so Spring manages the subscription, translates signals into the HTTP response, performs error handling, and observes cancellation when the client disconnects.

## 13. Observing Subscription Timing and Signals in Practice

A more reliable debugging technique than just looking at output is attaching `doOnSubscribe`, `doOnNext`, and `doFinally` to each source:

```java
Flux<String> observedA = slowA()
        .doOnSubscribe(s -> System.out.println("A subscribed"))
        .doOnNext(v -> System.out.println("A next: " + v))
        .doFinally(s -> System.out.println("A finally: " + s));

Flux<String> observedB = fastB()
        .doOnSubscribe(s -> System.out.println("B subscribed"))
        .doOnNext(v -> System.out.println("B next: " + v))
        .doFinally(s -> System.out.println("B finally: " + s));

Flux<String> result = Flux.concat(observedA, observedB);
// Can be replaced with Flux.merge(observedA, observedB) to compare.
```

The code above is a snippet; `slowA()` and `fastB()` are defined in section 7. When **there is a subscriber**:

- Concat: the `B subscribed` log only appears after A emits terminal `onComplete`.
- Merge: the two subscribe logs usually appear close together before asynchronous elements are received.
- `doFinally` distinguishes `ON_COMPLETE`, `ON_ERROR`, and `CANCEL`; it is also helpful when a subscriber cancels the stream or downstream `take(n)` has received enough elements.
- Logs from multiple schedulers can interleave at very close timestamps; do not treat tightly spaced log order as proof of event-time guarantees.

Be careful that **code outside the pipeline can run immediately**, even before source B is subscribed to:

```java
Flux<String> b = buildPublisher(); // this method is called immediately in Java
Flux<String> c = Flux.concat(slowA(), b);
```

`concat` delays **subscribing** to `b`, rather than guaranteeing that every side effect inside `buildPublisher()` during object construction is delayed. If you need to defer creating the source until subscription time, consider:

```java
Flux<String> delayedBuild = Flux.defer(() -> buildPublisher());
Flux<String> c = Flux.concat(slowA(), delayedBuild);
```

`Flux.defer` invokes the supplier when subscription begins, avoiding premature initialization side effects. Even so, uncontrolled side effects in publisher-building methods should still be avoided.

## 14. Common Misconceptions and Mistakes

| Misconception/mistake | What actually happens | How to handle it |
|---|---|---|
| “`concat` and `merge` differ only in speed” | They also differ in **subscription timing**, emission order, errors, and impact on hot sources | Choose based on ordering and lifecycle contracts |
| “Passing A first to merge means A always comes out before B” | A fast B can emit first | Do not rely on source order when using merge |
| “`merge` always creates two threads” | The operator does not allocate a dedicated thread per source | Check schedulers, I/O clients, and how upstream emits |
| “`concat` sorts events by timestamp” | Concat preserves source groups, not event time | Use an appropriate event-time processing design |
| “`merge` always makes results faster” | Concurrency is constrained by CPU, pools, network, and backend | Benchmark with realistic workload and monitor resources |
| “A hot source B still keeps history when concat subscribes late” | Some hot sources do not replay; already-emitted data can be lost | Use replay/cursor/broker when needed |
| “`merge` completes as soon as the first source finishes” | All involved sources must complete successfully | Separate infinite streams if a finite result is desired |
| “`Flux.never()` can be skipped by `concat`” | Never does not emit `onComplete`, so concat does not switch sources | Use timeout/cancel, or substitute an empty source properly |
| “Merge keeps source grouping like concat” | Merge allows interleaving | Use concat or mergeSequential |
| “`mergeSequential` is free in memory” | Later sources may have to be buffered while waiting for earlier ones | Bound concurrency/prefetch and load test |
| “`delayError` turns an error into success” | The error is only deferred and remains a terminal error | Use intentional fallback when business rules allow |
| “A test using real clock will always produce B1,B2,A1,A2” | Scheduling and system load can introduce jitter | Test timing with StepVerifier virtual time |

## 15. Reasoning Exercises

**Exercise 1.** Both sources are cold: A emits `A1` after 3 seconds then completes, B emits `B1` after 1 second then completes. If subscribed at `t=0`, what are the idealized order and total duration for concat/merge?

- `concat(A,B)`: A1 around `t=3s`, then subscribe B, B1 around `t=4s`, then complete.
- `merge(A,B)`: B1 around `t=1s`, A1 around `t=3s`, then complete.

**Exercise 2.** A = `Flux.just("A").concatWith(Flux.never())`; B = `Flux.just("B")`. What happens?

- `Flux.concat(A,B)` emits A and waits forever, never subscribing to B.
- `Flux.merge(A,B)` can emit both A and B, but never completes because A contains `never()`; ordering between A and B across the two sources is not strictly guaranteed.

**Exercise 3.** A hot source emits a message at `t=100ms`, while concat only subscribes to it at `t=500ms`. Can the message be recovered?

- There is no guarantee. With a non-replaying hot source, the message may already be lost. Recovering it requires a pre-designed storage/replay/cursor mechanism.

**Exercise 4.** You need to call three independent APIs concurrently but present results in the order A → B → C. Which operator should you choose?

- Consider `mergeSequential` or `flatMapSequential`, with appropriate concurrency/buffer limits. `concat` also preserves order but delays subscription to later APIs; `merge` does not preserve source groups.

**Exercise 5.** Source A emits an error before B finishes in `merge(A,B)`. Are all elements already generated by B guaranteed to appear in the result?

- No. A terminal error can cut off/cancel B. If you want to wait for other results, consider per-source error handling or `mergeDelayError` depending on business requirements.

## 16. Selection Conclusion

When dealing with multiple data sources with different timing relationships, answer three questions in order: **which sources are allowed to start immediately, what order must the output preserve, and what condition terminates the overall flow?**

- Use **`concat`** when one source must be fully processed and emit `onComplete` before starting the next source; preserves source group order.
- Use **`merge`** when multiple independent sources may start eagerly and results can be displayed as they progress, without requiring source group order.
- Use **`mergeSequential`** when you want eager startup while still preserving source group order, accepting extra buffering and needing resource control.

Then check for risks of **non-replaying hot sources**, **never-completing sources**, **error propagation**, timeouts/cancellation, and **concurrency/backpressure** levels. These are the factors that determine the correctness of a reactive program in Spring WebFlux.

## Official Documentation

- Project Reactor, **Flux API: concat, merge, mergeSequential, delayElements**: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Project Reactor, **Which operator do I need?**: https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html
- Project Reactor, **Testing with StepVerifier and virtual time**: https://projectreactor.io/docs/core/release/reference/testing.html
- Project Reactor, **Hot Versus Cold**: https://projectreactor.io/docs/core/release/reference/advancedFeatures/reactor-hotCold.html
- Spring Framework, **WebFlux overview**: https://docs.spring.io/spring-framework/reference/web/webflux.html