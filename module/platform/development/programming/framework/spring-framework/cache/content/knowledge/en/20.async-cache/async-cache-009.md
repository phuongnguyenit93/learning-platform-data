# Limitations of Multiple `cacheNames` and `sync` Mode with Asynchronous Retrieval in Spring Cache

## 1. Why Does Async Caching Change How We Think About Multiple Caches?

When learning Spring Cache, we often write a concise annotation:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String sku) {
    return repository.load(sku);
}
```

One `cacheName` specifies **one cache region**. With regular `@Cacheable`, Spring checks the cache region before running the real method. If the key is present, the value is returned; if absent, the method executes and the result is put into the cache per the provider's contract.

However, two harder questions emerge in systems using `CompletableFuture`, `Mono`, or `Flux`:

1. What happens if `@Cacheable` declares **multiple cache names**, yet a cache miss is only known **after a future completes**?
2. Can `sync=true` be enabled to coalesce concurrent requests for the same key **while using multiple cache names**?

Core answers:

- **Multiple cache names** is a valid configuration in certain ordinary caching paths, yet **does not guarantee** Spring will probe every cache when asynchronous retrieval has a **late-determined cache miss**.
- **`@Cacheable(sync=true)` supports only a single cache** for that operation. You cannot use `sync=true` to synchronize loading across multiple cache regions in the same annotation.
- Async and synchronized loading mechanisms only work properly when **the cache provider/adapter supports the required API**; merely returning `CompletableFuture` from a method does not guarantee single-flight across all nodes.

This lesson explains these limitations in Spring Framework 6.1+ (using 6.2.9 in the example), along with execution flow models, valid/invalid configurations, a Java 17 demo, and a testing checklist.

## 2. What Do Multiple `cacheNames` Regions Mean on the Synchronous Path?

An annotation can declare multiple cache names:

```java
@Cacheable(
    cacheNames = {"productsFast", "productsShared"},
    key = "#p0"
)
public Product find(String sku) {
    return repository.load(sku);
}
```

On the ordinary **synchronous retrieval** path, the general meaning is that Spring inspects the resolved cache regions. If one region holds a value, that value can be used instead of running the method. For caches lacking the entry, Spring can also populate the result when the operation completes. Detailed behavior depends on `CacheManager`, `CacheResolver`, and the provider.

Expected example with two regions answering cache lookups immediately:

```text
productsFast          productsShared          repository
     |                       |                      |
     +-- get(P1) -> miss     |                      |
     |                       +-- get(P1) -> hit      |
     |                       |                      |
     +-- may receive value / update missing region  |
     |                       |                      |
     +-- return value ------ +                      |
                                                 (not called)
```

This easily leads to the expectation that a multi-region annotation automatically acts as an **L1 → L2 fallback** mechanism. However, that is not a universal contract for a multi-tier caching system.

Distinguish clearly:

- **`cacheNames` list**: multiple regions resolved for **one caching operation**.
- **`CacheResolver`**: decides which one or more Spring `Cache` objects to return based on method and parameters.
- **`CompositeCacheManager`**: picks one manager able to supply the requested **cache name**; does not automatically perform `get(key)` on L1 and fall back to `get(key)` on L2.
- **True multi-tier cache**: an implementation with hit/miss logic, lower-tier loading, backfilling, eviction, and cross-tier error handling.

Therefore, even on the synchronous path, using multiple `cacheNames` does not replace designing L1/L2 consistency, especially when one tier may hold a stale value.

## 3. Late-Determined Cache Miss: The Most Important Async Limitation

### 3.1. Cache Miss Known Immediately or Known Later

Suppose Spring invokes the asynchronous retrieval API:

```java
java.util.concurrent.CompletableFuture<?> result =
        cache.retrieve("P1");
```

This snippet is an **illustrative fragment**, assuming variable `cache` has type `org.springframework.cache.Cache` and the provider supports `retrieve`.

Two kinds of misses must be distinguished:

- **Early/immediate miss**: the adapter knows immediately the key does not exist and can return `null` from the `retrieve(key)` call itself.
- **Late-determined miss**: the adapter returns a `CompletableFuture` first; only when the future completes does Spring know whether there is a value or a cache miss.

A remote provider involving a network round trip, such as certain `RedisCache` configurations, may return a future because the lookup result arrives later. At that point, deciding to "move on to the next cache" is no longer as simple as calling several `get` calls sequentially on the same synchronous stack.

### 3.2. When Multiple Cache Names Are Not All Traversed

Consider an illustrative annotation:

```java
@Cacheable(
    cacheNames = {"productsRemote", "productsBackup"},
    key = "#p0"
)
public CompletableFuture<Product> findAsync(String sku) {
    return CompletableFuture.supplyAsync(
            () -> repository.load(sku));
}
```

This is **not** a standalone program; it assumes `Product` and `repository` exist. This configuration is not necessarily rejected at startup, yet **is not guaranteed** to provide fallback semantics across both regions when the first cache returns a late miss.

A notable scenario:

```text
T0  Spring starts looking up key P1 in productsRemote
T1  Provider returns CompletableFuture (hit or miss unknown yet)
T2  Future completes: MISS
T3  Async handling path may proceed to real load,
    NOT necessarily checking productsBackup next
T4  repository.load(P1) runs, even though productsBackup may hold P1
```

Key takeaway: **a late miss on an earlier cache can cause subsequent cache names not to be consulted**. The Spring Cache documentation explicitly warns that async/reactive access does not necessarily support checking across every declared cache; when late-determined misses are involved, use **a single cache name** per operation.

This is a lookup-contract limitation, not necessarily a Redis bug, nor do all providers behave identically. Local providers may determine misses early; remote providers may require a future. Whenever swapping providers or versions, re-test the execution path.

### 3.3. What Not to Conclude from a Single Test

If you test with a local `ConcurrentMapCache` and observe `productsBackup` being queried, you cannot deduce that async Redis will also check the second region. If you test when `productsRemote` already has a cache hit, you also have not proven the system handles a **late miss** properly.

To test this limitation, construct the exact scenario: the first cache lacks the key and completes its lookup **asynchronously**, while the second cache already holds the value. Measure lookup counts per region and loader execution counts rather than merely comparing the final result.

## 4. `sync=true`: Synchronized Loading and Three Mandatory Restrictions

### 4.1. What Does `sync=true` Actually Request?

`@Cacheable(sync=true)` asks Spring to use a **synchronized cache loading** mechanism if the implementation supports it. The purpose is to reduce multiple callers missing the same key and all executing an expensive data source concurrently (cache stampede).

```java
@Cacheable(cacheNames = "products", key = "#p0", sync = true)
public CompletableFuture<Product> findAsync(String sku) {
    return CompletableFuture.supplyAsync(
            () -> repository.load(sku));
}
```

If the provider supports an atomic get-or-load mechanism per key, multiple callers for `P1` can receive futures corresponding to the same load. Executing the source only once is expected within **the scope guaranteed by the provider**, typically one cache instance/JVM for local caches.

**There is no cluster-wide distributed lock promise merely from setting `sync=true`.** Two application instances with separate caches can still both call the repository.

### 4.2. Three Restrictions of `@Cacheable(sync=true)`

Per Spring Framework's `@Cacheable` contract:

| Restriction | Consequence |
| --- | --- |
| Does not support `unless` | Cannot combine synchronized caching with a veto condition after the method returns a result |
| Only one cache resolved for the operation | Cannot declare multiple `cacheNames` when using `sync=true` |
| Cannot combine with other caching operations on the same method | Cannot pair `@CachePut`, `@CacheEvict`, or another `@Cacheable` on a synchronized method |

Three **invalid** examples (solely for recognizing errors; do not put into runnable demo code):

**Invalid 1 — `sync=true` with multiple regions:**

```java
@Cacheable(
    cacheNames = {"productsFast", "productsShared"},
    key = "#p0",
    sync = true
)
public CompletableFuture<Product> findAsync(String id) {
    return serviceLoad(id);
}
```

Spring cannot implement synchronized loading across a set of multiple caches for one `sync=true` operation under this contract.

**Invalid 2 — `sync=true` with `unless`:**

```java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    sync = true,
    unless = "#result == null"
)
public CompletableFuture<Product> findAsync(String id) {
    return serviceLoad(id);
}
```

`unless` needs to observe the result after method execution and decide not to write to the cache. The synchronized loading path delegates lookup-and-load coordination to the provider, so Spring does not support this veto form.

**Invalid 3 — combining another operation on a synchronized method:**

```java
@Caching(
    cacheable = @Cacheable(cacheNames = "products", sync = true),
    evict = @CacheEvict(cacheNames = "lists", allEntries = true)
)
public CompletableFuture<Product> findAsync(String id) {
    return serviceLoad(id);
}
```

If you need to evict or update another cache, place that operation on a separate method or handle it in the write workflow. `@Caching` does not turn an unsupported combination into a valid one either.

### 4.3. `condition` Differs from `unless`

`@Cacheable`'s `condition` is evaluated **before** invoking the method and can filter by inputs:

```java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    condition = "#p0 != null",
    sync = true
)
public CompletableFuture<Product> findAsync(String id) {
    return serviceLoad(id);
}
```

This is an illustrative fragment inside a hypothetical service. When `condition` is false, caching is skipped; the method can run on every call so `sync=true` no longer coalesces those calls. `condition` cannot inspect `#result` because the result does not exist at evaluation time.

## 5. Matrix of Allowed Combinations and Practical Limits

| Configuration | Valid Configuration? | Points to Note |
| --- | --- | --- |
| One `cacheName`, `sync=false`, synchronous method | Yes | Normal lookup and put; concurrent misses may invoke loader multiple times |
| Multiple `cacheNames`, `sync=false`, synchronous method | Yes | Can inspect multiple caches when lookups return immediately; cross-region consistency still depends on design |
| One `cacheName`, `sync=false`, `CompletableFuture<T>` | Yes with Spring 6.1+ and suitable provider | Future completion is adapted; async retrieve may miss late |
| Multiple `cacheNames`, `sync=false`, `CompletableFuture<T>` | Declarable, **full fallback not guaranteed** | Late-determined miss may prevent consulting later caches |
| One `cacheName`, `sync=true`, synchronous method | Yes if provider supports it | Synchronized loading is delegated to provider |
| One `cacheName`, `sync=true`, `CompletableFuture<T>` | Yes when provider supports async loading | Must test `retrieve(key, supplier)`/actual single-flight |
| Multiple `cacheNames`, `sync=true` | **Unsupported** | Violates `@Cacheable(sync=true)` single-cache restriction |
| One cache, `sync=true` with `unless` | **Unsupported** | Post-load veto is outside the synchronized path |
| One cache, `sync=true` combined with `@CachePut`/`@CacheEvict` | **Unsupported** | Split operations onto separate methods |

Thus, **removing `sync=true` does not automatically fix all multi-`cacheNames` issues**; multi-region configurations can still encounter late misses when async. Conversely, **enabling `sync=true` does not turn multiple regions into a single locked store**.

## 6. Spring `Cache.retrieve` and Async Contracts Providers Must Satisfy

Spring Framework 6.1 adds asynchronous retrieval methods to `org.springframework.cache.Cache`:

```java
CompletableFuture<?> retrieve(Object key);

<T> CompletableFuture<T> retrieve(
        Object key,
        java.util.function.Supplier<CompletableFuture<T>> valueLoader);
```

These are **API signatures** for explanation, not a standalone program.

### 6.1. `retrieve(key)` — Pure Lookup

`retrieve(key)` can report a miss immediately by returning `null` if the provider knows early the key is absent. Or it can return a `CompletableFuture` and report hit/miss when the future completes.

When needing to represent **cached null**, an adapter can use `Cache.ValueWrapper` instead of confusing it with "no entry"; unwrapping conventions must follow the Javadoc/provider. Do not treat "null wrapper", "future completing with null", and "cached null" as the same case.

```text
retrieve(P1)
   |
   +-- immediate null -----------------> early cache miss
   |
   +-- CompletableFuture<?> -----------> result arrives later
            |
            +-- value -----------------> hit
            +-- null ------------------> late miss
            +-- ValueWrapper(null) ----> cached-null (if supported)
```

### 6.2. `retrieve(key, valueLoader)` — Get or Load

The combined retrieve/load path takes a callback that produces a `CompletableFuture<T>` when the key is missing. For `@Cacheable(sync=true)` with asynchronous values, Spring relies on the cache provider implementing this combined contract accordingly. Synchronized load/single-flight expectations must come from the implementation, not be inferred from the API name alone.

Illustrative fragment:

```java
CompletableFuture<Product> product =
    cache.retrieve("P1", () -> CompletableFuture.supplyAsync(
        () -> repository.load("P1")
    ));
```

This is a direct API call when suitable `cache` and `repository` variables exist. **Do not** place this entire callback inside a `@Cacheable`-annotated method calling back into the same cache, as it can cause loops or double caching.

Some providers/adapters only support synchronous retrieval or do not support the `retrieve` path; they may throw `UnsupportedOperationException`. Setting `@Cacheable(sync=true)` does not substitute for choosing a supporting provider and testing your specific version.

### 6.3. What Is the Cached Value When a Method Returns a Future?

With Spring Framework 6.1+ async adaptation, the idea is to cache **the result value after completion**, rather than treating the pending `CompletableFuture` object itself as business data for other callers to read and cast. The adapter/manager is responsible for converting between the Spring contract and native cache.

Therefore, avoid thinking `CompletableFuture<Product>` and `Product` are two types that can arbitrarily share a region. When multiple methods share a cache, they must share the same key/value contract and unwrapping behavior.

## 7. Runnable Example: Java 17 + Spring 6.2.9 + Async Caffeine

The example uses a single `products` region and `sync=true`. Eight concurrent callers request an absent key; afterward the program verifies hits, another key, and eviction.

Uses **`CaffeineCacheManager#setAsyncCacheMode(true)`** so Spring gets a native async cache supporting `retrieve`. This is plain Spring Framework configuration; no Spring Boot required.

### 7.1. Directory Structure

```text
async-sync-cache-demo/
├── pom.xml
└── src/main/java/AsyncSyncCacheDemo.java
```

### 7.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>async-sync-cache-demo</artifactId>
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
        <dependency>
            <groupId>com.github.ben-manes.caffeine</groupId>
            <artifactId>caffeine</artifactId>
            <version>3.1.8</version>
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

### 7.3. `src/main/java/AsyncSyncCacheDemo.java`

```java
import java.time.Duration;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class AsyncSyncCacheDemo {

    @Bean
    CaffeineCacheManager cacheManager() {
        CaffeineCacheManager manager =
                new CaffeineCacheManager("products");

        manager.setAllowNullValues(false);
        manager.setCaffeine(Caffeine.newBuilder()
                .maximumSize(500)
                .expireAfterWrite(Duration.ofMinutes(5)));
        manager.setAsyncCacheMode(true);
        return manager;
    }

    @Bean
    ProductService productService() {
        return new ProductService();
    }

    public static class ProductService {
        private final AtomicInteger loads = new AtomicInteger();

        @Cacheable(cacheNames = "products", key = "#p0", sync = true)
        public CompletableFuture<String> findAsync(String sku) {
            return CompletableFuture.supplyAsync(() -> {
                int loadId = loads.incrementAndGet();

                try {
                    Thread.sleep(150);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(
                            "Interrupted during cache load", ex);
                }
                return sku + "#load" + loadId;
            });
        }

        @CacheEvict(cacheNames = "products", key = "#p0")
        public void evict(String sku) {
            // Spring interceptor performs eviction.
        }

        public int loads() {
            return loads.get();
        }
    }

    public static void main(String[] args) throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(
                        AsyncSyncCacheDemo.class)) {

            ProductService service =
                    context.getBean(ProductService.class);

            int callers = 8;
            ExecutorService executor =
                    Executors.newFixedThreadPool(callers);
            CountDownLatch ready = new CountDownLatch(callers);
            CountDownLatch start = new CountDownLatch(1);

            try {
                List<Future<CompletableFuture<String>>> submitted =
                        new ArrayList<>();

                for (int i = 0; i < callers; i++) {
                    submitted.add(executor.submit(() -> {
                        ready.countDown();
                        start.await();
                        return service.findAsync("P1");
                    }));
                }

                ready.await();
                start.countDown();

                List<CompletableFuture<String>> stages =
                        new ArrayList<>();
                for (Future<CompletableFuture<String>> f : submitted) {
                    stages.add(f.get());
                }

                CompletableFuture.allOf(
                        stages.toArray(new CompletableFuture[0]))
                        .join();

                Set<String> distinctValues = new HashSet<>();
                for (CompletableFuture<String> f : stages) {
                    distinctValues.add(f.join());
                }

                System.out.println("distinct values: "
                        + distinctValues.size());
                System.out.println("value: "
                        + distinctValues.iterator().next());
                System.out.println("loads after 8 callers: "
                        + service.loads());

                System.out.println("P1 repeat: "
                        + service.findAsync("P1").join());
                System.out.println("loads after P1 repeat: "
                        + service.loads());

                System.out.println("P2 first: "
                        + service.findAsync("P2").join());
                System.out.println("loads after P2: "
                        + service.loads());

                service.evict("P1");
                System.out.println("P1 after evict: "
                        + service.findAsync("P1").join());
                System.out.println("loads final: "
                        + service.loads());
            } finally {
                start.countDown();
                executor.shutdownNow();
            }
        }
    }
}
```

### 7.4. Run with Maven

In the directory containing `pom.xml`, using JDK 17+:

```bash
mvn -q compile exec:java -Dexec.mainClass=AsyncSyncCacheDemo
```

**Expected stdout lines from the program itself** with the provider configuration in the example (excluding Maven/Spring logs if any):

```text
distinct values: 1
value: P1#load1
loads after 8 callers: 1
P1 repeat: P1#load1
loads after P1 repeat: 1
P2 first: P2#load2
loads after P2: 2
P1 after evict: P1#load3
loads final: 3
```

### 7.5. Why Does This Example Verify Exactly What Needs to Be Learned?

- `@EnableCaching` activates caching advice; the service is a Spring bean retrieved from the context, **not** calling `this.findAsync(...)` inside the same bean.
- `CaffeineCacheManager("products")` in static mode creates a single cache region.
- `setAsyncCacheMode(true)` allows the adapter to use async caches, while `setAllowNullValues(false)` avoids confusing null representations on the async path.
- `CountDownLatch` makes eight tasks start together. `Thread.sleep(150)` keeps the source load long enough to observe competing callers.
- `AtomicInteger` counts **actual loader executions**, rather than just counting returned results. `distinctValues` has one element because the same key receives the same result.
- `P2` is a different key and must be loaded separately. `@CacheEvict` sits on **another method**, without violating the restriction against combining operations with `@Cacheable(sync=true)`.
- The example only illustrates **one JVM and one specific provider**; it does not prove single-flight across multiple processes or a Redis cluster.

If you run on another provider and the load count exceeds one, inspect the exact `Cache.retrieve(key, supplier)` implementation, how cache instances are created, and how requests partition keys; do not rely solely on the annotation to draw conclusions.

## 8. `CompletableFuture`, `Mono`, and `Flux`: Asynchronous Is Not Streaming

### 8.1. `CompletableFuture<T>`

Spring Framework 6.1+ can adapt the cache abstraction to methods returning `CompletableFuture<T>`: the cache learns the result after the future completes. When considering multiple `cacheNames`, examine **the provider's lookup mechanism**, not just the service's return type.

Calling `findAsync("P1")` can return a future very quickly while the source query is still running. If the cache lookup completes late, a plan to fall back to another cache may not execute as expected.

### 8.2. Reactor `Mono<T>`

When Reactor is on the classpath, Spring 6.1+ also supports methods returning `Mono<T>` by adapting via futures. `Mono` typically represents at most one value; test empty completion, null policy, errors, and the proper cache adapter.

Illustrative fragment (not part of the standalone program in Section 7):

```java
@Cacheable(cacheNames = "products", key = "#p0")
public reactor.core.publisher.Mono<Product> findReactive(String id) {
    return repository.findReactive(id);
}
```

Do not infer merely because code is reactive that Spring will check all `cacheNames` or automatically provide a distributed lock.

### 8.3. Reactor `Flux<T>`

For a finite `Flux<T>`, Spring's cache abstraction can **collect all elements into a `List`** to store the result and then reconstruct the publisher on subsequent calls. This is completely different from caching individual events in a stream.

Therefore, do not use `@Cacheable` this way for **infinite** or overly large event streams: memory and latency can spike sharply. Also, when a publisher fails or is canceled midway, test adapter semantics rather than asserting intermediate elements were saved.

### 8.4. Do Not Equate `@Async` with Async Caching

`@Async` is a mechanism for executing a method on an executor. `@Cacheable` is a mechanism for storing/retrieving results. Combining both requires checking proxy/advisor ordering and return types; a method using `@Async` **does not automatically** guarantee `Cache.retrieve` is supported by the provider.

Because the goal here only requires `CompletableFuture`, the example in Section 7 uses `CompletableFuture.supplyAsync` and omits `@Async` to avoid layering two abstractions.

## 9. Provider Capabilities Determine Real-World Outcomes

| Provider/manager | Characteristics to Verify |
| --- | --- |
| `ConcurrentMapCacheManager` | Local JVM; Spring supports adaptive retrieval mechanisms, yet does not share caches across processes |
| `CaffeineCacheManager` | Local JVM; use `setAsyncCacheMode(true)` for native Caffeine `AsyncCache` and `retrieve` overloads |
| `RedisCacheManager` | Remote/network; cache misses may be determined late; must check async retrieval support and locking semantics of **the adapter version** |
| JCache or custom `Cache` adapter | Does not include full `retrieve` by default; read code/Javadoc and run functional tests |
| Custom multi-tier/cache decorator | Must clearly define tier order, backfilling, stale values, null, exceptions, TTL, and concurrency |

Not every `CacheManager` has the same support for `retrieve`, `sync=true`, and async. Even when the API exists, synchronized loading is an **implementation-dependent contract**. You need to know whether single-flight is scoped to one `Cache` object, one JVM, one client, or the whole cluster.

For instance, using a Redis region as a remote cache does not automatically add a distributed lock around the method body. If the goal is preventing cache stampedes across nodes, you need a suitable coordination strategy such as a provider with a true atomic loader/lock or distributed single-flight with timeouts and recovery; do not treat `sync=true` as a global mutex.

### 9.1. Nulls and Failed Futures

With async caching, a future may complete with a value, null, or complete **exceptionally**. You must test:

- Does the provider cache `null` values, and how does Spring handle the wrapper?
- With `sync=true`, `unless` cannot be used to exclude null; if the provider disallows null, choose a different value type or suitable solution.
- When a loader fails, what error do callers waiting on the same key receive? Is the in-flight entry cleared/retried?
- On a network timeout, did the call already write to the cache even though the client never received a response?
- When a caller cancels a future, does the provider break shared loading for other callers?

Do not use successful/failed future completion to automatically conclude the cache was written or cleared prior to database transaction commit.

## 10. Alternative Designs When Both Multi-Tier Caching and Async Are Needed

If the product requirement is **L1 local Caffeine, L2 remote Redis, and finally DB/API**, design an explicit contract rather than relying on an asynchronous `cacheNames` list.

### 10.1. One Logical Cache, Multiple Tiers Inside

One approach is building **one** logical Spring `Cache` adapter named `products`; internally, the adapter performs:

```text
Application
   |
   +-- Spring Cache("products")
           |
           +-- L1 Caffeine get(P1)
           |      |
           |      +-- HIT -> return
           |      +-- MISS
           |
           +-- L2 Redis async get(P1)
           |      |
           |      +-- HIT -> backfill L1 -> return
           |      +-- MISS
           |
           +-- repository load(P1)
                  |
                  +-- put L2 and L1 per policy
                  +-- return
```

This adapter must properly implement `retrieve(key)`, `retrieve(key, supplier)`, `put`, `evict`, and null/error policies. With `sync=true`, the Spring operation still sees **one logical cache**, even though the adapter has multiple tiers internally. However, key-based synchronized loading and lock scope **must actually be implemented by the adapter**.

This is an **architectural option**, not a claim that Spring automatically constructs this adapter when you declare `CompositeCacheManager` or `cacheNames={"l1","l2"}`.

### 10.2. Only One Provider per Method

If L1/L2 is not needed, a simpler and more controllable solution is choosing one suitable cache region:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public CompletableFuture<Product> findAsync(String sku) {
    return repository.findAsync(sku);
}
```

This is an illustrative fragment. If `sync=true` is desired, verify the provider supports async retrieve-and-load and then enable `sync` with **one** cache.

### 10.3. `CacheResolver` Does Not Automatically Solve Late Misses

`CacheResolver` selects which caches are used for an operation based on context. It does not inherently define a state machine to wait for a remote future to complete and automatically fall over to the next region.

For true fallback, write that logic in a dedicated layer/service/adapter or use a cache provider with a verified multi-tier contract. When writing it yourself, test hit, early miss, late miss, errors, timeouts, and updates/evictions across tiers.

### 10.4. Consistency and Keys

In every design, keys must include all factors that change the result, such as tenant, currency, locale, query filters, and authorization context whenever they actually affect the data. If two requests share a SKU yet belong to different tenants, they must never coalesce into one load or share an entry.

If L1 and L2 have different TTLs, L1 can hold a stale value after DB/L2 changes. You need an invalidation strategy or product-approved consistency bounds. `sync=true` only resolves competing loads on a cache miss; it **does not** automatically resolve read–update races.

## 11. Common Mistakes

1. **Thinking multiple `cacheNames` always provide L1/L2 fallback.** With late async misses, trailing caches may never be consulted.
2. **Enabling `sync=true` across multiple cache names.** Directly violates `@Cacheable`'s single-cache restriction.
3. **Combining `sync=true` with `unless`.** Spring does not support result vetoing on synchronized cache operations.
4. **Combining `@CacheEvict` or `@CachePut` on the same `sync=true` method.** Separate methods and operations.
5. **Believing `sync=true` guarantees a single loader across multiple JVMs.** Atomicity scope depends on the provider and topology.
6. **Assuming every `Cache` supports `retrieve`.** Custom adapters may not implement async retrieval.
7. **Testing only cache hits or immediate misses.** Add late-determined miss tests when using remote async caches.
8. **Not counting source invocations.** Multiple callers can return the same value even when the loader ran multiple times.
9. **Confusing `@Async` with async caching.** One coordinates executors; the other manages cache lookup/storage.
10. **Storing publishers instead of finite results.** For long or infinite `Flux` streams, collecting into a `List` can overload memory.
11. **Mismatched keys across methods or tiers.** Stale/cross-tenant results matter far more than optimizing hit rates.
12. **Ignoring null or exceptions.** Async futures can complete with null or exceptionally; loader failures need appropriate retry policies.
13. **Mixing Spring Cache with native provider APIs without control.** Can bypass null adaptation, decorators, and metrics.
14. **Treating `CompositeCacheManager` as a key-level two-tier cache.** It handles manager selection, not automatic backfilling and fallback.
15. **Not re-testing after Spring/provider upgrades.** Async adaptation, retrieval, and eviction can change across versions.

## 12. Testing and Pre-Deployment Checklist

| Test Case | What to Observe |
| --- | --- |
| One cache, one key, multiple callers | How many times does the loader run with `sync=true`? |
| One cache, two different keys | Can both loads run independently without sharing values? |
| Multi-name, first cache returns early miss | Are trailing caches queried? |
| Multi-name, first cache returns **late miss** | Are trailing caches skipped and the source executed? |
| Multi-name, first cache hits | Is calling the real source avoided? |
| Cache provider lacks `retrieve` support | Is a clear error raised instead of silent fallback? |
| `CompletableFuture` returns null | Which provider policy governs null entries? |
| Future completes exceptionally | What error do callers get? Is an in-flight entry stuck? |
| Evict during load | Is there a race putting a stale value back into cache? |
| Requests arriving from two JVMs | Is single-flight only local or truly cross-node? |
| L1 and L2 have different TTLs | Are stale values read or invalidation rules violated? |
| Reactive `Flux` with many elements | Is memory collected/consumed unexpectedly? |

### Operational Checklist

1. Confirm the **exact Spring version** and cache adapter/provider version in runtime.
2. For async/reactive methods, prefer **one cache name** per caching operation.
3. If enabling `sync=true`, ensure **one cache**, no `unless`, and no combined caching operations.
4. Check `Cache.retrieve(key)` and `retrieve(key, supplier)` on the provider; do not assume all implementations match.
5. Write **late-determined miss** tests instead of testing only local in-memory caches.
6. Measure loader counts, cache hit/miss, lookup latency, waiting callers, timeouts, and exceptions.
7. Verify keys are scoped properly for tenant/filter/permission.
8. With multi-node deployments, measure per-process and cross-node behavior separately.
9. If L1/L2 is needed, use an adapter/strategy with an explicit contract for fallback, backfilling, and invalidation.
10. Test load–update races, eviction, TTL, rollbacks, and network errors.

## 13. Conclusion

Four principles help avoid bugs when designing asynchronous Spring Cache:

- **One cache name** is the most predictable choice for an async/reactive operation.
- **Multiple cache names with `sync=false`** can be declared, yet do not guarantee every region is queried when misses arrive late.
- **`sync=true` has strict restrictions**: only one cache, no `unless`, and no combining other operations on the same method.
- **True single-flight is a provider capability**; verify via `retrieve`, loader counts, and concurrency tests, especially across multiple JVMs.

If you need async, single-flight, and L1/L2 together, treat it as an **explicitly implemented and tested multi-tier cache design**, rather than merely listing multiple names in `cacheNames`.

## Official References

- Spring Framework 6.2 — Cache annotations, `@Cacheable`, Synchronized Caching, async/reactive: https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html
- Spring Framework 6.2.9 — `@Cacheable` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Framework 6.2.9 — `Cache.retrieve` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/cache/Cache.html
- Spring Framework 6.2.9 — `CaffeineCacheManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/cache/caffeine/CaffeineCacheManager.html
- Spring Framework — Cache Store Configuration: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html