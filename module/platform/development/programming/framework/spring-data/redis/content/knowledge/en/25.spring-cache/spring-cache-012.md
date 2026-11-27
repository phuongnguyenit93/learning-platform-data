# Proxy Limitations, Self-Invocation, and Data-Loading Synchronization in Spring Cache with Redis

## 1. Objectives and context

Spring Cache provides annotations such as `@Cacheable`, `@CachePut`, and `@CacheEvict` to add caching behavior to Java methods. When integrated with **Spring Data Redis**, method results can be stored in Redis so multiple application instances read from a shared cache. However, three concepts must be understood separately:

1. **Spring AOP proxy:** determines whether a method call passes through caching logic.
2. **Self-invocation:** calling one method from another on the same object typically bypasses the proxy; consequently, cache annotations may not execute.
3. **Loading synchronization:** when the cache lacks a value, concurrent requests may hit the canonical data source simultaneously. `@Cacheable(sync = true)` expresses a synchronization request, yet actual scope and guarantees depend on the `Cache` provider, Redis configuration, and multi-instance architecture.

This lesson explains how these three topics interact. The goal is avoiding situations like "added `@Cacheable` yet still hammering the data source," or "added `sync = true` yet multi-node deployments still suffer cache stampedes."

After completing this lesson, you will be able to:

- Trace the call path to a bean with cache annotations.
- Distinguish calls **going through a proxy** from calls **hitting the target object directly**.
- Structure services so `@Cacheable` and `@CacheEvict` are reliably applied.
- Explain how a single cache miss can trigger multiple concurrent data loads.
- Understand the `@Cacheable(sync = true)` contract and what it **does not guarantee** in distributed Redis.
- Distinguish in-JVM synchronization, cache-provider synchronization, and distributed locks.
- Select strategies to mitigate cache stampedes, synchronized TTL expirations, and database load spikes.
- Identify metrics needed to verify caching works as expected.

## 2. Spring Cache is an abstraction; Redis is a cache backend

Spring Cache defines a unified interface for operations like fetching results from cache, storing results, and evicting cached data. Annotations do not emit Redis commands directly; they describe **when** Spring should interact with the cache.

Example:

```java
@Cacheable(cacheNames = "products", key = "#productId")
public ProductDto getProduct(String productId) {
    return catalogGateway.loadProduct(productId);
}
```

When intercepted successfully by Spring Cache, the logical execution flow is:

```text
Caller
  |
  v
Spring bean proxy
  |
  +-- Compute cache key
  |
  +-- Cache.get(key) ----------------------> Redis
        |                                      |
        | cache HIT                            |
        +----> return stored value <-----------+
        |
        | cache MISS
        v
    Execute getProduct(...) on target
        |
        v
    catalogGateway.loadProduct(...) --> Source DB/API
        |
        v
    Cache.put(key, result) --------------> Redis
        |
        v
    Return result to caller
```

With Redis, a cache entry may use keys like `products::42`, depending on prefix settings, `KeyGenerator`, serializer, and cache name. Do not couple business logic to a guessed physical key name without confirming actual configuration.

There are two separate blocks:

- **Interceptor/proxy**: decides whether a method call consults the cache.
- **CacheManager/Cache**: executes reads/writes, e.g., via `RedisCacheManager` and `RedisCache`.

If a call **bypasses the proxy**, Redis may never be queried at all. In that situation, tweaking TTLs or changing Redis serializers will not fix the root cause.

## 3. Configuring Spring Cache with Redis in Spring Boot

Maven example with Spring Boot and Redis:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-cache</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
```

With Gradle:

```gradle
implementation 'org.springframework.boot:spring-boot-starter-cache'
implementation 'org.springframework.boot:spring-boot-starter-data-redis'
```

Configure the Redis connection in `application.yml`:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
```

Enable annotation caching in a configuration class:

```java
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheConfiguration {
}
```

Spring Boot can auto-configure `RedisCacheManager` when Redis and caching infrastructure are present, no other `CacheManager` takes precedence, and auto-configuration conditions match. **Adding the Redis dependency does not activate `@Cacheable` annotations if annotation-driven caching is not enabled**.

Basic TTL settings can be tuned via Spring Boot properties:

```yaml
spring:
  cache:
    type: redis
    redis:
      time-to-live: 10m
      cache-null-values: false
      use-key-prefix: true
```

This is a generic configuration example; property names, supported values, and precedence when customizing beans can vary with Spring Boot versions. When configuring a `RedisCacheManager` bean manually, apply policies directly on that bean.

For simple demonstrations without running Redis, you can swap in an in-memory cache manager to observe proxy mechanics. However, **conclusions about multi-instance load synchronization over Redis must be validated against real `RedisCache` and writer configurations**, never extrapolated from local memory.

## 4. Service example: a cached method

Consider the return object:

```java
package com.example.catalog;

import java.math.BigDecimal;

public record ProductDto(
    String id,
    String name,
    BigDecimal price
) {}
```

A gateway to the canonical data source:

```java
package com.example.catalog;

public interface CatalogGateway {
    ProductDto loadProduct(String productId);
}
```

`CatalogGateway` can be implemented using Spring Data JPA, JDBC, an HTTP API, or an internal service. This lesson does not depend on how it loads data.

Cached service:

```java
package com.example.catalog;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductLookupService {

    private final CatalogGateway catalogGateway;

    public ProductLookupService(CatalogGateway catalogGateway) {
        this.catalogGateway = catalogGateway;
    }

    @Cacheable(cacheNames = "products", key = "#productId")
    public ProductDto getProduct(String productId) {
        return catalogGateway.loadProduct(productId);
    }
}
```

A controller or another bean injecting `ProductLookupService`:

```java
package com.example.catalog;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/products")
public class ProductController {

    private final ProductLookupService productLookup;

    public ProductController(ProductLookupService productLookup) {
        this.productLookup = productLookup;
    }

    @GetMapping("/{id}")
    public ProductDto find(@PathVariable("id") String id) {
        return productLookup.getProduct(id);
    }
}
```

`productLookup.getProduct(id)` goes through the Spring-managed bean, normally a proxy wrapping `CacheInterceptor`. On a cache HIT, `getProduct`'s body never runs and `catalogGateway.loadProduct` is skipped.

In this example, SpEL key `#productId` depends on Spring resolving parameter name metadata. For expressions independent of parameter names, use `#p0` or `#a0` for the first parameter:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public ProductDto getProduct(String productId) {
    return catalogGateway.loadProduct(productId);
}
```

Parameter names in SpEL rely on compiler metadata and Spring's discovery settings; choosing `#p0` keeps examples independent of that configuration.

## 5. Spring AOP proxies operate at call boundaries

The default mode for cache annotations uses **proxies**. Spring creates or supplies an intermediary wrapper around the target bean. When a caller invokes a method via the proxy reference, Spring runs `CacheInterceptor` before/after delegating to the target.

```text
Path A — call from another bean:

ProductController
    |
    v
ProductLookupService proxy
    |
    +--> CacheInterceptor (@Cacheable)
    |       | hit -> return result
    |       | miss
    v       v
ProductLookupService target
    |
    v
CatalogGateway


Path B — self-invocation inside target:

ProductLookupService target
    |
    | this.getProduct(id)
    v
ProductLookupService target
    |
    +--> Bypasses CacheInterceptor
```

Depending on configuration, Spring uses **JDK dynamic proxies** (interface-based proxies) or **class-based proxies** (typically CGLIB). Both intercept calls arriving at the proxy wrapper. Proxying a class does not intercept calls routed directly via `this`.

### 5.1. Consequences of proxy mode

A cache-annotated method executes caching logic only when callers pass through the proper proxy. In standard proxy mode:

- **Public** methods invoked from external beans are the safest, most predictable pattern.
- Internal calls like `this.someMethod()` normally bypass the interceptor.
- Calls to **private** methods cannot be overridden/intercepted by standard class proxies.
- `final` methods on a class cannot be overridden by class-based proxies.
- Methods invoked in constructors or very early initialization phases may execute before proxies are wired as expected.
- Objects instantiated manually via `new` are not Spring-managed beans wrapped in cache proxies.
- Differences across JDK proxies, CGLIB, method visibility, interfaces, and Spring versions can affect edge cases. Design cached APIs as public methods on Spring-managed beans invoked externally.

Seeing an annotation in source code does not prove the interceptor runs. Inspect **the actual runtime call path**.

## 6. Self-invocation: the most common mistake

Consider this service:

```java
@Service
public class ProductService {

    private final CatalogGateway catalogGateway;

    public ProductService(CatalogGateway catalogGateway) {
        this.catalogGateway = catalogGateway;
    }

    public ProductDto checkoutProduct(String productId) {
        // The call here executes directly on the target object.
        return getProduct(productId);
    }

    @Cacheable(cacheNames = "products", key = "#p0")
    public ProductDto getProduct(String productId) {
        return catalogGateway.loadProduct(productId);
    }
}
```

Another bean calls:

```java
productService.checkoutProduct("p-42");
```

`checkoutProduct` carries no cache annotation. Once the proxy delegates to the target, `getProduct(productId)` executes internally on the target object itself. It **bypasses `getProduct`'s cache interceptor**.

Calling `checkoutProduct("p-42")` ten times can execute `catalogGateway.loadProduct` ten times despite `@Cacheable` on `getProduct`.

Meanwhile, a direct call from another bean:

```java
productService.getProduct("p-42");
```

passes through the proxy and caches as expected.

### 6.1. Call-path comparison table

| Call path | Passes through standard cache proxy? | Outcome |
|---|---|---|
| Controller injects service and calls `service.getProduct(id)` | Yes | `@Cacheable` can take effect |
| Bean A injects Bean B and calls `beanB.getProduct(id)` | Yes | `@Cacheable` can take effect |
| Within same bean calling `this.getProduct(id)` | No | Skips annotation on target method |
| Within same bean calling `getProduct(id)` | No | Still an internal call |
| Constructor calling a cached method | Do not rely on it | No stable proxy path yet |
| `@PostConstruct` calling a bean's own cached method | Do not rely on it | Often runs directly on target lifecycle |
| `new ProductService(...).getProduct(id)` | No | Object not managed by Spring |
| Calling a private `@Cacheable` method | Not safely supported in proxy mode | Annotation does not produce intended behavior |

Key takeaway: changing `getProduct(id)` to `this.getProduct(id)` **fixes nothing**. Both target the underlying object directly.

### 6.2. Why does the cache sometimes appear populated anyway?

A Redis key might exist because another proxy-routed call, a prewarm job, an earlier test, or a different instance created it. Seeing a key in Redis **does not prove** the self-invoking path uses the cache.

To diagnose properly, measure how many times the source-loading method runs along each code path. One HTTP endpoint may hit Redis while a background job calling internally bypasses the cache completely.

## 7. Preferred fix: move cached methods into another bean

The cleanest fix places cached methods in a dedicated bean injected wherever needed.

Cached reader service:

```java
package com.example.catalog;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CachedProductReader {

    private final CatalogGateway catalogGateway;

    public CachedProductReader(CatalogGateway catalogGateway) {
        this.catalogGateway = catalogGateway;
    }

    @Cacheable(cacheNames = "products", key = "#p0")
    public ProductDto getProduct(String productId) {
        return catalogGateway.loadProduct(productId);
    }
}
```

Orchestrating service:

```java
package com.example.catalog;

import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final CachedProductReader cachedProducts;

    public CheckoutService(CachedProductReader cachedProducts) {
        this.cachedProducts = cachedProducts;
    }

    public ProductDto prepareCheckout(String productId) {
        ProductDto product = cachedProducts.getProduct(productId);
        // Remaining business steps.
        return product;
    }
}
```

New flow:

```text
CheckoutService target
        |
        | calls injected bean
        v
CachedProductReader proxy
        |
        v
CacheInterceptor
        |
        +-- HIT --> return ProductDto
        |
        +-- MISS -> CatalogGateway -> write Redis -> return ProductDto
```

**Benefit:** the cache boundary becomes architecturally explicit. The orchestrating bean need not know whether proxies or Redis sit underneath; it simply calls a public dependency.

This also simplifies testing: tests verify routing through `CachedProductReader` instead of fighting opaque internal invocation behavior.

### 7.1. Bean separation and responsibilities

You do not need a separate class for every single method. Splitting beans makes sense when methods share a clear responsibility, such as:

- `CachedProductReader` handling cached reads.
- `ProductWriteService` handling source updates.
- `CheckoutService` coordinating business workflows.

Multiple read methods sharing a read contract and caching policy can live together inside one reader bean. The goal is **routing calls through a Spring bean proxy**, not proliferating classes unnecessarily.

## 8. Other fixes and their limitations

### 8.1. Self-injecting your own proxy

Some projects inject a self-proxy or `ObjectProvider`:

```java
@Service
public class ProductService {

    private final ObjectProvider<ProductService> selfProvider;

    public ProductService(ObjectProvider<ProductService> selfProvider) {
        this.selfProvider = selfProvider;
    }

    public void process(String id) {
        selfProvider.getObject().getProduct(id);
    }

    @Cacheable(cacheNames = "products", key = "#p0")
    public ProductDto getProduct(String id) {
        // Load from source.
        return null;
    }
}
```

This **illustrates the mechanism**, not a recommended default. Self-injection couples business code tightly to Spring's proxy lifecycle and risks circular dependencies or discrepancies between JDK and class proxies. Never enable circular reference flags solely to "fix" self-invocation.

Evaluate architectural reasons before insisting on a single bean; extracting a reader/service is clearer in most cases.

### 8.2. `AopContext.currentProxy()`

Spring AOP can expose the current proxy when configured to do so, letting code call `AopContext.currentProxy()` instead of `this`. However, this depends on AOP configuration, thread scoping, and whether the outer call is currently inside a proxied invocation.

This couples business logic directly to Spring AOP and breaks easily during refactoring or configuration changes. Avoid using it as your first resort for self-invocation.

### 8.3. AspectJ weaving

Spring Cache supports `ASPECTJ` advice mode when properly configured and woven. With AspectJ, advice is woven into bytecode so self-invocation can be intercepted.

However, it requires specific dependencies and compile-time or load-time weaving, introducing differences in classloaders, builds, operations, and annotation discovery. Setting `mode = AdviceMode.ASPECTJ` alone **does not enable full weaving**.

Reserve AspectJ for applications already relying on weaving across many cross-cutting concerns. For ordinary method caching, bean extraction remains simpler to understand and maintain.

## 9. Common proxy limitations

| Situation | Why errors occur easily | Design guidance |
|---|---|---|
| `@Cacheable` on `private` method | Proxies do not intercept private calls as external APIs | Make cached methods public on a dedicated bean |
| `@Cacheable` on `final` method | Class-based proxies cannot override final methods | Remove `final` if appropriate, or move cache boundary |
| `final` class under class proxy mode | CGLIB cannot subclass final classes | Use interface/JDK proxies or adjust bean structure |
| Self-invocation on same object | Bypasses proxy | Extract bean / call via dependency |
| Object created with `new` | Lacks Spring proxy | Use Spring-managed beans |
| Self-calling inside `@PostConstruct` | Does not pass through external bean proxy | Trigger from orchestrating bean via dependency at proper lifecycle |
| Missing `@EnableCaching` | Caching annotation infrastructure inactive | Enable caching in configuration |
| Calling non-interface method with JDK proxy | Proxy exposes only interface methods | Inject via proper interface or adjust proxy strategy |
| Annotation placed on interface under incompatible mode | Annotation detection rules differ | Place annotations clearly on implementation methods |
| Kotlin classes/methods final by default | Class proxies struggle to override | Configure all-open plugin or design interfaces |

Spring behavior around intercepting non-public methods varies across versions and proxy modes. Therefore, prefer **public methods on Spring beans called externally** to avoid corner-case dependencies.

### 9.1. Why doesn't proxyTargetClass fix self-invocation?

Enabling class-based proxies:

```java
@EnableCaching(proxyTargetClass = true)
```

selects class-based proxying where applicable. It does **not** route `this.cachedMethod()` inside the target back through the proxy. If the bug is self-invocation, switching from JDK proxies to CGLIB only changes proxy technology without changing call boundaries.

## 10. Same method called from different application entry points

Applications often have multiple entry paths:

```text
HTTP Controller -------+
                       |
Scheduled Job ---------+--> ProductService
                       |
Message Listener ------+
```

If all three inject `CachedProductReader` and call `reader.getProduct(id)`, the cache interceptor works across all paths.

If the scheduled job sits inside `ProductService` and calls `getProduct` internally while the controller calls through the proxy, you get:

```text
HTTP request    -> cache HIT
Scheduled job   -> bypasses cache, always queries source
Message handler -> cache HIT
```

Looking solely at global Redis hit rates makes it hard to tell why database load remains high. Track source load counts per endpoint/job or call path.

**Self-invocation also bypasses `@Cacheable(sync = true)`**: if the annotation is not intercepted, its loading-synchronization intent never runs either.

## 11. Concurrent cache misses and cache stampede

Suppose `products::p-42` expires and 100 requests call `getProduct("p-42")` within a tiny window.

If every request sees a cache MISS and runs the loader:

```text
Time  Request A    Request B    Request C       ... Request 100
----  ----------   ----------   -------------       ------------
t0    GET -> MISS  GET -> MISS  GET -> MISS          GET -> MISS
t1    DB load      DB load      DB load             DB load
t2    SET cache    SET cache    SET cache           SET cache
t3    respond      respond      respond             respond
```

One cache miss turns into dozens or hundreds of canonical database/API calls. This is a **cache stampede**, also called a thundering herd when requests surge into the source after cached data disappears.

Risk grows when:

- The key is very hot.
- The loader is slow, e.g., calling a high-latency API.
- Many keys share the same TTL and expire simultaneously.
- The application runs many instances or high concurrency.
- Redis restarts, or caches start empty after deploy/invalidation.
- Not-found results are not cached, causing repeated misses on nonexistent IDs.
- Redis outages force traffic directly onto the source.

Stampede mitigation works at multiple layers. Begin by quantifying **how many concurrent requests hit the same key** and **how many instances** invoke loaders.

## 12. What does `@Cacheable(sync = true)` mean?

Spring Cache allows:

```java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    sync = true
)
public ProductDto getProduct(String productId) {
    return catalogGateway.loadProduct(productId);
}
```

Per the Spring Cache contract, `sync = true` **asks the cache provider to synchronize value computation for the same cache key on a miss**. Instead of letting every thread execute the loader, the cache can coordinate so one thread computes the value while others receive the populated result.

Intended flow:

```text
Concurrent requests for key "p-42"
             |
             v
      Cache.get(key, loader)
             |
             +--> Thread A: runs loader and stores value
             |
             +--> Thread B: waits/coalesces on load
             |
             +--> Thread C: waits/coalesces on load
             |
             v
     All requests receive matching result
```

Spring Cache expresses this via `Cache.get(key, Callable<T> valueLoader)` or the provider's equivalent mechanism. **Actual synchronization capability is determined by the `Cache` implementation**.

### 12.1. `sync = true` does not make the method Java synchronized

The annotation is not equivalent to:

```java
public synchronized ProductDto getProduct(String id) { ... }
```

`synchronized` locks the object's monitor inside a single JVM with no awareness of cache keys; calls for completely different IDs block one another. By contrast, `sync = true` requests coordinating **cache value loading**, typically on cache misses and implemented as chosen by the provider.

Nor does `sync = true` imply a **distributed lock** resilient to crashes, timeouts, failovers, and fencing across an entire Redis Cluster. Check your application's `RedisCache` implementation and writer configuration.

### 12.2. Annotation constraints when `sync=true`

Spring Cache documents explicit restrictions on `@Cacheable(sync = true)`:

- Only **one cache** may be specified on synchronized-loading methods.
- `unless` cannot be used with `@Cacheable(sync = true)`.
- Do not combine the method with conflicting cache operations.
- The cache implementation must support synchronized value computation; otherwise outcomes or errors vary by provider/version.

Unsuitable example:

```java
@Cacheable(
    cacheNames = {"products", "productBackup"},
    key = "#p0",
    sync = true
)
public ProductDto load(String id) { ... }
```

because synchronized loading only supports a single cache in the annotation contract.

Another example:

```java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    sync = true,
    unless = "#result == null"
)
public ProductDto load(String id) { ... }
```

`unless` is unsupported when `sync = true`. If null caching must be prevented, check your cache manager/provider's null-caching configuration and evaluate how it interacts with synchronization.

### 12.3. Exceptions in the loader

When the loader fails, the cache must not turn that error into a bogus successful value. Callers receive the exception or failure response per cache/provider semantics. A key whose loader repeatedly fails can keep triggering fresh misses.

Handle:

- Data source timeouts.
- Bounded retries with backoff.
- Never conflating Redis errors with "product not found."
- Never caching/logging sensitive exceptions as valid payloads.
- Adding fallbacks or circuit breakers at the right layer for unstable sources.

Never treat `sync = true` as a substitute for loader error handling.

## 13. Single-JVM vs. multi-instance synchronization

Consider two deployment topologies.

### 13.1. Single application instance

```text
            JVM A
   Thread 1  Thread 2  Thread 3
       \        |        /
        \       |       /
         CachedProductReader proxy
                   |
              RedisCache
                   |
           Redis / database
```

If the provider supports synchronized cache loading per key, threads inside one JVM can avoid redundant loader invocations. Verify this against the concrete `CacheManager` implementation and configuration.

### 13.2. Multiple application instances sharing Redis

```text
       Application A                  Application B
       Thread A1, A2                  Thread B1, B2
             |                               |
       Cache interceptor                Cache interceptor
             |                               |
             +------------ Redis ------------+
                            |
                          MISS
                            |
               +------------+------------+
               |                         |
       A queries data source     B queries data source
               |                         |
               +------------> write Redis <+
```

Both instances can observe the miss almost simultaneously and call the data source. A local Java lock in Instance A **cannot stop** Instance B from running its loader.

`@Cacheable(sync = true)` with Redis **does not by itself prove** only one instance system-wide runs the loader. Actual guarantees depend on `RedisCache`, `RedisCacheWriter`, the chosen lock mechanism, and error/timeout handling.

### 13.3. Scope comparison table

| Solution | Coordination scope | Limitations |
|---|---|---|
| `synchronized` on Java method | Threads sharing one object monitor in one JVM | Key-unaware; cannot coordinate across instances |
| Local `ConcurrentHashMap` single-flight | Typically per-JVM, per-key | Does not coordinate across JVMs |
| `@Cacheable(sync = true)` | Cache provider's synchronized loading contract | Implementation-dependent; not a durable distributed lock by default |
| Redis locking cache writer | Locking mechanism at `RedisCacheWriter` layer per config/version | Watch lock granularity, latency, and failure modes |
| Application distributed lock | Can coordinate multiple instances if designed carefully | Requires lock TTL, ownership, retries, fencing, network failure handling |
| Prewarm/stale-while-revalidate/TTL jitter | Reduces or spreads out cache misses | Not a transaction or strict mutex |

This table underscores that caching targets **reducing average load**, whereas guaranteeing "strictly one computation per key across all instances under any failure" is a far stronger distributed systems commitment.

## 14. RedisCacheWriter: non-locking vs. locking

In Spring Data Redis, `RedisCacheManager` uses `RedisCache` and `RedisCacheWriter` to talk to Redis. A common default is **non-locking writer**, prioritizing throughput and avoiding lock wait overhead on cache operations.

Spring Data Redis also provides a **locking writer**. When selected, certain cache operations can acquire locks to prevent overlap per writer design. However:

- Lock scope in implementations can be **cache-wide**, broader than a single cache key.
- Unrelated keys may wait on one another during certain operations.
- Do not infer from the name `lockingRedisCacheWriter` that fair locks, fencing tokens, full network fault protection, or distributed exactly-once semantics exist.
- Exact behavior with `@Cacheable(sync = true)`, `get(key, loader)`, multi-step commands, and lock timeouts must be verified for your active **Spring Data Redis and driver version**.
- Broad writer locking can sharply reduce throughput under heavy load even when intended only to curb stampedes.

An example configuration when an application intentionally chooses a locking writer using supported APIs:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.cache.RedisCacheWriter;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
public class RedisCacheWriterConfiguration {

    @Bean
    RedisCacheManager cacheManager(RedisConnectionFactory connectionFactory) {
        RedisCacheWriter writer =
            RedisCacheWriter.lockingRedisCacheWriter(connectionFactory);

        return RedisCacheManager.builder(writer)
            .cacheDefaults(RedisCacheConfiguration.defaultCacheConfig())
            .build();
    }
}
```

This snippet illustrates selecting a writer, not that it is optimal for every workload. Declaring a custom `RedisCacheManager` bean also alters how Boot auto-configuration applied previously; if TTL, serializers, or prefixes are required, configure them on `RedisCacheConfiguration`.

**Before enabling a locking writer:** confirm you actually suffer from stampedes, verify lock granularity, measure contention, and benchmark p95/p99 latency. Turning on locks unmeasured can swap "too many loaders" for "too many blocked requests."

## 15. `sync = true` is not a Redis transaction and does not replace atomic updates

`@Cacheable(sync = true)` coordinates **computing a cache value on a miss**. It does not turn business read/modify/write sequences into transactions.

Concurrency-unsafe example:

```java
@Cacheable(cacheNames = "accountBalances", key = "#p0", sync = true)
public long readBalance(String accountId) {
    return accountRepository.readBalance(accountId);
}
```

The annotation can reduce source reads for the same key, yet **does not prevent two business transactions from updating balances concurrently** or keep caches strictly synchronized with the database.

For counters, balances, quotas, or inventory, build atomic updates inside the owning data store. Caches merely accelerate reads; synchronizing cache misses never replaces optimistic locking, transactions, or Redis atomic commands on canonical data.

Likewise:

- `@Cacheable` does not open `MULTI`/`EXEC`.
- `sync = true` does not turn multi-key sequences on Redis Cluster into cross-slot transactions.
- Writer locks reduce cache-operation overlap without enforcing business consistency in the database.
- Results loaded and placed into Redis can turn stale moments later if source data changes.

## 16. `@CachePut`, `@CacheEvict`, and proxy call paths

Caching is not only about reads. When source data changes, applications need policies to refresh or evict stored entries.

### 16.1. `@CacheEvict`: deleting cached values

Example:

```java
@Service
public class ProductWriteService {

    private final CatalogGateway catalogGateway;

    public ProductWriteService(CatalogGateway catalogGateway) {
        this.catalogGateway = catalogGateway;
    }

    @CacheEvict(cacheNames = "products", key = "#p0")
    public void updateProduct(String productId, ProductDto newValue) {
        catalogGateway.updateProduct(productId, newValue);
    }
}
```

This is an API example: `CatalogGateway` would also define `updateProduct(...)` in real usage.

`@CacheEvict` likewise relies on proxies in standard mode. If another method in the same class calls `this.updateProduct(...)` directly, it can **skip eviction**, leaving stale data in the cache.

### 16.2. `@CachePut`: run method then update cache

```java
@CachePut(cacheNames = "products", key = "#result.id")
public ProductDto refreshProduct(String productId) {
    return catalogGateway.loadProduct(productId);
}
```

Unlike `@Cacheable`, `@CachePut` normally **always executes the method body** and puts the result into the cache. Use `@CachePut` when the goal is refreshing cache entries, not bypassing source loads.

Internal calls bypassing proxies also bypass `@CachePut`.

### 16.3. Eviction and loader races

Suppose:

```text
t1: Thread A observes MISS and begins loading old product.
t2: Thread B updates product in DB, then evicts cache.
t3: Thread A finishes and puts old product into cache.
```

After `t3`, the cache can contain stale data despite `t2`'s eviction. `@CacheEvict` or `sync = true` alone does not always prevent races between concurrent loads and source mutations.

When freshness is critical, add consistency mechanisms such as versioned cache keys, conditional invalidation, versioned reads, or source-level version checks. For read-acceleration caches tolerating brief staleness, a low TTL may suffice.

### 16.4. Database transactions and caching

When an update method participates in a transaction, cache eviction timing relative to database commit matters greatly. Designs often defer eviction until after commit or use a transaction-aware cache manager/coordinator.

Never assume `@Transactional` on a service makes Redis cache and the database commit atomically together. When the database is the source of truth, align invalidation policies with transactions and consistency requirements.

## 17. Special cases that cause repeated cache misses

### 17.1. Null value caching

If the loader often returns `null` for nonexistent products and Redis cache **does not store nulls**, every request for that ID misses and hits the database.

Example:

```java
@Cacheable(cacheNames = "products", key = "#p0", sync = true)
public ProductDto getProductOrNull(String id) {
    return catalogGateway.loadProduct(id);
}
```

If the cache manager disallows nulls, check null handling alongside provider synchronization. `sync = true` forbids combining `unless = "#result == null"` as a null-exclusion workaround.

Consider changing the API to return a meaningful non-null absence value, or use negative caching with a short TTL. Keep in mind caching "not found" too long hides newly created products.

### 17.2. Inconsistent cache keys

Two expressions:

```java
@Cacheable(cacheNames = "products", key = "#p0")
```

and

```java
@Cacheable(cacheNames = "products", key = "'product:' + #p0")
```

produce two distinct cache keys and fail to share entries for the same product ID.

Similarly, `getProduct("42")`, `getProduct("042")`, and `getProduct(" 42 ")` create three separate keys unless IDs are canonicalized. Key-based synchronization helps only when every call for an entity resolves to the exact same key.

### 17.3. TTL too short

If TTL is 1 second while the loader takes 3 seconds, requests continuously miss. Balance TTL against data volatility and source latency.

### 17.4. Evicting `allEntries` too frequently

```java
@CacheEvict(cacheNames = "products", allEntries = true)
public void clearProductCache() { }
```

Called frequently, many hot keys vanish together and concurrent requests flood the source. In Redis, clearing an entire region also incurs key scanning or deletion costs depending on writer settings.

Avoid global evictions to fix single-product updates when targeted key eviction is possible.

### 17.5. Non-serializable results or wrong serializers

With `RedisCache`, return values must convert cleanly to bytes via the configured serializer. If a DTO fails serialization/deserialization, cache operations fail even though the proxy intercepted the call.

Distinguish clearly:

- **Not intercepted**: loader ran because the call bypassed the proxy.
- **True cache MISS**: key absent or TTL expired.
- **Cache read/write error**: Redis connection, serializer, or permission failure.
- **Key mismatch**: same entity yielded different keys.
- **Cache manager mismatch**: method used a different provider or cache name than expected.

Each category requires a different fix.

## 18. Mitigating cache stampedes beyond sync=true

No single technique fits every workload. Combine strategies as needed.

### 18.1. Prewarming hot data

Before heavy traffic arrives, proactively load a set of hot keys. Prewarming can call through an injected Spring bean to populate `@Cacheable`, or call the cache manager API directly.

If a prewarm job calls `this.getProduct()` on the same bean, it may bypass the proxy. Verify the call path.

### 18.2. TTL jitter to avoid simultaneous expirations

If all entries are created together with identical TTLs, vast batches expire at the same instant. Varying TTLs across a controlled range spreads source load.

Logical example:

```text
Base TTL:   600 seconds
Actual TTL: approx. 540 to 660 seconds per entry
```

Numbers are illustrative. Spring Data Redis `RedisCacheConfiguration` offers version-dependent TTL options; per-entry dynamic TTL requires APIs supported by your version or custom cache logic. Never assume a static YAML `time-to-live` property adds jitter automatically.

### 18.3. Stale-while-revalidate

If brief staleness is tolerable, serve acceptable stale values immediately while scheduling a bounded background refresh.

Pattern:

```text
Request for hot key
     |
     +-- value fresh: return immediately
     |
     +-- value stale yet within grace window:
     |       return stale value
     |       schedule bounded async refresh
     |
     +-- no usable data:
             wait for loader or use fallback
```

This is an **additional design pattern**, not default `@Cacheable` behavior with `RedisCacheManager`.

### 18.4. Application-level per-key single-flight

Within a single JVM, an application can track in-flight loads per key so concurrent callers share one `Future` or result from a single load. Useful when providers lack desired coalescing or loads occur outside Spring Cache.

Remember to clean up entries once the future completes, propagate errors cleanly, cap pending keys, and never retain failed futures forever. Local single-flight does not coordinate across instances.

### 18.5. Distributed locks when multi-instance coordination is truly required

If a hot key is extremely costly to compute, use a dedicated per-key distributed lock, e.g.:

```redis
SET lock:product:p-42 <unique-owner-token> NX PX 30000
```

Only the lock-winning instance loads; others wait briefly, re-check cache, or fall back. Correct implementation requires:

- Lock keys derived identically to cache keys.
- Unique ownership tokens and **token-verified deletion** to avoid releasing another request's lock.
- Lock TTL matching load duration, plus handling stalled loaders, timeouts, and failovers.
- Jittered, bounded retry/wait loops to prevent request storms.
- Re-checking cache after acquiring the lock in case another instance already populated it.
- Considering fencing/versions when strict correctness is needed; an expired Redis lease does not stop an old slow worker from writing later.

Distributed locks add operational complexity. For routine cache load reduction, start with provider-appropriate `sync = true`, prewarming, sensible TTLs, and metrics.

### 18.6. Limiting concurrent source loads

Use semaphores, bulkheads, rate limiters, or queues to bound concurrent requests reaching the canonical backend on misses. This protects the source from collapse even without strict single-flight guarantees.

Whenever throttling, enforce deadlines, timeouts, and clear error/fallback responses; never let requests queue indefinitely.

## 19. Comparing three common scenarios

| Scenario | Symptom | Core cause | Remediation |
|---|---|---|---|
| `@Cacheable` method still hits DB on internal calls | Low hit rate on a specific path | Self-invocation bypasses proxy | Move cached method to another bean |
| Concurrent requests hit one newly expired key | Multiple loader calls despite proxy interception | Concurrent cache misses | `sync = true` if supported, single-flight, prewarm |
| Two instances both query source for same key | Redundant loads across JVMs | Lack of cross-JVM coordination | Inspect Redis writer; add distributed strategy if needed |
| Many keys expire in the same minute | Periodic DB load spikes | Synchronized TTL expiration | TTL jitter, prewarm, bounded refresh |
| Cache stops updating after mutation | Serves stale data | Eviction bypassed proxy or raced loader | Extract write service, handle invalidation timing |
| Key exists in Redis yet method still hits source | Bypassed call, key mismatch, wrong manager, or error | Unidentified gap | Inspect proxy, keys, hit/miss stats, and serializer |

This table highlights how "cache seems ineffective" can stem from **two completely different layers**: Java calls not being intercepted vs. concurrent miss handling in the cache provider.

## 20. Observing to diagnose accurately

### 20.1. Count source invocations

In a controlled environment, attach a metric or counter inside `CatalogGateway.loadProduct`. Then invoke the same ID repeatedly.

Interpret outcomes:

```text
Calls through proxy, cache HIT:
    source loads roughly match cache misses.

Calls self-invoking target:
    source loads may roughly equal total method calls.

Concurrent requests:
    source loads may exceed missed cache keys
    without appropriate coalescing.
```

Useful metrics: cache hits/misses (when supported by provider/instrumentation), gateway call counts per key/group, source latency, Redis read/write errors, loader duration, and concurrent load counts.

### 20.2. Inspect keys in Redis

With cache name `products`, default prefix, and simple string keys, keys look roughly like:

```text
products::p-42
```

Actual keys depend on prefixes and serializers. In development, after calling the service through its proxy, inspect Redis with management tools or the CLI.

On Redis instances with many keys, use `SCAN` rather than running `KEYS *` blindly in production. Binary serializers produce output that is not human-readable.

### 20.3. Confirm a bean is proxied

In developer diagnostics, check:

```java
import org.springframework.aop.support.AopUtils;

boolean proxied = AopUtils.isAopProxy(productLookupService);
```

Receiving `true` proves the object is an AOP proxy, **not that every method has cache advice**. Still verify annotation detection, call paths, and the active cache manager.

Calling `this.getProduct(id)` still bypasses the proxy even when the outer bean is wrapped.

### 20.4. Testing through ApplicationContext

With proxy-based caching, unit tests constructing objects directly via `new` or `@InjectMocks` cannot demonstrate Spring Cache behavior. To test annotations, obtain **beans from a Spring `ApplicationContext`** with caching enabled and an appropriate cache manager.

A behavioral test can:

1. Call `cachedProductReader.getProduct("p-42")` twice through the Spring bean.
2. Record `CatalogGateway` invocation count.
3. Expect the loader ran once if the entry cached and did not expire.
4. Invoke the broken self-invocation example and observe the loader running again.
5. After separating beans, re-run via the orchestrating path and confirm caching works.

These are lab testing instructions, not a mandate to execute tests for this Markdown document.

## 21. Analyzing concurrency with a concrete scenario

Suppose three application instances—A, B, and C—each serve 100 requests/second for product `p-42`. Cache TTL is 60 seconds and database loading takes 800 ms.

When the entry expires:

```text
t0:
    Redis lacks products::p-42.

t0 + 10ms:
    A sees many concurrent MISSes.
    B sees many concurrent MISSes.
    C sees many concurrent MISSes.

t0 + 20ms:
    Without coalescing:
        many threads on A, B, and C start DB queries.

t0 + 800ms:
    some loaders finish and write to Redis.

Afterward:
    new requests HIT,
    yet previously started loaders still consume resources.
```

If `sync = true` works within each instance without **cross-instance coordination**, there can still be at least one load on A, one on B, and one on C. If a writer coordinates across instances via a suitable mechanism, total loads may drop further; verify exact writer behavior and error cases.

Coalescing benefit scales with **the length of the cache-miss window**. Slower loaders expose more concurrent requests to MISSes. If strict guarantees against ever computing a value twice are mandatory, the solution goes far beyond an annotation attribute.

### 21.1. Why adding instances doesn't automatically curb stampedes

Scaling from 3 to 10 instances increases request capacity yet also increases concurrent misses and competing loaders. Shared Redis shares **already-written values**; it does not automatically synchronize computation **before the cache is filled**.

### 21.2. Even with locks, staleness can still occur

Another race:

```text
t1: Loader A acquires lock and begins reading source data.
t2: Source data is updated.
t3: Another thread evicts the key.
t4: Loader A writes its stale result into cache.
```

Locks protecting cache loading do not serialize against transactions updating the source. When strong consistency is required, add versioning or source-coordinated cache updates/evictions.

## 22. Combining caching with @Async, @Transactional, and lifecycle hooks

Spring provides multiple AOP-driven features. When a method combines `@Cacheable` with `@Async` or `@Transactional`, remember:

- Calls must go through the appropriate proxy for all advice to apply.
- Self-invocation can drop **multiple advice layers at once**, not only caching.
- Advice ordering and execution threads affect runtime behavior.
- Newer Spring and provider releases include dedicated support for async/reactive return types; do not assume every `CompletableFuture` or reactive publisher synchronizes and caches identically to ordinary objects.

Example NOT to use to verify caching:

```java
@PostConstruct
public void initialize() {
    getProduct("p-42"); // Self-call; likely bypasses cache proxy.
}
```

Move prewarming into an orchestrating bean triggered after dependent beans finish initialization, calling the injected `CachedProductReader`. Choose lifecycle hooks matching startup requirements.

With `@Transactional`, check whether entries get evicted before database commit or on rollback. Never treat stacking annotations as an atomic consistency guarantee across Redis and the database.

## 23. Common issues and troubleshooting

### "@Cacheable is on the method, yet the database is called every time"

Check `@EnableCaching`, Spring-managed bean status, `public` visibility, external bean calls, and the exact annotated method. Hunt down self-invocation before changing serializers or TTLs.

### "Enabled proxyTargetClass=true, yet this.method() still doesn't cache"

Class-based proxies do not intercept internal calls. Move the cached method to a separate bean or consider weaving if truly justified.

### "Set sync=true, yet multiple requests still hit the source"

Verify calls are intercepted; next inspect the cache provider, `RedisCacheWriter`, instance count, and loader behavior. Verify keys truly match and TTL is sufficiently long.

### "sync=true cannot be combined with unless"

This is a Spring Cache synchronized-loading constraint. Configure provider null-caching policy or adjust return contracts per business rules.

### "Adding app replicas caused DB load spikes on TTL expiration"

Multiple instances can miss simultaneously. Measure cross-node loaders and apply prewarming, jitter, appropriate locks, or concurrent-load limits.

### "An entire cache slowed down after enabling locking writer"

Writer locks may lock more broadly than a single entry and cause contention. Inspect version behavior, latency, hot keys, and concurrency; narrow locking scope if appropriate.

### "@CacheEvict fails to delete keys after updates"

The update may be called internally, bypass proxies, or mismatch cache name/key. It could also be a loader racing an eviction and writing stale data back.

### "Annotations do nothing in tests"

Verify tests use beans from a Spring `ApplicationContext` rather than objects created via `new`/Mockito. AOP annotations never execute on unproxied objects.

### "First call returns null, and subsequent calls keep hitting backend"

Check null-caching configuration and how loaders represent missing data. Distinguish valid absence from backend/serializer exceptions.

### "Cache returns stale data after updates"

Inspect TTLs, key design, eviction strategy, commit ordering, and loader-writer races. `sync=true` does not synchronize the canonical data source.

## 24. Practice exercises

### Exercise 1: Demonstrate self-invocation

Create a service:

```java
@Service
public class DemoService {

    private final SlowGateway gateway;

    public DemoService(SlowGateway gateway) {
        this.gateway = gateway;
    }

    @Cacheable(cacheNames = "demo", key = "#p0")
    public String load(String id) {
        return gateway.fetch(id);
    }

    public String loadInside(String id) {
        return load(id);
    }
}
```

Execute via a Spring bean:

1. Call `demoService.load("x")` twice; observe `gateway.fetch` call count.
2. Call `demoService.loadInside("y")` twice; observe `gateway.fetch` call count.
3. Explain why the two paths differ.
4. Extract `load` into `CachedDemoReader`, inject it into `DemoService`, and re-test `loadInside`.
5. Compare source call counts after extracting the bean.

### Exercise 2: Same cache key vs. two different keys

Using:

```java
@Cacheable(cacheNames = "demo", key = "#p0", sync = true)
public String load(String id) {
    return gateway.fetch(id);
}
```

Have multiple threads call `"x"` concurrently while another group calls `"y"`. Contrast per-key coalescing against locking the entire method. Observe `fetch` counts and wait times under your active cache provider.

### Exercise 3: Testing sync=true against Redis

Using the application's real `RedisCacheManager`:

1. Evict the test cache entry.
2. Have multiple threads within one instance request the same key concurrently.
3. Count how many times the loader runs.
4. Repeat across two instances sharing Redis.
5. Document your exact Spring Data Redis version and writer configuration.
6. Compare loader counts, latency, and Redis error logs before drawing conclusions on synchronization scope.

### Exercise 4: Synchronized TTL expirations

Prepare 100 hot keys with identical TTLs. Drive steady traffic and observe source load spikes once TTL expires. Design TTL jitter or grouped prewarming and predict the impact on peak load.

### Exercise 5: Bypassed eviction

Write a bean with a `@CacheEvict` `updateProduct` method, then call it from another method in the same bean. Observe whether stale data remains cached. Move the update to another bean or call via proxy and compare.

### Exercise 6: Loader vs. update race

Simulate a loader reading stale data and pausing before writing to cache while a concurrent update modifies the source and evicts. Trace the interleaving causing stale data to reappear. Propose versioned keys or version checks on cache publish if business rules forbid staleness.

## 25. Self-assessment questions

1. Why can a `@Cacheable` annotation on a `public` method fail to execute?
2. Does replacing `getProduct(id)` with `this.getProduct(id)` solve self-invocation?
3. Why does a Spring AOP-proxied bean not guarantee every call to every method gets intercepted?
4. At which layer does `@Cacheable(sync = true)` synchronize, and which components determine its behavior?
5. Why can multiple instances sharing Redis still query the database simultaneously on a cache miss?
6. Is a locking `RedisCacheWriter` a per-key mutex guaranteeing exactly-once execution across all failures?
7. When should you use prewarm, TTL jitter, single-flight, or distributed locks?
8. Why can `@CacheEvict` miss invalidations or still let stale data reappear?
9. Why are unit tests using `new MyService(...)` insufficient to verify cache annotations?
10. If you only need fast reads, why shouldn't `sync=true` replace transactions when updating account balances?

## 26. Takeaways

- Spring Cache in proxy mode intercepts only calls **passing through the Spring AOP proxy**. `this.method()` on the same target typically bypasses `@Cacheable`, `@CachePut`, `@CacheEvict`, and accompanying `sync=true`.
- The most maintainable fix is **extracting cached methods into an injected bean** and calling it through an explicit dependency.
- JDK proxies, CGLIB, `proxyTargetClass`, `final`, `private`, `@PostConstruct`, and `new`-instantiated objects are prime suspects when annotations fail to fire.
- `@Cacheable(sync = true)` is a **cache-value loading synchronization hint** sent to the provider. It does not become an absolute distributed lock across all Redis-backed instances.
- A single Redis cache miss can trigger many concurrent source loads; understand **cache stampedes**, loader duration, hot keys, and TTLs.
- Non-locking vs. locking `RedisCacheWriter` carry distinct trade-offs. Choosing a locking writer requires checking lock scope, library version, and contention under load.
- To mitigate stampedes, combine synchronized loading, TTL jitter, prewarming, stale-while-revalidate, local single-flight, or properly engineered distributed locks when needed.
- Cache loading synchronization **never replaces transactions, canonical source protections, or invalidation strategies**.
- When diagnosing, count real loader executions, trace proxy call paths, check cache keys, Redis hits/misses, serializers, TTLs, and instance counts.

### Official references

- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html)
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Boot — Caching](https://docs.spring.io/spring-boot/reference/io/caching.html)
- [Redis — EXPIRE](https://redis.io/docs/latest/commands/expire/)
