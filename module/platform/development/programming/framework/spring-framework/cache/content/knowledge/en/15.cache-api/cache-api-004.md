# get with Callable to Load Data on Miss — Programmatic Spring Cache API

## Objectives

This lesson belongs to the **programmatic API** group of Spring Framework Cache. After this lesson, you will be able to:

- Use `Cache.get(Object key, Callable<T> valueLoader)` properly for the **read from cache if present, load from source and store if missing** operation.
- Distinguish `get(key)`, `get(key, Class<T>)`, and `get(key, Callable<T>)`, especially when the returned value may be `null`.
- Understand when `Callable` runs, handle errors with `Cache.ValueRetrievalException`, and avoid false assumptions about "loading strictly once" across multiple threads/instances.
- Use `CacheManager`, cache names, and keys consistently; update the source of truth and invalidate the right entry.
- Run a Spring Boot Java 17+ example with predictable stdout demonstrating cache hit, cache miss, stale value, and loader failure.

**Main idea:** this is how to **use Spring Cache directly via the API**, not annotation caching. `Cache.get(key, Callable)` lets you concisely write the *get-or-load* lifecycle: look up the entry; invoke the loader only on a miss; place the result into the cache according to provider policy; return the result to the caller.

## 1. Problem: loading data on a cache miss

Suppose a method reading book titles from a slow database. When multiple requests ask for book `B1`, we want:

~~~text
Call 1:
  cache["B1"] → MISS
  database.findTitle("B1") → "Java 17"
  store cache["B1"] = "Java 17"
  return "Java 17"

Call 2:
  cache["B1"] → HIT
  return "Java 17", DO NOT read database
~~~

You could write the logic manually:

~~~java
// Illustrative inside a method that already has cache and bookId variables.
Cache.ValueWrapper wrapper = cache.get(bookId);
if (wrapper != null) {
    return (String) wrapper.get();
}
String title = loadFromDatabase(bookId);
cache.put(bookId, title);
return title;
~~~

However, this is a **check-then-act** operation. Two threads can both observe a miss and both load, leading to duplicate queries or overwriting each other's puts. In many cases, Spring's load-on-miss API is more concise and sensible:

~~~java
String title = cache.get(
        bookId,
        () -> loadFromDatabase(bookId));
~~~

`() -> loadFromDatabase(bookId)` is a `Callable<String>`. **The Callable is only requested to execute when the entry does not yet exist or has become invalid according to the backend.** Do not call `loadFromDatabase` beforehand and pass the result into the callback, because doing so defeats the purpose of caching.

Note: the Spring JavaDoc encourages providers to coordinate loaders so a key only has to be loaded once if possible, but the actual level of synchronization depends on the implementation. Do not infer an exactly-once guarantee across multiple JVMs from the API signature.

## 2. Three important overloads of Cache.get

Spring Framework defines `org.springframework.cache.Cache` as the common API for cache regions. Commonly used read forms:

| API | Result | Cache miss | Auto-loads? |
| --- | --- | --- | --- |
| `Cache.ValueWrapper get(Object key)` | Wrapper of value, or `null` if no mapping | `null` | No |
| `<T> T get(Object key, Class<T> type)` | Properly typed value, or `null` | `null` | No |
| `<T> T get(Object key, Callable<T> valueLoader)` | Cached value or newly loaded callback result | Calls `valueLoader`, caches result per provider | **Yes** |

Comparison snippet:

~~~java
// cache is an org.springframework.cache.Cache retrieved from manager.
Cache.ValueWrapper present = cache.get("B1");
String typed = cache.get("B1", String.class);
String onDemand = cache.get("B1", () -> "Java 17");
~~~

**Do not confuse `get(key, Class<T>)` with `get(key, Callable<T>)`.** One method specifies the expected data type on read; the other specifies how to load on miss.

A subtle difference: `cache.get(key, String.class) == null` can mean **no entry exists** *or* **an entry with a null value exists**. `get(key)` with `Cache.ValueWrapper` lets you distinguish both cases if the backend supports cached null. If the wrapper is non-null while `wrapper.get() == null`, the entry exists but the business value is null.

### What is Callable?

`java.util.concurrent.Callable<V>` has one method:

~~~java
V call() throws Exception;
~~~

It is like a zero-argument function that **returns a result** and can throw checked exceptions. Spring only accepts the callback; running the callback on a miss is delegated to `Cache`. Compared to `Runnable`, `Callable` fits data-loading tasks because it returns the value to cache.

## 3. Loading mechanism: path of a call

~~~text
Service / Controller
        │
        └── Cache.get(key, Callable<T>)
                    │
               lookup key
                /       \
             HIT        MISS
              │           │
       return cached T    call valueLoader.call()
                          │
                    /-----------\
                 success       exception
                    │               │
               cache value   ValueRetrievalException
                    │
               return value
~~~

On the cache-hit path, the callback does not run. Therefore:

- Do not place access-control checks **only inside the loader**. On a hit, the loader is skipped. Authorization must be on the path that always executes, and the key must include sufficient tenant/user context if results differ.
- Do not place side effects required on every request (such as request auditing or billing) inside the loader.
- Do not assume data updates immediately when the database changes. As long as the cache still has a valid entry, callers keep receiving the old data until eviction/expiration.
- If the cached value is a mutable object and the provider stores by reference, callers may share references to the same object. `get(key, Callable)` does not make a deep copy.
- If the cache provider fails, not every runtime exception originates from the loader; distinguish `Cache.ValueRetrievalException` from backend/serialization errors.

## 4. Java 17+ Spring Boot example: hit, miss, evict, and loader failure

The demo uses **Spring Boot**, `ConcurrentMapCacheManager`, and a map simulating a database to avoid external system dependencies. The goal is to measure how many times `Callable` actually executes.

In a Java 17+ Spring Boot Gradle project already configured with appropriate plugins/versions, use dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
~~~

Use two Java files in the same `example.cacheapi` package. Because we **call the `Cache.get` API directly**, the demo **does not need `@EnableCaching`**. If using `@Cacheable`/`@CacheEvict` annotations in another application, appropriate interception must be enabled there.

### 4.1. BookCatalog.java — loading via Callable

Create `src/main/java/example/cacheapi/BookCatalog.java`:

~~~java
package example.cacheapi;

import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.stereotype.Service;

@Service
public class BookCatalog {
    private final Cache cache;
    private final Map<String, String> database =
            new ConcurrentHashMap<>(Map.of("B1", "Java 17"));
    private final AtomicInteger sourceReads = new AtomicInteger();

    public BookCatalog(CacheManager manager) {
        this.cache = Objects.requireNonNull(
                manager.getCache("bookTitles"),
                "Cache bookTitles missing");
    }

    public String title(String bookId) {
        return cache.get(bookId, () -> {
            int count = sourceReads.incrementAndGet();
            System.out.println("LOAD #" + count + " " + bookId);

            String result = database.get(bookId);
            if (result == null) {
                throw new IllegalArgumentException(
                        "Unknown book: " + bookId);
            }
            return result;
        });
    }

    // Only to demonstrate stale cache: change source, do not evict.
    public void changeSourceOnly(String bookId, String newTitle) {
        database.put(bookId, newTitle);
    }

    // In production, coordinate invalidation with transactions.
    public void changeAndEvict(String bookId, String newTitle) {
        database.put(bookId, newTitle);
        cache.evict(bookId);
    }

    public int sourceReadCount() {
        return sourceReads.get();
    }
}
~~~

Explanation:

1. `CacheManager.getCache("bookTitles")` retrieves the exact cache region. If the cache is missing from configuration, the constructor fails fast instead of silently reading the wrong region.
2. The loader is a lambda; `sourceReads.incrementAndGet()` sits **inside** the loader, so it increments only when a true miss occurs and loading is needed.
3. The initial source has `B1 → Java 17`. Since the simulated map is independent of the cache, we can modify the source without automatically removing the entry.
4. If the ID does not exist, the loader throws `IllegalArgumentException`, highlighting the exception-wrapper mechanism.
5. `cache.evict(bookId)` is the explicit entry-removal API using the same key as the read path.

### 4.2. CacheApiDemoApplication.java — scenario

Create `src/main/java/example/cacheapi/CacheApiDemoApplication.java`:

~~~java
package example.cacheapi;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CacheApiDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CacheApiDemoApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("bookTitles");
    }

    @Bean
    CommandLineRunner demo(BookCatalog books) {
        return args -> {
            System.out.println("first = " + books.title("B1"));
            System.out.println("second = " + books.title("B1"));

            books.changeSourceOnly("B1", "Intermediate");
            System.out.println("stale = " + books.title("B1"));

            books.changeAndEvict("B1", "Spring Cache");
            System.out.println("fresh = " + books.title("B1"));

            for (int attempt = 1; attempt <= 2; attempt++) {
                try {
                    books.title("MISSING");
                } catch (Cache.ValueRetrievalException ex) {
                    System.out.println("missing attempt " + attempt +
                            " = " +
                            ex.getCause().getClass().getSimpleName());
                }
            }

            System.out.println("sourceReads = " +
                    books.sourceReadCount());
        };
    }
}
~~~

Run in the Spring Boot project directory:

~~~bash
./gradlew bootRun
# Windows PowerShell: .\gradlew.bat bootRun
~~~

Lines printed by `System.out`, **in order** (ignoring Gradle and Spring Boot logs):

~~~text
LOAD #1 B1
first = Java 17
second = Java 17
stale = Java 17
LOAD #2 B1
fresh = Spring Cache
LOAD #3 MISSING
missing attempt 1 = IllegalArgumentException
LOAD #4 MISSING
missing attempt 2 = IllegalArgumentException
sourceReads = 4
~~~

**Comparing each action:**

- The first `title("B1")` misses; the loader runs and prints `LOAD #1 B1`. The value `Java 17` is stored under `bookTitles["B1"]`.
- The second call with the same key hits; the loader does not run, so there is no `LOAD #2` here.
- `changeSourceOnly` updates the source map to `Intermediate` but **does not delete the entry**. `stale = Java 17` proves the cache does not automatically detect source changes.
- `changeAndEvict` updates the source to `Spring Cache` and deletes entry `B1`. The subsequent `title("B1")` misses, prints `LOAD #2 B1`, and returns `Spring Cache`.
- The first `title("MISSING")` call prints `LOAD #3 MISSING` and the loader throws `IllegalArgumentException`. Spring wraps that error under `Cache.ValueRetrievalException`, and the code prints the class name of `getCause()`.
- Because the failed load did not produce a successful cached value, the second `MISSING` call misses again, prints `LOAD #4 MISSING`, and wraps the same error type.
- `sourceReads = 4` is completely determined by the four lambda executions.

**Why is stdout predictable?** It runs in a fresh process; `database` has only one entry, all calls run sequentially in a single `CommandLineRunner`, and no other request mutates the map/cache. The code consists of **two Java files inside a Spring Boot project with dependencies**, not a standalone file compiled with `javac` without Spring.

## 5. Missing values: null, exceptions, and negative caching

**Not finding** a record is not the same as an **infrastructure error**. The business contract must decide what the callback returns.

### 5.1. Loader throws an exception

~~~java
cache.get("MISSING", () -> {
    throw new IllegalArgumentException("No such record");
});
~~~

With the `get(key, Callable)` API, loader errors are wrapped in `Cache.ValueRetrievalException`. Errors do not produce a successful value to put; subsequent calls may invoke the loader again. This case is demonstrated above.

To handle meaningfully:

~~~java
try {
    return cache.get(id, () -> repository.load(id));
} catch (Cache.ValueRetrievalException ex) {
    Throwable original = ex.getCause();
    throw new IllegalStateException(
            "Cannot load item " + id, original);
}
~~~

This snippet is **illustrative only** inside a method that has `cache`, `id`, and `repository`. Do not catch all errors and blindly return a fake "success" value; that fake value could be cached and corrupt subsequent requests.

### 5.2. Loader returns null

~~~java
String notFound = cache.get("UNKNOWN", () -> null);
~~~

With backends supporting `null`, such as the default `ConcurrentMapCache`, `null` may be stored as an internal marker: subsequent calls return **cached null** and the callback does not run. With backends configured to disallow `null`, the cache operation may fail or require a different design.

Therefore, do not assume "`null` means cache miss". To check whether an entry exists even when the value is null:

~~~java
Cache.ValueWrapper wrapper = cache.get("UNKNOWN");
if (wrapper == null) {
    System.out.println("No mapping");
} else {
    System.out.println("Mapped value = " + wrapper.get());
}
~~~

The second example is also illustrative; it requires the `cache` variable. If the wrapper exists and `get() == null`, the entry is a cached null. If the wrapper is `null`, there is no mapping.

**Negative caching** (storing "not found" to reduce repeated queries) can be useful, but requires TTL, invalidation when a new record arrives, and distinguishing from network errors. If you do not want to cache null, `Cache.get(key, Callable)` does not have the annotation's `unless` option; design a corresponding read/put policy, or use `@Cacheable(unless = "#result == null")` when appropriate.

### 5.3. Optional is not the same as null

If the loader returns `Optional.empty()`, that is a non-null object (an empty `Optional`), not `null`. The cache backend may store that object according to configuration/serializer; with distributed caches, check serializability. Do not assume Spring unwraps `Optional` in every **direct API** call the way some annotation-caching paths do.

## 6. Multiple threads missing the same key: is it loaded only once?

If you write `get → if missing → load → put` yourself, two threads can observe a cache miss together:

~~~text
Thread A                        Thread B
--------                        --------
get(B1) → MISS                  get(B1) → MISS
loadFromSource(B1)              loadFromSource(B1)
put(B1, valueA)                 put(B1, valueB)
~~~

`Cache.get(key, Callable)` allows the provider to handle get-or-load within a single operation. The Spring JavaDoc states that **if possible**, implementations should ensure the callback is called only once for concurrent requests for the same key.

With the common `ConcurrentMapCache`, the implementation uses a `ConcurrentMap.computeIfAbsent`-style operation to coordinate within **a single JVM**. However:

- There is no guarantee replicas in other JVMs share a single load if each replica has its own local cache.
- With Redis, JCache, or other providers, you must read documentation/test the actual implementation; do not assume distributed locking on the same key.
- If the callback has non-idempotent side effects (creating payments, emitting events), do not use a cache loader as an exactly-once mechanism.
- An overly slow loader can cause other requests to wait or increase latency. Appropriate timeouts, monitoring, and policies are required.
- Avoid having the loader recursively call `cache.get(sameKey, loader)`; this risks recursive updates/deadlocks/exceptions depending on the provider.
- `@Cacheable(sync=true)` also depends on backend support and is not a substitute for distributed locks in every system.

To test, start with an empty cache, have multiple threads call the same key concurrently, and count actual callback executions. Test on production-like backends and topologies, not just a test map.

## 7. Choosing the right cache name, key, and lifecycle

### Cache region

~~~java
Cache cache = Objects.requireNonNull(
        manager.getCache("bookTitles"));
~~~

In the demo, the manager pre-creates the `bookTitles` region. Do not confuse **no cache region** with **region exists but entry missed**. With a static manager, a misspelled region name can cause `getCache(name) == null`; use `Objects.requireNonNull` to catch it early.

### Key and context

If the source returns tenant-specific data, the same ID `B1` in two tenants may have different titles. In that case `cache.get("B1", loader)` is wrong if two tenants share a cache region. A proper key:

~~~java
public record BookKey(String tenantId, String bookId) {}
~~~

Then:

~~~java
BookKey key = new BookKey(tenantId, bookId);
return cache.get(key, () ->
        repository.loadTitle(tenantId, bookId));
~~~

The snippet above is illustrative with `repository`, `tenantId`, and `bookId` available in the service. For in-memory caches, a Java `record` provides field-based equality/hashing; when using a distributed backend, verify serialization/key conversion.

**Access-control checks must sit on the path that is always called**, not only inside the loader, because a cache hit skips the loader. Never put access tokens, passwords, or raw sensitive data into the key.

### When the source of truth changes

In the demo, `changeSourceOnly` intentionally creates a stale cache for learning. In production, you must have one of these strategies:

- `cache.evict(key)` upon successful update/delete on the right region.
- `cache.put(key, freshValue)` if an accurate value is available after update.
- TTL/expiry on the provider to bound entry age when the source can change elsewhere.
- Versioning or event-driven invalidation when multiple services or replicas read concurrently.

Note: updating the database and deleting from the cache are not automatically atomic with the transaction. If you evict before commit, another request may reload the old value. For high consistency requirements, design post-commit invalidation or an appropriate transactional/synchronization mechanism.

## 8. Comparison with @Cacheable(sync=true)

Similar annotation form in terms of goal:

~~~java
@Cacheable(cacheNames = "bookTitles", key = "#p0", sync = true)
public String title(String id) {
    return repository.loadTitle(id);
}
~~~

This is a **different illustration**, not code to insert into the imperative demo. `repository` is a dependency of a real application.

| Aspect | `Cache.get(key, Callable)` | `@Cacheable(sync=true)` |
| --- | --- | --- |
| Implementation approach | Called directly on a `Cache` object. | Called on a service method handled by the Spring cache interceptor. |
| `@EnableCaching` | Not needed when using only the API. | Must enable caching and route calls through the proper proxy/weaving. |
| Key source | Caller constructs `key`. | Spring key generator or SpEL. |
| Value source | `Callable<T>` runs on miss. | Method body runs on miss. |
| Cache region | Retrieve `Cache` via `CacheManager`. | `cacheNames` and annotation configuration. |
| Conditions/`unless` | Controlled manually in Java and via provider policy. | Built-in annotation mechanisms, with restrictions when `sync=true`. |
| Self-invocation | Direct API calls remain normal Java calls. | `this.method()` calls within the same bean typically bypass the proxy. |
| Concurrency | Per `Cache.get(key, Callable)` semantics supported by the provider. | Also requires provider support for synchronized key loading. |

If you need caching in a block of code with flexible conditional branches, the imperative API is often clearer. If you want caching as a service-method concern, annotations are more concise. Do not mix both on the same value/key without designing who owns put/evict and the error policy.

## 9. Mistakes to avoid

1. **Assuming `Callable` always runs:** a cache hit skips the loader; do not put logic required for every request inside it.
2. **Assuming `get(key, Class<T>)` loads automatically:** it only reads/casts an existing value and accepts no callback.
3. **Wrong key or missing context:** causes hits returning another user's/tenant's data, even if the loader is correct.
4. **Wrong cache name:** `getCache(name)` can return `null`, which is not an entry miss.
5. **Not evicting after source changes:** the cache continues holding stale data.
6. **Not handling loader failures:** `ValueRetrievalException` has a cause and is not always a cache configuration error.
7. **Assuming exceptions are cached as results:** normal loader errors do not put a successful value; the next read can run the callback again.
8. **Not defining the cached-null contract:** can create unintended negative caching.
9. **Using mutable keys/values:** changing a key's `equals/hashCode` after put, or mutating a store-by-reference cached object, can break correctness.
10. **Expecting a default TTL from `ConcurrentMapCacheManager`:** TTL must be supported by the provider and configured separately.
11. **Assuming "one loader across the entire cluster":** load-coordination promises apply only at the provider-supported level, with no default distributed exactly-once guarantee.
12. **Not testing the production backend:** serialization, TTL, nulls, and concurrency of Redis/Caffeine/JCache can differ from the map used in the demo.

## 10. Exercises and testing plan

| Test | Action | Result to verify |
| --- | --- | --- |
| First miss | Call with key when cache is empty | Loader runs, value is stored. |
| Hit after miss | Call the same key again | Loader does not run; source read count does not increase. |
| Evict then read | `cache.evict(key)` then call get | Loader runs again, retrieves new data. |
| Source changed without evict | Update source independently | Cache may return old value before expiry. |
| Loader throws exception | Use key `MISSING` as in demo | `Cache.ValueRetrievalException` holds original cause. |
| Retry after error | Call the failing key again | Loader is called again, no previous successful value exists. |
| Cached null | Use backend with allowNullValues=true | Non-null `ValueWrapper` even if value is null; next call may not load. |
| Disallow null caching | Backend allowNullValues=false | Verify error/miss policy and handling design. |
| Different key | Call `B2` when source data exists | Independent cache miss, does not return B1. |
| Two tenants with same ID | Create BookKey with tenant and bookId | Does not return wrong tenant's data. |
| Concurrent miss | Multiple threads call same key concurrently | Measure loader count and waiting behavior on real backend. |
| Production backend | Run tests against deployed provider | Confirm serialization, concurrency, TTL, and exceptions. |

### Pre-merge checklist

- [ ] `CacheManager` has the right named region, checked `getCache(name) != null`.
- [ ] Cache key is immutable and includes all components affecting the result.
- [ ] `Callable<T>` returns the proper type and has no side effects required on every request.
- [ ] Contract defined for not found, cached null, loader errors, and retries.
- [ ] Evict/put/expiry strategy exists when source data changes.
- [ ] Authorization check runs on the call path even on a cache hit.
- [ ] Tested backend concurrent loading behavior without assuming cluster-wide exactly-once.
- [ ] Tests cover hit/miss, source updates, exceptions, and the real backend.

## Official documentation

- Spring Framework — `Cache` API, `get(Object, Callable)`, `ValueRetrievalException`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/Cache.html
- Spring Framework — `ConcurrentMapCache` API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCache.html
- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Boot — Caching: https://docs.spring.io/spring-boot/reference/io/caching.html
