# CaffeineCache and CaffeineCacheManager in Spring Framework Cache

## 1. Overview: Where Does Caffeine Fit in Spring Cache?

Spring Cache is an **abstraction layer** that allows applications to declare or invoke cache read/write operations without tying themselves tightly to a specific storage library. Caffeine is a **high-performance in-memory caching library for Java**; Spring provides an adapter that brings Caffeine into the `org.springframework.cache.Cache` contract.

Two core classes:

- `org.springframework.cache.caffeine.CaffeineCache`: **an adapter for a single cache region**; implements the `org.springframework.cache.Cache` interface and wraps a native `com.github.benmanes.caffeine.cache.Cache` (or `AsyncCache` depending on configuration). It responds for a specific cache name, such as `products`.
- `org.springframework.cache.caffeine.CaffeineCacheManager`: **a manager for multiple cache regions**; implements `CacheManager`, creates/looks up `CaffeineCache` instances by name, and applies shared Caffeine configuration.

Look at the diagram:

```text
Controller / caller
       |
       v
Spring proxy / CacheInterceptor (when using annotations)
       |
       v
CacheManager.getCache("products")
       |
       v
CaffeineCacheManager -------------------> Manages cache names
       |
       v
CaffeineCache(name="products") ----------> Spring Cache adapter
       |
       v
Native Caffeine Cache<Object, Object> --> Stores key/value in the JVM
```

**Distinguishing roles:** `CacheManager` is responsible for **selecting the region**, while `Cache` is responsible for **operating on entries**. The `@Cacheable` annotation uses Spring's abstraction; Caffeine itself does not understand annotations unless the Spring Cache mechanism is enabled.

Caffeine is a **local cache**: independent JVM instances generally have independent cache memory. It does not automatically create Redis, distributed caching, replication, or cluster-wide locking. This lesson walks through dependencies, configuration, APIs, lifecycle, a runnable example, and deployment limitations.

## 2. Required Dependencies and Runtime Prerequisites

For a plain Java Spring Framework application, both **Spring context** and the **Caffeine library** are needed; adding only `spring-context` does not provide the native Caffeine engine.

Maven example (JDK 17+):

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-context</artifactId>
        <version>6.2.9</version>
    </dependency>
    <dependency>
        <groupId>com.github.ben-manes.caffeine</artifactId>
        <artifactId>caffeine</artifactId>
        <version>3.1.8</version>
    </dependency>
</dependencies>
```

The two versions above are a real **illustrative** version pair. Spring Framework 6.1+ requires Caffeine 3.0 or higher for the modern adapter. When using Spring Boot, prefer the dependency versions managed by Boot's BOM if available, rather than hardcoding incompatible version numbers.

For annotations to take effect:

1. Create a `CacheManager` bean, such as `CaffeineCacheManager`.
2. Enable `@EnableCaching` on a `@Configuration` class.
3. Place `@Cacheable`, `@CachePut`, or `@CacheEvict` on the appropriate method.
4. Invoke the method through a **Spring-managed bean/proxy**. In default proxy mode, internal calls like `this.find(...)` usually bypass caching advice.

If you only use the `CacheManager.getCache(...)` and `Cache.put(...)` APIs directly, `@EnableCaching` is not strictly required; that is programmatic usage.

## 3. CaffeineCache: One Adapter per Cache Name

`CaffeineCache` implements `org.springframework.cache.Cache` and forwards operations to the corresponding native Caffeine region.

Commonly used APIs:

| Spring `Cache` API | Meaning |
| --- | --- |
| `getName()` | Name of the cache region, e.g. `products` |
| `get(key)` | Returns `Cache.ValueWrapper` if an entry exists, or a null wrapper on cache miss |
| `get(key, Product.class)` | Retrieves the value with the expected type; cannot distinguish a miss from a cached null from the null return alone |
| `get(key, Callable<T>)` | Retrieves or loads the value via a callback when the key is absent |
| `put(key, value)` | Inserts a new value or replaces an existing value for the key |
| `putIfAbsent(key, value)` | Inserts only if no mapping exists; returns the wrapper of the existing entry |
| `evict(key)` | Removes the entry by key |
| `clear()` | Clears all entries in the region |
| `getNativeCache()` | Returns the native Caffeine Cache to access Caffeine-specific features |

Example working with an existing `CacheManager manager` bean:

```java
import org.springframework.cache.Cache;
import org.springframework.cache.caffeine.CaffeineCache;

Cache cache = manager.getCache("products");
if (!(cache instanceof CaffeineCache caffeineCache)) {
    throw new IllegalStateException("Expected a Caffeine-backed cache");
}
cache.put("P1", "Pen");
System.out.println(cache.get("P1", String.class)); // Pen
System.out.println(caffeineCache.getName());       // products

// Native Caffeine API, use only when provider-specific capabilities are needed:
var nativeCache = caffeineCache.getNativeCache();
```

This is an **illustrative snippet** (assuming `manager` already exists), not a standalone program. The cast needs a guard because another `CacheManager` might return a Redis, JCache, ConcurrentMap adapter, or a decorator.

`CaffeineCache.getNativeCache()` allows measuring estimated size, viewing stats (if enabled), obtaining `asMap()`, etc. However, operating directly on the native cache **bypasses the Spring abstraction**, so it may skip `null` conversion, decorators, and Spring-level policies. For business read/write operations, prefer the `Cache` abstraction; only use the native API for intentional configuration or observation.

### 3.1. Cache Miss vs. Stored Null

`cache.get(key) == null` means there is no `Cache.ValueWrapper` — the key is not mapped. Conversely, `wrapper != null && wrapper.get() == null` indicates there is an entry storing null, **if the configuration allows it**.

Native Caffeine normally does not accept null values; Spring can convert null into an internal sentinel when `allowNullValues=true`. Therefore, the native map may contain a representation that does not look like a Java null object. Do not read directly from native and infer that it represents Spring's full null behavior.

In the hands-on example below, `setAllowNullValues(false)` is paired with `unless="#result == null"` so the cache is not asked to store null results.

## 4. CaffeineCacheManager: Creating and Selecting Cache Regions

### 4.1. Dynamic Mode: Auto-Creating Caches for Requested Names

```java
CaffeineCacheManager manager = new CaffeineCacheManager();
var cache = manager.getCache("products");
```

The no-argument constructor uses **dynamic mode**: each unknown name can have a cache created lazily. `getCache("products")` creates the needed region on first use; subsequent lookups for the same name use the manager's corresponding region.

The advantage is not having to declare every name upfront; the disadvantage is that a typo in `cacheNames` like `prodcuts` can silently create a new region instead of reporting an error.

A dynamic manager placed ahead of other managers in a `CompositeCacheManager` can accept every cache name and prevent lookup from reaching downstream delegates. When clear backend separation is needed, consider static mode.

### 4.2. Static Mode: Accepting Only Known Names

```java
CaffeineCacheManager manager =
        new CaffeineCacheManager("products", "productLabels");

System.out.println(manager.getCache("products") != null); // true
System.out.println(manager.getCache("unknown") != null);  // false
```

The constructor taking a list of cache names creates the manager in **static mode**. You can change the set of names with `setCacheNames(Collection<String>)`. In static mode, the manager does not auto-create new regions for unknown names; `getCache(name)` returns null if no accepted region exists.

Note that `setCacheNames(...)` can replace previously created caches for the specified names; it is not a harmless metadata-only list change. It is best to configure names and policies **before the application starts serving requests**. To revert to dynamic mode, the API accepts a null collection.

### 4.3. Shared Configuration for Manager-Created Regions

```java
CaffeineCacheManager manager =
        new CaffeineCacheManager("products", "productLabels");

manager.setCaffeine(
        com.github.benmanes.caffeine.cache.Caffeine.newBuilder()
            .maximumSize(500)
            .expireAfterWrite(java.time.Duration.ofMinutes(10))
            .recordStats()
);
manager.setAllowNullValues(false);
```

`setCaffeine(...)` accepts a Caffeine builder and applies a shared configuration to regions created by the manager. You can also pass spec-based configuration via `setCaffeineSpec(...)` or a string via `setCacheSpecification(...)`:

```java
manager.setCacheSpecification(
        "maximumSize=500,expireAfterWrite=10m,recordStats");
```

These are **two mutually exclusive alternatives**; you do not need to call both `setCaffeine(...)` and `setCacheSpecification(...)` on the same manager. Choose the builder when type safety and advanced customization are needed; spec is convenient for string-based configuration.

**Important:** TTL and entry count limits are native Caffeine cache policies. `@Cacheable` does not have a built-in provider-independent TTL attribute.

## 5. Common Cache Policies

### 5.1. Size Limits

```java
Caffeine.newBuilder().maximumSize(500)
```

Caffeine uses the library's eviction mechanism to keep approximately up to the configured maximum number of entries. This is **not** a business constraint guaranteeing an exact count of 500 entries at every instant; some maintenance/eviction work may run according to the provider's internal mechanics.

If data items vary widely in size, consider Caffeine's `maximumWeight(...)` and `weigher(...)` instead of treating every entry as having equal cost. Do not use `maximumSize` and `maximumWeight` simultaneously on the same builder.

### 5.2. Expire-after-write and expire-after-access

- `expireAfterWrite(Duration)`: expires based on the elapsed time since entry creation or value replacement; **reads** do not reset the expire-after-write clock.
- `expireAfterAccess(Duration)`: expires when a key has not been read or written for a duration; frequent access can keep an entry alive longer.
- `refreshAfterWrite(Duration)` is a **refresh** mechanism for loading caches and has different semantics from expiration; it requires a loader and you must verify how stale values are served during refresh. Do not treat refresh as synonymous with immediate eviction at the deadline.

Example using expire-after-write:

```java
var policy = Caffeine.newBuilder()
        .maximumSize(500)
        .expireAfterWrite(java.time.Duration.ofMinutes(10));
```

This is an **illustrative snippet** requiring `import com.github.benmanes.caffeine.cache.Caffeine`. After expiration, the next read typically finds no valid entry and may need to reload. Spring/Caffeine does not automatically refresh source data if the method is not called or if there is no separate refresh/loader mechanism.

### 5.3. Statistics

`recordStats()` enables recording metrics such as hits, misses, loads, and evictions on the native cache. When statistics are enabled:

```java
CaffeineCache springCache =
        (CaffeineCache) manager.getCache("products");

var stats = springCache.getNativeCache().stats();
System.out.println(stats.hitCount());
System.out.println(stats.missCount());
```

The lines above are illustrative only and **have no fixed stdout**: numbers depend on the calls that have occurred. Stats here are native provider metrics; when using Micrometer/Spring Boot Actuator, appropriate binding/observability configuration is required — do not assume `recordStats()` automatically exports metrics to a monitoring server.

### 5.4. Eviction Execution Timing

Caffeine may perform maintenance during reads/writes and may require cleanup for stats/size to reflect newly expired state. Native `estimatedSize()` is an **estimate**, not an instantaneously synchronized count of valid entries at every moment.

Do not write tests that rely on `estimatedSize()` dropping by an exact unit immediately after a fixed `sleep`. Instead, test `get` behavior after expiry using a controlled time source, or use the provider's testing APIs.

## 6. Runnable Example: Spring Framework 6.2.9 + Caffeine 3.1.8

The following Java 17 program uses plain Spring configuration and `CaffeineCacheManager`. It demonstrates:

1. Two reads for product `P1`: one cache miss and one cache hit.
2. `@CachePut` updating the value in the `products` region without forcing another reload.
3. `@CacheEvict` removing the entry when the product is deleted.
4. `unless="#result == null"` avoiding caching a not-found result, so the subsequent query still reads from the source.
5. A static manager with only the `products` region; an undeclared name is not auto-created.

**Project structure:**

```text
caffeine-spring-demo/
├── pom.xml
└── src/main/java/CaffeineCacheDemo.java
```

**Contents of `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>caffeine-spring-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
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
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**Contents of `src/main/java/CaffeineCacheDemo.java`:**

```java
import java.time.Duration;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.cache.Cache;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCache;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CaffeineCacheDemo {

    @Bean
    CaffeineCacheManager cacheManager() {
        var manager = new CaffeineCacheManager("products");
        manager.setAllowNullValues(false);
        manager.setCaffeine(Caffeine.newBuilder()
                .maximumSize(100)
                .expireAfterWrite(Duration.ofMinutes(10))
                .recordStats());
        return manager;
    }

    @Bean
    ProductRepository productRepository() {
        return new ProductRepository();
    }

    @Bean
    ProductService productService(ProductRepository repository) {
        return new ProductService(repository);
    }

    public record Product(String id, String name) {}

    public static class ProductRepository {
        private final Map<String, Product> data = new ConcurrentHashMap<>();
        private final AtomicInteger reads = new AtomicInteger();

        public ProductRepository() {
            data.put("P1", new Product("P1", "Pen"));
        }

        public Product find(String id) {
            reads.incrementAndGet();
            return data.get(id);
        }

        public Product save(Product product) {
            data.put(product.id(), product);
            return product;
        }

        public void delete(String id) {
            data.remove(id);
        }

        public int reads() {
            return reads.get();
        }
    }

    public static class ProductService {
        private final ProductRepository repository;

        public ProductService(ProductRepository repository) {
            this.repository = repository;
        }

        @Cacheable(
            cacheNames = "products",
            key = "#p0",
            unless = "#result == null"
        )
        public Product find(String id) {
            return repository.find(id);
        }

        @CachePut(cacheNames = "products", key = "#p0.id()")
        public Product update(Product product) {
            return repository.save(product);
        }

        @CacheEvict(cacheNames = "products", key = "#p0")
        public void delete(String id) {
            repository.delete(id);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(CaffeineCacheDemo.class)) {

            ProductService service = context.getBean(ProductService.class);
            ProductRepository repository =
                    context.getBean(ProductRepository.class);
            CaffeineCacheManager manager =
                    context.getBean(CaffeineCacheManager.class);

            System.out.println("first: " + service.find("P1"));
            System.out.println("second: " + service.find("P1"));
            System.out.println("reads after repeat: " + repository.reads());

            service.update(new Product("P1", "Blue pen"));
            System.out.println("after update: " + service.find("P1"));
            System.out.println("reads after update: " + repository.reads());

            service.delete("P1");
            System.out.println("after delete #1: " + service.find("P1"));
            System.out.println("after delete #2: " + service.find("P1"));
            System.out.println("reads final: " + repository.reads());

            Cache selected = Objects.requireNonNull(
                    manager.getCache("products"));
            System.out.println("Spring Caffeine adapter: "
                    + (selected instanceof CaffeineCache));
            System.out.println("unknown cache available: "
                    + (manager.getCache("missing") != null));
        }
    }
}
```

**Run from the directory containing `pom.xml`:**

```bash
mvn -q compile exec:java -Dexec.mainClass=CaffeineCacheDemo
```

**Lines printed by the program** (excluding environment-dependent Maven/Spring logs):

```text
first: Product[id=P1, name=Pen]
second: Product[id=P1, name=Pen]
reads after repeat: 1
after update: Product[id=P1, name=Blue pen]
reads after update: 1
after delete #1: null
after delete #2: null
reads final: 3
Spring Caffeine adapter: true
unknown cache available: false
```

### 6.1. Step-by-Step Readback Explanation

- The first `find("P1")` misses, calls the repository once, and stores the value `Product(P1,"Pen")`.
- The second call has the exact same key, hits the cache, and does not invoke the repository again: `reads = 1`.
- `update(Product("P1","Blue pen"))` runs the actual method, then `@CachePut` writes the new version into `products/P1`. The subsequent `find("P1")` hits the new version, so the source read count remains 1.
- `delete("P1")` deletes the source data and `@CacheEvict` removes the `products/P1` entry. The next lookup misses and returns null; `unless` prevents storing null. The following lookup misses again, increasing source reads from 1 to 3.
- `manager.getCache("products")` returns the `CaffeineCache` adapter. `manager.getCache("missing")` returns null because the manager was initialized with the single static name `products`.

**Note:** This is a single-JVM demo that prints a source call counter and uses a 10-minute TTL so immediate steps do not expire. Do not conclude that Caffeine guarantees cross-process cache synchronization or atomic database transactions.

## 7. CaffeineCacheManager and Different Policies Across Regions

`setCaffeine(...)` and `setCacheSpecification(...)` set a **shared** configuration for caches created by the manager. However, an application might want:

- `products`: maximumSize 1,000, expireAfterWrite 30 minutes.
- `labels`: maximumSize 5,000, expireAfterAccess 5 minutes.
- `pricing`: short lifetime because prices change rapidly.

When individual regions need their own native builders, Spring supports `registerCustomCache(name, nativeCache)`:

```java
CaffeineCacheManager manager = new CaffeineCacheManager("products");

manager.setCaffeine(Caffeine.newBuilder()
        .maximumSize(1_000)
        .expireAfterWrite(Duration.ofMinutes(30)));

manager.registerCustomCache(
        "labels",
        Caffeine.newBuilder()
            .maximumSize(5_000)
            .expireAfterAccess(Duration.ofMinutes(5))
            .build()
);
```

This is a standalone illustrative configuration snippet; imports for `Caffeine`, `Duration`, and `CaffeineCacheManager` are needed. A custom native cache is wrapped in an adapter and managed under the registered name; other regions continue using the manager's shared configuration. When using an async native cache, the API also provides an overload `registerCustomCache(String, AsyncCache<Object,Object>)`.

**Important:** Registering custom caches must be done during the configuration phase; do not arbitrarily replace existing caches while requests are accessing them. Each cache has its own policy, entries, and stats; `CacheManager` does not turn all caches with the same name across multiple managers into a unified store.

### 7.1. Does Changing Policy Take Effect Immediately on Existing Entries?

Think of changing the manager's builder/spec as **changing how native caches are constructed**, not as a transaction that immediately updates the TTL/size of all existing entries. Depending on the setter API and manager state, caches may be recreated/reset, losing stored entries.

Therefore, configure policies before putting the application into service. If runtime changes are unavoidable, use the manager/provider's official mechanism, understand the impact on entries, and test behavior under real traffic. Do not assume `setCaffeine` merely mutates a field on a running cache.

## 8. Null Handling and Limitations When Using Caffeine

Native Caffeine `Cache` does not store Java null as a normal entry value. However, the Spring adapter has a **null-value adaptation** mechanism. `CaffeineCacheManager` exposes:

```java
manager.setAllowNullValues(true);  // Can represent null via a sentinel.
manager.setAllowNullValues(false); // Rejects caching null.
```

When `allowNullValues=true`, Spring can convert Java null into a sentinel acceptable to the native store; when reading through Spring `Cache`, conversion returns null to the caller. Native `getIfPresent` should not be used to conclude whether Java null is present without understanding the adapter.

When `allowNullValues=false`, a caching path attempting to put null can cause an error. If the goal is to **skip caching not-found results**, use a result-based condition such as:

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

This snippet illustrates a service with a repository. `unless` is evaluated after the actual method returns and rejects caching null. With `Optional.empty()`, Spring Cache has unwrap semantics for supported `Optional` types; verify the provider's null behavior and actual return type.

**Do not combine `sync=true` with `unless`:** Spring `@Cacheable(sync=true)` does not support `unless`. If you want both single-flight loading and not caching null, design a value wrapper/cache provider or separate loading mechanism rather than combining incompatible annotation options.

## 9. Loading, Concurrency, and `@Cacheable(sync=true)`

`CaffeineCache` supports the `Cache.get(key, Callable)` path using a data-loading callback. Native Caffeine has compute-if-absent style evaluation, helping reduce duplicate loads when multiple threads in the same JVM simultaneously request a missing key.

Example:

```java
@Cacheable(cacheNames = "products", key = "#p0", sync = true)
public Product find(String id) {
    return repository.find(id);
}
```

This is an **alternative** snippet illustrating `find` from section 6; `unless` cannot be copied onto the same method alongside it.

Distinctions to keep clear:

- `sync=true` delegates loading coordination according to a cache provider contract; it does not automatically create a distributed mutex across all JVMs.
- In-memory Caffeine typically synchronizes only within the native cache instance of the current process.
- Two app instances with two separate Caffeine caches can still hit the source simultaneously because they do not share storage.
- `sync=true` does not solve the race where one thread loads stale data while another thread updates the DB and evicts the cache.
- Key selection must include every factor determining the result; omitting tenant/locale/currency can cause wrong result sharing.

If you truly need an L1 local + L2 remote cache, you cannot simply place a `CaffeineCacheManager` next to a Redis manager and expect Caffeine to automatically fall back per key. You need a multi-tier provider or composite `Cache` implementation with dedicated loading, update, and invalidation strategies.

## 10. Async CaffeineCache and Spring Framework 6.1+

Spring Framework 6.1+ supports asynchronous cache abstraction types. `CaffeineCacheManager` provides:

```java
manager.setAsyncCacheMode(true);
```

When async mode is enabled, newly created caches are built on Caffeine's `AsyncCache`; the Spring adapter can support `Cache.retrieve(key)` and `Cache.retrieve(key, supplier)` returning `CompletableFuture`. `CaffeineCache` exposes `getAsyncCache()` when a native async cache is available.

Points to note:

1. Only call `getAsyncCache()` when a native `AsyncCache` is actually present; otherwise an `IllegalStateException` may be thrown.
2. Spring Javadoc recommends **disabling** null configuration for async via `setAllowNullValues(false)` to keep `CompletableFuture` semantics simple and avoid unnecessary wrapping.
3. `setAsyncCacheMode(true)` controls caches created by the manager; registered custom caches have their own type and do not automatically switch sync ↔ async solely from this flag.
4. `setAsyncCacheLoader(...)` can build an asynchronous loading cache, but a loader shared across regions must have a compatible key/value contract.
5. Methods returning `CompletableFuture<T>` or Reactor types must be tested with the actual provider; do not infer correctness merely because synchronous `@Cacheable` works.

An illustrative signature on a service that already has a repository:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public java.util.concurrent.CompletableFuture<Product> findAsync(String id) {
    return java.util.concurrent.CompletableFuture.supplyAsync(
            () -> repository.find(id));
}
```

This snippet is **not part** of the standalone `CaffeineCacheDemo.java` program. Async caching requires executor, timeout, and failure-handling policies; Caffeine Cache does not replace overall asynchronous orchestration.

## 11. Using Caffeine with Spring Boot

When an application uses Spring Boot with `spring-boot-starter-cache` and the appropriate Caffeine dependency, Boot can auto-configure `CaffeineCacheManager` depending on the presence of other providers. Configuration example:

```properties
spring.cache.type=caffeine
spring.cache.cache-names=products,productLabels
spring.cache.caffeine.spec=maximumSize=500,expireAfterWrite=10m,recordStats
```

The syntax above is **an option for Boot**, not properties automatically read by plain Spring Framework's `AnnotationConfigApplicationContext`. Boot allows configuring a spec and/or `CaffeineSpec`/`Caffeine` beans according to auto-configuration precedence rules; consult the documentation for the Boot version in use. When an application provides a custom `CacheManager` bean, auto-configuration may back off.

Caching advice still needs to be enabled, typically via `@EnableCaching` in Spring configuration. `@Cacheable(cacheNames="products")` only works when the application has an appropriate manager/resolver, and TTL cannot be set via an annotation attribute.

Setting `spring.cache.type=caffeine` is helpful when multiple providers are on the classpath, but it does not replace testing region names, keys, the actual selected bean, and annotation effectiveness.

## 12. Caffeine Local Cache in Production

### 12.1. Benefits

- Very fast in-JVM access without network round trips on cache hits.
- Strong size/weight, expiration, refresh, and statistics policies from Caffeine.
- Well suited for caching reference data, infrequently changing configuration, computed results, and size-bounded DTOs.
- Integrates naturally with Spring's `@Cacheable`/`@CachePut`/`@CacheEvict`.

### 12.2. Limitations

- Each JVM has independent contents; when scaling from one instance to multiple instances, a change on node A does not automatically evict data on node B.
- Cache contents are lost on process restart; it is neither durable storage nor a source of truth.
- Choosing an improper `maximumSize`/TTL can cause memory pressure or excessive cache misses.
- Caching mutable objects can lead to unintended modifications if references are shared within the JVM. Caffeine does not automatically deep-copy objects for you.
- Using a shared key across different tenants/permissions/locales causes incorrect data sharing, even when the provider works technically as designed.
- Cache writes do not necessarily coincide with database transaction commits. Cache annotations do not inherently provide transactional atomicity.

A multi-node deployment must decide clearly: use local cache with short TTL and accept eventual consistency, broadcast invalidation events to nodes, use a distributed cache, or design a multi-tier cache with an explicit contract.

### 12.3. Metrics to Observe

- Hit/miss ratio, source load counts, evicted entry counts, and loader duration.
- Cache capacity and heap footprint; do not equate `estimatedSize()` with actual JVM memory usage.
- Whether TTL/refresh aligns with data change frequency.
- Latency of serving cache hits, cache misses, and impact during traffic spikes.
- Invalidation reliability after updates/deletes across nodes, including during rollbacks or delayed messages.

Avoid logging keys containing personal data or creating per-key metric tags due to exposure risks and high cardinality.

## 13. Common Mistakes and Fixes

1. **Adding only `spring-context` and forgetting the Caffeine library.** When `CaffeineCacheManager` is needed, a compatible `com.github.ben-manes.caffeine:caffeine` dependency must be present.
2. **Confusing `CaffeineCacheManager` with a single cache region.** The manager looks up/creates multiple regions; `CaffeineCache` represents a single named region.
3. **Forgetting `@EnableCaching`.** Annotations in code have no caching advice if the infrastructure is not enabled.
4. **Self-invocation or creating services manually with `new`.** Proxies do not intercept internal calls in default proxy mode.
5. **Using dynamic mode and misspelling a cache name.** `getCache("prodcuts")` can create a new region and mask a configuration error.
6. **Using static mode while an annotation requests an unknown name.** `getCache(name)` returns null; the operation cannot resolve a valid region.
7. **Expecting local caches to sync automatically across multiple JVMs.** Each node has its own cache unless a separate synchronization mechanism exists.
8. **Assuming `expireAfterWrite` means "auto-refresh".** Expiration invalidates the entry; reloading requires a request or loader.
9. **Reading the native cache and ignoring the null adapter.** Spring's sentinel may not match what the application expects.
10. **Enabling `allowNullValues(false)` while letting methods return null and still caching normally.** This can throw an error if a put is attempted; use `unless` where appropriate.
11. **Combining `sync=true` with `unless`.** This configuration is not supported by Spring on the same operation.
12. **Enabling `recordStats()` and expecting metrics to export automatically to monitoring systems.** Observability integration such as Micrometer/Actuator is required.
13. **Mixing incompatible value types under the same region/key.** One method may return `Product` while another returns `String` for the same key, causing cast errors or wrong results.
14. **Changing builder/TTL under live traffic and expecting all entries to stay intact.** The manager may recreate regions; changes must be controlled.
15. **Ignoring transactions/invalidation.** `@CachePut` and `@CacheEvict` must use consistent keys and appropriate timing relative to the database.
16. **Assuming async mode is always enabled by default.** `setAsyncCacheMode(true)` or a suitable native `AsyncCache` is required to use `retrieve`; test the async path separately.

## 14. Pre-Deployment Checklist

| Check Area | Acceptance Question |
| --- | --- |
| Dependencies | Are Spring Cache API, Caffeine 3.x, and a compatible JDK present? |
| Mode | Is the manager static or dynamic? Are there any typos in names? |
| Region mapping | Which `cacheNames` and manager/resolver does each operation use? |
| Policy | Are `maximumSize`/`maximumWeight`, expiry/refresh, and stats configured as needed? |
| Key | Does the key distinguish tenant, currency, locale, permissions, and filters affecting the result? |
| Null | Is caching null allowed or excluded via `unless`? |
| Concurrency | Have multiple threads on the same key and multiple nodes been tested separately? |
| Async | Are `AsyncCache` and `retrieve` used with the right provider/mode? |
| Invalidation | Do updates/deletes remove the right entries everywhere synchronization is required? |
| Observability | Are hit/miss, loads, evictions, and heap cost measured? |
| Production | Have TTL and max size been load-tested on realistic data? |

For a quick self-check, try four scenarios:

1. Call `find("P1")` twice: does the second call hit the cache?
2. After `update(P1)`: is the new entry put or is it still stale?
3. After `delete(P1)`: is the entry evicted? Are subsequent null reads cached again?
4. When adding a JVM instance: does the new node's cache automatically know the old node's data? If not, what mechanism satisfies the consistency requirement?

**Conclusion:** `CaffeineCacheManager` is responsible for managing regions; `CaffeineCache` bridges the Spring Cache abstraction and native Caffeine. Choosing the right region, key, null policy, expiry/size, and invalidation strategy matters more than simply adding dependencies and enabling cache annotations.

## Official Documentation

- Spring Framework 6.2.9 — `CaffeineCacheManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/cache/caffeine/CaffeineCacheManager.html
- Spring Framework 6.2.9 — `CaffeineCache` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/cache/caffeine/CaffeineCache.html
- Spring Framework — Cache Store Configuration: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
- Spring Framework — Cache Annotations: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Boot — Caching, Caffeine section: https://docs.spring.io/spring-boot/reference/io/caching.html
- Caffeine project: https://github.com/ben-manes/caffeine