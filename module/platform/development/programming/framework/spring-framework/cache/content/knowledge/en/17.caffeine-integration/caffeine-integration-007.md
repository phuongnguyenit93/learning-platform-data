# Registering Custom Caches with Dedicated Configurations — Spring Cache and Caffeine

## Objectives

This lesson belongs to the **Caffeine Integration** group in Spring Framework Cache. After this lesson, you will be able to:

1. Explain why each **cache region** may need different policies for TTL, capacity, and statistics.
2. Register dedicated Caffeine caches using `CaffeineCacheManager.registerCustomCache(name, nativeCache)`, combined with caches using the manager's **shared configuration**.
3. Distinguish `setCaffeine(...)`, `setCacheNames(...)`, `registerCustomCache(...)`, region names in `@Cacheable`, and keys inside a region.
4. Run a Java 17+ Spring Boot example having three caches with TTLs of **5 seconds, 40 seconds, and 30 seconds** respectively; verify the results using a simulated clock instead of `Thread.sleep`.
5. Recognize pitfalls around dynamic region creation, configuration ordering, nulls, keys, concurrency, memory bounds, transactions, and multiple replicas.

**Core idea:** `CaffeineCacheManager` has a **default configuration** used to build ordinary caches. When certain regions need dedicated policies, you **register the custom-built Caffeine cache instances themselves** per name via `registerCustomCache`. There is no need to duplicate an entire `CacheManager` just because two regions have different TTLs.

## 1. Why Does an Application Need Multiple Cache Policies?

Consider an e-commerce system with these data types:

| Cache region | Data type | Illustrative requirement |
| --- | --- | --- |
| `prices` | Frequently changing display prices | Short TTL, moderate entry cap |
| `productDetails` | Rarely changing product details | Longer TTL, more entries |
| `categories` | Small, stable category list | Shared default policy, invalidation on update |
| `searchResults` | Results by filter/sort/page | Composite key, dedicated capacity and TTL |

If all caches used one builder `expireAfterWrite(10 minutes).maximumSize(1_000)`, two issues could arise: prices are too stale due to a long TTL, and product details reload too often due to a short TTL. Per-region configuration defines the right **freshness contract and memory budget** for each data type.

Structurally:

~~~text
                   Spring Cache annotations
                              |
                         CacheManager
                              |
                   CaffeineCacheManager
              /---------------+----------------\
             /                |                 \
       prices            productDetails        categories
       custom Cache      custom Cache          default Cache
       TTL = 5 s         TTL = 40 s            TTL = 30 s
       max = 100         max = 1,000           max = 500
             |                |                 |
       key -> value      key -> value         key -> value
~~~

These numbers are for demonstration only, not real-world production TTL recommendations. **Each region** has its own namespace: the same key `"42"` in `prices` and `productDetails` does not refer to the same entry.

## 2. Essential APIs

`org.springframework.cache.caffeine.CaffeineCacheManager` is the adapter from **Spring Cache abstraction** to Caffeine. Three methods are commonly combined:

### 2.1. Shared Configuration: setCaffeine

~~~java
manager.setCaffeine(
        Caffeine.newBuilder()
                .maximumSize(500)
                .expireAfterWrite(Duration.ofSeconds(30)));
~~~

The code above only illustrates usage assuming an existing `manager` variable and imports for `Caffeine` and `Duration`. Caches **created automatically by the manager via the shared mechanism** use this builder. Configuring `setCaffeine` does **not overwrite builders of manually registered native Caffeine caches**.

Other methods serving the same shared purpose include `setCacheSpecification(...)` and `setCaffeineSpec(...)`; pick one consistent configuration method and avoid overwriting settings from multiple sources.

### 2.2. Declaring Default Region Names: setCacheNames

~~~java
manager.setCacheNames(List.of("categories"));
~~~

When given a collection of region names, `CaffeineCacheManager` switches to **static** mode for manager-created regions; calling `getCache("typo")` for a name that does not exist and was not custom-registered returns `null` instead of auto-creating a new cache. This helps catch cache name typos.

**Do not confuse:** `setCacheNames` accepts **region names**, not `Caffeine Cache` instances. It is not an API for setting per-name TTLs.

### 2.3. Registering a Dedicated Cache: registerCustomCache

~~~java
com.github.benmanes.caffeine.cache.Cache<Object, Object> fast =
        Caffeine.newBuilder()
                .expireAfterWrite(Duration.ofSeconds(5))
                .maximumSize(100)
                .build();

manager.registerCustomCache("prices", fast);
~~~

Here, you **build a native `com.github.benmanes.caffeine.cache.Cache`** and pass it to the manager under the name `prices`. Spring exposes it via `CacheManager.getCache("prices")` wrapped as a Spring `Cache` adapter. Multiple custom regions can be registered, each with its own builder.

This API has existed in Spring Framework since **5.2.8** for native synchronous Caffeine `Cache<Object,Object>`. Newer Spring Framework versions also offer an overload accepting Caffeine `AsyncCache<Object,Object>` (since Spring 6.1), though this demo uses the **synchronous** path to avoid mixing async semantics.

The API documentation clearly notes: custom caches operate alongside caches created from the shared configuration; caches created for regular names or dynamically later still use the manager's shared configuration.

### 2.4. Three Layers to Distinguish

| Component | Example | Responsibility |
| --- | --- | --- |
| Spring `CacheManager` | `CaffeineCacheManager` | Looks up/creates cache regions by name |
| Spring `Cache` adapter | `manager.getCache("prices")` | Unified `get/put/evict/clear` API |
| Native Caffeine `Cache` | `Caffeine.newBuilder()...build()` | Enforces TTL/size/eviction/concurrency in the backend |

When `@Cacheable(cacheNames = "prices", key = "#p0")` runs, the annotation **does not create its own builder**. Spring looks up the `prices` region on the manager; that region is already bound to the native cache you registered.

## 3. When Is a Custom Cache Needed Instead of One Global Configuration?

Three common scenarios:

- **Different freshness needs:** prices may be cached for 5–30 seconds, while product details stay stable longer.
- **Different sizes:** search caches with many keys grow quickly and need tighter `maximumSize` than small category lists.
- **Different eviction/expiry policies:** one region suits `expireAfterWrite`, another needs `expireAfterAccess` or per-entry `Expiry`, or only certain regions need `recordStats()`.

Note: `maximumSize(n)` roughly caps **entry count**; it does not guarantee each cache uses less than a fixed byte amount of RAM. If value sizes vary significantly, consider `maximumWeight` with a `weigher`. The term "TTL" in this lesson mainly refers to `expireAfterWrite`; `expireAfterAccess` is *time-to-idle* and extends upon eligible accesses.

Do not pick TTLs merely because the numbers look "nice." TTLs must be chosen based on acceptable staleness, update frequency, data loading cost, key creation rate, replica count, and memory limits.

## 4. Runnable Spring Boot Example: Three Regions, Three TTLs

This example uses Java 17+, Spring Boot with Gradle, and no real database. To **verify TTLs accurately** without waiting real wall-clock time, we create a `ManualTicker`. Caffeine supports swapping the time source via `Ticker`, so advancing by 6 seconds in the demo causes Caffeine to observe that time has elapsed.

Desired configuration:

| Region name | Creation method | Write TTL | maximumSize |
| --- | --- | --- | --- |
| `shortItems` | `registerCustomCache` | 5 seconds | 100 |
| `longItems` | `registerCustomCache` | 40 seconds | 1,000 |
| `defaultItems` | `setCacheNames` + `setCaffeine` | 30 seconds | 500 |

In an existing Spring Boot Gradle project configured with Java 17+-compatible plugins/versions, these two dependencies are required (letting Spring Boot dependency management control versions):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'com.github.ben-manes.caffeine:caffeine'
}
~~~

Four Java files reside in the same package `example.caffeinecustom`.

### 4.1. ManualTicker.java — Simulated Clock

Create `src/main/java/example/caffeinecustom/ManualTicker.java`:

~~~java
package example.caffeinecustom;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicLong;

import com.github.benmanes.caffeine.cache.Ticker;

public final class ManualTicker implements Ticker {
    private final AtomicLong nanos = new AtomicLong();

    @Override
    public long read() {
        return nanos.get();
    }

    public void advance(Duration duration) {
        if (duration.isNegative()) {
            throw new IllegalArgumentException(
                    "duration must not be negative");
        }
        nanos.addAndGet(duration.toNanos());
    }
}
~~~

Caffeine calls `Ticker.read()` (in nanoseconds) to evaluate TTLs. Here `nanos` starts at 0 and advances on test demand. In production, **do not use a manual ticker**; let Caffeine use its default monotonic clock.

### 4.2. CacheConfiguration.java — Registering Custom Caches

Create `src/main/java/example/caffeinecustom/CacheConfiguration.java`:

~~~java
package example.caffeinecustom;

import java.time.Duration;
import java.util.List;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfiguration {

    @Bean
    ManualTicker manualTicker() {
        return new ManualTicker();
    }

    @Bean
    CacheManager cacheManager(ManualTicker ticker) {
        CaffeineCacheManager manager = new CaffeineCacheManager();

        // SHARED configuration for regions created by the manager itself.
        manager.setAllowNullValues(false);
        manager.setCaffeine(Caffeine.newBuilder()
                .ticker(ticker)
                .maximumSize(500)
                .expireAfterWrite(Duration.ofSeconds(30)));

        // Static mode for shared regions; unregistered cache names
        // will not be auto-created when calling getCache(name).
        manager.setCacheNames(List.of("defaultItems"));

        // Custom #1: short TTL and dedicated max entry count.
        com.github.benmanes.caffeine.cache.Cache<Object, Object> fast =
                Caffeine.newBuilder()
                        .ticker(ticker)
                        .maximumSize(100)
                        .expireAfterWrite(Duration.ofSeconds(5))
                        .build();
        manager.registerCustomCache("shortItems", fast);

        // Custom #2: longer TTL and larger capacity.
        com.github.benmanes.caffeine.cache.Cache<Object, Object> longLived =
                Caffeine.newBuilder()
                        .ticker(ticker)
                        .maximumSize(1_000)
                        .expireAfterWrite(Duration.ofSeconds(40))
                        .build();
        manager.registerCustomCache("longItems", longLived);

        return manager;
    }
}
~~~

**Why this configuration order?**

1. Create the manager.
2. `setCaffeine` declares the default builder; when the manager creates `defaultItems`, it applies the default policy.
3. `setCacheNames` declares the shared region and locks down auto-creating arbitrary unlisted names. This region-name contract **does not replace** custom caches registered afterward.
4. `registerCustomCache` accepts two **already-built** native caches with dedicated 5-second and 40-second TTLs. These two regions are not forced onto the 30-second TTL of the default builder.

All caches share one `ManualTicker` so demo output stays deterministic. To avoid type confusion, the example uses the fully qualified `com.github.benmanes.caffeine.cache.Cache<Object,Object>` for native caches and `org.springframework.cache.CacheManager` for the Spring manager.

**What to verify:** calling `manager.getCache("shortItems")` or `"longItems"` resolves the registered custom cache; `getCache("defaultItems")` resolves the default region; `getCache("unknown")` returns `null` under this static-mode setup.

### 4.3. CatalogService.java — Three Methods Using the Same Key

Create `src/main/java/example/caffeinecustom/CatalogService.java`:

~~~java
package example.caffeinecustom;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final AtomicInteger shortLoads = new AtomicInteger();
    private final AtomicInteger longLoads = new AtomicInteger();
    private final AtomicInteger defaultLoads = new AtomicInteger();

    @Cacheable(cacheNames = "shortItems", key = "#p0")
    public String shortItem(String id) {
        int n = shortLoads.incrementAndGet();
        System.out.println("LOAD short #" + n);
        return "S-" + n;
    }

    @Cacheable(cacheNames = "longItems", key = "#p0")
    public String longItem(String id) {
        int n = longLoads.incrementAndGet();
        System.out.println("LOAD long #" + n);
        return "L-" + n;
    }

    @Cacheable(cacheNames = "defaultItems", key = "#p0")
    public String defaultItem(String id) {
        int n = defaultLoads.incrementAndGet();
        System.out.println("LOAD default #" + n);
        return "D-" + n;
    }
}
~~~

All three methods use key `"K1"` in the demo, yet they target **three different regions**, so loading and TTLs are independent. Strings `S-1`, `L-1`, `D-1` indicate **method-body execution counts**, not database values.

`@Cacheable` uses a Spring proxy: on hits, the method body does not run and counters do not increment. On misses due to TTL, the method runs and stores a new value. Calls come from another Spring bean (`CommandLineRunner`), avoiding self-invocation.

### 4.4. CustomCacheDemoApplication.java — Verifying with Simulated Time

Create `src/main/java/example/caffeinecustom/CustomCacheDemoApplication.java`:

~~~java
package example.caffeinecustom;

import java.time.Duration;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CustomCacheDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CustomCacheDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(
            CatalogService catalog,
            CacheManager manager,
            ManualTicker ticker) {

        return args -> {
            System.out.println("known = " +
                    (manager.getCache("shortItems") != null
                     && manager.getCache("longItems") != null
                     && manager.getCache("defaultItems") != null));
            System.out.println("unknown = " +
                    (manager.getCache("notRegistered") == null));

            // T = 0 seconds; all three regions miss initially.
            System.out.println("short@0 = " +
                    catalog.shortItem("K1"));
            System.out.println("long@0 = " +
                    catalog.longItem("K1"));
            System.out.println("default@0 = " +
                    catalog.defaultItem("K1"));
            System.out.println("short@0 again = " +
                    catalog.shortItem("K1"));

            // T = 6 seconds: only shortItems (5s TTL) has expired.
            ticker.advance(Duration.ofSeconds(6));
            System.out.println("short@6 = " +
                    catalog.shortItem("K1"));
            System.out.println("long@6 = " +
                    catalog.longItem("K1"));
            System.out.println("default@6 = " +
                    catalog.defaultItem("K1"));

            // T = 31 seconds: default has expired; long has not.
            ticker.advance(Duration.ofSeconds(25));
            System.out.println("short@31 = " +
                    catalog.shortItem("K1"));
            System.out.println("long@31 = " +
                    catalog.longItem("K1"));
            System.out.println("default@31 = " +
                    catalog.defaultItem("K1"));

            // T = 41 seconds: long (40s from T=0) has expired;
            // default reloaded at T=31 so it is still valid.
            ticker.advance(Duration.ofSeconds(10));
            System.out.println("long@41 = " +
                    catalog.longItem("K1"));
            System.out.println("default@41 = " +
                    catalog.defaultItem("K1"));
        };
    }
}
~~~

Run from the project directory:

~~~bash
./gradlew bootRun
# Windows PowerShell: .\gradlew.bat bootRun
~~~

**Lines printed by `System.out` in exact order**, excluding Spring Boot/Gradle logs:

~~~text
known = true
unknown = true
LOAD short #1
short@0 = S-1
LOAD long #1
long@0 = L-1
LOAD default #1
default@0 = D-1
short@0 again = S-1
LOAD short #2
short@6 = S-2
long@6 = L-1
default@6 = D-1
LOAD short #3
short@31 = S-3
long@31 = L-1
LOAD default #2
default@31 = D-2
LOAD long #2
long@41 = L-2
default@41 = D-2
~~~

**Stage-by-stage interpretation:**

- **T = 0:** each region misses key `K1` once; the second `shortItem("K1")` hits so no extra `LOAD short` prints.
- **T = 6:** `shortItems["K1"]` created at T=0 exceeded 5 seconds, reloading `S-2`. `longItems` (40 seconds) and `defaultItems` (30 seconds) still hit, keeping `L-1` and `D-1`.
- **T = 31:** `shortItems` created at T=6 also exceeded 5 seconds, reloading `S-3`; `longItems` keeps `L-1` since only 31 seconds elapsed from T=0; `defaultItems` exceeded 30 seconds and reloads `D-2`.
- **T = 41:** `longItems` created at T=0 exceeded 40 seconds, reloading `L-2`. `defaultItems` was reloaded at T=31, so its age of 10 seconds is under its 30-second TTL and it hits, still returning `D-2`.

**Why can the output be verified deterministically?** The caches share `ManualTicker` and calls execute sequentially inside `CommandLineRunner`. On a fresh startup, counters and the ticker both start at 0. The provider checks expiration on lookup: expired entries are never returned even if physical cleanup runs later. This demo has **four Java classes in a Spring Boot application**, requiring Gradle/Spring dependencies; it is not a single file runnable with plain `javac`.

## 5. Where Do Custom Caches Truly Differ from Default Caches?

In the code above:

~~~java
manager.setCaffeine(Caffeine.newBuilder()
        .maximumSize(500)
        .expireAfterWrite(Duration.ofSeconds(30)));

manager.setCacheNames(List.of("defaultItems"));

manager.registerCustomCache("shortItems",
        Caffeine.newBuilder()
                .maximumSize(100)
                .expireAfterWrite(Duration.ofSeconds(5))
                .build());
~~~

This is an **abbreviated illustrative snippet**, omitting `Ticker`; in the program in section 4, all builders receive the same ticker for testing.

What happens:

1. `defaultItems` is created by the manager using the shared builder; 30-second TTL, max 500.
2. `shortItems` is supplied to the manager as **a native Caffeine cache with its own builder**; 5-second TTL, max 100.
3. If the manager is configured in **dynamic** mode instead of static mode, a new non-custom name may be created on lookup, yet it still uses the **shared** builder and never infers a custom TTL by name. 
4. Keeping `setCacheNames` in static mode prevents unregistered names from being created accidentally, helping catch configuration mistakes.
5. Every annotation using `cacheNames` must match the registered name exactly, e.g., `"shortItems"` differs from `"shortItem"`.

This approach fits best when most caches share one default policy and only a few regions need overrides. If **every** region has its own policy, you can still register each cache individually, but centralize the policy registry to avoid scattering copy-pasted configuration.

## 6. Advanced Configuration Scenarios

### 6.1. expireAfterWrite and expireAfterAccess

~~~java
Caffeine.newBuilder()
        .expireAfterWrite(Duration.ofMinutes(5));
~~~

Entries expire based on time elapsed since creation or the last **write/replacement**. Normal hit lookups do not automatically extend this deadline.

~~~java
Caffeine.newBuilder()
        .expireAfterAccess(Duration.ofMinutes(5));
~~~

Entries expire when unaccessed for the duration; eligible accesses extend the lifetime (*time-to-idle*). Do not use `expireAfterAccess` for data requiring a fixed **maximum age** that continuous requests must not extend.

When per-entry custom TTLs are needed, Caffeine also supports `expireAfter(Expiry<K,V>)`. This belongs in the Caffeine builder/implementation, not as a generic `ttl=...` parameter on `@Cacheable`.

### 6.2. Size Eviction Is Not the Same as TTL

~~~java
Caffeine.newBuilder()
        .maximumSize(1_000)
        .recordStats();
~~~

`maximumSize` bounds the entry count in the region, but does not govern entry lifetime. The backend can evict entries to stay within capacity even before their TTL expires. In practice, victim selection follows Caffeine's policy, not simply "remove the least recently read key" in every case.

`recordStats` helps measure hits/misses/evictions; to read metrics from the native cache, retain a reference to the instance or use an integrated metrics system (such as Micrometer/Actuator when configured). **The manager does not automatically publish histograms or dashboards merely by calling `recordStats()`.**

### 6.3. Caching Null

Native Caffeine `Cache` does not accept `null` values. Spring's `CaffeineCacheManager` normally supports translating null into a sentinel via `allowNullValues`; when `setAllowNullValues(false)` is set as in the demo, a method returning `null` can throw an error when caching is attempted. That was intentional in the demo because all three loaders always return non-null strings.

If the business domain allows "not found," define **negative caching** explicitly: whether null is stored, for how long, and whether it is evicted when the record is created. Never assume all regions share the same null policy when custom adapters differ, and never use null policies as an authorization mechanism.

### 6.4. Synchronization and Cache Stampede

`@Cacheable(sync = true)` can coordinate loads for the same key if supported by the implementation. However, that does not become a **distributed** lock across replicas/JVMs. An in-memory Caffeine cache is **local**; three app instances on three JVMs have three independent caches, even with identical region names and TTLs.

When many entries expire at the same time, the backend can suffer a surge of misses and source queries. Mitigations include TTL jitter, request coalescing, warmup, concurrency limits, or a distributed cache, depending on requirements.

### 6.5. Data Mutations and Consistency

Custom TTLs do not know when the database changes. After updates/deletes, the application may still need `@CacheEvict(cacheNames="...", key="...")`, `@CachePut`, or event-based invalidation. A single update method might affect **multiple regions**; evicting `shortItems` does not automatically evict `longItems`.

If eviction executes before database commit, another request can reload stale data. There is no default atomic transaction spanning the database and Caffeine memory. For strict requirements, design after-commit invalidation, versioned values, or domain-level consistency checks.

### 6.6. Keys and Mutability

Custom TTLs do not fix broken keys. If two tenants share an item ID with different data, `key="#p0"` may omit the tenant. Include all factors affecting the output in the key, such as a `(tenantId, itemId)` record or a consistent key generator. Ensure authorization still runs **even on cache hits**.

Local Caffeine typically stores Java objects by **reference**. If the value is a mutable DTO or list, a caller mutating it after retrieval can corrupt the cached entry served to other requests. Prefer immutable DTOs, defensive copies at boundaries, and avoid caching live ORM-managed entities directly.

## 7. Common Mistakes When Registering Custom Caches

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling only `setCaffeine` with one TTL and expecting different cache names to get different TTLs | All regions created via the shared builder share the same expiry | Use `registerCustomCache` with separately built native caches |
| Passing `List<String>` to `registerCustomCache` | Wrong API/type; method expects a native Cache instance | `registerCustomCache(name, Caffeine.newBuilder().build())` |
| Confusing native Caffeine `Cache` with Spring `Cache` | Compile-time type mismatch or wrong API | Use fully qualified types; the manager adapts native caches for Spring |
| Calling `getCache("shortItem")` instead of `"shortItems"` | Missing region in static mode or stray region created in dynamic mode | Centralize region names; test `getCacheNames()` |
| Creating a custom cache while annotations point to a different default region | Dedicated TTL does not apply to that method | Verify `cacheNames`, keys, and resolved manager |
| Putting provider TTLs on `@Cacheable` as an attribute | Spring Cache annotations have no standard TTL attribute | Configure the native builder/provider |
| Leaving entry count unbounded | Memory usage grows unbounded with workload | Set `maximumSize`/`maximumWeight` and monitor metrics |
| Treating TTL as a millisecond-exact event | Logic wrongly relies on physical cleanup timing | Test validity on lookup; do not assume callbacks fire at exact TTL |
| Using `Thread.sleep` to test expiry | Slow and flaky tests | Use a simulated Caffeine `Ticker` as in the demo |
| Leaving `ManualTicker` in production | TTL relies on synthetic clock and stops advancing unless advanced manually | Use fake clocks only in test environments |
| Populating caches via self-invocation | Caching proxy can be bypassed | Call through a Spring proxy / another bean |
| Expecting a local cache to sync across multiple JVMs | Stale data diverges per replica | Use event invalidation/distributed caches or matching TTL/SLA |
| Re-registering a cache name unintentionally with a different config | Entries may be lost or policies may change unexpectedly | Treat cache names/policies as contracts; configure at startup and test |

## 8. How to Verify Configuration and Behavior

Some startup verification checks:

~~~java
// Illustrative check inside a bean holding CacheManager manager:
boolean shortExists =
        manager.getCache("shortItems") != null;
boolean longExists =
        manager.getCache("longItems") != null;
boolean defaultExists =
        manager.getCache("defaultItems") != null;
boolean unknownMissing =
        manager.getCache("typo") == null;
~~~

**Distinguish two kinds of tests:**

- **Configuration:** whether cache names are registered, the right `CacheManager` is used, and custom caches have expected TTL/size. `getCache(name) != null` only confirms the region exists.
- **Behavior:** first lookup for a key misses, second hits, after its specific TTL it misses again; source-update eviction also works. The `ManualTicker` demo above measures this via method-body execution counters.

To assert native policy values without depending on internal APIs, retain references to the native cache variables passed to `registerCustomCache` in integration tests, or call `CaffeineCache.getNativeCache()` from the adapter when the adapter type matches. Do not use reflection hacks to mutate Spring's internal cacheMap.

### Recommended Tests

1. **Independence by name:** invoke the same key `K1` on `shortItems` and `longItems`; the first call on each region misses.
2. **Different TTLs:** at T=6, only short expired; at T=31, default expired while long has not; at T=41, long expired.
3. **Different keys:** within one region, key `K2` misses independently from `K1`.
4. **Default policy:** add a region via `setCacheNames` without custom registration; verify it uses the shared builder rather than inheriting short's TTL.
5. **Wrong name in static mode:** `getCache("notRegistered") == null`; when an annotation uses a wrong name, resolution should fail instead of silently creating a region.
6. **Maximum size:** insert more entries than the max capacity and measure entry count/hit rate and eviction; do not assert a specific victim entry unless the policy guarantees order.
7. **Null:** have a loader return `null` and observe `allowNullValues=false` behavior.
8. **Source updates:** mutate source data while the cache is still valid, then evict the key and observe the updated result.
9. **Multiple replicas:** verify evicting in one JVM does not affect the local cache in another JVM.
10. **Metrics:** enable `recordStats()` and confirm hits/misses/evictions are observable properly.

## 9. Code Review Checklist

- [ ] Every cache region has a consistent name and clear data/key contract.
- [ ] Shared policy is defined by `setCaffeine`; only regions needing exceptions use `registerCustomCache`.
- [ ] Custom caches are built **before** registration with TTL/size tailored to each data type.
- [ ] Names in `@Cacheable`/`@CachePut`/`@CacheEvict` match those provided by the manager.
- [ ] `setCacheNames` is not confused with per-cache configuration; static or dynamic mode is explicitly chosen.
- [ ] Expiry is tested with a ticker and miss/hit is verified via counters/metrics rather than identical display values.
- [ ] `expireAfterWrite`, `expireAfterAccess`, `maximumSize`, and negative caching/`allowNullValues` are clearly understood.
- [ ] Strategies exist for updates, transactions, multiple instances, and concurrent misses.
- [ ] Fake tickers or demo parameters (5 seconds / 100 entries) are not left as default production configs.
- [ ] Integration tests exist against the actual Spring and Caffeine versions deployed.

## References

- Spring Framework — CaffeineCacheManager API (`registerCustomCache`, `setCacheNames`, `setCaffeine`): https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/caffeine/CaffeineCacheManager.html
- Spring Framework — Configuring the Cache Storage: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
- Spring Framework — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Boot — Caching: https://docs.spring.io/spring-boot/reference/io/caching.html
- Caffeine — Eviction and Expiration (builder policies, Ticker): https://github.com/ben-manes/caffeine/wiki/Eviction