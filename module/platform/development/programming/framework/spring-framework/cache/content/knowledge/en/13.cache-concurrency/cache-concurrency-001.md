# Multiple Threads Missing the Same Key and Recomputing Repeatedly

In a system using Spring Cache, a **cache miss** occurs when a key has no stored result yet, or when its entry has been evicted/expired. When **multiple threads concurrently invoke a method with the same cache name and cache key**, they can all observe a cache miss before any thread finishes storing the result. Each thread runs the same expensive computation again on its own. This phenomenon is commonly called a **cache stampede**, **dogpile effect**, or **thundering herd** at the data-loading layer.

**Example:** 100 concurrent requests ask for product **P01** whose TTL just expired. If each request queries the DB for 150 ms, a single cache miss that should have required only one query can turn into 100 nearly simultaneous queries. The cache stops reducing load at the exact moment it matters most.

This lesson explains the mechanism, impact, how to use **@Cacheable(sync = true)** and its limitations, and provides a **Java 17 + Spring Framework** project reproducing the unsynchronized and synchronized cases with observable results via **CountDownLatch**.

## 1. Same key: why do multiple threads all cache miss?

The typical mechanism of **@Cacheable** without synchronized data loading:

1. Compute **cache name + cache key** from the method and arguments.
2. Call the cache to look up the entry.
3. On hit, immediately return the stored data without executing the method.
4. On miss, **execute the method** to produce the result.
5. Write the result into the cache so subsequent calls can hit.

The critical point lies between step 2 and step 5: the two operations—**reading the cache** and **loading/writing the result**—are not by default a single critical section per key. Multiple threads can pass step 2 before any thread completes step 5.

~~~text
Time              Thread A                   Thread B
    |        get("P01") -> MISS        get("P01") -> MISS
    |        query DB / HTTP...       query DB / HTTP...
    |        compute result           recompute same result
    |        put("P01", value)         put("P01", value)
    v        return data               return data
~~~

The cache may still end up holding a valid entry; however, **the expensive computation ran multiple times**. If the data is read at different moments or the computation has side effects, the results across threads may even differ. A result that finishes later can write to the cache afterward and replace the earlier value, depending on the provider and actual ordering.

**Do not confuse with hash code collisions:** the calls here intentionally share the same **logical key**; the issue is multiple concurrent misses, not two semantically different objects accidentally producing the same key.

## 2. Conditions that trigger a stampede and its consequences

Common scenarios:

- **Cold start / fresh deployment:** the cache starts empty and many requests read popular data at once.
- **A hot key just reached its TTL:** thousands of users need the same entry right after expiration.
- **Bulk invalidation:** an event evicts an entry that many requests are actively using.
- **Cache node restart / memory-pressure eviction:** many keys become missing at the same time.
- **Slow database/HTTP backend:** the longer the window from miss to put, the more requests have a chance to miss together.
- **Traffic bursts:** requests arrive nearly simultaneously after an event, campaign, or content update.

| Consequence | Explanation |
| --- | --- |
| Duplicate DB/API queries | Consumes CPU, connection pools, quota, and bandwidth |
| Increased latency | Multiple threads must wait on the expensive computation |
| Feedback loop amplification | Slow backend -> wider miss window -> even more requests miss |
| Higher cost | Calling third-party services may be billed per request |
| Race/overwrite | Results computed at different times can overwrite the same key |
| Cascading failure | Exhausted thread pools/DB pools, timeouts, and retries amplify load |

**Distinction:** A *same-key stampede* happens when many calls wait on the same result. A *cache avalanche* can occur when a large batch of **different keys** expire together, causing heavy aggregate load. A per-key locking solution reduces duplicate computation for *one key* but **does not by itself solve** thousands of distinct keys expiring at the same time.

## 3. @Cacheable(sync = true): coordinating loads for the same key

Spring allows declaring:

~~~java
@Cacheable(cacheNames = "products", key = "#p0", sync = true)
public Product findById(String productId) {
    return repository.fetch(productId);
}
~~~

In an environment where the Cache implementation supports synchronized data loading, threads that concurrently miss **the same cache key** participate in a **get-or-load** operation: one thread executes the computation, while the remaining threads wait and use the loaded result.

~~~text
                       cache "products", key "P01"
       ┌────────────────────┼────────────────────┐
       │                    │                    │
    Thread A             Thread B             Thread C
       │                    │                    │
       └──── concurrent miss┴────────────────────┘
                            │
                    per-key load coordination
                            │
                   1 thread fetches from DB
                            │
                      write 1 entry
                            │
                  threads receive result
~~~

**Proper interpretation:** **sync = true** is a request/hint for the cache provider to synchronize loading of an entry. It **does not mean** Spring automatically creates a distributed lock guaranteeing only one execution across the entire cluster. Actual effectiveness depends on the CacheManager and the implementation of **Cache.get(key, Callable)** or an equivalent loading mechanism.

With **ConcurrentMapCache** inside a single JVM, the get-or-load mechanism can use atomic per-key computation on the concurrent map so the same key is loaded only once during a concurrent miss burst. With Caffeine, the proper mode/cache configuration must be checked. With Redis or a distributed provider, you must read the documentation on locking/load atomics and test across multiple instances: per-JVM sync or a cache operation without distributed locking **is not enough to claim** that only one replica queries the DB.

### Constraints of the sync annotation

For **@Cacheable(sync = true)** in Spring Framework, keep in mind:

1. **Declare only one cache** in that cacheable operation.
2. **Do not use the unless attribute** to veto a result after computation.
3. **Do not combine another cache operation on the same method** under the synchronized caching rules.
4. The cache provider must support synchronized semantics; this is a hint, not a universal guarantee.

Examples to avoid:

~~~java
// INVALID under synchronized caching constraints:
// @Cacheable(cacheNames = {"A", "B"}, sync = true)
// public Item load(String id) { ... }

// INVALID:
// @Cacheable(cacheNames = "A", sync = true,
//            unless = "#result == null")
// public Item load(String id) { ... }
~~~

**sync = true** does not automatically add tenant/locale/currency to the key. If the key is missing components, semantically different requests can be coalesced to **wrong data** even though duplicate computation stops. Before optimizing concurrency, the key must be business-correct.

## 4. Quantitative example: why waiting on each other can be cheaper than recomputing?

Suppose 40 requests arrive for the same key within 100 ms, and each origin query takes 200 ms.

| Without load coordination | With per-key load coordination |
| --- | --- |
| Many requests miss together and may run dozens of origin queries | One origin query serves multiple waiting requests |
| Backend endures heavy duplicate work | Backend experiences reduced load for the hot key |
| Multiple results are put concurrently | A single load can be shared |
| Can exhaust the connection pool | Fewer queries, though callers wait on one result |
| High total CPU/DB cost | Must account for lock overhead, wait time, and error handling |

Do not conclude that every request becomes faster: concurrent requests still have to wait for the first computation. The main benefit is **not duplicating work** and avoiding overwhelming backend resources. When the computation is very fast, synchronization overhead may be negligible or even outweigh the benefit; you must measure under realistic load.

## 5. Java 17 + Spring project: reproducing six threads missing the same key

The example uses **Spring Framework 6.1.14**, **Java 17+**, **ConcurrentMapCacheManager**, and Java concurrency primitives. It does not rely on sleep to guess timing; **CountDownLatch** forces all six threads in the unsynced case to enter the method body before any thread is allowed to return a result.

Structure:

~~~text
spring-cache-stampede-demo/
├── settings.gradle
├── build.gradle
├── src/main/java/demo/cache/CacheStampedeDemo.java
└── src/test/java/demo/cache/CacheStampedeDemoTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'spring-cache-stampede-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
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
    mainClass = 'demo.cache.CacheStampedeDemo'
}

test {
    useJUnitPlatform()
}
~~~

**src/main/java/demo/cache/CacheStampedeDemo.java**

~~~java
package demo.cache;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class CacheStampedeDemo {
    public static final int REQUESTS = 6;

    @Configuration
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("plain", "synced");
        }

        @Bean
        public WorkService workService() {
            return new WorkService();
        }
    }

    public static class WorkService {
        private final AtomicInteger plainLoads = new AtomicInteger();
        private final AtomicInteger syncLoads = new AtomicInteger();

        // Without sync: all six executions will wait here.
        private final CountDownLatch plainEntered =
                new CountDownLatch(REQUESTS);
        private final CountDownLatch plainRelease = new CountDownLatch(1);

        // With sync: only one call enters the method body on miss.
        private final CountDownLatch syncEntered = new CountDownLatch(1);
        private final CountDownLatch syncRelease = new CountDownLatch(1);

        @Cacheable(cacheNames = "plain", key = "#p0")
        public String plain(String key) {
            int n = plainLoads.incrementAndGet();
            plainEntered.countDown();
            await(plainRelease);
            return "plain:" + key + ":" + n;
        }

        @Cacheable(cacheNames = "synced", key = "#p0", sync = true)
        public String synced(String key) {
            int n = syncLoads.incrementAndGet();
            syncEntered.countDown();
            await(syncRelease);
            return "synced:" + key + ":" + n;
        }

        public void awaitAllPlainMisses() {
            await(plainEntered);
        }

        public void awaitOneSyncedLoad() {
            await(syncEntered);
        }

        public void releasePlain() {
            plainRelease.countDown();
        }

        public void releaseSynced() {
            syncRelease.countDown();
        }

        public int plainLoads() {
            return plainLoads.get();
        }

        public int syncLoads() {
            return syncLoads.get();
        }
    }

    private static void await(CountDownLatch latch) {
        try {
            if (!latch.await(15, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timed out at latch");
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", e);
        }
    }

    static List<Future<String>> submit(
            ExecutorService executor, Callable<String> task) {
        List<Future<String>> pending = new ArrayList<>();
        for (int i = 0; i < REQUESTS; i++) {
            pending.add(executor.submit(task));
        }
        return pending;
    }

    static int countDistinct(List<Future<String>> pending)
            throws Exception {
        Set<String> values = new HashSet<>();
        for (Future<String> future : pending) {
            values.add(future.get(15, TimeUnit.SECONDS));
        }
        return values.size();
    }

    public static void main(String[] args) throws Exception {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            WorkService service = context.getBean(WorkService.class);
            ExecutorService pool = Executors.newFixedThreadPool(REQUESTS);
            try {
                // Six workers all miss the same key "K1" before put.
                var plainTasks = submit(pool, () -> service.plain("K1"));
                service.awaitAllPlainMisses();
                service.releasePlain();

                int distinctPlain = countDistinct(plainTasks);
                System.out.println("plainLoads=" + service.plainLoads());
                System.out.println("plainDistinct=" + distinctPlain);

                // On another cache, six workers all miss the same key.
                var syncedTasks = submit(pool, () -> service.synced("K1"));
                service.awaitOneSyncedLoad();
                service.releaseSynced();

                int distinctSynced = countDistinct(syncedTasks);
                System.out.println("syncLoads=" + service.syncLoads());
                System.out.println("syncDistinct=" + distinctSynced);

                // Cache already holds the result: hit does not increment counter.
                service.synced("K1");
                System.out.println("syncAfterHit=" + service.syncLoads());
            } finally {
                // On error, prevent workers from getting stuck at latches.
                service.releasePlain();
                service.releaseSynced();
                pool.shutdownNow();
            }
        }
    }
}
~~~

Run from the project directory with Gradle suitable for Java 17 (or the project's Gradle wrapper if generated):

~~~bash
gradle run --quiet
~~~

The output printed by **System.out.println** is in the following order, with **ConcurrentMapCacheManager** and six threads executed as in the example:

~~~text
plainLoads=6
plainDistinct=6
syncLoads=1
syncDistinct=1
syncAfterHit=1
~~~

Exact explanation:

1. **plain** does not use **sync**. All six workers miss key **"K1"** in cache **plain** and enter the method body; each worker increments **plainLoads** and waits. The controller only opens the latch once **6 executions** are inside. Therefore **plainLoads = 6**, and the results contain sequence numbers 1 through 6, yielding **6 distinct results**.
2. **synced** uses **sync = true**. With ConcurrentMapCache, one worker computes the result of **"K1"** for cache **synced**; the other workers receive that result instead of recomputing. **syncLoads = 1**, **syncDistinct = 1**.
3. Calling **synced("K1")** one more time afterward is a cache hit, so the counter remains 1.

**Why are the results conclusive?** The plain part uses a latch counting all six method invocations **before allowing any method to return**, so it is not a lucky guess based on **Thread.sleep()**. The sync part allows exactly one invocation into the body while the remaining calls use the newly created entry. Do not put a latch waiting for six invocations *inside* the synced method: that would deadlock because the sync mechanism intentionally lets only one loader enter the method body.

**Limitations of the result:** The project uses Spring's local cache and a single JVM. The **syncLoads=1** guarantee relies on the provider supporting synchronized get-or-load; do not extrapolate this result to a Redis cluster or two separate JVMs.

### Testing with JUnit 5

**src/test/java/demo/cache/CacheStampedeDemoTest.java**

~~~java
package demo.cache;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(CacheStampedeDemo.Config.class)
class CacheStampedeDemoTest {

    @Autowired
    CacheStampedeDemo.WorkService service;

    @Test
    void sameKeyBurstIsComputedOnceWithSync() throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(
                CacheStampedeDemo.REQUESTS);
        try {
            var plain = CacheStampedeDemo.submit(
                    pool, () -> service.plain("K1"));
            service.awaitAllPlainMisses();
            service.releasePlain();

            assertEquals(6, CacheStampedeDemo.countDistinct(plain));
            assertEquals(6, service.plainLoads());

            var synced = CacheStampedeDemo.submit(
                    pool, () -> service.synced("K1"));
            service.awaitOneSyncedLoad();
            service.releaseSynced();

            assertEquals(1, CacheStampedeDemo.countDistinct(synced));
            assertEquals(1, service.syncLoads());

            assertEquals("synced:K1:1", service.synced("K1"));
            assertEquals(1, service.syncLoads());
        } finally {
            service.releasePlain();
            service.releaseSynced();
            pool.shutdownNow();
        }
    }
}
~~~

Run:

~~~bash
gradle test
~~~

Expected: **one JUnit test passes** on a suitable Spring and JDK 17 environment. This is a real integration test retrieving the bean from the ApplicationContext; calling **new WorkService()** directly will not activate the cache interceptor as intended.

The test uses **timeouts on latches and Future.get** to avoid hanging indefinitely if misconfigured. On timeout, the test should fail clearly rather than increasing wait times indefinitely to hide bugs. Detailed build output depends on Gradle/JDK, so there is no fixed stdout for the test command.

## 6. Why shouldn't you synchronize the whole method yourself with synchronized?

An easy idea that comes to mind:

~~~java
public synchronized Product findById(String id) {
    return repository.fetch(id);
}
~~~

However, **synchronized** on a method sharing a single instance can cause **all keys** to be serialized within that synchronized scope. A call for **P01** also blocks a call for **P02**, even though the two computations are independent. If a method belongs to multiple bean instances, synchronized on one object does not protect another instance either, let alone protect across multiple replicas.

When the goal is to avoid **multiple misses on the same key**, a better solution is usually **single-flight/per-key coordination** rather than locking the entire service. **@Cacheable(sync = true)** with a suitable provider is a simple way to request this behavior within a cache region. A different key can be loaded concurrently instead of waiting behind a hot key.

**Do not roll your own Map<key,Lock>** unless you properly manage lock lifecycle, key cardinality, errors/timeouts, and memory leak risks. If more complex coordination is needed, use primitives with clear semantics or a cache library that supports loaders.

## 7. Cases where sync = true is not enough

### 7.1. Multiple replicas or multiple processes

Suppose a service has three replicas A/B/C; each replica uses its own **ConcurrentMapCacheManager**. When all miss **P01** together, the following can happen:

~~~text
Replica A: local miss P01 -> 1 DB query
Replica B: local miss P01 -> 1 DB query
Replica C: local miss P01 -> 1 DB query
~~~

Even if **each JVM computes only once per key**, the overall system can still make **3 DB queries**. **sync = true** does not automatically turn a local cache into a distributed cache.

If using a shared cache like Redis, you still need to check whether the **provider and cache writer** perform locking/load coordination across replicas. Do not infer simply from pointing to the same Redis that all processes share a loader lock.

Options depending on requirements: distributed locking with **lease/timeout and fencing**, request coalescing at a shared layer, proactive refresh, or accepting some duplicate queries accompanied by rate limiting. Distributed locks are not free: you must handle dead lock holders, timeouts, retries, clock/lease drift, and consistency after lock expiration.

### 7.2. Different keys expiring together

**sync = true** typically coordinates **per key**. If 10,000 keys reach their TTL at the same time, 10,000 independent loaders can still run. Consider:

- **TTL jitter:** add controlled variance to expiration times to spread load, if the provider supports it.
- **Refresh-ahead / prewarming:** load hot keys before they expire when possible.
- **Stale-while-revalidate:** serve the old result for a short window while refreshing in the background via a separate mechanism and accepting bounded staleness.
- **Bulkheads and concurrency limits:** cap concurrent load to the DB/API.
- **Circuit breakers and backpressure:** avoid piling unlimited retries onto a degraded backend.
- **Sharding or tiered caching:** reduce hotspots, though consistency and invalidation must be addressed.

Not all of the above features are built into the **@Cacheable** annotation. They may require specific providers, libraries, or custom designs. Choose based on freshness SLA, backend capacity, and acceptable complexity.

### 7.3. Failing, slow, or null-returning loaders

If a loader **throws an exception**, the result is normally not stored as a successful value; other callers or subsequent calls may need to recompute. When multiple threads wait together, verify the provider's exact exception propagation/retry semantics; do not assume every caller sees the exact same exception.

If a loader hangs or takes several seconds, threads waiting on a hot key can cause **head-of-line waiting**. Synchronization reduces the number of computations; it does not set DB timeouts or prevent unbounded queues. You need timeouts, bounds on waiting callers, fallbacks, and monitoring.

Whether a **null** result is cached depends on the implementation and configuration; for example, ConcurrentMapCache supports storing null via an internal conversion mechanism when enabled. For "not found" data, consider **negative caching** with a short TTL if business rules allow. Do not assume a null result is cached forever or never cached.

### 7.4. Invalidation during computation

One thread is loading **P01** while another thread updates the DB and then **@CacheEvict** also targets **P01**. Depending on timing, the loader may return the stale read and write it into the cache **after eviction**, causing the stale entry to reappear. **sync = true** primarily handles *multiple loaders for the same key*; it **does not guarantee** atomic consistency between source updates and cache invalidation.

For data requiring high consistency, consider commit/evict ordering, versioned keys, optimistic checks, version-consistent cache-aside, or after-commit events/outbox. You must test races between loading and updating, not only concurrent reads.

## 8. Cache key design directly determines lock scope

Two calls are considered the "same key" according to the **cache name + key that Spring/the Cache implementation actually receives**, not just the parameter names in source code.

~~~java
@Cacheable(cacheNames = "quotes", key = "#p0", sync = true)
public Quote quote(String sku, String tenant, String currency) {
    return gateway.quote(sku, tenant, currency);
}
~~~

The annotation above **synchronizes over the wrong data domain** because the same SKU with different tenants/currencies can be collapsed into the same entry; **sync = true** does not fix that bug. If the output depends on all three dimensions, use a key with all components:

~~~java
@Cacheable(
    cacheNames = "quotes",
    key = "T(java.util.List).of(#p0, #p1, #p2)",
    sync = true
)
public Quote quote(String sku, String tenant, String currency) {
    return gateway.quote(sku, tenant, currency);
}
~~~

The **List.of** example requires non-null arguments and is suitable for illustrating a cache holding Java keys. With distributed caches, verify the key serializer; you can use a structured/encoded key that is stable by contract.

**Rule of thumb:** too narrow a key -> wrong-data cache hits; too wide a key -> calls that should share an entry miss each other, increasing stampedes and cache footprint. Key design must follow the business contract before optimizing concurrency.

## 9. Performance analysis and benchmarking

Do not only verify that the application throws no exceptions. Measure metrics under same-key and multi-key load:

| Metric | Interpretation |
| --- | --- |
| **loader invocations/key** | Actual computation count for a key after a cold miss |
| **cache hit/miss** | Frequency of lookups finding data; note hit ratio can be skewed by wrong keys |
| **DB/API requests** | Total backend calls after a burst |
| **latency p50/p95/p99** | Caller latency, including time spent waiting on the loader |
| **waiting threads/queue** | Number of callers waiting on a key and wait duration |
| **timeout/error/retry rate** | Contention bottlenecks or errors amplified by retries |
| **TTL/eviction/refresh metrics** | When entries expire and their impact on bursts |
| **distributed replication count** | How many times a key is loaded across the cluster, not just one JVM |

Recommended tests:

1. **Same-key cold miss:** n workers start simultaneously; unsynced often yields up to n loaders, while a supporting sync provider should drop near 1 loader.
2. **Hit after loading:** call 10 more times and verify the loader count does not increase.
3. **Two different keys:** test P01 and P02; ensure you do not accidentally lock the entire service.
4. **Method throws exception:** measure waiting behavior, retries, and cache state after failure.
5. **Evict mid-load:** check whether a stale result can return.
6. **Multiple replicas:** run load tests across processes against the same or different cache providers.
7. **Timeouts and resource pressure:** bounded pools, high backend latency, retries, and request cancellation.

Use **CountDownLatch/Barrier** to control test ordering; avoid **Thread.sleep(100)** and treating a single run as conclusive proof. When testing sync, wait for only **one loader to enter the method**; other callers cannot enter the method body simultaneously if sync works. Do not set a barrier waiting for n loaders inside a synced method because that will deadlock.

## 10. Choosing a solution by context

| Context | Preferred direction |
| --- | --- |
| Single JVM, local cache, one hot key | **@Cacheable(sync = true)** with a provider verified to support it |
| Multiple JVMs with local caches | Cluster-level coordination if system-wide single-flight is truly needed |
| Shared Redis without per-key distributed load lock | Do not assume cluster-wide sync; test the provider and consider locking/coalescing |
| Many keys expiring together | TTL jitter, prewarming/refresh, bulkhead |
| Very slow or occasionally failing loader | Timeouts, circuit breaker, queue bounds, fallback/negative caching |
| Cache changes while computing | Versioning design, after-commit invalidation, race handling |
| Output depends on tenant/locale/currency | Correct keys and security boundaries first, then sync |

If data requires extreme consistency, sometimes **not caching**, narrowing the cache scope, or using a controlled consistent read data source is better than layering complex locks.

## 11. Common pitfalls

- **Assuming @Cacheable blocks same-key misses by default:** there is no such guarantee.
- **Interpreting sync = true as a distributed lock:** synchronization level depends on the Cache implementation, and local caches do not coordinate across processes.
- **Assuming sync solves a multi-key avalanche:** sync mainly coalesces work per key.
- **Combining sync=true with unless/multiple caches/other operations:** violates synchronized caching constraints.
- **Applying synchronized to the entire method:** can serialize even independent keys.
- **Testing with arbitrary Thread.sleep:** results can flake; actively coordinate with latches.
- **Waiting for n loaders inside a synced method:** easily deadlocks since the intended mechanism lets only one loader enter.
- **Omitting tenant/currency from the key:** reduces loader count but can return wrong data across contexts.
- **Ignoring exceptions and long-running loaders:** many callers wait on a single bottleneck; timeouts/backpressure are needed.
- **Ignoring races between eviction and load:** stale data can be written back after invalidation.
- **Writing an uncleaned local lock Map:** can leak locks and introduce new races.
- **Confusing @CacheEvict with single-flight:** deleting an entry causes a new miss; it does not coordinate loaders.

## 12. Self-check questions

1. Why can all 10 threads query the DB when they concurrently cache-miss the same key, even though only one entry ends up stored?
2. What is the difference between a **single-key cache stampede** and a **multi-key cache avalanche**?
3. Which step in the typical cache-aside flow does **@Cacheable(sync = true)** aim to change?
4. Why does **sync=true** in a single JVM with ConcurrentMapCache not guarantee a single computation across the whole cluster?
5. What are the constraints of synchronized caching regarding **unless**, cache count, and other annotations?
6. Why does using a barrier requiring all six workers to enter the **synced** method body hang the test?
7. If a Product changes while the cache is loading an old version, what risk remains even with sync=true?
8. When are TTL jitter, refresh-ahead, or bulkheads needed instead of only per-key sync?
9. Why can **key = "#p0"** be dangerous for a method accepting SKU, tenant, and currency?
10. When a loader fails, what should be verified about retries/timeouts and cache state?

**Summary:** Multiple threads missing the same key can lead to duplicate computation and load spikes. **@Cacheable(sync = true)** is an appropriate tool to request *one loader per key* when supported by the cache provider, but it does not replace key design, consistency, error handling, resource bounds, or cross-process synchronization. Test with coordinated concurrency, measure actual loader executions, and verify behavior on the provider in use.

### Official Documentation

- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Synchronized Caching and @Cacheable(sync): https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — @Cacheable Javadoc (sync constraints): https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Framework — Cache.get(key, Callable): https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/cache/Cache.html
- Spring Framework — ConcurrentMapCache Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCache.html
- Spring Framework — AOP proxying and self-invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
