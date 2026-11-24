# flatMapSequential: Combining Concurrent Processing with Ordered Output in Project Reactor

In Spring WebFlux and Project Reactor, we often need to process many input elements using asynchronous tasks: making HTTP calls, querying reactive databases, decoding payloads, or fetching enrichment data. Running **one task at a time** can accumulate waiting time. Running **concurrently** with `flatMap` may return results out of input order. The **`Flux.flatMapSequential(...)`** operator solves cases that need both properties: **starting/subscribing to multiple subtasks eagerly, while emitting results downstream in the order of the source elements**.

This lesson is about **data transformation with `flatMapSequential`**, not about guaranteeing the order of all side effects or of external systems. You must clearly distinguish **input order**, **subtask completion order**, **order received downstream**, and **order in which side effects occur**.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the three phases of `flatMapSequential`: **map element to inner publisher → subscribe concurrently with a limit → emit results in source order**.
- Accurately compare `flatMap`, `concatMap`, and `flatMapSequential` in terms of **subscription timing**, **concurrency**, **output order**, **interleaving**, and **buffering memory**.
- Use `flatMapSequential(mapper, maxConcurrency, prefetch)` when making non-blocking I/O calls and display order must be preserved.
- Understand how inner publishers emit **0, 1, or multiple elements**, and how the operator keeps **each result slice** corresponding to one input intact.
- Recognize **head-of-line blocking**: a slow leading task causes subsequent results to be held back.
- Handle timeouts, errors, empty results, cancellation, and backpressure so the pipeline neither stalls nor consumes excessive resources.
- Write a standalone runnable Java 17+ example and use `StepVerifier` to verify both ordering and eager subscription.

## 2. Core Problem: Concurrency and Ordering Are Two Different Axes

Suppose a source emits three job IDs in exact order:

```text
Source:             [1] ── [2] ── [3]

Task duration:       1: ├───────────────────────────┤  slow
                     2:    ├──────┤                   fast
                     3:       ├─────────┤             medium

Completion order:             2       3             1
Display order needed:         1       2             3
```

If a request to “fetch info for ID 1” takes 300 ms, ID 2 takes 30 ms, and ID 3 takes 80 ms, then ID 2 can finish first. **Concurrency** allows multiple tasks waiting on I/O to exist at the same time; **emission order** determines which one the subscriber sees first.

- `concatMap` preserves order by waiting for the previous inner publisher to complete before subscribing to the next one: easy to reason about, but misses the opportunity to overlap I/O waiting times.
- `flatMap` subscribes eagerly to multiple inner publishers and emits elements as they arrive: leverages concurrency, but order can interleave.
- `flatMapSequential` also subscribes eagerly to inner publishers, yet **holds back early-arriving results from later publishers**, waiting until earlier publishers finish before moving on to the next result slice.

**Preserving emission order** is not synonymous with **sequential execution**. An HTTP request sent later may still reach its destination, write logs, or mutate external data before an earlier request; `flatMapSequential` only controls the order of **elements emitted downstream**.

## 3. The Three-Step Mechanism of flatMapSequential

Visualize a source `Flux.just(A, B, C)` mapped into three inner publishers:

```text
Upstream Flux
     A              B               C
     │              │               │
     ▼              ▼               ▼
mapper(A)       mapper(B)        mapper(C)
     │              │               │
     ▼              ▼               ▼
inner A          inner B           inner C
(slow)           (finishes early)  (finishes early)
     │              │               │
     │          [waiting in       [waiting in
     │           buffer]           buffer]
     ▼              ▼               ▼
                flatMapSequential
                       │
                       ▼
Downstream:    [all of A] → [all of B] → [all of C]
```

Step-by-step mechanics:

1. The source emits element `A`. The mapper creates inner publisher `inner A`; `flatMapSequential` subscribes to that inner source when demand/capacity allows.
2. It does not have to wait for `inner A` to finish before subscribing to `inner B` and `inner C`; the number of active inner publishers is bounded by `maxConcurrency` if configured.
3. If `inner B` returns results before `inner A`, the operator holds B's data in a buffer to preserve the correct order.
4. `inner A`'s data is emitted downstream as demand arrives. Only when `inner A` completes does the operator switch to emitting slice B, then slice C.
5. As inner publishers complete or cancel, freed slots in the concurrency limit can be used to subscribe to subsequent tasks.

**The preserved order is the order of source elements entering the operator**, after any prior sorting/filtering. If the source actually feeds IDs in order C, A, B, then `flatMapSequential` preserves C, A, B; it does not infer business order from IDs, timestamps, or request creation order.

### An Inner Publisher Can Emit Multiple Elements

Given source A, B:

```text
inner A emits:      A1 --- A2 --- A3
inner B emits:          B1 - B2 (arrives early)
downstream sees:   A1 --- A2 --- A3 --- B1 - B2
```

The operator preserves **the entire data slice of each inner publisher** in source order and does not mix B1 in between A1, A2, and A3. With an inner `Mono<R>`, each slice has at most one element; with an inner `Flux<R>`, there can be many elements. If an inner publisher completes empty, that slice has length 0: downstream still preserves the order of the remaining slices, though output count may be smaller than input count.

## 4. Comparing Three Easily Confused Operators

| Criterion | `flatMap(mapper)` | `concatMap(mapper)` | `flatMapSequential(mapper)` |
| --- | --- | --- | --- |
| Inner publisher subscription | Eager, possibly multiple inners at once | Sequential: waits for previous inner to finish before moving to the next | Eager, possibly multiple inners at once |
| Elements from inner publishers | Can interleave | Slice by slice, in source order | Slice by slice, in source order |
| Downstream order | Depends on when elements arrive | Follows input order | Follows input order |
| Independent I/O can overlap | Yes | Not under the sequential subscription model | Yes |
| Must hold early results waiting their turn | Usually no, since it merges on arrival | Does not need buffering to reorder slices like this | **Yes**, especially when an earlier inner is slow |
| Common risk | Out-of-order output | Long wait times, low throughput | Buffer memory and head-of-line blocking |
| When appropriate | Independent processing, prioritizing earliest results | Must finish the previous task before starting the next | Run I/O concurrently, return data in input order |

For example, if three tasks are subscribed together and finish in order 2 → 3 → 1:

- `flatMap` may emit `2, 3, 1` (order also depends on execution scheduling).
- `flatMapSequential` emits `1, 2, 3`.
- `concatMap` also emits `1, 2, 3`, but task 2 is only subscribed after task 1 completes; thus the scenario “2 finishes before 1” cannot happen with cold inners subscribed strictly sequentially.

Not every program using `flatMap` reorders output; if inner publishers run fast synchronously or finish in order, output can still happen to preserve order. **Do not use a single run's output to infer an API contract guarantee.**

### Is map Like flatMapSequential?

`map(fn)` turns **one element into one synchronous value**; `flatMapSequential(fn)` turns an element into a **Publisher** and merges data from those Publishers in order. For example, `map(id -> webClient.get()...)` only creates `Flux<Mono<User>>` if the mapper returns `Mono<User>`, without executing or flattening the HTTP calls. Choose `flatMapSequential(id -> fetch(id))` when you need to unpack those inner publishers into an ordered `Flux<User>`.

## 5. Key Overloads and Parameter Meanings

Common Reactor APIs:

```java
<R> Flux<R> flatMapSequential(
    Function<? super T, ? extends Publisher<? extends R>> mapper);

<R> Flux<R> flatMapSequential(
    Function<? super T, ? extends Publisher<? extends R>> mapper,
    int maxConcurrency);

<R> Flux<R> flatMapSequential(
    Function<? super T, ? extends Publisher<? extends R>> mapper,
    int maxConcurrency,
    int prefetch);
```

These are **conceptual API signatures** for explanation; normally you call `flux.flatMapSequential(...)` directly rather than declaring these methods yourself.

- **`mapper`**: receives a source element of type T and returns `Publisher<? extends R>`. Commonly a `Mono<R>` from WebClient, R2DBC, or an inner `Flux<R>`.
- **`maxConcurrency`**: limits the number of **concurrently subscribed/active inner publishers**. For example, `4` allows at most four in-flight inners within one subscription of the operator; the value must be positive. This should not be interpreted as “create exactly four threads”.
- **`prefetch`**: how many elements to request from **each inner publisher** before downstream has consumed them all. Used to tune how many elements may be in flight and buffered; an appropriate value depends on element size and downstream speed.

Concrete configuration example:

```java
Flux<Result> results = ids.flatMapSequential(
    id -> reactiveClient.fetch(id),
    8,  // at most 8 active inner publishers
    1   // prefetch 1 element from each inner
);
```

`ids`, `Result`, and `reactiveClient` in this example are **application-provided components**, not a standalone program. If `fetch` returns `Mono<Result>`, each inner has only 0 or 1 value; setting `prefetch = 1` is easy to reason about in examples. If the inner is a data-heavy `Flux`, prefetch tuning should be based on actual traffic.

**Note:** `maxConcurrency` bounds inner subscriptions, not CPU concurrency or total application-wide connections. Multiple separate HTTP requests can each create a new pipeline with its own limit. You still need connection pools, rate limits, overall load limits, and service-level resource measurement.

## 6. Runnable Java 17+ Demo: Asynchronous Yet Ordered Output

This example uses `Mono.delay` to simulate three I/O operations completing with different durations. Because `Mono.delay` uses a scheduler, waiting intervals can overlap **without blocking threads with `Thread.sleep`**. Output display uses `collectList()` so stdout is simple and deterministic.

Create the layout:

```text
reactor-ordered-merge/
├── pom.xml
├── src/main/java/OrderedMergeDemo.java
└── src/test/java/OrderedMergeTest.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>reactor-ordered-merge</artifactId>
  <version>1.0-SNAPSHOT</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-core</artifactId>
      <version>3.6.9</version>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
      <version>3.6.9</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.10.3</version>
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
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.3.0</version>
      </plugin>
    </plugins>
  </build>
</project>
```

`src/main/java/OrderedMergeDemo.java`:

```java
import java.time.Duration;
import java.util.List;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class OrderedMergeDemo {

    private static Mono<String> fetch(int id) {
        long latencyMillis = switch (id) {
            case 1 -> 300;
            case 2 -> 30;
            case 3 -> 80;
            default -> 50;
        };

        return Mono.delay(Duration.ofMillis(latencyMillis))
            .map(tick -> "result-" + id);
    }

    public static void main(String[] args) {
        List<String> ordered = Flux.just(1, 2, 3)
            .flatMapSequential(OrderedMergeDemo::fetch, 3, 1)
            .collectList()
            .block();

        System.out.println(ordered);
    }
}
```

Run in the project directory:

```bash
mvn -q compile exec:java -Dexec.mainClass=OrderedMergeDemo
```

Stdout from `main`:

```text
[result-1, result-2, result-3]
```

Explanation:

1. `Flux.just(1, 2, 3)` emits three IDs in order 1 → 2 → 3.
2. The mapper creates three separate `Mono`s. Because `maxConcurrency = 3`, the operator can subscribe to all three inner publishers without waiting for the first one to complete.
3. With the simulated latencies, inner publishers 2 and 3 usually finish before 1. **Internal observation logs, if added, may arrive in a different order depending on scheduler timing.**
4. `flatMapSequential` holds the results of 2 and 3 until 1's data slice completes. Since each inner emits only one element, the output is always ordered `result-1`, `result-2`, `result-3` if the pipeline completes normally.
5. `collectList()` accumulates the output into a `List<String>`, used solely to print the final result. `block()` only appears in the **command-line demo**; strictly avoid putting `block()` on a WebFlux event loop thread.

Replacing the operator with `flatMap(OrderedMergeDemo::fetch, 3)` **no longer guarantees** output order 1, 2, 3. Replacing it with `concatMap(OrderedMergeDemo::fetch)` preserves order, but starts each inner publisher sequentially so the three wait intervals no longer overlap in the same way.

**Do not infer higher throughput from a measurement of a few hundred milliseconds.** Real speed depends on whether I/O is non-blocking, downstream limits, payload sizes, connection pools, tail latencies, and error policies.

## 7. When One Input Produces Multiple Values

Not every mapper returns a `Mono`. A class ID might expand into multiple lessons, or a product group might turn into multiple items. When the mapper returns a `Flux`, `flatMapSequential` holds onto all data of **the entire earlier inner** before emitting data from a later inner, even if the later inner already has elements ready.

Another standalone Java example that can be placed in `src/main/java/MultiValueDemo.java` with the same `pom.xml`:

```java
import java.time.Duration;
import java.util.List;

import reactor.core.publisher.Flux;

public class MultiValueDemo {
    public static void main(String[] args) {
        List<String> values = Flux.just("A", "B")
            .flatMapSequential(group -> {
                if (group.equals("A")) {
                    return Flux.just("A1", "A2")
                        .delayElements(Duration.ofMillis(60));
                }
                return Flux.just("B1", "B2");
            }, 2, 1)
            .collectList()
            .block();

        System.out.println(values);
    }
}
```

Run:

```bash
mvn -q compile exec:java -Dexec.mainClass=MultiValueDemo
```

Stdout:

```text
[A1, A2, B1, B2]
```

Even though inner B can become ready earlier, it is not interleaved between A1 and A2. Note that `delayElements` creates an asynchronous publisher, while `Flux.just("B1", "B2")` can emit synchronously upon subscription. The operator still holds slice B until its turn. **The order within each inner publisher** follows the order that publisher itself emits; if the inner itself used `flatMap` and scrambled order, the outer `flatMapSequential` does not re-sort elements inside that inner by business ID.

### Empty Inner Publisher Case

If `fetch(id)` returns `Mono.empty()` for ID 2, downstream in the single-element-per-inner example may receive `result-1`, `result-3`, and then complete. Order is still preserved, but there is **no longer a one-to-one correspondence with IDs**. If the API requires exactly one result (including “not found”) per ID, convert the empty case into a valid outcome:

```java
Flux<LookupOutcome> outcomes = ids.flatMapSequential(
    id -> service.find(id)
        .map(value -> LookupOutcome.found(id, value))
        .switchIfEmpty(Mono.just(LookupOutcome.missing(id))),
    8, 1
);
```

`LookupOutcome`, `service`, and `ids` are real application types/objects; this snippet illustrates the design rather than being a standalone compilable program. Choose an appropriate “missing” model so the mapping between inputs and outputs is not lost. `Mono.just(null)` is not a valid way to represent a missing result in Reactor.

## 8. Why Can an Order-Preserving Operator Still Bottleneck?

`flatMapSequential` enables concurrency at the cost of **holding results from fast inners that sit behind a slow inner**. This is commonly called *head-of-line blocking* on the emission side.

Suppose 20 requests start eagerly: the first takes 10 seconds, and the remaining 19 take 100 ms. With mandatory ordering, downstream may not receive the results of the 19 fast requests while waiting for request 1. These results must be retained in memory/buffers; footprint also depends on the number of active publishers, data volume per inner, and backpressure.

Signs to watch for:

- Client result latency increases even though most internal requests have already finished.
- Heap/queue usage grows due to storing early-arriving results from inners whose turn has not arrived.
- Non-blocked threads can still experience **emission-progress stalling** because of the ordering constraint.
- An inner that never completes causes subsequent inners **not to be emitted** even if they have already finished running.

Therefore, `flatMapSequential` is the right choice when **output order is genuinely part of the API contract**. If users want to see whichever result finishes first appear immediately, `flatMap` usually serves better.

### Controlled Optimization

- Reduce `maxConcurrency` to cap in-flight inner publishers and the volume of queued results.
- Tune `prefetch` based on item size, downstream requests, and source speed; do not treat `prefetch` as a “memory byte limit”.
- Put a timeout on each subtask so a single leading element cannot block subsequent elements forever.
- Split into smaller batches, optimize slow endpoints, or use a bulk API if the backend supports it.
- If order is no longer mandatory, switch to `flatMap` to emit as data becomes ready.
- For large result sets, avoid accumulating everything with `collectList()` in production just to “keep order”: `flatMapSequential` already preserves stream order; do not collect everything unless you truly must return a list.

## 9. Understanding maxConcurrency and prefetch Properly

### maxConcurrency Limits Inner Publishers, Not Thread Count

`maxConcurrency = 8` allows at most eight inners subscribed simultaneously in that pipeline. If the mapper returns publishers performing non-blocking I/O, multiple tasks can wait on the network concurrently. However, if the mapper calls `Thread.sleep` or a synchronous JDBC repository **immediately when constructing the publisher**, that synchronous call can block the thread invoking the mapper:

```java
// WRONG on the event loop: the blocking call runs immediately when the mapper is invoked.
.flatMapSequential(id -> Mono.just(legacyClient.fetchBlocking(id)), 8)
```

The snippet above is an illustrative fragment (does not compile standalone without `legacyClient`). `Mono.just(...)` **evaluates its argument eagerly**, so the blocking operation has already occurred before the publisher finishes being built. Increasing `maxConcurrency` will not fix blocking behavior.

If you are forced to use a synchronous library, isolate the call appropriately:

```java
.flatMapSequential(
    id -> Mono.fromCallable(() -> legacyClient.fetchBlocking(id))
        .subscribeOn(Schedulers.boundedElastic()),
    8, 1
)
```

In a real application, import `reactor.core.scheduler.Schedulers` and manage timeouts, thread/queue limits, connection pools, overall load, and task cancellation. `boundedElastic` isolates blocking work from the event loop; it **does not make that I/O non-blocking**, nor does it guarantee a blocking task can be stopped immediately upon cancellation. Prefer WebClient/R2DBC/reactive drivers whenever possible.

### prefetch and Backpressure

Reactive Streams allows downstream to call `request(n)`; the operator propagates/adapts demand to upstream and inners. `prefetch` guides how many elements are pre-requested from each inner publisher. For inners emitting many records, requesting too much can increase buffered data; requesting too little can cause frequent request cycles and reduce throughput. Buffers can experience pressure when an earlier inner is slow and later inners emit rapidly.

You cannot deduce “at most `maxConcurrency × prefetch` elements across the entire application” as a hard guarantee: upstream itself, HTTP client libraries, network buffers, individual inner publishers, and other operators can each maintain their own buffers. Reasonable limits require load testing and observing active subscriptions, buffered bytes, throughput, P95/P99 latency, and cancellation.

## 10. Error Handling, Timeouts, and Cancellation

### What Happens When an Inner Errors?

In the standard `flatMapSequential` form, an error from an inner publisher becomes a pipeline error; expect that other work may be canceled and buffered data discarded. Do not promise that every result from earlier or later inners will still be emitted when one inner fails.

If individual IDs can fail yet the API must return a result record for **each ID in order**, handle errors **inside the mapper**, converting them into explicitly typed business results:

```java
Flux<LookupOutcome> outcomes = ids.flatMapSequential(
    id -> service.find(id)
        .map(value -> LookupOutcome.found(id, value))
        .switchIfEmpty(Mono.just(LookupOutcome.missing(id)))
        .onErrorResume(ex ->
            Mono.just(LookupOutcome.failed(id, ex.getClass().getSimpleName()))),
    8, 1
);
```

This application example (requiring `LookupOutcome` and `service` definitions) avoids turning an error into `null`, instead creating an object with an explicit status. Do not unconditionally swallow every exception in production: distinguish business errors from infrastructure errors, apply conditional retries, logging/metrics, and error information security requirements.

Reactor also provides `flatMapSequentialDelayError(mapper, maxConcurrency, prefetch)` to **defer error reporting** while draining backlog, though the final outcome is still an error stream if any inner failed; it does not automatically produce an error record per ID. Use it only after explicitly defining the contract for partial emission, completion, and error semantics.

### What If an Inner Waits Forever?

For instance, `Flux.just(1, 2).flatMapSequential(id -> id == 1 ? Mono.never() : Mono.just("two"), 2, 1)` may already have data from ID 2, yet downstream **never receives “two”** because ID 1 never completes. To bound waiting for a single ID, attach `timeout` inside the mapper:

```java
.flatMapSequential(
    id -> service.fetch(id)
        .timeout(Duration.ofSeconds(2))
        .onErrorResume(TimeoutException.class,
            ex -> Mono.just(Result.timeout(id))),
    8, 1
)
```

This is an integration fragment requiring `Duration`, `TimeoutException`, `service`, `Result`, and imports in a real application. Using Java's `java.util.concurrent.TimeoutException`, Reactor's `timeout` operator emits a timeout error when its expiration condition triggers. The fallback gives downstream a structured error result so ordered emission can continue. **Do not place a single pipeline-wide timeout and assume it acts as a per-ID timeout.** Where `timeout` is placed determines its scope.

### Downstream Cancels Mid-Stream

If the subscriber cancels, active inners are normally canceled as supported by their publishers. In WebFlux, a client disconnect can cancel the subscription. **Cancellation does not guarantee rolling back side effects already triggered**, such as calling a payment API, sending messages, or writing to a database. For operations with side effects, use idempotency keys or an appropriate transaction model; `flatMapSequential` only orders emitted data, not those side effects.

Do not call `subscribe()` manually inside a controller and return a different `Flux`; doing so detaches execution from the HTTP request's lifecycle, cancellation, and error handling. Return the publisher directly to WebFlux.

## 11. Integrating flatMapSequential into Spring WebFlux

Suppose an API receives a list of IDs in user-selected order and fetches details from an external reactive service. The handler wants to return data **in the order of the received IDs**, even if backend HTTP calls complete out of order.

The code below is **part of a Spring WebFlux controller**, not a standalone program: it requires a `ProfileService` bean with a `Mono<ProfileDto> fetch(long id)` method and the corresponding DTO.

```java
import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/profiles")
public class ProfileController {

    private final ProfileService service;

    public ProfileController(ProfileService service) {
        this.service = service;
    }

    @GetMapping("/lookup")
    public Flux<ProfileDto> lookup(@RequestParam List<Long> ids) {
        return Flux.fromIterable(ids)
            .flatMapSequential(service::fetch, 8, 1);
    }
}
```

Suppose the requested IDs are `[41, 7, 19]`. Even if `fetch(7)` completes before `fetch(41)`, the downstream stream still emits 41's result before 7's, followed by 19's, provided all three inner publishers emit one value and complete normally. If `fetch(41)` returns empty, 41's result does not appear; the order of **actually emitted results** still follows the source. If one result per ID is required, add an appropriate `switchIfEmpty` strategy.

For HTTP responses, keep these distinctions in mind:

- `Flux<ProfileDto>` is subscribed to by WebFlux and serialized into the response according to configured encoding and media types.
- If you want to stream items as soon as possible, consider `application/x-ndjson` or SSE depending on the API contract; a regular JSON array may be encoded/buffered differently.
- Because `flatMapSequential` preserves order, a fast item can still be delayed from emission until an earlier item is ready.
- If an inner errors after the HTTP response has already begun sending, the server may no longer be able to change a success status code to an error code in the usual way. Design a per-item result protocol and error mapping accordingly.
- HTTP response order is pipeline order, not a promise that external system calls or side-effect writes executed in that exact sequence.

**Do not use `collectList().block()` in a controller.** If you must return a complete JSON array, you can use `collectList()` to get `Mono<List<ProfileDto>>` and let the framework subscribe, while actively evaluating memory and latency costs.

## 12. Testing the Contract with StepVerifier and Sinks

Real-time examples can cause subtasks to finish in different orders across runs. To test **order preservation** deterministically, use `Sinks.One` to manually control when each inner emits data. Add `src/test/java/OrderedMergeTest.java` (using the test dependencies in the `pom.xml` above):

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;
import reactor.test.StepVerifier;

public class OrderedMergeTest {

    @Test
    void emitsInInputOrderEvenWhenSecondFinishesFirst() {
        Sinks.One<String> first = Sinks.one();
        Sinks.One<String> second = Sinks.one();

        AtomicInteger subscriptions = new AtomicInteger();

        Flux<String> output = Flux.just(1, 2)
            .flatMapSequential(id -> {
                Mono<String> inner =
                    id == 1 ? first.asMono() : second.asMono();
                return inner.doOnSubscribe(s ->
                    subscriptions.incrementAndGet());
            }, 2, 1);

        StepVerifier.create(output)
            .expectSubscription()
            .then(() -> assertEquals(2, subscriptions.get()))
            .then(() -> assertEquals(
                Sinks.EmitResult.OK,
                second.tryEmitValue("second")))
            .expectNoEvent(Duration.ofMillis(20))
            .then(() -> assertEquals(
                Sinks.EmitResult.OK,
                first.tryEmitValue("first")))
            .expectNext("first", "second")
            .verifyComplete();
    }

    @Test
    void respectsMaxConcurrency() {
        AtomicInteger started = new AtomicInteger();

        Flux<Integer> output = Flux.range(1, 5)
            .flatMapSequential(
                id -> Mono.<Integer>never()
                    .doOnSubscribe(s -> started.incrementAndGet()),
                2, 1);

        StepVerifier.create(output)
            .expectSubscription()
            .then(() -> assertEquals(2, started.get()))
            .thenCancel()
            .verify();
    }

    @Test
    void preservesWholeInnerSequences() {
        Flux<String> output = Flux.just("A", "B")
            .flatMapSequential(group -> {
                if (group.equals("A")) {
                    return Flux.just("A1", "A2");
                }
                return Flux.just("B1", "B2");
            }, 2, 1);

        StepVerifier.create(output)
            .expectNext("A1", "A2", "B1", "B2")
            .verifyComplete();
    }
}
```

Run tests:

```bash
mvn -q test
```

Once the environment has downloaded all dependencies, Maven exits cleanly with exit code 0 when all three tests pass. There is no requirement to print a specific stdout string from the tests.

**The first test is the most important:**

1. After subscribing, assert that **both inners have been subscribed** (demonstrating eagerness with `maxConcurrency = 2`).
2. Complete **second before first**; assert no output events occur during a short observation window, because first has not finished yet.
3. Complete first; downstream receives `first`, then `second`, and completes.
4. Do not use `Thread.sleep` to “guess” result order. The test drives events with sinks and only uses a 20 ms window to verify **no emission before its turn**, rather than asserting exact execution timing.

The second test keeps all inners in `never()` state, so only the first two inners are subscribed under `maxConcurrency=2`; it then explicitly cancels so the test does not hang. The third test proves multi-element results are preserved as contiguous slices.

To test real-world load, beyond unit tests you must also evaluate error rates, per-inner latency, result size, memory, cancellation, and connection pool limits. A small deterministic input test does not represent fluctuating network conditions in production.

## 13. Notes on Concurrency, Scheduling, and Side Effects

Three terms are often conflated:

- **Concurrency (multiple tasks making progress):** inner publishers are subscribed and can await independent results simultaneously.
- **Parallelism (CPU execution at the same instant):** work genuinely running on multiple cores/threads; `flatMapSequential` does not create this on its own if all inners run synchronously on one thread.
- **Ordering (order seen downstream):** the operator collects data and emits in inner-publisher order; it does not lock shared data or serialize external writes.

If the mapper returns asynchronous sources such as WebClient, R2DBC, or `Mono.delay`, concurrency brings clear benefits. If the mapper returns `Mono.just(doBlockingWork())`, the task already ran synchronously before the publisher was constructed and can block the event loop; redesign the source or isolate blocking work in a controlled way.

**Do not use `flatMapSequential` to enforce business rules like “update balances strictly in ID order”** when inners already start concurrent writes. If business rules require task B to start only after A finishes, use `concatMap` or an appropriate serialization/transaction mechanism. If only the displayed result must match the user's input list order, `flatMapSequential` can be suitable.

The following observations help avoid misunderstandings:

- `doOnSubscribe` and `doOnNext` **inside the mapper** reflect inner progress and may appear out of input order.
- `doOnNext` placed **after `flatMapSequential`** observes downstream order, which the operator preserves.
- There is no guarantee all inners start at the exact same instant; request/backpressure levels, schedulers, and `maxConcurrency` determine subscription timing.
- If upstream sends elements in a non-deterministic order from a hot source or earlier processing, `flatMapSequential` preserves the exact order **it receives**.
- Abnormal termination or cancellation can drop unemitted results; check error/cancellation contracts when interpreting “order preservation”.

## 14. Common Mistakes and Fixes

1. **Using `flatMap` and expecting order because the input is `Flux.just(1,2,3)`.** An ordered source does not mean asynchronous results will be ordered. Choose `flatMapSequential` or `concatMap` based on requirements.
2. **Using `concatMap` for every ordering case.** If multiple independent I/O calls can wait concurrently, `flatMapSequential` can overlap wait times. Conversely, if **side effects must be sequential**, `concatMap` is the right choice.
3. **Setting `maxConcurrency` arbitrarily high to go “as fast as possible”.** This can overload downstream services, connection pools, and buffers. Choose limits based on measurements.
4. **Confusing `prefetch` with total API requests.** It relates to per-inner element demand; total connections, queues, and threads also depend on other layers.
5. **Omitting timeouts on inners that can hang.** A leading `never()` inner can hold all later results forever. Place timeouts in the right spot with an error strategy.
6. **Interpreting “preserve order” as ordered database writes.** Inners run concurrently, so side effects can still happen out of order.
7. **Putting `Thread.sleep`, `block()`, or synchronous calls in a mapper on the event loop.** This reduces request concurrency and distorts concurrency semantics. Use non-blocking APIs or isolate blocking calls.
8. **Collecting everything with `collectList()` just to sort.** The operator already emits in order; collecting everything can delay time-to-first-byte and consume RAM.
9. **Assuming every ID always emits exactly one result.** An inner can be empty, error, or emit multiple values. Design the output contract and handle each case.
10. **Ignoring cancellation and retries.** Retries can resubscribe inners and repeat side effects; client disconnects can cancel the pipeline. Use idempotency for sensitive operations.
11. **Comparing internal logs with downstream results.** Inner logs may appear in completion order, while output after `flatMapSequential` is ordered by the source.
12. **Choosing operators by name alone.** “Sequential” here describes **merge and emission order**, not that everything inside runs sequentially.

## 15. Practice Exercises

**Exercise 1.** Input is `[10, 20, 30]`; inner 10 takes 500 ms, inner 20 takes 50 ms, inner 30 takes 100 ms. Concurrency limit is 3. If each inner returns one value, in what order does `flatMapSequential` emit?  
**Answer:** `10, 20, 30`. Inners 20 and 30 may finish earlier, but are held until their turn. Time to first output can be long because inner 10 is slow.

**Exercise 2.** If the requirement is “emit whichever result is ready first so the UI displays it immediately”, which operator should be used?  
**Answer:** `flatMap` is a better fit because it does not constrain emission to source order. Include the ID in each result so the UI attaches it to the right item.

**Exercise 3.** If the operations are “debit money and then write the invoice” and the second must **start** only when the first succeeds, is `flatMapSequential` suitable?  
**Answer:** No. Express the dependency with `then`/`flatMap` inside a dependent chain, or `concatMap` for sequential tasks. Preserving **output** order does not guarantee **side-effect** order.

**Exercise 4.** Source emits A, B; inner A emits A1 then A2, inner B emits B1 very early. What order does the subscriber of `flatMapSequential` receive?  
**Answer:** A1, A2, B1, provided all succeed and complete. B1 is not interleaved between A1 and A2.

**Exercise 5.** `maxConcurrency = 2`, the source has 100 IDs, and the first two inner publishers never complete. Are the remaining IDs guaranteed to be subscribed?  
**Answer:** No. Both slots are occupied; timeouts/cancellations or a source redesign are needed, along with monitoring for stuck tasks.

**Exercise 6.** The inner for the first ID returns `Mono.empty()`, and the second inner returns `Mono.just("B")`. What does downstream see?  
**Answer:** It receives `B` once the first inner completes empty and the second inner's turn arrives. There is no “null” element representing the first ID unless the mapper explicitly creates a valid result such as `Missing(id)`.

**Exercise 7.** If `prefetch=1` and `maxConcurrency=4`, can you claim the program uses memory for at most four elements?  
**Answer:** No. Those parameters tune demand/subscription within the operator; upstream, inners, the network stack, and other operators can still maintain their own buffers.

**Exercise 8.** Is it possible to observe inner B completing before inner A, while downstream still only sees A before B?  
**Answer:** Yes. That is precisely the difference between **task completion order** and **data emission order** in `flatMapSequential`.

## 16. Key Takeaways and Selection Criteria

`flatMapSequential` is appropriate when **each source element spawns an independent task that can run concurrently**, yet the consumer must receive results in **source order**. It subscribes to inner publishers eagerly (within `maxConcurrency`), buffers early-arriving results, and emits each result slice in order. You must accept buffering overhead and latency from a slow leading inner; designing timeouts, concurrency bounds, error handling, cancellation, and non-blocking I/O is essential.

If **result order is not needed**, choose `flatMap`. If **earlier work must finish before later work begins**, choose `concatMap` or an appropriate dependency chain. If **concurrency is needed while output stays ordered**, choose `flatMapSequential` and test it by having a later inner finish before an earlier one.

### References

- Project Reactor, [Flux Javadoc – flatMapSequential](https://projectreactor.io/docs/core/3.6.11/api/reactor/core/publisher/Flux.html): defines eager subscription, ordered merge, and the `maxConcurrency` and `prefetch` parameters.
- Project Reactor, [Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/).
- Project Reactor, [Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html).
- Spring Framework, [Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html).
- [Reactive Streams Specification](https://www.reactive-streams.org/).
