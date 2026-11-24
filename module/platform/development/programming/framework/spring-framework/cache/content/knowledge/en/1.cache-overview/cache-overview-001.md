# What Is a Cache and the Problem of Reducing Redundant Processing?

> Scope: foundational knowledge about caching, why caching reduces redundant work, and how to recognize its benefits, costs, and risks in Java/Spring applications.

## Learning Objectives

After this lesson, you can:
- Explain caching using the `key → value` model and distinguish a cache from the origin data source.
- Describe `cache hit`, `cache miss`, the first read flow, and subsequent reads.
- Identify repetitive tasks suitable for caching and calculate latency benefits using a quantitative example.
- Understand why a cache can return stale data, consume memory, add complexity, and require expiration/invalidation policies.
- Understand where Spring Cache fits and practice with a standalone runnable Java 17 example.

## 1. The Problem: Same Request, Same Expensive Processing

Suppose a service needs to fetch product information to display on a page. Every time `getProduct("P100")` is called, the application must query the database, assemble the information, and build the result. If the product data has not changed yet hundreds of requests ask for `P100`, we are repeating the exact same work.

Some common repetitive tasks:
- The same query for reference data or rarely changing configuration.
- Recomputing CPU-intensive calculation results from the same set of parameters.
- Repeatedly reading a resource from an external service with high network latency.
- Transforming or re-aggregating stable data for multiple reads.

Not every call to the same method can reuse its result. If the result depends on the current time, access permissions, recently changed state, or has side effects, reusing an old result may be incorrect. Therefore, the first question is: **given the same inputs and within an acceptable time window, can the result be safely reused?**

## 2. What Is a Cache?

A **cache** is a temporary storage place for existing or already-computed results so that subsequent requests can read them back at a lower cost than executing the entire original processing. A cache entry typically consists of:

| Component | Meaning | Example |
| --- | --- | --- |
| `key` | Unique identifier for the result being looked up | `product:P100:vi` |
| `value` | Stored result ready for reuse | Product P100 data |
| Expiration/policy | Rules defining when an entry is no longer valid or needs removal | 5-minute TTL, delete when product changes |

A cache is a **copy or derived result**, typically not the *source of truth* (the authoritative data source). For example, the database holds the official product information; the cache holds a fast-to-read copy that may be older.

Key vocabulary to remember:

- **Cache hit:** a usable entry is found for the key; return the stored result and skip the corresponding origin processing.
- **Cache miss:** no valid entry exists; the original work must be executed, and the result may then be stored for next time.
- **Cache population:** placing a result into the cache.
- **Invalidation:** proactively making a cache entry no longer usable, such as deleting `product:P100` after updating P100.
- **Expiration:** an entry expires based on time or policy.
- **Eviction:** removing an entry from the cache, usually to free up capacity or apply a replacement policy.

### Lifecycle of a Read: Cache-Aside (Lazy Loading)

```text
Request getProduct("P100")
          |
          v
Look up key "product:P100" in cache
          |
       +--+--+
       |     |
      HIT   MISS
       |     |
       |     v
       |  Query/compute from origin source
       |     |
       |  Store result in cache (if allowed)
       |     |
       +--+--+
          |
          v
      Return result
```

The first call is usually a miss; subsequent reads with the same key can be hits. A miss is not automatically a system error: it is normal behavior when an entry has not been loaded yet, has expired, was deleted, or when the cache just restarted. In the cache-aside pattern, the application proactively checks the cache and loads data on a miss.

## 3. How Does Caching Solve the Redundant Processing Problem?

Suppose querying and assembling a product takes 120 ms, while checking the cache takes 2 ms. With a hit rate `H = 80%`, a simple model for the average time is:

```text
T_average ≈ T_cache_lookup + (1 - H) × T_origin_processing
          = 2 ms + (1 - 0.8) × 120 ms
          = 26 ms/request
```

Without caching, the origin processing path in this example takes about 120 ms/request. This is an illustrative calculation, not a performance guarantee: in practice there are also resource contention, serialization, network access, data updates, key distribution, and memory costs.

**Cache hit rate** = number of cache read hits / total number of cache lookups. A high hit rate can reduce the number of hits to the database or external APIs, thereby reducing CPU/I/O load, improving latency, and helping the system handle more requests. However, a high hit rate alone is not enough to prove a system is healthy: if the cache holds wrong or overly stale data, good-looking numbers still come with wrong results.

### Distinguishing Three Concepts

- **Saving processing:** avoiding re-executing the original work on a hit.
- **Reducing latency:** a hit typically responds faster than a miss; not every cache is faster than the origin source.
- **Increasing throughput:** by relieving a bottleneck, the system can serve more requests; the benefit depends on where the bottleneck occurs.

## 4. When Should You Cache, and When Should You Not?

Prioritize results that have **high creation cost**, are **requested repeatedly**, are **identifiable by key**, and **tolerate a certain degree of update delay**. Examples: rarely changing catalogs, product display information, published configurations, and aggregated results for the same filter set.

Think carefully or avoid direct caching in the following situations:

1. Data must be accurate immediately after every change (for example, an account balance used to authorize a transaction), unless a consistency mechanism is in place that meets the requirement.
2. The result depends on identity, tenant, role, or private context, yet the key does not include that full context: there is a risk of cross-user data leakage.
3. Operations with side effects such as payments, sending notifications, or recording orders; returning a cached result **cannot** replace executing the business action.
4. Every request uses a different key, rarely repeats, or checking the cache is more expensive than the original processing.
5. Data is very large, memory is constrained, and strong consistency is required without an invalidation plan.

**Principle:** only cache what can be reused correctly; measurable optimization matters more than adding caching everywhere.

## 5. Java 17+ Example: Compute Once per Key

The standalone example below uses `ConcurrentHashMap` and `computeIfAbsent`. It simulates an expensive origin task by printing `Recomputing...`; subsequent calls with the same key will retrieve the stored result.

Create the file `CacheDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

public class CacheDemo {
    private final ConcurrentMap<String, String> cache =
            new ConcurrentHashMap<>();
    private final AtomicInteger calculations = new AtomicInteger();

    private String loadFromSource(String id) {
        int count = calculations.incrementAndGet();
        System.out.println("Recomputing for " + id + " (attempt " + count + ")");
        return "user:" + id;
    }

    public String getProfile(String id) {
        return cache.computeIfAbsent(id, this::loadFromSource);
    }

    public static void main(String[] args) {
        CacheDemo demo = new CacheDemo();
        System.out.println("Fetch 1: " + demo.getProfile("u1"));
        System.out.println("Fetch 2: " + demo.getProfile("u1"));
        System.out.println("Fetch 3: " + demo.getProfile("u2"));
        System.out.println("Origin processing count: " + demo.calculations.get());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac CacheDemo.java
java CacheDemo
```

Exact output when running `main` in the order above:

```text
Recomputing for u1 (attempt 1)
Fetch 1: user:u1
Fetch 2: user:u1
Recomputing for u2 (attempt 2)
Fetch 3: user:u2
Origin processing count: 2
```

**Explanation:** the first call for `u1` is a miss so `loadFromSource` runs; the second call for `u1` is a hit; `u2` is a new key so it misses. If `loadFromSource` were called directly all three times, the origin work would run three times. `ConcurrentHashMap` supports thread-safe concurrent access on the map, and `computeIfAbsent` avoids racing multiple computations for the same key under normal operation of this map.

**Intentional limitations of the example:** the cache lives only inside a single Java object, has no TTL, has no entry limit, does not synchronize across multiple instances, and is not cleared when source data changes. Do not use this prototype directly as a long-lived production cache because it can retain stale data and grow memory indefinitely with distinct keys.

## 6. Stale Data and Expiration Rules: Issues You Cannot Ignore

Suppose product P100 is priced at 100,000 VND and the result is cached. Staff updates the source price to 110,000 VND. If the cache still returns 100,000 VND, the system has **stale data**.

Common strategies:

| Strategy | How It Works | Trade-off |
| --- | --- | --- |
| TTL (*time to live*) | Entry expires after a duration | Simple, but has a stale-data window; too short a TTL causes many misses |
| Invalidate on write | When source data updates successfully, delete related keys | Fresher, but must accurately identify every affected key |
| Update cache on write | After updating source, write the appropriate cache value | Can avoid the next miss, but must handle ordering/concurrency |
| Capacity limit + eviction | Drop entries via provider policies such as LRU/LFU | Controls memory; hit rate may decrease |

**TTL does not mean data is always fresh.** A 5-minute TTL can still return an old price during that window if there is no invalidation on change. Also, eviction due to full memory does not necessarily mean the record has expired.

When handling updates, transactions must be considered: invalidating before the source write succeeds can cause the cache to be repopulated from the old value; invalidating after commit is usually more appropriate. In distributed systems there are also race conditions between read requests, source updates, and cache repopulation; the consistency design must match business requirements.

## 7. Keys, Storage Scope, and Associated Risks

### Designing the Right Key

If `getPrice(productId, currency, customerGroup)` returns different results per group, a key containing only `productId` is incomplete. A proper key must reflect **every parameter and context that changes the result**, such as `price:P100:VND:retail`. For per-account or per-tenant data, establish access boundaries before caching. Keys should be stable, consistent, and sufficiently distinct across results.

### Local Cache vs. Distributed Cache

- **Local/in-memory per instance:** fast lookup, minimal network dependency; each process has its own copy, hard to synchronize invalidation across multiple instances, and the cache is lost when the process restarts.
- **Distributed cache:** multiple instances can share data (e.g., Redis); enables shared hits and invalidation, but incurs network latency, extra infrastructure, connection failures, and serialization cost.
- **Multi-tier:** a cache close to the application combined with a shared cache can further reduce latency, but requires even clearer rules for read and update ordering.

### Common Pitfalls

- **Cache stampede / thundering herd:** many concurrent requests miss a hot key at once and all hit the origin. You can use single-flight loading for the same key, appropriately scoped locking, or controlled refresh policies.
- **Hot key:** one key receives excessive traffic, creating a bottleneck on a single node or memory region.
- **Memory pressure:** the number of keys grows uncontrolled; requires capacity limits and eviction policies.
- **Negative caching:** briefly caching "not found" results when appropriate; if the data appears shortly afterward, the old negative result also needs to expire.
- **Caching with wrong context:** omitting access permissions, locale, version, or tenant parameters from the key leads to returning wrong data.
- **Masking design flaws:** caching can hide an overly slow query; measure and optimize the origin when needed.

## 8. Where Does Caching Live in Spring Framework?

Spring Cache provides an **abstraction layer** to declare cache checking/storing/eviction around method calls. The idea remains: on a hit return the stored result, on a miss execute the method and consider storing the result. Common annotations:

- `@Cacheable`: can skip running the method if a result is found in the cache.
- `@CachePut`: the method still runs; the result is written to the cache.
- `@CacheEvict`: removes specified cache entries (or the entire cache depending on configuration).
- `@EnableCaching`: enables processing of cache annotations in Spring configuration.

Illustrative snippet in **a Spring project that already has `Product`, `ProductRepository`, and an appropriate `CacheManager`** (method illustration snippet, not a standalone Java program):

```java
@Cacheable(cacheNames = "products", key = "#id")
public Product getProduct(String id) {
    return repository.findById(id).orElseThrow();
}
```

When calling `getProduct("P100")` through a Spring proxy, the framework looks up the cache named `products` with key `P100`. A hit can return the stored value directly; a miss calls `repository`, then stores the result according to the rules. When updating a product, the application also needs a mechanism to delete or update related entries.

**Two common points of confusion:** (1) Spring Cache is an abstraction and does not itself determine TTL, eviction, or capacity for every provider; that depends on the storage configuration such as Caffeine or Redis. (2) In the default proxy mode, a method within the same object calling another `@Cacheable` method on itself (*self-invocation*) does not go through the proxy and therefore does not trigger caching behavior like a call from outside the bean.

Read more in the official documentation:
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — TTL/TTI/Eviction Policies](https://docs.spring.io/spring-framework/reference/integration/cache/specific-config.html)

## 9. Evaluating Cache Effectiveness with Real Metrics

Before and after enabling caching, monitor the same kind of workload:

1. **Hit/miss rate by cache and key group**: is redundant processing actually being avoided?
2. **API p50/p95/p99 latency** and origin latency: is it actually faster for users?
3. **DB query count, API calls, CPU, and throughput**: has the bottleneck eased?
4. **Capacity, eviction, expiration, reload time**: is too much data being retained?
5. **Freshness and wrong-data errors**: have update scenarios been tested?
6. **Behavior when the cache fails or is cold**: can the origin system withstand miss traffic?

A good cache delivers measurable benefits **while still meeting data correctness requirements**. Increasing hit rate at the expense of correctness is not a successful optimization.

## 10. Practice Scenario and Self-Check

**Scenario:** An API returns a list of provinces/cities from a rarely changing data source and is called 10,000 times/day. Choose a key identifying the dataset and display language; populate the cache on a miss; set a reasonable TTL; proactively invalidate when the dataset changes; and monitor hit rate, latency, and freshness.

Answer for yourself:
1. Why is the second call with the same key usually faster than the first? What could cause it to still miss?
2. If a product price was just updated, does a 10-minute TTL guarantee the new result immediately? What else is needed?
3. Why should `getPrice("P100", "USD")` and `getPrice("P100", "VND")` not share the same key?
4. When running 5 application instances, how does a local cache differ from a distributed cache?
5. You observe a 95% hit rate, yet both p95 latency and wrong-data reports are rising: what would you investigate?

**Takeaway:** Caching trades repeated computation/read cost for storage, lookup, and freshness management costs. Choose what to cache, keys, expiration, and invalidation mechanisms based on business requirements; then measure effectiveness with real metrics.