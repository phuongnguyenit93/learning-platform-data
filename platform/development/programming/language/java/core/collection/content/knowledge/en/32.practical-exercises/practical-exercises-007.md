# Comparing a Simple LRU Cache with Real-World Caching Requirements

## 1. Problem and Objectives

An application frequently reads the same data repeatedly: configurations, product catalogs, computed results, or database lookup entries. Placing results close to where they are used reduces latency and the number of calls to the data source. However, RAM is finite: when the cache is full, it must decide which entries to keep and which to evict.

**LRU (Least Recently Used)** is an eviction policy: when space is needed, remove the least recently accessed element. A simple LRU cache is great for practicing Java Collections and understanding eviction policies, but **a production cache is a full temporary data management system** that must also handle data expiration, concurrent load, RAM limits, source failures, and operational observability.

After completing this lesson, learners should be able to:
- Implement an entry-count-based LRU cache using Java Collections and accurately predict the order after read/write operations.
- Distinguish between **eviction** (removing entries to free up space), **expiration** (time-based expiry), and **invalidation** (proactively marking stale data as invalid).
- Identify where a minimal LRU cache will fail in real deployments and choose appropriate countermeasures for the requirements.
- Design metrics and test cases before transitioning from an academic example to a system under load.

### Running Scenario

Suppose a product service reads records from a database and holds at most three products in an in-process memory cache. If all queries have similar payload sizes, no updates occur, and only a single thread accesses the cache, an entry-count-based LRU cache is a reasonable starting point. Now add real-world requirements: product prices change, concurrent queries spike, payload sizes vary widely, and the service runs across multiple instances. Each requirement exposes a limitation of basic LRU.

## 2. How Does LRU Work?

With capacity = 3, assuming the order goes from **least recently used → most recently used**:

| Operation | Order After Operation | Explanation |
| --- | --- | --- |
| put(A), put(B), put(C) | A → B → C | A is the oldest entry. |
| get(A) | B → C → A | A cache hit on A makes A the most recently used entry. |
| put(D) | C → A → D | Cache is full; evict B and insert D. |
| get(B) | C → A → D | B is no longer in the cache: cache miss. |
| put(A, new value) | C → D → A | Updating A also counts as an access in an access-ordered LinkedHashMap. |

Key distinctions:
- **Hit**: the key exists and the value satisfies the cache's validity conditions; no data source call is needed.
- **Miss**: no usable value is present; typically requires loading from the source.
- **Eviction**: removing an entry according to a capacity policy. In this example, it is the least recently used entry.
- **Expiration**: an entry becomes expired under a time policy, even if it has not been evicted.
- **Invalidation**: removing or invalidating an entry due to an update, deletion, permission change, or business event.

LRU does not know whether a value is still valid from a business perspective. An entry that is read continuously can stay at the most-recently-used end of the LRU list forever while holding a stale price.

### How Does LRU Differ from Other Options?

| Mechanism | Decision Basis | When to Use | Notable Limitation |
| --- | --- | --- | --- |
| FIFO | Insertion time | Want simplicity without prioritizing re-access | May evict an entry that was just read many times. |
| LRU | Most recent access | Access patterns exhibit temporal locality | A sequential scan can flush hot data out of the cache. |
| LFU | Access frequency | Data popularity is relatively stable | Must manage counters and prevent formerly hot items from occupying space forever. |
| TTL / expire-after-write | Time since write | Want to bound data age | Does not inherently bound entry count or byte size. |
| Expire-after-access / TTI | Time since last access | Want to drop entries unused for a period | Data can remain stale indefinitely if continuously accessed. |
| Event-driven invalidation | Data/business change | Need immediate refresh upon a known change | Requires a reliable event stream and handling for missed events. |

TTL, size limits, and eviction policies can be **combined**. They solve different problems.

## 3. Implementing a Simple LRU Cache in Java 17+

Java provides **LinkedHashMap**. Its constructor with `accessOrder = true` maintains access order instead of insertion order. Overriding `removeEldestEntry` allows automatically evicting the head entry after insertion when capacity is exceeded.

Create the file **LruComparisonDemo.java**:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class LruComparisonDemo {

    static final class LruCache<K, V> {
        private final int capacity;
        private final LinkedHashMap<K, V> entries;

        LruCache(int capacity) {
            if (capacity <= 0) {
                throw new IllegalArgumentException("capacity must be positive");
            }
            this.capacity = capacity;
            this.entries = new LinkedHashMap<K, V>(16, 0.75f, true) {
                @Override
                protected boolean removeEldestEntry(Map.Entry<K, V> eldest) {
                    return size() > LruCache.this.capacity;
                }
            };
        }

        synchronized V get(K key) {
            return entries.get(Objects.requireNonNull(key, "key"));
        }

        synchronized void put(K key, V value) {
            entries.put(
                Objects.requireNonNull(key, "key"),
                Objects.requireNonNull(value, "value")
            );
        }

        synchronized List<K> keysOldestFirst() {
            return new ArrayList<>(entries.keySet());
        }

        synchronized int size() {
            return entries.size();
        }
    }

    public static void main(String[] args) {
        LruCache<String, Integer> cache = new LruCache<>(3);

        cache.put("A", 10);
        cache.put("B", 20);
        cache.put("C", 30);
        System.out.println("Ban dau : " + cache.keysOldestFirst());

        System.out.println("get(A)  : " + cache.get("A"));
        System.out.println("Sau doc : " + cache.keysOldestFirst());

        cache.put("D", 40);
        System.out.println("Sau D   : " + cache.keysOldestFirst());
        System.out.println("get(B)  : " + cache.get("B"));

        cache.put("A", 100);
        System.out.println("Sua A   : " + cache.keysOldestFirst());
        System.out.println("Kich thuoc: " + cache.size());
    }
}
```

Compile and run in the directory containing the file:

```bash
javac LruComparisonDemo.java
java LruComparisonDemo
```

Expected output:

```text
Ban dau : [A, B, C]
get(A)  : 10
Sau doc : [B, C, A]
Sau D   : [C, A, D]
get(B)  : null
Sua A   : [C, D, A]
Kich thuoc: 3
```

**Explanation of subtle details:**
1. The map is configured with access-order, so **a successful `get` mutates the internal ordering**. In an access-ordered `LinkedHashMap`, updating an existing key via `put` also refreshes the entry's position.
2. `removeEldestEntry` is evaluated after inserting a new entry. When the size exceeds capacity, the head of the list is removed. The condition must be `size() > capacity`, not `>= capacity`, otherwise it will never hold three entries.
3. The example uses `synchronized` for every operation on the map, including `get` and snapshotting the order. This prevents unsafe concurrent structural modification on an access-ordered map, though a single global lock can reduce throughput.
4. The demo intentionally rejects null keys and values. A result of `get(B) = null` is interpreted as a miss; if null values were allowed, `containsKey` or an explicit wrapper result type would be required to distinguish a miss from a cached null.
5. `keysOldestFirst` creates a copy while holding the lock; returning `keySet` directly would expose a backing collection that can mutate after the method returns.
6. Map read/write operations are approximately O(1) on average, but that **does not** include data loading costs, object allocation, lock contention, or garbage collection across the service.

This is an **entry-count-based LRU cache within a single JVM**. It has no loader, TTL, byte-weight accounting, metrics, or cross-process synchronization. The `synchronized` lock ensures thread safety for individual methods on the class, but does not make multi-step caller sequences atomic.

## 4. Why Is a Working LRU Still Not Enough for Production?

### 4.1. An Entry Limit Is Not a RAM Limit

Three entries could respectively hold 1 KB, 3 KB, and 200 MB. Bounding the cache to three keys does not bound the heap consumed by values, object headers, indexes, strings, or payload copies. For large or highly variable data, configure a **maximum weight** based on the estimated cost of each entry, and add time limits and overall resource budgets appropriate to the context.

Weight is a modeled number (for example, payload byte size); it does not automatically reflect all JVM overhead. You must measure actual heap usage and GC frequency, and tune thresholds in production. Do not treat small example capacities as production configurations.

### 4.2. LRU Does Not Guarantee Data Freshness

Suppose the cache holds Product P with a price of 100. The database updates the price to 120, but users continue calling `get(P)` every second. P remains the most recently used entry under LRU and can live indefinitely while serving an outdated price.

Commonly combined options:
- **Expire-after-write / TTL**: expires after a fixed duration since write or successful load; bounds data age while accepting a staleness window.
- **Invalidation after a successful update**: remove P from the cache when P is updated in the database so the next read loads the fresh version.
- **Version/sequence**: attach a version, ETag, or versioned source of truth; verify when strong consistency is required.
- **Controlled refresh**: asynchronously refresh before or after expiration depending on tolerance for stale data and library support.

**Expiration is not capacity-driven eviction**. An entry may be evicted before its TTL due to capacity pressure; conversely, it may expire even when the cache has plenty of free space. If the data involves access permissions, account balances, or safety rules, even a short TTL may be insufficient: define consistency requirements first.

### 4.3. Thread Safety Does Not Automatically Prevent Cache Stampede

A common error-prone pattern:

```java
// Illustrative snippet: cache and loadFromDatabase are defined elsewhere.
Value value = cache.get(key);
if (value == null) {
    value = loadFromDatabase(key);
    cache.put(key, value);
}
```

Twenty concurrent requests can simultaneously see a miss and query the database twenty times. Even if `get` and `put` are individually `synchronized` as in the demo, **the full `get → load → put` sequence is not atomic**.

Mitigation strategies:
- Coalesce concurrent loads for the same key (single-flight / per-key loading) so multiple requests await a single shared result.
- Configure timeouts, in-flight load limits, bounded retries, and failure policies when the source fails.
- Avoid locking the entire cache during a slow I/O call; use a proper cache loader or concurrent cache implementation.
- Across multiple processes/instances, an in-JVM lock does not stop multiple instances from loading the same key simultaneously. Evaluate a shared cache, distributed lock, or source-level rate limiting if necessary.

A production cache must define how to handle a loader returning null, throwing an exception, timing out, or returning a late result after the underlying data has already been updated.

### 4.4. Per-Key Loading, Negative Caching, and Non-Existent Data

A cache API that only returns null is easily ambiguous: no entry exists, the entry holds a null value, or the data source returned "record not found". For frequently requested keys that do not exist, without **negative caching**, every request hits the database again. If you cache the "not found" state, assign it a separate, typically shorter TTL than normal entries so newly created records do not stay hidden for too long.

Source errors require separate handling: a transient failure does not mean "not found". Do not cache exceptions or unvalidated data as successful lookups by default.

### 4.5. What Data Is Safe to Share?

An in-process memory cache only serves the current process; restarts, scale-out events, or deployments wipe out the local cache. With multiple instances:
- Each instance maintains its own LRU, so hit rates, cached entries, and eviction orders can diverge.
- Invalidation on one instance does not automatically propagate to other instances.
- A shared cache such as Redis can reduce duplicate storage across instances, but introduces network latency, operational overhead, capacity limits, serialization costs, and new failure modes.
- A system can combine a local L1 cache with a shared L2 cache, which then requires refresh and invalidation strategies across both levels.

Cache keys must include every attribute that affects the result: for example, tenant, locale, role/permission group when applicable, version, and filter parameters. **Never cache user-specific data under a key that omits context**, as that causes a data isolation bug rather than just a low hit rate.

### 4.6. Behavior When the Cache or Data Source Fails

A cache is a performance optimization and should not become the sole source of truth for valuable data by default. Explicitly design for:
- On cache miss: which source to load from, timeout duration, maximum retries, and which requests are allowed to wait.
- On cache failure: bypass to the source when safe, serve controlled stale data (only if business rules permit), or return an explicit error.
- On data source failure: whether serving stale data is allowed; stale entries need an absolute maximum age if the data is sensitive.
- When many entries expire simultaneously: add TTL jitter or staggered refreshes to avoid sudden load spikes.
- On data writes: update the DB first and then invalidate the exact key, or apply write-through/write-behind strategies after evaluating data loss risk, operation ordering, and retries.

There is no single fallback policy for every domain: user avatars can be stale for several minutes, whereas transaction limits or access permissions require much stricter guarantees.

## 5. Comparison Table: From an LRU Exercise to a Production Cache

| Aspect | Lesson's LinkedHashMap LRU | Production Cache Requirements and Design Questions |
| --- | --- | --- |
| Goal | Understand access ordering and entry removal | Latency SLAs, source load protection, correctness |
| Capacity | Entry count | Memory cost/weight measurement, heap headroom, GC |
| Eviction | Drop least recently used entry | Choose LRU/LFU/adaptive algorithms by workload; measure effectiveness |
| Expiration | None | TTL, expire-after-access, refresh, jitter |
| Consistency | Disconnected from source updates | Invalidate/version/define acceptable staleness bounds |
| Concurrency | Single `synchronized` lock | Avoid lock contention, coalesce same-key loads, handle races |
| Loading | Caller writes manually | Loader, timeouts, errors, nulls, negative caching |
| Topology | Single JVM | Multiple instances, local/shared/two-level, invalidation |
| Observability | Print key list | Hit/miss, eviction by cause, load time, error, heap, p95/p99 |
| Security | Sample string keys | Tenant isolation, cache key scoping, permissions, sensitive data |
| Lifecycle | Lost when application stops | Warm-up, restart, autoscale, cold start, burst limiting |

This table **does not mean** every feature must be built before using a cache. Choose based on real requirements; a small cache in an internal tool might only need a few constraints and basic metrics.

## 6. Choosing the Right Tool: Custom Implementation, Library, or Shared Cache

**Custom implementation with `LinkedHashMap`** is suitable for learning Collections, running demos, or building a tiny cache with well-defined semantics, low concurrency, and accepted feature trade-offs. In production code, you own every race condition, TTL check, metric, loader, and operational edge case.

**A local caching library like Caffeine** fits when you need an in-JVM cache where capacity management, expiration, loading, statistics, and concurrency are handled by a battle-tested library. The following snippet is an **illustrative API example requiring the Caffeine dependency and a real repository implementation**, and cannot be compiled standalone with just the JDK:

```java
Cache<String, Product> products = Caffeine.newBuilder()
    .maximumSize(10_000)
    .expireAfterWrite(Duration.ofMinutes(5))
    .recordStats()
    .build();

Product product = products.get(id, key -> repository.findById(key));
```

In real code, you must import `Cache`, `Caffeine`, `Duration`, and `Product`, and define how `repository` returns an object, null, or throws an exception. Do not copy `10_000` and `5 minutes` blindly without workload data, memory sizing, and consistency requirements. Caffeine is optimized for **local** caching; it does not automatically synchronize data across JVMs.

**A shared cache like Redis** is useful when multiple instances need to share cached entries or when application heap is unsuitable for holding a large dataset. In exchange, you must manage network hops, serialization, outages, TTLs, RAM pressure, and the shared system's own eviction policy. Do not equate "enabling LRU" in an external cache product with the exact `LinkedHashMap` algorithm from this exercise.

**Not using a cache** can also be the right choice if queries are cheap, data changes constantly, invalidation is complex, hit rates are low, or the cost of serving stale data outweighs the performance savings.

## 7. Measure Effectiveness Instead of Guessing

A cache is evaluated by **system-wide effectiveness**:
- Hit ratio = hits / (hits + misses). Clearly distinguish misses caused by absent, expired, or invalidated entries; guard against division by zero when no reads have occurred.
- Load successes/failures, source access latency, concurrent loading requests, and duplicate loads for the same key.
- Eviction count by cause: capacity, weight, expiration, or manual invalidation if provided by the library.
- Request p50/p95/p99 latency, database QPS, CPU, heap usage, GC pauses, and network traffic if a shared cache is used.
- Actual memory footprint and entry size distribution; ratio of hot keys versus sequential scans.

For example, a 95% hit rate can still be problematic if the remaining 5% of misses arrive concurrently and overwhelm the database; a 70% hit rate might be plenty if misses are cheap and the cache stays simple and maintainable. Measure with realistic workloads, including cold-cache phases and sudden traffic spikes. Detailed benchmarks of map/lock overhead should use tools like JMH rather than un-warmed hand-written microbenchmark loops.

## 8. Verification Practice and Edge Cases

Start by running the program in Section 3, then verify the following test cases. The **Expected** column assumes a cache with capacity = 3 and no TTL.

| Test | Operation Sequence | Expected |
| --- | --- | --- |
| Proper LRU eviction | put(A), put(B), put(C), get(A), put(D) | B is evicted; order is C, A, D |
| Overwrite existing key | put(A), put(B), put(C), put(A, new) | Size does not increase; A becomes most recent |
| Read missing key | put(A), get(X) | Returns null; A remains in cache |
| Invalid input | Create cache with capacity = 0 | Throws IllegalArgumentException |
| Null value | put(A, null) | Throws NullPointerException per demo API contract |
| Capacity bound | Insert 100 distinct keys with capacity = 3 | Size never exceeds 3 |
| Two threads sharing cache | Interleaved reads/writes on one LruCache | Map state is not corrupted thanks to `synchronized`, though final order depends on thread scheduling |

**Extension Exercise 1 – TTL:** Add a maximum age for values and a controllable `Clock`/`Ticker` for testing. Key test case: if an entry is still present in the LRU order but has passed its expiration time, `get` must treat it as a miss. Avoid using `Thread.sleep` to write timing-dependent tests. Clearly decide between expire-after-write and expire-after-access before coding.

**Extension Exercise 2 – Cache Stampede:** Simulate ten concurrent requests querying the same missing key. Count how many times the loader actually executes. Merely synchronizing `get` and `put` individually will not guarantee the loader runs only once. Implement per-key loading and measure the wait time of the other requests.

**Extension Exercise 3 – Weight-Based Sizing:** Replace the entries with three values of vastly different sizes. Demonstrate why `capacity = 3` cannot act as a RAM budget. Design a weight calculation rule and test how an entry larger than the total budget is handled.

**Extension Exercise 4 – Consistency:** Cache a product price, update the database, and read again. Define the requirements: maximum tolerable staleness window, whether an invalidation event exists, how late-arriving events are handled, and whether returning a stale price is allowed when the DB fails.

## 9. Decision Checklist Before Adding a Cache to an Application

1. **Why cache?** Identify the specific bottleneck and the metric you want to improve (latency or source call cost).
2. **What to cache?** Choose keys, values, tenant scoping, and identify data that must not be cached due to privacy or freshness requirements.
3. **Resource limits?** Count entries or weight, set heap/network bounds, and monitor GC behavior.
4. **When does a value become invalid?** Define TTL, invalidation events, versioning, and acceptable staleness.
5. **Who accesses it concurrently?** Single thread, multiple threads, or multiple instances? At what scope are duplicate loads prevented?
6. **What happens on failure?** Decide timeouts, retries, fallbacks, and whether serving stale data is permitted.
7. **Has the benefit been proven?** Test cold/warm caches, concurrent misses, realistic key distributions, and inspect latency/load metrics.

### Conclusion

**LRU answers a narrow question: "When space runs out, which entry should be evicted?"** A production cache must also answer: "Is the data still accurate, how long is it kept, how much RAM does it consume, how is concurrent load handled, and how does the system observe and recover from failures?" `LinkedHashMap` is an excellent tool for understanding access-based eviction; choosing a production caching mechanism must start from workload characteristics and correctness requirements before selecting a library or infrastructure.

## Further Reading

- Java 17 API – LinkedHashMap (insertion-order, access-order, removeEldestEntry): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html
- Caffeine (Java caching library, eviction/expiration policies): https://github.com/ben-manes/caffeine
- Redis eviction policies (memory limits and policy selection): https://redis.io/docs/latest/develop/reference/eviction/
