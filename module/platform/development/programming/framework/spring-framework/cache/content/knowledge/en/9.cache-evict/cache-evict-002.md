# @CacheEvict(allEntries = true): clearing an entire cache region in Spring Framework

## 1. Why clear an entire cache region?

Spring Cache reduces query or computation count by storing results by key. However, when the data source changes, old cached copies need to be invalidated.

With `@CacheEvict`, you have two eviction granularities:

- **Single-entry eviction:** by default `allEntries = false`, Spring resolves the cache and key for the invocation and removes the corresponding entry.
- **Clearing all entries of the selected caches:** `allEntries = true`, Spring skips resolving a single key and instructs each target cache region to clear all entries.

Common scenario: after re-importing the entire product catalog or changing a pricing rule table, the system does not know exactly which keys were affected. Clearing the entire relevant cache region is a simple approach so that subsequent reads load fresh data.

```java
@CacheEvict(cacheNames = "products", allEntries = true)
public void importAllProducts() {
    repository.importBatch();
}
```

This is an illustrative method snippet in a service with a suitable `repository`, **not a standalone Java file**. When the method finishes successfully and the call passes through the Spring proxy, Spring requests clearing all entries in the cache named `products`.

**Learning objectives:** accurately understand the scope of `allEntries`, eviction timing (`beforeInvocation`), condition (`condition`), impact on other caches, verify behavior on Java 17+, as well as limitations when used in distributed systems and transactions.

## 2. Eviction scope: what does "all" mean?

### 2.1. Clears all *entries* of the selected caches, not every cache in the application

Suppose a CacheManager has three caches:

```text
CacheManager
├── products
│   ├── "A" -> Product A
│   └── "B" -> Product B
├── productSummary
│   └── "VN" -> Summary
└── users
    └── "u1" -> User
```

With:

```java
@CacheEvict(cacheNames = "products", allEntries = true)
public void reloadCatalog() { /* update data source */ }
```

After a successful call through the proxy, **only entries in the `products` region are requested to be cleared**. The `productSummary` and `users` caches are not touched by this annotation, even though they may contain data dependent on the old catalog.

If both related regions need to be cleared:

```java
@CacheEvict(
    cacheNames = {"products", "productSummary"},
    allEntries = true
)
public void reloadCatalog() { /* update data source */ }
```

With a custom `CacheResolver`, the actual list of caches returned by the resolver must be clearly understood. In simple configurations, `cacheNames` specifies the exact caches to process.

**Do not confuse:** `allEntries=true` does not delete the `CacheManager` bean, does not delete cache definitions/instances, and **does not delete original data** in the database. It issues a command to clear entries in the relevant cache regions; subsequent `@Cacheable` calls will experience cache misses and reload values if the provider has completed clearing.

### 2.2. No key needed — and must not be combined with `key`

When clearing an entire region, the `key` parameter has no meaning. The `@CacheEvict` Javadoc in Spring Framework 6.x explicitly states: configuring `allEntries=true` together with `key()` is **invalid**. Omit the `key` attribute rather than hoping Spring merely ignores that expression.

```java
// CORRECT: clear every entry of the "products" cache.
@CacheEvict(cacheNames = "products", allEntries = true)
public void resetAll() { }

// CORRECT: remove a specific entry (default allEntries=false).
@CacheEvict(cacheNames = "products", key = "#p0")
public void resetOne(String sku) { }

// WRONG: key must not be combined with allEntries=true.
// @CacheEvict(cacheNames = "products", allEntries = true, key = "#p0")
// public void invalidConfiguration(String sku) { }
```

This is a code snippet illustrating methods placed in a service. The invalid configuration is commented out to avoid mistaking it for runnable example code. Do not use `allEntries=true` to delete "all keys of one tenant" in a shared cache: this operation clears the **entire region**, including other tenants if they share the same region.

### 2.3. Comparing single-entry vs. full-region eviction

| Criterion | Default `@CacheEvict` | `@CacheEvict(allEntries=true)` |
| --- | --- | --- |
| Eviction target | Entry matching the generated key | All entries in the selected cache(s) |
| Uses `key`/`keyGenerator`? | Yes, when key selection is needed | Does not use a single key; do not specify `key` |
| Effect on other caches | None, unless also selected | None, unless also selected |
| Best suited for | One product, one user, one specific record | Bulk imports, wide-reaching rule changes |
| Post-eviction cost | Few entries must reload | May cause many cache misses and load spikes |
| Tenant partitioning | Can use tenant-prefixed keys | Must separate cache regions if only clearing a dedicated region |

**Rule of thumb:** choose the smallest eviction scope that remains correct. Clearing broadly "just to be safe" often degrades cache efficiency and can trigger concurrent load bursts on the database.

## 3. Eviction timing: `beforeInvocation` and method failures

Default:

```java
@CacheEvict(cacheNames = "products", allEntries = true)
public void reload() { /* modify data */ }
```

Equivalent to `beforeInvocation=false`. Spring performs eviction **after the method is invoked successfully**. If the method throws an exception, post-invocation cache eviction does not happen.

Conversely:

```java
@CacheEvict(
    cacheNames = "products",
    allEntries = true,
    beforeInvocation = true
)
public void reload() { /* may throw exception */ }
```

Spring performs eviction **before executing the method**. Therefore, the cache may already be cleared even if the method subsequently fails. `@CacheEvict` does not skip the method and can be applied to `void` methods because the annotation's purpose is to trigger an eviction operation.

| Case | `beforeInvocation=false` (default) | `beforeInvocation=true` |
| --- | --- | --- |
| Method completes normally | Clears after method | Clears before method |
| Method throws exception | Does not perform post-method eviction | Clear was already requested before method, regardless of outcome |
| Stale cache visible while method runs | Possible, since not cleared yet | In a simple synchronous provider, cache is already cleared before body runs |
| Best suited for | Clearing old data after a successful update | Proactively invalidating before a task, even if the task fails |

**Important boundary:** "after the method succeeds" does not mean "after all related database transactions have committed" under every AOP/transaction configuration. Coordination with `@Transactional`, transaction-aware cache managers, commit/rollback, and the cache backend must be designed and verified separately.

### 3.1. Execution flow

```text
@CacheEvict(allEntries=true, beforeInvocation=false)

Client -> Spring proxy -> invoke method -> [succeeded?]
                                         |
                                       yes -> Cache.clear() -> return
                                         |
                                        no -> exception, no post-method eviction

@CacheEvict(allEntries=true, beforeInvocation=true)

Client -> Spring proxy -> Cache.clear() -> invoke method -> return/exception
```

The diagram shows the logical flow of the cache interceptor in a synchronous context; providers supporting deferred/async clear may not make every entry disappear immediately at the moment the clear operation is called.

## 4. Complete Java 17+ example: multiple keys, multiple regions, conditions, and failures

The example runs without a web server or Redis. It uses Spring Framework Cache via `spring-boot-starter-cache` (Spring Boot BOM 3.3.13), `ConcurrentMapCacheManager` as the in-memory cache, and a counter to observe when the method body actually executes.

Create the directory tree:

```text
cache-evict-all-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/evict/EvictAllDemo.java
```

Contents of `settings.gradle`:

```groovy
rootProject.name = 'cache-evict-all-demo'
```

Contents of `build.gradle`:

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
    mainClass = 'demo.evict.EvictAllDemo'
}
```

Contents of `src/main/java/demo/evict/EvictAllDemo.java`:

```java
package demo.evict;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class EvictAllDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class CacheConfig {
        @Bean
        CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("products", "reference");
        }

        @Bean
        CatalogService catalogService() {
            return new CatalogService();
        }
    }

    public static class CatalogService {
        private final AtomicInteger productLoads = new AtomicInteger();
        private final AtomicInteger referenceLoads = new AtomicInteger();

        @Cacheable(cacheNames = "products")
        public String product(String sku) {
            return sku + "-load-" + productLoads.incrementAndGet();
        }

        @Cacheable(cacheNames = "reference")
        public String reference(String code) {
            return code + "-ref-" + referenceLoads.incrementAndGet();
        }

        // Only clear when enabled=true. The method still runs in both cases.
        @CacheEvict(cacheNames = "products", allEntries = true,
                    condition = "#p0")
        public void clearIf(boolean enabled) {
            // No data operation needed for this simulation.
        }

        // By default, clears after the method runs successfully.
        @CacheEvict(cacheNames = "products", allEntries = true)
        public void clearAfter(boolean fail) {
            if (fail) {
                throw new IllegalStateException("simulated failure");
            }
        }

        // Clears before the method runs, even if the method throws an exception.
        @CacheEvict(cacheNames = "products", allEntries = true,
                    beforeInvocation = true)
        public void clearBefore(boolean fail) {
            if (fail) {
                throw new IllegalStateException("simulated failure");
            }
        }

        public int productExecutions() {
            return productLoads.get();
        }

        public int referenceExecutions() {
            return referenceLoads.get();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(CacheConfig.class)) {
            CatalogService service = context.getBean(CatalogService.class);

            System.out.println("A first: " + service.product("A"));
            System.out.println("B first: " + service.product("B"));
            System.out.println("A hit: " + service.product("A"));
            System.out.println("ref first: " + service.reference("R"));

            service.clearIf(false);
            System.out.println("condition false: " + service.product("B"));

            try {
                service.clearAfter(true);
            } catch (IllegalStateException e) {
                System.out.println("after error: " + e.getMessage());
            }
            System.out.println("after error A: " + service.product("A"));

            service.clearIf(true);
            System.out.println("after clear A: " + service.product("A"));
            System.out.println("after clear B: " + service.product("B"));
            System.out.println("ref still: " + service.reference("R"));

            try {
                service.clearBefore(true);
            } catch (IllegalStateException e) {
                System.out.println("before error: " + e.getMessage());
            }
            System.out.println("after before-error A: " + service.product("A"));

            service.clearAfter(false);
            System.out.println("after success B: " + service.product("B"));
            System.out.println("product executions: " + service.productExecutions());
            System.out.println("reference executions: " + service.referenceExecutions());
        }
    }
}
```

Run with JDK 17+ and a Java 17-compatible Gradle version:

```bash
gradle run --quiet
```

If using the Gradle Wrapper, use `./gradlew run --quiet` (Windows: `gradlew.bat run --quiet`). Expected lines printed by the program, excluding build/framework logs:

```text
A first: A-load-1
B first: B-load-2
A hit: A-load-1
ref first: R-ref-1
condition false: B-load-2
after error: simulated failure
after error A: A-load-1
after clear A: A-load-3
after clear B: B-load-4
ref still: R-ref-1
before error: simulated failure
after before-error A: A-load-5
after success B: B-load-6
product executions: 6
reference executions: 1
```

Reading the output stage by stage:

1. `product("A")` and `product("B")` populate two keys in the `products` cache, so `A hit` returns `A-load-1` without incrementing the counter.
2. `reference("R")` resides in **another cache**. It runs only once throughout the entire demo.
3. `clearIf(false)` has `condition=false`, so it does not clear; key `"B"` still hits.
4. `clearAfter(true)` throws an exception; because `beforeInvocation=false`, it does not clear; key `"A"` still hits.
5. `clearIf(true)` clears **the entire `products` region**: afterward *both A and B* miss, incrementing the counter to 3 and 4. The `reference` cache keeps its old entry.
6. `clearBefore(true)` clears first and only then throws the exception; `product("A")` subsequently misses, incrementing to 5.
7. `clearAfter(false)` completes successfully and then clears; `product("B")` must recompute, incrementing to 6. The totals across both caches show that eviction scope and timing are independent.

**Why must the bean be retrieved from the Spring context?** `@EnableCaching` activates caching infrastructure for Spring-managed beans. In the default proxy mode, external calls through the bean returned by `context.getBean(...)` trigger `@Cacheable` and `@CacheEvict`. Calling `new CatalogService()` or internal self-calls like `this.clearAfter(...)` may bypass the advice and cause the demo to produce different results.

**Limitations of the example:** `ConcurrentMapCacheManager` is suitable for hands-on practice, and `clear()` on a synchronous in-memory cache is enough to illustrate hit/miss behavior. It does not represent latency or consistency on Redis, Hazelcast, multiple JVMs, or transactional cache decorators.

## 5. `condition` with allEntries: clearing only when a condition holds

You can place a SpEL condition on a full-region clear operation:

```java
@CacheEvict(
    cacheNames = "reports",
    allEntries = true,
    condition = "#p0"
)
public void rebuildReports(boolean shouldInvalidate) {
    // Update data or generate reports.
}
```

This is an illustrative method, using `#p0` to retrieve the first boolean argument. When `shouldInvalidate=false`, the method **still runs**, but the annotation's cache clear is not performed; when true, Spring performs the clear at the configured pre/post-method timing. `condition` decides **whether to perform the cache operation**, not whether the method runs.

Do not use `condition` to skip clearing when code actually modified data but a flag was wrong. For update flows, always prioritize ensuring any relevant change properly invalidates the cache region.

Some configurations have `condition` based on `#p0.type`, `#root.args[1]`, or environment variables; keep conditions clear, null-safe, and tested. If a condition depends on a variable that can differ across systems, clearing behavior may become inconsistent.

## 6. Combining with other cache operations

### 6.1. When is clearing the whole region reasonable?

- **Bulk imports:** the data source changes for many keys and it is hard to know every affected key.
- **Changing shared calculation rules:** for example, changing a pricing/rate table invalidates a large batch of entries.
- **Refreshing a derived data region:** the cache holds aggregates computed from many records; updating part of the source can affect many entries.
- **Resetting after data synchronization:** related entries need refreshing rather than trying to count/evict individual keys.

### 6.2. When should it be avoided?

If only one product changes and the key is known, use key-based eviction:

```java
@CacheEvict(cacheNames = "products", key = "#p0")
public void deleteProduct(String sku) {
    repository.delete(sku);
}
```

This is an illustrative method depending on the application's repository. Clearing the entire region for every small update can reduce hit rates, increase database load, and create a **cache stampede** when many requests reload data at once.

If the cache holds data for multiple tenants, `allEntries=true` with `cacheNames="products"` sweeps the entire region without understanding a specific tenant. Use separate cache regions per tenant, deliberate namespacing, or provider-supported key/tag eviction strategies if narrower scope is needed.

### 6.3. Multiple caches depending on the same source

Suppose a business has `products` and `productSummary` both depending on the product table. Clearing only `products` leaves `productSummary` at risk of becoming stale. You can clear both via the `cacheNames` array in the same operation as in section 2, or use `@Caching(evict = {...})` when each region needs its own condition/key/beforeInvocation:

```java
@Caching(evict = {
    @CacheEvict(cacheNames = "products", allEntries = true),
    @CacheEvict(cacheNames = "productSummary", allEntries = true)
})
public void reload() { /* import data source */ }
```

This snippet is only an illustrative method and requires importing `@Caching` and project classes. If all caches share the same timing and condition, `cacheNames = {"products", "productSummary"}` is more concise.

**Do not assume all regions are cleared atomically together.** Spring's cache abstraction does not provide a distributed transaction spanning multiple cache backends. If clearing the first region succeeds and another fails, appropriate retry, observability, or data consistency strategies are required.

## 7. Consistency and transactions in practice

### 7.1. "Clear" does not always mean "every subsequent request immediately sees no data"

At the API level, `@CacheEvict(allEntries=true)` sends a request to clear the cache. The `org.springframework.cache.Cache.clear()` Javadoc allows the actual clear operation to be performed **asynchronously or deferred** by the provider/decorator. In that case, a lookup near the clear time may temporarily see old entries.

Specifically:
- Transaction-aware cache decorators may defer write/evict/clear until commit time.
- Distributed caches may take time to propagate state or synchronize across nodes.
- An in-flight request computing old data **may write the old entry back** after the clear operation if there is no coordination mechanism.

Therefore, `allEntries=true` is **not a guarantee of immediate consistency across every backend**. If a system needs a clear expecting entries to be immediately invisible to the next lookup, the Spring Cache API provides `Cache.invalidate()` with stronger semantics; however, `@CacheEvict` does not provide an attribute to switch directly from `clear()` to `invalidate()`. Check your provider and design consistency at the appropriate level.

### 7.2. Not automatically synchronized with database transactions

`@CacheEvict(beforeInvocation=false)` runs after the method returns successfully from the cache advice's perspective, **without automatically guaranteeing the database has committed** under every advice ordering.

Options depending on needs:
- Use a transaction-aware cache manager/decorator when appropriate, then verify exactly how `clear()` is synchronized with commit.
- Publish post-commit events (e.g., handled at `TransactionPhase.AFTER_COMMIT`) to invalidate after a successful transaction when the architecture requires it.
- For multi-service systems, use events/outbox and retry/reconciliation mechanisms if invalidation must not be lost.
- When clearing a very large cache, consider versioned namespaces or provider-supported strategies instead of bulk physical deletion.

Choose the solution by consistency SLA: caches for recommendation statistics can tolerate brief staleness; pricing, inventory, and authorization data require tighter guarantees. In particular, **never use cache invalidation as the sole access-control mechanism**.

### 7.3. Clearing the entire region does not change original data

Suppose a method already cleared the cache, but the database import fails midway. With `beforeInvocation=true`, the cache lost its entries while the source data may remain un-updated. The next read will load from a source that is still old or incomplete. Choose eviction timing based on the nature of the task, not merely on a desire to "always clear".

## 8. Common errors and diagnostics

| Symptom | Cause | How to handle |
| --- | --- | --- |
| `allEntries=true` yet some keys still hit | Advice did not run, cache resolver picked another cache, provider clear is delayed, or concurrent request re-cached | Check Spring proxy, cacheNames/cacheResolver, provider, and race conditions |
| Clears other users' data too | Multiple tenants share one region and `allEntries` is cleared | Separate regions/namespaces or narrow eviction scope |
| Startup error when `key` is present | Invalid combination of `allEntries=true` with `key()` | Remove the `key` attribute |
| Method fails yet cache is cleared | `beforeInvocation=true` | Choose appropriate timing |
| Method fails and cache is not cleared | `beforeInvocation=false`, which is the default | Check business design before/after errors |
| Method runs yet no eviction happens | `condition=false`, call bypasses proxy, or wrong cache | Test condition, method visibility, actual instance |
| Cleared `products` cache yet `summary` is stale | Forgot dependent cache | Clear all related regions |
| Frequent cache misses after small batch updates | Clearing too broadly too often | Evict by key or reorganize cache regions |
| Just cleared yet data is still stale | Deferred clear, transaction not committed, or race with in-flight request | Check commit timing, provider, and coordination strategy |
| Cache name does not exist | Static CacheManager did not create that cache or resolver did not return it | Check cache names list / CacheManager |

When diagnosing, separate four steps: **whether the call passes through the Spring proxy**, **which cache regions the operation selects**, **whether eviction is triggered before/after the method or skipped by condition**, and **whether the cache backend has actually reflected the clear**.

## 9. Implementation, testing, and operations checklist

Before deploying `allEntries=true` to production:

1. Confirm **the cache regions** affected. Check regions depending on the same data source, not only the region named like the method.
2. Analyze **change granularity**: if an entity's key is known, prefer `@CacheEvict(key=...)` to avoid unnecessary invalidation.
3. Verify `beforeInvocation` according to business logic. If clearing after commit is required, address transaction timing instead of assuming `beforeInvocation=false` provides that guarantee itself.
4. Ensure the annotated method is **Spring-managed** and called through the proxy, not via self-invocation.
5. Evaluate `condition`: when false, the method still runs without evicting. Test both true/false and exception cases.
6. Populate cache entries for **at least two different keys**, invoke the clear method, then verify both keys miss and must recompute.
7. Place an entry in **another cache** and confirm it is not unintentionally cleared.
8. With distributed providers, test visibility, latency, concurrency, and transactional clear operations; do not extrapolate from `ConcurrentMapCacheManager`.
9. Measure hit/miss ratio, database load, and latency spikes after clear; consider paced warm-up instead of reloading every key simultaneously.
10. Set up logging/metrics for wide-scope invalidation operations, as they have major impact on system performance and correctness.

In Spring Boot, the configuration example in section 4 enables caching itself via `@EnableCaching`. In a real Boot application, cache configuration must reside in the `ApplicationContext` containing the corresponding service beans; having a `CacheManager` does not replace `@EnableCaching`. If there are multiple `CacheManager`/`CacheResolver` beans, specify which manager the operation uses.

Small test case, logically:

```text
Given: cache products has key A and key B, cache reference has key R.
When : @CacheEvict(cacheNames="products", allEntries=true) is called successfully via proxy.
Then : A and B are no longer returned from cache products per provider semantics;
       cache reference still has R.
And  : new reads for A/B go to the source and can re-populate entries.
```

Do not rely on tests that only check the method return or entry count of a single isolated cache if the goal is verifying dependent regions. Test source data, execution counts, region names, keys, and transactional consistency.

## 10. Self-check questions

**Q1.** There are two entries `"A"` and `"B"` in the `products` cache. What entries will a successful `@CacheEvict(cacheNames="products", allEntries=true)` call remove?

**Answer:** Spring requests clearing **both A and B** from the `products` cache; no specific key is used. Other cache regions are not touched by this operation.

**Q2.** Does `allEntries=true` clear every cache in the `CacheManager`?

**Answer:** No. It clears all entries of the **cache(s) selected by the operation**, usually via `cacheNames` or `CacheResolver`. Unselected regions keep their entries.

**Q3.** Should `allEntries=true` be paired with `key="#p0"`?

**Answer:** No. The `@CacheEvict` Javadoc specifies this combination is invalid. When clearing an entire region, `key` has no role.

**Q4.** When a method throws an exception, when can the cache still already be cleared?

**Answer:** With `beforeInvocation=true`, eviction is requested before the method; an exception does not undo that operation. With `beforeInvocation=false`, Spring performs post-invocation eviction only when the method completes successfully.

**Q5.** When `condition=false` on `@CacheEvict`, is the method skipped?

**Answer:** No. The condition only controls the cache operation; the method still executes.

**Q6.** Why do stale entries sometimes still appear right after a clear?

**Answer:** The provider may perform deferred/async clearing; transactions or concurrently running requests also affect visibility. Verify against the actual backend.

## 11. Takeaways

- `@CacheEvict(allEntries=true)` **clears every entry of each selected cache**, not all cache regions of the application.
- When clearing an entire region, **do not declare `key`**; use `cacheNames`/`cacheResolver` to select caches.
- `beforeInvocation=false` (default) clears after success; `true` requests clearing before the method even if it later fails.
- `condition` can control eviction but **does not prevent the method from running**.
- Clearing does not automatically guarantee immediate transactional synchronization/visibility across every backend; monitor provider behavior, concurrency, and performance impact.

### Official documentation

- [Spring Framework – Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework 6.1 – @CacheEvict Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/cache/annotation/CacheEvict.html)
- [Spring Framework – Cache interface Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/Cache.html)
- [Spring Framework – Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Boot – Caching](https://docs.spring.io/spring-boot/reference/io/caching.html)
