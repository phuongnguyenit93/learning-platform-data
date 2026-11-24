# Capacity Bounds, Key Cardinality, and Overly Stale Data in Spring Cache

## Learning objectives

Caching reduces source queries and improves latency, yet an **unbounded** cache can cause excessive RAM consumption, GC pressure, higher Redis costs, or continued serving of outdated data. In the Spring Framework, annotations such as `@Cacheable`, `@CachePut`, and `@CacheEvict` determine **when** data is read, written, and removed. Policies for **bounding entry count, memory capacity, lifetime, and eviction algorithms** are primarily handled by the cache provider or system configuration.

After this lesson, you will know how to:

1. Distinguish memory capacity, **key count** (*cardinality*), per-entry size, and data age.
2. Understand the differences among **expiration**, **eviction**, and **explicit invalidation**.
3. Configure Caffeine with `maximumSize`, `expireAfterWrite`, `expireAfterAccess`, and know when to use `maximumWeight`.
4. Understand Redis limits such as `maxmemory`, `maxmemory-policy`, Spring Data Redis TTLs, and cases where Redis does not automatically remove data as expected.
5. Prevent unbounded key growth caused by overly diverse parameters, unnormalized inputs, or dynamic cache names.
6. Design refresh and invalidation policies when source data changes.
7. Read metrics, test memory boundaries, and build a runnable Java 17/Spring Boot example demonstrating TTL and entry-count bounds.

**Principle:** a good cache always has a **clear data scope**, a **resource budget**, and a **freshness contract**. Maximizing hit rate is not the sole objective.

## 1. Three distinct bounds

Consider a cache named `"products"`:

~~~text
products
  key1 -> value1 (4 KiB)
  key2 -> value2 (8 KiB)
  key3 -> value3 (120 KiB)
  ...
~~~

There are three separate risks:

| Risk | Meaning | Example |
| --- | --- | --- |
| Too many keys | Too many **distinct entries** | Every query string, user, or timestamp creates a new key |
| Entry size too large | Each value holds too much data | Caching a 10 MiB file or a list of hundreds of thousands of objects |
| Data retained too long | Entries persist and can be returned after the source changes | Price, stock, or access permissions changed yet the cache hits the old version |

Related metrics that do not substitute for one another:

~~~text
Estimated retained memory
    ≈ number_of_entries × average_retained_bytes_per_entry
    + metadata, key objects, references, index, and provider overhead
~~~

This formula is an **estimate**, not an exact heap measurement. In the JVM, object size is also affected by object headers, alignment, references, interned/shared objects, GC, and how the provider stores keys/values. In Redis, costs also include keyspace structures, encoding, allocator overhead, replication, and command memory.

A 100-entry cache can still be huge if each entry is several megabytes. A cache with tiny entries can still consume gigabytes of RAM if keys grow into the millions. TTL caps entry age, yet **does not automatically guarantee** a low entry count at a given moment: if new keys are generated rapidly, millions of keys can coexist within the TTL window.

### Cardinality vs. request count

~~~text
1,000,000 requests for the same key "P1"
    -> may only need 1 entry

1,000,000 requests with 1,000,000 distinct keys
    -> may create 1,000,000 entries
~~~

With unbounded keys such as millisecond timestamps, a fresh random UUID per request, or unnormalized query strings, a cache may **almost never hit** while still paying the cost of storing entries.

## 2. `@Cacheable` does not set TTL or capacity by itself

Example:

~~~java
// Illustrative snippet in a Spring-managed service, not a standalone runnable file.
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String id) {
    return repository.find(id);
}
~~~

This annotation does not declare “keep at most 10,000 entries” or “expire after 5 minutes.” It only expresses **key-based caching**. Spring's cache abstraction interacts with `CacheManager`/`Cache` without imposing a uniform memory policy across every backend.

Without adding a specific provider, Spring Boot may use a **simple** cache backed by `ConcurrentMapCacheManager`. Cache regions backed by a concurrent map are not designed to enforce Caffeine/Redis-style TTLs or maximum size bounds. In long-running applications, caching diverse IDs in an unbounded map is a real operational risk.

Never assume “having `@Cacheable` means Spring automatically removes old entries” or “every provider defaults to LRU.” Inspect the configuration of the **actual provider** used by your application and how each cache is created.

### Cache name is not key count

~~~text
cache name = "products"
key        = "P1", "P2", "P3", ...
~~~

One cache name can hold many keys. Dynamically creating cache names per user or request instead of using appropriate keys can also spawn many new **cache instances**, complicating bounds and monitoring. Cache names should generally be a finite set grouped by data type or domain; keys identify individual results. If tenant namespaces truly must be separated, establish clear namespace-count limits and lifecycle policies.

## 3. Three easily confused mechanisms: expiration, eviction, and invalidation

| Mechanism | When it happens | Question it answers |
| --- | --- | --- |
| **Expiration** | Entry exceeds its configured lifetime or idle time | Is the value still fresh enough to return from cache? |
| **Capacity eviction** | Cache must reduce entry count, weight, or memory | Has the cache exceeded its resource budget? |
| **Explicit invalidation** | Application actively deletes or updates entries when source changes | Which entries have become invalid per business logic? |

All three mechanisms can be used together:

~~~text
@Cacheable reads "P1"
       |
       +-- cache hit and entry unexpired -> fast return
       |
       +-- miss / expired / evicted
                |
                v
           load source data
                |
                v
           put into cache
                |
                v
           provider may evict another entry when full
~~~

Bounding entry count **does not guarantee fresh data**. TTL **does not guarantee low memory usage** under high traffic and high cardinality. Accurate `@CacheEvict` provides post-update consistency, yet creates no overall RAM ceiling. Combine them appropriately.

### TTL: time since write

`expireAfterWrite = 5 minutes` means an entry expires roughly 5 minutes after its last creation/write. **Reads** do not extend lifetime under this policy. If the value is rewritten, the clock resets from the new write according to provider semantics.

~~~text
T=00:00 write P1
T=04:59 read P1  -> can hit
T=05:01 read P1  -> expired, must reload
~~~

### Time-to-idle: time since last access

`expireAfterAccess = 5 minutes` typically allows an entry to stay alive while read or written frequently. It suits workloads with locality, yet **is not an absolute age cap**: a very hot key can survive indefinitely and remain stale unless invalidated from the source.

~~~text
T=00 write P1
T=04 read P1  -> resets idle timer
T=08 read P1  -> still hits if not idle long enough
T=14 read P1  -> may be expired if no read/write since T=08
~~~

If business requirements demand “data must never be older than 5 minutes,” `expireAfterAccess=5m` **does not satisfy** that rule because reads can extend its age forever. Choose write-based TTL, refresh/invalidation, or appropriate version/freshness checks.

### Eviction when the cache is full

Under an entry-count limit, the provider may remove one or more items to make room for new ones. Never assume the evicted entry is strictly “least recently used” unless the specific provider and configuration guarantee that algorithm. Caffeine uses admission/eviction policies tuned for hit rate and may defer some cleanup to maintenance cycles. Eviction outcomes can vary with access schedules, contention, and algorithm details.

## 4. Configuring Caffeine in Spring Boot

Caffeine is a high-performance **in-JVM-memory** cache integrated with Spring via `CaffeineCacheManager`. It is a popular choice for bounding **entry count** and data age when caching locally per application instance.

In Spring Boot with the Caffeine dependency and `@EnableCaching`, a properties-based configuration:

~~~properties
spring.cache.type=caffeine
spring.cache.cache-names=products,productSummaries
spring.cache.caffeine.spec=maximumSize=10000,expireAfterWrite=600s,recordStats
~~~

Explanation:

- `maximumSize=10000`: target maximum number of entries **per cache instance** created by this configuration. This is not a combined limit across all caches or all JVMs.
- `expireAfterWrite=600s`: entries past the deadline since write are no longer returned as valid hits.
- `recordStats`: enables Caffeine internal statistics to track hits/misses, evictions, and loads depending on operation paths.
- `spring.cache.cache-names`: declares the list of region names, easier to govern than unbounded creation.
- `spring.cache.type=caffeine`: selects the Caffeine provider for compatible auto-configuration.

`maximumSize` is an **entry-count cap**, not 10,000 bytes or 10,000 MiB. If each value is huge, you can still exhaust heap well before reaching 10,000 entries. Nor does `maximumSize` guarantee the application heap actually has room for the cache.

**Note:** when you declare a custom `@Bean CacheManager`, that bean's builder configuration is the primary source of truth; do not assume the auto-configuration properties above will automatically override a custom bean.

### `maximumSize` vs. `maximumWeight`

Caffeine can bound by **weight** using `maximumWeight(...)` and `weigher(...)`. Weight is application-defined, not an automatic heap-byte measurement.

~~~java
// Illustrative Caffeine builder, not a standalone runnable file.
// Suppose Cache<String, byte[]>; use byte[] length as the weight.
var cache = com.github.benmanes.caffeine.cache.Caffeine.newBuilder()
    .maximumWeight(10L * 1024 * 1024)
    .weigher((String key, byte[] value) -> value.length)
    .build();
~~~

In the example, the weight budget is roughly 10 MiB of **`byte[]` payload**, excluding key/object/index overhead. Weight is computed when inserting or updating an entry, and does not update automatically if a value object is mutated in place after storage. Therefore, prefer immutable values or ensure updates go through cache puts.

Never combine `maximumSize` and `maximumWeight` on the same Caffeine builder: choose **one capacity policy**. When values have roughly similar sizes, `maximumSize` is straightforward. When values vary widely in size and have a sensible weigher, `maximumWeight` can track budgets more closely.

### `expireAfterWrite`, `expireAfterAccess`, `refreshAfterWrite`

| Setting | Primary effect | Risk if misused |
| --- | --- | --- |
| `expireAfterWrite` | Expires after elapsed time since write | Many keys may expire together, increasing misses |
| `expireAfterAccess` | Expires after elapsed time without access | Hot entries can persist very long and go stale |
| `refreshAfterWrite` | Marks entries eligible for refresh after an interval | **Not a TTL**; may keep serving old values while refreshing |
| `maximumSize` | Bounds entry count via eviction | Does not bound bytes per value |
| `maximumWeight` + `weigher` | Bounds total application-declared weight | Inaccurate weights fail to reflect real RAM |

`refreshAfterWrite` does not replace `expireAfterWrite`: once eligible, refresh normally requires a **loading cache/loader** and an access to trigger; while refreshing, the old value may be served. With plain `@Cacheable` and a cache lacking an appropriate loader/refresh setup, do not assume enabling `refreshAfterWrite` will automatically refresh data on schedule. Test the loader path of your provider.

### Does expiration always physically delete at the exact timestamp?

No. In many local caches, an expired entry is not returned as a hit, yet **physical cleanup** from internal structures can occur during reads/writes or maintenance cycles. Strict RAM management requires watching heap and maintenance strategies, not just checking when `get()` returns a miss. Caffeine's `Cache.cleanUp()` is for maintenance; it is not an operation normal requests should call every time.

## 5. Runnable example: Caffeine bounded to two entries and a five-minute TTL

This example uses **Java 17, Spring Boot 3.3.5, Maven**. We configure `CaffeineCacheManager` with:

- `maximumSize(2)`: the `"catalog"` cache is bounded to two entries via eviction.
- `expireAfterWrite(Duration.ofMinutes(5))`: entries older than five minutes since write expire.
- A **simulated ticker** (`ManualTicker`) to advance time by 6 minutes immediately, verifying TTL **without real waiting**.
- `recordStats()` so statistics can be inspected from the native Caffeine cache.

No current timestamps are used as keys; `"P1"`, `"P2"`, `"P3"` are stable identifiers. `@Cacheable` executes loading only on misses.

### Directory layout

~~~text
bounded-cache-demo/
├── pom.xml
└── src/main/java/example/bounded/
    ├── DemoApplication.java
    ├── ManualTicker.java
    └── CatalogService.java
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
    <artifactId>bounded-cache-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-cache</artifactId>
        </dependency>
        <dependency>
            <groupId>com.github.ben-manes.caffeine</groupId>
            <artifactId>caffeine</artifactId>
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

The Spring Boot parent manages compatible dependency versions; no separate Caffeine version is needed in this template.

### `src/main/java/example/bounded/ManualTicker.java`

~~~java
package example.bounded;

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
            throw new IllegalArgumentException("Duration must not be negative");
        }
        nanos.addAndGet(duration.toNanos());
    }
}
~~~

In tests, `ManualTicker` replaces Caffeine's monotonic clock. Never use this ticker in production because time will **stand still** unless code calls `advance`. Production should use Caffeine's real ticker.

### `src/main/java/example/bounded/CatalogService.java`

~~~java
package example.bounded;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final AtomicInteger sourceLoads = new AtomicInteger();

    public record Entry(String productId, int generation) {}

    @Cacheable(
            cacheNames = "catalog",
            key = "#p0",
            unless = "#result == null"
    )
    public Entry find(String productId) {
        int generation = sourceLoads.incrementAndGet();
        return new Entry(productId, generation);
    }

    public int sourceLoads() {
        return sourceLoads.get();
    }
}
~~~

In this example, each method execution produces an incrementing `generation`, simulating a data source with fresh results. `generation` is **not a real DB version**; it simply makes cache hits, misses, and expirations visible in stdout.

### `src/main/java/example/bounded/DemoApplication.java`

~~~java
package example.bounded;

import java.time.Duration;
import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCache;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ManualTicker manualTicker() {
        return new ManualTicker();
    }

    @Bean
    CaffeineCacheManager cacheManager(ManualTicker ticker) {
        CaffeineCacheManager manager = new CaffeineCacheManager("catalog");
        manager.setCaffeine(Caffeine.newBuilder()
                .maximumSize(2)
                .expireAfterWrite(Duration.ofMinutes(5))
                .ticker(ticker)
                .recordStats());
        return manager;
    }

    @Bean
    CommandLineRunner demo(CatalogService service,
                           ManualTicker ticker,
                           CaffeineCacheManager manager) {
        return args -> {
            System.out.println("first=" + service.find("P1"));
            System.out.println("hit=" + service.find("P1"));
            System.out.println("sourceLoads=" + service.sourceLoads());

            ticker.advance(Duration.ofMinutes(6));
            System.out.println("after-ttl=" + service.find("P1"));
            System.out.println("sourceLoads=" + service.sourceLoads());

            service.find("P2");
            service.find("P3");

            CaffeineCache cache = (CaffeineCache) manager.getCache("catalog");
            cache.getNativeCache().cleanUp();
            System.out.println("size-within-2="
                    + (cache.getNativeCache().estimatedSize() <= 2));
        };
    }
}
~~~

### Running and reading the output

From the `bounded-cache-demo` directory, with JDK 17+ and Maven:

~~~bash
mvn -q spring-boot:run
~~~

Alongside Spring's startup logs, the lines printed by `CommandLineRunner` will be:

~~~text
first=Entry[productId=P1, generation=1]
hit=Entry[productId=P1, generation=1]
sourceLoads=1
after-ttl=Entry[productId=P1, generation=2]
sourceLoads=2
size-within-2=true
~~~

Line-by-line explanation:

1. The first `find("P1")` misses; the method runs and produces `generation=1`; the cache stores the entry.
2. The next `find("P1")` has had no simulated time elapse, so it hits; `sourceLoads` stays 1.
3. `ticker.advance(6 minutes)` moves Caffeine's clock past the configured 5-minute TTL. The next `find("P1")` misses and creates `generation=2`.
4. `find("P2")` and `find("P3")` introduce two more keys. When needed, the provider evicts entries to respect the two-item budget.
5. After `cleanUp()`, `estimatedSize() <= 2` evaluates to `true`. The demo **intentionally avoids asserting** specifically whether `P1`, `P2`, or `P3` was evicted: eviction policies can pick different entries.

Thus, the demo proves **both entry age and entry count** on a cache instance. It does not measure heap bytes, use Redis, synchronize across JVMs, or handle database updates. Those requirements need dedicated policies.

### Want a simpler production configuration?

When no fake ticker is needed, you can typically **omit `@Bean CaffeineCacheManager` from the demo** and use `spring.cache.caffeine.spec` alongside `spring.cache.cache-names` as shown in section 4. Never keep a custom bean while assuming auto-configuration properties will replace it. In production, choose TTLs and entry counts based on real data rather than copying 2 or 5 minutes verbatim from this lesson.

## 6. Redis: per-key TTL and server-wide memory limits

Redis is a **networked shared cache store**, so its capacity budget differs from local Caffeine:

- Local Caffeine: memory **per JVM**, multiplying across deployed replicas.
- Redis: memory on the **Redis node/cluster**, shared across applications if sharing an instance.
- Spring Data Redis `RedisCacheManager`: manages caches by name, prefix, and serializer; TTLs are applied to cache keys per configuration.
- Redis server: `maxmemory` and `maxmemory-policy` determine behavior when the configured memory threshold is reached.

Do not confuse `spring.cache.redis.time-to-live` with `maxmemory`: one governs entry age; the other governs the Redis server's memory ceiling.

### Example TTL configuration in Spring Boot

Once the application includes the Spring Data Redis dependency, configures connectivity, and uses `RedisCacheManager`, you can set:

~~~properties
spring.cache.type=redis
spring.cache.cache-names=products,referenceData
spring.cache.redis.time-to-live=10m
spring.cache.redis.cache-null-values=false
spring.cache.redis.use-key-prefix=true
~~~

These properties **illustrate Redis provider configuration** and cannot run in the Caffeine demo above without adding the Redis dependency and server. `time-to-live=10m` is a fixed entry TTL under Boot's configuration; review which caches can share the same policy. Slowly changing reference data and frequently updated pricing data may require separate TTLs.

You can set per-cache-name TTLs via Java configuration:

~~~java
// Illustrative configuration snippet; requires Spring Data Redis dependency
// and a RedisConnectionFactory in the application.
@Bean
RedisCacheManager cacheManager(RedisConnectionFactory factory) {
    RedisCacheConfiguration defaults =
            RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofMinutes(10))
                .disableCachingNullValues();

    return RedisCacheManager.builder(factory)
            .cacheDefaults(defaults)
            .withCacheConfiguration(
                "referenceData",
                defaults.entryTtl(Duration.ofHours(1)))
            .build();
}
~~~

To make this snippet compile, import `RedisCacheManager`, `RedisCacheConfiguration`, `RedisConnectionFactory`, `Duration`, `Bean`, and the corresponding dependency; this is **not a standalone runnable file**. Example policy: 10 minutes by default, and 1 hour specifically for `"referenceData"`.

According to Spring Data Redis, the default cache configuration has **key expiration = none** unless you set a TTL; null caching and prefixes also have their own defaults. Do not assume Redis cache entries disappear automatically after a finite period if nothing was configured.

### TTL is not TTI

Standard TTL in Redis is set/reset on write; a read via `GET` **does not** extend it automatically. If time-to-idle-like behavior is desired, Spring Data Redis supports `enableTimeToIdle()` in compatible versions, using Redis's `GETEX` command to read and renew TTL.

Check at minimum:

1. Redis server **6.2** or newer supporting `GETEX`.
2. `RedisCacheConfiguration` has a TTL set and TTI enabled per the version's API.
3. **Every** related read/write path uses operations with renewal semantics; a module issuing plain `GET` will not reset the timer.
4. TTI keeps hot keys alive longer without guaranteeing absolute freshness.

Do not blindly enable TTI across every cache hoping to save memory, because hot keys can outlive write-based TTLs.

### `maxmemory` and Redis eviction policies

Example configuration **on the Redis server** (not a Spring annotation):

~~~conf
maxmemory 512mb
maxmemory-policy allkeys-lru
~~~

Meaning: set a Redis memory ceiling and use an eviction policy to select keys when needed. `allkeys-lru` uses approximated least-recently-used selection; Redis also offers policies such as LFU, random, and the `volatile-*` group considering only keys with a TTL. Never claim a single policy is best for every workload.

Key points to remember:

- `maxmemory` is a **Redis node configuration ceiling**, not a private 512 MiB limit just for the `"products"` cache.
- `allkeys-*` policies can evict even keys without a TTL if they live in the Redis dataset governed by that policy.
- `volatile-*` only considers keys that have an expiration set; if eligible keys are lacking, Redis may fail to free enough memory and write commands can fail.
- With `noeviction`, Redis generally rejects commands that increase memory once the limit is reached, depending on the command and configuration.
- Redis does not automatically know “app A's keys matter more than app B's” when applications share an instance and policy.
- Overhead, replica buffers, fragmentation, and memory accounting cause actual memory usage to differ from raw payload size; monitor Redis metrics rather than estimating value sizes alone.

In Redis Cluster, evaluate limits and memory pressure **per node/shard**. An uneven keyspace distribution can overload one shard even when cluster-wide capacity has headroom.

### Prefixes and key counts

By default, Spring Data Redis typically prefixes cache keys with the cache name, such as:

~~~text
products::P1
referenceData::currency:USD
~~~

Prefixes reduce collisions across caches, yet do not limit cardinality by themselves. If keys are built from raw search queries, tenant IDs, user IDs, pages, sorts, and timestamps, combinations can still explode. Never strip key prefixes arbitrarily when multiple caches or applications share Redis.

In operations, prefer controlled `SCAN` for sampling or inspecting the keyspace instead of `KEYS *` on a large production Redis. When `RedisCacheWriter` clears an entire region, verify the batch strategy; Spring Data Redis documentation describes defaults involving `KEYS`/`DEL` versus `SCAN` options by driver and topology.

## 7. Preventing unbounded key growth by design

A `maximumSize` setting is only the last line of defense. For a cache to be effective, keys themselves must have a **high enough reuse rate**.

### Dangerous key patterns

~~~java
// ANTI-PATTERN: every call generates a different key.
@Cacheable(cacheNames = "reports", key = "#p0 + ':' + T(java.util.UUID).randomUUID()")
public Report find(String id) {
    return repository.load(id);
}
~~~

A fresh UUID key yields almost zero hits while still forcing the provider to pay insertion and eviction costs on every request. Likewise, needlessly adding `System.currentTimeMillis()`, `traceId`, `requestId`, nonces, or access tokens into keys explodes cardinality and can expose sensitive data that should not be stored or logged.

### Query combination explosions

A search API with parameters:

~~~text
tenant × keyword × filter × sort × page × pageSize × locale
~~~

If every combination is cached, hundreds of thousands of keys can arise even when each dimension has only a few values. Ways to control this:

- Cache hot queries with high reuse, rather than caching every raw query.
- Canonicalize semantically equivalent syntax, such as normalizing filter ordering that does not alter query results before generating the key.
- Cap `pageSize`/`page`, keyword length, and filter count in the API contract; validate independently of the cache.
- Scope personalized results properly, and consider not caching overly specific queries.
- Keep query-cache entry limits and TTLs tighter than those of reference-data caches.
- Avoid per-user dynamic cache names when keys or partitioning solve the problem cleanly.

When canonicalizing, preserve exact semantics: if search keywords are case-sensitive, blindly lowercasing can produce wrong cache hits. Do not truncate IDs down to a single 32-bit hash code due to collision risk; if hashing long keys, evaluate collision probability and keep full identity where required.

### Overly large cached results

~~~java
// ANTI-PATTERN: every search result puts the entire list into the cache.
@Cacheable(cacheNames = "allOrders", key = "#p0")
public List<Order> findAllOrders(String tenantId) {
    return repository.findEveryOrderForTenant(tenantId);
}
~~~

A tenant with millions of orders can create a massive entry, triggering GC pauses, serializer CPU spikes, network latency, or Redis evictions. Bound queries, return paginated results, cache slim DTOs, or cache individual entities where sensible. Keep in mind that caching paginated results also increases key count; budget key cardinality alongside entry size.

Never cache sensitive payloads or entire entity graphs containing lazy-loading associations without clear justification. Retained heap size can be vastly larger than the visible JSON response.

## 8. Data retained too long causes staleness and business bugs

Even with ample memory, a living entry can **no longer be accurate**.

~~~text
T0: find("P1") -> price=100; caches P1
T1: DB updates price=120
T2: find("P1") -> cache hit price=100
~~~

Lowering TTL to 5 minutes only bounds *how long staleness can last* under certain assumptions; it does not guarantee “reading right after an update sees fresh data.” If **read-your-writes** is required, use `@CachePut` with the same key and projection or `@CacheEvict` after a successful update, coordinated properly with transactions.

~~~java
// Illustrative: find and update share the same cacheName and key by productId.
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String productId) {
    return repository.findById(productId);
}

@CacheEvict(cacheNames = "products", key = "#p0")
public void updatePrice(String productId, long price) {
    repository.updatePrice(productId, price);
}
~~~

This snippet is illustrative inside a Spring service with a repository; it is not a standalone program. `@CacheEvict` evicts by default after the method completes normally. If a transaction rolls back or cache updates occur at the wrong commit boundary, cached data can become inconsistent. Check transaction-aware configuration, after-commit events, or explicit synchronization strategies.

**TTL limits do not replace authorization checks:** a user whose permissions were revoked can keep receiving cached entries if authorization sits **only inside the body** of a `@Cacheable` method, because cache hits skip the method body. Enforce authorization on a path that always runs, and partition keys by trusted scope when content varies by user or tenant.

### `expireAfterAccess` can keep stale data alive indefinitely

An entry read continuously may never sit idle long enough to expire, even after the source data has changed. That is why lifetime choices must follow the **freshness contract**, not hit ratio alone. If data must be revalidated after a maximum elapsed period, consider `expireAfterWrite`, refresh/invalidation, or version checks.

### Eviction does not happen precisely when business logic needs it

When capacity fills up, the provider may evict whichever entry its policy selects. If it keeps stale entry `"P1"` while evicting valid entry `"P2"`, staleness remains unresolved. Capacity eviction **manages resources**; it does not verify whether business data is fresh or stale.

## 9. Designing TTLs by data category

One TTL for the entire application is rarely appropriate.

| Data category | Characteristics | Starting-point policy guide |
| --- | --- | --- |
| Slowly changing reference config | Heavily read, rarely updated | Longer TTL, explicit eviction on changes |
| Pricing, stock, workflow state | Frequently updated | Short TTL, prefer invalidation after updates |
| Search/pagination results | High cardinality, uneven reuse | Short TTL, tight capacity, cache only hot queries |
| User/tenant profiles | Sensitive/partitioned data | Trusted-scope keys; TTL + authorization/invalidation |
| Negative cache (`not found`) | Avoids repeated queries for missing IDs | Deliberate short TTL so newly created data appears promptly |
| Expensive computed reports | Slow loader, brief staleness acceptable | TTL/refresh per SLA, stampede protection |
| Data requiring immediate exactness | Zero staleness tolerated | Consider not caching, or strict invalidation/consistency |

This table is a **thinking guide**, not ready-to-apply TTL numbers. Decide based on update rate, size, staleness tolerance, load cost, key count, traffic level, and invalidation capability.

Large caches can also suffer **cache stampedes** when many keys expire simultaneously. Consider adding TTL jitter for some key types if supported by the provider or application policy, or scheduled warm refreshes. `@Cacheable(sync=true)` coordinates concurrent misses for the same key within the scope supported by the provider, yet is not a cluster-wide exactly-once guarantee.

## 10. Observing caches in production

You cannot pick the right `maximumSize` and TTL by intuition alone. Measure at minimum:

| Metric | Question |
| --- | --- |
| `estimatedSize`/entry count | How many entries is the cache currently holding? |
| Hit/miss rate | Is data being reused, or are many one-off keys being stored? |
| Eviction count/weight | Is the cache full and evicting entries frequently? |
| TTL expirations / post-expiry misses | Are synchronized expiry waves overloading the backend? |
| Load time / errors | On misses, are source queries slow or error-prone? |
| Heap used / GC pauses | Is the local cache putting pressure on the JVM? |
| Redis `used_memory`, keyspace, evicted keys | Is the shared cache approaching its memory threshold? |
| Redis latency / network / serialization | Are oversized values inflating round-trip times? |
| Stale reads / age / version | Do living entries still honor the freshness contract? |
| Cardinality by cache name / tenant / query class | Which key categories are growing abnormally? |

Caffeine exposes internal stats when `recordStats()` is enabled. With Spring Boot Actuator and Micrometer, metric collection also depends on dependencies, the cache manager, and binding configuration; never assume a specific metric name exists in every project. Redis also provides server metrics and Spring Data Redis statistical snapshots in supported configurations.

Never attach **raw keys, user IDs, access tokens, or query text** as metric tags because that explodes monitoring cardinality and can leak sensitive data. Use bounded tags instead, such as `cacheName`, result category, or well-defined tenant tiers.

### Capacity auditing process

1. List all valid **cache names** and their owners; prevent unbounded dynamic region creation.
2. Document key schemas and participating parameters; estimate unique keys per day.
3. Measure actual serialized or retained value sizes, including worst-case outliers.
4. Set memory/key-count budgets per JVM/Redis node; reserve headroom for GC, traffic peaks, and other components.
5. Set TTL/eviction and measure hit rate alongside source load. Increase `maximumSize` only when evidence shows hit-rate gains justify the cost.
6. Set alerts for sustained key or memory growth, aggressive eviction, rising source misses, and degraded p95 latency.
7. Test warm-up/cold starts, multi-replica redeployments, Redis evictions, and cache flushes—not only steady-state traffic.

### Trade-off: smaller size is not always better

An undersized cache continuously evicts useful keys, increasing misses and source-read latency. An oversized cache retains rarely used keys and inflates resource costs. The sweet spot is typically found experimentally: vary capacity and compare hit rate, load rate, p95 latency, GC, and cost. A configuration number is meaningful only when tied to a **measured workload**.

## 11. Operating Redis and multi-instance deployments

When an application runs multiple pods:

~~~text
App A (local Caffeine: 10k entries)
App B (local Caffeine: 10k entries)
App C (local Caffeine: 10k entries)
            |
            +---- all read from the source DB
~~~

Total local entries can reach roughly 30k across three independent caches, including duplicated entries. Memory is consumed **per JVM**. With shared Redis, all three apps share one keyspace and TTL, yet must account for serialization, networking, Redis memory policies, and the risk of Redis becoming a bottleneck.

Do not set Redis `maxmemory` too close to physical RAM; Redis also needs room for background operations, buffers, replication/client queues, and fragmentation. Monitor real metrics and workloads. If Redis hosts both **evictable cache data** and **durable state** such as critical queues or sessions, shared eviction policies require extreme care; many architectures isolate workloads with different guarantees.

An application running multiple versions during rollout may change cache key/value schemas. Without namespace versioning or a cleanup plan for old keys, long-lived entries can trigger deserialization errors after deployment. Plan migration/invalidation and keep TTLs bounded to limit the lifespan of older versions.

### Bounding Redis key count per cache name?

Redis `maxmemory` is a node-wide limit, **not a per-cache-name quota** for Spring. If strict quotas are needed per application, tenant, or cache name, you may need separate instances/clusters, application-level admission rules, or dedicated key management. Never assume the `"products::"` prefix makes Redis account for the `products` region's memory separately.

## 12. Common pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| JVM heap keeps growing | Simple concurrent-map cache with no TTL/capacity | Choose a provider with bounded size/expiration; profile heap |
| Low hit rate despite a huge cache | Every request generates a new key | Audit `requestId`, timestamps, raw queries, and key cardinality |
| Redis key count grows continuously | No TTL or overly long TTL | Set appropriate TTLs and inspect the keyspace |
| Caffeine OOMs before reaching `maximumSize` | Oversized entries or objects retained elsewhere | Control payloads; evaluate `maximumWeight` and heap profiling |
| Stale data despite continuous reads | `expireAfterAccess` keeps extending entry lifetime | Use write-based TTL and invalidation/versioning |
| Cache hit after a user's permissions were revoked | Authorization checked only inside the method body | Check permissions on a path that always executes; invalidate |
| Increasing TTL raises hits yet returns old prices | Missing eviction after updates | Coordinate `@CachePut`/`@CacheEvict` and transactions |
| Caffeine eviction does not match expected “LRU” | Provider uses its own admission/eviction policy | Test behavior/budgets rather than guessing specific keys |
| Redis rejects writes despite `maxmemory` | `noeviction` or no eligible keys for `volatile-*` | Review Redis policy/TTL and workload characteristics |
| Redis runs out of space despite short TTLs | Rapid key generation, large values, or fragmentation | Measure entry counts/sizes; reduce cardinality and memory |
| Old data causes errors after deployment | Incompatible cache value serializer/schema version | Version key namespaces, bound TTL, plan migrations |
| Metric tags explode cardinality | Attaching raw keys to metrics | Use bounded tags; never use user IDs or raw queries |

## 13. Self-check exercises

**Exercise 1.** A search API receives millisecond-precision timestamps and uses the full timestamp as the cache key. What can happen?  
**Answer:** cardinality grows rapidly and hit rate drops near zero. Strip parameters that do not affect results, or reduce granularity carefully while preserving semantics; if data truly differs per millisecond, caching every request may be inappropriate.

**Exercise 2.** Does Caffeine configured with `maximumSize=5000` guarantee the cache uses at most 5,000 KiB of RAM?  
**Answer:** no. That is an entry-count threshold, not bytes. Key/value sizes and metadata still determine heap usage.

**Exercise 3.** An entry is read every second, and the cache has `expireAfterAccess=10m`. Can it survive for days?  
**Answer:** yes, if accessed continuously and not removed by capacity eviction or invalidation. It is not an absolute write-based TTL.

**Exercise 4.** A Redis cache has `time-to-live=5m`, yet the server sets no `maxmemory`. Does that guarantee low RAM usage?  
**Answer:** no. TTL expires entries eventually, yet key/value creation rates can exceed capacity within the TTL window; configure server memory budgets and monitor.

**Exercise 5.** Product P1's price changes from 100 to 120 after being cached. Should you only shorten the TTL, or do more?  
**Answer:** if immediate visibility of the new price is required, use put/evict/invalidation tied to the update and transaction. TTL alone only bounds data age under steady conditions.

**Exercise 6.** Each pod has Caffeine `maximumSize=10k`; there are 8 pods. Does `maximumSize` mean 10k entries cluster-wide?  
**Answer:** no. The limit applies **per cache instance**; multiple pods have independent local budgets and keyspaces.

**Exercise 7.** Is it safe to cache a million orders inside one entry if there are only 10 keys?  
**Answer:** it can still be far too large. Account for value/heap size, query bounds, DTOs, and pagination; few keys do not mean cheap.

**Exercise 8.** Why is `@Cacheable` insufficient to set TTL?  
**Answer:** the annotation describes the operation, while TTL/capacity/eviction are configured by the provider and `CacheManager`. Backends differ in capabilities and defaults.

**Exercise 9.** Redis has `maxmemory-policy=volatile-ttl`, yet most keys have no expiration. What is the risk?  
**Answer:** keys without a TTL are ineligible under `volatile-*` policies. When too few eligible keys can be evicted, writes may fail.

**Exercise 10.** Why is measuring hit rate alone insufficient?  
**Answer:** the cache may still be oversized, serve stale data, increase GC, cause eviction storms, or overload Redis. Also measure size, load time, latency, memory, key growth, and freshness.

## 14. Safe deployment checklist

Before shipping a cache to production, confirm:

- [ ] Cache names have a finite scope, clear owners, and a defined purpose.
- [ ] Keys accurately reflect tenant/user/projection whenever output varies by scope, without unnecessary sensitive data.
- [ ] Estimated count of **distinct keys**, not just request volume.
- [ ] Measured or bounded typical and worst-case entry sizes.
- [ ] Confirmed the provider genuinely supports the expected capacity limits/TTL, without relying on implicit defaults.
- [ ] `maximumSize`/`maximumWeight` or Redis limits are sized for the right scope (cache instance vs. Redis node).
- [ ] TTL/TTI match the freshness SLA; hot keys cannot stay stale indefinitely by accident.
- [ ] Source update/delete paths have clear `@CachePut`, `@CacheEvict`, or invalidation strategies.
- [ ] Sudden cache misses and concurrent requests for the same key cannot overwhelm downstream systems.
- [ ] Metrics/alerts for size, hits/misses, evictions, load time, GC, or Redis memory are in place.
- [ ] Tested expiration, capacity bounds, multi-instance behavior, rollbacks, and data mutations.
- [ ] Have a cleanup plan for old data after changing key/value serializers and deploying multiple versions.

## Official references

- Spring Framework – **Cache Abstraction** and declarative caching: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework – **Cache Annotations** and constraints on `@Cacheable`: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Boot – **Caching**, Caffeine specs, and Redis properties: https://docs.spring.io/spring-boot/reference/io/caching.html
- Spring Data Redis – **Redis Cache**, TTL, TTI, prefixes, and batch strategies: https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html
- Caffeine – **Eviction** (`maximumSize`, `maximumWeight`, expiration): https://github.com/ben-manes/caffeine/wiki/Eviction
- Redis – **Key eviction** (`maxmemory`, eviction policies): https://redis.io/docs/latest/develop/reference/eviction/

**Conclusion:** governing a cache requires three things simultaneously: **bounding entry count and data size**, **setting appropriate lifecycle/freshness policies**, and **actively invalidating when the source changes**. Spring Cache provides the abstraction; the provider enforces memory policies. Do not simply raise TTLs to chase hit rate, and do not merely add `maximumSize` assuming data will stay accurate. Measure cost, key cardinality, freshness, and behavior in your real deployment environment.