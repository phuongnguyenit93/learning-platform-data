# Limitations with Infinite Streams or Large Result Sets in Async Spring Cache

## 1. The Problem to Solve

Caching helps skip repeated queries/computations, but **not all asynchronous data is suitable for storing wholesale in a single cache entry**. A `CompletableFuture<T>` typically yields one result upon completion; `Mono<T>` emits at most one element; whereas `Flux<T>` can emit 0, a few elements, millions of elements, or continue infinitely.

When trying to cache an entire `Flux` by collecting elements into a list, two dangerous cases arise:

- **Infinite streams:** there is no normal completion signal (`onComplete`). There is no point at which a list of "all results" is finalized. If elements keep accumulating, memory can grow without bound until cancellation, error, or resource exhaustion.
- **Finite but very large streams:** it may eventually complete, yet the list, cache entry, serialized copy, and response can consume excessive heap/RAM, increasing GC time, CPU, and network usage.

**Principle:** only cache **results with a bounded scope, cost, and lifecycle**. For continuous events, use streaming, retention, or bounded snapshots; for large lists, use pagination, projections, or aggregates.

Scope of this lesson: Spring Framework 6.1+ supports adapting cached results of `CompletableFuture` and recognized reactive types such as Reactor `Mono`/`Flux`. Spring version, cache provider, and configuration can affect actual async caching behavior; do not extrapolate behavior blindly across all versions.

## 2. Asynchronous Differs from Infinite Data

"Asynchronous" describes **when** results arrive, not **how much** data is produced.

| Type / Source | Element Count | Suitability for Caching Wholesale |
|---|---|---|
| `CompletableFuture<Product>` | One result when the future completes | Usually reasonable if the value is moderate in size |
| `Mono<Product>` | At most one element | Usually reasonable when the value is not too large |
| `Mono<List<Product>>` | One emission, but the list can be huge | Must bound the list |
| `Flux<Product>` from a `LIMIT 20` query | Finite, at most 20 | Can be suitable if results are stable |
| `Flux<Product>` returning millions of records | Finite but very large | Memory/serialization risk |
| Unbounded `Flux.interval(...)` | Infinite until canceled | Do not cache wholesale |
| SSE, WebSocket, CDC, log tail | Usually long-lived/infinite | Use dedicated streaming/state stores |

A `Mono<List<T>>` is not "lightweight" merely because it has a single emission; the emitted object can still be huge. A `Flux<T>` is not necessarily infinite; you must examine **the data source and completion condition**.

## 3. How Does Spring 6.1+ Handle Reactive Return Types?

Spring Cache can recognize asynchronous/reactive return types, adapting caching to the emitted result rather than merely storing the future/publisher object.

Conceptual model:

~~~text
@Cacheable method returns Mono<T>
   → Mono completes with value T
   → caches value T if provider supports it

@Cacheable method returns Flux<T>
   → Flux emits T1, T2, ... Tn then onComplete
   → result is collected into List<T>
   → caches List<T>
   → cache hit can be adapted back into Flux<T>
~~~

With `Flux`, **the result must complete to obtain a full list**. This is why both non-terminating streams and gigantic lists are unsuitable for whole-sequence caching.

Do not assume every `CacheManager` supports asynchronous retrieval identically, or that the whole stream is sent element by element to the client while the cache mechanism is collecting the list. You must test the actual **Spring version + `CacheManager` + `Cache` provider + return type** combination.

Do not confuse "caching a finite snapshot sequence" with "maintaining a real-time connection for subscribers": those are two different goals.

## 4. Anti-Pattern: Caching a Non-Terminating `Flux`

Reactor example:

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofSeconds(1));

// DO NOT try to await collecting all items:
// Mono<List<Long>> allTicks = ticks.collectList();
~~~

`Flux.interval` keeps emitting elements over time and does not emit `onComplete` on its own. `collectList()` can only build a complete list when the source terminates normally; a non-terminating source never produces a full result.

Example **that should not be annotated**:

~~~java
// ANTI-PATTERN: this is an infinite real-time source.
@Cacheable(cacheNames = "liveTicks")
public Flux<Long> liveTicks() {
    return Flux.interval(Duration.ofSeconds(1));
}
~~~

This is illustrative Spring + Reactor integration code requiring appropriate imports and dependencies. If an adapter needs to collect the entire `Flux` into a `List` to cache it, there will be no complete list; unbounded data accumulation can grow memory usage. Cancellation, timeouts, and errors from the publisher/provider must be handled in a real pipeline.

Similar sources: SSE notifications, real-time stock prices, telemetry, message bus subscriptions, CDC, log tailing, WebSocket streams.

### Can a Timeout Turn an Infinite Stream into a Cacheable Result?

Not automatically. `timeout` usually causes the pipeline to signal an error when the time condition is exceeded, rather than producing a reliable complete list. `take(Duration)` can make the stream terminate after a duration, yet **does not bound the total number of elements or bytes** if the source emits very fast. To cache snapshots safely, enforce **element count, size, and time limits**.

## 5. Finite `Flux` That Is Too Large Still Creates Pressure

~~~java
// Do not cache an entire large catalog this way.
@Cacheable(cacheNames = "allProducts")
public Flux<Product> allProducts() {
    return repository.findAll();
}
~~~

Even though the database has a finite number of records, the collected list can be enormous. Consequences:

- **Heap growth:** source objects, the list being collected, the cache entry, and the response can all be live simultaneously.
- **GC pressure:** huge entries retain many objects for a long time, causing pauses or heavy allocation.
- **Serialization:** remote providers must encode/decode and transfer large payloads over the network.
- **Even cache hits are slow:** every fetch of a huge entry still has to decode, copy, and render.
- **Cache stampede:** multiple requests missing/expiring on TTL simultaneously can concurrently build multiple copies of large data.
- **Invalidation cost:** changing one record may require deleting and recomputing the entire list.
- **Key duplication across variants:** the same dataset with multiple filters/sorts/tenants can produce many large entries.

RAM footprint cannot be estimated accurately from JSON size alone; there is object overhead, serializer overhead, intermediate values, and concurrent requests. Measure with a profiler, metrics, and representative load.

**`Mono<List<T>>` does not solve the size issue**: the large list still must exist in memory. The goal is to reduce the amount of data per request/cache entry, not just change the publisher type.

## 6. Bounding at the Source Before Collecting Data

One way of writing it:

~~~java
Flux<Product> limited = repository.findAll().take(50);
~~~

`take(50)` limits at most 50 elements emitted downstream and then completes. However, if the repository already scanned/loaded too many records before emitting 50 elements, the backend still wastes resources.

Prefer bounding **directly at the DB or source API**. SQL example:

~~~sql
SELECT id, name, price
FROM products
WHERE tenant_id = :tenantId
ORDER BY id
LIMIT :pageSize OFFSET :offset;
~~~

Parameters must be validated and safely bound. For consistent pagination, sorting must be deterministic; check indexes and execution plans. For volatile datasets or large offsets, cursor/keyset pagination may be more suitable.

Bound simultaneously:
1. **Element count**: explicit maximum page size.
2. **Byte size**: records may contain oversized fields.
3. **Time**: query timeouts, publisher timeouts, and cancellation.
4. **Resources**: concurrent requests, connection pools, cache quotas.
5. **Data freshness**: TTL/invalidation/versioning to avoid stale snapshots.

A page that is still too large may need a smaller size or fetching only a projection.

## 7. Spring Pattern: Caching a Finite Page

Suppose a custom reactive repository `findPage` performs source-side pagination:

~~~java
import java.util.List;
import reactor.core.publisher.Mono;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductPageService {
    private final ProductPageRepository repository;

    public ProductPageService(ProductPageRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "productPages")
    public Mono<List<ProductDto>> findPage(
            String tenantId, int page, int size) {

        if (page < 0 || size < 1 || size > 100) {
            return Mono.error(
                    new IllegalArgumentException("Invalid page/size"));
        }

        // Repository MUST bound the query right at the source.
        return repository.findPage(tenantId, page, size)
                .take(size)
                .map(ProductDto::from)
                .collectList();
    }
}
~~~

This is **illustrative integration code**; `ProductPageRepository`, `ProductDto`, and `ProductDto.from` are application-provided. Requires Spring Cache, Reactor, `@EnableCaching`, and a provider suitable for async/reactive caching.

Advantages:
- Each cache entry is **a small page**.
- `take(size)` is an extra guardrail, **not a replacement** for a database limit.
- `Mono<List<ProductDto>>` expresses a finite snapshot result.
- The default key for a multi-parameter method includes `tenantId`, `page`, and `size`, distinguishing different pages.

**Important regarding authorization:** validation and permission checks should run **before cache interception** at the controller/facade. If all checks are placed inside the cached method, a cache hit can bypass the method body and accidentally skip checks. Never trust `tenantId` from a client without authentication/authorization; design keys/namespaces to avoid mixing data across tenants.

If results depend on filters/sort/locale/version/read permissions or snapshot date, those must also be included in the key or corresponding partitioning policy. A key consisting only of `page` is insufficient.

## 8. Can a Finite `Flux` Be Cached Directly?

It can be considered when you are certain the result is small and terminates:

~~~java
@Cacheable(cacheNames = "recentEvents")
public Flux<EventDto> recentEvents(String tenantId, int limit) {
    if (limit < 1 || limit > 50) {
        return Flux.error(new IllegalArgumentException("Invalid limit"));
    }

    return eventRepository.findRecent(tenantId, limit)
            .take(limit)
            .map(EventDto::from);
}
~~~

This is illustrative Spring + Reactor code requiring a repository and DTO. With Spring 6.1+ and a compatible provider, `Flux` is adapted into a result list for caching. Here the element count is bounded, so caching a snapshot can make sense.

Even so, if the API promises to **stream each element immediately as it arrives**, collecting for caching can alter latency or consumption characteristics. For APIs primarily returning a small snapshot, `Mono<List<EventDto>>` communicates intent more clearly. For SSE/live feeds, **do not cache wholesale**; create a separate recent-snapshot endpoint.

## 9. Alternative Caching: Pages, Summaries, Per-ID, and Snapshots

| Need | Better Approach | What to Cache |
|---|---|---|
| Large catalog | DB pagination or cursor | A small page/projection |
| Only need total count | Aggregate query | `count`/summary, without pulling every record |
| Single record details | Cache-aside by ID | Small DTO |
| Periodically updated dashboard | Versioned snapshot with TTL | Moderately sized aggregated data |
| Real-time events | Streaming + separate retention | Only metadata or recent snapshot |
| Large files/videos | Object storage/CDN/HTTP cache | URL/metadata/chunks per transport protocol |
| Long search results | Page by query/sort/filters | Frequently accessed pages |

Example of caching a count instead of caching the whole catalog:

~~~java
@Cacheable(cacheNames = "productCounts")
public Mono<Long> countByTenant(String tenantId) {
    return repository.countByTenant(tenantId);
}
~~~

This illustrative code is only valid when `countByTenant` is an aggregate query at the source. If inside it still does `findAll().collectList().map(list -> (long)list.size())`, the application has pulled all data pointlessly.

### Windowing Does Not Cure an Infinite Outer Stream

`buffer(100)`/`window(100)` splits data into batches; however, if the annotation still tries to store **the entire outer publisher** of an infinite stream, it still has no completion point. You must design **each window/snapshot as a finite request** with measurable retention and data bounds.

## 10. Standalone Runnable Java 17: Caching a Finite Page

The following program **only simulates** caching using `ConcurrentHashMap` and `CompletableFuture`; it does not run Spring/`Flux` or a distributed cache. It illustrates keying by page/size and taking a finite slice from a stream with no natural stopping point.

Create the file **`BoundedAsyncCacheDemo.java`**:

~~~java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;

public class BoundedAsyncCacheDemo {
    private static final ConcurrentMap<String, CompletableFuture<List<Integer>>>
            CACHE = new ConcurrentHashMap<>();
    private static final AtomicInteger SOURCE_LOADS = new AtomicInteger();

    private static CompletableFuture<List<Integer>> getPage(
            int page, int size, Executor executor) {
        if (page < 0 || size < 1 || size > 5) {
            throw new IllegalArgumentException("Invalid page/size");
        }
        String key = page + ":" + size;
        return CACHE.computeIfAbsent(key, ignored ->
                CompletableFuture.supplyAsync(() -> {
                    SOURCE_LOADS.incrementAndGet();
                    int start = Math.addExact(Math.multiplyExact(page, size), 1);
                    return IntStream.iterate(start, n -> n + 1)
                            .limit(size)
                            .boxed()
                            .toList();
                }, executor));
    }

    public static void main(String[] args) {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            List<Integer> page0 = getPage(0, 3, pool).join();
            List<Integer> repeat = getPage(0, 3, pool).join();
            List<Integer> page1 = getPage(1, 3, pool).join();
            List<Integer> boundedInfinite = IntStream.iterate(1, n -> n + 1)
                    .limit(4).boxed().toList();

            System.out.printf("page0=%s, repeated=%s%n", page0, repeat);
            System.out.println("page1=" + page1);
            System.out.printf("sourceLoads=%d, cacheEntries=%d%n",
                    SOURCE_LOADS.get(), CACHE.size());
            System.out.println("boundedInfinite=" + boundedInfinite);
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac --release 17 BoundedAsyncCacheDemo.java
java BoundedAsyncCacheDemo
~~~

**Verified stdout:**

~~~text
page0=[1, 2, 3], repeated=[1, 2, 3]
page1=[4, 5, 6]
sourceLoads=2, cacheEntries=2
boundedInfinite=[1, 2, 3, 4]
~~~

Explanation:
1. Page 0 and page 1 have different keys; each page loads at most 3 elements.
2. Repeating page 0 reuses the future in the map, so total source loads is 2.
3. `IntStream.iterate` is a stream with no natural endpoint, yet `limit(4)` causes `toList()` to complete.
4. The program **does not execute** unbounded collection of an infinite stream, avoiding hangs or out-of-memory errors.
5. `computeIfAbsent` only coordinates within **one map/one JVM**. Do not infer that Spring providers have the same sync mechanism. This code caches the future as an object for illustration and does not simulate Spring 6.1 reactive adaptation details.

If a future fails and the application keeps it in the map forever, subsequent requests may keep receiving the stale error. Production design requires eviction/retry, timeouts, and a policy for exceptional completion.

## 11. Validation, Keys, and Consistency Across Pages

A good pipeline:

~~~text
HTTP request
   |
   v
Auth + validate tenant/page/size/filter/sort
   |
   v
Facade calls Spring bean via proxy
   |
   v
@Cacheable page by key including tenant,page,size,sort,version
   |
   +-- HIT: return small page from cache
   |
   +-- MISS: query DB with LIMIT → collectList → cache page
~~~

In proxy mode, internal calls like `this.cachedMethod()` can bypass the cache interceptor. Tests must call through the appropriate Spring-managed bean.

Different pages must have different keys. Beyond tenant/page/size, you may also need sort, filter, locale, and version. Caching does not replace authorization.

### Pagination Does Not Automatically Create a Consistent Snapshot

If data is inserted/deleted between reads, offset pagination can duplicate or skip records. When consistent snapshots are required, use deterministic sorting, cursor/keyset pagination, versions/generations, or a snapshot token. TTL/invalidation must match the rate of change and freshness requirements.

## 12. Async Providers, TTL, Cancellation, and Stampede

Several questions must be verified in the real environment:

- Does the cache support the asynchronous retrieval/adapter required by the Spring version in use?
- If a `CompletableFuture` completes exceptionally or is canceled, does the cache leave an entry behind or not?
- Across what scope does `@Cacheable(sync=true)` coordinate requests for the same key—a single JVM or distributed?
- What is the page TTL? Who evicts when the source changes?
- If many requests miss simultaneously after TTL expiry, will multiple large lists be built concurrently?
- Does the cache enforce entry size limits, total capacity, and metrics by cache name/key?

**Timeouts do not replace element/byte limits.** A very fast source can still emit huge volumes before a timeout fires. If a subscriber cancels before `Flux` completes, do not assume a complete list was ready to cache; actual behavior must be tested with the provider and publisher in use.

Do not place critical business side effects inside a cache loader expecting the cache to execute it only once. With two pods using separate local caches, `sync=true` (when supported by the provider) does not automatically create distributed single-flight either.

## 13. Spring `@Cacheable` Is Not Reactor `Flux.cache()`

Both share the word "cache", yet their nature differs:

- **Spring `@Cacheable`**: caches method results by key via `CacheManager`; for `Flux` in Spring 6.1+, can collect emissions into a `List` to store.
- **Reactor `Flux.cache()`**: an operator on a single publisher instance to replay signals to future subscribers; has overloads bounding `history` or TTL.

Do not use unbounded replay `Flux.cache()` on an infinite stream and assume bounded memory. Sharing a live subscription, storing snapshots, and recording event history are three distinct needs requiring distinct mechanisms.

## 14. Safe Testing

### Functional Tests

1. Queries have source-side limits and the pipeline emits `onComplete`; each page is at most max size.
2. Negative pages or size zero/above max are rejected **before cache interception**.
3. Keys for tenant/page/size/filter/sort/version are distinct.
4. Cache hits retrieve the exact snapshot; TTL/eviction reflects source updates.
5. Loader errors, provider timeouts, and cancellation do not produce an incomplete "successful" result.

### Testing Infinite Streams Without Hanging the Process

**Do not** run unbounded `Flux.interval(...).collectList().block()` in tests. Use `StepVerifier` to cancel after a few elements or test a bounded pipeline:

~~~java
StepVerifier.create(Flux.range(1, 100).take(3).collectList())
    .expectNext(List.of(1, 2, 3))
    .verifyComplete();
~~~

This is a **Reactor test** (requiring imports `StepVerifier`, `Flux`, `List`, and the `reactor-test` dependency), not standalone plain Java. It verifies that `take(3)` makes the pipeline complete; **it does not prove the Spring cache provider was tested**.

### Performance Tests

- Measure peak heap, GC pauses, and serialized payload size of individual cache entries.
- Test many concurrent requests on cache miss/TTL expiry.
- Measure latency, hit rate, bandwidth, and deserialization time when caching a page versus caching the whole dataset.
- Test multiple instances and the real backend if production runs clustered.
- Inject provider errors, cancellations, and query timeouts, verifying zero subscription leaks.

## 15. Common Misconceptions

| Misconception | Reality |
|---|---|
| "Flux is async so infinite streams can be cached" | Caching a sequence generally requires a finite, completed result |
| "Mono emits one element so it must be small" | That element could be a huge list/byte array |
| "A finite Flux is always worth caching" | Large entries can strain RAM, network, and GC |
| "collectList stops automatically after N elements" | Usually waits for `onComplete`; must use `take(N)`/termination mechanisms |
| "take(50) guarantees the DB only scans 50 records" | Needs source-side limit/pushdown |
| "Timeout equals a size limit" | Timeouts do not stop bursts of millions of elements |
| "sync=true locks across all JVMs" | Provider-dependent; not automatically a distributed lock |
| "Flux.cache() is always bounded" | Bounded only with suitable history/TTL policies |
| "Key only needs page index" | Needs tenant/size/filter/sort/version when they affect data |
| "Testing with 3 elements is enough" | Must also test completion, provider, memory, and cancellation |

## 16. Design Checklist

Before adding `@Cacheable` to an asynchronous result:

1. Is the publisher guaranteed to terminate normally?
2. Are maximum element count, byte size, and time bounded?
3. Are bounds enforced directly at the DB/source API?
4. Should you cache a page/summary/per-ID instead of the whole `Flux`?
5. Does the key include tenant, size, page, filter, sort, and version?
6. Do your Spring/cache provider versions support reactive/`CompletableFuture` caching?
7. Do TTL and invalidation reflect acceptable staleness?
8. Under concurrent cache misses, is RAM/network pressure bounded?
9. On timeout/cancellation/error, are resources/subscriptions cleaned up properly?
10. Have you run realistic load tests and analyzed heap/entry sizes?

**Rule:** only cache **finite results with predictable cost**; keep live event streams on appropriate streaming mechanisms.

## 17. Self-Check

**1.** Why is `@Cacheable` on `Flux.interval(...)` unsuitable for storing the entire result?

**2.** Is `Mono<List<Product>>` guaranteed to use little memory?

**3.** Does `take(50)` automatically guarantee the database only scans 50 rows?

**4.** When displaying a very large catalog, cache the entire `Flux` or individual pages?

**5.** From an infinite Java `IntStream.iterate`, which operator helps `toList()` terminate?

**6.** Why do page keys need tenant/page/size/filter/sort when data depends on them?

**7.** Is `Flux.cache()` the same as `@Cacheable`?

**8.** Can a timeout replace byte limits and item limits?

**Answers:**

1. The source never completes on its own, so there is no full list to cache.
2. **No.** A single emission can hold a very large list.
3. **No.** Must bound at the source and inspect the execution plan.
4. **Paginate**, or cache small summaries/DTOs if suitable.
5. `limit(n)` or a finite stopping condition.
6. To avoid cache key collisions, wrong data, and cross-tenant leaks.
7. **No.** Reactor cache is a replay operator; Spring cache is a method/result cache abstraction.
8. **No.** A burst can emit huge amounts of data before the timeout fires.

## 18. References

- Spring Framework Reference — *Declarative Annotation-based Caching*, *Caching with CompletableFuture and Reactive Return Types* section: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Javadoc — `Cacheable` and `sync`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Javadoc — `Cache` and async retrieval API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/Cache.html
- Reactor Core Reference — `Flux`/`Mono` and operators: https://projectreactor.io/docs/core/release/reference/
- Reactor Javadoc — `Flux.collectList`, `take`, `cache`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Java 17 Javadoc — `IntStream.iterate` and `limit`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html

**Conclusion:** Spring can cache a `Flux` by collecting emissions into a list, yet **infinite streams have no complete result** and overly large finite streams strain resources. Cache **finite pages/snapshots/summaries**, bound at the source, choose accurate keys/TTLs, and verify against the real provider; do not cache entire live streams.