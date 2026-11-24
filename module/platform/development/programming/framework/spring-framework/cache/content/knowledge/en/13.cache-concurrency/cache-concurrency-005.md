# Synchronization Scope Within a Single Process vs. Across Machines with Spring Cache

## Learning objectives

In a system handling concurrent requests, two or more threads can encounter a **cache miss** together and run an expensive task simultaneously. Spring provides `@Cacheable(sync = true)` to ask the cache provider to coordinate calls for the same key. However, a **JVM-local** lock or cache store does not automatically become a synchronization mechanism across multiple machines, containers, or replicas.

After this lesson, you will be able to:

1. Distinguish concurrency in one thread, multiple threads in the same JVM, and multiple processes/machines.
2. Explain cache stampede, cache-aside, race conditions, and the true meaning of `@Cacheable(sync = true)`.
3. Distinguish **sharing a cache data store** from **sharing a distributed locking mechanism**.
4. Write, run, and test a Java 17 + Spring Boot example for same-key calls within a single JVM.
5. Evaluate Redis, Caffeine, `ConcurrentMapCacheManager`, and provider-dependent synchronization capabilities.
6. Choose a practical strategy: local single-flight, distributed coordination, expiration jitter, stale-while-revalidate, or a design that tolerates recomputation.
7. Recognize races around lock expiration, process crashes, stale data, transactions, and the limits of "computed only once" claims.

**Core principle:** `sync=true` is a *hint* to the cache implementation, **not a contract guaranteeing cluster-wide exactly-once execution**. Always identify the exact boundary within which participants actually share synchronization state.

## 1. The problem begins with concurrent cache misses

Suppose a service has a report-generation method:

~~~java
// Illustrative snippet on a Spring-managed service.
@Cacheable(cacheNames = "reports", key = "#p0")
public Report generate(String reportId) {
    return expensiveCalculation(reportId);
}
~~~

Once the cache holds `reportId="R1"`, many requests can quickly retrieve the same value. Yet when the cache just started, was cleared, or the entry just expired, a burst of requests observes a miss together.

~~~text
10:00:00.000  Thread A: GET reports/R1 -> MISS
10:00:00.001  Thread B: GET reports/R1 -> MISS
10:00:00.002  Thread C: GET reports/R1 -> MISS

Thread A -> generate(R1) -> DB/CPU
Thread B -> generate(R1) -> DB/CPU
Thread C -> generate(R1) -> DB/CPU

A/B/C can all compute the same report and then put the same key.
~~~

The phenomenon of multiple requests rebuilding an expired value together is called a **cache stampede**, often also called the *dogpile effect*. If building the value takes several seconds or executes multiple DB queries, the backend can suffer a load spike right when the cache was supposed to absorb load.

One way to model it:

~~~text
N concurrent requests, cache miss on the same key
       |
       +-- Without coordination: up to N loader runs
       |
       +-- With properly scoped single-flight: 1 loader run,
                                              N-1 calls wait and reuse result
~~~

"Single-flight" is the idea of coalescing in-flight calls for the **same key** so only one call computes while the rest use its result. It differs from locking the entire cache: two independent keys like `R1` and `R2` should ideally still compute in parallel.

## 2. Three concurrency boundaries you must distinguish

| Scope | What do participants share? | How far do local locks reach? |
| --- | --- | --- |
| Single thread | Current stack and control flow | Normally no lock needed against itself |
| Multiple threads in **one JVM/application context** | Heap, cache object, Java monitors/locks | Can coordinate if sharing the same cache instance and key |
| Multiple **JVMs/processes/containers/machines** | No shared Java heap/monitors; may share DB/Redis | A Java lock in process A does not block loaders in process B |

Do not equate "two requests on the same machine" with "same process": one host can run multiple separate JVMs. Conversely, two threads handling two requests inside the **same** JVM can access the same cache object.

### Visualizing two replicas

~~~text
                        Load balancer
                           /      \
                          v        v
                    App A (JVM)  App B (JVM)
                       |            |
                 Local cache A  Local cache B
                       |            |
                       +----- DB ---+
~~~

Suppose neither local cache has `R1`. `@Cacheable(sync=true)` on App A can make threads **inside App A** coordinate; App B also has an independent group of coordinating threads. The outcome can still be **two** calls to `expensiveCalculation("R1")` hitting the DB, once per process.

No Java monitor or `static` variable automatically spans across two JVMs. Two hosts can even run the exact same source code and bean/cache names, yet those remain separate runtime objects.

## 3. How does `@Cacheable(sync = true)` work?

In Spring Cache, `@Cacheable` normally looks up the key first. When `sync=false` (the default), on a miss multiple callers can all enter the method body and then put the result.

~~~java
@Cacheable(cacheNames = "reports", key = "#p0", sync = true)
public Report generate(String reportId) {
    return expensiveCalculation(reportId);
}
~~~

With `sync=true`, Spring asks the cache provider to perform a combined **get-or-compute** operation through a contract such as `Cache.get(key, Callable)`. If the provider supports coordination, only one thread for the same key within **the scope coordinated by the provider** runs the loader, while other threads wait and use the stored result.

~~~text
Thread A: getOrLoad(R1) -> MISS -> acquire/load R1
                                -> generate(R1)
                                -> store R1
Thread B: getOrLoad(R1) -> wait/read R1 -> same result
Thread C: getOrLoad(R1) -> wait/read R1 -> same result
~~~

**Accurate reading of semantics:**

- `sync=true` is a **hint** to the provider. The Javadoc explicitly notes that a cache provider may not support synchronization as expected.
- The annotation itself does not distinguish "one machine" from "multiple machines"; scope depends on the backend implementation and topology.
- `CacheManager` implementations in core Spring Framework support synchronized caching per their contracts; that does not mean their cache instances communicate across JVMs.
- Calls must actually share the **same `cacheName`, same key, and same cache instance/coordination domain**. Different keys or different cache managers do not coordinate.
- `sync=true` does not replace transactions, does not eliminate read/write races across operation types, and does not prove exactly-once execution under failures or retries.

### Constraints of `sync=true`

Per the `@Cacheable` contract:

1. Does not support combining with `unless` (post-invocation result vetoing).
2. Only **one cache** may be specified for a synchronized operation.
3. Do not combine other cache operations on the same method with that synchronized operation.

~~~java
// Invalid: synchronized caching does not support unless.
@Cacheable(
        cacheNames = "reports",
        key = "#p0",
        sync = true,
        unless = "#result == null"
)
public Report generate(String id) {
    return expensiveCalculation(id);
}
~~~

If you need **both same-key call coalescing and skipping storage of certain results**, design another strategy (such as service-level single-flight, or a custom loader/provider with an explicit result policy); do not simply put both `sync` and `unless` on the annotation and expect Spring to handle it.

One difference in cache error handling: `sync=true` uses a combined callback to load through the provider; if that operation fails, there is no separate `put` phase to retry in the exact way `sync=false` can. `CacheErrorHandler` policies and fail-open behavior must be tested on the real provider.

## 4. JVM-local locks: what problems are they enough for?

Primitives such as `synchronized`, `ReentrantLock`, `ConcurrentHashMap.computeIfAbsent`, or an in-bean single-flight mechanism only coordinate within **that JVM's memory space**.

~~~java
// Pure Java illustration, not a complete cache provider.
private final java.util.concurrent.ConcurrentMap<String, Object> locks =
        new java.util.concurrent.ConcurrentHashMap<>();

public Object localLockFor(String key) {
    return locks.computeIfAbsent(key, unused -> new Object());
}
~~~

A monitor obtained from `localLockFor("R1")` only applies to threads using **the same** `locks` map. Another process has its own map, so the same string `"R1"` does not form a shared lock. The snippet also has a lifecycle flaw: the lock map can grow unboundedly without safe cleanup; do not copy it into production without handling memory/eviction.

If you put `synchronized` directly on the method:

~~~java
public synchronized Report generate(String id) {
    return expensiveCalculation(id);
}
~~~

then every call on **the same object instance** must wait on the others, even if `R1` and `R2` could compute independently. This can become a bottleneck. If the method is invoked across multiple service instances/JVMs, the monitors are independent as well. `synchronized` does not provide cache hits on its own and does not solve distributed coordination.

### When local single-flight is already sufficient

It fits when:

- The application runs a single instance.
- Each replica has a local cache and you accept at most one computation **per replica** on a miss.
- The loader is not prohibitively expensive; a few duplicate runs across replicas stay within resource budgets.
- You want to reduce contention during warm-up rather than needing a cluster-wide guarantee.

With 8 replicas using local caches, good per-replica synchronization can still cause **up to roughly 8 concurrent loaders** for the same key when all eight miss together. The actual count depends on traffic, load, and timing, not a fixed constant.

## 5. Runnable Java 17 example: multiple threads, one cache instance

This example uses **Spring Boot 3.3.5, Java 17, Maven**, `@EnableCaching`, and `ConcurrentMapCacheManager`. Eight tasks wait on a `CountDownLatch` and concurrently call the service bean with the **same key `"X"`**. With this in-memory manager and `sync=true`, they receive one value while the loader runs once inside the same application context.

To demonstrate isolation, the program creates **another `ConcurrentMapCacheManager`** and checks that it cannot see the entry from the first manager. These are **two managers inside the same JVM** used to illustrate memory isolation; this is not a two-machine test. Two machines are isolated even more strongly unless they share a backend/coordination layer.

### Project structure

~~~text
cache-sync-scope-demo/
├── pom.xml
└── src/main/java/example/sync/
    ├── DemoApplication.java
    └── ExpensiveService.java
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
    <artifactId>cache-sync-scope-demo</artifactId>
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

### `src/main/java/example/sync/ExpensiveService.java`

~~~java
package example.sync;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ExpensiveService {
    private final AtomicInteger loads = new AtomicInteger();

    @Cacheable(cacheNames = "expensive", key = "#p0", sync = true)
    public String load(String id) {
        int generation = loads.incrementAndGet();
        try {
            Thread.sleep(150);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Loader interrupted", interrupted);
        }
        return "value:" + id + ":load#" + generation;
    }

    public int loadCount() {
        return loads.get();
    }
}
~~~

`Thread.sleep(150)` merely adds a small observable delay; it is not a formula guaranteeing contention. The demo outcome does not depend on tasks starting in the exact same nanosecond: if a task arrives after the entry exists, it still hits the same value.

### `src/main/java/example/sync/DemoApplication.java`

~~~java
package example.sync;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
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
        return new ConcurrentMapCacheManager("expensive");
    }

    @Bean
    CommandLineRunner demo(ExpensiveService service) {
        return args -> {
            ExecutorService workers = Executors.newFixedThreadPool(8);
            CountDownLatch start = new CountDownLatch(1);

            try {
                List<Future<String>> futures = new ArrayList<>();
                for (int i = 0; i < 8; i++) {
                    futures.add(workers.submit(() -> {
                        start.await();
                        return service.load("X");
                    }));
                }

                start.countDown();
                Set<String> uniqueValues = new HashSet<>();
                for (Future<String> future : futures) {
                    uniqueValues.add(future.get());
                }

                System.out.println("unique-results-X=" + uniqueValues.size());
                System.out.println("loads-after-X=" + service.loadCount());
                System.out.println("X-hit=" + service.load("X"));
                System.out.println("loads-after-hit=" + service.loadCount());

                System.out.println("Y-first=" + service.load("Y"));
                System.out.println("loads-after-Y=" + service.loadCount());

                CacheManager independent =
                        new ConcurrentMapCacheManager("expensive");
                boolean otherHasX =
                        independent.getCache("expensive").get("X") != null;
                System.out.println("independent-manager-has-X=" + otherHasX);
            } finally {
                workers.shutdownNow();
            }
        };
    }
}
~~~

### Running

In the `cache-sync-scope-demo` directory, with JDK 17+ and Maven installed, run:

~~~bash
mvn -q spring-boot:run
~~~

Aside from Spring startup logs, the lines printed by `CommandLineRunner` have this exact content in the demo:

~~~text
unique-results-X=1
loads-after-X=1
X-hit=value:X:load#1
loads-after-hit=1
Y-first=value:Y:load#2
loads-after-Y=2
independent-manager-has-X=false
~~~

Explanation:

1. Eight tasks call `service.load("X")` through the Spring-managed bean. `sync=true` coordinates getting or computing the same key `"X"` on the current cache instance; the real method runs only once, so `loads-after-X=1`.
2. Every task receives `value:X:load#1`, so the result set has size `1`.
3. Calling `"X"` again hits: the counter does not change.
4. `"Y"` is a different key, not yet cached; the loader runs a second time and returns `value:Y:load#2`.
5. `independent` is a **different** manager; even though it also has a cache named `"expensive"`, it has never stored `"X"`. It does not automatically see entries from the application's manager. This shows that "same cache name" **does not mean shared cache instance**.

If you run the same application in two separate JVM processes, each process has its own in-memory cache and its own `AtomicInteger`. Even with identical code and cache names, each process can still compute `"X"` once. This demo **verifies only local coordination**; it does not claim to measure cross-machine synchronization.

### Why didn't the example call `this.load("X")`?

Spring Cache in default proxy mode intercepts calls going through the proxy. When the same bean calls `this.load("X")`, the internal call normally bypasses cache advice; `@Cacheable(sync=true)` may have no effect. `CommandLineRunner` receives `ExpensiveService` as a Spring bean, so calls go through the proxy.

Do not use this example to assert that every provider behaves identically. Re-run tests against the actual deployed provider and configuration.

## 6. Does a shared Redis store guarantee only one loader cluster-wide?

**Not necessarily.** Shared Redis allows App A and App B to read/write **the same cache data**. Yet sharing storage does not automatically create a locking mechanism protecting the whole sequence:

~~~text
read cache -> if miss then run slow task -> put cache
~~~

Two processes can both read a miss **before** either writes, and then both compute. Even if only one Redis entry remains at the end, the DB/CPU hit count can still be two.

~~~text
App A                   Redis                    App B
  | GET R1 -------------->|<-------------- GET R1 |
  |<--- MISS ------------ | ------------ MISS --->|
  | compute R1            |            compute R1 |
  | SET R1 -------------->|<-------------- SET R1 |
~~~

The diagram illustrates a scenario without strong enough coordination. `@Cacheable(sync=true)` requests loading behavior from the provider, but **cluster-wide** effectiveness must be verified from the cache implementation, writer/loader path, and deployment setup. Do not infer it merely from configuring `RedisCacheManager`.

### Spring Data Redis: locking vs. non-locking writer

According to Spring Data Redis documentation, `RedisCacheManager` normally uses a **non-locking `RedisCacheWriter` by default**. That choice reduces latency/round-trips, though some operations may not be atomic across multiple Redis commands. Spring Data Redis also provides a **locking writer** that can use an explicit lock key to prevent overlap in certain operations.

One particularly important detail: the locking writer in documentation is described at the **cache level**, not per entry. That can cause wider waiting than a single key and add per-request overhead. Furthermore, API versions and providers differ in value-loader semantics; you should not claim enabling locking writer guarantees absolute single-flight for every method and version.

This is an **illustration of Redis configuration API**, not a standalone runnable program:

~~~java
// Inside a @Configuration class with RedisConnectionFactory and suitable imports.
@Bean
RedisCacheManager redisCacheManager(
        RedisConnectionFactory connectionFactory) {
    return RedisCacheManager
            .builder(RedisCacheWriter.lockingRedisCacheWriter(connectionFactory))
            .cacheDefaults(RedisCacheConfiguration.defaultCacheConfig())
            .build();
}
~~~

Before adopting this, check Spring Data Redis version compatibility, semantics of `RedisCache.get(key, Callable)` in that backend, cross-key contention, locking cost, expiry, failure recovery, and timeouts. Enabling locking on all caches can degrade throughput unnecessarily.

**Practical conclusion:** Redis can serve as **shared cache storage**, but it should only be called a **cross-JVM loader coordination** solution after verifying and testing the exact code path, writer configuration, and live topology.

## 7. Three strategies when running across multiple machines

### A. Accept one computation per replica

This is a reasonable choice when the computation is not overly expensive, the replica count is small, and exact cluster-wide coordination is unnecessary.

~~~text
Replica A: local single-flight for R1 -> 1 computation
Replica B: local single-flight for R1 -> 1 computation
Replica C: local single-flight for R1 -> 1 computation
~~~

Pros: simple, no distributed locks needed, fewer new failure modes. Cons: computation count can scale with the number of replicas and miss bursts. With shared Redis, a put by A can let later requests on B hit; however, **two concurrent missing requests** can still load together.

### B. Use a distributed coordination mechanism for the same key

When the task is very expensive or the DB cannot survive stampedes, you can design shared coordination:

~~~text
App A/B/C request R1
       |
       v
Shared cache GET R1
       |
    HIT? -- yes --> return
       |
       no
       v
Acquire coordination for "R1" in shared system
       |                         |
    Owner                      Not owner
       |                         |
  Recheck cache             Wait/poll with limits
       |                         |
  Compute once               Retry cache read
       |
  Put result
       |
  Release ownership safely
~~~

With distributed locks, naively calling `SETNX lock:R1` and then `DEL lock:R1` is **not enough**. You need at least:

1. A lock identifier with proper namespace, tenant, and semantic key.
2. A unique owner token for each lock acquisition.
3. TTL/lease so the lock does not stay stuck forever if a process dies.
4. Release checking **ownership** (executed atomically), never deleting a new owner's lock after an old lease expired.
5. Waiting with timeouts/backoff/jitter; no infinite polling or overloading Redis.
6. **Re-reading the cache after acquiring the lock**, since another process may have finished computing while you waited.
7. An explicit policy when the loader or cache backend fails: return error, fallback, stale value, or recompute.
8. Consider **fencing tokens/versions** when a lease can expire while the task is still running.

Specifically, a lock with TTL **does not guarantee only one computation**. If App A holds a 5-second lock but takes 10 seconds to compute, the lock can expire, App B becomes the new owner, and both compute. In that case, there must be a mechanism preventing the **old** result from overwriting fresh data, such as storage-enforced version checks or fencing.

The following is **pseudocode**, not standalone runnable Java:

~~~text
value = cache.get(key)
if value exists:
    return value

lease = coordinator.tryAcquire(lockKey(key), ownerToken, boundedLease)
if lease acquired:
    try:
        value = cache.get(key)       # recheck after acquiring lease
        if value exists:
            return value

        fresh = loadFromSource()
        writeWithVersionRules(key, fresh)
        return fresh
    finally:
        coordinator.releaseOnlyIfOwner(lockKey(key), ownerToken)
else:
    boundedWaitWithJitter()
    value = cache.get(key)
    if value exists:
        return value
    followExplicitFailureOrFallbackPolicy()
~~~

In practice, locks, cache, DB, and written outputs can live in separate systems; you must account for crashes/restarts, network partitions, lease expiry, timeouts, and write ordering. If you need **exactly-once execution of a side effect**, a distributed cache lock alone is usually insufficient; you need idempotency or transactional coordination at the business write layer.

### C. Reduce stampedes without strict distributed locks

Several proactive techniques flatten load peaks:

- **TTL jitter:** instead of every entry expiring at exactly 60 seconds, apply bounded random variance to keep many keys from expiring simultaneously.
- **Stale-while-revalidate:** return an older result within an allowed window and refresh in a controlled way; apply only if business logic tolerates staleness.
- **Refresh-ahead/prefetch:** refresh hot keys before expiration, with capacity limits.
- **Controlled warm-up:** pre-load only critical keys on deploy or scale-out, avoiding every replica warming a huge set at once.
- **Rate limits/bulkheads:** cap concurrent loaders to protect the DB when the cache fails or empties.
- **Separate TTLs by data class:** rare keys do not need complex strategies; ultra-hot keys may need dedicated refresh.
- **Task-layer deduplication:** deduplicate background work by ID if the loader is essentially a long-running job.

Every option has trade-offs. If data involves balances, access permissions, or transactional decisions requiring high consistency, do not casually serve stale values just to lower latency.

## 8. Comparing options by actual scope

| Option | Synchronizes threads in same JVM | Synchronizes across multiple JVMs | What must be verified |
| --- | --- | --- | --- |
| `synchronized` on bean instance | Yes for same instance; may over-lock | **No** | Bean instance count, lock scope |
| Local per-key lock/`computeIfAbsent` | Yes on same map/key | **No** | Cleanup, key equality, loader errors |
| `ConcurrentMapCacheManager` + `sync=true` | Yes per cache instance in the demo | **No** across independent managers | Correct bean/cache and proxy |
| Caffeine local cache with coordinated loader | Yes per cache instance and right API | **No** if each JVM has its own cache | Caffeine API/refresh semantics |
| Shared Redis without proper coordination | Shared values yet loaders can still duplicate | **Not guaranteed** | Redis writer, load callback, races |
| Redis locking writer | Implementation-dependent behavior | Can help coordinate some ops; **do not infer** per-key guarantee | Cache-level locking, version/provider |
| Properly designed distributed per-key coordinator | Yes | Can achieve single-flight under defined conditions | Lease, token, fencing, failure, version |
| TTL jitter / stale-while-revalidate | Reduces concurrent miss probability | Reduces need for cross-JVM coordination | Staleness bounds and refresh capacity |

No approach guarantees exactly-once automatically across all network failures, rollbacks, and retries. "One cached entry stored" is also completely different from "only one loader ran": two loaders can finish and one value can overwrite the other.

## 9. Rules for keys, cache names, and multi-tenant data

Whether synchronizing within one or many JVMs, calls should only coordinate if they target **the exact same business result**.

~~~text
Cache identity = backend/manager + cacheName + key
key = (tenantId, reportId, projectionVersion) when these affect output
~~~

For example, `R1` can exist in two different organizations:

~~~text
(acme, R1) -> Acme's report
(beta, R1) -> Beta's report
~~~

If you use `key="#p1"` with only the report ID in a shared cache, not only do you synchronize across the wrong boundary: one tenant can receive another tenant's data. Key by trusted scope, enforce authorization **on every request**, and ensure DB queries enforce tenant filtering. A cache is not a security boundary.

Adding random data like `requestId`/timestamp to the key makes every call have a distinct key; per-key synchronization becomes **meaningless**. Conversely, overly broad keys cause distinct outputs to share an entry. With distributed coordination, lock keys must also be normalized by cache identity to avoid mis-coordinating or missing locks.

Key data can appear in Redis, tracing, metrics, and logs: avoid putting tokens, passwords, or unnecessary sensitive data in keys. When moving record/object keys from in-memory to Redis, verify the serializer and how the provider prefixes cache names.

## 10. Loader synchronization does not mean data is always fresh

`sync=true` mainly helps coordinate **cache misses for the same key**. It does not automatically solve the following:

### Slow reader overwriting a newer writer

~~~text
T1: Reader A misses R1, starts computing origin data v1.
T2: Writer B updates origin to v2, puts cache v2.
T3: Reader A finishes and puts v1 into cache.
T4: Users may observe v1 even though origin is v2.
~~~

Depending on the implementation, read/put and load callbacks can be coordinated differently. Do not assume `sync=true` forces `@CachePut`, `@CacheEvict`, database transactions, and all other writers onto one cluster-wide lock or global order.

Solutions may require versioning, optimistic locking, pre-put version checks, after-commit invalidation, or record-versioned caches.

### Changed data or revoked permissions

On a cache hit, the `@Cacheable` method body may not execute. `sync=true` does not re-run authorization checks inside the method body. If results are access-controlled, check permissions at an entrypoint/facade that runs on **every request**, and align key/invalidation policies with tenant/user/permission changes.

### Exceptions, timeouts, and process crashes

If the loader throws an exception, normal caching does not store a successful value; other callers may have to recompute or receive errors. If a process dies while holding a distributed lease, the lock needs expiry or recovery. If a load callback is too slow, timeouts, circuit breakers, bulkheads, and fallbacks must be carefully designed.

A misplaced "cluster-wide lock" can stall waves of requests instead of protecting the system. Monitor tail latency, waiter counts, and lock hold times—not only the cache hit ratio.

## 11. Measuring and testing concurrency

To evaluate a design, identify **the right metrics to measure**:

| Metric | Meaning |
| --- | --- |
| `loaderInvocationCount` per key | How many times real work runs on cache misses |
| Cache hit/miss | Rate of ready results; does not reveal duplicate loaders on misses |
| `inflightLoads` | Number of loaders running concurrently |
| `waiterCount` and wait duration | How many requests are blocked by coordination |
| Loader error/timeout rate | Whether cache stampedes are pressuring downstream DB/APIs |
| Distributed lease expiry/reacquire | Whether old and new owners risk working simultaneously |
| Stale read/version mismatch | Whether the system serves old data after updates |
| p95/p99 latency | Whether locks create long wait queues and hurt tail latency |

### Test 1: Multiple threads in a single JVM

- Start with a clean cache.
- Have 8–100 threads concurrently call **one key** via the Spring proxy.
- Measure real method execution counts, returned values, and errors/timeouts.
- With `ConcurrentMapCacheManager` and `sync=true` as in the demo, expect one load for the same cached key. Do not treat this as multi-machine proof.

You can add a multi-key test to confirm independent keys are not blocked by an unintended global lock.

### Test 2: Two application instances

Deploy two separate JVM processes or two independent containers. Explicitly record whether they use **separate local caches** or **shared Redis**. Send concurrent requests for the same key across both processes, attach trace IDs, and count loaders at the origin (DB/API) via shared telemetry.

- If each process has a local cache, after cold start you can see at least one loader per process.
- If using shared Redis, check both compute counts **and** put counts, not just the final entry.
- If using distributed coordination, test contention, timeouts, owner crashes, lease expiration, flaky cache backends, and retries.
- Repeat tests when scaling up replicas and during mass cache loss.

You cannot prove a mechanism is "cluster-safe" using a single-JVM multi-threaded test, even with thousands of threads.

### Test 3: Mutating data concurrently with cache loading

While a loader is computing, update the DB and evict/put the same key. Record which version callers receive after the update. This test catches stale-data races specifically; it is distinct from stampede tests.

### Test 4: Provider failures

Simulate Redis timeouts, connection loss, or sudden cache misses, and observe `CacheErrorHandler`/loader/fallback behavior. Verify neither unbounded origin query storms nor deadlocks occur.

## 12. Common misconceptions

| Misconception | Reality |
| --- | --- |
| "`sync=true` guarantees cluster-wide single computation" | No; it is a hint depending on provider and coordination domain |
| "Nodes using the same cache name share a lock" | Identical names do not make Java cache/lock objects shared |
| "Shared Redis means loaders automatically wait on each other" | Shared storage is not enough to guarantee coalescing concurrent misses |
| "Java `synchronized` protects Kubernetes pods" | A Java monitor only applies to objects inside that JVM |
| "Using a `static Lock` locks across machines" | Static fields live per classloader/JVM, not across processes |
| "Enabling Redis locking writer definitely locks per key" | Documentation describes locking writer at cache level, with other trade-offs |
| "Having TTL eliminates stampedes" | TTL causes entries to expire; simultaneous expiry can worsen stampedes |
| "When a lock expires, the old owner definitely stops" | The old owner can keep running and write a stale value |
| "`sync=true` also blocks two concurrent updates" | It targets miss-time loading, not general transactions/locking |
| "One cache entry means only one loader ran" | Multiple loaders can overwrite the same entry |
| "Add `unless` to `sync=true` to avoid caching null" | The `@Cacheable` contract does not support this combination |
| "Passing one multi-threaded test proves production safety" | Requires multi-process testing on the real provider |

## 13. Self-check exercises

**Exercise 1.** A Spring Boot app runs on a single JVM using `ConcurrentMapCacheManager`; 20 requests concurrently call `@Cacheable(cacheNames="reports",sync=true)` with key `"R1"` on the same proxy. What expectation is reasonable?  
**Answer:** The in-memory manager can coordinate same-key loads within the same cache instance; when the loader succeeds and stores the entry, expect one computation for that miss burst and all other callers to receive the same result.

**Exercise 2.** The same app scales to 6 pods, each creating its own `ConcurrentMapCacheManager`. Is system-wide single loader for `"R1"` still guaranteed?  
**Answer:** No. Each pod has its own memory/cache; if all miss together, each pod can run its own loader, even though threads within each pod coordinate.

**Exercise 3.** Two pods share Redis. Are they guaranteed to run only one loader on concurrent GET misses?  
**Answer:** Not guaranteed. You must check the cache provider/writer semantics and coordination strategy; shared Redis storage does not inherently block two simultaneous computations.

**Exercise 4.** Why does a distributed lock need an owner token and atomic release?  
**Answer:** Owner A's lease can expire and B can acquire a new lock; A must not delete the lock now owned by B. Release must verify the token atomically.

**Exercise 5.** A holds a 5-second lock but takes 12 seconds to compute; B acquires the lock after 5 seconds. Can you claim only one loader runs?  
**Answer:** No. You need lease renewal/fencing/versioning or an acceptable recomputation policy. Lock TTL does not halt A's work.

**Exercise 6.** Why is `@Cacheable(sync=true, unless="#result == null")` unsuitable?  
**Answer:** `sync=true` does not support `unless` per Spring's contract. If you want both single-flight and result filtering, design another mechanism.

**Exercise 7.** A report at Acme and Beta both have ID `"R1"`. Can you use key `"R1"` alone so both tenants share the cache and distributed lock?  
**Answer:** No if results differ. Key by verified tenant/scope; never conflate two distinct datasets.

**Exercise 8.** When should you choose TTL jitter instead of distributed locks?  
**Answer:** When the primary goal is preventing many entries from expiring simultaneously, data tolerates eventual consistency, and occasional duplicate loader cost is acceptable; TTL jitter is simpler though it does not guarantee single-flight.

## 14. Architecture decision summary

For a quick decision sequence, proceed in order:

1. **Clarify the goal:** cutting duplicate loads on misses, protecting downstream systems, or preventing stale data on updates? These three goals are not identical.
2. **Identify real scope:** one JVM, multiple JVMs with local caches, or multiple JVMs sharing a cache?
3. **Verify the provider:** does `@Cacheable(sync=true)` support synchronized loading on `Cache.get(key,Callable)` and across which scope?
4. **Weigh the cost:** is one duplicate computation per replica dangerous? If not, local coordination plus TTL jitter may suffice.
5. **If cluster coordination is needed:** pick the right primitive and design owner tokens, leases, fencing/versions, timeouts, failure handling, and retries.
6. **Field-test:** measure cluster-wide loader counts, waiters/tail latency, stale versions, and test crashes/partitions/multi-instance rollouts.
7. **Do not conflate with authorization:** cache hits can skip the method; permission and scope checks must still execute properly on every request.

### Official References

- Spring Framework – **Synchronized Caching** and `@Cacheable(sync=true)`: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework – Javadoc `@Cacheable` (`sync` contract, `unless` constraints, single cache, and callbacks): https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Framework – Javadoc `Cache.get(Object, Callable)`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/Cache.html
- Spring Data Redis – **Redis Cache** (locking/non-locking writer, cache-level lock, TTL, prefix): https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html
- Spring Data Redis – Javadoc `RedisCacheWriter`: https://docs.spring.io/spring-data/redis/reference/4.0/api/java/org/springframework/data/redis/cache/RedisCacheWriter.html

**Takeaway:** Within a single JVM, `@Cacheable(sync=true)` with a supporting provider can coalesce same-key misses. Across multiple JVMs, local locks have no effect, and a shared cache does not automatically provide distributed single-flight. Cluster-wide coordination requires verifying provider capabilities or building distributed coordination with clear lease, failure, and version policies. Never extrapolate from a single-process multi-threaded test pass to a multi-machine guarantee.