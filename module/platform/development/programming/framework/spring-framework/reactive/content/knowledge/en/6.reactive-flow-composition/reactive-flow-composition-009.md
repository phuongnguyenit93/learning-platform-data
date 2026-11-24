# Data Retention Risk, Unconsumed Groups, and Memory Growth in Project Reactor

In Spring WebFlux, we often split an event stream into **keyed groups** (`groupBy`), **windows** (`window`), or **batches** (`buffer`). These operations help with parallel processing, aggregation, and bounding work units. However, when a group has no subscriber, upstream keeps introducing new keys, or downstream buffers data until source completion, the pipeline can **hold many elements in RAM, stall due to backpressure, or run out of memory**.

This lesson focuses on the causes, symptoms, and mitigations for those issues within the **Combining and Splitting Streams** topic of Spring Reactive. The centerpiece is `Flux.groupBy`, while also connecting `window`, `buffer`, `collectList`, `flatMap`, and subscription lifecycle.

## 1. Objectives

After this lesson, you can:

- Distinguish a live `GroupedFlux` group from an already-collected result list.
- Explain why **every group must be consumed** for `groupBy` to keep progressing smoothly.
- Recognize the risk when group key cardinality is high and `flatMap` has too low a `maxConcurrency`.
- Distinguish backpressure stalls, backlogs, intentional data retention, and memory leaks.
- Avoid unbounded `collectList` on infinite sources; choose finite windows or batches.
- Write runnable Java 17+ Reactor examples, test with `StepVerifier`, and apply them in WebFlux.
- Choose memory-management measures while still honoring business requirements for completeness and ordering.

## 2. Three Stream-Splitting Patterns Create Three Kinds of State

| Operator | General result | Splitting rule | Main risk |
| --- | --- | --- | --- |
| `groupBy(key)` | `Flux<GroupedFlux<K,T>>` | By key; elements with the same key need not be adjacent | Many live groups; unconsumed groups; per-key backlog |
| `window(n)` / `windowTimeout(...)` | `Flux<Flux<T>>` | By size, time, or conditional boundary | Inner publishers not drained; waiting windows; queues |
| `buffer(n)` / `bufferTimeout(...)` | `Flux<List<T>>` | Collects elements into a collection then emits it | Lists holding payloads; many batches waiting downstream |
| `collectList()` | `Mono<List<T>>` | Collects **the entire source** until completion | Large/infinite source grows the List or never emits a result |

Crucial distinction: `groupBy` and `window` emit **inner publishers**. The fact that the outer `Flux` emitted a group does not prove the elements **inside that group** have been drained. Each inner publisher needs a downstream branch to subscribe and request data. `buffer`, on the other hand, constructs an actual `List` in RAM; it has no inner publisher needing a subscription.

```text
Source: A1 → B1 → A2 → C1 → B2 → A3 → ...
             │ groupBy(Event::key)
             ▼
Outer:      group A      group B      group C
               │            │            │
               ▼            ▼            └─ nobody reading?
          subscriber A  subscriber B            │
               │            │                  └─ waiting data/demand
               ▼            ▼
          process A     process B
```

“Reactive is non-blocking” does not mean “zero data retention”. Queues, collections, group metadata, in-flight requests, and socket buffers all consume memory even when threads never `sleep` or `block`.

## 3. `groupBy` Creates Live Groups, Not a Pre-Built Map

Suppose the source stream emits:

```text
Source:  A1  B1  A2  C1  B2  A3  C2  complete
Group A: A1      A2          A3       complete
Group B:     B1      B2               complete
Group C:             C1          C2   complete
```

`groupBy` creates a `GroupedFlux` whenever a new key is encountered. A group can receive elements at multiple non-contiguous points in time. Per Reactor's contract, groups are **unicast**, meaning each group is intended for a single subscriber; do not assume you can subscribe repeatedly as if it were a fresh cold publisher. Each source element is routed to the group matching its key.

If the source is a non-terminating event stream, a quiet group **does not automatically complete**. Therefore:

```java
// Fragment only: requires application's Event and liveEvents.
Flux<GroupedFlux<String, Event>> groups =
    liveEvents.groupBy(Event::category);
```

Emitting a `GroupedFlux` object only announces “this key has been seen”. To actually process data, downstream must consume the inner streams, for example:

```java
// Integration example: requires Event and handle(Event) method.
Flux<Result> handled = liveEvents
    .groupBy(Event::category)
    .flatMap(group -> group.map(this::handle), 4);
```

This example is sensible only if the number of live categories is controlled and concurrency is bounded appropriately; `Result` and `this::handle` are application-defined. Never apply this pattern blindly to hundreds of thousands of keys.

## 4. Why Can an Unread Group Stall the Entire Source?

Reactive Streams has `Subscription.request(n)`: a subscriber requests more elements, and operators propagate/reshape that demand upstream. At the same time, `groupBy` must route each element to the right group. What happens when some groups are not being read?

1. The source emits elements for keys A, B, C, D... interleaved.
2. `groupBy` opens multiple groups and routes items to their respective groups.
3. Downstream only subscribes to a few inners because `flatMap(..., maxConcurrency)` was set too low, or because it only processes the first group.
4. Unsubscribed groups can hold data in buffers without releasing demand.
5. Once buffer/request capacity hits its limit, the source can no longer keep emitting as before.
6. A group currently being read may be waiting for that very source to advance and deliver more elements or complete. Yet source progress is blocked by the undrained groups.

```text
    group A waiting for completion / final elements
                   ▲
                   │ needs upstream to advance
                   │
      upstream → groupBy → A (subscribed)
                   ├────→ B (not subscribed)
                   └────→ C (not subscribed)
                           │
                           ▼
                 B/C data not drained
                           │
                           └─ backpressure prevents source from advancing
```

The symptom can look like a “hang”: no `onError`, no `onComplete`, throughput drops to 0; a thread dump does not even show a lock deadlock. This is a **consumption–backpressure dependency cycle**. Reactor documentation warns about this condition when cardinality is high while consumer concurrency is too low.

### Anti-pattern: `groupBy` followed by `concatMap` collecting entire groups

```java
// ANTI-PATTERN: do not run in production or in tests without timeouts.
Flux<List<Integer>> risky = Flux.range(1, 1000)
    .groupBy(n -> n % 10, 8)
    .concatMap(group -> group.collectList());
```

The source has 10 interleaved keys. `concatMap` subscribes to only one group at a time. `collectList` waits for the first group to complete; meanwhile other groups can receive elements without being drained, causing `groupBy` to be stalled by backpressure. Depending on prefetch sizes, threads, and request patterns, the pipeline **may never finish**. Without claiming every finite input or every Reactor version always hangs, this is a structure to avoid.

### Anti-pattern: concurrency significantly lower than group count

```java
// ANTI-PATTERN: each category creates a group, only 2 groups processed at once.
Flux<Integer> risky = events
    .groupBy(Event::category)
    .flatMap(group -> group.map(Event::payloadSize), 2);
```

This is a fragment; `events` and `Event` must exist in the application. If there are many interleaved categories, limiting active groups to two can cause a stall. **Raising concurrency without limit is not the fix**: it merely shifts pressure onto subscription counts, other resources, and memory.

## 5. Cardinality: New Keys Can Grow Without Bound

| Key used for grouping | Characteristics | Assessment |
| --- | --- | --- |
| `INFO` / `WARN` / `ERROR` | Three predefined values | Usually suitable |
| Finite business status enum | Clear upper bound on values | Easy to budget group count |
| Region from a small catalog | Bounded if input is validated | Potentially suitable |
| `userId` | Can reach hundreds of thousands/millions | Consider another architecture |
| `sessionId`, `requestId`, fresh UUID | Nearly one group per item | Cardinality grows very rapidly |

If an infinite source continually generates new keys, many groups can stay alive while the source has not ended. There is no basis to treat `groupBy` as a cache with TTL or automatic business eviction. Group management overhead plus queued items can create substantial heap pressure.

Distinguish **intentional key-space reduction** from **losing semantics**: grouping by `userId.hashCode() % 8` produces eight buckets, mixing multiple users together. That is valid when the goal is sharding into eight processing partitions; it is invalid when you need per-user statistics.

### Memory is not just payload size

```text
Total pipeline-related memory ≈
  state of live groups
+ items in undrained group queues
+ items held by inner operators (List, sort, join...)
+ downstream / transport queues
+ application objects and references
```

This is a qualitative model, not an exact heap-byte formula. A 1 KB payload can require multiple objects or wrappers; queues and collections also carry overhead.

## 6. Backlog, Heap Growth, and Memory Leak Are Three Different Problems

**Backlog:** the consumer processes slower than the source produces. Items wait in queues; if rates rebalance and queues drain, memory can drop again.

**Retention by design:** `collectList()` legitimately retains items until completion; `sort()` or `groupBy` also holds intermediate state. If the source is huge or never ends, data can stay retained far too long even without a reference bug.

**Memory leak:** objects remain referenced even though they are no longer needed for work. Examples include a Map cache with no eviction, forgotten subscriptions, or a global list continually appending events.

All three can cause `OutOfMemoryError`, yet they must not be conflated. Diagnosing a memory leak requires inspecting **live heap after GC**, allocation rate, GC pressure, and retention paths. Do not jump to conclusions solely because process RSS does not drop immediately after a batch finishes.

With external **hot sources** (brokers/callbacks) that cannot slow down per `request(n)`, pipeline backpressure does not guarantee the physical source stops emitting. You must bound queues and define an explicit overflow policy: reject, spill to storage, rate-limit at ingress, or drop data only when business rules truly permit it. Silently dropping payment events cannot be the default.

## 7. Runnable Java 17+ Reactor Demo: Three Groups Drained

This example uses a finite source and exactly three groups; `flatMap(..., 3)` subscribes to up to three inners, enough for all three to be consumed. `collectList` is safe in scope here **because the source is finite with only 12 elements**.

Create the structure:

```text
reactor-group-memory/
├── pom.xml
├── src/main/java/GroupMemoryDemo.java
└── src/test/java/GroupMemoryTest.java
```

Contents of `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>reactor-group-memory</artifactId>
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

Contents of `src/main/java/GroupMemoryDemo.java`:

```java
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

import reactor.core.publisher.Flux;

public class GroupMemoryDemo {
    public static void main(String[] args) {
        Map<Integer, List<Integer>> groups = Flux.range(1, 12)
            .groupBy(n -> n % 3, 8)
            .flatMap(group ->
                group.collectList()
                    .map(items -> Map.entry(group.key(), items)),
                3)
            .collectMap(Map.Entry::getKey, Map.Entry::getValue)
            .block(Duration.ofSeconds(5));

        System.out.println("groups=" + new TreeMap<>(groups));

        List<List<Integer>> batches = Flux.range(1, 7)
            .buffer(3)
            .collectList()
            .block(Duration.ofSeconds(5));

        System.out.println("batches=" + batches);

        List<Integer> windowed = Flux.range(1, 7)
            .window(3)
            .concatMap(window -> window)
            .collectList()
            .block(Duration.ofSeconds(5));

        System.out.println("windowed=" + windowed);
    }
}
```

Run:

```bash
mvn -q compile exec:java -Dexec.mainClass=GroupMemoryDemo
```

Stdout:

```text
groups={0=[3, 6, 9, 12], 1=[1, 4, 7, 10], 2=[2, 5, 8, 11]}
batches=[[1, 2, 3], [4, 5, 6], [7]]
windowed=[1, 2, 3, 4, 5, 6, 7]
```

Explanation of results:

1. `n % 3` creates groups 1, 2, 0 on first appearance; `flatMap(..., 3)` consumes all three groups.
2. `group.collectList()` waits for each group to complete; because `Flux.range(1, 12)` is finite and all three groups are drained, the result completes.
3. `collectMap` gathers the three key-value pairs. `TreeMap` sorts keys so output has a deterministic 0, 1, 2 order.
4. `buffer(3)` creates batches of up to size three. Since there are only seven elements, the final batch holds one.
5. `window(3)` creates inner publishers. `concatMap(window -> window)` **subscribes to and drains each window**, so the resulting sequence matches the original source.
6. `block(Duration...)` here is solely for the console demo; never use it on the WebFlux event loop.

The example uses Reactor 3.6.9 and JUnit 5 for a standalone Maven project. In Spring Boot, let the BOM manage compatible dependency versions for your application.

## 8. Why Is `collectList` on Non-Terminating Groups Dangerous?

```java
// ANTI-PATTERN: long-lived event stream; groups normally never complete on their own.
Flux<GroupSummary> summaries = liveEvents
    .groupBy(Event::category)
    .flatMap(group ->
        group.collectList()
            .map(items -> summarize(group.key(), items)));
```

This code is only a **fragment**, requiring `liveEvents`, `Event`, `GroupSummary`, and `summarize` in the application. If the source never finishes, groups stay alive indefinitely. `collectList` on a group waits for completion while retaining every received element, never emitting periodic summaries. A large event stream can exhaust memory while the UI sees zero output.

The right approach when you need **statistics per time/batch interval** is placing a finite boundary inside each group:

```java
// Appropriate only when Event::category has at most four validated values.
Flux<GroupSummary> summaries = liveEvents
    .groupBy(Event::category)
    .flatMap(group ->
        group.windowTimeout(100, Duration.ofSeconds(2))
            .concatMap(window ->
                window.collectList()
                    .filter(batch -> !batch.isEmpty())
                    .map(batch -> summarize(group.key(), batch))),
        4);
```

Mechanism: each group is drained through `flatMap`, and `windowTimeout` produces windows that close when reaching element count or timeout. `collectList` collects items of only **one window**, emitting summaries while upstream continues.

Remember: a limit of **100 items per window** does not bound **the total number of completed-but-unprocessed windows**, payload size per item, group count, or queues in other layers. If the number of keys grows beyond four, this design must also change.

If you do not need grouping by key, `bufferTimeout(100, Duration.ofSeconds(2))` is simpler. Never use `groupBy` merely to split events into size-based batches.

## 9. `window`, `buffer`, and `collectList` Have Their Own Risks Too

### `window`

`Flux.window(n)` produces `Flux<Flux<T>>`. Emitting a window from the outer Flux does not prove the inner has been read. There should be an explicit processing branch:

```java
Flux<Long> counts = Flux.range(1, 250)
    .window(100)
    .concatMap(window -> window.count());
// When subscribed: 100, 100, 50, then complete.
```

Count-based windows normally have a completion boundary as soon as n elements arrive or the source ends. That is why `concatMap(window -> window.count())` on a finite source works cleanly, whereas `concatMap(group -> group.collectList())` on interleaved groups can create a dependency cycle: keyed groups do not complete at a 100-element boundary.

### `buffer`

`buffer(100)` creates a `List` of up to 100 elements per batch, while retaining data in memory during accumulation. A hundred large items can make a very heavy batch; if downstream is slow, multiple batches sitting in subsequent buffers can still grow RAM.

`bufferTimeout(maxSize, maxTime)` keeps a batch from waiting indefinitely for full count on sparse sources, yet it does not cap total memory across all queues. Also design concurrency and capacity for steps after the buffer.

### `collectList`

`collectList()` emits only when **upstream completes**. On an infinite stream, it can wait forever:

```java
// ANTI-PATTERN: accumulates until cancelled, errored, or OOM.
Mono<List<Long>> forever = Flux.interval(Duration.ofMillis(10))
    .collectList();
```

If you genuinely need only the first 50 elements:

```java
Mono<List<Long>> first50 = Flux.interval(Duration.ofMillis(10))
    .take(50)
    .collectList();
```

`take(50)` completes downstream after 50 items and cancels upstream. This **intentionally discards later items**; it is valid only when business logic wants “the first 50 elements”. For an event stream that must process every item, use repeated batching or incremental processing rather than truncating arbitrarily.

## 10. `maxConcurrency` and `prefetch` Are Not Hard RAM Ceilings

`flatMap(mapper, maxConcurrency)` limits how many inners are subscribed to concurrently; `groupBy(keyMapper, prefetch)` controls upfront demand requested from the source. These parameters tune demand/backpressure, yet:

- A `maxConcurrency` that is too **small** relative to live groups can leave other groups undrained and cause a stall.
- A `maxConcurrency` that is too **large** can spawn excessive subscriptions, concurrent work, and buffers.
- `prefetch` changes how many elements can be requested ahead, yet **does not cap the number of new keys** and does not represent heap bytes.
- Queues from `flatMap`, `flatMapSequential`, HTTP clients, schedulers, serialization, or other operators still carry their own memory cost.

For example, `flatMapSequential` can subscribe to many inners simultaneously while holding results of early-completing inners so downstream sees **original source order**. One very slow first inner can cause **head-of-line blocking**, keeping subsequent results in a queue. That is a different retention mechanism from `groupBy`, yet one you must evaluate when composing streams.

You cannot write a simple formula “max memory = concurrency × prefetch” for the entire application. Measure payload sizes, live group counts, in-flight items, and actual buffers.

## 11. Safer Design Strategies

| Business need | Appropriate solution | What to verify |
| --- | --- | --- |
| Group by three fixed states | `groupBy` + `flatMap` draining all three | Actual cardinality, concurrency, and source lifecycle |
| Aggregate over an infinite stream | Count/time windows or incremental reducers | Avoid full-stream `collectList` |
| Split 500 records into batches | `buffer(500)` or `bufferTimeout(...)` | Item size and backlog |
| Process per `userId` with millions of keys | Keyed state with TTL/eviction, partitioning, or a dedicated stream processor | State persistence, recovery, and eviction semantics |
| Need results in original order | `concatMap` / `flatMapSequential` where suitable | Slow-inner latency and waiting queues |
| No output ordering needed | Bounded `flatMap` | Concurrency and throughput |
| Non-throttlable hot source | Bounded queues and explicit overload policy | Never drop critical data without authorization |
| Only need item count of a finite source | `count()` | Avoid `collectList().map(List::size)` |
| Want to drop certain keys before grouping | Filter items **before `groupBy`** | Do not leave created groups undrained |

**Filtering groups at the outer level** while ignoring inners can leave unconsumed groups behind. If business rules allow dropping events by key, filtering items before `groupBy` is usually much cleaner because excluded groups are never created in the first place. If you must create a group and then decide to drop it, explicitly design cancellation/draining and its effect on remaining data per Reactor semantics.

## 12. Spring WebFlux: Windowed Event Statistics

The controller integration example below assumes `service.events()` is a `Flux<Event>`, every Event has a category among **at most four validated values**, and the DTO is `CategoryCount(String category, long count)`.

```java
import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
public class EventStatsController {

    private final EventService service;

    public EventStatsController(EventService service) {
        this.service = service;
    }

    @GetMapping(value = "/stats",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<CategoryCount> stats() {
        return service.events()
            .groupBy(Event::category)
            .flatMap(group ->
                group.windowTimeout(100, Duration.ofSeconds(2))
                    .concatMap(window ->
                        window.count()
                            .filter(count -> count > 0)
                            .map(count ->
                                new CategoryCount(group.key(), count))),
                4);
    }
}
```

This is a **Spring WebFlux snippet** with no `main`, requiring the Spring WebFlux starter and declarations of `EventService`, `Event`, and `CategoryCount`. Only once those components exist can the code compile in a real project.

Helpful property: `window.count()` keeps only a counter per window rather than retaining the whole batch payload. Groups are subscribed via `flatMap` and the expected group count is capped. When upstream never ends, the SSE endpoint can keep streaming incremental results instead of waiting on a full-stream `collectList`.

Still, you must clarify:

1. What happens if the service emits a fifth category?
2. Could a client disconnect without releasing the subscription?
3. How does the application handle a hot source when the HTTP downstream is slow?
4. How are SSE client timeouts/heartbeats and network errors reported?
5. Can batches/windows be produced faster than response encoding speed?

Never call `subscribe()` manually inside the controller; **return the publisher to WebFlux** so the framework manages subscription, errors, and cancellation along the HTTP lifecycle. Never call `block()` or `Thread.sleep` on the Netty event loop to “wait for groups”.

## 13. Error Handling and Cancellation

An error inside one group or inner can terminate the outer pipeline and cancel other publishers, depending on the operator. If business rules want each item to yield its own success/failure outcome, convert errors **inside the item-processing branch** into a status-carrying result object instead of blindly swallowing exceptions.

```java
// Integration fragment: requires Event, Outcome, handler, and business error types.
Flux<Outcome> outcomes = events
    .groupBy(Event::category)
    .flatMap(group ->
        group.flatMap(event ->
            handler.handle(event)
                .map(result -> Outcome.ok(group.key(), result))
                .onErrorResume(error ->
                    Mono.just(Outcome.failed(group.key(), event.id()))),
            8),
        4);
```

This snippet has two concurrency levels: up to four outer groups, and eight concurrent item handlers per group. **If group count is unbounded, 4 can still be too low; if the source is very hot, 4 × 8 can also generate heavy load.** Base limits on downstream system capacity rather than picking arbitrary numbers.

For long-lived sources, handle client/user unsubscription cleanly. `doOnCancel` and `doFinally` help observe lifecycle events, yet **cancel is not equivalent to `onComplete`** and does not undo API calls that already happened.

`timeout` helps prevent an inner from waiting forever, provided you place it at the right **scope**. A timeout on an entire infinite SSE stream can trigger errors during valid quiet periods. Per-subrequest timeouts are usually clearer. Never use infinite retries to mask a stall caused by undrained groups: retries can re-subscribe and repeat side effects.

## 14. Testing with `StepVerifier`

Create `src/test/java/GroupMemoryTest.java` in the Maven project from section 7:

```java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class GroupMemoryTest {

    @Test
    void allThreeGroupsAreConsumed() {
        Flux<String> output = Flux.range(1, 12)
            .groupBy(n -> n % 3, 8)
            .flatMap(group ->
                group.count().map(n -> group.key() + ":" + n),
                3)
            .sort();

        StepVerifier.create(output)
            .expectNext("0:4", "1:4", "2:4")
            .verifyComplete();
    }

    @Test
    void bufferEmitsBoundedBatches() {
        StepVerifier.create(Flux.range(1, 7).buffer(3))
            .expectNext(
                List.of(1, 2, 3),
                List.of(4, 5, 6),
                List.of(7))
            .verifyComplete();
    }

    @Test
    void takeCancelsUpstreamAfterLimit() {
        AtomicBoolean cancelled = new AtomicBoolean();

        Flux<Integer> source = Flux.range(1, 10)
            .doOnCancel(() -> cancelled.set(true));

        StepVerifier.create(source.take(3))
            .expectNext(1, 2, 3)
            .verifyComplete();

        assertTrue(cancelled.get());
    }
}
```

Run:

```bash
mvn -q test
```

Maven exits with code 0 when all three tests succeed; depending on `-q`, detailed reports may be suppressed. The first test proves a finite stream with three groups consumes and completes all three. The second test verifies correctly sized batches. The third test verifies `take(3)` actively cancels the upstream subscription once enough elements arrive.

**Note when testing stall-prone pipelines:** never call `verifyComplete()` or `block()` unboundedly on a dangerous anti-pattern. Put a time limit on the test, for example:

```java
// Replacement fragment for the first test's assertion; import Duration.
StepVerifier.create(output)
    .expectNext("0:4", "1:4", "2:4")
    .expectComplete()
    .verify(Duration.ofSeconds(3));
```

You can use test-runner timeouts and isolated experiments to study stalls, without letting an illustrative example hang CI. Do not run tests with infinite group counts or endlessly growing Lists merely to prove OOM.

## 15. Diagnosing a Stalled Pipeline

When active requests stop draining, heap grows, and no errors appear, check in order:

**Check the flow:** is `groupBy` present? How many distinct keys exist? Does every `GroupedFlux` have a subscriber? Is `maxConcurrency` too low for the number of open groups? Did anyone call `collectList` on an infinite group? Is any inner not receiving `request` or waiting on downstream?

**Check boundaries:** is the source finite or infinite? When do groups/windows complete? Are there explicit `take`, `timeout`, cancellation, or group-closing mechanisms? Does an error-handling branch merely log and abandon the subscription?

**Check memory:** live heap after GC, allocation rate, retained `List`/queue instances, group counts, and backlog depth. For hot sources, measure emitted events vs. consumed events, not just API throughput.

**Check observability overhead:** avoid logging huge raw payloads or using per-userId/UUID values as metric labels; metric cardinality itself can drive memory growth. Prefer aggregating group counts, queued items, processing rates, wait times, and GC metrics.

An application instrumentation fragment:

```java
Flux<Result> observed = source
    .groupBy(Event::category)
    .flatMap(group ->
        group
            .doOnSubscribe(s -> metrics.groupSubscribed())
            .doOnCancel(() -> metrics.groupCancelled())
            .map(this::transform),
        4);
```

`source`, `Event`, `Result`, `metrics`, and `transform` are application-defined. Place `doOnNext` after processing to count items actually flowing through; do not conclude draining succeeded merely because the outer Flux emitted a group.

## 16. Common Mistakes

1. **Receiving a group without consuming the inner:** `groupBy` emits a `GroupedFlux`, not the group's full list.
2. **Using requestId/UUID as the group key:** cardinality approaches the total event count.
3. **Using `concatMap(group -> group.collectList())` with interleaved keys:** the first group waits for source completion while other groups stay undrained.
4. **Setting `flatMap` concurrency too low:** groups waiting to be subscribed cause backpressure to block source progress.
5. **Raising concurrency without limit:** turns a stall into resource exhaustion.
6. **`collectList` on an infinite stream:** never emits a result while retaining data indefinitely.
7. **Assuming `buffer(100)` always uses little total memory:** payload size and queued batches determine actual usage.
8. **Not subscribing to windows:** inner publishers are not drained just because the outer emitted them.
9. **Confusing a stalled pipeline with a Java thread deadlock:** backpressure can halt progress with zero locked threads.
10. **Confusing backlog with a memory leak:** inspect heap dumps and retention paths before concluding.
11. **Dropping groups at the outer level without deciding the fate of their data:** filter items before grouping if dropping is genuinely allowed.
12. **Feeding a hot source into unbounded buffers:** risks OOM when consumers slow down.
13. **Calling `subscribe()` inside a controller and discarding the disposable:** detaches the stream from HTTP request cancellation.
14. **Assuming timeouts fix everything:** if groups are not drained, timeouts simply turn the stall into another error.
15. **Skipping load tests and metrics:** bugs appear only when cardinality, throughput, or latency exceeds small demo conditions.

## 17. Self-Check Exercises

**1.** A stream of 1,000,000 events has 3 category values. Why is `groupBy(category)` far more reasonable than `groupBy(requestId)`?  
**Answer:** Category has low cardinality, so three groups can be drained in a controlled manner. RequestId can create nearly a million groups with heavy state and queue risks.

**2.** Why can `groupBy(key).concatMap(g -> g.collectList())` stop making progress?  
**Answer:** `concatMap` waits for the first group to complete, yet upstream may need other groups to be consumed before it can keep emitting and finish. Interleaved undrained groups create a backpressure dependency cycle.

**3.** A group was emitted by the outer `Flux<GroupedFlux>` but has not been subscribed to yet. Can its data be considered processed?  
**Answer:** No. There must be an inner consumer with appropriate element demand.

**4.** Given an infinite source, you need the item count per minute. Should you use `collectList()` and count the whole List?  
**Answer:** No. Use time-based windows or bounded incremental counters to avoid retaining entire payloads.

**5.** Does `buffer(100)` guarantee the app uses RAM for at most 100 items?  
**Answer:** No. Multiple batches and downstream queues can coexist, and items vary in size.

**6.** When `flatMap(maxConcurrency=2)` handles 50 live keys, should you immediately raise it to 50,000?  
**Answer:** No. Control cardinality/lifecycle first; choose appropriate concurrency and measure memory and downstream system load.

**7.** An SSE client closed the connection, yet the source stream keeps running because it was subscribed manually. What is the risk?  
**Answer:** The orphaned subscription can keep holding state/buffers and resources; return the publisher to WebFlux to manage lifecycle and propagate cancellation.

**8.** How do `window(100).concatMap(w -> w.count())` and `groupBy(key).concatMap(g -> g.count())` differ?  
**Answer:** Fixed windows normally complete by element count. Keyed groups can stay open until upstream completes, so `concatMap` risks leaving other groups waiting undrained.

**9.** If a heap graph climbs and then drops after GC, is that definitely a memory leak?  
**Answer:** No. Evaluate live heap across multiple cycles, retention paths, queues, and data progress.

**10.** If the system must process every transaction, can you use `onBackpressureDrop()` to prevent OOM?  
**Answer:** Not arbitrarily; dropping loses events. Choose a backpressure/bounded-storage strategy or reject input according to the business contract.

## 18. Pre-Production Checklist

- **Cardinality:** is there a clear ceiling on keys, or can every item open a new group?
- **Consumption:** is there an actual subscriber/drainer for every group and window that must be processed?
- **Completion:** when do the source and each inner publisher complete; is any `collectList` waiting indefinitely?
- **Concurrency:** is `maxConcurrency` high enough to avoid starving groups yet bounded so resources are not exhausted?
- **Prefetch:** have queues, throughput, and actual demand been verified?
- **Memory:** are payload sizes, queued batch counts, live heap, and GC measured?
- **Cancellation:** does client disconnect cancel the associated work?
- **Errors/timeouts:** are recovery, error responses, retries, and deadlines properly configured?
- **Hot sources:** are bounded queues or ingress throttling in place with an approved overflow policy?
- **Testing:** do tests have deadlines so CI cannot hang; are dangerous anti-patterns run only in isolation?
- **Correctness:** do all filtering, dropping, key-bucketing, or reordering choices conform to business rules?

**Key message:** `groupBy` emits live groups and requires downstream to consume them; if key count is high or group consumers stall, backpressure can halt the source and retain data. `window`, `buffer`, and `collectList` each carry distinct memory costs too. A resilient design simultaneously defines **group count, maximum retained data, lifecycle, consumer speed, and cancellation/error handling**.

### References

- Project Reactor, [Three Sorts of Batching — Grouping, Windowing, Buffering](https://projectreactor.io/docs/core/release/reference/advancedFeatures/advanced-three-sorts-batching.html).
- Project Reactor, [Flux Javadoc — groupBy and group draining requirements](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- Project Reactor, [Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/).
- Project Reactor, [Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html).
- Spring Framework, [Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html).
- [Reactive Streams Specification](https://www.reactive-streams.org/).
