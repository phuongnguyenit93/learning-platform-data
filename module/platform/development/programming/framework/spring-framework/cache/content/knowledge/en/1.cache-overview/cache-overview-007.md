# Trade-offs Between Speed, Memory, and Data Freshness

In Spring Framework, caching lets many reads be answered from a previously computed or loaded result. In return, the application must retain extra data, may serve older copies, and must manage the lifecycle of those copies. The three goals that often conflict are **response speed**, **memory usage**, and **data freshness**. Good cache design begins by deciding how stale each piece of data is allowed to be, and only then choosing cache size and expiration policies.

## 1. How Does Caching Change the Read Flow?

With the **application-layer cache-aside/read-through** pattern commonly seen with Spring Cache:

1. A read request enters a method annotated with **@Cacheable**.
2. Spring derives a key from the parameters and queries the cache configured via **CacheManager**.
3. On a **hit**, Spring returns the stored data, usually skipping the method body.
4. On a **miss**, the method reads from the database/origin service; eligible results are stored in the cache for subsequent calls.
5. When source data changes, the cache may continue holding the old version until updated, evicted, or expired.

~~~text
Client ──> Spring @Cacheable ──> Cache lookup
                                    ├── HIT  ──> Cached copy ──> Client
                                    └── MISS ──> Data source ──> Store in cache ──> Client

Write ──> Data source changes ──> Needs cache invalidation/update strategy
~~~

**Spring Cache is an abstraction over cache operations**, not a storage engine with fixed TTL, capacity, or synchronization semantics. Those policies are handled by providers such as Caffeine, Redis, or another backend. Consequently, the exact same annotation can exhibit different latency, memory, and consistency characteristics depending on actual configuration.

## 2. The Three Axes of Trade-offs

| Axis | Benefit When Optimized | Associated Cost/Risk |
| --- | --- | --- |
| **Speed** | Fast hits; fewer DB queries, network calls, and CPU work; lower load on origin systems | Requires extra RAM/storage space; refreshing, syncing, and measuring carry overhead |
| **Memory** | Retains more hot keys, typically raising the hit ratio | Increases heap, GC, or Redis cost; may hold rarely used data |
| **Freshness** | Short TTL or eager invalidation shrinks the window during which stale data exists | Increases misses, reloads, and DB pressure; distributed invalidation can be complex |

An estimate for a uniform read path:

~~~text
Average latency ≈ hitRatio × latencyHit + (1 − hitRatio) × latencyMiss
~~~

Suppose 90% of reads hit at 2 ms and 10% miss at 80 ms: the average is roughly **9.8 ms**. This is a hypothetical illustration, not a performance forecast. In real evaluations, you must also factor in lookup time, serialization, network, tail distribution **p95/p99**, concurrency, key churn rate, and origin latency under increased load.

Memory must also be calculated as **keys + values + metadata/overhead + related buffers**. For example, 100,000 values averaging 2 KiB equal nearly 195 MiB *for payload alone*, before counting Java objects, cache metadata, and replicas across multiple instances. Caffeine's **maximumSize** is an entry count limit, not a byte limit. If entry sizes vary widely, consider **maximumWeight** with an appropriate weigher and measure actual heap usage.

## 3. Why Does Increasing Speed Often Reduce Freshness?

Suppose at **10:00:00** an API reads a product price of 100 from the DB and caches it with **expireAfterWrite = 5 minutes**. At **10:00:01**, another system updates the DB price to 120. Without cache invalidation/updates, reads before the entry expires can still return 100. TTL does not monitor when the DB is updated. With write-based expiration, a source change immediately after population can keep the old copy alive for nearly the entire TTL cycle.

Lowering TTL to 10 seconds narrows the potential stale window, but also forces more entries to reload; if thousands of hot keys expire together, misses can spike suddenly. Increasing TTL to 30 minutes usually keeps data cached longer and reduces origin calls, but increases the risk of serving old copies.

Distinguish clearly:

- **Freshness**: the result is recent enough for business requirements; e.g., a leaderboard may lag by 1 minute.
- **Staleness**: how far behind the authoritative source state it is; measure both *entry age* and *update propagation lag*.
- **Expiration/TTL**: rule whereby an entry is no longer used after a duration calculated by the provider. This is not an instant-consistency guarantee.
- **Eviction**: removing an entry due to expiration, exceeding capacity, or explicit command; an entry can be evicted before its TTL.
- **Invalidation**: removing copies that are no longer trustworthy when source data changes.
- **Refresh**: fetching fresh data to replace an old copy; depending on the provider, stale values may still be served while refreshing.

In Caffeine, **expireAfterWrite** is measured from entry creation/update; **expireAfterAccess** is measured from the most recent access, so a continuously read entry can stay alive very long if using expire-after-access alone. **refreshAfterWrite** applies to a loading cache with a reload mechanism; once eligible by age, refresh is typically triggered on access and may return the old value while loading the new one. Do not assume setting a refresh parameter on a plain Spring annotation automatically enables stale-while-revalidate.

## 4. Key Tuning Knobs

| Decision | Typically Improves | What to Verify |
| --- | --- | --- |
| Increase capacity / keep more hot keys | Raises hit ratio, lowers origin load | RAM/heap, GC, cost, whether incremental gain is worthwhile |
| Lower capacity or apply size-based eviction | Caps memory cost | Misses from evicting hot keys; whether the origin can handle them |
| Long TTL | Reduces reloads | Whether the stale window after source updates is acceptable |
| Short TTL | Shrinks how long stale data is kept | Lower hit ratio, cache stampede risk, and higher DB load |
| Invalidate on successful write | New values become visible sooner | Any missed write paths, race conditions, or other nodes |
| Proactive warming / preloading | Reduces cold misses after startup | Memory spike and initial startup load burst |
| Background refresh / provider-supported stale-while-revalidate | Lowers read latency during refresh | Whether serving stale data during refresh is acceptable |
| Limit key cardinality, avoid huge entries | Saves memory and serialization | Whether genuinely hot access patterns are dropped |

**There is no "standard" TTL for every cache.** A good value depends on source update rate, user tolerance for staleness, read frequency, result size, and behavior when the cache/DB fails.

## 5. Local Cache, Distributed Cache, and Impact on the Three Axes

| Criterion | In-Process Caffeine in Spring | Shared Redis |
| --- | --- | --- |
| Hit read path | In JVM memory, usually very fast | Over network connection + serialization, usually adds latency |
| Capacity | From each instance's heap/budget | From Redis memory and infrastructure configuration |
| Multiple instances | Each JVM has its own copy and eviction policy | Multiple instances can share a single cached dataset |
| Freshness when one node updates source | Evicting on that node does not evict other nodes | Evicting the shared key improves consistency, though write ordering and races still need handling |
| Operations | Simple, but GC/heap pressure | Adds network, availability, monitoring, serializers, and security |

For example, a service with **4 replicas** where each replica retains up to 10,000 Caffeine entries: that limit is **10,000 per instance**, not 10,000 cluster-wide. The same key can exist in all 4 places. If one replica updates the DB and clears only its local cache, the remaining three replicas can still return the old version until their TTL expires. When changes must propagate cluster-wide, consider a shared cache or invalidation messages processed by every replica; both require testing races, dropped messages, and network failures.

Multi-tier caching (local Caffeine in front of Redis) can reduce latency further, yet introduces extra copies and harder invalidation. Use it only when measured benefits outweigh the complexity.

## 6. Spring Framework Illustration with Caffeine

The example below illustrates an **initial policy for experimentation**: up to 10,000 entries for a product-details cache, each expiring 2 minutes after write. The project needs compatible Spring Cache / Spring Context Support and Caffeine libraries; in a Spring Boot app you can use the cache starter and Caffeine dependencies. The code snippets are components of a Spring application that already has DI/repository setup, **not a standalone Java program**.

~~~java
// CacheConfiguration.java
package demo.cache;

import com.github.benmanes.caffeine.cache.Caffeine;
import java.time.Duration;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheConfiguration {
    @Bean
    public CacheManager cacheManager() {
        CaffeineCacheManager manager = new CaffeineCacheManager("productDetails");
        manager.setCaffeine(Caffeine.newBuilder()
                .maximumSize(10_000)
                .expireAfterWrite(Duration.ofMinutes(2))
                .recordStats());
        return manager;
    }
}
~~~

~~~java
// ProductService.java
package demo.cache;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductService {
    private final ProductGateway gateway;

    public ProductService(ProductGateway gateway) {
        this.gateway = gateway;
    }

    @Cacheable(cacheNames = "productDetails",
               key = "#id", unless = "#result == null")
    public ProductView findById(String id) {
        return gateway.load(id);
    }

    @CacheEvict(cacheNames = "productDetails", key = "#id")
    public void changePrice(String id, long newPriceInCents) {
        gateway.changePrice(id, newPriceInCents);
    }
}

// Application domain types; gateway requires an actual implementation.
interface ProductGateway {
    ProductView load(String id);
    void changePrice(String id, long newPriceInCents);
}
record ProductView(String id, long priceInCents) {}
~~~

Role of each part:

1. **@EnableCaching** enables annotation processing through Spring's mechanism; adding annotations without enabling caching creates no cache.
2. **@Cacheable** skips loading from the gateway when the key is present. **unless** avoids storing null results in this example. A key must cover every factor affecting the result, such as locale/tenant/permission where applicable.
3. **maximumSize(10_000)** caps Caffeine's entry count; inspect actual object sizes to estimate the RAM budget.
4. **expireAfterWrite(2 minutes)** limits entry age in the cache, but does not guarantee the data remains valid throughout those 2 minutes.
5. **@CacheEvict** removes the corresponding entry **after the method completes normally** by default. With DB transactions, commit and eviction order must be designed explicitly to avoid cases where the cache is cleared and another thread reloads uncommitted DB data and caches it; consider post-commit invalidation.
6. **recordStats()** tells Caffeine to collect internal stats; exposing them to an observability system requires wiring a suitable metrics tool. This call alone does not provide a dashboard.

This example is not meant to guarantee instant updates everywhere, especially with multiple replicas or alternative write paths bypassing `ProductService`. If checkout requires an authoritative up-to-the-second price, verify the price at the source during order finalization rather than trusting a display cache.

**Spring proxy note:** In standard proxy mode, calling a **@Cacheable** method from another method inside the same object (**self-invocation**) bypasses the proxy and does not trigger caching. **@Cacheable(sync = true)** can reduce duplicate loads for the same key on concurrent misses if supported by the provider, but has limitations when combined with other annotations/**unless** conditions; do not treat it as a system-wide distributed lock.

## 7. Self-Contained Java 17 Program: Stale Copies, TTL, and Invalidation

This is a small model **without Spring** to isolate the core mechanics. A virtual clock lets us deterministically reproduce reads without waiting 60 seconds. The code illustrates only one key and lacks capacity limits or thread safety of a real cache.

~~~java
// CacheTradeoffDemo.java
import java.util.HashMap;
import java.util.Map;

public class CacheTradeoffDemo {
    private record Entry(int price, long expiresAtMs) {}

    private static long nowMs = 0;
    private static int databasePrice = 100;
    private static final Map<String, Entry> cache = new HashMap<>();

    private static String readPrice() {
        Entry item = cache.get("product-1");
        if (item != null && nowMs < item.expiresAtMs()) {
            return item.price() + " (hit)";
        }
        cache.put("product-1", new Entry(databasePrice, nowMs + 60_000));
        return databasePrice + " (miss)";
    }

    public static void main(String[] args) {
        System.out.println("1: " + readPrice());
        System.out.println("2: " + readPrice());

        databasePrice = 120;              // Source changed, cache does not know yet.
        System.out.println("3: " + readPrice());

        nowMs = 61_000;                   // Past the 60-second TTL.
        System.out.println("4: " + readPrice());

        databasePrice = 140;
        cache.remove("product-1");        // Invalidate immediately upon writing to source.
        System.out.println("5: " + readPrice());
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac CacheTradeoffDemo.java
java CacheTradeoffDemo
~~~

Expected output:

~~~text
1: 100 (miss)
2: 100 (hit)
3: 100 (hit)
4: 120 (miss)
5: 140 (miss)
~~~

Call 3 returns **100 even though the DB is already 120** because the cache has not expired. Call 4 gets 120 because the 60-second TTL elapsed. Call 5 gets 140 immediately after invalidation, at the cost of loading from the source once more. This model illustrates clearly: the more data is reused, the fewer misses occur, yet copies can lag behind updates without refresh rules.

## 8. Choosing Policies by Data Characteristics

| Data / Scenario | Freshness Requirement | Design Direction to Try | Warning |
| --- | --- | --- | --- |
| Rarely changing catalog, introductory content | Tolerates a few minutes of lag | Few-minute TTL, cache sized for hot keys, evict when CMS updates | Do not pick TTL by guesswork; check content edit frequency |
| Near-real-time leaderboards / analytics | Tolerates defined publication lag | Periodic refresh, snapshot versioning, or suitable TTL | Clearly display update timestamp to users |
| Product detail page | Tolerates brief staleness | Read cache + evict on price/info edit | Write paths outside the app must also invalidate |
| Inventory, quotas, access rights, checkout price | May require current data | Skip cache on critical decisions or re-verify at source | A short TTL does not turn a cache into strong consistency |
| Large data, keys rarely repeat | Low hit opportunity | Do not cache, or cap strictly and filter cached objects | Storing everything wastes RAM without meaningful load reduction |

A design can use **two different read paths for the same data**: product display can read from cache for speed, whereas placing an order confirms price and inventory from the transactional source. This is usually better than forcing a single TTL to fit every business workflow.

## 9. Measure Then Tune: A Constrained Optimization Problem

Before changing TTL or capacity, define four things:

- **Latency target** (e.g., endpoint p95 and origin query p95), not just averages.
- **Freshness budget**: maximum acceptable lag per data type and read path. If exact post-commit data is required, TTL alone is insufficient.
- **Memory budget**: heap limit per instance or Redis RAM, including overhead and replication cost; set alerts before reaching the threshold.
- **Traffic/update pattern**: hot/cold key distribution, write frequency, peak load, replica count, and behavior when DB/cache fails.

Metrics to monitor: **hit/miss ratio per cache**, eviction counts and causes, entry/heap size, GC pauses, hit/miss latency and p95/p99, origin request rate, concurrent cache reloads, time for updates to become visible, failed refreshes, and Redis/network usage if applicable. A high hit ratio alone does not prove a good cache if the system returns wrong data or consumes too much RAM.

Suggested experimental workflow:

1. Measure baseline **without cache**: latency, DB QPS, CPU load, and memory.
2. Choose proper keys and cacheable datasets; exclude consistency-sensitive data from stale read paths.
3. Set an initial **budget**, e.g., max 10,000 entries and 2-minute TTL, then run representative load.
4. Vary **one variable at a time**: TTL 30s → 2m → 5m, or capacity 2,000 → 10,000, always checking both latency and staleness.
5. Simulate source updates right after cache fill, heavy concurrent writes, cold caches on deployment, multiple instances, and disconnected cache providers.
6. Finalize configuration based on business requirements and SLOs; re-evaluate whenever traffic patterns shift.

**Example decision with hypothetical numbers:** A product-detail read API targets p95 under 50 ms, allows up to 2 minutes of update lag on the view screen, and has a 256 MiB cache heap budget per replica. You might try Caffeine with **expireAfterWrite = 2 minutes**, capacity bounded by measured heap, plus **@CacheEvict** on the main write path. Then verify experimentally that hot keys fit within memory limits, p95 meets the target, and every product-edit path has a refresh mechanism. Do not assume an example config automatically hits those numbers.

## 10. Common Mistakes and Self-Check Questions

- **"With a long TTL, data is always fresh during the TTL."** False: TTL only bounds cache entry lifetime; the source can change right after cache fill.
- **"maximumSize = 10,000 means fixed RAM."** False: the value is an entry count; actual footprint depends on key/value types and overhead.
- **"@CacheEvict on one replica clears staleness across the cluster."** False for independent local caches. You need a cross-node strategy or a shared cache store.
- **"The higher the hit ratio, the better."** Insufficient: simultaneously inspect p95, origin load, memory budget, and correctness.
- **"Enabling refresh always returns fresh results."** Not guaranteed: some refresh modes return the old copy while loading the new one; behavior depends on the provider and integration.
- **"Caching any method's result is safe."** False: methods depending on time, session, tenant, permissions, or out-of-band state easily produce wrong keys and leak results across contexts.
- **"Enabling caching solves every traffic spike."** False: concurrent misses, cold starts, hot keys, and synchronized TTL expirations can trigger a **cache stampede**; consider limiting concurrent loads, warming, and jittering expiration times.

Answer three questions for yourself before picking a policy: **(1)** How stale is this data allowed to be? **(2)** How much will 1 GiB more cache raise hit ratio on real traffic? **(3)** Once the source changes, which read paths must see the new version immediately, and who owns invalidation? If you lack measured answers yet, start small, measure, and iterate.

### Official Documentation for Deeper Reading

- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Cache annotations and proxy mechanics: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Provider-dependent TTL and eviction: https://docs.spring.io/spring-framework/reference/integration/cache/specific-config.html
- Caffeine — Eviction/Expiration: https://github.com/ben-manes/caffeine/wiki/Eviction
- Caffeine — Refresh: https://github.com/ben-manes/caffeine/wiki/Refresh
- Spring Data Redis — TTL/TTI for Redis Cache: https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html