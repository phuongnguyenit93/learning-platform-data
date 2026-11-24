# @CacheEvict: Evicting a key when source data changes

> **Spring Framework Cache Abstraction · Topic: @CacheEvict.** The goal is to update the data source and invalidate the exact stale entry in the cache, so the next read fetches the new version while keeping unrelated entries.

## 1. The stale cache data problem

Suppose the system uses the `products` cache region to store product names by SKU. When calling `find("A")` for the first time, the service fetches `"Keyboard-v1"` from the source, then caches the value under key `"A"`. Subsequent reads with the same key use the cache immediately, saving a query.

If an update operation changes the source to `"Keyboard-v2"` without invalidating entry A, a read call may still receive `"Keyboard-v1"`. That is a **stale cache**: the copy in the cache no longer corresponds to the original data.

Common *cache-aside* solution:

1. The method that updates the data source actually succeeds.
2. Spring removes the entry with key `"A"` in the `products` cache.
3. The next read with the same key becomes a cache miss, loading `"Keyboard-v2"` from the source.
4. `@Cacheable` stores the new value; other entries such as `"B"` continue to be kept.

~~~text
Initially:
  source: A -> Keyboard-v1, B -> Mouse-v1
  products cache: A -> Keyboard-v1, B -> Mouse-v1

Execute update("A", "Keyboard-v2"):
  source: A -> Keyboard-v2, B -> Mouse-v1
  @CacheEvict: deletes exactly products["A"]

Afterward:
  products cache: no A, B -> Mouse-v1
  find("A") -> cache miss -> source -> Keyboard-v2 -> cache A
  find("B") -> cache hit -> Mouse-v1
~~~

`@CacheEvict` only controls the **cache**; it does not perform the source data write operation on behalf of the method. The source update behavior must reside in business code.

## 2. @CacheEvict syntax for removing a single entry

Example of a method that performs an update from an application with a repository:

~~~java
@CacheEvict(cacheNames = "products", key = "#p0")
public void rename(String sku, String newName) {
    repository.updateName(sku, newName);
}
~~~

This is an **illustrative snippet inside a service**, requiring a valid `repository` component and the application's Spring cache configuration. Section 5 provides a standalone program.

| Attribute | Function | Relevant default |
| --- | --- | --- |
| `cacheNames` or `value` | Selects cache region(s); here named `products` | Must be declared on the annotation or appropriate shared configuration |
| `key` | SpEL computing the key to evict; `#p0` is the first argument | If omitted, uses Spring's key generator |
| `allEntries` | Whether to clear the entire cache region? | `false`: only handles the entry by key |
| `beforeInvocation` | Whether to evict before the method runs? | `false`: evicts after the method succeeds |
| `condition` | SpEL expression allowing or denying eviction | If omitted: no additional condition |

`cacheNames = "products"` is the **cache region name**, while `key = "#p0"` is how to select **one entry inside that region**. With `rename("A", "Keyboard-v2")`, `#p0` retrieves the string `"A"`. Spring looks up the `products` cache via `CacheManager` and removes the entry corresponding to that key.

The update method can return `void` because `@CacheEvict` uses the method as an **eviction trigger**, without needing to put the method result into the cache.

Do not use `allEntries = true` when only one product changes. When you actually need to clear the entire region, use `allEntries = true` without `key` because `key` has no meaning in a full-region clear operation.

## 3. The most important condition: the eviction key must match the read key

Read and update methods often have **different signatures**:

~~~java
// Two method snippets belonging to a service with Map<String, String> source.
@Cacheable(cacheNames = "products", key = "#p0")
public String find(String sku) {
    return source.get(sku);
}

@CacheEvict(cacheNames = "products", key = "#p0")
public void rename(String sku, String newName) {
    source.put(sku, newName);
}
~~~

This is **illustrative service structure code**, not a standalone class yet. Both annotations select the SKU at index 0, so when updating A, the evicted key is the exact key that the reader is using.

Conversely:

~~~java
// Unsuitable if the read method only uses the SKU string as the key.
@CacheEvict(cacheNames = "products")
public void rename(String sku, String newName) {
    source.put(sku, newName);
}
~~~

Omitting `key` means Spring uses the default key mechanism. With **two parameters**, `SimpleKeyGenerator` creates a composite key of both the SKU and the new name; this key is **different** from the SKU string used when reading. In that case, eviction may miss entry A, leaving the old value in the cache.

### Selecting the right position in SpEL

| Expression | Meaning |
| --- | --- |
| `#p0` or `#a0` | First argument (index 0) |
| `#p1` or `#a1` | Second argument (index 1) |
| `#root.args[0]` | First argument obtained from the argument array |
| `#sku` | Java parameter named `sku`, when runtime finds name metadata |

If the updater has the signature `rename(String newName, String sku)`, the SKU is at position 1, so `key = "#p1"` must be chosen. For name-based notation like `#sku`, Java typically needs the `-parameters` compiler flag to retain metadata. `#p0` and `#p1` do not depend on source parameter names.

### Keys constructed with custom rules

If the reader uses `key = "'sku:' + #p0"`, the actual entry has key `"sku:A"`, not `"A"`. The evictor must also use that key generation rule. If one source record affects multiple cache representations (for example, price by SKU and currency), it may be necessary to evict **multiple different keys**. Evicting a single SKU is sufficient only when there is truly one entry representing the updated data.

## 4. Eviction timing: after or before the method?

### After invocation: the default

With `beforeInvocation = false`, Spring executes the method body first. Only when the method completes normally does Spring compute the key and perform eviction.

~~~text
Call update("A", "Keyboard-v2") through Spring proxy
                 |
                 v
          Source update logic
             /         \
       Succeeded     Threw exception
           |                 |
           v                 v
  Evict products["A"]   No eviction by default
~~~

This fits many synchronous update operations. If the update is rejected right at the input validation step, the old cache entry is kept because the source has not changed.

If the update has already partially affected the source and then throws an error, rollback and invalidation must be handled based on the actual transaction; `@CacheEvict` does not automatically roll back source data.

### Before invocation: intentional use

~~~java
@CacheEvict(
    cacheNames = "products",
    key = "#p0",
    beforeInvocation = true
)
public void rename(String sku, String newName) {
    repository.updateName(sku, newName);
}
~~~

This is illustrative code requiring the application's repository. In this mode, Spring evicts the key **before** the method runs, so the entry is removed even if the method subsequently throws an exception.

One risk: a reader running concurrently after eviction but before the source update finishes may load and re-cache the **old value**. Therefore, do not enable `beforeInvocation = true` mechanically for every update operation.

`@CacheEvict` also has `condition`, such as `condition = "#p0 != null"` to evict only when the input SKU is non-null. It **does not have an `unless` attribute** like `@Cacheable`. With `beforeInvocation = false`, SpEL evaluated after the method can reference `#result` when appropriate; with `beforeInvocation = true`, a result that does not yet exist cannot be used.

## 5. Java 17+ program demonstrating an exact single key

The example runs using Spring Framework **6.2.14** and Gradle. It uses `ConcurrentMapCacheManager` for single-JVM caching and `ConcurrentHashMap` to act as the data source. No database or Redis is needed.

**File `build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.14'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.EvictOneEntryDemo'
}
~~~

**File `src/main/java/demo/EvictOneEntryDemo.java`:**

~~~java
package demo;

import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class EvictOneEntryDemo {

    @Configuration
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("products");
        }

        @Bean
        public Catalog catalog() {
            return new Catalog();
        }
    }

    public static class Catalog {
        private final Map<String, String> source =
                new ConcurrentHashMap<>(Map.of(
                        "A", "Keyboard-v1",
                        "B", "Mouse-v1"
                ));
        private int sourceReads;

        @Cacheable(cacheNames = "products", key = "#p0")
        public String find(String sku) {
            sourceReads++;
            return source.get(sku);
        }

        @CacheEvict(cacheNames = "products", key = "#p0")
        public void update(String sku, String newName) {
            if (newName == null || newName.isBlank()) {
                throw new IllegalArgumentException("name must not be blank");
            }
            source.put(sku, newName);
        }

        public int sourceReads() {
            return sourceReads;
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            Catalog catalog = context.getBean(Catalog.class);
            CacheManager manager = context.getBean(CacheManager.class);
            Cache cache = Objects.requireNonNull(manager.getCache("products"));

            System.out.println("read A: " + catalog.find("A"));
            System.out.println("read B: " + catalog.find("B"));
            System.out.println("read A again: " + catalog.find("A"));
            System.out.println("source reads: " + catalog.sourceReads());

            catalog.update("A", "Keyboard-v2");
            System.out.println("A cached after update: " +
                    (cache.get("A") != null));
            System.out.println("B cached after update: " +
                    (cache.get("B") != null));

            System.out.println("read A after update: " + catalog.find("A"));
            System.out.println("read B after update: " + catalog.find("B"));
            System.out.println("source reads: " + catalog.sourceReads());

            try {
                catalog.update("B", "");
            } catch (IllegalArgumentException ex) {
                System.out.println("update rejected: " + ex.getMessage());
            }
            System.out.println("B cached after rejected update: " +
                    (cache.get("B") != null));
        }
    }
}
~~~

Run from the directory containing `build.gradle`, with JDK 17+ and a compatible Gradle version:

~~~bash
gradle run --quiet
~~~

**Expected stdout of the program (excluding build tool messages):**

~~~text
read A: Keyboard-v1
read B: Mouse-v1
read A again: Keyboard-v1
source reads: 2
A cached after update: false
B cached after update: true
read A after update: Keyboard-v2
read B after update: Mouse-v1
source reads: 3
update rejected: name must not be blank
B cached after rejected update: true
~~~

**Explanation:**

1. The first two reads of A and B hit the source, so the `sourceReads` counter is 2. The repeated read of A is a cache hit, and the counter stays unchanged.
2. `update("A", "Keyboard-v2")` writes the change to the map and Spring evicts key `"A"` after the method succeeds.
3. `cache.get("A") == null` indicates that entry A has been removed; entry B still has a `Cache.ValueWrapper`, so the two check lines print `false` and `true` respectively.
4. Reading A after the update misses again, loading `Keyboard-v2` from the source. Reading B still hits, bringing total source accesses to **3**.
5. `update("B", "")` throws `IllegalArgumentException` before modifying the map. Because `beforeInvocation = false`, Spring does not evict entry B after the exception.

The program uses `#p0`, so the `-parameters` compiler flag is not needed. Cached methods are invoked from `main` through the Spring bean; this is an important requirement in the default proxy mode.

**Note:** `Cache.get(key)` returns a `Cache.ValueWrapper` or null. Having a wrapper with a null inner value differs from having no entry at all; this example stores non-empty product names, so checking the wrapper alone is sufficient.

## 6. Single-key vs. multi-key scope

Only evict a single key when a source change makes only that corresponding entry stale. For example, renaming A while B does not change: keeping B cached avoids unnecessary re-querying.

If a source record appears in multiple cache entries, such as a detail cache by SKU, a list by category, and filtered search results, evicting `products["A"]` is not enough to guarantee all representations are fresh. In that case, identify the **set of affected keys/cache regions** and invalidate accordingly. `@Caching` can group multiple `@CacheEvict` annotations; `allEntries = true` is only suitable when you want to clear the whole region and accept the reload cost.

If an identifier changes from A to C, consider both the old key and the new key. If a key consists of multiple fields (SKU, currency, language), one update may require invalidating multiple variants.

## 7. Transactions, concurrency, and multiple instances

### Evicting after the method is not necessarily after commit

With a database source and a method annotated with `@Transactional`, the order between caching advice and transaction advice, together with how the cache backend supports transactions, determines **eviction timing relative to commit**. A case can occur where the cache is evicted while the write transaction has not yet committed; another reader misses the cache, still reads the old data, and writes the old value back.

For strict consistency requirements, design eviction **after a successful commit**, consider `TransactionAwareCacheManagerProxy` or post-commit events, and verify how the backend handles it. Simply adding `@Transactional` does not automatically guarantee cache consistency after commit.

### A reader can write stale data after eviction

A thread reading A starts before the update, retrieves the old value from the source, and has not cached it yet. The writer updates A and evicts successfully. Then the first reader puts the old value into the cache. Thus the entry can become stale even though eviction was called.

`@CacheEvict` does not provide atomicity across the data source, the cache, and multiple concurrent requests. Depending on the required consistency level, versioned keys, TTL, access synchronization, or stronger invalidation strategies may be needed.

### Local cache and other write paths

`ConcurrentMapCacheManager` in the example only caches within the current JVM. If multiple instances have their own caches, eviction on instance A does not automatically remove entries in instance B. Use a shared backend or broadcast cross-instance invalidation events when appropriate.

If source data is modified by direct SQL, batch jobs, or another service, the annotated method is not invoked, so Spring cannot automatically know to evict. Ensure **every source write path has an invalidation path** according to the application design.

### Spring proxy and self-invocation

With `@EnableCaching` in the default proxy mode, calls from another method within the same bean such as `this.update("A", "Keyboard-v2")` typically do not go through the caching interceptor. Therefore the annotation may not run. Calls from another bean through the proxy, as in the program above, have caching advice applied by Spring.

## 8. Comparison with @CachePut and direct operations

| Approach | Main behavior | Best suited for |
| --- | --- | --- |
| `@CacheEvict(cacheNames = "products", key = "#p0")` | Removes the entry after a successful update | Void updates or cached data that should be regenerated from the source |
| `@CachePut(cacheNames = "products", key = "#p0")` | Always runs the method, stores the **return value** in the cache | Updates returning the exact new value expected by the reader |
| `cacheManager.getCache("products").evict(sku)` | Removes the entry directly via API | Event handling, manual operations, or tasks outside interceptors |

Do not use `@Cacheable` on an update method because a cache hit can prevent the update code from running. If calling the manual API, `getCache(name)` can return null depending on the `CacheManager`, so check it while ensuring the right region and key.

## 9. Common pitfalls and how to check

| Symptom | Possible cause | Check |
| --- | --- | --- |
| Update succeeds but reads remain stale | Wrong `cacheNames` or wrong key | Compare reader and evictor; check SpEL/KeyGenerator |
| Update has two parameters and omits `key` | Default key includes both parameters | Specify the key by the identifier of the data to evict |
| Eviction does not trigger | Caching not enabled, call bypasses proxy | Check `@EnableCaching`, bean wiring, and call path |
| One key changes but every entry is removed | Using `allEntries = true` | Revert to `key`-based eviction |
| Method throws error yet cache stays | Default evicts after method succeeds | Check update/rollback and eviction timing |
| One server still serves stale data | Per-JVM local cache | Verify backend, invalidation events, TTL |
| Cache becomes stale again after eviction | Race condition or eviction before commit | Check transactions, read/write threads, and operation order |

Short diagnostic workflow: **check the new source value → confirm the update method went through the Spring proxy → confirm key/cache name → verify the entry was removed → read again to observe cache miss and new data**.

## 10. Self-check questions

**1.** Reader `get(String id)` caches by `key = "#p0"`; which key should updater `change(String id, String status)` use to remove the right entry?

**Answer:** `key = "#p0"` if the first argument is the ID just like the reader, with the same `cacheNames`.

**2.** Why does omitting `key` in a two-parameter updater easily lead to stale data?

**Answer:** `SimpleKeyGenerator` uses both parameters to build a composite key, which differs from the ID-only key in the reader.

**3.** With `beforeInvocation = false`, does an update throwing an exception remove the entry?

**Answer:** No, default post-invocation eviction only executes when the method finishes successfully.

**4.** Why should you avoid using `allEntries = true` for updating a single SKU?

**Answer:** It clears the entire cache region, including entries for unchanged SKUs, increasing unnecessary cache misses.

**5.** Why can a reader re-cache an old value after an updater has already evicted it?

**Answer:** That reader may have fetched the old value before the update finished or before commit, and then performed a cache put after the eviction time. An appropriate consistency strategy is needed.

## 11. Takeaways and official documentation

- `@CacheEvict` **invalidates entries**, it does not write source data itself.
- For a single-key target, set the right `cacheNames` and `key`, and keep `allEntries = false`.
- **Reader and evictor keys must match**; pay attention because update methods often have multiple arguments.
- By default, Spring evicts **after the method succeeds**. `beforeInvocation = true` removes beforehand even if the method later fails.
- In real systems, also consider transactions/commits, race conditions, proxies, and cache scope across instances.

References:

- [Spring Framework 6.2 — Cache Annotations](https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html)
- [Spring Framework — CacheEvict API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/annotation/CacheEvict.html)
- [Spring Framework — Cache API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/Cache.html)
- [Spring Framework — TransactionAwareCacheManagerProxy](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheManagerProxy.html)
