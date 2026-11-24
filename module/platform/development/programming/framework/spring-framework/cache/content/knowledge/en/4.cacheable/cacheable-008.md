# Limitations of Using Multiple `cacheNames` as a Multi-Tier Cache in `@Cacheable`

## 1. Architectural Conclusion to Remember

In the Spring Framework, declaring:

```java
@Cacheable(cacheNames = {"productsL1", "productsL2"}, key = "#p0")
public Product findProduct(String productId) {
    return repository.findById(productId);
}
```

means **a single cache operation is associated with multiple named caches**. On the normal synchronous access path, Spring looks up the result in the order the caches are resolved, returns on a hit, and stores the new result in the associated caches when loading from the method. This declaration **is not a full contract for a multi-tier cache (L1/L2, near-cache/remote-cache)**.

A true L1/L2 system must define: on an L1 miss, fall back to L2; on an L2 hit, whether and when to promote the result back to L1; which cache updates first; per-tier TTL/capacity limits; synchronized deletion when source data changes; cross-node consistency; and what happens when the lower-tier cache fails. `cacheNames` by itself neither describes nor guarantees those policies.

In this lesson, "L1" refers to the closer storage layer, typically local/in-process; "L2" refers to the remote/shared storage layer, typically Redis. Naming caches `productsL1` and `productsL2` does not automatically turn them into two coordinated tiers.

## 2. The Real Contract of `@Cacheable` with Multiple Names

Entries in `cacheNames` are **logical names of `Cache` instances**, not a list of `CacheManager` beans or backend priority settings. `CacheResolver` resolves the `Cache` objects; by default this usually goes through a single `CacheManager`. Spring uses the same invocation key across the selected caches.

```text
@Cacheable(cacheNames={"productsL1","productsL2"}, key="#p0")
                       │
                 CacheInterceptor
                       │
                 CacheResolver
                       │
             [Cache "productsL1",
              Cache "productsL2"]
                       │
            Look up in order
                       │
             Hit? return cached value
             No hit? invoke method
                       │
            Populate result into associated caches
```

Under **normal synchronous access**, consider these states:

| State before read | Outcome | Notable detail |
| --- | --- | --- |
| Both caches miss | Executes target method, obtains result, and puts into the specified caches | This populates multiple caches from one result; it does not prove an L1/L2 architecture |
| First cache hits | Immediately returns first cache's value, skips method | Does not verify whether a later copy is newer or still valid |
| First cache misses, later cache hits | Returns later cache's result, does not call source | Spring docs describe updating other caches missing the result; do not treat that description as a dedicated multi-tier promotion/coherency contract |
| Two caches hold different values for the same key | The value in the cache hit first wins according to lookup order | No version comparison or mechanism to pick the newest copy |
| Earlier cache throws access error | Error is handled per `CacheErrorHandler`/provider | No built-in guaranteed "if L1 fails, fall back to L2" policy |
| Value is evicted or expires in one cache | The other cache does not necessarily change | Per-cache TTL/eviction is a backend policy, not an automatic dependency |

According to Spring documentation, caches missing the value can be populated during the synchronous cache flow; **do not infer that asynchronous reads, failures, concurrency, or multi-node setups all guarantee two-tier synchronization**. Cache entries expire independently, and caches do not share a single source of truth merely by appearing together in the `cacheNames` array.

From an API perspective, `@Cacheable({"a","b"})` is better suited to describe **multiple regions sharing results** than claiming "A is L1, B is L2." The order is a **lookup order**, not a full runtime tiering policy.

## 3. What `cacheNames` Does Not Provide

### 3.1. Does not automatically pick two different backends

```java
@Cacheable(cacheNames = {"localProducts", "redisProducts"}, key = "#p0")
public Product findProduct(String id) {
    return repository.findById(id);
}
```

The snippet above only declares **two cache names**. It does not automatically wire Caffeine for the first name and Redis for the second. Both must be resolved by `CacheResolver` into valid `Cache` instances from existing configuration. With a manager that only knows one name, the other name may fail to resolve and cause the operation to fail; with a manager that auto-creates every region, both may end up on the exact same backend.

If two separate `CacheManager` beans are configured, `@Cacheable(cacheManager="...")` normally selects **one manager for the operation**. A custom `CacheResolver` can return multiple `Cache` objects from different managers, yet that still does not implement tier prioritization, promotion, coherence, and failure handling for a complete multi-tier system.

### 3.2. No contract that "L2 hit always promotes into L1"

An L1/L2 cache is commonly expected to work like:

```text
read(key)
  ├─ L1 hit  → return
  └─ L1 miss
       ├─ L2 hit  → copy data into L1 → return
       └─ L2 miss → read source → write L2 → write L1 → return
```

That is a **tiered caching algorithm**. By contrast, `@Cacheable` is defined as caching a method call across a list of `Cache`s. Even though Spring documentation mentions populating caches missing the value in standard scenarios, the annotation offers no API to set custom promotion rules, pick versions by timestamp, control per-tier write-through/write-behind, or guarantee promotion succeeds if one backend fails. Do not rely on behavior observed in one provider as a promise across all providers.

### 3.3. Does not manage consistency when two tiers have different TTLs

Suppose:

- In-memory L1 keeps records for 20 seconds.
- Redis L2 keeps records for 5 minutes.
- The database updated the product to a new version.

If L1 is cleared while L2 still holds stale data, the system can read L2 again and refill **stale data** into L1. Increasing the hit rate does not mean reading accurately. Conversely, when L1 holds stale data while L2 is already fresh, the first cache hit hides the newer version behind it.

TTL is a policy of each cache provider (`Caffeine`, `RedisCacheManager`, etc.); the Spring Cache abstraction has no shared TTL applied by the `cacheNames` array. TTL only bounds lifetime; invalidation, versioning, and business freshness must be managed separately.

### 3.4. Does not propagate invalidation across all nodes

`@CacheEvict(cacheNames={"productsL1","productsL2"}, key="#p0")` requests eviction of the two regions resolved in **that invocation**. If L1 lives in each JVM's memory, evicting on node A does not directly delete node B's local L1 copy. Nor does a shared distributed L2 automatically broadcast refresh notifications to all local L1 caches.

A distributed system needs an explicit policy: post-commit events, pub/sub or a message bus to signal invalidation; versions or timestamps to guard against out-of-order stale writes; fallback TTL in case events are lost; and multi-instance testing.

### 3.5. No atomic transaction across caches and database

When writing to multiple caches, the operations are not equivalent to an atomic commit. If writing L1 succeeds while writing L2 fails or the database rolls back, the two stores can diverge. Transaction-aware caches help defer certain changes until after the corresponding Spring transaction commits, but they do not turn database + Redis + local cache into an automatic 2-phase commit system.

### 3.6. Does not solve stampedes or cache failures on its own

Multiple concurrent requests missing at once can all hit the source. In `@Cacheable`, `sync=true` requires **only a single cache**, so the following declaration is invalid:

```java
// WRONG: sync=true only accepts a single cache.
@Cacheable(cacheNames = {"productsL1", "productsL2"}, sync = true)
public Product findProduct(String id) {
    return repository.findById(id);
}
```

Even with a single cache, `sync=true` is a hint to the provider, not a substitute for a distributed lock when system-wide guarantees are needed. Anti-stampede policies, load throttling, and bypassing failed caches must be designed and tested per backend.

## 4. Runnable Example: Two Cache Names Can Still Return Stale Data

This example uses Spring Framework **6.2.16**, Java 17+, and `ConcurrentMapCacheManager` purely to demonstrate **multi-name lookup semantics within a single process**. Both regions are local memory; naming them `l1Products`/`l2Products` does not prove two backends or a tiered cache system.

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>multi-cache-names-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.16</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Create `src/main/java/MultiCacheNamesDemo.java`:

```java
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class MultiCacheNamesDemo {

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("l1Products", "l2Products");
    }

    @Bean
    ProductLookup productLookup() {
        return new ProductLookup();
    }

    public static class ProductLookup {
        private final AtomicInteger sourceCalls = new AtomicInteger();

        @Cacheable(cacheNames = {"l1Products", "l2Products"}, key = "#p0")
        public String find(String sku) {
            int count = sourceCalls.incrementAndGet();
            return "db-" + sku + "-call" + count;
        }

        public int sourceCalls() {
            return sourceCalls.get();
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(MultiCacheNamesDemo.class)) {
            var service = context.getBean(ProductLookup.class);
            var manager = context.getBean(CacheManager.class);

            Cache l1 = Objects.requireNonNull(manager.getCache("l1Products"));
            Cache l2 = Objects.requireNonNull(manager.getCache("l2Products"));
            String key = "P1";

            // Both miss: calls the source once, writes to both caches.
            System.out.println("Read 1: " + service.find(key));
            System.out.println("Stored L1: " + (l1.get(key) != null));
            System.out.println("Stored L2: " + (l2.get(key) != null));

            // L1 miss, L2 still hits: no need to call the source again.
            l1.evict(key);
            System.out.println("Read 2: " + service.find(key));
            System.out.println("Source calls: " + service.sourceCalls());

            // Two conflicting copies: the first name determines the hit.
            l1.put(key, "STALE-L1");
            l2.put(key, "FRESH-L2");
            System.out.println("Read 3: " + service.find(key));
            System.out.println("Source calls: " + service.sourceCalls());
        }
    }
}
```

Run from the directory containing `pom.xml`, on a machine with Maven and JDK 17+ installed:

```bash
mvn -q compile exec:java -Dexec.mainClass=MultiCacheNamesDemo
```

Lines printed by the program (excluding Maven's own logs):

```text
Read 1: db-P1-call1
Stored L1: true
Stored L2: true
Read 2: db-P1-call1
Source calls: 1
Read 3: STALE-L1
Source calls: 1
```

At `Read 1`, both regions are populated with the same value. After evicting only L1, `Read 2` still retrieves the copy from the remaining cache without calling the source again. Finally, we intentionally place `STALE-L1` and `FRESH-L2` for the same key; `Read 3` returns the stale copy because the first cache hits. Spring does not compare freshness, versions, or timestamps across the specified caches.

The program demonstrates that **two different versions of the same key can coexist simultaneously**, requiring dedicated consistency rules. It does not measure latency or guarantee that a given implementation will always promote L2 → L1 under all conditions.

## 5. Two Commonly Confused API Limitations

### 5.1. `CompositeCacheManager` is not a key-level two-tier cache

`CompositeCacheManager` takes multiple `CacheManager` instances and finds the manager **capable of supplying a region by name**. That is fallback when **resolving a cache name**, not a pipeline where "if cache L1 misses the key, try cache L2 for the same key."

```java
// Configuration illustration only, not a standalone program.
@Bean
CacheManager cacheManager(
        CacheManager caffeineManager,
        CacheManager redisManager) {
    return new CompositeCacheManager(caffeineManager, redisManager);
}
```

If the first manager returns a `Cache` for the name `products`, resolution can stop right there; a subsequent `get(key)` miss **does not make CompositeCacheManager search for the key in the second manager**. Delegates must return `null` when they do not recognize a region name so resolution falls through. A provider that auto-creates regions for any name can shadow subsequent managers.

### 5.2. Asynchronous and reactive access may not traverse all caches

Since Spring Framework 6.1, `@Cacheable` supports return types like `CompletableFuture` and supported reactive types. However, the `Cacheable.cacheNames` Javadoc warns that with caches whose **miss is determined lazily** (such as asynchronous access to Redis), Spring may **not continue checking subsequent cache names**. Conversely, caches able to determine misses eagerly (such as Caffeine in an appropriate mode) are more amenable to multi-name access.

Therefore, the synchronous Java example above **is not proof** that the fallback order behaves identically with `Mono`, `Flux`, `CompletableFuture`, or `Cache.retrieve(...)` across all backends. When an async L1/L2 contract is needed, test against the exact provider, Spring version, and runtime configuration.

## 6. How Should a Real L1/L2 Cache Be Structured?

A clean approach is to provide **one logical `Cache` object** named `products`, backed internally by an implementation coordinating the two backends under a dedicated contract. Outside in the service, all that remains is:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public Product findProduct(String id) {
    return repository.findById(id);
}
```

Inside the cache-layer implementation, you decide how reads, writes, evictions, versioning, and error handling work:

```text
Cache "products" (one logical cache, implementation coordinates two tiers)
    get(key):
        if valid L1 hit             → return
        if L1 miss, valid L2 hit    → promote to L1 → return
        if both miss                → report miss
    put(key, value):
        write per chosen policy, confirm/monitor each tier
    evict(key):
        invalidate both tiers, signal L1 on other nodes
    clear():
        invalidate all keys in the region according to scope
```

`@Cacheable` remains responsible for calling the underlying method when the logical cache reports a miss; the cache implementation coordinates L1/L2. This is a **target algorithm**, not standalone Java code, and must be completed in full compliance with the `org.springframework.cache.Cache` contract. If replacing it with service-layer orchestration instead, clearly separate read, write/invalidate, and observability logic.

Illustrative example **solely for the get path** inside an implementation, where `nearCache` and `remoteCache` are two pre-configured `Cache` objects:

```java
// Illustration snippet inside a custom cache; not a standalone runnable file.
public Object readThroughLayers(Object key) {
    Cache.ValueWrapper near = nearCache.get(key);
    if (near != null) {
        return near.get();
    }

    Cache.ValueWrapper remote = remoteCache.get(key);
    if (remote != null) {
        Object value = remote.get();
        nearCache.put(key, value); // Intentional promotion.
        return value;
    }
    return null; // This example omits distinguishing cached-null from a miss.
}
```

The simple snippet above **is not ready for production**: you must distinguish cached-null from a cache miss, decide serialization/value types, TTL, timeouts, concurrent operations, cache errors, versioning, anti-stampede strategies, and stale refreshes. In a real `Cache.get(key)` implementation, do not lose hit-null information by simply returning `Object` as in the snippet.

A concrete strategy:

1. **Reads:** an L1 hit must verify the value is still valid/current in version; on miss, read L2; on L2 hit, promote to L1 with L1's TTL and matching version; if both miss, load from source and write in the chosen order.
2. **Source writes:** persist to the database, and publish/invalidate cache entries only via an appropriate post-commit mechanism; do not treat a sequence of puts as an atomic distributed transaction.
3. **Invalidation:** evict L2 and instruct local L1 instances to evict the corresponding key; account for dropped, duplicated, or out-of-order events. TTL and versioning serve as complementary safeguards.
4. **Data protection:** if keys include tenant/user/locale, every tier must share the same key structure and proper authorization; prevent cached mutable objects from unintended modification.
5. **Resilience:** define policies for L1 errors, L2 timeouts, cache put failures, or loader failures; add metrics and distributed tests.

## 7. When to Use Multiple `cacheNames` vs. When You Need Tiered Caching

| Need | Choice | Why |
| --- | --- | --- |
| A result may need to appear in multiple logical regions | `@Cacheable(cacheNames={"a","b"})` if genuinely needed and tested | Declares multiple caches for one call, sharing key and value |
| Need a local cache and a remote cache with reliable read-through/promotion | Custom composite `Cache` or explicit layer orchestration | Explicitly defines order, fallback, promotion, and failure behavior |
| Selecting different backends for different **types** of caches | `CacheManager`/`CacheResolver` configured by name and domain | Routes caches; does not imply multiple tiers for the same key |
| Caching one result while preventing concurrent duplicate loaders | `@Cacheable(sync=true)` with **one** supporting cache | Sync mode is restricted to one cache and depends on provider |
| Multiple instances with per-node L1 and shared Redis L2 | Composite cache + multi-node invalidation, or drop L1 if unneeded | `@CacheEvict` on one node does not clear L1 on other nodes |
| Async/reactive access with Redis at one position in the chain | Verify eager/lazy miss support; typically use a custom adapter | Do not assume `cacheNames` always traverses every tier |

**Do not choose multiple `cacheNames` just to "tack on Redis to make it faster."** Adding another cache also adds stale-data possibilities, write overhead, failure modes, and invalidation complexity. Choose the architecture based on quantified consistency and latency goals.

## 8. Checklist and Mandatory Tests When Considering a Two-Tier Cache

Before deploying to production, document the contract of each tier: key/value types, provider, lifetime, local/shared scope, null-caching rules, refresh timing, memory limits, restart recovery, error handling, and invalidation ownership. Then test at minimum these scenarios:

| Scenario | Outcome to observe |
| --- | --- |
| L1 miss, L2 miss | Reads source once per loader policy; writes to configured tiers |
| L1 miss, L2 hit | Returns accurate value and promotes to L1 per the **designed** contract |
| Stale L1 hit, fresh L2 hit | Explicit version/invalidation rules exist; does not silently return stale data when strong guarantees are required |
| Source update/delete | Tiers and other nodes do not keep serving stale data beyond allowed bounds |
| Concurrent misses | Controlled load counts, read-vs-evict races, no resurrecting stale values |
| L2 timeout or unavailable | Defined behavior: DB fallback, fail closed, bypass cache, or bounded stale serving |
| L1 restart or new instance | Cold start works; does not assume L1 is pre-warmed |
| Differing L1 and L2 TTLs | Does not extend stale data lifetime beyond contract |
| Async/reactive | Verify real cache path on each backend, especially lazy miss detection |
| Transaction rollback | Does not publish new values when source changes fail to commit |
| Null/empty caching and serialization | Does not confuse hit-null with miss; data compatible across tiers |

Measure per-tier hit/miss rates, loader execution counts, p95/p99 latency, promotion rates, provider errors, eviction counts, and actual staleness windows. A cache that "looks" multi-tiered because its hit rate is high yet serves stale values violates the business contract.

## 9. Misconceptions to Avoid

- **"Multiple names mean multiple tiers."** Names resolve to caches; no L1/L2 management is included.
- **"Putting Caffeine before Redis gives a proper near-cache."** Lookup order does not guarantee coherency, distributed invalidation, or backend failure handling.
- **"`CompositeCacheManager` will try Redis when Caffeine misses a key."** It searches for a manager by **region name**, not fallback by **key**.
- **"Any cache can use `sync=true` with multiple names."** Spring restricts synchronized `@Cacheable` to a single cache.
- **"All async cases check every name."** Async misses can stop subsequent name lookups early.
- **"An L1 hit is always the freshest data."** Without versioning/invalidation, a stale L1 can mask a fresh L2.
- **"`@CacheEvict` clears everywhere immediately."** Effectiveness and scope depend on backend/manager/node; cross-node invalidation requires dedicated design.
- **"TTL solves every consistency bug."** It only bounds storage duration; acceptable staleness and active mechanisms must still be defined.

## Official References

- Spring Framework — `@Cacheable` and caching annotations: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework 6.2 — Javadoc `Cacheable.cacheNames`, note on async misses: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Framework — Javadoc `CompositeCacheManager`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/cache/support/CompositeCacheManager.html
- Spring Framework — Configuring cache storage/backends: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
- Spring Framework — `Cache` API: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/Cache.html