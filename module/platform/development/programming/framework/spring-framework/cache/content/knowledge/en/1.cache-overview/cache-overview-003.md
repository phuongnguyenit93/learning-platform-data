# Cache Hit, Cache Miss, and Stale Data in Spring Framework

## 1. Three Concepts to Distinguish

A cache temporarily stores results as **key → value** pairs to avoid repeating expensive operations such as reading a database or calling an API. In Spring Framework, `@Cacheable` expresses the lookup and storage policy; data storage, expiration, and cache distribution depend on the `CacheManager` and configured cache provider.

| Phenomenon | What Happens on a Read? | Typical Impact |
| --- | --- | --- |
| **Cache hit** | The key already has a valid value per cache policy; returns the value from cache, typically without executing the `@Cacheable` method body. | Fast response, low load on the data source. |
| **Cache miss** | No usable value exists for the key—for example, not yet stored, recently evicted, or expired. Spring invokes the method to fetch data; the result may be cached per configuration. | Incurs origin data-source read cost, usually slower than a hit. |
| **Stale data** | The cache returns a version that no longer matches the latest data at the source. | Reads can be very fast but **wrong in freshness**. |

**Hit/miss describes the cache lookup result; stale describes the freshness of the content.** A cache hit can completely return stale data. A cache miss is not automatically an error, nor does it guarantee the source data is strictly up to date (the source might be reading a lagging replica).

When a call goes through the Spring cache interceptor, the typical `@Cacheable` flow is:

1. Determine the cache name and key from the method parameters.
2. Check whether the cache holds a value for that key.
3. **Hit:** return the stored result without running the method body.
4. **Miss:** execute the body, obtain the result, and consider storing it in the cache according to `condition`, `unless`, `null` caching support, and provider rules.
5. Subsequent calls for the same key can become hits until the entry is evicted, expires, or the cache is replaced.

This flow is the general model, not a guarantee of a single load under all concurrent scenarios: multiple requests arriving at the same instant on a miss can all execute the method if the provider/policy does not coalesce loads.

## 2. How Does Data Become Stale?

Suppose product `p1` in the database initially holds `"Version A"`, and the cache uses key `p1`:

| Time | Action | Cache | Data Source | Read Result |
| --- | --- | --- | --- | --- |
| T0 | First read call for `p1` | Key absent → **miss**, load `"Version A"` | `"Version A"` | `"Version A"` |
| T1 | Second read call for `p1` | Key present → **hit** | `"Version A"` | `"Version A"` |
| T2 | Another write path modifies source | Cache **still holds** `"Version A"` | **`"Version B"`** | Not read yet |
| T3 | Third read call for `p1` | **Hit**, but returns old version | `"Version B"` | **`"Version A"` (stale)** |
| T4 | Write data and evict same cache key | Key `p1` evicted | `"Version C"` | Not read yet |
| T5 | Next read of `p1` | **Miss**, loads new version | `"Version C"` | `"Version C"` |
| T6 | Read `p1` one more time | **Hit** | `"Version C"` | `"Version C"` |

At T3, the cache is still functioning correctly as a lookup store, but the source update process **did not synchronize** the cached version. This is a data consistency bug, not a cache miss.

Staleness can originate from direct database updates, background jobs, another service, another application instance with only a local cache, or an unexpired TTL policy. TTL bounds how long a value is retained per provider rules; TTL by itself **does not** mean data is updated immediately when the source changes.

## 3. Java 17+ Example with Spring Boot and Spring Cache

Create a Spring Boot 3.x application with the `org.springframework.boot:spring-boot-starter-cache` dependency, using Java 17 or later. Below is the complete code for a single file `src/main/java/com/example/cachedemo/CacheDemoApplication.java`. The project needs the standard Spring Boot plugin and Gradle setup like any regular Spring Boot application.

~~~java
package com.example.cachedemo;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.stereotype.Repository;
import org.springframework.stereotype.Service;

@SpringBootApplication
@EnableCaching
public class CacheDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CacheDemoApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products");
    }

    @Bean
    CommandLineRunner demo(ProductService service, ProductStore store) {
        return args -> {
            System.out.println("1: " + service.getName("p1"));
            System.out.println("2: " + service.getName("p1"));

            // Simulate another system writing to the source without evicting the cache.
            store.save("p1", "Version B");
            System.out.println("3: " + service.getName("p1"));

            // Write path with managed invalidation.
            service.updateName("p1", "Version C");
            System.out.println("4: " + service.getName("p1"));
            System.out.println("5: " + service.getName("p1"));
        };
    }
}

@Repository
class ProductStore {
    private final ConcurrentMap<String, String> data =
            new ConcurrentHashMap<>(Map.of("p1", "Version A"));

    String findName(String id) {
        System.out.println("LOAD " + id);
        return data.get(id);
    }

    void save(String id, String name) {
        data.put(id, name);
    }
}

@Service
class ProductService {
    private final ProductStore store;

    ProductService(ProductStore store) {
        this.store = store;
    }

    @Cacheable(cacheNames = "products", key = "#p0")
    public String getName(String id) {
        return store.findName(id);
    }

    @CacheEvict(cacheNames = "products", key = "#p0")
    public void updateName(String id, String name) {
        store.save(id, name);
    }
}
~~~

If using Gradle Groovy in an already-configured Boot project, include the dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
~~~

Run the application with `./gradlew bootRun` (Windows: `gradlew.bat bootRun`). Excluding Spring Boot startup logs, **the lines explicitly printed by the demo** in exact order are:

~~~text
LOAD p1
1: Version A
2: Version A
3: Version A
LOAD p1
4: Version C
5: Version C
~~~

Walkthrough:

- Call **1**: `products[p1]` is absent → miss → `ProductStore.findName` runs and prints `LOAD p1`; Spring caches `"Version A"`.
- Call **2**: hit → retrieves `"Version A"` directly; no additional `LOAD` line.
- Call **3**: `store.save` updated the source to `"Version B"`, but the cache did not change → hit returns `"Version A"` (**stale**).
- `service.updateName` updates to `"Version C"` and `@CacheEvict` removes `products[p1]` after the method completes successfully under the default mode.
- Call **4**: miss after eviction → loads `"Version C"`. Call **5**: hit returning `"Version C"`.

Note: `#p0` refers to the first parameter, so the example does not depend on the compiler retaining parameter name `id`. `ConcurrentMapCacheManager` is purely a per-process in-memory cache, **has no automatic TTL**, and does not share contents across instances; the example uses it deliberately to clearly demonstrate hits, misses, and staleness. In real applications, choose Caffeine, Redis, or a compatible provider depending on requirements.

## 4. How to Prevent or Limit Stale Data?

No single cache policy fits every kind of data. Choose based on required freshness, system load, source cost, and the likelihood of multiple writers.

| Approach | Mechanism | Things to Keep in Mind |
| --- | --- | --- |
| **Evict on write** | After a successful change, delete affected keys via `@CacheEvict(cacheNames = "products", key = "#p0")`; the next read will miss and reload. | Must cover **every** significant write path, including external jobs and services. |
| **Update cache on write** | `@CachePut` always executes the method and puts the **return value** into the cache under the key. | Ensure the return value is exact; avoid divergence between source and cache updates. |
| **TTL / expiration** | The provider automatically treats entries as expired after a duration; subsequent reads reload. | Tune TTL to freshness requirements; too short increases misses, too long widens staleness. Spring Cache abstraction does not set a universal TTL across providers. |
| **Invalidation events** | When data changes, publish notifications so instances evict or update related keys. | Account for delay, lost events, race conditions, and recovery mechanisms. |
| **Shared / coordinated cache** | Instances share a cache backend or synchronize invalidation. | Reduces cross-instance drift, but still requires rules when source data changes. |
| **Do not cache data needing strict freshness** | Read directly from a suitably consistent source, or design a version-check protocol before returning results. | Accepts extra latency/cost in exchange for correctness. |

When a single record is updated, prefer specific keys: evict `products[p1]` rather than clearing every entry when data relationships allow. `@CacheEvict(allEntries = true)` makes sense only when a change truly invalidates the entire cache; broad eviction triggers a burst of misses.

If database updates run inside a transaction, analyze **commit timing and invalidation timing**. An eviction running before transaction commit can cause another request to reload the old data. For strict consistency needs, implement post-commit eviction or explicit transaction/cache coordination; do not infer that any combination of `@Transactional` and `@CacheEvict` is always safe.

## 5. Reading Metrics and Signals Correctly

To verify caching, observe at least **hits, misses, source loads, latency, and data freshness**. When a provider exposes counters, hit ratio is typically calculated as:

`hit ratio = hits / (hits + misses)` (only when the denominator is greater than 0).

For example, 80 hits and 20 misses yield an 80% hit rate, yet **say nothing about whether those 80 hits are stale**. A high hit rate only proves many reads were served from the cache. Pair it with business metrics such as entry age, version, source update timestamps, eviction frequency, and sync errors. Do not assume every provider automatically emits hit/miss metrics to Spring; observability depends on cache and metrics configuration.

Some signs during testing:

- The data-loading method logs only on the first call, not on subsequent calls → matches the miss-then-hit pattern.
- After modifying the source, the next read still returns the old value → staleness or unsynchronized read source.
- After eviction, the first call reloads and the next does not → matches the miss-then-hit pattern.
- Every call loads from the source → keys may differ, caching is not enabled, calls bypass the proxy, entries are evicted/expired, or results are not being stored.

## 6. Common Misconceptions in Spring Cache

1. **"A cache hit is always the latest data."** False: a hit only means the cache holds a value for the key; it does not prove synchronization with the source.
2. **"Updating the database automatically notifies `@Cacheable`."** False: Spring does not monitor arbitrary source changes. You need invalidation, cache updates, or a separate coordination mechanism.
3. **"A cache miss always creates a cache entry."** Not necessarily: method exceptions, `condition`/`unless`, `null` handling, or provider policies can prevent caching.
4. **"Calling `this.getName(...)` within the same bean still gets `@Cacheable`."** With standard Spring proxy mode, self-invocation bypasses the proxy so the interceptor does not run.
5. **"A missing key runs the backend only once under concurrent requests."** There is no universal guarantee. `@Cacheable(sync = true)` can coalesce concurrent loads for the same key when the provider supports that contract, but you must verify provider behavior, error handling, and real conditions.
6. **"Local caches across instances always stay identical."** False: `ConcurrentMapCacheManager` or local Caffeine in each process maintains separate state; evicting on one instance does not evict on others.
7. **"TTL alone eliminates stale data."** TTL typically only bounds how long old copies are kept per configuration; it does not eliminate the stale window before expiration.

## 7. Self-Check

Consider key `user:42`. After the first read, the cache holds version `V1`. A background job updates the source to `V2` without evicting the cache.

- Is the next read through the cache a **hit or a miss**? → **Hit** if the entry has not expired or been evicted.
- What value can it return? → **V1**, meaning **stale** data despite a successful hit.
- What if `user:42` is evicted and then read again? → **Miss**, loads from the source and may store **V2** (assuming the source already reflects V2 and policy permits caching).
- What if you simply lower the TTL to 5 seconds? → Reduces the stale window but increases misses/source loads; does not guarantee updates appear immediately when written.

**Key takeaway:** Cache optimization is meaningful only when data freshness still satisfies business requirements. When designing a write path, explicitly define the affected cache keys, who can modify source data, when invalidation runs, and how to prove read results are not excessively stale.