# TTL and Capacity Limitations of Basic ConcurrentMap Implementations in Spring Cache

## Learning Objectives

Spring Cache provides a very convenient way to declare caching via `@Cacheable`, `@CachePut`, `@CacheEvict`, and `CacheManager`. For new applications, Spring Boot can often use the **Simple** provider, backed by `ConcurrentMapCacheManager` and `ConcurrentMapCache`. This approach is fast, has minimal dependencies, and is suitable for learning or testing. However, it **does not have TTL, TTI, entry count limits, or memory-pressure eviction policies** like dedicated cache providers.

After this lesson, you will:

1. Understand the structure and lifecycle of `ConcurrentMapCacheManager`, `ConcurrentMapCache`, and `ConcurrentHashMap`.
2. Distinguish **having no automatic TTL** from **still being able to evict manually** via the cache API or `@CacheEvict`.
3. Understand why unbounded key growth can retain JVM memory and cause OOM risks.
4. Know that options such as `setCacheNames` and `setAllowNullValues` are not TTL or capacity limits.
5. Run a **Java 17 + Spring Boot 3.3.5** example demonstrating that the cache keeps stale values after waiting, grows its entry count, and is cleared explicitly.
6. Switch to Caffeine when `maximumSize`, `maximumWeight`, `expireAfterWrite`, or `expireAfterAccess` is needed.
7. Test, measure, and decide when to keep simple ConcurrentMap and when to switch providers.

**Key point:** The Spring Cache abstraction does not mandate cache entry lifetime or capacity. Those policies must come from the underlying implementation. Do not treat `@Cacheable` as a guarantee that an entry will expire automatically.

## 1. Where Does `ConcurrentMapCacheManager` Store Data?

`ConcurrentMapCacheManager` is Spring Framework's `CacheManager` that creates and manages `ConcurrentMapCache` instances. Each cache has a data region backed by a `ConcurrentMap`, typically a `ConcurrentHashMap` in the memory of **the current JVM process**.

~~~text
Spring-managed service
  @Cacheable(cacheNames = "prices", key = "#p0")
               |
               v
        Spring Cache interceptor
               |
               v
       ConcurrentMapCacheManager
               |
               +-- ConcurrentMapCache "prices"
               |       |
               |       +-- "P1" -> 100
               |       +-- "P2" -> 200
               |
               +-- ConcurrentMapCache "products"
                       |
                       +-- "P1" -> Product(...)
~~~

`CacheManager` resolves **cache names**. `Cache` resolves **keys**. Two requests only share an entry when they go through the same cache instance with compatible keys. Each cache name normally has its own map. If two JVMs run the same application, each process creates its own `ConcurrentMapCacheManager` and map; it is not a distributed cache.

### Benefits of the Simple Implementation

- Built into the Spring ecosystem, minimal configuration.
- `ConcurrentHashMap` supports concurrent access across multiple threads with good performance.
- Suitable for small demos, tests, trying annotations, and small, bounded datasets.
- No need to run Redis or add Caffeine just to learn caching concepts.
- When the context/JVM terminates, the in-memory cache disappears as well.

### Important Limitations

- **No TTL**: an entry does not automatically expire after 30 seconds, 5 minutes, or 1 day.
- **No TTI**: no configuration to auto-remove after a period of inactivity.
- **No `maximumSize`**: the map does not automatically cap at 1,000 or 10,000 entries.
- **No `maximumWeight` or byte budget**: an entry can hold a large object graph.
- **No automatic LRU/LFU policy**: as entry counts grow, the provider does not automatically evict older keys to protect the heap.
- **No persistence or cross-JVM sharing**: restarts lose the cache; another replica has a different cache.

`ConcurrentHashMap` supports concurrent access; the word "Concurrent" **does not mean** it provides timeouts, eviction, or distributed coordination. These are different feature axes.

## 2. Two Types of Limits: Data Age and Capacity

### TTL: Time To Live

TTL is the duration for which an entry is still considered valid. In a dedicated cache, you can set, for example, "expire 120 seconds after write."

~~~text
T=00:00:00  put P1=100
T=00:01:00  get P1 -> HIT
T=00:02:10  get P1 -> MISS if TTL is 120 seconds
~~~

With basic `ConcurrentMapCache`, **there is no corresponding TTL timer**. If nothing explicitly deletes or replaces the entry, a call at `T=00:02:10` can still hit the old value. Waiting `Thread.sleep(120_000)` does not make the map know to expire data.

Some systems embed a timestamp into the **key** to produce a new key every interval. That is **not a map TTL**: entries with old keys remain in the map, continuing to occupy memory until removed or the process terminates. This is often a dangerous workaround because the number of keys can bloat continuously.

### TTI: Time To Idle

TTI (time-to-idle), also called expiration after access, limits the duration since the last access. It differs from post-write TTL:

| Policy | Age reference point | Behavior |
| --- | --- | --- |
| TTL/expire-after-write | Entry write/creation | Repeated reads do not extend the deadline |
| TTI/expire-after-access | Most recent access | Hot keys can live long because they are constantly accessed |
| No expiration | No reference point | Entry stays until evicted/cleared/overwritten or context ends |

Neither of the first two policies exists in basic `ConcurrentMapCache`. If business rules require "data no older than 5 minutes," choose a backend with write-based TTL or implement reliable invalidation, rather than using TTI as a substitute for strict freshness requirements.

### Capacity: Entry Count or Weight Limits

~~~text
Cache name = "prices"
"P1" -> 100
"P2" -> 200
"P3" -> 300
...
"P1000000" -> 999999
~~~

`ConcurrentMapCache` can keep accumulating different keys. It has no `maximumSize(1000)` like Caffeine, nor does it track total value weight to evict automatically. When memory runs low, the application can suffer GC pressure, degraded response times, or `OutOfMemoryError`.

Entry count limits and byte limits are two different things:

~~~text
Estimated retained memory
    ≈ entry count × (key weight + value weight + overhead)
~~~

This is only a mental estimate. Actual Java object graph size also depends on object headers, references, alignment, collection internals, and references held elsewhere. Just 100 entries can consume a lot of RAM if each value is a large list.

## 3. Why Doesn't `@Cacheable` Solve TTL/Capacity?

Example:

~~~java
// Illustrative snippet in a Spring-managed service.
@Cacheable(cacheNames = "prices", key = "#p0")
public Integer findPrice(String productId) {
    return repository.findPrice(productId);
}
~~~

The Spring cache interceptor works roughly like:

~~~text
key = productId
cache = cacheManager.getCache("prices")

if cache has entry(key):
    return entry.value

value = findPrice(productId)
cache.put(key, value)
return value
~~~

This is a simplified model, omitting features such as `condition`, `unless`, `sync`, null adaptation, or `CacheErrorHandler`.

With `ConcurrentMapCache`, the `key -> value` entry remains in the map after `put` until overwritten, `evict`ed, `clear`ed, or the process lifecycle ends. The annotation does not secretly run a scheduler to clean up keys over time, nor does it create a capacity policy.

### Does `@Cacheable(sync = true)` Add TTL?

**No.** `sync=true` is a hint to coordinate computation when multiple callers miss the same key concurrently, subject to provider support. It does not add expiration, LRU, quotas, or cross-JVM synchronization. Distinguish **concurrency control** from **lifecycle/capacity management**.

### Does `unless = "#result == null"` Have TTL?

**No.** `unless` can veto storing a new result (e.g., null) after the method executes. It does not remove old results already in the cache, does not set a lifetime, and does not cap key count.

## 4. Commonly Misunderstood `ConcurrentMapCacheManager` Options

Spring provides several settings for the simple manager, yet they **do not** turn it into a bounded cache provider.

| Option / API | What does it do? | Does it set TTL/capacity? |
| --- | --- | --- |
| `new ConcurrentMapCacheManager("prices")` | Declares named cache regions | **No** |
| `setCacheNames(...)` | Fixes the set of **cache names** that can be created/looked up | **Does not limit key count inside** |
| `setAllowNullValues(boolean)` | Allows/disallows storing null results via the adapter | **No** |
| `setStoreByValue(boolean)` | Configures copying via serialization when supported, instead of keeping references | **No** |
| `getCache("prices")` | Retrieves a cache region by name | **No** |
| `Cache.evict(key)` | Removes **a specified entry** | Explicit, not time-based |
| `Cache.clear()` | Removes all entries in a region | Explicit, not automatic capacity-based |
| `@CacheEvict` | Declares removal upon business operations | Explicit, not TTL |

Note that `setStoreByValue` has serialization requirements and performance trade-offs; do not enable it merely to reduce memory leaks. Copying values does not create eviction. With the default store-by-reference setup, cached mutable objects can be modified unintentionally if the same object is shared across places; prefer immutable DTOs where possible.

### `setCacheNames` Only Limits Cache Names, Not Keys

~~~java
// Illustrating static configuration for two cache names.
@Bean
ConcurrentMapCacheManager cacheManager() {
    return new ConcurrentMapCacheManager("prices", "products");
}
~~~

This prevents accidentally creating **new named cache regions** per request. However, `"prices"` can still hold millions of distinct keys. The two limits are independent:

~~~text
Cache name limit: prices, products
Key limit in prices: NONE in basic ConcurrentMap
~~~

If cache names are created dynamically per tenant or request in dynamic mode, the number of cache instances can grow too. Use a controlled set of cache names and design keys according to business needs rather than relying on unbounded name creation.

## 5. Runnable Example: Cache Does Not Auto-Expire and Entry Count Grows

We build a small application with **Java 17, Spring Boot 3.3.5, Maven**. `PriceService` simulates a data source using a `ConcurrentHashMap` and counts how many times the method actually reads the source. `ConcurrentMapCacheManager` is declared explicitly to ensure the simple provider is used even if other dependencies are present in the environment.

The program will:

1. Read `P1` the first time and then hit on the next call.
2. Update the price in the **data source** to 120, wait over 1 second, and still read the cached price 100.
3. Read four additional keys so the map holds five entries.
4. Call `Cache.evict("P1")` to evict manually and read the new price 120.
5. Call `Cache.clear()` to clear the entire region.

This is a behavioral demo, **not a maximum-limit benchmark**: five entries simply demonstrate that new keys are added without being auto-evicted. The provider's lack of capacity/TTL is documented in the official reference.

### Directory Structure

~~~text
simple-map-cache-demo/
├── pom.xml
└── src/main/java/example/simplecache/
    ├── DemoApplication.java
    └── PriceService.java
~~~

### `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>simple-map-cache-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-cache</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### `src/main/java/example/simplecache/PriceService.java`

~~~java
package example.simplecache;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class PriceService {
    private final ConcurrentMap<String, Integer> source =
            new ConcurrentHashMap<>();
    private final AtomicInteger sourceReads = new AtomicInteger();

    public PriceService() {
        for (int i = 1; i <= 5; i++) {
            source.put("P" + i, i * 100);
        }
    }

    @Cacheable(cacheNames = "prices", key = "#p0")
    public Integer findPrice(String productId) {
        sourceReads.incrementAndGet();
        return source.get(productId);
    }

    // Intentionally modify only the source to observe a stale cache entry.
    public void changeSource(String productId, int newPrice) {
        source.put(productId, newPrice);
    }

    public int sourceReads() {
        return sourceReads.get();
    }
}
~~~

`findPrice()` is the only method with a cache annotation. `changeSource()` **does not evict** to illustrate that modifying the DB/data source does not make Spring automatically detect and remove the cached entry. In a production application, this would be a consistency bug if business logic expects the next read to immediately see the new price.

### `src/main/java/example/simplecache/DemoApplication.java`

~~~java
package example.simplecache;

import java.util.List;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("prices");
    }

    @Bean
    CommandLineRunner demo(PriceService prices, CacheManager manager) {
        return args -> {
            System.out.println("first=" + prices.findPrice("P1"));
            System.out.println("hit=" + prices.findPrice("P1"));
            System.out.println("sourceReads=" + prices.sourceReads());

            prices.changeSource("P1", 120);
            Thread.sleep(1200);
            System.out.println("after-wait=" + prices.findPrice("P1"));
            System.out.println("sourceReads=" + prices.sourceReads());

            for (String id : List.of("P2", "P3", "P4", "P5")) {
                prices.findPrice(id);
            }

            ConcurrentMapCache cache =
                    (ConcurrentMapCache) manager.getCache("prices");
            System.out.println(
                    "entry-count=" + cache.getNativeCache().size());

            cache.evict("P1");
            System.out.println(
                    "after-evict=" + prices.findPrice("P1"));
            System.out.println("sourceReads=" + prices.sourceReads());

            cache.clear();
            System.out.println(
                    "after-clear-count=" + cache.getNativeCache().size());
        };
    }
}
~~~

### Run and Output

Open a terminal in the `simple-map-cache-demo` directory:

~~~bash
mvn -q spring-boot:run
~~~

Besides Spring Boot startup logs, the lines printed by `CommandLineRunner` will be:

~~~text
first=100
hit=100
sourceReads=1
after-wait=100
sourceReads=1
entry-count=5
after-evict=120
sourceReads=6
after-clear-count=0
~~~

**Explaining the output:**

- `first=100`: on the first call, `P1` is not cached yet, the method reads the source, `sourceReads=1`.
- `hit=100`: the second call hits the same key, so source reads stay at 1.
- The source price was changed to 120, yet the cache **has no TTL**. Even after `Thread.sleep(1200)` waits over a second, `after-wait=100` because the `P1` entry still exists.
- The program queries P2, P3, P4, and P5; together with P1, the map holds five keys, so `entry-count=5`. There is no configuration auto-evicting P1 as key count grows.
- `cache.evict("P1")` removes the old entry. The next read misses and returns `120`; total source loads equal `1 + 4 + 1 = 6`.
- `cache.clear()` removes entries in the **`"prices"` region**, resetting entry count to 0. It does not clear other cache names or caches in other JVMs.

`Thread.sleep` in the demo only helps learners observe elapsed time; it is not an eviction timer. Even if you replace `1200` with a larger duration, `ConcurrentMapCache` inherently still has no TTL. Do not increase sleep durations in production tests trying to "force" the cache to expire: the simple provider has no such logic.

### Why Does the Demo Call Through `CommandLineRunner`?

Spring Cache in standard proxy mode only intercepts calls **through a Spring bean proxy**. Calling `this.findPrice(...)` from inside `PriceService` itself usually bypasses the proxy. Injecting the `PriceService` bean into another runner bean ensures annotations are processed via the Spring-supported call path.

### Can Tests Avoid `Thread.sleep`?

Yes. For non-TTL tests, you can use a mock clock for the **data source** or simply prove that the entry still exists after modifying source data. However, a "manual clock" cannot affect `ConcurrentMapCache` TTL, because the provider **has no** TTL configuration in the first place. If you want to test time-based expiration using a fake ticker, use Caffeine with a custom `Ticker` in tests.

## 6. What `ConcurrentMapCache` Can Do Even Without TTL

### `@CacheEvict` Removes Entries on Business Operations

~~~java
// Illustrative example in a Spring service with a real repository.
@CacheEvict(cacheNames = "prices", key = "#p0")
public void updatePrice(String productId, int price) {
    repository.updatePrice(productId, price);
}
~~~

After the method completes normally, Spring evicts the corresponding key. The next `@Cacheable` call reloads from the data source. This is **explicit invalidation**, not TTL.

You must use the same cache name and the same key between read and update. If `@Cacheable` uses key `productId` while `@CacheEvict` uses `SimpleKey(productId, price)`, the old entry remains.

If the update method returns the exact value expected by readers, you can also use `@CachePut` to overwrite the entry. If the update only returns a status/boolean while the cache holds a DTO, using `@CachePut` directly would put the wrong value type into the cache; eviction is safer.

### Clearing an Entire Region When Needed

~~~java
// Illustration: evict all entries of the "prices" cache after a business operation.
@CacheEvict(cacheNames = "prices", allEntries = true)
public void invalidateAllPrices() {
    // Method body performs or records the appropriate business event.
}
~~~

`allEntries=true` applies to the selected cache region; it does not mean clearing every cache name in the application. Clearing an entire region can cause a spike of cache misses and source reloads, which should be weighed under heavy traffic.

### Cache API

~~~java
// Inside a class with CacheManager injected; non-standalone illustrative code.
Cache cache = cacheManager.getCache("prices");
cache.evict("P1");
cache.clear();
~~~

These operations take effect when invoked. `ConcurrentMapCacheManager` does not automatically schedule `evict` or `clear` by entry age, nor does it automatically know when a product changed in the DB.

### Blocking Null Caching

~~~java
@Cacheable(
        cacheNames = "prices",
        key = "#p0",
        unless = "#result == null"
)
public Integer findPrice(String productId) {
    return repository.findPrice(productId);
}
~~~

This rejects storing null **after a fresh computation**; it does not set a TTL. `ConcurrentMapCache` has an adaptation mechanism to support null via a marker when allowed by the manager; `ConcurrentHashMap` itself does not accept null values. `setAllowNullValues(false)` is a different setting from `unless` and should not be treated as a mechanism for deleting old data.

## 7. Why Building Your Own TTL on `ConcurrentHashMap` Is Usually a Poor Choice

A common idea is storing `(value, expiresAt)` pairs in a map and checking `System.currentTimeMillis()` before returning. It might work in a tiny example, but a production-grade cache must solve many problems:

1. **Time measurement:** use an appropriate monotonic time source for elapsed time; wall clocks can be adjusted, shifting TTL deadlines unexpectedly.
2. **Concurrent loading:** when two threads see the same entry expired, do both run the loader?
3. **Overwrite races:** a slow loader can overwrite with stale data after another request has already updated.
4. **Cleaning expired keys:** checking TTL on `get` only removes accessed keys. Expired entries that nobody reads can still retain memory.
5. **Capacity limits:** cleaning expired entries differs from evicting when key counts exceed a budget.
6. **Precision and overhead:** a scheduler running frequently costs CPU; running infrequently leaves high retained memory.
7. **Thread safety:** iterators, updates, and evictions must remain safe under concurrent access from multiple threads.
8. **Metrics:** you need visibility into hits/misses, expirations, capacity evictions, and load durations.
9. **Region and key management:** each cache name, tenant, and data type needs suitable policies.
10. **Failure handling:** loader exceptions, nulls, serialization, and application shutdown must have clear semantics.

Simply storing `expiresAt` in the value **does not create** a capacity mechanism. Running `@Scheduled(fixedRate=...)` to `clear()` the entire cache **is not per-entry TTL**; it invalidates every key at once and can trigger a cache stampede.

If requirements stay within a fixed set of a few dozen keys and data freshness is managed by specific updates/evicts, simple ConcurrentMap may suffice. If you need expiration, bounded size, weighted eviction, or reliable metrics, using an established cache provider carries far less risk than reimplementing those features yourself.

## 8. Switching to Caffeine When Real TTL and Limits Are Needed

Caffeine is a JVM in-memory provider offering expiration, maximum size/weight, statistics, and many optimizations for real-world applications. In Spring Boot, usually you just add the Caffeine dependency and let Boot configure `CaffeineCacheManager`.

### Add Dependency

In `pom.xml`, keep `spring-boot-starter-cache` and add:

~~~xml
<!-- Snippet of dependencies to add to an existing pom.xml -->
<dependency>
    <groupId>com.github.ben-manes.caffeine</groupId>
    <artifactId>caffeine</artifactId>
</dependency>
~~~

The Spring Boot BOM manages the appropriate version in a Boot project; this XML snippet is not a full POM.

### Remove the Demo's Custom `CacheManager` Bean

In `DemoApplication` from section 5, **delete the `@Bean CacheManager cacheManager()` method**. If you keep your own `ConcurrentMapCacheManager` bean, Boot will not automatically replace it with Caffeine just because the dependency and properties exist. A provider configuration must be chosen unambiguously.

### `application.properties`

Create `src/main/resources/application.properties`:

~~~properties
spring.cache.type=caffeine
spring.cache.cache-names=prices
spring.cache.caffeine.spec=maximumSize=1000,expireAfterWrite=120s,recordStats
~~~

Meaning:

| Configuration | Effect |
| --- | --- |
| `spring.cache.type=caffeine` | Selects Caffeine in auto-configuration |
| `cache-names=prices` | Specifies the desired cache name |
| `maximumSize=1000` | Target limit of around 1,000 **entries for this cache instance** |
| `expireAfterWrite=120s` | Entry expires 120 seconds after the most recent write |
| `recordStats` | Records Caffeine statistics upon access |

**Important note:** `maximumSize` counts **entries**, not RAM bytes. Very large values can still cause heap pressure even with few entries. Caffeine executes its own eviction/maintenance policies; do not assume a specific key will deterministically be evicted the instant a threshold is reached.

After switching providers, the logic in `PriceService` can keep `@Cacheable(cacheNames="prices", key="#p0")` unchanged: that is the benefit of the Spring Cache abstraction. However, the demo code that casts to `ConcurrentMapCache` and calls `getNativeCache().size()` will **no longer be valid** with Caffeine; update size inspection to use `CaffeineCache`/native API or Actuator metrics if needed. The demo output in section 5 applies only to **ConcurrentMap**, not to verify behavior after switching providers.

### Programmatic Configuration Instead of Properties

You can use Java configuration:

~~~java
// Illustrative snippet inside a @Configuration class, with appropriate imports.
@Bean
CaffeineCacheManager cacheManager() {
    CaffeineCacheManager manager = new CaffeineCacheManager("prices");
    manager.setCaffeine(
            Caffeine.newBuilder()
                    .maximumSize(1000)
                    .expireAfterWrite(java.time.Duration.ofMinutes(2))
                    .recordStats()
    );
    return manager;
}
~~~

This replaces auto-configuration via properties rather than adding a second manager with the same role. Required imports include `Caffeine`, `CaffeineCacheManager`, and `Bean`, with the Caffeine dependency on the classpath.

### If You Need Byte Limits Instead of Entry Counts

Caffeine supports `maximumWeight(...)` and `weigher(...)` to compute **application-defined weights**. For instance, a `byte[]` payload can be weighted by array length:

~~~java
// Illustrative Caffeine builder code, not standalone.
var nativeCache = Caffeine.newBuilder()
        .maximumWeight(20L * 1024 * 1024)
        .weigher((String key, byte[] value) -> value.length)
        .build();
~~~

Here the limit is a total **payload weight** of about 20 MiB, not an exact measurement of heap overhead, key objects, or metadata. Do not combine `maximumWeight` with `maximumSize` on the same builder: pick the appropriate bounding strategy. Weight is computed when an entry is created/updated; mutating the array contents after storing does not cause the provider to recompute weight, so prefer immutable values.

### Is `expireAfterAccess` Better?

`expireAfterAccess=120s` expires an entry after 120 seconds of **no access**. It fits workloads where hot keys should stay cached, yet a constantly accessed key can live for a very long time. If your goal is capping **maximum staleness**, write-based TTL or an appropriate refresh/invalidation mechanism is better.

`refreshAfterWrite` (when the cache is configured with a supporting loader) differs from expiration: it allows refreshing once eligible, and in many cases can still return the old value while refreshing. Do not enable refresh assuming data automatically refreshes on a strict background schedule; verify the provider, loader, and version in use.

### When Must You Use a Distributed Cache?

Both Caffeine and ConcurrentMap primarily reside in **each JVM's** memory. If multiple replicas must share entries or coordinate invalidation, consider Redis or an appropriate distributed provider. Shared storage lets replicas see common data, yet requires designing TTL, key prefixes, serializers, memory policies, and network failure handling. A distributed cache also does not automatically guarantee "exactly once" execution when multiple loaders miss simultaneously.

## 9. Managing Capacity If Temporarily Keeping ConcurrentMap

There are cases where keeping the Simple provider is a reasonable decision, such as a small, known upfront configuration dataset. In such cases, enforce bounds **through business design** rather than assuming a feature the provider lacks.

### Limit the Key Domain with Business Validation

~~~text
cache = "countryCodes"
key can only be one of a verified set of ISO country codes
key count has a clearly bounded domain
~~~

If you know the key count is finite and each value is small, the cache does not need complex eviction algorithms. However, do not confuse **bounding the key domain** with **provider-configured `maximumSize`**: if an API allows adding arbitrary new keys without validation, the finiteness assumption no longer holds.

### Do Not Put Request IDs or Timestamps in Keys

~~~java
// COUNTEREXAMPLE: a new UUID every call means the cache almost never hits.
@Cacheable(
    cacheNames = "prices",
    key = "#p0 + ':' + T(java.util.UUID).randomUUID()"
)
public Integer findPrice(String id) {
    return repository.findPrice(id);
}
~~~

Every request gets a new key, and old entries can stay forever in ConcurrentMap. Also avoid putting unnormalized raw query strings, access tokens, or tracing metadata in keys if they do not affect the return value. Pay attention to both performance and the risk of exposing sensitive data via logs/tracing.

### Be Careful with Methods Returning Large Lists

A single entry holding a list of hundreds of thousands of elements can grow the heap sharply even with a key count of 1. You can cache slimmer DTOs, cap query sizes, paginate appropriately, or avoid caching oversized results. Caching paginated results creates more keys: evaluate both value size and cardinality.

### Evict When Source Data Changes

If `updatePrice("P1")` just updated the database, you need a compatible invalidation or `@CachePut` policy. Otherwise, the old price can stay in the map **until restart**. A `@CacheEvict` with the right key ensures the next read loads the new price. When updates run inside a transaction, decide when evict/put happens relative to commit; do not assume cache and DB automatically share an atomic transaction.

### Does Periodic Clearing Replace TTL?

No. For example, clearing a region every hour:

~~~text
10:00 clear prices
10:00:01 P1 price is cached
10:59:59 P1 can still remain
11:00 clear entire region
~~~

Entry age varies depending on when it was created relative to the clear schedule. An entry created at 10:59:59 is deleted after one second, while an entry created at 10:00:01 lives nearly an hour. A full-region clear schedule also tends to make all requests miss at once afterward, spiking load on the source. For TTL SLAs, choose a provider supporting per-entry expiration.

## 10. Single JVM, Multiple JVMs, and Consequences of Local Caching

~~~text
                 Load balancer
                    /      \
                  App A    App B
                   JVM A    JVM B
                    |        |
             Map prices A  Map prices B
                    \        /
                   Shared database
~~~

`ConcurrentMapCacheManager` in App A does not share heap with App B. Two instances can cache **the same key with two different price versions**. Evicting `"P1"` in App A does not automatically evict `"P1"` in App B.

If you have four replicas and each holds 10,000 identical entries, memory consumed for those copies scales across all four JVMs. There is no exact formula based solely on entry count; measure retained heap and GC on each replica.

`@Cacheable(sync=true)` can coordinate loaders for the same key **within a single cache instance** as supported by the provider, but does not turn a local map into a distributed cache. When caches warm up simultaneously across multiple replicas, duplicate computations can occur. Depending on the application, this may be acceptable or require a shared cache / separate coordination.

### A Cache Hit Is Not an Authorization Mechanism

If a `@Cacheable` method only checks permissions **inside the method body**, a cache hit can bypass that check. For sensitive data, check permissions before the cached call in a place that always runs, and ensure keys are scoped by tenant/user/role if values vary by scope. A basic ConcurrentMap setup does not solve security on its own.

## 11. Testing TTL/Capacity and Operational Monitoring

### What to Test Properly

| Test | Simple/ConcurrentMap Provider | Provider with TTL/Capacity |
| --- | --- | --- |
| Call same key twice | Can hit on second call | Can hit if not expired/evicted |
| Wait 1 second without invalidation | Entry does not auto-expire | Depends on configured TTL |
| Change source while cached | Entry can remain stale | Can still be stale until TTL/invalidation |
| Add many distinct keys | Map keeps accepting keys | May trigger capacity eviction |
| `Cache.evict(key)` | Explicit removal | Also explicit removal |
| `Cache.clear()` | Clears entire region | Also clears entire region per provider |
| JVM restart | Local cache lost | Local cache lost; remote cache may persist |
| Multiple JVMs | Entries not shared | Local provider does not share; remote depends on backend |

With Caffeine, use a fake ticker in unit/integration tests to verify expiration quickly and reliably. With ConcurrentMap, tests can simply verify the **absence** of automatic TTL behavior and that explicit invalidation works. Avoid tests that sleep for many minutes when proper time-control APIs exist.

### Monitoring Key Count and Memory

From `ConcurrentMapCache`, `getNativeCache().size()` gives the number of entries present in the map at read time. That is not heap byte usage. If there are many cache names, monitor total entries and memory across all regions, not just one name.

A recommended set of metrics:

- Keys per cache, growth rate of new keys over time.
- Heap used/retained, garbage collection pauses, and OOM/near-OOM incidents.
- Cache hits/misses, source load counts, load latencies, and loader errors.
- Invalidation counts, full-region clears, and post-clear miss spikes.
- Maximum and median serialized value sizes (if applicable).
- Number of JVM replicas and cost of holding duplicate cache copies.
- Frequency of stale results observed after source updates.
- p95/p99 latency of APIs backed by the cache.

The Simple provider does not include full eviction/expiration statistics because it does not enforce those policies. You can add instrumentation at the service layer or use Actuator/Micrometer depending on configuration, yet **never** assume metrics are enabled automatically just because `@Cacheable` is present.

**Avoid cardinality explosions in metrics themselves:** do not attach every product ID, query string, or access token as a metric label. Only use bounded label sets such as cache name, business group, or environment.

### Avoid Inspecting by Scanning the Entire Map

`ConcurrentHashMap.size()` can be used to observe scale where necessary, but you should not continuously snapshot and log every key/value of a production cache; doing so incurs CPU/GC cost and data exposure risks. In applications with many concurrent writes, `size()` is a monitoring snapshot, not an atomic quota boundary.

## 12. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Prices remain stale after many hours | No TTL/invalidation in ConcurrentMap | Evict/put on updates, or use a provider with TTL |
| Heap grows over time | New keys keep getting added without auto-eviction | Reduce key cardinality, bound payloads, switch to bounded cache |
| `spring.cache.cache-names` has only 2 names yet memory grows | Limits cache names, not key count | Control key count in each cache |
| Set `@Cacheable(unless=...)` yet data stays stale | `unless` only vetoes new results | Explicitly evict old entries when data changes |
| Added `@Cacheable(sync=true)` yet map still grows | `sync` prevents duplicate miss loads, has no capacity limit | Use `maximumSize`/dedicated provider |
| Updating source does not update cache | Caching does not watch the DB automatically | Sync updates with `@CacheEvict`/`@CachePut` |
| Clearing hourly leaves unpredictable key ages | Scheduled clear differs from per-entry TTL | Choose appropriate expire-after-write |
| Added Caffeine dependency yet still no TTL | Custom `ConcurrentMapCacheManager` bean is present | Remove old bean, select right provider, verify at runtime |
| Using Caffeine yet casting to `ConcurrentMapCache` fails | Native cache class changed | Use the `Cache` abstraction or corresponding provider API |
| One replica evicted, another stays stale | Separate local cache per JVM | Use shared cache / broadcast invalidation |
| Cached mutable DTO changes unexpectedly | Store-by-reference and object was mutated | Use immutable values or appropriate copy config |
| Null caching produces unexpected behavior | `allowNullValues` and annotation policy | Define clear negative caching/`unless` rules |
| Mistaking `maximumSize` for a byte limit | Caffeine counts entries, not RAM | Use weight estimation or measure actual heap |

## 13. Practice Exercises

**Exercise 1.** An application uses `ConcurrentMapCacheManager` to cache `findById`. After 24 hours, a key still hits even though the data source changed. Is this a bug in Java's `ConcurrentHashMap`?  
**Answer:** No. The basic provider has no automatic TTL. If fresh data is required, evict/put when the source changes or use a provider with expiration and an appropriate freshness policy.

**Exercise 2.** Does `new ConcurrentMapCacheManager("users", "products")` stop `"users"` from accepting more than 1 million keys?  
**Answer:** No. It only specifies cache names, not the number of entries inside each cache.

**Exercise 3.** A cache holds 500 keys, each value 5 MiB. Can it be considered small because there are "only 500 keys"?  
**Answer:** No. Raw payload alone is already huge, not counting overhead. You need to bound value sizes, retained data, and heap budgets.

**Exercise 4.** Is clearing the entire cache at midnight equivalent to a 24-hour TTL?  
**Answer:** No. An entry created right before midnight is deleted after a few seconds, while an entry created right after midnight survives nearly 24 hours.

**Exercise 5.** You add `spring.cache.caffeine.spec=maximumSize=1000,expireAfterWrite=120s`, yet the project still has a `@Bean ConcurrentMapCacheManager`. Is it guaranteed that the properties took effect?  
**Answer:** No. A custom `CacheManager` bean can prevent Boot from auto-configuring Caffeine. Choose the right manager, inspect the running class, and test expiration/capacity behavior.

**Exercise 6.** Does `@Cacheable(sync=true)` make an entry disappear automatically after 5 minutes?  
**Answer:** No. It relates to coordinating cache misses, not providing a lifetime.

**Exercise 7.** App A and App B share the same source DB and the same cache name `"prices"`, yet each app has its own `ConcurrentMapCacheManager`. If App A evicts `"P1"`, does App B delete it automatically?  
**Answer:** No. The two local caches live in two independent JVMs.

**Exercise 8.** When is it fine to keep using ConcurrentMap?  
**Answer:** When the key set is small/finite and controlled, values are small, automatic expiration is unnecessary, invalidation is clearly managed, and memory metrics are monitored. For open keyspaces or data requiring freshness limits, choose a more suitable provider.

## 14. Selection and Migration Checklist

Before deciding to use the Simple provider long-term:

- [ ] Determined the maximum number of **distinct keys**, or at least the possible key growth rate.
- [ ] Measured or bounded the size of objects kept in the cache.
- [ ] Defined how long results may stay stale and which updates must trigger evict/put.
- [ ] Understood that basic ConcurrentMap has no automatic TTL/TTI/capacity limits.
- [ ] Not using timestamps or new UUIDs per request in keys to simulate TTL.
- [ ] Not treating `setCacheNames` as an entry count quota.
- [ ] Verified the **actual** `CacheManager` bean in the Spring context.
- [ ] If switching to Caffeine, verified `maximumSize`/`maximumWeight`, expiration, and per-JVM behavior.
- [ ] Audited any code casting to native cache classes when switching providers.
- [ ] Tested source updates, cache hits, evicts, clears, concurrency, and restarts.
- [ ] If running multiple replicas, understood that local eviction does not sync across JVMs.
- [ ] Have metrics/alerts for heap, key count, miss rate, and stale data.

## References

- Spring Framework – **Configuring the Cache Storage**, section *JDK ConcurrentMap-based Cache*: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
- Spring Framework – **Cache Abstraction**, `@Cacheable`, `@CachePut`, `@CacheEvict`: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework – **How can I Set the TTL/TTI/Eviction policy?**: https://docs.spring.io/spring-framework/reference/integration/cache/specific-config.html
- Spring Framework – Javadoc `ConcurrentMapCacheManager`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html
- Spring Framework – Javadoc `ConcurrentMapCache`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCache.html
- Spring Boot – **Caching** and Simple/Caffeine providers: https://docs.spring.io/spring-boot/reference/io/caching.html
- Caffeine – **Eviction** and expiration: https://github.com/ben-manes/caffeine/wiki/Eviction

**Key Takeaway:** `ConcurrentMapCacheManager` is a convenient option for demos, tests, and small local caches, yet **it does not automatically bound data age or capacity**. `@CacheEvict`/`Cache.clear()` only delete when invoked; `@Cacheable` does not turn them into TTL. When bounded memory, expiration, or advanced statistics are required, use a dedicated provider like Caffeine, configured and tested against the exact `CacheManager` the application uses.