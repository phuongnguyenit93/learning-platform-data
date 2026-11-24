# TTL, TTI, and Eviction Policies Belong to Cache Store Configuration

> **Context:** Spring Framework Cache — **Data and Lifecycle** section. This lesson explains why `@Cacheable` does not itself dictate time-to-live, time-to-idle, or cache-entry eviction strategies; those policies must be configured on the actual **cache provider** or cache implementation. The focus is on distinguishing **TTL**, **TTI**, **size-based eviction**, managing lifecycle, and applying them accurately on Caffeine and Redis.

## 1. Learning objectives

After this lesson, you will be able to:

1. Distinguish **TTL (Time To Live)**, **TTI (Time To Idle)**, capacity-based eviction, and business-driven invalidation.
2. Explain the responsibilities of the Spring Cache abstraction versus those of the cache provider.
3. Choose `expireAfterWrite`, `expireAfterAccess`, or `maximumSize` on Caffeine, and suitable TTL/TTI settings on Redis.
4. Understand why the default `ConcurrentMapCacheManager` does not automatically expire cache entries over time.
5. Write a Java 17 example using a **fake clock** to deterministically verify exact hit/miss timing without `Thread.sleep()`.
6. Design tests for expiration, eviction, fresh data after updates, multi-instance setups, and performance.
7. Avoid common misconceptions: `@Cacheable` has no standard TTL parameter, TTL is not equal to TTI, and logical expiration time is not the instant physical memory is reclaimed.

## 2. What does Spring Cache decide, and what does the provider decide?

A Spring application uses the annotation:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public Product findProduct(String productId) {
    return repository.find(productId);
}
```

This is an **illustrative code snippet** for a bean with a repository and a `Product` class; it is not a standalone Java program.

`@Cacheable` specifies: check the cache entry for the key; on a hit, return the result without executing the method body; on a miss, execute the method and store the result according to policy. Other parts of Spring Cache include `@CachePut` to update an entry and `@CacheEvict` to remove an entry.

However, `@Cacheable` **does not define a standard TTL/TTI/size-eviction policy**. These capabilities vary widely across in-JVM maps, Caffeine, Redis, JCache, and other providers.

```text
Client
  |
  v
Spring proxy / cache interceptor
  |
  +--> Select cache by cacheNames / CacheResolver
  +--> Generate key
  +--> Cache.get(key) --> HIT? --> return value
  |                       |
  |                      MISS
  |                       |
  +--> execute method, Cache.put(key, value)
                            |
                            v
                    Provider / Cache store
                    |                 |
                    |                 +--> TTL / TTI (if supported)
                    +--> maximumSize / eviction
                    +--> storage, serialization, expiry
```

Spring Cache defines the operation contract; **the provider manages the stored data, when an entry becomes invalid, memory consumption, and eviction mechanics**.

The Spring Framework documentation directly answers “How can I set the TTL/TTI/Eviction policy?” by stating that such features must be configured **directly through the cache provider**. Therefore, there is no standard `@Cacheable(ttl = 60)` recipe that works uniformly across all cache managers.

## 3. TTL — Time To Live: how long does an entry live after being written?

In common usage, TTL defines how long a cache entry remains valid starting from when it was **created or written/updated**. On Caffeine, the corresponding policy is typically `expireAfterWrite`.

Suppose `ttl = 5 seconds`, measured from the most recent write:

| Timestamp | Event | Result of accessing key A |
| --- | --- | --- |
| `t = 0s` | Miss, compute A and write to cache | Entry A is created |
| `t = 3s` | Read A | Hit, yet **does not extend** lifetime under `expireAfterWrite` |
| `t = 4s` | Read A | Hit, expiration time is still measured from `t = 0` |
| `t = 6s` | Read A | Miss because more than 5 seconds elapsed since write |
| `t = 6s` | Compute fresh A, write again | Starts a new TTL window |

This example assumes no other eviction or invalidation occurred and the loader succeeded.

**Important:** the label “TTL” does not by itself dictate how a provider computes the start timestamp. Some products treat TTL as expiration after write; some set a TTL per key on each write; others support per-entry variable policies. Always check the specific API/provider. In this lesson, when referring to TTL in Caffeine we mean `expireAfterWrite`; in Redis, TTL is attached to the key and write operations can reset the deadline.

TTL is useful when data is allowed to be stale for a **bounded maximum period from load time**, even if read frequently.

## 4. TTI — Time To Idle: expiring when unaccessed for too long

TTI specifies the maximum idle duration. Caffeine provides `expireAfterAccess`, which typically refreshes the “most recent access timestamp” when an item is **read or written** through the cache.

Suppose `tti = 5 seconds`, using the same key A:

| Timestamp | Event | Result |
| --- | --- | --- |
| `t = 0s` | Miss, create A | Starts the idle timer |
| `t = 4s` | Read A | Hit, refreshes access timestamp |
| `t = 8s` | Read A | Hit, only 4 seconds since the previous access |
| `t = 14s` | Read A | Miss, 6 seconds without access |
| `t = 14s` | Compute fresh A | Starts a new idle window |

The clearest difference: if a key is accessed continuously at intervals shorter than TTI, the entry can stay alive far longer than the configured duration, until removed by another policy.

### Can TTL and TTI coexist?

On Caffeine, you can combine them:

```java
Caffeine.newBuilder()
    .expireAfterWrite(Duration.ofMinutes(10))
    .expireAfterAccess(Duration.ofMinutes(2))
    .maximumSize(10_000);
```

This is an **illustrative builder snippet**, not a complete program. The intent is that a cache item expires if **either** expiration condition occurs: living too long since write, or sitting idle too long. Setting both does not mean TTI “extends” write-based expiration: each mechanism tracks its own timestamp.

Other providers may not support both simultaneously or may interpret them differently. Never assume every cache `GET` refreshes idle time.

## 5. Eviction — removal due to capacity or storage policy

**Expiration** invalidates an entry when a time-based condition is met. **Eviction** usually means removing an entry to manage capacity/resources or according to a replacement algorithm.

Example with Caffeine:

```java
Caffeine.newBuilder()
    .maximumSize(500)
    .expireAfterWrite(Duration.ofMinutes(10));
```

- `maximumSize(500)` sets a **capacity threshold** (maximum entry count per the implementation's policy). The provider may evict entries before their TTL expires.
- `expireAfterWrite(10 minutes)` is **time-based expiration**.
- Caffeine uses an eviction candidate selection policy based on access characteristics; **do not claim it is pure FIFO or LRU**.
- The exact impact of size eviction also depends on access patterns, weighted-size configuration, and when the provider runs maintenance.

**Conclusion:** an entry can miss before its TTL expires because it was evicted by size; and an entry can miss while plenty of capacity remains because its TTL expired. The two causes are not mutually exclusive.

### Expiration, eviction, and invalidation

| Term | Reason | Example |
| --- | --- | --- |
| **Expiration** | No longer valid due to elapsed time | 10-minute TTL, 2-minute TTI |
| **Capacity eviction** | Memory/capacity limit or replacement policy | Cache reaches `maximumSize` |
| **Explicit invalidation** | Business logic requires discarding stale data | `@CacheEvict(key = ...)` after an update |
| **Clear all** | Intentionally clearing an entire cache region | `@CacheEvict(allEntries = true)` |

With Spring, `@CacheEvict` enables **explicit removal** when business data changes. That annotation does not establish an automatic timer; TTL/TTI must be configured on the provider.

## 6. Configuring Caffeine in Spring Boot

If the application uses Spring Boot auto-configuration with the cache and Caffeine dependencies, you can set:

```properties
spring.cache.type=caffeine
spring.cache.cache-names=products,prices
spring.cache.caffeine.spec=maximumSize=500,expireAfterWrite=600s
```

This configuration sets a **500-entry limit and 600 seconds after write** for caches auto-configured by the manager, following Caffeine specification syntax. If you want **TTI** instead of write-based TTL:

```properties
spring.cache.type=caffeine
spring.cache.cache-names=products,prices
spring.cache.caffeine.spec=maximumSize=500,expireAfterAccess=600s
```

These are **two mutually exclusive alternatives**, not two `spring.cache.caffeine.spec` lines that should appear together in one file. You can configure both policies inside **a single** Caffeine spec if business requirements need both.

### Common Maven dependencies

In a Spring Boot project with a compatible parent/BOM:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-cache</artifactId>
    </dependency>
    <dependency>
        <groupId>com.github.ben-manes.caffeine</groupId>
        <artifactId>caffeine</artifactId>
    </dependency>
</dependencies>
```

This is a **dependency snippet** for a Spring Boot project's `pom.xml`, not a standalone POM. The parent/BOM manages versions; for caching annotations to work, `@EnableCaching` is required.

### Example service

```java
@Service
public class ProductService {
    @Cacheable(cacheNames = "products", key = "#p0")
    public Product find(String id) {
        return repository.find(id);
    }
}
```

This snippet requires a repository, `Product`, and matching imports; it only illustrates the annotation. Calls through the Spring proxy can hit if the entry has not expired and has not been evicted.

**Configuration notes:**
- An auto-configured `spring.cache.caffeine.spec` generally applies the same policy across caches created by that manager. If each cache needs a different TTL/TTI, create individual caches via the native Caffeine API and register them rather than expecting distinct cache names to automatically get distinct policies.
- Boot only configures Caffeine via auto-configuration when conditions are met. If you already supply a custom `CacheManager` or `CacheResolver`, the properties may not take effect as expected.
- Verify that the actual `CacheManager` bean is `CaffeineCacheManager` (or a custom manager with Caffeine caches registered) before assuming the policy is active.
- Never use `Thread.sleep(600000)` to test expiration; use a **fake ticker** on Caffeine for fast, deterministic tests.

## 7. Caffeine in Java: `expireAfterWrite`, `expireAfterAccess`, and `maximumSize`

Caffeine supports builders:

```java
Caffeine.newBuilder()
    .maximumSize(500)
    .expireAfterWrite(Duration.ofSeconds(30));

Caffeine.newBuilder()
    .maximumSize(500)
    .expireAfterAccess(Duration.ofSeconds(30));
```

These are **two independent builders for illustration**, without `build()` and not yet wired into a Spring `CacheManager`.

Key distinctions:
- `expireAfterWrite` is based on entry creation or update time; read hits do not reset it.
- `expireAfterAccess` is based on cache-API access timestamps observed by Caffeine; read hits can extend it.
- `maximumSize` is capacity eviction, not TTL.
- Caffeine may perform maintenance/physical entry removal **lazily**, during access operations or maintenance cycles. An entry that is **logically expired** is not necessarily freed from memory at the exact nanosecond of expiration.
- `@Cacheable` still only asks for hit/miss; expiration policies are enforced by the underlying cache and observed by Spring through the adapter.

This is why tests should exercise access and assert **misses/hits/method execution counts**, rather than checking the exact moment an entry disappears from an internal map.

## 8. Redis: TTL lives on the key; TTI requires opt-in and `GETEX`

### 8.1. TTL in Spring Boot with Redis

When Spring Boot auto-configures a Redis `CacheManager`, example configuration:

```properties
spring.cache.type=redis
spring.cache.cache-names=products,prices
spring.cache.redis.time-to-live=10m
spring.cache.redis.cache-null-values=false
```

`spring.cache.redis.time-to-live=10m` sets a 10-minute TTL for caches managed by this configuration. A Redis server must be configured and reachable; a matching Redis dependency such as `spring-boot-starter-data-redis` is required alongside Spring Cache integration. This configuration does not spin up a Redis server itself.

When different TTLs are needed per cache name, you can build a `RedisCacheManager` and configure each cache with `RedisCacheConfiguration`:

```java
RedisCacheConfiguration base =
        RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofMinutes(10));

RedisCacheConfiguration products =
        base.entryTtl(Duration.ofMinutes(2));

RedisCacheConfiguration prices =
        base.entryTtl(Duration.ofMinutes(30));

// Illustrative configuration example; must be combined with a RedisCacheManager builder
// and a RedisConnectionFactory in the Spring context.
```

Distinguish per-entry TTL from access-based renewal: **a standard Redis `GET` command does not extend a key's TTL**. Reading a key frequently does not keep it alive automatically.

### 8.2. Redis does not have Caffeine-style native TTI

Spring Data Redis provides a simulated TTI mechanism in supported versions via:

```java
RedisCacheConfiguration config =
        RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofMinutes(5))
                .enableTimeToIdle();
```

This is a **`RedisCacheConfiguration` snippet**, not a standalone program. `enableTimeToIdle()` must be explicitly enabled together with a declared TTL. To achieve emulated TTI behavior, Spring Data Redis Cache issues **`GETEX`** instead of `GET` when reading through the cache API; `GETEX` can both read the value and reset the key's expiration.

Critical prerequisites:
1. **Redis server version 6.2.0 or higher** supporting `GETEX`. Enabling TTI against an older server causes command execution failures; Spring Data Redis cannot automatically polyfill this missing feature.
2. Use a Spring Data Redis version that provides the `enableTimeToIdle()` API (3.2 line onward); avoid copying the code above into overly old versions.
3. **Every access path must agree on renewing expiration.** A regular `RedisTemplate.opsForValue().get(key)` or repository query using `GET` does not reset TTL. Mixing multiple access paths on the same key can make you think a value was just “used” while it still expires on the old TTL clock.
4. Redis TTI under this mechanism **is an emulation built on top of TTL**; Redis does not maintain a separate server-side “idle timestamp” across arbitrary commands.
5. If external non-Spring clients also read the key, evaluate the entire access flow; a single provider cannot know about reads bypassing its API.

### Inspecting Redis TTL directly

In a development environment with Redis CLI, if you know the exact physical key (including cache name prefix, serializer, and key format), you can inspect:

```bash
redis-cli TTL 'products::P1'
redis-cli PTTL 'products::P1'
```

These commands are **illustrative** with the prefix/key `products::P1` matching the corresponding Redis cache defaults; the actual key can differ depending on serializer, prefix, or cache key generator.

- `TTL` returns remaining lifetime in seconds; `PTTL` in milliseconds.
- A return code of `-2` means the key does not exist; `-1` means the key exists with no expiration set.
- A `TTL` command used to **observe remaining time** does not itself refresh TTI.
- Never delete or modify production keys just to run experiments; use a separate test environment.

## 9. `ConcurrentMapCacheManager`: why basic examples never expire automatically

`ConcurrentMapCacheManager` uses an in-JVM-memory cache backed by a map structure. It is suitable for demos or basic cache hit/miss tests, yet **has no built-in TTL/TTI policies** like Caffeine.

Illustrative example:

```java
@Bean
CacheManager cacheManager() {
    return new ConcurrentMapCacheManager("products");
}
```

Merely placing `@Cacheable("products")` on a method does not make entries expire after 5, 10, or 60 minutes. Unless there is explicit eviction/clear, overwrite via put, context reload, or another factor, the entry can remain in the map.

Consequences:
- Tests assuming “wait a little while and it will miss” fail when the provider has no expiration.
- Entry counts and memory usage can grow if keys grow unbounded without capacity management.
- Switching from `ConcurrentMap` to Redis/Caffeine can change when misses happen, value serializability requirements, and concurrency behavior.
- Choose a provider matching lifecycle requirements rather than adding a non-existent annotation attribute like `@Cacheable(ttl = ...)`.

## 10. Runnable Java 17 example: verifying TTL and TTI with a fake clock

This experiment uses Spring Framework 6.2.x, Caffeine 3.1.x, and JUnit 5. Within a single Spring `ApplicationContext`, we create **two separate caches**:
- `byWrite`: expires **5 seconds after write**.
- `byAccess`: expires **5 seconds after the most recent access**.

Both caches share a fake `Ticker` object to control time. This makes verification fast and deterministic without **sleeping 5–15 seconds**.

### 10.1. File layout

```text
cache-lifecycle-demo/
├── pom.xml
└── src/
    ├── main/java/demo/cache/CacheLifecycleDemo.java
    └── test/java/demo/cache/CacheLifecycleDemoTest.java
```

### 10.2. Maven `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>cache-lifecycle-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context-support</artifactId>
            <version>6.2.16</version>
        </dependency>
        <dependency>
            <groupId>com.github.ben-manes.caffeine</groupId>
            <artifactId>caffeine</artifactId>
            <version>3.1.8</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.cache.CacheLifecycleDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context-support` brings in the `CaffeineCache` adapter and pulls in the needed Spring modules; the Caffeine dependency provides the native builder. JUnit is used for assertions. Specific versions are pinned for reproducibility; when integrating into a real Spring Boot project, **use the BOM/parent to manage compatibility** instead of specifying overlapping Spring versions manually.

### 10.3. Complete Java — `CacheLifecycleDemo.java`

```java
package demo.cache;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import com.github.benmanes.caffeine.cache.Caffeine;
import com.github.benmanes.caffeine.cache.Ticker;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCache;
import org.springframework.cache.support.SimpleCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class CacheLifecycleDemo {

    public static final class FakeTicker implements Ticker {
        private final AtomicLong nanos = new AtomicLong();

        @Override
        public long read() {
            return nanos.get();
        }

        public void advanceSeconds(long seconds) {
            nanos.addAndGet(TimeUnit.SECONDS.toNanos(seconds));
        }
    }

    public static class PriceService {
        private final AtomicInteger writeLoads = new AtomicInteger();
        private final AtomicInteger accessLoads = new AtomicInteger();

        @Cacheable(cacheNames = "byWrite", key = "#p0")
        public String byWrite(String sku) {
            return sku + "-w" + writeLoads.incrementAndGet();
        }

        @Cacheable(cacheNames = "byAccess", key = "#p0")
        public String byAccess(String sku) {
            return sku + "-a" + accessLoads.incrementAndGet();
        }

        public int writeLoadCount() {
            return writeLoads.get();
        }

        public int accessLoadCount() {
            return accessLoads.get();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {

        @Bean
        public FakeTicker ticker() {
            return new FakeTicker();
        }

        @Bean
        public CacheManager cacheManager(FakeTicker ticker) {
            var ttlNative = Caffeine.newBuilder()
                    .ticker(ticker)
                    .expireAfterWrite(Duration.ofSeconds(5))
                    .maximumSize(100)
                    .build();

            var ttiNative = Caffeine.newBuilder()
                    .ticker(ticker)
                    .expireAfterAccess(Duration.ofSeconds(5))
                    .maximumSize(100)
                    .build();

            var manager = new SimpleCacheManager();
            manager.setCaches(List.of(
                    new CaffeineCache("byWrite", ttlNative),
                    new CaffeineCache("byAccess", ttiNative)
            ));
            return manager;
        }

        @Bean
        public PriceService priceService() {
            return new PriceService();
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            var clock = context.getBean(FakeTicker.class);
            var service = context.getBean(PriceService.class);

            System.out.println("t0 write=" + service.byWrite("A"));
            System.out.println("t0 access=" + service.byAccess("A"));

            clock.advanceSeconds(4);
            System.out.println("t4 write=" + service.byWrite("A"));
            System.out.println("t4 access=" + service.byAccess("A"));

            clock.advanceSeconds(4);
            System.out.println("t8 write=" + service.byWrite("A"));
            System.out.println("t8 access=" + service.byAccess("A"));

            clock.advanceSeconds(6);
            System.out.println("t14 write=" + service.byWrite("A"));
            System.out.println("t14 access=" + service.byAccess("A"));

            System.out.println("writeLoads=" + service.writeLoadCount());
            System.out.println("accessLoads=" + service.accessLoadCount());
        }
    }
}
```

Explanation:
- `FakeTicker` is a test-controlled nanosecond clock source. It implements Caffeine's `Ticker` interface.
- The `byWrite` cache expires 5 seconds after the most recent load/write.
- The `byAccess` cache expires 5 seconds after the most recent access.
- `SimpleCacheManager` here **registers two `CaffeineCache` objects with distinct policies**. Do not confuse `SimpleCacheManager` with `ConcurrentMapCacheManager`; this manager simply groups supplied caches, while each underlying cache is actually Caffeine.
- Both `@Cacheable` methods are called on the Spring-managed bean; counters sit inside the method bodies to observe real misses.
- Reading a hit from a Caffeine cache can refresh the access timestamp, yet does not refresh the write timestamp.

### 10.4. Running the application and expected stdout

Requires JDK 17+, Maven, and access to download dependencies from Maven Central. In the `cache-lifecycle-demo` directory:

```bash
java -version
mvn -q compile exec:java
```

Lines **printed by the program itself** (ignoring Maven/Spring messages):

```text
t0 write=A-w1
t0 access=A-a1
t4 write=A-w1
t4 access=A-a1
t8 write=A-w2
t8 access=A-a1
t14 write=A-w3
t14 access=A-a2
writeLoads=3
accessLoads=2
```

Step-by-step comparison:

- **t0:** both caches are empty; both methods execute for the first time.
- **t4:** under 5 seconds since t0, so both hit. `byAccess` refreshes its idle timestamp at t4.
- **t8:** `byWrite` has lived 8 seconds since its t0 write, so it misses and loads a second time; `byAccess` was just read at t4, idle for only 4 seconds, so it still hits.
- **t14:** `byWrite` was written at t8, and 6 seconds have elapsed, so it misses and loads a third time. `byAccess` was last read at t8, also past 5 seconds, so it misses and loads a second time.
- **Method body execution counts:** 3 for write-based expiry, 2 for access-based expiry; not equal to client call counts (each method was called 4 times).

This example avoids `Thread.sleep()` and thus does not depend on OS scheduling. However, the result reflects the behavior of **the Caffeine provider, policies, and specific configuration in this example**; it does not prove all providers behave identically.

## 11. JUnit 5 test: deterministically verifying lifecycle

Create `src/test/java/demo/cache/CacheLifecycleDemoTest.java`:

```java
package demo.cache;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CacheLifecycleDemoTest {

    @Test
    void writeExpiryAndIdleExpiryBehaveDifferently() {
        try (var context = new AnnotationConfigApplicationContext(
                CacheLifecycleDemo.Config.class)) {

            var clock = context.getBean(CacheLifecycleDemo.FakeTicker.class);
            var service = context.getBean(
                    CacheLifecycleDemo.PriceService.class);

            assertEquals("A-w1", service.byWrite("A"));
            assertEquals("A-a1", service.byAccess("A"));

            clock.advanceSeconds(4);
            assertEquals("A-w1", service.byWrite("A"));
            assertEquals("A-a1", service.byAccess("A"));

            clock.advanceSeconds(4);
            assertEquals("A-w2", service.byWrite("A"));
            assertEquals("A-a1", service.byAccess("A"));

            clock.advanceSeconds(6);
            assertEquals("A-w3", service.byWrite("A"));
            assertEquals("A-a2", service.byAccess("A"));

            assertEquals(3, service.writeLoadCount());
            assertEquals(2, service.accessLoadCount());
        }
    }
}
```

Run:

```bash
mvn -q test
```

If the test passes, Maven returns **exit code 0**. With `-q`, a “BUILD SUCCESS” line is not necessarily printed; the assertions themselves are the verification. Because the test constructs a fresh `ApplicationContext`, caches and counters start empty, independent of any prior `main` run.

When extending tests for size eviction, **never assert that key A is definitely evicted merely because another key was added**: candidate selection depends on the provider and access pattern. To test capacity policies, measure total entries or eviction likelihood under controlled workloads rather than hard-coding an incorrect eviction order.

## 12. Logical expiration differs from physical memory cleanup

A cache system can mark an entry invalid at t = 5 seconds without necessarily running a thread at that exact instant to physically delete it.

- Caffeine may perform maintenance during cache reads/writes; depending on scheduler configuration, cleanup can also be driven periodically.
- Redis deletes expired keys using both lazy checks on access and active server sampling; do not expect memory usage to drop at the exact millisecond a TTL expires.
- An expired entry **must not be returned as a valid cache hit** when the provider checks expiration, yet the data can temporarily remain in internal structures until the next maintenance pass.

Therefore, test **get/hit/miss** behavior rather than relying on wall-clock nanosecond precision or inspecting memory usage to decide whether an entry has expired.

## 13. What happens when source data is updated before the TTL ends?

Suppose a product price in the database changes from 100 to 200 at t = 1 second, while the cache TTL is 10 minutes. Without invalidation:

```text
t0: GET P1 -> MISS -> load 100 -> cache P1=100 (TTL 10 minutes)
t1: UPDATE DB P1=200
t2: GET P1 -> HIT -> still returns 100 (stale data)
t10m+: GET P1 -> MISS -> load 200 (if DB has committed and cache has expired)
```

**TTL only bounds the age of a cached entry; it does not mean the cache becomes fresh immediately when the source changes.** For data requiring fast updates, combine:
- `@CacheEvict` after write commands to remove the key and reload on the next query; or
- `@CachePut` when the write command returns the persisted canonical value and can put under the exact key; or
- proactive/event-based invalidation strategies aligned with transactions and multi-instance topologies.

Long TTLs reduce misses and source load while widening the staleness window; short TTLs refresh data sooner while increasing misses and processing cost. This is a **trade-off** measured against business requirements, with no single TTL ideal for every service.

### Transactions and cache delete/write ordering

Even `@CacheEvict`/`@CachePut` must be coordinated with commit timing. If the cache is evicted before the DB commits, another request can reload the old value; if the cache is updated yet the DB rolls back, the cache can hold an update that does not exist in the source. Check transaction advice ordering, after-commit invalidation, or compensating strategies as appropriate.

## 14. Multiple JVMs, local caches, and distributed caches

- **Caffeine local cache:** each application instance has its own cache, TTL/TTI clock, and entry lifecycle. Evicting on instance A does not automatically remove the entry on instance B.
- **Shared Redis cache:** multiple instances accessing keys in the same Redis share TTLs. Still, keys/serializers, namespaces, prefixes, and transactions must remain consistent.
- **TTI on Redis:** a request from instance A via `GETEX` can extend the TTL on a shared Redis key; a request using plain `GET` from instance B will not refresh that TTL. That is why every access path must follow a consistent policy.
- **Cache stampede:** multiple requests missing concurrently after expiration can load the source simultaneously. `@Cacheable(sync = true)` depends on the provider and does not automatically guarantee cross-instance coordination; dedicated design is required if system-wide single loading is needed.
- **Clock/TTL precision:** timing and execution belong to the provider. Never assume a single JVM's local clock governs the Redis server's TTL.

For critical data, even a distributed cache **does not replace the database as the source of truth**; ensure appropriate idempotency, transactions, versioning, or invalidation.

## 15. Common configuration pitfalls

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Cache never expires | Using `ConcurrentMapCacheManager` or no TTL configured | Inspect manager/provider type and expiration config |
| Entry expires even though it was just read | Using write-based TTL instead of TTI | Check `expireAfterWrite` vs `expireAfterAccess`; Redis `GET` vs `GETEX` |
| Cache misses before TTL arrives | Capacity eviction, manual eviction, mismatched key, or provider restart | Check size stats, keys, logs, and instance restarts |
| Stale values persist after DB update | Missing invalidation or cache updated under the wrong key | Compare read/write keys and transaction commit timing |
| Boot `spring.cache.caffeine.spec` has no effect | Custom `CacheManager` bean present or auto-config did not pick Caffeine | Log the active bean/provider and auto-config conditions |
| Redis throws command errors after enabling TTI | Server below Redis 6.2 or access path not using `GETEX` | Check Redis version, Spring Data Redis version, and read paths |
| Expiration tests pass sometimes and fail other times | Using `Thread.sleep()` and relying on OS scheduling | Inject a fake ticker or provider clock abstraction |
| Cache grows unusually large | TTL does not bound entry count, lazy maintenance, or unbounded key space | Configure `maximumSize`/memory budgets and metrics |
| Different instances observe different values | Per-process local caches or unsynchronized invalidation | Inspect topology and shared-cache strategy |
| `@Cacheable` keeps running the method repeatedly | Short TTL, changing keys, concurrent misses, self-invocation, or proxy issues | Count method-body executions and inspect keys/proxies |

**Note:** manually instantiating objects with `new` or calling `this.find(...)` inside the same bean can bypass the Spring proxy cache interceptor in default mode. When testing annotation-driven TTL/TTI, always invoke a Spring-managed bean through its actual proxy.

## 16. Policy selection checklist

1. **Freshness:** how stale can data be at most? Does the source change via batch jobs, events, or user actions?
2. **Time semantics:** do you need an age limit from write time (**TTL/write**) or to retain actively accessed entries (**TTI/access**)?
3. **Memory bounds:** do you need `maximumSize`, `maximumWeight`, or a memory quota alongside expiration?
4. **Provider:** do you need a local or distributed cache? Does your provider support native TTI, emulated TTI, or neither?
5. **Effective configuration:** confirm the active `CacheManager` bean, cache names, and applied policies rather than reading annotations alone.
6. **Read paths:** are multiple APIs reading the same key? On Redis in particular, TTI via `GETEX` differs from plain `GET`.
7. **Invalidation:** after source changes, do you evict/put affected entries instead of waiting solely for TTL?
8. **Null/negative caching:** how long should “not found” results be cached, and does the provider support it?
9. **Load:** could an overly short TTL trigger stampedes or overload the DB/API when many keys expire together?
10. **Observability:** monitor hit rate, miss rate, eviction count, source loads, p95/p99 latency, entry count, and heap/Redis memory.
11. **Testing:** do you test with a fake ticker/clock, invalidation after updates, and the real provider?
12. **Deployment:** could environment-specific configs be overridden by custom beans, profiles, or environment variables?

## 17. Practice exercises

**Exercise 1 — TTL.** Cache TTL is 5 seconds; written at t = 0, read at t = 2, t = 4, and t = 6. No updates, evictions, or reloads occur before t = 6. Does the read at t = 6 hit or miss?  
**Answer:** **Miss** under an `expireAfterWrite(5s)` policy because reads at t = 2 and t = 4 do not reset age since write.

**Exercise 2 — TTI.** Cache TTI is 5 seconds; written at t = 0, hit at t = 4, hit at t = 8, read at t = 14. Does the last call hit or miss?  
**Answer:** **Miss** because the idle gap from t = 8 to t = 14 is 6 seconds.

**Exercise 3 — Capacity.** A cache has `maximumSize(2)` and a 30-minute TTL. Three distinct keys are inserted. Why might a recently written key still miss?  
**Answer:** Because capacity eviction can remove an entry before it reaches its TTL. Never assume a specific key will be evicted without confirming the eviction algorithm and access pattern.

**Exercise 4 — Annotations.** Can you write `@Cacheable(cacheNames = "products", ttl = 60)` to get a 60-second TTL automatically across every provider?  
**Answer:** **No**; `ttl` is not a standard attribute on Spring's `@Cacheable`. It must be configured on the provider/cache manager.

**Exercise 5 — Redis TTI.** Why is using `RedisTemplate` to `GET` a key not guaranteed to extend Spring Data Redis's TTI?  
**Answer:** Because TTI emulation relies on `GETEX` to reset expiration, whereas a plain `GET` only reads.

**Exercise 6 — DB updates.** If TTL is 60 minutes and data changes right after the cache is written, can readers observe stale data?  
**Answer:** Yes, unless there is invalidation or a new value is put. TTL bounds age rather than synchronizing instantaneously with the source.

## Official references

- [Spring Framework — How can I set the TTL/TTI/Eviction policy/XXX feature?](https://docs.spring.io/spring-framework/reference/integration/cache/specific-config.html)
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework — Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Boot — Caching (Caffeine and Redis)](https://docs.spring.io/spring-boot/reference/io/caching.html)
- [Spring Data Redis — Redis Cache, TTL and TTI expiration](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html)
- [Caffeine — Eviction & Expiration Wiki](https://github.com/ben-manes/caffeine/wiki/Eviction)
- [Caffeine — Testing Wiki (Ticker)](https://github.com/ben-manes/caffeine/wiki/Testing)

**Key Takeaway:** Spring Cache manages **how caching is applied to method invocations**, not a unified expiration policy. **TTL, TTI, and capacity eviction must be configured on the provider**, and actual behavior must be verified via hits/misses, method execution counts, and source data checks. Setting the right lifetime alone is not enough: an effective and safe cache also requires capacity bounds, post-update invalidation, accurate topology awareness, and testing against the actual provider in use.