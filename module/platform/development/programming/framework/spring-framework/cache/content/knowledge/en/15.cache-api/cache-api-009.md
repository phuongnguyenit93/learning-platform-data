# `getNativeCache` and Provider-Coupling Boundaries

## 1. Objectives and conclusions

Spring Framework provides the `org.springframework.cache.Cache` interface so applications can interact with caches through a **common API**. This interface includes the method:

```java
Object getNativeCache();
```

`getNativeCache()` returns **the underlying native cache object or backend component used by the implementation**, depending on how each `Cache` adapter is implemented. It is an escape hatch from the abstraction when you need to inspect or use a *provider-specific feature*.

Three key conclusions:

1. **`Cache` is the common contract; the object returned from `getNativeCache()` has no unified type contract.** Its return type on the interface is `Object`. For a specific implementation, the actual type might be `ConcurrentMap`, a Caffeine cache, or a Redis component. You cannot write generic code and call every native API uniformly across different backends.
2. **Using native APIs creates coupling to the provider, adapter, and library version.** Switching from an in-memory cache to Redis, or changing adapters/wrappers, can invalidate a native cast or method call.
3. **Most application logic should rely on `Cache`/`CacheManager`, cache annotations, and standard provider configuration.** Only use `getNativeCache()` when there is a genuine requirement the abstraction does not provide, and isolate it inside an infrastructure layer with type checks, tests, and an unsupported fallback path.

Example:

```java
Cache springCache = cacheManager.getCache("books");
Object nativeObject = springCache.getNativeCache();
```

*This is an illustrative snippet in an application that already has `cacheManager`; check `springCache != null` before using it. A complete runnable example is in section 8.*

**You cannot assume** `nativeObject` is always a `Map`, always a Redis connection, or always has an `expireAfterWrite` method. You must check **the concrete `Cache` bean implementation in use**.

## 2. Where does the Spring Cache abstraction sit?

Spring Cache separates responsibilities:

| Component | Responsibility | Example |
| --- | --- | --- |
| `Cache` | Contract to read, write, evict entries, get name, and access native cache | `cache.get(key)`, `cache.put(key,value)`, `cache.evict(key)` |
| `CacheManager` | Looks up `Cache` objects by logical name | `manager.getCache("books")` |
| `CacheResolver` | Selects one or more `Cache` instances for a call/operation | May depend on method, arguments, or configuration |
| Spring cache annotations | Declare *when* cache lookup/put/evict occurs | `@Cacheable`, `@CachePut`, `@CacheEvict` |
| Native cache/provider | Actual storage, eviction, TTL, metrics, serialization, clustering | ConcurrentMap, Caffeine, Redis, and other adapters |

Typical flow:

```text
Business caller
      |
      v
Spring proxy (if cache annotations are intercepted)
      |
      v
Cache interceptor
      |
      v
CacheResolver / CacheManager
      |
      v
org.springframework.cache.Cache
      |
      +-- get(key) / put(key,value) / evict(key)    <-- common API
      |
      '-- getNativeCache()                       <-- escape hatch API
              |
              '-- different objects depending on provider/adapter
```

`getNativeCache()` **does not activate** `@Cacheable`, does not look up caches by name, and does not replace `@EnableCaching`. You must already have a `Cache` instance before calling it. Typical uses include diagnostics tools, native metrics integration, or a specialized adapter with explicit requirements.

### 2.1. What is in the `Cache` contract?

Key common operations include:

```java
String name = cache.getName();
Cache.ValueWrapper hit = cache.get(key);
cache.put(key, value);
cache.evict(key);
cache.clear();

Object nativeCache = cache.getNativeCache();
```

*This is an illustrative API list, not a standalone Java file.*

Common API methods keep business logic decoupled from providers. However, even within the abstraction, details such as load synchronization for the same key, when evictions become visible, null caching, TTL, and async support still depend on the implementation or version. **A common API does not mean all backends share every operational characteristic.**

### 2.2. `getNativeCache()` is not `CacheManager.getCache(name)`

It is easy to confuse two calls containing the word "cache":

```java
Cache books = cacheManager.getCache("books"); // Spring Cache
Object nativeBooks = books.getNativeCache(); // native object
```

`getCache("books")` is the **manager's** responsibility: selecting a logical cache region. `getNativeCache()` is the **`Cache` adapter's** responsibility: exposing the underlying native object.

One cache name can resolve to different implementations across environments. For example, `"books"` might run `ConcurrentMapCache` in tests and `RedisCache` in production. Thus logic like:

```java
// WRONG if used as multi-provider code
ConcurrentMap<?, ?> map =
    (ConcurrentMap<?, ?>) cacheManager.getCache("books").getNativeCache();
```

will only work when you **already guarantee** the backend actually returns a `ConcurrentMap`. Switching environments to Redis or Caffeine can lead to `ClassCastException`.

## 3. Native types differ across providers

### 3.1. Comparison table

| Spring `Cache` implementation | Example native object | Meaning and limitations |
| --- | --- | --- |
| `ConcurrentMapCache` | `java.util.concurrent.ConcurrentMap<Object,Object>` | Local in-JVM map; has no built-in TTL, replication, or cluster management |
| `CaffeineCache` | `com.github.benmanes.caffeine.cache.Cache<Object,Object>` | Has Caffeine native APIs like `estimatedSize()`, `stats()`, `policy()`; features depend on Caffeine configuration |
| `RedisCache` (Spring Data Redis) | `RedisCacheWriter` in current versions of Spring Data Redis | Native read/write component under the adapter; **not** a `Map`, `RedisTemplate`, or Redis connection you can cast arbitrarily |
| JCache/JCacheCache adapter | Cache object per the JCache adapter/provider | Check `javax.cache`/provider version; no guarantee adapters share the same native type as Caffeine or Redis |
| Cache decorator/wrapper | May forward the native object or expose its own implementation | Inspect wrapper type, transaction awareness, and `getNativeCache()` of the exact class received |

These are **examples**, not an exhaustive list of all Spring providers. Libraries can change APIs and returned classes in other versions. Therefore, when native access is needed, consult the Javadoc for the **exact dependency version** in your application, rather than relying on cache names or guessing from packages.

In Spring Framework 6.1, `ConcurrentMapCache.getNativeCache()` declares a narrowed return type of `ConcurrentMap<Object,Object>`, and `CaffeineCache.getNativeCache()` returns a `com.github.benmanes.caffeine.cache.Cache<Object,Object>` (a synchronous native cache, which may adapt an async cache depending on configuration). Spring Data Redis `RedisCache.getNativeCache()` returns `RedisCacheWriter` in documented versions. This clearly illustrates **the same method name returning different native types**.

### 3.2. "Native" does not always mean "datastore client connection"

In `ConcurrentMapCache`, the native object is indeed a directly storing Map.

In `RedisCache`, the native object may be **`RedisCacheWriter`** — an infrastructure layer executing cache commands with byte arrays and associated configuration. It does not automatically let business code operate on Redis the way `RedisTemplate<String,Book>` does, nor does it return an object representing the entire Redis keyspace.

In `CaffeineCache`, the native object is the underlying Caffeine cache; if the Spring wrapper uses an async cache, there is a separate API such as `getAsyncCache()` (when configuration supports it). Do not infer from `getNativeCache()` that **every** backend has a similar async mechanism.

Some adapters also decorate caches with a transaction-aware proxy. The `Cache` object returned from the manager may be a wrapper, making reliance on exact runtime classes or reaching through decorators to grab the native object fragile.

## 4. How to access the native cache safely

### 4.1. Find the right cache and check for null

```java
Cache cache = Objects.requireNonNull(
    cacheManager.getCache("books"),
    "Cache 'books' is not configured"
);
Object nativeStore = cache.getNativeCache();
```

*Illustrative snippet; imports and a `cacheManager` bean are required.*

`CacheManager.getCache(name)` **can return null** if it does not manage that cache name. `Objects.requireNonNull` ensures failing clearly instead of hitting a vague `NullPointerException` right at `getNativeCache()`.

### 4.2. Use `instanceof` before casting

```java
Object nativeStore = cache.getNativeCache();

if (nativeStore instanceof ConcurrentMap<?, ?> map) {
    long approximateEntries = map.size();
    System.out.println("Local map entries: " + approximateEntries);
} else {
    System.out.println(
        "Native map inspection unavailable: " +
        nativeStore.getClass().getName()
    );
}
```

*Illustrative snippet requiring `java.util.concurrent.ConcurrentMap`; to handle any provider, log cache-type info without exposing data.*

Here `instanceof` **prevents crashing from a bad cast**. However, checking the type alone does **not** make native features portable. This branch remains specific to providers returning a `ConcurrentMap`.

**Avoid** code based on class names:

```java
// FRAGILE: relying on class name or package to infer API
if (nativeStore.getClass().getSimpleName().equals("ConcurrentHashMap")) {
    // ...
}
```

Class names can change due to wrappers, subclasses, decorators, or different providers. Checking specific interfaces/capabilities is more reliable when a native API is truly needed.

### 4.3. Do not perform unchecked direct casts

```java
// Unsafe if provider changes:
ConcurrentMap<?, ?> nativeMap =
    (ConcurrentMap<?, ?>) cache.getNativeCache();
```

This snippet may run when `Cache` is `ConcurrentMapCache`, but fails with Redis/Caffeine caches. If a component strictly depends on Caffeine, declare that component's boundary explicitly and validate the provider at startup.

### 4.4. Do not use raw casts for features the abstraction already has

If you only need to read an entry, write an entry, or delete a key:

```java
Cache.ValueWrapper wrapper = cache.get(bookId);
cache.put(bookId, value);
cache.evict(bookId);
```

use **Spring `Cache`**. Calling native map `put/remove` instead of `Cache.put/evict` can bypass adapter logic and cause discrepancies in null adaptation, key serialization, transaction awareness, or metrics.

## 5. Specific characteristics of `ConcurrentMapCache`

`ConcurrentMapCache` is a simple implementation backed by a `ConcurrentMap` in the JVM. It is useful for tests and small apps, but has limits:

- **Local process:** the same cache name in two different JVMs does not guarantee shared entries.
- **No built-in TTL/TTI contract:** `ConcurrentHashMap` does not automatically expire keys after N seconds.
- **No distributed replication:** restarting the JVM loses in-memory cache data.
- **No size/cost-based eviction** like specialized cache providers.
- **Null value conversion:** by default, the Spring adapter may replace `null` with an internal sentinel because `ConcurrentHashMap` does not store `null` directly.
- **Native map is the live state:** calling `map.clear()` or `map.remove(key)` bypasses Spring's `Cache` path.

Check snippet:

```java
Cache cache = Objects.requireNonNull(cacheManager.getCache("books"));

if (cache instanceof ConcurrentMapCache mapCache) {
    ConcurrentMap<Object, Object> nativeMap = mapCache.getNativeCache();
    System.out.println(nativeMap.size());
}
```

*Illustrative snippet requiring imports `org.springframework.cache.concurrent.ConcurrentMapCache`, `ConcurrentMap`, `Objects`, and a suitable manager bean.*

This explicitly expresses a dependency on **Spring ConcurrentMapCache** and is no longer provider-agnostic code.

### 5.1. Why can reading raw values differ from `cache.get`?

When caching `null` is allowed:

```java
cache.put("missing-book", null);
Cache.ValueWrapper wrapper = cache.get("missing-book");
Object raw = ((ConcurrentMapCache) cache)
    .getNativeCache()
    .get("missing-book");
```

*Illustrative snippet, only valid for a `ConcurrentMapCache` allowing nulls.*

- `wrapper` is **non-null**: the cache has a mapping.
- `wrapper.get()` returns `null`: the business value has been converted back from the sentinel.
- `raw` may be an **internal object**, not `null` as business code expects.

Do not fetch raw values and cast directly `(Book) raw` when the adapter may store sentinels or use store-by-value/serialization. Bypassing the conversion layer can cause type errors, wrong null semantics, or leak implementation details.

### 5.2. Is collecting statistics via `size()` strictly reliable?

`ConcurrentMap.size()` is a Java map operation, but in a system with concurrent writes, the number reflects only a point-in-time observation; do not treat it as a transactional snapshot of the entire system. It also measures only **one JVM**. If the goal is measuring hits/misses or cache cost, consider provider-supported metrics rather than merely counting raw map entries.

## 6. Specific characteristics of Caffeine

Caffeine is a specialized local caching library that can support policies such as maximum size, time-based TTL/TTI, eviction, statistics, and async caches depending on how it is built.

With Spring's `CaffeineCache`, the native API in Spring Framework 6.x versions can be obtained as follows:

```java
// Illustrative code for Spring CaffeineCache only.
if (cache instanceof CaffeineCache caffeineCache) {
    com.github.benmanes.caffeine.cache.Cache<Object, Object> nativeCache =
        caffeineCache.getNativeCache();

    long estimated = nativeCache.estimatedSize();
    System.out.println("Estimated entries: " + estimated);
}
```

*This snippet does not compile standalone; it requires the Spring Caffeine adapter, the Caffeine library, imports, and a matching `Cache` instance.*

Example configuring the Caffeine backend via `CaffeineCacheManager`:

```java
@Bean
CacheManager cacheManager() {
    CaffeineCacheManager manager = new CaffeineCacheManager("books");
    manager.setCaffeine(
        Caffeine.newBuilder()
            .maximumSize(10_000)
            .expireAfterWrite(Duration.ofMinutes(5))
            .recordStats()
    );
    return manager;
}
```

*This is an illustrative bean requiring the `com.github.ben-manes.caffeine:caffeine` dependency and importing `Caffeine`, `CaffeineCacheManager`, `Duration`, `CacheManager`, and `Bean`. Do not replace the bean in the section 8 runnable example with this snippet without adding the dependency.*

Points to note:

1. `estimatedSize()` is an **estimated** size of the Caffeine cache, not a universal statistics contract.
2. `nativeCache.stats()` is only meaningful when the provider is configured to record statistics (such as `recordStats()`); complete data is not automatically available in every environment.
3. `nativeCache.policy()` exposes Caffeine's native policy controls, though APIs and availability depend on version/configuration.
4. Reading/writing directly through the native cache can bypass Spring adaptation layers, such as null-value handling.
5. For caches built from an async cache, `CaffeineCache.getAsyncCache()` is a separate API and may fail if no async cache is present; `getNativeCache()` does not mean it always returns an `AsyncCache`.
6. Caffeine in local configuration does not automatically become a distributed cache even when using the same cache region name across multiple nodes.

When TTL or maximum size is needed **only at the infrastructure level**, configuring the provider as above is usually better than accessing the native cache inside business methods.

## 7. Specific characteristics of Redis cache

When using Spring Data Redis, you typically have `RedisCacheManager` and `RedisCache`. The `getNativeCache()` API of `RedisCache` in documented Spring Data Redis versions returns **`RedisCacheWriter`**:

```java
// Illustrative code specific to Spring Data Redis.
if (cache instanceof RedisCache redisCache) {
    RedisCacheWriter writer = redisCache.getNativeCache();
    System.out.println("Redis writer available: " + (writer != null));
}
```

*This snippet is not a standalone runnable demo; it requires the Spring Data Redis dependency, `RedisCache` and `RedisCacheWriter` imports, and an actual cache of type `RedisCache`.*

Specifically:

- `RedisCacheWriter` is a **byte-oriented cache writer** layer for Redis, not a general-purpose `RedisTemplate`.
- Keys in Redis typically have **cache-name prefixes**, serializers, and custom conversions; `books::B42` may be one representation, not a universal rule.
- Code calling `writer.put(...)` or Redis commands directly must take responsibility for key/value conversion, TTL, prefixes, network errors, and data-format compatibility.
- `RedisCacheConfiguration`/`RedisCacheManager` supports configuring TTL, null caching, key prefixes, and serializers at the infrastructure level. **Instead of hunting for a raw client via `getNativeCache()` to set TTL per request, prefer the proper configuration API.**
- Redis has network latency, serialization, and replication concerns completely different from ConcurrentMap/Caffeine. Casting to `ConcurrentMap` makes no sense.
- A `RedisCache` in an application can also sit under a transaction-aware decorator, so the outer Spring `Cache` object does not necessarily have the exact runtime class `RedisCache`.

### 7.1. TTL configuration belongs in the provider

Illustrative example for Spring Data Redis:

```java
RedisCacheConfiguration config =
    RedisCacheConfiguration.defaultCacheConfig()
        .entryTtl(Duration.ofMinutes(2))
        .disableCachingNullValues();
```

*This snippet requires adding the Spring Data Redis dependency, importing `RedisCacheConfiguration`/`Duration`, and passing the config to `RedisCacheManager`; on its own it does not create a cache manager.*

When different policies are needed per cache name or entry content, use version-appropriate provider configuration/TTL functions rather than manipulating raw bytes on the writer directly inside business services.

### 7.2. Do not assume the same native API for all Redis clients

Even when Redis sits behind the scenes, the native object from the Spring Cache adapter **is not necessarily** a `RedisConnection`, `RedisTemplate`, `Jedis`, or `StatefulRedisConnection`. Abstractions serve different purposes. If the real need is executing specialized Redis commands, inject the appropriate Redis tool in a **dedicated infrastructure adapter** rather than abusing `getNativeCache()` as a service locator.

## 8. Complete Java 17+ demo: observing the native map while still using the Spring Cache API

The standalone runnable example uses Java 17, Maven, Spring Boot 3.3.5, and `ConcurrentMapCacheManager`. It demonstrates:

1. Retrieving a `Cache` via `CacheManager`.
2. Calling `getNativeCache()` and **checking the type** instead of casting blindly.
3. Calling `@Cacheable` on a Spring-managed bean to create an entry.
4. Comparing the entry via Spring `Cache.get` and key presence in the native `ConcurrentMap`.
5. Evicting via **Spring `Cache.evict`**, then observing the entry disappear from the map.
6. Calling the method again and seeing the body execute due to a cache miss.

### 8.1. Project structure

```text
native-cache-demo/
├── pom.xml
└── src/main/java/example/nativecache/
    ├── NativeCacheApplication.java
    └── BookService.java
```

### 8.2. File `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>native-cache-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-cache</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 8.3. File `src/main/java/example/nativecache/BookService.java`

```java
package example.nativecache;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class BookService {
    private final AtomicInteger loads = new AtomicInteger();

    @Cacheable(cacheNames = "books", key = "#p0")
    public String findTitle(String bookId) {
        int n = loads.incrementAndGet();
        System.out.println("METHOD_LOAD #" + n + " " + bookId);
        return "TITLE:" + bookId;
    }
}
```

### 8.4. File `src/main/java/example/nativecache/NativeCacheApplication.java`

```java
package example.nativecache;

import java.util.Objects;
import java.util.concurrent.ConcurrentMap;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class NativeCacheApplication {
    public static void main(String[] args) {
        SpringApplication.run(NativeCacheApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("books");
    }

    @Bean
    CommandLineRunner demo(CacheManager manager, BookService books) {
        return args -> {
            Cache cache = Objects.requireNonNull(
                manager.getCache("books"),
                "Cache books not found"
            );

            System.out.println("SPRING_NAME=" + cache.getName());

            Object nativeObject = cache.getNativeCache();
            System.out.println(
                "NATIVE_IS_CONCURRENT_MAP=" +
                (nativeObject instanceof ConcurrentMap<?, ?>)
            );

            if (!(nativeObject instanceof ConcurrentMap<?, ?> nativeMap)) {
                throw new IllegalStateException("Not a ConcurrentMap cache");
            }

            // Read entry state through the Spring abstraction.
            System.out.println("ENTRY_BEFORE=" + (cache.get("A") != null));

            System.out.println("READ1=" + books.findTitle("A"));
            System.out.println("READ2=" + books.findTitle("A"));

            // Inspect the native map only; do not mutate it.
            System.out.println("RAW_HAS_A=" + nativeMap.containsKey("A"));
            System.out.println("RAW_SIZE=" + nativeMap.size());
            System.out.println(
                "ABSTRACTION_VALUE=" +
                Objects.requireNonNull(cache.get("A")).get()
            );

            // Evict via Spring Cache API to preserve the abstraction boundary.
            cache.evict("A");
            System.out.println(
                "RAW_AFTER_EVICT=" + nativeMap.containsKey("A")
            );

            System.out.println("READ3=" + books.findTitle("A"));
            System.out.println("RAW_END_SIZE=" + nativeMap.size());
        };
    }
}
```

### 8.5. Running and expected output

Inside the `native-cache-demo` directory, JDK 17+, Maven, and initial dependency download capability are required:

```bash
mvn spring-boot:run
```

Lines from the demo application, **excluding Spring Boot startup logs**, in order:

```text
SPRING_NAME=books
NATIVE_IS_CONCURRENT_MAP=true
ENTRY_BEFORE=false
METHOD_LOAD #1 A
READ1=TITLE:A
READ2=TITLE:A
RAW_HAS_A=true
RAW_SIZE=1
ABSTRACTION_VALUE=TITLE:A
RAW_AFTER_EVICT=false
METHOD_LOAD #2 A
READ3=TITLE:A
RAW_END_SIZE=1
```

### 8.6. Stdout analysis

**Step 1:** the `ConcurrentMapCacheManager("books")` bean creates a cache named `books`. `cache.getName()` prints `books`. The real native object of `ConcurrentMapCache` is a `ConcurrentMap`, so `instanceof` returns `true`.

**Step 2:** before calling `BookService`, `cache.get("A")` returns `null` (miss), so `ENTRY_BEFORE=false`.

**Step 3:** the first `books.findTitle("A")` call goes through the Spring cache proxy, misses, runs the method, prints `METHOD_LOAD #1 A`, and returns `TITLE:A`. `@Cacheable` stores the value under key `A` of the `books` cache. The second call hits, returning the same value **without printing `METHOD_LOAD #2`**.

**Step 4:** the native map shows key `A` is present and the total entry count is 1. `Cache.get("A").get()` returns the value through the abstraction as `TITLE:A`. These results hold because the demo knows the exact provider is `ConcurrentMapCache`, with no other threads or TTL.

**Step 5:** `cache.evict("A")` deletes the key via the Spring API. The native map reflects that the key is gone (`RAW_AFTER_EVICT=false`). Calling `findTitle("A")` again misses, runs the method a second time, and writes the entry again; the map finishes with one entry.

**Why the demo does not fail due to self-invocation:** `BookService` is a Spring bean, injected into `CommandLineRunner`, and called from another bean through the proxy. `@EnableCaching` activates caching infrastructure; `@Cacheable` on a public method is a concrete operation. The program does not call `this.findTitle()` internally within the same service.

**Comparing with other providers:** all parts obtaining `Cache`, calling `get`, `evict`, and using annotations can remain unchanged if switching to another provider, but the `instanceof ConcurrentMap` branch and `containsKey`/`size` calls **will no longer work**. Hence the example includes an explicit guard and applies only to the manager created in the demo.

## 9. What `getNativeCache()` does NOT guarantee

### 9.1. Does not guarantee portable TTL or expiration

Spring `Cache` has no standard method such as:

```java
// Hypothetical API, DOES NOT exist on org.springframework.cache.Cache:
cache.setTtlForKey("A", Duration.ofSeconds(30));
```

TTL, time-to-idle, and eviction policies belong to the provider. `getNativeCache()` may give access to a specific provider's own mechanism, **but does not standardize how it is used**. Proper configuration usually is:

- Caffeine: builder with `expireAfterWrite`, `expireAfterAccess`, `maximumSize`, and matching policies.
- Redis: `RedisCacheConfiguration`, `RedisCacheManager`, and version-appropriate TTL functions/configs.
- `ConcurrentMapCache`: has no automatic TTL; if TTL is required, use a supporting provider or build another abstraction.

### 9.2. Does not guarantee identical null semantics

Spring `Cache` can adapt `null` via a sentinel. The native store may not hold a true `null`, or the backend may have a different null policy. **Reading a raw map or raw Redis bytes reads the storage-layer representation**, not necessarily the logical Java value.

With `Cache.ValueWrapper`:

```java
Cache.ValueWrapper wrapper = cache.get("A");

if (wrapper == null) {
    System.out.println("MISS");
} else if (wrapper.get() == null) {
    System.out.println("HIT_CACHED_NULL");
} else {
    System.out.println("HIT_VALUE");
}
```

*Illustrative snippet inside a method with a `cache` variable; distinguishing miss/hit-null uses the standard `Cache` API without needing native access.*

### 9.3. Does not guarantee a common key representation

A key produced by `@Cacheable(key = "#p0")` may be a Java object in a local map, or converted into bytes/strings with a prefix/cache namespace when stored in Redis. The native API does not necessarily use **keys in the same form** as Spring `Cache.get(Object key)`.

For example, with a Redis cache using cache-name prefixes, `books::A` may be the physical key depending on configuration. Code hitting Redis directly with key `A` will not automatically refer to the same entry. Changing serializers, conversion services, or prefix policies can also make keys from the two access paths incompatible.

### 9.4. Does not guarantee cross-process atomicity and synchronization

The atomicity of `putIfAbsent`, protection against cache stampedes, locking, replication delay, and consistency all depend on the implementation. A local `ConcurrentMap` behaves differently from Redis over the network. If you access the native API to leverage a specific atomic operation, state your concurrency assumptions explicitly and write integration tests with the real backend.

### 9.5. Does not guarantee accurate metrics and sizes

`Map.size()`, Caffeine `estimatedSize()`, and Redis statistics come from different sources:

- Some sizes are only approximations due to concurrent updates/maintenance.
- Some counters are **app-instance** statistics, not global server stats.
- Some providers require enabling `recordStats()` or dedicated metric collection options.
- With Redis, a cache name typically maps to many physical keys; a native object cannot be treated as a Java container of all entries.

Do not build a multi-provider dashboard by forcing every native object into a `Map`.

### 9.6. Does not guarantee persistence, eviction, or cluster topology

A local map does not preserve entries across restarts. Caffeine has its own local policies. Redis has configurable topology, memory policies, persistence, and replication; these do not "materialize" as a portable contract via `getNativeCache()`.

If an application switches backends across dev/test/prod, treat that as a **change in operational semantics**, not merely swapping a class behind an interface.

### 9.7. Does not guarantee transaction awareness if the adapter is bypassed

Suppose Spring is using `TransactionAwareCacheManagerProxy` or a decorator deferring `put/evict` until transaction commit. If code grabs the native object and writes directly, it can **bypass the decorator**, causing the cache to change before the database commits or even when the transaction rolls back.

Therefore, do not use the native API to "work around" after-commit requirements in business services. Design using transaction synchronization, provider configuration, or explicit invariants, and test against a real transaction manager.

## 10. What risks come with manipulating the native API directly?

### 10.1. Raw writes can corrupt representations

An example **not to copy into business code**:

```java
// Anti-pattern: strongly coupled to ConcurrentMapCache.
ConcurrentMap<Object, Object> raw =
    ((ConcurrentMapCache) cache).getNativeCache();

raw.put("A", someRawObject);
```

Depending on how `someRawObject` was created, that operation can:

- bypass `null`/sentinel conversion;
- bypass store-by-value/serialization;
- bypass the transaction-aware decorator;
- bypass metrics or callbacks of the cache implementation;
- cause Spring logic to read data with the wrong type or structure.

If the goal is simply storing a return value:

```java
cache.put("A", value);
```

it is both clearer and respects the abstraction.

### 10.2. Wrappers and `instanceof` checks

A statement like:

```java
if (cache instanceof ConcurrentMapCache cmc) {
    // ...
}
```

only runs if the **current Spring `Cache` instance** is actually that type. If the manager returned a `TransactionAwareCacheDecorator`, the check can evaluate to false even though the underlying backend uses ConcurrentMap. Conversely, `cache.getNativeCache()` may return a different native object depending on the wrapper.

**Do not bypass wrappers with reflection** to force access to internal fields. If native access is mandatory, let an infrastructure adapter have direct access to the exact provider configured by the application, with explicit contracts and tests.

### 10.3. Security and sensitive data

Raw caches may contain serialized data, tokens, customer identifiers, or internal payloads. Printing `nativeCache.toString()` or dumping all entries in production easily leaks secrets. Prefer aggregated metrics and mask identifying data; never expose native objects through REST APIs.

### 10.4. Dependency and upgrade risks

If a business module imports `CaffeineCache` or `RedisCacheWriter`, that module becomes tied to the provider and Spring adapter versions. A major upgrade can change return types, serializers, configuration, or async support. A lower-risk dependency layout is to **isolate all provider-specific code inside an infrastructure module**.

## 11. Designing an adapter when native access is unavoidable

Instead of letting every service know about `getNativeCache()`, define an interface around the **required capability**:

```java
public interface CacheDiagnostics {
    String cacheName();
    boolean supportsSizeInspection();
    long estimatedEntryCount();
}
```

*This is a standalone Java interface illustrating the design; an implementation is needed to run it.*

An implementation dedicated solely to `ConcurrentMapCache`:

```java
public final class ConcurrentMapCacheDiagnostics implements CacheDiagnostics {
    private final ConcurrentMapCache cache;

    public ConcurrentMapCacheDiagnostics(ConcurrentMapCache cache) {
        this.cache = cache;
    }

    @Override
    public String cacheName() {
        return cache.getName();
    }

    @Override
    public boolean supportsSizeInspection() {
        return true;
    }

    @Override
    public long estimatedEntryCount() {
        return cache.getNativeCache().size();
    }
}
```

*This is an illustrative class; it requires importing the `CacheDiagnostics` interface defined above and Spring's `ConcurrentMapCache`. It is not automatically present as a component unless registered as a bean in the application.*

For Caffeine, another implementation can call `estimatedSize()`; for Redis, it might only provide backend-supported statistical metrics without pretending to know exact entry counts.

This design ensures:

1. Business code depends on **capabilities**, not provider classes.
2. "Unsupported" cases are expressed explicitly instead of throwing `ClassCastException`.
3. Small tests can mock `CacheDiagnostics`, while integration tests verify each provider.
4. Switching backends does not require editing every business service.
5. There is a clear place for metrics, timeouts, access control, caching policies, and alerts.

In the API example above, define clearly within what scope `estimatedEntryCount()` returns an estimate and how stale it can be; never use it as a condition for security or transactional decisions.

## 12. How to test provider-dependent code

### 12.1. Testing the common Spring Cache contract

For every backend supported by the application, verify:

- `getCache(name)` returns an actual cache when the name is valid.
- `getName()` matches the logical name.
- `get(key) == null` on miss; distinguish null-containing hits using `ValueWrapper` when the provider allows it.
- `put`/`get`/`evict` behave according to expected contracts.
- `@Cacheable` method hits skip the body when called through the proxy.
- Cache names and key expressions across `@Cacheable`, `@CachePut`, and `@CacheEvict` are compatible.

### 12.2. Testing native features per provider

**ConcurrentMap:**

- Verify the native object is a `ConcurrentMap`.
- Verify size/containsKey after non-concurrent put/evict calls.
- Do not assume entries expire automatically.

**Caffeine:**

- Verify maximum size, TTL, and `recordStats()` configuration.
- Verify `estimatedSize()`/`stats()` per provider documentation.
- Test async characteristics if an actual `AsyncCache` is used.

**Redis:**

- Verify TTL/key prefix/serializer against real Redis or an appropriate test container.
- Test connection errors and timeouts; do not assume operations are always local.
- Verify write-through/invalidation compatibility with transactions and multiple instances.

### 12.3. Upgrade / provider-swap tests

A worthwhile anti-coupling test:

```text
Given: business service uses only org.springframework.cache.Cache
When: replacing ConcurrentMapCacheManager with another valid provider
Then: get/put/evict business behavior remains correct

Given: component has native diagnostic for ConcurrentMap
When: using RedisCache
Then: component returns "unsupported" or picks the Redis adapter
      instead of crashing with ClassCastException
```

Not every backend is required to support every native feature. What matters is **detecting capabilities and reacting intentionally**.

## 13. Self-check questions

**Question 1.** What is the return type of `Cache.getNativeCache()` on the Spring interface?

**Answer:** `Object`. Implementations may narrow the return type, but there is no single unified Java interface across all native backends.

**Question 2.** Can `ConcurrentMapCache.getNativeCache()` be cast to `ConcurrentMap`?

**Answer:** Yes, with the matching Spring `ConcurrentMapCache` implementation: the Javadoc returns `ConcurrentMap<Object,Object>`. Do not assume every Spring `Cache` does this.

**Question 3.** If you switch the backend to Caffeine, can you keep calling `ConcurrentMap.size()` on the native cache?

**Answer:** No. The native Caffeine cache uses a different API (such as `estimatedSize()`) and requires the corresponding dependency/configuration.

**Question 4.** Does `RedisCache.getNativeCache()` necessarily return a `RedisTemplate` or `RedisConnection`?

**Answer:** No. In documented versions of Spring Data Redis, it returns `RedisCacheWriter`. Read the Javadoc for the exact version.

**Question 5.** Can `getNativeCache()` be used as a portable way to set a TTL per entry?

**Answer:** No. TTL is not standardized via the native return type. Configure the provider or build a dedicated adapter.

**Question 6.** Why can `cache.get(key)` return `null` while the raw map has an entry?

**Answer:** `Cache.get(key)` returns `null` on a miss; if a cache hit holds a business `null` value, the wrapper can exist with `wrapper.get() == null`. The raw map may hold an internal sentinel in place of null.

**Question 7.** Should `cache.evict(key)` be replaced with `((Map) cache.getNativeCache()).remove(key)`?

**Answer:** Not in general logic: it is non-portable and can bypass adapters, wrappers, null handling, transaction awareness, and provider semantics.

**Question 8.** If a component only needs to estimate cache capacity, how should it be designed?

**Answer:** Use a capability/diagnostics interface with per-provider implementations and clear fallback rules. Do not assume every provider has `size()` with the same meaning.

**Question 9.** Why does calling `getNativeCache()` in a business service increase upgrade costs?

**Answer:** The business service becomes coupled to provider classes and APIs. Switching Redis/Caffeine/ConcurrentMap or upgrading versions can break casts, methods, and key/value assumptions.

## 14. Summary

- `getNativeCache()` is an **escape hatch** to access the object underneath `org.springframework.cache.Cache`.
- **The native type depends on the implementation**; there is no "universal native cache" sharing identical APIs across ConcurrentMap, Caffeine, and Redis.
- `ConcurrentMapCache` → `ConcurrentMap`; `CaffeineCache` → native Caffeine cache; `RedisCache` → in current versions, `RedisCacheWriter`.
- Use `Cache.get/put/evict` for general business operations. Only use native APIs when a **provider-specific feature** is needed with explicit guards/adapters/tests.
- TTL, statistics, serialization, concurrency, replication, null handling, and transaction behavior **are not fully standardized by `getNativeCache()`**.
- When changing backends, re-test both the abstraction contract and native branches; do not treat a dependency swap as merely a performance change.

## References

- Spring Framework Javadoc — `Cache`, `getNativeCache`, and `get/put/evict` APIs: https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/cache/Cache.html
- Spring Framework Javadoc — `ConcurrentMapCache`, native `ConcurrentMap`: https://docs.spring.io/spring-framework/docs/6.1.0-RC2/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCache.html
- Spring Framework Javadoc — `CaffeineCache`, `getNativeCache`, and `getAsyncCache`: https://docs.spring.io/spring-framework/docs/6.1.0-RC2/javadoc-api/org/springframework/cache/caffeine/CaffeineCache.html
- Spring Framework Reference — *Configuring the Cache Storage*: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
- Spring Framework Reference — *TTL/TTI/Eviction policy*: https://docs.spring.io/spring-framework/reference/integration/cache/specific-config.html
- Spring Data Redis Reference — `RedisCacheManager` and `RedisCacheConfiguration`: https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html
- Spring Data Redis Javadoc — `RedisCache`, `getNativeCache()`: https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/cache/RedisCache.html
