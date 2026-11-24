# Testing @Cacheable, @CachePut, and @CacheEvict Through Bean Proxies in Spring Boot

## 1. The problem: annotations are in the code, but does caching actually work?

Spring Cache allows adding caching to service methods without manually writing `Map.get`/`Map.put` in every method. For example:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public Book find(String isbn) {
    return repository.load(isbn);
}
~~~

With a call going through a **Spring-managed proxy**, the first read for a given key is a *cache miss*: it executes the method and stores the result. Subsequent calls are *cache hits*: the proxy returns the cached result **without executing the method body**.

However, there are at least four ways a test can reach a false conclusion:

1. The test uses `new BookService(...)` and calls the method directly, bypassing the Spring proxy.
2. A method inside the bean calls `this.find(isbn)`; self-invocation bypasses advice in proxy mode.
3. The test sets `spring.cache.type=none` or uses a no-op CacheManager and only asserts the return value.
4. The test only asserts that two returned values are equal, without checking the **dependency access count**, cache state, or the correctness of `@CachePut`/`@CacheEvict`.

This lesson verifies **behavior + proxy wiring + cache state** in a Java 17+/Spring Boot 3.5.x application:

- `@Cacheable`: miss → runs the method; hit → skips the method.
- `@CachePut`: always runs the method, using the result to update the corresponding key in the cache.
- `@CacheEvict`: removes an entry or an entire region, by default after success, optionally before the method runs.
- `@Caching` and `@CacheConfig`: combines multiple operations and shares cache names.
- `condition` and `unless`: decide **before** and **after** invocation whether to use the cache.
- Self-invocation and raw objects: proves that tests must call **beans through their proxies**.
- Test isolation: clears caches and resets the fake repository between tests without breaking the ApplicationContext.

### Learning outcomes

After this lesson, you will be able to:

1. Distinguish the Spring Cache abstraction from a concrete cache store.
2. Enable `@EnableCaching` and verify that a bean is actually proxied.
3. Assert all of: result, backend invocation count, cache entry, and cache key.
4. Test cache hits, misses, distinct keys, and that exceptions are not cached by default.
5. Verify updates/invalidations from `@CachePut`, `@CacheEvict`, `allEntries`, and `beforeInvocation`.
6. Verify `@Caching` evicting multiple cache regions.
7. Demonstrate `condition` skipping caching by input and `unless` vetoing caching by result.
8. Identify why self-invocation bypasses proxies and how to refactor it.
9. Isolate caches between tests inside a cached Spring TestContext.
10. Know when a ConcurrentMap test is sufficient and when Redis/Caffeine/transaction/concurrency integration tests are required.

## 2. What components make up the Spring Cache abstraction?

Spring Cache mainly consists of:

- `Cache`: interface to read/write/evict entries, such as `get`, `put`, `evict`, and `clear`.
- `CacheManager`: looks up caches by name, such as the `books` region.
- `CacheResolver`: can resolve one or more caches based on the invocation context.
- `KeyGenerator`: generates keys when `key` is not declared.
- Cache interceptor / AOP advice: triggered by annotations on methods invoked **through a proxy**.
- Cache provider: ConcurrentMap, Caffeine, Redis, JCache, Hazelcast, etc., each with different TTL/serialization/cluster semantics.

Diagram:

~~~text
JUnit / Controller / Other bean
             |
             v
   BookQueryService Spring PROXY
             |
             +-- Compute key "A"
             |
             +-- CacheManager -> Cache "books"
             |                      |
             |                  Cache.get("A")
             |                      |
             |                +-----+------+
             |                |            |
             |               HIT          MISS
             |                |            |
             |                |     target BookQueryService.get("A")
             |                |            |
             |                |         BookCatalog.load("A")
             |                |            |
             |                |       Cache.put("A", Book)
             |                |            |
             +----------------+------------+
                              |
                              v
                           Book result
~~~

**A cache hit does not mean "the target method runs faster."** With `@Cacheable`, the target method body is usually **not called** when the entry is already present. Therefore, tests must assert that the repository/load count stays unchanged on a cache hit.

### 2.1 Cache is an optimization, not a database replacement

A cache can hold stale data if not invalidated or updated properly. The source of truth remains the database/remote service (`BookCatalog` in the example), not the cache. Do not use a cache as a security mechanism: access permissions must be checked properly, especially when cache keys need to include tenant/user scope.

## 3. The three main annotations

| Annotation | Cache miss | Cache hit | Effect on cache |
| --- | --- | --- | --- |
| `@Cacheable` | Runs method, stores result | Returns cached result, skips method | Cache population/lookup |
| `@CachePut` | Always runs method | **Still runs** method | Sets/updates cache with result |
| `@CacheEvict` | Runs method (normally) | Does not use cache to skip method | Removes key or entire region |

Simple example:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public Book find(String isbn) {
    return catalog.load(isbn);
}

@CachePut(cacheNames = "books", key = "#result.isbn()")
public Book save(Book book) {
    return catalog.store(book);
}

@CacheEvict(cacheNames = "books", key = "#p0")
public void remove(String isbn) {
    catalog.delete(isbn);
}
~~~

These are **illustrative snippets**; the complete files and standalone tests appear later.

Using the same `books` region and the same key (ISBN) is a **mandatory condition** if you want `save` to update the value that `find` reads, or `remove` to delete the value that `find` stored. A separate test for `@CachePut` might PASS even if it updates the wrong region without affecting the cache used by `@Cacheable`. That is why you must test **cross-method interaction**.

## 4. @EnableCaching and real proxies

### 4.1 Enabling cache annotations

~~~java
@Configuration(proxyBeanMethods = false)
@EnableCaching(proxyTargetClass = true)
class CachingConfiguration {
    // @Bean CacheManager ...
}
~~~

`@EnableCaching` registers the caching infrastructure. `proxyTargetClass=true` requests class-based proxies; this is an explicit choice for examples that inject concrete service classes. It does not mean every final/private method can be intercepted.

Spring Boot also provides auto-configuration for `CacheManager` when cache support is enabled; however, the example defines its own `ConcurrentMapCacheManager` so tests are deterministic and do not depend on whatever provider happens to be on the classpath.

Spring Boot documentation recommends not placing `@EnableCaching` directly on the main application class if you do not want caching to be a requirement for **every** test/slice. Separating it into a dedicated configuration class gives you control when testing with or without caching.

### 4.2 Proxy mode and self-invocation

When a caller invokes:

~~~java
Book b = springBean.get("A");
~~~

and `springBean` is a proxy, the caching interceptor runs. However, inside the target bean:

~~~java
public Book getTwice(String isbn) {
    Book a = this.get(isbn);
    Book b = this.get(isbn);
    return b;
}
~~~

the `this.get` calls are self-invocations on the target object, **bypassing the proxy** under AOP proxy mode. Two catalog accesses still happen even though `get` has `@Cacheable`.

This is **not** "Spring caching is broken." It is a consequence of the call path. A good fix is to extract the cached method into another bean so the orchestration bean injects the cached bean and calls it through the proxy. AspectJ weaving is another option, but that is a different deployment/design choice from default proxying and must be tested separately.

### 4.3 Don't just assert that the annotation exists

~~~java
assertTrue(AopUtils.isAopProxy(bookQueries));
~~~

This is a useful technical assertion to confirm the bean is wrapped. However, **having a proxy alone is not enough**: the proxy might exist for transactions, security, or another advice. You still must verify that a cache hit does not call `BookCatalog.load` again, and that cache entries are added and removed properly.

## 5. Choosing the right CacheManager for tests

| Test goal | Recommended CacheManager | Notes |
| --- | --- | --- |
| Verify annotation/proxy/key/eviction logic | `ConcurrentMapCacheManager` | Fast, in-memory, deterministic |
| Caching not needed in ordinary tests | `NoOpCacheManager` or `spring.cache.type=none` | **Does not** prove `@Cacheable` works |
| Verify Caffeine TTL/max size/eviction policy | `CaffeineCacheManager` | Requires real provider, appropriate timer/expiry checks |
| Verify serialization, key prefix, TTL, Redis network | `RedisCacheManager` + Testcontainers | An in-memory map is not equivalent to Redis |
| Verify JCache/Hazelcast/etc. | Specific provider | Test provider-specific contract/config separately |
| Verify production DB transaction + cache consistency | Real cache + database integration | Must test commit/rollback boundaries |

Spring Boot 3.5 can select a simple provider backed by concurrent maps when no other provider is found. But **this lesson needs a real working cache**, so it defines an explicit `CacheManager` bean.

Do not accidentally set:

~~~properties
spring.cache.type=none
~~~

in a test suite meant to prove caching behavior: when the cache is a no-op, calling a `@Cacheable` method twice still executes the method twice. That property is very useful in **tests that do not test caching** to avoid test pollution, not in cache proxy integration tests.

## 6. Choosing keys accurately: never accidentally share data across users/tenants

Spring uses `SimpleKeyGenerator` by default:

| Method parameters | Default key |
| --- | --- |
| No parameters | `SimpleKey.EMPTY` |
| Single parameter (non-null) | That parameter object itself |
| Multiple parameters | `SimpleKey` containing the parameters |

For clarity in tests, this lesson uses `key="#p0"`: the first argument is the ISBN. Compared to `key="#isbn"`, `#p0` does not depend on parameter names being compiled into bytecode via the `-parameters` compiler flag.

Example:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public Book get(String isbn) {
    return catalog.load(isbn);
}
~~~

### 6.1 One cache, multiple keys

When `get("A")` is called twice, the catalog runs only once. But `get("B")` must have a **different cache entry**. A test that checks only one key can miss a hardcoded-key bug:

~~~java
// Wrong: every ISBN uses the same cache entry.
@Cacheable(cacheNames = "books", key = "'singleton'")
~~~

This annotation is an **illustrative anti-pattern** and must not be used in the runnable project.

### 6.2 Multi-tenant keys

If a method is:

~~~java
public Book getForTenant(String tenantId, String isbn)
~~~

and the cache uses only `isbn` as the key, then tenant A and tenant B can share cached results. That causes both incorrect data and an information leak. The key must include the **authenticated tenant scope**, for example:

~~~java
@Cacheable(cacheNames = "tenantBooks", key = "#p0 + ':' + #p1")
public Book getForTenant(String tenantId, String isbn) {
    // Query must still enforce tenant permission.
}
~~~

This is an illustrative fragment. If values can contain delimiters, use a composite typed key or `KeyGenerator` to avoid collisions; never treat the cache key as an authorization layer. You also need a negative test proving tenant A cannot retrieve tenant B's result.

## 7. @Cacheable: cache hit, miss, exception, condition, and unless

`@Cacheable` checks the cache first:

~~~text
get("A") first call
    cache.get("A") -> miss
    catalog.load("A") -> Book("A", "Alpha")
    cache.put("A", Book)
    return Book

get("A") second call
    cache.get("A") -> hit
    catalog.load NOT CALLED
    return cached Book
~~~

That is the most important test:

~~~java
assertEquals(new Book("A", "Alpha"), queries.get("A"));
assertEquals(new Book("A", "Alpha"), queries.get("A"));
assertEquals(1, catalog.reads());
assertNotNull(cache("books").get("A"));
~~~

### 7.1 Exceptions are not stored as cached successes by default

If `catalog.load("UNKNOWN")` throws `NoSuchElementException`, the `@Cacheable` call does not produce a successful value to store. Two subsequent calls with the same key normally run the catalog twice and throw the exception twice. The test checks `reads()==2` and that the cache has no entry.

**Note:** some applications intentionally convert "not found" into `null` or `Optional.empty()`, which may trigger null/negative caching depending on the provider and configuration. Do not conflate that behavior with uncaught exceptions.

### 7.2 condition is evaluated before the method

~~~java
@Cacheable(
    cacheNames = "conditionalBooks",
    key = "#p0",
    condition = "#p0.startsWith('C-')")
~~~

For an ISBN without the `C-` prefix, the cache advice does not use the cache; the target method runs every time. For example, calling `getConditional("A")` twice → `catalog.reads()==2`.

### 7.3 unless is evaluated after the result is produced

~~~java
@Cacheable(
    cacheNames = "conditionalBooks",
    key = "#p0",
    unless = "#result.title().startsWith('Skip')")
~~~

For a result whose title starts with `Skip`, the method still runs, but the cache put is vetoed. Calling it again runs the catalog again. For a valid title, the first call populates the cache and the second call is a hit.

**Distinction:**

- `condition` uses input arguments and decides before the target invocation whether caching applies.
- `unless` uses the return value and can veto cache population only **after the method returns a result**.
- `#result` in `unless` is the post-invocation value and cannot be used in a cache key that must be computed before the call.
- If the result can be null, use null-safe SpEL or an appropriate condition; the examples in this lesson do not return null.

### 7.4 sync=true

~~~java
@Cacheable(cacheNames = "books", key = "#p0", sync = true)
public Book getSynchronized(String isbn) {
    return catalog.load(isbn);
}
~~~

This is a **standalone illustrative sample**, not a method in the mini-project. `sync=true` hints to the cache provider to compute the value only once when multiple threads concurrently miss the same key. It has limitations when combined with `unless`, multiple cache names, and certain providers. Do not infer a **distributed lock** across all JVMs or Redis instances; test real concurrency and the actual provider if cache stampede protection is required.

## 8. @CachePut: method always runs and result updates the cache

Example:

~~~java
@CachePut(cacheNames = "books", key = "#result.isbn()")
public Book save(Book book) {
    return catalog.store(book);
}
~~~

When calling `save(new Book("A","New"))`:

1. `catalog.store(...)` **always runs**, even if `books["A"]` already holds a value.
2. Upon success, the cache put uses the ISBN taken from `#result.isbn()`.
3. The next `get("A")` returns the new `Book` from the cache **without loading from the catalog**.

Tests must prove both:

~~~java
assertEquals(2, catalog.writes()); // Two save calls.
assertEquals(new Book("A", "New 2"), queries.get("A"));
assertEquals(1, catalog.reads());  // No need to read again.
~~~

`@CachePut` differs from `@Cacheable` in that it **does not skip the method on a cache hit**.

### 8.1 Key alignment

If `@Cacheable(key="#p0")` stores by ISBN while `@CachePut` stores by the `Book` object, an update can write to a **different key**:

~~~text
Cacheable: books["A"] = old Book
CachePut: books[Book("A","New")] = new Book
next get("A") -> old Book
~~~

Therefore, the lesson uses `@CachePut(key="#result.isbn()")` to stay consistent with `@Cacheable(key="#p0")`. A test that only asserts `the new cache entry exists` can miss a stale entry under the old key; you must test `queries.get("A")` right after the update.

### 8.2 Do not arbitrarily combine @CachePut and @Cacheable on the same method

The two annotations have conflicting behaviors: `@Cacheable` can skip the method, while `@CachePut` requires the method to always execute. Spring Framework advises against combining them on the same method unless conditions are explicitly designed to be mutually exclusive. Separating read/cacheable and write/cacheput into distinct methods is much easier to test.

## 9. @CacheEvict: removing a key or an entire region, before or after the method

### 9.1 Evicting a single key after success (default)

~~~java
@CacheEvict(cacheNames = "books", key = "#p0")
public void remove(String isbn) {
    catalog.delete(isbn);
}
~~~

Default is `beforeInvocation=false`. If the method completes **successfully**, Spring evicts the key from the cache afterward. The next `get("A")` misses and queries the repository: it may see an updated record or receive not-found.

### 9.2 Evict does not modify the source of truth

~~~java
@CacheEvict(cacheNames = "books", key = "#p0")
public void invalidate(String isbn) {
    // Invalidate cache only; catalog data does not change.
}
~~~

This method is useful when source data is modified by another operation, such as an integration event. A test can modify the fake catalog directly, call `invalidate`, and assert that the next read fetches the new value. Do not confuse "evict" with "delete database record": `@CacheEvict` only operates on the cache abstraction.

### 9.3 allEntries=true

~~~java
@CacheEvict(cacheNames = "books", allEntries = true)
public void invalidateAll() {
}
~~~

Clears the **entire `books` region**. Do not declare `key` alongside `allEntries=true`; a key is meaningless when clearing everything. For tenant-partitioned caches, `allEntries=true` can wipe entries across multiple tenants, impacting performance and concurrency; use it only when policy requires it.

### 9.4 beforeInvocation=false and exceptions

~~~java
@CacheEvict(cacheNames = "books", key = "#p0")
public void failAfter(String isbn) {
    throw new IllegalStateException("after failure");
}
~~~

If the method throws an exception, **eviction does not happen** in the default mode. A test seeds the cache beforehand, calls `failAfter`, and verifies that the entry is still present.

### 9.5 beforeInvocation=true and exceptions

~~~java
@CacheEvict(
    cacheNames = "books",
    key = "#p0",
    beforeInvocation = true)
public void failBefore(String isbn) {
    throw new IllegalStateException("before failure");
}
~~~

The cache entry is removed **before** the method executes, even if the method later throws an exception. This makes a major difference if the method has an uncommitted transaction or validation that can fail. Tests must verify that the entry is gone and that the next read actually reloads.

**Do not assume `beforeInvocation=true` is "safer" by default.** When an update fails and the DB rolls back, evicting beforehand can cause unnecessary misses; with concurrent transactions, eviction timing can cause stale reads. Choose a consistent policy according to business requirements.

## 10. @CacheConfig and @Caching

### 10.1 @CacheConfig

If multiple methods share the `books` region, you can configure it at the class level:

~~~java
@Service
@CacheConfig(cacheNames = "books")
public class BookQueryService {

    @Cacheable(key = "#p0")
    public Book get(String isbn) {
        // ...
    }
}
~~~

This is a snippet; the full file is below. Method-level `cacheNames` can override the class-level value when using a different cache region. Class-level `@CacheConfig` only shares configuration (`cacheNames`, `keyGenerator`, `cacheManager`, `cacheResolver`) and **does not automatically create a caching operation** on methods without `@Cacheable`/`@CachePut`/`@CacheEvict`.

### 10.2 @Caching for multiple operations

A single command may need to invalidate two regions:

~~~java
@Caching(evict = {
    @CacheEvict(cacheNames = "books", allEntries = true),
    @CacheEvict(cacheNames = "conditionalBooks", allEntries = true)
})
public void invalidateBoth() {
}
~~~

The test must check that **both** regions are empty. If it only checks `books`, a wrong cache name on `conditionalBooks` can go undetected.

### 10.3 Multiple CacheManagers

If a project uses both local Caffeine and distributed Redis, each operation must explicitly specify `cacheManager` or `cacheResolver`, e.g. `@CacheConfig(cacheManager="catalogCacheManager")`. Using the right cache name alone is not enough; tests must inspect the right provider/manager. This lesson uses a **single CacheManager** to avoid ambiguity.

## 11. Testing strategy: result + count + cache state + proxy

Four assertion groups form the foundation:

| Group | Example | What it catches |
| --- | --- | --- |
| Business result | `assertEquals(new Book(...), queries.get("A"))` | Whether the returned cached value is correct |
| Backend execution count | `catalog.reads()==1` after two gets | Whether a cache hit actually skips loading |
| Cache entry state | `cache.get("A", Book.class)` | Correct key and proper put/evict |
| Proxy verification | `AopUtils.isAopProxy(queries)` | Test invokes the bean through the Spring advice boundary |

**Do not rely only on Mockito `verify` on the facade**: on a cache hit, the call into the **proxy** still occurs, while the invocation of the **target method/repository** is skipped. If you verify the wrong layer, you might think there were two cache misses because the proxy was invoked twice.

The right approach is to count how many times the target collaborator (catalog/repository/remote client) is actually called while also inspecting cache state.

### 11.1 Why not use a pure unit test for cache annotations?

~~~java
BookQueryService raw = new BookQueryService(catalog);
raw.get("A");
raw.get("A");
~~~

Without a Spring proxy, both calls reach the catalog. Testing a raw object is valuable for verifying the *business method body*, but it does not prove `@Cacheable` works. The runnable project includes this negative demonstration to highlight the difference.

## 12. Standalone Java 17+ / Spring Boot 3.5.x example suite

The lesson uses a mini-project with a simulated in-memory source of truth and a real `ConcurrentMapCacheManager`; it does **not** connect to an external Redis/DB and requires no Docker.

~~~text
spring-cache-proxy-demo/
  settings.gradle
  build.gradle
  src/main/java/example/cache/
    CacheDemoApplication.java
    CachingConfiguration.java
    Book.java
    BookCatalog.java
    BookQueryService.java
    BookCommandService.java
  src/test/java/example/cache/
    BookCacheProxyTest.java
~~~

The test suite has **15 JUnit Jupiter test methods**. Each test resets the catalog and clears both caches in `@BeforeEach`. This is an integration/component test of Spring Cache proxies, not a performance benchmark.

### 12.1 settings.gradle

~~~groovy
rootProject.name = 'spring-cache-proxy-demo'
~~~

### 12.2 build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-cache'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Versions are pinned for illustration, without claiming they are the latest available. Running the project requires a Gradle wrapper or compatible Gradle installation. `spring-boot-starter-cache` provides Spring cache infrastructure; `starter-test` includes JUnit Jupiter and AssertJ/Mockito. The test code below uses JUnit assertions directly and does not need Mockito.

**No Caffeine/Redis dependency is needed**: the in-memory provider is explicitly created in `CachingConfiguration`.

## 13. CacheDemoApplication.java

~~~java
package example.cache;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CacheDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CacheDemoApplication.class, args);
    }
}
~~~

The main application only contains `@SpringBootApplication`. Caching is enabled in a separate config class to keep boundaries clear for test slices.

## 14. CachingConfiguration.java

~~~java
package example.cache;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching(proxyTargetClass = true)
public class CachingConfiguration {

    @Bean
    CacheManager cacheManager() {
        ConcurrentMapCacheManager manager =
                new ConcurrentMapCacheManager(
                        "books", "conditionalBooks");

        manager.setAllowNullValues(false);
        return manager;
    }
}
~~~

Two explicitly named regions:

- `books`: regular read/write/invalidate operations.
- `conditionalBooks`: tests `condition`/`unless` and multi-cache invalidation.

`setAllowNullValues(false)` keeps the demo from silently storing null; `BookCatalog.load` returns a `Book` or throws, never null. `ConcurrentMapCacheManager` **has no default TTL/max-size eviction**, so tests here must clear caches manually between runs; it is not equivalent to Redis/Caffeine in production.

`proxyTargetClass=true` explicitly selects class-based proxies so tests can inject concrete services. Do not mark `BookQueryService`/`BookCommandService` as `final` in the project: class-based proxies need to be able to subclass them.

## 15. Book.java: immutable domain record

~~~java
package example.cache;

import java.util.Objects;

public record Book(String isbn, String title) {
    public Book {
        Objects.requireNonNull(isbn, "isbn");
        Objects.requireNonNull(title, "title");
    }
}
~~~

A record fits a cache demo well because its data is immutable. When the title changes, the catalog creates a **new `Book` record**. If a cache holds a mutable entity, tests can produce misleading results due to mutating the cached object without `@CachePut`/`@CacheEvict`; avoid mutable shared objects when demonstrating invalidation.

## 16. BookCatalog.java: source of truth and execution counters

~~~java
package example.cache;

import java.util.Map;
import java.util.NoSuchElementException;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Repository;

@Repository
public class BookCatalog {

    private final Map<String, Book> data =
            new ConcurrentHashMap<>();

    private final AtomicInteger reads = new AtomicInteger();
    private final AtomicInteger writes = new AtomicInteger();
    private final AtomicInteger deletes = new AtomicInteger();

    public Book load(String isbn) {
        reads.incrementAndGet();

        Book value = data.get(isbn);
        if (value == null) {
            throw new NoSuchElementException(
                    "Book not found: " + isbn);
        }
        return value;
    }

    public Book store(Book book) {
        writes.incrementAndGet();
        data.put(book.isbn(), book);
        return book;
    }

    public void delete(String isbn) {
        deletes.incrementAndGet();
        data.remove(isbn);
    }

    // Fixture setup: intentionally goes directly to the source of truth,
    // not counted as a service business write.
    public void seed(Book book) {
        data.put(book.isbn(), book);
    }

    public void reset() {
        data.clear();
        reads.set(0);
        writes.set(0);
        deletes.set(0);
    }

    public int reads() {
        return reads.get();
    }

    public int writes() {
        return writes.get();
    }

    public int deletes() {
        return deletes.get();
    }
}
~~~

`BookCatalog` has no cache annotations; it is where **target collaborator calls** are recorded. This lets tests detect cache hits via `reads()` instead of guessing from execution time. `ConcurrentHashMap` is safe for basic multi-threaded access, but a shared `reset()` is unsuitable for running tests in parallel that share a singleton context.

In a real application, `BookCatalog` could be a JPA repository or HTTP gateway. This lesson keeps it in-memory to focus on Spring proxy semantics.

## 17. BookQueryService.java: @Cacheable and self-invocation

~~~java
package example.cache;

import org.springframework.cache.annotation.CacheConfig;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
@CacheConfig(cacheNames = "books")
public class BookQueryService {

    private final BookCatalog catalog;

    public BookQueryService(BookCatalog catalog) {
        this.catalog = catalog;
    }

    @Cacheable(key = "#p0")
    public Book get(String isbn) {
        return catalog.load(isbn);
    }

    @Cacheable(
        cacheNames = "conditionalBooks",
        key = "#p0",
        condition = "#p0.startsWith('C-')",
        unless = "#result.title().startsWith('Skip')")
    public Book getConditional(String isbn) {
        return catalog.load(isbn);
    }

    public String getTwiceInsideSameBean(String isbn) {
        // Self-invocation: this.get call does not go through the proxy.
        Book first = this.get(isbn);
        Book second = this.get(isbn);
        return first.title() + "|" + second.title();
    }
}
~~~

Explanation:

- `@CacheConfig(cacheNames="books")` makes `get` default to the `books` region.
- `key="#p0"` ensures the key is the ISBN.
- `getConditional` overrides `cacheNames` to `conditionalBooks`; `condition` allows only keys prefixed with `C-`, and `unless` excludes results whose title starts with `Skip`.
- `getTwiceInsideSameBean` intentionally **fails to cache** the two internal calls; it is a negative demonstration of proxying. Do not use this pattern in production when cache hits between internal calls are expected.

### 17.1 Why place @Cacheable on public methods?

Standard Spring proxy-based caching applies best to public methods called from outside the bean. Private/final methods and self-invocation are not reliable interception points in proxy mode; if you need otherwise, choose another design such as AspectJ weaving and test that configuration properly.

## 18. BookCommandService.java: @CachePut, @CacheEvict, and @Caching

~~~java
package example.cache;

import org.springframework.cache.annotation.CacheConfig;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Caching;
import org.springframework.stereotype.Service;

@Service
@CacheConfig(cacheNames = "books")
public class BookCommandService {

    private final BookCatalog catalog;

    public BookCommandService(BookCatalog catalog) {
        this.catalog = catalog;
    }

    @CachePut(key = "#result.isbn()")
    public Book save(Book book) {
        return catalog.store(book);
    }

    @CacheEvict(key = "#p0")
    public void remove(String isbn) {
        catalog.delete(isbn);
    }

    // Invalidate only; intentionally leaves catalog intact.
    @CacheEvict(key = "#p0")
    public void invalidate(String isbn) {
    }

    @CacheEvict(allEntries = true)
    public void invalidateAll() {
    }

    @CacheEvict(key = "#p0")
    public void failAfter(String isbn) {
        throw new IllegalStateException("after failure");
    }

    @CacheEvict(key = "#p0", beforeInvocation = true)
    public void failBefore(String isbn) {
        throw new IllegalStateException("before failure");
    }

    @Caching(evict = {
        @CacheEvict(cacheNames = "books", allEntries = true),
        @CacheEvict(
            cacheNames = "conditionalBooks",
            allEntries = true)
    })
    public void invalidateBoth() {
    }
}
~~~

All methods are `public` and the class is non-final, so the Spring class-based caching proxy can advise them. `@CacheConfig` shares the `books` region. `@CachePut` derives the key from the return value of `save` rather than the entire `Book` input, so it matches the key used by `get(String)`.

### 18.1 Meaning of each command

- `save`: the business store always runs, and the cache entry is updated afterward.
- `remove`: deletes source data and evicts the same ISBN.
- `invalidate`: evicts only the cache without touching source data.
- `invalidateAll`: clears all entries in the `books` region, leaving `conditionalBooks` intact.
- `failAfter`: an exception prevents the default post-invocation eviction from running.
- `failBefore`: evicts before the method runs, even if the method throws an exception.
- `invalidateBoth`: clears both regions to demonstrate `@Caching`.

**Note:** `@CachePut`/`@CacheEvict` can execute via AOP around `@Transactional` methods. Timing relative to database commit is not automatically guaranteed by annotations alone; the transaction consistency section below analyzes the risks.

## 19. BookCacheProxyTest.java: testing 15 scenarios

File `src/test/java/example/cache/BookCacheProxyTest.java`:

~~~java
package example.cache;

import java.util.NoSuchElementException;
import java.util.Objects;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class BookCacheProxyTest {

    @Autowired BookQueryService queries;
    @Autowired BookCommandService commands;
    @Autowired BookCatalog catalog;
    @Autowired CacheManager manager;

    private Cache cache(String name) {
        return Objects.requireNonNull(
                manager.getCache(name),
                "Missing cache: " + name);
    }

    @BeforeEach
    void resetCacheAndCatalog() {
        // The same ApplicationContext can be reused across tests.
        cache("books").clear();
        cache("conditionalBooks").clear();

        catalog.reset();
        catalog.seed(new Book("A", "Alpha"));
        catalog.seed(new Book("B", "Beta"));
        catalog.seed(new Book("C-OK", "Cache me"));
        catalog.seed(new Book("C-SKIP", "Skip this"));
    }

    @Test
    void springServicesAreActuallyProxied() {
        assertTrue(AopUtils.isAopProxy(queries));
        assertTrue(AopUtils.isAopProxy(commands));
    }

    @Test
    void cacheableHitSkipsSecondCatalogLoad() {
        assertEquals(new Book("A", "Alpha"), queries.get("A"));
        assertEquals(new Book("A", "Alpha"), queries.get("A"));

        assertEquals(1, catalog.reads());
        assertEquals(new Book("A", "Alpha"),
                cache("books").get("A", Book.class));
    }

    @Test
    void distinctKeysHaveIndependentEntries() {
        queries.get("A");
        queries.get("B");
        queries.get("A");
        queries.get("B");

        assertEquals(2, catalog.reads());
        assertNotNull(cache("books").get("A"));
        assertNotNull(cache("books").get("B"));
    }

    @Test
    void cachePutAlwaysExecutesAndReplacesCachedValue() {
        assertEquals(new Book("A", "Alpha"), queries.get("A"));
        assertEquals(1, catalog.reads());

        assertEquals(new Book("A", "Updated 1"),
                commands.save(new Book("A", "Updated 1")));
        assertEquals(1, catalog.writes());

        assertEquals(new Book("A", "Updated 1"),
                queries.get("A"));
        assertEquals(1, catalog.reads());

        commands.save(new Book("A", "Updated 2"));
        assertEquals(2, catalog.writes());
        assertEquals(new Book("A", "Updated 2"),
                cache("books").get("A", Book.class));
        assertEquals(new Book("A", "Updated 2"),
                queries.get("A"));
        assertEquals(1, catalog.reads());
    }

    @Test
    void evictOneKeyForcesReloadButKeepsOtherKey() {
        queries.get("A");
        queries.get("B");
        assertEquals(2, catalog.reads());

        // External change bypasses cache deliberately.
        catalog.seed(new Book("A", "Alpha changed"));
        assertEquals(new Book("A", "Alpha"), queries.get("A"));
        assertEquals(2, catalog.reads());

        commands.invalidate("A");
        assertNull(cache("books").get("A"));
        assertNotNull(cache("books").get("B"));

        assertEquals(new Book("A", "Alpha changed"),
                queries.get("A"));
        assertEquals(3, catalog.reads());

        queries.get("B");
        assertEquals(3, catalog.reads());
    }

    @Test
    void removeEvictsEntryAndNextLoadSeesMissingSource() {
        queries.get("A");
        assertEquals(1, catalog.reads());

        commands.remove("A");
        assertEquals(1, catalog.deletes());
        assertNull(cache("books").get("A"));

        assertThrows(NoSuchElementException.class,
                () -> queries.get("A"));
        assertEquals(2, catalog.reads());
        assertNull(cache("books").get("A"));
    }

    @Test
    void afterInvocationEvictDoesNotRunOnException() {
        queries.get("A");
        catalog.seed(new Book("A", "New source value"));

        assertThrows(IllegalStateException.class,
                () -> commands.failAfter("A"));

        assertEquals(new Book("A", "Alpha"),
                cache("books").get("A", Book.class));
        assertEquals(new Book("A", "Alpha"), queries.get("A"));
        assertEquals(1, catalog.reads());
    }

    @Test
    void beforeInvocationEvictRunsEvenOnException() {
        queries.get("A");
        catalog.seed(new Book("A", "After failure"));

        assertThrows(IllegalStateException.class,
                () -> commands.failBefore("A"));

        assertNull(cache("books").get("A"));
        assertEquals(new Book("A", "After failure"),
                queries.get("A"));
        assertEquals(2, catalog.reads());
    }

    @Test
    void allEntriesClearsOnlyItsOwnCacheRegion() {
        queries.get("A");
        queries.get("B");
        queries.getConditional("C-OK");
        assertEquals(3, catalog.reads());

        commands.invalidateAll();

        assertNull(cache("books").get("A"));
        assertNull(cache("books").get("B"));
        assertNotNull(cache("conditionalBooks").get("C-OK"));

        queries.getConditional("C-OK"); // remains cached
        assertEquals(3, catalog.reads());

        queries.get("A");
        queries.get("B");
        assertEquals(5, catalog.reads());
    }

    @Test
    void cachingAnnotationEvictsBothRegions() {
        queries.get("A");
        queries.getConditional("C-OK");
        assertEquals(2, catalog.reads());

        commands.invalidateBoth();

        assertNull(cache("books").get("A"));
        assertNull(cache("conditionalBooks").get("C-OK"));

        queries.get("A");
        queries.getConditional("C-OK");
        assertEquals(4, catalog.reads());
    }

    @Test
    void conditionFalseDisablesCachingForGivenInput() {
        queries.getConditional("A");
        queries.getConditional("A");

        assertEquals(2, catalog.reads());
        assertNull(cache("conditionalBooks").get("A"));
    }

    @Test
    void unlessVetoesCachingOnlyForSpecificResult() {
        queries.getConditional("C-SKIP");
        queries.getConditional("C-SKIP");

        assertEquals(2, catalog.reads());
        assertNull(cache("conditionalBooks").get("C-SKIP"));

        queries.getConditional("C-OK");
        queries.getConditional("C-OK");

        assertEquals(3, catalog.reads());
        assertEquals(new Book("C-OK", "Cache me"),
                cache("conditionalBooks")
                        .get("C-OK", Book.class));
    }

    @Test
    void selfInvocationBypassesCacheAdvice() {
        assertEquals("Alpha|Alpha",
                queries.getTwiceInsideSameBean("A"));

        // this.get(...) on the target is called twice.
        assertEquals(2, catalog.reads());
        assertNull(cache("books").get("A"));

        // Only an external call through the proxy starts cache population.
        assertEquals(new Book("A", "Alpha"), queries.get("A"));
        assertEquals(new Book("A", "Alpha"), queries.get("A"));
        assertEquals(3, catalog.reads());
    }

    @Test
    void rawNewInstanceDoesNotActivateCaching() {
        BookQueryService raw = new BookQueryService(catalog);

        raw.get("A");
        raw.get("A");

        assertEquals(2, catalog.reads());
        assertNull(cache("books").get("A"));
    }

    @Test
    void failedLoadsAreNotCachedByDefault() {
        assertThrows(NoSuchElementException.class,
                () -> queries.get("UNKNOWN"));
        assertThrows(NoSuchElementException.class,
                () -> queries.get("UNKNOWN"));

        assertEquals(2, catalog.reads());
        assertNull(cache("books").get("UNKNOWN"));
    }
}
~~~

**15 JUnit Jupiter `@Test` methods**, using a real Spring context and real Spring caching proxies without mocking `BookQueryService`.

### 19.1 Points deliberately verified with multiple signals

- `springServicesAreActuallyProxied`: proxy exists.
- `cacheableHitSkipsSecondCatalogLoad`: correct result, backend `reads=1`, correct cache entry.
- `cachePutAlwaysExecutesAndReplacesCachedValue`: `writes` increases after each `save`, cached value changes, `get` does not increment `reads`.
- `evictOneKeyForcesReloadButKeepsOtherKey`: stale cache is refreshed after invalidation, key B is preserved.
- `afterInvocationEvictDoesNotRunOnException` and `beforeInvocationEvictRunsEvenOnException`: exception semantics of eviction.
- `selfInvocationBypassesCacheAdvice` and `rawNewInstanceDoesNotActivateCaching`: negative demonstrations for proxy boundaries.
- `conditionFalseDisablesCachingForGivenInput` and `unlessVetoesCachingOnlyForSpecificResult`: pre/post-invocation conditions.

### 19.2 Why does every test clear both caches?

Spring TestContext can cache the `ApplicationContext` between test methods and classes. Cache entries are **mutable state of the singleton cache manager** and do not automatically roll back with the JUnit lifecycle. If test A cached ISBN "A", test B could get a cache hit right away with `catalog.reads()==0`, causing flaky behavior or false positives.

`@BeforeEach` calls `cache.clear()` and `catalog.reset()` to isolate data while keeping the same beans/proxies under test. `@DirtiesContext` per method is unnecessary; it incurs expensive context recreation and still does not replace understanding ownership of an external Redis cache.

**Do not run tests in parallel** when they share a static/application cache region and identical keys while `@BeforeEach` clears them. If enabling JUnit parallelism, use unique namespaces/keys/test contexts or isolated `CacheManager` instances.

## 20. Running Gradle and expected results

Linux/macOS:

~~~bash
./gradlew test --tests example.cache.BookCacheProxyTest
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.cache.BookCacheProxyTest
~~~

Full suite:

~~~bash
./gradlew clean test
~~~

**Expected result by design:** Gradle discovers **15 JUnit Jupiter methods** and they PASS on Java 17+/Spring Boot 3.5.x with the source/dependencies shown in this lesson. This is an **expected outcome from static review**, **not** stdout observed from an actual build run. The real report is generated at `build/reports/tests/test/index.html` after execution.

The tests do not use `Thread.sleep`, do not depend on external Redis/DB, and do not print fake logs. They assert **collaborator call counts** rather than speed (whether a cache hit is faster), because timing benchmarks in CI are often flaky.

### 20.1 Result matrix

| Test | Important catalog reads/writes/deletes | Cache state |
| --- | --- | --- |
| Proxy presence | No backend call required | Both service beans are proxied |
| Repeated get A | `reads=1` | `books["A"]` holds Book Alpha |
| Distinct A/B keys | `reads=2` | Two independent entries |
| CachePut save twice | `writes=2`, `reads` stays 1 | `books["A"]` becomes Updated 2 |
| Evict one key | `reads` rises from 2 to 3 | A reloads, B stays cached |
| Remove | `deletes=1`, missing load increments `reads` | `books["A"]` evicted |
| Evict after failure | `reads` stays 1 | Entry remains |
| Evict before failure | `reads` rises to 2 after reload | Entry was removed |
| `allEntries` on `books` | `reads` 3 → 5 | `books` empty, `conditionalBooks` intact |
| `@Caching` evict both | `reads` 2 → 4 | Both regions empty |
| `condition` false | `reads=2` | No entry stored |
| `unless` veto | C-SKIP read twice; C-OK once | Only C-OK stored |
| Self-invocation | `reads=2` before external call | Internal calls do not populate |
| New raw instance | `reads=2` | Does not populate |
| Load exception | `reads=2` | Does not cache exception |

### 20.2 When a test fails

Check in order:

1. Is `@EnableCaching` actually loaded?
2. Is `@Autowired BookQueryService` a Spring proxy or a raw target?
3. Do `@CacheConfig`/`cacheNames` target the right region, and is `CacheManager` the right bean?
4. Does `#p0` point to the ISBN input, and does `#result.isbn()` point to the returned `Book`?
5. Did `@BeforeEach` clear **both caches**?
6. Are tests running in parallel/sharing a context with identical fixture keys?
7. Is `spring.cache.type=none`/NoOpCacheManager overriding the real provider?
8. Is there a self-invocation or a private/final method that cannot be advised?
9. Is data being mutated outside the cache, causing stale results without eviction?
10. Is transaction/async behavior causing updates/evictions to happen before/outside commit?

## 21. Comparing @SpringBootTest with @WebMvcTest and unit tests

### 21.1 @SpringBootTest

This lesson uses `@SpringBootTest` to load:

- `CachingConfiguration` with `@EnableCaching`.
- A real `CacheManager`.
- `BookCatalog`, `BookQueryService`, and `BookCommandService`.
- Spring cache advisor and proxies.

This is the direct way to prove annotation semantics in an application-like context.

### 21.2 @WebMvcTest

`@WebMvcTest` is an MVC slice focused mainly on controllers, filters, and serialization. By default, it does not load all service/cache configurations. If you mock a cached service with Mockito, tests may PASS while **not testing the caching proxy at all**.

When the goal is cache integration, import the necessary components and cache configuration, or use `@SpringBootTest` as shown. Never infer from a `@WebMvcTest` with a mocked service that `@CachePut`/`@CacheEvict` work in production.

### 21.3 Pure unit tests

~~~java
BookQueryService service = new BookQueryService(fakeCatalog);
service.get("A");
service.get("A");
~~~

This test checks target method logic, not AOP. It remains useful for branching and error handling, but you still need at least one Spring proxy integration suite when caching is an important contract.

### 21.4 Mockito spy: verify the right layer

If using `@MockitoSpyBean` on a bean in Spring Boot 3.4+/Framework 6.2, distinguish spying on the target method from wrapper/proxy interactions. A spy on a collaborator is fine when expecting target work to be skipped, but do not use `verify(proxy).get("A")` as evidence of cache miss counts: the proxy still receives two external calls. A catalog with an explicit counter, as in this lesson, is easier to reason about and avoids target/proxy spy confusion.

## 22. When the cache provider is Redis/Caffeine instead of ConcurrentMap

The in-memory suite verifies **Spring caching advice**, not the full behavior of a production provider.

### 22.1 Caffeine

Caffeine has size eviction, TTL/expire-after-access, stats, and its own concurrency semantics. If business logic depends on TTL, use `CaffeineCacheManager` with real configuration and a controllable `Clock`/`Ticker` to avoid sleeping. Tests must prove:

- Before TTL: cache hit.
- After TTL: loader runs again.
- Max size: older entries can be evicted.
- Correctness under concurrent misses.

The simple ConcurrentMap cache in this example does not auto-expire, so it **cannot** substitute for TTL tests.

### 22.2 Redis

Redis is a distributed store with serialization, key prefixes, TTL, network failures, and multiple application instances. Tests should run real Redis via Testcontainers or an isolated integration environment with per-suite namespaces/prefixes. Verify:

- Cache key prefixes isolate regions and tenants properly.
- Serializer preserves data types and versions accurately.
- TTL and invalidation are visible across JVM instances.
- Redis unavailable: application fallback/error policy behaves as designed.
- `allEntries` eviction has reasonable scope and cost without deleting other tests' data.

Do not run `FLUSHALL` against a shared or production Redis server; clean up by dedicated prefix/DB and ephemeral environments.

### 22.3 Which CacheManager gets auto-configured?

Boot checks dependencies and available beans before selecting a provider. If a project accidentally adds Redis or Caffeine dependencies, the chosen `CacheManager` can change. Defining an explicit `CacheManager` bean here keeps tests predictable; production should have dedicated configuration and tests for the actual deployed provider.

## 23. Caching and transactions: subtle stale-data risks

Consider a method:

~~~java
@Transactional
@CachePut(cacheNames = "books", key = "#result.isbn()")
public Book save(Book book) {
    return repository.save(book);
}
~~~

This is an illustrative snippet. Cache updates and DB commits do not automatically happen **atomically** just because both annotations are present. Depending on AOP advice ordering and the `CacheManager`, the cache may receive a value before the DB transaction commits, or a DB transaction may roll back after the cache operation, leaving **uncommitted** data in the cache.

### 23.1 Why @Transactional tests easily give false passes

A `@SpringBootTest @Transactional` test typically rolls back database state on the test thread, whereas a cache entry is state **outside the DB transaction**. If `@CachePut` updates the cache during the test, at the end of the test the DB rolls back while the cache entry remains. Subsequent tests may read rolled-back data from the cache.

Mitigations depend on architecture:

- Use a transaction-aware cache decorator/manager where appropriate, deferring cache puts/evicts until after commit.
- Perform invalidation in `@TransactionalEventListener(phase=AFTER_COMMIT)` when business rules require post-commit invalidation only.
- With outbox/eventual consistency, verify event delivery and cache invalidation after real commits.
- Write integration tests with **real commits**, testing rollbacks and cache readbacks on an independent connection/transaction.
- Avoid assuming `@Rollback` cleans up `CacheManager`; it does not automatically clear Redis, Caffeine, or ConcurrentMap entries.

**Simply enabling transaction-aware caching does not yield distributed atomicity** between a DB and Redis. Crash windows, retries, and event semantics still need handling when strong consistency matters.

### 23.2 Concurrency / cross-node invalidation

One instance updating the DB and evicting its local cache does not automatically evict another instance's cache. In replicated applications, use a distributed cache, pub-sub/invalidation strategy, or business-bounded TTL. A single-context proxy test is insufficient to prove cross-node consistency.

## 24. Secure cache keys and sensitive data

With `@Cacheable` on services returning user/tenant-specific data:

- Keys must include all parameters determining the output, such as `tenantId`, `locale`, and permissions version when relevant.
- `tenantId` must come from an **authenticated identity**, not an untrusted query parameter.
- If the result depends on role/authority while the key only contains a resource ID, data can leak between users.
- Do not store tokens, passwords, secrets, or unnecessary PII in keys, values, or logs.
- Cache contents may require encryption, TTL, and invalidation on permission changes.
- When permissions are revoked, verify whether the cache continues serving stale data beyond policy.

A good cross-tenant test uses two principals with tenant A and tenant B, the same ISBN, and asserts two separate cache keys/data scopes; this requires proper authentication/authorization setup beyond this lesson's basics.

## 25. @Cacheable(sync=true), thundering herd, and timing tests

When multiple threads miss the same key simultaneously, default caching can allow multiple loaders to run concurrently before an entry exists. `@Cacheable(sync=true)` is supported by Spring to request synchronized loading in cache providers that support it.

**Checklist before applying:**

1. Does the provider support synchronized loading semantics?
2. Does the operation target a single cache name and avoid unsupported `unless`/multi-cache setups?
3. Are there multiple JVM instances? A local lock does not prevent cluster-wide thundering herds.
4. Does the loader have timeouts and failure handling?
5. Do concurrency tests use `CountDownLatch`/`CyclicBarrier` rather than `Thread.sleep` for synchronization?
6. Is the backend call count verified accurately per key?

A sample concurrency test can fire two concurrent requests for the same key and verify the loader runs only once when `sync=true` and the provider allows it. Ensure the executor is shut down and `awaitTermination` is called in `finally`, and do not share the cache instance with parallel tests. This is an **advanced testing guide**, not part of the 15 demo methods.

**Do not benchmark cache hits by comparing nanoseconds of two calls in CI.** Backend load counts and cache state are what determine behavior; throughput/latency benchmarks require a dedicated measurement setup.

## 26. Common mistakes when testing caching proxies

**1. Calling `new BookQueryService(...)` and expecting caching to work.**  
Raw objects have no Spring proxy. Use an `@Autowired` bean and `AopUtils` assertions.

**2. A method calling `this.get()` inside the same bean.**  
Self-invocation bypasses the proxy; refactor into another cached bean.

**3. Only asserting that two return values are equal.**  
The repository may load twice and still return equal values. Assert the `reads` count.

**4. Only asserting that the bean is a proxy.**  
The proxy could be for a different advice; test behavior + cache store state.

**5. Setting `spring.cache.type=none` in tests.**  
A no-op provider disables real caching; suitable only for tests not verifying caching.

**6. Forgetting `@EnableCaching`.**  
Annotations sit in source code without being advised.

**7. `@CachePut` using a different key than `@Cacheable`.**  
The cache keeps a stale entry under the old key; read-after-write tests catch this.

**8. Expecting `@CachePut` to skip the method when the key exists.**  
Wrong: `@CachePut` always executes.

**9. Treating `@CacheEvict` as deleting a DB record.**  
It only removes from the cache; the source of truth needs separate mutation.

**10. Assuming `@CacheEvict` always runs when the method throws.**  
Default `beforeInvocation=false` evicts only on success.

**11. Using `beforeInvocation=true` without understanding rollback.**  
Eviction can occur even if the command fails or the DB rolls back.

**12. Declaring `key` together with `allEntries=true`.**  
Meaningless or invalid; `allEntries` clears the entire region.

**13. Clearing the wrong cache name.**  
If queries use `"books"` while commands evict `"book"`, stale entries remain.

**14. Not clearing caches between test methods.**  
Spring context cache reuse makes tests order-dependent.

**15. Using `@DirtiesContext` to mask shared cache pollution.**  
Expensive startup; clear caches/namespaces according to ownership instead.

**16. Enabling JUnit parallelism on a shared CacheManager with identical keys.**  
Test A clears while Test B asserts; use unique keys/contexts or disable parallelism.

**17. Not testing `condition` false / `unless` true.**  
A typo in SpEL can cache data that must not be cached.

**18. Caching a mutable entity and mutating it directly.**  
Tests can "see new data" without any put or evict.

**19. Cache keys missing tenant/user scope.**  
Risks data leakage; test cross-tenant access with the same resource ID.

**20. Treating ConcurrentMap as Redis/Caffeine.**  
Fails to verify TTL, serialization, cross-node consistency, or network failures.

**21. Mocking a cached service in `@WebMvcTest` and claiming the proxy works.**  
Mocking bypasses the real Spring cache advisor; an integration test is required.

**22. Assuming test transaction rollback rolls back the cache.**  
Caches outside DB transactions do not roll back automatically.

**23. Arbitrarily combining `@Cacheable` and `@CachePut` on one method.**  
Skip vs. always-run semantics conflict; separate read and write methods.

**24. Placing `@Cacheable` on private/final methods in proxy mode.**  
May not be intercepted; use public non-final proxied beans or another design.

**25. Having multiple CacheManagers without specifying the right `cacheManager`/`cacheResolver`.**  
Keys/entries may live in a different provider than where the test looks.

**26. Converting exceptions to `null` without checking policy.**  
Some providers cache null/negative responses; test if business rules forbid stale not-found results.

**27. Observing a cache hit on one thread and assuming multi-node consistency.**  
Requires distributed provider integration and cross-instance invalidation tests.

**28. Using the cache as a security layer.**  
Cache keys and isolation do not replace authorization or row-level security.

## 27. Workflow for building a cache test suite in real projects

1. Identify cached methods and sources of truth (DB/remote API).
2. List cache names, `CacheManager`/provider, cache key expressions, and TTLs.
3. Verify Spring actually enables caching and beans are invoked via proxies.
4. Choose test layers: unit for business logic, Spring proxy integration for annotations, provider integration for Redis/Caffeine.
5. Isolate cache keys/instances and repository data in `@BeforeEach`.
6. Verify `@Cacheable` miss→hit and exact backend load counts.
7. Verify keys A/B or tenants A/B do not overwrite each other.
8. Verify result types, Optional/null/exception policies explicitly.
9. Verify `condition` and `unless` with both positive and negative cases.
10. Verify `@CachePut` always invokes and updates entries read by `@Cacheable`.
11. Verify `@CacheEvict` by key, `allEntries`, after success, and before exception.
12. Verify `@Caching` when a single action must clear multiple regions.
13. Test self-invocation/raw instances to understand proxy boundaries; refactor if production code expects internal caching.
14. Verify full context with a real `CacheManager`, not `NoOpCacheManager`.
15. If `@Transactional` is present, test commit/rollback and post-transaction cache state.
16. If TTL/serialization/distributed caching applies, use the real provider in integration tests.
17. If data is sensitive, verify tenant/permission scopes on cache keys.
18. Avoid wall-clock performance assertions in CI; use call counts and controlled time.
19. Run the suite repeatedly to confirm no order dependencies or parallel races.
20. Document clearly which tests prove Spring caching advice and which prove the production provider.

### Final checklist

- [ ] `@EnableCaching` is loaded in the context testing caching.
- [ ] `@Autowired` beans are verified to be AOP proxies or exhibit equivalent behavior.
- [ ] Backend load counts prove cache hits skip the target method.
- [ ] Cache entries and keys are asserted accurately.
- [ ] `@CachePut` always executes and updates the right cache key.
- [ ] `@CacheEvict` removes the right key or `allEntries`; exception semantics are tested.
- [ ] `@Caching` covers every cache region that needs invalidation.
- [ ] `condition` and `unless` are tested across branches.
- [ ] Self-invocation is not mistaken for an external proxy call.
- [ ] Test context caching does not leak entries between methods.
- [ ] NoOp provider is not used as proof of caching.
- [ ] If DB rollbacks exist, cache cleanup/consistency has dedicated tests.
- [ ] If Redis/Caffeine is used, provider behavior is tested against that provider.
- [ ] Tenant/user key scoping prevents cross-tenant leakage.
- [ ] JUnit examples do not rely on timing/`sleep` or live external networks.

## 28. Conclusion

**Testing Spring Cache must go through Spring bean proxies**, because `@Cacheable`, `@CachePut`, and `@CacheEvict` do not alter the behavior of an object instantiated with `new`, nor do they activate on self-invocation in AOP proxy mode. A solid test proves four things together:

1. **Value**: what result is returned.
2. **Actual calls**: whether the source-of-truth/repository was called or skipped.
3. **Cache state**: entries, keys, and cache regions are populated or evicted properly.
4. **Proxy**: callers go through a Spring-advised bean.

In the demo, `@Cacheable` reduces reads, `@CachePut` updates the cached `Book` while always calling `store`, `@CacheEvict` handles invalidation and before/after exception behavior, and `@Caching` coordinates multiple regions. When scaling to Redis/Caffeine, database transactions, or multiple tenants, add tests for TTL, serialization, commit timing, and security isolation rather than treating a ConcurrentMap suite as sufficient for production.

### Official references

- [Spring Framework 6.2 — Cache Abstraction](https://docs.spring.io/spring-framework/reference/6.2/integration/cache.html): cache/cache-manager/key abstraction and AOP integration.
- [Spring Framework 6.2 — Declarative Cache Annotations](https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html): `@Cacheable`, `@CachePut`, `@CacheEvict`, `@Caching`, `@CacheConfig`, `sync`, `condition`/`unless`.
- [Spring Framework 6.2 — AOP Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): external proxy calls, self-invocation, and alternatives.
- [Spring Framework 6.2 — Cacheable API](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/cache/annotation/Cacheable.html): `key`, `condition`, `unless`, `sync`, and result caching.
- [Spring Framework 6.2 — CachePut API](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/cache/annotation/CachePut.html): always invoke and `#result`.
- [Spring Framework 6.2 — CacheEvict API](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/cache/annotation/CacheEvict.html): `allEntries`, `beforeInvocation`, and exception handling.
- [Spring Boot 3.5 — Caching](https://docs.spring.io/spring-boot/3.5/reference/io/caching.html): `starter-cache`, provider selection, no-op mode, and testing.
- [Spring Framework — Transaction-aware Cache Decorator](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheDecorator.html): post-commit cache operation timing where appropriate.
