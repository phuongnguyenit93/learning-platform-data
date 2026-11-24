# Fundamentals and Learning Path for Spring Cache

## Lesson Objectives

After this lesson, you can explain why applications need caching, distinguish cache hits/misses from the origin data source, describe how Spring Cache intercepts method calls, choose appropriately among `@Cacheable`, `@CachePut`, and `@CacheEvict`, and organize a learning path from simple examples to testing and operations. This is the foundational lesson of the **Overview** group, so it prioritizes mental models and practice order before diving deep into individual cache provider configurations.

Recommended prerequisites: Java 17+, classes/methods and collections, Spring beans/Dependency Injection concepts; basic familiarity with request → service → repository/database. Basic understanding of Spring AOP/proxies will help explain cases where annotations do not execute.

## 1. What Is a Cache and When Is It Worth Using?

A cache temporarily stores frequently accessed results or data so subsequent requests are served faster, reducing expensive operations like database queries, remote service calls, or computations. **The origin data source (source of truth)** remains the authority for correct values; the cache is a copy that can be stale and can be deleted and recreated.

Example: `getProduct("P01")` takes 80 ms to read from the database. With the same key `P01`, the first call is a **cache miss**: run the method, read the source, and put the result into the cache. The second call is a **cache hit**: return the value from the cache without running the method body. The 80 ms figure is illustrative only, not a performance guarantee.

| Concept | Accurate Understanding |
| --- | --- |
| Cache entry | A key → value pair inside a named cache. |
| Cache key | Identity of the data to retrieve; two calls should share a key only when they can legitimately share the same result. |
| Hit / miss | Suitable value exists in cache / must fetch or compute from source. |
| Invalidation / eviction | Removing one or more entries so subsequent reads reload. |
| TTL (time to live) | Lifespan of an entry per cache provider policy, if configured. |
| Stale data | Value in the cache that no longer matches the origin data. |
| Cache stampede | Many requests miss the same key concurrently and hit the origin simultaneously. |

**Consider caching** when reads repeat often, results are fairly stable, reloading is expensive, and update rules/data lag are acceptable. **Do not cache by default** data requiring strict real-time accuracy, user-sensitive data if keys do not distinguish tenant/permissions, or cheap computations with very low repetition. Caching trades off added complexity in consistency, memory, and operational observability.

Scope distinction: **Spring Cache** primarily caches method invocation results inside the application; it does not automatically replace HTTP caching (`Cache-Control`/ETag), ORM second-level caches, or database storage design.

## 2. What Does Spring Cache Provide?

Spring Cache is an **abstraction**: it defines how to request caching, without deciding the storage engine or expiration policy itself. Two interfaces to remember:

- `org.springframework.cache.Cache`: operations on a specific cache, such as getting/putting/evicting entries.
- `org.springframework.cache.CacheManager`: manages and looks up caches by name, e.g., the `products` cache.

When `@EnableCaching` is enabled and a Spring bean method is invoked **through a proxy**:

1. Spring resolves the cache and key per the annotation.
2. With `@Cacheable`, it checks the cache. **Hit:** returns the stored value without running the method body. **Miss:** runs the method body, then caches eligible results before returning.
3. With `@CachePut`, it always runs the method and updates the cache with the return value.
4. With `@CacheEvict`, it deletes entries according to the annotation's rules.

`@EnableCaching` only enables the advice mechanism. You need a `CacheManager` and a cache backend; in a Spring Boot application with a matching starter, Boot can auto-configure a cache manager based on dependencies. A simple cache backed by `ConcurrentHashMap` is useful for learning, but lacks built-in TTL or capacity limits for production.

**Important limitation of the default proxy:** calling `this.getProduct(id)` from another method **inside the same bean** bypasses the proxy, so `@Cacheable` on `getProduct` will not apply to that call. Call through a Spring bean from outside and establish clear service boundaries; in early lessons, prefer annotations on `public` methods of Spring-managed beans. Manually instantiating objects with `new` outside the container also loses Spring management.

## 3. The Three Core Annotations and Picking the Right One

| Annotation | When Does the Method Run? | Effect on Cache | Use Case |
| --- | --- | --- | --- |
| `@Cacheable` | Only when the cache lacks a matching value | Writes result on miss | Reading catalogs, configs, lookups |
| `@CachePut` | **Always runs** | Writes/updates with return value | Method updates source then returns new object |
| `@CacheEvict` | Runs normally | Removes entry or entire specified cache | After editing/deleting data, forces reload |

Attributes to learn in order:

- `cacheNames` (or `value`): cache name; organize by data type and keep consistent across reads/writes/deletes.
- `key`: SpEL expression generating the key, e.g., `key = "#p0"` uses the first argument; `#p0` does not depend on compiler settings retaining parameter names.
- `condition`: evaluated **before** calling the method to decide whether caching applies.
- `unless`: evaluated **after** obtaining the result, often used to avoid caching unsuitable results, e.g., `unless = "#result == null"`.
- `allEntries = true` in `@CacheEvict`: clears every entry in the specified cache; do not use casually because it can trigger mass misses.
- `beforeInvocation = true`: evicts before running the method; by default eviction occurs after the method completes successfully.

With default keys, Spring generally uses all input parameters: no parameters → `SimpleKey.EMPTY`, one parameter → that argument itself, multiple parameters → `SimpleKey` wrapping the arguments. Whether using default keys or SpEL, evaluate `equals/hashCode` stability, mutable arguments, same ID with different tenant/locale/permissions, and alignment between read keys and update/evict keys. Do not casually place `@Cacheable` and `@CachePut` on the same method because one aims to skip execution on hit while the other always runs.

## 4. Runnable Practice Example (Spring Boot, Java 17+)

This example simulates a data source using `ConcurrentHashMap` so actual source reads are clearly visible. Place the following files into **a Spring Boot project using Gradle/Groovy** that already has the Spring Boot plugin and Java 17+; add the starter to `build.gradle` (keeping the project's other dependencies intact):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
```

**File `src/main/java/example/cache/CacheConfig.java`:** enables caching and explicitly selects an in-memory backend for the demo.

```java
package example.cache;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfig {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("books");
    }
}
```

**File `src/main/java/example/cache/BookService.java`:** the origin data is `store`; the counter increments only when the body of `getTitle` actually runs.

```java
package example.cache;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class BookService {
    private final Map<String, String> store =
            new ConcurrentHashMap<>(Map.of("b1", "Java Basics"));
    private final AtomicInteger sourceReads = new AtomicInteger();

    @Cacheable(cacheNames = "books", key = "#p0")
    public String getTitle(String id) {
        System.out.println("SOURCE read #" + sourceReads.incrementAndGet());
        return store.get(id);
    }

    @CachePut(cacheNames = "books", key = "#p0")
    public String rename(String id, String newTitle) {
        store.put(id, newTitle);
        return newTitle;
    }

    @CacheEvict(cacheNames = "books", key = "#p0")
    public void evict(String id) {
        // Demo: only evicts the cache entry, does not modify the origin data.
    }
}
```

**File `src/main/java/example/cache/CacheDemoApplication.java`:** invokes the service from another bean, through the Spring-managed proxy.

```java
package example.cache;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CacheDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CacheDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(BookService books) {
        return args -> {
            System.out.println(books.getTitle("b1"));  // miss
            System.out.println(books.getTitle("b1"));  // hit
            System.out.println(books.rename("b1", "Spring Cache"));
            System.out.println(books.getTitle("b1"));  // hit with new value
            books.evict("b1");
            System.out.println(books.getTitle("b1"));  // miss after evict
        };
    }
}
```

Run inside the project directory:

```bash
./gradlew bootRun
# Windows PowerShell: .\gradlew.bat bootRun
```

**`System.out` lines of the example** in order (excluding Spring Boot startup logs):

```text
SOURCE read #1
Java Basics
Java Basics
Spring Cache
Spring Cache
SOURCE read #2
Spring Cache
```

Explanation: the first fetch is a miss so `sourceReads` increments; the second is a hit so it does not increment. `rename` always executes, updates `store`, and `@CachePut` puts `Spring Cache` into the cache under key `b1`. The next read still hits, receiving the updated value. `evict` removes the cache entry, so the final call reads from the source a second time. The demo only tests an existing key; handling not-found/null data requires a separate caching decision.

**Running note:** these are three classes placed inside an existing Spring Boot project, not a standalone Java file to run directly with `javac`. In a Gradle-configured Spring Boot project, `bootRun` is the right command; keep starter and versions consistent with your project.

## 5. Keys and Consistency: Where Bugs Happen Most Easily

When introducing caching into a real service, state the contract explicitly: **what is the origin data source, what is the cache name, what components make up the key, when is it updated, when is it evicted, and how long can it be stale**.

- **Same data, same key:** e.g., reading `getById(42)`, updating `update(42)`, and deleting `delete(42)` must coordinate on the same cache/key. Mismatched keys cause prolonged stale data.
- **Permission/tenant partitioning:** do not cache user-specific results under a key with only `productId` if permissions, prices, or locale alter the output; include the relevant components in the key.
- **Invalidation timing:** clear cache entries after the source change succeeds; with transactions that can roll back and concurrent calls, test execution order and consider post-commit updates. Cache annotations do not automatically guarantee transactional consistency.
- **TTL does not mean always accurate:** TTL bounds entry lifetime when supported by the provider, yet within that window data can still be stale; when stricter consistency is needed, evict or update proactively.
- **Do not cache unconditionally:** evaluate nulls, exceptions, results varying by time/permissions, mutable objects, and side-effecting operations. `@Cacheable` can skip the entire method body on a hit.
- **Concurrency:** multiple concurrent misses can execute the computation together. `@Cacheable(sync = true)` can coordinate loading for the same key when supported by the provider, but is not a global distributed lock; understand your backend's capabilities before relying on it.

## 6. Choosing a Backend for Your Needs

| Option | Good for Learning / Adoption | What You Must Configure or Verify |
| --- | --- | --- |
| `ConcurrentMapCacheManager` (in-memory) | Demos, tests, small apps; lightweight and easy to observe | No built-in TTL or capacity limits; cache lives per instance and resets on restart. |
| Caffeine (local cache) | Very fast access inside a single JVM, needs size limits or expiry | Configure Caffeine max size/TTL; multiple instances hold separate caches. |
| Redis (shared/distributed cache) | Multiple instances needing access to one cache store | Connections, serializers, TTL, key prefixes, network errors, operations, and consistency policy. |

Spring Cache decouples annotations from the backend, yet **semantics for TTL, eviction, memory bounds, nulls, and concurrency depend on the provider**. Never assume switching backends is strictly equivalent. In a multi-replica app, local caches do not auto-sync across replicas. Pick a backend after establishing lifetime, scale, and consistency requirements—not merely because a technology is popular.

## 7. Recommended Learning Sequence by Skill Stage

| Stage | What to Study and Practice | Sign of Understanding |
| --- | --- | --- |
| 1. Foundations | Cache hit/miss, key/value, data source, stale data, TTL, invalidation, memory cost. | Can draw read flows with/without cache; name at least two risks. |
| 2. Spring container/proxy | Beans, proxy calls, `@EnableCaching`, `Cache`, `CacheManager`. | Can explain why self-invocation skips `@Cacheable` by default. |
| 3. Cached reads | Run `@Cacheable` with an in-memory backend; observe hits/misses via a counter. | Second call with the same key does not run the method body. |
| 4. Writes and eviction | Try `@CachePut`, `@CacheEvict`, `allEntries`, aligned key rules. | Reads see new data after update; next read after evict is a miss. |
| 5. Storage policies | Try `key`, `condition`, `unless`; decide whether to cache nulls and per-user data. | Can prove two requests in different contexts do not return the wrong cache entry. |
| 6. Backends and lifetime | Compare ConcurrentMap, Caffeine, Redis; configure provider expiry/size. | Can explain how local cache differs from shared cache and who owns TTL. |
| 7. Consistency, concurrency | Test source updates, transaction rollback, concurrent misses, multiple instances. | Knows when post-commit eviction is needed and when `sync` falls short. |
| 8. Testing, operations | Write hit/miss/invalidation tests; measure hit rate, real queries, latency, memory, backend errors. | Has evidence caching reduces cost without returning wrong data. |

**Follow-up exercise:** using the demo above, add key `b2` and count source reads; compare results when changing keys, calling twice with the same key, after `rename`, and after `evict`. Then add an internal `this.getTitle("b1")` call inside `BookService` to observe the difference versus calling through the Spring bean. Finally, configure TTL with a supporting provider and verify behavior after entry expiration.

## 8. Common Mistakes and Self-Check Checklist

- **Annotations have no effect:** `@EnableCaching` not enabled, missing `CacheManager`, object not managed by Spring, non-proxied method, or self-invocation.
- **Returning wrong user/context data:** key missing tenant, locale, permissions, or business conditions; same key reused for distinct results.
- **Stale data after update/delete:** missing `@CacheEvict`/`@CachePut`, wrong cache name/key, invalidation before transaction commit, or out-of-band source updates.
- **Growing memory, entries never expire:** assuming Spring Cache provides built-in TTL/limits; inspect provider capabilities and config.
- **Performance fails to improve:** low repetition, fragmented keys, costly serialization/network, or miss stampedes. Measure before and after rather than assuming annotations help.
- **Order-dependent tests:** cache state leaks across test cases; use an appropriate cache manager, isolate state, or clear caches explicitly.
- **Using `@CachePut` like `@Cacheable`:** `@CachePut` always executes the method, so it never skips source computation/reads on hits.

Before considering a practice exercise complete, answer for yourself: (1) where are entries stored? (2) how is the key computed? (3) what controls entry expiration? (4) when origin data changes, which entries are affected? (5) where must calls originate for the proxy to apply? (6) what is the evidence for hits/misses and data correctness?

## Official Documentation for Further Reading

- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Boot — Caching: https://docs.spring.io/spring-boot/reference/io/caching.html