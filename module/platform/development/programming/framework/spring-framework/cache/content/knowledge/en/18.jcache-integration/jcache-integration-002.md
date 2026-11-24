# Distinguishing javax.cache.Cache from org.springframework.cache.Cache

## 1. Two Interfaces with the Same Name Under Different Contracts

In Java projects using Spring and JCache, two common imports appear:

```java
import javax.cache.Cache;
import org.springframework.cache.Cache;
```

Both describe a key-based data store, but their goals differ:

- `javax.cache.Cache<K,V>` belongs to **JCache (JSR-107)**, a standard API for cache providers. It defines typed keys/values, entry management operations, loaders, listeners, configuration, and lifecycle.
- `org.springframework.cache.Cache` belongs to the **Spring Cache Abstraction**. It is a unified contract allowing Spring annotations and application code to work across different backends.

Spring provides the `JCacheCache` adapter to wrap a native JCache instance and `JCacheCacheManager` to wrap a native `javax.cache.CacheManager`. As a result, a JCache cache can be accessed through both APIs without necessarily creating two separate data stores.

This lesson helps you distinguish packages, data types, methods, null semantics, loaders, lifecycles, cache managers, how to bridge the two APIs, and common pitfalls. At the end, there is a runnable Java 17+ example using Ehcache 3 as the JCache provider and Spring as the adapter layer.

## 2. Identifying Packages and Roles

| Criterion | `javax.cache.Cache<K,V>` | `org.springframework.cache.Cache` |
| --- | --- | --- |
| Origin | JCache / JSR-107 | Spring Framework |
| Namespace | `javax.cache` | `org.springframework.cache` |
| Generics | Typed `K` and `V` | Not generic; keys/values treated as `Object` |
| Provider | JCache provider via `javax.cache.CacheManager` | Spring implementation or adapter |
| Purpose | Standard cache contract with JSR-107 configuration and features | Common cache contract for Spring annotations and applications |
| Retrieval | `getCache(name, keyType, valueType)` | `getCache(name)` |
| Null key/value | JCache disallows null keys or values | May support null depending on implementation/configuration |
| Signature API | `getAll`, `loadAll`, `invoke`, listeners, `unwrap`, `close` | `ValueWrapper`, typed get, `Callable` loader, `getNativeCache` |
| Scope | Usable outside Spring | Tied to the Spring ecosystem |

**Do not infer the backend from the interface name.** `org.springframework.cache.Cache` is not a specific storage engine; it can be backed by ConcurrentMap, Caffeine, Redis, a JCache adapter, or another provider. Likewise, `javax.cache.Cache` does not imply an in-RAM-only cache; the provider determines storage, expiration, clustering, and additional capabilities.

JCache 1.1.1 still uses the `javax.cache.*` package. In Spring Boot 3 / Spring Framework 6 projects, do not rename this namespace to `jakarta.cache.*`.

## 3. Comparing Key Operations

### 3.1. Reading and Checking Keys

JCache:

```java
javax.cache.Cache<String, String> cache = ...;

String value = cache.get("SKU-1");
boolean exists = cache.containsKey("SKU-1");
```

Spring:

```java
org.springframework.cache.Cache cache = ...;

org.springframework.cache.Cache.ValueWrapper wrapper =
        cache.get("SKU-1");

if (wrapper == null) {
    System.out.println("MISS");
} else {
    System.out.println("HIT: " + wrapper.get());
}
```

Differences:
- JCache returns type `V` directly. Because JCache forbids storing null values, `get(key) == null` indicates no cached value exists. If read-through is configured, a miss may trigger the loader.
- Spring's `get(key)` returns `Cache.ValueWrapper` or null. A null wrapper indicates a miss; an existing wrapper may hold a null business value if the implementation supports nulls.
- Spring also offers `get(key, Class<T>)` to retrieve the value directly; this overload does not distinguish a cached null from a miss.
- JCache provides `containsKey(key)` to check for a mapping without retrieving the value. When read-through is configured, `containsKey` checks the cache only and does not invoke the loader.

### 3.2. Writing, Replacing, and Deleting

| Need | JCache `javax.cache.Cache` | Spring `org.springframework.cache.Cache` |
| --- | --- | --- |
| Write or replace | `put(key, value)` | `put(key, value)` |
| Write only if absent | `putIfAbsent(key, value)` returning boolean | `putIfAbsent(key, value)` returning old ValueWrapper or null |
| Get multiple keys | `getAll(keys)` | No equivalent method in core interface |
| Write multiple keys | `putAll(map)` | No equivalent method in core interface |
| Get and put | `getAndPut(key, value)` | No method with the same name |
| Delete one key | `remove(key)` returning boolean | `evict(key)`; `evictIfPresent(key)` in supported versions |
| Delete multiple keys | `removeAll(keys)` | No equivalent method in core interface |
| Clear all entries | `removeAll()` or `clear()` | `clear()`; `invalidate()` in supported versions |

Identical method names do not guarantee identical return types or semantics. JCache's `putIfAbsent` returns a boolean; Spring's `putIfAbsent` returns a wrapper for the previous value, or null if the value was registered. Always verify the return type of the imported package.

Another difference: JCache `removeAll()` may notify listeners and invoke `CacheWriter` for each mapping; `clear()` removes contents without notifying listeners or `CacheWriter`. Do not assume these two methods are equivalent. The Spring abstraction provides `clear()` to empty the region; exact execution details depend on the provider.

### 3.3. Loading Data on Cache Miss

JCache can configure read-through with `CacheLoader`:

```java
javax.cache.Cache<String, String> cache = ...;
String value = cache.get("SKU-1");
```

If the cache is configured for read-through, reading a missing key may invoke a provider-managed loader. JCache also provides `loadAll(keys, replaceExistingValues, completionListener)` to request loading multiple keys using the provider's asynchronous mechanism.

Spring Cache provides a per-call loader overload:

```java
String value = cache.get("SKU-1", () -> repository.load("SKU-1"));
```

Spring accepts a `Callable<T>` directly at the call site. Where possible, implementations should synchronize loading so the same key is not computed repeatedly when multiple threads miss concurrently; exact support depends on the implementation.

Both mechanisms serve similar purposes but differ in configuration:
- JCache typically attaches the loader to the cache/provider configuration.
- Spring's abstraction accepts a loader per call via `Callable`.
- You cannot convert a JCache `CacheLoader` directly into a Spring `Callable` without accounting for lifecycle, exceptions, and concurrency semantics.

### 3.4. Configuration, Observation, and Lifecycle

JCache offers standardized capabilities that the core Spring `Cache` interface does not expose directly:
- `registerCacheEntryListener(...)` and `deregisterCacheEntryListener(...)`.
- `getConfiguration(...)` to read cache configuration.
- `invoke(key, EntryProcessor, ...)` to process an entry through the provider's entry processor API.
- `unwrap(Class<T>)` to access a concrete implementation.
- `getCacheManager()`, `isClosed()`, and `close()` for lifecycle management.

Spring Cache focuses on common abstraction operations. It offers `getName()` and `getNativeCache()`; the latter is the escape hatch to the underlying provider. Using native APIs via `getNativeCache()` ties code to a specific implementation and reduces portability.

## 4. Null Semantics: The Most Error-Prone Difference

### 4.1. JCache Does Not Accept Null Keys or Null Values

Per JCache 1.1.1, operations using a null key or null value throw `NullPointerException`. A native cache has no standard contract for "key exists with a null value".

```java
javax.cache.Cache<String, String> nativeCache = ...;

nativeCache.put("missing", null); // NullPointerException per JCache
nativeCache.get(null);            // NullPointerException per JCache
```

Because null values are invalid, `nativeCache.get(key) == null` can represent the absence of an entry (or that a read-through loader produced no value). If business logic needs to cache a "not found" result, use a sentinel or DTO representing the not-found state.

### 4.2. Spring Abstraction Can Represent Cached Nulls

Spring Cache is designed for Java methods that may return null. `Cache.ValueWrapper` distinguishes:

```java
Cache.ValueWrapper wrapper = springCache.get("user:42");

if (wrapper == null) {
    // No entry.
} else if (wrapper.get() == null) {
    // Entry exists; business value is null.
}
```

Actual null storage support depends on implementation and configuration. Some caches use an internal marker to store null even when the native store forbids nulls.

### 4.3. When Spring Uses the JCache Adapter

Spring provides `JCacheCache` and `JCacheCacheManager`. By default, `JCacheCacheManager` allows Spring to convert business nulls into an internal holder before writing to JCache; native JCache still never accepts nulls directly under JSR-107.

If the same cache is accessed through both the Spring wrapper and the JCache API:
- Consider `JCacheCacheManager.setAllowNullValues(false)` to preserve JCache's null contract.
- If null support remains enabled in the Spring wrapper, do not arbitrarily read or write null-adapted entries via the native API. The native stored value may be Spring's holder rather than a JCache null.
- Do not cache nulls if the backend/provider does not support the conversion or if cache type constraints are incompatible.
- For negative caching, define TTL and eviction when the record eventually appears to avoid serving "not found" for too long.

This is a design decision to settle early, especially when multiple modules access one region through both APIs.

## 5. Both CacheManagers Are Also Different Interfaces

The name `CacheManager` collides as well:

| API | Interface | Primary Responsibility |
| --- | --- | --- |
| JCache | `javax.cache.CacheManager` | Create, look up, list, and destroy native caches; manage provider and lifecycle |
| Spring | `org.springframework.cache.CacheManager` | Supply caches by name to the Spring abstraction and cache interceptors |

A JCache manager provides operations such as `createCache(name, configuration)`, `getCache(name)`, `destroyCache(name)`, `getCacheNames()`, and `close()`. A Spring manager primarily provides `getCache(name)` and `getCacheNames()`.

Spring provides adapters to bridge the two systems:

```text
JCache provider
     |
javax.cache.CacheManager
     |
javax.cache.Cache<K,V>
     |
     v
JCacheCacheManager  (Spring adapter)
     |
JCacheCache         (Spring wrapper)
     |
org.springframework.cache.Cache
     |
Spring @Cacheable / @CacheEvict / application code
```

Specifically:
- `JCacheCache` implements `org.springframework.cache.Cache` on top of a `javax.cache.Cache` instance.
- `JCacheCacheManager` implements `org.springframework.cache.CacheManager` backed by a `javax.cache.CacheManager`.
- `springCache.getNativeCache()` gives access to the underlying JCache cache used by the wrapper.

When using the adapter, **there are not necessarily two independent cache stores**. The Spring Cache wrapper and native JCache can be two API views over the same cache instance.

## 6. Which API Should You Choose for Each Scenario?

| Scenario | Reasonable Choice |
| --- | --- |
| Services using `@Cacheable`/`@CacheEvict` wanting provider-agnostic code | `org.springframework.cache.Cache` via Spring CacheManager |
| Java application needing JSR-107 standard without Spring dependency | `javax.cache.Cache<K,V>` |
| Need EntryProcessor, CacheEntryListener, read-through/write-through, or JCache-specific operations | Native JCache API |
| Existing JCache provider integrating into Spring | `JCacheCacheManager` and `JCacheCache` adapter |
| Need to share a region between native code and Spring annotations | Use the adapter and align cache name, key type, key generation, and null policy |
| Need only basic abstraction with swappable backends | Spring Cache abstraction |
| Need provider-specific capabilities | Access native cache selectively via `getNativeCache()` |

**Recommendation:** keep business code on the Spring abstraction unless specialized features are needed. Restrict native JCache access to adapters or services with a clear reason so the rest of the application stays decoupled from the provider.

### 6.1. Watch Out for Key Generation

Native JCache can declare key/value types, such as `Cache<String, Product>`. The Spring abstraction accepts `Object` keys, and annotations may generate default keys from multiple parameters.

If a Spring method writes key `SimpleKey(productId, locale)` while native code reads String key `productId`, both sides are accessing **two different mappings** despite sharing the same cache name.

When sharing a region:
- Choose one common key rule.
- Use `@Cacheable(key = "#p0")` or an appropriate `KeyGenerator` if the native API uses the same key.
- Ensure key/value types are compatible with the JCache configuration.
- Align serialization, tenant prefixes, versioning, and null policies.
- Test both reading from Spring after a native write and reading natively after a Spring write.

### 6.2. Watch Out for Identical Annotation Names

Spring and JCache also share annotation names across different packages and semantics. For example:
- Spring `@Cacheable` is similar to JCache `@CacheResult`.
- Spring `@CachePut` and JCache `@CachePut` differ: JCache requires a `@CacheValue` parameter to specify the written value; Spring typically caches the method return value.
- Spring `@CacheEvict` is similar to JCache `@CacheRemove`; clearing all entries corresponds closely to `@CacheRemoveAll`.
- Spring `@CacheConfig` is similar to JCache `@CacheDefaults`.

Spring Framework supports JCache annotations when the JCache API and `spring-context-support` are on the classpath. You can use JCache annotations with Spring's caching abstraction without changing the cache store. If multiple annotations target the same region, align key generation and cache names.

## 7. Runnable Java 17+ Example: One Native JCache, Two Access Paths

This example uses Ehcache 3 as the JCache provider, Spring Cache as the adapter layer, and a service annotated with `@Cacheable`. It demonstrates:
1. Native JCache can read/write the cache directly.
2. The Spring Cache wrapper sees entries written via JCache.
3. Native JCache sees entries written via the Spring wrapper.
4. Spring annotations continue using the same JCache region through `JCacheCacheManager`.

### 7.1. Project Structure

```text
jcache-spring-bridge/
  settings.gradle
  build.gradle
  src/main/java/demo/jcache/JCacheBridgeDemo.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'jcache-spring-bridge'
```

File `build.gradle`:

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
    implementation 'org.ehcache:ehcache:3.10.8'
    implementation 'javax.cache:cache-api:1.1.1'
}

application {
    mainClass = 'demo.jcache.JCacheBridgeDemo'
}
```

Ehcache 3 provides a JCache provider; `javax.cache:cache-api` supplies the JSR-107 interfaces. Spring Boot starter cache brings in Spring cache support, including JCache integration. The example uses Java 17+ and requires no HTTP server or database.

### 7.2. Complete Java Source

File `src/main/java/demo/jcache/JCacheBridgeDemo.java`:

```java
package demo.jcache;

import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import javax.cache.Cache;
import javax.cache.CacheManager;
import javax.cache.Caching;
import javax.cache.configuration.MutableConfiguration;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.jcache.JCacheCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class JCacheBridgeDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class CacheConfig {

        @Bean(destroyMethod = "close")
        CacheManager nativeJCacheManager() {
            CacheManager manager = Caching.getCachingProvider(
                    "org.ehcache.jsr107.EhcacheCachingProvider")
                    .getCacheManager();

            if (manager.getCache("products") == null) {
                MutableConfiguration<String, String> configuration =
                        new MutableConfiguration<String, String>()
                                .setTypes(String.class, String.class);

                manager.createCache("products", configuration);
            }
            return manager;
        }

        @Bean
        org.springframework.cache.CacheManager cacheManager(
                CacheManager nativeJCacheManager) {
            JCacheCacheManager adapter =
                    new JCacheCacheManager(nativeJCacheManager);

            // Preserve JCache semantics: native JCache does not allow null values.
            adapter.setAllowNullValues(false);
            return adapter;
        }

        @Bean
        ProductService productService() {
            return new ProductService();
        }
    }

    public static class ProductService {
        private final AtomicInteger calls = new AtomicInteger();

        @Cacheable(cacheNames = "products", key = "#p0")
        public String load(String sku) {
            return sku + "-load-" + calls.incrementAndGet();
        }

        public int callCount() {
            return calls.get();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(CacheConfig.class)) {

            CacheManager nativeManager =
                    context.getBean("nativeJCacheManager", CacheManager.class);

            org.springframework.cache.CacheManager springManager =
                    context.getBean(org.springframework.cache.CacheManager.class);

            Cache<String, String> nativeCache =
                    nativeManager.getCache(
                            "products", String.class, String.class);

            org.springframework.cache.Cache springCache =
                    Objects.requireNonNull(
                            springManager.getCache("products"));

            System.out.println("sameNativeCache="
                    + (springCache.getNativeCache() == nativeCache));

            // Write via native JCache, read via Spring Cache.
            nativeCache.put("native-key", "from-jcache");
            System.out.println("nativeContains="
                    + nativeCache.containsKey("native-key"));
            System.out.println("nativeGet="
                    + nativeCache.get("native-key"));
            System.out.println("springReadsNative="
                    + springCache.get("native-key", String.class));

            // Write via Spring Cache, read via native JCache.
            springCache.put("spring-key", "from-spring");
            System.out.println("jcacheReadsSpring="
                    + nativeCache.get("spring-key"));

            // Spring annotation uses the same cache region.
            ProductService service = context.getBean(ProductService.class);
            System.out.println("first=" + service.load("SKU-1"));
            System.out.println("second=" + service.load("SKU-1"));
            System.out.println("methodCalls=" + service.callCount());
        }
    }
}
```

Run from the project directory with JDK 17+ and Gradle:

```bash
gradle run --quiet
```

If using the Gradle Wrapper, run `./gradlew run --quiet`; on Windows, run `gradlew.bat run --quiet`.

Lines printed by the application (excluding Gradle/framework logs):

```text
sameNativeCache=true
nativeContains=true
nativeGet=from-jcache
springReadsNative=from-jcache
jcacheReadsSpring=from-spring
first=SKU-1-load-1
second=SKU-1-load-1
methodCalls=1
```

### 7.3. Output Explanation

1. `sameNativeCache=true`: Spring `JCacheCache` wraps the exact native JCache instance retrieved from `javax.cache.CacheManager`.
2. `nativeContains=true` and `nativeGet=from-jcache`: direct reads and writes through the JCache API succeed.
3. `springReadsNative=from-jcache`: the Spring adapter sees data written natively because both use the same region and key.
4. `jcacheReadsSpring=from-spring`: native JCache reads data written by the Spring Cache wrapper.
5. `first=SKU-1-load-1` and `second=SKU-1-load-1`: the service is called twice with the same key, and `@Cacheable` hits on the second call so the method body runs only once.
6. `methodCalls=1` confirms the Spring caching interceptor is active. The service is obtained from the Spring context; instantiating `new ProductService()` manually or using self-invocation would bypass the cache proxy.

The example uses `String` keys and values so both APIs share compatible types. In real applications, verify serializers, key generators, null adaptation, and provider configuration before mixing both APIs.

## 8. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Imported wrong `Cache` | Both packages define an interface with the same name | Import the package explicitly or use fully qualified names |
| Imported wrong `CacheManager` | Both JCache and Spring define this interface | Use a fully qualified name for one of them |
| JCache `put(key, null)` throws an exception | JSR-107 forbids null keys/values | Use a sentinel/DTO or an explicit Spring null-adapter policy |
| Spring wrapper stores null but native code fails reading | Spring may use an internal holder to adapt null | Set `allowNullValues=false` for native compatibility or avoid reading null entries natively |
| Spring and native read different values | Key generation, key type, cache name, or serializer differs | Standardize keys, names, types, and serialization |
| `getNativeCache()` cannot be cast | Different underlying provider or wrapper than expected | Verify the cache manager and native cache type |
| `getCache(name)` returns null | Region has not been created or name is misspelled | Create the cache with the JCache manager beforehand or configure on-demand creation |
| Annotations have no effect | Missing `@EnableCaching`, non-Spring bean, or self-invocation | Check `ApplicationContext` and proxy configuration |
| Cache provider not found | Missing JCache provider or ambiguous multiple providers | Add the concrete provider; specify the provider class explicitly if needed |
| Runtime type exception | Key/value does not match JCache generic configuration | Use matching types and test directly with the provider |
| Closing manager renders cache unusable | Using a cache after the native manager was closed | Manage lifecycle through the Spring container |

### 8.1. Avoid Two Managers Backed by Separate Native Stores

An architectural mistake is creating:
- One `javax.cache.CacheManager` for native JCache code.
- Another `JCacheCacheManager` that initializes its own independent native manager.

Even if both managers use the same provider and region name, they may have different URIs, classloaders, or configurations. To share entries, create **one native JCache manager** and inject it into Spring's `JCacheCacheManager` adapter as shown in the example.

### 8.2. Watch Out for Spring's Default Key

Spring may generate a `SimpleKey` from multiple parameters. A native JCache cache may be configured as `Cache<String, Product>`. If the Spring key is not a String, the provider may throw a `ClassCastException` or the two APIs may observe separate entries.

Use an explicit compatible key, such as `@Cacheable(cacheNames="products", key="#p0")`, when native code uses the product ID directly as a String key.

## 9. Selection and Testing Checklist

Before integrating both APIs:

1. **Identify the primary contract:** do business modules depend on Spring Cache or native JCache?
2. **Identify the provider:** Ehcache, Hazelcast, Infinispan, or another JCache implementation; verify version and actual capabilities.
3. **Wire the adapter properly:** `JCacheCacheManager` must wrap the exact native `javax.cache.CacheManager` to be shared.
4. **Standardize region names:** cache names in annotations must match native region names.
5. **Standardize keys:** key types and values produced by Spring must be compatible with native JCache configuration.
6. **Decide null handling:** native JCache forbids nulls; the Spring adapter can convert nulls via a holder. Establish a clear policy.
7. **Verify lifecycle:** close the native manager only after services and cache wrappers no longer use it.
8. **Verify hit/miss:** write natively then read via Spring; write via Spring then read natively.
9. **Verify annotations:** invoke through the Spring proxy bean and measure body execution counts.
10. **Verify provider features:** TTL, listeners, read-through/write-through, statistics, serialization, and multi-node consistency.
11. **Verify failure cases:** provider unavailable, wrong cache name, wrong key/value type, manager closed.
12. **Evaluate performance vs. coupling:** provider-specific native APIs can optimize one use case while coupling code to the vendor; keep boundaries clear.

## 10. Self-Check Questions

**Q1.** Are `javax.cache.Cache<K,V>` and `org.springframework.cache.Cache` the same interface moved to a different package?

**Answer:** No. JCache is the JSR-107 standard with generic keys/values and provider APIs; Spring Cache is a separate abstraction for Spring integration.

**Q2.** Why does JCache `get(key)` returning null mean something different from Spring `get(key)` returning null?

**Answer:** JCache forbids null values, so null normally indicates a miss. Spring returns a null wrapper on a miss, whereas a non-null wrapper may contain a null business value.

**Q3.** Can a native JCache cache be used with Spring `@Cacheable`?

**Answer:** Yes. Use `JCacheCacheManager` to wrap `javax.cache.CacheManager`; Spring will use the `JCacheCache` adapter for the corresponding region.

**Q4.** What does `getNativeCache()` do?

**Answer:** It returns the underlying native cache provider wrapped by Spring, allowing provider-specific API usage at the cost of vendor coupling.

**Q5.** Do JCache `putIfAbsent` and Spring `putIfAbsent` share the same return type?

**Answer:** No. JCache returns a boolean; Spring returns the existing `ValueWrapper` or null per Spring Cache's contract.

**Q6.** Why should you avoid Spring's default key if native JCache requires String keys?

**Answer:** Spring may create a `SimpleKey` from multiple parameters; the native cache expects type-compatible keys. Both sides must agree on key generation and key types.

**Q7.** JCache disallows nulls, so can the Spring adapter still cache nulls?

**Answer:** Spring's JCache adapter can convert null into an internal holder when allowed; the native API never accepts raw nulls directly. If mixing both APIs, define an explicit null policy.

## 11. Key Takeaways

- `javax.cache.Cache<K,V>` is the **native JCache/JSR-107 API**, generic, with loaders, listeners, `EntryProcessor`, and lifecycle methods.
- `org.springframework.cache.Cache` is the **Spring abstraction**, non-generic, supporting wrappers, typed gets, and `Callable` loaders.
- `JCacheCache` wraps one native JCache cache; `JCacheCacheManager` wraps a native JCache `CacheManager`.
- JCache forbids null keys/values; Spring's abstraction can support nulls depending on implementation and configuration.
- When using both APIs on the same region, align **cache names, keys, types, serialization, and null policies**.
- Use the Spring abstraction for portability; reach for native JCache only when JSR-107 features are genuinely required.

### Official References

- [JCache 1.1.1 — javax.cache.Cache Javadoc](https://javadoc.io/static/javax.cache/cache-api/1.1.1/javax/cache/Cache.html)
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework — JCache (JSR-107) Annotations](https://docs.spring.io/spring-framework/reference/integration/cache/jsr-107.html)
- [Spring Framework — Configuring the Cache Storage / JCache](https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html)
- [Spring Framework — JCacheCache Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/jcache/JCacheCache.html)
- [Spring Framework — JCacheCacheManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/jcache/JCacheCacheManager.html)
- [Spring Boot — Caching](https://docs.spring.io/spring-boot/reference/io/caching.html)
