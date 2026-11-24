# Clearing Caches Between Test Cases and Verifying the Real Cache Provider

## 1. The problem: green unit tests, but integration tests hit stale cached data

Suppose a Spring Boot service has a method:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public String find(String sku) {
    return productSource.load(sku);
}
```

The first time `find("CAM-01")` is called, the method runs and its result is cached. On the second call with the same key, Spring can return a cache hit without running `productSource.load`. That is the behavior we want to test.

However, if test A cached `CAM-01`, and test B modifies the source data and reads the same key **without clearing the cache**, test B can receive the stale result. Tests pass in isolation but fail as a suite. Another even more dangerous cause exists: the team thinks it is testing real Redis, while Spring Boot actually fell back to `ConcurrentMapCacheManager`/Simple in-JVM cache, or `spring.cache.type=none` was active, meaning all assertions about "Redis cache" never touched Redis at all.

This lesson addresses **two distinct requirements**:

1. **Clear cache state between test cases** with the right scope: `CacheManager.getCache(...).clear()`, `Cache.evict(key)`, `@CacheEvict`, cache regions, namespaces, isolated providers, and test lifecycle hooks.
2. **Verify the actual provider in use** with multi-layer evidence: `CacheManager` type, hit/miss behavior and source invocation counts, **real Redis key/TTL state**, and evictions reflected down to the provider.

They are not interchangeable. A test with perfect `clear()` might still use the wrong provider; a test confirming a real `RedisCacheManager` can still be flaky if it does not reset keys between test methods.

The core example uses **Java 17, Spring Boot 3.3.0, Spring Cache, Spring Data Redis, Redis 7 in Testcontainers, and JUnit Jupiter**. We intentionally use a Java data source that counts calls rather than another database so the test focuses on the **real cache provider**. Advanced sections explain when to add a DB, multi-instance setups, race conditions, transactions, and CI integration testing.

## 2. Learning objectives

After this lesson, you will be able to:

1. Explain why the Spring Cache abstraction is not a cache store by itself: it needs a `CacheManager` + provider.
2. Distinguish `@Cacheable`, `@CachePut`, `@CacheEvict`, `Cache.evict(key)`, `Cache.clear()`, and provider-level resets.
3. Distinguish cache hits, misses, stale values, eviction, TTL expiration, manual refreshes, and test fixture mutations.
4. Know why `@EnableCaching`, AOP proxies, and external method invocations are critical prerequisites.
5. Use `@BeforeEach`/`@AfterEach` to clean up test-owned cache regions without disrupting other regions.
6. Understand that `@DirtiesContext` resets the Spring `ApplicationContext` but **does not guarantee clearing Redis data**.
7. Separate in-memory Caffeine caches from distributed Redis caches by lifecycle and state scope.
8. Use `spring.cache.type=redis` to enforce the provider instead of relying on implicit classpath detection.
9. Use `GenericContainer<?>` + `@ServiceConnection(name="redis")` with Spring Boot 3.3 to spin up real Redis for tests.
10. Avoid writing `RedisContainer` from third-party libraries as if it were an official Testcontainers core module.
11. Verify `RedisCacheManager`, actual Redis keys, TTL, cache hits/misses, and delete semantics via `StringRedisTemplate`.
12. Know why the default Redis key prefix is typically `cacheName::key` and when that format changes.
13. Understand Redis value serialization: Spring Data Redis cache may use JDK serialization by default; do not read binary values with a String decoder and conclude the cache is broken.
14. Write JUnit tests verifying single-key retention, single-key eviction, full-region eviction, setup/teardown clearing, and that exceptions are not cached.
15. Distinguish TTL expiration from explicit eviction; never use fixed `Thread.sleep` as the primary oracle.
16. Design namespaces/prefixes/isolated brokers for concurrent CI jobs, avoiding `FLUSHALL`/`FLUSHDB` on shared Redis.
17. Understand that `Cache.clear()` may issue Redis `KEYS`/`DEL`, causing scan/latency/races on large keyspaces.
18. Watch out for `@Transactional`, commit timing, cache stampedes, stale replication, and async/reactive cache managers.
19. Diagnose common failures: mock vs. real provider, cache proxy bypass, wrong cache name/key, serialization, timeouts, context caching, and parallel tests.
20. Distinguish **expected results** in documentation from **executed Gradle/JUnit runs**.

## 3. The Spring Cache layer and the storage layer are two different things

```text
ProductCatalog.find("CAM-01")
        |
        v
Spring AOP CacheInterceptor
        |
        +-- Compute cache key: "CAM-01"
        +-- Resolve cache region: "products"
        |
        v
CacheManager
        |
        +-- ConcurrentMapCacheManager (local JVM)
        +-- CaffeineCacheManager     (local JVM with eviction policy)
        +-- RedisCacheManager        (external Redis server)
        +-- JCache/Hazelcast/...     (other provider implementations)
        |
        v
Cache.get(key)
        |
        +-- HIT: return cached value, skip target method
        |
        +-- MISS: invoke ProductSource.load(key)
                  then cache result (subject to policy)
```

Spring's `@Cacheable` annotation does not contain a cache engine. It only declares a **cache operation**; execution is delegated to a `CacheManager`/`Cache` implementation. The provider itself determines storage, serialization, TTL, eviction, and sharing across JVMs.

### 3.1. Same annotation, not identical behavior

| Attribute | Simple/ConcurrentMap | Caffeine | Redis |
| --- | --- | --- | --- |
| Storage location | JVM heap | JVM heap | Redis server/process |
| Shared across app instances | No | No | Yes, if sharing Redis namespace |
| JVM restart | Cache lost | Cache lost | Redis may retain data |
| TTL/LRU | No full built-in policies | Supported via spec/config | TTL from Redis cache configuration |
| Network serialization | No | No | Yes, per RedisCache serializer |
| `Cache.clear()` | Clears local map | Invalidates local region | Deletes matching Redis keys |
| Test provider-specific errors | No network | No network | Auth/socket/serialization/TTL/etc. |
| Test isolation | Local context/JVM | Local context/JVM | Requires cleaning Redis namespace/broker |
| Docker needed for lab | No | No | Yes, with Testcontainers |

You cannot run a Caffeine/Map unit test and claim to have verified Redis serialization, Redis key prefixes, TTL, network failures, or multi-instance consistency.

### 3.2. How does Spring Boot choose a provider automatically?

Spring Boot includes cache auto-configuration that selects a provider based on the classpath and available beans. When multiple providers are present, detection order can create differences between machines or test profiles.

Example:

```properties
spring.cache.type=redis
spring.cache.cache-names=products
spring.cache.redis.time-to-live=60s
spring.cache.redis.cache-null-values=false
```

By setting `spring.cache.type=redis`, the integration test **forbids** the application from silently falling back to another provider to turn the test green. If Redis cannot connect, the test fails on provider operations rather than continuing against a local map.

These values are passed directly into `@SpringBootTest(properties=...)` in the runnable example. **Never use `spring.cache.type=none`** in a test meant to prove caching.

## 4. Cache hit, miss, eviction, and TTL

### 4.1. Cache miss

When the key does not exist, `CacheInterceptor` invokes the target method, stores the result (when conditions allow), and returns the value.

```text
GET products["CAM-01"] -> MISS
source.load("CAM-01") -> "CAM-01#load-1"
PUT products["CAM-01"] = "CAM-01#load-1"
return "CAM-01#load-1"
```

### 4.2. Cache hit

Next call with the same key:

```text
GET products["CAM-01"] -> HIT
return "CAM-01#load-1"
source.load(...) does not run
```

An `assertEquals(result1, result2)` assertion is **not enough**: the source could simply return the same string every time without caching. You must prove both that **source invocation counts did not increase** or observe provider state.

### 4.3. Evicting a single key

`Cache.evict(key)` or `@CacheEvict(cacheNames="products",key="#p0")` removes the mapping for a single key. The next `@Cacheable` call will miss and reload.

Eviction does not update source data. Deleting a cache key does not delete a database row; deleting a database row does not automatically delete a cache entry unless the application implements an invalidation policy.

### 4.4. Evicting every entry in a cache region

`Cache.clear()` or `@CacheEvict(cacheNames="products",allEntries=true)` deletes all entries in the `products` region, **not every Redis key across every application**. This holds true when cache configuration/namespaces are designed properly and executed correctly by the provider.

**Limitation:** In Redis, the default cache writer may use prefix scanning/deletion (some versions/strategies use `KEYS`); operating on large keyspaces or shared namespaces can be expensive and is not an atomic transaction against concurrent writers. This lab uses a private RedisContainer with only a few keys.

### 4.5. TTL expiration

An entry with a 60-second TTL lives until expiration (unless deleted or overwritten per provider policy). TTL is **time-based expiration**, not `@AfterEach` test cleanup. When a test needs deterministic isolation, **do not wait for TTL to elapse**; evict or clear within the proper scope.

Specifically, Redis TTL is normally **time-to-live**, not time-to-idle. Reading a cached value does not automatically reset TTL under default `RedisCache` behavior. TTI setups, especially in newer Spring Data Redis versions, require specific API and Redis server compatibility.

## 5. How @Cacheable, @CachePut, and @CacheEvict differ

| Annotation/API | Behavior | Test scenario |
| --- | --- | --- |
| `@Cacheable` | Checks cache first; skips target method on hit | 2 calls → source count 1 |
| `@CachePut` | Invokes method and updates cache with result | Update source then read again |
| `@CacheEvict(key=...)` | Removes a single entry | Cache A/B, evict A, B still hits |
| `@CacheEvict(allEntries=true)` | Clears an entire cache region | Deletes all `products` entries |
| `Cache.evict(key)` | Evicts programmatically via Cache abstraction | Key-level setup/teardown |
| `Cache.clear()` | Clears entire region via Cache abstraction | `@BeforeEach`/`@AfterEach` on private Redis |
| Redis `DEL` | Deletes a raw Redis key | Provider-level verification |
| Redis `FLUSHDB` | Wipes an entire Redis logical DB | Dangerous on shared databases |
| Redis `FLUSHALL` | Wipes all logical DBs on the server | Extremely dangerous on shared servers |

### 5.1. `beforeInvocation` on `@CacheEvict`

`@CacheEvict` defaults `beforeInvocation` to `false`; eviction runs after the method completes successfully under synchronous semantics. If the method throws an exception, eviction may not happen. `beforeInvocation=true` triggers eviction before the method executes, even if the method later fails.

Illustrative example, **not part of the runnable lab source**:

```java
@CacheEvict(
        cacheNames = "products",
        key = "#p0",
        beforeInvocation = true)
public void invalidateBeforeWork(String sku) {
    doPotentiallyFailingWork(sku);
}
```

Do not pick `beforeInvocation=true` just to make tests pass easily: if a DB update fails after the cache is cleared, users can suffer unnecessary misses or stampedes. With transactions, design eviction around the commit boundary and test it explicitly.

### 5.2. `@CachePut` does not replace `@Cacheable`

`@CachePut` always executes the method and updates the cache, so do not use it to prove cache hits skip reading the source. Combining `@Cacheable` and `@CachePut` on the same method leads to confusing semantics; keep read, update, and invalidate methods distinct.

### 5.3. Key expressions must match

The example uses `key="#p0"` instead of `key="#sku"` so the key resolves even without compiled parameter name metadata. If one method uses `#p0` while the eviction method accidentally uses `#p1` or formats the key differently, eviction will not delete the entry that was created.

## 6. Proxies and @EnableCaching: why tests see the wrong call counts

Spring `@Cacheable` is normally enforced by an AOP proxy. In default proxy mode:

- Calling a public annotated method from another bean → intercepted.
- Instantiating `new ProductCatalog(...)` outside Spring → no cache proxy.
- Calling `this.find(...)` inside `ProductCatalog` itself (self-invocation) → typically bypasses the proxy.
- Annotating a private/final method or misconfiguring proxies → interception is not guaranteed.
- Forgetting `@EnableCaching` → annotations produce no caching behavior.

```java
@Service
class Example {
    @Cacheable(cacheNames = "products")
    public String find(String id) { return "value"; }

    public String insideSameBean(String id) {
        return this.find(id); // usually bypasses the Spring cache proxy
    }
}
```

This is illustrative code. In the runnable lab, JUnit injects the `ProductCatalog` bean from the Spring context and invokes `catalog.find(...)` from outside the bean, ensuring cache interception actually runs.

### 6.1. How to detect that caching is disabled

A solid test includes both assertions:

```java
String first = catalog.find("CAM-01");
String second = catalog.find("CAM-01");

assertEquals(first, second);
assertEquals(1, source.calls());
```

If `@EnableCaching` is removed, the source call count becomes 2 and the test fails, even though the return values look identical.

### 6.2. AOP proxies and `@MockBean`

In Boot 3.3, `@MockBean` can replace a bean in the `ApplicationContext`. If you mock `ProductCatalog` itself while trying to test its cache annotations, you can bypass both the proxy and storage operations. Mock the **data source/repository collaborator** in separate unit tests, while keeping the **real `ProductCatalog` bean** in provider integration tests.

In the Redis lab, the source itself is a real Java component counting invocations so Mockito deep stubbing does not obscure side effects. There is no database in the lab because the goal is verifying the Redis cache layer.

## 7. Determining the right test level

| Test type | Provider | Can prove | Cannot prove |
| --- | --- | --- | --- |
| Plain unit test | Mockito `Cache` interface | Business fallback/invalidation choice | Redis key/TTL/network |
| Spring test with Simple cache | `ConcurrentMapCacheManager` | Basic annotation/proxy behavior | Redis provider |
| Spring test with Caffeine | `CaffeineCacheManager` | Local eviction/TTL/size policies | Multi-instance Redis state |
| Boot integration + Redis Testcontainers | `RedisCacheManager` + Redis container | Actual keys, TTL, serialization path, eviction | Managed Redis HA/TLS/ACL/cluster |
| 2 application contexts against same Redis | Redis distributed cache | Multi-instance sharing/invalidation | Full production topology |
| Deployment/staging test | Managed cache + network | Provider auth/topology/operability | Every production race/traffic pattern |

Do not just assert `cacheManager != null`: every `CacheManager` passes that. To prove real Redis is used, assert the implementation type **and provider-side key presence**.

## 8. Cache cleanup strategies between JUnit tests

### 8.1. `@BeforeEach`

`@BeforeEach` clears the cache before test setup and fixture assertions. It prevents state from an earlier test from giving the next test an unintended cache hit. If the source is a shared in-memory counter, reset the counter **after clearing the cache**, so subsequent calls start cleanly at 1.

```java
@BeforeEach
void beforeEach() {
    Cache cache = cacheManager.getCache("products");
    assertNotNull(cache);
    cache.clear();
    source.reset();
}
```

This is an illustrative snippet; in the runnable project, the `productsCache()` helper checks cache existence and the setup method also removes a test-owned sentinel key.

### 8.2. `@AfterEach`

`@AfterEach` cleans up the cache after the test (even on normal assertion failures), reducing state leakage into later classes or suites. Do not rely on `@AfterEach` alone because if the test process crashes, teardown never runs.

```java
@AfterEach
void afterEach() {
    productsCache().clear();
}
```

In a private Redis setup, clearing both before and after each method is straightforward. If running in parallel against the **same cache namespace**, one test's `@AfterEach` can delete keys still in use by another test: use unique prefixes/regions/providers or serialize test execution.

### 8.3. When should you use `@BeforeAll`/`@AfterAll`?

- `@BeforeAll`: prepare a dedicated provider/topic/namespace; does not replace per-test isolation if tests share keys.
- `@AfterAll`: stop class-scoped resources/providers and clean up owned namespaces.
- `@Testcontainers @Container static`: the Redis container lives for the duration of one test class, then the Testcontainers extension stops it.
- If multiple classes share a container or Redis namespace, define an explicit policy; do not assume JUnit class teardown erased shared provider state.

### 8.4. Do not treat `@DirtiesContext` as Redis cleanup

`@DirtiesContext` tells Spring TestContext to discard the cached application context and recreate it according to mode, but **external Redis keys remain on the Redis server** if the server stays alive. The new `RedisCacheManager` bean can read those exact stale keys.

Similarly, `@Transactional` on a Spring test normally rolls back the database transaction managed on the test thread; it **does not automatically roll back Redis `SET`/`DEL`**; cache puts and evictions can execute outside the transaction boundary. Clean up caches separately.

## 9. Using CacheManager without nuking all of Redis

In tests, clear only the products cache:

```java
Cache cache = cacheManager.getCache("products");
if (cache == null) {
    throw new IllegalStateException(
            "Missing products cache");
}
cache.clear();
```

**Benefit:** independent of how the cache provider currently stores keys/values. With Caffeine, it clears the local cache. With Redis, the provider deletes keys belonging to that region per configuration.

**Limitation:** `Cache.clear()` can still be costly and non-atomic under concurrent writes. It does not clean up orphan keys from legacy cache names, other TTLs, or externally created Redis namespaces.

### 9.1. Cleaning up specific keys

When multiple tests share a provider, `cache.evict(sku)` is narrower than `clear()`. If a test created `"CAM-01"`, delete only `"CAM-01"` instead of the whole region. Even so, with **parallel tests using the same key**, both evicts and source counters race; use unique IDs.

### 9.2. `FLUSHDB` and `FLUSHALL`: never use as the default

Redis `FLUSHDB` deletes every key in the selected logical DB; `FLUSHALL` wipes all logical DBs. On shared Redis, they can destroy sessions, rate-limit counters, locks, queues, and other applications' caches, causing severe damage.

**In a private Testcontainers lab**, you own the entire container for the class, yet you should still practice scoped cleanup of the `products` region. That builds clear ownership habits and prevents accidentally carrying `FLUSHALL` into shared environments.

## 10. Runnable project — Java 17 + Spring Boot 3.3 + Redis Testcontainers

The project uses **one test class** to avoid mismatches between Testcontainers class lifecycles and Spring TestContext caching across multiple classes. It uses `GenericContainer<?>` for the Redis image rather than assuming an official `RedisContainer` exists in Testcontainers 1.x.

### 10.1. Directory layout

```text
redis-cache-integration/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/cache/
    │   ├── CacheLabApplication.java
    │   ├── ProductSource.java
    │   └── ProductCatalog.java
    └── test/java/example/cache/
        └── RedisCacheIsolationTest.java
```

Wrapper binary files are not listed; if creating a Gradle Wrapper, use a compatible Gradle version (e.g., 8.7) and commit the wrapper in real projects.

### 10.2. settings.gradle

```groovy
rootProject.name = 'redis-cache-integration'
```

### 10.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
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
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Why only these dependencies?**

- `spring-boot-starter-cache`: Spring Cache abstraction and supporting configuration.
- `spring-boot-starter-data-redis`: Spring Data Redis/Lettuce Redis clients and `RedisCacheManager` auto-configuration.
- `spring-boot-starter-test`: JUnit Jupiter, AssertJ, Spring Test.
- `spring-boot-testcontainers`: Spring Boot `@ServiceConnection` support.
- `org.testcontainers:junit-jupiter`: Testcontainers JUnit 5 extension; brings in required Testcontainers core artifacts.
- No separate Redis Testcontainers module is needed, as none exists in the official core module set used here.

With Spring Boot 3.3 dependency management, compatible versions are coordinated via the Boot BOM. If upgrading Testcontainers major versions or Spring Data Redis, review breaking changes rather than copying imports across versions.

### 10.4. CacheLabApplication.java

**src/main/java/example/cache/CacheLabApplication.java**

```java
package example.cache;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.annotation.EnableCaching;

@SpringBootApplication
@EnableCaching
public class CacheLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                CacheLabApplication.class, args);
    }
}
```

`@EnableCaching` turns on Spring cache interception. There is no Web starter in the lab: this is an application context for service/cache tests without starting an HTTP server.

If `@EnableCaching` is removed, `@Cacheable` will not intercept method calls and the source call count will increase on both reads, causing the test to fail.

### 10.5. ProductSource.java — fake but countable data source

**src/main/java/example/cache/ProductSource.java**

```java
package example.cache;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Component;

@Component
public class ProductSource {

    private final AtomicInteger calls = new AtomicInteger();

    public String load(String sku) {
        int n = calls.incrementAndGet();

        if ("FAIL".equals(sku)) {
            throw new IllegalStateException(
                    "Backend unavailable");
        }

        return sku + "#load-" + n;
    }

    public int calls() {
        return calls.get();
    }

    public void reset() {
        calls.set(0);
    }
}
```

**Why not use a real database?** This lesson only aims to prove Redis cache behavior. `ProductSource` is a **deterministic Java data source simulator**, not a DB. With `AtomicInteger`, tests check the exact number of source loads. When you need to verify cache + JPA consistency, add a database Testcontainers setup separately; do not mistake this demo for a DB integration test.

**Why return `String`?** Spring Data Redis `RedisCacheManager` can default to Java/JDK serialization for values; `String` implements `Serializable`. Returning a custom record/entity that is not `Serializable` without configuring a custom serializer can trigger `SerializationException`. Studying Redis storage does not require choosing a complex DTO serializer.

### 10.6. ProductCatalog.java — @Cacheable and @CacheEvict

**src/main/java/example/cache/ProductCatalog.java**

```java
package example.cache;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductCatalog {
    private final ProductSource source;

    public ProductCatalog(ProductSource source) {
        this.source = source;
    }

    @Cacheable(cacheNames = "products", key = "#p0")
    public String find(String sku) {
        return source.load(sku);
    }

    @CacheEvict(cacheNames = "products", key = "#p0")
    public void invalidate(String sku) {
        // Eviction happens through Spring Cache proxy.
    }

    @CacheEvict(cacheNames = "products", allEntries = true)
    public void invalidateAll() {
        // Clears only the "products" cache region.
    }
}
```

All three methods are **public** and invoked from tests through the Spring-managed `ProductCatalog` bean, ensuring the cache advisor can intercept them. Do not call `this.find(...)` inside the same class to simulate an external call. `#p0` refers to the first argument, avoiding reliance on parameter name metadata.

**`@CacheEvict` on a `void` method:** valid, because eviction does not require a return value. `beforeInvocation=false` is the default, so on a synchronous `void` method that does not throw, eviction happens after the method finishes.

## 11. RedisCacheIsolationTest.java — integration test using real Redis

**src/test/java/example/cache/RedisCacheIsolationTest.java**

```java
package example.cache;

import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@SpringBootTest(properties = {
        "spring.cache.type=redis",
        "spring.cache.cache-names=products",
        "spring.cache.redis.time-to-live=60s",
        "spring.cache.redis.cache-null-values=false"
})
class RedisCacheIsolationTest {

    @Container
    @ServiceConnection(name = "redis")
    static final GenericContainer<?> REDIS =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7.2-alpine"))
                    .withExposedPorts(6379);

    private static final String OTHER_KEY =
            "integration:other-sentinel";

    @Autowired
    CacheManager cacheManager;

    @Autowired
    ProductCatalog catalog;

    @Autowired
    ProductSource source;

    @Autowired
    StringRedisTemplate redis;

    private Cache productsCache() {
        Cache cache = cacheManager.getCache("products");
        assertNotNull(cache);
        return cache;
    }

    private String redisKey(String sku) {
        // Default RedisCache prefix: cacheName + "::".
        return "products::" + sku;
    }

    private boolean exists(String key) {
        return Boolean.TRUE.equals(redis.hasKey(key));
    }

    @BeforeEach
    void resetStateBeforeTest() {
        productsCache().clear();
        redis.delete(OTHER_KEY);
        source.reset();
    }

    @AfterEach
    void clearOwnedStateAfterTest() {
        productsCache().clear();
        redis.delete(OTHER_KEY);
    }

    @Test
    void usesRedisCacheManagerAndStoresActualRedisKey() {
        assertTrue(REDIS.isRunning());
        assertInstanceOf(
                RedisCacheManager.class, cacheManager);

        assertFalse(exists(redisKey("CAM-01")));

        assertEquals(
                "CAM-01#load-1",
                catalog.find("CAM-01"));

        assertTrue(exists(redisKey("CAM-01")));
        assertEquals(1, source.calls());
    }

    @Test
    void cacheHitSkipsCallingSourceAgain() {
        String first = catalog.find("CAM-02");
        String second = catalog.find("CAM-02");

        assertEquals("CAM-02#load-1", first);
        assertEquals(first, second);
        assertEquals(1, source.calls());

        assertNotNull(productsCache().get("CAM-02"));
        assertTrue(exists(redisKey("CAM-02")));
    }

    @Test
    void redisEntryHasConfiguredPositiveTtl() {
        catalog.find("CAM-03");

        Long ttl = redis.getExpire(
                redisKey("CAM-03"),
                TimeUnit.SECONDS);

        assertNotNull(ttl);
        assertTrue(ttl > 0 && ttl <= 60,
                "Expected a positive TTL up to 60s; " +
                "actual=" + ttl);
    }

    @Test
    void evictOneKeyLeavesOtherProductCached() {
        assertEquals(
                "A#load-1",
                catalog.find("A"));
        assertEquals(
                "B#load-2",
                catalog.find("B"));

        catalog.invalidate("A");

        assertFalse(exists(redisKey("A")));
        assertTrue(exists(redisKey("B")));

        assertEquals(
                "A#load-3",
                catalog.find("A"));
        assertEquals(
                "B#load-2",
                catalog.find("B"));
        assertEquals(3, source.calls());
    }

    @Test
    void evictAllClearsProductsButKeepsUnrelatedKey() {
        catalog.find("A");
        catalog.find("B");
        redis.opsForValue().set(
                OTHER_KEY, "not-a-product-cache-entry");

        catalog.invalidateAll();

        assertFalse(exists(redisKey("A")));
        assertFalse(exists(redisKey("B")));
        assertTrue(exists(OTHER_KEY));

        assertEquals("A#load-3", catalog.find("A"));
        assertEquals(3, source.calls());
    }

    @Test
    void directCacheClearRemovesUnderlyingRedisEntry() {
        assertEquals(
                "CAM-04#load-1",
                catalog.find("CAM-04"));
        assertTrue(exists(redisKey("CAM-04")));

        productsCache().clear();

        assertFalse(exists(redisKey("CAM-04")));

        assertEquals(
                "CAM-04#load-2",
                catalog.find("CAM-04"));
        assertEquals(2, source.calls());
    }

    @Test
    void exceptionsAreNotStoredAsCachedValues() {
        assertThrows(
                IllegalStateException.class,
                () -> catalog.find("FAIL"));
        assertFalse(exists(redisKey("FAIL")));

        assertThrows(
                IllegalStateException.class,
                () -> catalog.find("FAIL"));
        assertEquals(2, source.calls());
        assertFalse(exists(redisKey("FAIL")));
    }
}
```

**There are 7 `@Test` methods** in the integration class. This test runs a real Redis process in Testcontainers: because `StringRedisTemplate` queries the Redis server directly for keys and TTLs, it does not trust a fake `Cache` object alone.

### 11.1. Why `@ServiceConnection(name="redis")`?

`GenericContainer<?>` only means "a Docker container"; it has no `RedisContainer` Java type for Spring Boot to infer the service. In Boot 3.3, `@ServiceConnection(name="redis")` declares that this container supplies `RedisConnectionDetails`, pointing the auto-configured Spring Redis connection to the dynamic mapped host and port.

If `name="redis"` is omitted from `GenericContainer`, Boot may fail to identify the service type; the test might try connecting to default Redis on `localhost:6379` and fail—or worse, connect by mistake to a Redis instance running on the host.

**Never hardcode** `localhost:6379` for Testcontainers. Docker maps the host port dynamically; Boot's service connection feeds that port into `LettuceConnectionFactory`/Redis clients.

### 11.2. Why not `@DynamicPropertySource`?

`@DynamicPropertySource` is another valid way to supply `spring.data.redis.host` and `spring.data.redis.port` from the container. Since this example uses `@ServiceConnection`, do not configure both and risk confusing precedence. Pick one deliberate wiring path and verify it with provider-side assertions.

Alternative illustrative snippet (not part of the runnable class):

```java
@DynamicPropertySource
static void redisConnection(DynamicPropertyRegistry registry) {
    registry.add(
            "spring.data.redis.host", REDIS::getHost);
    registry.add(
            "spring.data.redis.port",
            () -> REDIS.getMappedPort(6379));
}
```

This snippet requires `DynamicPropertySource` and `DynamicPropertyRegistry` imports. If using this approach, remove `@ServiceConnection` to avoid redundant dual configuration.

### 11.3. Redis image version

`redis:7.2-alpine` is an **illustrative tag for learning**, not guaranteed to be the latest patched image. Production-grade CI should pin an approved image digest/version that has passed security review and matches the target architecture. `@ServiceConnection(name="redis")` works with the image name as long as provider behavior is compatible.

### 11.4. Why doesn't the project use a `RedisContainer` module?

Testcontainers 1.x core provides `GenericContainer` and modules for many services. For Redis, Spring Boot officially demonstrates `GenericContainer` with `@ServiceConnection(name="redis")`. Community or third-party `RedisContainer` classes exist, but do not assume they belong to official Testcontainers core. This avoids unresolved Gradle dependencies or Java imports.

## 12. Analyzing the "real provider" evidence

### 12.1. Assert the `CacheManager` type

```java
assertInstanceOf(
        RedisCacheManager.class, cacheManager);
```

If Spring Boot auto-configured `ConcurrentMapCacheManager` or Caffeine, this assertion fails immediately. Still, **asserting the class alone is not enough**: a `RedisCacheManager` could be instantiated without connecting to the right Redis container, or operations could fail when accessed.

### 12.2. Assert the real key in Redis

```java
catalog.find("CAM-01");
assertTrue(Boolean.TRUE.equals(
        redis.hasKey("products::CAM-01")));
```

`StringRedisTemplate` executes a Redis query against the server. With only a local cache, the Redis key would never appear. Combined with the cache hit count, this proves both Spring caching interception **and** provider storage.

**Key format caveat:** `products::CAM-01` is the default `RedisCache` key prefix under the lab configuration, not a universal contract across all apps. Custom `RedisCacheConfiguration.computePrefixWith(...)`, `disableKeyPrefix()`, `CacheKeyPrefix`, or key generators change the format. Tests in real applications should derive from config or lock down an explicit key-prefix contract rather than hardcoding a value when setup changes.

### 12.3. Assert TTL

```java
Long ttl = redis.getExpire(
        "products::CAM-03",
        TimeUnit.SECONDS);

assertNotNull(ttl);
assertTrue(ttl > 0 && ttl <= 60);
```

Redis TTL replies include special server values such as `-1` (key exists without expiration) and `-2` (key does not exist). Spring Data Redis templates return the corresponding numeric TTL. The test asserts a positive TTL within the configured bound without calling `Thread.sleep(60_000)`.

**Do not assert that TTL equals exactly 60**; by the time the test reads it, some time has already elapsed. If execution is so slow that the entry expires right away, the test fails; that signals an environment or test sizing issue rather than something to mask by inflating timeouts indefinitely.

### 12.4. Assert source count

```java
String first = catalog.find("CAM-02");
String second = catalog.find("CAM-02");

assertEquals(first, second);
assertEquals(1, source.calls());
```

If `@Cacheable` is missing or the proxy is bypassed, the source count becomes 2. If the cache provider fails to store the entry, the second call may miss; the test fails, revealing broken caching behavior.

### 12.5. Assert single-key eviction

In `evictOneKeyLeavesOtherProductCached`, the source loads A and then B. After `catalog.invalidate("A")`:

- Key A is gone.
- Key B remains.
- Reading A reloads from source, increasing the source count.
- Reading B returns the cached value, leaving the source count unchanged.

This proves eviction is **scoped to the single key**, not wiping all of Redis.

### 12.6. Assert `allEntries` does not touch keys outside the namespace

`evictAllClearsProductsButKeepsUnrelatedKey` creates a sentinel key `integration:other-sentinel` directly in Redis. `catalog.invalidateAll()` deletes A and B in the `products` cache, while the sentinel remains intact.

If you confused `@CacheEvict(allEntries=true)` with Redis `FLUSHDB`, the sentinel would vanish and the assertion would fail. This verifies region isolation at the storage layer.

## 13. Running the project and expected results

Requirements:

- JDK 17.
- Compatible Gradle Wrapper (e.g., Gradle 8.7).
- Docker or compatible container runtime.
- Permission to pull the Redis image and access Maven repositories/caches.

Linux/macOS:

```bash
./gradlew test
./gradlew test --tests example.cache.RedisCacheIsolationTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.cache.RedisCacheIsolationTest
```

**Expected:** All 7 JUnit tests pass when the Redis container starts, Spring Boot auto-configures `RedisCacheManager` properly, and files are in the right paths. The first run may pull the Redis image over the network. Tests produce no fixed business stdout. Do not fabricate Docker logs, random ports, or Redis hashes as observed output.

| Test | Evidence |
| --- | --- |
| `usesRedisCacheManagerAndStoresActualRedisKey` | Real Redis provider + Redis key exists |
| `cacheHitSkipsCallingSourceAgain` | Two reads, only one source call |
| `redisEntryHasConfiguredPositiveTtl` | Entry has a TTL within expected range |
| `evictOneKeyLeavesOtherProductCached` | Evicting key A leaves key B untouched |
| `evictAllClearsProductsButKeepsUnrelatedKey` | Region clear does not delete unrelated Redis keys |
| `directCacheClearRemovesUnderlyingRedisEntry` | Cache API clear removes the real Redis key |
| `exceptionsAreNotStoredAsCachedValues` | Exceptions are not cached as success values |

**If Docker is unavailable:** the test fails when Testcontainers cannot locate a runtime; do not switch to Simple cache and report the Redis integration test as PASS. If CI conditionally skips Docker tests, report executed/skipped explicitly rather than silently marking the provider verified.

## 14. Why place cleanup in both `@BeforeEach` and `@AfterEach`?

In the test class:

```java
@BeforeEach
void resetStateBeforeTest() {
    productsCache().clear();
    redis.delete(OTHER_KEY);
    source.reset();
}

@AfterEach
void clearOwnedStateAfterTest() {
    productsCache().clear();
    redis.delete(OTHER_KEY);
}
```

**BeforeEach:** eliminates cache hits left over from an earlier method; resetting the source counter afterward keeps assertions deterministic.

**AfterEach:** reduces leaking keys to subsequent tests or post-failure inspection code. JUnit generally still executes teardown callbacks even when a `@Test` throws an exception or assertion failure, unless the process is killed or the runtime crashes severely.

**Why not delete all Redis keys?** The test owns only the `products` region and a single sentinel key. Other resources are not owned by the test, so they are left alone. Although the lab's Redis container is private, good ownership habits matter when moving to shared environments.

### 14.1. Which test proves clearing actually works?

`directCacheClearRemovesUnderlyingRedisEntry` calls `productsCache().clear()` directly inside the test and asserts `redis.hasKey(...)` is false. It **verifies the behavior of clearing itself**, rather than merely assuming `@AfterEach` ran.

### 14.2. Why not rely on method execution order?

JUnit does not guarantee test methods run in declaration order unless explicitly configured. Each `@Test` seeds its own data, verifies its own behavior, and cleans up. Never design "test B expects test A to have cached a key." With a shared cache provider and static container, the class runs sequentially by default; enabling JUnit parallelism requires stronger isolation.

### 14.3. Risk when cleanup fails

If the Redis connection fails during `@AfterEach`, the test cannot claim cleanup succeeded. Do not write `catch (Exception ignored) {}` to hide errors. When the broker is a private container about to be destroyed, you may record the cleanup failure and rely on container teardown as fallback, while ensuring results reflect that per-test cleanup did not finish.

## 15. Cache regions and Redis namespaces

`RedisCacheManager` prefixes keys with `cacheName` by default:

```text
Spring cache "products", key "A"
        -> Redis key "products::A"

Spring cache "prices", key "A"
        -> Redis key "prices::A"
```

Thus, two cache regions do not collide even with the same business key. Calling `productsCache().clear()` should not delete `prices::A`.

**However, if two applications share a Redis instance with the same cache name and key prefix**, clearing a region can still wipe the other app's data. Prefixes only help when ownership (application/environment/test run) is properly partitioned.

### 15.1. When using a shared test Redis

A namespace design might look like:

```text
application = inventory
environment = ci
runId = 2026-11-08-build-123

Keys:
inventory:ci:2026-11-08-build-123:products::A
inventory:ci:2026-11-08-build-123:products::B
```

This illustrates a naming strategy, **not the lab's default key format**. Implementation requires configuring a custom `RedisCacheConfiguration` prefix or `CacheKeyPrefix`. Do not just change a String in tests and hope `RedisCacheManager` changes too.

When sharing Redis, clean up only under your owned prefix/namespace and configure TTL retention. Never scan and wildcard-delete across the entire DB without guaranteed ownership.

### 15.2. Redis logical databases are not complete security isolation

Redis supports numbered databases in standalone mode, but that is not a strong enough authorization or safety boundary for multi-tenant production. Redis Cluster commonly supports only DB 0. Use dedicated containers/instances or proper ACL/namespace/network isolation as required, rather than relying on `SELECT 7` to guarantee isolation from other applications.

## 16. Caffeine local cache: how to clean it up?

Caffeine is a great **in-memory** provider for testing local eviction and expiry. If production uses Caffeine, integration tests should assert `CaffeineCacheManager` rather than substituting Redis.

Gradle dependency:

```groovy
implementation 'com.github.ben-manes.caffeine:caffeine'
```

Sample configuration:

```properties
spring.cache.type=caffeine
spring.cache.cache-names=products
spring.cache.caffeine.spec=maximumSize=500,expireAfterWrite=60s
```

When the provider is Caffeine:

```java
Cache cache = cacheManager.getCache("products");
assertNotNull(cache);
cache.clear();
```

This invalidates the local region. There are no Redis keys or TTLs to inspect, and nothing is shared across JVMs. Using `RedisTemplate` to assert Redis keys when testing Caffeine is **out of scope** and not a valid provider test.

### 16.1. Caffeine vs. Simple provider

If you want to test **Caffeine size/TTL eviction**, do not substitute `ConcurrentMapCacheManager`; the Simple provider has no Caffeine policies. With Caffeine, you can unwrap the native cache (`getNativeCache()`) to inspect stats or estimated size, given compatible versions and config. Never treat `cache.get(...) != null` as proof of TTL policy without testing expiration.

### 16.2. When should you use a fake clock?

To test short TTLs without `Thread.sleep`, you can inject a fake Caffeine `Ticker` (if configurable) and advance virtual time, or use provider-specific test utilities. With real Redis, server time is external; replacing the app's `Clock` does not speed up Redis server expiration. That is why the lab asserts TTL metadata instead of waiting 60 seconds.

## 17. Redis value serialization: check what actually needs checking

Spring Data Redis `RedisCacheManager` stores values according to its serializer configuration. By default across common versions, `RedisCacheConfiguration.defaultCacheConfig()` uses `StringRedisSerializer` for keys and `JdkSerializationRedisSerializer` for values.

In the lab:

- The cached value is a Java `String`, which supports serialization.
- `StringRedisTemplate.hasKey(...)`/`getExpire(...)` only read key metadata.
- **Do not** call `StringRedisTemplate.opsForValue().get("products::A")` expecting `"A#load-1"`: the bytes may be Java serialized data rather than UTF-8 plain text.
- `productsCache().get("A").get()` uses the configured `Cache` implementation and serializer to deserialize.
- If switching to a JSON serializer, update the test configuration and verify schema/type metadata.

### 17.1. Returning DTOs / custom records

A Java 17 record does not implement `Serializable` by default. With JDK serialization, storing a non-Serializable record fails on cache write. You have two options:

1. Declare `implements Serializable` on DTOs matching Java serialization policy (weighing security and compatibility).
2. Configure an appropriate JSON Redis serializer (such as a generic Jackson serializer with type safety/allowlists), manage schema evolution, and test round-trips.

Do not mix default JDK-serialized value bytes with UTF-8 reads via `StringRedisTemplate` and conclude "Redis cache is broken."

### 17.2. Schema evolution

If v1 of an app caches `ProductV1` and v2 changes its package, class, or `serialVersionUID`, deserializing old cache entries can fail. Plan versioned prefixes, TTLs, and rollout invalidation strategies. Simple map unit tests never catch serialization compatibility issues; real Redis tests can.

## 18. `@DirtiesContext`, Spring TestContext caching, and container lifecycle

Spring TestContext caches `ApplicationContext` instances to save startup time. If a class declares a static Redis `@Container`, the Testcontainers JUnit extension typically stops the container at the end of **that test class**, while the Spring context may stay cached for the next class.

Scenario:

```text
Test A:
    Spring context created
    LettuceConnectionFactory points to Redis A port
    Testcontainers starts Redis A
    methods pass
    JUnit stops Redis A after class

Test B:
    Spring reuses context cached from A
    connection still targets old Redis A port
    Redis B may be on another mapped port
    tests fail with connection refused/timeouts
```

The lab has **only one test class** to avoid cross-class context reuse issues. For larger integration suites:

- Use a Spring-managed container bean tied to the context lifecycle when supported by the framework version.
- Or use a singleton container pattern whose lifecycle spans all contexts.
- Or isolate contexts per class and accept the startup overhead.
- Never assume `@DirtiesContext` clears Redis keys.
- Never share a static container and stop it before cached beans finish using it.

### 18.1. `@DirtiesContext` does not replace `cache.clear()`

`@DirtiesContext` only marks the Spring context "dirty" so Spring rebuilds it; it is not Redis `FLUSHDB`. If Redis outlives the JVM or context, old data remains. When the goal is test isolation, use the Cache API or provider namespace cleanup.

### 18.2. `@Transactional` does not roll back Redis

A Spring test-managed database transaction can roll back JPA writes, but Redis cache writes do not automatically participate in the SQL transaction. If the app writes to the cache before the DB commits and the test rolls back, the cache retains data absent from the DB.

Do not try to solve this with `@DirtiesContext`; use transaction-aware cache designs, post-commit invalidation, or explicit resource cleanup. When DB/cache consistency matters critically, write integration tests with both a real DB and real Redis.

## 19. `@CacheEvict` and database transactions: stale-cache races

Suppose a service:

1. Updates a price row inside a DB transaction.
2. Deletes the Redis cache entry right before commit.
3. Another thread reads the stale DB value and repopulates the cache.
4. The transaction commits the new price.
5. The cache serves the stale price until TTL expires.

This is a **stale repopulation race**; sequential unit tests rarely catch it.

Mitigations depend on requirements:

- Evict after the transaction commits successfully (transaction synchronization / domain events).
- Use transaction-aware cache manager decorators where appropriate, understanding their semantic limits.
- Use reasonable TTLs and versioned keys / explicit version checks.
- Evaluate distributed locks or cache-aside update protocols with their trade-offs.
- Test concurrency with barriers/latches, **not** arbitrary sleeps.
- When strong consistency is required, consider avoiding caching on sensitive paths.

**Note:** Redis does not participate by default in ACID SQL transactions. `@Transactional` alone cannot guarantee atomic updates between an RDBMS and Redis.

## 20. TTL and "cache disappeared" are not the same as eviction

Redis TTL returns:

- Non-negative seconds: remaining time to live.
- `-1`: key exists with no expiration.
- `-2`: key does not exist.

An eviction test must prove the key disappears **immediately after cache clear/evict**. A TTL test must prove the key was created with the right expiration. Waiting for TTL to remove a key does not prove `@CacheEvict` works.

### 20.1. Do not assert exact TTL values

`assertEquals(60, ttl)` can fail when one second passes right after the cache PUT. Use a sensible range instead.

### 20.2. Watch out during parallel tests

If another test clears the same prefix while you measure TTL, `getExpire` can return `-2` even when your code is correct. That is an isolation bug, not a TTL bug.

### 20.3. Reloading after TTL

To verify expiry-driven reloads without waiting 60 seconds, use a cache region with a very short TTL in a dedicated test, or virtual time when supported by the provider. Real Redis server expiration relies on the server's wall clock; avoid overly tight timing assertions. When a contract requires verifying exact TTL behavior, put it in a separate integration test with sensible time bounds.

## 21. Cache stampedes and `sync=true`

If two threads miss the same key simultaneously, both can call the expensive source before either populates the cache: a **cache stampede**. `@Cacheable(sync=true)` asks the provider to perform synchronized loading semantics where supported; not every provider or distributed topology guarantees a cluster-wide lock.

Never claim that "one source call across two sequential reads" proves single-flight protection under 100 concurrent requests.

Concurrency tests must:

- Dispatch multiple concurrent calls for the same key.
- Use coordination barriers instead of fixed timing sleeps.
- Assert the real policy (maximum backend calls, eventual equality, no data corruption).
- Verify that the chosen provider version supports synchronous caching.
- Clarify desired semantics: local single-flight vs. distributed lock.
- Test timeouts, failures, and lock release.

This lab focuses on deterministic sequential cache semantics and does not claim to test stampede protection.

## 22. Negative scenarios and provider failures

### 22.1. Backend throws an exception

In the lab, `ProductSource.load("FAIL")` always throws `IllegalStateException`. Two calls both hit the source, incrementing the counter to 2; no Redis key exists for `FAIL`. This proves exceptions are not cached as successful values.

### 22.2. Cache down

If Redis stops while `@Cacheable` calls the provider, the application may fail the operation by default rather than safely falling back. A custom `CacheErrorHandler` can swallow cache exceptions and fall back to the source; that is a **business resilience policy that must be tested**.

Never "fix" a provider integration test by swallowing all Redis errors and claiming caching works. When verifying real Redis, network and serialization errors must surface.

### 22.3. Null caching

`spring.cache.redis.cache-null-values=false` disables caching null values. When testing negative caching/missing products, decide whether 404/not-found results should be cached, for how long, and how to handle stale negative entries after a product is created.

Do not assume `null` is cached identically across ConcurrentMap, Caffeine, and Redis; defaults and configs differ.

### 22.4. Data races

Default `RedisCacheWriter` may use non-locking operations. `clear`, `putIfAbsent`, and multi-command sequences are not automatically atomic in every scenario. Seeing a Redis key exist after one test PUT does not prove distributed consistency under concurrent load.

## 23. Why not run Redis `FLUSHALL` in `@BeforeEach`?

A dangerous anti-pattern:

```java
// DO NOT DO THIS on shared Redis:
redis.getConnectionFactory()
        .getConnection()
        .serverCommands()
        .flushAll();
```

Beyond raw connection API/lifecycle risks, `FLUSHALL` **wipes every logical DB on the Redis server**. If a test accidentally points at a production Redis connection, the outcome is data loss, not mere flakiness.

Use instead:

```java
Cache products = cacheManager.getCache("products");
assertNotNull(products);
products.clear();
```

In shared environments, even clearing a region can disrupt other tests sharing a prefix. Stronger approaches are **test-only isolated containers** or per-run prefixes, cleaning up only test-owned keys.

### 23.1. Redis `SCAN` vs. `KEYS`

Spring Data Redis's cache writer can use `KEYS` to locate a cache prefix during `clear()`. On large keyspaces, `KEYS` can introduce significant latency or blocking. Custom configurations can switch to `BatchStrategies.scan(...)` with Lettuce, though cluster/driver compatibility must be evaluated. For a private lab with 1–3 keys, default clearing is simple enough.

Do not pick `SCAN` and assume scan + delete is an atomic transaction; concurrent inserts can still race. In shared production caches, namespace ownership and targeted invalidation strategies matter more than just swapping commands.

## 24. Testing across multiple cache providers

If an app supports both Redis and Caffeine, build a test matrix:

```text
Suite A: spring.cache.type=caffeine
         -> assert CaffeineCacheManager
         -> local cache behavior
         -> memory eviction/expiry policy

Suite B: spring.cache.type=redis
         -> assert RedisCacheManager
         -> Redis Testcontainers
         -> key/TTL/serialization/evict assertions

Suite C: spring.cache.type=none
         -> verify business behavior when cache disabled
         -> expect source invocation every time
```

Do not run the `"two reads source.calls() == 1"` assertion under `type=none` and call it a product bug: that is the exact semantics of `NoOpCacheManager`. Test expectations must **match the active provider contract**.

### 24.1. Caffeine tests need native statistics when metrics are a goal

If hit/miss metrics are required, Caffeine offers `recordStats()` and stats APIs. `RedisCacheManager` can expose statistics depending on version and config, with different semantics. The `CacheManager` abstraction does not guarantee uniform stats or eviction policies across providers.

### 24.2. Different regions and different keys

Testing the `products` region does not prove `prices`, `sessions`, or `users` are cached properly. Each region can have its own TTL, serializer, and key policy, so choose representative tests according to business criticality.

## 25. CI/CD: at what levels should tests isolate caches?

### 25.1. Redis-per-test-class

As in this lab: one static `GenericContainer` per class. Pros: clear state ownership, never touches shared Redis; cost: Docker startup time.

### 25.2. Redis-per-suite

A Redis container can be shared across multiple test classes for speed, provided Spring context lifecycles, key prefixes, parallel execution, and cleanup are carefully designed. If a cached context points to a stopped container, later tests fail.

### 25.3. Redis-per-CI-job

One Redis service container per CI job; test classes use run-ID prefixes and clear only their own prefixes/regions. When the job ends, the container is destroyed. Avoid sharing across concurrent CI jobs.

### 25.4. Shared staging Redis

Use only with test-specific environments/credentials, explicit namespace ownership, and ACLs. Never run admin flushes or wildcard deletes. Dedicated namespaces or instances are far safer.

### 25.5. Parallel JUnit tests

Inside a class whose `@BeforeEach`/`@AfterEach` calls `productsCache().clear()`, parallel method execution lets Test A's teardown delete Test B's keys, and source counters get reset concurrently. **The lab must run sequentially by default.** If a repository enables global parallelism, annotate such classes with `@Execution(ExecutionMode.SAME_THREAD)` (with JUnit imports) or use separate providers/namespaces per method.

Never try to solve races by increasing sleeps or timeouts; fix isolation at the ownership level.

## 26. Pitfalls with keys, serialization, and prefixes

### 26.1. Mismatched key generators

`@Cacheable(key="#p0")` and `@CacheEvict(key="#p0")` must receive identical argument/key representations. If the eviction method uses the wrong SpEL expression, the key stays behind and tests see stale data.

A custom `KeyGenerator` for composite keys like `(tenantId, sku)` needs tests proving two tenants with the same SKU do not collide. Never use only SKU as the cache key in a multi-tenant application when data varies by tenant.

### 26.2. Do not disable key prefixes lightly

Spring Data Redis prefixes by `cacheName` by default to prevent collisions. `disableKeyPrefix()` can cause regions sharing a key to overwrite each other and one region's clear to wipe another region's keys. If using custom prefixes, establish a stable `app/env/version` scheme and assert raw Redis keys in tests.

### 26.3. Changing value serializers

With JDK serialization, classes must remain compatible. With JSON serializers, enforce trusted type mappings/allowlists and schema evolution, avoiding unsafe deserialization of arbitrary types. A direct `StringRedisTemplate` GET is inappropriate for asserting plain-text values when the cache writes binary serialized bytes.

### 26.4. Null values

Null-caching behavior must be explicit. For missing products, caching a 404 for too long can return false negatives after the product is created. Negative caching tests must reflect concrete business contracts rather than just checking `"null returned"`.

## 27. Database + cache invalidation patterns

| Pattern | Source of truth | Cache update | Risk |
| --- | --- | --- | --- |
| Cache-aside read | DB load on miss | Put result | Stale when DB changes |
| Write-through | Update source + cache | Put new value | Needs consistency coordination |
| Write-around | Update DB | Evict | Stale repopulation window |
| Read-through | Provider loader | Load/cache | Loader exception/transaction semantics |
| TTL-only | Independent DB writes | Expire over time | Stale data until TTL expires |
| Event invalidation | DB update + event | Listener evicts | Delivery delay, duplicates, out-of-order events |

This lab demonstrates **cache-aside reads + explicit eviction** via Spring Cache abstraction, not a distributed transaction between SQL and Redis. When testing with a database:

1. Seed the DB and start with a clean cache.
2. Perform the first read and verify the provider key.
3. Update the row in a DB transaction and commit per contract.
4. Trigger eviction or refresh.
5. Read again and assert the new value.
6. Run concurrent scenarios to catch stale repopulation.
7. Clean up both the DB and Redis rather than relying solely on transaction rollback.

## 28. Practice exercises

### Exercise 1 — Remove `@EnableCaching`

Temporarily remove `@EnableCaching` from the main app. `cacheHitSkipsCallingSourceAgain` must fail because `source.calls()` rises to 2. Restore it. This proves the test actually detects a non-working proxy.

### Exercise 2 — Switch cache provider to `none`

In a sandbox, change `spring.cache.type=redis` to `none`. Provider type and Redis key presence assertions must fail, while pure business behavior tests may still run. Distinguish which failures are expected for each test goal.

### Exercise 3 — Test Caffeine separately

Add the Caffeine dependency and configure `spring.cache.type=caffeine` in a separate test suite. Assert `CaffeineCacheManager` and local cache behavior; do not use Redis key assertions to measure a local cache.

### Exercise 4 — Remove `@BeforeEach` clear

Temporarily remove the pre-test clear while keeping overlapping test keys and run the suite repeatedly against a shared Redis sandbox. Observe stale values and counter mismatches. Restore per-test cleanup and isolate providers/namespaces.

### Exercise 5 — Remove `@AfterEach` clear

Remove `@AfterEach` cleanup on a scratch branch and inspect leftover keys after the test method finishes. Explain why `@BeforeEach` remains essential when a prior run crashes, and why teardown failures must never be treated as success.

### Exercise 6 — Key-level eviction

Run `evictOneKeyLeavesOtherProductCached`. Change `invalidate`'s SpEL key to a different key and confirm the test fails. Restore it.

### Exercise 7 — `allEntries` and the sentinel

Run `evictAllClearsProductsButKeepsUnrelatedKey`. Replacing `@CacheEvict(allEntries=true)` with raw `FLUSHDB` (only inside a private Redis sandbox) deletes the sentinel. Explain the danger on shared Redis. Never run destructive commands in shared environments.

### Exercise 8 — Check TTL within bounds

Run `redisEntryHasConfiguredPositiveTtl`, change the TTL config to `2s` in an isolated test setup, and adjust the expected range. Avoid using `Thread.sleep(2000)` as the primary oracle.

### Exercise 9 — Serialization

Change the cached return type to a non-`Serializable` custom record and observe the Redis serializer error. Then configure an appropriate serializer and test round-trip serialization. Do not assume `StringRedisTemplate.opsForValue().get` decodes JDK serialized bytes.

### Exercise 10 — `@DirtiesContext` does not clear Redis

Create two Spring contexts against the same private Redis in a controlled suite. Context A caches a key; close Context A; Context B connects to the same Redis and verifies the key still exists. Never confuse context recreation with Redis cleanup.

### Exercise 11 — Multi-instance caching

Run two Spring contexts or two application instances pointing to the same Redis Testcontainers instance and shared key namespace. Instance A puts, Instance B hits; then A evicts and B misses. That is real evidence of a distributed shared cache, unlike a single-JVM test.

### Exercise 12 — Parallel races

Enable parallel JUnit execution with a shared region and source counter; observe one method's `@AfterEach` deleting another method's key. Fix it with per-method cache namespaces/providers or by disabling parallelism on the class.

### Exercise 13 — Failure / circuit breaker

Stop Redis in an isolated sandbox test with safe cleanup. Observe the cache operation failure. Design an optional `CacheErrorHandler` fallback per business policy and assert provider failures are surfaced clearly rather than silently ignored.

### Exercise 14 — Transaction boundaries

Combine PostgreSQL Testcontainers, Redis, and a `@Transactional` update service. Simulate stale repopulation between the DB write and Redis eviction using latches/barriers. Verify an after-commit invalidation strategy.

### Exercise 15 — Tenant-scoped key prefixes

The same SKU `"A"` for tenants X and Y must produce two distinct keys and two distinct cached values without leaking data across tenants. Experiment with composite keys and custom prefixes; assert raw Redis keys.

### Exercise 16 — Provider upgrades

Update the Redis image digest/version and Spring Data Redis/Jedis/Lettuce versions on a reviewed branch. Run the full integration suite and watch for TTL, serialization, or key-format changes. Never rely on a `latest` tag for a reproducible test environment.

## 29. QA pre-merge checklist

- [ ] Knows which `CacheManager` tests use; does not merely assert the bean is non-null.
- [ ] `@EnableCaching` is enabled; no proxy bypass or self-invocation issues.
- [ ] For Redis providers, tests run against a real Redis server/container, not just Mockito fakes.
- [ ] `spring.cache.type=redis` is set in Redis integration tests.
- [ ] `@ServiceConnection(name="redis")` or connection properties point to the right container/host port.
- [ ] Spring `CacheManager` is `RedisCacheManager`, not Simple, Caffeine, or NoOp.
- [ ] Tests verify actual Redis keys via a provider client.
- [ ] Tests check cache hit/miss and source call counts, not just comparing two Strings.
- [ ] Cache TTL is verified in Redis without fixed sleeps.
- [ ] Cache value serializer is understood; JDK value bytes are not read as UTF-8.
- [ ] `@BeforeEach` clears the proper region and resets fixture/source state.
- [ ] `@AfterEach` cleans up owned regions/keys even when tests throw normally.
- [ ] Does not depend on test method order or shared cached fixtures.
- [ ] `@CacheEvict(key=...)` removes only the intended key.
- [ ] `@CacheEvict(allEntries=true)` leaves unrelated Redis keys intact.
- [ ] Direct `Cache.clear()` test proves the underlying key disappears.
- [ ] Negative exceptions are not cached as success values.
- [ ] Never uses `FLUSHALL`/`FLUSHDB` on shared caches.
- [ ] On shared providers, namespaces/prefixes clearly reflect run/tenant/app ownership.
- [ ] Clearing large Redis caches uses `KEYS`/`SCAN` carefully and is not called unconditionally on hot paths.
- [ ] Does not treat `@DirtiesContext` as Redis cleanup.
- [ ] Does not treat `@Transactional` database rollback as Redis rollback.
- [ ] Spring TestContext cache and Testcontainers lifecycles are aligned.
- [ ] Parallel test classes do not delete each other's keys or source state.
- [ ] Caffeine/local vs. Redis/distributed tests assert against their respective providers.
- [ ] Security: tests hold no production credentials and never point to shared/production Redis.
- [ ] Does not claim multi-instance/HA/TLS/cluster behavior from a single `RedisContainer` alone.
- [ ] Gradle/JUnit executed/passed/failed/skipped counts are recorded from real reports when run.
- [ ] Image and dependency versions are managed so `latest` tags cannot unexpectedly alter test environments.

## 30. Decision tree

```text
Need to test caching?
       |
       +-- Only business logic / cache disabled?
       |      -> Unit/mock or spring.cache.type=none.
       |
       +-- Cache annotation/proxy semantics?
       |      -> Spring context + real CacheManager.
       |
       +-- Local Caffeine expiry/size?
       |      -> CaffeineCacheManager + native policy tests.
       |
       +-- Real Redis provider?
       |      -> Redis Testcontainers
       |         + spring.cache.type=redis
       |         + RedisCacheManager type assertion
       |         + Redis raw key/TTL verification.
       |
       +-- Test isolation?
       |      -> BeforeEach/AfterEach scoped cache clear
       |         + unique key/namespace/provider
       |         + container cleanup per test group.
       |
       +-- Multi-instance consistency?
       |      -> Two app contexts/instances sharing Redis
       |         + concurrent/invalidation tests.
       |
       +-- Managed Redis TLS/ACL/cluster/HA?
              -> Provider-specific staging/deployment tests.
```

**Conclusion:** Clearing caches reliably between tests requires understanding the **state scope** of the `CacheManager`/provider, not merely resetting a Java mock or Spring context. Verifying a real cache provider requires multiple independent pieces of evidence: Spring's `RedisCacheManager`, keys/TTL inside Redis, cache hit/miss via source call counts, and eviction reflected in storage. For safe integration testing, prefer **isolated Redis Testcontainers, explicit key ownership, and scoped `@BeforeEach`/`@AfterEach` cleanup**, and never run `FLUSHALL` to clean a shared Redis instance.

## 31. Official references

- Spring Boot 3.3 — Caching and supported cache providers: https://docs.spring.io/spring-boot/3.3/reference/io/caching.html
- Spring Boot 3.3 — Testcontainers, Redis GenericContainer, and `@ServiceConnection(name="redis")`: https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html
- Spring Framework — Cache annotations (`@Cacheable`, `@CachePut`, `@CacheEvict`) and proxy caveats: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Cache abstraction and `CacheManager`/`Cache` APIs: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Data Redis — Redis Cache/TTL/prefix/serializer: https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html
- Spring Data Redis — `RedisTemplate`/`StringRedisTemplate`: https://docs.spring.io/spring-data/redis/reference/redis/template.html
- Spring Data Redis — `RedisCacheManager` API: https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/cache/RedisCacheManager.html
- Testcontainers Java — JUnit Jupiter extension: https://java.testcontainers.org/test_framework_integration/junit_5/
- Testcontainers Java — `GenericContainer` and network ports: https://java.testcontainers.org/features/creating_container/
- Redis — `EXPIRE`/`TTL` commands: https://redis.io/docs/latest/commands/ttl/
- Redis — `FLUSHDB` (destructive): https://redis.io/docs/latest/commands/flushdb/
- Redis — `FLUSHALL` (destructive): https://redis.io/docs/latest/commands/flushall/
- Spring Framework — Spring TestContext cache and `@DirtiesContext`: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
- JUnit Jupiter — Lifecycle/parallel execution: https://docs.junit.org/current/user-guide/