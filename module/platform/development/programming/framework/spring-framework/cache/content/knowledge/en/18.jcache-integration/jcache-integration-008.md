# Identifying When to Use Spring Cache vs. the JCache (JSR-107) Contract

> **Spring Framework – Cache Abstraction · Group: JCache.** This lesson guides how to choose between **Spring Cache** and **JCache (JSR-107)** based on actual system needs: framework coupling, portability across cache providers, annotation ergonomics, customizability, and keeping keys/invalidation consistent. Crucially, **choosing JCache annotations does not mean you must use a JCache backend**.

## 1. Decision Summary

**Choose Spring Cache** when the application runs primarily inside Spring/Spring Boot, needs method-level caching via `@Cacheable`, `@CachePut`, `@CacheEvict`, relies on SpEL `key`, `condition`, `unless`, `@Caching`, or already has stable `CacheManager`/`CacheResolver` infrastructure.

**Consider the JCache (JSR-107) contract** when a library or module needs a standard caching API **without direct Spring coupling**, when an organization mandates that cache providers expose `javax.cache` interfaces, or when you need JSR-107-modeled features such as `CachingProvider`, typed `Cache<K,V>`, `ExpiryPolicy`, entry processors, event listeners, or `@CacheResult` annotations.

Neither choice guarantees fresh data or identical performance across providers. Both are **abstraction contracts**, while TTL, memory limits, distribution, consistency, serialization, and transactions depend on configuration and the backing store.

### Guiding Questions

1. Does the code **run outside Spring**? If yes, the Java-standard JCache API may be a better contract.
2. Does the application need **SpEL and Spring-specific annotations**? If yes, Spring Cache is usually more convenient.
3. Is there a requirement that all cache providers **comply with JSR-107**? If yes, select a real JCache provider, not merely JCache annotations.
4. Are you already on Spring Cache with an existing backend and only want to switch annotations to JSR-107? You can keep the existing backend thanks to **Spring's JCache annotation support**.
5. Do update and read methods **share the exact same key**? Switching annotations while forgetting key generators easily causes stale caches.

## 2. What Are Spring Cache and JCache Actually?

### 2.1. Spring Cache Abstraction

Spring provides the primary APIs:

- `org.springframework.cache.Cache` and `org.springframework.cache.CacheManager`: abstraction layer for accessing and managing cache regions.
- `org.springframework.cache.annotation.Cacheable`, `CachePut`, `CacheEvict`, `Caching`, `CacheConfig`: declarative caching behavior.
- `@EnableCaching` and caching interceptors: activate annotation processing on Spring-managed beans.

Example:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public String findProduct(String productId) {
    return repository.findName(productId);
}
~~~

This is an **illustrative method snippet** requiring a service with a real `repository`, `@EnableCaching`, and a valid `CacheManager`.

Spring Cache is **not a cache storage product itself**. It ships adapters for multiple backends such as Caffeine, Redis (via Spring Data), `ConcurrentMapCache`, and JCache providers. Swapping backends can have minimal impact on business annotations once cache names, keys, serialization, and operational policies are reviewed.

### 2.2. JCache / JSR-107

**JCache** is the Java caching standard, also known as **JSR-107 / Java Temporary Caching API**. In Spring Framework 6.2, the standard namespace remains **`javax.cache`**—do not change it to `jakarta.cache` simply because many other APIs moved to Jakarta.

JCache defines:

- `javax.cache.Cache<K,V>`: typed key/value cache API.
- `javax.cache.CacheManager`: manages cache regions by name and configuration.
- `javax.cache.Caching` and `javax.cache.spi.CachingProvider`: bootstrap a JSR-107 implementation.
- `javax.cache.configuration.MutableConfiguration` and `javax.cache.expiry.ExpiryPolicy`: baseline standard policies.
- Annotations `javax.cache.annotation.CacheResult`, `CachePut`, `CacheRemove`, `CacheRemoveAll`, `CacheDefaults`, `CacheKey`, and `CacheValue`.
- Extension points such as `CacheLoader`, `CacheWriter`, event listeners, and `EntryProcessor` within the JCache API scope.

JCache is a **contract specification**, not a cache engine. Simply placing `javax.cache:cache-api` on the classpath **does not provide a working cache backend**. If using `Caching.getCachingProvider()` directly, the application needs a matching **JSR-107 provider** on the classpath plus provider cache configuration.

JCache also does not require Spring. That is why a library seeking minimal Spring coupling may consider this standard.

## 3. Two Independent Selection Axes: Annotations and Backend

This is the core point of the lesson. Distinguish:

**Axis A – Application-level annotations and caching interception:**

- Spring: `@Cacheable`, `@CacheEvict`, `@CachePut` from `org.springframework.cache.annotation`.
- JSR-107: `@CacheResult`, `@CacheRemove`, `@CachePut` from `javax.cache.annotation`.

**Axis B – Actual cache data storage:**

- Spring provider adapters: `ConcurrentMapCacheManager`, `CaffeineCacheManager`, `RedisCacheManager`, or other adapters.
- JCache-compliant provider: concrete implementation of `javax.cache.CacheManager`, used directly or via Spring's `JCacheCacheManager` adapter.

Matrix:

| Annotations Used | Actual Backend | Possible? | Notes |
| --- | --- | --- | --- |
| Spring `@Cacheable` | Caffeine via `CaffeineCacheManager` | Yes | Spring manages interception; Caffeine stores entries |
| Spring `@Cacheable` | JSR-107 provider via `JCacheCacheManager` | Yes | Spring Cache abstraction runs on a JCache backend |
| JSR-107 `@CacheResult` | Spring `ConcurrentMapCacheManager` | Yes in Spring | Spring's JCache annotation support routes operations to Spring Cache |
| JSR-107 `@CacheResult` | JSR-107 provider | Yes | Works in Spring or any environment with JCache interception |

**Conclusion:** "Using JCache annotations" and "using a JCache provider" are **two separate decisions**. When inspecting a real application, check **annotation imports**, **registered `CacheManager`**, and **active runtime provider** rather than guessing from cache names.

Spring Framework supports JSR-107 annotations when the standard API and required support module are on the classpath. Hence a project already using Spring Cache can adopt JSR-107 annotations while keeping its existing storage. Conversely, a JSR-107 backend can still be accessed via Spring annotations.

## 4. Comparing Spring Annotations and JSR-107 Annotations

| Need | Spring Cache | JCache (JSR-107) | Important Note |
| --- | --- | --- | --- |
| Cache method result | `@Cacheable` | `@CacheResult` | Both handle hit/miss, yet keys/exceptions differ |
| Write value into cache | `@CachePut` | `@CachePut` | Same annotation name, **different semantics** |
| Evict a single entry | `@CacheEvict` by key | `@CacheRemove` | Keys must match the reader's keys |
| Clear entire cache | `@CacheEvict(allEntries=true)` | `@CacheRemoveAll` | Avoid clearing the whole region when one record changes |
| Class-level shared config | `@CacheConfig` | `@CacheDefaults` | Scopes and attributes are not completely identical |
| Custom keys | SpEL `key`, Spring `KeyGenerator` | `@CacheKey`, JCache `CacheKeyGenerator` | Default keys may not share the same object/`equals` |
| Parameter-based conditions | Spring `condition`, `unless` | No 1:1 SpEL equivalent | Pick the API matching real requirements |
| Exception caching | No single annotation feature covering all of JCache | `@CacheResult` supports `cachedExceptions`, `nonCachedExceptions`, `exceptionCacheName` | Must understand exception cache lifetime |
| Force method execution | `@CachePut` or appropriate design | `@CacheResult(skipGet=true)` | Do not conflate these patterns |
| Group multiple cache operations | `@Caching` supports multiple operations | Standard JCache annotations use a different model | Spring is convenient when one method updates multiple regions |

### 4.1. `@Cacheable` and `@CacheResult`

Spring:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public String find(String isbn) {
    return repository.findName(isbn);
}
~~~

JSR-107:

~~~java
@CacheResult(cacheName = "books")
public String find(@CacheKey String isbn) {
    return repository.findName(isbn);
}
~~~

Both are **illustrative integration snippets** requiring a repository and caching interception. They share the **goal** of caching method results, yet their default key construction systems differ. JCache `@CacheKey` selects which parameters enter the key when multiple parameters exist.

JCache `@CacheResult` provides `skipGet`: it skips pre-invocation lookup per the annotation contract, fitting cases where method execution must be forced. It also supports selective exception caching; evaluate that carefully so transient errors are not cached for too long.

Spring `@Cacheable` offers flexible SpEL, for example:

~~~java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    condition = "#p0 != null",
    unless = "#result == null"
)
public String find(String isbn) {
    return repository.findName(isbn);
}
~~~

This snippet illustrates a Spring method with a real repository. `condition` decides whether caching applies; `unless` evaluates after execution and can veto storing the result. JSR-107 lacks equivalent SpEL `condition`/`unless` syntax.

### 4.2. Two Annotations Sharing the Name `@CachePut` with Different Meanings

Spring:

~~~java
@org.springframework.cache.annotation.CachePut(
    cacheNames = "books", key = "#p0"
)
public String update(String isbn, String newTitle) {
    repository.rename(isbn, newTitle);
    return newTitle;
}
~~~

Spring **always executes the method** and puts **the method's return value** into the cache. This illustrative snippet assumes the cached value is the title string.

JSR-107:

~~~java
@javax.cache.annotation.CachePut(cacheName = "books")
public void update(
        @CacheKey String isbn,
        @CacheValue String newTitle
) {
    repository.rename(isbn, newTitle);
}
~~~

Here JCache puts **the argument annotated with `@CacheValue`**, not the return value as Spring does. It supports configuring put timing before/after invocation per the contract. During migration, you cannot simply swap the `CachePut` import and expect semantics to stay unchanged.

### 4.3. Evicting One Key vs. Clearing an Entire Region

Spring commonly uses:

~~~java
@CacheEvict(cacheNames = "books", key = "#p0")
public void rename(String isbn, String newTitle) {
    repository.rename(isbn, newTitle);
}
~~~

JSR-107 uses:

~~~java
@CacheRemove(cacheName = "books")
public void rename(@CacheKey String isbn, String newTitle) {
    repository.rename(isbn, newTitle);
}
~~~

Both illustrative snippets require a repository. By intent, both delete the ISBN key after a successful update under default settings, yet JCache's exception policies and before/after-invocation options do not align 100% with Spring.

To clear an entire region, Spring uses `@CacheEvict(allEntries=true)`; JCache uses `@CacheRemoveAll`. Never apply blind automated conversions without verifying behavior.

## 5. Key Generation: Where Migrations Most Commonly Fail

Matching the **cache name** is not enough. An entry is only found or evicted if the key matches in **type and equality semantics** used by the cache provider.

### 5.1. Spring Default

Spring's `SimpleKeyGenerator` typically chooses:

- No arguments → `SimpleKey.EMPTY`.
- One non-null argument → the argument itself.
- Multiple arguments → a `SimpleKey` wrapping the parameters.

For example, for single-argument `find(String isbn)`, Spring can use the `"BK-1"` string itself as the key unless another expression or key generator is configured.

### 5.2. JCache Default

JCache's default `CacheKeyGenerator` relies on the selected arguments. Without `@CacheKey`, **all eligible arguments** participate. With one or more `@CacheKey` annotations, only the annotated arguments participate per the JCache contract.

A JCache implementation can produce a **generated key object** (such as a wrapper) even for a single argument. Therefore, never assume Spring's default key `"BK-1"` equals JCache's generated key for the same ISBN.

### 5.3. Pitfalls When Mixing Annotations on a Shared Cache

Example:

~~~java
// Spring-based reader: logical key is the isbn string.
@Cacheable(cacheNames = "books", key = "#p0")
public String read(String isbn) {
    return repository.findName(isbn);
}

// JCache-based writer: key is built by the JCache generator.
@CacheRemove(cacheName = "books")
public void rename(@CacheKey String isbn, String newTitle) {
    repository.rename(isbn, newTitle);
}
~~~

These are two illustrative integration methods. Despite sharing cache name `"books"`, **there is no guarantee** `@CacheRemove` removes the entry written by `@Cacheable`, due to **two different key strategies**. On mismatch, stale data continues to be served.

**How to handle this:**

1. Prefer **one consistent annotation style within a single cache region**.
2. If forced to mix during migration, document cache names, key types, and `equals()/hashCode()`/serialization behavior explicitly.
3. Configure compatible `KeyGenerator` or `CacheKeyGenerator` implementations so both sides produce identical keys.
4. Write integration tests against the real backend: read → update → verify old entry is evicted → read again and receive fresh source data.
5. Do not validate behavior solely via a single-method counter if the cache handles multiple tenants or key variants.

**Do not place `@Cacheable` and `@CacheResult` on the same method simultaneously** unless you have a very specific reason and test exact advice ordering. Keeping one deliberate annotation style per place is easier to maintain and avoids overlapping cache operations.

## 6. Runnable Java 17+ Example: Two Annotation Sets, One Spring Cache Backend

Goal of this example: use **no JCache provider**, yet run JSR-107 `@CacheResult`/`@CacheRemove` annotations alongside Spring `@Cacheable`/`@CacheEvict`. Spring executes caching advice for both annotation groups, backed by `ConcurrentMapCacheManager`.

The example runs with **Java 17+**, **Spring Framework 6.2.14**, and `javax.cache:cache-api:1.1.1`. These are illustrative versions for Spring 6.2; in real projects, align dependency versions and test against your active versions.

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
    implementation 'org.springframework:spring-context-support:6.2.14'
    implementation 'javax.cache:cache-api:1.1.1'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.SpringVsJCacheDemo'
}
~~~

**File `src/main/java/demo/SpringVsJCacheDemo.java`:**

~~~java
package demo;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import javax.cache.annotation.CacheKey;
import javax.cache.annotation.CacheRemove;
import javax.cache.annotation.CacheResult;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class SpringVsJCacheDemo {

    public static class BookStore {
        private final Map<String, String> values =
                new ConcurrentHashMap<>(Map.of(
                        "S", "Spring-v1",
                        "J", "JCache-v1"
                ));

        public String find(String id) {
            return values.get(id);
        }

        public void rename(String id, String name) {
            values.put(id, name);
        }
    }

    public static class SpringService {
        private final BookStore store;
        private int loads;

        public SpringService(BookStore store) {
            this.store = store;
        }

        @Cacheable(cacheNames = "springBooks", key = "#p0")
        public String read(String id) {
            loads++;
            return store.find(id);
        }

        @CacheEvict(cacheNames = "springBooks", key = "#p0")
        public void rename(String id, String newName) {
            store.rename(id, newName);
        }

        public int loads() {
            return loads;
        }
    }

    public static class StandardService {
        private final BookStore store;
        private int loads;

        public StandardService(BookStore store) {
            this.store = store;
        }

        @CacheResult(cacheName = "jcacheBooks")
        public String read(@CacheKey String id) {
            loads++;
            return store.find(id);
        }

        @CacheRemove(cacheName = "jcacheBooks")
        public void rename(@CacheKey String id, String newName) {
            store.rename(id, newName);
        }

        public int loads() {
            return loads;
        }
    }

    @Configuration
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager(
                    "springBooks", "jcacheBooks"
            );
        }

        @Bean
        public BookStore bookStore() {
            return new BookStore();
        }

        @Bean
        public SpringService springService(BookStore store) {
            return new SpringService(store);
        }

        @Bean
        public StandardService standardService(BookStore store) {
            return new StandardService(store);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            SpringService spring = context.getBean(SpringService.class);
            StandardService standard = context.getBean(StandardService.class);

            System.out.println("spring first: " + spring.read("S"));
            System.out.println("spring again: " + spring.read("S"));
            System.out.println("spring loads: " + spring.loads());

            spring.rename("S", "Spring-v2");
            System.out.println("spring updated: " + spring.read("S"));
            System.out.println("spring loads final: " + spring.loads());

            System.out.println("jcache first: " + standard.read("J"));
            System.out.println("jcache again: " + standard.read("J"));
            System.out.println("jcache loads: " + standard.loads());

            standard.rename("J", "JCache-v2");
            System.out.println("jcache updated: " + standard.read("J"));
            System.out.println("jcache loads final: " + standard.loads());
        }
    }
}
~~~

Run with JDK 17+ and a compatible Gradle version:

~~~bash
gradle run --quiet
~~~

**Expected stdout from the program** (excluding Gradle logs):

~~~text
spring first: Spring-v1
spring again: Spring-v1
spring loads: 1
spring updated: Spring-v2
spring loads final: 2
jcache first: JCache-v1
jcache again: JCache-v1
jcache loads: 1
jcache updated: JCache-v2
jcache loads final: 2
~~~

### Why Does It Produce This Output?

1. `Config` defines one Spring `ConcurrentMapCacheManager` with two independent cache regions. There is no `javax.cache.spi.CachingProvider` in this example.
2. `SpringService.read("S")` is intercepted by Spring `@Cacheable`; first call misses and second hits, leaving the service's load count at 1.
3. `SpringService.rename("S", "Spring-v2")` updates `BookStore` and `@CacheEvict` deletes the String key `"S"` from `springBooks`. The next read misses and reloads, making the count 2.
4. `StandardService.read("J")` uses JSR-107 `@CacheResult`, detected by Spring because `cache-api` and `spring-context-support` are present. First call misses, second hits; count is 1.
5. `StandardService.rename(@CacheKey "J", "JCache-v2")` uses `@CacheRemove`. Annotating `@CacheKey` ensures only the ID forms the key for both reads and writes within the **same JCache style**. The next read misses, loads V2, and count reaches 2.
6. Because two separate cache names are used, the example **does not claim** default Spring and JCache keys share a representation; instead, it deliberately avoids mixing keys inside one region.

**Operating conditions:** services are Spring-managed beans with `public`, non-`final` methods; the caller retrieves beans from `ApplicationContext` and invokes them via proxy. Calling `this.read(id)` directly from another method on the same target bypasses caching advice in proxy mode.

**Limitations:** this is a single-JVM application without transactions or a database. Output is deduced from the code and Spring/JCache contracts for this configuration; run integration tests in real projects whenever providers, interceptors, or dependencies differ.

## 7. How Do You Configure a Real JCache Backend When Needed?

When the requirement calls for a **JSR-107 provider contract**, Spring offers `org.springframework.cache.jcache.JCacheCacheManager` to wrap a provider's `javax.cache.CacheManager`.

Typical integration stack:

~~~text
Spring @Cacheable / @CacheEvict
            |
Spring CacheManager: JCacheCacheManager
            |
javax.cache.CacheManager (real provider)
            |
    JCache-compliant cache backend
~~~

Spring configuration example:

~~~java
import javax.cache.Caching;
import javax.cache.spi.CachingProvider;

import org.springframework.cache.jcache.JCacheCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class JCacheProviderConfig {

    @Bean
    public javax.cache.CacheManager jCacheManager() {
        CachingProvider provider = Caching.getCachingProvider();
        return provider.getCacheManager();
    }

    @Bean
    public org.springframework.cache.CacheManager cacheManager(
            javax.cache.CacheManager jCacheManager
    ) {
        return new JCacheCacheManager(jCacheManager);
    }
}
~~~

**This is an integration configuration snippet**, not a standalone program. Beyond `javax.cache:cache-api`, the project must add a **JCache provider implementation** and set up the provider's cache regions. `Caching.getCachingProvider()` will not work with the API JAR alone if no provider is available; if multiple providers exist, select the intended one via explicit configuration or bootstrap parameters.

**Important class name distinction:**

- `javax.cache.CacheManager`: manager from the **JCache specification**.
- `org.springframework.cache.CacheManager`: manager from the **Spring Cache Abstraction**.
- `JCacheCacheManager`: Spring adapter wrapping a JCache manager. Similar names, different interfaces.

You can use Spring annotations with this adapter. You can also use JSR-107 annotations via Spring caching interception with this adapter, provided you choose a clear annotation and key strategy.

### Accessing JCache Directly Without Going Through Spring Cache

A plain Java module can use:

~~~java
javax.cache.spi.CachingProvider provider =
        javax.cache.Caching.getCachingProvider();
javax.cache.CacheManager manager = provider.getCacheManager();
javax.cache.Cache<String, String> cache =
        manager.getCache("books", String.class, String.class);

if (cache == null) {
    throw new IllegalStateException("Required JCache cache 'books' missing");
}
cache.put("BK-1", "Java Basics");
String title = cache.get("BK-1");
~~~

This integration snippet requires a real provider configured with a typed cache named `books`. It requires no Spring `ApplicationContext`. When using the JCache API directly, lifecycle, closing, serialization, expiry, and exception handling must follow the provider contract.

**Do not equate JCache with distributed caching.** A JCache provider may store data in local memory or support clustering. JSR-107 compliance alone does not guarantee cluster replication, cross-instance consistency, or durability.

## 8. When Is Each Choice More Appropriate?

### Case A: Pure Spring Boot Project Caching Repository Reads

**Prefer Spring Cache.** The team already uses `@EnableCaching`/Boot caching auto-configuration, `@Cacheable`, SpEL keys, and `@CacheEvict`. Adding JSR-107 annotations brings no clear benefit without a cross-framework standardization requirement.

Example: an API looking up products by SKU that must evict on rename, include tenant ID in the key, handle null caching explicitly, and use `unless`. Spring annotations express this very directly.

### Case B: Java Library Used by Both Spring and Plain Java SE Applications

**Consider the JCache standard contract** in the shared module. `javax.cache.Cache`/`CacheManager` lets the library talk to a standard provider without importing `org.springframework.cache`. However, classes using JSR-107 annotations still need **an interception-capable environment** for annotations to run automatically; annotations do not activate merely because the JVM loads them.

Add adapters at the application boundary if Spring consumes the library. Avoid leaking both Spring Cache and JCache details into the library unless necessary.

### Case C: Organization Requires Swapping Across Multiple JCache-Compliant Providers

**The JCache contract** fits the provider layer. Test actual portability: TTL/expiry configuration, store-by-value vs. store-by-reference, serialization, entry processors, transactions, monitoring, and performance can all vary.

If the application still needs SpEL, **Spring annotations + `JCacheCacheManager`** is a valid combination; you do not have to rewrite every source annotation to JSR-107.

### Case D: Spring Project Already Using Caffeine Wants JSR-107 Annotations

You can use **Spring-supported JSR-107 annotations** while continuing to use `CaffeineCacheManager`. Add the JCache API and required Spring module, and **keep keys and cache names behaviorally consistent**. Do not assume you must find a Caffeine JCache provider solely because you imported `@CacheResult`.

### Case E: Need Declarative Exception Caching

JCache `@CacheResult` supports caching selected exceptions via `cachedExceptions` and a dedicated exception cache region. This can be a reason to pick JCache annotations, provided you separate **permanent errors** (e.g., invalid ID) from **transient errors** (e.g., network timeouts). Caching transient errors without proper TTLs amplifies outages.

### Case F: System Requires Async/Reactive Caching, Multi-Cache Operations, or Complex SpEL

**Spring Cache** generally fits better when application boundaries live inside Spring and need Spring's API/annotations. However, async/reactive support depends on **Spring version and cache provider**—do not assume all caches behave identically. Verify `CompletableFuture`/reactive return paths, lookup, TTL, and threading behavior on the real backend.

### Case G: Team Migrating Away from Spring Toward a Standalone Library

Do not swap annotations blindly. Evaluate:

- Which Spring APIs are used in domain code.
- Which Spring `@Cacheable` features have no JCache equivalent.
- Key generators and exception behavior.
- How interceptors run and how providers are managed without Spring.
- Tests proving caching behaves identically before and after migration.

**Guiding rule:** choose the **lowest-commitment contract sufficient** for the module. If an application is entirely Spring-based, do not add another standard layer just for different annotation names. If a library must remain Spring-independent, keep Spring integration at the edges rather than spreading `org.springframework.cache` across public APIs.

## 9. Problems Not Solved Merely by Choosing an API

### 9.1. Caching Does Not Automatically Keep Data Fresh After Updates

Both Spring Cache and JCache can serve stale data if the application updates the source without invalidating the right key. `@CacheEvict` or `@CacheRemove` removes entries on demand, yet neither monitors the database, batch jobs, or external services automatically.

If updates occur inside a transaction, check **commit timing** vs. eviction timing; a method returning normally does not guarantee the transaction has committed. Under concurrent readers, a race can occur where one reader loads stale data and writes it after eviction.

### 9.2. Provider-Specific Behavior and Portability

JSR-107 standardizes interfaces, **not every operational detail**. For example:

- Expiry/TTL has standard configuration, yet defaults and advanced options depend on the provider.
- Distribution, replication, consistency, and off-JVM memory management are not guaranteed by interfaces alone.
- `storeByValue`/`storeByReference`, serialization, and typed caches must be verified with the chosen implementation.
- Metrics, management, event listeners, and cache loaders must be validated against the backend and configuration.
- Switching providers can change hit ratios, latency, event ordering, and error handling.

The same holds for Spring Cache: switching from a local map to Redis may require rethinking key serialization and null handling even when annotations stay identical.

### 9.3. Proxies, Self-Invocation, and Interception

In Spring's default proxy mode, both Spring annotations and Spring-integrated JSR-107 annotations require calls to pass through the caching interceptor. Calling an annotated method on the same target via `this.find("BK-1")` normally **bypasses advice**. Split services or invoke through the proper proxy.

When using JCache annotations outside Spring, you need a matching interceptor implementation. Annotations alone are metadata and cannot execute caching by themselves.

### 9.4. Nulls, Mutable Objects, and Tenant Leaks

Never rely solely on API names to assume nulls are always cached or objects are deep-copied. Null policies and store-by-value behavior depend on the Spring adapter and provider.

Especially, keys must capture all dimensions affecting data—such as tenant, locale, currency, or permission context—whenever those vary the output. Never share one entry across tenants just because IDs collide.

Immutable DTOs or well-defined value objects are generally safer cache values than mutable JPA entities or lazy proxies. Never use JCache or Spring Cache as a substitute for access control.

## 10. Project Decision Checklist

| Question | If "Yes" | Direction |
| --- | --- | --- |
| Does the entire module run inside Spring? | Yes | Start with Spring Cache |
| Do you need SpEL `condition`/`unless`/multi-cache annotations? | Yes | Spring annotations are usually clearer |
| Must the library run without Spring? | Yes | Consider JCache API or a domain-neutral interface |
| Must the provider comply with JSR-107? | Yes | Pick a concrete JCache provider and verify SPI |
| Only want JSR-107 annotations inside Spring? | Yes | Use Spring's JCache annotation support without switching providers |
| Need standard declarative exception caching? | Yes | Evaluate `@CacheResult`, exception cache, and TTL |
| Multiple annotation styles on the same region? | Yes | Test and align key generators before rollout |
| New backend with different semantics (TTL/null/serialization)? | Yes | Write integration tests against the real backend |

**Safe rollout practices:**

1. Document both the **annotation axis** and **provider axis** in design docs.
2. Define cache names, key schemas, TTL/invalidation, null policies, and acceptable consistency levels.
3. Choose Spring annotations or JSR-107 annotations based on the contract the team must maintain.
4. Avoid mixing styles in one region; if unavoidable, standardize keys and write interoperability tests.
5. Test against the real backend: hit/miss, post-update eviction, exceptions, concurrency, serialization, and transaction boundaries.
6. Monitor hit/miss ratios, stale reads, load errors, eviction rates, and memory footprint after deployment.

## 11. Common Mistakes

| Mistake | Why It Is Wrong | Fix |
| --- | --- | --- |
| "Using `@CacheResult` requires a JCache backend" | Spring supports JSR-107 annotations on its own cache abstraction | Separate annotations from storage providers |
| "Adding `javax.cache:cache-api` makes caching work" | The API JAR contains no provider implementation | Add a JCache provider when bootstrapping via JCache SPI |
| "Spring 6 must import `jakarta.cache`" | JSR-107 in Spring 6.2 still uses `javax.cache` | Use the namespace matching the JCache artifact |
| "`@CachePut` shares the same name so semantics are identical" | Spring uses return value; JCache uses `@CacheValue` argument | Review method signatures and cached values |
| "Spring read + JCache remove on the same region always match keys" | Default key generation may differ in type/`equals` | Share a key strategy and write tests |
| "A JCache provider is always a distributed cache" | API compliance does not dictate topology | Check deployment, replication, and consistency |
| "Swapping annotations completes migration" | Interceptors, dependencies, keys, and error policies still differ | Build a migration plan with integration tests |
| "Annotations work when calling `this.read(id)`" | Proxy mode skips self-invocation | Invoke through the Spring proxy bean |
| "Service errors should be cached as long as normal results" | Transient failures differ from permanent errors | Choose `cachedExceptions` carefully with proper TTLs |
| "Swapping backends needs no re-testing" | Serialization, null, and expiry behavior may differ | Run contract/integration tests on the new provider |

## 12. Self-Check Exercises

**Exercise 1.** A Spring Boot application only needs to cache repository reads, wants `unless = "#result == null"`, and uses SpEL keys. What should you choose?

**Answer:** Usually **Spring Cache annotations**, since they provide these features directly. Pick the backend according to system load and data policies.

**Exercise 2.** A Spring-independent Java SE library needs a standard cache interface implemented by multiple providers. What is a sensible choice?

**Answer:** Consider **JCache `javax.cache`** with a JSR-107 provider. Still verify actual compatibility, especially beyond the portable subset.

**Exercise 3.** You already use `@CacheResult` on a Spring service. Must you replace Caffeine with Ehcache or a JCache provider?

**Answer:** No. With Spring's JSR-107 annotation support enabled, the annotations can run on your existing Spring `CacheManager`.

**Exercise 4.** Why can a Spring `key = "#p0"` reader and a JCache `@CacheKey` writer with the same ID still fail to invalidate the right entry?

**Answer:** Key generators may produce key objects of different types or representations. Verify equality, serialization, and unify the key strategy.

**Exercise 5.** Both ecosystems have `@CachePut`; what is the main difference?

**Answer:** Spring puts the **return value** into the cache; JCache puts the **parameter annotated with `@CacheValue`**.

**Exercise 6.** Does using `JCacheCacheManager` automatically guarantee distributed caching, strong consistency, and proper TTLs?

**Answer:** No. The adapter only connects Spring to the JCache manager; operational guarantees come from the provider and its configuration.

**Exercise 7.** A method puts both `@Cacheable` and `@CacheResult` to be "twice as safe". Should you do this?

**Answer:** Avoid doing so by default. Two interception models can overlap, causing unexpected lookups or puts; choose one style and verify behavior.

## 13. Key Takeaways and Official Documentation

**Quick takeaways:**

- **Spring Cache** is Spring's integrated abstraction with SpEL annotations/keys and many provider adapters.
- **JCache (JSR-107)** is a standard Java API/annotation contract in **`javax.cache`**, requiring a real provider when accessed via JCache SPI.
- **Annotations and backends are two separate axes.** Spring supports JSR-107 annotations on Spring `CacheManager`s; Spring `CacheManager` also adapts JCache providers.
- **Identical annotation names do not mean identical semantics**, especially `@CachePut`.
- **Default key generation differs**; standardize cache keys before mixing annotations or migrating.
- API choice **never replaces** testing TTL, nulls, serialization, transactions, concurrency, and tenant isolation.

**Official documentation for reference:**

- [Spring Framework – JCache (JSR-107) Annotations](https://docs.spring.io/spring-framework/reference/integration/cache/jsr-107.html)
- [Spring Framework 6.2 – Cache Abstraction](https://docs.spring.io/spring-framework/reference/6.2/integration/cache.html)
- [Spring Framework – Configuring Cache Storage / JSR-107](https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html)
- [Spring Framework 6.2 – `JCacheCacheManager` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/jcache/JCacheCacheManager.html)
- [JSR-107 JCache API 1.1.1](https://javadoc.io/doc/javax.cache/cache-api/1.1.1/index.html)
