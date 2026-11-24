# Memory Impact of collectList, cache, and replay in Project Reactor

## 1. Goal and Context

Project Reactor enables streaming data processing, yet several operators actively retain data to produce aggregated results or serve late subscribers. Three common cases are:

- **collectList()** holds all elements of a Flux in a List and emits the List only when the source completes.
- **cache()** retains signals so subsequent subscribers receive previously emitted data.
- **replay()** retains signal history in a ConnectableFlux so late subscribers can replay it.

These operators are useful when datasets are small, finite, and governed by explicit retention policies. They become hazardous when applied to long streams, infinite streams, large payloads, high concurrency, or long-lived publishers such as singleton beans.

A reactive application can still throw an OutOfMemoryError. Backpressure does not automatically stop an operator from deliberately accumulating data in memory.

This lesson covers how operators accumulate data, how to bound history, choosing streaming/batching/pagination, estimating heap usage, observing memory, and writing tests with Java 17, Reactor 3.8.8, and JUnit.

## 2. How Does collectList() Work?

API returning a Mono containing a List:

~~~java
Mono<List<T>> result = source.collectList();
~~~

collectList consumes every element emitted by the Flux, adds them to a List, and emits that List when the source **completes**. If the source is empty, the result is an empty List.

~~~java
Flux.range(1, 5)
    .collectList()
    .subscribe(System.out::println);
~~~

Output:

~~~text
[1, 2, 3, 4, 5]
~~~

Throughout collection, the List holds references to every received element. Only when the source completes does Mono<List<T>> emit the result downstream.

### 2.1. collectList Does Not Stream Elements One by One

~~~java
Flux<Order> orders = repository.findAll();
Mono<List<Order>> allOrders = orders.collectList();
~~~

allOrders does not emit each Order individually. It waits for findAll to complete and then emits a single List. If the source has 5 million records, collectList must retain all 5 million elements in memory. If the source never completes, the List keeps growing and the Mono never emits a result.

### 2.2. collectList on an Infinite Source

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofMillis(10));
Mono<List<Long>> neverFinishes = ticks.collectList();
~~~

ticks emits continuously and does not complete on its own. collectList retains values until completion, error, or cancellation. If the subscription lives long enough, the list can grow until heap is exhausted.

Do not use collectList on an infinite event stream without an explicit element cap or window.

### 2.3. Bounding the Source Before Collecting

~~~java
Mono<List<Order>> firstHundred =
    repository.findAll()
        .take(100)
        .collectList();
~~~

take(100) caps element count before collectList. This yields a finite and more predictable set. Even so, 100 elements can still be huge if each Order holds a heavy object graph. Count limits must go hand in hand with data size limits.

### 2.4. collectSortedList Also Costs Extra CPU

~~~java
Mono<List<Order>> sorted =
    orders.collectSortedList(
        Comparator.comparing(Order::createdAt)
    );
~~~

collectSortedList must hold all data to sort after completion. For n elements, sorting typically takes O(n log n) time complexity, while memory remains O(n). For large datasets, sort in the database using an index or read via keyset pagination.

## 3. Other collect Operators Can Also Retain Data

| Operator | Accumulated Structure | Growth by Data |
| --- | --- | --- |
| collectList() | List containing every element | O(n) |
| collectSortedList() | List containing every element, then sorted | O(n), plus sort CPU |
| collectMap() | Map by key, keeping the latest value per key | O(unique keys) |
| collectMultimap() | Map key -> Collection containing values | O(total elements) |
| collect(Collector) | Container defined by the Collector | Depends on accumulator |
| distinct() | Set of seen keys | O(unique keys) |
| buffer() | One buffer holding all elements until complete | O(n) |
| replay()/cache() | Signal history retained for later subscribers to read | Depends on history/TTL |

### 3.1. collectMap and collectMultimap

~~~java
Mono<Map<String, User>> usersById =
    users.collectMap(User::id);

Mono<Map<String, Collection<Event>>> eventsByType =
    events.collectMultimap(Event::type);
~~~

collectMap keeps the latest value for each key. If there are 10 million distinct IDs, the Map can still hold 10 million entries. collectMultimap keeps every Event in a per-key collection; a high-frequency key can cause its collection to keep growing.

### 3.2. distinct Also Retains Seen History

~~~java
Flux<Event> unique = events.distinct(Event::id);
~~~

distinct must remember seen keys to detect duplicates. With a high-cardinality infinite source, the key set can grow unbounded. If you only need a deduplication window, choose a mechanism with explicit retention/windowing.

### 3.3. Parameterless buffer() Is Also a Form of collect

~~~java
Flux<List<T>> oneLargeBuffer = source.buffer();
~~~

buffer() collects all elements into one List and emits when the source completes. It carries the same accumulation risk as collectList. Use buffer(maxSize) or bufferTimeout(maxSize, maxTime) when finite batches are needed.

## 4. Flux.cache() Is Replay Memory

Flux.cache() turns a source into a hot, replaying Flux. The first subscriber triggers the source subscription; later subscribers receive cached signals according to the overload's policy.

~~~java
Flux<Integer> cached = Flux.range(1, 5).cache();
~~~

If there are two subscribers, both can receive values 1 through 5; the later subscriber is replayed the cached data.

### 4.1. cache() Has Unbounded History

~~~java
Flux<Event> events = eventSource.cache();
~~~

The cache() overload retains an unbounded onNext history. With an infinitely emitting event source, the number of retained signals can grow forever.

This is a common cause of memory retention: the code has no infinite loop or hand-written static collection, yet the cache operator retains every event for replay.

### 4.2. Cache Retains Terminal Signals Too

Beyond onNext, cache also replays completion and error signals. If a source has errored, later subscribers may receive the cached error instead of triggering a fresh load. This is useful for sharing a single outcome, yet it can also keep transient errors around longer than expected.

### 4.3. Cache Holds References, Not Deep-Copied Objects

If the source emits an Order object, cache holds a reference to that object. Later subscribers receive the cached object itself, not an independent deep copy.

- Large objects retain the entire reachable object graph.
- Mutating an object after caching can cause other subscribers to observe modified state.
- Objects holding DataBuffer/ByteBuf or lifecycle-managed resources should not be retained/replayed indiscriminately.
- Caches should hold immutable data or a representation safe for sharing.

### 4.4. A Cache Can Live as Long as a Singleton Service

~~~java
@Service
public class EventService {
    private final Flux<Event> cached =
        eventRepository.streamAll().cache();
}
~~~

If the service is a singleton and `cached` is stored in a field, the cache can live for the application's entire lifetime. With an infinite source, the full history can remain retained in heap.

Check where publishers are created, which bean holds them, and how long objects referencing the publisher can survive.

## 5. cache(int history): Bounding by Element Count

~~~java
Flux<Event> recentEvents = eventSource.cache(1_000);
~~~

Reactor keeps at most the 1,000 most recent onNext signals to replay to later subscribers. Terminal complete/error signals are also replayed. cache(0) caches only terminal signals, storing no onNext elements.

### 5.1. History Example

~~~java
Flux<Integer> recent = Flux.range(1, 10).cache(3);
~~~

The first subscriber receives the entire source:

~~~text
1, 2, 3, 4, 5, 6, 7, 8, 9, 10
~~~

A later subscriber receives only the three most recently stored elements:

~~~text
8, 9, 10
~~~

Bounding history puts a ceiling on retained references regardless of how many elements the source has emitted.

### 5.2. Count Limit Is Not a Byte Limit

If one Event takes a few hundred bytes, 1,000 events may be tiny. Yet if each Event holds a 5 MiB image or a huge object graph, 1,000 elements can still exceed multiple GiB.

Choose history based on element count, average/maximum size, object graph, number of publisher/cache instances, and queues in other layers. If data sizes vary widely, cap payload size before caching or use a byte-budgeted cache at the appropriate layer.

## 6. cache(Duration ttl): TTL Does Not Mean Element Count Limit

~~~java
Flux<Event> recentByTime =
    eventSource.cache(Duration.ofMinutes(5));
~~~

Each item has a retention time governed by TTL. Terminal signals are also replayed until the corresponding TTL expires; after expiration, a new subscriber can trigger a new upstream subscription.

**Crucial point:** cache(Duration) keeps an unbounded count history and applies per-item expiry. If the source emits 100,000 items within 5 minutes, the cache can retain a massive number of items in that time window.

TTL alone is not a hard memory cap.

Example:
- Rate of 100 events/second.
- TTL of 300 seconds.
- Events remaining in the window can reach roughly 30,000.
- If the rate spikes to 10,000 events/second, events within the same TTL can reach 3 million.

When using TTL, estimate peak event rate rather than looking only at TTL duration.

## 7. cache(history, ttl): Dual Bound

~~~java
Flux<Event> bounded =
    eventSource.cache(
        1_000,
        Duration.ofMinutes(5)
    );
~~~

Reactor keeps at most a history of 1,000 items and applies a per-item TTL. This is the clearer choice when both dimensions must be bounded.

| Configuration | Count Bound | Time Bound |
| --- | --- | --- |
| cache() | No | No |
| cache(history) | Yes | No |
| cache(ttl) | No hard cap | Yes, per item |
| cache(history, ttl) | Yes | Yes |
| cache(0) | Stores no onNext | No expiry for terminal signal |

Overloads accepting a Scheduler let you select an appropriate clock/timer when scheduler control is required.

### 7.1. Choosing History by Load

If the system emits at most 200 events/second and you want to replay roughly the last 10 seconds, you can start with a history of around 2,000 items. Then test with realistic bursts, event sizes, and active cache instance counts.

Do not set history to an enormous number just to avoid missing data. Cache is a short-term in-memory replay mechanism, not a durable event store.

### 7.2. TTL Does Not Immediately Clear Objects Everywhere

When an item expires in the cache, the cache stops serving it to new subscribers under the TTL policy. However, the object can be garbage-collected only when no strong references remain from the cache, active subscribers, other collections, thread-locals, or application data structures.

TTL does not guarantee heap immediately drops by the exact byte count upon expiration.

## 8. replay() and ConnectableFlux

replay() also creates a hot source retaining history for later subscribers. The key difference is that replay returns a **ConnectableFlux**; the application controls when the source starts via connect() or connection strategies.

~~~java
ConnectableFlux<Event> replay =
    eventSource.replay(100);

replay.connect();
~~~

Later subscribers can receive up to the 100 most recent elements per the configured history.

### 8.1. Unbounded replay()

~~~java
ConnectableFlux<Event> allHistory = eventSource.replay();
~~~

replay() retains unbounded onNext history. If the source is a long-lived event stream, memory grows over time.

### 8.2. replay(int history)

~~~java
ConnectableFlux<Event> lastHundred = eventSource.replay(100);
~~~

Retains up to the 100 most recent elements, plus the terminal signal when the source completes/errors.

### 8.3. replay(Duration ttl)

~~~java
ConnectableFlux<Event> lastFiveMinutes =
    eventSource.replay(Duration.ofMinutes(5));
~~~

Per-item TTL sets no hard element cap. A very high-rate stream can still accumulate many items within that duration.

### 8.4. replay(history, ttl)

~~~java
ConnectableFlux<Event> boundedReplay =
    eventSource.replay(
        1_000,
        Duration.ofMinutes(5)
    );
~~~

Combines history and TTL bounds. This is appropriate when both the time window and replay item count must be controlled.

### 8.5. connect, autoConnect, and refCount

| Connection Method | Behavior |
| --- | --- |
| connect() | Actively starts the source |
| autoConnect(n) | Connects automatically once n subscribers join; does not auto-disconnect when subscribers leave |
| refCount(n) | Connects when n subscribers join and manages disconnect based on subscriber count |
| refCount(n, gracePeriod) | Waits a grace period before disconnecting when subscribers drop below threshold |

Connection strategies determine when the source runs and when the upstream subscription is managed. They do not replace history/TTL policies. To bound replay memory, you must still use replay(history) or replay(history, ttl).

## 9. Comparing collectList, cache, replay, and share

| Operator | Data Retained | When Emitted/Replayed? | Primary Risk |
| --- | --- | --- | --- |
| collectList() | All elements in a List | When source completes | O(n), infinite sources never emit |
| cache() | All onNext and terminal signals | First subscriber triggers, later subscribers get history | Unbounded history |
| cache(history) | Up to N most recent onNext signals | Auto-connects as needed | N too large or payloads too heavy |
| cache(ttl) | History within TTL, no hard count cap | Auto-connects as needed | Heavy bursts still retain many items |
| cache(history, ttl) | Up to N items and per-item TTL | Auto-connects as needed | Mis-sized N/TTL |
| replay() | Full history | connect()/autoConnect/refCount | Unbounded history |
| replay(history) | Up to N items | ConnectableFlux, controlled connect | History too large |
| share() | Shares live signals among active subscribers, not full history replay | Connects per subscriber | Unsuitable if late subscribers need history |

share() is not equivalent to cache(). If late subscribers need to receive prior history, share does not provide history replay semantics like cache/replay.

## 10. Combining collectList and cache Can Retain Data at Multiple Layers

~~~java
Mono<List<Order>> listOnce = orderFlux.collectList();

Mono<List<Order>> cachedList =
    orderFlux.collectList().cache();
~~~

cachedList caches a terminal signal containing a List. The list and the objects inside it may be retained for the lifetime of the cached Mono.

Another pattern:

~~~java
Flux<Order> cachedOrders = orderFlux.cache();

Mono<List<Order>> allOrders =
    cachedOrders.collectList();
~~~

Here, the Flux cache retains history; collectList creates an additional List holding references to emitted Orders. While subscribers receive and process the List, both the cache and the List can hold references to the object graph simultaneously.

This does not necessarily duplicate the entire payload since the List and cache may point to the same objects. However, it adds another reference-holding structure and extends data lifetime.

### 10.1. Do Not Cache Huge Lists Just to Avoid Re-Querying

If results contain millions of rows, consider storing results in a database/object storage, caching small metadata or summaries, using keyset pagination, partitioning results by tenant/partition, bounding TTL and entry count in an external cache, and caching only data truly accessed repeatedly.

### 10.2. Cache Is Not a Deep Copy

If one subscriber mutates a List or mutable object received from a cache, other subscribers can see that mutated state. Use immutable DTOs, intentional copies, or return projections without mutable resources.

## 11. Backpressure Does Not Automatically Bound Memory Retention

Backpressure regulates demand between Publisher and Subscriber. It does not prevent an operator from intentionally accumulating data.

~~~java
Flux<Event> events = eventSource
    .limitRate(100)
    .cache();
~~~

limitRate shapes upstream requests in batches. cache still retains history per cache policy; with unbounded cache(), memory can still grow with total event count.

Similarly:

~~~java
eventSource
    .onBackpressureBuffer()
    .collectList();
~~~

This pipeline can have both buffer and list accumulation. If the source outpaces downstream, backlogs can grow at multiple layers.

### 11.1. Memory Layers to Inspect

~~~text
Source / driver prefetch
        |
        v
Reactor operator queues
        |
        v
buffer / flatMap / publishOn
        |
        v
cache / replay history
        |
        v
collectList / collectMap
        |
        v
application references / response serialization
~~~

A limit at one operator does not mean the whole pipeline has an equivalent limit. Inspect concurrency, prefetch, batch size, cache history, and data held by controllers/services.

### 11.2. flatMap and Concurrency

~~~java
source.flatMap(this::remoteCall, 32, 64);
~~~

Concurrency bounds how many inner Publishers run simultaneously; prefetch controls how many items are requested/held per inner. If each inner returns a large object, total memory can approximate concurrency × prefetch × object size, plus other queues.

Do not raise concurrency and prefetch purely to chase throughput without measuring retained heap.

## 12. Alternatives to collectList for Large Datasets

### 12.1. Stream Processing Item by Item

~~~java
return repository.findAll()
    .map(this::toResponse)
    .doOnNext(this::recordMetric);
~~~

The controller can return the Flux directly or continue composing downstream. Each item is processed as a stream; there is no need to build a full List.

### 12.2. Reduce to Fixed-Size State

~~~java
Mono<Long> totalQuantity =
    orderLines.map(OrderLine::quantity)
        .reduce(0L, Long::sum);
~~~

The accumulator is just a Long, so accumulated memory does not grow with element count. However, if the accumulator is an unbounded List/Map, reduce can still accumulate O(n).

### 12.3. Count, any, and all

~~~java
Mono<Long> count = source.count();

Mono<Boolean> hasInvalid =
    source.any(item -> !item.isValid());

Mono<Boolean> allValid =
    source.all(Item::isValid);
~~~

These operators do not retain full history like collectList. any/all can short-circuit as soon as a result is known and cancel upstream.

### 12.4. take(limit)

~~~java
Mono<List<Event>> firstPage =
    source.take(500)
        .collectList();
~~~

Cap the element count before collecting. This is a simple solution for finite datasets with an explicit ceiling.

### 12.5. buffer(maxSize)

~~~java
Flux<List<Event>> batches = source.buffer(500);
~~~

Each batch holds at most 500 items. When full, it is emitted downstream; the final batch may be smaller if the source completes.

~~~java
return source.buffer(500)
    .concatMap(batch ->
        repository.saveBatch(batch)
    );
~~~

concatMap keeps one batch in-flight at a time, giving better concurrency control. Still, evaluate queues/prefetch of operators and drivers.

### 12.6. bufferTimeout(maxSize, maxTime)

~~~java
Flux<List<Event>> batches =
    source.bufferTimeout(
        500,
        Duration.ofSeconds(1)
    );
~~~

A batch is emitted upon reaching 500 items or after one second. This avoids holding a small batch for too long when the source emits slowly.

Time limits do not replace size limits: if the source emits fast, maxSize remains a critical guardrail.

### 12.7. window(maxSize)

~~~java
Flux<Flux<Event>> windows = source.window(500);
~~~

window emits inner Fluxes, each containing at most 500 events. Consumers must compose each window properly; avoid holding many unconsumed windows simultaneously if you want to control memory.

## 13. Pagination Instead of findAll().collectList()

A common mistake:

~~~java
return repository.findAll().collectList();
~~~

As a table grows over time, requests can load the entire dataset into heap. Use pagination or keyset pagination instead.

### 13.1. Offset Pagination

~~~java
Flux<Order> page =
    repository.findByStatus(
        status,
        PageRequest.of(0, 500)
    );
~~~

Offset pagination is simple, yet large offsets can be costly for the database and results can shift across pages if data is updated concurrently.

### 13.2. Keyset Pagination

~~~java
Mono<List<Order>> loadPage(long afterId) {
    return repository.findTop500ByIdGreaterThanOrderById(afterId)
        .collectList();
}
~~~

Each page is capped at 500; then the last ID is used to fetch the next page. Keyset pagination is generally more stable for large datasets with proper indexes.

### 13.3. Do Not Collect All Pages into One Final List

~~~java
Flux<Order> allPages =
    pageIds.concatMap(this::loadPage)
        .flatMapIterable(page -> page);
~~~

This illustrative snippet requires pageIds and loadPage. Calling collectList() at the end of the pipeline defeats the memory benefit of pagination. Process or write each page as it arrives, retaining only a summary if business logic needs one.

## 14. Memory Estimation and Capacity Planning

A simple estimate:

~~~text
Retained payload ≈ item count × average retained bytes
Total memory ≈ retained payload + collection/cache overhead
                 + other operator queues + active request state
~~~

Hypothetical example:
- 100,000 records in a single collectList.
- Each record and its retained object graph averages roughly 1 KiB.
- One request can retain roughly 97.7 MiB of payload.
- If 50 requests run concurrently, payload alone equals roughly 4.8 GiB, before counting List arrays, object headers, references, serializers, queues, and other objects.

This is only a rough budget calculation. Actual size must be measured with a heap profiler because object graphs, alignment, shared references, and compressed oops affect the footprint.

### 14.1. Concurrency Multiplies Memory

One request using 50 MiB may be acceptable in a small environment. Yet 100 concurrent requests each holding 50 MiB exceed 5 GiB for that data alone.

Capacity planning must account for concurrent requests, live stream/cache instances, emission rates, retention duration, average and p95/p99 payload sizes, indirectly retained object graphs, and other queue/prefetch layers.

### 14.2. Item Count and Byte Budgets

History=1,000 only limits item count. If items range from 1 KiB to 10 MiB, memory can swing wildly.

Cap payload bytes before caching, cache only small projections, offload large blobs to object storage, keep metadata instead of binary bodies, bound both entry count and TTL, and use an external cache with maximum weight/size if byte-aware eviction is required.

## 15. Cancellation, Errors, and Discard

### 15.1. collectList on Cancel

collectList has discard support: when a subscription is canceled or errors on a data signal, elements in the accumulating List may be discarded. However, cancellation does not make data retention free: the List was still allocated and references must be released from the operator.

### 15.2. DataBuffer and Reference-Counted Objects

When collecting DataBuffer/ByteBuf or reference-counted resources, ensure proper ownership release.

~~~java
Mono<List<DataBuffer>> body = dataBuffers
    .collectList()
    .doOnDiscard(
        DataBuffer.class,
        DataBufferUtils::release
    );
~~~

This is a Spring WebFlux snippet; import DataBuffer, DataBufferUtils, and corresponding APIs.

The doOnDiscard hook applies only to operators with discard support. Once the List has been emitted downstream, the caller assumes ownership and must release per contract; the hook does not replace consumer responsibility for delivered data.

### 15.3. Caches Retaining Resources Longer Than Request Lifetimes

Do not cache DataBuffer, ByteBuf, file handles, connections, or short-lived resources without explicit retain/release rules. A cache holding references past a request's lifetime can prevent resource release or cause use-after-release errors.

Prefer caching immutable DTOs/metadata, or caching keys/locators to fetch resources only when needed.

### 15.4. Errors in Cache

Flux.cache replays error signals. A transient error can be retained and replayed to subsequent subscribers per cache/TTL policy. To retry before caching, design operator ordering and retry counts carefully.

~~~java
Flux<Data> cached =
    remoteSource
        .retryWhen(retryPolicy)
        .cache(500, Duration.ofMinutes(1));
~~~

This illustrative snippet requires retryPolicy. Do not use infinite retries before caching if upstream can fail for prolonged periods or trigger a retry storm.

## 16. Choosing a Cache by Lifecycle and Semantics

- **Small, infrequently changing configuration data:** Mono.cache(Duration) or a keyed cache with explicit TTL can work; account for object size and invalidation.
- **Event streams needing short-term replay:** use cache(history, ttl) or replay(history, ttl) with history sized from event rate and payload size.
- **Sharing a live stream only:** consider share() or publish().refCount() when late subscribers do not need history replay.
- **Durable event history needed:** do not use an in-heap cache instead of Kafka, a database log, or an event store; use retention, offsets, pagination, and cursor-based replay.
- **Keyed caching needed:** consider Caffeine or Spring Cache with maximumSize/maximumWeight, expireAfterWrite/expireAfterAccess, and invalidation policies.

Do not share a single cached publisher across multiple users if the source depends on subscriber security context. The cache could serve data built for the first user and cause cross-tenant/user data leaks.

## 17. Java 17 and Reactor 3.8.8 Example Project

This project demonstrates collectList collecting a finite source entirely, buffer(3) emitting size-bounded batches, cache(2) keeping only the last two items for late subscribers, replay(2) keeping the two most recent items in a ConnectableFlux, and JUnit verifying outputs and upstream subscription counts.

Structure:

~~~text
reactor-memory-retention-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/memory/
    │       └── MemoryRetentionDemo.java
    └── test/
        └── java/com/example/memory/
            └── MemoryRetentionTest.java
~~~

### 17.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>reactor-memory-retention-demo</artifactId>
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
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <version>3.8.8</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.12.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.3</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 17.2. MemoryRetentionDemo.java

~~~java
package com.example.memory;

import java.util.List;

import reactor.core.publisher.ConnectableFlux;
import reactor.core.publisher.Flux;

public class MemoryRetentionDemo {

    public static void main(String[] args) {
        List<Integer> all = Flux.range(1, 10)
            .collectList()
            .block();

        System.out.println("collectList=" + all);

        Flux.range(1, 10)
            .buffer(3)
            .doOnNext(batch ->
                System.out.println("batch=" + batch)
            )
            .blockLast();

        Flux<Integer> cached =
            Flux.range(1, 5).cache(2);

        List<Integer> first = cached
            .collectList()
            .block();

        List<Integer> late = cached
            .collectList()
            .block();

        System.out.println("cache first=" + first);
        System.out.println("cache late=" + late);

        ConnectableFlux<Integer> replay =
            Flux.range(1, 5).replay(2);

        replay.connect();

        List<Integer> replayed = replay
            .collectList()
            .block();

        System.out.println("replay late=" + replayed);
    }
}
~~~

In `main`, block() is used only at the CLI boundary to print results. Do not call block() inside a WebFlux controller, Netty event-loop, or production reactive chain.

### 17.3. MemoryRetentionTest.java

~~~java
package com.example.memory;

import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.ConnectableFlux;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

class MemoryRetentionTest {

    @Test
    void collectListEmitsAllItemsAtCompletion() {
        StepVerifier.create(
                Flux.range(1, 5).collectList()
            )
            .expectNext(List.of(1, 2, 3, 4, 5))
            .verifyComplete();
    }

    @Test
    void bufferEmitsBoundedBatches() {
        StepVerifier.create(
                Flux.range(1, 7).buffer(3)
            )
            .expectNext(
                List.of(1, 2, 3),
                List.of(4, 5, 6),
                List.of(7)
            )
            .verifyComplete();
    }

    @Test
    void cacheHistoryReplaysOnlyLastNItemsToLateSubscriber() {
        AtomicInteger subscriptions = new AtomicInteger();

        Flux<Integer> source = Flux.defer(() -> {
            subscriptions.incrementAndGet();
            return Flux.range(1, 5);
        });

        Flux<Integer> cached = source.cache(2);

        StepVerifier.create(cached)
            .expectNext(1, 2, 3, 4, 5)
            .verifyComplete();

        StepVerifier.create(cached)
            .expectNext(4, 5)
            .verifyComplete();

        assertEquals(1, subscriptions.get());
    }

    @Test
    void replayHistoryRetainsLastNItemsForLateSubscriber() {
        ConnectableFlux<Integer> replay =
            Flux.range(1, 5).replay(2);

        replay.connect();

        StepVerifier.create(replay)
            .expectNext(4, 5)
            .verifyComplete();
    }

    @Test
    void takeBeforeCollectListBoundsCollectedCount() {
        StepVerifier.create(
                Flux.range(1, 1_000_000)
                    .take(4)
                    .collectList()
            )
            .expectNext(List.of(1, 2, 3, 4))
            .verifyComplete();
    }

    @Test
    void reduceCanKeepOnlyScalarState() {
        StepVerifier.create(
                Flux.range(1, 100)
                    .map(Integer::longValue)
                    .reduce(0L, Long::sum)
            )
            .expectNext(5050L)
            .verifyComplete();
    }
}
~~~

### 17.4. Exact Output

Run:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.memory.MemoryRetentionDemo
~~~

Output:

~~~text
collectList=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
batch=[1, 2, 3]
batch=[4, 5, 6]
batch=[7, 8, 9]
batch=[10]
cache first=[1, 2, 3, 4, 5]
cache late=[4, 5]
replay late=[4, 5]
~~~

Run tests:

~~~bash
mvn clean test
~~~

Expected: 6 JUnit tests PASS. The project uses only Reactor Core/Test, without starting Spring Boot.

## 18. Inspecting Memory in Real Applications

### 18.1. JVM Metrics

Track heap used/committed/max, old generation occupancy, allocation rate, GC count/pauses, active requests, live cache/publisher instances, configured history/TTL, and queues/prefetch on operators that can accumulate data.

Use Micrometer/Actuator metrics such as JVM memory and GC metrics. Do not attach high-cardinality user IDs or request IDs to metric tags.

### 18.2. JFR

Java Flight Recorder helps inspect allocation rate, object allocation hot spots, GC, and object lifetimes. Use JFR during load tests to spot operators or services creating excessive collections/DTOs.

### 18.3. Heap Dumps and Dominator Tree

When heap grows continuously:

1. Capture a heap dump under heavy load.
2. Open it in Eclipse MAT or an equivalent tool.
3. Inspect the dominator tree and retained heap.
4. Locate Lists, Maps, cache nodes, or object graphs occupying most of the heap.
5. Trace reference paths back to singleton services, fields, or Reactor publishers.
6. Cross-check with collectList/cache/replay code and subscription lifecycles.

A large List may be only a symptom; the root retainer may be a Mono cache or a service field holding a long-lived publisher.

### 18.4. Load Tests

Design tests with small/large datasets, normal/burst event rates, high request concurrency, mid-stream client cancellations, late subscribers joining cache/replay, expired cache TTLs, source completions/errors, multiple tenants/users/cache instances, and p50/p95/p99 payload sizes.

Measure post-GC heap and retained heap, not just RSS or point-in-time heap used.

## 19. Common Issues and Fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| OOM after calling findAll | collectList holds entire result set | Pagination or streaming |
| Mono<List<T>> never emits | Infinite source has not completed | Bound source or use batching/windowing |
| Heap grows over time | Unbounded Flux.cache()/replay() | cache(history) or replay(history) |
| Using cache(Duration) yet still OOM | TTL has no hard item count cap | cache(history, ttl) |
| Late subscribers receive all old events | Unbounded cache()/replay() history | Set appropriate history |
| Cache fails and all subsequent requests fail | Error signal is replayed | Clear TTL/invalidation and retry policy |
| User A's data appears for User B | Shared cache on user-dependent source | Cache key/tenant isolation or skip caching |
| Mutable DTO changes across subscribers | Cache holds the same object reference | Immutable DTOs or intentional copies |
| collectSortedList consumes heavy heap/CPU | Retains and sorts all data | Sort in database, keyset pagination |
| collectMultimap grows without bound | Every value stored in a collection | Bound keys/windows or process in batches |
| distinct() grows heap | Stores every seen key | Bound deduplication window |
| buffer() causes OOM | One List buffer waits for completion | buffer(maxSize)/bufferTimeout |
| limitRate does not solve memory | It shapes demand, not cache/list bounds | Bound retaining operators |
| flatMap increases memory | Concurrency/prefetch too high | Lower concurrency/prefetch, measure payloads |
| TTL expires yet heap does not drop | Other references still hold objects or GC hasn't run | Heap dump and dominator tree |
| Caching DataBuffer causes leaks | Reference-counted resources held too long | Cache metadata, release per ownership |
| Measuring only live heap misses allocations | GC hides high allocation rate | JFR and allocation profiling |
| replay(refCount) still holds huge history | Connect lifecycle differs from history retention | Bound replay history/TTL |
| Switched to buffer yet queues still grow | Slow downstream and queued batches waiting | Bound concurrency, prefetch, and queues |

## 20. Design Checklist

Before shipping collectList/cache/replay to production:

1. Does the source complete finitely?
2. Is the maximum element count predictable?
3. What is the p95/p99 payload size?
4. Does collectList truly need a complete List?
5. Can reduce/count/any/all replace it?
6. Can buffer(maxSize) or bufferTimeout be used?
7. Can the database be queried via keyset pagination?
8. Does the cache have a bounded history count?
9. Is TTL paired with a hard count limit when event rates are high?
10. Can the cache retain errors/terminal signals for too long?
11. Which bean/request holds the cached publisher?
12. Are objects immutable and safe to replay?
13. Is there user/tenant data requiring cache isolation?
14. Are reference-counted resources present inside items?
15. Are concurrency/prefetch/queues of other operators accounted for?
16. Do cancellation/error paths clean up discarded data?
17. Are JVM metrics, JFR, or heap dumps available when needed?
18. Do load tests cover bursts, concurrent requests, and late subscribers?
19. Are there per-instance/per-tenant memory limits?
20. Is there a fallback plan when caches exceed budget?

## 21. Practice Exercises

**Exercise 1 — collectList:** use Flux.range(1, 10).collectList() and observe that the Mono emits the List only when the source completes.

**Exercise 2 — infinite source:** use Flux.interval().collectList(); explain why it never emits and memory grows over time.

**Exercise 3 — take:** add take(100) before collectList and verify maximum element count.

**Exercise 4 — collectMap:** generate 100,000 items across 1,000 keys; measure entry count and retained objects.

**Exercise 5 — collectMultimap:** compare memory against collectMap when many items share the same key.

**Exercise 6 — unbounded cache:** create Flux.range(...).cache() and subscribe a second time; observe replay.

**Exercise 7 — cache(history):** switch to cache(10) and verify late subscribers receive only the last 10 items.

**Exercise 8 — TTL:** use cache(Duration) and cache(history, Duration), trigger an event burst, and compare retained replay counts.

**Exercise 9 — replay:** use replay(5), connect before subscribers join, and verify history.

**Exercise 10 — share:** replace replay with share and verify late subscribers do not receive full history.

**Exercise 11 — batch:** use buffer(500) and bufferTimeout(500, Duration.ofSeconds(1)); measure batch sizes and latency.

**Exercise 12 — reduce:** replace collectList with reduce to compute a sum; compare memory usage.

**Exercise 13 — concurrency:** run multiple concurrent collectList requests over a large dataset and measure heap.

**Exercise 14 — object graph:** cache a DTO holding a large List and use a heap dump to inspect retained heap.

**Exercise 15 — cancellation:** cancel a subscription while collectList is collecting and verify discard cleanup on an appropriate resource.

**Exercise 16 — DataBuffer:** add doOnDiscard and verify release of discarded buffers on cancel/error.

**Exercise 17 — keyset pagination:** load 10,000 records in pages of 500 and process each page without collecting all of them.

**Exercise 18 — observability:** enable JFR, locate allocation hotspots, and inspect the dominator tree of caches/lists under load test.

## 22. Key Takeaways

**collectList() retains all elements until the source completes.** On infinite sources, it may never emit and will keep growing memory. collectMap, collectMultimap, collectSortedList, distinct, and buffer() can also retain data proportional to seen elements/keys.

**Unbounded Flux.cache() and replay() can retain the entire signal history.** cache(history) and replay(history) bound element count. cache(ttl) and replay(ttl) provide per-item expiry without a hard count cap. When both are needed, use cache(history, ttl) or replay(history, ttl).

Backpressure regulates demand; it does not automatically discard data that an operator deliberately retains. Use streaming, reduce, pagination, size-bounded buffers, bounded concurrency/prefetch, and bounded caches. Size by **item count × object graph size × concurrent requests/caches**, then verify with JFR and heap dumps.

## 23. References

- Project Reactor Core 3.8 Reference — Which operator do I need?: https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html
- Reactor Core 3.8.8 API — Flux.collectList: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Reactor Core 3.8.8 API — Flux.cache(history, ttl): https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Reactor Core 3.8.8 API — Flux.replay(history, ttl): https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Reactor Core Reference — Multicasting a Flux to several Subscribers: https://projectreactor.io/docs/core/release/reference/advancedFeatures/advanced-broadcast-multiple-subscribers-connectableflux.html
- Reactor Core Reference — Backpressure: https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html
- Reactor Core Reference — Cleanup and Discard Support: https://projectreactor.io/docs/core/release/reference/advancedFeatures/cleanup.html
- Spring Framework Reference — Reactive Data Access: https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html
- Spring Framework Reference — WebFlux Reactive Types: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html
- Java Flight Recorder — Oracle Documentation: https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder.html
- Eclipse Memory Analyzer (MAT): https://eclipse.dev/mat/
