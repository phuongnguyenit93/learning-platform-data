# Flux: Collecting All Results into a List Before Storing in Spring Cache

> **Topic:** Spring Framework – Cache · **Group:** Asynchronous.  
> **Goal:** understand accurately why a method declared to return `reactor.core.publisher.Flux<T>` can be stored by Spring Cache as **a list of emitted elements** instead of caching items one by one; grasp the mechanism since Spring Framework 6.1+, asynchronous cache backend requirements, consequences for streaming/backpressure/memory, as well as how to test and choose an appropriate design.

## 1. Difference Between the `Flux<T>` Return Type and the Actually Cached Data

`Flux<T>` is a `Publisher` that can emit **0 to N elements**, then complete (`onComplete`), or terminate with an error (`onError`). It is not equivalent to a pre-computed `List<T>`. A typical cold `Flux` only runs the source work when a subscriber subscribes.

Example of a reactive service:

```java
@Cacheable(cacheNames = "searchResults", key = "#p0")
public Flux<String> search(String query) {
    return repository.findMatchingNames(query);
}
```

This is a **snippet inside a Spring-managed service** with an appropriate reactive repository, not a standalone file.

Since **Spring Framework 6.1**, the caching annotation mechanism supports adapting asynchronous return types, including `CompletableFuture`, Reactor `Mono`, and `Flux`, provided the corresponding async storage path is supported by the cache provider.

For `Flux<T>`, a cache operation does not retain an arbitrary `Flux` for later subscribers to re-subscribe to. Instead, Spring **collects all values emitted by the `Flux` into a `List<T>`**, waits for the source to complete, and then caches that collected result. On a cache hit, the values in the list are replayed to the subscriber as a `Flux<T>`.

Logical diagram:

```text
Client calls search("java")
  │
  ▼
Spring @Cacheable, key="java"
  │
  ├── Hit: get cached list
  │           ["JDK", "Spring", "Reactor"]
  │               │
  │               └── adapt into Flux replaying elements one by one
  │
  └── Miss: call source publisher
                │
                ├── onNext("JDK")
                ├── onNext("Spring")
                ├── onNext("Reactor")
                └── onComplete()
                        │
                        ▼
                collectList() per equivalent semantics
                        │
                        ▼
                List ["JDK", "Spring", "Reactor"]
                        │
                        ▼
                cache under ONE key "java"
                        │
                        ▼
                replay as Flux to caller
```

**Key point:** each cache key corresponds to **one complete result set** (a logical snapshot of one subscription), not one key per `onNext` element. When the method is called with a different query, Spring generates a different key if the `key`/`KeyGenerator` expression distinguishes that query.

### 1.1. Why Must It Wait for Completion?

With a finite result set, if a partial list were cached right when the first element arrived, a later subscriber could see a half-finished result without knowing how many elements were missing. Collecting up to `onComplete` makes it possible to cache a consistent result as a **list fully emitted by the source**.

In return, collecting into a list requires **buffering elements in memory** and can delay emitting results to the caller when going through the cache layer. This is a major trade-off for APIs designed to stream data element by element as soon as it is available.

### 1.2. Comparing `Mono<T>`, `Flux<T>`, and `List<T>`

| Method Return Type | What Is Cached Under the Adaptation Mechanism | Points to Note |
|---|---|---|
| Synchronous `T` | The value `T` | Usually handled in a synchronous call |
| `CompletableFuture<T>` | The future value completed asynchronously | Backend needs async retrieval support |
| `Mono<T>` | At most one value when the `Mono` completes | Does not cache the publisher like an ordinary immutable object |
| `Flux<T>` | **List of values** from the completed `Flux` | Collects the entire result, with size and streaming risks |
| Synchronous `List<T>` | A `List<T>` object returned by the method | The method itself already paid the cost of building the list |

For `Flux` and `Mono`, adaptation depends on Spring Framework 6.1+ cache annotation infrastructure and the configured backend; **do not assume this feature exists in Spring Framework 5.x or every custom `Cache` implementation**.

## 2. Mechanism on Cache Miss: From Publisher to List

A `Flux` may simply be a description of work not yet running. To cache **the result**, the cache layer must observe publisher completion and collect the elements.

Example source with three elements:

```java
Flux<String> names = Flux.just("Ada", "Bob", "Chi");
```

In Reactor terms, collecting into a list looks like:

```java
Mono<List<String>> allNames = names.collectList();
```

This snippet is a **Reactor conceptual illustration**, not the exact line-by-line internal code of Spring Cache. `collectList()` waits for `onComplete` before emitting a `List` containing all elements. Spring Cache uses an equivalent adaptation strategy to retain values emitted by `Flux` before caching.

In Spring 6.1+:

1. The cache interceptor resolves the cache name and key from the method/arguments.
2. On a cache hit, the completed data is fetched from the cache via the async-supported path and **turned back into a `Flux` emitting the elements**.
3. On a cache miss, the publisher supplied by the target method is subscribed to within the adaptation pipeline.
4. `onNext` signals are gathered into a list; `onComplete` is the condition for producing a **successful list result**.
5. The list is placed into the cache as the logical value for the key.
6. The subscriber receives the elements from the list once the asynchronous work completes.

**Do not say that Spring creates a new cache entry for each `onNext`.** The scope of a cache operation is **the result of the entire method invocation** associated with one key.

### 2.1. A Two-Element `Flux` Is Still One Cached Result

```java
@Cacheable(cacheNames = "codes", key = "#p0")
public Flux<String> codes(String locale) {
    return Flux.just(locale + "-A", locale + "-B");
}
```

If `locale="vi"`, the logical cached result is the two-item list `["vi-A","vi-B"]` under key `"vi"`. The next call with the same locale can receive both items from the cache without re-executing the source.

### 2.2. The Cache Key Belongs to the Invocation, Not Each Item

```java
@Cacheable(
    cacheNames = "ordersByCustomer",
    key = "#p0 + ':' + #p1"
)
public Flux<Order> orders(String tenantId, String customerId) {
    return repository.findByTenantAndCustomer(tenantId, customerId);
}
```

This is an illustrative snippet requiring `Order` and a repository. The key distinguishes tenant + customer; the **entire list of the customer's orders** is stored under one key. If `tenantId` were omitted from the key when results differ per tenant, caching the whole list could return one tenant's sensitive data to another tenant.

If the method depends on locale, access permissions, filters, page, sort, version, or feature flags, the components that alter the result must appear in the cache key or an appropriate namespace.

## 3. Major Consequence: No Longer Streaming Element-by-Element to Users as Before

Distinguish between **an API returning `Flux`** and **the actual path of the data**.

Without a result-collecting cache layer, a WebFlux endpoint can receive and emit each record as soon as the repository produces it. When `@Cacheable` adapts `Flux` by collecting into a list:

- The cache layer must wait for the entire upstream to complete to obtain the list.
- The cache value cannot be considered complete and successful when the source has only emitted a few elements.
- Data must be buffered in memory before becoming a cacheable set.
- Results can be replayed from the list; end-to-end semantics are no longer "receive the first record from upstream and forward it immediately to the client".

Scenario:

```text
Source emits:
t=0.1s: item 1
t=0.2s: item 2
t=0.3s: item 3
t=4.0s: item 4 + onComplete

If going through list-collecting caching:
    Must wait for source to complete to get list [1,2,3,4].
    Cannot assume item 1 already reached the client at t=0.1s.
```

The timestamps above are **illustrative examples**, not benchmarks of Reactor or any specific provider. The accurate point about the mechanism is that **requiring full list materialization** strips the result of upstream streaming's immediate item-by-item pass-through behavior.

### 3.1. Backpressure Changes Meaning

Reactive Streams has the `request(n)` mechanism: downstream can request a number of elements matching its processing capacity. However, `collectList` needs to consume **the entire upstream** to complete the list. Therefore, downstream consuming slowly item by item after a cache hit **is not equivalent** to reducing upstream data reading on a cache miss.

Do not put `@Cacheable` on a very large `Flux` merely because the method returns a Reactive type. Collecting many values can consume significant heap even when downstream only needs the first few items.

### 3.2. Interaction with Timeouts and Client Connections

Suppose a request only wants the first 10 records out of 1,000,000 records, yet the cacheable method returns the entire `Flux`. If the cache adapter tries to collect everything, it can cause long wait times and store an unnecessary list. `take(10)` on the subscriber side **after** the cache layer is not a reliable way to bound upstream work, because the cache's upstream already had to be drained completely.

Bound results at **the query or source before the cache layer collects**, such as SQL pagination, record limits, or accepting a validated `limit` parameter on the method.

### 3.3. Several Stream Types Are Unsuitable

| Flux Type | Is Caching the Entire List Suitable? | Why |
|---|---|---|
| Finite, small `Flux.just(a,b,c)` | Usually suitable | Small data, has `onComplete` |
| Paginated query result of 20 records | Usually suitable | Clear budget, one key per page |
| `Flux.empty()` | Can be represented by an empty list | Must check provider's empty/null policy |
| `Flux.error(...)` | No successfully completed list | Errors should not be treated as cached successful data |
| `Flux.never()` | Not suitable | No `onComplete` to finish the list |
| Infinite `Flux.interval(...)` | Not suitable | Never terminates; risk of long-lived retention/buffering |
| SSE/WebSocket live stream | Not suitable | Continuous live stream, not a finite snapshot |
| Exporting millions of records | Usually not suitable | Loses streaming benefits, OOM and latency risk |
| Fixed 50-row search page | More suitable | Size, key, and TTL are controllable |

## 4. Why Is a Cache Backend Capable of Asynchronous Retrieval Required?

Supporting `Flux` is not merely Spring recognizing the return type. The cache mechanism must be able to integrate with **a value that completes in the future**.

The Spring Cache API includes asynchronous operations, notably:

```java
CompletableFuture<?> retrieve(Object key);

<T> CompletableFuture<T> retrieve(
    Object key, Supplier<CompletableFuture<T>> valueLoader);
```

These are **illustrative signatures** of the `org.springframework.cache.Cache` interface. Provider support varies; `Cache.retrieve` is designed for non-blocking retrieval paths when data or computation is still pending.

For `Flux<T>`, the cache operation attaches to a logical value of type **asynchronously produced `List<T>`**. One can typically picture:

```text
Flux<T> source
   -> collect all
   -> CompletableFuture<List<T>> completes
   -> async cache storage
   -> cache hit: List<T>
   -> Flux replays T from List
```

Do not use this diagram to assert that every internal Spring implementation has the exact same class/future; this is the **correct mental model for list-based result caching and async retrieval**.

### 4.1. `ConcurrentMapCacheManager` and `CaffeineCacheManager`

Spring Framework supports async-cache-compatible paths in standard implementations, for example:

- `ConcurrentMapCache` has async retrieval methods suitable for common cases.
- `CaffeineCacheManager` has **async cache mode** since Spring Framework 6.1; enabled via `setAsyncCacheMode(true)` to use Caffeine's `AsyncCache`.

When using a custom `CacheManager` or an external provider, do not assume `retrieve` is supported just because `get`/`put` exist. Read the Javadoc, adapter implementation, and write integration tests with real `Flux<T>` return types.

### 4.2. What Is Caffeine Async Mode?

Java configuration example:

```java
@Bean
public CacheManager cacheManager() {
    CaffeineCacheManager manager =
            new CaffeineCacheManager("resultPages");
    manager.setAsyncCacheMode(true);
    manager.setCaffeine(Caffeine.newBuilder()
            .maximumSize(500)
            .expireAfterWrite(Duration.ofMinutes(5)));
    return manager;
}
```

This snippet belongs inside a Spring `@Configuration` class, requiring appropriate imports and the Caffeine dependency; a complete source example is in Section 7.

`setAsyncCacheMode(true)` tells the manager to use native Caffeine asynchronous caches to properly support future/reactive results. It **does not turn an infinite `Flux` into a finite one**, does not automatically cap items in a list, and does not enforce a total item quota across all lists.

### 4.3. Two Different Capacity Limits

`maximumSize(500)` on Caffeine means **at most roughly 500 cache entries/keys**, not 500 total elements across all cached `List<T>` instances.

For example, a cache holding 500 keys where each key holds a list of 10,000 records:

```text
500 keys × 10,000 elements / list
   = 5,000,000 referenced elements
```

This is an element-count estimate, not heap bytes. You must budget for the object graph, overhead, keys, and intermediate copies. To better bound total capacity, consider a weighted Caffeine cache with `maximumWeight` + `weigher` if snapshot size can be weighed reliably, or bound items/pages/responses directly at the data layer.

## 5. Business Examples: Which `Flux` Results Should Be Cached?

### 5.1. Finite Search Result Page

```java
@Cacheable(
    cacheNames = "productPages",
    key = "#tenantId + ':' + #page + ':' + #size"
)
public Flux<Product> findPage(
        String tenantId, int page, int size) {
    int safeSize = Math.min(size, 50);
    return repository.findPage(tenantId, page, safeSize);
}
```

This is a snippet in a service with `Product`/repository, not a runnable file. In production, validate `size >= 1` and clamp **before** computing the key, or make the key reflect `safeSize` to avoid redundant keys. Normalize sort/filters, and include access permissions and tenant whenever they affect the result.

With a page capped at 50 items and a short TTL, collecting the list is relatively easy to control.

### 5.2. Event History Over a Time Window

```java
@Cacheable(
    cacheNames = "recentEvents",
    key = "#customerId + ':' + #from + ':' + #to"
)
public Flux<EventDto> events(
        String customerId, Instant from, Instant to) {
    return repository.findEvents(customerId, from, to);
}
```

This snippet should only be used if the time window is bounded and the maximum record count is reasonable. If a client can pass a 30-year range, the list can be huge. Bound the range, item count, and pagination at the database; do not rely solely on `timeout` hoping to keep memory within bounds.

### 5.3. Financial Data or Access Permissions

For data requiring very high freshness (account permissions, balances...), caching an entire `Flux` can be dangerous when the same key is reused after updates, especially with long TTLs or missing invalidation. List-snapshot caching does not guarantee consistency automatically; proper version/tenant/permission scoping and post-commit invalidation paths are required when the business demands it.

### 5.4. When `Mono<List<T>>` Expresses the Domain Better

If an endpoint inherently always returns a bounded **finite result set**, explicitly declaring `Mono<List<T>>` can help code authors recognize this as an aggregate rather than an unbounded stream:

```java
@Cacheable(cacheNames = "productPages", key = "#p0")
public Mono<List<Product>> findSnapshot(String pageKey) {
    return repository.findPage(pageKey).collectList();
}
```

This is an illustrative snippet, not a standalone file. Spring still needs a provider compatible with reactive caching. Choosing `Mono<List<T>>` does not make the result smaller by itself; you must still **bound the source data**. However, the API semantics are clearer to consumers: a snapshot handled as a single unit.

## 6. Completion, Errors, Cancellation, and Empty Caching

### 6.1. `onComplete` Marks a Successful Result

A finite `Flux` emitting `A`, `B`, `C` and then `onComplete` has a complete cacheable result of `[A,B,C]`. On a cache hit, these elements are replayed in their original order to the subscriber.

If a `Flux` completes with **0 elements**, the collected result is semantically an empty list. With a cache backend supporting reactive result caching, an empty list can be stored as a valid completed value. Do not confuse this with a method returning `null` or the cache not finding the key.

### 6.2. `onError` Does Not Produce a Successful List

```java
Flux<String> broken = Flux.concat(
        Flux.just("A", "B"),
        Flux.error(new IllegalStateException("upstream failed")));
```

This is a Reactor example. The stream emits A, B and then errors, without emitting `onComplete`. `[A,B]` must not be treated as a complete successful snapshot to cache under the collect-then-store mechanism. Subsequent retries may re-subscribe to the source and trigger side effects/costs; retries, idempotency, and error handling must be designed separately.

**Do not assert that every kind of error is stored by Spring Cache like a normal item.** If the business wants negative caching or a cached failure policy, explicitly design a data type representing the error state and conditions to cache only safe results.

### 6.3. `Flux.never()` and Infinite Streams

```java
Flux<Long> numbers = Flux.interval(Duration.ofMillis(100));
```

This creates a stream **with no termination point**. If `@Cacheable` is applied and the cache layer collects the whole `Flux` to build a `List`, there will never be an `onComplete` to finalize the list. The buffer can grow until canceled, out of resources, or errored.

If you genuinely need a finite snapshot, **slice directly inside the cached method**:

```java
@Cacheable(cacheNames = "sample", key = "#p0")
public Flux<Long> sample(String group) {
    return Flux.interval(Duration.ofMillis(100)).take(10);
}
```

This is an illustrative snippet; `take(10)` makes the `Flux` terminate after 10 items. With real data, it is better to limit the query/loader at the source and set timeouts with cleanup mechanisms, rather than fetching infinitely and only slicing in a downstream controller.

### 6.4. Client Cancellation and Source Resources

In reactive systems, clients can cancel subscriptions. The materialize/caching behavior makes no guarantee that values were fully cached when only part of the result was emitted or when the publisher is canceled. Subscription sharing/cancellation behavior can depend on the adapter/provider path.

**Do not rely on a cache hit for an incomplete `Flux`.** Verify firmly that the cache only holds complete snapshots, especially when using a custom `Cache` implementation or complex retry/resubscribe logic.

### 6.5. `null` Is Not an Element of a `Flux`

Reactive Streams forbids `onNext(null)`. `Flux.just(null)` fails; there is no "list containing null" via normal element emission. This differs from synchronous data caching, which may have a null policy or sentinel. If business data has optional items, represent them with an explicit domain type instead of emitting null.

## 7. Runnable Java 17+ Demo: Caching a Finite `Flux` with Async Caffeine

Standalone example using **Java 17+**, **Maven**, **Spring Framework 6.2.12**, **Reactor Core 3.7.12**, and **Caffeine 3.2.2**. No Spring Boot, Redis, or database needed.

The goal is to prove, under **sequential, fully completed calls**:

1. First call with key `P42`: method emits three elements; source is actually subscribed to once.
2. Second call with the same key `P42`: result is served from cache, still emitting all three elements, without re-subscribing to the source.
3. Different key `P99`: creates an independent snapshot and subscribes to the source a second time.
4. Explicit eviction of `P42`; the next call must obtain a fresh snapshot.
5. Data is cached as **an aggregate result per key**, not one key per item.

### 7.1. Structure

```text
spring-reactive-flux-cache/
├── pom.xml
└── src/main/java/dev/example/fluxcache/FluxCacheDemo.java
```

### 7.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.example</groupId>
    <artifactId>spring-reactive-flux-cache</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context-support</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.7.12</version>
        </dependency>
        <dependency>
            <groupId>com.github.ben-manes.caffeine</groupId>
            <artifactId>caffeine</artifactId>
            <version>3.2.2</version>
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
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>dev.example.fluxcache.FluxCacheDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context-support` provides `CaffeineCacheManager` and pulls in the corresponding Spring Context/Cache core. `reactor-core` provides `Flux`. In a Boot project, use Boot's compatible dependency management/BOM rather than arbitrarily pinning individual versions.

### 7.3. Complete Java Source

**`src/main/java/dev/example/fluxcache/FluxCacheDemo.java`**

```java
package dev.example.fluxcache;

import java.time.Duration;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.publisher.Flux;

public class FluxCacheDemo {

    private static List<String> await(Flux<String> values) {
        return Objects.requireNonNull(
                values.collectList().block(Duration.ofSeconds(5)));
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            FeedService service = context.getBean(FeedService.class);
            CacheManager manager = context.getBean(CacheManager.class);
            Cache cache = Objects.requireNonNull(manager.getCache("feeds"));

            System.out.println("first=" + await(service.find("P42")));
            System.out.println("second=" + await(service.find("P42")));
            System.out.println("loadsAfterHit=" + service.loadCount());

            System.out.println("another=" + await(service.find("P99")));
            System.out.println("loadsAfterNewKey=" + service.loadCount());

            // Equivalent to invalidating one snapshot, without deleting other keys.
            cache.evictIfPresent("P42");
            System.out.println("afterEvict=" + await(service.find("P42")));
            System.out.println("loadsAfterEvict=" + service.loadCount());
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class AppConfig {

        @Bean
        public CacheManager cacheManager() {
            CaffeineCacheManager manager =
                    new CaffeineCacheManager("feeds");

            // Use async cache path for reactive results.
            manager.setAsyncCacheMode(true);
            manager.setCaffeine(Caffeine.newBuilder()
                    .maximumSize(100));

            return manager;
        }

        @Bean
        public FeedService feedService() {
            return new FeedService();
        }
    }

    public static class FeedService {
        private final AtomicInteger sourceSubscriptions =
                new AtomicInteger();

        @Cacheable(cacheNames = "feeds", key = "#p0")
        public Flux<String> find(String id) {
            return Flux.defer(() -> {
                // Increment only when actually subscribing to the source.
                int load = sourceSubscriptions.incrementAndGet();

                return Flux.just(
                        id + "-A-" + load,
                        id + "-B-" + load,
                        id + "-C-" + load
                );
            });
        }

        public int loadCount() {
            return sourceSubscriptions.get();
        }
    }
}
```

Run command in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

**Expected stdout from the application's `System.out.println` calls** on a fresh context/cache (excluding secondary Maven or SLF4J logs):

```text
first=[P42-A-1, P42-B-1, P42-C-1]
second=[P42-A-1, P42-B-1, P42-C-1]
loadsAfterHit=1
another=[P99-A-2, P99-B-2, P99-C-2]
loadsAfterNewKey=2
afterEvict=[P42-A-3, P42-B-3, P42-C-3]
loadsAfterEvict=3
```

This is a program illustrating **sequential calls** where the cache has completed the snapshot before the next call, not a concurrent stress test or cross-node proof. With other providers, async cache requirements must be verified separately.

### 7.4. Output Analysis

- `first`: key `P42` has no snapshot yet, so the `Flux.defer` source is subscribed to for the first time and emits A/B/C tagged with `1`. The cache layer stores the completed result corresponding to a three-item list.
- `second`: the same key is served from the cached snapshot, so the output number does not increment to `2`; `loadsAfterHit=1` confirms the source was not subscribed to again.
- `another`: key `P99` differs from `P42`, triggering a new data fetch and bringing the load count to `2`.
- `cache.evictIfPresent("P42")`: requests eviction of entry `P42`. Does not delete `P99`.
- `afterEvict`: `P42` misses again, the source emits A/B/C with load number `3`, and a new snapshot is created.

**Why count subscriptions instead of counting method entries?** In Reactive Java, a method may only construct a cold publisher (`Flux.defer`) while the real work runs when subscription happens. Counting inside `defer` reflects how many times the real source work was triggered. For other publishers, subscription and method invocation may not coincide.

### 7.5. Why Does the Example Use `block`?

`block(Duration)` is used only in **the demo main function / tests** to wait for completion and print deterministic stdout. **Do not copy `block()` into a production WebFlux event-loop request handler**: blocking a reactive thread degrades throughput or throws errors in non-blocking contexts.

In a real WebFlux controller, return `Flux`/`Mono` so the runtime manages subscriptions, and use `StepVerifier` or integration tests to verify behavior.

### 7.6. Why Does the Cache Use `setAsyncCacheMode(true)`?

Spring Framework supports reactive caching starting in 6.1 and needs a backend compatible with asynchronous caching. Caffeine async mode is the explicit configuration for this scenario. Do not just create a synchronous native Caffeine cache and assume every reactive caching path will reuse futures/lists properly.

### 7.7. Why Must the Method Be on a Spring Bean?

`@Cacheable` in proxy mode requires calls to go through a Spring-managed bean. In the demo, `context.getBean(FeedService.class)` retrieves the intercepted bean. If code instantiates `new FeedService()` outside the container or uses self-invocation like `this.find("P42")` within the same instance, the annotation can be bypassed, changing the demo outcome.

## 8. Common Design Mistakes When Caching a `Flux` as a List

### 8.1. Caching an Infinite Stream

Wrong:

```java
@Cacheable(cacheNames = "notifications", key = "#p0")
public Flux<Notification> liveNotifications(String userId) {
    return notificationBroker.liveStream(userId);
}
```

This is an **anti-pattern snippet**. Live streams typically never emit `onComplete`; collecting the entire `Flux` can never finish a list. You need true streaming, a bounded replay buffer, or another state/snapshot layer; **do not use full-result caching to hold a live stream**.

### 8.2. Caching Exports of Millions of Records

Architecturally wrong if the goal is streaming without loading all data into RAM:

```java
@Cacheable(cacheNames = "exports", key = "#p0")
public Flux<RowDto> exportAll(String reportId) {
    return repository.streamAllRows(reportId);
}
```

The cache layer will attempt to collect a huge list before caching. Replace it with direct streaming export, bounded pagination, chunked object storage, or a file-generation job. If you want to cache metadata of the exported file, cache **a small object describing the result**, not necessarily all row objects.

### 8.3. Failing to Distinguish Query/Page in the Cache Key

`@Cacheable(cacheNames="search", key="#query")` is wrong if the method also has `page`, `size`, and `sort` while the key relies only on `query`. Two calls with the same query and different pages can both receive **the previous page's list**.

Solution: the key must include every parameter that changes the list as well as user scope. For permission-dependent data, avoid caching by query alone while ignoring tenant/principal.

### 8.4. Caching Mutable Objects

The cached list or the items inside it may be mutable objects. When a subscriber mutates an object, subsequent subscribers may observe the mutated state depending on provider/object-reference semantics. Prefer immutable DTOs and explicit mapping before caching; do not treat Spring Cache as a deep-copy mechanism.

### 8.5. Missing TTL or Size Limits

If millions of queries have different keys, even 50 items per `Flux` can make the total cache huge. Configure `maximumSize`/`maximumWeight`/TTL on the provider appropriately; also cap the maximum number of items for **a single key**. A quota of 100 cache keys is not a quota of 100 items.

### 8.6. Assuming the Cache Automatically Handles Errors/Timeouts

When the source fails, error paths, cancellation, retry policies, and fallbacks must be handled explicitly. If `retryWhen` is used on the source `Flux`, elements already collected before the error may be re-evaluated differently; determine whether retries could duplicate/repeat items. Do not cache incomplete results as official snapshots.

## 9. Distinguishing Spring Cache `Flux` from Reactor `Flux.cache()`

Both APIs contain the word "cache", yet their purposes differ.

### 9.1. Spring `@Cacheable`: Caching by Business Key

```java
@Cacheable(cacheNames = "products", key = "#p0")
public Flux<Product> findProducts(String category) {
    return repository.findByCategory(category);
}
```

- Key is generated from method arguments.
- Cache backend is selected via `CacheManager`/`CacheResolver`.
- With a suitable adapter, a completed `Flux` is collected into a list and stored as the result for the key.
- TTL and capacity belong to the backend.
- Reusable across multiple method calls with the same key while the cache retains the entry.

### 9.2. Reactor `Flux.cache()`: Replaying Signals Within One Publisher

```java
Flux<String> shared = expensiveSource.cache();
```

- The `cache()` operator stores/replays emitted signals (values and terminal signal) of **that specific publisher instance**.
- Does not automatically build cache keys from method arguments across the entire `ApplicationContext`.
- Has overloads to bound replay history and/or signal TTL, such as `cache(int history, Duration ttl)`; choose appropriate size and duration.
- On a long-lived `Flux`, an unbounded cache can consume large amounts of memory.
- Suitable when sharing an already-created source and replaying to multiple subscribers referencing that same publisher, not as a replacement for a distributed cache or business-key caching.

Bounded replay example:

```java
Flux<String> source =
        Flux.just("A", "B", "C")
            .cache(3, Duration.ofMinutes(1));
```

This is a Reactor snippet independent of Spring Cache. It keeps a history of at most 3 elements scoped to this publisher with a TTL per the operator's semantics, which is not the same as storing a `List` in a `CacheManager`.

### 9.3. When to Use Which?

| Need | Suitable Choice |
|---|---|
| Cache an entire result page by filter/page with TTL | `@Cacheable` on a finite result with a suitable async provider |
| Replay signals of the same publisher to multiple subscribers | Reactor `Flux.cache(...)` or a share/replay strategy |
| Unbounded WebSocket/SSE live stream | Reactive streaming with bounded replay/backpressure policy |
| Extremely large data export | Stream directly or chunked export, without materializing a large `List` |
| Cache a completed report file | Cache metadata or object storage path |
| Need a shared cache across multiple nodes | Distributed provider and clear protocol/versioning |
| Data extremely sensitive to freshness | Control invalidation/versioning and be cautious with snapshot caching |

**Do not rely merely on the operator name.** Spring `@Cacheable` addresses **business keys / backends**, while Reactor `cache()` addresses **replaying publisher signals** at the reactive pipeline layer.

## 10. Does `@Cacheable(sync=true)` Solve All Concurrent `Flux` Requests?

`sync=true` asks the cache provider to coordinate loads for the same key on a miss to reduce duplicate computation. In a system supporting async retrieval, it can be used within Spring's limitations:

```java
@Cacheable(cacheNames = "productPages", key = "#p0", sync = true)
public Flux<Product> page(String pageKey) {
    return repository.findPage(pageKey);
}
```

This is a snippet requiring a real repository/domain. Spring `@Cacheable(sync=true)` has limitations documented in the Javadoc:

- Does not support the `unless` attribute to veto results after loading.
- Only **one Cache** may be used for the operation.
- Cannot be combined with other cache operations on the same method.

**Do not assume `sync=true` always creates a distributed lock across multiple JVMs.** If each pod keeps a separate local Caffeine cache, each pod can still run a load for the same key. If the cache backend does not support atomic async retrieval as expected, test it in practice.

With `Flux` caching, even if only one loader runs per key, requests awaiting the result **still must wait for the source to emit everything and complete the list**. Thus `sync=true` can reduce DB QPS, but does not by itself improve time-to-first-item.

## 11. Combining with `@CacheEvict`, Data Updates, and Transactions

### 11.1. List Snapshots Can Become Stale

Suppose the cache holds customer `C42`'s order list. A new order is created in the database, yet the old list remains in the cache. There is no automatic mechanism to append the 11th item to the list just because the DB changed. You need TTL, key-based eviction, or versioning.

Example:

```java
@Cacheable(
    cacheNames = "ordersByCustomer",
    key = "#p0"
)
public Flux<OrderDto> findOrders(String customerId) {
    return repository.findByCustomerId(customerId);
}

@CacheEvict(
    cacheNames = "ordersByCustomer",
    key = "#p0"
)
public Mono<Void> refreshOrders(String customerId) {
    return repository.recompute(customerId);
}
```

This is an **illustrative snippet**, not a guarantee that `@CacheEvict` will wait for an entire `Mono<Void>` to complete in every processing path: verify your Spring/cache annotation adapter version and the semantics of the actual reactive method. For reactive DB updates, invalidation is best tied to **a successful transaction commit signal** and tested end-to-end.

### 11.2. Eviction Timing Does Not Automatically Sync with the DB

If an entry is evicted before transaction commit, another reader can miss and reload **the old list**, leaving the cache holding a stale snapshot even after the transaction commits. This mirrors issues in synchronous data caching, except here loading the snapshot can span until the `Flux` completes.

Approaches depending on requirements:

- Evict the cache **after a successful commit**, or publish invalidation events from an outbox.
- Use keys with a version/generation to prevent a late loader from writing an old snapshot under a new key.
- Verify the exact cache key/namespace per tenant/customer/filter.
- Set a reasonably short TTL if data changes continuously.
- Test 2 concurrent read/write requests hitting the same key against the real data source.

### 11.3. Synchronous Transaction Managers Differ from Reactive Transaction Managers

In Reactor/R2DBC applications, the transaction context is usually bound to the **Reactor context**, not solely `ThreadLocal` like traditional JDBC transactions. Do not assume `TransactionAwareCacheManagerProxy` will automatically defer every cache put until a reactive R2DBC transaction completes. Check the transaction manager, cache adapter, and appropriate event/transaction synchronization for the reactive stack, then test commit/rollback.

## 12. Key Design and Result Bounding for a Cacheable `Flux`

A common problem is a search page with multiple parameters:

```java
public record SearchKey(
        String tenantId,
        String query,
        int page,
        int size,
        String sort
) { }
```

A method can use this immutable object itself as the key:

```java
@Cacheable(cacheNames = "searchPages", key = "#p0")
public Flux<ProductDto> search(SearchKey criteria) {
    return repository.findPage(
            criteria.tenantId(),
            criteria.query(),
            criteria.page(),
            Math.min(criteria.size(), 50),
            criteria.sort());
}
```

Both snippets here require a real `ProductDto`/repository. A record in Java 17 provides value-based `equals/hashCode` over its components, suitable for local cache keys when data is immutable. With Redis/shared caches, inspect serializer/key conversion; do not assume record objects encode identically across deployments.

**Mandatory validation:**

- `tenantId` is non-null/non-blank and comes from a trusted authentication context.
- `page >= 0`, `1 <= size <= 50` after normalization.
- `sort` belongs to a whitelist; never inject raw SQL.
- Query is normalized per business rules.
- Cache key uses **canonicalized values**; do not cache `size=9999` under a separate key even though the method clamps to 50.
- Source data returned is genuinely bounded, e.g. SQL `LIMIT 50`, rather than fetching millions of records and expensively calling `take(50)` afterward.
- When query filters are user-scoped, keys/namespaces must never mix results across different permission levels.

### 12.1. Lists Do Not Need Serialization in a Local Cache

Local Caffeine typically holds references to objects/lists in the JVM, whereas Redis needs a serialized representation. This difference affects memory, network, schema evolution, and mutable object risks. When caching DTO lists via Redis, you need:

- Clear serializer, DTO or schema versioning.
- Reasonable TTL/expiration.
- Total byte limit per entry, not just key count.
- Strategy when a cached list exceeds network/storage limits.
- Ability to invalidate when a deployment changes the representation.

## 13. Monitoring: Measure Both Cache Hits and List Materialization Cost

A completed-`Flux` cache can increase hit rate while making miss latency very high. Monitor:

| Group | Metric / Observation | Reason |
|---|---|---|
| Cache | Hit/miss ratio, evictions, cache key count | Assess backend effectiveness and key cardinality |
| Flux source | Source subscription count per key/key group | Confirm cache hits avoid upstream reads |
| Materialization | Items per list, serialized size, max payload bytes | Prevent oversized lists |
| Latency | Time to first item, time to completion, P95/P99 | Detect loss of streaming due to collection |
| Memory | Heap used, allocation rate, GC pauses, OOM | Measure cost of retaining lists and buffers |
| Downstream | DB QPS, R2DBC connections, API fanout | Verify real source load reduction |
| Cancellation | Canceled subscriptions, timeouts, errors | Detect lists that never complete |
| Consistency | Cache age, invalidation lag, stale hits | Detect stale snapshots after updates |
| Distributed | Loader counts across pods, Redis latency | Distinguish local async cache from cluster-wide coordination |

### 13.1. Do Not Measure Only Method Invocation Count

`Flux.defer` or a reactive repository may perform I/O only upon subscription. A counter at the **start of the method** may increment because the method created a publisher, which does not equal the number of DB queries. Count at source subscription/actual DB calls, or use database metrics.

### 13.2. End-to-End Tests for Finite `Flux`

Minimum test suite:

1. Same key, first miss: one source subscription, receives list in expected order.
2. Same key, subsequent hit: no new source subscription; receives the same snapshot.
3. Different key: creates an independent snapshot.
4. Evict key A: A misses, B is not deleted.
5. `Flux.empty()`: verify empty list handling per provider.
6. `Flux.error(...)`: verify incomplete snapshot is not returned as success.
7. Infinite or slow source: timeout/memory guard and cancellation.
8. Result with tens of thousands of items: measure heap, response latency, and backpressure.
9. Concurrent same-key misses: measure how many times the source is subscribed to under the real provider.
10. Two pods, local/shared cache: do not mistake local single-flight for distributed coordination.
11. Update in a transaction: test post-commit invalidation and late readers refilling stale data.
12. Using a real WebFlux endpoint: test time-to-first-byte/time-to-first-item, not just total duration.
13. Cache name, SpEL key, and tenant scope: never replay another user's list.
14. Never call `block()` on a production reactive request path.

## 14. Common Mistakes When Caching `Flux`

| Symptom | Cause | Resolution |
|---|---|---|
| Enabling `@Cacheable` makes streaming slow | Entire `Flux` collected into `List` before replaying | Cache only small finite data; use pure streaming for exports/live feeds |
| Infinite `Flux` never gets a complete cache hit | No `onComplete` | Do not cache entire live streams; bound snapshots or use bounded replay |
| JVM memory spikes sharply | Large lists buffered/stored | Limit query/page size, TTL, capacity, entry bytes |
| Cache hit returns stale data | List snapshot does not update automatically on DB changes | Evict/version the proper key after commit |
| Same `Flux` replayed to another tenant | Cache key lacks tenant/authorization scope | Fix cache key and data isolation |
| `@Cacheable` present yet source subscribed every time | Unsuitable cache adapter, method not called via proxy, differing keys, or entry not retained | Check `@EnableCaching`, Spring bean, async mode, and storage |
| Provider reports unsupported async retrieval | `Cache.retrieve`/future path not supported | Use a supporting adapter, e.g. Caffeine async |
| `sync=true` set yet DB still loads twice across pods | Independent local cache instances, or provider lacks distributed coordination | Test cross-node, choose distributed single-flight when needed |
| `Flux` errors partway, next call reloads | Result had no successful `onComplete` | Handle errors intentionally, avoid storing partial snapshots |
| Cache read returns unexpected order | Non-deterministic data source/order, adapter, or serialization | Ensure `ORDER BY` and deterministic snapshot lists |
| Client cancels request yet source keeps burning resources | Subscription/cancellation under adapter behaves unexpectedly | Test cancellation and cleanup on the real provider |
| Caffeine `maximumSize(100)` yet heap stays high | Each entry is a `List` of many items | Cap max items per entry or use weighted/byte budgets |
| `unless` evaluation with `Flux` differs from expectations | Future results must be adapted, SpEL/provider semantics differ from sync | Check Javadoc, write tests for result-based veto |
| Method returns `Flux` yet still uses blocking JDBC | Reactive return type does not make blocking I/O non-blocking | Switch to a suitable source or isolate on an appropriate scheduler |
| Caching a single record under both `Flux` and `Mono` | Snapshot, null/empty, and key semantics inconsistent | Pick one return-type contract matching the domain |

## 15. Decision Checklist: Should You Cache a `Flux`?

1. **Is the `Flux` finite?** If there is no termination point, do not use full-list caching.
2. **Is there a maximum element limit?** Bound at the query/source, not only on the client.
3. **Do clients need early streaming?** If records are needed immediately one by one, full-list caching may be the wrong architecture.
4. **Is a stale list snapshot acceptable during the TTL?** If not, design invalidation/versioning.
5. **Does the cache key include all tenant/permission/filter/page/sort parameters?**
6. **Does the provider have compatible async retrieval?** Have Caffeine async or a suitable adapter been tested?
7. **Is Spring 6.1+ configured with reactive cache adaptation enabled by default?** Check versions, flags, and configuration.
8. **With `@EnableCaching`, do calls pass through the Spring-managed bean proxy?** Avoid self-invocation.
9. **Can cache entry sizes grow too large?** Key count quotas do not bound the max size of a `List`.
10. **Can the source emit errors, empty, or cancel?** Has each case been tested?
11. **Are source subscriptions and DB queries measured, not just method call counts?**
12. **Have multi-node, concurrent misses, and hot-key expiry been tested?**
13. **Is `block()` misused on the reactive event loop?** Block only in demos/tests or appropriate boundaries.
14. **Is Spring Cache really the right tool?** If the goal is replaying one existing publisher, consider Reactor `Flux.cache(...)`; for long streams, avoid materializing.
15. **Are there dashboards for TTL, payload size, P99 latency, GC, and stale snapshots?**

### Summary

With reactive caching support in **Spring Framework 6.1+**, a `@Cacheable` method returning `Flux<T>` is adapted by **collecting all elements into a `List<T>` when the `Flux` completes**, then storing that list under **one cache key**. On a hit, the list is replayed as a `Flux`. This fits **finite, small, clearly keyed results** such as a search page, but can eliminate streaming benefits for large datasets or infinite streams.

To apply it safely, you need an async-capable cache backend, per-snapshot element/byte bounds, capacity/TTL configuration, proper key/invalidation design, and testing for subscriptions, latency, memory, and concurrency. **Do not mistake returning `Flux` on the API for a guarantee that the system still streams elements directly without collecting a list.**

### References

- Spring Framework — Declarative annotation-based caching, reactive/`CompletableFuture` return types section: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework 6.2 — `Cacheable` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Framework 6.2 — `Cache.retrieve` and asynchronous access: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/cache/Cache.html
- Spring Framework 6.2 — `CaffeineCacheManager.setAsyncCacheMode`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/cache/caffeine/CaffeineCacheManager.html
- Project Reactor — Reactor reference guide, Flux/Mono, backpressure, `collectList`, and `cache`: https://projectreactor.io/docs/core/release/reference/
- Caffeine — Population/AsyncCache: https://github.com/ben-manes/caffeine/wiki/Population