# Cache.get: Distinguishing a Cache Miss from a Null Value in Spring Framework

## 1. Why do these two states differ?

When working directly with Spring Cache, the important question is not only **what value is stored**, but also **whether the cache already has an entry for that key**.

Distinguish three states:

1. **MISS — no mapping for the key**: never cached, expired, or evicted.
2. **HIT_NULL — key exists, cached business value is `null`**: the method previously searched and found no data; the cache recorded that result if the provider allows it.
3. **HIT_VALUE — key exists, non-null value**: for example `"Alice"`, a DTO, or an integer.

The first two states are easily confused because a Java method returning `null` can carry two meanings: "entry not found in cache" or "entry exists but the business value is null". Without distinguishing them, an application may query the database repeatedly for nothing or skip a result that needs to be reloaded.

In Spring Framework, the `org.springframework.cache.Cache` API solves this problem with **`Cache.ValueWrapper`** for the `get(Object key)` overload:

- `cache.get(key) == null` means **the cache has no mapping** for the key.
- `cache.get(key) != null` but `cache.get(key).get() == null` means **there is a mapping containing a business null value**, if the cache implementation supports null.
- `cache.get(key).get() != null` is a cache hit with a normal value.

The core point: **whether the wrapper exists** tells you if it is a cache hit or miss; **the value inside the wrapper** is the business result.

## 2. The three overloads of Cache.get and their meanings

Spring Cache provides common read methods:

| API | Return type | Strength | Distinguishes hit-null from miss from the result? |
| --- | --- | --- | --- |
| `get(Object key)` | `Cache.ValueWrapper` or null | Checks whether a mapping exists and retrieves the value | **Yes**, by checking the wrapper |
| `get(Object key, Class<T> type)` | `T` or null | Directly retrieves the expected value with type checking | **No**, both cases return null |
| `get(Object key, Callable<T> loader)` | `T` | Computes and caches the value when the entry is missing | The return value alone does not distinguish them, since both a cached null and a loader returning null can yield null |

These three methods must not be conflated:

### 2.1. `get(Object)`: use when you need to know whether a key exists

```java
Cache.ValueWrapper wrapper = cache.get("user:42");

if (wrapper == null) {
    System.out.println("Cache MISS: no key user:42");
} else if (wrapper.get() == null) {
    System.out.println("Cache HIT: null stored for user:42");
} else {
    System.out.println("Cache HIT: " + wrapper.get());
}
```

This is an **illustrative code snippet inside a method that already has a valid `cache` variable**; section 4 has a full Java program.

Do not write `cache.get("user:42").get()` without checking the wrapper first, because a cache miss causes `cache.get(...)` to return null and calling `.get()` will throw a `NullPointerException`.

If the provider does not support storing null, the hit-null branch will not appear from a successful `put` operation on that provider. However, reading through `Cache.ValueWrapper` remains the way to express the Spring Cache contract accurately, independent of native storage details.

### 2.2. `get(key, Class<T>)`: concise but ambiguous with null

```java
String a = cache.get("neverStored", String.class);
String b = cache.get("storedNull", String.class);

// a == null and b == null: cannot conclude both keys are absent.
```

This overload **returns the business data directly**, not a wrapper. According to the Spring Javadoc, it **cannot distinguish a cached null from a missing entry**. If there is a cached value whose type does not match, it may throw `IllegalStateException` (for example, the cache stores a String but an Integer is requested).

When you only need the value and accept `null` carrying both meanings, the typed overload is convenient. When logic requires distinguishing "not yet loaded" from "loaded and not found", **use `get(key)`**.

### 2.3. `get(key, Callable<T>)`: load if missing

```java
String result = cache.get("sku:A1", () -> repository.load("A1"));
```

This snippet requires the application's `repository`. Meaning: if the key has a matching entry, return the cached value; if the key is absent, run `Callable` to compute it, store it according to the provider's semantics, and return it.

**Important:** if the entry holds a cached null, a provider that supports null will treat that as a cache **hit**, so the loader should not run just because the business value is null. With `ConcurrentMapCache` allowing null (in the complete example below), this is confirmed via a loader counter.

If the loader throws an exception, the `Cache.get(key, Callable)` API specifies that the error is wrapped in `Cache.ValueRetrievalException`. Regarding concurrency, the Javadoc encourages providers to synchronize loading for the same key **if possible**, but does not guarantee every implementation or every node loads only once. Check the actual backend if single-flight is required.

## 3. State table: wrapper and value

Example `users` cache:

| Key state | `cache.get(key)` | `wrapper.get()` if wrapper exists | `cache.get(key, String.class)` |
| --- | --- | --- | --- |
| Key `"u1"` not stored yet | `null` | `get()` must not be called | `null` |
| `put("u1", null)` called on a null-supporting cache | **Non-null** wrapper | `null` | `null` |
| `put("u1", "Alice")` called | **Non-null** wrapper | `"Alice"` | `"Alice"` |
| Key just `evict("u1")` and not rewritten | `null` on a simple synchronous cache | `get()` must not be called | `null` |

**Do not confuse two concepts of "null":**
- **Null key**: passing null as the key to the API, e.g., `cache.get(null)`. The cache backend may disallow this. That is a key-validity issue and **is not** the topic of cached-null.
- **Null value**: a valid key (e.g., `"u1"`) whose stored business result is null. Some providers accept it, while others reject it.

Also do not confuse `CacheManager.getCache("users") == null` — **no cache region with that name exists** — with `cache.get("u1") == null` — **the cache region exists but has no mapping for the key**.

## 4. Why can ConcurrentMapCache cache null even though ConcurrentHashMap does not allow it?

The JDK's `ConcurrentHashMap` does not support `null` as a value. However, Spring's `ConcurrentMapCacheManager` allows caching null by default (**`allowNullValues = true`**), because Spring converts business null into an internal **marker/sentinel** before storing it in the native map and converts it back to null when reading through the abstraction.

```java
ConcurrentMapCacheManager manager =
        new ConcurrentMapCacheManager("manual", "annotated");
manager.setAllowNullValues(true);
```

The snippet above illustrates manager configuration and requires importing `org.springframework.cache.concurrent.ConcurrentMapCacheManager`. In runnable examples, configuration is applied before using the cache. Setting `allowNullValues=false` prevents the cache from accepting null; the behavior of null writes (error or other policy) depends on the implementation. Do not assume all providers such as Redis, Caffeine, JCache, or custom caches share the same null support.

**Do not inspect the sentinel via `getNativeCache()` to check for business null.** The sentinel is an internal detail; the value in the native store layer can differ from `cache.get(key).get()`. When using the `Cache` API, Spring already provides the wrapper to keep semantics stable.

### 4.1. Negative caching: caching "not found" results

Cached-null is also known as a form of **negative caching**: remembering a search that returned no result.

For example, a service queries the database for a non-existent customer ID. If the provider allows caching null, repeated calls with that ID can hit the cache and **avoid querying again** while the entry remains valid.

Pros:
- Reduces database load when many requests ask for the same non-existent ID.
- Reduces repeated queries caused by absent data.

Risks:
- If the record appears later, cached-null can cause the service to keep returning "not found" until the entry's TTL expires or it is evicted.
- Caching a null caused by a transient error (instead of "genuinely does not exist") is dangerous. Distinguish exceptions/timeouts from not-found results; do not turn system errors into cached nulls indefinitely.
- Requires a dedicated TTL policy or eviction when creating a new record if the backend and design allow.

For data with strict consistency requirements, evaluate whether to cache null rather than assuming "null is always a cache miss".

## 5. Runnable example: distinguishing all three states

The example uses Java 17+, Spring Boot BOM 3.3.13 to pin Spring Cache dependencies, and an in-memory `ConcurrentMapCacheManager`. No HTTP server, Redis, or database is required.

### 5.1. Directory structure

```text
cache-get-null-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/cache/CacheGetDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'cache-get-null-demo'
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
    mainClass = 'demo.cache.CacheGetDemo'
}
```

### 5.2. Complete Java file

`src/main/java/demo/cache/CacheGetDemo.java`:

```java
package demo.cache;

import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class CacheGetDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class CacheConfig {
        @Bean
        CacheManager cacheManager() {
            ConcurrentMapCacheManager manager =
                    new ConcurrentMapCacheManager("manual", "annotated");
            manager.setAllowNullValues(true);
            return manager;
        }

        @Bean
        LookupService lookupService() {
            return new LookupService();
        }
    }

    public static class LookupService {
        private final AtomicInteger calls = new AtomicInteger();

        @Cacheable(cacheNames = "annotated", key = "#p0")
        public String query(String code) {
            calls.incrementAndGet();
            return null; // Simulates a query where no record is found.
        }

        public int callCount() {
            return calls.get();
        }
    }

    private static String state(Cache cache, String key) {
        Cache.ValueWrapper wrapper = cache.get(key);
        if (wrapper == null) {
            return "MISS";
        }
        Object value = wrapper.get();
        return value == null ? "CACHED_NULL" : "VALUE:" + value;
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(CacheConfig.class)) {

            CacheManager manager = context.getBean(CacheManager.class);
            Cache manual = Objects.requireNonNull(manager.getCache("manual"));
            Cache annotated = Objects.requireNonNull(manager.getCache("annotated"));

            // A missing cache region is different from a missing cache key.
            System.out.println("regionMissing="
                    + (manager.getCache("other") == null));

            // State 1: key has never been in the cache.
            System.out.println("missing=" + state(manual, "missing"));

            // State 2: stored the business null value itself.
            manual.put("storedNull", null);
            System.out.println("storedNull=" + state(manual, "storedNull"));

            // State 3: key has a normal value.
            manual.put("present", "alpha");
            System.out.println("present=" + state(manual, "present"));

            // Typed get returns null in both situations.
            System.out.println("typedMissing="
                    + manual.get("missing", String.class));
            System.out.println("typedStoredNull="
                    + manual.get("storedNull", String.class));

            AtomicInteger loaderCalls = new AtomicInteger();

            // Stored null is a hit: the loader does not run.
            String cachedNull = manual.get("storedNull", () -> {
                loaderCalls.incrementAndGet();
                return "should-not-run";
            });
            System.out.println("nullLoaderResult=" + cachedNull);
            System.out.println("nullLoaderCalls=" + loaderCalls.get());

            // Only a missing key runs the loader and writes the result.
            String created = manual.get("fresh", () -> {
                loaderCalls.incrementAndGet();
                return "generated";
            });
            String createdAgain = manual.get("fresh", () -> {
                loaderCalls.incrementAndGet();
                return "unexpected";
            });
            System.out.println("created=" + created);
            System.out.println("createdAgain=" + createdAgain);
            System.out.println("loaderCalls=" + loaderCalls.get());

            // putIfAbsent sees the existing null mapping.
            Cache.ValueWrapper previous =
                    manual.putIfAbsent("storedNull", "overwrite");
            System.out.println("putIfAbsentSawNull="
                    + (previous != null && previous.get() == null));
            System.out.println("nullStillStored="
                    + state(manual, "storedNull"));

            // Evict removes the mapping; does not keep a null wrapper.
            manual.evict("storedNull");
            System.out.println("afterEvict=" + state(manual, "storedNull"));

            // @Cacheable on a Spring bean also caches a null result.
            LookupService service = context.getBean(LookupService.class);
            System.out.println("firstQuery=" + service.query("X"));
            System.out.println("secondQuery=" + service.query("X"));
            System.out.println("queryCalls=" + service.callCount());
            System.out.println("annotatedState="
                    + state(annotated, "X"));
        }
    }
}
```

Run in the project directory with JDK 17+ and a compatible Gradle version:

```bash
gradle run --quiet
```

If a Gradle Wrapper is present, replace with `./gradlew run --quiet` (Windows: `gradlew.bat run --quiet`).

Expected output from `System.out.println`, excluding build/framework logs:

```text
regionMissing=true
missing=MISS
storedNull=CACHED_NULL
present=VALUE:alpha
typedMissing=null
typedStoredNull=null
nullLoaderResult=null
nullLoaderCalls=0
created=generated
createdAgain=generated
loaderCalls=1
putIfAbsentSawNull=true
nullStillStored=CACHED_NULL
afterEvict=MISS
firstQuery=null
secondQuery=null
queryCalls=1
annotatedState=CACHED_NULL
```

### 5.3. Reading the output properly

1. `regionMissing=true`: the manager is in fixed-cache-name-list mode with only `manual` and `annotated`, so region `other` does not exist. This is independent of the keys inside `manual`.
2. `missing=MISS`: `cache.get("missing")` returns a **null wrapper**.
3. `storedNull=CACHED_NULL`: calling `put("storedNull", null)` with a null-supporting provider; `get("storedNull")` returns a **non-null** wrapper, while `wrapper.get() == null`.
4. `present=VALUE:alpha`: non-null wrapper and the inner value is a string.
5. `typedMissing=null` and `typedStoredNull=null`: the typed overload has no flag indicating whether an entry exists.
6. `nullLoaderCalls=0`: `get("storedNull", Callable)` does not run the loader because cached-null is a **hit**.
7. `loaderCalls=1`: key `fresh` misses once, the loader produces `generated`, and the subsequent read hits.
8. `putIfAbsentSawNull=true`: an existing cached-null **is still an existing mapping**. Do not overwrite it just because the value inside the wrapper is null.
9. `afterEvict=MISS`: the entry is removed, so no wrapper remains; the synchronous in-memory example reflects this immediately.
10. `queryCalls=1` after two calls to `@Cacheable` returning null: the method ran only once; the cache annotation stored the negative result. `annotatedState=CACHED_NULL` shows the entry exists.

**Why must it be called through the Spring context?** `@EnableCaching` activates the interceptor for the `LookupService` bean. If you instantiate `new LookupService()` yourself or invoke `this.query(...)` internally within the same target in default proxy mode, the annotation call is not intercepted; the counter may increment both times and caching will not be demonstrated.

## 6. Safe code pattern when a three-state result is needed

If application logic needs to preserve the distinction between "not cached", "cached null", and "cached value", do not return `null` for the first two states. You can use a data type that represents it explicitly:

```java
record CacheRead(boolean hit, Object value) {}

static CacheRead read(Cache cache, Object key) {
    Cache.ValueWrapper wrapper = cache.get(key);
    return (wrapper == null)
            ? new CacheRead(false, null)
            : new CacheRead(true, wrapper.get());
}
```

This is a **Java 17 illustrative snippet inside a class** with `import org.springframework.cache.Cache`. With `new CacheRead(false, null)`, it is a miss. With `new CacheRead(true, null)`, it is a hit-null. With `new CacheRead(true, "Alice")`, it is a hit-value.

A variant using an enum `MISS`/`HIT_NULL`/`HIT_VALUE` and a result object further prevents logs, metrics, or source-query orchestration APIs from confusing the two concepts.

Avoid using the expression:

```java
// Wrong when null is a cacheable value:
if (cache.get("key", String.class) == null) {
    // Concluding "key does not exist" is not guaranteed!
}
```

If the cache key exists with null, the `== null` expression still evaluates to true. **This is not how to check for a cache miss**.

## 7. Controlling null caching policy with @Cacheable

If a method returns null when not found, there are two design choices:

**Proactively cache null (negative caching):**

```java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String id) {
    return repository.find(id); // May return null.
}
```

In a cache provider that allows null, the first null return can be stored, and subsequent calls hit. This is an illustrative method requiring the application's `Product`/`repository`.

**Do not store null:**

```java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    unless = "#result == null"
)
public Product find(String id) {
    return repository.find(id);
}
```

`unless` is evaluated **after the method runs on a miss**, so `#result` can be used to reject writing null. In that case, if the ID still does not exist, subsequent calls miss again and execute the method per provider policy.

Do not use `condition="#result != null"` instead of `unless`: `condition` for `@Cacheable` is evaluated before a method result exists, and is used to decide whether to perform cache lookup at all.

### 7.1. Optional.empty() also requires attention

Spring supports the `Optional<T>` return type for annotation-based caching. According to Spring documentation, `Optional.of(value)` is handled using the inner value; `Optional.empty()` can be cached as a **business null value** when the provider allows it.

```java
@Cacheable(cacheNames = "customers", key = "#p0")
public java.util.Optional<Customer> find(String id) {
    return repository.findOptional(id);
}
```

This snippet only illustrates a `Customer` class and an existing repository. If you want to avoid caching the empty case, you can use `unless="#result == null"` per Spring SpEL semantics with supported wrappers; `#result` is the unwrapped business data, not the `Optional` itself.

**API distinction:** `java.util.Optional.empty()` is **a return object at the business boundary**; upon entering the cache abstraction, Spring may store the corresponding null rather than necessarily storing the `Optional` object itself.

## 8. get(key, Callable): two more scenarios to check

### 8.1. Loader returns null

If the key is absent and the loader actually returns null:

```java
String result = cache.get("notFound", () -> (String) null);
```

With a cache that allows null, the provider can store the null result as an entry, so the next `get("notFound")` will return a **non-null ValueWrapper containing null**. With a cache that does not allow null, the operation may fail or follow provider-specific rules.

Therefore, **do not infer from the `result == null` variable alone whether the loader was called**; if you need to know, count loader calls or use `get(key)` to inspect the mapping afterward according to provider semantics.

### 8.2. Loader throws an exception

```java
try {
    cache.get("slowLookup", () -> {
        throw new IllegalArgumentException("upstream failed");
    });
} catch (Cache.ValueRetrievalException ex) {
    System.err.println("Cannot load cache key: " + ex.getKey());
}
```

This is an illustrative snippet requiring the `cache` variable and importing `Cache`. Spring uses `Cache.ValueRetrievalException` to wrap exceptions thrown by the loader. Never turn upstream errors into a persistent null entry if the business logic requires retrying or failing fast.

### 8.3. Concurrent loading and atomicity depend on the provider

`get(key, Callable)` is designed to combine the "lookup, if missing then compute and store" pattern. The Spring Javadoc encourages backends to ensure the loader runs only once under concurrent misses **if possible**. However, this is not a guarantee for all providers or across multiple JVMs/application nodes.

If single-flight is needed, test against the real backend and state the synchronization scope clearly. In Spring annotations, `@Cacheable(sync=true)` also relies on the cache provider's synchronized loading capability and does not create a distributed transaction between the cache and the database.

## 9. Common mistakes

| Symptom | Cause | Solution |
| --- | --- | --- |
| `NullPointerException` at `cache.get(key).get()` | Key missed so wrapper is null | Check the wrapper first |
| Returned null is always interpreted as a cache miss | Used typed `get(key, String.class)` | Use `get(key)` to distinguish |
| DB is not queried again even though a new record appeared | Null was cached earlier | Appropriate TTL, evict on record creation, or `unless` |
| Null is not stored and code throws an error | Provider/option does not support null | Verify `allowNullValues` and backend policy |
| Reading the native map shows a "strange" object instead of null | Spring uses a sentinel to represent cached-null | Read through `Cache.ValueWrapper` |
| `getCache("missing") == null` is mistaken for a key miss | CacheManager lacks the region | Distinguish a cache region from a mapping in the cache |
| `get(key, Callable)` still calls the loader multiple times concurrently | Provider does not guarantee synchronized load as expected | Measure call counts, check backend or locking mechanism |
| `putIfAbsent` overwrites cached null | Code checked value instead of wrapper/presence | Treat a wrapper containing null as an existing entry |
| Loading the same key calls the body twice | Service called via `new`/self-invocation, or caching not enabled | Check Spring proxy and `@EnableCaching` |
| Wrong tenant data returned from cache | Key lacks sufficient scope, unrelated to null semantics | Design proper keys/authorization |

### 9.1. Evict/clear may be deferred

Examples using in-memory `ConcurrentMapCache` typically show immediate eviction, but the `Cache.evict(key)` or `Cache.clear()` abstraction allows backends to defer or execute them asynchronously, especially through transaction-aware decorators. Therefore, code requiring strong visibility must read the provider contract and consider APIs such as `evictIfPresent` or `invalidate` when appropriate, rather than assuming every `get` immediately after eviction will miss on every backend.

### 9.2. Direct cache put is not atomic with a get-then-put sequence

`get(key)` reveals the current state, but between checking the wrapper and calling `put`, another thread may write the same key. If the goal is **write only when absent**, use `Cache.putIfAbsent` when the provider supports appropriate atomicity. The return value of `putIfAbsent` is also a `ValueWrapper`: a non-null wrapper may contain an already existing null value.

Do not confuse "knowing hit/miss" with "locking the entire business workflow" — especially when a loader queries source data concurrently with updates.

## 10. Testing checklist

When implementing a cache capable of holding null, test at least:

1. **Missing key:** `get(key) == null`, typed get returns null.
2. **Cached null:** non-null wrapper, `wrapper.get() == null`; typed get still returns null.
3. **Cached value:** non-null wrapper, matching type; typed get returns the value.
4. **Wrong type:** requested type does not match a non-null value; handle `IllegalStateException`.
5. **Loader on missing key:** calls loader and stores per provider contract.
6. **Loader on cached-null:** does not call loader, unless the backend does not support null and has no entry at all.
7. **Eviction and TTL:** after the entry is removed/expires, the wrapper returns to null.
8. **@Cacheable returning null:** call twice through proxy, count body executions with `allowNullValues=true`.
9. **@Cacheable(unless) rejecting null:** calling again with the same key still runs the method if no other entry exists.
10. **Concurrent miss:** verify synchronized loader behavior on the backend in use.
11. **Source state change from "no record" to "present":** need a way to invalidate the negative cache.
12. **Different provider:** repeat tests with Redis/Caffeine or the real manager; do not assume `ConcurrentMapCache` behavior.

Null cases should be defined by **business meaning**: null due to non-existence, lack of permission, query failure, or value being updated. Do not lump all of those outcomes into a long-lived negative cache if the system needs to distinguish them.

## 11. Summary

- **`Cache.get(key)` returning a null wrapper = cache miss**; **a non-null wrapper containing a null value = cached-null**, when the backend allows it.
- **`Cache.get(key, Class<T>)` returns null for both missing and cached-null**, so do not use it to determine whether a key exists.
- `Cache.get(key, Callable<T>)` invokes the loader when the entry is missing; cached-null is a hit for null-supporting caches; load synchronization depends on the provider.
- `ConcurrentMapCacheManager` allows null by default using an **internal sentinel**, even though `ConcurrentHashMap` cannot hold native nulls.
- Actively choose between **negative caching or `unless="#result == null"`**, TTL, and eviction when source data changes.
- Do not confuse **null key**, **null value**, **missing cache region**, and **cache miss inside an existing region**.

### Official documentation

- [Spring Framework 6.1 — Cache API, get(Object), get(Object, Class), get(Object, Callable)](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/cache/Cache.html)
- [Spring Framework — Cache.ValueWrapper API](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/cache/Cache.ValueWrapper.html)
- [Spring Framework — ConcurrentMapCacheManager, allowNullValues](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html)
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
