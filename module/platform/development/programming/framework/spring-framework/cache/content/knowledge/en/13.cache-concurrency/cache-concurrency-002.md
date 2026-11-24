# @Cacheable(sync=true) and Provider Support Contracts in Spring Cache

## 1. The problem to solve: multiple threads missing the cache together

When a system handles concurrent requests, multiple requests may look up a key that does not yet exist in the cache. If the whole group reads the cache before the first result is stored, they may all query the database or call an expensive API. This phenomenon is commonly called a **cache stampede** or **thundering herd**.

Example of a standard service:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String sku) {
    return repository.load(sku);
}
```

If eight threads concurrently call `find("P1")` when key `P1` is absent, default `@Cacheable` alone **does not guarantee** that the real method runs only once. The cache still speeds up subsequent calls once the entry is present, but the initial load step may be duplicated.

To ask the cache provider to coordinate calls for the same key, Spring supports:

```java
@Cacheable(cacheNames = "products", key = "#p0", sync = true)
public Product find(String sku) {
    return repository.load(sku);
}
```

`sync = true` requests a synchronized loading mechanism: if the provider supports it, one caller can take responsibility for loading the missing key's value, while the other callers receive the value once loading finishes.

**Core principle:** `sync=true` is a **hint/contract passed down to the cache implementation**; the actual synchronization level, lock scope, and error behavior **depend on the provider**. Spring does not automatically turn every cache backend into a distributed lock across multiple servers.

This lesson focuses on how it works, the `Cache.get(key, Callable)` contract, the three annotation constraints, provider testing, a runnable Java 17 example, and common misconceptions.

## 2. Processing flow with `sync` disabled vs. enabled

### 2.1. Without synchronization: get, compute, then put

With `sync=false` (the default), the flow can be visualized as:

```text
Thread A                        Thread B
   |                               |
   +-- get("P1") -> MISS           +-- get("P1") -> MISS
   |                               |
   +-- load("P1")                   +-- load("P1")
   |                               |
   +-- put("P1", value)             +-- put("P1", value)
   |                               |
   +-- return value                 +-- return value
```

Both threads may return the right result, but they called the origin twice. When the origin is very expensive or rate-limited, duplicate loading increases latency and system load.

### 2.2. With synchronization enabled: per-key get-or-load

On the synchronized path, Spring can delegate to the `Cache` API for a get-or-load operation:

```java
// Pseudocode illustrating the mechanism, not Spring source code.
return cache.get(key, () -> invokeTargetMethod());
```

If the provider executes atomically for the same key:

```text
Caller A                  Caller B                  Caller C
   |                         |                         |
   +-- getOrLoad("P1")       +-- getOrLoad("P1")       +-- getOrLoad("P1")
          |                         |                         |
          +-- MISS, load origin    +-- wait                  +-- wait
          |                         |                         |
          +-- write value           |                         |
          |                         |                         |
          +-- return value          +-- receive value         +-- receive value
```

This is the **per-key single-flight** model of a supporting cache provider. It does not mean the entire method runs sequentially for every request: `P1` and `P2` are distinct keys so they can be loaded concurrently. Different cache names, different cache instances, or different JVMs may have separate synchronization scopes.

Key selection is critical. If the key includes a random request ID, every request becomes a distinct key, so `sync=true` can no longer coalesce them. If the key omits tenant, locale, or access permissions while the result depends on them, calls may be wrongly coalesced and return wrong data.

## 3. Contract between Spring Cache and the provider

### 3.1. Interface point: `Cache.get(Object, Callable<T>)`

Spring Cache exposes these APIs:

| API | Purpose | Relevance to synchronization |
| --- | --- | --- |
| `get(Object key)` | Look up a key's value/wrapper | Does not include loading mechanics |
| `get(Object key, Class<T> type)` | Retrieve value with expected type | Does not prevent two threads from missing together |
| `put(key, value)` | Write result into cache | Independent write operation |
| `get(key, Callable<T> loader)` | Get value; if missing, use callback to load value | Key API for synchronized caching |
| `retrieve(...)` | Retrieve via `CompletableFuture` | Used for async/reactive methods; requires separate verification |

Key Java signature:

```java
<T> T get(Object key, java.util.concurrent.Callable<T> valueLoader);
```

The contract requires the implementation to return the value if present or invoke `valueLoader` to compute/store the result when absent. The Javadoc recommends that, if feasible, loading **should be synchronized** so the callback is called only once under concurrent access for the same key.

That is the crucial difference between a **conditional interface recommendation** and an **implementation technical guarantee**. A provider might implement it using `computeIfAbsent`, local locks, remote backend locks, or another mechanism. Some implementations may not guarantee loader coalescing at all, so declaring `@Cacheable(sync=true)` alone is not enough to assert an execution count.

### 3.2. Contract questions to verify when choosing a provider

Ask specific questions:

1. Is `get(key, Callable)` actually implemented, and does it synchronize the loader for the same key?
2. Is the synchronization scope **one cache object**, one JVM, or the entire cluster?
3. For distinct keys, does the provider allow parallel loads or lock the entire region?
4. When the loader fails, is the callback invoked again on the next call? What error do other callers receive?
5. When a node dies mid-load, can another node take over or is there a risk of long waits?
6. When a cache entry's TTL expires or it is evicted mid-load, is there a risk of overwriting fresh data with stale data?
7. Does a backend supporting synchronous `get(key, Callable)` also support **asynchronous** `retrieve(key, supplier)` under the required contract?

For example, `ConcurrentMapCacheManager` in Spring core uses an in-JVM cache and is suitable for testing concurrent loading within **a single process**. That does not imply two application instances running on two servers share a lock. With Redis or a remote cache, check the exact implementation and adapter version; storing values in Redis does not by itself prove synchronized loading across all nodes.

## 4. Constraints of `@Cacheable(sync=true)`

According to the Spring Framework `@Cacheable` Javadoc, synchronized caching has **three constraints**. These are not optional style recommendations, but annotation configuration contracts.

| Constraint | What to avoid |
| --- | --- |
| `unless` is not supported | Do not use `unless="#result == null"` with `sync=true` |
| Only one cache per operation | Do not specify multiple cache names on a synchronized cacheable |
| No combining other cache operations | Do not pair `@CachePut`/`@CacheEvict`/another `@Cacheable` on the same synchronized method |

### 4.1. `unless` is not supported

**Invalid:**

```java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    sync = true,
    unless = "#result == null"
)
public Product find(String sku) {
    return repository.load(sku);
}
```

`unless` needs to inspect the result after the method runs to decide whether to store it. On the synchronized path, Spring hands the loading callback and combined cache operation off to the provider; it cannot arbitrarily inject `unless`'s post-execution veto.

When the product requires **not caching null** while also avoiding duplicate loads, consider a non-null value wrapper paired with a "not found" handling strategy, or separate the single-flight mechanism from annotation-based caching. Do not assume a backend that rejects null will silently skip storing it: some backends throw an exception.

### 4.2. Single cache only

**Invalid:**

```java
@Cacheable(
    cacheNames = {"productsLocal", "productsShared"},
    key = "#p0",
    sync = true
)
public Product find(String sku) {
    return repository.load(sku);
}
```

Even though regular `@Cacheable` allows multiple cache regions, synchronized loading supports only **one region** resolved for that cache operation. When using a custom `CacheResolver`, ensure the resolver returns exactly one `Cache` instance.

This does not mean the entire application can only have one `CacheManager`. Multiple managers can exist, as long as the synchronized operation resolves to a single final cache.

### 4.3. Do not combine other operations on the same method

**Invalid:**

```java
@Caching(
    cacheable = @Cacheable(cacheNames = "products", sync = true),
    evict = @CacheEvict(cacheNames = "productLists", allEntries = true)
)
public Product find(String sku) {
    return repository.load(sku);
}
```

Place state-mutating operations, `@CachePut`, or `@CacheEvict` on **separate methods**. Do not try to "both synchronized-load and evict" within the same method.

**Valid:**

```java
@Cacheable(cacheNames = "products", key = "#p0", sync = true)
public Product find(String sku) {
    return repository.load(sku);
}
```

Argument-based `condition` is a different option from `unless`. When `condition` evaluates to false, caching is skipped; the method still executes and is not single-flighted through the cache for that call.

```java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    condition = "#p0 != null",
    sync = true
)
public Product find(String sku) {
    return repository.load(sku);
}
```

This snippet only illustrates input filtering. It does not replace business validation, and the method must still handle `sku == null` properly.

## 5. Runnable example with Spring Framework 6.2 and Java 17

The example has 8 threads concurrently requesting one SKU when the cache is empty. They are started with a `CountDownLatch` so they begin together, and then results and actual load counts are compared.

**Goals:**

- Concurrent access for the same key `P1` loads the origin only once with `ConcurrentMapCacheManager` in a single JVM.
- Calling `P1` again is a hit and does not increment the counter.
- Calling `P2` has its own key and triggers a new load.
- Evicting `P1` and calling again triggers a fresh load.

**Directory structure:**

```text
sync-cache-demo/
├── pom.xml
└── src/main/java/SyncCacheDemo.java
```

**`pom.xml` file:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>sync-cache-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/SyncCacheDemo.java` file:**

```java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class SyncCacheDemo {

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products");
    }

    @Bean
    ProductService productService() {
        return new ProductService();
    }

    public static class ProductService {
        private final AtomicInteger loads = new AtomicInteger();

        @Cacheable(cacheNames = "products", key = "#p0", sync = true)
        public String find(String sku) {
            int loadId = loads.incrementAndGet();
            try {
                Thread.sleep(120);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("Interrupted during load", e);
            }
            return sku + "#load" + loadId;
        }

        @CacheEvict(cacheNames = "products", key = "#p0")
        public void evict(String sku) {
            // Spring caching interceptor evicts the entry after the method.
        }

        public int loads() {
            return loads.get();
        }
    }

    public static void main(String[] args) throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(SyncCacheDemo.class)) {
            ProductService service = context.getBean(ProductService.class);

            int callers = 8;
            ExecutorService pool = Executors.newFixedThreadPool(callers);
            CountDownLatch ready = new CountDownLatch(callers);
            CountDownLatch start = new CountDownLatch(1);

            try {
                List<Future<String>> futures = new ArrayList<>();

                for (int i = 0; i < callers; i++) {
                    Callable<String> task = () -> {
                        ready.countDown();
                        start.await();
                        return service.find("P1");
                    };
                    futures.add(pool.submit(task));
                }

                ready.await();
                start.countDown();

                Set<String> distinct = new HashSet<>();
                for (Future<String> f : futures) {
                    distinct.add(f.get());
                }

                System.out.println("distinct same-key results: "
                        + distinct.size());
                System.out.println("same-key value: "
                        + distinct.iterator().next());
                System.out.println("loads after 8 callers: "
                        + service.loads());

                System.out.println("repeat P1: " + service.find("P1"));
                System.out.println("loads after repeat: "
                        + service.loads());

                System.out.println("different P2: " + service.find("P2"));
                System.out.println("loads after P2: " + service.loads());

                service.evict("P1");
                System.out.println("P1 after evict: " + service.find("P1"));
                System.out.println("loads final: " + service.loads());
            } finally {
                start.countDown();
                pool.shutdownNow();
            }
        }
    }
}
```

**Run with Maven and JDK 17+:**

```bash
mvn -q compile exec:java -Dexec.mainClass=SyncCacheDemo
```

**Lines printed by the program** (excluding Maven/Spring logs if any):

```text
distinct same-key results: 1
same-key value: P1#load1
loads after 8 callers: 1
repeat P1: P1#load1
loads after repeat: 1
different P2: P2#load2
loads after P2: 2
P1 after evict: P1#load3
loads final: 3
```

### 5.1. Why can we trust the results in this example?

`ready` ensures all eight tasks are ready before opening the `start` latch. `Thread.sleep(120)` stretches the load duration to make overlapping access easy to observe. The returned values and `AtomicInteger` show how many times the origin method actually ran.

`ProductService` is a Spring bean, `@EnableCaching` is enabled, and `main` calls through the bean retrieved from the context—avoiding the **self-invocation** pitfall in proxy mode. `ConcurrentMapCacheManager` creates a local `products` region. The `ConcurrentMapCache` implementation supports per-key synchronized loading within the example's JVM.

Because the first loaded value is `"P1#load1"`, all `Future` instances receive the same result; the `distinct` set has size one. Calling `P1` again is a hit so the load count stays at 1; `P2` is a new key so the counter increments to 2. `evict("P1")` removes the right entry in a separate method, so the next load increments to 3.

Limitation: this result does **not** prove multi-JVM synchronization capability. Systems sharing a Redis backend can still perform multiple concurrent loads across instances if the adapter lacks distributed locking.

## 6. Cache provider support scope

Spring Framework describes `sync` as an optional provider-dependent feature; Spring's core `CacheManager` implementations are documented as supporting it. Do not equate "the provider exposes the method" with "the provider performs single-flight across all nodes."

| Implementation group | What can be inferred | What must be verified |
| --- | --- | --- |
| `ConcurrentMapCacheManager` | Supports synchronized load in local JVM cache | No cluster locking; lifecycle is not shared across instances |
| `CaffeineCacheManager` | Provider can manage concurrent loading via its own mechanism | Sync mode contract, expiry/refresh, async mode configuration |
| Redis/remote cache | Data can be shared over the network | Does `get(key, Callable)` lock distributedly or only locally? |
| Custom `Cache` adapter | Can implement the API however the author wrote it | Must read the implementation and stress-test |
| `NoOpCache` | Retains no entries across calls | Do not expect long-term load reduction from caching |

**Design rule:** before enabling `sync=true` in production, verify the provider's `Cache.get(key, Callable)` API and test against the exact build, configuration, backend, and node count you run. If the provider throws an exception due to lack of support or does not lock the loader, address it with proper configuration/provider choice; Spring does not create a global mutex on its own.

In some implementations, per-key synchronization may widen into a region-wide lock, forcing unrelated keys to wait on each other. Therefore, test not only "one key across many threads," but also "many keys concurrently" to measure throughput.

## 7. Problems that `sync=true` does not solve

### 7.1. Load–update races and stale data

`sync=true` coordinates loaders on cache misses, but it does not automatically synchronize database writes/`@CacheEvict`. Example race:

```text
T1: miss -> start loading old version of Product P1
T2: update P1 to new version, evict P1
T1: finish loading and put old value into cache
T3: hit -> receive stale data
```

This is an update/invalidation ordering issue, not merely duplicate loading. It may require versioning, after-commit invalidation, transaction coordination, or a cache strategy with suitable consistency guarantees.

### 7.2. Not a lock on the entire service

`sync=true` does not turn other methods on the service into synchronized methods, does not create a transaction spanning cache and DB, does not automatically serialize `@CachePut`/`@CacheEvict`, does not guarantee fairness, and does not act as a multi-node distributed lock.

### 7.3. Cache hits bypass the method body

On a cache hit, `@Cacheable` skips the method body. If the method has mandatory side effects such as publishing events, billing, or per-request auditing, those may not happen on a cache hit. Do not place essential side effects inside a cacheable method; `sync=true` does not change this rule.

### 7.4. Keys must be stable and distinguish data properly

Do not put random per-request values like trace IDs into the key if they do not affect the result: every request will become its own key. Conversely, if price depends on SKU + currency + tenant, choosing a key with only SKU is wrong and risks returning another tenant's price. Ensure the cache key matches business semantics before optimizing concurrency.

## 8. Null, Optional, exceptions, and fault tolerance

With `@Cacheable(sync=true)`, you cannot use `unless = "#result == null"` to prevent storing null. Behavior when the loader returns null depends on the provider:

- Providers allowing cached nulls may store the null state so subsequent calls do not hit the origin.
- Providers disallowing nulls may throw an error in the callback path.
- `Optional.empty()` is handled by Spring according to its supported wrapper unwrapping contract; test the actual provider and return type.
- If business logic must not cache "not found," drop `sync=true` and use `unless`, or design a value wrapper/negative caching strategy with explicit TTL and invalidation.

When a loader throws an exception, the `Cache.get(key, Callable)` API may wrap the cause in `Cache.ValueRetrievalException`. Test how exceptions propagate through the interceptor, error handlers, and provider. When the cache backend fails, `sync=true`'s combined get-or-load path differs from `sync=false`'s get-then-put path; some `CacheErrorHandler` policies may not provide equivalent fallback behavior.

`sync=true` also does not replace retries with backoff, timeouts, circuit breakers, bulkheads, or database load limits. When the origin is down, retry waves from many callers can trigger stampedes right after a failed load.

## 9. CompletableFuture and reactive types

Spring Framework 6.1+ integrates cache annotations with `CompletableFuture` and several reactive return types. Illustrative signature:

```java
@Cacheable(cacheNames = "productFutures", key = "#p0", sync = true)
public java.util.concurrent.CompletableFuture<Product> findAsync(String sku) {
    return java.util.concurrent.CompletableFuture.supplyAsync(
            () -> repository.load(sku));
}
```

This is an illustrative snippet only, not part of the standalone `SyncCacheDemo.java` in section 5.

For async synchronized caching, the provider must support `CompletableFuture`-style retrieval, not just synchronous `get(key, Callable)`. Spring documentation notes that `ConcurrentMapCacheManager` provides async adaptation; `CaffeineCacheManager` supports async cache mode when configured with `setAsyncCacheMode(true)`. For Reactor `Mono`/`Flux`, the cache abstraction collects the corresponding outcomes rather than acting as a dedicated backpressure/stream orchestration mechanism.

When using reactive types or futures, verify whether the provider can fulfill `retrieve(key, supplier)` appropriately, and test concurrency with that exact return type.

## 10. Testing the concurrency contract in practice

| Scenario | Expected metric/behavior to measure |
| --- | --- |
| 8–20 threads on the same missing key | Number of loader executions, number of distinct results |
| Same key after loading completes | Cache hit, loader count does not increase |
| Two different keys | Can load independently; do not share values |
| Evict then call again | Loader runs again |
| Cache entry TTL expires | How many loaders run after expiry? |
| Loader throws an exception | Which error do callers receive? Does the lock get stuck? |
| Provider failure/network loss | Does it fail fast, retry, or fall back? |
| Multiple JVMs on the same key | Is there true cluster-wide single-flight? |
| Loader runs concurrently with DB update | Does a stale value overwrite the new result? |
| Null/`Optional.empty()` | Is null cached, rejected, or does it error? |
| Bypassing Spring proxy | Method runs repeatedly; is the annotation actually applied? |

Measure **origin invocation counts**, not just returned values. If all 20 threads return the string `"P1"`, all 20 might still have loaded it. Tests of synchronization effectiveness must include counters, logs, or metrics at the repository/API layer.

Monitor waiting requests, cache hit/miss latency, loader latency, timeouts, provider errors, evict/expiry rates, and peak traffic. Do not use sensitive raw keys as metric labels due to data exposure risks and high cardinality.

### Acceptance checklist when switching providers

1. Identify the actual manager and cache instance resolved by the operation.
2. Read the documentation/implementation of `get(key, Callable)`, not just the cache provider's name.
3. Test in a single JVM with multiple threads on the same key and on distinct keys.
4. For clustered deployments, run the same test across at least two instances.
5. Test null values, origin failures, backend failures, TTL/eviction, and load–update races.
6. Define the fallback path and timeout behavior.
7. Re-run tests after upgrading the provider version or changing async/sync configuration.

## 11. Common mistakes

1. **Assuming `sync=true` always locks cluster-wide.** No such guarantee exists in the annotation contract.
2. **Ignoring the provider API.** If `get(key, Callable)` does not actually synchronize, the annotation will not produce the expected single-flight.
3. **Combining `unless`.** `@Cacheable(sync=true, unless="...")` is not supported.
4. **Passing multiple cache names to a synchronized operation.** Violates the single-cache constraint.
5. **Combining `@CachePut` or `@CacheEvict` on the same method.** Incompatible with synchronized cacheable.
6. **Keying by request ID.** Requests querying the same data cannot be coalesced.
7. **Omitting tenant or authorization factors from the key.** Risks leaking or mixing data across callers.
8. **Testing via self-invocation.** Calling `this.find(...)` within the same bean can bypass the Spring proxy and caching mechanism.
9. **Seeing identical outputs and concluding only one loader ran.** Identical results do not reveal how many times the origin was called.
10. **Believing sync guarantees fresh data on updates.** Races between loading and updating still need to be solved.
11. **Having no timeouts or error policy.** A slow loader can stall many waiting callers.
12. **Assuming sync method results imply async support.** The two retrieval paths require separate verification.
13. **Thinking sync makes the first load faster.** The main benefit is cutting duplicate load, not speeding up a single loader execution.
14. **Failing to check caches per environment.** A provider may use local locks in dev while behaving differently across multiple nodes.

## 12. Application summary

Concise declaration:

```java
@Cacheable(cacheNames = "products", key = "#p0", sync = true)
public Product find(String sku) {
    return repository.load(sku);
}
```

Three questions to answer before production use:

1. Does the key accurately represent the result so requests for identical data coalesce, while different tenants/filters/permissions are never mixed?
2. Does the provider genuinely guarantee synchronized loading via `Cache.get(key, Callable)` at the required scope—single JVM or cluster-wide?
3. Have you tested the `unless`/single-cache/no-combined-operations limits, along with error handling, nulls, invalidation, and concurrent loads during updates?

**Conclusion:** `sync=true` can help mitigate per-key cache stampedes **when supported by the provider**. It is not a distributed mutex, does not replace data consistency, and does not automatically solve errors or read-write races.

## Official Documentation

- Spring Framework 6.2 — Synchronized Caching: https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html
- Spring Framework 6.2 — `@Cacheable` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Framework 6.2 — `Cache.get(key, Callable)` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/cache/Cache.html
- Spring Framework 6.2 — `ConcurrentMapCache` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCache.html
- Spring Framework — Async/Reactive Cache Annotations: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
