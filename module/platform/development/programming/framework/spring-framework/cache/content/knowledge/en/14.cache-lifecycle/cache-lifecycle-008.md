# Expiration Is Different from Data Refresh

In **Spring Framework Cache**, “the entry has expired” and “the entry has been refreshed” are **two distinct states/actions**. A cached result with a 5-minute **TTL** does not mean Spring queries the database every five minutes. TTL primarily defines **until when a cached copy remains valid to read**; **refresh** requires fetching fresh data from the source and writing a new value. The two can happen independently, together, or be driven by different components of the system.

For example: the price of product **P01** is cached at 10:00 as 100. By 10:03, the source price changes to 120, yet the entry has not reached its TTL so it can still return 100. At 10:05, the entry expires; **the next read** triggers a cache miss and executes the method to load 120. Conversely, if **refreshed at 10:04**, the cache can be replaced with 120 before the original TTL expires, and the post-update cache timestamp may also be reset.

Lesson goals: properly understand **expiration**, **eviction**, and **refresh**; distinguish **expireAfterWrite**, **expireAfterAccess**, and **refreshAfterWrite**; use **`@Cacheable` / `@CachePut` / `@CacheEvict`** in their proper roles; and test cache lifecycle with **Java 17 + Spring + Caffeine**.

## 1. Four distinct concepts

| Term | What happens? | Automatically loads fresh data? | What callers typically observe |
| --- | --- | --- | --- |
| **Expiration / TTL** | Entry becomes invalid after exceeding its configured lifetime | **No** | Next read may miss and must reload |
| **Eviction / invalidation** | Entry is removed due to commands, business updates, capacity limits, etc. | **No** | Next read misses |
| **Refresh** | A loader/method reads the source and replaces the cached value | **Yes, performs loading**, triggered by caller/provider/scheduler | New value appears once refresh completes; some models temporarily return stale |
| **Prewarming** | Preloads keys expected to be accessed | **Yes**, per application schedule | Subsequent requests can hit immediately |

**Expiration is a lifetime rule; refresh is an operation that produces a new value.** An entry can be refreshed many times without ever expiring. An entry can also expire and remain physically present until the provider cleans it up, while lookups must treat it as expired.

Do not confuse “expire” with “evict”: both can cause a cached entry to be skipped on read, yet their **causes** differ. Eviction can also stem from entry count, memory limits, or administrative commands, not solely time.

## 2. What happens when `@Cacheable` is called?

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String id) {
    return repository.load(id);
}
~~~

Typical processing flow:

~~~text
find("P01")
    |
    v
Look up cache "products" by key "P01"
    |
    +---- HIT, valid entry ---> return value, DO NOT run method
    |
    +---- MISS / expired -----> run repository.load("P01")
                                  |
                                  v
                              store new value
                                  |
                                  v
                               return value
~~~

When the cache lacks a value, **`@Cacheable`** handles the miss by running the method. However, the Spring Cache Abstraction **does not impose a default TTL** across all providers. You must configure a specific `CacheManager` and cache store. For instance, **`ConcurrentMapCacheManager`** is simply an in-JVM map cache and offers no automatic TTL; **Caffeine** and **Redis** have their own policies.

Suppose the provider applies a 5-minute TTL: an entry expires at 10:05. If no requests arrive afterward, **Spring does not automatically re-invoke `find`** merely because the clock passed that mark. A fresh copy typically appears when a read causes a miss or an explicit refresh occurs.

## 3. `expireAfterWrite` and `expireAfterAccess` are not the same

### `expireAfterWrite`: age measured from write/update

~~~java
// Caffeine builder configuration in an application with the Caffeine dependency.
Caffeine.newBuilder()
    .maximumSize(10_000)
    .expireAfterWrite(java.time.Duration.ofMinutes(5));
~~~

If a key is created at 10:00, by around 10:05 it is no longer valid. **Cache hit reads during that window do not reset the write age.** If a successful **put/refresh** occurs at 10:04, the new value's write timestamp is updated; the new entry can remain valid until around 10:09.

This policy is useful when bounding a copy's age, yet it **does not guarantee data always matches the source during those five minutes**. Source changes right after 10:00 can still leave the cached value stale.

### `expireAfterAccess`: age measured from last access

~~~java
Caffeine.newBuilder()
    .maximumSize(10_000)
    .expireAfterAccess(java.time.Duration.ofMinutes(5));
~~~

Under this policy, a hot key read continuously can extend its lifetime very far. **Frequent access does not mean data is updated from the DB**; a hot key can remain stale without other invalidation or refresh mechanisms.

**Selection rule:** `expireAfterWrite` focuses on bounding the age of a copy; `expireAfterAccess` generally fits reclaiming **rarely used** data. Neither replaces requirements around freshness, authorization, and transactional consistency.

## 4. Explicit refresh with `@CachePut`

Spring separates reading the cache from explicitly writing to the cache. Example of two methods sharing the same cache name and key:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String id) {
    return repository.load(id);
}

@CachePut(cacheNames = "products", key = "#p0")
public Product refresh(String id) {
    return repository.load(id);
}
~~~

**`@Cacheable`** can return an existing value while skipping the method. **`@CachePut`** executes the method to compute a result, then writes **the returned result** into the cache (subject to `condition`/`unless` if configured). Thus it can refresh a key **before its TTL expires**.

However:

- **`@CachePut` does not schedule itself**. If nobody calls **`refresh`**, no refresh occurs from the annotation alone.
- **The method must genuinely read fresh source data**. `@CachePut` does not automatically know what changed in the DB.
- **Cache name and key must match** the read method. If keys differ, the old entry can still be served.
- **Must be called through the Spring proxy**; calling **`this.refresh(...)`** inside the same bean in normal proxy mode can bypass cache advice.
- If the return value is **`null`**, understand null-storage rules and **`unless = "#result == null"`** on the method, especially when the provider forbids nulls.

With **`@CachePut`**, loading from the source and updating the cache can happen while the TTL is still active. That is the core difference from waiting for **expiration → miss → load**.

## 5. `@CacheEvict`: removing an entry is not refreshing an entry

~~~java
@CacheEvict(cacheNames = "products", key = "#p0")
public void invalidate(String id) {
    // No operation to fetch new data.
}
~~~

**`invalidate("P01")`** removes entry `P01`. Only then may **`find("P01")`** need to reload. Without a subsequent read, nothing guarantees data is preloaded.

By default, **`@CacheEvict`** runs eviction after the method finishes normally; **`beforeInvocation = true`** deletes before the invocation, even if the method later fails. In transactional applications, mind eviction timing relative to **commit**, avoiding another request missing the cache and loading uncommitted DB values.

For instance, when changing a price, you can choose **update DB then evict key** (so the next read gets the new price), or **refresh/put the confirmed post-update value**. Test race and failure behaviors for whichever approach you choose.

## 6. Caffeine `refreshAfterWrite`: “eligible” does not mean “runs on schedule”

Caffeine supports **`refreshAfterWrite`** for caches with a loader, such as **`LoadingCache`** (illustrative snippet; requires an actual backend and Caffeine/`LoadingCache` imports):

~~~java
LoadingCache<String, Product> cache = Caffeine.newBuilder()
    .maximumSize(10_000)
    .refreshAfterWrite(java.time.Duration.ofMinutes(2))
    .expireAfterWrite(java.time.Duration.ofMinutes(15))
    .build(key -> backend.load(key));
~~~

Exact meaning:

1. After **two minutes since write**, an entry becomes **eligible** for refresh.
2. Caffeine typically **triggers a refresh upon the first read to an eligible entry**, rather than running in the background across all keys every two minutes on the dot.
3. Refresh reloads **asynchronously**. While waiting, **the stale value may continue to be returned**, reducing latency spikes; once reload succeeds, the new value replaces it.
4. If refresh fails, Caffeine generally keeps the old value and logs/records the error; monitor errors and decide an acceptable staleness limit.
5. **`expireAfterWrite`** is an independent **hard expiration** policy; an unaccessed entry that became eligible for refresh can still expire.
6. Refresh requires a suitable **`CacheLoader` / `AsyncCacheLoader`**. Configuring **`@Cacheable`** alone does not automatically turn a method into a loader for **`refreshAfterWrite`**.

When using **`CaffeineCacheManager`** in Spring, verify how **`LoadingCache`** is built, which `CacheLoader` is registered, and how the adapter behaves. Do not assume that merely adding **`refreshAfterWrite`** to the builder causes every key to automatically re-run a Spring method on a schedule.

| Caffeine policy | When the threshold passes | Next read | Can it return stale data? |
| --- | --- | --- | --- |
| **`expireAfterWrite(5m)`** | Entry exceeds write age and is treated as invalid | Miss/fresh load | Not under the expiration policy |
| **`expireAfterAccess(5m)`** | Entry expires if unaccessed long enough | Miss if idle-expired | Not under the expiration policy |
| **`refreshAfterWrite(2m)`** | Entry becomes eligible for refresh | Typically triggers async reload | **Yes**, while reload is in flight |

**Refresh does not mean strong consistency.** If business requirements forbid returning stale data even for a few seconds, you need an appropriate synchronization and source-read policy; you cannot adopt stale-while-revalidate while ignoring that requirement.

## 7. Spring + Caffeine + Java 17 demo: verifying with a simulated clock

This complete example uses **Spring Framework 6.1.14**, **Caffeine 3.1.8**, **Java 17**, and Gradle. It includes a simulated **`Source`** with versions v1/v2/v3/v4 and a **`MutableTicker`** to advance the cache clock by minutes without `Thread.sleep`. Spring configures `CaffeineCacheManager` with **`expireAfterWrite(5 minutes)`**.

Goal: test a timeline with **two keys P01 and P02**:

- Minute **0**: read P01, P02; both are cached at v1.
- Source bumps to **v2**, yet unexpired entries still return v1.
- Minute **4**: **`refresh(P01)`** via `@CachePut` writes v2 and resets P01's write age.
- Minute **6**: P01 is only 2 minutes old so it hits v2; P02 is 6 minutes old and past its TTL so it reloads v2.
- Minute **11**: source is at v3; P01 is 7 minutes past its minute-4 refresh so it expires and reloads v3.
- Source bumps to **v4**; **`invalidate(P01)`** deletes the freshly loaded P01 entry, and the next read loads v4.

**`settings.gradle`**

~~~groovy
rootProject.name = 'spring-expiry-refresh-demo'
~~~

**`build.gradle`**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
    implementation 'org.springframework:spring-context-support:6.1.14'
    implementation 'com.github.ben-manes.caffeine:caffeine:3.1.8'
    testImplementation 'org.springframework:spring-test:6.1.14'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.10.2'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.cache.ExpiryRefreshDemo'
}

test {
    useJUnitPlatform()
}
~~~

**`src/main/java/demo/cache/ExpiryRefreshDemo.java`**

~~~java
package demo.cache;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import com.github.benmanes.caffeine.cache.Caffeine;
import com.github.benmanes.caffeine.cache.Ticker;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class ExpiryRefreshDemo {

    public static final class MutableTicker implements Ticker {
        private final AtomicLong nanos = new AtomicLong();

        @Override
        public long read() {
            return nanos.get();
        }

        public void advance(Duration duration) {
            nanos.addAndGet(duration.toNanos());
        }
    }

    public static final class Source {
        private final AtomicInteger version = new AtomicInteger(1);

        public String read(String id) {
            return id + ":v" + version.get();
        }

        public void bump() {
            version.incrementAndGet();
        }
    }

    @Bean
    public MutableTicker ticker() {
        return new MutableTicker();
    }

    @Bean
    public Source source() {
        return new Source();
    }

    @Bean
    public CacheManager cacheManager(MutableTicker ticker) {
        CaffeineCacheManager manager = new CaffeineCacheManager("products");
        manager.setCaffeine(Caffeine.newBuilder()
                .maximumSize(100)
                .expireAfterWrite(Duration.ofMinutes(5))
                .ticker(ticker));
        return manager;
    }

    @Bean
    public ProductService productService(Source source) {
        return new ProductService(source);
    }

    public static class ProductService {
        private final Source source;
        private final AtomicInteger loads = new AtomicInteger();

        public ProductService(Source source) {
            this.source = source;
        }

        @Cacheable(cacheNames = "products", key = "#p0")
        public String find(String id) {
            loads.incrementAndGet();
            return source.read(id);
        }

        @CachePut(cacheNames = "products", key = "#p0")
        public String refresh(String id) {
            loads.incrementAndGet();
            return source.read(id);
        }

        @CacheEvict(cacheNames = "products", key = "#p0")
        public void invalidate(String id) {
        }

        public int loadCount() {
            return loads.get();
        }
    }

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(
                ExpiryRefreshDemo.class)) {
            Source source = ctx.getBean(Source.class);
            MutableTicker clock = ctx.getBean(MutableTicker.class);
            ProductService service = ctx.getBean(ProductService.class);

            System.out.println("t0-P01=" + service.find("P01"));
            System.out.println("t0-P02=" + service.find("P02"));

            source.bump();
            System.out.println("source=" + source.read("P01"));
            System.out.println("beforeExpiry=" + service.find("P01"));

            clock.advance(Duration.ofMinutes(4));
            System.out.println("t4-beforeRefresh=" + service.find("P01"));
            System.out.println("t4-refresh=" + service.refresh("P01"));

            clock.advance(Duration.ofMinutes(2));
            System.out.println("t6-P01=" + service.find("P01"));
            System.out.println("t6-P02=" + service.find("P02"));

            source.bump();
            clock.advance(Duration.ofMinutes(5));
            System.out.println("t11-P01=" + service.find("P01"));

            source.bump();
            service.invalidate("P01");
            System.out.println("afterEvict-P01=" + service.find("P01"));
            System.out.println("loads=" + service.loadCount());
        }
    }
}
~~~

**Directory layout** requires the two Gradle files at the root, the main class at **`src/main/java/demo/cache/ExpiryRefreshDemo.java`**, and the test at **`src/test/java/demo/cache/ExpiryRefreshDemoTest.java`**.

Run using an installed Gradle or the created project's wrapper inside the project directory:

~~~bash
gradle run --quiet
~~~

Expected **`System.out.println`** lines:

~~~text
t0-P01=P01:v1
t0-P02=P02:v1
source=P01:v2
beforeExpiry=P01:v1
t4-beforeRefresh=P01:v1
t4-refresh=P01:v2
t6-P01=P01:v2
t6-P02=P02:v2
t11-P01=P01:v3
afterEvict-P01=P01:v4
loads=6
~~~

The **`find`/`refresh`** method bodies execute 6 times: two initial misses; one P01 refresh; one P02 expiration at minute 6; one P01 expiration at minute 11; and one P01 miss after eviction. All other reads hit and do not increment the counter.

### Runnable JUnit 5 test

**`src/test/java/demo/cache/ExpiryRefreshDemoTest.java`**

~~~java
package demo.cache;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.cache.CacheManager;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(ExpiryRefreshDemo.class)
class ExpiryRefreshDemoTest {

    @Autowired
    ExpiryRefreshDemo.MutableTicker ticker;

    @Autowired
    ExpiryRefreshDemo.Source source;

    @Autowired
    ExpiryRefreshDemo.ProductService service;

    @Autowired
    CacheManager manager;

    @Test
    void distinguishesExpireRefreshAndInvalidate() {
        assertEquals("P01:v1", service.find("P01"));
        assertEquals("P02:v1", service.find("P02"));
        assertEquals(2, service.loadCount());

        source.bump();
        assertEquals("P01:v2", source.read("P01"));
        assertEquals("P01:v1", service.find("P01"));

        ticker.advance(Duration.ofMinutes(4));
        assertEquals("P01:v1", service.find("P01"));
        assertEquals("P01:v2", service.refresh("P01"));
        assertEquals(3, service.loadCount());

        ticker.advance(Duration.ofMinutes(2));
        assertEquals("P01:v2", service.find("P01"));
        assertEquals("P02:v2", service.find("P02"));
        assertEquals(4, service.loadCount());

        source.bump();
        ticker.advance(Duration.ofMinutes(5));
        assertEquals("P01:v3", service.find("P01"));
        assertEquals(5, service.loadCount());

        source.bump();
        // P01 was just loaded at minute 11, so its entry is still present before eviction.
        assertNotNull(manager.getCache("products").get("P01"));
        service.invalidate("P01");
        assertNull(manager.getCache("products").get("P01"));
        assertEquals("P01:v4", service.find("P01"));
        assertEquals(6, service.loadCount());
    }
}
~~~

Run:

~~~bash
gradle test
~~~

**Expectation:** a passing test under the Java/Spring/Caffeine configuration above. No need to sleep five real minutes; **`MutableTicker`** advances the `CaffeineCache` clock and the assertions prove exact expiration/refresh/evict behavior. The Gradle commands are reproduction instructions; they are not guaranteed external stdout beyond the program itself.

**Limitations:** this demo uses **`@CachePut` for explicit refresh** plus **`expireAfterWrite`**. It does *not* use `LoadingCache`'s automatic **`refreshAfterWrite`**; that mechanism has different asynchronous semantics as described in section 6. The example retrieves the Spring bean via `ApplicationContext`, avoiding **`new ProductService(...)`** when testing AOP interceptors.

## 8. Configuration in Spring Boot and Redis

### Spring Boot + Caffeine

With Spring Boot using the cache starter/Caffeine and caching enabled, an illustrative configuration:

~~~properties
spring.cache.type=caffeine
spring.cache.cache-names=products,productList
spring.cache.caffeine.spec=maximumSize=10000,expireAfterWrite=300s
~~~

**`expireAfterWrite=300s`** is expiration approximately five minutes after write; it is not an instruction for Spring to automatically run the data-loading method every five minutes. Note that a Spring Boot app needs **`spring-boot-starter-cache`** and a compatible Caffeine library; in a standalone Spring Framework project, **`spring-context-support`** is needed for `CaffeineCacheManager`.

If you want **`refreshAfterWrite`**, verify how Boot registers a `CacheLoader` and underlying `LoadingCache`. Never simply add `refreshAfterWrite` to the spec and claim every **`@Cacheable`** method will automatically re-run on a schedule.

### Spring Data Redis TTL

Example at the Spring Data Redis configuration layer (not a standalone Java class):

~~~java
RedisCacheConfiguration.defaultCacheConfig()
    .entryTtl(java.time.Duration.ofMinutes(5));
~~~

Once a key reaches its TTL and Redis returns no value, **`@Cacheable`** in the application can run the method to reload on demand. Redis itself does not know which Java method to call to refresh. Verify cache prefixes, serializers, null handling, per-cache TTLs, and multi-instance characteristics; a shared cache does not automatically solve concurrent cache-miss races.

### Simple `ConcurrentMapCache`

When using **`ConcurrentMapCacheManager`**, do not assume an imaginary default TTL: an in-JVM map cache lacks built-in `expireAfterWrite` policies like Caffeine. Entries can remain until replaced/evicted or the application terminates. Choose a provider and configuration aligned with lifecycle requirements.

## 9. Is a scheduler a refresh?

If business logic requires reloading certain hot keys **on a schedule**, there must be logic that genuinely invokes a refresh. Illustrative snippet in an application configured with **`@EnableScheduling`**, calling a Spring service bean with a **`@CachePut`** method:

~~~java
@Component
public class HotProductWarmer {
    private final ProductService productService;

    public HotProductWarmer(ProductService productService) {
        this.productService = productService;
    }

    @Scheduled(fixedDelay = 120000)
    public void refreshP01() {
        productService.refresh("P01");
    }
}
~~~

Import **`@Component`** from `org.springframework.stereotype` and **`@Scheduled`** from `org.springframework.scheduling.annotation`. The code above is meant to be integrated into a full application and **is not part of the runnable project in section 7**. It calls through **another bean** so the Spring cache proxy applies **`@CachePut`**. When deploying multiple replicas, every instance may run the job concurrently; configure a single active scheduler or coordination if you do not want multiplied load.

A scheduler **differs** from expiration/`refreshAfterWrite`: it genuinely maintains an application-defined reload schedule; yet it still must know which keys to load, handle errors, and avoid excessive work. Refreshing every key every few seconds can cost even more than letting the cache miss naturally.

## 10. Races, refresh failures, and freshness guarantees

### 10.1. Refresh in progress while source data changes concurrently

~~~text
t0: Thread A reads v1 to refresh P01 (slow loader).
t1: Thread B updates DB to v2 and evicts P01.
t2: Thread A finishes late, writes stale v1 into cache.
t3: Request C gets a cache hit with v1, even though DB is already v2.
~~~

A short TTL does not solve this race by itself: `v1` can be written **after** eviction. You need an appropriate policy such as versioned keys/values, revision checks, after-commit invalidation, or ordered cache-aside design.

### 10.2. Stampede on expiration

When a hot key reaches its TTL, many requests can miss simultaneously and hit the DB. **`@Cacheable(sync = true)`**, when supported by the provider, can coordinate loaders for the same key; it is not **TTL**, not a refresh, and does not guarantee cluster-wide single-flight. When many keys expire together, consider TTL jitter, proactive refresh, concurrency limits, and bulkheads.

### 10.3. Refresh failures

- **`@CachePut`:** the refresh method must run and produce a result; an exception can prevent the put from completing.
- **Caffeine `LoadingCache` refresh:** async refresh can retain the old value if reloading fails; monitor exceptions and bound stale age.
- **Expiration:** expired keys are generally not served as hits even when the backend is failing, unless the application builds a dedicated stale/fallback mechanism.
- **Redis/distributed caches:** test network errors, serialization failures, and how the app falls back if `CacheManager` becomes unreachable.

A stale-while-revalidate strategy is very helpful for data tolerating brief staleness, yet **must not be applied mechanically** to information requiring strict consistency such as balances or access permissions.

## 11. Selection criteria

| Need | Typically suitable choice | Limitations |
| --- | --- | --- |
| Cache infrequently changing data, tolerate a few minutes of staleness | **`expireAfterWrite`** | Requests after TTL may wait for reload |
| Reclaim rarely read keys | **`expireAfterAccess`** | Hot keys do not automatically sync with source |
| Reduce hot-key tail latency | **`refreshAfterWrite`** + loader | May return stale data during async reload |
| Refresh immediately on source-change events | **`@CachePut`** or event-driven update | Incurs a source load and requires race handling |
| Avoid reading old data after updates | **`@CacheEvict`** and consistency policy | Next request suffers a cache miss |
| Preload keys on a planned cadence | Controlled scheduler/warmup | Loading cost even without traffic |
| Require results always very fresh and accurate | Versioning, post-commit invalidation, or no caching | Higher complexity or latency |
| Multiple replicas with an expensive backend | Combine per-key coordination with TTL/refresh strategy | Must verify cluster-level provider/locking |

Define a **freshness SLA**: maximum tolerable staleness, whether users must see their own updates immediately, whether stale reads are permitted during source outages, and acceptable p95/p99 latency. **Hit ratio alone is insufficient**: a cache with a high hit rate serving overly stale data is still functionally wrong.

## 12. Data lifecycle testing checklist

| Test case | Setup | Passing condition |
| --- | --- | --- |
| Before TTL | Read the same key multiple times | `@Cacheable` method executes only once |
| Source changes within TTL | Bump source version without evict/refresh | Cache still returns stored copy if unexpired |
| TTL expires | Advance clock past `expireAfterWrite` | Next read misses and fetches new version |
| Early refresh | `@CachePut` before TTL | New value written; write age resets per provider |
| Two keys with different schedules | Refresh P01, leave P02 aging | P01 and P02 expire at different times |
| Eviction | Ensure entry exists, then `@CacheEvict` | Entry disappears; next read reloads |
| `refreshAfterWrite` | `LoadingCache` with loader and fake clock | Only eligible entries that are read trigger reload |
| Async refresh | Intentionally slow down reload | Verify old/stale return and new value after completion |
| Loader failure | Source throws exception | Verify stale/error policy, no infinite retry loop |
| Concurrent misses | Burst traffic on one hot key | Backend load stays within acceptable bounds |
| Multiple replicas | Run across clustered/local caches | Consistency boundaries are clearly understood |
| DB commit + cache update | Race scenario | No stale entry resurrected after invalidation |

**Never use `Thread.sleep(300000)`** in unit/integration tests for TTL if the provider supports a fake ticker/clock. With Redis, clocks live server-side so test against an appropriate Redis environment; swapping Java's `Clock` alone does not alter Redis TTLs.

## 13. Common pitfalls and self-check questions

- **Thinking TTL is a refresh schedule:** expiration does not automatically call the repository.
- **Thinking Spring `@Cacheable` has a built-in default TTL:** in reality it depends on the store.
- **Using `expireAfterAccess` to cap absolute age:** hot keys can keep stale data alive indefinitely.
- **Confusing `refreshAfterWrite` with an exact-schedule background job:** Caffeine usually waits for an access to an eligible entry.
- **Configuring `refreshAfterWrite` without a matching loader:** reloads will not happen as expected.
- **Calling `@CacheEvict` and claiming the cache was refreshed:** the entry was only removed.
- **Calling `this.refresh(...)` inside the same bean:** the proxy may fail to intercept it.
- **Refreshing keys without tenant/currency context:** risks populating data for the wrong context.
- **Assuming short TTLs eliminate races:** a late-finishing refresh can still write stale data after an evict.
- **Ignoring source-failure cases:** stale bounds, timeouts, and fallback policies are required.
- **Increasing refresh frequency unboundedly:** can consume more backend resources than cache misses.

Answer for yourself:

1. If an entry expires after 5 minutes and nobody reads it again, does Spring automatically run the source-loading method?
2. Why can `expireAfterAccess` keep a stale hot key alive for a very long time?
3. With `@CachePut`, what must occur before the cache receives the new value?
4. Why does a single `@CacheEvict` not equal a refresh?
5. When `refreshAfterWrite` reaches two minutes, what typically triggers Caffeine to reload?
6. Why can the read that triggers an async refresh still receive the old value?
7. In the demo, why was P01 still valid at minute 6 while P02 had to reload?
8. Why can overlapping invalidation and refresh put stale v1 back into the cache?
9. If fresh reads are always required right after a transaction commits, is TTL enough?

**Conclusion:** **Expiration** defines when a cached copy becomes invalid. **Refresh** means re-reading the source and updating the value. In Spring, annotations describe lookup, put, and evict; the provider governs time policies, while refresh schedules and consistency levels must be designed explicitly. Test timestamps, values, keys, failures, and races rather than conflating the two concepts.

### References

- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Configuring Cache Storage: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
- Spring Framework — `@Cacheable`, `@CachePut`, and `@CacheEvict`: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Boot — Caching and Caffeine configuration: https://docs.spring.io/spring-boot/reference/io/caching.html
- Caffeine — Refresh wiki: https://github.com/ben-manes/caffeine/wiki/Refresh
- Caffeine — Expiration wiki: https://github.com/ben-manes/caffeine/wiki/Expiration
- Spring Data Redis — Redis Cache: https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html
