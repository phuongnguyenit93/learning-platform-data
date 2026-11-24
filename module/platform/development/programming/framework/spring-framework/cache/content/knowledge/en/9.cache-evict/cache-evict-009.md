# Distinguishing active eviction from store-level expiration

## Lesson objectives

After this lesson, you will be able to distinguish **active cache eviction** (application-driven eviction) from **entry expiration** governed by the cache store's policy (provider-driven expiration), know what Spring Cache is responsible for, choose when to use `@CacheEvict`, TTL, or both combined, and practice a Java 17+ example with verifiable results.

This lesson belongs to the **`@CacheEvict`** group: the focus is **who triggers entry removal**, **when the old value stops being used**, and **what happens when source data changes before the TTL expires**. An entry disappears from the reader's perspective in both situations, yet the cause, guarantees, and configuration differ.

## 1. Same cache miss, two different causes

Suppose `getProduct("P1")` reads from a database and caches the result with product name `"Java"`:

```text
Call 1: cache miss → read DB "Java" → store cache[P1] = "Java"
Call 2: cache hit  → return "Java" from cache
DB changes: P1 = "Spring"
```

At the moment the database changes, the cache **does not automatically know** there is a new value. There are two main ways the old entry stops being served:

1. **Active eviction:** application code executes an action like `@CacheEvict(key = "#p0")` after successfully updating the source. The next read sees a miss and loads `"Spring"`.
2. **Expiration:** the cache provider is configured with a TTL, such as `expireAfterWrite(10 minutes)`. Once the entry's lifetime elapses, reads can no longer use `"Java"`; a cache miss can occur and load `"Spring"` even if the application **never called `@CacheEvict`**.

Between the DB change and entry expiration, **TTL alone can still serve stale data**. Conversely, active eviction requires the application to know exactly which data is affected and actually run the invalidation mechanism.

### Concepts not to confuse

- **Active evict/invalidate:** an entry removal command initiated by business logic or an administrative task, via `@CacheEvict` or the appropriate cache API.
- **Expiration:** a lifetime policy enforced by the backend, typically based on elapsed time since **write**, **last access**, or a custom timestamp.
- **Logical expiration:** the entry has expired and is **no longer valid for lookups**, even if the backend has not physically swept it from memory yet.
- **Physical cleanup:** the backend actually frees the slot/memory or deletes the key; this may occur after logical expiration.
- **Capacity-based eviction:** the backend drops entries due to exceeding size/memory limits. This is a different mechanism from TTL, though backend documentation may use the word *eviction* for both.

**Mental model:** readers care whether an entry is still usable; operators must also care who triggers removal, timing, physical cleanup, and source re-access counts.

## 2. Direct comparison

| Criterion | Active eviction with `@CacheEvict` | Store-level expiration |
| --- | --- | --- |
| Who decides? | Application / Spring caching interceptor via annotation or cache API call. | Provider such as Caffeine/Redis via TTL/expiry policy. |
| Trigger condition | An invocation passes through the proxy and satisfies `@CacheEvict` conditions. | Lifetime / backend rules reached the threshold. |
| Time reference | Tied to business events: update, delete, import, data sync... | Time since write/access or an expiry timestamp depending on provider. |
| Scope | One key, or the entire cache via `allEntries=true`. | Usually per entry according to its lifetime. |
| Relation to DB | Can be placed right alongside source updates on the exact key. | Does not inherently know whether the DB changed. |
| Stale data risk | If eviction is missed, wrong key chosen, uncommitted, or proxy bypassed... | Throughout the active TTL window even after the DB changed. |
| When does a miss occur? | After the delete command completes and a subsequent lookup targets that cache/key. | After the backend considers the entry expired; physical cleanup may follow later. |
| Configuration required? | `@EnableCaching`, `CacheManager`, and `@CacheEvict` with exact cache name/key. | A backend supporting expiration and explicit duration configuration. |
| When to use | When you know exactly when data is modified or deleted. | When the source can change outside the app or to cap entry age. |

The two mechanisms **complement each other**: application events shrink the stale-data window; TTL prevents entries from living too long if an event is missed or an external change occurs. Neither mechanism alone guarantees absolute consistency across all transactions and concurrent scenarios.

## 3. What does @CacheEvict actually do?

`@CacheEvict` is an annotation of the **Spring Cache abstraction**; it marks a method as an eviction trigger. It is not an entry lifetime configuration.

Single-key example:

```java
@CacheEvict(cacheNames = "products", key = "#p0")
public void updateProduct(String id, String title) {
    repository.updateTitle(id, title);
}
```

*The snippet above illustrates the annotation; `repository` is a real application dependency.* After the method completes **successfully**, Spring instructs the `products` cache to remove the entry identified by the first argument. The next `@Cacheable(cacheNames = "products", key = "#p0")` read can reload the new value.

Example clearing all entries of a cache:

```java
@CacheEvict(cacheNames = "productSearch", allEntries = true)
public void rebuildSearchIndex() {
    searchIndexer.rebuild();
}
```

`allEntries=true` is meant for situations where a change invalidates **many keys**; Spring skips computing individual keys and ignores `key` during a full-region clear. However, bulk clearing can trigger **concurrent cache misses**, increasing load on the DB or downstream services. Prefer key-targeted eviction when data relationships allow.

### Before or after the method?

Two options to distinguish:

```java
// Default: evict AFTER the method runs successfully.
@CacheEvict(cacheNames = "products", key = "#p0")
public void updateAfterSuccess(String id, String title) {
    repository.updateTitle(id, title);
}
```

```java
// Evict BEFORE the method runs, even if the method later throws an exception.
@CacheEvict(cacheNames = "products", key = "#p0", beforeInvocation = true)
public void evictBeforeWork(String id) {
    performMaintenance(id);
}
```

In the second example, `performMaintenance` is an illustrative business function. `beforeInvocation=true` does not mean the subsequent update will succeed; it only changes **when cache removal happens**. If the work fails, the cache is already cleared and the next read may hit the source. Conversely, with the default `beforeInvocation=false`, a method throwing an exception will not trigger normal eviction.

**Important note on transactions:** "after invocation" **does not automatically mean after database commit**. Interceptor/transaction ordering, rollbacks, and concurrent requests can create a race: evicting the cache before commit while another request reloads old data. Systems requiring strong consistency must design post-commit invalidation or proper transaction coordination and test in real conditions.

### Conditions for the annotation to take effect

- Caching must be enabled, usually with `@EnableCaching`.
- A `CacheManager` and properly named cache must exist.
- The annotated method must be invoked **through the Spring proxy** in default proxy mode; calling `this.updateProduct(...)` internally inside the same bean bypasses caching advice.
- `key` must match the read path's key; `#p0` is the first argument. Same cache name with different key types (`Long 1L` vs. `String "1"`) may fail to match.
- If source changes affect multiple caches or multiple entries, invalidate the full affected scope; one `@CacheEvict` does not automatically know about other copies/aliases.

## 4. Provider-driven expiration: Spring Cache does not create TTLs on its own

Spring Framework provides `Cache`, `CacheManager`, and annotations to coordinate storing, looking up, updating, and deleting entries. **Time-based expiration policies belong to the cache provider** or its configuration layer. Adding `@Cacheable`/`@CacheEvict` does not set a TTL automatically.

Some common examples:

| Backend | Time policy | What to understand |
| --- | --- | --- |
| `ConcurrentMapCacheManager` | No built-in TTL by default. | Suitable for simple demos/tests; entries stay until evicted or the cache is discarded. |
| Caffeine local cache | `expireAfterWrite`, `expireAfterAccess`, configurable custom expiry. | Expired entries are not returned for lookups; physical cleanup may run during cache activity/maintenance. |
| Redis | Key TTL/expiration is governed by Redis and cache configuration. | Whether `GET` extends TTL depends on usage/configuration; do not assume "reading resets TTL". |
| Other cache systems | Depends on provider API and configuration. | Do not assume all backends share the same units, semantics, stats, or cleanup schedules. |

Two common Caffeine policies:

- **`expireAfterWrite(10 minutes)`:** an entry expires after the given duration since it was created or last replaced; normal lookup hits **do not refresh** this timestamp.
- **`expireAfterAccess(10 minutes)`:** an entry expires after the given duration without qualifying access; reads/writes can extend its lifetime. Useful for "drop if no longer used" data.

Some systems also support per-entry TTL or refresh. Distinguish **refresh (reloading a fresh value)** from **expire (no longer returning the old value)** and **manual evict (issuing a delete command)**. `@CacheEvict` does not mean "set TTL to 0 across the application"; it sends a deletion request for the exact cache entry/region.

### Expiration does not mean memory cleanup at that exact millisecond

With Caffeine, an expired entry **should not be returned to lookups**, yet physical reclamation may run during reads/writes or maintenance; there is no guarantee every key disappears from memory at the exact instant TTL ends. Caffeine can be configured with a scheduler for prompt cleanup, though scheduling remains best-effort.

Similarly, in Redis you must distinguish the lookup behavior of an expired key from the background strategy that physically reclaims keys from memory. Do not build correctness on the assumption that "at the exact TTL moment an event handler has definitely fired". The critical verification is **whether a lookup after TTL has elapsed still returns the old entry**.

## 5. Runnable example: @CacheEvict and TTL produce two distinct cache misses

This Spring Boot + Java 17+ example uses Caffeine as an in-memory cache. We use a **simulated clock** (`ManualTicker`) to advance the time seen by Caffeine, separating eviction from expiration **without `Thread.sleep()`** and independent of machine speed.

Prerequisites: create a Spring Boot Gradle project with the appropriate plugins and Java 17+; include these two dependencies in `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'com.github.ben-manes.caffeine:caffeine'
}
```

Place the following classes in the same package `example.eviction`. Run `main` using Gradle `bootRun`.

**File `src/main/java/example/eviction/ManualTicker.java`:**

```java
package example.eviction;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Component;
import com.github.benmanes.caffeine.cache.Ticker;

@Component
public class ManualTicker implements Ticker {
    private final AtomicLong nanoseconds = new AtomicLong();

    @Override
    public long read() {
        return nanoseconds.get();
    }

    public void advance(Duration duration) {
        if (duration.isNegative()) {
            throw new IllegalArgumentException("duration must be non-negative");
        }
        nanoseconds.addAndGet(duration.toNanos());
    }
}
```

In production, Caffeine uses the system monotonic clock; the custom ticker here is solely to make the demo output deterministic.

**File `src/main/java/example/eviction/CacheConfiguration.java`:**

```java
package example.eviction;

import java.time.Duration;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import com.github.benmanes.caffeine.cache.Caffeine;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfiguration {

    @Bean
    CacheManager cacheManager(ManualTicker ticker) {
        CaffeineCacheManager manager = new CaffeineCacheManager("products");
        manager.setCaffeine(Caffeine.newBuilder()
                .expireAfterWrite(Duration.ofSeconds(10))
                .ticker(ticker));
        return manager;
    }
}
```

`@EnableCaching` enables interception; `CaffeineCacheManager` provides the backend; `expireAfterWrite` sets a lifetime of **10 ticker seconds** for entries in `products`. There is no TTL configuration on `@Cacheable`/`@CacheEvict`.

**File `src/main/java/example/eviction/ProductService.java`:**

```java
package example.eviction;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductService {
    private final Map<String, String> database =
            new ConcurrentHashMap<>(Map.of("P1", "Original"));
    private final AtomicInteger reads = new AtomicInteger();

    @Cacheable(cacheNames = "products", key = "#p0")
    public String find(String id) {
        System.out.println("DB_READ #" + reads.incrementAndGet());
        return database.get(id);
    }

    // For demo only: modifies source yet INTENTIONALLY skips invalidation,
    // so stale data can be observed during the TTL window.
    public void changeSourceWithoutEvict(String id, String name) {
        database.put(id, name);
    }

    // After the method succeeds, Spring removes entry products[id].
    @CacheEvict(cacheNames = "products", key = "#p0")
    public void changeAndEvict(String id, String name) {
        database.put(id, name);
    }
}
```

Here `database` is simply a `ConcurrentHashMap` simulating the data source; in a real application, it would be a repository. The two source-modifying methods intentionally differ to illustrate behavior **with and without invalidation**.

**File `src/main/java/example/eviction/EvictionVsTtlApplication.java`:**

```java
package example.eviction;

import java.time.Duration;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class EvictionVsTtlApplication {

    public static void main(String[] args) {
        SpringApplication.run(EvictionVsTtlApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(ProductService service, ManualTicker ticker) {
        return args -> {
            System.out.println("first = " + service.find("P1"));
            System.out.println("hit = " + service.find("P1"));

            service.changeSourceWithoutEvict("P1", "Changed");
            System.out.println("still cached = " + service.find("P1"));

            service.changeAndEvict("P1", "Updated");
            System.out.println("after evict = " + service.find("P1"));

            ticker.advance(Duration.ofSeconds(10));
            System.out.println("after expiry = " + service.find("P1"));
        };
    }
}
```

Run in the project directory:

```bash
./gradlew bootRun
# Windows PowerShell: .\gradlew.bat bootRun
```

**Demo `System.out` lines** in exact order; omit logs generated by Spring Boot/Gradle:

```text
DB_READ #1
first = Original
hit = Original
still cached = Original
DB_READ #2
after evict = Updated
DB_READ #3
after expiry = Updated
```

Analysis:

1. The first `find("P1")` **misses**, reads `Original` from the source, and creates `products["P1"]`. The clock is currently 0.
2. The second `find("P1")` **hits**; no `DB_READ` is printed.
3. `changeSourceWithoutEvict` updates the source to `Changed` while the entry stays `Original`, so the next read **still hits the stale data**. TTL has not expired and the app did not evict.
4. `changeAndEvict` updates the source to `Updated`; since the method completes successfully, `@CacheEvict` immediately removes the entry for key `P1`. The next `find` **misses**, prints `DB_READ #2`, retrieves `Updated`, and caches it again.
5. `ticker.advance(10 seconds)` pushes the `Updated` entry past `expireAfterWrite(10 seconds)` without calling `@CacheEvict`.
6. The subsequent `find` **misses due to expiration**, prints `DB_READ #3`, and reads `Updated`. The value happens to be the same because the source did not change, yet **the source read count increasing** proves the mechanism discarded the expired entry.

The `DB_READ` lines are what prove the cache path; looking at identical return values alone **is not enough** to tell a hit from a miss. The mock clock serves testing so no real-time wait is needed; looking up after the TTL mark has passed is the moment to check logical expiration effectiveness.

**Testing note:** the demo must invoke `ProductService` from the `CommandLineRunner` bean to pass through the proxy; calling `this.find(...)` directly inside `ProductService` bypasses the proxy under default settings. These files are complete Spring Boot code inside a built project, not a single standalone Java file compiled with `javac` without dependencies.

## 6. Choosing a strategy by consistency requirements

### Case A: data modification events are well known

For example, updating a product name through the same application:

```text
request update(P1, "Spring")
   → update database successfully
   → evict products[P1]
   → next read misses and reloads from source
```

`@CacheEvict` fits well because business logic knows **the affected key** and does not need to wait for TTL. However, you must ensure every update/delete/import path handles invalidation, including batch jobs and other systems modifying the source.

### Case B: data can also change externally

For example, another application updates exchange rates while your service only has read paths. There is no update event in the current service to invoke `@CacheEvict`. TTL lets you specify **the maximum age of each entry before it becomes a miss**, though it does not guarantee returning fresh data immediately after every source change.

If you need to shrink the stale window, use shared invalidation events/messages or check data versions; TTL acts as a safety fallback. Do not blindly replace `@CacheEvict` with an ultra-short TTL, as that increases source traffic.

### Case C: multiple instances or shared caches

- With **local Caffeine**, each JVM typically maintains its own cache. Evicting on instance A **does not automatically delete** entries on instance B. If data changes from A, B can keep returning stale values until its own TTL/eviction takes effect.
- With **Redis shared cache**, instances can access shared keys together. Evicting on a shared cache can be observed by other instances on subsequent reads, depending on architecture and whether an extra local cache layer exists.
- With **multi-layer caches** (local + distributed), plan invalidation for each layer to avoid clearing only Redis while local caches keep stale values.

### Case D: data requiring very high accuracy

If staleness cannot be tolerated even briefly (such as permission state or certain financial decisions), evaluate whether to cache that result at all or use synchronous mechanisms, version checking, and transactions/locks as required. Neither `@CacheEvict` nor TTL **is** an absolute linearizability guarantee that every concurrent request after an update reads the exact new version.

## 7. When to use @CacheEvict, TTL, or both?

| Requirement | Approach |
| --- | --- |
| Frequent repeated reads, data rarely changes | Cache with a suitable TTL, optionally evicting on updates. |
| Clear update/delete APIs, results must update promptly | Evict by key after source changes; optionally keep TTL as a safety net. |
| Data updated outside the application without notifications | TTL or an active sync/event mechanism. |
| Catalog modified in bulk, impossible to determine all affected keys | Consider `allEntries=true` after success; assess cache stampede risk. |
| Multiple replicas using local caches | Cross-replica invalidation or a TTL short enough for the staleness SLA. |
| Stale data acceptable for at most a few minutes | TTL can help bound entry age; check provider semantics and reload windows. |
| Stale data unacceptable | Design appropriate source-read/sync paths or do not cache; do not rely solely on TTL. |

One way to formulate a policy is writing down three answers first:

1. **Which data store is the source of truth?** The cache only holds copies.
2. **Which events make an entry invalid?** List update/delete/transaction/batch/external events, and identify cache names/keys to evict.
3. **How long is stale data tolerable when an event is missed?** This drives TTL/expiry design and monitoring.

## 8. Error, performance, and operational notes

**Eviction skipped:** the annotation does not trigger if called within the same bean via `this`, on an object created with `new`, when `@EnableCaching` is missing, or with the wrong cache manager. Verify via hit/miss stats and inspecting entries by key on the backend.

**Evicting the wrong key:** reading with `@Cacheable(key="#p0")` yet evicting with another field or type. Ensure the same key schema and cache name across read/write/delete paths.

**Overly broad clearing:** `allEntries=true` is easy to use, yet causes many keys to miss together, potentially creating load spikes. For hot data, consider prewarming, refresh, or load coordination after invalidation.

**TTL too short:** avoids staleness yet reduces hit rates; concurrent requests after expiry can cause stampedes. `@Cacheable(sync=true)` can help synchronize computation for the same key if the provider supports it, though it is not a distributed lock across multiple instances by default.

**TTL too long:** keeps hits high yet increases stale data risk and memory usage; combine with event invalidation, size limits, or appropriate refresh.

**Errors during updates:** with default post-invocation eviction, a method throwing an exception does not evict. If the source was already modified before throwing, the cache may stay stale. Proper transaction contracts and error handling are required.

**Transaction races:** evicting after the method yet before commit can cause another request to load uncommitted/old values. For critical workflows, solutions may include post-commit invalidation, versioning, and re-verification; test concurrently.

**User/tenant context:** even when evicted or expired on time, a cache key missing tenant, locale, permissions, or result-affecting inputs can still serve wrong data. Cache lifecycle never fixes a flawed key design.

**System observability:** monitor hits/misses, cache size, source read counts, load failure rates, latency, entry age, and backend-supported eviction/expiration metrics. Avoid jumping to conclusions from a single metric; for instance, a high hit rate can coincide with stale data or wrong keys.

## 9. Exercises and self-assessment checks

On the demo in section 5, perform each step in order:

1. Change TTL from 10 seconds to 30 seconds and advance the ticker by 10 seconds: the final call must **hit**, without incrementing `DB_READ`. Then advance by 20 more seconds: the new read misses due to expiration.
2. Remove `@CacheEvict` from `changeAndEvict` and re-run: after updating to `Updated`, before expiry, the cache can still return `Original`. This proves a database update does not invalidate automatically.
3. Try `expireAfterAccess` instead of `expireAfterWrite`; advance the ticker a few seconds between reads to observe how accesses can extend the entry's lifetime window.
4. Intentionally use `key="#p1"` on the update method (whose argument is the new name) while reads use `#p0` (ID). Look for signs the old entry was not removed; then fix it. Do this only in a test environment.
5. Try `beforeInvocation=true` and make the update method throw an exception: verify eviction occurred before the error, compared to default post-success-only eviction.
6. Add product `P2` and try evicting only `P1`, confirming entry `P2` still hits; then try `allEntries=true` on a suitable method and confirm both keys miss.
7. For an application using Caffeine across multiple replicas, simulate two separate cache contexts/instances and observe that local eviction does not clear the other instance's cache.

Review questions:

- **If the DB changes without `@CacheEvict`, are results immediately fresh?** No; the entry can remain valid under its current TTL.
- **If TTL has elapsed yet the backend has not physically cleaned up, can GET fetch the expired entry?** With expiration-compliant backends like Caffeine, lookups do not return expired entries; physical cleanup may lag.
- **Does `@CacheEvict` run before or after the method by default?** After the method completes successfully; `beforeInvocation=true` shifts it to before.
- **Does `@CacheEvict` set a TTL on the cache automatically?** No, TTL is the provider configuration's responsibility.
- **Does evicting an entry automatically update the DB?** No; it only removes the cache copy, and source update logic must execute separately.
- **If the exact key is evicted properly, is TTL still needed?** Depends on requirements; TTL is useful when entries can go stale due to external source changes or a missed invalidation event.

## Further reading

- Spring Framework — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Boot — Caching: https://docs.spring.io/spring-boot/reference/io/caching.html
- Caffeine — Eviction/Expiration: https://github.com/ben-manes/caffeine/wiki/Eviction
- Caffeine — Cleanup: https://github.com/ben-manes/caffeine/wiki/Cleanup
