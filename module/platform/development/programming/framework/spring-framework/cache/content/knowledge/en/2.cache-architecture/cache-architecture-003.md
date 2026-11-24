# CacheResolver and Selecting Caches per Operation in Spring Framework

## 1. Why Select Caches per Operation?

Spring Cache separates **business logic** from **where temporary results are stored**. The same product lookup method may need different caches depending on user group, tenant, data region, or time-to-live (TTL) policy. Selecting the wrong cache can cause two groups to read each other's data; if read and update operations select different caches, stale records may persist even after an update.

For example: the same product ID 42 has different display data for PUBLIC and VIP users. We want calls to `find(PUBLIC, 42)` to access `catalogPublic`, and `find(VIP, 42)` to access `catalogVip`. When updating or evicting the cache, the corresponding operation must resolve the same storage region as the read operation.

**Distinguish two tasks:**
- *Which cache to pick?* Decided by `CacheResolver` or the cache name configuration + `CacheManager`.
- *Which entry inside the cache?* Decided by the cache key, usually via `key`/`keyGenerator`.

Different caches do not mean different keys. Two separate caches can both hold key `42` without colliding; conversely, if multiple tenants are placed into one shared cache, the key must include the tenant identity.

## 2. Components and Mechanism

| Component | Role |
| --- | --- |
| `Cache` | A storage region of key/value pairs; API includes `get`, `put`, `evict`, `clear`. |
| `CacheManager` | Manages and returns a `Cache` via `getCache(name)`. |
| `CacheResolver` | Receives the context of the **intercepted invocation** and determines one or more `Cache` instances to use. |
| `KeyGenerator` or `key` expression | Generates the key for the entry **inside** the selected cache. |
| `@EnableCaching` and Spring AOP | Enables processing of cache annotations when calls go through a Spring proxy. |

Conceptual flow:

```text
Client -> Spring proxy -> identify cache operation
                       -> resolve cache(s) by config or actual invocation
                       -> determine key and conditions
                       -> @Cacheable: check cache; on miss, run method and store result
                       -> @CachePut: run method then write result to cache
                       -> @CacheEvict: delete entry / entire cache per policy
```

This is a functional diagram, not a fixed detailed execution order for every condition and provider.

Core interface:

```java
@FunctionalInterface
public interface CacheResolver {
    Collection<? extends Cache> resolveCaches(
            CacheOperationInvocationContext<?> context);
}
```

`context.getArgs()` provides the invocation arguments; `context.getMethod()` and `context.getTarget()` allow inspecting the method/target object; `context.getOperation()` provides metadata of the cache operation. The resolver **returns `Cache` objects, not string names**. The result must not be `null`; when a required cache cannot be found, a clear error should be raised. Implementations must be thread-safe because the bean may be called concurrently.

By default, Spring uses an equivalent of `SimpleCacheResolver` to look up the names in `cacheNames`/`value` from the configured `CacheManager`. Write a custom resolver only when the selection depends on information that static names or specifying a manager cannot sufficiently express.

## 3. Choosing the Right Mechanism for the Problem

| Requirement | How to configure | When to use |
| --- | --- | --- |
| A fixed cache | `@Cacheable(cacheNames = "products")` | The method always accesses one cache. |
| Same cache name, different manager per method | `@Cacheable(cacheNames = "products", cacheManager = "fastCacheManager")` | Each operation uses a fixed backend. |
| Partition cache by runtime argument | `@Cacheable(cacheResolver = "audienceCacheResolver")` | The cache is determined by the call's audience/tenant/region. |
| Shared configuration across methods | `@CacheConfig(cacheNames = "products")` or `@CacheConfig(cacheResolver = "audienceCacheResolver")` | Reduces repetition in a service; methods can still override when needed. |
| One method triggers multiple cache operations | `@Caching(...)` | Combines multiple annotations with distinct purposes; consistency between operations must be verified. |

**Important rule:** On the **same cache operation**, do not specify both `cacheManager` and `cacheResolver` because the two options are mutually exclusive. When using a custom resolver, `cacheNames` can be omitted: the resolver decides the list of caches itself. However, if the resolver relies on `context.getOperation().getCacheNames()`, you must still declare the required names.

Do not use a resolver merely to change the key. If the physical cache stays the same and you only need to distinguish customer IDs/tenants, `key = "#p0 + ':' + #p1"` or a `KeyGenerator` is often enough. A resolver becomes clearly meaningful when you need to separate backends, TTLs, access controls, or storage regions per invocation.

## 4. Runnable Example: Selecting PUBLIC/VIP Cache on Read, Update, and Evict

The example uses **Java 17+, Spring Boot 3.3.x / Spring Framework 6.1.x**, including the `spring-boot-starter` and `spring-boot-starter-cache` dependencies. Create a Spring Boot application with those two starters and place the code below at `src/main/java/demo/cache/CacheRoutingDemo.java`. The in-memory `ConcurrentMapCacheManager` lets you observe the behavior without needing Redis.

```java
package demo.cache;

import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.interceptor.CacheResolver;
import org.springframework.context.annotation.Bean;
import org.springframework.stereotype.Service;

@SpringBootApplication
@EnableCaching
public class CacheRoutingDemo {

    public static void main(String[] args) {
        SpringApplication.run(CacheRoutingDemo.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        // Pre-declare the allowed caches.
        return new ConcurrentMapCacheManager("catalogPublic", "catalogVip");
    }

    @Bean("audienceCacheResolver")
    CacheResolver audienceCacheResolver(CacheManager manager) {
        return context -> {
            Object[] args = context.getArgs();
            if (args.length == 0 || !(args[0] instanceof Audience audience)) {
                throw new IllegalArgumentException(
                        "First argument must be Audience");
            }

            String name = audience == Audience.VIP
                    ? "catalogVip"
                    : "catalogPublic";
            Cache cache = manager.getCache(name);
            if (cache == null) {
                throw new IllegalStateException("Cache not configured: " + name);
            }
            return List.of(cache);
        };
    }

    @Bean
    CommandLineRunner demo(CatalogService service) {
        return args -> {
            System.out.println(service.find(Audience.PUBLIC, 42L));
            System.out.println(service.find(Audience.PUBLIC, 42L));
            System.out.println(service.find(Audience.VIP, 42L));
            System.out.println(service.refresh(Audience.PUBLIC, 42L));
            System.out.println(service.find(Audience.PUBLIC, 42L));
            service.invalidate(Audience.VIP, 42L);
            System.out.println(service.find(Audience.VIP, 42L));
            System.out.println("Method executions: " + service.executionCount());
        };
    }
}

enum Audience {
    PUBLIC, VIP
}

@Service
class CatalogService {
    private final AtomicInteger executions = new AtomicInteger();

    @Cacheable(cacheResolver = "audienceCacheResolver", key = "#p1")
    public String find(Audience audience, long productId) {
        return audience + "#" + productId + "-load-"
                + executions.incrementAndGet();
    }

    @CachePut(cacheResolver = "audienceCacheResolver", key = "#p1")
    public String refresh(Audience audience, long productId) {
        return audience + "#" + productId + "-refresh-"
                + executions.incrementAndGet();
    }

    @CacheEvict(cacheResolver = "audienceCacheResolver", key = "#p1")
    public void invalidate(Audience audience, long productId) {
        // Real data deletion/modification logic would go here.
    }

    public int executionCount() {
        return executions.get();
    }
}
```

Launch with `./gradlew bootRun` (Windows PowerShell: `./gradlew.bat bootRun`) in a Spring Boot project with the Gradle Wrapper. The `System.out.println` statements will produce the exact output below; Spring Boot startup logs may also appear:

```text
PUBLIC#42-load-1
PUBLIC#42-load-1
VIP#42-load-2
PUBLIC#42-refresh-3
PUBLIC#42-refresh-3
VIP#42-load-4
Method executions: 4
```

Step-by-step explanation:

1. First PUBLIC read: the `catalogPublic` cache misses, so `find` runs (execution 1).
2. Repeated PUBLIC/42 read: hits the same cache/key, so the method body is skipped; it still returns the value from execution 1.
3. VIP/42 read: the resolver selects `catalogVip`, misses independently, and runs `find` (execution 2).
4. `refresh(PUBLIC, 42)` has `@CachePut`: **always executes the method** and writes the new value to `catalogPublic` (execution 3).
5. Reading PUBLIC/42 receives the new data without executing `find`.
6. `invalidate(VIP, 42)` evicts only key 42 in `catalogVip`; reading VIP/42 again misses (execution 4). PUBLIC is unaffected.

The key takeaway is that all three **read – write – delete** operations use the same PUBLIC/VIP routing rule and the same key `#p1`. Here `#p1` is the second parameter (`productId`), avoiding reliance on parameter names at compile time. The first parameter (`audience`) participates in **cache selection**. If everything were combined into one cache, a lone key `42` would not suffice to distinguish the two audiences.

## 5. Variants Worth Knowing

### 5.1. Selecting a Manager per Method Without a Custom Resolver

```java
@Cacheable(cacheNames = "productCards", cacheManager = "localCacheManager")
public ProductCard findCard(long id) { /* ... */ }

@Cacheable(cacheNames = "productDetails", cacheManager = "redisCacheManager")
public ProductDetails findDetails(long id) { /* ... */ }
```

The snippet above is an **illustration inside an existing service**, not a standalone program. Both `CacheManager` beans must be pre-configured; each method chooses a fixed manager. When selection depends on runtime arguments of the *same* method, a custom `CacheResolver` is more appropriate.

### 5.2. Distinguishing Rules for Each Operation

- `@Cacheable` checks the cache first; on a matching hit, the method does not run. `condition` and `unless` affect caching according to the timing Spring supports.
- `@CachePut` executes the method and updates the cache conditionally; do not use it to optimize read calls. Avoid placing `@CachePut` and `@Cacheable` on the same method unless you have proven their conditions are mutually exclusive.
- `@CacheEvict` by default evicts **after the method succeeds**; `beforeInvocation = true` evicts beforehand even if the method might throw an exception. `allEntries = true` clears all **caches returned by the resolver**, and `key` cannot be configured at the same time.
- `@Caching` groups multiple operations. Each operation may declare different caches, but operations touching the same entity must stay consistent in cache routing and key.

Illustrative example of a policy clearing an **entire single region**:

```java
@CacheEvict(cacheResolver = "audienceCacheResolver", allEntries = true)
public void invalidateAudience(Audience audience) {
    // Perform changes to this audience's data.
}
```

The resolver reads `audience` and returns only `catalogPublic` or `catalogVip`; therefore `allEntries` here does not mean clearing **every cache in the CacheManager**. Conversely, if the resolver returns multiple caches, the operation can affect all of those caches.

### 5.3. Sharing Resolver Configuration

```java
@CacheConfig(cacheResolver = "audienceCacheResolver")
@Service
class AnotherCatalogService {
    @Cacheable(key = "#p1")
    public String read(Audience audience, long id) { /* ... */ return ""; }
}
```

This snippet illustrates class-level configuration syntax; in real usage, replace the method body with actual business logic. `@CacheConfig` shares defaults, while method-level annotations can specify operation-specific configuration.

## 6. Critical Architectural Risks

**Tenant isolation / authorization.** A resolver may rely on a tenant from an argument or a trusted authentication context. You must verify that the caller is actually authorized to access that tenant before returning data. Splitting caches by role is not necessarily secure enough: if two VIP users have different personal data, the key still needs the user identity or a safer data partition. Do not put sensitive information in cache names or logs.

**Consistency when updating data.** When a product is cached across multiple regions, updating the database may require invalidating **all** regions containing affected data, not just the caller's region. A resolver returning the right cache is a routing decision; it does not automatically ensure the rest of the system holds no stale data. Clearly map create/update/delete flows and verify acceptable staleness; for transactions, consider post-commit eviction timing.

**Thread safety and performance.** Do not use instance variables like `currentAudience` or store per-request state in a singleton resolver. Use local variables and thread-safe cache managers; avoid making heavy network API calls on every resolution. If a cache name does not exist, throw a configuration error instead of silently falling back to another group's cache.

**Resolver vs. key and TTL.** A resolver only selects the `Cache`; it does not create TTL or eviction policies on its own. TTL, size, serialization, backend, stats, and distributed policies are configured on the provider (Caffeine, Redis, etc.). If the provider creates caches dynamically by name, manage the number of cache names to prevent unbounded growth per tenant.

**Proxy boundary.** `@EnableCaching` must be enabled, the service must be a Spring-managed bean, and calls must pass through the proxy. Calling `this.find(...)` from a method on the same object usually bypasses interception in the default proxy mode, preventing the resolver from running. The fix is to move the method to another bean or redesign the call flow through the Spring proxy; never call `new CatalogService()` directly and expect annotations to work.

**Configuring multiple beans.** When multiple `CacheManager` or `CacheResolver` beans exist, explicitly identify the default bean or bean name; `@Cacheable(cacheResolver="...")` points to the exact **bean name**. Never set both `cacheManager` and `cacheResolver` on one operation.

## 7. Testing and Troubleshooting

Test according to *observable behavior*, rather than merely verifying that the resolver returns the expected name:

| Scenario | Expectation |
| --- | --- |
| PUBLIC/42 called twice | `find` body runs once; subsequent call is a cache hit. |
| After PUBLIC/42, call VIP/42 | VIP reads its own cache and does not use PUBLIC data. |
| `refresh(PUBLIC,42)` | PUBLIC value is replaced; VIP remains unchanged. |
| `invalidate(VIP,42)` | VIP misses on the next call; PUBLIC still hits. |
| Missing cache name | Clear configuration error, no fallback to another audience. |
| Calling via `this.find` | Recognized as self-invocation bypassing the proxy. |
| Multiple threads calling concurrently | Resolver has no mutable per-request state; also test provider behavior on concurrent cache misses. |

When results differ from expectations, check in order: (1) whether the annotation runs through a proxy; (2) whether the resolver bean name is correct; (3) whether `context.getArgs()` has the expected order/values; (4) which cache the resolver returns; (5) whether the key expression matches across reads/writes/evictions; (6) whether the provider has its own TTL, eviction, serialization, or async behavior. `@Cacheable(sync = true)` can limit duplicate loads on concurrent cache misses for the same key if supported by the provider, but does not replace cache selection policies or data consistency.

## 8. Key Takeaways

- The simplest sufficient approach is `cacheNames`; add `cacheManager` when a fixed backend per method is needed; use `cacheResolver` when the choice truly depends on the invocation.
- `CacheResolver` decides the **cache(s)**, while `key`/`KeyGenerator` decides the **entry**; both must stay consistent across `@Cacheable`, `@CachePut`, and `@CacheEvict`.
- The resolver runs on the cache path, must be thread-safe, must return valid caches, and cannot depend on a method result that does not exist yet.
- Cache partitioning does not replace authorization checks, TTLs, or cross-partition invalidation.

### Official References

- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — Configuring the Cache Storage](https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html)
- [CacheResolver API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/interceptor/CacheResolver.html)
