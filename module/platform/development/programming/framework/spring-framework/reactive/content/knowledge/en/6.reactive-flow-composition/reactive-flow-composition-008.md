# `buffer`, `window`, and `groupBy` in Project Reactor

## 1. Problem: Splitting One Stream into Smaller Parts

When processing a `Flux<T>` in Spring WebFlux/Project Reactor, we often need to collect several elements for batch writes, split a stream into windows for continuous processing, or route elements by a business key. Reactor provides three important operator families:

- **`buffer`:** collects multiple source elements into a collection, usually a `List<T>`.
- **`window`:** splits the source stream into **inner `Flux<T>` streams** based on size, time, or boundary conditions.
- **`groupBy`:** partitions the source stream into `GroupedFlux<K,T>` streams by key `K`, even when elements sharing the same key are interleaved in the input.

All three operators serve the goal of “splitting a stream”, yet they **differ in result type, when groups are emitted, how data is processed, and resource cost**. Confusing them easily leads to hanging without output, dropped elements due to `skip`, growing memory, or `groupBy` stalling under backpressure.

**Learning objectives:** choose the right operator from business requirements; read `Flux<List<T>>`, `Flux<Flux<T>>`, and `Flux<GroupedFlux<K,T>>` types; explain non-overlapping, overlapping, and gapped groups; build safe group-consuming pipelines; and test with Java 17+ and StepVerifier.

## 2. One-Page Comparison

| Criterion | `buffer` | `window` | `groupBy` |
| --- | --- | --- | --- |
| Typical result | `Flux<List<T>>` | `Flux<Flux<T>>` | `Flux<GroupedFlux<K,T>>` |
| Splitting criterion | Count, duration, predicate, boundary publisher | Count, duration, predicate, boundary publisher | Key computed by `keyMapper` |
| What is emitted per group? | An assembled collection | An inner Publisher to consume as a stream | An inner Publisher carrying `key()` |
| Need to `subscribe` inner stream? | No; downstream receives a list | Yes; must consume inner Flux | Yes; must consume each `GroupedFlux` |
| Holds data in a collection? | Yes, inside each buffer | Does not build a `List` by default; may queue elements depending on operator/demand | May queue elements per group if downstream is slow |
| Can overlap? | Yes, in `buffer(size, skip)` and variants | Yes, in `window(size, skip)` and variants | No; each element goes to exactly one key group |
| Can emit empty groups? | E.g., `bufferWhile` does not emit empty buffers | Some predicate variants like `windowWhile` can create empty windows | No; a group is created only when an element with that key arrives |
| Best suited for | Finite batching, exporting lists, short-lived accumulation | Keeping stream structure across time/size slices | Processing per tenant, event type, or customer ID with bounded key cardinality |

Example source `1,2,3,4,5,6,7`:

~~~text
Source            1  2  3  4  5  6  7

buffer(3)         [1,2,3]  [4,5,6]  [7]
window(3)        (Flux 1,2,3) (Flux 4,5,6) (Flux 7)

groupBy(parity)   odd:  1,3,5,7
                  even: 2,4,6
~~~

Even though windows and buffers look similar in a short example, **a window is an inner publisher** that can be processed while data is arriving, whereas a buffer is a collection already completed at its boundary.

## 3. `buffer(n)`: Batching by Count

`Flux<T>.buffer(int maxSize)` emits a `Flux<List<T>>`. Each time `maxSize` elements arrive, the operator closes the current buffer and emits a list. If a finite source ends with a remainder, the remainder is emitted as a shorter final list.

~~~java
Flux.range(1, 8)
    .buffer(3)
    .subscribe(batch -> System.out.println(batch));
~~~

Stdout of the snippet above (in a program importing `reactor.core.publisher.Flux`):

~~~text
[1, 2, 3]
[4, 5, 6]
[7, 8]
~~~

Points to remember:

1. `buffer(3)` **does not guarantee a list every three seconds**; this overload's criterion is **element count**, not time.
2. If the source stops sending without **completing** and the current buffer holds only two elements, `buffer(3)` can keep waiting for the third element. To emit after a wait timeout, consider `bufferTimeout`.
3. `List<T>` consumes memory holding the collected elements. Large batches or overlapping buffers increase memory cost.
4. `buffer` does not automatically execute a database batch/transaction; it only collects elements. The next step, such as `concatMap(batch -> repository.saveBatch(batch))`, determines how saving happens.
5. The final list size may be smaller than `maxSize`; never assume every batch has identical size.

With `Flux.empty().buffer(3)`, no data list comes from the source. Returning an empty list to represent “no results” in a response is a business-layer decision; do not assume every buffer operator emits an empty list.

## 4. `window(n)`: Splitting into Inner Publishers

`Flux<T>.window(int maxSize)` returns `Flux<Flux<T>>`. Each element of the outer stream is **an inner `Flux<T>`**, not a `List<T>`.

~~~java
Flux.range(1, 8)
    .window(3)
    .concatMap(inner -> inner.collectList())
    .subscribe(windowAsList -> System.out.println(windowAsList));
~~~

In this snippet, we **explicitly** call `collectList()` to illustrate each window's elements as a list. Stdout:

~~~text
[1, 2, 3]
[4, 5, 6]
[7, 8]
~~~

If you remove `collectList()`, downstream needs another way to **subscribe to/consume each inner Flux**. Simply writing:

~~~java
Flux<Flux<Integer>> windows = Flux.range(1, 8).window(3);
~~~

only **assembles the pipeline**; the statement itself prints nothing and does not automatically process elements inside.

Key differences:

- `buffer` emits each `List<T>` when the buffer closes; multiple elements have already been gathered into one object.
- `window` can publish an inner stream as soon as it opens. Downstream can process elements inside it **as they arrive**, depending on the combining operator and demand.
- `window` is not free: opening inner windows without consuming them can stall the pipeline or grow memory via queues/backpressure.
- Use `concatMap` when you want to process windows in order and concatenate output sequentially; use `flatMap` when interleaving is acceptable and you want concurrent processing (bounding concurrency when necessary).
- `window` **does not mean** creating threads, schedulers, or parallel execution. Switching threads requires appropriate operators and schedulers.

An example of processing each slice as a stream without collecting all elements into a list:

~~~java
Flux<String> summaries = Flux.range(1, 9)
    .window(3)
    .concatMap(inner ->
        inner.reduce(0, Integer::sum)
             .map(sum -> "window-sum=" + sum)
    );
~~~

This snippet emits:

~~~text
window-sum=6
window-sum=15
window-sum=24
~~~

Here `reduce` holds only the running sum rather than a list of all elements. Still, because each window must end to produce its sum, results are emitted at window boundaries.

## 5. `groupBy(keyMapper)`: Partitioning by Key, Not Position

`groupBy` produces a `Flux<GroupedFlux<K,T>>`. When an element with a new key `K` arrives, the operator opens a group for that key. Later elements with the same key route back to that same group even if dozens of elements with other keys appeared in between.

~~~java
Flux.just("A:1", "B:1", "A:2", "B:2", "A:3")
    .groupBy(value -> value.substring(0, 1))
    .flatMap(group ->
        group.collectList()
             .map(items -> group.key() + " -> " + items)
    )
    .sort()
    .subscribe(System.out::println);
~~~

Stdout (with `sort()` for deterministic output ordering):

~~~text
A -> [A:1, A:2, A:3]
B -> [B:1, B:2]
~~~

Here:

- `group.key()` returns the key of the `GroupedFlux`.
- Element `A:2` does not create a second group A; it goes into the existing group A.
- Each element belongs to **exactly one group**, unlike overlapping buffer/window.
- Groups are never empty because a group opens only when an element with that key arrives.
- `flatMap` is used to **consume all groups** concurrently; `collectList()` in the example is sensible only because the source is finite and small.

**`groupBy` differs from `windowUntilChanged` / `bufferUntilChanged`:** given input `A,A,B,A`, `groupBy` routes all A's into **one group A**; operators splitting by **contiguous runs** instead create three segments `[A,A]`, `[B]`, `[A]`. Choose according to business meaning: “all events for one customer” differs from “each consecutive streak with the same status”.

## 6. Complete Java 17+ Program Running and Comparing All Three

Create a simple Gradle project. Contents of `build.gradle`:

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
    mainClass = 'BatchingDemo'
}
~~~

Create `src/main/java/BatchingDemo.java`:

~~~java
import java.util.List;
import reactor.core.publisher.Flux;

public final class BatchingDemo {
    public static void main(String[] args) {
        Flux<Integer> numbers = Flux.range(1, 9);

        List<List<Integer>> buffers = numbers
            .buffer(4)
            .collectList()
            .block();

        List<List<Integer>> windows = numbers
            .window(4)
            .concatMap(inner -> inner.collectList())
            .collectList()
            .block();

        List<List<Integer>> overlapping = numbers
            .buffer(4, 2)
            .collectList()
            .block();

        List<List<Integer>> gapped = numbers
            .buffer(2, 4)
            .collectList()
            .block();

        List<String> groups = numbers
            .groupBy(i -> i % 2 == 0 ? "even" : "odd")
            .flatMap(group ->
                group.collectList()
                     .map(items -> group.key() + "=" + items)
            )
            .sort()
            .collectList()
            .block();

        System.out.println("buffer(4): " + buffers);
        System.out.println("window(4): " + windows);
        System.out.println("buffer(4,2): " + overlapping);
        System.out.println("buffer(2,4): " + gapped);
        System.out.println("groupBy(parity): " + groups);
    }
}
~~~

Run with `gradle run --quiet` (or `./gradlew run --quiet` if the project has Gradle Wrapper). Exact stdout for `Flux.range(1,9)`:

~~~text
buffer(4): [[1, 2, 3, 4], [5, 6, 7, 8], [9]]
window(4): [[1, 2, 3, 4], [5, 6, 7, 8], [9]]
buffer(4,2): [[1, 2, 3, 4], [3, 4, 5, 6], [5, 6, 7, 8], [7, 8, 9], [9]]
buffer(2,4): [[1, 2], [5, 6], [9]]
groupBy(parity): [even=[2, 4, 6, 8], odd=[1, 3, 5, 7, 9]]
~~~

**Why this output is accurate:**

1. Both `buffer(4)` and `window(4)` divide 9 elements into two full slices of four and one remainder of one. `window(4)` was converted to lists via `collectList()` solely for comparison.
2. `buffer(4,2)` opens a new buffer every two elements while each buffer holds up to four; hence buffers **overlap**. Elements 3 and 4 appear in two different buffers. At the end of the source, trailing buffers contain fewer than four elements.
3. `buffer(2,4)` opens buffers at elements 1, 5, and 9; each holds at most two elements. Elements 3, 4, 7, and 8 **are not placed into any buffer**.
4. `groupBy` creates two groups by parity; each value goes into exactly one group. `sort()` stabilizes display order because groups can complete/emit at different moments.
5. `numbers` built from `Flux.range` is a cold source that can be subscribed to multiple times; each `block()` in the console demo runs a separate pipeline from 1 to 9. `block()` is used **only in main demo code**; never put `block()` into Spring WebFlux reactive request handling.

## 7. `size` and `skip` Parameters: Disjoint, Overlapping, Gapped

With `buffer(size, skip)` and `window(size, skip)`:

- `size` is the maximum capacity of each group/window.
- `skip` is the number of source elements between **two consecutive group start positions**, not “skip that many elements outright”.
- `size == skip`: adjacent groups with no overlap and no gaps.
- `size > skip`: **overlapping**; the same element can belong to multiple buffers/windows.
- `size < skip`: **gapped**; elements falling in the gap are omitted from this operator's output.

Example on source 1…10:

| Expression | Emitted groups |
| --- | --- |
| `buffer(5)` | [1,2,3,4,5], [6,7,8,9,10] |
| `buffer(5,3)` | [1,2,3,4,5], [4,5,6,7,8], [7,8,9,10], [10] |
| `buffer(3,5)` | [1,2,3], [6,7,8]; 4,5,9,10 are excluded from output |

Overlapping **does not destroy the original source**, yet the same element is presented multiple times in the output. If downstream writes to a database, charges fees, or sends notifications per buffer without deduplication, business logic may process the same element multiple times.

Gaps also have data consequences: `buffer(3,5)` never sends elements 4, 5, 9, or 10 downstream after the buffer. Never use an overload with `skip > size` if the requirement is “every event must be processed exactly once”.

With `window(size, skip)`, the boundary rules are identical, except the outputs are inner Fluxes that must be consumed. When windows overlap, a single element can be emitted to multiple open windows.

## 8. Conditional Splitting: `bufferUntil`, `windowUntil`, and `*While`

### 8.1. Closing a group at an element matching a predicate

`bufferUntil(predicate)` collects elements and **closes the group when encountering an element matching the predicate**, normally including the boundary-closing element itself in the finished buffer.

~~~java
Flux.range(1, 7)
    .bufferUntil(i -> i % 3 == 0)
    .subscribe(System.out::println);
~~~

Stdout:

~~~text
[1, 2, 3]
[4, 5, 6]
[7]
~~~

`windowUntil(predicate)` has the corresponding boundary semantics while producing `Flux<Flux<T>>`. Overloads with the `cutBefore` parameter flip **which side** of the boundary receives the triggering element. Always verify exact boundary behavior when using it for protocol parsing or sessionization.

### 8.2. Keeping a group open while a predicate holds

`bufferWhile(predicate)` collects only **contiguous sequences** where the predicate returns true. Elements that do not match are dropped from output buffers. Example:

~~~java
Flux.just(1, 3, 5, 2, 4, 6, 11, 12, 13)
    .bufferWhile(i -> i % 2 == 0)
    .subscribe(System.out::println);
~~~

Stdout:

~~~text
[2, 4, 6]
[12]
~~~

A detail easily overlooked: **`windowWhile` can produce empty windows** when encountering consecutive elements that fail the predicate, whereas `bufferWhile` **does not emit empty buffers**. With `windowWhile`, if business logic must discard empty windows, `inner.filter(...)` does not apply directly because an inner Flux is not a list; you can use `inner.switchIfEmpty(...)` or `inner.collectList().filter(list -> !list.isEmpty())`, though converting to a list incurs memory cost.

Unlike `groupBy`, both `bufferWhile` and `windowWhile` react to **contiguity** of elements. If even values appear in multiple separated runs, the output can be multiple separate even groups rather than one overarching “even” group.

## 9. Time Boundaries: When Sources Emit Unevenly

Time-based sources rarely emit evenly. `buffer(100)` can wait a very long time to gather 100 elements if traffic is low. Reactor provides operators combining count and duration:

~~~java
Flux<Event> input = obtainEvents();

Flux<java.util.List<Event>> batches =
    input.bufferTimeout(100, java.time.Duration.ofSeconds(2));
~~~

This is an **illustrative snippet**; `Event` and `obtainEvents()` are supplied by the application. `bufferTimeout(maxSize, maxTime)` closes and emits a batch when either the size **or** time limit is reached, per operator semantics. The final batch may contain fewer elements than expected. Do not write tests expecting every batch to have exactly 100 elements on irregular sources.

Similarly, `windowTimeout(maxSize, maxTime)` creates inner windows as Fluxes rather than lists. There are also `buffer(Duration)`, `window(Duration)`, and overloads controlled by boundary publishers.

When writing time-dependent unit tests, use `StepVerifier.withVirtualTime(...)` and construct the source **inside the `withVirtualTime` supplier** so the test does not wait on a real wall clock. Never assume timer ordering if the pipeline has asynchronous sources on different schedulers without controlling schedulers in the test.

**Warnings:** time-based buffer/window does not guarantee millisecond-exact scheduling under load; furthermore, creating many overlapping time windows increases overhead, memory usage, or emits the same element in multiple places.

## 10. `groupBy` and the Risk of Stalling from Unconsumed Groups

A crucial characteristic of `groupBy` is that dynamic groups **must be consumed by downstream** to free capacity for the source to keep emitting. With interleaved keys, some groups may sit waiting for a subscriber while `groupBy` buffers their data.

**Error-prone example:**

~~~java
Flux<Event> events = obtainEvents();

Flux<Result> results = events
    .groupBy(Event::tenantId)
    .concatMap(group -> consumeWholeGroup(group));
~~~

This is a snippet (`Event`, `Result`, `obtainEvents`, and `consumeWholeGroup` are application-defined). `concatMap` processes only one group at a time. With long groups and interleaved tenant data, the first group may need more elements to complete while upstream can no longer send because buffers for other groups are full. The pipeline risks **hanging due to backpressure**, even without a traditional thread deadlock.

How to handle when the number of groups is **small and bounded**:

~~~java
Flux<String> results = Flux.just(
        "tenant-A:1", "tenant-B:1", "tenant-A:2", "tenant-B:2"
    )
    .groupBy(s -> s.substring(0, 8))
    .flatMap(group ->
        group.collectList()
             .map(items -> group.key() + "=" + items),
        2 // sufficient concurrency for the two A/B keys in the example
    );
~~~

For infinite/long-lived data, **never use `collectList()` on each group** without a mechanism to close groups: it waits for the group to complete and can accumulate unboundedly. Instead, process elements incrementally inside each group, or use `bufferTimeout`/`windowTimeout` per group to process finite slices, along with a lifecycle policy for the number of groups.

Safety principles:

1. **Cardinality:** `groupBy(event -> event.id())` on unique UUIDs can create nearly as many groups as elements, causing severe memory pressure. Only group by keys with controlled cardinality.
2. **Consume promptly:** as soon as a group is emitted, a subscriber must consume its contents. `flatMap` is usually more appropriate than `concatMap` when keys interleave; concurrency must match the data pattern and the number of concurrently open groups.
3. **Prefetch does not replace consumption:** raising prefetch/queue sizes only delays the stall and can consume more RAM.
4. **Ordering:** `flatMap` can interleave results across groups. If global source order is required, design for it separately; `groupBy` already reorganizes the stream by key.
5. **Unicast groups:** each `GroupedFlux` is tied to the source lifecycle and designed for a single subscriber. Do not blindly `retry()`/`repeat()` an inner group as if it were a re-subscribable cold Flux.
6. **Non-terminating sources:** groups usually remain open until the source completes or is cancelled; if you need daily or per-session grouping, a plain key alone does not represent time boundaries. Use a key paired with controlled time buckets or appropriate windowing.

If you have thousands or millions of unbounded keys, consider dedicated partitioning/queueing architectures, a downstream store capable of keyed processing, or capping active groups with an eviction policy; do not rely on `groupBy` as permanent storage for every key.

## 11. Backpressure: What Unit Does Downstream Demand Use?

In Reactive Streams, `request(n)` grants permission for n **`onNext` signals on that specific subscription**. After grouping, a single downstream element can represent multiple upstream elements:

- After `buffer(10)`, one downstream `onNext` is typically **one `List<T>` of up to 10 elements**; a downstream `request(2)` may require upstream to supply up to 20 elements to fill two lists of 10.
- After `window(10)`, one **outer** `onNext` is an inner Flux. That inner Flux then has its own demand from the subscriber consuming the window.
- After `groupBy(key)`, one **outer** `onNext` is a `GroupedFlux` for a key. Elements inside each group are throttled independently, and newly appearing keys may have to wait for groups to be consumed.

**Separate quota from memory:** `request(2)` on `Flux<List<T>>` does not guarantee only two source elements exist in RAM at any given time. Buffers, queues, prefetch, and inner operators maintain their own state. When handling large/fast sources, measure actual in-flight element/batch counts and tune sizes, concurrency, and schedulers appropriately.

Attach `doOnRequest(n -> System.out.println("requested " + n))` before and after an operator to observe how demand changes. Those logs show **each request size** at that stage, not directly the total pending demand across the entire pipeline.

## 12. Applications in Spring WebFlux

### 12.1. Batching events to send to a batch-saving service

A reactive service can collect 100 events per batch to reduce the number of calls to another service:

~~~java
public Flux<SaveResult> saveInBatches(Flux<Event> events) {
    return events
        .bufferTimeout(100, Duration.ofSeconds(1))
        .filter(batch -> !batch.isEmpty())
        .concatMap(batch -> reactiveRepository.saveBatch(batch));
}
~~~

This is a **business snippet**: `Event`, `SaveResult`, `reactiveRepository`, and `saveBatch` must be defined by the application; `Flux` and `Duration` must be imported. Assuming `saveBatch(batch)` returns `Publisher<SaveResult>`, `concatMap` processes **batches sequentially, not concurrently**. Use `flatMap(..., concurrency)` when the backend supports concurrent batches and contention/ordering constraints are clearly bounded.

**Do not assume a batch is a transaction:** DB transactions are managed by the repository/driver/Spring Transaction rules; a 100-element list does not automatically create a transaction.

If the repository is synchronous JDBC, JDBC calls must be deferred and executed on an appropriate scheduler instead of blocking the event loop:

~~~java
public Flux<SaveResult> saveLegacy(Flux<Event> events) {
    return events
        .buffer(100)
        .concatMap(batch -> Mono
            .fromCallable(() -> legacyRepository.saveBatchBlocking(batch))
            .subscribeOn(Schedulers.boundedElastic())
        );
}
~~~

This is also a snippet; `Mono`, `Schedulers`, and application types must be imported/defined. `boundedElastic` **isolates blocking** rather than turning JDBC into non-blocking I/O. Appropriate timeouts and connection pool limits must be configured.

### 12.2. Splitting events into windows for stream processing

~~~java
public Flux<WindowResult> processWindows(Flux<Event> events) {
    return events
        .windowTimeout(50, Duration.ofSeconds(2))
        .concatMap(window -> processOneWindow(window));
}
~~~

This is a snippet; `processOneWindow` accepts `Flux<Event>` and returns `Publisher<WindowResult>` per the application contract. Unlike `bufferTimeout`, the downstream service can process elements inside the window as a stream instead of waiting for a full list. If `processOneWindow` calls `collectList()` itself, the streaming benefit diminishes and data accumulates again.

### 12.3. Partitioning by business key

~~~java
Flux<HandledEvent> handled = events
    .groupBy(Event::category)
    .flatMap(group ->
        group.concatMap(event -> handleCategory(group.key(), event)),
        4
    );
~~~

This is a snippet; `HandledEvent` and `handleCategory` are supplied by the application. Assuming at most **four concurrent categories**, `flatMap(..., 4)` opens groups concurrently; the inner `concatMap` preserves element order **within each group**. Results from **different groups** can still interleave. If actual categories exceed the limit on an interleaved stream, revisit concurrency/backpressure to prevent stalling.

## 13. Testing with Reactor Test

Use `StepVerifier` to verify no elements are lost when `skip` is not configured, as well as predicate behavior.

Replace the `dependencies` block in `build.gradle` from section 6 with the following, and add `test` (without adding a duplicate dependencies block):

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

Create `src/test/java/BatchingTest.java`:

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class BatchingTest {
    @Test
    void bufferEmitsFinalPartialBatch() {
        StepVerifier.create(Flux.range(1, 7).buffer(3))
            .expectNext(List.of(1, 2, 3))
            .expectNext(List.of(4, 5, 6))
            .expectNext(List.of(7))
            .verifyComplete();
    }

    @Test
    void windowIsAnInnerPublisher() {
        StepVerifier.create(
                Flux.range(1, 5)
                    .window(2)
                    .concatMap(window -> window.collectList())
            )
            .expectNext(List.of(1, 2))
            .expectNext(List.of(3, 4))
            .expectNext(List.of(5))
            .verifyComplete();
    }

    @Test
    void bufferWhileIgnoresNonmatchingElements() {
        StepVerifier.create(
                Flux.just(1, 3, 5, 2, 4, 6, 11, 12, 13)
                    .bufferWhile(i -> i % 2 == 0)
            )
            .expectNext(List.of(2, 4, 6))
            .expectNext(List.of(12))
            .verifyComplete();
    }

    @Test
    void groupBySeparatesInterleavedKeys() {
        StepVerifier.create(
                Flux.just("A1", "B1", "A2")
                    .groupBy(s -> s.substring(0, 1))
                    .flatMap(group ->
                        group.collectList()
                             .map(items -> group.key() + "=" + items)
                    )
                    .sort()
            )
            .expectNext("A=[A1, A2]")
            .expectNext("B=[B1]")
            .verifyComplete();
    }
}
~~~

Run `gradle test`. All four tests are expected to PASS. The tests intentionally use finite, synchronous sources and `sort()` when comparing `groupBy` results so they do not depend on concurrent emission ordering. For time-based cases, use virtual time when testing timeout-driven group closing.

## 14. Choosing an Operator from Business Requirements

| Requirement | Initial choice | What else to check |
| --- | --- | --- |
| Send 100 records/batch, list acceptable | `buffer(100)` | If source is slow, batch can wait long |
| Send up to 100 records or every 2 seconds | `bufferTimeout(100, Duration.ofSeconds(2))` | Smaller final batch; timeout/scheduler |
| Process slices of 100 elements as a stream | `window(100)` | Must subscribe/consume inner Flux |
| Split into 5-second sessions | `window(Duration.ofSeconds(5))` | Timing, empty windows, resources |
| Group up to a message-terminator marker | `bufferUntil(isTerminator)` or `windowUntil(isTerminator)` | Exact keeping/routing of boundary element |
| Keep only consecutive runs matching predicate | `bufferWhile(predicate)`/`windowWhile(predicate)` | Non-matching elements; empty windows |
| Group all elements by customerId/tenantId | `groupBy(key)` | Cardinality, active groups, concurrency |
| Group only consecutive segments with same state | `bufferUntilChanged(keyFn)`/`windowUntilChanged(keyFn)` | Same key may produce multiple segments at different positions |
| Want overlapping groups | `buffer(size, skip)` with `size > skip` | Elements repeated in output |
| Want gapped sampling | `buffer(size, skip)` with `size < skip` | Intentionally drops elements; do not use when completeness is required |

Ask before choosing: “Does output need a **List** or an **inner Flux**?”, “Is the criterion **time/size** or **key**?”, “May groups overlap or drop elements?”, “Can the source be infinite?”, “How many concurrent groups exist?”, and “Will downstream consume all groups?”.

## 15. Common Mistakes and Fixes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Thinking `window(5)` returns a list | Wrong type `Flux<Flux<T>>` | Subscribe to inner Flux; call `collectList` only when genuinely needed |
| Using `buffer(100)` on a sparse source that never completes | Batches may never appear | Consider `bufferTimeout` and completion contracts |
| Using `buffer(5,3)` and assuming each item appears once | Duplicated items across buffers | Use `buffer(5)` or `buffer(5,5)` for disjoint groups |
| Using `buffer(3,5)` when completeness is required | Elements in gaps are dropped | Choose `skip == size` |
| Using `groupBy` to split **consecutive runs** of a state | Non-adjacent runs with the same key merge into one group | Use `UntilChanged` or predicate boundary operators |
| `groupBy` on a unique ID per event | Too many groups/queues | Lower cardinality or use a bounded partitioning design |
| `groupBy(...).concatMap(group -> group.collectList())` on long/interleaved streams | Can stall because other groups are not drained | Consume groups promptly with sufficient concurrency; avoid unbounded collect |
| Assuming `flatMap` preserves global order | Group results can interleave | Preserve order only where needed; bound concurrency |
| Calling `collectList()` on a never-ending inner group | Never emits summary; RAM can grow | Process incrementally as a stream or buffer with finite boundaries |
| Treating `buffer` as a database transaction | Grouping a list creates no transaction | Design repository/transaction boundaries separately |
| Assuming every window has at least one item | `windowWhile` can emit empty windows | Handle empty windows explicitly |
| Calling `block()` in a WebFlux handler | Blocks event loop, hurts throughput | Return Flux/Mono; compose with non-blocking operators |
| Ignoring backpressure on inner Fluxes | Queues fill up and pipeline stalls | Subscribe/drain inner streams properly; watch demand/prefetch |

## 16. Self-Check Questions with Answers

**Question 1.** How many lists does `Flux.range(1, 7).buffer(3)` emit, and of what lengths?

**Answer:** Three lists, of lengths 3, 3, and 1: `[1,2,3]`, `[4,5,6]`, `[7]`.

**Question 2.** Does `Flux.range(1, 10).buffer(5, 3)` duplicate elements?

**Answer:** Yes. Buffers start at 1, 4, 7, and 10; elements 4–5, 7–8, and 10 appear in multiple buffers due to overlap; output is `[1..5]`, `[4..8]`, `[7..10]`, `[10]`.

**Question 3.** Why is `Flux<Flux<T>>` from `window` not equivalent to `Flux<List<T>>` from `buffer`?

**Answer:** An inner Flux is a source with its own lifecycle and demand that can emit elements while the window is still open. A List is an already-accumulated collection emitted as a single downstream element.

**Question 4.** Given input `A1, B1, A2, B2` and `groupBy(prefix)`, how many group A's are created?

**Answer:** One group A containing A1 and A2, even though B1 appeared in between.

**Question 5.** Why can `groupBy(key).concatMap(g -> g.collectList())` hang on a source with many interleaved keys?

**Answer:** `concatMap` consumes only one group at a time, while `groupBy` may have to retain elements for other groups. Once buffers/prefetch fill up, upstream cannot emit the elements needed for the awaited group to finish.

**Question 6.** You are batching with `buffer(100)` yet the source might emit only 3 elements in an hour without completing. How do you emit the batch sooner?

**Answer:** Consider `bufferTimeout(100, Duration.ofSeconds(...))`; also explicitly allow batches smaller than 100 elements and define handling when the source goes silent.

**Question 7.** When should you use `groupBy`, and when should you use `bufferUntilChanged`?

**Answer:** Use `groupBy` when the same key from anywhere in the stream should go into one active group; use `bufferUntilChanged` when splitting into **consecutive runs** sharing the same key, so the same key can produce multiple segments.

## 17. Key Takeaways and References

- **`buffer` emits collections, `window` emits inner streams, `groupBy` emits keyed inner streams.**
- `size == skip` yields contiguous groups, `size > skip` yields overlapping groups, and `size < skip` skips elements in gaps.
- Predicate/time boundaries affect completion timing; `windowWhile` can emit empty windows, whereas `bufferWhile` does not emit empty lists.
- Inner `Flux`/`GroupedFlux` **must be consumed**; never use unbounded `collectList()` on infinite sources.
- `groupBy` fits **low/moderate controlled key cardinality**; combining low concurrency with interleaved keys risks backpressure stalls.
- In WebFlux, never call `block()` inside a reactive request handler; batching choices do not replace non-blocking I/O or transaction management.

Official documentation:

1. [Project Reactor — Three Sorts of Batching](https://projectreactor.io/docs/core/release/reference/advancedFeatures/advanced-three-sorts-batching.html): detailed comparison of `groupBy`, `window`, and `buffer`, overlap examples, and warnings about `groupBy` hangs.
2. [Project Reactor — Which Operator Do I Need?](https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html): operator lookup by scenario, including group/window/buffer.
3. [Flux API Reference](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): overloads and contracts for `buffer`, `window`, and `groupBy`.
4. [Reactor — Backpressure and Request Reshaping](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html): demand across operators.
5. [Spring WebFlux Reference](https://docs.spring.io/spring-framework/reference/web/webflux.html): using Reactor in Spring's HTTP stack.
