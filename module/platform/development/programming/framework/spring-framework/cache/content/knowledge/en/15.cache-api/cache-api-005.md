# `put` and `putIfAbsent` in Spring Cache — Programmatic Write Operations

## 1. Problem: overwrite or only create when the key does not exist yet?

Spring Framework has two styles of working with caches:

- **Declarative caching:** place `@Cacheable`, `@CachePut`, `@CacheEvict` on methods; the Spring interceptor handles the operations.
- **Programmatic caching:** obtain an `org.springframework.cache.Cache` object and explicitly call `get`, `put`, `putIfAbsent`, `evict` in code.

This lesson focuses on two direct operations on `Cache`:

```java
cache.put("P100", product);                      // Write or overwrite.
Cache.ValueWrapper previous =
        cache.putIfAbsent("P100", anotherProduct); // Only add if not present.
```

Suppose two requests both want to store data at key `P100`:

- With `put`, the later write request can **replace** the value written by the earlier request.
- With `putIfAbsent`, when the key already has a mapping, the application **keeps** the old value and receives information about that mapping.

This difference matters when initializing a cache once, racing between multiple threads, wanting to avoid overwrites, or needing a "first writer wins" model for a **cache entry**. However, `putIfAbsent` does not automatically create a database transaction and does not guarantee write exclusion across multiple nodes if the provider does not support atomic operations at that scope.

## 2. The `Cache` object and retrieving a cache region

Spring defines `org.springframework.cache.Cache` as the common API for cache providers. Each region has a **cache name** and a set of **key → value** mappings.

```java
import java.util.Objects;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;

Cache cache = Objects.requireNonNull(
        cacheManager.getCache("products"),
        "products cache is not configured");
```

This is an **illustrative snippet** inside code that already has a `cacheManager` variable. The complete example in section 6 creates a real `ConcurrentMapCacheManager` and needs no Spring proxy configuration.

`CacheManager.getCache("products")` can return `null` when the manager does not manage that name; certain managers can create caches dynamically. Do not call `cache.put(...)` when `cache` might be null.

Also distinguish:

- **Cache name:** `products` identifies the region.
- **Key:** `P100` identifies an entry inside the region.
- **Value:** the object stored under the key.
- **Cache provider:** the implementation storing in JVM, Caffeine, Redis, JCache, or another backend; determines atomicity, null handling, TTL, and durability.

Two different regions can use the same key without holding the same value. Two different managers can manage the same region name while backed by two independent data stores.

## 3. `Cache.put(key, value)`: unconditional write or replace

Main signature:

```java
void put(Object key, @Nullable Object value);
```

By contract, `put` **associates the supplied value with the key**. If the key already exists, the old mapping is replaced by the new value.

```java
cache.put("P100", "Pen");
cache.put("P100", "Blue Pen"); // Overwrite.
System.out.println(cache.get("P100", String.class)); // Blue Pen
```

The snippet above holds when the provider applies puts immediately, such as `ConcurrentMapCache`; some decorators/providers may defer the write, explained in section 8.

Key characteristics:

1. `put` does not inspect the old value before deciding to replace it. This is the choice when **intentionally updating** the cache to a new state.
2. `put` returns `void`, so the caller receives no information on "whether the key was already present" or "what the old value was" from that call itself.
3. `put` does not call the database automatically, does not check data freshness, and does not attach a TTL if the provider has none configured.
4. `put` may be executed asynchronously or **deferred** in some implementations, so do not assume another thread immediately observes the new value right after `put` returns.
5. When multiple writers call `put` on the same key concurrently, which caller writes last and the final value depend on the actual order processed by the provider. `put` is not compare-and-set.

**When to use:** proactively updating the cache after confirming accurate new data, refreshing a snapshot, or replacing an old entry following a consistently processed update event.

**Warning:** do not use `put` as a transactional data source. If the database transaction rolls back after writing to the cache, the cache may contain a value that was never committed. Consider transaction awareness and invalidation ordering.

## 4. `Cache.putIfAbsent(key, value)`: add only if no prior mapping exists

Signature:

```java
@Nullable
Cache.ValueWrapper putIfAbsent(Object key, @Nullable Object value);
```

Ideal contract: **check and add as an atomic operation**. If the key is not yet mapped, insert the value; if the key is already mapped, do not overwrite.

```java
Cache.ValueWrapper first = cache.putIfAbsent("P100", "Pen");
Cache.ValueWrapper second = cache.putIfAbsent("P100", "Blue Pen");

System.out.println(first == null); // true: key did not exist, added "Pen".
System.out.println(second.get());  // Pen: kept the old entry.
```

The snippet above assumes the cache starts empty and the implementation properly supports `putIfAbsent` semantics.

### 4.1. The return value must be interpreted properly

| Return value | Meaning per contract |
| --- | --- |
| `null` (the wrapper object itself is null) | No mapping before the call; value was accepted and added |
| Non-null `ValueWrapper`, non-null `get()` | Mapping already existed; did **not** replace the old value |
| Non-null `ValueWrapper`, `get() == null` | Entry already existed holding a **cached null** (if provider supports it); do not treat as an absent key |

Example showing the wrapper must be checked before reading:

```java
Cache.ValueWrapper previous =
        cache.putIfAbsent("P200", newProduct);

if (previous == null) {
    System.out.println("Created new cache entry");
} else {
    System.out.println("Entry already exists: " + previous.get());
}
```

`newProduct` is a variable from an actual service, and `putIfAbsent` **does not return a boolean**. To know whether the operation inserted, check **`previous == null`**, do not use `previous.get() == null` as the condition.

This point is especially important when the provider allows caching Java `null` values.

### 4.2. Do not replace `putIfAbsent` with `get` followed by `put`

The following pattern has a race condition:

```java
// NOT safe when multiple threads run concurrently.
if (cache.get("P100") == null) {
    cache.put("P100", value);
}
```

Two threads can both see `get` return null, then call `put` one after another, causing one writer to overwrite the other. That is a **check-then-act / TOCTOU** bug.

`putIfAbsent` is designed to combine "check" and "set value if missing" into a single operation. However, **actual atomicity depends on the implementation**, see section 5; do not infer a guarantee solely from the method name.

### 4.3. Cached-null differs from a cache miss

`Cache.get(Object key)` returns:

- **`null` wrapper:** no mapping exists.
- **`ValueWrapper` with `get() == null`:** mapping exists, value is null.

Example:

```java
Cache.ValueWrapper wrapper = cache.get("P100");
boolean absent = wrapper == null;
boolean cachedNull = wrapper != null && wrapper.get() == null;
```

The `cache.get(key, SomeClass.class)` variant usually **cannot distinguish** those two cases because it returns the unwrapped value. Whether null is allowed and how it maps to native values belongs to the cache provider/configuration.

In `ConcurrentMapCacheManager`, null is allowed by default by internally converting to a sentinel; `ConcurrentHashMap` itself does not accept null values. A cached-null entry **already exists**, so `putIfAbsent(key, nonNullValue)` must not overwrite it.

## 5. Atomicity: API expectations and implementation limits

The Javadoc for `Cache.putIfAbsent` describes adding when absent as an atomic operation. Yet the same Javadoc warns: the **default implementation of the `Cache` interface** may implement it as `get` then `put`, i.e., two **non-atomic** steps. Built-in `CacheManager` implementations provided by Spring are documented as supporting atomic put, but you still must verify the provider/cache adapter in use.

| Scenario | `put` | `putIfAbsent` with atomic implementation |
| --- | --- | --- |
| Key does not exist | Writes value | Writes value, returns null wrapper |
| Key already has `"V1"` | Replaces with `"V2"` | Keeps `"V1"`, returns wrapper of `"V1"` |
| Key holds cached-null | Replaces with new value | Keeps cached-null, returns wrapper with `get() == null` |
| Two writers try to add an empty key | Whichever writer runs later can overwrite the earlier one | Only one writer succeeds in adding during that race |
| Entry is evicted/expired after insertion | A new write can occur | A later `putIfAbsent` can insert again because the key is absent |

An implementation may guarantee atomicity on **one instance** while lacking the ability to exclude races across multiple JVMs. For instance, `ConcurrentMapCache` relies on a concurrent data structure in a single JVM; that does not make it a distributed cache store.

With Redis/JCache/Caffeine or a custom adapter, read the documentation and test the exact version, especially these questions:

- Is the check-and-set atomic **inside the provider** or only inside a Java wrapper?
- When two app instances write the same key, do they share the same lock/atomic operation scope?
- On connection errors or timeouts, what does the caller receive? Could the write have succeeded without the client receiving a response?
- Does the backend support cached-null and identical key/value serialization across all nodes?
- If TTL/eviction is configured, what is the final outcome after a key expires and is re-added?

**Do not use `putIfAbsent` as a default distributed lock mechanism.** It inserts an entry when absent; it provides no lease ownership, fencing token, safe timeout, or proper lock release. The cache entry may be evicted/expired while the task is still running.

## 6. Runnable Java 17 + Spring 6.2.9 example

This example uses the `Cache` API **directly**, without depending on `@EnableCaching` or Spring AOP. The goal is to verify each key state, the return value of `putIfAbsent`, and contention between two threads.

**Directory structure:**

```text
cache-put-demo/
├── pom.xml
└── src/main/java/CachePutDemo.java
```

**Contents of `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>cache-put-demo</artifactId>
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

**Contents of `src/main/java/CachePutDemo.java`:**

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import org.springframework.cache.Cache;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;

public class CachePutDemo {

    private static String oldValue(Cache.ValueWrapper wrapper) {
        return wrapper == null
                ? "ABSENT"
                : String.valueOf(wrapper.get());
    }

    public static void main(String[] args) throws Exception {
        var manager = new ConcurrentMapCacheManager("products");
        manager.setAllowNullValues(true);
        Cache cache = Objects.requireNonNull(
                manager.getCache("products"));

        System.out.println("A initially: "
                + oldValue(cache.get("A")));

        cache.put("A", "Alpha");
        System.out.println("A after put: "
                + cache.get("A", String.class));

        cache.put("A", "Alpha-v2");
        System.out.println("A after replace: "
                + cache.get("A", String.class));

        Cache.ValueWrapper priorA =
                cache.putIfAbsent("A", "Ignored");
        System.out.println("A previous: "
                + oldValue(priorA));
        System.out.println("A after putIfAbsent: "
                + cache.get("A", String.class));

        Cache.ValueWrapper priorB =
                cache.putIfAbsent("B", "Beta");
        System.out.println("B previous: "
                + oldValue(priorB));
        System.out.println("B after insert: "
                + cache.get("B", String.class));

        cache.put("N", null);
        Cache.ValueWrapper priorN =
                cache.putIfAbsent("N", "Replacement");
        System.out.println("N previous entry exists: "
                + (priorN != null));
        System.out.println("N previous value null: "
                + (priorN != null && priorN.get() == null));
        Cache.ValueWrapper currentN = cache.get("N");
        System.out.println("N remains cached null: "
                + (currentN != null && currentN.get() == null));

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch go = new CountDownLatch(1);
        try {
            List<Future<Boolean>> results = new ArrayList<>();
            for (int i = 1; i <= 2; i++) {
                String candidate = "writer-" + i;
                results.add(pool.submit(() -> {
                    ready.countDown();
                    go.await();
                    return cache.putIfAbsent("R", candidate) == null;
                }));
            }
            ready.await();
            go.countDown();

            int inserted = 0;
            for (Future<Boolean> result : results) {
                if (result.get()) {
                    inserted++;
                }
            }

            String stored = cache.get("R", String.class);
            System.out.println("R successful inserts: " + inserted);
            System.out.println("R stores a candidate: "
                    + ("writer-1".equals(stored)
                        || "writer-2".equals(stored)));
        } finally {
            go.countDown();
            pool.shutdownNow();
        }
    }
}
```

**Run in the directory containing `pom.xml`** (JDK 17+ and Maven):

```bash
mvn -q compile exec:java -Dexec.mainClass=CachePutDemo
```

**Lines printed by the program**, excluding Maven/SLF4J logs if the environment adds them:

```text
A initially: ABSENT
A after put: Alpha
A after replace: Alpha-v2
A previous: Alpha-v2
A after putIfAbsent: Alpha-v2
B previous: ABSENT
B after insert: Beta
N previous entry exists: true
N previous value null: true
N remains cached null: true
R successful inserts: 1
R stores a candidate: true
```

**Output explanation:**

1. `A` does not exist yet → `get("A")` returns a null wrapper; the first `put` writes `Alpha`, and the second `put` replaces it with `Alpha-v2`.
2. `putIfAbsent("A", "Ignored")` returns the wrapper containing `Alpha-v2` and does not replace the existing value.
3. `putIfAbsent("B", "Beta")` returns a null wrapper because `B` did not exist, and inserts `Beta`.
4. `N` is explicitly written as `null`. The provider in the example has null support enabled, so `putIfAbsent("N", "Replacement")` sees an **existing entry** and does not replace it; `priorN` is a non-null wrapper whose `priorN.get()` is null.
5. Two threads both call `putIfAbsent("R", candidate)`. `ConcurrentMapCache` implements this operation atomically within the same JVM; only **one** caller observes a null wrapper result. The application does not print the "winner" name because thread scheduling is non-deterministic.

The example uses `Cache` and `CacheManager` directly, so it does not require a Spring application context, `@EnableCaching`, or proxies. Only the `spring-context` dependency is needed. It also does not simulate transactions, TTL, or cache sharing across multiple JVMs.

## 7. How `putIfAbsent` differs from `get(key, Callable)` and `@Cacheable(sync=true)`

Three operations are easily confused because all involve cache misses:

| Mechanism | When is the new value created? | Purpose |
| --- | --- | --- |
| `cache.putIfAbsent(key, value)` | `value` is **already computed before the call** | Do not overwrite an existing key |
| `cache.get(key, () -> load())` | Provider may call `load()` **only when the key is missing** | Retrieve or load value via callback |
| `@Cacheable(sync=true)` | Interceptor invokes the callback-based cache load path, if provider supports it | Reduce duplicate loads when multiple calls miss the same key |

The following example can still call the repository **twice**:

```java
// Both threads may compute the value first.
Product expensive = repository.load(sku);
cache.putIfAbsent(sku, expensive);
```

Even though only one thread inserts successfully, both ran `repository.load(sku)` beforehand. `putIfAbsent` cannot undo computation cost that has already occurred.

If the goal is **not running the loader twice**, use the appropriate value-loader path and test the provider:

```java
Product product = cache.get(sku, () -> repository.load(sku));
```

This snippet is only illustrative when `repository` has a `load` method returning `Product`. `Cache.get(key, Callable)` has a **recommended** synchronized-loading contract if the implementation supports it; it is not an absolute guarantee for every provider or node.

Similarly, `@Cacheable(sync=true)` has its own restrictions: it does not support `unless`, only a single cache, and cannot combine other operations on the same synchronized method. Do not treat `putIfAbsent` as a workaround for those limits.

## 8. Transactions, deferred writes, and consistency

### 8.1. `put` is not necessarily visible immediately

Spring Cache Javadoc allows `put` to be executed later, for example via `TransactionAwareCacheDecorator`. While a Spring transaction is open, this decorator can **defer `put` until after a successful commit**; on rollback, the deferred put is not applied.

Illustrative timeline:

```text
Transaction starts
  -> update database
  -> cache.put("P100", productNew)   [may only register a callback]
  -> commit succeeds
  -> decorator executes the actual put
```

With direct `ConcurrentMapCache` as in section 6, `put` applies in memory immediately. With decorators, asynchronous providers, or remote backends, verify when the value actually becomes observable. Do not generalize one conclusion to every implementation.

### 8.2. `putIfAbsent` is an immediate operation — it cannot be deferred like `put`

`TransactionAwareCacheDecorator` distinguishes two groups:

- `put`/`evict`/`clear` can be deferred until **after-commit** when a suitable transaction is active.
- `putIfAbsent` and `evictIfPresent` have immediate semantics, so they **cannot be deferred** in the same way.

This can cause issues:

```text
Transaction starts
  -> create P100 record in database (uncommitted)
  -> cache.putIfAbsent("P100", productNew)  [writes immediately]
  -> transaction rolls back
  -> database lacks P100, cache may still retain P100
```

Therefore, **do not use `putIfAbsent` to replace `put` inside a transaction just because you want "atomic"**. Atomic key insertion does not mean atomic with the database transaction.

If transaction-aware caching is needed, inspect the decorator carefully and place cache operations at the proper boundary, such as after commit, or use a tested outbox/event/invalidation strategy. If you need "create only if not exists" in the database, use a database unique constraint or compare-and-set, do not rely on the cache.

### 8.3. Races between put and evict still exist

`putIfAbsent` only guards the condition **whether the key already exists at check-and-insert time**. It does not lock all other operations:

```text
T1: reads old P100 from DB
T2: updates DB to new P100, evicts P100
T1: putIfAbsent(P100, oldValue) -> sees empty cache, writes old value
T3: reads cache -> receives oldValue
```

This is a classic race between cache loads and updates. You may need versioning, post-commit invalidation, a consistent read/write contract, or versioned cache keys.

### 8.4. Same key but different cache name/provider

`putIfAbsent` applies to **one specific Cache region**. It provides no coordination between `productsLocal/P100` and `productsRedis/P100` if the two regions have separate stores. `CompositeCacheManager` also only selects a region by name and does not automatically perform L1/L2 coordination per key.

## 9. Relation to `@CachePut` and declarative APIs

`@CachePut` is a **declarative caching annotation operation**, distinct from `Cache.put`:

```java
@CachePut(cacheNames = "products", key = "#p0.id()")
public Product save(Product product) {
    return repository.save(product);
}
```

The example above is an illustrative service method that already has `repository` and the `Product` type. When called through the Spring proxy, the real method still runs and Spring puts the result into the cache according to the annotation.

`@CachePut` **is not another name for `putIfAbsent`**. Its purpose is to update the cache with the method's result; it does not provide a standard annotation equivalent to "put only if absent".

Conversely, when using the programmatic API:

```java
Cache cache = cacheManager.getCache("products");
cache.put(product.id(), product); 
```

The caller directly decides the value and when to invoke it. If a service uses both annotations and the programmatic API, you must align the region, key, data type, null policy, and invalidation timing; otherwise you may accidentally create two separate entries for the same entity.

**Note:** calling `Cache.put` or `Cache.putIfAbsent` directly does not require `@EnableCaching` or Spring AOP. However, caching annotations require the proper Spring infrastructure and calls routed through the interceptor/proxy. Do not confuse this difference when writing tests.

## 10. Choosing the right API for your needs

| Practical need | Recommendation |
| --- | --- |
| Replace entry with a newly confirmed result | `cache.put(key, newValue)` |
| Set an initial value only when the key does not exist yet | `cache.putIfAbsent(key, initialValue)` |
| Need to know if a prior entry existed | Inspect the wrapper returned by `putIfAbsent` or `get` |
| Value is expensive to compute and you want to avoid duplicate computation on miss | `cache.get(key, Callable)` when the provider guarantees appropriate support |
| Update cache with the result of a method going through Spring AOP | `@CachePut` |
| Do not want to keep a result when it returns null | `@Cacheable(unless="#result == null")` for suitable operations; do not apply mechanically to `putIfAbsent` |
| Need compare-and-set by version | Use a backend or DB API supporting CAS/versioning; do not treat `putIfAbsent` as full CAS |
| Need a distributed lock for business logic | Use a proper locking/transaction mechanism; do not infer one from a cache entry |

**Two differences that must not be overlooked:** `put` can replace the old value and returns no mapping info; `putIfAbsent` does not replace the old value (when the implementation honors the contract) and returns the wrapper of the previous mapping, which may contain Java `null`.

## 11. Common pitfalls and mandatory tests

### 11.1. Common pitfalls

1. **Assuming `putIfAbsent` returns a boolean.** Wrong: the method returns `Cache.ValueWrapper` or null; use `previous == null` to check whether there was no prior mapping.
2. **Confusing cached-null with a cache miss.** `wrapper.get() == null` does not mean there is no entry; check `wrapper == null`.
3. **Writing `get` then `put` manually.** Two threads can both see a miss and overwrite each other, whereas `putIfAbsent` is designed to prevent that race when the backend supports atomicity.
4. **Assuming every implementation is atomic.** Default `Cache.putIfAbsent` can be two steps; check the adapter and native cache.
5. **Assuming `put` is immediately visible.** `TransactionAwareCacheDecorator` or an async backend may defer the operation.
6. **Assuming `putIfAbsent` also defers until after commit.** With a transaction-aware decorator, this immediate operation does not wait for after-commit, risking cached data from a rolled-back transaction.
7. **Using `putIfAbsent` to ensure the freshest value.** It favors the *existing* value, even if stale; update/evict according to the business contract.
8. **Assuming `putIfAbsent` eliminates duplicate computation.** If the value is loaded before calling it, two threads can still load from the source together.
9. **Ignoring null policies.** Some providers reject null; `ConcurrentMapCache` may use a sentinel; test the real provider.
10. **Using mutable keys or omitting tenant discrimination.** Wrong keys can share entries across incompatible data groups.
11. **Extrapolating single-JVM atomicity to multi-JVM atomicity.** Local and remote caches have different scopes; test multi-node if needed.
12. **Using the cache to enforce long-term uniqueness constraints.** Caches have TTL/eviction and cannot replace database constraints.

### 11.2. Minimum test cases

| Test case | Action | What to verify |
| --- | --- | --- |
| Absent key | `putIfAbsent(K,V1)` | Returns null wrapper; subsequent read returns V1 |
| Existing key | `put(K,V1)` then `putIfAbsent(K,V2)` | Returns wrapper with V1; read still returns V1 |
| Overwrite | `put(K,V1)` then `put(K,V2)` | Final value is V2 per provider semantics |
| Cached-null | `put(K,null)` then `putIfAbsent(K,V1)` | If provider supports: non-null wrapper, null value preserved |
| Two threads, empty key | Have two threads call `putIfAbsent` | With an atomic provider, exactly one caller inserts |
| Two processes/nodes | Concurrent writes to remote cache from multiple JVMs | Verify real-scope atomicity, timeouts, and errors |
| Transaction rollback | Call `put` and `putIfAbsent` via transaction-aware decorator | Verify deferred vs. immediate behavior |
| Evicted/expired key | Insert, evict/expire, then insert again | Can insert anew once the mapping is gone |
| Provider failure | Simulate timeouts/failures | Error handling, "written without response" cases |
| Cache hit/miss | Read via `get` and inspect wrapper | Do not confuse cached-null with missing |

Beyond final values, measure error rates, write latency, key contention counts, unintended overwrites, and transaction interactions. When using a remote provider, do not place keys containing sensitive data directly into logs or metric labels.

## 12. Practical summary

Concise rule set:

```java
// To write a new entry or replace the old value:
cache.put(key, value);

// To preserve the old value when the key already exists:
Cache.ValueWrapper previous = cache.putIfAbsent(key, value);
boolean inserted = previous == null;

// To distinguish a miss from a cached-null:
Cache.ValueWrapper current = cache.get(key);
boolean missing = current == null;
boolean storedNull = current != null && current.get() == null;
```

**Choose `put` when intentionally updating; choose `putIfAbsent` when you need the condition "add only if the key is absent" and the provider satisfies your atomicity requirements.** Both are cache-entry operations and do not replace transactions, distributed locks, or source-data consistency guarantees.

## Official documentation

- Spring Framework 6.2.9 — `Cache` interface, `put` and `putIfAbsent`: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/cache/Cache.html
- Spring Framework 6.2.9 — `ConcurrentMapCache`: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCache.html
- Spring Framework 6.2 — `TransactionAwareCacheDecorator`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheDecorator.html
- Spring Framework — Cache abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
