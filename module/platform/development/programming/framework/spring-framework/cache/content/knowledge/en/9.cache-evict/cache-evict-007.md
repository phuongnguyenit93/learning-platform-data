# Void methods as cache eviction triggers with @CacheEvict

## Objective

When a method modifies source data (updating a price, deleting a product, re-importing configuration…), values stored by Spring Cache can become stale. `@CacheEvict` lets you turn **the business method invocation itself** into a trigger to remove stale entries. Crucially, that method **can return `void`**, because cache eviction does not need a return value to store.

After this lesson, you will be able to:

- Explain why `void` works with `@CacheEvict` yet does not work for populating cache values with `@Cacheable`/`@CachePut`.
- Trace the sequence **write source data → evict cache entry → next read reloads**.
- Choose `cacheNames`, `key`, `allEntries`, and `beforeInvocation` with the proper scope.
- Understand the effects of exceptions, transactions, AOP proxies, and multiple instances.
- Run a Java 17 demo verifying cache state before and after calling a `void` method.

## 1. Why can a void method still evict the cache?

Suppose the system reads product prices from a database:

~~~java
@Cacheable(cacheNames = "prices", key = "#p0")
public int getPrice(String sku) {
    return repository.findPrice(sku);
}
~~~

This is an illustrative snippet; `repository` is supplied by the application. For SKU `"A"`, after the first read, the cache may contain:

~~~text
Cache "prices"
    key "A" -> value 100
~~~

If the price in the database later changes to 120 without removing the entry, a call to `getPrice("A")` can **hit** and return 100. An update method does not need to return data:

~~~java
@CacheEvict(cacheNames = "prices", key = "#p0")
public void updatePrice(String sku, int newPrice) {
    repository.updatePrice(sku, newPrice);
}
~~~

When a caller invokes `updatePrice("A", 120)` through the Spring proxy and the method runs **successfully**, Spring deletes entry `"A"` in the `"prices"` cache. The next read misses, reloads 120, and can cache the new value.

Here `void` makes sense: the method only **triggers entry removal**. `@CacheEvict` does not need to read `return` to know what to remove; the cache name and key are derived from the annotation and arguments. Conversely, `@Cacheable` and `@CachePut` typically need the return value to put into the cache.

**Do not misunderstand:** `void` does not clear the cache on its own. It is `@CacheEvict` processed by Spring's caching mechanism that does so. A `void` method without the annotation (or one that does not pass through the interceptor) will not automatically alter the cache.

## 2. Standard execution flow: void + default @CacheEvict

Suppose both the getter and updater use `cacheNames = "prices"` and key `#p0`.

~~~text
1) getPrice("A")
       |
       v
   Cache("prices").get("A")
       |
       +-- MISS -> read DB: 100 -> put("A", 100) -> return 100

2) updatePrice("A", 120)   [void method]
       |
       v
   Spring cache interceptor
       |
       v
   Invoke body: update DB to 120
       |
       +-- succeeded --> evict("A") --> return void
       |
       +-- throws exception -> by default DOES NOT evict

3) getPrice("A")
       |
       v
   Cache("prices").get("A")
       |
       +-- MISS -> read DB: 120 -> put("A", 120) -> return 120

4) getPrice("A")
       |
       +-- HIT -> return 120, skips getter
~~~

An important point about timing: `@CacheEvict` defaults to `beforeInvocation = false`, meaning eviction occurs **after the method is invoked successfully**. `@CacheEvict` does not guarantee that the database transaction has committed (analyzed in section 7).

### Does the cache need to already contain the key?

No. Calling a `void` updater carrying `@CacheEvict` is still valid when the cache does not yet hold the corresponding entry. Removing an absent entry normally makes no change to cache data; the goal is ensuring subsequent reads do not reuse a stale value.

A method annotated with `@CacheEvict` **is not skipped just because the cache already hits**. It differs from a `@Cacheable` getter: the updater must execute to perform the business work, and then eviction is processed according to configuration.

## 3. Three layers of responsibility to separate

| Layer | Responsibility | Example |
| --- | --- | --- |
| Business logic | Write/delete source data, validate input, authorization | `repository.updatePrice(sku, newPrice)` |
| Spring Cache | Resolve cache, build key, coordinate `evict` per annotation | `@CacheEvict(cacheNames="prices", key="#p0")` |
| Cache provider | Perform actual entry deletion; determine distribution/persistence traits | ConcurrentMap, Caffeine, Redis |

`@CacheEvict` does not mean Spring will automatically update the database. If the method body only logs or does not write real data, the cache may still be evicted while source data stays unchanged. The next read will simply fetch the exact same old data from the source.

Conversely, updating the database while forgetting to evict/refresh the cache can leave the system serving stale values.

## 4. Choosing the key: targeting the exact entry to remove

### 4.1. Same cache name and same key rule as the getter

~~~java
// Read: use SKU as the key.
@Cacheable(cacheNames = "prices", key = "#p0")
public int getPrice(String sku) {
    return repository.findPrice(sku);
}

// Write: SKU is also the first argument; evict that exact key.
@CacheEvict(cacheNames = "prices", key = "#p0")
public void updatePrice(String sku, int newPrice) {
    repository.updatePrice(sku, newPrice);
}
~~~

Both snippets are illustrative and not standalone because `repository` is missing. `#p0` is the first parameter of each method. In the updater, the second parameter `newPrice` does **not** participate in the key because `key = "#p0"` is specified.

If `key` is omitted, Spring defaults to `SimpleKeyGenerator`. A getter with **one** parameter `sku` may use the string `sku` itself as the key; an updater with **two** parameters `sku` and `newPrice` will build a composite key containing both. Then the updater risks evicting the wrong key (effectively failing to remove the entry used by the getter). Therefore, for methods taking different parameters, **specify the key explicitly**.

### 4.2. Table of key mismatch errors

| Getter | Void updater | Consequence |
| --- | --- | --- |
| `prices` / `#p0` | `prices` / `#p0` | Evicts exact entry by SKU |
| `prices` / `#p0` | `prices` / default 2 parameters | May evict wrong key; stale copy remains |
| `prices` / `#p0` | `products` / `#p0` | Evicts in the wrong cache region |
| Key shaped `tenant + ":" + sku` | Only key `sku` | Tenant-scoped entry is not evicted |
| Getter using normalized code | Updater using unnormalized code | Key strings may fail to match |

For multi-tenant systems, keys should include the tenant ID or an appropriate cache partitioning scheme so eviction does not affect other tenants' data. When multiple caches hold data depending on one entity, design an invalidation policy for **all affected regions**, rather than just a single entry.

### 4.3. Using SpEL in the right context

~~~java
@CacheEvict(cacheNames = "prices", key = "#p0")
public void updatePrice(String sku, int price) { /* ... */ }

// Alternative: first argument via root.args.
@CacheEvict(cacheNames = "prices", key = "#root.args[0]")
public void deletePrice(String sku) { /* ... */ }
~~~

These are illustrative snippets. `#p0`/`#root.args[0]` avoids depending on whether Java parameter names are retained in bytecode. If using `#sku`, ensure the compiler configuration preserves parameter name metadata (e.g., `-parameters`). For `void` methods, **do not rely on `#result`** to build keys: there is no usable business result. Rely on arguments, appropriate objects/context, or a custom `KeyGenerator`.

### 4.4. Condition before eviction

~~~java
@CacheEvict(
    cacheNames = "prices",
    key = "#p0",
    condition = "#p0 != null && !#p0.isBlank()"
)
public void updatePrice(String sku, int price) { /* ... */ }
~~~

`condition` is a SpEL expression determining whether the operation should execute. If the condition is false, the business method body can still run, yet that eviction is skipped. A faulty condition can cause a stale cache, especially if source data still gets updated. Test this logic carefully.

## 5. beforeInvocation: evict after or before the void body?

Two common configurations:

~~~java
// Default: evicts if the method completes normally.
@CacheEvict(cacheNames = "prices", key = "#p0")
public void updateAfter(String sku, int price) { /* write DB */ }

// Evicts BEFORE calling the method, even if the method body later errors.
@CacheEvict(cacheNames = "prices", key = "#p0", beforeInvocation = true)
public void invalidateFirst(String sku) { /* proceed with work */ }
~~~

Both are snippets, not runnable files.

| Attribute | Default: `beforeInvocation=false` | `beforeInvocation=true` |
| --- | --- | --- |
| Eviction timing | After the method executes successfully | Before the method starts running |
| Method throws exception | Does not evict for this operation | Eviction was already requested |
| Can cache be evicted even if update fails? | Normally not from this operation itself | Yes |
| When suitable | Invalidate after update/delete succeeds | Force invalidation regardless of method outcome |

For example, in a price update workflow: **usually use the default**, since you do not want to clear the cache if the request is rejected before altering source data. Still, only judge "evict after is safe" after examining transactions and concurrency in full.

`beforeInvocation=true` can be used for tasks initiating a refresh, proactively clearing derived data before an activity; however, if someone reads right after eviction while the database is not yet updated, they may re-cache the old price. Hence, pre-eviction does not fix race conditions by itself.

### Exceptions and side effects

Suppose a `void` method writes source data partially and then throws an exception:

~~~java
@CacheEvict(cacheNames = "prices", key = "#p0")
public void riskyUpdate(String sku, int price) {
    repository.savePrice(sku, price);
    downstreamService.notifyChange(sku); // may fail
}
~~~

This is an illustrative snippet. If `notifyChange` throws an exception while source data **already saved successfully without rolling back**, default `@CacheEvict` **does not evict** the entry, leading to a stale cache. With a transaction that rolls back consistently, source data can also return to its prior state; that is a different situation. Design transaction boundaries, external calls, and invalidation policies based on the actual scenario.

## 6. Evict one key or the entire cache region?

### Evict one entry: suitable for updating a single object

~~~java
@CacheEvict(cacheNames = "prices", key = "#p0")
public void changePrice(String sku, int price) { /* ... */ }
~~~

For instance, updating `"A"` invalidates only the corresponding cache entry. Entries `"B"` and `"C"` do not need to reload.

### Clear all: allEntries = true

~~~java
@CacheEvict(cacheNames = "prices", allEntries = true)
public void reloadCatalog() {
    repository.reloadAllPrices();
}
~~~

Illustrative snippet; `repository` is undefined. After the method succeeds, Spring asks the cache to clear all entries in the `"prices"` region. With `allEntries=true`, no individual key needs to be computed. Do not combine it with `key` expecting to evict only a few entries: `allEntries` expresses the intent to clear the entire region, not by key.

**Trade-off:** `allEntries=true` is simple, yet it can cause many subsequent requests to miss simultaneously, creating heavy load on the DB or API. Use a specific key when you know the exact affected entry; use full-region clearing when many derived entries change or the affected key set cannot be determined.

## 7. Void eviction, DB transactions, and data consistency

**Distinguish two concepts:**

- **Method completion:** the method body finishes normally without throwing an exception.
- **Transaction commit:** the database actually commits the changes.

`beforeInvocation=false` only speaks to timing relative to **the intercepted method call**; it does not automatically ensure cache removal occurs **after commit** under every AOP/transaction combination. When using `@Transactional`, advice ordering, call paths, and the cache manager can affect timing.

A typical race:

~~~text
T1: Starts updating price A from 100 -> 120 in transaction
T1: Evicts cache entry A while transaction has not committed
T2: Reads A -> cache miss
T2: DB still sees 100 -> cache.put(A, 100)
T1: Successfully commits price 120
T3: Reads A -> cache hit 100 (stale)
~~~

To prevent this, consider **post-commit eviction** when the application needs stronger consistency: use an appropriate transaction-aware cache, transaction synchronization, or publish post-commit events for invalidation. This does not happen automatically merely by adding `@CacheEvict`. In distributed systems, also account for multiple instances, replication, propagation time, and potential cache stampedes.

Also distinguish `@CacheEvict` from `@CachePut`:

| Annotation | Purpose | Skips method body on hit? | Cache action |
| --- | --- | --- | --- |
| `@Cacheable` | Reuse result | Possible | Reads, and stores result on miss |
| `@CachePut` | Run method then store new result | No | Puts return value |
| `@CacheEvict` | Invalidate old result | No | Evicts key or clears cache |

Use `void` with `@CacheEvict` because output does not matter for eviction. If you want to **replace** an entry with new data without waiting for the next read, consider `@CachePut` on a method **returning the value to cache**, or manage the cache explicitly as fits your architecture. Do not assume an annotation can infer a new value from a `void` method.

## 8. Complete Java 17 + Maven demo: void updater causes the next read to miss

This demo runs Spring Framework 6.2.x on Java 17, using `ConcurrentMapCacheManager` for in-memory storage. The `database` map simulates the original data source, and a counter proves whether the getter actually runs or is skipped. Neither Spring Boot nor Redis is required.

### 8.1. Directory structure

~~~text
void-cache-evict/
├── pom.xml
└── src/main/java/demo/VoidEvictDemo.java
~~~

### 8.2. File pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>void-cache-evict</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.10</version>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 8.3. File src/main/java/demo/VoidEvictDemo.java

~~~java
package demo;

import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class VoidEvictDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class AppConfig {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("prices");
        }

        @Bean
        public PriceService priceService() {
            return new PriceService();
        }
    }

    public static class PriceService {
        // Simulates a database: this is the data source, NOT the cache.
        private final Map<String, Integer> database =
                new ConcurrentHashMap<>();
        private final AtomicInteger dbReads = new AtomicInteger();

        public PriceService() {
            database.put("A", 100);
        }

        @Cacheable(cacheNames = "prices", key = "#p0")
        public int getPrice(String sku) {
            Integer price = database.get(sku);
            if (price == null) {
                throw new IllegalArgumentException("Unknown SKU: " + sku);
            }
            int n = dbReads.incrementAndGet();
            System.out.println("DB_READ " + sku + " #" + n + " = " + price);
            return price;
        }

        // void return: Spring uses SKU as the key, NOT the return value.
        @CacheEvict(cacheNames = "prices", key = "#p0")
        public void updatePrice(String sku, int newPrice) {
            database.put(sku, newPrice);
            System.out.println("DB_WRITE " + sku + " = " + newPrice);
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                AppConfig.class)) {
            PriceService service = context.getBean(PriceService.class);
            Cache cache = Objects.requireNonNull(
                    context.getBean(CacheManager.class).getCache("prices"));

            System.out.println(
                    "Before read, cache A? " + (cache.get("A") != null));

            System.out.println("read1 = " + service.getPrice("A"));
            System.out.println("read2 = " + service.getPrice("A"));

            service.updatePrice("A", 120);
            System.out.println(
                    "After update, cache A? " + (cache.get("A") != null));

            System.out.println("read3 = " + service.getPrice("A"));
            System.out.println("read4 = " + service.getPrice("A"));
        }
    }
}
~~~

### 8.4. Running the demo

In the `void-cache-evict` directory, JDK 17+ and Maven are required:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.VoidEvictDemo
~~~

Stdout printed by the program (excluding Maven/environment-specific messages):

~~~text
Before read, cache A? false
DB_READ A #1 = 100
read1 = 100
read2 = 100
DB_WRITE A = 120
After update, cache A? false
DB_READ A #2 = 120
read3 = 120
read4 = 120
~~~

Explanation:

1. Before `read1`, there is no mapping for `"A"`. The getter misses, reads the source once, and stores 100.
2. `read2` hits, so `DB_READ A #2` does not appear at this time.
3. `updatePrice` **returns no result**. The body writes 120, then `@CacheEvict` deletes entry `"A"`. `After update, cache A? false` proves the removal.
4. `read3` misses and loads 120; `dbReads` increments to 2.
5. `read4` hits with 120, with no further `DB_READ`.

Although both the cache and the "database" live in the demo application, they are **two separate objects**. The demo only illustrates the Spring Cache flow accurately; it does not replace verifying real database consistency, Redis, transactions, and multiple nodes.

### 8.5. Why must the bean be obtained from ApplicationContext?

The example intentionally calls:

~~~java
PriceService service = context.getBean(PriceService.class);
service.updatePrice("A", 120);
~~~

This ensures the call passes through the Spring-managed bean and caching proxy. If you write `new PriceService().updatePrice(...)` outside the container, or call `this.updatePrice(...)` from inside the `PriceService` class itself in default proxy mode, the interceptor may not run, so the annotation produces no cache eviction effect. Within the same class, organize calls through another bean/service or redesign the boundary rather than relying on self-invocation.

## 9. A void method does not necessarily have to modify the database

A `void` method can also serve purely as an explicit invalidation action:

~~~java
@CacheEvict(cacheNames = "prices", key = "#p0")
public void invalidatePrice(String sku) {
    // No need to return a value and no need to call Cache.evict() manually.
}
~~~

This is an illustrative snippet. A caller can invoke this method when knowing external data just changed. However, if only clearing the cache is needed, the application can also use `CacheManager`/`Cache` programmatically; the key is choosing a clear boundary and avoiding a "dummy method" called internally where the proxy has no effect.

Another variant, when updating an entire catalog:

~~~java
@CacheEvict(cacheNames = "prices", allEntries = true)
public void importNewPriceList() {
    repository.importPrices();
}
~~~

A `void` method is still accepted; this time the trigger requests clearing **the entire `"prices"` cache**, without identifying individual SKUs. The snippets above are not standalone and must be integrated into a specific service, repository, and Spring configuration.

## 10. Impact of exceptions, cache providers, and runtime environments

### 10.1. If the entry is not found

An `evict("A")` call does not create a new value and does not invoke the getter itself. If entry `"A"` is absent, the operation simply removes any possibility of reusing that entry; only the next read determines hit/miss based on the actual state during lookup.

### 10.2. If the provider fails during evict

Errors from the cache backend (Redis connection loss, permissions, serialization…) are unlike business errors. Spring provides `CacheErrorHandler` to customize reactions when cache operations fail; by default, cache errors may propagate up to the caller. A policy that ignores cache errors can let the API keep running, but you must weigh the risk of **serving stale data** if eviction failed.

### 10.3. If there are multiple instances

`ConcurrentMapCacheManager` in the demo holds data inside the JVM and does not automatically synchronize with other JVMs. If instance A updates the DB and only evicts A's local cache, instance B may still hold the old copy. You can use a shared backend (e.g., Redis), an invalidation broadcast mechanism, or an appropriate TTL design. **Having the same annotation does not mean every instance sees the same eviction result.**

### 10.4. If multiple readers/writers run concurrently

`@CacheEvict` does not automatically create a global synchronization lock between DB writes and cache reads. A reader may load the old price right while the updater has not yet committed. Evaluate transaction boundaries, key strategies, cache providers, and asynchronous update paths when stronger consistency is required.

## 11. Recommended test matrix

| Test case | Steps | Expected result |
| --- | --- | --- |
| Evict exact key | Cache A=100, B=200; call updater for A | Entry A is gone; B stays |
| Missing entry | Cache empty; call updater for A | Method still runs; no entry created by evict |
| Updater succeeds | Cache A=100; DB changes A=120 | Next read of A misses and fetches 120 |
| Updater throws exception, default | Cache A=100; method throws exception | Default eviction does not run |
| `beforeInvocation=true` | Cache A=100; method throws exception | Eviction already occurred before method threw error |
| Key mismatch | Getter key SKU, updater key SKU+price | Fails to evict the exact entry stored by getter |
| Full-region clear | A/B have entries; call `allEntries=true` | Entries in the corresponding cache are removed |
| Internal call bypassing proxy | Method in same class calls `this.updatePrice(...)` | Should not expect `@CacheEvict` advice to run |
| Update before commit | Reader misses while DB transaction is open | Must verify risk of repopulating stale data |

A unit test that merely instantiates objects with `new` cannot test Spring AOP. To test the annotation for real, use a Spring application context and a real cache manager or test double, start beans with `@EnableCaching`, and invoke through the proxy as in the demo. When testing database/Redis integration, set up clean data, verify exact keys/TTLs, and observe real transaction commits.

## 12. Common pitfalls and fixes

**Pitfall: "Because the update method returns void, Spring doesn't know what to evict."** False. The annotation specifies cache name and key; a return value is unnecessary. If the entry still remains after the call, check the key, proxy, eviction timing, and provider.

**Pitfall: "Every update method should use @Cacheable."** False. `@Cacheable` can skip the body on a hit; a business update command must not be skipped. Use `@CacheEvict` for post-update invalidation, or `@CachePut` to put a meaningful result when appropriate.

**Pitfall: "Omitting key is the same as a single-parameter getter."** False if the updater accepts multiple parameters. The default key derives from **the entire parameter list**, which may not match the getter's key. Declare `key="#p0"` when the domain identifies by SKU.

**Pitfall: "beforeInvocation=false means after DB commit."** There is no such general guarantee. It is only after the method is invoked successfully from the cache interceptor's viewpoint. If after-commit semantics are needed, design them explicitly.

**Pitfall: "allEntries=true only evicts the entry of the current parameter."** False. It clears all entries in the declared cache region; avoid using it carelessly under heavy load.

**Pitfall: "Calling this.updatePrice(...) still runs @CacheEvict."** Incorrect in common proxy mode. External calls through the Spring proxy are what get intercepted.

**Pitfall: "Evicting the cache means updating the data."** Eviction **does not change the price in the DB** and **does not store the new price in the cache**. It only prevents reading the old entry again; the next getter call can repopulate it.

## 13. Self-check questions

1. **Why is `void` valid with `@CacheEvict`?** Because the return value is ignored; the method invocation merely triggers entry removal based on cache/key configuration.
2. **Getter has one SKU parameter, updater has SKU and new price: should `key` be omitted on both?** No. The default key generator produces keys with different structures for the two calls; use the same key expression, e.g., `#p0`.
3. **If a void method throws an exception, does default `@CacheEvict` evict?** No, normal post-invocation eviction only runs when the method completes successfully. With `beforeInvocation=true`, eviction occurs before the body runs.
4. **Right after evict, does the cache already hold the new price?** No. Reloading normally occurs when calling the `@Cacheable` getter afterward, or via another population process.
5. **Does `@CacheEvict` automatically synchronize data across multiple instances?** No. It depends on the cache backend, transactions, and how invalidations are distributed.

## Conclusion

A `void` method annotated with `@CacheEvict` is a **cache eviction trigger**, not a function providing new values. The rule for reading the flow is: **run business logic → (by default, on success) evict exact cache/key → next read misses and reloads**. In real-world usage, focus on matching keys between getter/updater, `beforeInvocation`, exceptions, transactions, and multi-instance environments. These are the factors that determine whether eviction truly prevents stale data.

## Official documentation

- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Declarative Annotation-based Caching (`@CacheEvict`, `@Cacheable`, `@CachePut`): https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Javadoc `@CacheEvict`: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/cache/annotation/CacheEvict.html
- Javadoc `Cache` interface: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/cache/Cache.html
