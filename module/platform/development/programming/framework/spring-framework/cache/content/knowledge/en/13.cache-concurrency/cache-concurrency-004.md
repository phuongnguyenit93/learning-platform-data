# Distinguishing Store Thread Safety from Operation Sequence Atomicity in Spring Cache

## 1. The problem: thread-safe does not mean atomic

When using Spring Cache, learners often encounter two statements that sound alike:

- **Thread-safe cache store:** multiple threads calling `get`, `put`, and `evict` concurrently can be handled by the backend according to each operation's concurrency contract without corrupting internal data structures.
- **Atomic business sequence:** an entire workflow such as `get -> load data -> put`, or `get -> increment value -> put`, must be protected as a single logical unit so other threads cannot interleave and corrupt the outcome.

These two guarantees are **different**. A `ConcurrentHashMap` has thread-safe individual operations, yet:

```java
int old = map.get("n");
map.put("n", old + 1);
```

does not turn the two statements into an atomic increment. Two threads can read the same old number and write the same new number. The store is not corrupted, but a *lost update* occurs.

Similarly in Spring: `ConcurrentMapCacheManager` provides caches backed by concurrent data structures, but does not by default atomically protect the entire path **cache miss -> run @Cacheable method -> cache put**. Two requests with the same key can miss together and both run the expensive load.

**Goals:** distinguish thread safety, per-key atomicity, and cross-resource transactions; recognize three kinds of races (lost update, duplicate load, stale put after evict); and know when to use `compute`, `@Cacheable(sync=true)`, locking, versioning, and transactions.

## 2. Three levels of guarantees

| Level | What is guaranteed | Example | What cannot be inferred |
| --- | --- | --- | --- |
| **Single-operation thread safety** | Multiple threads access a structure without breaking that operation's contract | `ConcurrentHashMap.get/put` | The entire `get+put` sequence is atomic |
| **Single-mapping/key atomicity** | A logical update on one key executes as a unit | `ConcurrentHashMap.compute`, provider with synchronized cache load | Every key or every cache is inside a transaction |
| **End-to-end business consistency** | Database updates, cache, and events stay consistent within SLA | DB transaction + coordinated invalidation | Guarantees merely from the word `Concurrent` or `sync` |

You must state the **scope** explicitly: one operation, one key, one JVM, multiple nodes, one cache, or multiple systems. There is no absolute "atomic" guarantee without specifying which scope of operations is atomic.

### 2.1. Interleaving causing a lost update

Suppose `map["n"] = 0`, and two threads both want to increment by 1:

| Time | Thread A | Thread B | Map |
| --- | --- | --- | --- |
| T0 | — | — | `n=0` |
| T1 | `get("n") → 0` | — | `n=0` |
| T2 | — | `get("n") → 0` | `n=0` |
| T3 | `put("n",1)` | — | `n=1` |
| T4 | — | `put("n",1)` | `n=1` |

Every `ConcurrentHashMap` operation worked properly. The flaw lies in **not protecting the read and write pair as a single sequence**.

For incrementing a single key, Java provides an atomic operation:

```java
map.compute("n", (key, oldValue) -> oldValue + 1);
```

Two `compute` calls on the same key yield 2 when starting from 0. Per the JDK, `ConcurrentHashMap.compute` performs the remapping atomically for the associated mapping. The function should be concise and **must not update the same map** from inside; slow work inside it can block other threads.

### 2.2. A thread-safe store does not synchronize value objects

If a cache stores a mutable `ArrayList`, multiple threads retrieving the same instance and adding/removing elements still need synchronization around mutating the List. A thread-safe backend does not automatically make mutable values thread-safe. Prefer immutable values or defensive copies where appropriate.

## 3. In Spring Cache: two requests cache-missing together

Illustrative snippet in a Spring service:

```java
@Cacheable(cacheNames = "books")
public Book findById(String id) {
    return repository.findById(id);
}
```

This is an **illustrative code snippet** requiring actual `Book` and `repository` types. When key `"B1"` is not yet cached, two requests can interleave:

```text
Thread A                   Cache                    Thread B
  |                         |                          |
  |--- get("B1") --------->|                          |
  |<-- miss ---------------|                          |
  |                         |<------- get("B1") -------|
  |                         |-------- miss ----------->|
  |--- query DB             |             query DB ----|
  |--- put("B1",v1) ------->|                          |
  |                         |<------- put("B1",v2) -----|
```

The diagram depicts **one possible interleaving**: each thread reads a miss before the other puts. The cache is not corrupted, but *duplicate computation* occurs, DB cost increases, and the final cached value can depend on put ordering.

If the origin value changes between the two reads, differing `v1` and `v2` values can cause a **stale write**. Thread-safety guarantees of `get` and `put` do not imply the intermediate steps are atomic.

### 3.1. The @Cacheable(sync=true) feature

```java
@Cacheable(cacheNames = "books", sync = true)
public Book findById(String id) {
    return repository.findById(id);
}
```

In Spring Cache, `sync=true` asks a supporting provider to **synchronize loading an entry for the same key on concurrent misses**. On supporting implementations, one thread computes the data; the other threads wait and receive the same cached result. Spring provides the `Cache.get(key, Callable)` API for this loading pattern.

However, this is a **provider-dependent hint/capability**, not a distributed transaction:

- Does not prevent all concurrent updates or evictions of the key.
- Does not automatically synchronize different keys or two distinct caches.
- Does not synchronize the database and the cache.
- Do not infer cross-JVM single-flight just because one JVM with `ConcurrentMapCacheManager` works.
- If the provider does not support locking as expected, verify in practice or use another mechanism.

Spring `@Cacheable(sync=true)` also has constraints: **no `unless` support**, **only one cache specified**, and **no combining other cache operations on the same method**. Do not write `@Cacheable(sync=true, unless="...")` expecting Spring to handle it automatically.

## 4. Complete Java 17+ example: three reproducible races

The example uses JDK 17+ and `spring-boot-starter-cache` to demonstrate:

1. Two threads performing `ConcurrentHashMap.get+put`: one increment is lost; switching to `compute` fixes it.
2. Two `@Cacheable` calls on the same key: by default the body runs twice when forced to miss together; with `sync=true` and `ConcurrentMapCacheManager`, it runs once.
3. A loader reads an old version, another thread updates and evicts, and then the old loader puts **after eviction**: the cache holds the stale value.

To keep results independent of timing luck, the program uses `CountDownLatch` to bring threads to the exact observation points. It is a **single-JVM** exercise and does not fully simulate a distributed backend.

### 4.1. Creating the Gradle project

Structure:

```text
cache-concurrency/
  settings.gradle
  build.gradle
  src/main/java/demo/cache/ConcurrencyDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'cache-concurrency'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}

application {
    mainClass = 'demo.cache.ConcurrencyDemo'
}
```

### 4.2. Complete Java file

`src/main/java/demo/cache/ConcurrencyDemo.java`:

```java
package demo.cache;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class ConcurrencyDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class CacheConfig {
        @Bean
        CacheManager cacheManager() {
            return new ConcurrentMapCacheManager(
                    "ordinary", "singleFlight", "direct");
        }

        @Bean
        CachedService cachedService() {
            return new CachedService();
        }
    }

    public static class CachedService {
        private final AtomicInteger ordinaryLoads = new AtomicInteger();
        private final AtomicInteger syncedLoads = new AtomicInteger();
        private final CountDownLatch bothInside = new CountDownLatch(2);

        @Cacheable(cacheNames = "ordinary")
        public String ordinary(String key) {
            int n = ordinaryLoads.incrementAndGet();
            bothInside.countDown();
            await(bothInside, "both ordinary calls entered");
            return "ordinary-" + n;
        }

        @Cacheable(cacheNames = "singleFlight", sync = true)
        public String singleFlight(String key) {
            return "sync-" + syncedLoads.incrementAndGet();
        }

        public int ordinaryCount() {
            return ordinaryLoads.get();
        }

        public int syncCount() {
            return syncedLoads.get();
        }
    }

    private static void await(CountDownLatch latch, String step) {
        try {
            if (!latch.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("timeout: " + step);
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("interrupted: " + step, e);
        }
    }

    private static List<String> inParallel(Callable<String> action)
            throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);
        try {
            Future<String> a = pool.submit(() -> {
                await(start, "start");
                return action.call();
            });
            Future<String> b = pool.submit(() -> {
                await(start, "start");
                return action.call();
            });
            start.countDown();

            List<String> values = new ArrayList<>();
            values.add(a.get(10, TimeUnit.SECONDS));
            values.add(b.get(10, TimeUnit.SECONDS));
            Collections.sort(values);
            return values;
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }

    private static void lostUpdate() throws Exception {
        ConcurrentHashMap<String, Integer> map = new ConcurrentHashMap<>();
        map.put("counter", 0);
        CountDownLatch bothRead = new CountDownLatch(2);

        inParallel(() -> {
            int previous = map.get("counter");
            bothRead.countDown();
            await(bothRead, "both threads read zero");
            map.put("counter", previous + 1);
            return "done";
        });
        System.out.println("getThenPut=" + map.get("counter"));

        map.put("counter", 0);
        inParallel(() -> {
            map.compute("counter", (k, previous) -> previous + 1);
            return "done";
        });
        System.out.println("atomicCompute=" + map.get("counter"));
    }

    private static void latePut(Cache cache) throws Exception {
        cache.clear();
        AtomicInteger source = new AtomicInteger(1);
        CountDownLatch tookSnapshot = new CountDownLatch(1);
        CountDownLatch allowPut = new CountDownLatch(1);
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Future<?> oldLoader = pool.submit(() -> {
                if (cache.get("item") == null) {
                    int snapshot = source.get();
                    tookSnapshot.countDown();
                    await(allowPut, "release old loader");
                    cache.put("item", snapshot);
                }
            });

            await(tookSnapshot, "snapshot ready");
            source.set(2);
            cache.evict("item");
            allowPut.countDown();
            oldLoader.get(10, TimeUnit.SECONDS);

            System.out.println("sourceVersion=" + source.get());
            System.out.println("cacheVersion="
                    + cache.get("item", Integer.class));
        } finally {
            allowPut.countDown();
            pool.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        lostUpdate();

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(CacheConfig.class)) {
            CachedService service = context.getBean(CachedService.class);

            System.out.println("ordinaryValues="
                    + inParallel(() -> service.ordinary("A")));
            System.out.println("ordinaryLoads=" + service.ordinaryCount());

            System.out.println("syncValues="
                    + inParallel(() -> service.singleFlight("A")));
            System.out.println("syncLoads=" + service.syncCount());

            Cache direct = context.getBean(CacheManager.class)
                                  .getCache("direct");
            if (direct == null) {
                throw new IllegalStateException("missing direct cache");
            }
            latePut(direct);
        }
    }
}
```

Run from the `cache-concurrency` directory with JDK 17+ and a compatible Gradle version:

```bash
gradle run --quiet
```

If using the Gradle Wrapper: `./gradlew run --quiet`; on Windows: `gradlew.bat run --quiet`. Lines printed by the program (excluding Gradle/framework logs):

```text
getThenPut=1
atomicCompute=2
ordinaryValues=[ordinary-1, ordinary-2]
ordinaryLoads=2
syncValues=[sync-1, sync-1]
syncLoads=1
sourceVersion=2
cacheVersion=1
```

The list from the two Futures is sorted so it does not depend on which thread finishes first. The `ordinary` case uses a latch inside the body: the first body must wait for the second body to arrive, ensuring both calls passed the cache miss before either body can return.

Conversely, **do not** place a latch waiting for both threads to enter the body of `singleFlight`: when load synchronization works, only one thread enters the body while the other waits on the entry; waiting for two bodies would deadlock. The example uses `sync=true` properly with one cache and no `unless`.

### 4.3. Why are the results meaningful?

**`getThenPut=1`:** both threads read 0 before being allowed to put. Both puts are valid, yet they only write 1.

**`atomicCompute=2`:** both `compute` operations update one mapping under `ConcurrentHashMap`'s atomic contract.

**`ordinaryLoads=2`:** with default `@Cacheable`, two misses for the same key can both run the method. This is a **duplicate load**, with no corruption inside the cache store.

**`syncLoads=1`:** `ConcurrentMapCacheManager` and `@Cacheable(sync=true)` handle the same key via synchronized loading. Both calls receive `sync-1`, with one computation.

**`sourceVersion=2` and `cacheVersion=1`:** the slow loader held snapshot 1 while the origin advanced to 2 and was evicted. Afterward the loader still put 1 into the cache; this is a **stale put after eviction**. Individual `Cache.get`, `Cache.evict`, and `Cache.put` calls did not fail—what went wrong is that their relative ordering was not protected for business consistency.

The last scenario manipulates `Cache` directly to expose the ordering. In real applications, similar races happen when loaders, invalidations, and origin updates run across threads or services; the exact behavior depends on the provider.

## 5. What @Cacheable(sync=true) solves — and does not solve

`sync=true` is useful when:
- An empty key is queried by multiple concurrent requests.
- The load is I/O- or CPU-heavy so duplicate loads are wasteful.
- The cache backend is verified to support synchronized loading within the desired scope.

However, it **does not** create a global transaction. Even if only one thread loads per key, you must still consider:
- Another request modifying the origin data and evicting the cache mid-load.
- Another cache region needing a simultaneous update.
- Two dependent keys needing to stay consistent as an aggregate.
- Other instances that do not share the same locking mechanism.
- A loader timing out, being cancelled, returning null, or throwing an exception.
- Providers with asynchronous caching, delayed eviction, or differing serialization behavior.

`Cache.get(key, Callable)` is a convenient API for asking a provider to get or load. The provider's actual synchronization level and atomicity must be verified; do not assume every implementation behaves like `ConcurrentHashMap.computeIfAbsent`.

## 6. Alternative mechanisms to choose by scope

| Need | Option | What to verify |
| --- | --- | --- |
| Read/write independent mappings without corrupting structure | `ConcurrentHashMap`, concurrent cache provider | Thread safety of individual operations |
| Increment/update one key within the same JVM | `compute`, `merge`, CAS, suitable atomic variable | Atomicity of the mapping/variable, not DB transactions |
| Avoid loading the same key concurrently | `@Cacheable(sync=true)` when supported by provider | Sync scope, single cache, `unless` |
| Protect a get-check-update sequence in the same process | `synchronized`/`ReentrantLock` or keyed lock wrapping **the whole sequence** | Lock errors, contention, deadlock, JVM scope |
| Prevent an old loader from overwriting a newer version | Versioned cache keys, generation/epoch, conditional put if supported by provider | Version must be updated/read consistently |
| Atomicity across multiple database rows | Transactions and optimistic/pessimistic locking | Isolation, retries, and rollbacks |
| Multi-node distributed cache | Atomic script/CAS/distributed lock with TTL/fencing if truly needed | Lock loss, network partitions, retries |
| Evict cache after database commit | Transaction-aware cache, after-commit event, or outbox | Eviction races with in-flight loaders |

### 6.1. Why putting synchronized on the body is rarely enough

If you only write:

```java
@Cacheable("books")
public synchronized Book load(String id) {
    return repository.findById(id);
}
```

This is an illustrative snippet. `synchronized` wraps the **method body**; however, the cache miss check happens **before** Spring invokes the body via the proxy. Two requests can still both observe a miss, enter the `synchronized` body one after the other, and both execute the query. To protect both lookup and computation, the lock must wrap **the entire cache path**, or you must use a provider supporting `sync=true` appropriately.

### 6.2. Using compute/merge for a single mapping

```java
// Illustrative snippet: counts is ConcurrentHashMap<String, Integer>.
counts.merge("A", 1, Integer::sum);
counts.compute("B", (key, old) -> old == null ? 1 : old + 1);
```

These updates are appropriate when the state to protect **lives inside a single map entry**. Avoid slow queries, updating the map itself, or recursive calls inside the mapping function—they can cause blocking, errors, or deadlocks.

If you need to update **two keys together**, per-key atomicity is still insufficient; design a critical section or transaction for the entire aggregate involved.

### 6.3. Keys with version/generation

Suppose before an update, the cache key is `product:42:v7`; after the update, the origin version increments to `v8` and new requests use key `product:42:v8`. The old loader can only write to the version-7 namespace and cannot pollute the version-8 entry.

This strategy reduces races between old loads and invalidation, but you must ensure the current version is resolved accurately and have a TTL/cleanup policy for old entries. Versioning does not by itself solve every consistency issue in the database.

## 7. Races between cache and database

Even when updating data and then evicting the cache, you can still hit:

```text
T1: cache miss K
T1: read origin data V1, start slow computation
T2: update origin to V2
T2: evict K
T1: put K = V1 after eviction
T3: cache hit K = V1  (stale)
```

Evicting "after commit" prevents some inconsistent states, but if you need strong freshness **under every interleaving**, you must also account for in-flight loaders, versions, write ordering, and the provider.

You can use versioned keys, check the generation before putting, coordinate a shared critical section between reads/updates, or rely on the data store's consistency mechanisms. For short-TTL caches serving advisory data, a brief stale window may be acceptable; for prices, inventory, or permissions, SLAs must be strictly defined.

Do not turn the cache into the sole source of authorization. A cache hit still needs proper tenant/user scoping and appropriate permission checks.

## 8. Common misconceptions

| False conclusion | Reality |
| --- | --- |
| "The map is thread-safe, so get+put is atomic." | Two separate operations can be interleaved. |
| "@Cacheable by default lets only one thread load per key." | Two requests missing the same key can run the body twice. |
| "sync=true is a distributed lock." | Depends on provider and scope; does not guarantee multi-node coordination. |
| "AtomicInteger makes all transactions atomic." | It only applies to operations on that atomic variable per its contract. |
| "Evict already finished, so an old loader cannot put." | An in-flight loader can still finish and write stale data. |
| "The cache is thread-safe, so mutable values are thread-safe too." | Object mutations require their own synchronization. |
| "With a DB transaction, the cache is always synchronized." | Commit timing, invalidation, races, and provider behavior must still be coordinated. |
| "Thread.sleep makes race tests deterministic." | Sleep cannot enforce ordering; use bounded barriers/latches. |

## 9. Practical testing checklist

1. **Define the guarantee scope:** one mapping, one key, one process, or multiple nodes?
2. **Two misses on one key:** force concurrency with a latch; measure body executions with `sync=false` and `sync=true`.
3. **Two different keys:** verify per-key sync does not turn into an unnecessary global lock.
4. **Read-modify-write:** force two threads to read the same value before putting; compare with `compute/merge`.
5. **In-flight loader:** pause after reading origin, update origin + evict, let loader put, and check for staleness.
6. **Timeouts/exceptions:** does a failing loader leave an entry behind? Are waiting threads released or retried?
7. **Multiple cache regions:** does updating one region leave dependent regions stale?
8. **Transactions:** what are the timing and visibility of commit/rollback alongside eviction?
9. **Multiple JVMs:** test against the real shared backend, not just an in-memory cache on one instance.
10. **Observability:** hit/miss ratios, duplicate DB loads, contention, p95/p99 latency, backend errors, and TTL.

In integration tests, always invoke services through the **Spring bean/proxy**. Calling `new CachedService()` or calling `this.ordinary(...)` internally inside the target will not prove that cache annotations work in default proxy mode.

## 10. Self-check questions

**Q1.** Two threads both call `ConcurrentHashMap.get("n")` and then `put("n",old+1)`; will the map structure break, and is the result guaranteed to increase by 2?

**Answer:** It will not break because accesses are valid; however, increasing by 2 is not guaranteed because a lost update can happen.

**Q2.** What does `compute` solve?

**Answer:** Atomic remapping for a single mapping in `ConcurrentHashMap`; it does not create a transaction with a database or across two caches.

**Q3.** Why can two `@Cacheable` requests load the same key twice?

**Answer:** Both can cache-miss before a cache put occurs; Spring does not lock the whole loading sequence by default.

**Q4.** Does `sync=true` guarantee single-flight across every pod and every cache?

**Answer:** No. You must verify the provider, scope, and constraints of the feature.

**Q5.** Can data become stale right after an eviction?

**Answer:** Yes. An older in-flight loader can put after the evict; coordination or versioning is needed if strict consistency is required.

**Q6.** Should you put `synchronized` on the method body and conclude that cache lookup is protected?

**Answer:** No. Cache lookup usually occurs in the proxy before the body, so two requests can still miss together.

## 11. Takeaways

- **Thread-safe store ≠ atomic sequence ≠ end-to-end business transaction.**
- `ConcurrentHashMap.get+put` can lose updates; `compute/merge` are suitable for atomic per-key updates.
- Default `@Cacheable` can duplicate loads; `sync=true` helps when supported by the provider, but is not a distributed consistency guarantee.
- Eviction does not eliminate the possibility of an older loader writing stale data afterward.
- Prove behavior with controlled interleavings, and design consistency according to real data requirements.

### Official Documentation

- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — @Cacheable.sync Javadoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/annotation/Cacheable.html)
- [Spring Framework — Cache API](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/cache/Cache.html)
- [Spring Framework — ConcurrentMapCache](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCache.html)
- [Java SE 17 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
