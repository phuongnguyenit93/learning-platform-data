# Why Spring Cache Annotations Do Not Declare a Standard TTL

## Lesson objectives

When first using Spring Cache, people often write `@Cacheable(cacheNames = "products")` and ask: **“How long is the result stored, and why isn't there a `ttl = 300` right on the annotation?”** This is not an overlooked attribute. Spring Cache deliberately acts as an **abstraction** to unify how an application invokes and consumes caches, while expiration policies belong to **the underlying cache storage technology**.

After this lesson, you will be able to:

- Explain accurately why `@Cacheable`, `@CachePut`, `@CacheEvict`, and `@CacheConfig` have no standard TTL attribute.
- Distinguish **TTL**, **TTI**, **expire-after-write**, **expire-after-access**, **refresh**, and **invalidation**.
- Identify which layer decides whether data expires: the annotation, `CacheManager`, the `Cache` object, or the native cache provider.
- Configure TTL via **Caffeine**, **Redis**, Spring Boot properties, or per-cache-name configuration.
- Run a **Java 17 + Spring Framework + Caffeine** program with a simulated clock to verify cache expiration deterministically without `Thread.sleep()`.
- Design lifecycle policies for different cache regions without confusing TTL with instant consistency requirements.

> **Upfront takeaway:** The `@Cacheable` annotation describes **which method can be cached and which cache name/key to use**. It does not describe a universal TTL contract because Spring Cache is not a cache engine. If a provider does not support time-based expiration (such as a plain `ConcurrentMapCache`), a universal TTL parameter would have no uniform way to execute.

## 1. What does the Spring Cache abstraction do and not do?

### 1.1. Typical `@Cacheable` flow

Suppose:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public ProductDto getProduct(long productId) {
    return repository.findDto(productId);
}
~~~

This is **illustrative code**; `ProductDto` and `repository` must be defined in a real project.

If the call passes through a Spring caching proxy (or configured AspectJ advice), the general flow is:

~~~text
Call getProduct(42)
          |
    Spring cache advice
          |
    select cache "products"
          |
       generate key 42
          |
       Cache.get(42)
          |
      +---+----------------+
      |                    |
    HIT                  MISS
      |                    |
return cached result  invoke getProduct(42)
skip method body           |
                      receive fresh result
                           |
                      Cache.put(42, result)
                           |
                      return fresh result
~~~

Spring needs to know **which cache**, **which key**, and **when to read/write/evict**. Whether an entry disappears after 5 minutes, after the last read, due to a memory limit, or never expires automatically is the responsibility of the chosen implementation.

### 1.2. Role of each component

| Component | Primary responsibility | Declares a generic TTL? |
| --- | --- | --- |
| `@Cacheable` | Lookup rules, cache hit/miss, cache selection, key, and conditions | **No** |
| `@CachePut` | Runs the method and writes the result into the cache | **No** |
| `@CacheEvict` | Requests deleting entries or clearing a cache region at a specified point | **No**; this is event-driven invalidation |
| `@CacheConfig` | Shares cache names, key generator, resolver, or manager for a class | **No** |
| `CacheManager` | Supplies `Cache` instances by name | Depends on implementation and configuration |
| `Cache` | `get`, `put`, `evict`, `clear`, and related operations | No universal per-entry TTL API |
| Native provider | Stores data and enforces expiration/eviction policies | **Usually here**, if supported by the provider |

Different Spring implementations can use Redis, Caffeine, JCache, Couchbase, Hazelcast, or `ConcurrentMapCache`. Some providers expire per entry, some expire on access, some only support expiration at region creation time, and some do not expire entries over time automatically.

### 1.3. Spring's official answer

The Spring Framework documentation, under **“How can I Set the TTL/TTI/Eviction policy/XXX feature?”**, explains that such policies are configured **directly via the cache provider**, because Spring Cache is purely an abstraction rather than a concrete cache implementation.

For example, JDK `ConcurrentHashMap` has no native TTL mechanism. If Spring forced every cache to understand the same `ttl` annotation attribute, applying it to `ConcurrentHashMap` would require building an auxiliary engine to track time and evict entries. Spring does not commit to adding such an engine for every provider.

Source: https://docs.spring.io/spring/reference/6.2/integration/cache/specific-config.html

## 2. Does having no standard TTL mean you cannot use TTL?

**No.** Spring Cache lacks a standard annotation attribute, yet providers can support TTL very well.

Examples of how it can be configured:

- **Caffeine:** `expireAfterWrite(Duration.ofMinutes(5))`, `expireAfterAccess(...)`, or variable expiration policies via Caffeine's API.
- **RedisCacheManager:** `RedisCacheConfiguration.entryTtl(Duration.ofMinutes(5))`, customizable per cache name; supporting versions of Spring Data Redis also provide TTL functions.
- **Spring Boot + Redis:** `spring.cache.redis.time-to-live=5m` when the Redis cache is auto-configured by Boot.
- **Spring Boot + Caffeine:** `spring.cache.caffeine.spec=maximumSize=1000,expireAfterWrite=300s` when the Caffeine manager is auto-configured by Boot.
- **ConcurrentMapCacheManager:** has no built-in TTL mechanism in its `ConcurrentHashMap`-backed caches; you must switch providers or build another lifecycle policy.

The examples above are **different configuration mechanisms**, not attributes you can copy onto `@Cacheable`.

Specifically, `@Cacheable(cacheNames = "products", ttl = 300)` is **invalid Java syntax** with the standard Spring Cache annotation. Your IDE and compiler will report that the `ttl` attribute does not exist.

## 3. Where do TTL, TTI, refresh, and eviction differ?

### 3.1. TTL: Time To Live

In caching, many places call it TTL, yet you must check **when the clock starts**. A common policy is `expireAfterWrite`:

- At `t = 0`, entry `products[42]` is written.
- Post-write TTL is 5 minutes.
- Reads at `t = 1`, `t = 2`, and `t = 4` minutes **do not extend** the expiration deadline.
- At or after the expiration mark per provider semantics, a read no longer sees a valid value; with `@Cacheable`, it can become a miss and re-invoke the source method.

~~~text
expire-after-write = 5 minutes

t=0         t=2           t=4           t=5+
 |-----------|-------------|--------------|
 PUT         GET hit       GET hit      expired -> MISS
                ^             ^
         does not reset TTL  does not reset TTL
~~~

A **rewrite/replace** of the entry can restart the deadline under an expire-after-write policy. However, **not every system calling something TTL behaves identically to expire-after-write**; check the specific backend documentation.

### 3.2. TTI: Time To Idle

TTI (time to idle) is how long an entry is allowed to sit **without access**. In Caffeine, `expireAfterAccess` applies based on elapsed time since the most recent read or write access.

~~~text
expire-after-access = 5 minutes

t=0         t=3            t=7            t=12+
 |-----------|--------------|---------------|
 PUT       GET hit        GET hit       may be expired
             |               |
       deadline slides to  deadline slides to
          t~8             t~12
~~~

The difference: **read hits can extend the lifetime**. This behavior differs from `expireAfterWrite`.

In Redis, idle expiration support may rely on specific commands such as `GETEX` or backend design; do not assume `GET` refreshes TTL by default. Spring Data Redis provides `enableTimeToIdle()` in supported versions, though it requires a compatible Redis server and consistent read paths.

### 3.3. Refresh is not expiration

`refreshAfterWrite` in Caffeine is a policy making an entry **eligible for refresh**, which is not equivalent to turning the entry into an immediate miss. With caches having loader/refresh semantics, the system can return the old value while the refresh runs. Actual refreshing and supplying new data depend on the cache/loader design.

Do not describe `refreshAfterWrite(5m)` as “delete the entry after 5 minutes,” because the two mechanisms behave differently, especially under heavy load.

### 3.4. Expiration is not explicit eviction

- **Expiration:** the backend decides an entry has expired based on a time policy.
- **Eviction:** can happen due to capacity, memory-management algorithms, or an explicit `@CacheEvict`/API call.
- **Invalidation:** source data changes or a business event renders an entry inaccurate, so the application actively deletes or refreshes the entry.

A long TTL does not keep data accurate if the database changed in the meantime. If the requirement is “once the name changes, the next read must see the new name,” use `@CacheEvict`/`@CachePut` or a consistent invalidation strategy, **not TTL alone**.

## 4. Why does Spring omit TTL from `@Cacheable`?

### 4.1. Capability differences across providers

`@Cacheable` is designed to work across many engines. A basic `ConcurrentMapCache` has no TTL, whereas Redis has key-level expiration and Caffeine offers write/access policies plus deep customization. A TTL attribute on a method has no clear execution path if the provider lacks support or models time differently.

Adding an option to the annotation that many backends cannot enforce would force Spring to choose between **silently ignoring it**, **throwing errors**, or **building an extra engine**; all three undermine the simplicity and consistency of the abstraction.

### 4.2. Policies typically belong to the cache region, not the method

Multiple methods can share the same region:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public ProductDto findById(long id) { /* ... */ }

@CachePut(cacheNames = "products", key = "#p0")
public ProductDto update(long id, ProductDto input) { /* ... */ }
~~~

These methods **share entries within a single cache name**. If `findById` declared a 10-minute TTL while `update` declared 15 seconds, which policy should apply when both write to the same key? Spring does not impose a universal resolution rule across all providers.

A manageable approach is **configuring policies per cache region**: for example, the `products` region has a 5-minute TTL, and both `@Cacheable` and `@CachePut` use that region. With providers supporting per-entry expiration, a custom policy can compute lifetimes from specific data.

### 4.3. Method-level TTL easily creates false expectations about consistency

Reads for inventory, balances, promotions, and configuration data have different freshness requirements. TTL is an **upper bound on data age**, not a guarantee that data reflects the latest committed transaction. If the source changes at `t = 1` while TTL is 5 minutes, an old entry can still be served for the remaining window unless invalidated.

Therefore, TTL must be designed alongside:

- business staleness tolerance;
- `@CacheEvict`/`@CachePut` strategy;
- transaction/commit ordering;
- multi-instance invalidation;
- source query latency and cost;
- observability of hits/misses, loads, memory, and cache backend failures.

### 4.4. Dynamic TTL may require context unavailable on the annotation

A product might be cached for 1 minute, a token expires at an absolute timestamp, and an error result is cached for only a few seconds. Policies that vary by value, response metadata, issuance time, or data sensitivity cannot always be expressed as a fixed number of seconds on a method.

Some backends support **per-entry expiration** or **TTL functions**. Spring lets the application customize that backend directly without forcing every implementation into a single API.

### 4.5. Decoupling business code from infrastructure

Replacing a local cache with a distributed cache often requires tuning TTLs, serializers, sizes, eviction, and topology. If those native policies lived inside annotations on hundreds of service methods, changing infrastructure would become hard to manage. With the abstraction, annotations focus on **the caching semantics of the call**, while infrastructure configures lifecycle.

## 5. Configuring TTL properly with Caffeine

### 5.1. Java Config for a cache region

Caffeine is a **local in-memory** caching library. This configuration example is for an application with a Spring context and Caffeine dependency already in place:

~~~java
import java.time.Duration;
import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.cache.CacheManager;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CacheConfiguration {

    @Bean
    public CacheManager cacheManager() {
        CaffeineCacheManager manager =
            new CaffeineCacheManager("products");

        manager.setCaffeine(
            Caffeine.newBuilder()
                .maximumSize(1_000)
                .expireAfterWrite(Duration.ofMinutes(5))
        );
        return manager;
    }
}
~~~

This snippet is **integration Java Config**, not a standalone application. It requires `spring-context-support` and `com.github.ben-manes.caffeine:caffeine`, and `@EnableCaching` must be present in the application.

A service uses it as follows:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public ProductDto getProduct(long id) {
    return repository.findDtoById(id);
}
~~~

There is no `ttl` on the annotation. Entries expire because **`CaffeineCacheManager` creates a Caffeine cache configured with a 5-minute `expireAfterWrite` policy**.

### 5.2. Local cache vs. distributed cache

If three service instances use Caffeine, each instance has its own cache memory and manages its own expiration. A 5-minute TTL on instance A **does not synchronize** values with instance B or C. If business logic needs cluster-wide synchronized invalidation, consider a shared cache (Redis, etc.) or broadcasting eviction events across instances.

### 5.3. Cache size and memory cleanup

`expireAfterWrite` caps entry age, yet does not replace `maximumSize` and resource management. With Caffeine, an expired entry is treated as unusable on lookup, while **physical cleanup and removal notifications can occur during maintenance cycles**, not necessarily at the exact nanosecond on the wall clock. If timely cleanup during idle traffic is required, the provider offers a scheduler option.

Do not write tests asserting that physical map size or removal listeners always update the instant the TTL boundary passes. Test **retrieved values after expiration** using a fake clock or an appropriate provider API.

## 6. Runnable Java 17 example: TTL governed by the provider

The example below runs with **Spring Framework 6.2.10**, **Caffeine 3.1.8**, Java 17, and Maven. Specifically, it demonstrates:

1. The `@Cacheable` annotation contains no TTL.
2. A 5-second TTL is configured on `CaffeineCacheManager` via `expireAfterWrite`.
3. Calling the same key again before the TTL produces a cache hit without running the method body.
4. After advancing simulated time past the TTL, the next read becomes a cache miss and reloads data.
5. Reads before the TTL **do not extend** the deadline in expire-after-write mode.

No `Thread.sleep()` is used, so the test does not depend on CPU delays or the OS scheduler.

### 6.1. Directory structure

~~~text
spring-cache-ttl/
├── pom.xml
└── src/main/java/demo/TtlDemo.java
~~~

### 6.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>spring-cache-ttl</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.10</version>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context-support</artifactId>
      <version>6.2.10</version>
    </dependency>
    <dependency>
      <groupId>com.github.ben-manes.caffeine</groupId>
      <artifactId>caffeine</artifactId>
      <version>3.1.8</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.1</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### 6.3. `src/main/java/demo/TtlDemo.java`

~~~java
package demo;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import com.github.benmanes.caffeine.cache.Caffeine;
import com.github.benmanes.caffeine.cache.Ticker;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class TtlDemo {

    // Simulated clock: tracks time in nanoseconds.
    public static final class ManualTicker implements Ticker {
        private final AtomicLong nanos = new AtomicLong();

        @Override
        public long read() {
            return nanos.get();
        }

        public void advance(Duration duration) {
            nanos.addAndGet(duration.toNanos());
        }
    }

    @Configuration
    @EnableCaching
    public static class Config {

        @Bean
        public ManualTicker manualTicker() {
            return new ManualTicker();
        }

        @Bean
        public CacheManager cacheManager(ManualTicker ticker) {
            CaffeineCacheManager manager =
                new CaffeineCacheManager("products");

            manager.setCaffeine(
                Caffeine.newBuilder()
                    .maximumSize(100)
                    .expireAfterWrite(Duration.ofSeconds(5))
                    .ticker(ticker)
            );
            return manager;
        }

        @Bean
        public ProductService productService() {
            return new ProductService();
        }
    }

    public static class ProductService {
        private final AtomicInteger sourceCalls = new AtomicInteger();

        // No ttl declared on @Cacheable at all.
        @Cacheable(cacheNames = "products", key = "#p0")
        public String getProduct(String sku) {
            int count = sourceCalls.incrementAndGet();
            return "Product-" + sku + " (load=" + count + ")";
        }

        public int sourceCalls() {
            return sourceCalls.get();
        }
    }

    public static void main(String[] args) {
        try (var ctx =
                new AnnotationConfigApplicationContext(Config.class)) {

            ProductService service =
                ctx.getBean(ProductService.class);
            ManualTicker ticker = ctx.getBean(ManualTicker.class);

            System.out.println("t=0: " + service.getProduct("A"));
            System.out.println("t=0 again: " + service.getProduct("A"));
            ticker.advance(Duration.ofSeconds(4));
            System.out.println("t=4: " + service.getProduct("A"));

            ticker.advance(Duration.ofSeconds(2));
            System.out.println("t=6: " + service.getProduct("A"));

            ticker.advance(Duration.ofSeconds(4));
            System.out.println("t=10: " + service.getProduct("A"));

            ticker.advance(Duration.ofSeconds(2));
            System.out.println("t=12: " + service.getProduct("A"));
            System.out.println(
                "Source calls: " + service.sourceCalls());
        }
    }
}
~~~

**Why does this example work?** `@EnableCaching` lets Spring apply cache advice to bean invocations. `ProductService` is retrieved from `ApplicationContext`, not instantiated manually with `new` inside `main`. `ManualTicker` is passed to the Caffeine builder; advancing the simulated clock makes Caffeine treat entries as having aged accordingly.

### 6.4. Running

From the directory containing `pom.xml`, with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.TtlDemo
~~~

Output **printed by the program** (excluding Maven logs):

~~~text
t=0: Product-A (load=1)
t=0 again: Product-A (load=1)
t=4: Product-A (load=1)
t=6: Product-A (load=2)
t=10: Product-A (load=2)
t=12: Product-A (load=3)
Source calls: 3
~~~

### 6.5. Exact timestamp-by-timestamp explanation

| Simulated time | Key `A` state | Does `getProduct` body run? | Value |
| --- | --- | --- | --- |
| t = 0 | Miss, written first time | Yes | `load=1` |
| t = 0, called again | Hit | No | `load=1` |
| t = 4 | Within 5 seconds since write at t=0 | No | `load=1` |
| t = 6 | Past expiration of entry written at t=0 | Yes | `load=2`, rewritten at t=6 |
| t = 10 | Within lifetime of entry written at t=6 | No | `load=2` |
| t = 12 | Past expiration of entry written at t=6 | Yes | `load=3` |

Important: reading at t=4 **does not reset** the t=5 expiration deadline. Had the configuration been `expireAfterAccess(Duration.ofSeconds(5))`, hitting at t=4 would extend the allowed access window, producing a different result. This choice belongs to Caffeine, **not** `@Cacheable`.

**Verification note:** the program uses a single JVM with no external data updates or transactions; it verifies only local Caffeine cache expiration. For production, replace the simulated source with a real repository and verify invalidation when source data changes.

## 7. Configuring TTL in Spring Boot

Spring Boot offers convenient properties for many providers. However, these properties take effect only when **Boot actually auto-configures the corresponding `CacheManager`**; if the application registers its own cache manager bean, inspect how that custom bean is configured.

### 7.1. Redis cache with a 10-minute TTL

Example `application.properties` for an application with Boot auto-configured Redis:

~~~properties
spring.cache.type=redis
spring.cache.cache-names=products,productSummaries
spring.cache.redis.time-to-live=10m
~~~

Here, the 10-minute TTL is applied to **`RedisCacheManager` configuration**, not passed into each `@Cacheable`.

With the Redis provider, you also need Redis connectivity, drivers, serializers, key prefixes, error handling, and valid deployment policies. The snippet above illustrates only TTL, not a complete Redis configuration.

### 7.2. Caffeine cache with a 10-minute expire-after-write

~~~properties
spring.cache.type=caffeine
spring.cache.cache-names=products,productSummaries
spring.cache.caffeine.spec=maximumSize=1000,expireAfterWrite=600s
~~~

Caffeine is a local cache; this property does not synchronize expiration across instances. Note the option name **`expireAfterWrite`**, not `ttl` as an annotation attribute.

If you want **expire-after-access**, substitute an option like `expireAfterAccess=600s`; the two policies differ on whether reads extend the deadline.

### 7.3. Why is there no single `spring.cache.ttl` property?

Spring Boot provides **provider-specific** properties such as `spring.cache.redis.time-to-live` and `spring.cache.caffeine.spec`. They do not share the same name because the backends do not share the same expiration model.

Configuring properties in Spring Boot is an auto-configuration convenience; it does not mean the Spring Framework Cache abstraction added a standard TTL attribute to `@Cacheable`.

Reference: https://docs.spring.io/spring-boot/reference/io/caching.html

## 8. Different TTLs for multiple cache regions

An application might require:

- `productDetails`: 10 minutes.
- `inventoryCounts`: 15 seconds.
- `referenceData`: 1 hour.

Using a single TTL for everything can leave inventory counts stale for too long or reload reference data too often.

### 8.1. Redis: configuring per cache name

Spring Data Redis supports `RedisCacheConfiguration`. The Java snippet below is **illustrative configuration code** requiring Spring Data Redis and a real `RedisConnectionFactory`:

~~~java
import java.time.Duration;
import java.util.Map;

import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

public class RedisCacheFactory {

    public RedisCacheManager build(
            RedisConnectionFactory connectionFactory) {

        RedisCacheConfiguration defaultConfig =
            RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofMinutes(10));

        RedisCacheConfiguration inventoryConfig =
            RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofSeconds(15));

        RedisCacheConfiguration referenceConfig =
            RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofHours(1));

        return RedisCacheManager.builder(connectionFactory)
            .cacheDefaults(defaultConfig)
            .withInitialCacheConfigurations(Map.of(
                "inventoryCounts", inventoryConfig,
                "referenceData", referenceConfig
            ))
            .build();
    }
}
~~~

Cache names without an explicit configuration can use the default, depending on the manager's cache creation policy. This manages TTL **by region**, not by annotation.

Spring Data Redis 3.2+ may offer a TTL function feature to compute lifetimes from the value or arguments of a write operation; verify provider version and semantics before using it. Do not assume every backend permits differing TTLs per entry.

### 8.2. Caffeine: multiple managers or individually configured caches

A standard `CaffeineCacheManager` can be configured with a shared `Caffeine` builder for caches it creates. When regions need markedly different TTLs, options include:

- **Multiple `CacheManager` beans** configured separately and selected by bean name via `cacheManager` or `CacheResolver`.
- **Registering customized native caches** per name via APIs supported by the version in use.
- **Grouping cache regions** that share expiration/size policies instead of forcing everything onto one builder.

Illustrative snippet selecting a manager by a bean name registered in the application:

~~~java
@Cacheable(
    cacheNames = "inventoryCounts",
    cacheManager = "fastExpiringCacheManager",
    key = "#p0"
)
public long inventoryCount(String sku) {
    return repository.countBySku(sku);
}
~~~

This snippet is **not standalone runnable**; the `fastExpiringCacheManager` bean and `repository` must be configured. It illustrates how a method selects a region/provider configured with a short TTL.

### 8.3. Result-dependent or per-key TTL

If an entry needs its own business-driven expiration, you may need native APIs:

- Caffeine provides variable expiration via `Expiry` when an entry requires a custom lifetime.
- Redis can support a TTL function in `RedisCacheConfiguration` in corresponding Spring Data Redis versions.
- Operations using `RedisTemplate` can call Redis APIs with explicit expiration, though that is **a different access model** from standard annotation-based caching.

Never assume a custom `@MyCacheable(ttl=...)` meta-annotated with `@Cacheable` automatically enforces TTL. Meta-annotations only inherit the Spring cache operation semantics; controlling native expiration requires custom integration logic, and the solution is no longer fully portable.

## 9. Common misconceptions about annotations and lifecycle

### 9.1. `@CacheEvict` does not trigger automatically after N seconds

~~~java
@CacheEvict(cacheNames = "products", key = "#p0")
public void updateProduct(long id) {
    repository.update(id);
}
~~~

This is **illustrative code**. The annotation is processed upon a **method invocation / business event**, not by counting down 300 seconds and then evicting. By default, after the method completes normally, Spring requests removal of the matching entry.

If automatic time-based expiration is needed, configure the provider.

### 9.2. `unless` and `condition` do not define TTL

~~~java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    condition = "#p0 > 0",
    unless = "#result == null"
)
public ProductDto getProduct(long id) {
    return repository.findDto(id);
}
~~~

This is **illustrative code**. `condition` decides whether a call participates in caching; `unless` vetoes storing a newly computed result. Neither means “delete the entry after 5 minutes.”

A SpEL time comparison inside `condition` does not make **already-existing entries** expire at that timestamp either. Using time values to build versioned keys requires managing old keys, memory, and synchronization; that is a **versioned cache design**, not native TTL.

### 9.3. `sync = true` does not mean TTL-based refresh

`@Cacheable(sync = true)` hints to the provider to coordinate concurrent calls for the same key on a cache miss, helping reduce duplicate loads if supported by the provider. It **does not add TTL** and does not schedule refreshes. Review `sync`'s other constraints when designing cache operations.

### 9.4. `@CachePut` can reset lifecycle per provider policy

`@CachePut` always executes the target method and considers storing the result in the cache. If the provider uses expire-after-write, rewriting the entry usually **restarts the lifetime from the write time**. Yet Spring Cache itself does not know what the TTL is; the provider decides.

### 9.5. Caching `null` or error results still needs a policy

If a method returns `null` and the provider allows storing nulls, a “not found” outcome can be cached. Whether to cache `null` for 10 seconds or skip caching `null` is an application/provider decision. Likewise, if a method catches an exception and returns a normal error DTO, that DTO can enter the cache unless blocked by `unless` or a suitable condition.

Negative caching should use an appropriate TTL and avoid turning transient errors into long-lived cached results.

### 9.6. Having no TTL does not mean data lives forever

Entries can still disappear due to:

- application restarts (for local caches);
- `@CacheEvict` or a `Cache.evict/clear` call;
- provider eviction when exceeding maximum size/memory;
- failovers and storage policies;
- administrators or housekeeping jobs deleting keys;
- provider-specific retention settings.

Hence “no TTL configured” and “entries are never lost” are two distinct statements.

## 10. TTL guarantees neither always-fresh data nor always-fast systems

### 10.1. Stale data before expiration

Suppose `inventoryCounts[SKU-1]` holds 10 with a 1-hour TTL. At minute 3, the warehouse ships 2 units, leaving 8. Without deleting or updating the entry, cache reads for the remaining lifetime may continue seeing 10.

For stronger consistency, combine:

- eviction with `@CacheEvict` after updating the source;
- updating with the exact new value via `@CachePut`;
- invalidation events sent to instances;
- shorter TTLs on sensitive regions;
- choosing not to cache certain critical reads.

TTL is an **age bound**, not a transaction synchronization mechanism.

### 10.2. Cache stampede after synchronized expiration

If thousands of keys expire at the same instant (or a very hot key expires under heavy traffic), many requests can hit the source concurrently. Consider:

- `@Cacheable(sync = true)` when the provider supports appropriate semantics;
- per-key single-flight/locking at the provider layer;
- TTL jitter to spread expiration times;
- well-designed refresh-ahead or stale-while-revalidate;
- monitoring source load when cache misses spike.

Do not assume every `CacheManager` supports cross-instance locking. Local Caffeine caches on multiple nodes can still all miss into the source on different nodes.

### 10.3. Where is TTL time measured?

- **Caffeine:** policies use the in-process cache's time source/ticker.
- **Redis:** expiration is managed inside Redis using the backend's semantics and clock.
- **Distributed caches:** instances must agree on keys, serialization, and invalidation, though they do not necessarily measure time the same way as a local cache.

Do not read `System.currentTimeMillis()` on each service instance and assume the provider expires at the exact same millisecond across nodes. For business-critical absolute deadlines (token expiration, legal deadlines), design to system requirements and account for clock skew.

### 10.4. Transactions and expiration/eviction

A `@CachePut` or `@CacheEvict` paired with a database update can run at a different point from transaction commit depending on advice ordering and transaction-aware cache settings. TTL cannot fix updating the cache before commit, nor races where a reader loads stale data while a writer evicts the cache.

When correctness outweighs latency, test rollbacks/commits and concurrent reads, and apply an appropriate after-commit policy.

## 11. How to choose TTLs and design per cache region

There is no “Spring standard” TTL value. Start from business-tolerated staleness, change frequency, source cost, access patterns, and the blast radius of wrong data.

| Data type | Considerations | Starting-point policy to evaluate |
| --- | --- | --- |
| Static catalog | Infrequently updated, clear release process | Relatively long TTL plus invalidation on deployment updates |
| Product pricing | May change per campaign | Shorter TTL; evict cache on price-change events |
| Inventory | Sensitive to sales transactions | Very short TTL or avoid caching on purchase-decision paths; verified invalidation needed |
| Config rules | Tied to versions or deployments | Keyed by version/config generation; longer TTL possible |
| “Not found” results | Data may be created shortly afterward | Short TTL or skip caching `null` |
| Personal/permission data | Requires authorization checks and leak prevention | Consider not caching, or strictly scoped keys/regions |

These are **evaluation guidelines**, not a promise that every system should pick fixed minute counts. The right TTL must be measured and agreed upon against business requirements.

### Design checklist

- [ ] Explicitly defined which data may be stale and for how long.
- [ ] Distinguished write-based TTL from access-based TTI.
- [ ] Selected a provider with matching expiration capabilities.
- [ ] Configured TTL where the provider actually enforces it, not on non-existent annotation attributes.
- [ ] Partitioned cache names by data group and lifetime policy.
- [ ] Defined `@CacheEvict`/`@CachePut` strategies for updates needing immediate visibility.
- [ ] Configured capacity limits/maximum size and monitored evictions.
- [ ] Tested expiration with a fake clock/ticker or an equivalent deterministic method.
- [ ] Tested cache hits, misses, expiration, reloads, and provider failures.
- [ ] Tested multi-instance, transactional, and concurrent behaviors if applicable.
- [ ] Monitored hit rate, load latency, stale data, memory, Redis connections, and cache errors.
- [ ] Avoided relying on TTL to replace authorization or idempotency checks.

## 12. Self-check questions

**1.** Why does `@Cacheable` not declare a generic `ttl`?  
**Answer:** Spring Cache abstracts cache read/write/evict operations across many providers with differing expiration capabilities; TTL belongs to backend policy.

**2.** Can `@Cacheable(cacheNames="x", ttl=60)` be used in standard Spring Framework cache annotations?  
**Answer:** No, `ttl` is not an attribute of `@Cacheable`.

**3.** Does the default `ConcurrentMapCacheManager` automatically expire entries after 5 minutes?  
**Answer:** It has no built-in TTL. Entries can be removed manually or disappear when the cache/process terminates, yet there is no standard expire-after-write.

**4.** What is the difference between `expireAfterWrite(5m)` and `expireAfterAccess(5m)`?  
**Answer:** The first measures from write/replace; the second measures from the most recent access, so cache hits can slide the deadline.

**5.** In the demo, why did `getProduct("A")` hit at t=4 yet miss at t=6?  
**Answer:** The 5-second TTL is measured from the write at t=0; reading at t=4 did not reset the deadline.

**6.** Does Spring Boot have a generic `spring.cache.ttl=5m` property for all providers?  
**Answer:** No. There are provider-specific options like `spring.cache.redis.time-to-live` and `spring.cache.caffeine.spec`.

**7.** If the DB changes before the TTL ends, does the cache automatically detect it?  
**Answer:** No. You need eviction/put or another sync/invalidation mechanism if fresh data is required immediately.

**8.** Does `@CacheEvict` run automatically after 60 seconds?  
**Answer:** No; it is bound to a cache operation triggered by a method invocation.

**9.** If two types of data need very different TTLs, what should you do?  
**Answer:** Separate cache names/provider configurations per region or use per-entry/per-region expiration policies supported by the provider.

**10.** Why avoid `Thread.sleep(5000)` in TTL unit tests?  
**Answer:** Tests become slow, scheduler-dependent, and flaky. With Caffeine, you can inject a fake `Ticker` as shown in the example.

**11.** When Caffeine marks an entry expired, is it necessarily removed from internal structures at that exact instant?  
**Answer:** No. The entry is invalid upon retrieval, while physical cleanup and notifications may occur when maintenance runs.

**12.** Does TTL prevent a cache stampede when a hot key expires?  
**Answer:** No. You may need miss synchronization, refresh strategies, jitter, or other techniques beyond TTL.

## References

- Spring Framework 6.2 — How can I Set the TTL/TTI/Eviction policy/XXX feature?: https://docs.spring.io/spring/reference/6.2/integration/cache/specific-config.html
- Spring Framework — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework 6.2 — CaffeineCacheManager API: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/cache/caffeine/CaffeineCacheManager.html
- Spring Boot — Caching and provider-specific properties: https://docs.spring.io/spring-boot/reference/io/caching.html
- Spring Data Redis — RedisCacheConfiguration API: https://docs.spring.io/spring-data/redis/docs/3.4.1/api/org/springframework/data/redis/cache/RedisCacheConfiguration.html
- Caffeine documentation — Eviction/expiration and ticker: https://github.com/ben-manes/caffeine/wiki/Eviction
- Caffeine documentation — Cleanup of expired entries: https://github.com/ben-manes/caffeine/wiki/Cleanup
