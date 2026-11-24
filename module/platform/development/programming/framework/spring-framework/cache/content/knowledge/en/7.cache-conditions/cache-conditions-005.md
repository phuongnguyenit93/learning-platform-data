# Optional: Storing the Inner Value or Representing Absence When Using Spring Cache

> **Spring Framework — Cache Abstraction · Topic: Caching Conditions.** This lesson explains how Spring handles methods returning `java.util.Optional<T>` with `@Cacheable`, how absent results are represented in the cache, and when to use `unless` to **avoid caching empty results**.

## 1. The Problem: Results Can Be Absent

Suppose a program looks up a product by SKU:

~~~java
public Optional<String> findProduct(String sku) {
    return "P-1".equals(sku) ? Optional.of("Keyboard") : Optional.empty();
}
~~~

This is minimal illustrative logic: SKU `"P-1"` returns `Optional.of("Keyboard")`, while other SKUs return `Optional.empty()`. In a real application, the lookup branch typically calls a repository or data source. `Optional<T>` explicitly conveys that finding no data is a valid outcome, rather than forcing callers to guess from `null`.

When adding `@Cacheable`, two cases must be distinguished:

1. **Found:** Should the `Optional` object itself be cached, or the `T` value inside it?
2. **Not found:** Is `Optional.empty()` cached? If so, how does the cache region record the absence and how does it differ from a *cache miss*?

The answer depends on **Spring's unwrapping mechanism** and **the backend's ability to store null values**. Caching an empty result can help avoid repeated queries, but it also risks preserving a "not found" state after the data appears.

## 2. Spring's Rule: Unwrap Optional Before Storing

With **Spring Framework's `@Cacheable`**, return types of `java.util.Optional<T>` are handled specially by Spring:

- Returning a present `Optional.of(value)` or `Optional.ofNullable(value)`: Spring extracts the **inner `value` inside the Optional** to store in the cache.
- Returning `Optional.empty()`: Spring treats the **logical cached business value as `null`**, provided the caching operation is not excluded by a condition and the cache backend allows representing null.
- When a subsequent call with the same key hits the cache, Spring returns a result matching the **method's declared return type**: a present value is wrapped as `Optional.of(value)`, and a cached null value is returned as `Optional.empty()`.
- Storing a *logical business value* does not mean every provider can write raw `null` directly. Some implementations use an internal **sentinel/null holder**; others reject caching null altogether.

Example:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public Optional<Product> findProduct(String sku) {
    return repository.findBySku(sku);
}
~~~

This snippet illustrates usage in an application that has a `Product` class and an appropriate `repository` bean. It is not a standalone runnable example. With `sku = "P-1"`:

| Repository result on cache miss | Value Spring intends to store | Subsequent call with same key |
| --- | --- | --- |
| `Optional.of(product)` | `product` (type `Product`) | Cache hit and returns `Optional.of(product)` |
| `Optional.empty()` | `null` at the cache contract level, when provider permits | Cache hit and returns `Optional.empty()` |
| Method throws exception | No normal result to store | Subsequent call may execute again; this cache mechanism does not cache exceptions by default |

**Key point:** `@Cacheable` normally does not store the intact `Optional.of(...)` or `Optional.empty()` wrapper as an `Optional` object in the cache region. Spring unwraps the wrapper to determine the value to store. This is specific to caching interception; if you call `cache.put(key, optional)` manually through the cache API, you are directly placing an `Optional` object into the cache and should not assume the same automatic unwrapping.

Spring documentation describes this policy for `java.util.Optional`. Do not generalize this claim to other wrapper types like `OptionalInt`, `Future`, or reactive types; they have their own support contracts or version-specific differences.

## 3. Three States Frequently Confused

Distinguish **no entry**, **an entry holding a null value**, and **an entry holding a real value**.

| State | `Cache.get(key)` (`ValueWrapper` API) | Meaning for `@Cacheable` returning Optional |
| --- | --- | --- |
| Cache miss | `null` (no wrapper) | Spring invokes the method unless prevented by another mechanism |
| Cached null | Non-null `Cache.ValueWrapper`, but `wrapper.get() == null` | Spring can return `Optional.empty()` without invoking the method |
| Cached value | Non-null `Cache.ValueWrapper`, `wrapper.get()` is the object | Spring can return `Optional.of(value)` without invoking the method |

`Cache.ValueWrapper` is a Spring interface; the concrete object depends on the provider. With the default `ConcurrentMapCacheManager`, Spring supports caching null even though `ConcurrentHashMap` cannot hold `null`: the implementation replaces null with an **internal marker object** and restores null when read through the cache API.

Operation flow:

~~~text
Call findProduct("P-404") via Spring cache proxy
                       |
                       v
                Entry exists for key?
                 /              \
               no               yes
               |                 |
        Run findProduct()    Read cached value
               |                 |
        Optional.empty()     cached null? ------> Optional.empty()
               |                 |
        Spring unwraps        value T ----------> Optional.of(T)
               |
        logical business value null
               |
   Does `unless` allow or veto?
      /                    \
    allow                  veto
      |                     |
 Provider supports null?  Do not write entry
      |
 Record cached null
~~~

In practice, if the backend does not support null or is configured to reject null, attempting to write an empty result can raise an error. **Do not** assume `Optional.empty()` is something every backend automatically skips.

## 4. `unless`: Deciding Whether to Store `Optional.empty()`

Suppose a missing SKU's data might be added a few seconds later. In that case, you may **not want to retain empty results**:

~~~java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    unless = "#result == null"
)
public Optional<Product> findProduct(String sku) {
    return repository.findBySku(sku);
}
~~~

`unless` is a condition that **vetoes writing the result to the cache after the method runs**. If the expression returns `true`, the result of that execution **is not stored**.

For a method returning `Optional<Product>`, Spring exposes the `#result` variable as the **inner `Product` value**, **not `Optional<Product>`**:

| Method returns | `#result` in `unless` | `#result == null` | Storage behavior |
| --- | --- | --- | --- |
| `Optional.of(product)` | `product` | `false` | Allowed to cache `product` |
| `Optional.empty()` | `null` | `true` | Do not write entry for this key |

Therefore, the pattern **`unless = "#result == null"`** is the clear way to cache successful hits while skipping missing data.

### Why Not Use `unless = "#result.isEmpty()"`?

In the `@Cacheable` context, `#result` has already been **unwrapped from Optional**. When `Optional.empty()` is returned, `#result` is `null`, so calling `isEmpty()` on it can cause a SpEL evaluation error. When `Optional.of(product)` is returned, `#result` is `Product`, which may not even have an `isEmpty()` method.

The right signal is **whether the actual object is present**, typically written `#result == null`. If you need to check a property on `Product`, you can use safe navigation, such as `unless = "#result?.archived == true"` if `Product` actually has a boolean `archived` property and business rules only want to skip archived records.

### `condition` Cannot Replace `unless`

~~~java
// Illustrating two different evaluation stages:
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    condition = "#p0 != null",
    unless = "#result == null"
)
public Optional<Product> findProduct(String sku) {
    return repository.findBySku(sku);
}
~~~

- `condition` inspects **inputs before calling the method**. Here, caching is enabled only when `sku` is non-null.
- `unless` inspects **the result after calling the method**, so it can tell whether the `Optional` was empty via `#result`.
- When `condition` is false, the call performs no caching; business code still needs to handle null input itself.
- Do not write `condition = "#result == null"` to inspect the result: at the `condition` stage, the method has no result yet to inspect.

**API limitation:** Do not combine `@Cacheable(sync = true)` with `unless`, because Spring does not support `unless` in synchronized caching mode. If you need both synchronized per-key loading and filtering of empty results, choose another design based on your backend/configuration; do not assume both attributes work together.

## 5. Runnable Java 17+ Example: Caching Empty vs. Skipping Empty

This example runs on **Spring Framework 6.2.14**. It uses the default `ConcurrentMapCacheManager` (which allows null) and two separate cache regions:

- `allowEmpty`: has no `unless`, so a not-found result is also remembered.
- `skipEmpty`: has `unless = "#result == null"`, so not-found results always reload.

Create a Gradle project with two files:

**`build.gradle`**

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
    mainClass = 'demo.OptionalCacheDemo'
}
~~~

**`src/main/java/demo/OptionalCacheDemo.java`**

~~~java
package demo;

import java.util.Optional;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class OptionalCacheDemo {

    @Configuration
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("allowEmpty", "skipEmpty");
        }

        @Bean
        public BookService bookService() {
            return new BookService();
        }
    }

    public static class BookService {
        private int allowCalls;
        private int skipCalls;

        @Cacheable(cacheNames = "allowEmpty", key = "#p0")
        public Optional<String> allowEmpty(String id) {
            allowCalls++;
            return "found".equals(id)
                    ? Optional.of("Java")
                    : Optional.empty();
        }

        @Cacheable(
            cacheNames = "skipEmpty",
            key = "#p0",
            unless = "#result == null"
        )
        public Optional<String> skipEmpty(String id) {
            skipCalls++;
            return "found".equals(id)
                    ? Optional.of("Java")
                    : Optional.empty();
        }

        public int getAllowCalls() {
            return allowCalls;
        }

        public int getSkipCalls() {
            return skipCalls;
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            // Retrieve the Spring-managed bean so @Cacheable is intercepted.
            BookService books = context.getBean(BookService.class);
            CacheManager manager = context.getBean(CacheManager.class);

            System.out.println(books.allowEmpty("missing"));
            System.out.println(books.allowEmpty("missing"));
            System.out.println("allow calls: " + books.getAllowCalls());

            Cache allow = manager.getCache("allowEmpty");
            Cache.ValueWrapper cachedEmpty = allow.get("missing");
            System.out.println("empty entry exists: " + (cachedEmpty != null));
            System.out.println("empty raw value: " + cachedEmpty.get());

            System.out.println(books.skipEmpty("missing"));
            System.out.println(books.skipEmpty("missing"));
            System.out.println("skip calls: " + books.getSkipCalls());

            Cache skip = manager.getCache("skipEmpty");
            System.out.println("skipped entry exists: " +
                    (skip.get("missing") != null));

            System.out.println(books.allowEmpty("found"));
            System.out.println(books.allowEmpty("found"));
            System.out.println("stored present value: " +
                    allow.get("found").get());
            System.out.println("allow calls: " + books.getAllowCalls());
        }
    }
}
~~~

Run in the project directory containing `build.gradle` with a compatible JDK/Gradle:

~~~bash
gradle run --quiet
~~~

**Stdout printed by the application in order** (excluding external environment tool messages/errors, if any):

~~~text
Optional.empty
Optional.empty
allow calls: 1
empty entry exists: true
empty raw value: null
Optional.empty
Optional.empty
skip calls: 2
skipped entry exists: false
Optional[Java]
Optional[Java]
stored present value: Java
allow calls: 2
~~~

### Reading the Output

1. Two calls to `allowEmpty("missing")` return `Optional.empty`, yet the method body runs **only once**; the second call reads the cached null entry.
2. `allow.get("missing") != null` is `true` because an **entry exists**; `cachedEmpty.get()` is `null` because the entry's content represents absence.
3. Both calls to `skipEmpty("missing")` run the body (`skip calls: 2`) because `unless` vetoed storing null.
4. `skip.get("missing") == null` confirms there is no entry for key `missing`.
5. `allowEmpty("found")` returns `Optional[Java]` both times, yet the cache stores the **string `Java`**, not an `Optional` object. `allow calls` increases from 1 to 2 for the first lookup of `found`, while the second lookup of `found` is a cache hit.

The example intentionally uses two separate cache regions so caching empty results in one case does not affect the other. In a real application, region names and TTLs must be designed per data requirements.

**Observation note:** `Cache.get(key)` returning a `ValueWrapper` or null is the cache-level inspection API. Do not use `Cache.get(key, String.class) == null` to assert a cache miss, because the direct value-returning API can also return null when the entry holds a cached null.

## 6. What If the Backend Rejects Null?

`ConcurrentMapCacheManager` allows null by default using a null-holder mechanism; this can be changed with:

~~~java
// Illustrative configuration snippet, not a standalone program.
ConcurrentMapCacheManager manager =
        new ConcurrentMapCacheManager("products");
manager.setAllowNullValues(false);
~~~

When null support is disabled, do not assume Spring can store `Optional.empty()`. With this implementation, attempting to cache a null value can throw **`IllegalArgumentException`**. Use `unless = "#result == null"` if you want to skip empty results, or choose a backend with an explicit **negative caching** mechanism if you truly need to remember "does not exist."

Null support does not follow one uniform configuration across all backends:

| Cache type | What to check |
| --- | --- |
| `ConcurrentMapCacheManager` | `allowNullValues`; defaults to true in Spring Framework |
| Caffeine via Spring cache adapter | How the adapter represents null and its null-allowing flag; do not equate with native Caffeine |
| Redis/JCache/other providers | Null acceptance configuration, serialization, TTL, region size, and specific contract |
| No-Op cache | Holds no entries, so it holds no meaningful cached nulls either |

`null` in this table is the **logical value at the Spring Cache API level**. Backends may store a byte marker, sentinel, or custom representation; do not assume the actual bytes in Redis/JCache are a Java `null`, nor claim that an `Optional.empty()` object is serialized.

## 7. Should You Cache Empty Results or Skip Them?

### When Caching Empty Results Helps

For example, invalid product codes are queried repeatedly thousands of times. If "does not exist" is fairly stable over a short period, caching an empty result is **negative caching**:

- First call: queries the data store, returns `Optional.empty()`, and stores the absence marker.
- Subsequent calls with the same key: cache hit, no data-store query.
- Result: reduces load and latency for non-existent keys.

**Risk:** If a new record is later created for a key that has a cached null, the system may continue returning `Optional.empty()` until the entry is evicted/expires or updated. Use a **short TTL**, evict the exact key when creating the record, or choose an appropriate cache-update strategy. Spring Cache abstraction does not set a uniform TTL; expiration configuration belongs to the backend.

### When Skipping Empty Results Helps

For data often created shortly after a failed lookup (e.g., job status awaiting initialization), `unless = "#result == null"` lets the next call retry the data source.

- **Advantage:** newly created data can become visible on the very next lookup, provided other data layers do not hold stale results.
- **Trade-off:** repeated misses for the same key continue hitting the data store, which can increase cost or load (*cache penetration*).

There is no single answer for every system. Decide based on **data volatility, lookup cost, acceptable staleness, and invalidation capabilities**, then configure the cache provider accordingly.

| Criterion | Cache `Optional.empty()` (if supported) | Skip empty via `unless` |
| --- | --- | --- |
| Repeated query load on non-existent keys | Significantly reduced after the first miss | Each miss typically queries again |
| Visibility of newly created records | May be delayed until evict/expire | Can be seen on the next lookup |
| Provider requirement | Must support representing null/negative entries | Does not require null caching support |
| Operations | Requires TTL and negative-entry invalidation rules | Requires protecting the data source under high miss traffic |
| Suitable use case | Stable "not found" state, expensive lookup | Frequently added data, early visibility required |

If a "not found" outcome actually spans multiple states (still loading, permission error, genuinely absent), do not collapse all states into `Optional.empty()` and cache them identically. Design explicit business return types before choosing a caching policy.

## 8. Common Mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Thinking Spring caches the `Optional.empty()` object intact | Misunderstanding what is stored in cache | Remember the unwrapping rule: empty becomes a logical cached null |
| Using `unless = "#result.isEmpty()"` | Evaluation fails because `#result` is the inner object or null | Use `unless = "#result == null"` when skipping empty |
| Using `condition = "#result == null"` | Wrong evaluation stage; result does not exist yet | Use `unless` to decide after the method runs |
| Treating `cache.get(key) == null` and `cache.get(key).get() == null` as identical | Confusing cache miss with cached null | Check `ValueWrapper` first before reading the value |
| Disabling null support while still caching `Optional.empty()` | Cache write can fail in the provider | Skip empty results or configure the provider appropriately |
| Caching null too long when records are created continuously | Returns "not found" after data exists | Short TTL, evict key on create/update operations |
| Skipping empty on APIs queried with many non-existent keys | Increased load on database | Rate limiting, DB protection, or negative cache with TTL |
| Calling `cache.put(key, Optional.empty())` directly and expecting Spring to unwrap it | Stores a different structure than the caching interceptor | Use cache annotations per contract or normalize values yourself when calling the cache API |
| Forgetting `@EnableCaching` or calling method internally via `this` | Annotation is not intercepted; hard to observe empty policy | Enable caching, call from another Spring bean via proxy, verify hit/miss |
| Combining `sync = true` with `unless` | `unless` attribute is not supported in synchronized caching | Redesign concurrency and result-storage policy |

**Additional distinction:** `Optional.empty()` is a *normal* return value. Exceptions from failed database/HTTP calls are a different event; `@Cacheable` does not cache exceptions as "empty" by default.

## 9. Self-Check

**Question 1.** Method:

~~~java
@Cacheable(cacheNames = "books")
public Optional<String> find(String isbn) {
    return Optional.of("Spring");
}
~~~

On a miss, what object does Spring intend to store?

**Answer:** The string `"Spring"` (the inner value inside `Optional`), not the `Optional.of("Spring")` wrapper.

**Question 2.** `Optional.empty()` is cached in the default `ConcurrentMapCacheManager`. Does the next call with the same key need to run the method?

**Answer:** Normally no: there is a logical cached null entry, so Spring gets a cache hit and returns `Optional.empty()`.

**Question 3.** With `unless = "#result == null"`, will `Optional.empty()` be cached?

**Answer:** No. Spring unwraps `Optional`, `#result` is null, and the `unless` expression evaluates to true, so the cache write is vetoed.

**Question 4.** Is `#result.isEmpty()` a general way to check for `Optional.empty()` in Spring Cache SpEL?

**Answer:** No, because `#result` does not point to the `Optional` wrapper; it points to the inner object or null.

**Question 5.** Data previously did not exist but was just inserted into the DB. Why does the application still return `Optional.empty()`?

**Answer:** The key may still hold a cached null from negative caching. Check and handle TTL, eviction, or cache updates when new records are created.

## 10. Takeaways and References

- `Optional.of(value)` → Spring caches **`value`**.
- `Optional.empty()` → Spring caches **`null` at the logical level**, if the operation is allowed and the provider supports it.
- *Cache miss* differs from *cached null*: `Cache.get(key) == null` differs from `Cache.get(key).get() == null`.
- `unless = "#result == null"` → **do not store `Optional.empty()`**; `#result` is the unwrapped data.
- Caching "not found" reduces queries but requires TTL/invalidation; skipping empty surfaces new data sooner but can increase load.
- Do not combine `sync = true` with `unless` on `@Cacheable`.

**Official references:**

- [Spring Framework — Declarative Annotation-based Caching (Optional and conditional caching)](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework 6.2 — @Cacheable API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/annotation/Cacheable.html)
- [Spring Framework 6.2 — ConcurrentMapCacheManager API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html)
- [Spring Framework 6.2 — Cache and Cache.ValueWrapper API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/Cache.html)
