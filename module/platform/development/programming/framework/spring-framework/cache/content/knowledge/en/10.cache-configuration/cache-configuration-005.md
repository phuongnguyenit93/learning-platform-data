# Separate Conditions and Keys for Operations Grouped with @Caching

## 1. Context and Goal

When a single business operation affects multiple cache regions, not every region shares the same **key** and **applicability condition**. For example, when updating a product: the `productById` cache needs to evict the entry by product ID, whereas the `regionSummary` cache only needs to evict by region code if that change actually impacts regional aggregate numbers. Both actions can sit on the same business method, yet you must not mistakenly share one key or one condition across them.

In Spring Framework, `@Caching` is a **grouping annotation** for multiple `@Cacheable`, `@CachePut`, and `@CacheEvict` annotations on one method. Each nested annotation can declare its own `cacheNames`, `key` or `keyGenerator`, `condition`, and valid specific attributes.

A short example:

```java
@Caching(evict = {
    @CacheEvict(cacheNames = "productById",
                key = "#p0",
                condition = "#p0 != null"),
    @CacheEvict(cacheNames = "regionSummary",
                key = "#p1",
                condition = "#p2")
})
public void update(String productId, String region, boolean affectsRegion) {
    repository.update(productId, region);
}
```

The snippet above illustrates a service method with `repository`, not a standalone runnable Java file. With `update("P1", "VN", false)`, the first operation can evict the `productById["P1"]` entry, while the second operation does not evict `regionSummary["VN"]`. **Each operation's condition is evaluated independently**; a false condition on one nested operation does not cancel the other operations.

Lesson goal: master the grouping mechanism, independent key/condition structure, avoiding pitfalls with `@Cacheable`/`@CachePut`, understanding the relationship with `@CacheConfig`, and verifying via a Java 17+ program.

## 2. Syntax and Scope of @Caching

`@Caching` contains three cache operation groups:

| Attribute | Nested Elements | Primary Effect |
| --- | --- | --- |
| `cacheable = { ... }` | `@Cacheable` | Can retrieve result from cache; on hit, method may not execute |
| `put = { ... }` | `@CachePut` | Method executes to obtain result, then updates the appropriate cache |
| `evict = { ... }` | `@CacheEvict` | Evicts entry by key or clears the selected cache |

Example declaring two evictions:

```java
@Caching(evict = {
    @CacheEvict(cacheNames = "byId", key = "#p0"),
    @CacheEvict(cacheNames = "byRegion", key = "#p1",
                condition = "#p2")
})
public void modify(String id, String region, boolean regionChanged) {
    // Update data source.
}
```

Unlike `@CacheEvict(cacheNames={"byId","byRegion"}, key="#p0")`, each nested annotation here has **its own key**. If two regions use different key types or decide eviction based on different conditions, grouping multiple operations is clearer than passing an array of cache names on a single operation.

Distinguish clearly:
- **`@Caching` only groups metadata**; it does not create caches, does not enable annotation processing, and has no shared `condition` or `key` attribute on the container annotation.
- **`@EnableCaching`** turns on cache annotation processing in the `ApplicationContext` containing the beans to intercept.
- **`CacheManager`** provides the actual cache regions. `cacheNames` chooses the region; `key` chooses the entry.
- **`@CacheConfig`** can set certain class-level defaults; nested operations still have the right to override applicable fields individually.

Do not confuse "grouped together in @Caching" with "all actions executing in an atomic transaction."

## 3. Conditions and Keys Are Evaluated Independently

Consider two operations:

```java
@Caching(evict = {
    @CacheEvict(
        cacheNames = "productById",
        key = "#p0",
        condition = "#p0 != null && !#p0.isBlank()"
    ),
    @CacheEvict(
        cacheNames = "regionSummary",
        key = "#p1",
        condition = "#p2 && #p1 != null && !#p1.isBlank()"
    )
})
public void modify(String productId, String region, boolean regionAffected) {
    // Mutate data.
}
```

When calling `modify("P1", "VN", false)`:

1. `#p0` is `"P1"`, so the `productById` operation satisfies its condition and uses key `"P1"`.
2. `#p1` is `"VN"` but `#p2=false`, so the `regionSummary` operation skips eviction.
3. The method still executes. `condition` on `@CacheEvict` decides **whether to evict the cache**, not whether business logic runs.

When calling `modify("P1","VN",true)`, both operations can evict their respective entries. Using `#p0` in the first annotation does not interfere with `#p1` in the second annotation.

### 3.1. SpEL expressions and parameter indices

| Expression | Meaning |
| --- | --- |
| `#p0` or `#a0` | First parameter |
| `#p1` or `#a1` | Second parameter |
| `#p2` or `#a2` | Third parameter |
| `#root.args[0]` | First element in arguments array |
| `#root.methodName` | Name of the current method |
| `#result` | Method result, only in contexts after the result is available |

Prefer `#p0`/`#p1` syntax when unsure whether Java parameter names are preserved via `-parameters`. Use short-circuit guards like `#p1 != null && !#p1.isBlank()` to avoid invoking methods on null.

**Note on `#result`:** With `@Cacheable`, `condition` decides lookup **before the method runs**, so it cannot reference the not-yet-existing result. `unless` on `@Cacheable` is evaluated after the method produces a result. With `@CachePut`, key/condition expressions can use the post-invocation result where context supports it. `@CacheEvict(beforeInvocation=true)` cannot use the method result in the pre-invocation step.

### 3.2. Keys must match the read methods

Suppose:

```java
@Cacheable(cacheNames = "productById", key = "#p0")
public Product getProduct(String productId) {
    return repository.findProduct(productId);
}

@Cacheable(cacheNames = "regionSummary", key = "#p0")
public Summary getSummary(String region) {
    return repository.findSummary(region);
}
```

The snippet above only illustrates a service with its corresponding repository/types. Both read methods use `#p0` because each method takes one parameter; the update method takes three parameters and thus must evict by `#p0` (ID) **and** `#p1` (region) respectively. If region eviction used `key="#p0"`, Spring would mistakenly delete key `"P1"` from the region cache, leaving the potentially stale `"VN"` entry behind.

Do not add conditions merely for premature optimization. For instance, if an update changed regional data while passing `regionAffected=false`, the summary cache becomes stale. Conditions must accurately reflect business logic.

## 4. Runnable Java 17+ Example: Two Regions and Two Keys

The program uses `ConcurrentMapCacheManager`, in-memory data, and two counters to clearly observe cache hits/misses. To accurately demonstrate `condition`, when `regionAffected=false`, the method only increments the product version; when true, it also increments the regional summary version.

Structure:

```text
grouped-cache-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/grouped/GroupedCacheDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'grouped-cache-demo'
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
    mainClass = 'demo.grouped.GroupedCacheDemo'
}
```

`src/main/java/demo/grouped/GroupedCacheDemo.java` (a complete single Java file):

```java
package demo.grouped;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Caching;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class GroupedCacheDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class CacheConfig {
        @Bean
        CacheManager cacheManager() {
            return new ConcurrentMapCacheManager(
                    "productById", "regionSummary");
        }

        @Bean
        CatalogService catalogService() {
            return new CatalogService();
        }
    }

    public static class CatalogService {
        private final Map<String, Integer> productVersions =
                new ConcurrentHashMap<>();
        private final Map<String, Integer> regionVersions =
                new ConcurrentHashMap<>();
        private final AtomicInteger productLoads = new AtomicInteger();
        private final AtomicInteger regionLoads = new AtomicInteger();

        @Cacheable(cacheNames = "productById", key = "#p0")
        public String product(String id) {
            int v = productVersions.getOrDefault(id, 0);
            return id + "-v" + v
                    + "-load" + productLoads.incrementAndGet();
        }

        @Cacheable(cacheNames = "regionSummary", key = "#p0")
        public String summary(String region) {
            int v = regionVersions.getOrDefault(region, 0);
            return region + "-v" + v
                    + "-load" + regionLoads.incrementAndGet();
        }

        @Caching(evict = {
            @CacheEvict(
                cacheNames = "productById",
                key = "#p0",
                condition = "#p0 != null && !#p0.isBlank()"
            ),
            @CacheEvict(
                cacheNames = "regionSummary",
                key = "#p1",
                condition = "#p2 && #p1 != null && !#p1.isBlank()"
            )
        })
        public void modify(String id, String region,
                           boolean regionAffected) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("id is required");
            }
            if (regionAffected && (region == null || region.isBlank())) {
                throw new IllegalArgumentException("region is required");
            }

            productVersions.merge(id, 1, Integer::sum);
            if (regionAffected) {
                regionVersions.merge(region, 1, Integer::sum);
            }
        }

        public String counts() {
            return productLoads.get() + "/" + regionLoads.get();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(CacheConfig.class)) {

            CatalogService service = context.getBean(CatalogService.class);

            System.out.println("id-first=" + service.product("P1"));
            System.out.println("id-hit=" + service.product("P1"));
            System.out.println("region-first=" + service.summary("VN"));
            System.out.println("region-hit=" + service.summary("VN"));

            // Modify only product. Region unchanged, so do not evict region.
            service.modify("P1", "VN", false);
            System.out.println("id-after-one=" + service.product("P1"));
            System.out.println("region-after-one=" + service.summary("VN"));

            // Change both product and regional statistics.
            service.modify("P1", "VN", true);
            System.out.println("id-after-two=" + service.product("P1"));
            System.out.println("region-after-two=" + service.summary("VN"));

            System.out.println("loads=" + service.counts());
        }
    }
}
```

Run from the project directory with JDK 17+ and Gradle:

```bash
gradle run --quiet
```

Or `./gradlew run --quiet` if a Gradle Wrapper is present; Windows: `gradlew.bat run --quiet`. The lines printed by the program itself (excluding library/build startup logs) are:

```text
id-first=P1-v0-load1
id-hit=P1-v0-load1
region-first=VN-v0-load1
region-hit=VN-v0-load1
id-after-one=P1-v1-load2
region-after-one=VN-v0-load1
id-after-two=P1-v2-load3
region-after-two=VN-v1-load2
loads=3/2
```

**Call-by-call explanation:**
1. Two calls to `product("P1")` share the same key, so the second hits and `productLoads` is only 1. Likewise, `summary("VN")` loads only once.
2. `modify("P1","VN",false)` increments the product version from 0 to 1. The `productById` operation evicts key `P1`; the `regionSummary` operation has a false condition and keeps key `VN`. Because regional data did not change, the hit on the region cache remains valid.
3. `modify("P1","VN",true)` increments versions of both sources; both operations evict. Both subsequent reads miss and load the new values.
4. `loads=3/2` shows three executions of `product` and two executions of `summary` across the entire run.

**Conditions for annotations to take effect:** `@EnableCaching` is registered in the proper context, the service is a Spring bean, and calls pass through the proxy (here retrieved via `context.getBean(...)`). Calling `new CatalogService()` or `this.modify(...)` inside the same target does not apply cache advice in default proxy mode. The example is a simplified model and does not replace real transactions or data synchronization mechanisms.

## 5. Grouping @CachePut: Two Writes, Two Keys/Conditions

When one method result needs to update multiple cache regions with **two key forms**, use `@Caching(put={...})`:

```java
@Caching(put = {
    @CachePut(cacheNames = "articleById", key = "#p0",
              condition = "#p2"),
    @CachePut(cacheNames = "articleBySlug", key = "#p1",
              condition = "#p3")
})
public Article save(String id, String slug,
                    boolean refreshId, boolean refreshSlug) {
    return repository.save(id, slug);
}
```

This is an illustrative snippet inside a service with suitable `Article` and `repository`. `@CachePut` **always lets the method execute**. Once the result is available, the operations whose conditions pass can write the same return value under the keys:
- `articleById[id]` when `refreshId=true`;
- `articleBySlug[slug]` when `refreshSlug=true`.

One `condition=false` does not stop the remaining operation. If both flags are false, the method still runs without any puts from these two annotations.

When saving a record that changes `slug` from old to new, putting under the new slug key **does not automatically delete the old key**. You must add appropriate eviction or redesign the cache key to avoid leftover stale data. For results that can be null, consider `unless="#result == null"` to veto cache puts as needed.

## 6. Grouping @Cacheable: Mutually Exclusive Conditions

Multiple `@Cacheable` annotations can be used if each branch serves a different read mode:

```java
@Caching(cacheable = {
    @Cacheable(cacheNames = "lookupById",
               key = "#p0", condition = "#p1 == 'ID'"),
    @Cacheable(cacheNames = "lookupByAlias",
               key = "#p0", condition = "#p1 == 'ALIAS'")
})
public Item lookup(String value, String mode) {
    return repository.lookup(value, mode);
}
```

This is an illustrative snippet; the `Item` type and repository belong to the application. Mode `ID` uses the first region, `ALIAS` uses the second. Because the two conditions are mutually exclusive, region selection is predictable. Any other mode makes both conditions false, so the method runs without using either cache.

**If multiple `@Cacheable` annotations satisfy their conditions simultaneously**, those operations can all participate in lookup/caching. Do not rely on ordering inside `@Caching` to pick the "right" region when the two regions hold different data. If you simply want to check multiple regions with **one key/condition**, sometimes a single `@Cacheable(cacheNames={"cacheA","cacheB"},key="#p0")` is clearer.

**Specifically avoid mixing `@Cacheable` and `@CachePut` on the same method:** Cacheable can skip the method on a hit, while CachePut needs the method to run. Spring Framework advises against combining them unless the conditions are guaranteed mutually exclusive **before invocation**; do not try to use `#result` in `condition` to resolve this conflict.

## 7. @CacheConfig is Default Configuration, Not an Operation Group

`@CacheConfig` is used to avoid repeating certain class-level attributes, including `cacheNames`, `keyGenerator`, `cacheManager`, and `cacheResolver`. It does not create a shared `condition` rule and does not automatically enable `@Caching`.

```java
@CacheConfig(cacheNames = "products")
@Service
public class ProductService {

    @Cacheable(key = "#p0")
    public Product find(String id) {
        return repository.find(id);
    }

    @Caching(evict = {
        @CacheEvict(key = "#p0"),
        @CacheEvict(cacheNames = "regionSummary",
                    key = "#p1", condition = "#p2")
    })
    public void update(String id, String region, boolean affected) {
        repository.update(id, region);
    }
}
```

This snippet illustrates service structure; real classes, imports, and repository are needed. The `@CacheEvict(key="#p0")` operation inherits `cacheNames="products"` from `@CacheConfig`, while the second operation specifies `cacheNames="regionSummary"` to override the default **only for itself**. Keys remain distinct.

The precedence rule is **operation-level > class-level > global configuration** for the supported attributes. Do not mistakenly assume every operation in `@Caching` must use the same key merely because they share `@CacheConfig`.

## 8. Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Evicted region yet key still hits | Write method parameters differ in position from read method | Compare actual cache names and keys, fix `#p0`/`#p1` |
| One region evicted, the other not | Second operation's `condition` is false or nested annotation missing | Test true/false branches separately |
| Condition true but no proxy interception | Wrong `ApplicationContext`, self-invocation, or `new` object | Call via Spring bean and enable `@EnableCaching` in the right place |
| Meant to delete one key but entire region wiped | Overly broad `allEntries=true` | Use explicit keys, separate caches by tenant/need |
| Error when declaring both `key` and `keyGenerator` | Two mutually exclusive attributes on one operation | Pick exactly one key generation strategy |
| Old key still present after changing slug | `@CachePut` only writes the new key | Evict the corresponding old key |
| Method skipped despite intending to update cache | Improperly mixing `@Cacheable` and `@CachePut` | Separate read/write, or use safely exclusive conditions |
| Unexpected eviction when method throws exception | Misunderstanding `beforeInvocation` | Default false deletes after method succeeds; true deletes before |
| Data updated yet cache still stale | Missing dependent region or transaction/provider delay | Build post-commit invalidation strategy, test backend |
| Data returned to wrong tenant | Cache key lacks tenant scope | Require proper key/region and security checks, do not rely on condition |

### 8.1. Each @CacheEvict has its own beforeInvocation

`@CacheEvict(beforeInvocation=false)` (default) performs eviction only after the method completes successfully; `beforeInvocation=true` instructs clearing before the method runs, even if an error later occurs. If two operations in a group have different values, they can run in **two different phases**. Do not assume the annotation array always behaves like a sequential list of statements with transaction-like ordering.

### 8.2. allEntries clears a region, not a single key

`@CacheEvict(cacheNames="reports", allEntries=true, condition="#p1")` clears the `reports` region when the condition is true; it does not use a specific key. **Do not declare `key` alongside `allEntries=true`.** A group can contain one operation deleting a single key in cache A and another clearing all of cache B, but clearly document the scope.

### 8.3. No default atomicity across multiple caches

One operation succeeding on backend A while another fails on backend B is not automatically rolled back by `@Caching` like a distributed transaction. When strong consistency is needed, review your cache provider, transaction boundaries, retry/outbox, post-commit deletion, or versioned namespaces. Do not treat `condition` as an authorization tool; cache hits must also be properly protected.

## 9. Per-Operation Testing Checklist

1. List all cache regions dependent on a business operation; describe how each region's key is determined.
2. Verify each write/delete operation's key has the **exact same type and value** as the key used on the read side.
3. Seed sample cache entries in both regions with two different keys. Call the method with the second condition false: verify only the first region is affected.
4. Call with the second condition true: verify both regions are updated/evicted accurately, without affecting out-of-scope caches.
5. Test null/blank string cases; SpEL has null-guards, while the business method must handle inputs per its own contract.
6. Test region changes, slug changes, tenant changes, and **old** keys that must be evicted; key changes typically require deleting both old and new.
7. Test exceptions with `beforeInvocation=true/false`, avoiding assuming no eviction occurs when a method fails.
8. Use integration tests fetching the service from the Spring context; do not test solely via `new Service()` since that bypasses the proxy.
9. With a real provider, verify TTL, visibility, and transaction synchronization rather than extrapolating completely from an in-memory cache.
10. Monitor hits/misses, cache size, and source query counts to verify grouped operations behave as intended.

A quick verification matching the example output:
- Before updates, both `product("P1")` and `summary("VN")` hit on the second call.
- After updating only the product, reading `P1` misses and `VN` hits.
- After updating both, both `P1` and `VN` miss.
- Counters are `3/2`; if different, re-check proxy, condition, cache name, or key.

## 10. Self-Assessment Questions

**Q1.** Two `@CacheEvict` annotations are in `@Caching(evict={...})`, and the second condition is false. Is the whole group cancelled?

**Answer:** No. Each operation has its own condition; the first operation can still run.

**Q2.** The read method takes `(region)` at `#p0`, while the update method takes `(productId, region)`. Which key should the summary eviction operation use?

**Answer:** `#p1` on the update method, so the effective key matches the read side's region.

**Q3.** You want a single save to write the result into two regions by ID and slug, each with its own toggle flag?

**Answer:** Use `@Caching(put={@CachePut(...), @CachePut(...)})` with two separate keys and conditions. The save method is still invoked.

**Q4.** Does `@CacheConfig(cacheNames="products")` apply the same `condition` to every nested annotation?

**Answer:** No; @CacheConfig only supports certain class-level defaults, not a shared condition.

**Q5.** Why shouldn't `@Cacheable` and `@CachePut` be mixed indiscriminately?

**Answer:** Cacheable can skip the method on a hit, while CachePut requires the method to run to put; their semantics conflict.

**Q6.** Does grouping two evictions mean an atomic transaction?

**Answer:** No. Consistency, transactions, and backend failures must be handled separately.

## 11. Takeaways and References

- **`@Caching` groups multiple operations; each nested annotation keeps its own key, condition, and cache name.**
- `condition=false` on one operation does not prevent other operations from running.
- Keys for evict/put must match the read operation's key, even when parameters appear at different positions.
- `@CachePut` always executes the method; be cautious when mixing with `@Cacheable`.
- `@CacheConfig` provides class-level defaults, not a replacement for per-operation configuration or `@EnableCaching`.
- Grouping operations does not automatically provide transactional consistency/atomicity across caches.

Official sources for deeper study:
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — @Caching Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/Caching.html)
- [Spring Framework — @CacheConfig Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CacheConfig.html)
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework — AOP Proxying](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
